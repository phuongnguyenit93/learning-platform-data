# Kiểm tra sức khỏe và tránh định tuyến đến thể hiện chưa sẵn sàng

## 1. Bối cảnh và mục tiêu

Trong kiến trúc microservices, một năng lực như Order hoặc Catalog thường có nhiều **thể hiện dịch vụ (service instances)**. Không phải instance nào cũng ở trạng thái phục vụ: một instance đang khởi động, một instance đang nạp cấu hình, một instance vừa mất kết nối đến tài nguyên thiết yếu, và một instance khác đang chuẩn bị dừng để triển khai phiên bản mới.

Nếu load balancer chỉ nhìn thấy một cổng TCP đang mở rồi gửi request đến mọi instance, hệ thống có thể gặp lỗi 502/503, timeout, request bị ngắt giữa chừng hoặc truy cập dữ liệu chưa được khởi tạo. Ngược lại, nếu health check quá nhạy, một sự cố nhỏ ở dependency chung có thể làm **toàn bộ replica tự loại khỏi routing pool**, khiến dịch vụ mất khả dụng dù một số chức năng vẫn hoạt động.

Câu hỏi thiết kế là: **Tại thời điểm này, thể hiện nào có thể nhận request mới một cách an toàn, thể hiện nào cần được khởi động lại và làm sao chuyển traffic giữa các phiên bản mà không gây lỗi không cần thiết?**

Bài học tập trung vào:
- Phân biệt liveness, readiness, startup và trạng thái suy giảm (degraded).
- Thiết kế health endpoint có ngữ nghĩa rõ, chi phí thấp, không tự tạo sự cố.
- Hiểu cách Kubernetes Service, EndpointSlice, gateway, load balancer và registry sử dụng tín hiệu sức khỏe.
- Tránh gửi traffic quá sớm trong startup/warm-up và quá muộn trong shutdown.
- Xử lý dependency outage, overload, retry và tình huống không còn Ready endpoints.
- Cấu hình minh họa cho Spring Boot/Java và Kubernetes.
- Đo, kiểm thử và ghi quyết định kiến trúc theo trường hợp thực tế.

**Nguyên tắc cốt lõi:** Process đang chạy không đồng nghĩa service đã sẵn sàng. Readiness phục vụ quyết định **có định tuyến request mới tới instance không**; liveness phục vụ quyết định **instance có cần được restart không**. Hai câu hỏi này không nên dùng một điều kiện chung thiếu cân nhắc.

## 2. Những khái niệm cần phân biệt

### 2.1. Process alive

Một process Java có thể tồn tại, giữ cổng HTTP mở và vẫn nhận TCP connection. Tuy nhiên:
- Spring context mới khởi tạo một phần.
- Cache chứa quy tắc bắt buộc chưa được nạp.
- Thread pool nghiệp vụ đã cạn.
- Connection pool còn đợi cấu hình hoặc secret.
- Ứng dụng đã bắt đầu shutdown nhưng vẫn đang hoàn tất request cũ.

Vì vậy, TCP connect thành công chỉ xác nhận một phần đường mạng, không chứng minh khả năng xử lý nghiệp vụ.

### 2.2. Liveness

**Liveness** trả lời: instance còn trong trạng thái vận hành có thể tiếp tục hay đã lỗi tới mức cần restart?

Ở Kubernetes, khi liveness probe thất bại đủ ngưỡng, kubelet có thể restart container. Một liveness probe tốt thường:
- Trả lời nhanh, không tạo tải lớn.
- Tập trung vào tình trạng bản thân tiến trình.
- Chỉ thất bại vì lỗi nội bộ khó tự phục hồi bằng cách khác.
- Không yêu cầu mọi downstream API/database đều hoạt động.

Nếu liveness gọi Payment và Payment lỗi cả vùng, mọi pod Order có thể cùng restart. Restart Order không sửa Payment và còn gây tốn CPU, cache warm-up và connection storm.

### 2.3. Readiness

**Readiness** trả lời: instance có **đủ điều kiện nhận request mới** thông qua đường routing được cấu hình không?

Readiness có thể chưa đạt vì:
- Startup/warm-up thiết yếu chưa hoàn thành.
- Cấu hình cục bộ cần thiết chưa hợp lệ.
- Instance chuyển trạng thái draining trước shutdown.
- Tài nguyên cục bộ thiết yếu không còn đủ để phục vụ theo hợp đồng.
- Một phụ thuộc thực sự bắt buộc đối với mọi request mà instance đang nhận không khả dụng, với chính sách chống lỗi dây chuyền phù hợp.

Trong Kubernetes, readiness thất bại khiến Pod không được xem là Ready để phục vụ qua Service thông thường; **nó không tự restart container**. Khi điều kiện phục hồi, instance có thể quay lại pool.

Readiness không phải cam kết rằng mọi request đã route trước đó sẽ bị hủy. Thông tin endpoint cần thời gian cập nhật và connection cũ có thể tiếp tục tồn tại.

### 2.4. Startup

**Startup probe** phục vụ ứng dụng khởi động chậm. Khi startup probe được cấu hình trong Kubernetes, liveness/readiness probes sẽ bị trì hoãn cho đến khi startup probe thành công. Nếu startup thất bại quá ngưỡng, container có thể bị restart.

Ví dụ một Java service cần 30–50 giây để tải class, khởi tạo Spring, cấu hình và warm-up. Liveness thất bại sau vài giây có thể tạo CrashLoopBackOff dù ứng dụng vốn có thể hoàn thành startup. Startup probe dành riêng một cửa sổ để khởi động, thay vì làm liveness bình thường quá rộng.

### 2.5. Dependency health

Một service có thể kiểm tra database, broker, Redis và các API liên quan. Nhưng không phải dependency lỗi nào cũng phải làm toàn instance NotReady.

Hãy hỏi: “Lỗi này có khiến **mọi loại request vào pool** không thể phục vụ, và chuyển sang instance khác có giúp ích không?”

Ví dụ:
- Broker tạm lỗi, nhưng Order dùng outbox và vẫn ghi được intent vào database: nhiều command có thể vẫn được nhận.
- Redis lỗi nhưng Catalog có fallback dùng database: vẫn có thể phục vụ, với giới hạn tải phù hợp.
- Recommendation lỗi nhưng trang sản phẩm có thể hiển thị mà không có gợi ý: không cần rút toàn bộ Catalog.
- Database ghi không sẵn sàng cho tất cả command: có thể cần trả lỗi hoặc tạm ngừng nhận command, nhưng readiness của cả service phải được quyết định theo phạm vi traffic.

