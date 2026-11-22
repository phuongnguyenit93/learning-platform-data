# Áp dụng policy as code cho hạ tầng serverless

Hạ tầng serverless được tạo và thay đổi liên tục qua Terraform, CloudFormation, deployment pipeline, console hoặc API. Nếu mỗi nhóm tự quyết định cách cấu hình function, API, queue, role và storage, các sai lệch về bảo mật, mạng, logging, retention hoặc chi phí rất dễ xuất hiện. Một function có thể vô tình mở public ingress, dùng execution role quá rộng, thiếu dead-letter destination hoặc không có log đủ lâu để điều tra sự cố.

**Policy as code** đưa các quy tắc quản trị vào dạng có thể đọc, review, kiểm thử và thực thi tự động. Thay vì chỉ mô tả “function phải có timeout”, “không được public nếu thiếu xác thực” trong tài liệu, tổ chức định nghĩa policy để pipeline hoặc hệ thống kiểm soát có thể đánh giá cấu hình trước khi triển khai và phát hiện drift sau khi chạy.

Trong serverless Java, policy cần bao phủ toàn bộ đường đi của workload: function/runtime, API trigger, event source, execution identity, network, secrets, database, storage, observability và deployment artifact. Policy tốt có owner, phạm vi rõ, lý do nghiệp vụ, cách kiểm thử và quy trình ngoại lệ. Bài học trình bày vòng đời policy as code, các lớp guardrail, ví dụ OPA/Rego và Terraform, tích hợp CI/CD, kiểm soát runtime drift và lưu bằng chứng tuân thủ.

## 1. Policy as code là gì?

Policy as code là cách biểu diễn quy tắc kỹ thuật hoặc quản trị bằng cấu trúc máy có thể đánh giá tự động. Policy có thể được viết bằng Rego/OPA, Sentinel, Cedar, JSON/YAML schema, rule engine của cloud provider hoặc công cụ policy cho IaC.

Một policy thường có:

- **Subject:** ai hoặc thành phần nào chịu quy tắc, ví dụ Lambda function, Cloud Run service hoặc service account.
- **Resource:** tài nguyên được tạo hay thay đổi.
- **Condition:** điều kiện phải thỏa, ví dụ ingress phải private hoặc timeout không vượt giới hạn.
- **Effect:** allow, deny, warn hoặc require approval.
- **Scope:** environment, account/project, region, workload class hoặc data classification.
- **Owner và version:** nhóm chịu trách nhiệm và phiên bản policy.
- **Evidence:** dữ liệu chứng minh policy đã được đánh giá và kết quả ra sao.

Ví dụ quy tắc:

~~~text
Mọi production function phải:
- dùng execution identity riêng theo workload;
- có timeout và memory trong khoảng được phê duyệt;
- không chứa plaintext secret trong environment variables;
- ghi log có cấu trúc và có retention;
- có trigger authentication phù hợp;
- có retry/DLQ strategy cho event processing;
- chỉ được cấp network egress và IAM permissions cần thiết.
~~~

Điểm quan trọng là policy phải có thể được áp dụng nhất quán cho nhiều đội và nhiều pipeline. Một checklist thủ công có thể hữu ích, nhưng khó phát hiện sai lệch khi số lượng function và deployment tăng.

## 2. Policy as code giải quyết vấn đề gì?

Serverless làm giảm công việc quản lý máy chủ, nhưng không loại bỏ trách nhiệm quản trị. Các cấu hình có thể thay đổi độc lập và được triển khai qua nhiều công cụ.

Policy as code giúp:

- Ngăn cấu hình rủi ro trước khi deploy.
- Chuẩn hóa baseline giữa development, staging và production.
- Kiểm tra IAM, ingress, network, encryption và logging.
- Đưa yêu cầu compliance vào pull request và pipeline.
- Phát hiện drift giữa IaC và cấu hình runtime.
- Lưu kết quả kiểm tra làm bằng chứng audit.
- Tạo ngoại lệ có thời hạn và có người phê duyệt.
- Giảm việc review lặp lại các quy tắc phổ biến.

Policy as code không tự chứng minh một ứng dụng tuân thủ toàn bộ quy định pháp lý. Nó kiểm tra các điều kiện kỹ thuật đã được chuyển thành policy. Tổ chức vẫn phải xác định yêu cầu, phạm vi, dữ liệu nhạy cảm, trách nhiệm và cách chứng minh kiểm soát hoạt động hiệu quả.

## 3. Các lớp policy trong serverless

