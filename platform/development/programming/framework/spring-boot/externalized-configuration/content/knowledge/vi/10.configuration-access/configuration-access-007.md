# Sử dụng SpEL trong `@Value` và giới hạn khi đọc dữ liệu cấu hình

## 1. Bối cảnh: từ thuộc tính cấu hình đến giá trị được tiêm vào Bean

Trong Spring Boot, cấu hình ứng dụng có thể được cung cấp qua `application.properties`, `application.yml`, biến môi trường, Java system properties, đối số dòng lệnh và các nguồn `PropertySource` khác. Một bean có thể cần đọc những giá trị này để quyết định thời gian chờ, ngưỡng giới hạn hoặc hành vi tính năng.

Spring Framework hỗ trợ annotation `@Value` để tiêm một giá trị vào field, constructor parameter, method parameter hoặc setter được quản lý bởi container. Hai cú pháp thường gặp trong `@Value` là:

~~~java
@Value("${app.name:demo}")
private String appName;

@Value("#{T(java.lang.Math).max(2, 5)}")
private int maximum;
~~~

Nhìn gần giống nhau nhưng cơ chế khác nhau:

- **Property placeholder `${...}`**: hỏi một tên thuộc tính trong hệ thống cấu hình, có thể kèm giá trị mặc định.
- **Spring Expression Language (SpEL) `#{...}`**: đánh giá một biểu thức, có thể thực hiện phép tính, điều kiện, truy xuất property, gọi phương thức hoặc tham chiếu bean trong evaluation context.

SpEL hữu ích khi cần **biến đổi một giá trị nhỏ tại điểm tiêm**. Tuy nhiên, đối với một nhóm cấu hình lớn, có cấu trúc, cần chuyển kiểu và validation, Spring Boot thường khuyến nghị `@ConfigurationProperties`. Hiểu rõ ranh giới này giúp tránh việc biến file cấu hình thành nơi chứa logic nghiệp vụ khó kiểm soát.

## 2. Hai cú pháp: `${...}` không đồng nghĩa với `#{...}`

### 2.1. Property placeholder: lấy cấu hình theo khóa

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

Ở đây Spring tìm thuộc tính `app.retry.max-attempts`. Nếu có giá trị `5`, field được tiêm `5`. Nếu không tìm được, sử dụng default `3`. Chuyển đổi sang `int` được thực hiện thông qua hệ thống chuyển kiểu thích hợp của Spring.

Đặc điểm:

- Phần trong dấu ngoặc nhọn là **tên thuộc tính**, không phải câu lệnh Java.
- Dấu `:` ngăn giữa khóa và giá trị dự phòng.
- Giá trị có mặt nhưng **không hợp lệ** không tự động bị thay bằng default.
- Placeholder thường lấy giá trị cuối cùng sau khi Spring xét thứ tự ưu tiên giữa các nguồn cấu hình.

### 2.2. SpEL: tính toán một biểu thức

~~~java
@Value("#{6 * 7}")
private int answer;

@Value("#{'spring boot'.toUpperCase()}")
private String title;

@Value("#{T(java.lang.Math).max(10, 25)}")
private int limit;
~~~

Kết quả tương ứng là `42`, `SPRING BOOT` và `25`. SpEL dùng cú pháp riêng, không phải Java source code đầy đủ: không thể viết mọi câu lệnh Java tùy ý vào một chuỗi SpEL.

Dấu hiệu nhận biết nhanh:

| Cú pháp | Ví dụ | Mục đích |
| --- | --- | --- |
| `${key}` | `${server.port}` | Tham chiếu thuộc tính |
| `${key:default}` | `${app.timeout:5s}` | Tham chiếu với giá trị dự phòng |
| `#{expression}` | `#{2 + 3}` | Đánh giá biểu thức |
| Kết hợp | `#{${app.workers:2} * 2}` | Lấy cấu hình rồi tính toán |

**Ghi nhớ:** dấu mở `${` và `#{` khác nhau. Viết `${2 + 3}` không phải cách tính `5`; Spring sẽ xem `2 + 3` như một tên thuộc tính cần tra cứu.

## 3. Ví dụ khởi đầu với `@Value` trong constructor

Giả sử file `src/main/resources/application.yml`:

~~~yaml
app:
  retry:
    max-attempts: 4
  gateway:
    connect-timeout: 3s
  mode: development
~~~

Tạo bean:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewaySettings {

    private final int maxAttempts;
    private final int doubledAttempts;
    private final String normalizedMode;

    public GatewaySettings(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("#{${app.retry.max-attempts:3} * 2}") int doubledAttempts,
            @Value("#{'${app.mode:local}'.toUpperCase()}") String normalizedMode) {

        this.maxAttempts = maxAttempts;
        this.doubledAttempts = doubledAttempts;
        this.normalizedMode = normalizedMode;
    }

    public int maxAttempts() {
        return maxAttempts;
    }

    public int doubledAttempts() {
        return doubledAttempts;
    }

    public String normalizedMode() {
        return normalizedMode;
    }
}
~~~

Trong điều kiện các thuộc tính được nạp như trên, giá trị là:

~~~text
maxAttempts     = 4
doubledAttempts = 8
normalizedMode  = DEVELOPMENT
~~~

