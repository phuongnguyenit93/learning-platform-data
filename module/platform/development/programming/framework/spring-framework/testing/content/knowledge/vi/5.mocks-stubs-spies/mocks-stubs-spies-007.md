# verify số lần gọi và các tương tác quan trọng

Trong unit test dùng Mockito, ta thường thay các collaborator bằng mock để điều khiển phản hồi và quan sát cách thành phần đang kiểm thử giao tiếp với chúng. `when(...).thenReturn(...)` thiết lập hành vi của mock; `verify(...)` xác nhận một tương tác đã xảy ra với đối số và số lần gọi mong đợi. Hai thao tác phục vụ hai mục đích khác nhau: stub chuẩn bị điều kiện cho kịch bản, còn verify kiểm tra hợp đồng tương tác sau khi hành động được thực hiện.

Không phải mọi lời gọi nội bộ đều cần verify. Hãy xác nhận những tương tác có ý nghĩa với hành vi bên ngoài của service: lưu dữ liệu, gửi yêu cầu đến gateway, phát event, gửi email hoặc từ chối gọi một collaborator khi điều kiện không hợp lệ. Nếu test xác nhận quá nhiều chi tiết triển khai như thứ tự gọi helper, số lần đọc một field hoặc mọi lời gọi đến mock, nó sẽ dễ hỏng khi code được refactor mà hành vi vẫn đúng.

## 1. Phân biệt stub và verify

Một mock có thể vừa được cấu hình để trả kết quả, vừa được kiểm tra sau khi chạy. Ví dụ, service cần tìm tài khoản rồi lưu một giao dịch:

```java
@ExtendWith(MockitoExtension.class)
class TransferServiceTest {
    @Mock
    private AccountRepository accounts;

    @Mock
    private TransferRepository transfers;

    @InjectMocks
    private TransferService service;

    @Test
    void storesTransferForExistingAccounts() {
        Account source = new Account(1L, new BigDecimal("100.00"));
        Account target = new Account(2L, new BigDecimal("20.00"));
        when(accounts.findById(1L)).thenReturn(Optional.of(source));
        when(accounts.findById(2L)).thenReturn(Optional.of(target));

        service.transfer(1L, 2L, new BigDecimal("30.00"));

        verify(transfers).save(any(Transfer.class));
    }
}
```

Trong ví dụ:

- `when(...).thenReturn(...)` là stub: nó cho biết mock repository sẽ trả về dữ liệu nào khi service gọi.
- `verify(transfers).save(...)` là verification: nó xác nhận service đã yêu cầu lưu một giao dịch.
- `@InjectMocks` yêu cầu Mockito tạo service và tiêm các mock phù hợp vào constructor hoặc field theo cơ chế của Mockito.

Verification mặc định yêu cầu phương thức được gọi đúng một lần. Vì vậy, `verify(transfers).save(...)` tương đương `verify(transfers, times(1)).save(...)`.

Điểm cần hiểu là verify mock chỉ chứng minh tương tác đã được gửi đến mock. Nó không chứng minh database đã ghi dữ liệu, transaction đã commit hay hệ thống bên ngoài đã xử lý yêu cầu. Những hành vi đó cần test ở mức tích hợp với thành phần thật hoặc môi trường tương thích.

## 2. Kiểm tra số lần gọi

Mockito cung cấp các chế độ xác minh số lần gọi qua `VerificationMode`.

| Cú pháp | Ý nghĩa |
|---|---|
| `verify(mock).method()` | Được gọi đúng một lần |
| `verify(mock, times(3)).method()` | Được gọi đúng ba lần |
| `verify(mock, never()).method()` | Không được gọi lần nào |
| `verify(mock, times(0)).method()` | Tương đương `never()` |
| `verify(mock, atLeast(2)).method()` | Được gọi ít nhất hai lần |
| `verify(mock, atMost(4)).method()` | Được gọi nhiều nhất bốn lần |
| `verify(mock, atLeastOnce()).method()` | Được gọi ít nhất một lần |

Ví dụ một service gửi thông báo cho từng người nhận:

