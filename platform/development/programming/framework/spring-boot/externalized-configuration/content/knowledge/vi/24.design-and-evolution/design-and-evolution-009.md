# Rà soát cấu hình trước phát hành bằng metadata, kiểm thử và tài liệu sử dụng

## Mục tiêu

Một ứng dụng Spring Boot có thể hoạt động đúng trên máy phát triển nhưng lỗi ngay khi đưa lên staging hoặc production vì tên thuộc tính khác nhau, profile không được kích hoạt, biến môi trường đặt sai, cấu hình thiếu, kiểu dữ liệu không chuyển đổi được, hoặc thay đổi tên property giữa hai phiên bản mà không thông báo người vận hành.

Trong **Spring Boot Externalized Configuration**, “phát hành phần mềm” không chỉ là build được file JAR. Những thuộc tính được công bố cho người sử dụng ứng dụng hoặc thư viện cũng là một dạng **public configuration contract**: chúng có tên, kiểu, mặc định, ràng buộc, cách override, đơn vị, trạng thái deprecated và chính sách bảo mật.

Một quy trình rà soát cấu hình tốt cần phối hợp ba lớp bằng chứng:

1. **Metadata** cho IDE, build tooling và người viết cấu hình biết những key được hỗ trợ, loại dữ liệu, mô tả, gợi ý, default và deprecated status.
2. **Kiểm thử** cho thấy Binder, validation, bean conditions, profiles, Config Data imports và quá trình khởi động thực sự vận hành theo hợp đồng.
3. **Tài liệu sử dụng** cho developer, DevOps/SRE và người tiêu thụ thư viện biết phải khai báo gì, ở đâu, cách override, cách xử lý thiếu/sai giá trị, và thay đổi gì so với phiên bản trước.

Ba lớp này bổ sung cho nhau. **Metadata không phải validator runtime**, một bộ test xanh không tự làm tài liệu trở nên đầy đủ, và README có ví dụ đúng không chứng minh JAR phát hành đã đóng gói metadata hoặc ứng dụng sẽ khởi động thành công.

Bài học hướng dẫn một quy trình trước phát hành có thể áp dụng cho một service hoặc thư viện Spring Boot. Ví dụ chủ yếu theo **Spring Boot 3.x**, Java 17+, Maven/Gradle và Jakarta Validation. Với Boot 4.x, cần đối chiếu dependency, package và các API đã được modularize/thay đổi theo phiên bản dự án.

### Kết quả mong muốn

Sau khi đọc, bạn có thể:

- Tạo bản kiểm kê các configuration properties theo prefix, owner và vòng đời.
- Định nghĩa schema Java bằng **@ConfigurationProperties** thay cho hàng loạt @Value rời rạc khi phù hợp.
- Sinh và kiểm tra **META-INF/spring-configuration-metadata.json**.
- Bổ sung mô tả/hints/deprecation bằng **additional-spring-configuration-metadata.json**.
- Phân biệt metadata advisory với binding/validation đang chạy thực.
- Viết test từ mức Java object, Binder, ApplicationContextRunner đến SpringApplication đầy đủ.
- Kiểm tra profile, precedence, Config Data imports, env var, CLI và cấu hình bắt buộc.
- Viết tài liệu vận hành không làm lộ secret.
- Lập checklist phát hành, tiêu chí chặn release và quy trình migration cho key đổi tên.
- Chẩn đoán khi metadata, test và tài liệu không cùng phản ánh một hợp đồng.

---

## 1. Vì sao cấu hình là một API?

Xét một thư viện HTTP client dùng cấu hình:

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 2s
    retry:
      max-attempts: 3
      backoff: 300ms
~~~

Nếu các service khác dựa vào những key này, chúng đang tiêu thụ một API dù không import class Java tương ứng.

Một thay đổi:

~~~text
acme.gateway.connect-timeout
           ->
acme.gateway.connection-timeout
~~~

có thể làm deployment cũ mất override nếu thư viện không hỗ trợ alias hoặc không công bố cách di trú. Tương tự, đổi đơn vị từ milliseconds sang seconds mà không nêu rõ có thể làm timeout tăng hoặc giảm hàng nghìn lần.

Các thành phần của configuration contract:

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| Canonical name | Tên property được hỗ trợ là gì? |
| Prefix | Nhóm này thuộc module nào? |
| Java type | String, URI, Duration, DataSize, boolean, List hay Map? |
| Required | Bỏ qua key có hợp lệ không? |
| Default | Giá trị nào được dùng khi không cung cấp? |
| Range/invariant | Giá trị nào bị từ chối? |
| Environment mapping | Tên biến môi trường chuẩn là gì? |
| Precedence | File, profile, env, JVM và CLI ghi đè nhau thế nào? |
| Secret classification | Có được log, tài liệu hóa giá trị cụ thể không? |
| Deprecated/replacement | Key cũ còn được chấp nhận không và đến khi nào? |
| Owner | Team nào quyết định schema và xử lý sự cố? |
| Observability | Có cách nào biết nguồn thắng mà không in raw value? |

**Rà soát trước phát hành** là xác nhận các thành phần liên quan đã được mô tả và kiểm chứng ở mức phù hợp, không phải cố gắng in mọi property đang tồn tại trong Environment.

---

## 2. Phân loại cấu hình theo tác động

Không phải thuộc tính nào cũng có cùng mức rủi ro. Có thể chia thành:

**Bootstrap-critical**: ảnh hưởng đến việc ứng dụng đọc Config Data, profile, logging hoặc khởi tạo những thành phần sớm. Sai thời điểm nạp có thể khiến sửa property sau đó không còn tác dụng như mong đợi.

**Operational-critical**: database URL, pool size, service endpoint, retry, timeout, message broker, storage location. Sai giá trị có thể làm startup thất bại hoặc hệ thống vận hành sai.

**Security-sensitive**: password, token, private key, trust store password, OAuth client secret. Cần chính sách bảo mật mạnh hơn tài liệu cấu hình thông thường.

**Feature/optional**: bật/tắt module, batch size của tính năng phụ, logging chi tiết của module. Có thể cho phép giá trị mặc định hoặc vắng mặt tùy thiết kế.

**Internal-only**: implementation detail không nên trở thành contract công khai nếu có thể tránh.

### 2.1. Ma trận phát hành theo rủi ro

| Nhóm | Metadata | Kiểm thử cần thiết | Tài liệu cần thiết |
| --- | --- | --- | --- |
| Bootstrap-critical | Có mô tả/thời điểm | SpringApplication/Config Data | Nguồn sớm, profile/import, restart |
| Operational-critical | Type, default, range | Binder, validation, startup | Ví dụ, đơn vị, tác động, rollback |
| Security-sensitive | Không ghi secret raw | Missing/invalid, redaction | Cách cấp secret an toàn, quyền, rotation |
| Feature/optional | Default, values hints | Conditional bean, enabled/disabled | Khi bật/tắt có tác động gì |
| Internal-only | Chỉ khi thực sự public | Test ở module sở hữu | Không vô tình công bố key chưa ổn định |

Tập trung test theo mức rủi ro sẽ hiệu quả hơn việc tạo một bộ @SpringBootTest cho tất cả key.

---

## 3. Bắt đầu từ một schema duy nhất

Một mẫu Java record cho cấu hình gateway:

~~~java
package example.gateway;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

/**
 * Connection and retry settings for the outbound gateway.
 *
 * @param baseUrl Base URL of the upstream gateway.
 * @param connectTimeout Maximum time for establishing a connection.
 * @param retry Retry settings for failed requests.
 * @param endpoints Endpoint definitions that the gateway may use.
 */
