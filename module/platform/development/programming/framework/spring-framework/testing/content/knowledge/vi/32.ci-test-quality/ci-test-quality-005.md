# Giảm số context khác nhau mà không làm mất phạm vi xác nhận

## 1. Vì sao số lượng Spring test context ảnh hưởng đến thời gian CI?

Spring integration test thường cần tạo `ApplicationContext` để khởi tạo bean, đọc cấu hình, chạy component scan, tạo proxy, kết nối datasource và thiết lập các thành phần web. Một context đầy đủ có thể mất vài giây hoặc lâu hơn tùy số lượng bean và hạ tầng mà ứng dụng khởi động.

Spring TestContext Framework có cơ chế cache `ApplicationContext` giữa các test class. Khi hai test class yêu cầu cùng một cấu hình context, Spring có thể dùng lại context đã tạo thay vì khởi động lại từ đầu. Lợi ích này chỉ xuất hiện khi cấu hình của các test tương thích với nhau.

Một suite có nhiều test class nhưng chỉ dùng một vài cấu hình chung có thể chạy nhanh hơn suite có ít test class nhưng mỗi class tạo một context khác nhau. Những thay đổi nhỏ như thêm một property riêng, một profile khác, một cấu hình mock bean khác hoặc một `@DirtiesContext` không cần thiết có thể làm cache miss và buộc Spring tạo context mới.

Mục tiêu tối ưu là **giảm các cấu hình context trùng lặp**, đồng thời giữ đúng ranh giới kiểm thử. Một test controller vẫn cần xác nhận MVC behavior; một test repository vẫn cần kiểm tra persistence; một số integration test vẫn phải khởi động server thật nếu cần xác nhận HTTP transport. Tái sử dụng context không có nghĩa là chuyển mọi test về cùng một kiểu test.

## 2. Spring xác định một context có thể tái sử dụng bằng cách nào?

Spring TestContext Framework xây dựng một khóa cấu hình từ metadata của test. Khi khóa của test mới khớp với một context đang có trong cache, context đó có thể được tái sử dụng.

Các thành phần quan trọng tham gia khóa gồm:

| Thành phần cấu hình | Ví dụ tạo khác biệt |
|---|---|
| `locations` | Hai class nạp các XML configuration location khác nhau |
| `classes` | Một class dùng cấu hình ứng dụng A, class khác thêm một configuration class riêng |
| `contextInitializerClasses` | Hai class đăng ký initializer khác nhau |
| `contextCustomizers` | Khác `@DynamicPropertySource`, bean override hoặc các customizer do Spring Boot/test framework cung cấp |
| `contextLoader` | Dùng loader khác nhau |
| `parent` | Context cha khác nhau trong context hierarchy |
| `activeProfiles` | Một test bật profile `test`, test khác bật `integration` |
| `propertySourceDescriptors` | Dùng các file `@TestPropertySource` khác nhau |
| `propertySourceProperties` | Inline properties khác nhau |
| `resourceBasePath` | Web resource base path khác nhau |

Tên test class tự nó không phải tiêu chí duy nhất quyết định cache key. Hai class khác tên vẫn có thể dùng chung context nếu các thành phần cấu hình hiệu lực giống nhau. Ngược lại, hai class nằm cùng package và cùng dùng `@SpringBootTest` vẫn có thể tạo hai context nếu properties, profiles, imports hoặc bean overrides khác nhau.

