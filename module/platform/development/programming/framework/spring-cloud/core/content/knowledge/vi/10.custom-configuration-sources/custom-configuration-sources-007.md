# Đặt tên nguồn ổn định và kiểm soát độ ưu tiên

Bài học thuộc chương **Nguồn cấu hình tùy biến** của module **SPRING_CLOUD_CORE**. Khi ứng dụng cần lấy cấu hình từ một nguồn ngoài cơ chế mặc định của Spring Boot, chẳng hạn tenant settings, feature policy, secret/configuration service nội bộ hoặc dữ liệu được tạo trong lúc khởi động, ta có thể đưa dữ liệu đó vào Spring `Environment` thông qua một `PropertySource`.

Việc thêm một nguồn cấu hình không chỉ là đưa một map vào Environment. Hai quyết định có ảnh hưởng trực tiếp đến hành vi ứng dụng là:

- **Tên nguồn (PropertySource name):** định danh ổn định để quản lý, thay thế, so sánh và chẩn đoán nguồn.
- **Vị trí trong danh sách nguồn:** quyết định nguồn nào thắng khi nhiều nguồn cùng khai báo một property.

Nếu đặt tên không ổn định hoặc thêm source ở vị trí không phù hợp, cấu hình có thể bị ghi đè ngoài dự kiến, bị loại khi merge Environment, hoặc không được nhận diện đúng trong quá trình refresh. Bài này tập trung vào cách thiết kế và kiểm chứng hai quyết định đó trong Spring Framework, Spring Boot và Spring Cloud Context.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích cấu trúc và vai trò của `PropertySource` trong `Environment`.
2. Đặt tên source ổn định, duy nhất và có ý nghĩa theo phạm vi.
3. Kiểm soát precedence bằng `MutablePropertySources`.
4. Phân biệt `addFirst`, `addLast`, `addBefore`, `addAfter`, `replace` và `remove`.
5. Hiểu điều gì xảy ra khi hai source trùng tên và khi một source chứa khóa trùng với source khác.
6. Chọn đúng thời điểm đăng ký source bằng `EnvironmentPostProcessor`, `ApplicationContextInitializer` hoặc `@PropertySource`.
7. Cập nhật nguồn cấu hình tùy biến an toàn khi ứng dụng đang chạy.
8. Kiểm thử source order, name collision, giá trị hiệu lực và tác động đến refresh.
9. Tránh ghi đè nhầm cấu hình hệ thống, làm lộ secret hoặc gọi nguồn từ xa quá nhiều lần.

## 2. PropertySource là gì?

`Environment` của Spring giữ một danh sách các `PropertySource`. Mỗi PropertySource đại diện cho một nguồn dữ liệu có thể trả về giá trị theo tên property.

Ví dụ, các nguồn có thể đến từ:

- File cấu hình của Spring Boot như `application.yml`.
- Environment variables và JVM system properties.
- Command-line arguments.
- Một map do ứng dụng tự tạo.
- Một file ngoài được nạp bằng code.
- Cấu hình từ Spring Cloud Config hoặc một hệ thống cấu hình khác.
- Một nguồn động do ứng dụng cung cấp.

Một `PropertySource` có hai thông tin quan trọng: **name** và **source**. Name là định danh của nguồn trong danh sách. Source là đối tượng dữ liệu mà PropertySource dùng để tra cứu.

~~~mermaid
flowchart TD
    APP["Ứng dụng / @ConfigurationProperties / @Value"] --> ENV["Spring Environment"]
    ENV --> LIST["MutablePropertySources: danh sách có thứ tự"]
    LIST --> P1["commandLineArgs"]
    LIST --> P2["systemProperties"]
    LIST --> P3["custom-tenant-policy"]
    LIST --> P4["applicationConfig"]
    P1 --> RESOLVE["Property resolution: nguồn ưu tiên cao nhất có giá trị"]
    P2 --> RESOLVE
    P3 --> RESOLVE
    P4 --> RESOLVE
~~~

Sơ đồ chỉ minh họa một danh sách có thứ tự. Thứ tự thực tế của các source mặc định phụ thuộc phiên bản Spring Boot, kiểu ứng dụng và cách khởi động.

### 2.1. Ví dụ với MapPropertySource

Spring cung cấp `MapPropertySource` để bọc một map:

~~~java
Map<String, Object> values = Map.of(
    "app.region", "ap-southeast",
    "app.routing.timeout", "800ms"
);

PropertySource<?> source =
    new MapPropertySource("custom-routing-defaults", values);
~~~

- `custom-routing-defaults` là tên source.
- `values` là dữ liệu.
- `app.region` và `app.routing.timeout` là các property key.