Giải thích:

1. `${app.retry.max-attempts:3}` được xử lý như tham chiếu thuộc tính.
2. Với biểu thức `#{${app.retry.max-attempts:3} * 2}`, kết quả placeholder tạo thành biểu thức số `4 * 2`.
3. SpEL đánh giá phép nhân và đưa kết quả về kiểu `int` tại constructor parameter.
4. Ví dụ chuỗi bọc giá trị trong dấu nháy để nó trở thành string literal của SpEL.

**Giới hạn quan trọng:** cách nhúng một chuỗi cấu hình trực tiếp vào biểu thức SpEL có thể nguy hiểm hoặc làm biểu thức sai cú pháp nếu giá trị chứa dấu nháy đơn, ký tự đặc biệt hay văn bản không đáng tin cậy. Ví dụ chuyển chữ hoa trên chỉ nên dùng để minh họa cú pháp; với dữ liệu đến từ bên ngoài, ưu tiên nhận một chuỗi bằng placeholder hoặc Binder rồi xử lý chuỗi trong Java bình thường.

## 4. Thứ tự xử lý khi kết hợp placeholder và SpEL

Khi một biểu thức `@Value` chứa cả placeholder và SpEL, về mặt khái niệm hãy hình dung chuỗi thao tác:

~~~text
Nguồn cấu hình Spring Boot
       ↓
Tra cứu tên thuộc tính / giải quyết placeholder
       ↓
Đưa giá trị đã giải quyết vào biểu thức
       ↓
Đánh giá SpEL trong context của bean
       ↓
Chuyển kết quả sang kiểu đích của injection point
       ↓
Tạo bean với giá trị được tiêm
~~~

Ví dụ:

~~~java
@Value("#{${app.pool.size:8} + 2}")
private int poolSizeWithBuffer;
~~~

Nếu `app.pool.size=10` thì Spring có thể đánh giá `10 + 2` và tiêm `12`.

Nhưng nếu cấu hình là:

~~~yaml
app:
  pool:
    size: many
~~~

thì biểu thức được tạo từ placeholder không còn là phép toán số hợp lệ. Default `8` không giúp vì khóa `app.pool.size` vẫn **tồn tại**. Lúc này lỗi có thể xảy ra trong quá trình đánh giá SpEL hoặc chuyển kiểu, dẫn đến thất bại khi tạo bean.

Khi biểu thức có tác dụng nghiệp vụ quan trọng, nên **đưa phép tính ra code Java** để dễ kiểm thử, debug và áp dụng validation. SpEL không phải một lớp thay thế cho việc kiểm soát dữ liệu đầu vào.

## 5. Các phép toán SpEL thường dùng trong `@Value`

### 5.1. Phép toán số học

~~~java
@Value("#{2 + 5}")
private int sum;

@Value("#{10 * 3}")
private int total;

@Value("#{100 / 4}")
private int quotient;

@Value("#{10 % 3}")
private int remainder;
~~~

SpEL hỗ trợ cộng, trừ, nhân, chia, chia lấy dư và các toán tử thích hợp khác. Phép chia, chuyển kiểu số và kết quả kiểu đích cần được hiểu theo semantics của biểu thức; không nên mặc định nó luôn hành xử giống một phép chia số nguyên trong mọi trường hợp.

Ví dụ dùng một giá trị cấu hình:

~~~yaml
app:
  worker:
    base-count: 4
~~~

~~~java
@Value("#{${app.worker.base-count:2} * 3}")
private int calculatedWorkers;
~~~

Trong ví dụ này, kết quả có thể là `12`. Nếu muốn kiểm soát ngưỡng min/max, có thể dùng phép gọi phương thức hay Java thay vì tăng độ phức tạp của biểu thức.

### 5.2. Phép so sánh và điều kiện

~~~java
@Value("#{10 > 5}")
private boolean enabled;

@Value("#{${app.retry.max-attempts:3} > 5 ? 'aggressive' : 'normal'}")
private String retryMode;
~~~

Phép so sánh tạo ra boolean; toán tử điều kiện `condition ? trueValue : falseValue` chọn một trong hai nhánh.

Giả sử `app.retry.max-attempts=8`, `retryMode` là `aggressive`. Nếu giá trị là `2`, kết quả là `normal`.

Cách này có thể phù hợp cho một phép hiển thị đơn giản. Nếu chế độ retry ảnh hưởng đến hành vi phức tạp, hãy mô hình hóa bằng một chính sách hoặc class Java có kiểm thử thay vì phân tán cùng điều kiện tại nhiều `@Value`.

### 5.3. Phép truy xuất chuỗi

~~~java
@Value("#{'hello'.toUpperCase()}")
private String upper;

@Value("#{'  demo  '.trim()}")
private String trimmed;
~~~

SpEL có thể gọi phương thức trên đối tượng phù hợp. Các thao tác này được thực hiện khi biểu thức được đánh giá; không phải tất cả các thao tác mà Java hỗ trợ đều nên đưa vào tệp cấu hình.

### 5.4. Tham chiếu static method hoặc kiểu Java

~~~java
@Value("#{T(java.lang.Math).max(4, 9)}")
private int safeMin;

