# Giảm cold start cho ứng dụng Java trên Cloud Run

Một API đơn hàng viết bằng **Java/Spring Boot** được triển khai trên **Cloud Run**. Ban ngày hệ thống xử lý hàng trăm request mỗi phút; ban đêm hầu như không có traffic. Request đầu tiên sau một khoảng yên ắng đôi khi mất vài giây, trong khi những request tiếp theo thường nhanh hơn. Đội phát triển muốn giảm độ trễ này nhưng không muốn duy trì quá nhiều instance nhàn rỗi hoặc làm chi phí tăng mất kiểm soát.

Đó là bài toán **cold start**: Cloud Run cần khởi tạo một container instance mới trước khi instance có thể phục vụ request. Với Java, thời gian này còn bao gồm việc JVM và framework khởi động. Giải pháp tốt phải phân biệt **khởi tạo hạ tầng, khởi tạo JVM, chuẩn bị ứng dụng và xử lý request**, sau đó chọn tối ưu theo số liệu thực tế.

Bài học thuộc chương **Cloud Run** của mô-đun **CLOUD_PROVIDERS_GCP**: lựa chọn Google Cloud services, quản lý project/IAM/VPC, triển khai từ Artifact Registry, kết nối Cloud SQL/Cloud Storage, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Nội dung tập trung vào **giảm cold start của dịch vụ Java trên Cloud Run**, không nhầm với độ trễ của một request nóng hoặc lỗi từ hệ thống phụ thuộc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện các pha cold start và phân biệt **cold start**, **first-request latency** và **warm-request latency**.
2. Chọn cấu hình **minimum instances**, **startup CPU boost**, **concurrency**, CPU/memory dựa trên SLO và ngân sách.
3. Giảm chi phí khởi tạo **JVM**, Spring Boot, dependency injection, connection pools và container image.
4. Thiết kế **startup probe** để không nhận request quá sớm, đồng thời tránh kéo dài khởi tạo vì làm việc không cần thiết.
5. Thử nghiệm có đối chứng, xem metrics/logs, phân tích p95/p99 và chi phí mỗi request.
6. Áp dụng chiến lược rollout/rollback an toàn và xử lý các triệu chứng thường gặp.

## 2. Cold start thực sự xảy ra ở đâu?

### 2.1. Các giai đoạn điển hình

~~~mermaid
flowchart LR
    R["Request đến"] --> S["Cloud Run cần instance mới"]
    S --> C["Chuẩn bị image / container"]
    C --> J["Khởi chạy JVM"]
    J --> F["Khởi tạo framework / beans"]
    F --> D["Chuẩn bị dependency tối thiểu"]
    D --> L["Ứng dụng sẵn sàng trên PORT"]
    L --> H["Xử lý request"]
~~~

Mỗi phần có một nguồn chi phí thời gian khác nhau:

| Giai đoạn | Dấu hiệu | Hướng tối ưu |
| --- | --- | --- |
| Cấp phát instance và container | Độ trễ phát sinh khi scale từ 0 hoặc tăng số instance. | Minimum instances, điều chỉnh concurrency, startup CPU boost. |
| Khởi chạy JVM | Java process lên chậm, class loading/JIT ban đầu. | JDK phù hợp, giảm classpath, CDS/AOT/native khi có lợi, JVM flags được benchmark. |
| Khởi tạo ứng dụng | Spring tạo nhiều beans, quét classpath, chạy migration hoặc gọi remote services. | Giảm autoconfiguration không dùng, bỏ công việc nặng khỏi startup. |
| Kết nối dependency | Chờ Cloud SQL, Secret Manager, DNS hoặc API ngoài. | Tối ưu timeout, connection pool, IAM/mạng và thứ tự khởi tạo. |
| Request đầu tiên | Endpoint đầu tiên kích hoạt lazy bean, JIT, truy vấn DB hoặc nạp cache. | Preload có chọn lọc, tối ưu xử lý request, đo riêng lần đầu. |

**Cold start không xảy ra ở mọi request.** Một instance đã khởi tạo có thể phục vụ nhiều request theo concurrency đã cấu hình. Cloud Run có thể tạo thêm instance dù dịch vụ đang có instance ấm nếu traffic tăng hoặc instance hiện tại không còn đủ capacity.

### 2.2. Ba phép đo không nên gộp

- **Startup duration:** thời gian từ lúc Java process bắt đầu tới khi ứng dụng sẵn sàng. Đây chỉ là một phần của cold start toàn tuyến.
- **Cold-request latency:** độ trễ từ phía client khi request cần instance mới, bao gồm routing/queueing, startup và công việc của request.
- **Warm-request latency:** độ trễ khi được phục vụ trên instance đã sẵn sàng; thường dùng làm baseline cho logic nghiệp vụ.

Ví dụ minh họa:

| Phép đo | P50 | P95 | Cách hiểu |
| --- | ---: | ---: | --- |
| Request trên instance ấm | 85 ms | 180 ms | Nền hiệu năng nghiệp vụ. |
| Request khi cần instance mới | 1.900 ms | 3.700 ms | Có thêm phần khởi tạo và chờ instance. |
| Thời gian JVM tới ApplicationReady | 1.150 ms | 1.600 ms | Chưa bao gồm toàn bộ Cloud Run startup. |

Đây là **số liệu giả định**, không phải benchmark chính thức của Cloud Run hay Java. Một vài lần gọi `curl` không đủ để suy p95 đáng tin cậy.

## 3. Giải pháp ở tầng Cloud Run

### 3.1. Minimum instances: giữ sẵn capacity

**Minimum instances** đặt mức instance tối thiểu được Cloud Run duy trì theo phạm vi cấu hình được hỗ trợ. Đối với dịch vụ ít traffic, đặt mức lớn hơn 0 có thể làm giảm xác suất request phải chờ khởi tạo từ 0.

~~~text
min instances = 0:
  không traffic → có thể scale về 0 → request sau cần cold start

min instances = 1:
  có instance được duy trì sẵn → request nhẹ có khả năng được phục vụ ngay
~~~

Điều cần nhớ:

- **Không cam kết loại bỏ mọi cold start.** Scale-out vượt số instance tối thiểu, rollout revision mới, khôi phục instance hoặc sự kiện hạ tầng vẫn có thể tạo instance lạnh.
- **Phát sinh chi phí duy trì instance.** Mô hình tính phí phụ thuộc CPU allocation/billing settings và bảng giá hiện hành.
- Cloud Run có khái niệm mức tối thiểu ở **service** và, trong những cấu hình được hỗ trợ, ở **revision**; khi traffic splitting hoặc giữ revision cũ, phải kiểm tra phạm vi để không duy trì capacity ngoài dự tính.
- Chọn 1, 2 hay nhiều instance phải dựa trên **tải nền, vùng/region, độ tin cậy và SLO**, không theo một con số mặc định cho mọi ứng dụng.

Ví dụ thao tác ghi trên **một dịch vụ đã tồn tại**:

~~~bash
# WRITE: thay đổi minimum instances cấp service theo CLI hỗ trợ.
# Kiểm tra "gcloud run services update --help" trước khi chạy.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --min=1
~~~

Trong một số hướng dẫn/phiên bản CLI, cờ cấu hình **revision-level** có tên gần giống `--min-instances`; không sử dụng hai loại mà chưa xác nhận chúng tác động đến **service** hay **revision**. Để so sánh baseline theo ngân sách, có thể quay về mức 0 theo quy trình thay đổi được phê duyệt.

### 3.2. Startup CPU boost: thêm CPU trong lúc khởi tạo

Cloud Run hỗ trợ **startup CPU boost** trên cấu hình đủ điều kiện: cấp thêm tài nguyên CPU cho giai đoạn khởi động container trong khoảng thời gian do dịch vụ quy định. Điều này thường hữu ích với JVM/Spring Boot vốn cần nhiều CPU để nạp lớp, khởi tạo beans và chuẩn bị runtime.

~~~bash
# WRITE: bật startup CPU boost trên dịch vụ có sẵn.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu-boost
~~~

Startup CPU boost **không làm một kết nối Cloud SQL chậm trở nên nhanh hơn** nếu nút thắt là timeout mạng, và không biến một ứng dụng nhiều I/O thành workload CPU-bound. CPU boost có thể có **mức tính phí bổ sung** trong giai đoạn boost; đối chiếu bảng giá và so sánh chi phí trên mỗi request hoàn thành.

### 3.3. Concurrency quyết định khi nào cần thêm instance

**Container concurrency** giới hạn số request có thể đồng thời được gửi đến một instance. Tăng concurrency phù hợp có thể giúp một số instance ấm phục vụ nhiều request hơn, giảm áp lực scale-out và số lần khởi tạo. Nhưng Java application phải xử lý đồng thời an toàn.

~~~bash
# WRITE: ví dụ thiết lập tối đa 40 request đồng thời/instance.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --concurrency=40
~~~

| Concurrency | Tình huống phù hợp | Rủi ro |
| --- | --- | --- |
| Thấp | Request CPU-intensive, ứng dụng chưa thread-safe, cần cô lập tải. | Cần thêm instances sớm hơn; có thể tăng cold starts/chi phí. |
| Trung bình | API Java có I/O đến database/API, đã đo thread pool và memory. | Cần kiểm soát thread/DB connection pools và request queue. |
| Cao | Workload I/O-bound có kiến trúc đồng thời hiệu quả và đủ CPU/RAM. | p95/p99 tăng do contention, GC, blocking hoặc giới hạn database. |

