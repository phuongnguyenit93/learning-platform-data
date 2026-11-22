# Kiểm thử liên kết và chuyển đổi kiểu bằng Binder với nguồn dữ liệu nhỏ

## 1. Mục tiêu học tập

Trong Spring Boot Externalized Configuration, ứng dụng thường khai báo thuộc tính trong `application.yml`, `application.properties`, biến môi trường hoặc đối số dòng lệnh. Sau đó, `@ConfigurationProperties` giúp liên kết các thuộc tính ấy vào những đối tượng Java có kiểu.

Khi muốn kiểm thử một quy tắc liên kết, nhiều người bắt đầu bằng `@SpringBootTest` và khởi động toàn bộ Spring context. Cách này hữu ích cho kiểm thử tích hợp, nhưng đôi khi quá rộng nếu câu hỏi thực tế chỉ là:

- Khóa `client.connect-timeout` có chuyển được từ `"5s"` thành `Duration` không?
- Khóa `client.max-retries` có chuyển từ `"4"` thành `int` không?
- Record chứa các thành phần lồng nhau có bind đúng không?
- Dữ liệu dạng `"2MB"` có trở thành `DataSize` không?
- Nếu tên khóa bị thiếu thì `BindResult` phản ánh điều gì?
- Nếu giá trị sai kiểu, lỗi binding có xuất hiện như mong đợi không?
- Có thể xác nhận hành vi này **không cần tạo ApplicationContext, không đọc file thật và không chạy web server** không?

Câu trả lời là **có**: Spring Boot cung cấp API `Binder` và những triển khai `ConfigurationPropertySource` cho phép thực hiện binding trực tiếp trên một nguồn dữ liệu nhỏ.

Bài này tập trung vào kỹ thuật:

```text
Map<String, Object> dữ liệu thử nghiệm
                |
                v
     MapConfigurationPropertySource
                |
                v
              Binder
                |
        tra cứu tên khóa
        chuyển đổi kiểu
        bind object
                |
                v
             BindResult
                |
                v
        JUnit / AssertJ assertions
```

Đây là **unit-level binding test** hoặc **focused binder test**. Nó kiểm tra phần binder, không thay thế mọi kiểm thử tích hợp của Spring Boot.

## 2. Khi nào nên dùng Binder trực tiếp?

Giả sử ứng dụng có nhóm cấu hình:

```yaml
client:
  endpoint: "https://api.example.invalid"
  connect-timeout: 5s
  max-retries: 4
  enabled: true
```

Record:

```java
import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

Nếu mục tiêu chỉ là xác nhận binder hiểu `client.connect-timeout=5s`, không cần khởi chạy HTTP server, tạo DataSource, quét các service, tải toàn bộ YAML hay bật profile.

Ta có thể tạo một Map chứa chính các khóa cần thử, rồi yêu cầu binder tạo `ClientProperties`.

Các ưu điểm của bài test nhỏ:

1. **Nhanh và cô lập:** không cần refresh Spring ApplicationContext.
2. **Đầu vào rõ ràng:** mọi giá trị được khai báo ngay trong test.
3. **Ít tác động phụ:** không phụ thuộc file cấu hình đang được developer chỉnh sửa.
4. **Chẩn đoán đơn giản:** khi lỗi xảy ra, nguồn có thể chỉ chứa vài property.
5. **Dễ thử các biến thể:** thay một giá trị đầu vào mà không phải thêm file YAML.
6. **Tập trung đúng trách nhiệm:** thử tên property, chuyển đổi kiểu, object lồng nhau, danh sách và giá trị mặc định.

Nhưng bài test này **không tự kiểm tra** việc Spring Boot có tìm đúng file theo profile, có đăng ký bean cấu hình trong context, hoặc có nạp một location từ `spring.config.import` hay không. Những phần đó cần loại test tương ứng.

## 3. Các thành phần API quan trọng

| API | Package chính | Vai trò |
| --- | --- | --- |
| `Binder` | `org.springframework.boot.context.properties.bind` | Liên kết thuộc tính thành đối tượng Java |
| `Bindable<T>` | `org.springframework.boot.context.properties.bind` | Mô tả kiểu đích và một số thông tin binding |
| `BindResult<T>` | `org.springframework.boot.context.properties.bind` | Biểu diễn kết quả có hoặc không có giá trị bind |
| `ConfigurationPropertySource` | `org.springframework.boot.context.properties.source` | Nguồn thuộc tính mà Binder hiểu |
| `MapConfigurationPropertySource` | `org.springframework.boot.context.properties.source` | Đưa một Map vào giao diện nguồn cấu hình |
| `BindException` | `org.springframework.boot.context.properties.bind` | Lỗi phát sinh khi binding không thực hiện được |
| `ConfigurationPropertyName` | `org.springframework.boot.context.properties.source` | Biểu diễn tên khóa có cấu trúc theo quy tắc của Binder |

Một ví dụ tối giản:

```java
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

public class MinimalBinderExample {

    public static void main(String[] args) {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("example.retries", "7")
                );

        Binder binder = new Binder(source);

        BindResult<Integer> result =
                binder.bind("example.retries", Integer.class);

        System.out.println(result.get()); // 7
    }
}
```

Ở đây:

- Map lưu giá trị `"7"` dưới dạng chuỗi.
- `MapConfigurationPropertySource` bọc Map thành nguồn cấu hình.
- `Binder` thực hiện chuyển từ dữ liệu nguồn sang kiểu đích `Integer`.
- `BindResult#get()` trả về số nguyên nếu kết quả có giá trị.

Bài test không cần annotation `@SpringBootTest`, không tạo SpringApplication và không đọc một file cấu hình nào.

## 4. Thiết lập phụ thuộc để viết test

Ví dụ hướng tới dự án dùng Java 17 trở lên và Spring Boot 3.x. Những API cụ thể cần đối chiếu phiên bản thực tế của dự án.

Một dự án Spring Boot với Gradle Groovy DSL thường đã có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Các API Binder nằm trong các thư viện cốt lõi của Spring Boot. `spring-boot-starter-test` cung cấp các thành phần kiểm thử thường dùng, như JUnit Jupiter và AssertJ.

Với Maven, dependency test thông dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Một số ví dụ về validation ở cuối bài yêu cầu thêm Bean Validation provider, thường qua:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Không cần starter web chỉ để kiểm thử một phép chuyển `String → Duration`.

Nếu dự án đã có dependencies và đang dùng Spring Boot BOM hoặc plugin quản lý phiên bản, không cần thêm version thủ công vào từng starter.

## 5. Test đầu tiên: bind một giá trị nguyên

Tạo file:

```text
src/test/java/com/example/configdemo/BinderBasicsTest.java
```

Nội dung:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class BinderBasicsTest {

    @Test
    void bindsStringToInteger() {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("worker.thread-count", "8")
                );

        Binder binder = new Binder(source);

        BindResult<Integer> result =
                binder.bind("worker.thread-count", Integer.class);

        assertThat(result.isBound()).isTrue();
        assertThat(result.get()).isEqualTo(8);
    }
}
```

Quy trình chính:

```text
"worker.thread-count" -> "8"
          |
          v
  MapConfigurationPropertySource
          |
          v
   Binder.bind(... Integer.class)
          |
          v
     BindResult<Integer>
          |
          v
           8
```

Đây là một test trực tiếp cho **chuyển đổi kiểu kết hợp với binding**, không phải một test unit thuần của `Integer.parseInt`.

Chạy bằng Gradle:

```bash
./gradlew test --tests "com.example.configdemo.BinderBasicsTest"
```

Trong PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.configdemo.BinderBasicsTest"
```

Nếu dùng Maven, hãy chạy test bằng cơ chế của dự án, ví dụ `./mvnw test -Dtest=BinderBasicsTest` trong môi trường phù hợp.

## 6. BindResult: có dữ liệu hay không có dữ liệu?

Method `Binder#bind` thường trả về một `BindResult<T>`, thay vì luôn trả trực tiếp `T`.

Điều này cho phép phân biệt:

- Binding tìm được dữ liệu phù hợp và tạo kết quả.
- Binding không tìm thấy dữ liệu nên không có kết quả.
- Binding tìm thấy dữ liệu nhưng bị lỗi trong khi chuyển đổi hoặc tạo object.

Với nguồn:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("worker.thread-count", "8")
        );
Binder binder = new Binder(source);
```

Khi hỏi đúng khóa:

```java
BindResult<Integer> found =
        binder.bind("worker.thread-count", Integer.class);

assertThat(found.isBound()).isTrue();
assertThat(found.get()).isEqualTo(8);
```

Khi hỏi khóa không tồn tại:

```java
BindResult<Integer> missing =
        binder.bind("worker.max-attempts", Integer.class);

