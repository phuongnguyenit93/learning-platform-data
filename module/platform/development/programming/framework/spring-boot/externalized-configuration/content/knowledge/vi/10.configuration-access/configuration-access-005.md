# Tiêm giá trị đơn bằng @Value ở constructor, trường và phương thức

## 1. Vì sao cần tiêm giá trị cấu hình?

Trong ứng dụng Spring Boot, nhiều giá trị không nên viết cố định trong mã Java: lời chào hiển thị, thời gian chờ, số lần thử lại, địa chỉ endpoint, chế độ tính năng hoặc ngưỡng xử lý. Các giá trị này có thể thay đổi giữa môi trường phát triển, kiểm thử và production.

Ví dụ, ứng dụng đọc tệp `src/main/resources/application.yml`:

```yaml
demo:
  greeting: "Xin chào từ application.yml"
  retry-count: 3
  feature-enabled: true
  region: "ap-southeast"
```

Thay vì viết:

```java
String greeting = "Xin chào từ application.yml";
int retryCount = 3;
```

ta muốn Spring đưa những giá trị đã được giải quyết từ hệ thống cấu hình vào bean.

**`@Value`**, thuộc gói `org.springframework.beans.factory.annotation`, là một cách để yêu cầu Spring **tiêm một giá trị được biểu diễn bằng biểu thức hoặc placeholder** vào điểm tiêm của bean.

Cú pháp phổ biến:

```java
@Value("${demo.greeting}")
```

Trong đó `${demo.greeting}` là một **property placeholder**. Khi Spring xử lý điểm tiêm, placeholder được giải quyết dựa trên `Environment` và các nguồn thuộc tính hiện có.

Có ba vị trí thực hành quan trọng:

1. **Constructor parameter:** giá trị được chuyển vào lúc tạo đối tượng.
2. **Field:** Spring đặt giá trị trực tiếp vào một trường của bean.
3. **Method/parameter:** Spring gọi một phương thức tiêm hoặc setter và truyền giá trị cần thiết.

Bài này tập trung vào **tiêm giá trị đơn** như `String`, `int`, `boolean`. Khi cấu hình là một nhóm nhiều trường, cần cân nhắc `@ConfigurationProperties`.

## 2. @Value không tự đọc một tệp cụ thể

`@Value("${demo.greeting}")` không có nghĩa là “đọc khóa `demo.greeting` từ đúng tệp `application.yml`”. Nó yêu cầu Spring lấy **giá trị có hiệu lực** của thuộc tính đó.

Ví dụ, `application.yml` chứa:

```yaml
demo:
  greeting: "Từ YAML"
```

Nhưng khi chạy:

```bash
java -jar app.jar --demo.greeting="Từ dòng lệnh"
```

một bean được tạo với:

```java
@Value("${demo.greeting}")
String greeting;
```

thường nhận `Từ dòng lệnh`, vì đối số dòng lệnh có mức ưu tiên cao hơn Config Data trong cấu hình Spring Boot thông thường.

Tương tự, biến môi trường được cấp cho tiến trình Java:

```bash
DEMO_GREETING="Từ biến môi trường" java -jar app.jar
```

có thể cung cấp giá trị cho khóa `demo.greeting` khi không có nguồn cao hơn ghi đè.

Do đó, ta cần tách hai câu hỏi:

- **Giá trị được chọn từ đâu?** Cơ chế Spring `Environment` và thứ tự ưu tiên giữa các nguồn thuộc tính quyết định.
- **Giá trị được đặt vào bean như thế nào?** `@Value` và cơ chế dependency injection của Spring thực hiện.

Hai cơ chế phối hợp với nhau nhưng không đồng nghĩa.

## 3. Chuẩn bị ứng dụng minh họa

Các ví dụ dùng Spring Boot 3.x, Java 17 trở lên và một ứng dụng có cấu hình `@SpringBootApplication`.

Tệp cấu hình:

```yaml
# src/main/resources/application.yml
demo:
  greeting: "Xin chào từ ứng dụng"
  retry-count: 3
  feature-enabled: true
  region: "vn"
  max-items: 50
```

Lớp khởi động:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Những ví dụ sau đặt các thành phần trong package `com.example.configdemo` hoặc package con để được Spring component scan phát hiện.

Cần nhớ: cơ chế `@Value` thông thường có hiệu lực với **đối tượng được Spring quản lý**. Nếu tự gọi `new MyClass()`, bạn đã tạo một đối tượng Java thông thường, không tự đi qua quá trình tiêm giá trị của Spring.

## 4. Tiêm qua constructor: lựa chọn thường được ưu tiên

