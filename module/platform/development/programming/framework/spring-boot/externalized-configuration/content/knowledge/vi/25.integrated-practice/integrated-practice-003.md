# Thiết kế cấu hình chung cùng profile local, test và prod trong Spring Boot

## 1. Mục tiêu của bài thực hành tổng hợp

Trong quá trình phát triển một ứng dụng Spring Boot, ta thường cần chạy **cùng một codebase** trong nhiều bối cảnh:

- **local**: lập trình viên chạy trên máy cá nhân, ưu tiên tốc độ phản hồi, địa chỉ giả lập và khả năng quan sát.
- **test**: bộ kiểm thử chạy trên CI hoặc trong IDE, cần tính tái lập, cô lập khỏi dịch vụ thật và không lệ thuộc cấu hình máy.
- **prod**: triển khai thực tế, ưu tiên an toàn, cấu hình được cấp bởi hệ thống triển khai, bảo vệ bí mật và hoạt động ổn định.

Ba bối cảnh này khác nhau về dữ liệu đầu vào, nhưng không nên dẫn đến ba bộ mã nguồn riêng biệt hoặc ba ứng dụng Spring Boot riêng biệt.

Một thiết kế cấu hình tốt phải trả lời:

1. Thuộc tính nào **giống nhau** ở mọi môi trường?
2. Thuộc tính nào được phép **thay đổi theo profile**?
3. Thuộc tính nào phải được **cấp từ bên ngoài**, không xuất hiện dưới dạng secret thật trong repository?
4. Cách nào đảm bảo test không vô tình kết nối tới hệ thống production?
5. Làm sao biết profile nào đang hoạt động và giá trị nào đang thắng?
6. Làm sao kiểm tra các giá trị đã được Binder chuyển thành object Java?
7. Làm sao bổ sung môi trường mới mà không copy-paste hàng trăm dòng YAML?
8. Khi một giá trị sai, nên sửa file chung, file profile hay cấu hình triển khai?

Bài này xây một dự án giả lập **Order Dispatch Configuration Lab**. Ứng dụng có một nhóm cấu hình chung cho khả năng gửi đơn hàng ra hệ thống bên ngoài, xử lý batch và thông tin vận hành. Để tập trung vào Externalized Configuration, service ví dụ chỉ tạo một kế hoạch xử lý, **không thực sự gửi HTTP**.

Kết quả mong muốn:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-prod.yml

src/test/resources/
  application-test.yml

Java code:
  @ConfigurationProperties(prefix = "app")
  AppSettings
  DispatchPlanService

Runtime:
  local -> app settings địa phương
  test  -> app settings cô lập
  prod  -> app settings production + ENV/secret
```

**Nguyên tắc:** một bản build, nhiều cấu hình triển khai. Giá trị dùng chung được định nghĩa một nơi; file theo profile chỉ khai những khác biệt có chủ đích.

## 2. Spring profile là gì?

Spring profile là một tên đại diện cho một nhóm điều kiện hoạt động trong `Environment`.

Ví dụ:

```text
local
test
prod
```

Khi profile `local` đang active, Spring Boot xem xét các nguồn cấu hình dành cho `local` và những bean được điều kiện hóa bằng profile đó. Tương tự với `test` và `prod`.

Một profile có hai tác dụng thường gặp nhưng khác nhau:

**A. Chọn Config Data theo profile**

```text
application.yml
application-local.yml
application-test.yml
application-prod.yml
```

Khi profile `prod` active, Boot có thể nạp `application.yml` cùng `application-prod.yml` từ những location được cấu hình.

**B. Chọn bean theo điều kiện profile**

```java
@Profile("local")
@Bean
OutboundGateway localGateway() { ... }
```

`@Profile` điều khiển việc đăng ký bean; file `application-local.yml` cung cấp giá trị. Chúng thường đi cùng nhau nhưng **không phải cùng một cơ chế**.

Trong một ứng dụng, có thể chọn profile mà không có file tương ứng, hoặc có file profile nhưng không có bean nào khai `@Profile`.

### 2.1. Profile mặc định

Nếu không có active profile, Spring Boot dùng profile mặc định theo cơ chế của Spring. Tên mặc định thông thường là `default`. Có thể cấu hình `spring.profiles.default` ở tài liệu cấu hình **không dành riêng cho profile** nếu thực sự cần.

Không nên coi `local` là profile luôn tự bật chỉ vì có `application-local.yml`. File tồn tại không đồng nghĩa được chọn.

### 2.2. “Môi trường” không nhất thiết trùng profile

Một tổ chức có thể có nhiều cluster production, mỗi cluster có vùng, namespace và secret khác nhau, nhưng đều sử dụng profile `prod`.

```text
prod + region=ap-southeast
prod + region=eu-west
prod + region=us-east
```

Profile trả lời nhóm **đặc điểm hành vi/cấu hình**, còn biến môi trường hoặc Config Data bên ngoài có thể cung cấp những **giá trị cụ thể của deployment**.

Tránh tạo hàng trăm profile theo từng hostname, tài khoản hay khách hàng nếu một nhóm profile ổn định cộng với cấu hình bên ngoài đã đủ.

## 3. Quy tắc thiết kế: common + overrides

Một cấu trúc dễ bảo trì:

```text
application.yml
  Giá trị không phụ thuộc môi trường
  Defaults an toàn
  Những thiết lập nền tảng chung

application-local.yml
  Chỉ khác biệt cho máy dev
  Fake URL / logging cục bộ
  Batch nhỏ, timeout ngắn
  Không bật kết nối ngoài không kiểm soát

application-test.yml
  Dành cho test classpath
  Đầu vào xác định và ổn định
  Không dùng credential thật
  Đảm bảo test không gọi hệ thống ngoài

application-prod.yml
  Khác biệt vận hành production
  Chế độ an toàn và thông số bảo thủ
  Tham chiếu tới biến môi trường/secret
  Không hard-code token thật
```

Ví dụ file chung có:

```yaml
app:
  batch:
    size: 40
    flush-interval: 5s
```

File `application-local.yml` chỉ đổi:

```yaml
app:
  batch:
    size: 10
```

Khi `local` hoạt động và không có nguồn cao hơn, `size=10`, còn `flushInterval=5s` từ file chung.

Đối với những thuộc tính scalar và nested object đơn giản, cách thiết kế này hạn chế trùng lặp. Tuy nhiên với **List**, Spring Boot có quy tắc thay thế danh sách giữa các nguồn, không phải lúc nào cũng merge từng phần tử. Với **Map**, các entry có thể được gộp/ghi đè theo khóa. Không áp dụng máy móc quy tắc “chỉ thêm một phần tử List” như một phép nối danh sách.

## 4. Bản thiết kế cấu hình của dự án lab

Ta đặt prefix riêng cho ứng dụng là `app`, tách ra khỏi các property chuẩn của Spring Boot như `server.*` và `management.*`.

Các nhóm:

| Property | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `app.display-name` | `String` | Nhãn hiển thị |
| `app.region` | `String` | Vùng triển khai logic |
| `app.outbound.enabled` | `boolean` | Có bật tích hợp gửi đi không |
| `app.outbound.endpoint` | `URI` | Đích của tích hợp |
| `app.outbound.connect-timeout` | `Duration` | Thời gian mở kết nối |
| `app.outbound.max-attempts` | `int` | Tổng số lần thử, gồm lần đầu |
| `app.outbound.auth-token` | `String` | Credential nhạy cảm, nếu có |
| `app.batch.size` | `int` | Số phần tử tối đa mỗi batch |
| `app.batch.flush-interval` | `Duration` | Khoảng thời gian giữa lần flush |
| `app.diagnostics.verbose` | `boolean` | Bật thông tin chẩn đoán an toàn |

Cấu hình này có ba loại dữ liệu:

1. **Giá trị chung:** tên ứng dụng, định nghĩa logic cấu hình, defaults tương đối an toàn.
2. **Giá trị theo môi trường:** endpoint, timeout, batch size, logging.
3. **Bí mật theo deployment:** token, API key, password; không đưa giá trị thật vào Git.

Thiết kế cũng đặt câu hỏi về trách nhiệm của field `authToken`. Không được log toàn bộ đối tượng properties nếu record chứa trường này vì `record.toString()` có thể làm lộ token. Trong ví dụ, bean service sẽ chỉ trả về các field **không nhạy cảm**.

## 5. Cấu trúc thư mục chi tiết

Một dự án Maven/Gradle phổ biến:

```text
order-config-lab/
├── build.gradle                 # hoặc pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/
│   │   │       ├── OrdersApplication.java
│   │   │       ├── AppSettings.java
│   │   │       └── DispatchPlanService.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       └── application-prod.yml
│   └── test/
│       ├── java/
│       │   └── com/example/orders/
│       │       ├── CommonConfigTest.java
│       │       ├── LocalProfileTest.java
│       │       ├── TestProfileTest.java
│       │       └── ProdProfileTest.java
│       └── resources/
│           └── application-test.yml
└── README.md
```

Có chủ đích đặt `application-test.yml` vào `src/test/resources`:

- Test runner nạp file này trên **test classpath**.
- Khi đóng gói ứng dụng thông thường, `src/test/resources` không thuộc bộ resource runtime chính.
- Cấu hình test giảm nguy cơ đi theo artifact production.
- Các bài test dùng `@ActiveProfiles("test")` để kích hoạt profile này.

Nếu một dự án thực sự phải chạy JAR với profile `test` bên ngoài bộ test, có thể cung cấp file test theo cách deployment riêng. Không nên thay đổi quy tắc đóng gói chỉ để phục vụ một kịch bản không có nhu cầu thật.

## 6. Chuẩn bị dependencies

Ví dụ Spring Boot 3.x, Java 17+, JUnit Jupiter. Các nguyên tắc Config Data/profile ở đây cũng áp dụng cho nhiều bản Spring Boot mới hơn, nhưng khi dùng Boot 4 cần đối chiếu package import ở một số phần test/Actuator.

### 6.1. Maven

Một dependency set tối thiểu:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu cần HTTP server thực sự, thêm `spring-boot-starter-web`. Nếu cần Actuator chẩn đoán, thêm `spring-boot-starter-actuator` và cấu hình exposure/security phù hợp. Bài lab có thể chạy như console application, không cần mở port.

### 6.2. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 6.3. Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Giả định project dùng Spring Boot plugin, parent/BOM hoặc dependency-management để chọn version tương thích. Không tự pha trộn các version của Spring Framework và Spring Boot nếu không có lý do và kiểm chứng.

## 7. Viết application.yml: defaults dùng chung

File `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: order-config-lab

