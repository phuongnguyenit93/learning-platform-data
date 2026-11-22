# Lặp lại thao tác an toàn khi tiến trình bị ngắt hoặc kết quả chưa rõ

Một job triển khai gửi yêu cầu tạo release tới hệ thống đích. Hệ thống nhận yêu cầu và đã tạo release, nhưng kết nối bị ngắt trước khi CI nhận được phản hồi. Job kết thúc với trạng thái timeout. Nếu chạy lại toàn bộ thao tác một cách mù quáng, pipeline có thể tạo release thứ hai, gửi thông báo trùng, chạy migration nhiều lần hoặc ghi đè trạng thái của một lần triển khai đang hoạt động.

Đây là tình huống phổ biến trong hệ thống phân tán: phía gọi không biết chắc thao tác đã được thực hiện hay chưa. Timeout chỉ cho biết caller không nhận được kết quả trong khoảng thời gian chờ; nó không chứng minh hệ thống đích chưa xử lý yêu cầu.

Để tự động hóa triển khai đáng tin cậy, thao tác cần được thiết kế sao cho có thể lặp lại an toàn, hoặc hệ thống phải có cách xác định trạng thái trước khi thử lại. Hai kỹ thuật quan trọng là **idempotency** (tính lũy đẳng) và **reconciliation** (đối soát trạng thái thực tế với trạng thái mong muốn). Kết hợp chúng với retry có giới hạn, định danh thao tác ổn định, ghi nhận trạng thái bền vững và kiểm soát tác dụng phụ sẽ giúp pipeline phục hồi sau gián đoạn mà không tạo ra kết quả trùng hoặc không nhất quán.

## 1. Hiểu tính lũy đẳng trong tự động hóa

Một thao tác có tính lũy đẳng nếu thực hiện nó một lần hay lặp lại nhiều lần với cùng đầu vào đều dẫn tới cùng trạng thái cuối cùng.

Về mặt khái niệm, một hàm biến đổi trạng thái S bằng thao tác A là lũy đẳng khi:

~~~text
A(A(S)) = A(S)
~~~

Ví dụ, đặt số replica của một service thành 4 là thao tác có thể lặp lại:

- Lần đầu: service đang có 2 replica, yêu cầu đặt thành 4.
- Lần hai: service đã có 4 replica, yêu cầu đặt thành 4 lần nữa.
- Trạng thái cuối vẫn là 4 replica.

Ngược lại, lệnh tăng số replica thêm 2 không lũy đẳng:

- Lần đầu: từ 2 lên 4.
- Lần hai: từ 4 lên 6.
- Lần thứ ba: từ 6 lên 8.

Nếu caller không biết lần trước đã thành công hay chưa, lặp lại lệnh tăng có thể tạo ra trạng thái sai.

### Đặt trạng thái mong muốn và ra lệnh thay đổi tương đối

| Dạng thao tác | Ví dụ | Khả năng lặp lại |
|---|---|---|
| Đặt trạng thái tuyệt đối | Đặt replicas = 4 | Thường lũy đẳng nếu cùng phạm vi và điều kiện |
| Đặt cấu hình mong muốn | Apply manifest version X | Có thể lũy đẳng nếu tool và resource identity ổn định |
| Tạo tài nguyên với tên cố định | Ensure bucket tên release-assets tồn tại | Có thể lũy đẳng nếu kiểm tra và xử lý xung đột đúng |
| Thay đổi tương đối | Tăng replicas thêm 2 | Không lũy đẳng |
| Tạo mới không có định danh ổn định | Tạo một release mới | Có thể tạo bản ghi trùng khi retry |
| Gửi thông báo | Gửi email phát hành | Thường tạo tác dụng phụ mới mỗi lần |
| Chuyển trạng thái có điều kiện | Chuyển deployment từ pending sang active | Cần kiểm soát trạng thái và cạnh tranh |

Cách thiết kế tốt thường mô tả **trạng thái cần đạt** thay vì chỉ mô tả một chuỗi lệnh thay đổi tương đối. Ví dụ, yêu cầu hệ thống bảo đảm một version cụ thể đang chạy ở production rõ ràng hơn lệnh "chạy deploy thêm một lần".

### Lũy đẳng không có nghĩa không có tác dụng phụ

Một API có thể cập nhật cùng một giá trị nhiều lần nhưng vẫn gửi email, tăng bộ đếm, ghi audit event hoặc kích hoạt webhook mỗi lần. Khi đánh giá idempotency, phải xét toàn bộ tác động quan sát được, không chỉ cột dữ liệu chính.

## 2. Vì sao kết quả của thao tác có thể không xác định?

Giả sử CI gửi yêu cầu tới deployment service. Có nhiều thời điểm lỗi khác nhau:

1. Caller lỗi trước khi gửi yêu cầu.
2. Yêu cầu đã gửi nhưng chưa tới server.
3. Server nhận yêu cầu nhưng chưa xử lý.
4. Server đã commit thay đổi nhưng phản hồi bị mất.
5. Server chấp nhận tác vụ bất đồng bộ, trả về operation ID, nhưng caller mất phản hồi.
6. Server hoàn tất một phần công việc rồi worker bị dừng.
7. Caller nhận phản hồi nhưng chết trước khi ghi nhận trạng thái thành công vào hệ thống của mình.

Ở các trường hợp 1-3, thao tác có thể chưa xảy ra. Ở các trường hợp 4-7, thao tác có thể đã xảy ra toàn bộ hoặc một phần. Từ phía caller, timeout hoặc mất kết nối không đủ để phân biệt các trường hợp này.

