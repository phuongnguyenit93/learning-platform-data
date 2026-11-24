# Truyền tham số, biến môi trường và secret lúc container khởi động

## 1. Cấu hình runtime cho native container

Một Spring Boot Native Image được đóng gói thành executable native. Khi container khởi động, process cần nhận profile, port, URL dịch vụ phụ thuộc, timeout, feature flag và thông tin xác thực để kết nối database hoặc API bên ngoài.

Những giá trị này thường khác nhau giữa local, staging và production. Vì vậy, image nên chứa executable cùng thành phần cần để chạy; môi trường triển khai cung cấp cấu hình và secret tại thời điểm khởi động. Nếu giá trị phụ thuộc môi trường bị đọc trong static initializer rồi đóng băng khi native image được build, executable có thể mang theo giá trị của máy build. Hãy đưa cấu hình vào Spring Boot externalized configuration và đọc nó trong lifecycle của application.

Bài này thuộc chương **Container** của module **SPRING_BOOT_NATIVE_IMAGE**. Nội dung tập trung vào command-line arguments, environment variables, thứ tự ưu tiên property, secret file mount, Docker/Compose/Kubernetes, rotation và khác biệt giữa application arguments với option của JVM hoặc Native Image runtime.

## 2. Command-line arguments của Spring Boot

Spring Boot nhận application arguments theo dạng option:

```bash
./orders-api --server.port=8080 --spring.profiles.active=production
```

Các argument dạng `--name=value` được Spring Boot chuyển thành property:

| Argument | Property |
| --- | --- |
| `--server.port=8080` | `server.port` |
| `--spring.profiles.active=production` | `spring.profiles.active` |
| `--spring.datasource.url=jdbc:postgresql://db:5432/orders` | `spring.datasource.url` |
| `--management.server.port=8081` | `management.server.port` |

Command-line arguments hữu ích khi cần ghi đè một vài giá trị trong lần chạy cụ thể. Không đặt password hoặc token trực tiếp trong command line vì chúng có thể xuất hiện trong process listing, shell history, CI log hoặc metadata của công cụ triển khai.

Với native executable, các argument sau tên executable là argument của chương trình và có thể được Spring Boot xử lý như trên:

```bash
/app/orders-api --server.port=8080 --spring.profiles.active=production
```

Không cần viết `java -jar` trước native executable.

## 3. Environment variables và relaxed binding

Environment variables phù hợp với cấu hình đơn giản do môi trường triển khai quản lý. Spring Boot hỗ trợ relaxed binding, cho phép property dạng chuẩn được biểu diễn bằng tên biến môi trường viết hoa và dùng dấu gạch dưới.

| Spring property | Environment variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `management.server.port` | `MANAGEMENT_SERVER_PORT` |
| `logging.level.com.example.orders` | `LOGGING_LEVEL_COM_EXAMPLE_ORDERS` |

Ví dụ chạy container:

```bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=production \
  -e SERVER_PORT=8080 \
  -e SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders \
  -e SPRING_DATASOURCE_USERNAME=orders_app \
  orders-api:native
```

Dùng biến môi trường cho profile, port, URL endpoint và timeout. Password, private key và token cần cơ chế quản lý secret riêng; environment variable không phải secret vault.

### 3.1. Cấu hình có cấu trúc

Với collection hoặc map, tên biến môi trường có thể khó đọc. Khi cấu hình trở nên phức tạp, cân nhắc dùng file cấu hình được mount hoặc `SPRING_APPLICATION_JSON` cho một phần cấu hình có cấu trúc:

```bash
docker run --rm \
  -e 'SPRING_APPLICATION_JSON={"feature":{"invoice-export":true},"clients":{"billing":{"connect-timeout":"2s"}}}' \
  orders-api:native
```

JSON này vẫn là cấu hình runtime của process và không nên chứa secret. Biến `SPRING_APPLICATION_JSON` có thể bị lộ qua inspection hoặc diagnostic output tùy nền tảng.

## 4. Thứ tự ưu tiên của Spring Boot configuration

Spring Boot tổng hợp property từ nhiều nguồn. Khi cùng một key xuất hiện ở nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn.

Với ứng dụng standalone thông thường, có thể nhớ thứ tự rút gọn từ cao xuống thấp:

1. Command-line arguments.
2. `SPRING_APPLICATION_JSON`.
3. Java system properties.
4. Operating-system environment variables.
5. Config data như `application.yaml` và file profile-specific.
6. Default properties.

Spring Boot còn có các nguồn đặc thù như servlet init parameters, JNDI và test property sources. Thứ tự chi tiết phụ thuộc loại ứng dụng và phiên bản Spring Boot; khi cần kết luận chính xác, kiểm tra tài liệu externalized configuration của phiên bản dự án.

Ví dụ, file `application.yaml` có:

```yaml
server:
  port: 8080
spring:
  profiles:
    active: local
```

Nếu container khởi chạy với `SERVER_PORT=9090` và `SPRING_PROFILES_ACTIVE=production`, environment values sẽ ghi đè hai giá trị trong file. Nếu command line truyền `--server.port=7070`, command-line value có độ ưu tiên cao hơn environment variable.

Không dựa vào thứ tự ưu tiên để quản lý secret bằng nhiều bản sao ở các nguồn khác nhau. Mỗi secret nên có một nguồn runtime được xác định rõ.

## 5. Phân biệt cấu hình build-time và runtime

Native Image có hai thời điểm quan trọng:

- **Build time:** GraalVM phân tích và tạo executable. Một số class có thể được initialize trong lúc build.
- **Runtime:** container khởi chạy executable; process nhận environment variables, arguments, mounted files và kết nối tới dependency.

Các giá trị như database password, service URL, hostname, port, secret path và feature flag thường phải được đọc ở runtime.

Ví dụ không an toàn:

```java
final class DatabaseSettings {

    static final String PASSWORD =
        System.getenv("DB_PASSWORD");
}
```

Nếu class này bị initialize ở build time, giá trị có thể được đọc từ môi trường build và lưu trong image. Cách đó có thể làm sai cấu hình production và vô tình đưa secret vào artifact.

Thay vào đó, để Spring quản lý cấu hình:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class DatabaseConnectionSettings {

    private final String password;

    DatabaseConnectionSettings(Environment environment) {
        this.password = environment.getProperty(
            "spring.datasource.password"
        );
    }

    String password() {
        return password;
    }
}
```

Spring inject property khi application context khởi tạo trong container runtime. Với datasource, ưu tiên để Spring Boot datasource auto-configuration tiêu thụ property chuẩn thay vì tự đọc environment trong static field.

### 5.1. Không đóng secret vào image

Không truyền secret qua Dockerfile `ARG` hoặc `ENV` trong lúc build:

```dockerfile
# Không làm như sau
ARG DB_PASSWORD
ENV DB_PASSWORD=secret-value
```

Build argument hoặc environment được ghi trong quá trình tạo image có thể xuất hiện trong layer, history, cache hoặc image configuration. Không COPY file secret vào image và không commit file secret vào repository.

Image nên được build một lần và promote giữa staging/production. Mỗi môi trường cấp cấu hình runtime và secret riêng khi container khởi động.

## 6. Docker ENTRYPOINT và CMD cho native executable

Với native executable, nên dùng exec form để process ứng dụng trở thành PID 1 trong container. Ví dụ Dockerfile runtime tối giản:

```dockerfile
FROM debian:bookworm-slim

WORKDIR /app

COPY --chown=10001:10001 target/orders-api /app/orders-api

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-api"]
CMD ["--server.port=8080"]
```

Docker kết hợp ENTRYPOINT và CMD: command mặc định trong CMD được truyền làm argument cho executable trong ENTRYPOINT. Khi chạy:

```bash
docker run --rm -p 8080:8080 orders-api:native \
  --spring.profiles.active=production