```java
@Test
void sendsOneNotificationForEachRecipient() {
    notificationService.notifyAll(List.of("a@example.test", "b@example.test"));

    verify(sender, times(2)).send(any(Notification.class));
}
```

Nếu hợp đồng yêu cầu chỉ gửi một email xác nhận, hãy kiểm tra chính xác một lần:

```java
verify(emailSender, times(1)).send(any(Email.class));
```

Do một lần là mặc định, có thể viết gọn `verify(emailSender).send(any(Email.class))`. Dùng `times(1)` khi muốn nhấn mạnh số lần gọi hoặc khi đặt cạnh các trường hợp `times(0)`, `times(2)`.

### 2.1. Kiểm tra không gọi bằng `never()`

Nhánh thất bại thường cần chứng minh một tác dụng phụ không xảy ra. Ví dụ, nếu số dư không đủ thì service không được gửi yêu cầu thanh toán:

```java
@Test
void doesNotRequestPaymentWhenBalanceIsInsufficient() {
    when(accounts.findById(1L)).thenReturn(Optional.of(accountWithBalance("10.00")));

    assertThatThrownBy(() -> service.pay(1L, new BigDecimal("30.00")))
            .isInstanceOf(InsufficientFundsException.class);

    verify(paymentGateway, never()).charge(any(PaymentRequest.class));
}
```

Assertion ngoại lệ kiểm tra kết quả của nhánh thất bại; `never()` kiểm tra ranh giới tác dụng phụ bị cấm. Đây là một tương tác quan trọng vì nếu gateway vẫn được gọi, hệ thống có thể phát sinh khoản thanh toán sai dù service đã ném ngoại lệ.

`never()` nên được áp dụng cho phương thức hoặc collaborator cụ thể mà hợp đồng yêu cầu không gọi. Đừng mặc định kiểm tra không có bất kỳ tương tác nào trên mọi mock nếu service vẫn được phép đọc dữ liệu, ghi log hoặc phát metric.

### 2.2. `atLeast` và `atMost` có thực sự cần thiết?

Các mode này hữu ích khi số lần gọi là một khoảng hợp lệ. Chẳng hạn một thuật toán có thể thử đọc cache một hoặc hai lần tùy tình huống, nhưng không được vượt quá một giới hạn. Tuy nhiên, nếu nghiệp vụ yêu cầu đúng một lần gửi message, `atLeastOnce()` là quá yếu: code gửi lặp nhiều lần vẫn làm test qua.

Hãy chọn mode sát với hợp đồng:

- Dùng `times(n)` khi số lần gọi chính xác là một yêu cầu.
- Dùng `never()` khi hành động bị cấm trong kịch bản.
- Dùng `atLeast` hoặc `atMost` khi hợp đồng thật sự cho phép một khoảng số lần.
- Tránh kiểm tra số lần gọi chỉ vì hiện tại implementation đang lặp qua một cấu trúc dữ liệu theo cách cụ thể.

## 3. Kiểm tra đối số được truyền

Xác nhận một phương thức đã được gọi chưa đủ nếu dữ liệu truyền vào có ý nghĩa. Ví dụ, service có thể gọi `paymentGateway.charge(...)` đúng một lần nhưng gửi sai amount, currency hoặc order id.

Mockito hỗ trợ truyền giá trị trực tiếp, argument matcher và `ArgumentCaptor`.

### 3.1. So sánh đối số trực tiếp

Nếu kiểu dữ liệu có `equals` phù hợp và giá trị mong đợi rõ ràng, có thể truyền trực tiếp:

```java
verify(repository).findById(42L);
verify(sender).send(new Email("a@example.test", "Order confirmed"));
```

Mockito so sánh đối số theo quy tắc tương đương của đối tượng, thông thường là `equals`. Với DTO hoặc value object, hãy bảo đảm `equals` phản ánh đúng dữ liệu cần so sánh. Nếu class không định nghĩa equality theo giá trị, dùng captor hoặc matcher để kiểm tra các field quan trọng.

