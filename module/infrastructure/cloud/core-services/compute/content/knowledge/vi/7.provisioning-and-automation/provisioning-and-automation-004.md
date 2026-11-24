# Tính idempotent và quản lý trạng thái khi cấp phát tài nguyên

Cấp phát tài nguyên cloud thường diễn ra qua nhiều bước: tạo mạng, subnet, máy ảo, đĩa, địa chỉ IP, quyền truy cập và các dịch vụ phụ thuộc. Một lệnh có thể bị gửi lại do timeout, pipeline chạy lại hoặc người vận hành thực hiện lại sau khi không nhận được phản hồi. Nếu mỗi lần chạy đều tạo tài nguyên mới, hệ thống có thể xuất hiện máy ảo trùng lặp, địa chỉ IP dư thừa, chi phí tăng và cấu hình khó kiểm soát.

**Idempotency** giúp một thao tác có thể được thực hiện lặp lại mà vẫn đưa hệ thống về cùng trạng thái mong muốn. **Quản lý trạng thái (state management)** giúp công cụ cấp phát biết tài nguyên logic trong cấu hình đang tương ứng với tài nguyên thực tế nào, thao tác nào đã hoàn tất và thay đổi tiếp theo cần thực hiện là gì.

Bài học này thuộc chương **Cấp phát và tự động hóa** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong bối cảnh đó, idempotency và quản lý state là nền tảng để tự động hóa việc tạo, cập nhật và hủy tài nguyên một cách an toàn.

## 1. Idempotency là gì?

Một thao tác được gọi là **idempotent** khi thực hiện một lần hay lặp lại nhiều lần đều tạo ra cùng kết quả trạng thái cuối cùng.

Ví dụ, yêu cầu bảo đảm một máy ảo có trạng thái **running** có thể được thực hiện nhiều lần. Nếu máy đã chạy, lần gọi tiếp theo không nên tạo thêm máy ảo khác; hệ thống chỉ cần xác nhận trạng thái hiện tại đã đáp ứng yêu cầu.

Ngược lại, thao tác “tạo thêm một máy ảo” mỗi lần được gọi là thao tác không idempotent nếu mỗi lần đều sinh ra một máy mới.

### 1.1. Idempotency khác với chạy đúng một lần

Trong hệ thống phân tán, client có thể gửi request nhưng mất kết nối trước khi nhận phản hồi. Client không biết server đã xử lý request hay chưa. Nếu gửi lại, thao tác có thể được thực hiện lần thứ hai.

Idempotency giải quyết tình huống này bằng cách bảo đảm việc lặp lại không tạo thêm tác động ngoài ý muốn. Nó không có nghĩa request chỉ được xử lý đúng một lần. Một request có thể được tiếp nhận nhiều lần, nhưng các lần xử lý phải hội tụ về cùng kết quả theo hợp đồng của thao tác.

Cần phân biệt:

- **At-most-once:** hệ thống cố gắng không thực hiện thao tác nhiều hơn một lần, nhưng có thể không thực hiện nếu request thất lạc.
- **At-least-once:** hệ thống có thể thử lại cho đến khi nhận được kết quả, nên cùng một request có thể được xử lý nhiều lần.
- **Effectively-once:** kết hợp retry, định danh thao tác và xử lý idempotent để tạo hiệu ứng nghiệp vụ như thể chỉ thực hiện một lần trong phạm vi đã xác định.

Với provisioning cloud, retry thường cần thiết vì mạng và dịch vụ có thể tạm thời lỗi. Do đó, thiết kế idempotent thường thực tế hơn giả định “mỗi lệnh chỉ chạy đúng một lần”.

### 1.2. Ví dụ về thao tác idempotent

| Yêu cầu | Lần thực hiện đầu | Lần lặp lại | Kết quả mong muốn |
|---|---|---|---|
| Bảo đảm VM có tên api-01 tồn tại | Tạo VM nếu chưa có | Tìm VM đã có và xác nhận cấu hình | Chỉ có một VM đúng định danh |
| Bảo đảm firewall có rule cho HTTPS | Thêm rule nếu thiếu | Không thêm rule trùng | Rule tồn tại đúng một lần |
| Đặt số replica của nhóm máy thành 3 | Đặt desired capacity bằng 3 | Đặt lại bằng 3 | Số replica mong muốn vẫn là 3 |
| Xóa một tài nguyên đã được định danh | Xóa tài nguyên | Xác nhận tài nguyên đã vắng mặt | Tài nguyên không tồn tại |
| Tăng số replica thêm 1 | Tăng từ 3 lên 4 | Tăng tiếp từ 4 lên 5 | Không idempotent nếu gửi lặp cùng yêu cầu |

Điểm quan trọng là cách diễn đạt yêu cầu. “Đặt số replica bằng 4” mô tả trạng thái đích. “Tăng số replica thêm 1” mô tả một hành động tương đối. Hành động tương đối dễ tạo tác động lặp khi retry.

