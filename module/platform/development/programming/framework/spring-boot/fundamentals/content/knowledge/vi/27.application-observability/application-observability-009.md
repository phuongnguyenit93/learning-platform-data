# Dữ liệu cấu hình nhạy cảm và chính sách công bố endpoint

Spring Boot Actuator giúp quan sát một ứng dụng đang chạy thông qua các endpoint như `health`, `info`, `metrics`, `env`, `configprops`, `loggers` hoặc `heapdump`. Những endpoint này rất hữu ích cho vận hành, nhưng không phải endpoint nào cũng nên được truy cập từ mọi mạng hay bởi mọi tài khoản.

Một yêu cầu quan trọng trong vận hành là **chỉ công bố thông tin cần thiết cho đúng đối tượng**. Tên endpoint, địa chỉ truy cập, trạng thái xác thực, mức chi tiết của response và dữ liệu được đưa vào metric/log đều có ảnh hưởng đến khả năng lộ thông tin.

Ví dụ, `/actuator/env` có thể cho biết tên property sources, profiles và cấu trúc cấu hình. `/actuator/configprops` cho biết các nhóm `@ConfigurationProperties`. `/actuator/heapdump` có thể chứa dữ liệu còn nằm trong bộ nhớ tiến trình. `/actuator/loggers` có thể điều chỉnh mức log lúc runtime. Ngay cả endpoint chỉ đọc như `mappings`, `beans` hoặc `metrics` cũng có thể tiết lộ cấu trúc nội bộ hoặc nhãn dữ liệu không nên công khai.

Bài học này tập trung vào Spring Boot **3.3**, Spring MVC và Spring Security 6 ở những ví dụ HTTP. Nó trình bày cách phân loại dữ liệu nhạy cảm, cấu hình exposure, cơ chế che giá trị, quyền truy cập, health details, management network, chính sách triển khai và cách kiểm thử để tránh vô tình công bố thông tin.

## 1. Quan sát ứng dụng không đồng nghĩa công khai mọi dữ liệu

Observability thường cần ba nguồn tín hiệu: logs, metrics và traces. Actuator cung cấp một số endpoint để đọc hoặc điều khiển các thành phần liên quan. Tuy nhiên, một endpoint hỗ trợ quan sát có thể trả về nhiều thông tin hơn một dashboard hoặc health check thực sự cần.

Ví dụ, các bên liên quan có nhu cầu khác nhau:

| Đối tượng | Dữ liệu thường cần | Không nên cấp mặc định |
| --- | --- | --- |
| Load balancer/kubelet | Health hoặc readiness status | Property sources, heap dump |
| Metrics scraper | Các metric đã được chọn | Secret, bản đồ toàn bộ bean |
| Developer ở môi trường test | Condition report, logger detail | Dữ liệu production nhạy cảm |
| SRE/operations | Một số endpoint chẩn đoán nội bộ | Quyền thay đổi mọi endpoint không kiểm soát |
| Người dùng cuối | API nghiệp vụ | Internal management endpoints |
| Hệ thống kiểm toán | Sự kiện truy cập/quản trị phù hợp | Dump toàn bộ bộ nhớ hoặc thông tin xác thực |

Vì thế “có endpoint” và “nên mở endpoint” là hai quyết định tách biệt. Một endpoint có thể rất cần thiết khi chẩn đoán nhưng vẫn phải bị giới hạn ở mạng nội bộ, tài khoản có vai trò phù hợp và thời gian truy cập được kiểm soát.

### 1.1. Những loại dữ liệu dễ bị lộ

Thông tin nhạy cảm không chỉ là password. Ví dụ:

- Password, API key, access token, private key, client secret, session cookie.
- URL chứa credential hoặc query parameter nhạy cảm.
- Database hostname, internal service name, private IP hoặc endpoint hạ tầng.
- Tên bean, tên class, package và internal route mapping.
- Giá trị config của một tenant cụ thể.
- Request/response body, header hoặc thông tin nhận dạng trong HTTP exchanges.
- Metric label có user ID, email, token hoặc thông tin cá nhân.
- Thread stack, heap object, buffer và dữ liệu trong memory dump.

Không phải thông tin nào cũng có mức rủi ro giống nhau. Chính sách cần dựa trên **tác hại nếu thông tin bị tiết lộ hoặc endpoint bị thao tác**, không chỉ dựa trên việc endpoint có chữ “secret” trong tên.

## 2. Các lớp kiểm soát của một Actuator endpoint

Để một endpoint Actuator có thể được gọi qua HTTP, cần phân biệt ít nhất ba lớp:

1. **Enablement**: endpoint được bật và tồn tại trong application context hay không.
2. **Exposure**: endpoint được công bố qua HTTP/JMX hay không.
3. **Security/authorization**: request có vượt qua xác thực và kiểm tra quyền hay không.

Một lớp thứ tư quan trọng là **response disclosure**: dù có quyền gọi endpoint, response được phép thể hiện mức chi tiết nào?

~~~mermaid
flowchart TD
    A["Có endpoint trong ứng dụng?"] --> B{"Endpoint enabled?"}
    B -->|Không| X["Không có endpoint khả dụng"]
    B -->|Có| C{"Exposed qua HTTP/JMX?"}
    C -->|Không| Y["Không truy cập qua transport đó"]
    C -->|Có| D{"Network + authentication + authorization?"}
    D -->|Không| Z["Từ chối truy cập"]
    D -->|Có| E{"Chính sách hiển thị dữ liệu"}
    E --> F["Status / metadata cho phép"]
    E --> G["Giá trị đã che / chi tiết giới hạn"]
~~~

Một endpoint **exposed** chưa chắc caller được phép truy cập. Ngược lại, một endpoint không exposed thì SecurityFilterChain không tự khiến nó có URL HTTP. Và việc caller đã được xác thực cũng không có nghĩa mọi secret phải được trả về nguyên văn.

### 2.1. Endpoint enablement

Trong Spring Boot 3.3, phần lớn built-in endpoints được bật mặc định, ngoại trừ `shutdown`. Bạn có thể disable một endpoint:

~~~properties
management.endpoint.env.enabled=false
~~~

Hoặc chuyển sang mô hình opt-in:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
~~~

Cấu hình trên **chỉ bật** `health` và `info`; các endpoint khác không được bật theo mặc định. Nếu muốn cả hai xuất hiện qua HTTP, cần xét thêm cấu hình web exposure.

Endpoint bị disable không chỉ bị ẩn một URL; nó không còn được cung cấp như endpoint khả dụng trong context theo cơ chế của Actuator.

### 2.2. Endpoint exposure

HTTP exposure trong Spring Boot 3.3 mặc định là:

~~~properties
management.endpoints.web.exposure.include=health
~~~

JMX exposure cũng mặc định chỉ gồm `health` trong nhánh 3.3.

Muốn cho phép thêm `info` và `prometheus` qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

`prometheus` chỉ có sẵn khi ứng dụng có dependency và cấu hình Micrometer registry phù hợp; đưa một tên vào include không tự cài đặt dependency tạo endpoint đó.

Có thể loại trừ endpoint bằng:

~~~properties
management.endpoints.web.exposure.include=health,info,env
management.endpoints.web.exposure.exclude=env
~~~

Trong cấu hình include/exclude, **exclude được ưu tiên**. Vì vậy `env` không được exposed qua HTTP trong ví dụ này.

### 2.3. Xác thực và phân quyền

Nếu Spring Security có trên classpath và ứng dụng không tự định nghĩa `SecurityFilterChain`, Spring Boot 3.3 có auto-configuration để bảo vệ các Actuator endpoints khác `health` khi chúng được exposed.

Nhưng nếu ứng dụng **tự khai báo một `SecurityFilterChain`**, cấu hình bảo vệ mặc định của Boot đối với Actuator sẽ nhường quyền cho ứng dụng. Khi đó bạn phải tự bảo vệ management endpoints, cùng phần còn lại của web application.

Không nên dựa vào tư duy “Spring Security đã nằm trong dependencies nên chắc chắn mọi endpoint đã được bảo vệ đúng”. Hãy đọc **các filter chain và matcher thực tế** của ứng dụng.

### 2.4. Mức độ chi tiết của response

Ví dụ `health` có thể trả trạng thái tổng quát cho public probe nhưng không trả về tình trạng database cụ thể hoặc cấu trúc thành phần.

`env` và `configprops` có thể trả nhiều tên property nhưng che giá trị theo policy `show-values`. Đây là một lớp bảo vệ dữ liệu nằm **sau** quyết định có cho request đi tới endpoint hay không.

## 3. Mặc định của Actuator trong Spring Boot 3.3

Thêm Actuator bằng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Với ứng dụng web có Actuator và cấu hình tiêu chuẩn, URL mặc định cho health là:

~~~http
GET /actuator/health
~~~

Response đơn giản có thể là:

~~~json
{"status":"UP"}
~~~

Các điểm cần nhớ ở Spring Boot 3.3:

| Thiết lập | Giá trị/hành vi mặc định đáng chú ý |
| --- | --- |
| HTTP exposure | Chỉ `health` |
| JMX exposure | Chỉ `health` |
| Phần lớn endpoint enablement | Bật, nhưng chưa chắc exposed |
| `shutdown` | Disabled |
| `health.show-details` | `never` |
| Giá trị của `env`, `configprops`, `quartz` | Mặc định được che `******` |
| Web base path | `/actuator` |

Kết quả cụ thể còn phụ thuộc dependency, application type và custom configuration. Ví dụ `prometheus`, `httpexchanges` hoặc `startup` có điều kiện cung cấp endpoint riêng.

### 3.1. Phân biệt enabled và exposed bằng ví dụ

Giả sử:

~~~yaml
management:
  endpoint:
    env:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

`env` được bật, nhưng **không có trong HTTP include list**. Vì vậy `/actuator/env` không trở thành URL được exposed chỉ nhờ `enabled: true`.

Để `env` có URL, bạn phải include `env` trong web exposure; đó cũng chính là thời điểm phải quyết định có thật sự cần công bố nó hay không.

### 3.2. Tránh include tất cả

Một cấu hình cần đặc biệt thận trọng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Dấu `*` phải được đặt trong dấu nháy ở YAML. Quan trọng hơn, cấu hình này mở phạm vi exposure rất rộng, có thể gồm các endpoint không phù hợp để công bố trên mạng mà service đang dùng.

Ngay cả khi bạn đang đặt Spring Security, chính sách tốt hơn thường là **allowlist**: chỉ include những endpoint cần thiết theo nhu cầu quan sát.

## 4. Rủi ro của từng nhóm endpoint

Không phải endpoint nào cũng nhạy cảm theo cùng cách.

| Endpoint | Thông tin/hành vi | Rủi ro chính |
| --- | --- | --- |
| `health` | Status và thông tin health contributors | Lộ topology/tình trạng dependency nếu mở details |
| `info` | Thông tin ứng dụng do cấu hình/contributor cung cấp | Lộ version, commit, environment hoặc metadata riêng |
| `metrics` | Metrics và available meter names/tags | Lộ operational metadata và labels không an toàn |
| `prometheus` | Metrics theo định dạng scrape | Lộ metric labels và cấu trúc hoạt động |
| `env` | Environment property sources và values theo policy | Lộ property names, config topology và secrets khi hiện giá trị |
| `configprops` | Các nhóm @ConfigurationProperties và values theo policy | Lộ cấu trúc và dữ liệu cấu hình |
| `beans` | Bean names, types, dependencies | Lộ kiến trúc ứng dụng |
| `conditions` | Auto-configuration condition report | Lộ các thư viện và tính năng đang hoạt động |
| `mappings` | Request mappings | Lộ HTTP routes/internal endpoint structure |
| `loggers` | Xem và thay đổi logger levels | Thao tác runtime có thể bật DEBUG/TRACE nhạy cảm |
| `logfile` | Nội dung file log nếu được cấu hình | Có thể có token, headers, request data |
| `httpexchanges` | Thông tin HTTP exchanges nếu có repository | Có thể lộ request/response metadata |
| `threaddump` | Thread stacks | Lộ implementation, tên class/method và trạng thái |
| `heapdump` | Dữ liệu heap trong process | Có thể chứa secrets, PII, session data, buffer |
| `shutdown` | Yêu cầu dừng ứng dụng | Rủi ro thay đổi availability |

Bảng này không nói rằng mọi endpoint đều trả về secrets. Nó nhấn mạnh rằng **những endpoint có thể mang thông tin nhạy cảm hoặc thay đổi trạng thái cần chính sách riêng**.

### 4.1. Chỉ đọc vẫn có thể nguy hiểm

Một endpoint có HTTP method GET không nhất thiết an toàn để công bố. `heapdump` là ví dụ: tải một memory dump có thể thu được những object còn chứa credential hoặc dữ liệu ứng dụng.

Ngay cả khi response được gửi qua HTTPS, người nhận có thể lưu file về máy không được quản lý. Cần kiểm soát cả **ai được tải, nơi lưu, thời hạn giữ và cách xóa dữ liệu**.

### 4.2. Endpoint cho phép thay đổi trạng thái cần kiểm soát chặt hơn

`loggers` có thao tác thay đổi level bằng POST. `shutdown` có hành vi dừng ứng dụng nếu được bật. Một số endpoint với operation ghi/xóa khác cũng có thể làm thay đổi state.

Không chỉ xác thực người gọi; cần phân quyền thao tác và audit khi có thay đổi, tránh cấp rộng cho mọi tài khoản đã login.

## 5. Env và configprops: vì sao có cơ chế che giá trị?

`/actuator/env` cung cấp thông tin về `Environment` và các property sources. `/actuator/configprops` tổng hợp các bean được bind bằng `@ConfigurationProperties`. Cả hai giúp chẩn đoán sai cấu hình nhưng cũng có thể chạm đến các giá trị nhạy cảm.

Một ví dụ cấu hình ứng dụng:

~~~yaml
app:
  billing:
    endpoint: https://billing.internal.example
    connect-timeout: 3s
    api-key: ${BILLING_API_KEY}
