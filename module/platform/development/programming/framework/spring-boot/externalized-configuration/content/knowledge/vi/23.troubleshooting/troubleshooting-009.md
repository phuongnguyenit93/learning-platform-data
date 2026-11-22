# Xử lý danh sách bị thay thế, Map sai khóa và biến môi trường sai tên trong Spring Boot

## 1. Mục tiêu

Khi vận hành ứng dụng Spring Boot, có những tình huống configuration file nhìn có vẻ đúng, ứng dụng vẫn khởi động, nhưng dữ liệu nhận được trong `@ConfigurationProperties` lại sai:

- File cơ sở có ba server; file production chỉ override một server nhưng **List** kết quả chỉ còn một.
- Một route Map dùng khóa `/api/v1`; sau binding, ứng dụng không tìm thấy key có dấu slash.
- Một key Map có dấu chấm `service.alpha` bị xem thành cấu trúc nested thay vì key nguyên vẹn.
- Operator cấp biến môi trường `APP_CLIENT_RETRY_MAX_ATTEMPTS` nhưng bean vẫn nhận default; tên canonical cần dạng khác.
- Một Map key được đặt chữ hoa qua biến môi trường nhưng khi binding lại trở thành lowercase.
- Có indexed properties trong `Environment` nhưng `Environment.getProperty("app.servers")` trả `null`, khiến người điều tra nhầm tưởng List rỗng.

Đây là các vấn đề thuộc chủ đề **Chẩn đoán lỗi Spring Boot Externalized Configuration**. Người học cần xác định lỗi nằm ở đâu trong chuỗi **nguồn cấu hình → thứ tự ưu tiên → tên property → Binder → object Java**, thay vì sửa ngẫu nhiên nhiều file và đoán kết quả.

Ba quy tắc phải nhớ:

1. **List:** khi nhiều property sources khai báo cùng một danh sách, danh sách ở nguồn ưu tiên cao hơn thay thế toàn bộ danh sách. Không có phép nối List hoặc merge fields của từng List element theo ý muốn.
2. **Map:** các khóa và thuộc tính nested có thể được tổng hợp từ nhiều sources; cùng một property path vẫn tuân theo precedence. Literal Map key có ký tự đặc biệt cần cú pháp phù hợp.
3. **Environment variables:** chuyển từ tên canonical sang tên môi trường bằng cách thay dấu chấm bằng underscore, **xóa dấu gạch nối**, rồi uppercase; indexed List sử dụng `_0_`, `_1_`. Khi binding Map, tên key lấy từ environment có thể thành lowercase.

Các ví dụ sử dụng những quy tắc của Spring Boot Binder và `@ConfigurationProperties`. Nếu một ứng dụng dùng custom converter, custom `PropertySource` hoặc tự parse một file bằng thư viện khác, hành vi cụ thể cần được kiểm chứng riêng.

## 2. Luồng đi của cấu hình

~~~text
application.yml / application-prod.yml
        |
  Spring Boot Config Data
        |
        +-------- OS environment variables
        |                |
        +------ JVM system properties
        |                |
        +------ command-line arguments
        |
        v
    Environment
        |
        v
 PropertySource precedence
        |
        v
  Spring Boot Binder
        |
  +-----+---------+--------+
  |               |        |
 List             Map    Scalar
 replacement     key     relaxed naming
                 rules
  |               |        |
  +---------------+--------+
                  |
                  v
       @ConfigurationProperties
                  |
                  v
            Business service
~~~

Không nên nhầm giá trị có trong một file với giá trị **thực sự có hiệu lực**. Một file `application.yml` đúng vẫn có thể bị `application-prod.yml`, một file external, environment variable hoặc command-line option ghi đè. Với List và Map, ngay cả khi biết nguồn thắng, cách ghép object Java vẫn khác nhau.

### 2.1. Bốn câu hỏi chẩn đoán

1. **Property source nào đang được nạp?** Profile có active, location và import có đúng không?
2. **Nguồn nào có ưu tiên cao nhất cho property?** Có override từ command line/system property/env không?
3. **Tên property có đúng?** Prefix, dấu gạch nối, env name, Map key, List index có khớp không?
4. **Target type là gì?** `List<POJO>`, `Map<String,String>` và `Map<String,Object>` không thể suy luận như nhau.

### 2.2. Đừng bắt đầu bằng cách dump Environment

`Environment` có thể chứa password, API keys, connection URLs và token từ CI/deployment. Không in tất cả `PropertySource` và raw values vào log. Hãy chẩn đoán từng key được phép, dùng source metadata, mã lỗi và dữ liệu giả trong test.

## 3. Một model để minh họa List và Map

~~~java
package com.example.gateway.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<Upstream> upstreams,
        Map<String, Route> routes,
        Duration connectTimeout,
        boolean failFast
) {
    public record Upstream(
            String name,
            String url,
            Duration timeout
    ) {}

    public record Route(
            String target,
            boolean enabled
    ) {}
}
~~~

Đăng ký:

~~~java
package com.example.gateway;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {}
~~~

Cấu hình:

~~~yaml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
        timeout: 2s
      - name: secondary
        url: "https://secondary.example.test"
        timeout: 3s
    routes:
      orders:
        target: primary
        enabled: true
      payments:
        target: secondary
        enabled: true
    connect-timeout: 5s
    fail-fast: true
~~~

Các field Java tương ứng:

- `upstreams` là `List<Upstream>`; thứ tự phần tử quan trọng.
- `routes` là `Map<String,Route>`; mỗi key định danh một tuyến.
- `connectTimeout` là scalar `Duration`.
- `failFast` là scalar boolean.

Binder có thể chuyển đổi `2s` sang `Duration`, tên `connect-timeout` sang `connectTimeout` và cấu trúc YAML sang object Java. Tuy nhiên, khi nhiều nguồn cùng cung cấp những field này, quy tắc kết hợp phải được hiểu theo loại target.

## 4. Lỗi số một: List bị thay thế, không merge

File cơ sở:

~~~yaml
# application.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
        timeout: 2s
      - name: secondary
        url: "https://secondary.example.test"
        timeout: 3s
~~~

File production:

~~~yaml
# application-prod.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://prod-primary.example.test"
        timeout: 1s
~~~

Khi profile `prod` active và nguồn production thắng, List thường chỉ còn:

~~~text
upstreams.size()          = 1
upstreams[0].name         = primary
upstreams[0].url          = https://prod-primary.example.test
upstreams[0].timeout      = 1s
~~~

Phần tử `secondary` không tự được giữ lại. Đây là hành vi **replacement của List giữa các nguồn cấu hình** được Spring Boot mô tả trong phần *Merging Complex Types*.

### 4.1. Vì sao không append?

Nếu hai nguồn cùng cung cấp `upstreams[0]`, không có cách duy nhất để biết người dùng muốn thêm, sửa hay xóa phần tử. Việc merge theo index còn có thể tạo một object “lai” gồm fields từ nhiều môi trường. Spring Boot chọn nguyên tắc rõ ràng hơn: **source có List ưu tiên cao hơn quyết định toàn bộ danh sách**.

### 4.2. Nested fields cũng không tự merge

File cơ sở:

~~~properties
app.gateway.upstreams[0].name=primary
app.gateway.upstreams[0].url=https://primary.example.test
app.gateway.upstreams[0].timeout=2s
~~~

File profile ưu tiên cao hơn:

~~~properties
app.gateway.upstreams[0].name=prod-primary
~~~

Đừng kỳ vọng `url` và `timeout` được giữ từ item thứ 0 của file cơ sở. Với List object binding, phần tử hiệu lực có thể có `name=prod-primary` trong khi những fields không được khai báo ở nguồn thắng trở thành `null` hoặc giá trị mặc định theo target type.

**Triệu chứng thường thấy:** List vẫn có item thứ 0, nhưng endpoint hoặc timeout của nó biến mất; ứng dụng lỗi ở service layer thay vì khởi động.

### 4.3. Cách sửa khi mỗi môi trường cần một danh sách hoàn chỉnh

Khai báo **tất cả phần tử và fields cần thiết** ở source chiến thắng:

~~~yaml
# application-prod.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://prod-primary.example.test"
        timeout: 1s
      - name: secondary
        url: "https://prod-secondary.example.test"
        timeout: 3s
~~~

Trong trường hợp đơn giản, đây là giải pháp dễ hiểu nhất vì danh sách production là một đơn vị cấu hình hoàn chỉnh.

### 4.4. Khi thật sự muốn append, hãy thiết kế một phép merge rõ ràng

Không nên coi Binder là công cụ “cộng hai List”. Có thể tách property:

~~~yaml
app:
  gateway:
    common-upstreams:
      - "https://shared.example.test"
    extra-upstreams:
      - "https://prod-only.example.test"
~~~

Java:

~~~java
public record UpstreamGroups(
        List<String> commonUpstreams,
        List<String> extraUpstreams
) {}
~~~

Khi cần list cuối:

~~~java
List<String> combined = new ArrayList<>(
        properties.commonUpstreams()
);
combined.addAll(properties.extraUpstreams());
~~~

Ví dụ yêu cầu model phù hợp, các list không null hoặc được xử lý thiếu giá trị, và cần kiểm tra duplicate/order. Đây là logic ứng dụng, không phải hành vi mặc định của Spring Boot.

### 4.5. Không “sửa” bằng cách chuyển List sang Set tùy tiện

`Set` không bảo đảm thứ tự như `List` và có thể loại duplicate theo `equals/hashCode`. Nếu ưu tiên endpoint có ý nghĩa, Set có thể làm mất semantics. Hãy thiết kế đúng nghiệp vụ thay vì đổi kiểu chỉ để tránh List replacement.

## 5. List khi nhiều profiles hoặc locations active

Giả sử:

~~~yaml
# application-dev.yml
app:
  gateway:
    upstreams:
      - name: dev
        url: "https://dev.example.test"
~~~

~~~yaml
# application-qa.yml
app:
  gateway:
    upstreams:
      - name: qa
        url: "https://qa.example.test"
~~~

Nếu một môi trường active nhiều profiles, kết quả không phải list nối từ `dev` và `qa`. Theo thứ tự ưu tiên Config Data/profile, List từ nguồn ưu tiên cao hơn được chọn.

Khi có file external, import hoặc location groups, hãy xác định source nào thực sự thắng. Đừng kết luận chỉ từ tên file hay vị trí thứ tự nhìn thấy trong repository.

### 5.1. File external có thể ghi đè JAR

Một ứng dụng có thể đọc:

~~~text
classpath:/application.yml
classpath:/application-prod.yml
file:./config/application.yml
file:./config/application-prod.yml
~~~

Các file external có thể có độ ưu tiên cao hơn theo thứ tự Config Data của Boot. Một danh sách trong file external có thể thay toàn bộ list ở `src/main/resources/application.yml`, dù developer không biết file external tồn tại.

### 5.2. Test local và production khác nhau

Test không active profile production có thể nhìn thấy hai endpoints của file cơ sở. Production kích hoạt profile và chỉ còn một endpoint. Muốn tránh sự cố, hãy có integration test với profile và sources tương ứng, assert **chính xác số lượng và thứ tự phần tử**.

### 5.3. Không suy luận property List từ prefix scalar

Nếu các key nguồn là `app.gateway.upstreams[0].name` và `app.gateway.upstreams[1].name`, câu lệnh:

~~~java
environment.getProperty("app.gateway.upstreams")
~~~

có thể trả `null` vì không có một scalar property ở prefix đó. Điều này **không chứng minh List rỗng**; cần xem indexed child keys hoặc object sau binding.

## 6. Khi List rỗng, thiếu hoặc sai kiểu

Ba trạng thái khác nhau:

1. Không có property List trong source liên quan.
2. Có List ở nguồn thấp nhưng bị nguồn cao thay thế.
3. Source thắng khai báo một giá trị rỗng, index lỗi hoặc conversion lỗi.

Ví dụ:

~~~properties
app.gateway.upstreams[0].timeout=not-a-duration
~~~

có thể gây conversion failure nếu target là `Duration`.

Một List mặc định được khởi tạo trong JavaBean cũng không có nghĩa source cao hơn sẽ append vào nó. Cần test khi có override, khi không có source và khi có empty list theo đúng Spring Boot version.

### 6.1. Index không liên tục

Cấu hình chỉ có `upstreams[1]` mà thiếu `[0]` không phải cách đáng tin cậy để biểu diễn phần tử đầu tiên. Nên sử dụng index liên tục bắt đầu từ 0 và viết test nếu có yêu cầu đặc biệt.