Ví dụ:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.audit=true")
class OrderServiceIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.audit=false")
class AuditDisabledIntegrationTest {
}
```

Hai class yêu cầu giá trị cấu hình khác nhau cho cùng property. Spring không thể dùng một context duy nhất cho cả hai cấu hình, vì bean đã được khởi tạo trong context phải nhìn thấy một giá trị nhất quán.

## 3. Cache hoạt động trong phạm vi nào?

Context cache là cache tĩnh trong tiến trình JVM đang chạy test. Các test class trong cùng một JVM có thể chia sẻ context nếu cache key khớp. Khi một JVM test kết thúc, cache trong tiến trình đó cũng kết thúc.

Điều này có ý nghĩa với CI và Gradle:

- Nhiều test class chạy tuần tự trong cùng test worker JVM có thể tái sử dụng context.
- Nếu build fork nhiều JVM, mỗi JVM có cache riêng; một context trong worker A không được chia sẻ trực tiếp với worker B.
- Một lần chạy Gradle test mới thường khởi tạo JVM test mới, nên không kế thừa cache của lần chạy trước.
- Chạy một class riêng lẻ có thể phải tạo lại context dù chạy cả suite trước đó đã dùng context tương tự.

Số lượng context khác nhau vì vậy ảnh hưởng trực tiếp đến chi phí khởi động trong từng worker process. Tăng số worker song song có thể giảm thời gian tường nhưng đồng thời làm nhiều context được khởi tạo đồng thời, tăng CPU và memory.

## 4. Dùng cùng cấu hình nền cho các test cùng phạm vi

Nếu nhiều test class cần cùng một loại integration context, hãy chuẩn hóa các annotation và configuration dùng chung. Ví dụ, các test service tích hợp cùng cần toàn bộ ứng dụng, profile `test` và một bộ test configuration giống nhau:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseIntegrationTest {
}
```

Các class con có thể dùng cấu hình đó:

```java
class OrderServiceIntegrationTest extends BaseIntegrationTest {
    // Các test liên quan đến order service.
}

class PaymentServiceIntegrationTest extends BaseIntegrationTest {
    // Các test liên quan đến payment service.
}
```

Kế thừa một base class không tự động bảo đảm cache hit nếu class con thêm properties, profiles, imports hoặc bean overrides khác. Giá trị của base class là giúp các test dùng cùng một cấu hình chuẩn và giảm việc khai báo lệch nhau.

Không nên đưa mọi test vào một base class khổng lồ chỉ để ép dùng chung context. Một controller slice và một real-server integration test có mục tiêu khác nhau; chúng có thể cần context riêng một cách hợp lý.

## 5. Tạo composed annotation cho nhóm test có cấu hình giống nhau

Một custom annotation có thể gom các annotation thường dùng để tránh mỗi class tự khai báo một biến thể:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(SharedMvcTestConfig.class)
public @interface MvcIntegrationTest {
}
```

Sử dụng:

```java
@MvcIntegrationTest
class OrderMvcIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}

@MvcIntegrationTest
class CustomerMvcIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
```

Composed annotation giúp mọi class cùng nhóm có một web environment, profile, MVC setup và test configuration. Nó giảm nguy cơ một class vô tình bật profile khác hoặc quên một cấu hình chung.

Nếu cần biến thể có chủ đích, có thể tạo composed annotation riêng như `@RealServerIntegrationTest` dùng `RANDOM_PORT`. Không nên thêm thuộc tính tùy biến vào annotation rồi truyền giá trị khác nhau cho từng class nếu mục tiêu là tái sử dụng cùng context; giá trị khác nhau có thể tạo cấu hình context khác.

## 6. Chuẩn hóa profile và property source

Profiles và properties là nguyên nhân phổ biến làm context cache bị phân mảnh. Hãy xác định một bộ cấu hình test mặc định cho mỗi nhóm test.

Ví dụ, thay vì mỗi class tự khai báo một tập inline property khác nhau:

```java
@SpringBootTest(properties = {
        "feature.audit=true",
        "client.timeout=2s"
})
class OrderIntegrationTest {
}

@SpringBootTest(properties = {
        "client.timeout=2s",
        "feature.audit=true"
})
class CustomerIntegrationTest {
}
```

Hãy gom cấu hình dùng chung vào một file property ổn định:

```properties
# src/test/resources/application-test.properties
feature.audit=true
client.timeout=2s
```

Sau đó dùng cùng profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
class CustomerIntegrationTest {
}
```

Các test cùng dùng `application-test.properties` và cùng cấu hình ứng dụng có cơ hội dùng lại context. Nếu một test thật sự cần kiểm tra `feature.audit=false`, đó là một cấu hình hành vi khác. Hãy giữ test đó thành một context riêng hoặc kiểm tra policy bằng unit test có dependency được điều khiển, tùy phạm vi cần xác nhận.