assertThat(missing.isBound()).isFalse();
```

Không nên gọi:

```java
missing.get();
```

nếu chưa kiểm tra có kết quả hay không. `BindResult#get()` dành cho trường hợp có giá trị, và có thể ném ngoại lệ khi kết quả không bound.

Bạn có thể dùng:

```java
Integer attempts = missing.orElse(3);
```

hoặc thực hiện logic khác qua những phương thức của `BindResult` phù hợp.

**Lưu ý:** giá trị mặc định trong `BindResult#orElse(...)` là logic trong **test hoặc mã gọi API**, không đồng nghĩa Spring Boot tự đặt mặc định runtime cho một bean `@ConfigurationProperties` được đăng ký ở ApplicationContext.

## 7. Bind một record từ một Map nhỏ

Một tình huống thực tế hơn là liên kết cả nhóm khóa vào record Java.

### 7.1. Định nghĩa record

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

Trong ví dụ này, record **không bắt buộc phải mang `@ConfigurationProperties`**, vì ta chủ động chỉ định prefix cho Binder trong test. Nếu lớp đó cũng được dùng bởi ứng dụng thật, có thể gắn annotation để đăng ký theo cơ chế configuration properties.

### 7.2. Tạo dữ liệu thử nghiệm

```java
Map<String, Object> input = Map.of(
        "client.endpoint", "https://api.example.invalid",
        "client.connect-timeout", "5s",
        "client.max-retries", "4",
        "client.enabled", "true"
);
```

Ở đây mọi giá trị được cố ý đặt dưới dạng String, giống nhiều nguồn externalized configuration. Nhờ đó test không “ăn gian” bằng cách đưa thẳng một `Duration` đã được tạo sẵn vào Map.

### 7.3. Test tạo record

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class ClientPropertiesBinderTest {

    @Test
    void bindsRecordAndConvertsValues() {
        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of(
                                "client.endpoint",
                                "https://api.example.invalid",
                                "client.connect-timeout", "5s",
                                "client.max-retries", "4",
                                "client.enabled", "true"
                        )
                );

        ClientProperties properties =
                new Binder(source)
                        .bind("client", ClientProperties.class)
                        .get();

        assertThat(properties.endpoint())
                .isEqualTo(URI.create("https://api.example.invalid"));
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(5));
        assertThat(properties.maxRetries()).isEqualTo(4);
        assertThat(properties.enabled()).isTrue();
    }
}
```

Mỗi assertion kiểm tra một phần của cùng hợp đồng:

| Thuộc tính nguồn | Thành phần record | Kết quả |
| --- | --- | --- |
| `client.endpoint` | `endpoint()` | `URI` |
| `client.connect-timeout` | `connectTimeout()` | `Duration.ofSeconds(5)` |
| `client.max-retries` | `maxRetries()` | `int 4` |
| `client.enabled` | `enabled()` | `true` |

**Đặc điểm quan trọng:** Binder không cần gọi setter của record. Nó sử dụng constructor binding để tạo đối tượng với những giá trị đã chuyển kiểu.

## 8. Phân biệt Binder trực tiếp với @ConfigurationPropertiesScan

Trong ứng dụng Spring Boot thông thường:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

Bean được phát hiện và đăng ký nhờ một trong các cơ chế:

```java
@ConfigurationPropertiesScan
```

hoặc:

```java
@EnableConfigurationProperties(ClientProperties.class)
```

Nhưng trong test trực tiếp:

```java
new Binder(source).bind("client", ClientProperties.class)
```

ta **không yêu cầu Spring ApplicationContext đăng ký bean**. Mã test tự tạo Binder, tự chọn prefix và kiểu đích.

Điều này có hai hệ quả:

1. Binder có thể tạo một record không gắn `@ConfigurationProperties`, nếu kiểu đó bind được.
2. Test binder trực tiếp **không chứng minh bean ấy sẽ được phát hiện bởi component scan hoặc configuration properties scan** trong ứng dụng thật.

Do đó, hãy dùng Binder test cho các quy tắc **chuyển kiểu và cấu trúc**, còn `ApplicationContextRunner` hoặc `@SpringBootTest` cho câu hỏi **đăng ký bean và kết hợp với Spring**.

## 9. Kiểm thử Duration mà không cần file application.yml

`Duration` dùng cho timeout, thời gian chờ và chu kỳ tác vụ. Spring Boot hỗ trợ cú pháp cấu hình thuận tiện như `500ms`, `3s`, `2m`.

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class DurationBinderTest {

    @Test
    void convertsSeveralDurationFormats() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of(
                                "time.fast", "250ms",
                                "time.normal", "3s",
                                "time.slow", "2m"
                        )
                )
        );

        assertThat(binder.bind("time.fast", Duration.class).get())
                .isEqualTo(Duration.ofMillis(250));

        assertThat(binder.bind("time.normal", Duration.class).get())
                .isEqualTo(Duration.ofSeconds(3));

        assertThat(binder.bind("time.slow", Duration.class).get())
                .isEqualTo(Duration.ofMinutes(2));
    }
}
```

Đoạn test xác nhận **binder và conversion của Spring Boot** hiểu các hậu tố thời gian. Nó không kiểm tra cú pháp `Duration.parse(...)` của Java thuần.

Cần phân biệt:

```java
Duration.parse("PT3S"); // cú pháp ISO-8601
```

và chuỗi externalized configuration:

```text
3s
```

Hai biểu diễn có thể mang cùng ý nghĩa thời lượng nhưng không nhất thiết được parse bằng cùng một API.

## 10. Kiểm thử DataSize với giá trị có hậu tố

Spring Boot sử dụng `org.springframework.util.unit.DataSize` để diễn đạt kích thước dữ liệu.

Ví dụ test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import org.springframework.util.unit.DataSize;

class DataSizeBinderTest {

    @Test
    void convertsMegabytes() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("upload.max-size", "2MB")
                )
        );

        DataSize size = binder.bind(
                "upload.max-size",
                DataSize.class
        ).get();

        assertThat(size).isEqualTo(DataSize.ofMegabytes(2));
        assertThat(size.toBytes()).isEqualTo(2L * 1024 * 1024);
    }
}
```

Sử dụng `DataSize` thay vì tự tách `"2MB"` thành hai phần chuỗi giúp code rõ nghĩa và giảm nguy cơ tính sai đơn vị.

Một test như trên thích hợp khi cần bảo đảm một cấu hình nhận `512KB`, `2MB` hoặc một giới hạn dung lượng khác theo quy tắc Spring Boot.

**Lưu ý:** các biến thể đơn vị và hành vi chuyển đổi cụ thể phụ thuộc hệ thống conversion được Binder sử dụng. Với một Binder tạo theo cách mặc định thông dụng trong Spring Boot, các converter chuẩn của Boot thường hỗ trợ `DataSize`.

## 11. Khi nào nên dùng Map<String,Object> thay vì YAML?

Một Map nhỏ là công cụ phù hợp khi mục tiêu là **kiểm tra Binder**, vì:

- Không cần tạo file tạm.
- Không cần YAML parser.
- Test chứa đủ đầu vào và kỳ vọng tại một nơi.
- Có thể đặt sai một giá trị mà không ảnh hưởng những test khác.
- Dễ xây dựng nhiều tình huống với các tập khóa khác nhau.

Ví dụ:

```java
Map<String, Object> config = new LinkedHashMap<>();
config.put("client.connect-timeout", "5s");
config.put("client.max-retries", "3");
```

Đây là dữ liệu đã ở dạng key/value mà `MapConfigurationPropertySource` hiểu.

Nhưng **Map không kiểm thử cấu trúc YAML**. Nếu mục tiêu là phát hiện lỗi thụt lề hoặc cách Spring Boot load Config Data, test với Map sẽ không giúp bạn.

Phân biệt:

| Yêu cầu | Công cụ ưu tiên |
| --- | --- |
| Chuỗi `5s` thành `Duration` | Binder + Map nhỏ |
| Khóa kebab-case thành record camelCase | Binder + Map nhỏ |
| Giá trị sai `int` gây BindException | Binder + Map nhỏ |
| Cấu trúc danh sách theo các khóa indexed | Binder + Map nhỏ |
| File YAML có cú pháp hợp lệ | Test parser hoặc tích hợp Config Data |
| Profile-specific configuration nạp đúng | Integration test với profile |
| Bean `@ConfigurationProperties` được đăng ký | `ApplicationContextRunner` / `@SpringBootTest` |
| Ưu tiên CLI, env, YAML trong thực tế | Test Spring Environment/Boot với nguồn thực |
| Annotation `@Validated` được thực thi lúc tạo bean | Context test hoặc handler validation tường minh |

Chọn mức test nhỏ nhất có thể trả lời chính xác câu hỏi.

## 12. Kiểm thử tên khóa theo quy ước relaxed binding

Trong Java, field thường dùng camelCase:

```java
int maxRetries;
Duration connectTimeout;
```

Trong nguồn cấu hình, nên dùng kebab-case:

```properties
client.max-retries=3
client.connect-timeout=5s
```

Binder của Spring Boot hỗ trợ **relaxed binding**: những cách trình bày tương đương về dấu phân cách/chữ hoa được ánh xạ về tên cấu hình có ý nghĩa tương ứng.

Test với record:

```java
public record RetryOptions(
        int maxRetries,
        Duration connectTimeout) {
}
```

Và Map:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of(
                        "retry.max-retries", "4",
                        "retry.connect-timeout", "750ms"
                )
        );

RetryOptions result = new Binder(source)
        .bind("retry", RetryOptions.class)
        .get();
```

