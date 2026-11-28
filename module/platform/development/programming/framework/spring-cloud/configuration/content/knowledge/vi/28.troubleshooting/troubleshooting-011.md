# Consul Watch, Zookeeper watcher hoặc Vault lease không hoạt động như dự kiến

Khi thay đổi cấu hình hoặc secret mà ứng dụng không cập nhật như mong đợi, cần xác định chính xác cơ chế đang chịu trách nhiệm. Consul Config Watch phát hiện thay đổi trong KV bằng blocking query rồi phát refresh event. Spring Cloud Zookeeper Config có hành vi khác nhau theo phiên bản: một số release chỉ đọc lúc khởi động hoặc cần gọi refresh thủ công, trong khi release mới hơn có hỗ trợ theo dõi namespace cấu hình. Spring Cloud Vault quản lý vòng đời lease cho secret có lease; việc gia hạn lease không đồng nghĩa mọi bean trong ứng dụng được nạp lại.

Ba nhóm lỗi thường bị nhầm với nhau:

1. **Không phát hiện thay đổi:** watcher không chạy, không theo dõi đúng key/path, thiếu quyền hoặc phiên bản không hỗ trợ.
2. **Có tín hiệu nhưng cấu hình không đổi:** refresh event không tới Spring Context, client đọc nhầm context hoặc property source vẫn giữ giá trị cũ.
3. **Secret hết hạn hoặc không được gia hạn:** lease không renewable, token xác thực hết hạn, policy không cho renew hoặc lease đã đạt giới hạn TTL.

Hãy chẩn đoán từng chặng từ backend đến bean đang sử dụng giá trị. Không kết luận watcher lỗi chỉ vì một service vẫn hiển thị giá trị cũ.

## 1. Phân biệt ba cơ chế trước khi điều tra

| Cơ chế | Nó theo dõi hoặc quản lý điều gì? | Khi có thay đổi |
|---|---|---|
| Consul Config Watch | Các key/prefix cấu hình mà ứng dụng đang đọc từ Consul KV | Blocking query phát hiện dữ liệu mới và Spring Cloud Consul phát refresh event |
| Zookeeper Config watcher | Namespace cấu hình mà Spring Cloud Zookeeper Config đã nạp | Hành vi phụ thuộc release; có phiên bản chỉ nạp lúc startup hoặc dùng refresh thủ công |
| Vault lease lifecycle | Lease của dynamic secret và một số login token được quản lý | Gia hạn lease trước khi hết hạn; khi không thể gia hạn có thể cần lấy credential mới |

Consul Catalog Watch là cơ chế khác với Consul Config Watch. Catalog Watch theo dõi danh sách service và instance phục vụ service discovery; Config Watch theo dõi dữ liệu KV phục vụ cấu hình.

Tương tự, Spring Cloud Zookeeper Dependency Watcher theo dõi trạng thái UP/DOWN của service dependency. Nó không đồng nghĩa với watcher của namespace cấu hình. Vault KV secret tĩnh cũng không phải dynamic secret có lease renewable.

Trước khi sửa cấu hình, xác nhận ứng dụng thật sự dùng backend tương ứng. Một ứng dụng lấy cấu hình qua Spring Cloud Config Server/Git sẽ không tự động nhận sự kiện Consul hoặc ZooKeeper chỉ vì các thư viện đó có mặt trong hệ thống.

## 2. Quy trình chẩn đoán chung

~~~mermaid
flowchart TD
    A[Thay đổi key hoặc secret ở backend] --> B{Backend đã lưu giá trị mới?}
    B -->|Không| C[Kiểm tra thao tác ghi, path và quyền]
    B -->|Có| D{Watcher hoặc lease manager có hoạt động?}
    D -->|Không| E[Kiểm tra version, cấu hình, kết nối và ACL]
    D -->|Có| F{Spring nhận refresh hoặc lease event?}
    F -->|Không| G[Kiểm tra event pipeline, scheduler và logs]
    F -->|Có| H{Environment / credential đã cập nhật?}
    H -->|Không| I[Kiểm tra context, property source, token và backend response]
    H -->|Có| J{Bean hoặc connection pool dùng giá trị mới?}
    J -->|Không| K[Kiểm tra refresh scope, rebind và lifecycle]
    J -->|Có| L[Theo dõi ổn định và xác nhận hoàn tất]
~~~

Thực hiện theo thứ tự:

1. Đọc lại đúng key/path trực tiếp từ backend bằng CLI hoặc API quản trị.
2. Xác minh application name, profile, prefix/root và context mà client đang đọc.
3. Kiểm tra kết nối, authentication, ACL/policy và trạng thái cluster.
4. Kiểm tra log để biết watcher đã poll/watch và có nhận thấy thay đổi hay không.
5. Xác minh Spring đã phát/nhận refresh event hoặc lease manager đã xử lý lease.
6. Đọc lại giá trị từ Environment mà không in secret.
7. Kiểm tra bean, connection pool hoặc consumer thực tế có sử dụng giá trị mới.
8. Ghi nhận thời gian từ lúc ghi backend đến lúc ứng dụng áp dụng xong để so với SLA refresh.

## 3. Consul Config Watch không phát hiện thay đổi

Spring Cloud Consul Config Watch dùng blocking HTTP query để kiểm tra prefix cấu hình của ứng dụng. Khi Consul báo có dữ liệu liên quan thay đổi, Spring Cloud Consul phát một refresh event, tương đương việc yêu cầu endpoint refresh của ứng dụng.

Các thuộc tính chính trong Spring Cloud Consul 5.1.0:

| Thuộc tính | Giá trị mặc định được tài liệu công bố | Ý nghĩa |
|---|---:|---|
| `spring.cloud.consul.config.watch.enabled` | `true` | Bật/tắt Config Watch |
| `spring.cloud.consul.config.watch.delay` | `1000` ms | Độ trễ cố định giữa các lần gọi watch |
| `spring.cloud.consul.config.watch.wait-time` | `55` giây | Thời gian blocking query chờ thay đổi |
| `spring.cloud.consul.config.acl-token` | Không có mặc định chung | Token có quyền đọc KV cấu hình |

Ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      host: consul.internal
      port: 8500
      config:
        enabled: true
        prefix: config
        default-context: application
        name: orders-service
        watch:
          enabled: true
          delay: 1000
          wait-time: 55
~~~

Không cần khai báo lại giá trị mặc định trong production nếu không có chủ đích. Ví dụ trên giúp làm rõ các thông số đang được kiểm tra; hãy đồng bộ tên thuộc tính với release train của ứng dụng.

### 3.1. Kiểm tra watcher có bị tắt hoặc dùng sai loại watch

Kiểm tra cấu hình đã được nạp:

- `spring.cloud.consul.config.enabled` có đang bật không?
- `spring.cloud.consul.config.watch.enabled` có bị đặt thành `false` bởi environment variable, profile hoặc command line không?
- Ứng dụng có dùng `spring.cloud.consul.discovery.catalog-services-watch-delay` thay cho Config Watch không? Thuộc tính này theo dõi catalog service, không theo dõi KV config.
- Có nhiều Consul client/config source cùng tồn tại khiến ứng dụng đọc từ prefix khác không?

Đừng chỉ đọc application.yml trong repository. Giá trị runtime có thể bị ghi đè bởi biến môi trường, tham số command line hoặc Config Data source khác. Kiểm tra effective property theo cách không làm lộ token.

### 3.2. Kiểm tra key nằm trong prefix/context được theo dõi

Consul Watch chỉ quan sát dữ liệu liên quan đến cấu hình mà client truy vấn. Nếu ghi nhầm prefix, application name, profile hoặc data key, watcher có thể hoạt động bình thường nhưng không thấy thay đổi cần quan tâm.

Kiểm tra các thuộc tính:

- `spring.cloud.consul.config.prefix` hoặc `prefixes`.
- `spring.cloud.consul.config.default-context`.
- `spring.cloud.consul.config.name` so với `spring.application.name`.
- `spring.cloud.consul.config.profile-separator`.
- `spring.cloud.consul.config.format` và `data-key` nếu lưu YAML/Properties dạng blob.

Đọc trực tiếp key:

~~~bash
consul kv get -detailed <consul-kv-key>
~~~

Kiểm tra `ModifyIndex` có thay đổi sau thao tác ghi hay không. Nếu index không đổi, có thể lệnh ghi đang dùng sai key, dữ liệu không được cập nhật hoặc bạn đang đọc nhầm datacenter/Consul cluster.

### 3.3. Kiểm tra blocking query timeout

