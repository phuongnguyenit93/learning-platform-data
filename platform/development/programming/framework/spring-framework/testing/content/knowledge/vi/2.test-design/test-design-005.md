# Kiểm tra kết quả, trạng thái và tác dụng phụ

Một bài kiểm thử có giá trị khi nó chứng minh được hành vi mà người dùng hoặc thành phần khác có thể quan sát. Với một thao tác trong ứng dụng Spring, hành vi đó thường có ba phần: **kết quả trả về**, **trạng thái sau thao tác** và **tác dụng phụ được tạo ra**. Thiết kế bài kiểm thử tốt bắt đầu bằng việc xác định phần nào thuộc hợp đồng của thao tác, sau đó chọn đúng điểm quan sát và mức kiểm thử để xác nhận.

Ví dụ, khi chuyển tiền giữa hai tài khoản, chỉ kiểm tra rằng phương thức trả về một `TransferReceipt` là chưa đủ. Ta còn cần biết số dư hai tài khoản đã thay đổi đúng hay chưa, và sự kiện `TransferCompleted` có được phát ra với đúng số tiền hay không. Ngược lại, khi dữ liệu đầu vào không hợp lệ, hợp đồng có thể yêu cầu ném ngoại lệ, giữ nguyên số dư và không phát thông báo nào. Các khẳng định này mô tả hành vi bên ngoài, không phụ thuộc vào cách lớp bên trong được chia thành bao nhiêu phương thức.

## 1. Ba khía cạnh cần quan sát

### 1.1. Kết quả (result)

Kết quả là giá trị hoặc tín hiệu mà lời gọi trực tiếp trả lại cho bên gọi. Tùy lớp đang kiểm thử, kết quả có thể là:

- Giá trị trả về của service, chẳng hạn `TransferReceipt`, `Optional`, danh sách hoặc trạng thái xử lý.
- Ngoại lệ được ném ra khi thao tác thất bại, gồm đúng loại ngoại lệ và thông tin cần thiết để phân biệt nguyên nhân.
- Phản hồi HTTP của controller: status, header, nội dung JSON, cookie hoặc redirect.
- Kết quả bất đồng bộ như `CompletableFuture`, `Mono` hoặc `Flux`, bao gồm giá trị phát ra, lỗi và việc hoàn tất luồng.

Đừng chỉ kiểm tra kết quả có khác `null` hoặc không ném ngoại lệ. Hãy kiểm tra những thuộc tính thể hiện hợp đồng: mã định danh, trạng thái, số tiền, thông báo lỗi ổn định, HTTP status và các trường phản hồi quan trọng.

```java
@Test
void returnsReceiptForSuccessfulTransfer() {
    TransferReceipt receipt = transferService.transfer(1L, 2L, new BigDecimal("30.00"));

    assertThat(receipt).isNotNull();
    assertThat(receipt.transferId()).isNotBlank();
    assertThat(receipt.amount()).isEqualByComparingTo("30.00");
    assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED);
}
```

Ví dụ trên minh họa việc kiểm tra kết quả nghiệp vụ. Nếu service còn thay đổi dữ liệu hoặc gọi hệ thống khác, những khẳng định đó cần được bổ sung tại điểm quan sát phù hợp; một kết quả đúng không tự chứng minh mọi phần còn lại đều đúng.

### 1.2. Trạng thái (state)

Trạng thái là dữ liệu tồn tại sau khi thao tác hoàn tất. Nó có thể nằm trong:

- Đối tượng domain đang được xử lý trong bộ nhớ.
- Cơ sở dữ liệu, gồm bản ghi, quan hệ, giá trị mặc định và ràng buộc.
- Cache, session hoặc vùng lưu trữ khác do ứng dụng quản lý.
- Trạng thái của một workflow, chẳng hạn đơn hàng chuyển từ `PENDING` sang `PAID`.

Khi kiểm tra trạng thái, hãy đọc lại dữ liệu qua giao diện mà thành phần sử dụng thực sự sẽ dùng. Trong unit test, có thể kiểm tra đối tượng sau khi gọi service hoặc dùng một fake repository lưu dữ liệu trong bộ nhớ. Trong kiểm thử persistence, hãy đọc lại bản ghi từ repository sau khi đồng bộ với cơ sở dữ liệu.

