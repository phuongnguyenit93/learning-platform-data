# Triển khai thử theo nhóm nhỏ, theo dõi bằng JFR và chuẩn bị quay lui phiên bản

> **Chương:** Build và triển khai  
> **Phạm vi:** Phát hành ứng dụng Java 25 theo từng nhóm traffic, dùng Java Flight Recorder (JFR) để chẩn đoán và giữ sẵn đường quay về bản ổn định.  
> **Mục tiêu:** Thiết kế canary rollout có tiêu chí tăng tải/dừng rõ ràng, so sánh sức khỏe của bản mới với baseline và khôi phục dịch vụ khi phát hiện hồi quy.

## 1. Vì sao không chuyển toàn bộ traffic trong một lần?

Một bản phát hành có thể biên dịch thành công nhưng vẫn phát sinh lỗi chỉ xuất hiện dưới tải thật: latency tăng khi có nhiều request đồng thời, pool kết nối cạn, allocation rate tăng, GC hoạt động dày hơn hoặc một nhánh nghiệp vụ hiếm bị lỗi.

Nếu chuyển toàn bộ traffic ngay lập tức, phạm vi ảnh hưởng có thể rất lớn trước khi nhóm phát hiện sự cố. Canary deployment giảm rủi ro bằng cách đưa bản mới tới một nhóm nhỏ trước, quan sát hành vi thực tế rồi mới mở rộng.

Quy trình này có ba vòng kiểm soát:

1. **Giới hạn phạm vi:** chạy bản mới ở một hoặc vài instance riêng, chỉ nhận một phần traffic.
2. **Đo bằng dữ liệu:** so sánh SLI/SLO, metric JVM, log, trace và JFR của bản mới với bản ổn định trong cùng khoảng thời gian.
3. **Giữ khả năng quay lui:** lưu image digest, JDK runtime, cấu hình và revision đã biết tốt; có thể giảm traffic canary hoặc phục hồi pod template khi cần.

Canary là phương pháp phát hành có kiểm soát, không thay thế kiểm thử. Smoke test, integration test, migration compatibility và kiểm tra bảo mật vẫn cần hoàn thành trước khi nhận traffic production.

## 2. Chốt chính xác artifact sẽ triển khai

Trước khi tạo canary, cần biết chính xác điều gì đang thay đổi. Một artifact triển khai nên được nhận diện bằng ít nhất:

- Image digest hoặc checksum bất biến.
- Phiên bản ứng dụng/commit và build identifier.
- JDK vendor, full version/build và loại runtime image.
- Base OS image và kiến trúc CPU.
- Cấu hình ứng dụng, feature flags và secret version.
- Phiên bản schema/database migration mà ứng dụng yêu cầu.
- Dependency và thư viện native quan trọng.

Không dùng tag có thể thay đổi như `latest` để đại diện cho bản phát hành. Một tag có thể trỏ sang image khác sau khi deploy; digest giúp xác định chính xác binary đang chạy.

Ví dụ:

~~~bash
docker build -t registry.example.com/orders-api:2026.11.27 .
docker push registry.example.com/orders-api:2026.11.27
docker inspect --format='{{index .RepoDigests 0}}' \
  registry.example.com/orders-api:2026.11.27
~~~

Ghi lại digest trả về trong release record và dùng digest đó trong manifest triển khai. Lệnh `docker inspect` ở trên chỉ minh họa cách truy vấn digest sau khi push; registry và pipeline thực tế có thể cung cấp digest trực tiếp.

### Tách riêng thay đổi ứng dụng và thay đổi JDK

Nếu một đợt phát hành vừa đổi code vừa nâng JDK, khi xảy ra hồi quy sẽ khó xác định nguyên nhân. Khi có thể, chia thành các bước:

| Lượt | Ứng dụng | JDK | Mục đích |
|---|---|---|---|
| Baseline | Bản hiện tại | Runtime hiện tại | Ghi nhận hành vi đã biết tốt |
| Runtime canary | Cùng artifact | JDK 25 update mới | Đo tác động của runtime |
| Application canary | Artifact mới | JDK đã chọn | Đo thay đổi ứng dụng |
| Combined release | Artifact và runtime mục tiêu | JDK mục tiêu | Xác nhận cấu hình cuối |

Không phải dự án nào cũng cần bốn lượt riêng. Nhưng nếu hai thay đổi lớn được gộp, phải có dữ liệu đủ để phân biệt tác động của runtime, code và cấu hình.

### Ghi lại baseline

Trước khi phát hành, lưu:

- Request rate, tỷ lệ lỗi và latency p50/p95/p99.
- CPU, memory/RSS, restart count và saturation.
- Heap occupancy, allocation rate, GC pause/cycle.
- Thread count, connection pool, queue depth và dependency latency.
- Các luồng nghiệp vụ quan trọng và tỷ lệ thành công.
- JDK version, image digest, cấu hình và thời gian lấy số liệu.

