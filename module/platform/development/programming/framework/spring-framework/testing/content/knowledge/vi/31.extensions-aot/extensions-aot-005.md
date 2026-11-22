# ContextCustomizerFactory và đóng góp vào khóa cache

Spring TestContext Framework tạo và quản lý ApplicationContext cho các test tích hợp. Vì khởi tạo context có thể tốn thời gian, Spring lưu context đã tạo trong một cache và tái sử dụng khi một test khác có cấu hình tương đương. Cơ chế mở rộng quan trọng ở giai đoạn chuẩn bị context là ContextCustomizerFactory.

ContextCustomizerFactory cho phép thư viện hoặc dự án đọc metadata của test class rồi tạo một ContextCustomizer. Customizer được áp dụng lên ConfigurableApplicationContext trước khi context refresh. Một customizer có thể thêm property source, đăng ký bean definition hoặc điều chỉnh môi trường test. Các customizer này cũng tham gia vào MergedContextConfiguration, đối tượng được dùng làm khóa tra cứu trong context cache.

Điều đó tạo ra một yêu cầu quan trọng: ContextCustomizer phải có equals() và hashCode() phản ánh đầy đủ những thông tin làm thay đổi ApplicationContext. Nếu hai cấu hình khác nhau bị xem là bằng nhau, Spring có thể tái sử dụng nhầm context. Nếu hai customizer có cùng cấu hình nhưng luôn bị xem là khác nhau, cache sẽ mất khả năng tái sử dụng và suite chạy chậm hơn.

## 1. ContextCustomizerFactory nằm ở đâu trong TestContext Framework?

Spring TestContext Framework sử dụng TestContextManager để điều phối vòng đời test và tạo TestContext. Khi cần nạp ApplicationContext, Spring xây dựng một MergedContextConfiguration từ metadata của test class, bao gồm các nguồn cấu hình và các tùy chỉnh liên quan.

Một phần của quá trình bootstrap có thể hình dung như sau:

~~~~text
Test class
    |
    v
TestContextBootstrapper
    |
    +--> Đọc @ContextConfiguration, profiles, properties...
    |
    +--> Phát hiện ContextCustomizerFactory
    |        |
    |        v
    |    createContextCustomizer(...)
    |        |
    |        v
    |    ContextCustomizer
    |
    v
MergedContextConfiguration
    |
    +--> Được dùng làm cache key
    |
    v
ContextCache
    |
    +--> Có context phù hợp? ---- Có ----> Tái sử dụng context
    |                                  |
    |                                  v
    |                                Test
    |
    +--> Chưa có? ----> Tạo context
                          |
                          v
                   ContextCustomizer
                   customizeContext(...)
                          |
                          v
                   ApplicationContext refresh
                          |
                          v
                         Test
~~~~

Factory không trực tiếp tạo ApplicationContext. Factory chỉ tạo ra một đối tượng mô tả cách tùy chỉnh context. Spring đưa các customizer vào cấu hình đã hợp nhất, dùng cấu hình đó để tra cache và áp dụng customizer nếu phải tạo context mới.

Hai interface chính:

- ContextCustomizerFactory: phát hiện metadata của test class và tạo ContextCustomizer.
- ContextCustomizer: thay đổi ConfigurableApplicationContext trước khi context được refresh.

Các interface nằm trong package org.springframework.test.context.

## 2. ContextCustomizerFactory có nhiệm vụ gì?

ContextCustomizerFactory khai báo phương thức:

~~~~java
ContextCustomizer createContextCustomizer(
        Class<?> testClass,
        List<ContextConfigurationAttributes> configAttributes
);
~~~~

Factory nhận test class và các thuộc tính cấu hình được thu thập từ @ContextConfiguration. Dựa trên metadata đó, factory tạo một customizer phù hợp.

Factory có thể đọc:

- Annotation riêng trên test class.
- Meta-annotation được đặt trên annotation khác.
- Các thuộc tính của @ContextConfiguration.
- Kiểu test hoặc cấu trúc class hierarchy nếu đó là một phần của quy ước test.
- Metadata cần thiết để chuẩn bị property source, bean hoặc hạ tầng context.

Factory thường không nên khởi tạo service ngoài, mở kết nối database hoặc thực hiện công việc tốn thời gian. Việc discovery xảy ra trong quá trình chuẩn bị cấu hình test; customizer mới là đối tượng được áp dụng lên context khi Spring cần tạo context.

Một factory tốt có các đặc điểm:

- Tạo kết quả xác định từ metadata của test.
- Không phụ thuộc trạng thái mutable dùng chung.
- Trả về customizer có equality/hashCode ổn định.
- Không khởi tạo context hoặc tự quản lý cache.
- Chỉ mô tả những thay đổi thực sự cần cho ApplicationContext.

## 3. ContextCustomizer được áp dụng lúc nào?

ContextCustomizer có phương thức:

~~~~java
void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
);
~~~~

Spring gọi phương thức này trong quá trình chuẩn bị ApplicationContext, trước khi context được refresh. Vì vậy, customizer phù hợp để thay đổi môi trường hoặc đăng ký cấu hình cần có mặt trước khi các singleton bean được khởi tạo.

Ví dụ, customizer có thể thêm MapPropertySource vào Environment:

~~~~java
context.getEnvironment()
        .getPropertySources()
        .addFirst(propertySource);
~~~~

Sau khi context refresh, các bean có thể đọc property đó qua @Value, Environment hoặc cơ chế cấu hình khác.

Customizer cũng có thể đăng ký bean definition thông qua bean factory hoặc context phù hợp. Tuy nhiên, nếu nhu cầu chỉ là khai báo bean cố định cho test, @TestConfiguration hoặc @Import thường dễ hiểu hơn. ContextCustomizer có giá trị khi việc thay đổi cần được quyết định từ metadata của test class hoặc cần được đóng gói thành một cơ chế tái sử dụng.

Không nên dùng customizer để sửa một context đã refresh. Các bean singleton có thể đã được tạo và dependency injection đã hoàn tất. Nếu cần cấu hình trước khi bean được khởi tạo, hãy thực hiện trong giai đoạn customizeContext.

## 4. Ví dụ: annotation riêng để chọn tenant cho test

Giả sử ứng dụng cần kiểm thử với tenant khác nhau. Ta muốn viết:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class NorthTenantTest {
    // Test với tenant north.
}

@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {
    // Test với tenant south.
}
~~~~

Mỗi test class cần ApplicationContext có property test.tenant-id tương ứng. Ta có thể xây dựng cơ chế gồm ba phần:

1. Annotation @TestTenant chứa tenant identifier.
2. ContextCustomizerFactory đọc annotation và tạo customizer.
3. ContextCustomizer thêm property source trước khi context refresh.

### Khai báo annotation

~~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface TestTenant {
    String value();
}
~~~~

@Retention(RUNTIME) để annotation có mặt khi Spring đọc metadata ở runtime. @Target(TYPE) giới hạn annotation ở class/interface. @Inherited cho phép annotation được kế thừa theo quy tắc Java từ superclass; nếu cần hỗ trợ meta-annotation hoặc merged attributes phức tạp, dùng AnnotatedElementUtils khi đọc annotation.

### Tạo ContextCustomizer

~~~~java
public final class TenantContextCustomizer implements ContextCustomizer {

    private final String tenantId;

    public TenantContextCustomizer(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        if (tenantId == null) {
            return;
        }

        Map<String, Object> properties = Map.of(
                "test.tenant-id", tenantId
        );

        MapPropertySource propertySource =
                new MapPropertySource("testTenant", properties);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(propertySource);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof TenantContextCustomizer that)) {
            return false;
        }
        return Objects.equals(this.tenantId, that.tenantId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId);
    }
}
~~~~

TenantContextCustomizer giữ tenantId bất biến. Khi context được tạo, customizer thêm property source có độ ưu tiên cao để bean có thể đọc tenant đã chọn.

Điểm quan trọng là equals() và hashCode() sử dụng tenantId. Hai customizer cùng tenant có thể được xem là bằng nhau; hai customizer với tenant khác nhau sẽ không bằng nhau.

Nếu customizer không override equals() và hashCode(), Java dùng identity equality kế thừa từ Object. Mỗi lần factory tạo một instance mới, các instance đó thường bị xem là khác nhau dù cùng chứa tenantId. Context cache có thể không tái sử dụng context giữa các test có cấu hình giống nhau.

### Tạo factory

~~~~java
public final class TenantContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes
    ) {
        TestTenant annotation =
                AnnotatedElementUtils.findMergedAnnotation(
                        testClass,
                        TestTenant.class
                );

        String tenantId = annotation != null
                ? annotation.value()
                : null;

        return new TenantContextCustomizer(tenantId);
    }
}
~~~~

Factory tìm annotation trên test class. Nếu không có annotation, customizer nhận null và không thay đổi context. Cách này luôn tạo một customizer có semantics rõ ràng; customizer no-op cho test không khai báo tenant vẫn có equality ổn định.

