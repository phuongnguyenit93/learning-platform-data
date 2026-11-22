# Kiểm tra mã, dependency và cấu hình hạ tầng trong pipeline

Trong chương **CI/CD và phát hành**, kiểm tra bảo mật và chất lượng cần chạy tự động trước khi artifact được đưa vào môi trường serverless. Một Java function có thể biên dịch và vượt qua unit test nhưng vẫn chứa lỗ hổng trong thư viện bắc cầu, vô tình đóng gói secret, cấp quyền IAM quá rộng hoặc cấu hình trigger khiến message bị mất khi retry. Vì vậy, pipeline cần kiểm tra đồng thời mã nguồn, dependency và cấu hình hạ tầng.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Những kiểm tra trong pipeline giúp phát hiện rủi ro trước khi function được cấp quyền truy cập dữ liệu hoặc nhận traffic production.

## 1. Vì sao cần kiểm tra trong CI/CD?

Một bản phát hành serverless thường gồm nhiều thành phần:

- Java source, resource và file cấu hình.
- Thư viện trực tiếp và dependency bắc cầu.
- JAR, ZIP deployment package hoặc container image.
- Mẫu hạ tầng như AWS SAM, CloudFormation, CDK hoặc Terraform.
- IAM role, resource policy, event source mapping và trigger.
- Environment variable, secret reference, network và logging configuration.

Một lỗi ở bất kỳ thành phần nào cũng có thể làm tăng rủi ro bảo mật hoặc gây gián đoạn. Ví dụ:

- Dependency JSON parser có CVE cho phép xử lý payload độc hại.
- Source code ghi log access token hoặc dữ liệu cá nhân.
- Terraform tạo Lambda Function URL công khai ngoài ý muốn.
- Execution role có quyền s3:* trên toàn account.
- SQS event source mapping không cấu hình DLQ hoặc redrive phù hợp.
- Container image chứa package hệ điều hành có lỗ hổng nghiêm trọng.
- Template đặt timeout quá thấp khiến message liên tục retry.
- Secret được truyền trực tiếp vào environment variable rồi xuất hiện trong bản mô tả triển khai hoặc log.

Kiểm tra trong pipeline tạo một cổng chất lượng có thể lặp lại. Mỗi commit hoặc pull request được đánh giá theo cùng quy tắc, có báo cáo và có thể truy vết về source revision.

## 2. Các lớp kiểm tra

Các loại kiểm tra bổ trợ nhau và phát hiện những vấn đề khác nhau.

| Lớp kiểm tra | Mục tiêu | Ví dụ công cụ |
|---|---|---|
| Code quality | Quy ước, lỗi tiềm ẩn, độ phức tạp | Checkstyle, PMD, SpotBugs |
| SAST | Phát hiện mẫu code có nguy cơ bảo mật | CodeQL, Semgrep, SonarQube |
| SCA | Lỗ hổng và license của dependency | OWASP Dependency-Check, OSV-Scanner, Trivy |
| Secret scanning | Credential hoặc secret bị commit | Gitleaks, detect-secrets |
| IaC scanning | Cấu hình cloud không an toàn | Checkov, tfsec, cfn-lint, cdk-nag |
| Policy as code | Quy tắc tổ chức cho hạ tầng và phát hành | OPA/Conftest, CloudFormation Guard |
| Artifact/image scanning | Thành phần nguy hiểm trong gói phát hành | Trivy, ECR image scanning |
| SBOM/provenance | Thành phần và nguồn gốc artifact | CycloneDX, SPDX, SLSA attestations |

Không nên coi một công cụ là giải pháp toàn diện. SAST không thay thế SCA; IaC scanner không phát hiện mọi lỗi trong Java; secret scanner không chứng minh một credential đã bị thu hồi. Cần xác định lớp nào đang bảo vệ tài sản và rủi ro nào còn chưa được kiểm tra.

~~~mermaid
flowchart TD
    SRC["Pull request / source"] --> CODE["Compile, lint, unit test"]
    CODE --> SAST["SAST"]
    SRC --> SECRET["Secret scan"]
    SRC --> SCA["Dependency / license scan"]
    SRC --> IAC["IaC scan and policy"]
    SAST --> GATE{"Quality gates"}
    SECRET --> GATE
    SCA --> GATE
    IAC --> GATE
    GATE --> BUILD["Build immutable artifact"]
    BUILD --> SBOM["SBOM and artifact scan"]
    SBOM --> SIGN["Sign / attest"]
    SIGN --> DEPLOY["Deploy to test environment"]
    DEPLOY --> VERIFY["Integration and smoke tests"]
    VERIFY --> RELEASE["Approve and promote"]
~~~

