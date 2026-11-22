# Thực thi container theo yêu cầu với Cloud Run services

Cloud Run services là nền tảng serverless của Google Cloud để chạy container nhận request qua HTTP hoặc gRPC. Đội phát triển đóng gói ứng dụng Java cùng runtime và thư viện thành container image, triển khai image lên Cloud Run, rồi cấu hình cách service nhận traffic, mở rộng instance và giới hạn tài nguyên. Google Cloud quản lý hạ tầng chạy container và tự điều chỉnh số instance theo tải.

Điểm quan trọng là Cloud Run chạy **container do ứng dụng cung cấp**. Ứng dụng vẫn phải khởi động web server, lắng nghe đúng cổng, xử lý nhiều request đồng thời, quản lý trạng thái và đóng tài nguyên đúng cách. Mô hình serverless giảm việc vận hành máy chủ, nhưng không loại bỏ trách nhiệm thiết kế một dịch vụ HTTP an toàn và có khả năng mở rộng.

Bài học này tập trung vào Cloud Run services theo mô hình request-driven, từ hợp đồng container, vòng đời revision/instance đến concurrency, autoscaling, triển khai Java và vận hành production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Cloud Run service thực thi container theo request như thế nào.
- Phân biệt service, revision và instance.
- Đóng gói ứng dụng Java thành container image đáp ứng hợp đồng Cloud Run.
- Cấu hình concurrency, min/max instances, timeout và tài nguyên.
- Hiểu scale-to-zero, cold start và tác động của cấu hình CPU.
- Thiết kế ứng dụng stateless, xử lý request đồng thời và dừng graceful.
- Triển khai revision mới, chia traffic và rollback.
- Cấu hình IAM invocation, service identity và quan sát chi phí.

## 1. Cloud Run services là gì?

**Cloud Run service** là một dịch vụ được triển khai từ container image và cung cấp một endpoint để nhận request. Cloud Run tạo các container instance khi có traffic, phân phối request đến instance phù hợp và tăng hoặc giảm số instance theo nhu cầu cùng các giới hạn đã cấu hình.

Các workload thường phù hợp:

- REST API hoặc backend HTTP viết bằng Java/Spring Boot.
- API gRPC giữa các service.
- Webhook receiver từ hệ thống bên ngoài.
- Backend cho ứng dụng web hoặc mobile.
- Service xử lý request ngắn hoặc vừa, gọi database, cache, object storage và API khác.
- HTTP endpoint nhận event được đẩy từ Pub/Sub hoặc Eventarc.

Cloud Run services phù hợp với ứng dụng cần phục vụ request liên tục khi có traffic. Nếu công việc là batch hoặc chạy đến khi hoàn tất mà không cần giữ endpoint nhận request, hãy cân nhắc Cloud Run Jobs. Nếu muốn triển khai một function theo mô hình event-driven mà không tự quản lý container, Cloud Run functions là lựa chọn khác trong hệ sinh thái Cloud Run.

### Cloud Run quản lý gì và ứng dụng quản lý gì?

| Thành phần | Cloud Run quản lý | Đội phát triển quản lý |
|---|---|---|
| Hạ tầng | Máy chủ, scheduling, môi trường chạy container và autoscaling | Chọn region, tài nguyên và cấu hình service |
| Container | Tạo instance từ image, phân phối request | Build image, runtime, dependency và entrypoint |
| Mạng | HTTPS endpoint, ingress và kết nối theo cấu hình | HTTP routing, TLS ở các kết nối riêng, xác thực ứng dụng |
| Mở rộng | Tăng/giảm instance theo tải và giới hạn | Concurrency, min/max instances, khả năng chịu tải của dependency |
| Vòng đời | Tạo và dừng instance theo nhu cầu | Khởi động nhanh, xử lý SIGTERM, không phụ thuộc bộ nhớ instance |
| Dữ liệu | Cung cấp kết nối đến các dịch vụ cloud | Lưu trạng thái bền vững, transaction, backup và idempotency |
| Bảo mật | IAM integration, service identity và secret integration | Cấp quyền tối thiểu, xác thực request và bảo vệ dữ liệu |

