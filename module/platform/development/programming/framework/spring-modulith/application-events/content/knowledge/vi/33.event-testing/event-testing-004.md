# Kiểm thử nhiều listener

## Vì sao phải kiểm thử nhiều listener cùng nhận một event?

Trong Spring Modulith, một application event có thể được nhiều listener đăng ký nhận. Ví dụ, khi Orders phát OrderConfirmed, các listener độc lập có thể cập nhật read model, tạo yêu cầu giao hàng, ghi nhận thông tin cho Billing và tạo thông báo cho khách hàng.

Một lần gọi publishEvent chỉ chứng minh ứng dụng đã công bố event. Nó không chứng minh mọi listener đã được gọi, mọi side effect đã commit hoặc mọi publication đã hoàn tất. Điều này đặc biệt quan trọng khi listener chạy bất đồng bộ hoặc sau transaction commit.

Kiểm thử nhiều listener cần xác nhận ba lớp hành vi:

1. Event được phát đúng một lần với dữ liệu và định danh mong đợi.
2. Từng listener phù hợp nhận event và thực hiện đúng trách nhiệm của nó.
3. Lỗi, retry, thứ tự và transaction của một listener không làm sai kết quả của listener khác theo semantics đã thiết kế.

~~~mermaid
flowchart TD
    P[Orders publishes OrderConfirmed] --> R[Event dispatch]
    R --> L1[Order summary listener]
    R --> L2[Fulfillment listener]
    R --> L3[Billing listener]
    R --> L4[Notification listener]
    L1 --> D1[(Read model)]
    L2 --> D2[(Shipment request)]
    L3 --> D3[(Billing record)]
    L4 --> D4[(Notification outbox)]
    D1 --> V[Assertions per listener]
    D2 --> V
    D3 --> V
    D4 --> V
~~~

Mỗi listener có thể có transaction, thời gian xử lý và chính sách lỗi riêng. Vì vậy, test nên quan sát kết quả của từng nhánh thay vì chỉ kiểm tra tổng số event đã phát.

## Phân biệt publish, dispatch và listener completion

Các mốc sau không đồng nghĩa:

| Mốc | Điều đã được xác nhận |
|---|---|
| Event published | Publisher đã gửi event vào cơ chế application event |
| Listener invoked | Một listener đã bắt đầu được gọi |
| Listener completed | Logic listener đã kết thúc |
| Listener transaction committed | Thay đổi dữ liệu của listener đã commit |
| Publication completed | Registry ghi nhận publication của listener hoàn tất theo implementation |
| Downstream action completed | Hệ thống bên ngoài đã thực hiện tác động tiếp theo nếu có |

Với listener đồng bộ, lời gọi publish thường diễn ra trong cùng luồng và có thể chờ listener kết thúc. Với listener bất đồng bộ, publish có thể trả về trước khi listener bắt đầu hoặc hoàn tất.

Nếu listener dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT), nó chỉ được xử lý sau khi transaction phát event commit thành công. Nếu transaction rollback, listener không được gọi theo phase đó.

@ApplicationModuleListener của Spring Modulith là lựa chọn tiện dụng cho listener chạy bất đồng bộ sau commit và trong transaction riêng theo semantics của framework. Khi dùng annotation này, test phải đợi side effect commit trước khi assert.

Không dùng việc publishEvent trả về làm điều kiện duy nhất để kết luận tất cả listener đã hoàn tất.

## Hiểu cách nhiều listener được thực thi

Một event có thể được nhiều listener cùng nhận, nhưng cách thực thi phụ thuộc cấu hình:

- Listener đồng bộ mặc định có thể chạy lần lượt trong luồng publish.
- @Order có thể xác định thứ tự gọi của các listener đồng bộ được sắp xếp.
- Listener bất đồng bộ được dispatch qua executor và có thể chạy đồng thời.
- Với listener bất đồng bộ, thứ tự bắt đầu hoặc hoàn tất không nên được giả định nếu không có cơ chế tuần tự hóa riêng.
- Listener transactional có thể commit hoặc rollback độc lập với transaction của publisher và listener khác.

