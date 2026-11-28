# Triển khai findOne và ánh xạ Environment cùng PropertySource

Spring Cloud Config Server nhận yêu cầu cấu hình theo ba thông tin chính: application, profile và label. Backend được truy vấn thông qua hợp đồng <code>EnvironmentRepository.findOne(application, profile, label)</code>. Kết quả không phải một YAML file đơn lẻ mà là một đối tượng <code>Environment</code> chứa metadata và danh sách <code>PropertySource</code> theo thứ tự ưu tiên.

Khi xây dựng repository tùy chỉnh hoặc tích hợp backend mới, phần quan trọng là ánh xạ đúng ba đầu vào của <code>findOne</code> sang dữ liệu cấu hình, sau đó tạo Environment nhất quán để Config Server trả cho client. Mỗi PropertySource cần có tên nhận diện rõ ràng, map thuộc tính đúng kiểu và vị trí phù hợp trong danh sách ưu tiên. Sai thứ tự có thể khiến client nhận response hợp lệ nhưng dùng nhầm giá trị.

Bài học này đi từ contract của <code>EnvironmentRepository</code>, cách phân giải application/profile/label, tạo <code>Environment</code>, chuyển dữ liệu thành <code>PropertySource</code>, kiểm soát precedence và origin, xử lý lỗi, kiểm thử endpoint, rồi tối ưu khi repository phải phục vụ nhiều client hoặc nâng cấp Spring Cloud.

Sau bài học, bạn có thể:

- Giải thích vai trò của <code>EnvironmentRepository.findOne</code>.
- Phân tích ý nghĩa application, profile và label trong request.
- Tạo <code>Environment</code> với name, profiles, label, version và state phù hợp.
- Ánh xạ nhiều tài liệu cấu hình thành nhiều <code>PropertySource</code>.
- Đặt thứ tự property source theo quy tắc precedence rõ ràng.
- Phân biệt <code>org.springframework.cloud.config.environment.PropertySource</code> với property source của Spring Environment.
- Bảo toàn kiểu dữ liệu, origin và revision khi chuyển dữ liệu.
- Xử lý trường hợp thiếu application, profile hoặc label.
- Viết unit test và integration test cho repository.
- Thiết kế repository thread-safe, có cache và khả năng nâng cấp.

## 1. Vị trí của findOne trong luồng Config Server

Config Server cung cấp HTTP endpoint cho client. Controller nhận application, profile và label từ URL, sau đó gọi repository để lấy Environment. Repository chịu trách nhiệm truy xuất và chuyển dữ liệu backend sang mô hình Environment của Spring Cloud Config.

~~~mermaid
sequenceDiagram
    participant Client as Config Client
    participant Controller as EnvironmentController
    participant Repo as EnvironmentRepository
    participant Store as Config Backend
    Client->>Controller: GET /orders-service/prod/release-1
    Controller->>Repo: findOne(application, profile, label)
    Repo->>Store: Resolve documents for request
    Store-->>Repo: Config documents + revision
    Repo-->>Controller: Environment + PropertySources
    Controller-->>Client: Environment JSON
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| EnvironmentController | Nhận HTTP request, giải mã path và gọi repository |
| EnvironmentRepository | Trả Environment cho một application/profile/label |
| Backend store | Đọc Git, database, Consul, Vault hoặc nguồn riêng |
| Environment | Mô tả cấu hình tổng thể được trả về |
| PropertySource | Chứa tên nguồn và map các property |
| Config Client | Đưa property sources từ response vào Spring Environment |

Khi chỉ cần thay backend, thông thường không cần tự viết controller mới. Cung cấp một bean <code>EnvironmentRepository</code> để Config Server gọi qua contract hiện có. Chỉ xây controller riêng khi cần API khác với giao thức Config Server.

## 2. Contract EnvironmentRepository.findOne

Interface nằm trong package:

~~~java
org.springframework.cloud.config.server.environment.EnvironmentRepository
~~~

Method cốt lõi có dạng:

~~~java
Environment findOne(String application, String profile, String label);
~~~

Ý nghĩa từng tham số:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| <code>application</code> | Tên ứng dụng đang yêu cầu cấu hình | <code>orders-service</code> |
| <code>profile</code> | Một hoặc nhiều profile được yêu cầu | <code>prod</code> hoặc <code>prod,cloud</code> |
| <code>label</code> | Nhãn/version backend cần đọc | Git branch, tag hoặc commit |
| Giá trị trả về | Environment gồm metadata và property sources | <code>Environment</code> |