app:
  display-name: Order Configuration Lab
  region: global

  outbound:
    enabled: false
    endpoint: https://sandbox.example.invalid/api
    connect-timeout: 2s
    max-attempts: 3

  batch:
    size: 40
    flush-interval: 5s

  diagnostics:
    verbose: false

logging:
  level:
    root: INFO
    com.example.orders: INFO
```

Phân tích:

- `spring.application.name` là property chuẩn của Spring Boot.
- `app.*` là namespace do ứng dụng tự định nghĩa.
- `outbound.enabled=false` giúp tránh việc bật tích hợp ngoài khi chưa chọn môi trường thích hợp.
- `endpoint` dùng domain `.invalid` chỉ làm dữ liệu giả.
- `connect-timeout=2s` và `flush-interval=5s` dùng đơn vị rõ ràng.
- Không khai `app.outbound.auth-token` trong file chung, vì token là bí mật tùy deployment.
- Logging mặc định dùng mức vừa đủ; không bật DEBUG cho toàn bộ framework.
- Không khai `spring.profiles.active=local` ở file chung, để deployment chủ động chọn profile và test không vô tình kế thừa local.

Một default chung không có nghĩa nó hợp lý trong mọi môi trường nếu property được **bật**. Ví dụ `sandbox.example.invalid` không thể là endpoint production thật; file prod sẽ phải cung cấp endpoint phù hợp.

### 7.1. Khi nào nên đặt default trong Java thay vì YAML?

Có thể khai Java field initializer hoặc `@DefaultValue` cho constructor binding. Nhưng nếu vừa đặt default trong Java vừa khai default khác trong YAML, người bảo trì phải nhớ hai nơi.

Với một project mới, có thể thống nhất:

- Default runtime thường dùng: nằm ở `application.yml`.
- Giá trị bắt buộc hoặc có ngữ nghĩa đặc biệt: ràng buộc bằng validation.
- Default chỉ phục vụ object được bind ngoài context: dùng Java default khi thật sự có lý do.
- Tài liệu: ghi rõ default thuộc Java, YAML hay deployment.

Không cần “lặp để chắc ăn” khi sự lặp tạo các nguồn dễ mâu thuẫn.

## 8. Viết application-local.yml: thuận tiện nhưng có rào chắn

File `src/main/resources/application-local.yml`:

```yaml
app:
  region: local

  outbound:
    enabled: false
    endpoint: http://127.0.0.1:18080/mock
    connect-timeout: 500ms
    max-attempts: 1

  batch:
    size: 10

  diagnostics:
    verbose: true

logging:
  level:
    com.example.orders: DEBUG
```

Định hướng local:

1. **Không tự gọi dịch vụ production.** Endpoint trỏ loopback và `enabled=false`.
2. **Timeout ngắn** giúp phát hiện kết nối không sẵn sàng sớm.
3. **Batch nhỏ** giúp debug thao tác trên lượng dữ liệu nhỏ.
4. **Verbose logging có kiểm soát** dành cho module do ta viết.
5. **Không có token thật** trong file.
6. Chỉ ghi đè những khóa khác biệt; `display-name` và `batch.flush-interval` vẫn đến từ common.

Nếu ứng dụng có logic gọi mạng mà không kiểm tra `outbound.enabled`, việc đặt false **không tự ngăn network call**. Code phải được thiết kế thật sự tôn trọng cờ này hoặc dùng fake adapter. Cấu hình là dữ liệu; nó không thay thế kiến trúc cô lập.

### 8.1. Có nên mở Actuator env/configprops ở local?

Có thể cần cho học tập, nhưng ngay ở máy cá nhân cũng có nguy cơ lộ biến môi trường và secret. Nếu thật sự muốn:

- Chỉ expose trên loopback/mạng cô lập.
- Dùng giá trị giả.
- Đặt `management.endpoint.env.show-values=never` và `configprops.show-values=never`.
- Đóng endpoint sau khi dùng.
- Không đẩy nguyên response vào ticket/chat.

Bài này **không mặc định mở** env/configprops trong profile local để tránh tạo thói quen mở rộng bề mặt quản trị không cần thiết.

## 9. Viết application-test.yml: cấu hình cho kiểm thử tự động

File `src/test/resources/application-test.yml`:

```yaml
app:
  region: test

  outbound:
    enabled: false
    endpoint: http://127.0.0.1:1/unreachable
    connect-timeout: 100ms
    max-attempts: 1

  batch:
    size: 5
    flush-interval: 100ms

  diagnostics:
    verbose: false

logging:
  level:
    com.example.orders: WARN
```

Tại sao chọn địa chỉ `127.0.0.1:1`? Đây là một giá trị giả dùng để biểu diễn đích không được phép gọi trong bài test. **Không dựa riêng vào port 1 như một cơ chế bảo mật**; một test đúng không nên tạo request thật khi `enabled=false`, hoặc nên thay adapter bằng fake/mock.

Đặc điểm của test profile:

- Không cần credential production.
- Có cùng giá trị đầu vào mỗi lần chạy.
- Batch nhỏ và thời lượng ngắn.
- Có khả năng fail fast nếu một client vẫn cố gọi mạng trái ý định.
- Không ảnh hưởng deployment artifact thông thường.
- Được kích hoạt bằng Spring TestContext, điển hình là `@ActiveProfiles("test")`.

### 9.1. Test profile khác local profile

Local profile phục vụ người phát triển quan sát ứng dụng đang chạy, có thể cần DEBUG. Test profile phục vụ automation, ưu tiên output gọn, tính tái lập và không có side effect. Không nên cho test mặc định chạy local chỉ vì máy developer đang dùng local.

### 9.2. Test fixture không phải secret store

Nếu một bài test cần credential, sử dụng chuỗi giả không có quyền trên hệ thống thật, hoặc secret test được cấp qua CI theo cơ chế được kiểm soát. Không sao chép token production vào `src/test/resources` chỉ vì thư mục đó không đóng gói vào JAR.

## 10. Viết application-prod.yml: bật tích hợp có kiểm soát

File `src/main/resources/application-prod.yml`:

```yaml
app:
  region: ${DEPLOY_REGION:global}

  outbound:
    enabled: true
    endpoint: ${ORDER_OUTBOUND_ENDPOINT}
    auth-token: ${ORDER_OUTBOUND_TOKEN}
    connect-timeout: 3s
    max-attempts: 5

  batch:
    size: 200
    flush-interval: 2s

  diagnostics:
    verbose: false

logging:
  level:
    com.example.orders: INFO
```

Ở đây:

- `enabled=true` cho biết production dự kiến bật tích hợp.
- `endpoint` và `auth-token` lấy từ **nguồn bên ngoài** qua placeholder.
- `DEPLOY_REGION` có fallback `global` trong ví dụ; dự án thật có thể yêu cầu region bắt buộc.
- Token không nằm trong Git.
- Timeout/retry/batch size phản ánh mục tiêu vận hành riêng và cần được đo/điều chỉnh theo yêu cầu dịch vụ thật.
- Logging không được tự động in token hoặc object chứa token.

**Không dùng giá trị minh họa làm thông số production đã tối ưu.** Các số 3s/5/200/2s chỉ để thấy cơ chế override. Hệ thống thật phải xác định theo latency, SLA, tải và idempotency.

### 10.1. Placeholder không thay thế validation

Cấu hình:

```yaml
auth-token: ${ORDER_OUTBOUND_TOKEN}
```

diễn tả rằng ứng dụng cần nguồn bên ngoài. Nhưng không nên chỉ nhìn cú pháp rồi kết luận *mọi phiên bản, mọi kiểu binding sẽ luôn fail ngay* khi token thiếu. Cách xử lý placeholder chưa giải quyết còn phụ thuộc cơ chế resolution, kiểu đích và giai đoạn binding.

Với thông tin bắt buộc, cần thêm **runtime validation hoặc kiểm tra khởi động được test**. Không chấp nhận một chuỗi literal dạng `${ORDER_OUTBOUND_TOKEN}` trở thành credential có vẻ “không rỗng”.

### 10.2. Không cần file prod chứa mọi property

`app.display-name` không có trong file prod. Nó tiếp tục lấy từ common. Đây là thiết kế có chủ đích: file theo profile chỉ khai khác biệt, giúp giảm nguy cơ drift.

## 11. Bảng kết quả kỳ vọng theo từng profile

Trong điều kiện không có môi trường/CLI ghi đè thêm:

| Thuộc tính | Common | local | test | prod |
| --- | --- | --- | --- | --- |
| `app.display-name` | Order Configuration Lab | Giữ common | Giữ common | Giữ common |
| `app.region` | global | local | test | `DEPLOY_REGION` hoặc global |
| `outbound.enabled` | false | false | false | true |
| `outbound.endpoint` | sandbox URL | loopback mock | loopback unreachable | ENV `ORDER_OUTBOUND_ENDPOINT` |
| `outbound.connect-timeout` | 2s | 500ms | 100ms | 3s |
| `outbound.max-attempts` | 3 | 1 | 1 | 5 |
| `outbound.auth-token` | Không khai | Không khai | Không khai | ENV `ORDER_OUTBOUND_TOKEN` |
| `batch.size` | 40 | 10 | 5 | 200 |
| `batch.flush-interval` | 5s | 5s | 100ms | 2s |
| `diagnostics.verbose` | false | true | false | false |
| `logging.level.com.example.orders` | INFO | DEBUG | WARN | INFO |

Các ô “giữ common” có nghĩa property không bị nguồn profile đó ghi đè, **không có nghĩa không thể có nguồn ưu tiên cao hơn từ ENV/CLI/Config Data bên ngoài**.

Bảng mô tả kỳ vọng trong lab; muốn xác minh trên một tiến trình thật phải đọc `Environment` và bean sau binding.

## 12. Khởi động ứng dụng và chọn profile

### 12.1. Khởi động local bằng command line

Với một JAR đã build:

```bash
java -jar app.jar --spring.profiles.active=local
```

Hoặc với Gradle:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

Hoặc Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Trên Windows dùng wrapper `gradlew.bat`/`mvnw.cmd`. Cú pháp quote có thể cần điều chỉnh cho PowerShell so với Bash; với JAR, đối số `--spring.profiles.active=local` đơn giản và rõ ràng.

### 12.2. Khởi động qua biến môi trường

Trên Bash:

```bash
export SPRING_PROFILES_ACTIVE=local
java -jar app.jar
```

Trong PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar app.jar
```