Không dùng `--concurrency=80` như mẹo tối ưu mặc định. Nếu một request chiếm toàn bộ CPU hoặc kết nối DB, concurrency cao có thể khiến hệ thống chậm hơn dù số cold starts giảm. **Autoscaling, concurrency và max instances là các giới hạn phối hợp**, cần load test cùng nhau.

### 3.4. CPU/memory và CPU allocation

Cloud Run cho phép lựa chọn số vCPU, memory và chế độ phân bổ CPU theo khả năng dịch vụ. Hai điểm:

1. **Ít CPU quá:** JVM bootstrap/JIT chậm, ứng dụng không kịp nhận request hoặc latency tăng.
2. **Nhiều CPU quá:** startup có thể nhanh hơn nhưng chi phí tăng, đặc biệt khi lượng traffic thấp.

Với **request-based CPU allocation**, CPU ngoài lúc xử lý request có thể bị hạn chế theo mô hình dịch vụ. Với **instance-based CPU allocation**, CPU được cấp trong suốt vòng đời instance và có cách tính phí khác. Chọn instance-based khi ứng dụng thật sự cần chạy tác vụ nền ngoài request; **không bật chỉ vì nghĩ nó tự loại cold start**.

Ví dụ cập nhật tài nguyên để benchmark:

~~~bash
# WRITE: cấu hình giả định, phải kiểm tra mức hỗ trợ và chi phí.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu=1 \
  --memory=1Gi
~~~

**Giới hạn `max instances` không phải cách chữa cold start**. Nó có thể kiểm soát ngân sách và số kết nối downstream, nhưng nếu đặt quá thấp khi traffic tăng, request có thể phải chờ hoặc bị từ chối. Ngược lại tăng tối đa vô hạn có thể khiến Cloud SQL cạn connection pool.

## 4. Tối ưu Java và JVM trước khi đổi kiến trúc

### 4.1. Chọn JDK và tránh startup nặng

Đối với dịch vụ Java truyền thống:

- Dùng một **JDK/JRE LTS được hỗ trợ** và base image được cập nhật, phù hợp bytecode và kiến trúc runtime.
- Giảm dependency không sử dụng, classpath và những plugin khởi động không cần thiết.
- Tránh tạo thread pools lớn, đọc toàn bộ cấu hình, tải dataset lớn hoặc gọi API từ xa đồng bộ trong static initializer/constructor.
- Không chạy migration database nặng ở mỗi lần một instance mới được tạo. Dùng migration job/pipeline riêng, có lock và quy trình rollback phù hợp.
- Giữ startup nhất quán; log mốc `application ready` để phát hiện bản phát hành nào khiến thời gian tăng.

Trước khi giảm thời gian startup, **xác định bottleneck là CPU, I/O hay dependency**. Tối ưu JVM flags sẽ ít tác dụng nếu Spring Boot đang đợi một kết nối database timeout 10 giây.

### 4.2. JVM flags: benchmark, không sao chép mù

Các cờ dưới đây là **ứng viên thử nghiệm**, không phải cấu hình “tốt nhất” cho mọi Java workload:

~~~bash
# Ví dụ biến môi trường cho một JVM dùng cgroups-aware memory limits.
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65"

# Một thí nghiệm khác khi muốn giảm thời gian tối ưu JIT lúc đầu:
JAVA_TOOL_OPTIONS="-XX:TieredStopAtLevel=1 -XX:MaxRAMPercentage=65"
~~~

`-XX:TieredStopAtLevel=1` có thể giảm công việc JIT ban đầu nhưng **giảm hiệu năng tối đa** của một ứng dụng chạy lâu. `MaxRAMPercentage` chỉ giới hạn cách JVM tính heap tương đối; container còn cần memory cho metaspace, thread stacks, native buffers và JIT. Nếu memory đặt quá sát heap, instance có thể bị OOM và làm latency/cold start tệ hơn.

Các cơ chế như **Class Data Sharing (CDS/AppCDS)** hoặc Java **AOT optimizations** có thể giảm một số chi phí nạp lớp/khởi tạo khi được đóng gói đúng với JDK/image tương ứng. Cần đo trên artifact thật và đảm bảo archive tương thích sau update, không coi chúng là thay thế cho tối ưu dependency.

### 4.3. Java native image

Với **GraalVM Native Image** hoặc công cụ native/AOT mà framework hỗ trợ, ứng dụng được biên dịch trước thành executable native. Trong nhiều workload, cách này có thể giảm startup và memory footprint đáng kể.

Đánh đổi cần tính:

| Lợi ích có thể đạt | Chi phí/rủi ro cần đo |
| --- | --- |
| JVM bootstrap/class loading được giảm hoặc loại theo runtime native. | Build pipeline phức tạp, thời gian build và mức tiêu thụ RAM lúc build cao. |
| Có thể phục vụ request sớm hơn khi scale-out. | Reflection, proxies, JNI, serialization, resource loading cần metadata/hỗ trợ phù hợp. |
| Memory nhỏ hơn trong một số ứng dụng. | Peak throughput/latency khác JVM JIT; cần benchmark cùng traffic. |

