# Đọc Docker secrets và Kubernetes Secrets bằng configtree trong Spring Boot 3.3

## 1. Mục tiêu và vấn đề cần giải quyết

Ứng dụng Spring Boot thường cần thông tin nhạy cảm để kết nối tới cơ sở dữ liệu, message broker hoặc dịch vụ bên ngoài: mật khẩu, API token, khóa riêng, chứng chỉ, credential theo môi trường. Đưa trực tiếp các giá trị này vào `application.properties`, `application.yaml` hoặc build artifact có thể làm chúng bị lưu trong Git, image, pipeline log hay cấu hình được chia sẻ quá rộng.

Docker và Kubernetes có cơ chế cung cấp secret **dưới dạng các tệp nằm trong container**. Spring Boot 3.3 có thể đọc các tệp này bằng tính năng **configuration tree** của Config Data, sử dụng prefix:

```properties
spring.config.import=configtree:/duong-dan-trong-container/
```

Ý tưởng cốt lõi:

- Mỗi **tệp** trong cây cấu hình mang một giá trị.
- **Tên tệp và thư mục** tạo thành tên property trong Spring `Environment`.
- **Nội dung tệp** trở thành value của property.
- Sau khi import, ứng dụng có thể truy cập secret qua `Environment`, `@Value`, `@ConfigurationProperties` hoặc auto-configuration thường dùng.
- Việc import **không tự cấp quyền** đọc secret, không tạo secret, không mã hóa dữ liệu và không tự hot-reload bean khi secret thay đổi.

Ví dụ container có:

```text
/run/secrets/
└── db.password      # một tệp chứa mật khẩu, không phải tên thư mục
```

Khai báo:

```properties
spring.config.import=configtree:/run/secrets/
```

sẽ làm property `db.password` có mặt trong `Environment` với value lấy từ nội dung tệp `/run/secrets/db.password`. Tên `db.password` có dấu chấm hợp lệ: Spring Boot có thể ánh xạ nguyên tên tệp có dấu chấm vào đường dẫn configuration property.

Đây là cơ chế do **Spring Boot Config Data** cung cấp; bản thân Docker/Kubernetes chỉ chịu trách nhiệm đặt tệp vào volume và quản lý quyền truy cập của workload.

## 2. Configuration tree là gì?

Một số nền tảng lưu cấu hình theo định dạng *một file lớn*:

```yaml
db:
  username: user_demo
  password: example-only
```

Những nền tảng khác lưu theo mô hình *mỗi key thành một file*:

```text
/etc/config/
└── db/
    ├── username   (nội dung: user_demo)
    └── password   (nội dung: một giá trị bí mật)
```

Spring Boot hỗ trợ cả hai cách, nhưng cú pháp import khác nhau:

| Dạng đầu vào | Lệnh import phù hợp |
| --- | --- |
| Một file YAML | `spring.config.import=file:/etc/config/application.yaml` |
| Một file không có đuôi nhưng có nội dung YAML | `spring.config.import=file:/etc/config/settings[.yaml]` |
| Thư mục có nhiều file key/value | `spring.config.import=configtree:/etc/config/` |

**Không dùng `file:/etc/config/` để thay cho `configtree:/etc/config/`.** Prefix `file:` dành cho file cấu hình theo định dạng được nhận biết; prefix `configtree:` dành cho cây file mà tên file chính là key.

### 2.1. Cấu trúc thư mục quyết định property name

Giả sử container thấy:

```text
/etc/config/
└── myapp/
    ├── username
    └── password
```

Với:

```properties
spring.config.import=configtree:/etc/config/
```

thì các key được tạo là:

```text
myapp.username
myapp.password
```

Nếu muốn key chỉ là `username` và `password`, import **thư mục con**:

```properties
spring.config.import=configtree:/etc/config/myapp/
```

Lúc này đường dẫn tương đối dưới điểm import được dùng làm tên property. Thư mục gốc chỉ xác định **phần đường dẫn nào tham gia vào tên key**, không phải một tên property bí mật khác.

### 2.2. Tên file có dấu chấm

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Với:

```properties
spring.config.import=configtree:/run/secrets/
```

ứng dụng có thể nhận hai property:

```text
spring.datasource.username
spring.datasource.password
```

Điều này đặc biệt hữu ích khi muốn **tích hợp trực tiếp với Spring Boot auto-configuration** mà không phải thêm Java code để đọc file hoặc tự nối chuỗi. Nếu ứng dụng sử dụng Spring JDBC/DataSource và có cấu hình JDBC đầy đủ, tên property tương ứng có thể được Binder đưa vào `DataSourceProperties`.

### 2.3. String và byte[] đều có thể là value

Tài liệu Spring Boot 3.3 nêu configuration tree value có thể được bind thành **`String`** hoặc **`byte[]`** tùy kiểu dữ liệu ứng dụng cần.

- `String` thích hợp cho username, password và token dạng văn bản.
- `byte[]` thích hợp khi ứng dụng muốn giữ nguyên dữ liệu nhị phân hoặc kiểm soát chính xác byte của một khóa/chứng chỉ.

Đừng tự giả định mọi secret là UTF-8 text sạch hoặc không có ký tự xuống dòng. Định dạng do bên tạo secret quyết định; khi một API yêu cầu chuỗi, hãy xác định chính sách encoding/newline của **chính ứng dụng** và tạo file đầu vào đúng cách.

## 3. Hai cách viết spring.config.import

### application.properties

```properties
spring.config.import=optional:configtree:/run/secrets/
```

### application.yaml

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Dấu nháy trong YAML giúp thể hiện toàn bộ chuỗi import rõ ràng.

Prefix có ý nghĩa:

- `spring.config.import`: chỉ định Config Data cần nhập thêm.
- `configtree:`: đọc **tên file → property key**, **nội dung file → property value**.
- `/run/secrets/`: đường dẫn nhìn từ **container chạy JVM**, không phải đường dẫn tuyệt đối trên máy developer.
- `optional:`: cho phép bỏ qua **location không tồn tại** thay vì luôn làm startup thất bại vì thiếu location.

Nếu secret bắt buộc để chạy production, không nên dùng `optional:` như giải pháp mặc định. Cấu hình không có optional sẽ giúp phát hiện sớm **thiếu cả thư mục import**. Nhưng ngay cả thư mục tồn tại, một file key cụ thể vẫn có thể bị thiếu: cần validation hoặc kiểm tra bắt buộc ở tầng property sử dụng.

### Khi nào dùng optional?

| Tình huống | Gợi ý |
| --- | --- |
| Development không có secret volume | `optional:configtree:/run/secrets/` có thể thuận tiện |
| Production bắt buộc mount chính xác | `configtree:/run/secrets/`, kết hợp kiểm tra key bắt buộc |
| Một số credential chỉ cần theo profile | Import trong tài liệu profile phù hợp hoặc cấu hình theo môi trường |
| Triển khai nhiều môi trường với đường dẫn khác nhau | Dùng location/volume mount đã quy ước; kiểm soát source precedence |
| Muốn bỏ lỗi secret bị sai nội dung | **Không** dùng optional để che lỗi value hoặc permission |

`optional:` chỉ điều chỉnh cách xử lý **location không tìm thấy**; nó không có nghĩa “nếu file không đọc được hoặc dữ liệu sai thì Spring tự lấy giá trị hợp lệ khác”.