```

Argument sau image name thay thế CMD mặc định và được truyền vào executable. ENTRYPOINT vẫn là native binary.

Base image runtime cũng phải tương thích với OS, architecture và libc mà native executable được build để sử dụng. Ví dụ, binary liên kết với glibc không tự chạy được trên Alpine/musl chỉ bằng cách đổi base image. Kiểm thử executable trong đúng runtime image sẽ phát hiện sớm lỗi thiếu shared library hoặc ABI không tương thích.

### 6.1. Exec form và shell form

Ưu tiên:

```dockerfile
ENTRYPOINT ["/app/orders-api"]
```

Hạn chế shell form:

```dockerfile
ENTRYPOINT /app/orders-api
```

Shell form chạy qua shell trung gian. Process có thể không nhận tín hiệu trực tiếp như mong muốn nếu shell không forward signal. Exec form giúp Docker gửi SIGTERM tới native process để Spring có cơ hội thực hiện graceful shutdown.

Nếu cần script chuẩn bị file hoặc kiểm tra mount trước khi chạy, dùng wrapper script có quyền thực thi và cuối script gọi `exec /app/orders-api "$@"` để thay thế shell process bằng ứng dụng.

### 6.2. Phân biệt application arguments và runtime options

| Loại | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| Spring application argument | `--server.port=8080` | Spring Boot Environment |
| Environment variable | `SPRING_PROFILES_ACTIVE=production` | OS environment, Spring relaxed binding |
| JVM launcher option | `-XX:...` hoặc `-D...` trong lệnh java | Java launcher khi chạy JVM |
| Native Image runtime option | Option runtime được GraalVM executable hỗ trợ | Native Image runtime |

Native executable không được khởi chạy bằng Java launcher. Vì vậy, `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS` không phải cách chung để truyền mọi JVM option cho native binary. Nếu cần giới hạn memory hoặc bật runtime monitoring, dùng option mà GraalVM Native Image version cụ thể hỗ trợ và kiểm tra tài liệu/help của toolchain. Spring properties vẫn có thể truyền qua environment hoặc application arguments.

## 7. Mount file cấu hình vào container

Khi có nhiều property hoặc cần quản lý file riêng, có thể mount file vào container:

```bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/run/config/ \
  --mount type=bind,src=/opt/orders/config,dst=/run/config,readonly \
  orders-api:native
```

Thư mục mount có thể chứa `application.yaml` hoặc file profile-specific. Bảo đảm file có thể đọc được bởi UID chạy ứng dụng. Mount read-only để process không sửa cấu hình do nền tảng quản lý.

`SPRING_CONFIG_LOCATION` có thể thay thế vị trí config mặc định. `SPRING_CONFIG_ADDITIONAL_LOCATION` bổ sung location bên cạnh các location mặc định. Chọn theo mục đích và kiểm tra log config loading khi khởi động.

## 8. Nạp secret từ file bằng Spring Config Tree

Một lựa chọn phù hợp cho container là mount từng secret thành file và dùng config tree import. Spring Boot đọc tên file làm property key và nội dung file làm property value.

Ví dụ cấu trúc trong container:

```text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
  api.partner.token
```

Khai báo import:

```properties
spring.config.import=optional:configtree:/run/secrets/
```

Hoặc qua environment:

```bash
SPRING_CONFIG_IMPORT=optional:configtree:/run/secrets/
```

Nội dung file `spring.datasource.password` trở thành giá trị property `spring.datasource.password`. File `api.partner.token` trở thành property `api.partner.token`. Ứng dụng tiếp tục dùng Spring Boot datasource auto-configuration và property injection như thông thường.

Dùng `optional:` khi secret mount không bắt buộc trong một số profile. Nếu production bắt buộc có secret, cân nhắc bỏ optional để ứng dụng fail fast khi file không tồn tại. Không để ứng dụng khởi động với password rỗng rồi chỉ phát hiện khi có request đầu tiên.

### 8.1. Quyền truy cập file secret

Process thường chạy bằng non-root user. Bảo đảm UID/GID của process đọc được file nhưng user không liên quan không có quyền đọc. Dùng mount read-only, file permission tối thiểu và secret volume được nền tảng quản lý.

Không in nội dung secret ra log khi kiểm tra mount. Chỉ kiểm tra file có tồn tại, quyền truy cập và property có được resolve; nếu cần xác nhận, log trạng thái boolean, không log giá trị.

## 9. Docker Compose: cấu hình và secret

Docker Compose có thể truyền cấu hình không nhạy cảm bằng environment và mount secret riêng:

```yaml
services:
  orders-api:
    image: registry.example.com/orders-api:native
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: production
      SERVER_PORT: "8080"
      SPRING_CONFIG_IMPORT: optional:configtree:/run/secrets/
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/orders
      SPRING_DATASOURCE_USERNAME: orders_app
    secrets:
      - source: db_password
        target: spring.datasource.password
      - source: partner_token
        target: api.partner.token

