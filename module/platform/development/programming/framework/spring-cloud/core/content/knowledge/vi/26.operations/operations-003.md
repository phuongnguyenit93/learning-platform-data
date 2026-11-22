# Đánh đổi giữa dừng sớm và dùng cấu hình dự phòng

> **Chương:** Vận hành
> **Module:** `SPRING_CLOUD_CORE` — hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình bên ngoài và tương thích phiên bản với Spring Boot. Người học tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử, vận hành các abstraction chung.
> **Trọng tâm:** Khi ứng dụng lấy cấu hình từ Spring Cloud Config Server, lỗi kết nối lúc khởi động đặt ra lựa chọn: dừng ứng dụng để tránh chạy với cấu hình thiếu, hay tiếp tục bằng cấu hình dự phòng. Bài học phân tích điều kiện chọn fail-fast hoặc optional import, cách kết hợp retry và nhiều Config Server, thiết kế local fallback an toàn và kiểm chứng trạng thái cấu hình trước khi đưa service vào nhận traffic.

## 1. Vì sao phải chọn giữa fail-fast và fallback?

Ứng dụng Spring Cloud thường lấy cấu hình từ nhiều nguồn: file đóng gói cùng ứng dụng, biến môi trường, tham số khởi chạy, Config Server, configuration tree hoặc secret store. Cấu hình bên ngoài giúp thay đổi hành vi theo môi trường mà không cần đóng gói lại ứng dụng. Đổi lại, lúc khởi động ứng dụng có thể phụ thuộc vào một dịch vụ mạng khác.

Giả sử một service cần các giá trị sau:

- địa chỉ và timeout của downstream;
- tên topic hoặc queue;
- giới hạn retry;
- feature flag;
- cấu hình kết nối database;
- thông tin xác thực được cấp từ secret store.

Nếu Config Server tạm thời không truy cập được, service có hai hướng xử lý.

**Fail-fast:** không lấy được cấu hình bắt buộc thì không khởi động. Cách này ngăn một instance chạy với giá trị thiếu, mặc định hoặc sai môi trường. Nó phù hợp khi cấu hình là điều kiện tiên quyết để service hoạt động an toàn.

**Fallback:** cho phép khởi động bằng cấu hình local hoặc nguồn dự phòng khi Config Server không khả dụng. Cách này có thể duy trì một số chức năng trong thời gian gián đoạn, nhưng chỉ an toàn nếu bộ cấu hình dự phòng đủ dùng và không làm giảm bảo mật hoặc tính đúng đắn của nghiệp vụ.

Không có lựa chọn nào tốt cho mọi ứng dụng. Cần xác định hậu quả khi thiếu từng nhóm cấu hình, khả năng vận hành ở chế độ suy giảm và cách xác nhận service đã sẵn sàng nhận traffic.

### Kết quả học tập

Sau bài này, người học có thể:

1. phân biệt fail-fast, optional import, retry và fallback;
2. cấu hình Config Client với `spring.config.import`;
3. lựa chọn cấu hình bắt buộc hoặc tùy chọn theo mức độ quan trọng;
4. thiết kế giá trị local mặc định và hiểu thứ tự ưu tiên property source;
5. kết hợp fail-fast với retry/backoff;
6. sử dụng nhiều Config Server và hiểu cách chọn server dự phòng;
7. phân biệt lỗi kết nối, timeout, xác thực, lỗi server và cấu hình rỗng;
8. kiểm tra cấu hình bắt buộc trước khi service nhận traffic;
9. kiểm thử các kịch bản Config Server gián đoạn;
10. xây dựng quy trình rollback và vận hành khi cấu hình ngoài không sẵn sàng.

## 2. Hiểu đúng các thuật ngữ

### 2.1. Fail-fast

Fail-fast nghĩa là ứng dụng kết thúc quá trình khởi động khi không lấy được cấu hình bắt buộc từ Config Server. Với cơ chế Config Data hiện nay, cách đơn giản là khai báo import không có tiền tố `optional:`.

```properties
spring.config.import=configserver:http://config.internal:8888
```

Nếu Config Server không thể cung cấp cấu hình, Config Client làm thất bại quá trình khởi động thay vì bỏ qua nguồn đó.

Với cơ chế bootstrap cũ, thuộc tính `spring.cloud.config.fail-fast=true` yêu cầu Config Client ném exception khi không kết nối được Config Server. Với Config Data import, bỏ `optional:` là cách tương đương được tài liệu hiện hành hướng dẫn.

### 2.2. Optional import

Optional import cho phép ứng dụng tiếp tục khởi động nếu nguồn cấu hình được đánh dấu tùy chọn không tải được:

```properties
spring.config.import=optional:configserver:http://config.internal:8888
```