Nếu muốn dùng meta-annotation, AnnotatedElementUtils.findMergedAnnotation(...) hỗ trợ tìm annotation hợp nhất trên các annotation được kết hợp. Điều này hữu ích khi dự án tạo annotation cấp cao như @NorthTenantTest được meta-annotate bằng @TestTenant("north").

### Đăng ký factory

Spring TestContext Framework phát hiện ContextCustomizerFactory qua SpringFactoriesLoader. Đăng ký factory trong file:

    src/test/resources/META-INF/spring.factories

Nội dung:

~~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TenantContextCustomizerFactory
~~~~

Nếu factory thuộc một thư viện test support được tái sử dụng bởi nhiều module, file metadata cần được đóng gói trong artifact mà các test tiêu thụ trên test classpath. Nếu chỉ dùng trong một project, đặt ở test resources là đủ.

Spring có thể phát hiện nhiều factory từ các file spring.factories trên classpath. Không ghi đè các entry của thư viện khác khi tạo file mới; cần dùng đúng cơ chế merge metadata của build để tất cả factory cần thiết được giữ lại.

## 5. Dùng property do customizer cung cấp trong bean

Cấu hình test có thể đọc property vừa được thêm. Ví dụ, dùng Environment để tránh phụ thuộc vào placeholder trong annotation:

~~~~java
@Configuration
public class TenantTestConfig {

    @Bean
    TenantInfo tenantInfo(Environment environment) {
        return new TenantInfo(
                environment.getRequiredProperty("test.tenant-id")
        );
    }
}

public record TenantInfo(String tenantId) {
}
~~~~

Test class:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class NorthTenantTest {

    @Autowired
    TenantInfo tenantInfo;

    @Test
    void shouldUseNorthTenant() {
        assertThat(tenantInfo.tenantId()).isEqualTo("north");
    }
}
~~~~

Khi Spring tạo context cho NorthTenantTest, factory đọc "north", customizer thêm property source, sau đó context refresh và bean TenantInfo được tạo với giá trị tương ứng.

Test class khác:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {

    @Autowired
    TenantInfo tenantInfo;

    @Test
    void shouldUseSouthTenant() {
        assertThat(tenantInfo.tenantId()).isEqualTo("south");
    }
}
~~~~

Customizer cho "south" không bằng customizer cho "north". Do đó, nếu các thành phần cấu hình khác giống nhau, Spring vẫn phải dùng hai cache entry khác nhau vì property và bean đã được cấu hình khác nhau.

## 6. MergedContextConfiguration là gì?

MergedContextConfiguration là đối tượng mô tả cấu hình đã được hợp nhất cho một test class. Nó chứa metadata cần thiết để Spring tạo ApplicationContext.

Các thành phần thường ảnh hưởng đến cấu hình bao gồm:

- Resource locations hoặc configuration classes.
- ApplicationContextInitializer classes.
- Active profiles.
- Property source descriptors và inline properties.
- ContextCustomizer instances.
- ContextLoader.
- Parent context nếu có context hierarchy.
- Resource base path đối với web application context.

MergedContextConfiguration triển khai equals() và hashCode(). Spring dùng các giá trị này khi tra cứu context trong ContextCache.

ContextCustomizer collection là một phần của cấu hình được so sánh. Vì vậy, equality của customizer không chỉ là chi tiết nội bộ của class; nó ảnh hưởng trực tiếp đến việc Spring tái sử dụng ApplicationContext.

Có thể mô tả cache key theo cách đơn giản:

~~~~text
Cache key
    =
MergedContextConfiguration
    |
    +--> Classes / locations
    +--> Initializers
    +--> Active profiles
    +--> Property sources
    +--> Context customizers
    +--> Context loader
    +--> Parent context
    +--> Web resource path
~~~~

Hai test có cùng cache key có thể dùng lại cùng ApplicationContext. Nếu bất kỳ phần cấu hình nào khác nhau theo semantics của MergedContextConfiguration, Spring tạo hoặc tìm một cache entry khác.

## 7. Vì sao equals() và hashCode() của customizer rất quan trọng?

ContextCustomizer được đưa vào MergedContextConfiguration. Khi Spring so sánh hai MergedContextConfiguration, các customizer cũng được so sánh. Điều đó tạo ra hai loại lỗi nếu equality không đúng.

### Lỗi 1: Không override equals/hashCode

Giả sử mỗi lần factory chạy, nó tạo:

    new TenantContextCustomizer("north")