secrets:
  db_password:
    file: ./secrets/db_password
  partner_token:
    file: ./secrets/partner_token
```

Compose mount secret trong thư mục mặc định `/run/secrets`; target trở thành tên file config tree. Không đưa file secret vào Git. Thêm thư mục secret vào `.gitignore` và giới hạn quyền đọc ở host.

File-backed secrets trong Docker Compose local thường được triển khai qua bind mount; các tùy chọn UID/GID/mode có thể không được áp dụng giống Swarm secrets. Kiểm tra quyền file thực tế trong container. Với production, ưu tiên secret manager hoặc nền tảng orchestration có quản lý secret và encryption phù hợp.

File `.env` của Compose chủ yếu hỗ trợ thay biến khi render Compose configuration. Nó không phải secret manager. Tránh lưu credential thật trong `.env` được commit hoặc chia sẻ rộng.

## 10. Kubernetes: ConfigMap, Secret và volume mount

Kubernetes thường dùng ConfigMap cho cấu hình không nhạy cảm và Secret cho dữ liệu nhạy cảm. Có thể mount Secret thành file rồi dùng config tree:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-api-config
data:
  SPRING_PROFILES_ACTIVE: production
  SPRING_CONFIG_IMPORT: optional:configtree:/run/secrets/
  SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/orders
---
apiVersion: v1
kind: Secret
metadata:
  name: orders-api
type: Opaque
stringData:
  db-password: REPLACE_FROM_SECRET_MANAGER
  partner-token: REPLACE_FROM_SECRET_MANAGER
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      securityContext:
        fsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/orders-api:native
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: orders-api-config
          volumeMounts:
            - name: app-secrets
              mountPath: /run/secrets
              readOnly: true
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            allowPrivilegeEscalation: false
      volumes:
        - name: app-secrets
          secret:
            secretName: orders-api
            defaultMode: 0440
            items:
              - key: db-password
                path: spring.datasource.password
              - key: partner-token
                path: api.partner.token
```

Ví dụ chỉ minh họa cấu trúc manifest. Không commit giá trị secret thật trong YAML. Trong production, tạo Secret qua External Secrets Operator, CSI Secret Store, sealed/encrypted workflow hoặc pipeline được bảo vệ. Kubernetes Secret được encode base64 trong manifest/API representation; base64 không phải encryption. Cần bật encryption at rest cho datastore, giới hạn RBAC và tránh cho mọi namespace/user đọc Secret.

Với volume permission, xác minh user 10001 thực sự đọc được file trên cluster. Tùy storage/volume type, có thể cần `fsGroup` hoặc CSI driver policy. Không chạy container bằng root chỉ để bỏ qua lỗi permission.

### 10.1. Secret dưới dạng environment variable trong Kubernetes

Kubernetes cũng cho phép lấy Secret key vào environment:

```yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-api
        key: db-password
```

Cách này đơn giản, nhưng secret trở thành environment variable của process. Environment có thể bị lộ qua diagnostic endpoint, process inspection hoặc dump nếu hệ thống thu thập không kiểm soát. Dùng file mount khi ứng dụng hỗ trợ config tree và nền tảng có thể cấp quyền file phù hợp.

## 11. Rotation và cập nhật cấu hình

Secret có thể được xoay vòng khi credential hết hạn, nghi ngờ lộ hoặc theo lịch. Nhưng mount file mới không đồng nghĩa Spring Boot tự cập nhật property đang được inject vào bean.

Khi Secret volume được cập nhật, Kubernetes có thể cập nhật nội dung file theo cơ chế projected volume; file mount bằng subPath có hành vi cập nhật khác và thường không nhận bản cập nhật như volume root. Tuy vậy, Spring Config Data thường đọc file khi application context khởi động. Bean đã nhận password/token có thể tiếp tục giữ giá trị cũ.

Quy trình rotation:

1. Tạo credential mới ở hệ thống đích và cho phép giai đoạn overlap nếu có thể.
2. Cập nhật secret store hoặc Kubernetes Secret.
3. Chờ volume update hoặc cập nhật file mount theo cơ chế nền tảng.
4. Restart/recreate pod hoặc kích hoạt cơ chế reload đã được ứng dụng hỗ trợ.
5. Xác nhận kết nối dùng credential mới.
6. Thu hồi credential cũ sau khi tất cả instance đã chuyển đổi.

