# Spy gọi hành vi thật và nguy cơ tác dụng phụ khi thiết lập

Trong Mockito, spy là một test double giữ phần lớn hành vi thật của một đối tượng. Khi gọi một phương thức chưa được stub, spy thường thực thi implementation thật. Điều này hữu ích khi cần thay thế có chọn lọc một vài hành vi trong một đối tượng cũ hoặc khi muốn quan sát tương tác mà vẫn giữ phần xử lý còn lại.

Tuy nhiên, chính việc gọi hành vi thật tạo ra một rủi ro dễ bỏ sót: **cú pháp stubbing thông thường `when(spy.method()).thenReturn(...)` gọi phương thức thật ngay trong lúc thiết lập test**. Nếu phương thức đó ghi database, gửi HTTP request, phát message, ghi file, gửi email hoặc thay đổi trạng thái dùng chung, tác dụng phụ có thể xảy ra trước cả khi phần Act của test bắt đầu.

Với spy, cần hiểu rõ thời điểm lời gọi thật xảy ra, chọn đúng API stubbing và kiểm soát dependency bên ngoài. Bài học này tập trung vào cơ chế đó trong bối cảnh kiểm thử đơn vị với Spring và Mockito.

## 1. Spy khác mock và object thật như thế nào?

Mock thường trả về giá trị đã được cấu hình hoặc giá trị mặc định và ghi nhận tương tác. Nó không tự chạy implementation thật của các phương thức thông thường. Spy giữ hành vi thật của đối tượng; những phương thức chưa bị stub sẽ được thực thi như khi gọi object thật.

| Đặc điểm | Object thật | Mock | Spy |
| --- | --- | --- | --- |
| Phương thức chưa stub | Chạy implementation thật | Không chạy implementation thật theo mặc định | Chạy implementation thật |
| Có thể stub phương thức | Không qua Mockito | Có | Có |
| Có thể verify lời gọi | Không trực tiếp bằng Mockito | Có | Có |
| Có nguy cơ side effect khi gọi phương thức | Có | Thường không từ implementation của mock | Có |
| Mục đích điển hình | Kiểm tra hành vi thật với dependency được kiểm soát | Thay thế dependency và xác nhận tương tác | Thay thế có chọn lọc một số hành vi của object thật |

Spy thường được tạo từ một object đã khởi tạo:

```java
InventoryService realService = new InventoryService(repository);
InventoryService spyService = Mockito.spy(realService);
```

Hoặc dùng static import:

```java
InventoryService spyService = spy(new InventoryService(repository));
```

Hãy dùng biến trả về từ `spy(...)` làm tham chiếu cho test. Mockito tạo một spy có trạng thái ban đầu lấy từ object được truyền vào; spy không phải một wrapper ủy quyền mọi lời gọi tới đúng instance gốc. Vì vậy, không nên giữ hai tham chiếu rồi kỳ vọng thay đổi trạng thái trên object ban đầu luôn đồng bộ với spy.

## 2. Vì sao `when(spy.method()).thenReturn(...)` có thể gây tác dụng phụ?

Java đánh giá đối số trước khi gọi phương thức bên ngoài. Khi viết:

```java
when(spyService.reserve("BOOK-1", 2)).thenReturn(true);
```

thì `spyService.reserve("BOOK-1", 2)` được gọi trước để Mockito ghi nhận lời gọi cần stub. Vì đây là spy, phương thức thật có thể chạy ngay ở bước thiết lập.

Giả sử service có implementation sau:

```java
class InventoryService {

    private final InventoryRepository repository;

    InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public boolean reserve(String sku, int quantity) {
        Stock stock = repository.findBySku(sku).orElseThrow();

        if (stock.availableQuantity() < quantity) {
            return false;
        }

        stock.reserve(quantity);
        repository.save(stock);
        return true;
    }
}
```

Nếu `repository` là database thật, lệnh stubbing phía trên có thể đọc và cập nhật tồn kho thật ngay trong Arrange. Nếu dữ liệu không tồn tại, nó còn có thể ném exception trước khi test chạy tới Act. Nếu phương thức gửi yêu cầu đến hệ thống ngoài, test có thể vô tình tạo giao dịch thật.