**Không tự coi native luôn nhanh hơn** cho ứng dụng Java có request dài, thuật toán tính toán nặng hoặc phụ thuộc thư viện chưa hỗ trợ tốt. Quyết định dựa trên startup p95, warm throughput, size, CI build time, khả năng debug và chi phí vận hành.

## 5. Tối ưu Spring Boot đúng chỗ

Spring Boot có thể tốn thời gian khởi tạo vì autoconfiguration, classpath scanning, dependency injection, ORM và connection pools. Các bước có tác dụng thường rõ hơn việc chỉnh cờ JVM ngẫu nhiên:

1. **Đo thời gian khởi tạo theo pha** bằng Spring Boot startup metrics/logs, JVM runtime uptime và tracing.
2. Loại starters không cần (ví dụ không dùng JPA thì không tự kéo database/ORM stack).
3. Giới hạn component scanning về package cần thiết, tránh quét module/plugin không thuộc dịch vụ.
4. Trì hoãn tác vụ ít dùng, nhưng **không đẩy lỗi vào request đầu tiên** một cách vô thức.
5. Giảm synchronous remote calls trong `@PostConstruct` hoặc bean initialization; cache/connection pools cần timeout phù hợp.
6. Kiểm thử **Spring AOT / native support** nếu service phần lớn xử lý các request ngắn và startup là bottleneck lớn.

### 5.1. Ghi mốc sẵn sàng của Spring Boot

Trong một project Spring Boot đã có dependency thông thường:

~~~java
import java.lang.management.ManagementFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupLogger {
    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        long uptimeMs = ManagementFactory.getRuntimeMXBean().getUptime();
        System.out.println("application_ready_jvm_uptime_ms=" + uptimeMs);
    }
}
~~~

Chỉ số này đo **thời gian JVM đã chạy tới ApplicationReadyEvent**; nó **không bao gồm toàn bộ thời gian Cloud Run chờ cấp phát instance/image**. Ghi timestamp, revision và instance identifier theo công cụ logging được hỗ trợ sẽ giúp so sánh từng bản phát hành.

### 5.2. Spring lazy initialization: chỉ dùng sau khi thử nghiệm

~~~properties
# Chỉ là thí nghiệm có kiểm soát, không bật mặc định cho production.
spring.main.lazy-initialization=true

# Spring Boot lắng nghe PORT do Cloud Run cấp.
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

Lazy initialization có thể làm ứng dụng “ready” sớm hơn, **nhưng bean đầu tiên sẽ được tạo lúc request chạm tới nó**; như vậy cold-start latency có thể chỉ bị chuyển sang request đầu tiên. Không bật chế độ này nếu ứng dụng cần phát hiện lỗi cấu hình/DB sớm hoặc SLO của request đầu tiên nghiêm ngặt. Hãy đo cả `ApplicationReady` **và** request đầu tiên trên từng endpoint quan trọng.

### 5.3. Connection pool và cache

Giả sử mỗi instance tạo pool 20 DB connections và Cloud Run có thể scale lên 30 instances: lý thuyết có thể tạo **600 connections** nếu mọi pool đạt mức tối đa. Đây là ví dụ tính capacity, không phải đảm bảo cả 600 kết nối được mở ngay khi startup.

Giảm kích thước pool, tái sử dụng kết nối trong instance và đặt giới hạn phù hợp với Cloud SQL. Tránh mở toàn bộ pool hoặc nạp cache hàng gigabyte **trong startup path** nếu request không cần ngay. Nếu dependency thiết yếu phải sẵn sàng, ưu tiên kiểm tra trạng thái nhỏ và timeout rõ ràng thay vì chờ vô hạn.

## 6. Container image và readiness

### 6.1. Tối ưu image có mục tiêu

Image quá lớn hoặc chứa nhiều dependency không dùng có thể làm tăng công việc phân phối/khởi chạy; tuy nhiên Cloud Run có tối ưu phía nền tảng nên **kích thước image không luôn tỷ lệ thuận với startup latency**.

Nên:

- Dùng **multi-stage build**, chỉ mang JRE/native binary và runtime artifacts vào final image.
- Dùng base image đáng tin cậy, pin theo digest khi phát hành; vá lỗ hổng định kỳ.
- Giữ layers ổn định để tận dụng build cache, loại build tools/secrets khỏi runtime image.
- Khai báo entrypoint trực tiếp, tránh shell script chạy nhiều lệnh không cần trước JVM.
- Không chờ `apt-get`, Maven download hoặc tải package tại **container startup**.

### 6.2. Lắng nghe đúng `PORT`