Không giả định Docker Compose file secret hoặc bind mount tự reload cấu hình trong process. Với ứng dụng cần rotation không gián đoạn, thiết kế secret provider/credential refresh có chủ đích và kiểm thử lifecycle đó.

## 12. Tín hiệu shutdown và thời gian graceful termination

Khi container dừng, runtime gửi tín hiệu tới PID 1. Với exec-form ENTRYPOINT, native executable nhận SIGTERM trực tiếp và Spring Boot có thể đóng application context, dừng server, hoàn tất hoặc từ chối request mới và đóng connection pool.

Kubernetes có thể gửi SIGTERM rồi chờ hết termination grace period trước khi kill process. Hãy cấu hình:

- `terminationGracePeriodSeconds` đủ cho thời gian drain request.
- Readiness chuyển sang không sẵn sàng trước hoặc trong giai đoạn shutdown theo cơ chế phù hợp.
- Spring graceful shutdown và timeout tương thích với grace period của Pod.
- PreStop hook chỉ khi thực sự cần; hook cũng tiêu thụ thời gian trong termination grace period.

Không dùng shell wrapper không forward signal. Nếu có wrapper, kết thúc bằng exec để native binary trở thành process chính.

## 13. Kiểm tra cấu hình hiệu lực khi container chạy

Có thể kiểm tra cấu hình qua log startup, health endpoint được bảo vệ hoặc diagnostic endpoint nội bộ. Không log password/token để chứng minh property đã được nạp.