Tên source không phải prefix của property key. Đổi tên source không làm đổi tên các property bên trong map.

### 2.2. Một khóa có thể tồn tại ở nhiều nguồn

Giả sử hai source khác tên cùng chứa `app.region`:

| Source | Giá trị |
| --- | --- |
| `custom-routing-defaults` | `ap-southeast` |
| `applicationConfig: [classpath:/application.yml]` | `eu-west` |

Giá trị được chọn phụ thuộc vị trí hai source trong danh sách. Spring tra cứu từ nguồn có precedence cao xuống thấp; source đầu tiên trả về giá trị khác `null` sẽ thắng.

Đây là quy tắc theo **thứ tự**, không theo tên source. Tên source giúp quản lý và nhận diện; vị trí source mới quyết định precedence.

## 3. Tên PropertySource phải ổn định

### 3.1. Vì sao tên quan trọng?

Tên PropertySource được dùng để nhận diện source trong `MutablePropertySources`. Nhiều thao tác quản lý source tìm source bằng tên, ví dụ `replace(name, source)`, `remove(name)`, `addBefore(relativeName, source)` và `addAfter(relativeName, source)`.

Một tên ổn định giúp:

- Thay thế đúng source khi tải lại cấu hình.
- Tránh tạo nhiều bản sao của cùng nguồn sau nhiều lần refresh.
- Phân biệt source nội bộ với source do Spring Boot/Spring Cloud tạo.
- Chẩn đoán thứ tự và nguồn cung cấp giá trị.
- So sánh các PropertySource giữa các lần refresh.
- Tránh xung đột tên khi ghép Environment parent–child.

Ví dụ tên có ý nghĩa:

~~~text
platform-tenant-defaults
platform-tenant-overrides
company-feature-policy
remote-runtime-settings
secrets-from-vault
~~~

Tên nên mô tả **chủ sở hữu và mục đích** của nguồn. Nếu source chứa cấu hình theo tenant, có thể đưa tenant identifier vào tên khi mỗi tenant thực sự có một source riêng. Không nên đưa timestamp hoặc UUID ngẫu nhiên vào tên cho mỗi lần tải.

### 3.2. Không tạo tên ngẫu nhiên ở mỗi lần refresh

Ví dụ không nên làm:

~~~java
String name = "remote-config-" + UUID.randomUUID();
environment.getPropertySources().addFirst(
    new MapPropertySource(name, values)
);
~~~

Mỗi lần chạy đoạn code này sẽ tạo một source mới. Sau nhiều lần refresh, danh sách có thể chứa nhiều source cùng mục đích. Source cũ có thể vẫn nằm trong Environment và tiếp tục thắng source mới tùy vị trí.

Nên dùng một hằng số ổn định:

~~~java
static final String SOURCE_NAME = "platform-remote-config";
~~~

Khi dữ liệu mới đến, thay source có tên đó hoặc cập nhật một snapshot dữ liệu được quản lý rõ ràng. Không thêm source mới chỉ để biểu thị một phiên bản dữ liệu mới.

### 3.3. Tên phải duy nhất trong một MutablePropertySources

Trong một danh sách PropertySource, tên là định danh. Hai source có cùng tên không được xem như hai nguồn độc lập có thể cùng tồn tại trong danh sách đó. Các thao tác add/replace được thiết kế để quản lý source theo name.

Đặc biệt, khi child Environment merge parent Environment, source cùng tên ở child được giữ và source cùng tên ở parent bị loại khỏi danh sách child. Hai source **không được merge theo từng key**.

Vì vậy, nếu hai thành phần không có cùng chủ sở hữu hoặc không có cùng semantics, đừng đặt cùng tên source chỉ vì chúng đều là cấu hình tùy biến.

### 3.4. Đặt tên theo vai trò, không theo nơi triển khai

Tên như `/etc/app/config.yml` hoặc `classpath:/custom.yml` gắn source với một vị trí triển khai. Khi đổi từ file sang Config Server, tên source sẽ phải đổi dù nguồn vẫn mang cùng ý nghĩa.

Nếu mục tiêu là cùng một nguồn logic có thể thay đổi cách triển khai, hãy dùng tên theo vai trò như `platform-routing-policy`. Khi chẩn đoán, ghi thêm metadata về loại backend hoặc revision, nhưng giữ tên source ổn định.

## 4. MutablePropertySources và precedence

`ConfigurableEnvironment.getPropertySources()` trả về đối tượng `MutablePropertySources`. Đây là danh sách có thứ tự, cho phép thêm, thay thế, di chuyển và gỡ PropertySource.

### 4.1. Các thao tác chính

