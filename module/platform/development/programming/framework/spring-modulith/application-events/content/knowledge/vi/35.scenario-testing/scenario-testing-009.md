# Timeout trong scenario

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, một application event có thể kích hoạt listener đồng bộ hoặc bất đồng bộ, cập nhật trạng thái module và phát ra event tiếp theo. Khi kiểm thử luồng này bằng Spring Modulith Scenario API, test thường phải chờ một kết quả xuất hiện sau stimulus ban đầu. **Timeout trong scenario** xác định khoảng thời gian tối đa mà test chấp nhận chờ kết quả đó.

Timeout giúp test kết thúc có giới hạn khi event không đến, listener lỗi hoặc hệ thống xử lý chậm. Đặt timeout đúng giúp phân biệt lỗi chức năng với độ trễ thực tế, giảm test treo và tránh dùng `Thread.sleep` cố định. Tuy nhiên, timeout của Scenario chỉ giới hạn thời gian chờ trong test; nó không hủy listener, rollback công việc đã commit hoặc dừng một tác vụ bất đồng bộ đang chạy.

## 1. Vì sao scenario cần timeout?

Một scenario thường gồm stimulus và outcome:

1. Test phát một application event hoặc gọi một component của module.
2. Listener xử lý stimulus, có thể sau commit hoặc trên executor riêng.
3. Listener cập nhật dữ liệu hoặc phát event tiếp theo.
4. Scenario chờ kết quả và xác minh nó.

Ví dụ, test phát `OrderConfirmed` và chờ `InventoryReserved`. Nếu listener không chạy, exception xảy ra, transaction chưa commit hoặc event kết quả không được phát, test có thể chờ mãi nếu không có giới hạn.

Timeout đặt một deadline cho kỳ vọng:

- Event mong đợi phải đến trước deadline.
- Hoặc trạng thái module phải đạt điều kiện trước deadline.
- Với kiểm thử phủ định, event không được xuất hiện trong toàn bộ khoảng chờ.

Khi deadline hết, Scenario kết thúc với kết quả timeout tương ứng. Điều này làm cho lỗi có thể quan sát được và ngăn test suite bị treo vô hạn.

## 2. Timeout của Scenario khác timeout nào?

Một hệ thống event có nhiều lớp timeout. Không nên dùng một giá trị cho tất cả.

| Timeout | Phạm vi | Ý nghĩa |
|---|---|---|
| Scenario timeout | Một kỳ vọng trong Scenario API | Thời gian tối đa chờ event hoặc state condition |
| JUnit test timeout | Toàn bộ test method | Giới hạn tổng thời gian một test được phép chạy |
| Listener/service timeout | Xử lý nghiệp vụ hoặc lời gọi downstream | Giới hạn thời gian một thao tác trong ứng dụng |
| HTTP/client timeout | Một request mạng | Giới hạn thời gian chờ phản hồi từ dịch vụ ngoài |
| Broker/consumer timeout | Transport và consumer | Phụ thuộc broker, acknowledgement và cấu hình client |
| Build/test task timeout | Tiến trình kiểm thử hoặc CI job | Giới hạn thời gian của một nhóm test hoặc toàn pipeline |

Scenario timeout nên ngắn hơn JUnit timeout một khoảng đủ để test thực hiện cleanup và tạo thông báo lỗi. Nếu JUnit timeout ngắn hơn, JUnit có thể kết thúc test trước khi Scenario báo rõ kỳ vọng event nào đã hết hạn.

Scenario timeout không phải là timeout của listener. Khi test hết thời gian chờ, listener có thể vẫn đang chạy hoặc có thể phát event sau đó. Vì vậy, cần thiết kế cleanup và test isolation để tác vụ đến muộn không ảnh hưởng test kế tiếp.

## 3. Đặt timeout riêng cho một scenario

Spring Modulith cho phép cấu hình thời gian chờ ngay trong chuỗi Scenario. Với một event mong đợi, dùng `andWaitAtMost(Duration)` trước khi khai báo event type cần chờ.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class InventoryScenarioTests {

    @Test
    void reservesInventoryWithinDeadline(Scenario scenario) {
        UUID orderId = UUID.randomUUID();

        OrderConfirmed input = new OrderConfirmed(orderId);

        scenario.publish(input)
            .andWaitAtMost(Duration.ofSeconds(3))
            .andWaitForEventOfType(InventoryReserved.class)
            .matching(event -> event.orderId().equals(orderId))
            .toArriveAndVerify(event ->
                assertThat(event.orderId()).isEqualTo(orderId)
            );
    }
}
~~~

