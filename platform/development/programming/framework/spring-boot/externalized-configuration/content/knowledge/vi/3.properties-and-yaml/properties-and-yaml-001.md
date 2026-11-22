# Cú pháp khóa và giá trị trong application.properties

`application.properties` là một định dạng văn bản theo cặp **khóa (key) – giá trị (value)** mà Spring Boot thường dùng để cấu hình ứng dụng từ bên ngoài mã Java. Nắm đúng cú pháp tệp giúp tránh những lỗi khó nhận thấy: một dấu cách vô tình làm đổi tên key, một dấu `#` tưởng là comment nhưng thực ra nằm trong giá trị, hay một dấu gạch chéo ngược bị xử lý như ký tự escape.

Bài này tập trung vào cách **viết và đọc từng dòng `application.properties`**. Các ví dụ dùng Spring Boot, nhưng cần phân biệt hai tầng: **cú pháp `.properties`** quyết định cặp key/value được đọc thành chuỗi như thế nào; **Spring Boot** quyết định key nào có ý nghĩa và chuyển chuỗi sang các kiểu Java phù hợp.

## 1. Một tệp properties đơn giản trông như thế nào?

~~~properties
# src/main/resources/application.properties

spring.application.name=order-service
server.port=8080
server.shutdown=graceful

app.client.base-url=https://api.example.test
app.client.connect-timeout=750ms
app.client.max-retries=3
app.feature.audit-enabled=true
~~~

Mỗi dòng không phải comment hay dòng trống khai báo một cặp key/value. Ví dụ, `server.port` là key và `8080` là phần văn bản của value. Spring Boot biết `server.port` là thuộc tính cấu hình cổng HTTP; khi bind sang thuộc tính có kiểu số, nó chuyển chuỗi `8080` thành số phù hợp.

Các key bắt đầu bằng `app.` trong ví dụ là **thuộc tính tự định nghĩa**. Spring Boot không tự biết phải dùng `app.client.base-url` để gọi API nào: ứng dụng cần một bean nhận cấu hình này, qua `@ConfigurationProperties`, `@Value` hoặc `Environment`.

Vị trí phổ biến của tệp trong dự án Java là `src/main/resources/application.properties`. Khi được đóng gói, tệp đi vào classpath và được Spring Boot xem như một nguồn Config Data theo cơ chế mặc định. Ứng dụng cũng có thể nhận cấu hình từ tệp ngoài JAR, biến môi trường, đối số dòng lệnh và những nguồn khác.

## 2. Cú pháp nền tảng: key, dấu phân cách và value

Cách viết dễ đọc và được khuyến nghị nhất là:

~~~properties
key=value
~~~

Định dạng Java properties còn cho phép dấu `:` hoặc khoảng trắng làm dấu phân cách:

~~~properties
app.mode=fast
app.mode:fast
app.mode fast
~~~

**Ba dòng trên là ba cách viết cùng một key/value**, không phải ví dụ nên đặt đồng thời trong một tệp. Hãy chọn `=` để thống nhất với những thành viên khác trong dự án và giảm khả năng đọc nhầm.

Một dòng được phân tích theo nguyên tắc cơ bản:

1. Bỏ qua khoảng trắng ở đầu dòng để xác định vị trí bắt đầu key.
2. Đọc key cho đến dấu `=`, dấu `:` hoặc khoảng trắng **chưa được escape** đầu tiên.
3. Bỏ qua dấu phân cách và khoảng trắng liên quan ngay trước khi value bắt đầu.
4. Phần còn lại của dòng logic trở thành value sau khi xử lý các escape hợp lệ.

Ví dụ:

~~~properties
app.title = Order Service
app.description: Handles purchase orders
app.region asia-southeast
app.empty=
~~~

Kết quả logic:

| Key | Value |
| --- | --- |
| `app.title` | `Order Service` |
| `app.description` | `Handles purchase orders` |
| `app.region` | `asia-southeast` |
| `app.empty` | Chuỗi rỗng |

`app.empty=` khai báo **một key có value rỗng**. Điều này khác với việc **không có key** trong nguồn cấu hình. Khi ứng dụng có fallback, validation hoặc kiểu đích đặc biệt, hai tình huống có thể cho kết quả khác nhau.

### Dấu `=` hoặc `:` nằm trong value thì sao?