Baseline cần đại diện cho cùng loại traffic, cùng khung giờ và cùng dependency mà canary sẽ nhận.

## 3. Chọn cách triển khai canary

### Canary bằng hai Deployment riêng

Tạo Deployment ổn định và Deployment canary, mỗi Deployment có Service riêng. Gateway, ingress controller hoặc service mesh chia traffic giữa hai Service.

Ưu điểm:

- Có thể giữ nguyên số replica ổn định trong lúc thử bản mới.
- Điều chỉnh traffic canary độc lập.
- Dễ dừng canary mà không cần thay đổi toàn bộ Deployment ổn định.
- Có thể gửi synthetic traffic hoặc traffic nội bộ vào canary trước.

### Rolling update của một Deployment

Kubernetes Deployment có chiến lược RollingUpdate, thay pod cũ bằng pod mới theo `maxSurge` và `maxUnavailable`. Cách này kiểm soát số pod thay đổi cùng lúc, nhưng bản thân Deployment không cung cấp bộ chia traffic theo tỷ lệ canary độc lập. Khi cần kiểm soát chính xác 1%, 5% hoặc 10% traffic, dùng hai backend riêng và một cơ chế routing có hỗ trợ weighted traffic.

Không nhầm rolling update với canary traffic splitting: rolling update quyết định thay pod như thế nào; gateway/service mesh quyết định request được gửi tới phiên bản nào.

### Chia traffic bằng Kubernetes Gateway API

`HTTPRoute` hỗ trợ trọng số tương đối giữa các backend. Ví dụ dưới đây gửi traffic theo tỷ lệ 99:1 giữa bản ổn định và canary:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-api
spec:
  parentRefs:
    - name: public-gateway
  hostnames:
    - orders.example.com
  rules:
    - backendRefs:
        - name: orders-stable
          port: 8080
          weight: 99
        - name: orders-canary
          port: 8080
          weight: 1
~~~

`weight` là tỷ lệ tương đối: tổng weight của các backend trong rule là mẫu số. Hai giá trị 99 và 1 tạo tỷ lệ xấp xỉ 99%/1% khi có đủ request; nó không đảm bảo mỗi nhóm 100 request sẽ chia đúng tuyệt đối 99/1.

Ví dụ này yêu cầu cluster đã cài Gateway API CRDs, Gateway controller và cấu hình listener phù hợp. Ingress controller hoặc service mesh khác có thể dùng cấu hình riêng.

## 4. Các bước mở rộng traffic

~~~mermaid
flowchart TD
    A["Build và xác minh artifact"] --> B["Deploy canary, traffic nội bộ"]
    B --> C["Smoke test và readiness"]
    C --> D["1% traffic"]
    D --> E{"SLI và JVM ổn định?"}
    E -->|Có| F["5% rồi 20%"]
    E -->|Không| R["Dừng tăng tải, quay lui"]
    F --> G{"So sánh JFR và SLO"}
    G -->|Đạt| H["50% rồi 100%"]
    G -->|Không| R
    H --> I["Bake time và theo dõi sau phát hành"]
    R --> J["Giữ bản ổn định, điều tra"]
~~~

Các mốc 1%, 5%, 20%, 50% và 100% chỉ là ví dụ. Tỷ lệ và thời gian ở mỗi bước phụ thuộc traffic volume, mức độ rủi ro, thời gian xuất hiện lỗi và khả năng quan sát.

Một quy trình thực tế:

1. **Deploy không nhận production traffic:** tạo pod canary, kiểm tra image digest, JDK, config, readiness và log startup.
2. **Smoke test:** gọi các endpoint chính, xác minh kết nối database, cache và dependency; chạy synthetic test qua route dành riêng.
3. **Traffic nội bộ:** cho một nhóm người dùng nội bộ hoặc request có header thử nghiệm đi vào canary nếu gateway hỗ trợ.
4. **Traffic nhỏ:** mở tỷ lệ thấp, ghi nhận SLI và JVM metrics trong cửa sổ đủ dài.
5. **Tăng từng nấc:** chỉ tăng khi mọi gate đạt và lượng request đủ để đánh giá.
6. **Mở rộng toàn bộ:** giữ bản cũ hoặc khả năng dựng lại bản cũ trong thời gian bake đã thống nhất.
7. **Kết thúc:** cập nhật release record, giữ JFR/metrics theo retention và dọn tài nguyên canary sau khi hết thời gian quan sát.

Nếu traffic quá thấp để có đủ mẫu, tăng tỷ lệ canary hoặc dùng synthetic traffic có kiểm soát. Không kết luận bản mới an toàn chỉ vì không thấy lỗi trong vài request.

## 5. Health probes giúp kiểm soát pod

Trong Kubernetes, ba loại probe có mục đích khác nhau:

| Probe | Câu hỏi | Hành động khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất khởi động chưa? | Kubelet restart container khi vượt ngưỡng thất bại |
| Readiness | Pod có thể nhận traffic ngay lúc này không? | Pod bị loại khỏi endpoint phục vụ traffic |
| Liveness | Process có còn hoạt động và có thể tiến triển không? | Kubelet restart container khi vượt ngưỡng thất bại |

Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /startupz
    port: 8080
  periodSeconds: 10
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Đây là cấu hình minh họa; ứng dụng cần triển khai endpoint tương ứng và chọn timeout/failure threshold theo thời gian startup, tải và SLO.

- Startup probe cho phép ứng dụng có thời gian nạp cấu hình, warm cache hoặc khởi tạo runtime trước khi liveness/readiness bắt đầu.
- Readiness có thể kiểm tra những dependency bắt buộc để phục vụ request. Khi dependency tạm thời không sẵn sàng, pod có thể ngừng nhận traffic nhưng vẫn tiếp tục chạy.
- Liveness nên phản ánh tình trạng process không thể phục hồi bằng cách chờ hoặc giảm tải, ví dụ deadlock. Không đưa mọi dependency bên ngoài vào liveness; nếu database gặp sự cố, restart đồng loạt tất cả pod có thể tạo thêm tải và làm sự cố lan rộng.

Probe không thay thế SLI. Một pod có thể trả readiness thành công nhưng latency hoặc tỷ lệ lỗi nghiệp vụ vẫn xấu.

## 6. Đặt điều kiện tăng traffic và điều kiện quay lui trước khi deploy

Không quyết định tăng traffic chỉ dựa trên cảm giác hoặc một dashboard màu xanh. Trước khi phát hành, thống nhất:

- SLO hiện tại và error budget còn lại.
- Chỉ số cần quan sát và nguồn dữ liệu.
- Cửa sổ đánh giá và lượng request tối thiểu.
- Ngưỡng dừng rollout.
- Người hoặc hệ thống có quyền dừng/tăng traffic.
- Cách quay về backend ổn định và cách xác minh sau rollback.

### Bảng gate tham khảo

| Nhóm | Điều kiện để tiếp tục | Dấu hiệu cần dừng |
|---|---|---|
| Availability | Tỷ lệ request thành công không giảm đáng kể | 5xx, timeout hoặc lỗi nghiệp vụ tăng |
| Latency | p95/p99 nằm trong SLO và gần baseline | Tail latency tăng liên tục |
| Throughput | Canary xử lý được offered load tương đương | Queue tăng, dropped request hoặc throughput giảm |
| CPU | CPU/request và CPU saturation trong giới hạn | CPU throttling hoặc saturation tăng |
| Memory | RSS/heap ổn định, còn headroom | OOM, restart, heap tăng liên tục |
| GC | Pause và concurrent GC cost chấp nhận được | Pause spike, allocation pressure hoặc GC cycle bất thường |
| Dependencies | Pool và downstream latency ổn định | Connection pool cạn, timeout hoặc retry storm |
| Business | Các giao dịch trọng yếu thành công | Sai dữ liệu, mất sự kiện hoặc kết quả nghiệp vụ sai |

### Dùng ngưỡng tương đối và ngưỡng tuyệt đối

Ví dụ một chính sách có thể yêu cầu:

- p99 không vượt SLO tuyệt đối.
- p99 của canary không cao hơn baseline quá một tỷ lệ đã thống nhất trong vài cửa sổ liên tiếp.
- Error rate không vượt ngưỡng SLO hoặc error-budget burn rate.
- Không có OOM, restart loop, dữ liệu sai hoặc lỗi bảo mật nghiêm trọng.
- Đã thu đủ request để tránh kết luận từ mẫu quá nhỏ.

Các ngưỡng số cụ thể phải lấy từ SLO và dữ liệu lịch sử của chính dịch vụ. Không dùng một con số chung cho mọi API hoặc mọi mức traffic. Với lỗi nghiêm trọng như ghi sai dữ liệu, rò rỉ thông tin hoặc vi phạm bảo mật, dừng rollout ngay cả khi tỷ lệ lỗi tổng thể còn thấp.

## 7. Theo dõi SLI và JVM metrics trong từng giai đoạn

Dashboard cần tách bản ổn định và canary theo version, image digest, pod, region và endpoint. Nếu chỉ xem số liệu tổng, một canary nhỏ có thể bị che khuất bởi phần lớn traffic ổn định.

### SLI ở tầng ứng dụng

- Request rate và số request thành công.
- Tỷ lệ HTTP 5xx, timeout và lỗi nghiệp vụ.
- p50, p95, p99 và p99.9 latency.
- Queue depth, retry rate và request đang xử lý.
- Kết quả các giao dịch quan trọng như tạo đơn, thanh toán hoặc phát sự kiện.

### Metrics ở tầng JVM