### 2.6. Degraded khác NotReady

Một service có thể **degraded** nhưng vẫn cung cấp một tập chức năng có ích. Ví dụ hệ thống vẫn xem được lịch sử đơn nhưng chưa tạo được đơn mới. Đây là thông tin cần được ghi trong metric/API contract; không nhất thiết biến một boolean readiness toàn instance thành false.

## 3. Mô hình vòng đời instance

Một vòng đời minh họa:

    CREATED
       |
       v
    STARTING
       |
       | startup/warm-up thiết yếu
       v
    NOT_READY
       |
       | Đủ điều kiện
       v
    READY <---------> TEMPORARILY_NOT_READY
       |
       | rollout / scale down / shutdown
       v
    DRAINING
       |
       | Ngừng nhận mới, xử lý in-flight
       v
    TERMINATED

Liveness, readiness, startup và draining là những tín hiệu/vòng đời có quan hệ nhưng không tạo ra một state machine bắt buộc giống nhau ở mọi framework.

| Trạng thái | Process có thể chạy? | Có nên nhận traffic mới? | Cách xử lý |
|---|---|---|---|
| Starting | Có | Chưa | Chờ hoàn tất điều kiện cần |
| Warming | Có | Chưa, nếu warm-up bắt buộc | Tiếp tục warm-up |
| Ready | Có | Có | Nhận request theo capacity |
| Temporarily NotReady | Có | Thường không qua pool tương ứng | Khôi phục và đánh giá lại |
| Draining | Có | Không nên nhận mới | Hoàn tất request đang chạy |
| Dead/unrecoverable | Không hoặc không hữu dụng | Không | Restart/replace theo chính sách |

Sự khác biệt quan trọng là một instance có thể **Live nhưng NotReady**: không cần restart, chỉ cần tạm dừng route để phục hồi.

## 4. Thiết kế hợp đồng health endpoint

Một thiết kế phổ biến:

    GET /livez    -> trạng thái liveness
    GET /readyz   -> trạng thái readiness
    GET /startupz -> trạng thái hoàn tất khởi tạo

Tên đường dẫn không phải tiêu chuẩn bắt buộc. Spring Boot Actuator có các health groups riêng như /actuator/health/liveness và /actuator/health/readiness; có thể cấu hình đường phụ trên cổng ứng dụng trong phiên bản hỗ trợ.

Một health endpoint phải có hợp đồng cụ thể:
- Probe phục vụ restart, routing hay chỉ quan sát?
- Khi nào trả thành công hoặc thất bại?
- HTTP status nào được hạ tầng diễn giải?
- Có lộ thông tin nội bộ trong body không?
- Một lần gọi có thể mất bao lâu?
- Probe chạy với tần suất nào?
- Có gọi tới DB/broker/downstream không, và nếu có thì vì sao?
- Khi shutdown có trạng thái nào được phát trước?
- Ai chịu trách nhiệm nếu probe trả sai?

### 4.1. Health check cần nhẹ

Nếu 30 pod mỗi pod bị kiểm tra nhiều lần mỗi giây, một health endpoint chạy truy vấn tổng hợp nặng hoặc thực hiện thao tác ghi thử có thể tạo tải đáng kể.

Ưu tiên trạng thái cục bộ và tín hiệu đã có:
- Cờ initialization/warm-up.
- Cờ draining.
- Trạng thái tài nguyên cục bộ thiết yếu.
- Kết quả kiểm tra dependency nhẹ và có giới hạn thời gian nếu cần.
- Cache ngắn kết quả kiểm tra đắt tiền, với chính sách độ tươi được ghi rõ.

Không gửi giao dịch thanh toán thử, không tạo đơn giả, không thực hiện migration khi chỉ có một probe GET. Probe nặng tự nó có thể làm service trở nên không khỏe.

### 4.2. Cổng probe phải phản ánh cổng phục vụ

Nếu management server chạy ở port 9090 còn ứng dụng phục vụ port 8080, management /health có thể trả 200 trong khi HTTP connector nghiệp vụ trên 8080 bị treo.

Khi phù hợp, cung cấp readiness/liveness trên **cổng ứng dụng chính** để tăng khả năng phát hiện vấn đề ở đường phục vụ thực. Nếu phải dùng cổng riêng, cần nhận rõ hạn chế và thêm kiểm tra/giám sát tương ứng.

### 4.3. Không dùng health endpoint làm dashboard chi tiết

Probe thường chỉ cần HTTP status và thông điệp ngắn. Các nguyên nhân lỗi, metric connection pool, queue, GC, latency và dependency health nên được gửi tới observability system. Tránh body trả chi tiết schema, password, URL database hoặc tên tenant ra endpoint có thể truy cập từ bên ngoài.

## 5. Service discovery và lựa chọn endpoint

Các service không nhất thiết biết địa chỉ IP của nhau cố định. **Service discovery** duy trì hoặc cung cấp tập instance; **routing/load balancing** chọn endpoint cho request.

Các cách phổ biến:
1. **Client-side discovery:** Client đọc registry/DNS, cache và tự chọn endpoint.
2. **Server-side load balancing:** Caller gọi một logical endpoint, load balancer chọn backend.
3. **Kubernetes Service:** Hạ tầng dựa trên Pod/EndpointSlice và trạng thái liên quan để chuyển traffic.
4. **Ingress/API gateway:** Quyết định route ở tầng HTTP, có thể kết hợp health riêng.
5. **Service mesh:** Data plane có chính sách lựa chọn backend, retry, outlier detection.
6. **Registry riêng:** Consul, Eureka hoặc hệ thống tương tự, với heartbeat/check/lease đặc thù.

Một số câu hỏi cần trả lời:
- Ai quyết định instance Ready?
- Trạng thái được cập nhật tới registry sau bao lâu?
- Bộ chọn endpoint có tôn trọng readiness không?
- Client có cache địa chỉ hay giữ connection keep-alive không?
- Khi không còn endpoint, trả lỗi, đợi, chuyển zone hay dùng fallback?
- Những request đang chạy trên instance bị loại được xử lý ra sao?

**Không có bảo đảm rút endpoint tức thời trên toàn hệ phân tán.** DNS TTL, registry propagation, sidecar, connection pool và proxy cần thời gian cập nhật.

### 5.1. Active health và passive health

