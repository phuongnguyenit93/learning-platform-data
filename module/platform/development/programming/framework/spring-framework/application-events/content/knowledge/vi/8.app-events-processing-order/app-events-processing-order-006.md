# Thiết kế listener độc lập với thứ tự trong Spring Framework Application Events

## 1. Mục tiêu và bối cảnh

Khi một nghiệp vụ phát sinh sự kiện, nhiều thành phần có thể cùng phản ứng: tạo biên nhận, cập nhật thống kê, gửi thông báo hoặc lưu lịch sử. Trong Spring Framework, các listener gắn `@EventListener` có thể cùng nhận một event. Tuy nhiên, nếu listener B chỉ hoạt động khi listener A đã chạy trước và ghi dữ liệu trung gian, hệ thống có **phụ thuộc thứ tự ngầm**.

Thiết kế listener độc lập với thứ tự nghĩa là: với cùng một sự kiện hợp lệ, **mỗi listener đủ dữ liệu và quy tắc để xử lý đúng dù nó được gọi trước hay sau listener khác**. Kết quả không được phụ thuộc vào thứ tự đăng ký bean, `@Order` hoặc timing của các thread.

Ví dụ `OrderPlacedEvent` có hai consumer: một consumer tạo biên nhận, một consumer ghi chỉ số doanh thu. Cả hai phải hoạt động được theo thứ tự “biên nhận → thống kê” lẫn “thống kê → biên nhận”.

## 2. Hiểu đúng thứ tự gọi trong Spring

`ApplicationEventPublisher.publishEvent(event)` phát event đến các listener trong `ApplicationContext`. Với cấu hình mặc định, Spring thường dùng `SimpleApplicationEventMulticaster`, gọi listener **đồng bộ trong thread của publisher**.

- `@Order` có thể điều chỉnh **ưu tiên gọi** các listener (giá trị nhỏ ưu tiên trước). Nó không nên là hợp đồng bảo đảm tính đúng đắn nghiệp vụ.
- Khi một listener đồng bộ ném ngoại lệ, multicaster mặc định không có `ErrorHandler` có thể dừng đợt dispatch và truyền lỗi về publisher. Listener còn lại có thể chưa được gọi.
- Nếu sử dụng `@Async` hoặc một executor bất đồng bộ, thứ tự lập lịch không đồng nghĩa thứ tự hoàn thành; tác vụ có thể chồng lấn.
- `@Order` không tạo transaction riêng, không tự bổ sung retry, idempotency hay bảo đảm event được lưu để phát lại.

Như vậy, **độc lập về dữ liệu và logic** khác với **cách ly lỗi và thời gian chạy**. Cần thiết kế cả hai nếu một tác vụ thất bại không được ảnh hưởng tác vụ khác.

## 3. Nhận diện một thiết kế phụ thuộc thứ tự

Giả sử hai listener cùng nhận `OrderPlacedEvent` nhưng dùng dữ liệu chia sẻ:

```text
Listener A: tính số điểm thưởng; ghi sharedPoints[orderId] = points
Listener B: đọc sharedPoints[orderId]; dùng points để phát voucher
```

Nếu B chạy trước A, giá trị `points` không tồn tại. Gán `@Order(1)` cho A và `@Order(2)` cho B chỉ che giấu vấn đề ở trường hợp dispatch đồng bộ. Khi có xử lý song song, retry hoặc thay đổi cấu hình, phụ thuộc có thể làm sai nghiệp vụ.

Cần phân biệt hai trường hợp:

1. **Hai trách nhiệm thực sự độc lập:** A và B đều lấy đầu vào từ event bất biến hoặc nguồn dữ liệu đã commit; tự xử lý phần việc của mình. Không đọc cache tạm do listener khác tạo.
2. **Có quan hệ trước–sau thật sự:** đưa các bước vào một application service/workflow rõ ràng, hoặc phát sự kiện tiếp nối sau khi bước trước hoàn tất, chẳng hạn `OrderPlaced → PointsCalculated → VoucherIssued`. Event tiếp nối giúp biểu diễn phụ thuộc, nhưng cần cơ chế giao nhận đáng tin nếu không được phép mất bước.