`watch.wait-time` là số giây Consul giữ blocking query. Tài liệu Spring Cloud Consul 5.1.0 nêu mặc định 55 giây và cần nhỏ hơn timeout mặc định 60 giây của Consul client. Nếu tăng wait-time nhưng không tăng timeout HTTP của client tương ứng, request có thể timeout trước khi Consul trả lời.

Triệu chứng:

- Log có socket timeout hoặc request timeout lặp lại.
- Watch task kết thúc bất thường và không tạo refresh event.
- Thay đổi chỉ được thấy sau một lần khởi động hoặc refresh thủ công.

Cách xử lý:

1. Kiểm tra timeout HTTP thực tế của Consul client.
2. Giữ `wait-time` thấp hơn timeout client một khoảng đủ cho network overhead.
3. Nếu cần wait-time dài hơn, cấu hình Consul client/HTTP client với timeout tương ứng theo API của release đang dùng.
4. Không giảm `delay` xuống quá thấp để bù timeout; điều đó có thể tăng số request và tải không cần thiết.

`delay` là fixed delay tính từ khi lần gọi trước kết thúc đến khi lần gọi kế tiếp bắt đầu. Nó không nhất thiết bằng thời gian từ lúc người vận hành ghi key đến lúc bean đổi giá trị.

### 3.4. Kiểm tra ACL và Consul cluster

Nếu client không có quyền đọc prefix, việc khởi động có thể báo lỗi hoặc watch không thể đọc dữ liệu mới. Kiểm tra token mà Config Watch sử dụng có quyền `read` trên đúng KV path. Đừng dùng token quản trị rộng chỉ để xác nhận watch.

Kiểm tra thêm:

- Consul agent/client kết nối đúng datacenter và cluster.
- Leader/raft cluster đang ổn định.
- DNS, TLS, proxy và network policy không cắt các request blocking.
- Token chưa hết hạn hoặc bị thu hồi.
- Các instance ứng dụng đều dùng cùng prefix và profile.

### 3.5. Phân biệt xóa key với cập nhật key

Không giả định hành vi khi xóa key giống hệt cập nhật giá trị. Khả năng phát refresh khi key bị xóa có thể khác theo release và cách cấu hình. Nếu bài toán phụ thuộc vào xóa key, kiểm tra thuộc tính và hành vi của đúng phiên bản Spring Cloud Consul; sau khi xóa, xác minh property đã biến mất khỏi Environment thay vì chỉ kiểm tra event đã phát.

## 4. Consul có phát refresh nhưng bean vẫn dùng giá trị cũ

Config Watch phát tín hiệu refresh; nó không thể làm mọi object Java tự thay đổi. Kiểm tra từng chặng:

1. Log cho thấy Config Watch phát hiện `ModifyIndex` mới.
2. Ứng dụng nhận refresh event.
3. `ContextRefresher` nạp lại property source từ Consul.
4. `Environment` trả giá trị mới.
5. Bean được rebind hoặc tạo lại theo cơ chế Spring Cloud Context.

Nếu Environment đã đổi nhưng bean vẫn cũ, xem bean có giữ giá trị trong field được gán một lần lúc khởi tạo không. Với bean cần được tạo lại, có thể dùng `@RefreshScope`:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class OrderPolicy {

    private final OrderProperties properties;

    public OrderPolicy(OrderProperties properties) {
        this.properties = properties;
    }

    public int maxItems() {
        return properties.getMaxItems();
    }
}
~~~

Đảm bảo `OrderProperties` được bind/rebind theo cơ chế đang sử dụng. Nếu một bean khác giữ bản sao giá trị hoặc giữ connection pool đã khởi tạo từ credential cũ, việc refresh một bean không tự thay thế mọi tài nguyên đã tạo.

## 5. Zookeeper watcher: xác minh khả năng theo phiên bản

Điểm đầu tiên cần kiểm tra là phiên bản Spring Cloud Zookeeper trong dependency tree. Hành vi watcher cấu hình có khác biệt rõ ràng giữa các release:

| Release được tài liệu Spring công bố | Hành vi Config namespace |
|---|---|
| Spring Cloud Zookeeper 5.0.2 | Cấu hình được đọc lúc startup; có thể gọi POST refresh; tài liệu ghi rõ watcher namespace chưa được triển khai |
| Spring Cloud Zookeeper 5.1.0 | Tài liệu ghi watcher namespace cấu hình đã có sẵn |
| Spring Cloud Zookeeper 4.1.3 | Tài liệu cũng mô tả watcher namespace đã có sẵn |