Đây là khác biệt quan trọng giữa mock và spy: khi stub một mock bằng `when(mock.method())`, implementation thật của method không được gọi theo cách thông thường; với spy, method thật được gọi để tạo lời gọi cần ghi nhận.

## 3. Dùng `doReturn(...).when(spy)...` để stub an toàn

Mockito cung cấp nhóm API `doReturn`, `doThrow`, `doAnswer`, `doNothing` và `doCallRealMethod`. Cú pháp `doReturn(...).when(spy).method(...)` thiết lập stub mà không cần gọi implementation thật của method trong lúc cấu hình.

Thay ví dụ nguy hiểm bằng:

```java
InventoryService spyService = spy(new InventoryService(repository));

doReturn(true)
    .when(spyService)
    .reserve("BOOK-1", 2);
```

Lúc này, khi một thành phần khác gọi `spyService.reserve("BOOK-1", 2)`, Mockito trả về `true` theo stub. Phương thức `reserve()` thật không chạy ở thời điểm thiết lập và cũng không chạy cho lời gọi khớp stub.

Có thể dùng argument matcher:

```java
doReturn(true)
    .when(spyService)
    .reserve(eq("BOOK-1"), anyInt());
```

Khi dùng matcher, tất cả đối số trong cùng lời gọi phải tuân theo quy tắc matcher của Mockito. Ví dụ `eq("BOOK-1")` đi cùng `anyInt()` là hợp lệ; không nên trộn matcher với giá trị literal ở các tham số khác.

`doReturn()` có ưu điểm là tránh gọi method thật trong quá trình stubbing, nhưng kém an toàn kiểu hơn `when(...).thenReturn(...)`: compiler không kiểm tra kiểu giá trị trả về theo cùng cách chặt chẽ. Chỉ dùng nó khi cần thiết để stub spy hoặc khi API stubbing dạng `do...` là phù hợp.

## 4. Chọn API `do...` theo loại hành vi

Nhóm API của Mockito hỗ trợ các kiểu stubbing khác nhau:

| API | Mục đích | Tình huống dùng với spy |
| --- | --- | --- |
| `doReturn(value)` | Trả về giá trị cố định | Stub method có giá trị trả về mà không chạy method thật lúc thiết lập |
| `doThrow(exception)` | Ném exception | Mô phỏng dependency hoặc nhánh lỗi mà không thực hiện hành vi thật |
| `doAnswer(answer)` | Tùy biến kết quả dựa trên lời gọi | Tạo phản hồi theo tham số hoặc cập nhật một test fixture |
| `doNothing()` | Không thực hiện gì với method `void` | Ngăn method thật gửi email, ghi file hoặc thực hiện side effect |
| `doCallRealMethod()` | Yêu cầu gọi implementation thật | Dùng khi một mock cần gọi method thật; với spy, method thật vốn đã được gọi mặc định nếu chưa stub |

### Stub method có giá trị trả về

```java
doReturn(Optional.of(stock))
    .when(spyRepository)
    .findBySku("BOOK-1");
```

### Stub để ném exception

```java
doThrow(new PaymentGatewayUnavailableException())
    .when(spyGateway)
    .charge(any(PaymentRequest.class));
```

### Stub method `void` để chặn side effect thật

```java
doNothing()
    .when(spyNotificationPort)
    .sendConfirmation(any(OrderConfirmation.class));
```

Nếu không stub method `void` trên spy, implementation thật sẽ chạy khi test gọi method đó. `doNothing()` giúp chặn việc gửi email thật trong trường hợp test chỉ cần quan sát lời gọi.

### Tạo phản hồi tùy theo tham số

```java
doAnswer(invocation -> {
    PaymentRequest request = invocation.getArgument(0);
    return PaymentResult.approved("test-payment-" + request.orderId());
}).when(spyGateway).charge(any(PaymentRequest.class));
```

`doAnswer()` hữu ích khi kết quả cần phụ thuộc dữ liệu đầu vào. Nếu chỉ cần một kết quả cố định, `doReturn()` thường dễ đọc hơn.

