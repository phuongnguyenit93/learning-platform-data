# Repository connections và Cloud Build triggers

Một pipeline CI/CD cần biết mã nguồn nằm ở đâu, cách xác thực với Git provider và sự kiện nào sẽ khởi chạy build. Repository connection thiết lập cầu nối có kiểm soát giữa Google Cloud với hệ thống quản lý mã nguồn như GitHub, GitLab hoặc Bitbucket. Cloud Build trigger lắng nghe sự kiện trên repository, chọn cấu hình build và khởi chạy pipeline khi điều kiện phù hợp.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, bài học này đặt repository connections và triggers vào quy trình phát hành ứng dụng chạy trên Compute Engine, GKE, Cloud Run và các dịch vụ lưu trữ, dữ liệu của Google Cloud. Khi kết nối và trigger được thiết kế đúng, nhóm có thể tự động kiểm thử mỗi pull request, đóng gói artifact theo commit, kiểm soát phát hành theo nhánh hoặc tag và lưu lại bằng chứng cho từng lần build.

Sau bài học, người học có thể:

- Phân biệt host connection, repository link và Cloud Build trigger.
- Chọn mô hình kết nối phù hợp giữa Developer Connect và Cloud Build repositories thế hệ 2.
- Hiểu trạng thái của Cloud Build repositories thế hệ 1 và Cloud Source Repositories.
- Tạo trigger cho push, tag, pull request và các sự kiện khác.
- Lọc sự kiện theo branch, tag, pull request và đường dẫn file.
- Cấu hình build bằng cloudbuild.yaml và sử dụng substitutions.
- Cấp quyền IAM đúng cho người quản trị connection, người tạo trigger và service account chạy build.
- Bảo vệ pipeline khỏi mã nguồn không tin cậy, secret bị lộ và quyền triển khai quá rộng.
- Theo dõi build, xử lý lỗi kết nối và kiểm thử luồng CI/CD từ commit đến artifact.

## 1. Tổng quan luồng repository connection và trigger

Cloud Build không tự đọc repository bên ngoài chỉ vì project đã bật Cloud Build API. Trước tiên cần thiết lập kết nối với Git provider, liên kết repository cụ thể, rồi tạo trigger để ánh xạ sự kiện Git sang một cấu hình build.

~~~mermaid
flowchart LR
    A[Developer push hoặc mở pull request] --> B[Git provider]
    B --> C[Repository connection]
    C --> D[Repository link]
    D --> E[Cloud Build trigger]
    E --> F[Build configuration]
    F --> G[Build service account]
    G --> H[Tests và package]
    H --> I[Artifact Registry]
    I --> J[Deploy stage hoặc release workflow]
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Source provider | Nơi lưu Git repository và phát sinh sự kiện | GitHub, GitLab, Bitbucket |
| Host connection | Kết nối tài khoản/tổ chức Git provider với Google Cloud | Kết nối GitHub organization |
| Repository link | Liên kết một repository cụ thể thuộc host connection | Liên kết repo orders-api |
| Cloud Build trigger | Điều kiện và hành động khi nhận sự kiện | Push vào main thì chạy build |
| Build config | Các bước kiểm thử, build, push artifact | cloudbuild.yaml |
| Build service account | Danh tính có quyền thực hiện các bước build | CI service account |

Một host connection có thể dùng cho nhiều repository link. Một repository có thể có nhiều trigger, chẳng hạn trigger kiểm thử pull request, trigger build nhánh main và trigger tạo release khi có tag. Nên đặt tên để người vận hành nhận biết mục đích, môi trường và repository của từng trigger.

## 2. Chọn cách kết nối repository

Cloud Build hiện hỗ trợ các luồng kết nối thế hệ mới thông qua Developer Connect hoặc Cloud Build repositories (2nd gen). Cả hai đều cho phép Cloud Build xây dựng từ repository đã liên kết và khởi chạy build theo commit hoặc pull request. Cách quản lý connection và một số loại trigger có khác nhau.

### 2.1. Developer Connect

Developer Connect cung cấp connection và link để kết nối Git repository bên ngoài Google Cloud. Connection đại diện cho cầu nối với Git provider; link đại diện cho repository cụ thể được chọn trong provider đó.

Cloud Build có thể dùng repository đã liên kết bằng Developer Connect để tạo trigger. Các nhà cung cấp được hỗ trợ cho luồng Cloud Build gồm:

- GitHub và GitHub Enterprise.
- GitLab và GitLab Enterprise Edition.
- Bitbucket Cloud và Bitbucket Data Center.
- Một số biến thể Enterprise hoặc private network tùy provider và hướng dẫn kết nối.

Khi tạo link repository, Developer Connect thiết lập cơ chế webhook cho repository. Nhờ vậy, push hoặc pull request có thể kích hoạt trigger mà người tạo connection không cần đăng nhập lại ở thời điểm build.

Developer Connect phù hợp khi tổ chức muốn quản lý các tích hợp Git trong một lớp kết nối chung của Google Cloud và dùng repository đó với nhiều dịch vụ hỗ trợ Developer Connect.

### 2.2. Cloud Build repositories (2nd gen)

Cloud Build repositories thế hệ 2 cung cấp host connection và repository link dành cho Cloud Build. Có thể tạo và quản lý connection qua Console, gcloud, API hoặc Terraform theo phạm vi provider được hỗ trợ.

