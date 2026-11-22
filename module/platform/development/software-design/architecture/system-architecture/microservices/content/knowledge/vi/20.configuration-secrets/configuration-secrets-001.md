# Tách cấu hình ứng dụng khỏi mã nguồn và gói phát hành

> **Bối cảnh:** Software Design Architecture → System Architecture → Microservices → Cấu hình và bí mật. Mục tiêu của tài liệu là thiết kế cách quản lý cấu hình để một bản build ứng dụng có thể chạy ở nhiều môi trường, mỗi môi trường nhận các giá trị thích hợp tại thời điểm triển khai hoặc khởi động, trong khi thông tin nhạy cảm được bảo vệ riêng.

## 1. Vấn đề: vì sao cấu hình bị dính vào mã nguồn gây rủi ro?

Một microservice thường phụ thuộc vào những giá trị thay đổi theo môi trường: URL của dịch vụ khác, kết nối cơ sở dữ liệu, timeout, số kết nối tối đa, cờ tính năng, nơi lưu file, địa chỉ broker, cấp độ log, giới hạn tốc độ và thông tin xác thực.

Khi hard-code các giá trị vào mã Java, đưa chúng trực tiếp vào file cấu hình đóng gói cùng JAR hoặc tạo một image riêng cho mỗi môi trường, nhóm phát triển sẽ gặp các vấn đề:

1. **Cùng một thay đổi cấu hình cũng phải sửa code hoặc build lại:** gây chậm quá trình triển khai và khó phân biệt lỗi cấu hình với lỗi nghiệp vụ.
2. **Không bảo đảm tính đồng nhất giữa môi trường:** image cho staging và production có thể được build từ những thời điểm hoặc dependency khác nhau.
3. **Rò rỉ bí mật:** mật khẩu, token hoặc private key có thể nằm trong Git, artifact registry, build log, Docker layer và file backup.
4. **Rollback khó kiểm soát:** khôi phục image cũ có thể vô tình kéo theo cấu hình môi trường cũ, hoặc cấu hình bên trong image không còn phù hợp.
5. **Mở rộng vận hành phức tạp:** mỗi region, tenant, deployment hoặc môi trường tạo thêm một biến thể build khó quản trị.
6. **Khó kiểm thử đường đi triển khai:** bản chạy trong test không thực sự giống bản đưa lên production.

**Nguyên tắc thiết kế:** Mã nguồn mô tả *ứng dụng làm gì*; artifact phát hành đóng gói *chương trình nào sẽ chạy*; cấu hình triển khai mô tả *chương trình đó chạy như thế nào ở môi trường cụ thể*.

Trong cách thực hành tương ứng với nguyên tắc Config của Twelve-Factor App, các giá trị khác nhau giữa các lần triển khai được cấp từ bên ngoài ứng dụng. **Một artifact bất biến có thể triển khai nhiều lần với cấu hình khác nhau**, miễn là tương thích về schema và dependency.

## 2. Phân biệt code, cấu hình, bí mật và dữ liệu nghiệp vụ

| Loại | Ví dụ | Nên nằm ở đâu? |
| --- | --- | --- |
| Logic nghiệp vụ | Quy tắc xác nhận đơn hàng, cách tính phí | Mã nguồn, version control, artifact |
| Hằng số thuộc thiết kế | Tên trường giao thức, mã trạng thái nội bộ | Mã nguồn, trừ khi thật sự là tham số vận hành |
| Cấu hình không nhạy cảm | URL nội bộ, timeout, pool size, log level | Deployment config, environment, ConfigMap hoặc config service |
| Bí mật | DB password, API token, private key, credential ký JWT | Secret manager hoặc nền tảng quản lý secret; cấp quyền theo workload |
| Cờ bật/tắt hành vi | Enable new checkout, rollout percentage | Feature-flag/config service, có kiểm soát và lịch sử |
| Dữ liệu nghiệp vụ | Giá sản phẩm, đơn hàng, chính sách theo khách hàng | Database hoặc dịch vụ nghiệp vụ có ownership rõ |
| Cấu hình thuộc mã nhưng không theo môi trường | Mapping mặc định, cấu trúc serializer | Có thể giữ trong source nếu không đổi theo deployment |

Không phải mọi dòng trong application.yml đều là “sai”. Một file trong source có thể chứa **cấu trúc cấu hình, key, giá trị mặc định an toàn và placeholder**; điều cần tránh là cố định URL production, tài khoản, quota thật hoặc secret theo môi trường bên trong gói phát hành.

Cần đặc biệt phân biệt:

- **Config** thường có thể đọc được bởi đội vận hành có quyền; **secret** cần chính sách truy cập, mã hóa, xoay vòng, phát hiện rò rỉ và thu hồi riêng.
- **Config deployment** tác động toàn instance/nhóm instance; **business data** được thay đổi bởi nghiệp vụ trong runtime, có validation và audit khác.
- **Feature flag** thay đổi hành vi trong runtime, thường cần rollout/kill switch; không nên coi là phương án vĩnh viễn cho mọi thay đổi logic.
- **Build-time value** bị đóng vào artifact; **runtime value** được cung cấp lúc tạo hoặc khởi động tiến trình; thay đổi runtime value không nhất thiết có hiệu lực ngay nếu ứng dụng chỉ đọc lúc startup.

## 3. Mục tiêu kiến trúc cần đạt

Một thiết kế tách cấu hình tốt nên thỏa những thuộc tính sau:

1. **Build once, deploy many:** dùng cùng một JAR/container image digest cho development, staging và production nếu phần mềm tương thích.
2. **Promotable artifact:** kiểm thử một image ở staging rồi promote đúng digest ấy sang production, không build lại bằng bộ biến môi trường mới.
3. **Cấu hình hiện diện tại runtime:** deployment manifest, orchestrator, environment hoặc config service cung cấp các giá trị.
4. **Bí mật được cô lập:** secret không có mặt trong Git plaintext, artifact, manifest public, Dockerfile, CI log hoặc URL truy cập.
5. **Validation trước khi nhận traffic:** cấu hình thiếu/sai làm service fail fast với thông báo đã loại bỏ dữ liệu nhạy cảm.
6. **Có ownership và lịch sử:** biết ai đổi cấu hình nào, lúc nào, ở môi trường nào, theo phiên bản nào.
7. **Triển khai và rollback có thể tái tạo:** record artifact digest, version cấu hình, version secret/alias và kết quả kiểm tra.
8. **Quan sát được mà không lộ thông tin:** biết cấu hình đã được nạp, kiểm tra được hành vi, nhưng không log secret.
9. **Giới hạn blast radius:** cấu hình sai của một service/tenant không phá hủy toàn bộ microservices.
10. **Không kéo dài downtime khi xoay vòng secret:** hỗ trợ giai đoạn chuyển tiếp credential và quản lý connection.