@Validated
@ConfigurationProperties(prefix = "acme.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @NotNull @DefaultValue("2s") Duration connectTimeout,
        @Valid @NotNull Retry retry,
        @NotEmpty List<@NotNull @Valid Endpoint> endpoints
) {

    /**
     * Retry policy.
     *
     * @param maxAttempts Maximum number of attempts, at least one.
     * @param backoff Delay between attempts.
     */
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}

    /**
     * A target endpoint.
     *
     * @param name Name of the endpoint.
     * @param host DNS host name.
     * @param port TCP port of the endpoint.
     */
    public record Endpoint(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Ví dụ cấu hình hợp lệ:

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 3s
    retry:
      max-attempts: 3
      backoff: 300ms
    endpoints:
      - name: primary
        host: edge-a.example.test
        port: 8080
~~~

### 3.1. Các thuộc tính theo đường dẫn canonical

~~~text
acme.gateway.base-url
acme.gateway.connect-timeout
acme.gateway.retry.max-attempts
acme.gateway.retry.backoff
acme.gateway.endpoints[0].name
acme.gateway.endpoints[0].host
acme.gateway.endpoints[0].port
~~~

Tên canonical nên ở dạng lower-case, dấu chấm chia nhóm và dấu gạch ngang chia từ. Ví dụ **connect-timeout** bind vào Java component **connectTimeout**.

### 3.2. Vì sao dùng @ConfigurationProperties?

So với việc tạo nhiều field:

~~~java
@Value("...") String baseUrl;
@Value("...") Duration timeout;
~~~

một class cấu hình có tên rõ ràng giúp tập trung schema, validation, defaults, tài liệu Javadoc và metadata cho IDE.

Tuy vậy, **chỉ có class không có nghĩa nó là một bean**. Cần đăng ký bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(GatewayProperties.class)** trong cấu trúc ứng dụng phù hợp.

### 3.3. @Validated, @Valid và @NotNull

**@Validated** đặt trên bean configuration properties giúp Spring Boot kích hoạt validation khi binding nếu có provider phù hợp.

**@Valid** trên Retry và các phần tử Endpoint cho phép validation đi sâu.

**@NotNull** trên Retry làm rõ rằng nhánh retry bắt buộc tồn tại. **@Valid không tự cấm null**.

**@NotEmpty** trên List bảo đảm có ít nhất một phần tử; **@Valid** trên element kiểm tra mỗi Endpoint.

Đây là những quy tắc runtime; metadata sinh ra từ class không tự kiểm tra ràng buộc khi ứng dụng được triển khai.

---

## 4. Metadata của Spring Boot là gì?

Spring Boot mô tả các thuộc tính cấu hình thông qua JSON metadata ở:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Nó có thể xuất hiện trong build output và được đóng gói vào JAR. Một số IDE đọc metadata từ dependency để gợi ý tên property, kiểu, mô tả, mặc định, danh sách lựa chọn và cảnh báo deprecated.

Các phần phổ biến:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

Trong những phiên bản/định dạng hỗ trợ metadata bổ sung còn có **ignored**.

**Metadata không phải application.yml đang chạy**. Nó mô tả những gì một module có thể nhận, không phải giá trị do operator đã khai báo trong một môi trường cụ thể.

### 4.1. groups

Một group đại diện prefix hoặc nhóm thuộc tính, ví dụ:

~~~json
{
  "name": "acme.gateway",
  "type": "example.gateway.GatewayProperties",
  "sourceType": "example.gateway.GatewayProperties"
}
~~~

Group giúp tooling tổ chức gợi ý, không phải một key bắt buộc phải có giá trị.

### 4.2. properties

Một property mô tả một key cụ thể:

~~~json
{
  "name": "acme.gateway.connect-timeout",
  "type": "java.time.Duration",
  "description": "Maximum time for establishing a connection.",
  "defaultValue": "2s",
  "sourceType": "example.gateway.GatewayProperties"
}
~~~

Đây là ví dụ minh họa của metadata hợp lệ về ý tưởng. Processor có thể sinh một tập thuộc tính/chi tiết khác đôi chút tùy kiểu đích và phiên bản Boot; khi rà soát hãy kiểm tra output thực tế, không kỳ vọng thứ tự JSON bất biến.

### 4.3. hints

Hints cung cấp gợi ý giá trị hoặc provider cho IDE:

~~~json
{
  "name": "acme.gateway.mode",
  "values": [
    {
      "value": "strict",
      "description": "Reject requests if the upstream is unavailable."
    },
    {
      "value": "best-effort",
      "description": "Allow degraded behavior when configured."
    }
  ]
}
~~~

**Hint không phải validation constraint**. Một IDE có thể đề xuất strict/best-effort, nhưng nếu ứng dụng nhận String tùy ý thì cần ràng buộc Java/enum/converter để runtime từ chối giá trị ngoài danh sách.

### 4.4. deprecated

Metadata có thể mô tả property được thay thế:

~~~json
{
  "name": "acme.gateway.old-timeout",
  "deprecation": {
    "level": "warning",
    "reason": "Use the new connection timeout property.",
    "replacement": "acme.gateway.connect-timeout",
    "since": "2.1.0"
  }
}
~~~

Deprecation là một tín hiệu cho người dùng và tooling. Không nên xem nó là cơ chế runtime tự chuyển key cũ sang key mới.

### 4.5. Metadata không chứa current value

Nếu production đang cấp:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT=12s
~~~

metadata vẫn có thể mô tả default 2s. Nó không đọc Environment của production và không biểu diễn giá trị runtime.

Muốn biết source thắng trong một tiến trình, cần diagnostic riêng có quyền truy cập phù hợp; **không ghi actual secret vào metadata**.

---

## 5. Sinh metadata bằng annotation processor

Spring Boot cung cấp artifact **spring-boot-configuration-processor**. Khi được cài trong annotation processing của quá trình compile, nó đọc các type/method **@ConfigurationProperties** và sinh metadata.

### 5.1. Maven

Với Maven Compiler Plugin và Spring Boot dependency management phù hợp, cấu hình ví dụ:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.12.1</version>
      <configuration>
        <annotationProcessorPaths>
          <path>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

**Chú ý phiên bản và dependency management:** đoạn trên dựa trên cách cấu hình của tài liệu Spring Boot 3.5 và Maven Compiler Plugin 3.12+; với toolchain khác, đặc biệt Maven Compiler Plugin mới hoặc Boot 4.x, kiểm tra cơ chế annotation processor tương ứng. Không sao chép một phiên bản plugin vào build đang được parent quản lý nếu nó xung đột chính sách dự án.

### 5.2. Gradle

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Nếu dự án dùng Kotlin source, cần cấu hình processor tương ứng với Kotlin toolchain (ví dụ kapt khi cần), không giả định Java annotationProcessor sẽ xử lý mọi lớp Kotlin.

### 5.3. Nếu dùng Lombok

Một dự án dùng Lombok để tạo getter/setter/constructor phải đảm bảo Lombok annotation processor hoạt động theo thứ tự phù hợp với configuration processor.

Nếu build không sinh metadata cho một field mà runtime Binder vẫn nhận, kiểm tra:

- Lombok có chạy trong compile không?
- Processor của Boot đã được cấu hình không?
- Các processor có thứ tự thích hợp không?
- Field có thể được phát hiện qua JavaBean getter/setter hoặc constructor không?
- Build đang dùng source class hay chỉ dependency đã compile?

Một test metadata artifact sẽ giúp phát hiện lỗi build kiểu này trước phát hành.

### 5.4. Không dùng dependency runtime để thay annotation processing

Chỉ thêm artifact vào runtime classpath không bảo đảm annotation processor được gọi trong build. Cần kiểm tra compile configuration thực sự kích hoạt processor.

Trong thư viện phát hành, điều quan trọng là **JAR cuối chứa metadata đúng**, không chỉ pom.xml hoặc build.gradle có dòng dependency đẹp.

---

## 6. Javadoc và mô tả của configuration properties

Một schema công khai cần mô tả dễ hiểu, không chỉ có tên và kiểu.

Với JavaBean:

~~~java
/**
 * Maximum time allowed to establish a TCP connection.
 * This does not include the full response time.
 */
private Duration connectTimeout = Duration.ofSeconds(2);
~~~

Processor có thể sử dụng Javadoc của field để tạo description khi source có sẵn tại compile time.

Với Java record, tài liệu Spring Boot khuyến nghị **class-level Javadoc và @param** cho mô tả các record component.

Ví dụ:

~~~java
/**
 * Retry behavior for the outbound client.
 *
 * @param maxAttempts Number of attempts, including the first call.
 * @param backoff Delay between successive attempts.
 */
public record Retry(
        int maxAttempts,
        Duration backoff
) {}
~~~

### 6.1. Một description tốt cần trả lời gì?

Không chỉ:

~~~text
Timeout value.
~~~

mà nên diễn đạt:

~~~text
Maximum time allowed to establish a connection to the upstream.
Use an explicit unit such as 2s or 250ms.
~~~

Khi mô tả về retry, cần nêu **maxAttempts có bao gồm lần gọi đầu tiên không**. Khi mô tả DataSize, cần nêu đơn vị/mặc định; khi mô tả boolean flag, cần nói hiệu ứng của true và false.

### 6.2. Không để secret trong description

Không viết:

~~~text
Production API key is abc-123-...
~~~

Description phải nói cách **cấp bí mật** và nơi tham khảo chính sách, không đưa giá trị thật vào source/Javadoc/build artifacts.

### 6.3. Không dùng Javadoc để tuyên bố một default không tồn tại

Nếu ghi “Default is 2s” trong mô tả mà runtime không có default tương ứng, tài liệu gây hiểu lầm. Cần đối chiếu **@DefaultValue**, field initializer, configuration file nền hoặc fallback logic thực tế.

---

## 7. Kiểm tra file metadata sinh ra trong build

Sau compile, metadata thường được tìm trong:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

đối với một bố cục Maven thông thường, hoặc:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

đối với một bố cục Gradle Java thông thường. Đường dẫn cụ thể có thể khác theo plugin/toolchain.

Các lệnh ví dụ:

~~~bash
./mvnw clean compile
~~~

hoặc:

~~~bash
./gradlew clean compileJava
~~~

Sau đó kiểm tra artifact:

~~~bash
jar tf target/my-library.jar
~~~

hoặc:

~~~bash
jar tf build/libs/my-library.jar
~~~

Trong một library JAR chuẩn, file metadata phải nằm ở **META-INF/spring-configuration-metadata.json**. Trong executable Spring Boot JAR, layout có thể đặt classes ở **BOOT-INF/classes/META-INF/**.

### 7.1. Điều cần kiểm tra ở metadata

- Tập key công khai cần hỗ trợ có xuất hiện không?
- Prefix được viết đúng không?
- Type có phù hợp với model Java không?
- Mô tả có rõ ý nghĩa không?
- Default value có đúng với runtime không?
- Hint có dùng đúng property name không?
- Deprecated property có reason và replacement khi cần không?
- Có key nội bộ/secret bị thêm thông tin không nên công bố không?
- Có property cũ đã xóa khỏi code nhưng vẫn đang xuất hiện do manual metadata không?
- Metadata có được đóng gói vào artifact mà người dùng thực sự tải về không?

Không nên assert **thứ tự** mọi phần tử JSON, vì format không yêu cầu thứ tự giống source code. Kiểm tra theo tên và thuộc tính quan trọng.

### 7.2. Metadata không phải schema bắt buộc

File JSON có thể chứa một property không còn được runtime bind nếu manual metadata bị lỗi thời. Ngược lại, Binder có thể nhận một key chưa được processor nhận diện do dynamic prefix hoặc binding thủ công.

**Đối chiếu metadata với bài test runtime**, không dùng metadata một mình làm bằng chứng “property này chạy đúng”.

---

## 8. Bổ sung manual metadata

Có tình huống processor không biết description/default, hoặc dự án có một key được đọc thủ công bằng Environment/Binder.

Tạo:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.gateway.connect-timeout",
      "description": "Maximum time to establish an upstream connection.",
      "defaultValue": "2s"
    },
    {
      "name": "acme.gateway.mode",
      "type": "java.lang.String",
      "description": "Gateway behavior when the upstream is unavailable."
    }
  ],
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        {
          "value": "strict",
          "description": "Reject requests if the upstream cannot be used."
        },
        {
          "value": "best-effort",
          "description": "Continue with the configured degraded path."
        }
      ]
    }
  ]
}
~~~

Ở đây connect-timeout được khai báo có default 2s **vì model Java đã có @DefaultValue("2s")** trong ví dụ ở trên. Nếu code không cung cấp default 2s, phải sửa manual metadata thay vì chỉ mong IDE gợi ý làm runtime có default.

### 8.1. Processor hợp nhất metadata

Annotation processor có thể hợp nhất nội dung từ additional metadata vào file kết quả. Nếu tên property trùng với key tự động phát hiện, các thuộc tính như description/default/deprecation có thể được bổ sung hoặc override theo quy tắc của phiên bản processor.

Nếu additional metadata khai báo key mà processor không tự phát hiện, nó có thể được đưa vào metadata tổng hợp như một property độc lập.

### 8.2. Gradle cần chú ý thứ tự task

Với một file additional metadata, tài liệu Spring Boot nêu rằng compileJava cần có resource sẵn khi annotation processor chạy. Một cấu hình thường được minh họa:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Nếu build hiện tại có thiết lập task dependency khác, dùng cơ chế phù hợp với Gradle version và plugin, rồi xác minh generated metadata. **Không chỉ giả định file trong src/main/resources tự được merge vào output theo mọi thứ tự build.**

### 8.3. Manual metadata không tự tạo property runtime

Nếu Java không đọc **acme.gateway.mode**, thêm key đó vào additional-spring-configuration-metadata.json chỉ làm IDE có thể gợi ý, **không làm Spring Boot tự sinh bean hoặc tự thực hiện logic mode**.

Khi rà soát release, property manual phải có một owner runtime rõ ràng: field Java, Binder code, Environment access hoặc extension tương ứng.

---

## 9. Hints cho enum, Map và đường dẫn

Metadata hints có thể tăng trải nghiệm của người viết cấu hình, nhất là khi một String chỉ chấp nhận một tập giá trị.

Ví dụ:

~~~json
{
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        { "value": "strict", "description": "Fail closed." },
        { "value": "best-effort", "description": "Allow degraded mode." }
      ]
    }
  ]
}
~~~

### 9.1. Hints không phải allowlist runtime

Nếu code đích là:

~~~java
String mode
~~~

không có validation, Binder có thể vẫn nhận một chuỗi khác.

Để thực sự giới hạn, cân nhắc enum:

~~~java
public enum GatewayMode {
    STRICT,
    BEST_EFFORT
}
~~~

và khai báo component:

~~~java
GatewayMode mode
~~~

hoặc dùng custom validation được tích hợp đúng.

### 9.2. Map key và Map value hints

Với property dạng Map, metadata format hỗ trợ gợi ý cho những đường dẫn có hậu tố như **.keys** hoặc **.values** khi phù hợp.

Ví dụ nếu một Map<String, String> có các key được chuẩn hóa, IDE có thể gợi ý key cho người dùng. Tuy vậy, key có thể được sinh động bởi tenant/module, khi đó không nên tạo một danh sách cứng không còn đúng.

### 9.3. Đừng biến hints thành tài liệu nghiệp vụ duy nhất

Một IDE có thể không đọc hints hoặc người dùng viết YAML trong một công cụ không hỗ trợ Spring Boot metadata. Các values quan trọng vẫn phải xuất hiện trong README hoặc tài liệu triển khai.

---

## 10. Deprecated properties và migration trước phát hành

Đổi tên key là một thay đổi contract.

Ví dụ tên cũ:

~~~text
acme.gateway.connection-timeout-ms
~~~

Tên mới:

~~~text
acme.gateway.connect-timeout
~~~

Tài liệu phát hành cần xác định:

- Key cũ còn hoạt động không?
- Nếu hoạt động, nó được chuyển đổi như thế nào?
- Nếu cả hai key xuất hiện, key nào thắng?
- Đơn vị cũ và mới có giống nhau không?
- Có phiên bản tối thiểu và phiên bản loại bỏ key cũ không?
- Làm sao quan sát một deployment còn dùng tên cũ mà không in value?

### 10.1. @DeprecatedConfigurationProperty

Một JavaBean getter có thể dùng:

~~~java
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@Deprecated
@DeprecatedConfigurationProperty(
        replacement = "acme.gateway.connect-timeout",
        since = "2.1.0"
)
public Duration getOldTimeout() {
    return this.connectTimeout;
}
~~~

Đây là ví dụ về metadata deprecated của một accessor, không phải một thiết kế JavaBean đầy đủ. Nếu muốn key cũ vẫn bind được, code phải thực sự giữ binding/accessor/alias tương ứng trong giai đoạn migration.

### 10.2. Metadata deprecated không phải automatic alias

Chỉ viết:

~~~json
{
  "deprecation": {
    "replacement": "acme.gateway.connect-timeout"
  }
}
~~~

không có nghĩa khi operator cấp key cũ thì Binder tự chuyển nó sang key mới.

Phải giữ compatibility trong JavaBean, thêm một lớp mapping rõ ràng hoặc yêu cầu người dùng nâng cấp cấu hình theo chính sách phát hành.

### 10.3. warning và error

Metadata deprecation có thể mang level **warning** hoặc **error** theo format. Ý nghĩa intended của error là property không còn được quản lý/bind, nhưng đó là mô tả cho tooling; cần đảm bảo implementation runtime phù hợp.

Không cố duy trì key deprecated ở metadata trong khi code âm thầm chấp nhận một hành vi hoàn toàn khác.

### 10.4. Tài liệu migration mẫu

| Phiên bản | Tên property | Chính sách |
| --- | --- | --- |
| 2.0.x | connection-timeout-ms | Tên cũ |
| 2.1.x | connect-timeout | Giới thiệu tên mới; tên cũ deprecated |
| 2.2.x | connect-timeout | Tên cũ có thể còn hỗ trợ theo contract |
| 3.0.x | connect-timeout | Có thể bỏ tên cũ sau thông báo breaking change |

Các số phiên bản trong bảng là **ví dụ**, không phải lịch sử của một thư viện thực tế. Trong dự án thật, công bố các phiên bản và thời hạn chính xác.

---

## 11. Default runtime và default trong metadata

Một trong những lỗi phát hành dễ bỏ sót nhất là metadata ghi một default, nhưng runtime có default khác.

Các nguồn default phổ biến:

1. Giá trị trong application.yml đóng gói cùng ứng dụng.
2. @DefaultValue trên record component/constructor binding.
3. Field initializer trong JavaBean.
4. Default do constructor hoặc factory đưa vào.
5. SpringApplication defaultProperties.
6. Một low-priority PropertySource do thư viện thêm.
7. Fallback khi Binder không bound hoặc service xử lý riêng.

### 11.1. Đối chiếu một default

Với Java:

~~~java
@DefaultValue("2s") Duration connectTimeout
~~~

và manual metadata:

~~~json
{
  "name": "acme.gateway.connect-timeout",
  "defaultValue": "2s"
}
~~~

hai phía nhất quán.

Nếu application-prod.yml cung cấp 5s, default ở metadata không thay đổi; người vận hành vẫn có thể nhận 5s tại runtime.

### 11.2. DefaultValue không có nghĩa object con luôn tồn tại

Một record có nested component không nhất thiết được tạo nếu cả nhánh không được khai báo. Hành vi phụ thuộc constructor binding, default và phiên bản Boot. Nếu nested object bắt buộc tồn tại, dùng @NotNull kết hợp @Valid hoặc một chính sách khởi tạo rõ.

### 11.3. Default từ code có thể khó suy ra tự động

Annotation processor chỉ có thể phát hiện một số default theo heuristic từ source. Nó không giải được mọi biểu thức, constant từ class khác hoặc collection được xây động.

Nếu metadata thiếu default vì processor không thể suy ra, có thể bổ sung manual metadata, **nhưng chỉ khi biết chắc default runtime**.

### 11.4. Không đặt default “hợp lệ giả” cho secret

Ví dụ không nên:

~~~yaml
acme:
  credentials:
    api-key: "placeholder-key-for-production"
~~~

vì nó có thể làm ứng dụng khởi động dù operator quên cấu hình secret thật.

Với giá trị bắt buộc và nhạy cảm, thích hợp hơn là để thiếu gây lỗi có kiểm soát, và trong tài liệu chỉ ghi placeholder mang tính hướng dẫn, không đưa giá trị dùng được.

---

## 12. Validation là hợp đồng runtime, không phải thuộc tính JSON

Một record chứa:

~~~java
@Validated
@ConfigurationProperties(prefix = "acme.gateway")
public record GatewayProperties(
        @NotBlank String baseUrl,
        @Min(1) int maxAttempts
) {}
~~~

Metadata có thể nói String/int và mô tả ý nghĩa, nhưng không nên xem metadata tự động áp dụng toàn bộ @NotBlank/@Min trong runtime.

Để validation hoạt động khi binding bean, cần:

- Có Jakarta Bean Validation provider tương thích.
- Bean @ConfigurationProperties được đăng ký đúng.
- Có @Validated khi tích hợp yêu cầu.
- Có @Valid ở những nhánh nested cần cascade.
- Dùng constraint đúng kiểu dữ liệu.
- Có bài test startup invalid để chứng minh tích hợp thực sự chạy.

### 12.1. Dependency validation

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Khi dùng Spring Boot 3, import các constraint từ **jakarta.validation**, không sao chép **javax.validation** của dự án Boot 2 mà không kiểm tra compatibility.

### 12.2. @Valid không đồng nghĩa @NotNull

~~~java
@Valid Retry retry
~~~

chỉ yêu cầu cascade khi có object.

Nếu retry bắt buộc:

~~~java
@Valid @NotNull Retry retry
~~~

Mức test cần có case vắng hẳn nhánh retry, không chỉ case retry.maxAttempts=0.

### 12.3. Duration và DataSize cần điều kiện đúng kiểu

**@Min(1)** không nên được áp trực tiếp lên Duration như một số millis rồi kỳ vọng Jakarta Validation tự hiểu. Có thể dùng custom constraint hoặc một invariant thích hợp để yêu cầu Duration dương.

Đối với int maxAttempts, @Min(1) phù hợp. Đối với String baseUrl, @NotBlank có thể phát hiện rỗng nhưng không bảo đảm đó là URL có thể kết nối.

### 12.4. Cấu hình đúng kiểu chưa chắc hợp lệ nghiệp vụ

Một value **max-attempts=0** có thể chuyển thành int thành công, nhưng vi phạm @Min(1).

Một value **max-attempts=many** có thể thất bại ở conversion trước khi validation.

Cần test hai loại lỗi riêng; không gộp tất cả thành “validation thất bại”.

---

## 13. Bốn mức kiểm thử cấu hình trước phát hành

Một chiến lược có thể chia thành:

| Mức | Cơ chế được thử | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Java object | Constructor/invariant/validator thủ công | Nhanh, lỗi rõ | Không kiểm tra binding |
| Binder | MapConfigurationPropertySource + Binder | Tên, kiểu, nested, List/Map | Không tự kiểm tra bean lifecycle |
| ApplicationContextRunner | Context nhỏ, bean registration, validation, conditions | Kiểm tra cơ chế Spring Boot cục bộ | Không mô phỏng mọi bootstrap behavior |
| Full SpringApplication / @SpringBootTest | Config Data, profile, imports, EPP, wiring | Xác nhận đường triển khai thật | Chạy nặng, nhiều thành phần |

**Chọn mức thấp nhất chứng minh được hành vi cần kiểm tra.** Một test Binder xanh không chứng minh spring.config.import hoạt động; một @SpringBootTest xanh với property override không chứng minh file production có giá trị ấy.

### 13.1. Test object

Nếu record có compact constructor chuẩn hóa List:

~~~java
public record EndpointGroup(List<String> hosts) {
    public EndpointGroup {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

JUnit test thuần có thể kiểm tra defensive copy mà không cần Spring.

### 13.2. Test Binder

Xác nhận Spring Boot chuyển strings sang Java type và map nested paths.

### 13.3. Test ApplicationContextRunner

Xác nhận @EnableConfigurationProperties, @Validated, @ConditionalOnProperty và auto-configuration đã hoạt động trong context.

### 13.4. Full app test

Xác nhận application.yml, profile, external location, EPP discovery, Config Data imports và integration theo triển khai mục tiêu.

---

## 14. Binder test: tên canonical và chuyển đổi kiểu

Ví dụ test rút gọn:

~~~java
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayBinderTest {

    @Test
    void bindsNestedSettings() {
        Map<String, Object> values = Map.of(
            "acme.gateway.base-url", "https://api.example.test",
            "acme.gateway.connect-timeout", "4s",
            "acme.gateway.retry.max-attempts", "3",
            "acme.gateway.retry.backoff", "250ms",
            "acme.gateway.endpoints[0].name", "primary",
            "acme.gateway.endpoints[0].host", "edge.example.test",
            "acme.gateway.endpoints[0].port", "8080"
        );

        Binder binder = new Binder(
            new MapConfigurationPropertySource(values)
        );

        GatewayProperties result = binder
            .bind("acme.gateway", GatewayProperties.class)
            .orElseThrow();

        assertThat(result.connectTimeout())
            .isEqualTo(Duration.ofSeconds(4));
        assertThat(result.retry().maxAttempts())
            .isEqualTo(3);
        assertThat(result.endpoints()).hasSize(1);
    }
}
~~~

Test này chứng minh Binder và conversion của Duration/nested List trong dữ liệu thử nghiệm. Nó không kiểm tra YAML parser đã đọc tài liệu đúng hay @Validated tự được gọi bởi Spring ApplicationContext.

### 14.1. Test lỗi conversion

Một test khác cấp:

~~~text
acme.gateway.retry.max-attempts=many
~~~

và khẳng định bind thất bại theo cơ chế phù hợp. Dữ liệu **many** không phải int, nên không đổ lỗi cho @Min(1).

### 14.2. Test prefix sai

Cấp:

~~~text
acme.gateway.max-attempts=3
~~~

thay vì:

~~~text
acme.gateway.retry.max-attempts=3
~~~

rồi quan sát kết quả binding. Điều này giúp phát hiện lỗi thụt lề/cấu trúc khi key đã được làm phẳng.

### 14.3. Test relaxed binding có phạm vi

Canonical:

~~~text
acme.gateway.connect-timeout
~~~

Java:

~~~text
connectTimeout
~~~

Biến môi trường chuẩn:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT
~~~

Binder test từ Map không đồng nghĩa đã kiểm tra một OS environment variable thật; test cấp process hoặc một PropertySource mô phỏng system environment sẽ phù hợp hơn nếu muốn xác nhận env mapping.

---

## 15. ApplicationContextRunner test: bean và validation

Một test nhỏ cho cấu hình:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class
            ))
            .withUserConfiguration(Config.class);

    @Test
    void acceptsValidGateway() {
        runner.withPropertyValues(
            "acme.gateway.base-url=https://api.example.test",
            "acme.gateway.connect-timeout=2s",
            "acme.gateway.retry.max-attempts=3",
            "acme.gateway.retry.backoff=250ms",
            "acme.gateway.endpoints[0].name=primary",
            "acme.gateway.endpoints[0].host=edge.example.test",
            "acme.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GatewayProperties.class);
        });
    }

    @Test
    void rejectsInvalidNestedRetry() {
        runner.withPropertyValues(
            "acme.gateway.base-url=https://api.example.test",
            "acme.gateway.connect-timeout=2s",
            "acme.gateway.retry.max-attempts=0",
            "acme.gateway.retry.backoff=250ms",
            "acme.gateway.endpoints[0].name=primary",
            "acme.gateway.endpoints[0].host=edge.example.test",
            "acme.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class Config {}
}
~~~

Các import JUnit Jupiter/Test và các assertion ở trên được trình bày rút gọn để tập trung vào ý tưởng. Dự án cần **spring-boot-starter-test**, validation provider và những dependencies tương ứng với phiên bản Spring Boot đang dùng.

### 15.1. Không chỉ assert hasFailed

Một context có thể fail vì thiếu bean hoặc lỗi classpath. Khi test mục tiêu là @Min(1), nên kiểm tra nguyên nhân lỗi thuộc validation của Retry, theo API/cause chain được hỗ trợ, nhưng tránh assert nguyên văn toàn bộ log thông báo vốn có thể khác giữa các phiên bản.

### 15.2. Test missing branch

Thêm case chỉ có base-url và endpoints, hoàn toàn thiếu retry. Với @NotNull Retry, context phải từ chối cấu hình nếu binder không cung cấp default Retry.

### 15.3. Test conditional beans

Nếu thư viện có:

~~~java
@ConditionalOnProperty(
    prefix = "acme.gateway",
    name = "enabled",
    havingValue = "true"
)
~~~

hãy test true, false và absent bằng ApplicationContextRunner. Không cần khởi động toàn bộ web server để kiểm tra một condition cục bộ.

---

## 16. Full application test cho Config Data và profile

Những hành vi sau phụ thuộc SpringApplication bootstrap:

- application.yml và application-prod.yml.
- Config Data import/location.
- Profile activation và profile-specific documents.
- External location hoặc configtree.
- EnvironmentPostProcessor được discover qua spring.factories.
- JVM system properties, command-line override và một số lifecycle event.
- Wiring giữa nhiều auto-configuration/module.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("release-smoke")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ReleaseConfigurationSmokeTest {

    @Autowired
    GatewayProperties gateway;

    @Test
    void gatewayIsBoundAfterBootstrap() {
        assertThat(gateway.baseUrl()).isNotBlank();
        assertThat(gateway.retry().maxAttempts())
            .isGreaterThanOrEqualTo(1);
    }
}
~~~

Cần đặt file test profile an toàn với đầy đủ các property bắt buộc, ví dụ application-release-smoke.yml trong test resources. Đừng để test vô tình đọc credentials production hoặc gọi endpoint thật.

### 16.1. Khi cần kiểm tra precedence

Giả sử application.yml có 2s, profile release-smoke có 5s và test không override trực tiếp. Assertion gateway.connectTimeout() bằng 5s giúp xác nhận profile-specific Config Data được nạp.

Nếu test dùng:

~~~java
@SpringBootTest(properties = "acme.gateway.connect-timeout=7s")
~~~

thì kết quả 7s chủ yếu chứng minh test override, không còn là bằng chứng file profile chứa giá trị 7s.

### 16.2. Config Data import

Nếu ứng dụng dùng:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

cần test location thông qua thư mục tạm/test-controlled, không trỏ vào file cá nhân trên máy developer. Với file bắt buộc, test cả missing-resource behavior.

### 16.3. EPP discovery

Một unit test gọi trực tiếp EnvironmentPostProcessor không chứng minh file **META-INF/spring.factories** đúng. Khi release thay bootstrap extension hoặc nâng cấp Boot major version, hãy có test SpringApplication xác nhận PropertySource được thêm như dự kiến.

---

## 17. Ma trận trường hợp tối thiểu trước phát hành

Một bảng giúp team tránh kiểm tra thiếu hoặc lặp:

| Case | Input | Kỳ vọng | Mức phù hợp |
| --- | --- | --- | --- |
| Happy path | Cấu hình đầy đủ | Bean được bind đúng | Binder/Runner |
| Missing base-url | Không khai báo | @NotBlank fail | Runner |
| Blank base-url | Chuỗi rỗng | Validation fail | Runner |
| Missing retry | Không có nhánh retry | @NotNull fail | Runner |
| Invalid attempts | max-attempts=0 | @Min fail | Runner |
| Wrong type | max-attempts=many | Conversion fail | Binder |
| Duration units | connect-timeout=250ms | Duration đúng | Binder |
| Nested endpoint | host rỗng | Cascaded validation fail | Runner |
| List empty | endpoints rỗng | @NotEmpty fail | Runner |
| Kebab/camel | connect-timeout -> connectTimeout | Bind đúng | Binder |
| Env canonical | ACME_GATEWAY_CONNECTTIMEOUT | Override đúng | Process/env integration |
| Profile override | File nền 2s, prod 5s | Giá trị cuối 5s | Full app |
| Import optional | File không tồn tại | Startup theo policy | Full app |
| Import required | File không tồn tại | Fail-fast | Full app |
| Disabled feature | enabled=false | Bean liên quan vắng | Runner |
| Deprecated key | Chỉ cấp key cũ | Theo compatibility policy | Runner/full app |
| Both old/new | Hai tên cùng tồn tại | Precedence đã công bố | Full app |
| Metadata packaging | Build artifact | JSON có key công khai | Artifact verification |
| Secret redaction | Giá trị giả | Không lộ trong log/Actuator | Security integration |

Ma trận phải được điều chỉnh theo rủi ro thật. Nếu service không có deprecated key hoặc dynamic source, không cần tạo test giả chỉ để lấp ô.

---

## 18. Kiểm thử metadata là một bước riêng

Các test runtime thông thường không phát hiện một lỗi như annotation processor bị vô hiệu hóa trong CI.

Một JAR có thể chạy đúng nhưng thiếu **META-INF/spring-configuration-metadata.json**, khiến người dùng thư viện mất autocomplete và cảnh báo deprecated.

Do đó cần bước kiểm tra build artifact:

1. Build library/application như quy trình phát hành thực.
2. Xác nhận metadata file có trong artifact cuối.
3. Parse JSON đúng định dạng.
4. Xác nhận các property name bắt buộc có mặt.
5. Xác nhận mô tả và deprecated replacement quan trọng.
6. Phát hiện manual metadata công bố key không tồn tại hoặc lỗi thời.
7. Không so sánh raw JSON bằng thứ tự toàn bộ array.

### 18.1. Ví dụ assertion cần có

~~~text
META-INF/spring-configuration-metadata.json exists
properties contains acme.gateway.base-url
properties contains acme.gateway.connect-timeout
properties contains acme.gateway.retry.max-attempts
properties contains acme.gateway.retry.backoff
property connect-timeout documents expected runtime default
removed/deprecated keys follow release contract
~~~

### 18.2. Đừng dựa riêng vào ClassLoader.getResource

Nếu trong test classpath có nhiều dependency chứa file **spring-configuration-metadata.json**, một lời gọi lấy “resource đầu tiên” có thể trả metadata của thư viện khác.

Để test artifact của module đang phát hành, hãy kiểm tra **build output hoặc đúng JAR được build**, thay vì bất kỳ metadata file nào tình cờ được classloader tìm thấy.

### 18.3. Metadata sinh ra có thể thiếu key dynamic

Nếu code dùng:

~~~java
Binder.get(environment).bind(dynamicPrefix, SomeType.class)
~~~

annotation processor không nhất thiết biết mọi prefix được chọn tại runtime. Nếu đó là public contract, cần manual metadata hoặc tài liệu có schema rõ và test cho các prefix được phép.

---

## 19. Tài liệu cấu hình dành cho người sử dụng

Một README tốt phải cho người vận hành biết cách sử dụng property mà không cần đọc source Java.

Một cấu trúc đề xuất:

~~~text
Configuration Reference
├── Purpose and module ownership
├── Supported Spring Boot versions
├── Quick start (minimal YAML)
├── Properties table
├── Environment variable names
├── Defaults and required fields
├── Nested List/Map examples
├── Profiles and override order
├── Secret handling
├── Validation and startup errors
├── Deprecated keys and migration
├── Production checklist
└── Troubleshooting
~~~

### 19.1. Bảng thuộc tính mẫu

| Property | Type | Required | Default | Ý nghĩa |
| --- | --- | --- | --- | --- |
| acme.gateway.base-url | String | Có | Không | URL gốc upstream |
| acme.gateway.connect-timeout | Duration | Không | 2s | Giới hạn thiết lập kết nối |
| acme.gateway.retry.max-attempts | int | Có | Không | Số lần thử ít nhất 1 |
| acme.gateway.retry.backoff | Duration | Có | Không | Thời gian chờ giữa các lần |
| acme.gateway.endpoints | List | Có | Không | Danh sách endpoint không rỗng |

Đây là bảng theo **schema ví dụ** trong bài; nếu project có rule bổ sung (chẳng hạn backoff phải dương), phải ghi rõ và có validator/test thực thi rule đó.

### 19.2. Required là thuộc tính nghiệp vụ, không phải kiểu Java

Một field Java kiểu int không tự thể hiện “operator buộc phải khai báo”. Một int có thể nhận 0 khi vắng dữ liệu tùy binding path. Nếu muốn phân biệt missing và value 0, dùng Integer kết hợp @NotNull/@Min hoặc một invariant cụ thể.

Bảng Required phải phản ánh cách ứng dụng xử lý dữ liệu thật, không chỉ suy luận từ tên biến.

### 19.3. Default nên nêu đơn vị

Đừng ghi:

~~~text
connect-timeout default = 2000
~~~

mà không biết milliseconds hay seconds. Ghi rõ **2s** hoặc **2000ms** và kiểm tra với Duration conversion thực tế.

### 19.4. Documentation samples không có credential thật

Trong YAML mẫu chỉ dùng domain **example.test** và placeholder an toàn. Không copy địa chỉ nội bộ, production hostname, token hoặc password thực vào README.

---

## 20. Ví dụ YAML tối thiểu và ví dụ đầy đủ

### 20.1. Mẫu tối thiểu

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    retry:
      max-attempts: 3
      backoff: 300ms
    endpoints:
      - name: primary
        host: edge.example.test
        port: 8080
~~~

Trong ví dụ này **connect-timeout** vắng mặt và record có @DefaultValue("2s").

### 20.2. Mẫu đầy đủ

~~~yaml
acme:
  gateway:
    base-url: "https://api.example.test"
    connect-timeout: 5s
    retry:
      max-attempts: 5
      backoff: 500ms
    endpoints:
      - name: primary
        host: edge-a.example.test
        port: 8080
      - name: secondary
        host: edge-b.example.test
        port: 8081
~~~

Dùng các ví dụ khác nhau để nêu ý nghĩa “tối thiểu” và “tùy chỉnh”. Không đặt một field bắt buộc nhưng bị thiếu trong ví dụ tối thiểu, vì người dùng có thể copy và gặp lỗi startup không rõ nguyên nhân.

### 20.3. Không đưa mọi tổ hợp profile vào một sample

Nếu có local, staging, prod, hãy cung cấp một ví dụ cơ sở và hướng dẫn override riêng. Quá nhiều YAML trong một file tài liệu có thể khiến người sử dụng nhầm đoạn nào là sample thực sự chạy được.

---

## 21. Bảng tên biến môi trường và CLI

Đường dẫn canonical:

~~~text
acme.gateway.connect-timeout
~~~

Tên biến môi trường chuẩn:

~~~text
ACME_GATEWAY_CONNECTTIMEOUT
~~~

Quy tắc chuyển canonical sang tên env của Spring Boot:

1. Dấu chấm thành dấu gạch dưới.
2. Dấu gạch ngang bị loại bỏ.
3. Viết hoa.

Tương tự:

| Canonical | Environment variable |
| --- | --- |
| acme.gateway.base-url | ACME_GATEWAY_BASEURL |
| acme.gateway.connect-timeout | ACME_GATEWAY_CONNECTTIMEOUT |
| acme.gateway.retry.max-attempts | ACME_GATEWAY_RETRY_MAXATTEMPTS |
| acme.gateway.retry.backoff | ACME_GATEWAY_RETRY_BACKOFF |

Với List indices, cần đối chiếu cách biểu diễn chỉ số theo nguồn thực tế; không nên tự áp dụng phép đổi đơn giản mà không test.

### 21.1. CLI override

~~~bash
java -jar gateway.jar \
  --acme.gateway.connect-timeout=7s
~~~

### 21.2. JVM system property

~~~bash
java -Dacme.gateway.connect-timeout=7s \
  -jar gateway.jar
~~~

### 21.3. Environment variable

~~~bash
ACME_GATEWAY_CONNECTTIMEOUT=7s java -jar gateway.jar
~~~

Các cách trên có cơ chế nguồn khác nhau. Nên mô tả rõ ưu tiên của những nguồn mà deployment thực sự cho phép. Không chỉ cung cấp một lệnh copy-paste rồi để operator đoán nguồn nào sẽ thắng.

### 21.4. Không dùng CLI để truyền secret raw

Command-line arguments có thể được ghi trong history, process listing hoặc logging. Đối với secret, ưu tiên secret injection được nền tảng bảo vệ, không hướng dẫn người dùng paste token thật vào lệnh shell ví dụ.

---

## 22. Thứ tự ưu tiên và profile trong tài liệu

Những nguồn cấu hình thường gặp:

- application.yml trong JAR.
- application-{profile}.yml.
- File ngoài JAR.
- OS environment variables.
- JVM system properties.
- Command-line arguments.
- Config Data imports.
- Nguồn custom như EnvironmentPostProcessor, TestPropertySource hoặc DynamicPropertySource.

**Thứ tự ưu tiên của Spring Boot được quy định theo từng loại nguồn**, và extension/test overrides có thể làm thứ tự thực tế khác. README nên nêu nguồn được hỗ trợ và đưa liên kết tới tài liệu externalized configuration của đúng phiên bản Boot.

### 22.1. Minh họa profile override

~~~yaml
# application.yml
acme:
  gateway:
    connect-timeout: 2s
~~~

~~~yaml
# application-prod.yml
acme:
  gateway:
    connect-timeout: 5s
~~~

Khi profile prod hoạt động, profile-specific config có thể ghi đè giá trị nền theo Config Data precedence.

### 22.2. Không coi List được ghép tự động

Nếu file nền có hai endpoint và file prod khai báo List một endpoint, Spring Boot thường dùng List ở nguồn ưu tiên cao thay vì nối hai danh sách. Điều này cần có ví dụ và test nếu danh sách endpoint là phần thiết yếu.

### 22.3. Map có thể hợp nhất key

Map thường có khả năng kết hợp key từ nhiều PropertySource, trong khi key trùng được giải quyết theo precedence. Nếu key Map chứa dấu chấm hoặc ký tự đặc biệt, có thể cần bracket notation để giữ nguyên.

### 22.4. Đổi profile có thể làm thay bộ giá trị bắt buộc

Một test local pass không chứng minh prod pass. Trước phát hành, nên có smoke test với các profile được hỗ trợ và dữ liệu giả phù hợp.

---

## 23. Config Data import và external location

Một tài liệu sử dụng có thể cần hướng dẫn người dùng nạp file ngoài:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

Từ **optional:** giúp cho phép location vắng mặt theo cơ chế Config Data.

Nếu file bắt buộc, dùng location không optional và mô tả điều kiện fail-fast phù hợp. Không mô tả một file là optional trong README nếu code hoặc Config Data đang yêu cầu bắt buộc.

### 23.1. Đường dẫn tương đối

Đường dẫn ./config có thể phụ thuộc working directory khi tiến trình khởi động. Với container/deployment, tài liệu phải quy định mount path/working directory hoặc sử dụng đường dẫn được nền tảng quản lý rõ.

### 23.2. Không nhập nhằng giữa spring.config.import và location

**spring.config.import** dùng để import tài liệu cấu hình theo ngữ cảnh Config Data. **spring.config.location** và **spring.config.additional-location** điều chỉnh location search theo cơ chế riêng.

Nếu tài liệu hướng dẫn đổi location, cần nêu rằng một số property điều khiển Config Data phải được cấp rất sớm, ví dụ qua env/system/CLI, chứ không thể thay sau khi quá trình nạp đã hoàn tất.

### 23.3. File từ nguồn không tin cậy

Không tự động import hoặc parse một file tùy ý do request user gửi vào mà không kiểm soát. Cần bảo vệ đường dẫn, permission và định dạng theo chính sách ứng dụng.

---

## 24. Tài liệu về secrets

Mỗi key nhạy cảm cần một chính sách:

- Ai/ứng dụng nào được phép cấp?
- Nguồn được phép là secret store, Kubernetes Secret, mounted file hay environment injection?
- Có cần file permission đặc biệt?
- Có thể rotate khi runtime hay phải restart?
- Khi vắng secret, ứng dụng fail-fast hay bỏ module?
- Khi validation fail, log được phép chứa thông tin gì?
- Actuator endpoints có thể cho người nào xem metadata?
- Secret có được phép xuất hiện trong startup diagnostics không?

### 24.1. Một ví dụ tài liệu an toàn

~~~text
ACME_GATEWAY_APIKEY

Purpose:
  Credential used to authenticate with the upstream provider.

Required:
  Only when upstream authentication is enabled.

Supply:
  Through the organization's secret delivery mechanism.

Do not:
  Commit the actual value to application.yml, README, screenshots,
  CI job logs or incident tickets.

Rotation:
  Follow the deployment's restart/refresh policy.
~~~

Không ghi giá trị thật và không cung cấp một “secret mặc định” trong source code.

### 24.2. Không expose Actuator env/configprops công khai

Những endpoint này có thể giúp chẩn đoán, nhưng cần access control và sanitization. Không bật **show-values=always** trong production chỉ để xác minh một timeout. Metadata như source names và paths cũng có thể có tính nhạy cảm.

### 24.3. Test không rò rỉ

Dùng secret giả như **dummy-test-key**, kiểm tra log và error response không chứa chuỗi này. Không đem token thật vào test fixtures chỉ để chứng minh masking.

---

## 25. Thiết kế thông báo lỗi cấu hình

Khi cấu hình thiếu hoặc sai, một startup failure rõ ràng giúp rút ngắn thời gian xử lý.

Ví dụ thuộc tính:

~~~text
acme.gateway.retry.max-attempts
~~~

bị khai báo 0.

Thông báo hữu ích về mặt ý nghĩa:

~~~text
Configuration validation failed.
Property: acme.gateway.retry.max-attempts
Constraint: must be greater than or equal to 1
~~~

Ví dụ này chỉ minh họa thông tin, không khẳng định đó là log nguyên văn của mọi phiên bản.

### 25.1. Không log rejected value nếu có thể là secret

Một lỗi parser/conversion có thể chứa raw input trong exception chain. Cần kiểm soát việc đưa các exception từ bootstrap vào log/ticket và không tự tạo message:

~~~java
"Invalid property " + key + "=" + value
~~~

vì key và value có thể thuộc nhóm secret.

### 25.2. Phân loại lỗi

| Loại lỗi | Dấu hiệu | Cách điều tra |
| --- | --- | --- |
| Missing | Không có property bắt buộc | Prefix/source/validation |
| Type conversion | Không chuyển được String sang Java type | Binder & kiểu |
| Bean Validation | Giá trị đúng kiểu nhưng vi phạm constraint | @Validated/@Valid |
| Wrong profile | File profile mong muốn không nạp | Config Data |
| Precedence | Key từ nguồn khác ghi đè | PropertySource order |
| Metadata missing | IDE không gợi ý dù code chạy | Annotation processor/JAR |
| Bean registration | Không inject được properties bean | Scan/EnableConfigurationProperties |
| Deprecated key | Deployment dùng tên cũ | Migration policy |

Trước khi phát hành, tài liệu nên nói người vận hành tìm thông tin chẩn đoán ở đâu mà không yêu cầu dump Environment.

---

## 26. Quy trình review trước release: thay đổi ở code

Với một pull request sửa cấu hình:

1. Xác định prefix và các property public bị thêm/sửa/bỏ.
2. Xác định module owner.
3. Kiểm tra Java type, constructor/default và nested model.
4. Xác định ràng buộc bắt buộc/optional.
5. Xem thay đổi có làm mất backward compatibility không.
6. Kiểm tra conversion units, list/map semantics và source precedence.
7. Bổ sung Javadoc hoặc manual metadata.
8. Bổ sung test ở mức thấp nhất chứng minh được behavior.
9. Bổ sung test tích hợp nếu thay profile/Config Data/bootstrap.
10. Cập nhật README, deployment samples, migration guide.
11. Đánh giá secret classification và logging.
12. Kiểm tra artifact cuối có metadata tương ứng.

Đây là **quy trình kỹ thuật của một release**, không phải một lời mời đi qua checklist nội dung một cách hình thức.

### 26.1. Một property mới không phải lúc nào cũng cần tất cả test

Nếu thêm một boolean feature flag cố định, test điều kiện bean ở ApplicationContextRunner có thể đủ cho logic chính. Nếu thêm external Config Data import, cần integration test khởi động. Nếu thêm record với List nested, cần Binder/validation tests.

Chọn test theo thay đổi thật.

---

## 27. Quy trình review trước release: thay đổi ở build

Build pipeline cần xác nhận:

- Annotation processor chạy với phiên bản đúng.
- Metadata được sinh đúng và không rỗng vì vô tình tắt annotation processing.
- Manual metadata được merge theo cơ chế của processor.
- JAR phát hành chứa metadata.
- Version của module và dependency Spring Boot tương thích.
- Tests chạy trong môi trường cô lập.
- Nếu thư viện hỗ trợ nhiều major version Boot, có ma trận compatibility phù hợp.
- Không có secret trong resource/package/test report.
- Release notes mô tả breaking changes.

### 27.1. Gradle và Maven không nhất thiết có cùng task names

Đừng copy lệnh Gradle sang pipeline Maven hoặc ngược lại. Ghi rõ build tool và JDK target được hỗ trợ.

### 27.2. Một bản build local không thay thế artifact CI

Nếu local build sinh metadata nhưng artifact release được build bằng profile/plugin khác, cần kiểm tra **artifact được phát hành** chứ không chỉ thư mục build local.

### 27.3. JAR metadata và executable JAR

Trong library JAR, metadata thường ở META-INF. Trong Spring Boot executable JAR, có thể nằm dưới BOOT-INF/classes/META-INF. Đối với các thư viện lồng trong BOOT-INF/lib, resource thuộc JAR con.

Đường dẫn archive phải được kiểm tra theo loại artifact, không dùng một quy tắc duy nhất cho mọi packaging mode.

---

## 28. Quy trình review trước release: tài liệu

Tài liệu cần phản ánh cả góc nhìn lập trình và vận hành:

**Góc nhìn developer:** class/record nào bind, dependency nào cần có, profile nào dùng cho test, ví dụ YAML và Java.

**Góc nhìn operator:** tối thiểu phải cấp gì, cách override qua env/CLI, default và đơn vị, khi nào restart, xử lý missing/invalid, cách cấp secret.

**Góc nhìn người nâng cấp:** key nào đổi tên, default nào đổi, behavior nào breaking, có alias không, thời hạn loại bỏ.

**Góc nhìn support:** cách xác định source thắng, thông tin nào an toàn để đưa vào ticket và lỗi startup sẽ được phân loại thế nào.

### 28.1. Không để docs thuộc về một team không rõ

Mỗi nhóm cấu hình nên có owner để trả lời câu hỏi về default, hợp đồng compatibility và rủi ro. Nếu không có owner, key có thể tồn tại nhiều năm mà không ai dám loại bỏ.

### 28.2. Docs và metadata cần dùng cùng một canonical name

Nếu README viết **acme.gateway.connectTimeout** nhưng metadata là **acme.gateway.connect-timeout**, người vận hành có thể chọn tên không nhất quán. Nên dùng kebab-case canonical trong bảng docs và ví dụ.

### 28.3. Giữ các ví dụ chạy được

Ví dụ tối thiểu phải đủ những nhánh bắt buộc. Nếu có @NotEmpty endpoints, README tối thiểu không nên bỏ endpoints và gọi đó là cấu hình chạy được.

---

## 29. Tiêu chí chặn release

Một quy trình release nên có mức độ ưu tiên rõ thay vì một danh sách mọi lỗi có trọng số bằng nhau.

### 29.1. Blocker

Các tình huống nên cân nhắc chặn phát hành:

- Application profile được hỗ trợ không khởi động vì cấu hình bắt buộc thiếu.
- Có property critical bị đổi tên mà không có migration/communication phù hợp.
- Một secret thật bị đưa vào source, metadata, test fixture hoặc artifact.
- Validation critical không chạy hoặc bị bỏ qua.
- Nguồn precedence khiến override an toàn của operator không hoạt động.
- Một default mới làm thay đổi behavior production theo hướng nguy hiểm.
- Schema documentation tuyên bố một key hoạt động nhưng runtime không nhận.
- Config Data import bắt buộc không hoạt động trong môi trường mục tiêu.
- Không có test xác nhận thay đổi bootstrap có tác dụng.

### 29.2. Cần sửa trước release theo chính sách team

- Metadata thiếu mô tả cho property public mới.
- Hints hoặc deprecation replacement chưa cập nhật.
- Env var example trong README sai tên.
- Một default chưa nói rõ đơn vị.
- Test thiếu case invalid của một property quan trọng.
- Release notes chưa đề cập hành vi thay đổi.

### 29.3. Có thể theo dõi sau nếu được chấp nhận

- Tối ưu mô tả IDE cho một property ít sử dụng.
- Cải thiện ví dụ của một option không ảnh hưởng behavior.
- Tái tổ chức tài liệu khi contract không thay đổi.

**Mức độ cuối cùng phải do chính sách rủi ro của tổ chức quyết định**, nhưng nên có tiêu chí cụ thể, không chỉ một câu chung “all tests green”.

---

## 30. Dùng CI làm bằng chứng phát hành

Một pipeline tham khảo:

~~~text
SOURCE CHECKOUT
    |
    v
COMPILE + ANNOTATION PROCESSING
    |
    v
METADATA ARTIFACT VERIFICATION
    |
    v
UNIT + BINDER TESTS
    |
    v
APPLICATIONCONTEXT RUNNER TESTS
    |
    v
PROFILE / CONFIG DATA SMOKE TESTS
    |
    v
SECURITY / SECRET SCANNING
    |
    v
PACKAGE ARTIFACT
    |
    v
VERIFY PACKAGED METADATA
    |
    v
RELEASE NOTES + DEPLOYMENT DOCUMENTATION
    |
    v
RELEASE
~~~

Đây là một ví dụ workflow. Có thể parallelize các bước độc lập để giảm thời gian chạy, nhưng những bằng chứng liên quan artifact cuối phải kiểm tra đúng artifact đang được phát hành.

### 30.1. Lệnh Maven ví dụ

~~~bash
./mvnw -B clean verify
~~~

### 30.2. Lệnh Gradle ví dụ

~~~bash
./gradlew clean test build
~~~

Không coi lệnh chạy thành công là bằng chứng tất cả môi trường production đều hợp lệ. CI còn cần tập input và profile phù hợp, không chỉ biên dịch.

### 30.3. Các điều kiện cho metadata gate

~~~text
- JSON parses successfully
- Required public property names are present
- No duplicate conflicting contract names without intention
- Deprecated/replacement mappings follow the release plan
- Metadata is inside the final library/JAR
- No raw secrets or production credentials are embedded
~~~

Nếu metadata không được generate do annotation processing bị tắt, gate này phải báo lỗi trước khi artifact được publish.

### 30.4. Không commit file generated tùy tiện

Thông thường metadata được tạo trong build. Nếu repository có chính sách lưu generated files, cần đảm bảo chúng không trôi lệch với source và processor. Đừng tự chỉnh sửa generated JSON trong thư mục build như cách sửa duy nhất; phải sửa source hoặc additional metadata.

---

## 31. Release notes cho thay đổi cấu hình

Một release notes có thể có mục:

~~~text
Configuration changes

Added:
- acme.gateway.connect-timeout (Duration; default 2s)

Changed:
- acme.gateway.retry.max-attempts now requires >= 1

Deprecated:
- acme.gateway.connection-timeout-ms
  Replacement: acme.gateway.connect-timeout
  Compatibility: supported during the announced migration window

Deployment action:
- Rename the old property in environment variables and YAML.
- Verify that production profile loads the intended override.
- Restart the service if the deployed configuration is read at startup.
~~~

Không dùng những ví dụ trên để tuyên bố một phiên bản thực tế có lịch sử như vậy; hãy điền đúng số phiên bản và chính sách của thư viện đang phát hành.

### 31.1. Breaking change có thể là đổi default

Ngay cả khi tên key giữ nguyên, đổi default retry từ 3 lên 10 có thể làm số request tăng và gây tải lên upstream. Release notes cần mô tả tác động, không chỉ rename.

### 31.2. Thay kiểu dữ liệu cũng có thể breaking

Đổi String sang enum, Duration sang số milliseconds, hoặc List thành Map có thể làm cấu hình cũ không bind được. Cần test compatibility và đưa hướng dẫn migration.

---

## 32. Kế hoạch rollout và rollback

Một thay đổi configuration contract nên có bước triển khai:

1. Phát hành tài liệu và thông báo thay đổi.
2. Cập nhật deployment templates/Helm values/CI vars/secret mappings.
3. Bật cấu hình ở staging với dữ liệu giả hoặc secret staging.
4. Kiểm tra startup, validation và nguồn property đang thắng.
5. Triển khai canary hoặc một nhóm service đại diện.
6. Theo dõi health và các metric không chứa secret.
7. Mở rộng rollout khi không có lỗi.
8. Có đường rollback tương thích với cấu hình đã được thay đổi.

### 32.1. Rollback code nhưng không rollback cấu hình

Nếu release mới đổi tên key và deployment templates chỉ còn tên mới, rollback JAR về phiên bản cũ có thể thất bại vì phiên bản cũ không nhận key mới.

Vì thế migration cần xét **cả chiều đi và chiều rollback**. Có thể duy trì cả hai key trong một giai đoạn, với quy tắc precedence rõ để tránh conflict.

### 32.2. Không rollback bằng cách ghi secret ra log

Nếu một service không start do thiếu credential, đừng bật debug raw Environment để chữa. Kiểm tra secret injection/source presence theo cách được cấp quyền, không phát tán giá trị.

---

## 33. Quy tắc cho thư viện dùng chung

Một thư viện Spring Boot starter có thể được hàng chục ứng dụng tiêu thụ. Với nó, configuration metadata và compatibility càng quan trọng.

### 33.1. Prefix nên có namespace rõ

Tốt:

~~~text
acme.gateway.*
acme.storage.*
acme.audit.*
~~~

Dễ gây va chạm:

~~~text
config.*
service.*
settings.*
~~~

Một prefix có namespace rõ giảm khả năng nhiều thư viện dùng trùng tên và giúp IDE nhóm metadata.

### 33.2. Không dùng property mang nghĩa không ổn định như public API

Nếu một implementation detail sẽ thay đổi liên tục, có thể giữ nó là internal constant hoặc tự xử lý theo cấu hình cấp cao thay vì công bố 15 key dễ gây khóa chặt thiết kế.

### 33.3. Đăng ký bean phù hợp

Với starter/auto-configuration, **@EnableConfigurationProperties** trên auto-configuration có thể phù hợp hơn dựa vào application component scan.

### 33.4. Metadata phải đi cùng library artifact

IDE của service tiêu thụ cần nhìn thấy metadata từ dependency JAR. Không chỉ sinh metadata trong ứng dụng demo rồi quên publish nó cùng thư viện.

### 33.5. Test compatibility với Boot versions được tuyên bố hỗ trợ

Nếu library hỗ trợ nhiều major/minor version Spring Boot, kiểm tra build và runtime theo ma trận tương thích đã công bố. Chỉ compile một phiên bản không chứng minh tất cả target versions hoạt động, đặc biệt khi extension point hoặc package thay đổi.

---

## 34. Rà soát trong quá trình nâng cấp Spring Boot

Khi nâng Boot version, configuration contract có thể bị ảnh hưởng bởi:

- Property của chính Spring Boot bị đổi tên hoặc deprecated.
- Default behavior của một auto-configuration thay đổi.
- Dependency starter thay đổi.
- Jakarta/Javax package migration ở các phiên bản liên quan.
- Constructor binding và annotation processing.
- Quy tắc Config Data, bootstrap hoặc profile.
- Module/package của các extension như EnvironmentPostProcessor.
- Actuator access/exposure options.
- Classpath của custom converter và Bean Validation provider.

### 34.1. Không nâng cấp chỉ bằng sửa dependency version

Cần đọc migration guide/release notes của phiên bản mục tiêu và chạy test cấu hình đại diện. Metadata về deprecated properties có thể cảnh báo một số key, nhưng không phải tất cả thay đổi đều được tooling tự phát hiện.

### 34.2. @Value so với @ConfigurationProperties

Một số property dùng @Value với placeholder camelCase có thể không hưởng relaxed binding giống khi dùng canonical kebab-case. Khi nâng cấp/refactor, cần test rằng biến môi trường và property file vẫn được nhận đúng.

### 34.3. Manual metadata có thể trở nên lỗi thời

Nếu một property đã chuyển vào class mới, thay type hoặc biến thành internal setting, manual metadata phải được cập nhật. Một key xuất hiện trong JSON không chứng minh phiên bản mới vẫn quản lý nó.

---

## 35. Checklist cho reviewer của pull request

- [ ] Tên canonical và prefix của property mới rõ ràng.
- [ ] Property mới thuộc module/owner xác định.
- [ ] Java type và conversion tương ứng đã được thử.
- [ ] Required/default được xác định bằng runtime behavior.
- [ ] @Validated/@Valid/@NotNull và các constraint đúng mục đích.
- [ ] List/Map có quy tắc thiếu/rỗng/key rõ.
- [ ] Tên env variable trong docs theo canonical rules.
- [ ] Những override từ profile/env/CLI không bị default che.
- [ ] Không đổi tên public key mà bỏ qua migration contract.
- [ ] Additional metadata không quảng bá property không được dùng.
- [ ] Metadata deprecation/replacement có ý nghĩa.
- [ ] Không có raw credential trong Javadoc, JSON hoặc sample.
- [ ] Binder hoặc Runner tests kiểm tra happy path và invalid path.
- [ ] Thay đổi bootstrap có integration test SpringApplication phù hợp.
- [ ] README và deployment templates đã cập nhật.
- [ ] Release notes nói rõ breaking change và operator action.
- [ ] Build cuối chứa metadata được sinh thành công.

Checklist này áp dụng cho **thay đổi cấu hình**, không phải lý do để sửa các module không liên quan trong cùng pull request.

---

## 36. Checklist cho SRE/DevOps trước deploy

- [ ] Xác định Spring Boot version và artifact build cần phát hành.
- [ ] Xác định active profiles.
- [ ] Xác định file Config Data/import/location được sử dụng.
- [ ] Các property required đã có nguồn cung cấp.
- [ ] Các secret được cấp qua cơ chế an toàn, không qua file public.
- [ ] Tên env variable đúng với canonical property.
- [ ] Đã biết policy precedence khi file/env/CLI cùng cấp một key.
- [ ] Các default quan trọng được người vận hành chấp nhận.
- [ ] Timeout, retry, pool size có đơn vị và giới hạn rõ.
- [ ] Không có property deprecated chưa được xử lý theo kế hoạch.
- [ ] Có smoke test/startup check trên staging.
- [ ] Có rollback plan cả code lẫn deployment config.
- [ ] Có hướng chẩn đoán nguồn thắng mà không in raw values.
- [ ] Các endpoint Actuator nhạy cảm được bảo vệ.
- [ ] Không có debug logging xuất toàn bộ Environment.
- [ ] Trách nhiệm owner/support và tài liệu escalation rõ ràng.

Một checklist operator tốt phải dùng được mà **không đòi họ đọc source Java**.

---

## 37. Runbook: IDE không gợi ý property

Triệu chứng: người dùng gõ **acme.gateway.connect-timeout** trong application.yml nhưng IDE không autocomplete.

Điều tra theo thứ tự:

1. Module có @ConfigurationProperties đúng không?
2. Build có spring-boot-configuration-processor không?
3. Annotation processing có chạy không?
4. Generated JSON có key không?
5. JAR cuối có metadata file không?
6. Service tiêu thụ có dependency version chứa metadata không?
7. IDE có đọc metadata từ dependency và cache phù hợp không?
8. Manual metadata có hợp lệ, có được merge không?
9. Key có phải dynamic và không thể được processor suy ra không?

**Không kết luận runtime không bind được chỉ vì IDE không gợi ý**. Metadata và Binder có trách nhiệm khác nhau.

### 37.1. Nếu metadata JSON có key nhưng IDE không nhận

Kiểm tra dependency artifact, IDE cache, indexing và việc resource được đóng gói. Đừng sửa code binding khi nguyên nhân chỉ là tooling.

### 37.2. Nếu metadata không có key

Kiểm tra processor, record Javadoc, getter/constructor visibility, Lombok order hoặc manual metadata. Việc thêm key thủ công có thể hữu ích nhưng phải biết vì sao runtime có key đó.

---

## 38. Runbook: YAML có property nhưng bean nhận default

Các khả năng:

- Prefix sai hoặc YAML thụt lề sai.
- Property name không canonical.
- Profile nạp một file khác ghi đè.
- Environment variable/JVM/CLI ưu tiên cao hơn.
- Constructor default làm mất tín hiệu “operator chưa khai báo”.
- Bean được tạo bằng cơ chế không phù hợp với constructor binding.
- Một custom converter hoặc BindHandler ảnh hưởng kết quả.
- List replacement khiến dữ liệu từ file nền không còn.
- Object được bind trước thay đổi runtime và không tự refresh.

Quy trình:

1. Viết canonical key và đường dẫn nested đúng.
2. Kiểm tra active profile/source names trong môi trường được bảo vệ.
3. Xác định nguồn thắng qua PropertySource/ConfigurationPropertySource theo cách an toàn.
4. Kiểm tra type conversion.
5. Kiểm tra bean registration.
6. Kiểm tra default và validation.
7. Tái hiện bằng Binder/Runner test với dữ liệu giả.
8. Sửa cấu hình hoặc code đúng tầng, không bật raw Environment dump.

### 38.1. Không in secret

Nếu key có thể chứa password/token, log chỉ status/source category/failure category. Không copy giá trị vào issue hoặc pipeline output.

---

## 39. Runbook: một profile chạy, profile khác không chạy

Ví dụ local pass, prod fail khi startup.

Điều tra:

- Profile prod thực sự active không?
- application-prod.yml có nằm đúng location không?
- Config Data import bắt buộc có mặt không?
- Một property required có bị bỏ khi prod override List không?
- Giá trị mới có sai kiểu/đơn vị không?
- Secret injection của prod có đầy đủ không?
- Một @ConditionalOnProperty có bật thêm bean đòi cấu hình mới không?
- Có env/CLI override từ deployment platform không?

### 39.1. Chọn test phù hợp

Nếu lỗi do String “many” không chuyển thành int, Binder test đủ để tái hiện conversion.

Nếu lỗi do profile prod không nạp một Config Data file, cần test SpringApplication/bootstrap.

Nếu lỗi do bean chỉ được tạo khi flag true, ApplicationContextRunner phù hợp để kiểm tra condition.

---

## 40. Runbook: sau nâng cấp key cũ không còn tác dụng

Một deployment vẫn cấp:

~~~text
acme.gateway.connection-timeout-ms
~~~

nhưng code mới chỉ bind:

~~~text
acme.gateway.connect-timeout
~~~

Nếu migration policy không có alias, key cũ có thể bị bỏ qua và default mới được dùng.

### 40.1. Kiểm tra thông tin phát hành

- Release notes có ghi rename?
- Metadata có deprecation replacement?
- JavaBean/alias logic có thực sự hỗ trợ tên cũ?
- Có test legacy-only?
- Có test cả old/new?
- Chính sách precedence khi hai key cùng tồn tại?
- Biến môi trường trong deployment template đã được đổi chưa?

### 40.2. Không sửa bằng cách thêm một default cứng

Nếu nguyên nhân là tên key cũ không còn được bind, thêm default để app chạy có thể che vấn đề tương thích. Cần sửa mapping hoặc deployment đúng hợp đồng.

---

## 41. Bài thực hành 1: xác định thiếu phần nào

Một project có:

~~~java
@ConfigurationProperties(prefix = "acme.worker")
public record WorkerProperties(int concurrency) {}
~~~

Runtime bind và chạy được, nhưng IDE không gợi ý acme.worker.concurrency.

Hãy nêu các bước:

1. Xác định annotation processor đã chạy chưa.
2. Xem build artifact có spring-configuration-metadata.json không.
3. Xem JSON có đúng property name không.
4. Nếu không có, kiểm tra processor configuration và source discovery.
5. Nếu có, kiểm tra IDE/dependency/packaging.

**Không cần thêm @SpringBootTest chỉ để chứng minh IDE autocomplete**, vì đó là contract metadata/tooling.

## 42. Bài thực hành 2: metadata hay validation?

Metadata:

~~~json
{
  "properties": [
    {
      "name": "acme.pool.max-connections",
      "type": "java.lang.Integer",
      "defaultValue": 20
    }
  ]
}
~~~

Người dùng cấp max-connections=0.

Có tự động bị metadata từ chối không? **Không.** Metadata có thể mô tả type/default nhưng không thay Bean Validation. Nếu số kết nối phải ít nhất 1, cần constraint/invariant runtime và test chứng minh nó được thực thi.

## 43. Bài thực hành 3: test đúng mức

Hãy chọn:

- Java object test cho defensive copy.
- Binder test cho **read-timeout=250ms**.
- ApplicationContextRunner cho @Validated nested object fail.
- Full app test cho application-prod.yml, Config Data import và EnvironmentPostProcessor discovery.

**Bài tập mở rộng:** Nếu một @SpringBootTest tốn nhiều thời gian chỉ để assert String → Duration, chuyển test sang Binder trong khi vẫn giữ smoke test tích hợp đại diện.

## 44. Bài thực hành 4: default không nhất quán

Runtime:

~~~java
@DefaultValue("5s") Duration timeout
~~~

Manual metadata:

~~~json
{
  "name": "acme.gateway.timeout",
  "defaultValue": "2s"
}
~~~

Vấn đề: IDE/docs có thể công bố 2s trong khi runtime dùng 5s khi key vắng mặt.

Cách xử lý: xác định **default thật**, cập nhật Java/manual metadata/docs đồng nhất và thêm test startup missing-key xác minh kết quả. Đừng đổi runtime default bừa bãi chỉ để JSON khớp nếu đó là breaking change chưa được chấp nhận.

## 45. Bài thực hành 5: deprecated không tự tương thích

Một key old-timeout có metadata:

~~~json
{
  "deprecation": {
    "replacement": "acme.gateway.connect-timeout"
  }
}
~~~

Điều đó có tự map key old-timeout sang connect-timeout không? **Không.** Cần runtime alias/legacy binding hoặc yêu cầu migration rõ. Viết test chỉ cấp old key và cả hai key nếu muốn tiếp tục hỗ trợ nó.

## 46. Bài thực hành 6: tên biến môi trường

Canonical:

~~~text
acme.gateway.retry.max-attempts
~~~

Tên env chuẩn:

~~~text
ACME_GATEWAY_RETRY_MAXATTEMPTS
~~~

Không tự thêm underscore tại dấu gạch ngang thành **MAX_ATTEMPTS** nếu muốn theo quy tắc canonical-to-env được Spring Boot công bố.

Để chứng minh behavior của OS env thật, test phải dùng source env semantics hoặc khởi động tiến trình với biến môi trường tương ứng.

## 47. Bài thực hành 7: có nên public source metadata?

Một helper nội bộ muốn trả về toàn bộ PropertySource names và values qua API public để người dùng báo lỗi.

Đây là rủi ro lớn: nó có thể lộ secret, đường dẫn hạ tầng hoặc tên tenant.

Giải pháp hợp lý: xác thực/ủy quyền chẩn đoán, giới hạn key bằng allowlist, chỉ trả source category và lỗi đã phân loại; không trả raw values hay full Environment.

---

## 48. Mẫu phiếu phát hành cấu hình

Có thể dùng mẫu dưới đây trong pull request/release ticket:

~~~text
Configuration change summary
----------------------------
Module/prefix:
Owner:
Spring Boot target versions:

Added properties:
Changed properties:
Deprecated properties:
Removed properties:

Defaults before:
Defaults after:
Required fields:
Validation constraints:
Data types and units:

Migration policy:
Old/new precedence:
Compatibility window:
Rollback requirements:

Metadata:
- Processor configured:
- Generated JSON verified:
- Packaged metadata verified:

Tests:
- Object/Binder:
- ApplicationContextRunner:
- Full application/profile/import:
- Security/redaction:

Documentation:
- Properties table:
- YAML sample:
- Environment variable examples:
- Secret handling:
- Troubleshooting:
- Release notes:

Deployment:
- Staging profile test:
- Canary/rollback plan:
- Owner approval:
~~~

Mục tiêu là khiến thay đổi cấu hình trở thành một quyết định có chứng cứ, không để mỗi team đoán cách sử dụng một key mới.

---

## 49. Tài liệu chính thức nên đối chiếu theo phiên bản

Các đường dẫn tham khảo:

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Configuration Metadata Format: https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html
- Spring Boot — Generating Your Own Metadata: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Annotation Processor Details: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot — Test Utilities: https://docs.spring.io/spring-boot/reference/testing/test-utilities.html
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html

Một dự án nâng cấp từ Boot 3 lên Boot 4 cần đọc tài liệu của **phiên bản đích**, không chỉ dựa vào một đoạn code cũ. Annotation processing, module packaging, startup extension và actuator settings có thể thay đổi theo phiên bản.

---

## 50. Tổng kết

Rà soát cấu hình trước phát hành là một quy trình xác nhận **configuration contract** của ứng dụng hoặc thư viện Spring Boot.

**Metadata** giúp người dùng và IDE khám phá key, kiểu, mô tả, default, hints và deprecated status. Nó được sinh bởi **spring-boot-configuration-processor** và có thể bổ sung bằng **additional-spring-configuration-metadata.json**. Cần kiểm tra metadata **trong artifact cuối**.

**Kiểm thử** xác nhận hành vi thật: Java object tests cho invariant, Binder tests cho name/conversion/nested binding, ApplicationContextRunner cho bean/validation/conditions, và full SpringApplication tests cho profile, Config Data, bootstrap và integration. Không cần tất cả mức cho mọi field, nhưng không được dùng một test thấp để kết luận thay một cơ chế chưa hề được chạy.

**Tài liệu sử dụng** phải giải thích canonical names, defaults, required fields, units, env var mapping, source precedence, profile/import, secret handling, startup errors, deprecation và migration. Ví dụ tối thiểu phải chạy được, không chứa credentials thật.

Một release sẵn sàng khi ba lớp trên cùng phản ánh **một hợp đồng duy nhất**: property nào được hỗ trợ, nó được cấp bằng cách nào, runtime dùng nó ra sao, những dữ liệu nào bị từ chối và người vận hành cần làm gì khi nâng cấp hoặc rollback.

Câu hỏi cuối cùng cho reviewer không chỉ là “JAR đã build thành công chưa?”, mà là: **“Người dùng có thể khám phá, cấu hình, kiểm tra và nâng cấp ứng dụng này mà không cần đoán hoặc làm lộ dữ liệu bí mật hay không?”**