Một lời gọi `verify(repository).save(entity)` chỉ chứng minh code đã yêu cầu repository lưu đối tượng. Nó không chứng minh SQL đã chạy thành công, mapping đúng, dữ liệu được ghi xuống database hoặc ràng buộc database được đáp ứng. Khi mục tiêu là xác nhận dữ liệu được lưu, hãy kiểm tra trạng thái đã đọc lại từ persistence layer.

### 1.3. Tác dụng phụ (side effect)

Tác dụng phụ là hành động bên ngoài giá trị trả về và trạng thái chính mà thao tác tạo ra. Ví dụ:

- Gửi email hoặc SMS.
- Gọi cổng thanh toán, dịch vụ vận chuyển hoặc API bên thứ ba.
- Phát application event hoặc gửi message vào broker.
- Ghi file, cập nhật cache, tạo audit log hoặc kích hoạt webhook.
- Lên lịch một công việc nền.

Tác dụng phụ có thể là một phần quan trọng của hợp đồng. Khi đơn hàng được xác nhận, hệ thống có thể phải phát `OrderConfirmed`; khi thanh toán bị từ chối, hệ thống không được gửi yêu cầu giao hàng. Vì vậy, kiểm thử cần xác nhận cả hành động phải xảy ra và hành động bị cấm trong từng tình huống.

Không phải mọi lời gọi nội bộ đều là tác dụng phụ cần kiểm tra. Việc một service gọi private helper nào, dùng bao nhiêu lần một mapper hay chia thuật toán thành những bước nào thường là chi tiết triển khai. Hãy tập trung vào ranh giới có ý nghĩa với hệ thống khác hoặc người dùng.

## 2. Chọn điều cần khẳng định theo hợp đồng

Trước khi viết assertion, mô tả hành vi bằng ba câu hỏi:

1. **Kết quả:** Bên gọi nhận được gì, hoặc phải nhận lỗi nào?
2. **Trạng thái:** Dữ liệu nào thay đổi, dữ liệu nào phải giữ nguyên?
3. **Tác dụng phụ:** Thành phần bên ngoài nào phải được gọi, với dữ liệu gì, và thành phần nào tuyệt đối không được gọi?

Không cần ép mọi bài kiểm thử phải khẳng định cả ba phần. Một bài kiểm thử parser có thể chỉ cần kết quả. Một repository test tập trung vào trạng thái lưu trữ. Một service điều phối thanh toán có thể cần kiểm tra kết quả, thay đổi trạng thái và lời gọi đến cổng thanh toán. Chọn số lượng assertion theo một kịch bản có ý nghĩa, tránh gom nhiều hành vi không liên quan vào cùng một test.

| Loại thao tác | Kết quả nên kiểm tra | Trạng thái nên kiểm tra | Tác dụng phụ nên kiểm tra |
|---|---|---|---|
| Tính toán thuần | Giá trị và quy tắc làm tròn | Thường không có | Thường không có |
| Service cập nhật domain | DTO/kết quả nghiệp vụ hoặc ngoại lệ | Các trường domain đã đổi hoặc được giữ nguyên | Event, gateway hoặc port được gọi khi thuộc hợp đồng |
| Repository | Entity được lưu/đọc và lỗi persistence | Bản ghi, quan hệ, constraint sau khi flush và đọc lại | Thường không kiểm tra ở đây |
| REST controller | HTTP status, header, body | Có thể kiểm tra qua service/repository ở integration test | Thường mock collaborator trong web slice |
| Consumer xử lý message | Ack/nack hoặc kết quả xử lý | Trạng thái nghiệp vụ sau message | Gửi message tiếp theo, retry hoặc dead-letter khi thuộc hợp đồng |

Một cách diễn đạt hữu ích là **Given – When – Then**:

- **Given:** thiết lập dữ liệu và trạng thái ban đầu.
- **When:** thực hiện đúng một hành động của kịch bản.
- **Then:** xác nhận kết quả, trạng thái sau hành động và tác dụng phụ liên quan.

