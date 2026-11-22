# Kiểm soát action, plugin, image và script từ bên thứ ba

Pipeline CI/CD thường sử dụng nhiều thành phần do bên thứ ba cung cấp: GitHub Actions, GitLab CI components, Jenkins plugins, Azure DevOps extensions, container image, package build, script cài công cụ và các đoạn mã được tải trong lúc chạy. Những thành phần này giúp nhóm triển khai nhanh hơn, nhưng mỗi thành phần được đưa vào pipeline cũng có thể thực thi mã, đọc dữ liệu hoặc sử dụng quyền mà job đang sở hữu.

Vì vậy, bảo mật pipeline không chỉ là bảo vệ file YAML hay che giấu secret. Nhóm cần biết **mã nào được phép chạy, mã đến từ đâu, phiên bản nào được sử dụng, mã chạy với quyền gì và làm sao phát hiện khi nhà cung cấp hoặc thành phần bị xâm phạm**.

Đây là năng lực thuộc **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git và pipeline dưới dạng mã đến build, kiểm thử, artifact, môi trường và cổng chất lượng. Kiểm soát action, plugin, image và script từ bên thứ ba giúp giữ chuỗi cung ứng của chính pipeline trong phạm vi có thể quản lý và kiểm toán.

## 1. Vì sao thành phần bên thứ ba là ranh giới tin cậy?

Một action, plugin, container image hoặc script có thể thực hiện nhiều việc hơn tên gọi của nó gợi ý:

- Đọc mã nguồn và file trong workspace.
- Đọc biến môi trường và secret mà job được phép truy cập.
- Gọi mạng ra ngoài hoặc gửi dữ liệu đến dịch vụ khác.
- Sửa file, thay đổi artifact hoặc ghi dữ liệu vào cache.
- Gọi API của nền tảng CI bằng token được cấp cho job.
- Tải thêm dependency hoặc script khác trong lúc chạy.
- Thay đổi trạng thái repository, release, registry hoặc môi trường nếu có quyền.

Khi pipeline gọi một action, plugin hoặc script, nhóm đang trao một phần quyền thực thi cho mã đó. Một thành phần có thể được dùng rộng rãi vẫn có thể bị chiếm quyền tài khoản phát hành, bị thay đổi tag, bị đưa mã độc vào dependency hoặc bị phát hành phiên bản mới có hành vi khác trước.

Hãy xem chuỗi tin cậy như một đồ thị:

~~~mermaid
flowchart TD
    A["Repository và pipeline"] --> B["CI platform / runner"]
    B --> C["Action, plugin hoặc extension"]
    B --> D["Container image và toolchain"]
    C --> E["Script và dependency phụ"]
    D --> E
    E --> F["Workspace, artifact và cache"]
    B --> G["Token, secret và workload identity"]
    C --> G
    E --> G
    F --> H["Registry và môi trường triển khai"]
~~~

Mỗi nút có thể trở thành điểm xâm nhập. Nếu một action bị xâm phạm và job có token ghi repository, secret triển khai hoặc quyền truy cập registry, tác động có thể vượt xa bước kiểm thử mà action được dùng để thực hiện.

**Nguyên tắc:** chỉ đưa vào pipeline thành phần đã được nhận diện, đánh giá và pin phiên bản; giới hạn quyền của job; xác minh nội dung trước khi dùng và theo dõi thay đổi trong suốt vòng đời.

## 2. Lập inventory cho những gì pipeline thực thi

Trước khi kiểm soát, cần biết pipeline đang sử dụng thành phần nào. Inventory nên bao gồm cả thành phần khai báo trực tiếp và thành phần được tải gián tiếp.

