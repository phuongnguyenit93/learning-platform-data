# Kiểm tra đối tượng lồng nhau bằng @Valid trong Spring Boot @ConfigurationProperties

## Mục tiêu

Trong Spring Boot, **@ConfigurationProperties** cho phép chuyển cấu hình bên ngoài thành một object Java có kiểu dữ liệu. Với cấu hình phẳng, một vài constraint như **@NotBlank** hoặc **@Min** trên các field ở cấp gốc có thể đủ để ngăn ứng dụng khởi động bằng dữ liệu sai. Nhưng cấu hình thực tế thường có nhiều cấp: database → pool, HTTP → timeout, retry → backoff, security → issuer, hoặc một danh sách các endpoint.

Một lỗi phổ biến là chỉ gắn **@Validated** lên class cấu hình gốc, rồi kỳ vọng mọi constraint của object con tự động được kiểm tra trong mọi trường hợp. Với Jakarta Bean Validation, việc kiểm tra **xuyên xuống object lồng nhau (cascaded validation)** được biểu thị bằng **@Valid** đặt trên thành phần tham chiếu đến object con hoặc các phần tử của collection.

Ví dụ cấu hình:

~~~yaml
app:
  client:
    base-url: "https://api.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 10s
      max-connections: 20
~~~

Nếu **client.base-url** rỗng hoặc **http.max-connections** bằng 0, ứng dụng nên báo lỗi cấu hình trước khi phục vụ request. Điều này đòi hỏi cách mô hình hóa đúng các cấp và quy tắc validation rõ ràng.

Sau bài học, người đọc có thể:

- Phân biệt **@ConfigurationProperties**, **@Validated**, **@Valid** và các constraint như **@NotNull**, **@NotBlank**, **@Min**, **@NotEmpty**.
- Đặt **@Valid** đúng ranh giới giữa object gốc và object con, kể cả nhiều cấp lồng nhau.
- Hiểu vì sao **@Valid không có nghĩa bắt buộc object con khác null**.
- Áp dụng validation cho **List**, **Map** và phần tử lồng nhau.
- Thiết kế Java **record (constructor binding)** và **JavaBean (setter binding)** với validation.
- Xử lý giá trị mặc định, nhóm cấu hình vắng mặt, sai kiểu dữ liệu và lỗi liên quan đến nested binding.
- Viết bài kiểm thử xác nhận cấu hình sai làm ứng dụng không khởi động.
- Đọc thông báo bind/validation để tìm đúng đường dẫn property gây lỗi.

Các đoạn code sử dụng phong cách **Spring Boot 3.x**, Jakarta Validation (**jakarta.validation**). Dự án dùng Spring Boot 2.x có khác biệt về package và một số cơ chế constructor binding, nên cần điều chỉnh theo dependency thực tế.

## 1. Tại sao cần validation cho cấu hình?

Giả sử một dịch vụ phụ thuộc endpoint đối tác:

~~~yaml
integration:
  catalog:
    endpoint: ""
    timeout: -1s
    retry:
      max-attempts: 0
~~~

YAML này có thể **đúng cú pháp** và binder có thể chuyển một số giá trị thành kiểu Java tương ứng, nhưng cấu hình không hợp lệ về nghiệp vụ:

- Endpoint trống: dịch vụ không biết gọi đi đâu.
- Timeout âm: không có ý nghĩa với chính sách timeout đang dùng.
- max-attempts = 0: nếu hợp đồng yêu cầu ít nhất một lần thử, giá trị này vi phạm ràng buộc.

Nếu không phát hiện khi khởi động, lỗi có thể chỉ xuất hiện khi chức năng được sử dụng. Với cấu hình quan trọng, nguyên tắc nên là **fail fast**: từ chối startup nếu điều kiện cấu hình bắt buộc không được đáp ứng.

Validation cần diễn đạt trên mô hình cấu hình, không dựa vào việc một dòng YAML “trông có vẻ hợp lý”.

### 1.1. Ba nhóm lỗi cần phân biệt

| Nhóm lỗi | Ví dụ | Tầng xử lý |
| --- | --- | --- |
| Không tìm thấy property | Thiếu integration.catalog.endpoint | Binder/default/validation |
| Chuyển kiểu thất bại | max-attempts: many nhưng Java cần int | Type conversion khi binding |
| Dữ liệu đúng kiểu nhưng sai ràng buộc | max-attempts: 0 với @Min(1) | Bean Validation |

**@Valid không sửa lỗi tên property hoặc sai kiểu.** Nó chỉ làm validation lan xuống những object thích hợp sau khi chúng đã được tạo hoặc được cung cấp cho validation.

## 2. @Validated và @Valid khác nhau ở đâu?

Đây là điểm quan trọng nhất của bài.

**@Validated** là annotation của Spring. Với bean **@ConfigurationProperties**, nó thường được đặt ở class/record gốc để kích hoạt kiểm tra hợp lệ khi cấu hình được bind, với điều kiện dự án có provider Bean Validation phù hợp.

**@Valid** thuộc Jakarta Validation. Nó biểu thị **cascaded validation**: khi validator gặp tham chiếu đến object con, nó tiếp tục xét các constraint trên object đó.

Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid Client client
) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

Nếu app.name rỗng, **@NotBlank** trên gốc có thể báo lỗi. Nếu app.client.base-url rỗng và Client được bind thành object, **@Valid** trên component client cho phép validator đi vào Client để kiểm tra **@NotBlank**.

Một cách nhớ:

~~~text
@Validated ở root
    -> Spring Boot thực hiện validation cho bean cấu hình

@Valid trên ranh giới nested
    -> Validator tiếp tục vào object con

@NotBlank / @NotNull / @Min / @Size...
    -> Quy định giá trị nào là hợp lệ
~~~

### 2.1. @Valid không thay thế @Validated ở root

Chỉ gắn @Valid trên field nhưng không có cơ chế nào kích hoạt validation cho bean cấu hình thì không đủ để bảo đảm dữ liệu bị kiểm tra khi startup.

Trong cách thiết kế phổ biến của Spring Boot:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(@Valid Client client) { ... }
~~~

**@Validated** nêu ý định kiểm tra hợp lệ của bean cấu hình; **@Valid** nêu ranh giới cần đi sâu.

### 2.2. @Validated không thay thế @Valid ở mọi cấp

Nếu object con chứa constraint, hãy gắn **@Valid** tại chỗ tham chiếu đến object con để thể hiện rõ yêu cầu kiểm tra xuyên cấp và bảo đảm hành vi khi cần, kể cả khi chưa có thuộc tính con được khai báo.

Không nên phụ thuộc vào suy đoán rằng “class đã có @Validated, nên tất cả nested object ở mọi cấp luôn được kiểm tra”. Trong các trường hợp nhất định Binder có thể tham gia validation của nested values, nhưng cách diễn đạt rõ ràng và được khuyến nghị cho cascaded validation vẫn là **@Valid**.

### 2.3. @Valid không phải constraint kiểm tra null

Đặt:

~~~java
@Valid Client client
~~~

không có nghĩa **client bắt buộc khác null**. Theo quy tắc Jakarta Validation, cascade thường bỏ qua tham chiếu null.

Muốn object con bắt buộc tồn tại:

~~~java
@Valid @NotNull Client client
~~~

Hai annotation có hai nhiệm vụ:

- **@NotNull**: tham chiếu client phải có object.
- **@Valid**: nếu có object, kiểm tra các constraint bên trong Client.

Đây là khác biệt gây nhiều lỗi cấu hình thực tế nhất.

## 3. Chuẩn bị dependency và đăng ký configuration properties

Để sử dụng Jakarta Bean Validation với Spring Boot 3, dự án cần một provider tương thích, thường được thêm qua starter validation.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Starter này giúp cung cấp phần tích hợp và implementation validator phù hợp theo dependency management của Spring Boot.

### 3.1. Đăng ký bean @ConfigurationProperties

Cách dùng scan:

~~~java
package example;

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

Record cấu hình cần nằm trong package được scan.

Cách đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
class PropertiesRegistration {
}
~~~

Nếu quên đăng ký bean, ứng dụng có thể lỗi vì thiếu dependency khi inject AppProperties. Đó là **lỗi đăng ký bean**, không phải lỗi @Valid.

### 3.2. Package javax.validation và jakarta.validation

Ở dự án Spring Boot 3.x, các annotation Bean Validation thông dụng được import từ **jakarta.validation**:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
~~~

Nhiều ví dụ Spring Boot 2.x cũ dùng **javax.validation**. Copy code sang Boot 3 mà không sửa dependency/package có thể gây lỗi compile hoặc làm annotation không tham gia validation như mong muốn.