### 6.2. Kết hợp List từ JSON/YAML/properties

Một `List<String>` có thể được biểu diễn bằng:

~~~properties
app.servers=alpha,beta
~~~

hoặc:

~~~properties
app.servers[0]=alpha
app.servers[1]=beta
~~~

hoặc YAML:

~~~yaml
app:
  servers:
    - alpha
    - beta
~~~

Dù hình thức nguồn khác nhau, khi nhiều property sources khai báo lại target List, vẫn cần hiểu quy tắc replacement. Không có quy tắc “comma-separated thì merge, YAML thì replace” chung như vậy.

## 7. Map khác List: có thể tổng hợp từ nhiều nguồn

Spring Boot cho phép một Map nhận các key từ nhiều property sources; cùng một property path thì nguồn ưu tiên cao hơn quyết định giá trị.

Model JavaBean:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class RoutesProperties {

    private final Map<String, Route> routes = new LinkedHashMap<>();

    public Map<String, Route> getRoutes() {
        return routes;
    }

    public static class Route {
        private String target;
        private String description;

        public String getTarget() { return target; }
        public void setTarget(String target) {
            this.target = target;
        }

        public String getDescription() { return description; }
        public void setDescription(String description) {
            this.description = description;
        }
    }
}
~~~

File cơ sở:

~~~properties
app.routes.orders.target=primary
app.routes.orders.description=Order service
~~~

File profile ưu tiên cao hơn:

~~~properties
app.routes.orders.target=prod-primary
app.routes.payments.target=prod-payments
app.routes.payments.description=Payment service
~~~

Kết quả binding Map object có thể là:

~~~text
routes.orders.target         = prod-primary
routes.orders.description    = Order service
routes.payments.target       = prod-payments
routes.payments.description  = Payment service
~~~

Map giữ `orders.description` từ nguồn thấp, cập nhật `orders.target` và thêm `payments` từ nguồn cao. **Đây là sự khác biệt quan trọng với List<POJO>.**

### 7.1. Map không tự làm mọi thứ

Cùng key/value path vẫn áp precedence; Map không cộng số, nối chuỗi hoặc ghép mọi object theo một thuật toán tùy ý. Nó chỉ có khả năng tổ hợp các keys và nested properties theo Binder.

### 7.2. Nếu muốn Map thay thế nguyên khối

Một file `application-prod.yml` chỉ khai báo một vài entries không nhất thiết xóa các keys của file base. Nếu cần tập routes độc lập theo môi trường, hãy dùng prefix khác nhau, model riêng hoặc bước replacement được thiết kế, có test.

### 7.3. Map<String,String> minh họa

Nguồn cơ sở:

~~~yaml
app:
  labels:
    owner: platform
    tier: backend
~~~

Nguồn cao:

~~~yaml
app:
  labels:
    tier: critical
    environment: prod
~~~

Map cuối có thể chứa `owner=platform`, `tier=critical`, `environment=prod`. Không nên mô tả nó như một List bị thay toàn bộ.

## 8. Map key sai vì không dùng bracket notation

Tên khóa trong Map đôi khi chứa ký tự như `/`, `:`, `@` hoặc `+`. Nếu khóa không được bao trong `[ ]`, Binder có thể loại những ký tự không được hỗ trợ theo relaxed binding.

Ví dụ muốn key literal `/catalog/v1`.

Không nên:

~~~properties
app.routes./catalog/v1=https://catalog.example.test
~~~

Đúng hơn:

~~~properties
app.routes[/catalog/v1]=https://catalog.example.test
~~~

Với YAML:

~~~yaml
app:
  routes:
    "[/catalog/v1]": "https://catalog.example.test"
~~~

**Hai ý nghĩa khác nhau:** dấu `[ ]` hướng Binder bảo toàn Map key; dấu quote trong YAML bảo đảm YAML parser nhận key bracket là scalar string.

### 8.1. Ví dụ ba Map keys

~~~properties
app.routes[/key1]=value1
app.routes[/key2]=value2
app.routes./key3=value3
~~~

Với target `Map<String,String>`, kết quả có thể là:

~~~text
"/key1" -> "value1"
"/key2" -> "value2"
"key3"  -> "value3"
~~~

Key thứ ba không được bảo vệ, nên dấu slash bị loại. Đây là ví dụ trực tiếp minh họa trong tài liệu Spring Boot.

### 8.2. Không sửa YAML parse error bằng cách xóa brackets

Đoạn:

~~~yaml
app:
  routes:
    [/orders]: "backend"
~~~

có thể được YAML parser diễn giải theo cú pháp khác. Hãy quote:

~~~yaml
app:
  routes:
    "[/orders]": "backend"
~~~

Nếu xóa brackets, YAML có thể parse nhưng Binder lại làm mất slash trong key.

### 8.3. Đường dẫn ứng dụng là dữ liệu, không phải cấu trúc property

Map key `/api/v1` có thể là route thật. Nếu Binder làm mất slash, đừng vội sửa code thành lookup theo `api/v1`; làm vậy che vấn đề dữ liệu và có thể gây collision với một route khác.

## 9. Dấu chấm trong key Map phụ thuộc vào kiểu value

Với `Map<String, String>`, Spring Boot có một ngoại lệ: dấu chấm trong key của **scalar map value** có thể được bảo toàn.

~~~properties
app.labels.a.b=enabled
~~~

Nếu target:

~~~java
Map<String, String> labels;
~~~

kết quả có thể là:

~~~text
"a.b" -> "enabled"
~~~

Nhưng nếu target là:

~~~java
Map<String, Object> labels;
~~~

thì cùng property có thể được biểu diễn thành cấu trúc nested:

~~~text
"a" -> {"b" -> "enabled"}
~~~

Muốn key literal `a.b`, viết:

~~~properties
app.labels[a.b]=enabled
~~~

Hoặc YAML:

~~~yaml
app:
  labels:
    "[a.b]": "enabled"
~~~

### 9.1. Quy tắc với Map<String, POJO>

Nếu value là object nested, dấu chấm thường tham gia phân cấp field. Ví dụ:

~~~properties
app.routes.orders.target=primary
~~~

được hiểu như Map key `orders` với property `target` của value object, không phải literal Map key `orders.target`.

Nếu tên route thực sự chứa dấu chấm, hãy bảo vệ bằng brackets:

~~~properties
app.routes[orders.v2].target=primary
~~~

### 9.2. Không áp quy tắc một cách máy móc

Tài liệu Boot mô tả scalar types bao gồm enums và các kiểu trong `java.lang` trừ `Object`. Với custom POJO hoặc Map value là `Object`, cần kiểm chứng cách Binder hiểu dấu chấm.

**Cách an toàn khi key có dấu chấm thật sự là identifier:** sử dụng bracket notation tường minh và test key cuối cùng.

## 10. Collision khi hai Map keys bị normalize trùng

Giả sử cần hai route khác nhau: `/orders` và `orders`.

Nếu viết:

~~~properties
app.routes./orders=serviceA
app.routes.orders=serviceB
~~~

khả năng chuẩn hóa tên key có thể làm hai cấu hình rơi vào cùng một key hoặc tạo kết quả khó lường theo precedence.

Cách tường minh:

~~~properties
app.routes[/orders]=serviceA
app.routes.orders=serviceB
~~~

Với `Map<String,String>`, test cần khẳng định có hai key độc lập. Không sử dụng phép trim slash hoặc lowercase tùy tiện trong service để “chữa” collision nếu domain thật sự phân biệt chúng.

### 10.1. Map key từ dữ liệu không tin cậy

Nếu key Map đến từ request hoặc nguồn được bên khác chỉnh sửa, cần validation về danh sách ký tự, độ dài, số phần tử và collision. Binder giúp chuyển cấu hình thành object chứ không thay thế kiểm soát dữ liệu đầu vào và chính sách bảo mật.

## 11. Biến môi trường không phải tên property được viết hoa tùy ý

Spring Boot khuyến nghị chuyển một **canonical property name** sang tên OS environment variable theo ba bước:

1. Thay dấu chấm `.` bằng underscore `_`.
2. **Loại bỏ dấu gạch nối `-`**.
3. Chuyển thành uppercase.

Ví dụ:

~~~text
spring.main.log-startup-info
         |
         v
SPRING_MAIN_LOGSTARTUPINFO
~~~

Một key khác:

~~~text
app.gateway.connect-timeout
         |
         v
APP_GATEWAY_CONNECTTIMEOUT
~~~

Nhiều người quen chuyển từng dấu gạch nối thành underscore, nhưng với relaxed binding của Spring Boot, đó không phải tên env được đề xuất.

### 11.1. Bảng ánh xạ

| Canonical property | Environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `app.gateway.connect-timeout` | `APP_GATEWAY_CONNECTTIMEOUT` |
| `app.gateway.fail-fast` | `APP_GATEWAY_FAILFAST` |
| `app.client.retry-max-attempts` | `APP_CLIENT_RETRYMAXATTEMPTS` |
| `payment.gateway.api-key` | `PAYMENT_GATEWAY_APIKEY` |
| `my.main-project.person.first-name` | `MY_MAINPROJECT_PERSON_FIRSTNAME` |

Đây là cách chuyển đổi từ key canonical trong trường hợp source là OS environment; custom PropertySource có thể áp dụng cơ chế khác.

### 11.2. Dấu gạch nối bị xóa, không thay bằng underscore

Canonical:

~~~properties
app.client.retry-max-attempts=3
~~~

Tên sai theo phép chuyển đổi chuẩn:

~~~text
APP_CLIENT_RETRY_MAX_ATTEMPTS=7
~~~

Tên đúng:

~~~text
APP_CLIENT_RETRYMAXATTEMPTS=7
~~~

Nếu operator dùng tên sai và bean vẫn là `3`, không nên kết luận ngay rằng environment source có precedence thấp. Hãy xác nhận tên env có thực sự ánh xạ đến field của bean.

### 11.3. Java field khác key canonical

Java:

~~~java
private int retryMaxAttempts;
~~~

Property canonical:

~~~properties
app.client.retry-max-attempts=3
~~~

Environment variable:

~~~text
APP_CLIENT_RETRYMAXATTEMPTS=7
~~~

Không tự thêm underscore giữa các từ camelCase theo một quy tắc bên ngoài Spring Boot.

## 12. List index trong env vars phải có underscore

Canonical:

~~~properties
my.service[0].other=alpha
my.service[1].other=beta
~~~

OS environment:

~~~text
MY_SERVICE_0_OTHER=alpha
MY_SERVICE_1_OTHER=beta
~~~

Số index được bao quanh bằng underscore trong tên biến, tương ứng với `[0]`, `[1]` của canonical key.

### 12.1. Ví dụ List of POJO

~~~properties
app.gateway.upstreams[0].name=primary
app.gateway.upstreams[0].url=https://primary.example.test
app.gateway.upstreams[1].name=secondary
app.gateway.upstreams[1].url=https://secondary.example.test
~~~

Tương ứng:

~~~bash
export APP_GATEWAY_UPSTREAMS_0_NAME="primary"
export APP_GATEWAY_UPSTREAMS_0_URL="https://primary.example.test"
export APP_GATEWAY_UPSTREAMS_1_NAME="secondary"
export APP_GATEWAY_UPSTREAMS_1_URL="https://secondary.example.test"
~~~

Đừng dùng:

~~~text
APP_GATEWAY_UPSTREAMS0NAME
~~~

rồi kỳ vọng Binder hiểu `upstreams[0].name`. Dạng được tài liệu hướng dẫn là `_0_`.

### 12.2. List từ env vẫn có replacement semantics

Nếu file base có hai upstreams nhưng một source environment ưu tiên cao hơn chỉ cấp `APP_GATEWAY_UPSTREAMS_0_NAME` và `APP_GATEWAY_UPSTREAMS_0_URL`, đừng mặc định phần tử thứ hai sẽ được giữ từ file base.

Cần cấp toàn bộ List mong muốn ở source thắng, hoặc xây phép merge riêng trong business logic.

### 12.3. Index không liên tục

Nếu chỉ khai báo phần tử `[2]`, thiếu `[0]` và `[1]`, kết quả có thể không như mong đợi hoặc binding có thể lỗi tùy target. Nên dùng index liên tục bắt đầu bằng 0, có test nếu bắt buộc hỗ trợ tình huống đặc biệt.

## 13. Map keys từ env vars có thể bị lowercase

