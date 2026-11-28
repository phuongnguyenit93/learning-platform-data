# Máy chủ trả cấu hình nhưng giá trị phía client không đúng dự kiến

Config Server có thể trả HTTP 200 và một Environment hợp lệ, nhưng ứng dụng vẫn đọc được giá trị khác với điều người vận hành mong đợi. Nguyên nhân thường nằm ở một trong các bước sau: client yêu cầu sai application/profile/label; property source có thứ tự ưu tiên khác dự kiến; một nguồn cấu hình khác ghi đè giá trị từ xa; client chưa refresh; hoặc giá trị đã nhận không bind vào bean theo cách mong muốn.

Cách chẩn đoán hiệu quả là lần theo cùng một thuộc tính từ đầu đến cuối: kiểm tra response của Config Server, xem property source nào cung cấp giá trị, xác định thứ tự ưu tiên ở phía client, rồi kiểm tra giá trị trong Spring Environment và bean thực tế. Đừng bắt đầu bằng việc sửa YAML ngay; trước hết phải xác định giá trị sai xuất hiện ở tầng nào.

Bài học này hướng dẫn quy trình đó với Spring Cloud Config Client và Server, gồm application/profile/label, thứ tự property source, local override, Config Data import, refresh, binding, conversion, YAML collection, composite repository và các endpoint chẩn đoán của Actuator.

Sau bài học, bạn có thể:

- Gọi đúng Environment endpoint để xác nhận Config Server đang trả gì.
- Đọc danh sách propertySources và tìm nguồn cung cấp một thuộc tính.
- Phân biệt thứ tự ưu tiên trong Config Server với thứ tự ưu tiên trong client.
- Phát hiện sai application name, profile, label hoặc cấu hình import.
- Tìm biến môi trường, system property, command-line argument hoặc local file đang ghi đè remote config.
- Xác định client chưa refresh hay bean chưa nhận giá trị mới.
- Chẩn đoán lỗi prefix, relaxed binding, kiểu dữ liệu, default và collection.
- Kiểm tra composite repository và revision của cấu hình.
- Dùng Actuator, log và test để xác minh giá trị cuối cùng mà không làm lộ secret.

## 1. Theo dấu một thuộc tính từ server tới bean

Một thuộc tính đi qua nhiều tầng trước khi được ứng dụng sử dụng:

~~~mermaid
flowchart TD
    A["Git / backend cấu hình"] --> B["Config Server EnvironmentRepository"]
    B --> C["Environment response"]
    C --> D["Config Client fetch"]
    D --> E["PropertySources trong Environment"]
    E --> F["Precedence và override"]
    F --> G["Binder / @Value / ConfigurationProperties"]
    G --> H["Bean và hành vi runtime"]
~~~

Hãy tách vấn đề thành bốn câu hỏi:

1. **Server có trả đúng dữ liệu không?** Kiểm tra application, profile, label và giá trị trong response.
2. **Client có nhận đúng response đó không?** Kiểm tra URL, log fetch, revision và thời điểm startup/refresh.
3. **Property source nào thắng?** Kiểm tra các nguồn trùng khóa và thứ tự ưu tiên.
4. **Bean có nhận đúng kiểu và giá trị không?** Kiểm tra prefix, binding, conversion, default và lifecycle của bean.

Ví dụ, Config Server trả <code>orders.reservation.timeout=2s</code>, nhưng ứng dụng đọc được <code>5s</code>. Có thể remote response đúng nhưng một nguồn local đang thắng; cũng có thể bean đã được tạo trước lần refresh và chưa được cập nhật. Chỉ so sánh file YAML ở Git sẽ không xác định được nguyên nhân.

## 2. Gọi trực tiếp Environment endpoint của Config Server

Config Server cung cấp endpoint dạng:

~~~http
GET /{application}/{profile}/{label}
~~~

Ví dụ kiểm tra orders-service với profile prod và label phát hành cụ thể:

~~~bash
curl --fail --silent --show-error \
  "https://config.internal/orders-service/prod/release-2026.11"
~~~

Nếu không chỉ định label, Config Server dùng label mặc định được cấu hình. Để điều tra, nên truyền label tường minh nhằm tránh vô tình đọc branch mặc định đang thay đổi.

