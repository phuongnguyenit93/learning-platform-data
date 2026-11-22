# Container runtime contract và yêu cầu ứng dụng

Một image Java chạy tốt bằng `docker run` nhưng khi deploy lên Cloud Run lại báo *container failed to start and listen on the port defined by PORT*. Một batch import dữ liệu được tạo dưới dạng Cloud Run service nhưng không mở HTTP port, nên không thể khởi động. Hai sự cố này xuất phát từ việc ứng dụng **không tuân thủ container runtime contract** của loại tài nguyên Cloud Run đã chọn.

**Container runtime contract** là tập quy tắc về image, process, network, vòng đời, tài nguyên và cách Cloud Run giao việc cho container. Hiểu contract giúp lựa chọn đúng giữa **service**, **job** và **worker pool**, đồng thời tránh lỗi startup, thất thoát dữ liệu tạm, quá thời gian request hay xử lý việc nền không đáng tin cậy.

Bài thuộc chương **Cloud Run** của học phần **CLOUD_PROVIDERS_GCP**, liên hệ với thiết kế project/IAM/VPC, triển khai Java, lưu trữ, cơ sở dữ liệu, CI/CD, khả năng chịu lỗi và chi phí. Nội dung tập trung vào **hợp đồng thực thi và yêu cầu code**, không lặp lại hướng dẫn kiến trúc toàn bộ Google Cloud.

Sau bài này, bạn có thể:

- Chọn đúng Cloud Run resource theo kiểu công việc.
- Đóng gói image Linux/AMD64 và viết HTTP server lắng nghe `0.0.0.0:$PORT`.
- Phân biệt timeout, concurrency, autoscaling, CPU allocation, filesystem tạm và shutdown.
- Tạo ứng dụng Java tối giản, kiểm thử bằng Docker và deploy service/job bằng `gcloud`.
- Dùng service identity, secrets, logs và health checks đúng mục đích.
- Phân tích lỗi startup, `504`, OOM, retry, kết nối mạng và chi phí.

## 1. Contract phụ thuộc vào loại tài nguyên

| Tiêu chí | **Cloud Run service** | **Cloud Run job** | **Cloud Run worker pool** |
|---|---|---|---|
| Cách bắt đầu | HTTP request hoặc event được chuyển thành request | Tạo một job execution theo lịch/lệnh/API | Worker chạy liên tục khi được cấp instance |
| Process phải làm gì? | Mở HTTP server trên đúng ingress port | Làm việc, **thoát khi xong** và trả exit code | Chạy consumer/daemon; không bắt buộc mở HTTP ingress |
| Kết thúc công việc | Trả HTTP response đúng request timeout | `exit 0` thành công, nonzero thất bại | Tự quản xử lý và checkpoint; có thể bị dừng |
| Scaling | Tự động hoặc manual theo cấu hình | Số tasks và parallelism của execution | **Manual scaling**, không tự tăng theo backlog |
| CPU | Theo billing setting và vòng đời instance | Cấp khi task chạy | Cấp trong toàn bộ thời gian instance hoạt động |
| Phù hợp | REST API, webhook, HTTP/gRPC handler | ETL, batch, migration có điểm kết thúc | Pub/Sub/Kafka pull consumer chạy lâu |

Cloud Run hiện còn có **Cloud Run instances** cho các ứng dụng cần điều khiển vòng đời instance trực tiếp. Đây là tài nguyên khác; bài tập trung ba loại trên vì chúng thể hiện rõ nhất sự khác biệt contract.

~~~mermaid
flowchart TD
  A["Cần chạy container trên Cloud Run"] --> B{"Có HTTP request/response?"}
  B -- Có --> C["Service: lắng nghe PORT, trả response"]
  B -- Không --> D{"Có điểm kết thúc?"}
  D -- Có --> E["Job: xử lý rồi exit 0 / nonzero"]
  D -- Không --> F["Worker pool: consumer liên tục, manual scale"]
~~~

**Không dùng service để chạy vô hạn một batch ở startup.** Service cần sẵn sàng nhận request; job không cần HTTP listener; worker pool cần thiết kế khả năng bị restart và xử lý lại message.

## 2. Các yêu cầu chung cho container image

Cloud Run thực thi container Linux 64-bit, hỗ trợ **Linux x86_64 ABI**. Image multi-platform phải có biến thể **`linux/amd64`**. Google Cloud chấp nhận Docker manifest và OCI image phù hợp; mã nguồn có thể viết bằng Java, Go, Python, Node.js hoặc ngôn ngữ khác.