Nên chia policy theo lớp để dễ gán owner và xác định nơi thực thi.

| Lớp | Ví dụ kiểm soát | Thời điểm đánh giá |
|---|---|---|
| Organization/account | Chặn region không được phép, hạn chế public resource | Organization guardrail / deployment |
| Infrastructure as Code | Timeout, memory, ingress, encryption, tags | Pull request / plan |
| Identity and access | Least privilege, trust policy, service account | Plan, IAM analysis và runtime |
| Network | Ingress, egress, private connectivity | Plan và runtime |
| API/trigger | Authentication, authorization, rate limit | API configuration và integration test |
| Event processing | Retry, DLQ, batch size, idempotency strategy | Plan và consumer validation |
| Data protection | Encryption, retention, classification, backup | Provisioning và runtime |
| Observability | Log, metric, trace, audit và retention | Deployment và runtime |
| Artifact/supply chain | Image digest, signature, dependency scan | Build và release |
| Cost/capacity | Max instances, concurrency, budget tags | Plan, deployment và FinOps review |

Không nên đặt mọi quy tắc trong một file lớn không có phân loại. Nhóm policy theo domain giúp người review hiểu lý do deny và tìm đúng owner để sửa.

## 4. Preventive, detective và corrective controls

Policy có thể được thực thi ở nhiều giai đoạn:

- **Preventive:** chặn cấu hình không hợp lệ trước khi tạo hoặc cập nhật resource.
- **Detective:** quét resource đang chạy để tìm drift hoặc vi phạm.
- **Corrective:** tạo ticket, yêu cầu remediation hoặc tự sửa khi hành động đó an toàn và đã được phê duyệt.

~~~mermaid
flowchart TD
    Change[Code or infrastructure change]
    PR[Pull request policy checks]
    Plan[Evaluate IaC plan]
    Deploy[Deploy approved change]
    Runtime[Runtime configuration scan]
    Alert[Violation finding / alert]
    Fix[Remediate or approved exception]

    Change --> PR --> Plan
    Plan -->|Pass| Deploy
    Plan -->|Deny| Change
    Deploy --> Runtime
    Runtime -->|Compliant| Monitor[Continuous monitoring]
    Runtime -->|Violation| Alert --> Fix
    Fix --> Runtime
~~~

Một policy chỉ chạy trong CI có thể bỏ sót thay đổi trực tiếp trên cloud console. Một scanner chỉ chạy hàng ngày có thể phát hiện vi phạm quá muộn. Kết hợp preventive và detective controls để bao phủ cả thay đổi được quản lý lẫn drift ngoài pipeline.

Corrective automation cần thận trọng. Ví dụ tự động xóa public endpoint hoặc thu hồi role có thể làm gián đoạn dịch vụ. Với hành động có tác động lớn, tạo finding và yêu cầu owner xử lý theo SLA thường an toàn hơn.

## 5. Xây dựng policy theo risk và data classification

Không phải mọi function đều cần cùng một cấu hình. Một function xử lý dữ liệu công khai có thể có yêu cầu khác với function xử lý payment, identity hoặc dữ liệu cá nhân.

Xác định workload profile:

| Profile | Ví dụ | Policy trọng tâm |
|---|---|---|
| Internal utility | Cron dọn dữ liệu nội bộ | Private ingress, workload identity, audit |
| Public API | HTTP endpoint cho khách hàng | Authentication, authorization, rate limit, WAF/API protection |
| Event processor | Queue consumer | Retry, DLQ, idempotency, encryption, least privilege |
| Sensitive workload | Payment hoặc dữ liệu cá nhân | Data classification, private networking, key policy, audit, retention |
| Batch/reporting | Export dữ liệu lớn | Timeout, memory, concurrency, storage encryption, cost limits |

Dùng label hoặc metadata chuẩn như environment, service, owner, data_classification, criticality và cost_center. Policy có thể dựa vào những thuộc tính này để áp dụng mức kiểm soát phù hợp.

Không cho caller tự gán classification để hạ mức kiểm soát. Classification cần đến từ registry hoặc pipeline đã được tin cậy và có quyền thay đổi riêng.

## 6. Viết policy có thể kiểm thử

Một policy tốt nên có:

1. Tên và ID ổn định.
2. Mô tả ngắn, rõ ràng.
3. Mục tiêu kiểm soát và rủi ro được giảm thiểu.
4. Phạm vi tài nguyên.
5. Điều kiện allow/deny/warn.
6. Mức độ nghiêm trọng.
7. Hướng dẫn remediation.
8. Owner.
9. Phiên bản và ngày hiệu lực.
10. Bộ test positive, negative và boundary.

