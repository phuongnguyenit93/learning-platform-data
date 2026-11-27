# Distinguishing Platform Conditions from Shell Commands

When reading a CI/CD pipeline, you often see many constructs that look like programming statements: if, logical operators, variables, comparison expressions, and command blocks. However, they can belong to different languages and execute at different times. A condition in the pipeline configuration is interpreted by the CI engine; a statement inside run, script, or sh is executed by the shell on the runner/agent.

Distinguishing these two layers is an essential skill when writing **Pipeline as Code** within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**. A pipeline as code describes Git events, job graphs, conditions, permissions, environments, artifacts, and automated steps. Shell commands perform concrete work on the runner, such as installing dependencies, compiling, running tests, packaging, or deploying. Writing logic in the right layer makes pipelines easier to read, predictable, maintainable, and safer.

## 1. A pipeline file has multiple language layers

A YAML file does not mean everything inside it is a shell script. Typically, there are at least three layers:

1. **YAML:** the data structure syntax such as keys, values, lists, indentation, and block scalars. YAML represents configuration; YAML itself does not decide whether a job runs.
2. **CI platform configuration language:** keys and expressions such as if, rules, when, condition, needs, dependsOn, matrix, or environment. The CI engine understands these elements to generate the pipeline, select jobs, and orchestrate execution order.
3. **Runner process language:** content inside run, script, sh, bash, pwsh, or powershell. These are commands executed by a specific shell or program on the runner/agent machine.

Example:

~~~yaml
steps:
  - name: Run only on the main branch
    if: ${{ github.ref == 'refs/heads/main' }}
    run: |
      echo "Starting checks"
      if [ -f package.json ]; then
        npm test
      else
        echo "package.json not found"
        exit 1
      fi
~~~

In this example:

- steps, name, if, and run are GitHub Actions configuration constructs.
- The expression in if is evaluated by GitHub Actions to decide whether the step should run.
- The lines inside run are executed by the shell after the step is selected.
- if [ -f package.json ] is a Bash shell condition checking for a file on the runner machine.

Both constructs contain the keyword if, yet they belong to different languages and have different responsibilities.

## 2. Which stages process a pipeline?

A useful mental model is to trace the path from configuration to command execution:

~~~mermaid
flowchart TD
    A["Git event or run request"] --> B["Read and validate YAML"]
    B --> C["CI engine parses platform DSL"]
    C --> D["Apply triggers, rules, conditions, dependencies"]
    D --> E{"Is job/step eligible?"}
    E -- "No" --> F["Skip or do not create job"]
    E -- "Yes" --> G["Runner/agent picks up work"]
    G --> H["Prepare environment and variables"]
    H --> I["Launch shell or program"]
    I --> J["Execute commands, capture exit code and output"]
    J --> K["CI engine updates pipeline status"]
~~~

Implementation details vary by platform. Some platforms evaluate certain expressions when creating the pipeline, while others evaluate conditions right before a stage, job, or step. Even so, the conceptual boundary remains useful: **the CI engine decides which units of work execute; the process on the runner executes the commands for that work.**

A platform condition is typically evaluated before the corresponding step starts. If the condition is false, the step or job may enter the skipped state. Once the shell has started, conditions inside the script only control the flow of that process. They do not dynamically alter the pipeline graph or prevent other jobs from being scheduled.

## 3. What do CI platform conditions do?

A platform condition is an expression or configuration belonging to the CI/CD product's DSL. It answers orchestration questions such as:

- Should a pipeline be created for this event?
- Should this job run on this branch or tag?
- Is the next stage allowed to start based on the previous stage's outcome?
- Should a step run only when a prior job succeeded, failed, or was canceled?
- Does deployment need to wait for environment approval?
- Should a matrix of jobs be generated across runtime versions or operating systems?

Platform conditions typically read metadata provided by the CI system: event name, branch, tag, commit SHA, dependent job results, pipeline parameters, configuration variables, and environment details. Expression syntax is platform-specific. Never assume a GitHub Actions expression works verbatim in GitLab CI, Jenkins, or Azure Pipelines.

### 3.1. Condition examples across platforms