Khi Config Server không truy cập được, các nguồn cấu hình local và những nguồn khác vẫn có thể cung cấp giá trị. Đây là một cơ chế cho phép bỏ qua nguồn import bị lỗi; nó không tự tạo ra một bản sao cấu hình gần nhất và cũng không tự bảo đảm mọi property bắt buộc đã có.

### 2.3. Retry

Retry thử lại một thao tác thất bại trước khi kết luận không thể lấy cấu hình. Nó xử lý lỗi tạm thời như Config Server đang khởi động, mạng chập chờn hoặc kết nối timeout ngắn.

Retry không thay thế fail-fast hoặc fallback:

- fail-fast quyết định ứng dụng có được phép khởi động khi không lấy được cấu hình hay không;
- retry quyết định có thử lại trước khi đưa ra kết luận hay không;
- fallback quyết định nguồn nào được dùng khi nguồn ưu tiên không sẵn sàng.

### 2.4. Fallback configuration

Fallback là một nguồn cấu hình dự phòng có thể được dùng khi nguồn ưu tiên không sẵn sàng hoặc không cung cấp một giá trị cần thiết. Ví dụ, ứng dụng có giá trị timeout an toàn trong file local và Config Server ghi đè giá trị đó khi kết nối thành công.

Fallback phải được thiết kế rõ ràng. Một property không có trong Config Server có thể được lấy từ nguồn thấp hơn theo thứ tự ưu tiên, nhưng điều đó không có nghĩa toàn bộ cấu hình remote đã được tải đầy đủ.

### 2.5. Last-known-good configuration

Last-known-good là bản cấu hình hợp lệ gần nhất mà ứng dụng hoặc nền tảng đã lưu bền vững và có thể khôi phục khi nguồn cấu hình hiện tại lỗi.

`optional:configserver:` không tự tạo last-known-good. Nó chỉ cho phép bỏ qua import không tải được. Nếu cần dùng bản cấu hình đã biết là tốt, phải thiết kế nơi lưu, version, tính toàn vẹn, thời hạn sử dụng và quy trình chọn bản đó.

## 3. Config Data import và thứ tự ưu tiên cấu hình

### 3.1. Khai báo Config Server bằng spring.config.import

Spring Boot Config Data là cách mặc định hiện nay để Config Client kết nối Config Server. Ứng dụng thường khai báo trong `application.yml`:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://config.internal:8888"

app:
  downstream:
    timeout: 2s
  retry:
    max-attempts: 3
```

Cấu hình trên yêu cầu Config Server. Nếu muốn nguồn remote là tùy chọn:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:http://config.internal:8888"

app:
  downstream:
    timeout: 2s
  retry:
    max-attempts: 3
```

Nếu Config Server truy cập thành công, các property từ Config Server có thể ghi đè giá trị local theo thứ tự ưu tiên của Config Data. Nếu import tùy chọn không tải được, các giá trị local vẫn có thể được dùng.

### 3.2. Import location và spring.cloud.config.uri

Có thể khai báo URL ngay trong import hoặc dùng `spring.cloud.config.uri` để đặt địa chỉ Config Server.

Ví dụ:

```yaml
spring:
  config:
    import: "optional:configserver:"
  cloud:
    config:
      uri: http://config.internal:8888
```

Nếu URL được khai báo trực tiếp trong `spring.config.import`, URL đó có độ ưu tiên hơn `spring.cloud.config.uri`. Không nên cấu hình hai nơi với các địa chỉ khác nhau mà không có chủ đích vì rất khó chẩn đoán endpoint thực tế đang được gọi.

### 3.3. Remote property source ghi đè local như thế nào?

Các location được import được xử lý như dữ liệu cấu hình bổ sung. Property từ location được import có thể có độ ưu tiên cao hơn document khai báo import. Ví dụ, Config Server trả `app.downstream.timeout=5s` thì giá trị này có thể ghi đè `2s` trong file local.

Thứ tự tổng quát còn chịu ảnh hưởng bởi các property source khác của Spring Boot, chẳng hạn command-line arguments, system properties và environment variables. Khi có xung đột, hãy kiểm tra effective Environment thay vì giả định file YAML nào luôn thắng.

Ví dụ bảng:

| Nguồn | Giá trị timeout | Vai trò |
| --- | --- | --- |
| Local application.yml | 2s | Giá trị mặc định dự phòng |
| Config Server | 5s | Cấu hình tập trung theo ứng dụng/profile |
| Environment variable | 7s | Override ở môi trường triển khai |
| Command-line argument | 9s | Override tường minh khi khởi chạy |

Đây là minh họa về các nguồn cùng khai báo một key. Thứ tự ưu tiên thực tế cần đối chiếu quy tắc property source của Spring Boot và cách ứng dụng nạp Config Data.

### 3.4. Profile và nhiều request lúc startup