~~~

Code có thể bind:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app.billing")
public record BillingProperties(
        String endpoint,
        Duration connectTimeout,
        String apiKey
) {}
~~~

`api-key` là dữ liệu không nên trả về nguyên văn qua public management endpoint. Thậm chí `endpoint` có thể là thông tin nội bộ cần giới hạn tùy môi trường.

### 5.1. Sanitization mặc định của Spring Boot 3.3

Trong Spring Boot 3.3, các endpoint `env`, `configprops` và `quartz` mặc định **che toàn bộ giá trị** (hiển thị dạng `******`). Đây là hành vi bảo vệ ngay cả khi value nhìn có vẻ không nhạy cảm.

Ví dụ dữ liệu phản hồi minh họa:

~~~json
{
  "property": {
    "value": "******",
    "origin": "class path resource [application.yml]"
  }
}
~~~

Cấu trúc JSON của endpoint thực tế có thể khác tùy URL và phiên bản. Điểm cần chú ý là value bị che, **nhưng tên property hoặc origin/metadata có thể vẫn hiển thị**. Vì thế che value không làm endpoint trở nên an toàn cho mọi đối tượng.

### 5.2. show-values có ba chế độ

Với các sanitizable endpoints, property `show-values` có các mức:

| Giá trị | Ý nghĩa |
| --- | --- |
| `never` | Luôn che values |
| `when-authorized` | Chỉ cho phép người dùng được coi là authorized xem values không bị che bởi cơ chế này |
| `always` | Cho phép hiển thị values cho mọi caller đi tới endpoint, trừ khi custom sanitizing function vẫn che |

Ví dụ:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

Đây là một cấu hình tường minh, nhất quán với mặc định bảo vệ.

**Không dùng `show-values=always` trong production chỉ để debug nhanh.** Nếu endpoint được exposed và caller có thể truy cập, những thông tin cấu hình mà bạn không định công bố có thể bị trả về nguyên văn.

### 5.3. when-authorized cần roles rõ ràng

Ví dụ chỉ cho phép tài khoản có vai trò quản trị Actuator xem giá trị trong `env`:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Với HTTP, user phải authenticated và thỏa role cấu hình để được coi là authorized cho việc hiển thị values. Trong Spring Boot 3.3, nếu không cấu hình roles cho endpoint, **mọi user đã authenticated** thường được coi là authorized khi bật `when-authorized`.

Do đó:

~~~properties
management.endpoint.env.show-values=when-authorized
~~~

không đồng nghĩa “chỉ SRE/admin được xem values”. Nếu không đặt roles, quyền có thể rộng hơn dự kiến.

### 5.4. Roles cho env và configprops là hai cấu hình độc lập

Nếu thực sự cần mở cả hai endpoint để chẩn đoán nội bộ:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
    configprops:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Điều này **chưa bảo vệ HTTP URL** nếu filter chain hoặc network policy cho người khác đi tới. Hãy kết hợp với endpoint exposure allowlist và Spring Security authorization.

Ngoài ra, một user có quyền xem value vẫn không nên nhận toàn bộ secrets nếu nghiệp vụ không yêu cầu. Khi có thể, hãy giữ `show-values=never` và cung cấp một diagnostics endpoint riêng chỉ trả metadata an toàn.

### 5.5. JMX không dùng cùng cơ chế HTTP authentication

Trong Spring Boot 3.3, theo `show-values` policy của các sanitizable endpoints, khi endpoint được truy cập qua JMX, caller được xem là authorized trong phép kiểm tra của Actuator. Vì vậy `when-authorized` không phải là tường lửa bảo vệ JMX tương đương Spring Security HTTP filter chain.

Nếu tổ chức dùng JMX, phải thiết lập **JMX connector authentication, network access controls và JMX exposure** riêng; hoặc giữ JMX exposure thật hạn chế.

## 6. SanitizingFunction: một lớp che giá trị bổ sung

Spring Boot 3.3 có extension point `SanitizingFunction` để tùy chỉnh việc che một số value khi chúng đi qua quá trình sanitization của endpoint.

Điểm quan trọng: một custom sanitizing function có thể tiếp tục che những value nhất định, ngay cả khi `show-values` đã cho phép hiển thị.

Một cách hiểu chính sách:

- `show-values` quyết định có cho phép hiển thị raw values trong hoàn cảnh đó hay không.
- `SanitizingFunction` cho phép áp thêm quy tắc che dữ liệu phù hợp.
- HTTP authentication/authorization quyết định ai được truy cập endpoint.
- Exposure và network policy giới hạn endpoint xuất hiện ở đâu.

Không nên chỉ dựa vào một regex tìm từ `password`, `secret` hoặc `token` vì dữ liệu nhạy cảm có thể nằm dưới key không có từ khóa dễ đoán. Ví dụ một internal URI có embedded credentials, một tên biến môi trường đặc thù hoặc một object có `toString()` chứa secret vẫn có thể tạo rủi ro.

**Chiến lược tốt nhất vẫn là không expose endpoint chứa dữ liệu quá nhạy cảm khi không cần**, thay vì cố gắng tạo một bộ lọc che mọi trường hợp.

## 7. Health endpoint: công bố trạng thái khác công bố chi tiết

`health` thường là endpoint mà load balancer, container orchestrator và hệ thống monitoring cần gọi. Nhưng những caller đó thường chỉ cần biết ứng dụng có sẵn sàng hay không, không cần tên database, connection details hoặc toàn bộ health contributors.

### 7.1. Mặc định không hiện details

Cấu hình:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

Trong Spring Boot 3.3, `show-details` mặc định là `never`. `show-components` cũng điều khiển mức hiển thị cấu trúc thành phần. Việc đặt tường minh giúp thể hiện chính sách công bố rõ ràng.

Một response đơn giản:

~~~json
{"status":"UP"}
~~~

### 7.2. Chỉ hiện details cho nhóm được phép

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Khi user không được authorized, endpoint không trả cùng mức details như user quản trị. Nếu cần điều khiển cả component list, cấu hình thêm `show-components` cho phù hợp.

Đừng nhầm `show-details=when-authorized` với việc tự động khóa URL health. Đó là một **chính sách response**, còn URL có thể vẫn cần được health checker truy cập không đăng nhập để đọc status.

### 7.3. always có nghĩa thật sự công bố chi tiết

~~~yaml
management:
  endpoint:
    health:
      show-details: always
~~~

Nếu `/actuator/health` có thể truy cập công khai, chi tiết health của dependency cũng có thể bị công bố. Chỉ dùng nếu các chi tiết đã được đánh giá an toàn và việc công bố có chủ đích.

### 7.4. Liveness và readiness

Với Spring Boot chạy trên môi trường hỗ trợ application availability/probes, có thể dùng các endpoint:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Đây là những endpoint hữu ích cho Kubernetes probe hoặc monitoring. Chúng phục vụ câu hỏi hẹp hơn so với toàn bộ health contributor tree.