### Ba trạng thái kết quả cần phân biệt

- **Thành công đã xác nhận:** caller có bằng chứng đáng tin cậy rằng thao tác hoàn tất.
- **Thất bại đã xác nhận:** hệ thống đích trả về kết quả cho biết thao tác không được thực hiện hoặc bị từ chối.
- **Chưa rõ kết quả (unknown outcome):** caller không biết thao tác đã được tiếp nhận, commit hay hoàn tất chưa.

Không nên tự động chuyển trạng thái unknown thành failed. Nếu một lần triển khai có thể đã hoàn tất, đánh dấu thất bại rồi tạo operation mới có thể khiến pipeline chạy song song hai lần.

### Timeout không phải bằng chứng thao tác thất bại

Timeout là sự kiện ở phía caller. Nó chỉ mô tả thời gian chờ đã hết. Hệ thống đích có thể tiếp tục xử lý sau khi caller ngừng chờ.

Khi gặp timeout, hành động an toàn thường là tra cứu trạng thái bằng operation ID hoặc idempotency key. Chỉ gửi lại yêu cầu khi đã xác định quy tắc retry phù hợp.

## 3. Delivery semantics: at-most-once, at-least-once và exactly-once

Trong hệ thống phân tán, thông điệp hoặc yêu cầu có thể bị mất, gửi lại hoặc xử lý trùng. Ba cách diễn đạt thường dùng:

| Semantics | Hành vi | Đánh đổi |
|---|---|---|
| At-most-once | Không gửi lại khi không chắc chắn | Tránh xử lý trùng nhưng có thể mất thao tác |
| At-least-once | Gửi lại cho tới khi nhận được xác nhận theo chính sách | Tăng khả năng hoàn thành nhưng có thể xử lý nhiều lần |
| Exactly-once | Mỗi thao tác có hiệu lực đúng một lần trong phạm vi xác định | Khó đạt xuyên suốt nhiều hệ thống độc lập |

Exactly-once thường chỉ có thể được bảo đảm trong một phạm vi transaction hoặc giao thức cụ thể. Khi một pipeline gọi API, ghi database, publish message và triển khai cluster, không có một transaction phân tán chung tự động bao trùm tất cả các hệ thống đó.

Trong thực tế, nhiều hệ thống xây dựng hiệu ứng **effectively-once** bằng cách:

- Cho phép yêu cầu được gửi lại (at-least-once).
- Gán định danh ổn định cho một thao tác logic.
- Lưu trạng thái xử lý bền vững.
- Khử trùng lặp ở nơi thực hiện tác dụng phụ.
- Đối soát trạng thái khi caller không nhận được kết quả.

Mục tiêu là một thao tác logic chỉ tạo ra một hiệu ứng nghiệp vụ, dù request có thể được gửi nhiều lần.

## 4. Thiết kế thao tác có thể lặp lại an toàn

### Ưu tiên API đặt trạng thái mong muốn

Thay vì API tăng hoặc giảm một giá trị, hãy thiết kế API nhận trạng thái đích khi nghiệp vụ cho phép.

Ví dụ:

~~~http
PUT /environments/production/services/order-api
Content-Type: application/json

{
  "version": "2.8.1",
  "replicas": 4
}
~~~

Caller có thể gửi lại cùng yêu cầu. Server đọc trạng thái hiện tại và đưa resource về version 2.8.1 với 4 replica.

HTTP định nghĩa PUT có ngữ nghĩa idempotent, nhưng implementation vẫn phải tuân thủ ngữ nghĩa đó. Nếu mỗi PUT lại tạo một release record mới hoặc gửi một thông báo nghiệp vụ mới, toàn bộ thao tác vẫn có tác dụng phụ trùng lặp.

### Dùng định danh tài nguyên ổn định

Resource cần có identity để lần chạy sau tìm đúng đối tượng đã tạo:

- Deployment name theo service và environment.
- Release ID theo repository, commit hoặc release version.
- Cloud resource name theo hệ thống và mục đích.
- Migration ID theo phiên bản schema.
- Operation ID cho một lần yêu cầu logic.

Tránh tạo tên ngẫu nhiên mới mỗi lần retry nếu mục tiêu là tiếp tục cùng một thao tác.

### Dùng idempotency key cho thao tác tạo mới

Với API tạo release, cấp tài nguyên hoặc xử lý thanh toán, có thể gửi một idempotency key. Server lưu key và kết quả xử lý tương ứng.

Ví dụ:

~~~http
POST /deployments
Idempotency-Key: order-api:production:release-2.8.1
Content-Type: application/json

{
  "service": "order-api",
  "environment": "production",
  "artifactDigest": "sha256:..."
}
~~~

Nếu cùng key được gửi lại, server trả lại operation hoặc kết quả đã ghi nhận thay vì tạo deployment thứ hai.

Một idempotency key tốt cần:

- Đại diện cho một thao tác nghiệp vụ cụ thể.
- Ổn định qua các lần retry của cùng thao tác.
- Khác nhau giữa các lần triển khai có chủ đích.
- Được lưu ở phía server trong thời gian đủ dài.
- Có phạm vi rõ, chẳng hạn theo tenant, endpoint hoặc loại thao tác.
- Được ràng buộc với payload để tránh dùng cùng key cho hai yêu cầu khác nhau.

Không tạo UUID mới ở mỗi lần retry. Nếu mỗi lần gửi có key khác, server không thể nhận biết đó là cùng một thao tác logic.

### Ràng buộc key với payload

