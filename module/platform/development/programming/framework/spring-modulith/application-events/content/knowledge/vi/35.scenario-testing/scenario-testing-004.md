# Expect event

Trong một ứng dụng Spring Modulith, một thao tác nghiệp vụ có thể phát application event và kích hoạt listener đồng bộ hoặc bất đồng bộ ở các module khác. Khi kiểm thử luồng này, chỉ gọi service rồi kiểm tra một repository ngay lập tức thường không đủ: listener có thể chưa chạy xong, event có thể chỉ được phát sau khi transaction commit, hoặc một event khác mới là tín hiệu cho biết quy trình đã hoàn tất.

Spring Modulith cung cấp API Scenario để mô tả một stimulus và kỳ vọng kết quả. Với kỳ vọng event, test kích hoạt hệ thống bằng cách publish một event hoặc gọi một component, chờ event thuộc kiểu mong đợi xuất hiện, lọc đúng event cần kiểm tra rồi xác minh payload. API này giúp kiểm thử event-driven integration mà không phải tự quản lý latch, polling hoặc sleep.

Bài này tập trung vào cách dùng Expect event trong Scenario: chọn stimulus, chờ event, matching, xác minh nội dung, kiểm tra event không được phát, quản lý timeout và cleanup, đồng thời hiểu rõ điều gì đã được chứng minh và điều gì vẫn cần test riêng.

## 1. Expect event là gì?

Expect event là một kỳ vọng rằng sau khi test kích hoạt một hành động, ứng dụng sẽ publish một application event thỏa điều kiện đã khai báo.

Một Scenario có bốn phần:

1. **Stimulus:** hành động bắt đầu, ví dụ publish OrderPlaced hoặc gọi OrderManagement.placeOrder.
2. **Execution customization:** tùy chọn cấu hình thời gian chờ hoặc hành vi thực thi.
3. **Expected outcome:** event type cần xuất hiện và predicate để chọn event phù hợp.
4. **Verification:** assertion trên event nhận được hoặc kết quả của stimulus.

Luồng khái quát:

~~~text
Test
  |
  | stimulus: gọi service hoặc publish event
  v
Application module
  |
  | commit transaction
  v
Transactional event listeners
  |
  | publish event kết quả
  v
Scenario quan sát event
  |
  | matching predicate đúng
  v
Assertion trên event
~~~

Scenario đợi event xuất hiện đến khi predicate khớp hoặc timeout. Vì vậy test có thể phối hợp với listener bất đồng bộ mà không cần đoán thời điểm listener hoàn tất.

Expect event kiểm tra việc application event được publish trong Spring ApplicationContext. Nó không tự chứng minh một message đã được broker xác nhận hoặc consumer bên ngoài đã xử lý thành công.

## 2. Chuẩn bị test với Spring Modulith

Để dùng Scenario trong module integration test, thêm Spring Modulith test starter ở test scope và đặt test class trong package của module hoặc package con.

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nên quản lý phiên bản dependency qua Spring Modulith BOM hoặc cơ chế version management của dự án để các artifact tương thích với nhau.

Test class dùng @ApplicationModuleTest:

~~~java
package example.order;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderScenarioTests {
    // Scenario test cases
}
~~~

Scenario được Spring Modulith cung cấp như một tham số của JUnit test method:

~~~java
@Test
void publishesOrderPlaced(Scenario scenario) {
    // Khai báo stimulus và event expectation
}
~~~

Đặt test trong đúng package module để bootstrap scope phản ánh ranh giới cần kiểm tra. Nếu module cần bean từ module phụ thuộc, chọn bootstrap mode phù hợp hoặc thay thế dependency ngoài module bằng test double khi mục tiêu chỉ là kiểm thử module hiện tại.

Tên package, dependency và bootstrap mode trong ví dụ cần điều chỉnh theo cấu trúc ứng dụng thực tế.

## 3. Chọn stimulus phù hợp