**Active check** gửi request probe định kỳ, giúp phát hiện backend không hoạt động trước khi traffic người dùng đến. Nó dễ tạo false positive nếu endpoint quá đơn giản.

**Passive check** dựa trên kết quả request thật như connection reset, timeout hoặc một số lỗi 5xx. Nó gần với trải nghiệm người dùng nhưng phụ thuộc traffic và có thể nhầm lỗi nghiệp vụ với lỗi instance.

Outlier detection của mesh/load balancer có thể tạm loại backend có tỷ lệ lỗi bất thường. Đây là một quyết định riêng của tầng routing, **không đồng nghĩa readiness do ứng dụng phát**. Cần phối hợp tránh việc mọi tầng đồng loạt loại instance quá mạnh.

## 6. Kubernetes: Pod Ready và tập endpoint

Trong Kubernetes, kubelet thực hiện probes và cập nhật trạng thái Pod. Controller và thành phần data plane phản ánh trạng thái vào các backend phục vụ Service. EndpointSlice có điều kiện endpoint phục vụ lựa chọn.

Khi readiness không đạt, một Pod thông thường không được chọn làm backend Ready cho Service. Tuy nhiên:
- Endpoint update không tới mọi proxy cùng thời điểm.
- Request đã route trước có thể tiếp tục.
- Connection keep-alive vẫn có thể tồn tại.
- Một custom load balancer hoặc caller gọi trực tiếp Pod IP có thể bỏ qua đường Service.
- Các cấu hình đặc biệt như publishNotReadyAddresses có thể thay đổi hành vi.

Readiness là tín hiệu định tuyến **có quá trình lan truyền**; không phải lệnh xóa mọi kết nối ngay tức thì.

### 6.1. Các trường probe quan trọng

| Trường | Ý nghĩa thiết kế |
|---|---|
| periodSeconds | Khoảng cách lên lịch kiểm tra |
| timeoutSeconds | Giới hạn chờ mỗi lần probe |
| failureThreshold | Ngưỡng số lần thất bại liên tiếp |
| successThreshold | Ngưỡng thành công liên tiếp để phục hồi theo loại probe |
| initialDelaySeconds | Trễ trước lần probe đầu tiên nếu được áp dụng |
| httpGet.path/port | Endpoint và cổng kiểm tra |
| startupProbe | Giai đoạn khởi động trước liveness/readiness bình thường |

Nếu readiness chỉ cần một lỗi ngắn để thành NotReady, các instance có thể flapping. Nếu liveness quá nhạy, một GC pause hoặc CPU spike dẫn tới restart không cần thiết. Ngưỡng phải dựa trên latency, mức ổn định và thời gian hồi phục của ứng dụng thực tế.

### 6.2. Ví dụ Deployment

Giả định ứng dụng Spring Boot cung cấp /readyz và /livez trên cổng 8080, readiness phản ánh khởi tạo cục bộ và draining:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: order
          image: example-registry/order-service:1.0.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Với startupProbe dùng /readyz, startup chỉ thành công khi trạng thái readiness lần đầu đạt. Điều này có thể phù hợp nếu readiness chủ yếu phản ánh khởi tạo cần thiết. **Nếu readiness còn phụ thuộc vào một dịch vụ ngoài có thể lỗi dài hạn**, startup probe có thể dẫn đến restart vô ích. Khi ấy cân nhắc một endpoint startup riêng, chỉ báo hoàn tất khởi tạo hoặc cấu hình lại phạm vi readiness.

Những con số trên là ví dụ, không phải cấu hình mặc định cho mọi ứng dụng. Cần đối chiếu thời gian khởi động, p99 latency và tải thực tế.

Service cơ bản:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Không nên suy từ manifest rằng mọi đường traffic đều đi qua Service. Ingress, service mesh hoặc client-side discovery cần được quan sát riêng khi có.

## 7. Spring Boot Actuator và health groups

Spring Boot Actuator hỗ trợ các nhóm health indicator và cơ chế liveness/readiness. Một cấu hình minh họa trong phiên bản hỗ trợ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info

server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Ở phiên bản Spring Boot có thuộc tính tương ứng, add-additional-paths có thể cung cấp /livez và /readyz trên cổng ứng dụng chính, bên cạnh đường Actuator health groups. Cần xác minh tên thuộc tính, thời điểm xuất hiện và đường dẫn theo phiên bản ứng dụng thực tế; không mặc định cấu hình chạy nguyên trạng trên mọi Spring Boot.

### 7.1. Liveness trong ứng dụng Java

Tránh thêm mọi dependency vào liveness. Một database chung down không phải lý do tốt để restart tất cả JVM. Cần tập trung vào:
- Runtime/progress nội bộ của service.
- Điều kiện không thể tự phục hồi mà restart có ích.
- Endpoint kiểm tra có thể trả lời đúng trong thời hạn ngắn.

Nếu thread pool nghiệp vụ bị nghẽn nhưng health executor riêng luôn trả 200, liveness chưa chắc phát hiện. Vì vậy phải kết hợp latency, queue và request errors để quan sát tình trạng thực.

### 7.2. Readiness trong ứng dụng Java

Ví dụ:

    ready =
      applicationInitialized
      AND essentialWarmupComplete
      AND configurationValid
      AND NOT draining
      AND requiredLocalCapacityAvailable

Đây là một công thức tư duy, không phải thuật toán chung.

Cần tránh điều kiện kiểu “ready chỉ khi tất cả 20 downstream đều trả 200”. Một service ngoài lỗi toàn vùng có thể khiến mọi replica NotReady. Nếu điều kiện không phục vụ được chỉ ảnh hưởng API riêng, nên xử lý ở chính API bằng timeout, fallback hoặc lỗi tạm thời theo hợp đồng.

### 7.3. Thông báo readiness khi shutdown

Một framework có thể cập nhật readiness khi bắt đầu shutdown. Nhưng không nên suy rằng data plane đã ngừng route ngay lập tức. Ứng dụng cần ngừng nhận công việc mới ở thời điểm phù hợp, xử lý các request đã vào và giữ trạng thái nghiệp vụ đúng khi connection bị đóng.

## 8. Startup và warm-up bắt buộc

Một instance có thể đã mở port nhưng chưa xử lý đúng nghiệp vụ. Ví dụ:
- Bảng quy đổi đơn vị hoặc chính sách tính phí chưa nạp.
- Kết nối dữ liệu bắt buộc chưa được thiết lập.
- Secret hoặc chứng chỉ phải có chưa khả dụng.
- Một mô hình tìm kiếm cục bộ chưa được nạp.
- Dữ liệu cấu hình cần version tối thiểu.