Config Data có thể gọi Config Server nhiều lần. Spring Boot trước tiên nạp cấu hình với profile mặc định để tìm các profile bổ sung có thể được kích hoạt từ cấu hình. Sau khi xác định active profiles, nó có thể gọi tiếp để tải cấu hình theo profile.

Vì vậy, thấy nhiều request tới Config Server trong quá trình startup không nhất thiết là lỗi hoặc retry. Hãy phân biệt request theo giai đoạn profile resolution với request retry do lỗi kết nối.

## 4. Quyết định cấu hình nào bắt buộc?

### 4.1. Chia cấu hình theo mức độ quan trọng

Không nên đánh dấu mọi property đều bắt buộc hoặc đều có thể dùng mặc định. Hãy phân loại theo tác động khi thiếu hoặc sai:

| Nhóm cấu hình | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Bắt buộc để bảo đảm an toàn | TLS trust material, credential, authorization policy | Fail-fast nếu không có nguồn hợp lệ |
| Bắt buộc để kết nối dịch vụ lõi | Database URL, schema, broker endpoint | Fail-fast hoặc dùng nguồn dự phòng đã xác minh |
| Bắt buộc theo nghiệp vụ | Topic xử lý thanh toán, tenant routing | Fail-fast nếu thiếu |
| Có thể dùng mặc định an toàn | Timeout nội bộ, số lần retry giới hạn | Local fallback có giới hạn |
| Không thiết yếu | Mức lấy mẫu telemetry, nhãn hiển thị | Có thể dùng default hoặc tắt tính năng |
| Chỉ dành cho môi trường phát triển | Mock endpoint, debug flag | Chỉ đặt trong profile phù hợp |

Ví dụ, nếu không có credential hợp lệ, khởi động service với mật khẩu mặc định hoặc quyền quá rộng là nguy hiểm. Nếu không lấy được cấu hình sampling telemetry, service có thể tiếp tục với sampling rate thấp hoặc tắt telemetry tùy yêu cầu vận hành.

### 4.2. Dùng validation để phát hiện cấu hình thiếu

Optional import chỉ cho phép tiếp tục qua lỗi tải nguồn tùy chọn. Nó không xác minh cấu hình còn lại có đầy đủ hay không.