Quy trình gồm:

1. Tạo host connection tới Git provider.
2. Hoàn tất xác thực hoặc cài đặt ứng dụng tích hợp theo provider.
3. Chọn repository và tạo repository link.
4. Tạo trigger tham chiếu tới repository đã liên kết.
5. Chọn build config, region và service account.

Cloud Build repositories thế hệ 2 hỗ trợ GitHub, GitHub Enterprise, GitLab, GitLab Enterprise Edition, Bitbucket Cloud và Bitbucket Data Center. Mô hình này có thể tạo trigger theo branch push, tag push và pull request; ngoài ra còn hỗ trợ manual, Pub/Sub và webhook trigger.

### 2.3. So sánh các lựa chọn thế hệ mới

| Khả năng | Developer Connect repository | Cloud Build repositories (2nd gen) |
|---|---|---|
| Branch push, tag push và pull request | Có | Có |
| Manual trigger | Không trong luồng Developer Connect | Có |
| Pub/Sub trigger | Không trong luồng Developer Connect | Có |
| Webhook trigger | Không trong luồng Developer Connect | Có |
| Quản lý connection qua gcloud | Có | Có |
| Tạo connection bằng Terraform | Không phải lựa chọn được hỗ trợ trong bảng capability của Cloud Build | Có với một số provider; ngoại lệ gồm Bitbucket Data Center và Bitbucket Cloud |
| Connection và repository link theo region | Có | Có |

Chọn mô hình dựa trên cách tổ chức quản lý Git integration và loại trigger cần dùng. Nếu chỉ cần build khi push hoặc pull request và muốn dùng lớp tích hợp chung, Developer Connect là lựa chọn phù hợp. Nếu cần quản lý connection trực tiếp cho Cloud Build hoặc cần thêm manual, Pub/Sub và webhook trigger, hãy đánh giá Cloud Build repositories thế hệ 2.

### 2.4. Cloud Build repositories (1st gen) và Cloud Source Repositories

Cloud Build repositories thế hệ 1 đã được thay thế bởi thế hệ 2 và hiện chỉ còn là lựa chọn legacy. Khi tạo kiến trúc mới, nên xem thế hệ 2 hoặc Developer Connect trước.

Cloud Source Repositories (CSR) cũng có giới hạn về khả năng tiếp nhận khách hàng mới: từ ngày 17-06-2024, tổ chức chưa từng sử dụng CSR trước thời điểm đó không thể bật API hoặc bắt đầu sử dụng dịch vụ. Các tổ chức đã sử dụng CSR trước mốc này không bị ảnh hưởng bởi thay đổi được công bố và có thể tiếp tục sử dụng theo điều kiện hiện hành.

Vì vậy:

- Không thiết kế hướng dẫn onboarding mới dựa trên giả định mọi project đều có thể bật CSR.
- Với tổ chức đang dùng CSR, lập kế hoạch duy trì hoặc chuyển repository sang Git provider phù hợp.
- Khi gặp tài liệu cũ hướng dẫn mirrored GitHub/Bitbucket qua CSR, kiểm tra xem tài liệu đang mô tả luồng legacy nào.
- Không nhầm Cloud Build repositories thế hệ 2 với Cloud Source Repositories; đây là hai tên sản phẩm và mô hình kết nối khác nhau.

Google Cloud cũng có Secure Source Manager với trigger tích hợp Cloud Build. Đây là một lựa chọn repository do Google Cloud quản lý riêng; cần đánh giá khả năng hỗ trợ và yêu cầu triển khai của tổ chức.

## 3. Chuẩn bị project, API và quyền truy cập

Trước khi tạo connection, xác định project sở hữu trigger, region sử dụng và danh tính sẽ chạy build. Không nhất thiết người có quyền kết nối repository cũng là người được quyền triển khai production.

### 3.1. API và project

Các API thường cần bật tùy kiến trúc:

- Cloud Build API để quản lý trigger và chạy build.
- Developer Connect API nếu dùng Developer Connect.
- Secret Manager API nếu connection hoặc build cần dùng secret.
- Artifact Registry API nếu pipeline lưu image hoặc package tại Artifact Registry.
- Các API của dịch vụ đích như Cloud Run, GKE hoặc Compute Engine nếu pipeline thực hiện deploy.

Nếu connection và trigger nằm ở các project khác nhau, phải xác định rõ project sở hữu connection, project chạy build và project chứa artifact. Cấu hình IAM cross-project cần được kiểm tra riêng.

### 3.2. Quyền của người quản trị connection

Người tạo connection cần quyền quản lý connection trong Google Cloud và quyền phù hợp tại Git provider để cài đặt/ủy quyền ứng dụng tích hợp hoặc chọn repository.

Một số role thường gặp:

| Role | Phạm vi sử dụng |
|---|---|
| roles/developerconnect.admin | Quản trị tài nguyên Developer Connect, gồm connection và repository link |
| roles/developerconnect.user | Dùng connection và tương tác với repository theo quyền được cấp |
| roles/cloudbuild.connectionAdmin | Tạo, sửa, xóa Cloud Build connections và repositories thế hệ 2 |
| roles/cloudbuild.connectionViewer | Xem connection và repository đã liên kết |

Role cụ thể cần dùng phụ thuộc mô hình kết nối. Không cấp đồng thời mọi role quản trị chỉ để một người chọn repository.

