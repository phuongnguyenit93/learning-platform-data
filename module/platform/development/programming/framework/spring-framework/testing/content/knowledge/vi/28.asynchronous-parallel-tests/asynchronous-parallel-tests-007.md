# Điều kiện TestContext phù hợp để chạy song song

**Ngữ cảnh:** Spring Framework Testing → Bất đồng bộ và song song.

Chạy nhiều bài kiểm thử cùng lúc có thể rút ngắn thời gian build, nhưng chỉ an toàn khi mỗi bài test có thể thực thi mà không làm thay đổi kết quả của bài khác. Với Spring TestContext Framework, điều kiện này cần được xem xét ở cả hai lớp: cách JUnit lập lịch test và cách Spring chia sẻ ApplicationContext giữa các test.

Spring có thể tái sử dụng một **ApplicationContext** cho nhiều test class có cấu hình tương đương. Việc tái sử dụng này giúp giảm chi phí khởi tạo, nhưng cũng có nghĩa nhiều test có thể đồng thời dùng chung singleton bean, mock, client, connection pool hoặc tài nguyên bên ngoài. Context cache được quản lý để hỗ trợ truy cập đồng thời; điều đó không tự động làm cho mọi bean và fixture bên trong context trở nên an toàn khi nhiều luồng cùng thao tác.

Một bộ test phù hợp để chạy song song cần có dữ liệu được cô lập, fixture không bị thay đổi cạnh tranh, vòng đời context ổn định và các tác vụ bất đồng bộ được đồng bộ đúng cách. Những test thay đổi trạng thái dùng chung hoặc đóng context cần được giới hạn chạy đồng thời.

## 1. Hai cơ chế khác nhau: JUnit lập lịch và Spring quản lý context

JUnit quyết định test nào chạy trên thread nào và thời điểm nào. Spring TestContext Framework cung cấp ApplicationContext, dependency injection, transaction test-managed và các listener cho vòng đời test.

Hai cơ chế phối hợp nhưng có trách nhiệm khác nhau:

~~~text
JUnit Jupiter
  |
  +--> chọn test class / test method
  |
  +--> lập lịch SAME_THREAD hoặc CONCURRENT
  |
  v
Spring TestContext Framework
  |
  +--> tạo hoặc lấy ApplicationContext từ context cache
  |
  +--> inject bean và quản lý test lifecycle
  |
  v
Test method
  |
  +--> dùng singleton bean / mock / datasource
  |
  +--> thao tác database / file / server / tài nguyên dùng chung
~~~

Bật parallel execution trong JUnit chỉ cho phép các test chạy đồng thời. Nó không tự động:

- Tạo ApplicationContext riêng cho mỗi test.
- Tạo database riêng hoặc rollback mọi thay đổi bên ngoài transaction.
- Làm mock và singleton bean an toàn với thao tác đồng thời.
- Chờ tất cả thread hoặc reactive pipeline hoàn tất.
- Ngăn một test đóng context mà test khác đang sử dụng.
- Cô lập system property, file, port hoặc server dùng chung.

Vì vậy, trước khi bật chạy song song cho một package hoặc module, cần xác định tài nguyên nào được chia sẻ và ai có quyền thay đổi chúng.

## 2. JUnit Jupiter bật chạy song song như thế nào?

### 2.1. Parallel execution là cấu hình của JUnit

JUnit Jupiter mặc định chạy test theo cách tuần tự nếu không bật parallel execution. Có thể bật bằng file **junit-platform.properties** trong test classpath:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent

junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

Ý nghĩa:

- **parallel.enabled:** bật cơ chế lập lịch song song của JUnit Jupiter.
- **mode.default:** đặt chế độ mặc định cho các node test như method.
- **mode.classes.default:** đặt chế độ mặc định cho các test class.
- **config.strategy:** chọn cách xác định parallelism.
- **fixed.parallelism:** đặt mức parallelism mục tiêu cho fixed strategy.

Giá trị **concurrent** cho phép node được chạy đồng thời khi không có ràng buộc hoặc resource lock ngăn cản. Không nên xem con số 4 là số thread tuyệt đối luôn tồn tại; đây là cấu hình parallelism của scheduler, còn việc thực thi thực tế còn phụ thuộc môi trường và các ràng buộc lập lịch.

Có thể đặt các thuộc tính này trong file cấu hình riêng của test thay vì bật ngay cho toàn bộ project. Bắt đầu từ một package có dữ liệu độc lập giúp phát hiện vấn đề chia sẻ tài nguyên dễ hơn.

### 2.2. Cấu hình bằng annotation

Có thể chỉ định chế độ trên một class hoặc method:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class IndependentControllerTests {

    @Test
    void firstScenario() {
        // Kịch bản độc lập.
    }

    @Test
    void secondScenario() {
        // Kịch bản độc lập khác.
    }
}
~~~

Hoặc ép một class chạy tuần tự:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class TestsUsingSharedMutableFixture {

    @Test
    void updatesSharedFixture() {
        // Thao tác trên trạng thái dùng chung.
    }

    @Test
    void readsSharedFixture() {
        // Phụ thuộc trạng thái đã được thiết lập.
    }
}
~~~

**SAME_THREAD** có nghĩa các node liên quan được thực thi trên cùng luồng theo lịch của JUnit. Nó không tự đồng bộ với một test class khác đang chạy song song. Nếu nhiều class cùng truy cập một tài nguyên, tất cả class liên quan cần dùng chung một quy ước khóa hoặc được cô lập ở phạm vi rộng hơn.

### 2.3. Chọn strategy phù hợp

JUnit hỗ trợ các strategy như dynamic, fixed và custom. Với fixed strategy, số parallelism được đặt rõ trong cấu hình. Với dynamic strategy, JUnit tính toán mức parallelism dựa trên cấu hình và số processor mà runtime nhận diện.