Hãy kiểm tra các property bắt buộc khi bind cấu hình:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    @NotBlank
    private String endpoint;

    @NotBlank
    private String merchantId;

    // getters and setters
}
```

Khi bật validation và đăng ký cấu hình đúng cách, ứng dụng sẽ không tạo bean cấu hình hợp lệ nếu property bắt buộc bị thiếu. Cách này giúp fallback chỉ hoạt động khi các giá trị local thực sự đáp ứng contract của service.

Đảm bảo ứng dụng có Jakarta Bean Validation implementation phù hợp, thường được thêm qua `spring-boot-starter-validation`, và class cấu hình đã được đăng ký bằng configuration properties scanning hoặc `@EnableConfigurationProperties`.

Không nên kiểm tra chỉ sự tồn tại của property. Cần xác minh format, range, scheme, hostname, timeout và mối quan hệ giữa các giá trị.

### 4.3. Fallback phải an toàn theo nghĩa nghiệp vụ

Một fallback an toàn không chỉ là giá trị giúp ứng dụng khởi động. Nó phải bảo đảm service không thực hiện hành động sai.

Ví dụ:

- timeout có thể dùng default nhỏ và có giới hạn;
- retry phải có giới hạn và backoff, không tạo retry storm;
- endpoint downstream có thể không có fallback nếu gọi nhầm môi trường gây ghi dữ liệu sai;
- credential không nên dùng mật khẩu mặc định;
- feature flag cho chức năng thanh toán hoặc phân quyền cần chọn trạng thái bảo thủ;
- khi thiếu tenant mapping, từ chối request có thể an toàn hơn chọn tenant mặc định.

Hãy đánh giá fallback theo hậu quả nếu service chạy nhiều giờ trong chế độ đó.

## 5. Fail-fast kết hợp retry và backoff

### 5.1. Vì sao cần retry trước khi fail?

Config Server có thể chưa sẵn sàng đúng thời điểm service bắt đầu. Nếu service dừng ngay ở lần kết nối đầu tiên, một sự cố vài giây có thể khiến nhiều instance cùng khởi động thất bại.

Retry cho phép chờ hệ thống phụ thuộc hồi phục. Sau khi hết số lần thử, fail-fast vẫn giữ nguyên nguyên tắc: cấu hình bắt buộc không lấy được thì service không khởi động.

### 5.2. Dependency cần thiết

Theo tài liệu Spring Cloud Config Client hiện hành, retry cho Config Client cần:

- `spring.cloud.config.fail-fast=true` trong cơ chế bootstrap cũ hoặc import bắt buộc tương ứng;
- dependency `spring-retry`;
- dependency `spring-boot-starter-aop`.

Với Config Data import, có thể bỏ `optional:` và đặt retry parameters trên import URL. Hãy dùng phiên bản dependency tương thích với release train Spring Cloud của dự án.

### 5.3. Cấu hình retry cho Config Data import

Ví dụ khi import được khai báo trực tiếp:

```properties
spring.config.import=configserver:http://config.internal:8888?fail-fast=true&max-attempts=8&initial-interval=1000&max-interval=5000&multiplier=1.5
```

Các tham số minh họa:

| Tham số | Ý nghĩa |
| --- | --- |
| `fail-fast` | Yêu cầu lỗi tải cấu hình làm startup thất bại sau khi retry |
| `max-attempts` | Giới hạn số lần thử |
| `initial-interval` | Khoảng chờ ban đầu |
| `max-interval` | Giới hạn khoảng backoff |
| `multiplier` | Hệ số tăng khoảng chờ giữa các lần thử |

Tài liệu Spring Cloud Config hiện hành mô tả mặc định retry sáu lần, khoảng chờ đầu tiên 1000 ms và multiplier 1.1. Các giá trị này có thể thay đổi theo phiên bản và cấu hình; hãy đặt ngưỡng rõ ràng thay vì phụ thuộc mặc định.

Nếu import được đặt trong file profile như `application-prod.yml`, cấu hình retry cần đặt dưới dạng query parameter trên import URL theo hướng dẫn của Config Client.

### 5.4. Tính ngân sách thời gian startup

Retry làm tăng thời gian khởi động tối đa. Khi thiết kế, hãy tính đến:

- connection timeout của mỗi lần gọi;
- read timeout;
- số lần thử;
- khoảng backoff;
- thời gian resolve profile và các request Config Data khác;
- thời hạn startup của orchestrator hoặc deployment platform.

Nếu startup probe có deadline ngắn hơn thời gian retry, nền tảng có thể kill process trước khi retry hoàn tất. Cần đồng bộ startup probe với ngân sách khởi động dự kiến.

Spring Cloud Config Client cung cấp `spring.cloud.config.request-connect-timeout` và `spring.cloud.config.request-read-timeout` để điều chỉnh thời gian chờ kết nối và đọc response. Hãy đối chiếu kiểu giá trị và đơn vị của hai property trong phiên bản đang dùng.

### 5.5. Backoff và jitter

Exponential backoff làm tăng khoảng chờ sau mỗi lần thất bại để tránh gửi request liên tục. Random backoff (jitter) giúp nhiều instance không retry cùng một thời điểm sau một outage.

Khi hàng trăm replica khởi động cùng lúc, retry đồng bộ có thể tạo tải đột biến lên Config Server vừa phục hồi. Hãy dùng backoff phù hợp và random policy nếu phiên bản hỗ trợ.

## 6. Nhiều Config Server và lựa chọn server dự phòng

### 6.1. Nhiều URI với spring.cloud.config.uri

Có thể khai báo danh sách URI phân tách bằng dấu phẩy:

```yaml
spring:
  cloud:
    config:
      uri: "http://config-a:8888,http://config-b:8888"
```

Config Client thử các URL theo thứ tự cho đến khi một lần lấy cấu hình thành công theo chiến lược đang dùng. Điều này tăng khả năng chịu lỗi khi một Config Server instance không chạy hoặc không thể phản hồi.

Tài liệu hiện hành mô tả `spring.cloud.config.multiple-uri-strategy` mặc định là `always`. Có thể đặt `connection-timeout-only` nếu chỉ muốn chuyển sang URL khác khi server không chạy hoặc kết nối timeout.

### 6.2. Không phải mọi lỗi đều là lỗi availability

Một HTTP 401 có thể là credential sai. HTTP 500 có thể là lỗi server hoặc backend Git. HTTP 400 thường cho thấy request/configuration không hợp lệ. Những lỗi này khác với connection refused hoặc connection timeout.

Khi dùng `connection-timeout-only`, client không thử URL tiếp theo cho một số lỗi HTTP như 401 hoặc 500 vì chúng có thể là lỗi cấu hình hoặc lỗi nghiệp vụ chứ không phải server mất kết nối. Cần đọc đúng semantics của strategy thay vì xem mọi response lỗi là lý do failover.

### 6.3. Nhiều import location trong spring.config.import

Có thể khai báo nhiều Config Server location trong một import:

```yaml
spring:
  config:
    import: "configserver:http://config-a:8888,configserver:http://config-b:8888"
