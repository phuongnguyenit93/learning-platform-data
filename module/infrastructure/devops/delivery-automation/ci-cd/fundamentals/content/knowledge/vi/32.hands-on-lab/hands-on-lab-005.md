# Thêm cổng chất lượng và kiểm tra quyền theo mức tin cậy nguồn

Trong bài thực hành này, bạn sẽ bổ sung một cổng chất lượng vào CI/CD và thiết kế quyền thực thi theo mức độ tin cậy của nguồn kích hoạt pipeline. Mục tiêu là để mọi thay đổi được kiểm tra tự động, trong khi mã đến từ pull request hoặc fork không thể dùng quyền publish, deploy hay secret production.

Bạn sẽ xây dựng hai lớp kiểm soát:

1. **Quality gate:** chỉ cho phép pipeline tiếp tục khi các kiểm tra bắt buộc đạt.
2. **Trust gate:** chỉ cấp quyền cao hơn cho sự kiện và ref đã được tổ chức bảo vệ, chẳng hạn push vào protected branch sau review.

Một pipeline xanh không tự chứng minh nguồn mã đáng tin cậy. Một commit từ nhánh nội bộ cũng không mặc nhiên được quyền deploy production. Quyết định quyền phải dựa trên event, repository, ref, protection policy, approval và mục tiêu của job.

Đây là bài thực hành thuộc **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường và cổng chất lượng.

## 1. Kết quả cần đạt

Sau bài lab, bạn có thể:

- Phân loại nguồn kích hoạt pipeline theo mức độ tin cậy.
- Xác định quality gate bắt buộc trước khi merge hoặc phát hành.
- Tách job kiểm thử mã chưa tin cậy khỏi job publish/deploy.
- Cấp quyền tối thiểu cho từng job thay vì dùng một token quyền rộng cho toàn workflow.
- Chặn release khi bất kỳ quality check bắt buộc nào thất bại.
- Kiểm chứng bằng một tình huống PR không tin cậy và một tình huống push vào protected branch.
- Giải thích rủi ro của pull_request_target, self-hosted runner và cache dùng chung.

## 2. Bối cảnh và kiến trúc lab

Giả sử repository sample-service có pipeline GitHub Actions. Dịch vụ có các kiểm tra lint/format, unit và component test, coverage threshold, dependency vulnerability/license audit, secret scanning và build artifact. Sau khi merge vào main đã được bảo vệ, pipeline có thể publish artifact. Production deployment có environment approval và workload identity nếu nền tảng hỗ trợ.

Luồng mong muốn:

~~~mermaid
flowchart TD
    A["Pull request / fork"] --> B["Quality gate<br/>read-only token"]
    B --> C{"Tất cả kiểm tra đạt?"}
    C -- "Không" --> X["Fail checks<br/>không publish/deploy"]
    C -- "Có" --> R["Review và branch protection"]
    R --> M["Merge vào protected main"]
    M --> Q["Quality gate chạy lại trên main"]
    Q --> D{"Quality gate đạt?"}
    D -- "Không" --> X
    D -- "Có" --> P["Build và publish<br/>quyền package giới hạn"]
    P --> E["Protected production environment"]
    E --> A2["Approval + deploy identity"]
    A2 --> V["Smoke test và xác minh sau deploy"]
~~~

PR từ fork có thể chạy mã do contributor cung cấp. Vì vậy, job kiểm thử PR phải được xem là đang thực thi mã chưa tin cậy, kể cả khi PR nằm trong repository của tổ chức. Job này chỉ nhận quyền cần thiết để đọc source và chạy test; không nhận secret production, quyền publish hoặc quyền deploy.

Sau khi thay đổi được review và merge vào protected branch, pipeline có thể thực hiện các bước phát hành với quyền riêng, giới hạn theo đúng job.

## 3. Chuẩn bị repository

Tạo hoặc xác nhận cấu trúc tương tự:

~~~text
sample-service/
├── .github/
│   └── workflows/
│       └── ci.yml
├── scripts/
│   └── ci/
│       ├── lint.sh
│       ├── test.sh
│       ├── coverage-check.sh
│       ├── dependency-audit.sh
│       ├── secret-scan.sh
│       ├── quality-gate.sh
│       ├── build-release.sh
│       └── publish.sh
├── src/
├── tests/
└── README.md
~~~

Các script là điểm tích hợp với toolchain của dự án. Thay lệnh minh họa bằng formatter, compiler, test runner, coverage tool, dependency scanner và secret scanner đang được nhóm sử dụng.

Trước khi bắt đầu:

- Bạn có quyền tạo branch và pull request.
- Repository có branch chính main.
- Có thể chạy các kiểm tra tương đương trên máy local hoặc runner.
- Biết script nào cần dependency riêng và script nào không cần secret.
- Có registry/package destination thử nghiệm nếu muốn thực hiện phần publish.

Không dùng credential production trong bài lab. Nếu chưa có registry thử nghiệm, dùng chế độ dry-run cho bước publish.

## 4. Phân loại nguồn theo mức độ tin cậy

Lập bảng quyền trước khi viết YAML:

| Nguồn/event | Mức tin cậy mặc định | Quyền phù hợp | Không cấp |
| --- | --- | --- | --- |
| PR từ fork | Chưa tin cậy | Đọc source, chạy quality checks trên runner cô lập | Secret, publish, deploy, quyền ghi repository |
| PR từ branch nội bộ | Chưa được phép phát hành | Quality checks, token đọc | Secret production, publish/deploy |
| Push vào protected main sau merge | Đã qua review theo branch policy | Build và publish artifact với quyền hẹp | Quyền quản trị organization hoặc cloud rộng |
| Protected release tag | Tin cậy theo policy phát hành | Ký/publish/deploy nếu đã xác minh tag và approval | Credential dài hạn không cần thiết |
| Manual workflow dispatch | Phụ thuộc actor, ref và approval | Chỉ quyền phù hợp với ref được bảo vệ và người khởi chạy | Mặc định coi mọi lần chạy thủ công là trusted |
| Scheduled scan | Nguồn workflow đã kiểm soát | Đọc source, scan và tạo report | Quyền deploy nếu không có mục đích rõ |

**Internal không đồng nghĩa trusted.** Một PR nội bộ vẫn có thể chứa mã chưa review. Chỉ nâng quyền phát hành sau khi thay đổi được merge vào protected branch/tag và đáp ứng policy.

### 4.1. Trust policy của lab

- PR event chỉ chạy job quality gate.
- Workflow mặc định chỉ có contents: read.
- Không truyền secret vào job chạy mã PR.
- Publish chỉ chạy khi event là push vào main và repository đúng là repository chính thức.
- Publish phải phụ thuộc quality gate thành công.
- Deploy production chỉ chạy qua protected environment và approval.
- Quyền OIDC chỉ cấp cho job thực sự cần danh tính cloud.

Không dựa riêng vào tên branch do người dùng chọn. Kiểm tra cả event type, repository identity và ref.

## 5. Xây dựng quality gate

Một quality gate tốt có các kiểm tra bắt buộc và kết quả pass/fail rõ ràng. Giữ từng bước riêng để biết điều kiện nào thất bại.

### 5.1. Xác định tiêu chí pass/fail

| Kiểm tra | Điều kiện đạt | Điều kiện chặn |
| --- | --- | --- |
| Lint/format | Không có lỗi theo cấu hình dự án | Có lỗi lint hoặc format |
| Unit/component tests | Tất cả test bắt buộc pass | Có test fail |
| Coverage | Đạt ngưỡng đã thống nhất cho phạm vi được đo | Dưới ngưỡng hoặc report thiếu |
| Dependency audit | Không có lỗ hổng vượt policy; license được phép | Có finding bị policy cấm |
| Secret scan | Không phát hiện secret hợp lệ trong thay đổi | Phát hiện credential chưa được xử lý |
| Build | Tạo được artifact từ source revision hiện tại | Build thất bại hoặc artifact không xác định |

