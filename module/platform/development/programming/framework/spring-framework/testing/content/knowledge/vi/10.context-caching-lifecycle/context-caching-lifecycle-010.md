# Context failure threshold và cách tìm nguyên nhân lỗi đầu tiên

Khi một bài kiểm thử Spring không khởi tạo được `ApplicationContext`, các test class khác dùng cùng cấu hình có thể tiếp tục báo lỗi dù nguyên nhân ban đầu chỉ xuất hiện một lần. Từ Spring Framework 6.1, Spring Test có cơ chế **context failure threshold** để giới hạn số lần thử tải lại một context đã thất bại. Mặc định, ngưỡng là `1`: sau lần tải context đầu tiên thất bại, các lần thử tiếp theo cho cùng context cache key sẽ bị bỏ qua.

Vì vậy, log có thể hiển thị một thông báo như:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context
```

Thông báo này thường là hệ quả của một lần khởi tạo context thất bại trước đó. Nó không cho biết nguyên nhân gốc. Muốn sửa đúng lỗi, cần tìm lần tải context đầu tiên thất bại, đọc exception chain của lần đó và xác định bean, property, profile, resource hoặc dịch vụ phụ trợ khiến Spring không tạo được context.

## 1. Vì sao Spring cần failure threshold?

Spring TestContext Framework hỗ trợ cache `ApplicationContext` để tránh khởi tạo lại một context giống nhau cho từng test class. Nếu context khởi tạo thành công, các test class có cùng cấu hình có thể tái sử dụng context đã cache.

Nếu một context không thể khởi tạo, việc thử tạo lại cùng một context nhiều lần thường tốn thời gian mà không đem lại thông tin mới. Ví dụ, một datasource không kết nối được hoặc một bean cấu hình sai có thể khiến mọi test class dùng cùng cấu hình đều thất bại trong lúc bootstrap.

Trước khi có failure threshold, test suite có thể lặp lại quá trình khởi tạo context và in ra nhiều stack trace dài cho cùng một nguyên nhân. Từ Spring Framework 6.1, Spring theo dõi số lần tải context thất bại và ngừng thử lại khi số lần thất bại đạt ngưỡng đã cấu hình.

Mục tiêu của cơ chế này là:

- Tránh lặp lại thao tác khởi tạo context đã biết là thất bại.
- Giảm thời gian và lượng log dư thừa trong test suite.
- Làm rõ rằng những lỗi xuất hiện sau có thể chỉ là các lần truy cập lại cùng context đã hỏng.
- Khuyến khích tìm nguyên nhân của lần tải đầu tiên thay vì sửa từng test class bị ảnh hưởng.

Failure threshold không sửa cấu hình Spring, không phục hồi context và cũng không biến một lần khởi tạo thất bại thành thành công. Nó chỉ giới hạn số lần Spring thử tải một context có cùng cache key.

## 2. Giá trị mặc định và thuộc tính cấu hình

Spring Test cung cấp thuộc tính:

```text
spring.test.context.failure.threshold
```

Giá trị mặc định là `1`. Đây là số lần tải context thất bại được cho phép trước khi các lần thử tiếp theo cho cùng context cache key bị bỏ qua.

| Threshold | Hành vi với cùng một context cache key |
|---:|---|
| `1` | Cho phép lần thử đầu tiên. Nếu thất bại, lần thử tiếp theo bị bỏ qua |
| `2` | Cho phép tối đa hai lần tải thất bại; lần tiếp theo bị bỏ qua |
| `3` | Cho phép tối đa ba lần tải thất bại; lần tiếp theo bị bỏ qua |
| Số nguyên dương rất lớn | Về thực tế, làm cho giới hạn khó đạt tới trong một test run thông thường |

Threshold là một số nguyên dương. Cấu hình giá trị không hợp lệ hoặc không dương không phải cách tắt cơ chế an toàn; hãy dùng một số nguyên dương đủ lớn nếu có nhu cầu chẩn đoán tạm thời.

Có thể truyền thuộc tính cho JVM chạy test:

```bash
-Dspring.test.context.failure.threshold=3
```

Nên đặt thuộc tính trước khi Spring Test bắt đầu sử dụng `DefaultCacheAwareContextLoaderDelegate` và khởi tạo context. Cấu hình ở JVM test giúp mọi test trong process sử dụng cùng một ngưỡng.

### 2.1. Cấu hình trong Gradle

Với Gradle Groovy DSL, có thể truyền system property cho task `test`:

```groovy
def contextFailureThreshold = providers
        .systemProperty('spring.test.context.failure.threshold')
        .getOrElse('1')

tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.failure.threshold', contextFailureThreshold
}
```

Hoặc chỉ cấu hình tạm thời khi chạy task:

```bash
./gradlew test -Dspring.test.context.failure.threshold=3
```

Gradle đọc `-D` ở JVM thực thi build; đoạn cấu hình trên chuyển giá trị đó sang test worker thông qua `Test.systemProperty`. Nếu không có cấu hình chuyển tiếp, đừng mặc định mọi system property của Gradle build process đều tự động xuất hiện trong JVM chạy test.

### 2.2. Cấu hình trong Maven Surefire

Với Maven Surefire, có thể truyền property vào forked test JVM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.test.context.failure.threshold>3</spring.test.context.failure.threshold>
        </systemPropertyVariables>
    </configuration>
</plugin>
```

Hoặc truyền qua command line nếu cấu hình Maven và Surefire của dự án chuyển tiếp system property đến test JVM:

```bash
mvn test -Dspring.test.context.failure.threshold=3
```

Nếu dùng Maven Failsafe cho integration test, cần cấu hình property cho test JVM của Failsafe tương ứng. Surefire và Failsafe có thể chạy ở các fork/process khác nhau, nên không nên giả định cấu hình của plugin này tự động áp dụng cho plugin kia.

## 3. Threshold được áp dụng theo context cache key

Failure threshold không phải bộ đếm tổng số test thất bại của toàn bộ suite. Spring theo dõi số lần tải thất bại gắn với **mỗi context cache key** trong context cache của test process.

Context cache key được tạo từ metadata dùng để xác định một `ApplicationContext`, chẳng hạn:

- Các lớp cấu hình được khai báo qua `@ContextConfiguration` hoặc annotation liên quan.
- Resource XML hoặc resource cấu hình khác.
- Context initializer.
- Active profiles.
- Property source descriptors và inline properties.
- Context customizers, bao gồm các customizer do một số annotation test tạo ra.
- Context loader và context cha trong cấu hình hierarchy.

Vì vậy, hai test class dùng cùng metadata cấu hình có thể chia sẻ context cache key và cùng chịu ảnh hưởng của failure threshold. Hai test class có cấu hình khác nhau có thể có cache key khác nhau, do đó failure count được theo dõi độc lập.

Ví dụ:

```java
@SpringBootTest
class OrderServiceTests {
}

@SpringBootTest
class OrderRepositoryTests {
}
```

Nếu cả hai lớp có metadata bootstrap giống nhau, Spring có thể dùng cùng một context cache entry. Nếu lần khởi tạo context đó thất bại, test class đầu tiên có thể hiển thị nguyên nhân gốc, còn test class tiếp theo có thể gặp thông báo threshold đã vượt.

Ngược lại, nếu một lớp sử dụng profile hoặc property source khác:

```java
@SpringBootTest
@ActiveProfiles("integration")
class OrderServiceIntegrationTests {
}

@SpringBootTest
@ActiveProfiles("repository-test")
class OrderRepositoryTests {
}
```

hai cấu hình có thể tạo cache key riêng. Một context thất bại không mặc nhiên làm mọi context khác trong suite bị đánh dấu thất bại.

Failure count tồn tại trong context cache của JVM test process. Nếu build tool chạy test ở nhiều fork hoặc worker JVM, mỗi process có cache và bộ đếm riêng. Vì vậy, log từ các process khác nhau có thể cho thấy những lần thử độc lập.

## 4. Phân biệt lỗi khởi tạo đầu tiên và lỗi threshold ở lần sau

Đây là điểm quan trọng nhất khi đọc log.

### 4.1. Lần tải context đầu tiên thất bại

Khi Spring thử tạo context lần đầu và thất bại, exception thường mô tả vấn đề thực tế. Một số thông báo có thể gặp:

```text
Failed to load ApplicationContext
```

```text
BeanCreationException: Error creating bean with name 'dataSource'
```

```text
Could not resolve placeholder 'partner.api.base-url'
```

```text
Connection refused
```

Đây là nơi cần bắt đầu điều tra. Stack trace có thể chứa nhiều lớp exception bọc bên ngoài, vì vậy cần đọc toàn bộ chuỗi `Caused by` và tìm nguyên nhân liên quan đến cấu hình hoặc thành phần ứng dụng.

