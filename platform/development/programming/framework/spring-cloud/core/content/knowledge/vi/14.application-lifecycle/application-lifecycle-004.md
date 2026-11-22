# Endpoint env với thao tác POST và rebind thuộc tính

Bài học thuộc chương **Vòng đời ứng dụng** của module **SPRING_CLOUD_CORE**. Spring Boot Actuator cung cấp endpoint `/actuator/env` để quan sát `Environment`. Khi tích hợp Spring Cloud Context, endpoint này còn có thể nhận thao tác **POST** để cập nhật một property trong Environment đang chạy. Spring Cloud phát `EnvironmentChangeEvent` cho các key thay đổi; các listener tiêu chuẩn dùng event này để rebind bean `@ConfigurationProperties` và cập nhật mức log `logging.level.*`.

Đây là một thao tác quản trị runtime, không phải cơ chế lưu cấu hình lâu dài. Giá trị được ghi vào Environment của process hiện tại; nó không tự sửa file YAML, Config Server, ConfigMap hoặc biến môi trường của hệ điều hành. Khi process khởi động lại, thay đổi tạm thời có thể mất nếu nguồn cấu hình bền vững chưa được cập nhật.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của Actuator `env` endpoint và điều kiện để endpoint khả dụng qua HTTP.
2. Bật thao tác POST bằng `management.endpoint.env.post.enabled`.
3. Giới hạn property được phép cập nhật bằng `management.endpoint.env.post.valid-keys-regex`.
4. Gửi JSON request để thay đổi một property trong Environment đang chạy.
5. Giải thích vai trò của `EnvironmentManager` và `EnvironmentChangeEvent`.
6. Phân biệt Environment update, rebind `@ConfigurationProperties` và refresh `@RefreshScope`.
7. Xác minh giá trị mới trong Environment, bean đã bind và hành vi nghiệp vụ.
8. Nhận diện giới hạn với `@Value` snapshot, constructor-bound configuration và bean có state.
9. Bảo vệ endpoint khỏi truy cập trái phép, cập nhật key ngoài allowlist và lộ thông tin nhạy cảm.
10. Thiết kế quy trình cập nhật có audit, rollback và đồng bộ nhiều instance.

## 2. Endpoint env nằm ở đâu trong vòng đời ứng dụng?

### 2.1. Environment là nguồn tra cứu cấu hình đang có hiệu lực

Spring `Environment` tổng hợp nhiều `PropertySource` như file cấu hình, environment variables, JVM system properties, command-line arguments và nguồn cấu hình tích hợp. Khi code gọi:

~~~java
String mode = environment.getProperty("app.routing.mode");
~~~

Spring tra cứu các source theo thứ tự ưu tiên. Giá trị được trả về là giá trị hiệu lực tại thời điểm tra cứu.

Actuator `env` endpoint cho phép quan sát các property source và giá trị của Environment. Khi Spring Cloud Context cung cấp thao tác POST, một giá trị mới có thể được thêm vào một property source ưu tiên cao của Environment đang chạy. Những lần tra cứu sau có thể nhận giá trị vừa cập nhật.

### 2.2. Luồng xử lý POST

~~~mermaid
sequenceDiagram
    participant Operator as Operator / automation
    participant Actuator as POST /actuator/env
    participant Manager as EnvironmentManager
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Logger as LoggingRebinder
    Operator->>Actuator: JSON {name, value}
    Actuator->>Manager: setProperty(name, value)
    Manager->>Env: Ghi vào property source ưu tiên cao
    Manager->>Event: Publish key vừa thay đổi
    Event->>Rebind: Rebind @ConfigurationProperties
    Event->>Logger: Cập nhật logging.level.*
    Actuator-->>Operator: Kết quả thao tác
~~~

Luồng này có các lớp riêng:

1. Actuator nhận request và kiểm tra thao tác được bật, được expose và được phép truy cập.
2. EnvironmentManager ghi property vào Environment của process.
3. Spring Cloud phát event mô tả key thay đổi.
4. ConfigurationProperties rebinder cập nhật các bean cấu hình được hỗ trợ.
5. Logging rebinder áp dụng các key thuộc nhóm `logging.level.*`.
6. Ứng dụng tiếp tục chạy với trạng thái cấu hình mới theo khả năng của từng bean.

