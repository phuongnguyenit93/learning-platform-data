# Quét image và phân quyền truy cập Amazon ECR

Một ứng dụng Java/Spring Boot được đóng gói thành container image thường chứa hệ điều hành nền, Java Runtime, thư viện Maven/Gradle, mã ứng dụng và cấu hình triển khai. Image có thể chạy tốt trên máy phát triển nhưng vẫn chứa **lỗ hổng bảo mật đã được công bố (CVE)** hoặc bị phát hành tới môi trường production từ một nguồn không đáng tin cậy. Khi triển khai container trên **Amazon Elastic Container Service (Amazon ECS)**, hai câu hỏi phải được giải quyết song song:

1. **Image có được kiểm tra và xử lý các lỗ hổng cần thiết trước/sau khi phát hành không?**
2. **Ai được đẩy image, ai được tải image và ECS có dùng đúng danh tính để tải từ registry không?**

**Amazon Elastic Container Registry (Amazon ECR)** là dịch vụ registry quản lý container images và artifacts. Với private repositories, ECR tích hợp với IAM, repository policies, image scanning và nhiều dịch vụ AWS như ECS, Amazon Inspector, EventBridge, CloudTrail. Một image được scan thành công **không tự trở thành an toàn tuyệt đối**, cũng như việc đăng nhập registry thành công **không tự cấp quyền push/pull cho mọi repository**.

Bài học thuộc chương **Container với ECS** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn với thiết kế ứng dụng an toàn trên Region/AZ và VPC, IAM roles, EC2/Fargate, S3-backed image layers, CI/CD, giám sát sự cố, tính sẵn sàng và kiểm soát chi phí.

> **Nguyên tắc:** Build một lần, quét image, lưu trữ theo **digest**, phát hành bằng IAM role đúng quyền, giám sát CVE mới và cập nhật image định kỳ. Quyền **kéo image cho ECS runtime** khác với quyền **truy cập AWS APIs trong mã ứng dụng**.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích quan hệ giữa ECR private registry, repository, image tag và image digest.
2. Phân biệt **Basic scanning** và **Enhanced scanning (Amazon Inspector)**, chế độ manual, scan on push và continuous.
3. Đọc và đánh giá scan status, severity, CVE, affected package và khả năng có bản vá.
4. Biết vì sao `DescribeImageScanFindings` là API phù hợp để xem kết quả scan, kể cả với Basic scanning mới.
5. Mô tả quyền cần thiết khi push và pull image, gồm `ecr:GetAuthorizationToken`, quyền trên repository và repository resource policy.
6. Phân biệt **ECS task execution role**, **ECS task role** và **container instance IAM role** theo launch type.
7. Thiết kế quyền truy cập ECR cross-account và đường mạng private subnet qua ECR VPC endpoints/S3 Gateway Endpoint.
8. Xây pipeline build–scan–approve–deploy có gate bảo mật, rollback và giám sát lỗ hổng mới.
9. Kiểm tra repository, image digest, scanning configuration, findings và policy qua AWS CLI mà không thay đổi tài nguyên.

## 2. Vị trí của ECR trong hệ sinh thái ECS

Một hệ thống có thể chạy chuỗi:

~~~mermaid
flowchart LR
    D["Developer / Git repository"] --> CI["CI: build và test"]
    CI --> SB["Kiểm tra thư viện, secrets, SBOM"]
    SB --> ECR["Amazon ECR private repository"]
    ECR --> SC["Basic scan hoặc Amazon Inspector"]
    SC --> G["Security gate / quyết định phát hành"]
    G --> TD["ECS task definition: image digest"]
    TD --> ECS["ECS service trên Fargate/EC2"]
    ECS --> ALB["ALB + Route 53 / CloudFront"]
    ECR --> EB["EventBridge / findings mới"]
    EB --> SEC["Security triage / rebuild / patch"]
~~~

**ECR lưu image**, **ECS chạy task/service**, **IAM kiểm soát truy cập**, còn **Amazon Inspector** cung cấp phân tích lỗ hổng nâng cao. Để một task tải image, cần ba điều độc lập: image có tồn tại trong repository/Region, runtime có IAM permissions, và task có **network path hợp lệ** tới ECR cùng kho layer liên quan.

### 2.1. Registry, repository, tag và digest

Một ECR private registry gắn với **AWS account và Region**; mỗi registry có nhiều repositories. Ví dụ:

~~~text
111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
|---------- registry endpoint -----------------| |----- repo -------| |tag|
~~~

- `111122223333`: AWS account **minh họa** sở hữu registry.
- `ap-southeast-1`: Region của ECR repository.
- `platform/orders-api`: tên repository, không phải thư mục trên EC2.
- `1.2.3`: **image tag**, một nhãn có thể bị gán lại nếu repository cho phép mutable tags.
- `sha256:...`: **image digest**, định danh nội dung manifest; phù hợp để gắn chính xác bản image đã được quét/duyệt.

**Tag khác digest.** Nếu tag `stable` được chuyển sang một image khác, quá trình deploy đọc tag ở hai thời điểm có thể cho nội dung khác nhau. Khi cần provenance và tính tái hiện, nên pin image bằng **digest**, hoặc kiểm soát chặt tag immutability và lưu digest tại thời điểm duyệt.

### 2.2. Private và public ECR

Bài này tập trung **Amazon ECR private repositories** dùng với ECS. Amazon ECR Public có endpoint và thao tác IAM riêng (ví dụ tiền tố `ecr-public:`) và cách chia sẻ image khác. Không sao chép chính sách ECR private sang ECR Public mà không kiểm tra tên action/registry tương ứng.

## 3. Vì sao phải quét container image?

Một image Java có thể gồm:

- **Base image**: ví dụ phân phối Linux, gói OpenSSL, libc, curl, shell.
- **Java runtime**: JRE/JDK, CA certificates, thư viện hệ thống.
- **Dependencies**: Spring Boot, Spring Framework, Jackson, Netty và thư viện transitives trong JAR.
- **Application code**: logic nghiệp vụ, cấu hình, endpoints.
- **Artifacts**: file cấu hình, scripts và đôi khi secrets bị thêm vào image nhầm.

Một bản phát hành mới có thể vá CVE trong image base, nhưng lại thêm lỗ hổng mới từ dependency. Ngược lại, **CVE có thể được công bố sau khi image đã deploy**; scan một lần tại thời điểm build không đủ để bảo đảm an toàn về sau.

### 3.1. Các lớp bảo vệ và giới hạn