@Value("#{T(java.lang.Integer).parseInt('42')}")
private int parsed;
~~~

`T(java.lang.Math)` là type reference trong SpEL. Ví dụ minh họa quyền truy cập đến kiểu và static method, không phải gợi ý rằng bạn nên nhúng logic parsing phức tạp vào annotation.

## 6. Elvis operator và giá trị dự phòng trong SpEL

Ngoài cú pháp default của placeholder `${key:default}`, SpEL có **Elvis operator `?:`**:

~~~java
@Value("#{systemProperties['user.region'] ?: 'local'}")
private String region;
~~~

Biểu thức trên lấy `user.region` từ Java system properties trong SpEL evaluation context. Nếu giá trị là null hoặc rỗng theo semantics Elvis của Spring, nó có thể dùng `local`.

Điểm phân biệt:

- `${app.region:local}`: giá trị dự phòng của **property placeholder**, dùng khi không giải quyết được khóa cấu hình.
- `#{someExpression ?: 'local'}`: giá trị dự phòng **trong SpEL** sau khi đánh giá toán hạng trái.

Không nên nghĩ hai cách luôn tương đương, vì đối tượng được tra cứu và cách xử lý chuỗi rỗng có thể khác nhau. Đặc biệt, `systemProperties['user.region']` truy cập **Java system property**, không tự tương đương với phép tra cứu `app.region` qua toàn bộ `Environment`.

Khi mục tiêu đơn giản chỉ là “lấy một thuộc tính Spring Boot, nếu thiếu thì dùng mặc định”, cách dễ đọc và dễ kiểm soát hơn thường là:

~~~java
@Value("${app.region:local}")
private String region;
~~~

## 7. Truy cập Java system properties bằng SpEL

Một ví dụ truyền thống của `@Value` với SpEL là truy cập bản đồ `systemProperties`:

~~~java
@Value("#{systemProperties['user.home']}")
private String userHome;

@Value("#{systemProperties['java.version']}")
private String javaVersion;

@Value("#{systemProperties['user.region'] ?: 'unknown'}")
private String userRegion;
~~~

`systemProperties` cung cấp các Java system property trong evaluation context mặc định của Spring bean expression. Các giá trị như `user.home` và `java.version` do JVM cung cấp.

Có thể cấp một Java system property khi chạy:

~~~bash
java -Duser.region=asia -jar app.jar
~~~

Lúc đó biểu thức đọc `user.region` có thể nhận `asia`.

**Cảnh báo về phạm vi:** truy cập một system property trực tiếp **khác** với việc tra cứu một tên cấu hình Spring qua `Environment`. Nếu một thuộc tính có thể đến từ biến môi trường, `application.yml` và CLI, cần cân nhắc sử dụng `${canonical-key}` hoặc `@ConfigurationProperties` để tôn trọng cơ chế nguồn cấu hình của Spring Boot.

## 8. Truy cập bean khác bằng SpEL

SpEL có cú pháp tham chiếu bean thông qua ký tự `@`:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureEnabled;
~~~

Ví dụ bean:

~~~java
import org.springframework.stereotype.Component;

@Component("featurePolicy")
public class FeaturePolicy {
    public boolean isEnabled() {
        return true;
    }
}
~~~

Khi Spring đánh giá biểu thức, nó tìm bean `featurePolicy` và gọi phương thức `isEnabled()`.

Trường hợp này có tính năng động về mặt cú pháp, nhưng **giá trị tiêm vào vẫn thường được tính khi bean đang được tạo**, không phải mỗi lần truy cập field. Nếu trạng thái `featurePolicy` thay đổi sau đó, field boolean đã được tiêm không tự cập nhật.

Điều đó dẫn đến một quy tắc thực hành:

- Cần **một giá trị cấu hình ổn định** lúc khởi tạo bean: `@Value` có thể phù hợp.
- Cần **trạng thái nghiệp vụ thay đổi theo thời gian**: inject chính bean `FeaturePolicy` rồi gọi phương thức tại thời điểm sử dụng, thay vì snapshot kết quả qua `@Value`.

Ví dụ nên dùng khi trạng thái có thể đổi:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final FeaturePolicy featurePolicy;

    public CheckoutService(FeaturePolicy featurePolicy) {
        this.featurePolicy = featurePolicy;
    }

    public boolean canUseFeatureNow() {
        return featurePolicy.isEnabled();
    }
}
~~~

## 9. SpEL với danh sách: một số cách biểu diễn và giới hạn

SpEL có cú pháp inline list:

~~~java
@Value("#{{'dev', 'test', 'prod'}}")
private java.util.List<String> environments;
~~~

Biểu thức `{'dev', 'test', 'prod'}` là một list literal theo cú pháp SpEL, không phải cú pháp Java array initializer. Phần `#{...}` bao quanh toàn bộ biểu thức; do đó có thể nhìn thấy hai cặp ngoặc nhọn liền nhau.

Một trường hợp khác là cấu hình chứa chuỗi phân tách bằng dấu phẩy:

~~~properties
app.notification.channels=email,sms,log
~~~

Có thể minh họa:

~~~java
@Value("#{'${app.notification.channels:email,log}'.split(',')}")
private String[] channels;
~~~