Vì vậy, nếu đang chạy 5.0.2, không nên tiếp tục tìm một thuộc tính bật watcher chưa được release đó hỗ trợ. Chọn một trong các cách: nâng cấp lên release có hỗ trợ watcher sau khi kiểm tra tương thích, hoặc chủ động gọi refresh endpoint theo quy trình vận hành.

Không nhầm Spring Cloud Zookeeper Dependency Watcher với Config watcher. `DependencyWatcherListener` nhận thay đổi trạng thái `CONNECTED`/`DISCONNECTED` của service dependency; nó không chứng minh config znode đã được theo dõi.

### 5.1. Xác minh Config Data import và kết nối ZooKeeper

Với Spring Boot Config Data API:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "zookeeper:zk-1.internal:2181"
  cloud:
    zookeeper:
      config:
        enabled: true
        root: config
        default-context: application
        profile-separator: ","
~~~

Nếu muốn cho phép ứng dụng khởi động khi ZooKeeper không khả dụng, có thể dùng `optional:zookeeper:`. Bỏ `optional:` khiến Config Data import thất bại khi không kết nối được ZooKeeper. Chỉ chọn optional nếu ứng dụng có fallback an toàn.

Đối chiếu:

- `spring.cloud.zookeeper.connect-string` và địa chỉ trong `spring.config.import`.
- Root namespace thực tế.
- `spring.application.name` hoặc `spring.cloud.zookeeper.config.name`.
- Default context và profile separator.
- Các context cụ thể nếu được truyền trực tiếp trong import.

Nếu ứng dụng dùng legacy bootstrap (`spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`), các thuộc tính bootstrap có thể phải đặt trong `bootstrap.yml`. Với Config Data import hiện đại, không cần tạo `bootstrap.yml` chỉ để khai báo Zookeeper.

### 5.2. Kiểm tra znode và ACL

Đọc đúng property node trong ZooKeeper:

~~~bash
zkCli.sh -server zk-1.internal:2181

get /config/orders-service,prod/orders.timeout
stat /config/orders-service,prod/orders.timeout
getAcl /config/orders-service,prod
~~~

Thay path ví dụ bằng root, application, profile separator và key thực tế của hệ thống. Xác minh:

- Node có tồn tại và chứa giá trị mới không?
- `version`/`mZxid`/`mtime` có thay đổi sau thao tác ghi không?
- Client có quyền `read` trên context và node con không?
- Danh tính ghi có quyền cập nhật đúng node không?
- Client có đang kết nối đúng ensemble, namespace hoặc chroot không?

Một thay đổi ở `/config/application` không nhất thiết là thay đổi ở context riêng `/config/orders-service,prod`. Nếu cập nhật nhầm node, watcher có thể không có gì để thông báo cho context đang được quan sát.

### 5.3. Kiểm tra session, connection state và watcher

Khi dùng watcher trong release có hỗ trợ, kiểm tra log Curator/ZooKeeper để xác định:

- Client đã kết nối và hoàn tất khởi tạo chưa?
- Có session expiration, authentication failure hoặc connection loss không?
- Watcher có đăng ký theo dõi context cần thiết không?
- Sự kiện node data changed có được nhận không?
- Sau khi reconnect, watcher có khôi phục theo dõi theo cơ chế của release đang dùng không?

ZooKeeper watch ở mức API thấp có semantics một lần kích hoạt; code tự triển khai phải đăng ký lại watch sau khi nhận event. Nếu dùng Curator recipe/cache hoặc watcher tích hợp của Spring Cloud, kiểm tra implementation và logs của đúng phiên bản thay vì tự giả định cần thêm một watcher thủ công.

Không tự tạo thêm listener cho mọi znode để chữa lỗi trước khi xác định watcher tích hợp có hỗ trợ release hiện tại. Nhiều watcher chồng lấp có thể tạo refresh event lặp và tăng tải.

### 5.4. Dùng refresh thủ công khi release không có watcher

Với release không hỗ trợ theo dõi namespace, có thể kích hoạt refresh theo endpoint được expose trong ứng dụng. Đường dẫn thường là endpoint refresh của Actuator; base path có thể được cấu hình khác nhau giữa dự án và release.

Ví dụ khi endpoint được expose dưới `/actuator/refresh`:

~~~bash
curl -i -X POST http://orders-service.internal/actuator/refresh
~~~