| Cơ chế | Phát hiện/ngăn điều gì? | Không thay thế điều gì? |
|---|---|---|
| ECR **Basic scanning** | Một số CVE trong gói hệ điều hành được hỗ trợ | Quét đầy đủ mọi thư viện Java, cấu hình runtime và logic bảo mật |
| ECR **Enhanced scanning** | CVE của hệ điều hành và nhiều gói ngôn ngữ được Amazon Inspector hỗ trợ | Pentest, kiểm thử API, secrets detection toàn diện |
| SBOM/dependency scanner ở CI | Gói/phụ thuộc và policy supply chain | Quyền IAM và network security khi chạy |
| Image signing/attestation | Nguồn gốc và tính toàn vẹn theo chính sách ký/xác minh | Tự động vá vulnerability |
| IAM/repository policy | Ai được push/pull/quản lý image | Image không có CVE hoặc cấu hình ứng dụng an toàn |
| ECS runtime/OS hardening | Giới hạn quyền tiến trình, network, secrets, filesystem | Kiểm thử mã ứng dụng |

Một kết quả **0 Critical findings** không chứng minh “image hoàn toàn không có lỗ hổng”. Có thể do scanner không hỗ trợ OS/package, đang pending, image đã archived, không có data feed phù hợp, scan scope thiếu hoặc findings chưa cập nhật.

## 4. Basic scanning và Enhanced scanning

Tại thời điểm tài liệu AWS hiện hành, ECR cung cấp hai loại scanning cho **private registry**:

| Thuộc tính | **Basic scanning** | **Enhanced scanning** |
|---|---|---|
| Công nghệ | AWS native scanning | Tích hợp **Amazon Inspector** |
| Loại phát hiện chính | CVE trong **OS packages** | CVE của **OS và programming-language packages** được hỗ trợ |
| Chế độ | **Manual** hoặc **Scan on push** | **Scan on push** hoặc **Continuous scanning** |
| Khi có CVE mới sau lúc push | Không tự tái đánh giá liên tục | **Continuous** có thể theo dõi và cập nhật findings khi có CVE liên quan |
| Manual scan | Có, khi Basic scanning cho phép | **Không** có manual enhanced scan theo ECR |
| Phạm vi cấu hình | **Registry scanning configuration**, filters theo repository trong Region | **Registry scanning configuration**, Inspector activation và filters trong Region |
| Kết quả | ECR `DescribeImageScanFindings` | ECR findings và chi tiết sâu hơn ở Amazon Inspector |
| Chi phí | Theo chính sách giá/quota Basic hiện hành | Có thể phát sinh phí Amazon Inspector scanning/monitoring |

### 4.1. Basic scanning mặc định không có nghĩa mọi push đều được scan

**Basic scanning được bật mặc định cho private registry**, nhưng các repositories **không khớp scan-on-push filter** thường ở chế độ **manual**, tức là phải chủ động bắt đầu scan mới được quét. Nếu muốn scan tự động mỗi khi push image, quản trị viên cần bật **scan on push** cho những repositories phù hợp hoặc cho toàn registry bằng quy tắc scanning.

Với Basic scanning, AWS giới hạn tần suất scan của mỗi image và quota toàn registry theo tài liệu; không thiết kế CI gọi manual scan lặp vô hạn nếu scan đã diễn ra gần đây. Basic scanning có thể không hỗ trợ một số OS hoặc image format.

### 4.2. Enhanced scanning và Amazon Inspector

Enhanced scanning yêu cầu bật tích hợp Amazon Inspector cho registry trong Region. Amazon Inspector có thể:

1. Quét lần đầu image mới được push vào repository thuộc phạm vi filter.
2. Đọc vulnerability data của OS và các gói thư viện ngôn ngữ được hỗ trợ.
3. Phát hiện/cập nhật findings khi cơ sở dữ liệu CVE có thông tin mới đối với **continuous scanning** và image còn trong thời gian giám sát.
4. Gửi các sự kiện scan/finding tới **EventBridge** để hệ thống triage, ticket hoặc notification xử lý.

Amazon Inspector sử dụng **service-linked role** khi được kích hoạt. Trong **Enhanced scanning**, repository **không khớp filter nào** có thể ở trạng thái **Off**; khi cùng repository khớp filter continuous và scan-on-push, **continuous ưu tiên**. Không coi việc bật Enhanced ở account là tự động quét mọi repository.

### 4.3. Khoảng thời gian đủ điều kiện và ảnh hưởng khi đổi scan type

Khi lần đầu bật Enhanced, AWS có quy tắc eligibility cho image cũ; tài liệu AWS nêu Inspector ban đầu nhận diện những image được push trong **14 ngày gần nhất**. Image quá cũ có thể nhận `SCAN_ELIGIBILITY_EXPIRED` và cần push lại để được quét trong phạm vi áp dụng. Thời gian re-scan/monitoring có thể được cấu hình theo chính sách Inspector.

Đổi giữa **Basic** và **Enhanced** làm thay đổi tính sẵn có của các scan đã được thực hiện; nếu chuyển lại kiểu trước có thể xem lại scan cũ. **Không chuyển scan type trong production tùy tiện** để lấy một kết quả từ CLI: đây là cấu hình **registry-level trong một Region**, ảnh hưởng nhiều repositories.

**Archived images không được quét** trong trạng thái archived; cần restore trước khi thực hiện scanning theo điều kiện hỗ trợ.

## 5. Đọc vulnerability findings đúng cách

Một finding có thể có các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| **CVE** | Mã lỗ hổng trong cơ sở dữ liệu, ví dụ `CVE-20XX-XXXXX` |
| **Severity** | Mức độ do scanner/provider đánh giá, như `CRITICAL`, `HIGH`, `MEDIUM` |
| **Affected package/version** | Gói hệ điều hành hoặc thư viện nằm trong phạm vi ảnh hưởng |
| **Fixed version / remediation** | Phiên bản khắc phục hoặc khuyến nghị nếu nhà cung cấp đã phát hành |
| **Image digest** | Bản image cụ thể bị ảnh hưởng |
| **Status/time** | Trạng thái quét/finding và thời điểm cập nhật |
| **Inspector risk context** | Thông tin ưu tiên xử lý theo dữ liệu khai thác/ngữ cảnh khi khả dụng |

### 5.1. Severity không phải là toàn bộ quyết định release

Ví dụ một image có `CRITICAL` trong gói OS nhưng app không dùng code path đó, còn một `HIGH` trong thư viện web xử lý dữ liệu đầu vào trực tiếp. Nhóm bảo mật cần xem:

- Khả năng khai thác và bề mặt exposure thực tế.
- Gói đang được sử dụng và image có chứa mã vulnerable hay không.
- Đã có bản vá hay chưa.
- Dữ liệu xử lý, quyền runtime và network reachability.
- Deadline vá theo chính sách doanh nghiệp, exception có owner/expiry.