Hai instance này có cùng tenantId nhưng nếu dùng Object.equals(), chúng không bằng nhau vì là hai object khác nhau.

Hệ quả:

- Test class A tạo context với tenant north.
- Test class B có cấu hình tương đương cũng tạo customizer north mới.
- Cache key có customizer khác nhau theo identity.
- Spring có thể tạo thêm ApplicationContext thay vì tái sử dụng context đã có.

Test vẫn có thể đúng, nhưng suite khởi động chậm và cache bị phân mảnh.

### Lỗi 2: equals/hashCode bỏ qua dữ liệu cấu hình

Giả sử customizer chứa tenantId nhưng equals() chỉ kiểm tra class:

~~~~java
@Override
public boolean equals(Object other) {
    return other instanceof TenantContextCustomizer;
}

@Override
public int hashCode() {
    return TenantContextCustomizer.class.hashCode();
}
~~~~

Khi đó customizer north và south bị xem là bằng nhau.

Hệ quả:

- Test north tạo context với property test.tenant-id=north.
- Test south có cache key bị xem là tương đương.
- Spring có thể trả lại context north cho test south.
- Test south nhìn thấy bean đã được tạo với tenant north.

Đây là lỗi nghiêm trọng hơn cache miss vì test có thể chạy trên cấu hình sai nhưng không nhất thiết thất bại ngay.

### Quy tắc thiết kế

equals() và hashCode() phải dựa trên toàn bộ state bất biến ảnh hưởng đến context được tạo ra.

| State của customizer | Có nên tham gia equality? | Lý do |
| --- | --- | --- |
| Tenant ID được đưa vào Environment | Có | Làm thay đổi property và bean trong context. |
| Danh sách profile hoặc feature flag được áp dụng | Có | Làm thay đổi cấu hình context. |
| Tên bean hoặc bean definition được đăng ký | Có | Làm thay đổi nội dung context. |
| Giá trị chỉ dùng để ghi log, không ảnh hưởng context | Không nhất thiết | Không làm thay đổi context semantics. |
| Timestamp tạo customizer | Không | Làm mọi instance khác nhau và phá cache. |
| Test class chỉ dùng để ghi log | Không nhất thiết | Có thể làm cache bị phân mảnh nếu cấu hình thực tế giống nhau. |
| Class/type được dùng để đăng ký bean khác nhau | Có | Thay đổi bean graph trong context. |

Một customizer nên là immutable value object. Không nên thay đổi tenantId, property map hoặc danh sách bean sau khi đã tạo customizer, vì hash code có thể thay đổi trong khi object đang là một phần của cache key.

## 8. Kiểm tra equality trực tiếp

Có thể viết unit test cho customizer để xác nhận semantics của equality:

~~~~java
class TenantContextCustomizerTest {

    @Test
    void customizersForSameTenantAreEqual() {
        var first = new TenantContextCustomizer("north");
        var second = new TenantContextCustomizer("north");

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }

    @Test
    void customizersForDifferentTenantsAreNotEqual() {
        var north = new TenantContextCustomizer("north");
        var south = new TenantContextCustomizer("south");

        assertThat(north).isNotEqualTo(south);
    }
}
~~~~

Đây là unit test nhỏ nhưng hữu ích vì equality sai có thể gây lỗi cache khó phát hiện. Nó không thay thế test tích hợp chứng minh context thực sự nhận property phù hợp.

Cũng có thể kiểm tra factory:

~~~~java
@Test
void factoryCreatesCustomizerFromTestAnnotation() {
    ContextCustomizerFactory factory =
            new TenantContextCustomizerFactory();

    ContextCustomizer first = factory.createContextCustomizer(
            NorthTenantTest.class,
            List.of()
    );

    ContextCustomizer second = factory.createContextCustomizer(
            AnotherNorthTenantTest.class,
            List.of()
    );

    assertThat(first).isEqualTo(second);
}
~~~~

Ví dụ giả định hai test class có cùng annotation tenant và các metadata khác không ảnh hưởng tới customizer. Mục tiêu là xác nhận factory tạo customizer theo giá trị cấu hình, không theo object identity của test class.

## 9. Tại sao không nên đưa test class vào equality một cách tùy tiện?

Một số factory có thể muốn giữ Class<?> testClass trong customizer để đọc annotation hoặc ghi log. Điều đó không tự động có nghĩa class phải tham gia equals/hashCode.

Nếu hai test class có cùng cấu hình context, Spring có thể tái sử dụng context giữa chúng. Nếu customizer equality bao gồm testClass, mỗi test class sẽ tạo một cache key riêng dù context thực tế giống nhau.

