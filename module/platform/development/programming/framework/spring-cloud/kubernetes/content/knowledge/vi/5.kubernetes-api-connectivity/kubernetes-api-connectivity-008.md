# Timeout kết nối, timeout đọc và hành vi khi API server gián đoạn

## 1. Vì sao timeout Kubernetes API cần được thiết kế riêng?

Ứng dụng Spring Cloud Kubernetes có thể gọi Kubernetes API để discovery, đọc ConfigMap hoặc Secret, và theo dõi thay đổi bằng watch. Đường gọi này khác với đường HTTP nghiệp vụ giữa checkout và orders. Khi kube-apiserver chậm hoặc tạm thời không truy cập được, ứng dụng cần phân biệt đúng loại timeout để chọn hành vi phù hợp.

Ba khái niệm thường bị trộn lẫn:

- **Connect timeout**: thời gian tối đa để thiết lập kết nối đến endpoint API.
- **Read timeout**: thời gian chờ dữ liệu hoặc response sau khi kết nối đã thiết lập.
- **Request timeout hoặc deadline**: giới hạn tổng thời gian cho một thao tác từ lúc bắt đầu đến lúc hoàn tất.

Một watch còn có vòng đời khác: connection có thể giữ lâu để chờ sự kiện, bị đóng định kỳ hoặc bị ngắt khi API server, proxy và load balancer đặt giới hạn. Client phải reconnect với backoff và giữ trạng thái nhất quán.

Timeout không làm API server nhanh hơn. Timeout chỉ giới hạn thời gian ứng dụng chờ và bảo vệ thread, connection pool cùng startup. Giá trị quá ngắn gây false failure; giá trị quá dài làm request treo, cạn tài nguyên và che giấu sự cố.

## 2. Bốn đường gọi cần tách

~~~text
Spring application
   |
   +--> Kubernetes API: discovery, ConfigMap, Secret, watch
   |
   +--> API nghiệp vụ: orders, catalog, payment
   |
   +--> DNS resolver
   |
   +--> Metrics/logging backend
~~~

Mỗi đường có thể có endpoint, certificate, authentication, timeout và retry riêng. Không lấy timeout của API nghiệp vụ để áp dụng mù quáng cho Kubernetes API.

Ví dụ:

| Đường gọi | Mục tiêu | Hậu quả khi timeout |
| --- | --- | --- |
| Kubernetes API get ConfigMap | Đọc cấu hình | Dùng cache, giữ giá trị cũ hoặc fail startup |
| Kubernetes API list Service | Khởi tạo discovery | Không có danh sách instance mới |
| Kubernetes API watch | Nhận thay đổi | Reconnect và resync |
| orders HTTP request | Xử lý nghiệp vụ | Trả lỗi, retry có điều kiện |
| DNS lookup | Tìm địa chỉ | Không tạo được kết nối mới |
| Health probe | Cho cluster biết trạng thái | Pod có thể NotReady hoặc restart tùy probe |

Một API server gián đoạn không nhất thiết làm API nghiệp vụ orders gián đoạn. Ngược lại, orders có thể hoạt động trong khi Configuration Watcher không nhận được thay đổi mới. Metric và log cần tách nhãn theo endpoint hoặc client.

## 3. Connect timeout

### 3.1. Connect timeout là gì?

Connect timeout giới hạn giai đoạn client cố thiết lập kết nối đến Kubernetes API. Các nguyên nhân có thể gồm:

- DNS endpoint API không phân giải được;
- route hoặc NetworkPolicy chặn;
- API server không lắng nghe;
- proxy hoặc load balancer không phản hồi;
- TLS handshake không hoàn tất trong thời gian cho phép;
- connection pool không có kết nối sẵn và việc mở connection bị chậm.

Khi connect timeout xảy ra, client chưa có response API. Không nên suy ra resource không tồn tại hoặc RBAC bị từ chối. Cần phân biệt lỗi mạng, lỗi TLS và lỗi HTTP status.

### 3.2. Connect timeout quá ngắn

Nếu timeout thấp hơn độ trễ bình thường của cluster, ứng dụng có thể:

- fail startup dù API server khỏe;
- reconnect watch quá nhanh;
- tạo log dày;
- tăng số lần retry;
- làm API server chịu thêm tải;
- đánh dấu cấu hình cũ là lỗi dù chỉ là mạng chậm.

