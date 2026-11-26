# Đăng ký PropertySource theo chương trình

## 1. Mục tiêu và bài toán

Trong ứng dụng Java dùng **Spring Vault**, một số thông tin cấu hình được lưu trong HashiCorp Vault thay vì đưa vào `application.yml` hoặc đóng gói cùng mã nguồn. Ví dụ dịch vụ `payment-api` cần `payment.gateway-url` và `payment.api-key` để gọi cổng thanh toán. Spring có cơ chế `Environment` và `PropertySource`: khi ứng dụng hỏi một thuộc tính, Spring sẽ tìm trong các nguồn cấu hình đã đăng ký theo thứ tự ưu tiên.

**Đăng ký `PropertySource` theo chương trình** nghĩa là chủ động tạo nguồn cấu hình từ Vault, rồi đưa nó vào `ConfigurableEnvironment.getPropertySources()` bằng mã Java. Cách làm này hữu ích khi muốn:

- Chọn một hoặc nhiều Vault path theo môi trường triển khai.
- Đặt **thứ tự ưu tiên** chính xác giữa Vault, biến môi trường, system properties và tệp cấu hình.
- Khởi tạo nguồn Vault **trước khi** những bean phụ thuộc `@Value` hay `@ConfigurationProperties` được tạo.
- Tách việc lấy bí mật thông qua `VaultTemplate` khỏi việc sử dụng chúng qua `Environment`.

Bài thuộc chương **Nguồn cấu hình** trong module **SPRING_VAULT**: ứng dụng Java truy cập Vault bằng workload authentication và policy tối thiểu; những kiến thức liên quan còn gồm KV secrets, vòng đời token/lease, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp.

Sau khi học, bạn sẽ có thể tạo một `VaultPropertySource`, đặt nó đúng vị trí trong `MutablePropertySources`, giải thích quy tắc ghi đè, kiểm thử lúc khởi động và tránh nhầm lẫn giữa **nạp cấu hình ban đầu** và **làm mới secret khi ứng dụng đang chạy**.

## 2. Vai trò của từng thành phần

| Thành phần | Chức năng |
| --- | --- |
| **Vault KV secrets engine** | Lưu và trả về cặp key/value theo đường dẫn được cấp quyền |
| `VaultTemplate` / `VaultOperations` | Gửi request đến Vault bằng Vault token của workload |
| `VaultPropertySource` | Đọc secret từ Vault và biểu diễn các key thành Spring properties |
| `ConfigurableEnvironment` | Giao diện truy cập và quản lý các nguồn thuộc tính |
| `MutablePropertySources` | Tập nguồn có thứ tự: thêm trước/sau, thay thế hoặc xóa |
| `@Value` / `@ConfigurationProperties` | Tiêu thụ giá trị đã được Environment phân giải |
| **Spring Cloud Vault** | Một lựa chọn tích hợp cao hơn, tự cấu hình các nguồn Vault khi bootstrap |

Đây là hai ý khác nhau:

1. `VaultTemplate.read(...)` hoặc `opsForKeyValue(...)` là **đọc một secret qua API**, trả `VaultResponse` cho mã nghiệp vụ xử lý.
2. `VaultPropertySource` dùng `VaultOperations` để **đưa thuộc tính vào Environment**. Bean có thể dùng property placeholder mà không cần gọi `VaultTemplate` mỗi khi đọc thuộc tính.

`VaultPropertySource` thông thường **nạp dữ liệu ngay lúc được tạo**. Vì thế, tạo object và đặt vào Environment không phải là thao tác thuần bộ nhớ: nó có thể phát sinh request đến Vault, chịu ảnh hưởng của network, TLS, token và ACL.

## 3. Dữ liệu trong Vault và tên property trong Spring

Giả sử có KV v2 mount `secret/`, key logic `apps/payment-api`. Operator chuẩn bị **giá trị giả** trên Vault dev/test:

~~~bash
vault kv put -mount=secret apps/payment-api \
  payment.gateway-url="https://gateway.sandbox.example.test" \
  payment.api-key="LAB_FAKE_KEY_ONLY" \
  payment.timeout-seconds="5"
~~~

Spring Vault sử dụng Vault path kiểu:

~~~text
secret/apps/payment-api
~~~

**Đừng tự chèn `data/` vào path truyền cho `VaultPropertySource` khi làm việc với KV v2.** Spring Vault xác định KV mount và xử lý đường dẫn nội bộ phù hợp. Trong khi đó, Vault ACL cho hoạt động **đọc dữ liệu KV v2** thường vẫn phải chỉ đến API path có `data/`:

~~~hcl
path "secret/data/apps/payment-api" {
  capabilities = ["read"]
}
~~~

Điểm dễ nhầm:

| Ngữ cảnh | Đường dẫn |
| --- | --- |
| KV CLI | `vault kv get -mount=secret apps/payment-api` |
| Spring `VaultPropertySource` | `secret/apps/payment-api` |
| Vault HTTP API của KV v2 | `/v1/secret/data/apps/payment-api` |
| Vault ACL đọc dữ liệu | `secret/data/apps/payment-api` |

Spring Vault có thể truy vấn endpoint nội bộ `sys/internal/ui/mounts/...` để xác định loại mount; nếu không truy xuất được thông tin mount trong môi trường được cấu hình, việc tạo `VaultPropertySource` có thể thất bại dù secret có tồn tại. Hãy kiểm tra auth token, các khả năng truy xuất cần thiết và cách triển khai phiên bản Vault đang dùng, **không** sửa bằng cách cấp root token cho workload.

Những key trong ví dụ (`payment.gateway-url`, `payment.api-key`) sẽ xuất hiện như thuộc tính trong Environment. `VaultPropertySource` cũng có thể làm phẳng object lồng nhau, nhưng để tránh phụ thuộc cách parse JSON/YAML giữa các hệ thống, bài lab dùng **tên property phẳng** ngay từ đầu.

## 4. Đăng ký thủ công trong GenericApplicationContext

Đây là ví dụ ngắn nhất để thấy thứ tự ưu tiên. Giả sử `vaultTemplate` đã được tạo đúng với endpoint, TLS và authentication:

~~~java
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.env.VaultPropertySource;

public final class PropertySourceExample {

    public static void register(
            GenericApplicationContext context,
            VaultTemplate vaultTemplate) {

        MutablePropertySources sources =
                context.getEnvironment().getPropertySources();

        VaultPropertySource vaultSource = new VaultPropertySource(
                "vault:payment-api",
                vaultTemplate,
                "secret/apps/payment-api"
        );

        sources.addFirst(vaultSource);
    }
}
~~~

**Gọi `register(context, vaultTemplate)` trước `context.refresh()`** nếu cấu hình Vault cần tham gia vào quá trình khởi tạo các bean. Khi đã đăng ký, ứng dụng có thể gọi:

~~~java
String gatewayUrl = context.getEnvironment()
        .getProperty("payment.gateway-url");
~~~

Không in `payment.api-key` ra console hoặc trả qua HTTP endpoint để “kiểm tra” việc đăng ký.

`sources.addFirst(...)` đặt nguồn Vault ở vị trí đầu trong chuỗi tìm kiếm **hiện tại**. Nếu cùng khóa có mặt trong nhiều nguồn, nguồn có độ ưu tiên cao hơn trả kết quả trước. Cách sử dụng `addFirst` là lựa chọn **có chủ đích**, không mặc định là chính sách phù hợp với mọi hệ thống.

**Mục tiêu của đăng ký theo chương trình** không chỉ là thêm nguồn mới, mà còn bảo đảm việc lấy secret đúng thời điểm và đặt nó ở thứ tự mong muốn.

## 5. Spring Boot: đăng ký sớm bằng ApplicationContextInitializer

Trong Spring Boot, một `@Bean` hoặc `ApplicationRunner` thêm property source **sau khi các bean khác đã được khởi tạo** có thể quá muộn: constructor `@Value` hoặc `@ConfigurationProperties` có thể đã được bind bằng giá trị khác hoặc thất bại vì thiếu thuộc tính.

Một cách minh họa rõ thứ tự là dùng `ApplicationContextInitializer<ConfigurableApplicationContext>`, chạy trong giai đoạn chuẩn bị context **trước `refresh()`**.

### 5.1. Lớp initializer

~~~java
import java.net.URI;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.env.VaultPropertySource;

public final class VaultConfigSourceInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    private static final String NAME = "vault:payment-api";

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String vaultUrl = requiredEnvironment("VAULT_ADDR");
        String token = requiredEnvironment("VAULT_APP_TOKEN");

        VaultTemplate template = new VaultTemplate(
                VaultEndpoint.from(URI.create(vaultUrl)),
                new TokenAuthentication(token)
        );

        // Constructor thực hiện đọc secret từ Vault.
        VaultPropertySource source = new VaultPropertySource(
                NAME,
                template,
                "secret/apps/payment-api"
        );

        MutablePropertySources sources =
                context.getEnvironment().getPropertySources();

        if (sources.contains(NAME)) {
            throw new IllegalStateException(
                    "Vault property source already registered: " + NAME);
        }

        // Giữ độ ưu tiên thường có của CLI/system props và OS env.
        String envSource =
                StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME;

        if (sources.contains(envSource)) {
            sources.addAfter(envSource, source);
        } else {
            // Fallback minh họa nếu một môi trường tùy biến
            // không có nguồn systemEnvironment.
            sources.addFirst(source);
        }
    }

    private static String requiredEnvironment(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(key + " is required");
        }
        return value;
    }
}
~~~