Cần phân biệt với **org.springframework.validation.annotation.Validated**, đây vẫn là annotation của Spring.

## 4. Ví dụ hoàn chỉnh: record nhiều cấp

Cấu hình:

~~~yaml
app:
  name: "Order Service"
  client:
    base-url: "https://orders.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 8s
      max-connections: 20
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

Mô hình Java:

~~~java
package example.config;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid @NotNull Client client
) {
    public record Client(
            @NotBlank String baseUrl,
            @Valid @NotNull Http http,
            @Valid @NotNull Retry retry
    ) {}

    public record Http(
            @NotNull Duration connectTimeout,
            @NotNull Duration readTimeout,
            @Min(1) int maxConnections
    ) {}

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

Những đường dẫn cần bind:

| Property canonical | Trường Java | Constraint |
| --- | --- | --- |
| app.name | name | @NotBlank |
| app.client | client | @NotNull + @Valid |
| app.client.base-url | client.baseUrl | @NotBlank |
| app.client.http | client.http | @NotNull + @Valid |
| app.client.http.connect-timeout | http.connectTimeout | @NotNull |
| app.client.http.read-timeout | http.readTimeout | @NotNull |
| app.client.http.max-connections | http.maxConnections | @Min(1) |
| app.client.retry | client.retry | @NotNull + @Valid |
| app.client.retry.max-attempts | retry.maxAttempts | @Min(1) |
| app.client.retry.backoff | retry.backoff | @NotNull |

Để validate được đến **maxConnections**, có thể hình dung các bước:

~~~text
AppProperties (@Validated)
  |
  +-- name (@NotBlank)
  |
  +-- client (@NotNull + @Valid)
        |
        +-- baseUrl (@NotBlank)
        |
        +-- http (@NotNull + @Valid)
        |     |
        |     +-- connectTimeout (@NotNull)
        |     +-- readTimeout (@NotNull)
        |     +-- maxConnections (@Min(1))
        |
        +-- retry (@NotNull + @Valid)
              |
              +-- maxAttempts (@Min(1))
              +-- backoff (@NotNull)
~~~

**@Valid phải xuất hiện tại từng ranh giới cần cascade**, từ AppProperties vào Client và từ Client vào Http/Retry. Nếu bỏ @Valid tại một ranh giới, không nên trông đợi các constraint sâu hơn được thực thi theo hợp đồng cascade của Jakarta Validation.

## 5. Thử cấu hình sai và hiểu lỗi

Giả sử thay YAML thành:

~~~yaml
app:
  name: "Order Service"
  client:
    base-url: ""
    http:
      connect-timeout: 2s
      read-timeout: 8s
      max-connections: 0
    retry:
      max-attempts: 0
      backoff: 500ms
~~~

Ba giá trị đáng chú ý:

- **app.client.base-url = ""** vi phạm **@NotBlank**.
- **app.client.http.max-connections = 0** vi phạm **@Min(1)**.
- **app.client.retry.max-attempts = 0** vi phạm **@Min(1)**.

Khi Spring Boot bind và validate AppProperties, ứng dụng có thể thất bại khi khởi động với thông tin về các field không hợp lệ, chẳng hạn đường dẫn và constraint tương ứng. Nội dung thông báo cụ thể tùy phiên bản Boot, validator và cách khởi tạo bean.

Một lỗi khởi động trong trường hợp này **là hành vi mong đợi**. Nó ngăn hệ thống chạy với endpoint rỗng hoặc chính sách retry không đúng.

### 5.1. Tại sao phải phân biệt lỗi validation với lỗi conversion?

Nếu cấu hình là:

~~~yaml
app:
  client:
    http:
      max-connections: "many"
~~~

thì giá trị **many** không thể chuyển thành int. Lỗi conversion có thể xảy ra trước khi validator kiểm tra **@Min(1)**. Thêm @Valid không biến một chuỗi chữ thành số.

Ngược lại, với **max-connections: 0**, giá trị đã là một int hợp lệ về kiểu, nhưng không đáp ứng constraint nghiệp vụ. Khi debug, cần đọc **root cause** và xác định lỗi thuộc bước nào.

## 6. Nhánh cấu hình bị thiếu: @Valid và @NotNull

Một trường hợp đặc biệt quan trọng:

~~~yaml
app:
  name: "Order Service"
~~~

Không có **app.client**.

Nếu khai báo:

~~~java
@Valid Client client
~~~

thì khi client là null, **@Valid không tự báo lỗi null**. Validator chỉ có nhiệm vụ đi sâu khi có object để kiểm tra.

Nếu yêu cầu client bắt buộc:

~~~java
@Valid @NotNull Client client
~~~

thì **@NotNull** phát hiện nhánh client không có object sau binding; **@Valid** xử lý constraint của Client khi object tồn tại.

### 6.1. Khi nhánh có object nhưng thiếu trường con

Ví dụ:

~~~yaml
app:
  name: "Order Service"
  client:
    http:
      max-connections: 5
~~~

Trong thiết kế ở phần 4, binder có thể tạo Client và Http, nhưng **baseUrl** có thể null và **retry** có thể null.

Các constraint có vai trò:

~~~text
client.baseUrl -> @NotBlank bắt lỗi null/rỗng
client.retry   -> @NotNull bắt lỗi thiếu object Retry
client.http    -> @Valid đưa validator xuống Http
~~~

**Mục tiêu validation phải được nêu rõ ở đúng cấp**: thiếu một object và thiếu một field con là hai lỗi khác nhau.

### 6.2. Nếu nhóm con là tùy chọn

Không phải mọi nested object đều bắt buộc. Ví dụ một cấu hình exporter có thể chỉ tồn tại khi feature được bật.

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        boolean exporterEnabled,
        @Valid Exporter exporter
) {
    public record Exporter(
            @NotBlank String endpoint
    ) {}
}
~~~

Ở đây **exporter** được cascade nếu có object, nhưng bản thân nó không bắt buộc khác null. Nếu nghiệp vụ yêu cầu “khi exporterEnabled=true thì exporter phải có endpoint”, chỉ @Valid và @NotBlank chưa diễn đạt đủ quan hệ xuyên trường.

Khi đó cần một **constraint mức object**, một phương thức kiểm tra invariant hoặc logic kiểm tra cấu hình phù hợp. Không nên thêm @NotNull vô điều kiện nếu exporter thực sự được phép vắng mặt khi tính năng tắt.

## 7. Khi không có thuộc tính con nào: vì sao @Valid quan trọng?

Spring Boot có các quy tắc riêng về việc bind và validate nested properties. Một chi tiết được nhấn mạnh trong tài liệu của Spring Boot là: **để bảo đảm validation của nested properties được kích hoạt ngay cả khi không có property con nào được tìm thấy, cần đánh dấu field nested bằng @Valid**.

Ví dụ JavaBean:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private final Security security = new Security();

    @Valid
    public Security getSecurity() {
        return security;
    }

    public static class Security {
        @NotBlank
        private String issuer;

        public String getIssuer() {
            return issuer;
        }

        public void setIssuer(String issuer) {
            this.issuer = issuer;
        }
    }
}
~~~

Với class JavaBean có nested Security được khởi tạo sẵn, annotation @Valid trên getter giúp diễn đạt ý định validation đối tượng đó, kể cả khi cấu hình không có **app.security.issuer**.

Trong thực tế, đặt @Valid trên field/getter/record component phụ thuộc kiểu binding và cách framework nhận diện property. Nên thống nhất vị trí annotation của dự án, bảo đảm đúng Bean Validation metadata và kiểm thử một trường hợp thiếu toàn bộ nhánh.

### 7.1. @Valid không có phép màu tạo object

Nếu security ban đầu là null, chỉ @Valid không nhất thiết tạo ra Security. Vấn đề **tạo nested object** thuộc binder, constructor, setter hoặc default, không thuộc @Valid.

Để bắt buộc object tồn tại, dùng @NotNull; để tạo object mặc định, dùng cơ chế constructor binding hoặc khởi tạo JavaBean phù hợp.

### 7.2. Không phụ thuộc vào primitive default

Một nested record có:

~~~java
public record Retry(int maxAttempts) {}
~~~

Khi property vắng mặt, giá trị nguyên thủy có thể về 0 theo cách constructor/binding tương ứng. **@Min(1)** giúp phát hiện 0 nếu validation tới được Retry. Nhưng nếu cả Retry object là null và không có @NotNull ở cấp cha, constraint sâu có thể không được đánh giá.

Với thuộc tính bắt buộc phải phân biệt “không khai báo” và “khai báo bằng 0”, cân nhắc **Integer** kết hợp **@NotNull** và **@Min(1)** thay vì chỉ primitive int.