Cloud Run không tự biến một ứng dụng có state trong RAM thành ứng dụng phân tán an toàn. Nếu nhiều instance cùng xử lý request, dữ liệu nghiệp vụ phải được lưu trong dịch vụ có độ bền và semantics phù hợp.

## 2. Service, revision và instance

Ba khái niệm này xuất hiện thường xuyên khi triển khai và vận hành.

- **Service:** tên logic và endpoint của ứng dụng, ví dụ `orders-api`.
- **Revision:** một phiên bản bất biến của cấu hình service và container image tại thời điểm deploy. Mỗi lần triển khai cấu hình hoặc image mới thường tạo revision mới.
- **Instance:** một container đang chạy từ revision cụ thể. Một revision có thể có nhiều instance khi traffic tăng.

~~~mermaid
flowchart TD
    A["Cloud Run service: orders-api"] --> B["Revision 00001"]
    A --> C["Revision 00002"]
    B --> D["Instance A"]
    B --> E["Instance B"]
    C --> F["Instance C"]
    G["HTTPS traffic"] --> H["Traffic routing"]
    H --> B
    H --> C
~~~

Service là điểm truy cập ổn định. Revision giữ lịch sử triển khai và có thể nhận một phần traffic. Instance là đơn vị thực thi container; số instance có thể thay đổi trong khi service vẫn giữ nguyên URL.

Một deployment mới không nhất thiết thay thế ngay mọi request bằng revision mới nếu traffic splitting đang được cấu hình. Có thể đưa revision mới vào staging, gửi một tỷ lệ traffic nhỏ rồi tăng dần khi các chỉ số đạt yêu cầu.

## 3. Hợp đồng container của Cloud Run

Container image phải đáp ứng một số điều kiện để Cloud Run gửi request đến được ứng dụng.

### Lắng nghe cổng được cung cấp

Cloud Run truyền biến môi trường `PORT` cho container. Ứng dụng phải lắng nghe trên cổng này và bind vào `0.0.0.0`, tức tất cả network interface trong container.

Không chỉ bind vào `127.0.0.1` hoặc `localhost`, vì request từ proxy của Cloud Run cần truy cập qua network interface của container. Cũng không hard-code một cổng khác với cấu hình service.

Với Spring Boot, có thể cấu hình:

~~~properties
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

`EXPOSE 8080` trong Dockerfile chỉ là metadata mô tả cổng của image; nó không khiến ứng dụng tự lắng nghe cổng đó. Web server bên trong process phải thực sự bind đúng `PORT`.

### Container phải khởi động và nhận request

Ứng dụng cần hoàn tất startup trong giới hạn nền tảng và cấu hình probe. Tránh tải dữ liệu lớn, gọi nhiều API bên ngoài hoặc chạy migration dài trong lúc khởi động nếu không cần thiết. Các bước khởi tạo nặng làm tăng cold start và có thể khiến instance không sẵn sàng đúng hạn.

Cloud Run hỗ trợ startup probe và liveness probe để kiểm tra tình trạng container theo cấu hình. Endpoint health nên phản ánh khả năng phục vụ thực tế; không nên trả healthy khi service chưa thể nhận request hoặc dependency thiết yếu chưa sẵn sàng.

### Container không nên phụ thuộc vào filesystem bền vững

Filesystem ghi được trong container là tạm thời và vòng đời gắn với instance; dữ liệu local không phải nơi lưu trạng thái lâu dài. Dung lượng ghi tạm cũng tiêu thụ tài nguyên bộ nhớ theo đặc tính môi trường Cloud Run.

Dùng Cloud Storage, database hoặc dịch vụ lưu trữ bền vững cho file và dữ liệu cần giữ lại sau khi instance dừng. File tạm có thể dùng trong một request nếu ứng dụng dọn dẹp và không giả định request tiếp theo sẽ chạy trên cùng instance.

## 4. Ví dụ ứng dụng Java với Spring Boot