Kỳ vọng:

```java
assertThat(result.maxRetries()).isEqualTo(4);
assertThat(result.connectTimeout())
        .isEqualTo(Duration.ofMillis(750));
```

Đây là bài test đúng trọng tâm: tên nguồn dạng kebab-case phải liên kết được với tham số constructor camelCase.

**Không nên dùng test này để suy ra mọi lỗi gõ tên sẽ được binder tự sửa.** Ví dụ `retry.max-retrise` chứa lỗi chính tả, không phải biến thể của `retry.max-retries`.

## 13. Kiểm thử khi toàn bộ prefix không có trong nguồn

Xét một Map chỉ chứa:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("database.url", "jdbc:example")
        );

Binder binder = new Binder(source);
```

Khi bind một nhóm hoàn toàn không có:

```java
BindResult<ClientProperties> result =
        binder.bind("client", ClientProperties.class);

assertThat(result.isBound()).isFalse();
```

Điểm này khác với việc **có một vài khóa dưới prefix, nhưng thiếu thành phần bắt buộc**.

Ví dụ Map:

```java
Map.of(
    "client.endpoint", "https://api.example.invalid",
    "client.enabled", "true"
)
```

có thể khiến binder cố tạo một `ClientProperties` với các thành phần chưa được cung cấp. Kết quả cụ thể còn phụ thuộc kiểu Java, constructor, mặc định và các chính sách binding.

Vì vậy:

- **Toàn bộ prefix vắng mặt:** thường kiểm tra qua `isBound()`.
- **Prefix có một số khóa nhưng thiếu khóa khác:** kiểm tra đối tượng nhận được và/hoặc áp dụng validation nếu muốn bắt buộc.

Không nên mặc định rằng một thành phần record kiểu tham chiếu luôn được tự động kiểm tra `@NotNull` khi gọi Binder trực tiếp mà không cấu hình validation.

## 14. Kiểm thử dữ liệu sai kiểu

Giả sử bean yêu cầu một số nguyên:

```java
public record WorkerOptions(int threadCount) {
}
```

Map có lỗi:

```java
Map.of("worker.thread-count", "many")
```

Dữ liệu có tên khóa đúng nhưng giá trị `"many"` không thể trở thành `int` theo chuyển đổi thông thường.

JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class InvalidTypeBinderTest {

    @Test
    void rejectsNonNumericThreadCount() {
        Binder binder = new Binder(
                new MapConfigurationPropertySource(
                        Map.of("worker.thread-count", "many")
                )
        );

        assertThrows(BindException.class, () ->
                binder.bind("worker.thread-count", Integer.class)
        );
    }
}
```

Test này mô tả hành vi **conversion/binding failure**. Có thể dùng `assertThatThrownBy(...)` của AssertJ để kiểm tra chi tiết hơn khi cần.

Không nên phụ thuộc vào toàn văn thông báo lỗi vì chuỗi exception và cách trình bày thông tin nguồn có thể khác nhau giữa các phiên bản Spring Boot.

Đối với test quan trọng, có thể xác nhận loại lỗi, tên khóa hoặc nguyên nhân sâu một cách có chọn lọc.

## 15. Phân biệt khóa thiếu với giá trị sai kiểu

Hai Map:

**A — thiếu thuộc tính:**

```java
Map.of("worker.name", "batch")
```

**B — tên đúng, giá trị không chuyển được:**

```java
Map.of("worker.thread-count", "many")
```

Với câu hỏi:

```java
binder.bind("worker.thread-count", Integer.class)
```

khả năng xử lý:

| Trường hợp | Tình huống |
| --- | --- |
| A | Không tìm thấy property cần bind; `BindResult#isBound()` thường là `false` |
| B | Có property nhưng chuyển kiểu thất bại; binding có thể ném `BindException` |

Nếu dùng `@DefaultValue` hoặc một giá trị dự phòng ở mức object, kết quả khi thiếu property có thể khác. Nhưng dữ liệu **có mặt mà sai kiểu** không tự động được xem là thiếu.

Đây là một khác biệt quan trọng khi viết test: không nên trộn “giá trị không có” và “giá trị không hợp lệ” thành cùng một assertion.

## 16. Kiểm thử giá trị Boolean và enum

### 16.1. Boolean

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("feature.enabled", "true")
        )
);

Boolean enabled =
        binder.bind("feature.enabled", Boolean.class).get();

assertThat(enabled).isTrue();
```

Khi mã nghiệp vụ cần hai trạng thái bật/tắt, boolean hoặc Boolean là lựa chọn tự nhiên. Nếu cần phân biệt **không khai báo** với **false**, dùng `Boolean` kết hợp quy tắc bắt buộc/default phù hợp.

### 16.2. Enum

Giả sử:

```java
public enum DispatchMode {
    FAST,
    SAFE,
    OFF
}
```

Test:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("dispatch.mode", "safe")
        )
);

DispatchMode mode =
        binder.bind("dispatch.mode", DispatchMode.class).get();

assertThat(mode).isEqualTo(DispatchMode.SAFE);
```

Spring Boot có những converter hỗ trợ tên enum theo cách nhập thông dụng. Một giá trị hoàn toàn không thuộc enum, chẳng hạn `"teleport"`, không có lý do để được tự động suy đoán thành `SAFE`.

Khi ứng dụng chỉ cho phép một tập giá trị hữu hạn, enum thường an toàn và dễ kiểm thử hơn chuỗi tự do.

## 17. Kiểm thử object lồng nhau

Cấu hình thực tế thường có nhiều mức.

Ví dụ:

```yaml
gateway:
  endpoint: "https://gateway.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

Record:

```java
import java.net.URI;
import java.time.Duration;

