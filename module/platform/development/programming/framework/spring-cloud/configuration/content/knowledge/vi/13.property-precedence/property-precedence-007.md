# Giải thích một giá trị bằng nguồn gốc thay vì đoán theo tên tệp

Khi một thuộc tính Spring Boot có mặt trong nhiều tệp hoặc nhiều nguồn cấu hình, nhìn vào tên tệp không đủ để biết ứng dụng đang dùng giá trị nào. Config Server có thể ghép cấu hình dùng chung với cấu hình theo profile và theo ứng dụng; Config Client tiếp tục kết hợp property source từ xa với cấu hình cục bộ, biến môi trường và tham số khởi chạy. Một thuộc tính có thể bị ghi đè ở nhiều tầng trước khi được bind vào bean.

Muốn giải thích chính xác một giá trị, cần truy vết từ request mà client gửi tới Config Server, các property source mà server trả về, thứ tự ưu tiên trong Spring Environment và giá trị cuối cùng mà ứng dụng sử dụng. Thông tin origin (nguồn gốc) giúp xác định thuộc tính đến từ tệp, biến môi trường hay nguồn nào; kiểm tra binding giúp xác nhận bean đã nhận đúng giá trị đó.

Bài học này hướng dẫn cách truy vết theo bằng chứng. Bạn sẽ biết cách phân biệt tên tệp với nguồn thắng thực tế, đọc phản hồi Config Server, kiểm tra PropertySource và origin, phát hiện ghi đè từ runtime, cũng như điều tra trường hợp Environment đúng nhưng bean vẫn có giá trị khác.

Sau bài học, bạn có thể:

- Giải thích vì sao tên tệp cấu hình không chứng minh giá trị hiệu lực.
- Xác định đúng application, profile và label mà Config Client yêu cầu.
- Đọc danh sách property source trong phản hồi Config Server.
- Truy vết thứ tự ưu tiên và origin của một khóa trong Spring Environment.
- Phân biệt giá trị trong Environment với giá trị đã bind vào bean.
- Phân tích ghi đè từ biến môi trường, tham số JVM và command line.
- Dùng Actuator, log và kiểm thử để chứng minh nguồn cung cấp giá trị.

## 1. Vì sao không thể đoán nguồn từ tên tệp?

Một repository Git thường có các tệp như:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── orders-service-prod.yml
~~~

Nhìn vào tên, ta biết các tệp có phạm vi dự kiến khác nhau:

- <code>application.yml</code>: cấu hình mặc định dùng chung.
- <code>application-prod.yml</code>: cấu hình chung khi profile <code>prod</code> được yêu cầu.
- <code>orders-service.yml</code>: cấu hình riêng của ứng dụng <code>orders-service</code>.
- <code>orders-service-prod.yml</code>: cấu hình riêng theo profile <code>prod</code> của ứng dụng đó.

Những tên này giúp Config Server tìm và tổ chức nguồn cấu hình. Chúng chưa đủ để kết luận giá trị cuối cùng mà một bean đang sử dụng, vì:

1. Client có thể gửi application name hoặc profile khác với dự kiến.
2. Label có thể trỏ tới một commit khác với commit mà người kiểm tra đang xem.
3. Config Server có thể dùng nhiều search path hoặc nhiều backend.
4. Một khóa có thể xuất hiện trong nhiều property source.
5. Config Client có thể nhận giá trị ghi đè từ nguồn cục bộ.
6. Biến môi trường hoặc tham số command line có thể thay đổi giá trị sau khi cấu hình từ xa được nạp.
7. Bean có thể có giá trị mặc định, logic chuyển đổi hoặc logic gán lại riêng.

Vì thế, câu trả lời “giá trị này nằm trong <code>orders-service-prod.yml</code>” chỉ đúng khi đã xác minh đó là nguồn cung cấp giá trị hiệu lực. Một tệp có thể chứa khóa nhưng bị nguồn khác ghi đè; một tệp có thể không có khóa nhưng ứng dụng vẫn nhận giá trị từ nguồn chung hoặc từ môi trường chạy.