Nên phân loại bước khởi tạo:

| Loại | Ví dụ | Tác động readiness |
|---|---|---|
| Bắt buộc để kết quả đúng | Chính sách tính phí cần thiết | Chặn Ready cho đến khi hoàn tất |
| Tối ưu hiệu năng | Cache dữ liệu có fallback | Có thể warm nền nếu request vẫn đúng |
| Công việc dài không cần HTTP chờ | Backfill báo cáo lớn | Tách job riêng |
| Migration schema | Thay đổi cấu trúc dữ liệu | Lên kế hoạch triển khai tương thích, không chỉ chặn probe |
| Kết nối dependency tùy chọn | Recommendation provider | Không nhất thiết chặn Ready |

Cold start của Java có thể tăng khi CPU bị giới hạn, ứng dụng phải tải nhiều class hoặc nhiều replica khởi động cùng lúc. Cần đo ở môi trường có resource limit thực tế, không chỉ trên laptop.

### 8.1. Đừng dùng readiness để che migration không tương thích

Nếu Pod mới yêu cầu schema mới còn Pod cũ không hoạt động với schema ấy, readiness chỉ quyết định ai nhận traffic, không tự xử lý tương thích dữ liệu. Nên dùng chiến lược expand–migrate–contract hoặc một migration plan được điều phối, để hai phiên bản có thể cùng chạy trong rolling update khi cần.

### 8.2. Tránh restart loop lúc startup

Nếu cold start thường mất 40 giây, liveness kiểm tra từ giây 5 và restart sau ba lần lỗi cách nhau 5 giây, ứng dụng có thể không bao giờ được khởi tạo xong. Startup probe với ngân sách riêng là cơ chế phù hợp hơn.

## 9. Rolling update và điểm đưa instance vào pool

Một rollout mong muốn:
1. Phiên bản cũ đang Ready.
2. Phiên bản mới được tạo ở trạng thái chưa Ready.
3. Khởi tạo và warm-up hoàn tất.
4. Readiness mới thành công.
5. Endpoint mới được đưa vào tập routing.
6. Nền tảng giảm các instance cũ theo chiến lược rolling.
7. Các instance cũ draining và thoát sau khi hoàn tất công việc.

Trong Kubernetes Deployment:
- maxSurge cho phép tạo thêm Pod trong giai đoạn rollout.
- maxUnavailable giới hạn số Pod không khả dụng theo cách tính của Deployment.
- minReadySeconds có thể yêu cầu Pod ổn định ở trạng thái Ready một khoảng trước khi được tính Available.

Ví dụ replicas=3, maxSurge=1, maxUnavailable=0 hướng tới giữ đủ số Pod khả dụng trong rolling update. Nhưng nó **không bảo đảm zero-downtime tuyệt đối**: một lỗi chung ở database, request quá dài hoặc proxy chưa cập nhật endpoint vẫn có thể gây lỗi.

### 9.1. Canary và blue-green

Readiness chỉ là điều kiện vận hành tối thiểu; không chứng minh mọi chức năng nghiệp vụ đúng. Với canary, cần theo dõi thêm:
- HTTP 5xx và request timeout theo phiên bản.
- Latency p95/p99.
- Sai lệch business metrics.
- Retry và circuit breaker activation.
- CPU/GC/thread/connection saturation.
- Lỗi serialize/deserialize và compatibility.
- Tỷ lệ Pod Ready cùng thời gian startup.

Một phiên bản có thể trả 200 trên /readyz nhưng tính phí sai. Canary và kiểm thử nghiệp vụ mới hỗ trợ phát hiện thay đổi loại này.

## 10. Graceful shutdown và draining

Khi scale down, rollout hoặc thu hồi Pod, mục tiêu là **ngừng nhận request mới trước khi tiến trình không còn phục vụ**, đồng thời xử lý in-flight requests.

Một timeline logic:

    T0  Quyết định terminate một instance
    T1  Đánh dấu instance đang draining / NotReady
    T2  Thay đổi endpoint lan đến các router
    T3  Ngừng nhận request mới theo khả năng
    T4  Hoàn tất hoặc bàn giao các request còn chạy
    T5  Đóng tài nguyên và thoát trong grace period

Thứ tự tín hiệu thực tế trong Kubernetes phụ thuộc vòng đời Pod, hook và cách framework nhận SIGTERM. Do đó cần kiểm tra bằng traffic thật.

### 10.1. Tại sao vẫn có request tới Pod NotReady?

- Request đã được route trước khi readiness đổi.
- Sidecar/Ingress chưa cập nhật danh sách endpoint.
- Client giữ connection cũ hoặc cache DNS.
- Traffic đi trực tiếp Pod IP, bỏ qua Kubernetes Service.
- Nền tảng định tuyến có cơ chế/cấu hình riêng.

Vì vậy receiver phải xử lý an toàn những request đến muộn. Readiness false không hứa “không còn byte nào tới từ bây giờ”.

### 10.2. SIGTERM và shutdown

Một Java service khi shutdown nên:
- Chuyển sang trạng thái không nhận thêm tác vụ mới.
- Phản ánh readiness phù hợp nếu có cơ chế.
- Cho request đã nhận hoàn thành trong giới hạn.
- Flush hoặc duy trì outbox/transaction theo trạng thái đã commit.
- Đóng kết nối database, HTTP client và worker trong thứ tự an toàn.
- Thoát trước khi grace period hết khi khả thi.

Với Spring Boot, graceful shutdown hỗ trợ hoàn tất những request đang xử lý theo giới hạn. Nhưng còn phải phối hợp với terminationGracePeriodSeconds, routing propagation và request deadlines.

### 10.3. preStop không phải giải pháp duy nhất

Một preStop hook có thể kích hoạt draining hoặc tạo khoảng đệm cho cập nhật endpoint. Nhưng một lệnh sleep đơn giản không chứng minh ứng dụng đã NotReady, và thời gian chạy hook dùng vào ngân sách chấm dứt.

Nếu chỉ thêm sleep 5 giây mà ứng dụng vẫn nhận request mới, độ trễ shutdown tăng nhưng lỗi có thể vẫn còn. Hãy xác định chính xác khi nào instance rút khỏi routing và khi nào server bắt đầu đóng listener.

