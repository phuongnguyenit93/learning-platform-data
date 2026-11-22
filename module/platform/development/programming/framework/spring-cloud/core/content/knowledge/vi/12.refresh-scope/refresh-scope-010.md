# extra-refreshable, never-refreshable và trường hợp HikariDataSource

Bài học thuộc chương **Refresh Scope** của module **SPRING_CLOUD_CORE**. Spring Cloud Context có thể làm mới một số bean khi cấu hình thay đổi. Ngoài việc đánh dấu bean trực tiếp bằng `@RefreshScope`, ứng dụng còn có hai thuộc tính để kiểm soát các bean được đưa vào hoặc loại khỏi cơ chế refresh: `spring.cloud.refresh.extra-refreshable` và `spring.cloud.refresh.never-refreshable`.

Hai thuộc tính này giải quyết hai nhu cầu khác nhau:

- **extra-refreshable:** bổ sung bean theo tên hoặc class name vào refresh scope, thường hữu ích khi bean đến từ thư viện hoặc auto-configuration mà ứng dụng không tiện sửa định nghĩa.
- **never-refreshable:** chỉ định bean theo tên hoặc class name không được refresh/rebind theo cơ chế Spring Cloud.
- **HikariDataSource:** là ngoại lệ quan trọng; `com.zaxxer.hikari.HikariDataSource` nằm trong danh sách `never-refreshable` mặc định. Tài liệu Spring Cloud khuyến nghị chọn DataSource implementation khác nếu cần refresh DataSource.

Cần hiểu rõ phạm vi của mỗi thuộc tính trước khi cấu hình. Đưa nhầm một pool kết nối, client giữ socket hoặc bean có state vào refresh scope có thể làm gián đoạn request đang chạy, tạo tài nguyên trùng lặp hoặc khiến ứng dụng giữ kết nối cũ. Ngược lại, loại một bean khỏi refresh khi bean đó thực sự cần cập nhật có thể khiến ứng dụng tiếp tục dùng cấu hình cũ.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích refresh scope hoạt động qua scoped proxy và target cache.
2. Phân biệt bean được đánh dấu `@RefreshScope` trực tiếp với bean được thêm qua `extra-refreshable`.
3. Cấu hình `spring.cloud.refresh.extra-refreshable` bằng bean name hoặc fully qualified class name.
4. Cấu hình `spring.cloud.refresh.never-refreshable` để giữ bean khỏi refresh/rebind.
5. Hiểu rằng danh sách `never-refreshable` mặc định có `HikariDataSource`.
6. Giữ ngoại lệ Hikari khi ứng dụng ghi đè danh sách `never-refreshable`.
7. Giải thích vì sao không nên ép HikariDataSource vào `extra-refreshable`.
8. Chọn chiến lược phù hợp khi database URL, credential hoặc pool setting thay đổi.
9. Kiểm thử bean có được tạo lại hay giữ nguyên sau refresh.
10. Bảo vệ endpoint refresh và quan sát lỗi khi target mới khởi tạo thất bại.

## 2. Refresh Scope hoạt động như thế nào?

Spring Cloud Context cung cấp `RefreshScope`. Bean trong scope này được truy cập qua một **scoped proxy**. Target bean thật được khởi tạo khi proxy nhận lời gọi đầu tiên cần target; scope giữ target trong cache. Khi refresh, cache entry bị invalidate. Lần gọi tiếp theo qua proxy sẽ tạo target mới.

~~~mermaid
sequenceDiagram
    participant Caller as Service caller
    participant Proxy as Scoped proxy
    participant Cache as RefreshScope cache
    participant Target as Bean target
    Caller->>Proxy: Gọi method
    Proxy->>Cache: Lấy target
    Cache-->>Proxy: Target hiện tại
    Proxy->>Target: Thực thi method
    Target-->>Caller: Kết quả
    Note over Cache: Refresh xóa cache entry
    Caller->>Proxy: Gọi method lần sau
    Proxy->>Cache: Lấy target
    Cache->>Target: Khởi tạo target mới nếu cache rỗng
    Target-->>Proxy: Target mới
    Proxy->>Target: Thực thi method
~~~

Điều này khác với việc sửa field của một singleton thông thường. Caller thường giữ proxy trong suốt vòng đời context; target bên trong proxy có thể được tạo lại.