Chỉ expose endpoint trên mạng quản trị được bảo vệ bằng authentication/authorization. Nếu ứng dụng dùng base path hoặc management port riêng, thay URL theo cấu hình thật. Sau POST, xác minh response, Environment và bean; HTTP 200 chỉ chứng minh request được xử lý, không chứng minh mọi bean đã cập nhật.

## 6. Vault lease không được gia hạn

Vault lease là metadata gắn với secret được cấp, thường gồm `lease_id`, `lease_duration`/TTL và cờ `renewable`. Khi lease hết hạn, Vault có thể thu hồi credential hoặc dữ liệu liên quan. Spring Cloud Vault quản lý vòng đời lease cho secret được hỗ trợ và lên lịch gia hạn trước khi hết hạn.

Phân biệt:

| Loại dữ liệu | Có lease renewable không? | Cần kiểm tra |
|---|---|---|
| KV v1/KV v2 secret tĩnh | Thông thường không có lease động cho từng giá trị | Path, version, policy và refresh khi secret thay đổi |
| Dynamic database credentials | Thường có lease; phụ thuộc secrets engine và role | `lease_id`, TTL, `renewable`, quyền renew và max TTL |
| Dynamic cloud credentials | Có thể có lease hoặc token TTL tùy engine | Lease metadata, auth token và policy của engine |
| Static Vault token | Không tự được renew/revoke như token có lifecycle | Token TTL, cách cấp và quy trình thay token |
| Token đăng nhập do auth method cấp | Phụ thuộc token có renewable và session manager | Token lookup, TTL, renewable, auth role và renewal logs |

Không chạy điều tra lease renewal cho một giá trị KV tĩnh không có lease. Cũng không coi secret lease và Vault login token là cùng một đối tượng: token dùng để gọi Vault có vòng đời riêng với credential database mà Vault trả về.

### 6.1. Xác minh lifecycle management

Spring Cloud Vault 5.1.0 công bố:

- `spring.cloud.vault.config.lifecycle.enabled` mặc định `true`.
- `spring.cloud.vault.config.lifecycle.min-renewal` đặt khoảng thời gian tối thiểu trước khi thực hiện renewal.
- `spring.cloud.vault.config.lifecycle.expiry-threshold` đặt khoảng thời gian trước khi hết hạn mà lease được lên lịch renew.
- `spring.cloud.vault.config.lifecycle.lease-endpoints` chọn endpoint renew/revoke phù hợp với phiên bản Vault.
- `spring.cloud.vault.config.lifecycle.lease-strategy` điều khiển cách xử lý khi renewal lỗi; thuộc tính này có từ Spring Cloud Vault 4.1.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    vault:
      config:
        lifecycle:
          enabled: true
          min-renewal: 10s
          expiry-threshold: 1m
~~~

Các khoảng thời gian trên là ví dụ để minh họa, không phải giá trị phù hợp cho mọi lease. TTL ngắn, network latency và max TTL của Vault role cần được tính đến. Không tắt lifecycle management chỉ để loại bỏ log renewal lỗi; điều đó có thể khiến credential hết hạn mà ứng dụng không kịp xử lý.

Nếu cần đặt `lease-endpoints`, đối chiếu phiên bản Vault và Spring Cloud Vault. Tài liệu phân biệt endpoint legacy với endpoint leases mới; không sao chép giá trị từ một hệ thống cũ sang hệ thống mới mà không kiểm tra API đang được Vault hỗ trợ.

### 6.2. Kiểm tra lease metadata và quyền renew

Dùng Vault CLI để tra cứu lease trong môi trường quản trị:

~~~bash
vault lease lookup <lease-id>
~~~

Kiểm tra các trường:

- `lease_duration`: thời gian còn hiệu lực hoặc thời lượng được cấp.
- `renewable`: lease có thể gia hạn hay không.
- `lease_id`: đúng lease mà ứng dụng đang sử dụng không.
- TTL còn lại có đủ cho lịch renewal và thời gian xử lý lỗi không?

Kiểm tra token mà ứng dụng dùng để xác thực:

~~~bash
vault token lookup
~~~

Lệnh phải chạy bằng đúng danh tính/token được cấp cho workload hoặc trong phiên quản trị được phép. Không copy token, lease ID hoặc secret vào log, ticket hay chat.

Nếu `renewable=false`, renewal sẽ không thành công theo cách mong muốn. Nếu lease đã đạt max TTL hoặc bị revoke, cần cấp credential mới qua secrets engine thay vì tiếp tục thử renew lease cũ.