Ví dụ cấu hình khi muốn chủ động bật probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Không nên gắn mọi dependency bên ngoài vào liveness khiến orchestrator restart ứng dụng chỉ vì một dependency tạm thời không sẵn sàng. Readiness và liveness cần phù hợp ý nghĩa vận hành của từng kiểm tra.

## 8. Thiết lập HTTP exposure theo allowlist

Một policy cho môi trường production có thể chỉ cần:

- `health` để probe.
- `info` nếu nội dung đã được chọn lọc.
- `prometheus` nếu hệ thống dùng Prometheus và có đường scrape an toàn.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
  endpoint:
    health:
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Trong ví dụ, `env` và `configprops` được đặt chế độ che giá trị, nhưng **chúng không được exposed qua HTTP** vì không có trong include list. Đây là thiết kế nhiều lớp, không phải lặp lại vô ích.

### 8.1. Vì sao không dùng exposure.include="*" rồi exclude vài endpoint?

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops,heapdump,shutdown"
~~~

Cấu hình này vẫn có thể công bố nhiều endpoint khác: `beans`, `mappings`, `conditions`, `loggers` hoặc một endpoint mới sau khi thêm dependency/nâng cấp framework.

Allowlist có lợi thế **fail closed**: những endpoint ngoài danh sách không tự xuất hiện qua HTTP chỉ vì một phiên bản mới bổ sung endpoint.

### 8.2. JMX cần policy riêng

HTTP allowlist không điều khiển JMX exposure. Nếu ứng dụng không có nhu cầu JMX monitoring, hãy áp một chính sách JMX riêng, ví dụ:

~~~properties
management.endpoints.jmx.exposure.include=health
~~~

Đừng mặc định security rules của Spring MVC hoặc WebFlux bảo vệ một JMX connector; đó là transport khác.

### 8.3. Không dùng base-path đổi tên làm biện pháp bảo mật

Thay:

~~~properties
management.endpoints.web.base-path=/management
~~~

chỉ đổi địa chỉ URL của endpoint, không thực hiện authorization. Một đường dẫn khó đoán không thay thế network isolation, authentication hoặc permission checks.

## 9. Spring Security bảo vệ Actuator như thế nào?

Spring Security có thể đưa ra quyết định dựa trên route matcher, principal và roles/authorities.

Với Spring MVC, Spring Boot cung cấp `EndpointRequest` để tạo matcher cho Actuator endpoints thay vì hard-code URL string. Điều này hữu ích khi ứng dụng thay đổi base path.

Nếu ứng dụng tự cấu hình một `SecurityFilterChain`, hãy chủ động định nghĩa rules cho cả Actuator và API nghiệp vụ. Cần nhớ rằng sự hiện diện của custom chain có thể khiến Actuator security auto-configuration của Boot nhường quyền kiểm soát.

### 9.1. Ví dụ hai filter chains tách biệt

Ví dụ Spring Security 6 / Spring Boot 3.3:

~~~java
package com.example.demo.security;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(requests -> requests
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
        );

        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(requests -> requests
                .anyRequest().authenticated()
        );

        http.httpBasic(withDefaults());
        return http.build();
    }
}
~~~

Đây là ví dụ về **authorization policy**, không phải cấu hình IAM/identity provider production đầy đủ. Trong hệ thống thật, bạn phải có cách xác thực người dùng hoặc service identity và ánh xạ quyền như `ROLE_ACTUATOR_ADMIN`. Cần cấu hình HTTPS/TLS và cơ chế quản lý credential phù hợp.

Ý nghĩa:

1. Chain có `@Order(1)` áp dụng cho Actuator endpoints.
2. `health` được phép gọi không cần đăng nhập vì health checker có thể cần status.
3. Các endpoint Actuator khác cần role `ACTUATOR_ADMIN`.
4. Chain `@Order(2)` xử lý các HTTP requests còn lại của ứng dụng, tránh vô tình bỏ trống bảo vệ API nghiệp vụ.

**Lưu ý:** Example cho phép health anonymous qua security nhưng exposure policy vẫn cần chứa `health`. Nó không tự bật `env`, `configprops` hay `loggers`.

### 9.2. Không cấu hình một chain chỉ cho Actuator rồi quên API

Một anti-pattern:

~~~java
@Bean
SecurityFilterChain actuatorOnly(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.toAnyEndpoint());
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Nếu đó là **chain duy nhất** mà ứng dụng cấu hình, các request ngoài Actuator matcher có thể không được bảo vệ bởi chain này, trong khi default application security đã nhường chỗ cho custom chain. Do đó cần một catch-all chain hoặc cấu hình bao phủ API tương ứng.

### 9.3. Role name và hasRole

`hasRole("ACTUATOR_ADMIN")` thường kiểm tra authority có tiền tố `ROLE_` theo mặc định của Spring Security. Nếu identity provider cung cấp authorities theo một convention khác, cần cấu hình mapping hoặc dùng `hasAuthority(...)` với tên thích hợp.

Không tự đoán rằng một JWT claim bất kỳ tên `role` sẽ được chuyển đúng thành GrantedAuthority; cần xác nhận việc mapping trong security configuration.

### 9.4. CSRF cho các thao tác ghi

Trong Spring Security sử dụng defaults, CSRF protection có thể khiến POST tới `/actuator/loggers` hoặc `/actuator/shutdown` trả 403 khi thiếu CSRF token, dù caller đã authenticated.

Không giải quyết bằng việc **tắt CSRF toàn cục một cách tùy tiện**. Với machine-to-machine clients, có thể dùng một security chain không dùng browser session và đặt CSRF policy phù hợp trong phạm vi hẹp, kết hợp authentication/authorization chắc chắn. Chỉ cho phép write operations nếu thực sự cần.

## 10. Exposure và authorization phải được kiểm soát cùng nhau

Một ví dụ sai mục đích:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Sau đó hy vọng rằng “Actuator mặc định được bảo vệ” là đủ. Rủi ro:

- Ứng dụng có thể đã định nghĩa custom `SecurityFilterChain` không bao trùm management URLs.
- Những endpoint mới có thể được công bố mà chưa có review.
- Authorization có thể quá rộng, ví dụ bất kỳ authenticated user nào cũng xem được diagnostics.
- Một số endpoint đọc có thể chứa thông tin nhạy cảm dù values được che.
- Access through reverse proxy/JMX hoặc management port có thể khác dự kiến.

Đúng hơn:

~~~text
Chỉ enable endpoint thật sự cần
    -> Chỉ expose qua transport cần dùng
        -> Chỉ route trên mạng cho phép
            -> Authenticate đúng identity
                -> Authorize theo vai trò và thao tác
                    -> Giới hạn details/values trả về
                        -> Audit, monitor và review định kỳ
~~~

Sự kết hợp các lớp kiểm soát làm giảm tác động nếu một lớp bị cấu hình sai.

## 11. Management port, interface và mạng nội bộ

Spring Boot cho phép đặt management HTTP endpoints trên port khác với port ứng dụng chính.

Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

Trong trường hợp này, application APIs có thể chạy ở port 8080, còn management endpoints ở port 9001. Khi management port khác, Boot có thể tạo management context riêng.