| Loại | Ví dụ | Thông tin cần ghi |
| --- | --- | --- |
| CI action | GitHub Action, GitLab CI component | Publisher, repository nguồn, commit/version, quyền và dữ liệu truy cập |
| Plugin/extension | Jenkins plugin, Azure DevOps extension | Nhà phát hành, phiên bản, quyền chạy, tương thích và lịch sử cập nhật |
| Container image | Build image, scanner image, service image | Registry, repository, tag, digest, publisher và base image |
| Script bên thứ ba | Script cài CLI, deploy helper | URL nguồn, revision, checksum/chữ ký, quyền và dependency |
| Build tool/plugin | Gradle plugin, Maven plugin, npm package | Phiên bản, repository, checksum/signature và lifecycle script |
| Reusable workflow/template | Workflow hoặc pipeline template dùng chung | Repository nguồn, revision pin, maintainer và phạm vi quyền |

Inventory nên lưu trong repository hoặc hệ thống quản lý cấu hình có review. Với từng thành phần, ghi lý do sử dụng, owner nội bộ, nơi lấy mã, phiên bản được duyệt và cách cập nhật. Thành phần không còn dùng cần được gỡ bỏ để giảm bề mặt tấn công.

Không chỉ kiểm tra file workflow. Hãy xem các lệnh trong script, Dockerfile, Compose file, build file, file cấu hình plugin và các lệnh cài đặt được gọi lúc runtime. Một script nội bộ có thể tải thêm một binary từ Internet; binary đó cũng là dependency của pipeline.

## 3. Xác minh nguồn và nhà phát hành

Trước khi sử dụng một thành phần, hãy xác minh:

- Repository hoặc registry nguồn có đúng là nguồn chính thức không?
- Tài khoản/organization phát hành có được xác minh và được tổ chức tin cậy không?
- Mã nguồn có lịch sử thay đổi, review và quy trình release rõ ràng không?
- Phiên bản được phát hành có gắn với commit/tag hoặc digest xác định không?
- Có chữ ký, checksum, provenance hoặc attestations để xác minh không?
- Có thông báo bảo mật, CVE hoặc sự cố chuỗi cung ứng liên quan không?
- Có owner nội bộ chịu trách nhiệm cập nhật và ứng phó không?

Tên hiển thị, số lượt tải, dấu sao hoặc việc một action xuất hiện trong marketplace không đủ để chứng minh an toàn. Một tài khoản phổ biến có thể bị chiếm quyền; một repository chính thức có thể bị xâm phạm; một phiên bản mới có thể thêm dependency hoặc hành vi mới.

Ưu tiên nguồn phát hành chính thức, tài liệu upstream, chữ ký hoặc attestation do publisher phát hành và metadata có thể xác minh. Khi tổ chức có chính sách cho phép, có thể dùng proxy/registry nội bộ để lưu trữ các phiên bản đã được kiểm tra. Proxy giúp kiểm soát nguồn tải và tính sẵn sàng, nhưng không tự biến package không đáng tin thành an toàn.

### 3.1. Đánh giá phạm vi quyền trước khi phê duyệt

Đọc tài liệu và mã nguồn để xác định thành phần cần quyền gì:

- Có cần đọc toàn bộ repository không?
- Có cần ghi source, tag, release hoặc pull request không?
- Có cần truy cập secret hoặc token không?
- Có cần truy cập Docker socket hoặc host filesystem không?
- Có cần kết nối mạng ra Internet hoặc mạng nội bộ không?
- Có chạy code tùy ý từ input người dùng không?

Nếu một action chỉ upload test report nhưng yêu cầu token có quyền ghi toàn bộ repository, cần xem xét lại lựa chọn hoặc tạo cơ chế upload có quyền hẹp hơn. Quyền vượt quá nhu cầu làm tăng thiệt hại nếu thành phần bị xâm phạm.

## 4. Pin phiên bản bằng tham chiếu bất biến

Tag và tên phiên bản thường dễ đọc nhưng có thể thay đổi nội dung được tham chiếu. Pin bằng định danh bất biến giúp pipeline sử dụng đúng mã đã được review.