Thông thường, sau dấu phân cách đầu tiên, những dấu `=` và `:` tiếp theo thuộc về value:

~~~properties
app.query=page=1&size=20
app.endpoint=https://example.test:8443/api
app.label=alpha:beta=gamma
~~~

Các giá trị lần lượt là `page=1&size=20`, `https://example.test:8443/api` và `alpha:beta=gamma`. Không cần escape `:` trong một URL chỉ vì nó xuất hiện ở phía value.

Ở phía **key**, nếu muốn dùng dấu `:`, `=` hoặc khoảng trắng như ký tự thực sự của tên, cần escape; tuy nhiên với cấu hình Spring Boot, thông thường nên tránh tên key đặc biệt và dùng tên phân cấp rõ ràng.

## 3. Quy tắc đặt tên key trong Spring Boot

Spring Boot thường dùng key phân cấp bằng dấu chấm và nhiều từ trong một thành phần bằng dấu gạch ngang:

~~~properties
server.port=8080
spring.application.name=order-service

app.mail.sender-address=noreply@example.test
app.mail.retry-policy.max-attempts=3
app.mail.retry-policy.backoff=2s
~~~

Có thể đọc `app.mail.retry-policy.max-attempts` theo cấu trúc: nhóm `app` → thành phần `mail` → nhóm `retry-policy` → thuộc tính `max-attempts`. Với `@ConfigurationProperties(prefix = "app.mail")`, Spring Boot Binder có thể ánh xạ các phần tương ứng sang thuộc tính Java như `senderAddress` và `maxAttempts`.

**Quy ước nên áp dụng:** dùng key dạng chữ thường `kebab-case` cho từng phần tên, ngăn cách các cấp bằng `.`. Ví dụ `app.client.connect-timeout` là tên canonical nên ưu tiên khi định nghĩa và tham chiếu cấu hình.

~~~properties
# Tên được khuyến nghị
app.client.connect-timeout=750ms
app.feature.audit-enabled=true
~~~

Spring Boot hỗ trợ *relaxed binding*, nghĩa là một số biến thể tên có thể được ánh xạ về thuộc tính Java tương ứng. Dù vậy, relaxed binding không phải lý do để trộn tùy tiện `connectTimeout`, `connect_timeout` và `connect-timeout` trong cùng một tệp. Tên chuẩn giúp thao tác tìm kiếm, override và tra cứu nhất quán.

Không có “đăng ký tự động” cho mọi key bắt đầu bằng `app.`. Nếu tên key không được bean nào tiêu thụ, dòng cấu hình đó có thể chỉ là dữ liệu nằm trong `Environment`. Một số key đặc biệt như `server.port` hoặc `spring.application.name` được Spring Boot và các auto-configuration tương ứng nhận diện.

## 4. Value là văn bản trước khi được Spring Boot chuyển kiểu

Trong tệp `.properties`, nội dung phía phải được đọc trước hết theo cú pháp chuỗi. Spring Boot có thể chuyển sang số, boolean, thời lượng, kích thước dữ liệu, URI, enum hoặc những kiểu khác tùy consumer.

~~~properties
app.worker.threads=8
app.feature.enabled=true
app.client.connect-timeout=1500ms
app.client.read-timeout=5s
app.cache.maximum-size=64MB
app.client.base-url=https://api.example.test/v1
app.banner=Welcome to Order Service
~~~

| Value trong tệp | Kiểu Java có thể bind | Cách hiểu |
| --- | --- | --- |
| `8` | `int` / `Integer` | Số nguyên |
| `true` | `boolean` / `Boolean` | Giá trị luận lý |
| `1500ms` | `Duration` | 1,5 giây |
| `5s` | `Duration` | 5 giây |
| `64MB` | `DataSize` | Kích thước dữ liệu theo đơn vị của Spring |
| `https://api.example.test/v1` | `URI` | Địa chỉ có cấu trúc |
| `Welcome to Order Service` | `String` | Văn bản thông thường |

Cú pháp `.properties` không tự khai báo kiểu của một dòng; **kiểu đích do cách ứng dụng đọc và bind quyết định**. Ví dụ `server.port=eight-thousand` vẫn có hình thức key/value hợp lệ, nhưng Spring Boot không thể dùng văn bản đó như một số cổng hợp lệ và có thể báo lỗi cấu hình khi khởi động.