### 4.1. Ví dụ cơ bản

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    private final String greeting;
    private final int retryCount;

    public GreetingService(
            @Value("${demo.greeting}") String greeting,
            @Value("${demo.retry-count:3}") int retryCount) {
        this.greeting = greeting;
        this.retryCount = retryCount;
    }

    public String getGreeting() {
        return greeting;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
```

Ý nghĩa:

- `@Component` giúp Spring nhận diện lớp như một bean.
- `@Value("${demo.greeting}")` đặt trên **tham số constructor** yêu cầu giải quyết thuộc tính `demo.greeting`.
- `@Value("${demo.retry-count:3}")` đặt trên tham số `int`; nếu không tìm thấy thuộc tính, sử dụng mặc định là `3`.
- Constructor gán giá trị vào các trường `final`. Sau đó đối tượng giữ trạng thái đã được khởi tạo đầy đủ.

Thêm thành phần quan sát:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingPrinter implements ApplicationRunner {

    private final GreetingService service;

    public GreetingPrinter(GreetingService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.getGreeting());
        System.out.println("retryCount = " + service.getRetryCount());
    }
}
```

Khi chạy với cấu hình đã cho, chương trình có thể in:

```text
Xin chào từ ứng dụng
retryCount = 3
```

Nếu chạy:

```bash
java -jar app.jar --demo.greeting="Xin chào từ CLI" --demo.retry-count=7
```

giá trị được tiêm vào bean mới tạo sẽ tương ứng với cấu hình có hiệu lực:

```text
Xin chào từ CLI
retryCount = 7
```

### 4.2. Vì sao constructor injection đáng ưu tiên?

Constructor injection có các ưu điểm thực tế:

- **Đối tượng hợp lệ ngay sau khi tạo:** các phụ thuộc và giá trị bắt buộc được truyền trong lúc khởi tạo.
- **Trường có thể là `final`:** giúp thể hiện dữ liệu không được gán lại sau constructor.
- **Dễ kiểm thử đơn vị:** bạn có thể tự tạo `new GreetingService("Test", 2)` mà không cần khởi động Spring context.
- **Thấy rõ phụ thuộc:** người đọc constructor biết bean cần những giá trị gì.

Ví dụ kiểm thử thuần Java/JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void constructorReceivesValues() {
        GreetingService service = new GreetingService("Trong test", 4);

        assertEquals("Trong test", service.getGreeting());
        assertEquals(4, service.getRetryCount());
    }
}
```

Khi tạo trực tiếp bằng `new` trong bài test này, Spring **không** giải quyết placeholder. Bạn chủ động đưa các giá trị vào constructor, và điều đó chính là một ưu điểm kiểm thử.

### 4.3. Có cần @Autowired trên constructor?

Với một bean có **duy nhất một constructor**, Spring hiện đại có thể sử dụng constructor ấy để tiêm dependency mà không cần đặt `@Autowired` trên constructor.

Trong ví dụ `GreetingService`, các tham số đều có `@Value`, còn constructor không cần chú thích thêm.

Nếu lớp có nhiều constructor, việc Spring chọn constructor nào cần được thiết kế rõ ràng; có thể dùng `@Autowired` trên constructor phù hợp. Tránh tạo nhiều constructor cạnh tranh mà không có quy tắc lựa chọn nhất quán.

## 5. Tiêm trực tiếp vào trường bằng @Value

### 5.1. Ví dụ field injection

```java
package com.example.configdemo;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldConfigPrinter {

    @Value("${demo.greeting:Hello}")
    private String greeting;

    @Value("${demo.retry-count:3}")
    private int retryCount;

    @PostConstruct
    public void printConfiguration() {
        System.out.println("Field greeting = " + greeting);
        System.out.println("Field retryCount = " + retryCount);
    }
}
```

Spring tạo bean rồi xử lý các điểm tiêm trên trường. Khi phương thức gắn `@PostConstruct` được gọi theo vòng đời bean thông thường, các giá trị cần tiêm đã được thiết lập.

Điểm đáng chú ý:

- Không cần viết constructor nhận `greeting` và `retryCount`.
- `@Value` gắn trực tiếp với trường cần nhận dữ liệu.
- Có thể tiêm vào trường `private` vì Spring thực hiện tiêm qua cơ chế phản chiếu/phần xử lý bean của framework.
- Đây không phải phép gán xảy ra khi Java thực thi câu lệnh `new` bên ngoài Spring.

### 5.2. Vì sao field injection có hạn chế?

Mã:

```java
@Value("${demo.greeting}")
private String greeting;
```

ngắn gọn nhưng làm phụ thuộc cấu hình bị “ẩn” trong lớp. Nếu tạo:

```java
FieldConfigPrinter printer = new FieldConfigPrinter();
```

thì Spring không tiêm gì vào đối tượng mới do bạn tự tạo. Trường `greeting` có thể vẫn là `null` và `retryCount` có thể là `0` theo giá trị mặc định của Java.

Các hạn chế thường gặp:

1. Khó tạo đối tượng trong unit test mà không dùng Spring hoặc reflection.
2. Khó biểu diễn phụ thuộc bắt buộc bằng trường `final` với cách tiêm vào trường sau khi tạo.
3. Dễ vô tình sử dụng trường quá sớm, ví dụ ngay trong constructor của chính bean.
4. Lớp có thể tích lũy nhiều trường cấu hình mà không có hợp đồng khởi tạo rõ ràng.

Field injection vẫn có thể xuất hiện trong ví dụ ngắn, ứng dụng nhỏ hoặc mã đã tồn tại, nhưng constructor injection thường dễ duy trì hơn với phụ thuộc bắt buộc.

### 5.3. Không đọc trường @Value trong constructor nếu nó được tiêm qua field

Ví dụ có vấn đề:

```java
@Component
public class BadFieldExample {

    @Value("${demo.greeting}")
    private String greeting;

    public BadFieldExample() {
        // Tại thời điểm này, field injection có thể chưa xảy ra.
        System.out.println(greeting);
    }
}
```

Giá trị của `greeting` tại thời điểm constructor chạy thường chưa được tiêm. Đừng xem đây là “Spring không đọc được application.yml”; đây là **vấn đề thời điểm trong vòng đời tạo bean**.

Nếu giá trị cần thiết để xây dựng trạng thái ban đầu, hãy tiêm qua constructor:

```java
@Component
public class GoodConstructorExample {

    private final String greeting;