Các mục tiêu này không đòi hỏi tất cả dự án phải cài một config server. Với service nhỏ, môi trường triển khai cung cấp environment variables và secret manager của nền tảng có thể đã đủ.

## 4. Mô hình ba lớp

~~~text
                    SOURCE CODE
                 Java + tests + schema
                         |
                  build / unit test
                         v
             RELEASE ARTIFACT BẤT BIẾN
             JAR hoặc OCI image + digest
                         |
                 deploy cùng digest
          +--------------+--------------+
          |              |              |
          v              v              v
       DEV             STAGING         PROD
    Config DEV      Config STG      Config PROD
    Secrets DEV     Secrets STG     Secrets PROD
          |              |              |
          +--------------+--------------+
                         v
               APP NẠP CONFIG RUNTIME
                 parse -> validate
                         |
                         v
                  READY -> TRAFFIC
~~~

**Lớp 1 — Source & build:** chứa logic, unit test, khai báo các property cần thiết, ràng buộc kiểu dữ liệu, các default an toàn. Môi trường CI chạy build một lần để tạo JAR/image.

**Lớp 2 — Artifact:** image được định danh bằng digest bất biến (ví dụ sha256 của image). Artifact chứa runtime, binary và tài nguyên cần thiết để chạy nhưng không chứa credential hoặc địa chỉ cố định của production.

**Lớp 3 — Deployment:** triển khai chỉ rõ artifact digest, resource limit, các value không nhạy cảm, nguồn secret, cấu hình network, identity và policy. Thứ tự khởi động: lấy cấu hình → parse/validate → kết nối theo chiến lược phù hợp → công bố readiness → nhận traffic.

Cần hiểu rõ **cấu hình cũng là một phần của trạng thái phát hành**. Việc chỉ biết Git commit của code là chưa đủ để tái tạo trạng thái lỗi production. Nên ghi kèm revision hoặc checksum của config cùng image digest, nhưng không ghi nội dung secret.

## 5. Thiết kế hợp đồng cấu hình trước khi triển khai

Thay vì rải rác những lệnh đọc biến môi trường trong mọi class, hãy xác định một **configuration contract** gồm tên key, kiểu, mục đích, phạm vi, điều kiện bắt buộc, default, mức nhạy cảm và chủ sở hữu.

Ví dụ service xử lý đơn hàng:

| Khóa cấu hình | Kiểu | Bắt buộc | Phạm vi | Chính sách |
| --- | --- | --- | --- | --- |
| PAYMENTS_ENDPOINT | HTTPS URL | Có | Theo môi trường | Không nhạy cảm, validation scheme/host |
| PAYMENTS_TIMEOUT | Duration | Có thể có default | Theo môi trường | Phải dương và nằm trong request deadline |
| DB_JDBC_URL | JDBC URL | Có | Theo môi trường | Không nhét password vào URL |
| DB_USERNAME | String | Có | Theo workload | Thường coi là thông tin cần bảo vệ theo chính sách |
| DB_PASSWORD | Secret | Có | Theo workload | Lấy từ secret manager/runtime |
| ORDER_WORKERS | Integer | Có thể default | Theo deployment | Giới hạn theo DB pool và CPU |
| ENABLE_NEW_CHECKOUT | Boolean | Có thể default false | Theo rollout | Có owner và kế hoạch gỡ bỏ |
| LOG_LEVEL | Enum | Có thể default INFO | Theo instance | Không cho phép bật debug tràn lan tại PROD |

**Không tạo biến riêng cho từng môi trường bằng tên khóa**, chẳng hạn PAYMENTS_URL_DEV / PAYMENTS_URL_PROD trong cùng chương trình rồi viết if-else chọn môi trường. Nên dùng **một khóa PAYMENTS_ENDPOINT**, còn nền tảng triển khai cung cấp giá trị đúng cho môi trường hiện tại.

Quy tắc đặt tên thực tế:

- Ưu tiên nhất quán, dễ truy vết: SERVICE__SECTION__KEY hoặc dạng ENV_VAR_NAME của framework.
- Định nghĩa rõ đơn vị: REQUEST_TIMEOUT_MS, RETENTION_DAYS; hoặc dùng một kiểu Duration chuẩn như 500ms/2s và parse thống nhất.
- Tránh tên mơ hồ như ENABLED, HOST, SIZE nếu thuộc nhiều dependency.
- Khai báo phạm vi: application-wide, per-region, per-tenant, per-request. Các phạm vi này có vòng đời và bảo mật khác nhau.
- Xác định tính tương thích khi đổi tên/xóa khóa; tránh rename bất ngờ khiến replica đang chạy phiên bản cũ hỏng.

## 6. Những kênh cấp cấu hình thường gặp

| Kênh | Ưu điểm | Giới hạn/cảnh báo | Phù hợp |
| --- | --- | --- | --- |
| Environment variables | Đơn giản; hầu hết runtime hỗ trợ | Đổi thường cần restart; dễ bị lộ nếu dump toàn bộ env | Cấu hình quy mô nhỏ/vừa, 12-factor |
| CLI arguments | Tường minh lúc chạy | Có thể xuất hiện trong process list, log; khó quản lý nhiều tham số | Tham số không nhạy cảm, lệnh quản trị |
| File mount từ volume | Hợp với PEM/cert, cấu hình có cấu trúc | Cần chính sách reload, mount permission và quyền file | TLS, file lớn, K8s config volume |
| Kubernetes ConfigMap | Quản trị giá trị không nhạy cảm theo namespace | Không phải kho secret; env var không tự đổi trong process | App trên Kubernetes |
| Kubernetes Secret | Tích hợp Pod; có thể mount/env | Dữ liệu secret biểu diễn base64; cần mã hóa at rest, RBAC, bảo vệ backup | Secret runtime trên K8s |
| Secret manager chuyên dụng | Audit, truy cập theo identity, rotation, version | Có phụ thuộc mạng, SDK, quota, bootstrap | Credential quan trọng, đa môi trường |
| Config service tập trung | Cấu hình dùng chung, version, đôi khi watch/reload | Thêm dependency, consistency và failure mode | Nhiều microservice, dynamic config |
| Feature flag service | Target theo cohort, rollout, kill switch | Có độ trễ/consistency; dễ tích tụ flag cũ | Thay đổi hành vi có kiểm soát |