## 2. Luồng truy vết từ request tới giá trị đang dùng

Có thể chia quá trình thành bốn chặng:

~~~mermaid
flowchart TD
    A["Config Client khởi động"] --> B["Application / Profile / Label thực tế"]
    B --> C["Config Server xử lý request"]
    C --> D["Environment và danh sách propertySources"]
    D --> E["Config Client nạp vào Spring Environment"]
    E --> F["Thứ tự PropertySource và nguồn ghi đè"]
    F --> G["Placeholder / type conversion / binding"]
    G --> H["Giá trị trong bean và hành vi ứng dụng"]
    H --> I["Đối chiếu origin, log và kiểm thử"]
~~~

Mỗi chặng trả lời một câu hỏi:

| Chặng | Câu hỏi cần xác minh | Bằng chứng |
|---|---|---|
| Request | Client yêu cầu cấu hình nào? | Log client, application/profile/label, URL |
| Config Server | Server tìm được những nguồn nào? | HTTP response, <code>propertySources</code>, version/ref |
| Spring Environment | Nguồn nào thắng khi trùng khóa? | Thứ tự <code>PropertySource</code>, Actuator <code>env</code>, origin |
| Binding và sử dụng | Bean thực tế nhận giá trị nào? | Actuator <code>configprops</code>, debug, integration test |

Không bỏ qua chặng đầu. Nếu client đang gửi <code>orders-service/staging/main</code>, việc đọc <code>orders-service-prod.yml</code> ở nhánh release sẽ không giải thích được phản hồi hiện tại.

## 3. Xác minh application, profile và label trước

Config Server thường nhận yêu cầu theo dạng:

~~~http
GET /{application}/{profile}/{label}
~~~

Ví dụ:

~~~http
GET https://config.internal/orders-service/prod/release-2026.11
~~~

Ba thành phần có ý nghĩa riêng:

| Thành phần | Nguồn thường gặp | Cần xác minh |
|---|---|---|
| Application | <code>spring.application.name</code> | Có đúng tên dịch vụ và khớp quy ước repository không? |
| Profile | <code>spring.profiles.active</code> và các profile được kích hoạt | Có đúng profile mà pipeline triển khai dự kiến không? |
| Label | <code>spring.cloud.config.label</code> hoặc label mặc định server | Đang trỏ tới branch, tag hay commit nào? |

### Application name

Nếu <code>spring.application.name</code> sai, Config Server có thể không tìm thấy tệp riêng mong muốn. Nếu vẫn có <code>application.yml</code>, request có thể nhận cấu hình chung và trả HTTP 200. Vì vậy, kết nối thành công chưa chứng minh application name đúng.

### Profile

Profile có thể được cấp từ tệp cấu hình, biến môi trường hoặc tham số khởi chạy. Trong một ứng dụng, nhiều profile có thể cùng hoạt động. Hãy kiểm tra danh sách profile thực tế trong log khởi động và trong response Config Server, thay vì chỉ xem giá trị dự kiến trong một tệp.

### Label

Label xác định phiên bản nguồn cấu hình. Hai người cùng mở một tệp <code>orders-service-prod.yml</code> nhưng ở hai commit khác nhau có thể nhìn thấy hai giá trị khác nhau. Khi điều tra, ghi lại label và version/commit mà Config Server thực sự phục vụ nếu metadata response có cung cấp.

Không bắt đầu bằng cách mở một tệp theo tên rồi suy ra request. Bắt đầu bằng request thật, sau đó mới đối chiếu repository.

## 4. Đọc Environment mà Config Server trả về

Gọi endpoint bằng đúng application, profile và label:

~~~bash
curl -i "https://config.internal/orders-service/prod/release-2026.11"
~~~

Phản hồi Config Server thường có các trường như:

- <code>name</code>: application được yêu cầu.
- <code>profiles</code>: các profile được xử lý.
- <code>label</code>: label được yêu cầu hoặc được resolve.
- <code>version</code>: version Git nếu backend cung cấp.
- <code>propertySources</code>: các nguồn thuộc tính mà server đã ghép.

