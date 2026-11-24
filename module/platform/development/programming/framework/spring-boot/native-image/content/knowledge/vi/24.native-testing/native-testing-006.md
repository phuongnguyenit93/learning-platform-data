# Mocking, instrumentation và tính năng kiểm thử cần xác nhận theo phiên bản

## 1. Vì sao bộ test JVM chưa đủ để xác nhận ứng dụng native?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để kiểm tra tính tương thích, thời gian khởi động, bộ nhớ, đóng gói container và vận hành. Phần lớn test vẫn nên phát triển và chạy trên JVM để có vòng lặp nhanh, nhưng một số hành vi thay đổi khi mã chạy trong executable native: reflection, dynamic proxy, class generation, Java agents, instrumentation, resource loading và các thư viện kiểm thử dựa trên những cơ chế đó.

Ví dụ, một unit test dùng Mockito để mock static method có thể chạy trên JVM nhờ inline mock maker và Java instrumentation. Khi test được biên dịch thành native executable, JVM instrumentation API và cơ chế sửa bytecode tại runtime không còn hoạt động theo cùng cách. Một test khác dùng Spring context, JUnit và DTO thuần có thể chạy tốt trong native test image nếu các thành phần và metadata cần thiết được hỗ trợ.

Vì vậy, cần xác định rõ **đang kiểm thử ứng dụng native bằng test harness JVM hay đang biên dịch chính test suite thành native executable**. Hai cách này kiểm tra những lớp khác nhau và có yêu cầu tương thích khác nhau.

Sau bài học, người học có thể:

1. Phân biệt JVM unit/integration tests, AOT-on-JVM tests, native tests và black-box tests cho executable.
2. Giải thích vì sao Mockito inline mock maker, Byte Buddy và Java instrumentation cần được xác minh riêng.
3. Chọn mock, stub, fake hoặc real test dependency phù hợp với native test.
4. Xác định những tính năng Spring Test/JUnit có thể dùng trong native testing theo version.
5. Cấu hình Maven/Gradle để build và chạy JUnit Platform tests dưới dạng native executable.
6. Tách test phụ thuộc JVM agent, Docker hoặc external infrastructure khỏi native test image khi cần.
7. Xây dựng test matrix theo dependency/toolchain/platform.
8. Đọc native test report, chẩn đoán lỗi và ghi nhận feature chưa được xác minh.

> **Nguyên tắc:** dùng JVM để có độ phủ kiểm thử rộng và phản hồi nhanh; dùng AOT-on-JVM để kiểm tra mã bootstrap đã sinh; dùng native tests và black-box tests để xác nhận các đường chạy có khác biệt thực sự trong Native Image.

## 2. Bốn lớp kiểm thử cần phân biệt

| Lớp | Test chạy ở đâu? | Mục đích chính | Ví dụ |
| --- | --- | --- | --- |
| JVM tests | JVM thông thường | Kiểm tra phần lớn logic, service, repository và integration nhanh. | JUnit, Mockito, Testcontainers, MockWebServer. |
| AOT-on-JVM | JVM nhưng dùng mã bootstrap Spring AOT đã sinh | Phát hiện lỗi trong generated AOT code trước khi biên dịch native. | Chạy ứng dụng với spring.aot.enabled=true. |
| Native tests | Test suite được build thành native executable | Xác nhận test engine, test code và application code hoạt động trong closed-world runtime. | GraalVM Native Build Tools nativeTest. |
| Black-box native tests | Test harness thường chạy trên JVM gọi native executable/process/container | Kiểm tra hợp đồng HTTP, startup, environment, database, broker và hệ điều hành đích. | WebClient, RestAssured hoặc Selenium gọi ứng dụng native. |

Không cần chuyển toàn bộ test suite sang native. Native compilation cho test có thể tốn thời gian và tài nguyên; ưu tiên các test có giá trị cao trong việc phát hiện khác biệt giữa JVM và native.

### 2.1. JVM tests vẫn là nền tảng

Dùng JVM để chạy nhanh phần lớn unit tests và integration tests. Đây là nơi phù hợp để dùng các thư viện mocking, assertion, fixture và test infrastructure có hỗ trợ JVM đầy đủ.

Giữ test logic độc lập với cách triển khai native. Ví dụ, kiểm thử quy tắc tính phí, validate input hoặc ánh xạ dữ liệu không cần biên dịch thành native chỉ để chứng minh thuật toán đúng.

### 2.2. AOT-on-JVM kiểm tra generated initialization

Spring Boot có thể chạy trên JVM nhưng sử dụng mã initialization do Spring AOT sinh. Sau khi build artifact có chứa AOT-generated code, chạy:

~~~bash
java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

Với Maven, artifact cần được build bằng profile kích hoạt AOT/native theo cấu hình dự án, ví dụ:

~~~bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

Với Gradle, bảo đảm plugin GraalVM Native Image đã được áp dụng và task build đã tạo AOT output trước khi chạy ứng dụng với property này.

AOT-on-JVM giúp xác nhận Spring context khởi tạo bằng mã generated không bị thiếu bean/configuration. Nó chưa chứng minh reflection, dynamic proxy, resource hoặc Java instrumentation sẽ hoạt động trong native executable.