Coverage threshold cần dựa trên baseline và mức độ quan trọng của code. Không tăng coverage bằng test assertion rỗng hoặc loại bỏ file khó kiểm tra khỏi report mà không có review.

Dependency audit nên phân biệt finding mới và finding đã được chấp nhận có thời hạn. Exception cần owner, lý do, phạm vi và ngày hết hạn; không tạo allowlist vĩnh viễn để làm pipeline xanh.

Secret scanner có thể phát hiện chuỗi giống credential nhưng không phải secret thật. Finding cần được xác minh; nếu credential đã lộ, revoke/rotate trước khi xử lý exception có căn cứ.

### 5.2. Tạo script điều phối quality gate

Tạo scripts/ci/quality-gate.sh:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

echo "== Lint and format =="
./scripts/ci/lint.sh

echo "== Tests =="
./scripts/ci/test.sh

echo "== Coverage =="
./scripts/ci/coverage-check.sh

echo "== Dependency audit =="
./scripts/ci/dependency-audit.sh

echo "== Secret scan =="
./scripts/ci/secret-scan.sh

echo "Quality gate passed"
~~~

set -e làm script dừng khi một lệnh thất bại; -u báo lỗi khi dùng biến chưa khai báo; pipefail giúp pipeline shell thất bại nếu một lệnh trong pipe thất bại. Mỗi script con phải trả exit code khác 0 khi policy không đạt.

Nếu cần thu thập tất cả kết quả thay vì dừng ở lỗi đầu tiên, hãy dùng cơ chế tổng hợp exit status rõ ràng và vẫn trả code thất bại ở cuối. Không nuốt lỗi bằng || true cho kiểm tra bắt buộc.

### 5.3. Kiểm tra local

