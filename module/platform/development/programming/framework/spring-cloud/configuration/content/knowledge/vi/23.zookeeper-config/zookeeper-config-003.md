# root, default-context và profile-separator

Spring Cloud Zookeeper Config cho phép ứng dụng Spring Boot lấy cấu hình trực tiếp từ Apache ZooKeeper. Thay vì gọi Spring Cloud Config Server, ứng dụng kết nối tới ZooKeeper và nạp các giá trị trong các context phù hợp vào Spring Environment. Ba thuộc tính `root`, `default-context` và `profile-separator` quyết định cách ứng dụng tìm đúng vùng cấu hình theo tên ứng dụng và profile đang hoạt động.

Ba thuộc tính này tạo thành quy ước đặt đường dẫn trong namespace ZooKeeper:

- `root` xác định thư mục gốc chứa cấu hình.
- `default-context` xác định context dùng chung cho mọi ứng dụng.
- `profile-separator` xác định ký tự nối tên context với profile.

Khi quy ước được thống nhất, nhóm có thể tách cấu hình dùng chung, cấu hình riêng từng service và cấu hình theo môi trường mà không phải thay đổi mã nguồn ứng dụng. Bài viết giải thích cách các đường dẫn được tạo, thứ tự ưu tiên giữa các context, cách ghi key-value vào ZooKeeper và cách kiểm tra ứng dụng đang đọc đúng namespace.

## 1. Spring Cloud Zookeeper Config nằm ở đâu trong kiến trúc?

Spring Cloud Zookeeper Config là một lựa chọn lưu trữ và phân phối cấu hình trực tiếp cho Spring Boot. Nó là một giải pháp thay thế cho mô hình Spring Cloud Config Server và Config Client trong những hệ thống muốn dùng ZooKeeper làm nguồn cấu hình.

Điểm này cần được phân biệt rõ: `spring.cloud.zookeeper.config.root`, `default-context` và `profile-separator` thuộc Spring Cloud Zookeeper Config. Chúng không phải các thuộc tính cấu hình Git backend của Spring Cloud Config Server.

Luồng nạp cấu hình:

~~~mermaid
flowchart LR
    Z[ZooKeeper ensemble] -->|Đọc các context| L[Spring Cloud Zookeeper Config]
    A[application name] --> L
    P[active profiles] --> L
    C[root / default-context / profile-separator] --> L
    L --> E[Spring Environment]
    E --> B[ConfigurationProperties / beans]
~~~

Ứng dụng sử dụng starter `spring-cloud-starter-zookeeper-config`. Spring Cloud Zookeeper tạo các PropertySource theo tên ứng dụng và profile, rồi đưa chúng vào Spring Environment. Các bean của ứng dụng đọc giá trị qua `@ConfigurationProperties`, `@Value` hoặc `Environment` như những nguồn cấu hình Spring khác.

## 2. Ba thuộc tính và giá trị mặc định

Các thuộc tính nằm dưới prefix `spring.cloud.zookeeper.config`:

| Thuộc tính | Mặc định | Vai trò |
| --- | --- | --- |
| `root` | `config` | Namespace gốc chứa toàn bộ context cấu hình |
| `default-context` | `application` | Context dùng chung cho mọi ứng dụng |
| `profile-separator` | `,` | Ký tự nối context với tên profile |

Một số thuộc tính liên quan:

| Thuộc tính | Mặc định/ý nghĩa |
| --- | --- |
| `enabled` | `true`; đặt `false` để tắt Zookeeper Config |
| `name` | Nếu không đặt, dùng `spring.application.name`; đây là tên context riêng của ứng dụng |
| `fail-fast` | `true`; lỗi khi tra cứu cấu hình có thể làm quá trình khởi động thất bại |
| `spring.cloud.zookeeper.connect-string` | `localhost:2181` nếu không chỉ định nơi kết nối khác |

Ví dụ cấu hình mặc định:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    zookeeper:
      connect-string: localhost:2181
      config:
        enabled: true
        root: config
        default-context: application
        profile-separator: ","
~~~

Với cấu hình này, các context nằm dưới namespace `/config`. Ứng dụng `orders-service` có profile `prod` sẽ tìm cấu hình trong những context được tạo từ tên ứng dụng, profile và context dùng chung.