Không phải mọi singleton trong ứng dụng đều được tạo lại. Rebind cũng không đồng nghĩa với refresh toàn bộ ApplicationContext.

## 3. Phân biệt env endpoint với các endpoint quản trị khác

| Endpoint | Vai trò chính | Tác động điển hình |
| --- | --- | --- |
| `GET /actuator/env` | Quan sát Environment và property source. | Chỉ đọc; giá trị nhạy cảm thường được sanitize. |
| `POST /actuator/env` | Thêm/cập nhật property trong Environment đang chạy. | Phát EnvironmentChangeEvent; rebind configuration properties và cập nhật logging levels. |
| `POST /actuator/refresh` | Chạy quy trình refresh của Spring Cloud Context. | Nạp lại cấu hình theo cơ chế refresher và invalidate target cache của `@RefreshScope`. |
| `POST /actuator/restart` | Đóng và khởi động lại ApplicationContext nếu capability được bật. | Thực hiện lifecycle restart; không phải thao tác cập nhật một property đơn lẻ. |

Điểm cần nhớ:

- `env POST` thay đổi Environment và kích hoạt rebind.
- `refresh` xử lý thêm vòng đời refresh-scoped bean.
- `restart` tác động đến ApplicationContext.
- Cả ba endpoint đều cần được quản lý như thao tác quản trị, với quyền truy cập và audit phù hợp.

Nếu bean cần tạo lại target qua `@RefreshScope`, chỉ POST `/actuator/env` chưa đủ để xóa target cache. Hãy dùng quy trình refresh tương ứng khi thiết kế yêu cầu đó và xác minh nguồn cấu hình vẫn chứa giá trị mong muốn sau khi refresher chạy.

## 4. Điều kiện để bật POST /actuator/env

Cần phân biệt ba điều kiện: endpoint có tồn tại, endpoint được expose qua HTTP và thao tác ghi được bật.

### 4.1. Dependency

Ứng dụng cần Spring Boot Actuator và Spring Cloud Context tương thích với release train Spring Boot đang sử dụng. Với dự án Maven, các starter thường được khai báo theo BOM đã chọn:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

Đây là ví dụ dependency tối thiểu theo vai trò. Dự án có thể đã kéo Spring Cloud Context qua starter/integration khác; kiểm tra dependency tree và BOM thay vì thêm dependency trùng lặp.

### 4.2. Bật thao tác POST

Thuộc tính bật write operation:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
~~~

Nếu không bật thuộc tính này, việc expose endpoint `env` không đồng nghĩa thao tác POST đã khả dụng.

### 4.3. Expose endpoint qua HTTP

Spring Boot mặc định chỉ expose endpoint health qua HTTP. Để gọi `/actuator/env` từ HTTP, thêm endpoint ID `env` vào danh sách exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env
~~~

Nếu ứng dụng đã có danh sách exposure, hãy bổ sung `env` vào danh sách hiện có. Không thay bằng `*` chỉ để tiện thử nghiệm vì điều đó có thể mở thêm nhiều endpoint quản trị khác.

### 4.4. Đặt allowlist cho key được phép cập nhật

Spring Cloud Commons hiện hành hỗ trợ regex giới hạn property key mà POST được phép ghi:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout)|logging\.level\.com\.example\.[A-Za-z0-9_.]+)$'
~~~

Regex ví dụ chỉ cho phép:

- `app.runtime.mode`.
- `app.runtime.timeout`.
- Các key log bắt đầu bằng `logging.level.com.example.` và có phần tên logger phù hợp.

Dấu `^` và `$` neo biểu thức vào toàn bộ key. Các dấu chấm được escape để khớp dấu chấm thật trong tên property. YAML dùng dấu nháy đơn để giữ nguyên dấu gạch chéo ngược của regex.

Hãy xây allowlist theo từng nhóm property cụ thể. Tránh regex rộng như `.*`, `app\..*` hoặc cho phép mọi key có tiền tố `spring.`, `management.` hay `spring.datasource.`. Các nhóm đó có thể thay đổi hành vi hạ tầng, bảo mật hoặc vòng đời ứng dụng.