Pipeline nên kiểm tra cả source trước build và artifact sau build. Source scan có thể phát hiện vấn đề trong code; artifact scan xác nhận đúng những gì sắp được triển khai, bao gồm dependency thực sự được đóng gói.

## 3. Kiểm tra chất lượng và biên dịch Java

Trước khi chạy các scanner chuyên sâu, pipeline cần xác nhận dự án biên dịch và tuân thủ quy tắc chất lượng cơ bản.

Với Maven:

~~~bash
mvn -B clean verify
~~~

verify chạy các phase trước đó trong Maven lifecycle, bao gồm compile, test và các plugin đã được gắn vào lifecycle. Pipeline nên cấu hình plugin rõ ràng để static analysis, test coverage hoặc kiểm tra định dạng được chạy ở đúng phase.

Một số công cụ phổ biến:

- **Checkstyle:** kiểm tra style, naming, import và quy ước code.
- **PMD:** tìm code smell và một số lỗi logic phổ biến.
- **SpotBugs:** phân tích bytecode để tìm bug có khả năng xảy ra.
- **SonarQube/SonarCloud:** tổng hợp chất lượng, coverage, maintainability và security finding theo rule set.
- **Error Prone:** phát hiện một số lỗi Java ngay trong quá trình biên dịch.

Các công cụ này không có cùng mục tiêu. Ví dụ, format sai không đồng nghĩa có lỗ hổng bảo mật; một bug concurrency có thể không bị phát hiện bởi rule style.

### 3.1. Khóa phiên bản công cụ

Plugin build và scanner cũng là dependency của pipeline. Cần khai báo phiên bản cụ thể, cập nhật có kiểm soát và tránh để build tự động lấy một phiên bản mới bất kỳ ở mỗi lần chạy.

Ví dụ cấu trúc Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>com.github.spotbugs</groupId>
            <artifactId>spotbugs-maven-plugin</artifactId>
            <version>APPROVED_VERSION</version>
            <executions>
                <execution>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

APPROVED_VERSION là placeholder, cần thay bằng phiên bản đã được tổ chức phê duyệt và pin trong repository. Cần quản lý phiên bản JDK, Maven/Gradle wrapper và plugin đồng bộ giữa máy developer với CI.

Với Gradle, dùng wrapper và khóa plugin version trong plugins block hoặc version catalog. Không phụ thuộc vào Gradle cài global trên runner.

## 4. SAST: phân tích bảo mật mã nguồn

Static Application Security Testing (SAST) phân tích source code hoặc bytecode để tìm mẫu có thể dẫn đến lỗ hổng. Công cụ có thể nhận diện:

- SQL injection do nối chuỗi đầu vào vào câu truy vấn.
- Command injection khi đưa input vào shell.
- Path traversal khi dùng path từ request mà không kiểm tra.
- Deserialization không an toàn.
- Hardcoded credential hoặc token.
- Mã hóa yếu hoặc cấu hình TLS sai.
- Lộ thông tin qua log hoặc exception response.
- SSRF do gọi URL do người dùng kiểm soát.
- Kiểm tra quyền thiếu trước khi truy cập resource.

Ví dụ code Java có rủi ro SQL injection:

~~~java
String sql = "SELECT * FROM orders WHERE id = '" + orderId + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Nên dùng parameterized query:

~~~java
String sql = "SELECT * FROM orders WHERE id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, orderId);
    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

SAST có thể phát hiện một số pattern nối chuỗi SQL, nhưng không chứng minh mọi đường dữ liệu đều an toàn. Cần xem source-to-sink flow, validation, framework behavior và ngữ cảnh thực tế.

### 4.1. SAST trong pull request

Một luồng thường dùng:

1. Quét các file thay đổi trong pull request để phản hồi nhanh.
2. Quét toàn repository theo lịch để phát hiện vấn đề ở code cũ.
3. Phân loại finding theo severity, confidence và vị trí.
4. Yêu cầu sửa finding mới có mức rủi ro vượt ngưỡng.
5. Cho phép ngoại lệ có owner, lý do và thời hạn.

Không nên bỏ qua toàn bộ rule chỉ vì có một false positive. Tạo suppression hẹp cho đúng finding, có giải thích và ngày xem xét lại.

### 4.2. SAST không phải kiểm thử runtime

SAST không thể xác nhận IAM role ở môi trường production, network route hoặc retry behavior của event source mapping. Cần kết hợp integration test, IaC scanning và kiểm tra cấu hình triển khai.

## 5. SCA: kiểm tra dependency trực tiếp và bắc cầu

Software Composition Analysis (SCA) kiểm tra thư viện bên thứ ba mà ứng dụng sử dụng. Java project thường có dependency trực tiếp và dependency bắc cầu (transitive dependency).