Tên test nên nêu điều kiện và hành vi mong đợi, ví dụ `rejectsTransferWhenBalanceIsInsufficient` hoặc `createsOrderAndPublishesConfirmationEvent`. Người đọc có thể hiểu mục đích mà không cần xem toàn bộ thân test.

## 3. Kiểm tra kết quả và ngoại lệ bằng JUnit

JUnit 5 cung cấp các assertion cơ bản như `assertEquals`, `assertThrows` và `assertAll`. Trong dự án dùng AssertJ, các assertion như `assertThat`, `isEqualByComparingTo` và `extracting` giúp biểu đạt điều kiện rõ ràng hơn.

Với `BigDecimal`, nên so sánh giá trị theo quy tắc nghiệp vụ. `BigDecimal.equals` xét cả scale, do đó `10.0` và `10.00` không bằng nhau theo `equals`. AssertJ có `isEqualByComparingTo` để so sánh giá trị số mà không coi scale là khác biệt.

```java
@Test
void rejectsTransferWhenAmountIsNotPositive() {
    assertThatThrownBy(() -> transferService.transfer(
            1L, 2L, new BigDecimal("0.00")))
        .isInstanceOf(InvalidTransferAmountException.class)
        .hasMessageContaining("greater than zero");
}
```

Chỉ ràng buộc vào phần thông điệp ổn định mà hợp đồng yêu cầu. Nếu thông điệp được bản địa hóa hoặc thay đổi theo dữ liệu đầu vào, kiểm tra toàn bộ chuỗi có thể làm test dễ hỏng dù hành vi vẫn đúng. Trong trường hợp đó, kiểm tra loại ngoại lệ, mã lỗi hoặc thuộc tính lỗi có ý nghĩa hơn.

Khi có nhiều điều kiện cùng mô tả một kết quả, `assertAll` giúp báo cáo nhiều lỗi trong một lần chạy:

```java
assertAll(
    () -> assertThat(receipt.transferId()).isNotBlank(),
    () -> assertThat(receipt.amount()).isEqualByComparingTo("30.00"),
    () -> assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED)
);
```

Không dùng `assertAll` để gom những hành vi độc lập vào một test lớn. Nếu một kịch bản thành công và một kịch bản thất bại có thiết lập khác nhau, hãy tách thành hai test để mỗi test có một nguyên nhân thất bại rõ ràng.

## 4. Kiểm tra trạng thái trong service test

Một unit test service thường dùng Mockito để thay thế collaborator và một fake nhỏ để quan sát trạng thái. Khi service làm thay đổi object domain, có thể kiểm tra trực tiếp object đó. Khi cần xác nhận logic làm việc với repository, hãy dùng fake repository hoặc mock theo đúng mục đích của test.

Ví dụ sau giả định `TransferService` nhận hai tài khoản, trừ số dư tài khoản nguồn, cộng số dư tài khoản đích, lưu cả hai và phát một event. API domain và tên kiểu có thể khác trong ứng dụng thực tế; điều quan trọng là cách chọn điểm quan sát.

```java
@ExtendWith(MockitoExtension.class)
class TransferServiceTest {
    @Mock
    private AccountRepository accounts;

    @Mock
    private ApplicationEventPublisher events;

    @InjectMocks
    private TransferService transferService;

    @Test
    void transfersMoneyAndUpdatesBothBalances() {
        Account source = Account.open(1L, new BigDecimal("100.00"));
        Account target = Account.open(2L, new BigDecimal("20.00"));
        when(accounts.findById(1L)).thenReturn(Optional.of(source));
        when(accounts.findById(2L)).thenReturn(Optional.of(target));

        TransferReceipt receipt = transferService.transfer(
                1L, 2L, new BigDecimal("30.00"));

        assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED);
        assertThat(source.balance()).isEqualByComparingTo("70.00");
        assertThat(target.balance()).isEqualByComparingTo("50.00");
    }
}
```

Các assertion trên kiểm tra kết quả và trạng thái của hai aggregate trong bộ nhớ. Chúng chưa chứng minh dữ liệu đã được ghi xuống database. Nếu mục tiêu của test là xác nhận persistence, hãy thêm một bài kiểm thử repository hoặc integration test riêng để ghi, flush, clear persistence context rồi đọc lại.