Các giá trị trên là quy ước đường dẫn, không phải tên file YAML. ZooKeeper lưu dữ liệu trong các znode; Spring Cloud Zookeeper đọc các znode dưới context và chuyển đường dẫn thành tên property.

## 3. root xác định namespace gốc

`spring.cloud.zookeeper.config.root` là thư mục gốc mà Spring Cloud Zookeeper dùng để xây dựng các context cấu hình. Mặc định là `config`, tương ứng namespace `/config` trong ZooKeeper.

Ví dụ:

~~~yaml
spring:
  cloud:
    zookeeper:
      config:
        root: configuration
~~~

Khi đổi `root` thành `configuration`, các context được tìm dưới `/configuration`:

~~~text
/configuration
├── application
├── application::prod
├── orders-service
└── orders-service::prod
~~~

Đây là cấu trúc minh họa khi dùng `profile-separator: "::"`. Root giúp phân vùng cấu hình của ứng dụng với các namespace ZooKeeper khác, chẳng hạn namespace service discovery hoặc dữ liệu điều phối.

Một số nguyên tắc khi chọn root:

- Dùng tên ngắn, ổn định và có ý nghĩa, ví dụ `config`, `configuration` hoặc `platform-config`.
- Dùng cùng root cho các ứng dụng cần chia sẻ context chung.
- Có thể dùng root khác nhau cho các môi trường nếu tổ chức muốn tách namespace dev, staging và production.
- Không thay root tùy tiện sau khi đã có dữ liệu; ứng dụng sẽ tìm ở namespace mới và có thể không còn thấy cấu hình cũ.
- Trong thuộc tính nên khai báo tên root không có dấu slash ở đầu, ví dụ `configuration`; đường dẫn znode thực tế được biểu diễn là `/configuration`.

Ví dụ tách môi trường bằng root:

~~~yaml
# Môi trường development
spring:
  cloud:
    zookeeper:
      config:
        root: config-dev
~~~

~~~yaml
# Môi trường production
spring:
  cloud:
    zookeeper:
      config:
        root: config-prod
~~~

Cách tách này tạo ranh giới namespace rõ ràng. Tuy nhiên, root khác nhau không thay thế ACL; vẫn cần giới hạn workload nào được đọc hoặc ghi từng namespace.

## 4. default-context là vùng cấu hình dùng chung

`spring.cloud.zookeeper.config.default-context` xác định tên context áp dụng cho tất cả ứng dụng dùng chung root. Giá trị mặc định là `application`.

Giả sử có hai ứng dụng:

- `orders-service`
- `payment-service`

Cả hai đều có thể đọc các thuộc tính trong context `application`. Nếu đổi `default-context` thành `apps`, context dùng chung chuyển từ `/config/application` sang `/config/apps`.

Ví dụ:

~~~yaml
spring:
  cloud:
    zookeeper:
      config:
        root: configuration
        default-context: apps
        profile-separator: "::"
~~~

Với cấu hình trên, các ứng dụng cùng đọc phần cấu hình chung từ:

~~~text
/configuration/apps
~~~

Nếu ứng dụng chạy profile `prod`, nó còn tìm context chung theo profile:

~~~text
/configuration/apps::prod
~~~

Dùng context chung cho các giá trị thật sự có cùng ý nghĩa giữa nhiều service, ví dụ:

~~~yaml
platform:
  region: ap-southeast-1
  connect-timeout: 2s
observability:
  metrics-enabled: true
~~~

Không đưa mọi cấu hình nghiệp vụ vào context dùng chung. Các thuộc tính riêng như số lần retry của đơn hàng hoặc endpoint của nhà cung cấp thanh toán nên nằm trong context riêng của từng ứng dụng. Nếu hai ứng dụng vô tình dùng chung một key nhưng có yêu cầu khác nhau, context chung có thể làm hành vi khó dự đoán.

## 5. Context riêng của ứng dụng được chọn từ application name

Tên context riêng mặc định lấy từ `spring.application.name`. Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
~~~

Khi đó context riêng là `orders-service`. Nếu có cấu hình:

~~~yaml
orders:
  retry:
    max-attempts: 4
  http:
    read-timeout: 10s
~~~

các key tương ứng được đặt dưới context riêng của ứng dụng.

Có thể thay tên dùng để tra cứu ZooKeeper bằng:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    zookeeper:
      config:
        name: order-platform
