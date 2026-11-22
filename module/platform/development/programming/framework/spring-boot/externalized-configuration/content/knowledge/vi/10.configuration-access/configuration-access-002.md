# Đọc giá trị bằng Environment.getProperty và chỉ định kiểu đích

Trong Spring Boot, cấu hình ứng dụng có thể đến từ `application.yml`, `application.properties`, biến môi trường, Java system properties, tham số khi chạy hoặc các nguồn cấu hình được import. Khi cần **đọc trực tiếp một giá trị cấu hình tại runtime**, Spring cung cấp đối tượng `Environment` với phương thức `getProperty(...)`.

Cách gọi cơ bản `environment.getProperty("app.name")` trả về giá trị dưới dạng **`String`** (hoặc `null` nếu không tìm thấy). Nhưng Spring còn cung cấp các overload cho phép **chỉ định kiểu đích**, ví dụ `Integer.class` hoặc `Boolean.class`, để yêu cầu chuyển đổi giá trị theo kiểu Java mong muốn. Tùy môi trường Spring Boot và bộ chuyển đổi đang được dùng, các kiểu như `Duration`, `URI` cũng có thể được hỗ trợ.

Bài này trình bày từ cách đọc một property đơn giản, chọn kiểu đích, xử lý trường hợp thiếu/sai giá trị, đến việc quyết định khi nào nên chuyển sang `@ConfigurationProperties`.

## 1. Environment đứng ở đâu trong cấu hình Spring Boot?

Một ứng dụng thường có nhiều nguồn cấu hình đồng thời:

~~~text
Tham số command line
Java system properties
Biến môi trường của hệ điều hành
SPRING_APPLICATION_JSON
Config Data: application.yml, application-prod.yml, config import...
Các nguồn property khác đã được đăng ký
                    |
                    v
        Spring Environment
        và các PropertySource
                    |
                    v
       getProperty("app.timeout")
                    |
                    v
        Giá trị được phân giải
                    |
                    v
     Chuyển đổi sang kiểu đích
~~~

Sơ đồ chỉ mô tả các **loại nguồn** chứ không phải thứ tự ưu tiên đầy đủ. Thứ tự áp dụng phụ thuộc cơ chế của Spring Boot và những nguồn mà ứng dụng thực sự đã đăng ký. Với cùng một key, `Environment` tìm giá trị theo thứ tự ưu tiên của các property source.

Ví dụ:

~~~yaml
# application.yml
app:
  display-name: "Order Service"
  retry-count: 3
  enabled: true
  request-timeout: 4s
~~~

Nếu deployment không ghi đè các key trên, ta có thể đọc:

~~~java
String name = environment.getProperty("app.display-name");
String retryText = environment.getProperty("app.retry-count");
String enabledText = environment.getProperty("app.enabled");
~~~

Giá trị dự kiến ở góc nhìn Java:

~~~text
name         = "Order Service"
retryText    = "3"
enabledText  = "true"
~~~

Dù trong YAML, `retry-count` trông như số và `enabled` trông như boolean, overload không truyền kiểu đích của `Environment#getProperty` trả về một `String` khi tìm thấy giá trị.

Đây là lý do cần phân biệt **biểu diễn cấu hình ở nguồn** với **kiểu mà mã Java yêu cầu**.

## 2. Các overload quan trọng của getProperty

`Environment` kế thừa hợp đồng tra cứu property từ Spring `PropertyResolver`. Những cách gọi thường dùng gồm:

| Cách gọi | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getProperty(String key)` | `String` | Đọc một giá trị dưới dạng chuỗi; có thể trả `null` |
| `getProperty(String key, String defaultValue)` | `String` | Dùng giá trị mặc định khi không tìm thấy giá trị |
| `getProperty(String key, Class<T> targetType)` | `T` | Chuyển giá trị tìm được sang kiểu đích |
| `getProperty(String key, Class<T> targetType, T defaultValue)` | `T` | Chuyển kiểu; dùng mặc định khi kết quả tra cứu không có giá trị |
| `getRequiredProperty(String key)` | `String` | Yêu cầu property có giá trị; thiếu thì báo lỗi |
| `getRequiredProperty(String key, Class<T> targetType)` | `T` | Yêu cầu property và chuyển sang kiểu đã chỉ định |
| `containsProperty(String key)` | `boolean` | Kiểm tra key có một giá trị mà resolver nhìn thấy hay không |

Ở Java, `Class<T>` thường được truyền bằng class literal, ví dụ `Integer.class`, `Boolean.class`, `String.class`, `Duration.class`.

Ví dụ minh họa:

~~~java
String name = environment.getProperty("app.display-name");

String nameWithFallback =
    environment.getProperty("app.display-name", "Unnamed App");

Integer attempts =
    environment.getProperty("app.retry-count", Integer.class);

int attemptsWithFallback =
    environment.getProperty("app.retry-count", Integer.class, 3);

Boolean enabled =
    environment.getProperty("app.enabled", Boolean.class);

String requiredName =
    environment.getRequiredProperty("app.display-name");
~~~

**Lưu ý:** `Integer` và `Boolean` là các kiểu wrapper, có thể nhận `null`. Đừng tự động unbox thành `int`/`boolean` khi chưa chắc property tồn tại hoặc có mặc định hợp lệ.

## 3. Đọc String trước: đơn giản nhưng không phải lúc nào cũng đủ

Cách dùng ngắn nhất:

~~~java
String value = environment.getProperty("app.display-name");
~~~

Nếu cấu hình là:

~~~yaml
app:
  display-name: "Inventory Service"
~~~

thì `value` là chuỗi `"Inventory Service"`.

Khi key không tồn tại:

~~~java
String unknown = environment.getProperty("app.unknown");
// unknown có thể là null.
~~~

Trường hợp này cần xử lý:

~~~java
String label = environment.getProperty("app.label");
if (label == null) {
    label = "Default label";
}
~~~

Hoặc ngắn gọn:

~~~java
String label =
    environment.getProperty("app.label", "Default label");
~~~

Đọc bằng `String` phù hợp khi giá trị thực sự là chuỗi như tên ứng dụng, mã định danh, nhãn hoặc endpoint cần xử lý thêm. Nhưng nếu key thể hiện số lần thử lại, cờ logic hoặc thời lượng, việc giữ mọi thứ dưới dạng chuỗi làm mã nguồn phải tự chuyển kiểu:

~~~java
String text = environment.getProperty("app.retry-count");
int retryCount = Integer.parseInt(text);
~~~

Đoạn trên có hai rủi ro: `text` có thể null khiến `parseInt` lỗi, và bạn phải tự quản lý conversion. Khi có converter phù hợp, gọi trực tiếp `getProperty(key, Integer.class)` thường rõ nghĩa hơn.

## 4. Chỉ định kiểu đích bằng Class<T>

Đây là tâm điểm của bài. Thay vì nhận `String`, lập trình viên cung cấp một class literal để Spring chuyển giá trị:

~~~java
Integer retryCount =
    environment.getProperty("app.retry-count", Integer.class);

Boolean enabled =
    environment.getProperty("app.enabled", Boolean.class);
~~~

Với YAML:

~~~yaml
app:
  retry-count: 5
  enabled: false
~~~

Kết quả dự kiến:

~~~text
retryCount -> Integer có giá trị 5
enabled    -> Boolean.FALSE
~~~

Cách viết này giúp tên biến và kiểu đích phù hợp với ý nghĩa dữ liệu. Nó cũng tránh việc mọi service tự parse chuỗi theo cách riêng.

Một số kiểu thường gặp:

| Ý nghĩa cấu hình | Ví dụ property | Kiểu đích gợi ý |
| --- | --- | --- |
| Tên hoặc mã | `app.name`, `app.code` | `String.class` |
| Số lượng tối đa | `worker.max-threads` | `Integer.class` |
| Số lượt retry lớn | `job.retry-limit` | `Long.class` hoặc `Integer.class` tùy phạm vi |
| Cờ bật/tắt | `feature.enabled` | `Boolean.class` |
| Tỷ lệ số thực | `client.backoff-factor` | `Double.class` hoặc kiểu số phù hợp |
| Thời lượng | `client.timeout` | `Duration.class` nếu ConversionService hỗ trợ |
| URI | `client.base-uri` | `URI.class` nếu ConversionService hỗ trợ |

Không có một quy tắc rằng mọi kiểu Java đều tự động chuyển được. `Environment#getProperty` dựa vào **conversion service** của môi trường Spring. Spring Boot thường bổ sung các converter thuận tiện cho cấu hình ứng dụng; một `Environment` thuần tạo trong unit test có thể có tập converter khác. Với type phức tạp hoặc format riêng, cần converter thích hợp.

### Ví dụ đầy đủ với cấu hình

~~~yaml
inventory:
  max-items: 120
  enabled: true
  display-code: "0012"
  timeout: 2500ms
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;

public final class InventoryReader {

    private final Environment environment;

    public InventoryReader(Environment environment) {
        this.environment = environment;
    }

    public void read() {
        Integer maxItems =
            environment.getProperty(
                "inventory.max-items", Integer.class);

        Boolean enabled =
            environment.getProperty(
                "inventory.enabled", Boolean.class);

        String displayCode =
            environment.getProperty("inventory.display-code");

        Duration timeout =
            environment.getProperty(
                "inventory.timeout", Duration.class);

        // Sử dụng các giá trị sau khi xử lý missing/validation.
    }
}
~~~

Trong ứng dụng Spring Boot có converter cho duration, `2500ms` có thể được chuyển thành một `Duration` 2,5 giây. Nếu môi trường của bạn không hỗ trợ converter tương ứng, sẽ cần cách chuyển đổi khác.

Đặc biệt, `display-code` phải là `String` nếu cần giữ chuỗi `"0012"`. Nếu đọc bằng `Integer.class`, kết quả là số 12 và phần định dạng bằng số 0 đầu không còn.

## 5. Giá trị mặc định: getProperty(key, type, default)

Cách lấy số lượng retry với mặc định:

~~~java
int retryCount =
    environment.getProperty(
        "batch.retry-count", Integer.class, 3);
~~~

Nếu không nguồn property nào cung cấp giá trị dùng được cho `batch.retry-count`, chương trình nhận mặc định `3`.

Cách lấy boolean:

~~~java
boolean enabled =
    environment.getProperty(
        "batch.enabled", Boolean.class, false);
~~~

Cách lấy chuỗi:

~~~java
String serviceName =
    environment.getProperty(
        "app.service-name", String.class, "order-service");
~~~

So sánh trực tiếp:

~~~java
Integer a =
    environment.getProperty("batch.retry-count", Integer.class);

Integer b =
    environment.getProperty(
        "batch.retry-count", Integer.class, 3);
~~~