public record GatewayOptions(
        URI endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

MapConfigurationPropertySource:

```java
Map<String, Object> values = Map.of(
        "gateway.endpoint", "https://gateway.example.invalid",
        "gateway.retry.attempts", "4",
        "gateway.retry.delay", "2s"
);
```

Test:

```java
GatewayOptions gateway = new Binder(
        new MapConfigurationPropertySource(values)
).bind("gateway", GatewayOptions.class).get();

assertThat(gateway.endpoint())
        .isEqualTo(URI.create("https://gateway.example.invalid"));

assertThat(gateway.retry()).isNotNull();
assertThat(gateway.retry().attempts()).isEqualTo(4);

assertThat(gateway.retry().delay())
        .isEqualTo(Duration.ofSeconds(2));
```

Bài test đồng thời xác nhận:

1. Binder nhận đúng prefix `gateway`.
2. Binder nhận đúng nhánh `gateway.retry.*`.
3. Binder tạo object `Retry` bằng các giá trị thích hợp.
4. Binder truyền object lồng nhau vào `GatewayOptions`.
5. Conversion của `Duration` hoạt động trong thành phần lồng nhau.

**Lưu ý:** nếu bỏ hoàn toàn các khóa `gateway.retry.*`, đối tượng lồng nhau có thể không được tạo. Nếu nó là bắt buộc, cần validation hoặc mặc định phù hợp, không chỉ kiểm tra happy path.

## 18. Kiểm thử danh sách bằng indexed keys

Tệp YAML:

```yaml
queue:
  delays:
    - 1s
    - 3s
    - 10s
```

Trong Map có thể biểu diễn dạng indexed:

```java
Map<String, Object> values = Map.of(
        "queue.delays[0]", "1s",
        "queue.delays[1]", "3s",
        "queue.delays[2]", "10s"
);
```

Record:

```java
import java.time.Duration;
import java.util.List;

public record QueueOptions(List<Duration> delays) {
}
```

Test:

```java
QueueOptions options = new Binder(
        new MapConfigurationPropertySource(values)
).bind("queue", QueueOptions.class).get();

assertThat(options.delays()).containsExactly(
        Duration.ofSeconds(1),
        Duration.ofSeconds(3),
        Duration.ofSeconds(10)
);
```

Đây là một ví dụ có giá trị vì binder cần làm **hai công việc**:

- Nhận diện cấu trúc danh sách từ các khóa `[0]`, `[1]`, `[2]`.
- Chuyển từng phần tử từ chuỗi sang `Duration`.

Nếu test chỉ đưa sẵn một `List<Duration>` vào Map, bạn chưa kiểm chứng đầy đủ khả năng chuyển đổi từng phần tử.

## 19. Kiểm thử Map có giá trị cần chuyển kiểu

Một Map cấu hình khác:

```yaml
routing:
  weights:
    blue: 50
    green: 30
```

Record:

```java
import java.util.Map;

public record RoutingOptions(Map<String, Integer> weights) {
}
```

Dữ liệu test:

```java
Map<String, Object> input = Map.of(
        "routing.weights.blue", "50",
        "routing.weights.green", "30"
);
```

Binding:

```java
RoutingOptions result = new Binder(
        new MapConfigurationPropertySource(input)
).bind("routing", RoutingOptions.class).get();

assertThat(result.weights())
        .containsEntry("blue", 50)
        .containsEntry("green", 30);
```

Ở đây `blue` và `green` là các khóa động của Map, còn `"50"` và `"30"` cần trở thành `Integer`.

**Không nhầm MapConfigurationPropertySource với thuộc tính đích kiểu Map**:

- `MapConfigurationPropertySource` là **cách đưa nguồn vào Binder**.
- `Map<String,Integer> weights` là **dữ liệu bên trong object kết quả**.

Hai loại Map có vai trò khác nhau.

## 20. Nhiều nguồn nhỏ: thử quy tắc ưu tiên

Binder có thể nhận nhiều `ConfigurationPropertySource`. Thứ tự bạn cung cấp có ý nghĩa khi cùng một khóa tồn tại ở nhiều nguồn.

Ví dụ:

```java
MapConfigurationPropertySource overrides =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "8")
        );

MapConfigurationPropertySource defaults =
        new MapConfigurationPropertySource(
                Map.of(
                        "client.max-retries", "3",
                        "client.enabled", "true"
                )
        );

Binder binder = new Binder(
        java.util.List.of(overrides, defaults)
);
```

Test:

```java
assertThat(
        binder.bind("client.max-retries", Integer.class).get()
).isEqualTo(8);

assertThat(
        binder.bind("client.enabled", Boolean.class).get()
).isTrue();
```

Nguồn `overrides` đứng trước, vì vậy khóa trùng `max-retries` lấy từ nguồn đó. Khóa `enabled` chỉ có ở `defaults` nên vẫn được liên kết.

Đây là test hữu ích khi bạn muốn xác nhận **quy tắc ưu tiên ở mức danh sách nguồn do test tạo**.

Nhưng nó **không chứng minh** thứ tự ưu tiên đầy đủ giữa CLI, biến môi trường, system properties và Config Data trong ứng dụng thật. Để thử chính sách runtime của Spring Environment, cần có test tạo các PropertySource thực tế hoặc dùng ApplicationContext với những nguồn phù hợp.

## 21. Constructor binding và yêu cầu tên tham số

Với record:

```java
public record WorkerOptions(int threadCount) {
}
```

Binder có thể dùng canonical constructor để tạo object từ thuộc tính `worker.thread-count`.

Nếu dùng một class thông thường:

```java
public final class WorkerOptions {

    private final int threadCount;

    public WorkerOptions(int threadCount) {
        this.threadCount = threadCount;
    }

    public int getThreadCount() {
        return threadCount;
    }
}
```

thì constructor binding cần biết tên tham số tương ứng, và trong Java build thông thường điều đó liên quan tới việc giữ metadata tên tham số, chẳng hạn tùy chọn compiler `-parameters`.

Spring Boot Gradle/Maven plugin với cấu hình build phù hợp thường thiết lập những điều kiện cần thiết; với hệ thống build tùy biến, cần kiểm tra việc giữ tên tham số nếu binder báo không thể bind class có constructor.

**Không nên viết test cho record rồi suy ra mọi class Java có nhiều constructor đều có thể được binder tạo tự động không cần thêm thông tin.** Trường hợp nhiều constructor có thể cần xác định constructor dùng để binding theo cơ chế của phiên bản Boot đang sử dụng.

## 22. Binder không có nghĩa là ApplicationContext

Có thể hình dung ba cách tạo một object cấu hình:

**A. Tạo thủ công:**

```java
ClientProperties p = new ClientProperties(
        URI.create("https://api.example.invalid"),
        Duration.ofSeconds(5),
        4,
        true
);
```

Điều này kiểm tra hành vi Java object, nhưng không thử binding hay conversion.

**B. Gọi Binder trực tiếp:**

```java
ClientProperties p = new Binder(source)
        .bind("client", ClientProperties.class)
        .get();
```

Điều này thử binding/conversion và constructor, nhưng không yêu cầu bean của Spring context.

**C. Đăng ký bằng @ConfigurationProperties và khởi tạo context:**

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(...) {
}
```

kèm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Cách C kiểm tra được cả đăng ký bean và các cơ chế Boot áp dụng trong context, nhưng thường rộng hơn và tốn thiết lập hơn.

Không có cách nào “luôn tốt nhất”. Chọn theo mục tiêu test, không theo thói quen chỉ dùng `@SpringBootTest` cho mọi vấn đề.

## 23. Kiểm thử giá trị mặc định của constructor binding

Spring Boot hỗ trợ `@DefaultValue` cho thành phần record hoặc tham số constructor ở những kiểu `@ConfigurationProperties` tương thích.

Ví dụ:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.bind.DefaultValue;

public record PollingOptions(
        @DefaultValue("5s") Duration interval,
        @DefaultValue("10") int batchSize) {
}
```

Một nguồn chỉ cung cấp:

```java
MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(
                Map.of("polling.batch-size", "20")
        );
```

Test:

```java
PollingOptions options = new Binder(source)
        .bind("polling", PollingOptions.class)
        .get();

assertThat(options.interval()).isEqualTo(Duration.ofSeconds(5));
assertThat(options.batchSize()).isEqualTo(20);
```

Bài test xác nhận rằng giá trị được cung cấp từ nguồn có thể ghi đè mặc định của một thành phần, còn thành phần không được khai báo sử dụng mặc định.

Lưu ý:

- `@DefaultValue` là một phần của mô hình binding; mặc định của record không giống `new PollingOptions(...)` khi bạn tự gọi constructor thông thường.
- Nếu **toàn bộ prefix không tồn tại**, kết quả `binder.bind("polling", ...)` có thể không bound; hãy kiểm tra `isBound()` thay vì giả định Binder luôn tạo object.
- Một giá trị có mặt nhưng **sai kiểu** không tự được coi là “thiếu” để sử dụng `@DefaultValue`.
- Nếu bạn muốn chắc chắn một nhánh lồng nhau tồn tại dù không có dữ liệu, cần thiết kế mặc định cho nhánh ấy theo cơ chế binder phù hợp.

## 24. Giá trị “0” và thuộc tính không tồn tại

Giả sử:

```java
public record RetryOptions(int maxAttempts) {
}
```

Và nguồn chỉ có:

```java
Map.of("retry.mode", "safe")
```

Trong một tình huống constructor binding có dữ liệu trong prefix nhưng thiếu một primitive, object cuối có thể nhận giá trị mặc định của kiểu primitive, chẳng hạn `0` cho `int`.

Điều đó đặt ra câu hỏi: `0` là giá trị được người vận hành cố tình khai báo hay một hệ quả của việc thiếu property?

Nếu ứng dụng cần phân biệt hai trạng thái, có thể dùng kiểu tham chiếu:

```java
public record RetryOptions(Integer maxAttempts) {
}
```

và yêu cầu `@NotNull` khi có validation phù hợp.

Đối với cấu hình yêu cầu số lần thử dương, `@Min(1)` cũng là một ràng buộc thích hợp, nhưng cần nhớ **direct Binder không tự đồng nghĩa validation của bean đã được thực thi**.

## 25. Direct Binder không tự thực thi toàn bộ @Validated của Spring Boot

Xét record:

```java
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;

@Validated
public record RetryOptions(
        @Min(1) int maxAttempts) {
}
```

Một test tạo Binder thủ công:

```java
new Binder(source).bind("retry", RetryOptions.class)
```

chủ yếu kiểm tra binder và conversion. Không nên mặc định rằng chỉ gắn `@Validated` ở record sẽ khiến đối tượng được tạo qua **mọi lần gọi `new Binder(...)`** đều trải qua quy trình Bean Validation như một bean `@ConfigurationProperties` do ApplicationContext đăng ký.

Trong ứng dụng Boot, cơ chế đăng ký configuration properties có thể bố trí những `BindHandler`/validator thích hợp. Nhưng Binder tự tạo trong test là một thành phần cấp thấp hơn.

Nếu bạn muốn kiểm tra **Bean Validation đúng như lúc khởi động**, có hai hướng:

1. Dùng `ApplicationContextRunner` với bean `@ConfigurationProperties` được đăng ký và provider Jakarta Validation.
2. Tạo cơ chế validation một cách tường minh trong test, chẳng hạn lấy object từ Binder rồi gọi Jakarta `Validator`, hoặc cấu hình một validation bind handler phù hợp.

Không nên viết một Binder test mà `@Min(1)` chỉ nằm trên record, sau đó khẳng định runtime luôn từ chối giá trị 0 khi test chưa thực sự gọi validator.

## 26. Kiểm thử Bean Validation tường minh sau khi bind

Giả sử bạn muốn giữ test nhỏ nhưng vẫn xác nhận constraint Jakarta.

Record:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record JobOptions(
        @NotBlank String queue,
        @Min(1) int maxAttempts) {
}
```

Đầu vào:

```java
Map<String, Object> values = Map.of(
        "job.queue", " ",
        "job.max-attempts", "0"
);
```

Ví dụ test sử dụng Jakarta Validation API:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class JobOptionsValidationTest {

    @Test
    void validatesBoundObject() {
        JobOptions options = new Binder(
                new MapConfigurationPropertySource(
                        Map.of(
                                "job.queue", " ",
                                "job.max-attempts", "0"
                        )
                )
        ).bind("job", JobOptions.class).get();

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            var violations = validator.validate(options);

            assertThat(violations)
                    .extracting(v -> v.getPropertyPath().toString())
                    .contains("queue", "maxAttempts");
        }
    }
}
```

Điểm quan trọng:

- Binder tạo đối tượng từ dữ liệu string.
- Jakarta Validator kiểm tra object **sau đó**, theo yêu cầu rõ ràng trong mã test.
- Test cần một Bean Validation provider thích hợp trên test runtime classpath.
- Đây là một thử nghiệm riêng biệt cho việc phối hợp binding và validation; nó không chứng minh Spring ApplicationContext đã đăng ký bean hoặc tự bật validation.

Nếu muốn kiểm thử chính quy trình “fail fast khi khởi động”, dùng ApplicationContextRunner ở phần sau.

## 27. Direct Binder và giá trị unknown

Giả sử một record mong đợi:

```java
public record RetryOptions(int maxAttempts) {
}
```

nhưng nguồn viết sai:

```java
Map.of("retry.max-attemps", "5")
```

Khóa `max-attemps` không tương ứng với `maxAttempts`.

Một Binder test đơn giản chỉ hỏi:

```java
binder.bind("retry", RetryOptions.class)
```

không nên được coi là một **trình kiểm tra schema toàn bộ Map**. Binder chỉ liên kết những giá trị mà mục tiêu đòi hỏi, và hành vi với unknown field có thể được tùy chỉnh bởi bind handler trong các đường đi khác nhau.

Trong Spring Boot, annotation `@ConfigurationProperties(ignoreUnknownFields = false)` có thể giúp từ chối những thuộc tính không được liên kết trong phạm vi bean khi cơ chế configuration-properties binding thích hợp được sử dụng.

Tuy nhiên, **đừng mặc định một Binder tạo trực tiếp bằng `new Binder(source)` tự áp dụng cùng chính sách chỉ vì kiểu Java có annotation**.

Nếu cần kiểm tra unknown fields ở mức Binder, hãy tìm hiểu cơ chế `BindHandler` như `NoUnboundElementsBindHandler` và cấu hình nó một cách tường minh; hoặc dùng một context test gần với cơ chế thực tế hơn.

## 28. BindHandler dùng để làm gì?

Spring Boot có API `BindHandler` để can thiệp vào các giai đoạn liên kết, ví dụ trước/sau binding, xử lý lỗi và một số chính sách bổ sung.

Trong tình huống ứng dụng thực tế, bind handler có thể liên quan đến:

- kiểm tra những phần tử cấu hình chưa được liên kết;
- validation của đối tượng;
- cách xử lý một số tình huống lỗi cụ thể;
- quan sát/lập báo cáo trong những công cụ phục vụ phát triển.

Nhưng **một test cơ bản về chuyển kiểu không cần tự cài BindHandler**.

Ví dụ:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
                Map.of("worker.max-attempts", "4")
        )
);