Ví dụ, ứng dụng khai báo framework HTTP; framework lại phụ thuộc vào thư viện logging, parser hoặc utility. Một lỗ hổng trong dependency bắc cầu vẫn có thể ảnh hưởng ứng dụng dù nhóm phát triển không khai báo thư viện đó trực tiếp.

Với Maven, xem dependency tree:

~~~bash
mvn -B dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind
~~~

SCA thường đối chiếu package, version và metadata với cơ sở dữ liệu lỗ hổng. Các công cụ có thể sử dụng CVE, GitHub Advisory Database, OSV hoặc nguồn advisory của nhà cung cấp.

### 5.1. OWASP Dependency-Check và OSV-Scanner

Một pipeline có thể dùng OWASP Dependency-Check để nhận diện dependency có advisory tương ứng. OSV-Scanner có thể đối chiếu package version với OSV database. Trivy cũng có thể quét filesystem, lockfile, image và một số dạng artifact.

Ví dụ chạy scanner là bước riêng của pipeline:

~~~bash
dependency-check --project "orders-lambda" --scan .
osv-scanner scan source -r .
~~~

Cú pháp cụ thể phụ thuộc phiên bản công cụ và cách cài đặt trên runner. Cần dùng command và output format đúng với phiên bản đã pin trong CI.

### 5.2. Đánh giá mức độ rủi ro

Không nên chỉ dựa vào CVSS để quyết định mọi finding. Cần xem:

- Dependency có nằm trong artifact production không?
- Code có gọi đến thành phần dễ bị ảnh hưởng không?
- Lỗ hổng có thể khai thác từ input mà function nhận không?
- Function có chạy với quyền nhạy cảm không?
- Có exploit công khai hoặc dấu hiệu đang bị khai thác không?
- Có bản vá hoặc workaround an toàn không?
- Runtime hoặc platform có giảm thiểu một phần rủi ro không?

Ví dụ, một thư viện có CVE trong module XML parser nhưng ứng dụng không đóng gói module đó có thể có mức phơi nhiễm khác với một function nhận XML từ Internet và dùng đúng parser dễ bị ảnh hưởng.

Tuy nhiên, không tự kết luận "không reachable" chỉ vì không thấy lời gọi trực tiếp. Framework có thể gọi dependency qua reflection, service loader hoặc auto-configuration. Cần kiểm tra dependency graph và cách runtime nạp class.

### 5.3. Khóa phiên bản dependency

Để build có thể tái lập:

- Khai báo version rõ ràng hoặc dùng BOM đã được pin.
- Kiểm tra dependency lockfile nếu hệ build hỗ trợ.
- Không dùng dynamic version như 1.+ trong production build.
- Không lấy dependency từ repository không đáng tin cậy.
- Theo dõi cả plugin build và annotation processor.
- Cập nhật dependency theo lịch và khi có advisory quan trọng.

Với Maven, dependencyManagement/BOM giúp thống nhất version trong dependency tree. Với Gradle, version catalog và dependency locking giúp kiểm soát phiên bản đã resolve.

## 6. Kiểm tra license của dependency

SCA có thể phát hiện license của thư viện bên thứ ba. License là một phần của rủi ro pháp lý và phân phối artifact.

Cần biết:

- License của dependency trực tiếp và bắc cầu.
- Nghĩa vụ khi phân phối binary hoặc source.
- Yêu cầu giữ copyright notice hoặc license text.
- Chính sách tổ chức với license hạn chế hoặc không rõ nguồn.
- Cách xử lý thư viện dual-license.

Không tự kết luận một license được phép chỉ dựa trên tên viết tắt. Những trường hợp chưa rõ cần chuyển cho nhóm pháp chế hoặc người phụ trách open source. Pipeline có thể chặn license nằm trong danh sách cấm và tạo finding để review các trường hợp cần đánh giá.

## 7. Secret scanning

Secret scanner tìm credential có thể bị commit vào source, file cấu hình hoặc lịch sử repository. Các mẫu thường gặp:

- AWS access key và secret.
- API token.
- Private key.
- Password trong connection string.
- OAuth client secret.
- Webhook signing secret.
- Credential trong file .env, YAML hoặc JSON.

Một số công cụ: Gitleaks, detect-secrets và secret scanning tích hợp trong nền tảng Git.

Ví dụ chạy Gitleaks:

~~~bash
gitleaks detect --source . --redact
~~~

Tùy phiên bản, command có thể là gitleaks git hoặc gitleaks dir; cần pin phiên bản và dùng syntax theo tài liệu tương ứng. Tùy chọn redact giúp hạn chế in nguyên secret vào log.

### 7.1. Quét lịch sử Git

Quét working tree chỉ phát hiện nội dung hiện có. Một secret đã bị xóa khỏi commit mới vẫn có thể tồn tại trong Git history, branch cũ, fork hoặc artifact.