Nếu thứ tự giữa các listener là yêu cầu nghiệp vụ, hãy mô hình hóa phụ thuộc đó bằng một workflow hoặc event chain rõ ràng. Không dựa vào thứ tự tình cờ của thread scheduler.

Ví dụ, nếu Notification chỉ được gửi sau khi Fulfillment tạo shipment thành công, có thể để Fulfillment phát ShipmentPrepared rồi Notification lắng nghe event mới. Cách này thể hiện quan hệ nhân quả rõ hơn việc mong hai listener cùng nhận OrderConfirmed rồi tự chạy đúng thứ tự.

## Chọn phạm vi kiểm thử

Không cần dùng một loại test để xác minh mọi hành vi. Chia theo trách nhiệm giúp test nhanh, ổn định và dễ xác định nguyên nhân lỗi.

| Cấp kiểm thử | Nội dung | Điều cần xác nhận |
|---|---|---|
| Unit test listener | Gọi trực tiếp từng listener với event mẫu | Mapping và quy tắc xử lý của listener |
| Publisher test | Gọi use case phát event | Event type, payload và số lần publish |
| Module integration test | Khởi tạo module cùng listener liên quan | Wiring, component scan và ranh giới module |
| Application event scenario test | Phát event qua test support của Spring Modulith | Event được phát và event tiếp theo đến đúng listener |
| Async integration test | Chạy listener bằng executor thật của test context | Side effect cuối cùng của từng listener |
| Persistence test | Dùng database test phù hợp | Transaction, rollback, unique constraint và publication state |
| Broker integration test | Dùng broker test khi externalization nằm trong phạm vi | Adapter, routing, serialization và acknowledgement |

Unit test có thể xác minh một listener xử lý đúng event, nhưng không chứng minh Spring đã đăng ký listener vào ApplicationContext. Ngược lại, một integration test có đầy đủ context có thể kiểm tra wiring nhưng thường chậm hơn.

Hãy giữ phần lớn quy tắc mapping trong unit test và dùng một số integration test tập trung để xác nhận fan-out, transaction và async behavior.

## Kiểm tra event được publish

Trước khi kiểm tra listener, xác nhận use case phát đúng event sau khi cập nhật nghiệp vụ.

Với Spring Test, có thể dùng @RecordApplicationEvents và ApplicationEvents để ghi nhận application event trong test:

~~~java
@SpringBootTest
@RecordApplicationEvents
class OrderConfirmationTests {

    @Autowired
    OrderConfirmationService confirmationService;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderConfirmed() {
        UUID orderId = UUID.randomUUID();

        confirmationService.confirm(orderId);

        assertThat(applicationEvents.stream(OrderConfirmed.class))
            .hasSize(1);
    }
}
~~~

Đây là ví dụ minh họa; fixture và cách tạo dữ liệu cần phù hợp với test context của ứng dụng. Với event chạy sau commit, test phải bảo đảm transaction publisher thực sự commit trước khi kỳ vọng listener được gọi.

Kiểm tra thêm các thuộc tính quan trọng:

- Event ID không rỗng và ổn định.
- Aggregate ID đúng với entity được cập nhật.
- Aggregate version phản ánh trạng thái sau thay đổi.
- Event type và payload đúng hợp đồng.
- Không phát event nếu nghiệp vụ bị từ chối hoặc transaction rollback.

Chỉ kiểm tra số lượng event là chưa đủ nếu payload sai hoặc event được phát trước khi dữ liệu nghiệp vụ hợp lệ.

## Kiểm tra từng listener bằng kết quả quan sát được

Giả sử OrderConfirmed có ba listener:

- OrderSummaryProjection cập nhật bảng read model.
- ShipmentRequestListener tạo yêu cầu giao hàng.
- BillingListener tạo bản ghi cần lập hóa đơn.

