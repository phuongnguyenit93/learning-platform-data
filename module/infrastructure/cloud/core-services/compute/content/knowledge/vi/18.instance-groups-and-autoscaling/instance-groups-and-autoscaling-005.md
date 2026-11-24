# Warmup, cooldown và thời gian máy mới sẵn sàng

## Mục tiêu bài học

Khi nhóm máy hoặc cụm compute tự động mở rộng, một instance mới không thể phục vụ tải ngay khi nhà cung cấp báo trạng thái đã khởi chạy. Máy còn phải boot hệ điều hành, hoàn tất bootstrap, lấy cấu hình và secret, khởi động ứng dụng, nạp dữ liệu cần thiết, thiết lập kết nối phụ thuộc và vượt qua health check. Với ứng dụng Java, quá trình JIT compilation và tạo cache còn có thể khiến hiệu năng ban đầu thấp hơn trạng thái ổn định.

Warmup và cooldown giúp hệ thống co giãn tính đến khoảng trễ này. Cấu hình sai có thể khiến autoscaler đánh giá thiếu hoặc thừa công suất, tạo thêm máy liên tục, scale-in quá sớm hoặc đưa traffic tới instance chưa sẵn sàng.

Sau bài học này, bạn có thể:

- Phân biệt thời gian launch, boot, bootstrap, application startup và readiness.
- Giải thích warmup ở cấp instance, ứng dụng và bộ điều khiển autoscaling.
- Phân biệt cooldown với startup delay và stabilization window.
- Thiết kế health check, readiness gate và traffic ramp-up.
- Đo thời gian máy mới sẵn sàng bằng metric và event.
- Chọn cấu hình warmup/cooldown theo workload và scaling policy.
- Xử lý tình huống máy mới khởi động chậm, health check thất bại hoặc scale dao động.

## 1. Vì sao máy mới không phục vụ tải ngay lập tức?

Trong cloud, lệnh tạo VM hoặc thêm node chỉ khởi đầu vòng đời tài nguyên. Nhà cung cấp cần cấp phát compute, gắn network và storage, khởi động máy; sau đó guest OS và workload tiếp tục các bước khởi tạo riêng.

Một instance có thể ở trạng thái đang chạy nhưng ứng dụng chưa thể xử lý request. Ví dụ:

- Cloud-init hoặc startup script còn cài package và tải cấu hình.
- Agent bảo mật, monitoring hoặc logging chưa đăng ký xong.
- Ứng dụng đang migrate schema, tải model hoặc đọc dữ liệu khởi tạo.
- Java đang load class, JIT compile và tạo connection pool.
- Cache còn lạnh nên request đầu tiên chậm hơn bình thường.
- Load balancer chưa đánh dấu target healthy.
- Network route, DNS hoặc service discovery chưa cập nhật.

Nếu autoscaler cộng instance vào capacity ngay sau khi VM được tạo, hệ thống có thể cho rằng đã có đủ năng lực trong khi máy mới chưa xử lý được request. Nếu traffic được chuyển tới quá sớm, người dùng có thể gặp timeout và lỗi. Nếu autoscaler không tính đúng thời gian máy mới sẵn sàng, nó có thể tiếp tục scale-out trong lúc những máy vừa tạo đang khởi động, dẫn tới dư công suất sau đó.

## 2. Phân biệt các mốc thời gian trong vòng đời instance

Nên đo riêng từng giai đoạn thay vì dùng một giá trị chung mang tên startup time.

| Mốc | Ý nghĩa | Sự kiện có thể dùng |
|---|---|---|
| Provisioning | Nhà cung cấp cấp phát instance, NIC, volume và metadata | Create/launch request và instance state |
| OS boot | Firmware, kernel và hệ điều hành khởi động | Boot timestamp, cloud-init start |
| Bootstrap | Cài agent, lấy cấu hình, secret, chứng thư và package | Bootstrap start/end |
| Application startup | Tiến trình ứng dụng khởi động, load class và cấu hình | Process start, application startup event |
| Dependency ready | Pool database, message broker, DNS hoặc cache đã sẵn sàng | Connection pool initialized, dependency probe |
| Readiness | Instance đủ điều kiện nhận traffic | Readiness check thành công |
| Traffic warmup | Instance tăng dần khả năng xử lý sau khi nhận traffic | Request rate, latency và error rate |
| Steady state | Hiệu năng và metric đạt trạng thái vận hành bình thường | SLO, throughput và resource baseline |

**Time to launch** thường chỉ đo từ yêu cầu tạo instance đến trạng thái cloud báo máy đã khởi chạy.

**Time to ready** đo từ lúc bắt đầu tạo máy đến lúc máy vượt qua điều kiện sẵn sàng phục vụ.

**Time to first successful request** đo tới request nghiệp vụ đầu tiên được xử lý thành công.

Ba số liệu này có thể khác nhau đáng kể. Đối với autoscaling dịch vụ, time to ready và thời gian để đạt throughput ổn định thường quan trọng hơn trạng thái máy đã chạy.