## 4. Ví dụ Docker secrets đơn giản nhất

Giả sử container chạy Spring Boot có file:

```text
/run/secrets/db.password
```

Nội dung file là mật khẩu thật, không chứa cú pháp `db.password=...`. Bạn chỉ cần:

```properties
# application.properties trong ứng dụng
spring.config.import=configtree:/run/secrets/
```

Rồi đọc:

```java
String password = environment.getProperty("db.password");
```

hoặc:

```java
@Value("${db.password}")
private String password;
```

Điều quan trọng là **Spring Boot không đi tìm mật khẩu bằng tên service Docker hay object Docker Secret**. Nó đọc **tệp mà container thực sự nhìn thấy**. Tệp nào được mount, path gì và user chạy ứng dụng có đọc được không là trách nhiệm của cấu hình Docker.

### 4.1. Docker Swarm secret

Trong một demo Swarm đã khởi tạo, có thể tạo secret từ file chứa dữ liệu minh họa:

```bash
# Chỉ dùng file demo này cho môi trường thử nghiệm; đừng commit.
docker secret create db.password ./local-secrets/db.password
```

Khi cấp secret có tên `db.password` cho một Docker Swarm service, secret thường được mount trong container tại:

```text
/run/secrets/db.password
```

Ví dụ cấp secret:

```bash
docker service create \
  --name catalog \
  --secret db.password \
  your-registry/catalog:1.0
```

Nếu image chứa ứng dụng Spring Boot đã khai báo `spring.config.import=configtree:/run/secrets/`, lúc khởi động nó sẽ đọc property `db.password` từ file mount.

**Điều kiện:** service có quyền sử dụng secret, container chạy với filesystem/mount đúng, tệp có thể đọc bởi user của JVM, và ứng dụng thật sự khởi động từ image tương ứng. Chỉ tạo Docker Secret mà **không attach vào service** sẽ không làm file xuất hiện trong mọi container.

### 4.2. Đặt tên secret phù hợp property

Docker Secret tên:

```text
spring.datasource.password
```

có thể được mount thành file cùng tên trong `/run/secrets/`. Với import đúng, property sẽ là `spring.datasource.password`, trực tiếp phù hợp auto-configuration. Đây là một cách tránh Java adapter code.

Nếu tổ chức yêu cầu tên secret ở Docker khác tên property, có thể dùng cơ chế target filename/alias mà nền tảng triển khai hỗ trợ để mount thành tên file Spring Boot cần. Đừng đổi tên source object rồi suy luận path mount cũng đổi nếu chưa kiểm tra.

### 4.3. Không dùng docker secret inspect để lấy plaintext

Docker Secret hướng tới việc cấp nội dung cho workload có quyền, không phải để truy vấn plaintext tùy ý qua metadata API. Đừng viết automation mong `docker secret inspect` sẽ trả giá trị secret. Kiểm tra ở phía container **theo cách không hiển thị nội dung**: file có tồn tại không, có đúng tên và quyền đọc không.

## 5. Docker Compose: ví dụ chạy local có file-backed secret

Với Docker Compose, có thể khai báo secret lấy từ file host:

```yaml
# compose.yaml -- ví dụ dành cho môi trường local/demo
services:
  catalog:
    image: your-registry/catalog:1.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - db.password

secrets:
  db.password:
    file: ./local-secrets/db.password
```

Ứng dụng nhận `SPRING_CONFIG_IMPORT` như property `spring.config.import`. Với file-backed Compose secret, nội dung `./local-secrets/db.password` được triển khai vào container dưới dạng file secret tương ứng.

**Các điểm cần nhớ:**

1. `./local-secrets/db.password` nằm **trên máy chạy Compose**, còn `/run/secrets/db.password` nằm **trong container**.
2. Docker Compose chạy local và Docker Swarm secrets **không có bảo đảm quản lý/lưu trữ giống nhau trong mọi chế độ triển khai**. Trong local Compose, secret có thể dựa trên file host/bind mount theo implementation.
3. File nguồn trên host cần quyền truy cập thích hợp và phải nằm ngoài Git/artifact public.
4. Không dùng một `environment: DB_PASSWORD: ...` chỉ để truyền ngược plaintext vào biến môi trường nếu mục tiêu là giới hạn điểm xuất hiện của secret.
5. Cần xác minh image thực sự chạy lệnh Java và `SPRING_CONFIG_IMPORT` được đưa vào đúng container service.
6. Nếu ứng dụng cũng có `spring.config.import` trong file, phải hiểu cách các nguồn cấu hình góp phần vào giá trị import. Đừng vô tình cấu hình hai import location mâu thuẫn.

### 5.1. Tạo file demo an toàn hơn echo

Ví dụ tạo **giá trị giả** và tránh ký tự xuống dòng ngoài ý muốn:

```bash
mkdir -p local-secrets
printf '%s' 'example-only-not-a-real-password' \
  > local-secrets/db.password
```

Lưu ý: đây chỉ là ví dụ học tập. Khi tạo secret thật, không đưa plaintext lên command line/log/history, không commit file chứa secret, và tuân theo hệ thống cấp phát secret được tổ chức cho phép.

Với nhiều shell, `echo` thường thêm newline; nếu mật khẩu thực tế không chứa newline, ký tự phụ đó có thể làm xác thực thất bại. Không mặc định mọi thư viện sẽ luôn trim secret theo cùng một cách.

### 5.2. Đọc nhiều Docker secrets

```yaml
services:
  catalog:
    image: your-registry/catalog:1.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - spring.datasource.username
      - spring.datasource.password
      - client.api-token

secrets:
  spring.datasource.username:
    file: ./local-secrets/db-user
  spring.datasource.password:
    file: ./local-secrets/db-password
  client.api-token:
    file: ./local-secrets/client-token
```

Nếu các file được mount tại tên khai báo, Spring Boot đọc:

```text
spring.datasource.username
spring.datasource.password
client.api-token
```

Các tên này nằm trong `Environment`; ứng dụng có thể bind chúng vào auto-configuration hoặc `@ConfigurationProperties` riêng.

## 6. Kubernetes Secrets dưới dạng volume

Kubernetes cung cấp `Secret` để lưu dữ liệu nhạy cảm có thể được workload sử dụng. Secret có thể được đưa vào Pod bằng environment variables hoặc volume. Đối với Spring Boot `configtree:`, cách phù hợp là **volume mount**.

Giả sử Kubernetes Secret tên `catalog-db-credentials` có hai keys:

```text
username
password
```

Ta muốn bên trong container có:

```text
/etc/secrets/db/
├── spring.datasource.username
└── spring.datasource.password
```

Cách làm là ánh xạ các key của Kubernetes Secret thành những **đường dẫn file** mà Spring Boot cần.

### 6.1. Tạo Secret cho demo từ file

Ví dụ minh họa trong môi trường test, với hai file đã được tạo an toàn và không lưu trong Git:

```bash
kubectl create secret generic catalog-db-credentials \
  --from-file=username=./local-secrets/db-user \
  --from-file=password=./local-secrets/db-password \
  -n demo
```

Tùy policy của tổ chức, Secret có thể được tạo bằng External Secrets Operator, CSI driver, GitOps với mã hóa ở nguồn hoặc hệ thống secret-management khác. Lệnh trên chỉ cho thấy quan hệ **Kubernetes key ↔ nội dung file**; nó không phải khuyến nghị lưu credential thật dưới dạng plaintext trong repo.

