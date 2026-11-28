# Phạm vi tùy chỉnh ConfigDataLocationResolver và ConfigDataLoader

Spring Boot Config Data cho phép ứng dụng nạp cấu hình từ nhiều nguồn thông qua thuộc tính `spring.config.import`. Ngoài các location có sẵn như file, classpath, config tree hoặc Spring Cloud Config Server, một thư viện có thể bổ sung scheme riêng bằng hai SPI `ConfigDataLocationResolver` và `ConfigDataLoader`.

Hai SPI có trách nhiệm khác nhau. Resolver nhận diện và phân tích chuỗi location, sau đó chuyển nó thành một hoặc nhiều resource có cấu trúc. Loader đọc từng resource, lấy dữ liệu từ nguồn tương ứng và trả về các `PropertySource` để Spring đưa vào Environment. Ranh giới này giúp mở rộng Config Data mà không phải tự viết lại toàn bộ quy trình khởi động Spring Boot.

Trong hệ thống Spring Cloud Configuration, cơ chế này hữu ích khi một ứng dụng cần nạp thêm dữ liệu từ một nguồn riêng, chẳng hạn file được mount, dịch vụ cấu hình nội bộ hoặc kho dữ liệu chuyên biệt. Cần xác định rõ phạm vi: Config Data resolver/loader chạy trong từng ứng dụng client; nếu mục tiêu là cung cấp cấu hình tập trung cho nhiều ứng dụng qua một endpoint thống nhất, phần mở rộng phía Config Server có thể phù hợp hơn.

## 1. Config Data SPI nằm ở giai đoạn nào?

Spring Boot xử lý Config Data rất sớm trong quá trình khởi động, trước khi ApplicationContext thông thường được tạo đầy đủ. Khi đọc `spring.config.import`, framework phân tích location, tìm resolver phù hợp, tạo resource và gọi loader để lấy PropertySource.

~~~mermaid
flowchart TD
    A[SpringApplication startup] --> B[Đọc spring.config.import]
    B --> C[ConfigDataLocationResolver]
    C --> D[ConfigDataResource]
    D --> E[ConfigDataLoader]
    E --> F[ConfigData + PropertySource]
    F --> G[Spring Environment]
    G --> H[ApplicationContext]
    H --> I[ConfigurationProperties / beans]
~~~

Resolver và loader tham gia vào bootstrap Config Data, vì vậy chúng không hoạt động như một service bean thông thường. Không nên dựa vào `@Autowired`, `@Value`, repository bean hoặc một `@Configuration` class của application context để thực hiện việc nạp dữ liệu. Các giá trị cần thiết để xác định nguồn phải được lấy từ location, từ bootstrap context phù hợp hoặc từ môi trường runtime có sẵn ở giai đoạn này.

## 2. Phân chia trách nhiệm giữa Resolver và Loader

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `ConfigDataLocationResolver` | Nhận diện scheme, phân tích location, xác định resource cần đọc | Nhận `acme:/etc/orders/orders.properties` |
| `ConfigDataResource` | Mô tả resource bất biến và trạng thái optional | Giữ đường dẫn file, URI hoặc định danh nguồn |
| `ConfigDataLoader` | Đọc resource, phân tích dữ liệu và tạo PropertySource | Đọc file properties hoặc gọi API cấu hình |
| `ConfigData` | Đóng gói các PropertySource loader đã tạo | Trả danh sách property source cho Spring |

Một resolver tốt chỉ làm nhiệm vụ định tuyến và mô tả resource. Nó không nên tải nội dung lớn hoặc tự xây dựng toàn bộ Environment. Loader mới là nơi thực hiện I/O và chuyển dữ liệu thành PropertySource.

Cách tách này có một lợi ích thực tế: cú pháp location có thể giữ ổn định trong khi cách đọc nguồn thay đổi. Ví dụ `acme:` ban đầu đọc file được mount, sau đó loader có thể được thay bằng adapter gọi dịch vụ nội bộ mà client vẫn dùng một cú pháp import nhất quán.

## 3. Khi nào nên mở rộng Config Data?

Một scheme riêng có thể phù hợp khi:

- Ứng dụng cần đọc một định dạng hoặc nguồn cấu hình mà Config Data hiện có chưa hỗ trợ.
- Nhiều ứng dụng dùng chung một thư viện client để đọc một hệ thống cấu hình nội bộ.
- Cần chuyển một location ngắn thành nhiều resource, ví dụ file chung và file theo profile.
- Cần kiểm soát cách parse, validate và đưa dữ liệu vào Spring Environment.
- Nguồn cấu hình có thể được truy cập an toàn trong giai đoạn bootstrap.

Nên cân nhắc cách tích hợp khác khi:

- Cần quản lý tập trung application/profile/label, phân quyền theo service, audit và rollout cấu hình cho nhiều client: Spring Cloud Config Server có sẵn mô hình server/client và có thể mở rộng backend.
- Nguồn là Vault và nhu cầu chủ yếu là secret lifecycle, lease hoặc dynamic credentials: ưu tiên integration Spring Cloud Vault phù hợp.
- Nguồn là file hoặc config tree thông thường: dùng location có sẵn của Spring Boot thay vì tạo scheme mới.
- Cần thay đổi cấu hình động sau startup: phải thiết kế cơ chế cập nhật Environment/bean riêng; Config Data SPI tự nó không phải cơ chế watch và refresh runtime.

Một extension chỉ nên sở hữu phần việc mà nó có thể thực hiện và kiểm thử rõ ràng. Không biến resolver thành một Config Server thứ hai với authentication, cache, versioning và event distribution tự phát nếu những năng lực đó đã thuộc hệ thống cấu hình trung tâm.

## 4. Cú pháp location và tiền tố riêng

Ví dụ một thư viện hỗ trợ scheme `acme:`:

~~~yaml
spring:
  config:
    import: "acme:/etc/orders/orders.properties"
~~~

Resolver nhận location và kiểm tra tiền tố. Nếu location thuộc scheme của mình, resolver lấy phần còn lại để tạo resource. Các resolver khác không nên nhận nhầm location này.

Có thể cho phép optional import:

~~~yaml
spring:
  config:
    import: "optional:acme:/etc/orders/extra.properties"
~~~

Tiền tố `optional:` do Config Data xử lý. Resolver cần giữ trạng thái optional trong resource để loader biết cách xử lý khi resource không tồn tại. Không nên tự xóa hoặc tự diễn giải optional theo một cú pháp riêng.

Nên định nghĩa cú pháp rõ ràng:

| Phần location | Ý nghĩa ví dụ |
| --- | --- |
| `acme:` | Scheme do thư viện đăng ký |
| `/etc/orders/orders.properties` | Định danh resource |
| `optional:` | Cho phép bỏ qua resource không tồn tại theo quy tắc Config Data |
| profile suffix | Resource riêng cho profile nếu backend hỗ trợ |

Tránh đặt password, access token hoặc secret trực tiếp trong location. Chuỗi location có thể xuất hiện trong log khởi động, exception, diagnostics hoặc metadata. Location nên chứa định danh nguồn; credential phải được cấp qua cơ chế secret phù hợp.

## 5. Tạo ConfigDataResource bất biến

Resource là đối tượng trung gian giữa resolver và loader. Nó nên chứa đủ thông tin để loader biết cần đọc gì, đồng thời giữ trạng thái optional.

Ví dụ:

~~~java
package com.example.configdata;

import org.springframework.boot.context.config.ConfigDataResource;

public final class AcmeConfigDataResource extends ConfigDataResource {

    private final String path;

    public AcmeConfigDataResource(String path, boolean optional) {
        super(optional);
        this.path = path;
    }

    public String getPath() {
        return this.path;
    }

    @Override
    public String toString() {
        return "AcmeConfigDataResource[path=" + this.path + "]";
    }
}
~~~

Trong ứng dụng thực tế, resource nên được thiết kế như value object:

- Các field là `final`, không thay đổi sau khi tạo.
- Constructor validate định dạng path/URI.
- `equals` và `hashCode` phản ánh định danh resource nếu framework hoặc extension cần nhận diện resource trùng.
- `toString` không chứa credential, token hoặc dữ liệu cấu hình.
- Optional được truyền từ `ConfigDataLocation` sang resource.

Không đặt nội dung secret vào resource. Resource có thể được giữ trong log hoặc exception; nó chỉ nên mô tả vị trí hay định danh nguồn.

## 6. Viết ConfigDataLocationResolver

Resolver nhận diện scheme và chuyển location thành resource. Ví dụ dưới đây hỗ trợ file properties với prefix `acme:`:

~~~java
package com.example.configdata;

import java.util.List;

import org.springframework.boot.context.config.ConfigDataLocation;
import org.springframework.boot.context.config.ConfigDataLocationResolver;
import org.springframework.boot.context.config.ConfigDataLocationResolverContext;
import org.springframework.boot.context.config.Profiles;
import org.springframework.core.Ordered;

public final class AcmeConfigDataLocationResolver
        implements ConfigDataLocationResolver<AcmeConfigDataResource>, Ordered {

    private static final String PREFIX = "acme:";

    @Override
    public boolean isResolvable(ConfigDataLocation location) {
        return location.hasPrefix(PREFIX);
    }

    @Override
    public List<AcmeConfigDataResource> resolve(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location) {

        String path = location.getNonPrefixedValue(PREFIX);
        if (path.isBlank()) {
            throw new IllegalArgumentException(
                    "acme: location phải có đường dẫn resource");
        }

        return List.of(
                new AcmeConfigDataResource(path, location.isOptional()));
    }

    @Override
    public List<AcmeConfigDataResource> resolveProfileSpecific(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location,
            Profiles profiles) {

        String basePath = location.getNonPrefixedValue(PREFIX);
        return profiles.getActive().stream()
                .map(profile -> new AcmeConfigDataResource(
                        addProfileSuffix(basePath, profile),
                        location.isOptional()))
                .toList();
    }

    private String addProfileSuffix(String path, String profile) {
        int extensionIndex = path.lastIndexOf('.');
        if (extensionIndex < path.lastIndexOf('/')) {
            return path + "-" + profile;
        }
        return path.substring(0, extensionIndex)
                + "-" + profile
                + path.substring(extensionIndex);
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Các đoạn mã trên minh họa API Config Data theo Spring Boot 3.x và Java 17 trở lên. Nếu thư viện còn hỗ trợ Spring Boot 2.4/Java cũ hơn, cần điều chỉnh các API Java như `List.of()` và `Stream.toList()` sang cách tương thích, đồng thời biên dịch kiểm tra với đúng phiên bản Boot mục tiêu.

Các điểm quan trọng:

- `isResolvable` phải chỉ nhận scheme mà extension sở hữu.
- `resolve` phân tích location và tạo resource nền.
- `resolveProfileSpecific` tạo resource theo profile khi nguồn có quy ước profile-specific.
- `location.isOptional()` được chuyển sang resource.
- `getOrder()` xác định thứ tự resolver khi có nhiều implementation cùng được đăng ký.

Đoạn profile suffix ở trên giả định file có tên như `orders.properties`, `orders-prod.properties`. Nếu backend dùng URL, path hierarchy hoặc profile separator khác, hãy định nghĩa quy ước tương ứng. Không ghép profile tùy tiện vào URI đã mã hóa hoặc vào path có query string.

Nếu nguồn không có dữ liệu riêng theo profile, resolver có thể không tạo thêm resource profile-specific. Nếu có, phải xác định rõ thứ tự các profile và precedence giữa file chung với file theo profile; kiểm thử với nhiều profile đang hoạt động.

## 7. Resolver order và tránh nhận nhầm location

Một ứng dụng có thể cài nhiều thư viện Config Data. Framework cần chọn resolver phù hợp cho từng location. Nếu resolver quá rộng, chẳng hạn nhận mọi chuỗi không phải URL chuẩn, nó có thể xung đột với resolver của thư viện khác.

Các nguyên tắc:

- Dùng scheme riêng, ngắn và có namespace rõ.
- `isResolvable` kiểm tra chính xác prefix.
- Chỉ dùng `Ordered` hoặc `@Order` khi có lý do về thứ tự xử lý.
- Không dùng thứ tự để chiếm location của resolver khác.
- Nếu nhiều resolver có thể nhận một location, thiết kế prefix để chỉ một resolver nhận.
- Test khi extension được dùng cùng các import location mặc định và extension khác.

Order của resolver quyết định cách framework tìm implementation xử lý location. Nó không phải thứ tự ưu tiên của các giá trị property trong Environment. Hai khái niệm này không được dùng thay thế cho nhau.

## 8. Viết ConfigDataLoader

Loader nhận resource, đọc nội dung và tạo PropertySource. Ví dụ dưới đây đọc file Java properties:

~~~java
package com.example.configdata;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

import org.springframework.boot.context.config.ConfigData;
import org.springframework.boot.context.config.ConfigDataLoader;
import org.springframework.boot.context.config.ConfigDataLoaderContext;
import org.springframework.core.env.MapPropertySource;

public final class AcmeConfigDataLoader
        implements ConfigDataLoader<AcmeConfigDataResource> {

    @Override
    public ConfigData load(
            ConfigDataLoaderContext context,
            AcmeConfigDataResource resource) throws IOException {

        Path path = Path.of(resource.getPath());

        Properties properties = new Properties();
        try (Reader reader = Files.newBufferedReader(
                path, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }
        catch (NoSuchFileException ex) {
            if (resource.isOptional()) {
                return new ConfigData(List.of());
            }
            throw ex;
        }

        Map<String, Object> values = new LinkedHashMap<>();
        properties.forEach((key, value) ->
                values.put(String.valueOf(key), value));

        MapPropertySource propertySource = new MapPropertySource(
                "acme:" + resource.getPath(), values);

        return new ConfigData(List.of(propertySource));
    }
}
~~~

Ví dụ này minh họa loader cho file local. Trong môi trường production, phải kiểm soát thư mục được phép đọc, symlink, file permission và quyền của user chạy ứng dụng. Không cho phép một location tùy ý đọc mọi file trên máy chủ.

Loader có thể dùng `ConfigDataLoaderContext` để truy cập bootstrap context hoặc resource loader phù hợp. Không lấy dependency từ ApplicationContext thông thường vì context đó chưa được khởi tạo ở giai đoạn Config Data.

Nếu loader đọc HTTP API hoặc kho cấu hình từ xa, cần bổ sung timeout, TLS verification, authentication, retry có giới hạn và xử lý response code. Không retry vô hạn trong startup; điều đó có thể khiến ứng dụng treo lâu và che khuất lỗi cấu hình.

## 9. Optional và xử lý resource không tồn tại

Optional import hữu ích khi resource chỉ bổ sung cấu hình và ứng dụng có fallback an toàn. Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:acme:/etc/orders/extra.properties"
~~~

Loader phải phân biệt resource không tồn tại với lỗi nội dung hoặc lỗi bảo mật:

| Tình huống | Xử lý phù hợp |
| --- | --- |
| File optional không tồn tại | Trả về không có PropertySource hoặc dùng cơ chế not-found phù hợp của Config Data |
| File bắt buộc không tồn tại | Làm startup thất bại với thông báo resource rõ ràng |
| File tồn tại nhưng sai định dạng | Báo lỗi parse; không âm thầm bỏ qua |
| Không đủ quyền đọc | Báo lỗi permission; không giả vờ resource không tồn tại |
| Server trả 401/403 | Báo lỗi xác thực/phân quyền; không coi là optional missing |
| Timeout hoặc lỗi mạng | Áp dụng retry giới hạn và fail theo chính sách |

Ví dụ loader ở trên trả ConfigData rỗng khi resource optional không tồn tại và để `NoSuchFileException` thoát ra nếu resource bắt buộc không tồn tại. Với backend phức tạp hơn, có thể dùng exception not-found chuyên biệt của Config Data để giữ ngữ nghĩa optional thống nhất. Không bắt mọi exception rồi trả danh sách rỗng; cách đó biến lỗi bảo mật, parse hoặc network thành cấu hình mặc định khó phát hiện.

## 10. Đăng ký Resolver và Loader

Resolver và loader phải được đăng ký để Spring Boot tìm thấy. Với Config Data SPI, dùng file `META-INF/spring.factories` trong JAR chứa extension:

~~~properties
org.springframework.boot.context.config.ConfigDataLocationResolver=\
com.example.configdata.AcmeConfigDataLocationResolver

org.springframework.boot.context.config.ConfigDataLoader=\
com.example.configdata.AcmeConfigDataLoader
~~~

Đảm bảo file nằm đúng đường dẫn:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Giá trị bên phải là tên đầy đủ của class implementation. Nếu đăng ký sai package, sai key hoặc resource file không được đóng gói vào JAR, Spring Boot sẽ không tìm thấy extension và location `acme:` không được xử lý.

Một thư viện có thể đăng ký nhiều implementation bằng danh sách class phân tách theo dòng theo định dạng Spring factories. Khi đóng gói fat JAR hoặc shaded JAR, kiểm tra công cụ build có hợp nhất các file `spring.factories` từ dependency hay không; không để file của một thư viện ghi đè file của thư viện khác.

## 11. Dùng extension trong ứng dụng

Sau khi thư viện chứa resolver/loader nằm trên classpath, ứng dụng khai báo:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import:
      - "acme:/etc/orders/orders.properties"
~~~

Với ví dụ resolver phía trên, các resource được tìm gồm:

~~~text
/etc/orders/orders.properties
/etc/orders/orders-prod.properties
~~~

Loader tạo PropertySource từ từng file. Các giá trị được đưa vào Spring Environment và có thể bind vào bean:

~~~java
@ConfigurationProperties(prefix = "orders.http")
public record OrdersHttpProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
~~~

Ứng dụng có thể tiếp tục dùng các cơ chế Spring thông thường như `@ConfigurationProperties`, `@Value` hoặc `Environment`. Extension chịu trách nhiệm nạp PropertySource; nó không cần tự tạo bean nghiệp vụ.

## 12. Profile và thứ tự ưu tiên

Config Data hỗ trợ import gắn với cấu hình chung và cấu hình profile-specific. Resolver có thể sử dụng `resolveProfileSpecific` để tạo resource tương ứng với các profile được chấp nhận trong giai đoạn xử lý Config Data.

Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active:
      - prod
      - observability
  config:
    import: "acme:/etc/orders/orders.properties"
~~~

Theo quy ước suffix của ví dụ, resolver có thể tạo:

~~~text
orders.properties
orders-prod.properties
orders-observability.properties
~~~

Cần kiểm tra thứ tự ưu tiên giữa các profile theo đúng quy tắc Config Data và thứ tự active profile của ứng dụng. Không giả định file được nạp sau luôn thắng trong mọi tình huống nếu còn nhiều import, profile group hoặc document activation. Viết integration test cho các key trùng nhau để chứng minh giá trị cuối cùng.

Trong một hệ thống dùng Spring Cloud Config Server, Config Server thường xử lý application/profile/label ở phía server. Custom Config Data source có thể bổ sung nguồn riêng, nhưng phải có quy ước rõ để tránh xung đột với remote property source. Ghi lại origin và tên PropertySource để khi chẩn đoán có thể xác định giá trị thắng đến từ đâu.

## 13. Thứ tự ưu tiên giữa nhiều import

Khi một document khai báo nhiều location trong `spring.config.import`, thứ tự import và vị trí của document ảnh hưởng tới precedence. Theo quy tắc Config Data, dữ liệu được import có thể ghi đè giá trị trong document khai báo import; khi có nhiều import, thứ tự được xử lý theo quy tắc import của Spring Boot.

Ví dụ:

~~~yaml
spring:
  config:
    import:
      - "acme:/etc/orders/shared.properties"
      - "acme:/etc/orders/overrides.properties"
~~~

Nếu hai resource cùng định nghĩa `orders.http.read-timeout`, cần xác nhận thứ tự thực tế bằng integration test với phiên bản Spring Boot mục tiêu. Không dùng resolver order để điều khiển property precedence: resolver order chỉ chọn implementation xử lý location, còn precedence thuộc Config Data/Environment.

Để giảm xung đột, nên phân chia ownership của key. Ví dụ file shared chứa timeout mặc định, file profile chứa giá trị theo môi trường và một import override chỉ dành cho ngoại lệ được phê duyệt.

## 14. Phạm vi profile-specific import và vòng lặp cấu hình

Resolver cần hoạt động tốt khi location xuất hiện trong document chung hoặc document được kích hoạt theo profile. Một số lưu ý:

- Không giả định active profile đã có đầy đủ ngay ở lần resolve đầu tiên.
- Dùng `resolveProfileSpecific` cho phần cần tạo resource theo profile.
- Tránh trả lại cùng resource vô hạn trong mỗi vòng profile resolution.
- Không dùng dữ liệu từ resource vừa tải để âm thầm thay đổi cú pháp location của những lần resolve tiếp theo.
- Không kích hoạt profile mới tùy tiện chỉ bằng cách nạp property source nếu điều đó làm luồng Config Data khó dự đoán.
- Kiểm tra profile group, `spring.config.activate.on-profile` và nhiều profile cùng hoạt động.

Resolver nên có kết quả xác định: cùng location và cùng tập profile sẽ tạo cùng danh sách resource. Tính xác định giúp khởi động có thể tái lập và giảm lỗi khó chẩn đoán.

## 15. Bootstrap context và truy cập dependency ở giai đoạn sớm

Resolver và loader chạy trước ApplicationContext chính. Khi cần tạo client để truy cập một backend, dùng API được cung cấp qua resolver/loader context hoặc bootstrap context theo phiên bản Spring Boot.

Một số nguyên tắc:

- Không inject service bean từ application context chưa tồn tại.
- Không dựa vào `@ConfigurationProperties` bean thông thường để khởi tạo chính nguồn Config Data của nó.
- Không gọi `SpringApplication.run()` lồng bên trong loader.
- Không tạo connection pool hoặc thread pool không có lifecycle rõ ràng.
- Tái sử dụng dependency đã đăng ký trong bootstrap context khi framework hỗ trợ.
- Đóng tài nguyên đúng cách nếu extension tự tạo client hoặc stream.
- Giữ resolver nhẹ; để I/O chính trong loader.

Nếu cần cấu hình cho chính client truy cập backend, dùng bootstrap property độc lập, biến môi trường, system property hoặc workload identity. Không tạo vòng phụ thuộc kiểu “cần đọc config source để lấy password dùng đọc chính config source đó”.

## 16. Bảo mật location và loader

Một custom loader có thể mở rộng đáng kể bề mặt truy cập của ứng dụng. Nếu location nhận path hoặc URI do người dùng điều khiển, nó có thể trở thành đường đọc file tùy ý hoặc gọi endpoint không mong muốn.

Các biện pháp cần áp dụng:

- Giới hạn scheme và định dạng location được phép.
- Với file, giới hạn trong một root directory được cấu hình; chuẩn hóa path và kiểm tra path sau khi resolve symlink.
- Với HTTP, dùng allowlist host, TLS verification và chặn địa chỉ nội bộ không được phép.
- Không đặt token/password trong location string.
- Lấy credential từ secret manager hoặc workload identity.
- Giới hạn timeout, response size và số lần retry.
- Không log response body hoặc property value nhạy cảm.
- Dùng tên PropertySource không chứa secret.
- Giữ quyền đọc nguồn cấu hình theo nguyên tắc tối thiểu.

Nếu loader trả secret vào Environment, giá trị vẫn có thể xuất hiện trong heap, bean, diagnostic endpoint hoặc request gửi tới downstream. Loader không làm cho secret tự động an toàn; phải bảo vệ cả Config Server/Client, Actuator, log và đường truyền.

## 17. Refresh sau startup: giới hạn quan trọng

Config Data SPI chủ yếu phục vụ giai đoạn khởi động. Khi ứng dụng đã chạy, thay đổi file hoặc backend không tự động khiến `ConfigDataLoader` được gọi lại. `POST /actuator/refresh` của Spring Cloud Context cũng không phải cam kết rerun toàn bộ Config Data resolver/loader cho mọi scheme tùy chỉnh.

Nếu cần cập nhật động, phải chọn và triển khai một cơ chế riêng:

1. Dùng Spring Cloud Config Client và refresh flow đã được hỗ trợ nếu nguồn phù hợp được phục vụ qua Config Server.
2. Tích hợp watcher/polling cho nguồn riêng, cập nhật Environment theo API được hỗ trợ và phát sự kiện thay đổi.
3. Dùng một service quản lý snapshot cấu hình bất biến, công bố snapshot mới và cho bean tiêu thụ thay thế theo ranh giới an toàn.
4. Rolling restart ứng dụng khi cấu hình chỉ được thiết kế để nạp lúc startup.

Khi cập nhật Environment thủ công, phải xác định cách thay PropertySource, precedence, validation, event và bean lifecycle. Không chỉ sửa một MapPropertySource đang được nhiều thread đọc mà không có cơ chế đồng bộ. Với key liên quan, nên tạo snapshot đầy đủ rồi thay thế nguyên tử.

Nếu nguồn là Git và cần phân phối đến nhiều ứng dụng, webhook/Bus của Spring Cloud Config có thể quản lý refresh ở tầng client. Custom Config Data loader không tự tham gia Spring Cloud Bus chỉ vì nó trả PropertySource.

## 18. Kiểm thử Resolver độc lập

Resolver nên được kiểm thử không cần khởi động toàn bộ ứng dụng:

| Test | Kết quả mong đợi |
| --- | --- |
| Location bắt đầu bằng `acme:` | `isResolvable` trả true |
| Location bắt đầu bằng `file:` hoặc `configserver:` | Resolver trả false |
| Location thiếu path | Bị từ chối với lỗi dễ hiểu |
| Location có `optional:` | Resource giữ optional=true |
| Location bắt buộc | Resource giữ optional=false |
| Profile `prod` | Tạo đúng resource suffix `-prod` |
| Nhiều profile | Tạo resource theo quy ước và thứ tự đã định nghĩa |
| Nhiều resolver cùng classpath | Chỉ resolver sở hữu scheme nhận location |

Kiểm tra cả path có extension, path không extension, profile chứa ký tự hợp lệ và URI có query nếu cú pháp cho phép. Không dùng string concatenation đơn giản nếu backend có quy tắc encode riêng.

## 19. Kiểm thử Loader và Config Data integration

Loader cần các test độc lập:

- File hợp lệ tạo đúng key/value.
- File rỗng trả PropertySource rỗng hoặc kết quả được định nghĩa rõ.
- File optional không tồn tại không làm startup thất bại.
- File bắt buộc không tồn tại tạo lỗi có ngữ cảnh.
- File sai encoding hoặc sai định dạng báo lỗi.
- Permission denied không bị biến thành optional missing.
- Backend timeout và HTTP 401/403 được phân biệt.
- Nội dung secret không xuất hiện trong exception hoặc log.

Integration test nên chạy một `SpringApplication` nhỏ với import `acme:` thật và xác nhận:

1. Resolver/loader được phát hiện qua `spring.factories`.
2. PropertySource xuất hiện trong Environment.
3. `@ConfigurationProperties` bind đúng.
4. Profile-specific resource được nạp.
5. Import optional và required có hành vi khác nhau.
6. Precedence giữa nhiều import đúng với quy tắc dự án.
7. Config Data từ extension tương tác đúng với environment variable và command line.
8. Lỗi nạp cấu hình làm startup thất bại theo chính sách đã chọn.

Test integration cần dùng file tạm trong thư mục test được kiểm soát; không đọc file hệ thống tùy ý. Không để test phụ thuộc vào một Vault, Git server hoặc broker production.

## 20. Tương thích phiên bản và đóng gói

Config Data SPI được giới thiệu trong mô hình Config Data của Spring Boot 2.4. Các package và hợp đồng API cần được đối chiếu với phiên bản Spring Boot mà thư viện hỗ trợ.

- Dùng Spring Boot BOM hoặc dependency management tương thích với Spring Cloud release train.
- Không đóng gói một phiên bản Spring Boot khác vào thư viện extension để ép ứng dụng tiêu thụ.
- Kiểm tra API của `ConfigDataLocationResolver`, `ConfigDataLoader`, `ConfigDataResource` trên từng major/minor được hỗ trợ.
- Kiểm tra `spring.factories` được giữ khi build fat JAR hoặc shaded JAR.
- Test trên Java version và Spring Boot version thực tế của ứng dụng.
- Nếu hỗ trợ nhiều major Boot, cân nhắc module build riêng thay vì reflection để né khác biệt API.

Một extension hoạt động ở môi trường IDE nhưng không hoạt động trong executable JAR thường liên quan đến đăng ký factory, resource packaging hoặc classpath. Kiểm tra nội dung JAR để xác nhận file `META-INF/spring.factories` và class implementation thực sự được đóng gói.

## 21. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy resolver cho `acme:` | Thiếu entry trong `spring.factories` hoặc sai class name | Kiểm tra JAR và key factory |
| Resolver không nhận location | Prefix sai hoặc `isResolvable` kiểm tra quá rộng/hẹp | Test trực tiếp location |
| Loader không được gọi | Resolver không trả resource hoặc resource type không khớp generic | Kiểm tra resolve result và loader registration |
| Startup báo resource không tồn tại | Path sai hoặc file chưa mount | Kiểm tra location, mount và optional flag |
| Optional import vẫn làm startup lỗi | Loader biến lỗi khác thành not-found hoặc không xử lý optional đúng | Phân biệt missing, permission, parse và network |
| Giá trị không xuất hiện trong Environment | Loader không tạo PropertySource hoặc map key sai | Kiểm tra ConfigData và MapPropertySource |
| Giá trị bị nguồn khác ghi đè | Precedence giữa import và property source khác | Xem origin trong Actuator env |
| Profile không nạp file riêng | Không implement profile-specific resolution hoặc suffix sai | Kiểm tra Profiles và resource path |
| Refresh không đọc lại nguồn | Config Data loader chỉ chạy trong startup pipeline | Dùng cơ chế refresh riêng hoặc restart |
| Extension chạy ở IDE nhưng lỗi trong JAR | Factory metadata không được đóng gói/hợp nhất | Kiểm tra META-INF/spring.factories |
| Nạp cấu hình làm lộ secret | Log location, response hoặc Environment | Sanitize log và bảo vệ Actuator |

Khi chẩn đoán, đi theo thứ tự: import string → resolver matching → resource creation → loader invocation → PropertySource creation → Environment precedence → bean binding. Nếu Environment đã có giá trị đúng nhưng bean sai, chuyển sang kiểm tra bean lifecycle thay vì sửa resolver.

## 22. Quy trình triển khai extension có kiểm soát

Một quy trình phù hợp cho thư viện dùng trong nhiều ứng dụng:

1. Xác định nguồn dữ liệu và lý do cần scheme riêng.
2. Định nghĩa grammar của location, optional semantics và profile behavior.
3. Tạo resource bất biến, không chứa secret.
4. Viết resolver chỉ parse location và tạo resource.
5. Viết loader thực hiện I/O, validate và tạo PropertySource.
6. Đăng ký hai SPI trong `META-INF/spring.factories`.
7. Thêm thư viện vào một ứng dụng test nhỏ.
8. Kiểm thử profile, precedence, optional, lỗi nguồn và security.
9. Xác nhận refresh/runtime behavior hoặc xác định restart policy.
10. Kiểm tra executable JAR và tương thích Spring Boot/Spring Cloud.
11. Triển khai canary cho một ứng dụng.
12. Mở rộng sang các client khác sau khi quan sát ổn định.

Khi scheme được dùng bởi nhiều service, version hóa thư viện extension và ghi lại nguồn cấu hình, profile, release ID cùng phiên bản loader. Nếu thay đổi grammar hoặc precedence, xem đó là thay đổi hợp đồng cấu hình và phát hành theo quy trình có review.

## 23. Nguyên tắc thiết kế

- Dùng Resolver để nhận diện và mô tả resource; dùng Loader để đọc dữ liệu và tạo PropertySource.
- Giữ location grammar ổn định, cụ thể và không chứa credential.
- Làm cho resource bất biến, có optional flag và định danh an toàn.
- Resolver phải xác định, nhanh và không thực hiện I/O nặng.
- Loader phải giới hạn I/O, timeout, retry và kích thước dữ liệu.
- Hỗ trợ profile-specific resource chỉ khi nguồn có quy ước profile rõ.
- Phân biệt resolver order với property source precedence.
- Đăng ký SPI đúng trong `META-INF/spring.factories`.
- Không dựa vào application bean ở giai đoạn Config Data bootstrap.
- Không giả định refresh endpoint tự gọi lại custom loader.
- Bảo vệ secret, file path, remote endpoint và Actuator.
- Kiểm thử cả startup, profile, precedence, lỗi nguồn và runtime lifecycle.
- Nếu cần phân phối cấu hình tập trung cho nhiều client, xác định rõ ranh giới giữa client-side Config Data extension và server-side Config Server backend.

`ConfigDataLocationResolver` và `ConfigDataLoader` mở rộng điểm nạp cấu hình của Spring Boot theo một hợp đồng rõ ràng: resolver biến location thành resource, loader biến resource thành PropertySource. Phân chia trách nhiệm, xử lý profile và optional đúng cách, đăng ký SPI chính xác và kiểm thử precedence giúp extension dễ tái sử dụng trong nhiều ứng dụng. Quan trọng nhất, cần xác định đây là cơ chế nạp ở startup; refresh động, phân phối qua Bus và vòng đời bean phải được thiết kế riêng để hệ thống cấu hình tập trung vận hành nhất quán.

## Tài liệu tham khảo

- [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot API – ConfigDataLocationResolver](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
- [Spring Boot API – ConfigDataLoader](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
- [Spring Cloud Config Reference](https://docs.spring.io/spring-cloud-config/reference/)

