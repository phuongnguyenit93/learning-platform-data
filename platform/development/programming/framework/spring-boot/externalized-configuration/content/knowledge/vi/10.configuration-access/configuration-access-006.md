# Chuyển đổi kiểu và giá trị mặc định khi dùng @Value

## 1. Vì sao đọc cấu hình không chỉ là lấy một chuỗi?

Trong Spring Boot, giá trị cấu hình có thể xuất phát từ `application.yml`, `application.properties`, biến môi trường hoặc tham số dòng lệnh. Các nguồn này cung cấp những thuộc tính có tên, chẳng hạn `payment.retry-count`, `payment.enabled` hoặc `payment.timeout`. Nhưng mã Java thường cần **kiểu dữ liệu cụ thể**, không chỉ văn bản.

Ví dụ, một ứng dụng thanh toán cần:

- Số lần thử lại: kiểu `int` để đếm số lần.
- Trạng thái bật/tắt: kiểu `boolean` để ra quyết định.
- Thời gian chờ: kiểu `Duration` để truyền vào HTTP client.
- Tên chế độ: có thể là kiểu `enum` thay vì chuỗi tùy ý.

Nếu mỗi bean tự gọi `Integer.parseInt(...)` và tự xử lý giá trị thiếu, logic chuyển đổi sẽ bị lặp ở nhiều nơi. Spring hỗ trợ annotation `@Value` để **giải quyết một giá trị cấu hình và đưa nó vào một điểm injection**, đồng thời chuyển sang kiểu Java của trường, tham số constructor hoặc phương thức nhận giá trị.

Ví dụ:

```java
@Value("${payment.retry-count:3}")
private int retryCount;
```

Khi bean được tạo, Spring xử lý placeholder `${payment.retry-count:3}`, tìm khóa `payment.retry-count` trong hệ thống cấu hình, dùng `3` nếu không tìm thấy, rồi chuyển giá trị phù hợp sang `int`.

Chú ý: `3` trong chuỗi annotation là **biểu diễn văn bản của giá trị mặc định**. Nó trở thành số nguyên nhờ cơ chế chuyển kiểu của Spring. Đây là hai bước khác nhau.

```text
Nguồn cấu hình (YAML / env / CLI / ...)
                  |
                  v
           Spring Environment
                  |
                  v
    Resolve placeholder ${key:default}
                  |
                  v
      Chọn chuỗi/giá trị có hiệu lực
                  |
                  v
      ConversionService / type conversion
                  |
                  v
    int / boolean / Duration / enum / ...
                  |
                  v
         Bean nhận giá trị đã chuyển
```

Bài này tập trung vào hai câu hỏi: **Spring đổi giá trị cấu hình sang kiểu Java như thế nào?** Và **điều gì xảy ra khi khóa không tồn tại hoặc giá trị không hợp lệ?**

## 2. Cú pháp @Value và vai trò của placeholder

`@Value` có thể đặt ở trường, tham số constructor hoặc phương thức được Spring xử lý. Trong ứng dụng hiện đại, nên ưu tiên **constructor injection** vì các phụ thuộc được xác định rõ khi tạo đối tượng và có thể được giữ ở trường `final`.

Cú pháp phổ biến:

```java
@Value("${ten.thuoc.tinh}")
```

Cú pháp có mặc định:

```java
@Value("${ten.thuoc.tinh:gia-tri-mac-dinh}")
```

Trong đó:

1. `ten.thuoc.tinh` là khóa để tra cứu.
2. Dấu hai chấm `:` trong placeholder phân cách khóa và giá trị mặc định.
3. Phần mặc định chỉ được dùng khi resolver **không tìm thấy** thuộc tính theo cơ chế đang áp dụng.
4. Kết quả được chuyển sang kiểu Java đích khi Spring tạo bean.

Ví dụ, tệp `src/main/resources/application.yml`:

```yaml
payment:
  enabled: true
  retry-count: 5
  timeout: 4s
  label: Checkout
```

Với lớp:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentSettings {
    private final boolean enabled;
    private final int retryCount;
    private final String label;

    public PaymentSettings(
            @Value("${payment.enabled:false}") boolean enabled,
            @Value("${payment.retry-count:3}") int retryCount,
            @Value("${payment.label:Payment}") String label) {
        this.enabled = enabled;
        this.retryCount = retryCount;
        this.label = label;
    }

    public boolean enabled() {
        return enabled;
    }

    public int retryCount() {
        return retryCount;
    }

    public String label() {
        return label;
    }
}
```

Khi các thuộc tính trong YAML được tìm thấy và không có nguồn ưu tiên cao hơn ghi đè:

```text
enabled    = true
retryCount = 5
label      = Checkout
```

Nếu bỏ `payment.retry-count` khỏi mọi nguồn, constructor nhận `3`. Nếu bỏ `payment.enabled`, constructor nhận `false`. Nếu bỏ `payment.label`, constructor nhận chuỗi `Payment`. Không phải sửa lớp Java.

**Điểm cần ghi nhớ:** `@Value` là cách khai báo giá trị cần chèn vào một bean do Spring quản lý. Tạo đối tượng bằng `new PaymentSettings(...)` trong mã Java thuần không khiến Spring tự xử lý annotation.

## 3. Thứ tự xử lý: tra cứu trước, đổi kiểu sau

Có thể quan sát cùng một thuộc tính ở hai góc độ.

```yaml
inventory:
  max-items: 12
