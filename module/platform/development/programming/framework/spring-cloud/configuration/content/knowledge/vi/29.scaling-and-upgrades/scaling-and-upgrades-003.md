# Tích hợp repository tùy chỉnh vào composite và thứ tự Ordered

Spring Cloud Config Server có thể ghép nhiều nguồn cấu hình thành một `Environment`. Ngoài Git, Vault, JDBC, Redis và các backend có sẵn, ứng dụng có thể bổ sung một nguồn riêng bằng cách triển khai `EnvironmentRepository`. Nguồn tùy chỉnh có thể đọc dữ liệu từ database nội bộ, API quản trị, hệ thống tenant hoặc một kho cấu hình của tổ chức.

Khi ghép nhiều repository, thứ tự quyết định nguồn nào thắng nếu cùng khai báo một khóa. Repository đứng trước đóng góp `PropertySource` có độ ưu tiên cao hơn. Vì vậy, một custom repository cần trả đúng cấu trúc `Environment`, tham gia composite đúng cách và khai báo `Ordered` rõ ràng. Nếu bỏ qua thứ tự, custom repository được xem là nguồn có độ ưu tiên thấp nhất theo mặc định.

## 1. Composite Environment Repository giải quyết vấn đề gì?

Một Config Server đơn giản thường đọc cấu hình từ một backend, ví dụ Git. Khi hệ thống phát triển, dữ liệu có thể nằm ở nhiều nơi:

- Git lưu cấu hình ứng dụng được review và version control.
- Vault lưu secret hoặc dữ liệu cần chính sách truy cập riêng.
- Database lưu tham số theo tenant hoặc cấu hình do một hệ thống nội bộ quản trị.
- Custom repository đọc một API hoặc kho dữ liệu chuyên biệt.

Composite cho phép Config Server gọi các repository và ghép `PropertySource` của chúng vào một response duy nhất.

```text
                         Config Client
                              |
                              | GET /{application}/{profile}/{label}
                              v
                    Config Server endpoint
                              |
                              v
                CompositeEnvironmentRepository
                   /          |           \
                  /           |            \
                 v            v             v
             Git repo     Vault repo    Custom repo
                 \            |             /
                  \           |            /
                   +----------+-------------+
                              |
                              v
                    Combined Environment
                     PropertySource list
                              |
                              v
                       Config Client
```

Composite không biến các backend thành một database duy nhất. Mỗi repository vẫn tự chịu trách nhiệm đọc dữ liệu, xác thực, hiểu application/profile/label và trả kết quả theo hợp đồng `EnvironmentRepository`.

## 2. Hợp đồng của `EnvironmentRepository`

Interface `org.springframework.cloud.config.server.environment.EnvironmentRepository` định nghĩa nguồn cấu hình mà Config Server có thể truy vấn. Phương thức chính là:

```java
Environment findOne(String application, String profile, String label);
```

Ba tham số có ý nghĩa:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `application` | Tên ứng dụng Config Client yêu cầu | `order-service` |
| `profile` | Một hoặc nhiều profile, thường là chuỗi phân tách bằng dấu phẩy | `prod,cloud` |
| `label` | Phiên bản cấu hình do backend hỗ trợ | `main`, `release-2026.11` hoặc commit ID |

Repository phải trả về `org.springframework.cloud.config.environment.Environment`. Đối tượng này mô tả application, profiles, label và danh sách `PropertySource` mà client sẽ nhận.

Một repository tối thiểu cần:

1. Đọc đúng application được yêu cầu.
2. Phân tích và áp dụng tất cả profile trong tham số `profile`.
3. Xử lý label theo hợp đồng của backend; không bỏ qua label nếu label đại diện cho phiên bản dữ liệu.
4. Tạo một hoặc nhiều `PropertySource` với tên ổn định và nội dung có thể bind vào Spring.
5. Trả các property source theo thứ tự ưu tiên từ cao xuống thấp.
6. Có hành vi rõ ràng khi không tìm thấy cấu hình, backend timeout hoặc người gọi không có quyền.

`EnvironmentRepository` không chỉ là một adapter trả về `Map`. Nó là điểm tích hợp vào mô hình phân giải cấu hình của Spring Cloud Config.