Chọn strategy dựa trên:

- Tài nguyên CPU và RAM của CI runner.
- Số lượng ApplicationContext cần khởi tạo đồng thời.
- Khả năng chịu tải của database test.
- Số lượng container hoặc mock server có thể chạy cùng lúc.
- Thời gian chờ network và giới hạn của dịch vụ test.

Nhiều test Spring khởi tạo context nặng, database và embedded server. Đặt parallelism quá cao có thể làm build chậm hơn do tranh chấp CPU, memory, connection pool hoặc I/O.

## 3. TestContext cache và ApplicationContext dùng chung

### 3.1. Vì sao nhiều test class có thể dùng cùng context?

Spring TestContext Framework lưu ApplicationContext trong một cache tĩnh theo tiến trình JVM. Khi một test class cần context có cấu hình tương đương context đã được tạo, Spring có thể lấy lại context đó thay vì khởi tạo từ đầu.

Cache key được hình thành từ các thuộc tính cấu hình test như:

- Context configuration classes và locations.
- Context initializer.
- Active profiles.
- Test property sources.
- Context customizers.
- Bean override hoặc mock bean declarations.
- Parent context và các thuộc tính liên quan khác.

Hai class có cùng cấu hình hiệu lực có thể dùng chung một ApplicationContext. Vì vậy, việc test class có instance riêng không có nghĩa các bean được inject vào chúng cũng riêng.

### 3.2. Context cache hỗ trợ truy cập đồng thời, nhưng bean vẫn có trạng thái

Spring quản lý cache để nhiều test có thể tra cứu và lấy context trong quá trình chạy song song. Tuy nhiên, các bean singleton trong context vẫn là cùng một object được nhiều test sử dụng.

Ví dụ:

~~~java
@Component
class RequestCounter {

    private int count;

    void increment() {
        count++;
    }

    int currentValue() {
        return count;
    }
}
~~~

Nếu nhiều test cùng gọi increment và currentValue trên singleton này, kết quả phụ thuộc thứ tự xen kẽ giữa các luồng. Việc JUnit tạo một test instance cho mỗi method không thay đổi điều đó.

Bean stateless, immutable hoặc đã được thiết kế thread-safe thường phù hợp hơn để dùng chung. Bean chứa mutable state, cache có thao tác ghi, bộ đếm, danh sách dùng làm fixture hoặc mock có stubbing thay đổi cần được xem xét riêng.

### 3.3. Không dùng context cache như cơ chế cô lập test

Context cache tối ưu chi phí khởi tạo, không phải ranh giới dữ liệu. Không nên giả định rằng mỗi test sẽ nhận một context mới hoặc trạng thái bean sẽ được reset sau mỗi method.

Nếu một test sửa bean state, đăng ký listener, thay đổi cấu hình runtime hoặc ghi vào bộ nhớ dùng chung, test khác có thể quan sát thay đổi đó. Cần reset state một cách an toàn, tạo context riêng hoặc không chạy các test liên quan đồng thời.

## 4. Điều kiện về trạng thái của test và test instance

### 4.1. Test instance lifecycle mặc định

JUnit Jupiter mặc định dùng **PER_METHOD**: tạo một instance test class mới cho mỗi test method.

~~~java
class OrderServiceTests {

    private int invocationCount;

    @Test
    void firstTest() {
        invocationCount++;
    }

    @Test
    void secondTest() {
        invocationCount++;
    }
}
~~~

Với PER_METHOD, hai method có instance riêng nên field instance không được chia sẻ giữa chúng. Tuy nhiên, static field, singleton bean, database, file và các tài nguyên ngoài test instance vẫn có thể được chia sẻ.

### 4.2. PER_CLASS cần chú ý khi chạy concurrent

Với **@TestInstance(PER_CLASS)**, JUnit dùng một instance cho toàn bộ test class:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class SharedTestInstance {

    private final List<String> observed = new ArrayList<>();

    @Test
    void firstTest() {
        observed.add("first");
    }

    @Test
    void secondTest() {
        observed.add("second");
    }
}
~~~

Ví dụ trên có race condition vì ArrayList không được thiết kế cho các thao tác ghi đồng thời. Ngoài collection, các field mutable khác và các callback lifecycle cũng có thể bị truy cập đồng thời.

Nếu dùng PER_CLASS, hãy bảo đảm:

- Field được chia sẻ là immutable hoặc thread-safe.
- Test method không phụ thuộc thứ tự.
- @BeforeAll và @AfterAll không tạo hoặc phá fixture khi method khác vẫn đang dùng.
- Các thao tác setup/cleanup không ghi đè trạng thái của nhau.

Nếu không cần một test instance chung, giữ mặc định PER_METHOD thường đơn giản hơn. Dù vậy, PER_METHOD không giải quyết vấn đề singleton bean hoặc database dùng chung.

### 4.3. Không dựa vào thứ tự test

Chạy song song có nghĩa thứ tự thực thi không còn là cơ chế đồng bộ đáng tin cậy. Một test không nên yêu cầu test khác chạy trước để tạo dữ liệu hoặc thiết lập trạng thái.

Không dùng @Order như một cách bảo đảm tuần tự khi các node được đánh dấu concurrent. Nếu hai bước thực sự là một kịch bản, hãy đặt chúng trong cùng một test method hoặc tạo fixture độc lập cho từng test.

## 5. Điều kiện về bean và mock dùng chung

### 5.1. Singleton bean phải an toàn với truy cập đồng thời

Một bean có thể được inject vào nhiều test class thông qua cùng context. Nếu bean chứa state mutable, cần xác định:

- State có được bảo vệ bằng synchronization hoặc concurrency primitive không?
- Test có thể reset state trong khi test khác đang đọc không?
- Có cache hoặc collection dùng chung không?
- Có scheduler, executor hoặc callback chạy nền không?
- Có cấu hình runtime được thay đổi trong test không?

