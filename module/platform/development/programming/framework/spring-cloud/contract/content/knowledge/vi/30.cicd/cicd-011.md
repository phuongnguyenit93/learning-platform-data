# Ngăn thay đổi không tin cậy trong DSL chạy bằng mã tùy ý

## Mục tiêu học tập

**Spring Cloud Contract** hỗ trợ kiểm thử hợp đồng giữa **producer** và **consumer**: các tương tác HTTP hoặc messaging được mô tả bằng **Groovy/YAML DSL**, plugin sinh test phía producer, đóng gói stub để consumer dùng **Stub Runner**, rồi đưa các bước kiểm chứng vào **CI/CD** nhằm phát hiện thay đổi API không tương thích.

Tuy nhiên, **Groovy DSL là mã Groovy có thể thực thi**, không chỉ là một tệp dữ liệu. Nếu một pull request (PR), một repository hợp đồng bên ngoài hoặc một artifact không đáng tin được phép cung cấp Groovy contract cho plugin, quá trình sinh test có thể trở thành **điểm chạy mã của bên gửi thay đổi**. Mối nguy đặc biệt nghiêm trọng khi CI đồng thời có token, quyền ghi artifact repository, quyền triển khai hoặc kết nối đến hạ tầng nội bộ.

Bài thuộc chương **CI/CD**, tập trung vào **ngăn thay đổi không tin cậy trong DSL chạy bằng mã tùy ý**. Sau bài học, bạn sẽ:

- Giải thích vì sao **đọc/biên dịch/thực thi Groovy DSL** khác với đọc một YAML khai báo.
- Xác định ranh giới tin cậy giữa PR từ fork, branch nội bộ, common contract repository, contract JAR, pipeline kiểm chứng và pipeline phát hành.
- Hiểu những gì kẻ gửi PR có thể nhắm tới: secrets, credentials, network nội bộ, workspace, artifact hoặc kết quả build.
- Đặt kiểm tra tĩnh và review **trước khi** thực thi DSL chưa được phê duyệt.
- Thiết kế job chạy code chưa tin cậy với **runner cô lập, không có secrets, quyền tối thiểu, egress bị hạn chế**.
- Tránh các lỗi cấu hình CI như chạy PR code với `pull_request_target`, dùng runner tự quản đặc quyền hoặc truyền PR title trực tiếp vào shell.
- Bảo vệ nguồn contract từ Git/JAR bằng version/digest, quyền repository, quy tắc review và provenance.
- Giữ **producer contract verification**, **stub publication** và **consumer Stub Runner tests** trong các tầng quyền khác nhau.
- Lập phương án phản ứng khi phát hiện DSL khả nghi hoặc artifact có nguồn gốc không xác minh được.

> **Nguyên tắc bảo mật:** không bao giờ coi một tệp `*.groovy`, vì nằm trong thư mục `contracts` hoặc “trông giống DSL”, là dữ liệu an toàn. Một pipeline chỉ được thực thi nó khi ranh giới tin cậy và mức cô lập phù hợp đã được xác lập.

## 1. Bài toán: hợp đồng là yêu cầu nghiệp vụ nhưng có thể là mã

Giả sử **Inventory Service** là producer cung cấp:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Response đã thỏa thuận với **Checkout Service**:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Hợp đồng Groovy bình thường:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 con 8 san pham'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

Trong trường hợp hợp lệ, Spring Cloud Contract Verifier sử dụng tệp để sinh **generated producer test**, kiểm tra controller/implementation Inventory và tạo stub mapping để Checkout dùng với Stub Runner.

Nhưng Groovy là một **ngôn ngữ lập trình đa dụng**. Bên trong một script Groovy, cú pháp import, biến, lời gọi hàm và câu lệnh không chỉ là dữ liệu mô tả HTTP. Ví dụ vô hại dưới đây vẫn là **mã được thực thi**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

def sourceLabel = 'consumer-proposal'
println "Contract source: $sourceLabel"

// Các dòng Contract.make { ... } vẫn chỉ là một phần của Groovy script.
~~~

Đây là minh họa về **tính thực thi**, không phải một mẫu contract được khuyến nghị đưa vào production: cách plugin nạp script và cho phép top-level statements có thể thay đổi theo phiên bản. Điều quan trọng là một plugin có thể cần **đánh giá script**, chứ không chỉ parse các key của JSON.

Một người có khả năng sửa tệp Groovy có thể cố thêm các thao tác **không liên quan đến hợp đồng**: đọc tệp, truy cập biến môi trường, gọi process, tạo kết nối mạng hoặc thay đổi đầu ra build. Không cần hướng dẫn một payload tấn công cụ thể để nhận diện rủi ro: **ranh giới đầu vào có thể thực thi là nguy cơ chính**.

## 2. Vì sao CI/CD là mục tiêu nhạy cảm?

Build job thường có quyền mà tác giả PR không có trực tiếp:

| Tài nguyên CI | Ví dụ | Rủi ro khi DSL không tin cậy được thực thi |
|---|---|---|
| **Secrets** | Artifact token, deploy credential, cloud key | Có thể bị truy cập hoặc lộ qua log/traffic |
| **Workspace** | Source, fixture, generated test, build output | Có thể bị sửa/xóa hoặc làm sai bằng chứng kiểm thử |
| **Network** | Maven repository nội bộ, database test, metadata endpoints | Có thể bị truy cập trái mục đích |
| **Artifact publisher** | Nexus/Artifactory, Maven Central hoặc registry nội bộ | Có thể phát hành artifact không được kiểm chứng |
| **Git credentials** | Token dùng để tạo tag/push | Có thể sửa repository/nhánh ngoài ý muốn |
| **Build cache** | Gradle cache, Maven local, CI artifacts | Có thể bị nhiễm bẩn để ảnh hưởng các job khác |
| **Runner host** | Self-hosted runner, Docker daemon socket | Có thể gây ảnh hưởng vượt ra khỏi container/job |
| **Report/status** | Test count, logs, generated stub | Có thể bị làm giả hoặc che giấu failure |

**Mã Groovy không cần nằm trong `src/main` mới là nguy hiểm.** Nếu plugin đọc contract script trong lúc generate tests hoặc stubs, bước “build/test” đã là một điểm có thể thực thi nội dung của tệp.

Đặc biệt, chạy lệnh `./mvnw verify` hoặc `./gradlew contractTest` **không phải kiểm tra thuần túy an toàn**: Maven/Gradle scripts, plugins, test code và contract Groovy đều là các thành phần có thể thực thi. Một câu lệnh “chỉ để xác thực hợp đồng” vẫn có thể khởi chạy mã.

## 3. Mô hình ranh giới tin cậy

Phân loại đầu vào và môi trường theo **quyền kiểm soát**, thay vì chỉ theo phần mở rộng file.

~~~mermaid
flowchart TD
    A["PR chưa tin cậy / fork"] --> B["Static diff / metadata checks"]
    B --> C["Review code owners + security"]
    C --> D{"Đủ điều kiện thực thi?"}
    D -->|Chưa| E["Không chạy Groovy DSL ở job đặc quyền"]
    D -->|Có, nhưng vẫn cần thử| F["Runner dùng một lần, không secrets"]
    F --> G["Producer contract verification"]
    G --> H{"Tests PASS và provenance OK?"}
    H -->|Không| I["Không publish"]
    H -->|Có| J["Tạo candidate artifact có digest"]
    J --> K["Consumer Stub Runner compatibility tests"]
    K --> L{"Release gates PASS?"}
    L -->|Có| M["Promotion job được bảo vệ"]
    L -->|Không| I