| API | Hành vi | Khi nên dùng |
| --- | --- | --- |
| `addFirst(source)` | Đặt source ở đầu danh sách, precedence cao nhất. | Override mặc định có chủ đích. |
| `addLast(source)` | Đặt source ở cuối danh sách, precedence thấp nhất. | Fallback/default có chủ đích. |
| `addBefore(name, source)` | Đặt source ngay trước source có tên chỉ định. | Muốn chèn vào vị trí tương đối rõ ràng. |
| `addAfter(name, source)` | Đặt source ngay sau source có tên chỉ định. | Muốn đặt source dưới một nguồn cụ thể nhưng trên các nguồn phía sau. |
| `replace(name, source)` | Thay source đang có bằng source mới tại vị trí của source đó. | Cập nhật dữ liệu mà không đổi precedence. |
| `remove(name)` | Gỡ source theo tên và trả về source bị gỡ nếu có. | Thu hồi nguồn cấu hình đã hết hiệu lực. |

Các API thêm source theo tên có thể loại source cũ cùng tên trước khi chèn source mới, để một tên không tạo nhiều entry trong danh sách. `replace` yêu cầu source có tên cần thay thế phải tồn tại; hãy kiểm tra danh sách hoặc xử lý tình huống chưa có source trước khi gọi.

### 4.2. addFirst: precedence cao nhất

~~~java
ConfigurableEnvironment environment = ...;

Map<String, Object> values = Map.of(
    "app.feature.enabled", true
);

environment.getPropertySources().addFirst(
    new MapPropertySource("platform-feature-override", values)
);
~~~

Source này được tìm trước các source còn lại. Nếu nó chứa `app.feature.enabled`, giá trị của nó thắng các nguồn thấp hơn.

Chỉ dùng `addFirst` khi muốn source có quyền override rất cao. Nếu source là dữ liệu mặc định, đặt ở đầu danh sách có thể vô tình ghi đè system property, environment variable hoặc command-line argument.

### 4.3. addLast: fallback thấp nhất

~~~java
environment.getPropertySources().addLast(
    new MapPropertySource(
        "platform-safe-defaults",
        Map.of("app.routing.timeout", "1s")
    )
);
~~~

Source ở cuối chỉ cung cấp giá trị khi không có source ưu tiên cao hơn trả về property đó. Đây là vị trí phù hợp cho default do nền tảng cung cấp, nếu chính sách ứng dụng cho phép.

### 4.4. addBefore và addAfter: kiểm soát tương đối

~~~java
MutablePropertySources sources = environment.getPropertySources();

sources.addAfter(
    StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
    new MapPropertySource("platform-runtime-settings", values)
);
~~~

Đoạn code đặt source ngay sau source environment variables. Khi đó, system environment có precedence cao hơn source tùy biến, còn source tùy biến có thể cao hơn những source nằm sau nó.

`addBefore` hoạt động tương tự nhưng đặt source trước source tham chiếu.

Tên tham chiếu phải tồn tại. Nếu không, thao tác có thể ném exception. Không hard-code tên source của Spring Boot mà không kiểm tra phiên bản và kiểu Environment; một số ứng dụng web có thêm source đặc thù. Khi cần một vị trí tương đối, hãy kiểm tra danh sách hiện tại và viết test cho cấu trúc mong đợi.

### 4.5. replace: thay nội dung, giữ vị trí

~~~java
MutablePropertySources sources = environment.getPropertySources();

PropertySource<?> replacement =
    new MapPropertySource("platform-runtime-settings", newValues);

sources.replace("platform-runtime-settings", replacement);
~~~

Nếu source tồn tại, source mới được đặt tại vị trí cũ. Đây là cách phù hợp khi cần thay dữ liệu nhưng giữ nguyên precedence đã được thiết kế.

Không nên dùng `remove` rồi `addFirst` nếu mục tiêu chỉ là cập nhật nội dung; làm vậy có thể vô tình thay đổi precedence.

### 4.6. Kiểm tra thứ tự thực tế

Có thể in tên source theo thứ tự:

~~~java
environment.getPropertySources().forEach(source ->
    System.out.println(source.getName())
);
~~~

Kết quả này hữu ích trong môi trường phát triển. Trong production, tránh log toàn bộ nội dung source vì có thể chứa secret. Nếu cần quan sát, ghi tên, loại source, thứ tự và revision không nhạy cảm.

## 5. Giá trị null, rỗng và precedence

Một PropertySource trả về `null` khi nó không cung cấp giá trị cho key. Khi đó, resolver tiếp tục tìm source thấp hơn.

Giá trị chuỗi rỗng `""` là một giá trị khác null. Nó có thể ghi đè một giá trị thấp hơn. Vì vậy, một override có giá trị rỗng có thể làm ứng dụng nhận chuỗi rỗng thay vì fallback.