Ví dụ:

- NorthTenantTest và AnotherNorthTenantTest đều khai báo @TestTenant("north").
- Factory tạo hai customizer cùng tenantId.
- Nếu equality chỉ dựa trên tenantId, chúng có thể dùng chung context.
- Nếu equality dựa cả testClass, cache bị tách thành hai entry.

Chỉ đưa test class vào equality khi context thực sự được cấu hình khác nhau theo class đó. Nếu class chỉ là nguồn metadata nhưng kết quả tùy chỉnh cuối cùng giống nhau, equality nên dựa trên kết quả cấu hình.

Nguyên tắc này cũng áp dụng cho annotation instance. Không dùng identity của annotation proxy làm equality nếu giá trị annotation mới là thứ quyết định cấu hình.

## 10. ContextCustomizerFactory và @DynamicPropertySource

@DynamicPropertySource là một ví dụ thực tế về cơ chế customizer trong Spring TestContext Framework. Spring phát hiện các phương thức được đánh dấu @DynamicPropertySource và sử dụng customizer để thêm các dynamic property vào Environment khi context được chuẩn bị.

Ví dụ:

~~~~java
@Testcontainers
@SpringBootTest
abstract class AbstractDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~~

Các supplier có thể trả về giá trị chỉ biết sau khi container khởi động, chẳng hạn JDBC URL có port động. Dynamic property được đưa vào Environment trước khi bean datasource cần giá trị đó được tạo.

Điểm cần chú ý là cache key không phải lúc nào cũng phản ánh mọi giá trị runtime mà supplier sẽ trả về. Với customizer của @DynamicPropertySource, equality dựa trên tập hợp các phương thức dynamic property được phát hiện. Nếu cùng một phương thức được kế thừa nhưng trả về giá trị khác nhau tùy subclass hoặc resource lifecycle, hai test class có thể bị xem là có cấu hình customizer tương đương dù giá trị động thay đổi.

Ví dụ, một superclass có @DynamicPropertySource method dùng container được khởi động lại hoặc thay đổi theo subclass. Nếu cache giữ context cũ, datasource có thể tiếp tục dùng URL cũ.

Khi dynamic property thay đổi giữa các subclass, Spring khuyến nghị dùng @DirtiesContext ở phạm vi phù hợp để context được loại khỏi cache và tạo lại. Cũng có thể thiết kế cấu hình để giá trị động ổn định trong suốt vòng đời context được chia sẻ.

Đừng mặc định rằng mọi supplier được đánh giá lại sẽ làm bean đã tạo trong context thay đổi theo. Environment có thể trả giá trị mới, nhưng singleton bean như DataSource đã được khởi tạo trước đó có thể vẫn giữ cấu hình cũ.

## 11. So sánh ContextCustomizer với các cơ chế cấu hình khác

Spring Test có nhiều điểm mở rộng. Hãy chọn cơ chế đơn giản nhất phù hợp với nhu cầu.

| Cơ chế | Dùng khi | Có liên quan đến context cache key? |
| --- | --- | --- |
| @TestPropertySource | Test class cần property tĩnh khai báo trực tiếp. | Các property source được đưa vào MergedContextConfiguration. |
| @DynamicPropertySource | Property chỉ có sau khi resource khởi động, như port container. | Dynamic property customizer tham gia vào context customizers. |
| @ContextConfiguration(initializers = ...) | Cần ApplicationContextInitializer áp dụng cấu hình khi context được tạo. | Initializer classes là một phần của merged configuration. |
| @TestConfiguration / @Import | Cần khai báo bean test rõ ràng trong cấu hình. | Configuration classes/imports ảnh hưởng merged configuration. |
| @MockitoBean hoặc bean override | Cần thay bean trong context bằng mock hoặc test bean. | Bean override context customizer tham gia cache key. |
| ContextCustomizerFactory | Cần đọc metadata của test class và tạo tùy chỉnh context có thể tái sử dụng qua một SPI. | ContextCustomizer do factory tạo là một phần của cache key. |

### Khi nên dùng @TestPropertySource

Nếu mọi test đều cần một property cố định:

    @TestPropertySource(properties = "feature.search.enabled=false")

thường dễ hiểu hơn một custom annotation và factory riêng.

### Khi nên dùng @DynamicPropertySource

Nếu test cần port hoặc URL do container cấp, @DynamicPropertySource là API có sẵn và thường không cần tự viết factory.

### Khi nên dùng ApplicationContextInitializer

