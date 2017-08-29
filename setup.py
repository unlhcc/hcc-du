from setuptools import setup

setup(
    name='hcc-du',
    version='1.0',
    description='HCC Disk Quota Utility',
    url='https://github.com/unlhcc/hcc-du',
    author='HCC',
    author_email='hcc-support@unl.edu',
    license='GPLv3',
    packages=['hccdu'],
    python_requires='<3',
    entry_points = {
        'console_scripts': [
        'hcc-du = hccdu.du:main',
        'lquota.py = hccdu.lquota:main',
        'rquota.py = hccdu.rquota:main',
        'purge.py = hccdu.purge:main',
        ],
    },    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Natural Language :: English',
        'Operating System :: Unix',
        'Topic :: System :: Filesystems',
        'Topic :: Utilities',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
    ],
)