Connect timeout nên phản ánh mạng thực tế, nhưng vẫn phải có giới hạn để thread không chờ vô hạn.

### 3.3. Connect timeout quá dài

Nếu endpoint bị blackhole, mỗi request có thể chiếm connection và thread trong thời gian dài. Khi discovery, config và watcher cùng chờ, connection pool có thể cạn. Request nghiệp vụ không dùng Kubernetes API cũng có thể bị ảnh hưởng nếu chúng dùng chung executor hoặc pool.

Thiết kế cần giới hạn cả connect timeout lẫn pool acquisition timeout nếu HTTP client hỗ trợ. Không chỉ đặt một timeout ở tầng business rồi giả định mọi lớp bên dưới được bảo vệ.

## 4. Read timeout

### 4.1. Read timeout là gì?

Read timeout giới hạn thời gian client chờ dữ liệu sau khi kết nối đã được thiết lập. API server có thể nhận request nhưng xử lý chậm, proxy giữ connection, hoặc response bị gián đoạn giữa chừng.

Read timeout khác connect timeout:

- connect timeout xảy ra trước khi có connection;
- read timeout xảy ra sau khi connection tồn tại;
- lỗi HTTP 403 hoặc 404 là response hợp lệ, không phải read timeout;
- response rỗng hoặc stream bị đóng có thể là lỗi khác tùy client.

Một request list ConfigMap có thể cần response nhanh. Một watch có thể cố ý chờ lâu để nhận event, nên không thể áp dụng read timeout ngắn như request get thông thường mà không hiểu cơ chế reconnect.

### 4.2. Read timeout với API thông thường

Với get hoặc list resource, read timeout bảo vệ client khỏi API server xử lý quá lâu. Khi timeout, ứng dụng nên coi kết quả là chưa xác định:

- không kết luận resource đã thay đổi;
- không ghi trạng thái mới một cách mù quáng;
- dùng cache còn hợp lệ hoặc retry;
- đặt giới hạn tổng thời gian;
- phát metric để người vận hành thấy độ trễ.

Nếu request là thao tác đọc, retry thường an toàn hơn ghi. Tuy vậy, retry vẫn cần backoff và jitter; retry liên tục có thể làm sự cố nặng hơn.

### 4.3. Read timeout với watch

Watch không giống một request trả response ngay. Server giữ connection để gửi event. Một client có thể đặt read timeout đủ dài hoặc dùng cơ chế heartbeat, socket timeout và reconnect theo library.

Không nên:

- coi việc watch không có event trong vài giây là lỗi dữ liệu;
- restart toàn bộ ứng dụng chỉ vì watch connection bị đóng;
- retry không backoff;
- bỏ qua resource version khi tạo watch mới.

Khi watch bị ngắt, client thường cần list hoặc resync rồi tạo watch từ resource version phù hợp. Cách xử lý cụ thể phụ thuộc Kubernetes client library.

## 5. Request deadline và timeout tầng trên

Một request có thể đi qua nhiều lớp:

~~~text
Application deadline
       |
       +-- retry budget
              |
              +-- connection pool wait
                     |
                     +-- connect timeout
                            |
                            +-- TLS handshake
                                   |
                                   +-- read timeout
~~~

Nếu mỗi lớp tự đặt timeout mà không có ngân sách tổng, tổng thời gian có thể vượt quá thời gian caller chấp nhận. Ví dụ ba lần retry, mỗi lần read 10 giây, có thể biến một thao tác tưởng là timeout 10 giây thành hơn 30 giây.

Nên định nghĩa:

- deadline của thao tác startup;
- deadline của một lần gọi API;
- tổng retry budget;
- timeout connect;
- timeout read;
- thời gian backoff;
- thời gian cache được phép cũ.

Khi deadline tầng trên hết hạn, dừng retry dù từng attempt vẫn còn timeout riêng.

## 6. API server gián đoạn theo từng kiểu

### 6.1. DNS hoặc route API hỏng

Client không thể tìm hoặc kết nối endpoint. Thường thấy UnknownHost, connection refused hoặc connect timeout. Kiểm tra DNS của Pod, biến endpoint, route và NetworkPolicy.

### 6.2. TLS hoặc CA lỗi

Connection có thể được mở nhưng handshake thất bại. Thấy lỗi certificate, trust anchor hoặc hostname verification. Không tắt kiểm tra TLS để chữa lỗi tạm thời trong production. Kiểm tra CA bundle, endpoint và cách client được cấu hình.