Ví dụ minh họa:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": "orders-service-prod.yml",
      "source": {
        "orders.http.read-timeout": "7s"
      }
    },
    {
      "name": "application-prod.yml",
      "source": {
        "orders.http.read-timeout": "5s"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "orders.http.read-timeout": "3s"
      }
    }
  ]
}
~~~

Đây là response minh họa để giải thích cách đọc, không phải thứ tự cố định cho mọi cấu hình. Trong một response thực tế, hãy quan sát thứ tự <code>propertySources</code> mà server trả về và kiểm tra backend, composite order, search path cùng quy tắc của phiên bản đang dùng.

Tên <code>propertySources[].name</code> cho biết nguồn mà server đã đưa vào Environment. <code>source</code> cho thấy các khóa và giá trị thô từ nguồn đó. Response này là bằng chứng tốt hơn việc chỉ mở một tệp Git vì nó phản ánh kết quả server đã phân giải cho request cụ thể.

Tuy nhiên, response của Config Server chưa cho biết mọi nguồn có thể được thêm vào ở phía client. Biến môi trường, tham số command line, thuộc tính hệ thống và tệp cục bộ có thể còn tham gia vào Environment sau khi client nạp dữ liệu từ xa.

## 5. Thứ tự PropertySource: tìm nguồn thắng thực tế

Spring <code>Environment</code> giữ các <code>PropertySource</code> theo thứ tự ưu tiên. Khi truy vấn một khóa, nguồn có độ ưu tiên cao hơn chứa khóa đó sẽ cung cấp giá trị được trả về. Các nguồn phía sau vẫn có thể chứa cùng khóa nhưng không phải nguồn thắng.

Ví dụ, cùng một khóa <code>orders.http.read-timeout</code> xuất hiện ở ba nguồn:

| Property source | Giá trị | Vai trò |
|---|---:|---|
| Cấu hình chung | <code>3s</code> | Giá trị nền |
| Cấu hình profile production | <code>5s</code> | Ghi đè theo môi trường |
| Cấu hình riêng orders production | <code>7s</code> | Giá trị riêng dịch vụ |

Nếu thứ tự nguồn thực tế đặt cấu hình riêng lên trước cấu hình chung, giá trị có thể là <code>7s</code>. Nhưng không nên kết luận chỉ từ tên tệp. Phải đọc thứ tự property source trong response và Environment.

### Các tầng nguồn có thể tham gia

Một ứng dụng Spring Boot có thể có nhiều loại nguồn:

- Property source từ Config Server.
- <code>application.yml</code> hoặc <code>application.properties</code> cục bộ.
- Tệp cấu hình profile-specific cục bộ.
- Biến môi trường của tiến trình.
- Thuộc tính hệ thống JVM (<code>-D...</code>).
- <code>SPRING_APPLICATION_JSON</code>.
- Tham số command line (<code>--property=value</code>).
- Giá trị mặc định trong code hoặc trong constructor của bean.

Thứ tự chính xác phụ thuộc phiên bản Spring Boot, cách dùng Config Data API hay bootstrap, cách import và cấu hình ghi đè của Spring Cloud Config. Một số thuộc tính như <code>spring.cloud.config.allowOverride</code>, <code>spring.cloud.config.overrideNone</code> và <code>spring.cloud.config.overrideSystemProperties</code> có thể ảnh hưởng việc nguồn cục bộ được phép ghi đè cấu hình từ xa như thế nào. Không thêm các cờ này theo suy đoán; hãy kiểm tra đúng phiên bản và nguồn cấu hình nơi chúng cần được khai báo.

### Ví dụ có command line override

Giả sử Config Server trả:

~~~yaml
orders:
  http:
    read-timeout: 7s
~~~

Nhưng tiến trình được chạy với:

~~~bash
java -jar orders-service.jar --orders.http.read-timeout=9s
~~~

Tham số command line thường có độ ưu tiên cao trong Spring Boot. Nếu nó đứng trước nguồn Config Server trong Environment, ứng dụng sẽ dùng <code>9s</code>. Việc Git vẫn chứa <code>7s</code> không có nghĩa Config Server trả sai; nguồn thắng đã được cung cấp ở runtime.