### 3.3. Quyền tạo trigger

Người quản lý trigger cần quyền tương ứng trên Cloud Build. Khi trigger dùng user-managed service account, người tạo hoặc cập nhật trigger còn cần quyền impersonate service account, thường thông qua:

- Cloud Build Editor hoặc role tùy chỉnh có quyền quản lý trigger cần thiết.
- roles/iam.serviceAccountUser trên service account được chọn để có quyền iam.serviceAccounts.actAs.

Quyền tạo trigger và quyền chạy build là hai vấn đề khác nhau. Người dùng có thể được phép cấu hình trigger nhưng service account của build vẫn cần được cấp quyền riêng cho từng hành động.

### 3.4. Quyền của service account chạy build

Nên tạo service account riêng cho từng nhóm pipeline hoặc môi trường, ví dụ:

- ci-test: đọc source và chạy test.
- ci-build: build image và đẩy image vào một Artifact Registry repository cụ thể.
- cd-staging: triển khai staging.
- cd-production: triển khai production sau bước phê duyệt.

Chỉ cấp các quyền mà build thực sự cần. Ví dụ, pipeline build image có thể cần Artifact Registry Writer trên repository đích; pipeline triển khai Cloud Run cần quyền triển khai dịch vụ và quyền actAs runtime service account theo thiết kế. Không cấp Owner hoặc Editor cho service account build chỉ để tránh lỗi quyền.

Cloud Build đã thay đổi cách chọn default service account theo cấu hình tổ chức. Có project dùng Compute Engine default service account, có project còn cho phép legacy Cloud Build service account. Vì vậy, hãy kiểm tra service account thực tế của trigger và chỉ định user-managed service account khi cần kiểm soát quyền rõ ràng.

Khi trigger sử dụng user-specified service account, hãy cấu hình nơi lưu build logs phù hợp, chẳng hạn Cloud Logging với lựa chọn logging tương ứng hoặc Cloud Storage bucket do người dùng quản lý. Xác minh service account có quyền ghi log.

## 4. Tạo repository connection

Quy trình chi tiết có thể khác theo Git provider, nhưng các bước chính tương tự nhau.

### 4.1. Kết nối từ Google Cloud Console

1. Chọn project sẽ quản lý kết nối.
2. Mở Developer Connect hoặc Cloud Build Repositories tùy mô hình được chọn.
3. Chọn region cho host connection.
4. Chọn Git provider, ví dụ GitHub hoặc GitLab.
5. Bắt đầu quy trình xác thực/cài đặt ứng dụng do Google Cloud hướng dẫn.
6. Chọn organization hoặc account cần kết nối tại Git provider.
7. Giới hạn repository mà ứng dụng được phép truy cập theo chính sách của tổ chức.
8. Hoàn tất tạo connection và xác minh trạng thái kết nối.
9. Chọn repository cụ thể để tạo repository link.
10. Đặt tên link rõ ràng và kiểm tra repository có thể được liệt kê/đọc.

Connection và link phải được tạo ở region được hỗ trợ. Trigger tham chiếu tới connection/link theo location; vì vậy hãy chọn region nhất quán ngay từ đầu và ghi rõ trong tài liệu vận hành.

### 4.2. Connection với GitHub

Với GitHub, người có quyền quản trị organization hoặc quyền phù hợp có thể cài đặt GitHub App do Google Cloud cung cấp. Khi cài app, chọn repository cụ thể hoặc toàn bộ organization theo chính sách.

Nên ưu tiên chỉ cho app truy cập những repository cần build. Nếu có nhiều nhóm sản phẩm, có thể tạo các connection hoặc quyền truy cập tách biệt để giảm phạm vi ảnh hưởng khi một connection bị thu hồi.

Sau khi cài app:

- Kiểm tra GitHub App đã được cài vào đúng organization.
- Kiểm tra repository mong muốn nằm trong phạm vi app.
- Liên kết repository vào đúng Google Cloud project và region.
- Xác minh push hoặc pull request có thể phát sinh sự kiện tới Cloud Build.

### 4.3. Connection với GitLab hoặc Bitbucket

GitLab và Bitbucket có các bước cấp quyền, cài ứng dụng hoặc cấu hình kết nối riêng. Với GitLab Enterprise, Bitbucket Data Center hoặc hệ thống nằm trong mạng riêng, cần kiểm tra DNS, firewall, TLS, đường kết nối và hướng dẫn cho đúng loại provider.

Không dùng một hướng dẫn GitHub để cấu hình GitLab hoặc Bitbucket chỉ vì cả ba đều dùng Git. Cơ chế cấp token, quyền repository, webhook và phạm vi network có thể khác nhau.

### 4.4. Kết nối repository private network

Repository Enterprise có thể nằm trong mạng riêng hoặc on-premises. Cần xác định hai đường kết nối:

1. Đường Developer Connect/Cloud Build kết nối tới Git host để xác thực, đọc metadata và nhận sự kiện.
2. Đường build worker truy cập các dependency private cần thiết trong lúc build, ví dụ private package registry, internal artifact store hoặc private endpoint.

Private pool của Cloud Build giải quyết nhu cầu chạy build trong network được kiểm soát và truy cập tài nguyên private theo thiết kế. Private pool không tự động tạo connection tới mọi Git host. Hãy kiểm tra riêng yêu cầu kết nối repository và yêu cầu network của build worker.