### 6.3. API server trả 401

Token thiếu, hết hạn, sai audience hoặc identity không được authentication. Retry ngay với cùng token thường không sửa được. Cần refresh credential hoặc sửa cấu hình identity.

### 6.4. API server trả 403

Request đã đến API server và identity đã được nhận diện, nhưng RBAC không cho phép verb, resource hoặc namespace. Retry không thay đổi policy. Cần kiểm tra Role, ClusterRole, Binding và ServiceAccount.

### 6.5. API server trả 429 hoặc 5xx

Có thể API server throttling, quá tải hoặc lỗi tạm thời. Retry cần backoff, jitter và giới hạn. Đồng thời phải giảm polling, giữ watch đúng cách và tránh tạo nhiều client hoặc reconnect đồng thời.

### 6.6. Connection bị đóng giữa watch

Đây là sự kiện có thể xảy ra bình thường trong vòng đời watch. Client cần reconnect và resync theo library. Ứng dụng nên duy trì giá trị hoặc danh sách gần nhất trong thời gian ngắn thay vì coi mọi lần đóng connection là fatal.

## 7. Hành vi startup và runtime

### 7.1. Startup bắt buộc phải có Kubernetes API

Nếu ứng dụng cần ConfigMap bắt buộc để tạo bean cốt lõi, có thể chọn fail startup khi không đọc được. Ưu điểm là Pod không chạy với cấu hình không xác định. Nhược điểm là API gián đoạn làm rollout thất bại.

Cần tránh vòng lặp:

1. Pod khởi động.
2. API timeout.
3. Container exit.
4. Controller tạo Pod mới.
5. Tất cả Pod lặp lại request cùng lúc.

Giảm rủi ro bằng startup timeout có giới hạn, backoff, jitter và rollout strategy phù hợp. Readiness có thể giữ Pod ngoài traffic trong thời gian chờ nếu process vẫn an toàn để chạy.

### 7.2. Runtime discovery

Nếu API server tạm thời gián đoạn sau khi discovery đã có danh sách, có thể giữ cache trong một khoảng thời gian. Nhưng cache phải có tuổi tối đa. Instance đã bị xóa hoặc NotReady không nên được dùng vô hạn.

Một policy cần ghi rõ:

~~~text
API lỗi dưới 30 giây:
  dùng danh sách discovery gần nhất, phát cảnh báo.
API lỗi lâu hơn:
  hạn chế request mới hoặc dùng Service fallback.
Không có danh sách ban đầu:
  không khởi tạo client hoặc trả lỗi rõ ràng.
~~~

Con số chỉ là ví dụ. Giá trị thực tế phụ thuộc tính an toàn của API và độ nhạy của dữ liệu.

### 7.3. Runtime configuration

Nếu ConfigMap thay đổi mà watcher mất kết nối, ứng dụng có thể giữ giá trị cũ. Đây là behavior cần thiết kế, không phải lỗi nếu giá trị cũ vẫn an toàn.

Cần xác định:

- giá trị cũ được giữ tối đa bao lâu;
- cấu hình hết hạn có làm readiness fail không;
- cấu hình mới sai có bị từ chối không;
- API trở lại thì có resync không;
- metric nào cho biết config đang cũ.

Không dùng liveness để báo mọi lỗi cấu hình. Restart chỉ phù hợp khi process không thể tự phục hồi hoặc policy yêu cầu khởi động lại.

## 8. Retry, backoff và jitter

Retry không phải câu trả lời cho mọi timeout. Trước khi retry, phân loại lỗi:

| Lỗi | Retry tự động? | Ghi chú |
| --- | --- | --- |
| Connect timeout tạm thời | Có thể | Backoff, jitter và giới hạn |
| Read timeout khi list/get | Có thể | Kiểm tra request đọc và deadline |
| Watch bị đóng | Có | Reconnect và resync |
| 401 | Không lặp mù | Refresh identity hoặc sửa token |
| 403 | Không | Sửa RBAC, retry không đổi policy |
| 404 resource không tồn tại | Thường không | Xác minh tên, namespace và lifecycle |
| 429 | Có kiểm soát | Tôn trọng throttling và backoff |
| 5xx | Có thể | Giới hạn tải và quan sát API server |
| TLS certificate lỗi | Không lặp mù | Sửa CA hoặc endpoint |