~~~

Các khái niệm quan trọng:

- **Untrusted input:** PR từ fork, commit chưa review, contract JAR do nguồn ngoài đẩy lên, Git ref chưa được ghim, dependency có nguồn gốc không rõ.
- **Trusted review:** thay đổi đã được người có trách nhiệm xem cả ngữ nghĩa contract lẫn phần code có thể thực thi.
- **Isolated execution:** môi trường cho phép chạy nội dung để kiểm thử, nhưng không trao secrets hoặc quyền truy cập nhạy cảm.
- **Trusted promotion:** giai đoạn chuyển **chính artifact đã kiểm chứng** sang kênh phát hành, với approval và credentials riêng.
- **Provenance:** khả năng trả lời contract đến từ commit/artifact digest nào và test đã chạy trên bytes nào.

Không có một nhãn “internal branch” nào tự bảo đảm mọi thay đổi đều đáng tin. Một tài khoản thành viên có thể bị chiếm, một dependency có thể bị thay đổi, và một contract JAR có thể bị ghi đè khi CI đang chạy.

## 4. Bản đồ nguồn contract: nơi nào cần kiểm soát?

Spring Cloud Contract có thể nhận hợp đồng từ nhiều nguồn. Mỗi nguồn có một đường vào build.

| Nguồn hợp đồng | Ví dụ | Ranh giới cần kiểm tra |
|---|---|---|
| **File trong producer repo** | `src/contractTest/resources/contracts/*.groovy` | PR diff, CODEOWNERS, branch protection |
| **Folder được checkout ngoài module** | `../common-contracts/inventory` | Commit của repo ngoài, quyền CI, path có bị thay không |
| **Maven contract artifact** | `com.example.contracts:shared-contracts:1.4.0` | Repository, publisher, tọa độ, digest và contents |
| **Git SCM contract store** | `git://https://git.example.invalid/contracts.git` | Git ref/commit, quyền repo, layout và history |
| **Fixture/body template** | JSON/XML/body files, request matcher config | Tài liệu/templating, dữ liệu nhạy cảm và file path |
| **Build scripts và plugins** | `pom.xml`, `build.gradle`, plugin code | Bản thân pipeline chạy những file thực thi khác |
| **Stub artifact cho consumer** | `inventory-producer:2.3.0:stubs` | Candidate/verified distinction, nguồn mapping, version |

Vì vậy, bảo vệ duy nhất thư mục `src/contractTest/resources/contracts` là **chưa đủ** nếu producer còn tải contract JAR hoặc Git SCM từ ngoài. Cần kiểm soát **toàn bộ đường từ nguồn DSL tới nơi code được chạy**.

### Điều cần kiểm chứng khi dùng contract JAR

Một JAR được resolve thành công chỉ chứng minh artifact có thể tải. Nó **không** chứng minh script trong JAR an toàn.

Cần xác minh:

1. Group/artifact/version/classifier và repository nguồn.
2. Version/digest bất biến, không bị overwrite sau review.
3. Nội dung DSL/fixture thực sự nằm trong JAR.
4. Người/CI nào có quyền publish artifact đó.
5. Chỉ những path đã duyệt mới được generator tiêu thụ.
6. Producer tests thực thi trên **đúng bản đã review**.

Một repository nội bộ cũng có thể chứa artifact không đáng tin nếu quyền publish không được giới hạn.

## 5. YAML DSL có loại bỏ hoàn toàn rủi ro không?

**Không**, nhưng cần phân biệt chính xác.

| Đặc điểm | Groovy DSL | YAML DSL |
|---|---|---|
| Bản chất định dạng | Script của ngôn ngữ lập trình | Dữ liệu khai báo |
| Rủi ro thực thi mã tùy ý trực tiếp qua file | **Cao hơn**, khi plugin đánh giá script | **Thấp hơn** nếu parse bằng loader an toàn đúng schema |
| Có thể mô tả HTTP/message contracts | Có | Có |
| Có thể dùng làm nguồn generated tests/stubs | Có | Có |
| Có thể chứa nội dung gây hại cho hệ thống tiêu thụ | Có | Có: path, body, template, giá trị không hợp lệ |
| Có thay thế dependency/plugin review không | Không | Không |
| Có nghĩa cả pipeline là sandbox an toàn không | Không | Không |

**YAML không đồng nghĩa “không thể gây lỗi bảo mật”.** Nếu loader được cấu hình hỗ trợ deserialization kiểu tùy ý, tag mở rộng không tin cậy, custom transformer, script/template engine hoặc plugin chưa cập nhật, dữ liệu YAML vẫn có thể dẫn tới hành vi nguy hiểm.

Tuy nhiên, một chính sách kỹ thuật có thể **ưu tiên YAML khai báo** cho contract do bên ngoài đề xuất, khi chức năng DSL tương ứng đáp ứng yêu cầu. Bằng cách không cho phép Groovy ở tuyến untrusted, diện tích thực thi mã trực tiếp sẽ giảm.

### Kiểm soát phù hợp cho YAML

- Parser hỗ trợ **safe load**, không cho phép khởi tạo object/class tùy ý từ tag không tin cậy.
- Validate theo **schema và allowlist field** của contract DSL, không nhận key tùy ý.
- Giới hạn kích thước file, nesting/alias hoặc tài nguyên parser để tránh DoS.
- Chỉ cho phép fixture/body path trong root đã duyệt.
- Không tự render template bằng evaluator có quyền mạnh.
- Không cho một file YAML của PR sửa **CI workflow** hoặc plugin config ngoài phạm vi review.
- Dù chỉ là YAML, generator và test runner vẫn nên chạy **không có secrets**.

Nếu đội quyết định cho phép Groovy DSL vì matcher cần logic phức tạp, phải chấp nhận nó là **code review + execution isolation**, không gọi đó là “parse config”.

## 6. Phân loại thay đổi DSL theo mức rủi ro

Mọi thay đổi contract cần review nghiệp vụ; nhưng với **Groovy**, review an ninh cần xem nhiều hơn các field request/response.

| Kiểu thay đổi | Ví dụ | Hành động review |
|---|---|---|
| Đổi expected status/body | `200` thành `201`, thêm `quantity` | Đánh giá compatibility |
| Thêm matcher | `byType()`, `byRegex(...)` | Kiểm tra quá lỏng/chặt |
| Thêm header/path/query | `Idempotency-Key`, endpoint mới | Đánh giá API semantics |
| Thêm `import` không cần cho Contract DSL | Thư viện ngoài API contract | **Security review**, giải thích mục đích |
| Thêm top-level statement hoặc closure tùy ý | Lệnh không phục vụ request/response | **Chặn chờ review**, không chạy trên CI đặc quyền |
| Dùng API file/process/network/environment | Không liên quan contract behavior | Coi là **dấu hiệu rủi ro nghiêm trọng** |
| Sửa `pom.xml`/`build.gradle`/wrapper | Thay plugin/repository/script | Review như **build code thực thi** |
| Sửa workflow permissions/runner | Thêm write permission hoặc self-hosted | Review bảo mật và branch protection |
| Thêm contract từ repository ngoài | Đổi URL/version/branch | Kiểm tra provenance và quyền publish |