Không có một kênh phù hợp cho mọi thứ. Một hệ thống có thể dùng environment variables cho URL/timeout, volume cho chứng chỉ, secret manager cho mật khẩu và feature flag service cho rollout.

**Chú ý bảo mật:** Environment variables tiện dụng nhưng không phải “kho lưu secret an toàn” tự thân. Giá trị có thể lọt vào output debug, telemetry, crash dump, môi trường shell hoặc những process có đủ quyền. Với bí mật nhạy cảm, ưu tiên identity của workload và secret manager/volume bảo vệ quyền đọc; giới hạn việc tiết lộ trong log và giao diện quản trị.

## 7. Ví dụ Java thuần: đọc một lần, chuyển thành đối tượng bất biến

Không nên đọc trực tiếp System.getenv ở mọi hàm nghiệp vụ. Đưa việc đọc, chuyển đổi và validate vào **composition root** khi ứng dụng khởi động.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record PaymentConfig(URI endpoint, Duration timeout) {
    public PaymentConfig {
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                "PAYMENTS_ENDPOINT must use HTTPS"
            );
        }
        if (endpoint.getHost() == null) {
            throw new IllegalArgumentException(
                "PAYMENTS_ENDPOINT must have a host"
            );
        }
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                "PAYMENTS_TIMEOUT must be positive"
            );
        }
        if (timeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException(
                "PAYMENTS_TIMEOUT exceeds supported limit"
            );
        }
    }

    public static PaymentConfig fromEnv(Map<String, String> env) {
        String endpoint = required(env, "PAYMENTS_ENDPOINT");
        String timeout = env.getOrDefault("PAYMENTS_TIMEOUT", "PT2S");

        try {
            return new PaymentConfig(
                URI.create(endpoint),
                Duration.parse(timeout)
            );
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException(
                "Payment configuration is invalid", ex
            );
        }
    }

    private static String required(Map<String, String> env, String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing required configuration: " + key
            );
        }
        return value;
    }
}
~~~

Sử dụng tại điểm khởi động:

~~~java
PaymentConfig paymentConfig =
    PaymentConfig.fromEnv(System.getenv());

// Inject đối tượng config vào class cần dùng,
// không đọc hoặc sửa environment giữa luồng nghiệp vụ.
PaymentClient client = new PaymentClient(paymentConfig);
~~~

Ở ví dụ này, Duration.parse nhận định dạng ISO-8601 như PT2S cho 2 giây. Cách parse cụ thể phải được ghi rõ trong contract và thống nhất giữa CI, orchestrator và ứng dụng.

Ưu điểm của cấu trúc trên: dễ kiểm thử với Map giả lập, type-safe, validation tập trung, giảm phụ thuộc toàn cục và tránh mỗi component tự tạo default khác nhau. Đối tượng config nên là bất biến sau khi ứng dụng sẵn sàng; nếu thực sự cần hot reload, dùng một cơ chế snapshot có version và cập nhật nguyên tử.

Đối với secret, hạn chế đưa giá trị vào ngoại lệ hoặc toString của record. Có thể dùng một abstraction cung cấp credential cho client đúng lúc và **không hiển thị secret trong logs**; lựa chọn String/char[]/buffer cần bám theo giới hạn thư viện, không nên hứa rằng xóa dữ liệu trong bộ nhớ JVM là tuyệt đối.

## 8. Ví dụ Spring Boot: binding type-safe và cấu hình ngoài JAR

Spring Boot hỗ trợ nạp cấu hình từ environment, command line và các nguồn bên ngoài theo cơ chế cấu hình của framework. Với Spring Boot 3 và Java 17, có thể dùng ConfigurationProperties:

~~~java
import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentsProperties(
    @NotNull URI endpoint,
    @NotNull Duration timeout
) {}
~~~

Kích hoạt quét cấu hình trong entry point:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Nền tảng triển khai cấp:

~~~text
PAYMENTS_ENDPOINT=https://payment.staging.internal
PAYMENTS_TIMEOUT=2s
~~~

Trong cơ chế relaxed binding phổ biến của Spring Boot, environment variable PAYMENTS_ENDPOINT tương ứng property payments.endpoint, còn PAYMENTS_TIMEOUT tương ứng payments.timeout. Duration binding của Spring Boot có thể nhận các đơn vị thời gian như 2s. Đảm bảo dependency validation hiện diện và có thể thêm ràng buộc nghiệp vụ sâu hơn bằng validator riêng (ví dụ bắt buộc HTTPS, host hợp lệ, timeout nhỏ hơn tổng request budget).

**Thực hành nên làm:**

- Đưa key/metadata/default an toàn vào source nếu cần; đưa giá trị theo môi trường vào deployment.
- Bật kiểm tra bắt buộc cho cấu hình quan trọng để service không báo READY khi thiếu endpoint hoặc credential.
- Cấu hình precedence phải rõ ràng; tránh vừa có environment variable vừa có flag CLI hoặc file mount cùng ghi đè một key mà đội vận hành không biết.
- Với file cấu hình ngoài JAR, chỉ rõ đường dẫn nạp và quyền đọc; tránh mount đè lên toàn bộ thư mục ứng dụng.
- Không expose toàn bộ environment, configuration properties hoặc actuator endpoints cho client không được cấp quyền. Nếu dùng actuator, giới hạn quyền và che nội dung nhạy cảm.

Cần phân biệt **lỗi cấu hình** với **dependency tạm thời không sẵn sàng**. Key sai schema, URL không hợp lệ, password bị thiếu thường nên fail fast; một DB khởi động chậm có thể cần cơ chế retry có giới hạn và readiness false thay vì crash loop vô tận. Chính sách cụ thể phụ thuộc yêu cầu vận hành và SLO.

## 9. Artifact bất biến: build một lần, triển khai nhiều nơi

Một pipeline lý tưởng:

~~~text
Git commit
   |
   v
compile + unit test + security scan
   |
   v
JAR -> OCI image
   |
   v
registry: image digest sha256:...
   |
   +---- deploy DEV + config DEV + secret DEV
   |
   +---- promote same digest -> STAGING + config STAGING + secret STAGING
   |
   +---- promote same digest -> PROD + config PROD + secret PROD
~~~

Dockerfile minh họa:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/order-service.jar /app/order-service.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/order-service.jar"]
~~~

Dockerfile chỉ đóng gói chương trình, không có ENV DB_PASSWORD, RUN lấy secret từ internet, file production.env hoặc COPY chứng chỉ riêng của production. Một biến ENV không nhạy cảm dùng chung cho mọi môi trường có thể có trong image; điểm cốt lõi là **không bake giá trị khác nhau giữa các deployment**.

