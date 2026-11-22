# Cô lập context, property source và trạng thái tĩnh giữa các ca kiểm thử

> **Chương:** Kiểm thử
> **Module:** `SPRING_CLOUD_CORE` — hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình bên ngoài và tương thích phiên bản với Spring Boot. Người học tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử, vận hành các abstraction chung.
> **Trọng tâm:** Một test có thể chạy đúng khi đứng riêng nhưng thất bại khi chạy cùng suite vì nó dùng lại ApplicationContext, thay đổi Environment, hoặc để lại trạng thái trong biến static và cache dùng chung. Bài học hướng dẫn nhận diện từng vòng đời, chọn cách cô lập phù hợp và dọn trạng thái có kiểm soát để test ổn định khi chạy tuần tự hoặc song song.

## 1. Vì sao test cần cô lập trạng thái?

Trong ứng dụng Spring Cloud, kết quả một ca kiểm thử có thể phụ thuộc vào nhiều lớp trạng thái:

- Bean singleton trong ApplicationContext.
- Property source và active profile trong Environment.
- Cache của Spring TestContext.
- Cache target của RefreshScope.
- Cache static của thư viện, ví dụ CachedRandomPropertySource.
- System property, Locale hoặc TimeZone của JVM.
- Database, registry, message broker, container và tài nguyên ngoài tiến trình.

Các trạng thái này có vòng đời khác nhau. Đóng một context không đồng nghĩa JVM được làm mới; xóa cache của một scope không đồng nghĩa property source được khôi phục; tạo một context mới không tự động xóa system property.

Ví dụ, test A thêm một PropertySource vào Environment. Test B dùng lại cùng context và đọc property đó, dù test B không hề khai báo giá trị. Trường hợp khác, test A ghi giá trị vào cache static; test B dùng cùng cache key và nhận kết quả do test A tạo ra.

Nếu không xác định đúng nơi giữ trạng thái, việc sửa test bằng cách đổi thứ tự chạy chỉ che giấu nguyên nhân. Test nên thiết lập dữ liệu đầu vào cần thiết, thực hiện assertion và khôi phục mọi trạng thái dùng chung mà nó đã thay đổi.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt vòng đời test method, bean, context, property source, scope cache và JVM static state.
2. Giải thích vì sao Spring TestContext tái sử dụng ApplicationContext.
3. Sử dụng @DirtiesContext đúng lúc và hiểu chi phí của nó.
4. Chọn ApplicationContextRunner cho kiểm thử cấu hình cô lập.
5. Thêm property theo từng test bằng TestPropertyValues, @TestPropertySource hoặc @DynamicPropertySource.
6. Khôi phục system property và static cache sau mỗi test.
7. Phân biệt refresh bean với khởi tạo lại toàn bộ context.
8. Nhận diện rủi ro khi chạy test song song.
9. Thiết kế quy trình setup, assertion và cleanup có thể lặp lại.

## 2. Nhận diện các lớp trạng thái và vòng đời

Trước khi chọn kỹ thuật cô lập, hãy xác định test đang thay đổi trạng thái ở đâu.

| Lớp trạng thái | Nơi lưu | Thường tồn tại đến khi nào? | Cách cô lập hoặc khôi phục |
| --- | --- | --- | --- |
| Biến local của test | Stack/frame của test | Kết thúc method | Không cần cleanup đặc biệt |
| Trường của test instance | Đối tượng test | Theo lifecycle của test framework | Dùng setup rõ ràng; không dựa vào thứ tự method |
| Bean singleton | Một ApplicationContext | Context đóng hoặc bean bị thay thế | Tạo context riêng hoặc dùng @DirtiesContext khi context bị làm bẩn |
| Environment / PropertySource | ApplicationContext hoặc Environment được chia sẻ | Theo vòng đời Environment | Dùng property riêng cho context; xóa source nếu đã tự thêm |
| Spring TestContext cache | Cache static trong JVM test | Trong test suite/process, có eviction hoặc shutdown | Thay đổi context key có chủ đích hoặc @DirtiesContext |
| RefreshScope target cache | Refresh scope của context | Đến khi target bị invalidate hoặc context đóng | RefreshScope.refresh(...) hoặc refreshAll() |
| Static cache / static field | Class loader/JVM | Đến khi xóa, class loader bị thu hồi hoặc JVM kết thúc | API reset chuyên dụng; cleanup và khóa đồng bộ |
| System properties | System.getProperties() của JVM | Đến khi bị sửa/xóa hoặc JVM kết thúc | Lưu giá trị cũ và khôi phục trong finally |
| Tài nguyên ngoài | Database, registry, broker, filesystem, container | Theo vòng đời tài nguyên | Tạo namespace/test data riêng và cleanup |