### 2.1. Refresh Scope không tự phát hiện mọi thay đổi

Một quy trình refresh thường cần các bước:

1. Nguồn cấu hình thay đổi.
2. Cấu hình mới được nạp vào Environment.
3. Spring Cloud chạy quy trình refresh.
4. Target cache của các bean thuộc refresh scope bị xóa.
5. Lần gọi tiếp theo tạo target mới bằng cấu hình hiện hành.

Nếu chỉ sửa file trên đĩa mà không có cơ chế reload, Environment chưa chắc đã thay đổi. Nếu Environment đã đổi nhưng không có refresh event/quy trình refresh, target đã cache vẫn có thể được dùng.

### 2.2. Refresh Scope không đồng nghĩa restart toàn bộ JVM

Refresh scope chỉ quản lý target của bean thuộc scope. Nó không tự khởi động lại process, không tự cập nhật mọi singleton và không bảo đảm mọi resource bên ngoài được thay thế an toàn.

Một số bean phụ thuộc vào target refresh có thể tiếp tục giữ state cũ nếu chính chúng đã snapshot dữ liệu trong constructor. Hãy kiểm tra toàn bộ đường phụ thuộc và cách caller giữ reference.

## 3. Phân biệt ba cơ chế

| Cơ chế | Cách khai báo | Tác động |
| --- | --- | --- |
| `@RefreshScope` | Đặt annotation trên bean hoặc bean method. | Bean được đăng ký với refresh scope và truy cập qua proxy. |
| `spring.cloud.refresh.extra-refreshable` | Liệt kê bean name hoặc class name. | Spring Cloud bổ sung các bean phù hợp vào refresh scope khi xử lý bean definitions. |
| `spring.cloud.refresh.never-refreshable` | Liệt kê bean name hoặc class name. | Spring Cloud loại các bean được chỉ định khỏi refresh/rebind theo cơ chế tương ứng. |

Không nên coi hai thuộc tính là hai danh sách đối xứng:

- `extra-refreshable` mở rộng nhóm bean được post-process thành refresh scope.
- `never-refreshable` là danh sách loại trừ, bao gồm ngoại lệ mặc định cho HikariDataSource.
- Bean đã có `@RefreshScope` không cần được thêm lại chỉ để nhắc lại cùng mục đích.
- Không cấu hình cùng một bean trong cả hai danh sách; điều đó làm ý định vận hành mâu thuẫn và khó kiểm chứng.

### 3.1. Khi nào dùng annotation trực tiếp?

Nếu bạn sở hữu mã nguồn và định nghĩa bean, cách rõ ràng nhất thường là đánh dấu bean trực tiếp:

~~~java
@Configuration
class RemoteClientConfiguration {

    @Bean
    @RefreshScope
    RemoteCatalogClient remoteCatalogClient(
            @Value("${catalog.base-url}") URI baseUrl) {
        return new RemoteCatalogClient(baseUrl);
    }
}
~~~

Bean được khai báo rõ ngay tại nơi tạo. Người đọc mã có thể nhận biết vòng đời refresh mà không phải tìm thêm một thuộc tính toàn cục.

### 3.2. Khi nào dùng extra-refreshable?

Dùng khi bạn không kiểm soát định nghĩa bean, chẳng hạn:

- Bean do auto-configuration của thư viện bên thứ ba tạo.
- Bean được tạo từ một module mà ứng dụng không muốn sửa.
- Bean cần được chuyển sang refresh scope theo chính sách triển khai.
- Không thể thêm annotation vào class hoặc method tạo bean.

Ví dụ, thư viện cung cấp `LegacyCatalogClient` và bean có tên `legacyCatalogClient`. Ứng dụng có thể thêm class hoặc bean name vào `extra-refreshable`.

Không thêm mọi class trong package vào danh sách. Chỉ chọn bean có thể được tạo lại an toàn và có đường proxy tương thích.

### 3.3. Khi nào dùng never-refreshable?

Dùng khi một bean không nên bị thay thế hoặc rebind tự động trong refresh workflow. Ví dụ:

- Bean giữ tài nguyên có lifecycle phức tạp.
- Thành phần thư viện không an toàn khi tạo lại trong khi request đang chạy.
- Bean cần được thay bằng quy trình rollout hoặc rotate riêng.
- HikariDataSource, vốn đã được Spring Cloud loại khỏi refresh mặc định.

Danh sách này là một ràng buộc vận hành. Khi thêm bean vào, bạn phải có kế hoạch khác để cập nhật cấu hình của bean đó, ví dụ restart/rolling deployment hoặc một quy trình quản lý tài nguyên riêng.

## 4. spring.cloud.refresh.extra-refreshable

### 4.1. Ý nghĩa và cách match

`spring.cloud.refresh.extra-refreshable` nhận thêm **bean name hoặc class name** của bean cần được post-process vào refresh scope.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: com.example.catalog.LegacyCatalogClient,legacyCatalogClient
~~~

Trong đó:

- `com.example.catalog.LegacyCatalogClient` là fully qualified class name.
- `legacyCatalogClient` là bean name.
- Danh sách được phân tách bằng dấu phẩy trong giá trị cấu hình.

Nếu class được chỉ định, Spring Cloud cần xác định được type của bean definition. Nếu bean được tạo bằng factory method, kiểu trả về và metadata của bean definition ảnh hưởng đến type được phát hiện. Khi match không như dự kiến, hãy kiểm tra bean name và type thực tế trong ApplicationContext.

### 4.2. Bean được thêm vào refresh scope khi nào?

Spring Cloud có một bean-definition post-processor để xử lý danh sách extra refreshable. Trong giai đoạn đăng ký bean definitions, các bean phù hợp được chuyển sang refresh scope và được tạo scoped proxy.

Điều đó có nghĩa:

- Thuộc tính cần có sẵn khi ApplicationContext đang xây dựng bean definitions.
- Đây không phải thao tác thêm annotation sau khi bean đã khởi tạo.
- Thay đổi thuộc tính này khi ứng dụng đang chạy không tự động biến một bean hiện có thành refresh-scoped.
- Muốn thay đổi chính sách scope, thường cần khởi động lại ứng dụng với cấu hình mới.

### 4.3. Ví dụ với bean bên thứ ba

Giả sử thư viện tạo bean:

~~~java
@Configuration
class VendorClientConfiguration {

    @Bean
    LegacyCatalogClient legacyCatalogClient(
            CatalogProperties properties) {
        return new LegacyCatalogClient(properties.baseUrl());
    }
}
~~~

Nếu không thể sửa class hoặc method của thư viện để thêm `@RefreshScope`, cấu hình có thể là:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: legacyCatalogClient
~~~

Sau khi ứng dụng khởi động với cấu hình này, caller nhận bean thông qua proxy refresh scope. Khi quy trình refresh xóa target cache, lần gọi sau sẽ tạo lại target.

### 4.4. Dùng class name hay bean name?

| Tiêu chí | Bean name | Class name |
| --- | --- | --- |
| Phạm vi | Chỉ định một bean cụ thể. | Có thể áp dụng cho các bean có type tương ứng. |
| Độ ổn định | Phụ thuộc quy ước đặt tên bean. | Phụ thuộc class được sử dụng và type được Spring nhận diện. |
| Hữu ích khi | Chỉ một bean trong ứng dụng cần refresh. | Muốn áp dụng cho bean theo implementation class. |
| Cần kiểm tra | Bean name thực tế trong context. | Fully qualified class name và type của bean definition. |

Ưu tiên bean name khi chỉ muốn thay đổi một bean cụ thể. Dùng class name khi chính sách áp dụng theo implementation và bạn đã xác minh cách Spring nhận diện type.

### 4.5. Những điều extra-refreshable không làm

Thuộc tính này không:

- Tự nạp lại file cấu hình hoặc gọi Config Server.
- Tự phát refresh event.
- Tự thay đổi mọi singleton phụ thuộc vào bean.
- Bảo đảm bean có thể proxy được trong mọi kiểu khai báo.
- Bảo đảm việc tạo target mới không lỗi.
- Bảo đảm tài nguyên target cũ được xử lý đúng nếu class không có lifecycle phù hợp.

Nếu bean là final, có API phụ thuộc concrete class hoặc không tương thích với proxy strategy, hãy thử trong integration test trước khi triển khai.

## 5. spring.cloud.refresh.never-refreshable