int attempts = binder.bind(
        "worker.max-attempts", Integer.class
).get();
```

Nếu mục tiêu chỉ là chuyển `"4"` thành số nguyên, cấu trúc này đủ rõ ràng.

Khi thêm bind handler, hãy chắc rằng test của bạn thật sự kiểm tra **hành vi cụ thể do handler cung cấp**, không vô tình trộn lẫn nhiều loại lỗi.

## 29. Placeholder và khả năng giới hạn của Map Binder

Trong ứng dụng thật, giá trị cấu hình có thể dùng placeholder:

```properties
service.base-url=https://api.example.invalid
client.endpoint=\${service.base-url}/v1
```

Một `Environment` với property resolver phù hợp có thể giải quyết placeholder theo quy tắc của Spring.

Nhưng khi tạo Binder trực tiếp:

```java
new Binder(new MapConfigurationPropertySource(values))
```

bạn đang chủ động cấp một nguồn nhỏ và **không nhất thiết cấu hình cùng một `PlaceholdersResolver` như Binder tạo từ Spring Environment**.

Vì vậy, đừng viết test mặc định kỳ vọng mọi biểu thức `\${...}` sẽ được giải quyết hệt như khi ứng dụng Boot đã khởi động đầy đủ.

Nếu placeholder là trọng tâm test:

- Hãy cấu hình `PlaceholdersResolver` cho Binder một cách tường minh, hoặc
- Dùng `Binder.get(environment)` với `ConfigurableEnvironment` chứa nguồn dữ liệu thử nghiệm, hoặc
- Chọn `ApplicationContextRunner` để kiểm tra trong ngữ cảnh gần runtime hơn.

Phân biệt này đặc biệt quan trọng với test chuyển sang `URI` hoặc `Duration`: một placeholder chưa giải quyết có thể làm conversion thất bại dù cú pháp giá trị sau giải quyết hoàn toàn hợp lệ.

## 30. Sử dụng Binder.get(Environment) khi cần Environment thật hơn

Spring Boot có cách lấy Binder từ Spring `Environment` phù hợp, thay vì tự tạo MapConfigurationPropertySource.

Ví dụ trong một test đơn giản:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class EnvironmentBinderTest {

    @Test
    void bindsFromMockEnvironment() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("client.max-retries", "6");

        Integer retries = Binder.get(environment)
                .bind("client.max-retries", Integer.class)
                .get();

        assertThat(retries).isEqualTo(6);
    }
}
```

`MockEnvironment` thuộc các công cụ kiểm thử của Spring và có thể được cung cấp qua dependency test phù hợp.

Ví dụ này vẫn không yêu cầu khởi động toàn bộ ApplicationContext. Nó chỉ chuyển đầu vào từ một MapConfigurationPropertySource độc lập sang một Environment test.

**Nên chọn:**

- `new Binder(new MapConfigurationPropertySource(...))` khi muốn test rất nhỏ, kiểm soát chính xác các khóa.
- `Binder.get(environment)` khi cần xem cách binder tương tác với những PropertySource của một Environment, đặc biệt khi liên quan placeholder hay nhiều nguồn.

Không phải mọi khía cạnh của Spring Boot Config Data đều xuất hiện chỉ bằng cách tạo `MockEnvironment`. Nó không tự nạp profile-specific YAML như một SpringApplication thật.

## 31. Một ApplicationContextRunner test cho cùng hợp đồng

Để kiểm tra tính năng rộng hơn — bean có được đăng ký, bind và inject vào context không — có thể dùng `ApplicationContextRunner`.

