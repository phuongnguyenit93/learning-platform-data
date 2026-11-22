# Phân giải chuỗi chứa placeholder qua Environment trong Spring Boot

## 1. Tình huống mở đầu: một chuỗi cần lấy giá trị từ cấu hình

Hãy tưởng tượng ứng dụng cần tạo thông điệp khởi động:

~~~text
Ứng dụng catalog đang chạy tại https://api.example.com:8443
~~~

Tuy nhiên, tên ứng dụng, máy chủ và cổng đều có thể thay đổi giữa máy cá nhân, môi trường kiểm thử và production. Nếu ghép cứng những giá trị ấy trong Java, mỗi lần thay môi trường phải sửa mã hoặc bổ sung logic riêng.

Spring cung cấp **placeholder cho thuộc tính** (*property placeholder*) với dạng:

~~~text
${property.name}
~~~

Khi phân giải, Spring tìm giá trị của `property.name` trong `Environment` và thay toàn bộ đoạn `${property.name}` bằng giá trị tìm được. Nhờ đó, một chuỗi mẫu có thể dùng các giá trị cấu hình mà Spring Boot đã tập hợp từ tệp, biến môi trường, Java System properties, tham số dòng lệnh và các nguồn khác.

Ví dụ `application.yaml`:

~~~yaml
spring:
  application:
    name: catalog

app:
  public-host: api.example.com
  public-port: 8443
  startup-message: "Ứng dụng ${spring.application.name} đang chạy tại https://${app.public-host}:${app.public-port}"
~~~

Nếu không có nguồn cấu hình nào khác ghi đè, chuỗi `app.startup-message` sau phân giải có giá trị:

~~~text
Ứng dụng catalog đang chạy tại https://api.example.com:8443
~~~

Với bài học này, bạn sẽ biết:

- Placeholder `${...}` là gì, lấy giá trị từ đâu và khác gì một chuỗi bình thường.
- Cách dùng `Environment.resolvePlaceholders(...)` và `Environment.resolveRequiredPlaceholders(...)`.
- Khi nào `Environment.getProperty(...)` cũng phân giải placeholder bên trong giá trị lấy từ cấu hình.
- Cách khai báo mặc định `${key:default}`, lồng nhau và thay thế nhiều placeholder trong một chuỗi.
- Ảnh hưởng của thứ tự nguồn cấu hình, profile, biến môi trường và tham số khởi chạy đến giá trị được thay thế.
- Những trường hợp lỗi khi thiếu khóa, vòng tham chiếu, tên khóa sai hoặc sử dụng placeholder chứa bí mật.

## 2. Ba thành phần cần phân biệt: khóa, giá trị và chuỗi mẫu

Xét tệp `application.properties`:

~~~properties
app.name=Catalog
app.host=localhost
app.port=8080
app.url=http://${app.host}:${app.port}
~~~

Có ba khái niệm:

1. **Khóa thuộc tính**: `app.host`, `app.port` hoặc `app.url`.
2. **Giá trị thuộc tính**: `localhost`, `8080` hoặc chuỗi chứa các placeholder.
3. **Chuỗi mẫu cần phân giải**: ví dụ `Kết nối tới ${app.url}`, có thể nằm trong tệp hoặc được tạo trực tiếp trong Java.

Với `app.url`, Spring phải thay hai biểu thức:

~~~text
Trước: http://${app.host}:${app.port}
Sau:   http://localhost:8080
~~~

Với một chuỗi mẫu khác:

~~~text
Trước: Sử dụng dịch vụ tại ${app.url}
Sau:   Sử dụng dịch vụ tại http://localhost:8080
~~~

Ở ví dụ sau, giá trị `app.url` tự chứa placeholder, nên việc phân giải có thể tiếp tục cho đến khi lấy được nội dung tương ứng. Điều quan trọng là **giá trị cuối cùng** đến từ các thuộc tính đang có hiệu lực trong `Environment`.

Placeholder không phải một khóa mới được tạo trong `Environment`. Nó là **cú pháp tham chiếu** tới một khóa đã có hoặc có giá trị mặc định nếu bạn khai báo.

## 3. Environment đứng ở vị trí nào?

`org.springframework.core.env.Environment` cung cấp giao diện đọc thuộc tính của ứng dụng và tra cứu các profile.

Các phương thức liên quan trực tiếp đến bài này:

~~~java
String getProperty(String key);

String getProperty(String key, String defaultValue);

<T> T getProperty(String key, Class<T> targetType);

String resolvePlaceholders(String text);

String resolveRequiredPlaceholders(String text);
~~~

Trong đó:

- `getProperty("app.host")`: lấy giá trị có hiệu lực của một **khóa**.
- `getProperty("app.host", "localhost")`: cung cấp giá trị dự phòng nếu khóa không có giá trị.
- `resolvePlaceholders("Địa chỉ: ${app.host}")`: phân giải placeholder bên trong một **chuỗi tùy ý**.
- `resolveRequiredPlaceholders("Địa chỉ: ${app.host}")`: phân giải chuỗi và yêu cầu những placeholder cần thiết phải có giá trị hoặc mặc định hợp lệ.

Spring Boot tập hợp nhiều nguồn thành các `PropertySource` có thứ tự trong `Environment`. Khi một placeholder tham chiếu `app.host`, bộ phân giải tìm theo cùng cơ chế tra cứu thuộc tính của môi trường.

Sơ đồ khái niệm:

~~~text
application.yaml ----------┐
application-prod.yaml -----┤
biến môi trường -----------┤
Java System properties ----┼--> PropertySources --> Environment
đối số --key=value --------┘                           |
                                                     app.host = ?
                                                         |
"Mở ${app.host}:${app.port}" -- resolvePlaceholders -----+
                                                         |
                                                         v
                                             "Mở api.example.com:8443"
~~~