Khi property có giá trị `email,sms,log`, phép `split(',')` tạo mảng gồm các phần tử tương ứng.

Tuy nhiên, cách này có nhiều giới hạn:

1. Phép tách chuỗi không tự xử lý khoảng trắng thừa theo chính sách nghiệp vụ.
2. Các giá trị chứa dấu phẩy như một phần dữ liệu cần cơ chế escaping hoặc định dạng khác.
3. Giá trị trống có thể tạo tập phần tử không như mong đợi.
4. Giá trị được chèn trực tiếp vào string literal của SpEL có thể làm sai cú pháp khi chứa dấu nháy.
5. Kiểu phức tạp như danh sách object không nên được dựng bằng một chuỗi CSV đơn giản.

Với danh sách cấu hình thật, ưu tiên YAML sequence và `@ConfigurationProperties`:

~~~yaml
app:
  notification:
    channels:
      - email
      - sms
      - log
~~~

Sau đó bind vào `List<String>`. Cách này hỗ trợ cấu trúc rõ ràng hơn, dễ validate hơn và tránh nhầm lẫn giữa parsing chuỗi với binding dữ liệu cấu hình.

## 10. SpEL với Map và dữ liệu có cấu trúc

SpEL có inline map literal:

~~~java
@Value("#{{'timeout': 5000, 'retries': 3}}")
private java.util.Map<String, Integer> options;
~~~

Ví dụ trên biểu diễn một map tĩnh trong biểu thức. Nhưng với cấu hình ứng dụng, map thường được nạp từ YAML:

~~~yaml
app:
  clients:
    catalog:
      base-url: "https://catalog.example.org"
      timeout: 5s
    inventory:
      base-url: "https://inventory.example.org"
      timeout: 8s
~~~

Không nên cố biến YAML này thành một chuỗi `@Value` dài với nhiều SpEL map literal. Thay vào đó, dùng `@ConfigurationProperties` để bind vào `Map<String, ClientConfig>`.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Map<String, ClientConfig> clients) {
    public record ClientConfig(String baseUrl, Duration timeout) {}
}
~~~

Bằng cách đó, tên `catalog` và `inventory` trở thành key của map, còn `base-url` và `timeout` thành trường của `ClientConfig`. Binder có cơ chế xử lý tên thuộc tính, danh sách, map key và chuyển kiểu riêng, phù hợp với dữ liệu cấu hình hơn việc tự viết các phép map bằng SpEL.

## 11. Truy cập an toàn khi một giá trị có thể null

SpEL hỗ trợ **safe navigation operator** `?.` để hạn chế lỗi truy cập thuộc tính/phương thức trên đối tượng null:

~~~java
@Value("#{systemProperties['user.region']?.toUpperCase() ?: 'LOCAL'}")
private String upperRegion;
~~~

Nếu `systemProperties['user.region']` không có giá trị, phần `?.toUpperCase()` trả null thay vì cố gọi method trên null; Elvis operator có thể dùng `LOCAL`.

Nhưng safe navigation **không biến mọi lỗi cấu hình thành giá trị hợp lệ**. Ví dụ:

- Chuỗi tồn tại nhưng có định dạng không đúng vẫn có thể không phù hợp để parse.
- Một object không tồn tại trong bean context có thể làm tham chiếu bean thất bại.
- Việc gọi phương thức có side effect vẫn có rủi ro riêng.
- Các thao tác tiếp theo trong biểu thức cần được xem xét độc lập về khả năng null.

Trong cấu hình, hãy ưu tiên mặc định rõ ràng và validation cụ thể hơn là tạo chuỗi toán tử null-safe rất dài.

## 12. `@Value` có hỗ trợ đọc toàn bộ cây cấu hình không?

`@Value` rất thuận tiện khi một bean cần **một hoặc vài scalar**, ví dụ:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("${app.region:local}")
private String region;
~~~

Nhưng `@Value` không phải API tốt nhất để lấy toàn bộ cây cấu hình lồng nhau. Ví dụ:

~~~yaml
app:
  upstreams:
    - name: primary
      url: "https://primary.example.org"
      retries: 2
    - name: backup
      url: "https://backup.example.org"
      retries: 1
~~~

Những tên phẳng của cấu hình này có dạng:

~~~properties
app.upstreams[0].name=primary
app.upstreams[0].url=https://primary.example.org
app.upstreams[0].retries=2
app.upstreams[1].name=backup
app.upstreams[1].url=https://backup.example.org
app.upstreams[1].retries=1
~~~

Không nên kỳ vọng một biểu thức đơn giản:

~~~java
@Value("${app.upstreams}")
private Object upstreams;
~~~

sẽ tự dựng đầy đủ `List<Upstream>`. Cách tra cứu một property đơn không giống chức năng **binding cấu trúc** của `@ConfigurationProperties`.

Với cấu hình gồm list, map, nested object và giá trị có đơn vị, hãy dùng Binder. Ngoài việc gọn hơn, nó còn tạo một hợp đồng cấu hình có kiểu mà người đọc code dễ theo dõi.

## 13. Cách thay thế có cấu trúc: `@ConfigurationProperties`