### 10.4. Request dài và streaming

Với WebSocket, SSE, gRPC stream hoặc upload dài, không thể luôn chờ cho tới khi mọi connection tự kết thúc. Cần:
- Thời hạn tối đa hoặc chính sách kết thúc stream.
- Cơ chế reconnect/resume.
- Operation ID, offset hoặc trạng thái bền vững nếu cần phục hồi.
- Idempotency khi client gửi lại.
- Đường cleanup tài nguyên.
- Giới hạn grace period không kéo dài vô hạn.

Nếu một yêu cầu nghiệp vụ thường kéo dài nhiều phút, nên cân nhắc biến thành job bất đồng bộ thay vì giữ HTTP connection trên một Pod có thể bị thu hồi.

## 11. Khi dependency chung lỗi: đừng tự loại mọi replica

Giả sử 20 Order Pod cùng gọi Payment. Nếu readiness của mọi Order Pod yêu cầu Payment trả 200 trong 200 ms, khi Payment down:
1. Cả 20 Pod cùng chuyển NotReady.
2. Kubernetes Service có thể không còn Ready endpoints.
3. Những API Order không cần Payment cũng mất khả năng phục vụ.
4. Health probes tiếp tục đập vào Payment đang lỗi.
5. Khi Payment phục hồi, 20 Pod cùng khởi động lại luồng traffic gây spike.

Cần phân biệt:
- Liveness không phụ thuộc Payment.
- Readiness phản ánh khả năng phục vụ các đường vào chính.
- API phụ thuộc Payment có thể trả PENDING/UNAVAILABLE hoặc dùng circuit breaker.
- Các chức năng chỉ đọc hoặc có fallback vẫn phục vụ.
- Metric/dashboard công bố tình trạng Payment degraded.

### 11.1. Broker tạm unavailable

Nếu Order dùng transactional outbox, request có thể ghi thay đổi cục bộ và bản ghi cần phát trong cùng transaction. Publisher gửi sự kiện khi broker phục hồi. Vì vậy broker down tạm thời có thể làm backlog tăng nhưng không nhất thiết khiến Order không thể nhận mọi command.

Nếu backlog vượt ngưỡng an toàn hoặc nghiệp vụ cần xác nhận sự kiện ngay, chính sách có thể khác. Cần quyết định theo **cam kết nghiệp vụ**, không dùng một mẫu readiness cho tất cả.

### 11.2. Cache tạm unavailable

Nếu Redis chỉ là bộ nhớ đệm, Catalog có thể fallback sang DB. Nhưng fallback đồng loạt có thể tạo cache stampede làm DB quá tải; vì vậy cần giới hạn concurrency, timeout, bulkhead và chính sách degrade. Không cho phép health check chỉ nhìn Redis down rồi tự xóa mọi Catalog Pod khỏi pool mà không xét khả năng phục vụ thực tế.

### 11.3. DB cốt lõi unavailable

Nếu database là điều kiện không thể thiếu cho toàn bộ traffic, readiness có thể cần chuyển trạng thái. Nhưng nếu một số route có thể phục vụ từ dữ liệu cục bộ hoặc projection, việc rút mọi Pod khỏi pool có thể làm mất các chức năng vẫn hữu ích.

Khi không thể đáp ứng bất biến, command phải từ chối hoặc chờ theo hợp đồng; không dùng dữ liệu cache để giả vờ đã commit.

## 12. Overload, backpressure và health-based routing

Một instance có thể Live và Ready nhưng quá tải do:
- Thread pool bận hết.
- Connection pool đang xếp hàng dài.
- GC pause và CPU throttling.
- Downstream chậm giữ nhiều request in-flight.
- Queue nội bộ không giới hạn.
- Retry storm.

Chuyển NotReady ngay khi tải tăng có thể làm các instance còn lại nhận nhiều traffic hơn và tiếp tục quá tải. Các công cụ bổ trợ:
- Giới hạn số request đồng thời.
- Rate limiting và admission control.
- Queue có kích thước tối đa.
- Timeout/deadline phù hợp.
- Bulkhead theo dependency.
- Circuit breaker và retry có backoff/jitter.
- Autoscaling theo metric phù hợp.
- Load shedding cho yêu cầu không ưu tiên.
- Fallback có ngữ nghĩa đúng.

Readiness không thay thế năng lực phục vụ và SLO. Một cluster có 4 Pod Ready vẫn có thể thiếu capacity cho đợt sale lớn.

### 12.1. Hysteresis và chống flapping

Readiness flapping là đổi UP/DOWN nhiều lần khi tải dao động nhẹ. Có thể giảm bằng:
- failureThreshold và successThreshold phù hợp.
- Đo theo cửa sổ hoặc điều kiện trạng thái ổn định.
- Cool-down khi cần.
- Không dùng một lần gọi dependency ngẫu nhiên làm điều kiện duy nhất.
- Chỉ đổi trạng thái khi thực sự có ý nghĩa cho quyết định routing.

Cân bằng giữa phát hiện lỗi sớm và tránh chuyển trạng thái quá nhiều. Một probe quá lỏng che sự cố, một probe quá nhạy tự tạo churn.

## 13. Service mesh, registry và cloud load balancer

### 13.1. Registry-based discovery

Với registry như Consul/Eureka hoặc tương đương, health có thể gắn với heartbeat, lease, active check hoặc trạng thái do service báo. Consumer có thể cache danh sách; khi deregister, cập nhật không đồng thời.

Đừng giả định các registry này có cùng ngữ nghĩa với liveness/readiness/startup của Kubernetes. Phải xác định chính xác check và trạng thái instance trong hệ thống đang sử dụng.

### 13.2. Cloud load balancer

Một LB có thể kiểm tra TCP hoặc HTTP target. TCP check đôi khi cho phép instance vào pool trước khi application ready. Khi cần warm-up, nên dùng HTTP health path phản ánh readiness theo đúng hợp đồng.

Cũng cần cấu hình deregistration delay/connection draining tương ứng với request in-flight và vòng đời instance, tránh rút backend quá nhanh.

### 13.3. Service mesh

Service mesh có thể định tuyến theo phiên bản, thực hiện timeout, retry và outlier detection. Mesh nhìn tỷ lệ lỗi request và có thể tạm loại endpoint. Đây không nhất thiết là cùng tín hiệu với readiness của ứng dụng.