```

Đọc thông qua `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class InventoryReader {

    private final Environment environment;

    public InventoryReader(Environment environment) {
        this.environment = environment;
    }

    public String asText() {
        return environment.getProperty("inventory.max-items");
    }

    public Integer asNumber() {
        return environment.getProperty(
                "inventory.max-items", Integer.class);
    }
}
```

`getProperty(key)` trả về dạng `String` theo giao diện của phương thức. Phiên bản nhận `Integer.class` yêu cầu chuyển sang kiểu đích. Với `@Value`, kiểu đích thường được xác định từ trường hoặc tham số constructor.

```java
public InventoryService(
        @Value("${inventory.max-items:10}") int maxItems) {
    this.maxItems = maxItems;
}
```

Giá trị mặc định `10` được cung cấp **trước bước chuyển kiểu**. Nếu khóa không có, Spring lấy văn bản `"10"` rồi chuyển sang `int`. Nếu khóa có giá trị `"12"`, Spring chuyển `"12"` thành `12`.

Sự khác nhau quan trọng:

| Tình trạng | Bước resolve | Bước chuyển kiểu |
| --- | --- | --- |
| Khóa có `12` | Chọn `12` | Chuyển sang `int` thành 12 |
| Khóa vắng, fallback `10` | Chọn `10` | Chuyển sang `int` thành 10 |
| Khóa có `abc` | Chọn `abc` | Không chuyển được sang `int`, có thể làm bean khởi tạo thất bại |
| Khóa vắng, không fallback | Không tìm được giá trị | Có thể lỗi unresolved placeholder khi tạo bean |
| Khóa có chuỗi rỗng | Giá trị rỗng vẫn có thể được coi là đã khai báo | Tùy kiểu đích và converter, có thể lỗi hoặc thành `null` |

Đừng nhầm **chọn giá trị** với **kiểm tra giá trị hợp lệ**. Placeholder mặc định không phải validator và không phải bộ sửa mọi chuỗi sai.

## 4. Chuyển sang String, số nguyên và số thực

`String` là trường hợp trực tiếp nhất:

```java
@Value("${store.name:My Store}")
private String storeName;
```

Nếu `store.name` tồn tại, trường nhận giá trị từ nguồn cấu hình; nếu không, nó nhận `"My Store"`.

Với kiểu số:

```java
@Value("${store.max-orders:100}")
private int maxOrders;

@Value("${store.tax-rate:0.08}")
private double taxRate;
```

Spring sử dụng cơ chế chuyển kiểu phù hợp để đổi từ giá trị cấu hình sang `int` hoặc `double`. Trong ví dụ:

```yaml
store:
  max-orders: 250
  tax-rate: 0.10
```

Kết quả là `maxOrders=250` và `taxRate=0.10`.

### 4.1. Kiểu nguyên thủy và kiểu bao

`int`, `long` và `double` là kiểu nguyên thủy của Java; `Integer`, `Long` và `Double` là đối tượng bao. Khác biệt quan trọng khi gặp `null`:

- Kiểu nguyên thủy không nhận được `null` làm giá trị hợp lệ.
- Kiểu bao có thể biểu diễn không có giá trị, nhưng điều đó **không có nghĩa** `@Value` tự động xử lý mọi thuộc tính thiếu một cách an toàn.
- Một chuỗi không phải số, ví dụ `"many"`, vẫn không thể được chuyển thành `Integer` hợp lệ.

```java
@Value("${store.max-orders:100}")
private Integer maxOrders;
```

Ở đây mặc định là 100, không phải `null`. Nếu muốn thể hiện “không có giá trị” như một trạng thái nghiệp vụ, nên thiết kế rõ cách biểu diễn và kiểm tra thay vì dựa vào việc converter xử lý chuỗi rỗng.

### 4.2. Giá trị sai cú pháp không kích hoạt fallback

Ví dụ:

```yaml
store:
  max-orders: many
```

Với:

```java
@Value("${store.max-orders:100}")
private int maxOrders;
```

Spring **đã tìm thấy** khóa `store.max-orders`. Vì vậy, fallback `100` không được dùng chỉ vì `"many"` không phải số. Bước chuyển kiểu thất bại và bean có thể không được khởi tạo. Muốn sửa, cần cung cấp giá trị hợp lệ hoặc có logic kiểm tra/khôi phục rõ ràng.

Đây là một lợi thế trong vận hành: ứng dụng có thể báo lỗi sớm khi cấu hình quan trọng sai kiểu, thay vì âm thầm hoạt động với giá trị khác ý định triển khai.

## 5. Chuyển sang boolean

Một trường bật/tắt thường được cấu hình bằng `true` hoặc `false`:

```yaml
audit:
  enabled: true