Đối với kịch bản thất bại, trạng thái trước và sau cần được so sánh. Ví dụ, khi số dư không đủ, số dư hai tài khoản phải giữ nguyên. Đây là một assertion quan trọng vì một service có thể ném đúng ngoại lệ nhưng đã thay đổi một object trước khi phát hiện lỗi.

```java
@Test
void keepsBalancesUnchangedWhenSourceHasInsufficientFunds() {
    Account source = Account.open(1L, new BigDecimal("10.00"));
    Account target = Account.open(2L, new BigDecimal("20.00"));
    when(accounts.findById(1L)).thenReturn(Optional.of(source));
    when(accounts.findById(2L)).thenReturn(Optional.of(target));

    assertThatThrownBy(() -> transferService.transfer(
            1L, 2L, new BigDecimal("30.00")))
        .isInstanceOf(InsufficientFundsException.class);

    assertThat(source.balance()).isEqualByComparingTo("10.00");
    assertThat(target.balance()).isEqualByComparingTo("20.00");
}
```

Kiểm tra trạng thái ban đầu và trạng thái cuối giúp test diễn đạt rõ tính nguyên tử ở mức nghiệp vụ: thao tác thất bại không để lại thay đổi dở dang trong domain object. Nếu ứng dụng còn có transaction database, bài kiểm thử persistence cần xác nhận rollback ở đúng ranh giới transaction.

## 5. Kiểm tra tác dụng phụ bằng Mockito

Mockito cho phép xác nhận một collaborator đã được gọi, số lần gọi và dữ liệu truyền vào. Dùng `ArgumentCaptor` khi cần kiểm tra nội dung event hoặc request được gửi ra ngoài.

```java
@Test
void publishesTransferCompletedEventWithTheTransferredAmount() {
    Account source = Account.open(1L, new BigDecimal("100.00"));
    Account target = Account.open(2L, new BigDecimal("20.00"));
    when(accounts.findById(1L)).thenReturn(Optional.of(source));
    when(accounts.findById(2L)).thenReturn(Optional.of(target));

    transferService.transfer(1L, 2L, new BigDecimal("30.00"));

    ArgumentCaptor<TransferCompleted> eventCaptor =
            ArgumentCaptor.forClass(TransferCompleted.class);
    verify(events).publishEvent(eventCaptor.capture());
    assertThat(eventCaptor.getValue().amount())
            .isEqualByComparingTo("30.00");
    assertThat(eventCaptor.getValue().sourceAccountId()).isEqualTo(1L);
    assertThat(eventCaptor.getValue().targetAccountId()).isEqualTo(2L);
}
```

Khi kịch bản thất bại yêu cầu không gửi thông báo, có thể kiểm tra ranh giới đó:

```java
verify(events, never()).publishEvent(any(TransferCompleted.class));
```

Hoặc nếu event publisher chỉ được dùng cho hành vi này trong test:

```java
verifyNoInteractions(events);
```

Chọn assertion hẹp nhất phù hợp với hợp đồng. `verifyNoInteractions` trên một mock có nhiều vai trò có thể làm test dễ hỏng khi hệ thống thêm một tương tác hợp lệ khác. Tương tự, không nên mặc định thêm `verifyNoMoreInteractions` cho mọi mock; điều đó thường khóa test vào thứ tự và cấu trúc triển khai.

Hãy phân biệt rõ ba mức bằng chứng:

1. `verify(events).publishEvent(...)` chứng minh service đã gọi Spring event publisher.
2. Test listener trong ApplicationContext chứng minh listener nhận và xử lý event theo cấu hình đang chạy.
3. Integration test với broker thật hoặc môi trường tương thích chứng minh message có thể được gửi/nhận qua hạ tầng messaging.

Một mức không tự động chứng minh mức tiếp theo. Ví dụ, xác nhận đã gọi `publishEvent` không chứng minh listener đã hoàn thành, email đã được gửi hoặc message đã được broker lưu thành công.

