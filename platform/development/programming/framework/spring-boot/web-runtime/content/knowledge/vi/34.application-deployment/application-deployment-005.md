# Đưa chứng thư, thư mục tạm và cấu hình môi trường ra ngoài gói ứng dụng

## 1. Mục tiêu: tách artifact khỏi runtime

Một ứng dụng Spring Boot được đóng gói dưới dạng executable JAR hoặc container image nên có thể dùng **cùng một bản build** trên dev, staging và production. Chứng thư TLS, private key, cấu hình kết nối, thư mục tạm, upload và secrets không nên bị đóng cứng vào file JAR. Nguyên tắc chính là **immutable artifact, external configuration, separate writable storage**.

Trong module **Spring Boot - web-runtime**, nhóm **Triển khai ứng dụng**, bạn sẽ học cách:

1. Tách **chứng thư, private key, keystore, truststore** khỏi `BOOT-INF/classes`, đọc từ file mounts và bảo vệ bằng permissions.
2. Tách **cấu hình môi trường** qua `application.properties`/YAML ngoài JAR, env vars, command-line, `spring.config.additional-location`, `spring.config.import` và `configtree:`.
3. Phân biệt **JVM temp** (`java.io.tmpdir`), **Spring MVC multipart temp** (`spring.servlet.multipart.location`), **WebFlux multipart temp** (`spring.webflux.multipart.file-storage-directory`), **Tomcat basedir** và **business data directory**.
4. Build và chạy một lab **Java 17 + Spring Boot 3.3.5** lưu upload vào external directory, rồi chuyển HTTP sang HTTPS bằng external PEM bundle mà không rebuild JAR.
5. Map cùng mô hình lên Docker Compose, Kubernetes volumes/ConfigMap/Secret/PVC và systemd.
6. Xử lý bảo mật least privilege, secret rotation, read-only root filesystem, disk quota, Pod replication, TLS trust và lỗi triển khai.

**Nguyên tắc:** JAR/image chứa mã và static resources không nhạy cảm; config, cert/key, temp và mutable data sống ở runtime, có cơ chế quyền/truy cập/lifecycle riêng. Đưa file ra ngoài JAR là bước đầu — còn phải xác định dữ liệu nào **ephemeral** và dữ liệu nào **durable**.

## 2. Vì sao không đặt private key, temp và uploads trong JAR?

Executable Spring Boot JAR có cấu trúc tương tự:

~~~text
myapp.jar
├── BOOT-INF/
│   ├── classes/
│   │   ├── application.properties
│   │   ├── static/
│   │   └── com/example/...
│   └── lib/
└── META-INF/
~~~

Resources trong JAR thường dùng để **đọc**. Đặt `server.key`, `production.p12` hay API token trong `src/main/resources` làm chúng bị sao chép vào artifact và có thể lan tới registry, máy CI, backups, Git history. Thay đổi certificate có thể buộc rebuild và deploy không cần thiết; private key bị lộ khi artifact leak.

Cũng không được trông chờ `ClassPathResource.getFile()` là writable location: trong nested JAR, resource không nhất thiết có một filesystem path độc lập có thể ghi. Với container root filesystem read-only, ghi vào `/app` hoặc lớp image sẽ thất bại.

~~~java
// ANTI-PATTERN — ví dụ sai, không chạy như một class độc lập:
File target = new ClassPathResource("uploads/example.bin").getFile();
Files.write(target.toPath(), bytes);
~~~

**Đúng:** để app nhận `Path` được cấu hình từ runtime, ví dụ `/var/lib/myapp/uploads`, rồi thao tác qua `Files.createDirectories` và `Files.copy`. Không dùng client filename trực tiếp làm storage path.

### 2.1. Phân loại tài nguyên

| Nhóm | Ví dụ | Tuổi thọ và quyền |
| --- | --- | --- |
| Immutable artifact | JAR/classes/static CSS | Versioned, chỉ cần đọc |
| Nonsecret config | Port, timeout, feature flags, downstream URL | Thay theo environment, thường read-only |
| Sensitive secrets | TLS private key, DB password, API token | Secret store/mounted file, quyền tối thiểu |
| Temporary work | Multipart spool, transform scratch, JVM temp | Writable, có quotas và cleanup, có thể mất |
| Durable business state | User uploads, reports, metadata | PVC/object storage/DB, có backup |
| Operational logs | stdout, optional access logs | Ưu tiên centralized logs, retention riêng |

**Không đặt durable uploads trên ephemeral temp volume.** Một container restart hoặc Pod replacement có thể phá hủy local state. Trong cluster nhiều replicas, các file lưu ở private filesystem của Pod A cũng không tự xuất hiện ở Pod B.

## 3. Một layout runtime dễ vận hành

~~~text
/opt/myapp/
    app.jar                      # immutable

/etc/myapp/
    application-prod.properties  # external nonsecret config
    tls/
        server.crt                # certificate
        server.key                # private key, bảo vệ nghiêm ngặt
    secrets/
        db.password               # secret file

/var/tmp/myapp/
    multipart/                   # Servlet multipart spool
    processing/                  # temporary business work
    tomcat/                      # optional Tomcat basedir

/var/lib/myapp/
    uploads/                     # persistent business data

/var/log/myapp/                  # optional file logs
~~~

Trong container, paths là **volume mount destinations**. Trên Linux host, các paths có thể do systemd/admin tạo và phân quyền. Môi trường Windows có thể dùng absolute paths khác, nhưng tư tưởng tách artifact, config, secrets, temp, data vẫn giống nhau.

Một số mục chỉ cần **read-only** (config, certificates, JAR), trong khi temp và uploads cần **writable**. Không mount tất cả thành một thư mục `/data` với quyền `777`: mất khả năng cô lập và làm tăng rủi ro khi app bị xâm nhập.

### 3.1. Relative path không nhất thiết tính từ thư mục JAR

~~~bash
cd /opt/myapp
java -jar app.jar --app.storage.root=./runtime/uploads
~~~

`./runtime/uploads` được resolve theo **process working directory**, không có contract rằng nó luôn theo vị trí file JAR. Trong Docker `WORKDIR`, systemd `WorkingDirectory` và khi chạy bằng IDE, working directory có thể khác nhau. Production nên dùng **absolute paths** và kiểm chứng file location thực.

## 4. Externalized configuration trong Spring Boot 3.3

Spring Boot 3.3 cho phép lấy config từ nhiều property sources như:

- `application.properties`/`application.yaml` packaged trong JAR (safe defaults).
- Files bên ngoài JAR: `file:/etc/myapp/application.properties` hoặc profile-specific.
- Environment variables: `SERVER_PORT`, `APP_STORAGE_ROOT`, `SPRING_CONFIG_ADDITIONAL_LOCATION`.
- JVM system properties `-Dkey=value`.
- Spring Boot command-line arguments `--key=value`.
- `spring.config.import` để đọc file/properties/config trees.
- Secret/config providers khác nếu thêm tích hợp phù hợp.

Config values có thể inject qua `@Value`, Spring `Environment` hoặc được bind thành POJO/record bằng `@ConfigurationProperties`. Khi các nguồn cùng định nghĩa một key, **property source precedence** quyết định giá trị cuối. Đừng đoán chỉ từ một file nếu deploy có env, CLI, ConfigMap, Helm values hay Config Server.