Ví dụ metadata policy:

~~~yaml
id: SVL-SEC-004
name: production-function-requires-authentication
version: 2
severity: high
scope:
  environments:
    - production
resources:
  - serverless.http_function
control:
  description: Public HTTP function must require approved authentication.
  rationale: Prevent unauthenticated access to protected application operations.
remediation: Configure API authentication or restrict ingress to an approved identity-aware gateway.
owner: platform-security
exception:
  allowed: true
  requires: security-approval
  max_days: 30
~~~

Metadata này minh họa một contract nội bộ. Tổ chức cần thống nhất schema và validator; không giả định mọi policy engine đều hiểu các field trên theo cùng một cách.

### Policy phải có thông điệp remediation

Thông báo “policy failed” không giúp developer sửa lỗi. Finding nên cho biết:

- Resource nào vi phạm.
- Field nào sai.
- Giá trị hiện tại và điều kiện mong đợi.
- Lý do policy tồn tại.
- Cách sửa.
- Link đến tài liệu hoặc owner.

Ví dụ:

~~~text
DENY SVL-IAM-002
Resource: aws_lambda_function.payment-worker
Field: role
Finding: execution role grants wildcard administrative actions.
Expected: workload-specific role with scoped actions and resources.
Remediation: replace broad policy with permissions required by payment-worker.
~~~

Không đưa secret, token hoặc dữ liệu nhạy cảm vào finding hay CI log.

## 7. OPA và Rego trong pipeline

Open Policy Agent (OPA) là policy engine có thể đánh giá input JSON theo policy Rego. Với Infrastructure as Code, pipeline có thể chuyển Terraform plan hoặc cấu hình đã render thành JSON rồi yêu cầu OPA trả kết quả allow/deny.

Ví dụ policy Rego theo cú pháp Rego v1:

~~~rego
package serverless.guardrails

import rego.v1

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.environment == "production"
    input.config.tracing_mode != "Active"

    message := sprintf(
        "%s must enable active tracing in production",
        [input.name],
    )
}

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.environment == "production"
    input.config.timeout < 3

    message := sprintf(
        "%s timeout must be at least 3 seconds",
        [input.name],
    )
}

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.config.environment_variables[_] == "PLAINTEXT_SECRET"

    message := sprintf(
        "%s appears to contain a forbidden plaintext secret marker",
        [input.name],
    )
}
~~~

Ví dụ cuối chỉ minh họa một marker kiểm thử, không phải cách phát hiện secret production. Phát hiện secret cần dùng secret scanner và rule dựa trên nguồn dữ liệu phù hợp; policy không nên cố suy luận secret chỉ từ một giá trị string.

Trong Rego, deny là tập các finding. Pipeline quyết định thất bại nếu tập này không rỗng. Tùy phiên bản OPA và convention, có thể dùng cú pháp deny contains ... if { ... } hoặc package/query contract khác; cố định version và kiểm thử cú pháp trong repository.

### Input cần được chuẩn hóa

Không nên để mỗi pipeline gửi một JSON shape khác nhau. Chuẩn hóa input có các field:

- Resource type và resource address.
- Environment/account/project/region.
- Module hoặc workload metadata.
- Cấu hình cần kiểm tra.
- Identity và policy attachment.
- Source revision và plan digest.

Nếu policy nhận thiếu field, phải xử lý theo hướng fail closed với control quan trọng hoặc trả lỗi input rõ ràng. Không được coi field thiếu là mặc định compliant.

## 8. Ví dụ OPA: chặn function public không có xác thực

Một policy đơn giản:

~~~rego
package serverless.network

import rego.v1

deny contains message if {
    input.kind == "http_function"
    input.environment == "production"
    input.ingress == "public"
    input.authentication != "required"

    message := sprintf(
        "production HTTP function %s is public without required authentication",
        [input.name],
    )
}
~~~

Test policy:

~~~rego
package serverless.network_test

import rego.v1
import data.serverless.network

test_public_production_function_without_auth_is_denied if {
    result := network.deny with input as {
        "kind": "http_function",
        "environment": "production",
        "ingress": "public",
        "authentication": "none",
        "name": "orders-api",
    }

    count(result) == 1
}

test_authenticated_public_function_is_allowed if {
    result := network.deny with input as {
        "kind": "http_function",
        "environment": "production",
        "ingress": "public",
        "authentication": "required",
        "name": "orders-api",
    }

    count(result) == 0
}
~~~

