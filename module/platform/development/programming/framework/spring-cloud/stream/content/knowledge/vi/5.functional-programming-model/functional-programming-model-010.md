# Kiểm chứng hàm nghiệp vụ độc lập với Spring và broker

Trong ứng dụng Spring Cloud Stream, Supplier, Function và Consumer là các điểm nối giữa mã ứng dụng với luồng thông điệp. Chúng giúp framework biết dữ liệu được tạo ra, biến đổi hoặc tiêu thụ như thế nào. Tuy nhiên, phần quyết định nghiệp vụ bên trong các hàm này vẫn cần được kiểm chứng rõ ràng: một đơn hàng có đủ điều kiện giữ hàng không, dữ liệu đầu vào nào bị từ chối, hoặc một kết quả được chuyển thành thao tác lưu trữ nào.

Một cách tổ chức hiệu quả là tách phần nghiệp vụ khỏi phần kết nối. Hàm nghiệp vụ nhận dữ liệu đã được chuẩn hóa, tính toán và trả về kết quả có thể dự đoán. Lớp tích hợp chịu trách nhiệm nhận thông điệp, gọi hàm nghiệp vụ, truy cập cơ sở dữ liệu hoặc phát kết quả qua binder. Nhờ ranh giới này, phần lớn quy tắc có thể được kiểm thử bằng JUnit mà không cần khởi động Spring ApplicationContext hoặc chạy Kafka, RabbitMQ hay Pulsar.

## 1. Phân biệt logic nghiệp vụ và phần tích hợp

Một luồng xử lý sự kiện thường có ba lớp trách nhiệm:

| Lớp | Trách nhiệm | Cách kiểm thử phù hợp |
|---|---|---|
| Nghiệp vụ | Kiểm tra điều kiện, tính toán quyết định, xác định kết quả | Unit test trực tiếp đối tượng hoặc hàm Java |
| Adapter ứng dụng | Đọc nguồn dữ liệu, gọi use case, chuyển kết quả thành thao tác qua cổng (port) | Unit test với fake hoặc mock dependency |
| Spring Cloud Stream và binder | Nhận/gửi thông điệp, ánh xạ binding, chuyển đổi payload, áp dụng cấu hình broker | Test Binder và integration test với broker |

Ví dụ, khi nhận OrderSubmitted, dịch vụ kho cần quyết định có thể giữ hàng hay không. Quy tắc như số lượng phải lớn hơn 0 và tồn kho phải đủ là nghiệp vụ. Việc đọc thông điệp từ topic, chuyển JSON thành record Java và ghi lệnh giữ hàng qua hệ thống kho là trách nhiệm tích hợp.

Nếu gộp tất cả vào một hàm Consumer lớn, bài kiểm thử thường phải khởi tạo nhiều dependency và dễ bị chi phối bởi hạ tầng. Khi tách phần quyết định thành một đối tượng Java thông thường, có thể kiểm tra các trường hợp đúng, sai và biên chỉ bằng dữ liệu đầu vào.

## 2. Thiết kế phần nghiệp vụ có đầu vào và đầu ra rõ ràng

Một hàm dễ kiểm thử thường có các đặc điểm:

- Nhận dữ liệu đầu vào tường minh, thể hiện đủ thông tin để đưa ra quyết định.
- Trả về kết quả tường minh thay vì âm thầm thay đổi trạng thái bên ngoài.
- Không tự đọc đồng hồ hệ thống, tạo số ngẫu nhiên hoặc gọi mạng trong lúc tính toán.
- Không phụ thuộc vào Spring Context, MessageChannel, KafkaTemplate hoặc API của broker.
- Xác định rõ cách xử lý dữ liệu không hợp lệ.

Ví dụ sau biểu diễn yêu cầu giữ hàng và quyết định nghiệp vụ bằng Java record:

~~~java
public record ReservationRequest(
    String orderId,
    String sku,
    int quantity,
    int availableQuantity
) {}