### 4.1. classpath: và file:

~~~properties
# Read-only resource packaged cùng mã:
app.banner=classpath:/banner.txt

# File runtime outside JAR:
app.partner-ca=file:/etc/myapp/tls/partner-ca.crt

# Custom property được bind thành Path:
app.storage.root=/var/lib/myapp/uploads
~~~

`classpath:` tra cứu trong classpath; `file:` là filesystem resource. Với custom property có type `Path`, thường cung cấp đường dẫn thuần `/var/lib/...`, không phải Spring resource URL `file:...`; cần kiểm tra Java type của bean.

### 4.2. Đọc external application.properties

~~~bash
java -jar /opt/myapp/app.jar \
  --spring.config.additional-location=file:/etc/myapp/
~~~

Giả sử `/etc/myapp/application.properties` hoặc `application-prod.properties` tồn tại đúng profile, Boot sẽ thêm location đó vào default search list. Theo Spring Boot 3.3, location thư mục nên kết thúc bằng `/`.

So sánh:

~~~properties
spring.config.additional-location=file:/etc/myapp/
spring.config.location=file:/etc/myapp/
~~~

`additional-location` **bổ sung** vào default locations; `location` **thay thế** danh sách default search locations. Nếu muốn override safe defaults trong JAR, `additional-location` thường thuận tiện hơn.

`spring.config.location`/`additional-location` được xác định sớm khi Boot tìm config, vì vậy thiết lập qua env/CLI/system property khi khởi động thay vì đặt trong file mà app còn chưa biết phải tìm.

### 4.3. optional và fail-fast

~~~bash
# Bổ sung file config tùy chọn, thiếu thì bỏ qua:
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/myapp/
~~~

`optional:` hợp lý cho cấu hình không bắt buộc. Với TLS private key hoặc DB credentials bắt buộc, **không dùng optional/default password rỗng** để che lỗi provision. Fail-fast khi missing required config/secret thường an toàn hơn.

### 4.4. Spring profiles

File `/etc/myapp/application-prod.properties`:

~~~properties
server.port=8443
app.storage.root=/var/lib/myapp/uploads
~~~

Launch:

~~~bash
java -jar /opt/myapp/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/myapp/
~~~

ApplicationContext nạp đúng profile theo Config Data rules. Không commit production passwords vào profile file trong repo. Có thể chứa **paths** tới external secret files, nhưng không chứa raw sensitive material.

## 5. Runtime environment variables, placeholders và precedence

Safe defaults packaged trong `src/main/resources/application.properties`:

~~~properties
server.port=8080
app.storage.root=${APP_DATA_DIR:./runtime/data}
spring.servlet.multipart.location=${APP_TMP_DIR:./runtime/tmp}
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

Spring placeholders `${NAME:default}` sẽ dùng env/config property nếu có, fallback nếu thiếu. Trong file thực, cú pháp bắt đầu bằng ký tự dollar và ngoặc nhọn. Defaults relative chỉ nên dành cho **local lab**, production phải cung cấp durable/writable paths theo deployment.

Ví dụ Linux:

~~~bash
export APP_DATA_DIR=/var/lib/myapp/uploads
export APP_TMP_DIR=/var/tmp/myapp/multipart
java -jar /opt/myapp/app.jar
~~~

Boot relaxed binding có thể map `APP_STORAGE_ROOT` thành `app.storage.root`. Dùng env để truyền **đường dẫn** có thể dễ hơn truyền toàn bộ PEM key/password trong env. Env secrets vẫn có rủi ro lộ qua process introspection, crash dumps hoặc debug tools.

**Precedence quan trọng:** CLI args thường có ưu tiên cao hơn environment variables. Nếu có `--app.storage.root=/wrong/place` trong launch script, một biến `APP_STORAGE_ROOT=/var/lib/myapp/uploads` có thể không được áp dụng. Xác minh effective property và nguồn override, tránh log raw secret values.

## 6. Secret files bằng configtree:

Kubernetes/Docker/secret provider có thể mount mỗi secret key thành một file:

~~~text
/run/secrets/myapp/
    db.password
    partner.api-key
~~~

Để Boot coi filenames thành property names:

~~~properties
spring.config.import=configtree:/run/secrets/myapp/
~~~

Khi được import, `db.password` được đọc từ file `db.password`, `partner.api-key` từ file tương ứng. Các properties khác có thể tham chiếu:

~~~properties
spring.datasource.password=${db.password}
partner.api-key=${partner.api-key}
~~~

Nếu secret tree bắt buộc, không đặt `optional:` trước `configtree:`. Ứng dụng phải fail khi missing mount hoặc quyền đọc bị từ chối. Đừng in giá trị password/api-key trong logs.

Ví dụ tạo **giá trị giả** chỉ cho local:

~~~bash
mkdir -p runtime/secrets
printf '%s' 'demo-only-password' > runtime/secrets/db.password
chmod 600 runtime/secrets/db.password
~~~

**configtree không có nghĩa hot-refresh tất cả beans.** Thay file cấu hình/secret không tự làm `@ConfigurationProperties`, DataSource, HttpClient hay mọi component rebind. Thông thường cần rolling restart; SSL PEM bundles có cơ chế reload riêng khi được bật và consumer hỗ trợ.

## 7. Chứng thư TLS: certificate, private key, keystore, truststore

| Tài nguyên | Vai trò | Phân loại |
| --- | --- | --- |
| `server.crt` | Public server certificate và chain | Thường là public data |
| `server.key` | Server private key chứng minh identity | **Secret cực kỳ nhạy cảm** |
| `server.p12` / JKS | KeyStore có thể chứa certificate/private key | Secret khi chứa private key |
| CA cert / truststore | Bảo vệ việc tin đúng đối tác | Bảo vệ integrity, không nhất thiết confidentiality |
| Keystore password | Mở bảo vệ keystore/private key | Secret |
| Outbound client cert/key | Identity của ứng dụng khi mTLS tới downstream | Secret và **khác** inbound TLS identity |

Certificate có thể được phát hành từ PKI/CA công ty hoặc public CA. Private key tuyệt đối không đặt trong JAR, Git, Dockerfile, ConfigMap hoặc logs. Dùng secret management, volume read-only, permissions tối thiểu và rotation/audit.

### 7.1. HTTPS server từ external PEM

Boot 3.3 hỗ trợ:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.certificate=file:/etc/myapp/tls/server.crt
server.ssl.certificate-private-key=file:/etc/myapp/tls/server.key
~~~

Private key PEM nên ở định dạng **PKCS#8** (thường bắt đầu bằng `-----BEGIN PRIVATE KEY-----` hoặc `-----BEGIN ENCRYPTED PRIVATE KEY-----`). Key PKCS#1/SEC1 cũ có thể cần chuyển đổi định dạng theo OpenSSL/Spring integration.

**Không tự tạo đồng thời cổng HTTP 8080 và HTTPS 8443** chỉ vì đặt `server.ssl.*` và `server.port=8443`. Spring Boot auto-config thông thường cấu hình một connector từ properties; muốn cả hai phải dùng explicit extra connector/server setup hoặc ingress.

### 7.2. HTTPS server từ external PKCS12

