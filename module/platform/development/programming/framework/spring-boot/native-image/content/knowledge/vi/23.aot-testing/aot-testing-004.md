# Kiểm thử ApplicationContext sau khi cố định profile và điều kiện build

## 1. Vì sao phải cố định profile và điều kiện trước khi kiểm thử AOT?

Spring Boot tạo ApplicationContext dựa trên configuration class, component scan, auto-configuration, active profiles, property sources và các condition như `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`. Những đầu vào này quyết định bean nào được đăng ký và dependency nào được kết nối.

Trong ứng dụng chạy JVM thông thường, mỗi lần process khởi động có thể nạp profile và property khác để tạo context tương ứng. Với **Spring AOT và GraalVM Native Image**, Spring phân tích một ApplicationContext ở build time và sinh mã khởi tạo dựa trên cấu trúc được chọn. Native executable được tạo từ kết quả đó. Nếu profile hoặc structural property thay đổi sau khi build, ứng dụng không thể mặc nhiên tạo lại mọi bean đã bị loại khỏi cấu trúc AOT.

Vì vậy, trước khi kiểm thử AOT cần cố định rõ:

- Profile dùng để phân tích ApplicationContext.
- Property tham gia điều kiện đăng ký bean.
- Classpath/dependency và các điều kiện class/resource.
- Các nguồn cấu hình build-time mà AOT thực sự nhận được.
- Kỳ vọng bean nào phải có và bean nào phải vắng mặt.

Bài này hướng dẫn xây kiểm thử ApplicationContext có thể tái lập, xác minh bean graph theo profile/condition, sau đó đối chiếu với AOT-generated context và native executable trong module **SPRING_BOOT_NATIVE_IMAGE**.

## 2. Structural configuration và runtime values

Không phải mọi property đều cần cố định khi build. Cần phân loại theo cách property được sử dụng.

| Loại property | Ví dụ | Ảnh hưởng |
|---|---|---|
| Structural/build-time | `spring.profiles.active` khi profile chọn configuration class | Có thể thay đổi tập bean được AOT phân tích |
| Structural/build-time | `payment.provider` dùng trong `@ConditionalOnProperty` | Quyết định implementation nào được đăng ký |
| Structural/build-time | Classpath/dependency có hoặc không có một thư viện | Ảnh hưởng condition như `@ConditionalOnClass` |
| Runtime value | URL API được inject vào bean luôn tồn tại | Thay giá trị endpoint, không đổi bean graph |
| Runtime value | Timeout/limit được đọc trong service | Thay hành vi nghiệp vụ trong phạm vi code đã có |
| Runtime value | Token/secret được cung cấp lúc chạy | Cung cấp credential cho bean đã tồn tại |

Ví dụ, `feature.enabled` chỉ được đọc trong một nhánh `if` của service đã đăng ký có thể là runtime value. Cùng property đó nếu dùng trong `@ConditionalOnProperty` để tạo hoặc bỏ bean thì nó là structural input.

Phân loại sai dẫn tới test không có ý nghĩa: kiểm thử JVM với property khác AOT có thể tạo bean graph khác rồi kết luận nhầm native bị lỗi.

## 3. Xác định build contract trước khi viết test

Tạo một cấu hình build contract có thể ghi lại trong CI:

| Đầu vào | Giá trị ví dụ | Nguồn cần kiểm soát |
|---|---|---|
| Spring profile | `native-prod` | Environment/argument của process AOT |
| Payment provider | `stripe` | Property được AOT đánh giá |
| Search integration | Có dependency search client | Runtime classpath |
| Metrics bean | `metrics.enabled=true` | Structural property nếu condition đăng ký bean |
| Inventory URL | `https://inventory.internal` | Runtime config nếu chỉ là giá trị inject |
| Locale mặc định | `vi-VN` | Runtime config nếu ứng dụng cho phép thay đổi |
| GraalVM/JDK | Version đã pin | CI toolchain |
| Spring Boot plugin | Version đã pin | Build configuration |