Ví dụ khởi chạy thủ công với biến không nhạy cảm:

~~~bash
docker run --rm \
  -e PAYMENTS_ENDPOINT=https://payment.dev.internal \
  -e PAYMENTS_TIMEOUT=2s \
  registry.example.com/order-service:1.8.0
~~~

Lệnh trên chỉ mang tính minh họa; trong production cần cấp secret qua cơ chế được quản lý bởi nền tảng thay vì gõ credential vào dòng lệnh hoặc lịch sử shell. Tag có thể bị gán lại, nên production rollout/rollback cần ghi lại **digest bất biến** tương ứng với tag được kiểm thử.

**Không build lại image chỉ để đổi endpoint hoặc timeout.** Thay đổi bản cấu hình triển khai rồi rollout ứng dụng bằng cùng digest; nếu cơ chế của nền tảng hỗ trợ dynamic config, phải xác định rõ khi nào tiến trình áp dụng thay đổi và cơ chế rollback.

## 10. Kubernetes: ConfigMap cho cấu hình, Secret cho credential

Kubernetes là ví dụ điển hình về việc tách artifact và deployment config. Service image không cần biết namespace, endpoint hoặc credential của môi trường.

ConfigMap cho giá trị không nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service-config
  namespace: orders
data:
  PAYMENTS_ENDPOINT: "https://payment.prod.internal"
  PAYMENTS_TIMEOUT: "2s"
  ORDER_WORKERS: "8"
  LOG_LEVEL: "INFO"
~~~

Deployment tham chiếu đúng key:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      serviceAccountName: order-service
      containers:
        - name: api
          image: registry.example.com/order-service:1.8.0
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: order-service-config
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: order-service-credentials
                  key: db-password
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
~~~

Ví dụ giả định Secret order-service-credentials đã được một controller hoặc quy trình quản lý secret cấp trước. Không chứa giá trị thực của secret trong manifest này. Đường dẫn probe minh họa cho ứng dụng có cấu hình readiness endpoint tương ứng; nếu app không bật endpoint hoặc port đó thì phải sửa deployment.

**Tác động cập nhật cần hiểu đúng:**

- Giá trị từ ConfigMap/Secret qua **env/envFrom** được chụp vào environment lúc container khởi động. Sửa ConfigMap/Secret **không tự cập nhật biến môi trường trong tiến trình đang chạy**; thường phải rollout hoặc restart workload.
- ConfigMap/Secret được **mount dạng volume** có thể được Kubernetes cập nhật theo thời gian, nhưng ứng dụng còn phải reread/reload file. Mount kiểu subPath có đặc điểm cập nhật khác và không nên giả định nhận được thay đổi tự động.
- Nếu Deployment chỉ đổi nội dung ConfigMap mà không đổi pod template, Kubernetes không tự bảo đảm tạo Pod mới. Có thể dùng versioned ConfigMap name, checksum annotation trên Pod template hoặc một controller rollout có kiểm soát.
- Secret của Kubernetes **không đồng nghĩa mã hóa đầu cuối**. Giá trị base64 trong YAML chỉ là encoding, không phải mã hóa. Thiết lập encryption at rest cho cluster data store, RBAC, phân quyền namespace, audit và hạn chế quyền đọc Secret.
- Không gắn IAM/cloud quyền đọc toàn bộ secret lên mọi service account. Một workload chỉ được phép truy cập đúng secret của nó.

Ví dụ: một image Order Service digest X được chạy ở staging và production, nhưng các ConfigMap, Secret, service account và replica count khác nhau. Như vậy việc kiểm thử image X trước khi promote có ý nghĩa mạnh hơn việc build hai image độc lập.

## 11. Quản lý bí mật: không để secret đi theo source và artifact

Những nơi **không nên chứa secret thật**:

- File committed lên Git, kể cả branch private hoặc lịch sử commit đã xóa.
- application-prod.yml đóng trong JAR, Dockerfile ARG/ENV cho secret, Docker build context và layer cache.
- CI/CD artifact, test report, build log, exception, stack trace hoặc debug endpoint.
- URL với query string chứa token, lệnh shell có credential có thể bị ghi lịch sử.
- Dashboard, telemetry tag, email hoặc ticket chứa ảnh chụp giá trị secret.
- Ví dụ tài liệu mà người đọc có thể vô tình copy trực tiếp vào production.

Thay vào đó:

1. Chọn secret manager có **encryption, audit, IAM/workload identity và policy** đáp ứng hệ thống.
2. Tạo riêng identity và chính sách truy cập cho Order Service ở từng môi trường.
3. Cấp secret qua CSI volume, injection của nền tảng hoặc truy xuất trực tiếp bằng identity; chọn cơ chế tương thích với SDK, availability và rotation.
4. Không log full config object hoặc process environment; sử dụng cấu trúc redaction theo key/kiểu dữ liệu.
5. Có quy trình **rotation**, **revocation**, **emergency replacement** và phát hiện secret cũ còn được sử dụng.
6. Với secret lưu trong cache ứng dụng, định nghĩa TTL, khi nào refresh, hành vi nếu refresh thất bại và mức độ chấp nhận stale credential.
7. Nếu ứng dụng cần nhiều phiên bản credential cùng tồn tại trong giai đoạn xoay vòng, dịch vụ đích nên hỗ trợ cửa sổ chấp nhận cả old/new trước khi thu hồi secret cũ.

Sơ đồ xoay vòng:

~~~text
Secret version V1 -> application using V1
        |
create V2 in secret manager
        |
activate V2 / allow overlap
        |
reload or rollout app to V2
        |
verify requests using V2
        |
revoke V1 and monitor failures
~~~

**Không thể khắc phục rò rỉ chỉ bằng xóa secret khỏi HEAD của Git.** Nếu giá trị từng bị commit hoặc xuất hiện trong registry/log, phải thu hồi/đổi secret thật, kiểm tra phạm vi tác động và xử lý lịch sử theo quy trình bảo mật. Tài liệu và script chỉ nên sử dụng tên key hoặc placeholder giả.

## 12. Cấu hình cố định lúc startup và cấu hình thay đổi khi đang chạy

Không phải mọi cấu hình đều cần hot reload. Chia thành các nhóm:

| Nhóm | Ví dụ | Phương án áp dụng |
| --- | --- | --- |
| Bootstrap | Địa chỉ config service, trust anchor, identity | Có sẵn trước/đúng lúc khởi động |
| Startup immutable | JDBC URL, pool strategy, port, thread architecture | Parse/validate lúc startup; rollout để thay đổi |
| Runtime adjustable | Log sampling, tỷ lệ giới hạn, rule không phá vỡ invariant | Watch + snapshot có version, cập nhật nguyên tử |
| Dynamic feature flag | New checkout theo cohort, kill switch | SDK có cache và fallback an toàn |
| Secret có thể rotation | API credential, chứng chỉ | Refresh an toàn hoặc rolling restart theo chính sách |

**Rủi ro của hot reload:**

- Một request có thể đọc một nửa cấu hình cũ, một nửa cấu hình mới nếu thay đổi từng field rời rạc.
- Việc thay đổi pool size, endpoint hoặc credential khi kết nối đang hoạt động có thể làm mất hoặc nhân đôi giao dịch nếu lifecycle không được thiết kế.
- Config service gặp sự cố có thể khiến service không biết dùng dữ liệu cache nào.
- Một giá trị không hợp lệ có thể lan tới hàng trăm instance ngay lập tức.

Nên tạo **immutable config snapshot** có version, validate toàn bộ snapshot trước khi swap, rồi cập nhật tham chiếu nguyên tử; ghi audit revision và chỉ log danh sách key được cập nhật, không log value nhạy cảm. Với thay đổi cấu trúc hoặc pool, ưu tiên rolling deployment có readiness và rollback.

Định nghĩa hành vi khi config service mất kết nối: dùng **last known good** trong thời hạn nào, ứng dụng có tiếp tục nhận traffic không, khi nào cảnh báo. Đối với kiểm soát truy cập và secret bị thu hồi, việc dùng stale data thường nguy hiểm hơn các flag thuần giao diện; không sử dụng một policy fail-open mặc định cho mọi loại cấu hình.

## 13. Config precedence và xử lý xung đột

Ứng dụng có thể cùng lúc nhận cấu hình từ default trong code, file đóng gói, file ngoài, environment, command line và config service. Nếu một key tồn tại ở nhiều nguồn, phải hiểu chính xác **thứ tự ưu tiên do framework và triển khai quy định**, không tự đoán.

Một nguyên tắc tổ chức hữu ích:

1. **Contract code:** định nghĩa khóa, kiểu, valid range và default an toàn.
2. **Environment/deployment config:** định nghĩa value khác nhau theo deployment.
3. **Secret source:** định nghĩa credential theo workload identity và môi trường.
4. **Emergency override:** nếu được phép, phải có hạn sử dụng, audit và quy trình loại bỏ.

Ví dụ một property timeout có default 2s, ConfigMap đưa 5s, deployment override 10s. Nếu không có chính sách precedence rõ, service có thể chạy 10s trong khi runbook vẫn ghi 5s. Sau khi nạp, chỉ nên xuất ra **effective non-sensitive config fingerprint** hoặc danh sách key/source đã được chọn; secret phải được redacted.

Tránh tên biến trùng hoặc generic quá rộng trong môi trường nhiều service. Khi một manifest inject đồng thời envFrom từ nhiều ConfigMap/Secret, key trùng nhau có thể tạo kết quả khó dự đoán với người vận hành. Tốt nhất là có ownership duy nhất cho key hoặc thực hiện policy check trong CI/CD.

## 14. Quản lý cấu hình theo môi trường mà không nhân bản artifact

Ví dụ những thuộc tính được phân chia:

| Thuộc tính | DEV | STAGING | PROD |
| --- | --- | --- | --- |
| Image digest | Digest X đang phát triển | Digest X đã được chọn kiểm thử | Cùng digest X được promote |
| Payment endpoint | Sandbox/dev service | Staging/sandbox provider | Production provider |
| DB | DB dev riêng | DB staging riêng | DB production riêng |
| Secrets | DEV-scoped identity | STG-scoped identity | PROD-scoped identity |
| Số replica | 1 hoặc ít | Gần cấu hình kiểm thử | Theo capacity/SLO |
| Log level | Có thể DEBUG khi cho phép | INFO | INFO, điều chỉnh có kiểm soát |
| Feature flags | On cho thử nghiệm | Canaries/test | Rollout theo policy |

Đây là ví dụ phân tách; độ tương đồng của staging với production cần được thiết kế theo loại bài kiểm thử, không mặc định staging phải dùng credential thật của production. **Tuyệt đối không chia sẻ secret production với dev/test**. Các dịch vụ bên ngoài có thể chỉ cung cấp sandbox, nên pipeline cần ghi rõ sự khác biệt để không đánh giá nhầm phạm vi kiểm thử.

Với nhiều region hoặc tenant, tránh tạo hàng chục image cho cùng code. Có thể tham số hóa deployment values theo region, nhưng lưu ý **residency, quyền truy cập, circuit breaker, quota và endpoint** của từng nơi. Khi tenant-specific config là dữ liệu nghiệp vụ biến đổi thường xuyên, nên sử dụng kho cấu hình/DB có ownership và audit thay vì 1.000 environment variable trong mỗi Pod.

## 15. CI/CD: tách compile, cấu hình và cấp phát bí mật

Một pipeline tham khảo:

~~~text
CI:
  checkout
  -> compile
  -> unit + integration tests
  -> build JAR / OCI image
  -> scan + sign/attest if available
  -> publish image by digest

CD:
  choose tested image digest
  -> load environment-specific deployment manifest
  -> policy + schema validation
  -> resolve secret references (without printing values)
  -> deploy canary/rolling
  -> readiness + smoke tests + SLO gates
  -> record digest/config revision and finalize
~~~

**Thay đổi code** tạo artifact mới. **Thay đổi runtime config** không bắt buộc tạo artifact mới nhưng vẫn phải đi qua review, validation, triển khai và rollback tương xứng với rủi ro. **Thay đổi secret** có vòng đời riêng, bao gồm cấp quyền/rotation/revocation, và có thể buộc restart hoặc refresh tuỳ cách app sử dụng.

Phân chia quyền: developer có thể đề xuất timeout; người có quyền deploy quyết định release; workload được đọc secret ở runtime; pipeline build không cần nắm password production. Hạn chế các pipeline inject toàn bộ bí mật vào biến môi trường cho bước build; điều đó có thể làm lộ qua build tooling, cache hoặc log.

**GitOps:** lưu các manifest/kustomize/Helm values không nhạy cảm trong repo cấu hình riêng theo môi trường và review bằng pull request. Secret trong GitOps nên dùng cơ chế secret reference, external secret controller hoặc mã hóa phù hợp với chính sách và quyền key. Không coi một chuỗi base64 trong YAML Git là bảo vệ bí mật.

## 16. Phương án version và rollback an toàn