~~~mermaid
flowchart LR
    A["Create instance"] --> B["Provisioning"]
    B --> C["OS boot"]
    C --> D["Bootstrap"]
    D --> E["Application startup"]
    E --> F["Dependency checks"]
    F --> G["Readiness passed"]
    G --> H["Receive traffic"]
    H --> I["Traffic warmup"]
    I --> J["Steady state"]
~~~

## 3. Warmup là gì?

Warmup là khoảng thời gian workload hoặc instance cần để đạt trạng thái hoạt động ổn định sau khi khởi động hoặc sau khi nhận tải.

Từ này được dùng ở nhiều lớp:

1. **Infrastructure warmup:** máy ảo hoặc node hoàn tất boot và bootstrap.
2. **Application warmup:** ứng dụng hoàn tất startup, nạp class, tạo pool và chuẩn bị dữ liệu.
3. **Runtime warmup:** JVM, JIT compiler, cache và các runtime component đạt hiệu năng ổn định.
4. **Autoscaling instance warmup:** khoảng thời gian bộ điều khiển autoscaling tạm thời chưa xem metric của instance mới là đại diện cho capacity ổn định, theo quy tắc của nền tảng.
5. **Traffic warmup:** tăng dần lượng request gửi tới instance mới thay vì đưa toàn bộ tải vào ngay lập tức.

Những khoảng thời gian này có thể chồng lấp nhưng không đồng nghĩa với nhau. Một instance có thể đã vượt readiness nhưng vẫn cần thêm thời gian để cache nóng hoặc JIT compile. Ngược lại, một instance đã hoàn tất runtime warmup nhưng chưa được load balancer đưa vào target group.

### 3.1. Warmup không phải một hằng số

Thời gian warmup phụ thuộc:

- Loại instance, CPU generation, storage và network.
- OS image, package, agent và startup script.
- Kích thước ứng dụng, dependency và dữ liệu phải nạp.
- JVM version, heap, collector và mức JIT compilation.
- Tình trạng database, broker, registry và secret service.
- Tải đang có, số instance khởi động đồng thời và giới hạn API.
- Availability Zone, image cache và trạng thái hạ tầng tại thời điểm tạo.

Vì vậy, không nên đặt warmup theo một con số mặc định rồi giữ nguyên mãi. Hãy đo trên các nhóm instance và release đại diện, sau đó xem phân phối p50, p95 và p99.

### 3.2. Ví dụ timeline

Giả sử một web service cần khoảng thời gian sau trong một lần scale-out:

| Giai đoạn | Thời gian minh họa | Trạng thái |
|---|---:|---|
| Provision và OS boot | 35 giây | VM đang khởi động |
| Bootstrap và agent | 25 giây | Chưa nhận traffic |
| Application startup | 20 giây | Process đang khởi động |
| Dependency/readiness | 10 giây | Kiểm tra điều kiện phục vụ |
| Runtime/traffic warmup | 30 giây | Nhận traffic có kiểm soát |
| Tổng đến trạng thái ổn định | 120 giây | Capacity mới đạt mức dự kiến |

Đây chỉ là ví dụ minh họa, không phải thời gian chuẩn của cloud. Nếu bộ điều khiển autoscaling dùng 120 giây làm instance warmup, cần hiểu rõ nền tảng bắt đầu tính từ event nào và metric nào bị loại khỏi đánh giá trong thời gian đó.

## 4. Application warmup: những việc cần hoàn tất

Ứng dụng nên có quy trình startup xác định rõ điều kiện nào bắt buộc trước khi nhận request.

Các công việc phổ biến:

- Đọc cấu hình và xác minh cấu hình hợp lệ.
- Lấy secret/certificate qua identity được cấp cho instance.
- Khởi tạo thread pool và giới hạn concurrency.
- Tạo connection pool tới database hoặc message broker.
- Nạp metadata, schema, model hoặc bảng tra cứu cần thiết.
- Khởi tạo cache nền hoặc precompute dữ liệu thiết yếu.
- Đăng ký service discovery và telemetry.
- Xác minh phiên bản ứng dụng tương thích với dependency.
- Mở readiness endpoint sau khi các bước bắt buộc hoàn tất.

Không phải mọi tác vụ đều phải chặn readiness. Ví dụ, tải dữ liệu phân tích phụ hoặc làm nóng cache không thiết yếu có thể chạy nền nếu ứng dụng vẫn phục vụ an toàn với cache miss. Ngược lại, nếu request cần model hoặc schema bắt buộc, readiness nên chờ cho đến khi tài nguyên đó sẵn sàng.

### 4.1. Tránh startup script quá dài

Startup script nên thực hiện các bước tối thiểu, có thể lặp lại và có timeout:

- Dùng image đã chuẩn bị sẵn để giảm cài đặt lúc boot.
- Tải artifact có version hoặc digest rõ ràng.
- Tránh tải dependency không cố định từ Internet mỗi lần scale-out.
- Retry có backoff và giới hạn tổng thời gian.
- Ghi log theo từng bước để phân biệt lỗi bootstrap và lỗi ứng dụng.
- Không lưu secret trong image hoặc log.
- Đảm bảo script chạy lại không tạo cấu hình hoặc tài nguyên trùng lặp.