### 2.3. Native tests xác nhận runtime native bên trong

Native Build Tools có thể build test suite thành native executable. JUnit Platform test engine được đưa vào test image và chạy danh sách test đã được phát hiện trong quá trình build.

Native tests phù hợp để xác minh:

- Spring context và test slice có thể được AOT xử lý.
- Reflection/resource/proxy metadata đủ cho test và application code.
- DTO binding, serializer, configuration và các đường truy cập động hoạt động.
- Các thư viện dùng trong test image tương thích với Native Image.

### 2.4. Black-box tests xác nhận executable trong môi trường thật

Một test harness JVM có thể khởi chạy executable native hoặc container, gọi HTTP endpoint, kiểm tra response và dọn tài nguyên. Test harness không cần được biên dịch thành native chỉ vì ứng dụng đích là native.

Cách này phù hợp với database, broker, Testcontainers, Selenium, TLS, network, filesystem và các công cụ kiểm thử cần Java agents hoặc dynamic class loading.

## 3. Mocking trong Native Image: xác định cơ chế trước khi sửa test

Mocking không phải một tính năng đơn nhất. Mock framework có thể tạo subclass, thay đổi bytecode của class đang tồn tại, tạo proxy hoặc dùng Java instrumentation. Các cơ chế này có yêu cầu rất khác nhau trong closed-world executable.

### 3.1. Mockito inline mock maker

Mockito 5 chuyển inline mock maker thành mặc định. Inline mock maker sửa bytecode của class để chặn method call; một số đường chạy dựa trên Java instrumentation và agent attachment.

Theo ghi chú phát hành Mockito 5, inline mock maker không hoạt động trên GraalVM Native Image; Mockito nêu subclass mock maker là lựa chọn phù hợp cho trường hợp này. Vì vậy, test dùng mock static method, mock constructor hoặc mock final type bằng inline maker cần được xem là JVM-specific cho đến khi version/framework cụ thể chứng minh khác.

Ví dụ kiểu test phụ thuộc inline maker:

~~~java
@Test
void calculatesUsingStaticClock() {
    try (MockedStatic<ClockProvider> clock =
             Mockito.mockStatic(ClockProvider.class)) {
        clock.when(ClockProvider::now)
             .thenReturn(Instant.parse("2026-01-01T00:00:00Z"));

        assertThat(service.calculate()).isEqualTo(expected);
    }
}
~~~

Đoạn test này minh họa static mocking. Để logic nghiệp vụ có thể chạy trong native, hãy đưa thời gian vào qua dependency có thể thay thế, chẳng hạn java.time.Clock, thay vì phải sửa static method.

### 3.2. Subclass mock maker

Mockito cung cấp artifact mockito-subclass để chọn subclass mock maker. Với một số version, có thể cấu hình mock maker bằng extension file hoặc dependency tương ứng. Kiểm tra tài liệu Mockito của đúng version trước khi thay dependency.

Ví dụ cấu hình extension truyền thống:

~~~text
src/test/resources/
└── mockito-extensions/
    └── org.mockito.plugins.MockMaker
~~~

Nội dung file:

~~~text
mock-maker-subclass
~~~

Subclass mock maker tạo subclass để đại diện mock. Cách này tránh cơ chế inline instrumentation, nhưng vẫn cần kiểm tra việc tạo class động, kiểu class được mock và metadata của Native Image. Không giả định mọi mock sẽ tự hoạt động chỉ vì đã đổi mock maker.

Lưu ý:

- Subclass mock maker không mock được final class/method theo cách inline maker làm.
- Constructor, visibility, sealed/final types và classloader có thể giới hạn việc tạo subclass.
- Một số dependency hoặc plugin có thể ép mock maker khác thông qua cấu hình riêng.
- Chạy nativeTest với đúng Mockito version để xác nhận, không chỉ dựa vào test JVM.

### 3.3. Khi nên dùng fake hoặc stub

Nếu test cần chạy trên cả JVM và native, một fake đơn giản thường ổn định hơn mock tạo class động. Ví dụ:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

final class FakePaymentGateway implements PaymentGateway {
    private final List<PaymentRequest> requests = new ArrayList<>();

    @Override
    public PaymentResult charge(PaymentRequest request) {
        requests.add(request);
        return PaymentResult.approved("test-transaction");
    }

    List<PaymentRequest> requests() {
        return List.copyOf(requests);
    }
}
~~~

Fake triển khai interface bằng class thông thường, có thể được phân tích tĩnh và dễ kiểm soát trong native test. Nó cũng giúp test kiểm tra hành vi quan sát được, thay vì phụ thuộc vào chi tiết nội bộ của mock framework.

| Test cần kiểm tra | Cách thay thế phù hợp |
| --- | --- |
| Thời gian hiện tại | Inject java.time.Clock và dùng Clock.fixed trong test. |
| Sinh số ngẫu nhiên | Inject Random/RandomGenerator hoặc một port tạo ID. |
| Gọi HTTP | Dùng stub HTTP server hoặc fake adapter; kiểm tra request/response thật. |
| Database repository | Dùng fake repository cho unit test; dùng database thật/container cho integration test. |
| Message broker | Fake publisher/consumer cho unit test; broker thật trong integration test. |
| Static utility | Bọc sau interface/adapter hoặc chuyển thành object có dependency rõ ràng. |
| Constructor side effect | Inject factory/provider thay vì mock constructor. |
| Final class khó mock | Dùng interface port hoặc fake triển khai interface. |