Không tự động bỏ qua mọi `MEDIUM` hoặc chặn mọi image mãi mãi chỉ vì một CVE chưa có bản vá. Cần **policy triage minh bạch, có thời hạn xử lý và ngoại lệ được phê duyệt**.

### 5.2. CVE mới xuất hiện sau khi ECS đã chạy

Nếu tag/digest đã triển khai hôm qua và hôm nay được công bố CVE mới, **continuous Enhanced scanning** có thể cập nhật finding, nhưng nó **không tự rebuild, vá image hoặc restart ECS service**. Quy trình chuẩn là cập nhật base image/dependency → rebuild → scan lại → deploy image digest mới → quan sát health → rollback nếu cần.

## 6. Cấu hình scanning trong ECR Console

### 6.1. Xác nhận Registry và Region

1. Đăng nhập AWS Console đúng account/role, ưu tiên IAM Identity Center và MFA.
2. Mở **Amazon ECR → Private registry → Scanning**.
3. Chọn **Region** chứa repository mục tiêu; scanning configuration được quản lý ở cấp registry/Region.
4. Kiểm tra **scan type** hiện tại: Basic hoặc Enhanced.
5. Kiểm tra các **repository filters** và scan frequency trước khi kết luận image sẽ được scan lúc push.
6. Đối với Enhanced, kiểm tra Amazon Inspector đã được bật và có coverage/eligibility.

### 6.2. Cấu hình ví dụ theo môi trường

| Loại repository | Tùy chọn gợi ý | Lý do |
|---|---|---|
| `dev/*` nhiều image ngắn hạn | Basic scan-on-push hoặc Enhanced theo mức rủi ro | Phát hiện sớm, kiểm soát khối lượng scan |
| `staging/*` | Enhanced scan-on-push | Quét gói OS và ngôn ngữ trước promotion |
| `production/*` | Enhanced **continuous** | Theo dõi CVE xuất hiện sau triển khai |
| Image archive không deploy | Lifecycle/archiving theo policy | Tối ưu lưu trữ và phạm vi theo dõi; archived images không scan được |

Đây chỉ là **phương án khởi đầu**. Tổ chức có thể dùng một repository cho nhiều môi trường và promotion theo digest; trong trường hợp đó, chọn filter không thể dựa đơn giản vào tên `dev/*`, `production/*`.

### 6.3. Đọc kết quả scan trong Console

Vào **ECR → Private repositories → chọn repository → Images**, tìm image theo **digest hoặc tag**. Mở image details để xem scan findings, vulnerability severity, scan status. Với Enhanced scanning, liên kết từ finding có thể dẫn tới **Amazon Inspector** để xem affected packages và context.

Không nhầm **image pushed** với **image scan completed**. Vì scan là xử lý bất đồng bộ, một pipeline phải **đợi trạng thái quét hợp lệ** trước khi ra quyết định release. Nếu scan status là unsupported/expired/pending/failed, không được coi đó là “không có CVE”.

## 7. AWS CLI: kiểm tra scanning configuration và findings an toàn

Các lệnh bên dưới **chỉ đọc**, giả định:

- Account nguồn ECR: `111122223333` (**minh họa**).
- Region: `ap-southeast-1`.
- Repository: `platform/orders-api`.
- Image tag: `1.2.3`.
- Profile AWS CLI `dev` đã có quyền phù hợp.

### 7.1. Xác nhận caller trước

~~~bash
aws --version
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Nếu account ID không như dự kiến, **không tiếp tục sửa cấu hình ECR hoặc deploy**. Một account có thể có repository cùng tên nhưng chứa image hoàn toàn khác.

### 7.2. Liệt kê repositories và thông tin image

~~~bash
aws ecr describe-repositories \
  --profile dev \
  --region ap-southeast-1 \
  --query 'repositories[].{Name:repositoryName,Uri:repositoryUri,TagMutability:imageTagMutability,Encryption:encryptionConfiguration.encryptionType}' \
  --output table

aws ecr describe-images \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query 'imageDetails[].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt,SizeBytes:imageSizeInBytes}' \
  --output json
~~~

Image size trong ECR có thể phản ánh **compressed layers**, khác kích thước local Docker image. `describe-images` có pagination. Không dùng `--no-paginate` rồi suy kết quả là đầy đủ.

### 7.3. Đọc registry scanning configuration

~~~bash
aws ecr get-registry-scanning-configuration \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Kết quả cho biết `scanType` (`BASIC` hoặc `ENHANCED`) và `rules` với `scanFrequency`/`repositoryFilters` khi cấu hình. Nếu filter không khớp repository cần triển khai, hãy xem hành vi **manual/off** tương ứng trước khi kết luận pipeline đã được tự động quét.

### 7.4. Xem scan findings của đúng image

~~~bash
aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Khi tag có thể bị đổi, nên truy vấn bằng **image digest** lấy từ `describe-images`:

~~~bash
aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageDigest=sha256:REPLACE_WITH_REAL_IMAGE_DIGEST \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Status:imageScanStatus,SeverityCounts:imageScanFindings.findingSeverityCounts,Enhanced:registryId}' \
  --output json
~~~

`REPLACE_WITH_REAL_IMAGE_DIGEST` là placeholder. Trong output API, findings có thể hiển thị dưới `imageScanFindings.findings` hoặc `imageScanFindings.enhancedFindings` tùy loại scan và API version. Với Enhanced, Amazon Inspector là nơi xem chi tiết bổ sung.

**Điểm cập nhật quan trọng:** phiên bản **AWS-native Basic scanning mới** không còn cung cấp kết quả đầy đủ qua `imageScanFindingsSummary` và `imageScanStatus` của `DescribeImages`. Khi cần kết quả scan, dùng **`DescribeImageScanFindings`**. Một bảng `describe-images` không có trường scan status không phải bằng chứng image chưa được quét.

### 7.5. Bắt đầu manual scan khi dùng Basic

Lệnh sau **thay đổi trạng thái quét**, không thuộc lab chỉ đọc:

~~~bash
# CHỈ MINH HỌA cho Basic scanning và image được phép quét
aws ecr start-image-scan \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1
~~~

Chỉ thực hiện khi repository đang dùng **Basic scanning** và người vận hành có quyền/quota. **Enhanced scanning không hỗ trợ khởi chạy manual scan theo cơ chế này**. Không gọi liên tục mỗi vài giây; Basic scanning có giới hạn số lần quét từng image và quota toàn registry.

## 8. Chính sách phân quyền cho ECR: Identity và Repository

Có hai lớp chính:

1. **IAM identity-based policy:** gắn với IAM user/role, giới hạn người dùng, CI role hoặc ECS execution role được gọi ECR APIs nào.
2. **ECR repository resource-based policy:** gắn với **một repository cụ thể**, xác định principals nào được làm hành động gì trên repository đó, đặc biệt hữu ích cho **cross-account access**.

IAM/SCP/permissions boundary và explicit deny vẫn có thể giới hạn quyền. Tài liệu ECR cho biết trong cùng account, một permission **allow** thích hợp ở IAM policy **hoặc** repository policy có thể đủ cho repository action nếu không bị deny. Cross-account cần xét **quyền phía caller và tài nguyên ở account sở hữu repository**; không nên dựa vào một allow đơn lẻ khi chưa xác thực hai phía.

### 8.1. `ecr:GetAuthorizationToken` khác quyền pull/push

ECR Docker registry yêu cầu đăng nhập. `ecr:GetAuthorizationToken` lấy **token đăng nhập registry** và **phải** được phép bởi **IAM identity-based policy**, với:

~~~json
{
  "Effect": "Allow",
  "Action": "ecr:GetAuthorizationToken",
  "Resource": "*"
}
~~~

`Resource: "*"` ở đây là do action không hỗ trợ giới hạn theo repository ARN; không đồng nghĩa caller có toàn quyền với mọi repository. Token truyền thống từ ECR private registry qua `GetAuthorizationToken`/`get-login-password` có hiệu lực **12 giờ** và quyền thực tế không vượt IAM principal.

Đăng nhập `docker login` thành công chỉ cho thấy nhận được token registry hợp lệ. **Push/pull vẫn có thể lỗi AccessDenied hoặc 403** do thiếu các repository actions.

### 8.2. Quyền tối thiểu khi pull image

Nhóm actions thông dụng:

| Action | Mục đích |
|---|---|
| `ecr:GetAuthorizationToken` | Nhận token đăng nhập private registry |
| `ecr:BatchGetImage` | Lấy image manifest theo tag/digest |
| `ecr:GetDownloadUrlForLayer` | Nhận URL tải image layer |
| `ecr:BatchCheckLayerAvailability` | Kiểm tra layer có sẵn trong một số luồng client |

Với ECS execution role thông thường, các quyền cốt lõi là `GetAuthorizationToken`, `BatchGetImage` và `GetDownloadUrlForLayer`. Chỉ cấp quyền read/pull lên **repository cụ thể**; không cấp `ecr:PutImage` cho runtime chỉ cần pull.

### 8.3. Quyền cần khi push image

CI pipeline đẩy image thường cần:

- `ecr:BatchCheckLayerAvailability`.
- `ecr:InitiateLayerUpload`.
- `ecr:UploadLayerPart`.
- `ecr:CompleteLayerUpload`.
- `ecr:PutImage`.
- `ecr:BatchGetImage` trong một số workflow Docker/push.
- `ecr:GetAuthorizationToken` trên `Resource: "*"`.

Gói IAM permissions mẫu cho CI role chỉ push vào một repository, **không cấp quyền xóa repository hoặc thay chính sách**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PushOnlyApprovedRepository",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

Nếu CI dùng role từ account khác, ngoài identity policy bên CI có thể cần **repository policy phía ECR** cho cross-account push và các guardrails/conditions liên quan.

## 9. Phân biệt ECS task execution role, task role và instance role

Đây là lỗi IAM phổ biến nhất với ECS + ECR.

| Danh tính / role | Được ai sử dụng? | Công việc phổ biến |
|---|---|---|
| **Task execution role** (`executionRoleArn`) | ECS/Fargate agent hoặc runtime thay mặt task | Kéo image từ ECR, gửi logs qua CloudWatch Logs, lấy secrets phục vụ khởi tạo container khi hỗ trợ |
| **Task role** (`taskRoleArn`) | **Mã ứng dụng bên trong container** | Đọc S3, DynamoDB, SQS, Secrets Manager, gọi AWS APIs nghiệp vụ |
| **Container instance IAM role** | EC2 host đăng ký vào ECS cluster (launch type EC2) | ECS agent đăng ký/điều khiển container instance; có thể tham gia ECR image pulls tùy ECS agent/launch type |
| **CI/CD role** | Pipeline build/push/deploy | Push image, đăng ký task definition, update ECS service theo quyền được cấp |
| **ECR repository policy** | Resource policy trên ECR repository | Cho phép/chặn principals, đặc biệt cross-account |

### 9.1. Với Fargate: execution role chịu trách nhiệm pull

Ví dụ ECS task definition:

~~~json
{
  "family": "orders-api",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::111122223333:role/EcsExecutionPullRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/OrdersApiTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3",
      "essential": true,
      "portMappings": [
        { "containerPort": 8080, "protocol": "tcp" }
      ]
    }
  ]
}
~~~

Đây là **mẫu task definition rút gọn** nhằm giải thích role/image. Các giá trị IAM ARN, account, tag đều minh họa và task thực tế còn cần VPC subnets/security group, target group, logging và các thiết lập triển khai phù hợp.

`executionRoleArn` cần pull ECR. `taskRoleArn` cấp cho Spring Boot quyền gọi API nghiệp vụ, chẳng hạn `s3:GetObject` trên bucket riêng. **Đừng cấp `ecr:PutImage` cho task role** chỉ vì task đang chạy image ECR.

### 9.2. Với ECS chạy trên EC2

ECS EC2 launch type có **container instance IAM role** của host dùng cho các thao tác ECS agent và có thể để agent kéo image theo cấu hình; task execution role cũng có chức năng trong những workflow ECS hiện đại. Cần kiểm tra **agent, launch type, cơ chế image pull và permissions thực tế** thay vì suy y hệt Fargate. App containers vẫn dùng **task role riêng** khi cần truy cập AWS APIs.

Với workload bảo mật cao, tránh để một EC2 instance role rộng được dùng thay cho việc cấp quyền tách theo từng task.

### 9.3. Execution role policy mẫu cho Fargate pull ECR

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GetRegistryLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PullOrdersApiOnly",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

Managed policy **`AmazonECSTaskExecutionRolePolicy`** đã chứa quyền cần cho ECR pulls và CloudWatch Logs phổ biến, nhưng vì bao phủ nhiều repositories theo chính sách mẫu nên các tổ chức có yêu cầu least privilege có thể dùng/customize policy riêng.

## 10. Cross-account ECR pull: một sơ đồ hai tài khoản

Giả sử:

- **Account A (111122223333)** lưu ECR repository `platform/orders-api` tại Singapore.
- **Account B (444455556666)** chạy ECS Fargate và có role `EcsExecutionPullRole`.
- Yêu cầu: B được **pull đúng repository của A** để chạy task; B không được push/overwrite image.