~~~bash
chmod +x scripts/ci/*.sh
./scripts/ci/quality-gate.sh
~~~

Nếu dự án dùng PowerShell hoặc runner Windows, tạo script tương đương và bảo đảm exit code được truyền về CI. Mục tiêu là cùng một policy có thể chạy local và trên runner.

## 6. Tạo workflow với quyền mặc định chỉ đọc

Ví dụ sau dùng GitHub Actions. Các action bên thứ ba cần được pin bằng full commit SHA đã xác minh. Chuỗi <VERIFIED_40_HEX_SHA> là placeholder, không phải giá trị có thể chạy.

Tạo .github/workflows/ci.yml:

~~~yaml
name: CI quality and release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  quality-gate:
    name: Required quality gate
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout source
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Run required checks
        shell: bash
        run: ./scripts/ci/quality-gate.sh

  publish:
    name: Publish trusted artifact
    needs: quality-gate
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      github.repository == 'ORG/REPOSITORY'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout trusted source
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Build release artifact
        shell: bash
        run: ./scripts/ci/build-release.sh

      - name: Publish artifact
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: ./scripts/ci/publish.sh
~~~

Thay ORG/REPOSITORY bằng tên đầy đủ của repository chính thức. Thay placeholder SHA bằng full commit SHA đã xác minh của action checkout. Trong workflow thật, thay ${{ github.token }} bằng expression chuẩn của GitHub Actions để cung cấp token ngắn hạn. Không ghi token thật vào YAML hoặc log.

Nếu không dùng GitHub Packages, điều chỉnh packages: write và publish script theo registry đích, chỉ cấp quyền thật sự cần. Nếu publish script không cần GitHub API token, bỏ biến GH_TOKEN và quyền không cần thiết.

### 6.1. Vì sao workflow được chia như vậy?

- Workflow mặc định chỉ có contents: read.
- quality-gate chỉ đọc source và chạy test; không cần publish token.
- persist-credentials: false tránh để checkout lưu credential Git trong cấu hình repository cho các lệnh sau.
- publish phụ thuộc quality-gate bằng needs, nên quality gate fail thì publish không chạy.
- Điều kiện if yêu cầu push vào main và đúng repository chính thức.
- Chỉ job publish có packages: write.
- PR từ fork hoặc branch nội bộ chưa merge không đáp ứng điều kiện publish.

Điều kiện này minh họa luồng publish sau merge. Nếu release được kích hoạt bằng tag, hãy định nghĩa riêng quy tắc xác minh tag được bảo vệ và approval; không mở rộng thành mọi tag.

## 7. Bổ sung deploy gate cho production

Publish artifact và deploy production là hai hành động khác nhau. Artifact có thể được publish sau quality gate, nhưng production deployment cần điều kiện riêng.

~~~yaml
  deploy-production:
    name: Deploy production
    needs: publish
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      github.repository == 'ORG/REPOSITORY'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout deployment scripts
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Deploy using workload identity
        shell: bash
        run: ./scripts/ci/deploy-production.sh
~~~

Trong repository settings, cấu hình environment production với required reviewers, branch/tag restrictions và protection rules phù hợp. id-token: write chỉ cấp cho job cần OIDC token để xác thực với cloud provider; trust policy phía cloud phải giới hạn đúng repository, branch/environment và audience.

Nếu chưa cấu hình OIDC, không thêm cloud access key dài hạn vào PR workflow. Có thể dừng lab ở bước publish dry-run và mô tả deploy gate như phần mở rộng.

## 8. Không dùng pull_request_target để chạy mã PR không tin cậy

pull_request_target chạy workflow trong ngữ cảnh repository đích và có thể có quyền/token/secret cao hơn workflow PR thông thường. Mẫu nguy hiểm:

1. Workflow được kích hoạt bằng pull_request_target.
2. Workflow checkout commit head của PR từ contributor.
3. Workflow chạy script từ checkout đó.
4. Script không tin cậy có thể đọc token hoặc secret mà workflow nhận được.

Với bài lab này, dùng pull_request cho quality checks và không cấp secret. Nếu cần tự động gắn label hoặc phản hồi PR bằng pull_request_target, chỉ chạy logic đã tin cậy từ base branch; không checkout rồi thực thi mã từ head của PR.

Mã PR vẫn là mã không tin cậy dù workflow dùng pull_request. Hãy chạy trên hosted runner cô lập hoặc runner ephemeral được thiết kế cho workload không tin cậy. Không dùng self-hosted runner có quyền truy cập mạng nội bộ, credential hoặc workspace dùng chung cho PR từ fork.

## 9. Cấu hình branch protection

Workflow tạo check; branch protection mới ngăn merge khi required check chưa đạt.

Trong repository settings, cấu hình branch rule hoặc ruleset cho main:

- Yêu cầu pull request trước khi merge.
- Yêu cầu số review phù hợp.
- Bật required status check tương ứng với job Required quality gate.
- Yêu cầu branch cập nhật với base branch nếu policy cần.
- Hạn chế ai được bypass rule.
- Bảo vệ quyền push trực tiếp vào main.
- Đặt mặc định GITHUB_TOKEN của repository/organization ở mức read-only nếu nền tảng hỗ trợ.
- Dùng CODEOWNERS và yêu cầu owner review cho .github/workflows/**, scripts/ci/**, reusable workflows và policy nhạy cảm.

Workflow và script CI là một phần của ranh giới bảo mật. Một PR có thể sửa chính file workflow để thay đổi permission hoặc điều kiện job; vì vậy, thay đổi các file này cần review theo quyền sở hữu riêng và không nên được merge chỉ dựa trên kết quả của workflow do chính PR sửa đổi.

Tên check hiển thị có thể gồm tên workflow/job hoặc context tùy nền tảng. Chọn đúng check thực tế từ một lần chạy; tránh chọn check cũ hoặc check không còn được cập nhật.

Nếu workflow không chạy do path/event filter, required check có thể ở trạng thái pending. Hãy thiết kế trigger sao cho mọi PR cần policy đều tạo ra required check; không để một đường đi bỏ qua gate.

## 10. Thử nghiệm nguồn không tin cậy

Tạo một branch hoặc PR thử nghiệm từ fork nếu repository hỗ trợ. Xác minh:

1. Workflow pull_request được kích hoạt.
2. Job quality-gate chạy trên runner phù hợp.
3. Token của job chỉ có quyền đọc source.
4. Không có secret production hoặc package write permission trong job.
5. Job publish bị skip vì event không phải push vào protected main.
6. Job deploy-production không chạy.
7. Nếu quality gate fail, required check báo fail và branch protection chặn merge.

Không đưa payload nhằm lấy secret vào PR để thử cơ chế bảo vệ. Có thể kiểm tra cấu hình quyền qua workflow permissions, run metadata và repository settings; không cần thực thi mã độc để chứng minh job không có quyền.

Nếu không có fork riêng, tạo branch PR nội bộ và kiểm tra cùng chính sách. Kết quả vẫn phải cho thấy PR chưa merge không có quyền publish/deploy.

## 11. Thử nghiệm nguồn đã được bảo vệ

Sau khi PR hợp lệ được review và merge vào main:

1. Xác minh branch protection đã áp dụng.
2. Workflow chạy theo event push trên main.
3. quality-gate chạy lại trên commit đã merge.
4. Nếu gate đạt, publish mới được thực thi.
5. Kiểm tra job publish có đúng permission cần thiết.
6. Nếu deploy gate được cấu hình, xác minh environment yêu cầu approval.
7. Xác minh artifact được tạo từ đúng commit và có version/digest truy vết được.

Không giả định merge đồng nghĩa artifact đã được publish hoặc deploy. Mỗi job phải có trạng thái và bằng chứng riêng.

## 12. Thử nghiệm quality gate thất bại

Trên một branch thử nghiệm, tạo một lỗi có kiểm soát:

- Làm một unit test thất bại.
- Hoặc tạo lỗi lint có thể sửa lại.
- Hoặc hạ coverage xuống dưới ngưỡng đã định trong một thay đổi thử nghiệm.

Mở PR và quan sát:

- quality-gate trả exit code khác 0.
- Check bắt buộc chuyển sang fail.
- publish không chạy do needs: quality-gate không đạt.
- deploy-production không chạy.
- Log chỉ rõ bước kiểm tra thất bại.

Sau đó sửa lỗi, push lại và xác minh gate có thể pass. Không tắt required check để làm PR merge được.

## 13. Bảng quyền mong đợi

| Job | PR từ fork | PR nội bộ | Push protected main |
| --- | --- | --- | --- |
| Quality gate | Chạy, read-only | Chạy, read-only | Chạy, read-only |
| Build test artifact tạm | Có thể chạy | Có thể chạy | Có thể chạy |
| Publish package | Không | Không | Chỉ sau quality gate, quyền package hẹp |
| Deploy staging | Không mặc định | Không mặc định | Theo policy riêng |
| Deploy production | Không | Không | Protected environment + approval |
| OIDC cloud identity | Không | Không | Chỉ job deploy cần dùng |
| Production secret | Không | Không | Chỉ cấp cho job/environment thực sự cần |

Đây là policy mục tiêu của lab. Nếu tổ chức có release tag, manual dispatch hoặc môi trường staging riêng, bổ sung điều kiện tương ứng; không suy rộng quyền từ một trường hợp sang mọi event.

## 14. Các lỗi thường gặp

| Lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Cấp quyền ghi ở workflow level | Mọi job có thể nhận quyền vượt nhu cầu | Đặt quyền mặc định read-only và cấp riêng từng job |
| PR job nhận secret | Mã PR có thể làm lộ credential | Không cấp secret cho untrusted PR |
| Dùng pull_request_target rồi chạy PR head | Thực thi mã không tin cậy trong context đặc quyền | Dùng pull_request; nếu dùng target, chỉ chạy base code tin cậy |
| Publish job không phụ thuộc quality gate | Artifact có thể được publish dù test fail | Dùng needs và điều kiện source trust |
| Chỉ kiểm tra branch name | Fork cũng có thể có branch cùng tên | Kiểm tra event, repository identity và ref |
| Coi PR nội bộ là trusted | Mã chưa review có thể lấy quyền cao | Chỉ nâng trust sau merge vào protected ref |
| Dùng self-hosted runner chung cho fork | PR có thể truy cập tài nguyên còn sót lại hoặc mạng nội bộ | Hosted/ephemeral runner và cô lập workload |
| Cache chia sẻ giữa nguồn không tin cậy và release | Có thể bị poisoning hoặc làm lộ dữ liệu | Tách cache scope theo trust boundary |
| Không cấu hình branch protection | Check fail nhưng vẫn có thể merge | Đặt quality check thành required status check |
| Token có quyền rộng hoặc sống lâu | Tăng phạm vi thiệt hại khi bị lộ | Token ngắn hạn, scope hẹp, OIDC |
| Bỏ qua lỗi bằng || true | Gate luôn xanh dù kiểm tra thất bại | Trả exit code đúng và xử lý exception có audit |

## 15. Checklist nghiệm thu lab

**Quality gate**

- [ ] Có script điều phối lint, test, coverage, dependency audit và secret scan.
- [ ] Mỗi kiểm tra bắt buộc trả exit code đúng.
- [ ] Gate thất bại khi một kiểm tra bắt buộc fail.
- [ ] Required status check được cấu hình cho main.

**Source trust và permissions**

- [ ] PR từ fork chạy với quyền đọc tối thiểu.
- [ ] PR nội bộ chưa merge cũng không có quyền publish/deploy.
- [ ] Publish chỉ chạy trên repository chính thức và protected main theo điều kiện đã định.
- [ ] Publish job có quyền package write đúng phạm vi.
- [ ] Deploy job dùng protected environment và approval.
- [ ] OIDC chỉ được cấp cho job cần workload identity.

**Bảo vệ runner và secret**

- [ ] Không truyền production secret vào PR workflow.
- [ ] Không checkout và thực thi PR head trong pull_request_target.
- [ ] PR không tin cậy chạy trên runner cô lập.
- [ ] Cache không tạo đường ghi từ untrusted job sang trusted release job.
- [ ] Action bên thứ ba được pin bằng full SHA đã xác minh.

**Bằng chứng**

- [ ] Đã thử một PR không tin cậy và xác minh publish/deploy bị skip.
- [ ] Đã thử một quality gate fail và xác minh downstream bị chặn.
- [ ] Đã thử một push vào protected main sau review.
- [ ] Artifact có commit, pipeline run và digest truy vết được.
- [ ] Có log/report cho biết gate nào pass hoặc fail.

## 16. Báo cáo kết quả thực hành

Sau khi hoàn thành, ghi lại:

| Nội dung | Kết quả cần ghi |
| --- | --- |
| Repository và branch rule | Tên repository, protected branch và required check |
| Quality gate | Danh sách checks, ngưỡng coverage và policy audit |
| Untrusted PR | Job được chạy, quyền token, publish/deploy có bị skip không |
| Trusted main push | Commit, pipeline run, artifact version/digest |
| Negative test | Gate nào được cố ý làm fail và downstream phản ứng ra sao |
| Production gate | Environment approval và workload identity nếu đã cấu hình |
| Ngoại lệ | Lý do, owner, phạm vi và ngày hết hạn |

Kết quả mong đợi là một PR chưa merge có thể được kiểm tra nhưng không thể phát hành; một commit đã merge vào protected branch chỉ được publish sau khi quality gate đạt; production deploy cần điều kiện và approval riêng.

## Kết luận

Quality gate và trust gate giải quyết hai câu hỏi khác nhau: thay đổi có đạt tiêu chuẩn kỹ thuật không, và nguồn/event hiện tại có được phép thực hiện hành động nào. Pipeline an toàn cần cả hai. Hãy kiểm tra mã PR với quyền tối thiểu, tách publish/deploy thành job riêng, yêu cầu quality gate thành công, xác minh repository/ref/event và bảo vệ production bằng approval cùng danh tính workload.

Hoàn thành bài lab khi bạn chứng minh được ba tình huống: PR không tin cậy chỉ chạy kiểm tra; quality gate thất bại chặn publish/deploy; push đã được review vào protected branch mới có thể đi tiếp theo đúng quyền được cấp. Những bằng chứng này giúp nhóm kiểm soát cả chất lượng mã lẫn ranh giới tin cậy của pipeline.