### 4.1. GitHub Actions và reusable workflow

Trong GitHub Actions, tham chiếu action bằng tag như @v4 thuận tiện nhưng tag có thể được cập nhật. Với workflow nhạy cảm hoặc yêu cầu kiểm soát chặt, pin action bằng full commit SHA đã xác minh:

~~~yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
~~~

Chuỗi trong dấu ngoặc nhọn là chỗ giữ chỗ; khi sử dụng phải thay bằng full commit SHA thực tế đã kiểm tra từ repository chính thức. Không dùng chuỗi minh họa như một phiên bản có thể chạy.

Với reusable workflow, cũng pin repository reference bằng commit SHA khi chính sách yêu cầu. Không dùng nhánh main hoặc tag có thể di chuyển làm căn cứ duy nhất cho workflow phát hành quan trọng.

Pin SHA ngăn tham chiếu tự đổi sang commit khác, nhưng không bảo đảm commit đó an toàn. Cần review nội dung commit, xác minh nguồn và theo dõi bản cập nhật upstream để không giữ mã có lỗ hổng quá lâu.

### 4.2. Container image

Không dựa vào tag di động như latest cho builder, scanner hoặc image được dùng trong release. Pin image bằng digest:

~~~text
ghcr.io/example-org/build-tool@sha256:<VERIFIED_IMAGE_DIGEST>
~~~

Digest định danh nội dung manifest/image cụ thể. Hãy lưu lại registry, repository, digest, platform và nguồn phát hành. Với multi-architecture image, kiểm tra image index digest và platform manifest tương ứng.

Nếu cần cập nhật image, tạo thay đổi có review để thay digest. Chạy lại build/test/scan và kiểm tra provenance của image mới trước khi đưa vào pipeline chính.

### 4.3. Plugin và extension

Với Jenkins, khai báo phiên bản plugin cụ thể trong cấu hình cài đặt, kiểm soát nguồn update center và cập nhật theo quy trình đã review. Không để controller tự cài plugin tùy ý từ một nguồn không được quản lý.

Với Azure DevOps hoặc các nền tảng extension khác, quản lý danh sách extension được phép, publisher, phiên bản và quyền tích hợp. Tắt hoặc gỡ extension không còn sử dụng. Nếu nền tảng tự cập nhật minor/patch version, cần hiểu cơ chế đó và áp dụng kiểm thử/kiểm soát thay đổi phù hợp.

### 4.4. Script và binary tải từ Internet

Tránh tải script rồi thực thi trực tiếp:

~~~bash
curl -fsSL https://example.com/install.sh | bash
~~~

Cách này thực thi ngay nội dung nhận được từ mạng, không cho người review cơ hội kiểm tra file hoặc xác minh checksum trước khi chạy.

Một cách có kiểm soát hơn:

~~~bash
curl --fail --location --silent --show-error \
  https://downloads.example.com/tool/1.4.2/tool-linux-amd64.tar.gz \
  --output tool.tar.gz

printf '%s  %s\n' "$EXPECTED_SHA256" tool.tar.gz | sha256sum --check -
tar -tzf tool.tar.gz
mkdir -p tool-unpacked
tar -xzf tool.tar.gz --no-same-owner -C tool-unpacked
~~~

EXPECTED_SHA256 phải đến từ một nguồn tin cậy độc lập hoặc metadata release có chữ ký được xác minh. Nếu tải archive và checksum từ cùng một endpoint không được xác thực, kẻ tấn công kiểm soát endpoint có thể thay cả hai. Với phần mềm hỗ trợ chữ ký số, ưu tiên xác minh chữ ký bằng trust root đã được quản lý. Trước khi giải nén, kiểm tra danh sách đường dẫn trong archive để phát hiện đường dẫn tuyệt đối hoặc thành phần ../ có thể ghi file ra ngoài thư mục đích; giải nén vào thư mục tạm riêng và không chạy binary trước khi xác minh.