- Heap used/committed và xu hướng sau GC.
- Allocation rate và object promotion nếu có metric.
- GC pause duration, số lần collection và concurrent GC activity.
- Process CPU, container CPU throttling và RSS.
- Thread count, thread states, monitor contention và thread park.
- Connection pool, direct buffer và metaspace nếu ứng dụng có sử dụng.

### So sánh công bằng

Canary và stable cần được so sánh trong cùng cửa sổ thời gian, cùng loại request, cùng khu vực và cùng dependency. Chuẩn hóa các số liệu theo request hoặc operation khi phù hợp, ví dụ CPU/request, allocation/request và error/request.

Nếu canary nhận traffic khác biệt (chẳng hạn chỉ nhận request đơn giản hoặc chỉ từ một region), kết quả không đại diện cho toàn bộ workload. Cần phân tầng theo endpoint, tenant/nhóm người dùng và kích thước payload.

## 8. Dùng JFR như một lớp chẩn đoán trong rollout

Java Flight Recorder thu thập các event có timestamp về JVM và ứng dụng. JFR giúp tìm hiểu **vì sao** một SLI xấu đi, trong khi metrics cho biết **điều gì** đang xảy ra và ở phạm vi nào.

Trong giai đoạn canary, JFR hữu ích để:

- Xác định hot methods qua execution samples.
- So sánh allocation pressure và nơi tạo object.
- Quan sát GC events, pause và concurrent work.
- Tìm thread bị park, chờ monitor hoặc contention.
- Kiểm tra exception và hoạt động I/O khi event tương ứng được bật.
- Đối chiếu thời điểm spike với request latency và log.

JFR không thay thế metrics, logs, distributed tracing hoặc business monitoring. JFR cũng không tự cung cấp mọi metric nghiệp vụ; nếu muốn phân tích request cụ thể, ứng dụng cần instrumentation phù hợp và không đưa dữ liệu nhạy cảm vào event.

### Chọn cấu hình recording

JDK 25 cung cấp hai cấu hình chuẩn trong `JAVA_HOME/lib/jfr`:

| Cấu hình | Mục đích | Cách dùng |
|---|---|---|
| `default.jfc` | Thu thập nền với overhead thấp, phù hợp continuous recording | Duy trì trong thời gian rollout |
| `profile.jfc` | Thu thập nhiều event hơn để phân tích sâu | Dùng ngắn hạn khi canary có dấu hiệu bất thường |

Continuous recording với `default.jfc` không bao gồm mọi thống kê heap hoặc allocation profiling. Khi cần điều tra allocation, lock hoặc hot method sâu hơn, dùng một recording ngắn với `profile.jfc` hoặc custom JFC đã được đánh giá.

Overhead phụ thuộc workload và event settings. Đo tác động trên staging hoặc một nhóm nhỏ trước khi bật cấu hình profiling dày trong production. Không mặc định mọi recording có overhead bằng không.

## 9. Bật continuous JFR ngay khi JVM khởi động

Có thể khởi động recording cùng ứng dụng để tránh mất dữ liệu trước khi thao tác thủ công:

~~~bash
java \
  '-XX:StartFlightRecording:name=rollout,settings=default,disk=true,maxage=6h,maxsize=512m,dumponexit=true,filename=/var/log/jfr/orders-%p-%t.jfr' \
  -jar orders-api.jar
~~~

Ý nghĩa các tùy chọn:

- `settings=default`: dùng cấu hình continuous recording có sẵn.
- `disk=true`: ghi dữ liệu vào disk repository.
- `maxage=6h`: chỉ giữ dữ liệu trong cửa sổ tối đa sáu giờ.
- `maxsize=512m`: giới hạn dữ liệu recording trên disk.
- `dumponexit=true`: dump recording khi JVM shutdown bình thường.
- `filename`: đặt đường dẫn file; `%p` và `%t` được thay bằng process ID và timestamp.

Các giá trị sáu giờ và 512 MB chỉ là ví dụ. Cần cân nhắc số pod, số recording, dung lượng volume, retention và chính sách thu thập dữ liệu của tổ chức.

### Lưu ý trong container

- Đường dẫn JFR phải ghi được bởi user chạy JVM.
- Dùng volume hoặc cơ chế export để file không biến mất cùng writable layer khi pod bị xóa.
- Thu thập file trước khi scale canary về 0 nếu cần điều tra.
- `dumponexit` hữu ích khi JVM shutdown bình thường, nhưng không bảo đảm file cuối cùng được dump khi process bị kill cưỡng bức, node mất điện hoặc container bị OOM kill.
- Theo dõi dung lượng volume và retention để recording không làm đầy filesystem.

## 10. Điều khiển recording bằng jcmd khi cần điều tra

Nếu ứng dụng đã chạy mà chưa bật recording phù hợp, dùng `jcmd` để điều khiển JVM. Chạy lệnh trong đúng container/PID namespace và bằng user phù hợp với process Java.

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Bắt đầu recording ngắn để profiling:

~~~bash
jcmd <PID> JFR.start name=canary-profile settings=profile duration=2m filename=/tmp/canary-profile.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <PID> JFR.check
~~~

Dump một bản snapshot trong khi continuous recording vẫn tiếp tục:

~~~bash
jcmd <PID> JFR.dump name=rollout filename=/tmp/rollout-snapshot.jfr
~~~

Dừng recording và ghi file:

~~~bash
jcmd <PID> JFR.stop name=rollout filename=/tmp/rollout-final.jfr
~~~

`JFR.dump` ghi dữ liệu hiện có ra file và recording tiếp tục chạy. `JFR.stop` dừng recording; dùng `filename` để ghi dữ liệu cuối cùng. Tên `rollout` trong ví dụ phải trùng tên recording đã khởi tạo.

Trong môi trường Kubernetes, PID thường là PID nhìn thấy từ container process namespace. Nếu `jcmd -l` không thấy JVM, kiểm tra PID namespace, user, quyền attach và việc công cụ `jcmd` có cùng JDK phù hợp với runtime hay không. Không mở remote JMX chỉ để lấy JFR nếu quy trình chẩn đoán nội bộ đã đủ.

## 11. Đọc và so sánh JFR của stable với canary

Sau khi dump recording, kiểm tra file trước khi mở bằng JDK Mission Control (JMC):

~~~bash
jfr summary /tmp/rollout-snapshot.jfr
jfr summary /tmp/canary-profile.jfr
~~~

Có thể in một số event tiêu biểu:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection,jdk.ThreadPark \
  /tmp/canary-profile.jfr
~~~

JMC hỗ trợ xem timeline, thread activity, CPU samples, allocation, GC và lock contention theo khoảng thời gian. Mở recording stable và canary riêng biệt rồi so sánh cùng time window.

### Các câu hỏi khi phân tích

| Quan sát | Câu hỏi cần trả lời |
|---|---|
| Execution samples tập trung ở method mới | Có hot path mới hoặc thuật toán tốn CPU không? |
| Allocation rate tăng | Bản mới có tạo thêm DTO, buffer, collection hoặc object tạm không? |
| GC pause/cycle tăng | Có thay đổi về object lifetime, heap headroom hoặc allocation burst không? |
| Thread park/monitor wait tăng | Có lock contention, pool exhaustion hoặc đồng bộ hóa mới không? |
| Socket/I/O events thay đổi | Downstream có chậm hơn hoặc retry nhiều hơn không? |
| Exception tăng | Có nhánh lỗi mới, retry loop hoặc cấu hình không tương thích không? |

Không kết luận từ số lượng sample tuyệt đối nếu thời lượng recording hoặc request volume khác nhau. So sánh cùng khoảng thời gian, cùng event settings và chuẩn hóa theo request/operation. Execution sample là dữ liệu lấy mẫu, không phải bộ đếm chính xác số lần gọi method.

### Bản ghi cần gắn với đúng phiên bản

Đặt tên file theo service, version, pod và thời gian, ví dụ:

~~~text
orders-api-v2026.11.27-canary-pod-7d8f-20261127T101500Z.jfr
~~~

Lưu metadata đi kèm:

- Git commit/build ID.
- Image digest và JDK full version.
- Pod name, namespace, node/region.
- Canary weight và cửa sổ traffic.
- JFR settings, start/end timestamp.
- Link tới dashboard, trace và incident/release record.

Không ghép recording của hai phiên bản vào cùng một file hoặc đặt tên chung khiến không thể xác định nguồn.

## 12. Bảo vệ dữ liệu và kiểm soát overhead của JFR

JFR được thiết kế cho chẩn đoán với overhead thấp, nhưng event settings có thể làm tăng chi phí và lượng dữ liệu. Một số event hoặc custom application event có thể chứa thông tin vận hành nhạy cảm.

Thực hiện các nguyên tắc sau:

- Bắt đầu bằng `default.jfc`; chỉ bật `profile.jfc` trong thời gian cần thiết.
- Kiểm tra overhead và dung lượng trên môi trường đại diện.
- Giới hạn `maxage`, `maxsize` và số recording chạy đồng thời.
- Lưu file trong vùng có access control; mã hóa khi lưu/chuyển nếu chính sách yêu cầu.
- Không ghi password, token, session ID, nội dung request hoặc dữ liệu cá nhân vào custom JFR event.
- Giới hạn quyền tải và mở recording; đặt retention và quy trình xóa rõ ràng.
- Chỉ bật thu thập GC root path hoặc event chi phí cao khi có giả thuyết sự cố cụ thể.
- Không coi JFR là kho lưu trữ log lâu dài; dump và giữ lại đúng cửa sổ phục vụ điều tra.

Nếu cần heap dump, đó là một thao tác chẩn đoán riêng có chi phí và rủi ro bộ nhớ/dữ liệu cao hơn; không tự động tạo heap dump trong mọi canary.