## 2. Thiết kế thao tác provisioning có tính idempotent

### 2.1. Khai báo trạng thái đích thay vì lặp lại hành động

Cách tiếp cận khai báo (declarative) mô tả trạng thái mong muốn của tài nguyên. Công cụ cấp phát so sánh cấu hình với trạng thái hiện tại rồi quyết định cần tạo, cập nhật hay xóa gì.

Ví dụ, yêu cầu một nhóm máy ảo có ba instance:

~~~hcl
resource "example_compute_group" "api" {
  name           = "api-group"
  desired_size   = 3
  machine_type   = "general-purpose"
  image_id       = "image-stable"
  subnet_id      = "subnet-private"
}
~~~

Tên resource và thuộc tính trong ví dụ là minh họa theo cú pháp HCL; provider thực tế có schema riêng. Khi desired_size đã là 3, chạy lại cùng cấu hình không nên tạo thêm ba máy mới. Công cụ sẽ đối chiếu state và API của provider để xác định hệ thống đã đạt trạng thái đó hay chưa.

Cách tiếp cận mệnh lệnh (imperative) mô tả từng hành động, ví dụ gọi API “tạo máy”, “gắn đĩa”, “thêm rule”. Nó vẫn có thể idempotent nếu mỗi bước kiểm tra tài nguyên hiện có, dùng định danh ổn định và xử lý trường hợp đã hoàn tất.

### 2.2. Dùng định danh ổn định

Một thao tác lặp lại cần biết nó đang nói về cùng một đối tượng. Định danh ổn định có thể là:

- Resource ID do cloud provider cấp.
- Tên logic duy nhất trong một phạm vi như project hoặc account.
- Tag hoặc label quản lý như environment=production và service=api.
- Idempotency key do client tạo cho một yêu cầu nghiệp vụ.
- Khóa tự nhiên có ràng buộc duy nhất, nếu dịch vụ hỗ trợ.

Không nên dựa duy nhất vào tên hiển thị nếu tên đó có thể trùng giữa project, region hoặc account. Nên xác định phạm vi đầy đủ và lưu resource ID sau khi tạo thành công.

### 2.3. Idempotency key cho API

Một số API hỗ trợ trường hoặc header **idempotency key**. Client tạo một khóa duy nhất cho một ý định tạo tài nguyên và gửi lại cùng khóa khi retry. Server dùng khóa đó để nhận biết các request là cùng một thao tác và trả về kết quả đã ghi nhận thay vì tạo tài nguyên mới.

Ví dụ minh họa:

~~~http
POST /v1/instances
Idempotency-Key: create-api-01-2026-11-22-001
Content-Type: application/json

{
  "name": "api-01",
  "machine_type": "general-purpose",
  "image": "image-stable"
}
~~~

Nếu client timeout và gửi lại cùng request với cùng key, API có thể trả lại kết quả của thao tác trước. Nếu gửi cùng key nhưng payload khác, API thường từ chối hoặc báo xung đột theo hợp đồng của dịch vụ.

Khi dùng idempotency key, cần kiểm tra tài liệu API về:

- Thời gian server lưu khóa và kết quả.
- Phạm vi duy nhất của khóa: theo account, endpoint, region hay tenant.
- Cách xử lý request đồng thời cùng khóa.
- Hành vi khi payload thay đổi.
- Kết quả trả về khi thao tác ban đầu vẫn đang xử lý.
- Cách truy vấn trạng thái nếu client mất phản hồi.

Không tự tạo giả định rằng mọi API POST đều hỗ trợ idempotency key. Nếu dịch vụ không hỗ trợ, ứng dụng cần thiết kế cơ chế kiểm tra và đối soát riêng.

### 2.4. HTTP method không tự bảo đảm idempotency cho toàn bộ nghiệp vụ

Theo ngữ nghĩa HTTP, PUT và DELETE được định nghĩa là idempotent; GET là phương thức an toàn và idempotent. POST thường không idempotent theo mặc định. Tuy nhiên, hiệu ứng thực tế còn phụ thuộc hợp đồng API.

Ví dụ:

- **PUT /instances/api-01** có thể đặt cấu hình tài nguyên theo biểu diễn gửi lên. Gửi lại cùng nội dung hướng tới cùng trạng thái.
- **DELETE /instances/api-01** có thể để tài nguyên ở trạng thái không tồn tại. Lần gọi sau vẫn hướng tới trạng thái đó, dù response có thể là 404.
- **POST /instances** thường tạo một tài nguyên mới mỗi lần; muốn retry an toàn cần idempotency key hoặc quy tắc chống trùng khác.

Một API có thể trả timestamp, request ID hoặc audit record mới ở mỗi lần gọi, dù trạng thái tài nguyên cuối không đổi. Vì vậy, khi đánh giá idempotency, cần xác định rõ đang nói đến trạng thái tài nguyên, phản hồi HTTP hay mọi side effect phụ trợ.

## 3. State trong công cụ Infrastructure as Code

