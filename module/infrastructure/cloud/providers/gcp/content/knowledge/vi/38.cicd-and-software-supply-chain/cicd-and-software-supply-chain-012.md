# Artifact Analysis, SBOM và provenance của bản build

Một bản build chỉ đáng tin khi tổ chức có thể trả lời ba câu hỏi: **artifact chứa những thành phần nào, có lỗ hổng nào cần xử lý, và artifact được tạo ra từ mã nguồn cùng quy trình nào?** Artifact Analysis, Software Bill of Materials (SBOM) và build provenance cung cấp các phần bằng chứng khác nhau để trả lời những câu hỏi đó. Khi kết hợp với attestation và Binary Authorization, nhóm phát triển có thể đặt điều kiện kiểm tra trước khi container được triển khai lên Cloud Run hoặc Google Kubernetes Engine (GKE).

Trong module CLOUD_PROVIDERS_GCP, các năng lực này giúp bảo vệ chuỗi cung ứng phần mềm từ mã nguồn, dependency, quy trình build đến registry và môi trường chạy. Người học cần biết cách quét image trong Artifact Registry, tạo và lưu SBOM, đọc provenance do Cloud Build tạo, xác minh nguồn gốc bằng digest và dùng attestation làm điều kiện triển khai.

Phạm vi module bao gồm tổ chức project, IAM và VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí; bài học này tập trung vào bằng chứng bảo mật của artifact trong quy trình phát hành đó.

Sau bài học, bạn có thể:

- Phân biệt Artifact Analysis, SBOM, vulnerability occurrence, build provenance và attestation.
- Bật quét lỗ hổng cho image trong Artifact Registry và đọc kết quả theo digest.
- Tạo hoặc tải SBOM theo định dạng được hỗ trợ, lưu và truy xuất bằng Google Cloud CLI.
- Cấu hình Cloud Build tạo build provenance và kiểm tra nguồn, builder, build arguments cùng image digest.
- Xác minh provenance theo SLSA bằng công cụ slsa-verifier.
- Dùng Binary Authorization và attestor để chỉ cho phép artifact đáp ứng chính sách được triển khai.

## 1. Bức tranh tổng thể của software supply chain security

Chuỗi cung ứng phần mềm gồm nhiều thành phần: repository mã nguồn, thư viện bên thứ ba, builder, build configuration, artifact registry, quy trình kiểm thử và nền tảng triển khai. Một lỗ hổng hoặc thay đổi trái phép ở bất kỳ khâu nào cũng có thể ảnh hưởng đến artifact cuối cùng.

Các dịch vụ Google Cloud đảm nhiệm những vai trò khác nhau:

| Thành phần | Câu hỏi cần trả lời | Vai trò |
|---|---|---|
| Artifact Registry | Artifact nào được lưu và phân phối? | Lưu container image và package theo phiên bản/tag/digest |
| Artifact Analysis | Artifact có package nào, lỗ hổng nào? | Quét image/package, lưu vulnerability occurrences, metadata và SBOM |
| SBOM | Artifact được cấu thành từ những dependency nào? | Danh mục package, phiên bản, nguồn và thông tin liên quan |
| Cloud Build provenance | Artifact được tạo ra bằng quy trình nào? | Bằng chứng có thể xác minh về source, builder, build definition, tham số và digest |
| Attestation | Điều kiện bảo mật nào đã được xác nhận cho artifact? | Chữ ký xác nhận một hoạt động hoặc kết quả kiểm tra trên digest |
| Binary Authorization | Artifact có đủ điều kiện được triển khai không? | Kiểm tra policy và attestation tại thời điểm deploy |

~~~mermaid
flowchart TD
    SRC["Source repository<br/>commit và dependency"] --> BUILD["Cloud Build<br/>build, test, scan"]
    BUILD --> IMAGE["Container image<br/>immutable digest"]
    BUILD --> PROV["SLSA build provenance"]
    IMAGE --> AR["Artifact Registry"]
    AR --> AA["Artifact Analysis"]
    AA --> VULN["Vulnerability occurrences"]
    AA --> SBOM["SBOM / dependency inventory"]
    BUILD --> TEST["Test và security checks"]
    PROV --> VERIFY["Verify source, builder, digest"]
    TEST --> SIGN["Signer tạo attestation"]
    VERIFY --> SIGN
    SIGN --> ATTEST["Binary Authorization attestor"]
    AR --> DEPLOY["Cloud Run / GKE deployment"]
    ATTEST --> POLICY["Binary Authorization policy"]
    POLICY --> DEPLOY
~~~

Luồng này có thể triển khai theo từng bước. Ban đầu, nhóm có thể bật quét lỗ hổng và tạo SBOM để hiểu thành phần của image. Sau đó bổ sung provenance để xác minh nguồn gốc và builder. Cuối cùng, attestation cùng Binary Authorization biến các kiểm tra thành điều kiện bắt buộc trước khi triển khai.

## 2. Vì sao cần dùng image digest làm định danh?

Container image thường được tham chiếu bằng tag, ví dụ:

~~~text
asia-southeast1-docker.pkg.dev/acme-prod/apps/orders-api:v1.4.0
~~~

Tag là tên dễ đọc và có thể được di chuyển sang image khác. Nếu một người push image mới rồi gắn lại tag v1.4.0, cùng một tag có thể trỏ đến nội dung khác nhau theo thời gian.

Digest xác định nội dung image bằng mã băm SHA-256:

~~~text
asia-southeast1-docker.pkg.dev/acme-prod/apps/orders-api@sha256:0123456789abcdef...
~~~

Khi nội dung image thay đổi, digest cũng thay đổi. Đây là định danh phù hợp để liên kết kết quả quét, SBOM, provenance, attestation và deployment.

**Quy tắc vận hành:** dùng tag để đặt tên và tổ chức release; dùng digest để xác định chính xác artifact được kiểm tra và triển khai.

Ví dụ, pipeline có thể build image với tag theo commit SHA, push lên Artifact Registry, lấy digest do registry trả về rồi truyền digest đó qua các bước:

1. Artifact Analysis quét đúng image digest.
2. SBOM được tạo và gắn với image đó.
3. Provenance xác nhận digest được tạo từ commit và builder mong muốn.
4. Test signer tạo attestation cho chính digest đã qua kiểm tra.
5. Cloud Run hoặc GKE triển khai cùng digest.

Nếu pipeline kiểm tra image theo tag rồi triển khai một tag có thể bị thay đổi, bằng chứng kiểm tra có thể không còn mô tả artifact đang chạy.

## 3. Artifact Analysis và vulnerability scanning

Artifact Analysis là dịch vụ quản lý metadata bảo mật cho artifact. Với container image trong Artifact Registry, dịch vụ có thể quét package hệ điều hành, package ngôn ngữ và phát hiện một số package độc hại được theo dõi công khai.

### 3.1. Bật API và chuẩn bị repository

Các API thường cần cho quy trình container scanning và provenance:

~~~bash
gcloud services enable \
  artifactregistry.googleapis.com \
  containeranalysis.googleapis.com \
  containerscanning.googleapis.com \
  cloudbuild.googleapis.com \
  --project=PROJECT_ID
~~~

Project cần có billing và Docker repository trong Artifact Registry. Image phải được push vào repository tương thích. Danh tính build cần quyền ghi image; danh tính vận hành cần quyền xem metadata và vulnerability occurrences.

Tách quyền theo trách nhiệm:

- Builder được phép build và push artifact vào repository đích.
- Nhóm bảo mật có quyền xem kết quả scan, SBOM và metadata.
- Signer có quyền tạo attestation sau khi kiểm tra đã hoàn tất.
- Deployer có quyền triển khai workload và đọc các policy cần thiết.

Không cấp quyền quản trị toàn project cho mọi pipeline chỉ để đọc kết quả scan hoặc push image.

### 3.2. Automatic scanning và on-demand scanning

Artifact Analysis hỗ trợ hai cách quét chính:

| Cách quét | Thời điểm | Phù hợp khi |
|---|---|---|
| Automatic scanning | Khi image mới được push vào Artifact Registry | Muốn có kết quả ban đầu và tiếp tục theo dõi rủi ro |
| On-demand scanning | Khi pipeline hoặc người vận hành chủ động gọi lệnh quét | Muốn đặt bước kiểm tra tại một thời điểm cụ thể trong CI/CD |

Automatic scanning gồm hai giai đoạn:

- **On-push scanning**: quét image mới và tạo vulnerability occurrences cho package được nhận diện.
- **Continuous analysis**: cập nhật metadata khi nguồn dữ liệu lỗ hổng có thông tin mới, bổ sung hoặc loại bỏ occurrence tương ứng.

Artifact Analysis quét theo image digest. Đổi tag nhưng không đổi nội dung image không tạo một lần quét mới. Kết quả chỉ bao phủ package và lỗ hổng mà dịch vụ có thể nhận diện từ các nguồn dữ liệu được hỗ trợ.

Với image hoặc package không được theo dõi công khai, kết quả không có finding không đồng nghĩa đã chứng minh artifact an toàn tuyệt đối.

### 3.3. Đọc vulnerability occurrences

Artifact Analysis lưu thông tin lỗ hổng dưới dạng note và occurrence. Note mô tả một loại vấn đề, ví dụ CVE; occurrence gắn vấn đề đó với package hoặc image cụ thể.

Có thể liệt kê vulnerability occurrences cho image:

~~~bash
gcloud artifacts docker images list \
  --show-occurrences \
  --occurrence-filter='kind="VULNERABILITY"' \
  --format=json \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE
~~~

Để xem metadata của một image cụ thể theo digest:

~~~bash
gcloud artifacts docker images describe \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST \
  --show-package-vulnerability \
  --format=json
~~~

Kết quả có thể chứa severity, CVE, package name, phiên bản đang cài và phiên bản đã được sửa. Khi phân tích finding, hãy kiểm tra:

- Package có thực sự nằm trong image đang triển khai không?
- Phiên bản bị ảnh hưởng có nằm trong phạm vi của CVE không?
- Có phiên bản cập nhật hoặc bản vá tương thích không?
- Package được dùng ở runtime hay chỉ trong build stage?
- Image đã được build lại sau khi cập nhật dependency chưa?

### 3.4. Continuous analysis không thay thế việc quét lại chủ động

Artifact Analysis tiếp tục cập nhật vulnerability metadata cho image/package được pull trong 30 ngày gần nhất. Sau 30 ngày không được pull, metadata có thể trở nên stale; metadata stale hơn 90 ngày có thể được archive và chỉ truy vấn qua API. Pull lại image có thể kích hoạt quá trình làm mới metadata, nhưng thời gian cập nhật có thể kéo dài đến 24 giờ.

Điều này quan trọng với image cũ đang chạy production nhưng ít được pull. Nhóm vận hành nên có quy trình kiểm tra freshness của kết quả, định kỳ pull/scan image quan trọng và không dùng kết quả cũ như bằng chứng hiện trạng.

## 4. SBOM: danh mục thành phần của artifact

SBOM (Software Bill of Materials) là danh mục máy có thể đọc được, mô tả các package và dependency tạo nên phần mềm. Một SBOM có thể bao gồm:

- Package hệ điều hành như Debian package hoặc Alpine package.
- Thư viện ứng dụng như Maven dependency, npm package, Go module.
- Tên package, phiên bản và nhà cung cấp.
- Quan hệ dependency, thông tin license và nguồn gốc package khi công cụ có thể xác định.

SBOM trả lời câu hỏi **artifact chứa những gì**. Nó hỗ trợ tìm ảnh hưởng khi một dependency có CVE mới, kiểm tra license và đáp ứng yêu cầu kiểm toán. SBOM không tự kết luận package an toàn hay không; cần kết hợp với vulnerability scanning, VEX và chính sách bảo mật.

### 4.1. Định dạng SBOM

Các định dạng thường gặp:

| Định dạng | Đặc điểm |
|---|---|
| SPDX | Chuẩn mô tả package, license, file và quan hệ; Artifact Analysis tạo SBOM theo SPDX 2.3 |
| CycloneDX | Chuẩn SBOM tập trung vào thành phần, dependency và thông tin phục vụ quản lý rủi ro |

Artifact Analysis tạo SBOM theo SPDX 2.3. Khi tải SBOM từ công cụ bên ngoài lên Artifact Analysis, các định dạng JSON được hỗ trợ gồm SPDX 2.2/2.3 và CycloneDX 1.4/1.5. Hãy xác nhận phiên bản định dạng với hệ thống downstream trước khi thiết kế hợp đồng dữ liệu.

### 4.2. Tạo SBOM từ image trong Artifact Registry

Sau khi image được push và Artifact Analysis có metadata package, dùng Google Cloud CLI để xuất SBOM:

~~~bash
gcloud artifacts sbom export \
  --uri=asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
~~~

Artifact Analysis lưu SBOM trong Cloud Storage của project. Nếu chưa có bucket phù hợp ở cùng region với image, dịch vụ có thể tự tạo bucket theo mẫu tên:

~~~text
artifactanalysis-REGION-PROJECT_NUMBER
~~~

Các SBOM khác trong cùng region của project được lưu vào bucket tương ứng. Vì SBOM có thể tiết lộ tên thư viện nội bộ, cấu trúc dependency và thông tin sản phẩm, hãy quản lý quyền truy cập bucket như dữ liệu kỹ thuật quan trọng.

Có thể xem thông tin SBOM reference của image:

~~~bash
gcloud artifacts docker images describe \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST \
  --show-sbom-references \
  --format=json
~~~

SBOM reference occurrence của Artifact Analysis có thể chứa vị trí lưu SBOM, hash của SBOM và chữ ký trên payload tham chiếu. Chữ ký này giúp kiểm tra nguồn tạo SBOM từ Artifact Analysis.

### 4.3. Tải SBOM do công cụ khác tạo lên

Một tổ chức có thể tạo SBOM trong build pipeline bằng Syft, cdxgen hoặc công cụ phù hợp với ngôn ngữ và container build. Sau khi xác nhận file đúng định dạng, tải lên Artifact Analysis:

~~~bash
gcloud artifacts sbom load \
  --source=./orders-api.spdx.json \
  --uri=asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
~~~

Artifact Analysis hỗ trợ SPDX 2.2/2.3 và CycloneDX 1.4/1.5 cho SBOM upload. Tham số uri xác định image mà SBOM mô tả; ưu tiên dùng digest để tránh gắn nhầm SBOM vào image khác.

Nếu muốn dùng bucket riêng, có thể chỉ định --destination. Có thể dùng --kms-key-version để ký payload của SBOM reference occurrence bằng Cloud KMS key version. Thao tác này ký tham chiếu SBOM, không có nghĩa nội dung SBOM đã được đánh giá bảo mật.

### 4.4. Đọc và sử dụng SBOM

