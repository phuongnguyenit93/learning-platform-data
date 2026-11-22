# Chuyển đổi kiểu với ApplicationConversionService và @EndpointConverter

## 1. Vì sao endpoint cần bước chuyển đổi kiểu?

Một công cụ vận hành có thể gửi yêu cầu:

```text
GET /actuator/conversionpreview?attempts=3&enabled=true&backoff=250ms&range=2..4
```

Ở phía yêu cầu, các giá trị query là chuỗi. Nhưng phương thức Java muốn nhận:

- `int attempts` để làm việc với số.
- `boolean enabled` để thể hiện lựa chọn bật/tắt.
- `Duration backoff` để thể hiện thời lượng có đơn vị.
- `WorkerRange range` để thể hiện một khoảng worker có cấu trúc và điều kiện hợp lệ.

Nếu mọi operation đều nhận `String` rồi tự tách chuỗi, chuyển số và bắt lỗi, logic tiếp nhận đầu vào sẽ lặp lại. **Chuyển đổi kiểu (type conversion)** đưa bước diễn giải giá trị về một cơ chế chung trước khi gọi operation.

Spring Boot Actuator dùng một `ApplicationConversionService` cùng các bean `Converter` hoặc `GenericConverter` được đánh dấu `@EndpointConverter` để chuyển đầu vào HTTP/JMX sang kiểu tham số cần thiết. Đây là hợp đồng được mô tả trong [Spring Boot 3.3: Input Type Conversion](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input-type-conversion).

### Các thành phần cần phân biệt

| Thành phần | Vai trò |
| --- | --- |
| `ConversionService` | API yêu cầu chuyển một giá trị sang kiểu đích |
| `ApplicationConversionService` | Cấu hình converter/formatter phù hợp với nhiều kiểu dữ liệu của Spring Boot |
| `Converter<S, T>` | Quy tắc chuyển một kiểu nguồn S thành một kiểu đích T |
| `GenericConverter` | Quy tắc linh hoạt hơn, có thể khai báo nhiều cặp kiểu và dùng mô tả kiểu |
| `@EndpointConverter` | Qualifier để Actuator chọn converter bean cho đầu vào operation |
| JSON deserialization | Bước đọc văn bản JSON thành dữ liệu ban đầu, không đồng nhất với converter tham số |

Bài dùng Java 21 và Spring Boot 3.3.0 để xây ví dụ có thể chạy độc lập.

## 2. Chuyển đổi diễn ra ở đâu?

Với operation được công bố qua HTTP, có thể hình dung:

```text
Yêu cầu HTTP
    -> khớp operation và thu thập đối số theo tên
    -> đọc query/path hoặc các trường ở cấp gốc của JSON body
    -> chuyển mỗi đối số sang kiểu Java cần thiết
    -> gọi operation
    -> chuyển kết quả thành phản hồi HTTP
```

Bước chuyển kiểu không chọn URL hay HTTP method. Nó cũng không phải bước chuyển đối tượng kết quả thành JSON.

Trong một JSON body như:

```json
{
  "attempts": 3,
  "enabled": true,
  "backoff": "250ms",
  "range": "2..4"
}
```

số và boolean có thể đã được bộ đọc JSON biểu diễn bằng giá trị Java phù hợp. `backoff` và `range` vẫn cần được diễn giải thành `Duration` và `WorkerRange`.

Vì vậy, không nên giả định rằng **mọi** đầu vào của converter đều là chuỗi chỉ vì yêu cầu đến từ HTTP. Hãy khai báo đúng cặp kiểu mà converter thực sự hỗ trợ.

Nếu thiếu tham số bắt buộc hoặc không chuyển được giá trị sang kiểu cần thiết, operation không được gọi và web endpoint trả 400. Trong JMX, lỗi không được biểu diễn bằng HTTP status; cần xem cơ chế phản hồi của giao thức đang sử dụng.