| Platform | How conditions are declared | Evaluation context |
| --- | --- | --- |
| GitHub Actions | if: github.ref == 'refs/heads/main' | GitHub Actions expressions and contexts |
| GitLab CI/CD | rules:if with $CI_COMMIT_BRANCH == "main" | rules:if expressions evaluated when GitLab creates the pipeline |
| Jenkins Declarative Pipeline | when { branch 'main' } | Jenkins Pipeline stage condition |
| Azure Pipelines | condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main')) | Azure Pipelines condition expression language |

These examples express similar intent: allow part of the pipeline to run only when the branch is main. Their syntax and evaluation timing differ. When migrating pipelines between platforms, translate the logic into the target DSL rather than merely renaming keys.

### 3.2. GitHub Actions: if belongs to workflow expressions

GitHub Actions provides contexts such as github, env, vars, needs, and inputs, along with status functions such as success(), failure(), cancelled(), or always(). These belong to the GitHub Actions expression environment, not automatic Bash variables.

~~~yaml
jobs:
  deploy:
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy
        run: ./scripts/deploy.sh
~~~

Here, the deploy job runs only when the event is push and the ref is the main branch. The condition is evaluated against the GitHub Actions context. The command ./scripts/deploy.sh runs only when the job is selected and the runner starts executing the step.

Another example is running a log collection step even if a previous test step failed:

~~~yaml
- name: Upload diagnostic logs
  if: ${{ failure() }}
  run: ./scripts/collect-logs.sh
~~~

failure() is a GitHub Actions status check function. Writing if [ "$?" -ne 0 ] in the shell is a different mechanism: it checks the exit code of the preceding shell command within the same process, and cannot replace a job-wide status condition.

### 3.3. GitLab CI/CD: rules decide whether a job is included in the pipeline

In GitLab CI/CD, rules are evaluated in order when the pipeline is created. The first matching rule determines the attributes applied to the job, such as when, allow_failure, or additional variables. If no rule matches and there is no suitable fallback, the job may not be added to the pipeline at all.

~~~yaml
deploy_staging:
  stage: deploy
  rules:
    - if: '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == "main"'
      when: on_success
    - when: never
  script:
    - ./scripts/deploy.sh staging
~~~

The expression in rules:if uses GitLab syntax, not Bash syntax. Lines under script are executed by the runner using its configured shell. The final rule when: never makes clear that unmatched cases must not run the job.

Do not write a shell expression such as [ "$CI_COMMIT_BRANCH" = "main" ] inside rules:if and expect GitLab to execute it. At rule evaluation time, GitLab is parsing its own DSL expression; no shell process has been launched yet.

### 3.4. Jenkins: Declarative when differs from sh

In a Jenkins Declarative Pipeline, when is a stage condition construct. sh launches a shell on a Unix/Linux agent; bat or powershell/pwsh is used for Windows environments as configured.