## 5. So sánh hai cách stubbing trong cùng một ví dụ

Giả sử `ReportService.loadReport()` đọc dữ liệu từ kho lưu trữ và có thể chạm vào hệ thống thật. Một test khác đang kiểm tra cách `ReportService.export()` xử lý khi không tìm thấy báo cáo.

```java
class ReportService {

    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    public Report loadReport(String id) {
        return repository.findById(id).orElseThrow();
    }

    public byte[] export(String id) {
        Report report = loadReport(id);
        return renderPdf(report);
    }

    private byte[] renderPdf(Report report) {
        // Tạo PDF
        return new byte[0];
    }
}
```

Cách dễ gây gọi thật khi thiết lập:

```java
ReportService spyService = spy(new ReportService(realRepository));

when(spyService.loadReport("missing-report"))
    .thenThrow(new ReportNotFoundException());
```

Trước khi Mockito đăng ký exception cho lời gọi sau này, `loadReport("missing-report")` thật đã chạy. Nó có thể truy vấn database, phát sinh lỗi từ repository hoặc phụ thuộc dữ liệu đang có.

Cách tránh lời gọi thật:

```java
ReportService spyService = spy(new ReportService(realRepository));

doThrow(new ReportNotFoundException())
    .when(spyService)
    .loadReport("missing-report");
```

Khi test gọi `export("missing-report")`, lời gọi nội bộ `loadReport()` trên spy sẽ được stub và ném exception đã cấu hình. Dù vậy, ví dụ này cũng cho thấy spy có thể làm test phụ thuộc cấu trúc nội bộ của class. Nếu mục tiêu là kiểm tra hành vi khi repository không có báo cáo, thiết kế tốt hơn thường là tạo `ReportService` thật với repository mock trả về `Optional.empty()`.

## 6. Spy trên method `void` và tác dụng phụ không mong muốn

Với method `void`, không thể dùng cú pháp `when(spy.method()).thenReturn(...)`. Mockito cung cấp `doNothing()` hoặc `doThrow()`.

Giả sử adapter gửi thông báo:

```java
class EmailNotifier {

    public void send(String recipient, String subject) {
        // Gọi SMTP hoặc email provider thật
    }
}
```

Nếu test muốn quan sát lời gọi nhưng không gửi email thật:

```java
EmailNotifier notifier = spy(new EmailNotifier());

doNothing()
    .when(notifier)
    .send(anyString(), anyString());

service.sendReceipt(notifier);

verify(notifier).send("customer@example.test", "Order receipt");
```

Trong trường hợp này, `doNothing()` ngăn implementation gửi email khi service gọi method. Tuy nhiên, nếu mục tiêu của test là xác nhận chính adapter SMTP gửi đúng request, không nên stub method đó; hãy kiểm tra adapter riêng bằng SMTP sandbox hoặc fake server.

Với method `void` cần mô phỏng lỗi:

```java
doThrow(new NotificationUnavailableException())
    .when(notifier)
    .send(anyString(), anyString());
```

Điều này cho phép kiểm tra cách service xử lý lỗi gửi thông báo mà không thực hiện kết nối thật.

## 7. Nguy cơ tác dụng phụ ngay khi tạo spy

An toàn trong bước stubbing chưa giải quyết tất cả rủi ro. Để tạo spy từ một object, object thật phải được khởi tạo trước:

```java
EmailNotifier realNotifier = new EmailNotifier();
EmailNotifier spyNotifier = spy(realNotifier);
```

Constructor của `EmailNotifier` đã chạy trước khi `spy()` được gọi. Nếu constructor mở socket, tạo thread, đọc cấu hình môi trường, tạo file hoặc kết nối database, side effect đó đã xảy ra. `doReturn()` chỉ ngăn implementation của method bị stub chạy trong lúc stubbing; nó không hoàn tác constructor hay các hành vi khác đã xảy ra.

Hãy xem xét các điểm sau trước khi tạo spy:

- Constructor có thực hiện I/O hoặc khởi động tài nguyên không?
- Các dependency được truyền vào có trỏ tới hệ thống thật không?
- Có method khởi tạo như `@PostConstruct` thực hiện kết nối hoặc ghi dữ liệu không?
- Các method không stub có thể gọi HTTP, database, broker, filesystem hoặc dịch vụ cloud không?
- Đối tượng có giữ trạng thái dùng chung giữa các test không?