```

Với nhiều import location, thứ tự location và cách xử lý lỗi có ý nghĩa. Theo tài liệu Config Client, nếu fail-fast là true, client có thể fail ngay khi lần gọi Config Server đầu tiên không thành công; nếu fail-fast là false, client thử các URL cho đến khi một lần thành công. `multiple-uri-strategy` không áp dụng cho danh sách URL được khai báo theo cách này.

Không đồng thời dùng nhiều cơ chế fallback mà không hiểu thứ tự precedence. Một import thành công nhưng trả cấu hình khác có thể ghi đè giá trị từ import trước đó.

### 6.4. Discovery-first lookup

Nếu Config Server đăng ký với service registry, client có thể dùng DiscoveryClient để tìm server. Cách này cho phép thay đổi địa chỉ Config Server mà client không cần biết URL cố định.

Đổi lại, startup có thêm một network round trip để truy vấn registry. Registry trở thành một dependency khởi động mới. Nếu cả registry lẫn Config Server đều không sẵn sàng, discovery-first không giải quyết được vấn đề cấu hình bắt buộc.

Hãy chọn giữa static URI, nhiều URI và discovery-first theo topology, độ sẵn sàng và các dependency mà service có thể chấp nhận lúc khởi động.

## 7. Thiết kế local fallback có kiểm soát

### 7.1. Đặt giá trị mặc định trong application.yml

Một mẫu thường dùng là khai báo default an toàn trong file local, sau đó cho Config Server ghi đè:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: "optional:configserver:http://config.internal:8888"

app:
  inventory:
    lookup-timeout: 1500ms
    max-retries: 2
    allow-stale-read: false
```

Khi Config Server truy cập được, nó có thể cung cấp các giá trị theo môi trường. Khi Config Server không truy cập được, service có thể dùng giá trị local nếu những giá trị đó đủ để chạy an toàn.

Không đặt credential giả hoặc endpoint production mặc định trong file local. Một local fallback không an toàn có thể biến sự cố cấu hình thành sự cố bảo mật hoặc ghi dữ liệu nhầm môi trường.

### 7.2. Chia fallback theo profile

Có thể dùng profile riêng cho local/test và production. Ví dụ, local có thể dùng mock endpoint, còn production bắt buộc lấy cấu hình từ Config Server.

Không nên đặt `optional:` chung cho mọi môi trường nếu production không được phép chạy khi thiếu remote config. Có thể khai báo import bắt buộc trong profile production và optional trong profile phát triển, nhưng phải kiểm tra chính xác profile nào active trước khi khởi động.

Ví dụ minh họa tách file:

```yaml
# application.yml
spring:
  application:
    name: billing-service
app:
  downstream:
    timeout: 2s
```

```yaml
# application-dev.yml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

```yaml
# application-prod.yml
spring:
  config:
    import: "configserver:https://config.internal"