## 6. Kiểm tra dữ liệu persistence với Spring Test

Với JPA, `@DataJpaTest` tạo một lát kiểm thử tập trung vào repository và cấu hình persistence. Test thường chạy trong transaction được quản lý và rollback sau mỗi test. Điều này giúp cô lập dữ liệu, nhưng có một điểm dễ gây hiểu nhầm: entity vừa lưu có thể vẫn nằm trong persistence context, nên đọc lại cùng entity không chứng minh dữ liệu đã được ghi và ánh xạ lại từ database.

Để kiểm tra đường đi qua SQL và mapping, hãy flush rồi clear persistence context trước khi đọc lại:

```java
@DataJpaTest
class AccountRepositoryTest {
    @Autowired
    private AccountRepository accounts;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void persistsAndReloadsAccountBalance() {
        Account saved = accounts.save(
                Account.open(null, new BigDecimal("70.00")));

        entityManager.flush();
        Long accountId = saved.id();
        entityManager.clear();

        Account reloaded = accounts.findById(accountId).orElseThrow();

        assertThat(reloaded.balance()).isEqualByComparingTo("70.00");
    }
}
```

`flush()` đẩy các thay đổi đang chờ xuống database trong transaction hiện tại. `clear()` loại các entity đang được quản lý khỏi persistence context, buộc lần đọc sau phải nạp lại dữ liệu. Cách này giúp phát hiện nhiều lỗi mapping, kiểu dữ liệu, câu lệnh SQL và constraint mà việc kiểm tra object ngay sau `save()` có thể bỏ sót.

Tuy nhiên, flush không tương đương commit. Test transaction được rollback sau test vẫn chưa chứng minh hành vi phụ thuộc vào commit thực sự. Nếu cần kiểm tra ranh giới commit, transaction propagation, trigger chạy sau commit hoặc xử lý chỉ chạy sau commit, hãy thiết kế test có transaction boundary thật, chẳng hạn điều khiển bằng `TransactionTemplate` và xác nhận dữ liệu từ transaction khác sau khi transaction đầu đã commit.

Với test kiểm tra rollback, hãy thực hiện thao tác trong transaction có thể rollback, gây lỗi tại đúng thời điểm cần kiểm tra, rồi đọc dữ liệu từ một transaction mới để xác nhận trạng thái cuối. Tránh đọc trong cùng persistence context vì dữ liệu đã cache có thể làm kết quả sai lệch.

## 7. Kiểm tra phản hồi HTTP với MockMvc và WebTestClient

Ở tầng web, kết quả thường là HTTP response. `MockMvc` phù hợp để kiểm tra Spring MVC mà không cần khởi động HTTP server thật. Một web slice với `@WebMvcTest` tập trung vào controller, binding, validation, exception handler, serialization và cấu hình web liên quan.

```java
@WebMvcTest(TransferController.class)
class TransferControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private TransferService transferService;

    @Test
    void returnsCreatedResponseForSuccessfulTransfer() throws Exception {
        when(transferService.transfer(anyLong(), anyLong(), any()))
                .thenReturn(new TransferReceipt(
                        "tr-42", new BigDecimal("30.00"),
                        TransferStatus.COMPLETED));

        mockMvc.perform(post("/api/transfers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sourceAccountId": 1,
                                  "targetAccountId": 2,
                                  "amount": 30.00
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(jsonPath("$.transferId").value("tr-42"))
                .andExpect(jsonPath("$.status").value("COMPLETED"));
    }
}
```

Trong web slice, service được mock để test tập trung vào hợp đồng HTTP. Test này không chứng minh service đã cập nhật database. Trách nhiệm đó thuộc service/repository integration test. Cũng không nên kiểm tra chi tiết lời gọi private method của controller; hãy xác nhận response mà client nhận được.

Với ứng dụng Spring WebFlux, `WebTestClient` có thể kiểm tra controller hoặc gọi endpoint trong môi trường tích hợp. Khi kiểm tra `Flux` hoặc `Mono`, hãy xác nhận cả dữ liệu phát ra, lỗi và việc hoàn tất nếu chúng thuộc hợp đồng. Đừng chỉ kiểm tra phần tử đầu tiên nếu endpoint có thể trả nhiều phần tử hoặc lỗi xảy ra sau phần tử đầu.