<code>findOne</code> là ranh giới giữa giao thức Config Server và cách lưu trữ thực tế. Backend có thể là Git, database, Consul, Vault hoặc một hệ thống nội bộ; client vẫn nhận cùng mô hình Environment.

### Không nhầm Environment của Config Server với Spring Environment

Có hai loại thường dễ nhầm tên:

- <code>org.springframework.cloud.config.environment.Environment</code>: DTO của Spring Cloud Config, được serialize thành response API.
- <code>org.springframework.core.env.Environment</code>: abstraction trong Spring Framework dùng để tra cứu property trong process.

<code>findOne</code> phải trả về DTO của Spring Cloud Config. Không trả <code>ConfigurableEnvironment</code> hoặc <code>StandardEnvironment</code> của ứng dụng server.

Tương tự, class <code>org.springframework.cloud.config.environment.PropertySource</code> dùng trong response khác với <code>org.springframework.core.env.PropertySource</code> mà Spring Framework sử dụng nội bộ. Khi import trong code, dùng đúng package để tránh lỗi compile hoặc chuyển đổi sai.

## 3. Application, profile và label cần được chuẩn hóa

<code>findOne</code> nhận các giá trị đã được controller phân tích từ request. Repository cần hiểu và giữ đúng ngữ nghĩa của chúng.

Ví dụ:

~~~http
GET /orders-service/prod/release-1
~~~

- Application: <code>orders-service</code>.
- Profile: <code>prod</code>.
- Label: <code>release-1</code>.

Nếu profile có nhiều giá trị:

~~~http
GET /orders-service/prod,cloud/release-1
~~~

repository cần bảo toàn danh sách profile và thứ tự mà client yêu cầu. Không nên tùy tiện đổi <code>prod,cloud</code> thành <code>cloud,prod</code>, vì thứ tự profile có thể ảnh hưởng việc ghép property source.

### Label không nhất thiết là Git branch

Với Git backend, label thường đại diện branch, tag hoặc commit. Với database hoặc backend riêng, label có thể là release ID hoặc revision. Repository cần định nghĩa rõ cách phân giải label:

- Label cụ thể: đọc đúng revision được yêu cầu.
- Label không truyền hoặc rỗng: dùng default label theo chính sách backend.
- Label không tồn tại: trả lỗi có ý nghĩa, không âm thầm chuyển sang revision khác.
- Label có ký tự đặc biệt: xử lý đúng quy tắc path và encoding của endpoint.

Không tự đặt label mặc định là <code>main</code> trong custom repository nếu hệ thống có default branch khác. Nên để một thành phần duy nhất chịu trách nhiệm phân giải default label.

### Application name là một định danh, không phải đường dẫn tùy ý

Không ghép trực tiếp application/profile/label thành filesystem path mà không kiểm tra. Nếu backend là filesystem hoặc database:

- Kiểm tra application thuộc danh sách được phép.
- Chuẩn hóa profile và label theo quy tắc đã định.
- Dùng parameterized query khi truy vấn database.
- Ngăn path traversal và truy cập chéo tenant.
- Không đưa input thô vào tên file hoặc lệnh shell.

## 4. Mô hình Environment và PropertySource

Một Environment thường chứa các trường:

| Field | Vai trò |
|---|---|
| <code>name</code> | Application name được yêu cầu |
| <code>profiles</code> | Danh sách profile được áp dụng |
| <code>label</code> | Label đã phân giải |
| <code>version</code> | Revision/version nếu backend có thể cung cấp |
| <code>state</code> | Metadata trạng thái nếu backend sử dụng |
| <code>propertySources</code> | Danh sách nguồn thuộc tính theo thứ tự ưu tiên |

Một PropertySource chứa:

| Field | Vai trò |
|---|---|
| <code>name</code> | Tên nguồn để nhận diện trong response |
| <code>source</code> | Map property key sang value |

Ví dụ JSON rút gọn:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "release-1",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": "orders-service-prod.yml",
      "source": {
        "orders.timeout": "2s",
        "orders.retry.max-attempts": 3
      }
    },
    {
      "name": "application.yml",
      "source": {
        "orders.timeout": "5s",
        "orders.retry.max-attempts": 2
      }
    }
  ]
}
~~~

Trong ví dụ, <code>orders-service-prod.yml</code> là nguồn cụ thể hơn và được đặt trước nguồn dùng chung. Client nhận cả hai nguồn, sau đó áp dụng precedence của Spring Environment.