Nếu key hoàn toàn không có, `a` có thể null còn `b` là 3.

**Giá trị mặc định không phải cơ chế nuốt lỗi conversion.** Nếu cấu hình có:

~~~yaml
batch:
  retry-count: "three-times"
~~~

mà Java yêu cầu `Integer.class`, bộ chuyển đổi có thể báo lỗi vì `"three-times"` không phải số nguyên. Đừng kỳ vọng overload có defaultValue sẽ tự bỏ qua dữ liệu sai để trả 3. Mặc định chỉ dùng khi tra cứu không có giá trị, còn dữ liệu sai kiểu cần được phát hiện và sửa.

### Chọn default có trách nhiệm

Một giá trị mặc định nên:

- An toàn trong bối cảnh ứng dụng.
- Có ý nghĩa nghiệp vụ/vận hành rõ ràng.
- Có thể dùng được mà không phải đoán đơn vị hay ý định.
- Không che lỗi thiếu secret hoặc endpoint bắt buộc.

Ví dụ `batch.retry-count` mặc định 3 có thể hợp lý nếu đã được xác định. Ngược lại, `payment.api-key` không nên có giá trị mặc định giả khiến production khởi động rồi thất bại muộn hoặc gửi request sai nơi.

## 6. Property bắt buộc: getRequiredProperty

Nếu một key phải có thì dùng:

~~~java
String endpoint =
    environment.getRequiredProperty("gateway.base-url");
~~~

Khi không tìm thấy giá trị cho key, `getRequiredProperty` sẽ báo lỗi, thường là `IllegalStateException`. Cách này phù hợp với một số thông số không có mặc định hợp lệ.

Có cả overload nhận kiểu đích:

~~~java
Integer maxConnections =
    environment.getRequiredProperty(
        "gateway.max-connections", Integer.class);
~~~

Hai kiểu lỗi cần tách biệt:

1. **Không có giá trị:** `getRequiredProperty` báo rằng property được yêu cầu không tìm thấy.
2. **Có nhưng sai định dạng/không chuyển được:** converter báo lỗi trong quá trình chuyển kiểu.

Bắt buộc **có giá trị** không đồng nghĩa giá trị **hợp lệ về mặt nghiệp vụ**. Ví dụ:

~~~yaml
gateway:
  base-url: ""
  max-connections: -5
~~~

Một chuỗi rỗng có thể vẫn được xem là có giá trị đối với một truy vấn `String`. Một số âm có thể được chuyển thành `Integer` nhưng không phù hợp với yêu cầu số kết nối tối thiểu.

Cần thêm kiểm tra:

~~~java
String baseUrl =
    environment.getRequiredProperty("gateway.base-url");

if (baseUrl.isBlank()) {
    throw new IllegalStateException(
        "gateway.base-url must not be blank");
}

int maxConnections =
    environment.getRequiredProperty(
        "gateway.max-connections", Integer.class);

if (maxConnections <= 0) {
    throw new IllegalStateException(
        "gateway.max-connections must be positive");
}
~~~

Khi số property bắt buộc nhiều hoặc có các ràng buộc liên quan nhau, mô hình `@ConfigurationProperties` kết hợp validation thường dễ bảo trì hơn các đoạn `if` lặp lại.

## 7. Thiếu property, null, chuỗi rỗng và giá trị không hợp lệ

Bốn tình huống này khác nhau:

| Tình huống | Ví dụ | Điều cần xử lý |
| --- | --- | --- |
| Key không tồn tại | Không có `app.name` trong nguồn nào | `getProperty` thường trả null hoặc default |
| Key có giá trị rỗng | `app.name: ""` | Với `String`, có thể nhận chuỗi rỗng; cần validation khi không hợp lệ |
| Key có JSON null từ `SPRING_APPLICATION_JSON` | `{"app":{"name":null}}` | Null không che giá trị từ nguồn property thấp hơn |
| Key có giá trị sai kiểu | `app.retry-count: "many"` | Conversion có thể thất bại, không phải missing |
| Key có giá trị đúng kiểu nhưng sai ràng buộc | `app.retry-count: -2` | Cần kiểm tra domain/config validation |

Ví dụ:

~~~java
String name =
    environment.getProperty("app.name", "default");

Integer retryCount =
    environment.getProperty(
        "app.retry-count", Integer.class, 3);
~~~

Nếu `app.name` không có thì `name` dùng `"default"`. Nhưng nếu `app.name` là chuỗi rỗng, không nên mặc định rằng `"default"` luôn được dùng; chuỗi rỗng có thể là giá trị hiện diện.

Một ví dụ quan trọng trong Spring Boot:

~~~yaml
# application.yml
app:
  mode: "normal"
~~~

~~~json
{
  "app": {
    "mode": null
  }
}
~~~

Nếu JSON được cung cấp qua `SPRING_APPLICATION_JSON`, `null` không phải lệnh xóa giá trị `"normal"`; bộ phân giải property có thể tiếp tục tìm trong `application.yml`. Vì thế, `getProperty("app.mode")` vẫn có thể trả `"normal"`. Muốn tắt một tính năng, nên dùng cờ có ý nghĩa như `app.feature.enabled=false` thay vì dựa vào null để che property.

## 8. Cẩn thận với wrapper và unboxing

Overload có kiểu đích trả giá trị kiểu `T`, và nếu không tìm thấy property, `T` có thể là null:

~~~java
Integer count =
    environment.getProperty("workers.count", Integer.class);
