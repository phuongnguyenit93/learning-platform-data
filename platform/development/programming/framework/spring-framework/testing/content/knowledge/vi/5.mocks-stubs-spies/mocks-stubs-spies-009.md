# Reset trạng thái, strict stubbing và cấu hình thừa

Mock và spy giúp kiểm soát collaborator trong unit test, nhưng chúng cũng giữ trạng thái trong suốt một lần chạy test. Một mock có thể lưu các hành vi đã stub và lịch sử lời gọi; một spy còn bọc một object thật nên có thể giữ cả trạng thái nghiệp vụ của object đó. Nếu trạng thái này bị chia sẻ hoặc cấu hình quá rộng, test có thể phụ thuộc vào nhau, che giấu lỗi hoặc thất bại vì những stub không bao giờ được dùng.

Mockito cung cấp cơ chế reset, clear invocation và strict stubbing để quản lý những vấn đề này. Cần hiểu mỗi cơ chế thay đổi phần trạng thái nào và dùng nó đúng chỗ. Trong phần lớn unit test, tạo mock mới cho mỗi test và chỉ khai báo những stub mà test đó cần là cách đơn giản, dễ đọc nhất.

## Mock giữ những trạng thái nào?

Một mock Mockito thường có hai nhóm trạng thái quan trọng:

1. **Stubbing:** hành vi giả lập đã cấu hình, ví dụ khi gọi `findById(10)` thì trả về một object cụ thể.
2. **Invocation history:** lịch sử những phương thức đã được gọi, gồm phương thức, đối số và số lần gọi.

~~~java
when(repository.findById(10L)).thenReturn(Optional.of(customer));

service.load(10L);

verify(repository).findById(10L);
~~~

Dòng `when(...).thenReturn(...)` cấu hình stubbing. Khi service gọi repository, Mockito ghi nhận invocation. `verify(...)` đọc lịch sử đó để xác nhận tương tác.

Hai nhóm trạng thái này có thể được quản lý riêng. `reset(mock)` xóa cả stubbing lẫn invocation history. `clearInvocations(mock)` chỉ xóa invocation history và giữ lại stubbing. Việc chọn nhầm API có thể khiến test mất hành vi giả lập hoặc mang theo lịch sử lời gọi từ giai đoạn trước.

| API | Stubbing | Lịch sử lời gọi | Mục đích |
|---|---|---|---|
| `reset(mock)` | Xóa | Xóa | Đưa mock về trạng thái chưa cấu hình |
| `clearInvocations(mock)` | Giữ | Xóa | Bắt đầu quan sát một giai đoạn tương tác mới |
| Tạo mock mới | Không có từ đầu | Không có từ đầu | Cô lập test bằng một collaborator mới |

## Vì sao thường không cần reset giữa các test?

Với JUnit Jupiter, lifecycle mặc định là tạo một test instance mới cho mỗi test method. Khi dùng `MockitoExtension`, các field được đánh dấu `@Mock` được khởi tạo và quản lý theo test instance đó. Vì vậy, mỗi test thường nhận mock mới, không phải dùng chung mock của test trước.

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @Test
    void returnsCustomerWhenFound() {
        when(repository.findById(10L))
            .thenReturn(Optional.of(new Customer(10L, "Lan")));

        assertThat(service.findName(10L)).isEqualTo("Lan");
    }

    @Test
    void returnsFallbackWhenMissing() {
        when(repository.findById(20L)).thenReturn(Optional.empty());

        assertThat(service.findName(20L)).isEqualTo("Unknown");
    }
}
~~~

Hai test có mock và service riêng. Stub của test đầu không rò sang test thứ hai. Không cần gọi `reset(repository)` trong `@BeforeEach` hoặc `@AfterEach`.

Nếu chủ động dùng lifecycle `@TestInstance(PER_CLASS)`, giữ mock trong biến `static`, chia sẻ fixture giữa nhiều test hoặc tự tạo một mock ở phạm vi rộng hơn test method, khi đó mới cần xem xét trạng thái dùng chung. Tuy nhiên, thường tốt hơn là chuyển mock và đối tượng đang kiểm tra về phạm vi từng test, hoặc tạo fixture mới cho mỗi test.