### 5.1. Ý nghĩa

`spring.cloud.refresh.never-refreshable` là danh sách bean name hoặc class name không được refresh/rebind theo cơ chế Spring Cloud.

Ví dụ:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Trong ví dụ:

- HikariDataSource được giữ trong danh sách không refresh.
- `ImmutableKeyStore` cũng được loại khỏi refresh/rebind.
- Các bean khác tiếp tục theo chính sách mặc định hoặc annotation/scope riêng.

Danh sách này cần được thiết kế theo yêu cầu vận hành. Nếu một bean bị loại khỏi refresh, đừng kỳ vọng thay đổi Environment sẽ tự cập nhật bean đó.

### 5.2. Giá trị mặc định có HikariDataSource

Theo tài liệu Spring Cloud Commons hiện hành, `com.zaxxer.hikari.HikariDataSource` là giá trị mặc định của `spring.cloud.refresh.never-refreshable`.

Đây là ngoại lệ quan trọng với ứng dụng dùng JDBC connection pool mặc định của Spring Boot. Spring Cloud không refresh HikariDataSource theo cơ chế thông thường. Nếu cần DataSource có thể refresh, tài liệu khuyến nghị chọn một DataSource implementation khác.

### 5.3. Ghi đè danh sách phải giữ lại Hikari

Khi khai báo `spring.cloud.refresh.never-refreshable` trong application configuration, giá trị cấu hình của bạn thay cho giá trị mặc định được dùng khi property không tồn tại. Vì vậy, nếu bạn thêm một class khác vào danh sách, hãy giữ lại HikariDataSource nếu ứng dụng vẫn dùng nó.

Ví dụ đúng khi muốn loại thêm một bean nhưng vẫn giữ ngoại lệ Hikari:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Ví dụ dễ gây lỗi:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.example.security.ImmutableKeyStore
~~~

Trong ví dụ thứ hai, cấu hình không còn liệt kê `com.zaxxer.hikari.HikariDataSource`. Nếu ứng dụng dùng Hikari, hãy chủ động giữ class này trong danh sách loại trừ như hướng dẫn Spring Cloud.

Đừng xem danh sách là một tập được tự động cộng thêm vào mặc định. Hãy cấu hình toàn bộ ngoại lệ cần thiết một cách tường minh.

### 5.4. Never-refreshable không phải cách cập nhật bean

Thêm bean vào `never-refreshable` chỉ ngăn cơ chế refresh/rebind áp dụng cho bean đó. Nó không tự:

- Tạo instance mới.
- Nạp lại cấu hình.
- Đóng tài nguyên cũ.
- Mở kết nối mới.
- Chuyển request sang bean khác.

Nếu bean cần đổi cấu hình, bạn phải thiết kế một quy trình khác có kiểm soát, ví dụ restart hoặc rollout instance.

## 6. Trường hợp HikariDataSource

### 6.1. HikariCP giữ gì?

`HikariDataSource` là implementation của `DataSource` sử dụng HikariCP connection pool. Nó quản lý các kết nối JDBC để nhiều request có thể mượn và trả connection thay vì tạo kết nối mới cho từng thao tác.

Một pool đang hoạt động có thể chứa:

- Kết nối đang được request sử dụng.
- Kết nối nhàn rỗi sẵn sàng cho lần mượn tiếp theo.
- Các thread quản lý pool và trạng thái kết nối.
- Thông số giới hạn, timeout và vòng đời pool.

Thay URL database hoặc credential là thay đổi liên quan đến tài nguyên đang hoạt động. Không thể xem nó như thay một chuỗi cấu hình đơn giản.

### 6.2. Vì sao Hikari không refresh mặc định?

Spring Cloud Commons ghi rõ HikariDataSource nằm trong danh sách `never-refreshable` mặc định và không thể được refresh theo cơ chế này. Khi cần refresh DataSource, tài liệu khuyến nghị chọn implementation khác.

Điều quan trọng là tuân thủ giới hạn được framework công bố. Không cố đưa Hikari vào `extra-refreshable` hoặc xóa ngoại lệ khỏi `never-refreshable` chỉ để làm endpoint refresh chạy qua.