| Yêu cầu | Hệ quả thực tế |
|---|---|
| Image Linux/AMD64, đúng ENTRYPOINT/CMD | Binary ARM-only hoặc Windows container không chạy |
| Các thư viện native/JNI tương thích Linux x86_64 | Ứng dụng Java dùng thư viện native có thể lỗi dù JVM hoạt động |
| Runtime process sống và báo lỗi đúng | Process thoát tức thì làm service không thể phục vụ |
| Tên file trong image tương thích UTF-8 | Tránh lỗi deploy do tên file encoding không hỗ trợ |
| Không đòi privileged container/host kernel | Không chạy `sudo`, mount filesystem bằng syscall, eBPF hoặc Docker-in-Docker kiểu đặc quyền |
| Image và dependencies được bảo trì | Pin version/digest, quét lỗ hổng và tránh nhúng credential |

**Lưu ý phân quyền:** chạy bằng user `root` bên trong image **không có nghĩa** được quyền root trên host của Cloud Run; sandbox chặn quyền host/privilege escalation. Đối với ứng dụng bình thường, vẫn nên dùng user không đặc quyền và image tối giản.

## 3. Service: bắt buộc lắng nghe `0.0.0.0:$PORT`

Một Cloud Run **service** có một container nhận ingress và tùy chọn các **sidecar containers**. Cloud Run tự đưa biến môi trường `PORT` vào **ingress container** (mặc định 8080, có thể cấu hình khi deploy). Ingress process phải:

1. Lấy cổng từ `PORT` thay vì hardcode `8080`.
2. Bind trên **`0.0.0.0`**, không chỉ `127.0.0.1` hoặc `localhost`.
3. Bắt đầu lắng nghe trong thời gian startup hợp lệ, sau khi khởi tạo những thành phần bắt buộc.
4. Trả HTTP response trong giới hạn request timeout.

~~~text
Client HTTPS
  → Google Cloud Run frontend (TLS termination)
  → HTTP/1 đến ingress container: 0.0.0.0:$PORT
  → Java HTTP handler
  → response / status code / logs
~~~

Cloud Run **kết thúc TLS ở lớp frontend** cho HTTP/HTTPS và gRPC. Ingress container thông thường nhận HTTP không TLS; nếu chọn **HTTP/2 end-to-end**, ứng dụng cần xử lý **h2c** (HTTP/2 cleartext), không tự bật HTTPS trên ingress port để “an toàn hơn”. Giữa các service, vẫn cần **authentication/authorization** và lựa chọn ingress/network phù hợp.

### Java thuần JDK: một HTTP server đúng contract

