# Rolling update và tương thích giữa các phiên bản ứng dụng

Trong chương **Vòng đời Pod** của **SPRING_CLOUD_KUBERNETES**, rolling update là cách thay dần các Pod của một ứng dụng bằng các Pod mang cấu hình triển khai mới. Trong một khoảng thời gian, phiên bản cũ và mới cùng tồn tại, cùng được khám phá và có thể cùng nhận lưu lượng.

Kubernetes điều phối số lượng và vòng đời Pod. Ứng dụng phải bảo đảm các phiên bản cùng tồn tại vẫn hiểu được API, dữ liệu, thông điệp và cấu hình của nhau. Một rollout có tất cả Pod Ready vẫn có thể làm hỏng nghiệp vụ nếu phiên bản mới ghi dữ liệu mà phiên bản cũ không đọc được.

Bài học sử dụng dịch vụ `order-service` có ba replica. Phiên bản v2 bổ sung thông tin tiền tệ vào phản hồi nhưng duy trì hợp đồng cũ trong thời gian chuyển đổi. Phần cấu hình ứng dụng minh họa dùng Java 17 và Spring Boot 3.5.x; các tính năng Spring Cloud Kubernetes được liên hệ theo vai trò discovery, load balancing và cập nhật cấu hình, không phải điều kiện bắt buộc để Deployment rolling update.

## 1. Rolling update tạo ra một hệ thống có nhiều phiên bản

