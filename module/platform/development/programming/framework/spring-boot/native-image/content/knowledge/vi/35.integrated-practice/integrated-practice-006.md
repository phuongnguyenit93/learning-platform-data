# Thay đổi profile và property để quan sát ranh giới build với runtime

## 1. Vì sao profile và property cần được kiểm tra khi dùng Spring AOT?

Spring Boot thường dùng profile và property để thay đổi cấu hình theo môi trường: bật/tắt integration, chọn endpoint, điều chỉnh timeout, chọn datasource hoặc đăng ký bean theo điều kiện. Trên JVM, Spring có thể tạo ApplicationContext khi process khởi động và đánh giá các điều kiện dựa trên cấu hình runtime.

Với Spring AOT và GraalVM Native Image, ApplicationContext được phân tích trước khi executable được tạo. Những quyết định ảnh hưởng đến cấu trúc context — chẳng hạn bean nào tồn tại, auto-configuration nào được bật, component nào được scan — có thể đã được cố định trong generated AOT code. Vì vậy, thay profile sau khi build không phải lúc nào cũng tương đương thay profile khi chạy JAR trên JVM.

Ngược lại, nhiều property chỉ cung cấp giá trị cho bean đã được tạo, như URL, timeout, pool size hoặc feature threshold. Các giá trị này thường có thể thay đổi khi chạy native nếu cấu hình và thư viện hỗ trợ binding runtime.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài thực hành này giúp phân biệt hai nhóm property, chạy thử nghiệm có kiểm soát và quan sát khác biệt giữa build-time AOT inputs với runtime configuration. Mục tiêu là biết property nào phải cố định khi AOT chạy và property nào có thể thay đổi mà không cần build lại executable.

## 2. Hai nhóm property cần phân biệt

| Nhóm | Tác động | Ví dụ |
|---|---|---|
| Structural/build-time | Thay đổi bean graph hoặc metadata được AOT phân tích | Profile bật cấu hình JPA hay MongoDB; property điều khiển `@ConditionalOnProperty`; component scan/auto-configuration |
| Runtime/value | Thay giá trị được bean đã tạo sử dụng | API URL, timeout, log level, pool size, retry delay |
| Mixed/depends-on-usage | Có thể là structural hoặc value tùy cách code dùng | Feature flag, locale, serializer mode, cache enabled |

Tên property không tự quyết định nhóm. Một property tên `feature.enabled` nếu chỉ được đọc trong method runtime có thể là value property. Nếu nó được dùng trong `@ConditionalOnProperty` để quyết định bean có được tạo hay không, nó là structural input đối với AOT.

Cần đọc cách property được sử dụng trong code, configuration class và auto-configuration thay vì chỉ nhìn tên trong YAML.

## 3. Spring AOT phân tích ApplicationContext ở thời điểm build

Trong quá trình AOT, Spring chuẩn bị ApplicationContext dựa trên:
- Application main configuration.
- Classpath và dependency versions.
- Active profiles được cung cấp cho AOT process.
- Property sources được AOT process nhìn thấy.
- Conditions và auto-configuration.
- Component scanning và imports.
- Bean definitions và runtime hints contributions.

Generated code phản ánh cấu trúc context đã phân tích. Khi native executable chạy, Spring vẫn đọc cấu hình runtime và bind property cho bean phù hợp, nhưng không thể tùy ý tạo một bean graph hoàn toàn khác nếu AOT output không chuẩn bị cho cấu trúc đó.

Đây là lý do cần phân biệt profile được kích hoạt khi AOT với profile được đặt lúc chạy. Cách hỗ trợ nhiều profile/variant phụ thuộc Spring Boot version và workflow AOT; xác minh theo tài liệu của version dự án.

## 4. Profile dùng để chọn cấu hình theo môi trường

Ví dụ cấu hình:

```yaml
spring:
  profiles:
    active: native-prod
```

Có thể dùng file riêng:

```text
application.yml
application-native-prod.yml
application-test.yml
```

Một profile có thể bật bean/configuration:

```java
@Configuration
@Profile("native-prod")
class NativeProductionConfiguration {
    // Beans thuộc cấu hình native production
}
```