Tài liệu chính thức nêu hành vi và khuyến nghị này; quyết định cụ thể về DataSource phải được đánh giá cùng driver, transaction manager, pool lifecycle và yêu cầu downtime của hệ thống.

### 6.3. Cấu hình Hikari thường gặp

Ví dụ cấu hình ban đầu:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: order_service
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Các giá trị này được đọc trong quá trình tạo DataSource/pool. Việc thay đổi Environment sau đó không có nghĩa Hikari pool tự đóng và tạo lại theo URL hoặc credential mới.

Nếu ứng dụng dùng Hikari, nên lập kế hoạch thay đổi các thông số kết nối theo một trong các cách:

- Restart/rolling restart các instance với cấu hình mới.
- Triển khai phiên bản mới của cấu hình cùng health/readiness checks.
- Dùng một cơ chế pool rotation do ứng dụng quản lý nếu thực sự cần đổi pool runtime; cơ chế đó phải xử lý request đang mượn connection, transaction đang chạy và đóng pool cũ đúng lúc.

Cách thứ ba là thiết kế lifecycle riêng của ứng dụng, không phải tính năng tự động mà `extra-refreshable` cung cấp.

### 6.4. Khi nào chọn DataSource implementation khác?

Nếu yêu cầu hệ thống là thay đổi database URL hoặc cấu hình DataSource trong runtime thông qua Spring Cloud refresh, hãy đánh giá một DataSource implementation khác được Spring Cloud hỗ trợ trong refresh scope.

Việc chọn implementation khác vẫn cần kiểm tra:

- Có thể được tạo lại an toàn qua proxy không?
- Bean và các dependency có giữ reference tới instance cũ không?
- Connection đang mượn được xử lý thế nào?
- Transaction đang chạy có thể hoàn tất không?
- Pool cũ được đóng khi nào?
- Target mới có được health-check trước khi nhận request không?
- Nếu target mới khởi tạo thất bại, ứng dụng còn sử dụng được trạng thái cũ hay chuyển sang DOWN?

Không đổi implementation chỉ để vượt qua danh sách never-refreshable. Hãy kiểm tra semantics và lifecycle thực tế của pool.

## 7. Cấu hình hai thuộc tính trong ứng dụng

### 7.1. Ví dụ kết hợp

Một ứng dụng có bean client cũ cần refresh và vẫn dùng HikariDataSource:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: com.example.catalog.LegacyCatalogClient
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Ý nghĩa:

- `LegacyCatalogClient` được bổ sung vào refresh scope.
- HikariDataSource tiếp tục nằm trong danh sách không refresh/rebind.
- ImmutableKeyStore cũng được loại khỏi refresh/rebind.
- Các bean không nằm trong hai danh sách vẫn tuân theo annotation và cơ chế mặc định.

Nếu `LegacyCatalogClient` đã được đánh dấu `@RefreshScope` trực tiếp, không cần thêm lại class đó vào extra-refreshable.

### 7.2. Environment variables

Spring Boot hỗ trợ truyền các thuộc tính này qua environment variables. Ví dụ:

~~~bash
SPRING_CLOUD_REFRESH_EXTRA_REFRESHABLE=com.example.catalog.LegacyCatalogClient
SPRING_CLOUD_REFRESH_NEVER_REFRESHABLE=com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Khi chạy container hoặc service manager, hãy đặt biến môi trường trong cấu hình deployment và kiểm tra process nhận đúng giá trị. Đây là thuộc tính cấu hình lúc khởi động; thay biến môi trường ở terminal sau khi process đã chạy không tự thay đổi bean definitions đã được xử lý.

### 7.3. Đừng đặt hai danh sách theo cùng một mục đích

Một bean không nên đồng thời được chỉ định là cần refresh và không được refresh. Nếu cần bean đó giữ nguyên, chỉ đặt trong `never-refreshable`. Nếu cần target được tạo lại, dùng `@RefreshScope` hoặc `extra-refreshable`.

Nếu có chính sách ngoại lệ theo bean name và class name, hãy ghi rõ trong tài liệu triển khai để người nâng cấp không vô tình thêm cùng một bean vào hai nhóm.

## 8. Cách refresh và xác minh bean

### 8.1. Expose endpoint refresh trong môi trường lab

Nếu ứng dụng đã có Actuator và Spring Cloud Context, endpoint refresh có thể được expose:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Gửi request:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