Không phải mọi key tự định nghĩa đều được Spring Boot kiểm tra. Nếu muốn một giá trị tùy biến bắt buộc phải có hoặc phải nằm trong một khoảng, hãy định nghĩa ràng buộc ở lớp nhận cấu hình.

## 5. Comment và dòng trống

Một dòng comment bắt đầu bằng `#` hoặc `!` tại **ký tự đầu tiên không phải khoảng trắng** của dòng tự nhiên:

~~~properties
# Cấu hình HTTP
! Dòng này cũng là comment

server.port=8080

    # Comment có khoảng trắng đầu dòng
app.feature.audit-enabled=true
~~~

Dòng trống giúp nhóm các thuộc tính có liên quan mà không tạo key/value.

### Không có cú pháp comment cuối dòng kiểu YAML

Đây là điểm rất dễ sai:

~~~properties
app.greeting=Hello # this is a comment
app.version=1.0 ! latest release
~~~

Theo cú pháp Java properties, `# this is a comment` và `! latest release` ở **cuối value** là một phần của giá trị, chứ không bị bỏ qua như comment. Nếu muốn chú thích, hãy chuyển comment sang một dòng riêng:

~~~properties
# Câu chào hiển thị ở trang chủ
app.greeting=Hello

# Phiên bản hiển thị trong màn hình About
app.version=1.0
~~~

Với dữ liệu có chứa dấu `#` như fragment của URL, nó có thể nằm trong value:

~~~properties
app.docs-url=https://docs.example.test/guide#configuration
~~~

Không nên giả định rằng các quy tắc viết comment của YAML hoặc JSONC cũng áp dụng trong `.properties`.

## 6. Dấu nháy không đóng vai trò bao chuỗi

Trong YAML, chuỗi thường được đặt trong dấu nháy. Trong `application.properties`, việc thêm dấu nháy thường khiến chính dấu nháy trở thành nội dung value theo cách đọc Java properties:

~~~properties
app.message=Hello world
app.message-quoted="Hello world"
app.choice='blue'
~~~

Các value theo cú pháp tệp lần lượt là:

- `Hello world`
- `"Hello world"`, có dấu nháy kép
- `'blue'`, có dấu nháy đơn

Vì vậy, **không thêm dấu nháy chỉ để chứa khoảng trắng**:

~~~properties
# Đủ để biểu diễn chuỗi có dấu cách
app.display-name=Order Management Service
~~~

Việc một consumer ở tầng cao có xử lý riêng dấu nháy hay không phụ thuộc consumer đó, nhưng đừng coi dấu nháy là quy tắc cốt lõi của định dạng properties. Nếu cần chuyển một chuỗi chứa dấu nháy theo đúng nghĩa đen, hãy kiểm tra nội dung giá trị mà bean nhận được.

## 7. Khoảng trắng trước, quanh và sau dấu phân cách

Một số dòng nhìn khác nhau nhưng có thể biểu diễn cùng một cặp:

~~~properties
app.locale=vi_VN
app.locale = vi_VN
app.locale: vi_VN
~~~

Khoảng trắng đầu dòng và khoảng trắng dùng để ngăn cách key/value được parser xử lý theo quy tắc của định dạng. Khoảng trắng **nằm trong value** vẫn có ý nghĩa:

~~~properties
app.display-name=Order Service
app.pattern=first  second
~~~

`app.pattern` chứa hai khoảng trắng giữa `first` và `second`. Khoảng trắng ở **cuối value** cũng có thể được giữ lại, tạo lỗi khó thấy nếu chuỗi tham gia so sánh, ký số hoặc tạo đường dẫn.

Nếu value cần **bắt đầu bằng một dấu cách thực sự**, có thể escape dấu cách đầu tiên:

~~~properties
app.indented-label=\ Leading space
~~~

Value của `app.indented-label` bắt đầu bằng một dấu cách. Trong thực tế, hãy tránh để dữ liệu quan trọng phụ thuộc vào khoảng trắng vô hình; nếu phải dùng, nên mô tả rõ ý định và kiểm thử giá trị khi bind.

Một tên key có dấu cách không escape cũng có thể bị cắt sớm:

~~~properties
# Không nên dùng để biểu thị key "feature flag"
feature flag=true

# Ví dụ escape dấu cách trong key của Java properties
feature\ flag=true
~~~