Theo tài liệu Boot, khi bind Map từ system environment, Spring Boot lowercase tên environment variable trước khi binding.

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.props")
public class MyMapsProperties {
    private final Map<String, String> values = new java.util.HashMap<>();

    public Map<String, String> getValues() {
        return values;
    }
}
~~~

Biến:

~~~text
MY_PROPS_VALUES_REGION=AP_SOUTHEAST
~~~

Kết quả:

~~~text
values.get("region") = "AP_SOUTHEAST"
~~~

**Key** thường là `region` lowercase, nhưng **value** vẫn giữ `AP_SOUTHEAST`.

### 13.1. Khi business cần key case-sensitive

Nếu Map key `US_EAST` khác `us_east` về mặt nghiệp vụ, OS environment variable không phải nguồn tốt để bảo toàn case của key. Nên dùng YAML/properties với literal key hoặc một cấu hình structured source thích hợp và test.

### 13.2. Map key có slash, colon hoặc ký tự khó biểu diễn trong env

Tên biến POSIX thường không chứa `/` hoặc `[ ]`. Không thể tự đổi `/orders` thành `_ORDERS` và kỳ vọng Binder khôi phục dấu slash cho key.

Với Map dùng URL paths, hostnames chứa ký tự đặc biệt hoặc identifiers chính xác, ưu tiên file Config Data có bracket notation hoặc một structured config source hỗ trợ key chính xác.

### 13.3. Đừng lowercase Map values

Nếu thấy value bị đổi case trong business object, kiểm tra custom converter, setter hoặc logic khác. Quy tắc đang nói đến **tên environment/key**, không phải mọi giá trị env var.

## 14. Quy tắc env-style chỉ áp dụng với nguồn tương ứng

Một điểm tinh vi: cơ chế Spring Boot dành cho system environment names được áp dụng với `systemEnvironment` và các nguồn có tên kết thúc bằng `-systemEnvironment` theo tài liệu.

Nếu test tự đưa:

~~~java
Map<String, Object> values = Map.of(
    "APP_GATEWAY_CONNECTTIMEOUT", "2s");
~~~

vào một `MapPropertySource` tùy ý, test đó không nhất thiết tái hiện đầy đủ hành vi OS environment của production.

Muốn xác minh naming, hãy tạo một test harness với nguồn có semantics của system environment, hoặc kiểm thử bằng chính process/container environment trong integration test được kiểm soát.

### 14.1. Không nhầm @Value với @ConfigurationProperties

`@ConfigurationProperties` sử dụng relaxed binding toàn diện hơn. `@Value` không có cùng mức hỗ trợ relaxed binding. Nếu sử dụng `@Value` với placeholder, tài liệu khuyến nghị tên canonical kebab-case để tận dụng cách tra cứu property phù hợp nhất.

~~~java
@Value("${app.gateway.connect-timeout}")
private Duration connectTimeout;
~~~

Ở đây placeholder dùng tên canonical. Dù vậy, khi xây một nhóm cấu hình nhiều field và collection, `@ConfigurationProperties` vẫn thường rõ ràng và dễ kiểm thử hơn.

## 15. Biến đúng tên vẫn có thể bị một nguồn khác override

Giả sử shell:

~~~bash
export APP_GATEWAY_CONNECTTIMEOUT=2s
~~~

Nhưng lệnh chạy:

~~~bash
java -Dapp.gateway.connect-timeout=1s \
     -jar gateway.jar \
     --app.gateway.connect-timeout=500ms
~~~

Trong Spring Boot thông thường, command-line option có precedence cao hơn Java system property và OS environment variable. Giá trị cuối có thể là `500ms`, không phải `2s`.

### 15.1. Nguồn nào thắng?

Trong nhiều ứng dụng Boot, những loại nguồn có thể tham gia gồm:

~~~text
Config Data files
OS environment variables
Java system properties
SPRING_APPLICATION_JSON
command-line arguments
test-specific properties
~~~

Các nguồn càng cao trong precedence cuối sẽ ghi đè giá trị trùng key từ nguồn thấp. Thứ tự chính xác cần xem theo phiên bản Boot, profile/import và test context, không dùng một phỏng đoán cố định cho mọi app.

### 15.2. Một process không tự nhận thay đổi từ shell khác

Việc export biến ở terminal A không làm tiến trình Java đã chạy hoặc tiến trình container khác tự nhận biến. Để tái hiện rõ:

~~~bash
APP_GATEWAY_CONNECTTIMEOUT=2s java -jar gateway.jar
~~~

Ví dụ này truyền env chỉ cho process con của lệnh. Với Docker/Kubernetes, phải cấu hình đúng container chạy JVM. Sau khi đổi environment của deployment, thường cần restart/redeploy để process mới nhận.

### 15.3. CLI có thể bị ứng dụng vô hiệu hóa

`SpringApplication.setAddCommandLineProperties(false)` cho phép không thêm CLI options vào Environment. Khi chẩn đoán, xác nhận cách ứng dụng thực tế bootstraps trước khi khẳng định mọi `--key=value` đều có hiệu lực.

## 16. Profiles, Config Data import và file external

Giả sử developer sửa:

~~~text
src/main/resources/application.yml
~~~

nhưng production chạy cùng:

~~~text
file:./config/application-prod.yml
~~~

thì source external có thể chứa các List/Map override mà bản code không thể hiện.

### 16.1. Thứ tự Config Data

Spring Boot có quy tắc về file đóng gói trong JAR, profile-specific file trong JAR, file external và profile-specific file external. Location groups và imports có thể tạo thứ tự tinh vi hơn.

Khi giá trị không như dự kiến, hãy xác định những file đã nạp, active profiles, `spring.config.import` và source đang thắng.

### 16.2. application.properties và application.yml cùng một location

Nếu cả hai tồn tại ở cùng location, tài liệu Boot nêu `.properties` được ưu tiên. Một người sửa YAML nhưng không thấy hiệu lực có thể đang bị file properties cùng tên thắng.

### 16.3. Placeholder trong giá trị

~~~properties
app.gateway.connect-timeout=${APP_TIMEOUT:5s}
~~~

Placeholder có thể được phân giải qua Environment. Nhưng cơ chế placeholder chỉ xác định giá trị scalar, không đổi bản chất **List replacement** hay **Map key binding**.

## 17. Quy trình chẩn đoán theo cây quyết định

~~~text
Khởi đầu: cấu hình Java sai
           |
           v