Trong ví dụ, Scenario chờ tối đa ba giây để tìm một `InventoryReserved` có cùng order ID. Nếu event phù hợp đến trước deadline, callback xác minh được thực hiện. Nếu không có event phù hợp trong khoảng thời gian đó, scenario thất bại vì timeout.

Hãy dùng predicate trong `matching` khi cùng một test context có thể phát nhiều event cùng type. Nếu chỉ chờ theo class, một event không liên quan có thể làm test thành công nhầm.

`Duration.ofSeconds(3)` chỉ là giá trị minh họa. Hãy chọn thời gian theo đặc tính listener, executor và môi trường test.

## 4. Timeout cho kỳ vọng event không xuất hiện

Một số test cần xác minh rằng một event **không** được phát. Ví dụ, khi đơn hàng bị từ chối, hệ thống không được phát `ShipmentRequested`.

Để chứng minh event không xuất hiện, Scenario phải chờ hết khoảng thời gian đã định. Nếu event phù hợp xuất hiện trong thời gian đó, test thất bại ngay; nếu không xuất hiện đến hết deadline, kỳ vọng phủ định được xem là thỏa mãn.

Ví dụ:

~~~java
@Test
void rejectedOrderDoesNotRequestShipment(Scenario scenario) {
    UUID orderId = UUID.randomUUID();

    scenario.publish(new OrderRejected(orderId))
        .andWaitAtMost(Duration.ofMillis(800))
        .forEventOfType(ShipmentRequested.class)
        .matching(event -> event.orderId().equals(orderId))
        .notToArrive();
}
~~~

Với `notToArrive()`, test chạy trong toàn bộ khoảng chờ. Đây là khác biệt quan trọng so với kỳ vọng event phải đến: kỳ vọng dương kết thúc ngay khi event phù hợp xuất hiện; kỳ vọng âm chỉ có thể kết luận sau khi hết thời gian quan sát.

Không nên dùng timeout quá ngắn cho test phủ định. Listener có thể chạy bất đồng bộ và event không mong muốn có thể xuất hiện sau một khoảng trễ. Chọn khoảng chờ đủ bao phủ đường xử lý mà test muốn kiểm tra.

## 5. Timeout khi chờ state change

Không phải mọi outcome đều là event mới. Một listener có thể cập nhật read model hoặc trạng thái của module mà không phát event tiếp theo. Scenario có thể chờ kết quả đọc từ một component được expose.

Ví dụ:

~~~java
@Test
void reservationBecomesVisibleWithinDeadline(
    Scenario scenario,
    InventoryManagement inventory
) {
    UUID orderId = UUID.randomUUID();

    scenario.publish(new OrderConfirmed(orderId))
        .andWaitAtMost(Duration.ofSeconds(3))
        .andWaitForStateChange(() -> inventory.findReservation(orderId))
        .andVerify(reservation ->
            assertThat(reservation).isPresent()
        );
}
~~~

Trong ví dụ, Scenario thăm dò kết quả của `findReservation` cho đến khi giá trị được xem là kết quả đủ điều kiện hoặc deadline hết. Mặc định, Scenario xem giá trị khác null, Optional có giá trị và boolean true là tín hiệu kết quả có ý nghĩa. Nếu điều kiện nghiệp vụ phức tạp hơn, dùng overload nhận predicate để xác định rõ trạng thái được chấp nhận.

Không nên dùng một giá trị luôn khác null nếu nó đã tồn tại trước stimulus và không chứng minh được cập nhật mới. Hãy kiểm tra version, trạng thái hoặc timestamp phù hợp để xác nhận thay đổi phát sinh từ event vừa gửi.

## 6. Tùy biến điều kiện chờ bằng customize

Ngoài timeout chuyên biệt, Scenario cho phép tùy biến ConditionFactory của Awaitility bằng `customize(...)`. Cách này hữu ích khi cần điều chỉnh nhiều thuộc tính chờ, chẳng hạn thời gian tối đa hoặc khoảng polling.