Fake cần có hành vi đủ rõ và test riêng nếu nó mô phỏng quy tắc quan trọng. Đừng biến fake thành một bản sao phức tạp của production implementation.

### 3.4. Spring test bean overrides

Spring test có các cơ chế thay bean bằng mock trong ApplicationContext, chẳng hạn @MockitoBean ở Spring Framework version hỗ trợ hoặc annotation tương ứng ở version cũ hơn.

Những annotation này không tự biến Mockito thành native-compatible. Cần xác định:

- Annotation thuộc Spring Framework/Spring Boot version nào.
- Mockito mock maker nào đang được nạp.
- Bean được thay có phải final class hoặc cần inline mocking không.
- Test context đã được Spring AOT xử lý chưa.
- Native test có tạo được mock và khởi động context không.

Nếu mock bean chỉ phục vụ test JVM, có thể giữ test đó ở JVM và tạo một native integration test khác dùng fake/real bean phù hợp.

## 4. Java instrumentation và Java agents

### 4.1. Instrumentation trên JVM

JVM có thể nạp Java agent bằng tham số -javaagent hoặc cơ chế attach. Agent có thể dùng java.lang.instrument.Instrumentation để biến đổi bytecode khi class được nạp hoặc redefine class trong phạm vi JVM cho phép.

Một số công cụ kiểm thử dùng cơ chế này:

- Mockito inline mock maker và Byte Buddy agent.
- JaCoCo Java agent để đo coverage trên JVM.
- Profiler/APM agent.
- Công cụ weaving hoặc instrumentation của test framework.
- Agent theo dõi hành vi class loading hoặc method invocation.

### 4.2. Native executable không chạy dưới HotSpot JVM

Native executable không phải JVM process thông thường. Không thể giả định các Java agents dùng -javaagent, attach API hoặc JVM class redefinition sẽ hoạt động trong executable native.

Nếu test suite cần agent, hãy xác định rõ agent đang instrument:

- JVM chạy test harness.
- JVM chạy ứng dụng dạng JAR.
- Hay chính ứng dụng đã biên dịch thành native executable.

Agent có thể tiếp tục instrument JVM test harness hoặc JVM server giả lập bên ngoài; điều đó không có nghĩa nó instrument được native process.

### 4.3. JaCoCo và coverage

JaCoCo Java agent thường đo coverage bằng cách instrument bytecode khi JVM chạy test. Coverage JVM rất hữu ích để đánh giá độ phủ logic, nhưng nó không tự cung cấp coverage cho mã native executable được tạo bởi GraalVM.

Có thể tổ chức hai báo cáo:

- **JVM coverage:** độ phủ logic của unit/integration tests chạy trên JVM.
- **Native execution coverage:** các scenario đã thực sự được chạy trên native, được ghi nhận bằng native test reports, black-box results hoặc công cụ coverage/debugging có hỗ trợ đúng GraalVM version.

Không gộp hai số liệu thành một tỷ lệ duy nhất nếu cách thu thập khác nhau. Ghi rõ test nào chạy trên JVM, test nào chạy native và phần nào chưa có coverage instrumentation tương ứng.

### 4.4. Phân biệt Java instrumentation với Spring AOP

Spring AOP có thể dùng JDK dynamic proxy hoặc class-based proxy. Đây là cơ chế proxy của framework và có hỗ trợ AOT/runtime hints theo trường hợp; nó không đồng nghĩa với Java instrumentation agent.

Nếu ứng dụng dùng Spring AOP, hãy kiểm tra generated proxy và hints trong AOT/native build. Nếu test dùng agent để sửa bytecode, đó là một vấn đề instrumentation khác.

## 5. JUnit Platform và native test conditions

GraalVM Native Build Tools hỗ trợ biên dịch test JUnit Platform thành native executable. Plugin có hỗ trợ tường minh cho JUnit Jupiter và JUnit Vintage; TestEngine khác cần được đánh giá theo khả năng Native Image và metadata tương ứng.

Các version plugin có yêu cầu JUnit Platform/JUnit Jupiter tối thiểu. Tài liệu Native Build Tools hiện hành nêu JUnit 5.8.1 là mức tối thiểu được hỗ trợ cho plugin; Maven còn cần Surefire và JUnit Platform artifacts tương thích. Luôn đối chiếu version matrix của plugin đang dùng.

### 5.1. Chỉ chạy test trong native image

JUnit có điều kiện @EnabledInNativeImage và @DisabledInNativeImage ở các version hỗ trợ. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledInNativeImage;
import org.junit.jupiter.api.condition.DisabledInNativeImage;

class NativeSpecificTests {

    @Test
    @EnabledInNativeImage
    void verifiesNativeOnlyBehavior() {
        // Chạy chỉ trong native image.
    }

    @Test
    @DisabledInNativeImage
    void usesJvmOnlyInstrumentation() {
        // Test phụ thuộc JVM instrumentation.
    }
}
~~~

Dùng điều kiện này có chủ đích:

- Test phụ thuộc JVM-only instrumentation có thể được đánh dấu JVM-only.
- Test native-specific có thể xác nhận một hành vi chỉ xuất hiện trong native.
- Logic nghiệp vụ quan trọng không nên biến mất khỏi native suite chỉ bằng cách gắn @DisabledInNativeImage.

Nếu một test bị loại khỏi native suite, tạo test native khác xác nhận cùng hợp đồng bằng fake hoặc integration path phù hợp. Kiểm tra JUnit version đang quản lý annotation này; không thêm import chỉ dựa vào tài liệu của release khác.

### 5.2. Test engine và extension

Native test image cần test engine, extension và các test classes có thể được phân tích. Hãy kiểm tra:

- JUnit Platform launcher, Jupiter engine và Vintage engine có version tương thích.
- TestEngine tùy chỉnh có hỗ trợ Native Image không.
- Extension có dùng reflection, service loader, dynamic class loading hoặc instrumentation không.
- Parameterized tests, test templates và dynamic tests có được plugin/JUnit version hỗ trợ trong cấu hình native không.
- Test discovery có tìm đúng tập test mong muốn không.

Nếu native test report không tìm thấy test, kiểm tra engine/launcher và discovery configuration trước khi thêm reflection hints vào application code.

## 6. Spring Test trong native image

Spring Framework có hỗ trợ AOT cho test ApplicationContext. Spring Boot documentation hiện hành mô tả các bước:

1. Phân tích test để tìm các ApplicationContext cần dùng.
2. Chạy AOT processing cho các context đó và sinh assets.
3. Tạo native image chứa các assets đã sinh và JUnit TestEngine.
4. Khởi chạy native image để thực thi các test được phát hiện.

Theo tài liệu Spring Boot hiện hành, các tính năng Spring testing thông dụng như @SpringBootTest và test slices có thể được dùng trong native tests. Tuy nhiên, test cụ thể vẫn phụ thuộc vào version của Spring, test framework, Mockito, database driver và các dependency khác.

### 6.1. @SpringBootTest

Dùng @SpringBootTest để kiểm tra ApplicationContext và wiring gần với ứng dụng thật:

~~~java
@SpringBootTest
class OrderApplicationNativeTests {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrder() {
        OrderResult result = orderService.create(
            new CreateOrderCommand("SKU-1", 2)
        );

        assertThat(result.status()).isEqualTo(OrderStatus.CREATED);
    }
}
~~~

Nếu test context chứa bean cần reflection/resource/proxy metadata, native test có thể phát hiện thiếu hints. Đảm bảo context được AOT processing và các cấu hình test không phụ thuộc classpath chỉ có ở JVM.

### 6.2. Test slices

Test slices giúp giới hạn ApplicationContext, ví dụ @WebMvcTest, @DataJpaTest hoặc slice khác theo Spring Boot version. Chúng có thể giảm phạm vi context và native image test, nhưng test slice vẫn cần các dependency/test doubles tương thích.

Nếu slice dùng @MockitoBean hoặc mock annotation khác, xác minh mock maker thực tế. Khi Mockito không phù hợp, dùng fake bean hoặc cấu hình test thay thế theo cơ chế Spring hỗ trợ.

### 6.3. Test context caching

Spring test có thể cache ApplicationContext giữa các test có cùng cấu hình. Trong native testing, mỗi context cần được phân tích và AOT xử lý phù hợp. Nhiều cấu hình test khác nhau làm tăng số context và thời gian build native test image.

Giữ số lượng context có chủ đích:

- Tái sử dụng cấu hình test khi cùng hợp đồng.
- Không tạo profile/context mới nếu không có khác biệt cần kiểm tra.
- Tách test cần external service khỏi unit/native test thuần khi hợp lý.
- Kiểm tra log AOT để biết context nào đã được phát hiện và xử lý.

## 7. Kiểm tra instrumentation và mocking theo version

Không nên suy ra native compatibility từ tên thư viện hoặc một test đơn lẻ. Lập matrix cho đúng dependency được phân giải.

| Thành phần | Câu hỏi phải xác minh |
| --- | --- |
| Mockito | Version, mock maker đang được chọn, có dùng inline/static/constructor mocking không? |
| Byte Buddy | Có tạo class hoặc instrument class lúc runtime không? Version có hướng dẫn cho GraalVM Native Image không? |
| JUnit | Platform/engine version có tương thích Native Build Tools không? Có native image conditions không? |
| Spring Test | Spring Framework/Boot version có AOT test support và annotation đang dùng không? |
| JaCoCo | Báo cáo coverage chỉ cho JVM hay có chế độ hỗ trợ native executable riêng? |
| Testcontainers | Docker client, container runtime và test harness được chạy ở JVM hay trong native test image? |
| WireMock/MockWebServer | Server/client và extension có phụ thuộc dynamic class generation hoặc Java agent không? |
| Agent/APM | Agent có thể attach vào JVM nào? Có tuyên bố hỗ trợ Native Image runtime không? |
| Database test driver | Driver và test database có metadata/native library cho OS đích không? |

### 7.1. Kiểm tra dependency thực tế

Maven:

~~~bash
./mvnw dependency:tree -Dverbose -Dscope=test
~~~

