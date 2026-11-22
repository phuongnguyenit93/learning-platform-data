# So sánh JavaBean, lớp bất biến và record qua cùng một mô hình `@ConfigurationProperties`

## 1. Mục tiêu và bối cảnh

Spring Boot hỗ trợ **externalized configuration**: một phiên bản ứng dụng có thể nhận cấu hình từ YAML, Properties, environment variables, Java system properties và đối số dòng lệnh. Thay vì rải nhiều `@Value` khắp mã Java, ta thường gom những thuộc tính liên quan thành một đối tượng có kiểu và dùng `@ConfigurationProperties` để bind.

Khi thiết kế đối tượng cấu hình, có ba hình thức Java đáng cân nhắc:

1. **JavaBean mutable:** có constructor không tham số, getter và setter; binder tạo object rồi gán từng property.
2. **Lớp bất biến (immutable class):** có field `final` và constructor nhận giá trị; binder tạo object bằng constructor binding.
3. **Java record:** biểu diễn dữ liệu ngắn gọn bằng các record components; constructor binding thường được suy ra từ canonical constructor.

Ba cách trên có thể đại diện **cùng một mô hình cấu hình**. Chúng khác nhau ở phương thức tạo đối tượng, API Java, giá trị mặc định, khả năng thay đổi và nhu cầu thiết kế.

Bài này dùng cùng nhóm property `app.delivery` để đối chiếu từng bước; không tạo ba bộ property với ý nghĩa khác nhau rồi so sánh kết quả không tương đương.

> Phạm vi ví dụ: Java 17+ và Spring Boot 3.x. Trong Spring Boot 2.x có những khác biệt ở cách khai báo `@ConstructorBinding` và namespace validation, được nêu ở phần lưu ý phiên bản.

## 2. Một mô hình cấu hình chung cho cả ba cách

Giả sử một dịch vụ gửi dữ liệu đến một hệ thống đối tác. Nó cần bốn thuộc tính:

| Thuộc tính cấu hình | Kiểu Java | Vai trò |
| --- | --- | --- |
| `app.delivery.endpoint` | `String` | Địa chỉ đích gửi yêu cầu |
| `app.delivery.connect-timeout` | `Duration` | Thời gian chờ kết nối |
| `app.delivery.max-retries` | `int` | Số lần thử lại tối đa |
| `app.delivery.enabled` | `boolean` | Có bật chức năng gửi hay không |

Một file `src/main/resources/application.yml`:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
~~~

Tương đương trong `application.properties`:

~~~properties
app.delivery.endpoint=https://api.example.test
app.delivery.connect-timeout=5s
app.delivery.max-retries=3
app.delivery.enabled=true
~~~

Giá trị mong muốn sau binding:

~~~text
endpoint       = "https://api.example.test"   (String)
connectTimeout = Duration.ofSeconds(5)        (Duration)
maxRetries     = 3                            (int)
enabled        = true                         (boolean)
~~~

Spring Boot dùng **relaxed binding**: `connect-timeout` từ file có thể ánh xạ sang `connectTimeout` của Java; `max-retries` sang `maxRetries`. `5s` được chuyển từ văn bản sang `Duration`.

Để các phép so sánh không bị nhiễu, từng đoạn mã dưới đây là **một phương án thay thế** cho cùng cấu hình, không phải yêu cầu đăng ký cả ba properties bean đồng thời. Nếu đưa cả ba class vào cùng một `@ConfigurationPropertiesScan`, bạn sẽ tạo ba bean cùng đọc `app.delivery`, khiến ví dụ lựa chọn một phong cách không còn rõ ràng.

## 3. Cách 1 — JavaBean mutable

### 3.1. Khai báo class