## 3. Cấu trúc `Environment` và `PropertySource`

Ví dụ đơn giản: custom repository đọc cấu hình từ một kho nội bộ và trả ba thuộc tính.

```java
import java.util.Map;

import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
import org.springframework.util.StringUtils;

public class EnvironmentExample {

    public Environment create(String application, String profile, String label) {
        String[] profiles = StringUtils.hasText(profile)
                ? StringUtils.commaDelimitedListToStringArray(profile)
                : new String[0];
        Environment environment = new Environment(application, profiles);
        environment.setLabel(label);

        Map<String, Object> properties = Map.of(
                "orders.timeout", "4s",
                "orders.retry-limit", 3,
                "feature.new-checkout", false
        );

        environment.add(new PropertySource("internal-config", properties));
        return environment;
    }
}
```

Trong response Environment API, `PropertySource` sẽ có dạng tương tự:

```json
{
  "name": "internal-config",
  "source": {
    "orders.timeout": "4s",
    "orders.retry-limit": 3,
    "feature.new-checkout": false
  }
}
```

Tên property source nên thể hiện backend và phạm vi dữ liệu, ví dụ `tenant-config:order-service` hoặc `policy-store:prod`. Không đưa token, password, connection string có credential hoặc dữ liệu nhạy cảm vào tên source vì tên này có thể xuất hiện trong response và log.

Nếu backend có nhiều lớp cấu hình, hãy trả nhiều `PropertySource` thay vì gộp tùy tiện. Ví dụ `application` context là mặc định chung, `order-service` là cấu hình ứng dụng, và `order-service-prod` là override riêng cho production. Nguồn có ưu tiên cao hơn phải được thêm trước trong Environment.

## 4. Triển khai custom repository

Giả sử tổ chức có một bảng cấu hình riêng theo application, profile và label. Một service `TenantConfigStore` chịu trách nhiệm truy vấn kho dữ liệu; repository chỉ chuyển request Config Server thành kết quả Environment.

### Interface của kho dữ liệu

```java
import java.util.List;
import java.util.Map;

public interface TenantConfigStore {

    Map<String, Object> load(
            String application,
            List<String> profiles,
            String label);
}
```

Phần triển khai store có thể dùng JDBC, JPA, HTTP client hoặc SDK của hệ thống nội bộ. Hãy dùng query có tham số và kiểm soát quyền truy cập theo application/tenant.

### Repository có `Ordered`

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
import org.springframework.cloud.config.server.environment.EnvironmentRepository;
import org.springframework.core.Ordered;
import org.springframework.util.StringUtils;