**Không có một quy tắc riêng cho placeholder bỏ qua thứ tự nguồn.** Nếu cùng khóa xuất hiện ở nhiều nguồn, giá trị mà `Environment` trả về cho khóa đó là giá trị được sử dụng để thay thế.

## 4. resolvePlaceholders: phân giải chuỗi tùy ý, cho phép thiếu khóa

Đây là phương thức phổ biến khi bạn có một chuỗi mẫu do mã ứng dụng hoặc người dùng nội bộ cung cấp:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class TemplateService {

    private final Environment environment;

    public TemplateService(Environment environment) {
        this.environment = environment;
    }

    public String renderGreeting() {
        return environment.resolvePlaceholders(
                "Xin chào từ ${spring.application.name}!");
    }
}
~~~

Tệp `application.yaml`:

~~~yaml
spring:
  application:
    name: catalog-service
~~~

Kết quả:

~~~text
Xin chào từ catalog-service!
~~~

### 4.1. Nhiều placeholder trong một chuỗi

~~~java
String message = environment.resolvePlaceholders(
        "Ứng dụng ${spring.application.name} chạy trên ${app.host}:${app.port}");
~~~

Tệp cấu hình:

~~~properties
spring.application.name=order-service
app.host=localhost
app.port=9090
~~~

Kết quả:

~~~text
Ứng dụng order-service chạy trên localhost:9090
~~~

Bạn không cần gọi `getProperty(...)` ba lần rồi tự nối từng phần. Bộ phân giải thay từng tham chiếu trong chuỗi đã cho.

### 4.2. Nếu khóa không có giá trị thì sao?

Giả sử không có `app.region` trong nguồn cấu hình:

~~~java
String result = environment.resolvePlaceholders(
        "Đang chạy tại vùng ${app.region}");
~~~

Kết quả có thể vẫn là:

~~~text
Đang chạy tại vùng ${app.region}
~~~

`resolvePlaceholders(...)` theo hợp đồng **không bắt buộc mọi placeholder chưa tìm thấy phải gây lỗi**; nó để lại placeholder không giải quyết được. Đây là lý do phương thức này còn gọi là dạng phân giải **không nghiêm ngặt**.

Đừng hiểu rằng một placeholder còn nguyên văn là giá trị hợp lệ. Nếu đưa chuỗi này vào URL hoặc thông điệp nghiệp vụ, phần `${app.region}` có thể xuất hiện trực tiếp trong dữ liệu đầu ra.

### 4.3. Nếu không có placeholder trong chuỗi

~~~java
String value = environment.resolvePlaceholders(
        "Không có thành phần cần thay");
~~~

Kết quả giữ nguyên chuỗi. Bộ phân giải chỉ xử lý các đoạn phù hợp cú pháp placeholder.

### 4.4. Khi nào nên dùng?

`resolvePlaceholders(...)` phù hợp khi:

- Bạn muốn hiển thị một mẫu văn bản mà placeholder không bắt buộc có đủ.
- Chuỗi có thể chứa tham chiếu chưa cấu hình, và ứng dụng có quy tắc xử lý riêng sau đó.
- Một hệ thống mẫu cho phép giữ lại những placeholder chưa được phân giải để xử lý ở giai đoạn khác.

Với URL, đường dẫn bắt buộc, endpoint hệ thống hoặc thông số cần thiết để khởi động, việc âm thầm giữ placeholder còn nguyên văn thường **không phù hợp**. Hãy cân nhắc phương thức nghiêm ngặt.

## 5. resolveRequiredPlaceholders: yêu cầu placeholder phải phân giải được

Phương thức thứ hai có cùng mục đích thay giá trị, nhưng khác chính sách khi gặp placeholder thiếu:

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "https://${app.api.host}:${app.api.port}/orders");
~~~

Nếu `app.api.host` hoặc `app.api.port` không tồn tại và không có mặc định, phương thức sẽ ném một `IllegalArgumentException` vì không thể phân giải placeholder bắt buộc.

Ví dụ xử lý có thông điệp lỗi rõ ràng:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class ApiEndpointService {

    private final Environment environment;

    public ApiEndpointService(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        try {
            return environment.resolveRequiredPlaceholders(
                    "https://${app.api.host}:${app.api.port}/orders");
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException(
                    "Thiếu hoặc không hợp lệ cấu hình địa chỉ API", error);
        }
    }
}
~~~

Phương thức nghiêm ngặt hữu ích khi **ứng dụng phải từ chối chạy hoặc từ chối thực hiện tác vụ** nếu thiếu thông số thiết yếu.

Cần phân biệt:

| Câu hỏi | `resolvePlaceholders` | `resolveRequiredPlaceholders` |
| --- | --- | --- |
| Có thay placeholder có giá trị? | Có | Có |
| Có xử lý nhiều placeholder trong một chuỗi? | Có | Có |
| Có dùng giá trị mặc định trong placeholder? | Có | Có |
| Khóa không có giá trị và không có mặc định? | Có thể giữ nguyên placeholder | Ném lỗi khi không thể phân giải |
| Hợp với thông số bắt buộc? | Chỉ khi mã gọi kiểm tra tiếp | Phù hợp hơn |

### Một lưu ý về loại lỗi

`resolveRequiredPlaceholders(...)` bảo đảm **không còn placeholder bắt buộc chưa được giải quyết theo quy tắc của bộ phân giải**, nhưng không đảm bảo giá trị có định dạng nghiệp vụ hợp lệ.

Ví dụ:

~~~properties
app.api.port=not-a-port
~~~

Chuỗi:

~~~text
https://localhost:not-a-port/orders
~~~

vẫn có thể được phân giải đầy đủ về mặt placeholder, dù cổng không phải số hợp lệ. Muốn kiểm tra kiểu số, địa chỉ URI hoặc quy tắc nghiệp vụ, bạn còn cần **chuyển kiểu và validation** ở bước tiếp theo, chẳng hạn qua `@ConfigurationProperties`.

## 6. Giá trị mặc định: cú pháp ${key:default}