Ví dụ đặt giới hạn hai giây:

~~~java
scenario.publish(new OrderConfirmed(orderId))
    .customize(conditionFactory ->
        conditionFactory.atMost(Duration.ofSeconds(2))
    )
    .andWaitForEventOfType(InventoryReserved.class)
    .matching(event -> event.orderId().equals(orderId))
    .toArriveAndVerify(event ->
        assertThat(event.orderId()).isEqualTo(orderId)
    );
~~~

`andWaitAtMost(Duration)` diễn đạt trực tiếp nhu cầu đặt deadline cho một kỳ vọng event. `customize(...)` phù hợp khi cần cấu hình ConditionFactory chi tiết hơn. Không cần dùng cả hai cùng lúc nếu chúng đặt các giới hạn chồng chéo mà không có mục đích rõ ràng.

API cụ thể cần tương thích với phiên bản Spring Modulith và Awaitility mà dự án đang dùng. Hãy ưu tiên API Scenario được cung cấp bởi dependency hiện tại.

## 7. Timeout mặc định cho nhiều scenario

Nếu nhiều test có cùng ngân sách chờ, có thể chuẩn hóa bằng `ScenarioCustomizer` được đăng ký như JUnit extension. Customizer cung cấp cấu hình mặc định cho các Scenario trong test class.

Cách này hữu ích khi:

- Nhiều module có cùng đặc tính xử lý bất đồng bộ.
- CI có tốc độ ổn định và đội ngũ muốn chuẩn hóa thời gian chờ.
- Cần áp dụng polling interval hoặc điều kiện Awaitility thống nhất.
- Muốn điều chỉnh mặc định tại một nơi thay vì lặp cấu hình trong mọi test.

Không nên áp dụng một timeout toàn cục quá ngắn cho tất cả luồng. Listener gửi email, cập nhật database và gọi dịch vụ ngoài có thời gian xử lý khác nhau. Giữ timeout mặc định hợp lý, sau đó override cho scenario có yêu cầu đặc biệt.

Với một test quan trọng, đặt timeout ngay cạnh kỳ vọng giúp người đọc hiểu test chờ bao lâu và vì sao.

## 8. Chọn giá trị timeout hợp lý

Timeout nên dựa trên thời gian xử lý quan sát được trong môi trường test, cộng thêm biên độ cho scheduler, thread contention và tải CI.

Một cách tiếp cận:

1. Đo thời gian hoàn tất của listener khi workload ổn định.
2. Xem phân vị cao như p95 hoặc p99 thay vì chỉ lấy average.
3. Xem sự khác biệt giữa máy local và CI.
4. Cộng khoảng dự phòng hợp lý.
5. Giữ timeout nhỏ hơn giới hạn tổng của test suite.
6. Điều chỉnh khi dependency hoặc kiến trúc xử lý thay đổi.

Ví dụ, nếu listener thường hoàn tất trong 100–300 ms và p99 dưới 700 ms trong CI, timeout hai hoặc ba giây có thể là điểm khởi đầu. Nếu listener phải khởi tạo container hoặc thực hiện I/O chậm, cần đánh giá riêng. Đây chỉ là minh họa; không có timeout chuẩn cho mọi dự án.

Timeout quá ngắn tạo test flaky vì test thất bại do tải máy hoặc scheduling. Timeout quá dài làm feedback chậm và che giấu listener bị kẹt. Mục tiêu là đủ dài để bao phủ biến thiên bình thường nhưng đủ ngắn để phát hiện bất thường kịp thời.

## 9. Timeout không thay thế điều kiện hoàn tất

Một scenario cần chờ đúng điều kiện nghiệp vụ. Timeout chỉ trả lời “chờ tối đa bao lâu”, không trả lời “điều gì được xem là thành công”.

Ví dụ, chờ bất kỳ `InventoryReserved` nào có thể không đủ nếu event thuộc một đơn hàng khác. Cần matching theo order ID hoặc correlation ID. Với state change, cần kiểm tra status/version thực sự đạt giá trị mong đợi.

Các điều kiện nên xác định rõ:

- Event type cần nhận.
- Aggregate hoặc business ID liên quan.
- Correlation ID nếu có nhiều luồng cùng chạy.
- Version hoặc sequence nếu cần kiểm soát thứ tự.
- Trạng thái cuối cùng cần đạt.
- Có chấp nhận event lặp hoặc kết quả trung gian không.

Nếu điều kiện quá rộng, test có thể xanh dù luồng nghiệp vụ sai. Nếu điều kiện quá hẹp, test có thể timeout dù listener đã phát event đúng nhưng predicate không khớp.

## 10. Không dùng Thread.sleep để chờ event

Một cách thường thấy là:

~~~java
publish(event);
Thread.sleep(1000);
assertThat(repository.findById(orderId)).isPresent();
~~~

Cách này có hai vấn đề. Nếu listener hoàn tất sau 20 ms, test vẫn lãng phí gần một giây. Nếu listener cần hơn một giây trong CI, test thất bại dù hệ thống có thể hoàn tất bình thường.

Scenario API kết hợp cơ chế chờ theo điều kiện giúp test kết thúc ngay khi outcome xuất hiện hoặc khi timeout hết. Nó thể hiện rõ kỳ vọng và giảm phụ thuộc vào một khoảng sleep cố định.

Dùng `Thread.sleep` không phải cơ chế đồng bộ test đáng tin cậy. Nếu cần kiểm tra một khoảng thời gian event không xuất hiện, dùng `notToArrive()` với timeout rõ ràng để thể hiện đúng ý định.

## 11. Phân biệt timeout với lỗi listener

Khi Scenario timeout, điều đó chỉ nói rằng điều kiện mong đợi chưa được quan sát trước deadline. Nguyên nhân có thể khác nhau:

- Event đầu vào không được publish.
- Transaction stimulus chưa commit theo cách test mong đợi.
- Listener không được đăng ký hoặc không thuộc module context.
- Listener ném exception.
- Listener đang chờ executor hoặc queue.
- Dependency database hoặc API bị chậm.
- Event đầu ra được phát nhưng predicate không khớp.
- State query không trả về giá trị được chấp nhận.
- Timeout quá ngắn so với môi trường chạy.

Timeout không tự cho biết nguyên nhân. Khi test thất bại, hãy kiểm tra exception, log listener, publication state, executor queue và điều kiện matching. Nếu cần, thêm assertion hoặc trace metadata để xác định event ID và correlation ID.

Không tăng timeout ngay lập tức nếu chưa hiểu nguyên nhân. Tăng từ hai lên ba mươi giây có thể làm test xanh nhưng che giấu lỗi listener hoặc dependency.

## 12. Event đến sau deadline

Một event có thể được phát sau khi Scenario đã timeout. Điều này có thể xảy ra nếu listener bị chậm nhưng vẫn tiếp tục chạy, hoặc downstream phản hồi muộn.

Do đó:

- Timeout không phải lệnh cancel listener.
- Timeout không rollback transaction đã commit.
- Timeout không xóa publication đang chờ trong Event Publication Registry.
- Timeout không bảo đảm không có side effect sau khi test kết thúc.
- Test cần cleanup dữ liệu và cô lập tác vụ bất đồng bộ có thể đến muộn.

Nếu event đến muộn, có thể test sau bị ảnh hưởng nếu dùng chung business ID hoặc dữ liệu. Dùng ID duy nhất cho mỗi test, cleanup theo ID và tránh chia sẻ state giữa test cases.

Với side effect bên ngoài như email hoặc broker, ưu tiên fake adapter hoặc môi trường test cô lập. Không để test timeout tạo message còn tồn tại trong broker dùng chung rồi tác động đến test khác.

## 13. Tương tác với transaction và AFTER_COMMIT

Scenario stimulus được thực thi qua transaction callback để bảo đảm event được publish trong transaction phù hợp với transactional event listener. Cơ chế này có thể bắt đầu transaction mới ngay cả khi test method đang chạy trong transaction. Vì vậy, thay đổi dữ liệu phát sinh từ stimulus có thể đã commit và không tự rollback theo transaction của test method.