~~~properties
server.port=8443
server.ssl.key-store=file:/etc/myapp/tls/server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
~~~

Nếu key password khác keystore password, cấu hình `server.ssl.key-password` phù hợp. Đừng hardcode password thật vào packaged config; mounted secret files/provider có thể thích hợp hơn env var trong production.

### 7.3. Outbound trust khác inbound HTTPS

`server.ssl.*` cấu hình server identity để trình cho clients. Một `WebClient`/`RestClient` gọi downstream dùng private CA hoặc client mTLS phải có **client SSL trust/identity** riêng qua SSL bundle/HTTP client integration. Không lấy server key và tin rằng mọi outbound HTTP client sẽ tự trust các CA hoặc tự xuất trình client cert.

Không dùng trust-all, `curl -k` hoặc tắt hostname verification để chữa lỗi `PKIX path building failed` trong production. Sửa CA chain, truststore, SAN/hostname và certificate validity đúng nguyên nhân.

## 8. Spring Boot SSL bundles: tổ chức TLS material ngoài JAR

Spring Boot 3.3 có `spring.ssl.bundle.pem.*` và `spring.ssl.bundle.jks.*`, cho phép gắn một named bundle vào embedded web server.

### 8.1. PEM bundle file-backed

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key
~~~

`server.ssl.bundle=web` chọn bundle tên `web`. **Không dùng đồng thời `server.ssl.bundle` với discrete `server.ssl.key-store` hoặc `server.ssl.certificate`/`certificate-private-key`.** Theo docs Boot 3.3, cipher/protocol settings khi dùng bundle phải được khai báo trong bundle options ở chỗ thích hợp.

### 8.2. JKS/PKCS12 bundle

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.jks.web.keystore.location=file:/etc/myapp/tls/server.p12
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
~~~

Đây là **lựa chọn khác** so với PEM bundle, không cấu hình đồng thời hai loại bundle cùng tên với kỳ vọng app tự chọn. Cả certificate file location và keystore password phải đúng.

### 8.3. Reload certificate có điều kiện

Spring Boot 3.3 cho phép PEM bundle opt-in reload-on-update:

~~~properties
server.ssl.bundle=web
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key
spring.ssl.bundle.pem.web.reload-on-update=true
~~~

Trong docs Boot 3.3, consumers tương thích được liệt kê gồm **Tomcat và Netty embedded web servers**. File watcher phát hiện thay đổi file, có thể điều chỉnh quiet period qua `spring.ssl.bundle.watch.file.quiet-period`.

**Không bảo đảm mọi certificate update tự áp dụng:** Kubernetes Secret projection có thể thay symlink, `subPath` có thể không nhận updates, watcher có thể không thấy event mong muốn. Một kết nối TLS đã thiết lập còn giữ session state. Kiểm tra **new TLS handshakes** sau update, và nếu reload không được bảo đảm, dùng **rolling restart** theo chính sách release.

## 9. Các loại thư mục tạm trong Spring web runtime

| Thành phần | Property hoặc cách đặt | Vai trò |
| --- | --- | --- |
| JVM general temp | `-Djava.io.tmpdir=/var/tmp/myapp` | `Files.createTempFile`, nhiều Java libraries |
| Spring MVC Servlet multipart | `spring.servlet.multipart.location=/var/tmp/myapp/multipart` | Intermediate uploaded file parts |
| Tomcat base | `server.tomcat.basedir=/var/tmp/myapp/tomcat` | Base/work directories của embedded Tomcat |
| Spring WebFlux multipart decoder | `spring.webflux.multipart.file-storage-directory=/var/tmp/myapp/webflux` | Spill file parts khi quá max-in-memory |
| App processing temp | `app.processing.temp-root=/var/tmp/myapp/work` | Xử lý file tạm trong nghiệp vụ |
| Durable upload root | `app.storage.root=/var/lib/myapp/uploads` | File nghiệp vụ cần retention/backup |
| Optional access log | `server.tomcat.accesslog.directory` | Logs riêng, lifecycle khác temp |

**Không có một property chung bảo đảm mọi thư viện dùng cùng temp directory.** Đổi `java.io.tmpdir` không tự override app-specific temp paths; đổi multipart location cũng không có nghĩa mọi `Files.createTempFile` trong code được chuyển theo.

### 9.1. JVM temp là system property lúc startup

~~~bash
mkdir -p /var/tmp/myapp
java -Djava.io.tmpdir=/var/tmp/myapp \
  -jar /opt/myapp/app.jar
~~~

Đây là JVM option, không phải `spring.java.io.tmpdir`. Nhiều library đọc hoặc cache temp path khi initialize; không xem `System.setProperty("java.io.tmpdir", ...)` trong request handler là cấu hình runtime đáng tin.

Trong Docker/Kubernetes, có thể dùng:

~~~text
JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/var/tmp/myapp
~~~

Không đưa password vào `JAVA_TOOL_OPTIONS` vì JVM launcher có thể log option hoặc process arguments có thể bị đọc bởi tooling.

### 9.2. Spring MVC multipart spool

~~~properties
spring.servlet.multipart.location=/var/tmp/myapp/multipart
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

Boot 3.3 mô tả `location` là **intermediate location of uploaded files**. Không dùng nó như permanent storage. Directory cần tồn tại và writable trước khi ứng dụng nhận uploads.

~~~bash
mkdir -p /var/tmp/myapp/multipart
chmod 700 /var/tmp/myapp/multipart
~~~

`file-size-threshold=0B` cho phép Servlet implementation ghi parts xuống disk gần như ngay thay vì giữ toàn bộ trong memory. Multipart size limits không thay thế disk quota, antivirus scan, rate limits hay authentication.

### 9.3. WebFlux multipart (khác MVC)

Trong ứng dụng dùng `spring-boot-starter-webflux`:

~~~properties
spring.webflux.multipart.file-storage-directory=/var/tmp/myapp/webflux
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=20
~~~

Trong Boot 3.3, directory này lưu file parts vượt in-memory size, mặc định có thể tạo `spring-multipart` trong system temp. **Property này bị bỏ qua khi dùng `PartEvent` streaming support.** Với `Flux<PartEvent>`, cần tự tiêu thụ/release `DataBuffer` đúng cách, lưu file và quản lý backpressure/limits.

Nếu app dùng MVC/Tomcat, đừng copy `spring.webflux.multipart.*` rồi kỳ vọng nó thay Servlet multipart location; nếu app dùng WebFlux/Reactor Netty, đừng trông chờ `spring.servlet.multipart.location` phát huy tác dụng.

### 9.4. Tomcat basedir, access logs và app logs

~~~properties
server.tomcat.basedir=/var/tmp/myapp/tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=/var/log/myapp
~~~

Boot 3.3 dùng temp directory khi `server.tomcat.basedir` chưa set. `server.tomcat.accesslog.directory` có thể là absolute path hoặc relative theo Tomcat base. Nó khác `logging.file.name`/`logging.file.path` của application logs. Trong container nên ưu tiên stdout/stderr + log aggregator, tránh thêm writable log mounts nếu không cần.

## 10. Lab Java 17 + Spring Boot 3.3.5: upload lưu ngoài JAR