Dòng đầu có thể được hiểu là key `feature` và value `flag=true` theo quy tắc tách key/value, thay vì key `feature flag`. Dòng thứ hai biểu diễn key có dấu cách, nhưng đây không phải kiểu đặt tên phù hợp cho phần lớn cấu hình Spring Boot. Hãy dùng `app.feature.enabled=true` hoặc `app.feature-flag=true` cho ý nghĩa cụ thể.

## 8. Escape bằng dấu gạch chéo ngược

Dấu backslash `\` có ý nghĩa đặc biệt trong Java properties. Những escape thường gặp gồm:

| Ký hiệu trong tệp | Ký tự sau khi đọc |
| --- | --- |
| `\\` | Một dấu backslash `\` |
| `\n` | Xuống dòng |
| `\r` | Carriage return |
| `\t` | Tab |
| `\f` | Form feed |
| `\u0041` | Ký tự Unicode `A` |
| `\ ` | Dấu cách được escape |
| `\=`, `\:` | Dấu `=`, `:` theo nghĩa đen, hữu ích khi nằm trong key |

Ví dụ:

~~~properties
app.message=First line\nSecond line
app.column-label=Name\tStatus
app.literal-backslash=\\
app.windows-export-dir=C:\\data\\exports
app.key\=with-equals=some-value
~~~

Theo cú pháp properties:

- `app.message` chứa một ký tự xuống dòng giữa hai phần văn bản, không phải hai ký tự `\` và `n`.
- `app.column-label` chứa tab.
- `app.literal-backslash` là một ký tự `\`.
- `app.windows-export-dir` chứa đường dẫn Windows `C:\data\exports` với backslash theo đúng nghĩa.
- Dòng cuối có key `app.key=with-equals`, được escape để dấu `=` là một phần tên key.

**Bẫy đường dẫn Windows:**

~~~properties
# Không an toàn khi kỳ vọng backslash được giữ nguyên
app.export-dir=C:\temp\reports

# Escape backslash
app.export-dir=C:\\temp\\reports
~~~

Trong ví dụ đầu, `\t` có thể thành tab, `\r` thành carriage return. Những backslash trước ký tự không được nhận diện như escape cũng có thể không còn nguyên vẹn. Đừng copy đường dẫn Windows vào properties mà không kiểm tra các backslash.

Đối với nội dung Unicode, cú pháp `\uXXXX` biểu diễn một đơn vị mã Unicode theo quy tắc properties. Khi cần biểu diễn ký tự ngoài Basic Multilingual Plane bằng escape truyền thống, có thể cần hai escape tương ứng cặp UTF-16 surrogate. Trong dự án thực tế, nên chuẩn hóa encoding của tệp và pipeline build; tránh phụ thuộc vào cách một trình soạn thảo hoặc loader riêng xử lý encoding.

## 9. Viết value qua nhiều dòng với dấu `\`

Dấu backslash ở **cuối dòng tự nhiên** có thể nối dòng tiếp theo thành cùng một value logic:

~~~properties
app.long-message=Welcome to \
  the order service \
  configuration guide
~~~

Các dòng trên tạo một key `app.long-message`. Phần khoảng trắng đầu dòng nối tiếp thường bị bỏ qua theo quy tắc continuation; ký tự xuống dòng vật lý không tự trở thành dấu cách trong value. Kết quả logic của ví dụ là `Welcome to the order service configuration guide` vì mỗi đoạn trước dấu `\` đã chứa dấu cách cần thiết.

Hãy xem ví dụ không có dấu cách trước backslash:

~~~properties
app.code=ABC\
  DEF
~~~

Value là `ABCDEF`, không phải `ABC DEF`. Muốn có dấu cách, cần viết dấu cách có chủ đích hoặc dùng một cách biểu diễn đơn giản hơn.

Nếu cần **ký tự xuống dòng thực tế** trong value, dùng escape `\n`, không giả định dấu nối dòng sẽ giữ newline:

~~~properties
app.notice=Line one\nLine two
~~~

Cú pháp nhiều dòng có thể tiết kiệm chiều ngang, nhưng với nội dung dài hoặc có cấu trúc phức tạp, hãy cân nhắc liệu YAML hay tài nguyên văn bản riêng có giúp đọc và bảo trì tốt hơn.

## 10. Key trùng và ý nghĩa của việc ghi đè

Xét một tệp duy nhất:

~~~properties
app.client.max-retries=2
app.client.max-retries=5
~~~

Khi hai khai báo cùng key được nạp tuần tự vào cùng một tập thuộc tính theo cách đọc thông thường, **khai báo sau sẽ thay giá trị của khai báo trước**. Vì thế, đừng dựa vào khai báo trùng như một cách biểu đạt môi trường hoặc lịch sử thay đổi. Chỉ giữ một khai báo rõ ràng cho mỗi key trong một tài liệu cấu hình.

Khác với key trùng *trong cùng một tài liệu*, Spring Boot còn có **nhiều property source**. Ví dụ `app.client.max-retries=2` trong `application.properties` có thể bị ghi đè bằng biến môi trường hoặc đối số khởi động có độ ưu tiên cao hơn. Lúc này kết quả phụ thuộc quy tắc precedence giữa các nguồn chứ không chỉ thứ tự dòng trong tệp.

~~~bash
java -jar order-service.jar --app.client.max-retries=7
~~~

Nếu không có nguồn ưu tiên cao hơn đang tác động, ví dụ command-line này có thể khiến giá trị hiệu lực của `app.client.max-retries` thành `7` dù tệp đặt `2`. Cần phân biệt **cú pháp đọc một tài liệu** với **cách Spring Boot hợp nhất nhiều nguồn**.

## 11. Danh sách, phần tử và map trong properties

Bản thân cú pháp `.properties` không có mảng như YAML. Tuy vậy, Spring Boot Binder hiểu các key dạng chỉ số khi liên kết cấu hình sang collection:

~~~properties
app.contacts[0].name=Operations
app.contacts[0].email=ops@example.test
app.contacts[1].name=Support
app.contacts[1].email=support@example.test
~~~

Một Java object chứa `List<Contact>` có thể nhận dữ liệu dựa trên các chỉ số `[0]`, `[1]` nếu bean và kiểu phần tử được khai báo phù hợp.

Với các giá trị đơn giản, cấu hình phân cách bằng dấu phẩy cũng có thể được bind sang collection tùy kiểu đích:

~~~properties
app.allowed-regions=ap-southeast-1,ap-northeast-1,eu-west-1
~~~

Đây không phải cú pháp mảng riêng của Java properties. Dữ liệu gốc là một chuỗi chứa dấu phẩy; cách chuyển thành danh sách thuộc Spring Boot Binder hoặc consumer tương ứng. Nếu bản thân giá trị phần tử có dấu phẩy hoặc cấu trúc phức tạp, cú pháp theo chỉ số rõ ràng hơn.

Map cũng có thể biểu diễn bằng những key con:

~~~properties
app.labels.team=payments
app.labels.owner=backend
~~~

Với những map key có ký tự đặc biệt như dấu gạch chéo, Spring Boot Binder hỗ trợ cú pháp bracket để giữ nguyên key trong ngữ cảnh phù hợp:

~~~properties
app.labels.[/public-api]=enabled
~~~

Đừng tự giả định dấu chấm, gạch chéo hoặc ngoặc sẽ luôn được giữ nguyên ở mọi kiểu map; hãy chọn key phù hợp và kiểm tra cách bind đối với kiểu đích cụ thể.

## 12. Placeholder: tham chiếu giá trị khác bằng `${...}`

Spring Boot cho phép giá trị cấu hình có placeholder được giải quyết qua `Environment`. Ví dụ:

~~~properties
app.http.scheme=https
app.http.host=api.example.test
app.http.port=8443
app.http.base-url=${app.http.scheme}://${app.http.host}:${app.http.port}
~~~

Khi được Spring giải quyết, `app.http.base-url` tương ứng `https://api.example.test:8443`.