```

Và được chèn vào:

```java
@Value("${audit.enabled:false}")
private boolean auditEnabled;
```

Nếu có `audit.enabled=true`, trường là `true`. Nếu thiếu khóa, fallback `false` được chuyển thành `boolean false`.

Một ví dụ constructor injection:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final boolean enabled;

    public AuditService(
            @Value("${audit.enabled:false}") boolean enabled) {
        this.enabled = enabled;
    }

    public boolean shouldRecord() {
        return enabled;
    }
}
```

Điều này cho phép thay đổi hành vi giữa các môi trường mà không sửa `AuditService`. Ví dụ:

```bash
java -jar app.jar --audit.enabled=true
```

Đối số dòng lệnh có thể ghi đè cấu hình từ YAML theo thứ tự ưu tiên nguồn tiêu chuẩn.

Spring có các converter cho boolean, nhưng nên dùng dạng `true`/`false` dễ đọc và thống nhất thay vì phụ thuộc vào mọi biến thể văn bản mà một converter có thể chấp nhận. Nếu cấu hình có `audit.enabled=maybe`, không nên kỳ vọng fallback `false` sẽ tự xử lý giá trị không hợp lệ.

## 6. Chuyển sang Duration và các kiểu đặc thù

Thời lượng thường được cấu hình dưới dạng `2s`, `500ms` hoặc `1m`. Trong Spring Boot, những converter phục vụ cấu hình có thể biến biểu diễn thời lượng thành `java.time.Duration` khi hệ thống `ConversionService` thích hợp được đăng ký.

Ví dụ:

```yaml
gateway:
  connect-timeout: 2s
  read-timeout: 1500ms
```

Với ứng dụng Spring Boot có khả năng chuyển đổi `Duration`:

```java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayTimeouts {

    private final Duration connectTimeout;
    private final Duration readTimeout;

    public GatewayTimeouts(
            @Value("${gateway.connect-timeout:3s}")
            Duration connectTimeout,
            @Value("${gateway.read-timeout:2s}")
            Duration readTimeout) {
        this.connectTimeout = connectTimeout;
        this.readTimeout = readTimeout;
    }

    public Duration connectTimeout() {
        return connectTimeout;
    }

    public Duration readTimeout() {
        return readTimeout;
    }
}
```

Giá trị mong đợi trong ví dụ là hai giây và 1500 mili giây. Khi converter phù hợp hiện diện, bean nhận hai `Duration` đã được chuyển kiểu; mã sử dụng không cần tự xử lý hậu tố `s` hoặc `ms`.

**Lưu ý về môi trường:** Hỗ trợ kiểu và đơn vị phụ thuộc vào `ConversionService` thực tế, phiên bản/framework và nơi binding. Spring Boot có cơ chế chuyển đổi bổ sung cho cấu hình; ứng dụng Spring Framework thuần không nên mặc định hỗ trợ mọi ký hiệu như `3s`. Nếu cấu hình theo nhóm gồm nhiều `Duration` hoặc cần quy tắc đơn vị/validation rõ ràng, `@ConfigurationProperties` thường thích hợp hơn.

Đối với các giá trị thời lượng, nên ghi rõ đơn vị thay vì dùng số trần:

```yaml
gateway:
  connect-timeout: 3s
```

Thứ này dễ hiểu hơn `gateway.connect-timeout=3000`, vì người đọc không cần đoán 3000 là mili giây, giây hay một đơn vị do ứng dụng tự quy định.

## 7. Chuyển sang enum

Giả sử ứng dụng có hai chế độ xử lý:

```java
public enum DispatchMode {
    SAFE,
    FAST
}
```

Có thể nhận giá trị bằng `@Value` nếu converter phù hợp với kiểu enum được sử dụng:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DispatchSettings {
    private final DispatchMode mode;

    public DispatchSettings(
            @Value("${dispatch.mode:SAFE}") DispatchMode mode) {
        this.mode = mode;
    }

    public DispatchMode mode() {
        return mode;
    }
}
```

Tệp cấu hình:

```yaml
dispatch:
  mode: FAST