Nếu cần thao tác trên context theo một class initializer được khai báo trực tiếp trong @ContextConfiguration, ApplicationContextInitializer có thể phù hợp. Cơ chế này hữu ích khi cấu hình được biết ở cấp class và không cần một SPI discovery theo annotation tùy chỉnh.

### Khi nên dùng ContextCustomizerFactory

Dùng factory khi muốn đóng gói quy ước cấu hình cho nhiều test class, ví dụ:

- Annotation test chọn tenant, region hoặc feature set.
- Tự động đăng ký bean dựa trên metadata của test class.
- Tích hợp thư viện test support cần điều chỉnh context trước refresh.
- Tạo cấu hình có thể được chia sẻ giữa nhiều module mà không yêu cầu mỗi test class viết initializer riêng.

Không nên tạo factory chỉ để thay thế một property đơn giản đã được hỗ trợ bởi @TestPropertySource.

## 12. ContextCustomizer và bean override

Các cơ chế thay thế bean trong Spring Test cũng có thể sử dụng context customizer để mô tả bean override và góp phần vào cache key.

Ví dụ một test cần thay PaymentGateway bằng mock. Annotation bean override xác định bean nào được thay và kiểu override nào được áp dụng. Thông tin override phải tham gia cấu hình đã hợp nhất, vì context có mock gateway khác với context có implementation thật.

Điều này cho thấy cache key không chỉ quan tâm property. Bất kỳ customization nào làm thay đổi bean graph hoặc behavior của context đều cần được biểu diễn bằng equality đúng.

Nếu customizer đăng ký bean khác nhau nhưng equals/hashCode bỏ qua loại bean hoặc qualifier, Spring có thể tái sử dụng context với bean override sai. Ngược lại, nếu equality đưa vào thông tin không ảnh hưởng bean graph, cache có thể bị phân mảnh.

Khi tích hợp bean override, mock framework hoặc test support library, hãy xem cách thư viện biểu diễn metadata trong customizer và cách nó xác định equality. Không tự tạo một customizer thứ hai để làm cùng việc nếu Spring đã cung cấp cơ chế phù hợp.

## 13. Factory discovery và thứ tự

ContextCustomizerFactory được phát hiện qua SpringFactoriesLoader. File metadata META-INF/spring.factories có thể chứa nhiều implementation cho cùng key:

~~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TenantContextCustomizerFactory,\
com.example.test.FeatureFlagContextCustomizerFactory
~~~~

Các factory nên độc lập nếu có thể. Nếu hai factory cùng sửa một property source hoặc đăng ký cùng bean name, kết quả có thể phụ thuộc thứ tự áp dụng.

Khi thứ tự có ý nghĩa, triển khai Ordered hoặc dùng @Order để khai báo ưu tiên theo cơ chế Spring hỗ trợ cho factory. Tuy nhiên, thiết kế tốt hơn thường là tránh để hai customizer tranh chấp cùng một phần cấu hình.

Cần phân biệt thứ tự của factory và thứ tự callback của TestExecutionListener. ContextCustomizerFactory tham gia giai đoạn bootstrap cấu hình context; TestExecutionListener tham gia vòng đời thực thi test method/class. Hai SPI phục vụ hai giai đoạn khác nhau.

## 14. Tác động tới cache hit, cache miss và hiệu năng

Context cache giúp Spring tránh tạo lại ApplicationContext có cấu hình tương đương. Việc customizer tham gia cache key có thể làm tăng hoặc giảm số cache hit.

### Cache hit

Hai test có cùng merged configuration và các customizer bằng nhau. Spring có thể trả lại ApplicationContext đã được tạo trước đó.

Ví dụ:
- Hai test class cùng dùng TenantTestConfig.
- Cả hai cùng khai báo @TestTenant("north").
- TenantContextCustomizer equality dựa trên tenantId.
- Các thành phần cấu hình khác tương đương.

Hai test có thể chia sẻ context north.

### Cache miss

Cấu hình khác nhau hoặc customizer không bằng nhau. Spring tạo context mới.

Ví dụ:
- Một test dùng tenant north.
- Một test dùng tenant south.
- Customizer equality dựa trên tenantId.

Spring cần context riêng vì property và bean đã được cấu hình khác nhau.

### Cache miss ngoài ý muốn

Customizer không override equals/hashCode hoặc đưa timestamp/random value vào equality. Mỗi lần bootstrap tạo cache key khác dù context semantics giống nhau.