~~~

Cách sau có nguy cơ:

~~~java
int count =
    environment.getProperty("workers.count", Integer.class);
~~~

Nếu property không có, Java cố unbox `null` sang `int` và gây `NullPointerException`. Lỗi này phát sinh ở mã gọi, không nhất thiết tại Spring.

Nên chọn một trong ba cách:

**Có mặc định rõ:**

~~~java
int count =
    environment.getProperty("workers.count", Integer.class, 4);
~~~

**Bắt buộc có:**

~~~java
int count =
    environment.getRequiredProperty(
        "workers.count", Integer.class);
~~~

**Cho phép thiếu:**

~~~java
Integer count =
    environment.getProperty("workers.count", Integer.class);

if (count != null) {
    // Sử dụng count khi đã có cấu hình.
}
~~~

Với boolean, tránh diễn giải `null` như `false` khi thực tế cần biết trạng thái “chưa được cấu hình”:

~~~java
Boolean flag =
    environment.getProperty("feature.enabled", Boolean.class);

if (Boolean.TRUE.equals(flag)) {
    // Chỉ thực thi khi property là true.
}
~~~

Nếu mô hình của bạn chỉ có hai trạng thái, dùng default boolean rõ ràng sẽ dễ đọc hơn.

## 9. Khi đọc Duration, URI và những kiểu không phải String

Spring Boot hỗ trợ binding nhiều loại giá trị hơn chỉ số và boolean. Tuy nhiên, khả năng chuyển đổi phụ thuộc ConversionService đã được cài cho `Environment`. Trong một ứng dụng Spring Boot chuẩn, cách đọc có kiểu này thường hữu ích:

~~~yaml
integration:
  base-uri: "https://gateway.example.invalid/api"
  timeout: 3s
  max-connections: 20
~~~

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.core.env.Environment;

URI uri =
    environment.getProperty(
        "integration.base-uri", URI.class);

Duration timeout =
    environment.getProperty(
        "integration.timeout", Duration.class);

Integer limit =
    environment.getProperty(
        "integration.max-connections", Integer.class);
~~~

Các trường hợp cần kiểm tra:

- `URI` hợp lệ về cú pháp chưa bảo đảm endpoint truy cập được hoặc dùng giao thức được phép.
- `Duration` cần đơn vị rõ ràng khi có thể; giá trị trần như `30` có thể bị hiểu theo quy ước conversion/kiểu đích.
- `Integer` chuyển được số âm nhưng ứng dụng có thể yêu cầu số dương.
- Các kiểu phức tạp, enum có quy tắc riêng, collection hoặc object lồng nhau không nên suy luận rằng một lời gọi `getProperty` sẽ tự bind mọi thứ.

Nếu format không được converter hỗ trợ, Spring có thể báo lỗi conversion. Khi đó phải xem đúng kiểu đích, converter và cách biểu diễn property. Đừng giải quyết bằng cách thêm `String.valueOf(...)` hoặc nuốt ngoại lệ chung.

### Enum và lựa chọn có tập giá trị

Ví dụ cấu hình chế độ:

~~~yaml
export:
  mode: "BATCH"
~~~

Kiểu Java:

~~~java
enum ExportMode {
    BATCH,
    STREAMING
}
~~~

Với conversion phù hợp, có thể yêu cầu:

~~~java
ExportMode mode =
    environment.getProperty(
        "export.mode", ExportMode.class, ExportMode.BATCH);
~~~

Nhưng enum chỉ chấp nhận những giá trị mà converter có thể ánh xạ. Hãy thống nhất cách viết và kiểm thử với phiên bản Spring Boot đang dùng, nhất là nếu giá trị có dấu gạch ngang, khoảng trắng hoặc alias.

## 10. Đọc cấu hình từ Environment trong một thành phần Spring

Một cấu hình Java có thể inject `Environment` qua constructor. Ví dụ service chỉ có vài tham số:

~~~java
package example.inventory;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class InventoryLimitService {

    private final int maxItems;
    private final boolean enabled;

    public InventoryLimitService(Environment environment) {
        this.maxItems = environment.getProperty(
            "inventory.max-items", Integer.class, 100);

        this.enabled = environment.getProperty(
            "inventory.enabled", Boolean.class, true);
    }

    public boolean mayAccept(int currentItems) {
        return enabled && currentItems < maxItems;
    }
}
~~~

File `application.yml`:

~~~yaml
inventory:
  enabled: true
  max-items: 120
~~~

Khi bean được khởi tạo, các field nhận giá trị được chuyển đổi từ `Environment`. Đây là ví dụ nhỏ để hiểu `getProperty`; với một nhóm cấu hình lớn, thường nên gom property vào một đối tượng có kiểu rõ ràng thay vì để từng service tự biết tên các key.

**Lưu ý về vòng đời:** Field `maxItems` và `enabled` ở ví dụ được gán khi constructor chạy. Nếu file YAML hoặc biến môi trường của deployment thay đổi sau đó, bean không tự đổi field. Spring Boot mặc định không có cơ chế theo dõi mọi file cấu hình và tự cập nhật mọi bean; yêu cầu refresh động cần thiết kế riêng.

## 11. Environment, @Value và @ConfigurationProperties khác nhau thế nào?

Ba cơ chế đều liên quan externalized configuration, nhưng phù hợp các mục đích khác nhau:

| Cơ chế | Mục đích thường gặp | Giới hạn/cân nhắc |
| --- | --- | --- |
| `Environment#getProperty` | Tra cứu động một key, cung cấp kiểu/default trực tiếp trong mã | Dễ rải literal key và validation ở nhiều nơi |
| `@Value` | Inject một biểu thức property/placeholder vào field hoặc constructor | Kém thuận tiện khi nhiều property cần grouping |
| `@ConfigurationProperties` | Bind một nhóm property vào đối tượng có cấu trúc, kiểu và validation | Cần đăng ký class cấu hình và tổ chức nhóm rõ |

Ví dụ `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class HealthBanner {

    private final String label;

    HealthBanner(
        @Value("${app.banner.label:Ready}") String label
    ) {
        this.label = label;
    }
}
~~~

Trong biểu thức `${app.banner.label:Ready}`, `Ready` là fallback của placeholder, không phải một property source độc lập.

Ví dụ `@ConfigurationProperties`:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        boolean enabled,
        int maxItems,
        Duration timeout
) {}
~~~

Đăng ký thông qua `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(InventoryProperties.class)` trong cấu hình phù hợp.

~~~java
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final InventoryProperties properties;

    InventoryService(InventoryProperties properties) {
        this.properties = properties;
    }

    boolean isEnabled() {
        return properties.enabled();
    }
}
~~~

Nếu ứng dụng có nhiều property liên quan nhau, `@ConfigurationProperties` giúp tập trung kiểu, default hợp lý, ràng buộc và documentation. Spring Boot Binder còn hỗ trợ **relaxed binding**, nested objects và collection tốt hơn việc tự gọi `getProperty` cho từng key.

Một quy tắc thực tế: dùng `Environment#getProperty` khi thật sự cần **tra một hoặc vài key** hoặc cần xử lý động theo một key đã biết; dùng `@ConfigurationProperties` để biểu diễn **hợp đồng cấu hình lâu dài** của một thành phần.

## 12. Vì sao không nên dùng getProperty để bind cả object lồng nhau?

Giả sử YAML:

~~~yaml
gateway:
  enabled: true
  endpoints:
    - "https://one.example.invalid"
    - "https://two.example.invalid"
  retry:
    attempts: 3
    delay: 2s
~~~

Việc gọi:

~~~java
String endpoints =
    environment.getProperty("gateway.endpoints");
~~~

không phải một hợp đồng đáng tin cậy để lấy toàn bộ YAML sequence. Sau khi được Spring Boot nạp, collection thường được biểu diễn qua các property có chỉ số và quy tắc binding tương ứng. Mã dựa vào một chuỗi dấu phẩy có thể không phù hợp với cấu trúc nguồn.

Với cấu hình nested/list, dùng Binder thông qua `@ConfigurationProperties`:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        boolean enabled,
        List<String> endpoints,
        Retry retry
) {
    public record Retry(int attempts, Duration delay) {}
}
~~~

Cách này phản ánh đúng cấu trúc dữ liệu và tạo một điểm kiểm soát hợp lệ. `Environment#getProperty` không phải API thay thế mọi khả năng của Spring Boot Binder.

Ngoài ra, Spring Boot hỗ trợ một số quy tắc chuẩn hóa tên property trong configuration binding, nhưng không nên tự giả định mọi tên camelCase, dấu gạch dưới và dấu gạch ngang đều tương đương trong mọi `PropertySource` khi tra key bằng `Environment`.

## 13. Tên property và biến môi trường hệ điều hành

Giả sử muốn cấu hình:

~~~yaml
app:
  order:
    max-items: 40
~~~

Từ mã Java, nên dùng tên key dạng chấm/kebab-case nhất quán:

~~~java
Integer limit =
    environment.getProperty(
        "app.order.max-items", Integer.class);
~~~

Khi triển khai qua biến môi trường, thường dùng dạng uppercase và underscore theo quy ước Spring Boot, chẳng hạn `APP_ORDER_MAXITEMS` cho property chuẩn hóa `app.order.max-items` trong relaxed binding. Một số nguồn property hệ thống có cơ chế tra tên tương đương riêng, nhưng không nên dựa vào suy luận tên cho mọi trường hợp.

Điều cần nhớ:

- `getProperty("app.order.max-items")` là truy vấn theo tên key mà resolver nhận biết.
- `@ConfigurationProperties(prefix = "app.order")` sử dụng quy tắc binding thuận tiện hơn cho cấu trúc Java.
- Biến môi trường có cú pháp và cách chuẩn hóa khác với YAML; cần chọn tên theo quy ước Spring Boot và kiểm tra trên runtime thực tế.
- Nên tránh tạo đồng thời nhiều biến môi trường có tên gần giống nhau nhưng khác dấu để thử “đánh cược” xem cái nào được nhận.

Nếu giá trị không như mong đợi, phải kiểm tra **nguồn nào đang thắng**, tên key có đúng không và targetType có phù hợp không.

## 14. Spring Environment không phải System.getenv

Hai cách sau khác nhau:

~~~java
String direct =
    System.getenv("APP_ORDER_MAXITEMS");

Integer resolved =
    environment.getProperty(
        "app.order.max-items", Integer.class);
~~~

`System.getenv` chỉ đọc biến môi trường của tiến trình với tên được yêu cầu. Nó không tự kết hợp giá trị từ `application.yml`, system properties, tham số command line, config import hoặc nguồn mà Spring đăng ký.

