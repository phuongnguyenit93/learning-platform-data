# Kiểm thử listener trong Spring Modulith

Listener là nơi application event được chuyển thành hành động nghiệp vụ: cập nhật read model, giữ tồn kho, tạo hóa đơn hoặc khởi động một quy trình tiếp theo. Một listener có thể chạy đồng bộ, sau khi transaction commit hoặc bất đồng bộ; nó cũng có thể được giao lại khi xử lý thất bại. Vì vậy, kiểm thử listener cần xác nhận cả logic nghiệp vụ lẫn thời điểm xử lý, ranh giới module và cách hệ thống phản ứng khi có lỗi.

Trong module `SPRING_MODULITH_APPLICATION_EVENTS`, publisher và listener giao tiếp qua application event để giảm phụ thuộc trực tiếp giữa các module. Spring Modulith bổ sung `@ApplicationModuleListener`, `@ApplicationModuleTest` và API `Scenario` để kiểm thử giao tiếp theo ranh giới module. Một bộ kiểm thử tốt cần chứng minh listener nhận đúng event, tạo đúng thay đổi, không chạy sai transaction phase và có thể phục hồi an toàn khi event được giao lại.

## 1. Xác định hành vi cần kiểm thử

Trước khi viết test, hãy mô tả hành vi quan sát được từ góc nhìn nghiệp vụ. Ví dụ, khi đơn hàng hoàn tất, module kho nhận `OrderCompleted` và xác nhận lượng hàng đã được giữ. Test cần chứng minh kết quả tồn kho thay đổi đúng theo event, đồng thời không làm thay đổi dữ liệu của đơn hàng thuộc module khác.

Một listener thường có nhiều khía cạnh cần kiểm tra:

- **Event contract:** listener nhận đúng loại event và diễn giải đúng các trường dữ liệu.
- **Business effect:** dữ liệu hoặc trạng thái do listener sở hữu được cập nhật đúng.
- **Transaction phase:** listener chỉ chạy ở thời điểm mong đợi, ví dụ sau commit.
- **Module boundary:** listener được phát hiện và hoạt động trong phạm vi module dự kiến.
- **Failure behavior:** lỗi được truyền ra đúng cách để transaction hoặc publication được xử lý phù hợp.
- **Idempotency:** giao lại cùng event không tạo side effect ngoài ý muốn.
- **Asynchronous behavior:** test đợi điều kiện hoàn tất thay vì giả định listener đã chạy ngay sau khi publish.
- **Observability:** lỗi và kết quả xử lý có đủ thông tin để điều tra mà không làm lộ dữ liệu nhạy cảm.

Không phải test nào cũng cần kiểm tra tất cả các khía cạnh. Unit test tập trung vào logic listener; module integration test tập trung vào giao tiếp giữa các thành phần; test có database/broker tập trung vào transaction và hạ tầng lưu trữ.

## 2. Chọn đúng cấp độ kiểm thử

Có thể chia kiểm thử listener thành các lớp sau:

| Cấp độ | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Unit test | Listener hoặc service xử lý event với dependency giả lập | Kiểm tra mapping, nhánh nghiệp vụ và dữ liệu đầu vào |
| Spring integration test | Application context, publisher và listener thật | Xác nhận event được dispatch và listener được gọi |
| Module integration test | Một module Spring Modulith cùng các dependency cần thiết | Xác nhận giao tiếp và ranh giới module |
| Transaction test | Transaction nguồn, listener phase và transaction xử lý | Xác nhận commit/rollback ảnh hưởng đúng tới listener |
| Persistence test | Event Publication Registry và repository thật | Xác nhận publication được lưu, hoàn tất hoặc còn dang dở đúng cách |
| Broker integration test | Adapter, broker và consumer | Xác nhận message được chuyển, nhận và acknowledge theo cấu hình |

Nên bắt đầu ở cấp nhỏ nhất có thể chứng minh hành vi, sau đó thêm integration test cho những bảo đảm phụ thuộc Spring, database hoặc broker. Một unit test gọi trực tiếp phương thức listener không chứng minh annotation đã được Spring đăng ký hoặc transaction phase hoạt động đúng.

## 3. Kiểm thử logic listener bằng unit test

Listener nên mỏng: nhận event, kiểm tra dữ liệu cần thiết và chuyển công việc tới service sở hữu nghiệp vụ. Khi đó, unit test có thể gọi trực tiếp listener và xác minh service nhận đúng thông tin.