Giả sử cấu hình:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 3s
    read-timeout: 10s
    max-attempts: 4
~~~

Thay vì:

~~~java
@Value("${app.client.base-url}") private String baseUrl;
@Value("${app.client.connect-timeout:3s}") private String connectTimeout;
@Value("${app.client.read-timeout:10s}") private String readTimeout;
@Value("${app.client.max-attempts:4}") private int maxAttempts;
~~~

có thể tạo một record cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts
) {}
~~~

Bật quét:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

Sử dụng trong service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ApiClient {
    private final ClientProperties properties;

    public ApiClient(ClientProperties properties) {
        this.properties = properties;
    }

    public int totalAllowedAttempts() {
        return properties.maxAttempts();
    }
}
~~~

Lợi ích:

- **Tập trung:** tất cả cấu hình của client nằm ở một kiểu riêng.
- **Có kiểu:** `3s` và `10s` được bind thành `Duration`, tránh truyền các chuỗi không rõ đơn vị.
- **Dễ kiểm thử:** test có thể tạo record trực tiếp và kiểm tra hành vi của code dùng cấu hình.
- **Dễ validate:** có thể kết hợp với Bean Validation khi cần.
- **Thống nhất với relaxed binding:** tên `base-url` có thể map sang component Java `baseUrl`.
- **Không cần SpEL để tính logic:** phần lớn tính toán được đặt trong Java thay vì rải trong annotation.

Spring Boot Binder không đánh giá SpEL như một biểu thức ứng dụng bên trong mọi giá trị cấu hình tùy ý. Đừng lấy ví dụ `@Value("#{...}")` rồi suy ra rằng `@ConfigurationProperties` cũng tự chạy biểu thức đó trong từng string property theo cùng cách.

## 14. Default và validation khi bỏ SpEL phức tạp

Có hai nhu cầu khác nhau:

1. **Default hợp lệ:** nếu thuộc tính không có, ta muốn giá trị an toàn.
2. **Validation:** nếu thuộc tính có nhưng sai nghiệp vụ, ta muốn ứng dụng báo lỗi.

Với `@Value`:

~~~java
@Value("${app.worker-count:4}")
private int workerCount;
~~~

Nếu có `app.worker-count=-2`, default `4` không được dùng: khóa đã tồn tại. Tùy cách sử dụng, giá trị âm có thể lọt qua nếu không validation.

Với `@ConfigurationProperties` có thể sử dụng `@DefaultValue` và Bean Validation:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.Min;

@Validated
@ConfigurationProperties(prefix = "app")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int workerCount
) {}
~~~

Ví dụ yêu cầu dependency validation tương ứng, thường là `spring-boot-starter-validation`. Default `4` áp dụng ở lớp binding khi không cung cấp giá trị, còn `@Min(1)` từ chối giá trị nhỏ hơn `1` khi validation hoạt động.

SpEL vẫn có thể viết `#{T(java.lang.Math).max(1, ...)}` để nâng số lên một ngưỡng, nhưng việc âm thầm sửa một cấu hình sai khác với việc **báo lỗi sớm**. Với cấu hình bắt buộc hoặc nhạy cảm, validation rõ ràng thường phù hợp hơn.

## 15. Biến môi trường và thứ tự ưu tiên nguồn cấu hình

Giả sử `application.yml`:

~~~yaml
app:
  retry:
    max-attempts: 3
  client:
    timeout: 5s
~~~

Khi chạy:

~~~bash
export APP_RETRY_MAXATTEMPTS=6
export APP_CLIENT_TIMEOUT=12s
java -jar demo.jar
~~~

Spring Boot có thể dùng các biến môi trường để ghi đè Config Data tương ứng thông qua relaxed binding.

Nếu bean có:

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

giá trị có thể là `6`, không phải `3` trong YAML hay default `3` trong annotation.

Nếu lại chạy:

~~~bash
java -jar demo.jar --app.retry.max-attempts=9
~~~

đối số CLI thường có mức ưu tiên cao hơn biến môi trường và Config Data. Trong trường hợp không có nguồn đặc biệt nào khác, giá trị là `9`.

SpEL cũng chịu ảnh hưởng của nguồn cấu hình khi nhúng placeholder:

~~~java
@Value("#{${app.retry.max-attempts:3} * 2}")
private int doubledAttempts;
~~~

Nếu khóa cuối cùng là `9`, biểu thức tính thành `9 * 2` và kết quả là `18`.

**Cần phân biệt:** `@Value` không làm thay đổi thứ tự ưu tiên property source. Nó chỉ giải quyết giá trị theo những nguồn đã được Spring tổ chức, rồi chuyển/đánh giá kết quả tại điểm tiêm.

## 16. Giới hạn thứ nhất: không tự động cập nhật cấu hình đang chạy

Một bean được tạo khi ứng dụng khởi động, ví dụ:

~~~java
@Component
public class FixedThreshold {
    @Value("${app.threshold:10}")
    private int threshold;

    public int currentThreshold() {
        return threshold;
    }
}
~~~

Giá trị `threshold` thông thường được tiêm một lần khi bean được khởi tạo. Nếu ai đó thay đổi file `application.yml` sau khi tiến trình đã chạy, field này **không tự thay đổi**.