Record:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        int maxRetries) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsAsSpringBean() {
        runner.withPropertyValues(
                "client.connect-timeout=3s",
                "client.max-retries=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            ClientProperties props =
                    context.getBean(ClientProperties.class);

            assertThat(props.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(props.maxRetries()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {
    }
}
```

Sự khác nhau:

| Tiêu chí | Direct Binder | ApplicationContextRunner |
| --- | --- | --- |
| Khởi tạo Spring context? | Không | Có, một context nhỏ |
| Cần đăng ký bean? | Không | Có |
| Tự chọn prefix trong lời gọi? | Có | Thường từ `@ConfigurationProperties` |
| Kiểm thử chuyển kiểu? | Có | Có |
| Kiểm thử bean registration? | Không | Có |
| Kiểm thử một số cơ chế binder của Boot context? | Một phần nếu cấu hình thủ công | Có, theo context cấu hình |
| Tốc độ và số thành phần | Tối giản | Nhiều hơn nhưng vẫn gọn |

Không nhất thiết viết cả hai loại test cho mọi lớp cấu hình. Chọn theo rủi ro và mục tiêu của dự án.

## 32. Độ ưu tiên các nguồn: Map Binder test chưa đủ để xác nhận Spring Boot

Bạn có thể dựng hai Map:

```java
MapConfigurationPropertySource first =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "6")
        );

MapConfigurationPropertySource second =
        new MapConfigurationPropertySource(
                Map.of("client.max-retries", "3")
        );
```

Sau đó:

```java
int retries = new Binder(
        java.util.List.of(first, second)
).bind("client.max-retries", Integer.class).get();

assertThat(retries).isEqualTo(6);
```

Test chứng minh thứ tự **mà chính bạn truyền vào Binder** có ảnh hưởng tới giá trị được chọn.

Nhưng thứ tự ưu tiên mặc định của Spring Boot khi có CLI, system properties, environment variables, profile-specific Config Data, `SPRING_APPLICATION_JSON` hoặc test properties là vấn đề rộng hơn.

Nếu muốn kiểm tra môi trường production có nhận đúng giá trị từ biến môi trường hay không, hãy test qua `Environment` hoặc SpringApplication phù hợp, không kết luận chỉ từ một Map Binder.

## 33. Giữ test không phụ thuộc giá trị cấu hình bên ngoài

Một trong những lợi thế của Map Binder là **test không bị ảnh hưởng bởi môi trường người chạy**.

Ví dụ:

```java
Map<String, Object> values = Map.of(
        "client.max-retries", "7",
        "client.connect-timeout", "500ms"
);
```

Dù shell chạy test có:

```text
CLIENT_MAXRETRIES=99
```

thì Binder trực tiếp với đúng Map trên không tự đọc biến ấy chỉ vì nó tồn tại trong process environment.

Điều này giúp test có kết quả ổn định ở máy developer và CI.

Nếu bạn chủ đích muốn đưa biến môi trường vào test, hãy xây nguồn phù hợp hoặc dùng Environment/context test thay vì lẫn lộn với một test thuần Map.

**Test isolation** là lợi ích lớn nhất của kỹ thuật: mỗi test sở hữu dữ liệu đầu vào của chính nó.

## 34. Tạo helper nhỏ để giảm lặp trong test

Khi có nhiều test cùng mẫu, có thể viết một helper:

```java
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

final class BinderTestSupport {

    private BinderTestSupport() {
    }

    static Binder binderOf(Map<String, ?> properties) {
        return new Binder(
                new MapConfigurationPropertySource(properties)
        );
    }
}
```

Sử dụng:

```java
Binder binder = BinderTestSupport.binderOf(
        Map.of(
                "client.timeout", "2s",
                "client.max-retries", "4"
        )
);
```

Helper này có lợi khi:

- Nhiều bài test cần cùng cách tạo Map Binder.
- Cần đổi sang một converter/placeholder resolver chung được định nghĩa tường minh.
- Muốn giữ từng test tập trung vào một tập property và kỳ vọng.

Nhưng đừng xây một framework test phức tạp đến mức che mất các khóa đầu vào. Một test tốt vẫn nên giúp người đọc thấy ngay **key → raw value → target type → expected value**.

## 35. Kiểm tra âm thầm bỏ qua lỗi chính tả

Một lỗi đánh máy:

```java
Map.of("client.connect-timout", "5s")
```

khác với:

```java
Map.of("client.connect-timeout", "5s")
```

Nếu test của bạn chỉ có happy path, nó không cho thấy ứng dụng sẽ làm gì khi người vận hành viết sai khóa.

Có thể viết hai test riêng:

**Test 1: khóa đúng**

```java
assertThat(
        new Binder(new MapConfigurationPropertySource(
                Map.of("client.connect-timeout", "5s")
        )).bind("client.connect-timeout", Duration.class).get()
).isEqualTo(Duration.ofSeconds(5));
```

**Test 2: khóa bị thiếu do sai tên**

```java
BindResult<Duration> result =
        new Binder(new MapConfigurationPropertySource(
                Map.of("client.connect-timout", "5s")
        )).bind("client.connect-timeout", Duration.class);

assertThat(result.isBound()).isFalse();
```

Kết quả của test 2 cho thấy Binder **không tự sửa tên khóa sai**.

Nếu hợp đồng yêu cầu khởi động thất bại khi có unknown field, cần cấu hình kiểm tra nghiêm ngặt trong đường đi binding thích hợp. Test `isBound()==false` không tương đương với việc runtime phát hiện và từ chối khóa sai.

## 36. Kiểm thử các giá trị biên

Một bộ test có giá trị nên bao gồm **dữ liệu bình thường, giá trị biên và dữ liệu sai**.

Ví dụ với timeout:

| Input | Kiểu đích | Kỳ vọng |
| --- | --- | --- |
| `1ms` | `Duration` | 1 millisecond |
| `500ms` | `Duration` | 500 milliseconds |
| `2s` | `Duration` | 2 seconds |
| `PT3S` | `Duration` | 3 seconds theo ISO-8601 |
| `invalid` | `Duration` | Binding/conversion failure |
| Không có khóa | `Duration` | `BindResult#isBound()==false` khi bind khóa đơn |

Với số nguyên:

| Input | Kiểu đích | Kỳ vọng |
| --- | --- | --- |
| `0` | `Integer` | `0`, đúng kiểu |
| `1` | `Integer` | `1` |
| `-1` | `Integer` | `-1`, đúng kiểu nhưng có thể sai nghiệp vụ |
| `many` | `Integer` | Lỗi conversion |
| Không có khóa | `Integer` | Không bound |

Một test Binder chỉ kiểm tra **hợp lệ về kiểu**, trừ khi bạn cấu hình thêm logic validation. Ví dụ `-1` có thể là số nguyên đúng kiểu dù số lần retry không được phép âm.

## 37. Đọc lỗi BindException thế nào?

Khi binding thất bại, có thể thấy `BindException` hoặc một exception liên quan do chuyển đổi hay tạo object.

Trong bài test, bạn có thể viết:

```java
BindException exception = assertThrows(
        BindException.class,
        () -> binder.bind("client.max-retries", Integer.class)
);
```

Với một input `"many"`, test có thể kiểm tra:

- lỗi có xảy ra không;
- đường dẫn property nào đang bind;
- kiểu đích yêu cầu;
- nguyên nhân chuyển đổi ở chuỗi `getCause()` nếu cần.

Tuy nhiên, thông điệp ngoại lệ có thể khác nhau giữa phiên bản Spring Boot. Không nên so sánh nguyên văn toàn bộ đoạn log nhiều dòng trong assertion khi mục tiêu là xác nhận thất bại chuyển kiểu.

Một assertion gọn tập trung vào **loại lỗi và điều kiện kích hoạt** thường bền vững hơn.

## 38. Kiểm thử chuyển đổi kiểu tùy chỉnh

Có khi cấu hình cần một kiểu miền riêng.

Giả sử:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null
                || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "RegionCode phải có dạng XX-YY");
        }
    }
}
```

Nguồn:

```properties
routing.region=vn-sg
```

Nếu muốn chuyển tự động `"vn-sg"` thành `RegionCode("VN-SG")`, có thể tạo `Converter<String,RegionCode>`:

```java
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Trong bài test Binder trực tiếp, bạn cần **cấu hình converter vào hệ thống chuyển đổi mà Binder sử dụng**. Chỉ khai báo class converter trong source code chưa đảm bảo `new Binder(mapSource)` tự phát hiện nó.

Một cách trình bày cấp cao:

```text
MapConfigurationPropertySource
            |
            v
        Binder đã được cấu hình
            |
            v
  ConversionService có converter
            |
            v
        RegionCode("VN-SG")
```

Ở runtime, Spring Boot có thể nhận converter cho `@ConfigurationProperties` từ bean được gắn `@ConfigurationPropertiesBinding`. Nhưng Binder tự tạo **không tự component-scan** các bean ấy.

Đây là ranh giới quan trọng khi unit test custom conversion: nếu test dùng Converter trực tiếp, bạn chỉ kiểm tra logic `convert(...)`; nếu muốn xác nhận Binder thật sự áp dụng Converter, phải đăng ký converter với Binder hoặc tạo context test có cơ chế converter tương ứng.

## 39. Ví dụ Binder có ConversionService tùy chỉnh

Để kiểm thử tích hợp giữa Map Binder và một converter riêng, có thể tạo một ConversionService và truyền cho constructor Binder cho phép nhận danh sách converter.

Ví dụ minh họa sử dụng các kiểu Spring Boot 3.x:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import org.springframework.core.convert.ConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

class CustomConverterExample {