Nếu profile quyết định bean nào được tạo, nó ảnh hưởng đến context structure. Khi AOT phân tích với profile `native-prod`, generated output được tạo theo cấu hình đó. Đổi sang profile có bean graph khác lúc runtime có thể không hoạt động như kỳ vọng.

Profile không tự động là build-time trong mọi trường hợp. Nếu profile chỉ thay giá trị của một bean đã tồn tại và cấu trúc context không đổi, nó có thể được xử lý như runtime configuration. Hãy kiểm tra điều kiện và bean graph thực tế.

## 5. @Profile và @ConditionalOnProperty tạo structural decisions

Ví dụ:

```java
@Configuration
@Profile("payments")
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
```

Hoặc:

```java
@Configuration
@ConditionalOnProperty(
        prefix = "search",
        name = "enabled",
        havingValue = "true")
class SearchConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
```

Trong cả hai trường hợp, property/profile quyết định bean definition có được đăng ký không. Đây là structural decision mà AOT cần biết.

Nếu AOT chạy với `search.enabled=false`, nhưng runtime được khởi chạy với `search.enabled=true`, không nên kỳ vọng bean `SearchService` sẽ xuất hiện nếu generated context không chứa cấu hình đó. Runtime property không thể tự sinh lại mọi bean definition đã bị loại trong AOT.

## 6. Property chỉ điều chỉnh giá trị runtime

Ví dụ một client đã được đăng ký nhưng endpoint thay đổi theo môi trường:

```java
@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout) {
}
```

Cấu hình:

```yaml
inventory:
  base-url: https://inventory.example.internal
  connect-timeout: 2s
  read-timeout: 5s
```

Nếu bean client luôn được tạo và các giá trị chỉ được bind vào bean đã tồn tại, thay URL hoặc timeout lúc runtime thường không làm thay đổi cấu trúc ApplicationContext.

Ví dụ environment override:

```bash
INVENTORY_BASE_URL=https://inventory.staging.internal
INVENTORY_CONNECT_TIMEOUT=3s
```

Tên biến môi trường cần tuân theo relaxed binding của Spring Boot. Cần xác minh bean/client đọc property ở runtime và không có condition dùng cùng property để quyết định bean registration.

## 7. Mixed property: feature flag có thể thuộc cả hai nhóm

Một feature flag có thể được sử dụng theo hai cách khác nhau.

**Cách A — Structural:**

```java
@Bean
@ConditionalOnProperty(
        name = "invoice.pdf.enabled",
        havingValue = "true")
PdfInvoiceRenderer pdfInvoiceRenderer() {
    return new PdfInvoiceRenderer();
}
```

Giá trị quyết định bean có tồn tại. Cần cố định giá trị khi AOT chạy hoặc chuẩn bị các cấu hình build variant được hỗ trợ.

**Cách B — Runtime behavior:**

```java
@Service
class InvoiceService {

    private final InvoiceProperties properties;

    InvoiceService(InvoiceProperties properties) {
        this.properties = properties;
    }

    byte[] render(Invoice invoice) {
        if (properties.pdfEnabled()) {
            return renderPdf(invoice);
        }
        return renderHtml(invoice);
    }
}
```

Bean luôn tồn tại; property chỉ điều khiển nhánh xử lý. Giá trị có thể thay lúc runtime nếu cả hai nhánh code đã nằm trong executable và dependencies/resources cần thiết đã được đưa vào.

Cùng một property có thể được dùng ở cả hai nơi. Khi đó nó có tác động structural và phải được đánh giá theo tác động structural.

## 8. Runtime profile không phải cơ chế thêm code mới vào native executable

Giả sử ứng dụng có hai cấu hình:

- `application-jpa.yml` bật Spring Data JPA.
- `application-mongo.yml` bật Spring Data MongoDB.

Nếu native executable được AOT build với JPA context, đặt `SPRING_PROFILES_ACTIVE=mongo` lúc chạy không tự đưa Mongo repository beans và driver classes vào executable. Các class có thể không reachable, metadata có thể chưa được tạo và context generated có thể không chứa Mongo configuration.