## 5. Ánh xạ backend document thành PropertySource

Một backend có thể lưu cấu hình dưới dạng nhiều document. Ví dụ database trả về:

| Document | Priority | Property |
|---|---:|---|
| <code>application.yml</code> | 10 | <code>orders.timeout=5s</code> |
| <code>application-prod.yml</code> | 20 | <code>orders.timeout=4s</code> |
| <code>orders-service.yml</code> | 30 | <code>orders.timeout=3s</code> |
| <code>orders-service-prod.yml</code> | 40 | <code>orders.timeout=2s</code> |

Mỗi document nên trở thành một PropertySource riêng. Không nên gộp toàn bộ document vào một map duy nhất nếu cần giữ lại nguồn gốc và khả năng truy vết precedence.

Ví dụ:

~~~java
Map<String, Object> values = new LinkedHashMap<>();
values.put("orders.timeout", "2s");
values.put("orders.retry.max-attempts", 3);

PropertySource propertySource =
    new PropertySource("orders-service-prod.yml", values);
~~~

Một PropertySource tốt có các đặc điểm:

- <code>name</code> ổn định, duy nhất trong Environment và dễ nhận diện.
- <code>source</code> chỉ chứa property của document đó.
- Key được chuẩn hóa nhất quán, thường là dotted property name.
- Value giữ kiểu dữ liệu phù hợp như String, Boolean, Number, List hoặc Map.
- Không đưa credential hoặc metadata nhạy cảm vào tên source.
- Map không bị dùng chung mutable giữa các request.

### Flatten key và nested data

Với YAML:

~~~yaml
orders:
  retry:
    max-attempts: 3
    enabled: true
~~~

Một map đã chuẩn hóa có thể là:

~~~java
Map<String, Object> source = new LinkedHashMap<>();
source.put("orders.retry.max-attempts", 3);
source.put("orders.retry.enabled", true);
~~~

Dạng key phẳng giúp property lookup nhất quán và tương thích với cách Spring Boot bind cấu hình. Nếu backend giữ nested map, hãy dùng parser/binder đã được kiểm thử để chuyển đổi; không tự viết thuật toán flatten đơn giản có thể làm hỏng list, map lồng nhau hoặc key chứa dấu chấm.

Không stringify mọi value. Ví dụ <code>3</code> nên được giữ là Number và <code>true</code> là Boolean nếu parser/backend cung cấp đúng kiểu. Việc chuyển mọi giá trị thành chuỗi có thể làm mất kiểu dữ liệu và khiến conversion phụ thuộc vào client.

## 6. Thứ tự PropertySource quyết định giá trị thắng

Trong Environment response, property source đứng trước có precedence cao hơn property source đứng sau. Khi nhiều nguồn có cùng key, client sẽ chọn giá trị từ nguồn có độ ưu tiên cao hơn.

Ví dụ mong muốn:

1. <code>orders-service-prod.yml</code> — cao nhất.
2. <code>orders-service.yml</code>.
3. <code>application-prod.yml</code>.
4. <code>application.yml</code> — thấp nhất.

Nếu model backend có priority tăng dần theo độ cụ thể, có thể sort giảm dần trước khi thêm vào Environment:

~~~java
List<ConfigDocument> ordered = documents.stream()
    .sorted(Comparator.comparingInt(ConfigDocument::priority).reversed())
    .toList();

for (ConfigDocument document : ordered) {
    environment.add(new PropertySource(
        document.name(),
        new LinkedHashMap<>(document.properties())
    ));
}
~~~

Đoạn code giả định số priority lớn hơn có nghĩa là độ ưu tiên cao hơn và <code>Environment.add</code> thêm nguồn vào cuối danh sách. Hãy xác minh thứ tự cuối cùng bằng unit test và response JSON của endpoint.

Nếu dùng API thêm nguồn vào đầu danh sách như <code>addFirst</code>, cần đảo cách duyệt tương ứng. Không kết hợp sort và addFirst mà không kiểm tra, vì rất dễ đảo ngược precedence.

### Không trộn precedence server với precedence toàn ứng dụng

<code>findOne</code> chỉ xây dựng property sources của Config Server. Client còn có các nguồn khác như command-line argument, system property, environment variable và local config file. Thứ tự tổng thể của các nguồn này được Spring Boot quyết định theo cấu hình và phiên bản.