Nếu startup phụ thuộc package repository hoặc registry, cần đo thời gian và xử lý khi dịch vụ đó chậm. Một đợt scale-out lớn có thể khiến hàng chục instance cùng tải artifact, gây nghẽn chính dependency mà chúng cần để trở nên sẵn sàng.

### 4.2. Warmup JVM và JIT

Đối với Java, JVM có thể cần thời gian để:

- Load class và khởi tạo framework.
- JIT compile các method được gọi thường xuyên.
- Tạo connection pool và cache.
- Đi qua một số chu kỳ GC ban đầu.
- Tích lũy profile thực thi để tối ưu code nóng.

Nếu readiness được mở ngay sau khi Spring context hoặc main method hoàn tất, instance vẫn có thể có latency cao trong các request đầu. Có thể dùng một warmup endpoint hoặc synthetic request để gọi các đường xử lý quan trọng trước khi nhận traffic thật.

Warmup request phải an toàn, không tạo side effect nghiệp vụ, không ghi dữ liệu giả vào production và không làm quá tải dependency. Nếu cần thực hiện thao tác ghi, dùng dữ liệu thử nghiệm hoặc transaction được rollback theo thiết kế.

Không nên chạy toàn bộ workload production để làm nóng một instance. Chọn một tập request đại diện, có giới hạn concurrency và timeout.

## 5. Readiness, liveness và startup health check

Health check có vai trò khác nhau. Dùng nhầm loại probe có thể tạo vòng lặp restart hoặc đưa traffic đến máy chưa sẵn sàng.

| Loại kiểm tra | Câu hỏi | Hành động thường gặp |
|---|---|---|
| Startup probe | Ứng dụng đã hoàn thành giai đoạn khởi động chưa? | Cho phép startup kéo dài mà chưa đánh dấu liveness thất bại |
| Readiness probe | Ứng dụng có thể nhận traffic ngay lúc này không? | Thêm hoặc giữ target trong trạng thái nhận traffic khi đạt |
| Liveness probe | Process có còn hoạt động và có thể tự phục hồi không? | Restart khi phát hiện trạng thái không thể phục hồi |

Readiness nên phản ánh khả năng phục vụ request của ứng dụng. Nó có thể kiểm tra các dependency bắt buộc, nhưng tránh gọi quá nhiều hệ thống bên ngoài với mỗi lần probe. Một dependency tạm thời chậm có thể khiến tất cả instance đồng loạt NotReady, tạo ra outage lớn hơn.

Liveness nên kiểm tra trạng thái process hoặc event loop đủ để phát hiện ứng dụng bị treo. Không nên dùng liveness để kiểm tra database hay API bên ngoài, vì dependency lỗi có thể khiến Kubernetes restart toàn bộ Pod liên tục mà không sửa được nguyên nhân.

Startup probe giúp ứng dụng có startup time dài không bị liveness restart quá sớm. Readiness vẫn phải thành công trước khi Pod nhận traffic qua Service.

### 5.1. Ví dụ Kubernetes probes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api:2.1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Trong ví dụ:

- Startup probe cho phép ứng dụng tối đa khoảng 180 giây để qua giai đoạn khởi động theo chu kỳ và failure threshold.
- Readiness probe quyết định Pod có đủ điều kiện nhận traffic qua Service hay không.
- Liveness probe phát hiện process không còn phản hồi theo tiêu chí đã thiết kế.

Các con số cần điều chỉnh theo số liệu startup thực tế. Endpoint health không nên thực hiện truy vấn nặng hoặc tạo side effect.

## 6. Autoscaling instance warmup

Autoscaling cần hiểu instance mới đóng góp bao nhiêu capacity và từ thời điểm nào. Khi một instance vừa được thêm vào nhóm, metric của nó có thể thấp bất thường vì chưa nhận traffic. Nếu bộ điều khiển lấy mức CPU thấp đó để tính capacity trung bình, nó có thể kết luận nhóm đã đủ công suất và dừng scale-out quá sớm.

Instance warmup thường giúp bộ điều khiển xử lý vấn đề này. Tùy dịch vụ, thời gian warmup có thể được dùng để:

- Không đưa metric của instance mới vào phép tính scaling trong khoảng khởi động.
- Không xem capacity mới là đã ổn định cho tới khi hết warmup.
- Điều chỉnh cách tính số instance cần thêm trong các bước scale tiếp theo.
- Tránh scale-in khi instance mới chưa đóng góp đầy đủ metric.

Tên gọi và semantics khác nhau theo cloud provider và loại scaling policy. Ví dụ, một số nền tảng có default instance warmup, estimated instance warmup hoặc warmup gắn với lifecycle state. Phải đọc đúng tài liệu của dịch vụ đang dùng để biết warmup ảnh hưởng metric aggregation, health check hay lifecycle như thế nào.