Không chia sẻ kết quả của lệnh `kubectl get secret ... -o yaml` công khai: dữ liệu dưới `data` thường là **base64 encoding, không phải mã hóa bảo mật**. Cần áp dụng encryption at rest, RBAC và các biện pháp quản trị secret phù hợp của cluster.

### 6.2. Mount vào Pod với items.path

Ví dụ phần Deployment đầy đủ tối thiểu:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: your-registry/catalog:1.0
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/secrets/db/"
          volumeMounts:
            - name: db-credentials
              mountPath: /etc/secrets/db
              readOnly: true
      volumes:
        - name: db-credentials
          secret:
            secretName: catalog-db-credentials
            optional: false
            items:
              - key: username
                path: spring.datasource.username
              - key: password
                path: spring.datasource.password
```

Kubernetes sẽ cung cấp những file tương ứng trong volume:

```text
/etc/secrets/db/spring.datasource.username
/etc/secrets/db/spring.datasource.password
```

Spring Boot import:

```properties
spring.config.import=configtree:/etc/secrets/db/
```

thông qua biến môi trường `SPRING_CONFIG_IMPORT` trong ví dụ Deployment. Kết quả có các property `spring.datasource.username` và `spring.datasource.password`.

**Không phải khai báo cả biến môi trường và file** nếu bạn chỉ muốn một vị trí cấu hình import: hãy chọn chỗ quản lý nhất quán. Trong ví dụ Kubernetes này, env var quy định *đường dẫn* nhập Config Data, không chứa plaintext credential.

### 6.3. Key của Secret và tên file không nhất thiết giống nhau

Phần:

```yaml
items:
  - key: password
    path: spring.datasource.password
```

có nghĩa:

- `password` là **key trong Kubernetes Secret object**.
- `spring.datasource.password` là **tên file bên trong volume mount**.
- `configtree:` đọc **tên file**, chứ không đọc tên object Secret trên Kubernetes API.
- Spring Boot nhận property `spring.datasource.password` do file path.

Nhờ đó bạn có thể dùng một convention cho Kubernetes Secret key, một convention khác cho Java/Spring property names mà không cần sửa nội dung secret.

### 6.4. Volume path là path của container

Ví dụ mount:

```yaml
mountPath: /etc/secrets/db
```

đòi hỏi import:

```properties
spring.config.import=configtree:/etc/secrets/db/
```

Nếu dùng nhầm đường dẫn của node/host hoặc import ở cấp trên như `/etc/secrets/`, key có thể bị thêm prefix `db.`:

```text
Import /etc/secrets/     -> db.spring.datasource.password
Import /etc/secrets/db/  -> spring.datasource.password
```

Đây là một trong những lỗi thường gặp nhất: file có mặt nhưng tên property hiệu lực không đúng.

## 7. Kubernetes: mount nguyên key thành file thay vì items

Một cách khác là đặt luôn Kubernetes Secret key trùng tên property Spring Boot. Ví dụ Secret được tạo từ một file đặt tên `spring.datasource.password`, rồi mount nguyên Secret vào thư mục:

```yaml
volumes:
  - name: db-credentials
    secret:
      secretName: catalog-db-credentials
```

Nếu Secret chứa key `spring.datasource.password`, Kubernetes mount file:

```text
/etc/secrets/db/spring.datasource.password
```

khi Pod có:

```yaml
volumeMounts:
  - name: db-credentials
    mountPath: /etc/secrets/db
    readOnly: true
```

Trường hợp Secret dùng key ngắn `password`, bạn có hai lựa chọn:

1. Giữ file tên `password` và import root để nhận `password`.
2. Dùng `items[].path` để đổi tên thành `spring.datasource.password` trước khi Spring Boot đọc.

Đừng xem dấu chấm trong tên file như “đuôi file phải được parse thành properties”: `configtree:` coi tên file là property key, không yêu cầu file chứa cấu trúc `key=value`.

## 8. Dùng @ConfigurationProperties để nhận secret

Khi không muốn gắn secret trực tiếp vào property `spring.datasource.password`, tạo prefix ứng dụng, ví dụ:

```text
/etc/secrets/app/
└── gateway/
    ├── username
    └── password
```

Import:

```properties
spring.config.import=configtree:/etc/secrets/app/
```

sẽ cho:

```text
gateway.username
gateway.password
```

Java record:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayCredentials(
        String username,
        String password) {
}
```

Đăng ký:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Một Spring-managed service có thể nhận cấu hình qua constructor:

```java
package com.example.demo.service;

import com.example.demo.config.GatewayCredentials;
import org.springframework.stereotype.Service;

@Service
public class GatewayClientFactory {

    private final GatewayCredentials credentials;

    public GatewayClientFactory(GatewayCredentials credentials) {
        this.credentials = credentials;
    }

    public void initializeClient() {
        // Truyền credentials.username()/password() vào
        // thư viện client mà ứng dụng sử dụng.
        // Không log hoặc trả secret ra HTTP response.
    }
}
```

`@ConfigurationProperties` binding vẫn có relaxed binding theo các quy tắc của Spring Boot. Việc giá trị đến từ configtree không làm mất khả năng bind theo prefix, nhưng thiết kế model phải phù hợp với tên file/đường dẫn đã mount.

### 8.1. Cần validation cho secret bắt buộc

Nếu credential phải có nội dung, dùng Jakarta Bean Validation:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayCredentials(
        @NotBlank String username,
        @NotBlank String password) {
}
```

Nếu không có giá trị hoặc chỉ có chuỗi rỗng/trắng, validation có thể từ chối startup khi dự án có Bean Validation provider phù hợp (thường là `spring-boot-starter-validation`).

Một validation như `@NotBlank` chỉ yêu cầu có nội dung, **không thể bảo đảm secret đúng, chưa hết hạn hoặc đã có quyền truy cập hệ thống đích**. Các lỗi xác thực vẫn cần được xử lý tại client/service.

### 8.2. Không expose secret qua record.toString()

Java record sinh `toString()` theo các components. Nếu record chứa password, gọi `logger.info("{}", credentials)` có thể làm lộ giá trị. **Không log nguyên object credentials**, không dùng debug serializer tùy tiện hoặc include secret trong exception message. Có thể dùng class thiết kế riêng không cung cấp `toString` chứa secret, hoặc che dữ liệu khi buộc phải hiển thị.

### 8.3. String vs byte[] cho key nhị phân

Khi mount một khóa nhị phân không phải text, đừng bind nó vào String rồi suy đoán encoding:

```java
@ConfigurationProperties(prefix = "crypto")
public record CryptoProperties(byte[] keyMaterial) {
}
```

File tương ứng:

```text
/etc/secrets/app/crypto/key-material
```

Configtree có thể cung cấp dữ liệu dạng byte cho binder khi target cần `byte[]`. Lưu ý byte array vẫn nằm trong bộ nhớ ứng dụng; đây **không phải một cơ chế bảo vệ bộ nhớ** hoặc xóa key material tự động. Không in Base64/hex của key ra log.

## 9. Tích hợp với Spring DataSource auto-configuration

Một ứng dụng dùng Spring Boot JDBC thường có cấu hình không nhạy cảm ở file:

```properties
# src/main/resources/application.properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/catalog
spring.datasource.driver-class-name=org.postgresql.Driver
spring.config.import=configtree:/run/secrets/
```

Secret volume:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Sau Config Data import, Spring có thể thấy:

```text
spring.datasource.url             <- application.properties
spring.datasource.driver-class-name <- application.properties
spring.datasource.username        <- configtree
spring.datasource.password        <- configtree
```

Nếu project có Spring JDBC/DataSource auto-configuration cùng JDBC driver thích hợp, các property này có thể được dùng theo quy tắc `spring.datasource.*` chuẩn. **Configtree không tự tạo JDBC driver, không bảo đảm server DB đang chạy và không cấp quyền mạng.**

Điểm mạnh là **mật khẩu không cần nằm trong JAR, source code hoặc application.properties**. Mã Java thông thường không cần viết:

```java
Files.readString(Path.of("/run/secrets/..."));
```

chỉ để chuyển mật khẩu vào auto-configuration.

### 9.1. Phương án dùng key trung gian và placeholder

Nếu secret file có tên `db.password` nhưng muốn dùng cho Spring datasource:

```properties
spring.config.import=configtree:/run/secrets/
spring.datasource.password=${db.password}
```

Đường đọc:

```text
/run/secrets/db.password
   -> Environment db.password
   -> placeholder ${db.password}
   -> spring.datasource.password
   -> DataSourceProperties