Ưu tiên constructor đơn giản, dependency injection và adapter riêng cho I/O. Khi cần kiểm thử logic, truyền mock hoặc fake cho dependency bên ngoài. Khi cần kiểm thử adapter, dựng môi trường giả lập có kiểm soát.

## 8. Spy và trạng thái của đối tượng

Spy gọi implementation thật cho method chưa stub, vì vậy các method có thể thay đổi state của spy. Điều này có thể làm test phụ thuộc thứ tự gọi hoặc trạng thái còn lại từ bước thiết lập.

Ví dụ:

```java
class Counter {
    private int value;

    public int incrementAndGet() {
        return ++value;
    }

    public int currentValue() {
        return value;
    }
}
```

Nếu viết:

```java
Counter counter = spy(new Counter());
when(counter.incrementAndGet()).thenReturn(100);
```

`incrementAndGet()` thật chạy trong lúc thiết lập stubbing và tăng `value` lên 1. Sau đó lời gọi khớp stub trả về 100 mà không tăng giá trị theo implementation thật. Trạng thái nội bộ vì thế không còn như test có thể tưởng tượng.

Nếu mục tiêu là stub method này mà không thay đổi state:

```java
Counter counter = spy(new Counter());
doReturn(100).when(counter).incrementAndGet();
```

Khi dùng spy, hãy xác định rõ trạng thái trước Arrange, sau stubbing và sau Act. Nếu test cần một trạng thái ban đầu cụ thể, tạo object mới cho mỗi test hoặc dùng fixture/reset rõ ràng. Không dựa vào thứ tự chạy của JUnit để trạng thái spy được giữ hay được làm mới.

## 9. Spy có thể gọi các method khác bên trong method thật

Một method trên spy có thể gọi nhiều method khác của cùng object hoặc dependency. Khi method thật được thực thi, những lời gọi nội bộ đó cũng có thể tạo side effect.

Ví dụ `publishReport()` có thể gọi `loadReport()`, `render()`, `writeFile()` rồi `upload()`. Khi stubbing `when(spy.publishReport(id)).thenReturn(result)`, toàn bộ luồng thật có thể chạy trong lúc thiết lập. Một method tưởng như chỉ tính toán cũng có thể gián tiếp ghi file hoặc gọi dịch vụ ngoài.

Vì vậy, trước khi dùng cú pháp `when(...)` trên spy, hãy đọc implementation của method và các method mà nó gọi. Đừng suy luận rằng method an toàn chỉ từ tên hoặc kiểu trả về.

Nếu cần stub một method để chặn luồng nguy hiểm, dùng `doReturn`, `doThrow` hoặc `doNothing` phù hợp. Nếu method đang kiểm thử có quá nhiều nhánh nội bộ và side effect, cân nhắc tách phần I/O thành port và kiểm tra use case bằng mock/fake của port.

## 10. Dùng spy trong unit test có thực sự cần thiết?

Spy thường hữu ích trong các tình huống giới hạn:

- Một class cũ có một vài method khó thay thế và cần stub tạm thời để kiểm tra nhánh khác.
- Cần quan sát lời gọi đến một method của object thật trong khi vẫn giữ hành vi của các method còn lại.
- Một phần implementation có thể chạy an toàn với dependency được kiểm soát, nhưng một method cụ thể cần được thay thế.
- Đang chuyển đổi dần một class lớn sang kiến trúc có port và adapter, chưa thể tách toàn bộ ngay.

Spy thường không phải lựa chọn đầu tiên khi kiểm thử service nghiệp vụ. Nếu test muốn kiểm tra `OrderService` thật, hãy khởi tạo `OrderService` thật với repository, payment port và notification port là mock hoặc fake. Khi đó không cần spy chính service đang kiểm thử.