~~~groovy
pipeline {
    agent any

    stages {
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    if [ "$DEPLOY_ENV" = "staging" ]; then
                        ./scripts/deploy.sh "$DEPLOY_ENV"
                    else
                        echo "Invalid deployment environment" >&2
                        exit 1
                    fi
                '''
            }
        }
    }
}
~~~

branch 'main' is a Jenkins Declarative Pipeline stage condition, commonly used in Multibranch Pipelines. The if [ ... ] block sits inside the string passed to sh, so it is Bash/POSIX shell depending on the shell configured in Jenkins. In a Scripted Pipeline, an if statement outside sh is Groovy logic; you must distinguish those contexts clearly.

### 3.5. Azure Pipelines: condition uses Azure expressions

Azure Pipelines provides expression functions such as and, or, eq, ne, succeeded, failed, and always. These functions are used in the condition property to orchestrate stages, jobs, or steps.

~~~yaml
stages:
  - stage: Deploy
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - job: DeployStaging
        steps:
          - bash: |
              if [ "$DEPLOY_ENV" = "staging" ]; then
                ./scripts/deploy.sh "$DEPLOY_ENV"
              else
                echo "Invalid deployment environment" >&2
                exit 1
              fi
            env:
              DEPLOY_ENV: $(DEPLOY_ENV)
~~~

condition is an Azure Pipelines expression. The bash section is a Bash script running on the agent. The $(DEPLOY_ENV) syntax is Azure Pipelines macro expansion injecting the variable value into task configuration; inside Bash, the variable passed via env is read as $DEPLOY_ENV.

Azure Pipelines has multiple expression processing phases, including template expressions, macro syntax, and runtime expressions. When writing complex pipelines, identify which phase expands each expression; do not treat every bracketed form as shell syntax.

## 4. What do shell commands do?

Shell scripts execute after the runner/agent accepts a step. They are typically used to perform operating system operations or invoke tools installed in the environment:

- Create directories, copy, or inspect files.
- Install dependencies and select runtime versions.
- Compile and run unit tests or integration tests.
- Package JARs, artifacts, or container images.
- Invoke CLIs to upload artifacts, run migrations, or deploy.
- Check local process conditions and return an exit code.

The shell has no built-in knowledge of contexts such as github.ref, needs.build.result, or Build.SourceBranch unless the pipeline passes those values into environment variables or files. Conversely, platform expressions cannot directly run commands like grep, test -f, npm test, or docker build simply because the command name appears in a string.

### 4.1. Condition example inside Bash

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$DEPLOY_ENV" == "staging" ]]; then
  echo "Deploying to staging"
  ./scripts/deploy.sh staging
elif [[ "$DEPLOY_ENV" == "production" ]]; then
  echo "Deploying to production"
  ./scripts/deploy.sh production
else
  echo "Unsupported DEPLOY_ENV: $DEPLOY_ENV" >&2
  exit 2
fi
~~~

if, elif, [[ ... ]], echo, exit, and the variables in this example are Bash syntax or builtins. They only control the process executing the script. For example, the else branch exits the script with status 2; the CI engine receives a non-zero exit code and typically marks the step as failed.

### 4.2. Condition example inside PowerShell

~~~powershell
if ($env:DEPLOY_ENV -eq "staging") {
    Write-Output "Deploying to staging"
    ./scripts/deploy.ps1 -Environment staging
}
elseif ($env:DEPLOY_ENV -eq "production") {
    Write-Output "Deploying to production"
    ./scripts/deploy.ps1 -Environment production
}
else {
    Write-Error "Unsupported DEPLOY_ENV: $env:DEPLOY_ENV"
    exit 2
}
~~~

This is PowerShell, not Bash. Variable referencing, comparison operators, braces, and error handling all differ. A script that works on Ubuntu is not guaranteed to work on Windows if the shell or dependent tools differ.

### 4.3. Shells are selected by runner or step configuration

Keys named run, script, or sh do not guarantee the same shell across all platforms:

| Platform/configuration | Common way shell is selected |
| --- | --- |
| GitHub Actions | shell: bash, shell: pwsh, shell: powershell, shell: cmd, or runner default |
| GitLab Runner | Shell configured on the runner/executor; the container image also affects available programs |
| Jenkins | sh, bat, powershell, or pwsh selects the corresponding execution step |
| Azure Pipelines | bash, pwsh, powershell, script, or cmdLine tasks select the corresponding interpreter |

When shell syntax affects correctness, declare the shell explicitly and choose an image/agent that includes the required tools. Do not write Bash and run it with PowerShell, or use PowerShell syntax inside a Bash task.

## 5. Direct comparison: one requirement, two condition layers

Suppose a team wants to deploy to staging when commits are pushed to the main branch, while only running the deploy command if the DEPLOY_ENABLED variable is turned on.

There are two distinct decisions:

1. **Orchestration decision:** do the event and branch allow the deployment job to be included? This is a CI platform condition.
2. **In-process decision:** once the job is running, is deployment configuration enabled and does the required file exist? This can be a shell condition, or should be elevated to a platform check/gate if it governs release eligibility.

GitHub Actions example:

~~~yaml
jobs:
  deploy-staging:
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
    env:
      DEPLOY_ENABLED: ${{ vars.DEPLOY_ENABLED }}
    steps:
      - uses: actions/checkout@v4
      - name: Deploy if enabled
        shell: bash
        run: |
          if [[ "$DEPLOY_ENABLED" == "true" ]]; then
            test -f deploy/manifest.yml
            ./scripts/deploy.sh staging
          else
            echo "Staging deployment is disabled"
          fi
~~~

The job condition restricts the pipeline to push events on main. Bash checks the configuration variable and manifest file in the workspace. If DEPLOY_ENABLED is not enabled, the job still runs and the step exits normally after printing the message. If the requirement is for the job to appear as skipped when disabled, move the appropriate variable check into the platform condition instead of checking it only inside the shell.

The example above uses the repository variable vars.DEPLOY_ENABLED for illustration. For sensitive data, use secrets or an appropriate credential-issuing mechanism; do not place secrets in public configuration variables.

## 6. Passing data between the platform and the shell

The two layers can exchange data, but must use a platform-supported mechanism. There is no universal rule that every variable in pipeline expressions automatically appears in the shell.

### 6.1. Passing context values into environment variables

In GitHub Actions, you can use env:

~~~yaml
- name: Build for selected ref
  env:
    SOURCE_REF: ${{ github.ref }}
  run: |
    printf 'Building ref: %s\n' "$SOURCE_REF"
    ./scripts/build.sh "$SOURCE_REF"
~~~

GitHub Actions expands the context expression while preparing the step, then passes the value to the process via the environment. Bash simply reads the SOURCE_REF variable; it does not re-evaluate the github.ref expression.

In Azure Pipelines, you can use env combined with the $(variable) macro. In GitLab, predefined variables like CI_COMMIT_SHA are typically injected into the job environment by the runner. In Jenkins, you can use Pipeline env variables and pass them into sh/bat commands. Read the platform documentation to know which variables are available at a given stage/job/step.

### 6.2. Returning results from the shell to the CI engine

If a script computes a value needed by a later step or job, export the result according to the platform's protocol:

| Platform | Common mechanism |
| --- | --- |
| GitHub Actions | Write name=value to the file pointed to by GITHUB_OUTPUT, then declare step/job outputs |
| GitLab CI/CD | Use a dotenv report artifact to pass variables to downstream stage jobs per dependency rules |
| Jenkins | Assign Pipeline variables, use returnStdout, or use stash/artifacts depending on data type |
| Azure Pipelines | Write logging command ##vso[task.setvariable ...] to stdout per Azure syntax |

GitHub Actions example:

~~~yaml
steps:
  - id: version
    name: Determine version
    shell: bash
    run: |
      VERSION="$(./scripts/read-version.sh)"
      printf 'version=%s\n' "$VERSION" >> "$GITHUB_OUTPUT"

  - name: Use version
    env:
      RELEASE_VERSION: ${{ steps.version.outputs.version }}
    run: |
      printf 'Release version: %s\n' "$RELEASE_VERSION"
~~~

The shell produces the value and writes it to the output file provided by GitHub. GitHub Actions reads that file, publishes the step output, and the expression in the next step references that output. This forms an explicit data-exchange contract between the two layers.

Do not assume a shell variable exported in one step automatically persists in another step. Each step typically runs in its own process; sharing mechanisms must be declared explicitly.

## 7. Distinguishing skipped, success, and failure states

A false platform-level condition and a shell command returning an error code produce different outcomes:

| Scenario | Typical outcome | Meaning |
| --- | --- | --- |
| Platform condition is not satisfied | Job/step is skipped or omitted from the pipeline | The CI engine decided not to execute it |
| Shell condition takes a no-op branch and exits with 0 | Step succeeds | The process ran and exited normally |
| Shell command returns non-zero code | Step fails, unless error-handling policy allows it | The process ran and reported an error |
| Platform condition uses special status functions | May run after prior failure or cancellation | Requires understanding exact platform semantics |

For example, the following script does not fail the step when the variable is disabled:

~~~bash
if [[ "$DEPLOY_ENABLED" == "true" ]]; then
  ./scripts/deploy.sh staging
else
  echo "Skipping deployment"
fi
~~~

This is a valid choice if the intent is a job that ran and did not need to deploy. However, the dashboard will show the step as succeeded, not skipped. If you need a skipped status to report accurately that the deployment step did not apply, express the condition at the platform layer.

Conversely, if a script detects missing required configuration, it should fail:

~~~bash
if [[ -z "${DEPLOY_ENV:-}" ]]; then
  echo "Missing DEPLOY_ENV" >&2
  exit 1
fi
~~~

Do not turn a configuration error into a success by merely printing a warning and continuing. The CI engine can reflect outcomes accurately only when processes return appropriate exit codes.

## 8. Security when passing data to the shell

The boundary between platform expressions and the shell is also a critical security boundary. Data from branch names, PR titles, commit messages, user inputs, or external systems can contain special characters. If that data is interpolated directly into script text, those characters can be interpreted as shell syntax.

### 8.1. Avoid interpolating untrusted data directly into scripts

Unsafe example in GitHub Actions:

~~~yaml
- name: Print pull request title
  run: echo "${{ github.event.pull_request.title }}"
~~~

The context expression is expanded before the shell executes. If the PR title contains quotes, semicolons, or shell syntax, the injected content can alter the command. This is a form of command injection.

A safer approach is passing the value via an environment variable and quoting it when used:

~~~yaml
- name: Print pull request title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$PR_TITLE"
~~~

Here, the PR title is environment data; the shell does not re-parse the variable's content as source code. Using printf with a fixed format string and quoting "$PR_TITLE" preserves the literal value. Never use eval or concatenate untrusted data into commands.

### 8.2. Prevent unintended shell variable expansion

In Bash, quote variables when passing arguments:

~~~bash
./scripts/deploy.sh "$DEPLOY_ENV"
~~~

If you omit quotes:

~~~bash
./scripts/deploy.sh $DEPLOY_ENV
~~~

the shell can perform word splitting and pathname expansion. A value containing spaces or wildcard characters can be split into multiple arguments or match unintended files.

In addition:

- Never print secrets to logs, even while debugging.
- Do not pass secrets via command-line arguments if they risk exposure in process lists or logs.
- Use secret stores/secret contexts and least privilege.
- Do not expose production secrets to pipelines executing untrusted code, such as jobs from forks unless policy explicitly permits and isolates them.
- Avoid string concatenation from input data to build commands; pass data as arguments or environment variables.
- Inspect script and dependency permissions before allowing a pipeline to execute.

Passing via environment variables prevents common script-interpolation bugs, but does not automatically make data safe. Scripts must still validate values, quote properly, and avoid passing data into eval, SQL, or contexts with separate escaping rules.

## 9. Common pitfalls

| Incorrect syntax or assumption | Why it is wrong | How to fix it |
| --- | --- | --- |
| Writing Bash syntax in GitLab rules:if | GitLab is evaluating the rules DSL, not running a shell yet | Use GitLab-valid operators and variables |
| Using github.ref directly in Bash | That is a GitHub Actions context, not a default environment variable | Pass via env, e.g., REF: ${{ github.ref }} |
| Using $VAR in every kind of condition | Each platform has its own variable syntax and expansion phase | Identify the DSL and context of the property being written |
| Thinking shell if can skip a job | The shell only controls an already-running process | Place the condition on the platform's job/stage/step |
| Thinking a false condition always turns the pipeline red | Unmet conditions typically result in skipped | Distinguish skipped from failure in reporting |
| Using && identically everywhere | && has different meaning or is invalid in some DSLs | Check the platform's expression syntax |
| Writing Bash but running it with PowerShell | The shell does not understand the other language's syntax | Declare the shell explicitly or write OS-appropriate scripts |
| Assuming a variable exported in one step persists in the next | Steps typically run as independent processes | Use outputs, artifacts, or platform variable mechanisms |
| Interpolating PR titles directly into scripts | Data can turn into executable shell syntax | Pass through environment variables and quote properly |
| Assuming a job with if suffices to protect production | Run conditions do not replace access controls, approvals, or secret protection | Combine environment protection, least privilege, and approvals |

## 10. How to read and write a step without mixing contexts

When reading a pipeline snippet, ask these questions in sequence:

1. **Is this a YAML key or script content?** Check indentation and parent keys like if, condition, script, run, bash, or sh.
2. **Who interprets this expression?** GitHub Actions, GitLab, Jenkins, Azure Pipelines, or Bash/PowerShell?
3. **When is the expression evaluated?** At pipeline creation, before stage/job/step, or after the shell process starts?
4. **Where does the data come from?** Platform context, pipeline variable, environment, file, artifact, or previous step output?
5. **How is the result passed along?** Job status, exit code, output, artifact, environment variable, or log?
6. **What happens if the condition is false or a command fails?** Skipped, continued, retried, allowed failure, or failure?
7. **Does untrusted data enter the script?** If so, verify passing mechanism, quoting, and validation.

This workflow helps place logic in the right layer. Conditions involving branches, events, dependencies, approvals, and pipeline status usually belong to the platform. Conditions involving files on the runner, command outcomes, workspace contents, or local operations usually belong in scripts. If a shell check is truly a release gate, consider promoting it into a dedicated job/step with explicit status so downstream steps can orchestrate accurately.

## 11. Comprehensive example: test all PRs, deploy only from main

A basic pipeline needs to satisfy two requirements:

- Every PR runs automated checks.
- Only pushes to main create the staging deployment job.

With GitHub Actions:

~~~yaml
name: CI and staging

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        shell: bash
        run: |
          set -euo pipefail
          ./scripts/ci-test.sh

  deploy-staging:
    needs: [test]
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' && needs.test.result == 'success' }}
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Deploy
        env:
          DEPLOY_ENV: staging
        shell: bash
        run: |
          set -euo pipefail
          ./scripts/deploy.sh "$DEPLOY_ENV"
      - name: Verify deployment
        shell: bash
        run: ./scripts/smoke-test.sh staging
~~~

Read it across the two layers:

- on specifies which events can create the workflow.
- needs and if coordinate the deployment job after the test job and restrict it to pushes on main.
- environment: staging links the job to the configured GitHub environment, where protection rules or approvals can apply.
- run launches Bash on the runner.
- set -euo pipefail and the commands inside the script handle process-level errors.
- DEPLOY_ENV is passed via env; the script reads it as data.

In this example, test runs for both PRs and pushes to main. The deployment job depends on a successful test result. When porting to another platform, keep the intent intact while translating on, needs, if, environment, and output passing to that platform's corresponding constructs.

## 12. Checklist before putting a pipeline into use

**Configuration and platform conditions**

- [ ] Triggers and branch/tag filters match requirements.
- [ ] Job/stage/step conditions use the platform's valid DSL.
- [ ] Dependencies and success/failure states are declared explicitly.
- [ ] Skipped, allowed failure, and failure statuses have clear meaning in reports.
- [ ] Environment approvals and deployment permissions are configured in the right place.

**Shell and runner**

- [ ] Shell or execution interpreter is explicitly identified.
- [ ] Scripts use valid syntax for Linux/Windows and the image/agent provides required tools.
- [ ] Exit codes accurately reflect success or failure.
- [ ] Scripts do not implicitly depend on working directory assumptions or unpassed variables.
- [ ] Outputs between steps/jobs are shared via official mechanisms.

**Data and security**

- [ ] Platform context is passed into scripts in a controlled manner.
- [ ] Untrusted input data is never interpolated directly into shell code.
- [ ] Shell variables are properly quoted and validated.
- [ ] Secrets are never printed to logs or exposed to untrusted jobs.
- [ ] Token and runner permissions are scoped strictly to what the work requires.

## Conclusion

Platform conditions and shell commands are two complementary layers in Pipeline as Code. The platform DSL orchestrates triggers, jobs, stages, dependencies, statuses, and environments. The shell on the runner executes commands, inspects local resources, and returns exit codes or outputs. Identical keywords like if do not mean the same language or the same execution time.

When writing pipelines, identify who interprets each expression, at which stage it is evaluated, and how data crosses the boundary. Keep orchestration logic in platform configuration, keep local operations in scripts, pass data through controlled outputs/environments, and preserve honest exit codes. This approach produces pipelines that are easier to read, traceable, and safer when automating builds, tests, and releases.