Mẫu dùng `TokenAuthentication` với `VAULT_APP_TOKEN` **chỉ để giảm thành phần trong phòng lab**; đây không phải thiết kế production cho service chạy dài. Token của workload phải được bảo vệ, cấp quyền tối thiểu, có vòng đời phù hợp. Ở Kubernetes/cloud, thay bằng `ClientAuthentication` tương ứng và chiến lược session/token renewal được kiểm chứng. Dùng **HTTPS với CA đáng tin cậy** thay cho HTTP khi không còn ở dev server cô lập.

Lời gọi `VaultPropertySource(...)` diễn ra trước khi thêm nguồn vào Spring, nên **lỗi kết nối Vault, token hết hạn, thiếu policy hoặc secret bắt buộc không tồn tại** có thể khiến ứng dụng không khởi động. Đối với secret bắt buộc, *fail fast* là lựa chọn hợp lý hơn tự hạ cấp sang credential tĩnh kém an toàn. Nếu bí mật là tùy chọn, phải định nghĩa rõ hành vi và cấu hình cách xử lý thiếu secret, không âm thầm bỏ qua mọi lỗi `403` hoặc TLS.

### 5.2. Đăng ký initializer trước khi chạy ứng dụng

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PaymentApiApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PaymentApiApplication.class);

        app.addInitializers(new VaultConfigSourceInitializer());
        app.run(args);
    }
}
~~~

Sau đó bean có thể đọc thuộc tính được nạp từ Vault:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class PaymentGatewaySettings {

    private final String gatewayUrl;

    public PaymentGatewaySettings(
            @Value("${payment.gateway-url}") String gatewayUrl) {
        this.gatewayUrl = gatewayUrl;
    }

    public String gatewayUrl() {
        return gatewayUrl;
    }
}
~~~

Tương tự, các key có thể được bind qua `@ConfigurationProperties(prefix = "payment")` khi tên property và kiểu Java phù hợp. Chỉ trả các giá trị **không nhạy cảm** ra API; không đưa `payment.api-key` vào `toString()`, log cấu hình hoặc endpoint chẩn đoán.

### 5.3. Vì sao không dùng ApplicationRunner để đăng ký?

`ApplicationRunner.run(...)` thực thi khi `ApplicationContext` đã refresh xong. Nếu một bean trong constructor có `@Value` cần `payment.api-key`, thêm `VaultPropertySource` lúc đó **không làm constructor tự chạy lại**. Ngay cả khi `Environment.getProperty(...)` sau đó nhìn thấy giá trị mới, bean đã được khởi tạo vẫn giữ giá trị được tiêm ban đầu.

Tương tự, không nên tạo `VaultPropertySource` bằng một `@Bean` rồi giả định Spring sẽ tự đăng ký nó vào `Environment` ở đúng thời điểm: **tạo bean và thêm vào MutablePropertySources là hai việc khác nhau**. Ngoài ra, thứ tự tạo bean, ràng buộc vòng phụ thuộc vào `VaultTemplate` và các property cần tải từ Vault có thể gây vấn đề bootstrap.

`ApplicationContextInitializer` là cách đăng ký *sớm so với quá trình tạo bean*, nhưng **không đủ sớm để quyết định mọi tham số bootstrap của chính Spring Boot**. Các khóa dùng để tìm `spring.config.import`, `spring.config.location`, hoặc thiết lập environment rất sớm phải đến từ nguồn bootstrap tương ứng. Khi cần tích hợp trọn vẹn Spring Boot Config Data API, cân nhắc **Spring Cloud Vault** thay vì tự viết initializer.

## 6. Vị trí trong MutablePropertySources quyết định giá trị thắng

Ví dụ `payment.timeout-seconds` có mặt trong Vault, `application.yml` và biến môi trường. Khi tra cứu, Spring chọn nguồn có property được ưu tiên **cao nhất** trong chuỗi tại thời điểm đó.

Các phương thức cần nhớ:

| Method | Ý nghĩa |
| --- | --- |
| `sources.addFirst(source)` | Đặt nguồn lên đầu: có thể ghi đè cả CLI và biến môi trường |
| `sources.addLast(source)` | Đặt nguồn cuối: chỉ dùng làm fallback khi nguồn khác thiếu thuộc tính |
| `sources.addBefore("x", source)` | Nguồn mới được ưu tiên hơn nguồn `x` |
| `sources.addAfter("x", source)` | Nguồn mới kém ưu tiên hơn nguồn `x` |
| `sources.replace("x", source)` | Thay nguồn có tên `x` mà giữ vị trí của nó |
| `sources.remove("x")` | Xóa nguồn theo tên; thận trọng với nguồn của framework |
| `sources.contains("x")` | Kiểm tra nguồn đã được đăng ký trước khi thêm |