JavaBean thường dùng constructor không tham số và các phương thức `getXxx`/`setXxx` (hoặc `isXxx` cho boolean).

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryJavaBeanProperties {

    @NotBlank
    private String endpoint;

    @NotNull
    private Duration connectTimeout;

    @Min(0)
    private int maxRetries;

    private boolean enabled;

    public DeliveryJavaBeanProperties() {
        // Constructor không tham số để tạo JavaBean.
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Với YAML ở mục 2, sau khi Spring Boot bind, bean này có các giá trị `endpoint=https://api.example.test`, `connectTimeout=PT5S`, `maxRetries=3`, `enabled=true`.

### 3.2. Cơ chế binder

~~~text
Spring thấy @ConfigurationProperties("app.delivery")
                |
                v
     new DeliveryJavaBeanProperties()
                |
                v
       setEndpoint("https://...")
       setConnectTimeout(5 giây)
       setMaxRetries(3)
       setEnabled(true)
                |
                v
       properties bean được dùng
~~~

Điểm cốt lõi: binder cần cách **ghi** giá trị vào những property tương ứng. Với JavaBean điển hình, đó là setter. Class có thể có logic trong setter nhưng nên tránh tác dụng phụ: property configuration object tốt nhất chỉ làm nhiệm vụ giữ cấu hình.

### 3.3. Giá trị mặc định trong JavaBean

Có thể khai báo mặc định ngay khi tạo object:

~~~java
private Duration connectTimeout = Duration.ofSeconds(5);
private int maxRetries = 2;
private boolean enabled = false;
~~~

Nếu cấu hình ngoài **không khai báo** `max-retries`, field có thể giữ giá trị `2`. Nếu có `max-retries: 3`, binder có thể ghi đè bằng `3`.

Đây là **giá trị mặc định nằm trong object**, không tự biến thành một entry `app.delivery.max-retries=2` trong `Environment`. Mã gọi `environment.getProperty("app.delivery.max-retries")` có thể vẫn nhận `null` nếu không có nguồn thực sự khai báo key đó.

### 3.4. Ưu điểm và giới hạn

**Ưu điểm:** quen thuộc với nhiều dự án Java/Spring, setter binding rõ ràng, dễ dùng với đối tượng từ thư viện thứ ba có JavaBean API, có thể khởi tạo collection/nested object trước khi bind.

**Giới hạn:** nhiều mã getter/setter; đối tượng có thể bị sửa sau khi khởi tạo do API setter là public; một bean tiêu thụ cấu hình nếu lỡ gọi `setMaxRetries(...)` sẽ làm thay đổi trạng thái và gây khó theo dõi. Nếu cấu hình là sự thật cố định theo một lần khởi động, việc cho phép sửa trạng thái thường không phải điều mong muốn.

## 4. Cách 2 — Lớp bất biến với constructor binding

### 4.1. Khai báo cùng các field

Với lớp bất biến, không có setter, mọi field được cấp qua constructor. Đây là ví dụ viết đầy đủ:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryImmutableProperties {

    @NotBlank
    private final String endpoint;

    @NotNull
    private final Duration connectTimeout;

    @Min(0)
    private final int maxRetries;

    private final boolean enabled;

    public DeliveryImmutableProperties(
            String endpoint,
            Duration connectTimeout,
            int maxRetries,
            boolean enabled) {
        this.endpoint = endpoint;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

Trong Spring Boot 3.x, một `@ConfigurationProperties` class có **một constructor có tham số** thường được tự động nhận diện cho constructor binding; không bắt buộc thêm `@ConstructorBinding` trong tình huống này.

### 4.2. Cơ chế binder

~~~text
Spring thấy @ConfigurationProperties("app.delivery")
                   |
                   v
       tra cứu các giá trị có hiệu lực
                   |
                   v
     chuyển endpoint        → String
     chuyển connect-timeout → Duration
     chuyển max-retries     → int
     chuyển enabled         → boolean
                   |
                   v
new DeliveryImmutableProperties(endpoint, timeout, retries, enabled)
                   |
                   v
     object đã được khởi tạo đầy đủ
~~~

Binder **không tạo object rỗng rồi lần lượt gọi setter**. Nó chuẩn bị các tham số và gọi constructor. Sau khi tạo xong, không có API `setEndpoint` để thay đổi các field.

Chú ý rằng `final` và việc không có setter tạo ra **bất biến ở cấp trường tham chiếu**, không tự bảo đảm deep immutability nếu field trỏ tới một `List` hoặc một đối tượng mutable. Với ví dụ chỉ dùng `String`, `Duration` và primitive, trạng thái tương đối đơn giản.

### 4.3. Điều kiện đăng ký để constructor binding hoạt động

Đối tượng constructor-bound cần được đăng ký thông qua cơ chế cấu hình properties của Spring Boot, ví dụ:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryImmutableProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

Hoặc dùng `@ConfigurationPropertiesScan` để quét những class có `@ConfigurationProperties`.

Không nên sử dụng cùng một object constructor-bound như một bean thông thường được tạo bằng `@Component`, `@Bean` method hoặc `@Import` rồi kỳ vọng binder truyền các giá trị vào constructor: đó là **cơ chế tạo bean khác**. Nếu cần object vendor được tạo qua `@Bean`, có thể bind class properties riêng rồi truyền nó vào factory method.

### 4.4. Constructor có nhiều lựa chọn

Nếu một class có **nhiều constructor**, Spring Boot cần biết constructor nào được dùng cho constructor binding. Trong Spring Boot 3.x, `@ConstructorBinding` có thể đặt trên constructor được chọn:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.sample")
public class SampleProperties {
    private final String name;

    public SampleProperties() {
        this.name = "fallback";
    }

    @ConstructorBinding
    public SampleProperties(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Ví dụ này minh họa **vị trí annotation trên constructor** trong Spring Boot 3.x. Không nên sao chép trực tiếp hướng dẫn Spring Boot 2.x đặt `@ConstructorBinding` trên class mà không kiểm tra package và API theo phiên bản đang sử dụng.

### 4.5. Lưu ý biên dịch tham số

Constructor binding cần tên tham số constructor để ánh xạ vào property names. Với Java class thông thường, quá trình build phải giữ tên tham số, thường qua compiler option `-parameters`. Spring Boot Maven parent hoặc plugin Gradle của Spring Boot có thể cấu hình việc này cho project theo cách tiêu chuẩn.

Một lỗi khó tìm khi tự cấu hình build là bytecode không còn metadata tên tham số, khiến constructor binder không xác định được `endpoint` hay `maxRetries` tương ứng với key nào. Nếu lỗi xảy ra dù YAML và constructor nhìn có vẻ đúng, kiểm tra cấu hình Java compiler và build plugin.

## 5. Cách 3 — Record với constructor binding

Java record giúp biểu diễn nhóm dữ liệu có các thành phần cố định mà không phải tự viết getter và constructor theo mẫu.

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        @NotBlank String endpoint,
        @NotNull Duration connectTimeout,
        @Min(0) int maxRetries,
        boolean enabled) {
}
~~~

Chỉ với vài dòng, Java compiler tạo những thành phần cơ bản của record:

- Canonical constructor nhận bốn components.
- Các accessor `endpoint()`, `connectTimeout()`, `maxRetries()` và `enabled()`.
- `equals(...)`, `hashCode()` và `toString()` dựa trên record components.

Spring Boot 3.x hỗ trợ constructor binding đối với record. Khi record có một canonical constructor thông thường, **không cần đặt `@ConstructorBinding`**.

Đăng ký:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryRecordProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

Hoặc cho phép `@ConfigurationPropertiesScan` phát hiện record.

### 5.1. Cách truy cập trong mã Java khác với JavaBean

Với JavaBean hoặc immutable class đã khai báo getter ở trên:

~~~java
String endpoint = props.getEndpoint();
int retries = props.getMaxRetries();
~~~

Với record:

~~~java
String endpoint = props.endpoint();
int retries = props.maxRetries();
~~~

**Không** dùng `props.getEndpoint()` với record trên, vì record tự sinh `endpoint()` thay vì JavaBean getter.

### 5.2. Record không đồng nghĩa dữ liệu bí mật được bảo vệ

`toString()` của record có thể hiển thị giá trị của các components. Nếu record chứa `apiKey`, `password` hay token, ghi log trực tiếp object có thể làm lộ secret.

Không làm:

~~~java
// Không log toàn bộ record nếu nó có dữ liệu nhạy cảm.
// log.info("Delivery config: {}", properties);
~~~

Nên log những thông tin được chọn và đã che, hoặc không log cấu hình nhạy cảm. Record có `final` references nhưng không tự mã hóa secrets hay che chúng khỏi `toString()`.

## 6. Ba cách dùng cùng một file sẽ cho giá trị nào?

Với file chung:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
~~~

Cả ba mẫu properties (khi **được đăng ký đúng cơ chế tương ứng**) biểu diễn cùng cấu hình:

| Giá trị hiệu lực | JavaBean | Immutable class | Record |
| --- | --- | --- | --- |
| Endpoint | `getEndpoint()` → URL ví dụ | `getEndpoint()` → URL ví dụ | `endpoint()` → URL ví dụ |
| Timeout | `getConnectTimeout()` → `PT5S` | `getConnectTimeout()` → `PT5S` | `connectTimeout()` → `PT5S` |
| Max retries | `getMaxRetries()` → `3` | `getMaxRetries()` → `3` | `maxRetries()` → `3` |
| Enabled | `isEnabled()` → `true` | `isEnabled()` → `true` | `enabled()` → `true` |

**Kết quả cấu hình giống nhau không có nghĩa cách tạo object giống nhau.** JavaBean lấy một instance rồi gán property. Constructor binding của class bất biến hoặc record đưa các giá trị đã chuyển đổi vào constructor.

Ví dụ ứng dụng được khởi động với:

~~~bash
java -jar app.jar --app.delivery.connect-timeout=9s
~~~

Nếu Spring Boot đang cho phép command-line properties và không có nguồn nào khác ưu tiên cao hơn, **cả ba** cách đều có thể nhận timeout `9s`. Cơ chế `@ConfigurationProperties` không đổi thứ tự ưu tiên nguồn theo kiểu class.

## 7. Cách đăng ký: chọn một kiểu cho mỗi thử nghiệm

### 7.1. `@EnableConfigurationProperties` — lựa chọn tường minh

Để chạy thử JavaBean:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryJavaBeanProperties.class)
public class DeliveryPropertiesConfiguration {
}
~~~

Để thử lớp bất biến, thay duy nhất loại class trong annotation:

~~~java
@EnableConfigurationProperties(DeliveryImmutableProperties.class)
~~~

Để thử record:

~~~java
@EnableConfigurationProperties(DeliveryRecordProperties.class)
~~~

Đặt một trong các cấu hình trên trong package được `@SpringBootApplication` scan hoặc đăng ký vào context bằng cách phù hợp. Đừng để ba class được đăng ký đồng thời nếu mục đích là kiểm chứng **một kiểu đại diện duy nhất**.

### 7.2. `@ConfigurationPropertiesScan` — lựa chọn qua quét package

~~~java
package com.example;

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
~~~

Annotation scan tìm những class có `@ConfigurationProperties` trong phạm vi package thích hợp. Vì vậy, khi dùng cách này với project thật, chỉ giữ class properties có chủ đích trong phạm vi quét hoặc thiết kế package scan rõ ràng.

Nếu đặt tất cả ba class demo ở cùng package và bật scan chung, cả ba có thể được đăng ký; đó là **ba bean riêng cùng prefix**, không phải một bean được thay đổi hình thức từ JavaBean thành record.

### 7.3. Không nhầm `@Component` với constructor-bound properties

JavaBean mutable có thể tồn tại như một Spring component thông thường và được bind theo JavaBean semantics khi được cấu hình phù hợp. Nhưng constructor binding cho immutable class/record **không** dùng cơ chế tạo bean thông thường như `@Component`.

Để tránh nhầm, khi làm việc với `@ConfigurationProperties` chuyên dụng, ưu tiên `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`; chỉ dùng `@Component` cho loại bean thực sự được Spring quản lý bằng injection và lifecycle thông thường.

### 7.4. Trường hợp `@Bean` của thư viện ngoài

Nếu bạn không sở hữu class của thư viện:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.pool")
VendorPoolConfig vendorPoolConfig() {
    return new VendorPoolConfig();
}
~~~

Spring gọi factory method để có object rồi bind các property có thể ghi vào object đó; đây là **JavaBean binding**, không phải cách Spring Boot truyền values vào một constructor bất biến. Nếu thư viện chỉ hỗ trợ constructor/builder, bind một class properties của ứng dụng rồi xây dựng vendor object trong `@Bean`.

## 8. JavaBean, lớp bất biến và record khác nhau ở điểm nào?

| Tiêu chí | JavaBean mutable | Immutable class | Java record |
| --- | --- | --- | --- |
| Cách binder thiết lập giá trị | Gọi setter sau khi tạo instance | Truyền vào constructor | Truyền vào canonical constructor |
| Constructor thường dùng | Không tham số | Constructor có tham số | Canonical constructor do Java tạo |
| Có setter công khai | Có | Không | Không |
| Field `final` | Không bắt buộc | Thường có | Record component backing fields là final |
| Boilerplate | Nhiều getter/setter | Constructor + getter + `final` | Ngắn gọn |
| API truy cập | `getXxx()`, `isXxx()` | Getter do lập trình viên viết | `xxx()` |
| Cách đăng ký chuẩn cho constructor binding | Không yêu cầu | Scan hoặc EnableConfigurationProperties | Scan hoặc EnableConfigurationProperties |
| Chứa default bằng field initializer | Dễ | Không thay thế constructor args tự động | Không có instance field initializer kiểu JavaBean |
| Default cho constructor args | Không phải cơ chế chính | `@DefaultValue` trên parameter | `@DefaultValue` trên record component |
| Thêm logic trong quá trình tạo | Constructor/setter có thể có | Constructor có thể có | Compact/canonical constructor có thể có |
| `equals`/`hashCode`/`toString` tự sinh | Không | Không | Có |
| Khả năng sửa cấu hình sau khi tạo | Có thể qua setter | Không qua setter | Không qua setter |
| Sử dụng tốt nhất | Class tương thích JavaBean/framework cũ | Cần kiểm soát API/constructor phức tạp | DTO cấu hình ngắn gọn, dữ liệu cố định |

“Immutable” trong bảng nói về API không có setter và những field không thể gán lại. Nếu class hoặc record chứa một `List` mutable, người dùng vẫn có thể sửa nội dung list qua reference nếu không copy phòng vệ.

## 9. Giá trị mặc định: cùng ý nghĩa nhưng cách biểu diễn khác

Giả sử ta bỏ hai key khỏi YAML:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
~~~

Ta mong `maxRetries=2` và `enabled=false` khi không có override.

### 9.1. JavaBean — field initializer

~~~java
private int maxRetries = 2;
private boolean enabled = false;
~~~

Nếu property không được cung cấp, object đã có default từ lúc tạo. Binder có thể giữ giá trị đó.

### 9.2. Immutable class — `@DefaultValue` trên constructor parameter

Trong Spring Boot 3.x có thể sử dụng `org.springframework.boot.context.properties.bind.DefaultValue`:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

// Các field/getter và annotation @ConfigurationProperties giống mẫu ở trên.
public DeliveryImmutableProperties(
        String endpoint,
        Duration connectTimeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled) {
    this.endpoint = endpoint;
    this.connectTimeout = connectTimeout;
    this.maxRetries = maxRetries;
    this.enabled = enabled;
}
~~~

Annotation `@DefaultValue("2")` cho biết giá trị dùng khi tham số tương ứng không có property. Chuỗi trong annotation được chuyển đổi sang kiểu `int`; tương tự với `boolean`.

### 9.3. Record — `@DefaultValue` trên record component

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled) {
}
~~~

Ở đây `@DefaultValue` là metadata của binding; nó không thay đổi cú pháp YAML và không làm key tự xuất hiện trong `Environment`.

### 9.4. Primitive bị thiếu không đồng nghĩa cấu hình đúng

Nếu không có `@DefaultValue` và một tham số constructor kiểu primitive `int` không có property, giá trị không được cung cấp có thể dẫn tới mặc định kiểu primitive (`0`); đối với `boolean` là `false`. Nhưng `0` không phải lúc nào cũng hợp lệ trong nghiệp vụ.

Nếu muốn **phân biệt thiếu key với người dùng chủ động đặt 0**, hãy cân nhắc dùng wrapper `Integer` kết hợp `@NotNull`, hoặc một quy tắc validation/constructor phù hợp.

Không nên chỉ dùng primitive `int` rồi kỳ vọng `@Min(0)` phát hiện trường hợp key không được cung cấp: giá trị `0` vẫn thỏa điều kiện `>= 0`.

## 10. Validation: áp dụng giống nhau nhưng cần chú ý điểm đặt annotation

Ba mô hình đều có thể tham gia kiểm tra cấu hình bằng Bean Validation, nếu thêm `@Validated` và các constraint tương ứng, đồng thời project có một Jakarta Bean Validation implementation.

Với Spring Boot 3.x, thường có dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Các constraint ví dụ:

- `@NotBlank` cho `endpoint`: không chấp nhận null, rỗng hoặc chỉ chứa whitespace.
- `@NotNull` cho `connectTimeout`: cần có giá trị.
- `@Min(0)` cho `maxRetries`: giá trị không được nhỏ hơn 0.

Vị trí ví dụ:

| Kiểu | Vị trí constraint |
| --- | --- |
| JavaBean | Field hoặc accessor theo cách validation hỗ trợ |
| Immutable class | Field `final` hoặc vị trí thích hợp để Bean Validation đọc |
| Record | Annotation trên record components, như `@NotBlank String endpoint` |

Với bean có nested configuration object, có thể cần `@Valid` trên field/component chứa object con để validation đi vào các trường bên trong.

**Lưu ý về semantic:** `@NotBlank` chỉ kiểm tra chuỗi không rỗng/blank; nó không kiểm tra URL là HTTPS, host hợp lệ hoặc chính sách endpoint. Với yêu cầu đặc thù, tạo constraint riêng hoặc validate thêm ở lớp phù hợp.

### 10.1. Không đặt logic dựa vào secret trong `toString()`

Record tự sinh `toString()`. Immutable class và JavaBean cũng thường được IDE hoặc Lombok sinh `toString()`. Nếu object chứa password/token, không log toàn bộ object vì có thể làm lộ giá trị qua logs hoặc traces.

Validation exception nên nêu **tên trường và loại vi phạm**, không in giá trị secret.

## 11. Nested configuration: cùng một cấu trúc phân cấp

Giả sử file cấu hình mở rộng:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 5s
    max-retries: 3
    enabled: true
    security:
      username: delivery-bot
      mode: bearer
~~~

Ba kiểu properties đều có thể chứa một nhóm con `security`, nhưng cách bind khác nhau.

### 11.1. JavaBean: nested JavaBean được khởi tạo trước

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryJavaBeanProperties {
    private final Security security = new Security();

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private String username;
        private String mode;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public String getMode() { return mode; }
        public void setMode(String mode) {
            this.mode = mode;
        }
    }
}
~~~

Đoạn này chỉ minh họa **phần security** được thêm vào class JavaBean ở mục 3, không thay thế bốn field còn lại. Với nested object được khởi tạo sẵn và có setter cho các field con, binder có thể cập nhật dữ liệu trong object đó.

### 11.2. Immutable class: nested constructor

~~~java
public final class Security {
    private final String username;
    private final String mode;

    public Security(String username, String mode) {
        this.username = username;
        this.mode = mode;
    }

    public String getUsername() { return username; }
    public String getMode() { return mode; }
}
~~~

Class properties chính thêm field `private final Security security;`, constructor thêm tham số `Security security`, getter trả về nó. Nếu nested class dùng constructor binding và được Spring Boot xem là đối tượng lồng nhau, binder có thể tạo `Security` từ `security.username` và `security.mode`.

### 11.3. Record: nested record

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled,
        Security security) {

    public record Security(String username, String mode) {
    }
}
~~~

Mẫu record cho cấu trúc lồng nhau thường gọn hơn. Nếu toàn bộ nhóm `security` không tồn tại trong config data, tham số `security` có thể là `null`, tùy cách khai báo default. Khi muốn luôn có một nested instance mặc định, Spring Boot hỗ trợ `@DefaultValue` không tham số ở vị trí thích hợp, nhưng các field bên trong cũng cần có default hoặc cho phép null theo yêu cầu.

### 11.4. Khi binding collection

Tương tự, `List<String>` và `Map<String,String>` có thể xuất hiện trong cả ba mô hình. Tuy nhiên:

- Với JavaBean, pre-initialized mutable collections có thể được binder xử lý mà không phải lúc nào cũng cần setter cho chính collection.
- Với class bất biến và record, collection được cấp qua constructor; **final reference không bảo đảm collection bất biến**. Khi cần an toàn, cân nhắc tạo bản sao bất biến trong constructor/compact constructor.
- Khi các nguồn config data ghi đè cùng một `List`, binding thường chọn danh sách từ nguồn ưu tiên cao hơn thay vì tự ghép nhiều list. `Map` có thể tổng hợp các entry theo quy tắc binding riêng.

Không chọn JavaBean hay record chỉ vì nghĩ rằng kiểu Java sẽ tự quyết định thứ tự ưu tiên giữa YAML, environment và CLI. Nguồn property và quy tắc collection binding là những lớp trách nhiệm khác.

## 12. Constructor/compact constructor có nên thực hiện validation?

Với immutable class, bạn có thể nêu bất biến nội tại ngay trong constructor:

~~~java
public DeliveryImmutableProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {

    if (maxRetries < 0) {
        throw new IllegalArgumentException("maxRetries must be >= 0");
    }

    this.endpoint = endpoint;
    this.connectTimeout = connectTimeout;
    this.maxRetries = maxRetries;
    this.enabled = enabled;
}
~~~

Đây là một dạng validation bằng Java, khác với Bean Validation. Nó có thể chặn việc tạo object không hợp lệ ngay cả khi object được tạo thủ công ngoài Spring.

Record có **compact constructor**:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryRecordProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {

    public DeliveryRecordProperties {
        if (maxRetries < 0) {
            throw new IllegalArgumentException(
                    "maxRetries must be non-negative");
        }
    }
}
~~~

Khi compact constructor kết thúc, Java gán các tham số component vào các field record theo quy tắc của ngôn ngữ, trừ các trường hợp mã không hợp lệ.

Có thể sử dụng constructor/compact constructor để bảo vệ invariant đơn giản, nhưng nên tránh:

- Truy cập database hoặc gọi mạng khi bind config.
- Dùng Spring beans khác trong constructor properties.
- Đưa secret vào exception message.
- Làm logic phức tạp khiến lỗi khởi động khó hiểu.

Với dự án cần thông báo validation nhất quán, `@Validated` và Jakarta Bean Validation thường là lựa chọn tốt; constructor validation có thể bổ sung nếu invariant cần được áp dụng trong mọi ngữ cảnh tạo object.

## 13. Ưu tiên nguồn cấu hình là như nhau với ba mô hình

Giả sử `application.yml`:

~~~yaml
app:
  delivery:
    endpoint: https://sandbox.example.test
    connect-timeout: 5s
    max-retries: 2
    enabled: false
~~~

Khi deploy, môi trường cung cấp:

~~~bash
APP_DELIVERY_ENDPOINT=https://api.example.test \
APP_DELIVERY_CONNECTTIMEOUT=10s \
java -jar demo.jar --app.delivery.max-retries=4
~~~

Trong Spring Boot thông thường, với những nguồn được bật và không có nguồn ưu tiên cao hơn:

| Property | Giá trị cuối | Nguồn |
| --- | --- | --- |
| `app.delivery.endpoint` | `https://api.example.test` | OS environment |
| `app.delivery.connect-timeout` | `10s` | OS environment |
| `app.delivery.max-retries` | `4` | Command-line argument |
| `app.delivery.enabled` | `false` | YAML |

Dù bạn dùng JavaBean, immutable class hay record, dữ liệu được bind từ các **giá trị hiệu lực trong `Environment`**. Không có kiểu nào tự tạo ra nguồn cấu hình mới hoặc thay đổi nguyên tắc ghi đè theo property.

Quy tắc canonical cho biến môi trường khi bind `@ConfigurationProperties`: dấu chấm `.` thành `_`, bỏ dấu gạch nối `-`, rồi chuyển thành chữ hoa. Ví dụ `app.delivery.connect-timeout` → `APP_DELIVERY_CONNECTTIMEOUT`.

Nếu hệ thống dùng `setAddCommandLineProperties(false)`, đối số `--app.delivery.max-retries=4` sẽ không được đưa vào nguồn cấu hình CLI theo cơ chế mặc định; kết quả phụ thuộc các nguồn còn lại.

## 14. Khi nào nên chọn từng kiểu?

### 14.1. Chọn JavaBean khi...

- Dự án hoặc thư viện sử dụng API getter/setter truyền thống.
- Có lớp mutable từ bên ngoài mà Spring chỉ có thể cấu hình sau khi tạo instance.
- Cần giữ một nested bean có thể được bind qua setters.
- Muốn tương thích với các framework/convention cũ có kỳ vọng JavaBean.

Đổi lại, cần quản lý việc tránh sửa config sau startup. Nếu không có nhu cầu sửa cấu hình trong runtime, các setter công khai có thể là một điểm yếu về thiết kế.

### 14.2. Chọn immutable class khi...

- Muốn một object có các field `final` và API chặt chẽ.
- Cần logic constructor riêng, nhiều phương thức trợ giúp hoặc invariant phức tạp.
- Muốn kiểm soát representation, ví dụ không để lộ `toString()` có secret.
- Không phù hợp với record vì cần kế thừa một class khác, hoặc thiết kế cần mức linh hoạt mà record không cung cấp.

Đổi lại, có thêm boilerplate constructor/getter/equals nếu cần.

### 14.3. Chọn record khi...

- Cấu hình chủ yếu là **dữ liệu**, không phải đối tượng chứa behavior phức tạp.
- Muốn code ít nhưng các trường cấu hình rõ ràng.
- Chạy Java version hỗ trợ record và Spring Boot hỗ trợ constructor binding.
- Muốn mô hình tự nhiên cho dependency injection: cấu hình được tạo một lần và truy cập qua các accessor.

Đổi lại, record không extends một class bất kỳ, tự sinh `toString()` có thể đưa nội dung cấu hình vào log và “bất biến” của collection chỉ ở cấp tham chiếu.

**Một lựa chọn thực dụng:** với nhóm cấu hình mới, thuần dữ liệu trong Java 17+/Spring Boot 3.x, record thường rất gọn. Với đối tượng vendor có setter, JavaBean binding phù hợp hơn. Với yêu cầu bất biến cần constructor logic đặc thù, class `final` là lựa chọn tốt.

## 15. Ba dạng binding không phải ba cách cập nhật cấu hình động

Một hiểu lầm phổ biến: JavaBean có setter nên khi chỉnh `application.yml` lúc ứng dụng đang chạy, Spring Boot sẽ tự gọi setter lần nữa.

Điều này **không mặc nhiên xảy ra**. Trong một ứng dụng Spring Boot thông thường, config data được nạp khi khởi động, bean properties được bind trong quá trình tạo context. Việc file YAML trên disk thay đổi không tự làm bean được cập nhật.

- JavaBean có thể thay đổi nếu code thực sự gọi setter, nhưng đó không phải config refresh tự động.
- Immutable class không có setter; nếu có cơ chế refresh chuyên biệt, thường cần xây object mới hoặc xử lý lifecycle riêng.
- Record cũng là đối tượng được tạo từ values trong lúc binding; việc sửa file không thay đổi components đã có.

Nếu dự án dùng Spring Cloud Config, `@RefreshScope` hoặc cơ chế reload riêng, cần xét hợp đồng của chính cơ chế đó. Không chọn JavaBean chỉ vì hy vọng Spring Boot đọc lại YAML sau mỗi request.

## 16. Kiểm tra bằng mã tiêu thụ cấu hình

Với ví dụ **record** được đăng ký bằng `@EnableConfigurationProperties(DeliveryRecordProperties.class)`:

~~~java
package com.example.service;

import com.example.config.DeliveryRecordProperties;
import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryRecordProperties properties;

    public DeliveryService(DeliveryRecordProperties properties) {
        this.properties = properties;
    }

    public boolean canDeliver() {
        return properties.enabled() && properties.maxRetries() >= 0;
    }

    public String targetEndpoint() {
        return properties.endpoint();
    }
}
~~~