    public GoodConstructorExample(
            @Value("${demo.greeting}") String greeting) {
        this.greeting = greeting;
        System.out.println(this.greeting);
    }
}
```

Khi chọn field injection, hãy dùng giá trị sau khi Spring hoàn thành tiêm thuộc tính, ví dụ trong `@PostConstruct` hoặc các phương thức nghiệp vụ được gọi sau khi bean khởi tạo.

## 6. Tiêm vào phương thức và setter

Ngoài constructor và trường, Spring có thể cung cấp giá trị cấu hình thông qua **phương thức tiêm**.

### 6.1. Phương thức nhận tham số có @Value

Ví dụ một phương thức nhận hai giá trị cấu hình:

```java
package com.example.configdemo;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MethodConfigPrinter {

    private String region;
    private boolean featureEnabled;

    @Autowired
    public void configure(
            @Value("${demo.region:local}") String region,
            @Value("${demo.feature-enabled:false}") boolean featureEnabled) {
        this.region = region;
        this.featureEnabled = featureEnabled;
    }

    @PostConstruct
    public void printConfiguration() {
        System.out.println("region = " + region);
        System.out.println("featureEnabled = " + featureEnabled);
    }
}
```

Ở đây:

- `@Autowired` trên phương thức yêu cầu Spring gọi phương thức đó như một điểm tiêm.
- `@Value` trên **từng tham số** chỉ rõ giá trị cấu hình tương ứng cần được giải quyết.
- Spring gọi `configure(...)` trong quá trình hoàn thiện bean, sau bước tạo đối tượng và trước các callback khởi tạo thông thường.
- Phương thức này không được gọi lại mỗi khi giá trị cấu hình ngoài ứng dụng thay đổi.

Với cấu hình YAML ban đầu, kết quả dự kiến:

```text
region = vn
featureEnabled = true
```

### 6.2. Setter một tham số với @Value

Với setter chỉ nhận một tham số, có thể viết:

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class BannerSettings {

    private String banner;

    @Value("${demo.greeting:Hello}")
    public void setBanner(String banner) {
        this.banner = banner;
    }

    public String getBanner() {
        return banner;
    }
}
```

`@Value` trên phương thức là một dạng khai báo tiêm giá trị được Spring xử lý với bean do container quản lý. Điểm tiêm này thích hợp cho một giá trị gắn với setter.

Một cách diễn đạt khác, thường rõ ràng hơn khi phương thức nhận nhiều tham số, là `@Autowired` trên phương thức và `@Value` trên từng tham số như ví dụ `MethodConfigPrinter`.

Đừng nhầm **method injection** với gọi thủ công một phương thức chứa tham số kiểu `@Value`. Nếu bạn tự viết:

```java
settings.setBanner("Gán tay");
```

thì đây chỉ là một lời gọi Java bình thường, không phải Spring tự đọc cấu hình ở thời điểm gọi.

### 6.3. Khi nào nên chọn setter/method injection?

Setter/method injection hữu ích khi một giá trị là tùy chọn hoặc khi cấu trúc lớp hiện có cần một bước cấu hình sau khi tạo đối tượng. Một phương thức có thể xử lý nhiều tham số liên quan trong một lần gọi.

Tuy nhiên, các trường được gán ở bước sau constructor có thể chưa sẵn sàng ngay lúc constructor chạy. Nếu lớp phải luôn có giá trị từ thời điểm tạo đối tượng, constructor injection thường là lựa chọn rõ ràng hơn.

Ngoài ra, việc Spring gọi một setter trong quá trình tạo bean **không đồng nghĩa** setter đó có cơ chế lắng nghe thay đổi cấu hình tự động ở thời gian chạy.

## 7. Bảng so sánh ba vị trí tiêm

| Tiêu chí | Constructor | Trường (field) | Phương thức/setter |
| --- | --- | --- | --- |
| Điểm đặt `@Value` | Tham số constructor | Trên field | Trên method hoặc tham số của method tiêm |
| Thời điểm nhận dữ liệu | Khi bean được tạo | Sau khi tạo, trong bước tiêm | Sau khi tạo, khi Spring gọi method tiêm |
| Có thể dùng field `final`? | Có | Không phù hợp với tiêm trường sau tạo | Không phù hợp nếu được gán sau constructor |
| Thuận tiện với unit test thuần Java | Rất tốt | Kém hơn | Có thể gọi setter thủ công |
| Phụ thuộc có hiện rõ khi tạo đối tượng? | Có | Không | Không phải lúc constructor |
| Ví dụ phù hợp | Giá trị bắt buộc | Mã ngắn, ví dụ đơn giản | Cấu hình tùy chọn hoặc nhiều tham số |
| Tự động cập nhật khi thuộc tính đổi? | Không | Không | Không |

Bảng này áp dụng cho tiêm giá trị cấu hình thông thường vào singleton bean của Spring. Những cơ chế chuyên biệt như refresh scope, tái tạo bean hoặc truy vấn `Environment` tại thời điểm sử dụng có vòng đời khác và không phải tác dụng mặc định của `@Value`.

## 8. Property placeholder: cú pháp ${...}

Cú pháp thông dụng nhất trong bài là:

```java
@Value("${demo.greeting}")
```

Nó yêu cầu Spring giải quyết khóa `demo.greeting` từ `Environment`.

### 8.1. Giá trị mặc định

Cú pháp:

```java
@Value("${demo.greeting:Hello}")
private String greeting;
```

Phần sau dấu hai chấm trong placeholder là **giá trị dự phòng** khi không tìm thấy thuộc tính.

Ví dụ với số nguyên:

```java
@Value("${demo.retry-count:3}")
private int retryCount;
```

Nếu `demo.retry-count` không có nguồn cung cấp, Spring có thể chuyển chuỗi dự phòng `3` sang `int`.

Với Boolean:

```java
@Value("${demo.feature-enabled:false}")
private boolean featureEnabled;
```

Nếu không thấy khóa, sử dụng `false`.

### 8.2. Thiếu thuộc tính mà không có mặc định

Ví dụ:

```java
@Component
public class RequiredConfig {

    public RequiredConfig(
            @Value("${demo.required-token}") String token) {
        // ...
    }
}
```

Nếu không có thuộc tính `demo.required-token` và không có cấu hình đặc biệt thay đổi cơ chế xử lý placeholder, Spring Boot thông thường sẽ không thể tạo bean này và quá trình khởi động có thể thất bại với lỗi liên quan đến placeholder chưa được giải quyết.

Điều đó hữu ích với cấu hình bắt buộc: ứng dụng nên phát hiện sớm khi thiếu đầu vào cần thiết.

Với các giá trị nhạy cảm như token, tránh in giá trị nhận được ra log hay hiển thị trong thông báo lỗi.

### 8.3. Mặc định rỗng

```java
@Value("${demo.optional-note:}")
private String note;
```

Nếu khóa không tồn tại, phần mặc định có thể là chuỗi rỗng.

Nhưng **chuỗi rỗng khác với thuộc tính hoàn toàn không tồn tại**. Nếu nguồn cấu hình đã cung cấp `demo.optional-note=""`, kết quả có thể là chuỗi rỗng từ chính nguồn đó. Không nên suy luận mọi giá trị rỗng sẽ tự kích hoạt giá trị mặc định sau dấu hai chấm.

Với những giá trị đầu vào cần kiểm tra không rỗng, hãy bổ sung validation hoặc kiểm tra nghiệp vụ thích hợp.

### 8.4. Không dùng placeholder như một phép tra cứu tệp tùy ý

`@Value("${demo.greeting}")` chỉ rõ một **khóa thuộc tính**. Nó không tự mở tệp, không tự parse JSON tùy ý và không tự lấy secret từ một dịch vụ bên ngoài. Những khả năng đó chỉ có khi nguồn cấu hình tương ứng đã được tích hợp vào Spring `Environment` hoặc có logic riêng giải quyết dữ liệu.

## 9. Chuyển đổi kiểu khi tiêm giá trị

Một ưu điểm của `@Value` là Spring có cơ chế chuyển kiểu cho giá trị đơn.

Ví dụ:

```yaml
demo:
  retry-count: 5
  feature-enabled: false
  threshold: 0.75
```

Các field nhận kiểu Java:

```java
@Value("${demo.retry-count:3}")
private int retryCount;

@Value("${demo.feature-enabled:true}")
private boolean featureEnabled;

@Value("${demo.threshold:0.5}")
private double threshold;
```

Khi những thuộc tính được giải quyết và chuyển đổi thành công, kết quả là:

```text
retryCount = 5
featureEnabled = false
threshold = 0.75
```

Nếu một giá trị không hợp lệ cho kiểu đích, Spring có thể báo lỗi trong lúc tạo bean. Ví dụ `demo.retry-count=abc` không thể chuyển trực tiếp sang `int` theo cách thông thường.

Không nên dùng `@Value` như cơ chế bỏ qua lỗi dữ liệu. Với cấu hình cần ràng buộc nghiêm ngặt — số dương, thời gian chờ hợp lệ, tập giá trị được phép — nên bổ sung validation, hoặc dùng `@ConfigurationProperties` với Bean Validation cho một nhóm thuộc tính.

### 9.1. Tên thuộc tính chuẩn và relaxed binding

Spring Boot khuyến nghị viết khóa trong `@Value` theo dạng chuẩn **lowercase, kebab-case**, ví dụ:

```java
@Value("${demo.retry-count}")
private int retryCount;
```

Cách viết nhất quán này giúp Spring Boot tận dụng việc tra cứu thuộc tính từ nhiều dạng cấu hình. Đừng cho rằng `@Value` có mọi khả năng liên kết danh sách, map và cấu trúc lồng nhau giống `@ConfigurationProperties`; hai cơ chế có phạm vi và tiện ích khác nhau.

Ví dụ biến môi trường được truyền cho JVM:

```bash
DEMO_RETRYCOUNT=8 java -jar app.jar
```

là một cách biểu diễn quen thuộc khi chuyển tên thuộc tính `demo.retry-count` sang dạng biến môi trường chuẩn. Với thuộc tính `demo.greeting`, biến `DEMO_GREETING` là dạng trực quan hơn. Dùng tên chuẩn trong placeholder và kiểm tra thực tế trong `Environment` nếu một biến môi trường không được ánh xạ như dự đoán.

## 10. @Value còn hỗ trợ biểu thức SpEL

Ngoài placeholder `${...}`, Spring `@Value` còn có thể dùng **Spring Expression Language (SpEL)** với cú pháp `#{...}`.

Ví dụ:

```java
@Value("#{2 * 3}")
private int computedValue;
```

Giá trị sau xử lý biểu thức là `6`.

Hoặc:

```java
@Value("#{systemProperties['user.home']}")
private String userHome;
```

Biểu thức trên đọc Java system property `user.home` thông qua SpEL.

So sánh:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `@Value("${demo.greeting}")` | Tra cứu thuộc tính từ môi trường cấu hình |
| `@Value("${demo.greeting:Hello}")` | Tra cứu thuộc tính, có giá trị dự phòng |
| `@Value("#{2 * 3}")` | Đánh giá biểu thức SpEL |
| `@Value("Nội dung cố định")` | Tiêm literal string |

Không cần sử dụng SpEL cho những trường hợp chỉ muốn lấy một thuộc tính đơn giản. Placeholder dễ đọc và gần với mục đích Externalized Configuration hơn.

Cũng cần phân biệt ký hiệu: `${...}` là placeholder, còn `#{...}` là biểu thức SpEL. Chúng không cùng một cơ chế.

## 11. Giá trị @Value đến từ những nguồn nào?