Một dấu hiệu thiết kế chưa tốt là phải reset mock trước mỗi test để các test không ảnh hưởng nhau. Hãy kiểm tra vì sao mock được chia sẻ, liệu test có thể nhận một instance mới hay không và object thật đang được kiểm tra có đang giữ trạng thái mutable không.

## reset(mock) xóa những gì?

`Mockito.reset(mock)` xóa toàn bộ cấu hình stubbing và lịch sử lời gọi của mock. Sau khi reset, mock vẫn là mock đó, nhưng mọi lời gọi chưa được stub sẽ quay về hành vi mặc định của Mockito (ví dụ trả về `null`, `false`, `0` hoặc giá trị rỗng phù hợp với kiểu trả về).

~~~java
@Test
void resetRemovesStubbingAndInvocationHistory() {
    List<String> names = mock(List.class);

    when(names.get(0)).thenReturn("Lan");
    names.get(0);
    verify(names).get(0);

    reset(names);

    // Stub cũ đã bị xóa; lời gọi này nhận giá trị mặc định (null).
    assertThat(names.get(0)).isNull();

    // Lịch sử trước reset cũng đã bị xóa.
    verify(names).get(0);
}
~~~

Ví dụ trên minh họa API, không phải cách tổ chức test thông thường. Sau reset, lời gọi `get(0)` mới được ghi nhận; vì vậy `verify(names).get(0)` cuối xác nhận invocation mới, không phải invocation trước reset.

Một lỗi dễ gặp là reset mock rồi quên cấu hình lại stub:

~~~java
@BeforeEach
void setUp() {
    when(repository.findAll()).thenReturn(List.of(customer));
}

@Test
void findsCustomer() {
    reset(repository);

    // findAll() giờ không còn stub; kết quả có thể là null.
    assertThat(service.findAll()).contains(customer);
}
~~~

Trong ví dụ này, reset đã xóa cấu hình vừa tạo trong setup. Nếu một test cần thay đổi hành vi của collaborator, hãy cấu hình stub riêng trong test đó thay vì reset một mock được cấu hình dùng chung.

Mockito khuyến nghị hạn chế dùng `reset()` trong test thông thường. Việc reset giữa các bước của cùng một test thường cho thấy test đang làm quá nhiều việc hoặc mock được chia sẻ ngoài phạm vi cần thiết. Tách kịch bản thành test riêng thường dễ hiểu hơn.

## clearInvocations(mock) khác reset(mock) thế nào?

`clearInvocations(mock)` xóa lịch sử lời gọi nhưng giữ lại stubbing. Nó hữu ích trong một số test có nhiều giai đoạn mà cùng một hành vi giả lập vẫn cần được duy trì, nhưng chỉ muốn xác minh những lời gọi phát sinh từ giai đoạn tiếp theo.

~~~java
@Test
void clearsOnlyInvocationHistory() {
    List<String> names = mock(List.class);
    when(names.get(0)).thenReturn("Lan");

    names.get(0);
    verify(names).get(0);

    clearInvocations(names);

    // Stub vẫn còn.
    assertThat(names.get(0)).isEqualTo("Lan");

    // Lịch sử đã được xóa; chỉ invocation mới được tính.
    verify(names).get(0);
}
~~~

Một trường hợp có thể dùng `clearInvocations` là test một giao thức tương tác theo hai giai đoạn: trước hết chuẩn bị hoặc khởi tạo collaborator, sau đó chỉ muốn kiểm tra các lời gọi của thao tác chính. Tuy nhiên, nên cân nhắc tách phần chuẩn bị thành fixture hoặc tạo mock riêng để test không cần xóa lịch sử thủ công.

Không dùng `clearInvocations` để che giấu các tương tác thừa. Nếu một service gọi collaborator ngoài dự kiến, xóa lịch sử trước khi kiểm tra có thể làm mất bằng chứng của lỗi đó.