Test cần bao phủ cả trường hợp thiếu authentication field, giá trị không hợp lệ và environment khác production. Nếu endpoint public được phép vì lý do sản phẩm, policy cần yêu cầu API gateway hoặc control tương đương thay vì bỏ kiểm soát toàn bộ.

## 9. Terraform plan và policy evaluation

Terraform plan có thể được xuất thành JSON để policy engine đánh giá trước khi apply:

~~~bash
terraform init
terraform validate
terraform plan -out=tfplan
terraform show -json tfplan > tfplan.json
opa eval --data policies/ --input tfplan.json "data.serverless.guardrails.deny"
~~~

Đây là lệnh minh họa. Trong pipeline thực tế, cần:

- Pin phiên bản Terraform và OPA.
- Kiểm tra exit code và kết quả query.
- Xử lý resource change actions như create, update, delete.
- Không chỉ kiểm tra cấu hình sau cùng nếu policy cần biết resource đang bị xóa hay thay thế.
- Bảo vệ plan artifact và tránh để secret lọt vào JSON hoặc log.
- Dùng adapter để ánh xạ Terraform JSON sang input contract ổn định nếu policy không trực tiếp hiểu plan format.
- Lưu digest của plan và policy bundle đã dùng để đánh giá.

OPA eval trả kết quả query; pipeline phải diễn giải kết quả và chủ động fail khi có deny. Không giả định chỉ cần chạy lệnh là Terraform tự động bị chặn.

### Kiểm tra resource thay đổi

Một policy cho function có thể cần kiểm tra:

- Runtime và architecture được hỗ trợ.
- Timeout, memory và ephemeral storage trong giới hạn.
- Environment variables không chứa secret.
- Execution role không có wildcard admin.
- Tracing/logging được bật.
- Ingress và VPC/egress phù hợp.
- Reserved/max concurrency không vượt quota.
- DLQ hoặc failure destination có cấu hình khi cần.

Chỉ đánh giá resource có thay đổi nếu pipeline có chủ đích đó. Với baseline toàn bộ hệ thống, cần thêm inventory/runtime scan để kiểm tra resource cũ không xuất hiện trong plan.

## 10. Policy cho IAM và workload identity

Least privilege là một trong những kiểm soát quan trọng nhất cho serverless. Mỗi function nên có execution identity theo workload hoặc nhóm chức năng có cùng trust boundary.

Policy IAM có thể kiểm tra:

- Không dùng role mặc định quá rộng.
- Không cấp wildcard action/resource nếu không có lý do được phê duyệt.
- Trust policy chỉ cho phép service principal và source phù hợp.
- Không cho phép function assume role không liên quan.
- Quyền đọc secret chỉ giới hạn secret cần dùng.
- Quyền ghi object giới hạn bucket/prefix.
- Quyền publish chỉ giới hạn queue/topic cần thiết.
- Quyền decrypt giới hạn key và encryption context nếu provider hỗ trợ.
- Quyền sửa IAM hoặc tạo credential bị cấm trừ workload quản trị chuyên biệt.

Không thể xác định mọi quyền quá rộng chỉ bằng tìm chuỗi *. Một số action cần wildcard resource theo semantics của provider; policy cần hiểu action/resource model và có allowlist ngoại lệ cụ thể.

### Ví dụ Terraform: role tối thiểu

~~~hcl
data "aws_iam_policy_document" "payment_worker" {
  statement {
    sid    = "ReadPaymentQueue"
    effect = "Allow"

    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]

    resources = [
      aws_sqs_queue.payment_events.arn
    ]
  }

  statement {
    sid    = "ReadPaymentSecret"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      aws_secretsmanager_secret.payment_api.arn
    ]
  }
}
~~~

Đây là ví dụ quyền tối thiểu cho một consumer cụ thể. Resource và actions thực tế cần khớp API/SDK, encryption key policy, event source mapping và cách runtime lấy secret. Không copy policy này sang mọi function.

## 11. Policy cho network và ingress

HTTP function có thể được gọi trực tiếp từ Internet, qua API gateway, internal load balancer hoặc service-to-service identity. Policy cần phân biệt public network reachability với authentication.

Một endpoint public không nhất thiết không an toàn nếu nó có authentication, authorization, rate limiting và protection phù hợp. Ngược lại, endpoint private vẫn cần xác thực service identity và authorization.

Các guardrail thường gặp:

- Production endpoint chỉ public khi có use case được duyệt.
- Public endpoint phải có authentication hoặc được bảo vệ bởi gateway có identity-aware policy.
- Không mở ingress rộng cho internal-only workload.
- Egress đến database/internal service phải dùng route và security rule được phê duyệt.
- Chặn metadata/link-local và dải nội bộ không cần thiết cho outbound URL fetch.
- Không cho function tự do truy cập Internet nếu workload không cần.
- Gắn policy vào VPC connector, firewall, security group hoặc egress gateway phù hợp.
- Tách network policy theo environment và data classification.

Không nhầm ingress policy với authorization ở tầng ứng dụng. Gateway có thể xác thực caller, nhưng function vẫn phải kiểm tra quyền trên tenant/resource theo contract.

## 12. Policy cho API trigger và event source

### HTTP/API

Policy có thể yêu cầu:

- Authentication method được phê duyệt.
- Authorization và scope/role rõ ràng.
- Rate limit, quota hoặc WAF policy theo mức rủi ro.
- CORS chỉ mở origin cần thiết nếu browser access được hỗ trợ.
- Request size và timeout hợp lý.
- TLS và custom domain configuration đúng baseline.
- Không để debug endpoint hoặc admin route public ngoài ý muốn.

CORS không thay thế authentication và không ngăn server-to-server request.

### Queue và event

Policy có thể yêu cầu:

- Encryption at rest và transport theo khả năng provider.
- Resource policy giới hạn producer/consumer.
- Retry hoặc redelivery behavior được khai báo.
- DLQ/failure destination cho luồng cần quarantine.
- Visibility/ack deadline phù hợp timeout xử lý.
- Batch size và concurrency nằm trong downstream capacity.
- Event schema/version và idempotency contract được định nghĩa.
- Retention và replay window phù hợp yêu cầu nghiệp vụ.
- Không đưa secret hoặc dữ liệu nhạy cảm vào event payload nếu không cần.

Không bắt buộc mọi queue phải có DLQ theo một con số chung. Policy cần dựa trên criticality và cách phục hồi; nếu một event source có failure destination khác, khai báo control tương đương.

## 13. Policy cho data protection và secrets

Serverless thường dùng environment variable để truyền cấu hình, nhưng secret cần được quản lý bằng secret manager hoặc cơ chế credential provider của nền tảng.

Guardrail có thể kiểm tra:

- Không có secret literal trong IaC, source hoặc deployment artifact.
- Function chỉ đọc secret được cấp quyền.
- Secret reference dùng version/rotation policy được phê duyệt.
- Storage/database/queue bật encryption theo classification.
- KMS key policy không cấp quyền rộng.
- Backup và retention đáp ứng yêu cầu.
- Log không chứa token, credential hoặc payload nhạy cảm.
- Public object access bị chặn trừ bucket được thiết kế public.
- Data residency/region được kiểm soát theo classification.

Secret scanner và IaC policy bổ sung cho nhau. Secret scanner tìm chuỗi có khả năng là credential; policy kiểm tra resource có tham chiếu secret manager và identity có quyền đọc đúng secret hay không.

## 14. Policy cho runtime, timeout và concurrency

Cấu hình runtime ảnh hưởng bảo mật, reliability và chi phí.

Một baseline có thể kiểm tra:

| Thuộc tính | Ví dụ policy |
|---|---|
| Runtime | Chỉ dùng Java LTS/runtime còn được hỗ trợ |
| Timeout | Không vượt giới hạn theo workload class |
| Memory/CPU | Trong khoảng đã benchmark và phê duyệt |
| Concurrency | Không vượt capacity downstream và quota |
| Min/max instances | Phù hợp SLO và budget |
| Tracing | Bật theo criticality và privacy policy |
| Logging | Structured logs, retention và redaction |
| Ephemeral storage | Giới hạn theo nhu cầu và data handling |
| Architecture | Dùng architecture đã kiểm thử và được hỗ trợ |

Không đặt cùng một timeout cho mọi function. HTTP request, short event handler và batch export có profile khác nhau. Dùng workload class để policy kiểm tra giá trị theo loại công việc.

### Giới hạn concurrency bảo vệ dependency

Nếu mỗi function invocation mở connection database, scale-out không kiểm soát có thể làm cạn database. Policy có thể yêu cầu:

- Max/reserved concurrency được khai báo.
- Tổng connection budget của workload không vượt quota.
- Consumer concurrency có giới hạn.
- Retry và batch size không tạo amplification.
- Max instances phù hợp downstream capacity.