`Environment` nhìn vào tập `PropertySource` của Spring, xét thứ tự ưu tiên và có thể chuyển kiểu cho ứng dụng.

Ưu điểm của `Environment` trong Spring Boot:

1. Cùng một đoạn mã Java có thể nhận giá trị từ nhiều nguồn khác nhau.
2. Deployment có thể override property mà không sửa logic chương trình.
3. Có thể khai báo fallback hoặc yêu cầu kiểu đích ngay tại điểm đọc.
4. Test có thể cung cấp property theo cơ chế của Spring mà không phải sửa biến môi trường thật của máy.

Tuy nhiên, không nên gọi `Environment` trong mọi class chỉ để tiện truy cập. Nếu property là dependency ổn định của một service, inject một đối tượng `@ConfigurationProperties` có cấu trúc thường giúp giảm coupling với tên key.

## 15. Kiểm tra thứ tự ưu tiên khi getProperty trả giá trị bất ngờ

Ví dụ:

~~~yaml
# application.yml
app:
  retry-count: 3
~~~

~~~yaml
# application-prod.yml
app:
  retry-count: 5
~~~

Và deployment cung cấp tham số:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.retry-count=7
~~~

Khi Spring Boot có cấu hình mặc định về ưu tiên nguồn, tham số dòng lệnh có thể thắng cả file chung và file profile; `environment.getProperty("app.retry-count", Integer.class)` trả về số 7.

Tình huống này không do `Integer.class`, mà do **property resolution** trước khi conversion.

Khi giá trị khác mong đợi:

- Kiểm tra các profile active và các file config đang được nạp.
- Kiểm tra command line, system properties, environment variables và các nguồn import.
- Tìm key trùng nhau; nhớ rằng một nguồn ưu tiên cao có thể ghi đè nguồn thấp hơn.
- Kiểm tra cách viết key và naming convention.
- Phân biệt giá trị có mặt nhưng sai kiểu với giá trị không tìm thấy.
- Xác định ứng dụng đã restart hoặc có cơ chế refresh riêng sau lần thay đổi config hay chưa.

Nếu cần đọc profile hoạt động, `Environment` còn có `getActiveProfiles()` và `getDefaultProfiles()`. Chúng thể hiện trạng thái profile đã được môi trường xử lý, phù hợp hơn việc tự đoán profile đang active chỉ từ một property string.

~~~java
import java.util.Arrays;

String[] activeProfiles = environment.getActiveProfiles();
System.out.println(Arrays.toString(activeProfiles));
~~~

Trong production, nên chỉ log thông tin đủ để chẩn đoán, không in secrets hoặc toàn bộ cấu hình ra stdout.

## 16. Test getProperty và chuyển kiểu

Một unit test nhỏ có thể dùng `MockEnvironment` của Spring Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class PropertyReadTest {

    @Test
    void readsTypedProperties() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("batch.retry-count", "4")
            .withProperty("batch.enabled", "false");

        assertEquals(
            Integer.valueOf(4),
            environment.getProperty(
                "batch.retry-count", Integer.class));

        assertEquals(
            Boolean.FALSE,
            environment.getProperty(
                "batch.enabled", Boolean.class));

        assertNull(
            environment.getProperty(
                "batch.unknown", Integer.class));

        assertEquals(
            Integer.valueOf(2),
            environment.getProperty(
                "batch.unknown", Integer.class, 2));
    }
}
~~~

Test này chứng minh mục đích của các overload: có key thì convert sang kiểu tương ứng, thiếu key thì nhận null hoặc default.

Với các kiểu phụ thuộc conversion của Spring Boot như `Duration`, nên kiểm tra trong Spring Boot context đã được cấu hình converter phù hợp. Một `MockEnvironment` đơn giản không nhất thiết có cùng conversion service với Spring Boot application.

Ví dụ kiểm tra trong ứng dụng Spring Boot:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "inventory.max-items=25",
    "inventory.enabled=false"
})
class InventoryEnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void readsValuesFromTestPropertySource() {
        assertEquals(
            Integer.valueOf(25),
            environment.getProperty(
                "inventory.max-items", Integer.class));

        assertEquals(
            Boolean.FALSE,
            environment.getProperty(
                "inventory.enabled", Boolean.class));
    }
}
~~~

Ở đây `@SpringBootTest` giả định project có một Spring Boot application context hợp lệ. Các property dành cho test được cấp trực tiếp vào context, giúp xác minh code đọc property theo kiểu đích.

Có thể thêm trường hợp **sai kiểu** hoặc **thiếu property bắt buộc** nếu đó là hợp đồng cấu hình quan trọng. Không cần thêm test chỉ để chứng minh mọi overload của framework hoạt động; hãy kiểm tra những quy tắc mà ứng dụng thực sự phụ thuộc.

## 17. Xử lý lỗi: missing, conversion và validation

Giả sử ứng dụng cần:

~~~yaml
jobs:
  max-attempts: 5
~~~

Một số lỗi khác nhau có thể xuất hiện:

**Thiếu key:**

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);
// Có thể null.
~~~

**Key sai định dạng:**

~~~yaml
jobs:
  max-attempts: "many"
~~~

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);
// Có thể ném lỗi conversion.
~~~

**Key đúng kiểu nhưng không hợp lệ:**

~~~yaml
jobs:
  max-attempts: -10
~~~

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);

if (attempts != null && attempts < 0) {
    throw new IllegalArgumentException(
        "jobs.max-attempts must be non-negative");
}
~~~