Response JSON có các trường quan trọng:

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
        "orders.reservation.timeout": "2s"
      }
    },
    {
      "name": "orders-service.yml",
      "source": {
        "orders.reservation.timeout": "3s"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "orders.reservation.timeout": "5s"
      }
    }
  ]
}
~~~

Đây là ví dụ minh họa cấu trúc response. Khi kiểm tra response thật, hãy xác nhận:

- <code>name</code> đúng application mà client yêu cầu.
- <code>profiles</code> chứa profile mong đợi.
- <code>label</code> đúng branch, tag hoặc commit.
- <code>version</code> hoặc metadata revision khớp bản phát hành nếu backend cung cấp.
- <code>propertySources</code> có chứa thuộc tính cần tìm.
- <code>source</code> của mỗi property source có giá trị gì.
- Tên property source giúp xác định file, context hoặc backend nào cung cấp giá trị.

Nếu response không chứa thuộc tính, hãy điều tra server/repository và cách chọn application/profile/label. Nếu response có giá trị đúng, chuyển sang kiểm tra phía client; sửa Git thêm lần nữa có thể không giải quyết được vấn đề.

Không in toàn bộ response ra ticket hoặc log chia sẻ nếu Environment có secret đã giải mã. Khi cần so sánh, chỉ trích đúng property không nhạy cảm hoặc che giá trị bí mật.

## 3. Đọc thứ tự propertySources

Trong Spring Environment, property source có độ ưu tiên cao hơn sẽ được tra cứu trước. Với response Config Server, thứ tự danh sách <code>propertySources</code> thể hiện thứ tự các nguồn cấu hình server ghép cho Environment.

Giả sử response chứa cùng một khóa:

| Thứ tự trong response | Property source | Giá trị |
|---:|---|---|
| 1 | <code>orders-service-prod.yml</code> | <code>2s</code> |
| 2 | <code>orders-service.yml</code> | <code>3s</code> |
| 3 | <code>application.yml</code> | <code>5s</code> |

Trong ví dụ, giá trị từ nguồn đầu tiên có ưu tiên cao nhất trong nhóm property source được trả về, nên server Environment cho <code>orders.reservation.timeout</code> là <code>2s</code>.

Đừng chỉ xem một file cụ thể. Config Server có thể ghép nhiều file và nhiều context:

- <code>application.yml</code> dùng chung.
- <code>application-prod.yml</code> dùng chung theo profile.
- <code>orders-service.yml</code> riêng cho ứng dụng.
- <code>orders-service-prod.yml</code> riêng cho ứng dụng và profile.
- Các nguồn bổ sung từ composite repository hoặc server-side overrides.

Thứ tự thực tế phụ thuộc cấu hình repository, profile và phiên bản. Dùng response Environment làm bằng chứng thay vì tự suy ra từ tên file.

### Kiểm tra từng nguồn chứa khóa trùng

Lập bảng các giá trị của cùng một property trong response:

| Nguồn | Có property? | Giá trị |
|---|---:|---|
| orders-service-prod.yml | Có | 2s |
| orders-service.yml | Có | 3s |
| application-prod.yml | Có | 4s |
| application.yml | Có | 5s |

Từ bảng này có thể thấy property bị khai báo ở nhiều nơi. Hãy quyết định nguồn nào nên sở hữu giá trị đó và loại bỏ các khai báo dư thừa nếu chúng gây nhầm lẫn. Giữ một giá trị ở một nơi có chủ đích giúp review và rollback dễ hơn.

## 4. Xác nhận application name, profile và label mà client thực sự dùng

Một trong những nguyên nhân phổ biến nhất là client yêu cầu một Environment khác với tài liệu mà người vận hành đang xem.

Cấu hình ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  cloud:
    config:
      label: release-2026.11
  config:
    import: "configserver:https://config.internal"
~~~

Kiểm tra từng giá trị:

| Thành phần | Nguồn cần xác minh | Sai lệch thường gặp |
|---|---|---|
| Application | <code>spring.application.name</code> hoặc tên Config Client được cấu hình | Tên artifact, tên service discovery và config name khác nhau |
| Profile | <code>spring.profiles.active</code>, profile group hoặc môi trường triển khai | Pod đang chạy profile dev/staging thay vì prod |
| Label | <code>spring.cloud.config.label</code> | Client đọc main/master trong khi operator sửa release tag |
| Config Server URI | <code>spring.config.import</code> hoặc URI của client | Client trỏ tới server/cluster khác |
| Context path | URL, gateway và server base path | Request tới route khác hoặc gateway rewrite sai |

