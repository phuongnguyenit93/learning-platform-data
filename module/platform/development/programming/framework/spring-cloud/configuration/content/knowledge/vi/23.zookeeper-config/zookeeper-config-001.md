# Nạp cấu hình từ Zookeeper bằng spring.config.import

Apache ZooKeeper có thể lưu các giá trị cấu hình trong một namespace phân cấp và cung cấp chúng trực tiếp cho `Environment` của ứng dụng Spring Boot. Spring Cloud Zookeeper Config tích hợp ZooKeeper như một nguồn cấu hình bên ngoài, giúp ứng dụng đọc thuộc tính theo tên application và profile ngay trong quá trình khởi động.

Với Spring Boot hiện đại, cách kích hoạt được khuyến nghị là khai báo `spring.config.import` với scheme `zookeeper:`. Ứng dụng dùng dependency `spring-cloud-starter-zookeeper-config`, kết nối đến ZooKeeper ensemble và nạp các property source tương ứng. Trong mô hình này, ứng dụng đọc cấu hình trực tiếp từ ZooKeeper; không cần dựng Spring Cloud Config Server chỉ để truy xuất các giá trị đó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Spring Cloud Zookeeper Config và sự khác nhau với Spring Cloud Config Server/Client.
- Thêm dependency `spring-cloud-starter-zookeeper-config`.
- Kích hoạt nguồn cấu hình bằng `spring.config.import=zookeeper:`.
- Phân biệt import bắt buộc với `optional:zookeeper:`.
- Cấu hình ZooKeeper connect string và hiểu thứ tự ưu tiên giữa import location với `spring.cloud.zookeeper.connect-string`.
- Tổ chức znode theo root, application và profile.
- Hiểu thứ tự ưu tiên của bốn property source mặc định.
- Chỉ định context tùy chỉnh và thay đổi root, default context, profile separator.
- Kiểm tra dữ liệu, refresh cấu hình, bảo vệ ACL và chẩn đoán lỗi kết nối.

## 2. Spring Cloud Zookeeper Config là gì?

ZooKeeper là dịch vụ phối hợp phân tán có namespace dạng cây. Mỗi znode có thể lưu dữ liệu và có các znode con. Spring Cloud Zookeeper Config đọc các context trong namespace này, chuyển dữ liệu thành các `PropertySource` và đưa vào Spring `Environment`.

Spring Cloud Zookeeper Config là một lựa chọn thay thế cho mô hình Config Server/Config Client khi tổ chức đã vận hành ZooKeeper và muốn ứng dụng đọc cấu hình trực tiếp từ đó.

```mermaid
flowchart LR
    App[Spring Boot application] -->|spring.config.import=zookeeper:| Client[Spring Cloud Zookeeper Config]
    Client -->|ZooKeeper protocol / Curator| Ensemble[(ZooKeeper ensemble)]
    Ensemble --> Root[/config namespace/]
    Root --> Shared[application contexts]
    Root --> Service[application-specific contexts]
    Client --> Env[Spring Environment]
    Env --> Beans[@ConfigurationProperties / @Value / beans]
```

Luồng cơ bản:

1. Spring Boot đọc cấu hình sớm, trong đó có `spring.config.import` và `spring.application.name`.
2. Config Data loader của Spring Cloud Zookeeper tạo kết nối đến ZooKeeper.
3. Client xác định các context chung, context riêng application và context theo profile.
4. Dữ liệu trong các znode được chuyển thành property source.
5. Spring Boot hợp nhất property source theo thứ tự ưu tiên.
6. `Environment` cung cấp giá trị hiệu lực cho `@ConfigurationProperties`, `@Value` và các bean.

ZooKeeper Config không phải là Git repository và không tự cung cấp quy trình pull request, review hoặc lịch sử commit như Git. Nếu cần kiểm soát thay đổi, cần thiết kế pipeline cập nhật znode, audit và backup riêng.

## 3. Thêm dependency

Dependency chính là `spring-cloud-starter-zookeeper-config`.

### Maven

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-config</artifactId>
</dependency>
```

### Gradle

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-zookeeper-config'
}
```