### 6.3. Kiểm tra policy và endpoint renew/revoke

Token có thể đọc secret nhưng không có quyền gia hạn lease. Đọc secret thành công lúc startup không chứng minh policy có đủ quyền cho lifecycle management.

Kiểm tra:

- Auth method có cấp token còn hiệu lực trong suốt thời gian chạy không?
- Token có quyền cần thiết trên endpoint renew/revoke mà Vault version sử dụng không?
- Policy có bị thay đổi sau khi ứng dụng khởi động không?
- `lease-endpoints` có phù hợp với API của Vault server không?
- Vault cluster có leader/standby và network route ổn định không?
- Clock giữa các node có sai lệch lớn khiến việc tính TTL/expiry không chính xác không?

Nếu dùng AppRole, Kubernetes auth hoặc cloud identity, kiểm tra cả quá trình lấy token mới. Renewal secret lease không thể thành công nếu token xác thực đã hết hạn hoặc bị revoke.

### 6.4. Phân biệt renew với cấp credential mới

Renew kéo dài thời hạn của lease hiện có nếu lease cho phép. Nó không nhất thiết tạo username/password mới. Khi lease không renewable, đạt max TTL hoặc bị revoke, ứng dụng cần lấy credential mới và chuyển consumer sang credential đó.

Đặc biệt với database connection pool:

1. Xác minh Vault đã cấp credential mới.
2. Xác minh Spring Environment hoặc property source có giá trị mới nếu tích hợp có cập nhật.
3. Xác minh bean cấu hình và DataSource/connection pool được rebind hoặc tái tạo.
4. Xác minh connection mới hoạt động bằng credential mới.
5. Đóng dần connection cũ trước khi Vault thu hồi credential cũ nếu chính sách cho phép.

Một lease được gia hạn thành công không đồng nghĩa connection pool đã thay password. Ngược lại, một credential mới được cấp cũng không tự động cập nhật object Java đã giữ giá trị cũ.

## 7. Bật log chẩn đoán có kiểm soát

Trong môi trường test hoặc khi điều tra ngắn hạn, có thể tăng log level cho package tích hợp:

~~~yaml
logging:
  level:
    org.springframework.cloud.consul: DEBUG
    org.springframework.cloud.zookeeper: DEBUG
    org.springframework.vault: DEBUG
~~~

Tên logger và mức chi tiết có thể khác theo release. Chỉ bật trong thời gian cần thiết, kiểm tra log trước khi chia sẻ và tắt lại sau khi điều tra.

Tìm các tín hiệu:

| Backend | Từ khóa/sự kiện cần tìm |
|---|---|
| Consul | Watch task start/stop, blocking query timeout, ACL/403, refresh event, Consul index |
| ZooKeeper | Connected/reconnected, session expired, NoAuth, NoNode, node data changed, refresh |
| Vault | Login/authentication, lease acquired, renewal scheduled/succeeded/failed, lease expired/revoked |
| Spring Context | Refresh event, property source reload, binding/rebind, refresh-scoped bean recreation |

Không log nội dung secret, Vault token, Consul ACL token, password hoặc toàn bộ Environment. Nếu cần xác định property nào thay đổi, chỉ ghi tên key không nhạy cảm và trạng thái hiện diện/phiên bản.

## 8. Phân biệt event không tới với bean không đổi

Dùng bảng này để khoanh vùng nhanh:

| Quan sát | Kết luận có khả năng | Bước kế tiếp |
|---|---|---|
| Backend CLI vẫn trả giá trị cũ | Ghi sai path, thao tác ghi thất bại hoặc đọc nhầm cluster | Sửa thao tác ghi và xác minh index/version |
| Backend có giá trị mới, không có watcher log | Watch bị tắt, không hỗ trợ trong release, sai path hoặc task chưa chạy | Kiểm tra version, dependency và cấu hình watch |
| Có watcher event nhưng không có refresh event | Event bridge hoặc Spring Context integration có vấn đề | Kiểm tra listener, scheduler và lỗi xử lý event |
| Có refresh event nhưng Environment cũ | Config source reload thất bại hoặc đang đọc context khác | Kiểm tra application/profile/root/prefix và backend response |
| Environment mới nhưng bean cũ | Bean không được rebind/recreate hoặc giữ bản sao giá trị | Kiểm tra ConfigurationProperties, RefreshScope và bean lifecycle |
| Vault lease renew thành công nhưng DB vẫn lỗi | Credential đã bị rotate/revoke ở nơi khác, pool giữ connection cũ hoặc credential không còn hợp lệ | Kiểm tra DB user, connection pool và lease metadata |
| Vault lease renew thất bại, token lookup cũng lỗi | Token/auth lifecycle hoặc network | Sửa authentication trước khi xử lý secret lease |