Nếu phát hiện secret thật:

1. Thu hồi hoặc rotate credential ngay theo quy trình.
2. Xác định resource và hành động mà credential có thể truy cập.
3. Kiểm tra audit log để tìm dấu hiệu sử dụng bất thường.
4. Loại bỏ secret khỏi source và lịch sử theo quy trình repository.
5. Kiểm tra artifact, cache và log có thể đã chứa bản sao.
6. Thay bằng workload identity hoặc secret manager phù hợp.

Chỉ xóa dòng secret khỏi file không làm credential cũ mất hiệu lực.

### 7.2. Không nhầm secret với cấu hình công khai

Một số giá trị như region, function name hoặc public API endpoint có thể là cấu hình thông thường. Không phải mọi chuỗi trông ngẫu nhiên đều là secret. Scanner cần suppression chính xác, có lý do và có thể audit.

Không đặt secret trong Docker build argument hoặc image layer. Dùng cơ chế secret mount của build tool khi thật sự cần secret lúc build, và tránh để secret trở thành một phần của artifact.

## 8. Kiểm tra Infrastructure as Code

Infrastructure as Code (IaC) mô tả tài nguyên cloud bằng file có thể review và version control. Với serverless, IaC có thể tạo:

- Lambda function, layer, alias và Function URL.
- API Gateway route, authorizer và permission invoke.
- IAM execution role và resource policy.
- SQS, SNS, EventBridge, Kinesis hoặc DynamoDB stream.
- Event source mapping, retry, DLQ và destinations.
- VPC, subnet, security group, endpoint và NAT.
- CloudWatch log group, alarm và retention.
- KMS key, secret reference và encryption configuration.

IaC scanner kiểm tra cấu hình trước khi deploy. Các công cụ phổ biến:

- **cfn-lint:** kiểm tra cú pháp và schema CloudFormation.
- **CloudFormation Guard:** policy as code cho template CloudFormation.
- **Checkov:** kiểm tra Terraform, CloudFormation, Kubernetes và nhiều loại IaC.
- **tfsec:** kiểm tra cấu hình Terraform; chức năng hiện được tích hợp trong hệ sinh thái Trivy.
- **cdk-nag:** áp dụng rule bảo mật và compliance cho AWS CDK.
- **OPA/Conftest:** kiểm tra policy trên file cấu hình hoặc kết quả render.

Không phải scanner nào cũng hiểu mọi macro, intrinsic function hoặc giá trị được tính lúc deploy. Cần kiểm tra template đã render/synthesize nếu công cụ hỗ trợ và bổ sung integration test sau deploy.

## 9. Các lỗi IaC thường gặp với Lambda

Một số cấu hình cần kiểm tra đặc biệt:

| Khu vực | Rủi ro | Kiểm tra |
|---|---|---|
| Function URL/API Gateway | Endpoint public ngoài ý muốn | Auth type, resource policy, authorizer |
| Execution role | Quyền wildcard hoặc quản trị | Action, Resource, Condition |
| Environment | Secret được nhúng trực tiếp | Secret reference và encryption |
| Logging | Không có retention hoặc thiếu quyền log | Log group, retention, execution role |
| SQS trigger | Message retry vô hạn hoặc mất sau timeout | Visibility timeout, DLQ, redrive |
| Stream trigger | Checkpoint và batch retry không phù hợp | Starting position, batch size, bisect/partial failure |
| EventBridge | Rule phát quá rộng hoặc target permission sai | Event pattern, target role/permission |
| Concurrency | Một function chiếm hết concurrency | Reserved/provisioned concurrency và account quota |
| Timeout/memory | Function timeout hoặc resource không phù hợp | Timeout, memory, ephemeral storage |
| VPC | Egress không cần thiết hoặc thiếu endpoint | Subnet, route, security group, endpoint |
| KMS | Key policy không cho workload hoặc quyền quá rộng | Key policy và encryption context |

### 9.1. Public access và xác thực

Function URL có thể được cấu hình để yêu cầu IAM authentication hoặc cho phép truy cập public tùy cấu hình. API Gateway có thể dùng JWT authorizer, Lambda authorizer hoặc IAM authorization. Pipeline nên yêu cầu cấu hình xác thực rõ ràng thay vì mặc định chấp nhận endpoint công khai.

Nếu endpoint public là yêu cầu sản phẩm, cần xác nhận authentication, rate limiting, WAF hoặc biện pháp chống lạm dụng phù hợp. Public không mặc nhiên là lỗi, nhưng phải là quyết định được review.

### 9.2. Execution role

Policy như Action "*" hoặc Resource "*" có thể cấp quyền vượt nhu cầu. Một số API không hỗ trợ resource-level permission và cần wildcard; trong trường hợp đó, phải giới hạn bằng condition hoặc tách statement, đồng thời ghi rõ lý do.