Policy cần đánh giá quan hệ giữa số instance và connection pool, không chỉ kiểm tra từng giá trị độc lập.

## 15. Policy cho artifact và software supply chain

Function Java thường được đóng gói thành JAR hoặc container image. Policy nên kiểm tra nguồn gốc artifact trước khi triển khai.

Các kiểm soát:

- Build từ pipeline được tin cậy.
- Dependency được scan CVE và license theo policy.
- Container image dùng digest bất biến thay vì tag mutable.
- Artifact có provenance/attestation nếu hệ thống hỗ trợ.
- Image/JAR được ký và verify theo quy trình.
- Không chứa file secret hoặc debug configuration.
- Base image và Java runtime còn được hỗ trợ.
- Chỉ deploy artifact đã qua test và approval cần thiết.
- Release record liên kết commit, build, artifact digest và deployment.

Không chỉ dựa vào tag như latest hoặc tên version trong file. Digest xác định nội dung artifact cụ thể và giúp pipeline chứng minh thứ đã scan chính là thứ được deploy.

## 16. Tích hợp policy vào CI/CD

Một pipeline có thể chạy policy ở các điểm:

1. **Source stage:** secret scan, dependency/license scan, static analysis.
2. **Pull request:** validate metadata và IaC policy.
3. **Plan stage:** đánh giá tài nguyên sắp tạo/sửa/xóa.
4. **Build stage:** kiểm tra artifact, image digest và provenance.
5. **Pre-deploy:** xác minh approval, exception và policy bundle version.
6. **Post-deploy:** kiểm tra cấu hình thực tế và smoke test.
7. **Continuous scan:** phát hiện drift và vi phạm mới.

~~~mermaid
flowchart TD
    Commit[Commit / pull request]
    Source[Secret and dependency scans]
    IaC[Terraform validate and plan]
    Policy[OPA / IaC policy checks]
    Build[Build and sign Java artifact]
    Approval[Approval and exception check]
    Deploy[Deploy serverless resources]
    Verify[Runtime config and smoke checks]
    Monitor[Continuous compliance scan]

    Commit --> Source --> IaC --> Policy
    Policy -->|Deny| Feedback[Return findings to developer]
    Policy -->|Pass| Build --> Approval
    Approval -->|Approved| Deploy --> Verify --> Monitor
    Approval -->|Missing approval| Feedback
~~~

### Fail fast nhưng phải có kết quả giải thích được

Policy violation nghiêm trọng nên chặn pipeline. Warning có thể cho phép deploy nhưng phải tạo finding hoặc yêu cầu review. Pipeline cần trả kết quả máy đọc được để tổng hợp dashboard và audit.

Không để policy engine lỗi mạng hoặc bundle không tải được rồi mặc định allow cho production. Xác định fail-closed hay fail-open theo mức độ kiểm soát; với security-critical guardrail, fail closed thường phù hợp hơn. Có thể cache policy bundle đã ký để tránh phụ thuộc network ở mọi lần đánh giá.

## 17. Policy bundle, versioning và rollout

Policy cũng là phần mềm và có thể chứa bug. Một thay đổi policy sai có thể chặn hàng loạt release hoặc cho phép cấu hình nguy hiểm.

Quản lý policy như artifact:

- Đặt version rõ ràng.
- Review bằng pull request.
- Có test positive/negative/boundary.
- Pin version trong pipeline hoặc policy bundle digest.
- Ghi version policy trong deployment evidence.
- Phân biệt policy đang ở draft, warn-only và enforce.
- Có kế hoạch rollback policy bundle.
- Thông báo trước thay đổi ảnh hưởng nhiều đội.

### Rollout theo giai đoạn

1. **Observe:** chạy policy trên resource hiện tại, chỉ báo finding.
2. **Warn:** pipeline hiển thị warning và remediation.
3. **Enforce on new resources:** chặn resource mới vi phạm.
4. **Enforce on updates:** chặn cập nhật làm tăng rủi ro.
5. **Remediate legacy:** lập kế hoạch xử lý resource cũ theo SLA.
6. **Continuous enforcement:** quét drift và tái đánh giá định kỳ.

Không bật deny toàn bộ cho policy mới nếu chưa biết số lượng legacy violation và đường remediation. Tuy nhiên, không kéo dài warn-only vô thời hạn cho kiểm soát critical.

## 18. Runtime drift và continuous compliance

IaC chỉ mô tả trạng thái mong muốn. Resource thực tế có thể bị thay đổi qua console, API hoặc một pipeline khác. Đây là configuration drift.