    static RegionCode bindRegion() {
        DefaultFormattingConversionService conversions =
                new DefaultFormattingConversionService();

        conversions.addConverter(
                String.class,
                RegionCode.class,
                raw -> new RegionCode(
                        raw.trim().toUpperCase(Locale.ROOT))
        );

        MapConfigurationPropertySource source =
                new MapConfigurationPropertySource(
                        Map.of("routing.region", "vn-sg")
                );

        Binder binder = new Binder(
                List.of(source),
                null,
                conversions
        );

        return binder.bind("routing.region", RegionCode.class).get();
    }
}
```

`DefaultFormattingConversionService` ở đây chỉ đóng vai trò một conversion service dùng cho ví dụ custom type. Với những kiểu cấu hình chuẩn của Boot, cần lưu ý `ApplicationConversionService` cung cấp thêm các converter hữu ích cho `Duration` và `DataSize`.

Tùy phiên bản Spring Boot, các overload của Binder hoặc cách truyền conversion service có thể khác nhau; hãy sử dụng constructor signature của version đang dùng. Khi mục tiêu là kiểm tra converter của **Spring Boot runtime**, `ApplicationContextRunner` với converter bean được đánh dấu `@ConfigurationPropertiesBinding` là một lựa chọn sát thực tế hơn.

Ý chính vẫn là: **test cần đăng ký converter rõ ràng** nếu muốn xác nhận phép chuyển riêng được Binder sử dụng.

## 40. Không trộn custom conversion với kiểm tra schema

Custom converter có thể kiểm tra biểu diễn của một giá trị, ví dụ RegionCode phải đúng `XX-YY`.

Nhưng nó không tự giải quyết:

- Một khóa sai tên như `routing.regoin`.
- Một nhóm cấu hình thiếu hoàn toàn.
- Việc một profile khác chưa được nạp.
- Việc một service không được đăng ký trong context.
- Thứ tự ưu tiên giữa CLI và Config Data.
- Một tập Map có những khóa không mong muốn.

Nếu muốn giới hạn một nhóm khóa, cần kiểm soát namespace và chiến lược unknown fields. Nếu muốn yêu cầu giá trị bắt buộc, cần default hoặc validation. Nếu muốn kiểm chứng loader, cần test loader/context.

Bài học: **giữ các trách nhiệm tách biệt**, để khi một test thất bại bạn có thể xác định rõ tầng gây lỗi.

## 41. Test theo phương pháp Given–When–Then

Một cách viết bài test dễ đọc:

**Given — dữ liệu đầu vào nhỏ**

```java
Map<String, Object> input = Map.of(
        "client.connect-timeout", "500ms"
);
```

**When — Binder thực hiện liên kết**

```java
Duration result = new Binder(
        new MapConfigurationPropertySource(input)
).bind("client.connect-timeout", Duration.class).get();
```

**Then — so sánh giá trị Java**

```java
assertThat(result).isEqualTo(Duration.ofMillis(500));
```

Một phương thức test gọn có thể kết hợp cả ba phần:

```java
@Test
void bindsDurationFromMilliseconds() {
    // Given
    MapConfigurationPropertySource source =
            new MapConfigurationPropertySource(
                    Map.of("client.connect-timeout", "500ms")
            );

    // When
    Duration timeout = new Binder(source)
            .bind("client.connect-timeout", Duration.class)
            .get();

    // Then
    assertThat(timeout).isEqualTo(Duration.ofMillis(500));
}
```

Đầu vào và kết quả hiển nhiên, giúp người khác đọc test mà không cần chạy cả Spring Boot application để suy luận.

## 42. Test có nên dùng nhiều giá trị cùng lúc?

Nếu mục tiêu là kiểm tra **một converter cụ thể**, nên chỉ thử một hoặc vài khóa:

```java
Map.of("upload.max-size", "2MB")
```

Nếu mục tiêu là kiểm tra **constructor binding của một record**, đưa đủ các trường liên quan:

```java
Map.of(
        "client.endpoint", "https://api.example.invalid",
        "client.connect-timeout", "5s",
        "client.max-retries", "4",
        "client.enabled", "true"
)
```

Không nhất thiết đưa vào hàng chục khóa unrelated như `spring.datasource.password`, `logging.level.root` hay `server.port`. Các khóa ấy làm bài test mất tính cô lập và có thể vô tình khiến người đọc nghĩ rằng một Binder trực tiếp đang kiểm thử toàn bộ Spring Boot runtime.

**Dữ liệu nhỏ không có nghĩa là test sơ sài; nó nghĩa là test được thiết kế để nguyên nhân thất bại luôn dễ xác định.**

## 43. Nên đặt test ở đâu?

Một cấu trúc dự án:

```text
src/
  main/
    java/
      com/example/configdemo/
        ClientProperties.java
    resources/
      application.yml
  test/
    java/
      com/example/configdemo/
        ClientPropertiesBinderTest.java
        ClientPropertiesContextTest.java
        ClientPropertiesValidationTest.java
```

Ba bài test có trách nhiệm khác nhau:

- `ClientPropertiesBinderTest`: chuyển kiểu và bind với Map nhỏ.
- `ClientPropertiesContextTest`: đăng ký bean/configuration properties trong context.
- `ClientPropertiesValidationTest`: các ràng buộc bắt buộc và miền dữ liệu.

Không cần tạo cả ba file cho mọi record nhỏ. Cấu trúc trên là cách tách khi dự án đủ phức tạp và những lớp bảo vệ khác nhau cần được kiểm chứng độc lập.

Nếu test đang bị chậm vì phải boot toàn bộ application context trong khi chỉ kiểm tra `Duration`, hãy cân nhắc chuyển trường hợp đó thành Binder test.

## 44. Một bộ test tổng hợp cho hợp đồng cấu hình

Một ví dụ hoàn chỉnh, dễ dùng trong dự án Spring Boot:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class ClientConfigBindingTest {

    private static Binder binderOf(Map<String, ?> values) {
        return new Binder(
                new MapConfigurationPropertySource(values)
        );
    }

    @Test
    void bindsRecordWithTypedFields() {
        ClientProperties options = binderOf(
                Map.of(
                        "client.endpoint",
                        "https://api.example.invalid",
                        "client.connect-timeout", "3s",
                        "client.max-retries", "4",
                        "client.enabled", "true"
                )
        ).bind("client", ClientProperties.class).get();

        assertThat(options.endpoint())
                .isEqualTo(URI.create("https://api.example.invalid"));
        assertThat(options.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(options.maxRetries()).isEqualTo(4);
        assertThat(options.enabled()).isTrue();
    }

    @Test
    void reportsMissingSingleProperty() {
        Binder binder = binderOf(
                Map.of("client.enabled", "true")
        );

        assertThat(
                binder.bind("client.connect-timeout", Duration.class)
                      .isBound()
        ).isFalse();
    }

    @Test
    void rejectsInvalidInteger() {
        Binder binder = binderOf(
                Map.of("client.max-retries", "many")
        );

        assertThrows(BindException.class, () ->
                binder.bind("client.max-retries", Integer.class)
        );
    }

    @Test
    void bindsMilliseconds() {
        Binder binder = binderOf(
                Map.of("client.connect-timeout", "750ms")
        );

        assertThat(
                binder.bind("client.connect-timeout", Duration.class)
                      .get()
        ).isEqualTo(Duration.ofMillis(750));
    }
}
```