Đổi sang JavaBean hoặc immutable class thì kiểu constructor parameter và các accessor đổi:

~~~java
// JavaBean:
properties.isEnabled();
properties.getMaxRetries();
properties.getEndpoint();

// Immutable class có getter tương tự:
properties.isEnabled();
properties.getMaxRetries();
properties.getEndpoint();

// Record:
properties.enabled();
properties.maxRetries();
properties.endpoint();
~~~

Không trộn mã truy cập của record với JavaBean: record mặc định không tự sinh `getEndpoint()`.

**Chú ý:** các ví dụ `DeliveryService`/`DeliveryJavaBeanProperties` ở đây được triển khai như các phương án thay thế, không nên sao chép tất cả snippets với cùng tên class vào một source file rồi kỳ vọng Java biên dịch. Mỗi public type đặt trong file Java thích hợp và chọn một cấu hình registration theo mẫu tương ứng.

## 17. Kiểm thử binding và validation

Một bài kiểm thử cấu hình cần kiểm tra ít nhất ba nhóm tình huống:

1. **Happy path:** bốn key có mặt và được chuyển đúng kiểu.
2. **Thiếu/giá trị mặc định:** key tùy chọn bị thiếu phải có default mong muốn; key bắt buộc bị thiếu cần fail.
3. **Sai kiểu/ràng buộc:** `connect-timeout: not-a-duration`, `max-retries: -1`, `endpoint: "   "` phải được nhận diện.