### 3.1. Ba trạng thái cần phân biệt

Khi dùng công cụ Infrastructure as Code (IaC), có ba khái niệm quan trọng:

1. **Desired state:** trạng thái mong muốn được mô tả trong file cấu hình.
2. **Actual state:** trạng thái tài nguyên đang tồn tại trên cloud provider.
3. **Recorded state:** trạng thái công cụ đã ghi nhận, bao gồm liên kết giữa resource address trong cấu hình và resource ID thực tế cùng các thuộc tính cần thiết.

~~~mermaid
flowchart LR
    D["Desired state<br/>File IaC"]
    S["Recorded state<br/>State backend"]
    A["Actual state<br/>Cloud API"]
    D --> P["Plan / Reconcile"]
    S --> P
    A --> P
    P --> C["Create / Update / Delete"]
    C --> A
    A --> R["Refresh / Read"]
    R --> S
~~~

Công cụ cần cả ba góc nhìn để lập kế hoạch thay đổi. File cấu hình cho biết người vận hành muốn gì; state cho biết công cụ đang quản lý đối tượng nào; API cloud cho biết tài nguyên thực tế đang ra sao.

State không phải bản sao đầy đủ và luôn mới của cloud. Nó là dữ liệu quản lý mà công cụ dùng để theo dõi tài nguyên. Nếu ai đó thay đổi trực tiếp trên console, recorded state có thể không phản ánh ngay thay đổi đó. Nếu state bị mất, tài nguyên trên cloud vẫn có thể tồn tại nhưng công cụ mất thông tin liên kết với chúng.

### 3.2. Resource address và resource ID

Trong Terraform, mỗi resource có một địa chỉ logic, ví dụ:

~~~hcl
resource "example_instance" "api" {
  name = "api-01"
}
~~~

Địa chỉ trong cấu hình là **example_instance.api**. Cloud provider có thể cấp một ID khác như **inst-7f31a2**. State lưu mối liên hệ giữa địa chỉ logic và ID thực tế, cùng các thuộc tính được provider đọc hoặc quản lý.

Nếu đổi tên resource block từ **example_instance.api** thành **example_instance.backend** mà không khai báo việc di chuyển địa chỉ, Terraform có thể diễn giải thay đổi thành xóa đối tượng cũ và tạo đối tượng mới. Với tài nguyên quan trọng, cần dùng moved block hoặc lệnh di chuyển state phù hợp để bảo toàn liên kết.

Ví dụ:

~~~hcl
moved {
  from = example_instance.api
  to   = example_instance.backend
}
~~~

Cú pháp này thông báo rằng địa chỉ logic đã đổi tên nhưng vẫn đại diện cho cùng một tài nguyên. Cần xác minh phiên bản Terraform và phạm vi module trước khi áp dụng thay đổi.

### 3.3. State có thể chứa dữ liệu nhạy cảm

State có thể chứa địa chỉ IP, tên máy, metadata, thuộc tính kết nối, mật khẩu hoặc giá trị nhạy cảm tùy provider và cách cấu hình. Đánh dấu biến là sensitive chủ yếu kiểm soát cách Terraform hiển thị giá trị trong một số đầu ra; nó không có nghĩa dữ liệu đó không được lưu trong state.

Do đó:

- Giới hạn quyền đọc và ghi state theo nguyên tắc tối thiểu.
- Dùng backend từ xa có mã hóa khi lưu trữ và khi truyền dữ liệu.
- Bảo vệ credential truy cập backend bằng secret manager hoặc cơ chế danh tính phù hợp.
- Không commit state hoặc backup chứa state vào repository công khai.
- Không đưa nội dung state vào log, ticket hoặc artifact không được bảo vệ.
- Thiết lập lưu trữ backup và chính sách retention phù hợp.
- Kiểm tra quyền truy cập và audit log của backend.

## 4. Lưu trữ state cục bộ và từ xa

### 4.1. Local state

Khi mới dùng Terraform, state thường được lưu trong file cục bộ như **terraform.tfstate**.

Ưu điểm là dễ bắt đầu và phù hợp với thử nghiệm cá nhân. Tuy nhiên, local state có rủi ro:

- Chỉ tồn tại trên máy của một người.
- Khó chia sẻ chính xác giữa nhiều thành viên hoặc pipeline.
- Dễ bị ghi đè khi nhiều người thao tác.
- Có thể bị mất khi máy hoặc workspace bị xóa.
- Dễ bị đưa nhầm vào Git nếu không quản lý cẩn thận.

Local state phù hợp cho lab hoặc môi trường thử nghiệm nhỏ, nơi không có nhiều người cùng quản lý một tập tài nguyên.

### 4.2. Remote state

Trong môi trường nhóm, state thường được lưu ở backend từ xa như object storage hoặc dịch vụ quản lý state. Backend cần hỗ trợ các đặc tính phù hợp:

- Lưu trữ bền vững và có khả năng khôi phục.
- Mã hóa khi truyền và khi lưu.
- Kiểm soát truy cập theo người dùng hoặc pipeline.
- Versioning hoặc backup để phục hồi state.
- Locking để ngăn các thao tác ghi state đồng thời, nếu backend hỗ trợ.
- Audit log và chính sách retention.

Ví dụ cấu hình backend minh họa:

~~~hcl
terraform {
  backend "s3" {
    bucket       = "company-terraform-state"
    key          = "compute/production/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
  }
}
~~~

Đây là ví dụ cho S3 backend; tên bucket và region chỉ là giá trị minh họa. Backend cần được tạo và cấp quyền trước khi chạy terraform init. Cần cấu hình locking theo cơ chế được phiên bản Terraform và backend đang dùng hỗ trợ. Không nên giả định chỉ bật mã hóa là đã có locking hoặc backup.

### 4.3. State locking

**State locking** ngăn nhiều tiến trình cùng sửa một state tại một thời điểm. Nếu hai pipeline cùng chạy apply, cả hai có thể đọc một phiên bản state cũ rồi ghi các thay đổi không nhất quán.

Quy trình khóa thường diễn ra như sau:

1. Terraform yêu cầu backend cấp lock.
2. Nếu lock thành công, Terraform đọc state và thực hiện plan/apply.
3. Khi hoàn tất hoặc dừng theo cách được hỗ trợ, Terraform giải phóng lock.
4. Nếu tiến trình bị lỗi, lock có thể cần được xử lý theo hướng dẫn của backend và công cụ.

Không nên tự xóa lock chỉ vì thấy một pipeline đang chạy lâu. Trước tiên cần xác minh tiến trình giữ lock đã kết thúc và state không còn được cập nhật. Lệnh force-unlock có thể gây hỏng state nếu dùng sai. Chỉ người có trách nhiệm quản lý state mới nên thực hiện sau khi xác minh.

### 4.4. Tách state theo phạm vi quản lý

Không nhất thiết lưu mọi tài nguyên của toàn tổ chức trong một state duy nhất. Có thể tách theo môi trường, ứng dụng, nhóm dịch vụ hoặc miền quản trị.

Ví dụ:

- **network/shared/terraform.tfstate:** mạng dùng chung.
- **compute/dev/api/terraform.tfstate:** compute cho API ở môi trường dev.
- **compute/prod/api/terraform.tfstate:** compute cho API production.
- **compute/prod/worker/terraform.tfstate:** compute cho worker production.

Tách state giúp giới hạn blast radius, giảm xung đột và phân quyền rõ hơn. Tuy nhiên, nhiều state tạo ra quan hệ phụ thuộc giữa các nhóm. Cần xác định giao diện đầu ra, quyền truy cập và thứ tự triển khai giữa chúng.

## 5. Quy trình reconcile và thao tác lặp an toàn

### 5.1. Plan trước khi apply

Một quy trình IaC phổ biến gồm:

~~~bash
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
~~~

- **init** khởi tạo provider và backend.
- **validate** kiểm tra cấu trúc cấu hình.
- **plan** so sánh cấu hình, state và dữ liệu provider để tính thay đổi dự kiến.
- **apply** thực hiện các thay đổi đã được lập kế hoạch.

Chạy lại cùng cấu hình sau khi hệ thống đã đạt trạng thái mong muốn thường tạo ra plan rỗng. Đây là một dấu hiệu cho thấy cấu hình và state đã hội tụ tại thời điểm kiểm tra. Tuy nhiên, plan rỗng không bảo đảm tài nguyên không thay đổi sau đó hoặc mọi side effect bên ngoài đều không tồn tại.

Không nên chạy apply tự động cho mọi thay đổi trong production nếu chưa có quy trình xem xét, phê duyệt và giới hạn quyền phù hợp.

### 5.2. Retry an toàn khi API timeout

Giả sử client gửi yêu cầu tạo VM. Server có thể đã tạo VM thành công nhưng phản hồi bị mất. Nếu client gọi lại endpoint tạo mới mà không có idempotency key hoặc kiểm tra trùng, có thể tạo hai VM.

Một quy trình an toàn hơn:

1. Tạo operation ID hoặc idempotency key cho ý định cấp phát.
2. Gửi yêu cầu với cùng định danh khi retry.
3. Nếu API trả operation ID, lưu lại và truy vấn trạng thái operation.
4. Nếu request timeout và API không hỗ trợ idempotency key, tìm tài nguyên theo định danh ổn định hoặc tag đã đặt trước.
5. Chỉ gửi yêu cầu tạo mới sau khi xác định tài nguyên chưa được tạo.
6. Ghi resource ID và kết quả vào state hoặc kho dữ liệu quản lý.

Ví dụ logic giả mã:

~~~python
def ensure_instance(spec, operation_key):
    result = cloud.find_by_operation_key(operation_key)

    if result is not None:
        return cloud.wait_until_ready(result.id)

    try:
        result = cloud.create_instance(
            spec=spec,
            idempotency_key=operation_key
        )
    except TimeoutError:
        result = cloud.find_by_operation_key(operation_key)
        if result is None:
            raise

    return cloud.wait_until_ready(result.id)
~~~

Đây là mã giả. API thực tế có thể dùng tên trường, cơ chế operation và thời gian lưu idempotency key khác nhau. Nếu API không hỗ trợ key, find_by_operation_key chỉ an toàn khi dịch vụ cho phép lưu và truy vấn một định danh duy nhất đáng tin cậy. Hai client đồng thời vẫn có thể cùng tìm thấy “chưa tồn tại” rồi cùng tạo; cần thêm cơ chế chống tranh chấp như unique constraint, lock hoặc API create-if-absent.

### 5.3. Xử lý thao tác bất đồng bộ

Nhiều API provisioning trả về operation ID thay vì chờ máy ảo hoặc database sẵn sàng. Khi đó, việc tạo tài nguyên và việc tài nguyên đạt trạng thái ready là hai giai đoạn khác nhau.

Client nên:

- Lưu operation ID và resource ID nếu đã có.
- Poll trạng thái theo khoảng thời gian có backoff.
- Phân biệt trạng thái pending, running, succeeded và failed theo API.
- Có timeout tổng thể và giới hạn retry.
- Khi mất phản hồi, truy vấn operation trước khi gửi yêu cầu tạo mới.
- Xử lý eventual consistency: tài nguyên vừa tạo có thể chưa xuất hiện ngay trong mọi API đọc hoặc danh sách.

Không nên xem “request đã được chấp nhận” đồng nghĩa “tài nguyên đã sẵn sàng”. Pipeline cần chờ điều kiện sức khỏe hoặc trạng thái mong muốn trước khi triển khai bước phụ thuộc.

## 6. Drift, refresh và đối soát trạng thái

### 6.1. State có thể khác thực tế

State là bản ghi của công cụ tại một thời điểm. Actual state có thể thay đổi do:

- Người vận hành sửa trực tiếp trên console.
- Một pipeline khác hoặc một công cụ khác thay đổi tài nguyên.
- Cloud provider tự cập nhật metadata hoặc trạng thái hệ thống.
- Tài nguyên bị xóa ngoài Terraform.
- Một thao tác trước đó hoàn tất một phần rồi gặp lỗi.

Sự khác biệt giữa desired state, recorded state và actual state cần được phát hiện trước khi tiếp tục cấp phát.

### 6.2. Refresh và plan

Terraform có thể đọc trạng thái thực tế từ provider để cập nhật thông tin quan sát vào state trong quá trình plan hoặc refresh. Các lệnh và hành vi cụ thể thay đổi theo phiên bản Terraform; nên dùng workflow hiện hành thay vì dựa vào lệnh refresh cũ.

Một số bước đối soát:

1. Kiểm tra workspace và backend đang dùng.
2. Chạy plan để xem Terraform phát hiện thay đổi nào.
3. Xác định thay đổi đến từ cấu hình, state hay thao tác ngoài hệ thống.
4. Quyết định cập nhật cấu hình, nhập tài nguyên vào state hoặc khôi phục trạng thái mong muốn.
5. Xem lại plan sau điều chỉnh trước khi apply.

Không nên dùng apply để “sửa cho hết diff” nếu chưa hiểu vì sao tài nguyên thay đổi. Một plan có thể đề xuất thay thế máy ảo, disk hoặc địa chỉ IP và gây gián đoạn nếu áp dụng không đúng thời điểm.

### 6.3. Import tài nguyên đã tồn tại

Nếu tài nguyên được tạo thủ công hoặc bởi công cụ khác nhưng cần đưa vào quản lý Terraform, có thể import nó vào state. Import gắn resource ID thực tế với địa chỉ logic trong cấu hình.

Ví dụ dùng import block:

~~~hcl
import {
  to = example_instance.api
  id = "inst-7f31a2"
}
~~~

Sau khi khai báo resource tương ứng và import block, chạy plan để xem kết quả. Cần bổ sung cấu hình phù hợp với tài nguyên hiện có trước khi apply; nếu cấu hình khai báo khác thực tế, plan có thể đề xuất thay đổi hoặc thay thế tài nguyên.

Import không tự động viết toàn bộ cấu hình mong muốn và cũng không biến mọi thay đổi ngoài Terraform thành thay đổi được chấp nhận. Sau import, cần xác minh thuộc tính quan trọng, dependency, lifecycle và quyền quản lý.

## 7. Bảo vệ và khôi phục state

### 7.1. Backup và versioning

State là dữ liệu quan trọng. Nếu state bị xóa hoặc ghi sai, công cụ có thể mất khả năng theo dõi tài nguyên dù các tài nguyên đó vẫn tồn tại.

Nên:

- Bật versioning hoặc snapshot cho backend khi dịch vụ hỗ trợ.
- Lưu backup trước các thao tác state nhạy cảm.
- Kiểm tra khả năng khôi phục định kỳ.
- Ghi lại ai thực hiện thay đổi và khi nào.
- Dùng quy trình phê duyệt cho các thao tác thay thế, import hoặc di chuyển state.
- Hạn chế số người có quyền ghi trực tiếp vào backend.

Backup state không thay thế backup dữ liệu ứng dụng. State chỉ hỗ trợ công cụ quản lý hạ tầng; nó không chứa đầy đủ nội dung disk, database hoặc object storage để khôi phục dữ liệu nghiệp vụ.

### 7.2. Mất state không có nghĩa tài nguyên đã mất

Nếu file state bị mất, không nên lập tức chạy apply với giả định mọi resource chưa tồn tại. Terraform có thể cố tạo lại các tài nguyên vốn vẫn còn trên cloud, gây trùng lặp hoặc lỗi tên đã được sử dụng.

Quy trình xử lý nên là:

1. Dừng các pipeline có thể ghi vào cùng state.
2. Tìm backup hoặc version state gần nhất còn hợp lệ.
3. Xác định phạm vi tài nguyên được quản lý và đối chiếu với cloud API.
4. Khôi phục state hoặc import các tài nguyên hiện có theo resource address.
5. Chạy plan và kiểm tra kỹ mọi hành động tạo, xóa hoặc thay thế.
6. Chỉ tiếp tục apply sau khi state và cấu hình đã được xác minh.

Nếu nghi state bị hỏng, tránh chỉnh sửa JSON thủ công. Dùng lệnh và hướng dẫn chính thức của công cụ, giữ bản sao state gốc và ghi nhận mọi thao tác phục hồi.

### 7.3. Di chuyển backend

Khi chuyển từ local state sang remote backend hoặc từ backend này sang backend khác, cần dùng quy trình migration được công cụ hỗ trợ. Với Terraform, **terraform init -migrate-state** có thể hỗ trợ chuyển state khi cấu hình backend thay đổi.

Trước khi di chuyển:

- Sao lưu state hiện tại.
- Xác nhận quyền truy cập backend mới.
- Kiểm tra encryption, versioning và locking.
- Tạm dừng pipeline hoặc thao tác đồng thời.
- Chạy migration theo hướng dẫn của phiên bản đang dùng.
- Xác minh state mới và chạy plan để kiểm tra không có thay đổi bất ngờ.

Không sao chép state bằng thao tác file thông thường trong khi có apply đang chạy.

## 8. Dependency, thứ tự và tính nhất quán

Provisioning thường có quan hệ phụ thuộc. Ví dụ, VM cần subnet và security group; volume cần zone tương thích; load balancer cần backend khỏe mạnh.

Công cụ IaC có thể suy ra dependency từ tham chiếu tài nguyên hoặc dùng khai báo phụ thuộc tường minh. Tuy nhiên, dependency trong graph chỉ giải quyết thứ tự thao tác, không tự bảo đảm dịch vụ đã sẵn sàng ở tầng ứng dụng.

Ví dụ:

~~~hcl
resource "example_instance" "api" {
  name      = "api-01"
  subnet_id = example_subnet.private.id

  depends_on = [
    example_security_group.api
  ]
}
~~~

Trong ví dụ, VM tham chiếu subnet nên công cụ có thể suy ra phụ thuộc tới subnet. depends_on bổ sung phụ thuộc tường minh tới security group nếu provider hoặc cấu hình không thể biểu diễn quan hệ qua thuộc tính tham chiếu. Schema thực tế phụ thuộc provider.

Một thao tác provisioning có thể trả thành công trước khi dịch vụ bên dưới thực sự sẵn sàng. Cần bổ sung health check, wait condition hoặc kiểm tra kết nối phù hợp. Tránh dùng sleep cố định như cách duy nhất để xác nhận sẵn sàng vì thời gian khởi tạo thay đổi theo tải và trạng thái nền tảng.

## 9. Thực hành quy trình idempotent với Terraform

### 9.1. Khai báo tài nguyên ổn định

Ví dụ một nhóm máy ảo với số lượng mong muốn cố định:

~~~hcl
variable "environment" {
  type = string
}

variable "instance_count" {
  type    = number
  default = 2
}

resource "example_instance" "worker" {
  count         = var.instance_count
  name          = format("worker-%s-%d", var.environment, count.index + 1)
  machine_type  = "general-purpose"
  image_id      = "image-stable"
  subnet_id     = "subnet-private"
}
~~~

Cấu hình mô tả hai worker theo tên ổn định dựa trên môi trường và chỉ số. Nếu chạy lại với cùng biến và cùng state, Terraform có thể nhận diện các instance đã quản lý và không tạo thêm bản sao.

Nếu đổi instance_count từ 2 lên 3, Terraform sẽ thêm một instance. Nếu giảm từ 3 xuống 2, Terraform sẽ đề xuất xóa instance tương ứng. Trước khi apply, cần kiểm tra chính sách lifecycle và tác động đến dữ liệu hoặc kết nối của tài nguyên bị xóa.