Lọc Mockito và Byte Buddy:

~~~bash
./mvnw dependency:tree -Dincludes=org.mockito:*,net.bytebuddy:*
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Xem lý do chọn version:

~~~bash
./gradlew dependencyInsight \
  --dependency mockito-core \
  --configuration testRuntimeClasspath
~~~

Kiểm tra cả artifact test-only và dependency bắc cầu. Ví dụ, ứng dụng có thể khai báo Mockito version này nhưng Spring Boot BOM hoặc starter test kéo một version khác vào runtime test classpath.

### 7.2. Kiểm tra mock maker thực tế

Trong Mockito, xác định artifact và extension file đang có. Mockito 5 mặc định inline mock maker; nếu muốn thử subclass mock maker cho native test, kiểm tra hướng dẫn của đúng release và cấu hình test classpath phù hợp.

Không dùng kết quả test JVM để kết luận native mock maker hoạt động. Chạy ít nhất một native test tạo và sử dụng mock theo đúng kiểu mock mà ứng dụng/test đang cần.

### 7.3. Ghi nhận phạm vi hỗ trợ

Một dependency có thể:

- Chạy được trong JVM tests nhưng không dùng được trong native test image.
- Chạy được nếu thay inline mock maker bằng subclass maker.
- Chỉ chạy được với interface mocks, không hỗ trợ static/final/constructor mocking.
- Chạy được trong test harness JVM điều khiển native app từ bên ngoài.
- Chưa có bằng chứng đủ để kết luận.

Ghi rõ trạng thái và feature đã test thay vì gắn nhãn chung “Mockito native supported”.

## 8. Tổ chức test doubles để tăng khả năng chạy native

Một cách thiết kế giúp cả JVM và native tests dễ duy trì là đưa dependency ngoài qua interface/port.

Ví dụ service:

~~~java
public class OrderService {
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;
    private final Clock clock;

    public OrderService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository,
            Clock clock) {
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
        this.clock = clock;
    }

    public OrderResult create(CreateOrderCommand command) {
        Instant createdAt = Instant.now(clock);
        PaymentResult payment = paymentGateway.charge(
            new PaymentRequest(command.sku(), command.quantity())
        );
        if (!payment.approved()) {
            return OrderResult.rejected();
        }
        return orderRepository.save(
            Order.create(command, createdAt, payment.reference())
        );
    }
}
~~~

Test dùng fake:

~~~java
final class FakePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult = PaymentResult.approved("fake-1");

    void returnResult(PaymentResult result) {
        this.nextResult = result;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return nextResult;
    }
}
~~~

Và fixed clock:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-05-10T08:00:00Z"),
    ZoneOffset.UTC
);
~~~

Cách tổ chức này có lợi:

- Không cần mock static time API.
- Không cần tạo subclass động cho mọi dependency.
- Test có thể chạy như nhau trên JVM và native.
- Dễ kiểm tra request gửi ra gateway và trạng thái repository.
- Dependency thật có thể được kiểm tra riêng bằng integration tests.

Không thay mọi integration test bằng fake. Dùng fake để kiểm tra logic và dùng real service/container để kiểm tra giao thức, transaction, schema, network và driver.

## 9. External integration tests và Testcontainers

### 9.1. Test harness JVM điều khiển native executable

Với database hoặc broker, một test harness JVM có thể:

1. Khởi chạy Testcontainers hoặc service test.
2. Khởi động native executable với environment variables phù hợp.
3. Gọi HTTP endpoint hoặc message interface.
4. Xác nhận dữ liệu trong database/broker.
5. Dừng executable và dọn container.

Đây là black-box integration test. Nó xác nhận ứng dụng native giao tiếp với dependency thật trong môi trường gần production mà không yêu cầu Testcontainers phải được biên dịch vào native test image.

### 9.2. Khi chạy Testcontainers trong native test image

Chỉ đưa Testcontainers vào native test image nếu version và toàn bộ dependency path được xác minh hỗ trợ. Testcontainers có thể dùng Docker client, service loading, reflection, dynamic configuration và process/network access; các feature này cần kiểm tra riêng.

Nếu native test image không hỗ trợ cấu hình Docker client hoặc runtime environment, giữ Testcontainers orchestration ở JVM harness và test native app từ bên ngoài.

### 9.3. Stub HTTP server

Với HTTP client, có thể dùng WireMock hoặc MockWebServer trong JVM integration tests để kiểm tra request, timeout, retry và error mapping. Để test native executable, chạy stub server như một process/container riêng và gọi nó từ ứng dụng native. Xác minh server test library không bị kéo vào native test image nếu không cần.

## 10. Cấu hình native testing với Maven

Cấu hình phụ thuộc Spring Boot parent và GraalVM Native Build Tools version.

### 10.1. Spring Boot parent với nativeTest profile

Tài liệu Spring Boot hiện hành hướng dẫn dùng profile nativeTest khi project sử dụng spring-boot-starter-parent và đã opt-in các plugin cần thiết. Lệnh:

~~~bash
./mvnw -PnativeTest test
~~~

Profile nativeTest kích hoạt test AOT và native test execution theo cấu hình Spring Boot/Native Build Tools tương ứng.