Đây là hai cách **cấp profile từ bên ngoài** thay vì thay file `application.yml`.

### 12.3. Khởi động production

Ví dụ Bash dùng các giá trị giả để minh họa:

```bash
export SPRING_PROFILES_ACTIVE=prod
export DEPLOY_REGION=ap-southeast
export ORDER_OUTBOUND_ENDPOINT=https://orders.example.invalid/api

# ORDER_OUTBOUND_TOKEN phải được cấp bởi hệ thống secrets.
# Không dán giá trị thật vào tài liệu, shell script hoặc log.

java -jar app.jar
```

Nếu chạy ví dụ này để thực hành mà không có token giả, phần kiểm tra cấu hình production có thể không đạt. Đó là điều nên diễn ra khi ứng dụng yêu cầu một credential bắt buộc nhưng deployment chưa cung cấp.

Trong triển khai thực tế, một secret manager, CI/CD vault, Kubernetes Secret hoặc nền tảng tương đương nên cấp token. Không đặt token thật trong lệnh startup có thể bị lưu vào process listing hoặc shell history.

### 12.4. Không tự bật test profile cho JAR phát hành

Ở cấu trúc bài này, `application-test.yml` nằm trong test resources nên không được kỳ vọng tồn tại trong executable JAR thường dùng ở production. Kích hoạt `test` nên thực hiện qua test runner; muốn chạy ứng dụng với test profile theo cách khác phải cấp resource tương ứng có chủ đích.

## 13. Tạo record @ConfigurationProperties

File `src/main/java/com/example/orders/AppSettings.java`:

```java
package com.example.orders;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        @NotBlank String displayName,
        @NotBlank String region,
        @Valid @NotNull Outbound outbound,
        @Valid @NotNull Batch batch,
        @Valid @NotNull Diagnostics diagnostics
) {

    public record Outbound(
            boolean enabled,
            @NotNull URI endpoint,
            @NotNull Duration connectTimeout,
            @Min(1) int maxAttempts,
            String authToken
    ) {}

    public record Batch(
            @Min(1) int size,
            @NotNull Duration flushInterval
    ) {}

    public record Diagnostics(boolean verbose) {}
}
```

Những điểm quan trọng:

- Prefix `app` ánh xạ toàn bộ nhóm vào một object.
- `display-name` được bind vào `displayName`.
- `connect-timeout` và `flush-interval` được chuyển thành `Duration`.
- `endpoint` được chuyển thành `URI`.
- `@Validated` và Jakarta Validation annotations giúp kiểm tra những giá trị cơ bản nếu project có validation provider.
- `@Valid` giúp validation đi vào các object lồng nhau theo cơ chế Bean Validation.
- `authToken` được khai như `String` tùy chọn vì local/test không dùng token; production cần một guard riêng theo điều kiện `enabled`.
- **Không log `AppSettings` trực tiếp** vì record có thể chứa token trong `toString()`.

Ràng buộc `@Min(1)` bảo đảm số lần thử/batch size ít nhất 1, nhưng không tự bảo đảm timeout dương hoặc URL dùng HTTPS. Những quy tắc nghiệp vụ này cần validation riêng.

### 13.1. @NotNull không có nghĩa timeout dương

`@NotNull Duration connectTimeout` chỉ kiểm tra có object. `Duration.ZERO` hoặc giá trị âm vẫn là non-null. Nếu hợp đồng yêu cầu lớn hơn 0, thêm một validator thích hợp hoặc kiểm tra custom.

Tương tự `@NotNull URI endpoint` không bảo đảm URI có scheme `https`. Việc chuyển kiểu thành công không đồng nghĩa URL an toàn hoặc hợp lệ theo chính sách vận hành.

## 14. Đăng ký AppSettings trong Spring Boot

File `OrdersApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppSettings.class)
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

`@EnableConfigurationProperties` cho Binder biết cần tạo bean cho `AppSettings`. Đối với record có một constructor đúng kiểu, Spring Boot 3.x hỗ trợ constructor binding mà không cần thêm `@ConstructorBinding` vào ví dụ cơ bản.

Trong dự án lớn, `@ConfigurationPropertiesScan` cũng phù hợp nếu package scan được cấu hình chính xác.

### 14.1. Không thêm @Component lên record chỉ để dùng constructor binding

Không nên đặt `@Component` lên record configuration properties như một cách chữa lỗi registration nếu muốn để Binder tạo object bằng constructor binding. Component scanning thông thường và constructor binding của `@ConfigurationProperties` có các quy tắc đăng ký khác nhau.

Chọn một mô hình rõ ràng: `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` đối với nhóm cấu hình được bind như dữ liệu.

## 15. Viết service dùng properties nhưng không làm lộ secret

File `DispatchPlanService.java`:

```java
package com.example.orders;

import java.net.URI;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class DispatchPlanService {

    private final AppSettings settings;

    public DispatchPlanService(AppSettings settings) {
        this.settings = settings;
    }

    public DispatchPlan currentPlan() {
        return new DispatchPlan(
                settings.region(),
                settings.outbound().enabled(),
                settings.outbound().endpoint(),
                settings.outbound().connectTimeout(),
                settings.outbound().maxAttempts(),
                settings.batch().size(),
                settings.batch().flushInterval()
        );
    }

    public record DispatchPlan(
            String region,
            boolean outboundEnabled,
            URI outboundEndpoint,
            Duration connectTimeout,
            int maxAttempts,
            int batchSize,
            Duration flushInterval
    ) {}
}
```

Service **không** trả `authToken` trong `DispatchPlan`. Mục tiêu là có một đối tượng an toàn để kiểm tra profile đã bind đúng những trường không nhạy cảm.

Trong ứng dụng thật, nếu service dùng token để gửi request, phải thiết kế quản lý credential riêng và không cung cấp chúng qua `toString()`, log hoặc response công khai.

### 15.1. Cờ enabled phải có hiệu lực thật

Nếu triển khai một `OutboundGateway`, cần bảo đảm code chỉ tạo/gọi adapter thật khi `enabled=true`, và với local/test dùng fake adapter hoặc cơ chế tắt phù hợp.

Một câu lệnh:

```yaml
app:
  outbound:
    enabled: false