Cần tránh tầng Gateway, mesh, HTTP client và SDK cùng tự retry nhiều lần gây khuếch đại tải. Readiness không giải quyết một retry storm nếu mọi tầng vẫn gửi request tới các backend còn lại quá mạnh.

### 13.4. Routing theo vùng

Nếu các Pod phân tán nhiều zone, health và locality ảnh hưởng thời gian failover. Khi một zone mất backend Ready, bộ định tuyến có thể chuyển sang zone khác, trả lỗi hoặc áp dụng chính sách riêng. Đo thời gian failover và capacity zone dự phòng; không suy rằng “còn một endpoint Ready ở vùng khác” là đã đáp ứng mọi SLO.

## 14. Bảo mật của health endpoints

Health endpoint thường cần được kubelet/LB gọi tự động, nhưng không nên phơi mọi dữ liệu chẩn đoán ra Internet.

- Chỉ mở đường truy cập cần thiết cho probe.
- Đảm bảo chính sách xác thực phù hợp với caller hạ tầng; nếu cấu hình bắt auth mà kubelet không có credential, probe sẽ luôn thất bại.
- Không đưa password, secret, JDBC URL, thông tin khách hàng hay stack trace vào body.
- Dùng body ngắn, HTTP status rõ.
- Gửi lỗi chi tiết sang log/metrics có phân quyền.
- Hạn chế chi phí của mỗi probe để tránh bị lạm dụng tạo tải.
- Không cho endpoint health thực hiện thay đổi nghiệp vụ.

Ví dụ HTTP response gọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Khi không đạt:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"DOWN"}
~~~

Mã và body cụ thể tùy framework/hợp đồng. Hạ tầng phải được cấu hình để diễn giải đúng trạng thái.

## 15. Observability: đo điều gì để tin health-based routing?

Các metric nên phân biệt **tình trạng của Pod**, **danh sách endpoint thực sự** và **trải nghiệm request**.

| Metric hoặc sự kiện | Câu hỏi trả lời |
|---|---|
| Ready instance count theo version/zone | Còn bao nhiêu backend phục vụ? |
| NotReady/Starting/Terminating count | Vòng đời Pod đang ở đâu? |
| Startup-to-Ready duration | Cold start hoặc warm-up mất bao lâu? |
| Readiness transition count | Có flapping không? |
| Liveness failure/restart count | Có restart storm hoặc liveness quá nhạy? |
| Startup probe failures | Có mắc kẹt khi khởi tạo không? |
| Actual routing endpoint count | Load balancer đã thấy danh sách mới chưa? |
| HTTP 5xx/timeout theo instance | Pod nào đang phục vụ lỗi? |
| Request after draining started | Có request đến muộn không? |
| In-flight requests lúc terminate | Có nguy cơ cắt ngang? |
| Graceful shutdown/forced termination count | Pod có thoát an toàn không? |
| CPU/GC/thread/connection pool saturation | Có quá tải dù Ready? |
| Dependency degraded/fallback rate | Lỗi có phạm vi nào? |
| Traffic split theo version | Canary/rollout có đúng chính sách? |
| Outlier ejection/circuit breaker state | Routing có tự loại endpoint thêm không? |

Một readiness probe thành công không chứng minh API tạo đơn đã xử lý đúng; metric request thật và business event vẫn cần thiết.

### 15.1. Log lý do đổi trạng thái

Nên ghi lý do khi readiness thay đổi, ví dụ:
- INITIALIZING
- WARMUP_NOT_COMPLETE
- LOCAL_RESOURCE_UNAVAILABLE
- DRAINING
- OVERLOAD_POLICY

Không nên log cùng một reason ở mọi lần probe tạo spam. Ghi sự kiện **chuyển trạng thái** và metric riêng cho tình trạng hiện tại sẽ hữu ích hơn.

### 15.2. Cảnh báo mất toàn bộ Ready endpoints

Nếu một Pod NotReady nhưng nhiều Pod khác còn phục vụ, mức tác động khác với không còn endpoint nào. Cần alert phân biệt:
- Một instance lỗi.
- Tỷ lệ Ready thấp hơn capacity cần thiết.
- Toàn pool không còn Ready endpoints.
- Readiness flapping trên toàn bộ deployment.
- 5xx tăng trong rollout hoặc scale down.

Một cảnh báo “health=DOWN” không có ngữ cảnh có thể gây nhiều tiếng ồn mà ít giá trị vận hành.

## 16. Kiểm thử phải có hạ tầng định tuyến thật

### 16.1. Cold start và warm-up

1. Khởi động một Pod, cố ý trì hoãn bước warm-up bắt buộc.
2. Kiểm tra readiness chưa đạt dù process đã mở cổng.
3. Kiểm tra Kubernetes Service/LB không chọn instance đó theo chính sách.
4. Hoàn tất warm-up; readiness thành công.
5. Quan sát endpoint mới xuất hiện trong pool.
6. Gửi request nghiệp vụ đầu tiên và kiểm tra kết quả.

### 16.2. Lỗi dependency tùy chọn

1. Cho Redis hoặc Recommendation Service trả lỗi.
2. Xác nhận liveness không thất bại vô ích.
3. Những endpoint không phụ thuộc vẫn hoạt động.
4. Endpoint phụ thuộc sử dụng fallback hoặc lỗi theo hợp đồng.
5. Không có restart storm và không mất toàn bộ Ready endpoints nếu policy không yêu cầu.

### 16.3. Liveness khi tiến trình hỏng thật

1. Gây lỗi không thể phục hồi có kiểm soát trong môi trường thử.
2. Kiểm tra liveness thất bại đủ ngưỡng.
3. Container được restart.
4. Trong lúc khởi động lại, instance không nhận traffic trước khi Ready.
5. Sau phục hồi, endpoint trở lại pool.

Không nên tiến hành thử nghiệm làm mất dữ liệu hoặc payment thật trong sản xuất nếu không có kế hoạch phù hợp.

### 16.4. Rolling update dưới tải

1. Gửi traffic liên tục vào Service/Gateway.
2. Deploy phiên bản mới có warm-up giả lập.
3. Theo dõi Request 2xx/5xx, latency và Ready endpoint counts.
4. Không gửi traffic mới đến phiên bản chưa Ready qua đường kiểm tra.
5. Khi Pod cũ terminating, ghi nhận request in-flight và lỗi.
6. Xác định request đến muộn là do route đã chọn trước, endpoint propagation, keep-alive hay bypass Service.

### 16.5. Scale down và shutdown