```

Cách này được dùng khi tên secret theo naming convention riêng nhưng đích là property framework. Cần xử lý thiếu `db.password` một cách rõ ràng; placeholder không có default có thể gây lỗi khi chưa resolve, hoặc khiến cấu hình không hoạt động theo ý định.

Một chiến lược khác là mount file thành tên `spring.datasource.password` và import trực tiếp, giảm số tầng alias.

### 9.2. Precedence khi trùng key

Giả sử file có:

```properties
spring.datasource.password=example-insecure-default
spring.config.import=configtree:/run/secrets/
```

Config Data được import sẽ có **ưu tiên cao hơn document khai báo import**. Vì vậy nếu configtree cung cấp `spring.datasource.password`, giá trị từ secret có thể ghi đè value trong file.

Tuy nhiên, nhiều nguồn có ưu tiên khác vẫn có thể override, ví dụ một command-line option `--spring.datasource.password=...` hoặc OS environment phù hợp. **Đừng để mật khẩu giả trong file cấu hình production** chỉ vì nghĩ configtree luôn thắng mọi nguồn.

Để tránh conflict, nên chỉ cung cấp password thật ở một nguồn secret đáng tin cậy và xác định quy tắc precedence ngay từ đầu.

## 10. Một secret object không tự map thành một file YAML

Kubernetes Secret có thể được volume mount theo nhiều cách. Phân biệt:

**A. Nhiều files:**

```text
/etc/config/
├── db.username
└── db.password
```

Dùng:

```properties
spring.config.import=configtree:/etc/config/
```

**B. Một file chứa YAML hoàn chỉnh:**

```text
/etc/config/app-credentials.yaml
```

Nội dung minh họa:

```yaml
db:
  username: demo
  password: example-only
```

Dùng:

```properties
spring.config.import=file:/etc/config/app-credentials.yaml
```

Nếu file không có phần mở rộng nhưng **nội dung là YAML**, có thể dùng extension hint:

```properties
spring.config.import=file:/etc/config/app-credentials[.yaml]
```

Không dùng `configtree:` cho trường hợp B rồi mong Boot parse YAML nằm **bên trong** một file: configuration tree coi **cả file đó là value của một property** có tên theo file path.

### Extension hint không thay thế configtree

`file:/etc/config/app-credentials[.yaml]` là cú pháp khác với `configtree:/etc/config/`. Dấu `[.yaml]` chỉ định kiểu format **của file import**, không phải cấu trúc cây secret. Khi Secret volume mount một file cho mỗi key, không cần thêm `[.properties]` cho từng file key-value.

## 11. Nhiều configuration tree trong cùng triển khai

Đôi khi một workload có nhiều nguồn secret:

```text
/etc/config/
├── dbconfig/
│   └── db/
│       ├── username
│       └── password
└── mqconfig/
    └── mq/
        ├── username
        └── password
```

Có thể import:

```properties
spring.config.import=optional:configtree:/etc/config/*/
```

Cú pháp wildcard `/*/` giúp import **các thư mục con trực tiếp** của `/etc/config/` như những config trees độc lập. Các key có thể là:

```text
db.username
db.password
mq.username
mq.password
```

Khi import wildcard, Spring Boot 3.3 sắp xếp những directory được nạp **theo thứ tự alphabet của absolute path**. Nếu có key trùng và bạn muốn kiểm soát override một cách cụ thể, hãy liệt kê các import locations tường minh.

### 11.1. Import nhiều locations tường minh

```properties
spring.config.import=\
  configtree:/etc/config/dbconfig/,\
  configtree:/etc/config/mqconfig/
```

Trong `application.yaml` có thể dùng danh sách:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/dbconfig/"
      - "configtree:/etc/config/mqconfig/"
```

Các import được xử lý theo thứ tự cấu hình; theo quy tắc Config Data, import về sau có thể có ưu tiên hơn import trước nếu cùng key. Do đó tránh trùng key hoặc tài liệu hóa thứ tự override rõ ràng.

### 11.2. Đặt namespace để tránh trùng

Với nhiều secret như `username`/`password`, tốt hơn là có:

```text
db.username
db.password
mq.username
mq.password
```

thay vì mount nhiều cây đều cung cấp key chung `password`. Đặt thư mục và file sao cho thành property namespace có ý nghĩa, rồi bind bằng `@ConfigurationProperties(prefix="db")`, `@ConfigurationProperties(prefix="mq")`.

## 12. optional:, startup failures và fail-fast

Các tình huống:

| Hiện tượng | Cách hiểu | Cách xử lý |
| --- | --- | --- |
| Không có directory, import không optional | Startup có thể lỗi `ConfigDataLocationNotFoundException` | Sửa volume/mountPath hoặc tạo location |
| Không có directory, import optional | Có thể bỏ qua import | Hợp lý cho local nếu credential không bắt buộc |
| Directory có, thiếu file password | Location có thể nạp nhưng property cần thiết không tồn tại | Validate/kiểm tra key bắt buộc |
| File có, không đọc được | Lỗi file permission/I/O, không đơn thuần location missing | Kiểm tra UID/GID, mount mode, policy |
| File rỗng | Value có thể là chuỗi rỗng | Chặn bằng validation hoặc logic |
| File chứa newline ngoài ý muốn | Giá trị thực có thể khác chuỗi cần thiết | Tạo secret file đúng encoding, định dạng |
| File tên sai | Property name không đúng | Sửa `items.path`, Docker secret target hoặc import root |
| Docker/Kubernetes Secret object tồn tại nhưng Pod không mount | Spring không thấy file | Kiểm tra volumes/volumeMounts/service secret grant |
| Configtree nạp nhưng auto-config không dùng value | Tên key không trùng property/framework cần | Dùng canonical property name hoặc placeholder |
| File đã thay đổi sau startup | Object đã bind không tự nạp lại | Thiết kế rollout/restart hoặc refresh riêng |

**Bảo mật và fail-fast:** Với credential bắt buộc, việc làm startup thất bại có thể tốt hơn nhiều so với chạy bằng password mặc định, rỗng hoặc cấu hình kết nối sai. `optional:` có ích về tính di động nhưng phải được sử dụng có chủ đích.