Các giá trị trên chỉ là ví dụ. Dự án cần xác định chính xác property và profile thực tế. Ghi lại cả nguồn property và cách nó được truyền vào process AOT; một biến có trong shell chưa chắc đã được plugin chuyển tới JVM thực thi AOT.

## 4. Thiết kế cấu hình có profile rõ ràng

Ví dụ ứng dụng có adapter thanh toán khác nhau theo profile:

```java
@Configuration(proxyBeanMethods = false)
@Profile("native-prod")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("local")
class LocalPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new MockPaymentGateway();
    }
}
```

Hai profile tạo bean graph khác nhau. Nếu AOT được thực hiện với `native-prod`, context sinh ra phản ánh cấu hình production. Không nên build native với profile `local`, rồi chỉ đặt `SPRING_PROFILES_ACTIVE=native-prod` trong container và kỳ vọng configuration production tự xuất hiện.

Nếu cần cùng một native executable chạy nhiều môi trường, hãy thiết kế tập bean ổn định và chuyển lựa chọn môi trường thành runtime value. Nếu cấu trúc bean thực sự khác nhau, build artifact riêng theo từng structural profile.

## 5. Condition property cần được cố định

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class SearchConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "search",
            name = "enabled",
            havingValue = "true"
    )
    SearchClient searchClient() {
        return new SearchClient();
    }
}
```

Khi `search.enabled=true`, bean `SearchClient` được đăng ký; khi false hoặc thiếu theo semantics của annotation, bean có thể không tồn tại.

Nếu condition được đánh giá trong AOT, giá trị structural phải được truyền vào đúng AOT process. Kiểm thử context nên assert cả trường hợp match lẫn non-match trên JVM; sau đó chạy AOT với biến thể phát hành đã chọn và xác nhận native context chứa bean mong đợi.

Không dùng một test chỉ assert application context “đã refresh” làm bằng chứng condition đúng. Context có thể khởi động thành công dù một integration bean quan trọng bị thiếu.

## 6. Kiểm thử active profile bằng Spring Boot test

Có thể tạo context test với profile cố định bằng `@ActiveProfiles`:

```java
@SpringBootTest
@ActiveProfiles("native-prod")
class ProductionContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersProductionGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(StripePaymentGateway.class);
    }
}
```

Test này xác minh ApplicationContext trên JVM được tạo với profile `native-prod`. Nó không tự chứng minh Spring AOT build đã dùng cùng profile. Cần bảo đảm build pipeline truyền profile tương ứng vào process AOT và kiểm tra output/log.

Nếu test dùng `@SpringBootTest(properties=...)` cùng `@ActiveProfiles`, hãy ghi rõ property nào là test override và property nào là structural input của artifact phát hành. Tránh để test override che mất cấu hình CI.

## 7. Kiểm thử condition property bằng ApplicationContextRunner

Với auto-configuration hoặc configuration class nhỏ, `ApplicationContextRunner` giúp kiểm tra condition độc lập:

```java
class SearchConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(SearchConfiguration.class);

    @Test
    void createsSearchClientWhenEnabled() {
        runner.withPropertyValues("search.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(SearchClient.class);
                });
    }

    @Test
    void omitsSearchClientWhenDisabled() {
        runner.withPropertyValues("search.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(SearchClient.class);
                });
    }
}
```

Runner tạo context riêng cho từng trường hợp, giúp xác nhận logic condition. Với cấu hình có nhiều dependency, profile, component scan hoặc auto-configuration, bổ sung test tích hợp trên ApplicationContext đầy đủ để kiểm tra tương tác giữa các bean.

ApplicationContextRunner test không chạy Spring AOT. Nó là lớp kiểm tra condition trên JVM trước khi chuyển sang AOT validation.

## 8. Assert cả bean có mặt và bean vắng mặt

Một test hữu ích cần xác nhận hai phía của bean graph:

- Bean bắt buộc phải có.
- Bean không được phép có trong profile/condition hiện tại.
- Có đúng một bean cho interface quan trọng.
- Dependency được inject là implementation dự kiến.
- Bean không bị tạo trùng do nhiều configuration class cùng match.

Ví dụ:

```java
assertThat(context).hasSingleBean(PaymentGateway.class);
assertThat(context).hasBean("stripePaymentGateway");
assertThat(context).doesNotHaveBean("mockPaymentGateway");
```

Tên bean trong assertion phải khớp naming convention thực tế hoặc dùng type assertion phù hợp. Với nhiều implementation, kiểm tra qualifier/primary selection và bean injection tại consumer, không chỉ kiểm tra các bean riêng lẻ.

Việc assert bean vắng mặt quan trọng vì một cấu hình quá rộng có thể vô tình tạo cả mock lẫn production client, dẫn đến ambiguity hoặc rủi ro gọi nhầm hệ thống.

## 9. Kiểm thử dependency graph và bean wiring

Sau khi xác nhận bean registration, kiểm tra service tiêu thụ đúng implementation:

```java
@SpringBootTest
@ActiveProfiles("native-prod")
class PaymentServiceWiringTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    ApplicationContext context;

    @Test
    void usesProductionGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(StripePaymentGateway.class);

        assertThat(paymentService).isNotNull();
    }
}
```

Nếu service nhận dependency qua constructor, có thể kiểm tra trực tiếp bean implementation hoặc dùng test behavior để xác minh lời gọi đi đến gateway dự kiến. Tránh chỉ assert object khác null nếu mục tiêu là kiểm tra wiring.

Với bean có lifecycle như scheduler, datasource hoặc message listener, test cần tránh khởi tạo side effect thật. Dùng test double hoặc cấu hình sandbox để ApplicationContext test không kết nối production.

## 10. Xác minh profile/property thực sự tới bước Spring AOT

Đây là điểm thường bị bỏ sót. Test `@ActiveProfiles` chỉ điều khiển context test. Nó không tự truyền profile vào Maven/Gradle AOT process.

Cần kiểm tra:

1. Build task/goal nào thực thi Spring AOT.
2. JVM process đó nhận active profile từ đâu.
3. System properties/environment có được plugin truyền tiếp không.
4. Profile-specific config data được nạp ở pha AOT hay không.
5. Condition report/log cho thấy property có giá trị dự kiến.
6. Generated AOT output tương ứng với cấu trúc context nào.

Có thể dùng log tạm thời hoặc một condition/configuration diagnostic an toàn để ghi tên profile và trạng thái feature (không log secret). Sau khi xác minh, bỏ log chẩn đoán không cần thiết.

Không chỉ nhìn command line bên ngoài. Plugin có thể fork process riêng hoặc dùng cấu hình riêng cho AOT; phải xác nhận property có mặt ở đúng JVM xử lý context.

## 11. Chạy AOT processing sau khi cố định structural inputs

Quy trình build cần chạy AOT với profile và condition đã chọn. Ví dụ Gradle minh họa:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./gradlew processAot
```