Cloud Run cấp biến môi trường `PORT` cho ingress container; ứng dụng cần lắng nghe trên **`0.0.0.0`** tại cổng phù hợp, không chỉ `127.0.0.1`.

Ví dụ Dockerfile dành cho một Spring Boot JAR **đã build sẵn** với tên `orders-api.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY orders-api.jar /app/app.jar
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ giả định `orders-api.jar` nằm trong Docker build context và có bytecode tương thích JRE 21. Cần cấu hình Maven/Gradle xuất đúng tên JAR hoặc sửa `COPY` theo artifact thật. `EXPOSE 8080` chỉ là metadata của image; Spring Boot vẫn phải bind đúng `PORT` và Cloud Run phải được cấu hình ingress port phù hợp.

### 6.3. Startup probe: chờ ứng dụng thật sự sẵn sàng

**Startup probe** giúp Cloud Run kiểm tra container khởi tạo thành công theo cơ chế hỗ trợ. Nó **không tự làm startup nhanh hơn**, nhưng giúp tránh coi một process đã mở socket là “đã sẵn sàng” nếu ứng dụng chưa thể phục vụ.

Ví dụ một phần service configuration dạng YAML minh họa:

~~~yaml
spec:
  template:
    spec:
      containers:
        - image: asia-southeast1-docker.pkg.dev/retail-lab/apps/orders-api:release-1
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 2
            failureThreshold: 10
~~~

Đoạn trên **chỉ minh họa cấu trúc bên trong** cấu hình Cloud Run service, không phải manifest đầy đủ để `kubectl apply`. Hãy kiểm tra schema/API và giới hạn startup probe của phiên bản Cloud Run trước khi cấu hình. Endpoint `/readyz` phải kiểm tra điều kiện khởi tạo tối thiểu, không làm truy vấn nặng hoặc gây side effects mỗi lần probe. Nếu timeout quá ngắn hoặc quá nhạy, Cloud Run có thể liên tục khởi tạo lại một container vốn chỉ cần thêm thời gian hợp lệ.

## 7. Ví dụ thực hành: tối ưu một dịch vụ Java

Giả sử image đã build/kiểm thử và được push vào **Artifact Registry**:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/apps/orders-api@sha256:<DIGEST_THAT>
~~~

`<DIGEST_THAT>` chỉ là placeholder: khi chạy phải thay bằng SHA-256 digest thực của image. Có thể deploy từ repository theo tag trong lab nhưng production nên lưu digest trong release manifest để rollback chính xác.

### 7.1. Lấy baseline trước khi chỉnh

~~~bash
# READ-ONLY: xác định cấu hình hiện tại và Cloud Run service URL.
gcloud run services describe orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format=yaml

gcloud run services describe orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format="value(status.url)"
~~~

Ghi lại revision, min instances, CPU/memory, concurrency, startup boost, image digest và trạng thái authentication. Không nhìn thấy cờ trong output có thể là do schema/default của dịch vụ; đối chiếu các trường được hỗ trợ thay vì đoán.

### 7.2. Thay một biến mỗi lần

Trình tự thí nghiệm nên là:

1. **A — Baseline:** min instances 0, CPU/concurrency hiện tại, image gốc.
2. **B — Startup CPU boost:** giữ mọi thứ khác, bật boost và đo.
3. **C — Java startup:** dùng image đã tối ưu classpath/initialization; đo lại.
4. **D — Minimum instances 1:** đo tác động lên first-request latency và chi phí idle.
5. **E — Concurrency:** thử 10/40/80 khi phù hợp, dùng cùng workload và giới hạn CPU/DB.

Không kết luận phiên bản D tốt hơn phiên bản A nếu đồng thời đổi cả image, CPU và số request đến. Hãy bảo đảm thí nghiệm có **cùng vùng, tải, phương án auth, upstream dependencies và quan sát instance lifecycle**.

### 7.3. Bộ lệnh cập nhật minh họa

~~~bash
# WRITE: áp dụng từng thay đổi trong môi trường thử nghiệm.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu-boost

gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --min=1

gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --concurrency=40
~~~

Mỗi lệnh có thể tạo một revision hoặc thay đổi cấu hình phân bổ capacity theo cơ chế Cloud Run. Lệnh trên **không tạo dịch vụ, không mở quyền public** và cũng không cấp quyền Artifact Registry. Với production, chuyển thành IaC/CI/CD có review, rollback và theo dõi Billing.

## 8. Đo lường cold start mà không tự đánh lừa mình

### 8.1. Thu thập đúng loại số liệu

| Tín hiệu | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Startup latency của container | Cloud Run metrics/logs được sản phẩm cung cấp. | Mức độ tốn thời gian khi tạo instance mới. |
| ApplicationReady JVM uptime | Log ứng dụng Java. | Thời gian bên trong JVM tới sự kiện ready. |
| Request latency theo revision | Cloud Run request metrics, logs và application tracing. | Trải nghiệm request, bao gồm cả tác động bên ngoài startup. |
| 5xx/timeout | Cloud Run, app logs, dependency logs. | Phân biệt lỗi readiness, cold start và dependency. |
| Instance count và concurrency | Cloud Monitoring/Cloud Run. | Khi nào Cloud Run scale và có bao nhiêu instance ấm. |
| Cloud SQL latency, connections | Metrics Cloud SQL và app. | Tránh đổ mọi độ trễ lên JVM. |
| Cost/usage | Cloud Billing và Cloud Run metrics. | Kiểm tra hiệu quả đổi latency lấy chi phí. |

Muốn phân biệt cold/warm, liên kết log với **revision/instance** và mốc request đầu tiên theo cơ chế logging của ứng dụng. Không khẳng định một request là cold chỉ vì nó chậm: có thể database nghẽn, cache miss, GC pause hoặc network timeout.

### 8.2. Quy trình thử nghiệm

1. Đo warm latency ở tải ổn định, có đủ số mẫu.
2. Dùng một môi trường kiểm thử có thể tạo instance mới theo quy trình kiểm soát; **không giả định ngừng gửi request một phút luôn khiến Cloud Run scale về 0**.
3. Thu thập nhiều đợt khởi tạo, ghi startup duration, first-request latency, lỗi và instance count.
4. Thử cả **burst traffic**: số request tăng mạnh có thể khiến Cloud Run tạo nhiều instance mới dù min=1.
5. So sánh p50/p95/p99, tỷ lệ timeout, chi phí/1.000 request và các ràng buộc Cloud SQL.
6. Chỉ promote thay đổi khi cải thiện phù hợp SLO và ngân sách ở nhiều lần thử.

Sử dụng **k6, JMeter, Gatling** hoặc công cụ tạo tải được phê duyệt, không chỉ gọi tuần tự `curl`. Nếu service yêu cầu IAM, load generator cần quyền `run.invoker` và gửi identity token hợp lệ; không mở public endpoint chỉ để đo.

### 8.3. Một phép tính đánh đổi

Giả sử (số giả định):

~~~text
Phương án 0:
  min instances = 0
  cold request p95 = 3,0 giây
  warm request p95 = 180 ms
  chi phí nền = thấp hơn

Phương án 1:
  min instances = 1
  phần lớn request lúc tải thấp = phục vụ ngay
  warm request p95 = 180 ms
  chi phí duy trì instance = tăng

Phương án 2:
  min instances = 0 + startup CPU boost + Java optimization
  cold request p95 = 1,4 giây
  warm request p95 = 180 ms
  chi phí duy trì instance = không bắt buộc
~~~

Không có phương án tốt nhất tuyệt đối. Nếu dịch vụ nội bộ chỉ được gọi vài lần/ngày và cho phép 2 giây chờ, giảm startup trong ứng dụng có thể kinh tế hơn minimum instances. Nếu API checkout có yêu cầu latency nghiêm ngặt cho **mọi request**, giữ capacity ấm có thể hợp lý, nhưng vẫn cần tính burst và kế hoạch dự phòng.

## 9. Kiến trúc: cold start không chỉ nằm ở Java

Ví dụ:

~~~mermaid
flowchart LR
    USER["Client"] --> RUN["Cloud Run Java API"]
    RUN --> SQL["Cloud SQL"]
    RUN --> SECRET["Secret Manager"]
    RUN --> STORE["Cloud Storage"]
    IMAGE["Artifact Registry"] -. "Image được dùng khi khởi tạo instance" .-> RUN
    MON["Cloud Monitoring/Logging"] -. "Latency, instance count, errors" .-> RUN
~~~

Những điểm cần kiểm soát:

- **Cloud SQL:** không khởi tạo pool quá lớn cho mỗi instance; đặt timeout và retry giới hạn; không chạy schema migration trong mọi lần startup.
- **Secret Manager:** dùng identity/permissions phù hợp; cân nhắc thời điểm fetch secret và cache hợp lệ, không log giá trị bí mật.
- **Cloud Storage:** không tải cả bucket hoặc dataset lớn trong constructor nếu request đầu tiên chỉ cần metadata nhỏ.
- **Artifact Registry:** image phải tồn tại và principal của Cloud Run có quyền truy xuất; lỗi pull image là lỗi deploy/startup, không phải bottleneck JVM.
- **Ingress/auth:** Cloud Run IAM, TLS, LB và network policy quyết định ai được gọi; tăng tốc startup không thay thế bảo mật.

Một anti-pattern điển hình là application startup gọi lần lượt nhiều dịch vụ mạng mà không có timeout. Nếu một dependency không sẵn sàng, instance có thể khởi động chậm hoặc bị restart; ưu tiên phân loại phụ thuộc **bắt buộc trước khi serve** và **có thể truy cập theo nhu cầu**.

## 10. Bảo mật và CI/CD khi tối ưu

1. **Build immutable image:** ghi Git commit, JDK/base image version và digest của artifact đã push.
2. **Phân quyền:** CI publisher có Artifact Registry Writer tại repo cần thiết; Cloud Run deployer và service agent có quyền cần thiết để deploy/pull; runtime service account chỉ có quyền gọi Cloud SQL/Storage/Secret Manager phù hợp.
3. **Không để secrets trong Dockerfile/JAR:** dùng dịch vụ quản lý bí mật và identity được cấp quyền tối thiểu.
4. **Kiểm soát thay đổi:** thử startup flags trong staging, benchmark, review, deploy canary/traffic splitting khi hỗ trợ và theo dõi revision metrics.
5. **Rollback:** ghi image digest và cấu hình Cloud Run cũ; khi bản mới lỗi, chuyển traffic về revision đã kiểm chứng hoặc redeploy theo quy trình.
6. **Theo dõi chi phí:** minimum instances và instance-based CPU allocation có thể làm tăng chi phí nền; đặt budget alerts và kiểm tra usage.

Một image native/AOT mới có thể giảm cold start nhưng **thay đổi hành vi runtime**. Quy trình phát hành cần thêm kiểm thử reflection, serialization, dependency và endpoint thực tế, không chỉ test startup.

## 11. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Request đầu tiên chậm, request sau nhanh | Cold start/JVM init, JIT, lazy bean hoặc cache miss. | Cloud Run startup metrics, ApplicationReady log, first-request traces. |
| Startup CPU boost gần như không cải thiện | Bottleneck I/O, chờ DB/Secret Manager, throttling ở dependency. | Phân đoạn thời gian startup và timeout network. |
| `min=1` nhưng vẫn có request chậm | Scale-out, revision rollout, instance replacement, app/dependency latency. | Instance count, revision, request concurrency, logs. |
| Tăng concurrency khiến p99 tệ hơn | CPU contention, thread/DB pool, GC hoặc lock contention. | Load test p95/p99, CPU/memory, pool metrics. |
| Container không nhận request hoặc lỗi port | Java chỉ bind localhost, sai `PORT`/entrypoint, startup probe lỗi. | Container logs, `server.port`, `server.address`, probe. |
| App startup nhanh nhưng request đầu chậm | Lazy initialization, JIT, cache/connection warmup vào request. | So sánh ApplicationReady với trace request đầu. |
| OOM khi startup | Heap/native memory vượt giới hạn container. | Cloud Run memory metrics, JVM heap, threads/metaspace. |
| Tăng instances làm Cloud SQL nghẽn | Mỗi instance tạo pool/queries quá lớn. | Cloud SQL connection limit, pool size, max instances. |
| Mỗi deploy đều có lỗi khởi tạo | Sai image/digest, service agent IAM, config/secrets, dependency. | Revision startup logs, Artifact Registry access và health. |
| Chi phí tăng mạnh sau tối ưu | Min instances lớn, CPU allocation luôn bật, scale-out hoặc logging. | Cloud Billing, CPU/memory allocation, instance counts. |

### Quy trình chẩn đoán ngắn

1. **Xác định chính xác revision và timestamp** của request chậm.
2. **Kiểm tra Cloud Run có tạo instance mới không**; nếu không, ưu tiên phân tích latency ứng dụng/dependency.
3. **Đọc log mốc ApplicationReady** và startup probe; nếu Java startup nhanh, xem image/platform/network.
4. **Phân biệt CPU và I/O** bằng profiler/startup logs, CPU/memory/DB metrics.
5. **Kiểm tra concurrency/scale-out**, warm pool và giới hạn downstream.
6. **Thay một biến trong staging**, đo nhiều lần, rollback nếu SLO hay chi phí xấu hơn.

Không giải quyết lỗi `403` từ Cloud SQL bằng việc tăng CPU, hoặc lỗi `PORT` bằng cách luôn giữ 10 instances.

## 12. Bài tập

### Bài 1 — Phân loại độ trễ

Một API có warm p95 = 120 ms; cold p95 = 2,8 giây; Spring báo ApplicationReady sau 1,6 giây. Phần 1,2 giây chênh lệch có chắc hoàn toàn do Cloud Run cấp phát container không? Hãy liệt kê ít nhất ba thành phần có thể ảnh hưởng.

**Gợi ý:** không. Còn routing/queueing, container platform startup, network và công việc request đầu; phải đo theo trace và metrics.

### Bài 2 — Chọn minimum instances

Dịch vụ A chỉ được gọi 20 lần/ngày và chấp nhận cold request khoảng 2 giây. Dịch vụ B là checkout với SLO nghiêm ngặt trong cả thời gian ít traffic. Bạn thử `min=0` hay `min=1` cho từng dịch vụ trước? Phải đo những chi phí nào?

### Bài 3 — Startup CPU boost

Spring Boot khởi tạo 2,5 giây, CPU bận cao trong quá trình tạo beans. Một API khác khởi động 9 giây do timeout kết nối Cloud SQL. Startup CPU boost có khả năng giúp trường hợp nào nhiều hơn, và làm cách nào chứng minh?

### Bài 4 — JVM flags và lazy initialization

Một nhóm bật `-XX:TieredStopAtLevel=1` và `spring.main.lazy-initialization=true`, ApplicationReady giảm từ 1,6 xuống 0,8 giây nhưng request đầu tăng từ 0,2 lên 1,4 giây. Có thực sự cải thiện trải nghiệm người dùng không? Bạn còn cần kiểm tra peak throughput gì?

### Bài 5 — Concurrency và database

Mỗi instance có pool tối đa 15 kết nối Cloud SQL, dịch vụ có thể scale tới 40 instances. Tính tổng số kết nối tối đa giả định. Đề xuất cách giảm rủi ro nghẽn DB khi tăng concurrency hoặc max instances.

**Gợi ý:** 15 × 40 = 600 kết nối nếu tất cả pools dùng hết capacity; cần pool sizing, connection reuse, giới hạn scale và metrics DB.

### Bài 6 — Thử nghiệm có đối chứng

Thiết kế ba lần benchmark để so sánh baseline Java JIT, startup CPU boost và image native. Mỗi lần phải giữ nguyên những biến nào? Nêu phép đo startup p95, first-request p95, warm p95, 5xx và chi phí/1.000 request.

### Bài 7 — Kiểm soát phát hành

Sau khi bật min instances và triển khai revision mới, traffic được chia 80% cho revision cũ và 20% cho revision mới. Tại sao số instance ấm và chi phí có thể khác dự toán ban đầu? Bạn cần đọc cấu hình **service-level/revision-level minimum instances** và traffic split ở đâu?

## 13. Checklist đưa vào production

| Hạng mục | Điều cần kiểm chứng |
| --- | --- |
| **Cold-start baseline** | Có phân biệt startup latency, cold-request và warm-request; đủ mẫu p50/p95/p99. |
| **Instance lifecycle** | Min instances và traffic split được cấu hình có chủ đích, hiểu scale-out vẫn cold. |
| **CPU** | Startup CPU boost, CPU/memory và CPU allocation được benchmark/costed. |
| **Concurrency** | Thread safety, CPU, memory, connection pool và p99 đạt SLO. |
| **JVM** | JDK LTS, dependency footprint, JVM flags và heap được kiểm chứng. |
| **Framework** | Autoconfiguration, lazy beans, remote calls khi startup đã được rà soát. |
| **Readiness** | Bind `0.0.0.0:$PORT`; startup probe đúng endpoint, timeout hợp lý. |
| **Artifact** | Image digest cố định, build lặp lại được, base image được cập nhật. |
| **Dependencies** | Cloud SQL, Storage, secrets, IAM và network có timeout/retry phù hợp. |
| **Security** | Deployer, service agent, runtime identity tách trách nhiệm; không nhúng secret. |
| **Rollout** | Có staging benchmark, SLO monitors, canary/rollback và ownership. |
| **Cost** | Theo dõi billed idle time/min instances, CPU, requests, transfer và logs. |

## 14. Tài liệu tham khảo

Đối chiếu giới hạn cấu hình, cờ CLI và giá với tài liệu Google Cloud/JDK/Spring Boot đang áp dụng:

- [Cloud Run — Optimize performance](https://cloud.google.com/run/docs/tips/general)
- [Cloud Run — Minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [Cloud Run — Startup CPU boost](https://cloud.google.com/run/docs/configuring/services/startup-cpu-boost)
- [Cloud Run — Maximum concurrent requests](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run — CPU allocation/billing settings](https://cloud.google.com/run/docs/configuring/billing-settings)
- [Cloud Run — Health checks](https://cloud.google.com/run/docs/configuring/healthchecks)
- [Cloud Run — Monitoring](https://cloud.google.com/run/docs/monitoring)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Run — Container runtime contract](https://cloud.google.com/run/docs/container-contract)
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Java Class Data Sharing](https://docs.oracle.com/en/java/javase/21/vm/class-data-sharing.html)

**Ghi nhớ:** Cloud Run cold start là tổng hợp các bước tạo instance, khởi chạy JVM và chuẩn bị ứng dụng. **Minimum instances** giảm xác suất phải khởi động mới; **startup CPU boost** giúp những startup CPU-bound; **concurrency** ảnh hưởng tốc độ scale-out; còn tối ưu Java/Spring và dependency loại bỏ công việc thừa. Không có một cấu hình loại bỏ mọi cold start. Hãy **đo đúng pha, thử từng thay đổi, giữ SLO của request đầu và cân bằng với chi phí**.
