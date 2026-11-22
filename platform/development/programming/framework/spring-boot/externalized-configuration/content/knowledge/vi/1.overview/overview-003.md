# Bản đồ khái niệm: thuộc tính, nguồn cấu hình, Environment, profile và liên kết kiểu

Trong Spring Boot, *externalized configuration* là cách đưa các giá trị có thể thay đổi theo môi trường chạy ra khỏi mã Java: URL dịch vụ, cổng HTTP, thời gian chờ, giới hạn kết nối, cờ tính năng và các thiết lập vận hành. Mục tiêu của bài này là nhìn thấy **đường đi của một giá trị cấu hình** từ nơi khai báo đến lúc ứng dụng sử dụng nó, đồng thời phân biệt rõ năm khái niệm thường bị trộn lẫn: *property*, *property source*, *Environment*, *profile* và *type-safe binding*.

## 1. Bản đồ tổng thể

~~~mermaid
flowchart LR
    A["Nguồn cấu hình<br/>application.yml, biến môi trường,<br/>system properties, command-line..."] --> B["PropertySources<br/>có thứ tự ưu tiên"]
    P["Profile đang active<br/>dev, test, prod..."] --> C["Config Data<br/>chọn tài liệu cấu hình phù hợp"]
    C --> B
    B --> E["Spring Environment<br/>tra cứu key và giá trị hiệu lực"]
    E --> V["Environment.getProperty()<br/>@Value"]
    E --> D["Spring Boot Binder<br/>@ConfigurationProperties"]
    D --> O["Đối tượng Java có kiểu<br/>Duration, URI, boolean..."]
    V --> U["Bean / logic ứng dụng"]
    O --> U
~~~

Có thể đọc sơ đồ bằng một câu: **nhiều nguồn cung cấp cùng một tên thuộc tính; profile tham gia quyết định dữ liệu cấu hình nào được nạp; Environment cung cấp giá trị hiệu lực; ứng dụng đọc trực tiếp hoặc bind thành đối tượng có kiểu**.

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| Property (thuộc tính) | Thiết lập có tên là gì? | `app.client.connect-timeout` |
| Property source (nguồn) | Giá trị được khai báo ở đâu? | `application.yml`, biến môi trường, `--app.client.connect-timeout=1s` |
| Environment | Với trạng thái khởi động hiện tại, tra key sẽ ra giá trị nào? | `environment.getProperty("app.client.connect-timeout")` |
| Profile | Cấu hình/bean nào được kích hoạt cho ngữ cảnh chạy này? | `dev`, `prod` |
| Binding | Chuyển các key chuỗi sang mô hình Java như thế nào? | `@ConfigurationProperties` → `ClientProperties` |

Một *property* không đồng nghĩa với một dòng YAML: cùng một key có thể xuất hiện trong nhiều nguồn. Một *profile* cũng không phải là kho lưu trữ cấu hình độc lập: nó giúp chọn tài liệu cấu hình và bean theo ngữ cảnh chạy.

## 2. Property là tên logic; property source là nơi chứa giá trị

Ví dụ một nhóm thiết lập cho HTTP client:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

Các key logic tương ứng là `app.client.base-url`, `app.client.connect-timeout` và `app.client.max-retries`. Chúng diễn tả *ý nghĩa* của cấu hình, không ràng buộc ứng dụng phải lấy giá trị từ tệp YAML. Cùng key có thể được khai báo bởi một nguồn khác:

~~~bash
java -jar demo.jar --app.client.connect-timeout=200ms
~~~

Spring Boot tập hợp các `PropertySource` thành thứ tự tra cứu. Khi nhiều nguồn có cùng key, **nguồn có độ ưu tiên cao hơn quyết định giá trị hiệu lực**. Trong cách chạy thông thường, tham số command-line `--key=value` có thể ghi đè cấu hình từ `application.yml`. Tuy nhiên, đừng cố suy ra toàn bộ thứ tự ưu tiên từ vị trí tệp: cấu hình ngoài ứng dụng, `spring.config.import`, test properties và cách khởi động cũng có thể tác động đến kết quả.

Một số nhóm nguồn thường gặp:

- **Config Data:** `application.properties`, `application.yml`, tài liệu theo profile, tệp bên ngoài hoặc tài liệu được import.
- **Biến môi trường hệ điều hành:** phù hợp cho cấu hình triển khai, container và CI/CD.
- **Java system properties:** ví dụ `-Dapp.client.max-retries=4`.
- **Command-line arguments:** ví dụ `--app.client.max-retries=5`.
- **Nguồn do ứng dụng/test bổ sung:** phục vụ cấu hình động hoặc cô lập tình huống kiểm thử.

Đối với biến môi trường dùng trong relaxed binding, tên canonical như `app.client.max-retries` có dạng thường dùng `APP_CLIENT_MAXRETRIES`: thay dấu chấm bằng `_`, bỏ dấu gạch ngang rồi viết hoa. Không nên tự đoán rằng mọi cách chèn dấu gạch dưới đều tương đương.

## 3. Environment: nơi tra cứu giá trị hiệu lực

Spring Framework cung cấp `org.springframework.core.env.Environment`. Spring Boot chuẩn bị `Environment` từ các nguồn cấu hình trong quá trình khởi động. Đối với mã ứng dụng, đây là một điểm truy cập thống nhất: không cần biết giá trị cuối cùng đến từ YAML, biến môi trường hay command-line.

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientSettingsReader {
    private final Environment environment;

    public ClientSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public void printNonSensitiveSettings() {
        String url = environment.getProperty("app.client.base-url");
        Duration timeout = environment.getProperty(
            "app.client.connect-timeout", Duration.class);
        String[] profiles = environment.getActiveProfiles();

        System.out.println("URL = " + url);
        System.out.println("Timeout = " + timeout);
        System.out.println("Active profile count = " + profiles.length);
    }
}
~~~

Điểm cần nhớ:

1. `getProperty(key)` đọc một thuộc tính ở dạng chuỗi; `getProperty(key, Type.class)` yêu cầu chuyển đổi sang kiểu đích khi có converter phù hợp.
2. Một key không tồn tại có thể cho kết quả `null`; biến thể có giá trị mặc định hoặc `getRequiredProperty` giúp biểu đạt kỳ vọng rõ hơn.
3. `getActiveProfiles()` cho biết profile đang kích hoạt; nó không cho biết giá trị của một key đến từ file nào.
4. `Environment` là bức tranh cấu hình của ứng dụng đang chạy. Việc sửa tệp cấu hình trên đĩa sau khi ứng dụng đã khởi động **không mặc nhiên làm các bean được bind lại**; cơ chế reload động cần được thiết kế riêng nếu ứng dụng thật sự cần.

Có thể hiểu `Environment` như câu trả lời cho câu hỏi **“giá trị hiện có là gì?”**. Để hỏi **“nó sẽ trở thành kiểu Java nào và có hợp lệ không?”**, ta cần tầng binding.

## 4. Profile điều khiển ngữ cảnh nạp cấu hình và lựa chọn bean

Giả sử có hai tệp:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8081
    connect-timeout: 1s
~~~

Khi chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=dev
~~~

Spring Boot có thể nạp cả cấu hình cơ sở và dữ liệu đặc thù cho profile `dev`. Trong ví dụ này, `app.client.base-url` và `app.client.connect-timeout` nhận giá trị từ cấu hình `dev`, còn `app.client.max-retries` tiếp tục lấy giá trị cơ sở là `2`. Đây là **ghi đè từng property**, không phải thay toàn bộ đối tượng `app.client`.

Ngoài tệp `application-dev.yml`, một tài liệu YAML có điều kiện cũng có thể được kích hoạt như sau:

~~~yaml
# Một tài liệu YAML bổ sung trong application.yml
spring:
  config:
    activate:
      on-profile: dev
app:
  client:
    connect-timeout: 1s
~~~

Tài liệu trên chỉ có hiệu lực khi điều kiện profile phù hợp. Không đặt `spring.profiles.active` trong một tài liệu vốn đã bị ràng buộc bằng `spring.config.activate.on-profile`; việc quyết định profile active phải đến từ nguồn được phép dùng cho kích hoạt.

Phân biệt hai vai trò của profile:

- **Profile đối với Config Data:** chọn tệp hoặc tài liệu cấu hình theo môi trường.
- **Profile đối với bean:** `@Profile("dev")` trên cấu hình/bean quyết định bean đó có được đăng ký hay không.