Một kiểm tra pattern tĩnh có thể phát hiện những dấu hiệu như import không thường gặp hoặc tham chiếu tới `System`, nhưng **không thể bảo đảm an toàn trước mọi mã Groovy**. Mã có thể được biểu diễn dưới nhiều dạng khác nhau. Do đó **không dùng blacklist regex thay cho ranh giới thực thi và review**.

## 7. Nguyên tắc không thực thi đầu vào chưa review ở job đặc quyền

Một pipeline không an toàn thường trộn chung:

~~~text
Pull request from untrusted contributor
    ↓
Checkout PR head
    ↓
Run ./gradlew contractTest (eval Groovy DSL)
    ↓
Artifact deploy credentials present
    ↓
Publish stubs / push tags
~~~

Ranh giới tin cậy đã bị vượt qua ở bước thực thi DSL **khi credentials đã hiện diện**, không phải chỉ tại bước publish.

Thiết kế tốt hơn:

~~~text
Untrusted PR
    ↓
Static review / checks with read-only permissions
    ↓
Optional isolated test execution (no secrets)
    ↓
Human/code-owner approval + verified source revision
    ↓
Producer verification on protected source
    ↓
Candidate artifact with digest
    ↓
Consumer compatibility tests
    ↓
Protected promotion job (credentials only here)
~~~

**Không có secret trong test execution job** nghĩa là không inject bằng environment, file, docker mount, agent credentials, credential helper hoặc network metadata service. Chỉ tắt một biến env mà vẫn mount `~/.m2/settings.xml` có repository password thì job chưa thực sự không có secrets.

### Kiểm soát quyền tối thiểu

- Token repository chỉ cần `contents: read` cho job đọc source.
- Không cấp quyền `packages: write`/`contents: write`/OIDC publish cho PR job.
- Không đưa deploy key, cloud credentials, Artifactory publish token vào test job.
- Không mount Docker socket hoặc thư mục host chứa secret vào runner untrusted.
- Không dùng persistent self-hosted runner có nhiều dự án cùng quyền nếu chưa có isolation.
- Mỗi PR execution dùng workspace/cache được cô lập hoặc reset đáng tin.
- Không dùng output/log/artifact từ PR để tự động thực thi trong privileged job.

Mục tiêu là nếu một PR chứa code không đáng tin, nó **không có tài nguyên giá trị để đánh cắp hoặc thao túng**, và không có quyền thay đổi bản phát hành.

## 8. CODEOWNERS, branch protection và nguồn review

Với GitHub, một `CODEOWNERS` minh họa có thể là:

~~~text
# Các đường dẫn minh họa theo repository cụ thể.
/inventory-producer/src/contractTest/resources/contracts/ @inventory-owners @security-reviewers
/inventory-producer/build.gradle @build-owners @security-reviewers
/.github/workflows/ @platform-security
/.github/CODEOWNERS @platform-security
~~~

Các tên account/team chỉ là placeholder. `CODEOWNERS` tự nó **không bắt buộc review** nếu branch protection/ruleset không yêu cầu code-owner approval.

Một chính sách nên có:

1. Protected branches không cho push trực tiếp tùy ý.
2. Required review của producer owner với Groovy DSL/contract JAR paths.
3. Security/platform review cho thay đổi workflow, Gradle/Maven plugin, wrapper và repository config.
4. Check runs bắt buộc, không cho tác giả tự bỏ qua.
5. Review lại khi PR được cập nhật sau approval, theo rule của nền tảng.
6. Phân quyền thay CODEOWNERS/ruleset cho nhóm quản trị thích hợp.
7. Ghi nhận reviewer đã kiểm tra **phần mã thực thi** chứ không chỉ status/body.

**Một approval của consumer về hành vi API không tương đương security approval cho mã Groovy tùy ý.** Hai loại review có mục tiêu khác nhau.


## 9. GitHub Actions: kiểm tra PR mà không chạy Groovy DSL

Ví dụ một workflow **chỉ kiểm tra tĩnh** của PR, không thực thi Gradle, Maven, Groovy, Spring Cloud Contract plugin hoặc test code từ nhánh PR:

~~~yaml
name: Contract proposal static checks

on:
  pull_request:

permissions:
  contents: read

jobs:
  contract-diff:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout for static review
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Check changed files without executing them
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        shell: bash
        run: |
          git diff --check "$BASE_SHA" "$HEAD_SHA"
          git diff --name-status "$BASE_SHA" "$HEAD_SHA" -- \
            inventory-producer/src/contractTest/resources/contracts/
          echo "DSL files were NOT executed in this job"
~~~

Đây là **ví dụ định hướng**; đường dẫn cần đổi theo repository, và action `actions/checkout@v4` nên được **ghim theo commit SHA đầy đủ** trong CI có yêu cầu supply-chain nghiêm ngặt. Workflow này làm được hai việc đơn giản:

- Hiển thị danh sách thay đổi trong vùng contract.
- Phát hiện whitespace errors của diff.

Nó **không phải** một Groovy security scanner, không đánh giá tính đúng đắn của contract, cũng không thay thế code-owner review.

### Vì sao không truyền secrets vào PR job?

Ngay cả job chỉ chạy kiểm tra tĩnh cũng nên **không có secrets**. Sau này có người thêm một bước `./gradlew contractTest` vào workflow: nếu workflow mặc định đã có credentials, ranh giới bảo mật sẽ bị phá mà ít người chú ý.

Đối với GitHub Actions:

- Sự kiện `pull_request` thường có quyền hạn chế hơn cho fork PR, nhưng phải **xác nhận chính sách của tổ chức và repository**; không dựa hoàn toàn vào mặc định.
- `permissions: contents: read` làm rõ ý định giới hạn quyền của `GITHUB_TOKEN`, nhưng không ảnh hưởng những secrets bị cấu hình ngoài token.
- `persist-credentials: false` giúp không lưu credentials checkout trong Git config để các bước sau vô tình tái sử dụng.
- `fetch-depth: 0` trong ví dụ để diff có đầy đủ base/head commit; cần cân nhắc chi phí fetch ở repository lớn.
- Chỉ `git diff` không thực thi DSL; nhưng chạy `./gradlew`, shell scripts, `make` hoặc Maven goals từ PR **là thực thi mã**.

### Nếu muốn chạy generator cho PR để phản hồi sớm?

Có thể, nhưng phải coi đây là **execution của untrusted code**. Dùng runner cô lập và ephemeral, không chứa secrets, không có quyền publish và hạn chế egress. Các bước kiểm tra tĩnh ở trên **không đủ bảo vệ** nếu sau đó runner được cấp quyền gọi Gradle/Maven.

Không gắn chất lượng contract với quyền truy cập bí mật: một PR hợp lệ về nghiệp vụ vẫn có thể chứa thêm câu lệnh Groovy không liên quan.

## 10. Cảnh báo đặc biệt: pull_request_target