Ví dụ cấu trúc ưu tiên:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    PaymentPort payment;

    @Mock
    NotificationPort notifications;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(repository, payment, notifications);
    }

    @Test
    void savesOrderWhenPaymentIsApproved() {
        when(payment.charge(any()))
            .thenReturn(PaymentResult.approved("payment-1"));

        service.place(validCommand());

        verify(repository).save(any(Order.class));
    }
}
```

Service là object thật; các dependency có side effect nằm sau port và được thay bằng mock. Test vừa chạy logic thực của service, vừa kiểm soát được tương tác bên ngoài. Đây thường là thiết kế dễ hiểu và ít rủi ro hơn việc spy service rồi stub các method nội bộ.

## 11. Spy trong Spring Test và Spring Boot

Trong test có Spring context, đôi khi cần spy một bean đã được Spring quản lý để giữ phần lớn hành vi thật nhưng thay thế một method cụ thể. Các annotation Spring hỗ trợ đăng ký Mockito spy trong context. Với Spring Framework 6.2 trở lên có `@MockitoSpyBean`; các dự án Spring Boot cũ hơn có thể đang dùng `@SpyBean` từ Spring Boot Test.

Ví dụ với `@MockitoSpyBean`:

```java
@SpringBootTest
class OrderWorkflowTest {

    @MockitoSpyBean
    PaymentAdapter paymentAdapter;

    @Autowired
    OrderService orderService;

    @Test
    void handlesPaymentDeclinedByGateway() {
        doReturn(PaymentResult.declined("declined"))
            .when(paymentAdapter)
            .charge(any(PaymentRequest.class));

        assertThrows(PaymentDeclinedException.class,
            () -> orderService.place(validCommand()));
    }
}
```

Ở đây Spring tạo context và bean; annotation đăng ký spy cho bean được chọn. `doReturn()` ngăn method `charge()` thật được gọi trong lúc stubbing. Nếu dùng `when(paymentAdapter.charge(...)).thenReturn(...)`, adapter có thể gọi cổng thanh toán thật ngay trong bước Arrange.

Spy bean trong Spring vẫn có những rủi ro riêng:

- Context phải khởi tạo bean và dependency của nó; các hành vi khởi tạo như `@PostConstruct` vẫn có thể chạy.
- Bean có thể được proxy bởi Spring AOP cho transaction, security hoặc cache; việc spy bean cần được cấu hình đúng để không làm mất hành vi cần kiểm tra.
- Nếu có nhiều bean cùng kiểu, cần chỉ rõ bean mục tiêu bằng qualifier hoặc tên bean theo API annotation đang dùng.
- Một test context dùng spy có thể được cache và chia sẻ giữa nhiều test; trạng thái hoặc stub còn lại cần được quản lý cẩn thận.
- Spy bean làm test phụ thuộc vào cấu trúc bean của ứng dụng; chỉ nên dùng khi cần kiểm tra tích hợp thực sự.

Khi mục tiêu là kiểm tra transaction, security hoặc AOP, hãy xác nhận test đi qua bean/proxy đúng cách. Không kết luận rằng transaction hoạt động chỉ vì một spy method đã được gọi.

## 12. Spy và các annotation Mockito

Mockito hỗ trợ khởi tạo spy bằng API thủ công hoặc annotation. Ví dụ:

```java
@ExtendWith(MockitoExtension.class)
class LegacyCalculatorTest {

    @Spy
    LegacyCalculator calculator = new LegacyCalculator();