### 6.1. Chọn thời gian instance warmup

Một cách làm thực tế:

1. Ghi timestamp lúc yêu cầu launch instance.
2. Ghi timestamp OS boot hoàn tất.
3. Ghi timestamp bootstrap hoàn tất.
4. Ghi timestamp readiness pass.
5. Ghi timestamp đạt throughput hoặc latency ổn định.
6. Tính phân phối thời gian từ launch đến readiness và từ launch đến steady state.
7. Chọn warmup phù hợp với mục tiêu scaling và độ biến động, rồi kiểm thử scale-out/scale-in.

Nếu warmup ngắn hơn thực tế, autoscaler có thể xem metric khi máy chưa ổn định. Nếu quá dài, autoscaler có thể phản ứng chậm với tải tiếp tục tăng. Hãy cân nhắc p95/p99 và tốc độ tăng tải, không chỉ lấy trung bình.

Warmup có thể thay đổi theo image version, loại instance, region hoặc workload. Nếu các nhóm có thời gian startup khác nhau rõ rệt, cân nhắc tách launch template, scaling group hoặc policy để không dùng chung một con số gây sai lệch.

## 7. Cooldown là gì?

Cooldown là khoảng thời gian sau một hành động scaling mà bộ điều khiển chờ trước khi thực hiện hoặc đánh giá một hành động scaling tiếp theo, theo semantics của nền tảng.

Mục tiêu là cho hệ thống thời gian phản ánh tác động của lần thay đổi vừa rồi. Ví dụ, sau khi thêm 2 instance, load balancer cần cập nhật target, traffic cần được phân phối lại và metric CPU cần có thời gian phản ánh capacity mới.

Cooldown có thể giúp:

- Giảm phản ứng quá mức trước metric dao động ngắn.
- Tránh thực hiện nhiều hành động scale liên tiếp khi hành động trước chưa có tác động đầy đủ.
- Cho ứng dụng và hạ tầng ổn định sau thay đổi capacity.

Cooldown không làm máy khởi động nhanh hơn, không thay thế readiness check và không bảo đảm instance mới đã phục vụ request. Đây là cơ chế điều tiết quyết định scaling.

### 7.1. Cooldown khác warmup như thế nào?

| Thuộc tính | Instance warmup | Cooldown |
|---|---|---|
| Trọng tâm | Thời gian instance mới cần để đóng góp ổn định | Khoảng chờ sau một scaling action |
| Bắt đầu tính | Thường gắn với lúc instance được thêm/khởi chạy; phụ thuộc dịch vụ | Sau hành động scale hoặc theo policy |
| Vấn đề giải quyết | Metric của instance mới chưa đại diện steady state | Tránh hành động scaling lặp quá nhanh |
| Tác động | Điều chỉnh cách đánh giá capacity/metric mới | Điều tiết thời điểm quyết định tiếp theo |
| Không thay thế | Readiness và application warmup | Startup, health check hoặc load balancer registration |

Một số dịch vụ có default instance warmup và không cần cooldown riêng cho target tracking; một số policy khác có cooldown hoặc stabilization window. Không áp dụng cùng một cấu hình cho mọi scaling mode nếu semantics khác nhau.

### 7.2. Ví dụ cooldown

Giả sử một nhóm máy scale-out thêm 2 instance sau khi CPU vượt ngưỡng. Trong 90 giây tiếp theo, CPU vẫn cao vì instance mới chưa nhận đủ traffic. Nếu policy lập tức tạo thêm 4 máy, nhóm có thể dư công suất sau khi traffic được phân phối đều.

Cooldown hoặc stabilization window có thể hạn chế hành động lặp trong khoảng đã định. Tuy nhiên, nếu tải tăng rất nhanh và SLO yêu cầu bổ sung capacity tức thì, thời gian chờ quá dài có thể gây thiếu công suất. Hãy kiểm thử cả tình huống tăng tải nhanh lẫn giảm tải.

## 8. Stabilization window và các scaling policy

Ngoài warmup và cooldown, nhiều hệ thống có cửa sổ ổn định để đánh giá metric trong một khoảng thời gian.

- **Target tracking:** cố gắng duy trì metric quanh một target, ví dụ CPU trung bình hoặc request trên mỗi instance.
- **Step scaling:** thực hiện mức tăng/giảm khác nhau tùy độ lệch metric so với ngưỡng.
- **Simple scaling:** thực hiện một hành động scale rồi áp dụng cooldown theo policy.
- **Scheduled scaling:** thay đổi capacity theo lịch đã biết.
- **Predictive scaling:** dự báo nhu cầu và chuẩn bị capacity trước thời điểm tải tăng.
- **Kubernetes HPA:** điều chỉnh số replica dựa trên metric; có behavior và stabilization window để kiểm soát dao động.
- **Cluster/node autoscaler:** thêm node khi Pod không thể được schedule và loại bỏ node khi có thể dồn workload an toàn.