Scenario hỗ trợ hai cách bắt đầu phổ biến: publish application event trực tiếp hoặc kích hoạt một component của module.

### 3.1. Publish event trực tiếp

Dùng scenario.publish khi mục tiêu là kiểm tra listener phản ứng với một event đầu vào:

~~~java
scenario.publish(new OrderPlaced(
        eventId,
        orderId,
        customerId
))
.andWaitForEventOfType(InventoryReserved.class)
.matching(event -> event.orderId().equals(orderId))
.toArriveAndVerify(event -> {
    assertThat(event.orderId()).isEqualTo(orderId);
});
~~~

Cách này phù hợp khi test muốn tập trung vào phần xử lý phía sau event: listener, process manager hoặc module nhận event.

### 3.2. Gọi component bằng stimulate

Dùng scenario.stimulate khi muốn kiểm tra đường đi từ application service tới event được publish:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
.andWaitForEventOfType(OrderPlaced.class)
.matching(event -> event.orderId().equals(expectedOrderId))
.toArriveAndVerify(event -> {
    assertThat(event.customerId()).isEqualTo(command.customerId());
});
~~~

Stimulus có thể là Runnable hoặc Supplier. Dùng Supplier khi cần giữ kết quả trả về của lời gọi để xác minh cùng event:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
.andWaitForEventOfType(OrderPlaced.class)
.matching(event -> event.orderId().equals(expectedOrderId))
.toArriveAndVerify((event, orderId) -> {
    assertThat(event.orderId()).isEqualTo(orderId);
});
~~~

Trong ví dụ này, callback nhận event được tìm thấy và giá trị trả về từ stimulus. Đây là cách hữu ích để chứng minh event chứa đúng định danh mà service vừa tạo.

### 3.3. Nên chọn cách nào?

| Mục tiêu test | Stimulus phù hợp |
|---|---|
| Kiểm tra service phát event sau thao tác nghiệp vụ | stimulate |
| Kiểm tra listener phản ứng với event đầu vào | publish |
| Kiểm tra event kết quả chứa đúng dữ liệu từ service | stimulate với Supplier |
| Kiểm tra chuỗi event bắt đầu từ một application event | publish |
| Kiểm tra một component công khai của module | stimulate |

Không dùng publish trực tiếp để thay thế test publisher nếu mục tiêu là chứng minh application service thực sự phát event. Ngược lại, không cần gọi toàn bộ use case phức tạp nếu test chỉ cần cô lập hành vi của listener.

## 4. Chờ event theo type

Phương thức andWaitForEventOfType khai báo kiểu event cần chờ:

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForEventOfType(InventoryReserved.class)
    .toArrive();
~~~

Scenario chỉ hoàn tất khi event thuộc kiểu yêu cầu được quan sát thấy hoặc thời gian chờ kết thúc. Nếu không cần kiểm tra payload trong test này, toArrive là terminal operation đơn giản.

Kỳ vọng theo type phù hợp khi chỉ có một event thuộc loại đó trong phạm vi stimulus. Trong hệ thống có nhiều đơn hàng hoặc nhiều test chạy song song, nên kết hợp predicate để tránh bắt nhầm event của luồng khác.

Tên event type nên là class event thực sự được publish trong application context. Nếu listener phát một integration DTO tới broker nhưng không publish application event tương ứng, Scenario không thể tự động xem message broker là application event.

## 5. Lọc event bằng matching

Một event type có thể được publish nhiều lần. matching nhận Predicate để chỉ chọn event thỏa điều kiện.

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForEventOfType(InventoryReserved.class)
    .matching(event ->
            event.orderId().equals(orderId)
            && event.reservationId() != null
    )
    .toArriveAndVerify(event -> {
        assertThat(event.reservationId()).isNotNull();
    });
~~~

Predicate nên dùng định danh ổn định như orderId, aggregateId, eventId hoặc correlationId. Tránh lọc chỉ theo timestamp hoặc một field có thể trùng giữa nhiều test.

