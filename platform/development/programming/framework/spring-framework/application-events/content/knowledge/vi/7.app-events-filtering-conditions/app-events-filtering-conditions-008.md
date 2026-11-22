# Tránh điều kiện phức tạp trong listener (Spring Application Events)

## 1. Vấn đề cần giải quyết

Trong Spring Framework, `@EventListener` nhận một kiểu sự kiện và có thể khai báo `condition` bằng Spring Expression Language (SpEL) để chỉ chạy khi điều kiện đúng. Đây là cơ chế lọc hữu ích, nhưng biểu thức quá dài, truy vấn dữ liệu ngay trong biểu thức hoặc hàng loạt nhánh `if/else` bên trong listener sẽ khiến việc đọc, kiểm thử và bảo trì khó khăn.

Một listener tốt nên trả lời rõ ba câu hỏi: **Sự kiện nào liên quan?** (kiểu sự kiện), **khi nào cần xử lý?** (điều kiện đơn giản) và **xử lý điều gì?** (gọi nghiệp vụ có trách nhiệm rõ ràng). Tránh biến listener thành nơi chứa toàn bộ quy tắc nghiệp vụ.

Mặc định, Spring dùng `SimpleApplicationEventMulticaster` và gọi listener **đồng bộ trên luồng phát sự kiện**. Vì vậy, biểu thức kiểm tra tốn thời gian hoặc logic xử lý chậm có thể làm lời gọi `publishEvent(...)` chậm theo. Việc lọc đúng chỗ giúp giảm chi phí và làm rõ hành vi, nhưng không thay thế thiết kế xử lý bất đồng bộ khi thực sự cần.

## 2. Nhận diện điều kiện đang quá phức tạp

Những dấu hiệu thường gặp:

- `@EventListener(condition = "...")` chứa nhiều phép `&&`, `||`, nhánh lồng nhau, gọi chuỗi thuộc tính dài hoặc có `null` khó dự đoán.
- Biểu thức SpEL gọi bean để truy vấn cơ sở dữ liệu, gọi HTTP, kiểm tra quyền qua mạng hoặc làm thao tác có tác dụng phụ. Khi ấy chi phí và điểm lỗi bị giấu trong annotation.
- Một listener nhận sự kiện rất rộng rồi dùng nhiều `if/else` để phân biệt các loại nghiệp vụ không liên quan.
- Cùng một điều kiện nghiệp vụ được sao chép trong nhiều listener; thay đổi quy tắc phải sửa ở nhiều nơi.
- Thử nghiệm hành vi buộc phải khởi tạo cả Spring context chỉ để kiểm tra một biểu thức dài.

Không phải cứ nhiều điều kiện là sai. Vấn đề là **độ phức tạp, chi phí và trách nhiệm** của điều kiện có phù hợp với vị trí lọc sự kiện hay không.

## 3. Đặt mỗi loại điều kiện vào đúng chỗ

| Loại điều kiện | Cách tổ chức nên dùng | Lý do |
| --- | --- | --- |
| Chỉ quan tâm một loại sự kiện | Tham số có kiểu cụ thể, ví dụ `OrderPaidEvent` | Spring tự chọn listener phù hợp; không cần kiểm tra loại bằng tay |
| Một cờ hoặc giá trị đơn giản trên sự kiện | `@EventListener(condition = "#a0.receiptRequested()")` hoặc một `if` trả về sớm | Dễ đọc và ít chi phí |
| Quy tắc nghiệp vụ nhiều nhánh | Một lớp policy/service có phương thức đặt tên rõ, gọi từ thân listener | Dễ kiểm thử và tái sử dụng |
| Lọc cần dữ liệu từ DB/dịch vụ ngoài | Xử lý qua service có quản lý lỗi, thời gian và giao dịch; cân nhắc thời điểm phát sự kiện | Không giấu I/O trong SpEL |
| Nhiều hành động độc lập | Các listener theo trách nhiệm hoặc các event có ngữ nghĩa hẹp hơn | Giảm chuỗi `if/else` và sự phụ thuộc |

Với `condition`, Spring đánh giá biểu thức trên từng sự kiện có kiểu phù hợp trước khi gọi phương thức listener. `#a0` (tương đương `#p0`) là tham số thứ nhất; dùng cú pháp này không phụ thuộc vào tên tham số Java có được giữ trong bytecode hay không. `#root.event` tham chiếu đến đối tượng sự kiện gốc của Spring; với sự kiện là object thường được publish, tham số listener có thể là chính object đó. Tránh viết `#event` khi không có tham số tên `event` được cung cấp.