Có thể khai báo giá trị fallback khi một tham chiếu không tồn tại:

~~~properties
app.client.timeout=${APP_TIMEOUT:3s}
app.client.base-url=${APP_BASE_URL:https://api.example.test}
~~~

Ở đây `${APP_TIMEOUT:3s}` nghĩa là tham chiếu `APP_TIMEOUT`; nếu không có giá trị tương ứng, dùng `3s` làm mặc định trong ngữ cảnh giải quyết placeholder. Dấu hai chấm **nằm trong biểu thức placeholder** có vai trò khác với dấu phân cách key/value của tệp.

Cần phân biệt:

- Tệp `.properties` xác định value nguyên thủy là văn bản chứa `${...}`.
- Spring Boot và hạ tầng giải quyết placeholder xử lý tham chiếu, fallback khi consumer lấy giá trị.
- Không phải trình đọc `java.util.Properties` thuần túy nào cũng tự giải quyết cú pháp `${...}`.

Nên tham chiếu tới các key nội bộ bằng tên canonical, ví dụ `${app.client.timeout}`, để tránh phụ thuộc vào quy ước tên không nhất quán. Nếu một placeholder không có nguồn và không có fallback, consumer có thể gặp lỗi khi giải quyết giá trị, tùy cách sử dụng.

## 13. Khi ứng dụng đọc value: Environment, @Value và @ConfigurationProperties

Ví dụ tệp:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=750ms
app.client.max-retries=3
~~~

Một bean có thể đọc bằng `Environment`:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientConfigReader {
    private final Environment environment;

    public ClientConfigReader(Environment environment) {
        this.environment = environment;
    }

    public Duration connectTimeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }
}
~~~