Custom repository không nên cố gắng mô phỏng toàn bộ precedence của mọi nguồn phía client. Nó chỉ cần trả các remote property sources theo đúng thứ tự đã định nghĩa.

## 7. Triển khai một EnvironmentRepository tùy chỉnh

Ví dụ dưới đây minh họa repository đọc các document đã được chuẩn hóa từ một store. Store là abstraction của backend; có thể triển khai bằng JDBC, API nội bộ hoặc một dịch vụ cấu hình khác.

Model document:

~~~java
public record ConfigDocument(
    String name,
    int priority,
    Map<String, Object> properties,
    String revision
) {}
~~~

Contract của store:

~~~java
public interface ConfigDocumentStore {

    String resolveLabel(String requestedLabel);

    List<ConfigDocument> load(
        String application,
        List<String> profiles,
        String resolvedLabel
    );

    String revisionFor(
        String application,
        List<String> profiles,
        String resolvedLabel
    );
}
~~~

Repository:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
import org.springframework.cloud.config.server.environment.EnvironmentRepository;

@Component
public class DatabaseEnvironmentRepository implements EnvironmentRepository {

    private final ConfigDocumentStore store;

    public DatabaseEnvironmentRepository(ConfigDocumentStore store) {
        this.store = store;
    }

    @Override
    public Environment findOne(
            String application,
            String profile,
            String label) {

        validateApplication(application);

        List<String> profiles = parseProfiles(profile);
        String resolvedLabel = store.resolveLabel(label);

        List<ConfigDocument> documents =
            store.load(application, profiles, resolvedLabel);

        Environment environment = new Environment(
            application,
            profiles.toArray(String[]::new)
        );
        environment.setLabel(resolvedLabel);

        documents.stream()
            .filter(document -> document != null)
            .sorted(Comparator.comparingInt(
                ConfigDocument::priority
            ).reversed())
            .forEach(document -> {
                Map<String, Object> values =
                    new LinkedHashMap<>(document.properties());

                environment.add(new PropertySource(
                    document.name(),
                    values
                ));
            });

        String revision = store.revisionFor(
            application,
            profiles,
            resolvedLabel
        );
        if (revision != null && !revision.isBlank()) {
            environment.setVersion(revision);
        }

        return environment;
    }

    private List<String> parseProfiles(String profile) {
        if (profile == null || profile.isBlank()) {
            return List.of();
        }

        return Arrays.stream(profile.split(","))
            .map(String::trim)
            .filter(value -> !value.isEmpty())
            .toList();
    }

    private void validateApplication(String application) {
        if (application == null || application.isBlank()) {
            throw new IllegalArgumentException(
                "Application name must not be blank"
            );
        }

        // Áp dụng allowlist/tenant policy của hệ thống tại đây.
    }
}
~~~

Đây là một khung triển khai. Cần bổ sung <code>ConfigDocumentStore</code>, chính sách label, xác thực application, xử lý lỗi và cấu hình bean phù hợp với backend thực tế.

### Đăng ký repository trong Config Server

Ứng dụng Config Server vẫn dùng cấu hình bật server thông thường:

~~~java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Đảm bảo package chứa <code>DatabaseEnvironmentRepository</code> nằm trong component scan hoặc được đăng ký qua một <code>@Bean</code>. Nếu dự án có nhiều <code>EnvironmentRepository</code>, xác định rõ Config Server đang dùng composite repository hay repository được chọn theo cấu hình. Tránh đăng ký custom repository rồi vẫn vô tình để một cấu hình khác phục vụ request.

### Vì sao tạo Environment mới cho mỗi lần gọi?

Không giữ một Environment mutable làm field dùng chung trong singleton repository. Nhiều request có thể đồng thời gọi <code>findOne</code> cho application, profile và label khác nhau. Nếu dùng chung object, property source của request này có thể lọt sang request khác.

Mỗi lần gọi cần tạo Environment mới, map mới hoặc snapshot immutable. Repository singleton có thể an toàn đa luồng khi dependency store và cache bên dưới cũng thread-safe.

## 8. Quyết định cách xử lý khi không có document

Không có dữ liệu có thể có nhiều ý nghĩa:

- Application chưa được đăng ký.
- Label không tồn tại.
- Profile không có override riêng nhưng vẫn có cấu hình dùng chung.
- Backend tạm thời không truy cập được.
- Người gọi không có quyền đọc tenant/application.

Không gộp tất cả thành một Environment rỗng mà không có quy ước. Một Environment rỗng có thể khiến Config Server trả response thành công nhưng client chạy với default ngoài dự kiến.