Trong GitHub Actions, `pull_request_target` chạy trong ngữ cảnh của **base repository** và có thể được cấu hình với quyền/secrets mạnh hơn `pull_request`. Mối nguy xuất hiện khi một workflow dùng ngữ cảnh đặc quyền này rồi checkout **head commit của PR chưa tin cậy** và chạy Gradle/Maven/Groovy từ đó.

Sơ đồ sai:

~~~text
on: pull_request_target
    ↓
Checkout untrusted PR head
    ↓
Run producer contract generator / tests
    ↓
Job has base repo credentials or write privileges
    ↓
Untrusted Groovy/build code executes in privileged context
~~~

**Không thực hiện mẫu trên.**

`pull_request_target` có các use case hợp lệ như gắn nhãn hoặc xử lý metadata, nhưng không nên được dùng để chạy **mã nguồn/DSL** của PR chưa đáng tin với credentials của base repo.

### Các biến thể cùng rủi ro

- Dùng `workflow_run` có quyền mạnh, tải artifact từ một PR untrusted rồi thực thi file bên trong.
- Dùng workflow reusable với secrets mặc định cho mọi người gọi mà không kiểm tra ref/provenance.
- Đọc tên PR/branch do contributor đặt rồi chèn thẳng vào shell script template.
- Dùng `git checkout` tới một SHA do PR tự cung cấp trong publish job.
- Chạy một công cụ “lint” do chính PR thêm vào, trong khi nó là script thực thi.
- Tái sử dụng container/runner có token còn lưu từ job trước.

**Đầu vào không đáng tin vẫn không đáng tin khi được chuyển qua artifact hoặc message của một workflow khác.** Phải xác minh loại dữ liệu, nguồn gốc, digest và quyền trước khi một job có privilege sử dụng nó.

## 11. Tránh command injection từ metadata CI

Ngay cả khi không đọc Groovy DSL, metadata PR như title, branch name hoặc comment vẫn là **dữ liệu do người ngoài kiểm soát**. Chèn thẳng một biểu thức workflow vào lệnh shell có thể làm dữ liệu trở thành cú pháp của shell.

Ví dụ nên tránh về nguyên tắc:

~~~yaml
# Không làm:
# run: echo "${{ github.event.pull_request.title }}"
~~~

Một cách xử lý an toàn hơn cho việc in title:

~~~yaml
- name: Print PR title as data
  env:
    CHANGE_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$CHANGE_TITLE"
~~~

Cách trên truyền chuỗi vào **environment variable** và in như dữ liệu đã được quote, thay vì nội suy trực tiếp nội dung do người dùng kiểm soát thành source code shell. Tuy nhiên, mọi chuỗi dùng làm **đường dẫn file, ref, regex, command argument hoặc URL** vẫn cần validate theo ngữ cảnh.

**Không chạy `eval`, `bash -c` hoặc một công cụ template động trên text của contributor** chỉ để tiện xây câu lệnh. Chính sách này áp dụng cho metadata CI, không chỉ Groovy DSL.

## 12. Job producer verification sau review

Một ví dụ khác dành cho **protected branch**, giả định branch protection và code-owner approvals đã được áp dụng:

~~~yaml
name: Verified producer contracts

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify-producer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Verify approved producer contracts
        shell: bash
        run: |
          ./gradlew :inventory-producer:contractTest \
            --no-daemon --no-build-cache
~~~

**Ranh giới quan trọng:** job này chỉ thực thi source từ một branch đã được bảo vệ và review, không phải một PR head tùy ý. Nó không có publish secrets và không nên tự động làm release.

Ví dụ giả định producer dùng **Spring Cloud Contract Gradle plugin hiện đại**, task `contractTest` có tồn tại, wrapper/Gradle plugins đã được cấu hình và dependencies có thể được resolve. Với Maven, thay bằng `./mvnw -B -ntp clean verify` trong producer đã cấu hình verifier plugin.

**Không kết luận “an toàn tuyệt đối” chỉ vì commit ở `main`.** Chính sách review có thể sai, tài khoản maintainer có thể bị compromise, dependency/plugin có thể độc hại. Vì thế vẫn cần runner ephemeral, quyền tối thiểu và supply-chain controls.

### Một vấn đề vận hành: main bị đỏ

Chờ đến sau khi merge mới chạy full contract verification có thể phát hiện lỗi muộn. Với đội cần feedback trước merge, có thể chạy producer tests **trên PR** trong runner cô lập **không có secrets và không có quyền publish**, với network/access được kiểm soát. Sau approval, vẫn chạy xác nhận lại trên protected source để làm release gate.

Điều không được phép là dùng áp lực “muốn feedback sớm” để cấp publish credentials cho untrusted execution.

## 13. Cô lập thực thi: runner, filesystem và network

Một container **không tự là sandbox bảo mật tuyệt đối**. Process trong container vẫn có thể có network access, mount workspace chứa secrets, chia sẻ kernel với host hoặc chạy ở privileged mode.

Một test environment cho Groovy từ PR chưa tin cậy cần được thiết kế:

| Kiểm soát | Mục đích |
|---|---|
| **Ephemeral VM/runner** | Xóa trạng thái sau một lần chạy; tránh tác động sang job khác |
| **Không có secrets** | Không có token, key, Maven settings credentials, agent socket hoặc CI environment nhạy cảm |
| **Không root/privileged** | Giảm quyền trên filesystem, kernel và container host |
| **Không mount Docker socket** | Không trao quyền điều khiển Docker daemon của host |
| **Network egress allowlist hoặc không network** | Ngăn truy cập dịch vụ nội bộ và nguồn nhận dữ liệu không được phép |
| **Isolated writable workspace** | Cho build ghi output mà không làm bẩn thư mục dùng chung |
| **CPU/memory/time quotas** | Hạn chế việc chạy mã quá lâu hoặc chiếm tài nguyên |
| **Read-only mount cho nguồn/dữ liệu có thể** | Giảm sửa đổi source/hệ thống; cho phép output vào volume riêng |
| **Isolated dependency/cache** | Không cho một PR sửa cache dùng cho job tin cậy |
| **Log + artifact retention có kiểm soát** | Có bằng chứng nhưng không lưu secrets |

### Xung đột thực tế giữa network và build dependencies

`./gradlew` hoặc `./mvnw` có thể cần tải dependencies. Nếu chặn toàn bộ network ngay khi khởi chạy mà cache chưa có, build sẽ fail vì thiếu dependency chứ không phải do contract.

Một thiết kế có thể:

1. **Prefetch các dependencies đã duyệt** trong bước tin cậy, vào cache/read-only repository mirror.
2. Chạy untrusted build trong runner isolated chỉ đọc từ nguồn dependency được allowlist, không có đường tới internal sensitive services.
3. Ghi cache/output vào namespace riêng cho từng PR.
4. Không cho PR job ghi vào cache dependency được các protected jobs tin dùng.

Những bước này cần được triển khai ở runner/network policy thực tế. Thêm `--offline` mà chưa có dependency trong cache **không** phải một giải pháp ổn định.

### Cảnh báo về self-hosted runners

Với self-hosted runner dùng chung:

- Tệp credentials có thể còn trên host.
- Workspace và cache giữa các repository/PR có thể bị reuse.
- Runner có thể nằm trên VPC truy cập database, metadata, Kubernetes API hoặc registry nội bộ.
- Nếu runner cho phép container privileged hoặc truy cập Docker daemon, container isolation có thể không giữ được ranh giới dự định.