```

Cần bảo đảm import không bị khai báo trùng theo cách tạo thêm request hoặc thay đổi precedence ngoài dự kiến. Kiểm thử từng profile bằng đúng command line và environment của môi trường deploy.

### 7.3. Fallback cho secret

Không dùng password mặc định trong application.yml làm fallback cho secret production. Nếu Config Server không truy cập được, hãy lấy secret từ một nguồn độc lập có bảo vệ, ví dụ secret manager hoặc configuration tree được mount bởi nền tảng.

Spring Boot hỗ trợ `configtree:` để đọc file trong mounted directory thành property. Ví dụ:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Nếu secret bắt buộc mà directory hoặc file không tồn tại, validation phải làm startup thất bại. Không đánh dấu nguồn secret là optional rồi tiếp tục với credential rỗng hoặc mặc định.

### 7.4. Không nhầm fallback với stale config

Local default là cấu hình dự phòng được đóng gói cùng ứng dụng. Stale config là cấu hình cũ từ lần tải trước. Hai cách này khác nhau về nguồn gốc và độ mới.

Nếu yêu cầu là tiếp tục bằng cấu hình cũ đã được kiểm chứng, hãy lưu bản last-known-good có version và integrity check. Xác định thời hạn tối đa được phép sử dụng bản cũ, cách rollback và cách ngăn instance dùng cấu hình không tương thích với phiên bản code hiện tại.

## 8. Phân biệt lỗi kết nối và lỗi nội dung cấu hình

### 8.1. Connection refused hoặc timeout

Đây thường là lỗi availability: Config Server chưa chạy, DNS sai, firewall, network policy, route hoặc timeout không phù hợp.

Hướng xử lý:

- kiểm tra DNS và route từ chính container/host của service;
- kiểm tra Config Server health và port;
- kiểm tra connection/read timeout;
- kiểm tra retry/backoff;
- thử URI dự phòng nếu được cấu hình.

### 8.2. HTTP 401 hoặc 403

Đây thường là vấn đề xác thực hoặc phân quyền. Không nên tự động coi đây là lỗi server tạm thời.

Kiểm tra credential, token, certificate, scope/role, clock skew và quyền đọc repository/configuration label. Không ghi password hoặc bearer token vào log để chẩn đoán.

### 8.3. HTTP 404 hoặc cấu hình rỗng

Config Server có thể trả cấu hình rỗng khi application/profile không tồn tại, tùy cấu hình server. Tài liệu Config Server có property `spring.cloud.config.server.accept-empty`; khi đặt false, server có thể trả 404 nếu không tìm thấy application.

Đây là khác biệt quan trọng: kết nối thành công không đồng nghĩa server đã cung cấp đầy đủ property mà service cần. Kiểm tra application name, profile, label và các property source trong response. Validation ở client cần phát hiện các key bắt buộc còn thiếu.

### 8.4. HTTP 500

HTTP 500 có thể đến từ Config Server hoặc backend repository như Git/Vault/database. Kiểm tra log phía server và repository health. Khi dùng nhiều URI, quyết định có thử endpoint khác hay không phụ thuộc `multiple-uri-strategy` hoặc semantics của danh sách import.

### 8.5. Cấu hình hợp lệ về cú pháp nhưng sai về ý nghĩa

Một property có thể tồn tại nhưng mang giá trị nguy hiểm, chẳng hạn timeout bằng 0, retry không giới hạn hoặc endpoint trỏ sang môi trường khác. Validation nên bao gồm range, pattern, URI scheme và mối quan hệ giữa các property.

Không dùng việc Config Server trả HTTP 200 làm bằng chứng duy nhất rằng service đã nhận cấu hình đúng.

## 9. Quyết định readiness khi dùng fallback

### 9.1. Khởi động thành công chưa chắc đã sẵn sàng

Khi optional import bị bỏ qua, Spring Boot có thể hoàn tất startup bằng local configuration. Nhưng service chỉ nên nhận traffic nếu local fallback đáp ứng đủ điều kiện nghiệp vụ.

Hãy tách ba trạng thái:

- **Process started:** JVM và ApplicationContext đã khởi tạo.
- **Application ready:** các bean và cấu hình bắt buộc hợp lệ.
- **Operationally degraded:** service đang chạy với fallback hoặc một số tính năng bị tắt.

Có thể đưa trạng thái degraded vào health detail hoặc metric nội bộ, nhưng không tiết lộ secret hay chi tiết cấu hình nhạy cảm.

### 9.2. Kiểm tra cấu hình trước khi nhận traffic

Một quy trình readiness nên xác minh:

1. property bắt buộc đã bind;
2. endpoint downstream có URI hợp lệ;
3. credential và TLS material đã sẵn sàng;
4. feature flags không tạo trạng thái mâu thuẫn;
5. service có thể kết nối các dependency bắt buộc;
6. fallback mode có được cho phép ở môi trường hiện tại không.

Nếu fallback không đủ an toàn, không đánh dấu instance ready. Điều này ngăn load balancer gửi traffic tới một service chỉ mới khởi động được nhưng chưa thể xử lý yêu cầu đúng.

### 9.3. Ghi nhận chế độ cấu hình

Nên ghi metric hoặc startup log có kiểm soát cho biết service đang chạy bằng remote config hay local fallback, kèm application name, active profile và label/version nếu có. Không log giá trị secret.

Thông tin này giúp người vận hành nhận ra service đang ở chế độ suy giảm thay vì cho rằng nó đang dùng cấu hình mới nhất.

## 10. Kiểm thử fail-fast và fallback

### 10.1. Kiểm thử theo ma trận kịch bản

Tạo test cho từng tình huống:

| Kịch bản | Cấu hình kỳ vọng | Kết quả cần xác nhận |
| --- | --- | --- |
| Config Server trả cấu hình hợp lệ | Required hoặc optional | Remote property được áp dụng |
| Config Server không kết nối được, import bắt buộc | Required | Startup thất bại |
| Config Server không kết nối được, import optional | Optional | Startup tiếp tục nếu local config đủ |
| Config Server timeout rồi hồi phục | Required + retry | Startup chờ retry rồi thành công |
| Credential sai | Required hoặc optional theo policy | Không âm thầm dùng fallback không an toàn |
| Remote config thiếu property bắt buộc | Optional hoặc required | Validation phát hiện property thiếu |
| Config Server trả cấu hình sai range | Bất kỳ | Validation từ chối cấu hình |
| Config Server A lỗi, B hoạt động | Multi-server | Client chuyển server theo strategy |
| Profile production không có remote config | Required | Instance không ready hoặc startup fail |

### 10.2. Kiểm tra bằng ApplicationContextRunner

Với các bean cấu hình và validation, có thể dùng `ApplicationContextRunner` để kiểm tra local fallback:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FallbackConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(InventoryConfiguration.class);

    @Test
    void usesLocalDefaultWhenNoRemotePropertyIsProvided() {
        runner.withPropertyValues("app.inventory.lookup-timeout=1500ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(InventoryProperties.class)
                            .getLookupTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Test
    void rejectsMissingRequiredEndpoint() {
        runner.run(context ->
                assertThat(context).hasFailed()
        );
    }
}
```

