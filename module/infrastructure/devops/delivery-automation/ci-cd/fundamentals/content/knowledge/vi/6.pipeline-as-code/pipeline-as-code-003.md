# Phân biệt điều kiện của nền tảng với lệnh chạy trong shell

Khi đọc một pipeline CI/CD, bạn thường thấy nhiều cấu trúc trông giống lệnh lập trình: if, toán tử logic, biến, biểu thức so sánh và các khối lệnh. Tuy nhiên, chúng có thể thuộc những ngôn ngữ và thời điểm thực thi khác nhau. Một điều kiện trong cấu hình pipeline được bộ máy CI diễn giải; một câu lệnh trong run, script hoặc sh được shell trên runner/agent thực thi.

Phân biệt hai lớp này là kỹ năng quan trọng khi viết **Pipeline as Code** trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**. Pipeline dưới dạng mã mô tả sự kiện Git, đồ thị job, điều kiện, quyền, môi trường, artifact và các bước tự động. Các lệnh shell thực hiện công việc cụ thể trên runner, chẳng hạn cài dependency, biên dịch, chạy test, đóng gói hoặc triển khai. Viết đúng lớp giúp pipeline dễ đọc, có thể dự đoán, dễ bảo trì và an toàn hơn.

## 1. Một file pipeline có nhiều lớp ngôn ngữ

Một file YAML không đồng nghĩa toàn bộ nội dung bên trong là shell script. Thông thường, có ít nhất ba lớp:

1. **YAML:** cú pháp cấu trúc dữ liệu như key, value, list, indentation và block scalar. YAML giúp biểu diễn cấu hình; bản thân YAML không quyết định một job có chạy hay không.
2. **Ngôn ngữ cấu hình của nền tảng CI:** các key và biểu thức như if, rules, when, condition, needs, dependsOn, matrix hoặc environment. Bộ máy CI hiểu các thành phần này để tạo pipeline, chọn job và điều phối thứ tự thực thi.
3. **Ngôn ngữ của tiến trình trên runner:** nội dung nằm trong run, script, sh, bash, pwsh hoặc powershell. Đây là lệnh được một shell hay chương trình cụ thể thực thi trên máy runner/agent.

Ví dụ:

~~~yaml
steps:
  - name: Chỉ chạy trên nhánh main
    if: ${{ github.ref == 'refs/heads/main' }}
    run: |
      echo "Bắt đầu kiểm tra"
      if [ -f package.json ]; then
        npm test
      else
        echo "Không tìm thấy package.json"
        exit 1
      fi
~~~

Trong ví dụ này:

- steps, name, if và run là cấu trúc cấu hình của GitHub Actions.
- Biểu thức trong if được GitHub Actions đánh giá để quyết định step có được chạy hay không.
- Các dòng trong run được shell thực thi sau khi step được chọn.
- if [ -f package.json ] là điều kiện của shell Bash, kiểm tra file trên máy runner.

Hai cấu trúc cùng có từ khóa if, nhưng chúng không cùng ngôn ngữ và không cùng trách nhiệm.

## 2. Pipeline được xử lý theo những giai đoạn nào?

Một cách hình dung hữu ích là theo dõi đường đi từ cấu hình đến lệnh thực thi:

~~~mermaid
flowchart TD
    A["Sự kiện Git hoặc yêu cầu chạy"] --> B["Đọc và kiểm tra YAML"]
    B --> C["Bộ máy CI phân tích DSL của nền tảng"]
    C --> D["Áp dụng trigger, rules, condition, dependency"]
    D --> E{"Job/step có đủ điều kiện?"}
    E -- "Không" --> F["Bỏ qua hoặc không tạo job"]
    E -- "Có" --> G["Runner/agent nhận công việc"]
    G --> H["Chuẩn bị môi trường và biến"]
    H --> I["Khởi chạy shell hoặc chương trình"]
    I --> J["Thực thi lệnh, nhận exit code và output"]
    J --> K["Bộ máy CI cập nhật trạng thái pipeline"]