Nếu project dùng parent POM riêng hoặc không dùng profile do Spring Boot cung cấp, cần cấu hình executions phù hợp cho:

- Spring Boot Maven Plugin goal process-test-aot.
- GraalVM Native Build Tools Maven plugin goal test.
- Maven Surefire và JUnit Platform artifacts tương thích.

### 10.2. Kiểm tra Surefire và JUnit Platform

Maven Native Build Tools hiện hành yêu cầu Maven Surefire 3.0.0 trở lên cho native test execution. JUnit Platform launcher phải tương thích với Jupiter/Vintage engine. Kiểm tra dependency tree để tránh trường hợp Surefire và Native Build Tools sử dụng các version JUnit Platform không khớp nhau.

### 10.3. Tách JVM test và native test

Có thể tổ chức CI thành các job:

~~~bash
# Nhanh: test trên JVM
./mvnw test

# Kiểm tra Spring AOT/native test theo profile của project
./mvnw -PnativeTest test

# Build application native image nếu pipeline yêu cầu
./mvnw -Pnative package
~~~

Lệnh cuối phụ thuộc profile build native của project. Không giả định nativeTest và native là cùng một profile hoặc cùng một lifecycle; kiểm tra POM thực tế và test report.

Nếu cần chạy test harness JVM cho executable, thực hiện ở một job riêng sau khi native package hoàn thành.

## 11. Cấu hình native testing với Gradle

Spring Boot Gradle plugin tự cấu hình AOT test tasks khi GraalVM Native Image plugin được áp dụng theo tài liệu version tương ứng.

Chạy native test:

~~~bash
./gradlew nativeTest
~~~

Build test image mà chưa chạy test:

~~~bash
./gradlew nativeTestCompile
~~~

Build application executable:

~~~bash
./gradlew nativeCompile
~~~

Các task có vai trò khác nhau:

- test: chạy test suite trên JVM.
- nativeTestCompile: biên dịch test suite thành native test executable.
- nativeTest: thực thi native test executable.
- nativeCompile: biên dịch ứng dụng chính thành native executable.

Có thể cấu hình test binary riêng nếu cần debug:

~~~groovy
graalvmNative {
    binaries {
        test {
            debug = true
            verbose = true
            buildArgs.add('-O0')
        }
    }
}
~~~

DSL có thể khác theo plugin version; đoạn trên là ví dụ Groovy DSL. Debug info và mức tối ưu thấp hữu ích khi cần GDB/source stepping trên môi trường được hỗ trợ, nhưng có thể làm binary lớn hơn hoặc chạy chậm hơn.

## 12. Phân loại test để chọn đúng nơi chạy

| Nhóm test | JVM | AOT-on-JVM | Native test image | Black-box native |
| --- | --- | --- | --- | --- |
| Pure domain logic | Chính | Có thể | Chọn lọc | Không bắt buộc |
| Mockito inline/static/constructor | Có nếu JVM hỗ trợ | Có nếu JVM hỗ trợ | Không giả định; thường cần thay mock maker/cách test | Harness có thể chạy ngoài native |
| Interface fake/stub | Có | Có | Phù hợp | Có |
| Spring context wiring | Có | Rất hữu ích | Phù hợp nếu version hỗ trợ | Có thể |
| Spring MVC/JSON binding | Có | Có | Chọn lọc | Rất hữu ích qua HTTP |
| Database/JDBC | Có | Có | Chỉ khi driver/test deps tương thích | Rất hữu ích với DB thật |
| Testcontainers orchestration | Có | Có | Chỉ khi toàn bộ stack được hỗ trợ | Phù hợp khi harness JVM điều khiển app native |
| Java agent/JaCoCo | Có | Có khi chạy JVM | Không giả định | Có thể instrument harness JVM |
| Startup/shutdown/environment | Hạn chế | Một phần | Có thể | Nên dùng |
| OS libraries/TLS/certificate | Baseline | Một phần | Có thể | Cần test container/platform |

### 12.1. Đừng bỏ qua test khi native không hỗ trợ một mock maker

Nếu một test phụ thuộc inline mock maker, có thể đánh dấu nó chỉ chạy JVM. Nhưng phải thay thế phần xác nhận hành vi native bằng test khác:

- Dùng fake hoặc adapter implementation.
- Chạy native test cho service với fake.
- Chạy black-box integration test với dependency thật hoặc stub server.
- Ghi rõ static/constructor mocking chỉ được kiểm tra ở JVM.

Không để một nhóm test bị disable khiến native suite không còn xác nhận logic quan trọng.