Không chặn mọi wildcard một cách máy móc vì có thể tạo false positive. Nhưng wildcard trên IAM administration, KMS decrypt, S3 delete hoặc Secrets Manager access cần review nghiêm ngặt.

### 9.3. Queue, retry và DLQ

Với SQS event source mapping, visibility timeout của queue phải được thiết kế phù hợp với timeout function và retry behavior. DLQ/redrive policy cần có ngưỡng nhận message lỗi và quy trình xử lý lại.

Với stream event source mapping, partial batch response, batch size và checkpoint có thể ảnh hưởng đến việc một record lỗi làm retry cả batch. IaC scan có thể phát hiện thiếu cấu hình, nhưng integration test cần xác minh behavior thực tế.

## 10. Kiểm tra policy bằng code

Policy as code cho phép diễn đạt quy tắc hạ tầng dưới dạng có thể chạy tự động. Ví dụ:

- Production Lambda không được public nếu chưa có exception.
- Execution role không được cấp iam:*.
- Function phải có timeout trong khoảng được phê duyệt.
- Log group phải có retention.
- Queue trigger phải có redrive policy.
- Storage bucket phải bật encryption và block public access.
- Secret không được hardcode trong template.
- Container image phải lấy từ registry được cho phép.

Ví dụ policy khái niệm với OPA/Rego:

~~~rego
package serverless.security

# Rego syntax in this example follows the classic rule form.
deny[msg] {
  input.resource_type == "aws_lambda_function"
  input.environment == "production"
  input.public_access == true
  not input.approved_public_endpoint
  msg := "Production Lambda must not be public without an approved exception"
}
~~~

Schema input ở đây là dữ liệu chuẩn hóa do pipeline cung cấp, không phải schema Rego mặc định của Terraform hay CloudFormation. Cần viết adapter hoặc dùng policy pack tương ứng với output của scanner.

Policy nên mô tả điều kiện và ngoại lệ cụ thể. Không tạo rule chỉ dựa trên tên resource nếu có thể đánh giá thuộc tính bảo mật thực tế.

## 11. Kiểm tra container image và artifact

Nếu Java Lambda được đóng gói dưới dạng container image, cần scan cả dependency ứng dụng lẫn package hệ điều hành trong image.

Các bước nên có:

- Build image từ base image được phê duyệt.
- Pin base image bằng tag có version hoặc digest.
- Quét OS package và Java dependency.
- Kiểm tra user, entrypoint, file permission và secret.
- Loại build tool/cache khỏi runtime image bằng multi-stage build.
- Chỉ push image đã qua gate vào registry triển khai.
- Lưu image digest trong metadata phát hành.

Ví dụ Trivy:

~~~bash
trivy image --severity HIGH,CRITICAL --exit-code 1 \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/orders:1.4.0
~~~

Command minh họa cho thấy pipeline có thể thất bại khi finding đạt ngưỡng. Cần pin Trivy version, cập nhật database và định nghĩa policy xử lý exception. Nếu dùng ZIP/JAR, scan filesystem và dependency report trước khi upload artifact.

Không phải mọi CVE trong OS package đều có thể khai thác trong Lambda; nhưng không nên tự bỏ qua mà không đánh giá runtime, reachability và khả năng khai thác.

## 12. SBOM: danh mục thành phần phần mềm

Software Bill of Materials (SBOM) là danh mục thành phần có trong artifact. SBOM có thể chứa:

- Tên package và version.
- Package URL (purl).
- Quan hệ dependency.
- License.
- Supplier hoặc publisher nếu có.
- Checksum và thông tin nhận dạng.
- Metadata về công cụ và thời điểm tạo.

Hai định dạng phổ biến là CycloneDX và SPDX. SBOM giúp truy vấn nhanh artifact nào có thư viện bị ảnh hưởng khi có CVE mới.

Ví dụ tạo SBOM bằng CycloneDX Maven Plugin:

~~~bash
mvn -B org.cyclonedx:cyclonedx-maven-plugin:APPROVED_VERSION:makeAggregateBom
~~~

Cần pin plugin version trong build thay vì dựa vào phiên bản ngầm định. Tên goal và tùy chọn có thể khác theo plugin version. Với Gradle, có plugin CycloneDX tương ứng; cần kiểm tra cấu hình và phạm vi dependency được đưa vào SBOM.

SBOM nên phản ánh artifact thực sự được phát hành. Nếu build có profile khác nhau hoặc dependency được shade vào uber JAR, cần xác nhận SBOM bao quát thành phần runtime cuối cùng.

## 13. Provenance, reproducible build và artifact signing