~~~

Chi tiết triển khai khác nhau theo nền tảng. Có nền tảng đánh giá một số biểu thức khi tạo pipeline, có nền tảng đánh giá điều kiện ngay trước stage, job hoặc step. Dù vậy, ranh giới khái niệm vẫn hữu ích: **bộ máy CI quyết định công việc nào được thực thi; tiến trình trên runner thực hiện các lệnh của công việc đó.**

Một điều kiện nền tảng thường được đánh giá trước khi step tương ứng bắt đầu. Nếu điều kiện sai, step hoặc job có thể ở trạng thái skipped. Khi shell đã chạy, điều kiện bên trong script chỉ điều khiển luồng của tiến trình đó. Nó không tự thay đổi đồ thị pipeline hay ngăn các job khác được lập lịch.

## 3. Điều kiện của nền tảng CI làm nhiệm vụ gì?

Điều kiện nền tảng (platform condition) là biểu thức hoặc cấu hình thuộc DSL của sản phẩm CI/CD. Nó trả lời các câu hỏi điều phối như:

- Pipeline có được tạo cho sự kiện này không?
- Job có chạy trên nhánh hoặc tag này không?
- Stage tiếp theo có được phép bắt đầu sau kết quả của stage trước không?
- Một bước chỉ chạy khi job trước thành công, thất bại hay bị hủy?
- Có cần chờ môi trường được phê duyệt trước khi triển khai không?
- Có cần tạo ma trận job theo phiên bản runtime hoặc hệ điều hành không?

Điều kiện nền tảng thường đọc metadata do hệ thống CI cung cấp: tên sự kiện, nhánh, tag, commit SHA, kết quả job phụ thuộc, tham số pipeline, biến cấu hình và thông tin môi trường. Cú pháp biểu thức phụ thuộc nền tảng. Không được giả định biểu thức của GitHub Actions có thể dùng nguyên dạng trong GitLab CI, Jenkins hay Azure Pipelines.

### 3.1. Ví dụ điều kiện trên một số nền tảng

| Nền tảng | Cách khai báo điều kiện | Ngữ cảnh được đánh giá |
| --- | --- | --- |
| GitHub Actions | if: github.ref == 'refs/heads/main' | Biểu thức và context của GitHub Actions |
| GitLab CI/CD | rules:if với $CI_COMMIT_BRANCH == "main" | Biểu thức rules:if khi GitLab tạo pipeline |
| Jenkins Declarative Pipeline | when { branch 'main' } | Điều kiện stage của Jenkins Pipeline |
| Azure Pipelines | condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main')) | Ngôn ngữ biểu thức condition của Azure Pipelines |

Những ví dụ này có ý nghĩa tương tự: chỉ cho phép một phần pipeline chạy khi nhánh là main. Cú pháp và thời điểm đánh giá không giống nhau. Khi chuyển pipeline giữa nền tảng, phải chuyển đổi logic theo DSL đích thay vì chỉ thay tên key.

### 3.2. GitHub Actions: if thuộc workflow expression

GitHub Actions cung cấp context như github, env, vars, needs, inputs và các hàm trạng thái như success(), failure(), cancelled() hoặc always(). Các giá trị này thuộc môi trường biểu thức của GitHub Actions, không phải biến tự động của Bash.

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

Ở đây, job deploy chỉ được chạy khi sự kiện là push và ref là nhánh main. Điều kiện được đánh giá theo context của GitHub Actions. Lệnh ./scripts/deploy.sh chỉ chạy khi job được chọn và runner bắt đầu thực thi step.

Một ví dụ khác là chạy bước thu thập log ngay cả khi bước test trước đó thất bại:

~~~yaml
- name: Upload diagnostic logs
  if: ${{ failure() }}
  run: ./scripts/collect-logs.sh
~~~