Đừng nhầm `addFirst` với “giá trị mới nhất”: nó điều khiển **ưu tiên tên nguồn**, không quyết định Vault secret đang là version nào. Nếu Env chỉ có `payment.api-key` từ Vault, còn `payment.timeout-seconds` được CLI ghi đè, hai thuộc tính có thể đến từ **hai nguồn khác nhau**.

Chính sách thường hữu ích: để các thông số bootstrap/override khẩn cấp ở environment hoặc CLI có thể ghi đè, trong khi Vault ưu tiên hơn config file đã đóng gói. Đó là lý do initializer ở trên dùng `addAfter("systemEnvironment", ...)` khi nguồn này hiện diện. Nhưng **thứ tự cụ thể phụ thuộc Environment thực tế và phiên bản Spring Boot**; không mặc định mọi Spring Boot project có cùng chuỗi tên nguồn.

Muốn kiểm tra thứ tự mà không làm lộ giá trị:

~~~java
MutablePropertySources sources = context.getEnvironment()
        .getPropertySources();

sources.forEach(source ->
        System.out.println("propertySource.name=" + source.getName()));
~~~

Lệnh chỉ in **tên nguồn**, không gọi `getPropertyNames()` hoặc in nội dung. Trong production, giới hạn log dạng này và không in Vault path nếu path tiết lộ thông tin nhạy cảm về hạ tầng.

**Kiểm soát tiền tố key** là cách khác tránh va chạm: dùng `payment.*` cho dịch vụ thanh toán, `billing.*` cho billing, không ghi `password` hoặc `url` chung chung.

## 7. Đăng ký nhiều Vault path và kiểm soát va chạm

Một ứng dụng thực tế có thể cần hai nhóm cấu hình: bí mật chung cho service và bí mật riêng theo môi trường. Đăng ký hai nguồn **có tên riêng biệt** cho phép kiểm soát rõ cái nào thắng khi một key xuất hiện ở cả hai:

~~~java
VaultPropertySource serviceSecrets = new VaultPropertySource(
        "vault:payment-service",
        vaultTemplate,
        "secret/apps/payment-api");

VaultPropertySource sharedSecrets = new VaultPropertySource(
        "vault:payment-common",
        vaultTemplate,
        "secret/shared/payment");

// Nguồn service được tra cứu trước nguồn shared.
MutablePropertySources sources =
        context.getEnvironment().getPropertySources();

sources.addFirst(serviceSecrets);
sources.addAfter("vault:payment-service", sharedSecrets);
~~~

Với cách này, `payment.timeout-seconds` của path riêng được ưu tiên so với path chung nếu cả hai đều có. Tuy nhiên vì `addFirst` đặt nguồn lên đầu, hai nguồn Vault cũng có thể ghi đè OS env hoặc CLI. **Muốn áp dụng chính sách khác, thay đổi vị trí khi đăng ký** thay vì sửa trực tiếp dữ liệu Vault cho trùng với thứ tự mong muốn.

Không khuyến khích xây path Vault bằng dữ liệu do người dùng HTTP gửi lên. Các đường dẫn nguồn cấu hình phải được kiểm soát bởi cấu hình triển khai hoặc danh tính workload; nếu nhận path tùy ý, ứng dụng có thể vô tình mở quyền đọc secret ở nhiều tenant. Không dùng wildcard policy trên `secret/data/*` chỉ để chạy thử nhiều path.

### Trường hợp thiếu key

Một `PropertySource` không chứa key được hỏi sẽ nhường cho các nguồn tiếp theo. Điều này **khác** với trường hợp **toàn bộ Vault secret path không tồn tại**, có thể khiến khởi tạo nguồn thất bại tùy constructor/cấu hình `ignoreSecretNotFound`.

Với cấu hình bắt buộc như `payment.api-key`, nên:

1. Xác minh path đúng và workload có quyền đọc.
2. Fail fast nếu nguồn không thể được đọc.
3. Fail fast nếu key không tồn tại hoặc rỗng trong `Environment`.
4. Không tự lấy một mật khẩu mặc định từ `application.yml` khi chưa có đánh giá bảo mật.

Spring Vault có constructor `VaultPropertySource` cho phép truyền `PropertyTransformer` và `ignoreSecretNotFound` để thiết kế hành vi tùy chọn. Chỉ bật bỏ qua secret không tìm thấy cho dữ liệu **thật sự tùy chọn**; không coi việc bỏ qua là giải pháp cho lỗi Vault 403/TLS.

### Flattening và định dạng giá trị

Vault có thể trả `Map<String,Object>` với cấu trúc lồng nhau. `VaultPropertySource` có khả năng làm phẳng tên thuộc tính (ví dụ `payment.timeout-seconds`). Đừng suy ra mọi kiểu `Object` sẽ được chuyển đúng thành giá trị Java theo ý định nếu secret chứa JSON phức tạp: hãy kiểm thử với `Environment.getProperty(...)` và `@ConfigurationProperties` của phiên bản đang dùng.