Ví dụ:

| Source ưu tiên cao | Source ưu tiên thấp | Kết quả tra cứu |
| --- | --- | --- |
| Không có key (null) | `ap-southeast` | `ap-southeast` |
| `""` | `ap-southeast` | Chuỗi rỗng |
| `eu-west` | `ap-southeast` | `eu-west` |

Với cấu hình boolean, số hoặc duration, việc chuyển đổi kiểu diễn ra sau khi resolver tìm được giá trị. Một giá trị rỗng hoặc sai định dạng có thể gây lỗi binding/conversion thay vì tự động rơi về nguồn thấp hơn.

Nếu muốn một source biểu thị “không cấu hình”, hãy trả về null cho key đó hoặc không đưa key vào map. Đừng dùng chuỗi rỗng làm ký hiệu fallback nếu ứng dụng chưa định nghĩa semantics rõ ràng.

## 6. Đăng ký custom PropertySource vào đúng thời điểm

Vị trí và thời điểm đăng ký source quan trọng như nhau. Nếu một property cần được dùng trước khi ApplicationContext được tạo, source phải được thêm vào Environment đủ sớm.

### 6.1. EnvironmentPostProcessor

`EnvironmentPostProcessor` là extension point của Spring Boot để tùy chỉnh Environment trong giai đoạn chuẩn bị ứng dụng, trước khi context được refresh. Đây là lựa chọn phù hợp khi custom source cần tham gia vào quá trình cấu hình sớm.

Ví dụ:

~~~java
public final class PlatformDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "platform-runtime-defaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> values = new LinkedHashMap<>();
        values.put("app.routing.timeout", "800ms");
        values.put("app.routing.strategy", "round-robin");

        PropertySource<?> source =
                new MapPropertySource(SOURCE_NAME, values);

        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            sources.replace(SOURCE_NAME, source);
        } else {
            sources.addAfter(
                StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
                source
            );
        }
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Ví dụ đặt source sau system environment để system environment vẫn có thể override. Thứ tự của các EnvironmentPostProcessor khác và source có sẵn phụ thuộc phiên bản Boot. Nếu ứng dụng cần chèn sau một source cụ thể, xác minh source đó tồn tại trong môi trường thực tế.

Đăng ký processor trong file:

~~~text
META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.config.PlatformDefaultsEnvironmentPostProcessor
~~~

Tên class phải khớp package thực tế. EnvironmentPostProcessor cần nằm trên classpath lúc Spring Boot khởi động. Hãy kiểm tra cơ chế đăng ký extension của phiên bản Boot dự án đang dùng.

**Chú ý về thứ tự:** `Ordered.LOWEST_PRECEDENCE` chỉ điều khiển thứ tự processor so với các processor khác. Nó không tự quyết định precedence của PropertySource. Precedence vẫn do `addAfter` hoặc thao tác trên `MutablePropertySources` quyết định.

### 6.2. ApplicationContextInitializer

`ApplicationContextInitializer` chạy trên context trước khi context được refresh. Nó phù hợp khi source cần được thêm trước lúc bean được khởi tạo, nhưng không nhất thiết phải tham gia giai đoạn xử lý Config Data sớm nhất.

Ví dụ:

~~~java
public class PlatformContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of(
            "app.tenant.mode", "standard"
        );

        context.getEnvironment()
            .getPropertySources()
            .addLast(new MapPropertySource("platform-tenant-defaults", values));
    }
}
~~~

Có thể đăng ký initializer qua `SpringApplication.addInitializers` hoặc cơ chế cấu hình bootstrap phù hợp. Cần bảo đảm initializer được đăng ký trước khi context refresh.

Nếu property cần thiết để quyết định Config Data locations, profile hoặc các bước bootstrap sớm, initializer có thể là quá muộn. Khi đó nên dùng EnvironmentPostProcessor hoặc extension point Config Data phù hợp.

### 6.3. @PropertySource

`@PropertySource` có thể đưa file properties vào Environment trong quá trình xử lý configuration class:

~~~java
@Configuration
@PropertySource(
    name = "platform-feature-defaults",
    value = "classpath:platform-feature-defaults.properties"
)
class PlatformFeatureConfiguration {
}
~~~

Ví dụ file:

~~~properties
app.feature.enabled=true
app.feature.rollout-percent=10
~~~

`@PropertySource` thuận tiện cho nguồn file classpath tĩnh. Tuy nhiên, nó được xử lý trong quá trình đăng ký cấu hình, muộn hơn một số thuộc tính cần thiết ở giai đoạn bootstrap sớm, chẳng hạn các thiết lập quyết định Config Data loading. Nếu nhiều `@PropertySource` được phát hiện qua component scan, thứ tự có thể khó dự đoán; đừng dùng nó làm cơ chế precedence phức tạp nếu thứ tự là yêu cầu quan trọng.

