# Quản lý state hạ tầng, phát hiện drift và rà soát thay đổi

Infrastructure as Code (IaC) mô tả hạ tầng mong muốn bằng code hoặc cấu hình có thể kiểm soát phiên bản. Khi một công cụ như Terraform hoặc OpenTofu tạo resource, nó cần biết resource nào trong cấu hình tương ứng với object nào đang tồn tại trên cloud. State là bản ghi giúp công cụ duy trì mối liên hệ đó qua nhiều lần plan và apply.

State không phải cấu hình mong muốn và cũng không phải bản sao đầy đủ, luôn chính xác của cloud. Nó lưu mapping, metadata và các thuộc tính cần thiết để công cụ tính toán thay đổi. Khi một người sửa resource trực tiếp trên portal, một automation khác thay đổi cấu hình, hoặc một thay đổi xảy ra ngoài pipeline IaC, state có thể không còn phản ánh thực tế. Sự khác biệt này được gọi là configuration drift hoặc infrastructure drift.

Quản lý state an toàn, phát hiện drift có chủ đích và rà soát plan trước khi apply là nền tảng để triển khai serverless ổn định. Một thay đổi nhỏ như sửa IAM policy, timeout của function, concurrency, queue retention hoặc database setting có thể ảnh hưởng đến bảo mật, độ sẵn sàng và chi phí của cả hệ thống.

Trong module **CLOUD_SERVERLESS**, người học phát triển và triển khai Java function được kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý quyền truy cập, trạng thái, retry, idempotency, cold start, mở rộng và chi phí. Bài này giải thích cách lưu và bảo vệ state, nhận biết drift, đọc plan và tổ chức quy trình review thay đổi hạ tầng.

## 1. Ba khái niệm cần phân biệt

Một quy trình IaC luôn có ít nhất ba góc nhìn:

1. **Desired configuration:** trạng thái mong muốn được mô tả trong file IaC, module, variable và provider configuration.
2. **State:** bản ghi mà công cụ IaC dùng để ánh xạ địa chỉ resource trong code với object thực tế, đồng thời lưu metadata và một số thuộc tính đã quan sát.
3. **Real infrastructure:** resource thực sự đang tồn tại trong cloud hoặc hệ thống đích tại thời điểm hiện tại.

Sơ đồ:

~~~mermaid
flowchart TD
    C[Desired configuration] --> P[Plan / diff]
    S[Stored state] --> P
    R[Real infrastructure] -->|Refresh / read| P
    P --> D{Reviewed changes}
    D -->|Approved| A[Apply]
    A --> R
    A --> S
~~~

Plan so sánh cấu hình mong muốn với state sau khi refresh từ provider. Công cụ dùng kết quả đó để đề xuất create, update, replace hoặc destroy. Apply thực hiện các thao tác đã được chấp thuận và cập nhật state sau khi provider trả kết quả.

Không nên xem state là bản sao tuyệt đối của real infrastructure. Một số thuộc tính không thể đọc lại, một số API trả dữ liệu eventual consistent, provider có thể chuẩn hóa giá trị và state có thể chưa được refresh kể từ lần thay đổi gần nhất.

## 2. State lưu những gì và tại sao cần state?

State thường chứa:

- Địa chỉ resource trong cấu hình, ví dụ module, resource type, resource name và instance key.
- ID của object thực tế do provider hoặc API cloud trả về.
- Các thuộc tính đã biết của resource, kể cả một số giá trị do provider tính toán.
- Quan hệ phụ thuộc và metadata cần để lập kế hoạch thay đổi.
- Thông tin provider/resource schema hoặc phiên bản định dạng state.
- Outputs và dữ liệu có thể nhạy cảm tùy cách cấu hình.

Ví dụ cấu hình:

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  runtime       = "java21"
  handler       = "com.example.OrderHandler"
  role          = aws_iam_role.lambda_exec.arn
  filename      = "build/orders.zip"
}
~~~

Trong state, công cụ cần biết resource address aws_lambda_function.orders tương ứng với Lambda function nào ở AWS, cùng các thuộc tính đã đọc được từ provider. Khi đổi tên resource trong code, công cụ cần biết đó là cùng một function được chuyển sang địa chỉ mới hay là một function khác cần tạo.

Nếu mất state, công cụ có thể không còn mapping để quản lý resource hiện hữu. Khi chạy plan, nó có thể đề xuất tạo mới resource đã tồn tại, hoặc không nhận ra resource cần cập nhật. Vì vậy, state phải được lưu bền vững, backup và bảo vệ như một dữ liệu vận hành quan trọng.

### State không phải backup của ứng dụng

State không chứa đầy đủ dữ liệu runtime của function, message trong queue, object trong bucket hay bản ghi database. Nó cũng không thay thế backup của database hoặc artifact. Backup state chỉ giúp khôi phục mapping IaC, không khôi phục dữ liệu nghiệp vụ đã mất.

## 3. State lifecycle: từ init đến apply

Một workflow Terraform/OpenTofu điển hình:

1. Khởi tạo working directory và backend.
2. Đọc provider/module và cấu hình.
3. Đọc state hiện tại từ backend.
4. Refresh các resource có thể đọc qua provider.
5. So sánh desired configuration với state đã refresh.
6. Tạo execution plan gồm các action cần thiết.
7. Người hoặc policy review plan.
8. Apply plan đã được chấp thuận.
9. Provider tạo/cập nhật/xóa resource và công cụ ghi state mới.

Các lệnh cơ bản:

~~~bash
terraform init
terraform validate
terraform plan
terraform apply
~~~

Với OpenTofu, lệnh CLI tương ứng thường dùng tiền tố tofu. Cần thống nhất một toolchain và phiên bản trong team; không nên để cùng một state bị thao tác bởi các phiên bản hoặc provider schema không tương thích.

### Refresh là gì?

Refresh là bước công cụ gọi provider để đọc trạng thái hiện tại của resource rồi cập nhật thông tin quan sát trong working state. Refresh giúp plan nhận ra một số thay đổi đã xảy ra bên ngoài IaC.

Refresh không tự sửa hạ tầng để khớp code. Nó chỉ giúp công cụ nhìn thấy trạng thái thực tế hơn trước khi lập plan. Plan sau refresh có thể đề xuất đưa resource về desired configuration, chấp nhận thay đổi bên ngoài bằng cách sửa code, hoặc thực hiện một thay đổi khác theo quyết định của người review.

## 4. Local state và remote backend

Mặc định, Terraform có thể lưu state cục bộ trong file terraform.tfstate. Cách này tiện cho thử nghiệm cá nhân nhưng không phù hợp với team hoặc pipeline production nếu không có quy trình đồng bộ và backup rõ ràng.

Remote backend lưu state ở một nơi dùng chung được hỗ trợ, ví dụ object storage hoặc dịch vụ quản lý state. Tùy backend, có thể có locking, versioning, encryption và access control.

| Tiêu chí | Local state | Remote backend |
|---|---|---|
| Chia sẻ giữa thành viên | Phải tự truyền file | Các thành viên truy cập cùng backend |
| Locking | Khó phối hợp nếu không có cơ chế ngoài | Có thể hỗ trợ lock tùy backend |
| Backup/versioning | Team phải tự tổ chức | Có thể dùng versioning hoặc lịch sử phiên bản |
| CI/CD | Dễ sai nếu runner có bản state khác nhau | Pipeline dùng cùng nguồn state |
| Bảo mật | Dễ bị commit hoặc gửi nhầm file | Có thể dùng IAM, encryption và audit |
| Phục hồi | Phụ thuộc backup local | Có thể khôi phục phiên bản backend nếu đã bật |

Remote backend không tự động bảo mật chỉ vì state nằm trên cloud. Cần cấu hình encryption, quyền truy cập, network policy, logging và backup theo yêu cầu hệ thống.

### Ví dụ backend S3

Ví dụ dưới đây minh họa backend S3 của Terraform. Cú pháp và tính năng lock phụ thuộc phiên bản Terraform; cần pin phiên bản tool và đọc tài liệu backend tương ứng trước khi dùng trong production.