```

**không tự ngăn** một client bất kỳ đang mở socket ngay trong constructor. Nó chỉ trở thành rào chắn khi code sử dụng cờ đó đúng cách.

## 16. Thêm kiểm tra production bắt buộc mà không in token

Trong profile prod, `enabled=true` và token phải được cấp. Có thể định nghĩa một bean chuyên kiểm tra cấu hình sau khi binding nhưng trước khi ứng dụng nhận traffic, ví dụ dùng `SmartInitializingSingleton`:

```java
package com.example.orders;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class ProductionConfigGuard {

    @Bean
    @Profile("prod")
    SmartInitializingSingleton verifyProdSettings(
            AppSettings settings) {

        return () -> {
            AppSettings.Outbound outbound = settings.outbound();

            if (!outbound.enabled()) {
                throw new IllegalStateException(
                    "Production outbound must be enabled"
                );
            }

            if (!"https".equalsIgnoreCase(
                    outbound.endpoint().getScheme())) {
                throw new IllegalStateException(
                    "Production outbound endpoint must use HTTPS"
                );
            }

            String token = outbound.authToken();

            if (token == null
                    || token.isBlank()
                    || token.startsWith("${")) {
                throw new IllegalStateException(
                    "Production outbound token must be supplied"
                );
            }
        };
    }
}
```

Đây là một guard minh họa cho lab:

- Có `@Profile("prod")` để chỉ tạo trong profile prod.
- Không đưa token vào exception.
- Kiểm tra token không thiếu/rỗng và không còn là placeholder literal.
- Kiểm tra endpoint production có scheme HTTPS.
- Không kiểm tra token có quyền thật trên hệ thống ngoài, chỉ kiểm tra sự hiện diện/hình thức.
- Chạy trong quá trình khởi tạo singleton, không phải một test logic thời gian thực khi đã phục vụ yêu cầu.

**Lưu ý:** `SmartInitializingSingleton` chạy sau khi các singleton đã được tạo, nên nó không phải điểm đảm bảo “chặn mọi side effect trong constructor” trước đó. Nếu cần chính sách fail-fast trước khi bất kỳ client nào khởi tạo, đặt validation vào chính `@ConfigurationProperties` hoặc thiết kế lifecycle dependency phù hợp. Guard ở đây chỉ minh họa kiểm tra có điều kiện theo profile.

### 16.1. Không đưa secret vào error message

Sai:

```java
throw new IllegalStateException(
    "Invalid token: " + settings.outbound().authToken()
);
```

Đúng hơn:

```java
throw new IllegalStateException(
    "Production outbound token is missing or invalid"
);
```

Một exception có thể được in ra CI log, APM hoặc monitoring. Thông báo lỗi phải cho biết **khóa nào có vấn đề**, không đưa dữ liệu bí mật vào log.

## 17. Viết test cho profile test bằng @ActiveProfiles

File `src/test/java/com/example/orders/TestProfileTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class TestProfileTest {

    @Autowired
    AppSettings settings;

    @Autowired
    Environment environment;

    @Autowired
    DispatchPlanService planService;

    @Test
    void loadsTestConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(settings.region()).isEqualTo("test");
        assertThat(settings.outbound().enabled()).isFalse();
        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofMillis(100));
        assertThat(settings.outbound().maxAttempts())
                .isEqualTo(1);

        assertThat(settings.batch().size()).isEqualTo(5);
        assertThat(settings.batch().flushInterval())
                .isEqualTo(Duration.ofMillis(100));

        assertThat(planService.currentPlan().batchSize())
                .isEqualTo(5);
    }
}
```

Bài test chứng minh:

1. TestContext bật profile `test`.
2. File `application-test.yml` từ test classpath được xem xét.
3. Binder chuyển `100ms` thành `Duration.ofMillis(100)`.
4. Bean service thấy `batch.size=5`.
5. Không cần truyền token production hay gọi dịch vụ thật.

Không chạy test dưới một môi trường có biến toàn cục kỳ lạ mà không kiểm soát. Nếu CI cấp một property có ưu tiên cao hơn file test, giá trị thực tế có thể khác dự đoán; khi cần cố định, dùng `@SpringBootTest(properties=...)` hoặc test-specific nguồn phù hợp.

## 18. Test cho local profile

File `LocalProfileTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("local")
@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class LocalProfileTest {

    @Autowired
    AppSettings settings;

    @Test
    void loadsLocalOverridesAndKeepsCommonDefaults() {
        assertThat(settings.region()).isEqualTo("local");

        assertThat(settings.outbound().enabled()).isFalse();
        assertThat(settings.outbound().endpoint())
                .isEqualTo(
                    URI.create("http://127.0.0.1:18080/mock")
                );

        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofMillis(500));

        assertThat(settings.batch().size()).isEqualTo(10);

        // Không khai lại trong application-local.yml:
        assertThat(settings.batch().flushInterval())
                .isEqualTo(Duration.ofSeconds(5));

        assertThat(settings.displayName())
                .isEqualTo("Order Configuration Lab");

        assertThat(settings.diagnostics().verbose()).isTrue();
    }
}
```

Test này kiểm tra **cả override lẫn fallback về common**. Nếu chỉ kiểm tra các giá trị khác biệt, ta chưa chứng minh rằng phần chung đang được tái sử dụng đúng.

### 18.1. Vì sao không bật local theo mặc định cho mọi test?

Một test có `@ActiveProfiles("local")` có thể nạp fake URL và DEBUG logging dành riêng cho máy developer. Test suite tự động nên dùng `test` để tránh khác biệt giữa CI và laptop.

## 19. Test cho common khi không có active profile

File `CommonConfigTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CommonConfigTest {

    @Autowired
    AppSettings settings;

    @Test
    void usesCommonDefaultsWithoutActiveProfile() {
        assertThat(settings.region()).isEqualTo("global");

        assertThat(settings.outbound().enabled()).isFalse();

        assertThat(settings.outbound().connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));

        assertThat(settings.outbound().maxAttempts())
                .isEqualTo(3);

        assertThat(settings.batch().size()).isEqualTo(40);
    }
}
```

Điều kiện quan trọng: test không có active profile từ nguồn khác; nếu CI đặt `SPRING_PROFILES_ACTIVE=prod` cho mọi process, test có thể vô tình bật prod. Một thiết kế CI tốt nên **không cấp profile production cho JVM chạy test**.

Nếu muốn test thật sự cố định baseline, có thể đặt cấu hình test setup phù hợp, nhưng đừng vừa kỳ vọng “không profile” vừa vô tình bật profile qua môi trường bên ngoài.

## 20. Test cho prod nhưng không dùng secret thật

Để kiểm tra profile prod, cung cấp các giá trị **giả và hợp lệ** qua test override; không dùng token production.

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(
    classes = OrdersApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "ORDER_OUTBOUND_ENDPOINT=https://prod.example.invalid/api",
        "ORDER_OUTBOUND_TOKEN=FAKE_TEST_TOKEN",
        "DEPLOY_REGION=ap-southeast"
    }
)
class ProdProfileTest {

    @Autowired
    AppSettings settings;

    @Test
    void bindsProdSettingsFromTestSuppliedValues() {
        assertThat(settings.region()).isEqualTo("ap-southeast");

        assertThat(settings.outbound().enabled()).isTrue();

        assertThat(settings.outbound().endpoint()).isEqualTo(
            URI.create("https://prod.example.invalid/api")
        );

        assertThat(settings.outbound().connectTimeout())
            .isEqualTo(Duration.ofSeconds(3));

        assertThat(settings.outbound().maxAttempts())
            .isEqualTo(5);

        assertThat(settings.batch().size()).isEqualTo(200);

        // Không in hoặc so sánh raw token trong thông báo lỗi.
        assertThat(settings.outbound().authToken())
            .isNotBlank();
    }
}
```

Đoạn trên dùng test properties mang những **tên được placeholder tham chiếu**: `ORDER_OUTBOUND_ENDPOINT`, `ORDER_OUTBOUND_TOKEN`, `DEPLOY_REGION`. Chúng được giải quyết qua `Environment` của test, giúp profile prod nhận các giá trị giả mà không phụ thuộc secret thật ở CI. Với một số loại source/placeholder hoặc phiên bản thư viện khác, có thể chọn override trực tiếp canonical keys như `app.outbound.endpoint` và `app.outbound.auth-token`; quan trọng là test phải chứng minh behavior trên phiên bản đang dùng.

**Không dùng test này để chứng minh hệ thống production thật có secret hợp lệ.** Nó chỉ xác minh cấu trúc cấu hình production, quá trình binding và guard với dữ liệu giả. Quyền truy cập secret và khả năng gọi API cần được kiểm tra trong môi trường tích hợp phù hợp.

## 21. Khi test một property cần được override thêm

File `application-test.yml` có:

```yaml
app:
  batch:
    size: 5
```

Nhưng một test muốn thử batch size 12:

```java
@ActiveProfiles("test")
@SpringBootTest(
    classes = OrdersApplication.class,
    properties = {
        "app.batch.size=12"
    }
)
class LargerBatchTest {

    @Autowired
    AppSettings settings;

    @Test
    void overridesBatchSizeForThisContext() {
        assertThat(settings.batch().size()).isEqualTo(12);
    }
}
```

Trong test context này, inline `@SpringBootTest(properties=...)` có ưu tiên cao hơn cấu hình Config Data thông thường, vì vậy `size=12` thay giá trị `5` ở file test.

Phân biệt:

- **Profile test** xác định một bộ giá trị mặc định cho automation.
- **Inline test property** xác định một ngoại lệ cụ thể cho một lớp test.
- **`@DynamicPropertySource`** phù hợp hơn nếu giá trị phụ thuộc cổng ngẫu nhiên của Testcontainers/mock server.
- **`@TestPropertySource`** phù hợp nếu muốn nạp riêng một fixture properties.
- **`ApplicationContextRunner`** hữu ích cho nhiều tổ hợp config nhỏ và trường hợp kỳ vọng context fail.

Tránh khai cùng key ở quá nhiều nguồn test rồi phải đoán ai thắng. Với mỗi key nên có một nguồn test chính và vài override có chủ đích.

## 22. Profile và precedence: hiểu vì sao một giá trị vẫn khác YAML

Một giá trị có thể đi qua:

```text
application.yml
application-{profile}.yml
external application.yml / application-{profile}.yml
environment variables
Java system properties
command line arguments
test inline properties / dynamic properties
custom PropertySource
```

Không nên học thuộc một danh sách precedence viết từ Spring Boot 1.x rồi áp vào mọi project hiện đại. Tài liệu Spring Boot Externalized Configuration mô tả nguồn Config Data, thứ tự, location groups và các mức ưu tiên riêng.

Với trường hợp thông thường:

1. File profile-specific có thể override file non-profile-specific trong cùng cơ chế Config Data.
2. Command-line options thường override giá trị từ file Config Data.
3. Biến môi trường thường có ưu tiên cao hơn Config Data đóng gói.
4. Test properties có thể có ưu tiên cao để cố định dữ liệu test.
5. Nếu profile nhiều hơn một, những tài liệu tương ứng được áp dụng theo quy tắc và thứ tự profile.