Không nên thay đổi system property hoặc environment state giữa các test để ép một context đã khởi tạo nhìn thấy giá trị mới. Bean có thể đã đọc property khi khởi tạo và giữ giá trị đó trong field. Cấu hình phải ổn định trong suốt vòng đời context.

## 7. Hạn chế `@DirtiesContext` ở những nơi thật sự cần

`@DirtiesContext` yêu cầu Spring loại context khỏi cache và đóng context đó. Test tiếp theo cần cùng cấu hình sẽ phải tạo lại context.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTest {
}
```

Annotation này phù hợp khi test làm thay đổi trạng thái cấu hình hoặc singleton bean theo cách không thể khôi phục an toàn và có thể làm test khác bị ảnh hưởng. Nó không nên được thêm chỉ vì test ghi dữ liệu database hoặc gọi một service có side effect.

Các trường hợp thường không cần `@DirtiesContext`:

- Test ghi dữ liệu trong transaction test và rollback đúng cách.
- Test có thể xóa dữ liệu riêng theo ID sau khi chạy.
- Mock bean được Spring Test quản lý và reset theo lifecycle của nó.
- Test dùng một fake hoặc spy có trạng thái và có thể reset rõ ràng.
- Test cần dọn message, cache hoặc file nhưng có cách cleanup riêng.

Hãy xử lý trạng thái ở đúng nơi sở hữu nó. Database cleanup nên làm sạch database; mock state nên reset mock; cache ứng dụng nên xóa entry liên quan; context chỉ nên bị loại khỏi cache khi chính context đã bị làm bẩn.

## 8. Chia sẻ test configuration thay vì tạo biến thể riêng cho từng class

`@TestConfiguration` cho phép khai báo bean chỉ dùng trong test. Nếu nhiều test class cần cùng fake, clock hoặc adapter test, có thể đặt cấu hình vào một class dùng chung và import giống nhau.

```java
@TestConfiguration(proxyBeanMethods = false)
public class SharedIntegrationTestConfig {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2025-04-10T09:30:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new InMemoryNotificationGateway();
    }
}
```

Các test cùng import cấu hình:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
class OrderNotificationIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
class AccountNotificationIntegrationTest {
}
```

Bean `Clock` cố định giúp kết quả thời gian nhất quán. Gateway trong bộ nhớ có thể ghi nhận thông báo để test đọc lại mà không cần gọi dịch vụ bên ngoài.

Nếu một test cần fake có hành vi khác, hãy cân nhắc tạo unit test cho policy đó hoặc một cấu hình integration riêng. Không nên thay đổi cùng một singleton fake giữa các test song song nếu state của nó không được cô lập.

## 9. Mock bean có thể làm context key khác nhau

Các bean override trong test, chẳng hạn `@MockitoBean` của Spring Framework mới hoặc `@MockBean` trong các phiên bản Spring Boot cũ, được đăng ký thông qua context customizer. Tập mock bean, qualifier và cách override khác nhau có thể làm cấu hình context khác nhau.

Ví dụ hai class khai báo hai tập mock khác nhau:

```java
@SpringBootTest
class OrderIntegrationTest {
    @MockitoBean
    PaymentGateway paymentGateway;
}

@SpringBootTest
class CustomerIntegrationTest {
    @MockitoBean
    EmailGateway emailGateway;
}
```

Các cấu hình mock khác nhau có thể dẫn đến context cache key khác nhau. Nếu hai nhóm test cần cùng một bộ mock override, hãy chuẩn hóa tập mock ở cấu hình chung hoặc dùng một test configuration với fake dùng chung.

Tuy nhiên, không thêm mock chỉ để hai class có cùng key. Nếu test cần xác nhận bean thật được wiring hoặc tương tác với dependency thật, thay bằng mock sẽ làm mất phạm vi kiểm chứng. Hãy chọn dependency thay thế theo mục tiêu test, sau đó mới chuẩn hóa cấu hình giữa các test có cùng mục tiêu.