### Thêm validation cho key bắt buộc

Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "db")
public record DbCredentials(
        @NotBlank String username,
        @NotBlank String password) {
}
```

Dùng Bean Validation provider tương thích và đăng ký configuration properties để kiểm tra ở startup. Nếu phần còn lại của app không dùng `DbCredentials`, đừng đăng ký chỉ để tạo một bean thừa mà không có mục đích; chọn nơi thực sự sở hữu contract cấu hình và validation.

## 13. Quyền truy cập file và nguyên tắc ít quyền nhất

Secret volume chỉ hữu ích nếu workload đọc được đúng giá trị nhưng những workload khác không có quyền không thể tùy ý đọc.

### 13.1. Những thành phần cần phân biệt

- **Docker/Kubernetes secret object:** nơi nền tảng quản lý dữ liệu và quyền cấp secret.
- **Volume mount trong container:** nơi dữ liệu được hiển thị dưới dạng file.
- **Process user (UID/GID):** danh tính tiến trình Java khi mở file.
- **Filesystem permissions:** mode, owner, group và policy của volume.
- **Cluster/container authorization:** RBAC, pod security, Docker service grant.
- **Application memory:** nơi secret đã được Binder đọc vào sau startup.

`configtree:` không tự nâng quyền filesystem. Nếu container chạy non-root nhưng file chỉ readable với root, ứng dụng có thể không đọc được. Nếu nới quyền `chmod 777` chỉ để khởi động, bạn đã làm yếu ranh giới bảo mật; cần giải quyết đúng ở cấu hình mount, runAsUser/runAsGroup/fsGroup và policy của nền tảng.

### 13.2. Kubernetes: readOnly và quyền của Secret volume

```yaml
volumeMounts:
  - name: db-credentials
    mountPath: /etc/secrets/db
    readOnly: true
```

`readOnly: true` là cách biểu diễn rõ rằng ứng dụng **chỉ được đọc**, không ghi ngược secret. Với Secret volume, Kubernetes cung cấp dữ liệu theo cơ chế volume riêng; quản trị viên cũng có thể điều chỉnh permission mode theo yêu cầu của pod và driver.

Không đề xuất một `defaultMode` tùy ý mà chưa xét user/group thực tế, bởi đặt quá chặt có thể khiến process không đọc được, đặt quá rộng có thể làm tăng phạm vi lộ secret.

### 13.3. Không đưa secret vào image

Không dùng:

```dockerfile
COPY local-secrets/db.password /run/secrets/db.password
```

cho secret thật, vì file có thể lưu trong image layer/registry. Với Docker/Kubernetes, đúng mục tiêu là **cấp secret khi container chạy**, không bake nó vào image.

Tương tự, đừng đưa secret vào `ARG`, `ENV` Dockerfile hoặc output log của CI nếu không cần. Việc sử dụng `configtree:` ở runtime nhằm tránh nhiều đường rò rỉ này.

### 13.4. Secret có thể xuất hiện trong bộ nhớ

Khi Boot đã bind `spring.datasource.password` hoặc `GatewayCredentials.password` thành String, plaintext sẽ có trong bộ nhớ của process. Cơ chế configtree giảm việc quản lý secret qua text cấu hình và environment variables, nhưng **không làm secret biến mất sau khi bind**. Đừng khẳng định file mount là giải pháp mã hóa end-to-end.

## 14. Kubernetes: Secret thay đổi có tự được ứng dụng nhận không?

Không nên coi hai chuyện sau là tương đương:

1. **Kubernetes cập nhật nội dung secret volume** theo cơ chế của kubelet.
2. **Spring Boot nạp lại Config Data và bind lại beans**.

Với Secret mounted as volume, Kubernetes có cơ chế cập nhật file sau một khoảng trễ nhất định trong trường hợp mount thông thường. Nhưng **Spring Boot 3.3 không tự reload tất cả Config Data và refresh mọi `@ConfigurationProperties` bean chỉ vì file thay đổi**. Các bean, connection pools và client được tạo từ credential cũ có thể tiếp tục sử dụng giá trị đó.

**Ngoại lệ của Kubernetes:** nếu mount Secret file bằng `subPath`, những bản cập nhật Secret thông thường **không được phản ánh** vào container theo cơ chế volume update. Cần cân nhắc điều này khi thiết kế rotation.

### 14.1. Phương án rotation thực tế

Một quy trình vận hành điển hình:

1. Cấp secret mới bằng hệ thống quản trị secret.
2. Cập nhật Kubernetes Secret hoặc nguồn secret được mount.
3. Tạo rollout/restart Pods một cách có kiểm soát để ứng dụng khởi động và bind lại Config Data.
4. Kiểm tra khả năng kết nối với credential mới.
5. Thu hồi credential cũ sau khoảng chuyển tiếp thích hợp.
6. Giám sát error rate, connection pool và quyền truy cập.

Có thể thiết kế reload riêng bằng Spring Cloud/CSI integration hay custom file watcher, nhưng cần quản lý atomic read, validation, update client connection và retry. **Đừng mặc định Kubernetes volume projection + configtree = live refresh**.

### 14.2. Docker secrets và thay đổi mật khẩu

Docker Swarm secrets thường được quản lý dưới dạng immutable secret objects theo cơ chế version/rotation của nền tảng. Muốn thay credential, quy trình có thể cần tạo secret mới, cập nhật service và thay task/container. Đừng giả định sửa file host là đủ để cập nhật mọi Swarm secret đã attach.

Docker Compose local dùng file-backed secrets có cơ chế triển khai khác, vì vậy cần kiểm tra lại mount/content sau khi thay file và thường khởi động lại service khi muốn ứng dụng đọc giá trị mới.

## 15. Vấn đề newline, whitespace và encoding

Có trường hợp file có:

```text
my-password<newline>
```

nhưng password thực chỉ là:

```text
my-password
```

Một số công cụ tạo tệp bằng `echo` sẽ thêm newline. Mỗi library/driver có thể xử lý hoặc không xử lý whitespace khác nhau; không nên dựa vào việc Boot hoặc client tự trim một cách tùy ý.

**Khuyến nghị triển khai:**

- Chọn encoding, thường UTF-8 cho text secret.
- Nếu giá trị không cần newline cuối, tạo source file không có newline.
- Không in file để debug; so sánh độ dài hoặc checksum chỉ khi đã cân nhắc nguy cơ lộ thông tin và kiểm soát log.
- Với khóa nhị phân/certificate, chọn target byte[] hoặc thư viện đọc trực tiếp file khi cần giữ nguyên byte.
- Kiểm tra chính sách của hệ thống cấp phát secret: một số secret có trailing newline hợp lệ, một số là JSON/PEM có newline nhiều dòng.
- Đừng áp dụng `trim()` tự động cho mọi secret; nó có thể làm thay đổi một giá trị mà nguồn cấp phát cố ý chứa khoảng trắng.

### Một tệp chứa `key=value` không giống tệp chứa value

Đúng cho `configtree:`:

```text
/run/secrets/db.password
  nội dung file: example-password
```

Không phải:

```text
/run/secrets/db.password
  nội dung file: db.password=example-password
```

Trường hợp thứ hai làm property `db.password` có **value là cả chuỗi `db.password=example-password`**, vì configuration tree không parse nội dung từng file theo định dạng properties.

## 16. Đưa nhiều bí mật vào một Secret volume: cách đặt tên

Ví dụ một ứng dụng tích hợp hai hệ thống:

```text
/etc/secrets/
└── app/
    ├── db/
    │   ├── username
    │   └── password
    └── payment/
        └── api-token