Không có một thao tác duy nhất làm sạch tất cả các lớp này. Chẳng hạn:

- @DirtiesContext loại context khỏi cache và đóng context đó, nhưng không xóa biến static tùy ý của ứng dụng.
- RefreshScope.refreshAll() xóa target cache của các bean thuộc refresh scope, nhưng không khởi động lại context.
- CachedRandomPropertySource.clearCache() xóa cache random tĩnh mà API đó quản lý, nhưng không thay đổi giá trị đã được bind vào các bean đang tồn tại.
- System.clearProperty() xóa system property, nhưng không tự cập nhật các bean đã đọc giá trị đó trước đó.

Khi điều tra một test thất thường, hãy ghi rõ: ai sở hữu trạng thái, trạng thái được tạo ở đâu, và thao tác nào có thể khôi phục nó?

## 3. Spring TestContext cache ApplicationContext như thế nào?

### 3.1. Cùng cấu hình có thể dùng chung context

Spring TestContext Framework cache một ApplicationContext sau lần tải đầu tiên. Các test tiếp theo có cùng cấu hình context sẽ dùng lại context đó trong cùng test suite và cùng tiến trình.

Điều này giúp suite chạy nhanh hơn vì Spring không phải tạo lại toàn bộ bean cho từng test class. Nhưng nó cũng có nghĩa singleton bean và Environment có thể được dùng chung giữa nhiều test.

Ví dụ:

```java
@SpringBootTest
class FirstIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void changesSharedState() {
        stateService.setValue("changed-by-first-test");
    }
}

@SpringBootTest
class SecondIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void expectsInitialState() {
        // Có thể nhận cùng bean/context mà FirstIntegrationTests đã dùng.
        assertThat(stateService.getValue()).isEqualTo("initial");
    }
}
```

Nếu hai class có cùng cấu hình context, test thứ hai có thể nhìn thấy trạng thái mà test thứ nhất để lại. Đây là lỗi isolation; không nên dựa vào việc test thứ hai tình cờ chạy trước.

### 3.2. Những yếu tố tạo cache key

Spring TestContext tạo cache key từ metadata dùng để tải context. Các thành phần chính gồm:

- locations và classes trong @ContextConfiguration;
- các ApplicationContextInitializer;
- context customizers, bao gồm @DynamicPropertySource và các bean override của test;
- ContextLoader;
- parent context trong @ContextHierarchy;
- active profiles trong @ActiveProfiles;
- descriptors và inline properties của @TestPropertySource;
- resource base path của @WebAppConfiguration.

Khi các metadata này giống nhau, hai test class có thể nhận cùng một context. Thêm một profile hoặc thay đổi test property source có thể tạo cache key khác và khiến Spring tải context khác.

Không nên thêm cấu hình giả chỉ để ép mỗi test dùng một context mới. Hãy dùng cache để giảm chi phí và chỉ cô lập lại context khi test thật sự thay đổi trạng thái không thể khôi phục an toàn.

### 3.3. Cache nằm trong JVM

Context cache là cache static trong tiến trình test. Nếu build tool fork JVM riêng cho từng test, cache không được chia sẻ giữa các process đó. Khi test chạy cùng một process, context cache có thể được tái sử dụng.

Tài liệu Spring Framework 6.2 mô tả mặc định tối đa 32 context và dùng chính sách LRU để loại context cũ khi vượt giới hạn. Có thể xem thống kê bằng cách đặt logger org.springframework.test.context.cache ở mức DEBUG.

Ví dụ cấu hình logging:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Log giúp quan sát số lần hit/miss, số context đang lưu và việc context bị loại khỏi cache. Khi suite tạo quá nhiều tổ hợp profile hoặc property, cache có thể bị churn và làm thời gian test tăng lên.

### 3.4. Cache context không phải cache bean nghiệp vụ

Context cache chỉ giữ và tái sử dụng container. Nó không tự reset dữ liệu bên trong bean sau mỗi method. Nếu một singleton giữ mutable state, test có thể ảnh hưởng test tiếp theo dù context được tái sử dụng đúng theo thiết kế.

Hãy ưu tiên:

- Dùng service stateless trong ứng dụng.
- Tạo dữ liệu test theo ID riêng.
- Dọn dữ liệu do test tạo ra.
- Không sửa singleton bean trong test nếu không cần.
- Nếu context đã bị thay đổi cấu trúc hoặc trạng thái không thể phục hồi, đánh dấu context dirty.