## Spy cũng có trạng thái cần quản lý

Mock thay thế implementation bằng hành vi giả lập. Spy bọc một object thật: những phương thức không được stub thường gọi implementation thật, và các thay đổi trên object có thể tồn tại sau lời gọi.

~~~java
class NameFormatter {
    private int callCount;

    String format(String name) {
        callCount++;
        return name.trim().toUpperCase();
    }

    int callCount() {
        return callCount;
    }
}
~~~

Một spy có thể được tạo như sau:

~~~java
NameFormatter realFormatter = new NameFormatter();
NameFormatter formatter = spy(realFormatter);

assertThat(formatter.format(" lan ")).isEqualTo("LAN");
assertThat(formatter.callCount()).isEqualTo(1);
~~~

Nếu test gọi phương thức thật, trạng thái `callCount` thay đổi. `reset(formatter)` xóa stubbing và invocation history do Mockito quản lý, nhưng không khôi phục trạng thái bên trong object thật về ban đầu. Nếu `callCount` đã là 1, reset spy không làm nó trở về 0.

Do đó, để cô lập test dùng spy, hãy tạo object thật mới cho mỗi test. Không nên dùng một spy toàn cục rồi reset nó và cho rằng object bên trong đã được làm mới.

### Stub spy mà không gọi nhầm phương thức thật

Với mock, cách viết phổ biến là:

~~~java
when(repository.findById(10L)).thenReturn(Optional.of(customer));
~~~

Với spy, biểu thức bên trong `when(...)` có thể gọi phương thức thật ngay trong lúc cấu hình stub:

~~~java
NameFormatter formatter = spy(new NameFormatter());

// Có thể gọi implementation thật của format() trong lúc stubbing.
when(formatter.format(" lan ")).thenReturn("TEST");
~~~

Nếu phương thức thật có side effect, truy cập tài nguyên hoặc ném exception với dữ liệu đầu vào đó, việc cấu hình stub có thể gây tác động không mong muốn. Dùng dạng `doReturn(...).when(spy)...` để không gọi implementation thật trong bước stubbing:

~~~java
doReturn("TEST").when(formatter).format(" lan ");

assertThat(formatter.format(" lan ")).isEqualTo("TEST");
~~~

Các API cùng họ gồm `doThrow()`, `doAnswer()` và `doNothing()`. Dùng chúng khi cần stub spy mà không muốn thực thi method thật trong quá trình thiết lập.

Spy nên được dùng có chủ đích, thường khi cần giữ phần lớn hành vi thật nhưng thay một điểm cộng tác cụ thể. Nếu phải stub nhiều phương thức của spy hoặc reset nó liên tục, hãy xem xét tách dependency bằng interface hoặc constructor injection để dùng mock/fake rõ ràng hơn.

## Strict stubbing là gì?

Strict stubbing yêu cầu các stub đã khai báo phải phù hợp với những lời gọi thực tế của test. Nó giúp phát hiện sớm hai loại vấn đề:

- **Unnecessary stubbing:** test đã cấu hình một hành vi giả lập nhưng không có lời gọi nào sử dụng stub đó.
- **Stubbing argument mismatch:** test cấu hình một lời gọi với đối số nhất định, nhưng code thực tế gọi cùng phương thức với đối số khác; điều này thường cho thấy stub hoặc code đang kiểm tra bị sai.

Mockito cung cấp các mức strictness:

| Mức | Hành vi |
|---|---|
| `STRICT_STUBS` | Phát hiện stub không được dùng và các trường hợp mismatch đáng ngờ; tự đánh dấu các lời gọi đã dùng stub là verified cho mục đích `verifyNoMoreInteractions` |
| `WARN` | Ghi cảnh báo về stubbing không phù hợp thay vì thất bại test theo strict mode |
| `LENIENT` | Bỏ qua các kiểm tra strict stubbing |