Đối với bean nghiệp vụ thật, thread safety là một thuộc tính của ứng dụng và cần được thiết kế đúng. Không nên thêm synchronization tùy tiện chỉ để làm test xanh; trước hết xác định hành vi đồng thời đó có đúng với production hay không.

### 5.2. @MockitoBean và @MockitoSpyBean có thể được chia sẻ qua context

Khi dùng **@MockitoBean** hoặc **@MockitoSpyBean**, mock/spy được đăng ký trong ApplicationContext. Nếu nhiều test dùng chung context, chúng có thể thao tác cùng một mock instance.

Hai annotation này được bổ sung trong Spring Framework 6.2. Với project dùng phiên bản cũ hơn, cơ chế mock bean có thể đến từ Spring Boot Test; nguyên tắc về trạng thái mock được chia sẻ qua context vẫn cần được áp dụng.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderControllerTests {

    @MockitoBean
    CatalogGateway catalogGateway;

    @Test
    void returnsAvailableOrder() {
        given(catalogGateway.findAvailability("SKU-1"))
                .willReturn(new ProductAvailability("SKU-1", true));

        // Gửi request và xác nhận response.
    }
}
~~~

Nếu một test đang stubbing mock trong khi test khác gọi hoặc thay đổi expectation trên cùng mock, kết quả có thể phụ thuộc lịch thực thi. Việc một test method có test instance riêng không tạo ra mock bean riêng nếu context được tái sử dụng.

Cách xử lý:

- Không chạy đồng thời các test dùng chung mock có stubbing hoặc verification mutable.
- Tách context khi các test cần cấu hình mock khác nhau.
- Dùng fake immutable hoặc dependency riêng cho từng test khi phù hợp.
- Tổ chức test theo nhóm để không chia sẻ mock mutable giữa các method concurrent.

Không nên cho rằng chỉ cần gọi reset(mock) trong @BeforeEach là an toàn. Một test có thể đang sử dụng mock trong khi test khác reset nó.

### 5.3. Mockito mock không phải fixture dùng chung tùy tiện

Mockito hỗ trợ các tình huống sử dụng thông thường, nhưng việc đồng thời stubbing, reset, verify và gọi cùng một mock có thể tạo race hoặc làm assertion không xác định. Đặc biệt, mock bean trong context cache có vòng đời dài hơn một test method.

Nếu test cần stubbing khác nhau, cách cô lập dependency hoặc context là điều kiện quan trọng. Khóa toàn bộ test class có thể là biện pháp tạm thời, nhưng cần bảo đảm mọi test truy cập mock đó cùng tuân thủ một resource lock.

## 6. @DirtiesContext và vòng đời ApplicationContext

### 6.1. @DirtiesContext làm gì?

**@DirtiesContext** đánh dấu ApplicationContext đã bị thay đổi và cần được loại khỏi context cache. Spring sẽ đóng context đó khi xử lý việc loại bỏ, để một lần yêu cầu tiếp theo có thể tạo context mới.

Annotation có thể được dùng ở cấp method hoặc class với các mode khác nhau, ví dụ sau method hoặc sau class.

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestsThatChangeApplicationContext {
    // Test thay đổi trạng thái cấu hình của context.
}
~~~

Nó hữu ích khi test thật sự làm hỏng hoặc thay đổi context theo cách không thể khôi phục an toàn bằng cleanup thông thường. Không nên dùng @DirtiesContext như một lệnh reset mặc định sau mọi test vì chi phí khởi tạo context có thể rất lớn.

### 6.2. Vì sao @DirtiesContext nguy hiểm khi test song song?

Giả sử hai test class dùng chung context:

~~~text
Test A ------------------------>
          đang dùng ApplicationContext
Test B --------->
          đánh dấu @DirtiesContext
          Spring loại và đóng context
Test A ------------------------>
          có thể tiếp tục dùng context đã bị đóng
~~~

Một test có thể đang dùng bean, connection pool hoặc embedded server trong khi test khác yêu cầu context bị đóng. Điều này tạo lỗi ngẫu nhiên như bean đã bị hủy, connection đã đóng hoặc server không còn hoạt động.

Các test dùng @DirtiesContext không phải ứng viên tốt cho chạy song song với test khác sử dụng cùng context. Hãy chạy chúng tuần tự hoặc cô lập class để không có test khác thực thi đồng thời trong cùng JUnit engine.

Ví dụ:

~~~java
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestsThatCloseSharedContext {
    // Các test cần thay đổi hoặc đóng context.
}
~~~

**@Isolated** là annotation của JUnit Jupiter, yêu cầu class đó chạy riêng biệt với các test khác trong cùng test plan. Nó không điều phối các JVM khác hoặc process bên ngoài đang truy cập cùng tài nguyên.

@Isolated có từ JUnit Jupiter 5.11. Nếu project dùng phiên bản JUnit cũ hơn, có thể dùng cấu hình chạy tuần tự ở build hoặc tách test thành task riêng; @Execution(SAME_THREAD) chỉ giới hạn các node thuộc phạm vi áp dụng và không tự cô lập class khỏi mọi class khác.

Nếu có thể, hãy thiết kế test cleanup trạng thái mà không cần đóng context. Khi bắt buộc phải dùng @DirtiesContext, hãy xem xét cả các class khác có cùng cache key.

### 6.3. Không dùng @DirtiesContext để giải quyết mọi race

Nếu hai test ghi cùng một row database, đóng context không tự giải quyết xung đột dữ liệu. Nếu hai test cùng sửa system property, việc tạo context mới cũng không cô lập được trạng thái toàn JVM.

Chọn biện pháp đúng với tài nguyên gây xung đột:

- Mutable bean state: reset có kiểm soát hoặc context riêng.
- Database data: transaction hoặc schema/record riêng.
- Global property: resource lock hoặc tránh thay đổi.
- HTTP mock server: server/queue riêng.
- Context lifecycle: tuần tự hóa test đóng context.

## 7. Điều kiện về database và transaction

### 7.1. Transaction test-managed thường gắn với thread

Spring TestContext hỗ trợ transaction test-managed qua **@Transactional** và TransactionalTestExecutionListener. Transaction được bắt đầu và kết thúc theo vòng đời test, thường rollback sau test nếu không cấu hình khác.

~~~java
@Transactional
@SpringJUnitConfig(DataTestConfig.class)
class CustomerRepositoryTests {

    @Test
    void savesCustomer() {
        // Các thao tác trong test transaction.
    }
}
~~~

Khi hai test method chạy trên hai thread khác nhau, mỗi test có transaction riêng. Điều đó giúp tách transaction, nhưng không tự tạo database hoặc schema riêng cho mỗi test.

Nếu hai test cùng ghi một unique key, cùng cập nhật một bản ghi hoặc phụ thuộc vào thứ tự dữ liệu, chúng vẫn có thể xung đột.

### 7.2. Rollback không thay thế cô lập dữ liệu

Transaction rollback hữu ích với thao tác database nằm trong cùng transaction test-managed. Tuy nhiên, các tình huống sau có thể vượt ra ngoài phạm vi rollback:

- Một thread khác thực hiện ghi dữ liệu.
- Một tác vụ @Async hoặc executor mở transaction riêng.
- HTTP call tới dịch vụ bên ngoài đã tạo side effect.
- Test dùng @Commit hoặc @Rollback(false).
- Một transaction khác đọc/ghi cùng dữ liệu.
- Dữ liệu được tạo bởi script hoặc fixture ngoài transaction hiện tại.

Không nên giả định mọi thứ xảy ra trong test đều tự rollback chỉ vì method có @Transactional.

### 7.3. Tạo dữ liệu riêng cho mỗi test

Một test song song an toàn nên dùng khóa hoặc định danh dữ liệu không đụng nhau.

Ví dụ, thay vì mọi test dùng cùng email:

~~~java
String email = "parallel-test-" + UUID.randomUUID() + "@example.test";
~~~

Với database lớn, có thể cô lập bằng:

- Database hoặc schema riêng cho từng worker.
- Tenant hoặc namespace riêng.
- ID duy nhất cho mỗi test.
- Cleanup theo owner/test identifier.
- Container database riêng cho nhóm test nếu chi phí cho phép.

Dữ liệu cần được tạo và xóa bằng cơ chế có thể chạy đồng thời. Một cleanup dạng **DELETE FROM customer** có thể xóa dữ liệu mà test khác vừa tạo; hãy xóa theo ID hoặc namespace mà test sở hữu.

### 7.4. @Sql và script cleanup

**@Sql** có thể chạy script trước hoặc sau test. Nếu nhiều test chạy trên cùng database và cùng thực thi script xóa toàn bộ bảng hoặc chèn các khóa cố định, chúng có thể tranh chấp.

Ví dụ nguy hiểm:

~~~sql
DELETE FROM customer;
INSERT INTO customer(id, email) VALUES (1, 'test@example.test');
~~~

Hai test chạy song song có thể xóa dữ liệu của nhau hoặc vi phạm unique constraint. Hãy dùng script chỉ thao tác dữ liệu thuộc test đó, hoặc đưa test dùng script toàn cục vào nhóm tuần tự.

### 7.5. Test bất đồng bộ không tự nằm trong transaction của test

Transaction test-managed của Spring được gắn với thread thực thi test. Nếu test khởi chạy công việc trên thread khác, ví dụ @Async, CompletableFuture hoặc executor, công việc đó không tự động tham gia transaction của thread test.

~~~java
@Test
@Transactional
void startsAsyncWork() {
    service.startAsyncUpdate();

    // Không được giả định worker thread đã chạy trong transaction này.
}
~~~

Test cần chờ công việc hoàn tất bằng cơ chế đồng bộ rõ ràng và xác nhận dữ liệu sau khi worker commit. Không kết thúc test hoặc rollback transaction trước khi tác vụ nền hoàn thành nếu tác vụ còn phụ thuộc dữ liệu test.

Với reactive transaction, transaction context có quy tắc truyền qua Reactor Context; không nên áp dụng giả định ThreadLocal của imperative transaction cho mọi pipeline reactive. Hãy dùng API reactive transaction và test theo đúng mô hình thực thi của ứng dụng.

## 8. Điều kiện về HTTP server, client và mock server

### 8.1. MockRestServiceServer có trạng thái expectation

MockRestServiceServer lưu expectation và response đã xếp hàng cho client được bind. Nếu nhiều test dùng chung một server instance, chúng có thể cùng thêm expectation, gửi request hoặc gọi verify/reset.

Điều này dễ tạo lỗi nếu expectation có thứ tự hoặc server được dùng chung qua singleton bean. Với test chạy song song, ưu tiên tạo MockRestServiceServer và client riêng cho từng test hoặc từng fixture cô lập.

Không dùng một static MockRestServiceServer với queue mutable cho nhiều test concurrent nếu không có cơ chế đồng bộ và cách phân biệt request rõ ràng.

### 8.2. MockWebServer và WireMock cần vòng đời riêng

MockWebServer có queue request/response và port đang lắng nghe. Nếu nhiều test dùng chung một instance, response có thể bị test khác tiêu thụ trước hoặc RecordedRequest có thể bị đọc nhầm.

Nên:

- Tạo server riêng cho mỗi test hoặc fixture có quyền sở hữu rõ ràng.
- Dùng port động.
- Đóng server trong teardown.
- Không chia sẻ queue response mutable giữa test concurrent.
- Chờ request bằng timeout hữu hạn.
- Không dùng một server static cho nhiều test nếu không có cơ chế phân vùng request.

WireMock cũng có trạng thái mapping và request journal. Reset mapping hoặc journal trong khi test khác đang dùng server có thể làm kết quả không xác định.

### 8.3. Embedded server và random port

Các test dùng Spring Boot random port hoặc server test có thể chia sẻ cùng ApplicationContext và server instance nếu context được cache. Điều này không tự động sai: nhiều test có thể gọi cùng server nếu endpoint stateless và dữ liệu được cô lập.

Nhưng cần chú ý:

- Test không được giả định port cố định.
- Không dừng server trong khi test khác đang dùng context.
- Không thay đổi cấu hình global của server trong khi request khác đang chạy.
- Dữ liệu và request state phải được phân biệt giữa các test.
- Test gọi endpoint reset toàn bộ ứng dụng cần được tuần tự hóa hoặc dùng instance riêng.

### 8.4. Không dùng cùng port hoặc file tạm cố định

Các test khởi động HTTP server, broker hoặc file service trên port cố định có thể xung đột khi chạy đồng thời. Dùng port được cấp động và truyền địa chỉ thực tế cho client.

Tương tự, không ghi nhiều test vào cùng một file tạm hoặc thư mục có tên cố định. Dùng thư mục test riêng, UUID hoặc cơ chế tạo file tạm của JUnit.

## 9. Điều kiện về system properties và trạng thái toàn JVM

Một số trạng thái không thuộc ApplicationContext nhưng vẫn được chia sẻ giữa mọi test trong cùng JVM:

- System properties.
- Default Locale và TimeZone.
- System.out/System.err.
- Static singleton hoặc cache.
- Default security provider.
- Shutdown hook và JVM-wide registry.
- File và thư mục tạm dùng chung.

Ví dụ:

~~~java
@Test
void changesSystemProperty() {
    System.setProperty("feature.mode", "test");
}
~~~

Nếu test khác đồng thời đọc hoặc ghi cùng property, kết quả phụ thuộc thời điểm. Hãy lưu giá trị cũ, khôi phục trong finally/teardown và dùng resource lock để ngăn các test trong cùng JUnit engine truy cập đồng thời.

JUnit Jupiter hỗ trợ **@ResourceLock**:

~~~java
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
class TestsChangingSystemProperties {

    @Test
    void changesPropertyForThisScenario() {
        // Thay đổi system property.
    }
}
~~~

Có thể dùng resource name tự định nghĩa cho tài nguyên dùng chung:

~~~java
@ResourceLock(
        value = "shared-test-database",
        mode = ResourceAccessMode.READ_WRITE
)
class TestsUsingGlobalDatabaseReset {
    // Các test cần độc quyền với database dùng chung.
}
~~~

Mọi test có thể truy cập cùng tài nguyên cần dùng chung tên lock và chế độ tương thích. Resource lock chỉ điều phối trong JUnit test plan của cùng engine. Nó không khóa process khác, JVM fork khác, ứng dụng đang chạy bên ngoài hoặc người dùng đang thao tác database.

Nếu tài nguyên có thể được tạo riêng cho từng test, cô lập tài nguyên thường đơn giản và mở rộng tốt hơn việc khóa toàn bộ nhóm test.

## 10. Điều kiện về @DynamicPropertySource và cấu hình context

### 10.1. Giá trị dynamic property cần ổn định trong vòng đời context

**@DynamicPropertySource** thường dùng để đăng ký URL, port hoặc credential từ tài nguyên test như Testcontainers.

~~~java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Các giá trị này được dùng khi Spring tạo ApplicationContext. Nếu context được cache, datasource có thể tiếp tục giữ URL và connection tới container đã được tạo trong lần khởi tạo đó.

Không nên thay đổi giá trị mà dynamic property source trả về trong khi một context đang được chia sẻ. Nếu hai test class cần endpoint khác nhau, hãy dùng context key khác hoặc tạo cấu hình test riêng.

### 10.2. Testcontainers dùng chung và dữ liệu dùng chung

Một container static dùng chung trong một test class hoặc test suite có thể giảm thời gian khởi động. Nhưng database bên trong container vẫn là một tài nguyên dùng chung.

Cần quyết định:

- Mỗi test dùng schema riêng hay chung schema?
- Dữ liệu có khóa duy nhất không?
- Cleanup có xóa đúng phần dữ liệu do test tạo không?
- Container có bị dừng trong khi test khác còn sử dụng không?
- Các test có chạy ở nhiều JVM fork không?

Static container trong một JVM không tự động được chia sẻ với JVM fork khác. Mỗi fork có thể tạo container riêng hoặc kết nối đến một database bên ngoài dùng chung; cả hai trường hợp cần được cấu hình rõ.

### 10.3. Context customizer và cache key

Các cấu hình như active profile, property source, bean override hoặc context customizer có thể làm thay đổi cache key. Hai test class tưởng như giống nhau nhưng có cấu hình khác có thể tạo hai context khác nhau; ngược lại, hai class có cùng cấu hình có thể dùng chung context.

Không nên dựa vào tên class để suy đoán context riêng hay chung. Hãy xem cấu hình test hiệu lực và các thành phần được inject. Khi một test cần trạng thái hoàn toàn riêng, hãy tạo ranh giới cấu hình rõ ràng thay vì chỉ đổi tên test class.

## 11. Tác vụ bất đồng bộ và đồng bộ hóa trong test

### 11.1. Không để test kết thúc khi công việc nền chưa xong

Một test khởi chạy @Async, executor hoặc reactive pipeline cần chờ kết quả trước khi kết thúc:

~~~java
@Test
void waitsForAsyncResult() {
    CompletableFuture<String> future = service.fetchAsync();

    String value = future.orTimeout(5, TimeUnit.SECONDS).join();

    assertThat(value).isEqualTo("completed");
}
~~~

Ví dụ dùng timeout hữu hạn để tránh test treo. Trong ứng dụng thực tế, chọn cách chờ phù hợp với API và xử lý exception từ future để test báo đúng lỗi gốc.

Nếu test kết thúc trước khi công việc nền hoàn thành, teardown có thể đóng context, xóa dữ liệu hoặc dừng container trong khi worker vẫn đang truy cập chúng.

### 11.2. Với Reactor, subscribe và verify tín hiệu

Không chỉ tạo Mono hoặc Flux rồi giả định nó đã thực thi. Dùng StepVerifier hoặc một cơ chế subscription có thời hạn:

~~~java
StepVerifier.create(service.fetchEvents())
        .expectNextMatches(event -> event.type().equals("CREATED"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Khi test hủy stream, xác nhận tài nguyên và công việc upstream được giải phóng theo thiết kế. Với stream dài hạn, cancellation là một phần quan trọng của vòng đời test.

### 11.3. Không dùng Thread.sleep làm đồng bộ

~~~java
@Test
void waitsForBackgroundWork() throws InterruptedException {
    service.startAsync();
    Thread.sleep(1000);
    // Kiểm tra trạng thái.
}
~~~

Cách này không bảo đảm worker đã hoàn tất sau một giây và làm test chậm ngay cả khi công việc hoàn tất sớm. Dùng Future, CountDownLatch, Awaitility hoặc StepVerifier để chờ điều kiện cụ thể với timeout hữu hạn.

Nếu dùng latch hoặc shared signal, mỗi test cần một instance riêng. Không tái sử dụng một latch static giữa các test concurrent.

## 12. Resource lock và cách cô lập test

### 12.1. Khi nào dùng @ResourceLock?

Dùng resource lock khi nhiều test cần truy cập một tài nguyên có tên rõ ràng và không thể tạo riêng ngay:

- System properties.
- Một file cấu hình dùng chung.
- Database test toàn cục cần reset.
- Singleton fixture có trạng thái mutable.
- Một mock server dùng chung có queue hoặc mapping mutable.

Ví dụ:

~~~java
@ResourceLock(
        value = "catalog-wiremock",
        mode = ResourceAccessMode.READ_WRITE
)
class CatalogWireMockTests {
    // Cấu hình hoặc reset WireMock dùng chung.
}
~~~

Các test khác cũng truy cập WireMock đó phải khai báo cùng resource name. Nếu một class không khai báo lock, JUnit không thể tự biết class đó đang dùng tài nguyên nào.

### 12.2. READ và READ_WRITE

**READ** cho phép các test cùng đọc tài nguyên khi không có writer đang giữ lock. **READ_WRITE** yêu cầu quyền độc quyền để đọc/ghi hoặc thay đổi tài nguyên.

Dùng READ chỉ khi test thực sự không thay đổi trạng thái dùng chung. Một request GET vẫn có thể thay đổi request journal, cache, counter hoặc audit log ở phía server; hãy xét trạng thái thực tế thay vì chỉ dựa vào HTTP method.

### 12.3. @Isolated cho test cần chạy riêng

Nếu một class cần thay đổi trạng thái toàn cục hoặc đóng tài nguyên được chia sẻ rộng, **@Isolated** có thể bảo đảm class đó không chạy đồng thời với các test khác trong cùng JUnit test plan.

~~~java
@Isolated
class GlobalEnvironmentTests {

    @Test
    void changesGlobalLocale() {
        // Thay đổi locale toàn JVM và khôi phục sau test.
    }
}
~~~

@Isolated là biện pháp rộng. Dùng nó khi tài nguyên khó mô hình hóa bằng resource lock hoặc khi test thay đổi môi trường dùng chung trên phạm vi lớn. Nó không đồng bộ giữa nhiều process/JVM hoặc dịch vụ bên ngoài.

### 12.4. Ưu tiên fixture riêng hơn khóa toàn cục

Nếu mỗi test có database schema, mock server, temp directory và test data riêng, các test có thể chạy đồng thời mà không phải chờ nhau.

Khóa hữu ích cho tài nguyên bắt buộc dùng chung. Nhưng nếu khóa quá rộng, parallel execution có thể chỉ tạo thêm scheduler overhead mà không tăng tốc. Cô lập fixture thường mang lại khả năng mở rộng tốt hơn.

## 13. Chạy song song trong build tool và giới hạn của lock

### 13.1. JUnit threads và JVM forks là hai mức khác nhau

Một build có thể chạy test song song theo hai cách:

- Nhiều test thread trong cùng JVM do JUnit Jupiter quản lý.
- Nhiều JVM fork do build tool khởi chạy.

Context cache và resource lock của JUnit chỉ tồn tại trong phạm vi JVM/test engine tương ứng. Hai JVM fork không chia sẻ context cache hoặc lock của nhau.

Nếu hai fork cùng dùng một database, file, port hoặc WireMock server bên ngoài, JUnit @ResourceLock trong mỗi fork không ngăn được xung đột giữa chúng.

### 13.2. Gradle

Gradle có thể chạy nhiều test process bằng maxParallelForks:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()

    maxParallelForks = 2
}
~~~

Thiết lập này điều khiển số fork process cho task Test. Nó khác với thuộc tính parallel execution của JUnit Jupiter. Có thể kết hợp cả hai, nhưng tổng concurrency cần được tính đến khi database và container có giới hạn tài nguyên.

Nếu chỉ muốn thử parallel execution trong một JVM, hãy bắt đầu bằng cấu hình JUnit và giữ maxParallelForks ở mức 1. Sau khi kiểm chứng dữ liệu, fixture và context, mới tăng số fork nếu cần.

### 13.3. Maven Surefire

Maven Surefire cũng có thể fork nhiều JVM hoặc cấu hình thực thi song song theo provider. Các thuộc tính JUnit Platform vẫn điều khiển parallel execution trong mỗi JVM khi dùng JUnit Jupiter.

Cần kiểm tra cả cấu hình Surefire/Failsafe và JUnit. Một resource lock không phải cơ chế khóa dùng chung cho nhiều fork.

### 13.4. Tính concurrency tổng thể

Nếu có 2 JVM fork và mỗi JVM cho phép 4 test chạy đồng thời, hệ thống có thể phải phục vụ nhiều test cùng lúc hơn so với chỉ nhìn một thuộc tính parallelism.

Tính đến:

- Số fork process.
- Parallelism của JUnit trong mỗi process.
- Context được khởi tạo đồng thời.
- Connection pool và database connection limit.
- Số container, server và port.
- CPU/RAM của CI runner.

Tăng concurrency từng bước và theo dõi thời gian thực tế, không mặc định rằng càng nhiều thread thì build càng nhanh.

## 14. Những trường hợp nên chạy tuần tự

Một test hoặc nhóm test nên chạy tuần tự khi có một trong các đặc điểm sau:

- Dùng @DirtiesContext và có thể chia sẻ context với test khác.
- Thay đổi singleton bean hoặc mock bean dùng chung.
- Gọi reset trên một mock server hoặc WireMock server dùng chung.
- Dùng dữ liệu database cố định và cleanup toàn bảng.
- Thay đổi system property, locale, timezone hoặc trạng thái JVM toàn cục.
- Dựa vào thứ tự giữa test method.
- Dùng port, file hoặc thư mục cố định.
- Dừng container, embedded server hoặc executor được test khác dùng.
- Khởi chạy async task nhưng teardown không chờ hoàn tất.
- Ghi vào cùng một file hoặc cùng một tài nguyên bên ngoài không có cơ chế cô lập.

Có thể dùng @Execution(SAME_THREAD), @ResourceLock hoặc @Isolated tùy phạm vi. Nếu xung đột nằm giữa các JVM fork hoặc process bên ngoài, cần cô lập tài nguyên ở mức hệ thống hoặc giảm fork; annotation của JUnit không đủ.

## 15. Ma trận đánh giá mức phù hợp để chạy song song

| Điều kiện | Phù hợp | Cần xử lý trước |
|---|---|---|
| Test không phụ thuộc thứ tự và dùng dữ liệu riêng | Có | — |
| Bean dùng chung stateless/immutable hoặc thread-safe | Có | — |
| Mỗi test có mock server và client riêng | Có | — |
| Nhiều test ghi cùng bảng với ID cố định | — | Tạo dữ liệu riêng hoặc khóa |
| Cùng context và cùng @MockitoBean được stubbing khác nhau | — | Tách context hoặc tuần tự hóa |
| Test đóng context bằng @DirtiesContext | — | Cô lập hoặc chạy tuần tự với context liên quan |
| Thay đổi system properties | — | Resource lock hoặc @Isolated |
| Dùng một WireMock instance có reset mapping | — | Server riêng hoặc lock chung |
| Async work hoàn tất và được chờ trước teardown | Có | — |
| Async work còn chạy sau khi test kết thúc | — | Thêm đồng bộ và cleanup |
| Test dựa vào thứ tự method | — | Viết lại thành kịch bản độc lập hoặc tuần tự |
| Nhiều JVM cùng thao tác một database ngoài process | — | Cô lập database/schema hoặc khóa liên process |

Một test chỉ nên được đánh dấu concurrent sau khi các trạng thái và tài nguyên nó sử dụng đã được xác định. Nếu chưa biết một bean hoặc fixture có được chia sẻ không, hãy xem nó là tài nguyên dùng chung cho đến khi chứng minh được điều ngược lại.

## 16. Ví dụ cấu hình một nhóm test an toàn hơn

### 16.1. Cấu hình JUnit

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

Cấu hình này cho phép các class chạy đồng thời nhưng mặc định giữ các node con trong class trên cùng thread. Có thể chọn chế độ method concurrent cho class cụ thể sau khi xác nhận test method độc lập.

### 16.2. Class có dữ liệu riêng và không đóng context

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@Execution(ExecutionMode.CONCURRENT)
class IndependentOrderTests {

    @Autowired
    OrderService orderService;

    @Test
    void handlesFirstOrder() {
        String id = "test-" + UUID.randomUUID();

        // Dữ liệu thuộc riêng kịch bản này.
        orderService.createOrder(id);
    }

    @Test
    void handlesSecondOrder() {
        String id = "test-" + UUID.randomUUID();

        // Không dùng lại ID hoặc cleanup của test khác.
        orderService.createOrder(id);
    }
}
~~~

Ví dụ minh họa điều kiện độc lập của dữ liệu. Bean OrderService được chia sẻ qua context, nên nó và các dependency singleton phải được thiết kế thread-safe. Nếu service ghi database, schema phải cho phép hai test cùng hoạt động và cleanup phải theo ID riêng.

### 16.3. Class cần độc quyền với tài nguyên toàn cục

~~~java
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
@Execution(ExecutionMode.SAME_THREAD)
class SystemPropertyTests {

    private String previousValue;

    @BeforeEach
    void rememberProperty() {
        previousValue = System.getProperty("feature.mode");
    }

    @AfterEach
    void restoreProperty() {
        if (previousValue == null) {
            System.clearProperty("feature.mode");
        } else {
            System.setProperty("feature.mode", previousValue);
        }
    }

    @Test
    void changesFeatureMode() {
        System.setProperty("feature.mode", "test");
        assertThat(System.getProperty("feature.mode")).isEqualTo("test");
    }
}
~~~

Resource lock phải được khai báo bởi mọi test truy cập system properties trong cùng test plan. Lưu và khôi phục giá trị cũ giúp tránh để trạng thái rò sang test sau.

### 16.4. Class làm hỏng context

~~~java
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {

    @Test
    void changesContextManagedState() {
        // Kịch bản thực sự cần loại context khỏi cache.
    }
}
~~~

Class này chạy tách khỏi các test khác trong cùng JUnit test plan và context bị đánh dấu loại bỏ sau class. Nếu có process khác dùng cùng database hoặc tài nguyên ngoài JVM, vẫn cần cơ chế cô lập riêng.

## 17. Cách triển khai parallel execution an toàn theo từng giai đoạn

Không nên bật đồng thời tất cả test của một project lớn rồi chỉ sửa các lỗi phát sinh ngẫu nhiên. Có thể triển khai từng bước:

### Bước 1: Phân loại tài nguyên

Lập danh sách những gì test sử dụng:

- ApplicationContext và singleton bean.
- MockitoBean/MockitoSpyBean.
- Database, transaction, schema và SQL script.
- MockRestServiceServer, MockWebServer, WireMock.
- Embedded server, container và port.
- System property, static state, file và thư mục tạm.
- Executor, scheduler và reactive stream.

Ghi rõ tài nguyên nào được tạo riêng cho test và tài nguyên nào được chia sẻ.

### Bước 2: Chạy song song một nhóm test độc lập

Bắt đầu với unit test hoặc adapter test có fixture riêng. Dùng JUnit parallelism nhỏ để phát hiện race condition và tranh chấp tài nguyên.

Không chọn test dựa trên việc chúng đang chạy nhanh; hãy chọn dựa trên mức cô lập thực tế.

### Bước 3: Tách test có trạng thái dùng chung

Tạo database record, schema hoặc mock server riêng. Loại bỏ cleanup toàn cục. Nếu test cần reset singleton hoặc context, đặt nhóm đó trong resource lock hoặc chạy tuần tự.

### Bước 4: Kiểm tra vòng đời async và context

Bảo đảm future, executor task và Flux được hoàn tất hoặc hủy trước teardown. Không để @DirtiesContext, container shutdown hoặc database cleanup xảy ra khi test khác còn sử dụng.

### Bước 5: Tăng concurrency có kiểm soát

Tăng parallelism theo từng mức và đo:

- Thời gian build.
- Số lỗi chập chờn.
- Thời gian khởi tạo context.
- RAM/CPU.
- Database connection usage.
- Số container và server đồng thời.

Nếu tốc độ không cải thiện hoặc lỗi không xác định tăng, giảm concurrency và tìm bottleneck thực tế.

## 18. Những dấu hiệu test chưa an toàn khi chạy song song

Các dấu hiệu phổ biến:

- Test pass khi chạy riêng nhưng fail khi chạy cả suite.
- Lỗi unique constraint xuất hiện không ổn định.
- Một test nhận response của test khác từ mock server.
- Mockito verification có invocation ngoài dự kiến.
- Bean bị đóng hoặc context bị refresh giữa request.
- Port đã được sử dụng hoặc server không khởi động được.
- Test đọc thấy dữ liệu của kịch bản khác.
- Async task ghi dữ liệu sau khi cleanup đã chạy.
- Lỗi biến mất khi thêm Thread.sleep.
- Kết quả thay đổi theo thứ tự test hoặc số fork.

Đây thường là dấu hiệu của shared mutable state, dữ liệu không cô lập hoặc vòng đời tài nguyên không được đồng bộ. Không nên khắc phục bằng cách thêm sleep hoặc retry test; hãy xác định chính xác tài nguyên bị chia sẻ và thiết lập quyền sở hữu rõ ràng.

## 19. Nguyên tắc thực hành

1. Phân biệt JUnit parallel scheduler với Spring TestContext context cache.
2. Chỉ bật CONCURRENT cho test không phụ thuộc thứ tự và không tranh chấp trạng thái.
3. Giả định singleton bean trong context cache có thể được nhiều test dùng chung.
4. Ưu tiên bean stateless, immutable và fixture riêng.
5. Chú ý PER_CLASS vì nhiều method có thể dùng cùng test instance.
6. Tránh chạy song song các test thay đổi hoặc đóng cùng ApplicationContext bằng @DirtiesContext.
7. Không stubbing, reset hoặc verify đồng thời cùng một @MockitoBean dùng chung.
8. Tách dữ liệu database theo test và không dùng cleanup toàn cục.
9. Nhớ rằng transaction test-managed không bao trùm tự động các thread hoặc dịch vụ bên ngoài.
10. Dùng MockRestServiceServer, MockWebServer và WireMock riêng cho từng test hoặc khóa tài nguyên dùng chung.
11. Dùng @ResourceLock cho trạng thái toàn JVM trong cùng JUnit engine; dùng @Isolated cho test cần chạy riêng.
12. Không xem JUnit resource lock là khóa liên process hoặc liên JVM.
13. Chờ async task và hủy reactive stream trước khi teardown.
14. Dùng port động và thư mục tạm riêng.
15. Tăng concurrency theo từng giai đoạn và theo dõi cả độ ổn định lẫn hiệu năng.

Spring TestContext Framework có thể tái sử dụng ApplicationContext trong lúc JUnit chạy nhiều test đồng thời. Điều kiện quyết định là các test phải độc lập về dữ liệu, trạng thái bean, mock và vòng đời tài nguyên. Khi context hoặc fixture có trạng thái mutable, cần cô lập hoặc đồng bộ rõ ràng. Chỉ sau khi các điều kiện đó được bảo đảm, parallel execution mới giúp giảm thời gian kiểm thử mà vẫn giữ kết quả ổn định.

