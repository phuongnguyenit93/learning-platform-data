# Expect trạng thái

Trong kiểm thử event bất đồng bộ, việc xác nhận event đã được publish chưa đủ để chứng minh listener hoàn thành nghiệp vụ. Một kiểm thử hữu ích cần chờ trạng thái mà người dùng hoặc module khác quan sát được thay đổi đến giá trị mong đợi. Spring Modulith cung cấp `Scenario` API với `andWaitForStateChange(…)` và `andExpect(…)` để mô tả kiểu kiểm thử này.

Ví dụ, use case xác nhận đơn hàng phát `OrderConfirmed`. Listener của module projection cập nhật `OrderSummary` sau commit. Test kích hoạt use case, chờ kết quả truy vấn read model thay đổi, rồi kiểm tra trạng thái cuối là `CONFIRMED`. Cách này kiểm tra được tác động bất đồng bộ ở ranh giới nghiệp vụ thay vì phụ thuộc vào thời gian chạy thread.

## 1. Phân biệt event arrival và state expectation

Một luồng event có nhiều mốc:

1. Use case gọi `ApplicationEventPublisher.publishEvent(…)`.
2. Transaction nguồn commit.
3. Listener transaction-bound được kích hoạt.
4. Listener thực hiện cập nhật nghiệp vụ hoặc read model.
5. Transaction của listener commit.
6. Trạng thái mới có thể được truy vấn từ repository hoặc query service.

Hai kiểu expectation kiểm tra các mốc khác nhau:

| Cách kiểm tra | Điều được xác nhận | Không tự chứng minh |
| --- | --- | --- |
| `andWaitForEventOfType(…).toArrive()` | Event thuộc kiểu mong đợi đã được phát trong scenario. | Listener đã xử lý thành công hoặc trạng thái nghiệp vụ đã đổi. |
| `andWaitForStateChange(…).andExpect(…)` | Kết quả quan sát được đã thay đổi và thỏa assertion. | Chỉ event đang kiểm thử là nguyên nhân duy nhất nếu có luồng khác cùng cập nhật trạng thái. |

Nếu mục tiêu là xác nhận hợp đồng publish, chờ event đến. Nếu mục tiêu là xác nhận listener cập nhật dữ liệu, chờ state change. Với luồng quan trọng, có thể kết hợp cả hai: event đúng được phát và trạng thái cuối cùng phản ánh đúng tác động.

## 2. Scenario API trong Spring Modulith

`@ApplicationModuleTest` khởi động phạm vi module để kiểm thử hành vi của module và các tương tác được cấu hình. Tham số `Scenario` được Spring Modulith cung cấp trong test để kích hoạt hành động, chờ event hoặc chờ trạng thái.

Một ví dụ đơn giản:

```java
@ApplicationModuleTest
class OrderProjectionScenarioTests {

    @Autowired ConfirmOrderService confirmOrder;
    @Autowired OrderSummaryRepository summaries;

    @Test
    void projectsConfirmedOrder(Scenario scenario) {
        UUID orderId = createPendingOrder();

        scenario.stimulate(() -> confirmOrder.confirm(orderId))
                .andWaitForStateChange(() -> summaries.findById(orderId))
                .andExpect(actual -> {
                    assertThat(actual).isPresent();
                    assertThat(actual.orElseThrow().status())
                            .isEqualTo(OrderStatus.CONFIRMED);
                });
    }
}
```

Trong ví dụ, `stimulate(…)` gọi use case như một hành động kích hoạt. `andWaitForStateChange(…)` nhận một `Supplier` để đọc trạng thái cần quan sát. Khi kết quả đọc thay đổi, `andExpect(…)` kiểm tra giá trị thu được. `OrderSummaryRepository`, `ConfirmOrderService` và `createPendingOrder()` là thành phần minh họa do ứng dụng cung cấp.

Scenario API có cơ chế chờ với giới hạn thời gian. Có thể cấu hình thời gian chờ tối đa bằng API được cung cấp trong phiên bản Spring Modulith đang dùng, ví dụ `andWaitAtMost(Duration.ofSeconds(5))` trên state expectation nếu phiên bản hỗ trợ. Hãy dùng đúng package và method của dependency dự án; không tự thay bằng vòng lặp hoặc `Thread.sleep()`.

## 3. Điều kiện ban đầu phải khác trạng thái đích

`andWaitForStateChange(…)` cần quan sát được sự thay đổi từ trạng thái ban đầu. Vì vậy, dữ liệu fixture nên tạo một trạng thái ban đầu rõ ràng.

Ví dụ:

| Thời điểm | Trạng thái `OrderSummary` |
| --- | --- |
| Trước khi kích hoạt | `PENDING` |
| Sau khi listener xử lý | `CONFIRMED` |

Nếu fixture đã ở `CONFIRMED` trước khi gọi use case, test không chứng minh được listener đã cập nhật trạng thái. Tương tự, nếu supplier luôn trả về một giá trị không thay đổi hoặc không phản ánh dữ liệu mới từ database, Scenario không thể quan sát đúng chuyển đổi.

Nên chuẩn bị fixture có ID riêng cho từng test, xác nhận trạng thái ban đầu trước khi kích hoạt, sau đó mới gọi scenario. Điều này giúp tránh dữ liệu còn lại từ test trước hoặc một listener khác vô tình làm assertion thành công.

## 4. Supplier phải đọc trạng thái mới

Supplier truyền vào `andWaitForStateChange(…)` được gọi để lấy trạng thái quan sát. Supplier nên thực hiện một truy vấn mới và trả về giá trị dễ so sánh, chẳng hạn `Optional<OrderSummary>`, record snapshot hoặc enum trạng thái.

Không nên trả về một entity mutable đang được giữ trong persistence context rồi mong test nhìn thấy thay đổi từ transaction khác. Entity có thể là cùng một object reference hoặc bị cache trong first-level cache. Hãy đọc qua repository/query service với transaction đọc mới và trả về DTO bất biến nếu cần.

Ví dụ một query method:

```java
public Optional<OrderSummarySnapshot> findSnapshot(UUID orderId) {
    return summaries.findById(orderId)
            .map(summary -> new OrderSummarySnapshot(
                    summary.getId(),
                    summary.getStatus(),
                    summary.getVersion()
            ));
}

public record OrderSummarySnapshot(
        UUID orderId,
        OrderStatus status,
        long version
) {}
```

Snapshot bất biến giúp phép so sánh nhận ra `PENDING` đã chuyển thành `CONFIRMED` hoặc version đã tăng. Nếu dùng một `Supplier<Boolean>`, hãy chắc rằng giá trị ban đầu và giá trị sau xử lý thực sự khác nhau; snapshot đầy đủ thường dễ chẩn đoán hơn một boolean chung.

## 5. Kiểm tra đúng trạng thái nghiệp vụ, không chỉ sự tồn tại

Assertion nên mô tả điều kiện nghiệp vụ mà listener phải tạo ra. Chỉ kiểm tra bản ghi tồn tại thường quá yếu: record có thể đã tồn tại từ trước, được tạo với trạng thái sai hoặc thiếu dữ liệu quan trọng.

Ví dụ kiểm tra nhiều trường:

```java
scenario.stimulate(() -> confirmOrder.confirm(orderId))
        .andWaitForStateChange(() -> summaries.findById(orderId))
        .andExpect(actual -> {
            OrderSummary summary = actual.orElseThrow();

            assertThat(summary.getStatus())
                    .isEqualTo(OrderStatus.CONFIRMED);
            assertThat(summary.getOrderId()).isEqualTo(orderId);
            assertThat(summary.getTotalAmount())
                    .isEqualByComparingTo("125.00");
            assertThat(summary.getVersion()).isPositive();
        });
```

Các assertion cần bám vào hợp đồng read model. Không kiểm tra mọi cột kỹ thuật nếu chúng không liên quan đến hành vi. Nếu listener chỉ có trách nhiệm cập nhật trạng thái, không nên buộc test phụ thuộc vào timestamp nội bộ hoặc thứ tự gọi repository.

## 6. Kết hợp event expectation và state expectation

Event expectation và state expectation trả lời hai câu hỏi khác nhau. Có thể tách chúng thành hai test tập trung để phân biệt lỗi publisher với lỗi listener, hoặc kết hợp trong một scenario chain nếu phiên bản Scenario API đang dùng hỗ trợ và vẫn chỉ kích hoạt use case một lần.

Test kiểm tra event arrival:

```java
@ApplicationModuleTest
class OrderEventPublicationTests {

    @Autowired ConfirmOrderService confirmOrder;

    @Test
    void publishesOrderConfirmed(Scenario scenario) {
        UUID orderId = createPendingOrder();

        scenario.stimulate(() -> confirmOrder.confirm(orderId))
                .andWaitForEventOfType(OrderConfirmed.class)
                .toArrive();
    }
}
```

Test kiểm tra trạng thái projection sau cùng một hành vi nghiệp vụ, trong một test riêng:

```java
@ApplicationModuleTest
class OrderProjectionStateTests {

    @Autowired ConfirmOrderService confirmOrder;
    @Autowired OrderSummaryRepository summaries;

    @Test
    void projectsConfirmedOrder(Scenario scenario) {
        UUID orderId = createPendingOrder();

        scenario.stimulate(() -> confirmOrder.confirm(orderId))
                .andWaitForStateChange(() -> summaries.findById(orderId))
                .andExpect(actual -> assertThat(actual)
                        .hasValueSatisfying(summary ->
                                assertThat(summary.getStatus())
                                        .isEqualTo(OrderStatus.CONFIRMED)));
    }
}
```

Hai test dùng fixture độc lập và mỗi test chỉ kích hoạt command một lần. Nếu muốn xác nhận cả event lẫn trạng thái trong cùng test, hãy dùng khả năng chaining được tài liệu của đúng phiên bản cung cấp; không gọi lại command chỉ để tạo assertion thứ hai, vì command lặp có thể tạo side effect hoặc event trùng.

## 7. Kiểm thử listener chạy sau commit

`@ApplicationModuleListener` được thiết kế cho giao tiếp bất đồng bộ giữa các module và xử lý theo transaction phase sau commit. Test state expectation nên để transaction nguồn thực sự commit trước khi chờ trạng thái projection.

Một lỗi thường gặp là đặt `@Transactional` trên phương thức test. Spring Test thường rollback transaction test khi kết thúc; listener `AFTER_COMMIT` sẽ không chạy như test mong đợi. Hãy để use case mở transaction riêng và commit, hoặc điều khiển transaction tường minh bằng `TransactionTemplate`/`TestTransaction` khi cần kiểm tra commit và rollback.

Ví dụ kiểm tra rollback:

```java
@SpringBootTest
class OrderRollbackScenarioTests {

    @Autowired PlatformTransactionManager transactionManager;
    @Autowired ApplicationEventPublisher events;
    @Autowired OrderSummaryRepository summaries;

    @Test
    void doesNotProjectAnEventFromRolledBackTransaction() {
        UUID orderId = UUID.randomUUID();
        TransactionTemplate transaction =
                new TransactionTemplate(transactionManager);

        transaction.executeWithoutResult(status -> {
            events.publishEvent(new OrderConfirmed(
                    UUID.randomUUID(), orderId, 1L,
                    new BigDecimal("125.00"), Instant.now()
            ));
            status.setRollbackOnly();
        });

        assertThat(summaries.findById(orderId)).isEmpty();
    }
}
```

Test này xác nhận listener sau commit không tạo projection từ transaction rollback. Nó không khẳng định `publishEvent` chưa được gọi; event có thể đã được phát trong application context nhưng transaction-bound listener không được chạy sau rollback.

## 8. Trạng thái thay đổi chậm hoặc không thay đổi

Nếu state expectation timeout, cần điều tra theo đúng các mốc:

1. Use case có được kích hoạt và kết thúc không?
2. Publisher có phát đúng event type và payload không?
3. Transaction nguồn có commit không?
4. Listener có được đăng ký và có nhận event không?
5. Listener có ném exception hoặc rollback transaction riêng không?
6. Repository mà supplier đọc có trỏ đến đúng database và đúng aggregate không?
7. Có cache, transaction test hoặc persistence context cũ khiến kết quả đọc bị stale không?
8. Publication có đang incomplete trong Event Publication Registry không?

Timeout là tín hiệu rằng điều kiện mong đợi chưa được quan sát trong giới hạn cho phép. Không nên tăng timeout vô hạn để làm test pass. Trước hết xác định listener có bị chậm do executor, lock, database hoặc dependency hay không.

## 9. Tránh false positive khi chờ trạng thái

State expectation có thể thành công vì một luồng khác cập nhật cùng record. Để test chứng minh đúng event đang kiểm thử tạo ra thay đổi, hãy cô lập dữ liệu và kiểm tra thêm dấu hiệu liên kết:

- Dùng aggregate ID mới cho mỗi test.
- Ghi source event ID hoặc source version vào projection nếu mô hình cho phép.
- Kiểm tra version tăng từ giá trị ban đầu.
- Kết hợp event arrival với state assertion khi cần xác minh publisher.
- Không chạy test song song trên cùng fixture hoặc cùng khóa nghiệp vụ.
- Dọn dữ liệu giữa các test và không phụ thuộc vào thứ tự chạy.

Nếu projection được cập nhật từ nhiều event type, assertion cần kiểm tra event/command đã tạo ra transition phù hợp. Chỉ nhìn thấy `CONFIRMED` không chứng minh event `OrderConfirmed` được phát nếu trạng thái có thể được cập nhật bằng một đường khác.

## 10. Kiểm tra trạng thái phức tạp và nhiều bước