SBOM hữu ích khi một CVE mới được công bố. Nhóm bảo mật có thể tìm tất cả artifact có package và phiên bản bị ảnh hưởng, sau đó đối chiếu với image đang chạy.

Ví dụ, khi thư viện Log4j hoặc một package hệ điều hành xuất hiện lỗ hổng:

1. Xác định package và phiên bản bị ảnh hưởng từ advisory.
2. Truy vấn SBOM của các image production.
3. Xác định image digest có chứa package.
4. Đối chiếu vulnerability occurrences để biết mức độ và trạng thái bản vá.
5. Ưu tiên rebuild/redeploy các workload có rủi ro cao.
6. Lưu lại kết quả kiểm tra và image digest đã được thay thế.

SBOM chỉ phản ánh thành phần tại thời điểm tạo. Khi image thay đổi, phải tạo hoặc liên kết SBOM mới với digest mới. Không tái sử dụng SBOM cũ cho image mới chỉ vì tag giống nhau.

## 5. VEX: giải thích khả năng bị ảnh hưởng bởi lỗ hổng

VEX (Vulnerability Exploitability eXchange) là thông tin tư vấn bảo mật cho biết một sản phẩm có bị ảnh hưởng bởi một lỗ hổng đã biết hay không. VEX bổ sung ngữ cảnh mà danh sách CVE đơn thuần chưa thể hiện.

Các trạng thái VEX thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| Not affected | Sản phẩm không bị ảnh hưởng bởi lỗ hổng này |
| Affected | Sản phẩm bị ảnh hưởng; cần hành động khắc phục |
| Fixed | Phiên bản này đã có bản sửa lỗi |
| Under investigation | Đang điều tra và sẽ cập nhật kết luận sau |

Ví dụ, scanner có thể phát hiện một package có CVE nhưng package đó nằm trong module không được bật hoặc đường mã dễ bị ảnh hưởng không thể truy cập trong cấu hình sản phẩm. Nhà phát hành có thể cung cấp VEX để giải thích vì sao artifact không bị ảnh hưởng, kèm bằng chứng và phạm vi áp dụng.

Artifact Analysis hỗ trợ lưu và xem VEX statements; tài liệu hiện hành đánh dấu chức năng này là Preview. Khi dùng VEX, cần:

- Gắn statement với đúng artifact và vulnerability.
- Nêu publisher, căn cứ và phạm vi sản phẩm.
- Chỉ dùng Not affected khi có phân tích kỹ thuật đủ tin cậy.
- Theo dõi thời hạn và cập nhật khi phiên bản hoặc cấu hình sản phẩm thay đổi.

VEX không xóa vulnerability occurrence gốc và không thay thế việc cập nhật package khi có bản vá. Đây là dữ liệu giúp ưu tiên xử lý, tránh kết luận sai từ một finding riêng lẻ.

## 6. Build provenance và SLSA

Build provenance là tập hợp dữ liệu có thể xác minh về quá trình tạo artifact. Với container image, provenance có thể mô tả:

- Image digest được tạo.
- Repository và revision/commit mã nguồn.
- Builder hoặc hệ thống thực thi build.
- Build configuration và build type.
- Tham số đầu vào, dependency đã resolve và thời gian build.
- Build invocation ID để truy vết lần chạy.

Provenance trả lời câu hỏi **artifact được tạo ra như thế nào và từ đâu**. SBOM mô tả thành phần; provenance mô tả quá trình tạo ra artifact đó. Hai loại bằng chứng bổ sung cho nhau.

### 6.1. SLSA là gì?

SLSA (Supply-chain Levels for Software Artifacts) là khung thực hành và mức bảo đảm nhằm cải thiện tính toàn vẹn của chuỗi cung ứng phần mềm. Các mức SLSA mô tả yêu cầu về quy trình build, builder và khả năng chống giả mạo provenance.

Cloud Build hỗ trợ tạo build provenance đạt SLSA Build Level 3 theo các đặc tả SLSA v0.1 và v1.0. Provenance SLSA v1.0 có buildType mô tả template build và nguồn của các tham số. Mức bảo đảm thực tế còn phụ thuộc cách cấu hình builder, source repository, quyền IAM và cách bảo vệ pipeline.

Không nên chỉ nhìn nhãn SLSA rồi kết luận toàn bộ phần mềm an toàn. SLSA provenance giúp tăng khả năng xác minh nguồn gốc và quy trình build; nó không tự chứng minh dependency không có lỗ hổng hoặc test nghiệp vụ đã đầy đủ.

### 6.2. Điều kiện tạo provenance trong Cloud Build

Để Cloud Build tạo provenance cho container image:

1. Bật Cloud Build API, Container Analysis API và Artifact Registry API.
2. Lưu image trong Artifact Registry.
3. Khai báo image trong trường images của build configuration.
4. Bật requestedVerifyOption: VERIFIED để yêu cầu provenance được tạo và kiểm tra có mặt.
5. Không push image bằng một bước docker push tường minh nếu muốn Cloud Build tự tạo provenance theo luồng được tài liệu hướng dẫn.