## 4. Ví dụ: lọc nhanh, đưa chính sách ra khỏi listener

Yêu cầu: Khi đơn hàng đã thanh toán, chỉ gửi biên nhận nếu khách yêu cầu và số tiền lớn hơn 0. Hai điều kiện có vai trò khác nhau:

1. `receiptRequested` là cờ đơn giản, có thể lọc ngay tại `@EventListener`.
2. `amountCents() > 0` là quy tắc nghiệp vụ minh họa, đặt trong `ReceiptPolicy` để kiểm thử độc lập.

Ví dụ sau là **một file Java 17+ hoàn chỉnh** chạy trong ứng dụng Spring Boot 3.x có phụ thuộc `spring-boot-starter`. Tạo file `src/main/java/example/events/EventFilterApplication.java`:

```java
package example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class EventFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventFilterApplication.class, args);
    }

    // Object sự kiện không bắt buộc kế thừa ApplicationEvent.
    public record OrderPaidEvent(
            String orderId,
            boolean receiptRequested,
            long amountCents) {
    }

    public static class ReceiptPolicy {
        public boolean canSend(OrderPaidEvent event) {
            return event.amountCents() > 0;
        }
    }

    public static class ReceiptListener {
        private final ReceiptPolicy policy;

        public ReceiptListener(ReceiptPolicy policy) {
            this.policy = policy;
        }

        // Bộ lọc đơn giản; không truy vấn DB hoặc gọi dịch vụ ngoài.
        @EventListener(condition = "#a0.receiptRequested()")
        public void onOrderPaid(OrderPaidEvent event) {
            if (!policy.canSend(event)) {
                return; // Guard clause: bỏ qua sự kiện không hợp lệ.
            }
            System.out.println("Gửi biên nhận: " + event.orderId());
        }
    }

    @Bean
    ReceiptPolicy receiptPolicy() {
        return new ReceiptPolicy();
    }

    @Bean
    ReceiptListener receiptListener(ReceiptPolicy policy) {
        return new ReceiptListener(policy);
    }

    @Bean
    CommandLineRunner publishSampleEvents(ApplicationEventPublisher publisher) {
        return args -> {
            publisher.publishEvent(new OrderPaidEvent("OD-101", true, 12000));
            publisher.publishEvent(new OrderPaidEvent("OD-102", false, 8000));
            publisher.publishEvent(new OrderPaidEvent("OD-103", true, 0));
        };
    }
}
```

Với module đã cấu hình Spring Boot Gradle plugin, chạy `./gradlew bootRun` (trên Windows có thể dùng `gradlew.bat bootRun`). Trong log khởi động sẽ có **duy nhất dòng do listener in ra**:

```text
Gửi biên nhận: OD-101
```

Giải thích luồng xử lý:

- `OD-101`: đúng kiểu event, `receiptRequested() == true` và `canSend(...) == true` nên in thông báo.
- `OD-102`: `condition` trả về `false`; Spring không gọi `onOrderPaid`.
- `OD-103`: `condition` đúng; listener được gọi nhưng `ReceiptPolicy` trả về `false` nên thoát sớm và không in.
- Ví dụ chỉ in ra console để dễ kiểm chứng; hệ thống thực tế có thể ủy quyền gửi biên nhận cho một service riêng, đồng thời xử lý lỗi và tránh gửi lặp.

Cú pháp `#a0.receiptRequested()` gọi trực tiếp accessor của Java record. Nếu dùng JavaBean thông thường có getter `getReceiptRequested()` hoặc `isReceiptRequested()`, có thể dùng truy cập thuộc tính SpEL tương ứng. Mỗi thay đổi về tên field/method cần được kiểm tra qua test vì chuỗi SpEL không được trình biên dịch Java kiểm tra như lời gọi phương thức trực tiếp.

## 5. Khi nào nên bỏ hẳn SpEL?

Khi toàn bộ điều kiện có thể thể hiện rõ bằng Java, có thể dùng `@EventListener` không `condition` rồi trả về sớm:

```java
@EventListener
public void onOrderPaid(OrderPaidEvent event) {
    if (!event.receiptRequested()) {
        return;
    }
    if (!policy.canSend(event)) {
        return;
    }
    System.out.println("Gửi biên nhận: " + event.orderId());
}
```

Đây là **đoạn thay thế phương thức** trong `ReceiptListener` ở ví dụ trên, không phải chương trình Java độc lập. Ưu điểm là điều kiện được Java kiểm tra kiểu và dễ debug. Đổi lại, listener vẫn được gọi rồi mới thực hiện kiểm tra cờ. Hãy chọn cách rõ ràng nhất cho nhóm: `condition` phù hợp với biểu thức nhỏ, còn `if`/guard clause phù hợp khi logic cần nhiều bước và kiểm thử trực tiếp.