Dự án lab có Spring MVC REST endpoint nhận `MultipartFile` và ghi với tên UUID vào external `app.storage.root`, không dùng original filename hay classpath file. Cùng JAR sau đó chạy với HTTPS bundle từ external PEM.

### 10.1. Cấu trúc project

~~~text
external-runtime-lab/
├── pom.xml
├── runtime/                      # ngoài src/main/resources, KHÔNG commit
│   ├── config/
│   ├── tls/
│   ├── data/
│   ├── tmp/
│   └── secrets/
└── src/main/
    ├── java/com/example/external/
    │   ├── ExternalRuntimeApplication.java
    │   ├── StorageProperties.java
    │   └── UploadController.java
    └── resources/
        └── application.properties
~~~

Các files trong `runtime/` là nguồn config/data tại runtime, **không phải** một phần của JAR. Maven chỉ đóng gói `src/main/resources`, nên không đặt certificate/private key dưới đó.

### 10.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>external-runtime-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` cung cấp MVC/embedded Tomcat/Servlet multipart. `spring-boot-starter-actuator` cho phép `/actuator/health` khi expose phù hợp. Java 17 hỗ trợ records.

### 10.3. Main class

**`src/main/java/com/example/external/ExternalRuntimeApplication.java`:**

~~~java
package com.example.external;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExternalRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalRuntimeApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` cho Spring Boot tìm config record trong package. Không tự `new` record với path hardcode trong controller.

### 10.4. StorageProperties.java

~~~java
package com.example.external;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path root) {
}
~~~

Với record có một constructor trong Boot 3.3, constructor binding được suy ra. Property `app.storage.root` được convert thành `Path`, không cần viết custom parser.

### 10.5. UploadController.java

~~~java
package com.example.external;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class UploadController {

    private final Path root;

    public UploadController(StorageProperties properties)
            throws IOException {
        if (properties.root() == null) {
            throw new IllegalStateException(
                    "app.storage.root must be configured");
        }

        root = properties.root().toAbsolutePath().normalize();
        Files.createDirectories(root);

        if (!Files.isDirectory(root) || !Files.isWritable(root)) {
            throw new IllegalStateException(
                    "Upload directory is not writable: " + root);
        }
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file)
            throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty file");
        }

        // Không dùng getOriginalFilename() làm filesystem path.
        String id = UUID.randomUUID().toString();
        Path target = root.resolve(id + ".bin");

        // Ghi file mới; không overwrite path do user chọn.
        try (InputStream in = file.getInputStream()) {
            Files.copy(in, target);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(id, Files.size(target)));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable String id) {
        try {
            UUID.fromString(id);
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid id");
        }

        Path path = root.resolve(id + ".bin");
        if (!Files.isRegularFile(path)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "file not found");
        }

        Resource resource = new FileSystemResource(path);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(id + ".bin")
                                .build()
                                .toString())
                .body(resource);
    }

    public record UploadReceipt(String id, long bytes) {
    }
}
~~~

**Phân tích:**

1. Controller đọc external storage root qua dependency injection, tạo thư mục nếu thiếu và fail-fast nếu không writable.
2. `Files.copy(InputStream, Path)` tạo output file bằng UUID, không dựa vào tên file client. Không ghi vào `src/main/resources/static` hay JAR.
3. `UUID.fromString` lọc ID route, không nhận raw path traversal từ user.
4. `ResponseEntity.status(CREATED)` chỉ trả sau khi copy xong; response body chứa ID và kích thước file đã ghi.
5. Endpoint GET dùng `application/octet-stream` và `Content-Disposition: attachment` để tránh browser tự interpret nội dung upload như HTML.
6. `Files.isWritable` tại startup không bảo đảm sau đó volume không hết dung lượng/không bị remount read-only.
7. Đây là **demo về external storage**: production cần authz từng file, user quotas, malware/content validation, retention, audit và cleanup file partial khi copy thất bại.
8. Việc copy trực tiếp có thể để lại file dở nếu crash. Trong production có thể stage cùng filesystem rồi move atomic khi supported; không assume `Files.move` giữa `emptyDir` và PVC khác filesystem là atomic.

### 10.6. application.properties packaged: safe local defaults

~~~properties
spring.application.name=external-runtime-lab
server.port=8080

app.storage.root=${APP_DATA_DIR:./runtime/data}
spring.servlet.multipart.location=${APP_TMP_DIR:./runtime/tmp}

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

Config này **không có password/key material**. Dùng relative paths chỉ cho local. Production phải cung cấp absolute dirs thông qua env/config volume.

### 10.7. Tạo runtime folders và build

~~~bash
mkdir -p runtime/data runtime/tmp runtime/config runtime/tls runtime/secrets
chmod 700 runtime/data runtime/tmp runtime/tls runtime/secrets
mvn clean package
~~~

Build output:

~~~text
target/external-runtime-lab-0.0.1-SNAPSHOT.jar
~~~

`.gitignore`/`.dockerignore` nên bỏ secrets và runtime tree:

~~~gitignore
/runtime/
/target/
*.key
*.p12
*.jks
~~~

Kiểm tra danh sách resources trong JAR:

~~~bash
jar tf target/external-runtime-lab-0.0.1-SNAPSHOT.jar \
  | grep -E 'application.properties|server.key|server.p12|runtime/'
~~~

Chỉ có safe application properties là hợp lý; **không nên xuất hiện private key hoặc runtime data**. Secret scanning phải áp dụng cả Git history/JAR/image layers, vì ignore rules không xóa secret đã từng commit.

## 11. Chạy HTTP local và kiểm chứng external upload

Trong project root:

~~~bash
APP_DATA_DIR=./runtime/data \
APP_TMP_DIR=./runtime/tmp \
java -Djava.io.tmpdir=./runtime/tmp \
  -jar target/external-runtime-lab-0.0.1-SNAPSHOT.jar
~~~

Dòng trên dùng shell POSIX; Windows PowerShell có cách set env `$env:APP_DATA_DIR` riêng. Đừng giả định syntax giống nhau.

Trong terminal khác:

~~~bash
printf 'Hello external storage\n' > runtime/sample.txt
curl -i -F "file=@runtime/sample.txt" \
  http://127.0.0.1:8080/api/files
~~~

Kỳ vọng HTTP **201 Created** với JSON có hình dạng:

~~~json
{
  "id": "1c8de7ae-b38c-4f84-98b1-98e1f63ba72c",
  "bytes": 23
}
~~~

ID là ví dụ vì UUID runtime ngẫu nhiên. Sample string dài **23 UTF-8 bytes** nếu tạo bằng lệnh `printf` ở trên; số thực tế có thể khác nếu bạn thay sample hoặc shell/file encoding.

Kiểm tra:

~~~bash
ls -la runtime/data
~~~

File mới có tên `<uuid>.bin` trong external directory, không nằm trong JAR. Để tải file, thay `UUID_THUC_TE` bằng ID đúng trong response JSON:

~~~bash
curl -i http://127.0.0.1:8080/api/files/UUID_THUC_TE
~~~

Kỳ vọng HTTP 200 + `application/octet-stream` + `Content-Disposition: attachment` và binary body. Demo này **không** chứng minh file durable nếu `runtime/data` thực chất là container ephemeral layer; phần deploy cần chọn đúng PVC/object storage.

## 12. Chạy HTTPS cùng JAR bằng external PEM files

### 12.1. Tạo self-signed certificate chỉ cho localhost lab

~~~bash
mkdir -p runtime/tls
openssl req -x509 -newkey rsa:2048 -sha256 -days 7 -nodes \
  -keyout runtime/tls/server.key \
  -out runtime/tls/server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 runtime/tls/server.key
~~~

Cert có SAN localhost/loopback và chỉ hiệu lực 7 ngày. `-nodes` tạo key không mã hóa, **chỉ dùng trong lab**; production dùng PKI/key protection/secret manager. Nếu OpenSSL version không hỗ trợ `-addext`, dùng config file extension tương đương, không loại bỏ SAN rồi tắt hostname verification.

Xem metadata certificate mà không in private key:

~~~bash
openssl x509 -in runtime/tls/server.crt \
  -noout -subject -dates -ext subjectAltName
~~~

### 12.2. External profile application-prod.properties

Tạo `runtime/config/application-prod.properties`:

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.pem.web.keystore.certificate=file:./runtime/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:./runtime/tls/server.key

# Tùy chọn thử hot reload trên Tomcat/Netty hỗ trợ:
spring.ssl.bundle.pem.web.reload-on-update=true

app.storage.root=./runtime/data
spring.servlet.multipart.location=./runtime/tmp
~~~

Lưu ý `file:./runtime/tls/...` theo **current working directory**. Production nên thay bằng `file:/etc/myapp/tls/...` tuyệt đối.

### 12.3. Chạy lại mà không rebuild

Dừng HTTP process, chạy:

~~~bash
java -Djava.io.tmpdir=./runtime/tmp \
  -jar target/external-runtime-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./runtime/config/
~~~

Spring Boot đọc external `application-prod.properties` và mở HTTPS 8443. Không phải sửa/rebuild JAR. Kiểm chứng certificate bằng trust riêng của lab:

~~~bash
curl --cacert runtime/tls/server.crt \
  https://localhost:8443/actuator/health
~~~

Kỳ vọng status 200 và body `{"status":"UP"}` nếu health indicators bình thường. Không dùng `curl -k` làm giải pháp production. Khi HTTPS chỉ nghe 8443, đừng cho rằng HTTP 8080 vẫn hoạt động đồng thời qua cùng Boot auto-config.

### 12.4. Rotation không chỉ là copy đè file

Khi certificate được thay:

- Kiểm tra key và certificate match, SAN/expiry/chain đúng.
- Cập nhật file pair theo cách tránh watcher đọc một nửa state.
- Kiểm tra `reload-on-update`, consumer hỗ trợ và cách volume projection gửi filesystem events.
- Test **new TLS handshake** sau update và client trust.
- Nếu chưa chứng minh reload đáng tin, **rolling restart** theo chiến lược không làm gián đoạn traffic.

Đừng coi mọi `application.properties` thay đổi cũng hot reload như PEM bundles. Hầu hết runtime binding được thiết lập lúc app start.

## 13. Docker: mounts thay vì COPY secrets vào image

### 13.1. Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY target/external-runtime-lab-0.0.1-SNAPSHOT.jar /app/app.jar
EXPOSE 8080

# Không COPY runtime/, tls private key hoặc secrets.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Container base image phải được pin/audit và production nên dùng non-root user. `EXPOSE` là metadata, không mở cổng trên host. Nếu external config bật HTTPS 8443, cần đồng bộ service/container port mapping.

### 13.2. docker-compose.yml cho HTTP lab

~~~yaml
services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      APP_DATA_DIR: /var/lib/myapp/uploads
      APP_TMP_DIR: /var/tmp/myapp
      JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/var/tmp/myapp
      SPRING_CONFIG_ADDITIONAL_LOCATION: file:/etc/myapp/config/
    volumes:
      - ./runtime/config:/etc/myapp/config:ro
      - ./runtime/tls:/etc/myapp/tls:ro
      - ./runtime/tmp:/var/tmp/myapp
      - ./runtime/data:/var/lib/myapp/uploads
~~~

Trên host:

~~~bash
mkdir -p runtime/config runtime/tls runtime/tmp runtime/data
docker compose up --build
~~~

Ví dụ trên chỉ dành cho local: bind-mount data path không tự đáp ứng production backup/replication, image đang dùng root trừ khi đổi user, và HTTPS chưa được enable trong Compose này. Nếu ConfigMap/secret paths chuyển vào container, `application-prod.properties` phải tham chiếu **container paths** thay vì host paths.

### 13.3. Docker read-only root filesystem

Khi bật `read_only: true` hoặc Kubernetes `readOnlyRootFilesystem: true`, ứng dụng vẫn cần writable mounts cho:

- `java.io.tmpdir` (JVM/libraries).
- Servlet multipart spool `spring.servlet.multipart.location`.
- Tomcat basedir/workdir nếu cần.
- Application processing scratch files.
- Business uploads nếu ghi local.
- File logs nếu không dùng stdout.

JAR, app config và TLS private keys nên giữ read-only. **Mount cert ro không có nghĩa process nào có quyền đọc cũng an toàn** — nếu app bị compromise, key vẫn có thể bị exfiltrate; cần least privilege và policies.

## 14. Kubernetes: ConfigMap, Secret, emptyDir, PVC

| Volume/resource | Cần cho | Không dùng để |
| --- | --- | --- |
| ConfigMap volume | Nonsecret app config, paths, limits | Raw TLS private key/password thật |
| Secret volume | TLS key/cert, credentials | Thay thế RBAC/encryption/audit |
| emptyDir | Multipart spill/temp/cache ngắn hạn | Durable user uploads |
| PVC | Files cần retention trên filesystem | Giả định multi-pod RWX nếu storage class không hỗ trợ |
| Object storage | Scalable user data nhiều replicas | JVM/temp workdir cần POSIX temp |
| Env vars | Paths, flags, nonsecret config | Dump full secrets không kiểm soát |

### 14.1. ConfigMap example

File `application.properties` được mount từ ConfigMap ở `/etc/myapp/config/application.properties`:

~~~properties
server.port=8443
server.ssl.bundle=web
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key

app.storage.root=/var/lib/myapp/uploads
spring.servlet.multipart.location=/var/tmp/myapp

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

management.endpoints.web.exposure.include=health
~~~

Chỉ **paths** tới TLS secret xuất hiện ở ConfigMap, không có private key contents. Nếu ứng dụng terminate TLS ở ingress, backend có thể sử dụng HTTP và không cần mount inbound server private key.

### 14.2. Deployment Pod template fragment

Đoạn này là **một phần Deployment template**, giả định ConfigMap `myapp-config`, Secret `myapp-tls`, PVC `myapp-data` đã tồn tại. Không phải manifest hoàn chỉnh:

~~~yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/myapp:1.0
          ports:
            - name: https
              containerPort: 8443
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/myapp/config/
            - name: JAVA_TOOL_OPTIONS
              value: -Djava.io.tmpdir=/var/tmp/myapp
            - name: APP_DATA_DIR
              value: /var/lib/myapp/uploads
            - name: APP_TMP_DIR
              value: /var/tmp/myapp
          volumeMounts:
            - name: config
              mountPath: /etc/myapp/config
              readOnly: true
            - name: tls
              mountPath: /etc/myapp/tls
              readOnly: true
            - name: scratch
              mountPath: /var/tmp/myapp
            - name: data
              mountPath: /var/lib/myapp/uploads
      volumes:
        - name: config
          configMap:
            name: myapp-config
        - name: tls
          secret:
            secretName: myapp-tls
            defaultMode: 0440
        - name: scratch
          emptyDir:
            sizeLimit: 1Gi
        - name: data
          persistentVolumeClaim:
            claimName: myapp-data
~~~

**Kiểm chứng các giả định:**

1. JRE image có thể chạy UID 10001; secret files có filenames `server.crt`/`server.key` đúng đường dẫn.
2. `fsGroup`/volume file mode `0440` thực sự cho phép app đọc key, không làm key world-readable. Ownership của PVC có thể cần chuẩn bị riêng.
3. Writable emptyDir ở `/var/tmp/myapp` đủ cho JVM/Servlet temp; app không vô ý ghi vào read-only root filesystem.
4. Data PVC phù hợp yêu cầu durability và access mode. Nhiều pods/nodes dùng chung PVC RWO có thể fail mount; chọn object storage khi cần scale-out.
5. `emptyDir.sizeLimit` và container ephemeral-storage resources/eviction budgets phải đồng bộ; disk vẫn có thể đầy.
6. ConfigMap update không mặc nhiên rebind property vào các Spring beans đang chạy; cert rotation còn phụ thuộc watcher/reload.
7. `subPath` mounts có thể không cập nhật khi Secret thay; phải test reload/rolling restart thực.
8. Service/Ingress/probes phải dùng HTTPS 8443 nếu backend bật TLS. Một plain HTTP check trên HTTPS port sẽ fail dù app khỏe.

Kubernetes Secrets cần RBAC, etcd encryption at rest nếu policy yêu cầu, access auditing, rotation và separation of duties. Secret object không tự bảo đảm mọi thứ an toàn chỉ vì có kind=Secret.

### 14.3. Đối chiếu temp và durability

`emptyDir` phù hợp cho multipart buffers vì dữ liệu request chỉ cần tồn tại trong lúc xử lý ở Pod đó. Nhưng nếu upload response thành công và ứng dụng lưu file vào `emptyDir`, Pod replacement có thể xóa file. **Durable storage** phải được chọn theo contract — PVC có backup/availability đúng hoặc object store. Với nhiều replicas, client sau upload có thể GET từ Pod khác; private Pod filesystem không cho kết quả nhất quán.

## 15. systemd khi chạy executable JAR trên máy Linux

Systemd unit minh họa:

~~~ini
[Unit]
Description=Externalized Spring Boot application
After=network.target

[Service]
Type=simple
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp
StateDirectory=myapp
CacheDirectory=myapp
Environment=APP_DATA_DIR=/var/lib/myapp/uploads
Environment=APP_TMP_DIR=/var/cache/myapp
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/myapp/
ExecStart=/usr/bin/java -Djava.io.tmpdir=/var/cache/myapp -jar /opt/myapp/app.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

`StateDirectory=myapp` và `CacheDirectory=myapp` giúp systemd quản lý directories dưới `/var/lib/myapp` và `/var/cache/myapp` trong nhiều Linux installations. User/group `myapp` và JDK path phải tồn tại, certificate/secrets phải readable bởi service identity. Unit chưa phải security-hardening hoàn chỉnh; khi bật `ProtectSystem=strict` hay `ReadWritePaths` phải cấp quyền ghi state/cache rõ ràng.

Không đặt raw DB passwords trong unit file hoặc CLI arguments. Dùng secret/credential facilities hoặc root-owned restricted files và định nghĩa loading/rotation policy phù hợp.

## 16. TLS terminate ở Ingress hay trong Spring Boot?

### 16.1. TLS kết thúc tại edge

~~~text
Browser -- HTTPS 443 --> Ingress/Gateway (giữ public TLS key)
                         |
                         '-- HTTP 8080 --> Spring Boot
~~~

Nếu organization chấp nhận HTTP trên internal trusted segment, app Pod **không nhất thiết cần mount public server private key**. Cert rotation diễn ra tại ingress. Nếu yêu cầu encrypt mọi hop hoặc mTLS nội bộ, cần backend TLS riêng.

### 16.2. TLS end-to-end hoặc mTLS

~~~text
Browser -- HTTPS 443 --> Ingress
                         |
                         '-- HTTPS/mTLS 8443 --> Spring Boot
                                                   server cert/key ở runtime
~~~

Khi app chịu trách nhiệm HTTPS, `server.ssl.bundle` hoặc `server.ssl.*` phải trỏ đúng external cert/key. Khi app còn đóng vai outbound HTTPS client, truststore/client cert là **khái niệm khác**.

Đừng nhầm “đưa chứng thư ra ngoài gói ứng dụng” với “mọi Pod bắt buộc phải giữ certificate của public domain”. Identity cần đặt tại thành phần terminate TLS.

## 17. File upload và temp khi nhiều replicas

~~~text
Client -> LB
          |-> Pod A: /tmp/uploads/file-X
          '--> Pod B: /tmp/uploads/ không có file-X
~~~

Chuyển upload ra `/tmp` đã tách khỏi JAR nhưng **không đảm bảo data visibility**. Khi GET đến Pod B, có thể 404. Nếu contract cần durable/shared files, cân nhắc object storage, shared PVC có access mode phù hợp, database metadata và retention/backup policy.

### 17.1. Upload bị crash giữa chừng

Controller lab ghi trực tiếp target, nên có thể để lại partial file nếu crash. Production pipeline có thể:

~~~text
Upload request
  -> stage temporary file (nằm cùng FS với final nếu muốn atomic move)
  -> validate size/type/hash/scan/quota
  -> finalize (atomic move khi filesystem hỗ trợ)
  -> commit metadata
  -> return success theo durability contract
~~~

Không giả định `Files.move(..., ATOMIC_MOVE)` hoạt động xuyên hai volumes `emptyDir` và PVC. Với object storage, multipart upload/finalize có semantics khác. Cần cleanup/incomplete-upload expiration và audit.

### 17.2. Chống upload abuse

- Dùng server-generated UUID thay client original filename.
- Lưu ngoài `static`/`public`; khi download kiểm soát auth và `Content-Disposition`.
- Giới hạn request/file sizes, concurrent uploads, request rate và disk quotas.
- Không tin MIME/extension do client cung cấp; scan/validate khi domain yêu cầu.
- Giảm nguy cơ symlink/path traversal bằng storage layout/permissions và UUID paths.
- Dữ liệu user upload có retention/backup/encryption at rest theo policy riêng.

## 18. Secret rotation và config reload: đừng suy luận sai

Có ba cơ chế khác nhau:

| Thay đổi | Kỳ vọng |
| --- | --- |
| Thay external application.properties | Spring thường không tự rebind tất cả beans; restart/refresh theo cơ chế đã thiết kế |
| Thay mounted Kubernetes Secret file | K8s có thể cập nhật projection; app không chắc tự đọc lại |
| Thay file-backed PEM SSL bundle có reload-on-update | Có thể reload với Tomcat/Netty supported consumer + watcher; phải kiểm thử thực tế |

**Không đánh đồng** dynamic TLS bundle reload với dynamic update của `spring.datasource.password`, `server.port`, `app.storage.root` hoặc mọi `@ConfigurationProperties`. Thay server port hầu như cần khởi động lại web listener, không đơn giản thay file text.

Một quy trình an toàn:
1. Stage new cert/key/config với quyền đúng, validate trước.
2. Thay theo atomic/controlled mechanism để không có khoảng certificate/key mismatch.
3. Test certificate SAN/expiry/trustchain và new handshake.
4. Rolling restart nếu cơ chế hot reload không được hỗ trợ/đảm bảo.
5. Quan sát health, 5xx, TLS alerts và có rollback plan.

## 19. File permissions và non-root process

Trong production:
- `/opt/myapp/app.jar`: process chỉ đọc.
- `/etc/myapp/config`: chỉ đọc.
- `/etc/myapp/tls/server.key`: chỉ service identity được đọc, không log.
- `/var/tmp/myapp`: service có quyền read/write/delete; quotas và cleanup.
- `/var/lib/myapp/uploads`: service có quyền ghi phù hợp; nếu shared storage, kiểm soát owner/ACL.
- Logging: ưu tiên stdout, hoặc external logs dir theo retention policy.

### 19.1. Không dùng chmod 777 để chữa lỗi

Nếu `AccessDeniedException`:
1. Xác minh process UID/GID và permission của **mọi parent directories**.
2. Kiểm tra Kubernetes volume readOnly/rootFS read-only, fsGroup, ACL và SELinux/AppArmor.
3. Kiểm tra disk quota, storage limit, file inode exhaustion.
4. Kiểm tra current working directory và absolute vs relative paths.
5. Kiểm tra secret projection mode/subPath updates.

`chmod -R 777` có thể mở quyền đọc/ghi không cần thiết cho secrets/upload data. Hãy sửa identity/permissions và mounts thay vì biến toàn bộ filesystem thành writable.

### 19.2. Cert/key integrity cũng quan trọng

Dù CA certificate không cần bí mật, attacker sửa truststore có thể khiến ứng dụng tin endpoint giả. Bảo vệ **integrity** của truststore/CA bundles bằng read-only mounts, checksum/signature và RBAC.

## 20. Chẩn đoán lỗi startup, HTTPS, multipart và storage

| Dấu hiệu | Nguyên nhân đáng thử | Hướng xử lý |
| --- | --- | --- |
| `FileNotFoundException` ở TLS | Sai `file:` path hoặc volume chưa mount | Xem actual paths và mounts |
| `AccessDeniedException` với key | UID/GID/mode/fsGroup/SELinux | Sửa quyền đọc tối thiểu |
| Keystore password error | Sai PKCS12/JKS type hoặc password | Verify keystore bằng keytool; không log secret |
| `PKIX path building failed` | Truststore/CA client thiếu | Cấu hình outbound trust đúng |
| Hostname/SAN mismatch | Cert không chứa hostname | Cấp lại cert đúng SAN, không trust-all |
| HTTPS không lên sau thêm prod config | `spring.config.additional-location` hoặc profile sai | Kiểm tra external config load và effective port |
| HTTP request đến HTTPS port | Scheme mismatch | Dùng HTTPS và port tương ứng |
| Cert đã đổi nhưng app còn cert cũ | SSL reload unsupported/watcher miss | Test new handshake, rolling restart |
| App fail Config Data import | Mandatory location/secret thiếu | Mount trước startup, kiểm tra prefix |
| Placeholder unresolved | Env var, configtree key sai | So property name và source precedence |
| Upload 500 | Tmp location không writable hoặc disk full | Kiểm tra Servlet multipart spool/quota |
| Upload >5MB | Multipart file-size limit | Điều chỉnh policy, không bỏ limits vô hạn |
| WebFlux multipart path không có tác dụng | Sai stack hoặc đang dùng PartEvent | Chọn config đúng và explicit stream handling |
| Tomcat create temp failure | basedir/JVM temp read-only | Mount writable scratch |
| Dữ liệu biến mất sau Pod replacement | File lưu trong emptyDir/writable layer | Dùng PVC/object storage |
| Pod A upload, Pod B không thấy | Filesystem private per Pod | Shared durable store |
| `No space left on device` | Ephemeral/durable disk full | Quotas, cleanup, monitoring |
| Config mới không có hiệu lực | Boot không auto-rebind | Restart hoặc supported refresh |
| `/actuator/env` lộ giá trị | Expose debug/config quá rộng | Security/exposure restrictions |
| Không biết file đang lưu ở đâu | Relative path đổi theo WorkingDirectory | Config absolute path, structured logging an toàn |

### 20.1. Chẩn đoán theo thứ tự

~~~text
Startup fail?
  +--> Property source loaded đúng chưa?
  +--> Cert/key có tồn tại, readable, đúng format?
  +--> Temp/Tomcat base writable?
  '--> Server port/TLS configuration đúng?

Upload fail?
  +--> Request vượt multipart limit?
  +--> Multipart spool còn dung lượng?
  +--> Business output writable/durable?
  '--> Name/path validation + cleanup?

TLS handshake fail?
  +--> Protocol/port/scheme?
  +--> SAN/chain/expiry/trust?
  '--> Certificate reload state và ingress termination?
~~~

Không “fix” bằng tắt TLS verification, in key ra logs, `chmod 777` hoặc bỏ disk quotas. Những cách đó chỉ che nguyên nhân hoặc làm deployment kém an toàn.

## 21. Bài tập và smoke tests

### Bài tập 1 — một JAR hai môi trường

Build Maven một lần. Chạy HTTP `8080` bằng local `APP_DATA_DIR`/`APP_TMP_DIR`; sau đó restart cùng JAR với `--spring.profiles.active=prod` và `--spring.config.additional-location=file:./runtime/config/` để có HTTPS 8443/cert ngoài JAR. Chứng minh không sửa bytecode/không rebuild.

### Bài tập 2 — test directory permission

Cho temp path trỏ tới folder service user không được ghi. Gửi multipart upload để quan sát failure trong spool layer, khôi phục proper UID/GID/permissions. Không test phá hoại trên shared production node.

### Bài tập 3 — bắt buộc phải có private key

Đặt `server.ssl.bundle=web` nhưng private-key file path sai, khởi động. Ghi nhận lỗi an toàn (không in key). Sửa secret mount/path, verify với `curl --cacert`. Không bỏ TLS để tạm chạy public service.

### Bài tập 4 — configtree secrets

Mount file `db.password` vào `/run/secrets/myapp`, dùng `spring.config.import=configtree:/run/secrets/myapp/`. Viết một test xác minh property tồn tại/đã bind nhưng **không print giá trị**. Làm thiếu required directory để kiểm chứng fail-fast.

### Bài tập 5 — WebFlux vs MVC

Trong một project WebFlux riêng, test `spring.webflux.multipart.file-storage-directory` với file lớn hơn `max-in-memory-size`; sau đó dùng `Flux<PartEvent>` và giải thích vì sao temp property không áp dụng. Đối chiếu với `spring.servlet.multipart.location` của MVC.

### Bài tập 6 — Secret rotation

Tạo cert local thứ hai với SAN phù hợp, thay external PEM pair theo controlled update, thử `reload-on-update` của Tomcat/Netty và verify new handshake. Nếu watcher không hỗ trợ mount topology, restart rolling và ghi rõ giới hạn.

### Bài tập 7 — Docker/Kubernetes persistence

Chạy app với ephemeral temp + durable PVC/object storage. Upload, restart/replace Pod, kiểm tra temp cũ không được đảm bảo giữ, file durable vẫn tồn tại. Với 2 replicas, GET bất kỳ replica phải đọc đúng shared file nếu contract yêu cầu.

## 22. Câu hỏi tự kiểm tra

**1.** Vì sao private key không nên nằm trong `src/main/resources`?

**2.** `classpath:` và `file:` khác nhau thế nào?

**3.** `spring.config.location` và `spring.config.additional-location` khác gì?

**4.** Khi nào nên dùng `optional:`? Tại sao required secret không nên optional?

**5.** `configtree:` biến file names thành property names ra sao? Có tự hot-reload DataSource không?

**6.** `server.ssl.certificate` và `server.ssl.certificate-private-key` cấu hình phía client hay server?

**7.** Có được kết hợp `server.ssl.bundle` với discrete `server.ssl.key-store`/`server.ssl.certificate` không?

**8.** `reload-on-update` có chắc hoạt động với mọi embedded server và Kubernetes Secret projection không?

**9.** `java.io.tmpdir`, `spring.servlet.multipart.location`, `spring.webflux.multipart.file-storage-directory` và `app.storage.root` có là cùng một property không?

**10.** Vì sao MVC multipart location không phải permanent user upload directory?

**11.** Khi dùng `PartEvent` streaming, WebFlux multipart file-storage-directory có hiệu lực không?

**12.** Root filesystem container read-only thì cần writable mounts ở đâu?

**13.** Upload file vào `emptyDir` có durable qua Pod replacement không?

**14.** Nếu Pod A ghi file local và Pod B nhận GET thì chuyện gì có thể xảy ra?

**15.** TLS terminate ở ingress, app có bắt buộc mount public server key không?

**16.** Khi cert SAN mismatch, có nên disable hostname verification không?

**17.** Vì sao absolute paths production an toàn hơn relative paths?

**18.** Nguy cơ của việc đưa passwords vào CLI args/env dump là gì?

**19.** Vì sao phải scan JAR/image layers dù đã có `.dockerignore`?

**20.** Upload controller phải xử lý gì khi user gửi `../filename`?

**Đáp án:**

1. Bị đóng vào JAR/image, dễ leak/khó rotate giữa môi trường.
2. `classpath:` là packaged/application classpath resource; `file:` trỏ external file.
3. `location` thay default locations, `additional-location` bổ sung.
4. Dùng cho config tùy chọn; required secret missing nên fail-fast.
5. File names thành properties, content thành values; không tự rebind DataSource.
6. Server-side TLS identity; outbound client trust khác.
7. Không theo Boot 3.3 SSL bundle contract.
8. Không; phụ thuộc supported Tomcat/Netty consumers, watcher, volume behavior.
9. Không: JVM temp, Servlet spool, WebFlux spool và durable storage có vai trò khác nhau.
10. Spool có thể bị dọn ngay sau request; dùng storage riêng cho durable data.
11. Không, docs ghi ignored với PartEvent streaming support.
12. JVM/temp, multipart spool, Tomcat work dirs và business data writable; config/tls read-only.
13. Không được đảm bảo; emptyDir thuộc Pod lifecycle.
14. Pod B có thể 404; dùng shared durable store.
15. Không nếu TLS chỉ kết thúc ở ingress và backend hop HTTP được phép.
16. Không; sửa certificate SAN/CA/hostname.
17. Không lệ thuộc cwd và dễ audit/mount/quota.
18. Process introspection, logs, history, crash diagnostics có thể lộ secret.
19. Private key có thể đã nằm trong packaged JAR/src resources hoặc build layers.
20. Không dùng client filename làm path; tạo ID/tên server-side và kiểm soát authorization.

## 23. Checklist trước production

- [ ] Build một immutable JAR/image; không package private key/password/upload data.
- [ ] Scan Git history, JAR và container image layers để phát hiện secrets.
- [ ] Tách external config, Secret volumes, writable temp và durable storage.
- [ ] Đọc đúng `spring.config.additional-location`/`spring.config.import` và precedence.
- [ ] Required secrets được mount trước startup; không default password thật.
- [ ] Cert có đúng SAN/expiry/chain/key, file permission tối thiểu.
- [ ] Dùng **một** phương thức SSL server: discrete `server.ssl.*` hoặc `server.ssl.bundle`.
- [ ] Không nhầm server SSL identity với outbound HTTP client CA/trust.
- [ ] Kiểm thử reload-on-update/rolling restart và TLS handshake sau rotation.
- [ ] JVM `-Djava.io.tmpdir` trỏ writable volume.
- [ ] MVC `spring.servlet.multipart.location` writable, giới hạn file/request sizes.
- [ ] WebFlux `spring.webflux.multipart.file-storage-directory` đúng stack; PartEvent có lifecycle riêng.
- [ ] Tomcat basedir/access log và application logging nằm ở nơi thích hợp.
- [ ] Business uploads nằm ngoài static/public web roots, có authz/quota/scan.
- [ ] Durable file cần storage có backup, retention và multi-replica visibility.
- [ ] Non-root UID/GID, fsGroup, permissions, SELinux và readOnlyRootFilesystem được kiểm thử.
- [ ] ConfigMap không chứa raw secret; Kubernetes Secret có RBAC/encryption/audit phù hợp.
- [ ] Quotas/monitoring cho ephemeral disk, inodes, concurrent uploads và cleanup.
- [ ] Không expose Actuator env/configprops ra public; không log secrets.
- [ ] Smoke test app cùng artifact với HTTP/HTTPS và external mounts.
- [ ] Có runbook xử lý file missing, permission denied, wrong port, cert expire, disk full.
- [ ] Có kế hoạch redeploy/rollback khi config hoặc cert thay đổi.

## 24. Tài liệu tham khảo chính thức

1. Spring Boot 3.3 — Externalized Configuration (Config Data, additional-location, configtree, placeholders): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
2. Spring Boot 3.3 — SSL Bundles, PEM/JKS, reload-on-update (Tomcat/Netty): https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
3. Spring Boot 3.3 — Embedded Web Servers, HTTPS, discrete PEM/keystore và SSL bundles: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
4. Spring Boot 3.3 — Common Application Properties, multipart/Tomcat temp: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
5. Spring Framework — Servlet Multipart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
6. Spring Framework — WebFlux Multipart: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
7. Kubernetes ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
8. Kubernetes Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
9. Kubernetes Volumes và emptyDir: https://kubernetes.io/docs/concepts/storage/volumes/
10. Kubernetes Persistent Volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
11. Kubernetes ephemeral-storage limits: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#local-ephemeral-storage
12. Kubernetes Security Context: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
13. Docker Bind Mounts: https://docs.docker.com/engine/storage/bind-mounts/
14. Docker Volumes: https://docs.docker.com/engine/storage/volumes/
15. Java 17 Files APIs: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