## 9. Kiểm thử tái hiện trong môi trường an toàn

Không thử nghiệm bằng cách xóa credential production hoặc cố tình để lease production hết hạn. Dùng môi trường test với key và secret giả:

### 9.1. Consul

1. Tạo key riêng cho ứng dụng test trong prefix đã cấu hình.
2. Khởi động client với Config Watch bật.
3. Ghi giá trị mới và xác nhận `ModifyIndex` tăng.
4. Quan sát blocking query kết thúc và watch tiếp tục chạy.
5. Xác nhận refresh event, Environment và bean thay đổi.
6. Thử đổi một key ngoài prefix để xác nhận client không refresh sai context.
7. Thử ACL read bị từ chối và timeout ngắn trong môi trường test.

### 9.2. ZooKeeper

1. Xác nhận release Spring Cloud Zookeeper có hỗ trợ config namespace watcher.
2. Tạo persistent znode trong context test đúng application/profile.
3. Khởi động client và đọc giá trị ban đầu.
4. Cập nhật znode, kiểm tra node metadata và logs watcher.
5. Xác nhận Environment và bean thay đổi.
6. Với release không hỗ trợ watcher, kiểm thử endpoint refresh thủ công thay vì chờ event tự động.
7. Thử session expiration, ACL read bị từ chối và reconnect trong môi trường test.

### 9.3. Vault

1. Dùng database secrets engine test cấp credential có TTL ngắn và renewable.
2. Xác nhận `lease_id`, `lease_duration` và `renewable` ngay sau khi cấp.
3. Để Spring Cloud Vault quản lý renewal; quan sát renewal trước expiry threshold.
4. Xác nhận token xác thực vẫn còn hiệu lực và policy cho phép renew.
5. Kiểm tra kết nối database vẫn hoạt động sau renewal.
6. Dùng role test có max TTL ngắn để kiểm tra tình huống lease không thể renew tiếp và quy trình cấp credential mới.
7. Xác nhận connection pool chuyển sang credential mới trước khi credential cũ bị revoke.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Consul key đổi nhưng client không refresh | Watch bị tắt, prefix sai hoặc blocking query timeout | Kiểm tra `watch.enabled`, prefix, `wait-time` và HTTP timeout |
| Consul chỉ phát hiện sau thời gian dài | `delay` lớn, blocking query chờ lâu hoặc scheduler bị nghẽn | Đo thời gian từng chặng và điều chỉnh delay/wait-time hợp lý |
| Consul Catalog thay đổi nhưng property không đổi | Đang quan sát Catalog Watch thay vì Config Watch | Bật và theo dõi `spring.cloud.consul.config.watch` |
| Consul 403 khi watch | ACL token thiếu quyền đọc KV prefix | Cấp quyền read đúng path và kiểm tra token runtime |
| ZooKeeper 5.0.2 không tự watch | Release không triển khai config namespace watcher | Dùng refresh thủ công hoặc nâng cấp release hỗ trợ |
| ZooKeeper Dependency Watcher không phát config refresh | Đang dùng watcher theo dõi UP/DOWN service dependency | Dùng đúng config watcher hoặc cơ chế refresh của release |
| ZooKeeper NoNode/NoAuth | Sai znode path hoặc ACL | Kiểm tra root/context/profile và ACL |
| ZooKeeper session expired | Network interruption, session timeout hoặc ensemble bất ổn | Kiểm tra connection state, reconnect và watcher re-registration |
| Vault lease không renewable | Secret engine/role cấp lease không renewable hoặc đã đạt max TTL | Cấp credential mới theo role và rotation flow |
| Vault renew bị 403 | Token thiếu quyền renew/revoke hoặc sai lease endpoint | Kiểm tra policy và `lease-endpoints` |
| Vault token hết hạn trước secret lease | Auth token lifecycle không được quản lý hoặc token tĩnh hết TTL | Sửa auth method/token renewal độc lập với secret lease |
| Vault lease renew được nhưng DB vẫn lỗi | Pool giữ connection cũ hoặc credential đã bị thu hồi | Rebind credential và recycle connection pool có kiểm soát |
| Refresh event có nhưng bean không đổi | Bean không refresh scope hoặc không được rebind | Kiểm tra Environment, ConfigurationProperties và lifecycle |