## 8. JavaBean binding: @Valid trên nested field/getter

Không phải dự án nào cũng dùng Java record. Có thể xây JavaBean có setter:

~~~java
package example.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Valid
    @NotNull
    private Http http = new Http();

    public Http getHttp() {
        return http;
    }

    public void setHttp(Http http) {
        this.http = http;
    }

    public static class Http {
        @NotBlank
        private String baseUrl;

        @NotNull
        private Duration timeout;

        @Min(1)
        private int maxConnections;

        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

        public Duration getTimeout() { return timeout; }
        public void setTimeout(Duration timeout) { this.timeout = timeout; }

        public int getMaxConnections() { return maxConnections; }
        public void setMaxConnections(int maxConnections) {
            this.maxConnections = maxConnections;
        }
    }
}
~~~

YAML:

~~~yaml
app:
  http:
    base-url: "https://api.example.test"
    timeout: 5s
    max-connections: 20
~~~

JavaBean binding tạo/cập nhật các property bằng getter và setter theo hỗ trợ của binder. Sau đó Bean Validation kiểm tra root và cascade vào Http qua **@Valid**.

### 8.1. Khởi tạo nested object sẵn

Ví dụ:

~~~java
private Http http = new Http();
~~~

cung cấp một object Http kể cả khi app.http hoàn toàn vắng mặt. Điều này hữu ích khi muốn **validation phát hiện trường bắt buộc bị thiếu bên trong**, với @Valid và constraint phù hợp.

Nếu thay bằng:

~~~java
private Http http;
~~~

thì khi app.http không có dữ liệu, field có thể vẫn null. Khi đó **@Valid** bỏ qua null và **@NotNull** là ràng buộc phát hiện nhánh bị thiếu.

Việc có setter hay khởi tạo sẵn còn tùy thiết kế JavaBean; không nên trộn logic tạo object với ý nghĩa của @Valid.

### 8.2. Có thể đặt @Valid trên getter?

Jakarta Bean Validation hỗ trợ metadata của property theo field hoặc getter. Ví dụ:

~~~java
@Valid
public Http getHttp() {
    return http;
}
~~~

có thể biểu diễn cascaded validation qua getter. Nhưng đừng gắn constraint vào cả field và getter của cùng property mà không có chủ đích, vì có thể khiến validation kiểm tra nhiều lần hoặc tạo metadata khó theo dõi.

Với một class JavaBean, lựa chọn vị trí annotation nhất quán giúp người đọc dễ biết ràng buộc đang áp dụng cho property nào.

## 9. Record và constructor binding: @Valid trên component

Trong Spring Boot 3, Java record thường được dùng cho @ConfigurationProperties thông qua constructor binding.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid @NotNull Database database
) {
    public record Database(
            @NotBlank String url,
            @NotBlank String username
    ) {}
}
~~~

Ở đây **database** là component của record gốc. Khi binder tạo AppProperties, Jakarta Validation có thể đọc các constraint được gắn vào component/field/accessor của record theo metadata hợp lệ.

Không cần setter cho record. @Valid **không phải một thủ thuật thay setter**; nó chỉ yêu cầu validator đi sâu vào Database sau khi binder đã tạo object.

### 9.1. Registration phù hợp với constructor-bound properties

Cách đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties được khuyến nghị cho constructor-bound record.

Không nên gắn đồng thời @Component vào record rồi giả định IoC constructor injection sẽ tự trở thành constructor binding. Hai cơ chế có ngữ nghĩa khác nhau: một bên bind **giá trị thuộc tính**, bên kia resolve **bean dependency**.

### 9.2. @DefaultValue và nested object

Một số phiên bản Spring Boot hỗ trợ **@DefaultValue** trên constructor parameter/record component.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @DefaultValue Http http
) {
    public record Http(
            @DefaultValue("5s") java.time.Duration timeout
    ) {}
}
~~~

Một **@DefaultValue rỗng** trên nested component có thể yêu cầu binder tạo nested instance ngay cả khi không có property bên dưới, để default và validation của object con được áp dụng. Hành vi cụ thể phụ thuộc kiểu constructor, phiên bản Spring Boot và khả năng chuyển đổi.

Nếu object thật sự bắt buộc được người vận hành cấu hình, tránh tạo default vô điều kiện chỉ để ứng dụng khởi động được. Việc tạo default có thể khiến ràng buộc “phải khai báo” bị vô hiệu hóa về mặt nghiệp vụ.

## 10. @Valid qua nhiều cấp: không bỏ một mắt xích

Một cấu hình có ba cấp:

~~~text
app
  -> client
      -> http
          -> pool
              -> max-size
~~~

Mô hình:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @NotNull Client client
) {
    public record Client(
            @Valid @NotNull Http http
    ) {}

    public record Http(
            @Valid @NotNull Pool pool
    ) {}

    public record Pool(
            @Min(1) int maxSize
    ) {}
}
~~~

Nếu **app.client.http.pool.max-size=0**, cần cascade:

~~~text
AppProperties
 -> client (@Valid)
 -> http (@Valid)
 -> pool (@Valid)
 -> maxSize (@Min(1))
~~~

Một lỗi dễ mắc là:

~~~java
public record Http(Pool pool) {}
~~~

mà không có @Valid trên pool, sau đó nghĩ rằng @Min trong Pool đương nhiên được kiểm tra chỉ vì root có @Validated. Với cascaded validation, mỗi ranh giới object được chọn để đi sâu cần diễn đạt.

### 10.1. @NotNull ở cấp nào?

Đặt **@NotNull** ở từng nested object bắt buộc, không chỉ ở root.

- Nếu client bắt buộc: @NotNull Client client.
- Nếu http bắt buộc bên trong Client: @NotNull Http http.
- Nếu pool bắt buộc bên trong Http: @NotNull Pool pool.

Khi một nhánh tùy chọn, không thêm @NotNull vô điều kiện; chỉ dùng @Valid để validate nếu có instance hoặc định nghĩa một ràng buộc điều kiện thích hợp.

## 11. @Valid đối với List các object

Một nhóm cấu hình có thể có nhiều endpoint:

~~~yaml
app:
  endpoints:
    - name: primary
      url: "https://api-a.example.test"
      timeout: 3s
    - name: backup
      url: ""
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record EndpointProperties(
        @NotEmpty List<@Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotBlank String url,
            @NotNull Duration timeout
    ) {}
}
~~~

Có hai kiểu ràng buộc:

- **@NotEmpty** trên List: danh sách phải có ít nhất một phần tử.
- **@Valid** trên kiểu phần tử Endpoint: mỗi Endpoint không null được kiểm tra các constraint của nó.

Nếu endpoint thứ hai có **url=""**, ràng buộc **@NotBlank** trong Endpoint có thể tạo violation với đường dẫn tương đương **endpoints[1].url**, tùy cách provider biểu diễn property path.

### 11.1. @Valid List<Endpoint> hay List<@Valid Endpoint>?

Có thể thấy hai mẫu:

~~~java
@Valid
private List<Endpoint> endpoints;
~~~

và:

~~~java
private List<@Valid Endpoint> endpoints;
~~~

Jakarta Validation hỗ trợ cascaded validation của container elements ở những phiên bản chuẩn phù hợp. **List<@Valid Endpoint>** biểu đạt trực tiếp yêu cầu validate từng phần tử. **@Valid** trên collection property cũng là một mẫu được sử dụng, theo metadata và container value extractor của provider.

Với code mới, hãy chọn một mẫu rõ ràng, thống nhất và được hỗ trợ bởi phiên bản validator. Không nên đặt cả hai kiểu trùng lặp chỉ để “chắc ăn” nếu không có lý do.

### 11.2. Nếu List chứa null

**@Valid** không tự cấm một phần tử null trong danh sách. Nếu phần tử bắt buộc khác null, có thể dùng constraint trên container element:

~~~java
@NotEmpty
List<@NotNull @Valid Endpoint> endpoints
~~~

Khi đó:

- @NotEmpty kiểm tra có phần tử.
- @NotNull trên element kiểm tra từng phần tử khác null.
- @Valid trên element kiểm tra nội dung từng Endpoint.

Đây là cách phân biệt validation của **container** với validation của **phần tử**.

## 12. @Valid đối với Map có value là object

Giả sử cấu hình vùng:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 4s
    europe:
      endpoint: ""
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record RegionProperties(
        @NotEmpty Map<@NotBlank String, @NotNull @Valid Region> regions
) {
    public record Region(
            @NotBlank String endpoint,
            @NotNull Duration timeout
    ) {}
}
~~~

Ở đây:

- @NotEmpty trên Map bảo đảm có ít nhất một entry.
- @NotBlank trên key String yêu cầu key không rỗng.
- @NotNull trên value bảo đảm mỗi value có object Region.
- @Valid trên value cho phép kiểm tra endpoint và timeout của từng Region.

**@Valid đặt trên value** khác với @Valid trên key, và khác với ràng buộc số entry. Mỗi tầng có mục đích riêng.

### 12.1. Chú ý Map key có dấu chấm

Với key có dấu chấm như **tenant.eu**, binder có thể cần bracket notation để giữ key nguyên vẹn:

~~~yaml
app:
  regions:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
      timeout: 4s
~~~

Việc dùng @Valid không chữa lỗi binder tách key thành nested path ngoài ý muốn. **Tên property và key Map** phải được bind đúng trước khi validator kiểm tra giá trị.

### 12.2. Validation không bảo đảm tính duy nhất của các key theo nghiệp vụ

Map theo định nghĩa có key duy nhất tại một thời điểm theo equals/hashCode, nhưng validator không tự kiểm tra một quy tắc nghiệp vụ như “region phải nằm trong tập đã đăng ký” hoặc “endpoint không được trùng giữa hai region”.

Những quy tắc này có thể cần custom constraint ở cấp Map hoặc class cấu hình.

## 13. Nested object bên trong List rồi bên trong Map

Có thể kết hợp nhiều tầng:

~~~yaml
app:
  tenants:
    - name: alpha
      routes:
        users:
          path: "/users"
          timeout: 2s
        orders:
          path: "/orders"
          timeout: 3s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        @NotEmpty List<@Valid Tenant> tenants
) {
    public record Tenant(
            @NotBlank String name,
            @NotEmpty Map<@NotBlank String, @Valid Route> routes
    ) {}

    public record Route(
            @NotBlank String path,
            @NotNull Duration timeout
    ) {}
}
~~~

Quy trình:

~~~text
TenantProperties
  -> tenants[0] (List<@Valid Tenant>)
       -> name (@NotBlank)
       -> routes (Map<String, @Valid Route>)
            -> users (Route)
                 -> path (@NotBlank)
                 -> timeout (@NotNull)
            -> orders (Route)
                 -> path (@NotBlank)
                 -> timeout (@NotNull)
~~~

Nếu **orders.path** rỗng, constraint thuộc Route. Nếu routes là Map rỗng, constraint **@NotEmpty** thuộc Tenant.routes. Nếu tenants không có phần tử nào, constraint **@NotEmpty** thuộc TenantProperties.tenants.

Cách này giúp đặt thông báo lỗi tại cấp đúng hơn so với việc chỉ có một phương thức kiểm tra tổng quát trả về false.

## 14. Các constraint thường dùng trong nested configuration

Một bộ constraint hữu ích:

| Constraint | Áp dụng cho | Ý nghĩa |
| --- | --- | --- |
| @NotNull | Object, wrapper type, String, collection | Không được null |
| @NotBlank | String / CharSequence phù hợp | Không null, không rỗng/toàn khoảng trắng |
| @NotEmpty | Collection, Map, String, array phù hợp | Có ít nhất một phần tử/ký tự |
| @Min(n) | Kiểu số nguyên được hỗ trợ | Giá trị ít nhất n |
| @Max(n) | Kiểu số nguyên được hỗ trợ | Giá trị tối đa n |
| @Positive | Kiểu số được hỗ trợ | Phải lớn hơn 0 |
| @Size(min,max) | String, collection, Map, array | Kiểm tra độ dài/kích thước |
| @Pattern(regexp=...) | String / CharSequence | Khớp biểu thức chính quy |
| @Valid | Object hoặc container elements | Cascade sang object con |
| @AssertTrue | boolean property/method | Giá trị hoặc điều kiện phải đúng |

Không dùng @NotBlank cho **Duration**, **Integer** hoặc nested object vì constraint này dành cho dữ liệu dạng ký tự.

Không dùng @Min trực tiếp lên Duration rồi mặc nhiên cho rằng validator hiểu đó là số mili giây. **@Min** được định nghĩa cho những kiểu số được hỗ trợ, không phải một ràng buộc Duration phổ quát.

### 14.1. Ràng buộc số lượng và các cấp collection

Ví dụ:

~~~java
@Size(min = 1, max = 10)
List<@Valid Endpoint> endpoints
~~~

Ràng buộc kích thước kiểm tra số phần tử List, còn @Valid kiểm tra nội dung từng Endpoint. Một List có 2 Endpoint nhưng URL của một Endpoint rỗng vẫn vi phạm constraint ở cấp phần tử.

### 14.2. Regex với @Pattern

Ví dụ kiểm tra tên cụm máy chỉ gồm chữ và số:

~~~java
@Pattern(regexp = "[a-zA-Z0-9]+")
String clusterName
~~~

Đây là một ràng buộc đơn giản. Với URL, URI hoặc các identifier phức tạp, nên chọn kiểu Java có conversion phù hợp và kiểm tra nghiệp vụ thay vì dùng một regex quá dài hoặc dễ sai.

### 14.3. Constraints cần provider validation

Việc import thành công các annotation không đủ bảo đảm ứng dụng có một Jakarta Bean Validation provider ở runtime. Đối với ứng dụng Boot, thường bổ sung **spring-boot-starter-validation** và khởi động qua cấu hình auto-configuration phù hợp.

Khi test thấy dữ liệu sai vẫn được chấp nhận, phải kiểm tra cả **validation provider**, **@Validated ở root**, **@Valid trên ranh giới nested**, và **class cấu hình có thực sự được bind thành bean**.

## 15. Duration cần ràng buộc như thế nào?

Timeout, interval và backoff thường dùng **java.time.Duration**:

~~~java
public record Http(Duration readTimeout) {}
~~~

Ví dụ YAML:

~~~yaml
app:
  http:
    read-timeout: 0s
~~~

Nếu nghiệp vụ yêu cầu timeout dương, chỉ @NotNull chưa đủ vì Duration.ZERO không phải null. Mặt khác, không áp dụng @Min(1) vào Duration như int.

Có thể đặt một ràng buộc tùy chỉnh hoặc invariant trong Java:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record Http(@NotNull Duration readTimeout) {

    @AssertTrue(message = "readTimeout must be positive")
    public boolean isReadTimeoutPositive() {
        return readTimeout != null
                && !readTimeout.isZero()
                && !readTimeout.isNegative();
    }
}
~~~

Với object Http được validate qua @Valid, ràng buộc @AssertTrue trên property **readTimeoutPositive** kiểm tra Duration phải lớn hơn 0.

### 15.1. @AssertTrue có giới hạn

Một phương thức @AssertTrue phù hợp với logic ngắn, trả boolean. Nhưng nếu class chứa nhiều điều kiện liên quan đến nhau, dùng custom class-level constraint hoặc một validator riêng có thể tốt hơn.

Đừng đặt trong phương thức validation các tác động phụ như gọi database, gửi HTTP request hoặc ghi file. Validation cấu hình cần có khả năng chạy nhanh và lặp lại an toàn khi startup.

### 15.2. Trường hợp Duration là null

Ví dụ trên có @NotNull và kiểm tra dương. Khi readTimeout=null, có thể có nhiều violation liên quan. Đó không hẳn là lỗi; nhưng nếu muốn thông báo gọn, có thể thiết kế constraint riêng xử lý null theo cách thống nhất.

Nếu một giá trị “không khai báo” được phép thì đừng gắn @NotNull chỉ vì thấy kiểu Duration; hãy quy định ý nghĩa null và default ở chính sách cấu hình.

## 16. Ràng buộc giữa các trường của object nested

Không phải điều kiện nào cũng là ràng buộc của một field độc lập.

Ví dụ:

~~~yaml
app:
  retry:
    enabled: true
    max-attempts: 0
~~~

Yêu cầu nghiệp vụ: nếu enabled=true thì max-attempts phải ít nhất 1; nếu enabled=false thì có thể là 0.

Record:

~~~java
import jakarta.validation.constraints.AssertTrue;

public record Retry(
        boolean enabled,
        int maxAttempts
) {
    @AssertTrue(message =
            "maxAttempts must be >= 1 when retry is enabled")
    public boolean isRetryConfigurationValid() {
        return !enabled || maxAttempts >= 1;
    }
}
~~~

Ràng buộc này thuộc **cả đối tượng Retry**, dù được biểu diễn qua một boolean property. Để nó được kiểm tra, object Retry phải nằm trên đường đi được validation cascade hoặc được validate trực tiếp.

### 16.1. Khi nào nên tạo custom constraint?