~~~

Lúc này Spring Cloud Zookeeper dùng `order-platform` làm tên context riêng. Thuộc tính `spring.application.name` vẫn giữ giá trị `orders-service` cho các thành phần khác của ứng dụng, trừ khi chúng được cấu hình riêng. Vì vậy, chỉ đặt `name` khi có chủ đích ánh xạ application name sang một context lưu trữ khác.

Đặt tên context nhất quán giúp dễ phân quyền và truy vết. Tránh để nhiều service không liên quan cùng trỏ đến một context riêng, vì thay đổi của một service có thể ảnh hưởng đến các service còn lại.

## 6. profile-separator nối context với profile

`spring.cloud.zookeeper.config.profile-separator` xác định chuỗi được chèn giữa tên context và profile. Mặc định là dấu phẩy.

Ví dụ mặc định:

- Application: `orders-service`
- Profile: `prod`
- Root: `config`
- Separator: `,`

Context profile-specific là:

~~~text
/config/orders-service,prod
~~~

Nếu dùng:

~~~yaml
spring:
  cloud:
    zookeeper:
      config:
        profile-separator: "::"
~~~

thì cùng application/profile sẽ dùng:

~~~text
/config/orders-service::prod
~~~

Separator có thể là chuỗi không rỗng, chẳng hạn `,`, `-` hoặc `::`. Nên chọn một quy ước ổn định và dùng nhất quán cho tất cả ứng dụng. Tránh chọn dấu slash vì slash là ký tự phân cấp đường dẫn của ZooKeeper; dùng separator có thể làm thay đổi cấu trúc znode ngoài ý muốn.

Không nhầm `profile-separator` với dấu phân tách danh sách profile trong `spring.profiles.active`. Ví dụ `spring.profiles.active=prod,observability` dùng cú pháp danh sách profile của Spring Boot; còn `profile-separator` được dùng khi tạo tên context ZooKeeper cho từng profile.

## 7. Bốn context tự động và thứ tự ưu tiên

Với root mặc định `config`, default context `application`, ứng dụng `testApp` và profile `dev`, Spring Cloud Zookeeper tạo bốn PropertySource theo thứ tự từ cụ thể nhất đến tổng quát nhất:

1. `/config/testApp,dev`
2. `/config/testApp`
3. `/config/application,dev`
4. `/config/application`

Thứ tự này có ý nghĩa:

- Context ứng dụng + profile chỉ áp dụng cho một ứng dụng trong một profile.
- Context ứng dụng áp dụng cho ứng dụng đó ở mọi profile.
- Context chung + profile áp dụng cho mọi ứng dụng trong profile đó.
- Context chung áp dụng cho mọi ứng dụng và mọi profile.

Nếu cùng một key xuất hiện ở nhiều context, nguồn cụ thể hơn nằm trước và có độ ưu tiên cao hơn. Ví dụ:

| Context | Giá trị `orders.http.read-timeout` |
| --- | --- |
| `/config/application` | `5s` |
| `/config/application,prod` | `8s` |
| `/config/orders-service` | `7s` |
| `/config/orders-service,prod` | `10s` |

Với `orders-service` chạy profile `prod`, giá trị được chọn là `10s` từ context cụ thể nhất.

Sơ đồ thứ tự:

~~~mermaid
flowchart TD
    A["/config/orders-service,prod<br/>Ưu tiên cao nhất"] --> B["/config/orders-service"]
    B --> C["/config/application,prod"]
    C --> D["/config/application<br/>Ưu tiên thấp nhất"]
~~~

Thứ tự trên là thứ tự giữa các context ZooKeeper tự động. Spring Environment còn có các nguồn cấu hình khác như command-line arguments, environment variables và file Config Data; giá trị cuối cùng của ứng dụng vẫn chịu quy tắc ưu tiên tổng thể của Spring Boot.

## 8. Tính đường dẫn với root, default-context và profile-separator tùy chỉnh

Giả sử cấu hình:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  cloud:
    zookeeper:
      config:
        root: configuration
        default-context: apps
        profile-separator: "::"
~~~

Bốn context được tạo:

| Mức | Đường dẫn ZooKeeper | Phạm vi |
| --- | --- | --- |
| 1 | `/configuration/orders-service::prod` | Riêng orders-service, profile prod |
| 2 | `/configuration/orders-service` | Riêng orders-service, mọi profile |
| 3 | `/configuration/apps::prod` | Chung cho mọi ứng dụng, profile prod |
| 4 | `/configuration/apps` | Chung cho mọi ứng dụng, mọi profile |

Nếu một thuộc tính được đặt ở cả bốn nơi, context mức 1 được ưu tiên. Khi không có key ở mức 1, Spring tiếp tục tìm trong context mức 2 rồi mức 3 và mức 4.

Bảng này là công cụ kiểm tra nhanh khi tạo znode. Nếu một property không xuất hiện, hãy tính lại đường dẫn theo đúng ba giá trị cấu hình và application/profile thực tế trước khi kiểm tra nội dung node.

## 9. Đưa key-value vào các znode

Spring Cloud Zookeeper đọc dữ liệu dưới context như các property. Mỗi znode có dữ liệu sẽ tạo ra một giá trị; đường dẫn tương đối dưới context được chuyển thành property key bằng cách thay dấu slash bằng dấu chấm.

Ví dụ context:

~~~text
/configuration/orders-service::prod
~~~

Cấu trúc key:

~~~text
/configuration/orders-service::prod
└── orders
    └── http
        └── read-timeout = 10s
~~~

Property tương ứng:

~~~properties
orders.http.read-timeout=10s
~~~

Có thể biểu diễn các key bằng znode lồng nhau hoặc tên key có dấu chấm. Ví dụ lệnh ZooKeeper CLI cho môi trường lab, giả sử các node cha đã tồn tại:

~~~text
create /configuration
create /configuration/orders-service::prod
create /configuration/orders-service::prod/orders
create /configuration/orders-service::prod/orders/http
create /configuration/orders-service::prod/orders/http/read-timeout 10s
~~~

Đối với key dùng chung:

~~~text
create /configuration/apps
create /configuration/apps/platform
create /configuration/apps/platform/region ap-southeast-1
~~~

Các lệnh `create` yêu cầu node cha tồn tại trước. Trong automation có thể dùng Curator với `creatingParentsIfNeeded()` để tạo các cấp cha khi cần. Không dùng lệnh minh họa trên một ZooKeeper production nếu chưa xác định ACL, quyền ghi và quy trình review.

## 10. Kích hoạt Zookeeper Config trong Spring Boot

Thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-config</artifactId>
</dependency>
~~~

Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án để quản lý dependency. Không tự ghép phiên bản starter và Curator khác release train.

Với Spring Boot 2.4 trở lên, Config Data import là cách mặc định để kết nối Zookeeper Config. Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "zookeeper:"
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      config:
        root: configuration
        default-context: apps
        profile-separator: "::"
~~~

Nếu cấu hình từ ZooKeeper là bắt buộc để ứng dụng chạy đúng, dùng `zookeeper:` không có tiền tố `optional:`. Nếu nguồn này không bắt buộc và ứng dụng có fallback an toàn, có thể dùng:

~~~yaml
spring:
  config:
    import: "optional:zookeeper:"
~~~

Vị trí kết nối cũng có thể đặt trong location import, ví dụ `zookeeper:zk-1.internal:2181`. Khi địa chỉ được ghi ngay trong import location, nó có độ ưu tiên cao hơn `spring.cloud.zookeeper.connect-string`.

Khi dùng Config Data import, không cần `bootstrap.yml` chỉ để kết nối Zookeeper Config. Nếu dự án cố ý bật legacy bootstrap bằng `spring.cloud.bootstrap.enabled=true`, `spring.config.use-legacy-processing=true` hoặc starter bootstrap, các thuộc tính Zookeeper Config cần được đặt trong `bootstrap.yml` theo cơ chế cũ.

## 11. Chọn context tường minh trong Config Data import

Ngoài bốn context được tạo tự động, Config Data import cho phép chỉ định các context cụ thể trong location. Ví dụ:

~~~properties
spring.config.import=optional:zookeeper:zk-1.internal:2181/contextone;/context/two
~~~

Trong ví dụ này, ứng dụng chỉ nạp các context `/contextone` và `/context/two` được chỉ định. Khi dùng danh sách context tường minh, bạn đang chọn trực tiếp vùng dữ liệu cần đọc thay vì để Spring Cloud Zookeeper tính bốn context từ application, default-context và profile.