Endpoint phải được cấu hình, expose và bảo vệ phù hợp. Không public endpoint refresh ra Internet hoặc cho phép mọi người dùng gọi tùy ý. Trong production cần authentication, authorization, network restriction và audit.

### 8.2. Refresh toàn bộ hoặc từng bean

Spring Cloud cung cấp `RefreshScope` với các thao tác:

- `refreshAll()`: xóa cache target của các bean thuộc refresh scope.
- `refresh(String name)`: xóa cache target của bean theo tên.

Khi dùng endpoint `/actuator/refresh`, Spring Cloud thực hiện quy trình refresh tương ứng. Các target bị invalidate sẽ được tạo lại ở lần gọi tiếp theo qua proxy.

Không nhầm việc gọi refresh scope với việc cập nhật PropertySource. Nguồn cấu hình phải thực sự được cập nhật trước khi target mới được tạo.

### 8.3. Health indicator

Spring Cloud có `RefreshScopeHealthIndicator` để theo dõi trạng thái refresh scope. Nếu bean không thể re-initialize hoặc rebind sau refresh, health indicator có thể chuyển trạng thái sang `DOWN` và cung cấp thông tin exception liên quan.

Hãy đưa trạng thái này vào health/monitoring theo cách phù hợp với chính sách readiness của ứng dụng. Không che lỗi khởi tạo target mới bằng cách chỉ ghi log rồi tiếp tục coi instance khỏe.

## 9. Kiểm thử extra-refreshable

### 9.1. Mục tiêu

Kiểm tra bean không có annotation `@RefreshScope` nhưng được đưa vào refresh scope qua bean name hoặc class name.

Một bean lab:

~~~java
public class LegacyCatalogClient {
    private final int generation;

    public LegacyCatalogClient(int generation) {
        this.generation = generation;
    }

    public int generation() {
        return generation;
    }
}
~~~

Khai báo bean:

~~~java
@Configuration
class LegacyCatalogConfiguration {