### 9.2. Chạy lại và kiểm tra plan

Quy trình thực hành:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
terraform plan
~~~

Lần plan cuối thường không còn thay đổi nếu cấu hình, state và actual state đã đồng bộ. Nếu vẫn có thay đổi, hãy tìm nguyên nhân: giá trị mặc định do provider trả về, thuộc tính thay đổi ngoài hệ thống, dữ liệu chưa ổn định hoặc cấu hình không biểu diễn đúng trạng thái thực tế.

### 9.3. Chạy song song có kiểm soát

Trong nhóm, nhiều pipeline có thể cùng muốn cấp phát tài nguyên. Cần:

- Dùng một backend state chung cho cùng một phạm vi quản lý.
- Bật locking nếu backend hỗ trợ.
- Tránh tạo hai pipeline độc lập cùng quản lý một resource address.
- Dùng concurrency group hoặc hàng đợi triển khai trong CI/CD.
- Phân tách state khi hai nhóm có phạm vi sở hữu độc lập.
- Định nghĩa rõ quyền sở hữu tài nguyên dùng chung.

State locking chỉ bảo vệ thao tác ghi cùng state theo cơ chế backend. Nó không ngăn một người dùng console hoặc một công cụ khác sửa tài nguyên ngoài state. Cần kết hợp quyền IAM, quy trình thay đổi và phát hiện drift.

### 9.4. Idempotency trong quản lý cấu hình bằng Ansible

Ansible thường làm việc theo mô hình khai báo trạng thái. Các module chuyên dụng nhận trạng thái mong muốn và kiểm tra trước khi thay đổi, ví dụ bảo đảm package đã cài hoặc service đang chạy:

~~~yaml
- name: Configure web service
  hosts: web
  become: true
  tasks:
    - name: Ensure Nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Ensure Nginx is enabled and running
      ansible.builtin.service:
        name: nginx
        enabled: true
        state: started
~~~

Chạy playbook nhiều lần với cùng biến và cùng máy đích sẽ không cài lại package hoặc khởi động lại service nếu trạng thái đã đúng. Module chỉ báo thay đổi khi cần thực hiện thao tác.

Các module command hoặc shell thường không biết trạng thái nghiệp vụ của lệnh. Ví dụ, lệnh tạo thư mục hoặc tải file có thể chạy lại và tạo side effect. Nếu chưa có module chuyên dụng, cần thêm điều kiện kiểm tra như creates hoặc removes khi phù hợp:

~~~yaml
- name: Generate a one-time initialization marker
  ansible.builtin.command:
    cmd: /usr/local/bin/initialize-app
    creates: /var/lib/my-app/initialized
~~~

Điều kiện creates giúp bỏ qua lệnh khi file marker đã tồn tại. Cách này chỉ an toàn nếu marker được tạo đúng khi tác vụ hoàn tất và vẫn phản ánh trạng thái cần bảo đảm. Không nên dùng marker đơn giản cho thao tác có thể hoàn tất một phần hoặc cần đối chiếu nhiều thuộc tính; khi đó nên viết module có khả năng kiểm tra trạng thái thực tế.

Thuộc tính changed_when chỉ điều chỉnh báo cáo task có thay đổi hay không; tự nó không ngăn lệnh chạy lại. Muốn idempotent, cần kiểm tra điều kiện trước khi thực thi hoặc dùng module có state semantics.

## 10. Những sai lầm thường gặp

**Nhầm retry với idempotency.** Gửi lại một lệnh tạo tài nguyên có thể tạo thêm đối tượng mới nếu API không hỗ trợ chống trùng. Cần định danh ổn định và quy tắc retry.

**Dùng tên ngẫu nhiên ở mỗi lần chạy.** Nếu tên mới được sinh mỗi lần, hệ thống khó nhận ra đó là cùng một ý định cấp phát. Nên dùng ID hoặc khóa ổn định theo nghiệp vụ.

**Cho rằng state chính là hạ tầng.** State là bản ghi quản lý; tài nguyên cloud vẫn tồn tại độc lập. Mất state không tự xóa tài nguyên và cũng không có nghĩa nên tạo lại toàn bộ.

**Cho rằng sensitive sẽ mã hóa state.** Thuộc tính sensitive kiểm soát hiển thị trong một số đầu ra, không thay thế mã hóa backend và kiểm soát truy cập.

**Nhiều pipeline cùng apply một state mà không locking.** Có thể dẫn đến ghi đè hoặc state không nhất quán. Dùng remote backend có locking và điều phối pipeline.

**Tự sửa state JSON bằng tay.** Một chỉnh sửa sai có thể làm mất liên kết resource hoặc khiến công cụ đề xuất xóa nhầm. Dùng lệnh state/import/moved chính thức và backup trước.