### 4.2. Lần thử tiếp theo bị bỏ qua

Khi failure count của cùng cache key đã đạt threshold, Spring ném một `IllegalStateException` với thông báo tương tự:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...
```

Lần này Spring không thực hiện lại toàn bộ quá trình tạo context. Do đó, stack trace của lỗi threshold không nhất thiết chứa exception gốc từ lần khởi tạo trước. Nó chỉ cho biết Spring đã bỏ qua lần thử vì context key đó từng thất bại đủ số lần.

### 4.3. Bảng phân biệt

| Dấu hiệu | Lần khởi tạo đầu tiên | Lần thử sau khi vượt threshold |
|---|---|---|
| Hành vi | Thực sự tạo `ApplicationContext` | Bỏ qua việc tải context |
| Thông báo | `Failed to load ApplicationContext` cùng exception nguyên nhân | `failure threshold ... exceeded` |
| Thông tin hữu ích | Bean, property, profile, resource hoặc kết nối gây lỗi | Cache key đã vượt ngưỡng |
| Cách xử lý | Tìm và sửa nguyên nhân gốc | Quay lại log của lần thất bại đầu tiên |

Nếu chỉ tập trung vào test class cuối cùng báo threshold, có thể mất thời gian sửa nhầm test class vốn không gây ra lỗi ban đầu.

## 5. Cách tìm lần lỗi đầu tiên trong log

Khi test suite có nhiều test class và log dài, hãy tìm theo thứ tự sau.

### Bước 1: Tìm thông báo threshold

Tìm chuỗi:

```text
failure threshold
```

hoặc:

```text
skipping repeated attempt to load context
```

Thông báo này xác nhận có một cache key đã thất bại đủ số lần. Ghi lại test class, context key hoặc phần mô tả cấu hình đi kèm để xác định nhóm test liên quan.

### Bước 2: Tìm lỗi load context xuất hiện trước đó

Trong cùng test run và cùng JVM, tìm lần xuất hiện sớm nhất của:

```text
Failed to load ApplicationContext
```

Đừng chỉ chọn lỗi đầu tiên trong toàn bộ file log nếu build chạy song song nhiều module hoặc nhiều fork. Hãy đối chiếu test class và metadata context để chắc rằng đó là cùng cache key.

### Bước 3: Đọc đầy đủ exception chain

Một stack trace có thể có dạng:

```text
IllegalStateException: Failed to load ApplicationContext
    ...
Caused by: BeanCreationException: Error creating bean with name 'orderClient'
    ...
Caused by: IllegalArgumentException: Could not resolve placeholder
    'partner.api.base-url' in value "${partner.api.base-url}"
```

Trong ví dụ này, lỗi đầu tiên có thể được mô tả chung là không tải được context. Nguyên nhân có ý nghĩa là bean `orderClient` không được tạo vì thiếu property `partner.api.base-url`.

Đọc từ exception ngoài cùng xuống các `Caused by`, đồng thời xem những frame đầu tiên thuộc code ứng dụng hoặc cấu hình test. Đừng mặc định exception sâu nhất luôn là lời giải thích đầy đủ; một số thư viện có thể bọc lỗi hệ thống bằng exception thấp cấp hơn như `IOException`, `SQLException` hoặc `ConnectException`.

### Bước 4: Đối chiếu test class và cấu hình context

Kiểm tra các annotation và cấu hình có thể ảnh hưởng tới cache key:

```java
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = "feature.payment.enabled=true")
class PaymentIntegrationTests {
}
```

Xem xét:

- Test có dùng profile mà môi trường hiện tại chưa cung cấp property không?
- Có file `application-integration.yml` hoặc property source cần thiết không?
- Có `@DynamicPropertySource` đăng ký URL, host hoặc cổng từ container không?
- Container hoặc server đã được khởi động trước khi Spring tạo bean sử dụng endpoint chưa?
- Có bean được khai báo có điều kiện nhưng điều kiện không thỏa mãn không?
- Test có cấu hình component scan, import hoặc mock bean khác với cấu hình ứng dụng không?

### Bước 5: Chạy riêng test class gây lỗi

Sau khi xác định test class đầu tiên, chạy riêng lớp đó để log tập trung hơn:

```bash
./gradlew test --tests "com.example.orders.OrderServiceIntegrationTests"
```

Với Maven Surefire:

```bash
mvn -Dtest=OrderServiceIntegrationTests test
```

Nếu test class được chạy riêng vẫn thất bại ở lần bootstrap đầu tiên, lỗi không phụ thuộc vào việc một test class khác đã làm hỏng context cache. Nếu test riêng thành công nhưng suite thất bại, cần điều tra thứ tự thực thi, trạng thái dùng chung, resource lifecycle, parallel execution hoặc sự khác biệt về JVM/configuration giữa hai lần chạy.

## 6. Ví dụ: thiếu dynamic property làm context thất bại

Giả sử một client yêu cầu URL:

```java
@Component
class PartnerClient {