Cách này hữu ích khi một ứng dụng cần ghép các namespace đặc biệt hoặc khi cấu trúc ZooKeeper đã được chuẩn hóa theo quy ước khác. Tuy nhiên, nó làm cho quan hệ tự động giữa application name và profile không còn là cơ sở duy nhất. Hãy ghi rõ thứ tự context và kiểm thử xung đột key giữa chúng.

Không trộn lẫn cú pháp context tường minh với cách tính tự động nếu chưa hiểu cách resolver xử lý location. Với phần lớn ứng dụng, bắt đầu bằng context tự động sẽ dễ vận hành và dễ dự đoán hơn.

## 12. Nhiều profile đang hoạt động

Spring Cloud Zookeeper tạo context profile-specific dựa trên các profile được Spring Boot chấp nhận. Với một profile `prod`, đường dẫn dễ dự đoán như `orders-service,prod` hoặc `orders-service::prod`.

Khi ứng dụng bật nhiều profile, chẳng hạn:

~~~yaml
spring:
  profiles:
    active:
      - prod
      - observability
~~~

sẽ có các context profile-specific tương ứng với từng profile được chấp nhận. Thứ tự profile của Spring có thể ảnh hưởng đến kết quả nếu nhiều context cùng khai báo một key. Vì vậy:

- Chỉ bật các profile có mục đích rõ ràng.
- Dùng profile-specific context cho những khác biệt thực sự cần thiết.
- Tránh để nhiều profile cùng sở hữu một key nếu không có quy tắc ưu tiên được kiểm thử.
- Kiểm tra danh sách profile và PropertySource thực tế trong ứng dụng khi có nhiều profile.

Không tự ghép toàn bộ danh sách profile thành một tên context duy nhất. Spring Cloud Zookeeper xử lý các profile đang hoạt động để tạo những nguồn theo profile; hãy xác nhận các context mà phiên bản đang dùng thực sự truy vấn.

## 13. Thứ tự cấu hình với @ConfigurationProperties

Các giá trị lấy từ ZooKeeper đi vào Spring Environment và có thể được bind vào bean như cấu hình thông thường.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "orders.http")
public record OrdersHttpProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
~~~

Đăng ký binding:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Nếu ZooKeeper có key `orders.http.read-timeout` trong context ưu tiên cao nhất, bean nhận giá trị từ context đó. Nếu key không tồn tại ở context cụ thể, Spring tiếp tục phân giải từ các PropertySource khác theo thứ tự.

Để kiểm tra, có thể đọc giá trị qua `Environment` hoặc xem bean đã bind trong môi trường kiểm thử. Không log toàn bộ cấu hình nếu có secret hoặc dữ liệu nhạy cảm.

## 14. Kiểm tra đường dẫn và giá trị trong ZooKeeper

Khi một ứng dụng không nhận được property mong đợi, kiểm tra theo thứ tự:

1. Xác nhận ZooKeeper đang hoạt động và client kết nối được.
2. Ghi nhận `spring.application.name`, profile active và `spring.cloud.zookeeper.config.name` nếu có.
3. Ghi nhận `root`, `default-context` và `profile-separator`.
4. Tính bốn context tự động theo các giá trị đó.
5. Dùng ZooKeeper CLI hoặc Curator kiểm tra các node có tồn tại không.
6. Kiểm tra key nằm dưới đúng context và có data.
7. Xác nhận property đã xuất hiện trong Spring Environment và bean binding.

Ví dụ kiểm tra node bằng ZooKeeper CLI:

~~~text
ls /configuration
ls /configuration/orders-service::prod
get /configuration/orders-service::prod/orders/http/read-timeout
get /configuration/apps/platform/region
~~~

Tên lệnh và cú pháp CLI có thể khác theo phiên bản ZooKeeper CLI. Khi chạy trên môi trường thật, dùng công cụ quản trị đã được cấp quyền và không in dữ liệu secret ra terminal chia sẻ.

Có thể expose Actuator `env` hoặc `configprops` trong môi trường kiểm thử để xem property source và giá trị đã bind. Chỉ expose các endpoint này trong mạng quản trị, bật xác thực và sanitization phù hợp.

## 15. Refresh sau khi thay đổi znode