    @Test
    void usesStubbedRateWhenCalculatingTotal() {
        doReturn(0.1).when(calculator).taxRate();

        assertEquals(110.0, calculator.total(100.0));
    }
}
```

`@Spy` cần một instance có thể khởi tạo. Nếu constructor cần dependency, có thể tạo instance rõ ràng với mock/fake hoặc dùng cách khởi tạo phù hợp của Mockito. Đừng cho rằng annotation spy sẽ tự biến một object có constructor phức tạp và side effect thành object an toàn.

`@InjectMocks` có thể kết hợp với spy trong một số cách tổ chức test, nhưng cần đọc rõ object nào là SUT và object nào là dependency. Nếu nhiều annotation cùng tham gia tạo object, test dễ che giấu cách dependency được inject. Tạo đối tượng trực tiếp trong `@BeforeEach` thường minh bạch hơn khi constructor có nhiều port.

## 13. Spy, method final và các giới hạn kỹ thuật

Khả năng spy hoặc stub method phụ thuộc phiên bản Mockito và mock maker đang được cấu hình. Các dự án Mockito hiện đại thường hỗ trợ nhiều trường hợp trước đây bị hạn chế, nhưng không nên mặc định mọi method đều có thể bị intercept trong mọi cấu hình.

Một số điểm cần lưu ý:

- Private method không phải API Mockito thông thường để stub trực tiếp. Nếu private method có logic quan trọng cần kiểm thử riêng, cân nhắc tách logic thành một thành phần có trách nhiệm rõ ràng.
- Method final, class final và một số kiểu đặc biệt phụ thuộc mock maker/phiên bản Mockito.
- Static method cần cơ chế mocking riêng và không phải là mục tiêu tự nhiên của spy instance.
- Native method hoặc method gắn chặt với runtime có thể không phù hợp để spy.
- Một số method có thể bị framework proxy hoặc bytecode instrumentation tác động, làm hành vi khó suy luận.

Nếu Mockito báo lỗi không thể stub hoặc verify một method, hãy xem cấu hình Mockito và thiết kế của class trước khi thêm công cụ phức tạp. Thường một port nhỏ hoặc một adapter tách biệt sẽ làm test ổn định hơn.

## 14. Quản lý stub và reset giữa các test

Spy có state thật, vì vậy một test có thể làm thay đổi trạng thái và ảnh hưởng đến test tiếp theo nếu cùng một spy được chia sẻ. JUnit Jupiter thường tạo instance test class mới cho mỗi test method theo lifecycle mặc định `PER_METHOD`, nhưng Spring context và bean có thể được tái sử dụng giữa nhiều test. Mockito extension cũng quản lý mock/spy theo vòng đời test được khởi tạo.

Hãy ưu tiên tạo spy mới cho mỗi test khi có thể. Nếu dùng spy bean được chia sẻ trong Spring context:

- Dùng API reset của Spring Test/Mockito phù hợp với phiên bản khi cần làm sạch stub và invocation history.
- Không dựa vào thứ tự test để một stub còn tồn tại.
- Không thay đổi state dùng chung mà không khôi phục.
- Cẩn thận khi chạy song song vì một test có thể tương tác với spy trong khi test khác đang thay đổi stub.

Reset mock/spy không nhất thiết khôi phục mọi trạng thái nghiệp vụ của object thật. Nó có thể xóa stubbing và lịch sử invocation nhưng không hoàn tác database, file, message hay side effect đã xảy ra. Muốn cô lập dữ liệu, cần transaction rollback, database riêng, fake state mới hoặc cleanup có kiểm soát.

## 15. Phân biệt side effect của bước Arrange và bước Act

Một test dễ hiểu thường chia thành ba giai đoạn:

1. **Arrange:** tạo fixture, khởi tạo object, cấu hình mock/spy.
2. **Act:** gọi hành vi mà test cần kiểm tra.
3. **Assert:** xác nhận kết quả và tương tác.

Khi stubbing spy bằng `when(spy.method())`, implementation thật có thể chạy trong Arrange. Điều đó phá vỡ kỳ vọng rằng Arrange chỉ chuẩn bị trạng thái. Một test có thể gửi email hoặc cập nhật database trước khi hành động được kiểm tra bắt đầu.

Hãy dùng `doReturn`/`doThrow`/`doNothing` khi stub spy để ngăn method thật chạy trong Arrange. Nếu method thật phải được chạy để kiểm tra hành vi, gọi nó rõ ràng trong Act và chuẩn bị dependency của nó an toàn.

Ví dụ:

```java
@Test
void publishesReportWhenReportIsAvailable() {
    ReportService spyService = spy(new ReportService(repository, publisher));

    doReturn(sampleReport())
        .when(spyService)
        .loadReport("report-7");

    // Act: lời gọi thật của publish() chạy tại đây
    spyService.publish("report-7");

    // Assert: xác nhận port publish nhận báo cáo
    verify(publisher).publish(sampleReport());
}
```

Trong ví dụ, `loadReport()` được stub để không truy vấn repository thật; `publish()` vẫn chạy implementation thật trong Act. Publisher nên là mock hoặc fake để không gửi message thật. Đây là cách dùng spy có kiểm soát, nhưng nếu `publish()` là logic chính cần kiểm tra, hãy cân nhắc tách `loadReport` thành repository port thay vì stub method nội bộ.

## 16. Bảng quyết định: khi nào dùng `when` và khi nào dùng `doReturn`?

| Đối tượng được stub | Cú pháp thường phù hợp | Lý do |
| --- | --- | --- |
| Mock thông thường | `when(mock.method()).thenReturn(value)` | Mock không chạy implementation thật theo mặc định |
| Spy, method thuần và việc gọi thật lúc setup an toàn | Có thể dùng `when(spy.method()).thenReturn(value)` | Method thật được gọi trong lúc setup nhưng không tạo tác dụng phụ đáng lo |
| Spy, method đọc DB/gọi mạng/ghi dữ liệu | `doReturn(value).when(spy).method()` | Tránh gọi implementation thật trong lúc stubbing |
| Spy, method cần ném exception thay vì chạy thật | `doThrow(error).when(spy).method()` | Ngăn side effect thật và mô phỏng nhánh lỗi |
| Spy, method `void` có side effect | `doNothing().when(spy).method()` | Chặn implementation thật |
| Spy, cần phản hồi động theo đối số | `doAnswer(...).when(spy).method()` | Điều khiển hành vi mà không gọi method thật lúc setup |

Không có yêu cầu phải dùng `doReturn` cho mọi stub của spy. Nếu method là pure function, không truy cập state ngoài và việc gọi trong Arrange không gây tác dụng phụ, cú pháp `when(...).thenReturn(...)` vẫn có thể dùng. Tuy nhiên, `doReturn` là lựa chọn an toàn hơn khi không chắc method thật sẽ làm gì.

## 17. Các tình huống nên tránh dùng spy

Hãy cân nhắc lại thiết kế nếu:

- Spy một service chỉ để stub repository hoặc HTTP client. Nên inject mock/fake của port thay vì spy service.
- Spy một bean có constructor hoặc `@PostConstruct` kết nối hệ thống thật. Nên tách khởi tạo tài nguyên sang adapter hoặc lifecycle có kiểm soát.
- Stub nhiều method của cùng một spy. Có thể class đang có quá nhiều trách nhiệm hoặc test đang phụ thuộc cấu trúc nội bộ.
- Dùng spy để kiểm tra transaction, cache hoặc security nhưng test không đi qua Spring proxy thực tế.
- Dùng spy repository thật rồi stub method bằng `when(...)` có thể truy vấn hoặc cập nhật database trong Arrange.
- Spy một object có state dùng chung, thread nền hoặc scheduler đang hoạt động.
- Test cần kiểm soát toàn bộ dependency. Khi đó một object thật với mock/fake dependency thường đơn giản hơn.

Spy là công cụ hỗ trợ kiểm thử, không phải lý do để giữ một class có ranh giới mơ hồ. Nếu việc stub một method nội bộ trở thành điều kiện để test được, hãy xem xét đưa hành vi đó thành collaborator hoặc port có tên rõ ràng.

## 18. Ví dụ so sánh thiết kế với spy và thiết kế qua port

Giả sử `OrderService` vừa tính tổng tiền, vừa truy cập database, vừa gọi payment API và gửi email. Một test dùng spy có thể phải stub `loadCustomer()`, `chargeCard()`, `saveOrder()` và `sendEmail()`. Mỗi lần thay đổi cấu trúc nội bộ, test phải sửa theo.

Một thiết kế tách port:

```java
class OrderService {

