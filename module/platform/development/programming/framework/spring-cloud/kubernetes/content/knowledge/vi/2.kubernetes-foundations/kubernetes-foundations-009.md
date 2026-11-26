# Readiness, liveness và startup probe

## 1. Vì sao probe quan trọng với ứng dụng Spring?

Kubernetes cần biết một container đang chạy có thật sự sẵn sàng nhận traffic hay không và có cần được khởi động lại hay không. Một process Java có thể còn tồn tại nhưng đang khởi động, bị treo, mất kết nối đến tài nguyên bắt buộc hoặc chưa hoàn tất việc nạp cấu hình. Chỉ nhìn vào việc container còn chạy không đủ để quyết định đường gọi và vòng đời workload.

Kubernetes cung cấp ba loại probe thường dùng:

- **Readiness probe** trả lời: Pod có nên nhận request mới ngay lúc này không?
- **Liveness probe** trả lời: Container có đang ở trạng thái cần được khởi động lại không?
- **Startup probe** trả lời: Ứng dụng đã hoàn tất khởi động ban đầu chưa?

Ba probe có mục tiêu khác nhau. Readiness thất bại thường khiến Pod bị loại khỏi endpoint sẵn sàng nhưng không tự khởi động lại container. Liveness thất bại có thể khiến kubelet khởi động lại container. Startup probe bảo vệ ứng dụng khởi động chậm bằng cách trì hoãn việc đánh giá liveness và readiness cho tới khi startup thành công.

Đối với Spring Cloud Kubernetes, probe còn liên quan đến Service, EndpointSlice, rollout, Configuration Watcher và cách ứng dụng phản ứng khi ConfigMap hoặc Secret thay đổi. Một cấu hình probe đúng giúp cluster ngừng gửi request đến Pod chưa phục vụ được, đồng thời tránh khởi động lại hàng loạt chỉ vì ứng dụng cần nhiều thời gian để khởi động.

## 2. Trạng thái chạy và trạng thái sẵn sàng

Cần phân biệt ba ý:

1. Container có process đang chạy.
2. Pod được Kubernetes xem là Ready.
3. Service có thể dùng Pod làm endpoint sẵn sàng.

Một process Spring có thể đã mở JVM nhưng chưa hoàn tất khởi tạo bean. Khi đó container có thể được báo Running, nhưng readiness probe vẫn thất bại. Service không nên đưa Pod chưa Ready vào tập backend phục vụ traffic thông thường.

Ngược lại, một Pod có thể tạm thời không Ready vì dependency bắt buộc chưa sẵn sàng. Điều này không nhất thiết có nghĩa process bị hỏng cần restart. Readiness là tín hiệu điều phối traffic; liveness là tín hiệu vòng đời process.

~~~text
Container process đang chạy
          |
          +--> startup probe thành công? ---- chưa --> chưa đánh giá bình thường
          |
          +--> readiness thành công? -------- không --> tạm ngừng nhận traffic
          |                                  có --> có thể nhận traffic
          |
          +--> liveness thất bại? ----------- có --> kubelet xử lý restart
~~~

Mô hình trên là khái niệm. Quyết định cuối cùng còn phụ thuộc ngưỡng thành công, ngưỡng thất bại, chu kỳ kiểm tra và cách workload được triển khai.

## 3. Readiness probe

### 3.1. Mục đích

Readiness probe kiểm tra khả năng nhận request của container tại thời điểm hiện tại. Khi probe thất bại đủ số lần theo cấu hình, Pod được đánh dấu không sẵn sàng. Các endpoint của Service có thể được cập nhật để ngừng gửi traffic mới đến Pod đó.

Readiness phù hợp cho các tình huống như:

- ứng dụng vẫn khởi động nhưng HTTP server đã mở cổng;
- ứng dụng đang nạp hoặc xác thực cấu hình;
- kết nối tới dependency bắt buộc tạm thời chưa dùng được;
- ứng dụng cần rút khỏi traffic trước khi graceful shutdown;
- một Pod vừa được cập nhật và cần thời gian warm-up cache.

Readiness thất bại không phải lệnh restart. Nếu ứng dụng vẫn chạy và có thể tự phục hồi, việc tạm ngừng traffic thường an toàn hơn việc liên tục restart.

### 3.2. Readiness của Spring Boot

Ứng dụng Spring Boot có thể dùng endpoint sức khỏe của Actuator, trong đó các nhóm liveness và readiness được cấu hình theo phiên bản Spring Boot và dependency của dự án. Một cấu hình minh họa:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