public enum DecisionReason {
    APPROVED,
    INSUFFICIENT_STOCK
}

public record ReservationDecision(
    String orderId,
    String sku,
    int quantity,
    boolean accepted,
    DecisionReason reason
) {}
~~~

Quy tắc được đặt trong ReservationPolicy. Đối tượng này không biết thông điệp đến từ Kafka hay một lời gọi Java trực tiếp:

~~~java
import java.util.Objects;

public final class ReservationPolicy {

    public ReservationDecision decide(ReservationRequest request) {
        Objects.requireNonNull(request, "request must not be null");

        if (request.orderId() == null || request.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (request.sku() == null || request.sku().isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (request.availableQuantity() < 0) {
            throw new IllegalArgumentException(
                "availableQuantity must not be negative"
            );
        }

        if (request.availableQuantity() < request.quantity()) {
            return new ReservationDecision(
                request.orderId(),
                request.sku(),
                request.quantity(),
                false,
                DecisionReason.INSUFFICIENT_STOCK
            );
        }

        return new ReservationDecision(
            request.orderId(),
            request.sku(),
            request.quantity(),
            true,
            DecisionReason.APPROVED
        );
    }
}
~~~

Với cùng một ReservationRequest, decide luôn trả về cùng một ReservationDecision hoặc cùng một loại lỗi xác thực. Đây là tính xác định (determinism), giúp bài kiểm thử không phụ thuộc thời điểm chạy hay trạng thái của broker.

## 3. Kiểm thử Function trực tiếp bằng JUnit

Function phù hợp với phần xử lý có đầu vào và đầu ra rõ ràng. Có thể chuyển phương thức decide thành một Function bằng method reference:

~~~java
import java.util.function.Function;

Function<ReservationRequest, ReservationDecision> decideReservation =
    new ReservationPolicy()::decide;
~~~

Đoạn mã trên chỉ dùng API Java. Không cần khởi động Spring để gọi hàm. Khi Spring Cloud Stream đăng ký một bean Function, framework mới đảm nhiệm việc nối đầu vào và đầu ra của hàm với binding.

Ví dụ kiểm thử với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ReservationPolicyTest {

    private final ReservationPolicy policy = new ReservationPolicy();

    @Test
    void approvesReservationWhenStockIsEnough() {
        var request = new ReservationRequest(
            "order-101", "BOOK-01", 2, 5
        );

        var result = policy.decide(request);

        assertEquals(
            new ReservationDecision(
                "order-101",
                "BOOK-01",
                2,
                true,
                DecisionReason.APPROVED
            ),
            result
        );
    }

    @Test
    void rejectsReservationWhenStockIsInsufficient() {
        var request = new ReservationRequest(
            "order-102", "BOOK-01", 4, 3
        );

        var result = policy.decide(request);

        assertEquals(false, result.accepted());
        assertEquals(
            DecisionReason.INSUFFICIENT_STOCK,
            result.reason()
        );
    }

    @Test
    void rejectsInvalidQuantity() {
        var request = new ReservationRequest(
            "order-103", "BOOK-01", 0, 10
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> policy.decide(request)
        );
    }
}
~~~

Ba trường hợp trên kiểm tra quyết định thành công, từ chối theo nghiệp vụ và dữ liệu không hợp lệ. Có thể bổ sung các trường hợp biên như tồn kho bằng đúng số lượng yêu cầu, số lượng tồn bằng 0, mã đơn hàng trống và SKU không hợp lệ. Mỗi test nên mô tả một quy tắc cụ thể để khi thất bại, nguyên nhân dễ xác định.

Với record Java, equals được sinh tự động dựa trên các thành phần dữ liệu. Vì vậy, so sánh kết quả record giúp xác minh toàn bộ giá trị đầu ra. Nếu kết quả chứa danh sách hoặc kiểu dữ liệu phức tạp, có thể dùng AssertJ để viết assertion dễ đọc hơn.

## 4. Kiểm thử Supplier bằng nguồn dữ liệu giả

Supplier không nhận đối số và trả về một giá trị mỗi lần được gọi. Trong ứng dụng thực tế, nguồn dữ liệu có thể đọc một hàng đợi công việc, truy vấn repository hoặc lấy dữ liệu từ hệ thống ngoài. Để kiểm thử phần lấy dữ liệu mà không cần broker, đặt thao tác đọc sau một interface nhỏ.

~~~java
import java.util.Optional;

@FunctionalInterface
public interface PendingOrderSource {
    Optional<OrderSubmitted> next();
}

public record OrderSubmitted(
    String orderId,
    String sku,
    int quantity
) {}
~~~

Supplier adapter chuyển Optional thành giá trị được phát. Khi không có dữ liệu, trả về null để biểu thị lần poll này không tạo thông điệp:

~~~java
import java.util.function.Supplier;

public final class PendingOrderSupplier
        implements Supplier<OrderSubmitted> {

    private final PendingOrderSource source;

    public PendingOrderSupplier(PendingOrderSource source) {
        this.source = source;
    }

    @Override
    public OrderSubmitted get() {
        return source.next().orElse(null);
    }
}
~~~

Kiểm thử Supplier bằng một nguồn giả trong bộ nhớ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PendingOrderSupplierTest {

    @Test
    void returnsNextOrderAndThenReturnsNullWhenSourceIsEmpty() {
        var order = new OrderSubmitted(
            "order-201", "BOOK-02", 1
        );
        Deque<OrderSubmitted> queue =
            new ArrayDeque<>(List.of(order));

        PendingOrderSource source =
            () -> Optional.ofNullable(queue.pollFirst());
        var supplier = new PendingOrderSupplier(source);

        assertEquals(order, supplier.get());
        assertNull(supplier.get());
    }
}
~~~

Test này xác minh adapter lấy đúng phần tử tiếp theo và biểu thị nguồn rỗng. Nó không kiểm tra chu kỳ poll, thread, binding hay việc broker nhận thông điệp. Các hành vi đó thuộc lớp kiểm thử Spring Cloud Stream và binder.

Nếu Supplier tạo dữ liệu mới bằng thời gian hoặc số ngẫu nhiên, hãy cân nhắc đưa Clock, ID generator hoặc nguồn dữ liệu vào qua constructor. Bài kiểm thử có thể cung cấp implementation cố định để kết quả lặp lại được. Không nên để test phụ thuộc vào thời gian thực hoặc giá trị ngẫu nhiên khó dự đoán.

## 5. Kiểm thử Consumer qua cổng nghiệp vụ

Consumer thường kết thúc luồng bằng một tác động: ghi cơ sở dữ liệu, gọi dịch vụ khác hoặc phát một lệnh tiếp theo. Tác động này không phải phép tính thuần. Có thể tách nó sau một interface để kiểm tra quyết định gọi hay không gọi mà không kết nối hệ thống thật.

Khai báo cổng thực hiện thao tác giữ hàng:

~~~java
@FunctionalInterface
public interface ReservationPort {
    void reserve(String orderId, String sku, int quantity);
}
~~~

Consumer xử lý quyết định:

~~~java
import java.util.function.Consumer;

public final class ReservationDecisionConsumer
        implements Consumer<ReservationDecision> {

    private final ReservationPort reservationPort;

    public ReservationDecisionConsumer(ReservationPort reservationPort) {
        this.reservationPort = reservationPort;
    }

    @Override
    public void accept(ReservationDecision decision) {
        if (decision.accepted()) {
            reservationPort.reserve(
                decision.orderId(),
                decision.sku(),
                decision.quantity()
            );
        }
    }
}
~~~

Test dùng fake port ghi lại các lời gọi:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReservationDecisionConsumerTest {

    record Reservation(String orderId, String sku, int quantity) {}

    @Test
    void sendsAcceptedDecisionToReservationPort() {
        List<Reservation> calls = new ArrayList<>();
        ReservationPort fakePort = (orderId, sku, quantity) ->
            calls.add(new Reservation(orderId, sku, quantity));
        var consumer = new ReservationDecisionConsumer(fakePort);

        consumer.accept(new ReservationDecision(
            "order-301",
            "BOOK-03",
            2,
            true,
            DecisionReason.APPROVED
        ));

        assertEquals(
            List.of(new Reservation("order-301", "BOOK-03", 2)),
            calls
        );
    }

    @Test
    void doesNotReserveWhenDecisionIsRejected() {
        List<Reservation> calls = new ArrayList<>();
        ReservationPort fakePort = (orderId, sku, quantity) ->
            calls.add(new Reservation(orderId, sku, quantity));
        var consumer = new ReservationDecisionConsumer(fakePort);

        consumer.accept(new ReservationDecision(
            "order-302",
            "BOOK-03",
            2,
            false,
            DecisionReason.INSUFFICIENT_STOCK
        ));

        assertEquals(List.of(), calls);
    }
}
~~~

Fake port cho biết Consumer đã yêu cầu thao tác gì mà không cần cơ sở dữ liệu hoặc broker. Với logic phức tạp hơn, có thể dùng Mockito để xác minh số lần gọi và đối số. Fake thường phù hợp khi muốn thể hiện một hành vi nghiệp vụ đơn giản bằng trạng thái có thể đọc trực tiếp.

## 6. Nối các lớp bằng bean Spring Cloud Stream

Sau khi kiểm thử các lớp Java độc lập, ứng dụng mới đăng ký chúng thành bean để Spring Cloud Stream nối với binding. Ví dụ một dịch vụ xử lý quyết định có thể khai báo:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReservationStreamConfiguration {

    @Bean
    Function<ReservationRequest, ReservationDecision> reservationDecision(
            ReservationPolicy policy) {
        return policy::decide;
    }
}
~~~

Nếu ứng dụng dùng Consumer, bean có thể trả về một instance của ReservationDecisionConsumer. Nếu dùng Supplier, bean có thể trả về PendingOrderSupplier. Trong một ứng dụng có nhiều bean hàm, khai báo spring.cloud.function.definition để chỉ rõ hàm nào được kích hoạt hoặc tổ hợp nào được nối với nhau. Các dịch vụ minh họa ở trên có thể được triển khai riêng, mỗi dịch vụ chỉ đăng ký những bean cần thiết.

Điểm quan trọng là ReservationPolicy, PendingOrderSupplier và ReservationDecisionConsumer có constructor tường minh, không tự tìm dependency từ ApplicationContext. Unit test có thể khởi tạo chúng trực tiếp. Spring chỉ đảm nhiệm việc tạo bean, cấu hình và kết nối các adapter khi ứng dụng chạy.

## 7. Kiểm soát tính xác định và các phụ thuộc bên ngoài

Một hàm có thể khó kiểm thử nếu kết quả thay đổi theo môi trường. Các nguồn không xác định thường gặp gồm:

| Nguồn phụ thuộc | Cách làm cho kết quả kiểm thử ổn định |
|---|---|
| Thời gian hiện tại | Truyền java.time.Clock và dùng Clock.fixed trong test |
| UUID hoặc số ngẫu nhiên | Truyền ID generator hoặc Random có seed cố định |
| Cơ sở dữ liệu | Đặt thao tác đọc/ghi sau repository hoặc port; dùng fake cho unit test |
| HTTP hoặc dịch vụ bên ngoài | Đặt sau client interface; kiểm thử logic với fake response |
| Biến môi trường và cấu hình | Truyền giá trị cần thiết qua constructor hoặc tham số |
| Broker và header thông điệp | Chuyển dữ liệu cần cho nghiệp vụ thành input rõ ràng; kiểm thử binding ở lớp tích hợp |

Ví dụ, nếu quyết định giữ hàng cần xét thời điểm hết hạn của đơn, không nên gọi Instant.now() rải rác trong policy. Hãy đưa thời điểm hiện tại vào ReservationRequest hoặc truyền Clock vào use case. Khi đó test có thể cố định thời gian và kiểm tra chính xác ranh giới hết hạn.

Không phải mọi lớp đều phải thuần tuyệt đối. Supplier đọc dữ liệu và Consumer ghi dữ liệu vốn có tác động bên ngoài. Mục tiêu là đặt tác động tại ranh giới rõ ràng, còn phần quy tắc quan trọng có đầu vào và kết quả có thể kiểm chứng.

## 8. Kiểm thử lỗi và khả năng xử lý lại

Trong hệ thống phân tán, một thông điệp có thể được giao lại khi consumer đã thực hiện tác động nhưng chưa hoàn tất xác nhận với broker. Vì vậy, test logic nghiệp vụ nên kiểm tra các điều kiện đầu vào, còn test adapter cần kiểm tra cách xử lý lỗi và lặp.

Một số tình huống nên có trong bộ kiểm thử:

- Payload thiếu mã định danh hoặc có trường bắt buộc không hợp lệ.
- Số lượng bằng 0, số lượng âm hoặc vượt giới hạn nghiệp vụ.
- Dữ liệu tồn kho bằng đúng số lượng yêu cầu và thấp hơn một đơn vị.
- Cổng lưu trữ ném lỗi tạm thời hoặc lỗi không thể phục hồi.
- Cùng một message ID được gửi lại.
- Consumer được gọi lại sau khi lần trước thất bại.
- Một tác động đã hoàn tất nhưng tiến trình lỗi trước khi xác nhận thông điệp.

Idempotency thường phải được thực hiện ở ranh giới lưu trạng thái hoặc cổng nghiệp vụ. Ví dụ, ReservationPort có thể cung cấp thao tác reserveIfAbsent theo orderId hoặc một khóa idempotency. Unit test có thể kiểm tra quy tắc chống trùng của lớp ứng dụng với fake store; integration test cần xác minh transaction và ràng buộc duy nhất trên hệ thống lưu trữ thật.

Không nên kiểm tra rằng hàm Consumer tự bảo đảm exactly-once chỉ bằng một unit test. Bảo đảm giao nhận là kết quả phối hợp của broker, binder, cấu hình acknowledgement, transaction và cách hệ thống đích ghi nhận tác động. Bài kiểm thử độc lập chỉ xác minh phần trách nhiệm mà mã ứng dụng kiểm soát.

## 9. Chọn đúng cấp kiểm thử

Unit test và integration test giải quyết những câu hỏi khác nhau. Tăng số lượng test Spring Context cho mọi quy tắc nhỏ sẽ làm bộ test chậm và khó chẩn đoán. Ngược lại, chỉ có unit test thì chưa phát hiện lỗi tên binding, chuyển đổi payload hoặc cấu hình broker.

| Cấp kiểm thử | Câu hỏi cần trả lời | Thành phần sử dụng |
|---|---|---|
| Unit test nghiệp vụ | Với dữ liệu này, policy trả về quyết định nào? | JUnit, AssertJ; đối tượng Java thuần |
| Unit test adapter | Khi nhận kết quả này, adapter gọi port với đối số nào? | Fake hoặc Mockito |
| Spring Cloud Stream Test Binder | Payload có đi vào/ra đúng binding và được chuyển đổi đúng không? | Test Binder, InputDestination, OutputDestination |
| Integration test broker | Group, partition, acknowledgement, retry, DLQ và kết nối thực hoạt động thế nào? | Kafka, RabbitMQ hoặc Pulsar thực; có thể dùng Testcontainers |
| End-to-end test | Chuỗi dịch vụ có tạo ra kết quả nghiệp vụ mong muốn không? | Môi trường tích hợp với các thành phần cần thiết |

Ví dụ, unit test ReservationPolicy không cần biết destination là inventory.requested. Test Binder mới kiểm tra ứng dụng nối đúng binding và gửi/nhận payload. Integration test với Kafka mới có thể kiểm tra consumer group, partition assignment và hành vi retry theo cấu hình broker đang dùng.

Test Binder không thay thế broker thật. Nó rất hữu ích để kiểm tra đường đi thông điệp trong phạm vi ứng dụng, nhưng không mô phỏng đầy đủ mọi đặc tính của Kafka, RabbitMQ hoặc Pulsar.

## 10. Tổ chức bộ test dễ bảo trì

Nên đặt test gần với lớp mà nó xác minh:

~~~text
src/
  main/
    java/
      .../
        domain/
          ReservationPolicy.java
          ReservationRequest.java
          ReservationDecision.java
        application/
          ReservationDecisionConsumer.java
          PendingOrderSupplier.java
        messaging/
          ReservationStreamConfiguration.java
  test/
    java/
      .../
        domain/
          ReservationPolicyTest.java
        application/
          ReservationDecisionConsumerTest.java
          PendingOrderSupplierTest.java
        messaging/
          ReservationBindingTest.java
~~~

Đây là cách chia tham khảo. Dự án nhỏ có thể giữ cấu trúc package đơn giản hơn, miễn là phần nghiệp vụ không buộc phải phụ thuộc vào binder hoặc Spring để được kiểm thử.

Một test tốt thường có ba phần:

1. **Arrange:** tạo dữ liệu đầu vào và fake dependency với trạng thái xác định.
2. **Act:** gọi đúng một hành vi cần kiểm chứng.
3. **Assert:** kiểm tra kết quả hoặc tác động quan sát được.

Tên test nên mô tả điều kiện và kết quả, ví dụ rejectsReservationWhenStockIsInsufficient. Tránh test chỉ có tên test1 hoặc kiểm tra nhiều quy tắc không liên quan trong cùng một phương thức.

Không nên mock mọi đối tượng. Với policy thuần và record dữ liệu, tạo instance thật thường đơn giản hơn. Dùng fake hoặc mock cho ranh giới như repository, HTTP client, clock, ID generator và cổng lưu trữ. Cách này giữ test gần với hành vi thực tế và giảm phụ thuộc vào chi tiết nội bộ của implementation.

## 11. Quy trình thực hành

Khi phát triển một hàm xử lý sự kiện mới, có thể thực hiện theo thứ tự sau:

1. Xác định dữ liệu nghiệp vụ cần có trong input và kết quả cần trả về.
2. Viết policy hoặc use case Java thuần, không tham chiếu API Spring hay broker.
3. Tạo test cho trường hợp thành công, từ chối, dữ liệu biên và đầu vào sai.
4. Tách thời gian, ID, repository và dịch vụ ngoài thành dependency có thể thay thế.
5. Viết Supplier hoặc Consumer adapter để đọc nguồn hoặc thực hiện tác động qua port.
6. Unit test adapter bằng fake hoặc mock để xác minh cách gọi dependency.
7. Đăng ký bean Supplier, Function hoặc Consumer và cấu hình function definition/binding.
8. Dùng Test Binder để kiểm tra payload và binding.
9. Dùng broker phù hợp để kiểm thử group, partition, retry, DLQ và hành vi giao nhận cần thiết.

Khi logic nghiệp vụ được kiểm chứng độc lập, thay đổi broker hoặc cấu hình binding ít ảnh hưởng đến các quy tắc đã kiểm thử. Đồng thời, khi một bài test thất bại, nhóm phát triển có thể xác định rõ vấn đề nằm ở quyết định nghiệp vụ, adapter hay lớp tích hợp thông điệp.