Maven minh họa:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./mvnw -Pnative spring-boot:process-aot
```

Đây là minh họa về ý định truyền environment; task/goal và cách plugin nhận property phụ thuộc Spring Boot version cùng cấu hình dự án. Xác nhận đúng task tồn tại và log cho thấy AOT process nhận các property này.

Một số dự án dùng Maven profile hoặc Gradle project property để cấu hình plugin, nhưng project property không tự động đồng nghĩa Spring Environment property. Đọc cấu hình plugin hiện có và dùng cơ chế được version đó hỗ trợ.

## 12. Đối chiếu generated context với kỳ vọng

Sau AOT processing, kiểm tra generated sources/resources theo vị trí output của build tool và plugin version. Không chỉnh trực tiếp generated files; chúng là sản phẩm của lần build và sẽ được tạo lại.

Câu hỏi cần xác minh:

- Configuration class nào được xử lý?
- Bean initialization code có implementation dự kiến không?
- Conditional bean có mặt/vắng đúng không?
- Proxy/hints liên quan được thu thập chưa?
- Profile/property structural có khớp build contract?
- Build có warning về bean hoặc dynamic access không?

Generated output có thể khác nhau theo version Spring Boot, vì vậy không viết test phụ thuộc cứng vào tên file nội bộ nếu framework không cam kết API đó. Dùng log, public testing hooks và behavior của executable làm bằng chứng chính.

## 13. Phân biệt test JVM context với AOT-generated context

| Kiểm thử | Context được kiểm tra | Bằng chứng |
|---|---|---|
| `@SpringBootTest` | Context được khởi tạo trên JVM theo test profiles/properties | Cấu hình JVM và wiring đúng |
| `ApplicationContextRunner` | Context nhỏ theo condition/property test | Condition logic đúng |
| Spring AOT processing | Context được phân tích trong build phase | AOT có thể tạo mã cho structural inputs đã chọn |
| AOT-generated context test nếu project hỗ trợ | Context được khởi tạo qua generated initializer | Generated initialization hoạt động trong test setup |
| Native executable test | Context thực tế trong native process | Binary khởi tạo và wiring đúng trong runtime |

Không gọi mọi `@SpringBootTest` là AOT test. Nó thường chạy trên JVM. Muốn xác nhận native, phải chạy native test mode được plugin hỗ trợ hoặc khởi chạy native executable thật.

Một số Spring Boot version có test support để dùng AOT-generated initializers trong JVM test. Cách bật và phạm vi hỗ trợ phụ thuộc version; nếu dùng, phải xác nhận test thực sự tải generated initializer thay vì chỉ tạo context thông thường.

## 14. Kiểm tra bean condition trong native executable

Sau khi build native với profile/condition đã cố định, chạy executable và kiểm tra hành vi bean qua endpoint hoặc test probe. Ví dụ endpoint nội bộ dành cho integration test có thể trả về tên implementation đang được dùng; không expose thông tin cấu hình nhạy cảm ra public API.

Tốt hơn nữa, gọi nghiệp vụ thật:

- Gửi payment request và xác minh request đi đến sandbox gateway dự kiến.
- Gọi search endpoint và xác nhận bean search được dùng.
- Kiểm tra feature tắt không khởi tạo integration hoặc không phát sinh outbound call.
- Xác minh profile không tạo mock implementation trong production artifact.

Nếu không muốn endpoint chẩn đoán, dùng test harness hoặc log có cấu trúc trong môi trường test. Tránh dựa vào reflection để liệt kê mọi bean ở runtime native chỉ nhằm xác nhận context nếu ứng dụng không có metadata cho thao tác đó.

## 15. Nhiều profile cần nhiều artifact hay một artifact?

Nếu profile thay đổi cấu trúc bean, có hai chiến lược:

| Chiến lược | Cách thực hiện | Khi phù hợp |
|---|---|---|
| Artifact riêng theo profile | Chạy AOT/native build với từng structural profile | Tập bean khác biệt rõ, yêu cầu cô lập |
| Một bean graph ổn định | Đăng ký các implementation cần thiết, chọn bằng runtime values | Cần một binary dùng qua nhiều môi trường |

Ví dụ, nếu `local` dùng mock datasource và `production` dùng cloud datasource với configuration class khác nhau, một AOT build chỉ phân tích một profile không tự chứa cả hai cấu trúc. Có thể build riêng artifact hoặc thiết kế adapter/factory để cả implementation cần thiết đều có trong context và selector chọn lúc runtime.

Một artifact chung có thể lớn hơn hoặc mang dependency không cần thiết ở một số môi trường. Cần cân nhắc kích thước, bảo mật, dependency và chi phí build.

## 16. Tránh để test profile làm sai lệch kết luận

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test pass nhưng native thiếu bean | Test dùng `@ActiveProfiles` khác profile AOT | Đồng bộ structural profile và xác minh AOT process |
| Native có cả mock và production bean | Condition/profile không loại đúng implementation | Assert bean có mặt/vắng và kiểm tra condition |
| Property test pass nhưng AOT khác | Test property chỉ áp dụng cho test context | Truyền property vào đúng AOT process |
| Local pass, CI fail | Environment/profile/plugin khác | Ghi build contract và pin toolchain |
| Runtime đổi profile nhưng bean không đổi | Bean graph đã được xác định trong AOT | Build artifact khác hoặc dùng runtime selector |
| AOT build pass nhưng startup lỗi | Bean wiring/lifecycle/runtime dependency lỗi | Chạy native context startup và integration test |
| Search bean không có | `@ConditionalOnClass` không match do dependency thiếu | Kiểm tra runtimeClasspath và dependency graph |

Không sửa bằng cách thêm profile vào container nếu vấn đề nằm ở generated bean graph. Cần quyết định lại structural input hoặc thiết kế bean graph ổn định.

## 17. Bài thực hành: cố định production profile và xác minh context

**Bối cảnh:** Order API có hai payment gateway. Local dùng mock, native production dùng Stripe. Search integration được bật bằng `search.enabled`.

**Bước 1 — Khai báo configuration.** Tạo profile-specific configuration cho gateway và condition property cho search client.

**Bước 2 — Viết JVM context tests.** Dùng `@ActiveProfiles("local")` và `@ActiveProfiles("native-prod")` để xác nhận gateway đúng; dùng ApplicationContextRunner cho `search.enabled=true/false`.

**Bước 3 — Tạo build contract.** Ghi profile `native-prod`, `search.enabled=true`, classpath/dependency và toolchain version.

**Bước 4 — Truyền structural inputs vào AOT.** Cấu hình Maven/Gradle process để Spring AOT nhận đúng profile/property; xác minh qua log và output.

**Bước 5 — Build native executable.** Dùng cùng structural inputs, không thay profile giữa AOT và native compilation.

**Bước 6 — Chạy native context tests.** Khởi động executable, gọi payment/search scenario và xác minh implementation được sử dụng.

**Bước 7 — Thử thay runtime value.** Đổi URL hoặc timeout mà không đổi structural property; xác nhận cùng binary vẫn dùng đúng bean graph và nhận giá trị runtime mới.

**Bước 8 — Thử structural variant.** Build một artifact khác với `search.enabled=false` nếu cần; xác nhận bean search vắng mặt trong variant đó.

Tiêu chí hoàn thành: profile/condition được ghi nhận; JVM context tests xác nhận bean graph; AOT xử lý đúng structural inputs; native executable khởi tạo và dùng đúng bean; runtime values có thể đổi trong phạm vi thiết kế.

## 18. Checklist tái lập trong CI

Mỗi native build nên lưu lại các thông tin sau:

- Git commit và trạng thái working tree.
- JDK/GraalVM distribution và version.
- Spring Boot, Native Build Tools và plugin versions.
- Active profiles tại AOT phase.
- Structural properties và nguồn truyền vào.
- Dependency graph/classpath.
- Build arguments và environment liên quan.
- Kết quả context assertions trên JVM.
- AOT processing log/status.
- Kết quả native build và native runtime scenarios.
- Container image/base OS/architecture.
- Runtime properties được phép thay đổi sau build.

Không đưa secret vào artifact log. Có thể ghi tên property và trạng thái đã được cấp thay vì giá trị. Nếu build cần credential để resolve dependency, dùng secret CI và không lưu vào generated source hoặc native image.

## 19. Kết luận

Kiểm thử ApplicationContext cho Spring AOT cần bắt đầu bằng việc cố định **profile, structural properties, classpath và điều kiện build**. JVM context tests xác nhận condition và bean wiring theo đầu vào đã chọn; AOT processing cần nhận đúng các đầu vào đó; native executable phải được chạy để xác minh context và các bean thực sự hoạt động.

Hãy phân biệt structural configuration với runtime values, assert cả bean phải có lẫn bean phải vắng, ghi lại build contract và kiểm tra profile/property đến đúng process AOT. Nếu các môi trường cần bean graph khác nhau, build artifact riêng hoặc thiết kế một context ổn định với runtime selection. Cách làm này giúp native build có thể tái lập và tránh nhầm lẫn giữa một JVM test pass với bằng chứng AOT/native behavior đúng.