Placeholder có thể khai báo giá trị dự phòng ngay trong biểu thức:

~~~text
${property.name:default-value}
~~~

Ví dụ:

~~~java
String greeting = environment.resolveRequiredPlaceholders(
        "Xin chào, ${app.user:khách}!");
~~~

Nếu `app.user` tồn tại với giá trị `Minh`:

~~~text
Xin chào, Minh!
~~~

Nếu `app.user` không có giá trị:

~~~text
Xin chào, khách!
~~~

Vì đã có mặc định, `resolveRequiredPlaceholders(...)` không phải ném lỗi chỉ vì thiếu `app.user`.

### 6.1. Giá trị mặc định dùng cho nhiều loại cấu hình

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "http://${app.host:localhost}:${app.port:8080}/health");
~~~

Không có hai thuộc tính nào, chuỗi cuối là:

~~~text
http://localhost:8080/health
~~~

Nếu chỉ có:

~~~properties
app.port=9090
~~~

kết quả:

~~~text
http://localhost:9090/health
~~~

Mỗi placeholder được xử lý **độc lập**. Không cần mọi khóa cùng xuất hiện trong một tệp.

### 6.2. Default trong placeholder và default của getProperty khác nhau

Hai cách sau có thể cho kết quả giống nhau ở tình huống đơn giản, nhưng chúng làm việc với **đầu vào khác nhau**:

~~~java
String a = environment.getProperty("app.region", "local");

String b = environment.resolvePlaceholders(
        "${app.region:local}");
~~~

`getProperty(...)` bắt đầu từ **tên khóa cần đọc**. `resolvePlaceholders(...)` bắt đầu từ **một chuỗi mẫu cần thay thế**. Khi chuỗi mẫu chứa văn bản xung quanh hoặc nhiều placeholder, phương thức thứ hai thuận tiện hơn.

### 6.3. Giá trị rỗng không hoàn toàn giống giá trị thiếu

Nếu cấu hình có:

~~~properties
app.user=
~~~

thì khóa `app.user` vẫn có thể tồn tại với **giá trị chuỗi rỗng**. Trong trường hợp này, đừng mặc định rằng `${app.user:khách}` chắc chắn sẽ dùng chữ `khách`. Giá trị mặc định dùng khi không tìm thấy giá trị thuộc tính theo cơ chế phân giải, không phải bộ kiểm tra mọi chuỗi trống hoặc chỉ gồm khoảng trắng.

Nếu nghiệp vụ yêu cầu giá trị **không được rỗng**, hãy kiểm tra điều kiện này riêng.

## 7. Placeholder lồng nhau và giá trị dự phòng nhiều cấp

Spring hỗ trợ biểu thức có placeholder nằm trong placeholder khác. Cách dùng thường gặp là **chọn khóa dự phòng**.

Ví dụ:

~~~java
String host = environment.resolveRequiredPlaceholders(
        "${app.host:${fallback.host:localhost}}");
~~~

Các trường hợp:

| Thuộc tính có mặt | Kết quả |
| --- | --- |
| `app.host=prod.example.com` | `prod.example.com` |
| Không có `app.host`, có `fallback.host=backup.example.com` | `backup.example.com` |
| Không có cả hai | `localhost` |

Quy tắc được đọc như sau:

1. Ưu tiên giá trị của `app.host`.
2. Nếu không tìm được, dùng giá trị của `fallback.host`.
3. Nếu cả hai không có, dùng chuỗi `localhost`.

Điều này giúp mô tả thứ tự dự phòng mà không cần viết logic `if/else` riêng trong Java.

### 7.1. Một khóa có giá trị chứa placeholder khác

Tệp cấu hình:

~~~properties
app.host=api.example.com
app.port=8443
app.base-url=https://${app.host}:${app.port}
app.orders-url=${app.base-url}/orders
~~~

Trong trường hợp thông thường:

~~~java
String orders = environment.getProperty("app.orders-url");
~~~

có thể nhận:

~~~text
https://api.example.com:8443/orders
~~~

Khi lấy giá trị thuộc tính chuỗi qua `PropertySourcesPropertyResolver` của `Environment`, các placeholder lồng trong **giá trị thuộc tính** cũng được phân giải theo cơ chế thích hợp. Bạn không nhất thiết phải gọi `resolvePlaceholders(...)` thêm một lần cho mỗi khóa trong chuỗi tham chiếu.

Tuy nhiên, nếu bản thân **mã Java** tạo ra chuỗi mẫu tùy ý:

~~~java
String template = "Kết nối đến ${app.orders-url}";
~~~

thì việc gọi `environment.resolvePlaceholders(template)` giúp phân giải chuỗi này.

### 7.2. Có thể lồng placeholder trong phần tên khóa

Một mẫu khác là:

~~~text
${app.${app.target}.url}
~~~

Nếu có:

~~~properties
app.target=orders
app.orders.url=https://orders.example.com
~~~

thì khóa bên trong có thể được phân giải thành `orders` để tạo ra tên khóa `app.orders.url`, sau đó lấy giá trị URL.

Cách này có thể phù hợp với một mẫu cấu hình có cấu trúc đặt tên rõ ràng, nhưng đọc khó hơn những tên khóa tường minh. Chỉ sử dụng khi thật sự có nhu cầu lựa chọn khóa động; với nhiều nhóm cấu hình có kiểu, `@ConfigurationProperties` thường dễ bảo trì hơn.

### 7.3. Tránh vòng tham chiếu

Ví dụ:

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Không có giá trị cuối độc lập để hoàn tất phân giải. Đây là **vòng tham chiếu**. Bộ phân giải có thể báo lỗi do tham chiếu vòng hoặc không thể hoàn tất việc thay thế.

Đừng dùng chuỗi placeholder vòng để mô tả mặc định giữa hai thuộc tính. Hãy chọn một khóa có giá trị thực hoặc một mặc định cụ thể làm điểm kết thúc:

~~~properties
app.b=localhost
app.a=${app.b}
~~~

## 8. Cách Environment chọn giá trị để thay

Một placeholder không tự chỉ định tệp nguồn. Nó nêu **tên thuộc tính**, còn `Environment` chịu trách nhiệm tìm trong các `PropertySource`.

Ví dụ:

~~~yaml
# application.yaml
app:
  region: local
  message: "Đang phục vụ tại ${app.region}"
~~~

Khi chạy:

~~~bash
java -jar app.jar --app.region=asia-east
~~~

theo thứ tự ưu tiên mặc định của Spring Boot, command-line property `app.region=asia-east` thắng giá trị `local` trong YAML.

Vì vậy:

~~~java
String message = environment.getProperty("app.message");
~~~

có thể trả về:

~~~text
Đang phục vụ tại asia-east
~~~

Điểm quan trọng là `app.message` nằm trong `application.yaml` nhưng placeholder `${app.region}` **không bị cố định** vào giá trị `app.region` cùng tệp. Nó sử dụng giá trị mà `Environment` phân giải được.

### 8.1. Thứ tự nguồn thường gặp

Trong một lần chạy Spring Boot thông thường, các nguồn đáng chú ý gồm:

- Config Data: `application.properties`/YAML, cấu hình theo profile, cấu hình ngoài JAR và các import.
- Biến môi trường của hệ điều hành.
- Java System properties, ví dụ `-Dapp.region=...`.
- Tùy chọn dòng lệnh, ví dụ `--app.region=...`.

Các nguồn có **thứ tự ưu tiên**; trong trường hợp thông thường, option dòng lệnh có thể ghi đè Java System properties, biến môi trường và Config Data. Những nguồn riêng cho kiểm thử hoặc Devtools có thể làm thứ tự tổng thể khác đi.

Ví dụ:

~~~bash
APP_REGION=env-value \
java -Dapp.region=jvm-value -jar app.jar \
  --app.region=cli-value
~~~

Khi mọi nguồn trên đều được Spring Boot nhận theo cấu hình mặc định, `${app.region}` có kết quả `cli-value`.

Nếu bỏ `--app.region=cli-value`, giá trị `jvm-value` có thể thắng. Nếu bỏ tiếp `-Dapp.region=jvm-value`, giá trị từ biến môi trường có thể thắng.

### 8.2. Profile quyết định những tài liệu nào được tham gia

Tệp nền:

~~~yaml
# application.yaml
app:
  host: localhost
  endpoint: "https://${app.host}/api"
~~~

Tệp production:

~~~yaml
# application-prod.yaml
app:
  host: api.example.com
~~~

Nếu chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

thì `application-prod.yaml` có thể cung cấp `app.host` và kết quả phân giải `app.endpoint` là:

~~~text
https://api.example.com/api
~~~

Nếu có nguồn ưu tiên cao hơn ghi đè `app.host`, placeholder sẽ lấy giá trị từ nguồn đó. Profile không tạo một phạm vi tên khóa riêng chỉ cho placeholder.

## 9. Ví dụ hoàn chỉnh với Environment và ApplicationRunner

Tạo một ứng dụng Spring Boot với cấu hình:

~~~yaml
# src/main/resources/application.yaml
spring:
  application:
    name: billing-service

app:
  public-host: localhost
  public-port: 8080
  protocol: http
  public-url: "${app.protocol}://${app.public-host}:${app.public-port}"
  welcome-template: "Chào mừng đến ${spring.application.name} tại ${app.public-url}"
~~~

Lớp khởi động:

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PlaceholderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
~~~

Thêm runner để quan sát:

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PlaceholderDemoRunner implements ApplicationRunner {

    private final Environment environment;

    public PlaceholderDemoRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String direct = environment.getProperty("app.public-url");

        String fromTemplate = environment.resolvePlaceholders(
                "Ứng dụng đang phục vụ ở ${app.public-url}");

        String required = environment.resolveRequiredPlaceholders(
                "Tên ứng dụng: ${spring.application.name}");

        System.out.println("Direct URL: " + direct);
        System.out.println("Template: " + fromTemplate);
        System.out.println("Required: " + required);
    }
}
~~~

Với cấu hình mặc định, đầu ra minh họa:

~~~text
Direct URL: http://localhost:8080
Template: Ứng dụng đang phục vụ ở http://localhost:8080
Required: Tên ứng dụng: billing-service
~~~

Chạy lại và ghi đè qua CLI:

~~~bash
java -jar app.jar \
  --app.protocol=https \
  --app.public-host=billing.example.com \
  --app.public-port=443
~~~

Kết quả:

~~~text
Direct URL: https://billing.example.com:443
Template: Ứng dụng đang phục vụ ở https://billing.example.com:443
Required: Tên ứng dụng: billing-service
~~~

Đây là ví dụ liên kết hai tính năng:

1. Spring Boot hợp nhất các nguồn cấu hình thành giá trị có hiệu lực.
2. Spring Framework phân giải placeholder bằng cách truy vấn những giá trị có hiệu lực ấy.

**Lưu ý:** ví dụ in các giá trị mẫu công khai để dễ quan sát. Trong ứng dụng thật, không in mật khẩu, khóa bí mật, token hoặc nội dung nhạy cảm sau phân giải.

## 10. resolvePlaceholders và getProperty có quan hệ gì?

Hai lời gọi dưới đây thường được sử dụng cho hai mục đích khác nhau:

~~~java
String one = environment.getProperty("app.public-url");

String two = environment.resolvePlaceholders(
        "${app.public-url}");
~~~

Trong trường hợp thuộc tính hiện diện và cách xử lý phù hợp, cả hai có thể trả về cùng một URL. Nhưng chúng **không phải cùng API**:

- `getProperty(...)` nhận **tên khóa**, tìm giá trị và có thể chuyển kiểu qua các overload tương ứng.
- `resolvePlaceholders(...)` nhận **một chuỗi bất kỳ** và tìm các biểu thức placeholder bên trong nó.
- `resolveRequiredPlaceholders(...)` cũng nhận chuỗi bất kỳ nhưng có chính sách nghiêm ngặt hơn khi thiếu giá trị.

Ví dụ:

~~~java
environment.getProperty("Hello ${app.public-host}");
~~~

không có nghĩa “hãy tìm host rồi ghép chữ Hello”. Nó đang yêu cầu một thuộc tính có **tên đúng bằng toàn bộ chuỗi** `Hello ${app.public-host}`. Nếu không có khóa ấy, kết quả thường là `null`.

Muốn ghép chuỗi mẫu, dùng:

~~~java
environment.resolvePlaceholders(
        "Hello ${app.public-host}");
~~~

### Lấy giá trị mặc định của getProperty

~~~java
String host = environment.getProperty(
        "app.public-host", "localhost");
~~~

Đây là một cách chỉ định mặc định **cho lời gọi lấy khóa**. Nó phù hợp khi bạn chỉ cần một thuộc tính, và có thể dễ kết hợp với xử lý kiểu đích.

Còn:

~~~java
String text = environment.resolvePlaceholders(
        "Host hiện tại: ${app.public-host:localhost}");
~~~

là mặc định đặt **bên trong biểu thức của chuỗi mẫu**.

### Lấy giá trị có kiểu

~~~java
Integer port = environment.getProperty(
        "app.public-port", Integer.class, 8080);
~~~

Phương thức phân giải placeholder trả về **String**. Nếu cần `int`, `Duration`, `URI` hay các kiểu khác, nên dùng phương thức đọc có kiểu hoặc `@ConfigurationProperties` để Spring thực hiện chuyển kiểu tương ứng.

## 11. @Value dùng placeholder như thế nào?

Trong bean được Spring quản lý, cách phổ biến là dùng `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AppMessage {

    private final String message;

    public AppMessage(
            @Value("${app.welcome-template:Chào bạn}") String message) {
        this.message = message;
    }

    public String text() {
        return message;
    }
}
~~~

`@Value("${...}")` yêu cầu cơ chế của Spring phân giải placeholder khi tiêm giá trị vào bean. Giá trị lấy từ `Environment` và các nguồn cấu hình hiện có.

Nếu tệp YAML chứa:

~~~yaml
app:
  welcome-template: "Chào mừng đến ${spring.application.name}"
~~~

thì giá trị được tiêm có thể là chuỗi đã phân giải, ví dụ `Chào mừng đến billing-service`.

### Khác biệt giữa @Value và gọi Environment trực tiếp

| Đặc điểm | `@Value("${...}")` | `Environment.resolvePlaceholders(...)` |
| --- | --- | --- |
| Nơi thường dùng | Điểm tiêm phụ thuộc trong bean Spring | Bất kỳ mã có tham chiếu `Environment` |
| Khi thực hiện | Trong quá trình Spring tạo/cấu hình bean | Tại thời điểm mã gọi phương thức |
| Dạng đầu vào | Biểu thức trong annotation | Chuỗi `String` do mã cung cấp |
| Đọc nhiều placeholder | Có thể | Có |
| Chính sách khi thiếu khóa | Phụ thuộc bộ xử lý placeholder của context, có thể làm bean không khởi tạo được | Tường minh qua `resolvePlaceholders` hoặc `resolveRequiredPlaceholders` |

Không nên giả định `@Value` hoàn toàn tương đương mọi chi tiết của một lời gọi `resolvePlaceholders(...)` tự viết. `@Value` đi qua hệ thống xử lý bean và có thể kết hợp những khả năng khác của Spring.

### Phân biệt placeholder với SpEL

Hai cú pháp trông giống nhau nhưng có ý nghĩa khác:

~~~java
@Value("${app.port:8080}")
int port;
~~~

và:

~~~java
@Value("#{2 * 3}")
int number;
~~~

- `${...}`: placeholder cho một **thuộc tính cấu hình**.
- `#{...}`: biểu thức **Spring Expression Language (SpEL)**.

`Environment.resolvePlaceholders(...)` không phải một trình đánh giá SpEL. Đừng mong:

~~~java
environment.resolvePlaceholders("#{2 * 3}");
~~~

tự thực hiện phép nhân. Nếu không có cú pháp `${...}` cần thay, phương thức chủ yếu trả lại chuỗi như đã nhận.

## 12. @ConfigurationProperties và placeholder bên trong tệp

Với nhiều thuộc tính liên quan, `@ConfigurationProperties` thường giúp tổ chức tốt hơn `@Value` rải rác.

Tệp `application.yaml`:

~~~yaml
app:
  api:
    protocol: https
    host: localhost
    port: 8443
    base-url: "${app.api.protocol}://${app.api.host}:${app.api.port}"
    timeout: 5s
~~~