Để tái tạo một deployment, cần ghi các thành phần:

- **Image:** repository + digest không thay đổi.
- **Config revision:** commit/version của deployment config hoặc config service, kèm checksum không chứa secret.
- **Secret reference/version:** alias hoặc version ID theo chính sách, không cần lưu raw value.
- **Platform:** runtime/version Java, Kubernetes namespace/cluster, region, các phụ thuộc cần thiết.
- **Database schema:** phiên bản migration đã được áp dụng, tương thích với version app.
- **Feature flag state:** snapshot hoặc lịch sử thay đổi tại thời điểm sự cố nếu flag ảnh hưởng luồng nghiệp vụ.

Khi rollback, quay lại image cũ chưa chắc đủ nếu schema mới hoặc config key đã đổi. Ví dụ version app 1.8 đọc PAYMENTS_TIMEOUT, app 1.7 đọc PAYMENT_TIMEOUT_MS. Nếu đổi key đồng thời với promote, rollback app sẽ không khởi động. Cách an toàn là duy trì **giai đoạn tương thích**: app mới chấp nhận khóa cũ/khóa mới trong cửa sổ chuyển đổi, migration config trước/sau theo thứ tự, rồi chỉ xóa key cũ khi không còn phiên bản cần dùng.

Với secret rotation, rollback không nhất thiết cho phép dùng lại secret bị thu hồi. **Rollback cấu hình không được tự ý hồi sinh credential cũ**; cần quy trình vận hành tương thích với secret mới và app cũ.

Nếu dùng immutable ConfigMap versioned name, việc rollback có thể tham chiếu một version cũ còn lưu; đảm bảo retention policy đủ cho cửa sổ rollback và config cũ không chứa dữ liệu nhạy cảm.

## 17. Khởi động, readiness và failure policy

Một service nên có state rõ ràng:

~~~text
START
  |
  v
Load sources -> Parse -> Validate -> Build dependencies
  |               |            |
  | error         | error      | dependency temporarily unavailable
  v               v            v
FAIL STARTUP   FAIL STARTUP   NOT READY / bounded retry
                                   |
                              connected?
                               /      \
                              no      yes
                              |        |
                         NOT READY    READY
~~~

**Missing required config:** trả thông báo tên key thiếu, không hiện value. **Invalid schema:** log kiểu, giới hạn, nguồn đã che nhạy cảm; fail startup trước khi công bố readiness. **Dependency chậm:** có thể retry giới hạn theo startup budget hoặc giữ readiness false; không dùng loop vô hạn che sự cố. **Config service unavailable:** lựa chọn rõ last-known-good/fail-closed, xác định khoảng thời gian có thể sống với cache.

Khi chạy trên Kubernetes, readiness ngăn Pod chưa sẵn sàng nhận traffic từ Service, nhưng không tự khắc phục cấu hình lỗi. Liveness phải tránh restart liên tục vì dependency tạm thời chậm; startup probe có thể giúp ứng dụng cần bootstrap lâu. Vận hành cần quan sát số lần restart, readiness trạng thái, nguyên nhân validation và revision của config.

**Cấm log secret khi fail startup.** Exception thường có thể vô tình chứa URL với password, JDBC credentials hoặc token. Viết message theo tên key/error category; redaction cần áp dụng cả exception chaining và telemetry exporter.

## 18. Kiểm thử cấu hình: test logic và test deployment

### 18.1. Unit test cho schema và default

Với Java thuần ở phần 7, test logic có thể tạo Map giả:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class PaymentConfigTest {
    @Test
    void acceptsValidConfiguration() {
        PaymentConfig cfg = PaymentConfig.fromEnv(Map.of(
            "PAYMENTS_ENDPOINT", "https://payments.example.test",
            "PAYMENTS_TIMEOUT", "PT2S"
        ));
        assertEquals("payments.example.test", cfg.endpoint().getHost());
    }

    @Test
    void rejectsMissingEndpoint() {
        assertThrows(IllegalStateException.class,
            () -> PaymentConfig.fromEnv(Map.of()));
    }

    @Test
    void rejectsNonHttpsEndpoint() {
        assertThrows(IllegalStateException.class,
            () -> PaymentConfig.fromEnv(Map.of(
                "PAYMENTS_ENDPOINT", "http://payments.example.test"
            )));
    }
}
~~~

Nên test đầy đủ: missing, blank, invalid URL, sai đơn vị timeout, số âm/0, cấu hình vượt budget, key bị đổi tên và giá trị không tương thích. **Unit test không cần secret thật**; dùng local fake/stub và dữ liệu thử nghiệm không nhạy cảm.

### 18.2. Integration test và môi trường kiểm thử

- Khởi động cùng một artifact với config test khác nhau; xác minh endpoint và behavior thay đổi mà không build lại.
- Dùng Testcontainers hoặc môi trường tích hợp để kiểm tra kết nối DB/broker; inject URL và test credentials tạm thời.
- Thử thiếu secret, sai quyền truy cập, secret chưa sẵn sàng, secret rotation và restart.
- Kiểm tra env variable mapping của Spring Boot, especially complex property names và nguồn ghi đè.
- Thử thay ConfigMap trong Kubernetes: với env var thì xác minh cần rollout; với volume thì xác minh cơ chế reload mà app thực sự hỗ trợ.
- Kiểm tra rollback artifact với config version mới/cũ, nhất là khi rename hoặc xóa key.
- Thử nhiều replica đồng thời, bảo đảm config và secret version không bị lệch lâu hơn dự kiến.

### 18.3. Policy test trong pipeline

Bổ sung kiểm tra trước deploy:

1. Những key bắt buộc có giá trị hoặc secret reference hợp lệ.
2. Kiểu, min/max, URL scheme, TLS policy và timeout được validate.
3. Secret không xuất hiện plaintext trong manifests/artifact/scanner logs.
4. Service account có quyền tối thiểu; service không mount secret không liên quan.
5. Image được chọn theo digest; deployment config có revision.
6. Có đủ version tương thích để rolling update và rollback.
7. Cấu hình nhạy cảm không bị xuất qua actuator, metrics hoặc debug.
8. Smoke test có thể kiểm chứng cấu hình có hiệu lực mà không đọc secret.

## 19. Các tình huống thường gặp và quyết định thực tế

### Tình huống A — đổi URL payment ở staging

**Đầu vào:** image Order Service đã kiểm thử, nhưng sandbox Payment Service đổi endpoint.