Khi dùng endpoint readiness, cần kiểm tra rằng đường dẫn và cổng thực tế khớp với cấu hình management server. Nếu Actuator chạy trên cổng riêng, probe phải gọi cổng đó hoặc ứng dụng phải cung cấp endpoint trên cổng mà Pod công bố.

Ví dụ Deployment:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: management
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1
~~~

Đây là mẫu minh họa. Endpoint cần tồn tại trong ứng dụng và cổng management phải có tên tương ứng trong phần ports của container.

### 3.3. Readiness không nên kiểm tra mọi dependency một cách máy móc

Có thể đưa trạng thái dependency vào readiness, nhưng cần xác định ý nghĩa vận hành. Nếu một dependency phụ không ảnh hưởng đến mọi request bị lỗi mà readiness kiểm tra mọi thứ, toàn bộ Pod có thể bị loại khỏi traffic dù phần lớn API vẫn phục vụ được.

Ngược lại, nếu một dependency thật sự bắt buộc cho mọi request mà readiness không kiểm tra, Service có thể tiếp tục gửi request đến Pod chắc chắn trả lỗi.

Nên phân loại dependency:

| Dependency | Có nên ảnh hưởng readiness? | Lý do cần xem xét |
| --- | --- | --- |
| Cơ sở dữ liệu bắt buộc cho mọi request | Có thể có | Pod không thể xử lý hợp đồng chính nếu mất kết nối |
| Cache tùy chọn | Thường không | Ứng dụng có thể dùng đường xử lý chậm hơn |
| Một API chỉ dùng cho tính năng phụ | Có thể tách | Không nên làm mất toàn bộ traffic |
| ConfigMap bắt buộc cho startup | Có thể kiểm tra lúc startup | Cấu hình thiếu có thể là lỗi triển khai |
| Service khác có retry bất đồng bộ | Tùy thiết kế | Tránh loại toàn bộ Pod vì lỗi tạm thời |

Readiness nên phản ánh khả năng phục vụ theo hợp đồng mà Service đang công bố, không chỉ phản ánh số lượng dependency đang hoạt động.

## 4. Liveness probe

### 4.1. Mục đích

Liveness probe kiểm tra process có còn hoạt động theo cách có thể tự phục hồi hay không. Khi liveness thất bại đủ ngưỡng, kubelet có thể khởi động lại container theo restart policy.

Liveness phù hợp cho tình trạng như:

- process bị deadlock;
- event loop hoặc worker nội bộ bị treo;
- ứng dụng không còn phản hồi dù process vẫn tồn tại;
- trạng thái nội bộ không thể tự phục hồi nếu không restart.

Liveness không nên dùng để kiểm tra mọi dependency bên ngoài. Nếu cơ sở dữ liệu tạm thời lỗi mà liveness thất bại, tất cả Pod có thể bị restart cùng lúc trong khi việc restart không chữa được dependency. Hệ quả có thể là retry storm, mất cache và làm tình hình nghiêm trọng hơn.

### 4.2. Một endpoint liveness đơn giản

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: management
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Endpoint liveness nên nhẹ, nhanh và phản ánh trạng thái mà restart thật sự có khả năng cải thiện. Không để endpoint này thực hiện truy vấn sâu tới mọi hệ thống bên ngoài nếu ứng dụng không cần restart khi một hệ thống đó tạm thời mất kết nối.

Liveness thành công cũng không có nghĩa Pod nhận traffic. Một Pod có thể liveness tốt nhưng readiness thất bại vì đang warm-up hoặc đang rút khỏi traffic để xử lý một trạng thái tạm thời.

## 5. Startup probe

### 5.1. Mục đích

Startup probe dành cho ứng dụng mất nhiều thời gian để khởi động. Khi startup probe được cấu hình, kubelet ưu tiên chờ startup probe thành công trước khi thực hiện các probe liveness và readiness theo cách bình thường.

Điều này giải quyết xung đột thường gặp: liveness cần phát hiện deadlock nhanh sau khi ứng dụng đã khởi động, nhưng cùng ngưỡng đó lại quá ngắn đối với thời gian khởi động JVM, migration, nạp cache hoặc tải cấu hình lớn.

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health
    port: management
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 60
~~~

Với mẫu trên, tổng thời gian cho phép khởi động xấp xỉ số lần thất bại nhân với chu kỳ, có xét đến thời gian phản hồi và hành vi thực tế của kubelet. Không nên coi đây là một đồng hồ tuyệt đối; cần đo startup trong điều kiện tài nguyên và tải gần với môi trường triển khai.