Mỗi policy có semantics khác nhau. Ví dụ, cooldown của simple scaling không nhất thiết hoạt động giống stabilization window của HPA hoặc default instance warmup của nhóm VM.

### 8.1. Ví dụ HPA với stabilization window

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

Ví dụ cho phép scale-up phản ứng nhanh, giới hạn tốc độ tăng theo policy và giữ lịch sử metric trong cửa sổ 300 giây khi quyết định scale-down. Đây là cấu hình minh họa; HPA cần resource requests chính xác để tính CPU utilization. Nếu Pod mới chưa ready, cần xem thêm behavior của controller, metric pipeline và node capacity.

Stabilization window giúp giảm dao động nhưng không thay thế node provisioning time. Nếu cluster cần 2 phút để tạo node, HPA có thể tạo Pod trước nhưng Pod sẽ Pending cho tới khi node mới sẵn sàng.

## 9. Load balancer và traffic warmup

Khi instance mới qua readiness, nó có thể được đăng ký vào load balancer. Tuy nhiên, chuyển toàn bộ traffic ngay lập tức có thể làm cache lạnh hoặc connection pool mới bị quá tải.

Một số cách kiểm soát:

- Chỉ đăng ký target sau khi readiness thành công.
- Dùng slow start hoặc weighted traffic nếu load balancer hỗ trợ.
- Tăng dần weight của instance mới theo từng giai đoạn.
- Giới hạn concurrency hoặc request rate ban đầu.
- Warm cache bằng các request an toàn và có giới hạn.
- Theo dõi latency, error và saturation trước khi tăng traffic tiếp.

Không phải load balancer nào cũng có slow-start. Nếu không hỗ trợ, ứng dụng có thể dùng readiness gate, queue, rate limit hoặc cơ chế điều phối traffic khác.

### 9.1. Target health và draining

Vòng đời target thường có các trạng thái như registering, initial, healthy, unhealthy và draining. Tên gọi cụ thể tùy sản phẩm.

Khi scale-in, cần cho target ngừng nhận request mới, chờ request đang xử lý hoàn tất và đóng kết nối theo chính sách. Quá trình này thường được gọi là connection draining hoặc deregistration delay.

Warmup xử lý lúc instance đi vào nhóm; draining xử lý lúc instance rời nhóm. Cả hai đều ảnh hưởng tới trải nghiệm người dùng và cần được kiểm thử.

## 10. Lifecycle hook và warm pool

Một số dịch vụ nhóm máy cung cấp lifecycle hook để tạm dừng instance ở trạng thái chờ trước khi hoàn tất bước launch hoặc termination. Điều này cho phép hệ thống chạy bootstrap bổ sung, đăng ký cấu hình hoặc thực hiện cleanup trước khi tiếp tục vòng đời.

Ví dụ hành động trong giai đoạn launch hook:

1. Instance được tạo và chuyển sang trạng thái chờ.
2. Bootstrap agent lấy cấu hình và secret.
3. Ứng dụng khởi động và thực hiện kiểm tra.
4. Automation báo hoàn tất lifecycle action.
5. Instance được tiếp tục vào nhóm và có thể nhận traffic theo health policy.

Lifecycle hook cần timeout, retry và cơ chế xử lý khi automation thất bại. Nếu hook bị treo, instance có thể mắc ở trạng thái chờ và nhóm không đạt capacity mong muốn.

**Warm pool** là tập instance được chuẩn bị trước một phần hoặc toàn bộ để rút ngắn thời gian scale-out. Instance có thể ở trạng thái stopped, hibernated hoặc running tùy nền tảng và cấu hình. Khi cần, nhóm lấy instance từ pool rồi hoàn tất các bước còn lại.

Warm pool hữu ích khi:

- Startup time dài và khó rút ngắn.
- Tải có thể tăng nhanh hơn thời gian tạo máy.
- Ứng dụng có chi phí bootstrap lớn.
- Cần chuẩn bị capacity cho giờ cao điểm hoặc sự kiện.

Đổi lại, warm pool có thể phát sinh chi phí storage, compute, license và bảo trì image. Cần cập nhật bản vá, rotate credential và xác minh cấu hình trước khi đưa máy trong pool vào phục vụ. Không để instance warm pool giữ secret hoặc token lâu hơn chính sách cho phép.

## 11. Đo thời gian warmup và cooldown

Không thể chọn warmup/cooldown tốt nếu không có dữ liệu. Hãy tạo event và metric theo từng mốc vòng đời.

Các metric nên có:

| Metric | Định nghĩa |
|---|---|
| instance_launch_duration_seconds | Thời gian từ yêu cầu launch đến trạng thái instance running |
| instance_boot_duration_seconds | Thời gian từ boot start tới OS ready |
| instance_bootstrap_duration_seconds | Thời gian hoàn tất bootstrap |
| application_startup_duration_seconds | Thời gian từ process start tới ứng dụng startup complete |
| instance_time_to_ready_seconds | Thời gian từ launch tới readiness pass |
| instance_time_to_steady_state_seconds | Thời gian từ launch tới khi đạt tiêu chí throughput/latency ổn định |
| autoscaling_action_count | Số hành động scale-up/scale-down theo policy |
| pending_instance_count | Số instance đang provisioning hoặc warmup |
| healthy_target_count | Số target được load balancer đánh dấu healthy |
| capacity_ready_ratio | Capacity đã sẵn sàng so với capacity mục tiêu |
| scale_in_drain_duration_seconds | Thời gian từ bắt đầu drain đến khi instance kết thúc |