Pin version, checksum hoặc signature cho cả dependency gián tiếp mà script cài đặt. Một installer đã pin nhưng lại tải bản latest của dependency bên trong vẫn tạo ra đầu vào không xác định.

## 5. Quyền tối thiểu cho job và thành phần

Một action hoặc script chạy trong job thường có thể sử dụng quyền mà job được cấp. Vì vậy, giảm quyền job là lớp bảo vệ quan trọng ngay cả khi thành phần đã được review.

Áp dụng least privilege:

- Chỉ cấp quyền đọc/ghi cần thiết cho từng job.
- Chỉ cấp secret cho step cần sử dụng.
- Tách job build/test khỏi job publish/deploy.
- Dùng token có thời hạn ngắn và scope hẹp.
- Không cấp quyền production cho job chạy mã từ pull request không tin cậy.
- Hạn chế quyền truy cập registry, cloud account và Kubernetes namespace.
- Không chạy runner với quyền administrator/root nếu không cần.

Ví dụ GitHub Actions đặt quyền mặc định ở mức đọc:

~~~yaml
permissions:
  contents: read

jobs:
  test:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
        with:
          persist-credentials: false
      - name: Run tests
        run: ./scripts/test.sh
~~~

Giá trị SHA trong ví dụ là chỗ giữ chỗ và cần được thay bằng commit đã xác minh. persist-credentials: false ngăn action checkout lưu credential Git được cấp trong cấu hình Git cho các lệnh sau khi step checkout hoàn tất, nếu job không cần push hoặc thao tác Git có xác thực.

Nếu một job cần publish package, hãy tạo job riêng chỉ có quyền ghi registry. Nếu một job cần tạo attestation bằng OIDC, chỉ cấp id-token: write cho job đó. Không cấp quyền này toàn workflow khi các job khác không cần.

### 5.1. Tách quyền theo giai đoạn

| Job | Quyền cần thiết | Không nên có |
| --- | --- | --- |
| Pull request test | Đọc source, chạy test | Secret production, quyền ghi release |
| Build/package | Đọc source, tải dependency, ghi artifact tạm | Quyền deploy production |
| Publish artifact | Ghi đúng registry/repository | Quyền sửa source hoặc quản trị organization |
| Attest/sign | Danh tính workload để ký đúng artifact | Private key dài hạn nằm trong workspace |
| Deploy staging | Quyền triển khai staging | Quyền quản trị production |
| Deploy production | Quyền production có approval và audit | Quyền rộng không liên quan đến deployment |

Tách job không tự động bảo đảm an toàn nếu artifact hoặc workspace có thể bị sửa giữa các job. Hãy truyền artifact theo digest, xác minh trước khi dùng và không tin dữ liệu đầu ra từ job không đáng tin cậy nếu chưa kiểm tra.

## 6. Bảo vệ secret và danh tính workload

Secret thường được dùng để truy cập registry, cloud, signing service hoặc môi trường triển khai. Một thành phần bên thứ ba có quyền đọc secret có thể gửi secret ra ngoài.

Thực hành nên áp dụng:

- Không ghi secret trực tiếp trong YAML, Dockerfile hoặc script.
- Dùng secret store của nền tảng CI hoặc secret manager.
- Chỉ truyền secret vào đúng step cần thiết.
- Không bật debug làm lộ environment hoặc command line.
- Không ghi token vào log, artifact, cache hoặc provenance.
- Dùng credential ngắn hạn thay cho access key dài hạn khi có thể.
- Xoay vòng và thu hồi credential khi nghi ngờ bị lộ.

Ưu tiên workload identity hoặc OIDC federation khi nền tảng và nhà cung cấp hỗ trợ. CI lấy token ngắn hạn dựa trên danh tính workflow/job, còn cloud provider kiểm tra issuer, audience và claims trước khi cấp quyền. Điều này giảm nhu cầu lưu cloud access key dài hạn trong repository secret.