public class TenantEnvironmentRepository
        implements EnvironmentRepository, Ordered {

    private final TenantConfigStore store;

    public TenantEnvironmentRepository(TenantConfigStore store) {
        this.store = store;
    }

    @Override
    public Environment findOne(String application, String profile, String label) {
        String[] profileArray = StringUtils.hasText(profile)
                ? StringUtils.commaDelimitedListToStringArray(profile)
                : new String[0];

        List<String> profiles = Arrays.asList(profileArray);
        Map<String, Object> properties = store.load(application, profiles, label);

        Environment environment = new Environment(application, profileArray);
        environment.setLabel(label);

        if (properties != null && !properties.isEmpty()) {
            environment.add(new PropertySource(
                    "tenant-config:" + application,
                    properties));
        }

        return environment;
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
```

`getOrder()` là phương thức của `org.springframework.core.Ordered`. Giá trị số càng nhỏ thì độ ưu tiên càng cao. Ví dụ `10` được dùng ở đây để minh họa; giá trị production phải được chọn sau khi xác định thứ tự của các repository còn lại.

Nếu custom repository không cần ưu tiên ghi đè, có thể trả `Ordered.LOWEST_PRECEDENCE` để đặt nó ở cuối. Nếu không triển khai `Ordered`, Spring Cloud Config cũng xem custom repository là nguồn có độ ưu tiên thấp nhất.

### Đăng ký bean trong Config Server

```java
import org.springframework.cloud.config.server.environment.EnvironmentRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("composite")
public class TenantRepositoryConfiguration {

    @Bean
    EnvironmentRepository tenantEnvironmentRepository(TenantConfigStore store) {
        return new TenantEnvironmentRepository(store);
    }
}
```

Khi Config Server chạy với profile `composite`, bean custom được đưa vào danh sách `EnvironmentRepository` để composite tổng hợp cùng các backend khác. Chỉ tạo bean khi profile phù hợp để tránh vô tình thay thế default Git repository trong một cấu hình chỉ định dùng một backend.

## 5. Bật composite và khai báo backend có sẵn

Ví dụ Config Server dùng Git làm nguồn cấu hình chính và thêm custom repository để bổ sung tham số từ hệ thống nội bộ.

```yaml
spring:
  application:
    name: config-server
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.com/platform/config-repo.git
            default-label: main
```

Trong profile `composite`, Spring Cloud Config tạo `CompositeEnvironmentRepository` từ các bean `EnvironmentRepository`. Các repository khai báo bằng danh sách `spring.cloud.config.server.composite` được tạo bởi cơ chế composite configuration; bean custom cũng được đưa vào danh sách đó.

Không cần tự tạo `CompositeEnvironmentRepository` bằng tay trong ứng dụng thông thường. Hãy để auto-configuration của Config Server quản lý composite, trừ khi bạn có một lý do đặc biệt để thay thế toàn bộ cơ chế này.

## 6. `Ordered` quyết định repository nào thắng

Spring Cloud Config ghép các repository theo thứ tự ưu tiên. Repository có order thấp hơn được đặt trước và có độ ưu tiên cao hơn khi hai nguồn khai báo cùng một key.

| `getOrder()` | Độ ưu tiên | Ý nghĩa |
|---:|---|---|
| `Ordered.HIGHEST_PRECEDENCE` | Cao nhất | Nguồn được xét trước |
| `-10` | Rất cao | Thường dùng cho policy/override có chủ đích |
| `0` | Cao | Ưu tiên hơn repository có order lớn hơn |
| `10` | Thấp hơn `0` | Ví dụ custom repository trong phần trước |
| `100` | Thấp | Nguồn bổ sung hoặc fallback |
| `Ordered.LOWEST_PRECEDENCE` | Thấp nhất | Nguồn dự phòng, không ghi đè nguồn khác nếu key đã tồn tại |

Giả sử có ba repository:

```text
Policy repository       order = 0
Tenant repository       order = 10
Git repository          order = 20
```

Nếu cả ba cùng trả `orders.timeout`, giá trị từ Policy repository có ưu tiên cao nhất; nếu policy không có khóa đó, Tenant repository được dùng; nếu cả hai không có, Git cung cấp giá trị.

```text
Composite Environment
  1. policy-source       <- order 0   (cao nhất)
  2. tenant-source       <- order 10
  3. git-source          <- order 20  (thấp nhất)
```

Đây là thứ tự giữa các repository. Bên trong từng repository, thứ tự các `PropertySource` do repository trả về vẫn quyết định độ ưu tiên giữa các file/context mà chính repository đó đọc.

### Phân biệt `Ordered` với thuộc tính `order` của backend

Spring Cloud Config có thuộc tính `order` cho một số backend tích hợp. Ví dụ khi kích hoạt profile `git,vault`, có thể cấu hình:

```yaml
spring:
  profiles:
    active: git,vault
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          order: 2
        vault:
          host: vault.internal
          port: 8200
          order: 1
```

Giá trị `order: 1` của Vault có ưu tiên cao hơn `order: 2` của Git. Với custom bean, cách trực tiếp và rõ ràng là implement `Ordered` và trả về `getOrder()`.

Trong composite profile, thứ tự các repository khai báo trong danh sách `composite` cũng quyết định precedence của những backend được liệt kê ở đó. Khi kết hợp danh sách backend với bean custom, hãy chọn order có chủ đích và xác minh thứ tự thực tế trong response. Tránh để các repository có cùng order vì kết quả khi trùng thứ tự không phải là một hợp đồng ưu tiên mà ứng dụng nên dựa vào.

### Lưu ý về tên phương thức

Một số đoạn mô tả composite trong tài liệu có thể ghi nhầm `getOrdered`. Interface `org.springframework.core.Ordered` thực tế khai báo `getOrder()`. Hãy dùng `getOrder()` như ví dụ trong trang Custom Environment Repositories và API Spring Framework.

## 7. Thứ tự repository khác thứ tự property source

Có hai lớp thứ tự cần kiểm soát:

1. **Repository order:** quyết định backend nào đóng góp property source trước trong composite.
2. **Property source order:** quyết định nguồn nào bên trong một Environment của repository được ưu tiên.

Ví dụ Git repository tự trả về:

```text
1. order-service-prod.yml
2. order-service.yml
3. application-prod.yml
4. application.yml
```

Nếu custom repository có mức ưu tiên cao hơn Git (tức giá trị `getOrder()` nhỏ hơn), toàn bộ property source từ custom repository sẽ được ghép trước các property source từ Git. Nếu custom repository trả về nhiều source, chính repository phải sắp chúng đúng quy tắc mà nó mong muốn.

Tài liệu Spring Cloud Config yêu cầu custom repository tuân theo quy tắc precedence giống Spring Boot. Các repository native, Git và SVN nhận thứ tự đó từ cơ chế nạp cấu hình của Spring Boot; backend tự viết phải tự thực hiện và kiểm thử.

Không nên gộp mọi key từ nhiều context vào một `Map` nếu điều đó làm mất thông tin nguồn, profile hoặc label. Giữ nhiều `PropertySource` giúp response có thể chỉ ra key đến từ lớp cấu hình nào.

## 8. Ví dụ xung đột giá trị và cách dự đoán kết quả

Giả sử ba nguồn cùng khai báo `payment.timeout`:

| Repository | Order | Giá trị |
|---|---:|---:|
| Custom policy | `0` | `1s` |
| Tenant store | `10` | `3s` |
| Git | `20` | `5s` |

Config Client nhận các property source theo thứ tự policy, tenant, Git. Giá trị hiệu lực là `1s`.

Nếu policy không trả khóa `payment.timeout`, tenant thắng với `3s`. Nếu tenant cũng không có khóa, Git cung cấp `5s`.

Điều quan trọng là precedence chỉ giải quyết xung đột của cùng một key. Các key khác nhau vẫn được hợp nhất. Một repository không cần chứa toàn bộ cấu hình; nó có thể chỉ bổ sung những key mà backend đó sở hữu.

## 9. Hỗ trợ application, profile và label đúng cách

Config Server truy vấn repository bằng ba selector:

- `application`: tên ứng dụng client.
- `profile`: một hoặc nhiều profile phân tách bằng dấu phẩy.
- `label`: phiên bản dữ liệu.

Custom repository cần xác định cách ánh xạ ba giá trị này vào mô hình dữ liệu riêng. Ví dụ:

| Selector Config Server | Cách ánh xạ trong kho nội bộ |
|---|---|
| `application=order-service` | `service_code = 'order-service'` |
| `profile=prod,cloud` | Tìm cấu hình áp dụng cho cả profile chung và profile chuyên biệt theo thứ tự đã quy định |
| `label=release-2026.11` | Lấy snapshot/revision `release-2026.11` |

Profile có thể chứa nhiều phần tử. Không nên coi cả chuỗi `prod,cloud` là một profile duy nhất nếu backend lưu profile riêng. Hãy chuẩn hóa danh sách, loại bỏ khoảng trắng thừa, xử lý thứ tự profile và định nghĩa quy tắc khi có key trùng.

Label là một phần của contract versioning. Nếu backend không hỗ trợ label, cần quyết định rõ: chỉ chấp nhận label mặc định, ánh xạ label sang snapshot, hoặc từ chối label không được hỗ trợ. Không âm thầm bỏ qua label vì client có thể yêu cầu một revision cũ nhưng lại nhận dữ liệu mới nhất.

Khi composite có nhiều repository, các backend phải tương thích với label mà client yêu cầu. Nếu Git có branch `main` nhưng một repository khác không có label đó và không có quy tắc ánh xạ, toàn bộ request composite có thể thất bại.

## 10. Không có dữ liệu và lỗi backend là hai trường hợp khác nhau

Custom repository nên phân biệt:

| Trường hợp | Hành vi nên chọn |
|---|---|
| Application không có key trong custom store nhưng nguồn khác có thể cung cấp | Trả Environment rỗng hoặc chỉ chứa property source có dữ liệu |
| Application/profile/label không hợp lệ theo contract | Từ chối rõ ràng bằng exception phù hợp |
| Database/API tạm thời không truy cập được | Báo lỗi backend; không giả vờ trả dữ liệu rỗng nếu nguồn là bắt buộc |
| Credential hết hạn hoặc không có quyền | Báo lỗi xác thực/phân quyền và ghi log an toàn |
| Dữ liệu có schema sai hoặc không thể parse | Báo lỗi dữ liệu; không trả một phần không hợp lệ mà không có chính sách |

Composite mặc định fail khi một repository gặp lỗi trong lúc lấy dữ liệu. Điều này giúp tránh response thiếu một nguồn mà client nghĩ là đầy đủ.

Có thể đặt:

```yaml
spring:
  cloud:
    config:
      server:
        fail-on-composite-error: false
```

Khi tắt `fail-on-composite-error`, composite có thể tiếp tục với repository còn hoạt động. Chỉ dùng nếu nguồn bị lỗi thực sự là tùy chọn và ứng dụng có thể chạy an toàn khi thiếu dữ liệu của nguồn đó. Nếu custom repository chứa feature flag bắt buộc, endpoint thanh toán hoặc policy bảo mật, trả Environment thiếu có thể nguy hiểm hơn việc từ chối request.

## 11. Khi nào custom repository cần `SearchPathLocator`?

Một custom repository cơ bản chỉ cần `EnvironmentRepository`. Một số backend tích hợp thêm `SearchPathLocator` để công bố search path hoặc vị trí tài nguyên mà backend sử dụng. Trong composite, Config Server có thể chọn `SearchPathCompositeEnvironmentRepository` nếu có repository hỗ trợ `SearchPathLocator`; nếu không, dùng `CompositeEnvironmentRepository` thông thường.

Chỉ implement `SearchPathLocator` khi custom backend thực sự có khái niệm search path cần expose. Không tạo search path giả để cố buộc composite chọn một implementation cụ thể. Dù chọn loại composite nào, contract chính vẫn là trả Environment và property source có thứ tự đúng.

## 12. Bảo đảm tính nhất quán và hiệu năng của custom repository

Custom repository thường gọi database hoặc API trong mỗi lần Config Client yêu cầu cấu hình. Cần thiết kế nó như một backend production:

- Dùng connection pool và timeout hữu hạn.
- Dùng query có tham số; không nối trực tiếp application/profile/label vào SQL.
- Xác thực quyền đọc theo application hoặc tenant ở phía server.
- Chỉ trả các key được phép phát hành cho Config Client tương ứng.
- Không log secret hoặc raw payload chứa thông tin nhạy cảm.
- Có cache nếu phù hợp, nhưng cache key phải gồm application, danh sách profile và label.
- Đặt TTL/invalidation rõ ràng để tránh phục vụ revision cũ sau khi cập nhật.
- Tránh cache dùng chung giữa tenant hoặc application khác nhau.
- Nếu backend trả nhiều key, đọc chúng trong một transaction/snapshot nhất quán.
- Đặt metric cho latency, lỗi, cache hit, revision và số property source.

Một lỗi nguy hiểm là cache theo application nhưng bỏ profile hoặc label. Khi đó request `order-service/prod/main` có thể nhận dữ liệu của `order-service/dev/feature-x`. Cache key cần phản ánh đủ selector và mọi yếu tố bảo mật có ảnh hưởng tới response.

## 13. Kiểm thử custom repository

Không chỉ kiểm thử rằng `findOne()` trả về một Map. Cần kiểm tra contract mà Config Client sẽ quan sát:

- Application, profile và label được chuyển đúng.
- Nhiều profile được phân tích đúng thứ tự.
- Property source có tên ổn định và thứ tự đúng.
- Key trùng giữa custom repo và Git/Vault được giải quyết đúng theo `Ordered`.
- Không có dữ liệu trả Environment rỗng theo chính sách.
- Backend timeout, lỗi quyền và dữ liệu sai được xử lý đúng.
- Label không tồn tại không âm thầm trả revision khác.
- Các request đồng thời cho hai application/tenant không rò dữ liệu chéo.

### Dùng `EnvironmentRepositoryComplianceTests`

Spring Cloud Config cung cấp bộ kiểm thử tuân thủ trong test JAR của `spring-cloud-config-server`. Bộ `EnvironmentRepositoryComplianceTests` có thể ghi các file cấu hình mẫu vào backend, truy vấn custom repository và kiểm tra thứ tự property source cũng như giá trị mà client sẽ phân giải.

Thêm test dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

Tạo test fixture:

```java
class TenantEnvironmentRepositoryComplianceTests
        extends EnvironmentRepositoryComplianceTests {

    private final InMemoryTenantConfigStore store =
            new InMemoryTenantConfigStore();

    @Override
    protected EnvironmentRepositoryFixture fixture() {
        return new EnvironmentRepositoryFixture() {

            @Override
            public void reset() {
                store.clear();
            }

            @Override
            public void store(ConfigFile file) {
                store.put(
                        file.application(),
                        file.profile(),
                        file.label(),
                        file.properties());
            }

            @Override
            public EnvironmentRepository repository() {
                return new TenantEnvironmentRepository(store);
            }

            @Override
            public Set<Capability> capabilities() {
                return EnumSet.of(
                        Capability.LABELS,
                        Capability.MULTIPLE_APPLICATIONS);
            }
        };
    }
}
```

Fixture minh họa trên cần bổ sung import và store test phù hợp với dự án. Khai báo đúng `Capability` mà backend thật sự hỗ trợ; các scenario cần capability không được khai báo sẽ được bỏ qua. Nếu repository chủ ý có hành vi khác một scenario, override test đó và ghi rõ lý do thay vì bỏ qua kiểm thử chung một cách im lặng.

## 14. Kiểm tra composite qua HTTP API

Sau khi bật composite profile và đăng ký custom bean, khởi động Config Server rồi gọi một request có application/profile/label cụ thể:

```bash
curl -sS \
  http://localhost:8888/order-service/prod/main
```

Response Environment cần cho thấy:

1. `name`, `profiles` và `label` phản ánh request.
2. `propertySources` có source từ Git và custom backend.
3. Source có order cao hơn xuất hiện trước.
4. Khi hai nguồn cùng khai báo một key, giá trị ở source đứng trước được client phân giải.

Ví dụ rút gọn:

```json
{
  "name": "order-service",
  "profiles": ["prod"],
  "label": "main",
  "propertySources": [
    {
      "name": "tenant-config:order-service",
      "source": {
        "orders.timeout": "3s"
      }
    },
    {
      "name": "https://git.example.com/platform/config-repo.git/order-service-prod.yml",
      "source": {
        "orders.timeout": "5s",
        "orders.retry-limit": 4
      }
    }
  ]
}
```

Ở ví dụ này, `orders.timeout` có giá trị hiệu lực `3s` vì custom source đứng trước Git. `orders.retry-limit` vẫn lấy từ Git vì custom source không khai báo khóa đó.

Không chỉ kiểm tra HTTP 200. Hãy kiểm tra cả thứ tự `propertySources`, giá trị cuối cùng và metadata label/version nếu backend cung cấp.

## 15. Troubleshooting khi custom repository không được ghép

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Custom repository không xuất hiện | Bean không được đăng ký hoặc profile chứa bean không active | Kiểm tra component scan, `@Bean` và `spring.profiles.active` |
| Chỉ trả custom source, không có Git | Default Git repository bị thay thế bởi custom bean hoặc composite profile chưa bật | Bật `composite` và khai báo backend Git trong danh sách composite |
| Custom source luôn đứng cuối | Repository không implement `Ordered` hoặc trả `LOWEST_PRECEDENCE` | Implement `Ordered.getOrder()` với giá trị ưu tiên phù hợp |
| Git luôn thắng custom dù đã đặt order | Order của bean và danh sách composite không như dự kiến; cấu hình bị override | Kiểm tra profile, bean thực tế và response `propertySources` |
| Giá trị không đúng dù repository order đúng | Property source nội bộ của repository bị sắp sai | Kiểm tra thứ tự `Environment.add(...)` và precedence trong backend |
| Request profile nhiều giá trị trả thiếu key | Chỉ xử lý profile đầu hoặc coi chuỗi comma là một profile | Parse danh sách profile và áp dụng quy tắc merge rõ ràng |
| Label `main` hoạt động nhưng `release` thất bại | Backend custom không có hoặc không ánh xạ label đó | Đồng bộ label, ánh xạ snapshot hoặc trả lỗi rõ ràng |
| Composite trả lỗi dù Git còn hoạt động | Custom backend ném exception hoặc label/backend khác thất bại | Kiểm tra log từng repository và quyết định fail-on-composite-error |
| Response có cấu hình của tenant khác | Cache key hoặc authorization không bao gồm tenant/application | Sửa cache key, kiểm tra quyền và test isolation |
| Response thiếu origin/source name | Custom source không đặt tên ổn định hoặc không lưu provenance | Đặt tên PropertySource có ý nghĩa và lưu metadata phù hợp |

## 16. Checklist trước khi đưa vào production

| Hạng mục | Điều kiện đạt |
|---|---|
| Contract | `findOne(application, profile, label)` trả `Environment` hợp lệ |
| Registration | Custom bean được đăng ký đúng profile và xuất hiện trong composite |
| Ordering | Implement `Ordered.getOrder()`; giá trị không trùng ngoài ý muốn |
| Property source | Tên rõ ràng, nội dung đúng và thứ tự nội bộ đã kiểm thử |
| Profile | Xử lý đúng một hoặc nhiều profile và quy tắc merge |
| Label | Hỗ trợ hoặc từ chối label theo contract; không bỏ qua âm thầm |
| Missing data | Có quy tắc rõ giữa Environment rỗng và lỗi backend |
| Composite failure | `fail-on-composite-error` được chọn theo mức độ bắt buộc của nguồn |
| Security | Query có tham số, authorization theo application/tenant và secret được bảo vệ |
| Performance | Timeout, pool, cache key và invalidation được cấu hình |
| Consistency | Đọc dữ liệu nhất quán và có revision/provenance khi cần |
| Tests | Unit, integration, precedence conflict và compliance tests đều đạt |
| Observability | Có log/metric cho latency, lỗi backend, cache và revision |
| API verification | Environment API trả đúng source order và giá trị hiệu lực |

## 17. Nguyên tắc cần ghi nhớ

- Custom backend tích hợp với Config Server bằng `EnvironmentRepository` và trả về một `Environment` chứa `PropertySource`.
- `findOne` nhận application, profile và label; phải xử lý đủ ba selector.
- Custom bean được đưa vào composite khi composite profile và cấu hình bean phù hợp được kích hoạt.
- Implement `org.springframework.core.Ordered` và dùng `getOrder()` để kiểm soát thứ tự; số càng nhỏ thì ưu tiên càng cao.
- Custom repository không implement `Ordered` được đặt ở độ ưu tiên thấp nhất.
- Repository order quyết định thứ tự backend; property source order quyết định thứ tự bên trong từng backend.
- Danh sách composite khai báo backend tích hợp theo thứ tự ưu tiên; backend có label không tương thích có thể làm request composite thất bại.
- Mặc định một repository lỗi có thể làm toàn bộ composite request thất bại; chỉ cho phép partial response khi nguồn đó thực sự tùy chọn.
- Custom repository phải xử lý nhiều profile, label, missing data, timeout và lỗi quyền một cách tường minh.
- Kiểm tra precedence bằng response `propertySources` và `EnvironmentRepositoryComplianceTests`, không chỉ kiểm tra endpoint trả HTTP 200.

Tích hợp một custom repository không dừng ở việc trả một Map từ database hoặc API. Repository phải tuân thủ contract Environment, được đăng ký đúng vào composite và có thứ tự rõ ràng để các nguồn cùng phân giải một key theo quy tắc dự đoán được. Khi kiểm thử cả repository order lẫn property source order, Config Server có thể mở rộng thêm backend riêng mà vẫn giữ kết quả cấu hình nhất quán cho mọi Config Client.

## Tài liệu tham khảo

- [Spring Cloud Config 5.1 — Custom Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/custom-enviroment-repository.html)
- [Spring Cloud Config 5.1 — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
- [Spring Cloud Config 5.1 — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Config API — EnvironmentRepository](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-config-server/latest/org/springframework/cloud/config/server/environment/EnvironmentRepository.html)
- [Spring Framework API — Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html)