Một PR public/untrusted **không nên tự động được chạy trên runner self-hosted đặc quyền**. Nếu tổ chức cần self-hosted, hãy dùng runner dùng một lần với isolation đã được security team đánh giá.

## 14. Cấm secrets ở bước sinh test và kiểm thử contract

Một lỗi thiết kế là gộp nhiều quyền trong cùng job:

~~~text
Build:
  resolve contracts
  generate tests
  run producer implementation
  package stubs
  publish artifact
  push tags
  deploy staging
~~~

Nếu job có credentials từ đầu, **mọi mã được thực thi ở các bước đầu** đều có thể ảnh hưởng tới chúng. Groovy DSL chỉ là một trong các entry points.

Phân tách đề xuất:

1. **Validate proposal:** kiểm tra tĩnh, không secrets.
2. **Execute tests:** runner cô lập, read-only source, không publish token.
3. **Package candidate:** tạo artifact có digest/provenance, vẫn không có quyền phát hành chính thức.
4. **Compatibility check:** Stub Runner consumer test dùng candidate cụ thể.
5. **Approve release:** protected environment và approval.
6. **Promote artifact:** job có credentials, **không thực thi lại Groovy chưa tin cậy**; ưu tiên promotion của chính artifact đã kiểm chứng.

Đối với dịch vụ artifact cần xác thực **chỉ để đọc**, có thể dùng repository mirror hoặc token có quyền đọc rất hạn chế, chỉ dùng trong bước môi trường thích hợp. Dù vậy, **read credential vẫn là secret** và không nên đưa cho untrusted Groovy execution. Prefetch hoặc cache nguồn phụ thuộc đã được duyệt là lựa chọn an toàn hơn.

## 15. Supply chain: plugin, contract JAR và dependency đều là mã/nguồn dữ liệu

Ngăn Groovy script của PR chỉ là một lớp. Một build Java còn có thể thực thi:

- Gradle build scripts, init scripts, wrapper và plugin code.
- Maven plugins, extensions, lifecycle hooks.
- JUnit test classes, static initializers và build-time processors.
- Groovy contract scripts được tải từ Maven/SCM.
- Custom matcher/transformer/helper code và test fixtures.
- GitHub Actions/CI tasks và container entrypoints.

### Ghim version và nguồn

Không dùng các phụ thuộc nhạy cảm theo `latest` hoặc version wildcard nếu cần kết quả tái lập. Cần:

- Ghim phiên bản Spring Boot, Spring Cloud Contract plugin và dependency BOM tương thích.
- Kiểm tra provenance, checksum hoặc signatures theo chính sách tổ chức.
- Dùng repository đáng tin và giới hạn quyền publish.
- Không cho artifact release bị overwrite cùng version.
- Ghim contract JAR version và digest thay vì chỉ dựa vào một tên artifact.
- Với Git SCM, ghi commit SHA thực tế; một folder `META-INF/.../version` không tự ghim Git revision.
- Pin CI actions/container images theo immutable digest/SHA khi môi trường yêu cầu.
- Cô lập cache và không promote một artifact chỉ vì tên file giống output đã test.

### Vì sao “repo nội bộ” chưa đủ?

Nếu một tài khoản có quyền publish nội bộ bị compromise, một Groovy contract JAR có thể được cập nhật ngay trong registry được producer tin tưởng. Producer build sau đó tải artifact và thực thi DSL dù không có PR mới trong producer repository.

**Ranh giới tin cậy phải đặt ở cả nơi phát hành contract artifact**, không chỉ nơi chạy plugin.

## 16. Contract DSL, stub mapping và artifact promotion khác nhau

Trong pipeline Spring Cloud Contract:

~~~text
Groovy/YAML contract source
    |
    v
Producer generated tests (may execute code)
    |
    v
Producer verification PASS
    |
    v
Generated mappings/message definitions
    |
    v
Producer stubs artifact
    |
    v
Consumer Stub Runner
    |
    v
Consumer compatibility test
~~~

**Tạo stub JAR không chứng minh producer đã đáp ứng.** Generator có thể tạo mapping từ DSL ngay cả khi implementation producer không có endpoint tương ứng.

**Stub Runner test PASS cũng không thay thế producer test.** Consumer đang nói chuyện với stub, không phải producer thật.

### Khi artifact tới từ bước không tin cậy

Một output có vẻ đúng như `*-stubs.jar` vẫn là **untrusted artifact** nếu đến từ job đã thực thi DSL không được review. Privileged job không nên:

- Unzip/execute custom code hoặc load plugin/classes từ artifact mà không kiểm soát nguồn.
- Dùng mapping/fixture chưa verify để tạo “official” behavior.
- Đẩy artifact đó sang release repository mà không kiểm tra digest và provenance.
- Tự gắn nhãn verified chỉ vì consumer tests với stub thành công.

Một artifact candidate chỉ được promote khi nó **được tạo dưới nguồn/điều kiện đã xác minh** và có bằng chứng producer tests + consumer gates theo policy.

## 17. Không bỏ qua các thay đổi gián tiếp tới workflow

Một contributor có thể không cần sửa `*.groovy` nếu được phép sửa cách generator chạy. Những thay đổi sau cũng cần review bảo mật:

| File hoặc cấu hình | Tác động |
|---|---|
| `pom.xml` / `build.gradle` | Thêm plugin, repository, script hoặc tắt tests |
| `settings.gradle` / Gradle init scripts | Đổi nguồn plugins/dependencies hoặc logic cấu hình |
| `gradlew` / Maven wrapper config | Thay công cụ thực thi build |
| `.github/workflows/*.yml` | Đổi trigger, permissions, secrets, runner |
| Contract repository URL | Đổi nguồn Groovy từ artifact đáng tin sang nơi khác |
| `contractsPath`, include/ignore filters | Có thể kéo DSL khác hoặc bỏ test |
| `failOnNoContracts`, `failOnInProgress` | Ảnh hưởng gate khi không có contract hợp lệ |
| `skipTests` hoặc disable `contractTest` | Có thể tạo stub mà không xác minh producer |
| Stub publication destination | Có thể công bố artifact tới nơi không được phép |
| Docker runner/volume config | Có thể đưa secrets/socket vào phạm vi untrusted code |

CODEOWNERS và ruleset nên bao phủ cả **contract source và build/CI configuration**. Nếu chỉ yêu cầu review trong `contracts/`, kẻ gửi PR có thể làm thay đổi hành vi pipeline ở nơi khác.


## 18. Các mức kiểm tra: tĩnh, cô lập và tin cậy

Không phải mọi kiểm tra đều có quyền hoặc rủi ro như nhau.