Đối với ứng dụng Spring Boot, một khóa như `demo.greeting` có thể được cung cấp bởi:

- tệp `application.yml`, `application.properties`;
- tài liệu theo profile;
- tệp cấu hình ngoài JAR;
- dữ liệu được nạp qua `spring.config.import`;
- biến môi trường của tiến trình;
- Java system properties;
- đối số dòng lệnh;
- các nguồn cấu hình khác được framework hoặc ứng dụng bổ sung.

Ví dụ:

```yaml
# application.yml
demo:
  greeting: "from-yaml"
```

Chạy:

```bash
DEMO_GREETING=from-env java -jar app.jar
```

Giá trị của `demo.greeting` thường là `from-env` nếu không có nguồn cao hơn ghi đè.

Chạy:

```bash
DEMO_GREETING=from-env java -jar app.jar --demo.greeting=from-cli
```

Giá trị được tiêm thông qua `@Value("${demo.greeting}")` là `from-cli` trong trường hợp thông thường.

Điểm chính là: **Spring tiêm kết quả sau khi giải quyết thứ tự nguồn**, chứ không tiêm nguyên văn “giá trị đầu tiên nhìn thấy trong một tệp” hoặc chọn dựa trên vị trí đặt annotation trong lớp.

## 12. Khi nào @Value được giải quyết trong vòng đời bean?

Hãy hình dung hai kiểu bean.

**Constructor injection:**

```text
Spring chuẩn bị tạo bean
        |
        +-- giải quyết ${demo.greeting}
        |
        +-- gọi constructor(greeting)
        |
        +-- đối tượng có trường final được gán
        |
        +-- tiếp tục các bước khởi tạo bean
```

**Field/method injection:**

```text
Spring gọi constructor
        |
        +-- đối tượng Java được tạo
        |
        +-- Spring xử lý @Value trên field/method
        |
        +-- Spring gọi các callback khởi tạo phù hợp
        |
        +-- bean sẵn sàng cho ứng dụng sử dụng
```

Đó là lý do bạn **không nên đọc field được tiêm bằng `@Value` trong constructor của cùng đối tượng**.

Đối với `@PostConstruct` trong một Spring bean được cấu hình bình thường, các điểm tiêm field/method đã được xử lý. Vì vậy đây là nơi có thể quan sát giá trị đã được tiêm nếu cần minh họa vòng đời.

Tuy nhiên, đừng dựa vào thứ tự tiêm của nhiều field hoặc nhiều method độc lập để cài đặt logic nghiệp vụ phụ thuộc vào thứ tự đó. Nếu cần thiết lập trạng thái từ nhiều giá trị, hãy nhóm chúng vào constructor hoặc một phương thức có các tham số rõ ràng.

### 12.1. @Value không tự làm mới giá trị

Giả sử bean được tạo lúc 9 giờ với:

```text
demo.greeting = Hello
```

Đến 10 giờ bạn sửa tệp cấu hình thành:

```text
demo.greeting = Hi
```

Một singleton bean bình thường đã nhận `Hello` qua `@Value` **không tự thay đổi** chỉ vì tệp trên đĩa đã được chỉnh sửa. Ứng dụng thường cần khởi động lại để lấy giá trị mới qua vòng đời tạo bean.

Nếu ứng dụng có cơ chế cấu hình động chuyên biệt, phải thiết kế quy trình refresh hoặc truy vấn thuộc tính theo nhu cầu; đó không phải chức năng mặc định của `@Value`.

## 13. @Value trên @Bean factory method parameter

Ngoài `@Component`, Spring cũng có thể giải quyết `@Value` trong tham số của một phương thức tạo bean thuộc `@Configuration`.

Ví dụ:

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkerConfiguration {

    @Bean
    public WorkPolicy workPolicy(
            @Value("${demo.retry-count:3}") int retryCount,
            @Value("${demo.feature-enabled:false}") boolean enabled) {
        return new WorkPolicy(retryCount, enabled);
    }
}

class WorkPolicy {

    private final int retryCount;
    private final boolean enabled;