Một test Spring Boot có thể sử dụng `ApplicationContextRunner` để nạp một lớp cấu hình và xác minh bean, ví dụ với **record**:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ConfigurationPropertiesAutoConfiguration.class))
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsRecordFromExternalProperties() {
        runner
            .withPropertyValues(
                "app.delivery.endpoint=https://api.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3",
                "app.delivery.enabled=true"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                DeliveryRecordProperties props =
                        context.getBean(DeliveryRecordProperties.class);
                assertThat(props.endpoint())
                        .isEqualTo("https://api.example.test");
                assertThat(props.connectTimeout())
                        .isEqualTo(java.time.Duration.ofSeconds(5));
                assertThat(props.maxRetries()).isEqualTo(3);
                assertThat(props.enabled()).isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryRecordProperties.class)
    static class TestConfiguration {
    }
}
~~~

Ví dụ test cần dependency `spring-boot-starter-test`, cùng các dependency validation nếu test kiểm tra validation. Nếu project có cấu hình test riêng, có thể dùng `@SpringBootTest(properties = {...})` để xác minh tại mức application context.

Với JavaBean và immutable class, thay type được `@EnableConfigurationProperties` đăng ký, sau đó thay cách đọc getter tương ứng. Mục tiêu là xác minh rằng **cùng input** tạo ra **cùng giá trị mô hình** qua ba phương án.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JavaBean có field nhưng không bind | Thiếu setter cho property cần ghi, hoặc class chưa được đăng ký | Thêm getter/setter phù hợp và đăng ký bean |
| Lớp bất biến nhận null/0 không mong muốn | Thiếu key, không có `@DefaultValue` hoặc constraint tương ứng | Khai báo default/validation rõ ràng |
| Record không được tạo từ cấu hình | Sử dụng constructor binding với `@Component`/`@Bean` không phù hợp | Dùng `@EnableConfigurationProperties` hoặc scan |
| Class có hai constructor và binder chọn sai | Chưa chỉ rõ constructor bind | Dùng `@ConstructorBinding` trên constructor thích hợp trong Boot 3.x |
| Constructor binding báo không biết tên parameter | Build không giữ metadata tên tham số | Kiểm tra cấu hình `-parameters` |
| `connectTimeout` không được bind | Sai tên key hoặc giá trị timeout không chuyển đổi được | Dùng `connect-timeout: 5s` và `Duration` đúng kiểu |
| Endpoint sai nhưng không fail | Chưa có validation, hoặc thiếu `spring-boot-starter-validation` | Dùng `@Validated` + constraint/logic nghiệp vụ |
| Record bị lộ secret trong log | `toString()` tự sinh chứa record components | Không log trực tiếp object có secret; dùng redaction |
| YAML thay đổi nhưng object không đổi | Không có cơ chế refresh được cấu hình | Restart/redeploy hoặc dùng refresh riêng |
| Có ba bean cùng prefix, dependency ambiguous | Scan/enable cả ba biến thể một lúc | Đăng ký một phương án hoặc dùng qualifier có chủ đích |
| JavaBean setter thay đổi khi chạy | Mã nghiệp vụ gọi setter ngoài ý muốn | Giảm khả năng mutation, cân nhắc immutable class/record |
| Nested object không được tạo | Không có default/nested binding phù hợp | Khởi tạo nested JavaBean hoặc dùng default/constructor model đúng cách |
| Đặt default trong object nhưng `Environment` không thấy | Object initializer không thêm entry vào property sources | Đặt default vào config data nếu cần tra cứu ở nơi khác |