Tên tham số là một phần riêng của quá trình ánh xạ. Mã Java cần được biên dịch với `-parameters` để framework đọc tên đối số. Một converter đúng không sửa được lỗi do mất tên tham số hoặc gửi sai tên trường.

## 3. Dùng khả năng có sẵn trước khi viết converter mới

`ApplicationConversionService` là một chuyên biệt của `FormattingConversionService`, được cấu hình với các converter và formatter của Spring Boot. Nó có thể được tạo trực tiếp và cũng cung cấp các phương thức đăng ký converter vào registry. Xem [ApplicationConversionService API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/ApplicationConversionService.html).

Trong ví dụ này:

| Đầu vào | Kiểu đích | Kết quả |
| --- | --- | --- |
| `"3"` | Integer/int | 3 |
| `"true"` | Boolean/boolean | true |
| `"250ms"` | Duration | 250 mili giây |
| `"PT2S"` | Duration | 2 giây |
| `"2..4"` | WorkerRange | Cần converter riêng của ví dụ |

Khi truyền thời lượng, nên dùng đơn vị hoặc định dạng rõ ràng như `250ms`, `2s` hay `PT2S`. Tránh dựa vào một con số không có đơn vị rồi để các bên hiểu khác nhau.

Không cần viết lại converter từ chuỗi sang số chỉ để nhận `attempts=3`. Hãy thêm converter khi có một kiểu giá trị hoặc định dạng đầu vào mà cơ chế hiện tại chưa diễn đạt theo hợp đồng mong muốn.

### Chuyển được kiểu chưa có nghĩa là hợp lệ về nghiệp vụ

`"-1"` có thể chuyển thành một số nguyên. Cơ chế chuyển kiểu không tự biết ứng dụng chỉ cho phép số lần thử trong khoảng 1..5.

Tương tự, `Duration` biểu diễn được một thời lượng không có nghĩa thời lượng đó phù hợp với giới hạn timeout, tài nguyên hoặc chính sách của hệ thống.

Cần tách:

1. **Biểu diễn:** có đọc được giá trị thành kiểu cần thiết không?
2. **Điều kiện của kiểu giá trị:** đối tượng này có thỏa các bất biến của chính nó không?
3. **Quy tắc thao tác:** với người gọi và trạng thái hiện tại, giá trị đó có được sử dụng không?

Converter phù hợp với hai phần đầu khi chúng thuộc ý nghĩa ổn định của kiểu giá trị. Phần thứ ba thường thuộc logic xử lý và chính sách truy cập của ứng dụng.

## 4. Thiết kế một converter nhỏ và rõ

Ta chọn hợp đồng biểu diễn khoảng worker:

```text
first..last
```

Ví dụ `2..4` nghĩa là các worker từ 2 đến 4. Kiểu `WorkerRange` của mẫu yêu cầu:

```text
1 <= first <= last <= 32
```

Đây là một giá trị đầu vào có biểu diễn chuỗi đơn, không phải yêu cầu bind một cây JSON tùy ý vào DTO.

### 4.1. Converter<S, T>

Một converter khai báo rõ:

```java
implements Converter<String, WorkerRange>
```

Quy trình của nó:

1. Chuẩn hóa khoảng trắng ngoài theo chính sách của mẫu.
2. Kiểm tra cú pháp `first..last`.
3. Chuyển hai phần thành số nguyên.
4. Tạo `WorkerRange`, để constructor kiểm tra bất biến.

Khi chuỗi không hợp lệ, converter ném `IllegalArgumentException`. Cơ chế conversion bọc lỗi chuyển đổi; Actuator xử lý lỗi ánh xạ đối số thành 400 trước khi gọi operation.

Theo [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), converter cần an toàn khi dùng đồng thời và có thể báo giá trị nguồn không hợp lệ bằng ngoại lệ thích hợp. Với mẫu này, converter không giữ dữ liệu yêu cầu trong field và không thực hiện I/O.