    private final RestClient client;

    PartnerClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl
    ) {
        this.client = builder.baseUrl(baseUrl).build();
    }
}
```

Test class dự định lấy URL từ một server test nhưng quên đăng ký property:

```java
@SpringBootTest
class PartnerClientTests {
    // Missing @DynamicPropertySource registration
}
```

Lần đầu Spring tạo context, bean `PartnerClient` không thể được khởi tạo vì placeholder chưa được giải quyết. Lỗi ban đầu sẽ xuất hiện dưới dạng `Failed to load ApplicationContext`, sau đó là `BeanCreationException` và nguyên nhân liên quan đến placeholder.

Nếu test class khác dùng cùng context configuration, Spring có thể bỏ qua lần tải lại tiếp theo do threshold mặc định bằng 1. Log của test class thứ hai chỉ hiển thị thông báo threshold, không lặp lại toàn bộ nguyên nhân thiếu property.

Cách sửa là đăng ký property trước khi context cần tạo client:

```java
@SpringBootTest
class PartnerClientTests {

    @DynamicPropertySource
    static void registerPartnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.api.base-url", () -> "http://localhost:49172");
    }
}
```

Trong test thực tế, URL nên đến từ server hoặc container đã khởi động, chẳng hạn `wireMock::baseUrl` hoặc supplier ghép `getHost()` với `getMappedPort(...)`. Ví dụ trên dùng URL minh họa để tập trung vào quan hệ giữa property bị thiếu và lỗi bootstrap.

Sau khi sửa, chạy lại test trong một test JVM mới để bảo đảm context được tạo từ đầu với cấu hình mới. Nếu vẫn dùng một JVM hoặc một test run đang giữ context cache cũ, cần kết thúc run đó trước khi đánh giá kết quả.

## 7. Các nguyên nhân gốc thường gặp

Failure threshold chỉ là cơ chế phát hiện việc lặp lại tải context thất bại. Nguyên nhân gốc thường nằm ở cấu hình hoặc thành phần mà context cần khởi tạo.

| Nhóm nguyên nhân | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| Bean không khởi tạo được | `BeanCreationException`, `UnsatisfiedDependencyException` | Đọc bean đầu tiên không tạo được và dependency của nó |
| Thiếu property | `Could not resolve placeholder`, bind configuration properties thất bại | Kiểm tra profile, file YAML, environment variable và dynamic property |
| Sai profile | Bean hoặc property không được đăng ký | Kiểm tra `@ActiveProfiles` và cấu hình theo profile |
| Database không sẵn sàng | `SQLException`, `Connection refused`, timeout | Kiểm tra URL, mapped port, credentials, container health và lifecycle |
| HTTP dependency không sẵn sàng | Connect timeout hoặc connection refused | Kiểm tra server startup, base URL và cổng runtime |
| Cấu hình Java/XML sai | Parse exception, bean definition conflict | Kiểm tra `@Configuration`, `@Import`, XML resource và component scan |
| Dependency không tương thích | `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` | Kiểm tra dependency graph và phiên bản runtime |
| Test context tùy chỉnh sai | Lỗi từ `ContextCustomizer`, initializer hoặc loader | Kiểm tra metadata và extension của test |
| Tài nguyên đã bị dừng | Context cache còn nhưng container/server không còn hoạt động | Đồng bộ vòng đời tài nguyên với context cache |

Hãy bắt đầu từ exception cụ thể trong lần load đầu tiên. Không phải mọi `Failed to load ApplicationContext` đều là lỗi dependency hoặc lỗi threshold; nhiều trường hợp chỉ là một cấu hình test chưa đầy đủ.

## 8. Failure threshold và context cache

Context cache giữ các context đã tải thành công để tái sử dụng. Với context tải thất bại, Spring ghi nhận số lần thất bại theo cache key để áp dụng threshold. Việc này có nghĩa là cùng một lỗi cấu hình có thể ảnh hưởng tới nhiều test class chia sẻ context, dù từng lớp không trực tiếp gây ra lỗi.

### 8.1. Vì sao nhiều test class cùng báo lỗi?

Giả sử ba test class dùng chung `@SpringBootTest` và cùng active profile:

```java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerServiceTests {
}