Ví dụ cloudbuild.yaml:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:$SHORT_SHA
      - .

images:
  - asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:$SHORT_SHA

options:
  requestedVerifyOption: VERIFIED
~~~

Trường images yêu cầu Cloud Build lưu image đã build vào Artifact Registry sau khi build hoàn tất. requestedVerifyOption: VERIFIED bật việc tạo provenance và kiểm tra metadata đã được sinh. Build chỉ được đánh dấu thành công khi provenance được tạo theo yêu cầu.

Chạy build:

~~~bash
gcloud builds submit \
  --project=PROJECT_ID \
  --config=cloudbuild.yaml \
  .
~~~

Cloud Build provenance cho container chỉ được tạo cho artifact lưu trong Artifact Registry. Với ứng dụng không phải container, Cloud Build cũng hỗ trợ provenance cho một số artifact độc lập như Go, Java Maven, Python và Node.js npm khi upload artifact lên Artifact Registry.

### 6.3. Xem provenance theo image digest

Sau build, ghi nhận digest từ output hoặc Artifact Registry. Truy vấn provenance:

~~~bash
gcloud artifacts docker images describe \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST \
  --show-provenance \
  --format=json
~~~

Kết quả có thể chứa:

- fully_qualified_digest của image.
- buildType và predicate của SLSA provenance.
- Source repository, branch và commit SHA.
- Build ID và trigger.
- Builder ID.
- Dependency đã resolve và digest của builder image.
- Thời điểm bắt đầu/kết thúc build.

Có thể dùng Security insights trong Cloud Build Build History hoặc Artifact Registry để xem thông tin tổng hợp về build, dependency, SBOM, vulnerability và provenance.

### 6.4. Xác minh provenance bằng SLSA verifier

Đọc JSON provenance chưa đủ để xác nhận dữ liệu không bị giả mạo. Cần xác minh chữ ký, builder và source theo chính sách tin cậy.

SLSA verifier là công cụ mã nguồn mở để kiểm tra provenance. Tài liệu Google Cloud hướng dẫn dùng phiên bản 2.1 trở lên.

Cài công cụ theo hướng dẫn của dự án slsa-verifier, sau đó lấy provenance của image theo digest:

~~~bash
export IMAGE="asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST"

gcloud artifacts docker images describe "$IMAGE" \
  --format=json \
  --show-provenance > provenance.json
~~~

Xác minh provenance:

~~~bash
slsa-verifier verify-image "$IMAGE" \
  --provenance-path provenance.json \
  --source-uri "github.com/ORG/REPOSITORY" \
  --builder-id="https://cloudbuild.googleapis.com/GoogleHostedWorker"
~~~

Thay source URI bằng repository thực tế và builder ID bằng builder được tổ chức cho phép. Kết quả PASSED cho biết provenance đáp ứng các điều kiện xác minh đã cung cấp. Nếu source hoặc builder không đúng, verifier sẽ báo lỗi.

Khi thiết kế policy, hãy xác định rõ:

- Repository nào được phép làm source.
- Branch/tag/revision nào được phép build.
- Builder ID nào được tin cậy.
- Build definition và tham số nào được phép.
- Image digest có trùng với artifact chuẩn bị triển khai không.

## 7. Attestation và Binary Authorization

Provenance cho biết quá trình build. Attestation thường xác nhận một điều kiện hoặc hoạt động đã được thực hiện trên một artifact, ví dụ:

- Image đã vượt qua regression test.
- Vulnerability scan không vượt ngưỡng policy.
- License review đã được hoàn tất.
- Artifact đã được nhóm bảo mật phê duyệt.
- Image được tạo bởi một builder nằm trong danh sách tin cậy.

Attestation được tạo bằng cách ký image digest. Vì chữ ký gắn với digest, thay đổi nội dung image sẽ tạo digest khác và không thể dùng lại attestation của image cũ.

### 7.1. Thành phần của Binary Authorization

| Thành phần | Vai trò |
|---|---|
| Attestation | Bằng chứng đã ký gắn với image digest |
| Signer | Danh tính hoặc dịch vụ tạo chữ ký |
| Attestor | Định nghĩa bên xác minh chữ ký và attestation |
| Policy | Quy tắc yêu cầu attestor hoặc cho phép/exempt image |
| Deployer | Nền tảng triển khai gọi kiểm tra policy |

Binary Authorization có thể kiểm tra attestation tại thời điểm triển khai. Nếu image không có attestation từ attestor bắt buộc hoặc chữ ký không hợp lệ, deployment bị từ chối theo policy.

Cloud Build có attestor built-by-cloud-build cho tình huống chỉ muốn triển khai image được tạo bởi Cloud Build. Với quy trình riêng, tổ chức có thể tạo attestor và signer cho các điều kiện kiểm tra của mình.

### 7.2. Luồng attestation sau kiểm thử

Một pipeline có thể thực hiện:

1. Build image và lấy digest.
2. Chờ Artifact Analysis hoàn thành scan.
3. Đánh giá findings theo policy.
4. Tạo SBOM và xác minh provenance.
5. Chạy test và policy checks.
6. Nếu tất cả điều kiện đạt, signer tạo attestation cho digest.
7. Binary Authorization kiểm tra attestation khi deploy.

~~~mermaid
sequenceDiagram
    participant CB as Cloud Build
    participant AR as Artifact Registry
    participant AA as Artifact Analysis
    participant QA as Test / Security gate
    participant SG as Attestation signer
    participant BA as Binary Authorization
    participant CR as Cloud Run hoặc GKE

    CB->>AR: Push image và tạo provenance
    AR->>AA: Image digest mới
    AA-->>QA: Vulnerability findings và SBOM
    CB-->>QA: Build provenance
    QA->>QA: Kiểm tra test, CVE, license, source
    QA->>SG: Yêu cầu ký digest nếu đạt
    SG->>AR: Ghi attestation cho digest
    CR->>BA: Yêu cầu kiểm tra image
    BA->>AR: Tìm attestation và xác minh chữ ký
    BA-->>CR: Allow hoặc deny deployment
~~~

Tách quyền signer khỏi quyền build thông thường giúp giảm nguy cơ một build step bị xâm nhập tự ký artifact của chính nó. Signer nên nhận kết quả đã được xác minh từ pipeline có kiểm soát và chỉ ký digest đã đạt điều kiện.

### 7.3. Áp dụng policy cho Cloud Run và GKE

Binary Authorization hỗ trợ policy cho GKE và Cloud Run. Với Cloud Run service, policy được kiểm tra khi triển khai revision mới. Nếu revision không đáp ứng policy, deployment thất bại; revision đang phục vụ trước đó vẫn tiếp tục phục vụ theo trạng thái hiện tại.

Với Cloud Run job, policy được kiểm tra khi thực thi job. Một job có thể cập nhật cấu hình nhưng lần thực thi sẽ thất bại nếu image không đáp ứng policy.

Nếu có tình huống khẩn cấp cần bypass policy, Cloud Run hỗ trợ breakglass. Đây là ngoại lệ có chủ đích và được ghi nhận trong Cloud Audit Logs; chỉ dùng theo quy trình khẩn cấp, có người phê duyệt và có bước khắc phục sau đó.

Không nhầm Binary Authorization với vulnerability scanner. Scanner tạo metadata về lỗ hổng; Binary Authorization kiểm tra policy và attestation. Muốn chặn image có CVE, pipeline phải biến kết quả scan thành điều kiện đạt/không đạt và chỉ tạo attestation khi policy được đáp ứng.

## 8. Xây dựng policy kiểm tra trong CI/CD

Một policy thực tế nên chia điều kiện thành các nhóm:

| Nhóm | Ví dụ điều kiện | Bằng chứng |
|---|---|---|
| Nguồn gốc | Build từ repository và branch được phép | Build provenance |
| Builder | Dùng Cloud Build worker đã tin cậy | Builder ID trong provenance |
| Thành phần | SBOM được tạo và gắn đúng digest | SBOM reference |
| Lỗ hổng | Không có Critical hoặc High chưa được chấp thuận | Vulnerability occurrences và VEX |
| Kiểm thử | Unit, integration và security tests đã đạt | CI test result / attestation |
| Phê duyệt | Release production được người có thẩm quyền duyệt | Approval record / attestation |

Ví dụ policy đơn giản:

- Critical vulnerability: chặn release ngay, trừ khi có ngoại lệ được phê duyệt và ghi nhận.
- High vulnerability: yêu cầu bản vá hoặc VEX có căn cứ.
- Medium/Low: tạo backlog với thời hạn xử lý.
- Provenance không hợp lệ: chặn deployment.
- SBOM thiếu hoặc không khớp digest: chặn promotion.
- Không có attestation từ signer tin cậy: Binary Authorization từ chối deploy.

Ngưỡng severity chỉ là ví dụ. Tổ chức cần đánh giá khả năng khai thác, mức độ phơi nhiễm, dữ liệu xử lý, môi trường và thời gian khắc phục. Không nên chỉ dựa vào điểm CVSS mà bỏ qua exploitability và bối cảnh runtime.

## 9. Tình huống thực tế: bảo vệ Orders API

Giả sử nhóm phát triển triển khai Orders API dưới dạng container lên Cloud Run. Họ muốn chứng minh image được build từ repository chính thức, biết dependency bên trong và chặn image chưa qua kiểm tra.

Quy trình:

1. Cloud Build lấy commit đã được review.
2. Build image với tag theo commit SHA và lưu vào Artifact Registry.
3. Cloud Build tạo provenance có source commit, builder, build configuration và digest.
4. Artifact Analysis quét image, tạo vulnerability occurrences và cung cấp dependency metadata.
5. Pipeline xuất SBOM SPDX 2.3 gắn với digest.
6. SLSA verifier xác minh source repository và builder ID.
7. Test stage chạy regression/security test.
8. Policy gate đánh giá CVE và license. Nếu có finding được chấp thuận là không ảnh hưởng, lưu VEX hoặc hồ sơ ngoại lệ.
9. Signer tạo attestation cho digest sau khi mọi gate đạt.
10. Cloud Run Binary Authorization kiểm tra attestation trước khi nhận revision mới.