1. Tạo request có thời gian xử lý ngắn và dài.
2. Bắt đầu scale down.
3. Quan sát readiness/draining/SIGTERM/endpoint removal.
4. Xác nhận request đã commit không mất sự kiện/outbox.
5. Kiểm tra trường hợp grace period hết và Pod bị buộc dừng.
6. Client có idempotency hoặc cơ chế resume để thử lại an toàn.

### 16.6. Lỗi chung và quá tải

Gây tình huống Payment down 30 giây, database chậm hoặc CPU throttling:
- Có bao nhiêu Pod chuyển NotReady?
- Có Pod nào restart vô ích?
- API không phụ thuộc có tiếp tục phục vụ?
- Không còn backend gây lỗi hàng loạt?
- Khi phục hồi có thác traffic cùng lúc?
- Hysteresis/retry/backpressure có hoạt động như thiết kế?

## 17. Hai ví dụ phân tích sự cố

### 17.1. Mọi Pod Ready nhưng POST /orders timeout

Giả sử Order có bốn Pod và readiness chỉ kiểm tra Spring đã khởi tạo. PostgreSQL chậm bất thường. Tất cả Pod vẫn Ready nhưng thread đang chờ DB, dẫn đến timeout.

Hai giải pháp cực đoan đều nguy hiểm:
- Giữ mọi request vô hạn vì Pod Ready, làm cạn thread pool.
- Rút tất cả Pod khỏi Service ngay vì database chậm, làm mất cả GET không cần DB.

Hướng xử lý có kiểm soát:
- Liveness độc lập với lỗi DB tạm thời.
- Readiness phản ánh khởi tạo/draining/tài nguyên cục bộ và chính sách cần thiết.
- API ghi dùng transaction timeout, admission control và error contract phù hợp.
- API đọc có thể tiếp tục nếu vẫn đảm bảo ý nghĩa và bảo mật.
- Dashboard thể hiện DB degraded, số request từ chối và queue.
- Chỉ đánh NotReady khi instance không thể phục vụ loại traffic được định tuyến theo policy đã thống nhất.

### 17.2. Pod Terminating vẫn có 502/503

Một rolling deployment có readiness đầy đủ nhưng vẫn có lỗi ngắn khi Pod bị thu hồi. Các nguyên nhân:
- Ingress/mesh cập nhật endpoint chậm.
- Connection keep-alive đã tạo trước.
- Ứng dụng đóng listener khi vẫn còn in-flight request.
- Termination grace không đủ.
- Tác vụ dài không có resume/idempotency.
- Một bộ định tuyến ngoài không dùng readiness.

Cách điều tra:
1. So sánh timestamp Pod deletion, readiness transition, EndpointSlice update, SIGTERM và lỗi request.
2. Xem connection nào đã có trước mốc rút endpoint.
3. Kiểm tra Spring graceful shutdown và giới hạn grace period.
4. Nếu cần, chủ động draining trước khi terminate theo cơ chế phù hợp.
5. Thử lại rollout dưới traffic liên tục và phân biệt lỗi đến muộn với lỗi từ Pod mới chưa warm.

Không nên chỉ tăng grace period mà không xác định nguyên nhân.

## 18. Các sai lầm thiết kế phổ biến

**“Pod Running là Ready.”** Sai. Pod có thể còn warm-up hoặc chưa đủ điều kiện phục vụ.

**“Liveness và readiness chỉ cần cùng một /health.”** Không nên nếu điều đó khiến lỗi dependency tạm thời gây restart hoặc startup chưa xong đã nhận traffic.

**“Readiness fail sẽ restart.”** Không phải chức năng trực tiếp của readiness probe.

**“Port 8080 mở nghĩa là endpoint nghiệp vụ hoạt động.”** Không chắc; cần kiểm tra các bước khởi tạo cần thiết.

**“Liveness phải ping tất cả downstream.”** Có thể gây restart storm khi một dependency chung lỗi.

**“Readiness false thì mọi request dừng tức thì.”** Sai; route propagation và connection cũ có độ trễ.

**“Một probe trả 200 chứng minh chất lượng business API.”** Sai; cần contract/integration/canary tests.

**“Thêm preStop sleep là zero downtime.”** Không: sleep không tự đảm bảo NotReady, drain và xử lý in-flight.

**“Càng nhiều health query sâu càng tốt.”** Không: health endpoint nặng có thể tự gây tải hoặc làm tăng độ nhạy vô ích.

**“Mọi Pod Ready nghĩa là có đủ capacity.”** Không: throughput còn phụ thuộc CPU, DB, pool, traffic và sự phân phối latency.

**“HPA tạo thêm Pod sẽ chữa lỗi readiness.”** Không nếu lỗi chung nằm ở cấu hình hoặc dependency.

**“Một API phụ thuộc bị lỗi thì cả service phải NotReady.”** Không tự động; cần xét phạm vi ảnh hưởng và đường phục vụ thực tế.

## 19. Quy trình quyết định health-based routing

### Bước 1 — Xác định loại traffic

Instance phục vụ command, query, stream, job hay nhiều loại? Mọi endpoint có cùng phụ thuộc không? Router chọn đích theo Pod, service hay API group?

### Bước 2 — Viết điều kiện readiness có thể kiểm thử

Ví dụ: “Instance Order Ready khi khởi tạo thành công, quy tắc phí bắt buộc đã nạp, cấu hình hợp lệ, chưa draining và có khả năng nhận thêm request theo policy cục bộ.”

Tránh câu mơ hồ “mọi dependency phải xanh”.

### Bước 3 — Thiết kế liveness riêng

Chỉ đưa những lỗi nội bộ mà restart có ích vào liveness. Chọn timeout/threshold có cân nhắc pause/GC và lịch trình CPU thực tế.

### Bước 4 — Thiết kế startup

Đo cold start p95/p99, xác định warm-up bắt buộc và cửa sổ startup. Không dùng initialDelay tùy tiện để che thời gian khởi tạo biến thiên khi startup probe phù hợp hơn.

### Bước 5 — Chọn điểm health trong đường routing

Xác nhận Gateway, Service, EndpointSlice, Ingress, mesh, client-side discovery và connection cache có thật sự tôn trọng readiness hoặc health do nguồn nào cung cấp.

### Bước 6 — Thiết kế drain

Xác định thời điểm NotReady, dừng request mới, cách xử lý in-flight, SIGTERM/preStop/grace period và việc phục hồi tác vụ bị ngắt.