Một service Java đơn giản có thể cung cấp endpoint kiểm tra sức khỏe và endpoint đọc đơn hàng. Ví dụ dùng Java 21 và Spring Boot 3.

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
@RequestMapping
class OrdersController {

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("ok");
    }

    @GetMapping("/orders/{orderId}")
    public OrderResponse getOrder(@PathVariable String orderId) {
        // Thay bằng service/repository có kiểm tra quyền truy cập.
        return new OrderResponse(orderId, "PROCESSING");
    }
}

record HealthResponse(String status) {
}

record OrderResponse(String orderId, String status) {
}
~~~

Ứng dụng cần dependency Spring Web và Spring Boot Maven Plugin trong `pom.xml`. Cấu hình cổng và địa chỉ bind:

~~~properties
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

Controller trên chỉ minh họa cấu trúc HTTP. Trong ứng dụng thật, endpoint nghiệp vụ cần xác thực caller, kiểm tra quyền trên order và đọc dữ liệu từ kho bền vững. Không trả một trạng thái giả lập như PROCESSING cho request production.

### Dockerfile nhiều giai đoạn

Ví dụ Dockerfile dùng Maven để build JAR và một JRE image để chạy:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/orders-api.jar app.jar
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec java -jar app.jar --server.port=${PORT:-8080} --server.address=0.0.0.0"]
~~~

Ví dụ giả định Maven tạo artifact `target/orders-api.jar`; cấu hình `finalName` hoặc Spring Boot build output tương ứng trong project. CI nên chạy unit test và integration test trước khi build image phát hành; `-DskipTests` trong ví dụ chỉ để minh họa bước đóng gói image.

Dùng base image có JRE phù hợp với Java version của ứng dụng. Có thể tối ưu image bằng cách chọn runtime image gọn, loại bỏ file build không cần thiết và chạy process với quyền user không đặc quyền theo chính sách bảo mật của tổ chức.

## 5. Build và deploy lên Cloud Run

Một quy trình phổ biến là build image, đẩy image lên Artifact Registry rồi triển khai service.

Trước tiên, cần có Docker repository trong Artifact Registry ở region đã chọn và quyền build/push phù hợp. Ví dụ dùng Cloud Build để build image:

~~~bash
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
~~~

Sau đó deploy:

~~~bash
gcloud run deploy orders-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1 \
  --region REGION \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --concurrency 40 \
  --min 0 \
  --max 20 \
  --timeout 300s \
  --no-allow-unauthenticated
~~~

Thay `REGION`, `PROJECT_ID` và service account bằng giá trị của môi trường. Repository `apps` cần được tạo trước. Lệnh trên yêu cầu xác thực IAM khi invoke service; nếu endpoint phải công khai, có thể cấu hình cho phép unauthenticated invocation nhưng vẫn cần xác thực và phân quyền ở tầng ứng dụng nếu dữ liệu yêu cầu.

Các flag minh họa:

| Flag | Ý nghĩa |
|---|---|
| `--region` | Region triển khai service |
| `--service-account` | Service identity mà container sử dụng khi gọi Google Cloud APIs |
| `--concurrency` | Số request đồng thời tối đa được gửi đến một instance |
| `--min` | Số instance tối thiểu cần duy trì |
| `--max` | Giới hạn số instance |
| `--timeout` | Thời gian tối đa cho một request |
| `--no-allow-unauthenticated` | Không cấp quyền invoke công khai |

Cloud Run tạo revision mới từ image và cấu hình triển khai. Sau deploy, hãy kiểm tra service URL, revision được tạo, trạng thái ready và log startup trước khi chuyển traffic production.

## 6. Request lifecycle và autoscaling

Một request thường đi qua các bước:

1. Client gửi HTTPS request đến URL của Cloud Run service.
2. Lớp ingress và routing chọn revision theo traffic allocation.
3. Cloud Run chọn instance sẵn sàng hoặc tạo instance mới nếu tải vượt năng lực hiện có.
4. Container nhận request trên cổng `PORT`.
5. Java web server xử lý request, gọi dependency và tạo response.
6. Response được trả về client; instance có thể tiếp tục xử lý request khác hoặc được dừng khi không còn nhu cầu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Cloud Run router
    participant I as Container instance
    participant D as Database / API
    C->>R: HTTPS request
    R->>I: Route to ready instance
    I->>D: Query or update
    D-->>I: Result
    I-->>R: HTTP response
    R-->>C: Response