### 4.5. Một cấu hình lab đầy đủ

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout)|logging\.level\.com\.example\.[A-Za-z0-9_.]+)$'
      show-values: when-authorized
      roles: OPS_ADMIN
  endpoints:
    web:
      exposure:
        include: health,info,env
~~~

Cấu hình này minh họa:
- POST được bật.
- Chỉ key khớp allowlist mới được phép cập nhật.
- Endpoint env được expose qua HTTP.
- Giá trị trả về qua endpoint env chỉ hiển thị theo chính sách quyền đã cấu hình.

Cần có security configuration tương ứng để chỉ người dùng có role quản trị được thực hiện thao tác. `show-values` điều khiển việc hiển thị giá trị trong response; nó không thay thế authentication/authorization và không phải cơ chế allowlist cho POST.

## 5. Cảnh báo bảo mật: CVE-2026-59284

Spring công bố advisory **CVE-2026-59284 – Spring Cloud Commons no allow list for writable env actuator endpoint** ngày 20-08-2026. Vấn đề là các phiên bản bị ảnh hưởng không có allowlist cho property key khi writable `/actuator/env` được bật.

Các dải phiên bản bị ảnh hưởng được advisory liệt kê:

| Dòng Spring Cloud Commons | Phiên bản bị ảnh hưởng |
| --- | --- |
| 5.0.x | 5.0.0 đến 5.0.2 |
| 4.3.x | 4.3.0 đến 4.3.3 |
| 4.0.x đến 4.2.x | 4.0.0 đến 4.2.6 |
| 3.1.x | 3.1.10 và các bản cũ hơn |

Các bản sửa được advisory nêu:

| Dòng | Bản sửa |
| --- | --- |
| 5.0.x | 5.0.3 (OSS) |
| 4.3.x | 4.3.4 (Enterprise Support) |
| 4.2.x | 4.2.7 (Enterprise Support) |
| 3.1.x | 3.1.11 (Enterprise Support) |

Với ứng dụng có bật POST `/actuator/env`:

1. Nâng Spring Cloud Commons lên bản đã sửa tương ứng với chính sách hỗ trợ của dự án.
2. Cấu hình `management.endpoint.env.post.valid-keys-regex` với allowlist hẹp.
3. Không expose endpoint env ra mạng công cộng.
4. Bắt buộc xác thực và phân quyền cho thao tác ghi.
5. Theo dõi audit log và các lần cập nhật property.
6. Kiểm thử rằng key ngoài allowlist bị từ chối.

Không bật write operation trên phiên bản bị ảnh hưởng rồi trông chờ firewall hoặc regex tự viết ở tầng proxy thay thế bản vá của thư viện. Kiểm tra Spring Cloud BOM thực tế vì version của starter không nhất thiết bằng version của Spring Cloud Commons.

## 6. Gửi request POST

### 6.1. JSON body

Actuator nhận tên property và giá trị mới qua JSON body:

~~~json
{
  "name": "app.runtime.mode",
  "value": "safe"
}
~~~

`name` là key trong Environment. `value` là giá trị dạng chuỗi mà endpoint nhận; Binder/conversion của ứng dụng sẽ chuyển sang kiểu đích khi rebind configuration properties.

### 6.2. Gọi bằng curl

Ví dụ chạy trong môi trường lab đã cấu hình authentication:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.mode","value":"safe"}' \
  http://localhost:8080/actuator/env
~~~

Thay thông tin đăng nhập bằng cơ chế secret an toàn của môi trường. Không commit mật khẩu vào script, không lưu trong shell history dùng chung và không in credential ra log.

Nếu hệ thống dùng token thay cho HTTP Basic, truyền token bằng header Authorization theo cấu hình bảo mật thực tế. Nếu Spring Security đang bật CSRF protection cho endpoint này, client phải gửi CSRF token hợp lệ; không tắt CSRF toàn ứng dụng chỉ để request lab chạy được.

### 6.3. Thay một property khác

Ví dụ cập nhật timeout:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.timeout","value":"1500ms"}' \
  http://localhost:8080/actuator/env
~~~

Key này chỉ được chấp nhận nếu regex allowlist có cho phép `app.runtime.timeout`.

### 6.4. Cập nhật logging level