```

Trong trường hợp converter chuyển chuỗi tên enum, bean nhận `DispatchMode.FAST`. Khi khóa không có, `SAFE` là giá trị mặc định.

Cách tiếp cận này có lợi thế so với chuỗi tự do vì tập giá trị hợp lệ được biểu diễn bởi enum. Tuy nhiên, giá trị nằm ngoài tập khai báo như `dispatch.mode=UNKNOWN` vẫn sẽ gây lỗi chuyển đổi, chứ không tự rơi về `SAFE`.

Để hạn chế khác biệt converter, khi viết cấu hình ví dụ nên dùng đúng tên enum đã khai báo. Với những nhóm thuộc tính cần kiểm soát quy tắc chuyển kiểu và lỗi nhập liệu, sử dụng `@ConfigurationProperties` kèm validation có thể giúp tập trung hợp đồng cấu hình.

## 8. Tình huống thiếu khóa: có và không có mặc định

Xét hai constructor parameter:

```java
public WorkerSettings(
        @Value("${worker.batch-size}") int batchSize,
        @Value("${worker.max-retries:3}") int maxRetries) {
    // ...
}
```

Nếu `worker.batch-size` không tồn tại, placeholder không có fallback. Trong cấu hình Spring thông dụng dùng strict placeholder resolution cho bean injection, quá trình tạo bean có thể thất bại vì không giải quyết được khóa.

Ngược lại, nếu `worker.max-retries` vắng mặt, `3` được dùng. Hai điều kiện này truyền đạt **hai ý định khác nhau**:

- Không có mặc định: thuộc tính có thể là bắt buộc trong môi trường đang chạy.
- Có mặc định: ứng dụng có một giá trị dự phòng đã được thiết kế.

Không nên thêm fallback cho mọi khóa chỉ để ứng dụng luôn khởi động. Ví dụ URL hệ thống thanh toán thật hoặc địa chỉ kho dữ liệu sản xuất là những giá trị có thể cần được cấp tường minh. Một fallback sai có thể khiến ứng dụng kết nối nhầm dịch vụ.

### 8.1. Mặc định là một phần của biểu thức injection

`${worker.max-retries:3}` không tự bổ sung khóa `worker.max-retries` vào `application.yml`. Nó chỉ nói rằng **điểm injection này** chấp nhận giá trị `3` nếu khóa không được tìm thấy.

Nếu một bean khác đọc khóa bằng:

```java
environment.getProperty("worker.max-retries")
```

và không có thuộc tính trong các nguồn cấu hình, kết quả có thể là `null`. Nó không biết fallback nằm trong annotation của bean thứ nhất.

Nếu cần một giá trị mặc định **dùng chung cho mọi điểm tra cứu**, nên đặt giá trị đó trong `application.yml` hoặc một nguồn cấu hình chung, rồi dùng annotation không phải lặp lại mặc định ở nhiều nơi.

## 9. Khóa thiếu khác với giá trị rỗng

Đây là một trong những điểm dễ gây lỗi nhất khi dùng `@Value`.

Giả sử:

```java
@Value("${notice.title:Untitled}")
private String title;
```

Nếu `notice.title` hoàn toàn không được khai báo, `title` nhận `Untitled`. Nhưng nếu có:

```properties
notice.title=
```

thì thuộc tính tồn tại với **giá trị rỗng**. Placeholder thông thường không coi mọi chuỗi rỗng là “không có khóa”. Kết quả có thể là chuỗi rỗng, không phải `Untitled`.

Với số nguyên:

```java
@Value("${notice.retry-count:3}")
private int retryCount;
```

và:

```properties
notice.retry-count=
```

giá trị rỗng có thể không chuyển được sang `int`; trong quá trình injection, bean có thể thất bại. Không nên suy luận rằng dấu `:3` là cơ chế sửa tất cả các giá trị rỗng hoặc không hợp lệ.

Bảng so sánh:

| Trạng thái của khóa | `@Value("${notice.title:Untitled}")` | `@Value("${notice.retry-count:3}") int` |
| --- | --- | --- |
| Không tồn tại | `Untitled` | 3 |
| Có giá trị hợp lệ | Giá trị tìm được | Số nguyên đã chuyển |
| Có giá trị rỗng | Có thể là chuỗi rỗng | Có thể lỗi chuyển kiểu |
| Có giá trị sai kiểu | Vẫn là chuỗi | Có thể lỗi chuyển kiểu |

Một quy tắc thiết kế hữu ích: **mặc định xử lý trường hợp vắng mặt; validation xử lý trường hợp có mặt nhưng không hợp lệ**.

## 10. Tên khóa canonical và biến môi trường

Đặt tên thuộc tính nhất quán giúp Spring Boot giải quyết placeholder trong nhiều nguồn.

Ví dụ YAML:

```yaml
orders:
  max-retries: 4