Gắn metadata ổn định như launch template version, image ID, instance type, region/AZ, application version và environment. Tránh dùng instance ID làm nhãn cho mọi metric có cardinality cao nếu hệ thống có hàng nghìn instance ngắn hạn; có thể lưu ID trong event/log và dùng nhóm tài nguyên trong metric tổng hợp.

### 11.1. Xác định steady state

Readiness pass không nhất thiết đồng nghĩa hiệu năng đã ổn định. Định nghĩa steady state theo workload, ví dụ:

- Latency p95/p99 nằm trong SLO.
- Error rate thấp hơn ngưỡng cho trước.
- Throughput đạt mức tối thiểu mong đợi.
- CPU và memory không tăng bất thường.
- Connection pool và cache đã đạt trạng thái vận hành.
- Không có backlog tăng liên tục.

Đối với batch worker, steady state có thể được xác định bằng tốc độ xử lý message và độ dài queue. Đối với API, có thể dựa vào request rate, latency và error. Không dùng một điều kiện chung cho mọi workload.

### 11.2. Đo bằng event timestamp

Một cách triển khai là ứng dụng hoặc bootstrap agent phát event:

- instance.launch.requested
- instance.os.ready
- instance.bootstrap.completed
- application.startup.completed
- application.readiness.passed
- application.steady_state.reached

Collector tính duration giữa các event. Đồng bộ thời gian trên host và control plane là cần thiết; nếu timestamp lệch, duration có thể âm hoặc sai lệch. Ưu tiên timestamp từ một nguồn chuẩn hoặc dùng monotonic clock cho đo khoảng thời gian trong cùng process.

## 12. Cách chọn warmup và cooldown theo workload

| Loại workload | Đặc điểm | Hướng cấu hình |
|---|---|---|
| Stateless web/API | Có thể khởi động tương đối nhanh, cần latency ổn định | Warmup dựa trên p95/p99 time-to-ready và traffic warmup; cooldown vừa đủ để metric phản ánh capacity |
| Java service lớn | Class loading, JIT và cache có thể kéo dài | Tách application readiness khỏi runtime warmup; cân nhắc synthetic warmup và warm pool |
| Batch worker | Có thể nhận message sau khi kết nối broker và queue consumer sẵn sàng | Readiness sau khi consumer sẵn sàng; warmup theo tốc độ xử lý ổn định |
| GPU/model serving | Tải model và cấp phát GPU memory có thể lâu | Chuẩn bị model/cache trước khi nhận traffic; warm pool hoặc predictive scale nếu cần |
| Stateful service | Cần đồng bộ dữ liệu, quorum hoặc attach volume | Dùng lifecycle-aware orchestration; không đưa node vào nhóm phục vụ trước khi trạng thái dữ liệu an toàn |
| Node Kubernetes | VM mới phải đăng ký node, cài CNI/CSI và nhận Pod | Đo node-ready và Pod-ready riêng; tính cả thời gian schedule và image pull |

Warmup nên đủ dài để tránh tính capacity quá sớm nhưng không dài tới mức làm autoscaler phản ứng chậm với nhu cầu mới. Cooldown hoặc stabilization window nên dựa trên thời gian cần để hành động trước ảnh hưởng tới metric và SLO.

Với workload có burst rất nhanh, chỉ tăng warmup/cooldown không đủ. Cần duy trì minimum capacity, dùng scheduled/predictive scaling, warm pool hoặc queue buffering để có capacity trước khi tải đến.

## 13. Ví dụ luồng scale-out end-to-end

Giả sử CPU hoặc request-per-instance vượt target:

1. Scaling policy phát hiện tải vượt mục tiêu trong thời gian đánh giá.
2. Nhóm máy yêu cầu launch thêm instance.
3. Instance boot OS và chạy bootstrap.
4. Agent đăng ký monitoring, lấy cấu hình và secret.
5. Ứng dụng khởi động, kết nối database và cache.
6. Startup check hoàn tất; readiness pass.
7. Load balancer đánh dấu target healthy và đưa vào traffic.
8. Traffic được tăng dần nếu có slow-start hoặc weighted routing.
9. Metric của instance được đưa vào đánh giá capacity khi hết instance warmup theo semantics của autoscaler.
10. Autoscaler đánh giá lại tải và quyết định có cần scale tiếp hay không.