Với một thuộc tính đơn lẻ, `@Value` cũng có thể phù hợp:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SingleTimeoutHolder {
    public SingleTimeoutHolder(
        @Value("${app.client.connect-timeout:1s}") Duration timeout
    ) {
        System.out.println(timeout);
    }
}
~~~

Nhưng với nhiều key liên quan, một cấu hình có kiểu sẽ rõ ràng hơn:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Kích hoạt quét các bean properties trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Khi đó Spring Boot Binder có thể ánh xạ `base-url` → `baseUrl`, `connect-timeout` → `connectTimeout` và `max-retries` → `maxRetries`. Value `750ms` được chuyển thành `Duration`, còn `3` thành số nguyên.

Lưu ý, nếu chỉ khai báo record có `@ConfigurationProperties` mà không đăng ký bean bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` tương ứng, ứng dụng không mặc nhiên có một bean `ClientProperties` để inject.

## 14. Chạy cùng cấu hình theo profile

Một tệp cơ sở có thể khai báo:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=3
~~~

Tệp dành cho development:

~~~properties
# application-dev.properties
app.client.base-url=http://localhost:8081
app.client.connect-timeout=500ms
~~~

Khi profile `dev` được kích hoạt qua một nguồn hợp lệ, ví dụ:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Spring Boot có thể nạp cấu hình theo profile. Trong tình huống này, `base-url` và `connect-timeout` lấy giá trị trong `application-dev.properties`, còn `max-retries` tiếp tục nhận `3` từ tệp cơ sở nếu không có nguồn ưu tiên cao hơn ghi đè.

Không được hiểu rằng tệp `application-dev.properties` tự có hiệu lực chỉ vì nó tồn tại. Ngoài ra, cùng một key có thể bị ghi đè bởi biến môi trường, system property hay command-line theo thứ tự ưu tiên nguồn cấu hình.

### Nhiều tài liệu trong một tệp properties của Spring Boot

Spring Boot Config Data hỗ trợ phân cách các tài liệu trong một tệp `application.properties` bằng dấu `#---`:

~~~properties
app.client.connect-timeout=3s
app.logging.detail=normal

#---
spring.config.activate.on-profile=dev
app.client.connect-timeout=500ms
app.logging.detail=verbose
~~~

Khi phần sau được kích hoạt bởi profile `dev`, các giá trị phù hợp từ tài liệu đó được áp dụng. `#---` ở đây là **dấu phân cách tài liệu đặc biệt do Spring Boot hỗ trợ**, không đơn thuần là chú thích tiếng người. Vì đây là cơ chế của Spring Boot Config Data, không suy ra rằng mọi parser Java properties thông thường sẽ có cùng hành vi.

Không đặt `spring.profiles.active` trong tài liệu đã bị ràng buộc bởi `spring.config.activate.on-profile`. Quy tắc kích hoạt profile cần được thiết kế ở nguồn có thể quyết định active profile hợp lệ.

## 15. File properties khác YAML ở những điểm nào?

Hai cách khai báo sau có thể biểu diễn cùng những key:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=3
~~~

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 3
~~~