## 4. Dùng @DirtiesContext đúng mục đích

### 4.1. Annotation làm gì?

@DirtiesContext báo cho Spring TestContext rằng context đã bị thay đổi hoặc hỏng và cần đóng, đồng thời loại nó khỏi cache. Test tiếp theo cần cùng cấu hình sẽ phải tạo context mới.

Ví dụ dùng ở cấp class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void mutatesContextOwnedState() {
        stateService.setValue("temporary");
    }
}
```

Hoặc ở cấp method:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void testThatCorruptsContext() {
    // Thay đổi trạng thái singleton mà test khác không thể khôi phục an toàn.
}
```

Khi test kết thúc theo mode đã chọn, Spring đóng context và loại context khỏi cache. Test sau đó cần cùng cấu hình sẽ được cấp một context mới.

### 4.2. Khi nào nên dùng?

Dùng @DirtiesContext khi test:

- Thay đổi bean definition hoặc cấu trúc context.
- Thay đổi singleton bean theo cách không thể khôi phục.
- Thay đổi trạng thái nội bộ của context mà cleanup thông thường không thể làm sạch.
- Cần kiểm tra hành vi khởi tạo mới của container.

Không cần dùng chỉ vì một test thay đổi dữ liệu trong database, system property hoặc static cache. Hãy khôi phục trạng thái tại đúng nơi nó được lưu.

### 4.3. Chi phí và giới hạn

Đóng context có thể kéo theo việc đóng connection pool, client, listener, scheduler và các bean lifecycle khác. Context tiếp theo cần khởi tạo lại các thành phần này, làm test suite chậm hơn.

@DirtiesContext cũng không tự động:

- Xóa system property đã đặt.
- Xóa biến static của class ứng dụng.
- Xóa cache static của thư viện.
- Khôi phục file hoặc database đã sửa.
- Dừng tài nguyên ngoài không được context quản lý.

Vì vậy, hãy kết hợp với cleanup dành riêng cho trạng thái ngoài context. Không dùng @DirtiesContext như nút reset toàn JVM.

## 5. Tạo context nhỏ, mới cho từng tổ hợp bằng ApplicationContextRunner

### 5.1. Khi phù hợp

ApplicationContextRunner của Spring Boot phù hợp để kiểm tra auto-configuration hoặc một tập bean nhỏ với các tổ hợp property và user configuration khác nhau.

Mỗi lần gọi run(...) tạo context cho lần kiểm tra đó và đóng context sau callback. Nhờ vậy, test có thể diễn tả từng tổ hợp cấu hình mà không cần khởi động toàn bộ ứng dụng.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void createsFeatureWhenEnabled() {
        runner.withPropertyValues("feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getEnvironment()
                            .getProperty("feature.enabled"))
                            .isEqualTo("true");
                });
    }

    @Test
    void doesNotCreateFeatureWhenDisabled() {
        runner.withPropertyValues("feature.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(FeatureService.class)
                );
    }
}
```

Hai test mô tả hai Environment riêng. Không cần đổi system property toàn cục hoặc sửa context dùng chung để tạo ra hai trường hợp.

### 5.2. Kiểm tra auto-configuration cụ thể

Có thể đưa auto-configuration vào runner:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                AcmeClientAutoConfiguration.class
                        )
                );
```

Sau đó dùng withPropertyValues(...), withUserConfiguration(...) hoặc class loader phù hợp để kiểm tra các nhánh điều kiện. Đây là cách tốt để kiểm tra bean mặc định, bean do ứng dụng thay thế và điều kiện thiếu dependency.

### 5.3. Giới hạn

ApplicationContextRunner không thay thế mọi integration test. Nó không tự mô phỏng toàn bộ lifecycle của ứng dụng, web server thật, bootstrap, config server hoặc external registry. Dùng runner cho cấu hình và auto-configuration; dùng @SpringBootTest hoặc test chuyên biệt khi cần kiểm tra ứng dụng trong môi trường gần thực tế.

## 6. Cô lập property source trong từng test

### 6.1. Environment là tập PropertySource có thứ tự

Spring Environment tra cứu property qua danh sách PropertySource. Nếu nhiều nguồn có cùng key, nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị trả về.

Một ứng dụng có thể có property từ:

- command-line arguments;
- Java system properties;
- OS environment variables;
- application.properties hoặc application.yml;
- @PropertySource;
- property source được thêm bằng code;
- property source do Spring Cloud hoặc test framework cung cấp.

Khi test không nhận giá trị mong đợi, hãy kiểm tra effective value qua Environment thay vì chỉ nhìn vào một file cấu hình.