Nếu cần đổi tên, thêm tiền tố hoặc biến đổi cặp thuộc tính, Spring Vault cung cấp `PropertyTransformer` và các constructor tương ứng. Đây là bước xử lý dữ liệu lúc tạo nguồn; không phải cơ chế sửa quyền của Vault hoặc gia hạn lease.

## 8. Nạp một lần và cập nhật trong thời gian chạy là hai bài toán

`VaultPropertySource` thường nạp giá trị **tại thời điểm khởi tạo đối tượng**. Nếu KV v2 được operator cập nhật sang version mới sau đó, không nên kết luận một `VaultPropertySource` đã tạo từ trước sẽ tự đi lấy version mới mỗi lần bean gọi `getProperty()`.

Nếu chỉ cần làm mới **đầu vào của Environment** có thể chủ động tạo một source mới rồi thay thế:

~~~java
public static void reloadEnvironmentSource(
        ConfigurableEnvironment env,
        VaultTemplate vaultTemplate) {

    String name = "vault:payment-api";

    // Đọc và xác minh secret mới trước khi thay nguồn đang dùng.
    VaultPropertySource fresh = new VaultPropertySource(
            name,
            vaultTemplate,
            "secret/apps/payment-api"
    );

    MutablePropertySources sources = env.getPropertySources();
    if (!sources.contains(name)) {
        throw new IllegalStateException("Source not registered: " + name);
    }
    sources.replace(name, fresh);
}
~~~

Đây **không phải** giải pháp rotation đầy đủ:

- `Environment.getProperty("payment.gateway-url")` thực hiện **sau** khi thay nguồn có thể thấy giá trị mới, nếu không bị một nguồn ưu tiên cao hơn ghi đè.
- Field `@Value` đã được tiêm vào **bean tồn tại trước đó** thường không tự cập nhật.
- Một `@ConfigurationProperties` đã được bind thường không tự bind lại chỉ vì `MutablePropertySources.replace(...)`.
- Connection pool hoặc HTTP client đã được khởi tạo bằng credential cũ **không tự tái tạo** hoặc thay credential.
- Nếu Vault không kết nối được trong lúc tạo `fresh`, nguồn cũ vẫn tồn tại; ứng dụng cần phân loại tình trạng stale, TTL và readiness, không cứ tiếp tục dùng credential cũ vô hạn.

Đối với **dynamic secrets có lease**, Spring Vault có `SecretLeaseContainer` và `LeaseAwareVaultPropertySource`: các secret có thể được renew hoặc rotate theo `RequestedSecret`, và nội dung nguồn có thể được cập nhật bởi các thread chạy nền. Tuy nhiên cập nhật `PropertySource` vẫn **khác việc áp dụng credential vào consumer** đã khởi tạo. Việc chuyển JDBC pool, TLS client hoặc resource khác cần lifecycle/consumer tương ứng.

### So sánh cách tích hợp

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Cấu hình KV tĩnh khi khởi động, muốn đặt thứ tự cụ thể | `VaultPropertySource` + `MutablePropertySources` |
| Cấu hình chủ yếu từ Vault theo quy ước Spring Boot/Config Data | Spring Cloud Vault |
| Nhiều nguồn với ưu tiên tùy chỉnh, control thời điểm nạp | Đăng ký theo chương trình trước refresh |
| Dynamic database credentials cần renew/rotate | `SecretLeaseContainer`, `LeaseAwareVaultPropertySource` hoặc consumer rotation phù hợp |
| Dùng một secret để gọi API nghiệp vụ theo yêu cầu | `VaultTemplate` / `VaultOperations` trực tiếp |
| Đọc KV version mới và tác động lên bean đang chạy | Nạp mới + chiến lược rebinding/cập nhật consumer được thiết kế riêng |

Không nên vừa bật tự động đăng ký cùng KV path trong Spring Cloud Vault vừa thêm một `VaultPropertySource` thủ công ở vị trí khác **mà không kiểm soát trùng tên/key**. Kết quả có thể là nguồn bị che khuất, khó chẩn đoán thứ tự và tạo thêm request tới Vault.

## 9. Bảo mật, workload authentication và khả năng khởi động

Tầng property source không tự giải quyết xác thực. `VaultTemplate` vẫn phải có **Vault token đại diện workload**; Vault kiểm tra ACL trên API path khi `VaultPropertySource` được tạo.

Đối với ứng dụng production:

- Chọn Kubernetes/AppRole/cloud auth theo môi trường, giới hạn Vault role và policy đúng path/capability; không dùng root token.
- Truyền **địa chỉ Vault, phương thức đăng nhập, CA/truststore và thông tin bootstrap cần thiết** qua nguồn khởi động đáng tin cậy. Tránh vòng phụ thuộc “muốn tạo Vault client phải đọc property vốn đang ở Vault”.
- Chỉ dùng TLS đáng tin cậy. Không dùng tùy chọn bỏ kiểm tra CA/hostname.
- Giới hạn Vault secrets trong `Environment` ở phạm vi cần thiết. Nhiều thư viện đọc được Environment; không coi đây là kho bí mật cách ly tuyệt đối.
- Hạn chế công khai Spring Boot Actuator `/actuator/env`, `/actuator/configprops` và endpoint chẩn đoán. Không phụ thuộc hoàn toàn vào cơ chế masking mặc định.
- Không in `getPropertyNames()`, toàn bộ `Environment`, `VaultResponse` hoặc giá trị api-key vào log; một property key đôi khi cũng tiết lộ kiến trúc.
- Quản lý token TTL, renewal và secret lease độc lập. Tính đúng thứ tự property source không bảo đảm token còn hợp lệ khi reload.

**Ranh giới trách nhiệm:** property source cung cấp giá trị cho hệ thống cấu hình Spring; nó không thay Spring Security, không phân quyền người dùng cuối và không biến biến cấu hình thành API đọc secret công khai.

## 10. Kiểm thử ưu tiên và bảo đảm không rò rỉ dữ liệu

Kiểm thử nên tách hai lớp: **thứ tự của Spring Environment** và **đọc secret thật từ Vault**.

### 10.1. Kiểm tra quy tắc thứ tự bằng source giả

Không cần chạy Vault để kiểm tra việc chọn nguồn trước/sau:

~~~java
import java.util.Map;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

public class PropertySourceOrderCheck {

    public static void main(String[] args) {
        ConfigurableEnvironment env = new MockEnvironment();

        env.getPropertySources().addFirst(new MapPropertySource(
                "lab-vault",
                Map.of("payment.timeout-seconds", "5")
        ));

        env.getPropertySources().addFirst(new MapPropertySource(
                "lab-commandline",
                Map.of("payment.timeout-seconds", "2")
        ));

        String result = env.getProperty("payment.timeout-seconds");
        if (!"2".equals(result)) {
            throw new AssertionError("Wrong property precedence");
        }

        // Đổi thứ tự, Vault sẽ thắng.
        env.getPropertySources().remove("lab-vault");
        env.getPropertySources().addFirst(new MapPropertySource(
                "lab-vault",
                Map.of("payment.timeout-seconds", "5")
        ));

        if (!"5".equals(env.getProperty("payment.timeout-seconds"))) {
            throw new AssertionError("Priority change not reflected");
        }

        System.out.println("PASS property-source precedence");
    }
}
~~~

`MockEnvironment` thuộc dependency **spring-test**; ví dụ có thể chạy trong test source của ứng dụng. Kết quả kỳ vọng:

~~~text
PASS property-source precedence
~~~

Test trên chỉ kiểm tra quy tắc `MutablePropertySources`, **không chứng minh đã đọc được Vault**.

### 10.2. Kiểm thử tích hợp với Vault dev/test

Cần chạy Vault sandbox, tạo đúng KV v2 và token chỉ đọc; gọi Spring Boot initializer trước khi bean được tạo. Quan sát:

1. Trước khi gọi `context.refresh()`, Environment đã chứa nguồn tên `vault:payment-api`.
2. `payment.gateway-url` được đọc với giá trị test đúng (kiểm tra equality, không in secret).
3. CLI/OS env có giá trị trùng key sẽ thắng khi nguồn Vault đứng sau `systemEnvironment`.
4. Xóa quyền `read` trên KV v2: việc tạo `VaultPropertySource` phải thất bại theo phản hồi Vault, không tự rơi về root token.
5. Đổi tên Vault path sang không tồn tại: ứng dụng xử lý fail-fast hoặc optional đúng hợp đồng.
6. Thay KV version sau khi app đã khởi động: bean đã bind không được mặc định coi là đổi ngay; nếu reload, kiểm tra phân biệt `Environment` và consumer.
7. Không có log/token/secret trong stdout, HTTP response, heap dump thử nghiệm hoặc endpoint Actuator mở công khai.

**Một bài kiểm thử tốt phải quan sát cả tác động:** property có đúng giá trị mà người dùng được phép dùng, source precedence đúng chính sách, và lỗi Vault không biến thành việc phục vụ credential cũ một cách không kiểm soát.

## 11. Bài thực hành từng bước trong Vault dev server

Đây là phòng lab dùng secret giả và token ngắn hạn. Không chạy trên Vault production, không commit secret thật, không tái sử dụng root token trong ứng dụng Java.

### Bước 1 — Khởi tạo Vault và dữ liệu KV v2

Ở terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Ở terminal thứ hai, dùng token quản trị **chỉ trong bước chuẩn bị**:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