Tuy nhiên, **đổi port không phải một cơ chế authentication**. Nếu port 9001 mở ra mạng công khai, rủi ro vẫn tồn tại.

### 11.1. Bind loopback trong môi trường phù hợp

Nếu chỉ cần thao tác quản trị từ cùng máy, có thể xem xét:

~~~yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
~~~

Với Spring Boot, `management.server.address` được sử dụng phù hợp khi management port được cấu hình riêng với application port.

Một interface loopback có thể khiến remote scrape/probe từ bên ngoài host không truy cập được. Trong Kubernetes, kubelet thường gọi Pod IP chứ không phải localhost trong network namespace của container. Vì vậy không áp cấu hình loopback một cách máy móc cho deployment cần cluster probes.

### 11.2. Network policy và reverse proxy

Trong môi trường container hoặc cloud, có thể giới hạn bằng:

- Firewall/security group cho management port.
- Kubernetes NetworkPolicy và internal Service.
- API gateway/reverse proxy rules chặn `/actuator/**` khỏi public ingress.
- Service identity hoặc mTLS cho nội bộ.
- RBAC/authorization cho từng endpoint.
- IP allowlist nếu thật sự phù hợp topology và có cách quản lý đáng tin cậy.

Network isolation quan trọng nhưng không nên là lớp bảo vệ duy nhất cho endpoint chứa dữ liệu rất nhạy cảm.

### 11.3. Tách management port vẫn cần kiểm tra chính sách security

Nếu dùng management context khác, cần xác nhận các `SecurityFilterChain`, authentication và request matchers đang hoạt động đúng trên management port của phiên bản/configuration thực tế.

Đừng mặc định một filter chain cấu hình cho main web context luôn bao phủ chính xác mọi request trên management context trong tất cả cách triển khai. Kiểm tra bằng integration test hoặc smoke test trên **đúng port được expose**.

## 12. Heapdump và threaddump: nguy cơ khác nhau

`threaddump` có thể tiết lộ tên thread, stack traces và implementation details. `heapdump` nhạy cảm hơn vì dump có thể chứa object trong heap, bao gồm dữ liệu request, cache, credential hoặc token đang nằm trong bộ nhớ.

### 12.1. Không mở heapdump qua public network

Một endpoint download heap dump không phù hợp với public ingress. Khi phải lấy heap dump để xử lý sự cố:

1. Có quy trình phê duyệt và giới hạn người thực hiện.
2. Thu thập qua môi trường điều tra an toàn.
3. Tránh chụp/truyền heap dump nếu không cần thiết.
4. Mã hóa khi lưu và truyền.
5. Giới hạn retention và xóa khi hoàn tất.
6. Theo dõi quyền truy cập và audit hoạt động tải dữ liệu.

Tài khoản có quyền xem health **không** nên đồng thời mặc định có quyền tải heap dump.

### 12.2. Thread dumps cũng có thể lộ chi tiết

Thread dump có thể không chứa toàn bộ heap, nhưng stack traces và thread names vẫn có thể cho biết implementation classes, job names, queue names hoặc metadata hệ thống. Hãy đánh giá nó như một endpoint chẩn đoán nội bộ.

## 13. Loggers và logfile: quan sát nhưng cũng có thể lộ dữ liệu

`/actuator/loggers` cho phép xem configured/effective log levels, và trong các cấu hình phù hợp có thể thay đổi level khi ứng dụng đang chạy.

Ví dụ:

~~~http
GET /actuator/loggers/com.example.payment.PaymentService
~~~

Response minh họa:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
~~~

Để thay đổi level:

~~~http
POST /actuator/loggers/com.example.payment.PaymentService
Content-Type: application/json

{"configuredLevel":"DEBUG"}
~~~

Một người có quyền đổi log level có thể làm ứng dụng ghi nhiều thông tin chi tiết hơn. Nếu code log token, request payload hoặc object nhạy cảm ở DEBUG/TRACE, rủi ro lộ dữ liệu tăng lên.

### 13.1. Chính sách phù hợp với loggers

- Không expose cho internet công khai.
- Chỉ cấp quyền thay đổi cho role quản trị cụ thể.
- Có audit ai đổi logger nào, khi nào và vì sao.
- Giới hạn thời gian bật DEBUG/TRACE.
- Khôi phục level sau khi chẩn đoán.
- Giảm nguy cơ log chứa secrets ngay từ code.
- Tránh bật root TRACE trong production.

### 13.2. Logfile có thể mang dữ liệu cá nhân

Nếu `logfile` được expose, một caller có thể tải nội dung file log do ứng dụng cấu hình. Log có thể chứa headers, user IDs, error descriptions hoặc dữ liệu do developer vô tình ghi.

Không nên coi file log là dữ liệu đã được sanitization giống `env`. Cần có logging policy riêng: redact/mask ở nguồn, role-based access, retention và kiểm soát tải dữ liệu.

### 13.3. Chỉ bật thêm log không sửa được mọi lỗi

Logging level quyết định event nào được ghi, không tạo ra log statement chưa tồn tại. Khi điều tra lỗi nên dùng metrics/traces/logging phù hợp thay vì bật tất cả endpoint và TRACE mọi nơi.

## 14. Metrics, Prometheus và rủi ro ở nhãn

Metrics thường được xem là dữ liệu tổng hợp, nhưng tag/label có thể chứa thông tin nhạy cảm nếu developer tạo meter sai cách.

Ví dụ **không nên** dùng các giá trị động không kiểm soát làm tag:

~~~java
registry.counter(
        "payment.requests",
        "email", customerEmail,
        "token", accessToken
).increment();
~~~

Vấn đề:

- `email` và `token` có thể lộ dữ liệu nhận dạng/credential.
- Mỗi giá trị mới có thể tạo time series mới, tăng cardinality.
- Hệ thống monitoring và những người xem metrics có thể lưu được các label đó trong thời gian dài.

Thay bằng tag ít giá trị, không nhạy cảm:

~~~java
registry.counter(
        "payment.requests",
        "outcome", "success",
        "method", "card"
).increment();
~~~

Các label `outcome` hoặc `method` trong ví dụ được lấy từ tập giá trị nhỏ, đã được định nghĩa và không chứa thông tin cá nhân.

### 14.1. Scrape không cần đồng nghĩa anonymous

Một Prometheus scraper có thể được cấp service identity phù hợp và chỉ được phép truy cập `/actuator/prometheus`. NetworkPolicy và authentication có thể bảo đảm không phải mọi client đều scrape được metrics.

Không phải mọi monitoring server hỗ trợ cùng một cơ chế auth, vì vậy cần điều chỉnh theo topology thật của hệ thống.

### 14.2. Custom HealthIndicator cũng có thể lộ dữ liệu

Một `HealthIndicator` tự viết không nên trả trực tiếp connection string có password, raw SQL exception với dữ liệu nhạy cảm hoặc toàn bộ remote response.

Kể cả khi details bị giới hạn, hãy thiết kế health data theo nguyên tắc chỉ đưa ra điều cần thiết cho quyết định sức khỏe của component.

## 15. Endpoint info: đừng coi metadata luôn vô hại