Có thể khai báo tên Config Client riêng bằng thuộc tính client tương ứng nếu ứng dụng không dùng trực tiếp <code>spring.application.name</code>. Hãy kiểm tra cấu hình hiệu lực và URL request thay vì chỉ nhìn file cấu hình đóng gói.

### Profile được xác định trước khi lấy remote config

Config Client cần biết application và profile để yêu cầu Environment. Không nên kỳ vọng một giá trị <code>spring.profiles.active</code> chỉ nằm trong response remote có thể quyết định ngược lại profile dùng để tạo chính request lấy response đó.

Hãy đặt profile cần dùng ở nguồn bootstrap có sẵn trước khi Config Data import chạy, chẳng hạn biến môi trường hoặc cấu hình triển khai. Sau đó kiểm tra trường <code>profiles</code> trong response để xác nhận client đã yêu cầu đúng profile.

### Profile group và profile bổ sung

Spring Boot có thể kích hoạt nhiều profile thông qua profile group, <code>spring.profiles.include</code> hoặc cấu hình triển khai. Khi đó Config Server có thể nhận nhiều profile và ghép thêm property source. Hãy kiểm tra danh sách profile thực tế thay vì giả định chỉ có một profile.

## 5. Xác nhận Config Data import đã nạp đúng nguồn

Với Config Data API, client thường khai báo:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal"
~~~

Nếu import có tiền tố <code>optional:</code>:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal"
~~~

client có thể tiếp tục startup khi Config Server không truy cập được. Khi đó, ứng dụng có thể chạy bằng file local, environment variable hoặc default mà người vận hành tưởng rằng đã được lấy từ remote.

Các bước kiểm tra:

1. Xác nhận import URI có đúng host, port, scheme và context path.
2. Xác nhận không vô tình dùng <code>optional:</code> trong khi remote config là bắt buộc.
3. Kiểm tra startup log có ghi nhận fetch Config Server thành công hay bỏ qua nguồn.
4. Kiểm tra application/profile/label mà client gửi.
5. Xác nhận response revision đúng bản dự kiến.
6. Kiểm tra có nhiều Config Server import hoặc nhiều URI fallback hay không.

Nếu dự án dùng legacy bootstrap, xác định rõ cơ chế đó còn được bật và thuộc tính bootstrap được đọc đúng thời điểm. Không trộn cách chẩn đoán Config Data API với bootstrap legacy mà không kiểm tra phiên bản và dependency.

## 6. Kiểm tra nguồn local đang ghi đè remote config

Ngay cả khi Config Server trả đúng giá trị, client vẫn có thể dùng giá trị khác do property source khác có độ ưu tiên cao hơn.

Các nguồn cần kiểm tra:

- Command-line arguments.
- Java system properties như <code>-Dorders.reservation.timeout=5s</code>.
- Environment variables như <code>ORDERS_RESERVATION_TIMEOUT=5s</code>.
- File <code>application.yml</code> hoặc file profile trong artifact.
- External config file được mount vào container.
- Profile-specific local file.
- Test property, <code>@DynamicPropertySource</code> hoặc <code>@TestPropertySource</code>.
- Giá trị default trong <code>@Value</code> placeholder hoặc code tự gán.

Ví dụ triển khai container có:

~~~text
ORDERS_RESERVATION_TIMEOUT=5s
~~~

trong khi Config Server trả:

~~~yaml
orders:
  reservation:
    timeout: 2s
~~~

Ứng dụng có thể nhận <code>5s</code> nếu nguồn environment variable đang có độ ưu tiên cao hơn trong cấu hình precedence hiện tại.

### Kiểm tra giá trị và nguồn trong Actuator

Nếu endpoint được expose và bảo vệ, có thể truy vấn:

~~~http
GET /actuator/env/orders.reservation.timeout
~~~

Endpoint Environment có thể hiển thị giá trị hiệu lực và property source cung cấp giá trị đó, tùy phiên bản và cấu hình masking. Dùng kết quả này để xác định property source nào thắng.