### 22.1. Ví dụ cùng key ở nhiều nơi

`application.yml`:

```yaml
app:
  batch:
    size: 40
```

`application-prod.yml`:

```yaml
app:
  batch:
    size: 200
```

Lệnh:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.batch.size=300
```

Trong tình huống chuẩn không có nguồn cao hơn, bean nhận `300`. Sửa file prod từ 200 thành 250 không thay kết quả cho đến khi bỏ hoặc thay CLI override.

Nếu một deployment có biến môi trường `APP_BATCH_SIZE`, phải kiểm tra thứ tự và nguồn thực sự có hiệu lực trước khi kết luận. Với ứng dụng thật, dùng Actuator `env` đã được bảo vệ hoặc test bằng `Environment`.

### 22.2. Nguồn được thêm sau không nhất thiết ưu tiên cao

`MutablePropertySources` có các thao tác `addFirst`, `addLast`, `addBefore` và `addAfter`. Một custom source được đăng ký sau nhưng đặt ở cuối danh sách có thể chỉ đóng vai trò fallback. Khi chẩn đoán, xét **thứ tự source**, không xét thời điểm dòng code chạy.

## 23. Không đặt spring.profiles.active trong file theo profile

Một lỗi đáng tránh:

```yaml
# application-prod.yml - KHÔNG ĐÚNG Ý ĐỊNH
spring:
  profiles:
    active: local
```

Tài liệu Spring Boot hiện đại quy định `spring.profiles.active` và `spring.profiles.default` chỉ dùng trong **non-profile-specific documents**. Không đặt chúng trong file `application-prod.yml` hoặc trong document được kích hoạt bằng `spring.config.activate.on-profile`.

Tương tự, các cấu hình như `spring.profiles.include` và `spring.profiles.group` có những giới hạn tương ứng: đặt ở tài liệu không dành riêng cho profile, theo documentation của version đang dùng.

Cách đúng để chọn profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc:

```text
SPRING_PROFILES_ACTIVE=prod
```

Hoặc trong test:

```java
@ActiveProfiles("test")
```

Khi xây JAR, **không đóng cứng profile prod trong main method** nếu cùng artifact cần chạy local/test hoặc được dùng trong nhiều môi trường.

## 24. Multi-document YAML với on-profile: cách thay thế file riêng

Spring Boot hỗ trợ nhiều YAML document cách nhau bằng `---`:

```yaml
app:
  region: global
  batch:
    size: 40

---
spring:
  config:
    activate:
      on-profile: local

app:
  region: local
  batch:
    size: 10

---
spring:
  config:
    activate:
      on-profile: prod

app:
  region: ${DEPLOY_REGION:global}
  batch:
    size: 200
```

Ở đây:

- Document đầu luôn có thể áp dụng.
- Document thứ hai áp dụng khi `local` active.
- Document thứ ba áp dụng khi `prod` active.
- `spring.config.activate.on-profile` quy định điều kiện **document**, không tự bật profile.

**Đây là một phương án thay thế cấu trúc nhiều file, không phải thứ gì cần khai đồng thời thêm vào bộ file của lab.** Nếu đặt cả `application-local.yml` và một document `on-profile: local` khai cùng key, phải hiểu precedence; người bảo trì sẽ khó đoán hơn.

### 24.1. Chọn nhiều file hay một YAML nhiều document?

Dùng file riêng khi:

- Mỗi profile có nhiều khác biệt.
- Tổ chức muốn review tách theo môi trường.
- Dễ phân quyền hoặc đóng gói test resources khác main resources.
- Muốn giảm xung đột khi nhiều nhóm sửa cấu hình.

Dùng multi-document YAML khi:

- Chỉ có vài khác biệt nhỏ.
- Muốn đặt các biến thể gần nhau để dễ so sánh.
- Đội ngũ hiểu rõ `on-profile` và ranh giới document.

Với lab có test resources riêng, **file theo profile** dễ thể hiện cấu trúc phát hành và kiểm thử hơn.

## 25. Nhiều active profile: đừng vô tình trộn local với prod

Spring Boot có thể nhận nhiều active profile:

```bash
java -jar app.jar --spring.profiles.active=prod,metrics
```

Điều này phù hợp nếu `metrics` là một nhóm config bổ trợ rõ ràng. Nhưng:

```bash
java -jar app.jar --spring.profiles.active=local,prod
```

có thể tạo một cấu hình lai nguy hiểm: giá trị của file theo profile được xử lý theo thứ tự precedence, trong khi bean mang `@Profile("local")` và `@Profile("prod")` có thể cùng được đăng ký tùy điều kiện.

**Không xem nhiều profile như phép cộng vô hại.** Với những profile mang ý nghĩa môi trường loại trừ lẫn nhau như local/test/prod, nên có chính sách chỉ cho phép một profile chính trong deployment.

Nếu cần thêm observability, dùng profile bổ trợ rõ ràng:

```text
prod + metrics
local + devtools
```

Và kiểm tra bean conditions/profile expression của từng nhóm.

### 25.1. Trình tự profile ảnh hưởng override

Khi có nhiều profile trong cùng location group và nhiều file profile cung cấp cùng key, Spring Boot dùng các quy tắc override trong đó profile xuất hiện sau có thể thắng.

Nhưng nếu có các location group phức tạp với dấu phẩy và chấm phẩy trong `spring.config.location`, precedence còn phụ thuộc nhóm location. Không suy ra mọi cấu hình luôn theo nguyên tắc “tên file được nạp cuối tuyệt đối thắng”.

Trong thực hành tổng hợp, giữ một profile môi trường chính sẽ giảm bất ngờ.

## 26. Profile groups: gom nhóm profile bổ trợ

Spring Boot hỗ trợ profile group để khi bật một tên logic sẽ kích hoạt các profile thành viên. Ví dụ ở file **không profile-specific**:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
```

Khi kích hoạt `production`, nhóm có thể bật những profile thành viên theo cơ chế Boot.

Đây là chức năng nâng cao, chỉ dùng khi cần. Với lab hiện tại, không cần profile group để chạy local, test và prod.

Một nguyên tắc quan trọng: `spring.profiles.group` phải được khai ở tài liệu phù hợp **không bị kích hoạt bằng profile**, không chèn vào `application-prod.yml` rồi kỳ vọng nhóm tự hình thành khi prod đã active.

Nếu dùng nhóm, cần kiểm tra rằng không vô tình bật cả hai profile môi trường xung đột như `local` và `prod`.

## 27. Bí mật production: cấu hình phải được cấp từ ngoài

Điểm nguy hiểm nhất khi thiết kế cấu hình nhiều môi trường là **đưa credential thật vào repository**, kể cả trong một file tên `application-prod.yml`.

Sai:

```yaml
app:
  outbound:
    auth-token: real-production-token-goes-here
```

Đúng hơn về nguyên tắc:

```yaml
app:
  outbound:
    auth-token: ${ORDER_OUTBOUND_TOKEN}
```

Các nguồn cấp token có thể gồm:

- Kubernetes Secret.
- Secret manager của nền tảng cloud.
- Vault nội bộ.
- Environment variable được cấp bởi pipeline an toàn.
- Config Data import từ hệ thống bí mật nếu có tích hợp phù hợp.

**Không đưa token thật vào Git, log, screenshot, test fixture hoặc nội dung ticket.**

### 27.1. Đặt token trong env có phải tuyệt đối an toàn?

Không. Environment variables cũng có rủi ro: bị đọc bởi process có quyền, dump, debug tools hoặc vô tình in trong log. Nó chỉ giúp tách nguồn giá trị khỏi source code; quản lý quyền, rotation, audit và thời hạn sống vẫn cần giải quyết.

### 27.2. Không log record chứa authToken

Với:

```java
log.info("Settings: {}", appSettings);
```

Java record có thể xuất toàn bộ thành phần qua `toString()`. Token đã được bind không tự che ở application log.

Tốt hơn:

```java
log.info(
    "Order outbound enabled={}, region={}",
    appSettings.outbound().enabled(),
    appSettings.region()
);
```

Ngay cả việc log endpoint/region cũng nên theo phân loại dữ liệu của tổ chức.

## 28. Một JAR cho tất cả môi trường

Một mục tiêu DevOps quan trọng là:

```text
Build application một lần
          |
          v
      app.jar
          |
          +--> local: local profile + local settings
          |
          +--> test: test classpath / test fixtures
          |
          +--> prod: prod profile + deployment secrets
```

Không cần biên dịch lại mã chỉ để đổi `app.batch.size` từ 10 thành 200. Về nguyên tắc, cấu hình nên được tách khỏi artifact.

Tuy nhiên, `application-local.yml` và `application-prod.yml` trong `src/main/resources` có thể được đóng gói cùng artifact. Điều này không có nghĩa chúng tự hoạt động; chỉ các profile được kích hoạt và nguồn được nạp đúng quy tắc mới quyết định kết quả.

Có tổ chức chọn **không đóng gói file prod** mà cấp toàn bộ cấu hình từ deployment. Đây cũng là một lựa chọn hợp lý cho hệ thống có yêu cầu quản lý cấu hình tập trung. Bài lab dùng file prod trong resources để minh họa override, nhưng vẫn yêu cầu secret thật nằm bên ngoài.

## 29. Cấu hình ngoài JAR: tách deployment khỏi source code

Spring Boot cho phép chỉ định hoặc bổ sung vị trí Config Data. Ví dụ:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
```

Trong thư mục `./config/` có thể có:

```text
config/
  application.yml
  application-prod.yml