```

Import:

```properties
spring.config.import=configtree:/etc/secrets/app/
```

Kết quả:

```text
db.username
db.password
payment.api-token
```

Ta có thể bind:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentCredentials(String apiToken) {
}
```

Tương ứng `payment.api-token`. Tuy nhiên, Kubernetes native Secret keys không thể tùy ý chứa dấu `/`; muốn tạo cấu trúc thư mục lồng nhau cần sử dụng `items.path` phù hợp trong volume projection, hoặc kết hợp nhiều volumes theo một layout rõ ràng.

Trong Kubernetes, một Pod cũng có thể mount nhiều Secret volumes tại các mount paths riêng; khi đó dùng nhiều locations hoặc wildcard `configtree:` nếu phù hợp.

### Lợi ích của namespace

- Tránh hai secret khác hệ thống cùng ghi key `password`.
- Cho phép phân quyền theo workload và chức năng.
- Dễ di chuyển từ secret object này sang object khác mà giữ property name.
- Hạn chế lỗi do import root khác nhau.
- Dễ mô tả và validate từng nhóm property.

Đừng dùng một thư mục chung chứa toàn bộ credential của cluster rồi mount mọi thứ vào mọi Pod. Nguyên tắc ít quyền nhất khuyến nghị chỉ cấp cho workload những secret thực sự cần thiết.

## 17. Tên property có dấu chấm và relaxed binding

Tài liệu Spring Boot xác nhận filename `myapp.username` được ánh xạ đúng thành property `myapp.username`. Do đó, hai layout có thể tạo cùng tên property:

**Layout A: thư mục lồng nhau**

```text
/etc/config/myapp/username
```

Import:

```properties
spring.config.import=configtree:/etc/config/
```

**Layout B: filename có dấu chấm**

```text
/etc/config/myapp.username
```

Import:

```properties
spring.config.import=configtree:/etc/config/
```

Cả hai có thể tạo `myapp.username`. Chọn một convention trong cùng hệ thống; tránh đồng thời cung cấp hai file trùng property name rồi kỳ vọng precedence trong cùng một configtree sẽ luôn rõ ràng cho người vận hành.

### Canonical tên property

Đối với `@ConfigurationProperties`, nên dùng tên lowercase kebab-case khi có từ ghép:

```text
service.auth.client-secret
```

Có thể mount file `service.auth.client-secret` hoặc tạo cấu trúc thư mục `service/auth/client-secret` dưới root import. Binder ánh xạ `client-secret` sang Java property `clientSecret` theo relaxed binding.

Nhưng đừng suy luận rằng các ký tự tùy ý như slash trong key sẽ luôn được bảo toàn qua mọi nguồn. Nếu cần key Map phức tạp, thiết kế naming convention và kiểm tra đường dẫn; tránh dùng tên file chứa ký tự không phù hợp filesystem/volume.

## 18. Đặt spring.config.import ở đâu?

Có nhiều cách cung cấp vị trí import:

### A. Trong application.properties đóng gói

```properties
spring.config.import=optional:configtree:/run/secrets/
```

Phù hợp khi ứng dụng luôn hiểu một đường dẫn cố định, nhưng local development có thể không mount secret. Nếu production bắt buộc, cần validation hoặc một cấu hình profile-specific thay vì tin optional là đủ.

### B. Trong application-prod.yaml

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Được nạp khi tài liệu/profile production phù hợp; cần hiểu cơ chế active profile và Config Data. Không đặt những property có quy tắc chỉ được phép trong non-profile-specific documents vào vùng profile không hợp lệ, nhưng `spring.config.import` có thể được khai báo theo các quy tắc Config Data import và kích hoạt document phù hợp.

### C. Qua biến môi trường container

```yaml
env:
  - name: SPRING_CONFIG_IMPORT
    value: "configtree:/etc/secrets/db/"
```

Ở đây env var **không chứa password**; nó chỉ định secret volume path. Đây là cách tiện khi cùng một image được triển khai tại những môi trường khác nhau với mount path khác nhau.

### D. Qua command-line argument

```bash
java -jar app.jar \
  --spring.config.import=configtree:/run/secrets/
```

Cũng chỉ cung cấp path. Với property startup, nguồn cần có từ giai đoạn Spring Boot nạp Config Data; đường dẫn phải tồn tại trong environment/container khi JVM bắt đầu.

**Không dùng một `ApplicationRunner` để thiết lập `spring.config.import` rồi mong Boot quay lại nạp secret mới:** Config Data đã được xử lý trước đó.

## 19. Chẩn đoán khi secret file đã mount nhưng ứng dụng không nhận

Thứ tự kiểm tra:

1. **Vùng mount:** file có thực sự tồn tại trong container được chạy không?
2. **Đúng Pod/service:** Secret đã được gán cho workload đó hay chỉ tồn tại trong cluster/Swarm?
3. **Đường dẫn:** `spring.config.import` có trỏ đúng path bên trong container, và kết thúc bằng `/` cho directory không?
4. **Root import:** file nằm ở ngay root hay trong thư mục con, làm property có prefix khác?
5. **Filename:** khớp chính xác property key cần đọc hay cần alias?
6. **Quyền đọc:** user chạy JVM có thể đọc file, không bị security context hoặc mount permissions chặn?
7. **Dữ liệu file:** file chứa **value**, không phải một dòng `key=value` ngoài ý định?
8. **Nguồn có ưu tiên cao hơn:** env var, CLI hoặc Config Data khác có override cùng property?
9. **Thiếu key bắt buộc:** directory có thể tồn tại dù file secret quan trọng bị thiếu.
10. **Encoding/newline:** secret string có thể chứa ký tự ngoài ý muốn.
11. **Thời điểm:** import phải có hiệu lực trong Config Data startup, không phải được set muộn.
12. **Cấu hình ứng dụng:** `@ConfigurationProperties` bean có được đăng ký, field/record có tên phù hợp và validation hoạt động không?
13. **Rotation:** Pod đã restart chưa; bean/connection pool có dùng secret mới chưa?
14. **Đã đặt optional đúng mục đích chưa:** optional có thể bỏ qua location bị thiếu, làm lỗi xuất hiện muộn ở client.
15. **Có giới hạn platform?** Secret volume với `subPath` không tự nhận cập nhật như mount thông thường.

### Chỉ kiểm tra sự tồn tại của file

Trong container Linux, đối với file **không nhạy cảm về tên**, một lệnh kiểm tra khái niệm là:

```bash
test -r /run/secrets/db.password && echo readable
```

Lệnh này không in plaintext. Nhưng với chính sách nghiêm ngặt, ngay cả tên path cũng có thể cung cấp thông tin vận hành; chỉ chạy trong môi trường được ủy quyền và không dùng `cat` hoặc `printenv` để dump secret.

Kubernetes có thể dùng `kubectl describe pod` hoặc `kubectl get pod -o yaml` để kiểm tra cấu hình volume/mount mà không cần truy xuất secret value. Tuy nhiên, các lệnh này có thể hiển thị metadata nhạy cảm về hạ tầng, nên vẫn cần phân quyền và cách chia sẻ phù hợp.

### Vì sao không dùng env để debug mật khẩu?