## 13. Quyết định tăng traffic, giữ nguyên hoặc quay lui

Mỗi lần đánh giá cần đưa ra một trong ba quyết định:

**Tăng traffic:** tiếp tục nấc rollout tiếp theo khi SLI đạt SLO, JVM metrics ổn định, không có lỗi nghiệp vụ và lượng mẫu đủ đại diện.

**Giữ nguyên tỷ lệ:** giữ canary ở mức hiện tại khi dữ liệu chưa đủ, có tín hiệu cần điều tra hoặc một metric chưa rõ nguyên nhân. Thu thêm metrics/JFR trước khi quyết định.

**Quay lui:** chuyển traffic về bản ổn định khi vượt ngưỡng đã định, có lỗi nghiêm trọng hoặc không thể chứng minh bản mới an toàn trong cửa sổ rollout.

Ví dụ: p99 của canary tăng nhưng 5xx chưa tăng. Không vội tăng traffic; kiểm tra CPU throttling, JFR execution samples, thread contention, GC và downstream latency. Nếu p99 vượt SLO liên tục, dừng mở rộng và thực hiện quyết định rollback theo policy đã thống nhất.

Nếu phát hiện sai dữ liệu, mất giao dịch, lỗi bảo mật hoặc tương thích schema nghiêm trọng, không chờ hết cửa sổ quan sát. Chuyển traffic khỏi canary và kích hoạt quy trình incident ngay.

## 14. Quay lui trên Kubernetes và kiểm tra sau rollback

### Canary dùng hai Deployment

Khi canary có vấn đề:

1. Ghi nhận thời điểm, tỷ lệ traffic và version đang lỗi.
2. Nếu hệ thống còn ổn định, dump JFR/log/metrics cần thiết trước khi scale pod về 0.
3. Cập nhật route để đưa 100% traffic về Service ổn định và 0% về canary.
4. Xác minh route đã được controller áp dụng và request mới không còn tới canary.
5. Giữ canary ở trạng thái không nhận traffic để điều tra hoặc scale về 0 sau khi thu thập dữ liệu.
6. Kiểm tra SLI của bản ổn định đã trở lại baseline.

### Một Deployment dùng rollout history

Xem lịch sử:

~~~bash
kubectl rollout history deployment/orders-api
~~~

Quay về revision đã xác định:

~~~bash
kubectl rollout undo deployment/orders-api --to-revision=12
~~~

Chờ rollout hoàn tất:

~~~bash
kubectl rollout status deployment/orders-api --timeout=5m
~~~

Số `12` chỉ là ví dụ; phải chọn revision đã xác minh là bản tốt. Có thể dùng `kubectl rollout undo deployment/orders-api` để quay về revision trước đó nếu lịch sử đúng như dự kiến.

Kubernetes Deployment lưu revision thông qua ReplicaSets và mặc định giữ lại một số revision cũ. Kiểm tra `revisionHistoryLimit`; nếu đặt bằng 0 thì không còn lịch sử để rollback bằng cơ chế này.

**Giới hạn quan trọng:** `kubectl rollout undo` khôi phục Pod template của Deployment. Nó không tự hoàn tác mọi thay đổi bên ngoài như ConfigMap/Secret độc lập, database schema, dữ liệu đã ghi, message đã phát hoặc cấu hình Gateway. Những thành phần này phải có versioning và quy trình rollback riêng.

## 15. Database, config và feature flag phải tương thích khi quay lui

Rollback ứng dụng chỉ an toàn nếu phiên bản cũ vẫn chạy được với schema và dữ liệu hiện tại.

Dùng chiến lược **expand-and-contract**:

1. **Expand:** thêm cột/bảng/index hoặc cấu trúc mới theo cách phiên bản cũ vẫn đọc/ghi được.
2. **Deploy:** phát hành ứng dụng mới có thể hoạt động với cả schema cũ và schema mở rộng.
3. **Migrate data:** chuyển đổi dữ liệu theo batch, có kiểm tra và khả năng tiếp tục.
4. **Switch:** chuyển traffic và feature flag sang logic mới sau khi canary đạt.
5. **Contract:** chỉ xóa cấu trúc cũ sau khi phiên bản cũ không còn cần và thời gian rollback đã kết thúc.

Không chạy migration phá hủy tương thích ngay trước khi mở canary. Nếu migration không thể đảo ngược, phải có kế hoạch phục hồi dữ liệu và quyết định nghiệp vụ riêng; quay lui image không thể tự khôi phục dữ liệu đã thay đổi.

Feature flag có thể giúp tắt nhanh một tính năng gây lỗi mà không cần thay image. Tuy nhiên, flag cũng cần owner, default an toàn, audit và kế hoạch dọn dẹp sau khi phát hành.

### Khi rollback JDK