Nếu một key đã được sử dụng với payload A, request tiếp theo cùng key nhưng payload B phải được xử lý như xung đột hoặc yêu cầu không hợp lệ. Không được âm thầm trả kết quả của A cho B hoặc thực hiện B như một thao tác mới.

Có thể lưu hash của payload chuẩn hóa cùng key:

| Trường | Mục đích |
|---|---|
| idempotency_key | Nhận diện thao tác logic |
| request_hash | Phát hiện payload khác với lần đầu |
| status | Trạng thái xử lý |
| operation_id | Tham chiếu tới công việc thực tế |
| response/result | Kết quả có thể trả lại khi retry |
| created_at / expires_at | Quản lý vòng đời bản ghi |

Việc ghi key và tạo operation phải được thực hiện nguyên tử trong phạm vi database của service nhận request, thường bằng unique constraint và transaction.

## 5. Lưu trạng thái thao tác bằng state machine

Một thao tác triển khai dài không nên chỉ có hai trạng thái success/failed. Nó có thể đang chờ, đang chạy hoặc chưa rõ kết quả.

Ví dụ state machine:

~~~text
          +-----------+
          | REQUESTED |
          +-----+-----+
                |
                v
          +-----------+
          |  RUNNING  |
          +-----+-----+
                |
       +--------+---------+
       |                  |
       v                  v
 +-----------+       +-----------+
 | SUCCEEDED |       |  UNKNOWN  |
 +-----------+       +-----+-----+
                           |
                     Reconcile state
                           |
                 +---------+---------+
                 |                   |
                 v                   v
            SUCCEEDED          RETRYABLE
                                     |
                                     v
                                  RUNNING

Terminal failure: FAILED
~~~

Các trạng thái có thể dùng:

| Trạng thái | Ý nghĩa | Hành động phù hợp |
|---|---|---|
| REQUESTED | Đã ghi nhận yêu cầu | Worker có thể nhận xử lý |
| RUNNING | Đang thực thi | Theo dõi lease/heartbeat |
| SUCCEEDED | Hoàn tất đã xác nhận | Trả lại kết quả khi retry |
| FAILED_RETRYABLE | Lỗi tạm thời, biết chắc có thể thử lại | Retry theo chính sách |
| FAILED_TERMINAL | Lỗi không thể tự khắc phục bằng retry | Dừng và yêu cầu xử lý |
| UNKNOWN | Caller hoặc worker mất dấu kết quả | Tra cứu và reconcile |
| CANCELLED | Đã hủy theo chính sách | Xác minh tác động trước khi tạo thao tác mới |

Không phải hệ thống nào cũng cần đủ các trạng thái trên. Điều quan trọng là phân biệt lỗi đã biết với kết quả chưa rõ và định nghĩa chuyển trạng thái hợp lệ.

### Dùng chuyển trạng thái có điều kiện

Nhiều worker có thể cùng nhận một operation sau khi lease hết hạn hoặc job bị retry. Hãy dùng transaction, compare-and-set hoặc optimistic locking để chỉ một worker có thể nhận quyền xử lý hợp lệ tại một thời điểm.

Ví dụ, chỉ chuyển REQUESTED sang RUNNING nếu trạng thái hiện tại vẫn là REQUESTED. Nếu worker khác đã chuyển thành RUNNING hoặc SUCCEEDED, worker mới phải đọc lại trạng thái thay vì tiếp tục xử lý.

### Lease và fencing token

Lease cho phép worker giữ quyền xử lý trong một khoảng thời gian. Nếu worker chết, lease hết hạn và worker khác có thể tiếp tục.

Tuy nhiên, worker cũ có thể sống lại sau khi lease hết hạn và tiếp tục ghi dữ liệu. Fencing token giải quyết tình huống này bằng một số phiên bản tăng dần; hệ thống đích chỉ chấp nhận thao tác từ worker có token mới nhất. Lease mà không có fencing hoặc kiểm soát tương đương có thể không ngăn được hai worker cùng tác động.

## 6. Xử lý kết quả chưa rõ bằng reconciliation

Khi caller timeout sau khi gửi request, không nên mặc định tạo operation mới. Hãy tra cứu operation cũ bằng idempotency key, operation ID hoặc resource identity.

Quy trình tổng quát:

1. Ghi nhận request ID và idempotency key trước khi gửi.
2. Gửi yêu cầu tới hệ thống đích.
3. Nếu nhận phản hồi thành công, lưu operation ID và kết quả.
4. Nếu timeout hoặc mất kết nối, đánh dấu trạng thái là UNKNOWN.
5. Truy vấn hệ thống đích bằng key hoặc operation ID.
6. Nếu thao tác đã hoàn tất, cập nhật SUCCEEDED.
7. Nếu đang chạy, tiếp tục polling với khoảng chờ phù hợp.
8. Nếu chắc chắn chưa được tiếp nhận, gửi lại cùng key.
9. Nếu hệ thống không thể xác định, dừng tự động và yêu cầu đối soát thủ công thay vì tạo thêm tác dụng phụ.

### Reconciliation theo trạng thái mong muốn

Với triển khai kiểu declarative, hệ thống có thể so sánh:

- Desired state: version 2.8.1, 4 replicas.
- Observed state: version 2.8.1, 3 replicas.
- Difference: thiếu 1 replica.
- Action: tiếp tục reconcile để đạt desired state.

Nếu observed state đã đúng, thao tác hoàn tất dù caller trước đó bị ngắt. Nếu observed state ở trạng thái chuyển tiếp, chờ hoặc tiếp tục controller. Nếu trạng thái không hợp lệ, tạo cảnh báo và yêu cầu can thiệp.

### Không suy đoán từ log cuối cùng