Một bean `@Profile("dev")` không tự động làm mọi key trong `Environment` chuyển sang “nguồn dev”. Ngược lại, có `application-dev.yml` cũng không tự động tạo hay thay bean trừ khi phần cấu hình hoặc điều kiện bean liên quan yêu cầu.

Khi không có profile active được chỉ định, Spring có cơ chế profile mặc định. Vì vậy hãy kiểm tra profile thực tế khi chẩn đoán cấu hình, thay vì giả định luôn có `dev` hoặc `prod`.

## 5. Luồng lựa chọn giá trị: ba lớp ghi đè trong một ví dụ

Giữ các tệp ở mục trước và giả sử chạy trong môi trường có biến `APP_CLIENT_CONNECTTIMEOUT=750ms`, sau đó truyền thêm đối số:

~~~bash
java -jar demo.jar --spring.profiles.active=dev --app.client.connect-timeout=200ms
~~~

| Nguồn | Giá trị `app.client.connect-timeout` | Vai trò |
| --- | --- | --- |
| `application.yml` | `3s` | Cơ sở |
| `application-dev.yml` | `1s` | Ghi đè cơ sở khi `dev` active |
| Biến môi trường | `750ms` | Ghi đè dữ liệu config trong tình huống này |
| Command-line | `200ms` | Giá trị hiệu lực cuối trong tình huống này |

Kết quả: khi bean cần `app.client.connect-timeout`, nó nhận **200 ms**. Nếu bỏ đối số command-line, kết quả trong ví dụ sẽ là **750 ms**. Nếu bỏ tiếp biến môi trường, kết quả sẽ là **1 s** khi `dev` còn active.

Bài học chính là profile chỉ giải quyết **tài liệu nào được xét**; chính thứ tự nguồn mới giải quyết **giá trị nào thắng** khi có xung đột. Với cấu hình import, vị trí ngoài ứng dụng hoặc quy tắc dành cho test, hãy kiểm tra precedence cụ thể thay vì thuộc lòng một danh sách rút gọn.

## 6. Type-safe binding: từ nhóm key sang đối tượng Java

Khi nhiều thiết lập thuộc cùng một chức năng, `@ConfigurationProperties` cho phép khai báo prefix một lần và để Spring Boot Binder tạo đối tượng Java có kiểu cụ thể:

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

Đăng ký cho component scan của ứng dụng:

~~~java
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

Một service có thể nhận trực tiếp đối tượng đã bind:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteClientService {
    private final ClientProperties properties;

    public RemoteClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public void describeTimeout() {
        System.out.println(properties.connectTimeout());
    }
}
~~~

Trong ví dụ này, Binder lấy `app.client.base-url`, `app.client.connect-timeout`, `app.client.max-retries` từ cấu hình hiệu lực rồi chuyển thành `URI`, `Duration` và `int`. Ví dụ `3s`, `500ms` và `200ms` có thể được chuyển thành `Duration` thay vì phải tự parse chuỗi. Cần có `@ConfigurationPropertiesScan` hoặc một cách đăng ký tương đương như `@EnableConfigurationProperties(ClientProperties.class)`; chỉ khai báo record không bảo đảm bean được tạo.

**Relaxed binding** giúp nối tên theo convention. Ví dụ key canonical `base-url` tương ứng với thuộc tính Java `baseUrl`. Tương tự `max-retries` ↔ `maxRetries`. Nên chuẩn hóa tên khai báo trong file thành *kebab-case* để tránh rối khi đi qua nhiều nguồn.

Binding còn xử lý cấu trúc lồng nhau, danh sách, map và kiểu chuyên biệt như `DataSize` khi nguồn có dạng phù hợp. Với các cấu hình cần đảm bảo đầu vào, có thể kết hợp `@Validated` và Jakarta Bean Validation (kèm dependency validation thích hợp) để phát hiện giá trị sai lúc tạo đối tượng thay vì chờ lỗi ở một request sau này.

### Cùng đọc một key: Environment, @Value hay @ConfigurationProperties?

| Cách đọc | Hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| `Environment.getProperty(...)` | Tra cứu động theo tên key trong một thành phần | Caller phải biết key và xử lý thiếu giá trị |
| `@Value("${app.client.connect-timeout:3s}")` | Một hoặc vài giá trị đơn lẻ | Placeholder và default nằm rải trong mã nếu dùng nhiều |
| `@ConfigurationProperties(prefix = "app.client")` | Một nhóm cấu hình có ý nghĩa nghiệp vụ | Cần đăng ký bean; có thể thêm validation và metadata |