OIDC không tự động an toàn. Cần giới hạn trust policy theo repository, branch, environment, workflow hoặc subject claim phù hợp. Nếu trust policy cho phép mọi workflow trong organization, một workflow ít tin cậy có thể xin danh tính có quyền cao.

## 7. Ngăn script injection từ dữ liệu không tin cậy

Pipeline thường nhận dữ liệu từ branch name, pull request title, commit message, issue body, tag hoặc input người dùng. Những giá trị này phải được xem là dữ liệu không tin cậy.

Ví dụ rủi ro trong GitHub Actions:

~~~yaml
- name: Print pull request title
  run: echo "${{ github.event.pull_request.title }}"
~~~

GitHub Actions mở rộng expression trước khi shell chạy. Nếu tiêu đề chứa dấu nháy hoặc cú pháp shell, nội dung được chèn có thể thay đổi câu lệnh.

Truyền dữ liệu qua environment variable:

~~~yaml
- name: Print pull request title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$PR_TITLE"
~~~

Trong ví dụ này, shell đọc giá trị biến đã được truyền vào môi trường. Trích dẫn "$PR_TITLE" ngăn word splitting và pathname expansion trong Bash. Tuy nhiên, dữ liệu vẫn cần được kiểm tra theo ngữ cảnh sử dụng: nếu đưa vào SQL, URL, option của CLI hoặc file path, phải dùng API/escaping/validation phù hợp với ngữ cảnh đó. Không dùng eval hoặc ghép dữ liệu đầu vào thành mã.

Các nguyên tắc:

- Giữ code cố định trong file đã review; truyền input dưới dạng dữ liệu.
- Validate input theo allowlist và định dạng mong đợi.
- Dùng argument array hoặc API thay cho chuỗi command ghép.
- Dùng -- để kết thúc option parsing nếu công cụ hỗ trợ và dữ liệu có thể bắt đầu bằng dấu gạch.
- Không thực thi script được lấy từ comment, PR body hoặc artifact không tin cậy.
- Không đưa dữ liệu không tin cậy vào template được đánh giá như mã.

## 8. Kiểm soát sự kiện pull request và fork

Pull request từ fork hoặc contributor bên ngoài là nguồn mã không tin cậy. Test job có thể cần chạy mã đó, nhưng không nên nhận secret hoặc quyền ghi.

Với GitHub Actions:

- pull_request thường là lựa chọn phù hợp để kiểm tra mã PR với quyền token hạn chế.
- Hãy đặt permissions tối thiểu và không cấp secret production cho job kiểm thử mã từ fork.
- Không dùng cache có thể ghi từ PR không tin cậy rồi để job phát hành tin cậy sử dụng mà không có ranh giới tin cậy.
- Cẩn trọng với pull_request_target: workflow chạy trong ngữ cảnh repository đích và có thể có quyền/secret cao hơn. Không checkout rồi thực thi mã từ head của PR không tin cậy trong workflow đó.
- Nếu cần tự động gắn nhãn hoặc phản hồi PR bằng pull_request_target, chỉ chạy code từ nhánh cơ sở đã tin cậy, kiểm tra input và giới hạn quyền token.

Mẫu nguy hiểm là dùng pull_request_target, sau đó checkout github.event.pull_request.head.sha và chạy script từ checkout đó với token ghi repository hoặc secret. Contributor có thể sửa script để lấy token hoặc secret.

Các nền tảng khác cũng có ranh giới tương tự: pipeline chạy từ merge request, fork, branch bảo vệ và tag release có thể nhận quyền khác nhau. Cần kiểm tra chính xác context, token và secret nào được cung cấp cho từng loại sự kiện.

## 9. Hardening container image và runner

Container image có thể chứa binary, package manager, entrypoint và script do bên thứ ba cung cấp. Image được pin digest vẫn có thể chứa lỗ hổng hoặc chạy với quyền quá rộng.