Nếu startup probe thất bại vượt ngưỡng, container được xem là khởi động không thành công và kubelet có thể restart container. Vì vậy, startup probe không phải cách vô hạn để bỏ qua một ứng dụng không thể khởi động.

### 5.2. Dùng cùng endpoint hay endpoint riêng?

Có thể dùng endpoint sức khỏe tổng quát cho startup, hoặc cung cấp endpoint phù hợp với giai đoạn khởi động. Quyết định phụ thuộc vào điều kiện ứng dụng:

- Nếu mọi điều kiện cần cho việc khởi động đều thể hiện trong health endpoint, dùng endpoint đó có thể đơn giản.
- Nếu endpoint tổng quát kiểm tra dependency chưa cần ở giai đoạn đầu, nên tách kiểm tra để startup không bị chặn quá mức.
- Nếu startup chỉ cần HTTP server và bean cốt lõi, không nên buộc nó chờ một dependency tùy chọn.

Mục tiêu là phân biệt “chưa khởi động xong” với “đã khởi động nhưng bị treo”. Startup probe phụ trách giai đoạn đầu; liveness cần phát hiện vấn đề sau giai đoạn đó.

## 6. Ba loại cách kiểm tra probe

### 6.1. HTTP GET

HTTP probe gửi request đến địa chỉ và cổng của container. Mã trạng thái thành công phụ thuộc quy tắc của Kubernetes; thông thường response trong nhóm thành công được xem là đạt, còn lỗi HTTP hoặc timeout là thất bại.

~~~yaml
readinessProbe:
  httpGet:
    path: /ready
    port: http
    scheme: HTTP
    httpHeaders:
      - name: X-Probe
        value: kubernetes
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Dùng tên port giúp tránh lặp số cổng trong nhiều cấu hình, nhưng tên phải tồn tại trong khai báo container. Path phải là endpoint thực tế và không nên phụ thuộc vào xác thực người dùng thông thường. Nếu endpoint yêu cầu token ứng dụng mà kubelet không thể cung cấp, probe sẽ thất bại dù API nghiệp vụ có thể hoạt động.

Cần kiểm tra:

- endpoint có bind trên địa chỉ và cổng mà probe truy cập không;
- HTTP hoặc HTTPS có đúng scheme không;
- server management có chạy cổng riêng không;
- endpoint có trả chậm hơn timeout không;
- reverse proxy hoặc base path có làm thay đổi URL không.

### 6.2. TCP socket

TCP probe chỉ kiểm tra kubelet có thể mở kết nối TCP tới cổng hay không. Nó hữu ích khi ứng dụng không có endpoint HTTP, nhưng tín hiệu hạn chế hơn.

TCP thành công cho biết có process lắng nghe cổng. Nó không xác nhận process đã xử lý đúng request, đã nạp cấu hình hay dependency đã sẵn sàng. Vì vậy, TCP có thể phù hợp cho liveness rất cơ bản, còn readiness thường nên dùng HTTP hoặc một kiểm tra thể hiện khả năng phục vụ rõ hơn.

~~~yaml
livenessProbe:
  tcpSocket:
    port: http
  periodSeconds: 10
  failureThreshold: 3
~~~

### 6.3. Exec

Exec probe chạy một lệnh bên trong container. Lệnh trả mã thành công thì probe đạt; mã khác hoặc lỗi thực thi là thất bại.

~~~yaml
readinessProbe:
  exec:
    command:
      - sh
      - -c
      - test -f /tmp/application-ready
  periodSeconds: 5
  failureThreshold: 2
~~~

Exec có thể hữu ích khi trạng thái được biểu diễn bằng file hoặc lệnh kiểm tra nội bộ. Tuy nhiên, lệnh phụ thuộc vào shell, binary và filesystem của image. Image tối giản có thể không có sh, curl hoặc công cụ được giả định. Exec probe cũng tạo thêm process và chi phí; lệnh nên ngắn, xác định và không gây side effect.

Không dùng probe để thực hiện migration, xóa dữ liệu, gọi API thay đổi trạng thái hoặc thao tác có thể lặp lại. Kubelet có thể chạy probe nhiều lần.

### 6.4. gRPC probe