Trong integration test, gọi use case thật rồi đợi từng kết quả đạt điều kiện mong đợi:

~~~java
@SpringBootTest
class OrderConfirmedFanOutTests {

    @Autowired
    OrderConfirmationService confirmationService;

    @Autowired
    OrderSummaryRepository summaries;

    @Autowired
    ShipmentRequestRepository shipments;

    @Autowired
    BillingEntryRepository billingEntries;

    @Test
    void updatesAllRegisteredReadAndBusinessModels() {
        UUID orderId = createConfirmedTestOrder();

        confirmationService.confirm(orderId);

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            assertThat(summaries.findByOrderId(orderId))
                .isPresent();

            assertThat(shipments.existsByOrderId(orderId))
                .isTrue();

            assertThat(billingEntries.existsByOrderId(orderId))
                .isTrue();
        });
    }
}
~~~

await().untilAsserted(...) là cách minh họa bằng Awaitility để chờ các listener bất đồng bộ. Test cần cấu hình timeout hợp lý và kiểm tra dữ liệu cuối cùng đã commit.

Các assertion độc lập cho biết listener nào chưa hoàn tất. Nếu chỉ đợi một listener bất kỳ hoặc chỉ kiểm tra một bảng, test có thể xanh dù các listener còn lại chưa chạy.

Ưu tiên kiểm tra kết quả nghiệp vụ hoặc trạng thái persistence thay vì chỉ verify một mock được gọi. Mock interaction hữu ích trong unit test, nhưng integration test cần xác nhận wiring và transaction thực tế.

## Dùng Scenario API của Spring Modulith

Spring Modulith cung cấp test support để kiểm tra luồng application event theo cách hướng hành vi. Với @ApplicationModuleTest, có thể inject Scenario, phát một event và chờ event tiếp theo đến.

Ví dụ:

~~~java
@ApplicationModuleTest
class OrderEventScenarioTests {

    @Autowired
    Scenario scenario;

    @Test
    void publishesFollowUpEvent() {
        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            UUID.randomUUID()
        );

        scenario.publish(event)
            .andWaitForEventOfType(ShipmentPrepared.class)
            .toArriveAndVerify(shipmentPrepared ->
                assertThat(shipmentPrepared.orderId())
                    .isEqualTo(event.orderId())
            );
    }
}
~~~

Ví dụ này kiểm tra một event tiếp theo được phát trong luồng module. Nếu có nhiều listener độc lập, cần xác nhận kết quả của từng listener bằng các assertion bổ sung hoặc bằng cách chờ từng loại event/kết quả tương ứng.

Scenario API phù hợp để kiểm tra event chain và bất đồng bộ mà không phải tự quản lý sleep. Kiểm tra side effect trong database vẫn cần repository assertion hoặc state assertion tương ứng.

Tên package, cấu hình module test và API cụ thể cần theo phiên bản Spring Modulith đang dùng.

## Kiểm tra nhiều listener cùng nhận một event

Một test fan-out tốt nên xác nhận đủ các nhánh. Có thể thiết kế fixture để mỗi listener tạo ra một kết quả có thể truy vấn bằng cùng aggregate ID hoặc event ID.

Ví dụ bảng kết quả mong đợi:

| Listener | Side effect | Assertion |
|---|---|---|
| OrderSummaryProjection | Upsert order summary | Có đúng một summary với version mong đợi |
| ShipmentRequestListener | Tạo shipment request | Có request cho order ID và trạng thái ban đầu đúng |
| BillingListener | Tạo billing entry | Có entry đúng amount và currency |
| NotificationListener | Ghi notification outbox | Có notification với recipient và template đúng |

Đối với mỗi listener, kiểm tra cả dữ liệu quan trọng và số lượng bản ghi. Một listener có thể được gọi hai lần và tạo hai bản ghi khác nhau; chỉ kiểm tra exists sẽ không phát hiện duplicate.