~~~mermaid
flowchart TD
    R["Account A: ECR repository platform/orders-api"]
    P["Repository policy: cho execution role B pull"]
    B["Account B: ECS Fargate task"]
    X["Task execution role ở account B"]
    I["IAM: GetAuthorizationToken + pull repository A"]
    A["Task role: AWS API nghiệp vụ"]
    R --> P
    X --> I
    B --> X
    P -->|"Repository allow cùng identity allow"| B
    B --> A
~~~

### 10.1. Repository policy ở Account A

Ví dụ **resource policy gắn riêng repository**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAccountBExecutionRolePull",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:role/EcsExecutionPullRole"
      },
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Trong **repository policy** gắn với một ECR repository, `Resource: "*"` áp dụng trong phạm vi repository chứa policy; không đồng nghĩa cấp quyền đối với mọi repository khác. Đây là cú pháp trong ví dụ chính thức của AWS. Quyền `ecr:GetAuthorizationToken` **không** được cấp bằng repository policy; nó nằm ở **identity policy** của role B.

### 10.2. IAM identity policy ở Account B

Gắn vào execution role của ECS ở B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PullCrossAccountOrdersApi",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

Nếu SG/VPC routing hợp lệ và ECR có image ở Region đúng, Fargate task B có thể pull thông qua execution role theo policy thiết kế. Trong môi trường thật, cần xét SCP, permissions boundaries, deny statements, endpoint policies và ECR repository policy. Account B cũng cần được kích hoạt ở Region tương ứng nếu tính năng/Region yêu cầu.

### 10.3. Những nhầm lẫn dễ gặp

- **B có `GetAuthorizationToken`, A không cấp quyền repo:** login thành công nhưng pull bị 403.
- **A cho role B pull, role B thiếu `GetAuthorizationToken`:** runtime không đăng nhập registry được.
- **A cấp cho root account B thay vì specific role:** phạm vi có thể rộng ngoài ý muốn, cần policy review.
- **Task role có permission nhưng execution role thiếu:** container không khởi động dù app role có quyền rộng.
- **Repository cùng tên ở account/Region khác:** manifest không tìm thấy, task pull sai endpoint hoặc `CannotPullContainerError`.

## 11. Docker login, push và pull trong thực hành

Những lệnh sau chỉ là **cú pháp vận hành có tác động thật**. Để chạy cần AWS CLI, Docker, IAM profile được cấp quyền và repository được phép sử dụng.

### 11.1. Đăng nhập private ECR theo Region

~~~bash
aws ecr get-login-password \
  --profile ci \
  --region ap-southeast-1 \
  | docker login --username AWS --password-stdin \
      111122223333.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

`get-login-password` sử dụng AWS credentials hiện tại để nhận **token 12 giờ**. Lệnh truyền mật khẩu qua standard input, tránh đặt mật khẩu trực tiếp trên command line. Docker có thể lưu registry credentials trong cấu hình cục bộ hoặc credential store; nên dùng credential helper phù hợp và không sao chép `~/.docker/config.json` chứa thông tin đăng nhập vào artifacts/CI logs.

ECR private token thông thường lấy theo Region qua `get-login-password`, vì vậy dùng **Region khớp registry endpoint**. Việc token hợp lệ không làm vượt quyền IAM.

### 11.2. Build, tag và push image

~~~bash
# Ví dụ cho CI được cấp quyền push; có thể tạo phí lưu trữ ECR.
docker build -t orders-api:1.2.3 .

docker tag orders-api:1.2.3 \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3

docker push \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
~~~

Sau push, đọc image digest và scan status. Đừng mặc định `docker push` hoàn tất là image đã vượt qua **security gate**. Khi phát hành production, dùng digest và quy trình review để bảo đảm ECS chạy chính bản đã được kiểm tra.

### 11.3. Tải một image có quyền

~~~bash
docker pull \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
~~~

Nếu pull thành công ở laptop nhưng ECS task fail, hãy so sánh **IAM principal khác nhau**: laptop dùng role developer, còn Fargate dùng **task execution role**. Phải kiểm tra quyền/network từ môi trường ECS chứ không chỉ từ máy cá nhân.

## 12. ECR trong VPC private subnet: quyền IAM và network path

ECS Fargate task có thể chạy trong private subnets **không có public IP**. Nếu subnet không có NAT/Internet egress, image pull vẫn có thể thực hiện qua **AWS PrivateLink / VPC endpoints** khi cấu hình đầy đủ.

Với Linux Fargate platform version **1.4.0 trở lên**, khi dùng ECR private VPC endpoint, thông thường cần:

| Endpoint | Loại | Vai trò |
|---|---|---|
| `com.amazonaws.ap-southeast-1.ecr.api` | Interface | ECR API, token/metadata actions |
| `com.amazonaws.ap-southeast-1.ecr.dkr` | Interface | Docker registry API cho image pull |
| `com.amazonaws.ap-southeast-1.s3` | **Gateway endpoint** | Truy cập S3-backed image layers trong quá trình pull |

Với Fargate platform version 1.3.0 hoặc cũ hơn có khác biệt về endpoint requirements; tham khảo tài liệu AWS tương ứng. Nếu task còn dùng CloudWatch Logs, Secrets Manager, SSM Parameter Store qua private network, có thể cần **endpoints tương ứng** hoặc NAT egress hợp lệ.

### 12.1. Kiểm tra kết nối

1. **VPC/Subnet/route table:** S3 Gateway Endpoint có liên kết với các route tables cần thiết.
2. **Private DNS:** bật cho interface endpoints ECR để runtime tìm đúng private endpoint.
3. **Endpoint Security Group:** cho phép traffic TCP 443 từ task ENIs theo subnet/SG thiết kế.
4. **Execution IAM role và repository policy:** chỉ cho đúng ECR actions.
5. **Endpoint policy:** không chặn repository/account dùng.
6. **DNS resolution:** VPC attributes/Route 53 Resolver không phá endpoint hostname.
7. **Cross-account/cross-Region:** bảo đảm endpoint và network path phục vụ đúng Region của registry.
8. **S3 layer delivery:** đường truy cập S3 cho layer phải có; chỉ có ECR API endpoint chưa đủ.

**Lưu ý:** với image đầu tiên từ ECR pull-through cache hoặc một số cơ chế layer ngoại vi có thể cần Internet egress theo tài liệu dịch vụ; không suy rằng ba endpoints luôn đủ cho mọi nguồn image. Cần thử nghiệm topology đúng với launch type và image source thực tế.