Không đưa truy vấn cơ sở dữ liệu, gọi mạng, phân quyền hoặc bắt đầu công việc vào `convert()`. Một bước chuyển đổi nên có kết quả rõ từ đầu vào và không tạo hiệu ứng phụ.

### 4.2. Khi nào cần GenericConverter?

`Converter<S, T>` phù hợp khi chỉ cần một cặp kiểu nguồn–đích rõ ràng. `GenericConverter` hữu ích khi cần nhiều cặp kiểu hoặc cần đọc `TypeDescriptor`.

Không cần dùng `GenericConverter` cho mọi converter để “linh hoạt hơn”. Nó tăng trách nhiệm xác định cặp kiểu và kiểm tra nguồn/đích. Cũng không nên khai báo một converter quá rộng như từ mọi `Object` sang một kiểu tùy chỉnh khi hợp đồng thực tế chỉ chấp nhận chuỗi.

## 5. Đăng ký bean và qualifier là hai việc khác nhau

Ví dụ đăng ký đúng cho Actuator:

```java
@Bean
@EndpointConverter
WorkerRangeConverter endpointWorkerRangeConverter() {
    return new WorkerRangeConverter();
}
```

- `@Bean` tạo đối tượng do Spring quản lý.
- `@EndpointConverter` đánh dấu đối tượng để cơ chế conversion của endpoint chọn.
- `WorkerRangeConverter` triển khai `Converter<String, WorkerRange>`, cung cấp quy tắc chuyển đổi thực tế.

Chỉ đặt `@EndpointConverter` lên một lớp chưa được đăng ký không tự tạo bean. Ngược lại, chỉ có một converter bean thông thường không bảo đảm Actuator sử dụng nó cho operation.

Mẫu dùng một lớp cụ thể thay vì một biểu thức lambda để kiểu nguồn và kiểu đích được thể hiện rõ trên khai báo lớp. Khi đăng ký converter, cần giữ đủ thông tin kiểu cho cơ chế phát hiện.

**Qualifier không phải cơ chế cách ly tuyệt đối.** Nó chỉ cho Actuator biết converter nào cần chọn theo hợp đồng của Actuator. Một hệ thống khác có thể có quy tắc thu thập bean riêng; vấn đề này được giải thích thêm ở mục 9.

## 6. Ứng dụng ví dụ chạy được

Ứng dụng chỉ xem trước các giá trị sau chuyển đổi. Nó không gửi công việc, không thay đổi cấu hình worker thật và không kiểm tra quyền quản lý một nhóm worker thực tế.

### 6.1. Cấu trúc dự án và phụ thuộc

```text
endpoint-conversion-demo/
├── pom.xml
└── src/main/
    ├── java/example/endpointconversion/EndpointConversionApplication.java
    └── resources/application.properties
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>endpoint-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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
```

Mẫu dùng Maven và JDK 21; cấu hình compiler từ Spring Boot starter parent giữ tên tham số cần cho operation. Khi đưa các thành phần vào ứng dụng đã có build, kiểm tra cờ `-parameters` trong cấu hình hiện có thay vì thay toàn bộ build bằng mẫu.

### 6.2. Mã Java

Tệp `src/main/java/example/endpointconversion/EndpointConversionApplication.java`:

```java
package example.endpointconversion;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.EndpointConverter;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.core.convert.converter.Converter;

@SpringBootApplication
public class EndpointConversionApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointConversionApplication.class, args);
    }

    @Bean
    PreviewEndpoint previewEndpoint() {
        return new PreviewEndpoint();
    }

    @Bean
    @EndpointConverter
    @ConditionalOnProperty(name = "demo.endpoint-qualified",
            havingValue = "true", matchIfMissing = true)
    WorkerRangeConverter endpointWorkerRangeConverter() {
        return new WorkerRangeConverter();
    }

    @Bean
    @ConditionalOnProperty(name = "demo.endpoint-qualified",
            havingValue = "false")
    WorkerRangeConverter ordinaryWorkerRangeConverter() {
        return new WorkerRangeConverter();
    }

    public record WorkerRange(int first, int last) {
        public WorkerRange {
            if (first < 1 || last > 32 || first > last) {
                throw new IllegalArgumentException(
                        "Expected 1 <= first <= last <= 32");
            }
        }
    }

    public static class WorkerRangeConverter
            implements Converter<String, WorkerRange> {
        private static final Pattern FORMAT =
                Pattern.compile("([0-9]+)\\.\\.([0-9]+)");

        @Override
        public WorkerRange convert(String source) {
            var match = FORMAT.matcher(source.trim());
            if (!match.matches()) {
                throw new IllegalArgumentException(
                        "Expected first..last");
            }
            return new WorkerRange(
                    Integer.parseInt(match.group(1)),
                    Integer.parseInt(match.group(2)));
        }
    }

    public record Preview(int attempts, boolean enabled, long backoffMs,
            int firstWorker, int lastWorker) {
    }

    @Endpoint(id = "conversionpreview")
    public static class PreviewEndpoint {
        private final AtomicInteger calls = new AtomicInteger();

        @ReadOperation
        public Preview read(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            return preview(attempts, enabled, backoff, range);
        }

        @WriteOperation
        public Preview write(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            return preview(attempts, enabled, backoff, range);
        }

        private Preview preview(int attempts, boolean enabled,
                Duration backoff, WorkerRange range) {
            calls.incrementAndGet();
            return new Preview(attempts, enabled, backoff.toMillis(),
                    range.first(), range.last());
        }

        public int invocationCount() {
            return calls.get();
        }
    }
}
```

Hai bean converter được đặt dưới các điều kiện đối nhau để phục vụ thí nghiệm:

| demo.endpoint-qualified | Bean được tạo | Có @EndpointConverter |
| --- | --- | --- |
| true hoặc không khai báo | endpointWorkerRangeConverter | Có |
| false | ordinaryWorkerRangeConverter | Không |

Mỗi lần chạy chỉ có một bean converter của mẫu. Thay đổi thuộc tính rồi khởi động lại giúp kiểm tra khác biệt giữa “bean tồn tại” và “bean được Actuator chọn”.

Bộ đếm `calls` chỉ dùng để kiểm tra operation đã được gọi hay chưa. `invocationCount()` không có annotation operation nên không tự trở thành một URL Actuator. Nó có thể được đọc từ bean trong bài test.