Với unit test thuần, dùng Mockito trực tiếp và tạo service bằng constructor injection. Không cần tạo Spring context chỉ để có `@MockitoBean`; cách đó vừa chậm vừa làm cache key phức tạp.

## 10. Dùng `@DynamicPropertySource` có tính ổn định

`@DynamicPropertySource` thường được dùng để đưa endpoint động như URL của Testcontainers vào Spring Environment:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Các method `@DynamicPropertySource` tham gia vào context customizer. Nếu mỗi test class có method đăng ký property khác nhau hoặc endpoint khác nhau, chúng có thể tạo context key khác nhau và giảm khả năng tái sử dụng.

Nếu nhiều test class có thể dùng cùng một container hoặc cùng một hạ tầng test, có thể đặt container và method đăng ký dynamic properties trong một base class hoặc cấu hình dùng chung. Cách này chỉ phù hợp khi vòng đời container và endpoint thực sự dùng chung an toàn.

Không để supplier trả về endpoint thay đổi trong khi context đã được tạo và bean datasource đã giữ connection pool theo giá trị cũ. Khi endpoint thay đổi, cần một context mới hoặc một thiết kế test infrastructure có lifecycle tương ứng.

Một container tĩnh được chia sẻ giữa nhiều class có thể giảm thời gian khởi động, nhưng cần chú ý test chạy song song, dữ liệu giữa test và thứ tự dừng container. Tái sử dụng context không thay thế việc cô lập schema hoặc dữ liệu.

## 11. Giữ các slice test có chủ đích

Không phải mọi test đều cần `@SpringBootTest`. Một cách giảm số context đồng thời vẫn giữ phạm vi xác nhận là dùng đúng loại test cho từng hành vi:

| Mục tiêu | Test scope phù hợp | Context thường cần |
|---|---|---|
| Logic tính toán hoặc quy tắc service thuần | JUnit unit test, tạo service trực tiếp | Không cần Spring context |
| Controller mapping, validation, JSON | `@WebMvcTest` + MockMvc | MVC slice |
| Repository query và mapping persistence | `@DataJpaTest` | JPA slice |
| Client HTTP hoặc adapter tích hợp | Test với mock HTTP server hoặc context hẹp | Context adapter cần thiết |
| Nhiều bean phối hợp trong ứng dụng | `@SpringBootTest(MOCK)` | Full application context, không mở cổng |
| Filter/connector/HTTP stack trên server thật | `@SpringBootTest(RANDOM_PORT)` | Full context kèm embedded server |

Ví dụ, nếu chỉ cần xác nhận controller chuyển command cho service và tạo response đúng, dùng `@WebMvcTest` cùng service mock. Không cần khởi động database, message broker và toàn bộ application context.

Nếu cần xác nhận controller, service, repository và transaction phối hợp, dùng integration test có phạm vi phù hợp. Nếu cần xác nhận server bind port, cookie hoặc TLS, giữ một số test `RANDOM_PORT` riêng.

Không gộp các test vào một context rộng hơn chỉ để giảm số context. Một slice nhỏ thường khởi động nhanh và xác nhận một ranh giới rõ ràng hơn.

## 12. Context reuse không đồng nghĩa với chia sẻ trạng thái test

Khi hai test class dùng chung context, chúng cũng dùng chung các singleton bean trong context đó. Điều này có thể ảnh hưởng đến trạng thái:

- Cache trong ứng dụng có thể còn dữ liệu từ test trước.
- In-memory fake có thể giữ danh sách event hoặc request.
- Singleton có mutable field có thể mang trạng thái qua test.
- Mock bean có thể được reset theo lifecycle của Spring Test, nhưng cấu hình reset phải phù hợp với phiên bản và test setup.
- Scheduled task hoặc background worker có thể tiếp tục chạy giữa các test.

Vì vậy, hãy thiết kế fixture và cleanup riêng cho từng test. Ví dụ fake có thể cung cấp `clear()`; repository test có thể xóa record theo test ID; cache có thể evict key được tạo trong test.

```java
@BeforeEach
void resetFixture() {
    notificationGateway.clear();
    orderRepository.deleteAllByTestRunId(TEST_RUN_ID);
}
```