failure() là hàm trạng thái của GitHub Actions. Viết if [ "$?" -ne 0 ] trong shell là một cơ chế khác: nó kiểm tra exit code của lệnh shell trước đó trong cùng tiến trình, không thay thế được điều kiện trạng thái của toàn bộ job.

### 3.3. GitLab CI/CD: rules quyết định job có mặt trong pipeline

Trong GitLab CI/CD, rules được xét theo thứ tự khi tạo pipeline. Rule đầu tiên phù hợp quyết định thuộc tính áp dụng cho job, chẳng hạn when, allow_failure hoặc biến bổ sung. Nếu không rule nào khớp và không có cấu hình dự phòng phù hợp, job có thể không được thêm vào pipeline.

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

Biểu thức trong rules:if sử dụng cú pháp của GitLab, không phải cú pháp Bash. Dòng trong script được runner thực thi bằng shell đã cấu hình. Rule cuối when: never làm rõ rằng các trường hợp không khớp không được chạy job.

Không nên viết một biểu thức shell như [ "$CI_COMMIT_BRANCH" = "main" ] vào rules:if rồi kỳ vọng GitLab chạy nó. Ở giai đoạn xét rule, GitLab đang phân tích biểu thức DSL của mình; chưa có tiến trình shell nào được khởi chạy.

### 3.4. Jenkins: when của Declarative khác với sh