## 11. Runbook xử lý sự cố

Khi nhận cảnh báo watcher hoặc lease:

1. Ghi thời điểm thay đổi backend và thời điểm ứng dụng bắt đầu có lỗi.
2. Xác định backend, application, profile, context và phiên bản thư viện.
3. Đọc trực tiếp key hoặc lease metadata; không in secret.
4. Kiểm tra quyền truy cập và trạng thái kết nối từ chính workload.
5. Kiểm tra watcher/lease manager có chạy và có phát sinh lỗi không.
6. Kiểm tra Spring Environment đã thay đổi chưa.
7. Kiểm tra bean, DataSource, pool hoặc consumer có dùng giá trị mới chưa.
8. Nếu cần refresh thủ công, thực hiện qua endpoint nội bộ đã bảo vệ và theo dõi kết quả.
9. Nếu lease không thể renew, cấp credential mới theo quy trình rotation và chuyển consumer trước khi revoke credential cũ.
10. Ghi lại nguyên nhân gốc, thời gian phát hiện, thời gian phục hồi và thay đổi phòng ngừa.

Không khởi động lại hàng loạt instance như bước đầu tiên. Restart có thể nạp lại cấu hình hoặc xin credential mới, nhưng cũng có thể che giấu lỗi watcher, làm tăng tải backend và tạo gián đoạn đồng thời. Chỉ dùng restart khi đã xác định nó là biện pháp phục hồi phù hợp.

## 12. Checklist phòng ngừa

- [ ] Xác nhận ứng dụng đang đọc cấu hình từ Consul, ZooKeeper hay Vault.
- [ ] Ghi nhận phiên bản Spring Cloud và đối chiếu tính năng watcher của release.
- [ ] Consul Config Watch được bật và theo dõi đúng prefix/application/profile.
- [ ] Consul `wait-time` nhỏ hơn HTTP client timeout.
- [ ] Consul ACL token có quyền read đúng KV path.
- [ ] Phân biệt Consul Config Watch với Catalog Watch.
- [ ] Phân biệt ZooKeeper Config watcher với Dependency Watcher.
- [ ] ZooKeeper root, context, profile separator và ACL khớp với dữ liệu.
- [ ] Nếu release không có watcher, đã có quy trình refresh thủ công an toàn.
- [ ] Vault secret thực sự có lease trước khi điều tra renewal.
- [ ] Vault token lifecycle và secret lease lifecycle được kiểm tra riêng.
- [ ] `renewable`, TTL, max TTL và policy renew được xác minh.
- [ ] Có quy trình cấp credential mới và cập nhật connection pool.
- [ ] Bean cần cập nhật đã được thiết kế cho refresh/rebind.
- [ ] Logs không chứa secret, token hoặc toàn bộ Environment.
- [ ] Đã kiểm thử cập nhật, xóa, timeout, reconnect và lease expiry ở môi trường test.

## Tài liệu chính thức theo phiên bản

- [Spring Cloud Consul — Config Watch và các thuộc tính watch](https://docs.spring.io/spring-cloud-consul/reference/index.html)
- [Spring Cloud Consul — Common application properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Zookeeper 5.0.2 — Distributed Configuration](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)
- [Spring Cloud Zookeeper 5.1.0 — Distributed Configuration](https://docs.spring.io/spring-cloud-zookeeper/reference/5.1/config.html)
- [Spring Cloud Vault — Lease lifecycle management](https://docs.spring.io/spring-cloud-vault/reference/advanced-topics.html)
- [Spring Cloud Vault — Common application properties](https://docs.spring.io/spring-cloud-vault/reference/appendix.html)

Khi watcher hoặc lease không hoạt động, điều quan trọng là phân biệt cơ chế phát hiện thay đổi với cơ chế áp dụng thay đổi. Consul cần blocking query hoạt động đúng; ZooKeeper cần release có hỗ trợ config watcher hoặc quy trình refresh phù hợp; Vault cần lease renewable, token và policy hợp lệ. Sau cùng, luôn xác minh cả Environment lẫn bean/connection pool để biết ứng dụng đã thực sự chuyển sang cấu hình hoặc credential mới hay chưa.