## 6. Phân biệt ba điều: giá trị khai báo, giá trị Environment và giá trị bean

Khi giải thích một cấu hình, cần nói rõ đang đề cập tới lớp nào.

**Giá trị khai báo** là nội dung trong tệp hoặc secret store. Ví dụ Git có <code>read-timeout: 7s</code>.

**Giá trị Environment** là kết quả Spring trả về sau khi xét property source và placeholder. Ví dụ <code>Environment.getProperty("orders.http.read-timeout")</code> trả về <code>9s</code>.

**Giá trị bean** là giá trị đã được bind hoặc gán vào đối tượng ứng dụng. Bean có thể nhận <code>9s</code>, nhưng cũng có thể chuyển đổi, áp dụng default hoặc bị logic code thay đổi sau đó.

Bảng ví dụ:

| Lớp | Giá trị | Cách kiểm tra |
|---|---|---|
| Git | <code>7s</code> | Xem đúng repository, label và commit |
| Config Server response | <code>7s</code> | Đọc <code>propertySources[].source</code> |
| Spring Environment | <code>9s</code> | Actuator <code>env</code> hoặc <code>Environment.getProperty</code> |
| Bean properties | <code>Duration.ofSeconds(9)</code> | Actuator <code>configprops</code>, debug hoặc test |
| Hành vi runtime | Timeout thực tế của HTTP client | Kiểm tra cấu hình thư viện/client và telemetry |

Nếu Environment trả <code>9s</code> nhưng bean giữ <code>7s</code>, cần kiểm tra binding và vòng đời bean. Nếu bean đã nhận <code>9s</code> nhưng HTTP client vẫn timeout sau <code>7s</code>, có thể thư viện được cấu hình ở một nơi khác hoặc client đã được tạo trước khi refresh.

## 7. Dùng Actuator env để truy vết origin

Spring Boot Actuator cung cấp endpoint <code>env</code> để xem các property source và thông tin về một thuộc tính trong Environment. Khi được bật, endpoint tổng quát:

~~~http
GET /actuator/env
~~~

Có thể truy vấn một khóa cụ thể:

~~~http
GET /actuator/env/orders.http.read-timeout
~~~

Response có thể cho biết:

- Giá trị hiện tại trong Environment.
- Tên property source cung cấp giá trị.
- Các nguồn khác có cùng khóa.
- Origin metadata, chẳng hạn tệp resource và vị trí dòng nếu nguồn có cung cấp.

Ví dụ minh họa:

~~~json
{
  "property": {
    "source": "commandLineArgs",
    "value": "9s",
    "origin": "commandLineArgs"
  },
  "activeProfiles": ["prod"]
}
~~~

Một response khác có thể chỉ ra origin từ tệp:

~~~text
Config resource 'class path resource [application-prod.yml]'
via location 'optional:classpath:/'
- 12:18
~~~

Định dạng chi tiết phụ thuộc phiên bản Spring Boot và loại property source. Một số nguồn như biến môi trường hoặc nguồn tùy chỉnh có thể không có vị trí dòng giống tệp YAML.

### Bật endpoint một cách có kiểm soát

Ví dụ cấu hình chỉ expose endpoint cần dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
~~~

Các endpoint này có thể tiết lộ hostname, cấu trúc nội bộ và thông tin nhạy cảm. Trong production, cần bảo vệ bằng xác thực/phân quyền, giới hạn mạng và cấu hình masking. Chỉ cấp quyền xem giá trị cho người thực sự cần. Không công khai <code>/actuator/env</code> ra Internet và không đưa response chứa secret vào ticket hoặc log chia sẻ.

Tùy phiên bản Spring Boot, có thể cấu hình chính sách hiển thị giá trị của endpoint <code>env</code>, chẳng hạn chỉ hiển thị khi người gọi được xác thực. Kiểm tra tài liệu phiên bản và chọn chính sách hạn chế nhất đáp ứng nhu cầu vận hành.

## 8. Dùng configprops để xác nhận giá trị đã bind