### 3.2. Dùng argument matcher

Mockito có các matcher phổ biến như `any()`, `anyString()`, `eq(...)`, `isNull()`, `notNull()`, `argThat(...)` và các matcher cho kiểu nguyên thủy.

```java
verify(repository).findById(eq(42L));
verify(sender).send(any(Email.class));
verify(auditLog).record(argThat(event ->
        event.type() == AuditType.PAYMENT_COMPLETED));
```

Matcher hữu ích khi chỉ một phần đối số quan trọng. Nhưng nếu dùng matcher cho một đối số trong lời gọi có nhiều tham số, các đối số còn lại cũng phải được biểu diễn bằng matcher:

```java
verify(client).charge(eq("order-42"), any(BigDecimal.class), eq("VND"));
```

Không trộn matcher với giá trị literal trong cùng lời gọi verification:

```java
// Sai: một đối số dùng matcher, các đối số còn lại là literal.
verify(client).charge(eq("order-42"), new BigDecimal("30.00"), "VND");

// Đúng: mọi đối số đều dùng matcher.
verify(client).charge(
        eq("order-42"), eq(new BigDecimal("30.00")), eq("VND"));
```

Với kiểu primitive, dùng matcher tương ứng như `anyInt()` hoặc `eq(3)`. `any()` không thể thay trực tiếp một primitive trong mọi tình huống vì generic matcher trả về giá trị tham chiếu; dùng đúng matcher primitive để tránh lỗi unboxing.

### 3.3. Dùng `ArgumentCaptor`

Khi cần kiểm tra nhiều field của một đối tượng được truyền vào mock, `ArgumentCaptor` giúp thu thập đối số:

```java
@Captor
private ArgumentCaptor<PaymentRequest> requestCaptor;

@Test
void sendsPaymentRequestWithExpectedDetails() {
    service.pay(new Order("order-42", new BigDecimal("30.00")));

    verify(paymentGateway).charge(requestCaptor.capture());

    PaymentRequest request = requestCaptor.getValue();
    assertThat(request.orderId()).isEqualTo("order-42");
    assertThat(request.amount()).isEqualByComparingTo("30.00");
    assertThat(request.currency()).isEqualTo("VND");
}
```

`@Captor` được khởi tạo khi test chạy với `MockitoExtension`. Nếu không dùng extension, có thể tạo captor bằng `ArgumentCaptor.forClass(PaymentRequest.class)`.

`getValue()` trả về đối số đã capture gần nhất. Nếu phương thức được gọi nhiều lần và cần kiểm tra tất cả, dùng `getAllValues()`:

```java
verify(sender, times(3)).send(emailCaptor.capture());

assertThat(emailCaptor.getAllValues())
        .extracting(Email::recipient)
        .containsExactly("a@example.test", "b@example.test", "c@example.test");
```

Việc kiểm tra thứ tự trong danh sách trên có ý nghĩa nếu thứ tự gửi là hợp đồng. Nếu các email có thể được gửi theo bất kỳ thứ tự nào, hãy dùng assertion không phụ thuộc thứ tự, chẳng hạn `containsExactlyInAnyOrder`.

### 3.4. Captor hay `argThat`?

Hai cách đều có thể kiểm tra nội dung đối số, nhưng phù hợp với mục tiêu khác nhau:

- Dùng `argThat` khi điều kiện ngắn, tập trung và chỉ cần xác nhận lời gọi phù hợp.
- Dùng `ArgumentCaptor` khi cần đọc nhiều thuộc tính, kiểm tra nhiều assertion hoặc tái sử dụng giá trị đã capture.
- Dùng đối số literal khi equality đã diễn đạt đầy đủ hợp đồng.

Không nên capture chỉ để kiểm tra một giá trị đơn giản. Ngược lại, một lambda `argThat` dài chứa nhiều điều kiện sẽ khó đọc và khó chẩn đoán khi thất bại; captor thường rõ ràng hơn trong trường hợp đó.

## 4. Kiểm tra tương tác theo thứ tự với `InOrder`

