pipeline {
    agent { label 'python311' }

    options {
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
    }

    environment {
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Validate') {
            steps {
                sh 'python -m py_compile ca_analyzer/*.py tests/*.py'
            }
        }
        stage('Test') {
            steps {
                sh 'python -m pytest tests/ -v --tb=short --junit-xml=test-results/results.xml'
            }
            post {
                always {
                    junit 'test-results/results.xml'
                }
            }
        }
        stage('Smoke') {
            steps {
                sh '''
                    python -m ca_analyzer.cli analyze fixtures/sample_events.log
                    python -m ca_analyzer.cli analyze fixtures/sample_rlf.log --format json | python -m json.tool
                    python -m ca_analyzer.cli analyze fixtures/sample_events.log --filter-kind SCEL_ADD,RLF
                '''
            }
        }
    }
}