## 5. Cloud Build trigger hoạt động như thế nào?

Trigger là cấu hình liên kết sự kiện, nguồn code, build config, region, service account và các điều kiện bổ sung. Khi sự kiện phù hợp đến, Cloud Build tạo build tương ứng.

### 5.1. Các loại repository event trigger

| Loại sự kiện | Khi nào chạy | Ví dụ |
|---|---|---|
| Branch push | Có commit mới được đẩy vào nhánh khớp bộ lọc | Push vào main |
| Tag push | Có tag mới được đẩy và khớp pattern | v1.4.0 |
| Pull request | Pull request được tạo/cập nhật theo cấu hình provider | PR hướng tới main |
| Manual | Người vận hành chủ động chạy trigger | Chạy lại release candidate |
| Pub/Sub | Có message được publish tới topic đã chọn | Artifact Registry có image mới |
| Webhook | Endpoint webhook nhận sự kiện phù hợp | Hệ thống Git hoặc công cụ ngoài gửi event |
| Scheduled manual | Cloud Scheduler gọi manual trigger theo lịch | Chạy build kiểm tra định kỳ |

Không phải mọi loại trigger có trên mọi mô hình repository connection. Developer Connect-linked repository hỗ trợ các sự kiện repository như branch push, tag push và pull request; manual, Pub/Sub và webhook trigger là các khả năng được nêu cho Cloud Build repositories thế hệ 2.

### 5.2. Branch và tag filters

Trigger có thể giới hạn branch hoặc tag bằng pattern. Ví dụ:

- Branch pattern: main.
- Branch pattern: release/*.
- Tag pattern: v*.
- Tag pattern: v[0-9]* nếu muốn giới hạn theo cấu trúc tag phù hợp.

Pattern được đánh giá theo cú pháp mà giao diện hoặc API trigger hỗ trợ. Cần thử với tên nhánh/tag thực tế, đặc biệt khi dùng wildcard hoặc biểu thức phức tạp.

Một trigger production không nên chạy trên mọi branch. Hãy chọn nhánh được bảo vệ, quy định review và quyền merge trước khi cho phép trigger có quyền triển khai.

### 5.3. Pull request trigger

Pull request trigger phù hợp để chạy lint, unit test, kiểm tra dependency, build kiểm thử hoặc phân tích mã trước khi merge.

Các điều kiện cần xem:

- Nhánh đích của pull request.
- Repository nguồn của pull request, bao gồm fork nếu provider cho phép.
- Sự kiện tạo hoặc cập nhật pull request.
- Cơ chế comment control nếu cần người có quyền trong repository xác nhận build.
- Quyền của service account và loại secret mà build có thể truy cập.

Build chạy từ pull request có thể thực thi code do người gửi PR cung cấp. Nếu service account có quyền đọc secret hoặc deploy production, một PR không đáng tin cậy có thể tìm cách sử dụng các quyền đó. Vì vậy, PR trigger nên dùng service account chỉ có quyền test, không được đọc production secrets và không được deploy production.

Với GitHub pull request trigger, có thể dùng comment control để yêu cầu repository owner hoặc collaborator bình luận lệnh /gcbrun trước khi build bắt đầu. Đây là một lớp kiểm soát bổ sung; vẫn cần bảo vệ branch và giới hạn quyền service account.

### 5.4. Lọc theo file thay đổi

Trigger có thể dùng included files và ignored files để giới hạn build theo đường dẫn thay đổi. Ví dụ:

- Chỉ chạy khi thư mục services/orders/** thay đổi.
- Bỏ qua docs/** khi pipeline không cần build lại ứng dụng.
- Chạy pipeline dùng chung khi cloudbuild.yaml hoặc thư mục shared-libraries/** thay đổi.

Khi dùng path filters, cần tính tới file được đổi tên, xóa, hoặc pull request chạm nhiều thư mục. Một thay đổi trong shared library có thể ảnh hưởng nhiều service dù thư mục service không đổi. Nếu filter quá chặt, trigger có thể bỏ sót thay đổi quan trọng.

## 6. Cấu hình build bằng cloudbuild.yaml

Build config mô tả các bước mà Cloud Build thực hiện sau khi trigger được kích hoạt. Tệp thường đặt ở root repository hoặc đường dẫn được khai báo trong trigger.

Một build config có thể gồm:

- steps: các bước chạy lệnh hoặc container builder.
- images: image được đẩy lên registry sau khi build thành công.
- artifacts: cấu hình lưu artifact khác theo định dạng được hỗ trợ.
- substitutions: biến được thay thế tại thời điểm build.
- options: cấu hình build như logging, machine type hoặc tùy chọn khác.
- timeout: thời gian tối đa cho build.
- availableSecrets/secretEnv: cách đưa secret từ Secret Manager vào bước cần dùng.

### 6.1. Ví dụ build và test ứng dụng Java

Ví dụ sau chạy Maven test, đóng gói image và đẩy image lên Artifact Registry. Repository Artifact Registry cần được tạo trước; trigger sẽ chọn service account có quyền ghi vào repository đó.

~~~yaml
steps:
  - name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "test"]

  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_AR_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$SHORT_SHA
      - .

images:
  - $_AR_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$SHORT_SHA

substitutions:
  _AR_REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

Trong ví dụ:

- Bước Maven chạy test trước khi tạo image.
- Docker builder đóng gói source thành image.
- Trường images yêu cầu Cloud Build đẩy image đã tạo tới Artifact Registry sau khi các bước thành công.
- SHORT_SHA là substitution mặc định của trigger, lấy bảy ký tự đầu của commit SHA.
- Các biến tùy chỉnh bắt đầu bằng dấu gạch dưới, ví dụ _AR_REGION.
- logging được đặt thành CLOUD_LOGGING_ONLY để build log đi vào Cloud Logging.

Ví dụ là cấu hình khởi đầu, cần điều chỉnh image builder, Java version, Maven wrapper, đường dẫn Dockerfile và tên Artifact Registry theo repository thực tế. Không dùng cùng build config này cho PR không tin cậy nếu service account có quyền đẩy image release; hãy dùng trigger/config riêng cho kiểm thử pull request.

### 6.2. Build steps và thứ tự thực thi

Mặc định các bước build được thực hiện theo thứ tự trong danh sách. Khi một bước thất bại, build thường dừng và đánh dấu lỗi. Có thể dùng waitFor để cho phép các bước độc lập chạy song song.

Ví dụ:

~~~yaml
steps:
  - id: unit-tests
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "test"]

  - id: lint
    name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args: ["-c", "./scripts/lint.sh"]

  - id: package
    name: maven:3.9-eclipse-temurin-21
    waitFor: ["unit-tests", "lint"]
    entrypoint: mvn
    args: ["-B", "package", "-DskipTests"]
~~~

Ở đây, unit-tests và lint có thể chạy song song; package chờ cả hai hoàn tất. Hãy tránh song song hóa các bước có phụ thuộc dữ liệu hoặc thay đổi cùng một workspace.

### 6.3. Default substitutions và user-defined substitutions

Cloud Build cung cấp substitutions cho build:

| Biến | Ý nghĩa |
|---|---|
| $PROJECT_ID | Project ID |
| $BUILD_ID | ID của build |
| $PROJECT_NUMBER | Project number |
| $LOCATION | Region của build |
| $TRIGGER_NAME | Tên trigger |
| $COMMIT_SHA | Commit SHA |
| $SHORT_SHA | Bảy ký tự đầu của commit SHA |
| $REPO_NAME | Tên repository |
| $REPO_FULL_NAME | Tên repository kèm owner/organization |
| $BRANCH_NAME | Tên branch |
| $TAG_NAME | Tên tag |
| $REF_NAME | Tên branch hoặc tag |

Một số biến chỉ có giá trị trong loại sự kiện tương ứng. Ví dụ, TAG_NAME không có ý nghĩa với build không được kích hoạt bởi tag; biến không có sẵn có thể được thay bằng chuỗi rỗng.

Với pull request trigger, có thêm các biến như:

- $_HEAD_BRANCH: branch nguồn của pull request.
- $_BASE_BRANCH: branch đích.
- $_HEAD_REPO_URL: URL repository nguồn.
- $_PR_NUMBER: số pull request.

User-defined substitutions phải bắt đầu bằng dấu gạch dưới và dùng chữ hoa, chữ số hoặc dấu gạch dưới. Ví dụ: _AR_REGION, _IMAGE_NAME, _DEPLOY_ENV. Dùng substitutions để tái sử dụng build config theo môi trường, nhưng không đưa mật khẩu, token hoặc private key vào substitutions vì giá trị có thể xuất hiện trong cấu hình hoặc log.

## 7. Tạo Cloud Build trigger trong Console

Các nhãn trên giao diện có thể thay đổi theo phiên bản Console, nhưng quy trình tổng quát như sau:

1. Chọn project dùng để quản lý build.
2. Mở Cloud Build > Triggers.
3. Chọn region của trigger.
4. Chọn Create trigger.
5. Đặt tên và mô tả mục đích trigger.
6. Chọn event: branch push, tag push hoặc pull request.
7. Chọn repository connection và repository link đã tạo.
8. Cấu hình branch/tag pattern hoặc pull request target branch.
9. Thêm included/ignored files nếu cần.
10. Chọn build config trong repository, ví dụ cloudbuild.yaml.
11. Chọn service account chạy build.
12. Cấu hình substitutions, approval hoặc build options nếu cần.
13. Lưu trigger và kiểm thử bằng một commit hoặc pull request có kiểm soát.

Nếu chọn trigger ở region cụ thể, hãy bảo đảm repository connection và link có trong location phù hợp. Nếu cần private pool, cấu hình pool trong build config hoặc build arguments theo hướng dẫn của Cloud Build.

### 7.1. Một repository, nhiều trigger

Một cách tổ chức thông dụng:

| Trigger | Sự kiện | Build config | Quyền của build |
|---|---|---|---|
| orders-pr-check | Pull request vào main | cloudbuild-pr.yaml | Chỉ test và đọc dependency công khai |
| orders-main-build | Push vào main | cloudbuild.yaml | Test, build và push image vào Artifact Registry |
| orders-release | Tag v* | cloudbuild-release.yaml | Tạo artifact release, chờ approval trước deploy |

Tách trigger giúp mỗi loại sự kiện có quyền và mục tiêu riêng. Nếu dùng một trigger duy nhất cho mọi sự kiện, phải kiểm soát kỹ substitutions, điều kiện và service account để không vô tình cấp quyền release cho PR.

## 8. Quản lý trigger bằng gcloud và tự động hóa

gcloud CLI hỗ trợ liệt kê, xem, chạy và quản lý Cloud Build triggers. Cú pháp tạo trigger cụ thể thay đổi theo kiểu repository connection và provider; hãy dùng đúng nhóm lệnh tương ứng với loại connection đã chọn.

Liệt kê trigger trong một region:

~~~bash
gcloud builds triggers list --region=asia-southeast1
~~~

Chạy trigger thủ công theo branch:

~~~bash
gcloud builds triggers run orders-main-build \
  --region=asia-southeast1 \
  --branch=main
~~~

Chạy build trực tiếp từ source đang có trong thư mục hiện tại:

~~~bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  .
~~~

Chạy build trực tiếp hữu ích để kiểm tra build config trước khi gắn trigger. Nó không chứng minh webhook, branch filter hoặc repository connection đã hoạt động; cần thực hiện thêm một lần kiểm thử bằng sự kiện Git thực tế.

Với Cloud Build repositories thế hệ 2, host connection và repository link có thể được tạo bằng gcloud, API hoặc Terraform theo loại provider được hỗ trợ. Developer Connect cũng có thể được quản lý qua Console/gcloud/API theo khả năng của từng tài nguyên. Nên quản lý connection và trigger bằng Infrastructure as Code khi tổ chức cần tái tạo cấu hình giữa nhiều project hoặc môi trường.

## 9. Bảo mật repository connection và build trigger

Trigger có thể biến quyền ghi mã nguồn thành quyền thực thi build. Nếu build service account có quyền deploy, người có thể đẩy code vào branch kích hoạt trigger có thể gián tiếp yêu cầu Cloud Build chạy code với quyền đó. Đây là ranh giới bảo mật quan trọng.

### 9.1. Bảo vệ quyền truy cập Git provider

- Chỉ cài Git app vào organization/repository cần thiết.
- Ưu tiên quyền repository-scoped thay vì cấp quyền toàn tổ chức nếu không cần.
- Dùng branch protection hoặc ruleset để yêu cầu review và kiểm tra trước khi merge.
- Bật MFA/SSO và quy trình thu hồi tài khoản cho Git provider.
- Rà soát bot account, token và quyền của connection định kỳ.
- Theo dõi thay đổi installation, webhook và repository access.

### 9.2. Tách quyền theo giai đoạn

Tách quyền test, build, publish và deploy:

- PR trigger: chạy test, lint, scan; không truy cập production secret.
- Main trigger: build và push image vào repository staging hoặc repository ứng dụng tương ứng.
- Release trigger: tạo release artifact và có approval trước khi deploy production.
- Deploy service account: chỉ có quyền cập nhật đúng dịch vụ/cluster/project cần thiết.

Không đặt service account quyền Owner hoặc Editor trong build config. Với trigger, service account được cấu hình trên trigger là danh tính thực hiện build; trường serviceAccount trong build config không thay thế lựa chọn service account của trigger khi trigger gọi build.

### 9.3. Bảo vệ pull request từ fork hoặc contributor ngoài

Code trong pull request có thể sửa script, Dockerfile, Maven plugin hoặc test để đọc biến môi trường và gửi dữ liệu ra ngoài. Do đó:

- Không cung cấp secret production cho PR build.
- Không dùng service account có quyền deploy hoặc đọc dữ liệu production.
- Dùng comment control hoặc approval cho trigger có rủi ro cao khi provider hỗ trợ.
- Kiểm tra quyền truy cập repository và quy tắc merge.
- Tách build kiểm thử khỏi build phát hành.
- Không tin cậy kết quả từ PR chưa được review như một artifact production.

### 9.4. Dùng Secret Manager cho bí mật

Nếu build cần token để truy cập package registry hoặc dịch vụ nội bộ:

1. Lưu secret trong Secret Manager.
2. Cấp quyền Secret Manager Secret Accessor cho build service account trên đúng secret.
3. Khai báo secret trong build config bằng cơ chế availableSecrets/secretEnv phù hợp.
4. Chỉ truyền secret vào bước thực sự cần dùng.
5. Không echo secret ra stdout/stderr và không đưa secret vào substitution.
6. Đặt lịch rotation và quy trình thu hồi.

Với PR không tin cậy, không cấp quyền đọc secret. Chỉ bật secret trong trigger hoặc build dành cho source đã được kiểm soát.

### 9.5. Approval và separation of duties

Cloud Build có thể cấu hình trigger để build ở trạng thái pending approval trước khi chạy. Người có quyền Cloud Build Approver có thể approve hoặc reject build đang chờ.

Approval hữu ích cho deploy production, migration dữ liệu hoặc thay đổi hạ tầng có tác động lớn. Nên tách người phê duyệt khỏi người tạo thay đổi khi quy trình tổ chức yêu cầu separation of duties.

## 10. Theo dõi build và kiểm tra trạng thái trigger

Sau khi trigger được tạo, kiểm thử lần lượt từng điều kiện:

1. Tạo commit trên branch không khớp filter và xác nhận trigger không chạy.
2. Tạo commit trên branch khớp filter và xác nhận build được tạo.
3. Mở pull request để xác nhận đúng trigger PR được kích hoạt.
4. Thay đổi file ngoài phạm vi included files để xác nhận path filter.
5. Tạo tag phù hợp nếu có release trigger.
6. Kiểm tra build log, artifact và substitutions.
7. Kiểm tra service account trong build details để xác nhận đúng danh tính.

Trong Cloud Build History, kiểm tra:

- Build ID, trigger name, source repository và commit SHA.
- Event/branch/tag/pull request gây ra build.
- Build config path và substitutions.
- Service account, worker pool và thời gian thực thi.
- Step nào thành công/thất bại và log tương ứng.
- Artifact được tạo và vị trí lưu trong Artifact Registry.

Nên lưu liên kết build hoặc commit SHA trong thông tin release để truy vết từ artifact về source.

## 11. Troubleshooting: lỗi thường gặp

**Không thấy repository trong danh sách.** Kiểm tra connection đã được tạo ở đúng project/region chưa; Git app đã được cài vào đúng organization chưa; repository có nằm trong phạm vi được cấp quyền không.

**Không tạo được connection.** Kiểm tra quyền IAM quản lý connection, quyền quản trị tại Git provider, API đã bật, callback/authentication hoàn tất và network tới Git host.

**Trigger không chạy sau khi push.** Kiểm tra branch/tag pattern, region, repository link, webhook delivery, trạng thái trigger và event type. Đảm bảo commit thực sự được push tới repository đã liên kết.

**Pull request không kích hoạt build.** Kiểm tra base branch filter, provider support, fork policy và comment control. Nếu comment control được bật, cần đúng người có quyền bình luận lệnh kích hoạt.

**Trigger chạy nhưng build không tìm thấy cloudbuild.yaml.** Kiểm tra build config path, tên file, phân biệt chữ hoa/chữ thường và vị trí file trong commit được build.

**Build lỗi permission denied.** Xác định danh tính service account thực tế của trigger; kiểm tra quyền Artifact Registry, Cloud Logging, Secret Manager, Cloud Run/GKE hoặc private pool theo bước thất bại. Không cấp Owner để xử lý lỗi tạm thời.

**Build không truy cập được private dependency.** Kiểm tra private pool, subnet, DNS, firewall, route, proxy và quyền registry. Repository connection không tự cấp network access cho build worker.

**Image build thành công nhưng không được push.** Kiểm tra trường images, Artifact Registry repository, region, tên image và quyền Artifact Registry Writer của service account.

**Build PR có thể đọc secret ngoài dự kiến.** Tách service account và build config cho PR, loại secret khỏi trigger không tin cậy, rà soát quyền truy cập Secret Manager và lịch sử build.

**Build dùng service account khác dự kiến.** Kiểm tra service account được chọn trên trigger. Với trigger, lựa chọn trên trigger quyết định danh tính chạy build; không dựa vào serviceAccount trong build config để thay đổi danh tính đó.

**Trigger ở region khác repository connection.** Kiểm tra location của host connection, repository link và trigger. Tạo lại hoặc chọn region nhất quán theo yêu cầu sản phẩm.

## 12. Thực hành: tạo CI cho pull request và build image từ main

Giả sử repository GitHub chứa ứng dụng Java tên orders-api. Mục tiêu:

- Mỗi pull request vào main chạy unit test.
- Khi merge vào main, Cloud Build chạy test, tạo container image và push vào Artifact Registry.
- Khi tạo tag release, một pipeline riêng tạo artifact release và yêu cầu phê duyệt trước bước deploy production.

### Bước 1: tạo kết nối

1. Chọn project CI.
2. Bật Cloud Build API và Developer Connect API hoặc dùng Cloud Build repositories thế hệ 2.
3. Tạo host connection tới GitHub ở region đã chọn.
4. Cài GitHub App vào organization và chỉ cấp quyền tới repository orders-api.
5. Liên kết repository orders-api.
6. Xác minh link repository ở trạng thái sẵn sàng.

### Bước 2: tạo service account

Tạo service account cho từng mục đích:

- orders-pr-ci: chỉ chạy test, không có quyền push image production.
- orders-main-ci: chạy test, build và push image vào Artifact Registry repository app-images.
- orders-prod-release: dùng cho release/deploy và chỉ được chọn trong trigger có approval.

Cấp Artifact Registry Writer cho orders-main-ci trên đúng repository image. Cấp quyền deploy cần thiết cho orders-prod-release trên đúng dịch vụ đích. Người tạo trigger cần quyền actAs trên service account được chọn.

### Bước 3: tạo PR trigger

1. Chọn repository orders-api đã link.
2. Chọn pull request event.
3. Đặt base branch là main.
4. Chọn build config cloudbuild-pr.yaml.
5. Chọn service account orders-pr-ci.
6. Không cấp production secret hoặc quyền deploy.
7. Tạo pull request thử nghiệm và xác nhận build chỉ chạy test.

### Bước 4: tạo main trigger

1. Chọn branch push event.
2. Đặt branch pattern là main.
3. Chọn build config cloudbuild.yaml.
4. Chọn service account orders-main-ci.
5. Đặt substitutions cho Artifact Registry region và image name.
6. Push một commit vào main và xác nhận image được lưu với tag theo commit SHA.

### Bước 5: tạo release trigger

1. Chọn tag push event.
2. Dùng pattern v*.
3. Chọn cloudbuild-release.yaml.
4. Chọn service account orders-prod-release.
5. Bật approval trước khi build/deploy nếu quy trình yêu cầu.
6. Tạo tag release thử nghiệm và kiểm tra build pending approval.

### Bước 6: xác minh bằng chứng

- Pull request build có kết quả test và không thể đọc production secret.
- Main build có commit SHA, image URI và log.
- Release build có tag, người phê duyệt và lịch sử triển khai.
- Mỗi build dùng đúng service account.
- Repository connection chỉ có quyền truy cập repository cần thiết.

## 13. Checklist vận hành repository connections và triggers

### Repository connection

- [ ] Đã chọn Developer Connect hoặc Cloud Build repositories thế hệ 2 theo nhu cầu.
- [ ] Connection được tạo ở đúng project và region.
- [ ] Git provider app chỉ có quyền truy cập repository cần thiết.
- [ ] Repository link trỏ tới đúng organization và repository.
- [ ] Quyền quản trị connection được giới hạn theo nhiệm vụ.
- [ ] Đã xác minh webhook/event delivery và trạng thái connection.

### Trigger

- [ ] Trigger có tên, mô tả và owner rõ ràng.
- [ ] Region và repository link tương thích.
- [ ] Event type, branch/tag/PR filters chính xác.
- [ ] Included/ignored files không bỏ sót thay đổi quan trọng.
- [ ] Build config path tồn tại trong commit được chạy.
- [ ] PR, main và release dùng trigger hoặc quyền phù hợp riêng.
- [ ] Approval được bật cho release cần kiểm soát.

### Build identity và secrets

- [ ] Trigger chọn service account có quyền tối thiểu.
- [ ] Người quản lý trigger có quyền actAs đúng service account.
- [ ] Build account chỉ có quyền đọc source, ghi log và tạo artifact cần thiết.
- [ ] PR từ nguồn không tin cậy không có production secret.
- [ ] Secret được lấy từ Secret Manager và chỉ dùng ở step cần thiết.
- [ ] Artifact Registry và dịch vụ deploy giới hạn theo repository/project.

### Theo dõi và kiểm thử

- [ ] Đã thử branch push, tag push và pull request theo cấu hình.
- [ ] Đã kiểm tra build log, commit SHA, substitutions và artifact.
- [ ] Có quy trình xử lý lỗi connection, webhook và permission.
- [ ] Có owner rà soát quyền, token, app installation và trigger định kỳ.
- [ ] Build và release có thể truy vết từ commit tới artifact và môi trường triển khai.

## 14. Sai lầm thường gặp

**Tạo trigger trước khi repository được kết nối.** Trigger cần tham chiếu nguồn code hợp lệ. Hãy hoàn tất host connection và repository link trước.

**Dùng Cloud Source Repositories cho project mới.** CSR không còn khả dụng cho khách hàng mới từ tháng 6-2024. Chọn Git provider hoặc Secure Source Manager phù hợp.

**Nhầm connection với trigger.** Connection chỉ thiết lập tích hợp với Git provider; trigger mới quyết định sự kiện nào khởi chạy build.

**Dùng một service account cho mọi môi trường.** Một build test có thể vô tình kế thừa quyền deploy production. Tách danh tính theo mục đích và môi trường.

**Cho PR build truy cập secret.** Code trong PR có thể thực thi lệnh tùy ý. Dùng build identity hạn chế và không cấp secret production cho PR.

**Đặt filter quá rộng.** Mọi branch hoặc mọi file thay đổi đều có thể kích hoạt build không cần thiết, tăng chi phí và tải pipeline.

**Đặt filter quá hẹp.** Thay đổi shared library hoặc build config có thể không kích hoạt pipeline cần thiết. Kiểm tra các đường dẫn phụ thuộc.

**Giả định trigger tự động chạy đúng region.** Connection, repository link và trigger đều có location. Cần kiểm tra region nhất quán.

**Không kiểm tra default service account.** Cấu hình mặc định có thể khác giữa project. Xác minh danh tính thật của build và thu hẹp quyền.

**Không kiểm tra build log sau khi trigger chạy.** Trigger được kích hoạt không đồng nghĩa build thành công. Cần xem step, quyền, artifact và kết quả cuối.

## 15. Tài liệu tham khảo chính thức

- [Cloud Build repositories](https://cloud.google.com/build/docs/repositories)
- [Cloud Build triggers](https://cloud.google.com/build/docs/triggers)
- [Developer Connect overview](https://cloud.google.com/developer-connect/docs/overview)
- [Git repository connections in Developer Connect](https://cloud.google.com/developer-connect/docs/git-repo-connections)
- [Connect a GitHub repository](https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github)
- [Create and manage build triggers](https://cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Substituting variable values](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Run builds with a user-managed service account](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Default Cloud Build service account](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Cloud Build IAM roles and permissions](https://cloud.google.com/build/docs/iam-roles-permissions)
- [Cloud Source Repositories release notes](https://cloud.google.com/source-repositories/docs/release-notes)

Repository connection tạo đường kết nối có kiểm soát giữa Git provider và Google Cloud; trigger chuyển sự kiện source control thành một build có thể lặp lại. Khi region, event filter, build config, service account và quyền secret được thiết kế rõ ràng, Cloud Build có thể tự động kiểm thử và đóng gói theo commit mà vẫn giữ được khả năng kiểm soát, truy vết và phê duyệt phát hành.