gRPC probe có thể dùng khi ứng dụng công bố health checking theo giao thức gRPC và cluster hỗ trợ kiểu probe này. Service name, cổng và cơ chế TLS cần khớp với server. Không coi một cổng TCP mở là bằng chứng gRPC health check thành công.

Nếu ứng dụng vừa cung cấp HTTP Actuator vừa cung cấp gRPC, chọn probe theo tín hiệu đại diện cho hợp đồng cần bảo vệ. Với gRPC, cần kiểm tra hành vi khi server đang khởi động, khi dependency lỗi và khi graceful shutdown.

## 7. Các tham số điều chỉnh probe

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| initialDelaySeconds | Chờ trước lần probe đầu tiên trong các trường hợp áp dụng |
| periodSeconds | Khoảng thời gian giữa các lần kiểm tra |
| timeoutSeconds | Thời gian tối đa chờ một lần kiểm tra |
| failureThreshold | Số lần thất bại liên tiếp để chuyển sang trạng thái thất bại |
| successThreshold | Số lần thành công liên tiếp để chuyển lại trạng thái đạt; readiness thường hay dùng giá trị mặc định |
| terminationGracePeriodSeconds | Thời gian kết thúc graceful khi kubelet dừng container, tùy cấu hình và phiên bản |

Không chọn các giá trị chỉ vì chúng “trông an toàn”. Timeout quá dài làm phát hiện chậm và có thể tạo nhiều request đang chờ. Timeout quá ngắn gây false negative khi JVM chịu tải. Period quá ngắn tạo tải không cần thiết; period quá dài làm traffic tiếp tục đến Pod lỗi lâu hơn.

Có thể ước lượng thời gian phản ứng theo số lần liên tiếp và chu kỳ, nhưng cần kiểm tra hành vi thực tế. Probe không thay thế metric và tracing; nó là tín hiệu điều phối, không phải hệ thống quan sát đầy đủ.

## 8. Thiết kế endpoint sức khỏe cho Spring

### 8.1. Endpoint phải nhẹ và không có side effect

Endpoint probe được gọi định kỳ trên nhiều Pod. Endpoint nên:

- trả lời nhanh;
- không ghi dữ liệu;
- không tạo job;
- không gửi request thay đổi trạng thái;
- có logic ổn định và dễ quan sát;
- phân biệt rõ liveness với readiness.

Nếu endpoint probe gọi một dependency chậm, timeout của dependency cần được giới hạn. Một probe bị treo có thể tạo ra chuỗi timeout và làm Pod bị đánh dấu sai.

### 8.2. Liveness và readiness khác nội dung

Liveness nên trả lời khả năng process tự tiếp tục. Readiness nên trả lời khả năng Pod nhận traffic theo hợp đồng. Một ứng dụng có thể có liveness UP và readiness DOWN trong thời gian bình thường, ví dụ đang chờ kết nối cơ sở dữ liệu bắt buộc hoặc đang nạp cấu hình.

Với Spring Boot Actuator, các health group liveness và readiness có thể được bật và cấu hình theo dependency dự án. Cần đọc rõ dependency nào được đưa vào từng group thay vì đưa toàn bộ indicator vào cả hai.

### 8.3. Cổng management riêng

Một số ứng dụng mở management endpoint trên cổng riêng. Khi đó cần khai báo cổng trong container:

~~~yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081
~~~

Và probe phải dùng đúng tên:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: management
~~~

Khai báo containerPort mang tính mô tả và hỗ trợ tham chiếu tên; nó không tự làm process lắng nghe cổng đó. Spring phải thực sự bind management server trên cổng tương ứng.

## 9. Readiness trong rollout và graceful shutdown

Khi Deployment cập nhật image, Pod mới cần vượt qua readiness trước khi nhận đầy đủ traffic. Pod cũ có thể bị loại khỏi endpoint khi bắt đầu kết thúc. Tuy nhiên, việc loại endpoint và việc đóng các kết nối đang tồn tại có thể có độ trễ.

Ứng dụng Spring nên phối hợp:

- readiness để ngừng nhận request mới;
- graceful shutdown để hoàn tất request đang chạy trong thời gian cho phép;
- termination grace period phù hợp;
- connection pool và keep-alive timeout;
- retry và timeout của client.

Không giả định rằng readiness thất bại làm mọi kết nối lập tức biến mất. Client có thể giữ kết nối lâu dài; request đã gửi có thể vẫn đang xử lý. Nếu nghiệp vụ cần đảm bảo không mất dữ liệu, phải thiết kế idempotency, transaction và cơ chế retry riêng.