matching không thay thế assertion cuối cùng. Predicate trả lời câu hỏi event nào được xem là kết quả cần chờ; toArriveAndVerify kiểm tra nội dung event sau khi đã tìm thấy event phù hợp.

Một cách chia trách nhiệm rõ ràng:

- matching: chọn đúng event.
- toArriveAndVerify: kiểm tra payload và invariant.
- timeout: giới hạn thời gian chờ.
- cleanup: dọn dữ liệu do stimulus tạo ra.

Nếu predicate quá rộng, Scenario có thể kết thúc bởi một event không thuộc test. Nếu predicate quá hẹp, event hợp lệ có thể đã được phát nhưng không bao giờ được chọn và test sẽ timeout.

## 6. Xác minh event nhận được

toArriveAndVerify nhận Consumer của event. Đây là nơi đặt assertion về dữ liệu và quy tắc nghiệp vụ.

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
    .andWaitForEventOfType(OrderPlaced.class)
    .matching(event -> event.orderId().equals(expectedOrderId))
    .toArriveAndVerify(event -> {
        assertThat(event.orderId()).isEqualTo(expectedOrderId);
        assertThat(event.customerId()).isEqualTo(command.customerId());
        assertThat(event.lines()).hasSize(2);
        assertThat(event.total()).isEqualByComparingTo("125.00");
    });
~~~

Nếu stimulus trả về một giá trị, overload BiConsumer cho phép assertion đồng thời trên event và kết quả đó:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
    .andWaitForEventOfType(OrderPlaced.class)
    .matching(event -> event.orderId().equals(expectedOrderId))
    .toArriveAndVerify((event, result) -> {
        assertThat(event.orderId()).isEqualTo(result);
    });
~~~

Nếu chỉ cần xác nhận event xuất hiện, dùng toArrive. Nếu cần assertion sâu hơn, dùng toArriveAndVerify hoặc các biến thể toArriveAndAssert khi muốn dùng assertion API của PublishedEventsAssert.

Không nhồi logic nghiệp vụ vào predicate. Predicate nên dễ đọc, ổn định và chỉ đủ để chọn đúng event; các assertion chi tiết nên nằm trong callback verification.

## 7. Đặt timeout cho kỳ vọng event

Listener bất đồng bộ có thể hoàn tất sau một khoảng thời gian. Scenario chờ theo timeout mặc định hoặc timeout được tùy chỉnh.

Có thể cấu hình riêng cho một test:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
    .customize(conditionFactory ->
            conditionFactory.atMost(Duration.ofSeconds(3)))
    .andWaitForEventOfType(OrderPlaced.class)
    .matching(event -> event.orderId().equals(expectedOrderId))
    .toArriveAndVerify(event -> {
        assertThat(event.orderId()).isEqualTo(expectedOrderId);
    });
~~~

Timeout cần đủ cho xử lý bất đồng bộ bình thường trong môi trường test, nhưng vẫn phải hữu hạn để test lỗi trả kết quả trong thời gian có thể chẩn đoán.

Không tăng timeout quá lớn để che listener bị treo hoặc executor bị nghẽn. Khi test timeout, hãy xem log của publisher/listener, exception, transaction và trạng thái publication registry trước khi nới thời gian chờ.

Nếu nhiều test dùng cùng một timeout mặc định, có thể đăng ký ScenarioCustomizer để chuẩn hóa điều kiện chờ cho test class. Chỉ thay đổi global timeout khi có lý do chung; các luồng đặc biệt nên đặt timeout tại test tương ứng.

## 8. Expect event không được phát

Một số quy tắc nghiệp vụ yêu cầu một event không được xuất hiện. Ví dụ đơn hàng bị từ chối vì không đủ tồn kho thì không được phát PaymentRequested.

Có thể dùng notToArrive:

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitAtMost(Duration.ofMillis(500))
    .forEventOfType(PaymentRequested.class)
    .matching(event -> event.orderId().equals(orderId))
    .notToArrive();