## 4. Nguyên tắc thiết kế

### 4.1. Định nghĩa event là sự thật nghiệp vụ

Đặt tên theo điều **đã xảy ra** như `OrderPlacedEvent`, `PaymentConfirmedEvent`. Payload nên là snapshot bất biến chứa dữ liệu consumer thật sự cần: ID nghiệp vụ, `eventId` ổn định, số tiền, phiên bản hoặc thời điểm khi có ý nghĩa. Với Java 17+, `record` thuận tiện cho payload gồm giá trị bất biến.

Không đưa entity JPA còn lazy loading hoặc object mutable cho nhiều listener cùng chỉnh sửa. Nếu listener đọc lại DB qua `orderId`, phải xét xem dữ liệu đã commit chưa và có cần version cụ thể không.

### 4.2. Mỗi listener sở hữu side effect riêng

Listener tạo biên nhận quản lý bản ghi biên nhận; listener thống kê quản lý bản ghi thống kê. Không listener nào dựa vào dữ liệu tạm mà listener khác vừa lưu. Dùng chung một ID tương quan để log và theo dõi là hợp lý; dùng chung biến mutable để ra quyết định thì không.

### 4.3. Idempotency và giao trùng

Phải tính đến retry, ứng dụng restart hoặc cùng một sự kiện logic được gửi lại. Một listener đáng tin cần xử lý nhiều lần mà không tạo side effect sai:

- Với DB, dùng unique constraint trên khóa nghiệp vụ (ví dụ mỗi `orderId` có tối đa một biên nhận) hoặc trên `(consumerName, eventId)`; đặt việc ghi trạng thái đã xử lý và thay đổi dữ liệu nghiệp vụ trong cùng transaction.
- Với email/API ngoài, dùng idempotency key ở phía nhận khi có thể, hoặc dùng outbox/job để kiểm soát trạng thái, retry và xác nhận hoàn thành. Không đánh dấu “đã gửi thành công” trước khi nhận được kết quả đáng tin cậy.
- Khi retry cùng một event logic, giữ nguyên `eventId`. Tạo ID khác ở mỗi lần retry làm mất ý nghĩa khử trùng lặp theo event.

Idempotency không đồng nghĩa Spring application event tự có durable storage.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dùng Spring Context, không cần Spring Boot hay cơ sở dữ liệu. Hai listener chỉ đọc cùng một event bất biến rồi tạo hai kết quả khác nhau, không dùng `@Order`.

Cấu trúc:

```text
independent-listeners/
├── build.gradle
└── src/main/java/demo/IndependentListenersExample.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.IndependentListenersExample'
}
```

Nội dung `src/main/java/demo/IndependentListenersExample.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class IndependentListenersExample {

    public record OrderPlaced(String orderId, long totalCents) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ReceiptListener receiptListener() {
            return new ReceiptListener();
        }

        @Bean
        public MetricsListener metricsListener() {
            return new MetricsListener();
        }
    }

    public static class ReceiptListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("RECEIPT " + event.orderId());
        }
    }

    public static class MetricsListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "METRIC " + event.orderId() + " " + event.totalCents()
            );
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.publishEvent(new OrderPlaced("ORD-42", 19_900L));
        }
    }
}
```

Với JDK 17+ và Gradle được cài sẵn, chạy tại thư mục dự án:

```bash
gradle run --quiet
```

Hai dòng được in ra (thứ tự có thể thay đổi, không nên assert theo thứ tự):

```text
RECEIPT ORD-42
METRIC ORD-42 19900
```

`ReceiptListener` chỉ cần `orderId`; `MetricsListener` chỉ cần `orderId` và `totalCents`. Dù ai được gọi trước, nội dung từng dòng vẫn như nhau. `@Bean` đăng ký hai listener vào context, và Spring phát hiện các phương thức `@EventListener` trên bean tương ứng.