Một số luồng có thứ tự tương tác là một phần của hợp đồng. Ví dụ, service phải lưu giao dịch trước khi phát event xác nhận. Mockito cung cấp `InOrder`:

```java
@Test
void savesTransferBeforePublishingCompletionEvent() {
    service.transfer(command);

    InOrder order = inOrder(transfers, eventPublisher);
    order.verify(transfers).save(any(Transfer.class));
    order.verify(eventPublisher).publishEvent(any(TransferCompleted.class));
}
```

`InOrder` xác nhận các tương tác được verify theo thứ tự tương đối. Những tương tác khác không được đưa vào chuỗi verify vẫn có thể xảy ra giữa chúng. Nếu muốn xác nhận toàn bộ các tương tác liên quan theo trình tự, hãy verify từng bước cần thiết.

Chỉ dùng `InOrder` khi thứ tự có ý nghĩa. Ví dụ, nếu service gọi hai repository độc lập và thứ tự không ảnh hưởng kết quả, kiểm tra thứ tự sẽ khiến test phụ thuộc vào implementation. Một lần refactor đổi thứ tự truy vấn có thể làm test thất bại dù hành vi vẫn chính xác.

Với transaction và event, cần đặc biệt thận trọng. Việc service gọi `publishEvent` sau `save` không chứng minh transaction đã commit trước khi listener chạy. Nếu yêu cầu là event chỉ được xử lý sau commit, hãy kiểm thử `@TransactionalEventListener` và transaction boundary trong Spring integration test.

## 5. Kiểm tra các tương tác bị cấm hoặc ngoài dự kiến

Mockito cung cấp hai API thường được dùng:

```java
verifyNoInteractions(mock);
verifyNoMoreInteractions(mock1, mock2);
```

`verifyNoInteractions(mock)` xác nhận mock chưa nhận bất kỳ lời gọi nào. `verifyNoMoreInteractions(...)` xác nhận không còn tương tác chưa được verify trên các mock được truyền vào.

Ví dụ, dữ liệu đầu vào không hợp lệ phải bị từ chối trước khi gọi gateway:

```java
@Test
void rejectsInvalidAmountWithoutCallingGateway() {
    assertThatThrownBy(() -> service.pay(BigDecimal.ZERO))
            .isInstanceOf(InvalidAmountException.class);

    verifyNoInteractions(paymentGateway);
}
```

Đây là assertion phù hợp nếu hợp đồng yêu cầu gateway hoàn toàn không được chạm tới trong trường hợp này.

### 5.1. Dùng `verifyNoMoreInteractions` có chọn lọc

Một ví dụ khác:

```java
service.findCustomer(42L);

verify(customers).findById(42L);
verifyNoMoreInteractions(customers);
```

Test này nói rằng service chỉ được gọi đúng thao tác đã verify trên mock `customers`. Nhưng nếu sau này service bổ sung một lần đọc cache, metric hoặc thao tác hợp lệ khác trên cùng mock, test sẽ thất bại dù hợp đồng bên ngoài không thay đổi.

Vì vậy:

- Dùng `verifyNoInteractions` khi không có bất kỳ tương tác nào là một yêu cầu rõ ràng.
- Dùng `verifyNoMoreInteractions` khi việc cấm tương tác bổ sung là quan trọng đối với kịch bản.
- Không tự động thêm `verifyNoMoreInteractions` sau mọi verify.
- Tránh dùng nó như cách ép test phải phản ánh toàn bộ cấu trúc nội bộ của service.

Nếu chỉ một hành động bị cấm, `verify(mock, never()).specificMethod(...)` thường diễn đạt ý định chính xác hơn việc cấm mọi tương tác.

## 6. Kiểm tra retry và các lần gọi lặp

Khi service có retry, số lần gọi có thể là một phần của hợp đồng vận hành. Ví dụ, client được phép thử tối đa ba lần trước khi báo lỗi:

```java
@Test
void retriesRemoteCallAtMostThreeTimes() {
    when(remoteClient.fetch("item-42"))
            .thenThrow(new TemporaryRemoteException())
            .thenThrow(new TemporaryRemoteException())
            .thenReturn(new RemoteItem("item-42"));

    RemoteItem item = service.fetchWithRetry("item-42");

    assertThat(item.id()).isEqualTo("item-42");
    verify(remoteClient, times(3)).fetch("item-42");
}
```

Kịch bản trên kiểm tra service đã thử hai lần thất bại rồi thành công ở lần thứ ba. Một test khác nên kiểm tra trường hợp cả ba lần đều thất bại và service trả lỗi phù hợp.

Không nên kiểm tra số lần retry nếu số lần đó không được quy định và có thể thay đổi do circuit breaker, timeout hoặc chính sách backoff. Khi đó, hãy kiểm tra kết quả cuối cùng, trạng thái và những tác dụng phụ quan trọng. Nếu số lần thử là yêu cầu, hãy kiểm tra chính xác số lần thay vì chỉ dùng `atLeastOnce()`.

Với retry bất đồng bộ, lời gọi có thể chưa xảy ra ngay tại thời điểm assertion. Hãy đợi theo điều kiện hoàn tất có timeout hoặc đồng bộ qua future/latch. Không dùng sleep cố định để đoán khi nào lời gọi tiếp theo sẽ được thực hiện.

## 7. Verify tương tác bất đồng bộ

Một service có thể gửi tác vụ vào executor, phát event có listener `@Async` hoặc gọi một client chạy nền. Khi đó, test không thể mặc định rằng tất cả tương tác đã hoàn thành ngay sau khi phương thức ban đầu trả về.

Mockito có `timeout` và `after` để chờ verification:

```java
verify(notificationSender, timeout(1_000))
        .send(any(Notification.class));
```

`timeout(1_000)` chờ tối đa một giây để tương tác mong đợi xảy ra; khi điều kiện thỏa mãn, verification có thể kết thúc sớm. Đây là cách kiểm tra một tương tác bất đồng bộ đơn giản, nhưng không nên dùng timeout lớn tùy tiện để che giấu việc test thiếu đồng bộ.

`after(...)` chờ hết khoảng thời gian được chỉ định rồi đánh giá số lần gọi:

```java
verify(notificationSender, after(500).never())
        .send(any(Notification.class));
```

Cách này có thể dùng khi cần xác nhận một tương tác không xảy ra trong một khoảng quan sát, nhưng test sẽ phải chờ hết khoảng thời gian đó. Nó cũng không chứng minh hành động sẽ không bao giờ xảy ra sau khoảng chờ.

Đối với luồng bất đồng bộ phức tạp, ưu tiên đồng bộ theo cơ chế của ứng dụng:

- Đợi `CompletableFuture` hoàn tất bằng `get` hoặc `join` với timeout phù hợp.
- Dùng `CountDownLatch` trong test observer để đợi listener xử lý xong.
- Dùng executor có thể điều khiển hoặc scheduler test khi cần xác nhận thứ tự và thời điểm lên lịch.
- Sau khi đã đồng bộ, dùng `verify` thông thường để kiểm tra tương tác.

Ví dụ:

```java
@Test
void sendsNotificationAfterBackgroundTaskCompletes() throws Exception {
    CompletableFuture<Void> task = service.notifyAsync(command);

    task.get(2, TimeUnit.SECONDS);

    verify(notificationSender).send(any(Notification.class));
}
```

Ví dụ này giả định future chỉ hoàn tất sau khi service đã hoàn thành lời gọi gửi thông báo. Nếu future chỉ báo tác vụ đã được xếp hàng, cần đợi tín hiệu xử lý thực tế từ worker hoặc listener.

## 8. Spy và việc xác minh tương tác

Mock mô phỏng toàn bộ đối tượng. Spy bọc một đối tượng thật và mặc định gọi phương thức thật khi phương thức đó được gọi, trừ khi test stub một phương thức cụ thể. Vì vậy, spy có thể được verify giống mock:

```java
List<String> names = new ArrayList<>();
List<String> spyNames = spy(names);

spyNames.add("Lan");

verify(spyNames).add("Lan");
assertThat(names).containsExactly("Lan");
```