Tương tự, biểu thức:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureAtStartup;
~~~

không có nghĩa mỗi lần gọi getter sẽ đánh giá lại `featurePolicy.isEnabled()`. Kết quả thường đã được tính tại lúc tiêm vào bean.

Nếu hệ thống cần refresh cấu hình động, phải thiết kế cơ chế riêng như tạo lại bean có chủ đích, thay nguồn cấu hình qua nền tảng hỗ trợ refresh, hoặc đọc trạng thái động qua một service. Không nên giả định SpEL hoặc `@Value` tự tạo khả năng hot reload.

## 17. Giới hạn thứ hai: lỗi xuất hiện khi tạo bean

Có ba nhóm lỗi thường gặp:

### 17.1. Thiếu thuộc tính bắt buộc

~~~java
@Value("${payment.api-key}")
private String paymentApiKey;
~~~

Nếu không có `payment.api-key` và không có default, quá trình resolve placeholder có thể thất bại khi tạo bean. Đây có thể là hành vi mong muốn với giá trị quan trọng.

### 17.2. Sai kiểu hoặc giá trị không hợp lệ

~~~java
@Value("${app.max-connections:10}")
private int maxConnections;
~~~

Nếu môi trường cấp `APP_MAXCONNECTIONS=abc`, Spring vẫn tìm thấy khóa nhưng việc chuyển thành `int` có thể thất bại. Default không che lỗi parse.

### 17.3. Biểu thức SpEL sai cú pháp hoặc không phù hợp

~~~java
@Value("#{${app.workers:2} * 2}")
private int workerSlots;
~~~

Nếu `app.workers` là chuỗi `two`, biểu thức tính toán không còn hợp lệ theo kỳ vọng. Lỗi có thể phát sinh trong quá trình parse/evaluate SpEL, không chỉ trong bước conversion.

Những lỗi này xảy ra khi bean chứa injection point được tạo, có thể ngay lúc khởi động hoặc trễ hơn tùy phạm vi/lazy initialization. Việc biên dịch Java thành công không đảm bảo biểu thức SpEL hoặc dữ liệu cấu hình runtime hợp lệ.

## 18. Giới hạn thứ ba: bảo mật và dữ liệu không đáng tin cậy

SpEL có khả năng truy xuất bean, property, phương thức và các kiểu Java trong phạm vi evaluation context được cấp. Đó là một ngôn ngữ biểu thức **mạnh hơn nhiều so với việc đọc một khóa cấu hình**.

Nguyên tắc bảo mật:

- **Không** lấy biểu thức SpEL do người dùng bên ngoài gửi rồi đánh giá trực tiếp bằng một evaluation context quyền rộng.
- **Không** tạo biểu thức bằng cách ghép giá trị cấu hình không đáng tin cậy vào cú pháp SpEL, vì dữ liệu có thể làm hỏng hoặc thay đổi ý nghĩa biểu thức.
- Không sử dụng SpEL để che hoặc thực thi logic phân quyền quan trọng bằng những chuỗi cấu hình khó kiểm soát nếu có thể viết kiểm tra rõ trong code.
- Không đưa secret vào giá trị được in log, exception message hoặc endpoint chẩn đoán một cách tùy tiện.

Ví dụ minh họa rủi ro về ghép chuỗi:

~~~java
@Value("#{'${app.display-name:guest}'.toUpperCase()}")
private String upperDisplayName;
~~~

Nếu `app.display-name` chứa một dấu nháy đơn hoặc chuỗi có hình dạng giống một phần của biểu thức, cách nhúng text trực tiếp này có thể phá vỡ string literal của SpEL. Với dữ liệu đầu vào bên ngoài, nên:

~~~java
@Value("${app.display-name:guest}")
private String displayName;
~~~

Sau đó xử lý:

~~~java
public String normalizedDisplayName() {
    return displayName.toUpperCase(java.util.Locale.ROOT);
}
~~~

Việc này khiến giá trị cấu hình được xem là **dữ liệu**, không phải mã biểu thức.

## 19. Giới hạn thứ tư: khả năng kiểm thử và bảo trì

Giả sử một ứng dụng chứa nhiều annotation:

~~~java
@Value("#{${app.workers:4} * ${app.slots-per-worker:2}}")
private int totalSlots;

@Value("#{${app.retry.max-attempts:3} > 5 ? 20 : 10}")
private int retryBudget;

@Value("#{'${app.region:local}'.toUpperCase()}")
private String region;
~~~

Các biểu thức vẫn có thể đọc được khi còn đơn giản, nhưng khi dự án lớn dần:

- Tên thuộc tính lặp lại ở nhiều class, dễ đổi sót.
- Default bị phân tán thay vì được mô tả tập trung.
- Validation và giới hạn giá trị không rõ ràng.
- Cần tạo Spring context mới dễ kiểm tra chính xác kết quả của injection point.
- Sự phụ thuộc giữa các thuộc tính nằm ẩn trong chuỗi annotation.
- Một thay đổi cấu hình có thể làm sai SpEL tại runtime, không bị trình biên dịch Java phát hiện.