## 8. Event, transaction và xử lý bất đồng bộ

Spring application event mặc định được phát và xử lý đồng bộ trong cùng luồng gọi nếu listener không được cấu hình bất đồng bộ. Khi dùng `@Async`, message broker hoặc executor, thời điểm hoàn thành không còn đồng nhất với thời điểm service trả về.

Một số điểm cần phân biệt:

- Kiểm tra service phát event: mock `ApplicationEventPublisher` hoặc quan sát event tại application context.
- Kiểm tra listener: khởi tạo ApplicationContext với listener thật và xác nhận trạng thái mà listener tạo ra.
- Kiểm tra event chỉ chạy sau commit: phải tạo một transaction thực sự được commit. Test-managed transaction mặc định rollback có thể khiến listener dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` không được gọi.
- Kiểm tra tác vụ bất đồng bộ: đồng bộ với kết quả bằng `CountDownLatch`, `CompletableFuture` hoặc một điều kiện chờ có timeout; không dùng `Thread.sleep` cố định để đoán thời gian hoàn tất.

Ví dụ dùng latch để đợi một listener bất đồng bộ hoàn thành:

```java
CountDownLatch handled = new CountDownLatch(1);

@Async
@EventListener
void onTransferCompleted(TransferCompleted event) {
    // Xử lý event trong listener.
    handled.countDown();
}