Mặc định, `@PropertySource` phù hợp với properties/XML theo hỗ trợ của factory mặc định. Nếu muốn nạp YAML hoặc định dạng riêng, cần `PropertySourceFactory` tương ứng hoặc dùng cơ chế Config Data phù hợp.

### 6.4. So sánh extension point

| Cơ chế | Thời điểm | Trường hợp phù hợp |
| --- | --- | --- |
| `EnvironmentPostProcessor` | Trong giai đoạn chuẩn bị Environment của Spring Boot. | Nguồn cần có sớm, trước khi ApplicationContext được refresh. |
| `ApplicationContextInitializer` | Sau khi context được tạo, trước refresh. | Nguồn cần trước khi bean khởi tạo, nhưng không cần can thiệp Config Data sớm. |
| `@PropertySource` | Khi configuration class được xử lý. | File cấu hình classpath đơn giản gắn với một cấu hình Java. |
| Config Data resolver/loader | Trong pipeline Config Data của Boot. | Định dạng hoặc protocol cấu hình tùy biến cần tích hợp như một Config Data location. |

Chọn extension point theo thời điểm property cần có, không chỉ theo độ ngắn của đoạn code.

## 7. Tích hợp nguồn động và cập nhật cấu hình

Một custom PropertySource có thể bọc một dữ liệu thay đổi theo thời gian. Có hai kiểu thiết kế thường gặp.

### 7.1. Source chứa snapshot bất biến

Mỗi lần nhận cấu hình mới, tạo map mới rồi thay source:

~~~java
Map<String, Object> nextValues = loadValidatedValues();

PropertySource<?> replacement =
    new MapPropertySource(SOURCE_NAME, Map.copyOf(nextValues));

MutablePropertySources sources = environment.getPropertySources();

if (sources.contains(SOURCE_NAME)) {
    sources.replace(SOURCE_NAME, replacement);
} else {
    sources.addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        replacement
    );
}
~~~

Ưu điểm:

- Dữ liệu mới được kiểm tra trước khi công bố.
- Source cũ vẫn tồn tại cho đến khi source mới sẵn sàng.
- Tên source ổn định nên vị trí precedence được giữ khi replace.
- Dễ gắn revision vào log hoặc metadata riêng.

`Map.copyOf` yêu cầu không có key/value null. Nếu dữ liệu có thể chứa null, cần validate hoặc dùng cấu trúc snapshot phù hợp.

### 7.2. Source động đọc từ provider

Có thể tạo subclass của `PropertySource` để truy vấn một provider:

~~~java
public final class RuntimePolicyPropertySource
        extends PropertySource<RuntimePolicyProvider> {

    public RuntimePolicyPropertySource(RuntimePolicyProvider provider) {
        super("platform-runtime-policy", provider);
    }

    @Override
    public Object getProperty(String name) {
        return getSource().find(name);
    }
}
~~~

`RuntimePolicyProvider` là interface do ứng dụng định nghĩa, có thể trả về dữ liệu từ cache hoặc snapshot nội bộ.

Không nên gọi HTTP/Config Server trực tiếp cho mọi lần `getProperty` nếu thao tác này có độ trễ hoặc có thể thất bại. Binder, placeholder resolution và các thành phần framework có thể tra cứu property nhiều lần trong startup. Một PropertySource chậm hoặc phụ thuộc mạng sẽ làm khởi động khó dự đoán.

Nếu dùng nguồn từ xa:

- Có cache và timeout rõ ràng.
- Có trạng thái last-known-good nếu chính sách cho phép.
- Validate dữ liệu trước khi công bố.
- Có revision/version để so sánh.
- Có cơ chế refresh và xử lý lỗi.
- Không log nội dung nhạy cảm.

### 7.3. Cập nhật nhiều key như một snapshot

Giả sử routing policy có ba thuộc tính liên quan:

~~~yaml
app:
  routing:
    mode: weighted
    primary-region: ap-southeast
    fallback-region: ap-northeast
~~~

Không nên cập nhật từng key trong map dùng chung khi nhiều request có thể đọc đồng thời. Một request có thể nhìn thấy mode mới nhưng region cũ.

Thay vào đó, tạo một snapshot hoàn chỉnh, validate các quan hệ giữa key rồi thay source. Nếu cần cập nhật object đang được dùng bởi bean, tiếp tục xác định cơ chế rebinding hoặc refresh scope phù hợp. Việc thay PropertySource không tự động cập nhật mọi singleton đã inject giá trị trước đó.

## 8. Quan hệ với Spring Cloud Context và refresh