Hãy quản lý phiên bản bằng Spring Cloud BOM tương thích với dòng Spring Boot của ứng dụng. Không tự chọn phiên bản starter độc lập khi dự án đã dùng BOM. Kiểm tra hướng dẫn tương thích ZooKeeper client/server theo release train, đặc biệt nếu hệ thống vẫn chạy ZooKeeper 3.4.

## 4. Kích hoạt bằng `spring.config.import`

Spring Boot 2.4 trở lên hỗ trợ Config Data API qua `spring.config.import`. Đây là cách mặc định hiện nay để nạp cấu hình từ ZooKeeper.

Ví dụ trong `application.yml`:

```yaml
spring:
  application:
    name: orders
  config:
    import: "zookeeper:"
```

Nếu không chỉ định địa chỉ, Config Data import dùng địa chỉ mặc định `localhost:2181`.

Có thể chỉ định ZooKeeper connect string ngay trong import:

```yaml
spring:
  application:
    name: orders
  config:
    import: "zookeeper:zk-1.internal:2181"
```

Hoặc cấu hình connect string bằng thuộc tính riêng:

```yaml
spring:
  application:
    name: orders
  config:
    import: "zookeeper:"
  cloud:
    zookeeper:
      connect-string: "zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181"
```

Connect string của một ensemble có thể chứa nhiều địa chỉ host:port, phân tách bằng dấu phẩy. Nếu địa chỉ được đặt trực tiếp trong `spring.config.import`, địa chỉ trong import có độ ưu tiên cao hơn `spring.cloud.zookeeper.connect-string`.

## 5. Chọn import bắt buộc hay optional

Hai cách khai báo dưới đây có hành vi khác nhau khi ZooKeeper không thể truy cập.

**Import bắt buộc:**

```yaml
spring:
  config:
    import: "zookeeper:zk-1.internal:2181"
```

Nếu không thể kết nối hoặc nạp nguồn cấu hình bắt buộc, quá trình khởi động có thể thất bại. Dùng cách này khi ứng dụng không thể chạy an toàn nếu thiếu cấu hình từ ZooKeeper.

**Import optional:**

```yaml
spring:
  config:
    import: "optional:zookeeper:zk-1.internal:2181"
```

Tiền tố `optional:` cho phép ứng dụng tiếp tục xử lý khi nguồn import không khả dụng. Chỉ dùng khi ứng dụng có giá trị dự phòng đã được kiểm thử và việc thiếu cấu hình từ xa không tạo ra hành vi nguy hiểm.

Ví dụ, nếu ZooKeeper chứa URL của dịch vụ thanh toán hoặc chính sách giới hạn giao dịch, khởi động với giá trị mặc định không phù hợp có thể gây lỗi nghiệp vụ. Trong trường hợp đó, nên để import bắt buộc để phát hiện sự cố sớm.

Không nhầm `optional:` với việc ZooKeeper luôn có sẵn dữ liệu. Import optional không tạo ra znode còn thiếu và cũng không đảm bảo giá trị fallback là đúng.

## 6. Cấu hình namespace mặc định

Spring Cloud Zookeeper Config lưu cấu hình trong namespace `/config` theo mặc định. Nó tạo các property source dựa trên tên application và active profile.

Các thuộc tính mặc định quan trọng:

| Thuộc tính | Giá trị mặc định | Ý nghĩa |
| --- | --- | --- |
| `spring.cloud.zookeeper.config.enabled` | `true` | Bật/tắt Zookeeper Config |
| `spring.cloud.zookeeper.config.root` | `config` | Root namespace chứa cấu hình |
| `spring.cloud.zookeeper.config.default-context` | `application` | Context dùng chung cho các application |
| `spring.cloud.zookeeper.config.name` | Giá trị `spring.application.name` | Tên application dùng để tìm context riêng |
| `spring.cloud.zookeeper.config.profile-separator` | `,` | Ký tự phân tách tên application/context với profile |
| `spring.cloud.zookeeper.connect-string` | `localhost:2181` | Địa chỉ ZooKeeper nếu import không chỉ định location |

Ví dụ thay root và default context:

```yaml
spring:
  application:
    name: orders
  config:
    import: "zookeeper:"
  cloud:
    zookeeper:
      config:
        root: configuration
        default-context: shared
        profile-separator: "::"
```

Khi đó, root là `/configuration`, context dùng chung có tên `shared`, và profile separator là `::`. Các tên context cụ thể được ghép theo cấu hình này.

Với Config Data API, các thuộc tính này có thể đặt trong `application.yml`. Nếu dự án bật legacy bootstrap processing, chẳng hạn dùng `spring.cloud.bootstrap.enabled=true`, `spring.config.use-legacy-processing=true` hoặc `spring-cloud-starter-bootstrap`, tài liệu Spring Cloud Zookeeper yêu cầu đặt các thuộc tính tùy chỉnh liên quan vào `bootstrap.yml` thay vì `application.yml`.

## 7. Bốn context tự động được nạp

Giả sử:

```yaml
spring:
  application:
    name: testApp
  profiles:
    active: dev
  config:
    import: "zookeeper:"
```

Với root mặc định `config`, default context `application` và profile separator `,`, Spring Cloud Zookeeper tạo bốn property source theo thứ tự từ cụ thể nhất đến tổng quát nhất:

| Thứ tự | Context trong ZooKeeper | Phạm vi |
| --- | --- | --- |
| 1 | `/config/testApp,dev` | Riêng application `testApp`, profile `dev` |
| 2 | `/config/testApp` | Riêng application `testApp`, mọi profile |
| 3 | `/config/application,dev` | Mọi application, profile `dev` |
| 4 | `/config/application` | Mọi application và profile |

Property source ở trên có độ ưu tiên cao hơn property source ở dưới. Vì vậy, nếu cùng một khóa xuất hiện trong nhiều context, giá trị trong `/config/testApp,dev` thắng giá trị ở `/config/testApp`, `/config/application,dev` và `/config/application`.

`default-context` là tên context dùng chung, mặc định `application`; nó không phải tên Spring profile `default`. Tương tự, `spring.application.name` xác định context riêng của ứng dụng, không phải tên cluster ZooKeeper.

## 8. Tổ chức znode cho cấu hình

Có thể tổ chức namespace theo application và profile như sau:

```text
/
└── config
    ├── application
    │   ├── platform.http.connect-timeout
    │   └── platform.logging.level
    ├── application,dev
    │   └── platform.logging.level
    ├── orders
    │   ├── orders.api.max-retries
    │   └── orders.checkout.enabled
    └── orders,dev
        ├── orders.api.base-url
        └── orders.checkout.enabled
```

Mỗi context là một znode gốc cho một property source. Các znode con lưu giá trị thuộc tính. Ví dụ:

- `/config/application/platform.http.connect-timeout` chứa `2s`.
- `/config/application/platform.logging.level` chứa `INFO`.
- `/config/orders/orders.api.max-retries` chứa `3`.
- `/config/orders,dev/orders.api.base-url` chứa URL dịch vụ dùng trong môi trường dev.

Đặt giá trị trong context chung nếu nhiều ứng dụng cần dùng. Đặt giá trị trong context riêng application nếu chỉ một dịch vụ sử dụng. Đặt giá trị trong context profile khi nó chỉ phù hợp với một môi trường.

Không đưa tất cả cấu hình vào một context chung nếu các ứng dụng có ranh giới bảo mật khác nhau. ACL trên znode cần phản ánh đúng ai được đọc và ai được cập nhật từng nhánh.

## 9. Tạo và kiểm tra znode bằng ZooKeeper CLI

Ví dụ sau minh họa cách tạo context và lưu từng thuộc tính bằng `zkCli.sh`. Các lệnh phải được chạy trong môi trường đã cài ZooKeeper CLI và kết nối đúng ensemble.

Tạo root và context:

```text
create /config ""
create /config/application ""
create /config/orders ""
create /config/orders,dev ""
```

Tạo các property node:

```text
create /config/application/platform.http.connect-timeout "2s"
create /config/application/platform.logging.level "INFO"
create /config/orders/orders.api.max-retries "3"
create /config/orders,dev/orders.api.base-url "https://orders-dev.internal"
```