Khi phát hiện một CVE mới sau khi image đã chạy production, nhóm vận hành dùng SBOM để tìm image có package bị ảnh hưởng, dùng Artifact Analysis để xem occurrence và severity, sau đó build image mới đã cập nhật dependency. Provenance và attestation mới phải được tạo cho digest mới trước khi deploy.

Luồng này giúp nhóm trả lời được ba câu hỏi trong một sự cố: image nào đang bị ảnh hưởng, nó chứa dependency nào, và nó được build từ commit/builder nào.

## 10. Quản trị quyền, lưu giữ và kiểm toán

### 10.1. IAM theo trách nhiệm

Một số vai trò thường gặp trong quy trình:

- Builder: đọc source, chạy build và ghi image vào Artifact Registry.
- Artifact reader: đọc image, SBOM, provenance và vulnerability occurrences.
- Security reviewer: xem findings, đánh giá VEX và phê duyệt ngoại lệ.
- Signer: ký digest và tạo attestation.
- Deployer: triển khai image đã được policy chấp nhận.

Quyền đọc artifact và quyền ghi artifact cần tách biệt. Quyền tạo attestation nên được giới hạn chặt vì signer là một phần của ranh giới tin cậy. Quyền chỉnh sửa Binary Authorization policy cũng cần dành cho nhóm quản trị nền tảng/bảo mật.

### 10.2. Lưu giữ bằng chứng

Artifact Registry cleanup policy có thể xóa image cũ. Provenance và SBOM có thể được lưu dưới dạng attachment hoặc object trong Cloud Storage; vòng đời của chúng có thể khác nhau.

Cloud Build provenance attachment không chịu cleanup policy của Artifact Registry theo cách thông thường; attachment được xóa khi image mà nó gắn vào bị xóa. SBOM do Artifact Analysis tạo được lưu trong Cloud Storage cho đến khi object hoặc bucket bị xóa.

Đối với kiểm toán, cần xác định thời hạn lưu giữ riêng cho:

- Image digest và tag release.
- SBOM, provenance và attestation.
- Build logs và test reports.
- Vulnerability findings, VEX và hồ sơ ngoại lệ.
- Cloud Audit Logs cho hành động deploy và breakglass.

Không nên xóa image chỉ để giảm dung lượng trước khi xác định các bằng chứng liên quan có cần lưu theo chính sách tuân thủ hay không.

### 10.3. Chi phí và hiệu năng

Chi phí có thể phát sinh từ Artifact Analysis scanning, Cloud Storage chứa SBOM, Artifact Registry storage, Cloud Build execution và log retention.

Để kiểm soát:

- Chọn repository và image cần quét theo mức độ quan trọng.
- Loại bỏ package thừa và tối ưu multi-stage Docker build.
- Dùng digest để tránh kiểm tra lặp do tag thay đổi.
- Thiết kế retention phù hợp cho image và bằng chứng.
- Theo dõi lượng scan, storage và build time.
- Không bỏ qua continuous analysis đối với image production chỉ vì đã scan ở thời điểm build.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy vulnerability findings | Scan chưa hoàn tất, API chưa bật hoặc image không có package được hỗ trợ | Kiểm tra Artifact Analysis API, repository, digest và trạng thái scan |
| Đổi tag nhưng không có lần scan mới | Scan được tính theo image digest | Xác nhận tag có trỏ tới digest mới hay không |
| Vulnerability metadata stale | Image không được pull trong thời gian dài | Pull image và chờ metadata được cập nhật; kiểm tra trạng thái freshness |
| Không xuất được SBOM | Image chưa có package metadata hoặc thiếu API/quyền Cloud Storage | Kiểm tra scan, Container Analysis API, Container Scanning API và quyền lưu SBOM |
| SBOM gắn sai image | Dùng tag bị di chuyển hoặc URI sai | Dùng image digest khi export/upload và xác minh SBOM reference |
| Cloud Build không tạo provenance | Thiếu images field, thiếu requestedVerifyOption hoặc dùng docker push thủ công | Dùng images field, đặt VERIFIED và để Cloud Build lưu image theo luồng hỗ trợ |
| Provenance không hiển thị | Artifact không lưu trong Artifact Registry hoặc truy vấn sai digest | Kiểm tra registry, image digest và quyền đọc metadata |
| SLSA verifier báo sai source | Source URI trong lệnh không khớp provenance | Kiểm tra repository URI, commit và builder ID được phép |
| Binary Authorization từ chối deploy | Thiếu attestation hoặc chữ ký không được attestor tin cậy | Kiểm tra digest, attestor, public key, policy và quyền truy cập |
| Cloud Run revision deploy thất bại | Image không đáp ứng Binary Authorization policy | Xem lỗi policy và attestation; chỉ dùng breakglass theo quy trình khẩn cấp |
| Không tìm được SBOM cũ | Object hoặc bucket Cloud Storage đã bị xóa | Kiểm tra retention, audit log và chính sách lưu trữ bằng chứng |