```

Nên viết placeholder theo dạng canonical, chữ thường, dấu gạch ngang khi tên có nhiều từ:

```java
@Value("${orders.max-retries:3}")
private int maxRetries;
```

Cách này giúp Spring Boot áp dụng các quy tắc tra cứu tương thích với tên thuộc tính của mình; cùng thuộc tính có thể được cấp từ file cấu hình hoặc biến môi trường theo quy ước.

Ví dụ trên Linux/macOS:

```bash
ORDERS_MAXRETRIES=8 java -jar app.jar
```

Trong cách ánh xạ thông dụng của Spring Boot, dấu chấm chuyển thành dấu gạch dưới, dấu gạch ngang trong tên thuộc tính bị loại bỏ và tên được viết hoa khi biểu diễn bằng biến môi trường. Vì vậy `orders.max-retries` có dạng tương ứng `ORDERS_MAXRETRIES`.

Đừng đoán rằng `ORDERS_MAX_RETRIES` luôn tương đương với `orders.max-retries` trong mọi cơ chế tra cứu. Một quy ước tên khóa nhất quán quan trọng đặc biệt khi dùng `@Value` vì nó khác với binding nguyên đối tượng bằng `@ConfigurationProperties`.

Ngoài ra, giá trị có thể đến từ nguồn ưu tiên cao hơn:

```bash
java -jar app.jar --orders.max-retries=9
```

Nếu có cả giá trị YAML `4` và đối số dòng lệnh `9` trong tình huống chuẩn, điểm injection dùng giá trị `9`. Fallback `3` không được dùng vì thuộc tính đã có.

## 11. Giá trị mặc định cũng có thể tham chiếu thuộc tính khác

Một fallback không nhất thiết là hằng số. Spring cho phép placeholder lồng nhau:

```java
@Value("${orders.max-retries:${defaults.retry-count:3}}")
private int maxRetries;
```

Hành vi mong đợi:

1. Nếu `orders.max-retries` tồn tại, sử dụng giá trị đó.
2. Nếu `orders.max-retries` vắng mặt nhưng `defaults.retry-count` tồn tại, sử dụng giá trị mặc định lấy từ `defaults.retry-count`.
3. Nếu cả hai đều vắng mặt, dùng `3`.
4. Chuyển kết quả sang `int`.

Ví dụ tệp cấu hình:

```properties
defaults.retry-count=5
```

Khi không có `orders.max-retries`, kết quả là 5. Nếu thêm `orders.max-retries=7`, kết quả thành 7. Nếu bỏ cả hai, kết quả là 3.

Kiểu biểu thức này hữu ích nếu nhiều thuộc tính có mặc định theo một cấu hình chung. Tuy nhiên, mặc định lồng nhiều tầng sẽ khó đọc và khó lần theo khi triển khai. Nếu cấu hình có quan hệ phụ thuộc phức tạp, nên cân nhắc mô hình `@ConfigurationProperties` và tính toán rõ ràng trong Java.

### 11.1. Mặc định có dấu hai chấm

Giá trị mặc định có thể là một URL:

```java
@Value("${service.endpoint:http://localhost:8080/api}")
private String endpoint;
```

Trong cơ chế placeholder thông dụng, dấu hai chấm **đầu tiên** phân tách tên khóa và mặc định; phần `http://localhost:8080/api` là giá trị mặc định cần dùng khi thiếu `service.endpoint`. Không nên đọc dấu `:` trong URL như một placeholder khác.

Nếu chuỗi mặc định chứa cú pháp đặc biệt hoặc biểu thức lồng phức tạp, cần kiểm tra cách escape và cách một lớp cấu hình trung gian xử lý nó; đừng mặc định mọi chuỗi có dấu `$` hay `:` đều được giữ nguyên qua mọi công cụ triển khai.

## 12. Phân biệt placeholder và SpEL trong @Value

`@Value` có thể dùng cú pháp placeholder `${...}` hoặc cú pháp biểu thức Spring Expression Language, viết tắt SpEL, `#{...}`.

```java
@Value("${pool.size:8}")
private int poolSize;

@Value("#{2 * 3}")
private int six;
```

Trường thứ nhất dùng **tra cứu cấu hình**. Trường thứ hai yêu cầu **đánh giá biểu thức**. Cả hai có thể nhận `int`, nhưng cơ chế và ý nghĩa khác nhau.

Trong một số tình huống, placeholder được giải quyết trước, rồi kết quả tham gia SpEL:

```java
@Value("#{${pool.workers:4} * 2}")
private int maxConnections;
```

Với `pool.workers=5`, kết quả mong đợi là `10`. Nhưng nếu `pool.workers=fast`, biểu thức không còn là phép nhân số hợp lệ. Đây không phải cách thích hợp để “chữa” cấu hình sai kiểu.

Không nên lạm dụng SpEL để xây logic cấu hình phức tạp, đặc biệt khi giá trị có thể đến từ nguồn không tin cậy. Với phép tính nghiệp vụ hoặc quy tắc có nhiều nhánh, một lớp Java có kiểm thử và validation rõ ràng thường dễ bảo trì hơn.

**Một khác biệt cần nhớ:** giá trị khai báo trong `application.yml` không mặc nhiên được xử lý như SpEL theo cùng cách một annotation `@Value("#{...}")` được đánh giá. Không coi mọi chuỗi cấu hình là mã biểu thức.

## 13. List, map và cấu trúc phức tạp: giới hạn của @Value

Các ví dụ trước là scalar: chuỗi, số, boolean, thời lượng hoặc enum. Nhưng một cấu hình phức tạp có thể gồm danh sách và đối tượng lồng nhau:

```yaml
mail:
  retries: 3
  recipients:
    - ops@example.invalid
    - audit@example.invalid
  smtp:
    host: smtp.example.invalid
    port: 2525
```

Nếu mỗi thuộc tính được tiêm riêng bằng `@Value`, class sẽ phải chứa nhiều annotation, các tên khóa dạng chuỗi và quy tắc chuyển kiểu phụ thuộc vào cấu trúc nguồn. Với list, hành vi chuyển đổi có thể khác nhau giữa chuỗi phân tách dấu phẩy và các giá trị chỉ số đến từ YAML; không nên xem `@Value("${mail.recipients}")` như giải pháp bảo đảm cho mọi kiểu danh sách ở mọi nguồn.