Trong Jenkins Declarative Pipeline, when là cấu trúc điều kiện của stage. sh khởi chạy shell trên agent Unix/Linux; bat hoặc powershell/pwsh được dùng cho môi trường Windows theo cấu hình tương ứng.

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
                        echo "Môi trường triển khai không hợp lệ" >&2
                        exit 1
                    fi
                '''
            }
        }
    }
}
~~~

branch 'main' là điều kiện stage của Jenkins Declarative Pipeline, thường dùng trong Multibranch Pipeline. Khối if [ ... ] nằm trong chuỗi truyền cho sh, vì vậy nó là Bash/POSIX shell tùy shell được Jenkins cấu hình. Nếu dùng Scripted Pipeline, một câu lệnh if bên ngoài sh lại là logic Groovy; phải phân biệt rõ ngữ cảnh đó.

### 3.5. Azure Pipelines: condition dùng biểu thức của Azure

Azure Pipelines có các hàm biểu thức như and, or, eq, ne, succeeded, failed và always. Các hàm này dùng trong thuộc tính condition để điều phối stage, job hoặc step.

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
                echo "Môi trường triển khai không hợp lệ" >&2
                exit 1
              fi
            env:
              DEPLOY_ENV: $(DEPLOY_ENV)
~~~

condition là biểu thức của Azure Pipelines. Phần bash là script Bash chạy trên agent. Cú pháp $(DEPLOY_ENV) là macro expansion của Azure Pipelines để đưa giá trị biến vào cấu hình task; bên trong Bash, biến đã được truyền qua env được đọc bằng $DEPLOY_ENV.

Azure Pipelines có nhiều giai đoạn xử lý biểu thức, gồm template expression, macro và runtime expression. Khi viết pipeline phức tạp, cần xác định biểu thức đang được mở rộng ở giai đoạn nào; không nên xem mọi dạng dấu ngoặc đều là cú pháp shell.

## 4. Lệnh shell làm nhiệm vụ gì?

Shell script chạy sau khi runner/agent nhận step. Nó thường dùng để thực hiện công việc trên hệ điều hành hoặc gọi công cụ cài trong môi trường:

- Tạo thư mục, sao chép hoặc kiểm tra file.
- Cài dependency và chọn phiên bản runtime.
- Biên dịch, chạy unit test hoặc integration test.
- Đóng gói JAR, package hoặc container image.
- Gọi CLI để upload artifact, migration hoặc triển khai.
- Kiểm tra điều kiện cục bộ của tiến trình và trả exit code.

Shell không tự biết các context như github.ref, needs.build.result hoặc Build.SourceBranch nếu pipeline không truyền giá trị đó vào môi trường hay file. Ngược lại, biểu thức của nền tảng không tự chạy được lệnh grep, test -f, npm test hoặc docker build chỉ vì tên lệnh xuất hiện trong một chuỗi.

### 4.1. Ví dụ điều kiện bên trong Bash

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$DEPLOY_ENV" == "staging" ]]; then
  echo "Triển khai lên staging"
  ./scripts/deploy.sh staging
elif [[ "$DEPLOY_ENV" == "production" ]]; then
  echo "Triển khai production"
  ./scripts/deploy.sh production
else
  echo "DEPLOY_ENV không được hỗ trợ: $DEPLOY_ENV" >&2
  exit 2
fi
~~~

if, elif, [[ ... ]], echo, exit và các biến trong ví dụ là cú pháp hoặc lệnh Bash. Chúng chỉ điều khiển tiến trình đang chạy script. Ví dụ, nhánh else kết thúc script với mã 2; bộ máy CI nhận mã khác 0 và thường đánh dấu step thất bại.

### 4.2. Ví dụ điều kiện bên trong PowerShell

~~~powershell
if ($env:DEPLOY_ENV -eq "staging") {
    Write-Output "Triển khai lên staging"
    ./scripts/deploy.ps1 -Environment staging
}
elseif ($env:DEPLOY_ENV -eq "production") {
    Write-Output "Triển khai production"
    ./scripts/deploy.ps1 -Environment production
}
else {
    Write-Error "DEPLOY_ENV không được hỗ trợ: $env:DEPLOY_ENV"
    exit 2
}
~~~

Đây là PowerShell, không phải Bash. Cách tham chiếu biến, toán tử so sánh, dấu ngoặc và xử lý lỗi đều khác. Một script chạy được trên Ubuntu chưa chắc chạy được trên Windows nếu shell hoặc công cụ phụ thuộc khác nhau.

### 4.3. Shell được chọn bởi runner hoặc cấu hình step

Tên key run, script hay sh không bảo đảm cùng một shell trên mọi nền tảng:

| Nền tảng/cấu hình | Cách chọn shell thường gặp |
| --- | --- |
| GitHub Actions | shell: bash, shell: pwsh, shell: powershell, shell: cmd hoặc mặc định theo runner |
| GitLab Runner | Shell được cấu hình cho runner/executor; image/container cũng ảnh hưởng chương trình có sẵn |
| Jenkins | sh, bat, powershell hoặc pwsh chọn bước thực thi tương ứng |
| Azure Pipelines | Task bash, pwsh, powershell, script hoặc cmdLine chọn bộ thực thi tương ứng |

Nếu cú pháp shell ảnh hưởng đến tính đúng đắn, hãy khai báo shell rõ ràng và chọn image/agent có công cụ cần thiết. Đừng viết Bash rồi chạy nó bằng PowerShell, hoặc dùng cú pháp PowerShell trong một task Bash.

## 5. So sánh trực tiếp: cùng một yêu cầu, hai lớp điều kiện

Giả sử nhóm muốn triển khai staging khi commit được push lên nhánh main, đồng thời chỉ chạy lệnh deploy nếu biến DEPLOY_ENABLED được bật.

Có hai quyết định khác nhau:

1. **Quyết định điều phối:** sự kiện và nhánh có cho phép job triển khai xuất hiện hay không? Đây là điều kiện của nền tảng CI.
2. **Quyết định trong tiến trình:** khi job đã chạy, cấu hình triển khai có đủ điều kiện và file cần thiết có tồn tại không? Đây có thể là điều kiện shell, hoặc nên được nâng lên thành kiểm tra/cổng nền tảng nếu nó quyết định việc phát hành.

Ví dụ GitHub Actions:

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
            echo "Triển khai staging đang bị tắt"
          fi
~~~

Điều kiện của job giới hạn pipeline vào sự kiện push trên main. Bash kiểm tra biến cấu hình và file manifest trong workspace. Nếu DEPLOY_ENABLED không bật, job vẫn được chạy và step kết thúc bình thường sau khi in thông báo. Nếu yêu cầu là job phải hiển thị trạng thái skipped khi tắt, hãy đưa biến phù hợp vào điều kiện của nền tảng thay vì chỉ kiểm tra bên trong shell.

Ví dụ trên dùng repository variable vars.DEPLOY_ENABLED để minh họa. Với dữ liệu nhạy cảm, dùng secret hoặc cơ chế cấp thông tin xác thực phù hợp; không đưa bí mật vào biến cấu hình công khai.

## 6. Cách truyền dữ liệu giữa nền tảng và shell

Hai lớp có thể trao đổi dữ liệu, nhưng phải dùng cơ chế được nền tảng hỗ trợ. Không có quy tắc chung rằng mọi biến trong biểu thức pipeline tự xuất hiện trong shell.

### 6.1. Truyền giá trị từ context vào biến môi trường

Trong GitHub Actions, có thể dùng env:

~~~yaml
- name: Build for selected ref
  env:
    SOURCE_REF: ${{ github.ref }}
  run: |
    printf 'Đang build ref: %s\n' "$SOURCE_REF"
    ./scripts/build.sh "$SOURCE_REF"
~~~

GitHub Actions mở rộng biểu thức context khi chuẩn bị step, sau đó truyền giá trị qua môi trường cho tiến trình. Bash chỉ đọc biến SOURCE_REF; nó không tự đánh giá lại biểu thức github.ref.

Trong Azure Pipelines, có thể dùng env kết hợp macro $(variable). Trong GitLab, các predefined variables như CI_COMMIT_SHA thường được runner đưa vào môi trường job. Trong Jenkins, có thể dùng biến env của Pipeline và truyền vào lệnh sh/bat. Hãy đọc tài liệu nền tảng để biết biến nào có sẵn ở stage/job/step cụ thể.

### 6.2. Trả kết quả từ shell về bộ máy CI

Nếu script tính ra một giá trị mà job hoặc step sau cần dùng, hãy xuất kết quả theo giao thức của nền tảng:

| Nền tảng | Cơ chế thường dùng |
| --- | --- |
| GitHub Actions | Ghi name=value vào file được chỉ định bởi GITHUB_OUTPUT, sau đó khai báo output của step/job |
| GitLab CI/CD | Dùng dotenv report artifact để chuyển biến cho job ở stage sau theo quy tắc phụ thuộc |
| Jenkins | Gán biến Pipeline, dùng returnStdout hoặc cơ chế stash/artifact tùy loại dữ liệu |
| Azure Pipelines | Ghi logging command ##vso[task.setvariable ...] vào stdout theo cú pháp Azure |

Ví dụ GitHub Actions:

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

Shell tạo ra giá trị và ghi vào file output do GitHub cung cấp. GitHub Actions đọc file đó, công bố output của step, rồi biểu thức ở step sau tham chiếu output. Đây là một hợp đồng trao đổi dữ liệu rõ ràng giữa hai lớp.

Không nên giả định một biến shell được export trong step này sẽ tự tồn tại ở step khác. Mỗi step thường chạy trong tiến trình riêng; cơ chế chia sẻ cần được khai báo rõ.

## 7. Phân biệt trạng thái skipped, success và failure

Điều kiện sai ở cấp nền tảng và lệnh shell trả mã lỗi tạo ra kết quả khác nhau:

| Tình huống | Kết quả thường thấy | Ý nghĩa |
| --- | --- | --- |
| Điều kiện platform không thỏa | Job/step bị skipped hoặc không được thêm vào pipeline | Bộ máy CI quyết định không thực thi |
| Điều kiện shell chọn nhánh không làm gì và script kết thúc mã 0 | Step thành công | Tiến trình đã chạy và kết thúc bình thường |
| Lệnh shell trả mã khác 0 | Step thất bại, trừ khi có chính sách xử lý lỗi | Tiến trình đã chạy nhưng báo lỗi |
| Platform condition dùng hàm trạng thái đặc biệt | Có thể chạy khi trước đó thất bại hoặc bị hủy | Cần hiểu rõ semantics của nền tảng |

Ví dụ, script sau không làm step thất bại khi biến bị tắt:

~~~bash
if [[ "$DEPLOY_ENABLED" == "true" ]]; then
  ./scripts/deploy.sh staging
else
  echo "Bỏ qua triển khai"
fi
~~~

Đây là lựa chọn hợp lệ nếu mục tiêu là một job đã chạy nhưng không cần triển khai. Tuy nhiên, dashboard sẽ thể hiện step thành công, không phải skipped. Nếu cần trạng thái skipped để báo cáo chính xác rằng bước triển khai không được áp dụng, hãy biểu diễn điều kiện ở lớp nền tảng.

Ngược lại, nếu script phát hiện cấu hình bắt buộc bị thiếu, nên trả lỗi:

~~~bash
if [[ -z "${DEPLOY_ENV:-}" ]]; then
  echo "Thiếu DEPLOY_ENV" >&2
  exit 1
fi
~~~

Không nên biến một lỗi cấu hình thành thành công bằng cách chỉ in cảnh báo rồi tiếp tục. Bộ máy CI chỉ có thể phản ánh đúng kết quả khi tiến trình trả exit code phù hợp.

## 8. Bảo mật khi đưa dữ liệu vào shell

Ranh giới giữa biểu thức nền tảng và shell cũng là ranh giới quan trọng về bảo mật. Dữ liệu từ tên nhánh, tiêu đề PR, commit message, input người dùng hoặc hệ thống bên ngoài có thể chứa ký tự đặc biệt. Nếu chèn trực tiếp dữ liệu đó vào nội dung script, ký tự có thể bị shell diễn giải như cú pháp.

### 8.1. Tránh nội suy dữ liệu không tin cậy trực tiếp vào script

Ví dụ không an toàn trong GitHub Actions:

~~~yaml
- name: Print pull request title
  run: echo "${{ github.event.pull_request.title }}"
~~~

Biểu thức context được mở rộng trước khi shell thực thi. Nếu tiêu đề PR chứa dấu nháy, dấu chấm phẩy hoặc cú pháp shell, nội dung được chèn có thể làm thay đổi câu lệnh. Đây là một dạng command injection.

Cách an toàn hơn là truyền giá trị qua biến môi trường và trích dẫn khi sử dụng:

~~~yaml
- name: Print pull request title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$PR_TITLE"
~~~

Ở đây, tiêu đề PR là dữ liệu môi trường; shell không phân tích lại nội dung của biến như một phần mã nguồn. Dùng printf với format cố định và trích dẫn "$PR_TITLE" giúp giữ nguyên giá trị. Không dùng eval hoặc ghép dữ liệu không tin cậy thành lệnh.

### 8.2. Không để shell mở rộng biến ngoài ý muốn

Với Bash, nên trích dẫn biến khi truyền đối số:

~~~bash
./scripts/deploy.sh "$DEPLOY_ENV"
~~~

Nếu bỏ dấu nháy:

~~~bash
./scripts/deploy.sh $DEPLOY_ENV
~~~

shell có thể thực hiện word splitting và pathname expansion. Một giá trị chứa khoảng trắng hoặc ký tự wildcard có thể bị tách thành nhiều đối số hoặc khớp file ngoài dự kiến.

Ngoài ra:

- Không in secret ra log, kể cả khi đang debug.
- Không truyền secret qua tham số dòng lệnh nếu có nguy cơ bị lộ trong danh sách process hoặc log.
- Dùng secret store/secret context và quyền tối thiểu.
- Không cấp secret production cho pipeline chạy mã không đáng tin cậy, chẳng hạn job từ fork nếu chính sách không cho phép.
- Tránh ghép chuỗi từ dữ liệu đầu vào để tạo câu lệnh; truyền dữ liệu như argument hoặc environment variable.
- Kiểm tra quyền của script và dependency trước khi cho phép pipeline thực thi.

Truyền qua environment giúp tránh lỗi nội suy script phổ biến, nhưng không tự động biến dữ liệu thành an toàn. Script vẫn phải xác thực giá trị, trích dẫn đúng và tránh đưa dữ liệu vào eval, SQL hoặc các ngữ cảnh có quy tắc escape riêng.

## 9. Những lỗi nhầm lẫn thường gặp

| Cách viết hoặc suy nghĩ sai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Viết cú pháp Bash trong rules:if của GitLab | GitLab đang phân tích DSL của rules, chưa chạy shell | Dùng toán tử và biến đúng cú pháp GitLab |
| Dùng github.ref trực tiếp trong Bash | Đây là context của GitHub Actions, không phải biến môi trường mặc định | Truyền qua env, ví dụ REF: ${{ github.ref }} |
| Dùng $VAR trong mọi loại condition | Mỗi nền tảng có quy tắc biến và giai đoạn mở rộng riêng | Xác định DSL và context của thuộc tính đang viết |
| Nghĩ shell if có thể skip một job | Shell chỉ điều khiển tiến trình đã được chạy | Đặt điều kiện ở job/stage/step của nền tảng |
| Nghĩ condition sai luôn làm pipeline đỏ | Điều kiện không thỏa thường dẫn đến skipped | Phân biệt skipped với failure trong báo cáo |
| Dùng && giống nhau ở mọi nơi | && có ý nghĩa khác hoặc không hợp lệ trong từng DSL | Tra cú pháp biểu thức của nền tảng |
| Viết Bash nhưng chạy bằng PowerShell | Shell không hiểu cú pháp của ngôn ngữ kia | Chọn shell rõ ràng hoặc viết script đúng hệ điều hành |
| Cho rằng biến export trong step trước tồn tại ở step sau | Step thường là tiến trình độc lập | Dùng output, artifact hoặc cơ chế biến của nền tảng |
| Nội suy tiêu đề PR trực tiếp vào script | Dữ liệu có thể biến thành cú pháp shell | Truyền qua environment và trích dẫn đúng |
| Cho rằng job có if là đủ bảo vệ môi trường production | Điều kiện chạy không thay thế quyền truy cập, approval và bảo vệ secret | Kết hợp environment protection, quyền tối thiểu và phê duyệt |

## 10. Cách đọc và viết một step không bị lẫn ngữ cảnh

Khi đọc một đoạn pipeline, hãy đặt lần lượt các câu hỏi sau:

1. **Đây là key YAML hay nội dung script?** Xác định indentation và key cha như if, condition, script, run, bash hoặc sh.
2. **Ai diễn giải biểu thức này?** Là GitHub Actions, GitLab, Jenkins, Azure Pipelines hay Bash/PowerShell?
3. **Biểu thức được đánh giá khi nào?** Lúc tạo pipeline, trước stage/job/step hay sau khi tiến trình shell bắt đầu?
4. **Dữ liệu đến từ đâu?** Context của nền tảng, biến pipeline, environment, file, artifact hay output của bước trước?
5. **Kết quả được truyền đi bằng cách nào?** Trạng thái job, exit code, output, artifact, biến môi trường hay log?
6. **Điều gì xảy ra nếu điều kiện sai hoặc lệnh lỗi?** Bị skipped, tiếp tục, retry, allowed failure hay failure?
7. **Có dữ liệu không tin cậy đi vào script không?** Nếu có, kiểm tra cách truyền, quoting và xác thực.

Quy trình này giúp xác định đúng nơi đặt logic. Điều kiện liên quan đến nhánh, sự kiện, dependency, phê duyệt và trạng thái pipeline thường thuộc nền tảng. Điều kiện liên quan đến file trên runner, kết quả của lệnh, nội dung workspace hoặc thao tác cục bộ thường thuộc script. Nếu một kiểm tra shell thực sự là cổng phát hành, hãy cân nhắc biến nó thành một job/step có trạng thái rõ ràng để các bước phụ thuộc có thể điều phối chính xác.

## 11. Ví dụ tổng hợp: kiểm thử mọi PR, chỉ triển khai từ main

Một pipeline cơ bản cần đáp ứng hai yêu cầu:

- Mọi PR đều chạy kiểm tra tự động.
- Chỉ push lên main mới tạo job triển khai staging.

Với GitHub Actions:

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

Hãy đọc theo hai lớp:

- on xác định sự kiện có thể tạo workflow.
- needs và if điều phối job triển khai sau job test và giới hạn job vào push trên main.
- environment: staging liên kết job với môi trường đã cấu hình trên GitHub, nơi có thể áp dụng protection rule hoặc approval.
- run khởi chạy Bash trên runner.
- set -euo pipefail và các lệnh trong script điều khiển lỗi ở cấp tiến trình.
- DEPLOY_ENV được truyền qua env; script đọc nó như dữ liệu.

Trong ví dụ này, test chạy cho cả PR và push main. Job triển khai phụ thuộc kết quả test thành công. Khi chuyển sang nền tảng khác, giữ nguyên ý định nhưng chuyển on, needs, if, environment và cách truyền output sang cấu trúc tương ứng của nền tảng đó.

## 12. Checklist trước khi đưa pipeline vào sử dụng

**Về cấu hình và điều kiện nền tảng**

- [ ] Trigger và filter nhánh/tag đúng với yêu cầu.
- [ ] Điều kiện job/stage/step dùng đúng DSL của nền tảng.
- [ ] Dependency và trạng thái thành công/thất bại được khai báo rõ.
- [ ] Trạng thái skipped, allowed failure và failure có ý nghĩa đúng trong báo cáo.
- [ ] Phê duyệt môi trường và quyền triển khai được cấu hình ở nơi phù hợp.

**Về shell và runner**

- [ ] Shell hoặc chương trình thực thi đã được xác định.
- [ ] Script dùng đúng cú pháp cho Linux/Windows và image/agent có đủ công cụ.
- [ ] Exit code phản ánh đúng thành công hoặc thất bại.
- [ ] Script không phụ thuộc ngầm vào working directory hoặc biến chưa được truyền.
- [ ] Output giữa các step/job được chia sẻ qua cơ chế chính thức.

**Về dữ liệu và bảo mật**

- [ ] Context của nền tảng được truyền vào script một cách có kiểm soát.
- [ ] Dữ liệu đầu vào không tin cậy không được nội suy trực tiếp thành mã shell.
- [ ] Biến shell được trích dẫn và xác thực phù hợp.
- [ ] Secret không bị in ra log hoặc cấp cho job không đáng tin cậy.
- [ ] Quyền của token và runner chỉ đủ cho công việc cần làm.

## Kết luận

Điều kiện của nền tảng và lệnh shell là hai lớp bổ sung cho nhau trong Pipeline as Code. DSL của nền tảng điều phối trigger, job, stage, dependency, trạng thái và môi trường. Shell trên runner thực hiện lệnh, kiểm tra tài nguyên cục bộ và trả exit code hoặc output. Từ khóa giống nhau như if không có nghĩa là cùng ngôn ngữ hoặc cùng thời điểm thực thi.

Khi viết pipeline, hãy xác định ai diễn giải từng biểu thức, nó được đánh giá ở giai đoạn nào và dữ liệu đi qua ranh giới bằng cách nào. Đặt logic điều phối ở cấu hình nền tảng, đặt thao tác cục bộ trong script, truyền dữ liệu qua output/environment có kiểm soát và giữ exit code trung thực. Cách làm này tạo pipeline dễ đọc, có thể truy vết và an toàn hơn khi tự động hóa build, kiểm thử và phát hành.