### 6.2. Dùng TestPropertyValues

Spring Boot cung cấp TestPropertyValues để thêm các cặp key/value vào ConfigurableEnvironment hoặc ConfigurableApplicationContext.

Ví dụ:

```java
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment environment = new MockEnvironment();

TestPropertyValues.of(
        "acme.client.enabled=true",
        "acme.client.timeout=2s"
).applyTo(environment);

assertThat(environment.getProperty("acme.client.enabled"))
        .isEqualTo("true");
```

Có thể dùng cách này trong test đơn vị hoặc initializer. Mỗi test nên dùng Environment riêng hoặc context riêng để property của test này không rò sang test khác.

### 6.3. Dùng @TestPropertySource cho integration test

Với Spring TestContext, có thể khai báo property riêng cho một test class:

```java
@SpringJUnitConfig(FeatureConfiguration.class)
@TestPropertySource(properties = {
        "feature.enabled=true",
        "feature.timeout=2s"
})
class FeatureEnabledIntegrationTests {
    // Assertions cho cấu hình bật.
}
```

Có thể dùng file property riêng bằng thuộc tính locations nếu muốn tách cấu hình dài khỏi annotation. @TestPropertySource là một phần metadata của context cache key, vì vậy các test có property source khác nhau có thể dùng context khác nhau.

Nếu test chỉ cần một vài giá trị tĩnh, đây thường là lựa chọn dễ đọc. Nếu giá trị chỉ có sau khi một tài nguyên ngoài khởi động, dùng dynamic property.

### 6.4. Dùng @DynamicPropertySource cho tài nguyên có địa chỉ động

@DynamicPropertySource cho phép đăng ký property bằng Supplier. Supplier chỉ được gọi khi property được phân giải. Đây là cách phổ biến để đưa host, port hoặc URL của Testcontainers vào Environment.

Ví dụ minh họa:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class RedisIntegrationTests {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine").withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port", redis::getFirstMappedPort);
    }
}
```

Testcontainers extension quản lý vòng đời container. Dynamic property lấy host và mapped port từ container đang chạy, không hard-code port ngẫu nhiên.

Dynamic properties có precedence cao hơn property từ @TestPropertySource, OS environment, Java system properties và property source do ứng dụng khai báo bằng @PropertySource hoặc thêm bằng code. Điều này hữu ích khi cần ghi đè chọn lọc một giá trị do test cung cấp.

### 6.5. Lưu ý khi dùng DynamicPropertySource trong base class

Nếu một base test class có @DynamicPropertySource và supplier trả về giá trị khác nhau giữa các subclass, context cache có thể khiến subclass dùng lại context cũ. Spring Framework khuyến nghị cân nhắc @DirtiesContext trên base class để mỗi subclass nhận context phù hợp với dynamic properties của nó.

Hãy kiểm tra kỹ tình huống này khi mỗi subclass dùng một container hoặc endpoint khác nhau. Chỉ thay đổi giá trị Supplier không đảm bảo một context đã tạo sẽ tự khởi tạo lại bean để dùng giá trị mới.

## 7. Cô lập static state và system properties

### 7.1. Static state sống ngoài ApplicationContext

Các biến static được chia sẻ giữa những test chạy cùng class loader/JVM. Chúng có thể tồn tại sau khi một context đóng và được mở lại.

Ví dụ:

```java
public final class GlobalFlags {

    private static boolean enabled;

    private GlobalFlags() {
    }

    public static boolean isEnabled() {
        return enabled;
    }

    public static void setEnabled(boolean value) {
        enabled = value;
    }
}
```

Nếu một test gọi GlobalFlags.setEnabled(true) nhưng không khôi phục trạng thái, test khác có thể bắt đầu với giá trị true. @DirtiesContext không tự động reset field này.

Tốt nhất là tránh static mutable state trong code ứng dụng. Nếu không thể loại bỏ, cung cấp API reset rõ ràng hoặc lưu giá trị cũ để khôi phục trong cleanup.

### 7.2. CachedRandomPropertySource

Spring Cloud Context có CachedRandomPropertySource để cache giá trị random theo key. Trong các phiên bản có API tương ứng, CachedRandomPropertySource.clearCache() xóa cache static mà property source quản lý.

Có thể dùng trong test:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.cloud.util.random.CachedRandomPropertySource;

@ResourceLock("cached-random-property-source")
class CachedRandomConfigurationTests {

    @BeforeEach
    void clearBeforeTest() {
        CachedRandomPropertySource.clearCache();
    }

    @AfterEach
    void clearAfterTest() {
        CachedRandomPropertySource.clearCache();
    }
}
```