Ví dụ dùng `com.sun.net.httpserver.HttpServer` (có sẵn trong JDK) để học contract, không cần framework. Tên file **`App.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class App {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PORT", "8080")
        );

        HttpServer server = HttpServer.create(
            new InetSocketAddress("0.0.0.0", port), 0
        );
        ExecutorService pool = Executors.newFixedThreadPool(8);
        server.setExecutor(pool);

        server.createContext("/healthz", exchange -> {
            respond(exchange, 200, "ok");
        });
        server.createContext("/", exchange -> {
            respond(exchange, 200, "hello from Cloud Run");
        });

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("SIGTERM: stopping HTTP server");
            server.stop(1);
            pool.shutdown();
        }));

        server.start();
        System.out.println("Listening on 0.0.0.0:" + port);
    }

    private static void respond(
        HttpExchange exchange, int status, String body
    ) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8"
        );
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

Ví dụ khai báo **`PORT` có default** để chạy local, nhưng trên Cloud Run phải dùng giá trị được inject. Với Spring Boot, thông thường có thể cấu hình `server.address=0.0.0.0` và `server.port=${PORT:8080}` trong `application.properties`; với Quarkus/Micronaut hoặc framework khác phải kiểm tra đúng tên config.

**Lỗi phổ biến:** image Dockerfile có `EXPOSE 8080` nhưng app lại bind `localhost:8080` hoặc `8081`. `EXPOSE` chỉ mô tả cổng trong image; nó không khiến process tự lắng nghe, không thay thế việc đọc `PORT`.

## 4. Đóng gói bằng Docker và kiểm thử local

Dockerfile đa giai đoạn giúp giữ image runtime chỉ chứa JRE và bytecode. Ví dụ build `App.java` từ mục 3 và `BatchApp.java` ở mục 9:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY App.java BatchApp.java ./
RUN javac --add-modules jdk.httpserver -d /app App.java BatchApp.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app /app
USER 65532:65532
EXPOSE 8080
CMD ["java", "--add-modules", "jdk.httpserver", "-cp", "/app", "App"]
~~~

Trong lab, lưu hai file Java và Dockerfile ở **thư mục thử nghiệm riêng**. Nếu chỉ thử service, có thể bỏ `BatchApp.java` khỏi `COPY`/`javac`. Với production, nên pin base image digest, có kiểm tra dependencies/JDK, CVE scanning và provenance.

~~~bash
docker build --platform linux/amd64 -t cloudrun-contract:lab .

# Dùng cổng 9090 để chứng minh ứng dụng đọc PORT thay vì hardcode 8080.
docker run --rm -e PORT=9090 -p 9090:9090 cloudrun-contract:lab

# Ở terminal khác:
curl -i http://localhost:9090/healthz
curl -i http://localhost:9090/
~~~

Kỳ vọng hai endpoint trả HTTP 200. Dừng container bằng `docker stop` và xem log shutdown. **Local thành công chưa chứng minh IAM, ingress, quota hoặc VPC trên Cloud Run đã đúng**; cần kiểm thử sau deploy.

## 5. Startup, health checks và shutdown

Cloud Run service yêu cầu ingress container **lắng nghe trong vòng 4 phút** từ lúc instance khởi động; các container trong instance cần khỏe. Nếu Java app mất quá lâu để tải dependencies, kết nối database hoặc chạy migration lúc startup, revision có thể không sẵn sàng.

| Giai đoạn | Cloud Run làm gì? | Ứng dụng cần làm gì? |
|---|---|---|
| **Startup** | Cấp CPU khi khởi động; đánh giá cổng hoặc startup probe | Đọc config, mở cổng đúng, warmup có giới hạn |
| **Serve** | Chuyển HTTP request, có thể nhiều request đồng thời | Xử lý concurrency an toàn, timeout, cancellation |
| **Idle** | Có thể scale down theo cấu hình | Không coi local state là bền vững |
| **Shutdown** | Gửi `SIGTERM`, khoảng **10 giây** sau có thể `SIGKILL` | Dừng nhận việc mới, flush/checkpoint trong giới hạn |

Các probe có mục đích khác nhau:

- **Startup probe** kiểm tra quá trình khởi động (TCP, HTTP hoặc gRPC theo cấu hình). Nếu không cấu hình, service có mặc định kiểm tra TCP port.
- **Liveness probe** phát hiện container treo và có thể restart. Không biến một lần Cloud SQL lỗi thành “mọi Pod phải restart”.
- **Readiness probe** giúp Cloud Run ngừng gửi **request mới** tới instance chưa sẵn sàng rồi phục hồi khi probe đạt; khác liveness.

Health endpoint như `/healthz` cần trả kết quả nhanh, an toàn; không thực hiện migration hay tác vụ nặng. Với ứng dụng có sidecar (proxy/agent), cấu hình **container startup order** và startup probes để ingress container không mở cổng khi thành phần phụ thuộc chưa sẵn sàng.

**`SIGTERM` không cam kết xử lý hết mọi request.** Instance có thể ngừng vì scaling, rollout, maintenance hoặc lỗi. Với công việc có tác dụng phụ, dùng trạng thái bền vững, idempotency key và retry thay vì chỉ tin `shutdownHook`.

## 6. Request timeout và concurrency của service

### Request timeout khác startup timeout

Cloud Run service có **request timeout mặc định 5 phút (300 giây)**; cấu hình tối đa **60 phút (3.600 giây)**. Giới hạn này bao gồm cả thời gian chờ instance khởi động để xử lý request. Nếu quá hạn, frontend đóng kết nối và trả **HTTP 504**, nhưng container **có thể tiếp tục xử lý** request đã bị ngắt. Đó là lý do quan trọng để giữ idempotency và timeout của downstream.

~~~text
HTTP request → container xử lý → trả response trước timeout
                     │
                     └── quá hạn → Cloud Run 504 đến client
                                        (process có thể chưa dừng)
~~~

Không thiết kế client retry một thao tác thanh toán không có idempotency key sau `504`: lần đầu có thể đã ghi dữ liệu. Dùng Cloud Tasks, Pub/Sub hoặc job cho công việc dài/thực thi không đồng bộ thay vì giữ kết nối HTTP quá lâu; với kết nối dài hơn 15 phút, tài liệu khuyến nghị thiết kế client có khả năng reconnect/retry.

### Concurrency là **mỗi instance**, không phải tổng của cả service

`--concurrency=20` cho phép tối đa **20 request đồng thời trên một instance**. Khi traffic tăng, Cloud Run có thể tạo thêm instance trong phạm vi scaling settings/quota. Mặc định concurrency phụ thuộc công cụ triển khai và cấu hình CPU; nên đặt giá trị có chủ đích rồi xác minh trên revision thực tế thay vì phụ thuộc một con số ghi nhớ.

| Concurrency | Đánh đổi thường gặp |
|---|---|
| **1** | Cô lập request và giảm tranh chấp RAM/CPU, nhưng có thể cần nhiều instance |
| **10–40** | Điểm thử phù hợp với API Java thông thường nếu thread pool và DB đủ capacity |
| **Cao** | Giảm số instance nhưng tăng áp lực heap, CPU, threads và DB connections |

Ví dụ một Java API có 2 GiB RAM, mỗi request có thể dùng 50 MiB tạm. Với concurrency 40, **riêng dữ liệu request** có thể cần khoảng 2 GiB (chưa kể JVM heap, metaspace, thread stacks và writable filesystem). Vì vậy cần đo heap, memory và P95/P99 latency dưới load thật.

Các giới hạn cần điều chỉnh cùng nhau:

- Application server thread pool và maximum active HTTP connections.
- HikariCP/DB pool size, Cloud SQL connection quota và request deadline.
- CPU/memory mỗi instance, `max-instances`, min instances và retry của client.
- Tốc độ cold start và startup CPU boost cho Java.

## 7. CPU, việc nền và filesystem tạm

### CPU allocation không giống nhau giữa các billing settings

Với Cloud Run service:

- **Request-based billing** (mặc định): CPU được cấp chủ yếu trong lúc xử lý request, startup và shutdown. Khi request kết thúc, việc nền có thể bị giảm CPU đáng kể.
- **Instance-based billing:** CPU được cấp trong toàn vòng đời instance; phù hợp với một số xử lý ngắn ngoài request, nhưng vẫn có thể bị scale-down/restart và bị tính phí khi idle.
- **Jobs** và **worker pools** được cấp CPU trong thời gian task/instance hoạt động theo billing của loại tài nguyên.

**Sai lầm:** HTTP handler trả `202 Accepted` rồi tạo Java thread chạy hàng giờ để xử lý file. Với request-based service, thread nền có thể bị treo CPU hoặc bị giết khi instance biến mất. Cách đúng là **enqueue** công việc vào Pub/Sub/Cloud Tasks hoặc tạo Cloud Run job và để worker độc lập xử lý.

### Writable filesystem là in-memory, không bền

Cloud Run cho ghi vào container filesystem, nhưng dữ liệu:

- Sử dụng **bộ nhớ instance** và có thể khiến container OOM.
- Có thể còn tồn tại giữa các request trên **cùng một instance**, nhưng **biến mất** khi instance dừng.
- **Không được đồng bộ** giữa các instance hoặc revisions.

Ví dụ ứng dụng nhận file 300 MiB, tạo tệp tạm 600 MiB trong `/tmp` và dùng heap 500 MiB: có thể vượt memory dù image chỉ vài chục MiB. Xóa tệp tạm bằng `try/finally` hoặc dùng **in-memory volume có size limit**; với file cần lưu lâu, dùng Cloud Storage. Mount Filestore/Cloud Storage khi có nhu cầu phải qua **Cloud Run managed volume mounts**, không chạy `mount -t nfs` bằng process đặc quyền trong container.

| Dữ liệu | Chỗ phù hợp |
|---|---|
| Tệp tạm nhỏ, có thể tạo lại | `/tmp` với hạn mức memory và cleanup |
| Ảnh/PDF người dùng tải lên | Cloud Storage và kiểm soát quyền object |
| Dữ liệu giao dịch, lock, session dùng chung | Cloud SQL/Firestore/Memorystore theo yêu cầu |
| File POSIX cần dùng chung | Filestore qua volume integration khi tương thích |
| Secrets | Secret Manager qua API/managed secret mounts |

**Không giữ session người dùng hoặc bộ đếm giao dịch chỉ trong biến static của Java.** Một service có thể có nhiều instance và scale-to-zero; trạng thái cần chia sẻ phải ở dịch vụ lưu trữ ngoài container.

## 8. Environment variables, IAM và kết nối mạng

Cloud Run tự inject một số biến môi trường; không nên định nghĩa đè biến dành riêng cho runtime.

| Tài nguyên | Biến tự cấp quan trọng | Ý nghĩa |
|---|---|---|
| **Service (ingress container)** | `PORT` | Cổng bắt buộc cho HTTP server |
| **Service** | `K_SERVICE`, `K_REVISION`, `K_CONFIGURATION` | Nhận diện service/revision |
| **Job** | `CLOUD_RUN_JOB`, `CLOUD_RUN_EXECUTION` | Job và execution hiện tại |
| **Job** | `CLOUD_RUN_TASK_INDEX`, `CLOUD_RUN_TASK_COUNT`, `CLOUD_RUN_TASK_ATTEMPT` | Chia việc và theo dõi retry |
| **Worker pool** | `CLOUD_RUN_WORKER_POOL`, `CLOUD_RUN_REVISION` | Nhận diện worker pool/revision |

**Quyền truy cập dịch vụ:** mỗi Cloud Run revision/job có **runtime service account**. Dùng **Application Default Credentials (ADC)** trong Google Cloud client libraries (ví dụ `StorageOptions.getDefaultInstance()` trong Java) để gọi Cloud Storage, Pub/Sub, Secret Manager hoặc Cloud SQL connectors; **không nhúng JSON key vào image**.

- Người **deploy** cần IAM để cập nhật Cloud Run và `iam.serviceAccounts.actAs` trên runtime service account.
- Người/hệ thống **gọi** một private service cần `roles/run.invoker` (hoặc quyền tương đương) và **ID token** có audience hợp lệ.
- **Runtime service account** chỉ được cấp quyền nghiệp vụ cụ thể, ví dụ Object Viewer trên một bucket hoặc Pub/Sub Publisher trên một topic; `roles/run.invoker` không thay quyền đọc dữ liệu.
- Secret được đưa qua **Secret Manager integration** hoặc API; biến môi trường chứa plaintext thông thường không phù hợp để lưu mật khẩu quan trọng.

Với kết nối Cloud SQL/private APIs, phải kiểm tra **hai điều kiện độc lập**: (1) IAM/DB authentication và (2) mạng/DNS/egress. Cloud Run **services/jobs** hỗ trợ **Direct VPC egress** theo cấu hình; các kiểu resource mới có thể có hỗ trợ Direct VPC ingress khác nhau, không suy luận từ worker pool sang service. Outbound TCP connections có thể bị reset khi hạ tầng thay đổi; dùng timeout, connection pool kiểm tra kết nối chết và retry có giới hạn.

## 9. Job: hoàn thành công việc rồi thoát với exit code

**Cloud Run job** không phục vụ HTTP request. Container chạy command, xử lý công việc, **kết thúc bằng `exit 0` nếu thành công** hoặc **nonzero** nếu thất bại. Không cần mở `PORT` hay chạy web server. Một execution có thể gồm nhiều task song song; **Cloud Run không tự chia dữ liệu** cho các task.

Các biến môi trường job giúp chia tập dữ liệu. Ví dụ file **`BatchApp.java`** sau in thông tin task; ứng dụng thực tế cần xử lý partition tương ứng bằng idempotency key/checkpoint bền vững:

~~~java
public class BatchApp {
    public static void main(String[] args) {
        int index = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_INDEX", "0")
        );
        int count = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_COUNT", "1")
        );
        int attempt = Integer.parseInt(
            System.getenv().getOrDefault("CLOUD_RUN_TASK_ATTEMPT", "0")
        );

        try {
            System.out.printf(
                "Processing partition %d/%d, attempt=%d%n",
                index, count, attempt
            );
            // Thực tế: đọc partition index; ghi kết quả idempotently.
            // Không chỉ dựa vào attempt để chống ghi trùng.
        } catch (Exception ex) {
            System.err.println("Batch failed: " + ex.getMessage());
            System.exit(1);
        }
        // Kết thúc main thành công -> exit code 0.
    }
}
~~~

Job có **task timeout mặc định 10 phút**; theo tài liệu hiện hành có thể cấu hình tới **168 giờ**, nhưng task dùng GPU có giới hạn riêng (tối đa 12 giờ ở tính năng preview tại thời điểm viết). **Task timeout áp dụng cho mỗi attempt**, không phải toàn bộ execution; task thất bại có thể được retry theo `max-retries`. Job chạy nhiều giờ có thể bị gián đoạn bảo trì/mất kết nối, vì vậy phải checkpoint/khôi phục.

**Với dữ liệu quan trọng:** sử dụng `CLOUD_RUN_TASK_INDEX` để chia phần việc; lưu trạng thái đã xử lý ở database/object storage; tránh chỉ ghi kết quả vào `/tmp` rồi exit. Khi `max-retries` bật, cùng task index có thể chạy lại và phải không tạo thanh toán/bản ghi trùng.

## 10. Worker pool: consumer chạy liên tục

**Worker pool** phù hợp ứng dụng kéo message từ Pub/Sub/Kafka hoặc xử lý event dài hạn **không có HTTP request/response làm đầu vào chính**. Container chạy entrypoint như consumer loop; có thể cấu hình probes để bảo đảm các container phụ trợ/worker khỏe.

Khác service: **worker pool không tự autoscale theo số message**. Phải điều chỉnh số instance thủ công hoặc xây cơ chế vận hành riêng; mặc định có một instance, có thể cấu hình về 0 để dừng. Khi instance hoạt động, CPU luôn được cấp và **được tính phí trong suốt thời gian chạy**.

~~~text
Pub/Sub subscription / Kafka topic
            ↓ pull / poll
   Cloud Run worker pool (N instances)
            ↓
  Deserialize → xử lý → durable commit → ACK
~~~

Consumer cần **flow control**, retry/backoff, dead-letter handling và idempotency. Khi nhận `SIGTERM`, dừng poll message mới, ưu tiên ack những message đã commit và trả lại việc chưa xong cho hệ thống queue; thời gian shutdown grace không phải giấy phép chạy job vô hạn.

Nếu luồng công việc thực sự đến từ HTTP webhook, service thường đơn giản hơn. Nếu cần chạy xong rồi thoát hoặc chạy theo lịch, dùng job thay worker pool; nếu cần event delivery qua HTTP Cloud Run, có thể dùng Pub/Sub push hoặc Eventarc.

## 11. Build, deploy service và job trong project lab

Ví dụ dưới đây dựa trên `App.java`, `BatchApp.java` và Dockerfile ở các mục trước. Giả sử một repository Artifact Registry **đã tồn tại**, có billing, Cloud Run/Artifact Registry APIs và runtime service account được cấp quyền cần thiết. Chỉ chạy trong project thử nghiệm đã được phép.

~~~bash
PROJECT_ID="my-cloudrun-lab-project"
REGION="asia-southeast1"
REPO="apps"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/cloudrun-contract:v1"
RUNTIME_SA="run-app@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Repository $REPO cần được tạo sẵn bởi platform/CI.
gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
~~~

### Deploy private service

~~~bash
gcloud run deploy contract-api \
  --image="$IMAGE" \
  --region="$REGION" \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=20 \
  --timeout=60s \
  --max-instances=5 \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated

gcloud run services describe contract-api \
  --region="$REGION" \
  --format="yaml(status.url,status.conditions,spec.template)"
~~~

Ở đây `--port=8080` cấu hình **cổng mà Cloud Run gửi request**, và Cloud Run inject `PORT=8080` vào ingress container. Với image Java trên, nếu sửa `--port=9090`, app phải lắng nghe 9090 mà không cần build lại.

Giả sử người dùng đã được cấp `roles/run.invoker` trên service và được phép gọi endpoint:

~~~bash
URL="$(gcloud run services describe contract-api \
  --region="$REGION" --format='value(status.url)')"

curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$URL/healthz"
~~~

Nếu nhận `401/403`, kiểm tra IAM Invoker, identity thực sự dùng để gọi, ID token audience và ingress settings; **không sửa thành `--allow-unauthenticated` để khắc phục lỗi IAM production**.

### Deploy job từ cùng image

~~~bash
gcloud run jobs create contract-batch \
  --image="$IMAGE" \
  --region="$REGION" \
  --command=java \
  --args="-cp,/app,BatchApp" \
  --tasks=3 \
  --parallelism=2 \
  --max-retries=2 \
  --task-timeout=900s \
  --service-account="$RUNTIME_SA"

gcloud run jobs execute contract-batch \
  --region="$REGION" --wait

gcloud run jobs describe contract-batch --region="$REGION"
~~~

Command override khiến job chạy **`BatchApp`**, không khởi động web server `App`. Ba tasks có chỉ số 0, 1, 2; chạy tối đa hai task đồng thời theo `--parallelism=2`, và thứ tự thực thi không được bảo đảm. Đọc logs theo execution/task để xác nhận `exit code`; `gcloud run jobs execute --wait` chờ execution trong CLI, không biến job thành HTTP endpoint.

**Tác động chi phí:** mỗi lệnh deploy tạo revision/tài nguyên phù hợp; `--max-instances` giới hạn mở rộng service nhưng không hạn chế mọi phí phát sinh từ storage, network hay database. Khi lab xong, kiểm tra owner và dọn service/job cùng image/Artifact Registry resources đúng quy trình.

## 12. Quan sát và xử lý sự cố theo contract

Không bắt đầu bằng việc tăng CPU/RAM cho mọi lỗi. Hãy xác định lỗi nằm ở **image/process**, **HTTP contract**, **IAM**, **mạng** hay **tài nguyên**.

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đúng |
|---|---|---|
| Container không listen trên `PORT` | Bind `127.0.0.1`, hardcode port, app crash, JAR sai entrypoint | Logs startup; test `PORT=9090` local |
| `exec format error` | Image/binary không hỗ trợ `linux/amd64` | `docker build --platform linux/amd64`, xem image manifest |
| Revision không healthy | Startup kéo dài, probe sai path/port, sidecar chưa sẵn sàng | Startup/liveness/readiness, dependency initialization |
| HTTP `504` | Request quá `--timeout`; DB/API chậm hoặc deadlock | Request latency, downstream timeout, idempotency |
| HTTP `500` và instance biến mất | OOM, lỗi ứng dụng, process bị kill | Cloud Run logs, memory, heap, tệp `/tmp` |
| CPU cao/P95 tăng khi concurrency cao | Quá nhiều request dùng chung instance | Điều chỉnh concurrency, JVM heap, thread/DB pool |
| `401/403` gọi service | Không có ID token đúng, thiếu Invoker, ingress chặn | Caller IAM, audience và ingress |
| `403` gọi Cloud Storage | Runtime service account thiếu quyền trên bucket | Resource IAM, ADC, audit logs |
| Cloud SQL timeout | VPC/connector/DNS sai, DB pool cạn hoặc kết nối chết | VPC egress, auth, DB metrics, connection pooling |
| Java background task chưa xong | CPU bị giảm sau HTTP response, instance bị scale down | Billing mode; dùng queue/job/worker pool |
| Job execution failed | Exit nonzero, timeout, OOM hoặc task retry hết | Execution/task logs, exit code, `TASK_ATTEMPT` |
| Worker pool có backlog tăng | Manual scaling quá thấp, consumer không ack, downstream chậm | Subscription backlog, retry/DLQ, số instance worker |

### Lệnh điều tra

~~~bash
gcloud run services describe contract-api --region="$REGION"
gcloud run services logs read contract-api \
  --region="$REGION" --limit=50

gcloud run jobs describe contract-batch --region="$REGION"

# Cloud Logging / Monitoring Console:
# lọc theo service, revision, execution, error code và thời gian deploy.
~~~

Log ứng dụng nên ghi ra **stdout/stderr**, theo dạng structured JSON nếu cần liên kết request ID, revision, latency và lỗi. Không ghi toàn bộ access token, secrets hay payload nhạy cảm. Với `504`, phải kiểm tra xem downstream đã commit thành công hay chưa trước khi retry.

**Outbound connections cũng có lifecycle:** theo runtime contract, idle outbound connections tới VPC có thể timeout sau **10 phút**, ra Internet sau **20 phút**, và có thể bị reset do hạ tầng cập nhật. Java HTTP/DB clients cần kiểm tra kết nối còn sống, reconnect và retry có giới hạn; không dùng TCP connection sống mãi không kiểm chứng.

## 13. Chi phí, an toàn và triển khai production

| Quyết định | Ảnh hưởng | Hướng kiểm soát |
|---|---|---|
| Request-based service | Phù hợp request rời rạc; việc nền sau response không đáng tin | Ghi công việc vào queue trước khi trả response |
| Instance-based service | CPU có thể chạy ngoài request, vẫn bị terminate và tính phí theo instance | Chỉ dùng nếu đúng nhu cầu, theo dõi idle time |
| Min instances | Giảm cold start nhưng giữ instance và có chi phí | Đo P95 latency, không đặt cao vô cớ |
| High concurrency | Ít instance hơn nhưng áp lực heap/thread/DB tăng | Load test và circuit breaker |
| Jobs với retries | Phục hồi lỗi tạm thời, có thể chạy trùng business action | Idempotency và checkpoint |
| Worker pool | Phù hợp consumer liên tục, CPU/instance được tính theo thời gian | Manual scale, giám sát backlog |
| File tạm lớn | Tiêu thụ RAM, dễ OOM | Stream lên Cloud Storage hoặc giới hạn temp |
| VPC, LB, logs, database | Phát sinh chi phí ngoài container | Billing budget, labels, quota và monitoring |

Một số nguyên tắc áp dụng cho **mọi** loại tài nguyên:

- **Runtime identity quyền tối thiểu**, secrets qua Secret Manager; không dùng service account key dài hạn.
- **Ingress theo nhu cầu**: chỉ public khi có yêu cầu thật, nếu không dùng Invoker/IAM và network restrictions thích hợp.
- **Không giả định instance ổn định**: không dựa vào local disk, process singleton hay biến static để giữ trạng thái nghiệp vụ.
- **Tự động hóa phát hành**: pin image tag/digest, kiểm tra lỗ hổng, deploy revision, test health/SLO rồi chuyển traffic/rollback khi cần.
- **Giới hạn tải vào backend**: đặt service max instances, concurrency và application pool dựa trên capacity Cloud SQL/Redis; scaling không thể sửa database bottleneck.
- **Theo dõi chi phí**: Cloud Billing budget alerts không tự đảm bảo ngắt toàn bộ usage; cân nhắc giới hạn công suất, quota và công cụ kiểm soát chi phí theo dịch vụ.

## 14. Tình huống áp dụng: API nhận tài liệu và xử lý bất đồng bộ

Một ứng dụng Java cho phép người dùng upload PDF. Yêu cầu: **API phản hồi nhanh**, file lớn cần OCR vài phút, kết quả phải còn sau khi instance bị restart.

~~~mermaid
flowchart LR
  U["Client"] --> S["Cloud Run service: upload API"]
  S --> O["Cloud Storage: tài liệu gốc"]
  S --> Q["Pub/Sub / Cloud Tasks"]
  Q --> W["Worker pool hoặc service nhận push"]
  W --> R["Cloud Storage: kết quả + Cloud SQL trạng thái"]
  J["Cloud Run job theo lịch"] --> R
~~~

**Thiết kế:**

1. Service bind `0.0.0.0:$PORT`, xác thực caller, giới hạn upload và đưa bytes vào Cloud Storage; trả `202` cùng job ID **sau khi enqueue thành công**.
2. Consumer độc lập xử lý OCR. Nếu chọn **worker pool**, tự quản pull/ack/manual scaling. Nếu dùng **Pub/Sub push tới service**, handler phải hoàn thành trong request timeout và chịu retry. Nếu xử lý theo lô có điểm kết thúc, chọn **job**.
3. Output ghi vào Cloud Storage; trạng thái và idempotency key lưu trong Cloud SQL/Firestore. Khi request hoặc task bị retry, cùng job ID không tạo kết quả trùng.
4. Theo dõi response latency ở service, processing delay/backlog ở queue và success/failure theo task; không đo “API trả 202” là OCR đã hoàn thành.
5. Nếu dùng Cloud SQL private IP, cấu hình Direct VPC egress, IAM/DB credentials và connection pool; không chỉ cấp role rồi giả định mạng hoạt động.

Với yêu cầu này, **không** dùng Java background thread chạy OCR sau khi service đã trả `202` và ghi kết quả vào `/tmp`: cả CPU và local state đều không bảo đảm tồn tại cho đến khi xong.

## 15. Checklist và bài tập thực hành

### Checklist triển khai

- [ ] Chọn đúng **service, job hoặc worker pool** theo loại công việc.
- [ ] Image có biến thể `linux/amd64`, đúng entrypoint và không yêu cầu host privileges.
- [ ] Service đọc `PORT`, bind `0.0.0.0`; job exit code đúng; worker pool có xử lý shutdown.
- [ ] Local test với cổng **khác 8080** và kiểm tra `/healthz`.
- [ ] Timeout, concurrency, CPU, memory, startup probes và max/min instances được chọn bằng phép đo.
- [ ] Không đặt trạng thái quan trọng ở RAM hoặc writable filesystem; dọn file tạm.
- [ ] Không làm việc nền dài sau response theo request-based billing.
- [ ] Dùng runtime service account + ADC, kiểm tra IAM caller và resource IAM riêng.
- [ ] Secret Manager, VPC egress/ingress và kết nối database được kiểm chứng.
- [ ] Có logs, alerts theo lỗi startup, `5xx`, P95, OOM, retry, backlog và chi phí.
- [ ] Rollout, rollback, xử lý `SIGTERM`, idempotency và clean-up đã có owner.

### Bài tập

**Bài 1 — Sửa lỗi startup.** Một app Java dùng `new InetSocketAddress("127.0.0.1", 8080)`. Cloud Run deploy `--port=9090` và revision không sẵn sàng. Hãy sửa code, build lại image `linux/amd64` và nêu hai phép test local xác minh đã tuân contract.

**Bài 2 — Chọn tài nguyên.** Phân loại ba tác vụ: REST API bán hàng, job tổng hợp báo cáo mỗi đêm, consumer liên tục đọc Pub/Sub. Nêu process lifecycle, loại scaling và điều kiện hoàn thành của mỗi tác vụ.

**Bài 3 — Tính concurrency.** Một service được cấu hình `--concurrency=20`, `--max-instances=5`. Tính **mức công suất đồng thời danh nghĩa** theo hai thông số này (20 × 5), rồi giải thích tại sao đó **không phải** SLA về throughput, hard cap tuyệt đối trong mọi thời điểm hoặc bảo đảm luôn có 5 instances.

**Bài 4 — Lỗi `504` và dữ liệu trùng.** Một request ghi đơn hàng vào Cloud SQL xong nhưng không kịp trả response. Client retry. Thiết kế idempotency key/transaction để không tạo hai đơn; nêu nên điều chỉnh request timeout hay chuyển sang queue khi xử lý kéo dài.

**Bài 5 — Memory và background.** Container có 512 MiB RAM, JVM chiếm 300 MiB, tải file tạm 350 MiB vào `/tmp`. Nêu kết quả có thể xảy ra, cách xử lý streaming và vì sao tăng min instances không giải quyết dữ liệu tạm mất khi restart.

**Bài 6 — Job retry.** Ba Cloud Run job tasks xử lý ba phân vùng dữ liệu. Task index 1 lỗi mạng và được retry. Chọn khóa idempotency, vị trí checkpoint và mã thoát cần dùng; chỉ ra vai trò của `CLOUD_RUN_TASK_INDEX` so với `CLOUD_RUN_TASK_ATTEMPT`.

## Tài liệu tham khảo chính thức

- [Cloud Run container runtime contract](https://cloud.google.com/run/docs/container-contract) — image, `PORT`, TLS, lifecycle, filesystem, signals và sự khác biệt resource.
- [Configure container port for services](https://cloud.google.com/run/docs/configuring/services/containers) — ingress port, sidecars và runtime settings.
- [Request timeout for services](https://cloud.google.com/run/docs/configuring/request-timeout) — mặc định, giới hạn và HTTP 504.
- [Concurrency for services](https://cloud.google.com/run/docs/about-concurrency) — nhiều request trên một instance và autoscaling.
- [Configure health checks](https://cloud.google.com/run/docs/configuring/healthchecks) — startup, liveness và readiness probes.
- [Billing settings for services](https://cloud.google.com/run/docs/configuring/billing-settings) — request-based/instance-based CPU.
- [General development tips](https://cloud.google.com/run/docs/tips/general) — tránh background task và quản lý temp files.
- [Create Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs) — tasks, parallelism và retries.
- [Set task timeout for jobs](https://cloud.google.com/run/docs/configuring/task-timeout) — thời gian tối đa mỗi task attempt.
- [Cloud Run worker pools](https://cloud.google.com/run/docs/worker-pools) — consumer liên tục và manual scaling.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — ADC và quyền truy cập Google Cloud APIs.
- [Cloud Run pricing](https://cloud.google.com/run/pricing) — phí service, job, worker pool và cấu hình liên quan.