SBOM cho biết artifact chứa gì; provenance cho biết artifact được tạo ra như thế nào và từ đâu.

Provenance có thể ghi:

- Source repository và commit.
- Workflow hoặc builder đã tạo artifact.
- Build parameters và dependency resolution.
- Thời điểm build.
- Digest của artifact đầu ra.
- Danh tính workload đã thực hiện build.

Một build có thể tái lập giúp kiểm tra hai lần build từ cùng source và dependency có tạo ra artifact tương đương hay không. Để tăng khả năng tái lập:

- Pin JDK, Maven/Gradle và plugin.
- Pin dependency version và repository.
- Không tải dependency từ URL không kiểm soát.
- Chuẩn hóa timestamp nếu build tool hỗ trợ.
- Lưu checksum và artifact digest.
- Tách build artifact khỏi deploy môi trường.

### 13.1. Ký artifact

Ký artifact giúp bên triển khai xác minh artifact đến từ nguồn tin cậy và không bị thay đổi sau khi ký. Với Lambda ZIP, AWS Lambda Code Signing có thể kiểm tra package được ký bằng signing profile được tin cậy theo cấu hình function. Với container image, có thể dùng cơ chế ký image/attestation của chuỗi cung ứng phù hợp và policy xác minh tại thời điểm deploy.

Ký artifact không chứng minh code không có lỗ hổng. Nó xác nhận nguồn gốc và tính toàn vẹn theo khóa/chính sách đã cấu hình. Vẫn cần SAST, SCA, IaC scan và test.

## 14. Thiết kế quality gate

Quality gate là điều kiện để pipeline tiếp tục hoặc dừng. Gate cần rõ ràng và nhất quán.

Một ví dụ:

| Finding | Hành động gợi ý |
|---|---|
| Secret thật bị phát hiện | Chặn ngay, thu hồi credential |
| Critical vulnerability có khả năng khai thác trong runtime | Chặn phát hành |
| High vulnerability trong dependency runtime | Chặn hoặc yêu cầu exception có phê duyệt |
| IaC tạo public access ngoài policy | Chặn |
| IAM quyền quản trị không cần thiết | Chặn và yêu cầu review |
| Medium finding | Tạo issue, đặt thời hạn xử lý theo risk |
| Low/informational | Ghi nhận và theo dõi |
| License chưa rõ | Chuyển review trước khi phân phối |

Không áp dụng ngưỡng cứng chỉ dựa trên CVSS mà không xét môi trường. Một function public nhận payload không tin cậy có risk profile khác function nội bộ không có đường truy cập trực tiếp. Nhưng cũng không dùng "không reachable" như lý do bỏ qua nếu chưa có bằng chứng.

### 14.1. Baseline và finding mới

Repository cũ có thể đã có nhiều finding. Nếu chặn toàn bộ ngay lập tức, nhóm có thể không triển khai được dù thay đổi mới không làm tăng rủi ro.

Có thể:

- Tạo baseline ban đầu có owner.
- Chặn finding mới vượt ngưỡng.
- Đặt thời hạn xử lý finding cũ.
- Không cho phép baseline tăng tùy tiện.
- Báo cáo trend để giảm dần nợ bảo mật.

Baseline không phải nơi che giấu lỗ hổng. Mọi suppression phải có lý do, người chịu trách nhiệm và ngày hết hạn.

### 14.2. Quản lý exception

Một exception cần có:

- Finding ID và tài nguyên bị ảnh hưởng.
- Lý do chấp nhận rủi ro.
- Biện pháp giảm thiểu.
- Owner phê duyệt.
- Phạm vi artifact/environment.
- Ngày hết hạn hoặc điều kiện xem xét lại.

Không cho phép ignore all hoặc tắt scanner trong pipeline chỉ vì một rule gây false positive. Cần suppress đúng rule và đúng resource.

## 15. Pipeline mẫu cho Java Lambda

Một pipeline có thể chia thành các giai đoạn:

1. Checkout source và xác minh commit.
2. Setup JDK và build tool đã pin.
3. Compile, unit test và code quality.
4. SAST và secret scan.
5. SCA và license scan.
6. Validate/synthesize IaC.
7. IaC scanning và policy-as-code.
8. Build ZIP/JAR hoặc container image.
9. Generate SBOM và scan artifact.
10. Ký/attest artifact.
11. Deploy vào môi trường kiểm thử.
12. Integration test, smoke test và kiểm tra quyền.
13. Approve và promote cùng artifact sang production.

~~~mermaid
flowchart TD
    A["Commit / Pull request"] --> B["Compile + unit tests"]
    B --> C["SAST + secret scan"]
    B --> D["SCA + license"]
    A --> E["IaC validate + scan"]
    C --> F{"Security gates"}
    D --> F
    E --> F
    F --> G["Build immutable artifact"]
    G --> H["SBOM + image/package scan"]
    H --> I["Sign and attest"]
    I --> J["Deploy test environment"]
    J --> K["Integration / permission / smoke tests"]
    K --> L["Approve and promote"]