### 6.3. Cấu hình và chạy

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,conversionpreview
demo.endpoint-qualified=true
```

Mẫu chỉ lắng nghe trên loopback và không thêm Spring Security để tách việc học conversion khỏi cấu hình xác thực. Trong hệ thống thật, cần áp dụng chính sách truy cập thích hợp cho endpoint quản lý.

Chạy từ thư mục chứa `pom.xml`:

```shell
mvn spring-boot:run
```

## 7. Quan sát chuyển đổi qua query và JSON

### 7.1. Query string: chuyển chuỗi thành tham số Java

Trong PowerShell, đặt toàn bộ URL trong dấu nháy để ký tự `&` không bị shell hiểu sai:

```powershell
curl.exe -sS 'http://127.0.0.1:8080/actuator/conversionpreview?attempts=3&enabled=true&backoff=250ms&range=2..4'
```

Phản hồi 200 với body:

```json
{"attempts":3,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

Operation đã nhận số nguyên, boolean, Duration và WorkerRange. Nó không cần tự gọi `Integer.parseInt` cho `attempts` hoặc tách `range` trong thân phương thức.

### 7.2. JSON body: không phải mọi giá trị đều cần cùng converter

Gửi POST bằng PowerShell:

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/conversionpreview' -ContentType 'application/json' -Body '{"attempts":3,"enabled":true,"backoff":"250ms","range":"2..4"}'
$r.StatusCode
$r.Content
```

Kết quả:

```text
200
{"attempts":3,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

Các thuộc tính ở cấp gốc được ghép với đối số operation. `attempts` và `enabled` trong JSON đã là số và boolean; `range` vẫn là chuỗi nên cần converter tương ứng. Thao tác POST trong mẫu chỉ xem trước kết quả, không thực thi một công việc nền.

### 7.3. Vì sao JSON object lồng không tự hoạt động?

Thay riêng `range` bằng:

```json
{
  "attempts": 3,
  "enabled": true,
  "backoff": "250ms",
  "range": {
    "first": 2,
    "last": 4
  }
}
```

Với chính ứng dụng mẫu, phản hồi là 400 và operation không được gọi.

Nguồn lúc này là một cấu trúc map sau khi đọc JSON, không phải chuỗi `"2..4"`. Converter `String -> WorkerRange` không có trách nhiệm chuyển mọi cấu trúc JSON thành `WorkerRange`.

Đó cũng là lý do không nên xem `@EndpointConverter` như một Jackson deserializer hoặc một cơ chế bind DTO tùy ý. Nếu hợp đồng thực sự yêu cầu một body phức tạp, cần lựa chọn cơ chế tiếp nhận phù hợp thay vì mở rộng converter quá rộng để che sự khác biệt.

### 7.4. Converter thông thường vẫn là bean, nhưng chưa được Actuator chọn

Đổi thuộc tính rồi khởi động lại:

```properties
demo.endpoint-qualified=false
```

Ứng dụng vẫn có một bean `WorkerRangeConverter`, nhưng bean này không được đánh dấu `@EndpointConverter`.

Gửi lại query hợp lệ ở mục 7.1. Với mẫu này, kết quả là 400 và operation không được gọi, vì Actuator không có quy tắc đã đăng ký để chuyển chuỗi `2..4` thành kiểu `WorkerRange`.

Kiểu `WorkerRange` của ví dụ có hai thành phần số nguyên, không có constructor nhận một String hoặc factory method diễn giải String. Nhờ vậy, thí nghiệm không dựa vào một cơ chế chuyển đổi tự động khác có thể vô tình làm yêu cầu thành công.

Đổi lại `demo.endpoint-qualified=true` để tiếp tục các bài thử còn lại.

## 8. Kiểm tra lỗi chuyển đổi và phân biệt với validation

### 8.1. Ma trận đầu vào

Giữ các tham số khác đúng như query chuẩn:

| Thay đổi | Kết quả trong mẫu | Operation được gọi? |
| --- | --- | --- |
| range=two-four | 400 | Không |
| range=4..2 | 400 | Không |
| backoff=soon | 400 | Không |
| attempts=three | 400 | Không |
| enabled=maybe | 400 | Không |
| Bỏ tham số range | 400 | Không |
| JSON range là object lồng | 400 | Không |
| attempts=-1 | 200 | Có |

Hai lỗi của `range` có nguồn gốc khác nhau:

- `two-four` sai cú pháp biểu diễn mà converter chấp nhận.
- `4..2` có thể tách thành hai số, nhưng vi phạm bất biến của `WorkerRange`.

Cả hai đều thất bại trong bước chuyển thành đối tượng đầu vào, trước khi operation chạy.

Ngược lại, `attempts=-1` chuyển được thành int. Phản hồi xem trước có:

```json
{"attempts":-1,"enabled":true,"backoffMs":250,"firstWorker":2,"lastWorker":4}
```

Mẫu cố ý không thực hiện nghiệp vụ thử lại để làm rõ giới hạn của conversion. Một operation thật sử dụng số lần thử phải kiểm tra giới hạn phù hợp trước khi bắt đầu công việc; không lấy việc parse thành công làm bằng chứng yêu cầu được phép thực thi.

### 8.2. Không dùng null để che đầu vào sai

Không nên bắt mọi lỗi trong converter rồi trả `null` hoặc một khoảng mặc định. Cách làm đó che mất nguyên nhân và có thể đưa operation vào một trạng thái khác với yêu cầu người gọi.

Converter cũng không phải nơi xử lý một tham số bắt buộc bị thiếu. Khi thiếu đầu vào, cơ chế ánh xạ tham số có thể kết thúc trước bước gọi converter. Nếu cần tham số tùy chọn hoặc giá trị mặc định, hãy thiết kế điều đó rõ trong hợp đồng operation.

Không đồng nhất chuỗi rỗng, chuỗi chỉ có khoảng trắng, tham số không được gửi và JSON null. Trong converter của mẫu, chuỗi chỉ có khoảng trắng sau `trim()` không khớp định dạng và bị từ chối.

### 8.3. Kiểm tra bằng ConversionService không thay cho kiểm tra endpoint

Đoạn sau minh họa sử dụng API trực tiếp trong mã Java đã có các dependency của mẫu. Đặt nó trong một phương thức để thử; đây không phải một chương trình độc lập có `main`:

```java
var conversion = new org.springframework.boot.convert.ApplicationConversionService();

Duration backoff = conversion.convert("250ms", Duration.class);
System.out.println(backoff.toMillis());

conversion.addConverter(
        new EndpointConversionApplication.WorkerRangeConverter());

var range = conversion.convert(
        "2..4", EndpointConversionApplication.WorkerRange.class);
System.out.println(range);
```

Với import `java.time.Duration` và cùng package của mẫu, stdout là:

```text
250
WorkerRange[first=2, last=4]
```

Nếu chuyển `4..2`, conversion service ném `ConversionFailedException` chứa nguyên nhân từ quá trình chuyển đổi. HTTP 400 chỉ xuất hiện khi lỗi đó được cơ chế ánh xạ operation thích ứng thành phản hồi web.

Một `ApplicationConversionService` tự tạo bằng `new` không tự đi tìm các bean `@EndpointConverter` trong Spring context. Đoạn mã trên chủ động `addConverter` vào instance đang dùng.

Tương tự, `canConvert(String.class, WorkerRange.class)` nếu trả true chỉ cho biết có đường chuyển giữa hai kiểu, không bảo đảm mọi chuỗi đều hợp lệ. Vẫn phải kiểm tra các giá trị cụ thể.

## 9. Phạm vi Actuator, MVC và cấu hình ứng dụng

Một ứng dụng có thể có nhiều cơ chế conversion song song:

| Nơi tiếp nhận dữ liệu | Cơ chế cần xem |
| --- | --- |
| Đối số operation Actuator | ApplicationConversionService và converter được chọn bằng @EndpointConverter |
| Đầu vào controller Spring MVC | ConversionService/formatter và cấu hình MVC |
| Thuộc tính @ConfigurationProperties | Cơ chế bind cấu hình và @ConfigurationPropertiesBinding khi cần converter riêng |
| JSON body hoặc JSON output | HttpMessageConverter/Jackson và hợp đồng xử lý JSON |

Không mặc định rằng thêm converter ở một nơi sẽ cấu hình đúng mọi nơi còn lại.

Đồng thời, cũng không nên khẳng định một bean có `@EndpointConverter` chỉ có thể được Actuator sử dụng. Tự cấu hình Spring MVC của Spring Boot có khả năng đăng ký các bean Converter/GenericConverter/Formatter vào MVC theo cơ chế của nó. Qualifier dành cho Actuator không tự cấm cơ chế đó. Xem [Spring MVC auto-configuration và conversion service](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.spring-mvc.auto-configuration).

Đối với thuộc tính cấu hình, `@ConfigurationPropertiesBinding` là một qualifier khác phục vụ mục đích bind cấu hình; không phải tên thay thế của `@EndpointConverter`. Xem [Properties Conversion](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion).

Vì thế, khi một converter hoạt động trong controller nhưng endpoint vẫn báo 400, hãy kiểm tra converter có được Actuator chọn hay không. Ngược lại, một yêu cầu Actuator thành công cũng không đủ chứng minh cơ chế bind cấu hình hoặc JSON DTO đã được cấu hình như mong muốn.

Không thay toàn bộ conversion service của ứng dụng chỉ để sửa một định dạng đầu vào endpoint. Trước tiên hãy xác định đúng cặp kiểu, đúng nơi đăng ký và đúng cơ chế phát hiện converter.

## 10. Lỗi thường gặp và cách kiểm chứng

| Lỗi | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| Có lớp converter nhưng chưa là bean | Không có quy tắc tùy chỉnh trong ứng dụng | Kiểm tra đăng ký @Bean hoặc component phù hợp |
| Có bean nhưng thiếu @EndpointConverter | Operation Actuator vẫn không chuyển được kiểu tùy chỉnh | Kiểm tra qualifier của bean mà Actuator chọn |
| Mất tên tham số | Không ánh xạ đúng giá trị đầu vào | Kiểm tra -parameters và tên trường/query |
| Đưa object lồng vào tham số cần scalar | 400 dù object có các trường trông hợp lý | Kiểm tra kiểu nguồn sau khi đọc JSON |
| Converter giữ dữ liệu yêu cầu trong field | Có thể trộn dữ liệu khi có nhiều yêu cầu đồng thời | Giữ converter không trạng thái theo từng yêu cầu |
| Dùng parse thành công thay validation | Giá trị số hoặc thời lượng ngoài chính sách vẫn đi tiếp | Kiểm tra giới hạn trong kiểu giá trị hoặc logic thao tác |
| Thực hiện I/O trong convert() | Khó dự đoán độ trễ và hiệu ứng phụ khi bind | Tách chuyển đổi khỏi thực thi |
| Ghi toàn bộ đầu vào và lỗi thô ra log/phản hồi | Có thể lộ thông tin không cần thiết | Chỉ mô tả lỗi theo hợp đồng chẩn đoán phù hợp |

Một bộ kiểm tra có ý nghĩa cho mẫu nên bao gồm:

1. Converter trực tiếp: cú pháp đúng, sai cú pháp, thứ tự sai, biên 1 và 32.
2. Operation qua HTTP: query và JSON scalar cho cùng kết quả.
3. Lỗi đầu vào: phản hồi 400 và bộ đếm invocation không tăng.
4. Phát hiện bean: converter thường tồn tại nhưng không thay converter được qualifier chọn.
5. Phân biệt validation: số âm parse được nhưng không tự thỏa quy tắc nghiệp vụ.

Kiểm tra trực tiếp converter chứng minh thuật toán chuyển đổi. Kiểm tra endpoint chứng minh thêm việc thu thập đối số, chọn converter và ngăn operation chạy khi đầu vào không thể ánh xạ.

## 11. Bài tập củng cố

1. Bổ sung trường hợp kiểm tra `1..32`, `0..3`, `2..33` và khoảng trắng ngoài ` 2..4 `. Giải thích lớp nào chấp nhận hoặc từ chối mỗi trường hợp.
2. Thay biểu diễn đầu vào thành `2-4` nhưng giữ nguyên kiểu WorkerRange. Xác định phần nào phải đổi và phần nào không cần đổi.
3. Thêm giới hạn số lần thử 1..5 cho một thao tác thực sự. Giải thích vì sao giới hạn này không tự xuất hiện khi tham số khai báo int.
4. Tạo một kiểm tra chỉ đăng ký converter bean thông thường, một kiểm tra đăng ký đúng qualifier, rồi so sánh việc operation có được gọi hay không.
5. Giải thích vì sao converter String -> WorkerRange không phải cơ chế bind object JSON `{"first":2,"last":4}` vào tham số.
6. Nếu cần thêm một cặp kiểu nguồn–đích khác, đánh giá nên tạo converter riêng hay dùng GenericConverter; không mở rộng sang mọi Object nếu chưa có hợp đồng rõ.

Một lời giải tốt chỉ ra dữ liệu nguồn, kiểu đích, quy tắc biểu diễn, nơi đăng ký converter và ranh giới giữa chuyển đổi với thực thi.