Nếu bản phát hành nâng JDK, runtime cũ và runtime mới phải được đóng gói thành image riêng, có version/digest rõ ràng. Không thay JDK trong một container đang chạy. Khi cần quay lui, deploy lại image đã biết tốt cùng cấu hình tương thích.

Java 25 là một LTS release theo lộ trình Oracle, nhưng lịch hỗ trợ và bản vá còn tùy vendor/distribution. Không quay về một JDK đã biết có lỗ hổng chỉ để khôi phục nhanh mà không đánh giá rủi ro bảo mật. Nếu bản cũ không còn an toàn, ưu tiên fix-forward sang một build đã vá và tương thích.

## 16. Playbook sự cố và các sai lầm thường gặp

### Playbook khi canary xấu đi

| Thứ tự | Hành động | Kết quả cần có |
|---|---|---|
| 1 | Dừng tăng traffic, giữ nguyên hoặc giảm weight | Không mở rộng phạm vi ảnh hưởng |
| 2 | Kiểm tra 5xx, p95/p99, throughput, restart và saturation | Xác định mức độ ảnh hưởng |
| 3 | So sánh canary với stable theo cùng endpoint/time window | Khoanh vùng khác biệt |
| 4 | Dump JFR và log nếu an toàn | Có dữ liệu chẩn đoán trước khi pod bị thay |
| 5 | Kiểm tra config, JDK, image digest và database compatibility | Xác định thay đổi liên quan |
| 6 | Chuyển traffic về stable hoặc rollout undo | Phục hồi khả năng phục vụ |
| 7 | Xác minh SLI, dữ liệu và queue sau rollback | Xác nhận dịch vụ đã ổn định |
| 8 | Lưu incident record và nguyên nhân | Ngăn tái diễn trong lần phát hành sau |

### Các sai lầm cần tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gộp code, JDK, config và schema change mà không tách baseline | Khó tìm nguyên nhân hồi quy | Ghi manifest release và chia thay đổi khi có thể |
| Dùng tag image có thể thay đổi | Không xác định được binary đang chạy | Deploy bằng digest bất biến |
| Coi rolling update là weighted canary | Không kiểm soát chính xác tỷ lệ request | Dùng Gateway/service mesh với backend riêng |
| Tăng traffic khi sample quá ít | Kết luận thiếu độ tin cậy | Đặt minimum request volume và cửa sổ đánh giá |
| Chỉ nhìn aggregate metrics | Lỗi canary bị stable che khuất | Tách theo version/pod/endpoint/region |
| Chỉ dựa vào JFR | Không thấy SLO hoặc lỗi nghiệp vụ tổng thể | Kết hợp metrics, logs, traces và business signals |
| Dùng profile recording liên tục cho mọi pod | Tăng overhead và dung lượng | Continuous default, profile ngắn khi cần |
| Dump JFR vào filesystem tạm rồi xóa pod | Mất dữ liệu điều tra | Export recording hoặc dùng volume phù hợp |
| Dùng liveness probe kiểm tra mọi dependency | Restart storm khi downstream lỗi | Liveness cho process; readiness cho khả năng nhận traffic |
| Rollback image nhưng bỏ qua schema | Phiên bản cũ không đọc được dữ liệu mới | Expand-and-contract và compatibility tests |
| Chỉ rollback Deployment template | Config/route/secret vẫn ở trạng thái mới | Version hóa và rollback từng thành phần |
| Quay về JDK có lỗ hổng đã biết | Khôi phục dịch vụ nhưng tạo rủi ro bảo mật | Dùng bản đã vá hoặc fix-forward |
| Dọn bản stable ngay khi canary đạt 100% | Mất đường quay lui nhanh | Giữ artifact và revision theo bake/retention policy |

## 17. Checklist và bài tập triển khai

### Checklist trước phát hành

- [ ] Image digest, commit, JDK full version và config đã được ghi lại.
- [ ] Có baseline SLI/JVM metrics của bản stable.
- [ ] Đã xác minh integration test, smoke test và database compatibility.
- [ ] Canary có Service/route riêng và có thể nhận traffic nội bộ.
- [ ] Startup, readiness và liveness probes có mục đích riêng.
- [ ] Có traffic split và quyền dừng rollout.
- [ ] Có ngưỡng SLO, minimum sample volume và cửa sổ đánh giá.
- [ ] JFR continuous recording dùng cấu hình phù hợp và có giới hạn dung lượng/tuổi.
- [ ] Đường export recording khỏi pod đã được kiểm tra.
- [ ] Có bản stable image/config và revision đã biết tốt.
- [ ] Database migration hỗ trợ phiên bản cũ trong cửa sổ rollback.
- [ ] Có người chịu trách nhiệm ra quyết định tăng traffic hoặc rollback.

### Checklist trong rollout