~~~mermaid
sequenceDiagram
    participant AS as Autoscaler
    participant VM as Instance
    participant APP as Application
    participant LB as Load Balancer
    participant MON as Monitoring
    AS->>VM: Launch instance
    VM->>VM: OS boot và bootstrap
    VM->>APP: Start application
    APP->>APP: Connect dependencies và warmup
    APP->>LB: Readiness passed
    LB->>LB: Register target và health check
    LB->>APP: Traffic ramp-up
    VM->>MON: Publish metrics
    MON->>AS: Capacity metrics sau warmup
    AS->>AS: Re-evaluate scaling
~~~

Luồng thực tế có thể song song một số bước. Ví dụ agent monitoring có thể chạy trước ứng dụng, còn đăng ký target có thể diễn ra ngay khi readiness pass. Sơ đồ thể hiện các điểm kiểm soát chính, không bắt buộc mọi dịch vụ thực hiện đúng thứ tự này.

## 14. Scale-in: drain, cooldown và bảo vệ workload

Scale-in có rủi ro khác scale-out. Instance bị loại khỏi nhóm có thể đang xử lý request, message hoặc job. Nếu terminate ngay, request có thể lỗi, message bị xử lý trùng hoặc dữ liệu chưa ghi xong.

Quy trình scale-in an toàn:

1. Autoscaler chọn instance có thể loại bỏ theo policy.
2. Đánh dấu instance không nhận thêm công việc.
3. Load balancer chuyển target sang draining hoặc deregister.
4. Ứng dụng ngừng nhận request/message mới.
5. Chờ request, transaction hoặc job đang chạy hoàn tất trong giới hạn.
6. Đóng connection pool, flush dữ liệu và ghi nhận trạng thái.
7. Lifecycle hook/termination handler hoàn tất.
8. Instance được terminate.
9. Monitoring xác nhận capacity và error rate sau scale-in.

Đối với worker xử lý queue, cần dừng polling trước, hoàn thành hoặc trả lại message theo semantics của broker, rồi mới kết thúc process. Với HTTP service, cần hỗ trợ graceful shutdown và thời gian drain đủ dài cho request hợp lệ.

Cooldown sau scale-in có thể giúp tránh scale-up/scale-down liên tục khi metric dao động, nhưng không thay thế graceful shutdown. Cần có termination grace period, deregistration delay và handler phù hợp.

## 15. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| VM running nhưng target unhealthy | Ứng dụng chưa start, port sai hoặc security group chặn health check | Kiểm tra bootstrap log, listener, route và health check path |
| Instance nhận traffic rồi latency tăng | Readiness quá sớm, cache lạnh hoặc JIT chưa warm | Tách readiness/steady-state, dùng traffic ramp-up và synthetic warmup |
| Autoscaler scale-out liên tục | Metric của instance mới thấp, warmup sai hoặc tải tăng nhanh hơn provisioning | Kiểm tra instance warmup semantics, capacity-ready và tốc độ tải |
| Scale-out chậm | Cooldown/stabilization quá dài, quota hoặc launch failure | Kiểm tra policy, quota, lifecycle hook và event provisioning |
| Instance mắc ở Pending/Wait | Lifecycle hook không hoàn tất hoặc automation lỗi | Kiểm tra timeout, retry, permission và completion callback |
| Instance mới không được tính capacity | Chưa healthy hoặc warmup chưa hết theo policy | Kiểm tra health state và metric aggregation |
| Scale-in làm lỗi request | Không drain hoặc grace period quá ngắn | Bật graceful shutdown và kiểm tra thời gian request dài nhất |
| Máy mới có CPU thấp bất thường | Chưa nhận traffic hoặc metric chưa ổn định | Đối chiếu healthy target, request count và warmup state |
| Node mới có nhưng Pod vẫn Pending | CNI/CSI, image pull, taint hoặc resource chưa sẵn sàng | Kiểm tra node condition, scheduler event và runtime |

Khi xử lý, xác định chính xác tầng nào đang chậm: cloud provisioning, OS boot, bootstrap, application startup, readiness, load balancer hay autoscaler policy. Không tăng cooldown để che một lỗi bootstrap hoặc health check.

## 16. Quy trình kiểm thử warmup/cooldown

Trước khi áp dụng cho production, nên kiểm thử cả scale-out, scale-in và tình huống lỗi.

### 16.1. Chuẩn bị

- Chọn workload đại diện và xác định SLO.
- Ghi lại baseline startup time và steady-state throughput.
- Bật event cho từng giai đoạn instance lifecycle.
- Bảo đảm có đủ metric CPU, memory, request, latency và health.
- Xác định giới hạn chi phí và số instance tối đa của bài test.

### 16.2. Kiểm thử scale-out

1. Bắt đầu ở minimum capacity.
2. Tạo tải tăng dần vượt target.
3. Ghi thời điểm autoscaler ra quyết định và yêu cầu launch.
4. Đo từng giai đoạn tới readiness và steady state.
5. Kiểm tra target chỉ nhận traffic sau khi đủ điều kiện.
6. Quan sát autoscaler có scale lặp trong warmup không.
7. Xác nhận SLO trong suốt quá trình tăng capacity.

### 16.3. Kiểm thử scale-in