Spring Cloud Context cung cấp các cơ chế để cập nhật Environment và bean khi cấu hình thay đổi. Tuy nhiên, custom PropertySource phải được tích hợp đúng vào quy trình đó.

### 8.1. Tên ổn định giúp so sánh nguồn qua refresh

Quy trình refresh thường cần so sánh các giá trị cấu hình trước và sau khi tải lại. Tên source ổn định giúp framework và người vận hành nhận diện nguồn tương ứng giữa hai lần đọc.

Nếu mỗi lần refresh source lại có tên ngẫu nhiên:
- Khó xác định source nào là phiên bản mới của source cũ.
- Dễ tích lũy nhiều source trùng mục đích.
- Khó chẩn đoán key nào đổi vì dữ liệu hay vì thứ tự source.
- Có thể làm phép so sánh nguồn và giá trị trở nên khó hiểu.

### 8.2. Thay PropertySource không tự refresh bean

Sau khi thay source:

- `Environment.getProperty(key)` có thể trả giá trị mới.
- Bean singleton đã nhận `@Value` trong constructor có thể vẫn giữ giá trị cũ.
- `@ConfigurationProperties` cần cơ chế rebinding thích hợp.
- Bean `@RefreshScope` cần target cache được invalidate để lần gọi tiếp theo tạo target mới.

Vì vậy, cần xác định rõ mục tiêu cập nhật. Chỉ thay PropertySource chưa đồng nghĩa toàn bộ ứng dụng đã sử dụng cấu hình mới.

### 8.3. Phát sự kiện và refresh

Với Spring Cloud Context, quy trình refresh có thể phát `EnvironmentChangeEvent` để rebinding các bean `@ConfigurationProperties` và cập nhật logging levels. `@RefreshScope` quản lý target cache riêng.

Không tự phát event tùy tiện chỉ để “làm mới mọi thứ”. Nếu custom source được cập nhật, hãy tích hợp vào một quy trình refresh có kiểm soát: thay source, xác định các key đổi, phát sự kiện/refresh theo API phù hợp, sau đó kiểm chứng bean và hành vi nghiệp vụ.

Với nhiều instance, mỗi instance có Environment riêng. Refresh một instance không tự cập nhật các instance còn lại; cần broadcast/rollout hoặc cơ chế phân phối phù hợp.

## 9. Thực hành: thêm source với precedence có chủ đích

Giả sử ứng dụng có ba nguồn:

1. System environment: cấu hình do nền tảng triển khai cung cấp.
2. Custom runtime defaults: cấu hình mặc định do platform team cung cấp.
3. Application config: cấu hình được đóng gói trong ứng dụng.

Mục tiêu của lab:

- Environment variable được quyền override custom source.
- Custom source được quyền override file application mặc định.
- Command-line/system properties vẫn có precedence cao hơn custom source.
- Source có tên ổn định và chỉ xuất hiện một lần.

### 9.1. Tạo source

~~~java
public final class PlatformRuntimeDefaults {
    public static final String SOURCE_NAME = "platform-runtime-defaults";

    private PlatformRuntimeDefaults() {
    }

    public static PropertySource<?> create() {
        Map<String, Object> values = Map.of(
            "app.routing.timeout", "800ms",
            "app.routing.strategy", "round-robin"
        );

        return new MapPropertySource(SOURCE_NAME, values);
    }
}
~~~

### 9.2. Chèn source sau system environment

~~~java
MutablePropertySources sources = environment.getPropertySources();
PropertySource<?> source = PlatformRuntimeDefaults.create();

if (sources.contains(PlatformRuntimeDefaults.SOURCE_NAME)) {
    sources.replace(PlatformRuntimeDefaults.SOURCE_NAME, source);
} else {
    sources.addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        source
    );
}
~~~

Thứ tự mong muốn ở phần liên quan:

~~~text
systemProperties / command-line sources (tùy loại Environment)
systemEnvironment
platform-runtime-defaults
applicationConfig
các source có precedence thấp hơn
~~~

Đây là sơ đồ định hướng. Một ứng dụng web hoặc Spring Boot version khác có thể có source bổ sung và thứ tự khác; hãy xem danh sách thực tế trước khi xác nhận.

### 9.3. Kiểm chứng bằng marker key

Trong `application.yml`:

~~~yaml
app:
  routing:
    timeout: 2s
    strategy: random
~~~

Khi custom source được thêm:

- `app.routing.timeout` mong đợi là `800ms`.
- `app.routing.strategy` mong đợi là `round-robin`.

Nếu environment variable `APP_ROUTING_TIMEOUT=1500ms` được cung cấp, nó có precedence cao hơn custom source trong sơ đồ đã chọn và kết quả mong đợi là `1500ms`.