| Khía cạnh | Properties | YAML |
| --- | --- | --- |
| Cấu trúc phân cấp | Tên key phẳng với dấu `.` | Thụt lề và nested mapping |
| Dấu phân cách | `=`, `:` hoặc khoảng trắng theo cú pháp properties | Dấu `:` với thụt lề theo YAML |
| Comment | `#` hoặc `!` ở đầu dòng logic | `#` với quy tắc YAML |
| Dấu nháy | Không phải dấu bao chuỗi tiêu chuẩn của properties | Có cú pháp chuỗi nháy đơn/đôi |
| Danh sách | Dùng key chỉ số hoặc chuỗi để binder phân tích | Có native sequence `- item` |
| Escape | Dấu `\` theo cú pháp properties | Phụ thuộc kiểu chuỗi YAML |

Dù cùng mô tả một key, không nên duy trì cả `application.properties` lẫn `application.yml` với những giá trị cạnh tranh trong cùng vị trí cấu hình. Spring Boot có quy tắc ưu tiên khi cùng địa điểm có cả hai; với cấu hình mặc định, định dạng `.properties` được ưu tiên hơn YAML. Chọn một định dạng chính giúp tránh nhầm lẫn.

## 16. Những lỗi phổ biến và cách nhận biết

### Lỗi 1 — Coi phần cuối dòng là comment

~~~properties
# Sai nếu chỉ muốn lưu giá trị "3"
app.retry-count=3 # retries
~~~

Giá trị có thể trở thành `3 # retries`, khiến việc bind sang `int` thất bại. Đúng hơn là:

~~~properties
# Số lần thử lại
app.retry-count=3
~~~

### Lỗi 2 — Dùng nháy kép theo thói quen từ YAML

~~~properties
app.mode="production"
~~~

Nếu consumer mong `production` không có dấu nháy, value ở tầng properties có thể không khớp. Nên viết:

~~~properties
app.mode=production
~~~

### Lỗi 3 — Ghi đường dẫn Windows với backslash đơn

~~~properties
app.download-path=C:\new\temp
~~~

`\n` và `\t` là escape nên chuỗi có thể bị biến dạng. Viết rõ:

~~~properties
app.download-path=C:\\new\\temp
~~~

### Lỗi 4 — Nhầm tên key và kiểu Java

~~~properties
app.client.connectTimeout=500ms
~~~

Relaxed binding có thể xử lý các biến thể tên trong ngữ cảnh phù hợp, nhưng key chuẩn, đặc biệt khi dùng placeholder, nên là:

~~~properties
app.client.connect-timeout=500ms
~~~

Nếu tên prefix khác hoàn toàn, ví dụ `client.connect-timeout` thay vì `app.client.connect-timeout`, Binder sẽ không tự đoán ý định và tìm sang prefix khác.

### Lỗi 5 — Tin rằng value rỗng đồng nghĩa với không khai báo

~~~properties
app.smtp.username=
~~~

Key có tồn tại với giá trị rỗng. Một ứng dụng yêu cầu username không được để trống cần kiểm tra riêng, ví dụ thông qua Bean Validation của properties bean.

### Lỗi 6 — Dùng key trùng để ghi lịch sử

~~~properties
app.feature.enabled=false
app.feature.enabled=true
~~~

Hãy xóa dòng cũ hoặc dùng cơ chế override có chủ đích. Các khai báo trùng trong một tài liệu gây khó đọc và khó bảo trì.

### Lỗi 7 — Cho rằng một dòng khai báo tùy biến tự kích hoạt tính năng

~~~properties
app.feature.new-checkout=true
~~~

Dòng này chỉ tạo cấu hình. Tính năng thực sự hoạt động hay không phụ thuộc mã đọc `app.feature.new-checkout` hoặc điều kiện cấu hình liên quan.

## 17. Cách thực hành kiểm tra một key có được đọc đúng

Giả sử muốn đặt thời gian chờ HTTP client là `750ms`.

**Bước 1 — Viết key canonical trong tệp:**

~~~properties
app.client.connect-timeout=750ms
~~~

**Bước 2 — Tra giá trị thông qua `Environment`:**

~~~java
Duration timeout = environment.getProperty(
    "app.client.connect-timeout", Duration.class);
~~~

Nếu converter phù hợp có sẵn, kết quả là một `Duration` tương ứng 750 mili giây.

**Bước 3 — So sánh đầu vào khi chạy khác nhau:**

~~~bash
java -jar order-service.jar --app.client.connect-timeout=2s
~~~

Lúc này kết quả có thể trở thành 2 giây do tham số command-line ghi đè file. Đó là thay đổi **nguồn cấu hình hiệu lực**, không phải lỗi parser `.properties`.