Record dùng cho ví dụ:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
```

Nếu record này đồng thời được dùng làm Spring bean trong ứng dụng thật, có thể bổ sung `@ConfigurationProperties(prefix="client")` và đăng ký nó phù hợp. Test Binder trực tiếp vẫn tự chọn prefix `client`.

Bộ test tập trung vào đúng bốn mục tiêu: **tạo object có kiểu, khóa vắng mặt, chuyển kiểu thất bại và đơn vị thời gian**.

## 45. Những nhầm lẫn phổ biến

### 45.1. “Muốn test @ConfigurationProperties phải luôn dùng @SpringBootTest”

Không. Với mục tiêu liên kết và chuyển kiểu, Binder với nguồn Map nhỏ có thể đủ.

### 45.2. “MapConfigurationPropertySource đọc application.yml”

Không. Nó bọc những giá trị bạn đã đưa vào Map. Nếu muốn kiểm tra YAML loading, chọn test khác.

### 45.3. “Gắn @ConfigurationProperties là đủ để new Binder biết prefix”

Không nên giả định vậy. Trong direct Binder test, bạn chỉ định prefix qua `binder.bind("client", ...)`.

### 45.4. “Một BindResult không bound nghĩa là lỗi chuyển đổi”

Không. Không bound thường có nghĩa không có giá trị phù hợp để liên kết. Conversion failure có thể ném exception.

### 45.5. “Kiểm tra Integer=−1 nghĩa là @Min đã chạy”

Không. Chuyển thành `int -1` có thể thành công; validation nghiệp vụ là trách nhiệm khác.

### 45.6. “@Validated tự chạy ở mọi lời gọi new Binder(...)”

Không nên mặc định. Direct Binder không phải toàn bộ configuration-properties lifecycle của Spring context.

### 45.7. “Custom Converter trong source tự được Binder nhận”

Không. Cần đăng ký converter vào service/handler mà Binder sử dụng hoặc kiểm tra qua context có cơ chế đăng ký.

### 45.8. “Test Binder với hai Map chứng minh toàn bộ Boot precedence”

Không. Nó chỉ chứng minh thứ tự các nguồn do test chủ động đưa vào Binder.

### 45.9. “Map chứa Duration sẵn cũng kiểm tra String-to-Duration conversion”

Không đầy đủ. Muốn thử conversion, hãy đưa `"3s"` dưới dạng chuỗi đầu vào.

### 45.10. “Test Binder với Map đủ bảo đảm cấu hình prod”

Không. Profile, Config Data imports, external file paths và environment của deployment cần kiểm thử riêng.

### 45.11. “Không có context thì không thể test validation”

Có thể gọi Jakarta Validator tường minh sau khi bind; nhưng nếu muốn kiểm tra hành vi fail fast của context, cần context test.

### 45.12. “Sai khóa chính tả sẽ luôn được Binder tự sửa”

Không. Relaxed binding hỗ trợ biến thể trình bày tên, không phải công cụ sửa mọi lỗi đánh máy.

## 46. Quy trình chọn mức kiểm thử phù hợp

Khi chuẩn bị một test cấu hình, hãy trả lời theo thứ tự:

**Câu 1 — Tôi đang kiểm tra tên khóa và chuyển kiểu đơn giản?**

Dùng:

```java
Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);
```

**Câu 2 — Tôi đang kiểm tra cấu trúc nested object, List hay Map?**

Binder test vẫn phù hợp; đưa đúng tên dạng dotted/indexed và giữ dữ liệu đầu vào nhỏ.

**Câu 3 — Tôi cần kiểm tra một converter custom có thực sự được đăng ký?**

Dùng Binder được cấp converter tường minh hoặc một ApplicationContextRunner với bean converter được đăng ký.

**Câu 4 — Tôi muốn kiểm tra @Validated, bean registration hoặc cơ chế @ConfigurationProperties của Spring context?**

Ưu tiên ApplicationContextRunner. Nếu cần toàn ứng dụng, dùng `@SpringBootTest`.

**Câu 5 — Tôi muốn chắc rằng application-prod.yml được nạp theo profile prod?**

Dùng integration test có profile và Config Data thực tế.

**Câu 6 — Tôi muốn kiểm tra lệnh java -jar ngoài production có đủ biến môi trường, config location và secret?**

Cần smoke/integration test trên artifact và phương thức khởi chạy phù hợp, không chỉ một unit-level Binder test.

Một thiết kế kiểm thử tốt không phải chọn duy nhất một tầng; đó là **dùng đúng tầng cho đúng rủi ro**.

## 47. Bài tập A — bind một số nguyên

Tạo Map:

```java
Map.of("scheduler.pool-size", "12")
```

Yêu cầu: dùng Binder để nhận một `Integer` có giá trị 12.

Lời giải:

```java
Integer size = new Binder(
        new MapConfigurationPropertySource(
                Map.of("scheduler.pool-size", "12")
        )
).bind("scheduler.pool-size", Integer.class).get();

assertThat(size).isEqualTo(12);
```

## 48. Bài tập B — Duration và DataSize

Đầu vào:

```java
Map.of(
        "upload.timeout", "1500ms",
        "upload.max-size", "3MB"
)
```

Hỏi:

1. `upload.timeout` chuyển sang `Duration` tương đương bao nhiêu giây?
2. `upload.max-size` chuyển sang `DataSize` tương đương bao nhiêu byte?

Đáp án:

- `1500ms` tương đương `Duration.ofMillis(1500)`, tức 1,5 giây.
- `3MB` tương đương `3 * 1024 * 1024` byte theo quy ước `DataSize` thường dùng của Boot.

Có thể xác minh bằng:

```java
assertThat(
        binder.bind("upload.timeout", Duration.class).get()
).isEqualTo(Duration.ofMillis(1500));

assertThat(
        binder.bind("upload.max-size", DataSize.class)
              .get().toBytes()
).isEqualTo(3L * 1024 * 1024);
```

## 49. Bài tập C — thiếu khóa và sai kiểu

Cho hai Map:

```java
Map.of("task.enabled", "true")
```

và:

```java
Map.of("task.max-attempts", "many")
```

Khi bind `task.max-attempts` thành `Integer`:

- Map thứ nhất **không có khóa** cần bind; kết quả thường không bound.
- Map thứ hai **có khóa nhưng sai dạng giá trị**; có thể gây `BindException`.

Hãy viết hai test với `isBound()` và `assertThrows(...)` tương ứng.

## 50. Bài tập D — record lồng nhau

Record:

```java
public record CacheOptions(Retry retry) {

    public record Retry(int attempts, Duration delay) {
    }
}
```

Nguồn:

```java
Map.of(
        "cache.retry.attempts", "3",
        "cache.retry.delay", "250ms"
)
```

Lời giải:

```java
CacheOptions options = new Binder(
        new MapConfigurationPropertySource(
                Map.of(
                        "cache.retry.attempts", "3",
                        "cache.retry.delay", "250ms"
                )
        )
).bind("cache", CacheOptions.class).get();

assertThat(options.retry().attempts()).isEqualTo(3);
assertThat(options.retry().delay())
        .isEqualTo(Duration.ofMillis(250));
```

## 51. Bài tập E — tìm giới hạn của Binder test

Một nhóm phát hiện:

- Binder test với `client.timeout=5s` thành công.
- Khi chạy JAR ở production, timeout vẫn là 30 giây.

Có thể kết luận Binder bị lỗi không?

**Chưa thể.** Hãy kiểm tra giá trị có hiệu lực ở production: profile nào đang hoạt động, CLI/environment/system property có ghi đè không, file Config Data nào đã được nạp, và JAR có phải phiên bản mong đợi không.

Binder test chỉ xác nhận hành vi với tập đầu vào nhỏ **được khai báo trong chính test**.

## 52. Bài tập F — mặc định và validation

Một record:

```java
public record RetryOptions(
        @DefaultValue("3") int attempts) {
}
```

Nguồn có:

```java
Map.of("retry.mode", "safe")
```

Hỏi:

1. Binder có thể dùng giá trị mặc định nào cho `attempts`?
2. Nếu nguồn có `retry.attempts=many`, có tự quay về `3` không?
3. Gắn `@Min(1)` có khiến direct Binder test tự thực thi Jakarta Validation không?

Đáp án:

1. Trong constructor binding phù hợp, mặc định được khai báo là `3`.
2. Không nên mặc định như vậy; giá trị có mặt nhưng sai kiểu có thể gây binding failure.
3. Không tự suy ra; cần gọi validator tường minh hoặc dùng Spring context test có cơ chế validation phù hợp.

## 53. Ghi nhớ

- **`Binder` cho phép kiểm tra configuration binding mà không cần khởi chạy Spring ApplicationContext.**
- **`MapConfigurationPropertySource`** là nguồn nhỏ, rõ ràng, phù hợp với unit-level test.
- `Binder#bind(...)` trả về **`BindResult<T>`**; dùng `isBound()` trước khi gọi `get()` nếu giá trị có thể vắng mặt.
- Binder phối hợp **tra cứu tên khóa và chuyển đổi kiểu**; có thể kiểm tra String thành `Integer`, `Boolean`, `Duration`, `DataSize`, `URI` hoặc enum.
- Với record, Binder có thể thực hiện **constructor binding**; test được cả nested record, danh sách indexed và Map.
- Đầu vào nên giữ dạng **chuỗi thô** nếu mục tiêu là kiểm tra conversion thật, tránh đưa sẵn Java object đã chuyển đổi.
- **Khóa vắng mặt** khác **khóa có mặt nhưng sai kiểu**; test hai trường hợp bằng assertion riêng.
- Direct Binder test **không tự chứng minh** bean `@ConfigurationProperties` được scan/đăng ký, validator đã chạy, placeholder được giải quyết giống runtime, hoặc file/profile được nạp đúng.
- Với custom converter, phải cấu hình conversion phù hợp; một class `Converter` không tự được Binder phát hiện.
- Dùng `ApplicationContextRunner` khi cần kiểm tra tích hợp của binder với Spring bean registration và validation; dùng `@SpringBootTest` hoặc smoke test khi cần xác nhận cấu hình ở phạm vi ứng dụng/artifact.
- Một bộ kiểm thử đáng tin cậy kết hợp **Binder test nhỏ cho luật liên kết**, **context test cho wiring và validation**, và **integration/smoke test cho môi trường triển khai**.