Ví dụ:

- Developer mở public ingress để debug rồi quên đóng.
- Role được thêm quyền wildcard thủ công.
- Log retention bị giảm.
- DLQ bị xóa hoặc event source mapping đổi retry policy.
- Secret reference được thay bằng plaintext environment variable.
- Max instances tăng vượt budget hoặc database capacity.

Cách kiểm soát:

- Lấy inventory cấu hình thực tế theo account/project/region.
- Chuẩn hóa resource thành input schema.
- Chạy cùng policy bundle dùng trong CI.
- Ghi finding, severity, owner và thời điểm phát hiện.
- So sánh với IaC state và deployment record.
- Theo dõi remediation SLA.
- Tạo ticket hoặc auto-remediate nếu action an toàn.

Runtime scan nên chạy theo chu kỳ phù hợp với risk và sau các thay đổi quan trọng. Với tài nguyên public hoặc IAM nhạy cảm, có thể cần event-driven detection thay vì chờ lần scan hàng ngày.

## 19. Ngoại lệ policy có kiểm soát

Không phải mọi workload đều có thể tuân thủ cùng một rule. Một function public không có authentication có thể là endpoint health check công khai đã được giới hạn; một function batch có thể cần timeout dài hơn baseline.

Ngoại lệ phải có:

- Policy ID và resource scope cụ thể.
- Lý do nghiệp vụ và rủi ro được chấp nhận.
- Owner chịu trách nhiệm.
- Người phê duyệt phù hợp với severity.
- Biện pháp bù trừ.
- Ngày bắt đầu và ngày hết hạn.
- Ticket hoặc evidence liên quan.
- Kế hoạch quay về baseline.

Ví dụ:

~~~yaml
exception:
  policy_id: SVL-NET-004
  resource: production/health-probe
  reason: Public probe is required by an external monitoring provider.
  compensating_controls:
    - response_contains_no_sensitive_data
    - strict_rate_limit
    - dedicated_health_route
  owner: platform-operations
  approved_by: security-team
  expires_at: 2026-12-15
~~~

Đây là ví dụ metadata nội bộ. Exception cần được validator xác minh và gắn với đúng resource; không cho phép wildcard scope hoặc thời hạn vô hạn. Khi hết hạn, pipeline/runtime scan phải tự động đánh dấu vi phạm nếu resource vẫn chưa về baseline.

### Không dùng exception để bỏ qua mọi policy

Policy không thể được miễn trừ nếu điều đó vi phạm luật, hợp đồng hoặc yêu cầu bắt buộc của tổ chức. Những kiểm soát non-waivable cần được phân loại rõ và engine phải từ chối exception cho chúng.

## 20. Audit evidence và compliance reporting

Để audit có thể tái dựng một quyết định, lưu lại:

- Source commit và pull request.
- Terraform plan digest hoặc deployment manifest.
- Artifact digest/provenance.
- Policy bundle version/digest.
- Input resource snapshot đã được làm sạch.
- Kết quả allow/deny/warn và finding ID.
- Exception và approval record.
- Người hoặc workload identity thực hiện deploy.
- Timestamp, environment, account/project và region.
- Post-deploy scan result và remediation status.

Không lưu secret hoặc raw payload nhạy cảm trong evidence. Dùng immutable storage hoặc audit service theo yêu cầu retention và quyền truy cập.

Bằng chứng cần nối được policy decision với đúng artifact và resource đã deploy. Nếu pipeline đánh giá plan A nhưng deploy plan B, evidence không chứng minh được resource thực tế đã qua kiểm tra.

## 21. Kiểm thử policy

Policy cần được test giống code ứng dụng.

### Positive tests

- Function hợp lệ với auth, timeout, role và logging đúng.
- Event consumer có retry/DLQ theo profile.
- Secret được tham chiếu qua secret manager.
- Runtime và region nằm trong allowlist.
- Exception hợp lệ, còn hạn và đúng resource.

### Negative tests

- Production HTTP function public không auth.
- Execution role có quyền admin không được duyệt.
- Environment variable chứa marker secret test.
- Storage public ngoài policy.
- Function thiếu log hoặc timeout vượt giới hạn.
- Event source không có failure handling bắt buộc.
- Artifact dùng mutable tag hoặc thiếu provenance.
- Resource deploy sang region không được phép.
- Exception hết hạn hoặc scope rộng.

### Boundary tests