Ví dụ chỉ phù hợp nếu fake và repository được thiết kế để reset an toàn. Với test song song, dùng ID duy nhất cho mỗi test method thay vì xóa toàn bộ dữ liệu dùng chung.

Không dùng `@DirtiesContext` để che giấu một fake không có khả năng reset hoặc một test không quản lý dữ liệu của nó. Hãy dọn trạng thái ở đúng resource owner để context có thể tiếp tục được tái sử dụng.

## 13. Cẩn thận với test chạy song song

Context cache có thể phục vụ nhiều test class hoặc method cùng dùng một context. Nếu bật parallel execution, các test có thể truy cập cùng singleton bean và cùng external resource đồng thời.

Các nguyên tắc quan trọng:

- Không để test thay đổi mutable singleton state mà không có cơ chế cô lập.
- Dùng dữ liệu riêng theo test ID hoặc tenant.
- Không xóa toàn bộ bảng database nếu test khác có thể đang dùng bảng đó.
- Không chia sẻ một mock server expectation queue giữa các test nếu request có thể đến đồng thời.
- Không thay đổi system property hoặc default timezone trong lúc test khác đang chạy.
- Nếu một tài nguyên không thể dùng đồng thời, dùng resource lock hoặc tắt parallel cho nhóm test đó.
- Chờ background task kết thúc trước khi reset fake, database hoặc container.

Tăng số worker Gradle cũng không làm context cache chia sẻ giữa các process. Nó có thể làm nhiều bản context giống nhau được tạo ở nhiều JVM. Cân nhắc chi phí khởi động và memory khi chọn mức song song.

## 14. Giới hạn kích thước context cache và hành vi LRU

Spring TestContext Framework có giới hạn kích thước cache. Mặc định thường là 32 context trong một JVM. Khi số context khác nhau vượt giới hạn, cache sử dụng chính sách least recently used (LRU) để loại context ít được dùng gần đây nhất. Khi test cần context đã bị loại, Spring phải khởi tạo lại.

Có thể thay đổi giới hạn qua system property:

```text
spring.test.context.cache.maxSize=64
```

Hoặc truyền system property khi chạy test:

```bash
./gradlew test -Dspring.test.context.cache.maxSize=64
```

Tăng cache size có thể giảm số lần context bị loại nếu suite thật sự cần nhiều cấu hình. Nhưng mỗi context có thể giữ bean, connection pool, executor, cache và embedded server. Tăng giới hạn có thể làm tăng đáng kể memory và số resource mở cùng lúc.

Không nên tăng cache size để che một suite có quá nhiều cấu hình gần giống nhau. Trước tiên hãy tìm nguyên nhân tạo cache key khác nhau. Chỉ tăng giới hạn sau khi đã hiểu số context cần thiết và đo được memory phù hợp.

## 15. Quan sát cache hit, miss và số context đã tạo

Có thể bật log cho cache của Spring TestContext để hiểu suite đang tái sử dụng context ra sao:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Log cache có thể cho biết số lần hit/miss và thống kê cache. Khi phân tích:

- **Hit tăng** khi test dùng lại context đã có.
- **Miss tăng** khi Spring cần tìm hoặc tạo context cho một key chưa có trong cache.
- **Size** cho biết số context hiện đang được giữ trong cache.
- **Eviction** cho biết context bị loại do giới hạn cache hoặc bị đánh dấu dirty.

Một suite có nhiều test class không nhất thiết có nhiều cache miss. Hãy nhìn thống kê trong cùng một JVM test process và đối chiếu với log khởi tạo context.

Nếu CI chạy nhiều worker JVM, mỗi process có cache riêng. Để hiểu tổng thời gian, cần xem log theo từng worker và cấu hình fork/parallel của build tool. Một báo cáo tổng hợp mà không phân biệt process có thể khiến ta tưởng context không được tái sử dụng.

## 16. `@DirtiesContext` và các mode của nó

`@DirtiesContext` có thể đánh dấu context dirty ở nhiều thời điểm, ví dụ sau method hoặc sau class. Khi context bị đánh dấu dirty, Spring đóng và loại context khỏi cache; lần test tiếp theo cần cấu hình đó sẽ tạo context mới.