### Bước 7 — Thiết kế khi dependency chung lỗi

Chọn fallback, circuit breaker, rate limit, trạng thái degraded và chính sách NotReady sao cho không loại tất cả replica vì một lỗi không thể sửa bằng đổi instance.

### Bước 8 — Đo và thử lỗi

Gây cold start, dependency outage, overloaded instance, rollout và scale down. Đo request 5xx/timeout, endpoint propagation, restart, Ready counts, warm-up và shutdown.

## 20. Mẫu ADR

~~~text
ADR: Health checks và routing cho <service>

Bối cảnh và năng lực:
Hạ tầng: Kubernetes Service, Ingress, mesh, registry, LB...
Loại request được định tuyến:
SLO và capacity mục tiêu:

Health contracts:
  Liveness: điều kiện, endpoint, cổng, ngưỡng:
  Readiness: điều kiện, endpoint, cổng, ngưỡng:
  Startup: điều kiện, endpoint, cổng, ngưỡng:

Warm-up:
  Công việc bắt buộc trước Ready:
  Công việc tối ưu có thể chạy nền:
  Cold start p95/p99:

Dependency policy:
  Dependency nào thực sự chặn Ready:
  Dependency nào chỉ báo degraded:
  Fallback/circuit breaker/load shedding:
  Hành vi khi mọi replica cùng lỗi:

Discovery/routing:
  Nguồn Ready endpoints:
  DNS/registry/proxy caching:
  Độ trễ endpoint propagation:
  Hành vi khi không còn backend:

Rollout:
  maxSurge/maxUnavailable/minReadySeconds:
  Canary, rollback và metric:

Shutdown:
  Readiness/draining sequence:
  preStop/SIGTERM:
  Termination grace:
  In-flight request, stream và idempotency:

Security:
  Quyền gọi probe:
  Thông tin được phép công bố:

Observability:
  Ready count/restarts/5xx/latency:
  Reasons, alerts, dashboards:

Các test bắt buộc:
Owner, rủi ro và ngày đánh giá lại:
~~~

## 21. Bài thực hành: Order Service trên Kubernetes

Một nền tảng thương mại điện tử chạy bốn Pod Order bằng Spring Boot.

Giả định:
- Cold start từ 15 đến 45 giây.
- Port 8080 mở trước khi cache quy tắc tính phí nạp xong 12 giây.
- POST /orders cần PostgreSQL.
- GET lịch sử đơn có thể dùng read model.
- Email được gửi từ transactional outbox.
- Redis chỉ dùng làm cache tùy chọn.
- Payment có thể lỗi 30 giây.
- p99 POST /orders bình thường là 1.200 ms.
- Scale down đôi lúc có 502/503.
- Đội hiện dùng /health kiểm tra PostgreSQL, Redis, Payment và broker cho cả liveness/readiness; không có startup probe, termination grace 10 giây.

**Yêu cầu thực hành:**
1. Phân tích vì sao /health chung có nguy cơ gây restart storm.
2. Đề xuất ba hợp đồng riêng cho liveness, readiness và startup.
3. Xác định bước warm-up bắt buộc và bước có thể chạy nền.
4. Viết manifest Deployment có startupProbe, readinessProbe, livenessProbe cùng ngưỡng phù hợp.
5. Giải thích vì sao Redis/Broker không nhất thiết nằm trong readiness khi có fallback/outbox.
6. Khi PostgreSQL lỗi toàn vùng, các API nào có thể còn hoạt động? Trạng thái nào phải trả cho command chưa thể xử lý?
7. Thiết kế sequence draining/NotReady/SIGTERM/terminationGracePeriodSeconds để giảm 502/503.
8. Nêu cách phân biệt lỗi do Pod mới chưa sẵn sàng và lỗi do Pod cũ bị dừng quá nhanh.
9. Thiết kế sáu metric cho startup, readiness flapping, Ready endpoints, liveness restarts, 5xx và draining.
10. Lập ba bài thử: cold start, Payment outage, rolling deployment dưới traffic liên tục.
11. Viết ADR ngắn giải thích tại sao liveness không phụ thuộc Payment và readiness không thay thế timeout/circuit breaker.

### Một hướng tiếp cận

Startup probe dành ngân sách cho 45 giây cold start cùng biên an toàn. Readiness chỉ đạt sau khi khởi tạo và nạp quy tắc phí bắt buộc, cấu hình cục bộ hợp lệ và instance chưa draining. Liveness không phụ thuộc Payment/Redis/Broker nên một lỗi ngoài không khiến tất cả Pod restart.

Khi Payment không khả dụng, các command phụ thuộc có thể trả trạng thái PENDING/UNAVAILABLE hoặc xử lý qua workflow được định nghĩa; các API không phụ thuộc vẫn hoạt động. Trong rollout, endpoint mới chỉ nhận traffic sau Ready, endpoint cũ được draining có giới hạn. Các request đến muộn vẫn cần được xử lý an toàn, không chỉ dựa vào lời hứa zero downtime.

## 22. Ghi nhớ

1. **Liveness** để đánh giá khả năng cần restart; **readiness** để quyết định route traffic mới; **startup** để quản lý cửa sổ khởi tạo.
2. Một process chạy hoặc cổng mở chưa chứng minh service đủ khả năng xử lý nghiệp vụ.
3. Readiness chỉ nên bao gồm những điều kiện thực sự cần cho traffic của pool, không mặc định kiểm tra mọi downstream.
4. Thay đổi readiness cần thời gian lan đến registry/load balancer; connection cũ và in-flight request vẫn có thể đến.
5. Startup và warm-up thiết yếu phải hoàn thành trước khi đưa instance mới vào pool.
6. Lỗi dependency chung không nên gây restart storm hoặc làm toàn bộ replica tự loại nếu điều đó không cải thiện khả năng phục vụ.
7. Timeout, circuit breaker, bulkhead, admission control, retry có giới hạn và autoscaling bổ trợ health checking.
8. Draining, graceful shutdown và termination grace phải được kiểm thử dưới traffic thực.
9. Health endpoint cần nhẹ, an toàn và có ngữ nghĩa rõ; metric và tracing giải thích nguyên nhân sự cố.
10. **Mục tiêu kiến trúc là đưa request đến instance có thể phục vụ, loại instance chưa sẵn sàng một cách có kiểm soát và tránh lỗi dây chuyền trong startup, suy giảm và shutdown.**