vault status
vault secrets list -detailed
~~~

Vault dev mode thông thường có `secret/` là KV v2. Nếu mount không tồn tại, tạo nó bằng `vault secrets enable -path=secret -version=2 kv`; nếu đã tồn tại, **không tạo chồng lên** mà xác nhận version. Ghi dữ liệu:

~~~bash
vault kv put -mount=secret apps/payment-api \
  payment.gateway-url="https://gateway.sandbox.example.test" \
  payment.api-key="LAB_FAKE_KEY_ONLY" \
  payment.timeout-seconds="5"
~~~

### Bước 2 — Policy và token của workload giả lập

~~~bash
vault policy write payment-config-read - <<'HCL'
path "secret/data/apps/payment-api" {
  capabilities = ["read"]
}
HCL

APP_TOKEN="$(vault token create \
  -policy=payment-config-read \
  -ttl=15m \
  -field=token)"
~~~

Đối với Spring Vault PropertySource, có thể phát sinh request xác định mount từ `sys/internal/ui/mounts/...`. Nếu môi trường không cho Vault đọc metadata mount bằng token ứng dụng, cần xem xét cách Vault xác định loại KV, các capability bổ sung đúng yêu cầu và cấu hình auth; **không cấp rộng trên `sys/*` một cách tùy tiện**.

### Bước 3 — Khởi động Java với token ứng dụng, không dùng root

Cấu hình môi trường của tiến trình Java (IDE hoặc terminal khác) như sau:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_APP_TOKEN="$APP_TOKEN"

# Ví dụ dự án đã biên dịch:
# java -jar target/payment-api.jar
~~~

Đây là biến môi trường demo. Khi đưa lên production, chọn auth method workload phù hợp và secret delivery/rotation an toàn thay vì giữ một token tĩnh lâu dài. Nếu Java chạy ở shell khác, phải truyền token qua kênh thử nghiệm an toàn; không copy token vào mã nguồn, screenshot hoặc log.

Đặt `VaultConfigSourceInitializer` trước `SpringApplication.run`. Trong `PaymentGatewaySettings`, giá trị `gatewayUrl()` dự kiến bằng URL sandbox. Để kiểm tra `payment.api-key`, chỉ xác nhận property **có giá trị** qua test được ủy quyền; không in nó ra console hoặc response.

### Bước 4 — Kiểm tra precedence

Chạy ứng dụng với đối số giả định:

~~~bash
# Ví dụ, khi app đã có lớp main và executable JAR:
# java -jar target/payment-api.jar \
#   --payment.gateway-url=https://override.sandbox.example.test
~~~

Với cách `addAfter("systemEnvironment",...)` trong initializer và khi `commandLineArgs` vẫn ở vị trí ưu tiên thường thấy trong Spring Boot, URL từ command-line được phép ghi đè giá trị trong Vault. Nếu thay `addAfter` bằng `addFirst`, Vault có thể thắng giá trị từ CLI. **Kiểm tra chuỗi source thực tế**, đừng suy ra chỉ từ chú thích trong mã.

### Bước 5 — Thử trường hợp bị từ chối

Dùng token không được cấp policy để xác minh Vault thật sự kiểm soát truy cập:

~~~bash
DENIED_TOKEN="$(vault token create \
  -policy=default \
  -ttl=5m \
  -field=token)"

curl -sS -o /dev/null -w "status=%{http_code}\n" \
  -H "X-Vault-Token: $DENIED_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/apps/payment-api"
~~~

Kỳ vọng thường là **HTTP 403** khi token `default` không có quyền đọc path đó. Ở phía Java, đặt token bị từ chối vào `VAULT_APP_TOKEN` và khởi động lại sẽ dẫn tới lỗi nạp source: phân biệt lỗi thiếu policy với secret không tồn tại. Không tắt xác minh Vault TLS, không bỏ kiểm tra lỗi rồi chạy ứng dụng bằng credential dự phòng có quyền cao hơn.

### Bước 6 — Dọn phòng lab

~~~bash
vault token revoke "$APP_TOKEN"
vault token revoke "$DENIED_TOKEN"

vault kv metadata delete -mount=secret apps/payment-api
vault policy delete payment-config-read
~~~

`vault kv metadata delete` xóa toàn bộ phiên bản secret ở đúng key. Chỉ chạy trên sandbox sau khi đã đối chiếu mount/path; nếu một token đã hết hạn thì thao tác revoke có thể báo đối tượng không còn.