- Timeout đúng min/max.
- Memory ở sát ngưỡng.
- Resource không có field tùy chọn.
- Environment không phải production.
- Function internal-only nhưng không có public endpoint.
- Policy input có resource bị replace/delete.
- Hai policy cùng tạo finding cho một resource.
- Policy bundle cũ và mới đánh giá cùng một plan.

OPA có thể dùng lệnh opa test để chạy unit tests Rego. Ngoài unit test, nên có integration test xác minh pipeline thực sự fail khi policy deny và pass khi compliant.

## 22. Những lỗi triển khai policy as code thường gặp

- **Policy chỉ nằm trong tài liệu:** khó kiểm tra nhất quán; đưa rule có thể tự động hóa vào engine.
- **Một policy chung cho mọi workload:** có thể quá chặt hoặc quá lỏng; dùng workload class và data classification.
- **Không có owner:** finding không được xử lý; gắn team chịu trách nhiệm.
- **Input schema không ổn định:** cùng policy cho kết quả khác giữa pipeline; chuẩn hóa contract.
- **Thiếu field lại mặc định allow:** cấu hình chưa rõ có thể lọt qua; fail closed với control quan trọng.
- **Chỉ kiểm tra Terraform plan:** bỏ sót console drift; bổ sung runtime scan.
- **Chỉ quét runtime:** phát hiện muộn sau khi resource đã public; dùng preventive gate.
- **Policy deny không có remediation:** developer không biết sửa gì; trả finding cụ thể.
- **Không pin policy version:** khó tái dựng quyết định cũ; lưu bundle digest.
- **Bật enforce đột ngột:** chặn nhiều workload legacy; rollout observe/warn/enforce.
- **Exception không hết hạn:** ngoại lệ trở thành cấu hình vĩnh viễn; yêu cầu owner và expiration.
- **Chỉ tìm wildcard trong IAM:** có false positive và false negative; đánh giá action/resource semantics.
- **Coi policy pass là compliance hoàn chỉnh:** policy chỉ kiểm tra control được mã hóa; cần audit và kiểm tra quy trình.
- **Lưu secret trong policy input/evidence:** tạo rò rỉ mới; redact và giới hạn dữ liệu.
- **Không test policy engine failure:** pipeline có thể fail-open ngoài ý muốn; xác định rõ behavior khi engine unavailable.
- **Không gắn kết quả với artifact thực tế:** scan một artifact nhưng deploy artifact khác; dùng digest/provenance.

## 23. Quy trình áp dụng policy as code cho Java serverless

Có thể triển khai theo thứ tự:

1. Lập danh mục function, API, event source, identity, data store và network dependency.
2. Phân loại workload theo environment, criticality và data classification.
3. Xác định baseline security, reliability, privacy và cost cho từng profile.
4. Viết policy với ID, owner, severity, scope và remediation.
5. Chuẩn hóa IaC/runtime input schema.
6. Viết positive, negative và boundary tests.
7. Chạy policy ở chế độ observe để đánh giá legacy violations.
8. Tích hợp policy vào pull request và Terraform plan.
9. Chặn production deploy khi critical policy deny.
10. Gắn policy bundle digest và result với artifact/deployment.
11. Quét runtime để phát hiện drift.
12. Quản lý exception có phê duyệt, scope và expiry.
13. Tạo dashboard compliance và remediation SLA.
14. Review policy khi runtime, provider, threat model hoặc quy định thay đổi.
15. Định kỳ diễn tập policy engine outage và quy trình rollback bundle.

## 24. Ghi nhớ

Policy as code biến yêu cầu quản trị serverless thành quy tắc có thể review, test và thực thi tự động. Các policy cần bao phủ IaC, IAM, network, API trigger, event source, data protection, runtime, artifact, observability và cost guardrails.

Kết hợp preventive checks trong pull request/CI với detective scans ở runtime để phát hiện cả cấu hình mới lẫn drift. Dùng policy engine như OPA/Rego với input schema ổn định, version bundle được pin và finding có remediation rõ ràng. Rollout theo giai đoạn để xử lý legacy resources, đồng thời quản lý exception có owner, approval và expiry.

Lưu bằng chứng nối policy decision với đúng plan, artifact và resource được triển khai. Policy pass là bằng chứng một tập kiểm soát kỹ thuật đã được đánh giá; nó không thay thế việc xác định nghĩa vụ pháp lý, đánh giá rủi ro và audit toàn diện. Với Java serverless, policy as code giúp các function HTTP, message và event được triển khai nhất quán, có thể kiểm chứng và duy trì an toàn khi hệ thống mở rộng.