Nếu command-line argument `--app.routing.timeout=300ms` được cung cấp, giá trị command line cần thắng theo precedence của Spring Boot.

Kết quả cần kiểm tra bằng `Environment.getProperty` và hành vi bean đã bind. Đừng chỉ kiểm tra map của custom source vì map không chứng minh source đã được thêm đúng thứ tự vào Environment.

## 10. Kiểm thử source name và precedence

### 10.1. Unit test với StandardEnvironment

Ví dụ JUnit 5:

~~~java
@Test
void customSourceOverridesApplicationDefaultButNotSystemEnvironment() {
    ConfigurableEnvironment environment = new StandardEnvironment();

    environment.getPropertySources().addLast(
        new MapPropertySource("application-test", Map.of(
            "app.region", "default-region"
        ))
    );

    environment.getPropertySources().addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        new MapPropertySource("platform-runtime-defaults", Map.of(
            "app.region", "platform-region"
        ))
    );

    assertEquals("platform-region", environment.getProperty("app.region"));
}
~~~

Test trên xác minh source custom đứng trước source được thêm bằng `addLast`. Nó không kiểm tra environment variable thực tế của máy test; muốn kiểm tra precedence đầy đủ, tạo PropertySource mô phỏng cho từng lớp hoặc dùng integration test có environment được kiểm soát.

### 10.2. Kiểm thử tên trùng

~~~java
@Test
void addingSourceWithSameNameDoesNotCreateDuplicateEntry() {
    ConfigurableEnvironment environment = new StandardEnvironment();

    environment.getPropertySources().addFirst(
        new MapPropertySource("platform-policy", Map.of("app.mode", "old"))
    );

    environment.getPropertySources().addFirst(
        new MapPropertySource("platform-policy", Map.of("app.mode", "new"))
    );

    long count = StreamSupport.stream(
        environment.getPropertySources().spliterator(), false
    ).filter(source -> source.getName().equals("platform-policy")).count();

    assertEquals(1, count);
    assertEquals("new", environment.getProperty("app.mode"));
}
~~~

Đoạn test minh họa semantics của việc thêm source có cùng tên. Nếu dùng `replace`, cần bảo đảm source đã tồn tại; test riêng cả nhánh lần đầu chưa có source và nhánh cập nhật source đã có.

### 10.3. Kiểm thử source order trực tiếp

Có thể assert thứ tự tương đối:

~~~java
List<String> names = StreamSupport.stream(
        environment.getPropertySources().spliterator(), false
    )
    .map(PropertySource::getName)
    .toList();

assertTrue(
    names.indexOf("platform-runtime-defaults")
        < names.indexOf("application-test")
);
~~~

Thứ tự là một phần của contract cấu hình. Khi nâng Spring Boot, hãy kiểm tra lại nếu test dựa vào tên hoặc vị trí source do framework tạo.

### 10.4. Ma trận kiểm chứng

| ID | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| P1 | Custom source ở đầu danh sách. | Giá trị của nó thắng các source thấp hơn. |
| P2 | Custom source ở cuối danh sách. | Giá trị chỉ dùng khi source cao hơn không cung cấp key. |
| P3 | Custom source chèn sau system environment. | Environment variable thắng custom source; custom source có thể thắng file cấu hình thấp hơn. |
| P4 | Hai source cùng key, tên khác nhau. | Source đứng trước thắng. |
| P5 | Hai source cùng tên được add. | Danh sách chỉ có một source với tên đó theo semantics của API. |
| P6 | Replace source cùng tên. | Source mới ở đúng vị trí cũ và giá trị mới có hiệu lực. |
| P7 | Remove source. | Resolver lấy giá trị từ source thấp hơn còn lại. |
| P8 | Child merge parent có source trùng tên. | Source child được giữ, source parent cùng tên bị loại khỏi child. |
| P9 | Source được thay sau khi bean singleton khởi tạo. | Environment có thể mới nhưng bean snapshot vẫn cũ. |
| P10 | Refresh configuration bean/refresh scope. | Bean chỉ thay đổi theo cơ chế rebinding/target invalidation tương ứng. |

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Custom property không có hiệu lực. | Source chưa được thêm, thêm quá muộn hoặc nằm dưới source khác. | Kiểm tra source list và giá trị Environment. |
| Giá trị luôn là custom dù đã đặt environment variable. | Custom source dùng addFirst và override nguồn môi trường. | Chuyển sang vị trí tương đối phù hợp như addAfter system environment nếu đó là chính sách mong muốn. |
| Một source xuất hiện nhiều lần sau refresh. | Tên source thay đổi mỗi lần hoặc code luôn thêm source mới. | Dùng tên ổn định và replace/update thay vì tạo tên ngẫu nhiên. |
| replace báo không tìm thấy source. | Source chưa được đăng ký hoặc tên truyền vào không khớp. | Kiểm tra contains(name), thêm lần đầu, replace các lần sau. |
| addBefore/addAfter thất bại. | Source tham chiếu không tồn tại trong Environment đó. | Kiểm tra tên source thực tế; không giả định mọi Environment có cùng source. |
| Một số key của parent biến mất ở child. | Source parent và child trùng tên nên source parent bị loại khi merge. | Đặt tên khác nhau hoặc hợp nhất dữ liệu có chủ đích. |
| Bean vẫn dùng giá trị cũ sau khi source được replace. | Bean đã snapshot giá trị; chưa rebinding/refresh. | Chọn @ConfigurationProperties rebind hoặc @RefreshScope phù hợp. |
| Khởi động chậm khi có custom source. | getProperty gọi backend từ xa đồng bộ hoặc lặp lại nhiều lần. | Dùng cache/snapshot, timeout và nạp sớm có kiểm soát. |
| Giá trị rỗng ghi đè fallback. | Source trả chuỗi rỗng thay vì null/không có key. | Xác định semantics cho blank value và validate đầu vào. |
| Actuator env làm lộ cấu hình. | Endpoint được expose rộng hoặc hiển thị property nhạy cảm. | Giới hạn endpoint, quyền truy cập và dữ liệu được quan sát. |