| Lớp kiểm tra | Công việc | Có thực thi Groovy DSL? | Điều kiện |
|---|---|---|---|
| **Static file review** | Xem diff, extension, paths, whitespace, size | **Không** | PR từ nguồn bất kỳ, chỉ quyền đọc |
| **Static policy scan** | Tìm dấu hiệu imports/lệnh không cần thiết | **Không**, nếu scanner chỉ đọc text | Dùng scanner đã được review; không dùng script từ PR |
| **YAML schema validation** | Parse bằng safe loader, validate field/type | Thông thường không chạy Groovy | Chặn custom object deserialization/template execution |
| **Groovy syntax/generator check** | Compile/evaluate DSL | **Có thể có** | Runner untrusted-isolated hoặc nguồn đã review |
| **Producer contractTest** | Generated tests trên implementation | **Có** | Runner kiểm soát và không có publish secrets |
| **Consumer Stub Runner test** | Chạy stub mappings / message definitions | Có thể thực thi test/plugin code | Chỉ artifact nguồn rõ; test runner có quyền tối thiểu |
| **Artifact publish/promotion** | Công bố verified stub | **Không nên** thực thi lại untrusted input | Protected job, approval, provenance/digest |

Phân biệt “phân tích syntax” và “thực thi” rất quan trọng. Một công cụ kiểm tra cú pháp bằng cách **load/evaluate Groovy script** không còn là static scanner, dù CLI đặt tên là `validate` hay `lint`.

### Một chính sách đơn giản cho PR từ nguồn không tin cậy

1. Thu thập diff dưới dạng dữ liệu.
2. Kiểm tra cấu trúc file, đường dẫn, extension và giới hạn kích thước.
3. Gắn nhãn các thay đổi có import/top-level statement hoặc sửa build/CI config.
4. Đưa cho code owner và security reviewer.
5. Nếu cần chạy để nhận feedback trước review: **ephemeral isolated environment không secrets**, egress allowlist, không quyền publish.
6. Sau approval/merge vào protected ref, chạy producer verification lại.
7. Chỉ phát hành từ artifact đã được kiểm chứng cùng source revision.

Tìm chuỗi `System.getenv` hay `new File` giúp phát hiện một số thay đổi bất thường, nhưng không chứng minh các thay đổi còn lại an toàn. Dựa vào **positive policy và isolation**, không dựa vào blacklist ký tự.

## 19. Fail closed: bảo vệ tính toàn vẹn của contract test gate

Rủi ro không chỉ là exfiltration; một PR có thể làm test **không còn chạy** nhưng CI vẫn xanh.

Ví dụ:

~~~text
Before:
  24 generated producer tests executed, 24 passed

After change:
  0 generated producer tests executed
  Gradle/Maven build reports SUCCESS
~~~

Nếu publish dựa vào mỗi exit code, CI có thể công bố stub không được producer xác nhận.

### Các tín hiệu cần ghi lại

- Contract source/artifact version và SHA.
- Số DSL files được phát hiện theo producer/consumer.
- Số generated producer tests được sinh và thực thi.
- Tên các tests bị skip/ignored/in progress và lý do.
- Test reports PASS/FAIL, expected/actual khi có lỗi.
- Plugin version và test mode.
- `verifierStubsJar` hoặc `*-stubs.jar` có đúng mappings/fixtures không.
- Artifact hash/provenance và destination publish.

### Fail-on-no-contracts

Spring Cloud Contract có những option như `failOnNoContracts` và `failOnInProgress` trong các phiên bản/plugin tương ứng. Ví dụ minh họa phần cấu hình Gradle:

~~~groovy
contracts {
    failOnNoContracts = true
    failOnInProgress = true
}
~~~

**Cần kiểm tra tính tương thích/semantics theo version đang dùng.** Dù option được bật, CI vẫn nên kiểm tra số test thực thi, vì một base class bị sai hoặc bộ lọc `-x contractTest` có thể làm mất tác dụng của gate.

### Không dùng skip để “thông qua” release

Một số cách vô hiệu hóa test:

~~~bash
# Không dùng các cách này cho verified release gate:
./mvnw verify -DskipTests
./mvnw verify -Dmaven.test.skip=true
./gradlew build -x contractTest
~~~

Dù stub generation hoặc artifact packaging vẫn có thể tạo file, điều đó **không chứng minh producer implementation đã đạt DSL**.

### Không sửa report thay cho sửa code

Một thay đổi `generateContractTests` hoặc `contractTest` bị disable, xóa test report hay dùng task cache cũ có thể tạo vẻ ngoài thành công. Đối với security gate, không chỉ dựa vào artifact tồn tại và log tổng quát “BUILD SUCCESS”; phải kiểm tra bằng chứng của **đúng test run trên đúng revision**.

## 20. Bảo vệ artifact promotion và consumer pipeline

Một quy trình an toàn cho contract source đã được review:

~~~mermaid
sequenceDiagram
    participant Repo as Protected source
    participant P as Isolated producer CI
    participant Art as Candidate artifacts
    participant C as Consumer CI
    participant Gate as Approval / release policy
    participant Pub as Trusted publisher
    Repo->>P: Checkout reviewed SHA
    P->>P: Generate + execute producer contract tests
    alt Producer tests PASS
        P->>Art: Upload candidate stubs with digest
        Art->>C: Provide exact artifact version
        C->>C: Stub Runner consumer tests
        alt Consumer PASS
            C-->>Gate: Verified test evidence + digest
            Gate->>Pub: Approve promotion
            Pub->>Art: Promote exact artifact, no DSL re-evaluation
        else Consumer FAIL
            C-->>Gate: Block release
        end
    else Producer tests FAIL
        P-->>Gate: Block release
    end
~~~

### Tại sao cần kiểm tra digest?

Tên artifact có thể đúng nhưng bytes bị thay khi:

- Version `SNAPSHOT` bị overwrite.
- CI artifacts từ workflow untrusted được tải nhầm.
- Repo mirror/cache trả bản cũ.
- Release job rebuild lại từ branch di chuyển sang commit khác.
- Plugin sinh stub từ một contract source khác với bản producer test.

Ghim version **và** digest giúp kiểm tra **chính byte artifact** đã được producer verification tạo và consumer test sử dụng.

### Consumer Stub Runner có phải nơi chạy code không tin cậy?

Stub Runner không giống Groovy contract generator, nhưng consumer test vẫn chạy **Java test code, Spring runtime và mappings/fixtures từ artifact**. Mappings có thể sử dụng templating hoặc extension nếu đã được cấu hình; một stub artifact từ nguồn không tin cậy không nên được trao cho môi trường có secrets hoặc network nội bộ rộng.

Với consumer pipeline:

- Chỉ tải artifact từ repository được phép và version/digest đúng.
- Tránh `latest`/dynamic versions trong release gate.
- Không dùng `repositoryRoot` của một nguồn bất kỳ do PR tự cung cấp.
- Cô lập runner khỏi deployment secrets.
- Chặn việc consumer test pass được coi là producer verification pass.
- Kiểm tra cả request matcher và response/error body, không chỉ status.

## 21. Kịch bản 1: PR hợp đồng có đoạn Groovy không liên quan

### Bối cảnh

Một contributor ngoài nhóm gửi PR “sửa response JSON”. Diff thực tế gồm:

- Đổi `quantity` từ `8` sang `9`.
- Thêm một import/helper không phục vụ contract.
- Thêm top-level statement có thao tác môi trường.
- Sửa workflow để chạy `./gradlew contractTest` trong ngữ cảnh có quyền mạnh.

### Tại sao đáng nghi?

Thay đổi JSON có thể hợp lý. Nhưng import/top-level statement và workflow permissions **không cần thiết để biểu diễn response**. Đây là dấu hiệu có thể đang biến file contract thành điểm thực thi mã với quyền CI.