1. Giảm tải từ mức peak về thấp.
2. Xác nhận stabilization/cooldown không loại bỏ capacity quá sớm.
3. Quan sát load balancer draining.
4. Gửi request hoặc job dài có kiểm soát trong giai đoạn drain.
5. Xác nhận request hoàn tất hoặc được retry an toàn.
6. Kiểm tra error rate và queue backlog sau terminate.

### 16.4. Kiểm thử lỗi

Mô phỏng một số trường hợp có kiểm soát:

- Package repository hoặc image registry chậm.
- Ứng dụng không qua readiness.
- Dependency không sẵn sàng.
- Bootstrap script timeout.
- Lifecycle hook không phản hồi.
- Một AZ hoặc một nhóm instance launch chậm.
- Tải tăng nhanh hơn tốc độ tạo capacity.

Xác nhận hệ thống có timeout, retry, cảnh báo và cơ chế fallback. Không chạy fault injection trên production nếu chưa có phạm vi và quy trình được phê duyệt.

## 17. Tối ưu thời gian máy mới sẵn sàng

Các biện pháp cải thiện có thể được chia theo tầng:

**Provisioning và image**

- Chọn instance family và image phù hợp.
- Dùng image đã cài sẵn package/agent ổn định.
- Giảm bước cài đặt không cần thiết khi boot.
- Chuẩn bị snapshot hoặc warm pool khi startup time dài.
- Kiểm tra quota và capacity theo vùng.

**Bootstrap**

- Tải cấu hình theo batch và song song khi an toàn.
- Dùng artifact có version/digest cố định.
- Tránh gọi API bên ngoài quá nhiều lần.
- Dùng retry có backoff, timeout và idempotency.
- Không chờ tác vụ tùy chọn trước khi mở readiness.

**Application**

- Giảm classpath và khối lượng khởi tạo không cần thiết.
- Lazy-load thành phần không cần cho request đầu tiên.
- Tạo connection pool với kích thước ban đầu phù hợp.
- Warm cache bằng dữ liệu phổ biến có giới hạn.
- Dùng synthetic request an toàn cho đường xử lý quan trọng.

**Traffic và autoscaling**

- Đưa target vào traffic sau readiness.
- Dùng slow-start/weighted routing nếu hỗ trợ.
- Đặt warmup theo time-to-steady-state đã đo.
- Giữ minimum capacity cho tải nền.
- Dùng scheduled/predictive scaling khi nhu cầu có thể dự báo.
- Chọn cooldown/stabilization dựa trên độ trễ metric và thời gian phản ánh tác động.

Tối ưu startup không có nghĩa bỏ qua bước bảo mật hoặc xác minh cấu hình. Không được bỏ qua kiểm tra chứng thư, secret, image integrity hoặc quyền truy cập chỉ để rút ngắn vài giây.

## 18. Checklist vận hành

- [ ] Đã phân biệt launch, boot, bootstrap, application startup, readiness và steady state.
- [ ] Có timestamp hoặc event cho các giai đoạn chính.
- [ ] Đã đo p50/p95/p99 time-to-ready và time-to-steady-state.
- [ ] Startup script có timeout, retry, backoff và idempotency.
- [ ] Secret và credential được lấy an toàn, không nhúng trong image.
- [ ] Readiness chỉ mở khi workload có thể phục vụ request an toàn.
- [ ] Liveness không phụ thuộc trực tiếp vào mọi external dependency.
- [ ] Startup probe cho phép ứng dụng có startup time dài.
- [ ] JVM/runtime warmup và cache lạnh đã được tính đến.
- [ ] Load balancer chỉ chuyển traffic tới target healthy.
- [ ] Traffic ramp-up được dùng khi workload cần warm cache hoặc pool.
- [ ] Instance warmup của autoscaler được cấu hình theo semantics đúng của provider.
- [ ] Cooldown/stabilization window không làm autoscaler phản ứng quá chậm.
- [ ] Scale-in có draining, graceful shutdown và termination grace period.
- [ ] Lifecycle hook có timeout và xử lý khi callback thất bại.
- [ ] Warm pool được vá, cập nhật và quản lý credential đúng hạn.
- [ ] Đã kiểm thử scale-out, scale-in và các trường hợp bootstrap lỗi.
- [ ] Có dashboard theo dõi capacity ready, target health và thời gian sẵn sàng.

Warmup, cooldown và thời gian máy mới sẵn sàng là những phần khác nhau của cùng một vòng đời autoscaling. Hãy đo từ lúc yêu cầu launch đến readiness và steady state, chỉ cho instance nhận traffic khi ứng dụng thực sự phục vụ được, rồi cấu hình autoscaler theo thời gian capacity mới bắt đầu đóng góp ổn định. Cooldown và stabilization giúp giảm quyết định scale liên tiếp; readiness, traffic ramp-up và graceful shutdown bảo vệ request trong lúc nhóm máy thay đổi. Kiểm thử cả scale-out lẫn scale-in giúp hệ thống phản ứng đúng với tải mà vẫn giữ SLO và chi phí trong giới hạn.