Nếu context hoặc root đã tồn tại, không tạo lại; dùng `set` để cập nhật dữ liệu của znode đã có:

```text
set /config/orders/orders.api.max-retries "5"
```

Đọc và liệt kê:

```text
ls /config
ls /config/orders
get /config/orders/orders.api.max-retries
```

Lưu ý:

- Parent znode phải tồn tại trước khi tạo znode con bằng lệnh `create` thông thường.
- Dữ liệu cấu hình nên dùng persistent znode; không dùng ephemeral znode cho cấu hình cần tồn tại qua lần client disconnect.
- Giá trị znode là dữ liệu byte. Với cấu hình văn bản, dùng encoding UTF-8 nhất quán.
- Không lưu file nhị phân lớn hoặc toàn bộ artifact trong ZooKeeper; chỉ lưu các giá trị cấu hình nhỏ.
- Không dùng lệnh `deleteall` hoặc xóa root khi đang vận hành nếu chưa có kế hoạch khôi phục và xác nhận phạm vi ảnh hưởng.

## 10. Cấu hình import chỉ định context

Thông thường Config Client tự tính bốn context từ application name và profile. Nếu muốn nạp một tập context cụ thể, có thể khai báo path trong `spring.config.import`.

Ví dụ:

```yaml
spring:
  config:
    import: "optional:zookeeper:zk-1.internal:2181/contextone;/context/two"
```

Trong ví dụ, Config Data import chỉ nạp các context `/contextone` và `/context/two`, không dùng bốn context tự động theo tên application/profile.

Danh sách context được phân tách bằng dấu chấm phẩy (`;`). Vì vậy, nên đặt toàn bộ giá trị import trong dấu nháy ở YAML để tránh lỗi phân tích cú pháp hoặc hiểu nhầm chuỗi.

Chỉ định context tường minh phù hợp khi tổ chức đã có namespace riêng theo domain hoặc muốn tái sử dụng cấu trúc znode hiện có. Cần tài liệu hóa thứ tự các context và kiểm thử trường hợp trùng khóa để xác nhận property source nào thắng.

## 11. Thay đổi tên application và profile

Mặc định, `spring.cloud.zookeeper.config.name` lấy giá trị từ `spring.application.name`.

Ví dụ:

```yaml
spring:
  application:
    name: orders
  profiles:
    active: prod
  config:
    import: "zookeeper:"
```

Client sẽ tìm context riêng cho `orders` và profile `prod`. Nếu muốn dùng một tên lookup khác với application name:

```yaml
spring:
  application:
    name: orders-api
  cloud:
    zookeeper:
      config:
        name: orders
```

Khi đó tên context riêng lấy từ `orders`. Chỉ dùng thuộc tính này nếu có chủ đích chia sẻ cấu hình hoặc duy trì tên namespace cũ; nếu không, việc tách `spring.application.name` và tên lookup có thể khiến nhóm vận hành khó xác định nguồn dữ liệu.

Profile separator mặc định là dấu phẩy. Nếu đổi sang `::`, các context profile-specific sẽ dùng separator mới. Tên znode trong ZooKeeper phải được cập nhật đồng bộ với cấu hình client.

## 12. Bind giá trị vào Spring bean

Sau khi Config Data import nạp các property source, ứng dụng có thể sử dụng cấu hình như các nguồn khác trong Spring `Environment`.

Ví dụ dữ liệu trong ZooKeeper:

```text
/config/orders/orders.api.base-url = https://orders.internal
/config/orders/orders.api.max-retries = 4
/config/orders/orders.api.read-timeout = 3s
```

Bean cấu hình:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders.api")
public record OrdersApiProperties(
        URI baseUrl,
        int maxRetries,
        Duration readTimeout) {
}
```

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(OrdersApiProperties.class)`. Spring Boot chuyển giá trị dạng chuỗi trong `Environment` sang kiểu Java tương ứng nếu có converter phù hợp.

Với cấu hình quan trọng, nên dùng validation để phát hiện thiếu URL, số lần retry âm hoặc timeout không hợp lệ ngay khi khởi động. Không để ứng dụng âm thầm dùng giá trị mặc định không an toàn khi context trong ZooKeeper bị thiếu.