Các giá trị được nạp vào Spring Environment theo cơ chế Config Data hoặc bootstrap. Khi nội dung ZooKeeper thay đổi, không nên giả định mọi bean đều tự cập nhật tức thì trong mọi phiên bản.

Trong các cấu hình hỗ trợ refresh, có thể gửi HTTP POST đến endpoint `/refresh` của ứng dụng để yêu cầu nạp lại cấu hình. Endpoint cần được bật và bảo vệ theo phiên bản Spring Cloud Context đang dùng. Bean cần thay đổi runtime phải hỗ trợ rebind hoặc refresh scope; singleton thông thường có thể vẫn giữ giá trị đã capture lúc khởi tạo.

Một số phiên bản Spring Cloud Zookeeper có cơ chế watcher cho namespace cấu hình; khả năng này phụ thuộc phiên bản và cấu hình watcher. Nếu cần cập nhật tự động, kiểm tra tính năng ở đúng release train thay vì giả định ZooKeeper hỗ trợ watch đồng nghĩa ứng dụng đã tự đăng ký listener.

Với thay đổi nhiều key liên quan, hãy cập nhật dữ liệu theo quy trình có kiểm soát, sau đó refresh và kiểm tra một bộ cấu hình nhất quán. Đối với nhiều instance, theo dõi từng instance đã nhận giá trị mới trước khi coi rollout hoàn tất.

## 16. Bảo mật namespace và ACL

ZooKeeper có thể lưu cả cấu hình vận hành và thông tin nhạy cảm. Việc đặt context đúng không thay thế quyền truy cập. Dùng ACL để giới hạn workload nào có thể đọc hoặc ghi từng namespace.

Một số nguyên tắc:

- Chỉ cấp quyền đọc cho ứng dụng cần đọc context.
- Giới hạn quyền ghi cho pipeline hoặc nhóm vận hành chịu trách nhiệm cấu hình.
- Tách namespace theo môi trường hoặc miền sở hữu nếu cần giảm phạm vi ảnh hưởng.
- Bảo vệ kết nối tới ZooKeeper bằng network policy và TLS nếu triển khai hỗ trợ.
- Không đưa password hoặc token dạng rõ vào znode nếu chưa có chính sách secret management phù hợp.
- Không cấp quyền ghi toàn bộ root cho mọi service.
- Theo dõi thay đổi znode và người thực hiện thông qua audit phù hợp với nền tảng.

Spring Cloud Zookeeper cho phép tùy biến `CuratorFramework` để cấu hình ACL authentication. Với các phiên bản hiện đại, có thể cung cấp `CuratorFrameworkCustomizer` để thêm thông tin xác thực trước khi client được tạo. Ví dụ digest auth minh họa:

~~~java
@Configuration
public class ZookeeperAuthConfiguration {

    @Bean
    CuratorFrameworkCustomizer digestAuthCustomizer() {
        return builder -> builder.authorization(
                "digest",
                "orders-reader:replace-with-secret".getBytes(StandardCharsets.UTF_8));
    }
}
~~~

Đoạn code chỉ minh họa cách gắn cơ chế xác thực; credential phải được cấp từ secret manager và không hard-code trong source. Cần cấu hình ACL tương ứng ở phía ZooKeeper để danh tính có quyền đọc đúng context.

## 17. Lỗi thường gặp khi cấu hình ba thuộc tính

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng không thấy cấu hình | Root sai hoặc node được tạo dưới namespace cũ | Tính lại đường dẫn và kiểm tra root |
| Tất cả ứng dụng đều nhận cùng giá trị | Key riêng bị đặt trong default-context | Chuyển key vào context application |
| Một ứng dụng không nhận cấu hình riêng | `spring.application.name` hoặc `config.name` không khớp tên context | Xác nhận tên context thực tế |
| Profile prod không ghi đè giá trị chung | Sai profile active hoặc separator không khớp | Kiểm tra context có hậu tố profile đúng |
| Thay separator nhưng ứng dụng mất cấu hình | Znode vẫn dùng tên context theo separator cũ | Di chuyển hoặc tạo lại node theo quy ước mới |
| Ứng dụng khởi động thất bại khi ZooKeeper lỗi | Import bắt buộc hoặc fail-fast bật | Kiểm tra chính sách bắt buộc/optional và khả năng sẵn sàng |
| Property key bị sai dấu chấm | Cấu trúc znode lồng nhau không như dự kiến | Kiểm tra cách ánh xạ slash thành dot |
| Có nhiều giá trị cùng key | Key được đặt ở nhiều context | Xem thứ tự PropertySource và chỉ giữ override có chủ đích |
| Refresh không đổi bean | Bean không hỗ trợ rebind/refresh hoặc endpoint không được bật | Kiểm tra refresh mechanism và vòng đời bean |
| Access denied | ACL không cho phép workload đọc context | Kiểm tra identity, ACL và quyền theo namespace |