## 12. Chẩn đoán những lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Cách xác minh |
| --- | --- | --- |
| `@Value` không phân giải được property | Source đăng ký quá muộn, path sai hoặc key thiếu | Xem lifecycle initializer, tên nguồn, tên key; không in value |
| `Environment` thấy giá trị nhưng bean không đổi | Bean đã được tạo/bind trước khi thay source | Cấu hình nguồn trước refresh hoặc có cơ chế rebinding riêng |
| Vault 403 khi tạo `VaultPropertySource` | Token workload thiếu capability, token hết hạn hoặc mount path | Kiểm tra token policy, KV v2 `data/`, mount discovery |
| Vault 404 / secret not found | Sai mount, key, Vault namespace hoặc secret không được tạo | Kiểm tra path logic và KV version |
| Giá trị vẫn là giá trị trong OS env | Nguồn OS env được ưu tiên cao hơn | Kiểm tra `MutablePropertySources` theo tên/thứ tự |
| Value sai kiểu khi bind | `@ConfigurationProperties` không chuyển được dữ liệu | Kiểm tra kiểu dữ liệu, ký pháp key và validator |
| Một secret đọc được ở CLI root nhưng Java thất bại | CLI đang dùng root token, Java dùng token riêng | So sánh capability bằng token workload và nguồn authentication |
| Ứng dụng không boot khi Vault mất kết nối | Constructor nguồn đọc Vault sớm | Chọn chiến lược availability/fail-fast phù hợp, metric và retry ở mức có kiểm soát |
| KV đã được cập nhật nhưng bean dùng giá trị cũ | PropertySource chưa reload hoặc bean không rebind | Thiết kế reload + cập nhật consumer có kiểm tra |
| Có hai nguồn Vault cùng key nhưng khó dự đoán | Trùng path hoặc thứ tự đăng ký không rõ | Đặt tên riêng và quyết định precedence tường minh |

**Lưu ý về Spring Cloud Vault:** nếu đã cấu hình `spring.config.import=vault://` và nó tự tải properties cho ứng dụng, không nhất thiết phải đăng ký `VaultPropertySource` bằng Java. Chọn cách tích hợp phù hợp, tránh đọc cùng path nhiều lần và tạo chu kỳ phụ thuộc giữa việc lấy credential Vault với chính property source cần credential đó.

## 13. Câu hỏi ôn tập và tiêu chí hoàn thành

1. Vì sao việc tạo `VaultPropertySource` có thể phát sinh request mạng ngay trước `context.refresh()`?
2. Nếu cùng key xuất hiện trong Vault và biến môi trường, `addFirst` khác `addAfter("systemEnvironment", ...)` thế nào?
3. Đường dẫn nào đúng khi gọi `new VaultPropertySource(...)` cho KV v2 key `apps/payment-api` ở mount `secret`? Đường dẫn ACL đọc có gì khác?
4. Vì sao đăng ký bằng `ApplicationRunner` không phù hợp nếu một bean cần `@Value` ngay khi khởi tạo?
5. Nếu `sources.replace(...)` đổi secret đang lưu, connection pool cũ có tự nhận password mới không?
6. Cách nào giúp phân biệt lỗi thiếu policy với lỗi Vault path không tồn tại?
7. Khi nào nên dùng `SecretLeaseContainer` hoặc Spring Cloud Vault thay vì tự quản lý `VaultPropertySource`?

**Gợi ý trả lời:** (1) nguồn nạp secret trong constructor; (2) thay đổi quyền ưu tiên; (3) Spring dùng `secret/apps/payment-api`, Vault ACL KV v2 dùng `secret/data/apps/payment-api`; (4) quá muộn cho bean đã bind; (5) không; (6) kiểm tra mã lỗi, Vault token và capability/path; (7) khi cần lifecycle secret hoặc tích hợp cấu hình rộng hơn.

**Tiêu chí hoàn thành:** thực hiện được một lần đăng ký programmatic **trước bean initialization**, xác minh một property đọc đúng, kiểm tra hai thứ tự ưu tiên, kiểm chứng token bị từ chối, tách biệt nguồn cấu hình và cập nhật consumer khi dữ liệu thay đổi, đồng thời không lộ token/secret trong log.

### Tài liệu tham khảo

- [Spring Vault — Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html)
- [Spring Vault — VaultPropertySource API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/env/VaultPropertySource.html)
- [Spring Vault — LeaseAwareVaultPropertySource API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/env/LeaseAwareVaultPropertySource.html)
- [Spring Vault — VaultOperations](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Framework — MutablePropertySources](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
- [Spring Framework — ApplicationContextInitializer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Vault — Configuration Integration](https://docs.spring.io/spring-cloud-vault/reference/)

**Kết luận:** Đăng ký `VaultPropertySource` theo chương trình cho phép ứng dụng **chọn thời điểm và thứ tự** đưa cấu hình Vault vào Spring `Environment`. Đây là cơ chế cấu hình lúc khởi tạo; khả năng reload, gia hạn token/lease và cập nhật thành phần sử dụng secret đang chạy là **trách nhiệm riêng**, cần được thiết kế và kiểm thử độc lập.