Runner phù hợp để kiểm tra binding và validation. Nó không tự mô phỏng HTTP Config Server. Với Config Client, cần integration test có server giả lập hoặc môi trường test Config Server để xác minh import, status code, retry và failover thực tế.

### 10.3. Kiểm tra retry và failover

Trong integration test, có thể điều khiển server giả lập để:

- từ chối kết nối ở các lần đầu rồi trả cấu hình thành công;
- trì hoãn response để gây timeout;
- trả 401 hoặc 500;
- trả 404 hoặc property source rỗng;
- cho server A lỗi và server B thành công;
- xác nhận số lần thử và khoảng thời gian retry trong giới hạn.

Không kiểm thử retry bằng cách sleep cố định dài nếu có thể quan sát request count hoặc dùng clock/test harness phù hợp. Giữ timeout test đủ lớn cho retry budget nhưng vẫn có giới hạn để phát hiện vòng lặp vô tận.

### 10.4. Kiểm tra profile và property precedence

Chạy integration test với các profile khác nhau và cùng key ở local/remote. Xác nhận:

- import có đúng profile không;
- remote property có ghi đè local theo mong đợi không;
- environment variable hoặc command-line argument có ghi đè ngoài ý muốn không;
- fallback có được dùng chỉ khi Config Server không tải được không;
- validation có thất bại khi remote config thiếu key bắt buộc không.

## 11. Troubleshooting và vận hành

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| App fail ngay khi Config Server down | Import bắt buộc hoặc fail-fast bật | Xác định cấu hình có thật sự bắt buộc; nếu không, thiết kế optional fallback |
| App khởi động nhưng thiếu property | Import optional bị bỏ qua hoặc remote response rỗng | Kiểm tra property source và validation |
| App mất nhiều thời gian startup | Retry nhiều, timeout lớn hoặc nhiều profile request | Tính lại startup budget và probe timeout |
| App gọi Config Server nhiều lần | Config Data resolve default/profile hoặc retry | Phân biệt request profile với retry qua log |
| Không chuyển sang Config Server B | Strategy không cho failover với loại lỗi đó hoặc import fail-fast | Kiểm tra URI strategy, status code và import syntax |
| App dùng giá trị local dù remote đang hoạt động | URL sai, application/profile/label sai hoặc property không được trả về | Kiểm tra response Config Server và Environment |
| App dùng cấu hình cũ sau deploy | Label hoặc repository revision không đúng | Kiểm tra label, commit và version cấu hình |
| Retry tạo tải lớn khi outage | Nhiều replica retry đồng bộ | Dùng backoff/jitter, giới hạn attempt và rollout có kiểm soát |
| Production chạy với fallback không mong muốn | Profile/import optional dùng chung giữa môi trường | Tách profile và kiểm tra startup policy |
| Cấu hình có đủ key nhưng service vẫn lỗi | Giá trị sai semantics hoặc không tương thích version | Thêm validation range/format và contract check |

### Quy trình xử lý sự cố

1. Xác định service đang dùng import bắt buộc hay optional.
2. Xác định nguồn cấu hình thực tế: Config Server URI, discovery hay local.
3. Kiểm tra DNS, TCP, TLS và timeout từ môi trường chạy service.
4. Đọc HTTP status và log Config Server.
5. Xác nhận application name, active profile và label.
6. Xác minh property source remote có được nạp không.
7. Kiểm tra property bắt buộc và validation.
8. Xác định service đang dùng remote, local fallback hay last-known-good.
9. Kiểm tra readiness và traffic có được phép vào instance không.
10. Khi Config Server hồi phục, áp dụng refresh/restart theo quy trình đã kiểm thử; không giả định optional import tự tải lại cấu hình sau startup.

## 12. Checklist chọn fail-fast hay fallback

Trước khi triển khai, hãy trả lời:

- [ ] Property nào thực sự bắt buộc để service hoạt động an toàn?
- [ ] Thiếu property nào phải làm startup thất bại?
- [ ] Local fallback có đầy đủ và an toàn cho môi trường mục tiêu không?
- [ ] Production có được phép chạy ở degraded mode không?
- [ ] Secret có nguồn độc lập và không dùng credential mặc định không?
- [ ] Remote config được kiểm tra schema, range và version không?
- [ ] Retry có giới hạn attempt, backoff và timeout không?
- [ ] Startup probe có đủ thời gian cho retry budget không?
- [ ] Có nhiều Config Server và đã định nghĩa chiến lược failover không?
- [ ] Đã phân biệt connection failure với 401, 404 và 500 chưa?
- [ ] Có metric/log cho biết service đang dùng fallback không?
- [ ] Readiness có chặn traffic khi cấu hình không đủ an toàn không?
- [ ] Có test cho outage, empty config, invalid config và recovery không?
- [ ] Có quy trình rollback về label/version cấu hình đã biết là tốt không?