~~~

Autoscaler điều chỉnh số instance dựa trên traffic và mức sử dụng tài nguyên, trong phạm vi cấu hình và quota. Khi tải tăng, Cloud Run có thể khởi động thêm instance. Khi tải giảm, instance có thể bị giảm hoặc dừng.

Không nên giả định số instance tăng ngay lập tức trong mọi tình huống. Startup time, giới hạn max instances, quota vùng và tốc độ tăng traffic có thể tạo ra độ trễ hoặc request bị từ chối. Nếu hệ thống có burst traffic lớn, hãy kiểm thử tải và thiết kế retry ở client theo backoff cùng jitter.

## 7. Scale-to-zero, cold start và minimum instances

Khi cấu hình minimum instances bằng 0, Cloud Run có thể scale service về zero khi không có traffic trong một khoảng thời gian. Điều này giúp tránh giữ instance chạy liên tục cho service ít được sử dụng.

Khi request tiếp theo đến, nền tảng cần khởi động container trước khi xử lý. Khoảng khởi động bổ sung này góp phần tạo **cold start**.

Cold start chịu ảnh hưởng bởi:

- Kích thước image và số layer cần tải.
- Thời gian khởi động JVM và Spring application context.
- Số lượng bean, thư viện và tác vụ khởi tạo.
- Kết nối database, cache hoặc API được mở trong startup.
- Startup probe và thời gian service sẵn sàng nhận request.

### Giảm cold start

- Dùng image gọn và loại bỏ dependency không cần thiết.
- Tránh gọi nhiều dịch vụ bên ngoài trong constructor hoặc static initializer.
- Chỉ khởi tạo kết nối khi cần, nhưng tránh tạo client mới cho mọi request.
- Đo startup duration và request latency p95/p99 trước khi tối ưu.
- Dùng minimum instances nếu yêu cầu latency đầu tiên quan trọng hơn chi phí giữ instance.
- Cân nhắc startup CPU boost nếu startup bị giới hạn bởi CPU và cấu hình này có lợi qua số liệu đo.

Minimum instances có thể giữ sẵn năng lực để giảm cold start, nhưng làm tăng chi phí. Cần phân biệt cấu hình min instances ở cấp service và revision nếu dùng cả hai; xác minh cấu hình đang áp dụng cho traffic production.

## 8. Concurrency: nhiều request trên một instance

Cloud Run cho phép cấu hình số request đồng thời tối đa trên một instance. Một instance có thể phục vụ nhiều request cùng lúc, tùy concurrency setting và khả năng ứng dụng.

Concurrency cao có thể tăng hiệu suất sử dụng CPU và bộ nhớ, giảm số instance cần thiết. Nhưng nó cũng làm tăng tranh chấp trong ứng dụng Java và tải đồng thời lên database/API phía sau.

### Không giả định request được xử lý tuần tự

Spring Boot server thường dùng thread pool để xử lý request. Các request đồng thời có thể truy cập cùng singleton bean, static field, cache cục bộ hoặc connection pool.

- Dữ liệu request phải nằm trong biến cục bộ hoặc request context riêng.
- Singleton bean không nên giữ mutable state theo từng request.
- Collection dùng chung phải thread-safe nếu có cập nhật đồng thời.
- Database transaction và conditional update cần bảo vệ dữ liệu nghiệp vụ.
- Connection pool cần giới hạn và phù hợp với concurrency.

Ví dụ, không lưu userId của request hiện tại vào field của singleton service. Hai request đồng thời có thể ghi đè giá trị và làm truy cập sai dữ liệu. Hãy truyền user identity qua tham số method hoặc security context được quản lý đúng.

### Chọn concurrency dựa trên tải

| Concurrency mỗi instance | Lợi ích | Rủi ro cần kiểm tra |
|---|---|---|
| Thấp | Ít request tranh chấp; phù hợp tác vụ nặng CPU hoặc bộ nhớ | Cần nhiều instance hơn khi tải tăng |
| Trung bình | Cân bằng sử dụng tài nguyên và số instance | Cần đo thread pool và connection pool |
| Cao | Tăng khả năng chia sẻ tài nguyên instance | Có thể tăng latency, heap pressure và tải database |