Một thiết kế rõ ràng hơn:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record CapacityProperties(int workers, int slotsPerWorker) {
    public int totalSlots() {
        return workers * slotsPerWorker;
    }
}
~~~

Tất nhiên cần cấp default hoặc validation phù hợp theo hợp đồng cấu hình. Nhưng phép nhân đã trở thành **code Java bình thường**, có thể kiểm thử bằng unit test:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CapacityPropertiesTest {
    @Test
    void computesTotalSlots() {
        CapacityProperties props = new CapacityProperties(4, 2);
        assertEquals(8, props.totalSlots());
    }
}
~~~

SpEL vẫn hữu ích cho biểu thức ngắn, mang tính trình bày hoặc tích hợp framework; không nên lạm dụng như một ngôn ngữ nghiệp vụ thứ hai.

## 20. Giới hạn thứ năm: hoạt động trong và ngoài Spring container

`@Value` không phải một annotation mà JVM tự xử lý. Nó cần cơ chế của Spring container, thông thường các BeanPostProcessor/BeanFactory phù hợp, để resolve và tiêm giá trị.

Ví dụ:

~~~java
@Component
public class AppInfo {
    @Value("${app.name:demo}")
    private String name;

    public String name() {
        return name;
    }
}
~~~

Nếu tạo đối tượng trực tiếp bằng `new AppInfo()` ở ngoài Spring container, trường `name` **không tự được tiêm** bởi `@Value`. Trong unit test thuần Java, nếu tự tạo một đối tượng như vậy mà không có DI, bạn sẽ không nhận kết quả như khi Spring khởi tạo bean.

Với thiết kế constructor injection:

~~~java
public class AppInfo {
    private final String name;