Không mở <code>/actuator/env</code> công khai. Các giá trị nhạy cảm phải được mask; chỉ cấp quyền xem chi tiết cho người vận hành được phép.

### Remote override policy của Spring Cloud Config

Mặc định, remote property source thường được bảo vệ khỏi việc ghi đè bởi local property source. Nếu muốn local configuration được phép override remote, server có thể cấp quyền thông qua các thuộc tính trong remote configuration:

~~~yaml
spring:
  cloud:
    config:
      allow-override: true
      override-none: true
~~~

<code>allow-override</code> phải được đặt trong remote property source theo chính sách Spring Cloud Config; đặt nó tùy tiện trong local client không tự cấp quyền override. <code>override-none</code> điều chỉnh mức độ local property source được phép thắng. Có thêm lựa chọn liên quan đến system properties và command-line/environment overrides; hành vi chi tiết cần đối chiếu phiên bản Spring Cloud đang dùng.

Đừng bật override rộng chỉ để xử lý một property sai. Trước tiên xác định nguồn nào đang ghi đè và lý do nguồn đó tồn tại. Một override ngoài ý muốn có thể che cấu hình production trong thời gian dài.

## 7. Kiểm tra server-side overrides và composite repository

Config Server có thể thêm các giá trị override áp dụng rộng cho nhiều ứng dụng qua cấu hình server, ví dụ <code>spring.cloud.config.server.overrides</code>. Đây có thể là nguồn có ưu tiên cao trong Environment được trả về.

Nếu response chứa giá trị khác với file Git đang xem:

1. Kiểm tra <code>propertySources</code> xem có nguồn override riêng không.
2. Kiểm tra server-wide overrides và profile cấu hình của Config Server.
3. Nếu dùng composite repository, kiểm tra từng backend và thứ tự repository.
4. Xác nhận backend nào cung cấp cùng property key.
5. Kiểm tra Config Server replica có cùng cấu hình server-side không.

Trong composite repository, một property có thể tồn tại đồng thời ở Git, Vault hoặc Consul. Thứ tự repository được cấu hình quyết định nguồn thắng khi trùng khóa. Không giả định Git luôn ưu tiên hơn Vault hoặc ngược lại.

Hãy ghi lại property source name, backend, revision và thứ tự để xác định nguồn thắng. Nếu nhiều backend cùng sở hữu một property, cần quy định rõ ownership để tránh thay đổi ở backend có ưu tiên thấp nhưng không ảnh hưởng runtime.

## 8. Phân biệt cấu hình server mới với Environment cũ trong client

Config Server trả giá trị mới không có nghĩa mọi client đang chạy đã nhận giá trị đó. Config Client thường lấy cấu hình khi startup; thay đổi ở Git không tự động cập nhật bean trong mọi instance nếu chưa có cơ chế refresh.

Ví dụ:

1. Client khởi động lúc 09:00 và nhận timeout 3s.
2. Operator cập nhật Git lúc 09:10 thành timeout 2s.
3. Gọi trực tiếp Config Server lúc 09:11 thấy timeout 2s.
4. Client vẫn đọc timeout 3s vì chưa fetch lại hoặc chưa áp dụng refresh.

Kiểm tra:

- Client đã nhận refresh request hoặc Bus event chưa?
- Client fetch lại Config Server thành công không?
- Refresh có dùng đúng application/profile/label không?
- Environment sau refresh có property source mới không?
- Bean đọc property có được rebind hoặc tạo lại không?
- Instance nào chưa refresh trong cụm?

### Refresh cục bộ

Có thể gọi endpoint nếu ứng dụng expose và bảo vệ nó:

~~~http
POST /actuator/refresh
~~~

Sau thao tác, kiểm tra response, log, Environment và bean. HTTP 200 của endpoint không tự chứng minh tất cả thành phần nghiệp vụ đã dùng giá trị mới.

### Refresh qua Spring Cloud Bus

Bus refresh có thể phát sự kiện tới nhiều client:

~~~http
POST /actuator/busrefresh
~~~

Một event phát thành công không có nghĩa mọi instance đã hoàn tất fetch và rebind. Theo dõi kết quả theo từng instance; nếu cần xác minh, dùng metric/log hoặc endpoint chẩn đoán nội bộ.

## 9. Environment đã đổi nhưng bean vẫn giữ giá trị cũ