## 13. Chẩn đoán lỗi native tests

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mockito inline mock maker lỗi trong native | Dựa trên inline bytecode modification/Java instrumentation. | Dùng mockito-subclass nếu version hỗ trợ, hoặc thay bằng fake. |
| Không tạo được mock subclass | Runtime class generation, final/sealed type, constructor hoặc metadata không phù hợp. | Mock interface, dùng fake class tĩnh và kiểm tra native support của Mockito/Byte Buddy. |
| Native test không tìm thấy JUnit engine | Thiếu engine/launcher hoặc version không tương thích. | Kiểm tra testRuntimeClasspath, Surefire và Native Build Tools matrix. |
| @SpringBootTest JVM pass nhưng native test context lỗi | AOT context chưa được xử lý hoặc thiếu metadata/feature support. | Kiểm tra process-test-aot, generated context, hints và test slice. |
| Test bị bỏ qua trong native image | Native image condition hoặc test discovery/filter. | Kiểm tra @EnabledInNativeImage/@DisabledInNativeImage, tags và test report. |
| JaCoCo/Java agent không hoạt động trong native test | Agent yêu cầu JVM instrumentation. | Dùng coverage JVM; tách native runtime verification hoặc công cụ hỗ trợ native. |
| Testcontainers không khởi tạo được | Docker client/runtime không phù hợp native test image hoặc thiếu environment. | Chạy Testcontainers trong JVM harness và điều khiển native app từ bên ngoài. |
| Test pass JVM nhưng resource không tìm thấy native | Resource metadata thiếu hoặc path khác. | Thêm native integration test và xác minh resource hints/packaging. |
| Native test image build rất lâu | Nhiều context/test dependencies hoặc compile optimization. | Giảm số context, tách suite và chạy native tests chọn lọc trong CI. |
| Native test pass nhưng container deployment lỗi | OS/architecture, certificates, shared library hoặc environment khác. | Chạy black-box tests trong runtime image đích. |

### 13.1. Trình tự chẩn đoán

~~~mermaid
flowchart TD
    A[Native test thất bại] --> B{Lỗi nằm ở test framework hay application code?}
    B -->|Test framework| C[Kiểm tra JUnit, Mockito, Byte Buddy, agent]
    B -->|Application code| D[Kiểm tra AOT, hints, reflection, resources]
    C --> E{Có phụ thuộc JVM instrumentation?}
    E -->|Có| F[Tách JVM-only test hoặc thay bằng fake]
    E -->|Không| G[Kiểm tra version và native metadata]
    D --> H[Thêm scenario tái hiện và kiểm tra metadata]
    F --> I[Build lại native test]
    G --> I
    H --> I
    I --> J{Test và hành vi mục tiêu pass?}
    J -->|Chưa| B
    J -->|Rồi| K[Chạy black-box/container tests]
~~~

### 13.2. Debug native test

Khi test fail trong native executable, có thể build test binary với debug information và dùng debugger như GDB trên nền tảng được hỗ trợ. Native Build Tools có task compile test riêng để giữ executable và debug artifacts. Xem tài liệu GraalVM theo OS/debugger; GDB thường phù hợp nhất với Linux.

Trước khi debug, lưu:

- Native test executable và build log.
- Test report và tên test fail.
- GraalVM/JDK/plugin version.
- Build arguments và metadata.
- Input/fixture để tái hiện.

## 14. Xây dựng test matrix và CI strategy

Không cần chạy mọi native test ở mọi lần commit nếu thời gian compile quá lớn. Có thể chia pipeline:

| Giai đoạn | Nội dung | Nhịp chạy gợi ý |
| --- | --- | --- |
| Pull request | JVM unit tests, static checks, focused integration tests. | Mỗi thay đổi |
| AOT verification | Build AOT và chạy ứng dụng/test trên JVM với AOT mode. | Mỗi thay đổi quan trọng hoặc PR |
| Native compile | Build application native executable. | PR liên quan native config và CI chính |
| Native tests | Test suite chọn lọc chạy thành native image. | CI chính hoặc nightly tùy thời gian |
| Black-box native | HTTP, database, broker, TLS và container runtime. | Nightly, release candidate hoặc PR theo feature |
| Platform matrix | OS/architecture/base image/libc cần hỗ trợ. | Theo lịch hoặc trước release |

### 14.1. Test matrix cần ghi lại

- Spring Boot và Spring Framework version.
- JDK vendor/major version.
- GraalVM distribution/release.
- Native Build Tools Maven/Gradle plugin version.
- JUnit Platform/Jupiter/Vintage version.
- Mockito version và mock maker.
- Byte Buddy version.
- Testcontainers/WireMock/MockWebServer version nếu dùng.
- OS/architecture/libc và runtime container.
- Các test được chạy JVM, AOT-on-JVM, native test image hoặc black-box.

Khi nâng bất kỳ thành phần nào trong matrix, chạy lại nhóm test bị ảnh hưởng. Ví dụ, nâng Mockito có thể đổi mock maker mặc định; nâng JUnit có thể đổi Native Image conditions; nâng Spring Boot có thể đổi AOT test integration.

### 14.2. Báo cáo kết quả không được gộp mơ hồ

Ghi riêng:

- JVM tests: số pass/fail/skip và coverage.
- AOT-on-JVM: application context/profile đã được xác nhận.
- Native tests: số test thực thi trong native test image.
- Black-box tests: endpoint/scenario/platform đã chạy.
- JVM-only tests: lý do chưa chạy trong native và test thay thế.
- Known limitations: feature chưa có bằng chứng.

## 15. Bài thực hành: thay mocking phụ thuộc instrumentation bằng native-compatible tests

**Bối cảnh:** một dịch vụ Spring Boot xử lý đơn hàng dùng Mockito để mock static clock, mock payment gateway và mock một constructor của client. JVM test pass, nhưng native test image lỗi khi tạo inline mocks. Ứng dụng cần xác nhận logic trong native và giao tiếp với một payment stub.