Bắt đầu bằng một giá trị vừa phải, sau đó chạy load test với payload thực tế. Đo throughput, latency p95/p99, CPU, memory, số connection và lỗi 429/5xx. Không chọn concurrency chỉ dựa trên số request trung bình.

### Giới hạn tổng tải lên backend

Giả sử một service có thể chạy tối đa 20 instance và mỗi instance cho phép 40 request đồng thời. Về lý thuyết, hệ thống có thể có đến 800 request đang hoạt động cùng lúc. Nếu mỗi request mở một kết nối database riêng, database có thể bị quá tải.

Cần phối hợp concurrency với:

- Connection pool mỗi instance.
- Max instances ở Cloud Run.
- Giới hạn connection của database.
- Rate limit của API bên ngoài.
- Queue hoặc Cloud Tasks khi cần hấp thụ tải.
- Timeout và circuit breaker cho dependency.

Max instances là một công cụ bảo vệ backend, nhưng nếu giới hạn quá thấp, request có thể phải chờ hoặc bị từ chối khi traffic tăng. Cần kiểm thử cả hai phía: khả năng phục vụ của Cloud Run và khả năng chịu tải của dependency.

## 9. CPU, memory và request timeout

Mỗi revision có cấu hình CPU và memory. Chọn quá ít CPU có thể làm tăng thời gian xử lý và startup; chọn quá ít memory có thể khiến JVM gặp OutOfMemoryError hoặc instance bị dừng.

Với Java, cần đo heap cùng native memory, thread stack, direct buffer, class metadata và các thư viện native. Không đặt `-Xmx` bằng toàn bộ memory limit vì process còn cần vùng nhớ ngoài heap. Dùng container-aware JVM và kiểm tra memory metrics trong load test.

Cloud Run có các lựa chọn CPU allocation khác nhau, trong đó request-based allocation phù hợp service chủ yếu xử lý trong lúc có request; instance-based allocation phù hợp workload cần CPU ngoài thời gian xử lý request. Cấu hình CPU allocation ảnh hưởng đến hành vi nền và billing. Không dựa vào thread nền để làm công việc nghiệp vụ sau khi trả HTTP response nếu không chọn mô hình CPU và cơ chế thực thi phù hợp.

Request timeout là giới hạn thời gian chờ cho một request. Khi request vượt timeout, client có thể nhận lỗi dù backend đã thực hiện một phần hoặc toàn bộ side effect. Vì vậy:

- Chọn timeout theo SLA và phân bố latency thực tế.
- Đặt timeout của dependency thấp hơn timeout tổng của request.
- Dùng idempotency key cho thao tác có thể bị client retry.
- Không dùng HTTP request dài làm cơ chế chạy batch kéo dài nếu có thể chuyển sang queue/job.
- Ghi nhận trạng thái công việc nếu client cần polling hoặc nhận callback sau.

Cloud Run service có giới hạn request timeout theo sản phẩm và cấu hình hiện hành; hãy kiểm tra giới hạn region/runtime khi chọn giá trị dài. Timeout lớn không thay thế thiết kế xử lý bất đồng bộ.

## 10. Thiết kế stateless và lưu trạng thái bền vững

Một instance có thể bị dừng sau khi request hoàn tất hoặc khi autoscaler giảm tải. Request tiếp theo có thể đến instance khác. Vì vậy, ứng dụng cần xem mỗi request là độc lập.

Không dùng các nơi sau làm nguồn trạng thái chuẩn:

- Biến static hoặc field singleton chứa trạng thái nghiệp vụ.
- File local trong container.
- Session chỉ nằm trong RAM của một instance.
- Cache local không có cơ chế tái tạo hoặc invalidation.

Có thể dùng:

| Nhu cầu | Dịch vụ lưu trữ phù hợp |
|---|---|
| Dữ liệu quan hệ và transaction | Cloud SQL, AlloyDB hoặc database phù hợp |
| Document/key-value | Firestore hoặc datastore phù hợp |
| Object/file | Cloud Storage |
| Cache chia sẻ | Memorystore hoặc cache service phù hợp |
| Hàng đợi và event | Pub/Sub hoặc Cloud Tasks |
| Trạng thái quy trình dài | Database hoặc workflow/orchestration service |

Session affinity có thể giúp tăng khả năng một client được gửi đến cùng instance, nhưng không phải bảo đảm lưu trữ session bền vững. Instance vẫn có thể dừng hoặc thay thế. Nếu cần session, hãy lưu dữ liệu ở external store và chỉ giữ cache local như một tối ưu.

## 11. Xử lý tác vụ nền và request retry

Cloud Run service chủ yếu phục vụ request. Không nên khởi chạy một thread nền rồi trả HTTP 200 trong khi công việc quan trọng vẫn chưa được lưu hoặc giao cho hệ thống khác. Instance có thể bị dừng và công việc sẽ mất.

Với công việc bất đồng bộ:

- Ghi yêu cầu vào Pub/Sub hoặc Cloud Tasks rồi trả mã job/accepted.
- Dùng Cloud Run service làm push endpoint cho event khi cần xử lý HTTP.
- Dùng Cloud Run Jobs cho batch hoặc tác vụ chạy đến khi hoàn tất.
- Dùng workflow engine khi quy trình có nhiều bước, retry và trạng thái dài hạn.

Client có thể retry khi timeout hoặc mất kết nối, do đó endpoint ghi dữ liệu cần idempotency. Ví dụ, `POST /orders` có thể nhận `Idempotency-Key`; database lưu key và kết quả để lần gửi lại trả kết quả cũ thay vì tạo đơn hàng mới.

Nếu Cloud Run service nhận event từ Pub/Sub push, handler cần trả status code phù hợp với kết quả xử lý. Response lỗi có thể khiến event được gửi lại theo retry policy. Vì thế, validate payload, idempotency và dead-letter policy vẫn cần thiết.

## 12. Graceful shutdown và quản lý tài nguyên

Cloud Run có thể dừng instance khi scale down hoặc thay thế revision. Ứng dụng nên xử lý tín hiệu dừng như SIGTERM:

- Ngừng nhận hoặc bắt đầu xử lý công việc mới khi shutdown.
- Cho request đang chạy hoàn tất trong khoảng thời gian nền tảng cho phép.
- Đóng connection pool, HTTP client và executor có quản lý.
- Không dựa vào shutdown hook để ghi trạng thái nghiệp vụ quan trọng; thao tác đó phải được commit trước khi trả response.
- Không để thread nền tiếp tục ghi dữ liệu sau khi request hoặc instance đã kết thúc.

Spring Boot hỗ trợ graceful shutdown qua cấu hình server shutdown và lifecycle bean. Ví dụ:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

Cloud Run gửi SIGTERM trước khi kết thúc instance và chỉ dành một khoảng grace ngắn (10 giây) trước khi buộc dừng process. Đặt timeout của Spring thấp hơn khoảng này để còn thời gian đóng tài nguyên. Shutdown hook là cơ hội đóng tài nguyên, không phải cơ chế đảm bảo hoàn tất một job dài.

## 13. Bảo mật và service identity

Cloud Run service có thể yêu cầu IAM authentication hoặc cho phép truy cập công khai. Với service nội bộ, caller thường cần quyền `roles/run.invoker` trên service. Với public endpoint, có thể cho phép unauthenticated invocation, nhưng các thao tác nghiệp vụ vẫn cần cơ chế xác thực phù hợp như OAuth/JWT hoặc session.

Tách hai danh tính:

- **Caller identity:** principal được phép invoke Cloud Run service.
- **Runtime service identity:** service account mà container sử dụng khi gọi Google Cloud APIs.

Runtime service account nên có quyền tối thiểu, ví dụ đọc một bucket cụ thể hoặc truy cập đúng secret. Không dùng service account mặc định có quyền quá rộng chỉ để ứng dụng chạy được.