Khi chọn image:

- Dùng registry và publisher đáng tin cậy.
- Pin digest, ghi lại tag dễ đọc và platform.
- Kiểm tra Dockerfile, entrypoint và layer khi có thể.
- Quét image và theo dõi advisory sau khi publish.
- Ưu tiên image tối giản, giảm package và shell không cần thiết.
- Tạo SBOM và provenance cho image quan trọng.
- Cập nhật base image theo lịch và khi có advisory phù hợp.

Khi chạy container:

- Chạy bằng user không phải root.
- Dùng read-only root filesystem nếu ứng dụng cho phép.
- Bỏ Linux capabilities không cần thiết.
- Bật no-new-privileges khi phù hợp.
- Không mount Docker socket hoặc host filesystem trừ khi thực sự cần.
- Giới hạn CPU, memory, network và thời gian chạy.
- Không dùng privileged như giải pháp mặc định.

Ví dụ minh họa:

~~~bash
docker run --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  ghcr.io/example-org/test-runner@sha256:<VERIFIED_IMAGE_DIGEST>
~~~

Digest trong ví dụ là chỗ giữ chỗ, phải thay bằng digest đã xác minh. Một số ứng dụng cần capability, thư mục ghi hoặc quyền truy cập mạng cụ thể; hãy cấp đúng nhu cầu và ghi lý do thay vì bật toàn quyền.

Runner cũng là một phần của trust boundary. Runner dùng chung giữa các repository hoặc job có mức tin cậy khác nhau có thể làm rò rỉ workspace, cache hoặc credential. Dùng runner ephemeral cho workload nhạy cảm nếu nền tảng hỗ trợ; cô lập runner theo nhóm tin cậy và dọn workspace sau job.

## 10. Quản trị plugin và extension

Plugin thường có quyền sâu hơn một script chạy trong container. Plugin Jenkins có thể chạy trong tiến trình controller/agent và tương tác với các API của Jenkins. Extension của nền tảng CI có thể truy cập repository, build, variable hoặc service connection theo quyền được cấp.

Một quy trình quản trị nên có:

1. Danh sách plugin/extension được phép và owner nội bộ.
2. Lý do nghiệp vụ và quyền cần thiết của từng plugin.
3. Nguồn phát hành và publisher đã xác minh.
4. Phiên bản được pin hoặc chính sách cập nhật được kiểm soát.
5. Kiểm thử tương thích trong môi trường thử nghiệm trước production.
6. Theo dõi advisory, CVE và thông báo từ upstream.
7. Quy trình rollback hoặc gỡ plugin nếu bản cập nhật gây sự cố.
8. Review định kỳ để gỡ plugin không còn sử dụng.

Không cài plugin trực tiếp trên Jenkins controller production mà không có review và quy trình thay đổi. Cần bảo vệ quyền quản trị Jenkins, giới hạn ai được cài plugin và giữ bản kê phiên bản plugin để điều tra.

Với GitLab CI components hoặc Azure DevOps extensions, cũng cần quản lý nguồn include, version, publisher và quyền. Nếu một component tham chiếu bằng tag có thể thay đổi, cân nhắc pin revision hoặc dùng mirror nội bộ theo chính sách.

## 11. Cập nhật thành phần mà không bỏ quên rủi ro

Pin bất biến giúp build không tự thay đổi, nhưng pin mãi một phiên bản dễ giữ lại lỗ hổng đã biết. Vì vậy, cần kết hợp pinning với quy trình cập nhật:

- Theo dõi release và security advisory từ upstream.
- Dùng bot tạo pull request cập nhật version/SHA/digest khi phù hợp.
- Review diff, changelog, dependency mới và quyền thay đổi.
- Chạy test, scan và kiểm tra provenance của phiên bản mới.
- Cập nhật theo đợt nhỏ, có khả năng rollback.
- Đặt thời hạn xử lý cho lỗ hổng nghiêm trọng.
- Ghi nhận phiên bản đang được dùng và thời điểm cập nhật.