    public AppInfo(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

việc test trở nên đơn giản hơn. Nếu cần Spring giải quyết placeholder, có thể đưa `@Value` vào constructor parameter của một bean được quản lý:

~~~java
@Component
public class ManagedAppInfo {
    private final String name;

    public ManagedAppInfo(@Value("${app.name:demo}") String name) {
        this.name = name;
    }
}
~~~

Chọn cách phù hợp với mục tiêu: với các lớp có nhiều phụ thuộc và cấu hình, constructor injection thường giúp mô tả rõ nhu cầu của bean hơn field injection.

## 21. SpEL khác với việc đọc cấu hình qua `Environment`

Đối với nhu cầu lấy một thuộc tính mà không cần SpEL, có thể dùng Spring `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionReader {
    private final Environment environment;

    public RegionReader(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "local");
    }

    public int retryCount() {
        return environment.getProperty("app.retry.max-attempts", Integer.class, 3);
    }
}
~~~

Ưu điểm:

- Tên thuộc tính và default là các tham số rõ ràng.
- Có thể dùng kết quả trong Java để xử lý logic phức tạp.
- Có thể gọi khi cần nếu thiết kế muốn đọc từ `Environment` tại thời điểm thực thi.

Nhưng `Environment#getProperty` không phải là Binder cấu trúc đầy đủ cho list/map/object lồng nhau. Ngoài ra, việc gọi lại `Environment` không tự đồng nghĩa với các file Config Data được nạp lại trên đĩa. Đối với hệ thống có cập nhật cấu hình động, phải có nguồn và cơ chế refresh tương ứng.

Bảng so sánh:

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Một scalar với default | `@Value("${key:default}")` |
| Một phép tính/điều kiện ngắn tại điểm tiêm | `@Value("#{...}")` |
| Nhiều khóa có cấu trúc, list/map, validation | `@ConfigurationProperties` |
| Tra cứu một khóa trong Java lúc thực thi | `Environment#getProperty(...)` |
| Logic nghiệp vụ, tính toán phức tạp, test độc lập | Phương thức hoặc service Java |
| Đọc dữ liệu thay đổi sau khi ứng dụng chạy | Cơ chế nguồn cấu hình/refresh hoặc service được thiết kế riêng |

## 22. Các lỗi nhầm lẫn thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `${2+3}` không ra `5` | Nhầm placeholder với SpEL | Dùng `#{2+3}` |
| `@Value` báo thiếu key | Placeholder không có default và không tìm thấy thuộc tính | Cấp cấu hình hoặc default hợp lệ |
| Biểu thức SpEL lỗi khi biến chứa chuỗi có dấu nháy | Chèn giá trị vào string literal SpEL | Tiêm chuỗi riêng rồi xử lý bằng Java |
| Giá trị field không thay đổi sau khi sửa YAML | Field được inject khi bean tạo, không auto-refresh | Khởi động lại hoặc thiết kế refresh |
| `systemProperties['x']` không thấy giá trị trong `application.yml` | Đang đọc JVM system properties, không phải toàn bộ `Environment` | Dùng `${x}` hoặc `Environment` |
| SpEL trong chuỗi cấu hình không được xử lý như mong muốn bởi Binder | `@ConfigurationProperties` không dùng chung toàn bộ semantics SpEL của `@Value` | Bind dữ liệu thuần, chuyển logic sang Java |
| `@Value` muốn lấy cả list object nhưng chỉ nhận chuỗi | Property placeholder không phải binder cấu trúc | Dùng `@ConfigurationProperties` |
| Có default nhưng vẫn lỗi parse | Khóa tồn tại với giá trị sai kiểu | Validation và sửa cấu hình |
| `@Value` trên đối tượng tạo bằng `new` không chạy | Đối tượng không được Spring quản lý | Dùng Spring DI hoặc truyền tham số rõ |
| Dữ liệu nhạy cảm xuất hiện trong log | In trực tiếp giá trị cấu hình hoặc biểu thức | Ẩn/redact, không log secret |

## 23. Bài tập thực hành

### Bài 1 — Phân biệt cú pháp

Ba annotation:

~~~java
@Value("${app.count:4}")
private int a;

@Value("#{2 * 3}")
private int b;

@Value("#{${app.count:4} * 3}")
private int c;
~~~

Giả sử `app.count=5`, không có nguồn ưu tiên cao hơn. Hãy tính `a`, `b`, `c`.

**Đáp án:** `a=5`, `b=6`, `c=15`. Placeholder được dùng để lấy `5`, còn SpEL đánh giá phép nhân.

### Bài 2 — Giá trị sai kiểu

Cấu hình:

~~~yaml
app:
  count: invalid
~~~

Bean:

~~~java
@Value("#{${app.count:4} * 3}")
private int total;
~~~

Hỏi: `total` có mặc định là `12` không?

**Đáp án:** không. Khóa `app.count` tồn tại nên default `4` không được dùng. Biểu thức có thể thất bại khi đánh giá vì chuỗi `invalid` không phải số.

### Bài 3 — SpEL có tự cập nhật không?

Một bean có:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureEnabled;
~~~

Sau khi tạo bean, `featurePolicy` đổi trạng thái. `featureEnabled` có tự đổi theo không?

**Đáp án:** thông thường không. Đó là giá trị snapshot được tiêm khi bean được tạo. Để lấy trạng thái mới, inject bean `featurePolicy` và gọi `isEnabled()` lúc sử dụng.

### Bài 4 — Chọn API đọc cấu hình

Cho YAML:

~~~yaml
app:
  clients:
    - name: primary
      timeout: 3s
    - name: backup
      timeout: 7s
~~~

Hãy chọn giữa `@Value`, SpEL và `@ConfigurationProperties` nếu muốn nhận một `List<Client>`.

**Đáp án:** `@ConfigurationProperties` là lựa chọn phù hợp để bind danh sách object có kiểu; không nên nhồi toàn bộ cấu trúc vào một biểu thức SpEL.

### Bài 5 — Elvis và placeholder default

So sánh:

~~~java
@Value("${app.region:local}")
private String regionA;

@Value("#{systemProperties['app.region'] ?: 'local'}")
private String regionB;
~~~

Nếu `app.region=asia` chỉ được khai báo trong `application.yml`, hai giá trị có chắc giống nhau không?

**Đáp án:** không chắc. `regionA` sử dụng tra cứu property source của Spring, còn `regionB` trong ví dụ chỉ đọc Java system properties qua map `systemProperties`. Cùng tên khóa không có nghĩa cùng phạm vi nguồn.

### Bài 6 — Chuyển một biểu thức sang Java

Đang có:

~~~java
@Value("#{${app.workers:2} * ${app.slots:4}}")
private int totalSlots;
~~~

Nếu cần kiểm soát `workers >= 1` và `slots >= 1`, nên tổ chức thế nào?

**Đáp án gợi ý:** bind hai thuộc tính vào một class/record `@ConfigurationProperties` có validation, sau đó tính `workers * slots` trong một phương thức Java được unit test. Như vậy validation và tính toán có trách nhiệm riêng, tránh che giá trị sai bằng phép toán ở annotation.

## 24. Ghi nhớ

- **`${...}`** lấy giá trị cấu hình; **`#{...}`** đánh giá biểu thức SpEL.
- Có thể kết hợp, ví dụ `#{${app.count:2} * 2}`, nhưng phép đánh giá cần giá trị hợp lệ và có thể lỗi ở runtime.
- `@Value` tốt cho **một vài thuộc tính đơn giản hoặc biểu thức ngắn**; không phải lựa chọn mặc định cho mọi cấu trúc cấu hình.
- SpEL hỗ trợ phép toán, điều kiện, static method, bean references và safe navigation; quyền năng này cũng đòi hỏi kiểm soát dữ liệu đầu vào và bảo mật.
- **Không nhúng chuỗi không đáng tin cậy trực tiếp vào cú pháp SpEL.** Tiêm dữ liệu thuần và xử lý bằng Java nếu cần.
- Giá trị `@Value` thông thường được tính **khi bean được tạo**, không tự cập nhật khi file cấu hình hoặc trạng thái bean khác thay đổi.
- `systemProperties` trong SpEL là một nguồn dữ liệu cụ thể, **không đồng nghĩa** tra cứu mọi property source của Spring Boot.
- `@ConfigurationProperties` phù hợp cho nested properties, danh sách, map, conversion, default có kiểu và validation.
- Default của placeholder không sửa một giá trị sai kiểu hoặc sai nghiệp vụ; lỗi cấu hình quan trọng nên được phát hiện sớm.

## Tài liệu tham khảo

- [Spring Framework — Expressions (SpEL)](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Annotation-based Container Configuration: Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