Nếu điều kiện phức tạp hơn:

- minConnections không vượt maxConnections.
- enabled=true yêu cầu endpoint tồn tại.
- Một danh sách server phải có ít nhất một node primary.
- Các region không được sử dụng cùng một identifier.
- Backoff phải dương và nhỏ hơn request timeout.
- Các trường xác thực phải đi cùng nhau.

Khi đó có thể tạo annotation class-level và **ConstraintValidator**. Cách này tăng code nhưng giúp tách hợp đồng validation khỏi cơ chế bind và có thể test độc lập.

### 16.2. Đừng thay validation bằng điều kiện ở lần request đầu tiên

Nếu một trạng thái cấu hình được biết là sai ngay khi startup, nên từ chối tạo ứng dụng thay vì để lỗi đến khi khách hàng gọi endpoint. Điều này đặc biệt quan trọng với thông số liên quan an toàn, giới hạn tài nguyên và kết nối bắt buộc.

## 17. Có cần @Valid khi object con đã có @Validated?

Một cách viết dễ gây nhầm:

~~~java
@Validated
public record Client(
        @NotBlank String baseUrl
) {}
~~~

rồi ở root:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {}
~~~

Nếu chỉ vì Client có @Validated mà nghĩ validation chắc chắn tự nhảy từ AppProperties xuống Client trong mọi tình huống, đây là suy luận không vững.

Cascaded validation của Jakarta Bean Validation được thể hiện bằng **@Valid** trên tham chiếu ở root:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {}
~~~

Và nếu client bắt buộc:

~~~java
@Valid @NotNull Client client
~~~

**Vị trí gọi validator và đường đi cascade** là hai khái niệm khác nhau. Một object con có constraint không tự bảo đảm nó được validation từ object cha, trừ khi cơ chế tương ứng thực sự kiểm tra nó.

## 18. @NestedConfigurationProperty không phải @Valid

Spring Boot có annotation **@NestedConfigurationProperty** để hỗ trợ thông tin metadata về cấu hình lồng nhau trong một số tình huống.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

public class ClientProperties {
    @NestedConfigurationProperty
    private HttpOptions http;
}
~~~

Annotation này **không thay thế**:

~~~java
@Valid
private HttpOptions http;
~~~

Khác biệt:

| Annotation | Trách nhiệm chính |
| --- | --- |
| @NestedConfigurationProperty | Giúp mô tả cấu trúc nested cho configuration metadata/tooling |
| @Valid | Cho validator đi sâu vào object con |
| @NotNull | Bắt buộc tham chiếu object tồn tại |
| @Validated | Kích hoạt/cấu hình cơ chế validation ở điểm tích hợp Spring |

Một field có thể dùng cả @NestedConfigurationProperty và @Valid vì phục vụ hai mục đích, nhưng không nên thêm annotation metadata để chữa lỗi validation hoặc ngược lại.

## 19. @Valid với collection bất biến hoặc Java record

Collection bất biến và cascaded validation là các khái niệm độc lập.

Ví dụ record:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@Valid Server> servers
) {
    public AppProperties {
        servers = servers == null
                ? List.of()
                : List.copyOf(servers);
    }

    public record Server(
            @jakarta.validation.constraints.NotBlank String host,
            @jakarta.validation.constraints.Min(1) int port
    ) {}
}
~~~

Bộ binder có thể đưa dữ liệu List đến constructor. Compact constructor tạo snapshot unmodifiable bằng List.copyOf. Validation sau đó vẫn có thể kiểm tra từng Server thông qua @Valid trên phần tử.

### 19.1. Immutable List không làm các object con tự hợp lệ

**List.copyOf** ngăn thêm/bớt phần tử, nhưng không kiểm tra host có rỗng hoặc port bằng 0. Đó là trách nhiệm của constraints.

Nếu các phần tử Server là mutable object, việc copy List cũng không biến chúng thành immutable; dữ liệu bên trong phần tử vẫn cần hợp đồng riêng.

### 19.2. List.copyOf có thể thất bại trước validation

List.copyOf không chấp nhận phần tử null. Nếu List chứa null, compact constructor có thể ném exception trước khi @NotNull trên element được báo theo cách mong muốn.

Nếu cần thông báo validation nhất quán cho phần tử null, cân nhắc cách normalize/copy không làm mất cơ hội validation, hoặc dùng constructor invariant có thông báo cụ thể. Không đặt một bước defensive copy thiếu cân nhắc rồi nghĩ mọi lỗi sẽ thành ConstraintViolation.

## 20. Validation của Map và List từ nhiều PropertySource

Giả sử file nền có:

~~~yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
~~~

File prod:

~~~yaml
app:
  servers:
    - host: production.example.test
      port: 0
~~~

Trong cơ chế binding danh sách thông thường của Spring Boot, **List từ nguồn ưu tiên cao thường thay thế List ở nguồn thấp**. Khi profile prod có hiệu lực, binder có thể nhận danh sách chỉ gồm production.example.test với port=0, rồi validator phát hiện **@Min(1)** trên Server.port.

Validation **không tự merge** phần tử từ file nền để lấy port 8080 hoặc 8081. Nó kiểm tra **object cuối cùng được bind**.

### 20.1. Map thường kết hợp key, List thường thay thế

Ví dụ map:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
~~~

~~~yaml
# application-prod.yml
app:
  labels:
    region: asia
    tier: critical
~~~

Binder có thể tạo Map cuối với owner=platform, region=asia, tier=critical.

Nếu Map value là nested object có @Valid, những constraint được áp dụng trên **giá trị sau khi binder giải quyết precedence**, không trực tiếp trên từng dòng ở từng file nguồn.

Do đó, trong troubleshooting cần tách:

- Sai tên/cấp property.
- Nguồn cấu hình nào thắng.
- Collection cuối cùng có cấu trúc gì.
- Constraint nào bị vi phạm sau binding.

## 21. Việc dùng @Valid không giải quyết chuyện null trong List/Map

Xét:

~~~java
List<@Valid Endpoint> endpoints;
~~~

Nó có nghĩa mỗi Endpoint không-null sẽ được cascade, không tự cấm List null, List rỗng hoặc phần tử null.

Muốn ràng buộc nhiều cấp:

~~~java
@NotEmpty
List<@NotNull @Valid Endpoint> endpoints;
~~~

Với Map:

~~~java
@NotEmpty
Map<@NotBlank String, @NotNull @Valid Endpoint> routes;
~~~

Ý nghĩa của từng constraint là khác nhau. Một giải pháp chuẩn là **định nghĩa hợp đồng về container, key/value và object con theo từng lớp**, thay vì chỉ thêm @Valid ở mọi nơi.

### 21.1. Khi một phần tử tùy chọn

Nếu nghiệp vụ cho phép một phần tử null như một placeholder, không thêm @NotNull lên element. Nhưng hãy xác định rõ các service sử dụng collection có xử lý null hay không. Với cấu hình vận hành, phần tử null thường là dấu hiệu thiết kế chưa rõ ràng; dùng cấu trúc dữ liệu biểu diễn trạng thái tùy chọn rõ hơn sẽ dễ bảo trì.

## 22. Validation và default: không được nhầm

Có ba nguồn giá trị mặc định thường gặp:

1. Giá trị được khai báo trong application.yml nền.
2. Giá trị mặc định được Spring Boot hỗ trợ qua constructor binding, như **@DefaultValue**.
3. Giá trị mặc định do JavaBean field initializer hoặc record constructor cung cấp.

Ví dụ:

~~~yaml
app:
  http:
    timeout: 5s
~~~

Nếu profile prod không override timeout, giá trị 5s có thể được binder nhận và sau đó validation. Không cần @Valid phải “tạo ra” giá trị 5s.

Nếu một constructor đưa vào Duration.ofSeconds(5) khi timeout null, kết quả validation là object với timeout 5s, không phải null. Khi đó @NotNull sẽ không báo lỗi thiếu cấu hình ban đầu, bởi vì default đã thay thế.

### 22.1. Default có thể che yêu cầu cấu hình bắt buộc

Nếu URL backend phải được cấp riêng trong production mà JavaBean lại có:

~~~java
private String baseUrl = "http://localhost:8080";
~~~

và @NotBlank trên baseUrl, validation sẽ thấy String không rỗng nên có thể pass, dù người vận hành quên cấu hình URL thật.

Nếu một giá trị bắt buộc được đặt từ môi trường, cân nhắc **không cung cấp default có vẻ hợp lệ**, rồi dùng @NotBlank/@NotNull để phát hiện thiếu.

### 22.2. Default của nested object không đồng nghĩa default các child

Tạo:

~~~java
private Http http = new Http();
~~~