Một ứng dụng có thể đã cập nhật Spring Environment nhưng bean vẫn giữ giá trị cũ do cách bean được tạo và quản lý.

Ví dụ:

~~~java
@Component
public class ReservationService {

    @Value("${orders.reservation.timeout:1s}")
    private Duration timeout;

    public Duration timeout() {
        return timeout;
    }
}
~~~

Một singleton thông thường nhận <code>@Value</code> tại thời điểm bean được tạo. Nó không tự động chạy lại injection mỗi khi Environment thay đổi. Với bean cần cập nhật động, dùng cơ chế refresh phù hợp, ví dụ <code>@RefreshScope</code>, hoặc dùng <code>@ConfigurationProperties</code> và kiểm tra cơ chế rebinding trong phiên bản đang sử dụng.

Ví dụ:

~~~java
@Component
@RefreshScope
public class ReservationService {

    @Value("${orders.reservation.timeout:1s}")
    private Duration timeout;

    public Duration timeout() {
        return timeout;
    }
}
~~~

Khi refresh scope được làm mới, target bean có thể được tạo lại ở lần truy cập tiếp theo. Điều đó có thể kéo theo khởi tạo lại resource hoặc kết nối; hãy kiểm tra side effect trước khi áp dụng cho bean nặng.

### Kiểm tra bean có đang dùng Environment trực tiếp hay không

Các trường hợp dễ gây nhầm:

- Bean đã copy property vào field hoặc constructor một lần.
- Static field không được Spring inject lại.
- Code gọi <code>System.getenv()</code> trực tiếp thay vì đọc Spring Environment.
- Tự tạo object bằng <code>new</code> nên object không thuộc Spring container.
- Cache ứng dụng giữ giá trị cũ sau khi bean đã được cập nhật.
- Một HTTP client/pool được tạo với timeout cũ và không tự tái cấu hình.

Nếu Environment đúng nhưng hành vi vẫn sai, kiểm tra bean và resource thực tế. Không tiếp tục thay file Git khi vấn đề nằm ở lifecycle của object.

## 10. Kiểm tra prefix, tên property và relaxed binding

Spring Boot hỗ trợ relaxed binding cho nhiều cách viết property, nhưng prefix và cấu trúc dữ liệu vẫn phải khớp với bean.

Ví dụ cấu hình:

~~~yaml
orders:
  reservation:
    max-attempts: 3
    connect-timeout: 500ms
~~~

Bean:

~~~java
@ConfigurationProperties(prefix = "orders.reservation")
public class ReservationProperties {
    private int maxAttempts;
    private Duration connectTimeout;

    // getters và setters
}
~~~

Một số điểm cần kiểm tra:

- Prefix có đúng <code>orders.reservation</code> không?
- Field có setter/getter hoặc constructor binding phù hợp không?
- Tên property có bị viết sai như <code>max-attempt</code> thay vì <code>max-attempts</code> không?
- Bean có được đăng ký bằng <code>@ConfigurationPropertiesScan</code> hoặc <code>@EnableConfigurationProperties</code> không?
- Có một bean khác dùng prefix khác hoặc được inject nhầm không?
- Có custom converter hoặc property editor thay đổi cách chuyển kiểu không?

Nếu dùng <code>@Value</code>, placeholder cũng cần đúng key. Ví dụ:

~~~java
@Value("${orders.reservation.max-attempts:1}")
private int maxAttempts;
~~~

Nếu property không tồn tại, default <code>1</code> sẽ được dùng. Người đọc có thể tưởng server đã trả <code>1</code>, trong khi thực tế client không tìm thấy property và placeholder đã dùng default.

Hãy phân biệt rõ “property tồn tại với giá trị 1” và “property không tồn tại nên default bằng 1”.

## 11. Kiểm tra conversion và đơn vị của giá trị

Một property có thể được lấy đúng nhưng được chuyển kiểu theo quy tắc khác mong đợi.

Ví dụ:

| Property | Giá trị | Ý nghĩa cần kiểm tra |
|---|---|---|
| <code>timeout</code> kiểu String | <code>2000</code> | Chuỗi không có đơn vị |
| <code>timeout</code> kiểu Duration | <code>2000</code> | Số không đơn vị thường được hiểu theo millisecond mặc định |
| <code>timeout</code> kiểu Duration | <code>2s</code> | Hai giây |
| <code>payload-size</code> kiểu DataSize | <code>10MB</code> | Mười megabyte |
| <code>enabled</code> kiểu boolean | <code>false</code> | Boolean false, không phải thiếu property |