Đây là ví dụ **độc lập về logic**. Nếu thay `System.out.println` bằng lưu DB/gửi API, cần thêm transaction, retry và idempotency. Nếu một handler ném ngoại lệ, chế độ phát đồng bộ mặc định vẫn có thể ảnh hưởng handler còn lại.

## 6. Cách ly lỗi: đừng nhầm với độc lập thứ tự

`SimpleApplicationEventMulticaster` mặc định không tự bắt và bỏ qua mọi lỗi listener. Trong dispatch đồng bộ, lỗi runtime không được xử lý có thể lan về publisher và ngăn các listener sau chạy.

Chọn chính sách theo tính chất tác vụ:

- **Tác vụ phụ có thể retry:** đặt xử lý lỗi tại service phụ trách, ghi log/metric với `eventId`, lên lịch retry và cảnh báo nếu retry hết. Không nuốt lỗi rồi báo thành công giả.
- **Muốn multicaster tiếp tục gọi consumer khác sau lỗi:** cân nhắc cấu hình `SimpleApplicationEventMulticaster.setErrorHandler(...)`; phải hiểu rằng suppress exception có thể khiến caller không biết một consumer thất bại, do đó cần giám sát và khôi phục riêng.
- **Tác vụ có thể xử lý sau:** dùng `@Async` cùng `@EnableAsync` và executor được quản lý, hoặc chuyển sang hàng đợi bền vững nếu cần. Listener bất đồng bộ không bảo đảm hoàn thành trước khi `publishEvent` trả về; ngoại lệ không được truyền về caller theo cùng cách listener đồng bộ. Cần cơ chế xử lý `AsyncUncaughtExceptionHandler` hoặc theo dõi lỗi phù hợp.
- **Nhiều bước phải thành công cùng nhau:** thực hiện orchestration/transaction có chủ đích. Fan-out sự kiện đơn thuần không phải cơ chế điều phối atomic.

Độ chậm của listener cũng là một dạng coupling khi dùng dispatch đồng bộ: listener chạy lâu có thể giữ thread publisher. Tách trách nhiệm xử lý và chọn executor theo yêu cầu thực tế.

## 7. Transaction và thời điểm xử lý

Nếu publisher phát sự kiện trong một `@Transactional` service, listener `@EventListener` đồng bộ thông thường có thể chạy **trước khi transaction commit**. Việc gửi email hoặc gọi hệ thống ngoài lúc ấy có nguy cơ tạo side effect dù giao dịch gốc rollback.

Khi tác vụ chỉ được phép bắt đầu sau commit, dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. `AFTER_COMMIT` là phase mặc định của annotation này. Nếu không có transaction đang hoạt động, listener **không được gọi**, trừ khi dùng `fallbackExecution = true`.