`@Value` cũng hỗ trợ placeholder và chuyển kiểu thông dụng. Tuy nhiên, đối với một nhóm thiết lập có quan hệ như cấu hình HTTP client, type-safe binding thường rõ ràng và dễ bảo trì hơn các biến rời rạc.

## 7. Phân biệt placeholder, giá trị mặc định và nguồn cấu hình

Có ba cách dễ nhầm:

~~~yaml
# Giá trị được định nghĩa trong một nguồn
app:
  client:
    connect-timeout: 3s
~~~

~~~java
// Giá trị fallback khi placeholder không tìm thấy key
@Value("${app.client.connect-timeout:5s}")
private Duration timeout;
~~~

~~~java
// Tra cứu thủ công với fallback ở phía caller
String timeoutText = environment.getProperty(
    "app.client.connect-timeout", "5s");
~~~

Nếu `app.client.connect-timeout` tồn tại trong nguồn có ưu tiên phù hợp, giá trị từ nguồn được dùng; fallback trong placeholder hoặc lời gọi API không ghi đè nó. **Fallback không phải một PropertySource có độ ưu tiên cao**. Với `@ConfigurationProperties`, lựa chọn default cần thể hiện qua thiết kế đối tượng/cách binding tương ứng, không mặc định rằng cú pháp `@Value` áp dụng nguyên xi cho mọi field.

Lưu ý phân biệt giá trị bị thiếu, chuỗi rỗng và giá trị sai định dạng. Chúng có thể tạo ra hành vi khác nhau tùy kiểu đích, cách binding và validation.

## 8. Dòng thời gian khởi động: ai làm việc trước?

1. **Ứng dụng nhận đầu vào khởi động**: command-line, system properties, biến môi trường, vị trí cấu hình.
2. **Spring Boot chuẩn bị Environment và xử lý Config Data**: giải quyết location/import, profile, tệp/tài liệu được áp dụng và thứ tự property source.
3. **Các điều kiện bean được đánh giá trong quá trình tạo ApplicationContext**: `@Profile` và các điều kiện cấu hình khác có thể dựa vào Environment.
4. **Binder hoặc cơ chế injection lấy giá trị hiệu lực**: `@ConfigurationProperties`, `@Value` và mã gọi `Environment` nhận cấu hình cần thiết.
5. **Ứng dụng vận hành với cấu hình đã nhận**: các bean sử dụng giá trị đã được thiết lập trong vòng đời khởi tạo của chúng.

Đây là bản đồ khái niệm của quá trình, không phải cam kết rằng mọi property đều chỉ được đọc ở một thời điểm duy nhất: một bean vẫn có thể gọi `Environment` vào lúc khác. Nhưng những quyết định cấu trúc trong startup, chẳng hạn chọn nguồn Config Data hoặc điều kiện tạo bean, không mặc nhiên được tính lại khi thay đổi file đang chạy.

## 9. Cách truy vết khi giá trị không như kỳ vọng

Giả sử thời gian chờ mong đợi là `1s`, nhưng ứng dụng lại sử dụng `200ms`. Truy vết theo cùng trật tự của bản đồ:

1. **Xác định key canonical** đang được mã sử dụng: ví dụ `app.client.connect-timeout`. Kiểm tra có gõ nhầm prefix hoặc tên field không.
2. **Xác định active profiles** của tiến trình đang chạy. Đừng suy diễn từ tên máy, thư mục hay biến môi trường chưa được nạp vào tiến trình.
3. **Liệt kê các nguồn có thể khai báo key**: YAML/properties cơ sở, bản theo profile, biến môi trường, system properties, command-line, dữ liệu import và cấu hình test.
4. **Đối chiếu thứ tự ưu tiên** tại thời điểm khởi động để tìm nguồn thắng, thay vì chỉ sửa tệp đầu tiên nhìn thấy.
5. **Kiểm tra bước binding**: key có map đúng sang field không, kiểu đích có chuyển đổi được không, validation có báo lỗi không.
6. **Kiểm tra thời điểm sử dụng**: bean được tạo lúc nào; có đang kỳ vọng reload động dù ứng dụng chưa hỗ trợ không.