## 13. ZooKeeper Config và Spring Cloud Config Server khác nhau thế nào?

| Tiêu chí | Spring Cloud Zookeeper Config | Spring Cloud Config Server/Client |
| --- | --- | --- |
| Nơi lưu | Znode trong ZooKeeper | Git, filesystem, Vault, JDBC và các backend được hỗ trợ |
| Client kết nối | Ứng dụng kết nối trực tiếp đến ZooKeeper | Client gọi Config Server qua HTTP(S) |
| Phân phối cấu hình | Property source được nạp trực tiếp vào `Environment` | Config Server tổng hợp `Environment` rồi trả cho client |
| Version control | Không có commit/tag như Git mặc định | Có thể dùng Git branch, tag, commit |
| ACL | ZooKeeper ACL trên znode và quyền mạng | Bảo vệ Config Server, backend và quyền của client |
| Hạ tầng | Cần ZooKeeper ensemble | Cần Config Server và backend tương ứng |
| Phù hợp | Hệ thống đã dùng ZooKeeper và cần cấu hình nhỏ, truy cập trực tiếp | Hệ thống cần repository quản lý phiên bản, API tập trung hoặc nhiều loại backend |

Không nên chọn ZooKeeper chỉ vì nó đã có trong hệ thống discovery. Discovery và Config là hai mục đích khác nhau dù cùng dùng một ensemble. Nếu dữ liệu cấu hình cần lịch sử review, rollback theo commit và quản trị thay đổi qua pull request, Git backend có thể phù hợp hơn.

## 14. Refresh sau khi thay đổi znode

Việc cập nhật znode không đồng nghĩa mọi bean trong ứng dụng tự động thay đổi ngay lập tức. Cần phân biệt ba giai đoạn:

1. Giá trị trong ZooKeeper được cập nhật.
2. Config Client nạp lại property source vào `Environment`.
3. Bean sử dụng giá trị mới thông qua rebind, refresh scope hoặc cơ chế cập nhật riêng.

Tài liệu Spring Cloud Zookeeper mô tả việc nạp cấu hình khi ứng dụng khởi động và hỗ trợ gửi HTTP `POST` đến endpoint refresh để tải lại cấu hình. Với Spring Boot Actuator/Spring Cloud Context, endpoint thường được expose dưới management path, ví dụ `/actuator/refresh`, tùy phiên bản và cấu hình management.

Ví dụ:

```bash
curl -X POST http://localhost:8080/actuator/refresh
```

Endpoint refresh có thể làm thay đổi cấu hình runtime. Chỉ expose khi cần, bảo vệ bằng authentication/authorization và giới hạn network access.

### Theo dõi thay đổi znode

ZooKeeper hỗ trợ watch ở cấp client. Tuy nhiên, việc Spring Cloud Zookeeper Config tự động theo dõi namespace và phát refresh phụ thuộc phiên bản. Tài liệu Spring Cloud Zookeeper 5.0.2 hiện hành mô tả hỗ trợ watching; một số tài liệu của release cũ ghi rõ tính năng này chưa được triển khai.

Vì vậy, hãy kiểm tra tài liệu đúng release train và thử nghiệm thay đổi znode trong môi trường staging trước khi dựa vào watch cho production. Nếu chưa xác nhận watcher hoạt động, dùng quy trình refresh tường minh hoặc rollout ứng dụng.

Ngay cả khi `Environment` đã được refresh, singleton bean giữ giá trị từ constructor có thể vẫn giữ state cũ. Dùng `@RefreshScope` hoặc cơ chế rebind phù hợp cho bean cần cập nhật; tài nguyên như connection pool có thể cần xử lý riêng.

## 15. Bảo vệ ZooKeeper bằng ACL

ZooKeeper ACL kiểm soát ai được đọc, ghi, tạo, xóa hoặc quản lý znode. Không nên để mọi ứng dụng dùng `world:anyone` với quyền đọc/ghi trên toàn bộ `/config`.

Nguyên tắc:

- Dùng authentication scheme phù hợp với nền tảng, chẳng hạn digest hoặc SASL/Kerberos theo kiến trúc.
- Cấp quyền `READ` cho ứng dụng chỉ cần nạp cấu hình.
- Giới hạn quyền `CREATE`, `WRITE` và `DELETE` cho pipeline hoặc nhóm vận hành chịu trách nhiệm thay đổi cấu hình.
- Tách ACL theo application/context nếu các service có mức độ tin cậy khác nhau.
- Không dùng chung username/password quản trị cho mọi service.
- Bảo vệ credential và không ghi nó vào Git, image hoặc log.
- Kết hợp ACL với TLS, network policy và giới hạn truy cập đến client port của ZooKeeper.

Spring Cloud Zookeeper cho phép thêm thông tin xác thực ACL thông qua Curator/ZooKeeper client. Tài liệu chính thức minh họa việc tùy biến `CuratorFramework` và thêm auth info trong giai đoạn bootstrap, sau đó đăng ký lớp cấu hình qua cơ chế bootstrap configuration. Với Config Data import hiện đại, cần kiểm tra cách đăng ký hoặc tùy biến Curator client phù hợp phiên bản đang dùng; không mặc định rằng một ví dụ `@BootstrapConfiguration` cũ có thể áp dụng nguyên trạng cho mọi ứng dụng Config Data.

Thông tin xác thực phải được gắn vào client trước khi client đọc các znode được bảo vệ. `username` và `password` phải lấy từ secret manager hoặc nguồn bảo mật; không hard-code giá trị thật. Cần kiểm tra ACL của từng znode và xác nhận ứng dụng chỉ đọc được context được phép.

## 16. Độ bền và vận hành ZooKeeper ensemble

ZooKeeper thường được triển khai thành ensemble có quorum. Khả năng đọc/ghi và tính sẵn sàng phụ thuộc số node, trạng thái leader/follower, network và dung lượng lưu trữ.

Các nguyên tắc vận hành:

- Triển khai số lượng server phù hợp để duy trì quorum khi một node lỗi; mô hình phổ biến dùng 3 hoặc 5 node.
- Đặt các node trên failure domain khác nhau nếu hạ tầng cho phép.
- Giám sát trạng thái quorum, latency, request rate, session expiration và dung lượng snapshot/transaction log.
- Cấu hình connect string chứa các thành viên ensemble, không chỉ một node đơn lẻ trong production.
- Đặt timeout/retry phù hợp với network và startup requirements.
- Backup dữ liệu ZooKeeper theo quy trình snapshot/backup được hỗ trợ và thử restore.
- Không dùng ZooKeeper làm kho lưu file lớn hoặc dữ liệu thay đổi liên tục với tần suất cao.

ZooKeeper có thể lưu cấu hình, nhưng không thay thế hệ thống quản lý phiên bản. Nếu cần audit ai thay đổi giá trị nào, lúc nào và rollback về commit trước, hãy xây dựng pipeline cập nhật có log hoặc dùng backend có version control.

## 17. Chẩn đoán lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Ứng dụng không kết nối được ZooKeeper | Sai connect string, DNS, firewall, ensemble mất quorum hoặc port sai | Kiểm tra connect string, network và trạng thái ensemble |
| Import không được kích hoạt | Thiếu starter hoặc thiếu `spring.config.import` | Kiểm tra dependency và log Config Data |
| Client đọc context rỗng | Sai `spring.application.name`, profile, root hoặc default context | Đối chiếu các path `/config/...` thực tế trong ZooKeeper |
| Giá trị application không ghi đè giá trị chung | Context cụ thể không tồn tại hoặc tên context sai | Kiểm tra application name và profile separator |
| Profile-specific value không được nạp | Active profile không đúng hoặc znode dùng separator khác | Kiểm tra `spring.profiles.active` và `profile-separator` |
| App vẫn chạy khi ZooKeeper lỗi | Import có tiền tố `optional:` hoặc fallback được cấu hình | Xác nhận chính sách required/optional và giá trị dự phòng |
| `NoNode` hoặc `NONODE` | Parent/context znode chưa được tạo hoặc path sai | Tạo parent trước và kiểm tra chính tả path |
| `NoAuth` hoặc `NoAuthException` | ACL không cấp quyền đọc hoặc auth info không được gửi | Kiểm tra auth scheme, identity và ACL của từng context |
| Cập nhật znode nhưng bean chưa đổi | Client chưa refresh hoặc bean giữ state cũ | Gọi refresh, kiểm tra Environment và refresh scope/rebind |
| Chỉ một số instance nhận giá trị mới | Một số instance không refresh, cache/session lỗi hoặc đang kết nối ensemble khác | Kiểm tra log và trạng thái từng replica |
| Import location không dùng connect-string đã đặt | Location trong `spring.config.import` có độ ưu tiên cao hơn | Kiểm tra URI/location ngay trong import |