Kiểm tra package và sự hiện diện của API trong đúng phiên bản Spring Cloud Context đang dùng. Không giả định mọi release có cùng chữ ký hoặc hành vi.

Việc xóa cache là thao tác toàn cục đối với cache đó. Nếu test khác đang dùng cùng cache, nó có thể bị ảnh hưởng. Khi chạy song song, hãy dùng cùng một JUnit ResourceLock cho mọi test truy cập cache này hoặc tắt parallel execution cho nhóm test liên quan. Có thể dùng cache key riêng cho từng test khi mục tiêu chỉ là tránh trùng dữ liệu.

Lưu ý: xóa cache không thay đổi giá trị đã được inject vào field hoặc bind vào bean trước đó. Nếu cần kiểm tra giá trị mới sau khi clear, hãy đọc lại property trong một lần phân giải mới hoặc tạo context/bean mới theo đúng mục tiêu test.

### 7.3. System properties cần được khôi phục

System property là trạng thái của JVM. Nếu test gọi System.setProperty, hãy lưu giá trị cũ và khôi phục chính xác trong finally:

```java
@Test
void readsSystemProperty() {
    String key = "acme.test.mode";
    String previous = System.getProperty(key);

    try {
        System.setProperty(key, "isolated");
        assertThat(System.getProperty(key)).isEqualTo("isolated");
    }
    finally {
        if (previous == null) {
            System.clearProperty(key);
        }
        else {
            System.setProperty(key, previous);
        }
    }
}
```

Không chỉ gọi System.clearProperty(key) ở cleanup nếu property vốn đã tồn tại trước test. Làm vậy sẽ xóa cấu hình do môi trường test hoặc build tool cung cấp.

Nếu property được đọc lúc context khởi tạo, hãy bảo đảm test context được tạo sau khi set property và không được tái sử dụng từ cache với giá trị đã bind trước đó. Với cấu hình riêng cho một test, @TestPropertySource, @DynamicPropertySource hoặc ApplicationContextRunner thường dễ kiểm soát hơn thay đổi system property.

### 7.4. Các trạng thái JVM khác

Các API toàn cục khác cũng cần được khôi phục nếu test thay đổi chúng:

- Locale.setDefault(...);
- TimeZone.setDefault(...);
- system properties;
- default uncaught exception handler;
- thread context class loader;
- static singleton hoặc registry tự tạo của ứng dụng.

Lưu giá trị cũ, thay đổi trong phạm vi ngắn và khôi phục bằng finally hoặc callback cleanup. Không giả định một test class chạy trong JVM mới.

## 8. Phân biệt refresh scope với tạo lại ApplicationContext

### 8.1. RefreshScope giữ cache target của bean

@RefreshScope tạo lazy proxy cho bean. Target bean được khởi tạo khi proxy được sử dụng và được giữ trong cache của scope. Khi cache entry bị invalidate, lần gọi tiếp theo sẽ tạo target mới.

Spring Cloud cung cấp RefreshScope.refresh(String) để refresh một bean theo tên và RefreshScope.refreshAll() để xóa cache target của toàn bộ bean trong scope.

Ví dụ:

```java
RefreshScope refreshScope = context.getBean(RefreshScope.class);

// Tên là bean name được đăng ký trong ApplicationContext.
refreshScope.refresh("remoteClient");
```

Sau khi refresh, target mới được tạo ở lần gọi tiếp theo qua proxy. Context và các singleton không thuộc refresh scope vẫn còn nguyên.

### 8.2. Refresh scope không thay thế @DirtiesContext

Hai thao tác có mục tiêu khác nhau:

| Thao tác | Phạm vi | Tác dụng |
| --- | --- | --- |
| RefreshScope.refresh("beanName") | Một bean refresh-scoped | Invalidate target cache của bean đó |
| RefreshScope.refreshAll() | Tất cả bean trong refresh scope | Invalidate các target cache của scope |
| ContextRefresher.refresh() | Environment và refresh scope theo cơ chế ContextRefresher | Cập nhật Environment rồi refresh scope |
| @DirtiesContext | Toàn ApplicationContext | Đóng context và loại khỏi TestContext cache |

Nếu test chỉ cần xác minh bean refresh-scoped được tạo lại, dùng RefreshScope. Nếu test đã làm hỏng context hoặc thay đổi cấu trúc container, dùng @DirtiesContext.

### 8.3. Property thay đổi và bean được bind lại

Refresh bean không tự động xóa static cache của thư viện. Tương tự, đổi Environment không đảm bảo mọi bean singleton được bind lại.