Log có thể bị thiếu do tiến trình chết trước khi flush, hoặc log "request sent" không chứng minh server đã commit. Dùng trạng thái bền vững từ hệ thống sở hữu resource làm nguồn sự thật. Log và trace giúp điều tra nhưng không thay thế operation record hoặc trạng thái thực tế.

## 7. Retry đúng loại lỗi và có giới hạn

Không phải lỗi nào cũng nên retry.

### Phân loại lỗi

| Loại lỗi | Ví dụ | Chính sách |
|---|---|---|
| Lỗi tạm thời | Network reset, timeout, service unavailable | Retry có backoff nếu thao tác an toàn |
| Rate limit | HTTP 429 | Tuân thủ Retry-After hoặc giới hạn do server cung cấp |
| Lỗi server tạm thời | HTTP 502, 503, 504 | Retry có giới hạn, giữ cùng idempotency key |
| Lỗi xác thực | HTTP 401 | Không retry liên tục; sửa identity/credential |
| Lỗi phân quyền | HTTP 403 | Dừng và xử lý policy |
| Dữ liệu không hợp lệ | HTTP 400, schema validation failure | Không retry cùng payload |
| Xung đột trạng thái | HTTP 409 hoặc version conflict | Đọc trạng thái mới và reconcile |
| Không tìm thấy | HTTP 404 | Tùy thao tác; có thể là lỗi terminal hoặc trạng thái chưa đồng bộ |
| Kết quả không rõ | Timeout sau khi gửi request | Tra cứu trạng thái trước khi tạo thao tác mới |

Mã HTTP chỉ là một tín hiệu; API riêng có thể dùng status khác. Hãy dựa vào hợp đồng của service và phân loại lỗi rõ ràng.

### Exponential backoff và jitter

Nếu nhiều job cùng retry ngay lập tức, chúng có thể tạo một đợt tải mới lên hệ thống đang gặp sự cố. Exponential backoff tăng dần khoảng chờ giữa các lần thử; jitter thêm độ ngẫu nhiên để giảm việc nhiều caller đồng bộ retry.

Ví dụ:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait = random(0, delay)
~~~

Có thể cấu hình base delay 1 giây, max delay 30 giây và giới hạn số lần retry. Các con số phải phù hợp SLA, thời gian deploy và hướng dẫn từ service đích.

### Giới hạn tổng thời gian và số lần thử

Một retry policy nên có:

- Số lần thử tối đa.
- Deadline tổng cho thao tác.
- Timeout riêng cho mỗi request.
- Backoff tối đa và jitter.
- Cách xử lý Retry-After.
- Điều kiện dừng khi lỗi terminal.
- Cách ghi nhận kết quả unknown khi hết thời gian.

Không retry vô hạn. Pipeline phải có trạng thái kết thúc rõ ràng và cung cấp đủ dữ liệu để người vận hành tiếp tục điều tra.

### Tránh retry lồng nhau gây khuếch đại

Nếu HTTP client retry 3 lần, SDK retry 3 lần và CI job retry 3 lần, một thao tác logic có thể tạo tới 27 request. Cần thống nhất retry budget ở các tầng. Một tầng nên chịu trách nhiệm chính hoặc các tầng phải phối hợp qua deadline và idempotency key chung.

## 8. Thiết kế CI/CD để resume cùng một thao tác

Một job có thể bị hủy, runner mất kết nối hoặc pipeline được chạy lại thủ công. Nếu mỗi lần chạy tạo deployment ID mới, hệ thống không thể biết đó là tiếp tục thao tác cũ hay một lần phát hành mới.

### Tạo operation identity ổn định

Một định danh thao tác có thể được tạo từ:

- Service.
- Environment.
- Release hoặc deployment version.
- Artifact digest.
- Source commit.
- Loại thao tác.

Ví dụ:

~~~text
operation_key =
  service + environment + release_version + artifact_digest
~~~

Nếu cùng một release được retry, key phải giữ nguyên. Nếu artifact digest hoặc release version thay đổi, đó là một thao tác khác và cần key mới.

Không nên chỉ dùng CI run ID nếu mỗi lần rerun tạo một run ID mới. Có thể lưu run ID để truy vết, nhưng operation key cần nhận diện cùng một ý định phát hành qua nhiều lần chạy.

### Tách request khỏi worker thực thi

Một API triển khai tốt có thể trả về operation ID ngay khi nhận yêu cầu:

~~~http
POST /deployments
Idempotency-Key: order-api:production:2.8.1:sha256-abc123

HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "op-4821",
  "status": "RUNNING"
}
~~~

Caller lưu operation ID. Nếu job bị ngắt, lần chạy tiếp theo tra cứu operation này thay vì gửi một yêu cầu tạo mới.

Nếu server nhận cùng key lần nữa, server trả lại operation hiện tại hoặc kết quả đã hoàn tất. Caller có thể tiếp tục polling.

### Ví dụ pseudo-code cho deploy client

~~~python
def deploy_release(service, environment, release, digest):
    key = f"{service}:{environment}:{release}:{digest}"

    operation = deployment_api.find_by_idempotency_key(key)

    if operation is None:
        try:
            operation = deployment_api.create(
                service=service,
                environment=environment,
                release=release,
                artifact_digest=digest,
                idempotency_key=key,
            )
        except TimeoutError:
            operation = deployment_api.find_by_idempotency_key(key)
            if operation is None:
                raise UnknownOutcome(key)

    return wait_until_terminal(operation.id)
~~~