Khi `spec.template` của Deployment thay đổi, Deployment controller quản lý một ReplicaSet mới và thay dần Pod thuộc ReplicaSet cũ. Thay image, biến môi trường hoặc tên ConfigMap được tham chiếu trong Pod template đều có thể tạo thay đổi cần rollout. [Kubernetes: cập nhật Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#updating-a-deployment).

Trong tình huống thông thường:

~~~mermaid
flowchart LR
    Client[Client cũ hoặc mới] --> Service[Service order-service]
    Service --> OldA[Pod v1]
    Service --> OldB[Pod v1]
    Service --> NewA[Pod v2]
    OldA --> DB[(Dữ liệu dùng chung)]
    OldB --> DB
    NewA --> DB
    OldA --> Queue[Hàng đợi và cache]
    NewA --> Queue
~~~

Service có selector ổn định theo ứng dụng nên không tự phân loại request theo phiên bản API. Hai request liên tiếp của cùng một client có thể đến hai phiên bản khác nhau. Một kết nối dài cũng có thể giữ client trên một Pod cũ lâu hơn dự kiến.

Do đó, một lượt triển khai phải giải quyết đồng thời:

- **Khả năng phục vụ:** còn đủ Pod sẵn sàng và đủ tài nguyên trong lúc thay thế.
- **Tương thích hợp đồng:** client cũ và mới gọi được những server đang cùng tồn tại.
- **Tương thích trạng thái:** các phiên bản hiểu được dữ liệu, session, cache và thông điệp dùng chung.
- **Khả năng quay lại:** bản cũ được chọn để rollback vẫn hoạt động với trạng thái đã thay đổi.

Các Pod hết v1 trong Deployment chưa chắc toàn hệ thống hết thành phần cũ. Một worker ở Deployment khác, một client chưa nâng cấp hoặc thông điệp trong hàng đợi vẫn có thể dùng hợp đồng cũ.

## 2. Những tham số nào điều khiển tiến độ thay Pod?

Ví dụ:

~~~yaml
spec:
  replicas: 3
  minReadySeconds: 10
  progressDeadlineSeconds: 300
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
~~~

### maxUnavailable và maxSurge

| Tham số | Ý nghĩa trong ví dụ |
| --- | --- |
| `replicas: 3` | Mức replica mong muốn khi ổn định là ba |
| `maxUnavailable: 0` | Controller không chủ động giảm mức available xuống dưới ba trong quá trình rollout bình thường |
| `maxSurge: 1` | Có thể tạo thêm một replica để thay dần |
| `minReadySeconds: 10` | Pod mới cần giữ Ready đủ thời gian trước khi được Deployment tính là available |
| `progressDeadlineSeconds: 300` | Báo rollout không tiến triển sau khoảng thời gian cấu hình |

Hai giá trị rolling update có thể là số tuyệt đối hoặc phần trăm. Khi dùng phần trăm, `maxUnavailable` làm tròn xuống và `maxSurge` làm tròn lên. Chúng không được đồng thời bằng 0. [Hướng dẫn rolling update của Kubernetes](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/).

Với ba replica, `25%` tương ứng với unavailable bằng 0 và surge bằng 1. Trong bài thực hành, dùng số tuyệt đối để nhìn rõ ý định.

Một trình tự minh họa:

| Giai đoạn | Pod v1 | Pod v2 | Điều cần quan sát |
| --- | --- | --- | --- |
| Trước cập nhật | 3 | 0 | Ba replica cũ phục vụ |
| Pod mới đang khởi động | 3 | 1 chưa Ready | Chưa rút Pod cũ chỉ vì Pod mới đã Running |
| Pod mới Ready nhưng chưa đủ thời gian | 3 | 1 Ready | Pod mới có thể đã nhận lưu lượng |
| Pod mới được tính available | Giảm dần | Tăng dần | Controller tiếp tục từng đợt |
| Hoàn tất | 0 | 3 available | Toàn bộ replica mong muốn dùng template mới |

Đây là cách đọc ý định rollout, không phải chuỗi sự kiện có thời gian cố định. Các Pod đang terminating có thể còn tiêu thụ tài nguyên, khiến tổng số Pod hiện hữu và mức dùng tài nguyên tạm thời vượt con số ba cộng một. [Deployment và Pod đang kết thúc](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment).

### Ready khác với available của Deployment

`minReadySeconds` phục vụ việc Deployment đánh giá Pod đã đủ ổn định để tiếp tục rollout. Nó **không trì hoãn việc Service gửi lưu lượng thêm 10 giây sau khi Pod Ready**.

Readiness phải phản ánh việc instance đã có khả năng nhận request. Không dùng `minReadySeconds` để bù cho một readiness probe báo thành công quá sớm. [Deployment API: minReadySeconds](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

### Progress deadline không phải lệnh tự rollback

Khi rollout không tiến triển đúng hạn, Kubernetes công bố condition có lý do `ProgressDeadlineExceeded`; controller vẫn có thể tiếp tục xử lý. Trường này không tự chọn revision cũ rồi phục hồi cho bạn.

Tương tự, `kubectl rollout status --timeout=...` giới hạn thời gian CLI chờ kết quả, không phải timeout áp đặt cho mọi công việc trong ứng dụng. [Deployment API: progressDeadlineSeconds](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

Nếu Pod mới không schedule được do thiếu CPU, quota hoặc capacity cho surge, rollout có thể dừng tiến độ dù các Pod cũ vẫn khỏe. `maxUnavailable: 0` không phải bảo đảm tuyệt đối không có lỗi request khi node hỏng hoặc ứng dụng có lỗi.

## 3. Xác định hợp đồng phải tương thích

Một release cần xét nhiều hợp đồng hơn JSON trả về cho HTTP:

| Hợp đồng | Ví dụ thay đổi | Điều có thể hỏng khi cùng chạy |
| --- | --- | --- |
| HTTP request | Thêm trường bắt buộc, đổi kiểu số | Client cũ không gửi được dữ liệu cần thiết |
| HTTP response | Xóa trường, thêm enum mới | Client cũ giải mã hoặc xử lý sai |
| Database | Đổi tên cột, thêm ràng buộc | Pod cũ đọc/ghi không còn hợp lệ |
| Thông điệp | Đổi schema hoặc ý nghĩa event | Consumer cũ không hiểu event mới |
| Cache/session | Đổi định dạng lưu Redis | Pod v1 không đọc được dữ liệu do v2 ghi |
| Cấu hình | Đổi tên key hoặc đơn vị | Hai phiên bản hiểu cùng giá trị theo hai cách |
| Credential | Thu hồi credential cũ quá sớm | Pod còn sống hoặc client cũ mất quyền |
| Hành vi nghiệp vụ | Thay quy tắc tính phí | Cùng request cho kết quả khác tùy Pod |

Tương thích ngược là một chiều: server mới vẫn hỗ trợ client hoặc dữ liệu cũ. Trong rolling update còn cần kiểm tra chiều còn lại: client hoặc dữ liệu do bản mới tạo có làm bản cũ đang sống thất bại không?

### Ma trận HTTP tối thiểu

| Client | Server v1 | Server v2 |
| --- | --- | --- |
| Client v1 | Hành vi nền đã có | Phải giữ hợp đồng cũ trong cửa sổ hỗ trợ |
| Client v2 ở chế độ chuyển tiếp | Phải chấp nhận phản hồi cũ và gửi request v1 hiểu được | Hoạt động với phần mở rộng |
| Client v2 đã bật tính năng chỉ v2 có | Có thể không hoạt động | Chỉ bật khi đích gọi được bảo đảm phù hợp |

Không chỉ thử tổ hợp “client mới gọi server mới”. Tổ hợp client mới gọi server cũ là nguồn lỗi phổ biến trong giai đoạn chuyển tiếp.

Nếu client mới bắt đầu gọi `/api/v2/orders` trong khi Service vẫn có Pod v1 chưa hỗ trợ đường dẫn đó, một số request có thể trả 404. Tạo đường dẫn mới không tự bảo đảm request được chuyển đến đúng phiên bản server.

## 4. Ví dụ mở rộng API đơn hàng

Phản hồi v1:

~~~json
{
  "orderId": "O-1001",
  "amount": 150000.00,
  "status": "CREATED"
}
~~~

Phản hồi v2 trong giai đoạn tương thích:

~~~json
{
  "orderId": "O-1001",
  "amount": 150000.00,
  "status": "CREATED",
  "currency": "VND"
}
~~~

Trong ví dụ, đơn hàng mẫu dùng VND ở cả hai phiên bản. V2 giữ tên, kiểu và ý nghĩa của ba trường cũ, đồng thời bổ sung `currency`.

Điều kiện để chuyển đổi an toàn:

- Client v1 đã được kiểm chứng chấp nhận trường JSON chưa biết.
- Client v2 không bắt buộc phản hồi phải có `currency` trong thời gian còn server v1.
- Giá trị mặc định VND chỉ hợp lệ vì hợp đồng dữ liệu cũ của ví dụ đã xác định mọi đơn hàng đó dùng VND.
- Request mới gửi đến server v1 vẫn tuân thủ hợp đồng mà server v1 hiểu.

Không suy ra “thêm trường luôn an toàn”. Client kiểm tra schema nghiêm ngặt, chữ ký payload hoặc logic so sánh toàn bộ JSON có thể không chấp nhận phần mở rộng.

### Các thay đổi trông nhỏ nhưng có thể phá vỡ hợp đồng

| Thay đổi | Rủi ro |
| --- | --- |
| Đổi `amount` từ số thành chuỗi | Client cũ có thể không deserialize được |
| Đổi đơn vị từ đồng sang nghìn đồng | Kiểu dữ liệu vẫn đúng nhưng số tiền sai |
| Thêm status `PENDING_REVIEW` | Client dùng enum đóng có thể thất bại |
| Đổi trường tùy chọn thành bắt buộc | Request cũ bị từ chối |
| Đổi cách xử lý `null` hoặc chuỗi rỗng | Kết quả nghiệp vụ có thể thay đổi |
| Trả HTTP status khác cho cùng tình huống | Retry hoặc xử lý lỗi phía client thay đổi |

Nếu cần thay đổi không tương thích, tạo một hợp đồng có phiên bản và kế hoạch chuyển client rõ ràng. Có thể dùng Service/route riêng cho phiên bản mới, nhưng vẫn phải xử lý tương thích của database và những thành phần dùng chung.

### Tách triển khai khỏi bật tính năng

Một trình tự thực dụng:

~~~text
1. Triển khai server có khả năng hiểu cả hợp đồng cũ và mới.
2. Giữ hành vi phát sinh request/event mới ở trạng thái tắt.
3. Xác nhận các server và consumer cần thiết đã hỗ trợ.
4. Bật tính năng theo phạm vi kiểm soát được.
5. Quan sát lỗi nghiệp vụ, dữ liệu và khả năng quay lại.
6. Chỉ gỡ hợp đồng cũ sau khi kết thúc cửa sổ hỗ trợ.
~~~

Feature flag cần có nghĩa rõ ràng ở từng phiên bản. Không để một key cấu hình mới được v1 bỏ qua nhưng v2 dùng để tạo dữ liệu mà v1 không đọc được, rồi coi việc “v1 không lỗi khi đọc config” là đủ.

## 5. Database: thay đổi theo nhiều giai đoạn

Một database dùng chung có thể được đọc/ghi bởi Pod v1 và v2 trong cùng thời điểm. Đổi tên cột trực tiếp hoặc xóa cột ở lúc v2 khởi động sẽ làm Pod v1 đang phục vụ gặp lỗi ngay.

Ví dụ đổi `customer_name` thành `display_name` với cùng ý nghĩa nghiệp vụ.

### 5.1. Expand: mở rộng schema trước

Ví dụ SQL PostgreSQL:

~~~sql
ALTER TABLE customer
ADD COLUMN display_name TEXT;
~~~

Thêm cột nullable cho phép code cũ tiếp tục ghi mà chưa biết cột mới. Tránh lập tức thêm `NOT NULL` nếu writer cũ không có cách cung cấp giá trị. Các câu lệnh thay schema, ràng buộc và dữ liệu có hành vi riêng về khóa và chi phí; cần lên kế hoạch theo database thực tế. [PostgreSQL: thay đổi bảng](https://www.postgresql.org/docs/current/ddl-alter.html).

Chưa đổi tên hoặc xóa `customer_name` trong giai đoạn này.

### 5.2. Bản chuyển tiếp: xác định một nguồn dữ liệu có thẩm quyền

Một lỗi thiết kế dễ gặp là:

~~~text
V2 đọc display_name nếu có, nếu không mới đọc customer_name.
V2 đã ghi cả hai cột.
V1 cập nhật customer_name nhưng không biết display_name.
V2 tiếp tục đọc display_name cũ và trả tên đã lỗi thời.
~~~

Chỉ thêm fallback không giải quyết được các writer cũ còn hoạt động.

Trong phương án minh họa, bản chuyển tiếp B thực hiện:

~~~text
Đọc: customer_name vẫn là nguồn có thẩm quyền.
Ghi: cập nhật customer_name và display_name trong cùng giao dịch.
~~~

Khi v1 cập nhật cột cũ, bản B vẫn đọc đúng nguồn chính. Cột mới có thể chưa đồng bộ hoàn toàn; chưa được dùng làm nguồn chính chỉ vì nó khác null.

### 5.3. Backfill và chuyển nguồn đọc sau khi đủ điều kiện

Trình tự đầy đủ có thể là:

| Giai đoạn | Code đang được hỗ trợ | Nguồn đọc chính | Cách ghi |
| --- | --- | --- | --- |
| A | v1 | Cột cũ | Cột cũ |
| Expand | v1 | Cột cũ | Cột cũ; schema đã có cột mới |
| B chuyển tiếp | v1 và B trong lúc rollout | Cột cũ | v1 ghi cũ; B ghi cả hai |
| Hoàn tất B, đóng rollback về v1 | Chỉ B hoặc bản tương thích hơn | Cột cũ | Tất cả writer ghi cả hai |
| Backfill và xác minh | B | Cột cũ | Đồng bộ dữ liệu mới có kiểm soát |
| C chuyển nguồn đọc | B và C | B đọc cũ; C đọc mới | Cả hai tiếp tục ghi cả hai |
| D ngừng dùng cột cũ | C và D trong lúc rollout | Cột mới | C ghi cả hai; D có thể chỉ ghi mới |
| Contract | Chỉ D và các bản không dùng cột cũ | Cột mới | Có thể bỏ cột cũ sau khi đóng rollback về C |

Ở bước C, rollback về B còn an toàn vì cả B và C ghi cả hai cột. Nhưng không được cho v1 trở lại làm writer đơn cột sau khi đã chuyển nguồn đọc, trừ khi có cơ chế đồng bộ tương ứng.

Ở bước D, dữ liệu cột cũ có thể không còn đầy đủ do D chỉ ghi mới. Vì vậy không còn coi rollback về B là lựa chọn mặc định. Trước khi xóa cột cũ, cũng phải loại bỏ mọi bản C có thể còn ghi vào cột đó.

Đây là kế hoạch minh họa; nếu cần giữ rollback về v1 lâu hơn, phải giữ nguồn cũ làm nguồn chính lâu hơn hoặc thiết kế đồng bộ tại database phù hợp.

### 5.4. Backfill không chỉ là một câu UPDATE

Một backfill cần xem xét:

- Chia phạm vi xử lý để không giữ giao dịch hoặc khóa quá lâu.
- Tránh ghi đè dữ liệu mới bằng ảnh chụp cũ trong lúc ứng dụng tiếp tục cập nhật.
- Có checkpoint và khả năng chạy lại.
- Kiểm tra độ đầy đủ, độ nhất quán và ý nghĩa dữ liệu.
- Tính cả các writer ngoài HTTP: batch job, consumer, công cụ quản trị và worker ở Deployment khác.

Đừng để mọi Pod mới cùng thực hiện một migration phá vỡ tương thích ngay lúc startup. Chọn cơ chế điều phối migration có kiểm soát và biết rõ phần nào được thực hiện một lần, phần nào được phép lặp lại.

Một thao tác rollout undo chỉ khôi phục Pod template. Nó không tự đảo ngược migration, dữ liệu đã ghi hoặc backfill đã chạy.

## 6. Thông điệp, cache và session cũng đi qua nhiều phiên bản

### Thông điệp cần tương thích với consumer còn tồn tại

Nếu v2 bắt đầu phát một event mà consumer v1 chưa hiểu, lỗi có thể xuất hiện sau khi HTTP rollout đã hoàn tất. Hàng đợi còn giữ event và consumer có thể được rollback độc lập.

Cần kiểm tra cả hai chiều:

~~~text
Producer v1 -> Consumer v2: consumer mới đọc được event cũ.
Producer v2 -> Consumer v1: event mới còn được phát ở dạng v1 hiểu.
~~~

Một cách chuyển đổi là triển khai consumer có khả năng đọc schema cũ và mới trước, sau đó mới cho producer phát schema mới. Nếu không có một dạng payload tương thích, dùng loại event hoặc luồng có phiên bản riêng và kế hoạch chuyển consumer.

Giữ rõ ý nghĩa của trường, đơn vị, định dạng thời gian và giá trị enum. Thêm một giá trị enum mới có thể gây lỗi dù JSON vẫn parse được.

Khi consumer hoặc HTTP handler được thử lại sau khi Pod kết thúc, khóa idempotency phải giữ ổn định cho cùng thao tác nghiệp vụ. Rolling update và graceful shutdown không tự tạo ra bảo đảm xử lý exactly-once.

### Cache và session phải có chính sách đọc/ghi rõ ràng

Ví dụ v2 thay định dạng một giá trị Redis nhưng vẫn ghi vào khóa mà v1 đang đọc. Một request tiếp theo rơi vào v1 có thể thất bại dù không có thay đổi database.

Các lựa chọn có thể gồm:

- Duy trì dạng serialization chung trong cửa sổ cùng tồn tại.
- Thêm phiên bản vào payload và hỗ trợ đọc các dạng còn hiệu lực.
- Dùng namespace khóa riêng khi cache có thể xây dựng lại và chấp nhận được chi phí chuyển tiếp.
- Chuyển session sang cơ chế dùng chung với định dạng tương thích, thay vì giữ trạng thái cần thiết chỉ trong bộ nhớ Pod.

Sticky session có thể làm lỗi ít xuất hiện hơn nhưng không chứng minh tương thích. Pod cũ vẫn sẽ bị thay hoặc kết nối có thể chuyển sang replica khác.

Thời hạn tương thích vì vậy có thể dài hơn thời gian rollout: phải tính client chưa nâng cấp, retention của event, TTL session/cache, credential còn hiệu lực và thời gian cho phép rollback.

## 7. Cấu hình và quyền truy cập là một phần của release

Một release nên được mô tả bằng nhiều thông tin hơn image:

~~~text
Image hoặc digest
+ revision cấu hình
+ schema dữ liệu được hỗ trợ
+ trạng thái feature flag
+ phiên bản credential hoặc tập khóa được chấp nhận.
~~~

### 7.1. Dùng cấu hình ổn định cho từng release

Nếu các Pod v1 và v2 cùng tham chiếu một ConfigMap đang bị sửa, cả hai có thể nhìn thấy cấu hình mới theo thời điểm khác nhau, tùy cách tiêu thụ.

Với biến môi trường lấy từ ConfigMap, cập nhật ConfigMap không tự thay đổi environment của container đang chạy. Với volume thông thường, dữ liệu được chiếu cập nhật theo cơ chế eventual; việc ứng dụng nạp lại giá trị là câu chuyện khác. [Kubernetes ConfigMap: các cách sử dụng](https://kubernetes.io/docs/concepts/configuration/configmap/).

Một phương án dễ truy vết là tạo ConfigMap có tên theo revision, ví dụ `orders-config-r1` và `orders-config-r2`, rồi đổi tham chiếu trong Pod template cùng lúc đổi image. Pod cũ tiếp tục dùng r1, Pod mới dùng r2.

Nếu dùng `immutable: true`, nội dung object không được cập nhật theo cách thông thường. Tạo revision mới thay vì sửa object cũ. Vẫn cần giữ các object cũ trong thời gian mà rollback còn tham chiếu đến chúng.

Đổi nội dung ConfigMap cùng tên không tự tạo revision Deployment mới. Annotation checksum trong Pod template có thể được công cụ triển khai dùng để kích hoạt rollout khi cấu hình thay đổi, nhưng đó phải là hành vi được thiết kế trong công cụ, không phải sự suy luận tự động của Deployment.

### 7.2. Configuration Watcher không phải cơ chế rolling update

Spring Cloud Kubernetes Configuration Watcher có thể gửi yêu cầu refresh hoặc sự kiện Bus để các instance nạp lại cấu hình; nó cũng có chiến lược shutdown tùy cấu hình. [Spring Cloud Kubernetes Configuration Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Refresh nhiều instance không phải một giao dịch đồng thời toàn cụm. Trong lúc refresh, có thể tồn tại cả hai tổ hợp “binary cũ với config mới” và “binary mới với config cũ”.

Nếu một cơ chế bên ngoài gọi shutdown vào nhiều instance, không thể lấy `maxUnavailable` của Deployment rollout làm bảo đảm rằng chỉ một instance bị ảnh hưởng. Giới hạn đó điều khiển quá trình thay replica do Deployment quản lý; nó không bao phủ mọi nguyên nhân ứng dụng dừng hoặc mất readiness.

Chọn rõ một quy trình cho từng loại thay đổi:

| Loại cấu hình | Cách triển khai có thể phù hợp |
| --- | --- |
| Tham số tương thích, đã kiểm chứng hỗ trợ refresh | Refresh có giám sát |
| Thay đổi bắt buộc đi cùng binary | Config revision và image trong cùng Pod template |
| Tính năng chỉ bật sau khi toàn bộ thành phần hỗ trợ | Bật flag sau giai đoạn triển khai khả năng |
| Thay đổi cần restart để có hiệu lực | Rollout có kiểm soát và readiness phù hợp |

Không đồng thời dùng một thay đổi ConfigMap để refresh toàn bộ Pod cũ và triển khai image mới nếu chưa xác định tính hợp lệ của mọi tổ hợp.

### 7.3. Secret rotation cần khoảng chồng lấp

Một Pod cũ có thể vẫn giữ credential cũ trong environment hoặc connection pool. Tạo Secret mới không đồng nghĩa mọi kết nối cũ đã đổi credential.

Trình tự thường cần có khoảng thời gian hệ thống đích chấp nhận cả credential cũ và mới, chuyển các instance sang credential mới, xác nhận sử dụng rồi mới thu hồi credential cũ. Với token hoặc chữ ký, còn phải xét token đã phát trước đó và thời hạn của chúng.

Kubernetes có các quy tắc cập nhật Secret theo cách sử dụng: volume, environment hoặc truy cập API. Không suy ra tất cả cách này có cùng hành vi cập nhật. [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Trong log release, chỉ ghi định danh revision hoặc phiên bản khóa; không ghi giá trị Secret.

### 7.4. Cấp quyền cần thiết trước khi Pod mới dùng đến

Ví dụ bản client mới chuyển từ Endpoints sang EndpointSlices. ServiceAccount của client phải có quyền đọc tài nguyên API mới trước khi triển khai client đó; quyền cũ còn cần được duy trì trong cửa sổ mà Pod cũ sử dụng nó.

Spring Cloud Kubernetes có tùy chọn sử dụng EndpointSlices và yêu cầu RBAC tương ứng cho tài nguyên `endpointslices` thuộc nhóm `discovery.k8s.io`. [DiscoveryClient 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

Đây là thay đổi quyền có tính mở rộng trước, thu hẹp sau. Server chỉ phục vụ HTTP và được kubelet probe không cần quyền đọc Kubernetes API chỉ để tham gia rollout.

## 8. Ứng dụng mẫu quan sát hợp đồng v1 và v2

Dự án mẫu cần `spring-boot-starter-web` và `spring-boot-starter-actuator`, với phiên bản do parent/BOM Spring Boot tương thích quản lý.

Các tên tệp và image trong phần thực hành là hướng dẫn chuẩn bị dự án mẫu. Chúng không đại diện cho image đã được build sẵn. Thay image ví dụ bằng artifact thực tế của môi trường thực hành và giữ chúng ổn định bằng tag không đổi nội dung hoặc digest đã xác minh.

### 8.1. Mã Java

Ứng dụng chính:

~~~java
package example.rollout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Controller minh họa dùng cấu hình release để biểu diễn phần phản hồi bổ sung:

~~~java
package example.rollout;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final String release;
    private final String podName;
    private final boolean currencyEnabled;

    public OrderController(
            @Value("${release.version:local}") String release,
            @Value("${POD_NAME:local}") String podName,
            @Value("${release.currency:false}") boolean currencyEnabled) {
        this.release = release;
        this.podName = podName;
        this.currencyEnabled = currencyEnabled;
    }

    @GetMapping("/api/orders/{id}")
    public ResponseEntity<Map<String, Object>> getOrder(
            @PathVariable("id") String id) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("orderId", id);
        body.put("amount", new BigDecimal("150000.00"));
        body.put("status", "CREATED");

        if (currencyEnabled) {
            body.put("currency", "VND");
        }

        return ResponseEntity.ok()
                .header("X-App-Version", release)
                .header("X-Pod-Name", podName)
                .body(body);
    }
}
~~~

Đặt hai lớp trong hai tệp Java riêng cùng package `example.rollout`. Phản hồi là dữ liệu mẫu cố định; nó giúp kiểm chứng đường định tuyến và hợp đồng JSON, chưa triển khai đọc/ghi đơn hàng thật.

Hai image thực hành có thể dùng khung controller này, còn release revision quyết định có phát trường `currency` không. Trong dự án thật, cần chạy ma trận hợp đồng với chính binary v1 và v2, vì mã của chúng có thể khác nhiều hơn phần minh họa.

Cấu hình `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

Graceful shutdown cho web server có thời gian hoàn tất các request đang xử lý khi application context đóng. Cách từ chối request mới phụ thuộc web server và việc dùng kết nối lâu dài. `timeout-per-shutdown-phase` là timeout theo phase, không phải thời gian đóng tối đa cho mọi thành phần cộng lại. [Spring Boot 3.5: graceful shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html).

Image cần chuyển tín hiệu dừng đến tiến trình Java đúng cách, chẳng hạn chạy Java bằng exec-form entrypoint thay vì giữ một shell không chuyển tiếp tín hiệu.

### 8.2. Manifest triển khai ban đầu

Ví dụ `orders-v1.yaml`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rollout-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config-r1
  namespace: rollout-lab
immutable: true
data:
  RELEASE_VERSION: "v1"
  RELEASE_CURRENCY: "false"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config-r2
  namespace: rollout-lab
immutable: true
data:
  RELEASE_VERSION: "v2"
  RELEASE_CURRENCY: "true"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: rollout-lab
spec:
  replicas: 3
  revisionHistoryLimit: 5
  minReadySeconds: 10
  progressDeadlineSeconds: 300
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
        release: v1
    spec:
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example/order-service:1.0.0
          envFrom:
            - configMapRef:
                name: orders-config-r1
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 45
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: order-service
  namespace: rollout-lab
spec:
  type: ClusterIP
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Service chọn `app: order-service`, nên cả release v1 và v2 đều có thể phục vụ. Nhãn `release` dùng để quan sát, không nằm trong selector cố định của Deployment.

Các resource request/limit là giá trị lab để bắt đầu quan sát, cần đo lại theo ứng dụng. Cụm còn phải đủ chỗ cho surge và các Pod cũ đang kết thúc.

`terminationGracePeriodSeconds: 45` tạo ngân sách kết thúc cho Pod. Nếu dùng preStop, thời gian hook cũng nằm trong ngân sách đó; còn phải tính các phase dừng và xử lý nền. Khi ngân sách hết, tiến trình chưa dừng có thể bị kết thúc cưỡng bức. [Kubernetes: trình tự kết thúc Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow).

Mẫu không thêm thời gian sleep cố định vào preStop. Trong triển khai thật, việc cập nhật endpoint và dừng web server diễn ra qua các đường điều phối có độ trễ; cần kiểm chứng drain và kết nối thực tế thay vì xem một con số sleep là bảo đảm không mất request.

## 9. Thực hành rollout và quan sát hai phiên bản

Các lệnh sau dành cho namespace lab sau khi đã chuẩn bị các image và tệp minh họa. Đây là quy trình để người học thực hiện, không phải kết quả của một lần chạy đã có sẵn.

### 9.1. Đưa v1 về trạng thái nền ổn định

~~~powershell
kubectl apply -f orders-v1.yaml
kubectl rollout status deployment/order-service -n rollout-lab --timeout=360s
kubectl rollout history deployment/order-service -n rollout-lab
~~~

Ghi lại revision, image và ConfigMap tương ứng với bản nền đã kiểm chứng. Revision số 1 chỉ đúng khi đây thực sự là rollout đầu của Deployment trong lab.

Mở các cửa sổ quan sát:

~~~powershell
kubectl get pods -n rollout-lab -l app=order-service -L release,pod-template-hash -w
~~~

~~~powershell
kubectl get replicasets -n rollout-lab -l app=order-service -w
~~~

Có thể đọc trạng thái endpoint khi cần:

~~~powershell
kubectl get endpointslices -n rollout-lab -l kubernetes.io/service-name=order-service -o yaml
~~~

### 9.2. Gọi qua Service từ trong cụm

Mở một Pod công cụ có curl. Ví dụ dùng image `curlimages/curl`; có thể thay bằng image công cụ được registry lab cung cấp:

~~~powershell
kubectl run rollout-caller -n rollout-lab --image=curlimages/curl --restart=Never --rm -it --command -- sh
~~~

Trong shell của Pod công cụ, thực hiện nhiều lần:

~~~sh
curl -i --http1.1 -H 'Connection: close' --max-time 3 http://order-service/api/orders/O-1001
~~~

Ghi lại `X-App-Version`, `X-Pod-Name`, mã HTTP và nội dung JSON. Mỗi lần gọi mới giúp giảm việc phép thử chỉ bám một kết nối đã tồn tại.

Khi đang ở v1, ba trường `orderId`, `amount`, `status` phải có ý nghĩa đã định. Với hệ thống thật, sử dụng chính client hoặc bộ kiểm thử hợp đồng cần duy trì để xác nhận, thay vì chỉ nhìn JSON trong terminal.

### 9.3. Đổi image và config reference trong một lần cập nhật

Chuẩn bị tệp `orders-v2.patch.json`:

~~~json
{
  "spec": {
    "template": {
      "metadata": {
        "labels": {
          "release": "v2"
        }
      },
      "spec": {
        "containers": [
          {
            "name": "app",
            "image": "example/order-service:1.1.0",
            "envFrom": [
              {
                "configMapRef": {
                  "name": "orders-config-r2"
                }
              }
            ]
          }
        ]
      }
    }
  }
}
~~~

Sau khi thay image bằng artifact thực tế, áp dụng:

~~~powershell
kubectl patch deployment order-service -n rollout-lab --type=strategic --patch-file orders-v2.patch.json
kubectl rollout status deployment/order-service -n rollout-lab --timeout=360s
~~~

Strategic merge cập nhật container theo tên `app`, giữ các trường không bị thay như probe, port và tài nguyên; danh sách `envFrom` của ví dụ được đổi sang ConfigMap r2.

Ghép hai thay đổi trong một lần cập nhật tránh vô tình tạo một revision trung gian “image mới nhưng cấu hình cũ” chỉ do thao tác triển khai tách rời. Dù vậy, vẫn phải kiểm chứng mọi tổ hợp có thể xảy ra do refresh hoặc những nguồn cấu hình khác nếu hệ thống có dùng chúng.

Trong môi trường GitOps, cập nhật nguồn khai báo tương ứng để bộ điều phối không đưa Deployment về template cũ. Các lệnh patch ở đây phục vụ bài lab trực tiếp.

### 9.4. Điều cần thấy trong lúc rollout

Khi tiếp tục gọi qua Service:

- Có giai đoạn endpoint của cả v1 và v2 cùng đủ điều kiện phục vụ.
- `X-App-Version` và tên Pod giúp nhận biết request đến phiên bản nào.
- Cả hai phản hồi đều còn `orderId`, `amount`, `status` với cùng kiểu và ý nghĩa.
- Phản hồi v2 bổ sung `currency`; client ở chế độ chuyển tiếp phải chấp nhận cả hai dạng.
- ReplicaSet mới tăng dần, ReplicaSet cũ giảm dần.
- Pod cũ cần dừng có kiểm soát; không chỉ đo tổng số Pod Ready.

Không yêu cầu response luân phiên v1/v2, cũng không suy ra `maxSurge: 1` tương đương một tỷ lệ phần trăm lưu lượng cố định. RollingUpdate kiểm soát replica, không cung cấp cơ chế cân trọng số request.

Sau khi rollout hoàn tất, tiếp tục quan sát nghiệp vụ trong một khoảng phù hợp. Kết quả `rollout status` thành công cho biết tiến độ Deployment, không thay thế kiểm chứng dữ liệu và hành vi.

## 10. Kiểm chứng tương thích trước khi cho phép phát hành đầy đủ

Bài thực hành HTTP chỉ minh họa một phần nhỏ của release. Một bộ kiểm chứng có ý nghĩa cần tập trung vào ranh giới giữa các phiên bản.

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Client v1 gọi server v2 | Deserialize được và giữ đúng hành vi đã hỗ trợ |
| Client v2 chuyển tiếp gọi server v1 | Xử lý trường thiếu hợp lệ; không dùng tính năng chỉ v2 có |
| V1 ghi, v2 đọc | Bản mới hiểu dữ liệu được tạo theo hợp đồng cũ |
| V2 ghi, v1 đọc | Bản cũ không lỗi với dữ liệu mới được tạo trong cửa sổ hỗ trợ |
| Hai phiên bản cùng cập nhật | Không để hai nguồn dữ liệu lệch nhau hoặc mất cập nhật |
| Producer mới, consumer cũ | Không phát schema mà consumer đang sống chưa hiểu |
| Consumer mới đọc backlog cũ | Event cũ còn được xử lý theo nghĩa đúng |
| Rollback sau khi v2 đã ghi | Binary cũ chạy được với trạng thái hiện tại |
| Một Pod bị kết thúc khi đang xử lý | Retry và checkpoint không tạo hiệu ứng trùng ngoài dự kiến |
| Pod dùng config cũ và mới cùng tồn tại | Mọi tổ hợp được cho phép đều có nghĩa rõ ràng |

Nên dùng fixture dữ liệu và client thực tế từ bản cũ. Một test mới viết lại theo cách hiểu của bản mới có thể bỏ qua chính giới hạn của bản cũ.

Với v2 thêm `currency`, ngoài trường hợp VND cần kiểm tra điều gì xảy ra khi xuất hiện loại tiền khác. Nếu v1 chỉ có thể hiểu VND, không bật tạo đơn khác tiền tệ khi v1 còn được phép đọc các đơn đó. Cấu trúc JSON không đổi không có nghĩa ý nghĩa dữ liệu vẫn tương thích.

### Quan sát theo phiên bản

Các tín hiệu hữu ích gồm:

- Tỷ lệ lỗi HTTP, timeout và lỗi parse theo release.
- Độ trễ p95/p99, số request và kết nối đang xử lý.
- Lỗi constraint, lỗi đọc schema hoặc sai lệch dữ liệu.
- Consumer lag, retry, dead-letter và lỗi đọc event.
- Restart, readiness dao động và thời gian khởi động.
- Số thao tác bị loại do idempotency hoặc được phục hồi từ checkpoint.

Ghi image/release và config revision để liên hệ thay đổi với triệu chứng. Tổng error rate có thể che khuất một v2 mới chỉ nhận ít request; cần xem đúng nhóm phiên bản.

Lỗi nghiệp vụ có thể không trả 5xx. Ví dụ amount vẫn là số nhưng bị hiểu sai đơn vị sẽ qua health check và nhiều metric HTTP thông thường.

## 11. Rollback là một lần chuyển đổi khác

Rollback cũng tạo giai đoạn cùng tồn tại. Khi đưa v1 trở lại, các Pod v2 có thể còn đang phục vụ hoặc hoàn tất phần việc; dữ liệu mới đã tồn tại và thông điệp có thể còn trong hàng đợi.

Trước khi rollback, cần trả lời:

1. Revision nào đã được kiểm chứng tốt?
2. Image và ConfigMap/Secret mà revision đó tham chiếu còn tồn tại không?
3. Schema hiện tại có còn hỗ trợ bản đó không?
4. Dữ liệu và event v2 đã tạo có được bản đó hiểu không?
5. Feature flag hoặc credential mới có cần điều chỉnh theo kế hoạch phục hồi không?

### Thực hành khôi phục Pod template đã biết

Xem lịch sử:

~~~powershell
kubectl rollout history deployment/order-service -n rollout-lab
~~~

Chọn revision nền thực sự phù hợp; trong lab mới tạo, đó có thể là 1:

~~~powershell
$goodRevision = 1
kubectl rollout history deployment/order-service -n rollout-lab --revision=$goodRevision
~~~

Sau khi kiểm tra đúng template, thực hiện:

~~~powershell
kubectl rollout undo deployment/order-service -n rollout-lab --to-revision=$goodRevision
kubectl rollout status deployment/order-service -n rollout-lab --timeout=360s
~~~

Trong mẫu, template r1 có cả image v1 và tham chiếu `orders-config-r1`. Vì ConfigMap r1 vẫn được giữ nguyên, Pod quay lại dùng đúng cấu hình đó. Nếu chỉ giữ lịch sử Deployment nhưng xóa ConfigMap r1 hoặc thay nội dung cùng tên, khả năng phục hồi không còn tương đương.

Revision Deployment được lưu qua ReplicaSet được giữ trong lịch sử. `revisionHistoryLimit` cần phù hợp với kế hoạch rollback và việc lưu artifact. [Deployment: revision history](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#revision-history-limit).

### Khi rollout đang bị pause

Có thể pause để điều tra hoặc gom thay đổi, nhưng pause không biến các Pod v2 đã khỏe thành endpoint bị loại và không hoàn tác dữ liệu chúng đã ghi.

Kubernetes không cho rollback Deployment đang pause cho đến khi resume. Nếu đang ở trạng thái này, lên kế hoạch sửa template hoặc resume rồi thực hiện rollback phù hợp; không xem pause là cách cách ly lưu lượng tự động. [Deployment: pause và resume](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#pausing-and-resuming-a-rollout-of-a-deployment).

### Khi rollback binary không còn an toàn

Ví dụ đã xóa cột mà v1 cần, hoặc v2 đã ghi trạng thái enum v1 không hiểu. Lúc này, lệnh undo thành công về mặt điều khiển vẫn có thể đưa lỗi cũ trở lại.

Các hướng phục hồi có thể là tắt phần tính năng gây lỗi, sửa tiến bằng một bản tương thích, khôi phục hỗ trợ schema hoặc thực hiện quy trình dữ liệu đã được chuẩn bị. Không tự coi việc chạy migration ngược là an toàn, nhất là khi nó có thể làm mất dữ liệu hợp lệ đã phát sinh.

Chỉ kết thúc cửa sổ rollback của một bản khi đã biết rõ từ thời điểm nào code đó không còn được phép chạy.

## 12. Liên hệ DiscoveryClient và Spring Cloud LoadBalancer

Trong rollout, một Service name ổn định thường trỏ đến endpoint của cả Pod cũ và mới còn Ready. DiscoveryClient khám phá instance không tự chứng minh các instance có cùng hợp đồng nghiệp vụ.

Nếu Spring Cloud LoadBalancer chọn Pod trực tiếp, cache danh sách instance và connection pool có thể làm một client tiếp tục sử dụng thông tin cũ trong một khoảng thời gian. Nếu gọi qua Service, cơ chế mạng của cụm quản lý backend. Cả hai đường đều cần ứng dụng chịu được thời gian chuyển tiếp.

Các nguyên tắc áp dụng:

- Dùng readiness để không đưa Pod khởi tạo dở vào tập đích thông thường.
- Không bật lấy địa chỉ chưa ready cho client nghiệp vụ chỉ để nhìn thấy Pod mới sớm hơn.
- Giữ Service và namespace đúng phạm vi mong muốn, tránh trộn nhầm các nhóm ứng dụng.
- Nếu dùng nhãn version để định tuyến, phải có bộ lọc hoặc Service/route thực sự sử dụng nhãn đó.
- Duy trì quyền RBAC phù hợp với client ở cả hai phiên bản trong thời gian chuyển đổi.

Một Service v2 riêng có selector `release: v2` có thể tạo đường gọi riêng cho API mới. Nhưng nếu nó cùng dùng database, event hoặc cache với v1, vẫn phải giải quyết tương thích trạng thái.

Khi cần điều chỉnh tỷ lệ lưu lượng, đánh giá canary hoặc routing có trọng số theo cơ chế triển khai đang dùng. Không lấy số lượng surge làm thay thế cho kiểm soát lưu lượng.

## 13. Chẩn đoán lỗi rollout theo triệu chứng

| Hiện tượng | Khả năng cần kiểm tra | Hướng điều tra |
| --- | --- | --- |
| Pod mới Pending, Pod cũ còn đủ | Thiếu tài nguyên surge, quota hoặc ràng buộc scheduling | Events, request/limit, quota và capacity |
| Pod mới Running nhưng không available | Readiness, startup hoặc minReadySeconds | Kết quả probe, log khởi tạo, điều kiện Deployment |
| Rollout hoàn tất nhưng một nhóm client lỗi | Hợp đồng response/request bị đổi | Client version, strict schema, enum và kiểu dữ liệu |
| Lỗi database chỉ xảy ra ở v1 | Migration đã phá schema cũ | Cột, ràng buộc, truy vấn của binary cũ |
| Dữ liệu lúc đúng lúc sai tùy Pod | Hai nguồn dữ liệu hoặc quy tắc nghiệp vụ không đồng nhất | Writer cũ, dual write và nguồn đọc chính |
| Config revision không đi cùng image | Cập nhật template tách rời hoặc refresh ngoài kế hoạch | Pod spec, env source, watcher và nguồn khai báo |
| V2 khỏe nhưng v1 mất quyền truy cập phụ thuộc | Credential cũ bị thu hồi hoặc RBAC thu hẹp sớm | Tập credential được chấp nhận và quyền của từng client |
| HTTP ổn nhưng consumer lag tăng | Event mới chưa được consumer hỗ trợ | Producer/consumer schema, retry và backlog |
| Undo xong nhưng hệ thống vẫn lỗi | Trạng thái dùng chung đã vượt khả năng của bản cũ | Schema, dữ liệu, config, key và event đã phát |

Một release có thể được xem là sẵn sàng tiếp tục khi bản mới phục vụ đúng hợp đồng ở trạng thái cùng tồn tại, các tín hiệu theo phiên bản ổn định và đường phục hồi đã được kiểm chứng với trạng thái thật sau chuyển đổi. Việc gỡ trường API, cột dữ liệu, quyền cũ hoặc credential cũ nên là bước riêng sau khi các thành phần còn phụ thuộc đã hết cửa sổ hỗ trợ.