Khi dùng `MockitoExtension` với JUnit Jupiter, strict stubbing là chế độ mặc định thông thường. Có thể khai báo mức strictness rõ ràng bằng `@MockitoSettings`.

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class PricingServiceTest {
    // ...
}
~~~

Strict stubbing giúp test gọn hơn vì các stub được dùng đã được Mockito xử lý như những tương tác đã xác nhận trong cơ chế strict stubs. Nó không thay thế assertion về kết quả nghiệp vụ. Test vẫn cần xác nhận output, trạng thái hoặc exception mà nó thực sự quan tâm.

## UnnecessaryStubbingException: cấu hình nhưng không dùng

Một stub được xem là thừa khi test không thực hiện lời gọi tương ứng. Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @BeforeEach
    void setUp() {
        when(repository.count()).thenReturn(1L);
    }

    @Test
    void returnsFallbackWhenCustomerIsMissing() {
        when(repository.findById(20L)).thenReturn(Optional.empty());

        assertThat(service.findName(20L)).isEqualTo("Unknown");
    }
}
~~~

Test chỉ gọi `findById(20L)`; stub `count()` trong `@BeforeEach` không được dùng. Vì đây là một phương thức khác, ví dụ minh họa rõ một stub thừa mà không tạo thêm tình huống argument mismatch. Với strict stubbing, Mockito có thể ném `UnnecessaryStubbingException` khi kết thúc test session.

Cách sửa tốt nhất là đưa stub đến đúng test cần nó:

~~~java
@Test
void returnsNameWhenCustomerExists() {
    when(repository.findById(10L))
        .thenReturn(Optional.of(new Customer(10L, "Lan")));

    assertThat(service.findName(10L)).isEqualTo("Lan");
}

@Test
void returnsFallbackWhenCustomerIsMissing() {
    when(repository.findById(20L)).thenReturn(Optional.empty());

    assertThat(service.findName(20L)).isEqualTo("Unknown");
}
~~~

Mỗi test chỉ khai báo dữ liệu và hành vi collaborator mà kịch bản đó cần. Cấu hình trở nên gần với assertion hơn, người đọc dễ hiểu điều kiện test và strict stubbing không phải bỏ qua các stub không dùng.

Nếu nhiều test thực sự cần cùng một stub, có thể đặt nó trong fixture chung nhưng cần bảo đảm mọi test sử dụng fixture đó đều gọi stub. Nếu chỉ một vài test sử dụng, cấu hình cục bộ thường rõ ràng hơn.

## PotentialStubbingProblem: stub không khớp đối số

Giả sử test cấu hình:

~~~java
when(repository.findByEmail("lan@example.test"))
    .thenReturn(Optional.of(customer));
~~~

Nhưng service thực tế gọi:

~~~java
repository.findByEmail("lan@exampl.test");
~~~

Có thể đây là lỗi đánh máy trong code hoặc test. Strict stubbing có thể phát hiện tình huống đối số không khớp và báo `PotentialStubbingProblem`, giúp xác định sai lệch sớm hơn việc nhận một giá trị mặc định từ mock rồi thất bại ở assertion phía sau.

Khi gặp lỗi mismatch:

1. Đọc đối số trong stub và đối số trong invocation thực tế.
2. Xác định giá trị nào đúng theo hợp đồng nghiệp vụ.
3. Sửa test fixture hoặc code sản phẩm theo bằng chứng.
4. Chỉ dùng matcher như `anyString()` nếu test không cần kiểm tra giá trị cụ thể; nếu đối số có ý nghĩa nghiệp vụ, nên giữ matcher chính xác.
5. Nếu đang stub nhiều lần cùng một phương thức với các đối số khác nhau, cân nhắc `doReturn(...).when(...)` hoặc BDD `willReturn(...).given(...)` để tránh Mockito diễn giải một lần gọi trong lúc stubbing thành invocation cần kiểm tra.

Không nên đổi toàn bộ stub sang `any()` chỉ để loại bỏ lỗi strictness. Làm như vậy có thể khiến test không còn kiểm tra unit có truyền đúng dữ liệu cho collaborator hay không.

