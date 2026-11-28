# Placeholder và phân giải giá trị trong nội dung được trả về

Trong kho cấu hình Spring Cloud Config, một thuộc tính có thể tham chiếu tới thuộc tính khác thay vì lặp lại một giá trị cố định. Ví dụ, URL của một dịch vụ có thể được tạo từ scheme, hostname và port được khai báo ở nơi khác. Spring dùng placeholder để biểu diễn tham chiếu này, thường theo dạng ${property.name} hoặc ${property.name:defaultValue}.

Khi Config Client lấy cấu hình từ Config Server, nội dung trả về có thể vẫn chứa chuỗi placeholder. Spring Environment ở phía ứng dụng phân giải các tham chiếu dựa trên những property source mà ứng dụng đang có. Vì vậy, cần hiểu rõ giá trị nào được trả về từ server, giá trị nào được thay thế ở client, nguồn nào cung cấp giá trị tham chiếu và thứ tự ưu tiên ảnh hưởng tới kết quả cuối cùng.

Bài học này trình bày cú pháp placeholder, luồng phân giải trong Spring Cloud Config, cách kết hợp cấu hình chung với cấu hình riêng, cách dùng giá trị mặc định, cách phát hiện placeholder chưa được giải quyết hoặc tham chiếu vòng và cách kiểm tra giá trị thực tế mà ứng dụng sử dụng.

Sau bài học, bạn có thể:

- Đọc và viết placeholder trong YAML hoặc Properties.
- Giải thích sự khác nhau giữa giá trị thô trong response của Config Server và giá trị đã được Spring phân giải.
- Xác định property source có thể cung cấp giá trị cho placeholder.
- Dùng placeholder để tái sử dụng cấu hình chung và ghi đè theo profile hoặc dịch vụ.
- Xử lý giá trị mặc định, placeholder lồng nhau, tham chiếu thiếu và tham chiếu vòng.
- Kiểm tra giá trị cuối cùng bằng Spring Environment, Actuator và kiểm thử ứng dụng.

## 1. Placeholder là gì?

Placeholder là một biểu thức đặt trong giá trị cấu hình để tham chiếu tới một thuộc tính khác. Spring thường dùng cú pháp:

~~~text
${property.name}
~~~

Ví dụ, một tệp có thể khai báo hostname và port riêng, rồi tạo URL từ hai thuộc tính đó:

~~~yaml
inventory:
  host: inventory.internal
  port: 8443
  base-url: https://${inventory.host}:${inventory.port}
~~~

Thuộc tính <code>inventory.base-url</code> có giá trị được tính từ hai thuộc tính khác. Khi Spring phân giải placeholder, kết quả có thể là:

~~~text
https://inventory.internal:8443
~~~

Lợi ích của cách này:

- Không phải lặp lại cùng hostname hoặc port ở nhiều nơi.
- Có thể thay đổi một giá trị nguồn và để các thuộc tính phụ thuộc sử dụng giá trị mới.
- Có thể dùng cấu hình chung làm mặc định rồi ghi đè ở phạm vi ứng dụng hoặc profile.
- Làm rõ quan hệ giữa các thuộc tính thay vì lưu nhiều chuỗi đã ghép sẵn.

Placeholder là tham chiếu ở thời điểm Spring đọc và phân giải cấu hình. Nó không phải cú pháp nội suy của Git, YAML parser hay shell. Việc một tệp YAML có cú pháp hợp lệ không có nghĩa mọi placeholder trong tệp đã được giải quyết.

## 2. Cú pháp cơ bản và giá trị mặc định

### Tham chiếu bắt buộc

~~~yaml
orders:
  inventory:
    base-url: https://${inventory.host}:${inventory.port}
~~~

Ở đây, Spring cần tìm được cả <code>inventory.host</code> và <code>inventory.port</code>. Nếu một giá trị không tồn tại và không có mặc định, quá trình phân giải có thể thất bại khi thuộc tính được truy cập hoặc bind, tùy nơi và thời điểm sử dụng.

### Tham chiếu có giá trị mặc định

Có thể đặt giá trị mặc định sau dấu hai chấm:

~~~yaml
orders:
  inventory:
    base-url: ${inventory.base-url:http://localhost:8082}
~~~

Nếu không tìm thấy <code>inventory.base-url</code>, Spring dùng giá trị mặc định <code>http://localhost:8082</code>.

Cú pháp tổng quát:

~~~text
${property.name:defaultValue}
~~~

Giá trị mặc định chỉ được dùng khi không phân giải được khóa tham chiếu theo quy tắc placeholder. Nó không thay thế validation nghiệp vụ. Ví dụ, dùng localhost làm mặc định cho production có thể khiến dịch vụ kết nối nhầm đích. Với thuộc tính bắt buộc hoặc nhạy cảm, thường nên để thiếu giá trị trở thành lỗi rõ ràng thay vì đặt một mặc định không an toàn.

Nếu giá trị mặc định chứa dấu hai chấm, ví dụ URL có scheme, Spring vẫn phân tích phần mặc định theo cú pháp placeholder. Nên đặt biểu thức trong chuỗi YAML có trích dẫn khi nội dung có ký tự đặc biệt:

~~~yaml
inventory:
  base-url: "${inventory.base-url:https://inventory.internal:8443}"
~~~

Việc trích dẫn giúp YAML đọc chuỗi rõ ràng. Nó không làm thay đổi cơ chế phân giải placeholder của Spring.

## 3. Config Server trả gì và placeholder được phân giải ở đâu?

Cần tách luồng thành hai giai đoạn.

1. **Config Server đọc và trả property source.** Server đọc repository, xác định application/profile/label và tạo phản hồi Environment gồm các property source. Giá trị trong repository có thể vẫn là chuỗi chứa placeholder.
2. **Config Client nạp property source vào Spring Environment.** Khi ứng dụng đọc thuộc tính qua cơ chế của Spring như <code>Environment</code>, <code>@Value</code> hoặc binding cấu hình, Spring có thể phân giải placeholder dựa trên Environment của client.

Ví dụ repository có:

~~~yaml
# application.yml
platform:
  inventory:
    host: inventory.internal
    port: 8443
~~~

~~~yaml
# orders-service.yml
orders:
  inventory:
    base-url: https://${platform.inventory.host}:${platform.inventory.port}
~~~

Client của <code>orders-service</code> yêu cầu cấu hình từ Config Server. Response có thể chứa giá trị thô:

~~~text
orders.inventory.base-url =
https://${platform.inventory.host}:${platform.inventory.port}
~~~

Sau khi property source được nạp vào Spring Environment, ứng dụng có thể phân giải thành:

~~~text
https://inventory.internal:8443
~~~

Điều quan trọng là giá trị tham chiếu phải có mặt trong Environment tại thời điểm phân giải. Nếu property source dùng chung không được nạp, hoặc một nguồn khác thay đổi giá trị tham chiếu, kết quả có thể khác dự kiến.

### Không đồng nhất môi trường của server với môi trường của client

Một placeholder được lưu trong repository không nên được hiểu là tự động lấy biến môi trường của tiến trình Config Server. Ví dụ:

~~~yaml
orders:
  inventory:
    base-url: ${INVENTORY_BASE_URL}
~~~

Khi ứng dụng Spring Boot nạp property source, Spring tìm thuộc tính tương ứng trong Environment của client. Nếu biến môi trường chỉ tồn tại ở máy Config Server mà không có trong môi trường client, client không thể dựa vào biến đó như thể nó là biến cục bộ của mình.

Nếu muốn giá trị được cấp cho ứng dụng, hãy cung cấp nó qua một property source mà client nhận được hoặc qua biến môi trường/secret mount của chính tiến trình client. Không dựa vào việc Config Server tình cờ có một biến môi trường cùng tên.

### Consumer không phải Spring

Nếu một hệ thống khác gọi REST endpoint của Config Server và tự đọc JSON, nó có thể nhìn thấy chuỗi placeholder chưa được thay thế. Hệ thống đó cần có cơ chế phân giải tương ứng hoặc phải nhận cấu hình đã được xử lý theo hợp đồng riêng. Không nên giả định mọi consumer HTTP đều tự động có hành vi giống Spring Config Client.

## 4. Placeholder tham chiếu giữa cấu hình chung và cấu hình riêng

Một cách tổ chức phổ biến là khai báo giá trị nền trong <code>application.yml</code> và dùng placeholder trong tệp của từng dịch vụ.

Ví dụ:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── inventory-service.yml
~~~

Cấu hình chung:

~~~yaml
# application.yml
platform:
  inventory:
    host: inventory.internal
    port: 8082
~~~

Cấu hình riêng của đơn hàng:

~~~yaml
# orders-service.yml
orders:
  inventory:
    base-url: http://${platform.inventory.host}:${platform.inventory.port}
    connect-timeout: 1s
~~~

Với profile production, có thể thay đổi host/port ở tệp chung theo profile:

~~~yaml
# application-prod.yml
platform:
  inventory:
    host: inventory.prod.internal
    port: 8443
~~~

Client <code>orders-service</code> hoạt động với profile <code>prod</code> sẽ nhận các property source phù hợp. Khi placeholder được phân giải trong Environment, URL có thể thành:

~~~text
http://inventory.prod.internal:8443
~~~

Nếu muốn HTTPS, cần khai báo scheme phù hợp trong thuộc tính URL hoặc đưa scheme thành một thuộc tính riêng. Ví dụ:

~~~yaml
platform:
  inventory:
    scheme: https
    host: inventory.prod.internal
    port: 8443
~~~

~~~yaml
orders:
  inventory:
    base-url: ${platform.inventory.scheme}://${platform.inventory.host}:${platform.inventory.port}
~~~

Việc đặt scheme, host và port riêng có ích khi nhiều dịch vụ cùng dùng một endpoint. Tuy nhiên, không nên tách nhỏ mọi chuỗi thành quá nhiều thuộc tính nếu chúng luôn thay đổi cùng nhau và không có nhu cầu tái sử dụng. Thiết kế tốt cần làm rõ phạm vi sở hữu và đơn vị thay đổi của từng giá trị.

## 5. Thứ tự ưu tiên và nguồn cung cấp giá trị placeholder

Placeholder được tìm trong các property source của Spring Environment. Nguồn có độ ưu tiên cao hơn có thể cung cấp giá trị tham chiếu ngay cả khi placeholder được khai báo trong cấu hình từ Config Server.

Ví dụ, Config Server trả về:

~~~yaml
platform:
  inventory:
    host: inventory.internal
orders:
  inventory:
    base-url: http://${platform.inventory.host}:8082
~~~

Nhưng môi trường chạy client có biến:

~~~text
PLATFORM_INVENTORY_HOST=inventory-canary.internal
~~~

Nếu biến môi trường client có độ ưu tiên cao hơn property source từ xa theo thứ tự cấu hình hiện tại, placeholder có thể được phân giải thành:

~~~text
http://inventory-canary.internal:8082
~~~

Do đó, cần phân biệt:

- **Nguồn chứa placeholder:** nơi khai báo biểu thức cần phân giải.
- **Nguồn cung cấp giá trị tham chiếu:** nơi chứa khóa được nhắc tới trong biểu thức.
- **Giá trị cuối cùng:** kết quả sau khi Spring phân giải trong Environment.

Thứ tự ưu tiên giữa Config Server và nguồn cục bộ phụ thuộc cách nạp Config Data và chính sách ghi đè đã cấu hình. Những thuộc tính như <code>spring.cloud.config.allowOverride</code>, <code>spring.cloud.config.overrideNone</code> và <code>spring.cloud.config.overrideSystemProperties</code> có thể ảnh hưởng việc nguồn cục bộ được phép ghi đè nguồn từ xa như thế nào. Cần kiểm tra theo phiên bản Spring Cloud đang dùng.

Khi kết quả không như dự kiến, hãy xem giá trị tham chiếu đến từ đâu thay vì chỉ kiểm tra tệp chứa placeholder. Một biến môi trường cũ có thể khiến URL trỏ sang hệ thống khác dù Git repository đã được cập nhật đúng.

## 6. Placeholder lồng nhau và tham chiếu nhiều bước

Một placeholder có thể tham chiếu tới thuộc tính mà chính nó lại chứa placeholder khác.

Ví dụ:

~~~yaml
platform:
  inventory:
    scheme: https
    host: inventory.internal
    port: 8443
    base-url: ${platform.inventory.scheme}://${platform.inventory.host}:${platform.inventory.port}

orders:
  inventory:
    endpoint: ${platform.inventory.base-url}
~~~

Kết quả cuối cùng của <code>orders.inventory.endpoint</code> có thể là:

~~~text
https://inventory.internal:8443
~~~

Spring hỗ trợ phân giải placeholder lồng nhau trong các cơ chế cấu hình thông thường. Tuy nhiên, chuỗi tham chiếu càng sâu thì càng khó hiểu và khó truy vết. Nên giới hạn số tầng và dùng tên thuộc tính mô tả rõ ý nghĩa.

Tránh tạo chuỗi phụ thuộc vòng:

~~~yaml
service:
  first: ${service.second}
  second: ${service.first}
~~~

Hai thuộc tính này phụ thuộc lẫn nhau và không có giá trị nền để phân giải. Tùy cách truy cập và cơ chế phân giải, kết quả có thể là lỗi vòng lặp hoặc placeholder không được giải quyết. Cần thiết kế đồ thị tham chiếu một chiều, có điểm bắt đầu là các giá trị cụ thể.

Một quy tắc dễ bảo trì:

- Các giá trị nền như host, port, scheme được khai báo ở một nơi.
- Các giá trị ghép như base URL tham chiếu tới giá trị nền.
- Thuộc tính nghiệp vụ của dịch vụ tham chiếu tới base URL.
- Không để một thuộc tính nền phụ thuộc ngược lại thuộc tính nghiệp vụ của dịch vụ.

## 7. Placeholder thiếu, mặc định và lỗi phân giải

Khi một placeholder không tìm thấy khóa tham chiếu, hành vi phụ thuộc vào việc biểu thức có giá trị mặc định hay không và cách ứng dụng sử dụng thuộc tính.

Ví dụ không có mặc định:

~~~yaml
orders:
  inventory:
    base-url: http://${platform.inventory.host}:8082
~~~

Nếu <code>platform.inventory.host</code> không tồn tại, Spring có thể báo lỗi khi phân giải thuộc tính. Lỗi có thể xuất hiện lúc khởi tạo bean, bind <code>@ConfigurationProperties</code> hoặc khi gọi <code>Environment.getProperty</code> với cơ chế resolve placeholder.

Ví dụ có mặc định:

~~~yaml
orders:
  inventory:
    base-url: http://${platform.inventory.host:localhost}:8082
~~~

Nếu không tìm thấy host, Spring dùng <code>localhost</code>. Điều này hữu ích cho cấu hình phát triển nhưng có thể nguy hiểm khi production vô tình nhận giá trị mặc định.

Nên chọn mặc định theo mục đích:

| Loại thuộc tính | Cách xử lý gợi ý |
|---|---|
| Host dịch vụ bắt buộc trong production | Không dùng mặc định localhost; validation phải thất bại khi thiếu |
| Mức log | Có thể dùng mặc định an toàn |
| Cổng nội bộ cố định của môi trường phát triển | Có thể có mặc định dev rõ ràng |
| Secret, token hoặc mật khẩu | Không dùng chuỗi giả làm mặc định để che thiếu secret |
| Cờ tính năng tùy chọn | Đặt mặc định an toàn và ghi rõ hành vi khi tắt |

Không nên thêm mặc định chỉ để ứng dụng khởi động bằng mọi giá. Mặc định có thể biến lỗi triển khai dễ phát hiện thành lỗi vận hành âm thầm.

## 8. Placeholder và các cơ chế cấu hình khác

Một số cơ chế có thể cùng xuất hiện trong kho cấu hình nhưng có ý nghĩa khác nhau.

| Cơ chế | Ví dụ | Mục đích |
|---|---|---|
| Spring placeholder | <code>${platform.host}</code> | Tham chiếu thuộc tính khác trong Environment |
| Placeholder có mặc định | <code>${platform.host:localhost}</code> | Dùng giá trị dự phòng khi khóa không có |
| Biến môi trường | <code>PLATFORM_HOST</code> | Cung cấp giá trị từ môi trường tiến trình |
| Config Server overrides | <code>spring.cloud.config.server.overrides</code> | Thêm thuộc tính mặc định/ghi đè từ phía server theo chính sách Config Server |
| Giá trị mã hóa Config Server | <code>{cipher}...</code> | Biểu diễn giá trị được mã hóa và cần giải mã bằng cơ chế của Config Server |

Đặc biệt, <code>{cipher}</code> không phải placeholder <code>${...}</code>. Nó là dấu hiệu cho giá trị mã hóa trong cơ chế mã hóa/giải mã của Spring Cloud Config. Không thể thay khóa mã hóa bằng cách tạo một property có tên tương ứng, cũng không nên dùng placeholder để thay thế cơ chế quản lý bí mật.

Tương tự, <code>spring.cloud.config.server.overrides</code> là cơ chế cung cấp các thuộc tính từ phía Config Server theo quy tắc của nó. Nó không đơn giản là một cú pháp placeholder. Khi sử dụng đồng thời overrides và placeholder, hãy xem property source mà client nhận được và xác nhận giá trị cuối cùng.

## 9. Dùng placeholder với @Value và @ConfigurationProperties

### Với @Value

Có thể inject thuộc tính đã phân giải vào bean:

~~~java
@Component
public class InventoryClient {

    private final String baseUrl;

    public InventoryClient(
            @Value("${orders.inventory.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

<code>@Value</code> dùng placeholder của Spring để lấy giá trị trong Environment. Nếu thuộc tính chưa có hoặc placeholder bên trong giá trị không thể phân giải, quá trình tạo bean có thể thất bại.

### Với @ConfigurationProperties

Với nhóm cấu hình có cấu trúc, nên dùng <code>@ConfigurationProperties</code>:

~~~yaml
orders:
  inventory:
    base-url: https://${platform.inventory.host}:${platform.inventory.port}
    connect-timeout: 2s
~~~

~~~java
@ConfigurationProperties(prefix = "orders.inventory")
@Validated
public class InventoryProperties {

    @NotBlank
    private String baseUrl;

    @NotNull
    private Duration connectTimeout;

    // getters và setters
}
~~~

Binder của Spring Boot xử lý cấu hình và các placeholder theo cơ chế của Environment. Có thể kết hợp Bean Validation để phát hiện thiếu hoặc sai giá trị. Cần bảo đảm có dependency validation và đăng ký lớp properties bằng <code>@ConfigurationPropertiesScan</code> hoặc <code>@EnableConfigurationProperties</code> tùy ứng dụng.

Nếu cần kiểm tra giá trị sau khi bind, có thể log một số thuộc tính không nhạy cảm hoặc viết test cho bean cấu hình. Không log token, mật khẩu, URL có credential hoặc nội dung secret đã phân giải.

## 10. Kiểm tra nội dung thô và giá trị đã phân giải

Khi debug, cần biết mình đang quan sát lớp nào.

### Xem nội dung Config Server trả về

Gọi endpoint:

~~~http
GET http://config.internal:8888/orders-service/prod/release-2026.11
~~~

Response JSON chứa danh sách property source và các giá trị từ repository. Có thể thấy một giá trị vẫn ở dạng:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "propertySources": [
    {
      "name": "orders-service-prod.yml",
      "source": {
        "orders.inventory.base-url": "https://${platform.inventory.host}:8443"
      }
    }
  ]
}
~~~

Đây là nội dung thô server trả về. Nó hữu ích để xác nhận tệp và giá trị gốc mà Config Server tìm thấy.

### Xem giá trị ở phía client

Nếu Spring Boot Actuator được cấu hình và bảo vệ, endpoint <code>/actuator/env</code> có thể cho biết property source và giá trị của thuộc tính trong Environment. Endpoint <code>/actuator/configprops</code> giúp kiểm tra các nhóm cấu hình đã bind vào bean.

Các endpoint này có thể tiết lộ cấu hình nội bộ và thông tin nhạy cảm. Chỉ mở cho người vận hành có quyền, cấu hình masking phù hợp và không công khai qua mạng không tin cậy.

Một cách kiểm tra khác là viết integration test khởi tạo Spring Context với Config Client hoặc property source mô phỏng. Test nên xác nhận:

- Giá trị placeholder được phân giải đúng.
- Giá trị tham chiếu lấy từ nguồn dự kiến.
- Profile khác nhau tạo ra giá trị khác nhau khi cần.
- Giá trị bắt buộc thiếu thì validation thất bại.
- Biến môi trường hoặc tham số cục bộ không ghi đè ngoài dự kiến.

Không so sánh trực tiếp response JSON với giá trị cuối cùng của bean rồi kết luận có lỗi. Hai dữ liệu này thuộc hai giai đoạn khác nhau: response có thể chứa placeholder thô, còn Environment/bean có thể chứa giá trị đã phân giải.

## 11. Những lỗi thường gặp khi dùng placeholder

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Giá trị còn nguyên chuỗi ${...} | Consumer đọc response thô hoặc cơ chế resolve chưa được gọi | Kiểm tra đang đọc JSON trực tiếp hay dùng Spring Environment |
| Placeholder không tìm thấy khóa | Property source tham chiếu chưa được nạp hoặc sai tên | Kiểm tra khóa trong Environment và response server |
| URL trỏ tới host cũ | Biến môi trường hoặc nguồn có ưu tiên cao ghi đè | Kiểm tra nguồn cung cấp giá trị tham chiếu |
| Dùng giá trị mặc định ở production | Khóa tham chiếu bị thiếu nhưng có fallback | Kiểm tra profile, label và validation |
| Một số instance có kết quả khác nhau | Biến môi trường, profile hoặc nguồn cục bộ không đồng nhất | So sánh Environment từng instance |
| Lỗi khi khởi tạo bean | Placeholder bắt buộc thiếu hoặc tham chiếu vòng | Đọc nguyên nhân gốc trong exception |
| Config Server response không như dự kiến | Sai application/profile/label hoặc repository/search path | Kiểm tra request và propertySources |

Một số nguyên nhân cần phân biệt:

- **Sai tên khóa:** <code>platform.inventory.hostname</code> khác <code>platform.inventory.host</code>.
- **Sai phạm vi:** giá trị được khai báo trong tệp riêng của một dịch vụ khác.
- **Sai profile:** client không nạp tệp profile chứa giá trị tham chiếu.
- **Sai label:** client đọc phiên bản Git cũ chưa có thuộc tính mới.
- **Ghi đè cục bộ:** biến môi trường hoặc tham số chạy cung cấp giá trị khác.
- **Sai consumer:** chương trình đọc JSON thô mà không chạy cơ chế placeholder của Spring.

## 12. Quy trình thiết kế và xử lý placeholder

Khi thêm placeholder, hãy thực hiện theo thứ tự:

1. **Chọn khóa nguồn:** xác định thuộc tính nền như host, port, scheme hoặc timeout.
2. **Chọn phạm vi:** đặt khóa ở cấu hình chung, theo profile hay theo dịch vụ dựa trên quyền sở hữu thực tế.
3. **Khai báo tham chiếu:** dùng tên khóa rõ ràng, có namespace và tránh phụ thuộc vòng.
4. **Quyết định fallback:** chỉ thêm mặc định khi giá trị đó an toàn cho môi trường đang dùng.
5. **Kiểm tra nguồn và ưu tiên:** xác nhận property source chứa giá trị tham chiếu và không bị ghi đè ngoài ý muốn.
6. **Kiểm thử binding:** xác nhận giá trị trong Environment và bean cấu hình đúng như mong đợi.
7. **Kiểm tra sau phát hành:** so sánh các instance, profile và label nếu chạy nhiều replica.

Khi placeholder không được phân giải, bắt đầu từ biểu thức cụ thể đang lỗi. Xác định tên khóa mà nó tham chiếu, sau đó tìm khóa đó trong property source phía server và Environment phía client. Nếu server response không có khóa, kiểm tra repository, profile và label. Nếu response có khóa nhưng client không thấy, kiểm tra cách nạp Config Data và thứ tự ưu tiên. Nếu Environment có khóa nhưng bean vẫn sai, kiểm tra binding, kiểu dữ liệu và vòng đời bean.

## 13. Ví dụ hoàn chỉnh: cấu hình URL dịch vụ theo môi trường

Repository:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── orders-service-prod.yml
~~~

Cấu hình chung:

~~~yaml
# application.yml
platform:
  inventory:
    scheme: http
    host: inventory-service
    port: 8082
~~~

Cấu hình chung production:

~~~yaml
# application-prod.yml
platform:
  inventory:
    scheme: https
    host: inventory.prod.internal
    port: 8443
~~~

Cấu hình riêng orders:

~~~yaml
# orders-service.yml
orders:
  inventory:
    base-url: ${platform.inventory.scheme}://${platform.inventory.host}:${platform.inventory.port}
    connect-timeout: 2s
~~~

Client khai báo:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config.internal:8888"
  cloud:
    config:
      label: release-2026.11
~~~

Khi client lấy cấu hình, Config Server trả về các property source phù hợp với <code>orders-service</code>, profile <code>prod</code> và label phát hành. Giá trị thô của <code>orders.inventory.base-url</code> vẫn có thể là biểu thức placeholder. Khi Spring phân giải trong Environment, các khóa <code>platform.inventory.scheme</code>, <code>platform.inventory.host</code> và <code>platform.inventory.port</code> được lấy từ nguồn phù hợp. Giá trị cuối cùng dự kiến:

~~~text
https://inventory.prod.internal:8443
~~~

Nếu ứng dụng chạy với profile <code>dev</code>, các giá trị chung trong <code>application.yml</code> có thể tạo URL:

~~~text
http://inventory-service:8082
~~~

Nếu một biến môi trường ở client ghi đè <code>PLATFORM_INVENTORY_HOST</code>, URL có thể dùng host do biến môi trường cung cấp, tùy thứ tự ưu tiên. Vì thế, khi triển khai production, pipeline phải bảo đảm profile, label và các biến môi trường được kiểm soát nhất quán.

## 14. Checklist sử dụng placeholder

- [ ] Placeholder có tên khóa rõ ràng, nhất quán và có namespace.
- [ ] Property source chứa giá trị tham chiếu được nạp trong profile/label đang chạy.
- [ ] Đã xác định placeholder được phân giải ở Spring Environment phía client.
- [ ] Không dựa vào biến môi trường chỉ tồn tại trên Config Server để cung cấp giá trị cho client.
- [ ] Giá trị mặc định an toàn và phù hợp với môi trường; thuộc tính bắt buộc có validation.
- [ ] Không có chuỗi tham chiếu vòng hoặc quá nhiều tầng khó truy vết.
- [ ] Đã kiểm tra thứ tự ưu tiên và nguồn cung cấp giá trị tham chiếu.
- [ ] Đã phân biệt response thô của Config Server với giá trị sau khi Spring phân giải.
- [ ] Consumer không phải Spring có cơ chế xử lý placeholder theo hợp đồng rõ ràng.
- [ ] Không log secret hoặc giá trị nhạy cảm sau khi phân giải.
- [ ] Đã kiểm thử kết quả trên từng profile và label cần hỗ trợ.

Placeholder giúp cấu hình tập trung tránh lặp lại các giá trị nền và thể hiện quan hệ giữa các thuộc tính. Muốn kết quả ổn định, cần biết Config Server trả nội dung gì, Config Client phân giải trong Environment nào, property source nào cung cấp giá trị tham chiếu và nguồn nào có quyền ưu tiên. Khi các quan hệ đó được thiết kế và kiểm thử rõ ràng, cấu hình có thể tái sử dụng mà vẫn giữ đúng giá trị theo từng dịch vụ và môi trường.