## 12. Checklist triển khai production

- [ ] Container image được lưu trong Artifact Registry và được định danh bằng digest.
- [ ] Artifact Analysis API và Container Scanning API được bật theo phạm vi cần dùng.
- [ ] Kết quả vulnerability scan đã hoàn tất và có trạng thái freshness rõ ràng.
- [ ] Vulnerability findings được đánh giá theo severity, exploitability và môi trường runtime.
- [ ] SBOM được tạo hoặc upload đúng định dạng, gắn với đúng image digest.
- [ ] SBOM được lưu trong Cloud Storage với IAM và retention phù hợp.
- [ ] Cloud Build dùng images field và requestedVerifyOption: VERIFIED để tạo provenance.
- [ ] Provenance được kiểm tra source repository, commit, builder và build parameters.
- [ ] SLSA verifier hoặc cơ chế tương đương xác minh provenance trước promotion.
- [ ] Attestation được ký cho digest đã qua test và policy checks.
- [ ] Signer có danh tính và quyền riêng, không chia sẻ quyền ký với builder không đáng tin.
- [ ] Binary Authorization policy được cấu hình cho Cloud Run hoặc GKE.
- [ ] Breakglass có quy trình phê duyệt, audit và khắc phục.
- [ ] Build logs, SBOM, provenance, attestation và hồ sơ ngoại lệ có retention phù hợp.
- [ ] Có quy trình tìm và rebuild tất cả image bị ảnh hưởng khi CVE mới xuất hiện.

## 13. Câu hỏi tự kiểm tra

**1. Artifact Analysis và Artifact Registry khác nhau thế nào?**

Artifact Registry lưu trữ và phân phối artifact. Artifact Analysis quét và quản lý metadata bảo mật như vulnerability occurrences, package information, SBOM và một số loại attestation/metadata.

**2. SBOM và build provenance cung cấp hai loại thông tin nào?**

SBOM mô tả các thành phần và dependency của artifact. Build provenance mô tả nguồn mã, builder, build definition, tham số và digest của artifact được tạo ra.

**3. Vì sao nên gắn SBOM, provenance và attestation với image digest?**

Digest xác định nội dung image cụ thể. Tag có thể thay đổi, còn digest giúp bảo đảm mọi bằng chứng đang mô tả đúng artifact được kiểm tra và triển khai.

**4. Cloud Build cần cấu hình gì để tạo provenance cho container image?**

Lưu image vào Artifact Registry bằng trường images trong build config và đặt options.requestedVerifyOption thành VERIFIED. Không dùng bước docker push thủ công theo luồng tạo provenance được hướng dẫn.

**5. SLSA verifier kiểm tra điều gì?**

Công cụ xác minh provenance của image, bao gồm tính hợp lệ của bằng chứng build và các điều kiện source URI, builder ID mà người vận hành yêu cầu.

**6. Binary Authorization dùng attestation như thế nào?**

Attestation xác nhận một hoạt động đã hoàn tất trên image digest. Binary Authorization kiểm tra chữ ký qua attestor và so với policy trước khi cho phép triển khai.

**7. Nếu scanner không tìm thấy lỗ hổng thì có thể kết luận image an toàn tuyệt đối không?**

Không. Kết quả chỉ phản ánh package và lỗ hổng được nguồn dữ liệu cùng scanner hỗ trợ tại thời điểm kiểm tra. Cần kết hợp SBOM, provenance, test, policy và theo dõi liên tục.

## 14. Tài liệu tham khảo

- [Artifact Analysis overview](https://cloud.google.com/artifact-analysis/docs/overview)
- [Artifact Analysis: types of scanning](https://cloud.google.com/artifact-analysis/docs/scanning-types)
- [Get started with Artifact Analysis scanning](https://cloud.google.com/artifact-analysis/docs/get-started-scanning)
- [SBOM overview](https://cloud.google.com/artifact-analysis/docs/sbom-overview)
- [Generate and store SBOMs](https://cloud.google.com/artifact-analysis/docs/generate-store-sboms)
- [Upload SBOMs](https://cloud.google.com/artifact-analysis/docs/upload-sboms)
- [Create VEX statements](https://cloud.google.com/artifact-analysis/docs/create-vex)
- [Generate and validate build provenance](https://cloud.google.com/build/docs/securing-builds/generate-validate-build-provenance)
- [View build security insights](https://cloud.google.com/build/docs/view-build-security-insights)
- [Binary Authorization attestations overview](https://cloud.google.com/binary-authorization/docs/attestations)
- [Create Binary Authorization attestations](https://cloud.google.com/binary-authorization/docs/making-attestations)
- [Binary Authorization for Cloud Run](https://cloud.google.com/binary-authorization/docs/run/overview)
- [SLSA specification](https://slsa.dev/spec/v1.0/)