Endpoint <code>env</code> giúp biết giá trị trong Environment. Endpoint <code>configprops</code> giúp kiểm tra các bean được bind từ <code>@ConfigurationProperties</code>.

Ví dụ ứng dụng có:

~~~java
@ConfigurationProperties(prefix = "orders.http")
@Validated
public class OrdersHttpProperties {

    @NotNull
    private Duration readTimeout;

    // getter và setter
}
~~~

Sau khi đăng ký properties class, bean có thể nhận giá trị từ Environment. Endpoint:

~~~http
GET /actuator/configprops
~~~

có thể hiển thị prefix, bean và các thuộc tính đã bind. Dùng endpoint này để trả lời câu hỏi “bean cấu hình đang giữ giá trị nào?” thay vì chỉ nhìn response Config Server.

Nếu Environment và bean khác nhau, kiểm tra:

- Prefix hoặc tên thuộc tính có khớp không.
- Kiểu dữ liệu và conversion có thành công không.
- Bean có default field value hoặc constructor parameter không.
- Có nhiều bean cùng prefix nhưng được cấu hình khác nhau không.
- Bean có bị tạo trước khi property source được refresh không.
- Code có setter, post-processor hoặc logic tự gán lại giá trị không.

Không phải mọi bean trong ứng dụng đều được quản lý bằng <code>@ConfigurationProperties</code>. Với <code>@Value</code>, cấu hình constructor hoặc thư viện tự tạo client, cần kiểm tra đúng nơi nhận giá trị.

## 9. Kiểm tra bằng Spring Environment trong code

Khi cần chẩn đoán nội bộ hoặc viết integration test, có thể truy vấn trực tiếp Environment:

~~~java
@Component
public class ConfigDiagnostics {

    private final Environment environment;

    public ConfigDiagnostics(Environment environment) {
        this.environment = environment;
    }

    public String readTimeout() {
        return environment.getProperty("orders.http.read-timeout");
    }
}
~~~

Để xem nguồn nào chứa một khóa, có thể duyệt property source theo thứ tự:

~~~java
for (PropertySource<?> propertySource : environment.getPropertySources()) {
    Object value = propertySource.getProperty("orders.http.read-timeout");

    if (value != null) {
        System.out.println(
            propertySource.getName() + " -> " + value
        );
    }
}
~~~

Đây là ví dụ phục vụ kiểm thử/chẩn đoán. Không in toàn bộ giá trị cấu hình trong production vì property source có thể chứa password, token hoặc URL có credential. Với <code>CompositePropertySource</code>, cần duyệt tiếp các nguồn con để thấy nguồn cụ thể. Khi cần origin metadata, dùng API origin phù hợp của Spring Boot nếu property source hỗ trợ; không phải nguồn nào cũng cung cấp origin.

Trong test, nên xác nhận cả giá trị hiệu lực lẫn nguồn mong đợi. Ví dụ, nếu production yêu cầu giá trị từ Config Server, test không chỉ assert <code>read-timeout == 7s</code>, mà còn kiểm tra nguồn nào đã cung cấp <code>7s</code> và bảo đảm không có command-line hoặc biến môi trường của test ghi đè ngoài ý muốn.

## 10. Truy vết một ví dụ từ đầu tới cuối

Giả sử <code>orders-service</code> có ba tệp trong Git:

~~~yaml
# application.yml
orders:
  http:
    read-timeout: 3s
~~~

~~~yaml
# application-prod.yml
orders:
  http:
    read-timeout: 5s
~~~

~~~yaml
# orders-service-prod.yml
orders:
  http:
    read-timeout: 7s
~~~

Client production khai báo:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      label: release-2026.11
~~~

Pipeline lại chạy ứng dụng bằng:

~~~bash
java -jar orders-service.jar --orders.http.read-timeout=9s
~~~

Quy trình xác minh:

1. Log client xác nhận application là <code>orders-service</code>, profile là <code>prod</code>.
2. Request/response xác nhận label <code>release-2026.11</code> và version Git đang được server phục vụ.
3. Config Server response cho thấy các property source có chứa khóa <code>orders.http.read-timeout</code>.
4. Kiểm tra thứ tự <code>propertySources</code> để biết nguồn từ xa nào được ưu tiên nếu có nhiều giá trị trùng khóa.
5. Kiểm tra <code>/actuator/env/orders.http.read-timeout</code> ở client. Nếu origin là <code>commandLineArgs</code>, giá trị hiệu lực là <code>9s</code>.
6. Kiểm tra <code>/actuator/configprops</code> hoặc bean trong debug để xác nhận <code>OrdersHttpProperties.readTimeout</code> đã bind thành 9 giây.
7. Nếu HTTP client vẫn sử dụng 7 giây, kiểm tra nơi khởi tạo client và liệu nó có được tạo lại sau khi cấu hình thay đổi không.

Kết luận có căn cứ sẽ là: Git có các giá trị nền và theo profile/dịch vụ; Config Server trả những property source tương ứng với request; command line cung cấp giá trị có ưu tiên cao hơn trong Environment; bean đã bind giá trị runtime. Cách giải thích này chỉ ra cả nguồn và cơ chế, thay vì gán kết quả cho tên tệp có vẻ cụ thể nhất.

## 11. Composite repository và nhiều backend

Khi Config Server dùng composite repository, một thuộc tính có thể xuất hiện từ nhiều backend, ví dụ Git và Vault. Thứ tự backend và chính sách lỗi ảnh hưởng property source mà server trả về.

Trong trường hợp này, cần ghi nhận thêm:

- Các backend được cấu hình và thứ tự <code>order</code> hoặc thứ tự danh sách.
- Backend nào cung cấp property source chứa khóa.
- Label có áp dụng được cho mọi backend trong composite không.
- Một backend lỗi có khiến toàn bộ request thất bại hay tạo partial Environment.
- Secret backend có trả giá trị cùng tên khóa với Git hay không.

Không suy ra nguồn thắng chỉ từ loại backend. Hãy xem response Environment và thứ tự property source thực tế. Với secret, kiểm tra origin và quyền truy cập cẩn thận; không sao chép giá trị bí mật vào output chẩn đoán.

Nếu hai backend cùng cung cấp một khóa, hãy quyết định rõ đây là ghi đè có chủ đích hay lỗi thiết kế. Các thuộc tính có cùng tên nhưng khác ý nghĩa nên được tách namespace để tránh phụ thuộc thứ tự backend một cách khó hiểu.

## 12. Placeholder và giá trị mặc định cũng ảnh hưởng nguồn gốc

Một giá trị có thể được tạo từ placeholder thay vì được khai báo trực tiếp:

~~~yaml
orders:
  inventory:
    base-url: "https://${platform.inventory.host}:8443"
~~~

Khi truy vết <code>orders.inventory.base-url</code>, cần tìm cả hai thứ:

1. Property source chứa biểu thức placeholder.
2. Property source cung cấp <code>platform.inventory.host</code>.

Nếu host được ghi đè bởi biến môi trường phía client, URL cuối cùng có thể dùng host đó dù biểu thức được khai báo trong Git. Nếu placeholder có default như <code>${platform.inventory.host:localhost}</code>, ứng dụng có thể dùng <code>localhost</code> khi không tìm thấy khóa. Origin của thuộc tính URL có thể chỉ ra tệp chứa biểu thức, trong khi giá trị tham chiếu đến từ nguồn khác.

Do đó, một thuộc tính được phân giải có thể phụ thuộc vào nhiều nguồn. Khi báo cáo sự cố, hãy nêu nguồn chứa placeholder và nguồn cung cấp từng thành phần tham chiếu.

## 13. Các lỗi chẩn đoán thường gặp