Ví dụ event:

```java
public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant completedAt
) {}
```

Listener của module kho:

```java
@Component
class InventoryOnOrderCompleted {

    private final InventoryService inventory;

    InventoryOnOrderCompleted(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        inventory.confirmOrder(event.orderId());
    }
}
```

Unit test có thể dùng Mockito:

```java
@ExtendWith(MockitoExtension.class)
class InventoryOnOrderCompletedTests {

    @Mock
    InventoryService inventory;

    @InjectMocks
    InventoryOnOrderCompleted listener;

    @Test
    void confirmsInventoryForCompletedOrder() {
        UUID orderId = UUID.randomUUID();
        OrderCompleted event = new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()
        );

        listener.on(event);

        verify(inventory).confirmOrder(orderId);
        verifyNoMoreInteractions(inventory);
    }
}
```

Test này xác nhận listener chuyển đúng `orderId` tới service. Nó không khởi tạo Spring context và không thực thi semantics của `@ApplicationModuleListener`; phần đó cần được kiểm thử ở cấp integration.

### Kiểm tra dữ liệu và nhánh nghiệp vụ

Nếu listener có logic chuyển đổi dữ liệu, hãy kiểm tra các trường quan trọng thay vì chỉ xác minh một phương thức đã được gọi. Ví dụ, khi event chứa nhiều dòng hàng, test nên xác nhận đúng mã sản phẩm, số lượng, đơn vị tiền tệ và định danh nghiệp vụ được truyền tới service.

Nếu listener chỉ chuyển tiếp event, tránh đưa quá nhiều logic vào listener. Quy tắc nghiệp vụ phức tạp nên nằm trong service có thể kiểm thử độc lập.

## 4. Kiểm thử event dispatch trong Spring context

Unit test không xác nhận Spring đã phát hiện listener. Một integration test có thể tạo application context, phát event qua `ApplicationEventPublisher` và xác nhận listener tạo ra thay đổi thật trong repository.

Ví dụ cấu trúc test:

```java
@SpringBootTest
class InventoryEventIntegrationTests {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    InventoryRepository inventory;

    @Test
    void updatesInventoryWhenOrderCompleted() {
        UUID orderId = UUID.randomUUID();
        inventory.save(InventoryReservation.forOrder(orderId));

        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()
        ));

        // Chỉ phù hợp nếu listener xử lý đồng bộ trong cùng test flow.
        assertThat(inventory.findReservation(orderId).orElseThrow())
                .isConfirmed();
    }
}
```

Đây là ví dụ cho listener đồng bộ. Nếu listener dùng `@ApplicationModuleListener` hoặc một executor bất đồng bộ, không nên đọc repository ngay sau `publishEvent()` rồi giả định công việc đã hoàn tất. Hãy đợi một điều kiện quan sát được hoặc dùng test support của Spring Modulith.

Với test sử dụng database, tạo dữ liệu ban đầu rõ ràng và dọn dữ liệu sau test. Tránh phụ thuộc vào thứ tự chạy test hoặc dữ liệu còn sót từ test khác.

## 5. Dùng `@ApplicationModuleTest` để kiểm thử ranh giới module

Spring Modulith cung cấp `@ApplicationModuleTest` để tạo test context tập trung vào một application module. Cách này hữu ích khi muốn kiểm tra listener thuộc module kho mà không khởi động toàn bộ ứng dụng cùng mọi module không liên quan.

Ví dụ:

```java
@ApplicationModuleTest
class InventoryModuleEventTests {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    InventoryRepository inventory;

    @Test
    void handlesOrderCompletedEvent() {
        UUID orderId = UUID.randomUUID();
        inventory.save(InventoryReservation.forOrder(orderId));

        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()
        ));

        // Xác nhận trạng thái theo cơ chế đồng bộ hoặc await phù hợp.
    }
}
```

`@ApplicationModuleTest` giúp kiểm tra module trong phạm vi kiến trúc Spring Modulith. Tùy cấu hình bootstrap và module dependency, test có thể cần import thêm bean hoặc thay thế một dependency ngoài module bằng test double. Không nên mở rộng context tới toàn ứng dụng chỉ để làm một listener test chạy được nếu điều đó che giấu phụ thuộc module không mong muốn.

## 6. Dùng `Scenario` để kiểm thử luồng event