Không nên cập nhật tự động mọi action/plugin/image lên phiên bản mới nhất trong production mà không qua kiểm tra. Ngược lại, không nên trì hoãn cập nhật vô thời hạn chỉ vì đang pin SHA. Cân bằng giữa tính bất biến của mỗi lần chạy và khả năng cập nhật có kiểm soát.

Một thay đổi dependency nên được review như thay đổi mã: ai phát hành, mã nào đổi, có thêm quyền hoặc network access không, có script cài đặt mới không và có ảnh hưởng đến artifact hay không.

## 12. Ứng phó khi một thành phần bên thứ ba bị xâm phạm

Nếu upstream công bố action, plugin, image hoặc package bị xâm phạm, cần xác định liệu pipeline đã sử dụng phiên bản bị ảnh hưởng hay chưa.

Quy trình ứng phó:

1. **Xác định phạm vi:** inventory cho biết repository, workflow, job, runner và artifact nào dùng thành phần đó.
2. **Đóng băng thay đổi:** chặn phiên bản hoặc digest bị ảnh hưởng, ngừng cập nhật tự động từ nguồn đó.
3. **Cô lập:** vô hiệu hóa thành phần, runner hoặc credential có liên quan nếu cần.
4. **Điều tra:** kiểm tra log, network egress, workspace, cache, token usage và artifact đã tạo.
5. **Thu hồi secret:** revoke/rotate token, signing key hoặc credential có khả năng bị truy cập.
6. **Xác minh artifact:** xác định digest, provenance và release nào được tạo trong khoảng thời gian nghi ngờ.
7. **Tái tạo:** build lại từ source và dependency đã xác minh trên builder sạch.
8. **Phát hành lại hoặc rollback:** triển khai artifact sạch theo quy trình release.
9. **Ghi nhận:** lưu timeline, bằng chứng, quyết định và hành động khắc phục.

Không chỉ đổi version là đủ nếu runner hoặc secret có thể đã bị xâm phạm. Cần đánh giá quyền và credential mà thành phần từng có, đồng thời xác định artifact nào cần thu hồi.

## 13. Ví dụ workflow GitHub Actions có kiểm soát

Ví dụ dưới đây minh họa các nguyên tắc: quyền đọc mặc định, pin action bằng commit SHA, checkout không lưu credential và không truyền trực tiếp tiêu đề PR vào mã shell. Các SHA là chỗ giữ chỗ, phải thay bằng full SHA đã xác minh trước khi dùng:

~~~yaml
name: Pull request checks

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
        with:
          persist-credentials: false

      - name: Inspect pull request title
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
        shell: bash
        run: |
          printf 'PR title: %s\n' "$PR_TITLE"

      - name: Run tests
        shell: bash
        run: |
          set -euo pipefail
          ./scripts/ci-test.sh
~~~

Workflow này không cần secret để chạy test và chỉ có quyền đọc nội dung repository. Khi cần publish hoặc deploy, hãy tạo job riêng với quyền hẹp, approval và danh tính workload phù hợp. Không mở rộng quyền của job PR chỉ để dùng chung một workflow với release.