    private final CustomerRepository customers;
    private final PaymentPort payments;
    private final OrderRepository orders;
    private final NotificationPort notifications;

    OrderService(
            CustomerRepository customers,
            PaymentPort payments,
            OrderRepository orders,
            NotificationPort notifications) {
        this.customers = customers;
        this.payments = payments;
        this.orders = orders;
        this.notifications = notifications;
    }

    OrderId place(PlaceOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(CustomerNotFoundException::new);

        PaymentResult payment = payments.charge(
            new PaymentRequest(command.amount(), command.paymentToken())
        );

        Order order = Order.create(customer, command, payment);
        orders.save(order);
        notifications.sendOrderConfirmation(order);
        return order.id();
    }
}
```

Unit test tạo service thật và mock các port:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock CustomerRepository customers;
    @Mock PaymentPort payments;
    @Mock OrderRepository orders;
    @Mock NotificationPort notifications;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(customers, payments, orders, notifications);
    }

    @Test
    void doesNotSendConfirmationWhenPaymentIsDeclined() {
        when(customers.findById("customer-42"))
            .thenReturn(Optional.of(sampleCustomer()));
        when(payments.charge(any()))
            .thenReturn(PaymentResult.declined("declined"));

        assertThrows(PaymentDeclinedException.class,
            () -> service.place(validCommand()));

        verify(orders, never()).save(any());
        verify(notifications, never()).sendOrderConfirmation(any());
    }
}
```