Một event có thể cập nhật nhiều trường hoặc kích hoạt nhiều listener. Thay vì chỉ chờ một giá trị boolean, tạo snapshot thể hiện các phần quan trọng của trạng thái:

```java
public record OrderWorkflowSnapshot(
        OrderStatus orderStatus,
        ReservationStatus reservationStatus,
        InvoiceStatus invoiceStatus,
        long orderVersion
) {}
```

Query service có thể trả về snapshot này, sau đó Scenario chờ đến khi toàn bộ điều kiện thỏa:

```java
scenario.stimulate(() -> confirmOrder.confirm(orderId))
        .andWaitForStateChange(() -> workflowQueries.findSnapshot(orderId))
        .andExpect(actual -> {
            OrderWorkflowSnapshot state = actual.orElseThrow();
            assertThat(state.orderStatus()).isEqualTo(OrderStatus.CONFIRMED);
            assertThat(state.reservationStatus())
                    .isEqualTo(ReservationStatus.RESERVED);
            assertThat(state.invoiceStatus()).isEqualTo(InvoiceStatus.CREATED);
        });
```

Chỉ dùng snapshot tổng hợp khi các trạng thái đó thực sự thuộc phạm vi kiểm thử và có thể truy vấn an toàn. Nếu Inventory và Billing là các module độc lập với thời gian xử lý khác nhau, test cần xác định thời hạn chờ và chính sách partial completion phù hợp. Không giả định mọi listener chạy theo một thứ tự cố định nếu ứng dụng không thiết kế bảo đảm đó.

## 11. Kiểm thử trạng thái âm và sự kiện không mong đợi

Một số test cần xác nhận trạng thái không thay đổi khi event không được phát, command không hợp lệ hoặc transaction rollback. Với điều kiện âm, cần xác định rõ khoảng quan sát. Việc đọc trạng thái ngay sau command không chứng minh một listener bất đồng bộ sẽ không chạy muộn hơn.

Các cách kiểm tra phù hợp:

- Với nhánh validation đồng bộ: xác nhận command ném lỗi và không có event được ghi nhận trong phạm vi test.
- Với transaction rollback: điều khiển rollback tường minh và xác nhận listener sau commit không tạo side effect.
- Với event bất đồng bộ không được mong đợi: kiểm tra publisher/recorded events và trạng thái sau một cơ chế chờ có giới hạn được hỗ trợ, không tự suy luận từ một lần đọc tức thời.
- Với trạng thái cuối: xác nhận giá trị không bị thay đổi ngoài chính sách nghiệp vụ, đồng thời cô lập fixture để tránh cập nhật từ test khác.

Không dùng một assertion “không có state change ngay lập tức” để khẳng định listener không bao giờ chạy. Kiểm thử bất đồng bộ cần một giới hạn quan sát có ý nghĩa và xác định rõ điều kiện kết thúc.

## 12. Chọn kiểu dữ liệu trả về từ Supplier

Supplier càng đơn giản và ổn định thì test càng dễ hiểu:

| Kiểu trả về | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| `Optional<DTO>` | Chờ một projection được tạo. | Ban đầu `empty`, sau đó `present`. |
| Enum trạng thái | Chờ transition như `PENDING` sang `CONFIRMED`. | Giá trị ban đầu phải khác trạng thái đích. |
| Immutable record | Chờ nhiều trường cùng thay đổi. | Tạo snapshot mới ở mỗi lần đọc. |
| Version number | Chờ projection bắt kịp source version. | Assertion cần kiểm tra version tối thiểu mong đợi. |
| Boolean | Chỉ khi điều kiện có ý nghĩa đơn giản. | Dễ mất thông tin về trạng thái ban đầu và nguyên nhân. |

Không trả về stream, entity mutable hoặc object có `equals` không phản ánh các trường nghiệp vụ cần kiểm tra. Nếu supplier ném exception khi record chưa tồn tại, hãy trả `Optional.empty()` thay vì coi “chưa có dữ liệu” là lỗi test.

## 13. Timeout, độ ổn định và hiệu năng test

Thời gian chờ nên đủ cho môi trường test nhưng vẫn ngắn để phát hiện lỗi thật. Chọn timeout dựa trên đường đi event, số listener, transaction và môi trường CI. Không đặt timeout quá thấp khiến test flaky; cũng không đặt quá dài để che giấu listener bị treo.

Các nguyên tắc:

- Dùng timeout hữu hạn và nhất quán.
- Tránh `Thread.sleep()` cố định; nó không kiểm tra điều kiện và làm test chậm.
- Giữ supplier nhẹ, chỉ truy vấn dữ liệu cần thiết.
- Không gọi dịch vụ ngoài không liên quan trong supplier.
- Dùng fixture riêng và dọn dữ liệu sau test.
- Khi timeout, log aggregate ID, event ID và trạng thái quan sát được để điều tra.
- Đảm bảo executor/listener được đóng đúng cách sau test context.

Scenario chờ state change có thể thực hiện nhiều lần đọc trong thời gian chờ. Supplier vì vậy cần an toàn khi được gọi lặp và không tạo side effect. Không dùng supplier để cập nhật dữ liệu hoặc phát event.

## 14. Event Publication Registry và state expectation

Event Publication Registry theo dõi publication đến transactional listener và trạng thái hoàn tất. Nếu listener thất bại, publication có thể còn incomplete và được phát hiện để phục hồi theo cấu hình và phiên bản Spring Modulith.

State expectation kiểm tra kết quả nghiệp vụ/read model; registry kiểm tra trạng thái giao publication. Hai lớp này bổ sung cho nhau:

- State expectation thành công cho biết dữ liệu đọc đã đạt trạng thái mong đợi.
- Publication completed cho biết listener tương ứng đã được ghi nhận hoàn tất theo registry.
- Publication incomplete giúp điều tra listener lỗi hoặc bị gián đoạn.

Không truy cập trực tiếp bảng nội bộ của registry để làm test pass. Dùng API công khai của `EventPublicationRegistry` và Scenario API được hỗ trợ. Nếu state đã đổi nhưng publication chưa hoàn tất, cần xem xét transaction commit, lỗi lúc ghi registry hoặc listener có side effect đã commit trước khi process dừng.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ chờ event arrival | Test pass dù listener không cập nhật dữ liệu. | Chờ state change và assert trạng thái cuối. |
| Fixture đã có trạng thái đích | Không chứng minh được transition. | Tạo trạng thái ban đầu khác trạng thái mong đợi. |
| Supplier trả entity mutable từ persistence context cũ | Không quan sát được cập nhật từ transaction khác. | Truy vấn mới và trả immutable snapshot. |
| Dùng `Thread.sleep()` | Test flaky và tốn thời gian. | Dùng Scenario API với timeout hữu hạn. |
| Test transaction luôn rollback | Listener `AFTER_COMMIT` không chạy. | Để use case commit hoặc điều khiển transaction rõ ràng. |
| Gọi command hai lần để chờ state | Có thể tạo side effect hoặc event trùng. | Kích hoạt một lần và chờ đúng kết quả của lần đó. |
| Chỉ assert record tồn tại | Không xác nhận dữ liệu nghiệp vụ đúng. | Assert status, version và các trường quan trọng. |
| Chia sẻ fixture giữa test chạy song song | State change của test khác tạo false positive. | Dùng ID riêng và cô lập dữ liệu. |

## 16. Checklist cho `Expect trạng thái`

- [ ] Xác định state quan sát và query service sở hữu state đó.
- [ ] Fixture có trạng thái ban đầu rõ ràng, khác trạng thái đích.
- [ ] Dùng `@ApplicationModuleTest` và inject `Scenario` cho luồng module phù hợp.
- [ ] Kích hoạt use case đúng một lần bằng `stimulate(…)` hoặc publish event có chủ đích.
- [ ] Dùng `andWaitForStateChange(…)` với supplier chỉ đọc và trả snapshot ổn định.
- [ ] Dùng `andExpect(…)` để kiểm tra trạng thái nghiệp vụ cụ thể.
- [ ] Đặt timeout hữu hạn theo API của phiên bản Spring Modulith.
- [ ] Không dùng `Thread.sleep()` hoặc supplier có side effect.
- [ ] Đảm bảo transaction nguồn commit khi kiểm thử listener sau commit.
- [ ] Phân biệt event arrival, listener completion và state change.
- [ ] Tránh false positive bằng fixture riêng, event ID và version khi cần.
- [ ] Kiểm tra Event Publication Registry riêng nếu cần xác minh publication recovery.

`Expect trạng thái` giúp kiểm thử tập trung vào kết quả mà module khác hoặc người dùng thực sự quan sát được sau khi event được xử lý. Trong Spring Modulith, `Scenario` kích hoạt hành động, `andWaitForStateChange(…)` chờ read model thay đổi và `andExpect(…)` xác nhận trạng thái cuối. Khi fixture có trạng thái ban đầu rõ ràng, supplier đọc dữ liệu mới, timeout hữu hạn và transaction sau commit được thiết lập đúng, test có thể xác nhận luồng event bất đồng bộ mà không phụ thuộc vào sleep hoặc timing ngẫu nhiên.