Backoff tăng dần giúp client không dồn request vào API server đang lỗi. Jitter tránh việc nhiều Pod cùng retry tại một thời điểm sau rollout hoặc outage.

Không tạo một vòng retry bên trong client, một vòng ở integration và một vòng ở business service mà không tính tổng ngân sách. Nhiều lớp retry có thể nhân số request.

## 9. Watch và reconnect

Một watcher thường có chuỗi:

~~~text
List trạng thái ban đầu
        |
        v
Tạo watch từ resource version
        |
        v
Nhận event hoặc bị đóng connection
        |
        +--> event hợp lệ: cập nhật cache
        |
        +--> đóng bình thường: reconnect
        |
        +--> resource version không còn hợp lệ: resync list
~~~

Khi resync, cần xử lý khoảng thời gian giữa list và watch theo behavior của client library. Không tự viết watcher đơn giản bằng một vòng GET liên tục nếu thư viện đã có watch và backoff.

Watcher cần có:

- metric số lần reconnect;
- thời gian từ event đến lúc ứng dụng áp dụng;
- trạng thái cache hiện tại;
- tuổi của dữ liệu cuối;
- log không chứa Secret;
- giới hạn số client và connection.

Nếu chỉ cần cấu hình lúc startup, không cần mở watch liên tục. Rollout có thể là cách giảm trạng thái và đơn giản hóa failure mode.

## 10. Thiết kế timeout trong Spring integration

Tên property phụ thuộc starter, HTTP client và version dependency. Vì vậy, không nên chép một key cấu hình không kiểm chứng rồi coi là áp dụng. Hãy xác định client nào thực sự gửi request đến Kubernetes API:

- Java Kubernetes client;
- Spring Cloud Kubernetes integration;
- WebClient hoặc RestClient tùy chỉnh;
- HTTP client được framework bọc phía dưới.

Sau đó cấu hình timeout ở đúng lớp. Một mô hình cấu hình khái niệm:

~~~yaml
kubernetes:
  api:
    connect-timeout: 2s
    read-timeout: 5s
    request-deadline: 10s
    retry:
      max-attempts: 4
      initial-backoff: 200ms
      max-backoff: 5s
~~~

Các key trên chỉ minh họa cấu trúc, không phải tên property bảo đảm cho mọi starter. Trong dự án thật, đọc tài liệu của dependency đang dùng và kiểm tra log client đã nhận cấu hình.

Nếu Spring application dùng RestClient để gọi API nghiệp vụ, timeout đó không tự điều khiển Kubernetes API client bên trong Spring Cloud Kubernetes. Có thể cần cấu hình hai client riêng.

## 11. Pool, thread và request đồng thời

Timeout chỉ hiệu quả khi client còn tài nguyên để tạo request. Cần quan sát:

- số connection đang dùng;
- số request chờ connection pool;
- số thread chờ response;
- số watcher connection;
- thời gian DNS và TLS;
- số retry đang chạy.

Nếu API server gián đoạn, mọi Pod cùng reconnect có thể tạo thundering herd. Giới hạn số connection, dùng singleton client, backoff và jitter. Không tạo client Kubernetes mới cho mỗi request discovery hoặc config.

Một watcher nên dùng connection dài hạn có kiểm soát, còn get/list nên dùng client pool phù hợp. Tách executor của watcher khỏi executor xử lý HTTP nghiệp vụ nếu failure của API server không được phép chặn traffic chính.

## 12. Readiness, liveness và API timeout

Có thể dùng readiness để báo ứng dụng chưa có cấu hình bắt buộc hoặc discovery chưa sẵn sàng, nhưng cần thận trọng:

- readiness fail làm Pod rời endpoint;
- liveness fail có thể restart container;
- startup fail có thể làm container restart;
- timeout API ngắn không nhất thiết là process hỏng.

Nếu kube-apiserver tạm thời lỗi nhưng checkout vẫn có thể phục vụ từ cache an toàn, không nên làm liveness fail. Nếu ứng dụng không thể xử lý request nào khi thiếu config, readiness có thể phù hợp hơn. Nếu cấu hình bắt buộc chỉ được đọc lúc startup, fail startup có thể là policy rõ ràng.

Health endpoint nên phân biệt “API Kubernetes đang chậm” với “process deadlock”. Không gộp mọi dependency vào liveness.

## 13. Quan sát và chẩn đoán