## 19. Bài tập thực hành: đổi từ JavaBean sang record

### Đề bài

Cho file cấu hình:

~~~yaml
app:
  delivery:
    endpoint: https://api.example.test
    connect-timeout: 7s
    max-retries: 4
    enabled: false
~~~

JavaBean đang có:

~~~java
@ConfigurationProperties("app.delivery")
public class DeliveryProperties {
    private String endpoint;
    private Duration connectTimeout;
    private int maxRetries;
    private boolean enabled;

    // getters và setters cho cả bốn field
}
~~~

Hãy chuyển nó sang record, không đổi tên property hay ý nghĩa giá trị.

### Đáp án tham khảo

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        String endpoint,
        Duration connectTimeout,
        int maxRetries,
        boolean enabled) {
}
~~~

Đăng ký type record với `@EnableConfigurationProperties(DeliveryProperties.class)` hoặc `@ConfigurationPropertiesScan`. Kết quả: endpoint là URL ví dụ, timeout là `Duration.ofSeconds(7)`, maxRetries là `4` và enabled là `false`.

Hãy chú ý mã tiêu thụ phải chuyển từ `properties.getEndpoint()` sang `properties.endpoint()` và tương tự với các field còn lại.

### Câu hỏi tiếp theo

**Câu 1.** Nếu bỏ `app.delivery.max-retries` và muốn mặc định là `2`, có thể làm gì?