```java
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
@Test
void changesSingletonConfigurationThatCannotBeRestored() {
    // Thay đổi trạng thái context có ảnh hưởng đến test khác.
}
```

Các mode khác nhau cho phép chọn thời điểm loại context, chẳng hạn trước hoặc sau method/class. Chọn mode nhỏ nhất đáp ứng nhu cầu và chỉ dùng khi trạng thái context thật sự không thể phục hồi.

Nếu test chỉ cập nhật database, hãy rollback hoặc cleanup database. Nếu test thêm key vào cache, evict key. Nếu test thay đổi system property, lưu và khôi phục giá trị. Nếu test tạo mock server, đóng mock server. Các hành động đó không cần loại toàn bộ Spring context.

`@DirtiesContext` hữu ích cho test xác nhận hành vi thay đổi context hoặc test legacy không thể khôi phục singleton state. Nhưng dùng rộng rãi sẽ làm cache gần như mất tác dụng và kéo dài CI.

## 17. Khi nào context riêng là cần thiết?

Không phải mọi cache miss đều là vấn đề. Một số khác biệt phản ánh các phạm vi kiểm thử thực sự khác nhau:

- `@WebMvcTest` và `@DataJpaTest` có slice configuration khác nhau.
- Test `MOCK` và `RANDOM_PORT` có web environment khác nhau.
- Test security bật và tắt một cấu hình filter khác nhau.
- Test profile production-like và profile với fake external service có mục tiêu khác nhau.
- Test kiểm tra một feature flag false có thể cần property context khác với feature flag true.
- Test cần database/container endpoint khác nhau không thể dùng chung bean connection pool đã khởi tạo.

Không nên loại bỏ khác biệt chỉ để tăng cache hit. Hãy hỏi: khác biệt đó có cần thiết để kiểm tra một hành vi/rủi ro khác không? Nếu có, giữ context riêng. Nếu khác biệt chỉ là khai báo lặp lại hoặc một giá trị không ảnh hưởng đến test, chuẩn hóa nó.

## 18. Một quy trình thực tế để giảm số context

1. Bật log cache và ghi nhận số context được tạo trong một lần chạy CI đại diện.
2. Nhóm test theo scope: unit, MVC slice, persistence slice, full context mock web và real server.
3. Với từng nhóm, xác định bộ profiles, properties, imports và bean overrides chuẩn.
4. Tạo composed annotation hoặc base configuration cho nhóm cần dùng cùng cấu hình.
5. Chuyển dependency mock đơn giản về unit test thuần nếu Spring context không cần thiết.
6. Chuẩn hóa `@TestPropertySource`, `@ActiveProfiles` và `@DynamicPropertySource` khi các test thật sự dùng cùng giá trị.
7. Loại `@DirtiesContext` không cần thiết; thay bằng cleanup dữ liệu, cache hoặc fake state.
8. Giữ real-server test cho các ranh giới cần xác nhận HTTP thật.
9. Chạy lại suite và so sánh cache hit/miss, số lần khởi động context, thời gian và memory.
10. Nếu cache vẫn bị eviction nhiều, đánh giá `spring.test.context.cache.maxSize` sau khi đã giảm cấu hình trùng lặp.

## 19. Ví dụ tổ chức một suite có nhiều phạm vi

Một module có thể tổ chức test như sau:

```text
src/test/java/
  unit/
    OrderPricingServiceTest.java
    RefundPolicyTest.java

  mvc/
    OrderControllerTest.java
    CustomerControllerTest.java

  persistence/
    OrderRepositoryTest.java
    PaymentRepositoryTest.java

  integration/
    BaseIntegrationTest.java
    OrderWorkflowIntegrationTest.java
    PaymentWorkflowIntegrationTest.java

  http/
    BaseRealServerTest.java
    OrderHttpIntegrationTest.java
```