Với service-to-service invocation, caller có thể lấy Google-signed ID token có audience phù hợp với URL service đích và gửi trong Authorization header. Service đích kiểm tra IAM Invoker permission. Không dùng access token tùy ý thay cho ID token khi cơ chế yêu cầu ID token.

Secret có thể được inject qua Secret Manager integration dưới dạng environment variable hoặc mounted volume. Hãy chọn cách phù hợp với yêu cầu cập nhật và rotation; tránh bake secret vào image hoặc commit trong repository. Không log secret value hay token.

## 14. Revision, traffic splitting và rollback

Mỗi deployment tạo revision mới. Có thể triển khai revision mới mà chưa chuyển toàn bộ traffic, sau đó chia traffic giữa revision cũ và mới để canary.

Ví dụ, sau khi deploy revision mới, dùng lệnh:

~~~bash
gcloud run services update-traffic orders-api \
  --region REGION \
  --to-revisions orders-api-00002-abc=10,orders-api-00001-def=90
~~~

Ví dụ gửi 10% traffic đến revision mới và 90% đến revision cũ. Thay tên revision bằng giá trị thực từ service. Khi đã xác nhận ổn định, chuyển 100% traffic sang revision mới:

~~~bash
gcloud run services update-traffic orders-api \
  --region REGION \
  --to-revisions orders-api-00002-abc=100
~~~

Nếu có lỗi, chuyển traffic về revision cũ. Rollback routing chỉ ảnh hưởng request mới; nó không hoàn tác dữ liệu hoặc side effect mà revision mới đã thực hiện. Nếu hai revision cùng truy cập database, schema và API contract cần tương thích trong thời gian rollout.

### Quy trình canary đề xuất

1. Build image bất biến theo commit hoặc build ID.
2. Deploy revision mới và xác minh startup/health.
3. Chạy smoke test qua revision tag hoặc môi trường staging.
4. Gửi một tỷ lệ nhỏ traffic đến revision mới.
5. So sánh latency, 5xx, CPU, memory và lỗi nghiệp vụ.
6. Tăng tỷ lệ nếu đạt ngưỡng.
7. Chuyển toàn bộ traffic hoặc rollback.
8. Giữ revision cũ trong thời gian quan sát và kiểm tra dependency.

Không chỉ nhìn tỷ lệ HTTP 2xx. Một service có thể trả 200 nhưng ghi dữ liệu sai hoặc xử lý event trùng; cần metric nghiệp vụ và kiểm tra dữ liệu sau release.

## 15. Quan sát và vận hành production

Cloud Run tích hợp với Cloud Logging và Cloud Monitoring. Ứng dụng nên phát log có cấu trúc và correlation ID để kết nối request log với log nghiệp vụ.

Các chỉ số cần theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Request count | Lưu lượng theo service/revision |
| Request latency p50/p95/p99 | Độ trễ người dùng quan sát |
| 4xx/5xx và timeout | Lỗi client, lỗi server và request vượt thời gian |
| Instance count | Số container instance đang hoạt động |
| CPU và memory utilization | Mức sử dụng tài nguyên, nguy cơ quá tải |
| Container startup latency | Thời gian khởi động instance mới |
| Concurrency | Số request đồng thời trên instance |
| Container restarts / startup probe failures | Lỗi khởi động hoặc sức khỏe container |
| Dependency latency/errors | Thời gian và lỗi database, cache, API ngoài |
| Cost by revision/service | Chi phí theo cấu hình và traffic |

Log không nên chứa access token, secret, password, dữ liệu cá nhân hoặc toàn bộ request body nếu không cần. Ghi request ID, route, status code, duration và mã lỗi đã chuẩn hóa.

Khi latency tăng, phân tách thời gian startup, xử lý trong ứng dụng và chờ dependency. Nếu chỉ tăng concurrency hoặc memory mà không tìm nguyên nhân, chi phí có thể tăng mà lỗi gốc vẫn còn.

## 16. Chi phí và lựa chọn cấu hình

Chi phí Cloud Run phụ thuộc vào tài nguyên CPU/memory, thời gian hoặc mức cấp phát theo billing mode, request, network egress và các dịch vụ phụ trợ. Minimum instances, CPU allocation luôn sẵn sàng và logging/monitoring cũng có thể ảnh hưởng tổng chi phí.