## 18. Quy trình triển khai từng bước

1. **Chọn phiên bản:** xác định Spring Boot, Spring Cloud release train và ZooKeeper version tương thích.
2. **Cấp dependency:** thêm `spring-cloud-starter-zookeeper-config` và quản lý phiên bản qua BOM.
3. **Tạo ensemble:** xác nhận quorum, DNS, port, TLS/authentication và connect string.
4. **Tạo namespace:** chuẩn bị root context, application context và profile-specific context.
5. **Đặt dữ liệu:** tạo persistent znode cho các key cần thiết, kiểm tra UTF-8 và giá trị.
6. **Cấu hình import:** khai báo `spring.config.import=zookeeper:` hoặc import location phù hợp.
7. **Đặt application/profile:** xác nhận `spring.application.name` và active profile khớp context.
8. **Kiểm tra precedence:** tạo một khóa trùng ở context chung và context riêng, xác nhận giá trị cụ thể thắng.
9. **Bind bean:** dùng `@ConfigurationProperties` và validation.
10. **Bảo vệ ACL:** cấp quyền đọc tối thiểu cho client và quyền ghi riêng cho pipeline.
11. **Kiểm tra refresh:** thay znode trong staging, gọi refresh hoặc xác minh watcher theo phiên bản.
12. **Kiểm tra nhiều replica:** xác nhận tất cả instance nạp đúng cấu hình và có chính sách fallback phù hợp.
13. **Thiết lập backup/monitoring:** giám sát quorum, latency, session và khả năng restore.

## 19. Checklist trước khi đưa vào production

- [ ] Đã thêm `spring-cloud-starter-zookeeper-config` và dùng Spring Cloud BOM tương thích.
- [ ] `spring.config.import` khai báo đúng scheme `zookeeper:`.
- [ ] Đã chọn import bắt buộc hay optional theo mức độ quan trọng của cấu hình.
- [ ] Connect string chứa các node ensemble cần thiết.
- [ ] `spring.application.name` khớp application context trong ZooKeeper.
- [ ] Active profile và profile separator khớp các znode đã tạo.
- [ ] Root và default context được tài liệu hóa.
- [ ] Các context chung, riêng application và profile-specific có thứ tự ưu tiên đúng.
- [ ] Znode cấu hình dùng persistent node và dữ liệu có kích thước phù hợp.
- [ ] ACL chỉ cấp quyền cần thiết; không dùng `world:anyone` với quyền ghi.
- [ ] Credential được quản lý an toàn và TLS/network policy phù hợp.
- [ ] Đã kiểm thử `@ConfigurationProperties` và validation.
- [ ] Đã kiểm thử refresh và hành vi bean sau khi thay đổi znode.
- [ ] Đã xác minh watcher có được hỗ trợ trong đúng phiên bản đang chạy hay chưa.
- [ ] Đã kiểm tra mọi replica và tình huống ZooKeeper mất kết nối.
- [ ] Có backup, restore test, audit và quy trình rollback cấu hình.

## 20. Tài liệu tham khảo

- [Spring Cloud Zookeeper — Distributed Configuration](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)
- [Spring Cloud Zookeeper — Quick Start](https://docs.spring.io/spring-cloud-zookeeper/reference/)
- [Spring Cloud Zookeeper — Configuration Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Apache ZooKeeper — Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache ZooKeeper — Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