Khi test cấu hình refresh:

1. Thiết lập property ban đầu.
2. Tạo context và gọi bean để tạo target.
3. Thay đổi property source theo cách test đang kiểm chứng.
4. Phát tín hiệu refresh hoặc dùng ContextRefresher phù hợp.
5. Gọi lại proxy để target được tạo lại.
6. Xác nhận bean mới đọc giá trị mới.
7. Cleanup property source và tài nguyên test.

Đừng dùng RefreshScope.refreshAll() để sửa lỗi do system property hoặc static cache còn sót lại. Hãy cleanup đúng lớp trạng thái đã thay đổi.

## 9. Chạy test song song và trạng thái dùng chung

### 9.1. Vì sao parallel test dễ gây race condition?

Hai test song song có thể cùng thay đổi một static field, system property, cache key, file hoặc database record. Dù mỗi test đúng khi chạy riêng, chúng có thể ghi đè dữ liệu của nhau khi chạy đồng thời.

Ví dụ:

- Test A đặt feature.enabled=true.
- Test B đặt feature.enabled=false.
- Cả hai cùng đọc system property.
- Kết quả phụ thuộc thời điểm set/get/cleanup.

Tương tự, test A gọi CachedRandomPropertySource.clearCache() trong lúc test B đang phân giải cùng cache key.

### 9.2. Khi nào không nên chạy song song?

Spring Framework cảnh báo không nên chạy song song những test sử dụng @DirtiesContext, bean override như @MockitoBean/@MockitoSpyBean, hoặc thay đổi trạng thái hệ thống dùng chung như database, broker hay filesystem. Những test cùng sửa static cache hoặc system property cũng cần đồng bộ riêng.

Nếu gặp lỗi context đã bị đóng hoặc không còn active trong lúc test đang chạy, hãy kiểm tra xem một thread khác có vừa loại context khỏi cache bằng @DirtiesContext hoặc eviction hay không.

### 9.3. Dùng ResourceLock khi chia sẻ trạng thái có chủ đích

JUnit Jupiter cung cấp @ResourceLock để các test khai báo cùng tên tài nguyên được đồng bộ với nhau khi chạy song song.

Ví dụ:

```java
@ResourceLock("system-property:acme.test.mode")
class SystemPropertyTests {
    // Các test trong nhóm cùng thay đổi property này.
}
```

Tất cả test có thể đụng tới cùng tài nguyên phải dùng chung tên lock. Một test không khai báo lock vẫn có thể gây race condition. ResourceLock chỉ điều phối các test trong cùng JUnit execution; nó không khóa một process bên ngoài hoặc test runner khác.

Nếu một nhóm test sửa nhiều tài nguyên toàn cục, cân nhắc tắt parallel execution cho nhóm đó hoặc chạy riêng trong một suite tuần tự.

## 10. Mẫu setup và cleanup có thể lặp lại

Một test tốt có ba pha rõ ràng:

1. **Setup:** tạo dữ liệu riêng, property source riêng, context hoặc tài nguyên ngoài cần thiết.
2. **Exercise và assertion:** thực hiện hành vi đang kiểm tra và xác minh kết quả.
3. **Cleanup:** khôi phục trạng thái đã thay đổi, đóng tài nguyên và xóa dữ liệu do test tạo.

Ví dụ khung JUnit:

```java
class IsolatedEnvironmentTests {

    private ConfigurableEnvironment environment;
    private String previousMode;

    @BeforeEach
    void setUp() {
        environment = new StandardEnvironment();
        previousMode = System.getProperty("acme.mode");
    }

    @AfterEach
    void tearDown() {
        if (previousMode == null) {
            System.clearProperty("acme.mode");
        }
        else {
            System.setProperty("acme.mode", previousMode);
        }
    }

    @Test
    void testUsesItsOwnEnvironment() {
        TestPropertyValues.of("acme.mode=test")
                .applyTo(environment);

        assertThat(environment.getProperty("acme.mode"))
                .isEqualTo("test");
    }
}
```

Environment được tạo mới trong setup nên property của test không đi vào context dùng chung. System property được lưu và khôi phục đúng trạng thái trước đó.

Với tài nguyên ngoài, ưu tiên lifecycle API của test framework hoặc container library. Cleanup nên chạy ngay cả khi assertion thất bại; dùng try/finally, @AfterEach, @AfterAll hoặc extension tương ứng.