## 14. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng action theo tag có thể thay đổi trong pipeline nhạy cảm | Nội dung thực thi có thể đổi mà không có review | Pin full commit SHA và cập nhật qua PR |
| Dùng image latest | Build có thể dùng nội dung khác nhau giữa các lần chạy | Pin digest và quản lý cập nhật |
| Tải script rồi pipe thẳng vào shell | Thực thi nội dung mạng mà không xác minh | Tải về, xác minh checksum/chữ ký rồi mới chạy |
| Cho mọi job quyền ghi repository | Thành phần bị xâm phạm có thể sửa source/release | Cấp permissions theo từng job |
| Cấp secret production cho job PR | Mã không tin cậy có thể lấy secret | Tách job, event và môi trường đặc quyền |
| Tin chữ ký mà không kiểm tra signer | Mã từ nguồn không được phép vẫn có thể được chấp nhận | Kiểm tra issuer, identity và policy |
| Dùng container privileged và Docker socket tùy tiện | Container có thể kiểm soát host/runner | Giảm capability, user non-root và cô lập runner |
| Cài plugin không qua review | Plugin có thể chạy với quyền cao của CI controller | Allowlist, pin version, test và audit |
| Dùng dữ liệu PR trực tiếp trong script | Có thể tạo command injection | Truyền qua env, validate và quoting theo ngữ cảnh |
| Pin rồi không bao giờ cập nhật | Giữ lại phiên bản có lỗ hổng đã biết | Theo dõi advisory và cập nhật có kiểm soát |
| Không có inventory | Khó biết pipeline nào bị ảnh hưởng khi upstream có sự cố | Duy trì danh sách thành phần và owner |

## 15. Checklist kiểm soát thành phần bên thứ ba

**Nguồn và phiên bản**

- [ ] Có inventory cho action, plugin, extension, image và script.
- [ ] Publisher và repository/registry nguồn đã được xác minh.
- [ ] Thành phần được pin bằng commit SHA, digest hoặc version cụ thể phù hợp.
- [ ] Có checksum, chữ ký hoặc provenance khi nguồn hỗ trợ.
- [ ] Dependency gián tiếp và script cài đặt được xem xét.

**Quyền và dữ liệu**

- [ ] Job chỉ có quyền tối thiểu cần thiết.
- [ ] Secret chỉ được cấp cho step/job cần sử dụng.
- [ ] Job từ fork/PR không tin cậy không có secret production hoặc quyền ghi.
- [ ] Dữ liệu bên ngoài được truyền như dữ liệu và validate theo ngữ cảnh.
- [ ] Không có lệnh tải và thực thi trực tiếp nội dung chưa xác minh.
- [ ] OIDC trust policy giới hạn đúng repository/workflow/environment.

**Runner, container và plugin**

- [ ] Image được pin digest và quét theo chính sách.
- [ ] Container chạy non-root, giảm capability và giới hạn tài nguyên khi phù hợp.
- [ ] Không mount Docker socket/host filesystem nếu không cần.
- [ ] Runner được cô lập theo mức độ tin cậy và có cleanup.
- [ ] Plugin/extension nằm trong allowlist, có owner và lịch cập nhật.

**Vận hành và ứng phó**

- [ ] Có quy trình review/update action, plugin, image và script.
- [ ] Theo dõi advisory và sự cố từ upstream.
- [ ] Có khả năng revoke credential và cô lập runner.
- [ ] Có inventory để truy tìm artifact/release bị ảnh hưởng.
- [ ] Có quy trình tái tạo artifact và rollback khi cần.
- [ ] Lưu log và audit trail đủ để điều tra.

## Kết luận

Action, plugin, image và script từ bên thứ ba đều là mã được pipeline tin cậy để thực thi. Kiểm soát chúng cần bắt đầu từ inventory và xác minh nguồn, sau đó pin bằng định danh bất biến, giới hạn quyền, bảo vệ secret, cô lập runner và kiểm tra dữ liệu đầu vào. Chữ ký hoặc digest giúp xác định nội dung và nguồn phát hành, nhưng vẫn cần policy để quyết định thành phần nào được phép chạy.

Pinning phải đi cùng cập nhật có kiểm soát. Khi upstream bị xâm phạm, nhóm cần biết thành phần xuất hiện ở đâu, credential nào có thể bị truy cập và artifact nào cần xác minh hoặc phát hành lại. Duy trì những thực hành này giúp giảm rủi ro chuỗi cung ứng ngay trong pipeline và giữ luồng build, test, publish, deploy có thể truy vết.