```

Trong tình huống này, Boot xem xét các nguồn được cấu hình theo quy tắc location và profile. `optional:` cho phép không có vị trí/tài nguyên mà không gây một lỗi “location không tồn tại” trong những trường hợp được hỗ trợ; nó không làm mọi lỗi YAML hay thiếu credential trở nên hợp lệ.

**Lưu ý:** `spring.config.location` và `spring.config.additional-location` được xử lý từ giai đoạn rất sớm. Cấp chúng qua biến môi trường, system property hoặc argument khởi động theo hướng dẫn phiên bản đang dùng; không đặt trong một file mà chính chúng phải giúp Boot tìm tới.

### 29.1. Dấu phẩy và chấm phẩy trong Config Data location

Trong những phiên bản Spring Boot hiện đại, dấu phẩy và dấu chấm phẩy có ngữ nghĩa về **location groups**. Hai cấu hình có cùng đường dẫn nhưng grouping khác nhau không nhất thiết có cùng precedence khi kết hợp profile-specific files.

Nếu dự án chỉ cần một thư mục bổ sung, hãy dùng một vị trí rõ ràng, test và quan sát source order thay vì ghép nhiều nhóm location phức tạp chưa có nhu cầu.

## 30. Chẩn đoán cấu hình đang thắng

Nếu đã sửa `application-prod.yml` nhưng bean vẫn nhận giá trị khác:

1. Xác định profile thực sự: `Environment.getActiveProfiles()`.
2. Xác định canonical key: `app.batch.size`, `app.outbound.connect-timeout`.
3. Kiểm tra command-line arguments của đúng process.
4. Kiểm tra biến môi trường hoặc system properties có ghi đè không.
5. Kiểm tra file Config Data bên ngoài, import và origin.
6. Kiểm tra class `@ConfigurationProperties` đã đăng ký.
7. Đối chiếu typed value của bean.
8. Kiểm tra service có snapshot hoặc logic tự thay đổi giá trị không.

Nếu được phép sử dụng Actuator, có thể xem:

```text
GET /actuator/env/app.batch.size
GET /actuator/configprops/app
```

`env` giúp thấy nguồn thắng và origin; `configprops` giúp thấy object configuration properties và input binding. **Không bật show-values=always trên production** để chỉ xem một batch size; dùng truy vấn metadata và kiểm tra whitelist được phân quyền.

### 30.1. Không có bean ở configprops?

Có thể class chưa đăng ký, prefix không khớp, bean có điều kiện profile chưa tạo hoặc endpoint chưa được expose. `Environment` có property không đồng nghĩa Binder tự tạo một object Java đích.

### 30.2. Value đã bị mask không phải bằng 6 dấu sao

Nếu `env` trả `******`, đó thường là sanitized response của Actuator. Nó không chứng minh token hay batch size thực tế là chuỗi `******`.

## 31. Cách đọc Environment trực tiếp trong Java

Để kiểm tra những khóa **không nhạy cảm** ở startup, có thể tạo một runner trong môi trường local/test:

```java
package com.example.orders;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class LocalDiagnosticsConfiguration {

    @Bean
    @Profile("local")
    ApplicationRunner inspectLocalConfig(
            Environment environment,
            AppSettings settings) {

        return args -> {
            System.out.println(
                "Profiles: " +
                String.join(",", environment.getActiveProfiles())
            );

            System.out.println(
                "Batch size: " + settings.batch().size()
            );

            System.out.println(
                "Outbound enabled: " +
                settings.outbound().enabled()
            );
        };
    }
}
```

Ví dụ chỉ in profiles, batch size và cờ enabled. Không in `authToken` hoặc toàn bộ object `AppSettings`.

Trong production, ưu tiên structured logging đã được kiểm soát, không dùng `System.out.println` tự phát.

### 31.1. Một giá trị từ Environment không chứng minh bean đã bind

`environment.getProperty("app.batch.size")` có thể trả `"200"`, nhưng `settings.batch().size()` là giá trị `int` sau binding. Nếu bean bị dựng sai hoặc được khởi tạo trước một thay đổi runtime, hai quan sát có thể khác.

Dùng test và `configprops` khi cần tìm lỗi binding, không chỉ kiểm tra text ở Environment.

## 32. Profile và Bean có điều kiện

Có thể tách adapter local với adapter production:

```java
public interface OutboundGateway {
    String kind();
}
```

Cấu hình bean:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Profile({"local", "test"})
    OutboundGateway simulatedGateway() {
        return () -> "simulated";
    }

    @Bean
    @Profile("prod")
    OutboundGateway productionGateway() {
        return () -> "production";
    }
}
```

Đoạn trên chỉ trả nhãn, không gọi mạng. Nó minh họa cơ chế điều kiện tạo bean.

**Vấn đề:** nếu không có profile nào active, có thể không có `OutboundGateway`. Nếu local và prod cùng active, có thể có hai bean cùng interface, khiến injection theo type trở nên mơ hồ.

Vì vậy nên:

- Có chính sách profile môi trường loại trừ lẫn nhau.
- Thiết kế bean fallback cho profile mặc định nếu ứng dụng cần.
- Tránh đặt bean production được tạo bởi profile khi thiếu kiểm tra config/secret.
- Viết integration test rằng một profile chỉ có đúng gateway theo ý định.

### 32.1. @Profile không đồng nghĩa feature flag

Một profile chọn bean ở startup. Cờ `app.outbound.enabled` có thể quyết định hành vi của bean. Chúng giải quyết các lớp khác nhau:

- `@Profile`: **bean nào tồn tại** trong context.
- Property flag: **bean thực hiện hành vi nào**.
- Configuration Properties: **dữ liệu nào được bind** vào object.
- Runtime validation: **dữ liệu đó có hợp lệ không**.

Đừng thêm cả profile và flag chỉ để lặp cùng một ý định nếu chưa rõ vì sao cần cả hai.

## 33. Kết hợp @ConditionalOnProperty khi thích hợp

Một alternative với profile để điều kiện tạo bean:

```java
@Bean
@ConditionalOnProperty(
    prefix = "app.outbound",
    name = "enabled",
    havingValue = "true"
)
OutboundGateway enabledGateway() {
    return () -> "enabled";
}
```

Khi `app.outbound.enabled=false`, bean này không được đăng ký. Nhưng nếu một service yêu cầu `OutboundGateway`, nó phải có một bean fallback hoặc dependency optional tương ứng.

Dùng `@ConditionalOnProperty` khi điều kiện **tính năng** là yếu tố chính; dùng `@Profile` khi đó là lựa chọn **môi trường**. Trong thực tế có thể kết hợp, nhưng phải test để tránh thiếu bean hoặc có hai bean cùng type.

## 34. Một chiến lược ngăn profile không hợp lệ

Nếu local/test/prod phải loại trừ nhau, có thể kiểm tra trong một test hoặc guard startup. Một cách lập luận:

```text
active profiles = [local]     OK
active profiles = [test]      OK cho test context
active profiles = [prod]      OK khi có secret hợp lệ
active profiles = [prod,metrics] OK nếu metrics là bổ trợ
active profiles = [local,prod]  Không hợp lệ theo chính sách
active profiles = [test,prod]   Không hợp lệ theo chính sách
```

Có thể kiểm tra bằng `Environment.acceptsProfiles(Profiles.of("prod & local"))` hoặc các tập profile đang active.

Ví dụ phác thảo guard:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean localAndProd =
        environment.acceptsProfiles(Profiles.of("local & prod"));

boolean testAndProd =
        environment.acceptsProfiles(Profiles.of("test & prod"));

if (localAndProd || testAndProd) {
    throw new IllegalStateException(
        "Conflicting environment profiles"
    );
}
```

Đây là logic cần đặt ở điểm startup phù hợp, không phải code chạy trong request handler. Để đảm bảo fail trước side effect nguy hiểm, hãy đưa guard vào giai đoạn cấu hình đủ sớm hoặc ràng buộc từ deployment policy, không đợi một job nền đã chạy rồi mới kiểm tra.

## 35. Không sử dụng profile như một hệ thống phân quyền

Tên `prod` hoặc `local` có thể được đặt bởi command line hay biến môi trường. Nó không phải thông tin xác thực về danh tính người gọi.

Sai lầm:

```java
if (environment.acceptsProfiles(Profiles.of("prod"))) {
    // Bỏ qua authentication vì chắc chắn là production
}
```

Profile chỉ mô tả điều kiện cấu hình, không được dùng để bỏ qua security. Ngay trong profile local, nếu endpoint được expose trên mạng rộng hoặc chứa dữ liệu thật, vẫn cần quyền và kiểm soát phù hợp.

Tương tự, **profile test không bảo đảm test không có network access**. Phải thiết kế fake clients, test isolation và kiểm tra side effects.

## 36. Những nguồn cấu hình không nên trộn lẫn vô tội vạ

Một số nguồn đều có thể cấp `app.batch.size`:

```text
src/main/resources/application.yml
src/main/resources/application-prod.yml
file:./config/application-prod.yml
APP_BATCH_SIZE
-Dapp.batch.size=...
--app.batch.size=...
@SpringBootTest(properties=...)
@DynamicPropertySource
```

Trong một workflow tốt:

- Common quản lý default.
- Profile file quản lý khác biệt có tính chất môi trường.
- Deployment quản lý giá trị đặc thù của cluster/instance.
- Test quản lý fixture và nguồn test động.
- Không có hai nhóm cùng “sở hữu” một key vô tình.
- Khi một key được override, có tài liệu giải thích vì sao.

Cần cẩn trọng với Java system properties: sửa `System.setProperty(...)` trong một test có thể ảnh hưởng test khác cùng JVM, đặc biệt khi chạy song song. Dùng `@SpringBootTest(properties=...)` hoặc nguồn test riêng để giảm side effect.

## 37. Các quy tắc về cấu hình collection

### 37.1. List

File chung:

```yaml
app:
  routes:
    - primary
    - backup