Bean @ConfigurationProperties tồn tại?
   | không -> kiểm tra scan / registration
   |
   có
   |
   v
Property source đúng được nạp?
   | không -> kiểm tra profile / import / location / process env
   |
   có
   |
   v
Tên canonical và prefix đúng?
   | không -> sửa kebab-case / env naming
   |
   đúng
   |
   v
Có source ưu tiên cao hơn?
   | có -> xác định source thắng
   |
   v
Target là gì?
   |
   +-- List -> replacement / index / nested fields
   |
   +-- Map -> bracket key / dot / slash / lowercase
   |
   +-- Scalar -> conversion / validation
   |
   v
Viết test tái hiện -> sửa đúng nguồn -> xác minh bean
~~~

Cây quyết định giúp tránh cách làm thường gặp: thêm nhiều giá trị override mới để “ép” kết quả mà không rõ nguyên nhân ban đầu.

## 18. Kiểm tra Environment và bean trong test

Một bài test có thể xác định scalar source:

~~~java
import org.springframework.core.env.Environment;

@Autowired Environment environment;

@Test
void timeoutPropertyIsVisible() {
    assertThat(environment.getProperty(
        "app.gateway.connect-timeout"))
        .isEqualTo("2s");
}
~~~

Sau đó kiểm tra type conversion:

~~~java
@Autowired GatewayProperties properties;

@Test
void timeoutHasBeenBound() {
    assertThat(properties.connectTimeout())
        .isEqualTo(Duration.ofSeconds(2));
}
~~~

Nếu kiểm tra đầu sai, tìm source, prefix hoặc precedence. Nếu kiểm tra đầu đúng nhưng bean sai, tìm bean registration, conversion, setter/constructor, validation và custom binding.

### 18.1. Không yêu cầu Environment trả cả List thành một String

Nếu nguồn cung cấp indexed keys, việc `environment.getProperty("app.gateway.upstreams")` trả null không chứng minh List rỗng. Đúng hơn là test bean `properties.upstreams()` hoặc từng key đã được nạp.

### 18.2. Tránh print toàn bộ ConfigProps

Một record `@ConfigurationProperties` có thể chứa secret và Java record tự sinh `toString()` gồm nhiều field. Không in toàn object bằng logger khi điều tra.

## 19. Actuator giúp truy tìm nguồn — với điều kiện bảo mật

Khi cấu hình thích hợp, Spring Boot Actuator có các endpoint:

- `/actuator/env`: hỗ trợ quan sát Environment/property sources theo mức hiển thị cho phép.
- `/actuator/configprops`: hỗ trợ quan sát beans `@ConfigurationProperties` và giá trị đã bind theo mức hiển thị được cấu hình.

Không expose hai endpoint này công khai. Cần xác thực, phân quyền, sanitization và kiểm thử rằng credential không bị lộ. Các option `show-values` hoặc cơ chế masking có thể khác theo phiên bản Boot.

Thực hành vận hành tốt: ghi **mã lỗi, tên key đã cho phép, source type và expected requirement**, không ghi raw password, token hoặc toàn Environment.

### 19.1. TRACE/DEBUG không phải lời giải mặc định

Bật log chi tiết toàn hệ thống có thể giúp xác định profile/source nhưng đồng thời làm lộ thông tin nhạy cảm hoặc tăng lượng log. Nếu cần, dùng một môi trường giả lập với fake secrets và giới hạn logger, thời gian lưu, quyền xem.

## 20. Test List replacement bằng SpringBootTest

Với file `application.yml` chứa hai upstreams, `application-prod.yml` chứa một upstream:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionGatewayConfigTest {

    @Autowired GatewayProperties properties;

    @Test
    void productionListReplacesBaseList() {
        assertThat(properties.upstreams())
            .extracting(GatewayProperties.Upstream::name)
            .containsExactly("primary");
    }
}
~~~

Bài test này cần application/test configuration thực sự có hai file đúng như ví dụ. Nó minh họa cách xác minh **whole List replacement**, thay vì chỉ assert có `primary`.

### 20.1. Test thiếu nested List fields

Nếu production chỉ ghi `upstreams[0].name`, thêm assertion về `url`, `timeout` để phát hiện field thiếu. Nếu những field bắt buộc, dùng validation để startup báo lỗi sớm thay vì cho service nhận null.

### 20.2. Test với Config Data thật

Nếu mục tiêu là kiểm tra profile-specific precedence, dùng `@ActiveProfiles` và Config Data files thực sự, không chỉ truyền một list đã được xây sẵn bằng code Java.

## 21. Test Map special keys

Target:

~~~java
@ConfigurationProperties(prefix = "app")
public record RouteStrings(
    Map<String, String> routes
) {}
~~~

YAML:

~~~yaml
app:
  routes:
    "[/api/v1]": service-a
    orders: service-b
~~~

Test:

~~~java
assertThat(properties.routes())
    .containsEntry("/api/v1", "service-a")
    .containsEntry("orders", "service-b");
~~~

Một test như vậy xác nhận cả **key** lẫn **value**, không chỉ rằng Map có hai entries.

### 21.1. Test key có dấu chấm

Với `Map<String, Object>` và key `team.alpha`, assert rằng `keySet()` chứa `"team.alpha"` chứ không phải chỉ có `"team"`. Đặt bracket key trong YAML để bảo toàn literal.

### 21.2. Test collision

Khai báo `[/orders]` và `orders` thành hai keys độc lập rồi assert cả hai. Nếu một key biến mất, xem lại syntax/source trước khi sửa business lookup.

## 22. Test env var naming

Nếu muốn mô phỏng env var, chú ý **loại property source**. Spring Boot áp dụng quy tắc env-style vào `systemEnvironment` hoặc những sources có tên kết thúc `-systemEnvironment`. Một `MapPropertySource` bất kỳ với key viết hoa không nhất thiết giống OS environment thật.

Một test có thể xác nhận:

~~~text
Canonical: app.client.retry-max-attempts
Expected OS env: APP_CLIENT_RETRYMAXATTEMPTS
~~~

Khi chạy integration test với container hoặc process environment giả, assert bean `retryMaxAttempts` đúng giá trị. Đồng thời test một List index như `MY_SERVICE_0_OTHER`.

### 22.1. Không sửa System.getenv tùy tiện