~~~

Không nên build lại artifact riêng cho production nếu có thể promote đúng artifact đã test. Nếu mỗi môi trường tạo artifact khác nhau, cần ghi nhận digest và chứng minh source/dependency vẫn tương ứng.

### 15.1. Ví dụ workflow GitHub Actions ở mức khung

~~~yaml
name: serverless-ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        # Replace the major tag with an approved full commit SHA in production.
        uses: actions/checkout@v4

      - name: Set up Java
        # Pin this action to a reviewed full commit SHA in production.
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Compile and test
        run: mvn -B clean verify

      - name: Dependency tree
        run: mvn -B dependency:tree

      - name: Secret scan
        run: gitleaks detect --source . --redact

      - name: IaC validation
        run: cfn-lint infrastructure/template.yaml

      - name: IaC security scan
        run: checkov -f infrastructure/template.yaml
~~~

Đây là skeleton minh họa. Workflow thực tế cần pin action bằng full commit SHA, pin tool version, cài scanner từ nguồn tin cậy và lưu report. Không cấp id-token: write, quyền deploy hoặc secret production cho job chỉ chạy kiểm tra pull request từ fork.

Các lệnh cfn-lint và checkov giả định repository có CloudFormation template ở đường dẫn đã nêu. Nếu dùng SAM, CDK hoặc Terraform, pipeline cần validate/synthesize/plan trước khi scan đúng artifact IaC tương ứng.

## 16. Quyền của pipeline và OIDC federation

CI runner cần quyền để đọc source, tải dependency, lưu artifact và có thể triển khai. Không nên lưu access key dài hạn trong secret của CI nếu nền tảng hỗ trợ OIDC federation.

Một luồng an toàn:

- Job kiểm tra source chỉ có quyền read repository.
- Job build chỉ có quyền ghi artifact vào kho build.
- Job deploy nhận token OIDC ngắn hạn và assume role chỉ được deploy môi trường được chỉ định.
- Production deployment có approval hoặc environment protection.
- Role deploy giới hạn function, stack và role có thể truyền bằng iam:PassRole.

Không cấp quyền deploy production cho mọi pull request. Job chạy code từ fork không nên nhận secret hoặc quyền cloud nhạy cảm.

## 17. Kiểm thử sau khi deploy vào môi trường tạm

Static scan không thể xác minh mọi cấu hình runtime. Một môi trường test tạm (ephemeral environment) giúp kiểm tra hành vi thật:

- Function có thể khởi tạo với runtime và dependency đã build.
- Trigger HTTP có authentication đúng.
- Queue event source mapping nhận và ACK message đúng.
- Retry và DLQ hoạt động khi handler thất bại.
- IAM role chỉ truy cập resource được phép.
- Secret được lấy từ secret manager và không xuất hiện trong log.
- Timeout, memory, concurrency và network hoạt động đúng.
- Trace/log/metric được phát theo cấu hình.
- Function không vô tình public endpoint.

Môi trường tạm cần được tạo và xóa có kiểm soát. Không dùng chung dữ liệu production hoặc secret production nếu không có phê duyệt. Dùng dữ liệu test và account/project riêng khi phù hợp.

### 17.1. Test quyền cho phép và quyền bị từ chối

Một integration test nên xác minh cả positive và negative cases:

- Function được đọc object trong prefix cần thiết.
- Function bị từ chối khi đọc bucket khác.
- Function được publish vào topic/queue đã chỉ định.
- Function bị từ chối khi gọi API quản trị IAM.
- Caller không có quyền tenant A không thể truy cập dữ liệu tenant B.

Chỉ kiểm tra thao tác thành công không chứng minh least privilege. Cần xác nhận quyền ngoài phạm vi thực sự bị từ chối.

## 18. Theo dõi finding sau khi phát hành

Bảo mật không kết thúc ở thời điểm deploy. Dependency mới có thể bị công bố CVE sau vài tháng; base image hoặc runtime có thể có bản vá; cấu hình hạ tầng có thể thay đổi.

Nên chạy:

- Dependency scan theo lịch, kể cả khi không có commit.
- Container image scan khi có advisory mới.
- IaC drift detection hoặc kiểm tra cấu hình cloud định kỳ.
- Secret scanning trên pull request và lịch sử theo chính sách.
- SBOM inventory để tìm artifact bị ảnh hưởng.
- Theo dõi runtime deprecation và bản vá nền tảng.