## 12. Nguyên tắc thiết kế cho production

1. **Tên source ổn định:** dùng hằng số có namespace theo chủ sở hữu và mục đích.
2. **Precedence có chủ đích:** ghi rõ source nào được phép override source nào.
3. **Không ghi đè hệ thống ngoài ý muốn:** tránh addFirst cho dữ liệu mặc định hoặc tenant policy nếu system property/environment phải có quyền cao hơn.
4. **Cập nhật source theo snapshot:** validate toàn bộ dữ liệu trước khi thay source.
5. **Không gọi mạng trong mỗi getProperty:** dùng cache, timeout, last-known-good và cơ chế refresh rõ ràng.
6. **Kiểm soát concurrency:** không mutate map nhiều key khi request đang đọc; cân nhắc immutable snapshot.
7. **Tách secret khỏi cấu hình thường:** dùng secret management, không log giá trị và không expose rộng qua Actuator.
8. **Kiểm tra khi nâng phiên bản:** tên và thứ tự các source mặc định có thể thay đổi giữa kiểu ứng dụng hoặc phiên bản framework.
9. **Kiểm thử collision:** test source trùng tên, key trùng và merge parent-child.
10. **Quan sát metadata:** ghi source name, thứ tự và revision không nhạy cảm khi cần điều tra.

## 13. Checklist hoàn thành

- [ ] Giải thích được PropertySource và Environment.
- [ ] Phân biệt source name với property key.
- [ ] Đặt tên source ổn định, duy nhất và có namespace.
- [ ] Hiểu source trùng tên được quản lý theo name, không cộng dồn thành hai entry độc lập.
- [ ] Dùng được addFirst/addLast và các thao tác addBefore/addAfter.
- [ ] Biết replace giữ vị trí source và xử lý trường hợp source chưa tồn tại.
- [ ] Biết remove source và quan sát giá trị fallback.
- [ ] Phân biệt null với chuỗi rỗng khi resolve property.
- [ ] Chọn được EnvironmentPostProcessor, ApplicationContextInitializer hoặc @PropertySource theo thời điểm cần cấu hình.
- [ ] Biết đăng ký EnvironmentPostProcessor theo cơ chế của Spring Boot version đang dùng.
- [ ] Cập nhật custom source bằng tên ổn định và snapshot đã validate.
- [ ] Phân biệt thay PropertySource với rebinding bean và refresh scope.
- [ ] Có test xác minh precedence, source-name collision và refresh.
- [ ] Có chính sách bảo vệ secret, Actuator và nguồn cấu hình từ xa.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Framework – PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): tên source, dữ liệu và semantics so sánh.
- [Spring Framework – MutablePropertySources](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html): thêm, thay thế, sắp xếp và gỡ source.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, thứ tự ưu tiên và Config Data.
- [Spring Boot – EnvironmentPostProcessor](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html): extension point tùy chỉnh Environment trong quá trình khởi động.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment changes, refresh scope và tích hợp cấu hình.

Tên API, thứ tự source mặc định và extension registration có thể khác theo phiên bản. Hãy kiểm tra đúng Spring Boot/Spring Cloud release train và xác minh danh sách PropertySource trong ứng dụng thật trước khi đưa một chính sách precedence vào production.