Không nên gom ba trường hợp thành một `catch (Exception e) { return 3; }`. Cách đó có thể che lỗi deployment và làm ứng dụng chạy với tham số không mong muốn.

Một hướng xử lý rõ ràng:

| Vấn đề | Giải pháp |
| --- | --- |
| Property thực sự không bắt buộc | Dùng `getProperty` và xử lý null hoặc dùng default hợp lý |
| Property bắt buộc | Dùng `getRequiredProperty` và/hoặc validation |
| Giá trị sai kiểu | Sửa nguồn config hoặc converter; không lặng lẽ thay bằng mặc định |
| Giá trị đúng kiểu nhưng vượt ràng buộc | Kiểm tra/validate rõ ràng ở lớp cấu hình |
| Rất nhiều property cùng một prefix | Dùng `@ConfigurationProperties` và validation tập trung |
| Giá trị từ nguồn không mong muốn | Kiểm tra thứ tự ưu tiên và profile/source đang active |

Một ranh giới quan trọng: **conversion** không tự động chứng minh **đúng nghiệp vụ**. Số 0, số âm, URI hợp lệ về cú pháp hoặc boolean false đều có thể được convert thành công nhưng vẫn vi phạm yêu cầu của thành phần.

## 18. Những lỗi sử dụng phổ biến

### 18.1. Nghĩ getProperty luôn trả đúng kiểu YAML

~~~yaml
server:
  port: 8080
~~~

~~~java
String port = environment.getProperty("server.port");
~~~

`port` ở đây là `String`. Muốn số, gọi:

~~~java
Integer port =
    environment.getProperty("server.port", Integer.class);
~~~

### 18.2. Truy vấn thiếu default rồi unbox trực tiếp

~~~java
int maxAttempts =
    environment.getProperty("job.max-attempts", Integer.class);
~~~

Nếu thiếu key có thể phát sinh `NullPointerException` khi unbox. Dùng default hoặc required property phù hợp.

### 18.3. Tin rằng default cứu được giá trị sai kiểu

~~~yaml
job:
  max-attempts: "unlimited"
~~~

~~~java
int maxAttempts =
    environment.getProperty(
        "job.max-attempts", Integer.class, 3);
~~~

Default 3 không được thiết kế để chấp nhận chuỗi `"unlimited"` như một số hợp lệ. Nếu muốn hỗ trợ chữ `"unlimited"`, cần thiết kế một kiểu cấu hình có trạng thái đó, chẳng hạn enum, Optional hoặc quy tắc riêng, thay vì ép vào `int`.

### 18.4. Dùng getProperty thay cho validation

~~~java
String endpoint =
    environment.getRequiredProperty("payment.endpoint");
~~~

Có endpoint không đồng nghĩa endpoint an toàn hoặc được cấp quyền. Cần validate URI, scheme, ràng buộc business/config và policy bảo mật của thành phần.

### 18.5. Dùng Environment như kho dữ liệu thay đổi theo request

`Environment` đại diện cho externalized configuration của ứng dụng, không phải nơi lưu trạng thái đơn hàng, người dùng hiện tại hay kết quả giao dịch. Dữ liệu nghiệp vụ nên đi qua request/command, service và persistence thích hợp.

### 18.6. Đọc trực tiếp System.getenv vì “gọn hơn”

Khi ứng dụng đã dùng Spring Boot, `System.getenv("...")` có thể bỏ qua các nguồn khác và khiến test khó cấu hình. Dùng `Environment` hoặc `@ConfigurationProperties` nếu giá trị thuộc hợp đồng cấu hình của ứng dụng.

### 18.7. Đổi cấu hình rồi mong field đã inject tự thay đổi

Một bean đã đọc giá trị trong constructor giữ giá trị đó cho tới khi tự cập nhật. Không có lời đảm bảo mọi property source được cập nhật động hoặc mọi bean được tạo lại khi bạn sửa YAML. Thiết kế refresh là yêu cầu riêng.

### 18.8. Đọc secret để log kiểm tra

~~~java
String token =
    environment.getProperty("payment.api-token");
~~~

Việc đọc token có thể hợp lệ cho client được cấp quyền, nhưng không in giá trị đó ra log, không truyền vào exception message và không xuất toàn bộ `Environment` qua endpoint công khai. Khi cần debug, chỉ kiểm tra sự hiện diện/trạng thái an toàn của cấu hình mà không tiết lộ dữ liệu nhạy cảm.

## 19. Ví dụ thực tế: một HTTP client cần ba property

Giả sử adapter gọi hệ thống logistics có:

~~~yaml
logistics:
  client:
    base-url: "https://logistics.example.invalid/api"
    connect-timeout: 2s
    max-attempts: 3
    enabled: true
~~~

Một factory nhỏ có thể đọc cấu hình như sau:

~~~java
package example.logistics;

import java.net.URI;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class LogisticsClientConfiguration {

    @Bean
    LogisticsClient logisticsClient(Environment environment) {
        String urlText = environment.getRequiredProperty(
            "logistics.client.base-url");

        URI url = URI.create(urlText);

        Duration timeout = environment.getProperty(
            "logistics.client.connect-timeout",
            Duration.class,
            Duration.ofSeconds(2));

        int maxAttempts = environment.getProperty(
            "logistics.client.max-attempts",
            Integer.class,
            3);

        boolean enabled = environment.getProperty(
            "logistics.client.enabled",
            Boolean.class,
            false);

        if (urlText.isBlank()
                || timeout.isZero()
                || timeout.isNegative()
                || maxAttempts < 1) {
            throw new IllegalStateException(
                "Invalid logistics client configuration");
        }

        return new LogisticsClient(
            url, timeout, maxAttempts, enabled);
    }
}
~~~