Một cách kiểm tra an toàn là log trạng thái cấu hình:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class RuntimeConfigurationCheck implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(RuntimeConfigurationCheck.class);

    private final Environment environment;

    RuntimeConfigurationCheck(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean hasDatasourceUrl =
            StringUtils.hasText(
                environment.getProperty("spring.datasource.url")
            );

        boolean hasDatasourcePassword =
            StringUtils.hasText(
                environment.getProperty("spring.datasource.password")
            );

        log.info(
            "Runtime configuration: datasourceUrlPresent={}, passwordPresent={}",
            hasDatasourceUrl,
            hasDatasourcePassword
        );
    }
}
```

Ví dụ chỉ ghi boolean, không ghi giá trị. Cần cân nhắc liệu ngay cả tên property hoặc trạng thái presence có nhạy cảm trong môi trường cụ thể hay không.

Không expose toàn bộ `env` hoặc `configprops` endpoint chỉ để kiểm tra runtime config. Nếu dùng Actuator, bảo vệ endpoint, giới hạn detail và chỉ truy cập từ network quản trị.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Container vẫn dùng profile local | Không truyền `SPRING_PROFILES_ACTIVE` hoặc command line ghi đè | Kiểm tra effective property và thứ tự ưu tiên |
| Port không đổi dù đặt `SERVER_PORT` | Entry point không truyền env hoặc app có nguồn ưu tiên cao hơn | Kiểm tra command args, env và config data |
| Spring không đọc secret file | Sai mount path, tên file không khớp property hoặc thiếu config import | Kiểm tra `SPRING_CONFIG_IMPORT`, file path và quyền đọc |
| Container khởi động với password rỗng | Secret mount chưa có nhưng import dùng optional | Bỏ optional khi secret bắt buộc và fail fast |
| Native executable mang giá trị máy build | Static initializer đọc environment trong build-time initialization | Chuyển sang Spring runtime configuration và điều chỉnh class initialization |
| Secret xuất hiện trong image history | Dùng Dockerfile ARG/ENV hoặc COPY secret lúc build | Loại secret khỏi build context/image, cấp runtime |
| Process không dừng graceful | Shell form hoặc wrapper không forward SIGTERM | Dùng exec form hoặc exec native binary trong wrapper |
| Non-root process không đọc được secret | UID/GID/mode của mounted file không phù hợp | Điều chỉnh ownership/permissions hoặc fsGroup/CSI policy |
| Secret đã rotate nhưng app vẫn dùng giá trị cũ | Spring đã bind property khi startup | Restart/reload có kiểm soát hoặc triển khai credential refresh |
| Local Compose đọc được secret nhưng cluster lỗi | Cách mount và permission khác nhau | Kiểm tra trực tiếp trong container/Pod theo UID thực tế |

## 15. Kiểm thử runtime arguments và secrets

Kiểm thử cần xác minh cả giá trị được bind và hành vi của process:

1. Khởi chạy binary với command-line argument và xác nhận Spring property tương ứng.
2. Khởi chạy container với environment variable và xác nhận relaxed binding.
3. Cung cấp cùng property ở file config và environment để xác nhận precedence.
4. Mount config tree và kiểm tra các property từ secret file được resolve.
5. Thử thiếu secret bắt buộc và xác nhận ứng dụng fail fast.
6. Chạy bằng non-root UID và xác minh file permission.
7. Kiểm tra secret không xuất hiện trong Docker image layer/history hoặc log startup.
8. Thay secret và xác minh quy trình restart/reload.
9. Gửi SIGTERM và đo thời gian graceful shutdown.
10. Chạy cùng bài test trên native executable được đóng gói trong image cuối cùng, không chỉ trên JVM hoặc build container.

Một bài smoke test chỉ xác nhận HTTP 200 là chưa đủ. Hãy xác nhận ứng dụng thực sự kết nối được database hoặc dependency bằng credential runtime đúng, nhưng tuyệt đối không in credential ra log hoặc test report.

## 16. Bài thực hành: triển khai native container với cấu hình theo môi trường

**Bối cảnh:** Một Spring Boot Native Image service kết nối PostgreSQL và một partner API. Cùng một image được triển khai ở staging và production với URL, profile và secret khác nhau.

**Các bước:**

1. Tạo native executable và Dockerfile dùng exec-form ENTRYPOINT, chạy bằng non-root UID.
2. Đặt profile, port và datasource URL thành environment variables.
3. Không đưa password hoặc partner token vào Dockerfile, image hoặc source control.
4. Tạo secret file cho datasource password và partner token.
5. Cấu hình `SPRING_CONFIG_IMPORT=optional:configtree:/run/secrets/` nếu secret có thể vắng mặt ở local; production phải fail fast khi thiếu.
6. Tạo Docker Compose service dùng environment cho cấu hình và Compose secrets cho file secret.
7. Tạo Kubernetes Secret/ConfigMap và Deployment mount secret read-only.
8. Xác minh UID/GID, file mode và quyền đọc trong container.
9. Kiểm thử property precedence bằng cách đặt cùng một key ở file, environment và command line.
10. Xoay credential ở staging, xác minh restart/reload và thu hồi credential cũ.
11. Gửi SIGTERM để kiểm tra graceful shutdown.
12. Chạy smoke/integration test trên native container image cuối cùng.

**Tiêu chí đạt:**

- Native executable nhận được Spring command-line arguments và environment variables lúc khởi động.
- Cấu hình không nhạy cảm được tách khỏi secret.
- Secret được cấp qua runtime file mount hoặc secret manager, không nằm trong image.
- Spring Config Tree ánh xạ file name thành đúng property.
- Ứng dụng chạy non-root và chỉ đọc được file cần thiết.
- Quy trình rotation có bước reload/restart và xác minh.
- Process nhận SIGTERM và đóng graceful trong thời hạn nền tảng cho phép.
- Cùng một image có thể chạy ở staging/production với cấu hình runtime khác nhau.

## 17. Tổng kết

Container chỉ nên mang native executable và thành phần cần để chạy. Spring Boot command-line arguments, environment variables và config files cho phép thay đổi cấu hình theo môi trường; command line thường có ưu tiên cao hơn environment, còn environment ghi đè config data theo thứ tự externalized configuration. Hãy kiểm tra effective property thay vì đoán từ một file đơn lẻ.

Secret cần được cấp lúc runtime bằng secret manager hoặc file mount. Spring Config Tree giúp ánh xạ tên file thành property, nhưng ứng dụng thường đọc cấu hình khi khởi động nên rotation có thể cần restart hoặc cơ chế refresh riêng. Không đóng secret vào Dockerfile/image, không log giá trị, giới hạn quyền file và chạy process bằng non-root user.

Với GraalVM Native Image, phân biệt application arguments với JVM launcher options và Native Image runtime options. Tránh đọc cấu hình môi trường trong static initializer có thể chạy ở build time. Kiểm thử cấu hình, secret mount, quyền truy cập, rotation và graceful shutdown trên chính container image native sẽ giúp artifact hoạt động nhất quán giữa các môi trường triển khai.