Muốn hỗ trợ nhiều cấu trúc, cần một chiến lược được framework/version hỗ trợ, ví dụ:
- Tạo các build variant riêng theo profile.
- Thiết kế một context có các bean cần thiết luôn tồn tại và chỉ thay value runtime.
- Tách cấu hình/ứng dụng thành executable riêng.
- Dùng cơ chế AOT/native support chính thức nếu version cung cấp khả năng tương ứng.

Không xem việc đổi environment variable profile là thay thế cho build variant.

## 9. Xác định property nào được AOT process nhìn thấy

Một lỗi thường gặp là đặt environment variable trong terminal nhưng build plugin chạy AOT trong process khác hoặc daemon đã khởi động trước đó.

Cần xác minh:
- Biến môi trường có mặt trong process Maven/Gradle không.
- Profile được truyền tới đúng AOT task/goal.
- Property source nào có precedence cao hơn.
- Test profile có vô tình override production profile không.
- Gradle daemon có giữ environment cũ không.
- Build cache có tái sử dụng output AOT từ cấu hình khác không.

Đặt property trong shell không đảm bảo plugin nhận đúng nếu lifecycle/task có cách fork process riêng. Đọc build log và task configuration để xác nhận.

## 10. Thí nghiệm: thay structural property trước và sau AOT

Tạo configuration:

```java
@Configuration
@ConditionalOnProperty(
        prefix = "feature",
        name = "search",
        havingValue = "true")
class SearchFeatureConfiguration {

    @Bean
    SearchFeature searchFeature() {
        return new SearchFeature();
    }
}
```

Thực hiện hai biến thể:

**Build A:** AOT chạy với `feature.search=false`.

**Build B:** AOT chạy với `feature.search=true`.

Sau đó chạy từng executable với hai runtime values:
- `feature.search=false`
- `feature.search=true`

Quan sát bean có tồn tại không và behavior của endpoint. Kết quả dự kiến: mỗi executable phản ánh structural configuration được phân tích khi AOT chạy. Runtime override không thể bảo đảm tạo bean đã bị loại khỏi generated context.

Ghi lại:
- AOT profile/property inputs.
- Generated output/build ID.
- Runtime profile/property.
- Bean presence.
- Endpoint behavior.
- Native build và test result.

Đừng dùng cùng output directory/cache giữa Build A và Build B nếu có nguy cơ trộn generated outputs.

## 11. Thí nghiệm: thay value property tại runtime

Tạo một bean luôn tồn tại:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration timeout) {
}
```

Build native với context chứa bean này. Sau đó chạy cùng executable hai lần với endpoint khác nhau:

```bash
SHIPPING_BASE_URL=https://shipping-a.example.internal \
SHIPPING_TIMEOUT=2s ./orders-service
```

```bash
SHIPPING_BASE_URL=https://shipping-b.example.internal \
SHIPPING_TIMEOUT=5s ./orders-service
```

Nếu application chỉ bind value cho bean đã tồn tại, cùng một binary có thể dùng các giá trị runtime khác nhau. Dùng mock server hoặc sandbox để xác nhận request thực sự đi tới endpoint được cấu hình.

Không dùng endpoint/credential production trong thí nghiệm. Ghi image/binary digest để chứng minh hai lần chạy dùng cùng executable.

## 12. Profile dành cho test và profile dành cho native production

Test thường dùng profile như `test`, `integration` hoặc `testcontainers`. Native production có thể dùng profile riêng. Cần tránh để test profile thay đổi context theo cách không được kiểm tra.

Ví dụ:
- `test`: dùng fake bean hoặc embedded/test database.
- `native-prod`: dùng production adapters và security configuration.
- `staging`: chỉ thay endpoint/credential/observability values nếu cấu trúc bean không đổi.

Nếu test AOT/native executable dùng profile test, kết quả không tự chứng minh production profile cũng tương thích. Cần build/test theo cấu trúc production hoặc tạo variant tương ứng.

Giữ profile naming rõ và ghi trong build manifest. Không để profile active ngầm phụ thuộc máy developer.

## 13. Maven: truyền profile/property cho AOT/native build

Cách truyền property phụ thuộc Spring Boot và Native Build Tools plugin version. Ví dụ chạy Maven với environment:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./mvnw -Pnative -DskipTests package
```