`info` có thể cung cấp build version, commit ID, application name hoặc metadata tùy chỉnh. Những thông tin đó hữu ích cho release debugging, nhưng có thể giúp người ngoài suy ra:

- Version/framework hiện tại.
- Internal environment name.
- Build timestamp.
- Source revision.
- Tên tổ chức/module nội bộ.

Policy có thể công bố một số trường (ví dụ version release dạng public) nhưng không công bố commit hash/internal repository URL nếu không cần.

Ví dụ cấu hình metadata có chủ đích:

~~~yaml
info:
  app:
    name: public-catalog-api
    version: "1.2.0"
~~~

Cần review những gì thực tế được expose qua `info` theo cấu hình InfoContributor và environment. Không đặt API key trong nhóm `info` với suy nghĩ Actuator sẽ tự che mọi trường tùy ý.

## 16. Httpexchanges, custom endpoints và dữ liệu trả về

`httpexchanges` yêu cầu một `HttpExchangeRepository` phù hợp và có thể cung cấp thông tin về các HTTP exchanges được ghi nhận. Nó hữu ích để chẩn đoán request nhưng cần cân nhắc URL, status, headers và những dữ liệu mà repository lưu.

Một số header như `Authorization` hoặc `Cookie` đặc biệt nhạy cảm. Khi cấu hình HTTP exchange recording, chỉ giữ thông tin cần thiết và tránh thu thập/bộc lộ credentials.

### 16.1. Custom @Endpoint phải tự chịu trách nhiệm về dữ liệu

Ví dụ một endpoint tùy chỉnh:

~~~java
import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "deployment")
public class DeploymentEndpoint {

    @ReadOperation
    public Map<String, String> current() {
        return Map.of(
                "state", "ready",
                "region", "apac"
        );
    }
}
~~~

Đây là một endpoint đọc đơn giản. Nhưng nếu method trả:

~~~java
return Map.of(
        "dbPassword", databasePassword,
        "apiKey", apiKey
);
~~~

thì bạn đã tự đưa sensitive values vào response. Không nên giả định mọi custom endpoint đều được che bằng cùng cơ chế `env`/`configprops`.

Tốt hơn là **không đưa secrets vào response ngay từ đầu**. Nếu không cần công bố endpoint cho hệ thống bên ngoài, không include ID `deployment` vào web exposure.

### 16.2. Endpoint trả về object cũng có thể rò rỉ qua serialization

Một object response có thể vô tình chứa field mới khi class thay đổi. Dùng DTO dành riêng cho việc công bố dữ liệu vận hành với những field được cho phép, thay vì trả trực tiếp `Environment`, `DataSourceProperties` hoặc một domain object lớn.

## 17. Cấu hình mẫu: production theo hướng hạn chế tối đa

Ví dụ Spring Boot 3.3 với policy tập trung vào health/info và Prometheus trong mạng kiểm soát:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
    jmx:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
    quartz:
      show-values: never

info:
  app:
    name: example-service
    version: "1.0.0"
~~~

Đây là **mẫu chính sách exposure**. Nó chưa bao gồm authentication, firewall hoặc ingress configuration của deployment. Nếu `prometheus` được exposed trên main HTTP port, cần thêm security/network policy để chỉ hệ thống scrape phù hợp truy cập.

### 17.1. Mẫu private management port

Nếu môi trường hỗ trợ một management port riêng và internal scrape:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: never
~~~

Đi kèm cần có network policy không expose 9001 ra public ingress và security rules thích hợp. Chỉ thay port không bảo đảm an toàn.

### 17.2. Mẫu khi thật sự cần env/configprops để chẩn đoán

Chỉ dùng ở môi trường có kiểm soát:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Ngay cả với values bị che, nên yêu cầu authenticated admin cho `env` và `configprops` vì tên property, nguồn config và cấu trúc bean có thể tiết lộ topology.

Nếu bắt buộc xem raw values cho một tác vụ chẩn đoán đặc biệt, cân nhắc phương án ít rủi ro hơn: một lệnh nội bộ truy vấn đúng key, một diagnostics endpoint được kiểm soát chặt, hoặc tạm thời dùng `when-authorized` với role rõ ràng, audit và kiểm soát thời gian.

## 18. Chính sách theo môi trường: local, staging, production

Không nhất thiết mọi môi trường có cùng danh sách endpoint.

| Môi trường | Mức exposure gợi ý | Điều kiện quan trọng |
| --- | --- | --- |
| Local dev | Health, info, và chẩn đoán cần thiết | Không dùng dữ liệu production thật |
| Test/CI | Theo mục đích test; có thể bật env/configprops đã che | Cô lập, credential giả lập, không mở public |
| Staging | Gần production, mở thêm có thời hạn nếu cần | Auth và network policy như production |
| Production | Health, info đã review, metrics cho scraper | Least privilege, audit, retention, TLS |

### 18.1. Profile-specific configuration

Cấu hình cơ sở:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