Metric nên tách ít nhất:

- request count đến Kubernetes API;
- connect latency;
- TLS latency;
- time to first byte;
- read timeout count;
- 401, 403, 404, 429 và 5xx;
- watch reconnect count;
- cache age;
- retry count;
- số request đang chờ pool.

Log nên có:

- operation: get, list hoặc watch;
- resource và namespace, không ghi token;
- attempt và tổng deadline;
- loại lỗi;
- cache fallback;
- resource version nếu không chứa dữ liệu nhạy cảm;
- thời điểm reconnect.

Bảng chẩn đoán:

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| Startup timeout | Endpoint, CA, ServiceAccount, API availability và deadline |
| 403 ngay lập tức | Role, Binding, resource, verb và namespace |
| Watch ngắt liên tục | Proxy, API load, timeout, resource version và reconnect |
| Retry tăng mạnh | Backoff, jitter, nhiều client hoặc thundering herd |
| Cache quá cũ | Watcher state, resync và policy hết hạn |
| HTTP nghiệp vụ chậm theo API | Dùng chung pool hoặc executor, integration chặn thread |
| Pod bị restart khi API tạm lỗi | Liveness/readiness mapping và failure policy |

Không dùng tăng timeout làm bước đầu tiên cho 403 hoặc sai CA. Không cấp ClusterRole để chữa connect timeout. Không restart ứng dụng chỉ để chữa một watch connection đã có cơ chế reconnect.

## 14. Ví dụ policy cho các chế độ

### Config bắt buộc lúc startup

- connect timeout ngắn nhưng đủ;
- tổng startup deadline hữu hạn;
- retry có backoff;
- fail startup nếu không có config hợp lệ;
- log nguyên nhân không lộ Secret;
- rollout không tạo quá nhiều Pod đồng thời.

### Discovery tùy chọn lúc runtime

- khởi tạo bằng danh sách Service hoặc fallback DNS;
- cache có tuổi tối đa;
- watcher reconnect;
- không dùng instance quá cũ vô hạn;
- readiness phản ánh mức độ phục vụ thật, không phản ánh mọi warning API.

### Watcher cấu hình runtime

- giá trị cũ được giữ khi API tạm lỗi;
- giá trị mới được validate trước khi áp dụng;
- metric cache age;
- resync sau reconnect;
- rollback hoặc giữ giá trị cũ khi validation thất bại.

## 15. Checklist triển khai

- Xác định request nào gọi Kubernetes API.
- Tách connect timeout, read timeout và tổng deadline.
- Đặt retry budget thay vì retry vô hạn.
- Dùng backoff và jitter.
- Tách watch connection khỏi request get/list.
- Dùng một client được quản lý thay vì tạo client mỗi request.
- Xác định fallback khi API server gián đoạn.
- Quyết định cache tối đa bao lâu.
- Không dùng liveness để restart vì mọi lỗi dependency.
- Tách metric Kubernetes API khỏi metric API nghiệp vụ.
- Kiểm tra 401 và 403 bằng identity/RBAC, không bằng retry.
- Không ghi token hoặc Secret vào log.
- Kiểm tra behavior khi rollout nhiều Pod cùng lúc.

Các giá trị timeout cần được đo và điều chỉnh theo cluster thật. Không chạy thử bằng cách tắt API server trong production; dùng môi trường kiểm thử hoặc mô phỏng lỗi theo quy trình an toàn.

## 16. Kết luận

Connect timeout giới hạn thời gian mở kết nối đến Kubernetes API. Read timeout giới hạn thời gian chờ dữ liệu sau khi kết nối đã có. Request deadline giới hạn toàn bộ thao tác và retry budget. Watch cần cơ chế reconnect, resync, backoff và theo dõi tuổi cache riêng.

Khi API server gián đoạn, ứng dụng Spring Cloud Kubernetes cần behavior rõ: fail startup nếu cấu hình bắt buộc, dùng cache trong thời gian giới hạn cho discovery, giữ cấu hình cũ khi watcher mất kết nối hoặc tạm ngừng traffic khi không thể phục vụ an toàn. Không dùng một timeout hoặc một chiến lược retry cho mọi đường gọi.

Thiết kế timeout cùng RBAC, ServiceAccount, readiness và observability giúp ứng dụng chịu được gián đoạn ngắn mà không tạo retry storm, restart loop hoặc dùng dữ liệu stale vô hạn.