    @Bean
    LegacyCatalogClient legacyCatalogClient(GenerationCounter counter) {
        return new LegacyCatalogClient(counter.next());
    }
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: legacyCatalogClient
~~~

`GenerationCounter` là bean lab tự tăng số mỗi lần factory được gọi. Sau khi ứng dụng khởi động, gọi `generation()` để ghi nhận target ban đầu. Sau khi refresh scope được làm mới, gọi lại qua proxy và xác minh target mới có generation khác.

### 9.2. Kịch bản test

1. Khởi động ApplicationContext với extra-refreshable đã cấu hình.
2. Inject `LegacyCatalogClient` vào một caller singleton.
3. Gọi method và ghi generation ban đầu.
4. Gọi `RefreshScope.refreshAll()` hoặc refresh bean theo tên.
5. Gọi lại method qua cùng reference caller đang giữ.
6. Xác minh target được tạo lại.
7. Kiểm tra log khởi tạo target và exception nếu factory thất bại.

Kết quả mong đợi: caller giữ proxy; target bên trong được tạo lại sau khi cache bị invalidate. Nếu caller giữ trực tiếp target thay vì proxy, phép thử có thể không phản ánh refresh scope.

### 9.3. Kiểm tra class name và bean name

Chạy hai trường hợp độc lập:

| Cách cấu hình | Giá trị | Điều cần xác minh |
| --- | --- | --- |
| Bean name | `legacyCatalogClient` | Đúng một bean được đưa vào refresh scope. |
| Class name | `com.example.catalog.LegacyCatalogClient` | Bean có type phù hợp được nhận diện và proxy hóa. |

Nếu class name không match, kiểm tra kiểu bean thực tế mà Spring nhận diện. Với factory method, khai báo return type cụ thể khi có thể và kiểm tra bean definition metadata.

## 10. Kiểm thử never-refreshable và Hikari

### 10.1. Kiểm tra danh sách mặc định

Trong ứng dụng dùng Spring Cloud Context, xác minh `spring.cloud.refresh.never-refreshable` có giá trị mặc định chứa:

~~~text
com.zaxxer.hikari.HikariDataSource
~~~

Có thể kiểm tra cấu hình đã được resolve qua Environment trong integration test. Không cần tạo kết nối database thật chỉ để kiểm tra tên class trong danh sách.

### 10.2. Kiểm tra khi override danh sách

Giả sử ứng dụng muốn thêm `com.example.security.ImmutableKeyStore` vào danh sách. Cấu hình phải giữ cả Hikari:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Test cần xác minh:
- HikariDataSource vẫn có mặt trong danh sách loại trừ.
- ImmutableKeyStore có mặt trong danh sách loại trừ.
- Các bean khác không bị loại ngoài ý muốn.
- Không có bean nào bị đồng thời cấu hình trong extra-refreshable và never-refreshable.

### 10.3. Kiểm tra hành vi của DataSource

Với ứng dụng thực sự dùng Hikari:

1. Xác nhận implementation runtime của bean DataSource.
2. Ghi nhận URL/metadata không nhạy cảm và trạng thái pool.
3. Thay đổi cấu hình nguồn trong môi trường test.
4. Chạy refresh workflow.
5. Xác minh HikariDataSource không được thay thế qua cơ chế refresh thông thường.
6. Kiểm tra ứng dụng tiếp tục dùng pool hiện hành hoặc thực hiện rollout theo quy trình đã thiết kế.
7. Không dùng password, JDBC URL chứa credential hoặc dữ liệu kết nối nhạy cảm trong log.

Không kết luận rằng database URL mới đã được áp dụng chỉ vì Environment trả về URL mới. Phải kiểm tra DataSource thực tế và kết nối mới.

## 11. Ma trận quyết định

| Loại bean | Chính sách phù hợp | Lý do |
| --- | --- | --- |
| Bean client tự viết, cần tạo lại khi config đổi | `@RefreshScope` | Ý định được khai báo ngay trên bean. |
| Bean thư viện không thể sửa annotation | `extra-refreshable` | Có thể chọn bằng bean name hoặc class name. |
| Bean giữ tài nguyên không thể tạo lại an toàn | `never-refreshable` | Loại khỏi refresh/rebind tự động. |
| HikariDataSource | Giữ trong `never-refreshable` mặc định | Spring Cloud không hỗ trợ refresh Hikari theo cơ chế này. |
| DataSource implementation khác có lifecycle phù hợp | Đánh giá `@RefreshScope` hoặc `extra-refreshable` | Phải xác minh connection lifecycle và proxy. |
| Constructor-bound configuration properties | Không dùng extra-refreshable để giả định rebinding constructor | Cần thiết kế snapshot/refresh scope riêng hoặc restart. |
| Bean có dependency giữ reference cũ | Đánh giá toàn bộ dependency graph | Refresh target không tự thay state snapshot ở caller. |

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bean không được refresh dù đã khai báo extra-refreshable. | Sai bean name/class name hoặc bean definition không được nhận diện như dự kiến. | Kiểm tra bean name, runtime type và property đã được nạp lúc startup. |
| Bean được refresh nhưng caller vẫn thấy giá trị cũ. | Caller giữ target/reference cũ hoặc không gọi qua proxy. | Inject và sử dụng scoped proxy; không lưu target trực tiếp. |
| Bean mới khởi tạo lỗi sau refresh. | Cấu hình mới không hợp lệ hoặc dependency chưa sẵn sàng. | Kiểm tra exception, health indicator và validation trước khi refresh. |
| HikariDataSource không thay đổi sau refresh. | Đây là hành vi mặc định theo never-refreshable. | Dùng rollout/restart hoặc đánh giá DataSource implementation khác. |
| Thêm bean khác vào never-refreshable làm Hikari mất khỏi danh sách. | Cấu hình mới đã thay giá trị mặc định nhưng không giữ lại Hikari. | Thêm lại `com.zaxxer.hikari.HikariDataSource` trong danh sách. |
| Hikari bị cấu hình trong extra-refreshable. | Nhầm extra-refreshable là cách override never-refreshable. | Bỏ Hikari khỏi extra-refreshable; giữ nó trong never-refreshable. |
| Bean bị loại khỏi refresh dù cần cập nhật. | Bean name/class name vô tình nằm trong never-refreshable. | Kiểm tra danh sách và chọn một chính sách duy nhất cho bean. |
| Thay đổi extra-refreshable lúc runtime không có tác dụng. | Bean definitions đã được xử lý trong startup. | Khởi động lại với cấu hình mới. |
| Refresh endpoint trả 404. | Chưa có Actuator/Cloud Context hoặc endpoint chưa expose. | Kiểm tra dependency và management endpoint configuration. |
| Refresh endpoint trả 401/403. | Security chặn thao tác quản trị. | Cấp quyền cho principal quản trị và giữ endpoint trong mạng tin cậy. |
| Pool cũ còn hoạt động sau thay đổi cấu hình. | DataSource không thuộc refresh scope hoặc đang bị never-refreshable. | Kiểm tra implementation thực tế và quy trình rollout/pool rotation. |

## 13. Nguyên tắc vận hành an toàn

1. **Chỉ thêm bean thực sự cần refresh.** Không dùng extra-refreshable như một danh sách mặc định cho toàn bộ bean trong ứng dụng.
2. **Giữ Hikari trong never-refreshable.** Nếu override property này, thêm lại fully qualified class name của Hikari.
3. **Không ép Hikari vào refresh scope.** Chọn DataSource implementation khác hoặc thiết kế pool rotation riêng nếu có yêu cầu runtime.
4. **Đánh giá dependency graph.** Bean phụ thuộc có thể giữ snapshot hoặc tài nguyên cũ dù target bên dưới đã refresh.
5. **Validate trước khi refresh.** Cấu hình mới cần được kiểm tra trước khi đưa vào Environment và tạo target mới.
6. **Quan sát quá trình khởi tạo lại.** Ghi bean name, revision và kết quả khởi tạo; không ghi secret.
7. **Có phương án rollback.** Nếu target mới không khởi tạo được, biết cách khôi phục revision trước hoặc rollout lại.
8. **Bảo vệ endpoint quản trị.** Refresh là thao tác thay đổi runtime state, cần xác thực, phân quyền, audit và giới hạn network.
9. **Kiểm tra nhiều instance.** Refresh một instance không tự cập nhật toàn bộ cluster; dùng broadcast hoặc rollout có kiểm soát.
10. **Đối chiếu phiên bản.** Hành vi auto-configuration và danh sách mặc định phải được kiểm tra theo Spring Cloud release train thực tế.

## 14. Checklist hoàn thành

- [ ] Giải thích được scoped proxy và target cache của RefreshScope.
- [ ] Phân biệt được `@RefreshScope` và `spring.cloud.refresh.extra-refreshable`.
- [ ] Biết extra-refreshable nhận bean name hoặc class name.
- [ ] Biết extra-refreshable được xử lý trong giai đoạn đăng ký bean definitions.
- [ ] Phân biệt được extra-refreshable với never-refreshable.
- [ ] Biết `spring.cloud.refresh.never-refreshable` là danh sách bean không được refresh/rebind.
- [ ] Nhớ `com.zaxxer.hikari.HikariDataSource` là ngoại lệ mặc định trong never-refreshable.
- [ ] Khi ghi đè never-refreshable, giữ lại Hikari nếu ứng dụng sử dụng nó.
- [ ] Không đưa Hikari vào extra-refreshable để cố làm mới pool.
- [ ] Chọn được restart/rollout hoặc DataSource implementation khác khi cần thay cấu hình database.
- [ ] Có test chứng minh extra-refreshable tạo target mới sau refresh.
- [ ] Có test kiểm tra never-refreshable và Hikari exclusion.
- [ ] Kiểm tra health indicator và log khi target không thể khởi tạo.
- [ ] Bảo vệ endpoint refresh và có audit/rollback.
- [ ] Xác minh trạng thái từng instance sau khi refresh trong môi trường phân tán.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): RefreshScope, extra-refreshable, never-refreshable, HikariDataSource và refresh health indicator.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): mô tả các thuộc tính `spring.cloud.refresh.extra-refreshable` và `spring.cloud.refresh.never-refreshable`.
- [Spring Cloud Commons – RefreshAutoConfiguration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshAutoConfiguration.java): cách Spring Cloud xử lý bean definitions và cấu hình refresh.

Hãy kiểm tra đúng Spring Boot/Spring Cloud release train trước khi áp dụng. Đặc biệt với DataSource, cần xác minh implementation runtime, bean type và lifecycle kết nối thay vì suy ra từ giá trị Environment.