## Khi nào dùng lenient stubbing?

Đôi khi một stub có thể được dùng trong một số test của một fixture chung nhưng không được dùng trong các test còn lại. Mockito cho phép đánh dấu riêng stub đó là lenient:

~~~java
lenient()
    .when(featureFlags.isEnabled("new-checkout"))
    .thenReturn(true);
~~~

Hoặc có thể đặt strictness cho toàn bộ test class:

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class LegacyServiceTest {
    // ...
}
~~~

Lenient làm giảm khả năng phát hiện cấu hình thừa. Vì vậy, nên ưu tiên theo thứ tự:

1. Chuyển stub vào đúng test method.
2. Tách fixture dùng chung thành các fixture nhỏ hơn theo nhóm hành vi.
3. Nếu stub thật sự là tùy chọn và có lý do rõ ràng, đánh dấu riêng stub đó bằng `lenient()`.
4. Chỉ chuyển cả class sang `LENIENT` khi có lý do đặc biệt và đã hiểu những kiểm tra strictness bị bỏ qua.

Không nên thêm `lenient()` cho mọi stub chỉ để test suite hết báo lỗi. Lỗi strict stubbing thường là tín hiệu cho thấy test setup đang rộng hơn nhu cầu thực tế hoặc đối số giữa test và code không khớp.

## Strict stubbing không đồng nghĩa với verify mọi lời gọi

Cần phân biệt ba câu hỏi:

- Stub có được sử dụng không?
- Unit có gọi collaborator với đối số và số lần mong muốn không?
- Kết quả nghiệp vụ có đúng không?

Strict stubbing chủ yếu giúp phát hiện stub thừa và mismatch. `verify()` dùng khi tương tác là một phần hợp đồng cần xác nhận, ví dụ service phải yêu cầu kho giữ đúng số lượng. Assertion kiểm tra kết quả quan sát được như tổng tiền, trạng thái hoặc exception.

~~~java
@Test
void reservesRequestedQuantityAndReturnsOrder() {
    when(inventory.reserve("SKU-1", 2)).thenReturn(true);

    Order result = service.place(new OrderCommand("SKU-1", 2));

    assertThat(result.quantity()).isEqualTo(2);
    verify(inventory).reserve("SKU-1", 2);
}
~~~

Không phải mọi stub đều cần một lệnh `verify()` tương ứng. Khi dùng `STRICT_STUBS`, lời gọi đã dùng stub được tự động xem là verified trong ngữ cảnh `verifyNoMoreInteractions`. Việc thêm `verifyNoMoreInteractions()` vào mọi test thường làm test phụ thuộc quá mức vào chi tiết triển khai và gây khó khăn khi refactor. Chỉ xác minh những tương tác có ý nghĩa đối với hợp đồng của unit.

## Quản lý mock bean trong Spring Test

Trong test thuần Mockito, `MockitoExtension` tạo và quản lý mock theo test session. Trong Spring integration test, mock có thể được đăng ký trong ApplicationContext để thay thế một bean thật, chẳng hạn bằng `@MockitoBean` trong Spring Framework hiện đại.

Vì ApplicationContext có thể được cache và tái sử dụng giữa nhiều test, mock bean trong context có vòng đời khác với field mock thông thường. Spring cung cấp chính sách reset mock bean sau test; mặc định của `@MockitoBean` là reset sau mỗi test method. Điều này giúp loại bỏ stubbing và invocation của test trước trong khi vẫn giữ context được cache. Chính sách reset này độc lập với strict stubbing của `MockitoExtension`: việc Spring reset mock bean không tự động có nghĩa mock bean đã tham gia cùng Mockito test session hoặc được kiểm tra unused stubbing theo cùng lifecycle.

~~~java
@SpringJUnitConfig(AppTestConfig.class)
class CheckoutIntegrationTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void completesCheckoutWhenPaymentSucceeds() {
        when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.approved());

        var result = checkoutService.checkout(command());

        assertThat(result.isSuccessful()).isTrue();
    }
}
~~~