giúp có object Http, nhưng các field bên trong như timeout và endpoint vẫn có thể null hoặc bằng 0. Validation với @Valid mới giúp kiểm tra các constraint của Http.

Điều này khác với việc tạo một Http đã có đầy đủ giá trị default hợp lệ. Hãy phân biệt thiết kế object tồn tại với chính sách default cho các field của nó.

## 23. Không dùng @NotNull cho primitive để phát hiện thiếu key

Java primitive **int**, **long**, **boolean** không thể null.

Ví dụ:

~~~java
public record Pool(
        @NotNull int maxConnections
) {}
~~~

@jakarta.validation.constraints.NotNull không có ý nghĩa phát hiện một int vắng mặt theo cách thường mong muốn, bởi vì đối tượng primitive khi được cung cấp cho validator không có trạng thái null.

Nên dùng:

~~~java
public record Pool(
        @Min(1) int maxConnections
) {}
~~~

nếu cần số dương, hoặc:

~~~java
public record Pool(
        @NotNull @Min(1) Integer maxConnections
) {}
~~~

nếu thực sự muốn phân biệt **không có giá trị** với giá trị **0** ở kiểu wrapper.

### 23.1. Boolean bắt buộc phải khai báo

Nếu cần phân biệt “cấu hình chưa khai báo” với **false**, dùng:

~~~java
@NotNull Boolean enabled
~~~

thay vì chỉ:

~~~java
boolean enabled
~~~

Với primitive boolean, false có thể là giá trị mặc định không được phân biệt với false được cấp chủ động. Mô hình Java phải phản ánh đúng hợp đồng của cấu hình.

## 24. Không dùng @Valid để phát hiện sai tiền tố hoặc sai thụt lề YAML

Bean chờ:

~~~text
app.client.http.max-connections
~~~

Nhưng YAML khai báo:

~~~yaml
app:
  client:
    max-connections: 20
~~~

Đường dẫn thực là:

~~~text
app.client.max-connections
~~~

Nếu nested Http không có dữ liệu, Http có thể null hoặc được khởi tạo với các default. Khi đó validation có thể báo @NotNull Http hoặc @Min maxConnections, tùy thiết kế.

**Nguyên nhân gốc vẫn là sai đường dẫn.** Không sửa bằng cách thêm một annotation tùy ý mà không sửa cấu trúc YAML.

Một cách xử lý bài bản:

1. Viết prefix của root.
2. Viết tên từng nested component.
3. Ghép thành đường dẫn canonical.
4. So sánh với YAML mapping.
5. Đọc PropertySource cuối cùng và dữ liệu binder nhận.

## 25. Xem thông báo lỗi của Spring Boot

Khi bind/validation thất bại, Spring Boot thường báo những thông tin như:

~~~text
Failed to bind properties under 'app.client.http'
Property: app.client.http.max-connections
Value: 0
Reason: must be greater than or equal to 1
~~~

Đây là **mẫu minh họa về cấu trúc thông tin**, không phải một log cố định cho mọi phiên bản. Nội dung thực có thể có nhiều lớp exception như BindException, BindValidationException hoặc BeanCreationException, và thông tin về nguồn file nếu được nạp kèm origin metadata.

Với object nhiều cấp, hãy tìm **property path đầy đủ**, không chỉ tên field cuối cùng. Hai field **retry.maxAttempts** và **client.maxAttempts** có thể dùng cùng tên ngắn nhưng thuộc hai nhánh khác nhau.

### 25.1. Đọc root cause

Một lỗi ApplicationContext không khởi động có thể bị bọc trong nhiều exception. Khi phân tích, xác định:

- Có lỗi parse YAML không?
- Có lỗi conversion trước validation không?
- Validator có báo constraint nào không?
- Có lỗi tạo nested object bằng constructor không?
- Có thiếu bean configuration properties vì chưa scan/enable không?

Chỉ thêm @Valid khi lỗi thực sự là validation chưa cascade. Nếu lỗi do thiếu dependency validator, sai cấu trúc YAML hoặc lỗi constructor, cách sửa phải ở đúng tầng.

## 26. Kiểm tra giá trị cấu hình bằng Environment

Có thể đọc property từ Spring Environment:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {

    private final Environment environment;

    public ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
            environment.getProperty("app.client.http.max-connections")
        );
    }
}
~~~

Ví dụ này hữu ích khi ứng dụng **khởi động thành công** và muốn xem một property không nhạy cảm. Nhưng nếu validation khiến startup thất bại, ApplicationRunner có thể không được gọi. Khi ấy phải xem báo lỗi khởi động, test context hoặc công cụ truy nguyên nguồn cấu hình.

### 26.1. Không in secret khi debug

Các nested properties có thể chứa password, API key và token. Không in toàn bộ record qua toString, không bật log quá chi tiết của Environment ở hệ thống production để chẩn đoán một lỗi nhỏ.

Khi cần, in tên property hoặc trạng thái “có/không”, không in giá trị nhạy cảm. Spring Boot Actuator nếu được sử dụng phải bảo vệ endpoint cấu hình và áp dụng chính sách che dữ liệu thích hợp.

## 27. Kiểm thử binding và @Valid bằng ApplicationContextRunner

Một bài kiểm thử hữu ích là xác nhận **cấu hình hợp lệ tạo được bean** và **cấu hình sai ngăn bean tạo thành công**. Spring Boot cung cấp ApplicationContextRunner để tạo ApplicationContext thử nghiệm với property values riêng.