Spring Modulith cung cấp `Scenario` như một test API để mô tả một event được publish và chờ một event khác được phát ra. Cách này hữu ích khi kiểm thử tương tác giữa publisher và listener mà không phải tự quản lý latch hoặc gọi `Thread.sleep()`.

Ví dụ minh họa:

```java
@ApplicationModuleTest
class OrderCompletionScenarioTests {

    @Test
    void publishesInventoryConfirmedAfterOrderCompletion(
            Scenario scenario
    ) {
        UUID orderId = UUID.randomUUID();

        scenario.publish(new OrderCompleted(
                        UUID.randomUUID(), orderId, Instant.now()))
                .andWaitForEventOfType(InventoryConfirmed.class)
                .matching(event -> event.orderId().equals(orderId))
                .toArrive();
    }
}
```

Ví dụ thể hiện ý tưởng kiểm thử theo kịch bản: publish event đầu vào, đợi event kết quả và lọc theo dữ liệu nghiệp vụ. Kiểu event kết quả `InventoryConfirmed` cần được ứng dụng phát ra nếu đó là hợp đồng của luồng. Cú pháp chi tiết của `Scenario` và cách inject test API cần khớp phiên bản Spring Modulith trong dự án.

Nếu listener chỉ cập nhật database và không phát event tiếp theo, hãy kiểm tra trạng thái repository bằng một cơ chế await có timeout hoặc dùng một tín hiệu test rõ ràng. Không thêm event sản xuất chỉ để thỏa mãn một test nếu nghiệp vụ không cần event đó.

## 7. Kiểm thử listener chạy sau commit

Với `@TransactionalEventListener`, listener thường được gọi ở transaction phase được cấu hình, phổ biến là `AFTER_COMMIT`. Mục tiêu là chỉ phản ứng với thay đổi nghiệp vụ đã commit. Test cần chứng minh event được phát trong transaction và listener chỉ chạy sau khi transaction kết thúc thành công.

Các tình huống nên kiểm tra:

- Transaction commit: listener được gọi sau commit.
- Transaction rollback: listener phase `AFTER_COMMIT` không thực hiện hành động.
- Không có transaction: hành vi tuân theo cấu hình `fallbackExecution`; mặc định listener transaction-bound không được gọi nếu không có transaction phù hợp.
- Listener cần ghi database: transaction xử lý riêng được mở đúng theo thiết kế.

Test rollback có thể dùng transaction test do Spring quản lý và chủ động kết thúc transaction theo cách phù hợp với test framework. Cần chú ý rằng nhiều test `@Transactional` mặc định rollback ở cuối phương thức; nếu không commit thật, listener `AFTER_COMMIT` sẽ không chạy. Một test chỉ publish event trong transaction test rồi kiểm tra listener đã chạy có thể sai giả định.

Một cách tổ chức là gọi service nghiệp vụ có transaction từ test không nằm trong transaction bao ngoài, để transaction của service commit trước khi assertion được thực hiện. Nếu test cần kiểm soát commit/rollback thủ công, dùng test transaction API và xác nhận rõ thời điểm kết thúc transaction.

### Listener sau commit có transaction riêng

Sau khi transaction nguồn commit, listener không còn tham gia transaction đó. Nếu listener cần cập nhật database, hãy thiết kế transaction xử lý riêng, ví dụ service được gọi từ listener có `@Transactional`. Test cần xác nhận thay đổi của listener được commit hoặc rollback độc lập theo đúng yêu cầu.

## 8. Kiểm thử listener bất đồng bộ

Listener bất đồng bộ có thể chạy trên thread khác sau khi publisher trả về. Do đó, assertion tức thì dễ gây flaky test.

Không nên viết:

```java
events.publishEvent(event);
Thread.sleep(500);
assertThat(repository.findById(id)).isPresent();
```

Thời gian chờ cố định không bảo đảm listener đã chạy; trên máy chậm, test vẫn có thể thất bại, còn trên máy nhanh thì lãng phí thời gian.

Thay vào đó, đợi điều kiện có ý nghĩa với timeout hữu hạn:

```java
await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(repository.findById(id))
                        .isPresent()
        );
```

Ví dụ sử dụng Awaitility; cần khai báo dependency test phù hợp. Có thể dùng `Scenario` của Spring Modulith khi test theo luồng event. Timeout nên đủ cho môi trường CI nhưng không quá dài để che giấu listener bị treo.

### Tránh dùng chung executor gây race trong test