```

File prod:

```yaml
app:
  routes:
    - prod-primary
```

Theo các quy tắc binding của Spring Boot, List thường được **thay thế** khi cấu hình profile/nguồn cao hơn khai list mới, không nối tự động `primary, backup, prod-primary`.

Vì vậy, với List, nên khai trọn bộ phần tử của môi trường ở một nguồn rõ ràng.

### 37.2. Map

File chung:

```yaml
app:
  channels:
    email: enabled
    push: disabled
```

File prod:

```yaml
app:
  channels:
    push: enabled
```

Map có thể gộp các entry, trong đó key `push` bị nguồn ưu tiên cao hơn ghi đè, còn `email` giữ từ common.

Không xem đây là bảo đảm mọi cấu trúc custom type đều merge giống Map String thông thường. Với object lồng nhau, collection và Map key đặc biệt, cần test kết quả Binder thực tế.

## 38. Cách quản lý tên biến môi trường

Spring Boot hỗ trợ relaxed binding giữa tên canonical và một số dạng biến môi trường.

Ví dụ:

```text
app.outbound.connect-timeout
APP_OUTBOUND_CONNECTTIMEOUT
```

Quy tắc điển hình khi chuyển canonical property sang environment variable: thay dấu chấm bằng gạch dưới, bỏ dấu gạch ngang và viết hoa. Vì vậy `APP_OUTBOUND_CONNECTTIMEOUT` là ví dụ gần với quy tắc của Binder.

Không viết `APP_OUTBOUND_CONNECT_TIMEOUT` rồi mặc định nó luôn bind đúng theo mọi trường hợp chỉ vì nhìn tự nhiên. Kiểm tra convention thực tế và test cấu hình trên phiên bản Boot đang dùng.

Một số property có List index/Map key có mapping phức tạp hơn. Với secret trong ví dụ, ta dùng placeholder `ORDER_OUTBOUND_TOKEN` nên tên biến được **tham chiếu trực tiếp**, không cần suy ra từ tên `app.outbound.auth-token`.

## 39. Common defaults có thể che việc thiếu cấu hình prod

Một rủi ro của cách “common + overrides” là một default an toàn cho local lại trở thành **giá trị fallback không chấp nhận được ở prod**.

Ví dụ common:

```yaml
app:
  outbound:
    endpoint: https://sandbox.example.invalid/api
```

Nếu file prod không override hoặc biến môi trường chưa cấp, ứng dụng có thể nhận endpoint sandbox và khởi động sai ý định.

Để giảm rủi ro:

1. File prod khai endpoint từ placeholder bắt buộc.
2. Production guard xác minh endpoint/credential.
3. Test profile prod bằng giá trị giả.
4. Deployment readiness kiểm tra các điều kiện thật sự cần.
5. Không cho service outbound gửi dữ liệu cho endpoint không được phê duyệt.
6. Có policy xác nhận host hoặc allowlist phù hợp với hợp đồng tích hợp.

Không phải “một default hợp lệ về kiểu Java” là “một default an toàn về vận hành”.

## 40. Cấu hình local phải tránh xung đột cổng

File local có thể đặt:

```yaml
server:
  port: 8081
```

Nhưng nếu nhiều developer hoặc nhiều app chạy cùng máy, port cố định vẫn có thể xung đột. Với test HTTP integration, có thể dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
```

và client test được cấu hình để dùng cổng thực tế.

**Không đặt server.port=0 trong mọi profile** chỉ để tránh xung đột nếu hệ thống giám sát hoặc deployment cần cổng cố định. Mỗi môi trường nên có chiến lược port riêng.

Với bài lab không cần HTTP, ta không khai server.port để giảm liên quan đến web stack.

## 41. Production không nên giữ DEBUG toàn cục

File local có:

```yaml
logging:
  level:
    com.example.orders: DEBUG
```

File prod giữ INFO. Nếu ứng dụng log một object chứa token, chính sách DEBUG quá rộng có thể vô tình làm lộ dữ liệu.

Không coi mức INFO tuyệt đối an toàn; một lệnh `log.info("{}", settings)` vẫn có thể rò secret. **Hành vi code logging** phải được thiết kế đúng bất kể profile.

Một phương án tốt:

- Chỉ log những field đã được đánh giá không nhạy cảm.
- Không in `Environment` hoàn chỉnh.
- Không bật raw Actuator values trên production.
- Sử dụng structured logging và kiểm soát vòng đời lưu trữ.
- Có test hoặc review các điểm log cấu hình khi thêm credential mới.

## 42. Tài liệu cấu hình cho người triển khai

Một bảng hợp đồng mẫu trong README của dự án:

| Property | Bắt buộc khi nào? | Default | Nguồn khuyến nghị |
| --- | --- | --- | --- |
| `spring.profiles.active` | Khi chọn local/prod | Không ép local | ENV/CLI/deployment |
| `app.display-name` | Tất cả | Common YAML | Common |
| `app.region` | Tất cả | global | Profile/ENV |
| `app.outbound.enabled` | Tất cả | false | Common + prod |
| `app.outbound.endpoint` | Khi tích hợp bật | Sandbox giả trong common | Prod ENV |
| `app.outbound.auth-token` | Khi prod outbound bật | Không có | Secret manager |
| `app.outbound.connect-timeout` | Tất cả | 2s | Common/profile |
| `app.outbound.max-attempts` | Tất cả | 3 | Common/profile |
| `app.batch.size` | Tất cả | 40 | Common/profile/deploy |
| `app.batch.flush-interval` | Tất cả | 5s | Common/profile |
| `app.diagnostics.verbose` | Tất cả | false | Common/local |

Một hợp đồng đầy đủ còn nên nói:

- Kiểu dữ liệu và đơn vị.
- Phạm vi giá trị hợp lệ.
- Nơi chịu trách nhiệm cấp giá trị.
- Liệu thay đổi có cần restart hay không.
- Có được log/quan sát value không.
- Giá trị ảnh hưởng đến dịch vụ ngoài nào.
- Khi thiếu/sai thì fail startup hay fallback.
- Cách test đường cấu hình đó.

## 43. Checklist trước khi đưa prod lên môi trường thật

**Phần cấu hình:**

- [ ] Artifact được build từ đúng version.
- [ ] `SPRING_PROFILES_ACTIVE=prod` được cấp đúng.
- [ ] Không vô tình bật `local` hoặc `test` cùng prod.
- [ ] File prod và Config Data ngoài đã được nạp.
- [ ] Region, endpoint, timeout, batch size đã có giá trị phù hợp.
- [ ] Token/credential được cấp từ secret store, không từ Git.
- [ ] Production guard/validation thực sự hoạt động.
- [ ] Không dùng endpoint sandbox làm fallback không mong muốn.

**Phần bảo mật:**

- [ ] Không log settings record có token.
- [ ] Không expose Actuator `env`/`configprops` công khai.
- [ ] Các management endpoint được bảo vệ bằng auth/network policy.
- [ ] Secret không nằm trong command line có thể bị ghi history hoặc process listing.
- [ ] Có quy trình rotate/revoke nếu credential bị lộ.

**Phần vận hành:**

- [ ] Có readiness/health checks phù hợp.
- [ ] Timeout và retry phù hợp SLA và idempotency.
- [ ] Batch size không vượt khả năng hệ thống.
- [ ] Metrics/logs không tiết lộ dữ liệu nhạy cảm.
- [ ] Rollback không phụ thuộc sửa file thủ công sau khi deploy.
- [ ] Test/CI có profile riêng và không gọi network production.

## 44. Lỗi thường gặp: profile không được bật

Triệu chứng: `application-local.yml` khai batch size 10 nhưng bean vẫn nhận 40.

Nguyên nhân có thể:

- Không có active profile `local`.
- Biến `SPRING_PROFILES_ACTIVE` được đặt ở shell khác với process.
- File không nằm trên runtime classpath.
- File được đặt tên sai như `application-lcoal.yml`.
- Một source có ưu tiên cao hơn ghi đè size.
- App chạy instance khác với instance đang được debug.

Cách xử lý:

1. Kiểm tra active profiles của process.
2. Xác nhận file được đóng gói/nạp.
3. Xác định canonical key `app.batch.size`.
4. Xem `Environment`/Actuator env theo quyền được cấp.
5. Kiểm tra bean `AppSettings` đã bind.
6. Không sửa bừa file chung để ép kết quả.

## 45. Lỗi thường gặp: file test bị đóng gói vào sản phẩm

Nếu đặt fixture chứa token giả hoặc cấu hình test trong `src/main/resources`, nó có thể đi cùng JAR. Dù không active, thông tin vẫn có thể tồn tại trong artifact.

Một cách giảm rủi ro là đặt `application-test.yml` trong `src/test/resources` nếu chỉ test runner cần nó. Sau build, kiểm tra nội dung artifact theo quy trình release khi có yêu cầu bảo mật.

Đừng dùng cách này như giấy phép lưu bí mật thật trong test resources; test artifacts và logs cũng có thể bị chia sẻ.

## 46. Lỗi thường gặp: đặt spring.profiles.active sai nơi

Không khai `spring.profiles.active` trong `application-local.yml` hoặc trong một document đang dùng `spring.config.activate.on-profile`.

Đúng: chọn profile từ CLI/ENV/test annotation hoặc non-profile-specific source thích hợp.