Chính sách cần xác định:

| Trường hợp | Cách xử lý nên chọn |
|---|---|
| Application hợp lệ, chỉ có cấu hình dùng chung | Trả các nguồn dùng chung |
| Profile hợp lệ nhưng không có document riêng | Tiếp tục với nguồn thấp hơn nếu policy cho phép |
| Label không tồn tại | Báo lỗi rõ ràng, không tự chuyển label |
| Application không tồn tại | Empty Environment hoặc 404 theo <code>accept-empty</code> và policy server |
| Backend timeout | Trả lỗi backend, không giả vờ là không có cấu hình |
| Không đủ quyền | Từ chối truy cập, không tiết lộ dữ liệu tenant khác |

Config Server có chính sách <code>accept-empty</code> để quyết định hành vi khi Environment không có property source trong một số phiên bản. Hãy kiểm tra cấu hình và contract của release đang dùng. Nếu repository tự ném exception, cần xác minh exception được ánh xạ thành HTTP status phù hợp thay vì thành 500 chung chung.

Không trả thông báo lỗi chứa SQL, filesystem path nội bộ, token hoặc secret.

## 9. Ánh xạ label, version và state

Ba trường metadata này giúp client và operator xác định nguồn cấu hình đang dùng.

### Label

Label là giá trị được yêu cầu hoặc đã phân giải. Nếu client gửi null/blank và backend có default label, Environment nên phản ánh label thực tế được dùng theo chính sách backend.

### Version

Với Git, version thường có thể là commit ID. Với database, có thể là revision ID hoặc version của release. Giá trị cần đủ để tái lập nội dung đã trả.

Nếu một Environment ghép nhiều backend có revision độc lập, không gán tùy tiện version của một backend cho toàn bộ response. Có thể:

- Chỉ set <code>Environment.version</code> khi có một revision chung có ý nghĩa.
- Ghi revision từng nguồn trong log hoặc metadata mở rộng được thiết kế rõ.
- Dùng một release manifest tổng hợp nếu hệ thống có version cấu hình thống nhất.

### State

<code>state</code> có thể mang metadata trạng thái do repository/backend cung cấp. Chỉ dùng nếu có ngữ nghĩa cụ thể; không dùng làm nơi nhét thông tin tùy ý hoặc secret. Nếu backend không có state hữu ích, để trống.

## 10. Giữ nguồn gốc thuộc tính để hỗ trợ chẩn đoán

Khi một property có nhiều bản khai báo, người vận hành cần biết nó đến từ document nào. Tên <code>PropertySource</code> là thông tin tối thiểu:

~~~text
orders-service-prod.yml
orders-service.yml
application-prod.yml
application.yml
~~~

Nếu backend hỗ trợ origin theo từng property, hãy giữ metadata đó khi phiên bản Spring Cloud Config đang dùng hỗ trợ. Một số API/release có overload liên quan tới <code>includeOrigin</code>; kiểm tra interface của đúng release train trước khi implement thêm method này.

Không đưa <code>origin</code> thành một property giả trong map <code>source</code>, ví dụ <code>__origin.orders.timeout</code>, vì client có thể hiểu đó là cấu hình nghiệp vụ thật. Metadata nguồn cần được biểu diễn qua cơ chế origin mà framework hỗ trợ hoặc ghi log/tracing riêng.

Origin nên chỉ ra vị trí an toàn như file và dòng, key trong store hoặc revision. Không chứa giá trị bí mật hoặc đường dẫn nội bộ nhạy cảm.

## 11. Xử lý profile nhiều giá trị và cấu hình phân tầng

Profile truyền vào <code>findOne</code> có thể là chuỗi nhiều profile. Repository cần phân giải đúng thứ tự và quy tắc fallback.

Ví dụ request:

~~~text
application = orders-service
profile = prod,cloud
label = release-1
~~~

Một cây cấu hình minh họa:

~~~text
application.yml
application-prod.yml
application-cloud.yml
orders-service.yml
orders-service-prod.yml
orders-service-cloud.yml
~~~

Không phải backend nào cũng dùng đúng quy tắc file giống Git repository mặc định. Custom repository phải định nghĩa:

- Profile nào được truy vấn.
- Có đọc từng profile riêng hay kết hợp thành một context.
- Thứ tự profile ảnh hưởng precedence thế nào.
- Có cho phép fallback về cấu hình dùng chung không.
- Profile không tồn tại có phải lỗi không.