## 13. Bài tập vận dụng

### Bài tập 1 — Config Server gián đoạn trong production

Một service xử lý đơn hàng cần database URL, credential và timeout của payment gateway. Config Server không truy cập được khi pod khởi động.

Hãy phân loại property nào bắt buộc, property nào có thể dùng default. Đề xuất import required/optional và điều kiện readiness.

### Bài tập 2 — Local fallback không đủ an toàn

Một ứng dụng có local fallback với database username admin và password mặc định. Nhóm bật optional Config Server để service luôn khởi động được.

Hãy phân tích rủi ro và đề xuất cách lấy secret độc lập bằng secret manager hoặc config tree, cùng validation khi secret thiếu.

### Bài tập 3 — Retry làm startup vượt thời hạn

Deployment có startup probe timeout 30 giây. Config Client retry 10 lần, mỗi lần có read timeout 5 giây và backoff tăng dần.

Hãy phân tích vì sao probe có thể kill process trước khi retry hoàn tất. Đề xuất ngân sách timeout, số lần retry và rollout phù hợp.

### Bài tập 4 — Config Server A trả 401, B đang khỏe

Client có hai URI và được cấu hình `multiple-uri-strategy=connection-timeout-only`. Server A trả 401 vì credential sai; server B hoạt động bình thường.

Hãy giải thích vì sao client có thể không thử B và cách phân biệt lỗi credential với lỗi availability.

### Bài tập 5 — Remote config trả rỗng

Config Server trả response thành công nhưng thiếu `app.payment.endpoint`. Ứng dụng dùng optional import và khởi động với giá trị local không đầy đủ.

Hãy đề xuất validation và readiness check để service không nhận traffic khi property bắt buộc chưa có.

### Bài tập 6 — Config Server hồi phục sau khi service dùng fallback

Service đã khởi động bằng local fallback. Sau vài phút, Config Server hoạt động trở lại.

Hãy giải thích vì sao optional import không tự động bảo đảm cấu hình được tải lại. Đề xuất quy trình refresh hoặc restart, xác minh property mới và rollback nếu cấu hình không hợp lệ.

## 14. Tự kiểm tra nhanh

1. Fail-fast có nghĩa gì? **Không khởi động nếu cấu hình bắt buộc không tải được.**
2. Với Config Data import, làm thế nào để yêu cầu Config Server? **Bỏ tiền tố `optional:`.**
3. Optional import có tự lưu last-known-good không? **Không.**
4. Retry giải quyết vấn đề gì? **Lỗi tạm thời trước khi kết luận nguồn cấu hình không sẵn sàng.**
5. Retry có thay thế validation không? **Không.**
6. Config Client retry cần các dependency nào theo tài liệu hiện hành? **Spring Retry và Spring Boot Starter AOP.**
7. Multiple URI strategy mặc định hiện hành là gì? **`always`.**
8. `connection-timeout-only` làm gì? **Chỉ failover cho trường hợp server không chạy hoặc kết nối timeout theo semantics của client.**
9. Config Server trả 401 có giống connection timeout không? **Không; thường cần xử lý credential hoặc authorization.**
10. HTTP 200 có chứng minh đủ property bắt buộc không? **Không, cần kiểm tra response và validate cấu hình.**
11. Vì sao cần readiness check khi dùng fallback? **Để không gửi traffic tới instance khởi động được nhưng không thể xử lý nghiệp vụ an toàn.**
12. Optional import có tự tải lại remote config khi server hồi phục không? **Không nên giả định; cần cơ chế refresh hoặc restart phù hợp.**

**Thông điệp cốt lõi:** Fail-fast bảo vệ service khỏi chạy với cấu hình bắt buộc bị thiếu; optional import và fallback giúp duy trì một phần khả năng hoạt động khi nguồn cấu hình gián đoạn. Hãy phân loại property theo mức độ quan trọng, kết hợp retry/backoff có giới hạn, hiểu chính xác hành vi failover của nhiều Config Server và validate cấu hình trước khi nhận traffic. Một service chỉ nên chạy ở chế độ fallback khi bộ giá trị dự phòng đã được chứng minh là an toàn cho môi trường đó.

**Tài liệu tham khảo:**

- [Spring Cloud Config 5.0 — Config Client, Fail Fast and Retry](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Multiple Config Server URLs and Timeout Configuration](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration and Optional Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Configuration Trees for Mounted Secrets](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Environment Repository and accept-empty](https://docs.spring.io/spring-cloud-config/docs/current/reference/html/)

Hành vi Config Data, retry properties và multiple-server strategy có thể thay đổi theo release. Đối chiếu tài liệu của Spring Boot/Spring Cloud release train đang dùng trước khi triển khai.