Điều này quan trọng khi kiểm thử listener dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`:

- Event chỉ được xử lý sau khi transaction stimulus commit.
- Scenario chờ outcome sau stimulus và có thể quan sát listener bất đồng bộ.
- Nếu test timeout, transaction stimulus có thể đã commit.
- Cleanup cần được đăng ký hoặc thực hiện rõ ràng, kể cả khi scenario thất bại.

Dùng callback cleanup của Scenario nếu phù hợp với dữ liệu test. Không giả định rollback tự động sẽ xóa mọi thay đổi được tạo trong transaction stimulus.

## 14. JUnit timeout và Scenario timeout phối hợp

Có thể dùng JUnit `@Timeout` như một lớp bảo vệ tổng thời gian test method. Tuy nhiên, Scenario timeout nên quản lý kỳ vọng event/state cụ thể.

Ví dụ minh họa:

~~~java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryScenarioTimeoutTests {

    @Test
    @Timeout(value = 8, unit = TimeUnit.SECONDS)
    void publishesInventoryResultWithinScenarioDeadline(Scenario scenario) {
        scenario.publish(new OrderConfirmed(UUID.randomUUID()))
            .andWaitAtMost(Duration.ofSeconds(3))
            .andWaitForEventOfType(InventoryReserved.class)
            .toArrive();
    }
}
~~~

Scenario có tối đa ba giây cho kỳ vọng event; JUnit có giới hạn tổng tám giây để bao phủ stimulus, assertion và cleanup. Cần chọn các giá trị theo thời gian thực tế của test.

Không đặt JUnit timeout bằng hoặc nhỏ hơn Scenario timeout nếu test còn cần khởi tạo context, chạy stimulus và cleanup. Khi JUnit timeout xảy ra trước, thông tin lỗi có thể kém cụ thể và cleanup có thể không hoàn tất theo cách mong muốn.

## 15. Polling interval và tải của test

Scenario sử dụng cơ chế chờ theo điều kiện. Polling quá thường xuyên có thể tạo truy vấn lặp lên database hoặc gọi getter liên tục; polling quá thưa làm test phát hiện kết quả muộn hơn dù event đã hoàn tất.

Khi chờ state change:
- Supplier nên nhẹ, nhanh và không có side effect.
- Truy vấn nên dùng index phù hợp.
- Tránh gọi API ngoài trong mỗi lần polling.
- Chỉ tăng polling interval khi có bằng chứng truy vấn quá dày.
- Không dùng polling để thay thế event-driven assertion nếu event là kết quả mong đợi trực tiếp.

Khi chờ event publication, framework có thể quan sát event thông qua cơ chế Scenario/AssertablePublishedEvents. Predicate matching nên thuần và nhanh, không gọi dịch vụ hoặc thay đổi trạng thái.

## 16. Chẩn đoán timeout trong Scenario

Khi test timeout, kiểm tra theo thứ tự:

1. **Stimulus:** event hoặc component invocation có thực sự được thực thi không?
2. **Transaction:** transaction stimulus có commit để transactional listener chạy không?
3. **Listener registration:** listener có nằm trong application module context và được phát hiện không?
4. **Execution:** listener có được gọi không, executor có task backlog không?
5. **Failure:** listener có exception hoặc retry không?
6. **Outcome:** event kết quả có được publish hoặc state có được cập nhật không?
7. **Matching:** predicate có lọc nhầm event đúng không?
8. **Deadline:** timeout có đủ cho workload và môi trường CI không?
9. **Cleanup:** listener hoặc message đến muộn có làm ảnh hưởng test khác không?

Nên đưa event type, event ID, aggregate ID, correlation ID và thời gian chờ vào log test khi có thể. Không ghi payload nhạy cảm chỉ để chẩn đoán.

Nếu listener được quản lý bởi Event Publication Registry, kiểm tra publication chưa hoàn tất và lỗi tương ứng. Registry cung cấp tín hiệu về việc giao event đến listener; nó không thay thế việc kiểm tra executor, downstream hoặc logic nghiệp vụ.

## 17. Ví dụ: kiểm tra event không đến trong một khoảng thời gian

Giả sử đơn hàng bị từ chối thì không được tạo yêu cầu giao hàng. Test cần chờ đủ khoảng thời gian để xác minh không có `ShipmentRequested` phù hợp.

~~~java
@Test
void rejectedOrderMustNotStartShipment(Scenario scenario) {
    UUID orderId = UUID.randomUUID();

    scenario.publish(new OrderRejected(orderId))
        .andWaitAtMost(Duration.ofSeconds(1))
        .forEventOfType(ShipmentRequested.class)
        .matching(event -> event.orderId().equals(orderId))
        .notToArrive();
}
~~~

Kết quả này chỉ chứng minh không có event phù hợp trong một giây quan sát. Nó không chứng minh event không bao giờ được phát trong tương lai. Nếu nghiệp vụ yêu cầu một điều kiện lâu dài, cần kiểm tra state machine hoặc invariant tương ứng thay vì chỉ dựa vào một khoảng chờ ngắn.

## 18. Những lỗi thường gặp

**Không đặt timeout.** Một listener không bao giờ phát event có thể khiến test chờ quá lâu hoặc bị giới hạn ở cấp build.

**Timeout quá ngắn.** Test thất bại ngẫu nhiên trên CI do tải máy, JIT hoặc scheduler.

**Timeout quá dài.** Feedback chậm và lỗi listener bị phát hiện muộn.

**Chờ sai event.** Test chờ event type đúng nhưng không matching theo business ID, khiến event của test khác làm test xanh.

**Dùng notToArrive với khoảng chờ không hợp lý.** Event đến chậm hơn khoảng quan sát vẫn có thể tạo side effect sau khi test đã qua.

**Nhầm Scenario timeout với cancellation.** Listener vẫn có thể tiếp tục sau khi test hết thời gian chờ.

**Dùng Thread.sleep.** Test vừa chậm vừa không ổn định khi tốc độ xử lý thay đổi.

**Bỏ qua transaction commit.** Listener sau commit không chạy vì stimulus chưa tạo transaction commit như dự kiến.

**Không cleanup.** Dữ liệu hoặc tác vụ bất đồng bộ còn lại ảnh hưởng test khác.

**Tăng timeout để che lỗi.** Listener bị kẹt, dependency lỗi hoặc predicate sai vẫn còn nguyên.

## 19. Checklist timeout cho Scenario API

- [ ] Mỗi kỳ vọng bất đồng bộ có timeout rõ ràng hoặc default đã được kiểm soát.
- [ ] Timeout phù hợp với latency quan sát được và môi trường CI.
- [ ] Scenario timeout nhỏ hơn JUnit test timeout và còn thời gian cleanup.
- [ ] Event type được xác định rõ.
- [ ] Predicate matching theo business ID/correlation ID khi cần.
- [ ] Kỳ vọng phủ định dùng `notToArrive()` và chờ đủ khoảng thời gian.
- [ ] State change dùng predicate thể hiện đúng trạng thái mong đợi.
- [ ] Supplier dùng để polling nhẹ và không có side effect.
- [ ] Không dùng `Thread.sleep` để chờ listener.
- [ ] Hiểu rằng timeout không cancel listener hoặc rollback transaction đã commit.
- [ ] Có cleanup cho dữ liệu và tác vụ đến muộn.
- [ ] Khi timeout, có thể tra cứu log, publication state và executor/dependency.
- [ ] Không tăng timeout chỉ để che một lỗi chưa được chẩn đoán.
- [ ] Đã kiểm tra API Scenario theo phiên bản Spring Modulith đang sử dụng.

## 20. Nguyên tắc sử dụng timeout trong scenario

Timeout trong Spring Modulith Scenario API giới hạn thời gian chờ một event hoặc state change sau stimulus. Dùng `andWaitAtMost(Duration)` cho một kỳ vọng cụ thể, `customize(...)` khi cần điều chỉnh ConditionFactory và `ScenarioCustomizer` khi muốn chuẩn hóa mặc định cho một nhóm test. Với kỳ vọng event không xuất hiện, `notToArrive()` phải chờ hết khoảng thời gian đã định.

Hãy chọn timeout theo latency thực tế, phân biệt nó với JUnit và service timeout, matching đúng event và chuẩn bị cleanup cho công việc đến muộn. Khi timeout xảy ra, điều tra transaction, listener, executor, publication và predicate trước khi tăng thời gian chờ. Như vậy scenario test vừa có giới hạn rõ ràng vừa phản ánh đúng hành vi bất đồng bộ của application events.