Một hướng thiết lập:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AppPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                    ValidationAutoConfiguration.class
                ))
                .withUserConfiguration(TestConfig.class);

    @Test
    void rejectsInvalidNestedProperty() {
        runner.withPropertyValues(
            "app.name=Order Service",
            "app.client.base-url=https://api.example.test",
            "app.client.http.connect-timeout=2s",
            "app.client.http.read-timeout=5s",
            "app.client.http.max-connections=0",
            "app.client.retry.max-attempts=3",
            "app.client.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void acceptsValidNestedProperty() {
        runner.withPropertyValues(
            "app.name=Order Service",
            "app.client.base-url=https://api.example.test",
            "app.client.http.connect-timeout=2s",
            "app.client.http.read-timeout=5s",
            "app.client.http.max-connections=20",
            "app.client.retry.max-attempts=3",
            "app.client.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AppProperties.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class TestConfig {}
}
~~~

Đoạn test dùng record AppProperties ở mục 4. Dự án cần có **spring-boot-test**, AssertJ, JUnit Jupiter, validation starter/provider và các dependency tương ứng.

Điểm thiết kế ở đây: cung cấp các property thật cho binder, không tự tạo AppProperties bằng new trong test này. Nhờ đó bài test quan sát được việc binding, cascading validation và khởi tạo bean.

### 27.1. Chỉ test assert lỗi startup thôi đã đủ chưa?

Không nhất thiết. Một context thất bại có thể do typo package hoặc thiếu dependency không liên quan đến constraint mong muốn. Trong test dành riêng cho validation, có thể xét root cause hoặc thông báo chứa tên property/constraint phù hợp.

Tuy nhiên, việc truy nguyên exception phải chịu biến thể theo phiên bản. Tránh phụ thuộc nguyên văn toàn bộ log; kiểm tra thông tin quan trọng thay vì chuỗi message bất biến.

### 27.2. Test thiếu toàn bộ nested branch

Thêm một test chỉ khai báo:

~~~text
app.name=Order Service
~~~

Nếu AppProperties có **@Valid @NotNull Client client**, kỳ vọng context bị từ chối vì client không tồn tại. Điều này giúp phân biệt @Valid với @NotNull.

### 27.3. Test thiếu child nhưng parent vẫn có object

Cấp:

~~~text
app.name=Order Service
app.client.base-url=https://api.example.test
app.client.http.connect-timeout=2s
app.client.http.read-timeout=5s
app.client.http.max-connections=20
~~~

nhưng bỏ nhánh retry. Với **@NotNull Retry retry**, cần có lỗi validation nếu binder không cung cấp default Retry. Đây là bài test điển hình cho nested branch bắt buộc.

## 28. Test cascaded validation của List/Map

Với EndpointProperties ở mục 11, cung cấp:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=
app.endpoints[0].timeout=3s
~~~

Vì List không rỗng nên @NotEmpty có thể pass, nhưng **@NotBlank** của Endpoint.url phải fail nếu cascade hoạt động.

Một test khác:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://api.example.test
app.endpoints[0].timeout=3s
~~~

có dữ liệu hợp lệ và cho phép context tạo bean.

Tương tự với Map:

~~~properties
app.regions.asia.endpoint=
app.regions.asia.timeout=5s
~~~

Vì Map có entry, @NotEmpty có thể pass; do value được đánh dấu @Valid, @NotBlank của Region.endpoint có thể fail.

**Bài test nên tách container constraint và element constraint.** Nếu chỉ dùng một case với Map rỗng, ta chỉ biết @NotEmpty hoạt động, chưa biết @Valid có thật sự đi vào Region.

## 29. @Valid không làm các collection tự bất biến

Một record cấu hình có:

~~~java
List<@Valid Endpoint> endpoints
~~~

thì validation xét phần tử. Nó không ngăn code khác gọi endpoints.add(...) nếu List là mutable.

Muốn tránh sửa cấu hình sau khởi động:

~~~java
public EndpointProperties {
    endpoints = endpoints == null
            ? List.of()
            : List.copyOf(endpoints);
}
~~~

Cách này bảo vệ collection ở cấp ngoài, còn @Valid bảo vệ điều kiện hợp lệ của từng phần tử.

Hai trách nhiệm độc lập:

| Cơ chế | Đảm bảo gì? |
| --- | --- |
| @Valid | Xét constraints của object con |
| @NotEmpty | Collection không rỗng |
| List.copyOf | Collection không bị mutate qua API sau khi copy |
| @ConfigurationProperties | Bind nguồn cấu hình vào kiểu Java |
| PropertySource precedence | Chọn nguồn có hiệu lực |

Không nên dùng defensive copy để thay validation hoặc dùng @Valid để thay một thiết kế immutable.

## 30. Khi dùng custom Validator của Spring Boot

Ngoài Jakarta Bean Validation, Spring Boot cũng cho phép cấu hình cơ chế **org.springframework.validation.Validator** ở những điểm thích hợp. Trong các dự án cần quy tắc phức tạp, custom Validator có thể là lựa chọn thay thế/bổ sung, nhưng phải tích hợp đúng cách vào lifecycle của configuration properties.

Điểm cần phân biệt:

- **Jakarta @Valid** là metadata cho cascading validation.
- **Jakarta constraints** như @NotBlank/@Min mô tả ràng buộc dữ liệu.
- **Spring Validator** là một API kiểm tra dữ liệu khác, có thể được gọi ở điểm tích hợp Spring.
- **@Validated** có thể mang thông tin validation group trong những ngữ cảnh hỗ trợ.

Không nên tự gắn một implementation Validator lên một class rồi cho rằng Spring Boot sẽ tự tìm nó mà không có cơ chế đăng ký. Với yêu cầu thông dụng của nested configuration, Jakarta Bean Validation kết hợp @Validated + @Valid thường là thiết kế dễ hiểu hơn.

## 31. Validation groups: dùng khi có chính sách khác nhau

Jakarta Validation hỗ trợ **validation groups**, có thể dùng khi cùng một kiểu dữ liệu cần bộ ràng buộc khác nhau trong những ngữ cảnh cụ thể.

Tuy nhiên, với externalized configuration, các ràng buộc thường cần ổn định ngay lúc startup. Việc tùy biến nhóm theo môi trường hoặc profile có thể khiến hợp đồng cấu hình khó kiểm soát.

Nếu yêu cầu là “production phải có một thuộc tính, local có thể bỏ”, các giải pháp thường dễ hiểu hơn gồm:

- Thiết kế rõ giá trị mặc định của local.
- Tách cấu hình mandatory và optional theo module.
- Áp dụng một ràng buộc điều kiện có chủ đích.
- Viết test cho những tổ hợp profile thực sự được sử dụng.

Chỉ dùng validation groups khi dự án có nhu cầu thực và đã xác định chính xác nhóm nào được Spring Boot áp dụng cho bean cấu hình.

## 32. Vấn đề vòng lặp trong object graph

Bean Validation có thể cascade qua nhiều object. Trong cấu hình dạng cây được bind từ YAML, object graph thường không có vòng lặp nên dễ kiểm tra.

Nếu Java class tự tạo tham chiếu vòng giữa parent và child, hoặc chia sẻ cùng một object qua nhiều nhánh, validation graph trở nên phức tạp. Provider Jakarta Validation có cơ chế xử lý graph, nhưng việc thiết kế cấu hình vòng vẫn khó hiểu với binder.

Cấu hình bên ngoài nên ưu tiên **mô hình cây hoặc DAG đơn giản**, thay vì object graph tùy ý. Tách các tham chiếu lẫn nhau thành identifier hoặc khóa lookup nếu cần quan hệ phức tạp.

## 33. Một ví dụ đầy đủ: cấu hình cụm server

YAML:

~~~yaml
cluster:
  name: "orders"
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 4s
    europe:
      endpoint: "https://eu.example.test"
      timeout: 5s
  nodes:
    - name: node-a
      host: node-a.example.test
      port: 8080
    - name: node-b
      host: node-b.example.test
      port: 8081
~~~

Record:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "cluster")
public record ClusterProperties(
        @NotBlank String name,
        @NotEmpty Map<@NotBlank String, @NotNull @Valid Region> regions,
        @NotEmpty List<@NotNull @Valid Node> nodes
) {
    public record Region(
            @NotBlank String endpoint,
            @NotNull Duration timeout
    ) {}

    public record Node(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Các đường dẫn đáng chú ý:

~~~text
cluster.name
cluster.regions.asia.endpoint
cluster.regions.asia.timeout
cluster.regions.europe.endpoint
cluster.regions.europe.timeout
cluster.nodes[0].name
cluster.nodes[0].host
cluster.nodes[0].port
cluster.nodes[1].name
cluster.nodes[1].host
cluster.nodes[1].port
~~~

Cấu hình này có ba lớp validation:

1. Root: name bắt buộc; regions và nodes phải có entry/phần tử.
2. Container: key region không trống; value và node phần tử không null.
3. Nested value object: Region.endpoint, Region.timeout, Node.name/host/port hợp lệ.

Nếu node-b.port = 0, vi phạm **@Min(1)**. Nếu regions.europe.endpoint = "", vi phạm **@NotBlank**. Nếu nodes rỗng, vi phạm **@NotEmpty** trên List, không phải constraint trên Node.

## 34. Trường hợp cấu hình bảo mật

Một cấu hình security có thể chứa issuer, public key location hoặc token audience. Các field này thường có yêu cầu bắt buộc rõ.

~~~java
@Validated
@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(
        @Valid @NotNull Jwt jwt
) {
    public record Jwt(
            @NotBlank String issuer,
            @NotBlank String audience
    ) {}
}
~~~

Nếu một ứng dụng yêu cầu xác thực JWT ở mọi môi trường, không nên cung cấp default **issuer="localhost"** chỉ để validation pass. Thiếu issuer phải được phát hiện sớm.

Mặt khác, @NotBlank chỉ kiểm tra chuỗi có nội dung; nó không xác nhận issuer có đáng tin cậy, URL có thể truy cập hoặc chữ ký token được kiểm tra đúng. Validation cấu hình là **một lớp bảo vệ**, không thay thế thiết kế security đúng.

Trong log, tránh in secret hoặc toàn bộ SecurityProperties nếu record chứa thông tin nhạy cảm.

## 35. Bài thực hành 1: thiếu @Valid

Cho code:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

Cấu hình:

~~~yaml
app:
  client:
    base-url: ""
~~~

Hãy nêu điểm cần bổ sung để thể hiện yêu cầu validation xuyên xuống Client.

Đáp án:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {
    public record Client(@NotBlank String baseUrl) {}
}
~~~

Nếu client bắt buộc có object, dùng **@Valid @NotNull Client client**.

## 36. Bài thực hành 2: null và cascading validation

Code:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {
    public record Client(@NotBlank String endpoint) {}
}
~~~

Không có bất kỳ property app.client.* nào.

Hỏi: chỉ @Valid có nghĩa client phải khác null không? **Không.** Theo quy tắc cascade, null không làm validator đi sâu và tự phát sinh violation. Muốn phát hiện nhánh thiếu, thêm **@NotNull** trên client hoặc một ràng buộc nghiệp vụ tương đương.

## 37. Bài thực hành 3: hai cấp nested

Cấu hình:

~~~yaml
app:
  http:
    pool:
      max-size: 0
~~~

Mô hình:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @NotNull Http http
) {
    public record Http(
            @Valid @NotNull Pool pool
    ) {}

    public record Pool(
            @Min(1) int maxSize
    ) {}
}
~~~

Hỏi: vì sao phải có @Valid trên Http.pool? Bởi vì validator cần một đường cascade từ Http sang Pool để kiểm tra @Min(1). Nếu chỉ root có @Valid trên http, không nên mặc định constraint bên trong Pool luôn được kiểm tra theo đúng hợp đồng cascade.

## 38. Bài thực hành 4: List phần tử có dữ liệu sai

YAML:

~~~yaml
app:
  providers:
    - name: fast
      timeout: 2s
    - name: ""
      timeout: 3s
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@Valid Provider> providers
) {
    public record Provider(
            @NotBlank String name,
            @NotNull Duration timeout
    ) {}
}
~~~

List có hai phần tử nên **@NotEmpty** pass. Nhưng phần tử thứ hai có name rỗng nên constraint của Provider fail nhờ @Valid trên element. Đó là ví dụ phân biệt container validation và element validation.

## 39. Bài thực hành 5: Map value và nested @Valid

YAML:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
    europe:
      endpoint: ""
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty Map<String, @Valid Region> regions
) {
    public record Region(
            @NotBlank String endpoint
    ) {}
}
~~~