~~~

Vì không thể chứng minh sự vắng mặt ngay lập tức, Scenario phải chờ hết khoảng thời gian đã đặt. Nếu event phù hợp xuất hiện trong thời gian đó, test thất bại ngay.

Dùng notToArrive cho các quy tắc phủ định có ý nghĩa rõ ràng. Không lạm dụng nó cho mọi event phụ vì mỗi test sẽ phải chờ hết timeout. Nếu trạng thái cuối có thể quan sát trực tiếp và phản ánh invariant tốt hơn, hãy dùng andWaitForStateChange.

Ví dụ, khi payment bị từ chối, có thể xác minh PaymentRequested không xuất hiện và order state chuyển sang PAYMENT_REJECTED. Hai assertion kiểm tra hai khía cạnh khác nhau; chọn theo yêu cầu của test.

## 9. Khi cần chờ state change thay vì event

Không phải mọi listener đều phát event kết quả. Có listener chỉ cập nhật projection hoặc trạng thái nội bộ. Khi đó, Scenario có thể chờ một state change bằng cách gọi một component đọc trạng thái.

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForStateChange(() -> inventory.findReservation(orderId))
    .andVerify(reservation -> {
        assertThat(reservation).isPresent();
        assertThat(reservation.get().orderId()).isEqualTo(orderId);
    });
~~~

Mặc định, Scenario xem giá trị khác null, Optional có giá trị hoặc boolean true là tín hiệu state change. Nếu trạng thái cần điều kiện cụ thể hơn, dùng overload nhận Predicate:

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForStateChange(
            () -> orderQueries.findStatus(orderId),
            status -> status.filter(value -> value == OrderStatus.CONFIRMED)
                            .isPresent()
    )
    .andVerify(status -> {
        assertThat(status).contains(OrderStatus.CONFIRMED);
    });
~~~

Dùng state change khi trạng thái đọc là hợp đồng quan trọng của module. Dùng expect event khi chính event được phát là kết quả cần kiểm chứng hoặc là hợp đồng giao tiếp giữa các module.

## 10. Transaction boundary và AFTER_COMMIT

Một điểm quan trọng của Scenario là stimulus được thực thi trong transaction callback để bảo đảm event được publish và transactional event listener có cơ hội chạy theo pha commit. Scenario mở transaction mới cho stimulus, kể cả khi test method đang có transaction.

Điều này có nghĩa dữ liệu được ghi bởi stimulus không tự động rollback cùng transaction test method. Cần dọn dữ liệu sau mỗi scenario bằng cleanup callback hoặc cơ chế test fixture phù hợp.

Ví dụ:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
    .andCleanup(orderId -> orderRepository.deleteById(orderId))
    .andWaitForEventOfType(OrderPlaced.class)
    .matching(event -> event.orderId().equals(expectedOrderId))
    .toArrive();
~~~

andCleanup được gọi khi scenario kết thúc, kể cả khi expectation thành công hay thất bại. Nếu stimulus trả về ID, overload Consumer cho phép dùng ID đó để xóa dữ liệu. Nếu không cần kết quả stimulus, dùng Runnable cleanup.

Cleanup phải xử lý đúng thứ tự phụ thuộc dữ liệu và tránh xóa dữ liệu dùng chung giữa các test. Với side effect ngoài database như message broker hoặc dịch vụ giả lập, cần dọn queue, mock server hoặc test resource riêng theo vòng đời test.

Không giả định @Transactional trên test method sẽ rollback mọi thay đổi do Scenario tạo ra. Hãy đọc rõ transaction boundary và chủ động dọn fixture.

## 11. Kiểm thử event chain giữa các module

Một event có thể kích hoạt listener ở module khác, rồi listener phát event tiếp theo. Scenario phù hợp để xác minh một kết quả ở cuối chuỗi.

Ví dụ:

~~~java
scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForEventOfType(InventoryReserved.class)
    .matching(event -> event.orderId().equals(orderId))
    .toArriveAndVerify(event -> {
        assertThat(event.reservationId()).isNotNull();
    });
~~~

Test trên chứng minh event đầu vào đã dẫn tới event InventoryReserved được publish. Nếu muốn xác minh module Payment cũng phát PaymentRequested, có thể viết scenario riêng với stimulus và expectation phù hợp hoặc dùng PublishedEvents assertion để kiểm tra tập event được ghi nhận.

Một Scenario expectation đơn lẻ không tự chứng minh toàn bộ chuỗi event đã hoàn tất. Event InventoryReserved có thể được publish trước khi listener tiếp theo xử lý xong. Nếu kết quả cần kiểm tra là trạng thái cuối, hãy chờ event cuối cùng hoặc dùng state change ở module sở hữu trạng thái đó.

Khi test nhiều module, chọn @ApplicationModuleTest bootstrap mode để đưa các module liên quan vào context. STANDALONE phù hợp với module độc lập; DIRECT_DEPENDENCIES hoặc ALL_DEPENDENCIES khi test cần module phụ thuộc thực sự. Không mở toàn ứng dụng chỉ để làm test qua được nếu điều đó che giấu coupling không mong muốn.

## 12. Event identity và tránh bắt nhầm event

Test chạy song song có thể publish cùng event type. Nếu chỉ chờ theo type, test có thể nhận event do một scenario khác tạo ra.

Dùng ID duy nhất cho mỗi test:

~~~java
UUID orderId = UUID.randomUUID();
UUID eventId = UUID.randomUUID();

scenario.publish(new OrderPlaced(eventId, orderId, customerId))
    .andWaitForEventOfType(InventoryReserved.class)
    .matching(event ->
            event.orderId().equals(orderId)
            && event.eventId() != null
    )
    .toArriveAndVerify(event -> {
        assertThat(event.orderId()).isEqualTo(orderId);
    });
~~~

Nếu event contract có correlationId, có thể dùng correlationId để lọc toàn bộ event thuộc cùng luồng. Event ID định danh một event; correlation ID liên kết nhiều event trong một workflow. Không dùng timestamp làm định danh duy nhất.

Không dùng static mutable state để chia sẻ ID hoặc kết quả giữa test method. Dữ liệu test cần độc lập để chạy song song và dễ tái hiện khi thất bại.

## 13. Expect event và kiểm tra nhiều event

Scenario tập trung vào một expected outcome làm điều kiện hoàn tất. Khi cần kiểm tra nhiều event được publish trong cùng một stimulus, có thể kết hợp với API assertion của PublishedEvents mà Spring Modulith cung cấp cho test.

Ví dụ khái niệm:

~~~java
scenario.stimulate(() -> orderManagement.placeOrder(command))
    .andWaitForEventOfType(OrderPlaced.class)
    .matching(event -> event.orderId().equals(orderId))
    .toArriveAndAssert(publishedEvent -> {
        // Kiểm tra các thuộc tính của event được ghi nhận
    });
~~~

toArriveAndAssert cho phép dùng PublishedEventsAssert để xác minh event đã được publish. Với yêu cầu kiểm tra nhiều loại event, số lượng hoặc quan hệ giữa các event, hãy dùng assertion API phù hợp và lọc theo định danh của scenario.

Không suy ra thứ tự toàn cục chỉ từ việc nhiều event cùng xuất hiện. Nếu thứ tự là hợp đồng nghiệp vụ, hãy kiểm tra sequence/version hoặc trạng thái chuyển tiếp cụ thể.

## 14. Phân biệt application event với broker message

Scenario theo dõi application events trong Spring ApplicationContext. Nó phù hợp để kiểm thử publisher/listener nội bộ và các module giao tiếp qua application events.

Nếu adapter chuyển event thành RabbitMQ, Kafka hoặc message broker khác, expect event trong Scenario không chứng minh:

- Broker đã nhận message.
- Publisher confirm đã thành công.
- Routing key đưa message tới đúng queue/partition.
- Consumer bên ngoài đã xử lý và acknowledgement.
- Side effect của service khác đã commit.

Các hành vi đó cần integration test cho adapter và broker, hoặc test contract với consumer. Có thể kiểm thử riêng mapper từ application event sang integration message, sau đó dùng broker test để xác minh headers, routing, acknowledgement và redelivery.

Giữ ranh giới này giúp test có kết luận chính xác: Scenario xác minh application event; broker integration test xác minh giao message qua transport.

## 15. Lỗi thường gặp khi dùng Expect event

**Chỉ chờ theo event type.** Nhiều test có thể phát cùng type. Thêm matching predicate theo orderId, eventId hoặc correlationId.

**Predicate kiểm tra quá nhiều logic.** Test khó đọc và event hợp lệ có thể không khớp. Dùng predicate để chọn event, callback để assert payload.

**Không cấu hình timeout.** Test có thể chờ lâu hoặc phụ thuộc default không phù hợp. Đặt timeout hữu hạn theo thời gian xử lý hợp lý.

**Dùng sleep để chờ listener.** Sleep không chứng minh điều kiện đã xảy ra và khiến test chậm. Dùng Scenario expectation.

**Quên transaction commit.** Transactional listener không chạy nếu stimulus không đi qua transaction commit như kỳ vọng. Dùng Scenario stimulus để kiểm tra đúng boundary.

**Cho rằng dữ liệu sẽ rollback theo test.** Scenario mở transaction riêng cho stimulus. Dùng andCleanup hoặc fixture cleanup.

**Dùng expect event để chứng minh side effect đã hoàn tất.** Event kết quả có thể được publish trước khi listener downstream kết thúc. Chờ event cuối hoặc state change cần thiết.

**Không tách application event và broker message.** Scenario không xác minh publisher confirm hay consumer acknowledgement của broker. Viết broker integration test riêng.

**Dùng notToArrive với timeout dài.** Test phủ định phải chờ hết khoảng thời gian. Chỉ dùng khi sự vắng mặt là hợp đồng cần xác minh.

**Không cô lập dữ liệu test.** Event của test khác có thể thỏa predicate. Dùng ID riêng và cleanup độc lập.

## 16. Checklist thiết kế Expect event test

Trước khi hoàn tất một test, xác minh các câu hỏi sau:

1. Stimulus là publish event trực tiếp hay gọi component công khai?
2. Test đang kiểm tra publisher, listener hay chuỗi event giữa module?
3. Event type được chờ có phải kết quả đúng của stimulus không?
4. Predicate có lọc theo ID duy nhất để tránh bắt nhầm event không?
5. Assertion kiểm tra các trường và invariant quan trọng chưa?
6. Timeout có hữu hạn và phù hợp với xử lý bất đồng bộ không?
7. Transaction của stimulus có commit để transactional listener chạy không?
8. Dữ liệu được tạo trong transaction riêng có được cleanup không?
9. Nếu cần xác minh trạng thái cuối, state change có phù hợp hơn event trung gian không?
10. Nếu event đi qua broker, có integration test transport riêng chưa?

Một test tốt có thể đọc như một câu: kích hoạt hành động, chờ event có định danh đúng, rồi xác minh dữ liệu được công bố. Khi dùng Scenario đúng mục đích, test event-driven của Spring Modulith trở nên xác định hơn, ít phụ thuộc thời gian và tập trung vào hợp đồng giữa các module.

## 17. Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith — Scenario API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.html)
- [Spring Modulith — Scenario.When API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.When.html)
- [Spring Modulith — Scenario.When.EventResult API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.When.EventResult.html)

Các API có thể thay đổi theo phiên bản Spring Modulith. Hãy dùng BOM và tài liệu tương ứng với phiên bản đang được dự án quản lý.