    WorkPolicy(int retryCount, boolean enabled) {
        this.retryCount = retryCount;
        this.enabled = enabled;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

Ở đây, `@Value` đặt trên **tham số của factory method**, còn `@Bean` yêu cầu Spring gọi phương thức để tạo đối tượng `WorkPolicy`.

Đây là cách hữu ích khi lớp đối tượng được tạo không thuộc mã do bạn kiểm soát hoặc bạn muốn giữ phần xây dựng đối tượng ở một lớp cấu hình.

Nó khác với annotation trên một phương thức nghiệp vụ được gọi nhiều lần. Spring giải quyết tham số khi container gọi factory method để tạo bean, không tự động tiêm giá trị mỗi lần bất kỳ ai gọi một phương thức Java thông thường.

## 14. @Value chỉ có tác dụng khi đối tượng do Spring quản lý

Tình huống hay gặp:

```java
public class PlainService {

    @Value("${demo.greeting}")
    private String greeting;

    public String greeting() {
        return greeting;
    }
}
```

Và:

```java
PlainService service = new PlainService();
System.out.println(service.greeting());
```

Trong tình huống này, kết quả có thể là `null`: bạn tự tạo đối tượng, nên nó không đi qua bước tiêm annotation của Spring.

Muốn được quản lý, có thể khai báo `@Component` và bảo đảm component scan nhận diện lớp:

```java
@Component
public class PlainService {

    @Value("${demo.greeting}")
    private String greeting;

    public String greeting() {
        return greeting;
    }
}
```

Sau đó dùng dependency injection lấy bean:

```java
@Component
public class PlainServiceRunner implements ApplicationRunner {

    private final PlainService service;

    public PlainServiceRunner(PlainService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.greeting());
    }
}
```

Hoặc tạo bean bằng `@Bean` trong lớp `@Configuration`. Điều cốt lõi không phải tên annotation trên lớp mà là **đối tượng có được Spring container tạo và xử lý qua vòng đời bean hay không**.

## 15. Không dùng @Value cho static field

Ví dụ không nên làm:

```java
@Component
public class StaticConfiguration {

    @Value("${demo.greeting}")
    private static String greeting;
}
```

Trường `static` thuộc về lớp, không thuộc một instance bean cụ thể. Tiêm trực tiếp `@Value` trên static field không phải cách Spring hỗ trợ như tiêm trường của instance; thường dẫn đến giá trị không được gán như mong muốn.

Nếu bắt buộc phải có một API tĩnh vì tương thích với mã cũ, hãy cân nhắc thiết kế lại để truyền bean hoặc giá trị qua đối tượng được quản lý, thay vì trông chờ field static được Spring tự điền.

Không nên giải quyết bằng mẹo chuyển giá trị sang static trong `@PostConstruct` trừ khi thực sự không thể thay đổi thiết kế; cách đó tạo trạng thái toàn cục và làm vòng đời/kiểm thử trở nên khó hiểu.

## 16. Khi nào dùng @Value, khi nào dùng @ConfigurationProperties?

`@Value` rất hợp với **một vài giá trị đơn**:

```java
@Component
public class RetryService {
    private final int maxRetries;

    public RetryService(
            @Value("${demo.retry-count:3}") int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
```

Nhưng nếu cấu hình có nhiều khóa liên quan:

```yaml
client:
  endpoint: "https://api.example.invalid"
  connection-timeout: 5s
  read-timeout: 15s
  retry-count: 3
  retry-enabled: true
```

thì khai báo quá nhiều `@Value` rải rác trong nhiều lớp dễ gây khó quản lý.

Spring Boot cung cấp `@ConfigurationProperties` để liên kết **một nhóm thuộc tính có cấu trúc** vào đối tượng cấu hình, hỗ trợ kiểu dữ liệu phong phú, liên kết tên, metadata và validation thuận tiện hơn.

So sánh:

| Tiêu chí | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Nhu cầu chính | Một hoặc vài giá trị đơn | Một nhóm cấu hình có liên hệ |
| Điểm đặt | Field, parameter, method | Lớp/bean cấu hình |
| Placeholder | Có | Cấu hình thông qua cơ chế binder |
| SpEL | Có | Không phải cơ chế mục tiêu |
| Liên kết cấu trúc lồng nhau | Không thuận tiện | Được thiết kế cho mục đích này |
| Validation cho nhiều thuộc tính | Cần thiết kế thêm | Dễ kết hợp với Bean Validation |
| Khả năng tập trung hóa cấu hình | Dễ phân tán khi lạm dụng | Tốt hơn với nhóm cấu hình |

Không phải mọi ứng dụng đều cần chuyển tất cả `@Value` sang `@ConfigurationProperties`. Chọn cơ chế dựa vào độ phức tạp và quy mô cấu hình.

## 17. Kiểm thử việc tiêm @Value

### 17.1. Unit test constructor injection mà không cần Spring

Từ lớp `GreetingService` đã tạo ở trên:

```java
@Test
void canConstructWithoutSpring() {
    GreetingService service = new GreetingService("Hello test", 6);

    assertEquals("Hello test", service.getGreeting());
    assertEquals(6, service.getRetryCount());
}
```

Bài test này kiểm tra **logic đối tượng** và cách các giá trị được sử dụng sau constructor; không kiểm tra cơ chế placeholder.

### 17.2. Integration test với Spring Boot context

Nếu muốn kiểm tra Spring thực sự giải quyết `@Value` từ nguồn thuộc tính, dùng một test tạo context:

```java
package com.example.configdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.greeting=Hello integration test",
        "demo.retry-count=9"
})
class GreetingServiceIntegrationTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void valuesComeFromSpringEnvironment() {
        assertEquals("Hello integration test",
                greetingService.getGreeting());
        assertEquals(9, greetingService.getRetryCount());
    }
}
```

Ở đây:

- `@SpringBootTest` khởi động Spring context phục vụ test.
- Mảng `properties` cung cấp giá trị riêng cho môi trường kiểm thử.
- Spring tạo bean `GreetingService` và giải quyết các tham số `@Value`.
- Test xác nhận kết quả tiêm giá trị cho trường hợp cụ thể.

Tùy cấu trúc dự án, có thể cần khai báo lớp ứng dụng chính cho `@SpringBootTest` nếu Spring Boot không tự tìm được cấu hình khởi động phù hợp. Mã ví dụ đặt cùng package với `ConfigDemoApplication`.

### 17.3. Vì sao test field injection khó hơn?

Nếu dùng:

```java
@Value("${demo.greeting}")
private String greeting;
```

thì một unit test tạo đối tượng bằng `new` sẽ không có quá trình tiêm. Bạn phải tạo Spring context, dùng cơ chế test hỗ trợ hoặc thay đổi thiết kế. Với constructor injection, có thể truyền thẳng `"Hello test"` vào đối tượng nên bài test đơn giản hơn.

## 18. Một cấu hình đầy đủ với cả ba cách tiêm

Để so sánh thực tế, giả sử `application.yml`:

```yaml
demo:
  greeting: "Hello"
  retry-count: 4
  region: "local"
  feature-enabled: true
```

**Bean A — constructor:**

```java
@Component
public class ConstructorExample {

    private final String greeting;

    public ConstructorExample(
            @Value("${demo.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String value() {
        return greeting;
    }
}
```

**Bean B — field:**

```java
@Component
public class FieldExample {

    @Value("${demo.retry-count:3}")
    private int retryCount;

    public int value() {
        return retryCount;
    }
}
```

**Bean C — method:**

```java
@Component
public class MethodExample {

    private String region;
    private boolean enabled;

    @Autowired
    public void configure(
            @Value("${demo.region:unknown}") String region,
            @Value("${demo.feature-enabled:false}") boolean enabled) {
        this.region = region;
        this.enabled = enabled;
    }

    public String region() {
        return region;
    }

    public boolean enabled() {
        return enabled;
    }
}
```

Các import cần thiết cho những ví dụ rút gọn này là:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
```

Tạo một runner:

```java
@Component
public class ThreeWaysRunner implements ApplicationRunner {

    private final ConstructorExample constructorExample;
    private final FieldExample fieldExample;
    private final MethodExample methodExample;

    public ThreeWaysRunner(
            ConstructorExample constructorExample,
            FieldExample fieldExample,
            MethodExample methodExample) {
        this.constructorExample = constructorExample;
        this.fieldExample = fieldExample;
        this.methodExample = methodExample;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(constructorExample.value());
        System.out.println(fieldExample.value());
        System.out.println(methodExample.region());
        System.out.println(methodExample.enabled());
    }
}
```

Với import:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
```

Nếu các lớp được lưu ở vị trí được component scan phát hiện và không có nguồn khác ghi đè, kết quả minh họa là:

```text
Hello
4
local
true
```

Ba kiểu viết khác nhau nhưng **cùng giải quyết thuộc tính từ Spring Environment**. Việc chọn kiểu tiêm phụ thuộc vào mục đích thiết kế lớp và vòng đời bean.

## 19. Những sai lầm thường gặp

### 19.1. Quên khai báo bean

Đặt `@Value` lên trường của lớp tự tạo bằng `new` không làm Spring tự tiêm. Hãy để Spring quản lý đối tượng hoặc dùng constructor nhận giá trị rõ ràng.

### 19.2. Viết sai cú pháp placeholder

Sai:

```java
@Value("demo.greeting")
private String greeting;
```

Đây là literal string `demo.greeting`, không phải yêu cầu tra cứu thuộc tính.

Đúng:

```java
@Value("${demo.greeting}")
private String greeting;
```

Với mặc định:

```java
@Value("${demo.greeting:Hello}")
private String greeting;
```

### 19.3. Nhầm tên thuộc tính và giá trị

Nếu tệp YAML viết:

```yaml
demo:
  retry-count: 5
```

nhưng Java yêu cầu `${demo.max-retries}`, đó là hai khóa khác nhau. Hãy bảo đảm tên property được tham chiếu chính xác, ưu tiên dạng kebab-case chuẩn.

### 19.4. Thiếu thuộc tính bắt buộc

`@Value("${demo.required}")` không có mặc định. Nếu không nguồn nào cung cấp giá trị, quá trình tạo bean có thể thất bại. Đừng khắc phục bằng cách thêm một giá trị giả nếu thuộc tính thực sự bắt buộc; tốt hơn là cấp cấu hình cần thiết và thông báo lỗi thiết lập rõ ràng.

### 19.5. Không chuyển đổi được kiểu

Nếu dùng:

```java
@Value("${demo.retry-count}")
private int retryCount;
```

mà cấu hình chứa:

```yaml
demo:
  retry-count: "many"
```

thì `"many"` không phải số nguyên hợp lệ. Cần sửa đầu vào hoặc thay đổi kiểu dữ liệu mong muốn.

### 19.6. Đọc field trước khi Spring tiêm

Với field injection, constructor chạy trước bước tiêm giá trị vào trường. Nếu logic của constructor phụ thuộc vào thuộc tính, hãy chuyển sang constructor injection.

### 19.7. Cho rằng @Value tự làm mới cấu hình

Đổi tệp YAML khi ứng dụng đang chạy không khiến các trường `@Value` của singleton bean mặc định được cập nhật. Khởi động lại hoặc có giải pháp cấu hình động được thiết kế rõ ràng nếu cần.

### 19.8. Cho rằng @Value chỉ đọc application.yml

Giá trị thực tế có thể đến từ đối số dòng lệnh, system properties, biến môi trường, tài liệu theo profile hoặc Config Data khác. Hãy kiểm tra `Environment` khi kết quả không đúng dự đoán.

### 19.9. Cho rằng dùng @Value trên method bất kỳ sẽ chạy mỗi lần gọi

Spring xử lý điểm tiêm method trong vòng đời bean. Annotation không biến một phương thức Java thông thường thành hàm tự tra cứu thuộc tính mỗi lần người dùng gọi.

### 19.10. Dùng @Value cho quá nhiều khóa liên quan

Một lớp có hàng chục `@Value` cho cấu hình HTTP, timeout, kết nối, retries và bảo mật thường khó đọc, khó thay đổi. Khi số thuộc tính tăng, hãy cân nhắc tạo một đối tượng `@ConfigurationProperties` tương ứng.

## 20. Chẩn đoán khi giá trị tiêm không đúng mong đợi

### Bước 1: xác nhận bean được Spring quản lý

Kiểm tra lớp có `@Component` hoặc được đăng ký qua `@Bean`, và nằm trong phạm vi component scan. Nếu đối tượng được tạo thủ công, injection sẽ không diễn ra.

### Bước 2: xem cú pháp @Value

Ví dụ:

```java
@Value("${demo.greeting:Hello}")
```

Phải có `${...}` nếu muốn placeholder. Nếu cần biểu thức SpEL, sử dụng `#{...}`.

### Bước 3: kiểm tra thuộc tính có tồn tại không

Dùng `Environment` để quan sát giá trị có hiệu lực:

```java
@Component
public class ValueInspector implements ApplicationRunner {

    private final Environment environment;

    public ValueInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(environment.getProperty("demo.greeting"));
    }
}
```

Import tương ứng:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
```

Nếu `Environment#getProperty` không có giá trị và `@Value` có mặc định, bean nhận mặc định theo cú pháp placeholder. Nếu `@Value` không có mặc định, việc tạo bean có thể thất bại.

### Bước 4: xét nguồn ưu tiên cao hơn

Thử xem có `--demo.greeting=...` trong lệnh khởi chạy hoặc Run Configuration của IDE không. Kiểm tra Java system properties, biến môi trường và các tệp theo profile.

### Bước 5: xét thứ tự vòng đời

Nếu giá trị null trong constructor của bean có field injection, đây là dấu hiệu quá sớm để đọc trường. Dùng constructor injection hoặc chuyển logic sau bước tiêm.

### Bước 6: kiểm tra kiểu dữ liệu

Nếu bean không tạo được vì chuyển đổi kiểu, xem giá trị thực tế có đúng dạng `int`, `boolean` hay kiểu khác không. Với giá trị số, tránh các chuỗi như `"three"` khi kỳ vọng `int`.

### Bước 7: tránh lộ thông tin nhạy cảm

Chỉ dùng các khóa minh họa không nhạy cảm để in ra log. Không in mật khẩu, token hoặc thông tin riêng tư chỉ nhằm chẩn đoán thứ tự nguồn.

## 21. Bài tập củng cố

### Bài tập A: tính giá trị được tiêm

Cho:

```yaml
demo:
  greeting: "From YAML"
  retry-count: 2
```

Và:

```java
@Component
public class DemoSettings {

    private final String greeting;
    private final int retryCount;

    public DemoSettings(
            @Value("${demo.greeting:Default}") String greeting,
            @Value("${demo.retry-count:3}") int retryCount) {
        this.greeting = greeting;
        this.retryCount = retryCount;
    }

    public String getGreeting() {
        return greeting;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
```

Câu hỏi: nếu chỉ có YAML trên, `getGreeting()` và `getRetryCount()` trả về gì?

Đáp án:

```text
From YAML
2
```

Mặc định `Default` và `3` không được dùng vì YAML đã có thuộc tính.

### Bài tập B: ghi đè bằng dòng lệnh

Vẫn dùng cấu hình trên, khởi chạy:

```bash
java -jar app.jar --demo.greeting=FromCLI --demo.retry-count=8
```

Đáp án:

```text
FromCLI
8
```

Đối số ứng dụng có ưu tiên cao hơn Config Data trong ví dụ.

### Bài tập C: field injection và new

Xét:

```java
@Component
class FeatureFlag {

    @Value("${demo.feature-enabled:true}")
    private boolean enabled;

    boolean isEnabled() {
        return enabled;
    }
}
```

Nếu gọi `new FeatureFlag().isEnabled()` bên ngoài Spring, có chắc kết quả là `true` không?

**Không.** Đối tượng không được Spring tiêm; giá trị mặc định của trường boolean do Java khởi tạo là `false`. Placeholder dự phòng `true` chỉ có tác dụng khi cơ chế tiêm của Spring xử lý điểm tiêm.

### Bài tập D: phân biệt field và constructor

Tại sao đoạn mã sau không nên dùng?

```java
@Component
class EarlyRead {

    @Value("${demo.greeting}")
    private String greeting;

    EarlyRead() {
        System.out.println("Greeting = " + greeting);
    }
}
```

Vì field injection xảy ra sau lúc Java gọi constructor. Nếu cần giá trị ngay trong constructor, truyền nó bằng tham số gắn `@Value`.

### Bài tập E: sửa phương thức tiêm

Bắt đầu với:

```java
@Component
class RegionSettings {

    private String region;
    private int maxItems;
}
```

Hãy viết một phương thức `configure(...)` để Spring tiêm `demo.region` (mặc định `local`) và `demo.max-items` (mặc định `50`).

Một cách làm:

```java
@Autowired
public void configure(
        @Value("${demo.region:local}") String region,
        @Value("${demo.max-items:50}") int maxItems) {
    this.region = region;
    this.maxItems = maxItems;
}
```

Đoạn mã này đặt `@Autowired` lên phương thức và `@Value` trên các tham số.

## 22. Ghi nhớ

- `@Value` giúp tiêm **giá trị đơn** đã được giải quyết từ Spring `Environment` hoặc biểu thức vào một điểm tiêm của bean.
- **Constructor injection** nhận giá trị lúc tạo đối tượng, phù hợp với giá trị bắt buộc và trường `final`; thường là lựa chọn ưu tiên.
- **Field injection** ngắn gọn nhưng phụ thuộc việc Spring xử lý bean sau constructor, khiến kiểm thử và kiểm soát trạng thái khó hơn.
- **Method/setter injection** cho phép Spring gọi phương thức tiêm sau khi tạo đối tượng; có thể dùng `@Autowired` trên phương thức và `@Value` trên các tham số.
- `${key}` là placeholder; `${key:default}` thêm giá trị dự phòng; `#{...}` là biểu thức SpEL.
- Cơ chế tiêm không tự áp dụng cho đối tượng được tạo bằng `new` bên ngoài Spring, và không thích hợp với static field.
- Giá trị tiêm có thể đến từ bất kỳ nguồn thuộc tính nào đang có hiệu lực, không nhất thiết từ `application.yml`.
- `@Value` không mặc định tự làm mới giá trị khi nguồn cấu hình thay đổi lúc ứng dụng đang chạy.
- Với một nhóm cấu hình lớn, lồng nhau hoặc cần validation, nên cân nhắc `@ConfigurationProperties`.