Một cách phù hợp hơn là dùng `@ConfigurationProperties`:

```java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        int retries,
        List<String> recipients,
        Smtp smtp
) {
    public record Smtp(String host, int port) {}
}
```

Sau khi đăng ký `MailProperties` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Spring Boot binder liên kết từng thuộc tính và phần tử theo cấu trúc. Với yêu cầu kiểm tra đầu vào, có thể thêm Bean Validation phù hợp.

Có thể ghi nhớ sự phân công:

- `@Value`: hợp với một vài giá trị đơn lẻ, cần được tiêm tại nơi dùng.
- `@ConfigurationProperties`: hợp với một nhóm cấu hình có cấu trúc, nhiều trường, chuyển kiểu và validation tập trung.
- `Environment`: hợp với việc tra cứu một khóa có chọn lựa hoặc chẩn đoán giá trị cấu hình.

Không cần thay toàn bộ `@Value` bằng `@ConfigurationProperties` trong mọi trường hợp; hãy chọn theo độ lớn và tính nhất quán của nhóm cấu hình.

## 14. Thí nghiệm hoàn chỉnh: cấu hình chuyển kiểu và fallback

Ta xây một ứng dụng nhỏ để quan sát cả bước chọn giá trị lẫn bước đổi kiểu.

Tạo `src/main/resources/application.yml`:

```yaml
demo:
  name: SampleService
  enabled: true
  max-retries: 4
  batch-size: 20
```

Tạo `DemoConfigurationApplication.java`:

```java
package com.example.valueconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoConfigurationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoConfigurationApplication.class, args);
    }

    @Bean
    ApplicationRunner printDemo(DemoSettings settings) {
        return args -> {
            System.out.println("=== VALUE CONVERSION ===");
            System.out.println("name        = " + settings.name());
            System.out.println("enabled     = " + settings.enabled());
            System.out.println("maxRetries  = " + settings.maxRetries());
            System.out.println("batchSize   = " + settings.batchSize());
            System.out.println("========================");
        };
    }
}
```

Tạo `DemoSettings.java`:

```java
package com.example.valueconversion;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DemoSettings {

    private final String name;
    private final boolean enabled;
    private final int maxRetries;
    private final long batchSize;

    public DemoSettings(
            @Value("${demo.name:Unnamed}") String name,
            @Value("${demo.enabled:false}") boolean enabled,
            @Value("${demo.max-retries:3}") int maxRetries,
            @Value("${demo.batch-size:10}") long batchSize) {
        this.name = name;
        this.enabled = enabled;
        this.maxRetries = maxRetries;
        this.batchSize = batchSize;
    }

    public String name() {
        return name;
    }

    public boolean enabled() {
        return enabled;
    }

    public int maxRetries() {
        return maxRetries;
    }

    public long batchSize() {
        return batchSize;
    }
}
```

Đóng gói ứng dụng bằng Gradle `bootJar` hoặc Maven theo cấu trúc dự án, rồi dùng đường dẫn tới JAR thực thi. `app.jar` dưới đây là tên minh họa.

### Lần A: chỉ có YAML

```bash
java -jar app.jar
```

Kết quả mong đợi:

```text
name        = SampleService
enabled     = true
maxRetries  = 4
batchSize   = 20
```

Các khóa đều tồn tại. Spring không cần dùng bất kỳ fallback nào trong constructor.

### Lần B: ghi đè bằng tham số dòng lệnh

```bash
java -jar app.jar \
  --demo.enabled=false \
  --demo.max-retries=9 \
  --demo.batch-size=35
```

Kết quả mong đợi:

```text
name        = SampleService
enabled     = false
maxRetries  = 9
batchSize   = 35
```

Tất cả số và boolean được chuyển sang kiểu Java đã khai báo. Giá trị `name` vẫn đến từ YAML vì dòng lệnh không ghi đè khóa này.

### Lần C: kiểm tra fallback

Tạo một bản cấu hình thử nghiệm mà các khóa `demo.enabled`, `demo.max-retries` và `demo.batch-size` đều không xuất hiện trong bất kỳ nguồn ưu tiên nào. Có thể tạm bỏ các dòng đó trong YAML và đóng gói lại, rồi chạy mà không truyền override:

```bash
java -jar app.jar
```

Kết quả mong đợi theo fallback:

```text
name        = SampleService
enabled     = false
maxRetries  = 3
batchSize   = 10
```

Lưu ý, nếu giá trị vẫn còn trong YAML hoặc biến môi trường của shell, fallback sẽ không được dùng. Thí nghiệm này chứng minh giá trị mặc định nằm tại từng annotation của điểm injection.

### Lần D: giá trị không chuyển được sang int

Chạy:

```bash
java -jar app.jar --demo.max-retries=many
```

Kỳ vọng: trong lúc Spring tạo `DemoSettings`, giá trị `many` không thể được chuyển thành `int` và quá trình khởi động bean thất bại, kèm thông báo liên quan đến lỗi chuyển kiểu hoặc tạo bean. **Không nhận `3`** dù annotation có fallback.

### Lần E: khóa đã khai báo thành rỗng