### Cách xử lý đúng

1. **Không chạy PR trên runner đặc quyền** để “kiểm tra xem có sao không”.
2. Xem toàn bộ diff của Groovy, build scripts và workflows.
3. Yêu cầu tác giả giải thích phần mã không liên quan hợp đồng.
4. Security/code owner review, từ chối hoặc sửa thay đổi nguy hiểm.
5. Giữ proposal validation ở chế độ kiểm tra tĩnh; nếu cần dynamic check, dùng sandbox ephemeral không secrets.
6. Sau approval, producer tests chạy trên source revision đã kiểm soát.
7. Không publish bất kỳ stub được tạo từ PR này trước producer gate.

**Vì sao không dùng regex duy nhất?** Tên import hoặc cách diễn đạt mã có thể thay đổi; việc tìm một số từ khóa giúp triage, không chứng minh đoạn script còn lại vô hại.

## 22. Kịch bản 2: contract JAR từ repository ngoài bị ghi đè

### Bối cảnh

Producer cấu hình tải:

~~~text
com.example.contracts:shared-contracts:1.4.0
~~~

Tổ chức sử dụng repository artifact nội bộ. Một publisher có quyền ghi đè version `1.4.0`, và pipeline sau đó tải contract JAR khác bytes đã review.

### Rủi ro

- Groovy DSL bên trong artifact có thể khác PR đã được duyệt.
- Producer generated tests có thể kiểm tra hành vi khác.
- Môi trường build có thể đánh giá mã Groovy mới mà không qua producer code review.
- Stub được tạo từ artifact khác với nguồn người review mong đợi.
- Các build dùng cache khác nhau có thể cho kết quả khác nhau.

### Biện pháp khắc phục

- Chặn overwrite release versions ở artifact registry.
- Tách quyền publish contract definitions khỏi quyền đọc của producer CI.
- Lưu digest của contract JAR đã review.
- Tạo candidate version riêng cho PR, không reuse release coordinate.
- Verify artifact digest ngay trước bước generator/producer tests.
- Kiểm tra repository ACL, publisher identity và provenance.
- Nếu có nghi vấn compromise, **dừng thực thi Groovy từ nguồn đó** cho tới khi xác minh.

**Không coi HTTPS và chữ “internal” là đủ.** HTTPS bảo vệ transport, không bảo đảm nội dung đã qua review hoặc publisher account chưa bị chiếm.

## 23. Kịch bản 3: pipeline bị sửa để bỏ qua tests

### Bối cảnh

Trong PR thay DSL, một contributor cũng đổi Gradle task dependencies để `verifierStubsJar` được publish dù `contractTest` chưa chạy, hoặc thêm `-x contractTest` vào CI command.

### Kết quả nguy hiểm

~~~text
Contract: new endpoint expected 201
Producer implementation: still returns 404

Generated stub: can return 201 according to DSL
Producer generated test: not executed
Consumer Stub Runner test: PASS
Release artifact published: YES
~~~

Cả artifact tồn tại và consumer test xanh đều **không chứng minh producer thật** đáp ứng API.

### Cách chặn

- CODEOWNERS bao phủ `build.gradle`/`pom.xml` và workflow files.
- CI kiểm tra producer test report và số generated tests đã chạy.
- Publish job phụ thuộc producer verification gate, không chỉ packaging.
- Release job không chạy tùy ý scripts từ PR artifacts.
- Quyền publish chỉ có sau approval và điều kiện pass.
- Lưu source SHA/digest cho contract và stub.
- Có chính sách chống `skipTests` hoặc test task bị vô hiệu hóa.

Đây là lý do việc **bảo vệ quá trình kiểm chứng** cũng quan trọng như bảo vệ secrets.

## 24. Khi nghi ngờ đã thực thi DSL độc hại

Một sự cố có thể bị phát hiện khi log build xuất hiện thao tác bất thường, output khác với hợp đồng, network traffic đi đến đích không mong đợi hoặc credentials có dấu hiệu bị lộ.

### Các bước ứng phó

1. **Dừng các job đang chạy cùng nguồn contract đáng nghi**, chặn publish và promotion.
2. **Cô lập runner** hoặc loại bỏ runner ephemeral theo quy trình sự cố; không tiếp tục dùng workspace/cache không rõ tình trạng.
3. **Giữ bằng chứng an toàn**: commit SHA, artifact digest, pipeline ID, logs đã được lọc secrets, danh sách hành động và thời điểm.
4. Xác định **tài nguyên mà job có quyền truy cập**: token, secret mounts, repository, registry, cloud credentials, network.
5. **Thu hồi/rotate credentials có khả năng bị lộ** theo quy trình an ninh của tổ chức; không đợi chứng minh hoàn toàn đã có exfiltration nếu rủi ro đáng kể.
6. Quarantine artifact/cache do job tạo; không tái sử dụng hoặc promote.
7. Review lịch sử PR, contract JAR versions, CI config và publisher ACL để tìm điểm vào.
8. Tạo runner mới, nguồn artifact đã xác minh và chạy lại producer/consumer gates.
9. Ghi lại root cause và bổ sung controls: permissions, CODEOWNERS, isolation, provenance, log.
10. Chỉ khôi phục phát hành sau khi đội chịu trách nhiệm xác nhận ranh giới đã được sửa.

Không đăng công khai secret hoặc nội dung nhạy cảm trong issue/PR để mô tả sự cố. Dùng kênh incident-response có phân quyền và log đã được redaction.

## 25. Bài tập 1: đánh giá độ tin cậy của một contract PR

### Đề bài

Có một PR từ fork thêm:

~~~text
inventory-producer/src/contractTest/resources/contracts/reservation.groovy
~~~

Ngoài `Contract.make { ... }`, tệp chứa import/helper không liên quan DSL. PR đồng thời sửa GitHub Actions để chạy Gradle trên `pull_request_target` và cấp `contents: write`.

**Câu hỏi 1:** Nên chạy `./gradlew contractTest` ngay để xem có pass không?

**Đáp án:** Không chạy trong job có quyền mạnh. Phải review diff, loại bỏ/giải thích mã không liên quan và kiểm tra workflow. Nếu cần dynamic feedback, dùng runner ephemeral cô lập, không secrets, không quyền publish.

**Câu hỏi 2:** Nếu code owner approve contract body thì đã đủ chưa?

**Đáp án:** Chưa. Cần review phần Groovy có thể thực thi và thay đổi workflow permissions; approval về nghiệp vụ không thay thế security review.

**Câu hỏi 3:** Thay toàn bộ Groovy thành YAML có giúp không?

**Đáp án:** Có thể giảm bề mặt thực thi trực tiếp nếu dùng safe YAML parser và schema chặt, nhưng vẫn phải bảo vệ build scripts, dependencies, templating, fixtures, runner và artifact promotion.

**Câu hỏi 4:** Test trong runner không có secrets nhưng vẫn cùng VPC nội bộ có an toàn không?

**Đáp án:** Chưa chắc. Runner có thể truy cập các dịch vụ nhạy cảm qua network, metadata endpoints hoặc caches. Cần egress policy, network segmentation và isolation phù hợp.