## 11. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Test chạy riêng thì pass, chạy cả suite thì fail | Bean singleton hoặc static state bị test trước thay đổi | Xác định nơi giữ trạng thái; thêm cleanup hoặc context riêng |
| @SpringBootTest nhận property cũ | Context được tái sử dụng từ TestContext cache | Kiểm tra cache key, property metadata và dynamic supplier |
| @DirtiesContext vẫn không reset giá trị random | Cache random là static state ngoài context | Dùng API clear cache đúng phiên bản và đồng bộ test truy cập |
| Test A ảnh hưởng test B dù context đã đóng | System property hoặc static field còn tồn tại | Lưu/khôi phục giá trị cũ trong finally |
| Testcontainers có port mới nhưng bean dùng port cũ | Dynamic property supplier thay đổi nhưng context cũ được reuse | Tạo context phù hợp cho từng resource hoặc dùng @DirtiesContext khi cần |
| Refresh bean nhưng giá trị vẫn cũ | Bean không thuộc refresh scope, property source chưa đổi hoặc cache tĩnh vẫn giữ giá trị | Kiểm tra scope, Environment và static cache riêng |
| Test chạy song song thất bại ngẫu nhiên | Nhiều test cùng sửa shared resource | Dùng ResourceLock, namespace riêng hoặc tuần tự hóa |
| Context khởi tạo quá nhiều lần | Quá nhiều context key khác nhau hoặc dùng @DirtiesContext rộng | Xem log cache và gom test có cấu hình chung |
| Test đọc nhầm property source | Thứ tự ưu tiên nguồn không như dự kiến | Kiểm tra Environment và danh sách PropertySources |
| Cleanup xóa cấu hình có sẵn | Chỉ clear system property mà không khôi phục giá trị trước test | Lưu giá trị cũ và phục hồi chính xác |

## 12. Quy trình chẩn đoán test bị rò trạng thái

Khi một test thất bại phụ thuộc thứ tự chạy, hãy thực hiện lần lượt:

1. Chạy test lỗi riêng để xác nhận baseline.
2. Chạy test lỗi sau test nghi ngờ đã làm thay đổi trạng thái.
3. Xác định hai test có dùng chung cache key của ApplicationContext không.
4. Kiểm tra bean singleton nào có mutable state.
5. Đọc Environment và liệt kê property source theo thứ tự ưu tiên.
6. Tìm system property hoặc biến static được thay đổi.
7. Kiểm tra cache riêng của thư viện như CachedRandomPropertySource hoặc RefreshScope.
8. Kiểm tra tài nguyên ngoài có dùng chung database/schema/topic/queue/file không.
9. Thêm cleanup tại đúng nơi lưu trạng thái.
10. Chỉ dùng @DirtiesContext nếu context thật sự bị làm bẩn.
11. Chạy lại theo thứ tự khác và bật parallel execution nếu suite có yêu cầu.
12. Nếu lỗi chỉ xuất hiện khi parallel, đồng bộ tài nguyên dùng chung hoặc tách test khỏi nhóm parallel.

Một cách hữu ích là ghi log trước và sau test cho các giá trị quan trọng: context ID, active profiles, property đang đọc, cache key, bean instance identity và resource identifier. Không log secret hoặc dữ liệu nhạy cảm.

## 13. Checklist cô lập test

Trước khi thêm một test vào suite, hãy xác nhận:

- [ ] Test khai báo đầy đủ property và profile mà nó cần.
- [ ] Không phụ thuộc vào test method chạy trước.
- [ ] Không sửa singleton bean dùng chung mà thiếu cleanup.
- [ ] Property source được thêm vào context riêng hoặc được xóa sau test.
- [ ] Dynamic property phản ánh đúng vòng đời của tài nguyên ngoài.
- [ ] TestContext cache được hiểu và dùng có chủ đích.
- [ ] @DirtiesContext chỉ dùng khi context không thể khôi phục.
- [ ] Static cache có API reset hoặc key riêng.
- [ ] System property được khôi phục về giá trị ban đầu.
- [ ] RefreshScope được refresh đúng bean khi cần.
- [ ] Database, broker, registry và filesystem dùng dữ liệu riêng hoặc có cleanup.
- [ ] Test sửa trạng thái dùng chung không chạy song song nếu chưa có đồng bộ.
- [ ] Cleanup vẫn chạy khi assertion hoặc setup thất bại.

## 14. Bài tập vận dụng

### Bài tập 1 — Hai class dùng chung ApplicationContext

Hai test class có cùng @SpringBootTest configuration. Class A sửa một singleton bean; class B mong bean có trạng thái ban đầu nhưng thất bại khi chạy toàn suite.