Giữ quy tắc này nhất quán với cách Config Server client yêu cầu profile. Việc tự bỏ qua profile không tồn tại hoặc sắp xếp lại profile có thể làm response khác với ý định của client.

## 12. Composite repository và thứ tự nguồn

Một Config Server có thể kết hợp nhiều repository, ví dụ Git và Vault hoặc Git và backend tùy chỉnh. Có hai cách tiếp cận:

1. Mỗi repository trả Environment riêng và Config Server ghép chúng theo cơ chế composite đã cấu hình.
2. Một custom repository đóng vai trò aggregator, tự đọc nhiều backend và tạo một Environment hoàn chỉnh.

Không nên vô tình dùng cả hai cách cùng lúc, vì property source có thể bị lặp hoặc thứ tự precedence khó dự đoán.

Nếu custom repository là aggregator:

- Xác định rõ backend nào có ưu tiên cao.
- Đặt tên property source có backend/source identity.
- Giữ revision từng backend nếu có.
- Xử lý lỗi backend bắt buộc và tùy chọn riêng.
- Không để một backend rỗng âm thầm che lỗi backend bắt buộc.

Nếu dùng composite repository có sẵn, đọc cấu hình thứ tự repository của đúng phiên bản Spring Cloud. Xác minh thứ tự cuối bằng endpoint response; không chỉ dựa vào thứ tự bean được tạo trong Spring context.

## 13. Kiểm thử precedence của findOne

Unit test cần xác minh cả metadata và thứ tự property source. Ví dụ với JUnit và Mockito:

~~~java
@Test
void returnsPropertySourcesInDescendingPriorityOrder() {
    when(store.resolveLabel("release-1"))
        .thenReturn("release-1");

    when(store.load(
            eq("orders-service"),
            eq(List.of("prod")),
            eq("release-1")
    )).thenReturn(List.of(
        new ConfigDocument(
            "application.yml", 10,
            Map.of("orders.timeout", "5s"), "r1"
        ),
        new ConfigDocument(
            "application-prod.yml", 20,
            Map.of("orders.timeout", "4s"), "r1"
        ),
        new ConfigDocument(
            "orders-service.yml", 30,
            Map.of("orders.timeout", "3s"), "r1"
        ),
        new ConfigDocument(
            "orders-service-prod.yml", 40,
            Map.of("orders.timeout", "2s"), "r1"
        )
    ));

    when(store.revisionFor(
            "orders-service",
            List.of("prod"),
            "release-1"
    )).thenReturn("r1");

    Environment result =
        repository.findOne("orders-service", "prod", "release-1");

    assertThat(result.getName()).isEqualTo("orders-service");
    assertThat(result.getProfiles()).containsExactly("prod");
    assertThat(result.getLabel()).isEqualTo("release-1");
    assertThat(result.getVersion()).isEqualTo("r1");

    assertThat(result.getPropertySources())
        .extracting(PropertySource::getName)
        .containsExactly(
            "orders-service-prod.yml",
            "orders-service.yml",
            "application-prod.yml",
            "application.yml"
        );

    assertThat(result.getPropertySources().get(0).getSource())
        .containsEntry("orders.timeout", "2s");
}
~~~

Test này giả định <code>priority</code> càng lớn thì precedence càng cao và repository thêm các nguồn theo thứ tự đã sort. Nếu đổi cách sắp xếp hoặc dùng <code>addFirst</code>, test phải phát hiện sự đảo thứ tự.

Các test khác nên bao gồm:

- Profile có nhiều giá trị và khoảng trắng.
- Label null/blank được phân giải đúng default.
- Label không tồn tại.
- Application không hợp lệ hoặc không được phép.
- Không có document.
- Backend timeout.
- Hai nguồn trùng key.
- Giá trị Boolean, Number, List và Map.
- Không rò dữ liệu giữa hai request đồng thời.
- Revision nhất quán khi có nhiều document.

## 14. Integration test qua HTTP endpoint

Unit test xác nhận logic <code>findOne</code>, nhưng integration test cần xác minh Config Server controller serialize Environment đúng.

Ví dụ request:

~~~bash
curl --fail --silent --show-error \
  "http://localhost:8888/orders-service/prod/release-1"
~~~

Kiểm tra response:

- HTTP status đúng với policy.
- <code>name</code>, <code>profiles</code> và <code>label</code> đúng.
- <code>version</code> có giá trị khi backend cung cấp.
- <code>propertySources</code> xuất hiện theo đúng thứ tự.
- Mỗi source có <code>name</code> ổn định và <code>source</code> chứa key/value đúng.
- Property trùng key cho kết quả theo precedence đã kiểm thử.
- Không có internal field hoặc secret ngoài dự kiến.

Nên có test cho nhiều request liên tiếp với application/profile/label khác nhau. Điều này phát hiện lỗi repository giữ Environment hoặc Map mutable dùng chung.

Integration test cũng cần kiểm tra authentication và authorization nếu Config Server bảo vệ endpoint. Một repository đúng không có nghĩa mọi client được phép đọc mọi application.

## 15. Tối ưu findOne khi số client và request tăng

Trong môi trường nhiều ứng dụng, <code>findOne</code> có thể được gọi đồng thời bởi nhiều client khi startup hoặc refresh. Một implementation chậm hoặc có N+1 query sẽ làm Config Server thành nút thắt.

### Tránh N+1 query

Thay vì truy vấn từng property hoặc từng file bằng một round trip riêng, backend nên tải một nhóm document cần thiết trong một lần hoặc một số ít truy vấn batch.

Không thiết kế <code>findOne</code> gọi backend một lần cho mỗi property. Contract trả toàn bộ Environment cho request; hãy tận dụng để đọc cấu hình theo batch.

### Cache theo khóa đầy đủ

Nếu dùng cache, key tối thiểu cần phân biệt:

- Application.
- Danh sách profile theo đúng thứ tự.
- Resolved label/revision.
- Tenant hoặc namespace nếu có.
- Các tùy chọn ảnh hưởng kết quả như include-origin.

Không cache chỉ theo application vì có thể trả nhầm cấu hình profile hoặc tenant. Cache nên có TTL, giới hạn kích thước và cơ chế invalidation khi revision thay đổi.

### Không chia sẻ object mutable

Có thể cache immutable snapshot của document hoặc serialized representation. Khi trả response, tạo Environment mới và PropertySource/map mới hoặc dùng cấu trúc immutable an toàn.

Không trả cùng một Environment object mutable cho nhiều request. Một thao tác thêm PropertySource hoặc sửa map có thể làm request khác nhận dữ liệu không nhất quán.

### Timeout và bulkhead

- Đặt timeout cho database/Git/Vault/API backend.
- Giới hạn số truy vấn đồng thời.
- Dùng connection pool phù hợp.
- Tách lỗi backend chậm khỏi lỗi không tìm thấy cấu hình.
- Có metric cho thời gian và lỗi riêng của <code>findOne</code>.

Không để thread HTTP của Config Server chờ backend vô hạn. Retry nên có giới hạn và không nhân bản tải khi backend đang quá tải.

## 16. Nâng cấp Spring Cloud mà không phá contract

Các class <code>Environment</code>, <code>PropertySource</code> và interface <code>EnvironmentRepository</code> là API của Spring Cloud Config. Khi nâng cấp Spring Boot hoặc Spring Cloud release train:

1. Nâng dependency theo Spring Cloud BOM tương thích.
2. Compile custom repository với API mới.
3. Kiểm tra method signature của <code>EnvironmentRepository</code>, gồm overload hoặc default method nếu release có bổ sung.
4. Kiểm tra constructor và metadata của <code>Environment</code>/<code>PropertySource</code>.
5. Kiểm tra origin support và serialization.
6. Chạy unit test precedence và profile.
7. Chạy integration test Environment endpoint.
8. Kiểm tra behavior khi label không tồn tại và Environment rỗng.
9. Kiểm tra security và response không lộ dữ liệu.
10. Chạy canary Config Server trước khi thay toàn bộ replica.

Không phụ thuộc vào class nội bộ của <code>EnvironmentController</code> nếu chỉ cần cung cấp repository. Internal implementation có thể thay đổi giữa các release trong khi contract repository được giữ ổn định hơn.

Nếu API mới thêm overload, không tự suy đoán ý nghĩa. Đọc Javadoc của dependency đang dùng và xác định có cần hỗ trợ <code>includeOrigin</code> hoặc metadata mới không. Giữ logic backend độc lập với DTO thông qua một mapper nhỏ để giảm phạm vi phải sửa khi nâng cấp.

## 17. Log, metric và truy vết cho findOne

Mỗi lần <code>findOne</code> nên có thể được quan sát mà không log nội dung cấu hình.

Metadata hữu ích:

- Application.
- Profiles.
- Label đã phân giải.
- Backend.
- Số PropertySource được trả.
- Revision/version.
- Duration.
- Outcome hoặc error category.
- Correlation/trace ID.

Metric có thể gồm:

| Metric | Ý nghĩa |
|---|---|
| <code>config.server.environment.find</code> | Thời gian xử lý findOne |
| <code>config.server.environment.find.errors</code> | Số lần findOne thất bại |
| <code>config.server.environment.property-sources</code> | Số PropertySource được trả |
| <code>config.server.backend.lookup</code> | Thời gian truy vấn backend |
| <code>config.server.backend.errors</code> | Lỗi backend |

Đây là metric tùy chỉnh minh họa. Không dùng application tùy ý, label commit hoặc property key làm tag có cardinality cao nếu danh sách giá trị không được giới hạn. Không log map <code>source</code>, token hoặc secret đã giải mã.

## 18. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm tra |
|---|---|---|
| Client nhận sai giá trị trùng key | PropertySource order bị đảo | Kiểm tra thứ tự JSON và test precedence |
| Environment không có profile | Không parse profile hoặc tạo sai constructor | Kiểm tra <code>getProfiles()</code> |
| Label response khác yêu cầu | Tự thay label không tồn tại bằng default | Kiểm tra label resolver |
| Client không bind được property | Map key hoặc kiểu value không đúng | Kiểm tra source map và binder |
| Request khác application nhận dữ liệu cũ | Dùng chung Environment mutable hoặc cache key thiếu application | Kiểm tra thread safety và cache key |
| Endpoint trả 200 nhưng cấu hình rỗng | Empty Environment được trả mà không có policy | Kiểm tra <code>accept-empty</code> và store lookup |
| Nguồn Git/Vault ghi đè khó hiểu | Composite repository order chưa rõ | Kiểm tra propertySources và backend priority |
| Origin không hiển thị | Mapper bỏ metadata hoặc API version không hỗ trợ | Kiểm tra include-origin support |
| Config Server chậm khi startup đồng loạt | N+1 query hoặc backend không giới hạn concurrency | Đo findOne/backend duration |
| Nâng cấp làm custom repository không compile | API signature hoặc DTO constructor thay đổi | Compile theo BOM mới và cập nhật adapter |

## 19. Checklist hoàn thiện EnvironmentRepository

- [ ] <code>findOne</code> nhận và giữ đúng application, profile, label.
- [ ] Profile nhiều giá trị được parse và giữ thứ tự.
- [ ] Default label được phân giải tại một nơi thống nhất.
- [ ] Environment mới được tạo cho mỗi request.
- [ ] <code>name</code>, <code>profiles</code>, <code>label</code>, <code>version</code> và <code>state</code> được điền đúng ngữ nghĩa.
- [ ] Mỗi document được ánh xạ thành PropertySource riêng khi cần giữ precedence.
- [ ] <code>PropertySource.name</code> ổn định và có thể truy vết.
- [ ] Map source giữ kiểu String, Number, Boolean, List và Map phù hợp.
- [ ] PropertySource được sắp xếp theo precedence và có test xác nhận.
- [ ] Không nhầm DTO PropertySource của Config Server với Spring Framework PropertySource.
- [ ] Missing application/label, empty config và backend failure có semantics rõ.
- [ ] Origin metadata được giữ nếu API/release hỗ trợ.
- [ ] Composite backend có thứ tự rõ ràng và không ghép lặp.
- [ ] Repository thread-safe, không chia sẻ mutable Environment.
- [ ] Cache key bao gồm application, profiles, label/revision và tenant cần thiết.
- [ ] Có timeout, batch lookup và metric cho backend.
- [ ] Unit test và HTTP integration test xác minh response.
- [ ] Nâng cấp được kiểm tra bằng BOM tương thích và canary.
- [ ] Log/metric không chứa property values, token hoặc secret.

<code>findOne</code> là điểm chuyển đổi từ yêu cầu application/profile/label thành Environment mà Config Server trả cho client. Một implementation tốt tạo Environment mới, ánh xạ từng tài liệu thành PropertySource có tên rõ ràng, giữ kiểu dữ liệu và sắp xếp nguồn theo precedence đã định. Kết hợp contract rõ, xử lý label/missing data nhất quán, test ở cả repository lẫn HTTP endpoint và tối ưu truy vấn/cache giúp custom Config Server phục vụ nhiều ứng dụng ổn định qua các lần mở rộng và nâng cấp.