**Cách làm:** sửa PAYMENTS_ENDPOINT ở staging ConfigMap/deployment, chạy policy validation, rollout Pod nếu app nạp bằng env var, kiểm tra readiness và integration request. **Không rebuild image**. Nếu endpoint mới lỗi, rollback config revision; ghi lại sự kiện thay đổi.

### Tình huống B — DB password production sắp hết hạn

**Cách làm:** cấp credential mới bằng secret manager, thiết lập cửa sổ cho cả old/new nếu DB hỗ trợ, cập nhật secret reference/rotation, rollout/reload pool và xác minh kết nối mới, sau đó thu hồi old credential. Tránh chạy một thời gian dài với Pod cũ chỉ biết password đã bị thu hồi. Có quy trình dừng rollout nếu connection error tăng.

### Tình huống C — tăng pool size khi traffic tăng

**Cách làm:** sửa ORDER_WORKERS và DB pool size có kiểm soát theo quota DB **toàn cụm**, không dựa duy nhất vào CPU của một Pod. Rollout, quan sát saturation và rollback nếu DB bị nghẽn. Tăng mỗi replica từ pool 20 lên 40 trên 20 replica là tăng nhu cầu tối đa từ 400 lên 800 connection; cần kiểm tra giới hạn DB trước.

### Tình huống D — cần bật nhanh tính năng mới cho 5% người dùng

**Cách làm:** dùng feature-flag service có targeting và audit nếu hệ thống hỗ trợ; có default an toàn, kill switch và owner. Không rebuild image cho mỗi lần thay đổi tỷ lệ rollout. Khi feature ổn định, dọn cờ và nhánh logic dư thừa theo vòng đời sản phẩm.

### Tình huống E — cấu hình cần phân biệt nhiều tenant

Nếu mỗi tenant có hàng trăm key thay đổi thường xuyên, không nên đưa toàn bộ tenant config vào environment của mọi instance. Dùng config/data service có tenant identity, schema validation, cache theo TTL, audit, giới hạn quyền truy cập và version. Tách config theo môi trường (deployment scope) khỏi thuộc tính thay đổi theo khách hàng (business scope).

### Tình huống F — chứng chỉ TLS cần mount file

Một số thư viện đọc certificate/private key từ đường dẫn file. Sử dụng file mount với file permission tối thiểu, ví dụ Secret/CSI volume; không đưa PEM thật vào image. Khi chứng chỉ được xoay, xác định rõ thư viện có reread file và thay mới connection không, hay phải rolling restart. Kiểm tra hiệu lực cả certificate chain, SAN/hostname và truststore.

## 20. Quan sát cấu hình trong vận hành

Những tín hiệu nên theo dõi mà không tiết lộ secret:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| app_image_digest | Xác nhận phiên bản binary chạy thực tế |
| config_revision | Truy vết lần thay đổi cấu hình |
| config_validation_failures_total | Phát hiện rollout với giá trị thiếu hoặc sai |
| config_reload_success_total / failure_total | Theo dõi dynamic reload |
| config_last_successful_reload_timestamp | Phát hiện instance dùng config cũ |
| secret_refresh_errors_total | Phát hiện lỗi rotation/không đọc được secret |
| dependency_connection_errors_total | Phát hiện sai endpoint, TLS hoặc credential |
| deployment_ready_replicas | Xác minh rollout sẵn sàng phục vụ |
| 5xx / latency / saturation | Kiểm tra hậu quả nghiệp vụ của thay đổi cấu hình |

Không đặt token, password hoặc toàn bộ cấu hình vào metric label vì có thể làm lộ dữ liệu và gây cardinality lớn. Nếu cần phân biệt version, dùng revision/digest đã được duyệt cho phép công khai nội bộ. Dashboard release nên đặt **image digest + config revision + rollout time + readiness + error rate + p95/p99 latency** cùng dòng thời gian.

Một thông điệp log startup có thể hiển thị:

~~~text
INFO order-service started
     image_digest=sha256:<redacted-example>
     config_revision=deploy-2026-11-12-03
     required_config_valid=true
     secret_source=managed
     payments_endpoint_scheme=https
~~~

Không log giá trị DB_PASSWORD, access token, private key hoặc raw Authorization header. Nếu URL có userinfo/query nhạy cảm, không log toàn bộ URL.

## 21. Các lỗi thiết kế phổ biến

| Sai lầm | Tác động | Cách làm phù hợp |
| --- | --- | --- |
| Hard-code URL production trong Java | Phải sửa code/build lại khi đổi môi trường | Inject endpoint qua runtime config |
| Commit application-prod.yml có password | Bí mật tồn tại trong Git và artifact | Secret manager, rotation và secret scan |
| Dockerfile có ENV token | Token ở image metadata/layer/distribution | Inject runtime bằng workload identity/secret |
| Build image staging và image production khác nhau | Không chắc đã kiểm thử đúng binary | Promote cùng digest |
| Dùng một DB password cho DEV/STG/PROD | Một nơi lộ làm ảnh hưởng toàn bộ | Scope secret theo môi trường/workload |
| ConfigMap chứa password được base64 | Dễ lộ và thiếu quyền bảo vệ | Secret/secret manager + RBAC/encryption |
| Sửa ConfigMap nhưng mong env var tự đổi | Replica chạy giá trị cũ | Rollout hoặc cơ chế reload phù hợp |
| Không validate config khi start | Lỗi phát hiện sau khi nhận traffic | Type-safe binding, fail fast/readiness |
| Nhiều nguồn cấu hình override không rõ | Không biết effective value | Precedence contract và audit |
| Log toàn bộ System.getenv() | Rò rỉ token/password | Structured log có redaction |
| Thay key mà không hỗ trợ app cũ | Rollback hoặc rolling update hỏng | Expand/contract key migration |
| Autoscale mà không giới hạn kết nối DB | Quá tải dependency chung | Capacity budget toàn cụm |
| Hot reload sửa field từng cái | Request thấy cấu hình hỗn hợp | Snapshot bất biến, atomic swap |
| Chỉ lưu image version khi điều tra sự cố | Không tái tạo được deployment | Ghi thêm config revision và secret reference |
| Secrets bị leak rồi chỉ xóa file Git | Credential vẫn có thể dùng được | Thu hồi/rotate, điều tra phạm vi ảnh hưởng |

## 22. Lộ trình chuyển từ cấu hình hard-code sang cấu hình ngoài artifact

**Bước 1 — Kiểm kê:** liệt kê mọi giá trị trong Java, YAML, Dockerfile, CI variables và script. Đánh dấu phần khác giữa môi trường và secret. Phân loại giá trị nào thuộc business logic để không “config hóa” quá mức.