**Import tài nguyên nhưng không khai báo cấu hình phù hợp.** Import chỉ đưa ID vào state. Cấu hình không khớp có thể tạo plan thay thế hoặc thay đổi tài nguyên ngoài ý muốn.

**Xem request thành công là tài nguyên đã sẵn sàng.** API có thể trả operation ID trong khi VM vẫn đang khởi tạo. Cần poll trạng thái và health check.

**Xóa lock đang được sử dụng.** Force-unlock sai thời điểm có thể khiến hai tiến trình cùng ghi state. Phải xác minh tiến trình và trạng thái backend trước.

**Coi plan rỗng là bảo đảm vĩnh viễn.** Plan chỉ phản ánh dữ liệu quan sát tại thời điểm chạy. Hệ thống có thể bị thay đổi ngay sau đó bởi người hoặc công cụ khác.

## 11. Checklist trước khi tự động hóa provisioning

- [ ] Mô tả trạng thái mong muốn thay vì chỉ liệt kê hành động tạo mới.
- [ ] Chọn resource ID, tên logic hoặc idempotency key ổn định.
- [ ] Kiểm tra API có hỗ trợ idempotency key và thời gian lưu key.
- [ ] Thiết kế retry có backoff, giới hạn số lần và truy vấn operation khi timeout.
- [ ] Phân biệt desired state, actual state và recorded state.
- [ ] Dùng remote backend phù hợp cho môi trường nhóm.
- [ ] Bật locking nếu backend hỗ trợ và điều phối pipeline.
- [ ] Mã hóa state, giới hạn quyền truy cập và không commit state vào Git.
- [ ] Bật versioning/backup và thử quy trình khôi phục.
- [ ] Có quy trình refresh, import và di chuyển resource address.
- [ ] Kiểm tra plan trước apply và xác minh trạng thái sau apply.
- [ ] Xử lý dependency và readiness bằng health check hoặc wait condition.
- [ ] Ghi log operation ID, resource ID và kết quả mà không làm lộ secret.
- [ ] Có runbook khi mất state, timeout, lock bị treo hoặc apply thất bại.

## 12. Ghi nhớ

- **Idempotency** bảo đảm thao tác lặp lại đưa tài nguyên về cùng trạng thái đích, giúp retry an toàn hơn.
- **Desired state, actual state và recorded state** là ba góc nhìn khác nhau cần được đối chiếu.
- **Idempotency key** giúp API nhận diện các lần gửi lại cùng một ý định, nếu dịch vụ hỗ trợ.
- **Terraform state** liên kết resource address với resource ID và lưu thông tin cần thiết để quản lý vòng đời.
- **Remote backend, locking, encryption và backup** giúp nhóm quản lý state an toàn và nhất quán.
- **Import và moved block** hỗ trợ đưa tài nguyên hiện có vào quản lý hoặc đổi địa chỉ logic mà không tạo lại tài nguyên.
- **Retry cần hiểu trạng thái operation và eventual consistency.** Timeout không chứng minh thao tác thất bại.
- **Plan và health check** giúp xác minh hệ thống đã đạt trạng thái mong muốn trước khi chuyển sang bước tiếp theo.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Idempotency | Tính chất thao tác lặp lại vẫn tạo cùng trạng thái cuối. |
| Desired state | Trạng thái tài nguyên mà cấu hình khai báo mong muốn. |
| Actual state | Trạng thái tài nguyên đang tồn tại trên hệ thống cloud. |
| Recorded state | Trạng thái được công cụ IaC ghi nhận để theo dõi tài nguyên. |
| State backend | Nơi lưu trữ state của công cụ IaC. |
| State locking | Cơ chế khóa state để ngăn nhiều thao tác ghi đồng thời. |
| Idempotency key | Khóa giúp API nhận diện các lần gửi lại cùng một yêu cầu. |
| Resource address | Địa chỉ logic của resource trong cấu hình IaC. |
| Resource ID | Định danh tài nguyên do provider hoặc nền tảng cấp. |
| Refresh | Quá trình đọc trạng thái thực tế để cập nhật thông tin quản lý. |
| Import | Đưa tài nguyên đã tồn tại vào phạm vi quản lý của IaC. |
| Configuration drift | Sự khác biệt giữa cấu hình chuẩn và trạng thái thực tế. |
| Reconcile | Đối chiếu và đưa actual state về desired state. |
| Eventual consistency | Tính nhất quán mà các bản đọc có thể cần thời gian để phản ánh cập nhật mới. |
| Retry with backoff | Thử lại với khoảng chờ tăng dần để giảm áp lực lên dịch vụ. |
| Ansible module | Thành phần thực hiện một tác vụ quản lý cấu hình và thường có thể kiểm tra trạng thái mong muốn. |
| creates | Điều kiện của Ansible command để bỏ qua lệnh khi file chỉ định đã tồn tại. |
| changed_when | Biểu thức Ansible điều chỉnh việc báo cáo task có thay đổi; không tự ngăn lệnh chạy lại. |