Nếu nhiều test cùng dùng executor hoặc queue chung, một listener có thể xử lý event của test khác. Hãy dùng dữ liệu định danh riêng cho từng test, dọn dữ liệu đúng cách và chờ theo điều kiện gắn với ID cụ thể. Không chỉ chờ một biến đếm toàn cục tăng lên vì một event khác có thể làm assertion vượt qua.

## 9. Kiểm thử listener thất bại và publication chưa hoàn tất

Listener có thể ném exception khi database không sẵn sàng, dependency timeout hoặc payload không hợp lệ. Với Event Publication Registry, cần kiểm tra publication chưa hoàn tất được giữ lại theo cấu hình và có thể được quan sát/phục hồi.

Một kịch bản integration test có thể:

1. Dùng persistent Event Publication Registry tương ứng với ứng dụng.
2. Cấu hình listener test có thể thất bại theo một cờ hoặc dependency giả lập.
3. Publish event trong transaction phù hợp.
4. Xác nhận listener thất bại và publication còn incomplete.
5. Khắc phục điều kiện lỗi trong test.
6. Resubmit publication qua API hỗ trợ của phiên bản Spring Modulith.
7. Xác nhận listener hoàn tất và publication được đánh dấu hoàn thành.

Không nên chỉ xác minh exception được ném ra rồi kết luận registry hoạt động đúng. Cần kiểm tra trạng thái publication trong repository/API và kết quả nghiệp vụ sau khi phục hồi.

`IncompleteEventPublications` là abstraction phù hợp để làm việc với các publication chưa hoàn tất. Cách liệt kê hoặc resubmit phụ thuộc API phiên bản cụ thể; hãy dùng public API thay vì sửa bảng registry bằng SQL trong test hoặc production.

## 10. Kiểm thử idempotency và giao event lặp

Một listener có thể thực hiện xong thay đổi nghiệp vụ nhưng tiến trình dừng trước khi registry ghi nhận publication hoàn tất. Khi publication được giao lại, listener phải tránh tạo side effect trùng.

Các test quan trọng:

- Publish cùng event hai lần và xác nhận thay đổi nghiệp vụ chỉ được áp dụng một lần.
- Giao hai event có cùng `businessOperationId` nhưng khác `eventId` nếu nghiệp vụ yêu cầu một hành động logic duy nhất.
- Xử lý đồng thời cùng một event ở hai instance hoặc hai thread và xác nhận unique constraint bảo vệ dữ liệu.
- Làm listener thất bại trước commit rồi retry, xác nhận transaction rollback không để lại dấu vết xử lý sai.
- Mô phỏng lỗi sau side effect ngoài và trước khi ghi nhận hoàn tất; xác nhận provider idempotency key hoặc quy trình đối soát ngăn tác động trùng.

Ví dụ assertion nên kiểm tra trạng thái nghiệp vụ cuối cùng, số bản ghi và tổng giá trị. Chỉ xác minh một phương thức được gọi một lần trong Mockito không chứng minh database có unique constraint hoặc xử lý đồng thời an toàn.

## 11. Kiểm thử listener dùng nhiều module

Một module có thể phát event mà nhiều module khác cùng lắng nghe. Khi kiểm thử, cần xác nhận mỗi listener chịu trách nhiệm cho một hành vi riêng và publisher không cần biết danh sách consumer.

Ví dụ `OrderCompleted` có thể được nhận bởi:

- Module kho để xác nhận reservation.
- Module hóa đơn để tạo chứng từ.
- Module thông báo để lên lịch gửi thông tin cho khách hàng.

Không nên viết một test khổng lồ khởi động toàn ứng dụng rồi kiểm tra mọi side effect trong cùng một assertion. Có thể viết test riêng cho từng module listener, sau đó thêm một số end-to-end test cho các luồng nghiệp vụ quan trọng.

Với `@ApplicationModuleTest`, mỗi module test tập trung vào module sở hữu listener và những dependency được phép. Test kiến trúc module có thể bổ sung để xác nhận phụ thuộc giữa các module không bị mở rộng ngoài dự kiến.

## 12. Kiểm thử externalized event và broker consumer

Nếu listener hoặc adapter chuyển event tới Kafka/RabbitMQ, cần tách test application listener khỏi test broker. Unit test không nên cần broker đang chạy; broker integration test cần kiểm tra đúng những bảo đảm của adapter.