Nếu nhiều listener ghi vào cùng một database, có thể truy vấn các bảng trong cùng integration test. Nếu chúng ghi vào database hoặc hệ thống độc lập, dùng test fixture hoặc API quan sát phù hợp cho từng hệ thống. Không truy cập repository nội bộ của module khác chỉ để làm test thuận tiện.

## Kiểm tra transaction và after-commit

Với event được phát trong transaction, cần có hai trường hợp cơ bản:

**Transaction commit**

- Dữ liệu write model được commit.
- Listener after-commit đủ điều kiện chạy.
- Side effect của listener được commit trong transaction riêng nếu listener được cấu hình transactional.
- Publication tương ứng được ghi nhận hoàn tất khi listener kết thúc thành công theo registry implementation.

**Transaction rollback**

- Dữ liệu write model không được commit.
- Listener after-commit không được xử lý event của transaction rollback.
- Không có side effect read model hoặc downstream tương ứng với thay đổi chưa commit.

Ví dụ test rollback cần tạo transaction thật, phát event rồi chủ động rollback. Không nên chỉ mock repository ném exception, vì điều đó không chứng minh transaction event và listener phối hợp đúng.

Cần chú ý test class có @Transactional: Spring Test thường rollback transaction ở cuối test. Listener after-commit sẽ không chạy nếu transaction chưa commit. Có thể dùng test không bọc transaction hoặc chủ động commit bằng cơ chế transaction test phù hợp.

## Kiểm tra lỗi ở một listener

Nhiều listener có thể xử lý cùng event, nhưng không có một transaction nguyên tử bao trùm mọi listener và mọi side effect. Khi một listener lỗi, kết quả của listener khác phụ thuộc vào cách dispatch, executor và transaction được cấu hình.

Các trường hợp cần kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Listener A thành công, B thất bại | A giữ kết quả đã commit; B còn trạng thái có thể phục hồi theo policy |
| Listener A thất bại, B thành công | Không mặc định B bị rollback cùng A nếu chúng chạy độc lập |
| Listener đồng bộ ném exception | Xác nhận exception propagation và việc các listener tiếp theo có được gọi theo multicaster config |
| Listener bất đồng bộ ném exception | Lỗi được ghi nhận, không bị mất trong executor |
| Listener transaction rollback | Side effect của listener đó không còn sau rollback |
| Retry listener | Tác động của listener không bị nhân đôi |

Không giả định một listener lỗi sẽ luôn không ảnh hưởng đến listener khác. Với listener đồng bộ, exception có thể lan về publisher và ảnh hưởng quá trình dispatch tiếp theo. Với listener bất đồng bộ, một listener có thể chạy độc lập, nhưng executor và error handler vẫn quyết định cách lỗi được xử lý.

Nếu cần bảo đảm mọi listener đều được thử thực thi độc lập, hãy cấu hình và kiểm thử semantics đó một cách tường minh.

## Kiểm tra Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication cho các transactional listener được quản lý. Khi một event có nhiều listener thuộc phạm vi registry, mỗi listener có publication lifecycle riêng.

Vì vậy, test nên xác nhận:

- Event tạo publication cho đúng các listener cần theo dõi.
- Listener thành công được ghi nhận hoàn tất.
- Listener lỗi không bị đánh dấu hoàn tất sai.
- Publication chưa hoàn tất có thể được phục hồi theo persistence và resubmission configuration.
- Việc hoàn tất một listener không làm mất trạng thái của listener khác.

Không kiểm tra bằng cách hard-code tên bảng hoặc schema nội bộ của registry nếu không thuộc contract công khai của implementation. Ưu tiên API quản lý/quan sát được hỗ trợ ở phiên bản đang dùng hoặc kiểm tra hành vi qua listener và kết quả persistence.

Registry không phải event store vô hạn. Publication đã hoàn tất có thể được dọn theo chính sách lưu trữ; test không nên giả định mọi publication lịch sử luôn tồn tại.

## Kiểm tra retry và idempotency theo từng listener