Trong một rollout, readiness quá nghiêm ngặt có thể khiến không có Pod nào Available. Readiness quá lỏng có thể cho traffic vào Pod chưa đủ khả năng. Cần kiểm tra cả thời gian khởi động, thời gian warm-up và số replica tối thiểu.

## 10. Readiness và Service

Service chọn Pod theo selector, còn readiness ảnh hưởng tập endpoint sẵn sàng. Luồng khái niệm:

~~~text
Pod template có label app=catalog
             |
             v
Service selector chọn Pod phù hợp
             |
             v
readiness probe cập nhật điều kiện Ready
             |
             v
EndpointSlice phản ánh endpoint sẵn sàng
             |
             v
Service route traffic đến backend phù hợp
~~~

Một DNS lookup thành công không bảo đảm có backend Ready. Tương tự, Pod Running không bảo đảm request nghiệp vụ sẽ thành công. Khi điều tra lỗi, cần xem Service selector, EndpointSlice, readiness status và phản hồi HTTP cùng nhau.

Trong mạng nội bộ, ứng dụng Spring chỉ cần gọi tên Service nếu đó là cách định địa chỉ đã chọn. Không cần gọi Kubernetes API để hỏi Pod nào đang đứng sau Service chỉ để gửi request HTTP thông thường.

## 11. Probe và Configuration Watcher

Configuration Watcher có thể nhận biết thay đổi ConfigMap hoặc Secret qua Kubernetes API, nhưng probe vẫn kiểm tra khả năng phục vụ thực tế của ứng dụng.

Ví dụ khi cấu hình timeout mới được áp dụng:

1. ConfigMap thay đổi.
2. Watcher nhận sự kiện hoặc component đọc lại dữ liệu.
3. Ứng dụng xác thực và áp dụng cấu hình mới.
4. Readiness có thể phản ánh ứng dụng đã sẵn sàng với cấu hình mới, nếu cấu hình là điều kiện bắt buộc.
5. Liveness vẫn chỉ nên restart khi process ở trạng thái không thể tự phục hồi.

Không dùng liveness để biểu đạt “cấu hình mới chưa đến”. Nếu cấu hình chưa đến nhưng ứng dụng vẫn phục vụ an toàn, readiness hoặc metric phù hợp hơn. Nếu cấu hình bắt buộc và không hợp lệ, cần có chính sách rõ: giữ cấu hình cũ, tạm ngừng traffic, fail startup hoặc dừng process để controller tạo Pod mới.

Nếu watcher dựa trên Kubernetes API, RBAC của nó phải cho phép đọc và watch resource cần thiết. Quyền API không sửa được một readiness endpoint sai path hoặc một probe trỏ nhầm cổng.

## 12. Các lỗi cấu hình phổ biến

### Probe trỏ sai path

Ứng dụng trả 404 hoặc 401 vì path không tồn tại hoặc endpoint yêu cầu cơ chế xác thực khác. Kiểm tra route thật trong container và cách exposure của Actuator.

### Probe trỏ sai cổng

Application server nghe 8080 nhưng probe gọi cổng management chưa mở, hoặc tên port trong probe không khớp khai báo container. Kiểm tra port binding, tên port và log khởi động.

### Liveness quá giống readiness

Liveness kiểm tra database, cache và nhiều API bên ngoài. Một dependency tạm thời lỗi khiến container restart liên tục. Tách mục tiêu: dependency ảnh hưởng traffic thì cân nhắc readiness; liveness chỉ kiểm tra trạng thái cần restart.

### Không có startup probe cho ứng dụng khởi động chậm

Liveness bắt đầu quá sớm và giết ứng dụng trước khi Spring hoàn tất. Dùng startup probe hoặc điều chỉnh cách kiểm tra sau khi đo startup thực tế.

### Dùng initial delay thay cho startup probe

initialDelaySeconds chỉ trì hoãn lần kiểm tra đầu. Nếu thời gian khởi động dao động lớn, giá trị cố định dễ quá ngắn hoặc quá dài. Startup probe biểu đạt rõ giai đoạn khởi động và bảo vệ các probe sau đó.

### Exec phụ thuộc tool không có trong image

Lệnh hoạt động trên máy phát triển nhưng thất bại trong image sản xuất tối giản. Dùng HTTP endpoint, TCP hoặc lệnh chắc chắn có trong image; không cài thêm tool chỉ để che lỗi thiết kế.

### Endpoint probe quá nặng