Các tình huống nên kiểm tra:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Event được externalize | Đúng exchange/topic và routing key được sử dụng |
| Serialization | Consumer đọc được payload theo schema đã công bố |
| Broker unavailable | Publication không bị đánh dấu hoàn tất nhầm khi gửi thất bại |
| Acknowledgement timeout | Hệ thống chấp nhận khả năng giao lặp và consumer idempotent |
| Consumer xử lý thành công | Offset/acknowledgement chỉ được xác nhận theo thứ tự transaction đã chọn |
| Consumer ném exception | Retry/DLQ policy hoạt động như cấu hình |
| Message không hợp lệ | Được cách ly hoặc dead-letter theo chính sách |

Có thể dùng Testcontainers để chạy broker cô lập trong integration test. Chỉ thêm broker test khi bài kiểm thử cần xác nhận protocol, topology hoặc adapter thật; không dùng broker container cho mọi unit test listener.

## 13. Kiểm thử bảo mật và dữ liệu event

Listener nhận dữ liệu từ event contract và có thể ghi dữ liệu vào read model, log hoặc gọi API ngoài. Test cần xác nhận listener không vô tình làm lộ dữ liệu nhạy cảm và không tin metadata không được xác thực.

Một số kiểm tra phù hợp:

- Event DTO chỉ chứa các trường listener được phép nhận.
- Log không ghi toàn bộ payload hoặc thông tin cá nhân không cần thiết.
- Consumer kiểm tra quyền theo tenant/resource nếu event có phạm vi dữ liệu.
- Event không hợp lệ hoặc thiếu trường bắt buộc được xử lý theo chính sách lỗi.
- Correlation ID và event ID không bị dùng thay cho thông tin xác thực.
- Listener không gọi service thuộc module khác qua đường truy cập nội bộ trái với ranh giới đã công bố.

Các kiểm thử này nên dựa trên hợp đồng và quyền thực tế của ứng dụng, tránh chỉ kiểm tra chuỗi literal trong một log mẫu.

## 14. Quản lý dữ liệu test và tính độc lập

Event listener thường được gọi bất đồng bộ hoặc sau commit nên có thể tiếp tục chạy sau khi test đã kết thúc nếu test không đợi. Điều này làm rò dữ liệu giữa các test và gây lỗi khó tái hiện.

Để test ổn định:

- Dùng UUID hoặc business key riêng cho mỗi test.
- Chờ listener hoàn tất trước khi test kết thúc.
- Dọn dữ liệu được tạo trong test theo đúng transaction và lifecycle.
- Không dùng một queue hoặc static counter chung nếu không reset an toàn.
- Cấu hình executor và timeout phù hợp với môi trường CI.
- Không dựa vào thứ tự chạy test.
- Với broker, dùng queue/topic hoặc consumer group riêng theo test suite khi cần cách ly.

Nếu listener dùng transaction `AFTER_COMMIT`, hãy kiểm tra test có commit transaction thật hay không. Nếu listener chạy bất đồng bộ, hãy đợi trạng thái hoàn tất bằng API phù hợp thay vì dựa vào thời gian ngủ cố định.

## 15. Kiểm thử lỗi và khả năng phục hồi

Một listener đáng tin cậy cần có hành vi rõ khi dependency lỗi hoặc tiến trình bị gián đoạn. Các kịch bản có thể bao gồm:

1. Repository ném lỗi trước khi thay đổi dữ liệu được commit.
2. Dependency ngoài timeout.
3. Listener bị dừng sau khi side effect đã xảy ra nhưng trước khi publication được đánh dấu hoàn tất.
4. Publication được resubmit sau khi ứng dụng khởi động lại.
5. Một poison event lỗi liên tục trong khi các event khác vẫn cần tiến triển.
6. Nhiều event của cùng aggregate đến đồng thời hoặc sai thứ tự.

Test cần xác nhận transaction rollback, publication incomplete, idempotency và trạng thái cuối cùng. Với side effect ngoài, dùng fake server hoặc sandbox có thể mô phỏng timeout sau khi đã nhận request; đây là tình huống quan trọng để kiểm tra idempotency key.

Không nên kiểm thử bằng cách chỉ ném exception ở đầu listener rồi kết luận mọi crash window đều được xử lý. Cần mô phỏng các điểm thất bại khác nhau giữa lúc nhận event, thay đổi dữ liệu, gọi hệ thống ngoài và ghi nhận hoàn tất.