Khi listener lỗi, publication có thể được resubmit theo cấu hình. Một listener có thể nhận lại cùng event, nên idempotency phải được kiểm tra riêng cho từng consumer.

Ví dụ:

- Projection listener dùng aggregate version để không ghi đè snapshot mới bằng event cũ.
- Shipment listener dùng event ID hoặc order ID làm idempotency key để không tạo shipment request trùng.
- Notification listener ghi outbox với unique key phù hợp để không gửi cùng thông báo hai lần.

Test nên mô phỏng:
1. Listener thất bại ở lần đầu.
2. Publication còn trạng thái chưa hoàn tất.
3. Listener được thử lại sau khi lỗi tạm thời được khắc phục.
4. Side effect cuối cùng chỉ xuất hiện một lần.
5. Listener khác đã thành công không bị chạy lại ngoài chính sách của nó.

Nếu retry toàn event dẫn đến nhiều listener được gọi lại, các listener đã thành công cũng cần idempotent. Không dựa vào giả định registry sẽ chỉ retry đúng listener lỗi nếu implementation/configuration không bảo đảm điều đó.

## Kiểm tra thứ tự và concurrency

Nhiều listener bất đồng bộ có thể hoàn tất theo thứ tự khác nhau. Test không nên assert thứ tự thời gian nếu nghiệp vụ không có hợp đồng ordering.

Nếu listener cần chạy song song, kiểm tra:
- Tất cả side effect cuối cùng đều xuất hiện.
- Không có race condition khi cùng cập nhật một aggregate hoặc một bản ghi dùng chung.
- Unique constraint và optimistic locking hoạt động.
- Không tạo deadlock hoặc vượt giới hạn connection pool dưới concurrency dự kiến.

Nếu listener cần thứ tự:
- Thể hiện dependency bằng event chain hoặc workflow.
- Dùng aggregate version/sequence để phát hiện event đến sai thứ tự.
- Tuần tự hóa theo aggregate khi cần.
- Không dựa riêng vào @Order khi listener được thực thi bất đồng bộ.

Một test concurrency nên dùng barrier/latch hoặc công cụ đồng bộ có kiểm soát để tạo tình huống cạnh tranh. Tránh dùng sleep để hy vọng hai listener chạy đồng thời.

## Kiểm tra listener có được đăng ký đúng module

Một listener có thể không được gọi vì bean không nằm trong ApplicationContext, package scan sai hoặc module dependency không cho phép truy cập thành phần cần thiết.

Test module nên xác nhận:
- Listener bean được phát hiện trong module dự kiến.
- Event type đúng với method listener.
- Module có dependency được khai báo đúng theo ranh giới.
- Không có listener trùng do component scan hoặc cấu hình bị lặp.
- Listener không phụ thuộc trực tiếp repository nội bộ của module khác.

Với Spring Modulith, @ApplicationModuleTest giúp kiểm tra module trong phạm vi phù hợp. Có thể bổ sung kiểm tra cấu trúc module bằng công cụ test của Spring Modulith để phát hiện dependency không hợp lệ.

Không chỉ assert bean tồn tại; hãy phát event và xác nhận hành vi listener để chứng minh wiring hoạt động.

## Cô lập test và tránh flakiness

Test nhiều listener dễ bị flaky nếu các listener bất đồng bộ còn chạy khi test kết thúc hoặc dữ liệu dùng chung giữa các test.

Nên:
- Dùng database/schema riêng hoặc cleanup dữ liệu theo test.
- Tạo aggregate ID và event ID riêng cho từng test.
- Chờ điều kiện cuối cùng bằng Awaitility hoặc Scenario API với timeout hữu hạn.
- Đặt timeout đủ rộng cho môi trường CI nhưng không quá dài để che giấu lỗi.
- Không dùng Thread.sleep cố định.
- Không dùng một static counter dùng chung giữa các test chạy song song.
- Dọn executor và tài nguyên test đúng vòng đời context.
- Tránh chạy nhiều test cùng ghi vào một aggregate ID cố định.