@SpringBootTest
@ActiveProfiles("integration")
class CustomerRepositoryTests {
}

@SpringBootTest
@ActiveProfiles("integration")
class CustomerControllerTests {
}
```

Nếu context của profile `integration` thất bại ở lần đầu, các lần thử sau với cùng cache key có thể bị bỏ qua. Khi đó, một test report có thể liệt kê ba lớp thất bại, nhưng chỉ có một lỗi bootstrap gốc cần sửa.

### 8.2. Cấu hình khác có thể tạo context khác

Nếu một test class dùng `@ActiveProfiles("integration")` và lớp khác dùng `@ActiveProfiles("repository")`, chúng có thể tạo hai cache key khác nhau. Mỗi context có thể thất bại vì một nguyên nhân riêng. Không nên gộp mọi thông báo threshold trong suite thành một lỗi duy nhất nếu metadata không giống nhau.

### 8.3. Cache không tự sửa sau khi thay đổi cấu hình

Trong cùng một test JVM, failure count và context cache thuộc vòng đời của process. Khi thay đổi file cấu hình hoặc sửa bean trong lúc test JVM vẫn đang chạy, không nên kỳ vọng cache tự quên lần thất bại cũ và tự tạo lại context theo source mới. Hãy kết thúc test process và chạy lại để kiểm chứng cấu hình đã sửa.

## 9. Khi nào nên tăng threshold?

Trong phần lớn trường hợp, giữ mặc định `1` giúp test suite dừng việc lặp lại tải một context đã hỏng. Tuy nhiên, có thể tạm tăng threshold để chẩn đoán một tình huống đặc biệt.

Ví dụ:

```bash
./gradlew test -Dspring.test.context.failure.threshold=3
```

Việc này cho phép Spring thử tải context tối đa ba lần thất bại trước khi bỏ qua lần tiếp theo. Có thể hữu ích khi đang điều tra một lỗi phụ thuộc thời điểm hoặc một môi trường test không ổn định.

Tuy nhiên, tăng threshold có các giới hạn:

- Không sửa nguyên nhân khiến context không khởi tạo được.
- Có thể kéo dài thời gian test nếu mỗi lần khởi tạo tốn nhiều thời gian.
- Có thể tạo nhiều stack trace gần giống nhau và làm log khó đọc hơn.
- Không thay thế việc kiểm tra resource lifecycle hoặc race condition.

Nếu mỗi lần thử lại cho kết quả khác nhau, hãy xác định vì sao cấu hình hoặc tài nguyên thay đổi giữa các lần bootstrap. Ví dụ, container chưa sẵn sàng, cổng chưa được cấp, service chưa health-check thành công hoặc một property supplier trả về giá trị không ổn định. Sau khi tìm được nguyên nhân, trả threshold về mặc định nếu không còn nhu cầu chẩn đoán.

## 10. Không nhầm threshold với retry hoặc cơ chế tự phục hồi

Failure threshold không phải retry policy cho database hoặc HTTP request. Nó cũng không phải cơ chế tự khởi động lại Spring context sau khi ứng dụng đã chạy.

| Cơ chế | Mục đích |
|---|---|
| Context failure threshold | Giới hạn số lần thử tải một `ApplicationContext` đã thất bại cho cùng cache key |
| Retry của HTTP/database client | Thử lại một thao tác I/O theo chính sách retry của client |
| Testcontainers wait strategy | Chờ dịch vụ trong container sẵn sàng trước khi test sử dụng |
| Context cache | Tái sử dụng context đã khởi tạo thành công giữa các test có cấu hình tương thích |
| `@DirtiesContext` | Đánh dấu context không còn phù hợp để tái sử dụng và yêu cầu loại khỏi cache theo phạm vi được cấu hình |

Nếu PostgreSQL container chưa sẵn sàng, tăng context failure threshold không giải quyết được vấn đề. Cần cấu hình wait strategy, kiểm tra readiness hoặc điều chỉnh lifecycle để datasource chỉ được tạo khi dịch vụ có thể nhận kết nối.

Nếu một test làm thay đổi trạng thái context hoặc tài nguyên được gắn với context đã kết thúc, `@DirtiesContext` có thể phù hợp. Nhưng annotation này không phải cách sửa mọi lỗi bootstrap. Nếu bean cấu hình sai hoặc property bị thiếu, tạo context mới với cùng cấu hình vẫn sẽ thất bại.

## 11. Kiểm tra lỗi phụ thuộc thứ tự và chạy song song

Đôi khi test class chạy riêng thì thành công, nhưng cả suite lại thất bại. Trường hợp này cần kiểm tra các yếu tố ngoài bản thân cấu hình:

- Test trước đó có thay đổi system property, system clock, default locale hoặc cấu hình global không?
- Một test có dừng container hoặc mock server mà test khác vẫn cần dùng không?
- Các test có dùng chung port cố định, file tạm, database schema hoặc dữ liệu không?
- Có test nào gọi `@DirtiesContext` và làm thay đổi cách tái sử dụng context không?
- Test chạy song song có tranh chấp tài nguyên dùng chung không?
- Các test worker có dùng cùng JVM, hay build tool tách chúng sang nhiều fork?

Để điều tra, có thể chạy riêng test class gây lỗi, sau đó chạy cùng nhóm test theo thứ tự tái hiện được. Nếu chỉ lỗi khi chạy song song, thử tạm thời giảm mức song song để xem lỗi có liên quan tới tranh chấp tài nguyên hay không. Việc này là bước chẩn đoán; giải pháp lâu dài vẫn cần loại bỏ phụ thuộc không an toàn giữa các test.

Với log bị xen kẽ do chạy song song, hãy dựa vào tên test class, timestamp, test worker/process và context metadata. Không nên lấy dòng `Failed to load ApplicationContext` gần nhất theo thứ tự file log mà không xác nhận nó thuộc cùng context key.

## 12. Quy trình xử lý lỗi theo từng bước

Khi gặp `ApplicationContext failure threshold exceeded`, có thể thực hiện quy trình sau:

1. **Xác nhận phiên bản Spring.** Failure threshold có từ Spring Framework 6.1; kiểm tra dependency graph nếu dự án dùng phiên bản cũ hơn hoặc nhiều phiên bản Spring khác nhau.
2. **Tìm thông báo threshold.** Ghi lại test class và phần context metadata trong log.
3. **Tìm lần `Failed to load ApplicationContext` đầu tiên** cho cùng cache key và cùng test JVM.
4. **Đọc toàn bộ cause chain.** Xác định bean hoặc thành phần đầu tiên gây lỗi, property chưa resolve, kết nối thất bại hoặc cấu hình không hợp lệ.
5. **Đối chiếu cấu hình test.** Kiểm tra `@SpringBootTest`, `@ContextConfiguration`, profile, property source, initializer và dynamic property.
6. **Kiểm tra vòng đời tài nguyên.** Đảm bảo container, database, WireMock hoặc server đã sẵn sàng và còn chạy trong thời gian context sử dụng.
7. **Chạy riêng test class đầu tiên.** Làm log ngắn hơn và xác nhận lỗi bootstrap có tái hiện độc lập hay không.
8. **Sửa nguyên nhân gốc.** Điều chỉnh cấu hình hoặc lifecycle tại đúng thành phần gây lỗi.
9. **Chạy lại test JVM mới.** Xác nhận context có thể khởi tạo thành công và các test dùng chung context chạy được.
10. **Trả threshold về giá trị mặc định** nếu trước đó đã tăng chỉ để chẩn đoán.

Khi ghi issue hoặc báo cáo lỗi, hãy đính kèm test class đầu tiên thất bại, exception gốc và context metadata liên quan. Danh sách dài các test class chỉ bị bỏ qua do threshold thường ít hữu ích hơn một stack trace nguyên nhân được xác định rõ.

## 13. Ví dụ đọc log từ đầu đến cuối

Giả sử log có dạng rút gọn:

```text
OrderRepositoryTests
Failed to load ApplicationContext
Caused by: BeanCreationException: Error creating bean 'dataSource'
Caused by: SQLException: Connection refused