Nên dùng giá trị có đơn vị tường minh như <code>2s</code>, <code>500ms</code>, <code>10MB</code> cho các kiểu <code>Duration</code> và <code>DataSize</code>. Nếu dùng số không đơn vị, xác nhận default unit hoặc annotation như <code>@DurationUnit</code> trong code.

Với enum, kiểm tra tên constant và converter. Với số, kiểm tra range và overflow. Với boolean, kiểm tra placeholder/default và nguồn override. Giá trị trong JSON response có thể là chuỗi, nhưng bean nhận kiểu đã chuyển đổi.

## 12. Kiểm tra cách merge map, list và YAML document

Không phải mọi cấu trúc YAML đều được ghép theo cách người viết mong muốn.

Ví dụ cấu hình chung:

~~~yaml
orders:
  retry:
    max-attempts: 3
    delay: 200ms
  endpoints:
    - https://node-a.internal
    - https://node-b.internal
~~~

Cấu hình profile:

~~~yaml
orders:
  retry:
    delay: 500ms
  endpoints:
    - https://node-prod.internal
~~~

Khi các property source được ghép, map/nested property có thể nhận giá trị từ nhiều nguồn theo từng key, nhưng list trong Spring Boot thường được thay thế như một đơn vị bởi nguồn có ưu tiên cao hơn, không tự động nối thêm phần tử của list thấp hơn.

Trong ví dụ, list endpoint có thể chỉ còn phần tử <code>https://node-prod.internal</code>, trong khi <code>max-attempts</code> vẫn nhận giá trị 3 từ nguồn thấp hơn và <code>delay</code> nhận 500ms từ nguồn profile.

Nếu muốn append danh sách, cần thiết kế rõ cơ chế ghép hoặc tạo cấu hình hoàn chỉnh trong nguồn có ưu tiên cao. Không giả định YAML merge key hoặc cú pháp anchor có thể ghép property source giữa nhiều file Config Server.

Ngoài ra, kiểm tra:

- Thụt lề YAML.
- Dấu nháy và kiểu scalar.
- Key bị lặp trong cùng document.
- Dùng <code>spring.config.activate.on-profile</code> ở sai ngữ cảnh.
- YAML document separator <code>---</code> và khả năng parser trong luồng Config Server.
- Tên file profile-specific có đúng quy ước không.

## 13. Xác định client đang đọc revision nào

Một cụm có thể chứa nhiều instance khởi động ở các thời điểm khác nhau hoặc nhận refresh không đồng đều. Vì vậy, cùng một service có thể tạm thời chạy với các revision khác nhau.

Ghi nhận các thông tin sau cho mỗi instance:

- Application name.
- Active profiles.
- Config label.
- Revision/commit nếu backend trả metadata.
- Thời điểm fetch gần nhất.
- Kết quả fetch/refresh gần nhất.
- Config Server instance đã phục vụ request.
- Giá trị hiệu lực của một số property không nhạy cảm.

Nếu server trả đúng label nhưng client đang dùng label khác, kiểm tra cấu hình client và deployment environment. Nếu các instance dùng cùng label nhưng revision khác nhau, kiểm tra branch mutable, cache/working copy của Config Server, load balancer và trạng thái repository replica.

Ưu tiên label bất biến như commit hash hoặc tag phát hành khi cần tái lập chính xác. Với branch đang thay đổi, hai lần request cùng tên branch có thể nhận nội dung khác nhau ở hai thời điểm.

## 14. Dùng Actuator để tìm nguồn giá trị cuối cùng

Các endpoint hữu ích:

| Endpoint | Mục đích |
|---|---|
| <code>/actuator/env/{property}</code> | Xem property value và property source có liên quan |
| <code>/actuator/env</code> | Kiểm tra Environment và property sources |
| <code>/actuator/configprops</code> | Xem các bean đã bind từ <code>@ConfigurationProperties</code> |
| <code>/actuator/refresh</code> | Yêu cầu refresh khi endpoint được expose |
| <code>/actuator/health</code> | Xác minh trạng thái ứng dụng và dependency theo health indicator đã bật |