Ví dụ dưới đây là phương thức minh họa bên trong Spring-managed bean, giả định ứng dụng đã định nghĩa `OrderPlacedEvent` và `receiptJobService`:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void enqueueReceipt(OrderPlacedEvent event) {
    receiptJobService.enqueue(event.orderId());
}
```

Cơ chế `AFTER_COMMIT` giải quyết **thời điểm**, không bảo đảm tiến trình không mất event nếu ứng dụng chết sau commit nhưng trước khi side effect hoàn tất. Nếu listener sau commit cần tạo bản ghi DB mới, hãy dùng transaction mới phù hợp (chẳng hạn service gọi qua proxy với `REQUIRES_NEW`), không giả định transaction vừa commit vẫn ghi tiếp một cách an toàn.

Khi cần bảo đảm event tồn tại qua restart, xem xét **transactional outbox**: lưu outbox cùng transaction với dữ liệu nghiệp vụ, một worker chuyển bản ghi ra broker/consumer, phía nhận idempotent và có retry/monitoring. Application events thông thường chỉ là phát sự kiện trong application context; không phải durable broker.

## 8. Kiểm thử đúng thuộc tính độc lập

Không kiểm thử bằng điều kiện “dòng RECEIPT luôn phải xuất hiện trước METRIC”. Hãy kiểm thử kết quả nghiệp vụ dưới các thứ tự và chế độ thực thi khác nhau.

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Đảo thứ tự | Gọi hai handler/service theo A→B và B→A trên hai trạng thái khởi tạo tương đương | Kết quả cuối giống nhau; không cần dữ liệu tạm từ handler kia |
| Giao trùng | Xử lý cùng `eventId` hai lần | Không tạo thêm bản ghi/side effect không hợp lệ |
| Một listener lỗi | Cho một service ném lỗi và chạy với chính sách xử lý lỗi đã chọn | Có log/retry phù hợp; mức cách ly của listener còn lại đúng theo thiết kế |
| Giao dịch rollback | Publish trong transaction rollback và kiểm tra listener `AFTER_COMMIT` | Không chạy tác vụ chỉ dành cho sau commit |
| Chạy bất đồng bộ | Chủ động làm thay đổi thứ tự hoàn thành, chờ bằng synchronization test | Kết quả cuối đúng; không phụ thuộc thời gian sleep tùy ý |

Tách logic nghiệp vụ thành service có thể gọi trực tiếp để kiểm thử hoán đổi thứ tự. Integration test với `ApplicationContext` xác nhận đăng ký và dispatch sự kiện; test DB/API xác minh ràng buộc idempotency, transaction và retry thực sự.

## 9. Sai lầm thường gặp

1. **Dùng `@Order` để biến một dependency nghiệp vụ thành may mắn về timing.** Nếu B cần đầu ra A, hãy biểu diễn bước A→B rõ ràng.
2. **Cho nhiều listener cùng sửa object mutable hoặc cache chung.** Đây là nguồn phụ thuộc ngầm và race condition.
3. **Tin rằng mỗi listener chắc chắn được gọi dù listener khác ném lỗi.** Multicaster đồng bộ mặc định có thể dừng dispatch.
4. **Tin rằng `@Async` bảo đảm độc lập.** Thứ tự hoàn thành càng khó dự đoán; cần error handling, executor và observability.
5. **Gửi side effect bên ngoài trước commit.** Giao dịch gốc có thể rollback sau khi email đã gửi.
6. **Coi `@TransactionalEventListener` là queue bền vững.** Annotation này chỉ ràng buộc thời điểm với transaction.
7. **Khử trùng lặp bằng Map trong RAM.** Restart hoặc nhiều instance làm mất hoặc phân tán trạng thái.
8. **Test thứ tự log thay cho trạng thái nghiệp vụ.** Test kiểu này dễ qua trong môi trường này và thất bại ở môi trường khác.

## 10. Checklist review

- Mỗi listener có thể chạy trước listener khác mà vẫn tạo kết quả đúng không?
- Dữ liệu đầu vào có đến từ event bất biến hoặc nguồn đã commit với phiên bản phù hợp không?
- Listener có dùng side effect của listener khác làm điều kiện tiếp tục không?
- Có khóa idempotency, transaction và retry tương xứng với từng side effect không?
- Đã xác định hành vi khi một listener lỗi, chậm hoặc hoàn thành sau các listener khác chưa?
- Với event sau commit/bất đồng bộ, đã xét thread context, độ bền và khả năng mất event chưa?
- Test có bao phủ đảo thứ tự, duplicate, lỗi, rollback và async khi áp dụng không?

**Nguyên tắc ghi nhớ:** nhiều listener cùng nghe một sự thật nghiệp vụ phải là các consumer tự chủ. Nếu có bước phải chờ kết quả bước khác, hãy mô hình hóa luồng đó công khai và kiểm soát lỗi/khôi phục của nó.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events, @EventListener, @Order và @Async](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