Một record cấu hình:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(
        String protocol,
        String host,
        int port,
        URI baseUrl,
        Duration timeout) {
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(ApiProperties.class)` trong cấu hình.

Sau đó:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ApiClientSettings {

    private final ApiProperties properties;

    public ApiClientSettings(ApiProperties properties) {
        this.properties = properties;
    }

    public URI baseUrl() {
        return properties.baseUrl();
    }
}
~~~

Bộ gắn kết của Spring Boot đọc các giá trị cấu hình hiệu lực, xử lý các tham chiếu cần thiết, rồi chuyển chúng sang kiểu `URI`, `Duration` hoặc `int` tương ứng. `base-url` được ánh xạ với trường Java `baseUrl` theo quy tắc *relaxed binding*.

**Không nhầm phạm vi:** `@ConfigurationProperties` là cơ chế gắn và chuyển kiểu cấu hình, còn `Environment.resolvePlaceholders(...)` là API phân giải **chuỗi mẫu**. Hai cơ chế có thể phối hợp, nhưng không nên thay toàn bộ việc gắn cấu hình có kiểu bằng những chuỗi mẫu dài nếu ứng dụng cần validation và cấu trúc rõ ràng.

## 13. Tên khóa trong placeholder và quy tắc đặt tên

Trong Spring Boot, nên viết placeholder dùng **tên thuộc tính dạng chuẩn (canonical form)**, thường là chữ thường, dấu chấm phân cấp và dấu gạch ngang giữa các từ:

~~~text
${app.api.base-url}
${app.retry-count}
${spring.application.name}
~~~

Cách viết này thuận lợi cho khả năng ánh xạ từ các nguồn cấu hình khác nhau của Spring Boot.

Ví dụ với một nhóm cấu hình:

~~~yaml
app:
  api:
    base-url: "https://example.com"
~~~

Placeholder:

~~~text
${app.api.base-url}
~~~

khớp ý định rõ ràng hơn một biến thể tùy tiện về chữ hoa/thường.

Trong môi trường triển khai, tên biến môi trường theo quy tắc gắn kết chuẩn thường chuyển từ:

~~~text
app.api.base-url
~~~

thành:

~~~text
APP_API_BASEURL
~~~

Quy tắc cho `@ConfigurationProperties` là thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch ngang và viết hoa. Chi tiết tra cứu của `Environment` và chuẩn hóa tên có thể khác tùy loại `PropertySource`; vì vậy, khi viết `${...}` trong cấu hình Spring Boot, dùng tên khóa chuẩn sẽ giúp các cơ chế phối hợp dễ dự đoán hơn.

### Placeholder không tự sửa tên khóa bị sai

Giả sử cấu hình có:

~~~properties
app.api.host=api.example.com
~~~

nhưng chuỗi mẫu tham chiếu:

~~~text
${app.ap1.host}
~~~

chữ `i` bị gõ thành số `1`. Bộ phân giải không đoán ý định để lấy `app.api.host`. Dạng nghiêm ngặt sẽ báo lỗi thiếu khóa, dạng không nghiêm ngặt có thể để lại placeholder.

Điều này giúp lý giải tại sao lỗi chính tả trong placeholder đôi khi bị phát hiện khi khởi động, đôi khi lại chỉ xuất hiện dưới dạng chuỗi chưa được thay thế ở thời điểm chạy.

## 14. Placeholder có thể lồng vào nhiều lớp PropertySource

Một chuỗi mẫu chỉ chứa một tên khóa, nhưng chính tên khóa ấy có thể có nhiều nguồn định nghĩa.

Ví dụ nguồn trong JAR:

~~~yaml
# application.yaml
app:
  endpoint:
    host: localhost
    url: "http://${app.endpoint.host}:8080/api"
~~~

Tệp ngoài JAR:

~~~yaml
# ./config/application-prod.yaml
app:
  endpoint:
    host: internal-api
~~~

Biến môi trường:

~~~bash
APP_ENDPOINT_HOST=gateway.example.com
~~~

Tham số dòng lệnh:

~~~bash
--app.endpoint.host=public.example.com
~~~

Nếu profile `prod` hoạt động và tất cả nguồn này cùng tham gia, giá trị hiệu lực `app.endpoint.host` sẽ chịu thứ tự ưu tiên của Spring Boot. Trong lần chạy bình thường, tham số CLI có thể thắng các giá trị còn lại, khiến:

~~~text
app.endpoint.url = http://public.example.com:8080/api
~~~

Người học cần tách rõ hai câu hỏi:

1. **Placeholder chỉ đến khóa nào?** Ở đây là `app.endpoint.host`.
2. **Khóa ấy lấy giá trị ở đâu?** `Environment` quyết định qua tập `PropertySource` và thứ tự ưu tiên.

Không có bước “placeholder trong application.yaml thì chỉ được đọc application.yaml”. Nó truy cập môi trường cấu hình tổng hợp.

## 15. Các lỗi thường gặp khi phân giải placeholder

### 15.1. Quên dấu ngoặc hoặc đặt sai cú pháp

Sai:

~~~text
¤app.host
${app.host
¤app.host}
~~~

Đúng:

~~~text
${app.host}
~~~

Placeholder phải có dấu `$`, dấu ngoặc mở `{` và dấu ngoặc đóng `}` phù hợp. Nếu biểu thức không khớp cú pháp, bộ phân giải có thể coi đó là văn bản thông thường hoặc không thể hoàn tất thay thế.

### 15.2. Nhầm chuỗi mẫu với tên khóa getProperty

~~~java
environment.getProperty("Hello ${app.name}");
~~~

Cách trên tìm một khóa có tên là **toàn bộ chuỗi**, chứ không ghép lời chào. Hãy dùng:

~~~java
environment.resolvePlaceholders("Hello ${app.name}");
~~~

### 15.3. Dùng resolvePlaceholders cho giá trị bắt buộc mà không kiểm tra

~~~java
String url = environment.resolvePlaceholders(
        "https://${app.remote.host}/api");
~~~

Nếu khóa thiếu, URL có thể còn `${app.remote.host}`. Với cấu hình bắt buộc, dùng `resolveRequiredPlaceholders(...)` hoặc validation tại bước gắn cấu hình.

### 15.4. Nghĩ default là bộ kiểm tra mọi giá trị rỗng

~~~text
${app.user:guest}
~~~

Nếu khóa có giá trị chuỗi rỗng, không nhất thiết được thay thành `guest`. Trách nhiệm xác minh chuỗi không rỗng thuộc về validation của ứng dụng.

### 15.5. Tạo vòng tham chiếu

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Không có điểm kết thúc. Hãy thay bằng giá trị thực hoặc nhánh mặc định không tạo vòng.

### 15.6. Dùng sai tên biến môi trường

Giả sử muốn đọc `app.retry-count` nhưng đặt biến môi trường sai quy ước tên. Điều này khiến placeholder có thể không tìm thấy giá trị mong muốn. Với cách đặt tên của Spring Boot, nên kiểm tra chính xác biến tương ứng và viết tên placeholder dạng chuẩn.

### 15.7. Cho rằng placeholder tự lấy giá trị mới ngay khi tệp đổi

Spring Boot thường nạp Config Data khi ứng dụng khởi động. Thay `application.yaml` trên đĩa không tự bảo đảm `Environment` được nạp lại hoặc bean dùng `@Value` được cấu hình lại. Những hệ thống cần làm mới động phải có cơ chế riêng.

### 15.8. Đưa giá trị bí mật vào chuỗi log

~~~java
String text = environment.resolvePlaceholders(
        "Token: ${service.auth.token}");
System.out.println(text);
~~~

Ví dụ trên có thể làm lộ token nếu `service.auth.token` tồn tại. Placeholder không tự che dữ liệu nhạy cảm. Khi cần chẩn đoán, hãy log tên khóa hoặc trạng thái có/không có, tránh in giá trị bí mật.

### 15.9. Nghĩ placeholder thay được mọi loại biểu thức

`${...}` là cú pháp tham chiếu thuộc tính. Nó không phải shell expansion, không tự gọi API bên ngoài, không tính biểu thức SpEL `#{...}` và không thực hiện phép toán nghiệp vụ tùy ý.

Nếu bạn cần ghép URL, tên file hoặc thông điệp từ cấu hình, placeholder phù hợp. Nếu cần logic điều kiện phức tạp, kiểm tra giá trị và tạo đối tượng có kiểu trong Java sẽ rõ ràng hơn.

### 15.10. Lồng placeholder quá phức tạp

Một biểu thức có nhiều mức như:

~~~text
${app.host:${fallback.host:${global.host:localhost}}}
~~~

có thể hợp lệ theo cách phân giải lồng nhau, nhưng khó đọc nếu xuất hiện ở nhiều nơi. Khi chuỗi cấu hình trở thành một cây lựa chọn dài, hãy cân nhắc thiết kế lại khóa cấu hình để dễ bảo trì và dễ kiểm thử.

## 16. Cách chẩn đoán giá trị thực tế trong ứng dụng

Khi chuỗi đã phân giải không như kỳ vọng, hãy kiểm tra từ **khóa** đến **nguồn** rồi đến **chuỗi mẫu**.

### Bước 1: xác định khóa được tham chiếu

Ví dụ:

~~~text
https://${app.api.host}:${app.api.port:8443}
~~~

Các khóa là `app.api.host` và `app.api.port`. Đừng nhầm `8443` là tên khóa; nó là **giá trị mặc định**.

### Bước 2: kiểm tra các giá trị có hiệu lực

Trong môi trường phát triển, với dữ liệu không nhạy cảm:

~~~java
String host = environment.getProperty("app.api.host");
String port = environment.getProperty("app.api.port");

System.out.println("Host configured: " + (host != null));
System.out.println("Port configured: " + (port != null));
~~~

Cách trên chỉ xác định sự có mặt, không in giá trị. Nếu cần kiểm tra chính xác, chỉ dùng dữ liệu mẫu an toàn.

### Bước 3: phân giải bằng API phù hợp

~~~java
String permissive = environment.resolvePlaceholders(
        "${app.api.host}:${app.api.port:8443}");

String strict = environment.resolveRequiredPlaceholders(
        "${app.api.host}:${app.api.port:8443}");
~~~

Quan sát sự khác nhau khi cố ý bỏ `app.api.host`.

### Bước 4: kiểm tra thứ tự nguồn

Nếu kết quả khác với tệp YAML đang đọc, hãy xác định có biến môi trường, Java System property, tham số CLI hay profile nào đang tác động không.

Khi cần xem danh sách nguồn mà không in giá trị bí mật:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void listSources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

`ConfigurableEnvironment` cung cấp quyền truy cập các `PropertySource` có thứ tự. Tên nguồn có thể chỉ ra loại nguồn hoặc vị trí tệp, giúp xác định nơi có thể đang ghi đè khóa.

### Bước 5: kiểm tra thời điểm tạo bean

Nếu một bean nhận giá trị bằng `@Value` tại thời điểm khởi tạo, việc đọc lại `Environment` sau này có thể không đồng nghĩa với việc trường của bean đã thay đổi. Cần xác định cơ chế cập nhật cấu hình của ứng dụng trước khi kết luận hai nơi phải luôn phản ánh cùng một giá trị.

## 17. Bài thực hành từng bước

### Bài 1: phân giải nhiều giá trị

Cấu hình:

~~~properties
app.name=orders
app.host=localhost
app.port=8181
~~~

Mã:

~~~java
String text = environment.resolveRequiredPlaceholders(
        "Service ${app.name}: http://${app.host}:${app.port}");
~~~

**Đáp án:**

~~~text
Service orders: http://localhost:8181
~~~

### Bài 2: so sánh permissive và strict

Giả sử không có `app.zone`:

~~~java
String a = environment.resolvePlaceholders(
        "Zone = ${app.zone}");

String b = environment.resolveRequiredPlaceholders(
        "Zone = ${app.zone}");
~~~

**Đáp án:** `a` có thể giữ nguyên `Zone = ${app.zone}`. `b` báo lỗi vì placeholder bắt buộc không phân giải được.

### Bài 3: thêm giá trị mặc định

Không có `app.zone`:

~~~java
String text = environment.resolveRequiredPlaceholders(
        "Zone = ${app.zone:local}");
~~~

**Đáp án:**

~~~text
Zone = local
~~~

### Bài 4: tham chiếu lồng nhau

Cấu hình:

~~~properties
service.host=api.internal
service.port=8088
service.base-url=http://${service.host}:${service.port}
service.health-url=${service.base-url}/health
~~~

Hỏi `environment.getProperty("service.health-url")` trả gì trong trường hợp thông thường?

**Đáp án:**

~~~text
http://api.internal:8088/health
~~~

Giải thích: giá trị `service.health-url` tham chiếu `service.base-url`, mà khóa này lại tham chiếu `service.host` và `service.port`.

### Bài 5: nguồn ưu tiên ghi đè giá trị tham chiếu

Trong `application.yaml`:

~~~yaml
app:
  host: localhost
  endpoint: "https://${app.host}/v1"
~~~

Khởi chạy:

~~~bash
java -jar app.jar --app.host=public.example.com
~~~

Hỏi `environment.getProperty("app.endpoint")` trả gì?

**Đáp án:** `https://public.example.com/v1`, nếu không có nguồn ưu tiên cao hơn thay `app.endpoint`. Lý do: placeholder tham chiếu giá trị hiệu lực `app.host` từ `Environment`.

### Bài 6: phân biệt getProperty và resolvePlaceholders

Cấu hình:

~~~properties
app.name=billing
~~~

Mã:

~~~java
String a = environment.getProperty("app.name");
String b = environment.resolvePlaceholders("Xin chào ${app.name}");
String c = environment.getProperty("Xin chào ${app.name}");
~~~

**Đáp án:**

- `a` là `billing`.
- `b` là `Xin chào billing`.
- `c` thông thường là `null` vì không có thuộc tính tên `Xin chào ${app.name}`.

### Bài 7: sử dụng profile

Tệp `application.yaml`:

~~~yaml
app:
  host: localhost
  url: "https://${app.host}/v1"
~~~

Tệp `application-prod.yaml`:

~~~yaml
app:
  host: api.production.test
~~~

Chạy với `--spring.profiles.active=prod`. Hỏi `app.url` là gì?

**Đáp án:** `https://api.production.test/v1`, giả sử không có nguồn ưu tiên cao hơn ghi đè các khóa liên quan.

### Bài 8: đặt mặc định nhiều cấp

Mẫu:

~~~text
${app.host:${fallback.host:localhost}}
~~~

Hãy thử ba cấu hình: có `app.host`; chỉ có `fallback.host`; không có cả hai. Theo thứ tự, kết quả lần lượt lấy từ `app.host`, `fallback.host` và chuỗi mặc định `localhost`.

### Bài 9: kiểm tra cú pháp SpEL

Mã:

~~~java
String x = environment.resolvePlaceholders("#{4 + 5}");
~~~

Hỏi `x` có chắc bằng `9` không?

**Đáp án:** Không. Phương thức này phân giải property placeholder dạng `${...}`, không phải bộ đánh giá SpEL. `#{4 + 5}` là cú pháp khác.

### Bài 10: nhận diện rủi ro

Mẫu:

~~~text
Kết nối bằng mật khẩu ${db.password}
~~~

Có nên in trực tiếp kết quả của `resolveRequiredPlaceholders(...)` vào log production không?

**Đáp án:** Không. Dù phân giải đúng, chuỗi có thể chứa bí mật. Chỉ kiểm tra sự tồn tại hoặc thông báo trạng thái đã che giá trị.

## 18. Chọn công cụ nào cho từng mục đích?

| Nhu cầu | API/cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Lấy một khóa ở dạng chuỗi | `Environment.getProperty("app.name")` | Ngắn gọn và trực tiếp. |
| Lấy khóa với dự phòng | `getProperty("app.name", "demo")` | Mặc định tại điểm đọc. |
| Lấy khóa có kiểu | `getProperty("app.port", Integer.class)` | Chuyển kiểu dữ liệu. |
| Phân giải các placeholder trong chuỗi bất kỳ | `resolvePlaceholders("URL: ${app.url}")` | Thay các tham chiếu có thể phân giải được. |
| Yêu cầu mọi placeholder bắt buộc có giá trị | `resolveRequiredPlaceholders("${app.url}")` | Báo lỗi khi thiếu tham chiếu bắt buộc. |
| Tiêm một giá trị vào bean khi tạo | `@Value("${app.url}")` | Tích hợp với cơ chế tạo bean. |
| Gắn cả nhóm cấu hình vào record/POJO | `@ConfigurationProperties` | Có kiểu dữ liệu và cấu trúc rõ ràng. |
| Kiểm tra profile, nguồn và thứ tự cấu hình | `Environment` / `ConfigurableEnvironment` | Hiểu vì sao một khóa có giá trị đang thấy. |

## 19. Tổng kết

- `${property.name}` là một **tham chiếu cấu hình**, không phải một phép tính và không phải một biến Java.
- `Environment` tìm giá trị của khóa trong những `PropertySource` có hiệu lực theo thứ tự ưu tiên.
- `resolvePlaceholders(...)` xử lý chuỗi mẫu và có thể giữ nguyên placeholder chưa phân giải.
- `resolveRequiredPlaceholders(...)` yêu cầu placeholder phải có giá trị hoặc mặc định phù hợp, nếu không sẽ báo lỗi.
- `${key:default}` cho phép dùng giá trị dự phòng; các placeholder có thể lồng nhau.
- Khi thuộc tính được đọc từ `Environment`, giá trị của nó có thể chứa các placeholder khác và được phân giải tiếp.
- `@Value` và `@ConfigurationProperties` sử dụng hạ tầng cấu hình Spring nhưng có mục đích khác nhau: tiêm giá trị đơn hoặc gắn cả nhóm cấu hình.
- Placeholder không tự xác minh nội dung nghiệp vụ, không tự làm mới cấu hình đang chạy và không bảo vệ bí mật.

Hãy tập thói quen xác định **khóa được tham chiếu**, **giá trị có hiệu lực của khóa** và **chính sách khi khóa thiếu**. Ba yếu tố này giải thích phần lớn tình huống chuỗi có `${...}` được thay đúng, bị giữ nguyên hoặc gây lỗi trong ứng dụng Spring Boot.

## Tài liệu tham khảo

- [Spring Framework — Environment và Property Resolution](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).
- [Spring Framework — PropertyResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/PropertyResolver.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).