Câu hỏi: Map có hai entry có đủ để cấu hình hợp lệ không? Không. @NotEmpty chỉ xét số entry; @Valid đưa validator đến Region của từng entry, phát hiện europe.endpoint rỗng.

## 40. Bài thực hành 6: ràng buộc điều kiện

YAML:

~~~yaml
app:
  notifications:
    enabled: false
~~~

Giả sử endpoint chỉ bắt buộc khi enabled=true. Nếu viết:

~~~java
public record Notifications(
        boolean enabled,
        @NotBlank String endpoint
) {}
~~~

thì ràng buộc endpoint áp dụng vô điều kiện kể cả khi enabled=false. Nếu nghiệp vụ cho phép endpoint vắng mặt khi tắt, @NotBlank trực tiếp có thể không phù hợp.

Một giải pháp dùng invariant:

~~~java
public record Notifications(
        boolean enabled,
        String endpoint
) {
    @AssertTrue
    public boolean isConfigurationValid() {
        return !enabled || (endpoint != null && !endpoint.isBlank());
    }
}
~~~

Để invariant trên Notifications được chạy khi nó nằm trong AppProperties, cần cascade vào Notifications bằng @Valid ở chỗ tham chiếu.

## 41. Bài thực hành 7: validation cho Duration

Record:

~~~java
public record TimeoutProperties(
        @NotNull Duration timeout
) {}
~~~

Cấu hình timeout: **0s**. Hỏi: @NotNull có fail không? **Không**, vì Duration.ZERO không phải null.

Muốn kiểm tra dương, cần constraint phù hợp với Duration hoặc một quy tắc như:

~~~java
@AssertTrue
public boolean isTimeoutPositive() {
    return timeout != null && !timeout.isZero() && !timeout.isNegative();
}
~~~

Đặt invariant ở đúng object và bảo đảm object nằm trên đường validation.

## 42. Bài thực hành 8: phát hiện lỗi thực sự

Cho tình huống:

~~~yaml
app:
  client:
    http:
      max-connections: "many"
~~~

Java:

~~~java
public record Http(
        @Min(1) int maxConnections
) {}
~~~

Hỏi: nguyên nhân có phải vì thiếu @Valid không? Chưa thể kết luận. Giá trị **many** không chuyển được sang int, nên lỗi conversion có thể xuất hiện trước validation. Sửa giá trị thành số nguyên hợp lệ rồi mới kiểm tra điều kiện @Min.

Đây là nguyên tắc chẩn đoán: **validation không thay thế conversion**.

## 43. Quy trình debug nested validation

Khi cấu hình sai nhưng ứng dụng vẫn chạy hoặc báo lỗi không rõ, lần theo:

1. **Xác định prefix** của class @ConfigurationProperties.
2. **Viết toàn bộ đường dẫn property** đến field, ví dụ app.client.http.max-connections.
3. **Kiểm tra source**: YAML, .properties, profile, biến môi trường, JVM properties, CLI và import.
4. **Xem kiểu đích và conversion**: int, String, Duration, List, Map.
5. **Xác định object con có được tạo không**: constructor binding, setter binding, default, null.
6. **Kiểm tra root có @Validated** và Jakarta Validation provider tồn tại.
7. **Kiểm tra @Valid trên mọi ranh giới nested** cần cascade.
8. **Kiểm tra @NotNull hoặc @NotEmpty** cho object/collection bắt buộc.
9. **Kiểm tra constraints ở field đích**: @NotBlank, @Min, @Size hoặc custom validator.
10. **Đọc root cause của lỗi khởi động** và viết test phản ánh chính xác tình huống.
11. **Tránh in dữ liệu nhạy cảm** trong log chẩn đoán.
12. **Kiểm tra dữ liệu sau precedence** thay vì chỉ nhìn một file nguồn.

Cách nghĩ phù hợp là:

~~~text
Tên đúng?
   |
   v
Nguồn có hiệu lực?
   |
   v
Bind + conversion thành công?
   |
   v
Nested object tồn tại?
   |
   v
Validation được kích hoạt?
   |
   v
@Valid có cascade tới cấp cần kiểm tra?
   |
   v
Constraint field/container/element có đúng?
~~~

Nếu một khâu thất bại, thêm annotation ở khâu khác không giải quyết nguyên nhân.

## 44. Quy ước cho dự án thực tế

Một số quy ước giúp dự án Spring Boot giữ cấu hình dễ bảo trì:

- Sử dụng **@ConfigurationProperties** để nhóm các cấu hình có quan hệ rõ ràng.
- Đặt **@Validated** trên bean cấu hình cần kiểm tra khi startup.
- Đặt **@Valid** trên object con và container elements khi cần validate sâu.
- Đặt **@NotNull** khi một nhánh bắt buộc tồn tại; không lạm dụng @Valid thay @NotNull.
- Sử dụng **@NotBlank** cho String cần có nội dung; **@NotEmpty** cho collection cần phần tử.
- Với kiểu số, dùng constraint miền giá trị như @Min, @Max hoặc @Positive.
- Với Duration/URI/logic nhiều trường, dùng kiểu Java phù hợp và constraint hợp lệ cho kiểu đó.
- Viết **test cho nhánh vắng mặt**, **field rỗng**, **sai kiểu**, **List/Map phần tử sai**.
- Tránh default hợp lệ giả nếu giá trị bắt buộc được cấp khi deploy.
- Không xây dựng validation dựa trên side effect hoặc một kết nối bên ngoài thiếu kiểm soát.
- Không log record cấu hình có secret vì toString có thể lộ component values.
- Không coi việc ứng dụng start thành công là bằng chứng toàn bộ nhánh cấu hình đã được validate.

Nếu muốn nâng mức bảo đảm, có thể quy định rằng mỗi nhóm cấu hình quan trọng phải có ít nhất hai bài test: một cấu hình hợp lệ và một cấu hình nested sai có chủ đích.

## 45. Tổng kết

**@Validated** và **@Valid** thường xuất hiện cùng nhau trong Spring Boot nhưng không đồng nghĩa.

- **@Validated** ở bean **@ConfigurationProperties** giúp Spring Boot kích hoạt validation khi binding trong điều kiện tích hợp phù hợp.
- **@Valid** biểu thị **cascaded validation**: tiếp tục kiểm tra object lồng nhau, phần tử List hoặc value trong Map.
- **@NotNull** kiểm tra một object/field phải tồn tại. **@Valid không tự cấm null**.
- Với nhiều cấp nested, phải có đường cascade đi qua từng cấp cần kiểm tra.
- **@NotEmpty** kiểm tra kích thước collection; các constraint trên phần tử vẫn cần được áp dụng qua @Valid hoặc metadata của container element.
- Cấu hình vắng mặt, chuỗi rỗng, giá trị sai kiểu và giá trị đúng kiểu nhưng vi phạm constraint là những vấn đề khác nhau.
- Constructor binding, setter binding và default quyết định **object nào được tạo**; Bean Validation quyết định **object đã tạo có đáp ứng hợp đồng không**.
- Validation chạy trên cấu hình **sau khi Spring xác định nguồn và binder xử lý dữ liệu**, nên cần phân biệt precedence với logic constraint.
- Một mô hình validation tốt giúp ứng dụng **fail fast** khi cấu hình quan trọng sai, và giúp thông báo lỗi gắn với đường dẫn property cụ thể.

Quy tắc dễ ghi nhớ: **root có @Validated, nhánh cần kiểm tra sâu có @Valid, nhánh bắt buộc có @NotNull và mỗi field/container có constraint đúng ý nghĩa nghiệp vụ**. Khi áp dụng nhất quán, cấu hình lồng nhau trở thành một hợp đồng dữ liệu rõ ràng thay vì tập hợp những giá trị chỉ được kiểm tra ở thời điểm request đầu tiên.