`System.getenv()` không phải một mutable map dùng để set/unset đơn giản bằng API Java chuẩn. Những thư viện test thao tác process environment có thể có ràng buộc JVM/module khác nhau. Tốt nhất là dùng test harness có hỗ trợ OS env/source semantics rõ hoặc tách test naming khỏi test source precedence.

### 22.2. Test Map lowercase

Cấp `MY_PROPS_VALUES_REGION=AP_SOUTHEAST` trong môi trường test phù hợp, assert key `region` và value `AP_SOUTHEAST`. Nếu nghiệp vụ cần chữ hoa trong key, chuyển sang một nguồn hỗ trợ literal keys.

## 23. ApplicationContextRunner cho các ca binding nhỏ

Spring Boot cung cấp `ApplicationContextRunner` để tạo context với property values và kiểm tra kết quả mà không cần toàn bộ `@SpringBootTest`.

Model:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sample")
public record SampleProperties(
    List<String> servers,
    Map<String, String> labels
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class SampleBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(SampleTestConfig.class);

    @Test
    void bindsCollections() {
        runner.withPropertyValues(
            "sample.servers[0]=https://prod.example.test",
            "sample.labels[region]=ap-southeast"
        ).run(context -> {
            SampleProperties p = context.getBean(SampleProperties.class);

            assertThat(p.servers())
                .containsExactly("https://prod.example.test");
            assertThat(p.labels())
                .containsEntry("region", "ap-southeast");
        });
    }
}
~~~

`SampleTestConfig` phải đăng ký `SampleProperties` bằng `@EnableConfigurationProperties(SampleProperties.class)` hoặc cơ chế phù hợp. Ví dụ trên chỉ test một tập values. Khi cần test merge/replacement **giữa nhiều nguồn**, hãy tạo các `PropertySource` tách biệt với thứ tự ưu tiên được mô phỏng đúng, hoặc dùng Config Data integration test.

## 24. Một tình huống production đầy đủ

Giả sử Kubernetes service gặp ba triệu chứng:

1. List upstream còn một phần tử dù file cơ sở có hai.
2. Route `/payments` không truy cập được.
3. Timeout không đổi sau khi operator thêm env var.

Cấu hình cơ sở:

~~~yaml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
      - name: backup
        url: "https://backup.example.test"
    routes:
      /payments: "payment-service"
    connect-timeout: 5s
~~~

File production:

~~~yaml
app:
  gateway:
    upstreams:
      - name: production
        url: "https://prod.example.test"
~~~

Deployment:

~~~yaml
env:
  - name: APP_GATEWAY_CONNECT_TIMEOUT
    value: "2s"
~~~

### 24.1. Triệu chứng List

File production khai báo List riêng nên có thể thay toàn bộ List base. Nếu muốn giữ backup, khai báo backup ngay trong danh sách production, hoặc thiết kế nguồn merge rõ ràng.

### 24.2. Triệu chứng Map

Key `/payments` cần bracket notation:

~~~yaml
app:
  gateway:
    routes:
      "[/payments]": "payment-service"
~~~

Không nên sửa business code thành key `payments` nếu đường dẫn thực sự cần slash.

### 24.3. Triệu chứng env

Tên canonical `app.gateway.connect-timeout` chuyển thành:

~~~text
APP_GATEWAY_CONNECTTIMEOUT
~~~

không phải `APP_GATEWAY_CONNECT_TIMEOUT` theo quy tắc canonical. Sửa tên biến cho đúng trong container spec, redeploy và xác minh bean nhận `2s`.

### 24.4. Thứ tự xử lý an toàn

1. Xác nhận profile production và file external đang nạp.
2. Kiểm tra List source thắng, không ngầm merge.
3. Kiểm tra key Map sau binder, sửa brackets.
4. Kiểm tra tên env được inject vào đúng container.
5. Xác minh không có CLI/system property override timeout.
6. Tạo integration test tái hiện.
7. Redeploy/restart theo quy trình.
8. Xác nhận behavior của route và upstream thật, không chỉ context startup.

## 25. Những lỗi thiết kế thường gặp

### 25.1. Dùng profile để “patch” phần tử List

Khi profile cao hơn chỉ đặt `items[0].name`, không nên kỳ vọng các fields khác từ source thấp hơn vẫn có sẵn. Khai báo item đầy đủ.

### 25.2. Nghĩ Map thay toàn bộ giống List

Map có thể giữ các key không bị override từ nguồn thấp hơn. Nếu mục tiêu là replacement, xây policy riêng.

### 25.3. Xóa brackets để tránh YAML syntax error

Cần quote bracket key, không xóa nó. Xóa brackets có thể khiến Binder làm sai literal Map key.

### 25.4. Chỉ nhìn tên Map key mà không nhìn generic value type

`Map<String,String>` và `Map<String,Object>` có thể xử lý dấu chấm khác nhau. Xác nhận target type.

### 25.5. Lowercase mọi Map values

Tên env/key có thể bị lowercase; Map value không tự động bị lowercase vì thế. Nếu cần phân biệt case, xem phần xử lý target value.

### 25.6. Chèn underscore vào tất cả từ Java camelCase

Canonical `retry-max-attempts` phải thành `RETRYMAXATTEMPTS` khi đổi tên env theo quy tắc Boot, không phải `RETRY_MAX_ATTEMPTS`.

### 25.7. Export env var ở shell không chạy Java

Scope của process/container quan trọng. Hãy đặt env ở đúng lệnh hoặc deployment container.

### 25.8. Nhìn thấy property trong Environment rồi cho rằng bean đúng

Có thể sai prefix, sai generic type, thiếu bean registration, conversion fail hoặc collection replacement. Kiểm tra bean.

### 25.9. Dump toàn bộ Environment để debug

Có thể lộ secrets và tạo log không an toàn. Chỉ xem key/source metadata cần thiết.

### 25.10. Sửa nhiều Config Data sources cùng lúc

Nếu không biết nguồn nào đang thắng, thay cả YAML, external properties và env sẽ che nguyên nhân. Khoanh vùng, sửa một chỗ, viết test, rồi xác minh.