Cấu hình ví dụ để chỉ hiển thị giá trị khi đã xác thực:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
    configprops:
      show-values: when-authorized
~~~

Tùy phiên bản Spring Boot, giá trị mặc định có thể được mask hoặc ẩn. Giữ endpoint trong mạng quản trị, yêu cầu authorization và không mở rộng quyền chỉ để debug nhanh.

So sánh kết quả theo ba điểm:

1. Config Server Environment response.
2. Config Client Environment.
3. Bean đã bind trong <code>/actuator/configprops</code> hoặc qua code kiểm tra nội bộ.

Nếu server và client Environment giống nhau nhưng bean khác, tập trung vào binding/lifecycle. Nếu client Environment khác server, tập trung vào import, property precedence, refresh hoặc Config Client URI.

## 15. Tăng log có chọn lọc khi cần

Có thể tăng log tạm thời cho các package liên quan tới Config Client và Config Data:

~~~yaml
logging:
  level:
    org.springframework.cloud.config.client: DEBUG
    org.springframework.boot.context.config: DEBUG
~~~

Tên logger và mức log hữu ích phụ thuộc phiên bản. Sau khi thu thập đủ bằng chứng, đưa log về mức bình thường để tránh tăng lượng log và lộ metadata không cần thiết.

Tìm các thông tin:

- Config Server URI mà client đang gọi.
- Application/profile/label được yêu cầu.
- Import được xử lý hay bị bỏ qua.
- Fetch thành công, retry hoặc thất bại.
- Property source được nạp.
- Refresh event được nhận và hoàn tất hay không.
- Lỗi bind/conversion hoặc validation.

Không bật TRACE lâu dài trên production nếu chưa kiểm tra nội dung có thể được ghi. Tránh log response body, password, token hoặc giá trị Environment.

## 16. Quy trình chẩn đoán theo thứ tự

Khi người dùng báo “server trả đúng nhưng client đọc sai”, thực hiện theo thứ tự dưới đây:

| Bước | Việc kiểm tra | Kết luận có thể rút ra |
|---:|---|---|
| 1 | Gọi Environment endpoint với application/profile/label tường minh | Xác nhận dữ liệu server |
| 2 | Tìm property trong từng property source | Xác định nguồn server thắng |
| 3 | Kiểm tra revision, label và Config Server instance | Phát hiện branch/revision lệch |
| 4 | Xác nhận client URI, application name và active profiles | Phát hiện request sai context |
| 5 | Kiểm tra Config Data import và startup logs | Phát hiện remote source không được nạp |
| 6 | Kiểm tra <code>/actuator/env/{property}</code> trên client | Xác định property source phía client thắng |
| 7 | Kiểm tra env var, system property, command line và local files | Tìm local override |
| 8 | Xác nhận client đã refresh sau thay đổi | Phát hiện Environment stale |
| 9 | Kiểm tra <code>/actuator/configprops</code> và bean runtime | Phát hiện bind/lifecycle |
| 10 | Kiểm tra kiểu dữ liệu, default, map/list và custom converter | Phát hiện conversion/merge |
| 11 | Kiểm tra composite repository và server-side overrides | Phát hiện backend precedence |
| 12 | Sửa đúng nguồn, refresh một canary và xác minh | Xác nhận kết quả trước rollout |

Quy trình này tránh việc sửa cùng một property ở nhiều file mà không biết nguồn nào thực sự có hiệu lực.

## 17. Ví dụ điều tra hoàn chỉnh

Tình huống: Config Server trả <code>orders.reservation.timeout=2s</code>, nhưng orders-service vẫn dùng 5 giây.

**Bước 1: Xác nhận server.**

Gọi:

~~~bash
curl --fail --silent --show-error \
  "https://config.internal/orders-service/prod/release-2026.11"
~~~

Response có property source <code>orders-service-prod.yml</code> với giá trị <code>2s</code>.

**Bước 2: Kiểm tra client Environment.**

Gọi endpoint nội bộ đã bảo vệ:

~~~http
GET /actuator/env/orders.reservation.timeout
~~~

Giả sử response cho thấy property source từ system environment cung cấp <code>5s</code>. Từ đó xác định nguyên nhân là local override, không phải Config Server.