Ví dụ này giả định API hỗ trợ tra cứu bằng key và lưu key bền vững. Nếu API không có khả năng đó, client cần một cơ chế đối soát khác; không được xem việc tra cứu không tìm thấy ngay lập tức là bằng chứng chắc chắn request chưa tới server, vì dữ liệu có thể chưa được đồng bộ.

## 9. Triển khai declarative và reconcile desired state

Các công cụ quản lý hạ tầng hoặc orchestration thường hoạt động theo mô hình khai báo: người dùng mô tả trạng thái mong muốn, controller so sánh với trạng thái hiện tại rồi điều chỉnh.

Ví dụ manifest Kubernetes:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: app
          image: registry.example.com/order-api@sha256:...
~~~

Áp dụng cùng manifest nhiều lần thường hướng resource tới cùng desired state. Tuy nhiên:

- Image nên tham chiếu digest bất biến.
- Không dùng tên resource ngẫu nhiên mỗi lần.
- Admission webhook hoặc controller có thể tạo side effect riêng.
- Job migration, hook hoặc notification cần idempotency riêng.
- Cần theo dõi rollout status, không chỉ dựa vào lệnh apply trả về thành công.

### Apply và wait là hai việc khác nhau

Lệnh apply có thể đã cập nhật desired state nhưng Pod chưa sẵn sàng. Nếu job bị ngắt trong lúc chờ, lần chạy sau nên đọc resource và tiếp tục chờ rollout. Không cần tạo một Deployment mới.

Một quy trình resume:

1. Apply manifest với resource identity cố định.
2. Ghi nhận generation hoặc revision.
3. Theo dõi rollout status.
4. Nếu job bị ngắt, đọc lại Deployment và ReplicaSet.
5. So sánh observed generation với desired generation.
6. Tiếp tục chờ hoặc reconcile.
7. Chỉ đánh dấu thành công khi readiness và tiêu chí sau triển khai đạt.

Không coi việc API server chấp nhận manifest là bằng chứng ứng dụng đã phục vụ traffic an toàn.

## 10. Tạo tài nguyên cloud an toàn khi retry

Các thao tác tạo bucket, database, queue, load balancer hoặc service account có thể gặp tình huống request đã thành công nhưng caller timeout.

### Dùng resource name và client token ổn định

Nếu cloud API hỗ trợ idempotency token hoặc client request token, dùng một token ổn định cho cùng thao tác logic. Nếu không, có thể:

- Tạo resource với tên xác định.
- Tìm resource theo tên hoặc tag do hệ thống quản lý.
- Kiểm tra thuộc tính trước khi dùng lại.
- Nếu resource đã tồn tại và đúng cấu hình, coi thao tác đã đạt.
- Nếu resource tồn tại nhưng cấu hình khác, xử lý conflict thay vì ghi đè mù quáng.

### Kiểm tra ownership

Tên cố định có thể bị một hệ thống khác sử dụng. Không nên thấy resource tồn tại rồi mặc định đó là resource do deployment hiện tại tạo.

Có thể gắn metadata như:

- Owner service.
- Environment.
- Managed-by.
- Release hoặc stack ID.
- Resource schema version.

Trước khi cập nhật, xác minh ownership và cấu hình. Nếu không khớp, dừng và yêu cầu điều tra.

### Terraform và state

Terraform dùng state để ánh xạ resource trong cấu hình với resource thật. Nếu một lần apply bị ngắt, state hoặc thao tác provider có thể chưa phản ánh đầy đủ trạng thái.

Quy trình an toàn:

- Dùng remote state có locking.
- Không chạy đồng thời hai apply trên cùng state.
- Sau khi bị ngắt, đọc lại state và trạng thái cloud.
- Chạy plan để xem chênh lệch.
- Chỉ apply lại sau khi hiểu resource nào đã được tạo hoặc cập nhật.
- Không xóa state file để "làm lại từ đầu".
- Nếu resource tồn tại nhưng chưa được quản lý, dùng import hoặc quy trình recovery phù hợp.

Không dùng thao tác tạo mới để thay thế một lần apply chưa rõ kết quả.

## 11. Database migration và dữ liệu cần đặc biệt thận trọng

Migration thường có tác dụng phụ khó đảo ngược. Một lệnh thêm cột có thể an toàn khi chạy lại nếu được viết có điều kiện, nhưng một lệnh cộng tiền hoặc chuyển đổi dữ liệu có thể tạo sai lệch nếu chạy hai lần.

### Phân biệt schema migration và data migration

| Loại | Ví dụ | Rủi ro retry |
|---|---|---|
| Schema migration | Tạo bảng hoặc thêm cột | Có thể conflict nếu đối tượng đã tồn tại |
| Data migration | Chuyển đổi dữ liệu từ format cũ sang mới | Có thể xử lý trùng hoặc cập nhật sai |
| Backfill | Điền dữ liệu thiếu theo batch | Cần checkpoint và điều kiện cập nhật |
| Index migration | Tạo index lớn | Có thể tốn thời gian hoặc conflict khi đã tồn tại |
| Destructive migration | Xóa cột hoặc dữ liệu cũ | Khó rollback và có thể mất dữ liệu |

### Dùng migration history và version duy nhất

Công cụ migration thường lưu version hoặc migration ID đã chạy. Trước khi thực thi, kiểm tra migration history trong transaction hoặc cơ chế locking của tool. Một migration đã được đánh dấu thành công không nên chạy lại như migration mới.

Không sửa nội dung một migration đã áp dụng ở môi trường thật. Thay đổi cần được thể hiện bằng migration mới để lịch sử schema vẫn truy vết được.

### Viết migration có khả năng tiếp tục

Với data backfill lớn:

- Chia thành batch có giới hạn.
- Dùng khóa hoặc cursor ổn định.
- Cập nhật theo điều kiện để chỉ xử lý bản ghi chưa hoàn tất.
- Ghi checkpoint bền vững.
- Mỗi batch có transaction phù hợp.
- Sau khi bị ngắt, đọc checkpoint và tiếp tục.
- Có thể chạy lại batch gần nhất mà không tạo tác dụng phụ trùng.

Ví dụ, thay vì tăng counter cho mọi dòng mỗi lần job chạy, chỉ cập nhật các dòng chưa có migration marker. Với thao tác tài chính, cần ràng buộc duy nhất hoặc ledger để ngăn ghi nhận giao dịch hai lần.

### Expand-contract cho triển khai nhiều phiên bản

Khi rolling deployment, phiên bản cũ và mới có thể cùng truy cập database. Một chiến lược an toàn:

1. Expand: thêm cấu trúc mới mà phiên bản cũ vẫn tương thích.
2. Deploy code có khả năng đọc/ghi theo giai đoạn chuyển tiếp.
3. Backfill dữ liệu có checkpoint.
4. Chuyển đọc sang cấu trúc mới và xác minh.
5. Contract: chỉ xóa cấu trúc cũ khi không còn phiên bản phụ thuộc.

Không gộp thay đổi phá hủy schema vào cùng bước deploy đầu tiên nếu rollback ứng dụng vẫn cần cấu trúc cũ.

## 12. Tác dụng phụ bên ngoài: message, email, thanh toán và webhook

Không phải mọi thao tác có thể được biểu diễn thành desired state. Gửi email, tạo giao dịch thanh toán hoặc phát message thường tạo một sự kiện mới mỗi lần gọi.

### Inbox/deduplication ở consumer

Consumer có thể nhận cùng một message nhiều lần. Dùng message ID hoặc business event ID làm khóa duy nhất. Trước khi xử lý, kiểm tra message đã được ghi nhận chưa; việc ghi dấu đã xử lý và cập nhật dữ liệu nghiệp vụ nên nằm trong cùng transaction nếu có thể.

Ví dụ:

~~~text
Receive message with event_id
          |
          v
Insert event_id into inbox table
          |
     unique constraint
       /       \
    new       duplicate
     |            |
     v            v
Apply effect   Return prior result
     |
     v
Commit inbox + business update
~~~

Nếu consumer đánh dấu message hoàn tất trước khi cập nhật nghiệp vụ, process chết giữa hai bước có thể làm mất hiệu ứng. Nếu cập nhật nghiệp vụ trước rồi chết trước khi đánh dấu, message được gửi lại có thể lặp hiệu ứng. Transaction chung hoặc pattern phù hợp giúp giải quyết khoảng trống này.

### Transactional outbox

Nếu một transaction vừa cập nhật database vừa cần publish event, hai thao tác độc lập có thể không đồng bộ. Transactional outbox ghi event vào bảng outbox cùng transaction với dữ liệu nghiệp vụ. Worker publish event và đánh dấu đã gửi.

Worker có thể publish cùng event nhiều lần nếu chết sau khi gửi nhưng trước khi ghi trạng thái. Consumer vẫn cần deduplication. Outbox giúp tránh mất event giữa database commit và message publish, nhưng không tự tạo exactly-once xuyên suốt broker và consumer.

### API thanh toán và thao tác không thể đảo ngược

Với thanh toán, hoàn tiền hoặc cấp phát tài nguyên có giá trị, dùng idempotency key do hệ thống nghiệp vụ quản lý và lưu kết quả giao dịch. Không retry một request tạo giao dịch bằng key mới chỉ vì client timeout.

Nếu nhà cung cấp không hỗ trợ idempotency, cần tra cứu giao dịch theo merchant reference hoặc business reference trước khi gửi lại. Khi không xác định được trạng thái, dừng tự động và chuyển sang đối soát.

## 13. Rollback, retry và compensation không giống nhau

Ba khái niệm này giải quyết những vấn đề khác nhau:

- **Retry:** thử thực hiện lại cùng một thao tác sau lỗi tạm thời hoặc khi có thể chứng minh lần trước chưa hoàn tất.
- **Rollback:** đưa hệ thống về một phiên bản hoặc trạng thái trước đó, nếu việc quay lại còn khả thi.
- **Compensation:** thực hiện một thao tác nghiệp vụ mới để bù cho hiệu ứng đã xảy ra.

Ví dụ:

| Tình huống | Retry | Rollback | Compensation |
|---|---|---|---|
| Deploy version mới chưa rollout | Tiếp tục apply cùng digest | Quay về digest trước | Thường không cần |
| Migration thêm cột tương thích | Tiếp tục migration | Có thể giữ cột, không cần xóa ngay | Thường không cần |
| Đã gửi email | Không gửi lại nếu đã ghi nhận gửi | Không thể thu hồi email | Gửi thông báo đính chính nếu cần |
| Đã thu tiền | Không tạo charge mới khi chưa rõ kết quả | Có thể không thể xóa giao dịch | Tạo refund theo business reference |
| Đã tạo cloud resource | Tra cứu và tiếp tục cấu hình | Xóa resource nếu an toàn | Chuyển hoặc giải phóng tài nguyên theo quy trình |

Compensation không phải lúc nào cũng đưa hệ thống về trạng thái ban đầu. Một khoản hoàn tiền tạo ra giao dịch mới và có audit riêng. Vì vậy, không nên dùng từ rollback cho mọi hành động khắc phục.

### Thiết kế rollback cũng phải lũy đẳng