| Kết luận vội | Vì sao chưa đủ bằng chứng | Cách xác minh |
|---|---|---|
| “Giá trị nằm trong tệp profile nên nó đang thắng” | Nguồn khác có thể ưu tiên cao hơn | Đọc propertySources và origin |
| “Config Server trả 200 nên cấu hình đúng” | Có thể sai application/profile hoặc thiếu khóa bắt buộc | Kiểm tra request và từng property |
| “Git đã đổi nên ứng dụng đang dùng giá trị mới” | Client có thể đang dùng label cũ hoặc chưa refresh/restart | Kiểm tra label, version và Environment |
| “Actuator env đúng nên bean chắc chắn đúng” | Binding hoặc logic code có thể làm giá trị khác | Kiểm tra configprops và bean |
| “Biến môi trường có giá trị nên nó luôn thắng” | Thứ tự nguồn phụ thuộc cấu hình và phiên bản | Xem Environment thực tế |
| “Tên property source có tên tệp là origin đầy đủ” | Tên nguồn không phải lúc nào cũng có vị trí dòng hoặc provenance từng khóa | Xem origin metadata nếu có |
| “Một replica cho kết quả này nên mọi replica giống nhau” | Runtime env, profile, label, cache hoặc server có thể khác | So sánh từng instance |

## 14. Quy trình truy vết có thể lặp lại

Khi có câu hỏi “vì sao ứng dụng đang dùng giá trị này?”, thực hiện theo trình tự:

1. **Ghi khóa chính xác:** dùng tên canonical, ví dụ <code>orders.http.read-timeout</code>.
2. **Xác minh request:** application, profile, label, URL và Config Client mode.
3. **Đọc response server:** property source nào chứa khóa, server version/ref nào được phục vụ.
4. **Kiểm tra Environment:** giá trị hiện tại, danh sách nguồn và origin.
5. **Tìm ghi đè runtime:** biến môi trường, system property, JSON, command line và nguồn cục bộ.
6. **Kiểm tra binding:** <code>@ConfigurationProperties</code>, <code>@Value</code>, default và conversion.
7. **Kiểm tra consumer:** bean hoặc thư viện thực sự sử dụng giá trị nào.
8. **So sánh replica:** nếu nhiều instance, kiểm tra cùng khóa trên từng instance.
9. **Ghi kết luận:** nêu giá trị, property source thắng, origin và cơ chế ghi đè.
10. **Sửa tại đúng nguồn:** cập nhật nguồn có chủ sở hữu; tránh thêm một bản ghi đè khác chỉ để che triệu chứng.

Một kết luận tốt nên có dạng: “<code>orders.http.read-timeout</code> hiện là <code>9s</code>; giá trị trong Config Server là <code>7s</code> ở property source của dịch vụ; <code>/actuator/env</code> cho thấy <code>commandLineArgs</code> cung cấp giá trị thắng; bean <code>OrdersHttpProperties</code> đã bind <code>9s</code>.” Câu trả lời này có thể được kiểm chứng và giúp nhóm sửa đúng nơi.

## 15. Checklist giải thích nguồn gốc một giá trị

- [ ] Đã ghi đúng tên property canonical.
- [ ] Đã xác minh application name, profile và label thực tế.
- [ ] Đã xác định version/ref của Config Server response.
- [ ] Đã đọc toàn bộ <code>propertySources</code> có chứa khóa.
- [ ] Đã kiểm tra thứ tự ưu tiên thay vì suy đoán từ tên tệp.
- [ ] Đã kiểm tra nguồn cục bộ, biến môi trường, system property và command line.
- [ ] Đã xem origin metadata nếu property source hỗ trợ.
- [ ] Đã xác nhận giá trị đã bind vào bean.
- [ ] Đã kiểm tra placeholder, default và logic code có thể thay đổi kết quả.
- [ ] Đã so sánh các replica nếu có khác biệt runtime.
- [ ] Đã bảo vệ Actuator và không làm lộ secret trong log hoặc báo cáo.
- [ ] Kết luận nêu rõ giá trị hiệu lực, nguồn thắng và bằng chứng.

Trong Spring Cloud Config, tên tệp giúp tổ chức và tìm cấu hình, còn nguồn gốc thực tế phải được chứng minh từ request, property source, thứ tự Environment và binding. Khi truy vết theo các lớp đó, nhóm có thể giải thích một giá trị bằng bằng chứng, xác định đúng điểm ghi đè và sửa cấu hình tại nơi chịu trách nhiệm.