### Nhiệm vụ

1. Kiểm tra dependency graph của Mockito, Byte Buddy, JUnit Platform và Native Build Tools.
2. Xác định mock maker thực tế và test nào dùng static/constructor/final mocking.
3. Phân loại test theo JVM-only, AOT-on-JVM, native test và black-box native.
4. Refactor service để inject Clock, PaymentGateway và ClientFactory qua constructor/interface.
5. Viết FakePaymentGateway và fake factory để kiểm tra domain/service logic.
6. Giữ test Mockito inline cần thiết ở JVM, ghi rõ lý do không chạy trong native image.
7. Viết native test dùng fake để xác nhận luồng tạo đơn hàng, lỗi thanh toán và retry.
8. Viết black-box integration test trên JVM harness: khởi chạy native executable, kết nối payment stub và gọi API.
9. Chạy AOT-on-JVM, nativeTest và container smoke tests.
10. Ghi version matrix, test report, các test bị disable có lý do và test thay thế.
11. So sánh kết quả JVM/native cho cùng fixtures và side effects.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Dependency matrix | JUnit, Mockito, Byte Buddy, Spring Boot, GraalVM, plugin versions. |
| Mock maker | Cấu hình thực tế và các test phụ thuộc inline/subclass. |
| Test classification | Danh sách JVM-only, AOT-on-JVM, native và black-box. |
| Test doubles | Fake gateway, clock và factory; hợp đồng mà fake mô phỏng. |
| Native test | Test report, executable và các scenario đã chạy. |
| External integration | Payment stub/container, HTTP request/response và cleanup. |
| AOT evidence | Log process-test-aot hoặc processAot, context được xử lý. |
| Limitations | Test chưa hỗ trợ, nguyên nhân, test thay thế và next action. |

### Tiêu chí hoàn thành

- [ ] Phân biệt được test harness JVM và native test image.
- [ ] Xác định đúng Mockito mock maker và các test phụ thuộc instrumentation.
- [ ] Có fake/stub thay thế cho luồng logic cần xác nhận native.
- [ ] AOT-on-JVM khởi tạo được context đã chọn.
- [ ] Native tests chạy được các luồng nghiệp vụ trọng yếu.
- [ ] Black-box test gọi được native executable và payment stub.
- [ ] Test bị disable có lý do và có kiểm thử thay thế.
- [ ] Version matrix và báo cáo JVM/native được lưu riêng.
- [ ] Kết quả tương đương theo cùng fixtures và hợp đồng.

## 16. Câu hỏi tự đánh giá

1. Khác nhau giữa JVM test, AOT-on-JVM, native test và black-box native test là gì?
2. Vì sao Mockito 5 inline mock maker cần được kiểm tra riêng khi chạy native image?
3. Subclass mock maker tránh cơ chế nào và vẫn có giới hạn gì?
4. Vì sao một fake triển khai interface thường dễ dùng trong native test hơn mock tạo class động?
5. Java agent dùng JaCoCo/Byte Buddy instrument JVM khác gì việc chạy native executable?
6. @SpringBootTest và test slices được Spring AOT xử lý như thế nào trong native testing?
7. Khi nào nên dùng @EnabledInNativeImage hoặc @DisabledInNativeImage?
8. Vì sao Testcontainers có thể phù hợp hơn khi chạy trong JVM test harness điều khiển native app từ bên ngoài?
9. Native test pass có chứng minh executable chạy đúng trong container production không?
10. Cần ghi những version nào để kết luận một tổ hợp test framework hỗ trợ native?

## 17. Tài liệu chính thức

Tính năng test native phụ thuộc version Spring Boot, Spring Framework, JUnit, Mockito và GraalVM Native Build Tools. Đối chiếu đúng release của dự án:

- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html): JVM testing, AOT-on-JVM, Spring test contexts, Maven và Gradle native testing.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): nativeTest, nativeTestCompile, JUnit Platform và cấu hình test binary.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin): native test execution, Surefire/JUnit Platform compatibility và plugin options.
- [GraalVM — Debug Native Tests in Maven and Gradle Projects](https://www.graalvm.org/latest/reference-manual/native-image/guides/debug-native-tests-maven-gradle/): build/debug native test executable và xử lý thiếu metadata.
- [Mockito 5 — Release Notes](https://github.com/mockito/mockito/wiki/Draft-Mockito-5-release-notes): thay đổi mock maker mặc định và lưu ý về inline/subclass mock maker trong GraalVM Native Image.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html): các cơ chế mocking và ghi chú instrumentation theo release.
- [JUnit User Guide — Native Image Conditions](https://docs.junit.org/6.0.0/user-guide/#writing-tests-conditional-execution-native-image): @EnabledInNativeImage và @DisabledInNativeImage.
- [Byte Buddy](https://bytebuddy.net/): runtime code generation và instrumentation; kiểm tra hỗ trợ theo version.

**Điểm cần nhớ:** mocking và instrumentation phải được đánh giá theo cơ chế thật và version thật. Duy trì độ phủ logic trên JVM, kiểm tra Spring AOT trên JVM, chọn lọc native tests cho những đường có rủi ro khác biệt và dùng black-box integration tests để xác nhận executable trong môi trường triển khai.