## 26. Bảng triệu chứng và cách sửa

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| List mất phần tử base | Nguồn cao hơn thay toàn bộ List | Khai báo đầy đủ List ở source thắng |
| List item mất url/timeout | Nested fields của List không merge | Cấp đầy đủ fields và validate |
| Muốn append List nhưng không có | Binder không tự concat Lists | Merge rõ trong application |
| Map giữ một key cũ | Map có thể tổng hợp từ nhiều sources | Thiết kế replacement nếu cần |
| Key `/foo` thành `foo` | Thiếu bracket literal key | Dùng `[/foo]` |
| YAML bracket bị parse sai | Không quote key | Dùng `"[/foo]"` |
| `a.b` thành nested Map | Map value là object, không bracket | Dùng `[a.b]` |
| Map key env lowercase | Env names được lowercase | Dùng nguồn khác nếu key case-sensitive |
| Biến env không override | Tên biến sai chuẩn | Bỏ dấu `-` khi chuyển canonical |
| List index env không nhận | Thiếu `_0_` | Dùng `MY_LIST_0_NAME` |
| File đã sửa nhưng bean không đổi | Source khác thắng hoặc process cũ | Kiểm tra precedence/restart |
| Prefix scalar lookup null | List dùng indexed children | Kiểm tra child keys và bean |
| Binder báo lỗi | Type conversion/validation | Kiểm tra target type và requirement |
| Actuator hiển thị dữ liệu nhạy cảm | Endpoint/quyền/masing không phù hợp | Bảo vệ, sanitize và kiểm thử |

## 27. Checklist khi sửa production

- [ ] Đã xác định bean, prefix và target field.
- [ ] File/profiles/imports thực tế đang được nạp.
- [ ] Có danh sách các nguồn cùng key theo metadata an toàn.
- [ ] List được xem là replacement, không tự merge.
- [ ] Danh sách production khai báo đầy đủ tất cả elements cần thiết.
- [ ] Nested fields trong List items được xác định và validate.
- [ ] Nếu cần append, đã viết và test cơ chế merge riêng.
- [ ] Map được xem theo quy tắc tổng hợp keys từ sources.
- [ ] Literal Map keys có `/` hoặc ký tự đặc biệt sử dụng `[ ]`.
- [ ] YAML bracket keys được quote.
- [ ] Map keys có dấu chấm được phân tích theo generic value type.
- [ ] Case-sensitive Map keys không phụ thuộc env naming bị lowercasing.
- [ ] Canonical property names dùng kebab-case.
- [ ] Env names thay dấu chấm bằng underscore và loại bỏ dấu gạch nối.
- [ ] List indexes qua env dùng `_0_`, `_1_`.
- [ ] Env thực sự nằm trong đúng process/container.
- [ ] Không có source ưu tiên cao hơn ghi đè ngoài ý định.
- [ ] Bean đã được đăng ký và type conversion thành công.
- [ ] Integration tests assert exact List/Map entries và scalar values.
- [ ] Không in secret hoặc dump toàn Environment.
- [ ] Có restart/redeploy khi thay đổi cấu hình runtime.
- [ ] Quan sát behavior thực tế sau sửa, không chỉ kiểm tra startup.

## 28. Bài tập áp dụng

### Bài A — List replacement

~~~properties
# base
app.nodes[0].name=a
app.nodes[1].name=b
~~~

~~~properties
# prod
app.nodes[0].name=prod
~~~

Khi profile production thắng, hỏi List có tự giữ node `b` không?

**Định hướng:** không. List nguồn thắng thay toàn bộ danh sách.

### Bài B — Nested field List

File base có `app.nodes[0].url` và `app.nodes[0].timeout`. File prod chỉ có `app.nodes[0].name`.

Hỏi url/timeout có được merge từ item base không?

**Định hướng:** không được dựa vào merge nested properties của List. Cần khai báo fields cần thiết ở source thắng.

### Bài C — Map merging

~~~properties
# base
app.routes.orders.target=primary
app.routes.orders.description=Orders
~~~

~~~properties
# prod
app.routes.orders.target=prod
app.routes.payments.target=prod-payment
~~~

Hỏi `orders.description` có thể còn không?

**Định hướng:** Map nested fields có thể được tổng hợp từ nhiều sources, khác List.

### Bài D — Map path key

Target `Map<String,String>` muốn key `/v1/orders`. Viết property đúng.

**Định hướng:**

~~~properties
app.routes[/v1/orders]=order-service
~~~

### Bài E — Map dot key

Target `Map<String,Object>` cần literal key `team.alpha`.

**Định hướng:**

~~~yaml
app:
  labels:
    "[team.alpha]": enabled
~~~

### Bài F — Environment variable

Canonical property là `app.client.retry-max-attempts`.

**Định hướng:** tên env phù hợp là `APP_CLIENT_RETRYMAXATTEMPTS`.

### Bài G — Indexed List env

Canonical `my.service[0].other`.

**Định hướng:** `MY_SERVICE_0_OTHER`.

### Bài H — Map case từ environment

Env `MY_PROPS_VALUES_REGION=AP_SOUTHEAST`.

**Định hướng:** Map key `region`, value `AP_SOUTHEAST`.

## 29. Kết luận

Ba triệu chứng — **List bị thay thế**, **Map key không đúng** và **env var sai tên** — thường không phải bug ngẫu nhiên. Chúng là hệ quả có thể giải thích từ quy tắc externalized configuration của Spring Boot:

- **List:** source ưu tiên cao hơn khai báo lại List thì thường thay toàn bộ; không tự append hoặc merge nested item fields.
- **Map:** có thể nhận keys và nested fields từ nhiều sources; cùng path thì precedence quyết định. Dùng bracket notation để giữ key literal có special characters.
- **Dấu chấm trong Map keys:** cách diễn giải phụ thuộc scalar value hay object value; khi cần literal key, hãy dùng brackets.
- **Environment variables:** từ tên canonical, `.` → `_`, xóa `-`, viết uppercase; List index dùng `_0_`. Map key lấy từ system environment có thể bị lowercase.
- **Chẩn đoán:** xác định nguồn thắng và key thực tế, kiểm tra cả `Environment` lẫn bean `@ConfigurationProperties`, viết test tái hiện rồi sửa nguồn phù hợp.

Nắm rõ các bước này giúp người phát triển và vận hành sửa đúng một nguyên nhân, giữ behavior nhất quán giữa local/test/staging/production, và tránh đưa secret vào log khi debug.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding)
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot Reference — Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)
- [Spring Boot Reference — Merging Complex Types](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types)
- [Spring Boot API — Binder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html)