**Bước 2 — Xác lập contract:** đặt key duy nhất theo ngữ nghĩa, kiểu dữ liệu, validation, default, mức nhạy cảm, ownership và SLA thay đổi. Thống nhất naming giữa application và orchestrator.

**Bước 3 — Tạo adapter cấu hình:** chỉ đọc nguồn cấu hình tại composition root, bind sang object type-safe; inject vào service qua constructor. Loại bỏ if DEV/STG/PROD trong business logic. Viết unit tests cho missing/invalid.

**Bước 4 — Chuyển bí mật:** đưa credential sang secret manager, thu hồi giá trị từng commit hoặc đóng gói. Giới hạn IAM/RBAC cho workload, kiểm tra log và artifact không chứa secret.

**Bước 5 — Đổi CI/CD:** build artifact một lần, phát hành theo digest; staging/prod nhận cùng digest nhưng deployment config khác nhau. Thêm policy check, smoke test, rollout và rollback bằng version.

**Bước 6 — Chuyển từng service:** triển khai trước ở dev/staging, chạy so sánh behavior, quan sát readiness và lỗi kết nối; giữ cửa sổ tương thích các key trong rollout. Không xoá key cũ khi replica phiên bản cũ còn tồn tại.

**Bước 7 — Quan sát và vận hành:** lưu config revision, dashboard, quy trình đổi config/secret, audit và runbook. Thử tình huống secret manager không truy cập được, config sai type, rollback và rotation.

**Bước 8 — Dọn dẹp:** bỏ logic hard-code, xóa các bản sao environment-specific trong package, loại bỏ secret bị lộ; cập nhật tài liệu configuration contract và owner. Kiểm tra thành công bằng việc triển khai **cùng một image digest** tới hai môi trường với hai bộ config khác nhau.

## 23. Checklist trước khi đưa service vào production

- [ ] Không có endpoint theo môi trường hoặc credential thật bị hard-code trong source.
- [ ] Một artifact đã kiểm thử có thể được promote đến staging/prod bằng cùng digest.
- [ ] Có danh sách key, type, required/default, phạm vi, sensitivity và owner.
- [ ] Config không nhạy cảm được cấp tại deployment; secret có nguồn quản lý riêng.
- [ ] CI build không cần password production, không in secret trong log/artifact.
- [ ] App nạp config ở điểm khởi động rõ ràng, bind type-safe và validate fail fast.
- [ ] Config precedence được định nghĩa và không có key override khó truy vết.
- [ ] Thay env var trên Kubernetes có cơ chế rollout/restart; mounted file có quy tắc reload.
- [ ] RBAC/IAM, encryption at rest và quyền truy cập secret tuân thủ least privilege.
- [ ] Có rotation/revocation credential và quy trình xử lý secret bị lộ.
- [ ] Có tương thích config key giữa phiên bản app mới/cũ trong rolling update và rollback.
- [ ] Deployment ghi image digest, config revision, secret version/reference an toàn.
- [ ] Cấu hình sai làm readiness fail hoặc startup fail trước khi nhận traffic.
- [ ] Dynamic config chỉ áp dụng nếu có version, validation, atomic update và recovery policy.
- [ ] Kiểm thử config schema, integration, quyền secret, rollout và rollback.
- [ ] Metrics/log chỉ chứa metadata cần thiết; secret và dữ liệu nhạy cảm được che.
- [ ] Có runbook để sửa, khôi phục và kiểm chứng cấu hình khi sự cố xảy ra.

## 24. Câu hỏi thường gặp

**Có bắt buộc dùng environment variables cho mọi cấu hình?**

Không. Environment variables thuận tiện cho các giá trị đơn giản thay đổi theo deployment. File mount phù hợp chứng chỉ và cấu hình có cấu trúc; secret manager phù hợp credential; feature flag phù hợp thay đổi hành vi có chủ đích. Quan trọng là **cấu hình được tách khỏi binary và có lifecycle rõ ràng**.

**Có nên cấm tất cả file application.yml trong Git?**

Không. File trong source có thể chứa tên key, default an toàn hoặc cấu hình thực sự giống nhau ở mọi môi trường. Tránh để giá trị môi trường production và secret thật trong source/artifact. Một mẫu cấu hình không có secret giúp lập trình viên biết contract.

**Giữa ConfigMap và Secret Kubernetes có khác biệt tuyệt đối về bảo mật?**

Không. ConfigMap dành cho dữ liệu không nhạy cảm; Secret cung cấp loại tài nguyên chuyên biệt để quản lý dữ liệu nhạy cảm nhưng vẫn cần RBAC, encryption at rest, kiểm soát quyền trên kubelet/Pod, backup và audit. Base64 không phải mã hóa.

**Nếu chỉ sửa timeout, có cần release ứng dụng không?**

Không nhất thiết phải build artifact mới. Nếu timeout nạp từ environment lúc startup, thay giá trị rồi rollout/restart là cách thường gặp; nếu từ config service hỗ trợ reload, cần theo chính sách reload an toàn. Bất kỳ thay đổi nào ảnh hưởng SLO vẫn nên qua review, validation và theo dõi kết quả.

**Nếu secret hết hạn khi instance đang chạy thì sao?**

Cần policy rotation. Tùy client/SDK, ứng dụng sẽ refresh credential và tạo lại connection, hoặc được rolling restart. Nếu credential cũ bị thu hồi trước khi instance nhận mới, có thể phát sinh lỗi truy cập. Thiết kế cửa sổ chuyển tiếp và quan sát kết nối là điều bắt buộc với workload quan trọng.

**Một image áp dụng cho tất cả môi trường có nghĩa hành vi luôn giống nhau?**

Không. Binary giống nhau nhưng dependency, cấu hình, tải, quyền mạng, feature flag và dữ liệu khác nhau sẽ tạo ra hành vi khác nhau. Đó là lý do cần contract, integration tests, deployment smoke tests và truy vết version config thay vì chỉ kiểm thử artifact.

**Khi config service gặp lỗi thì service phải tắt ngay?**

Tùy loại cấu hình và yêu cầu an toàn. Với flag giao diện có thể dùng last known good; với secret bị thu hồi hoặc policy truy cập, dùng dữ liệu stale có thể không chấp nhận được. Cần viết rõ fallback/TTL, cảnh báo và fail-closed theo từng loại config.

---

**Nguyên tắc ghi nhớ:** *Build ứng dụng một lần, triển khai artifact bất biến nhiều lần, cấp cấu hình đúng môi trường tại runtime, bảo vệ secret bằng cơ chế riêng, validate trước khi nhận traffic và version mọi thay đổi cấu hình có ảnh hưởng vận hành.*