Đổi `root`, `default-context` hoặc `profile-separator` là thay đổi quy ước lưu trữ. Nếu chỉ cập nhật application.yml mà không di chuyển dữ liệu, ứng dụng sẽ tìm các đường dẫn mới trong khi dữ liệu vẫn nằm ở đường dẫn cũ. Hãy coi việc đổi quy ước như một migration: tạo namespace mới, sao chép dữ liệu, kiểm tra, chuyển client và chỉ dọn namespace cũ sau khi xác nhận không còn ứng dụng sử dụng.

## 18. Quy trình thiết kế namespace cho nhiều ứng dụng

Một quy trình triển khai có thể thực hiện như sau:

1. Chọn root dùng chung cho môi trường hoặc miền hệ thống.
2. Chọn default-context cho các giá trị áp dụng rộng.
3. Chọn profile-separator và thống nhất với nhóm phát triển/vận hành.
4. Xác định tên application context theo `spring.application.name` hoặc `spring.cloud.zookeeper.config.name`.
5. Tạo context dùng chung và context riêng theo profile.
6. Ghi các key-value vào znode theo cấu trúc dễ quản lý.
7. Cấu hình Config Data import và kết nối ZooKeeper.
8. Kiểm tra property source và precedence với một ứng dụng đại diện.
9. Áp dụng ACL theo ứng dụng và môi trường.
10. Kiểm thử thay đổi, refresh và rollback trước khi đưa vào production.

Ví dụ quy ước:

| Phạm vi | Context |
| --- | --- |
| Tất cả ứng dụng, mọi profile | `/configuration/apps` |
| Tất cả ứng dụng, profile prod | `/configuration/apps::prod` |
| orders-service, mọi profile | `/configuration/orders-service` |
| orders-service, profile prod | `/configuration/orders-service::prod` |
| payment-service, mọi profile | `/configuration/payment-service` |
| payment-service, profile prod | `/configuration/payment-service::prod` |

Quy ước này dễ mở rộng khi thêm service mới: chỉ cần tạo context riêng theo application, trong khi các giá trị dùng chung tiếp tục nằm ở `apps`.

## 19. Nguyên tắc sử dụng

- Dùng `root` để xác định namespace gốc, không dùng nó thay cho tên application.
- Dùng `default-context` cho thuộc tính thật sự dùng chung.
- Dùng application name để tách cấu hình riêng của từng service.
- Dùng `profile-separator` nhất quán để tạo context theo môi trường.
- Hiểu thứ tự ưu tiên từ application/profile cụ thể đến context dùng chung.
- Dùng Config Data import cho ứng dụng hiện đại; chỉ dùng bootstrap khi dự án chủ động duy trì legacy processing.
- Kiểm tra đường dẫn znode và PropertySource trước khi sửa code.
- Xem thay đổi ba thuộc tính này là migration namespace có kế hoạch.
- Bảo vệ root bằng ACL và không lưu secret dạng rõ nếu chưa có cơ chế quản lý phù hợp.
- Kiểm thử refresh và hành vi bean theo phiên bản Spring Cloud Zookeeper đang dùng.

Ba thuộc tính `root`, `default-context` và `profile-separator` định hình cách Spring Cloud Zookeeper tìm cấu hình. Root tạo vùng lưu trữ, default context cung cấp giá trị dùng chung, còn profile separator tạo biến thể theo môi trường. Khi kết hợp với application name và thứ tự PropertySource, nhóm có thể quản lý cấu hình nhiều ứng dụng trong một namespace rõ ràng, dễ phân quyền và dễ kiểm tra.

## Tài liệu tham khảo

- [Spring Cloud Zookeeper – Distributed Configuration](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)
- [Spring Cloud Zookeeper – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)