Test không cần spy `OrderService`. Nó chạy logic thật, còn các tác dụng phụ được kiểm soát tại port. Cách này giúp test bám vào hợp đồng của ứng dụng thay vì method nội bộ.

## 19. Checklist an toàn khi stubbing spy

Trước khi thiết lập stub cho spy, hãy xác định:

- Method thật có chạy ngay khi viết `when(spy.method())` không?
- Method đó có gọi database, HTTP, broker, email, filesystem hoặc dịch vụ cloud không?
- Method có thay đổi state, tăng counter, ghi audit hoặc phát event không?
- Constructor và lifecycle callback đã tạo tài nguyên thật chưa?
- Có thể dùng `doReturn`, `doThrow`, `doNothing` hoặc `doAnswer` để tránh thực thi method trong Arrange không?
- Dependency bên ngoài có thể thay bằng mock/fake để Act an toàn không?
- Test đang kiểm tra hành vi công khai hay đang stub quá nhiều method nội bộ?
- Có cần integration test riêng để chứng minh adapter, Spring proxy hoặc transaction không?

Nếu không thể trả lời chắc chắn về side effect của method thật, hãy đọc implementation và dependency của nó trước khi stubbing. Đừng coi một lời gọi trong biểu thức `when(...)` là thao tác khai báo thuần túy khi đối tượng được stub là spy.

## 20. Quy trình dùng spy có kiểm soát

1. **Xác định mục tiêu:** nêu rõ method nào cần giữ hành vi thật và method nào cần stub.
2. **Kiểm tra khởi tạo:** xem constructor, dependency và lifecycle có tạo side effect hay không.
3. **Cô lập I/O:** thay database, HTTP, message broker, email và filesystem bằng adapter test hoặc test double phù hợp.
4. **Chọn cú pháp stubbing:** với spy, ưu tiên `doReturn`, `doThrow`, `doNothing` hoặc `doAnswer` nếu không muốn method thật chạy trong Arrange.
5. **Gọi hành vi thật trong Act:** chỉ để method thật chạy ở thời điểm test chủ đích kiểm tra nó.
6. **Xác nhận kết quả:** kiểm tra kết quả nghiệp vụ và các tương tác qua port có ý nghĩa.
7. **Đánh giá lại sự cần thiết:** nếu phải stub nhiều method nội bộ, tách dependency hoặc chuyển sang test object thật với mock/fake collaborator.

Spy rất hữu ích khi cần giữ một phần hành vi thật, nhưng nó cũng có thể thực hiện side effect ngoài ý muốn trong lúc thiết lập. Với Mockito, khác biệt quan trọng nằm ở cách Java đánh giá lời gọi trong `when(spy.method())`; dùng nhóm API `do...` để stub mà không chạy implementation thật. Trong ứng dụng Spring, hãy kiểm soát cả việc khởi tạo bean, dependency, proxy và lifecycle. Khi ranh giới I/O được đưa qua port rõ ràng, phần lớn unit test có thể dùng object thật với mock/fake dependency và chỉ cần spy cho những tình huống thực sự cần thiết.