Hãy giải thích context cache và đề xuất hai cách xử lý: cleanup bean state hoặc đánh dấu context dirty khi không thể khôi phục.

### Bài tập 2 — Dynamic property thay đổi giữa các subclass

Một base class đăng ký server.port bằng @DynamicPropertySource. Mỗi subclass khởi động server khác port nhưng một số test vẫn dùng port cũ.

Hãy giải thích supplier, context cache key và khi nào cần @DirtiesContext.

### Bài tập 3 — Cache random rò giữa test

Hai test cùng đọc cachedrandom.test-node.uuid. Test sau nhận UUID do test trước tạo.

Hãy đề xuất cách dùng cache key riêng, clearCache() và @ResourceLock khi chạy parallel. Nêu vì sao @DirtiesContext không đủ.

### Bài tập 4 — System property bị xóa nhầm

Một test đặt acme.mode=test, sau đó gọi System.clearProperty("acme.mode"). Khi chạy suite, một test khác mất giá trị do build tool đã thiết lập trước đó.

Hãy viết cleanup lưu và phục hồi giá trị ban đầu, kể cả trường hợp ban đầu không tồn tại property.

### Bài tập 5 — RefreshScope và context lifecycle

Một bean @RefreshScope giữ endpoint của downstream. Test đổi property rồi gọi RefreshScope.refreshAll(), nhưng kết quả vẫn là endpoint cũ.

Hãy nêu các bước kiểm tra: property source có đổi không, bean có thật sự thuộc refresh scope không, proxy được gọi lại chưa và có static cache độc lập nào không.

### Bài tập 6 — Parallel test có race condition

Hai test chạy song song cùng sửa system property và cùng dùng một database schema. Chúng thất bại không ổn định.

Hãy đề xuất cách dùng ResourceLock cho JVM state, namespace riêng cho dữ liệu database và cấu hình chạy tuần tự cho nhóm test không thể cô lập.

## 15. Tự kiểm tra nhanh

1. Spring TestContext cache ApplicationContext ở đâu? **Trong cache static của test process.**
2. Hai test có cùng context metadata có thể dùng chung context không? **Có.**
3. @DirtiesContext làm gì? **Đóng và loại context khỏi cache để lần sau tạo lại.**
4. @DirtiesContext có xóa static field của ứng dụng không? **Không.**
5. ApplicationContextRunner hữu ích cho loại test nào? **Kiểm thử auto-configuration và các tổ hợp context nhỏ, cô lập.**
6. TestPropertyValues có thể thêm property vào đâu? **ConfigurableEnvironment hoặc ConfigurableApplicationContext.**
7. @DynamicPropertySource nhận đối tượng nào? **DynamicPropertyRegistry.**
8. Supplier của dynamic property được gọi khi nào? **Khi property được phân giải.**
9. Dynamic property có precedence cao hơn @TestPropertySource không? **Có.**
10. RefreshScope.refreshAll() có đóng toàn bộ ApplicationContext không? **Không, nó invalidate target cache của refresh scope.**
11. CachedRandomPropertySource.clearCache() có xóa giá trị đã bind vào bean không? **Không.**
12. Vì sao static cache cần ResourceLock khi test parallel? **Để tránh test này xóa hoặc thay đổi trạng thái mà test khác đang dùng.**
13. Có nên dùng @DirtiesContext cho mọi test integration không? **Không, vì tốn chi phí khởi tạo và không reset trạng thái ngoài context.**
14. Khi cleanup system property, vì sao cần lưu giá trị cũ? **Để khôi phục đúng cấu hình đã tồn tại trước test.**

**Thông điệp cốt lõi:** Muốn test Spring Cloud ổn định, hãy cô lập đúng lớp trạng thái. TestContext cache giữ lại ApplicationContext để tăng tốc; PropertySource quyết định giá trị mà bean nhìn thấy; RefreshScope quản lý target cache của bean; static field, system property và cache của thư viện sống ngoài context. Dùng ApplicationContextRunner, property source dành riêng cho test, cleanup có kiểm soát và @DirtiesContext đúng lúc sẽ giúp suite có kết quả lặp lại mà không phụ thuộc thứ tự chạy.

**Tài liệu tham khảo:**

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Boot 4.1 — Test Utilities and TestPropertyValues](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html)
- [Spring Boot — Testing Auto-configuration with ApplicationContextRunner](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Cloud Commons 5.0.4 — Application Context Services and RefreshScope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

Một số API và package phụ thuộc phiên bản Spring Boot/Spring Cloud đang dùng. Đối chiếu release train tương thích của dự án trước khi sao chép ví dụ vào mã nguồn.