`application-dev.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops,loggers"
~~~

Khi profile `dev` được bật, danh sách exposure thay đổi theo property-source precedence. Nhưng phải bảo đảm profile `dev` không vô tình được kích hoạt trong production.

### 18.2. Không dùng profile làm lớp bảo mật duy nhất

Nếu production bị cấu hình nhầm `spring.profiles.active=dev`, endpoints dev có thể được mở. Vì vậy vẫn cần network/security controls độc lập, và automated checks xác nhận runtime exposure thực tế.

## 19. Những yếu tố cần cân nhắc khi thiết kế chính sách công bố

Trước khi expose một endpoint, hãy trả lời các câu hỏi:

1. **Mục đích**: ai cần endpoint này và để ra quyết định gì?
2. **Dữ liệu**: endpoint trả status, metadata, user data, secrets hay heap contents?
3. **Quyền**: caller được đọc, thay đổi, xóa hay shutdown?
4. **Transport**: HTTP, JMX hoặc cả hai?
5. **Mạng**: public internet, cluster internal hay localhost?
6. **Identity**: human admin hay service account? Authentication có phù hợp không?
7. **Response policy**: cần details/values thô hay chỉ sanitized status?
8. **Thời hạn**: endpoint cần mở liên tục hay chỉ khi điều tra?
9. **Audit**: có biết ai truy cập/đổi level/tải dump không?
10. **Review**: khi nâng cấp Boot hoặc thêm dependency, exposure có được đánh giá lại không?

Một chính sách thực tế nên được biểu diễn trong source-controlled configuration, infrastructure-as-code và security tests, thay vì chỉ là quy ước miệng.

### 19.1. Least privilege cho service-to-service observability

Một Prometheus scraper thường chỉ cần `prometheus`. Một Kubernetes health probe chỉ cần health/probe endpoint. Một log collector không cần khả năng thay đổi log level qua `loggers`.

Dùng các service identities khác nhau hoặc network controls tương ứng khi có thể, thay vì cấp một admin credential dùng chung cho mọi tool vận hành.

### 19.2. Thông tin có thể tồn tại ngoài endpoint

Ngay cả khi đã tắt endpoint, dữ liệu nhạy cảm có thể còn ở:

- Logs đã gửi tới hệ thống tập trung.
- Traces chứa attributes.
- Metrics time series với labels không an toàn.
- Crash/heap dump được tạo bằng tool khác.
- CI/CD logs hoặc environment dump.
- Trình quản lý configuration/secret backend.

Chính sách Actuator là một phần của **chính sách observability data**, không phải giải pháp thay thế cho quản lý secret và data retention tổng thể.

## 20. Kiểm thử exposure và authorization

Một policy nên có automated tests xác nhận endpoint nào có thể truy cập dưới danh tính nào.

### 20.1. Test health public, env không exposed

Với Spring Boot MVC, có thể dùng MockMvc trong một integration test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,info",
        "management.endpoint.env.enabled=true"
})
@AutoConfigureMockMvc
class ActuatorExposureTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void healthIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void envIsNotExposedOverHttp() throws Exception {
        mvc.perform(get("/actuator/env"))
                .andExpect(status().isNotFound());
    }
}
~~~

Ví dụ này giả định endpoint Actuator và security/test setup của ứng dụng phù hợp, chẳng hạn health được permitAll và management chạy **cùng server port**. Nếu management port riêng, MockMvc gắn main context có thể không quan sát đúng management context; lúc đó dùng integration test trên port thật hoặc một cách kiểm thử management context tương ứng.

Kết quả `404` có thể khác nếu ứng dụng có routing/security/filter đặc biệt. Khi kiểm thử quyền, điều quan trọng là endpoint không trả dữ liệu cho caller không được phép, và test cũng phải xác nhận endpoint thật sự tồn tại cho người dùng được quyền nếu đó là yêu cầu.

### 20.2. Test role-based security với Spring Security Test

Nếu dùng Spring Security và mẫu chain trước đó, có thể dùng `@WithMockUser` để mô phỏng authorities trong một web security integration test.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

class ActuatorAuthorizationExample {

    // Test class cần cấu hình @SpringBootTest / @AutoConfigureMockMvc
    // cùng một MockMvc đã inject, và có endpoint thích hợp được expose.

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void adminCanReadProtectedEndpoint() throws Exception {
        // mvc.perform(get("/actuator/info")).andExpect(status().isOk());
    }
}
~~~

Đây là skeleton minh họa; với test thực, bổ sung test context, bean injection và assertion có thể chạy được. Cần dependency `spring-security-test` thích hợp (thường do cấu hình test starter/security test của dự án quyết định).

### 20.3. Đừng chỉ test tình huống được phép

Một policy kiểm soát thông tin nên có cả negative tests:

- Anonymous caller không đọc được `env`, `configprops`.
- User bình thường không được đổi `loggers`.
- Không có route tải `heapdump` từ public listener.
- Health probe chỉ nhận status, không nhận raw connection details.
- Credentials hoặc marker giả lập không xuất hiện nguyên văn trong response.
- Request trên đúng management port và qua ingress/public route có chính sách khác nhau theo thiết kế.

Nếu test chỉ xác nhận admin đọc được endpoint, bạn chưa chứng minh user khác bị chặn.

### 20.4. Test sanitization bằng secret giả lập

Trong test environment, đặt một marker **giả**, không dùng credential production:

~~~properties
app.demo.fake-secret=FAKE_SECRET_DO_NOT_USE
management.endpoints.web.exposure.include=health,env
management.endpoint.env.show-values=never
~~~

Khi endpoint được truy cập bởi caller có quyền, xác nhận value marker không xuất hiện nguyên văn ở response. Test kiểu này giúp phát hiện việc ai đó vô tình chuyển `show-values` từ `never` sang `always`.

Khi làm test thực tế, không in secret thật vào output nếu assertion thất bại.

## 21. Một ví dụ rủi ro: custom SecurityFilterChain mở tất cả

Giả sử team có một chain:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().permitAll()
    );
    return http.build();
}
~~~

Nếu cùng lúc cấu hình:

~~~properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
~~~

thì bạn có thể đã mở rất nhiều Actuator endpoints qua HTTP **và** cho phép anonymous caller truy cập; `env` có thể hiển thị raw values. Đây là một kiểu cấu hình có rủi ro rất cao.

Một số endpoint có điều kiện dependency, enablement hoặc request method riêng, nhưng không nên dựa vào chúng để giảm rủi ro chung.

Cách xử lý là:

1. Thu hẹp `exposure.include` thành allowlist.
2. Giữ `show-values=never` cho endpoints chứa cấu hình.
3. Định nghĩa chain rõ ràng cho Actuator và app APIs.
4. Áp network isolation.
5. Kiểm thử với anonymous/unauthorized callers.
6. Review logs, metrics và custom endpoints để giảm dữ liệu nhạy cảm.

## 22. Tình huống vận hành điển hình

### 22.1. SRE cần kiểm tra một config sai

**Không nhất thiết phải bật `env.show-values=always`.**

Một trình tự ít rủi ro hơn:

- Kiểm tra deployment/config source metadata.
- Dùng log an toàn để biết property có được bind hoặc profile có active hay không.
- Nếu cần Actuator, chỉ expose `env` cho mạng/quyền phù hợp và vẫn che value.
- Nếu cần một giá trị cụ thể, sử dụng kênh nội bộ có quyền và audit, thay vì công bố toàn bộ Environment.
- Sau khi chẩn đoán, thu hồi quyền/đóng endpoint nếu chỉ mở tạm.

### 22.2. Monitoring cần Prometheus

Chỉ expose `prometheus` và `health` nếu đó là yêu cầu; dùng service identity hoặc internal network. Kiểm tra metrics tags không chứa email, user ID hay token.

### 22.3. Incident cần heap dump

Không bật `heapdump` ra public ingress. Thu thập trên một kênh hạn chế, bảo vệ file dump bằng encryption/access controls và xóa theo retention.

### 22.4. Operator muốn bật DEBUG

Nếu dùng `loggers`, cần authenticated admin, audit, thời gian giới hạn, và kế hoạch khôi phục level. Không cấp cùng quyền đó cho health checker.

### 22.5. Public status page cần tình trạng hệ thống

Một public status page thường chỉ cần trạng thái tổng quát hoặc dữ liệu đã được tổng hợp. Không expose nguyên cây health contributors hoặc dependency exceptions chỉ để hiển thị chữ “UP”.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `/actuator/env` trả 404 | Endpoint không exposed hoặc disabled | Kiểm tra enabled và web exposure riêng |
| `/actuator/health` trả UP nhưng không có details | Mặc định `show-details=never` | Chỉ bật details cho role nếu cần |
| `env` trả `******` | Sanitization mặc định | Đây là hành vi bảo vệ; đừng vội bật always |
| `when-authorized` lộ raw values cho quá nhiều user | Chưa giới hạn `roles` | Đặt role rõ ràng và kiểm tra HTTP security |
| Endpoint bị 401 | Chưa authenticated | Dùng identity được phép và kiểm tra auth config |
| Endpoint bị 403 | Không đủ quyền hoặc CSRF với write request | Kiểm tra authorities và CSRF policy |
| Custom filter chain làm mất bảo vệ Actuator | Default security backing off | Định nghĩa chain cho Actuator và app |
| Mở `/actuator/**` qua ingress | Reverse proxy route quá rộng | Chặn public route và dùng internal management service |
| Prometheus scrape không được | Endpoint thiếu dependency, không exposed hoặc network policy chặn | Kiểm tra registry/exposure/network |
| Heap dump vô tình có thể tải công khai | Include wildcard và authorization rộng | Tắt exposure, giới hạn quyền, kiểm tra bản ghi truy cập |
| Thông tin vẫn lộ dù env bị che | Log, metrics, info, custom endpoint khác | Review toàn bộ observability data surface |
| Đổi management port nhưng vẫn bị truy cập ngoài | Port riêng vẫn được route công khai | Thêm firewall/network policy và auth |
| Kubernetes readiness probe fail sau bind localhost | Kubelet không tới được loopback listener | Cấu hình Pod networking và probe theo topology |
| Actuator URL thay đổi | Đã sửa base path hoặc management port | Kiểm tra route và EndpointRequest matcher |
| JMX có access khác HTTP | JMX không đi qua Spring web filters | Cấu hình JMX transport và authentication riêng |

### 23.1. Quy trình điều tra an toàn

Khi một endpoint không hoạt động hoặc có vẻ lộ dữ liệu:

1. Xác định Spring Boot version và Actuator dependencies đang dùng.
2. Xác định endpoint có enabled và exposed qua transport mong muốn không.
3. Xác định management port/base path thực tế.
4. Kiểm tra reverse proxy/ingress/network policy.
5. Kiểm tra identity, role/authority mapping và SecurityFilterChain matchers.
6. Kiểm tra `show-details`, `show-components` hoặc `show-values`.
7. Quan sát response bằng tài khoản test được phép, **không log raw secrets**.
8. Kiểm tra trường hợp anonymous và user không có quyền.
9. Đánh giá custom endpoint, metric labels và dữ liệu log liên quan.
10. Sửa policy và thêm regression test để lỗi không tái diễn.

## 24. Bài tập thực hành

### Bài tập 1 — Enabled khác exposed

Tạo ứng dụng Spring Boot có Actuator. Bật `env` bằng `management.endpoint.env.enabled=true` nhưng chỉ expose `health,info`. Gọi `/actuator/env` và giải thích vì sao endpoint không được truy cập qua HTTP.

### Bài tập 2 — Allowlist và wildcard

So sánh hai cấu hình:

~~~properties
management.endpoints.web.exposure.include=health,info
~~~

và:

~~~properties
management.endpoints.web.exposure.include=*
~~~

Liệt kê các endpoint có thể xuất hiện thêm ở cấu hình thứ hai và phân tích rủi ro, không chỉ khác biệt về số lượng URL.

### Bài tập 3 — Sanitization

Thêm một property có marker giả trong `application.yml`. Expose `env` chỉ ở môi trường test và đặt `show-values=never`. Quan sát value bị che; sau đó giải thích vì sao property name/origin vẫn cần giới hạn truy cập.

### Bài tập 4 — when-authorized

Đặt `management.endpoint.env.show-values=when-authorized` và role `ACTUATOR_ADMIN`. Viết security tests với anonymous user, authenticated user thường và admin. Xác nhận raw marker giả chỉ được xem trong điều kiện chủ đích.

### Bài tập 5 — Health details

Đặt `health.show-details=never`, gọi health endpoint và ghi nhận response. Sau đó thay bằng `when-authorized` với role phù hợp. So sánh khả năng health checker đọc status và khả năng admin đọc details.

### Bài tập 6 — Hai SecurityFilterChain

Tạo chain riêng cho Actuator và chain cho application APIs. Bảo đảm health được phép anonymous, admin được đọc endpoint chẩn đoán, còn các API nghiệp vụ không vô tình chuyển thành public.

### Bài tập 7 — Management port

Đặt `management.server.port` khác `server.port`. Kiểm tra đường truy cập và security trên hai port. Nếu dùng Docker/Kubernetes, giải thích vì sao binding `127.0.0.1` có thể làm scrape/probe từ bên ngoài container không thành công.

### Bài tập 8 — Loggers endpoint

Trong môi trường test cô lập, expose `loggers` chỉ cho admin. Kiểm tra GET và POST. Giải thích ảnh hưởng của CSRF, authentication và khả năng thay đổi DEBUG/TRACE đối với bảo mật dữ liệu.

### Bài tập 9 — Metric label review

Tạo một counter theo `outcome` và một counter theo `customerEmail`. Đánh giá nguy cơ lộ dữ liệu và cardinality; thiết kế lại metric thứ hai để không chứa thông tin cá nhân.

### Bài tập 10 — Incident response

Giả sử cần heap dump để điều tra memory leak trong production. Viết quy trình yêu cầu quyền, thu thập an toàn, mã hóa, lưu trữ, audit và xóa dump; giải thích vì sao không dùng `exposure.include=*`.

### Bài tập 11 — Policy review

Tạo bảng policy cho `health`, `info`, `metrics`, `prometheus`, `env`, `configprops`, `loggers` và `heapdump`: ai cần, endpoint có được expose không, qua transport nào và có cần role riêng không.

### Bài tập 12 — Security regression test

Tạo test xác nhận anonymous caller không đọc được `env` và admin không thể tải `heapdump` qua public listener vì endpoint không được exposed. Dùng marker giả để kiểm tra cấu hình che values mà không đưa secrets thật vào test.

## 25. Tài liệu tham khảo

- [Spring Boot 3.3 — Actuator Endpoints, Exposure, Security và Sanitization](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

## 26. Ghi nhớ

Spring Boot Actuator phục vụ observability nhưng **không phải mọi endpoint đều thích hợp để công bố**. Trong Spring Boot 3.3, mặc định chỉ `health` được exposed qua HTTP/JMX; việc một endpoint được enabled không đồng nghĩa nó đã có URL truy cập.

Cần phân biệt bốn lớp: **enablement**, **exposure**, **authentication/authorization** và **response disclosure**. `env`, `configprops`, `quartz` mặc định che values; `show-values=when-authorized` cần roles phù hợp và không thay thế HTTP security. `health.show-details` mặc định `never`; health checker thường chỉ cần trạng thái tổng quát.

Chính sách thực tế nên dùng allowlist thay vì `include="*"`, giới hạn management port/network, bảo vệ Actuator bằng Spring Security và xác nhận custom `SecurityFilterChain` không làm hở API khác. `heapdump`, `logfile`, `loggers` và metric labels cần mức kiểm soát khác nhau vì có thể chứa dữ liệu nhạy cảm hoặc thay đổi hành vi runtime.

Một endpoint chỉ được phép công bố khi bạn có câu trả lời rõ ràng cho **ai cần nó, họ cần thấy dữ liệu gì, qua đường mạng nào, với quyền gì và trong thời gian bao lâu**. Hãy bổ sung negative security tests và định kỳ review exposure mỗi khi đổi profile, dependency, Spring Boot version hoặc topology triển khai.