Chạy:

```bash
java -jar app.jar --demo.max-retries=
```

Giá trị được cung cấp là chuỗi rỗng, khác với việc không truyền khóa. Với tham số constructor kiểu `int`, cấu hình này không thể được xem như số nguyên hợp lệ, có thể khiến việc tạo bean thất bại. Không nên dựa vào fallback `3` để sửa trường hợp rỗng.

## 15. Bảng dự đoán kết quả trước khi chạy

Bảng sau giả sử file YAML ban đầu chứa `demo.max-retries=4` và điểm injection là:

```java
@Value("${demo.max-retries:3}") int maxRetries
```

| Nguồn cung cấp | Chuỗi/giá trị có hiệu lực | Kết quả kỳ vọng |
| --- | --- | --- |
| Chỉ YAML | `4` | `maxRetries = 4` |
| Tham số `--demo.max-retries=9` | `9` | `maxRetries = 9` |
| Không có khóa ở bất kỳ nguồn nào | Fallback `3` | `maxRetries = 3` |
| Tham số `--demo.max-retries=abc` | `abc` | Lỗi chuyển đổi sang `int` |
| Tham số `--demo.max-retries=` | Chuỗi rỗng | Có thể thất bại khi inject vào `int` |

Dự đoán tương tự cho:

```java
@Value("${demo.enabled:false}") boolean enabled
```

Với `true` hoặc `false` hợp lệ, bean nhận boolean tương ứng. Khi khóa vắng, nó nhận `false`. Một giá trị không thể chuyển đổi sang boolean không tự chuyển thành fallback chỉ vì fallback đã được khai báo.

Khi thực hành, luôn đổi **một yếu tố mỗi lần**: giá trị YAML, biến môi trường, tham số dòng lệnh hoặc sự hiện diện của khóa. Làm vậy sẽ dễ phân biệt lỗi ưu tiên nguồn, lỗi placeholder và lỗi chuyển kiểu.

## 16. Các lỗi thường gặp khi dùng @Value

### 16.1. Quên dấu $ trong placeholder

Sai:

```java
@Value("{demo.max-retries:3}")
private int maxRetries;
```

Chuỗi bên trong annotation lúc này là văn bản `{demo.max-retries:3}`, không phải placeholder hợp lệ. Nếu Spring cố chuyển nguyên văn chuỗi này sang `int`, việc chuyển đổi sẽ thất bại.

Đúng:

```java
@Value("${demo.max-retries:3}")
private int maxRetries;
```

### 16.2. Dùng tên khóa không thống nhất

Nếu YAML khai báo `demo.max-retries` nhưng annotation viết `${demo.maxretry:3}`, Spring có thể không tìm được giá trị và dùng fallback `3`. Ứng dụng vẫn khởi động nhưng kết quả không theo ý định. Với các khóa quan trọng, cần đặt tên rõ ràng và kiểm tra từ nguồn.

### 16.3. Gọi một giá trị không hợp lệ là “thiếu”

`demo.max-retries=xyz` là khóa **có mặt** nhưng giá trị **sai kiểu**. Fallback không được thiết kế để che giấu sai kiểu này. Phải sửa giá trị hoặc thiết kế xử lý lỗi phù hợp.

### 16.4. Dùng chuỗi rỗng để yêu cầu mặc định

Viết `demo.max-retries=` không giống xóa khóa khỏi các nguồn. Chuỗi rỗng có thể khiến chuyển đổi thất bại với kiểu nguyên thủy. Khi muốn dùng fallback, hãy loại bỏ nguồn khai báo khóa thay vì cấp chuỗi rỗng.

### 16.5. Cố inject vào đối tượng tự tạo bằng new

`@Value` chỉ được Spring xử lý đúng trong vòng đời đối tượng do Spring quản lý hoặc một đối tượng được xử lý qua cơ chế framework tương ứng. Một đối tượng tạo thủ công bằng `new` không tự nhận giá trị annotation.

### 16.6. Phụ thuộc vào giá trị thay đổi sau khởi động

Thông thường, giá trị `@Value` được đưa vào bean trong quá trình tạo bean. Khi file cấu hình thay đổi lúc ứng dụng đang chạy, trường đã được inject không tự động được cập nhật chỉ vì file mới có giá trị khác. Để quan sát cấu hình mới, hãy khởi động lại tiến trình hoặc dùng cơ chế cập nhật cấu hình được thiết kế riêng.

### 16.7. Giả định mọi kiểu phức tạp được chuyển đổi giống nhau

Số và boolean đơn giản thường ít gây bất ngờ. Các kiểu như `Duration`, `DataSize`, list, map, URI hoặc kiểu tự định nghĩa có thể cần converter, binder hoặc cấu hình bổ sung thích hợp. Nếu ứng dụng có cấu hình nhiều trường cùng cấu trúc, hãy chọn `@ConfigurationProperties` thay vì gắn nhiều `@Value` rời rạc.

### 16.8. Đặt fallback không an toàn cho dữ liệu bắt buộc