Nếu import từ configtree, password **không bắt buộc trở thành OS environment variable**. Gõ `printenv` rồi không thấy `DB_PASSWORD` không chứng minh Spring chưa đọc secret. Đọc đúng tên property qua Spring `Environment` có thể cho thấy nguồn đã import, nhưng **không được log giá trị raw**. Dùng kiểm tra presence hoặc xác nhận downstream authentication trong môi trường an toàn.

## 20. Chẩn đoán từ Spring Environment mà không tiết lộ giá trị

Có thể kiểm tra key có giá trị có thể giải quyết được mà **không in plaintext**:

```java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class SecretPresenceDiagnostics {

    @Bean
    ApplicationRunner checkSecrets(Environment env) {
        return args -> {
            boolean usernamePresent =
                    env.containsProperty("spring.datasource.username");
            boolean passwordPresent =
                    env.containsProperty("spring.datasource.password");

            System.out.println("DB username configured: "
                    + usernamePresent);
            System.out.println("DB password configured: "
                    + passwordPresent);
        };
    }
}
```

**Những giới hạn của phép kiểm tra này:**

- `containsProperty` không chứng minh giá trị đến từ **configtree**; có thể là file, env var hoặc CLI.
- Giá trị có mặt có thể là chuỗi rỗng; presence không bảo đảm secret có nội dung.
- Một secret có mặt nhưng sai/expired vẫn có thể khiến kết nối thất bại.
- `ApplicationRunner` chỉ chạy sau khi context khởi tạo; nếu Config Data import làm startup thất bại, chẩn đoán bằng log startup thay vì Runner.

Nếu cần xác định nguồn property trong quá trình điều tra, chỉ dùng công cụ có quyền và tránh in raw values. Actuator endpoints `/actuator/env` và `/actuator/configprops` có thể chứa metadata về cấu hình và phải được bảo vệ, sanitization rõ ràng; không expose public để debug.

## 21. Kiểm thử configtree không cần Docker/Kubernetes thật

Để kiểm tra ứng dụng có đọc đúng **layout tên file → property name**, có thể tạo thư mục fixture trong test resources hoặc thư mục tạm, rồi khởi động một context/test app với import location trỏ tới đó.

Ví dụ thư mục fixture minh họa:

```text
src/test/resources/secret-fixture/
├── gateway.username
└── gateway.password
```

Giá trị các file là **dữ liệu giả dành cho test**, không phải credential production.

Trong một integration test dùng `@SpringBootTest`, có thể cung cấp property import tường minh:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest(properties = {
    "spring.config.import=optional:configtree:classpath:/secret-fixture/"
})
class ConfigTreeFixtureTest {

    @Autowired
    Environment env;