Nếu đang viết một chuỗi `if (event instanceof ...)` cho các sự kiện khác nhau, hãy cân nhắc thiết kế các kiểu sự kiện cụ thể và tách listener theo chức năng trước khi thêm điều kiện.

## 6. Giới hạn về hiệu năng, giao dịch và lỗi

- **Đường đồng bộ:** Mặc định `publishEvent(...)` chờ listener đồng bộ hoàn tất. Việc gọi repository/API ngay trong `condition` hoặc thân listener vẫn tiêu tốn thời gian của luồng phát, cho dù kết quả cuối cùng là bỏ qua sự kiện.
- **Xử lý bất đồng bộ:** `@Async` có thể tách công việc nặng khỏi luồng phát, nhưng cần cấu hình async phù hợp; exception trong listener bất đồng bộ không tự trả về cho nơi gọi `publishEvent`. Ngữ cảnh giao dịch và `ThreadLocal` không mặc định được truyền sang luồng khác. Không dùng `@Async` chỉ để che giấu điều kiện lọc khó hiểu.
- **Sau khi commit:** Khi hành động chỉ được thực hiện sau một giao dịch thành công, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` theo đúng yêu cầu nhất quán dữ liệu. Annotation này giải quyết **thời điểm** nhận sự kiện, không tự đơn giản hóa policy; listener loại này có quy tắc riêng khi không có transaction đang hoạt động.
- **Lỗi trong điều kiện:** SpEL truy cập sai thuộc tính, gọi method trên đối tượng `null` hoặc gọi service ném lỗi có thể làm việc xử lý sự kiện thất bại. Điều kiện nên dựa trên dữ liệu sự kiện ổn định và tránh side effect.
- **Tính đúng đắn:** Listener phục vụ phản ứng với event; đừng đặt quy tắc bắt buộc để một giao dịch được phép thành công chỉ trong listener. Tác dụng phụ như gửi email cần thiết kế tránh xử lý trùng nếu sự kiện được phát lại hoặc tác vụ được retry.

## 7. Kiểm thử điều kiện ở hai mức

Đầu tiên, kiểm thử `ReceiptPolicy.canSend(...)` như một hàm Java thông thường, không cần khởi tạo Spring context. Sau đó, dùng integration test với Spring context để xác minh `@EventListener(condition = ...)` chọn đúng sự kiện.

| Dữ liệu | Có gọi phương thức listener? | Có thực hiện hành động? |
| --- | --- | --- |
| `receiptRequested=true`, `amountCents=12000` | Có | Có |
| `receiptRequested=false`, `amountCents=8000` | Không | Không |
| `receiptRequested=true`, `amountCents=0` | Có | Không |

Khi có thêm policy về khách hàng, quyền truy cập hoặc cấu hình, hãy kiểm thử policy bằng các trường hợp biên, dữ liệu thiếu và ngoại lệ; ở integration test chỉ cần kiểm tra điểm nối event → condition → listener → service. Để đánh giá hiệu năng, đo thời gian xử lý trong bối cảnh thực và số lần gọi I/O; không kết luận chỉ từ việc code trông ngắn hơn.

## 8. Checklist trước khi thêm điều kiện vào listener

1. Event đã có kiểu đủ cụ thể chưa, hay đang dùng một event chung rồi phân nhánh quá nhiều?
2. Biểu thức trong `condition` có thể hiểu trong vài giây, chỉ đọc dữ liệu ổn định và không có I/O không?
3. Quy tắc nghiệp vụ có tên rõ và được kiểm thử độc lập trong policy/service chưa?
4. Trường hợp không cần xử lý có thể thoát sớm mà không gây tác dụng phụ không?
5. Đã cân nhắc việc listener mặc định chạy đồng bộ, lỗi và giao dịch tác động đến publisher ra sao chưa?
6. Có test thể hiện cả đường chạy, đường bị lọc và đường policy từ chối chưa?

**Nguyên tắc thực hành:** Dùng **kiểu sự kiện** để lọc theo bản chất, **SpEL ngắn hoặc guard clause** để kiểm tra đơn giản, và **service/policy** để chứa quyết định nghiệp vụ. Mục tiêu là điều kiện dễ đọc, hành vi dễ kiểm chứng và chi phí xử lý được đặt ở nơi dễ kiểm soát.

*Tài liệu tham khảo:* [Spring Framework — ApplicationContext Events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