Ví dụ bật DEBUG cho một package:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"logging.level.com.example.orders","value":"DEBUG"}' \
  http://localhost:8080/actuator/env
~~~

Spring Cloud Context xử lý các key `logging.level.*` để cập nhật logger level. Đây là cách điều chỉnh mức log runtime mà không cần sửa file cấu hình và restart process.

Không bật DEBUG trên diện rộng trong production nếu chưa đánh giá lượng log, dữ liệu nhạy cảm và chi phí lưu trữ.

### 6.5. Kết quả HTTP

POST là write operation. Response thành công có thể là `204 No Content` khi operation không trả body; tùy phiên bản và implementation, hãy kiểm tra status thực tế thay vì phụ thuộc vào một response body cụ thể.

Các lỗi thường gặp:

- `404`: endpoint không tồn tại hoặc chưa được expose.
- `405`: write operation chưa được bật hoặc HTTP method không được hỗ trợ.
- `400`: request body thiếu field bắt buộc, kiểu dữ liệu không hợp lệ hoặc key bị validation từ chối.
- `401`: chưa xác thực.
- `403`: principal không có quyền hoặc bị CSRF/security policy từ chối.
- `5xx`: lỗi trong quá trình cập nhật Environment hoặc rebind bean.

Mã trạng thái cụ thể còn phụ thuộc phiên bản, cấu hình security và lỗi phát sinh. Hãy kiểm tra response body và server log trong môi trường được kiểm soát.

## 7. EnvironmentManager và EnvironmentChangeEvent

### 7.1. EnvironmentManager làm gì?

Spring Cloud Context cung cấp `EnvironmentManager` làm điểm vào để thực hiện thay đổi cục bộ trên Environment của ứng dụng đang chạy.

Về khái niệm, thao tác `setProperty(name, value)`:

1. Đưa key/value vào một property source ưu tiên cao trong Environment hiện tại.
2. Khiến lần tra cứu tiếp theo có thể nhận giá trị mới.
3. Phát event báo các key thay đổi để listener xử lý.

Các thay đổi này là **local và volatile**. Chúng không tự ghi lại file YAML, Config Server hay nguồn cấu hình bên ngoài. Nếu process khởi động lại, giá trị do EnvironmentManager thêm vào có thể không còn.

### 7.2. EnvironmentChangeEvent mang danh sách key thay đổi

`EnvironmentChangeEvent` chứa tập key đã thay đổi. Các listener tiêu chuẩn của Spring Cloud dùng event để:

- Rebind các bean `@ConfigurationProperties` được hỗ trợ trong context.
- Cập nhật logger level cho các key `logging.level.*`.

Ứng dụng có thể bổ sung listener riêng nếu một thành phần tùy biến cần phản ứng với các key nhất định. Listener nên lọc key cụ thể, kiểm tra giá trị mới và xử lý lỗi có kiểm soát.

### 7.3. Không phải mọi bean đều tự cập nhật

| Thành phần | Hành vi sau POST env |
| --- | --- |
| `Environment.getProperty(key)` | Lần tra cứu sau có thể thấy giá trị mới. |
| Mutable `@ConfigurationProperties` | Được rebinding qua EnvironmentChangeEvent nếu bean thuộc nhóm được hỗ trợ. |
| `logging.level.*` | Logging rebinder cập nhật mức log tương ứng. |
| Singleton có `@Value` inject vào constructor/field | Thường giữ snapshot cũ; không tự inject lại. |
| Constructor-bound `@ConfigurationProperties` / Java record | Không được rebinding trực tiếp theo cơ chế thông thường. |
| Bean `@RefreshScope` | POST env không tự invalidate target cache của bean. |
| Bean tùy biến không lắng nghe event | Không tự biết property đã thay đổi. |

Vì vậy, sau khi POST thành công, hãy kiểm tra cả Environment lẫn bean thực tế. Chỉ nhìn thấy giá trị mới ở `/actuator/env` chưa chứng minh mọi thành phần đã sử dụng giá trị đó.

## 8. Rebind @ConfigurationProperties

### 8.1. Ví dụ mutable configuration bean

Cấu hình:

~~~yaml
app:
  runtime:
    mode: standard
    timeout: 800ms
~~~

Bean mutable:

~~~java
@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeProperties {

    private String mode;
    private Duration timeout;

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RuntimeProperties.class)`. Bean có thể được inject vào service:

~~~java
@Service
public class RoutingService {

    private final RuntimeProperties properties;

    public RoutingService(RuntimeProperties properties) {
        this.properties = properties;
    }

    public String currentMode() {
        return properties.getMode();
    }
}
~~~

Khi POST `app.runtime.mode=safe`, Spring Cloud phát event và rebinder cập nhật bean mutable. Lần gọi `currentMode()` sau khi rebind hoàn tất có thể trả `safe`.

### 8.2. Conversion và validation

Giá trị gửi qua POST thường là chuỗi. Binder chuyển đổi sang kiểu property tương ứng, ví dụ:

- `1500ms` thành `Duration`.
- `true` thành `boolean`.
- `5` thành `int`.
- `ROUND_ROBIN` thành enum nếu có giá trị enum phù hợp.

Nếu dùng `@Validated` và Bean Validation, cấu hình mới phải thỏa các constraint. Một giá trị sai định dạng hoặc vi phạm constraint có thể làm rebind thất bại. Hãy kiểm tra lỗi rebinding và trạng thái ứng dụng; không giả định response POST thành công đồng nghĩa mọi bean đã nhận giá trị mới một cách hoàn chỉnh.

### 8.3. Rebind không phải giao dịch atomic cho toàn bộ ứng dụng

Rebind cập nhật bean cấu hình theo cơ chế của Spring Cloud. Nếu một bean có nhiều field liên quan, thread khác có thể đọc object trong lúc quá trình cập nhật đang diễn ra. Cần cân nhắc:

- Dùng snapshot bất biến nếu nhiều giá trị phải nhất quán với nhau.
- Chỉ thay đổi runtime các property có semantics rõ ràng.
- Tránh POST nhiều key liên quan theo các request rời rạc nếu nghiệp vụ yêu cầu chúng phải đổi đồng thời.
- Có version/revision cấu hình để kiểm tra trạng thái.
- Test hành vi dưới tải khi property được cập nhật.

Nếu cần thay một nhóm state như một đơn vị, cân nhắc refresh-scoped target hoặc rollout instance theo một revision mới.

## 9. Quan hệ với @Value và @RefreshScope

### 9.1. @Value không tự inject lại

Ví dụ singleton:

~~~java
@Component
public class GreetingService {

    private final String greeting;

    public GreetingService(@Value("${app.runtime.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
~~~

`greeting` được inject khi bean được tạo. POST `/actuator/env` có thể làm Environment trả giá trị mới nhưng không tự gọi lại constructor của singleton này. Nếu yêu cầu bean phải dùng giá trị mới, hãy thiết kế cách đọc động hoặc cơ chế tạo lại bean phù hợp.

### 9.2. @RefreshScope là cơ chế khác

Bean được đánh dấu `@RefreshScope` được truy cập qua scoped proxy. Target cache bị invalidate trong quy trình refresh; lần gọi tiếp theo tạo target mới.

POST `/actuator/env` tập trung vào Environment update và rebinding. Nó không phải thao tác xóa cache `RefreshScope`. Endpoint `/actuator/refresh` thực hiện quy trình refresh của Spring Cloud, bao gồm xử lý cấu hình theo cơ chế refresher và invalidate target refresh scope.

Nếu kết hợp hai cơ chế, hãy xác định thứ tự cập nhật nguồn, Environment và target. Không gọi refresh một cách máy móc nếu việc nạp lại Config Server có thể thay đổi giá trị vừa cập nhật cục bộ.

### 9.3. Constructor-bound configuration

Java record hoặc class constructor-bound được tạo từ giá trị tại thời điểm binding. Chúng không được rebinding trực tiếp theo cơ chế thông thường của Spring Cloud Context. Nếu cần cập nhật runtime, hãy chọn mutable configuration bean, refresh-scoped snapshot được thiết kế đúng hoặc restart/rollout.

## 10. Xác minh sau khi cập nhật

### 10.1. Kiểm tra Environment

Có thể đọc key cụ thể:

~~~bash
curl --user ops-user:REPLACE_WITH_SECRET \
  http://localhost:8080/actuator/env/app.runtime.mode
~~~

Endpoint env có thể sanitize giá trị nhạy cảm. Không thay đổi chính sách sanitize toàn cục chỉ để nhìn thấy secret trong response.

### 10.2. Kiểm tra configuration properties

`/actuator/configprops` cung cấp thông tin tổng hợp các bean `@ConfigurationProperties`. Dùng endpoint này trong môi trường được bảo vệ để xác minh bean đã bind nhận giá trị mới.

Không mặc định expose endpoint configprops công khai. Response có thể chứa dữ liệu nhạy cảm hoặc thông tin cấu trúc nội bộ; giữ sanitization và phân quyền.

### 10.3. Kiểm tra hành vi nghiệp vụ

Tốt nhất, ngoài kiểm tra endpoint quản trị, hãy gọi một API nghiệp vụ an toàn để xác minh giá trị mới thực sự có tác động như mong đợi.

Ví dụ:
- Mode routing mới được sử dụng.
- Timeout mới được áp dụng cho request tiếp theo.
- Logger chỉ ghi DEBUG ở package đã chọn.
- Bean mutable trả về giá trị mới sau khi rebind.

Không tạo endpoint debug trả toàn bộ Environment cho production. Chỉ quan sát các key không nhạy cảm cần thiết.

### 10.4. Ghi nhận revision

Trong hệ thống vận hành, mỗi lần cập nhật nên ghi nhận:

- Property key được phép thay đổi.
- Revision hoặc ticket cấu hình liên quan.
- Người/automation yêu cầu.
- Instance nhận request.
- Thời điểm và kết quả.
- Giá trị trước/sau đã được mask nếu cần.
- Kết quả xác minh bean và nghiệp vụ.

Không ghi password, token, private key hoặc secret vào audit log.

## 11. Mỗi instance có Environment riêng

POST `/actuator/env` chỉ cập nhật Environment của instance nhận request. Trong hệ thống có nhiều replica, các instance khác không tự nhận giá trị này.

Ví dụ có ba instance:

| Instance | Nhận POST? | Giá trị sau thao tác |
| --- | --- | --- |
| `orders-1` | Có | `safe` |
| `orders-2` | Không | Có thể vẫn `standard` |
| `orders-3` | Không | Có thể vẫn `standard` |

Để đồng bộ nhiều instance, cần một cơ chế phân phối có chủ đích:

- Ghi cấu hình vào nguồn bền vững như Config Server hoặc hệ thống quản lý cấu hình.
- Dùng Spring Cloud Bus để broadcast event refresh khi phù hợp.
- Dùng orchestration/automation gọi endpoint quản trị trên từng instance theo quy trình kiểm soát.
- Dùng rolling deployment nếu thay đổi yêu cầu cùng revision hoặc cần khởi động lại tài nguyên.

Spring Cloud Config Client không mặc định polling liên tục để tự phát hiện thay đổi Environment. Không xem POST thành công trên một replica là bằng chứng toàn cluster đã cập nhật.

## 12. Quy trình vận hành có kiểm soát

Một quy trình phù hợp cho thay đổi runtime:

1. Xác định key được phép cập nhật và mục đích thay đổi.
2. Kiểm tra key có khớp allowlist regex không.
3. Xác minh giá trị mới hợp lệ với kiểu dữ liệu và constraint.
4. Ghi audit request và revision.
5. Gửi POST đến instance mục tiêu.
6. Kiểm tra response và log server.
7. Đọc lại Environment và configuration properties.
8. Gọi một luồng nghiệp vụ an toàn để xác minh hành vi.
9. Nếu có nhiều instance, phân phối thay đổi đến các replica còn lại hoặc dùng cơ chế broadcast.
10. Theo dõi lỗi và latency sau thay đổi.
11. Nếu kết quả không đúng, ghi lại giá trị trước và khôi phục bằng một thao tác được allowlist cho phép.
12. Cập nhật nguồn cấu hình bền vững nếu muốn thay đổi tồn tại sau restart.

Không nên để thao tác POST trực tiếp trở thành nguồn sự thật lâu dài. Hãy cập nhật hệ thống quản lý cấu hình chuẩn để lần deploy tiếp theo không ghi đè ngược giá trị runtime.

## 13. Bài thực hành: thay đổi mode và timeout

### 13.1. Chuẩn bị

Tạo ứng dụng Spring Boot có:

- Spring Boot Actuator.
- Spring Cloud Context tương thích.
- Mutable `@ConfigurationProperties` bean `RuntimeProperties`.
- Endpoint nghiệp vụ lab đọc `mode` và `timeout`.
- Security policy chỉ cho role quản trị truy cập actuator.
- Allowlist regex chỉ cho phép hai key runtime của lab.

Cấu hình:

~~~yaml
app:
  runtime:
    mode: standard
    timeout: 800ms

management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout))$'
      show-values: when-authorized
      roles: OPS_ADMIN
  endpoints:
    web:
      exposure:
        include: health,env,configprops
~~~

Đây là cấu hình lab. Production cần security chain, network policy, audit và endpoint exposure được xem xét riêng.

### 13.2. Thử cập nhật mode

Gửi:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.mode","value":"safe"}' \
  http://localhost:8080/actuator/env
~~~

Sau đó:

1. Đọc `app.runtime.mode` từ Environment.
2. Kiểm tra bean RuntimeProperties.
3. Gọi endpoint nghiệp vụ lab.
4. Xác nhận mode mới được sử dụng.

### 13.3. Thử cập nhật timeout

Gửi:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.timeout","value":"1500ms"}' \
  http://localhost:8080/actuator/env
~~~

Kiểm tra Environment, bean và hành vi timeout. Nếu service đã tạo client/connection pool giữ timeout trong constructor, việc rebind RuntimeProperties không tự cấu hình lại resource đó. Cần đánh giá lifecycle của bean sử dụng timeout.

### 13.4. Thử key ngoài allowlist

Gửi key không được phép, ví dụ:

~~~json
{
  "name": "spring.datasource.url",
  "value": "jdbc:postgresql://other-host:5432/orders"
}
~~~

Kết quả mong đợi: request bị từ chối do key không khớp allowlist. Xác minh Environment và DataSource không thay đổi.

### 13.5. Thử principal không có quyền

Gửi cùng request bằng principal không có role `OPS_ADMIN`. Kết quả phải bị security policy từ chối. Kiểm tra audit log và xác minh không có property nào được cập nhật.

## 14. Ma trận kiểm thử

| ID | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| E1 | POST với key hợp lệ và value hợp lệ. | Environment nhận giá trị mới. |
| E2 | POST key ngoài allowlist. | Request bị từ chối; giá trị không đổi. |
| E3 | POST thiếu `name` hoặc `value`. | Request lỗi validation/input; không thay đổi ngoài dự kiến. |
| E4 | POST value sai kiểu cho property. | Rebind/conversion báo lỗi; quan sát bean và trạng thái ứng dụng. |
| E5 | POST mutable `@ConfigurationProperties`. | Bean được rebind sau EnvironmentChangeEvent. |
| E6 | POST property được inject qua `@Value` vào singleton. | Singleton snapshot không tự đổi. |
| E7 | POST property dùng bởi `@RefreshScope` target. | Environment đổi; target cache không tự bị invalidate chỉ bởi env POST. |
| E8 | POST key `logging.level.*` hợp lệ. | Logger level thay đổi theo cấu hình mới. |
| E9 | GET env/configprops sau POST. | Quan sát được giá trị đã cập nhật, có sanitize. |
| E10 | Gọi POST bằng principal thiếu quyền. | Bị từ chối; không thay đổi Environment. |
| E11 | POST tới một replica trong cluster. | Chỉ replica đó được cập nhật. |
| E12 | Restart process sau POST. | Thay đổi volatile không còn nếu chưa lưu vào nguồn bền vững. |
| E13 | Dùng Spring Cloud Commons phiên bản bị ảnh hưởng bởi CVE. | Không bật writable env; nâng lên bản đã sửa trước khi dùng. |
| E14 | Rebind nhiều key liên quan dưới tải. | Kiểm tra trạng thái trung gian và tính nhất quán nghiệp vụ. |

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `POST /actuator/env` trả 404. | Actuator thiếu, endpoint không khả dụng hoặc chưa expose qua HTTP. | Kiểm tra dependency và `management.endpoints.web.exposure.include`. |
| GET env hoạt động nhưng POST không hoạt động. | Write operation chưa được bật. | Kiểm tra `management.endpoint.env.post.enabled=true` và version Spring Cloud. |
| POST bị từ chối dù endpoint đã bật. | Key không khớp `valid-keys-regex` hoặc security từ chối. | Kiểm tra regex, principal, role và CSRF policy. |
| Environment có giá trị mới nhưng bean vẫn cũ. | Bean không phải mutable `@ConfigurationProperties` hoặc event/rebind chưa hoàn tất. | Kiểm tra loại bean, event và configprops. |
| `@Value` singleton vẫn trả giá trị cũ. | Giá trị đã được snapshot khi bean tạo. | Dùng tra cứu động hoặc thiết kế refresh scope phù hợp. |
| Refresh-scoped bean vẫn giữ target cũ. | POST env không invalidate refresh scope cache. | Chạy quy trình refresh riêng nếu target cần tạo lại. |
| Giá trị timeout mới không ảnh hưởng client. | Client đã snapshot timeout khi khởi tạo. | Đánh giá lifecycle client và tạo lại resource an toàn. |
| POST thành công nhưng sau restart giá trị biến mất. | EnvironmentManager lưu thay đổi local/volatile. | Cập nhật nguồn cấu hình bền vững. |
| Một số replica có giá trị khác nhau. | Chỉ một instance nhận POST. | Dùng broadcast/rollout hoặc gọi có kiểm soát tới từng instance. |
| Endpoint lộ giá trị nhạy cảm. | Exposure hoặc show-values/security không phù hợp. | Giữ sanitize, giới hạn role, network và endpoint exposure. |
| POST làm thay đổi cấu hình ngoài ý muốn. | Regex allowlist quá rộng hoặc cho phép key hạ tầng. | Thu hẹp regex, nâng bản vá và audit key được phép. |
| Rebind phát sinh lỗi hoặc trạng thái không nhất quán. | Giá trị không hợp lệ, mutable bean hoặc nhiều key phụ thuộc nhau. | Validate trước, cập nhật theo snapshot/rollout và theo dõi lỗi rebinder. |

## 16. Checklist hoàn thành

- [ ] Giải thích được vai trò của `/actuator/env`.
- [ ] Phân biệt endpoint khả dụng, exposure qua HTTP và write operation.
- [ ] Bật `management.endpoint.env.post.enabled`.
- [ ] Expose endpoint env trong danh sách HTTP exposure.
- [ ] Đặt `management.endpoint.env.post.valid-keys-regex` với allowlist hẹp.
- [ ] Biết định dạng JSON body gồm `name` và `value`.
- [ ] Gửi được POST bằng client quản trị có xác thực.
- [ ] Giải thích được EnvironmentManager lưu thay đổi local/volatile.
- [ ] Hiểu EnvironmentChangeEvent kích hoạt rebind configuration properties và logging levels.
- [ ] Phân biệt mutable configuration properties, `@Value` snapshot và constructor-bound config.
- [ ] Phân biệt env POST với refresh scope và restart.
- [ ] Kiểm tra được Environment và bean sau khi cập nhật.
- [ ] Biết POST một instance không đồng bộ các replica khác.
- [ ] Nâng Spring Cloud Commons lên phiên bản đã vá CVE-2026-59284 trước khi bật writable env.
- [ ] Có authentication, authorization, CSRF policy, network restriction và audit.
- [ ] Có phương án rollback và cập nhật nguồn cấu hình bền vững.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment Changes, rebind và thao tác POST `/actuator/env`.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính quản trị của Spring Cloud Context.
- [Spring Security Advisory CVE-2026-59284](https://spring.io/security/cve-2026-59284/): các phiên bản bị ảnh hưởng, bản sửa và yêu cầu allowlist cho writable env endpoint.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint availability, exposure, security, JSON input và response semantics.

Hãy đối chiếu đúng Spring Boot/Spring Cloud release train của ứng dụng. Thao tác POST chỉ thay đổi Environment của process đang chạy; mọi quyết định rebind, refresh bean, cập nhật nguồn cấu hình bền vững và đồng bộ cluster cần được kiểm chứng riêng.