OrderServiceTests
IllegalStateException: ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...

OrderControllerTests
IllegalStateException: ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...
```

Cách đọc:

- `OrderRepositoryTests` là test class đầu tiên trong ví dụ thực hiện việc tải context và thất bại.
- `dataSource` không được tạo vì kết nối database bị từ chối.
- `OrderServiceTests` và `OrderControllerTests` gặp cùng cache key, nên Spring bỏ qua lần tải tiếp theo khi threshold mặc định là 1.
- Cần điều tra database URL, host, mapped port, credentials, container startup và readiness ở lần đầu.
- Không cần sửa riêng hai test class sau nếu chúng chỉ dùng chung context bị lỗi.

Nếu `OrderServiceTests` có profile hoặc property source khác, cần kiểm tra cache key trước khi kết luận rằng nó bị ảnh hưởng bởi lỗi của `OrderRepositoryTests`.

## 14. Những sai lầm thường gặp

**Chỉ sửa test class hiển thị thông báo threshold.** Test đó có thể không phải nơi gây lỗi. Hãy tìm lần tải context đầu tiên thất bại cho cùng cache key.

**Tăng threshold rồi coi như đã sửa xong.** Threshold cao chỉ cho phép thử lại nhiều lần hơn. Nếu cấu hình vẫn sai, mọi lần thử vẫn có thể thất bại.

**Xóa context cache mà không tìm nguyên nhân.** Tạo lại context với cùng property và bean lỗi sẽ tiếp tục thất bại. Cache không phải nguyên nhân gốc nếu context chưa từng khởi tạo thành công.

**Dùng `@DirtiesContext` cho mọi test.** Annotation có thể làm suite chậm và không giải quyết placeholder thiếu, bean sai hoặc database chưa sẵn sàng.

**Giả định mọi test failure đều có cùng cache key.** Profile, property source, context customizer hoặc lớp cấu hình khác nhau có thể tạo cache key riêng.

**Đọc exception threshold như exception gốc.** Thông báo `skipping repeated attempt` chỉ giải thích vì sao Spring không thử lại. Hãy tìm stack trace của lần bootstrap thất bại đầu tiên.

**Bỏ qua khác biệt giữa test JVM.** Mỗi fork/worker JVM có context cache và failure count riêng. Log của nhiều process có thể chứa nhiều lần tải đầu tiên độc lập.

**Chỉ đọc dòng exception sâu nhất.** Root cause thấp nhất đôi khi chỉ là lỗi I/O chung. Cần kết hợp exception chain với bean hoặc cấu hình ứng dụng đầu tiên xuất hiện trong stack trace.

## 15. Cách ghi nhận và chia sẻ nguyên nhân lỗi

Khi báo cáo một lỗi context threshold cho nhóm phát triển, nên cung cấp các thông tin có thể tái hiện:

| Thông tin | Ví dụ |
|---|---|
| Phiên bản Spring Framework/Boot | Phiên bản thực tế từ dependency graph |
| Test class đầu tiên thất bại | `OrderRepositoryTests` |
| Context key liên quan | Profile, config class, property source hoặc loader |
| Threshold | `spring.test.context.failure.threshold=1` |
| Exception nguyên nhân | `Connection refused` khi tạo datasource |
| Tài nguyên phụ thuộc | PostgreSQL Testcontainers, mapped port hoặc server ngoài |
| Cách tái hiện | Lệnh chạy riêng test class và kết quả |
| Cách sửa | Điều chỉnh startup/readiness hoặc property registration |

Tránh chỉ gửi phần log cuối cùng có thông báo threshold, vì phần đó thường thiếu thông tin về lần tạo context đầu tiên. Một báo cáo tốt nên chỉ rõ test class đầu tiên thất bại và exception gốc dẫn đến thất bại đó.

Context failure threshold là cơ chế giới hạn các lần thử tải lại `ApplicationContext` đã thất bại, theo từng context cache key trong test JVM. Giá trị mặc định `1` khiến Spring chỉ thử một lần trước khi bỏ qua các lần lặp. Khi thấy `failure threshold exceeded`, hãy xem đây là dấu hiệu có một lần bootstrap thất bại trước đó: tìm `Failed to load ApplicationContext` đầu tiên thuộc cùng context, đọc cause chain, kiểm tra profile/property/bean và vòng đời dịch vụ phụ trợ, rồi chạy lại test trong JVM mới sau khi sửa nguyên nhân. Tăng threshold chỉ nên là biện pháp chẩn đoán tạm thời, không phải giải pháp thay thế cho việc sửa lỗi gốc.