Spy hữu ích khi cần quan sát một tương tác trên đối tượng thật hoặc thay một phần hành vi trong tình huống đặc biệt. Tuy nhiên, nó cũng khiến test phụ thuộc vào implementation nhiều hơn. Nếu một phương thức gọi phương thức khác trên cùng object, verify có thể nhìn thấy tương tác nội bộ đó; hãy cân nhắc liệu tương tác ấy có thực sự là hợp đồng cần kiểm tra.

### 8.1. Cẩn thận khi stub spy

Với mock, `when(mock.method()).thenReturn(value)` thường không thực thi logic thật. Với spy, biểu thức trong `when(...)` có thể gọi phương thức thật ngay trong lúc thiết lập stub. Nếu phương thức thật truy cập file, database, mạng hoặc ném lỗi do trạng thái chưa sẵn sàng, test có thể gặp tác dụng phụ trước khi chạy hành động chính.

Với spy, dùng cú pháp `doReturn(...).when(spy).method(...)` khi muốn tránh gọi phương thức thật lúc stub:

```java
List<String> spyNames = spy(new ArrayList<>());

doReturn(10).when(spyNames).size();

assertThat(spyNames.size()).isEqualTo(10);
verify(spyNames).size();
```

Các biến thể `doThrow`, `doAnswer` và `doNothing` cũng có thể dùng với spy. Chỉ stub những phương thức cần thiết và giữ phần còn lại hoạt động thật để test không mất mục tiêu.

### 8.2. Không dùng spy để kiểm tra private method

Mockito verify các lời gọi qua phương thức có thể intercept trên mock/spy; nó không phải công cụ để kiểm tra private method. Nếu một private method chứa logic nghiệp vụ phức tạp đến mức cần kiểm tra riêng, hãy xem xét đưa trách nhiệm đó vào một collaborator có API phù hợp. Nếu logic chỉ là chi tiết triển khai, kiểm tra kết quả của phương thức công khai thay vì mở rộng phạm vi truy cập chỉ để test.

## 9. Strict stubbing và các stub không được sử dụng