Sự khác biệt giữa **chọn profile** và **cấu hình cho profile** là nguyên tắc cốt lõi của thiết kế này.

## 47. Lỗi thường gặp: thiếu secret nhưng ứng dụng vẫn chạy

Có thể nguyên nhân là default không an toàn, guard không được bật, placeholder chưa giải quyết theo cách mong đợi hoặc code chưa kiểm tra token khi `enabled=true`.

Cần:

- Kiểm tra profile prod được active.
- Xác minh guard/validation có được tạo.
- Có test với token thiếu/rỗng.
- Không in token trong lỗi.
- Kiểm tra ứng dụng không phát request bên ngoài khi config không hợp lệ.

Nếu muốn fail ngay trong giai đoạn binding, hãy biểu diễn ràng buộc theo `@ConfigurationProperties`/Bean Validation hoặc validator chuyên dụng phù hợp, thay vì chờ service gửi request đầu tiên mới phát hiện.

## 48. Lỗi thường gặp: List và Map cho kết quả bất ngờ

Một List ghi hai phần tử ở common, một phần tử ở prod có thể cho kết quả chỉ gồm phần tử prod. Một Map thì có thể gộp và ghi đè theo key.

Cách tránh: ghi rõ hợp đồng collection và viết test typed object. Khi config thay đổi lớn, đừng đoán kết quả chỉ từ việc nhìn các đoạn YAML riêng lẻ.

## 49. Lỗi thường gặp: context không khởi động trong test prod

Vì `application-prod.yml` chứa placeholder bắt buộc, test dùng `@ActiveProfiles("prod")` mà không cung cấp fake endpoint/token có thể fail. Đây là tín hiệu cần **cấp fixture test**, không phải lý do để đưa secret thật vào test.

Dùng `@SpringBootTest(properties=...)` với giá trị giả; bảo đảm endpoint không mở kết nối thật và guard chỉ kiểm tra format/sự hiện diện phù hợp.

Muốn test một startup failure dự kiến, `ApplicationContextRunner` có thể phù hợp hơn `@SpringBootTest` vì test method của `@SpringBootTest` có thể không chạy khi context fail ngay từ đầu.

## 50. Bài tập 1: tự xác định giá trị hiệu lực

Cho:

```yaml
# application.yml
app:
  batch:
    size: 40
    flush-interval: 5s
```

```yaml
# application-local.yml
app:
  batch:
    size: 10
```

Với profile `local`, hãy trả lời:

1. `batch.size` là 10.
2. `batch.flush-interval` là 5s.
3. Vì sao không cần lặp lại `flush-interval` trong file local?
4. Nếu thêm `--app.batch.size=15` qua CLI, giá trị nào thắng trong tình huống thông thường?

## 51. Bài tập 2: tách đúng trách nhiệm của từng file

Một đồng nghiệp muốn đưa cả `display-name`, `max-attempts`, `batch.size`, `auth-token` và `region` vào cả ba file local/test/prod.

Hãy thiết kế lại:

- Thuộc tính dùng chung ở `application.yml`.
- Khác biệt theo môi trường ở các file profile.
- Secret trong nguồn được bảo vệ.
- Test fixture trong `src/test/resources`.
- Một bảng giải thích những giá trị nào bắt buộc override ở prod.

Mục tiêu là giảm trùng lặp mà vẫn tránh default nguy hiểm.

## 52. Bài tập 3: kiểm tra @ConfigurationProperties

Thêm:

```java
@ConfigurationProperties(prefix = "app")
public record AppSettings(
    String displayName,
    Batch batch
) {
    public record Batch(int size, Duration flushInterval) {}
}
```

Viết một `@SpringBootTest` với `@ActiveProfiles("local")` rồi assert:

```java
assertThat(settings.batch().size()).isEqualTo(10);
assertThat(settings.batch().flushInterval())
    .isEqualTo(Duration.ofSeconds(5));
```

Giải thích sự khác nhau giữa giá trị `"5s"` trong YAML và object `Duration` trong Java.

## 53. Bài tập 4: phát hiện rủi ro bí mật

Cho `application-prod.yml`:

```yaml
app:
  outbound:
    auth-token: "live-token-here"
```

Hãy sửa thành placeholder, nêu nơi cấp token phù hợp và giải thích vì sao không được:

- Commit token vào Git.
- In toàn bộ `AppSettings`.
- Bật raw values của Actuator trên cổng công khai.
- Dùng token production trong CI test.

## 54. Bài tập 5: test cho profile test

Yêu cầu:

- `app.batch.size=5`.
- `app.outbound.enabled=false`.
- `app.outbound.connect-timeout=100ms`.
- `app.diagnostics.verbose=false`.

Viết `application-test.yml` trong `src/test/resources` và một test:

```java
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
```

Assert typed bean và đảm bảo test không cần bất kỳ API token thật nào.

## 55. Bài tập 6: bảo vệ profile prod

Yêu cầu prod phải:

- Bật outbound.
- Có endpoint HTTPS.
- Có token khác rỗng.
- Không log token.
- Không dùng địa chỉ sandbox mặc định.

Hãy viết một kiểm tra startup phù hợp, test bằng token giả và giải thích vì sao kiểm tra chỉ ở `ApplicationRunner` có thể quá muộn để ngăn side effect trong bean constructor.

## 56. Bài tập 7: dùng nhiều profile

Chạy:

```bash
java -jar app.jar --spring.profiles.active=local,prod
```

Hãy dự đoán những rủi ro:

- Một số property prod có thể ghi đè local.
- Các bean `@Profile("local")` và `@Profile("prod")` có thể đồng thời tồn tại.
- Một bean injection có thể trở nên mơ hồ.
- Một cấu hình giả lập có thể bị trộn với credential production.

Đề xuất chính sách chỉ có một profile môi trường chính, các profile bổ trợ có tên và chức năng rõ ràng.

## 57. Bài tập 8: xử lý giá trị từ deployment

File prod có:

```yaml
app:
  batch:
    size: 200
```

Deployment đặt:

```text
APP_BATCH_SIZE=300
```

Hãy giải thích vì sao kết quả có thể là 300 và cách xác nhận bằng `Environment`/Actuator env trên đúng instance. Nếu muốn giá trị 200 từ file prod, cần loại bỏ hoặc thay override tương ứng ở deployment.

## 58. Bài tập 9: dùng source ngoài JAR

Yêu cầu cluster A và cluster B cùng chạy một JAR, cùng profile prod nhưng có endpoint và region khác nhau.

Hãy thiết kế:

- `application-prod.yml` giữ logic chung.
- Region/endpoint cấp qua Config Data ngoài hoặc ENV của cluster.
- Token cấp qua secret store riêng.
- Test xác nhận mỗi cluster chỉ nhận nguồn của mình.
- Không tạo profile tên từng pod nếu không cần.

## 59. Bài tập 10: viết bảng hợp đồng cấu hình

Tạo bảng cho 10 thuộc tính trong lab với các cột:

```text
name | Java type | common default | local | test | prod |
required | source owner | sensitive | validation
```

Nêu chính sách:

- Không chứa secret thật trong repository.
- Dùng explicit time units.
- Không trùng lặp các default không cần thiết.
- Thông tin runtime phải có thể kiểm chứng bằng test.
- Các profile môi trường chính không được trộn trái ý định.

## 60. Tổng kết

Thiết kế cấu hình chung với ba profile là cách chuyển từ “mỗi môi trường một ứng dụng” sang “một ứng dụng, nhiều tập giá trị có kiểm soát”.

```text
               application.yml
               (common defaults)
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
 application-local  application-test  application-prod
    (local)            (test)             (prod)
          |           |           |
          +-----------+-----------+
                      |
              Externalized Configuration
                      |
               Environment / Binder
                      |
                @ConfigurationProperties
                      |
                Application services
```

Những quy tắc cần ghi nhớ:

1. **Common chỉ chứa cấu hình dùng chung và default an toàn.**
2. **Profile file chỉ chứa khác biệt**, tránh copy-paste toàn bộ YAML.
3. **Local** ưu tiên fake endpoint, batch nhỏ, quan sát tốt và không kết nối production.
4. **Test** ưu tiên fixture xác định, cô lập, không có secret thật; nếu chỉ dùng cho test runner, đặt `application-test.yml` trong `src/test/resources`.
5. **Prod** ưu tiên secret bên ngoài, validation bắt buộc, HTTPS và chính sách vận hành rõ.
6. **Không đặt `spring.profiles.active` trong file profile-specific** hoặc document `on-profile`.
7. **Không tự bật local chỉ vì file local tồn tại**; chọn profile từ môi trường, CLI hoặc test annotation.
8. **Nhiều profile có thể gây xung đột**, nhất là local và prod; có chính sách cho profile chính và profile bổ trợ.
9. **@ConfigurationProperties** giúp liên kết dữ liệu có kiểu; **Bean Validation** giúp kiểm soát hợp đồng.
10. **Config Data precedence** quyết định nguồn thắng; file profile không phải nguồn duy nhất.
11. **Không log object chứa token**, không coi environment variable là kho secret tuyệt đối an toàn.
12. **Test cả override và fallback về common**, không chỉ test một giá trị.
13. **Một artifact có thể dùng cho nhiều môi trường** khi cấu hình được tách khỏi việc build.
14. **Quan sát theo đúng instance** bằng Environment/Actuator đã bảo vệ khi một giá trị khác dự đoán.
15. **Không mặc định flag enabled=false tự tắt mọi side effect**; code phải thực thi chính sách đó.

### Tài liệu tham khảo chính thức

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestContext Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