| Cấu hình | Tác động thường gặp |
|---|---|
| Min instances = 0 | Có thể scale-to-zero, tiết kiệm khi idle nhưng có cold start |
| Min instances lớn hơn 0 | Giảm cold start, tăng chi phí giữ năng lực |
| Concurrency cao | Có thể giảm số instance nhưng tăng tranh chấp và memory pressure |
| Concurrency thấp | Cần nhiều instance hơn nhưng cô lập request tốt hơn |
| Max instances thấp | Bảo vệ dependency và chi phí, nhưng có thể giới hạn throughput |
| CPU/memory lớn hơn | Có thể giảm thời gian xử lý, nhưng tăng mức tài nguyên tính phí |
| CPU luôn được cấp phát | Hỗ trợ tác vụ nền trong giới hạn mô hình, nhưng có thể làm tăng chi phí |

Đừng tối ưu chi phí bằng cách giảm max instances mà không xem queueing, timeout và user latency. Cũng đừng tăng min instances cho mọi service nếu chỉ một số endpoint cần latency thấp. Có thể tách service theo đặc tính tải để cấu hình phù hợp hơn.

## 17. Checklist trước khi đưa Cloud Run service vào production

- [ ] Container lắng nghe trên biến môi trường `PORT` và bind `0.0.0.0`.
- [ ] Image có runtime Java phù hợp và không chứa secret.
- [ ] Startup probe/health endpoint phản ánh đúng khả năng phục vụ.
- [ ] Service không phụ thuộc filesystem hoặc RAM instance làm nguồn state bền vững.
- [ ] Singleton bean, static field và cache local an toàn với concurrency.
- [ ] Concurrency, CPU, memory, min/max instances được load test.
- [ ] Connection pool và tải lên database/API được giới hạn.
- [ ] Timeout và retry có idempotency cho thao tác ghi.
- [ ] Công việc nền được giao cho queue/job thay vì thread chạy sau response.
- [ ] Service identity có quyền tối thiểu; caller có IAM Invoker phù hợp.
- [ ] Secret được lấy từ Secret Manager và có chính sách rotation.
- [ ] Graceful shutdown đóng tài nguyên và không phụ thuộc vào state trong RAM.
- [ ] Revision mới được canary, quan sát và có phương án rollback.
- [ ] Có dashboard cho latency, lỗi, concurrency, instance, CPU/memory và dependency.
- [ ] Đã ước tính chi phí cả Cloud Run lẫn database, cache, network và logging.

## Tự kiểm tra

1. Cloud Run service khác Cloud Run Job ở kiểu workload và vòng đời thực thi như thế nào?
2. Vì sao container phải bind vào `0.0.0.0` và đọc cổng từ biến `PORT`?
3. Service, revision và instance khác nhau ở điểm nào?
4. Scale-to-zero giúp tiết kiệm chi phí nhưng có thể làm tăng latency đầu tiên ra sao?
5. Concurrency cao ảnh hưởng thế nào đến thread safety và connection pool của ứng dụng Java?
6. Vì sao không nên giữ session hoặc trạng thái đơn hàng duy nhất trong RAM của một instance?
7. Khi client retry một request sau timeout, idempotency giúp bảo vệ nghiệp vụ như thế nào?
8. Max instances có thể bảo vệ database ra sao và đánh đổi điều gì?
9. Rollback traffic về revision cũ có hoàn tác side effect của revision mới không?
10. Cần theo dõi những metric nào để phân biệt cold start với dependency latency?

Cloud Run services cho phép đưa ứng dụng Java đóng gói trong container lên Google Cloud và chỉ mở rộng năng lực khi có request. Để tận dụng mô hình này, container phải tuân thủ hợp đồng cổng và startup, ứng dụng phải stateless và thread-safe, còn concurrency cùng max instances phải phù hợp với dependency phía sau. Revision, traffic splitting, IAM và observability giúp triển khai service theo từng bước và vận hành với chi phí có thể kiểm soát.