### 12.2. Phân biệt ba nhóm lỗi khi không pull được

| Triệu chứng | Nghi ngờ đầu tiên |
|---|---|
| `ResourceInitializationError` lấy auth | `GetAuthorizationToken`, execution role hoặc ECR API endpoint |
| Timeout kết nối registry | ECR DKR/API endpoint, DNS, route, SG/NACL, NAT |
| Auth thành công nhưng manifest/layer bị 403 | `BatchGetImage`, `GetDownloadUrlForLayer`, repository policy, endpoint policy |
| Không tải được layer | S3 endpoint/NAT/route hoặc quyền ECR cần thiết |
| Image/tag không tồn tại | Sai account/Region/repository/tag/digest |
| Task chạy nhưng app lỗi gọi S3 | **Task role của ứng dụng**, không phải ECR execution role |

## 13. Thiết kế release gate từ scan findings

Một pipeline được kiểm soát tốt có thể dùng các giai đoạn:

~~~mermaid
flowchart TD
    C["Commit"] --> B["Build + unit/integration tests"]
    B --> S["Dependency scan / SBOM / secrets checks"]
    S --> P["Push image với tag duy nhất tới ECR"]
    P --> Q["Đợi ECR/Inspector scan hoàn tất"]
    Q --> D{"Kết quả có đạt release policy?"}
    D -->|"Đạt hoặc exception hợp lệ"| R["Ghi image digest đã duyệt"]
    D -->|"Không đạt"| F["Block promotion, tạo remediation ticket"]
    R --> E["ECS task definition dùng image digest"]
    E --> H["Canary/rolling deploy + health checks"]
    H --> M["Theo dõi CloudWatch và CVE mới"]
    M --> U["Rebuild/patch/rollout khi có finding mới"]
~~~

### 13.1. Một policy gate minh họa

Đây là **ví dụ của một nhóm**, không phải tiêu chuẩn bắt buộc của AWS:

- **Block** nếu scan không hoàn tất/hết eligibility/unsupported ở phần image bắt buộc kiểm tra.
- **Block hoặc yêu cầu exception** với Critical vulnerabilities có thể khai thác và thuộc phạm vi exposure của ứng dụng.
- **Yêu cầu remediation SLA** theo mức độ rủi ro cho High/Medium.
- **Lưu trữ bằng chứng:** image digest, commit SHA, scan type, scan timestamp, số findings, exception owner và ngày hết hạn.
- **Re-evaluate** khi có CVE mới liên quan image đã triển khai.

**Đừng triển khai theo `latest` mutable tag** sau khi scan tag `latest` trước đó. Pipeline phải gắn **image digest** từ đúng image đã quét với task definition được deploy.

### 13.2. Những điều gate không được giả định

- `scan completed` không đồng nghĩa `0 findings`.
- `0 findings` không đồng nghĩa mọi OS/framework/dependency đều đã được hỗ trợ/kiểm tra.
- Scan kết thúc trước deploy không có nghĩa image đã được ký hay nguồn code đã được review.
- ECR image scanning không tự làm sạch secrets, malware, runtime CVEs hay IAM misconfiguration.
- CVE mới sau khi phát hành cần phát hiện và xử lý liên tục; chạy task cũ không tự cập nhật code.

## 14. EventBridge, Amazon Inspector và CloudTrail

### 14.1. Sự kiện khi scan hoàn tất

Với **Basic scanning**, Amazon ECR có thể phát sự kiện tới EventBridge với:

~~~json
{
  "source": "aws.ecr",
  "detail-type": "ECR Image Scan",
  "detail": {
    "scan-status": "COMPLETE",
    "repository-name": "platform/orders-api",
    "image-digest": "sha256:EXAMPLE_IMAGE_DIGEST"
  }
}
~~~

Đây là **mẫu sự kiện rút gọn**, không phải payload đầy đủ hợp lệ cho production.

Với **Enhanced scanning**, **Amazon Inspector** phát sự kiện khi scan lần đầu xong hoặc có finding tạo/cập nhật/đóng. EventBridge patterns thường quan tâm:

~~~json
{
  "source": ["aws.inspector2"],
  "detail-type": ["Inspector2 Scan", "Inspector2 Finding"]
}
~~~

Có thể dùng EventBridge → Lambda/Step Functions/SNS/Security Hub để cập nhật ticket, thông báo owner hoặc đánh dấu cần rebuild. Khi xử lý sự kiện, cần kiểm tra idempotency, quyền IAM, rate limiting và phân biệt event lifecycle với **kết quả scan hiện tại** lấy từ ECR/Inspector APIs.

### 14.2. CloudTrail và trách nhiệm kiểm toán

CloudTrail có thể ghi các API quản lý ECR như `PutImage`, `SetRepositoryPolicy`, `PutRegistryScanningConfiguration`, `BatchDeleteImage` theo cấu hình event logging. Khi điều tra một image bị ghi đè, cần đối chiếu actor/principal, timestamp, Region, repository và image digest. Không dùng tag làm ID duy nhất của một sự kiện phát hành.

### 14.3. Giám sát thực tế

- Tỷ lệ image production có scan thành công/gần đây.
- Số Critical/High findings còn mở và tuổi phát hiện.
- Images chưa scan, unsupported hoặc hết eligibility.
- Số lần task `CannotPullContainerError`/`ResourceInitializationError`.
- Thời gian từ CVE có fix đến image được rebuild và deploy.
- Số image/layer cũ chưa xóa, dung lượng ECR và phí Inspector/CloudWatch.

## 15. Quản trị repository: immutable tags, lifecycle và mã hóa

### 15.1. Tag immutability

Khi repository đặt **IMMUTABLE** tag policy, client không thể tùy ý ghi đè một tag đã có; ECR trả lỗi nếu cố push lại cùng tag theo quy tắc áp dụng. Một số cấu hình mới hỗ trợ exclusions có chủ đích, nên kiểm tra setting chính xác của repository.

- Ưu tiên tag có định danh commit/release, ví dụ `1.2.3-9af15d`.
- Ghi image **digest** trong release manifest, task definition và dữ liệu audit.
- Không dùng mutable `latest` làm căn cứ release.
- Điều chỉnh tag policy qua IaC/approval, không làm thay đổi thủ công ngoài pipeline.

**Tag immutability không thay thế digest pinning** và không tự chứng minh image đã được scan.

### 15.2. Lifecycle/archiving

ECR lifecycle policies có thể dọn image cũ không còn cần dùng theo quy tắc count/age/tag hoặc cấu hình được hỗ trợ. Tuy nhiên:

- Nếu xóa **image digest** đang được task mới cần pull, scale-out hoặc recovery có thể thất bại.
- Nếu giữ quá nhiều image/layer sẽ tăng chi phí lưu trữ.
- Archived images chưa được restore có giới hạn pull/scan; cần xem quy trình restore trước khi đưa trở lại production.
- Nên giữ **release đang chạy, rollback candidates và retention theo chính sách**.

### 15.3. Mã hóa và quyền KMS

ECR hỗ trợ mã hóa image lưu trữ với cách cấu hình phù hợp như encryption được AWS quản lý hoặc **AWS KMS** khi chọn. Với KMS customer managed key, quản trị viên cần kiểm tra key policy, grant và quyền KMS. Mã hóa **at rest** bảo vệ nội dung trong registry theo thiết kế, nhưng không sửa CVE trong image và không bảo đảm container sẽ chạy an toàn.

## 16. Chi phí và vận hành đa Region

| Nguồn chi phí | Điều cần quan sát |
|---|---|
| **ECR storage** | Dung lượng image/layers còn lưu, loại lưu trữ/tiering nếu có |
| **Amazon Inspector** | Enhanced scanning, monitoring/re-scans theo giá hiện hành |
| **Data transfer** | Cross-Region/cross-account/Internet và đường kéo layers |
| **VPC Interface Endpoints** | Endpoint-hour và dữ liệu xử lý |
| **NAT Gateway** | Data processing nếu image pulls đi qua NAT |
| **CloudWatch/CloudTrail/EventBridge** | Logs, metrics, event processing và audit |
| **ECS Fargate/EC2** | Compute của task/service, độc lập với ECR registry |

Để phục vụ ECS triển khai đa Region, có thể dùng **ECR replication rules** hoặc pipeline push/promote vào từng Region, nhưng cần kiểm tra quyền, tính nhất quán về digest, thời điểm replication và scanning configuration **riêng của Region đích**. Tạo repository ở Singapore không làm image xuất hiện tự động tại Tokyo nếu chưa có replication/copy.

Không ép mọi task cross-Region kéo image nếu có thể tránh bằng replication và chính sách release phù hợp; thiết kế cần đánh giá độ trễ triển khai, mạng, chi phí và availability.

## 17. Troubleshooting theo nhóm lỗi

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| `no basic scan findings` dù đã push | Repository vẫn manual scan; chưa trigger Basic; scan status pending/unsupported | `get-registry-scanning-configuration` rồi `describe-image-scan-findings` |
| `DescribeImages` không có `imageScanFindingsSummary` | Basic scanning mới không trả trường này | Dùng `DescribeImageScanFindings` |
| `SCAN_ELIGIBILITY_EXPIRED` | Image ngoài thời gian Inspector monitoring/eligibility | Xem Inspector coverage/duration, cân nhắc push image mới |
| `UNSUPPORTED_IMAGE` | OS/package/media type không nằm trong phạm vi scanner | Xem AWS supported images/OS, quét bổ sung ở CI |
| `StartImageScan` không khả dụng | Enhanced scanning không hỗ trợ manual scan | Kiểm tra scan type và filter |
| ECR Docker login bị `AccessDenied` | Thiếu `ecr:GetAuthorizationToken` trong identity policy | Kiểm tra caller, IAM/SCP, đúng Region |
| Docker login được nhưng pull 403 | Thiếu `BatchGetImage`/`GetDownloadUrlForLayer`, repository policy/endpoint deny | Kiểm tra repo ARN, principal, policy ở hai phía |
| `CannotPullContainerError` khi Fargate start | Role, image URI, auth, VPC endpoints hoặc S3 layer path | Xem ECS stopped reason, logs, execution role, SG/endpoints |
| ECS task chạy nhưng ứng dụng gọi S3 lỗi | Thiếu `s3:GetObject` ở **task role** | So sánh `taskRoleArn` và resource policy |
| `ImageTagAlreadyExistsException` | Repository immutable tags | Dùng tag mới và ghi digest |
| Registry khác Region trả manifest not found | Pull sai registry endpoint/Region | Đối chiếu account ID/Region/image digest |
| Enhanced bật nhưng repo không scan | Repo không khớp filters → Off hoặc Inspector chưa active | Xem scanning rules và Inspector coverage |
| CPU/memory task thiếu để chạy | Image pull thành công nhưng task startup bị lỗi | Xem task size, container logs và health checks |
| Image còn CVE sau khi sửa code | Base image hoặc Java dependency transitives chưa cập nhật | Rebuild bằng base image/dependency mới, scan digest mới |
| Image đã được xóa/archived | Lifecycle policy loại bản dùng cho rollback | Điều tra ECR lifecycle/restore, giữ release digests cần thiết |
| Phí ECR/Inspector tăng | Nhiều image stale, scans/monitoring scope quá rộng, data transfer | Phân tích Cost Explorer/billing/retention và filter |

### 17.1. Trình tự chẩn đoán khi ECS không khởi động

1. Đọc ECS **stopped reason** và event của service; xác định lỗi pull image hay lỗi ứng dụng.
2. Xác minh **AWS account, Region, image URI/tag/digest**.
3. Đọc **`executionRoleArn`** của task definition; có `GetAuthorizationToken` và repo pull actions không?
4. Nếu cross-account, kiểm tra repository policy phía account chủ image.
5. Kiểm tra **network path** từ task subnet/ENI đến ECR API/DKR và S3 layers.
6. Nếu image pull thành công, chuyển sang kiểm tra **`taskRoleArn`**, application logs, secrets/DB/ALB health.
7. Không dùng quyền administrator hoặc mở toàn bộ Internet để “thử” trong production.

## 18. Bài lab chỉ đọc: đánh giá một ECR repository

### 18.1. Điều kiện

Có AWS account thực hành với AWS CLI v2 và profile `dev`; có quyền đọc ECR repository, scanning configuration và scan findings. Không cần tạo repository, push image, kích hoạt Inspector hay sửa IAM. Nếu không có repository, dùng **output giả lập** từ bảng/policy của bài để phân tích.

### 18.2. Bước A – xác nhận tài khoản và Region

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws ecr describe-repositories \
  --profile dev \
  --region ap-southeast-1 \
  --query 'repositories[].{Name:repositoryName,Uri:repositoryUri}' \
  --output table
~~~

Câu hỏi: repository nào được sử dụng cho production, có trùng tên với repository ở account/Region khác không?

### 18.3. Bước B – đọc registry scanning rules

~~~bash
aws ecr get-registry-scanning-configuration \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Phân tích `scanType`, `scanFrequency`, `repositoryFilters`. Với Basic, nếu repository không khớp scan-on-push filter thì nó được scan theo chế độ nào? Với Enhanced, nếu repository không khớp filter nào thì sao?