**Bước 4 — Khi kết quả khác dự kiến, lần lượt kiểm tra:**

1. Dòng thực tế có bị comment, có thiếu `=` hoặc có escape ngoài ý muốn không?
2. Key viết chính xác chưa, đặc biệt prefix và dấu gạch ngang?
3. Value có ký tự thừa như `# ghi chú`, dấu nháy, tab, dấu cách cuối không?
4. Có key trùng trong cùng tệp hay không?
5. Có nguồn ưu tiên cao hơn ghi đè cùng key không?
6. Consumer cần kiểu gì, và phép chuyển kiểu có hợp lệ không?

Nếu ứng dụng dùng Spring Boot Actuator, những endpoint chẩn đoán cấu hình như `env` hoặc `configprops` có thể hỗ trợ quan sát nguồn và binding khi đã được kích hoạt, bảo vệ truy cập thích hợp. Không in token, mật khẩu hoặc thông tin nhạy cảm ra log chỉ để chứng minh parser hoạt động.

## 18. Bài tập đọc cú pháp

### Bài 1

Cho tệp:

~~~properties
app.count=4
app.title=Hello World
app.endpoint=https://example.test:9443/a?x=1
~~~

Hãy xác định ba cặp key/value. Đáp án: `app.count` → `4`, `app.title` → `Hello World`, `app.endpoint` → `https://example.test:9443/a?x=1`. Dấu `:` và `=` xuất hiện trong URL ở phía value không tạo thêm key.

### Bài 2

~~~properties
app.stage=prod # current
~~~

Giá trị có đúng bằng `prod` không? **Không.** Trong cú pháp properties, `# current` phía sau không tự trở thành comment. Nếu cần số hoặc enum hoặc chuỗi chính xác, phần thừa có thể gây lỗi. Chuyển ghi chú lên một dòng `# ...` riêng.

### Bài 3

~~~properties
app.path=C:\\logs\\archive
app.text=One\nTwo
~~~

Value của `app.path` có các backslash đơn như `C:\logs\archive`. Value của `app.text` chứa một ký tự xuống dòng giữa `One` và `Two`.

### Bài 4

~~~properties
app.word=Hello,\
  World
~~~

Giá trị logic là `Hello,World`: không có dấu cách tự sinh ở điểm nối. Muốn có `Hello, World`, cần đặt dấu cách trong dữ liệu gốc có chủ đích.

### Bài 5

~~~properties
app.client.timeout=5s
app.client.timeout=8s
~~~

Nếu hai dòng được đọc tuần tự trong cùng một tài liệu properties, khai báo sau thay khai báo trước, nên `app.client.timeout` mang value `8s` từ tài liệu đó. Tuy nhiên giá trị hiệu lực toàn ứng dụng còn phụ thuộc các property source ưu tiên cao hơn.

## 19. Bảng ghi nhớ cú pháp

| Muốn viết | Mẫu trong `application.properties` | Ghi nhớ |
| --- | --- | --- |
| Key/value đơn giản | `server.port=8080` | Ưu tiên `=` |
| Tên có nhiều cấp | `app.mail.retry-count=3` | `.` phân cấp, `kebab-case` cho từng phần |
| Chuỗi có dấu cách | `app.name=Order Service` | Không cần nháy |
| Comment | `# Cấu hình kết nối` | Đưa lên dòng riêng |
| Value rỗng | `app.optional-value=` | Khác với key không tồn tại |
| Ký tự xuống dòng | `app.text=One\nTwo` | `\n` là escape |
| Windows path | `app.path=C:\\data\\logs` | Gấp đôi backslash |
| Liên kết placeholder | `app.timeout=${app.default-timeout:5s}` | Spring giải quyết placeholder |
| Item trong danh sách | `app.items[0]=first` | Cấu trúc cho Binder |
| Tài liệu theo profile | `#---` rồi `spring.config.activate.on-profile=dev` | Tính năng Config Data của Spring Boot |

Hãy nhìn một dòng `application.properties` bằng hai bước liên tiếp: **parser đọc được key nào và chuỗi value nào**, sau đó **Spring Boot/bean nào tiêu thụ key đó và chuyển nó thành kiểu gì**. Tách rõ hai bước giúp tìm đúng nguyên nhân khi một dòng cấu hình trông hợp lệ nhưng ứng dụng vẫn vận hành khác dự kiến.