Khi dùng `MockitoExtension`, strict stubbing thường giúp phát hiện những stub không được dùng hoặc cấu hình không khớp với lời gọi thực tế. Điều này có ích vì một test có thể đang chuẩn bị sai dữ liệu mà vẫn chạy qua một nhánh không dự kiến.

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock
    CustomerRepository customers;

    @InjectMocks
    CustomerService service;

    @Test
    void findsCustomerById() {
        when(customers.findById(42L))
                .thenReturn(Optional.of(new Customer(42L, "Lan")));

        Customer customer = service.findById(42L);

        assertThat(customer.name()).isEqualTo("Lan");
        verify(customers).findById(42L);
    }
}
```

Nếu stub được khai báo nhưng service không gọi đến, hãy kiểm tra lại test: có thể setup thừa, tham số không đúng hoặc code đi vào nhánh khác. Không vội tắt strictness cho cả class để bỏ qua cảnh báo.

Nếu một stub chỉ được dùng trong một số kịch bản, hãy đặt stub ngay trong test cần nó. Trong trường hợp thật sự cần stub tùy chọn, Mockito có `lenient()` nhưng chỉ nên dùng có chủ đích và giới hạn phạm vi.

## 10. Những tương tác nào đáng verify?

Một nguyên tắc thực tế là verify những tương tác vượt qua ranh giới có ý nghĩa hoặc quyết định hành vi nghiệp vụ. Ví dụ:

| Tình huống | Tương tác đáng verify | Điều không nên khóa cứng |
|---|---|---|
| Tạo đơn hàng | Repository lưu đơn hàng với dữ liệu đúng; phát event theo hợp đồng | Số lần gọi helper nội bộ hoặc mapper |
| Thanh toán thất bại | Gateway không bị gọi nếu lỗi đầu vào được phát hiện trước | Mọi lần đọc repository nếu không thuộc hợp đồng |
| Gửi email | Người nhận, nội dung hoặc template cần dùng | Thứ tự các bước format nội bộ |
| Retry API | Số lần thử nếu giới hạn retry là yêu cầu | Các lời gọi log/metric không ảnh hưởng hành vi |
| Phát domain event | Event type và payload chính xác | Cách service tạo object event bên trong |
| Cache | Ghi hoặc invalidate cache nếu đó là hành vi cần đảm bảo | Mọi thao tác đọc cache nếu implementation có thể thay đổi |

Hãy tự hỏi: nếu bỏ tương tác này, người dùng hoặc thành phần khác có nhận thấy hành vi sai không? Nếu có, đó có thể là assertion quan trọng. Nếu chỉ có thể nhận ra bằng cách xem cấu trúc nội bộ của class, có lẽ assertion đang quá chặt.

## 11. Các lỗi thường gặp khi verify

### Verify trước khi hành động hoàn tất

Nếu tương tác xảy ra bất đồng bộ, verify ngay sau khi gọi service có thể chạy trước worker. Hãy đồng bộ bằng future, latch hoặc cơ chế chờ có timeout rồi mới verify.

### Chỉ verify số lần, bỏ qua payload

`verify(gateway).charge(any())` không chứng minh amount, currency hoặc order id đúng. Capture đối số hoặc dùng matcher diễn đạt thuộc tính quan trọng.

### Dùng `atLeastOnce()` cho yêu cầu đúng một lần

Test vẫn qua khi code gửi lặp nhiều lần. Dùng `times(1)` hoặc verify mặc định khi số lần chính xác là hợp đồng.

### Lạm dụng `verifyNoMoreInteractions`

Nó khóa test vào danh sách mọi tương tác đã biết. Một tương tác hợp lệ mới có thể làm test thất bại. Chỉ dùng khi không có tương tác bổ sung thực sự là một yêu cầu.

### Kiểm tra thứ tự không cần thiết

`InOrder` có thể làm test phụ thuộc vào cách triển khai. Chỉ xác nhận thứ tự nếu việc đổi thứ tự làm thay đổi kết quả hoặc vi phạm hợp đồng.

### Dùng captor quá sớm

Với một đối số đơn giản có equality đúng, truyền trực tiếp thường dễ đọc hơn. Dùng captor khi cần kiểm tra nhiều field hoặc nhiều lần gọi.

### Nhầm verify mock với xác nhận hệ thống ngoài

Verify repository mock chỉ chứng minh service gọi repository. Nó không chứng minh database đã commit. Verify event publisher chỉ chứng minh event được phát đến publisher; không chứng minh listener hoặc broker đã xử lý xong.

### Stub spy bằng `when` gây chạy code thật

Trên spy, biểu thức stub có thể thực thi phương thức thật. Dùng `doReturn`, `doThrow` hoặc API `do...when` phù hợp để tránh tác dụng phụ ngoài ý muốn.

## 12. Quy trình viết verification rõ ràng

Khi viết một unit test có mock, hãy đi theo trình tự:

1. Xác định collaborator nào là ranh giới cần quan sát trong kịch bản.
2. Stub chỉ những phản hồi cần thiết để đưa service vào đúng nhánh.
3. Gọi một hành động công khai của thành phần đang kiểm thử.
4. Kiểm tra kết quả trả về hoặc ngoại lệ.
5. Verify tương tác bắt buộc: phương thức, số lần và đối số quan trọng.
6. Verify tương tác bị cấm bằng `never()` hoặc `verifyNoInteractions()` khi hợp đồng yêu cầu.
7. Chỉ dùng `InOrder`, `verifyNoMoreInteractions` hoặc `timeout` khi mục tiêu kiểm thử thực sự cần chúng.

Một test tốt thường có ít verification nhưng mỗi assertion đều nói rõ điều gì sẽ sai nếu tương tác bị bỏ hoặc gửi sai dữ liệu. Tên test nên thể hiện kịch bản, chẳng hạn `doesNotChargeWhenAccountIsBlocked` hoặc `publishesOrderCreatedAfterSavingOrder`.

## 13. Ví dụ tổng hợp: tạo đơn hàng và phát event

Service tạo đơn hàng phải lưu bản ghi và phát event chứa ID của đơn hàng. Nếu dữ liệu đầu vào không hợp lệ, service không được lưu và không được phát event.

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock
    private OrderRepository orders;

    @Mock
    private ApplicationEventPublisher events;

    @InjectMocks
    private OrderService service;

    @Test
    void savesOrderAndPublishesEventWithSavedId() {
        Order saved = new Order("order-42", "customer-7");
        when(orders.save(any(Order.class))).thenReturn(saved);

        Order result = service.create(new CreateOrderCommand("customer-7"));

        assertThat(result.id()).isEqualTo("order-42");

        ArgumentCaptor<Order> orderCaptor =
                ArgumentCaptor.forClass(Order.class);
        ArgumentCaptor<OrderCreated> eventCaptor =
                ArgumentCaptor.forClass(OrderCreated.class);

        InOrder order = inOrder(orders, events);
        order.verify(orders).save(orderCaptor.capture());
        order.verify(events).publishEvent(eventCaptor.capture());

        assertThat(orderCaptor.getValue().customerId()).isEqualTo("customer-7");
        assertThat(eventCaptor.getValue().orderId()).isEqualTo("order-42");
        verifyNoMoreInteractions(orders, events);
    }

    @Test
    void doesNotSaveOrPublishEventForInvalidCommand() {
        assertThatThrownBy(() -> service.create(new CreateOrderCommand("")))
                .isInstanceOf(InvalidOrderException.class);

        verifyNoInteractions(orders, events);
    }
}
```