Với ứng dụng có Spring Boot Actuator, endpoint `env` và `configprops` (nếu đã bật và được cấp quyền) có thể giúp quan sát nguồn hoặc binding. Cần giữ cơ chế kiểm soát truy cập và che thông tin nhạy cảm; không công khai các endpoint hay tự in mật khẩu/token để gỡ lỗi. Một số giá trị được sanitize nên không xuất hiện nguyên văn trong kết quả chẩn đoán.

## 10. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Ứng dụng chỉ đọc `application.yml`.” | Nó có thể tổng hợp nhiều nguồn và tuân theo thứ tự ưu tiên. |
| “Active `dev` nên chắc chắn thắng mọi cấu hình khác.” | Profile giúp chọn config data/bean; nguồn ưu tiên cao hơn vẫn có thể ghi đè key. |
| “Thêm `application-prod.yml` thì `prod` tự active.” | Tệp theo profile chỉ được áp dụng khi profile tương ứng được kích hoạt qua cơ chế hợp lệ. |
| “`Environment` và `@ConfigurationProperties` là hai nơi giữ giá trị độc lập.” | Binder đọc từ hạ tầng cấu hình hiệu lực rồi ánh xạ sang đối tượng Java. |
| “`@Value` và `@ConfigurationProperties` dùng y hệt nhau.” | Một bên thuận tiện cho giá trị riêng lẻ; bên kia mô hình hóa nhóm cấu hình theo kiểu. |
| “Đổi file YAML khi app đang chạy thì bean tự đổi theo.” | Cần cơ chế refresh/rebind riêng; chỉnh file không tự bảo đảm thay đổi runtime. |
| “Cấu hình bí mật nên để cố định trong source code.” | Nên cấp từ nguồn bảo mật phù hợp với môi trường triển khai và hạn chế lộ qua log/endpoint. |

## 11. Tự kiểm tra bằng tình huống nhỏ

**Tình huống A.** `application.yml` đặt `app.client.max-retries=2`; `application-dev.yml` đặt `4`; ứng dụng chạy với `dev` và `--app.client.max-retries=6`. Giá trị hiệu lực trong ví dụ là **6** vì command-line ghi đè dữ liệu Config Data.

**Tình huống B.** Không có `app.client.base-url` trong bất kỳ nguồn nào. `@Value("${app.client.base-url:https://fallback.example.test}")` có giá trị fallback, trong khi một cấu hình bind bắt buộc kiểu `URI` có ràng buộc not-null có thể khiến khởi động thất bại khi thiếu giá trị. Kết quả phụ thuộc cách khai báo default và validation của từng consumer.

**Tình huống C.** Có tệp `application-prod.yml`, nhưng active profile là `dev`. Nội dung chỉ dành cho `prod` không được nạp chỉ vì tệp tồn tại. Nếu không thấy giá trị mong đợi, kiểm tra profile và nguồn thắng trước khi nghi ngờ Binder.

**Tình huống D.** Trong Java, field tên `connectTimeout`; trong YAML, key là `connect-timeout`. Đây là cặp tên được relaxed binding hỗ trợ. Nhưng điều đó không biến một prefix bị viết sai thành đúng: `@ConfigurationProperties(prefix = "app.client")` sẽ không tự tìm các key nằm dưới prefix khác.

## 12. Mô hình ghi nhớ

Hãy lần lượt trả lời năm câu hỏi:

1. **Key gì?** — Xác định tên thuộc tính, ưu tiên tên canonical `kebab-case`.
2. **Nguồn nào?** — Tìm các tệp, biến môi trường, system properties và đối số có khai báo key.
3. **Profile nào?** — Biết tài liệu theo profile và bean nào được kích hoạt.
4. **Giá trị hiệu lực nào?** — `Environment` phản ánh kết quả tra cứu theo các property source.
5. **Đi vào Java như thế nào?** — Đọc bằng `Environment`/`@Value` hoặc bind một nhóm bằng `@ConfigurationProperties`, rồi chuyển kiểu và kiểm tra hợp lệ.

Khi phân biệt được **tên thuộc tính → nguồn và ưu tiên → profile → Environment → binding → bean**, việc giải thích một giá trị cấu hình trong Spring Boot trở thành một chuỗi truy vết có thể kiểm chứng, thay vì đoán theo tên file.