~~~hcl
terraform {
  backend "s3" {
    bucket       = "company-iac-state"
    key          = "cloud-serverless/prod/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
~~~

Bucket và object key phải được tạo/chuẩn bị theo quy trình bootstrap. Identity chạy Terraform cần quyền đọc/ghi đúng object state và quyền lock cần thiết. Nếu backend version hỗ trợ state locking, hãy bật và kiểm tra nó; không giả định mọi backend hoặc phiên bản đều có cùng cơ chế.

Không đặt access key hoặc secret trong backend block rồi commit lên Git. Dùng workload identity, role assumption, environment credential hoặc secret manager phù hợp với môi trường chạy pipeline.

## 5. State locking và concurrent apply

State locking ngăn hai tiến trình cùng lúc ghi state của một workspace/backend key. Nếu hai pipeline cùng apply, chúng có thể đọc cùng một state cũ, thực hiện các thay đổi xung đột rồi ghi đè state của nhau. Kết quả có thể là state không còn khớp resource thật.

Khi backend hỗ trợ locking, Terraform/OpenTofu thường lấy lock trước khi thao tác có thể ghi state và giải phóng lock sau khi hoàn tất. Nếu lock đang được giữ, tiến trình khác cần chờ hoặc dừng theo chính sách.

Quy tắc vận hành:

- Không chạy apply đồng thời trên cùng state key.
- Không xóa lock thủ công chỉ vì thấy pipeline đang chờ.
- Xác định process/runner sở hữu lock và kiểm tra nó đã kết thúc hay chưa.
- Chỉ force-unlock khi chắc chắn lock bị bỏ lại và không còn thao tác đang chạy.
- Ghi nhận lock ID, workspace/backend key và lý do force-unlock trong audit.
- Tách state theo boundary triển khai nếu nhiều nhóm cần thay đổi độc lập.

Lệnh force-unlock có thể gây hại nếu dùng khi một apply khác vẫn đang chạy. Không tự động force-unlock trong CI chỉ vì timeout; hãy kiểm tra trạng thái runner và backend trước.

## 6. Bảo mật state: coi state như dữ liệu nhạy cảm

Một lỗi phổ biến là cho rằng thuộc tính được đánh dấu sensitive sẽ không nằm trong state. Trong Terraform, sensitive chủ yếu kiểm soát cách giá trị được hiển thị ở output/CLI; nó không tự động loại giá trị khỏi state hoặc plan file.

State có thể chứa:

- Connection string, password hoặc token nếu provider lưu giá trị đó.
- Secret environment variable của function.
- Database endpoint, resource ID và network topology.
- Private key hoặc credential nếu cấu hình/provider không xử lý đúng.
- Dữ liệu đầu vào hoặc output nhạy cảm được truyền qua resource.

Ví dụ:

~~~hcl
variable "database_password" {
  type      = string
  sensitive = true
}

resource "example_database_user" "app" {
  name     = "orders-service"
  password = var.database_password
}
~~~

Dù variable được đánh dấu sensitive, password vẫn có thể được lưu trong state tùy provider/resource. Hãy đọc tài liệu provider để hiểu attribute nào được lưu, có ephemeral/write-only mechanism hay không và cách xử lý secret đúng.

### Các biện pháp bảo vệ

- Bật encryption at rest cho backend và encryption in transit.
- Giới hạn quyền đọc state theo least privilege; quyền đọc state thường nhạy cảm gần bằng quyền apply.
- Không commit state, plan file hoặc backup state vào repository.
- Không đính kèm state/plan vào ticket, chat hoặc artifact công khai.
- Dùng secret manager hoặc identity ngắn hạn để cấp credential.
- Bật audit log cho truy cập và thay đổi backend.
- Thiết lập retention, versioning và backup có kiểm soát.
- Tách state theo môi trường và mức độ nhạy cảm.
- Redact log của pipeline và tránh in output nhạy cảm.

Plan file đã lưu cũng có thể chứa dữ liệu nhạy cảm. Hãy bảo vệ plan artifact giống state, giới hạn thời gian lưu và quyền tải xuống.

## 7. Phân tách state theo môi trường và ownership

Không nên để development, staging và production cùng ghi vào một state nếu chúng có vòng đời, quyền và lịch triển khai khác nhau.

Một cấu trúc backend key có thể là:

~~~text
state/
  cloud-serverless/
    dev/terraform.tfstate
    staging/terraform.tfstate
    prod/terraform.tfstate
~~~

Các môi trường nên có:

- Backend key hoặc state store riêng.
- Cloud account/subscription/project phù hợp.
- Credential và IAM role riêng.
- Variable và secret riêng.
- Quyền approve/apply khác nhau, đặc biệt với production.
- Backup, retention và audit theo yêu cầu môi trường.

### Workspace có phải ranh giới bảo mật không?

Terraform workspace cho phép nhiều state instance dùng chung một cấu hình và backend. Workspace hữu ích cho một số trường hợp tạo nhiều bản triển khai tương tự, nhưng không nên mặc định workspace là ranh giới bảo mật mạnh. Các workspace vẫn có thể chia sẻ code, credential và quyền backend.

Nếu production cần isolation rõ ràng, thường nên dùng backend key, account/project, role và pipeline riêng. Cách tổ chức chính xác phụ thuộc team ownership và yêu cầu audit.

### Chia nhỏ state theo boundary

Một state quá lớn có thể khiến plan chậm, lock lâu và tăng phạm vi ảnh hưởng khi apply. Chia state theo hệ thống hoặc lifecycle giúp các team triển khai độc lập hơn.

Ví dụ:

- Network state quản lý VPC, subnet, route và security boundary.
- Platform state quản lý shared runtime, logging và artifact storage.
- Application state quản lý Lambda/function, API, queue và permission.
- Data state quản lý database, bucket và backup policy.

Không chia state quá nhỏ đến mức phải truyền hàng chục output giữa các state. Remote state output có thể tạo coupling và mở rộng quyền đọc dữ liệu. Chỉ xuất những giá trị cần thiết, tránh xuất secret và cân nhắc dùng service discovery hoặc parameter store cho thông tin chia sẻ.

## 8. Drift là gì?

Drift xảy ra khi hạ tầng thực tế khác với trạng thái mong muốn trong IaC. Các nguyên nhân thường gặp:

- Người vận hành sửa trực tiếp resource trên portal hoặc CLI.
- Một pipeline khác hoặc công cụ khác thay đổi cùng resource.
- Auto-scaling, controller hoặc managed service thay đổi thuộc tính được provider quan sát.
- Một resource bị xóa hoặc sửa ngoài IaC.
- Provider/API chuẩn hóa giá trị hoặc thay đổi default.
- State cũ chưa được refresh sau một thời gian dài.

Ví dụ, code định nghĩa timeout Lambda là 30 giây, nhưng người vận hành sửa trực tiếp thành 60 giây trên console. Khi plan refresh được state mới, công cụ có thể phát hiện timeout thực tế là 60 trong khi desired configuration là 30 và đề xuất cập nhật về 30.

### Drift không phải lúc nào cũng là sự cố

Có ba tình huống cần phân biệt:

1. **Thay đổi ngoài ý muốn:** sửa nhầm, xâm nhập hoặc thao tác không theo quy trình. Cần khôi phục desired state và điều tra nguyên nhân.
2. **Thay đổi khẩn cấp có chủ đích:** người vận hành thay đổi để giảm tác động sự cố. Cần ghi nhận, review và đưa thay đổi hợp lệ trở lại code.
3. **Thay đổi do hệ thống tự điều chỉnh:** autoscaling hoặc service-managed field thay đổi bình thường. Cần xác định field đó có nên được IaC quản lý hay bỏ qua có kiểm soát.

Không nên tự động apply mọi drift về code trước khi hiểu tại sao nó xảy ra. Nếu thay đổi trực tiếp là một hotfix cần giữ lại, trước tiên cập nhật code để phản ánh trạng thái được chấp thuận, rồi mới apply các thay đổi tiếp theo.

## 9. Phát hiện drift bằng plan

Lệnh plan thông thường sẽ refresh các resource mà provider có thể đọc trước khi tính thay đổi, trừ khi dùng tùy chọn thay đổi hành vi refresh.

~~~bash
terraform plan
~~~

Plan có thể phát hiện:

- Resource tồn tại nhưng một thuộc tính khác với code.
- Resource đã bị xóa ngoài IaC và cần được tạo lại.
- Resource được tạo ngoài IaC chỉ được phát hiện nếu có data source, inventory hoặc quy trình discovery riêng; plan không tự quét toàn bộ account để tìm mọi object chưa được quản lý.
- Thay đổi cấu hình yêu cầu update hoặc replacement.
- Thay đổi output hoặc dependency kéo theo các action khác.

Plan không nhất thiết phát hiện mọi thay đổi. Provider có thể không expose một thuộc tính, API có thể eventual consistent, hoặc resource nằm ngoài state. Drift detection cũng phụ thuộc credential có quyền đọc đủ dữ liệu.

### Refresh-only plan

Khi muốn xem state khác gì so với hạ tầng thực tế mà không lập tức sửa hạ tầng, có thể dùng refresh-only mode:

~~~bash
terraform plan -refresh-only
~~~

Chế độ này tạo plan để cập nhật state/output theo giá trị provider đọc được, thay vì thay đổi resource nhằm khớp desired configuration. Review kết quả trước khi apply refresh-only plan.

Không dùng refresh-only như cách che drift. Nếu state được cập nhật để phản ánh thay đổi ngoài IaC, code vẫn có thể mô tả giá trị cũ. Lần plan bình thường tiếp theo có thể đề xuất thay đổi resource trở lại cấu hình cũ. Hãy quyết định thay đổi ngoài đó được chấp nhận và codify, hay cần rollback.

### Tránh tắt refresh trong quy trình thường ngày

Tùy chọn refresh=false có thể làm plan nhanh hơn trong một số tình huống, nhưng plan sẽ dựa vào state cũ và có thể bỏ qua drift. Chỉ dùng khi hiểu rõ tác động, ví dụ một bước chẩn đoán có kiểm soát; không dùng như cách mặc định để tránh lỗi provider hoặc che thay đổi ngoài IaC.

## 10. Quy trình xử lý drift có kiểm soát

Khi phát hiện drift:

1. **Khoanh vùng:** resource address, backend key, workspace, account/Region và thời điểm plan.
2. **Xác minh thực tế:** kiểm tra resource trên provider/API bằng quyền read-only phù hợp.
3. **Tìm nguồn thay đổi:** audit log, cloud activity log, pipeline run, ticket sự cố và người thực hiện.
4. **Phân loại:** thay đổi trái phép, hotfix được chấp thuận, thay đổi tự động hay provider normalization.
5. **Chọn hướng xử lý:** đưa resource về desired state hoặc cập nhật IaC để giữ trạng thái mới.
6. **Review tác động:** kiểm tra replacement, downtime, IAM, network, data loss và cost.
7. **Apply qua pipeline:** thực hiện bằng plan được review và người có quyền approve.
8. **Chạy plan lại:** xác nhận không còn drift ngoài dự kiến.
9. **Ghi audit:** lưu nguyên nhân, quyết định, commit và execution ID.

### Ví dụ: timeout của Java function bị sửa ngoài IaC

Desired configuration:

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  timeout       = 30
  memory_size   = 1024
}
~~~

Người vận hành đổi timeout trên AWS Console thành 60 giây trong lúc điều tra timeout downstream. Plan sau đó có thể hiển thị update để đưa timeout về 30.

Nếu hotfix 60 giây được chấp thuận, cập nhật code thành 60 và review các tác động liên quan như duration billing, retry và timeout của API Gateway. Nếu hotfix không được chấp thuận, giữ code 30 và apply plan sau khi xác nhận không có dependency nào cần thay đổi cùng lúc.

## 11. Plan là bản đề xuất thay đổi, không phải lệnh vô hại

Plan cho biết công cụ dự định làm gì. Review cần đọc action ở từng resource, không chỉ nhìn dòng tổng kết “Plan: n to add, m to change, k to destroy”.

Các dấu hiệu thường gặp trong plan text:

| Ký hiệu/hành động | Ý nghĩa | Cần chú ý |
|---|---|---|
| + create | Tạo resource mới | IAM, public exposure, quota và cost |
| ~ update in-place | Sửa resource hiện tại | Có downtime, restart hoặc thay đổi behavior không? |
| - destroy | Xóa resource | Có mất dữ liệu hoặc làm gián đoạn không? |
| -/+ replace | Xóa rồi tạo lại theo thứ tự plan | Có downtime, đổi endpoint hoặc mất stateful data không? |
| +/− create then destroy | Tạo mới trước rồi xóa cũ khi provider hỗ trợ | Có thể cần quota tạm thời và kiểm tra migration |
| known after apply | Giá trị chỉ có sau khi apply | Kiểm tra dependency và output downstream |

Dấu hiển thị có thể khác giữa phiên bản CLI và provider. Hãy đọc action detail trong plan thay vì chỉ dựa vào một ký hiệu.

### Những câu hỏi khi review

- Resource nào được tạo, sửa, thay thế hoặc xóa?
- Có thay đổi IAM policy, trust relationship hoặc public network exposure không?
- Có thay đổi function runtime, handler, memory, timeout, environment variable hoặc concurrency không?
- Queue retention, visibility timeout, retry, DLQ hoặc event source mapping có thay đổi không?
- Database, bucket, encryption key hoặc log retention có bị thay đổi/xóa không?
- Resource replacement có gây downtime, đổi ARN/endpoint hoặc mất dữ liệu không?
- Có thay đổi ở Region/account/workspace không?
- Provider version hoặc module version có đổi cùng lúc không?
- Cost có tăng do memory, provisioned capacity, replication hoặc logging không?
- Plan có chứa giá trị nhạy cảm hoặc unknown cần kiểm tra thêm không?

## 12. Lưu plan và apply đúng plan đã review

Với pipeline production, có thể tạo saved plan:

~~~bash
terraform plan -out=tfplan
terraform show tfplan
~~~

Sau khi reviewer chấp thuận đúng artifact đó, pipeline có thể apply saved plan:

~~~bash
terraform apply tfplan
~~~

Saved plan giúp apply thực hiện đúng quyết định đã review thay vì tính lại một plan mới không được xem. Tuy nhiên, plan artifact cần được bảo vệ vì có thể chứa dữ liệu nhạy cảm. Không commit tfplan vào Git hoặc lưu ở artifact public.

Plan có thể trở nên stale nếu state hoặc hạ tầng thay đổi sau khi tạo. Terraform có thể từ chối apply stale plan; khi đó cần tạo plan mới và review lại. Không tìm cách ép apply một plan đã lỗi thời.

Quy trình an toàn thường là:

- Plan chạy trên commit cụ thể và backend/workspace cụ thể.
- Lưu artifact có quyền truy cập hạn chế, thời hạn ngắn và gắn commit SHA.
- Reviewer xem toàn bộ action, đặc biệt destroy/replacement và IAM.
- Trước apply, xác nhận plan vẫn hợp lệ và không có deployment khác đang thay đổi cùng state.
- Apply cùng artifact đã review; nếu cần tạo lại plan thì yêu cầu review lại.
- Ghi lại người approve, commit, plan summary, backend key và kết quả apply.

## 13. Đọc plan trong CI bằng exit code và JSON

Terraform hỗ trợ detailed exit code cho plan trong automation:

~~~bash
terraform plan -detailed-exitcode
~~~

Thông thường:

- Exit code 0: plan thành công và không có thay đổi.
- Exit code 1: lỗi khi tạo plan.
- Exit code 2: plan thành công và có thay đổi cần review.

CI cần xử lý ba trường hợp riêng. Không coi exit code 2 là pipeline failure; đó là tín hiệu có thay đổi. Ngược lại, không bỏ qua exit code 1.

Có thể xuất JSON để policy engine hoặc công cụ review phân tích:

~~~bash
terraform show -json tfplan > tfplan.json
~~~

JSON plan có thể chứa giá trị nhạy cảm, kể cả khi output text đã redacted. Bảo vệ file, hạn chế log và chỉ đưa các trường cần thiết vào báo cáo. Không in toàn bộ JSON lên CI log.

Policy-as-code có thể kiểm tra các quy tắc như:

- Không tạo security group mở SSH/RDP ra Internet nếu không có ngoại lệ.
- Không public bucket chứa dữ liệu riêng tư.
- Không xóa database production nếu thiếu approval.
- Lambda role chỉ được cấp quyền cần thiết.
- Encryption và log retention phải được bật.
- Resource có tag owner, environment và cost center.

Policy engine hỗ trợ chặn plan không đạt quy tắc, nhưng vẫn cần con người review các thay đổi có ngữ cảnh nghiệp vụ.

## 14. Import resource đã tồn tại vào state

Có thể có resource được tạo thủ công hoặc bởi một hệ thống khác mà team muốn đưa vào quản lý IaC. Import tạo mapping giữa resource address trong cấu hình và object ID ở provider.

Với Terraform hiện đại, có thể khai báo import block:

~~~hcl
import {
  to = aws_lambda_function.orders
  id = "orders-api"
}
~~~

Sau đó viết resource configuration tương ứng, chạy plan để xem công cụ sẽ import và có đề xuất thay đổi gì. Không apply cho đến khi hiểu plan; nếu cấu hình khác xa resource hiện tại, plan có thể đề xuất update hoặc replacement ngay sau import.

CLI import truyền thống cũng có thể được dùng tùy phiên bản/tool:

~~~bash
terraform import aws_lambda_function.orders orders-api
~~~

Import không tự tạo đầy đủ cấu hình mong muốn trong file HCL. Sau import, cần viết hoặc generate configuration phù hợp, review plan và kiểm tra state mapping.

Không import cùng một object vào nhiều resource address trong cùng state nếu không có mô hình provider hỗ trợ rõ ràng. Mapping trùng có thể khiến hai resource block cùng quản lý một object và tạo hành vi không dự đoán.

## 15. Đổi tên, di chuyển hoặc ngừng quản lý resource

Refactor IaC có thể đổi tên resource hoặc chuyển resource sang module khác. Nếu không khai báo migration, công cụ có thể nghĩ resource cũ cần destroy và resource mới cần create.

### Moved block

Khi đổi địa chỉ resource nhưng vẫn là cùng object, có thể khai báo moved block:

~~~hcl
moved {
  from = aws_lambda_function.orders
  to   = module.orders.aws_lambda_function.this
}
~~~

Công cụ dùng mapping này để chuyển địa chỉ trong state thay vì tạo mới resource. Cần xác nhận phiên bản Terraform/OpenTofu hỗ trợ cú pháp và semantics tương ứng.

### State mv

Lệnh state mv có thể thay đổi địa chỉ resource trong state:

~~~bash
terraform state mv \
  aws_lambda_function.orders \
  module.orders.aws_lambda_function.this
~~~

Thực hiện khi đã backup state, khóa quy trình triển khai và review địa chỉ nguồn/đích. Với thay đổi lâu dài trong repository, moved block thường giúp migration có thể tái lập và được review cùng code.

### Ngừng quản lý mà không xóa resource

Có trường hợp muốn IaC ngừng quản lý một resource nhưng vẫn giữ object trong cloud, ví dụ chuyển ownership sang team hoặc tool khác. Terraform có thể hỗ trợ removed block với tùy chọn destroy=false ở các phiên bản phù hợp; state rm cũng có thể bỏ mapping mà không gọi API xóa resource.

~~~bash
terraform state rm aws_lambda_function.legacy
~~~

Lệnh state rm chỉ bỏ resource khỏi state; nó không xóa resource thật. Sau đó, nếu resource block vẫn còn trong code, plan có thể đề xuất tạo một resource mới. Hãy xóa/điều chỉnh cấu hình và phối hợp ownership trước khi bỏ mapping.

Không dùng state rm để “sửa” drift hoặc làm biến mất resource khỏi plan. Đây là thao tác thay đổi ownership mapping, cần review và audit.

## 16. Các lệnh state hữu ích và cách dùng an toàn

| Lệnh | Mục đích | Lưu ý |
|---|---|---|
| terraform state list | Liệt kê resource address trong state | Không hiển thị toàn bộ giá trị |
| terraform state show ADDRESS | Xem thuộc tính resource | Có thể in secret; tránh log công khai |
| terraform state pull | Đọc state hiện tại từ backend | Output nhạy cảm; chỉ dùng trong môi trường bảo vệ |
| terraform state mv | Chuyển địa chỉ resource trong state | Backup và review mapping trước |
| terraform state rm | Bỏ mapping khỏi state | Không xóa resource thật; code còn block có thể tạo lại |
| terraform import | Import resource hiện hữu | Cần cấu hình resource và review plan sau import |

Trước mọi thao tác sửa state:

1. Dừng pipeline hoặc thông báo team để tránh concurrent apply.
2. Xác nhận backend, workspace, account và Region.
3. Kiểm tra lock và người đang sở hữu lock.
4. Tạo backup state được mã hóa và giới hạn quyền.
5. Ghi lại resource address và object ID.
6. Thực hiện đúng một thao tác có phạm vi nhỏ.
7. Chạy plan và xác minh mapping.
8. Ghi audit và thông báo cho team.

Không chỉnh sửa JSON state bằng tay như một cách thông thường. State format có schema, lineage, serial và metadata nội bộ; thay đổi sai có thể khiến công cụ từ chối đọc hoặc quản lý nhầm resource.

## 17. Backup và phục hồi state

Remote backend có versioning hoặc state history giúp khôi phục khi state bị ghi sai hoặc thao tác nhầm. Cần kiểm tra:

- Versioning đã bật và retention có đủ dài không?
- Backup có được mã hóa và bảo vệ quyền đọc không?
- Có thể khôi phục một version mà không ghi đè nhầm state mới hơn không?
- Ai có quyền restore và ai phê duyệt?
- Sau restore, làm sao xác minh state khớp với resource thật?

Quy trình phục hồi cơ bản:

1. Tạm dừng mọi pipeline có thể ghi state.
2. Xác định backend key, workspace và thời điểm sự cố.
3. Tải bản state hiện tại và phiên bản backup vào nơi an toàn để đối chiếu.
4. Xác định state version nào phù hợp với hạ tầng thực tế; không chỉ chọn file cũ nhất hoặc mới nhất.
5. Khôi phục bằng cơ chế backend/tool được hỗ trợ và giữ audit.
6. Chạy plan refresh để kiểm tra mapping với provider.
7. Review mọi action trước khi apply.
8. Mở lại pipeline sau khi owner xác nhận.

Không dùng state backup cũ một cách mù quáng. Nếu resource đã được tạo/xóa sau thời điểm backup, restore có thể khiến mapping không còn đúng. Cần đối chiếu provider ID và real infrastructure trước khi apply.

## 18. CI/CD cho plan review và apply

Một pipeline IaC có thể chia thành hai giai đoạn:

~~~mermaid
flowchart TD
    A[Pull request / commit] --> B[Format and validate]
    B --> C[Init and plan]
    C --> D[Publish protected plan artifact]
    D --> E[Review diff and policy checks]
    E --> F{Approved?}
    F -- No --> G[Revise or close change]
    F -- Yes --> H[Verify plan and state are current]
    H --> I[Apply reviewed plan]
    I --> J[Post-apply plan / verify]
    J --> K[Audit and monitoring]
~~~

Các bước thường có:

- Format và validate cấu hình.
- Pin provider/module version và kiểm tra dependency lock file.
- Init backend bằng identity phù hợp.
- Plan trên đúng environment/state.
- Chạy policy check và security scan.
- Xuất plan artifact bảo mật.
- Reviewer đọc action và approve.
- Apply bằng identity chỉ có quyền cần thiết.
- Chạy kiểm tra sau apply và ghi audit.

### Tách quyền plan và apply

Plan thường cần quyền đọc state và đọc metadata resource từ provider. Apply cần thêm quyền tạo/sửa/xóa resource. Có thể dùng role khác nhau để người review hoặc pipeline plan không có quyền thay đổi production.

Dù plan có thể cần quyền đọc state chứa secret, không nên coi role plan là vô hại. Hạn chế quyền đọc backend và bảo vệ output/artifact.

### Tránh nhiều pipeline cùng thay đổi một state

Dùng concurrency group hoặc lock ở CI để serialize apply theo backend key. Có thể cho nhiều pull request chạy plan read-only, nhưng trước apply cần xác nhận plan không stale và state lock được lấy thành công. Một pipeline khác apply giữa lúc review có thể khiến plan cũ không còn hợp lệ.

## 19. Rủi ro đặc thù với serverless resources

Khi review plan của module serverless, chú ý các resource có thể tạo ảnh hưởng lớn:

| Resource/field | Rủi ro khi thay đổi | Câu hỏi review |
|---|---|---|
| Function runtime/handler | Deployment lỗi hoặc function không khởi động | Artifact có tương thích runtime và handler không? |
| Memory/timeout | Latency, OOM và chi phí thay đổi | Đã benchmark và kiểm tra timeout của trigger chưa? |
| Reserved concurrency | Throttling hoặc bảo vệ downstream không đủ | Capacity có phù hợp peak và database không? |
| Provisioned concurrency | Chi phí cố định và alias/version routing | Traffic có gọi đúng qualifier và capacity có READY không? |
| IAM role/policy | Mở rộng quyền hoặc function mất quyền | Có least privilege và trust policy đúng không? |
| Queue visibility/retry/DLQ | Message duplicate, backlog hoặc mất khả năng retry | Timeout, max receive count và poison queue có tương thích không? |
| Event source mapping | Tăng/giảm tốc độ tiêu thụ | Batch, parallelization và partial failure đã được kiểm tra chưa? |
| API Gateway route/authorizer | Endpoint mở sai hoặc client bị từ chối | Method, auth, CORS và throttling có đúng không? |
| Bucket/database replacement | Có thể mất dữ liệu | Có backup, retention và migration plan không? |
| Log retention/encryption | Tăng chi phí hoặc giảm khả năng điều tra | Policy có phù hợp compliance và incident response không? |

Một plan có thể chỉ hiển thị một thay đổi nhỏ trong HCL nhưng provider có thể phải replace resource hoặc thay đổi nhiều thuộc tính phụ thuộc. Luôn xem chi tiết action và đọc tài liệu provider khi có replacement.

## 20. Drift detection tự động và cảnh báo

Có thể chạy plan định kỳ hoặc sau thay đổi nhạy cảm để phát hiện drift. Ví dụ:

- CI chạy nightly plan với quyền read-only và không apply.
- Cloud audit log phát hiện resource bị sửa ngoài pipeline.
- Policy engine so sánh cấu hình security quan trọng.
- Dashboard theo dõi số lượng drift và tuổi drift chưa xử lý.

Một báo cáo drift nên chứa:

- Environment/backend key và commit đang được triển khai.
- Resource address và resource ID.
- Field thay đổi, giá trị desired và observed (đã redact).
- Thời điểm phát hiện và nguồn thay đổi nếu biết.
- Mức độ rủi ro và người chịu trách nhiệm.
- Quyết định: revert, codify, ignore có chủ đích hoặc điều tra thêm.

Không tự động apply ngay khi drift detection phát hiện thay đổi. Một thay đổi có thể là hotfix hợp lệ hoặc thay đổi do autoscaling. Cảnh báo và review giúp phân biệt trước khi sửa.

### Ignore changes có chủ đích

Terraform lifecycle có ignore_changes để bỏ qua thay đổi ở một số thuộc tính do hệ thống khác quản lý. Đây là công cụ phù hợp khi ownership được xác định rõ, ví dụ autoscaler quản lý desired capacity của một resource.

Không dùng ignore_changes để che drift chưa điều tra. Ghi chú lý do, field được bỏ qua, owner của field và cách kiểm tra thay đổi đó. Nếu một thuộc tính quan trọng bị bỏ qua, cần có telemetry hoặc policy khác để giám sát.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Commit state vào Git | Lộ secret và xung đột state | Dùng remote backend hoặc lưu trữ bảo vệ |
| Nghĩ sensitive nghĩa là không lưu trong state | Credential có thể vẫn nằm trong state/plan | Đọc provider schema và bảo vệ backend |
| Dùng local state cho team production | Mỗi người có mapping khác nhau | Remote backend và locking |
| Cho nhiều pipeline apply đồng thời | State ghi đè hoặc resource conflict | Lock và serialize apply |
| Force-unlock khi chưa kiểm tra | Apply đang chạy có thể mất coordination | Xác minh runner và lock owner |
| Apply ngay sau drift detection | Có thể ghi đè hotfix hoặc gây outage | Phân loại và review nguồn thay đổi |
| Tắt refresh để plan sạch | Bỏ qua drift thực tế | Dùng refresh bình thường và xử lý lỗi provider |
| Dùng workspace như ranh giới bảo mật | Quyền và backend vẫn có thể dùng chung | Tách account/backend/role cho environment nhạy cảm |
| Không review replacement/destroy | Mất dữ liệu hoặc downtime | Đọc action chi tiết và có approval |
| Lưu plan artifact công khai | Lộ dữ liệu nhạy cảm | Bảo vệ và giới hạn retention |
| Import resource nhưng không viết config | Plan có thể đề xuất thay đổi lớn | Hoàn thiện desired configuration và review |
| Dùng state rm để sửa drift | Mất mapping, có thể tạo resource trùng | Chỉ dùng cho ownership migration có kế hoạch |
| Restore backup state cũ không đối chiếu | Mapping không khớp resource thật | Đối chiếu ID/provider và plan trước apply |
| Ignore_changes để che mọi drift | Mất khả năng phát hiện thay đổi ngoài ý muốn | Chỉ ignore field có ownership rõ |

## 22. Checklist quản lý state và review thay đổi

Trước khi áp dụng IaC trong production, hãy xác nhận:

- **Backend:** state được lưu bền vững ở backend đúng environment và có backup/versioning phù hợp.
- **Locking:** backend hỗ trợ locking hoặc có cơ chế serialize tương đương; không có apply đồng thời.
- **Encryption:** state và plan được mã hóa khi truyền/lưu.
- **Access:** quyền đọc state được giới hạn; quyền apply tách biệt và có audit.
- **Secrets:** không commit credential; sensitive output không bị hiểu nhầm là đã loại secret khỏi state.
- **Isolation:** dev/staging/prod có state key, identity và quyền phù hợp.
- **Drift:** plan refresh được chạy theo lịch hoặc trigger phù hợp; drift có owner và quy trình xử lý.
- **Review:** plan được đọc theo từng resource action, đặc biệt destroy, replacement, IAM và data resource.
- **Plan artifact:** gắn commit, backend/workspace, được bảo vệ và chưa stale trước apply.
- **Import/refactor:** mapping resource được chuyển bằng import/moved/state migration có review.
- **Recovery:** có backup và runbook phục hồi state; không sửa JSON thủ công.
- **Serverless impact:** kiểm tra runtime, memory, timeout, concurrency, IAM, trigger, queue, DLQ và log retention.
- **Post-apply:** chạy plan/verification sau deploy và ghi nhận kết quả vào audit.

## 23. Kết luận

State là mapping có giá trị cao giúp công cụ IaC biết resource nào trong code tương ứng với object nào ngoài cloud. Nó cần được lưu bền vững, khóa khi ghi, mã hóa, backup và bảo vệ quyền đọc. Desired configuration, state và real infrastructure là ba góc nhìn khác nhau; drift xuất hiện khi chúng không còn đồng nhất.

Quy trình an toàn là refresh và plan để phát hiện khác biệt, xác minh nguồn thay đổi, phân loại drift, review action rồi mới apply. Saved plan giúp apply đúng nội dung đã review nhưng phải được bảo vệ và kiểm tra stale. Import, moved, state mv và state rm là các thao tác thay đổi ownership mapping, cần backup và audit.

Với hạ tầng serverless, review kỹ các thay đổi về IAM, runtime, memory, timeout, concurrency, queue, DLQ, API route và database. Khi state được quản lý có kỷ luật và mọi thay đổi đi qua plan review, team có thể triển khai lặp lại, phát hiện cấu hình lệch và giảm rủi ro vận hành.