    @Test
    void readsSecretKeyFromTree() {
        assertThat(env.getProperty("gateway.username"))
                .isEqualTo("demo-user");
    }
}
```

**Chú ý về bootstrap trong test:** `spring.config.import` được xử lý rất sớm theo pipeline Config Data, nên test properties được thêm muộn trong một context không nhất thiết tái hiện đúng mọi quyết định import. Để integration test đáng tin cậy, đặt import trong file `application-test.properties` hoặc cung cấp nó như một **early Environment property** cho tiến trình Spring Boot test, và dùng một **filesystem path** nếu cách nạp configtree yêu cầu một thư mục thật. Không suy luận từ ví dụ test annotation trên rằng mọi test runner đều load configtree classpath như một filesystem directory.

Một cách ổn định hơn để kiểm tra đúng hành vi production là tạo **temporary directory trên filesystem**, ghi file dummy `gateway.username` và `gateway.password`, rồi khởi động ứng dụng/test với `spring.config.import=configtree:/duong-dan-thu-muc/` được cung cấp từ đầu. Kiểm tra cả tên key, giá trị, quyền đọc và property precedence. Không chép secret thật vào test fixture.

### 21.1. Test với @ConfigurationProperties

Khi import đã có hiệu lực trong `Environment`:

```java
assertThat(credentials.username()).isEqualTo("demo-user");
assertThat(credentials.password()).isEqualTo("example-only");
```

Nếu cần test parse nội dung nhị phân, dùng target `byte[]` và so sánh byte trong unit test cục bộ; tránh in chúng trong assertion message khi dữ liệu có thể nhạy cảm.

### 21.2. Những điều không thể kết luận từ unit test thuần

Test với `MapPropertySource` có thể xác minh binding nhưng **không** chứng minh Docker/Kubernetes mount đã đúng path, permission, Secret items hoặc startup import. Với bài toán này, nên có tối thiểu một smoke test trong container có dummy secret volume.

## 22. Chọn configtree hay biến môi trường?

| Tiêu chí | Configtree (volume file) | OS environment variable |
| --- | --- | --- |
| Cơ chế cấp dữ liệu | File được mount ở container | Value được đưa vào environment của process |
| Phù hợp Docker Swarm/K8s Secret volume | Rất phù hợp | Có thể dùng nguồn khác |
| Spring Boot truy cập | `spring.config.import=configtree:...` | Environment PropertySource mặc định |
| Biểu diễn binary secret | Có thể dùng file/byte[] | Khó và thường cần encode |
| Lộ trong process environment | Không bắt buộc | Value có mặt trong environment |
| Root/path ảnh hưởng property name | Có | Tên biến ảnh hưởng property name |
| Nhu cầu IAM/RBAC/quyền mount | Có | Có, tùy hạ tầng |
| Tự refresh Spring bean | Không | Không |
| Secret rotation | Cần chiến lược rollout/refresh | Thường cần restart để process nhận env mới |
| Khả năng vô tình log | Vẫn có nếu app log value | Vẫn có nếu dump env |

**Không khẳng định file mount luôn an toàn tuyệt đối hơn biến môi trường**. Mức bảo vệ phụ thuộc hạ tầng quản lý secret, quyền file, namespace/isolation, process, logging và cơ chế phát hành. Configtree là một phương án tích hợp rất tiện cho secret volume; nó **không thay thế secret governance**.

## 23. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Import nhầm path host

```properties
spring.config.import=configtree:/home/developer/secrets/
```

Nhưng container chỉ thấy `/run/secrets/`. Sửa thành path **trong container** và cấu hình volume tương ứng.

### Lỗi 2 — Thiếu prefix configtree:

```properties
spring.config.import=file:/run/secrets/
```

Một directory chứa nhiều file key/value phải dùng:

```properties
spring.config.import=configtree:/run/secrets/
```

### Lỗi 3 — File có tên password nhưng code đọc db.password

```text
/etc/secrets/db/password
```

Import `/etc/secrets/db/` cho key `password`; import `/etc/secrets/` cho key `db.password`. Chọn root tương ứng với code.

### Lỗi 4 — Kubernetes Secret đã có nhưng chưa mount

Có object `Secret` trong namespace không làm nó tự hiển thị trong mọi Pod. Thêm `volumes.secret.secretName` và `volumeMounts` tương ứng.

### Lỗi 5 — Secret key khác file path mong đợi

Kubernetes key `password` được mount nguyên tên, nhưng Spring cần `spring.datasource.password`. Dùng `items[].path` hoặc placeholder mapping.

### Lỗi 6 — Dùng optional trong production rồi không phát hiện thiếu mount

`optional:configtree:...` có thể bỏ qua thư mục không tồn tại. Khi secret bắt buộc, dùng non-optional và validation cho key cụ thể.

### Lỗi 7 — Tên file là `db.password.properties`

Configtree không tự bóc đuôi `.properties` theo ý định “tệp chứa property `db.password`”; nó coi tên file là key tương ứng. Nếu muốn `db.password`, đặt tên file đúng `db.password` hoặc đổi cách import file dựa trên format.

### Lỗi 8 — Cho nội dung `db.password=...` vào file `db.password`

Cả chuỗi `db.password=...` trở thành **value**, vì configtree không parse từng file như một properties document.

### Lỗi 9 — Secret file chỉ root đọc được, app chạy non-root

Giải quyết quyền và security context của volume, không bỏ security bằng cách chạy tất cả container root hoặc mở quyền toàn bộ filesystem.

### Lỗi 10 — Thay Secret nhưng Spring vẫn dùng mật khẩu cũ

Cần kế hoạch restart/rollout hoặc refresh đúng nghĩa. File volume có thể thay, nhưng object `@ConfigurationProperties` và DataSource không tự cập nhật.

### Lỗi 11 — Mount Secret bằng subPath và kỳ vọng auto-update

Kubernetes `subPath` có giới hạn cập nhật với Secret volume; tránh khi kỳ vọng projection file mới xuất hiện mà không restart.

### Lỗi 12 — Dùng ConfigMap để lưu mật khẩu vì cùng đọc được bằng configtree

`ConfigMap` dành cho cấu hình không nhạy cảm; muốn quản lý credential, dùng `Secret` hoặc giải pháp quản lý bí mật được tổ chức phê duyệt. `configtree:` đọc được cả hai dạng file mount nhưng **không tự làm ConfigMap thành bí mật**.

### Lỗi 13 — Log toàn bộ Environment để chứng minh đã nạp

Không log plaintext. Chỉ kiểm tra presence, key không nhạy cảm và kết quả xác thực downstream trong môi trường kiểm soát.

### Lỗi 14 — Secret được base64-encode hai lần

Kubernetes `data` nhận byte biểu diễn base64, còn `stringData` cho phép truyền plaintext để API server chuyển thành dữ liệu Secret; file volume khi mount chứa **bytes đã được giải mã**, không phải text base64 trong trường hợp thông thường. Không tự base64-decode thêm ở Spring nếu nguồn đã đưa đúng bytes, trừ khi ứng dụng cố ý lưu một lớp encoding riêng.

### Lỗi 15 — Chỉ nhìn default của @Value và không kiểm tra file

`@Value("${db.password:}")` có default rỗng có thể khiến ứng dụng chạy với password rỗng khi secret thiếu. Với credential production, ưu tiên fail-fast và validation thay vì fallback âm thầm.

## 24. Quy trình triển khai production đề xuất

1. **Thiết kế property names** trước: ví dụ `spring.datasource.username`/`spring.datasource.password` hoặc `gateway.username`/`gateway.password`.
2. **Tách dữ liệu bí mật khỏi image và source control**; cấp secret qua Docker Swarm/Kubernetes hoặc hệ thống secret-management được phê duyệt.
3. **Quy ước mount path** của container: ví dụ `/run/secrets/`, `/etc/secrets/db/`.
4. **Định nghĩa file names hoặc items.path** khớp property name; nếu cần namespace, dùng thư mục con và xác định root import.
5. **Khai báo `spring.config.import=configtree:...`** ở nguồn startup phù hợp. Dùng `optional:` chỉ khi thiếu volume là tình huống được chấp nhận.
6. **Giới hạn quyền cấp secret** tới đúng workload, namespace và user/group cần đọc.
7. **Cấu hình validation** cho secret bắt buộc, tránh default rỗng trong production.
8. **Kiểm tra property source precedence** để không bị CLI/env/config khác ghi đè ngoài ý muốn.
9. **Kiểm thử trong container với dummy secrets**, gồm path, filename, newline/encoding và non-root user.
10. **Bảo vệ logging, Actuator, diagnostics** và không đưa secret value vào error response.
11. **Thiết kế rotation**: thay secret, restart/rollout/refresh có kiểm soát, theo dõi kết nối và thu hồi credential cũ.
12. **Ghi rõ ownership và quy trình vận hành**: ai cấp secret, đổi secret, kiểm tra quyền, xử lý thiếu mount và ứng phó sự cố.

### Bảng kiểm trước release

- [ ] Secret không nằm trong Git, artifact, Dockerfile hoặc image layer.
- [ ] Container có volume mount đúng path.
- [ ] Tên file khớp canonical property name mà ứng dụng cần.
- [ ] `spring.config.import` có mặt từ giai đoạn Config Data.
- [ ] Có quy tắc rõ cho `optional:` và key bắt buộc.
- [ ] UID/GID của JVM đọc được file mà không cần quyền thừa.
- [ ] Secret value không bị thêm newline/encoding không mong muốn.
- [ ] Không có nguồn config ưu tiên cao hơn chứa credential cũ.
- [ ] `@ConfigurationProperties`/auto-configuration sử dụng đúng key.
- [ ] Validation xử lý secret thiếu/rỗng.
- [ ] Không log password/token/đối tượng chứa credential.
- [ ] Actuator `env` và `configprops` được bảo vệ và masking thích hợp.
- [ ] Kịch bản rotate/revoke secret đã được thử.
- [ ] K8s `subPath` không bị dùng sai cho kịch bản cập nhật volume.
- [ ] Smoke test với dummy secrets xác nhận startup/kết nối.

## 25. Tài liệu tham khảo chính thức

- **Spring Boot 3.3 Reference — Externalized Configuration / Using Configuration Trees / Docker secrets**, cú pháp `spring.config.import=configtree:...`, nhiều file tạo key/value, wildcard `/*/`, String/byte[]: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 Reference — Importing Additional Data**, semantics `optional:`, import precedence và extensionless files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Kubernetes Documentation — Distribute Credentials Securely Using Secrets**, tạo Secret và đưa vào Pod: https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/
- **Kubernetes Documentation — Secrets**, Secret volume, projected updates, `subPath` limitations và security considerations: https://kubernetes.io/docs/concepts/configuration/secret/
- **Docker Docs — Manage sensitive data with Docker secrets**, Docker Swarm secret mounts và lifecycle: https://docs.docker.com/engine/swarm/secrets/
- **Docker Compose Docs — Secrets**, file-backed secrets và mount vào service: https://docs.docker.com/compose/how-tos/use-secrets/

## 26. Ghi nhớ cuối bài

Với Spring Boot 3.3, đọc secret bằng configtree có thể nhớ qua công thức:

```text
Docker/Kubernetes Secret
    -> volume mount trong container
    -> file name/path tương đối tạo property key
    -> nội dung file tạo property value
    -> spring.config.import=configtree:/mount-root/
    -> Environment / @ConfigurationProperties / auto-configuration
```

Một ví dụ ngắn nhất:

```text
File trong container: /run/secrets/spring.datasource.password
Import:               spring.config.import=configtree:/run/secrets/
Property tạo ra:      spring.datasource.password
```

**Configtree là cầu nối giữa filesystem secret volume và Spring Environment**, không phải trình quản lý secret. Muốn triển khai an toàn cần đúng mount path, đúng tên property, quyền đọc tối thiểu, validation khi thiếu/rỗng, tránh log secret và có kế hoạch restart/rotation rõ ràng.