### 18.4. Bước C – đọc image và scan findings

~~~bash
aws ecr describe-images \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query 'imageDetails[].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt}' \
  --output json

aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Nếu không có image được cấp quyền, không cần tự push; hãy giải thích các trạng thái `COMPLETE`, `IN_PROGRESS`, `FAILED` hoặc `SCAN_ELIGIBILITY_EXPIRED` mà API/scanner có thể báo theo loại quét. Nếu scan thành công nhưng có Critical findings, đề xuất quy trình xử lý theo chính sách release.

### 18.5. Bước D – đọc repository policy

~~~bash
aws ecr get-repository-policy \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Nếu repository chưa gắn resource policy riêng, API có thể báo không tìm thấy policy; điều đó **không mặc định cho phép public access**. Cần xem identity IAM policies và quy tắc cross-account. Chỉ ra `Principal` nào được pull/push và có quyền quản lý/xóa hay không.

### 18.6. Bước E – phân quyền cho ECS Fargate

Xem lại JSON task definition/policies ở các phần trước và trả lời:

1. Role nào cần quyền `ecr:GetAuthorizationToken`?
2. Role nào cần `s3:GetObject` khi ứng dụng Java xử lý đơn hàng từ S3?
3. Account B có quyền pull image ở account A nếu chỉ có IAM policy B mà repository policy A không cho phép không?
4. Nếu task chạy private subnet không NAT, cần endpoints nào để kéo image ECR?
5. Nếu task definition dùng mutable tag, rủi ro khác gì so với dùng digest?
6. Scan mới phát hiện lỗ hổng Critical sau khi image đang chạy, ECS có tự vá không?

### 18.7. Bước F – đề xuất policy release

Viết một trang ngắn mô tả **image digest nào được phép deploy**, khi nào block, khi nào có exception, ai duyệt và cách theo dõi CVE mới. Kèm một runbook rollback đến digest đã được kiểm chứng. Không cần tạo ECS service thật trong bài.

## 19. Câu hỏi tự đánh giá

1. ECR registry, repository, image tag và digest khác nhau ra sao?
2. Vì sao scan Basic không bao phủ đầy đủ các Java dependencies?
3. Phân biệt Basic manual, Basic scan-on-push, Enhanced scan-on-push và Enhanced continuous.
4. Mặc định một ECR registry dùng Basic có đồng nghĩa mọi repository tự scan khi push không?
5. Với Enhanced, một repository không khớp scanning filter nào sẽ được scan như thế nào?
6. Vì sao `DescribeImageScanFindings` đáng tin cậy hơn việc chỉ đọc `DescribeImages` để xem kết quả Basic hiện hành?
7. Khi image có `0 findings` nhưng scanner báo unsupported image, có thể phát hành không cần xem xét gì không?
8. `GetAuthorizationToken` có thể bị giới hạn `Resource` về đúng một repository ARN không?
9. Role nào cho phép ECS Fargate **pull** ECR image: task role hay task execution role?
10. Một task đã chạy, gọi DynamoDB nhận AccessDenied; nên xem role nào?
11. Trong cross-account pull, repository policy và caller IAM policy đóng vai trò gì?
12. ECR login token có hiệu lực bao lâu và token có nâng quyền IAM không?
13. Khi ECS task ở private subnet, vì sao ECR endpoints đôi khi chưa đủ nếu thiếu S3 gateway endpoint?
14. Vì sao một image tag immutable vẫn cần được đối chiếu bằng digest trong release record?
15. Điều gì xảy ra khi Enhanced scanning phát hiện CVE mới ở image đang triển khai?
16. Vì sao nên giới hạn CI role chỉ được push vào repository cụ thể và không được sửa repository policy?
17. Làm sao tránh lifecycle policy xóa image cần cho rollback?
18. Những khoản phí có thể phát sinh khi bật Enhanced scanning và kéo image qua private endpoints?

### Định hướng đáp án

Năng lực đạt yêu cầu là phân biệt được **image content/digest**, **scanner coverage/finding status**, **ECR repository access**, **ECS runtime execution permissions** và **AWS API permissions của ứng dụng**. Có thể đọc một kết quả scan, đưa ra quyết định release có bằng chứng và tìm được nguyên nhân khi ECS không kéo được image.

## 20. Tài liệu AWS chính thức

1. [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) – Tổng quan Basic và Enhanced.
2. [Configuring basic scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-basic-enabling.html) – Registry-level configuration, scan-on-push filters.
3. [Enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html) – Inspector integration, coverage và thời hạn giám sát.
4. [Configuring enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-enabling.html) – Filters, frequency, CLI.
5. [Retrieving basic scan findings](https://docs.aws.amazon.com/AmazonECR/latest/userguide/describe-scan-findings.html) – API `DescribeImageScanFindings`.
6. [Retrieving enhanced scan findings](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-describe-scan-findings.html) – Xem findings và Amazon Inspector.
7. [ECR scanning filters](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-filters.html) – Điều kiện khớp repository.
8. [Private repository policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policies.html) – Phân quyền resource policy và IAM.
9. [ECR repository policy examples](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policy-examples.html) – Cross-account examples.
10. [IAM permissions for pushing images](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html) – Các actions cần cho push.
11. [Amazon ECR images with ECS](https://docs.aws.amazon.com/AmazonECR/latest/userguide/ECR_on_ECS.html) – Image URI và quyền pull.
12. [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) – Quyền ECR/Logs cho ECS execution.
13. [ECR VPC endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) – API/DKR interface và S3 gateway endpoints.
14. [AWS CLI get-login-password](https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html) – Đăng nhập registry và token 12 giờ.
15. [AWS ECR events and EventBridge](https://docs.aws.amazon.com/AmazonECR/latest/userguide/ecr-eventbridge.html) – Basic scan events.
16. [Enhanced scanning EventBridge events](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-events.html) – Inspector2 Scan/Finding events.
17. [ECR image scanning troubleshooting](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-troubleshooting.html) – Lỗi scan và eligibility.
18. [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/) – Storage và data transfer.
19. [Amazon Inspector pricing](https://aws.amazon.com/inspector/pricing/) – Enhanced vulnerability scanning.

> **Ghi nhớ:** ECR kiểm soát **image được lưu và ai có quyền truy cập**, ECS sử dụng **execution role** để kéo image, và Amazon Inspector giúp **theo dõi CVE**. Một quy trình đáng tin cậy phải kết hợp **digest pinning, scanning phù hợp, IAM/repository policies có giới hạn, kết nối VPC đúng, release gate, audit và cập nhật image sau khi có vulnerability mới**.