Unit test tạo object trực tiếp, không cần context. MVC tests cùng dùng một `@WebMvcTest` pattern và cấu hình security/import thống nhất. Persistence tests cùng dùng cấu hình JPA slice. Các integration test dùng một profile và test configuration chung. Real-server tests dùng `RANDOM_PORT` và HTTP client khi cần xác nhận connector hoặc filter trên server thật.

Ví dụ base class cho nhóm integration:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseIntegrationTest {
}
```

Ví dụ nhóm real server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseRealServerTest {
}
```

Hai nhóm có web environment khác nhau nên có thể cần hai context. Trong mỗi nhóm, các test class dùng cùng cấu hình có cơ hội tái sử dụng context. Test vẫn giữ phạm vi xác nhận riêng bằng dữ liệu và assertion của từng class.

## 20. Những lỗi thường gặp khi tối ưu context cache

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi test class lại khởi động Spring | Profiles, properties, imports hoặc bean overrides khác nhau | So sánh context configuration và chuẩn hóa phần dùng chung |
| `@SpringBootTest` có nhiều biến thể inline | Mỗi class thêm một property riêng | Chuyển cấu hình chung vào profile/property file; giữ context riêng chỉ khi hành vi cần khác |
| Cache hit thấp dù annotation giống nhau | `@DynamicPropertySource`, customizer hoặc parent context khác | Kiểm tra log cache và dynamic property methods |
| Context liên tục bị đóng | Dùng `@DirtiesContext` rộng | Cleanup resource/data ở đúng owner thay vì loại context |
| Tăng cache size nhưng CI dùng nhiều memory | Nhiều context giữ connection pool, bean và server | Giảm context key khác nhau trước, đo memory rồi mới chỉnh cache size |
| Test pass riêng lẻ nhưng fail khi chạy suite | Context singleton hoặc dữ liệu được chia sẻ | Reset fake/cache, cô lập dữ liệu và kiểm tra parallel access |
| Chuyển mọi test sang full context để dùng chung | Mất lợi ích của slice và unit test | Giữ các scope cần thiết; chỉ chia sẻ context trong cùng nhóm cấu hình |
| Dùng chung container nhưng connection pool trỏ endpoint cũ | Dynamic property thay đổi sau khi context đã tạo | Giữ endpoint ổn định trong vòng đời context hoặc tạo context mới có chủ đích |
| Nhiều worker JVM vẫn tạo context lặp | Cache chỉ nằm trong từng JVM | Đánh giá số fork và mức song song; không kỳ vọng cache xuyên process |

## 21. Checklist giữ phạm vi xác nhận trong khi tái sử dụng context

- Test nào chỉ kiểm tra logic thuần có thể chạy không cần Spring context?
- Controller, repository và full application integration đã được chia theo scope phù hợp chưa?
- Các test cùng scope có dùng chung profiles, property sources, imports và bean overrides không?
- Những khác biệt cấu hình nào thực sự cần để kiểm tra một hành vi khác?
- `@DirtiesContext` có đang được dùng thay cho cleanup dữ liệu hoặc reset fake không?
- `@DynamicPropertySource` có cung cấp giá trị ổn định trong suốt vòng đời context không?
- Các test dùng chung context có cô lập database, cache, mock server và mutable singleton state không?
- Test chạy song song có thể ghi/xóa dữ liệu của nhau không?
- Real-server test vẫn được giữ cho port, connector, TLS hoặc HTTP filter behavior cần xác nhận chứ?
- Cache log cho thấy hit/miss và eviction như thế nào trong từng JVM?
- Cache size có phù hợp với memory mà các context đang giữ không?
- CI có dùng nhiều worker process khiến cache bị tách riêng không?

Giảm số Spring test context khác nhau là bài toán chuẩn hóa cấu hình và quản lý trạng thái. Spring có thể tái sử dụng context khi test yêu cầu cùng một cấu hình; vì vậy hãy gom những profile, properties, imports và bean overrides thực sự giống nhau, đồng thời tránh loại context không cần thiết. Giữ unit, slice, full-context và real-server test ở đúng ranh giới sẽ bảo toàn phạm vi xác nhận. Context cache giúp suite chạy nhanh hơn, còn dữ liệu test và trạng thái mutable vẫn phải được cô lập độc lập.