Probe truy vấn sâu, tạo log lớn hoặc gọi nhiều dependency. Khi cluster tăng replica, chính probe tạo tải và làm sức khỏe xấu hơn. Giữ endpoint nhẹ và đặt timeout hợp lý.

## 13. Chẩn đoán theo thứ tự

Khi Pod không Ready hoặc bị restart, kiểm tra theo lớp:

1. Xem trạng thái Pod và điều kiện Ready.
2. Xem event để biết probe thất bại, timeout hay container bị restart.
3. Kiểm tra path, port, scheme và tên port trong manifest.
4. Gọi endpoint từ vị trí phù hợp trong cluster nếu môi trường cho phép.
5. Đọc log ứng dụng để phân biệt server chưa bind, endpoint trả lỗi hay dependency thất bại.
6. Kiểm tra Service và EndpointSlice nếu vấn đề biểu hiện như không nhận traffic.
7. Kiểm tra resource CPU, memory và thời gian GC nếu probe timeout dưới tải.
8. Kiểm tra rollout và graceful shutdown nếu lỗi xuất hiện khi cập nhật.

Bảng gợi ý:

| Hiện tượng | Điểm kiểm tra đầu tiên |
| --- | --- |
| Pod Running nhưng NotReady | readiness path, port, status response và dependency |
| Container restart liên tục | liveness, startup, exit code và event |
| Startup timeout | thời gian khởi động, startup threshold và registry/config |
| Service không gửi traffic | selector, endpoint và readiness |
| Lỗi chỉ xảy ra khi rollout | graceful shutdown, connection pool và thời gian warm-up |
| Lỗi chỉ dưới tải | timeout probe, CPU throttling, GC và thread pool |
| Watcher báo cấu hình mới nhưng Pod vẫn lỗi | validation cấu hình, readiness và log áp dụng |

Không tăng failureThreshold vô hạn khi chưa biết nguyên nhân. Ngưỡng lớn chỉ làm phản ứng chậm hơn; nó không sửa endpoint sai hoặc ứng dụng không thể khởi động.

## 14. Manifest mẫu cho ứng dụng Spring

Mẫu sau minh họa ba probe cùng management port:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: registry.example.com/catalog:1.0.0
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 8081
          startupProbe:
            httpGet:
              path: /actuator/health
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Mẫu này không phải giá trị chuẩn cho mọi ứng dụng. Cần thay path, cổng, ngưỡng và dependency theo hành vi thực tế. Cần kiểm tra rằng ứng dụng thật sự cung cấp ba endpoint này và các endpoint không bị chặn bởi authentication không phù hợp.

## 15. Nguyên tắc thiết kế

- Readiness quyết định nhận traffic, không quyết định restart.
- Liveness phát hiện trạng thái cần restart, không phải bảng kiểm tra mọi dependency.
- Startup bảo vệ giai đoạn khởi động chậm, không che giấu lỗi khởi động vô hạn.
- Probe phải nhẹ, có timeout và không có side effect.
- Endpoint và port trong manifest phải khớp server thực tế.
- Chọn HTTP, TCP, exec hoặc gRPC theo tín hiệu cần kiểm tra.
- Kết hợp probe với Service, EndpointSlice, graceful shutdown và quan sát.
- Khi cấu hình thay đổi qua ConfigMap hoặc Secret, xác định rõ lúc nào ứng dụng áp dụng và probe phản ánh điều kiện nào.
- Không cấp thêm RBAC chỉ vì probe thất bại; probe thường được kubelet gọi đến container, còn quyền API là câu chuyện riêng của integration.

## 16. Kết luận

Readiness, liveness và startup probe là ba tín hiệu khác nhau trong vòng đời Pod. Readiness bảo vệ traffic bằng cách loại Pod chưa phục vụ được khỏi endpoint sẵn sàng. Liveness cho kubelet biết khi nào process có thể cần restart. Startup cho phép ứng dụng khởi động chậm mà không bị liveness kết luận quá sớm.

Với ứng dụng Spring, endpoint Actuator có thể cung cấp tín hiệu rõ ràng, nhưng cấu hình phải khớp cổng, path, dependency và chính sách rollout. Khi kết hợp Spring Cloud Kubernetes, hãy giữ ranh giới giữa probe, Service, Kubernetes API, RBAC và Configuration Watcher. Một probe tốt phản ánh đúng quyết định vận hành mà cluster cần đưa ra; nó không thay thế log, metric, tracing hay xử lý lỗi trong ứng dụng.