Một số workflow dùng property system hoặc plugin configuration riêng. Điều quan trọng là biến phải tới process thực hiện Spring AOT. Kiểm tra log và generated output để xác nhận.

Không giả định `-Dspring.profiles.active=native-prod` luôn có cùng precedence với environment variable hoặc property file. Spring Boot property source ordering và cách plugin fork process có thể ảnh hưởng. Dùng đúng cơ chế của version dự án và kiểm thử.

## 14. Gradle: truyền profile/property cho AOT task

Ví dụ:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./gradlew clean nativeCompile
```

Nếu dùng Gradle daemon, process daemon có thể được tạo từ môi trường trước đó. Khi thay đổi toolchain hoặc environment inputs, kiểm tra daemon/task configuration và cache. Có thể cần dừng daemon hoặc chạy build trong runner sạch để loại trừ environment cũ.

Task `nativeCompile` có thể phụ thuộc `processAot` theo plugin configuration. Xác minh task graph thay vì giả định. Nếu dự án cấu hình AOT task riêng, truyền structural properties tới đúng task đó.

## 15. Build variant riêng cho structural configuration

Nếu cần hai bean graph khác nhau, có thể tạo hai native build variants:

| Variant | AOT inputs | Runtime purpose |
|---|---|---|
| `orders-native-search` | Search enabled | Triển khai nơi có search feature |
| `orders-native-core` | Search disabled | Triển khai tối giản không có search |

Mỗi variant cần:
- AOT profile/property riêng.
- Output directory riêng.
- Artifact/image tag và digest riêng.
- Native tests riêng.
- Manifest ghi structural inputs.
- SBOM/provenance tương ứng.

Không tái sử dụng generated AOT output giữa hai variant nếu structural inputs khác nhau. Cũng không đổi runtime profile của variant này để giả lập variant kia.

## 16. Property precedence và nguồn cấu hình

Spring Boot có nhiều property sources: config data, environment variables, system properties, command-line arguments và các nguồn khác. Giá trị cuối cùng phụ thuộc precedence.

Khi điều tra mismatch, ghi:
- Property key chuẩn.
- Nguồn cung cấp.
- Giá trị đã redact.
- Process nhận property.
- Thời điểm đọc/bind.
- Property có được dùng trong condition hay chỉ trong bean logic.

Actuator env/configprops endpoints có thể hỗ trợ diagnostics nhưng rất nhạy cảm. Chỉ expose trong môi trường nội bộ, giới hạn quyền và không trả secret. Không bật endpoint environment công khai trong production.

## 17. Property được đọc một lần và property được đọc động

Không phải mọi value property đều tự cập nhật khi file cấu hình thay đổi. Ví dụ `@ConfigurationProperties` thường được bind khi bean được tạo; thay file config sau startup không có nghĩa bean tự refresh.

Phân biệt:
- Value được bind lúc ApplicationContext khởi động.
- Value được đọc trực tiếp từ `Environment` khi method chạy.
- Bean được refresh bởi Spring Cloud/config mechanism nếu ứng dụng có hỗ trợ.
- Property được quyết định ở AOT/build time.

Native Image không tự biến property tĩnh thành dynamic configuration. Nếu cần refresh runtime, dùng cơ chế refresh/configuration đã được thiết kế và xác minh native support. Đừng kỳ vọng thay file mounted sẽ cập nhật object đã bind mà không có refresh mechanism.

## 18. Cache và output AOT phải tách theo structural inputs

Nếu AOT output được cache, cache key phải phản ánh mọi đầu vào ảnh hưởng context:
- Commit/source revision.
- Dependency graph.
- Spring Boot/plugin versions.
- Active profiles của AOT process.
- Structural properties.
- Generated source/resources.
- RuntimeHints/metadata.
- OS/toolchain nếu output phụ thuộc nền tảng.

Nếu cache key chỉ dựa trên commit mà bỏ profile/property, output từ build variant trước có thể bị tái sử dụng sai. Điều này gây behavior khó giải thích hoặc build không tái lập.

Dùng output directories riêng cho variants và lưu manifest. Khi nghi ngờ cache, chạy clean build trên runner sạch để so sánh.

## 19. Chẩn đoán lỗi do profile/property không khớp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bean thiếu dù runtime property bật | AOT đã phân tích condition là false | Build lại với structural input đúng |
| Bean tồn tại dù runtime property tắt | Bean đã được tạo trong AOT context | Đưa điều kiện vào runtime logic nếu cần toggle |
| JVM chạy profile, native không chạy | Profile thay đổi bean graph sau AOT | Tạo build variant hoặc context tương thích |
| URL runtime không đổi | Bean/property đã bind từ nguồn khác hoặc precedence khác | Kiểm tra Environment/property source |
| AOT output giữa job bị lẫn | Cache/output directory không tách variant | Tách cache key và output path |
| Native test pass, production fail | Test profile/context khác production | Test structural production configuration |
| Thay file config nhưng behavior không đổi | Bean không refresh sau startup | Dùng refresh mechanism hoặc restart |

## 20. Bài thực hành tổng hợp: hai profile, một binary hay hai binary?

**Bối cảnh:** Order API có tính năng search tùy chọn. Khi bật search, ứng dụng cần đăng ký SearchRepository và SearchService; endpoint inventory chỉ thay URL/timeout theo môi trường.

**Bước 1 — Phân loại property.** Xác định `search.enabled` được dùng trong `@ConditionalOnProperty`; `inventory.base-url` và `inventory.timeout` chỉ được bind vào client bean.

**Bước 2 — Chạy JVM baseline.** Khởi động với search bật/tắt và inventory endpoint A/B; ghi bean presence và request destination.

**Bước 3 — Build AOT variant search-off.** Chạy AOT với `search.enabled=false`, lưu generated output và manifest.

**Bước 4 — Build AOT variant search-on.** Chạy AOT với `search.enabled=true` trong output directory riêng.

**Bước 5 — Build native executable.** Tạo hai binary hoặc workflow variant theo cấu hình structural, ghi digest.

**Bước 6 — Thử runtime overrides.** Với mỗi binary, thay inventory URL/timeout mà không rebuild; xác nhận client dùng value mới.

**Bước 7 — Thử đổi search flag sau build.** Đặt giá trị ngược với AOT input và quan sát bean/endpoint. Ghi nhận giới hạn thay đổi cấu trúc context.

**Bước 8 — Kiểm tra test và cache.** Chạy native integration tests cho từng variant, xác minh cache key chứa structural inputs.

**Bước 9 — Đưa ra thiết kế.** Chọn một binary nếu feature chỉ là runtime behavior; dùng build variants nếu bean graph khác nhau.

Tiêu chí hoàn thành: mỗi property được phân loại dựa trên cách sử dụng; AOT inputs được ghi rõ; runtime values thay đổi đúng trên cùng binary; structural changes được build/test thành variant phù hợp; cache và manifest không trộn cấu hình.

## 21. Kết luận

Ranh giới quan trọng trong Spring Boot Native Image là property nào thay đổi cấu trúc ApplicationContext khi Spring AOT chạy và property nào chỉ cung cấp giá trị cho bean đã được tạo. Profile, `@Profile` và `@ConditionalOnProperty` thường tạo structural decisions; URL, timeout và nhiều operational values có thể thay đổi ở runtime. Nhưng cách dùng trong code mới là yếu tố quyết định.

Hãy phân loại property theo tác động, truyền đúng structural inputs vào process AOT, tách output/cache theo build variant và ghi manifest. Kiểm chứng bằng cách build hai AOT variants, chạy cùng executable với runtime value khác nhau và thử đổi structural flag sau build. Nếu cần thay đổi bean graph, tạo build variant được kiểm thử; nếu chỉ cần đổi giá trị, thiết kế bean luôn tồn tại và bind runtime configuration.