Trong test thành công, `InOrder` chỉ được dùng vì yêu cầu ví dụ đặt việc lưu trước khi phát event. Nếu thứ tự không phải hợp đồng, có thể verify riêng từng mock và bỏ `InOrder`. `verifyNoMoreInteractions` trong ví dụ diễn đạt rằng hai collaborator này không được nhận thêm tương tác nào trong kịch bản; ở dự án thật, chỉ giữ assertion này nếu giới hạn đó có ý nghĩa và ổn định.

Test thất bại xác nhận cả exception và việc không có tác dụng phụ. Nếu service vẫn được phép đọc dữ liệu trước khi phát hiện lỗi, hãy thay `verifyNoInteractions` bằng các assertion hẹp hơn như `verify(orders, never()).save(...)` và `verify(events, never()).publishEvent(...)`.

## 14. Nguyên tắc cần nhớ

- Stub bằng `when(...).thenReturn(...)` để thiết lập phản hồi; verify để xác nhận tương tác sau hành động.
- `verify(mock).method()` mặc định kiểm tra đúng một lần; dùng `times`, `never`, `atLeast` hoặc `atMost` theo hợp đồng.
- Kiểm tra payload bằng đối số trực tiếp, matcher hoặc `ArgumentCaptor`; đừng chỉ xác nhận phương thức được gọi.
- Dùng `InOrder` khi thứ tự tương tác thực sự quan trọng.
- `verifyNoInteractions` và `verifyNoMoreInteractions` có phạm vi khác nhau; tránh dùng chúng như assertion mặc định cho mọi mock.
- Với xử lý bất đồng bộ, đồng bộ theo future/latch hoặc timeout có chủ đích trước khi verify.
- Spy gọi phương thức thật theo mặc định; dùng `doReturn` hoặc API `do...when` khi cần stub mà không thực thi code thật.
- Tương tác với mock không chứng minh database, listener hoặc hệ thống ngoài đã hoàn thành công việc.

Verification hữu ích nhất khi nó tập trung vào hợp đồng tương tác: thành phần nào phải được gọi, với dữ liệu gì, bao nhiêu lần và trong điều kiện nào không được gọi. Giữ assertion ở ranh giới có ý nghĩa giúp test phát hiện lỗi thực sự mà vẫn cho phép refactor cấu trúc bên trong một cách an toàn.