Ví dụ giả định context có bean `CheckoutService` và `PaymentGateway`, cùng các kiểu dữ liệu tương ứng. Khi dùng mock bean trong context, vẫn nên khai báo stub cục bộ trong từng test để strictness và phạm vi fixture dễ theo dõi. Nếu cần tùy chỉnh chế độ reset của bean override, hãy làm theo nhu cầu thực tế của test và phiên bản Spring đang dùng.

Không nhầm reset mock bean với việc tạo lại toàn bộ ApplicationContext. Reset mock chỉ làm mới trạng thái Mockito của bean thay thế; nó không khởi tạo lại các bean khác và không hoàn tác side effect bên ngoài mock như dữ liệu database, file hoặc message đã gửi.

## Checklist khi test báo lỗi stubbing hoặc trạng thái bị rò rỉ

Khi Mockito báo lỗi hoặc kết quả phụ thuộc thứ tự test, hãy xác định nguyên nhân theo từng bước:

1. **Tìm stub không được sử dụng.** Stub có thuộc test method hiện tại không? Có thể chuyển nó khỏi `@BeforeEach` hoặc fixture chung không?
2. **So sánh đối số.** Đối số của invocation thực tế có khớp với stub không? Giá trị nào là đúng theo hợp đồng?
3. **Kiểm tra phạm vi mock.** Mock có bị chia sẻ qua static field, `PER_CLASS`, Spring context hoặc fixture toàn cục không?
4. **Xác định loại reset.** Cần xóa cả stub và invocation, hay chỉ cần xóa lịch sử tương tác?
5. **Kiểm tra spy.** Object thật bên trong spy có giữ trạng thái mutable hoặc side effect từ test trước không?
6. **Tìm lenient đang che lỗi.** Stub có thật sự tùy chọn hay đang bị đánh dấu lenient chỉ để bỏ qua cảnh báo?
7. **Kiểm tra tác động ngoài Mockito.** Reset mock không hoàn tác database, file, message, thread hoặc trạng thái của object thật.

| Triệu chứng | Hướng xử lý |
|---|---|
| `UnnecessaryStubbingException` | Chuyển stub vào test sử dụng nó; thu hẹp fixture chung |
| `PotentialStubbingProblem` | So sánh đối số stub với invocation thực tế và sửa nguồn sai |
| Test sau nhận kết quả từ stub cũ | Kiểm tra mock có bị chia sẻ; ưu tiên tạo mock mới |
| Spy vẫn giữ bộ đếm hoặc trạng thái cũ sau reset | Tạo object thật mới rồi tạo spy mới |
| `verifyNoMoreInteractions` thất bại vì lời gọi không mong muốn | Xem lại hợp đồng tương tác; không xóa lịch sử để che lỗi |
| Test chỉ chạy được khi dùng LENIENT | Xác định stub thừa hoặc fixture đang quá rộng trước khi nới strictness |

## Nguyên tắc áp dụng

Hãy để mỗi test sở hữu mock, stub và dữ liệu riêng. Cấu hình hành vi ngay trong test cần dùng nó, giữ strict stubbing để phát hiện setup thừa, và chỉ xác minh những tương tác thuộc hợp đồng của unit.

Dùng `reset()` khi thực sự cần xóa cả stubbing lẫn invocation history của cùng một mock; dùng `clearInvocations()` khi chỉ cần bắt đầu một giai đoạn quan sát mới. Với spy, tạo object thật mới nếu cần trạng thái sạch vì reset Mockito không hoàn tác trạng thái bên trong object. Khi strict stubbing báo lỗi, hãy sửa fixture hoặc đối số trước khi cân nhắc lenient.

Những quy tắc này giữ cho mock và spy phản ánh đúng phạm vi của một test, giúp lỗi cấu hình được phát hiện sớm và làm cho kết quả kiểm thử ổn định qua các lần chạy.