## 26. Bài tập 2: tìm chỗ làm CI xanh giả

### Tình huống

Producer và consumer đều là Spring Boot projects. Consumer yêu cầu thêm `POST /api/inventory/reservations`.

~~~text
Producer code:
  POST /reservations not implemented

Producer pipeline:
  generateClientStubs PASS
  verifierStubsJar PASS
  contractTest SKIPPED

Consumer pipeline:
  Stub Runner serves 201 from generated mapping
  Checkout test PASS

Release:
  candidate stub was promoted to verified repository
~~~

**Câu hỏi 1:** Bước nào sai về mặt chất lượng?

**Đáp án:** Producer contract verification đã bị skip, nhưng artifact được công bố như verified. Stub Runner chỉ chứng minh consumer xử lý được mapping, không chứng minh producer implementation đáp ứng.

**Câu hỏi 2:** Cần quality gate nào?

**Đáp án:** Bắt buộc generated producer tests thực sự chạy và PASS trên implementation, số test hợp lệ, artifact cùng revision, consumer compatibility PASS nếu policy yêu cầu, cuối cùng protected approval trước promotion.

**Câu hỏi 3:** Nếu contract đến từ common contract JAR thì kiểm soát gì thêm?

**Đáp án:** Repository/publisher ACL, immutable version, source SHA/digest, đúng `contractsPath` và bảo đảm Groovy trong JAR là mã đã được review.

**Câu hỏi 4:** Nếu PR cần thử DSL trước khi producer implement thì sao?

**Đáp án:** Dùng proposal/candidate test lane, báo rõ **chưa được hỗ trợ**; không dùng release gate hoặc verified repository cho kết quả thử nghiệm.

## 27. Checklist bảo vệ CI/CD khi có Groovy contract DSL

### Kiểm soát đầu vào và review

- [ ] Đã xác định mọi nguồn DSL: producer repo, external folder, contract JAR, Git SCM.
- [ ] Groovy DSL được coi là **mã thực thi**, không chỉ file cấu hình.
- [ ] Contract YAML dùng parser/schema an toàn; không bật deserialization/template tùy ý.
- [ ] PR từ nguồn chưa tin cậy không tự chạy Groovy trong job có quyền mạnh.
- [ ] CODEOWNERS/ruleset yêu cầu review code owner và security cho thay đổi nhạy cảm.
- [ ] Build scripts, wrapper, dependencies, CI workflows và runner config cũng được review.
- [ ] Diff không thêm lệnh file/process/network/environment không phục vụ contract.
- [ ] Không dựa duy nhất vào grep/regex blacklist để kết luận một script an toàn.

### Quyền và cô lập

- [ ] PR job chỉ có permission tối thiểu, không secrets/publish tokens.
- [ ] Không checkout rồi thực thi untrusted PR head bằng `pull_request_target` đặc quyền.
- [ ] Không để `workflow_run` thực thi artifact không tin cậy trong job có quyền cao.
- [ ] Không nội suy trực tiếp metadata PR chưa tin cậy vào shell commands.
- [ ] Dynamic PR testing nếu cần dùng runner ephemeral, không secrets, network hạn chế.
- [ ] Runner không privileged/root nếu không cần, không mount Docker socket.
- [ ] Workspace, dependencies và build caches không dùng chung theo cách PR có thể làm bẩn protected jobs.
- [ ] Network egress và quyền truy cập internal services được giới hạn.
- [ ] CPU/memory/time limits và log retention được cấu hình phù hợp.

### Producer verification và artifact

- [ ] Resolver tải đúng contract repository, source revision, version và digest.
- [ ] `contractsPath`/include filters không làm mất DSL cần kiểm chứng.
- [ ] Generated producer tests **được sinh, thực thi và PASS**, không bị skip/0.
- [ ] Build gate không coi `verifierStubsJar` được tạo là producer verification.
- [ ] Không dùng `-x contractTest`/`skipTests` cho verified release.
- [ ] Candidate artifact được ghim version/commit/digest, không overwrite release.
- [ ] Stub Runner consumer tests dùng đúng producer artifact candidate.
- [ ] Consumer tests không thay thế producer verification.
- [ ] Artifact promotion chỉ xảy ra sau gates và approval cần thiết.
- [ ] Publish credentials chỉ có ở protected promotion job, không có trong DSL execution job.

### Vận hành và ứng phó

- [ ] Có quy trình quarantine artifact/cache hoặc runner khi nghi ngờ compromise.
- [ ] Có khả năng thu hồi/rotate credentials liên quan.
- [ ] CI giữ source SHA, test report, artifact provenance và digest.
- [ ] Thay đổi breaking API/message vẫn được review như một phần quality gate.
- [ ] Không coi repository nội bộ hay HTTPS là bằng chứng duy nhất của trust.
- [ ] Nhóm có người chịu trách nhiệm bảo vệ workflow, repository ACL và release policy.

## 28. Ghi nhớ và tài liệu tham khảo

**Groovy contract DSL có thể là mã thực thi.** Vì vậy một PR hoặc contract JAR chưa tin cậy có thể không chỉ thay expected HTTP response; nó còn có khả năng ảnh hưởng quá trình sinh test hoặc build nếu bị đánh giá ở môi trường có quyền mạnh.

**Ba ranh giới không được nhập làm một:**

1. **Untrusted proposal:** đọc diff, review và kiểm tra tĩnh; dynamic test chỉ khi có isolation.
2. **Producer verification:** chạy mã từ nguồn đã được phê duyệt hoặc trong runner cô lập, không có publish secrets; chứng minh implementation đáp ứng contract.
3. **Trusted publication:** promote đúng artifact/version đã được kiểm chứng, có provenance và approval; không đánh giá lại DSL chưa tin cậy trong job có credentials.

Chọn YAML khai báo thay cho Groovy ở những tình huống phù hợp có thể giảm bề mặt thực thi trực tiếp, nhưng không loại bỏ nhu cầu bảo vệ dependencies, runners, sources, scripts, artifact pipeline và consumer Stub Runner.

### Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): Groovy/YAML DSL, generated producer tests, stubs và Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): các dạng DSL và matcher.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): lifecycle sinh và chạy contract tests.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, `verifierStubsJar` và publication.
- [GitHub Docs — Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): least privilege, untrusted input, runners, third-party actions.
- [GitHub Docs — Events that trigger workflows](https://docs.github.com/en/actions/reference/events-that-trigger-workflows): khác biệt ngữ cảnh của `pull_request` và `pull_request_target`.
- [GitHub Docs — About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners): cách yêu cầu review khi sửa file nhạy cảm.
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html): ranh giới quyền, secrets, runner isolation và supply-chain controls.
- [SLSA — Supply-chain Levels for Software Artifacts](https://slsa.dev/): provenance, build integrity và artifact verification.

**Kết luận thực hành:** nếu không thể giải thích **ai kiểm soát DSL đang được thực thi, job đó có quyền gì, và artifact được công bố đến từ đúng test run nào**, thì chưa đủ căn cứ để gọi pipeline là an toàn hoặc đáng tin. Bảo vệ được cả nguồn, bước thực thi và bước phát hành mới giúp Spring Cloud Contract phát hiện thay đổi không tương thích mà không tạo thêm rủi ro supply chain.