**Đáp án:** thêm `@DefaultValue("2")` trên record component `int maxRetries`, hoặc đặt giá trị mặc định ở một nguồn config data như `application.yml`. Nếu chọn default của object, key đó không tự xuất hiện trong `Environment`.

**Câu 2.** Nếu muốn class đọc cấu hình phải kế thừa một class cơ sở thì record có phù hợp không?

**Đáp án:** Java record không extends class bất kỳ ngoài `java.lang.Record`. Cân nhắc immutable class thông thường hoặc JavaBean tùy yêu cầu thiết kế.

**Câu 3.** Nếu có một client thư viện chỉ có constructor nhận `endpoint` và `timeout`, có thể đặt `@ConfigurationProperties` trên `@Bean` trả về client bất biến và tự động bind constructor không?

**Đáp án:** Không theo cơ chế constructor binding chuyên dụng. Hãy bind một class/record properties riêng, rồi inject nó vào `@Bean` factory method để tạo client.

**Câu 4.** Dùng record có tự giải quyết vấn đề hot reload không?

**Đáp án:** Không. Spring Boot mặc định nạp config data và bind bean trong giai đoạn khởi động; muốn refresh cần cơ chế khác và thiết kế vòng đời phù hợp.

## 20. Checklist lựa chọn trong dự án