Nếu phát hiện CVE mới, truy ngược SBOM để biết function/version nào chứa dependency đó. Sau khi cập nhật, build và test artifact mới, rồi phát hành qua pipeline bình thường.

Không sửa trực tiếp resource production ngoài IaC nếu có thể tránh. Nếu cần hành động khẩn cấp, cập nhật source of truth và ghi nhận drift để tránh lần deploy sau ghi đè hoặc tái tạo cấu hình lỗi.

## 19. Những lỗi thường gặp

**Chỉ chạy unit test:** Không phát hiện CVE dependency hoặc IAM wildcard. Bổ sung SCA và IaC scan.

**Chỉ scan dependency trực tiếp:** Bỏ sót thư viện bắc cầu. Quét resolved dependency graph và artifact cuối.

**Không pin scanner/plugin:** Kết quả thay đổi theo phiên bản tool không kiểm soát. Pin version và cập nhật theo lịch.

**Bỏ qua secret đã xóa khỏi file:** Credential vẫn có thể nằm trong Git history hoặc artifact. Rotate/revoke trước, sau đó xử lý bản sao.

**Tin IaC scanner là đủ:** Macro hoặc giá trị runtime có thể không được phân tích đầy đủ. Kết hợp policy, template render và integration test.

**Chặn mọi finding theo CVSS đơn thuần:** Tạo nhiều false positive và làm pipeline mất hiệu lực. Xem xét reachability, exposure và context.

**Tắt scanner khi có lỗi:** Pipeline có thể âm thầm bỏ qua kiểm tra. Phân biệt scanner unavailable với no findings; nếu policy yêu cầu scan, lỗi scanner phải làm gate thất bại.

**Dùng quyền production trong pull request:** Code không tin cậy có thể lấy secret. Tách job và quyền theo môi trường.

**Build lại artifact khi promote:** Artifact production có thể khác artifact đã test. Promote đúng digest đã kiểm chứng.

**Không có SBOM:** Khó tìm nhanh function bị ảnh hưởng khi có CVE mới. Lưu SBOM gắn với từng artifact/version.

**Chỉ scan image mà không scan IaC:** Image sạch vẫn có thể chạy với role quá rộng hoặc endpoint public. Kiểm tra cả package và cấu hình hạ tầng.

**Không kiểm thử quyền bị từ chối:** Function có thể vô tình nhận quyền thừa. Thêm negative authorization tests.

## 20. Checklist bảo mật pipeline cho Java serverless

- [ ] JDK, Maven/Gradle wrapper, plugin và action được pin version.
- [ ] Compile và unit test chạy trên pull request.
- [ ] Có code quality check và SAST.
- [ ] Dependency trực tiếp và bắc cầu được quét SCA.
- [ ] License của dependency được kiểm tra theo chính sách.
- [ ] Secret scanning bao gồm source và lịch sử theo yêu cầu.
- [ ] IaC được validate và scan trước deploy.
- [ ] IAM role và resource policy được kiểm tra least privilege.
- [ ] Function URL/API Gateway authentication được review.
- [ ] Queue retry, visibility timeout, DLQ và event source mapping được kiểm tra.
- [ ] Timeout, memory, concurrency, VPC và logging có policy rõ ràng.
- [ ] Container image và deployment package được scan sau build.
- [ ] SBOM được tạo và lưu cùng artifact.
- [ ] Artifact có digest, provenance và cơ chế ký/xác minh phù hợp.
- [ ] Quality gate có ngưỡng, baseline và exception có owner/expiry.
- [ ] Pipeline job có quyền tối thiểu và dùng OIDC thay cho key dài hạn khi có thể.
- [ ] Pull request từ fork không nhận secret hoặc quyền deploy production.
- [ ] Có ephemeral environment và integration/negative permission tests.
- [ ] Artifact đã test được promote nguyên vẹn sang production.
- [ ] Có scheduled rescan và quy trình xử lý CVE mới.

## Kết luận

Pipeline serverless cần kiểm tra đồng thời source Java, dependency và hạ tầng. Code quality và SAST tìm lỗi trong chương trình; SCA và license scan kiểm soát thư viện; secret scanning ngăn credential lọt vào repository; IaC scanning và policy as code phát hiện cấu hình cloud nguy hiểm. Sau build, SBOM, artifact/image scanning, provenance và signing giúp xác định chính xác thành phần cùng nguồn gốc của bản phát hành.

Với Java Lambda, kiểm tra cần chú ý thêm execution role, public endpoint, event source mapping, retry/DLQ, concurrency, timeout, secret reference và network. Quality gate phải có tiêu chí rõ, ngoại lệ có thời hạn và quyền CI tối thiểu. Kết hợp static scan với integration test trên môi trường tạm, negative permission test và scheduled rescan để phát hiện rủi ro trước lẫn sau khi phát hành.