@Test
void eventuallyHandlesPublishedEvent() throws InterruptedException {
    eventPublisher.publishEvent(new TransferCompleted(/* dữ liệu test */));

    assertThat(handled.await(2, TimeUnit.SECONDS)).isTrue();
}
```

Đây là minh họa về cơ chế đồng bộ trong test; trong mã thực tế, listener thường là bean riêng và latch được đặt trong test observer hoặc collaborator được tiêm vào. Timeout phải đủ rộng cho môi trường CI nhưng vẫn hữu hạn để test không treo. Nếu test timeout, hãy báo lỗi rõ ràng thay vì tiếp tục assertion trên trạng thái chưa hoàn tất.

Với tác vụ có retry, hãy xác định hợp đồng về số lần thử, điều kiện retry và trạng thái cuối. Kiểm tra số lần gọi chỉ khi số lần đó là yêu cầu vận hành có ý nghĩa; nếu không, ưu tiên kiểm tra kết quả cuối cùng và việc không tạo tác dụng phụ trùng lặp.

## 9. Kiểm tra tác dụng phụ bên ngoài ứng dụng

Đối với email, thanh toán, vận chuyển hoặc API bên thứ ba, unit test nên phụ thuộc vào một port/interface mà ứng dụng kiểm soát. Mockito có thể xác nhận request được gửi với đúng dữ liệu, còn fake có thể mô phỏng phản hồi ổn định. Không gọi dịch vụ thật trong unit test vì điều đó khiến test phụ thuộc mạng, credential, chi phí và trạng thái của hệ thống ngoài.

Ở mức integration, khi cần xác nhận cách client HTTP, serialization, timeout hoặc retry tương tác với dịch vụ ngoài, dùng mock server hoặc môi trường thử nghiệm có kiểm soát. Với database, broker hoặc cache, Testcontainers hoặc hạ tầng test tương đương có thể cung cấp dịch vụ thật trong môi trường cô lập. Hãy chọn hạ tầng thật khi câu hỏi kiểm thử liên quan đến hành vi giao thức hoặc cấu hình mà mock không thể chứng minh.

Một số hợp đồng tác dụng phụ thường gặp:

- Thanh toán thành công: gửi một yêu cầu authorize với đúng amount và currency.
- Thanh toán bị từ chối: không tạo yêu cầu giao hàng.
- Đơn hàng đã xác nhận: phát một event có order id và trạng thái chính xác.
- Yêu cầu tạo tài nguyên lặp lại: không gửi thông báo trùng nếu hệ thống cam kết idempotency.
- Dữ liệu không hợp lệ: không gọi gateway, không phát event và không ghi bản ghi nghiệp vụ.

Khi kiểm tra “không có tác dụng phụ”, hãy xác định phạm vi cụ thể. Chẳng hạn, một lệnh tìm kiếm có thể được phép ghi metric nhưng không được tạo giao dịch thanh toán. Không nên dùng một assertion toàn cục để cấm mọi tương tác nếu hợp đồng chỉ cấm một loại hành động.

## 10. Chọn mức kiểm thử trong Spring

Mỗi mức kiểm thử cung cấp một loại bằng chứng khác nhau:

| Mức kiểm thử | Cách thường dùng trong Spring | Bằng chứng chính |
|---|---|---|
| Unit test | JUnit 5, Mockito, fake tự viết | Quy tắc service/domain, kết quả, trạng thái object và lời gọi port |
| Web slice | `@WebMvcTest`, `MockMvc` | Binding, validation, HTTP status, header, body và exception mapping |
| Persistence slice | `@DataJpaTest` | Mapping, query, SQL, constraint và trạng thái database |
| Integration test | `@SpringBootTest` cùng các dependency test | Wiring giữa bean, transaction, event listener và luồng xử lý kết hợp |
| End-to-end test | Ứng dụng chạy trong môi trường gần thực tế | Hành vi xuyên qua ranh giới HTTP, database, broker và hệ thống phụ thuộc |

Không cần dùng `@SpringBootTest` cho mọi tình huống. Test càng rộng thường càng tốn thời gian và có nhiều nguyên nhân thất bại. Hãy dùng mức nhỏ nhất vẫn cung cấp được bằng chứng cần thiết; chỉ mở rộng khi điều cần chứng minh nằm ở cấu hình hoặc tương tác giữa nhiều thành phần.

Một service test với mock repository có thể chứng minh service yêu cầu lưu dữ liệu, nhưng không chứng minh repository hoạt động đúng. Một repository test có thể chứng minh mapping, nhưng không chứng minh controller trả HTTP status phù hợp. Chia trách nhiệm như vậy giúp mỗi test có mục tiêu và tín hiệu lỗi rõ ràng.

## 11. Những lỗi thiết kế assertion thường gặp

### Chỉ kiểm tra kết quả trả về

Service có thể trả receipt thành công nhưng không lưu dữ liệu hoặc không phát event bắt buộc. Hãy kiểm tra thêm state và side effect khi chúng thuộc hợp đồng.

### Chỉ kiểm tra lời gọi `save`

Mockito xác nhận lời gọi đến mock, không xác nhận SQL, transaction hay dữ liệu cuối cùng. Dùng repository test hoặc integration test để kiểm tra persistence.

### Kiểm tra implementation thay vì hành vi

Assert vào số lần gọi helper nội bộ, thứ tự các bước không có ý nghĩa bên ngoài hoặc tên method riêng khiến test dễ hỏng khi refactor. Chỉ kiểm tra tương tác tại ranh giới có ý nghĩa.

### Kiểm tra quá ít ở nhánh thất bại

Test xác nhận có exception nhưng bỏ qua dữ liệu đã thay đổi hoặc message đã gửi. Với mỗi nhánh thất bại quan trọng, xác nhận trạng thái cần giữ nguyên và side effect bị cấm.

### Đọc entity ngay sau khi lưu

Persistence context có thể trả về chính object trong bộ nhớ. Flush và clear trước khi đọc lại để kiểm tra đường đi qua database.

### Chờ bất đồng bộ bằng `Thread.sleep`

Thời gian cố định có thể quá ngắn trên CI hoặc làm test chậm không cần thiết. Dùng latch, future hoặc điều kiện chờ có timeout để đồng bộ theo sự kiện hoàn tất thực tế.

### Mock tất cả collaborator trong integration test

Nếu mọi thành phần đều là mock, test chỉ kiểm tra cách các mock được gọi và không còn xác minh wiring thật. Giữ lại những thành phần cần kiểm tra, thay thế đúng ranh giới bên ngoài.

### Assertion quá rộng hoặc quá chặt

`isNotNull()` thường không chứng minh được quy tắc nghiệp vụ. Ngược lại, so sánh toàn bộ object có thể khóa test vào trường kỹ thuật như timestamp, generated id hoặc metadata không thuộc hợp đồng. Chọn các thuộc tính quan trọng và nêu rõ vì sao chúng quan trọng.

## 12. Quy trình thiết kế một test có thể tin cậy

Khi bắt đầu một kịch bản, hãy thực hiện lần lượt:

1. Viết điều kiện ban đầu có liên quan: dữ liệu, quyền, trạng thái hiện tại và phản hồi của collaborator.
2. Gọi một hành động công khai của thành phần đang kiểm thử.
3. Kiểm tra kết quả trực tiếp: giá trị trả về, ngoại lệ hoặc HTTP response.
4. Đọc trạng thái sau hành động tại đúng ranh giới cần xác nhận: object, fake repository hay database.
5. Kiểm tra các tác dụng phụ bắt buộc và các tác dụng phụ bị cấm.
6. Đảm bảo test tự thiết lập dữ liệu, không phụ thuộc thứ tự chạy và có timeout cho xử lý bất đồng bộ.

Trước khi hoàn tất, hãy tự hỏi: nếu xóa dòng code thực hiện thay đổi quan trọng, test nào sẽ thất bại? Nếu câu trả lời là “không có test nào”, có thể bạn đang chỉ kiểm tra đường đi thành công mà chưa kiểm tra kết quả thực tế. Nếu test chỉ thất bại khi đổi tên một helper nội bộ, assertion có thể đang gắn quá chặt với implementation.

## 13. Ví dụ ma trận kịch bản cho một thao tác chuyển tiền

Ma trận dưới đây giúp xác định các assertion cần có trước khi triển khai test. Không phải mọi dòng đều cần một test riêng; có thể nhóm các assertion cùng mô tả một kịch bản.

| Kịch bản | Kết quả | Trạng thái cuối | Tác dụng phụ |
|---|---|---|---|
| Chuyển tiền hợp lệ | Trả receipt `COMPLETED` | Trừ nguồn, cộng đích đúng số tiền | Phát một `TransferCompleted` đúng dữ liệu |
| Số tiền bằng 0 hoặc âm | Ném lỗi validation | Không đổi số dư | Không gọi gateway hoặc phát event |
| Số dư không đủ | Ném `InsufficientFundsException` | Không đổi số dư hai tài khoản | Không phát event hoàn tất |
| Không tìm thấy tài khoản | Ném lỗi not-found phù hợp | Không tạo giao dịch dở dang | Không phát event hoàn tất |
| Yêu cầu lặp có cùng idempotency key | Trả kết quả đã có theo hợp đồng | Không tạo giao dịch thứ hai | Không gửi yêu cầu thanh toán trùng |

Ma trận này cũng giúp phát hiện thiếu coverage theo hợp đồng. Ví dụ, nếu test chỉ xác nhận `COMPLETED` mà không kiểm tra số dư và event, một lỗi cập nhật dữ liệu hoặc phát sai event vẫn có thể lọt qua.

## 14. Nguyên tắc ghi nhớ

- Kết quả trả về cho biết bên gọi nhận được gì.
- Trạng thái cho biết dữ liệu cuối cùng ra sao.
- Tác dụng phụ cho biết hệ thống đã tác động đến những ranh giới bên ngoài nào.
- Chỉ kiểm tra những gì thuộc hợp đồng của kịch bản, tại đúng mức kiểm thử có thể cung cấp bằng chứng.
- Mock xác nhận tương tác; fake hỗ trợ quan sát hành vi; integration test xác nhận sự phối hợp với hạ tầng thật.
- Với persistence, phân biệt rõ `save`, `flush` và `commit`; với xử lý bất đồng bộ, phân biệt phát lệnh và hoàn tất xử lý.

Một bài kiểm thử được thiết kế tốt sẽ thất bại khi hành vi quan trọng bị sai, đồng thời vẫn ổn định khi cấu trúc nội bộ được refactor. Hãy dùng kết quả, trạng thái và tác dụng phụ như ba góc nhìn bổ sung để kiểm chứng trọn vẹn hợp đồng của từng thao tác trong ứng dụng Spring.
