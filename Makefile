deps-dev:
	pip install -r requirements_dev

test:
	python -m rabbitmqalert.tests.test_rabbitmqalert -b
	python -m rabbitmqalert.tests.test_optionsresolver -b

test-install:
	python setup.py install

clean:
	rm -rf dist/ rabbitmq_alert.egg-info/

dist: clean
	python setup.py sdist

dist-inspect:
	tar -tvf dist/*

publish: dist
	twine upload dist/*

test-publish: dist
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*