`@Value("${payment.gateway-url:http://localhost:8080}")` có thể khiến môi trường production kết nối nhầm địa chỉ thử nghiệm khi cấu hình bị thiếu. Với endpoint quan trọng, có thể nên **không đặt fallback** và để ứng dụng báo lỗi khởi động thay vì tự chọn giá trị có rủi ro.

## 17. Tổ chức cấu hình để dễ vận hành

Một số quy ước hữu ích:

1. **Dùng giá trị mặc định an toàn.** Số lần retry thấp, tính năng tùy chọn tắt hoặc thời gian chờ hợp lý có thể phù hợp làm mặc định, tùy mục tiêu ứng dụng.
2. **Ghi rõ đơn vị.** Với thời lượng, ưu tiên `2s` hoặc `500ms` thay vì số trần khó hiểu.
3. **Dùng tên khóa canonical.** Điều này giúp nguồn YAML, environment variable và placeholder dễ truy vết.
4. **Đặt giá trị dùng chung trong nguồn cấu hình.** Nếu ba bean đều cần cùng fallback, đưa nó vào `application.yml` thay vì lặp `:3` tại ba nơi.
5. **Để bean giữ kiểu phù hợp.** Số lần retry nên là `int`, cờ nên là `boolean`, thời lượng nên là `Duration` khi converter thích hợp đã sẵn sàng.
6. **Phân biệt thiếu với sai.** Khóa thiếu có thể được giải quyết bằng fallback; khóa sai cần validation hoặc sửa cấu hình.
7. **Không in cấu hình nhạy cảm.** Khi debug, chỉ in những khóa vô hại; đừng vô tình ghi password, token hoặc URL có thông tin xác thực vào log.
8. **Tập trung nhóm cấu hình khi tăng độ phức tạp.** Với nhiều trường có quan hệ với nhau, hãy cân nhắc `@ConfigurationProperties` và các quy tắc validation.

## 18. Bài tập kiểm tra hiểu biết

**Bài 1.** Cho:

```java
@Value("${cache.capacity:128}")
private int capacity;
```

Hãy dự đoán `capacity` khi: (a) không khai báo khóa; (b) `cache.capacity=256`; (c) `cache.capacity=large`. Giải thích trường hợp nào dùng fallback và trường hợp nào lỗi chuyển đổi.

**Bài 2.** Cho:

```java
@Value("${jobs.enabled:false}")
private boolean enabled;
```

Với YAML `jobs.enabled=true` và dòng lệnh `--jobs.enabled=false`, giá trị nào có hiệu lực? Vì sao việc chọn nguồn khác với chuyển sang `boolean`?

**Bài 3.** Cho:

```java
@Value("${jobs.retry-count:${defaults.retry-count:2}}")
private int retryCount;
```

Hãy dự đoán kết quả với ba trạng thái: chỉ có `defaults.retry-count=6`; có thêm `jobs.retry-count=8`; hoặc cả hai khóa đều không tồn tại. Kết quả lần lượt là 6, 8 và 2 trong cơ chế placeholder phù hợp.

**Bài 4.** Một ứng dụng có `@Value("${server.label:App}") String label`, nhưng file properties khai báo `server.label=`. Tại sao kết quả có thể là chuỗi rỗng, không phải `App`? Hãy phân biệt khóa vắng với khóa có giá trị rỗng.

**Bài 5.** Cho `@Value("${gateway.timeout:3s}") Duration timeout`. Vì sao cần quan tâm đến `ConversionService` đang dùng? Khi nào nên đưa thời lượng vào một lớp `@ConfigurationProperties` có validation thay cho một annotation đơn lẻ?

**Bài 6.** Viết một bean nhận hai giá trị `orders.max-retries` kiểu `int` và `orders.enabled` kiểu `boolean` qua constructor, có fallback lần lượt là 3 và false. Sau đó thử thay từng giá trị trên dòng lệnh và quan sát kết quả.

## 19. Ghi nhớ

Khi dùng `@Value`, hãy tách rõ các bước:

```text
@Value("${orders.max-retries:3}")
             |
             v
   Tìm orders.max-retries trong Environment
             |
       +-----+------+
       |            |
    Tìm thấy     Không thấy
       |            |
  Dùng giá trị    Dùng "3"
       |            |
       +-----+------+
             |
             v
       Chuyển sang int
             |
       +-----+------+
       |            |
  Hợp lệ         Sai kiểu
       |            |
       v            v
   Inject vào     Lỗi tạo bean
   constructor
```

**Placeholder quyết định lấy giá trị từ đâu và dùng mặc định nào khi thiếu; cơ chế chuyển kiểu quyết định giá trị đó có thể trở thành kiểu Java đích hay không.** Giá trị sai kiểu và giá trị rỗng không tự biến thành fallback.

Dùng `@Value` khi cần một số ít thuộc tính đơn lẻ, nhất là qua constructor injection. Khi cấu hình trở thành một tập có cấu trúc, nhiều quy tắc validation hoặc converter, hãy chuyển sang thiết kế `@ConfigurationProperties` cho rõ ràng và dễ bảo trì.

Tài liệu tham khảo: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).