## 16. Ví dụ một bộ test theo lớp

Với listener `InventoryOnOrderCompleted`, có thể tổ chức test suite như sau:

| Test | Cấp độ | Assertion chính |
| --- | --- | --- |
| `confirmsInventoryForCompletedOrder` | Unit | Service nhận đúng order ID |
| `updatesReservationWhenEventIsPublished` | Spring integration | Event dispatch tới listener và reservation chuyển trạng thái |
| `handlesOrderCompletedWithinInventoryModule` | Module test | Module kho nhận event trong context phù hợp |
| `waitsForListenerCompletion` | Async integration | Test đợi trạng thái cập nhật thay vì sleep |
| `doesNotHandleEventAfterSourceRollback` | Transaction integration | Rollback không kích hoạt listener sau commit |
| `doesNotReserveTwiceForDuplicateEvent` | Persistence integration | Event giao lặp không trừ/giữ hàng hai lần |
| `resubmitsIncompletePublication` | Registry integration | Publication thất bại có thể được phục hồi |
| `handlesBrokerRedelivery` | Broker integration | Consumer xử lý lặp an toàn và ack đúng lúc |

Không nhất thiết phải triển khai toàn bộ các test trong mọi module. Hãy chọn test tương ứng với cách listener thực sự chạy và mức độ rủi ro của hành động nghiệp vụ.

## 17. Những lỗi kiểm thử listener thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ gọi trực tiếp phương thức listener | Không kiểm tra Spring dispatch và annotation | Bổ sung integration test |
| Kiểm tra ngay sau `publishEvent()` với listener async | Test flaky vì listener chưa chạy xong | Await điều kiện hoặc dùng `Scenario` |
| Dùng `Thread.sleep()` cố định | Chậm và không ổn định trên CI | Awaitility hoặc test support có timeout |
| Test `AFTER_COMMIT` trong transaction luôn rollback | Listener không chạy như mong đợi | Commit transaction thật trong test |
| Chỉ verify mock được gọi | Không chứng minh dữ liệu được commit đúng | Kiểm tra repository và transaction behavior |
| Không test duplicate delivery | Side effect bị nhân đôi khi retry | Test idempotency bằng event/business key |
| Mock Event Publication Registry hoàn toàn | Bỏ qua persistence và recovery behavior | Có integration test với repository thật |
| Khởi động toàn bộ ứng dụng cho mọi listener test | Test chậm và phụ thuộc nhiều module | Dùng `@ApplicationModuleTest` khi phù hợp |
| Không chờ listener hoàn tất trước cleanup | Test khác bị ảnh hưởng bởi event chạy muộn | Đợi trạng thái cuối trước khi kết thúc |
| Chỉ test happy path | Không phát hiện lỗi retry, poison event và timeout | Bổ sung failure/recovery test theo rủi ro |

## 18. Quy trình xây dựng test cho listener

Khi bổ sung listener cho một application event, hãy thực hiện theo thứ tự:

1. Xác định loại listener, transaction phase, sync/async và side effect của nó.
2. Viết unit test cho mapping và logic nghiệp vụ với dependency giả lập.
3. Viết Spring integration test để xác nhận event được dispatch tới listener thật.
4. Dùng `@ApplicationModuleTest` để kiểm tra listener trong ranh giới module phù hợp.
5. Dùng `Scenario` hoặc cơ chế await có timeout cho luồng bất đồng bộ.
6. Kiểm thử commit, rollback và transaction riêng của listener nếu có.
7. Kiểm thử duplicate, failure, publication incomplete và resubmit với persistent registry khi yêu cầu cần phục hồi.
8. Bổ sung broker integration test cho externalization/consumer khi luồng có broker.
9. Kiểm tra log, dữ liệu nhạy cảm, quyền truy cập và tính độc lập của test.
10. Chạy test phù hợp trong CI và giữ timeout đủ ngắn để phát hiện listener bị treo.

Kiểm thử listener cần chứng minh cả hành vi nghiệp vụ và cách event được giao trong runtime. Khi kết hợp unit test, `@ApplicationModuleTest`, `Scenario`, transaction test và integration test cho registry/broker theo đúng nhu cầu, nhóm phát triển có thể phát hiện sớm lỗi dispatch, sai thời điểm commit, xử lý lặp và phục hồi thất bại mà vẫn giữ được ranh giới module rõ ràng.