**Bước 3: Kiểm tra deployment.**

Tìm thấy biến:

~~~text
ORDERS_RESERVATION_TIMEOUT=5s
~~~

được khai báo trong deployment manifest.

**Bước 4: Quyết định nguồn sở hữu.**

Nếu production cần dùng giá trị từ Config Server, cập nhật hoặc loại bỏ biến môi trường theo quy trình release. Nếu biến môi trường được thiết kế để override remote, ghi rõ quy tắc đó trong tài liệu vận hành.

**Bước 5: Xác minh runtime.**

Sau khi rollout hoặc refresh phù hợp, kiểm tra lại Environment và bean. Chỉ xác nhận hoàn tất khi giá trị hiệu lực là 2 giây và luồng nghiệp vụ thực sự sử dụng giá trị đó.

Nếu <code>/actuator/env</code> đã trả 2s nhưng bean vẫn 5s, quay lại kiểm tra binding, <code>@RefreshScope</code>, rebinding và resource được tạo từ bean.

## 18. Những lỗi dễ bị chẩn đoán nhầm

| Triệu chứng | Nhầm lẫn thường gặp | Kiểm tra đúng |
|---|---|---|
| Git có giá trị mới, server response cũ | Cho rằng server luôn đọc remote Git mới nhất | Label, clone/refresh rate, revision và server replica |
| Server response đúng, client Environment cũ | Cho rằng HTTP 200 startup trước đó là đủ | Client import, refresh và property source |
| Client Environment đúng, bean sai | Tiếp tục sửa YAML | Binding, bean lifecycle và cache |
| Property bị ghi đè | Chỉ tìm trong Git | Env var, system property, CLI, local file và server overrides |
| Profile-specific không có hiệu lực | Sửa nhầm file application chung | Active profiles và request profile |
| Label không đúng | Chỉ nhìn branch trên Git UI | Label thực tế trong request/response |
| Duration sai đơn vị | Đổi số trong YAML mà không xem kiểu Java | Duration conversion và unit |
| List bị mất phần tử | Kỳ vọng list được append giữa các nguồn | Quy tắc list replacement |
| Placeholder dùng default | Cho rằng server đã trả default đó | Kiểm tra property có tồn tại hay không |
| Bus refresh thành công nhưng bean cũ | Cho rằng publisher 200 là tất cả instance đã xong | Fetch/rebind kết quả từng instance |

## 19. Checklist trước khi kết luận Config Server trả sai

- [ ] Đã gọi Environment endpoint với application, profile và label tường minh.
- [ ] Đã kiểm tra <code>name</code>, <code>profiles</code>, <code>label</code> và revision.
- [ ] Đã tìm property trong mọi property source và xác định nguồn thắng.
- [ ] Đã xác minh Config Client đang gọi đúng Config Server URI.
- [ ] Đã xác nhận Config Data import thực sự được nạp.
- [ ] Đã kiểm tra biến môi trường, system properties, command line và local files.
- [ ] Đã kiểm tra server-side overrides và composite repository order.
- [ ] Đã xác nhận client đã fetch/refresh sau lần thay đổi gần nhất.
- [ ] Đã so sánh client Environment với Config Server response.
- [ ] Đã so sánh Environment với bean đã bind.
- [ ] Đã kiểm tra prefix, field name, converter, default và validation.
- [ ] Đã kiểm tra quy tắc merge map/list và cú pháp YAML.
- [ ] Đã kiểm tra revision và trạng thái giữa các instance.
- [ ] Actuator endpoint được bảo vệ và secret được mask.
- [ ] Log không ghi toàn bộ Environment, token hoặc secret.
- [ ] Đã refresh hoặc rollout một canary và xác minh hành vi thực tế trước khi mở rộng.

Khi Config Server trả cấu hình nhưng ứng dụng dùng giá trị khác, hãy xác định điểm đầu tiên mà dữ liệu không còn khớp: response server, Environment client hay bean runtime. Kiểm tra application/profile/label và property source trước, sau đó tìm local override, refresh chưa hoàn tất hoặc lỗi binding. Việc so sánh có hệ thống ba tầng này giúp sửa đúng nguồn sở hữu của thuộc tính, tránh thay đổi cấu hình ở nhiều nơi và xác nhận được giá trị mà ứng dụng thực sự đang sử dụng.