- [ ] Xác minh canary nhận đúng tỷ lệ và đúng nhóm request.
- [ ] So sánh error rate, p95/p99 và throughput với stable.
- [ ] Theo dõi CPU, RSS, heap, GC, thread, queue và connection pool.
- [ ] Kiểm tra JFR khi xuất hiện khác biệt đáng kể.
- [ ] Không tăng traffic khi chưa đủ mẫu hoặc có gate chưa đạt.
- [ ] Lưu JFR, dashboard và release metadata theo đúng version.

### Checklist sau rollout

- [ ] Traffic đã chuyển hoàn toàn tới bản mục tiêu.
- [ ] SLI vẫn đạt trong bake window.
- [ ] Không có restart, OOM hoặc lỗi nghiệp vụ tăng bất thường.
- [ ] Giữ artifact/revision cũ theo rollback policy.
- [ ] Database contract/destructive migration chỉ chạy sau khi hết thời gian cần rollback.
- [ ] Đã lưu release record, JFR và kết quả so sánh.
- [ ] Đã lập kế hoạch xóa tài nguyên canary và feature flag không còn dùng.

### Bài tập: nâng JDK của Orders API

Một dịch vụ Orders API đang chạy trên JDK 21 và chuẩn bị phát hành image mới dùng JDK 25. Mục tiêu là giữ p99 trong SLO, không tăng error rate và không vượt memory limit của container.

1. Build hai image bất biến: bản stable và bản canary; ghi digest, JDK version và commit.
2. Chạy cùng application artifact trên JDK mới trong staging để tách ảnh hưởng runtime nếu có thể.
3. Tạo Deployment canary và Service riêng; gửi synthetic traffic trước.
4. Cấu hình startup/readiness/liveness probes.
5. Bật continuous JFR bằng `default.jfc` với `maxage` và `maxsize` phù hợp.
6. Mở traffic canary theo các nấc đã thống nhất; ở mỗi nấc ghi request volume, error rate, p95/p99, CPU, RSS, heap và GC.
7. Khi p99 tăng, dump JFR, mở bằng JMC và so sánh CPU samples, allocation, GC và thread contention với stable.
8. Thử một tình huống lỗi có kiểm soát: dừng rollout, chuyển weight về stable hoặc dùng `kubectl rollout undo`.
9. Xác minh readiness, SLI, dữ liệu và queue sau rollback.
10. Ghi lại nguyên nhân, thời gian phục hồi và thay đổi cần thực hiện trước lần phát hành tiếp theo.

**Câu hỏi tự đánh giá:**

1. Vì sao weighted traffic giữa hai Deployment phù hợp hơn một RollingUpdate khi cần canary 1%?
2. Readiness và liveness probe khác nhau thế nào?
3. Khi nào nên dùng `default.jfc` và khi nào dùng `profile.jfc`?
4. Vì sao JFR không thay thế metrics và distributed tracing?
5. `JFR.dump` khác `JFR.stop` ở điểm nào?
6. Vì sao phải so sánh recording cùng event settings và time window?
7. `kubectl rollout undo` có hoàn tác ConfigMap và database migration không?
8. Tại sao schema migration phải tương thích với bản stable trong cửa sổ rollback?
9. Khi nào cần dừng rollout ngay mà không chờ thêm mẫu?
10. Vì sao không nên quay lại một JDK có lỗ hổng đã biết?

## 18. Tài liệu chính thức

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): trạng thái LTS và mốc hỗ trợ của Java 25; lịch hỗ trợ cần đối chiếu theo vendor.
- [Oracle JDK 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): sử dụng JFR và `jcmd` để chẩn đoán JVM đang chạy.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): tùy chọn `-XX:StartFlightRecording`, settings, max age, max size và dump khi thoát.
- [Oracle JDK 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): cú pháp `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop`.
- [Oracle JDK 25 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): overhead, profile recording và phân tích hiệu năng bằng JFR.
- [Oracle JDK 25 — Recording API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): quản lý dung lượng và tuổi dữ liệu của recording.
- [Oracle JDK 25 — EventStream API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): đọc event stream từ JFR.
- [JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html): xem recording, CPU, thread, lock và GC.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, rollout history và rollback Deployment.
- [Kubernetes — Rolling Back a Deployment](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/): xem revision và dùng `kubectl rollout undo`.
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/): ý nghĩa và cách cấu hình ba loại probe.
- [Gateway API — HTTP Traffic Splitting](https://gateway-api.sigs.k8s.io/guides/user-guides/traffic-splitting/): weighted backend routing để triển khai canary.

> **Ghi nhớ:** Chỉ tăng traffic khi bản canary đạt SLO và dữ liệu đủ đại diện. Duy trì JFR continuous bằng `default.jfc`, dùng `profile.jfc` cho điều tra ngắn, gắn recording với đúng image/JDK/pod và giữ file ngoài vòng đời pod. Khi cần quay lui, khôi phục traffic hoặc image đã biết tốt, đồng thời kiểm tra riêng config, schema và dữ liệu vì rollback Deployment không tự hoàn tác các thành phần đó.