Hệ quả có thể là:
- Thời gian suite tăng.
- Nhiều ApplicationContext được tạo.
- Nhiều connection pool hoặc resource được mở.
- Cache nhanh đạt giới hạn và loại context cũ.
- Test chạy chậm hơn mà không có lợi ích về tính cô lập.

### Cache collision về semantics

Customizer bỏ qua một giá trị thực sự ảnh hưởng context. Hai cấu hình khác nhau bị xem là bằng nhau và Spring có thể tái sử dụng context không phù hợp.

Đây là lý do equality phải vừa đủ: không bỏ sót state ảnh hưởng context, cũng không đưa vào state không liên quan.

## 15. Theo dõi context cache

Spring TestContext Framework có log cho context cache. Có thể bật mức DEBUG để xem cache statistics và các lần truy cập context:

    logging.level.org.springframework.test.context.cache=DEBUG

Log giúp nhận biết:
- Cache hit và cache miss.
- Số context đang được giữ.
- Context bị loại khỏi cache.
- Suite tạo nhiều context hơn dự kiến.

Nếu một test suite có số lượng context tăng bất thường, hãy kiểm tra:
- Test class có cùng cấu hình nhưng customizer equality khác nhau không?
- Có timestamp hoặc random value trong customizer không?
- Annotation attribute có được chuẩn hóa nhất quán không?
- Các test có thật sự cần các context khác nhau không?
- @DirtiesContext có được dùng quá rộng không?
- Dynamic property có thay đổi trong khi cache vẫn giữ context cũ không?

Đừng cố tăng cache size trước khi hiểu vì sao có nhiều cache key. Tăng giới hạn có thể che giấu customizer equality sai và làm tiêu tốn tài nguyên hơn.

## 16. ContextCustomizer và AOT

Context customization là một phần của quá trình chuẩn bị ApplicationContext. Khi dự án sử dụng AOT test processing hoặc native image, các thay đổi cần thiết cho context phải phù hợp với cơ chế AOT mà phiên bản Spring hỗ trợ.

Một customizer phụ thuộc vào metadata ổn định của test class, chẳng hạn annotation value, thường dễ dự đoán hơn customizer đọc environment bên ngoài hoặc tạo dữ liệu ngẫu nhiên trong lúc bootstrap.

Khi thiết kế cho môi trường AOT:

- Giữ customization dựa trên metadata test rõ ràng và ổn định.
- Không dùng thời điểm hiện tại hoặc random value làm một phần cấu hình context nếu không có cơ chế AOT tương ứng.
- Đảm bảo class factory và customizer nằm trong classpath mà test AOT processing có thể phát hiện.
- Xác nhận các bean definition hoặc property source được tạo có thể được xử lý trong mô hình AOT của phiên bản Spring đang dùng.
- Chạy test trong chính cấu hình AOT/native mục tiêu, không suy ra chỉ từ việc JVM test thông thường thành công.

AOT không làm thay đổi yêu cầu cơ bản về equality của customizer đối với context cache. Nếu customizer ảnh hưởng cấu hình context, state đó vẫn cần được mô tả ổn định và chính xác.

## 17. Những lỗi thường gặp

**Không override equals() và hashCode().**

Mỗi lần factory tạo một customizer mới, object identity có thể làm cache key khác nhau. Hãy dùng value equality dựa trên state ảnh hưởng context.

**equals() bỏ qua property hoặc bean khác nhau.**

Hai test có cấu hình tenant/feature khác nhau có thể bị xem là bằng nhau. Context cache có thể trả về context được cấu hình cho test khác. Đưa mọi context-affecting value vào equality.

**Đưa timestamp hoặc random ID vào customizer.**

Giá trị thay đổi theo lần tạo làm cache miss liên tục. Chỉ dùng state cấu hình ổn định, có ý nghĩa với context.

**Đưa toàn bộ test class vào equality dù context giống nhau.**

Cache bị tách theo class dù cấu hình thực tế giống nhau. Equality nên phản ánh kết quả customization, không phải nguồn metadata nếu nguồn đó không làm thay đổi context.

**Tạo property source sau khi context đã refresh.**

Bean có thể đã được khởi tạo với giá trị cũ. Thực hiện customization trước refresh.

**Dùng ContextCustomizerFactory cho property tĩnh đơn giản.**

Một factory riêng làm tăng độ phức tạp và tạo thêm thành phần tham gia cache key. Ưu tiên @TestPropertySource hoặc @DynamicPropertySource nếu đã đáp ứng nhu cầu.

**Nhầm ContextCustomizerFactory với TestExecutionListener.**