Nếu dùng @DirtiesContext, chỉ dùng khi cần thiết vì nó làm tăng thời gian test suite. Ưu tiên dữ liệu cô lập và cleanup có chủ đích.

## Kiểm thử externalized event và broker

Nếu một trong các listener là externalization adapter gửi event ra Kafka hoặc RabbitMQ, kiểm thử listener nội bộ chưa chứng minh message đã đến broker.

Tách test theo lớp:

- Test publisher và event contract.
- Test externalization mapping: target, routing key, payload và header.
- Test producer acknowledgement với broker test.
- Test consumer nhận message và thực hiện side effect.
- Test duplicate, retry và dead-letter theo cấu hình broker.

Một broker test có thể xác nhận một event được gửi đúng destination. Nếu nhiều consumer group độc lập phải nhận cùng event, test từng group hoặc subscription tương ứng; một queue cạnh tranh không chứng minh mọi consumer độc lập đều nhận được message.

Không mock toàn bộ broker trong test duy nhất rồi kết luận fan-out end-to-end đã hoạt động.

## Ma trận test đề xuất

Có thể dùng ma trận sau để tránh bỏ sót nhánh:

| Kịch bản | Listener A | Listener B | Listener C | Kết quả cần xác nhận |
|---|---|---|---|---|
| Event hợp lệ | Thành công | Thành công | Thành công | Cả ba side effect đúng |
| A lỗi tạm thời | Retry | Thành công | Thành công | B/C không bị mất; A phục hồi |
| B lỗi dữ liệu | Thành công | Quarantine/failure | Thành công | B không bị đánh dấu thành công sai |
| Publisher rollback | Không chạy | Không chạy | Không chạy | Không có side effect |
| Event được giao trùng | Deduplicate | Deduplicate | Deduplicate | Không nhân đôi tác động |
| Hai listener chạy song song | Thành công | Thành công | Không áp dụng | Không race hoặc deadlock |
| Một listener chậm | Chậm | Thành công | Thành công | Test chờ đúng điều kiện, không phụ thuộc thứ tự |

Ma trận cần được điều chỉnh theo số listener và semantics thực tế. Không phải mọi ứng dụng đều cần kiểm thử mọi tổ hợp lỗi; ưu tiên các listener có tác động nghiệp vụ quan trọng hoặc có persistence riêng.

## Quy trình viết test cho nhiều listener

Khi thêm listener mới cho một event, thực hiện theo thứ tự:

1. Liệt kê tất cả listener dự kiến nhận event và module sở hữu từng listener.
2. Ghi rõ listener đồng bộ, after-commit hay bất đồng bộ.
3. Xác định side effect và transaction của từng listener.
4. Viết unit test cho mapping và quy tắc nghiệp vụ của từng listener.
5. Viết integration test xác nhận event được publish đúng payload.
6. Chờ và kiểm tra side effect của từng listener bằng điều kiện độc lập.
7. Kiểm thử publisher rollback và listener failure.
8. Kiểm thử retry, duplicate và idempotency.
9. Kiểm tra ordering/concurrency nếu nghiệp vụ yêu cầu.
10. Nếu externalize, bổ sung broker integration test cho từng consumer group cần nhận event.

Một bộ test nhiều listener tốt chứng minh được event đã đi qua đúng ranh giới, từng listener thực hiện đúng trách nhiệm và lỗi được xử lý theo chính sách đã định. Khi test dựa trên side effect đã commit, chờ bất đồng bộ có giới hạn và không giả định thứ tự ngoài hợp đồng, bộ kiểm thử sẽ đáng tin cậy hơn khi số listener tăng lên.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith Reference — Testing Application Modules: https://docs.spring.io/spring-modulith/reference/testing.html
- Spring Framework Reference — Application Events and Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Awaitility — Usage: https://github.com/awaitility/awaitility/wiki/Usage