`LogisticsClient` là lớp minh họa, có constructor nhận các giá trị tương ứng. Đoạn code cho thấy:

1. `base-url` phải có; giá trị đọc ra là chuỗi trước khi chuyển thành `URI`.
2. `connect-timeout` được yêu cầu dưới dạng `Duration` và có default 2 giây.
3. `max-attempts` được yêu cầu dưới dạng `Integer` và có default 3.
4. `enabled` được yêu cầu dưới dạng `Boolean` và có default false.
5. Những ràng buộc như timeout dương và số lượt thử lại tối thiểu 1 vẫn cần kiểm tra.

Với dự án lớn, nên chuyển ba hoặc bốn property này thành một `LogisticsClientProperties` dùng `@ConfigurationProperties` để các service và factory không lặp lại key string. Ví dụ trên có mục tiêu minh họa việc dùng `Environment#getProperty` và `getRequiredProperty` cùng kiểu đích.

## 20. Khi nào vẫn nên dùng Environment trực tiếp?

Các trường hợp hợp lý:

- Một thành phần framework/infrastructure cần tra cứu một key khi đang khởi tạo.
- Một adapter nhỏ chỉ có một hoặc hai property và không cần nhiều validation.
- Công cụ nội bộ muốn quan sát **giá trị có hiệu lực** của một key không nhạy cảm.
- Logic cần quyết định giữa các key đã biết trước, không phải bind cả object cấu hình.
- Test cần xác nhận thứ tự nguồn property và giá trị đã được convert theo kiểu yêu cầu.

Các trường hợp nên dùng `@ConfigurationProperties`:

- Một prefix có nhiều field liên quan.
- Có nested object, list, map hoặc cấu trúc cấu hình phức tạp.
- Cần validation tập trung và thông báo lỗi startup rõ ràng.
- Nhiều bean cùng sử dụng một hợp đồng cấu hình.
- Muốn giảm phụ thuộc vào tên key rải rác trong mã nguồn.

Việc dùng `Environment` không sai; lựa chọn tốt là lựa chọn diễn đạt **ý nghĩa của cấu hình** và giúp nhóm phát triển hiểu được mặc định, nguồn, kiểu và ràng buộc của mỗi giá trị.

## 21. Tự luyện với bốn kiểu property

Cho YAML:

~~~yaml
demo:
  application-name: "Receipt Service"
  max-users: 50
  enabled: false
  customer-code: "0019"
~~~

Hãy đọc bằng cả kiểu chuỗi và kiểu cụ thể:

~~~java
String name =
    environment.getProperty("demo.application-name");

Integer maxUsers =
    environment.getProperty("demo.max-users", Integer.class);

Boolean enabled =
    environment.getProperty("demo.enabled", Boolean.class);

String code =
    environment.getProperty("demo.customer-code");

Integer unknownWithDefault =
    environment.getProperty("demo.unknown", Integer.class, 10);
~~~

Giá trị dự kiến:

| Biến Java | Giá trị |
| --- | --- |
| `name` | `"Receipt Service"` |
| `maxUsers` | `Integer(50)` |
| `enabled` | `Boolean.FALSE` |
| `code` | `"0019"`, giữ số 0 đầu |
| `unknownWithDefault` | `Integer(10)` |

Sau đó thử đổi `demo.max-users` thành `"fifty"`. Khi Java vẫn yêu cầu `Integer.class`, hãy quan sát conversion error. Thử bỏ key này: `getProperty(key, Integer.class)` có thể trả null, trong khi overload có default có thể trả giá trị mặc định. Thử dùng `getRequiredProperty(key, Integer.class)` để phân biệt lỗi thiếu key với lỗi giá trị sai kiểu.

## 22. Ghi nhớ

`Environment#getProperty` cho phép đọc một property từ các nguồn cấu hình đã được Spring kết hợp. Không chỉ có `String getProperty(key)`: bạn còn có thể truyền **`Class<T>`** để yêu cầu kiểu đích, hoặc cung cấp **giá trị mặc định** khi key không được tìm thấy. Với property bắt buộc, dùng `getRequiredProperty`, đồng thời hiểu rằng phương thức này không thay thế validation nghiệp vụ.

Ba quy tắc dễ áp dụng:

1. **Muốn số, boolean hoặc kiểu chuyên biệt thì chỉ định kiểu đích rõ ràng**, thay vì đọc chuỗi rồi parse thủ công ở nhiều nơi.
2. **Thiếu giá trị, giá trị rỗng và giá trị không chuyển đổi được là các tình huống khác nhau.** Default xử lý thiếu, converter xử lý kiểu, validation xử lý ràng buộc.
3. **Với cấu hình có cấu trúc hoặc nhiều key liên quan, ưu tiên `@ConfigurationProperties`.** `Environment#getProperty` phù hợp cho tra cứu có chủ đích từng property.

Khi đọc một dòng mã như `environment.getProperty("app.retry-count", Integer.class, 3)`, hãy hiểu đầy đủ: **tra key theo thứ tự nguồn cấu hình, chuyển giá trị tìm được thành Integer, và chỉ dùng 3 khi không có giá trị phù hợp để tra cứu**.