Factory/customizer ảnh hưởng quá trình tạo context; listener nhận callback trong vòng đời test. Dùng đúng SPI theo thời điểm cần can thiệp.

**Dynamic property thay đổi nhưng context vẫn được tái sử dụng.**

Nếu customizer equality không phản ánh giá trị động mới, context cũ có thể giữ datasource hoặc bean đã được tạo với URL cũ. Dùng @DirtiesContext khi cấu hình động thay đổi giữa các test class hoặc thiết kế resource lifecycle ổn định.

**Ghi đè metadata spring.factories của thư viện khác.**

Một file metadata mới có thể làm mất factory cần thiết nếu quá trình đóng gói không merge entry. Kiểm tra resource cuối cùng trong test runtime classpath.

## 18. Quy trình triển khai một ContextCustomizerFactory

Khi cần một cơ chế tùy chỉnh context dùng lại ở nhiều test class, triển khai theo trình tự:

1. Xác định chính xác phần ApplicationContext cần thay đổi.
2. Kiểm tra @TestPropertySource, @DynamicPropertySource, @TestConfiguration hoặc ApplicationContextInitializer có đáp ứng sẵn không.
3. Nếu cần SPI, định nghĩa annotation test với retention runtime và các attribute bất biến.
4. Viết ContextCustomizerFactory để đọc metadata và tạo customizer.
5. Viết ContextCustomizer để thay đổi Environment hoặc đăng ký bean definition trước refresh.
6. Implement equals() và hashCode() trên toàn bộ state ảnh hưởng context.
7. Đăng ký factory trong META-INF/spring.factories.
8. Viết unit test cho factory và equality của customizer.
9. Viết integration test xác nhận context nhận đúng property/bean.
10. Dùng hai test class có cùng cấu hình để xác nhận khả năng cache reuse.
11. Dùng hai test class có cấu hình khác nhau để xác nhận context không bị dùng chung sai.
12. Bật cache DEBUG log nếu cần chẩn đoán số lần tạo context.

Một customizer nên có constructor nhận state rõ ràng, field final, không giữ mutable object bên ngoài và không thực hiện side effect trong equals/hashCode.

## 19. Mẫu kiểm thử cache behavior

Có thể dùng hai test class có cùng cấu hình tenant để kiểm tra equality và khả năng tái sử dụng context. Ví dụ:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class FirstNorthTenantTest {
    @Autowired ApplicationContext context;
}

@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("north")
class SecondNorthTenantTest {
    @Autowired ApplicationContext context;
}
~~~~

Nếu các thành phần cấu hình khác tương đương, Spring có thể tái sử dụng context. Trong một test chuyên kiểm tra cache, có thể so sánh identity của context được inject:

~~~~java
assertThat(firstContext).isSameAs(secondContext);
~~~~

Đối với tenant khác:

~~~~java
@SpringJUnitConfig(TenantTestConfig.class)
@TestTenant("south")
class SouthTenantTest {
    @Autowired ApplicationContext context;
}
~~~~

Context south cần khác context north nếu tenant property làm thay đổi bean graph hoặc cấu hình context:

~~~~java
assertThat(northContext).isNotSameAs(southContext);
~~~~

Những assertion này chỉ phù hợp trong test infrastructure chuyên kiểm tra context cache. Không nên làm mọi test nghiệp vụ phụ thuộc vào thứ tự chạy hoặc chia sẻ context giữa test class chỉ để so sánh identity. Nếu kiểm tra cache, hãy thiết kế test có kiểm soát và tránh để các test khác làm bẩn cache state.

## Kết luận

ContextCustomizerFactory là SPI để tạo ContextCustomizer dựa trên metadata của test class và cấu hình Spring Test. ContextCustomizer thay đổi ConfigurableApplicationContext trước refresh. Các customizer được đưa vào MergedContextConfiguration, đối tượng đóng vai trò khóa của context cache.

Vì vậy, equals() và hashCode() của customizer phải phản ánh mọi giá trị làm thay đổi ApplicationContext. Equality quá rộng có thể khiến Spring tái sử dụng nhầm context; equality theo identity hoặc chứa state ngẫu nhiên có thể làm cache miss không cần thiết.

Hãy ưu tiên các cơ chế cấu hình có sẵn khi chúng đáp ứng nhu cầu. Khi cần một test infrastructure SPI dùng lại, giữ customizer immutable, đăng ký factory đúng cách, kiểm tra equality và xác nhận cả trường hợp cache reuse lẫn context phải được tạo riêng.