Một job rollback có thể bị timeout sau khi đã chuyển traffic về version cũ. Lần chạy lại phải kiểm tra trạng thái hiện tại và tiếp tục đưa hệ thống về digest đích, không tạo thêm bản release hoặc chạy một chuỗi lệnh đảo ngược nhiều lần.

Hãy cấp operation key riêng cho rollback và lưu version đích cần khôi phục.

## 14. Lock và xử lý hai lần deploy đồng thời

Idempotency xử lý việc lặp cùng một thao tác; nó không tự giải quyết hai thao tác khác nhau cùng lúc.

Ví dụ:

- Pipeline A muốn deploy version 2.8.1.
- Pipeline B muốn deploy version 2.8.2.
- Cả hai cùng đọc trạng thái hiện tại là 2.8.0.
- A và B lần lượt cập nhật tài nguyên, khiến trạng thái cuối không theo thứ tự release mong muốn.

Cần kiểm soát concurrency theo service/environment:

- Một deployment active cho mỗi service và environment, nếu chính sách yêu cầu tuần tự.
- Dùng lock có lease hoặc hàng đợi.
- Gắn sequence/version hoặc generation vào operation.
- Từ chối thao tác cũ nếu version mới hơn đã được chấp nhận.
- Dùng optimistic concurrency như If-Match hoặc resource version.
- Không giữ lock vô hạn khi worker chết; cần lease và recovery.

### Không chỉ dựa vào CI concurrency group

CI có thể hỗ trợ concurrency group để tránh hai workflow cùng deploy. Tuy nhiên, thao tác có thể được khởi chạy từ công cụ khác hoặc một workflow cũ vẫn đang chạy sau khi job bị hủy. Hệ thống đích nên có cơ chế concurrency hoặc version check riêng, không chỉ dựa vào khóa ở phía CI.

## 15. Kiểm thử khả năng retry và phục hồi

Idempotency không thể chỉ xác nhận bằng cách đọc code. Cần kiểm tra hành vi khi lỗi xảy ra ở các điểm khác nhau.

### Failure injection

Thử mô phỏng:

- Caller chết trước khi gửi request.
- Server commit xong nhưng response bị drop.
- Worker chết giữa hai bước side effect.
- Lease hết hạn trong khi worker cũ vẫn chạy.
- Hai request cùng idempotency key tới đồng thời.
- Cùng key nhưng payload khác.
- Job bị rerun khi operation đang RUNNING.
- Job bị rerun sau khi operation đã SUCCEEDED.
- Database tạm mất kết nối khi ghi trạng thái.
- Cloud API trả 429 hoặc 503.

### Kỳ vọng của test

| Tình huống | Kết quả mong muốn |
|---|---|
| Cùng key, cùng payload, gửi đồng thời | Chỉ một operation logic được tạo |
| Cùng key, payload khác | Bị từ chối như conflict |
| Timeout sau commit | Tra cứu thấy operation đã tồn tại; không tạo operation thứ hai |
| Retry khi đang chạy | Trả trạng thái hiện tại hoặc operation ID cũ |
| Retry sau thành công | Trả lại kết quả cũ |
| Worker cũ quay lại sau lease expiry | Fencing token ngăn ghi trạng thái lỗi thời |
| Lỗi validation | Dừng, không retry |
| Lỗi tạm thời | Retry theo budget và backoff |
| Migration bị ngắt giữa các batch | Tiếp tục từ checkpoint, không áp dụng trùng |
| Hai release cạnh tranh | Lock/version policy quyết định rõ thứ tự |

Nên kiểm tra cả trạng thái dữ liệu cuối và số lần side effect thực sự xảy ra. Chỉ xác nhận API trả HTTP 200 là chưa đủ.

## 16. Quan sát, audit và vận hành sau gián đoạn

Khi job bị ngắt, người vận hành cần biết nên resume, retry, reconcile hay dừng. Điều đó đòi hỏi log và metadata đủ để nhận diện cùng một thao tác.

Mỗi operation nên có:

- Operation ID và idempotency key.
- Service và environment.
- Release version, commit SHA và artifact digest.
- Pipeline run ID và job attempt.
- Thời điểm bắt đầu, cập nhật và hoàn tất.
- Trạng thái hiện tại và lịch sử chuyển trạng thái.
- Số lần retry, loại lỗi và thời gian backoff.
- External resource ID hoặc deployment revision.
- Người hoặc identity khởi tạo.
- Kết quả health check và rollback/compensation nếu có.

Không ghi secret hoặc token vào log. Có thể ghi fingerprint hoặc identifier không nhạy cảm để truy vết.

### Metrics hữu ích

- Tỷ lệ operation retry.
- Số operation ở trạng thái UNKNOWN quá thời hạn.
- Số request được deduplicated.
- Tỷ lệ retry thành công.
- Thời gian từ REQUESTED tới SUCCEEDED.
- Số operation phải can thiệp thủ công.
- Số lần conflict do concurrent deployment.
- Số migration được resume từ checkpoint.
- Tỷ lệ rollback và compensation.

Nếu tỷ lệ retry tăng đột ngột, có thể hệ thống đích đang quá tải hoặc timeout cấu hình quá thấp. Nếu UNKNOWN tăng, khả năng tra cứu hoặc reconciliation có thể chưa đủ tin cậy.

## 17. Quy trình xử lý khi pipeline bị ngắt

Khi một job deploy bị ngắt hoặc có kết quả không rõ, người vận hành có thể làm theo trình tự:

1. Xác định operation key, release version và artifact digest của lần chạy.
2. Kiểm tra trạng thái pipeline và thời điểm job mất kết nối.
3. Tra cứu operation ở hệ thống triển khai bằng operation ID hoặc idempotency key.
4. Kiểm tra observed state của resource thật, không chỉ dựa vào log caller.
5. Nếu operation đang chạy, tiếp tục polling hoặc chờ worker hiện tại.
6. Nếu đã thành công, cập nhật pipeline record và chạy bước verify hậu triển khai nếu chưa có.
7. Nếu thất bại terminal, dừng và xử lý nguyên nhân.
8. Nếu xác nhận chưa được tiếp nhận, retry cùng operation key.
9. Nếu kết quả vẫn unknown, giữ trạng thái không xác định, cảnh báo và yêu cầu đối soát.
10. Chỉ tạo operation key mới khi đó thực sự là một release hoặc ý định triển khai mới.

Quy trình này giúp phân biệt "tiếp tục một lần triển khai" với "bắt đầu một lần triển khai khác".

## 18. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Timeout thì chạy lại toàn bộ script | Có thể tạo side effect trùng | Tra cứu operation và reconcile trước |
| Tạo idempotency key mới ở mỗi retry | Server không nhận ra request trùng | Giữ key ổn định cho cùng thao tác logic |
| Dùng lệnh tăng/giảm tương đối | Retry làm trạng thái lệch dần | Đặt desired state tuyệt đối |
| Chỉ lưu trạng thái ở memory của job | Runner chết làm mất dấu operation | Lưu operation record bền vững |
| Đánh dấu failed khi không nhận response | Có thể tạo operation mới trong khi thao tác cũ đã chạy | Dùng trạng thái UNKNOWN |
| Retry mọi lỗi | Lặp lỗi validation/auth và tăng tải | Phân loại lỗi, retry có budget |
| Retry ngay lập tức | Tạo retry storm | Exponential backoff và jitter |
| Retry lồng ở nhiều tầng | Khuếch đại số request | Thống nhất retry budget |
| Tin API 202 Accepted là deploy hoàn tất | Tác vụ bất đồng bộ có thể vẫn đang chạy | Poll operation và xác minh observed state |
| Chạy migration dữ liệu không checkpoint | Có thể xử lý trùng hoặc bỏ sót | Batch, marker, transaction và history |
| Dùng cache/state file không khóa | Hai pipeline cùng sửa trạng thái | Lock, version và backend state phù hợp |
| Dùng artifact mới cho lần retry cùng release | Một thao tác logic có thể đổi đầu vào giữa chừng | Gắn operation với digest bất biến |
| Coi compensation là rollback hoàn toàn | Có thể bỏ sót tác động đã xảy ra | Theo dõi compensation như giao dịch riêng |

## 19. Checklist thiết kế thao tác deploy có thể phục hồi

### Định danh và trạng thái

- [ ] Mỗi thao tác logic có operation ID hoặc idempotency key ổn định.
- [ ] Cùng thao tác retry giữ nguyên key và payload.
- [ ] Key được ràng buộc với hash payload.
- [ ] Operation record được lưu bền vững.
- [ ] Trạng thái UNKNOWN được phân biệt với FAILED.
- [ ] Có quy tắc chuyển trạng thái và kiểm soát worker cạnh tranh.
- [ ] Có lease, fencing hoặc cơ chế ngăn worker cũ ghi đè.

### Retry và reconciliation

- [ ] Phân loại lỗi transient, terminal và unknown.
- [ ] Chỉ retry khi thao tác an toàn hoặc server hỗ trợ deduplication.
- [ ] Có exponential backoff, jitter, max attempts và deadline.
- [ ] Tuân thủ Retry-After hoặc hướng dẫn của service đích.
- [ ] Không retry vô hạn hoặc retry lồng gây khuếch đại.
- [ ] Có API hoặc cách tra cứu operation/resource hiện tại.
- [ ] Sau timeout, reconcile trước khi tạo operation mới.

### Triển khai và tác dụng phụ

- [ ] Artifact gắn với digest bất biến.
- [ ] Desired state dùng resource identity ổn định.
- [ ] Database migration có history và khả năng resume.
- [ ] Message consumer có deduplication.
- [ ] Email, payment và webhook có business reference hoặc idempotency key.
- [ ] Rollback và compensation có operation identity riêng.
- [ ] Có concurrency control cho service/environment.

### Vận hành

- [ ] Log và trace có operation ID, release và artifact digest.
- [ ] Metrics theo dõi retry, unknown và deduplication.
- [ ] Có test failure injection ở các điểm commit/response/worker.
- [ ] Có quy trình thủ công cho trạng thái không thể tự xác định.
- [ ] Không đánh dấu thành công chỉ vì API chấp nhận request.
- [ ] Chỉ kết thúc deploy sau khi health check và điều kiện hậu triển khai đạt.

## Kết luận

Một tiến trình bị ngắt không đồng nghĩa thao tác ở hệ thống đích chưa xảy ra. Khi kết quả chưa rõ, pipeline phải tra cứu trạng thái và reconcile trước khi tạo thêm tác dụng phụ. Hãy thiết kế thao tác theo desired state, dùng định danh và idempotency key ổn định, lưu state machine bền vững, phân loại lỗi và retry có giới hạn. Với migration, message, payment và resource cloud, cần bổ sung checkpoint, deduplication, locking hoặc compensation phù hợp. Nhờ đó, cùng một ý định triển khai có thể được tiếp tục an toàn sau timeout, runner failure hoặc job rerun mà không tạo release, giao dịch hay thay đổi tài nguyên trùng lặp.