Khi thiết kế một nhóm cấu hình mới, có thể tự hỏi:

1. Object cấu hình có phải dữ liệu thuần, chỉ đọc sau startup? Nếu có, record hoặc immutable class thường dễ bảo toàn trạng thái.
2. Có bắt buộc tương thích setter-based framework hay object bên ngoài? Nếu có, JavaBean có thể phù hợp hơn.
3. Có cần logic constructor đặc thù hoặc subclassing? Nếu có, immutable class thông thường linh hoạt hơn record.
4. Cấu hình có nested object hoặc collection mutable? Nếu có, xác định rõ null/default và chiến lược deep immutability.
5. Key bắt buộc và điều kiện hợp lệ đã có `@Validated`/constraints chưa? Chỉ có constructor binding chưa đủ.
6. Dự án đang dùng Spring Boot 2.x hay 3.x? Kiểm tra vị trí `@ConstructorBinding` và namespace Jakarta/Javax validation.
7. Cơ chế đăng ký bean đúng chưa? Đặc biệt với constructor-bound properties, ưu tiên `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
8. Có property nguồn ưu tiên cao hơn đang ghi đè file? Loại class không thay đổi precedence.
9. Có định log object properties không? Cẩn thận với secret và `toString()` của record.
10. Có cần refresh runtime hay chỉ cấu hình tại startup? Đừng nhầm tính mutable của JavaBean với khả năng tự động reload config.

## 21. Tóm tắt

**Cùng một cấu hình `app.delivery` có thể bind vào cả JavaBean, immutable class hoặc record**, miễn là đúng cơ chế đăng ký và tạo object:

- **JavaBean:** constructor không tham số + setter; dễ bind từng field và giữ initializer defaults, nhưng mutable và nhiều boilerplate.
- **Immutable class:** constructor binding + `final` fields; phù hợp khi cần API cố định và logic tạo object, nhưng phải viết constructor/getter.
- **Record:** constructor binding dựa trên record components; ít code, dễ đọc, tự sinh accessor/equals/hashCode/toString, nhưng cần để ý secret và collection mutability.

Chọn mô hình dựa trên **hợp đồng cấu hình và API mong muốn**, không phải trên suy đoán rằng kiểu này sẽ có property source ưu tiên hơn kiểu kia. Dù dùng loại nào, vẫn phải kiểm tra validation, giá trị mặc định, tên property và thứ tự nguồn cấu hình.

### Tài liệu tham khảo

- Spring Boot 3.5 Reference — JavaBean Properties Binding, Constructor Binding và Default Values: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Validation và Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Java Language Specification — Record Classes: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
