# Event lồng nhau và dữ liệu dẫn xuất

## Mục tiêu

Sau bài này, bạn có thể mô tả cách một listener phát thêm event trong khi đang xử lý event khác, phân biệt event lồng nhau với event dẫn xuất từ giá trị trả về của @EventListener, dự đoán thứ tự thực thi khi phân phối đồng bộ, và thiết kế chuỗi event tránh vòng lặp hoặc phụ thuộc ngầm.

## 1. Event lồng nhau là gì?

Một event lồng nhau (nested event) xuất hiện khi listener đang xử lý một event lại phát thêm event khác thông qua ApplicationEventPublisher.

Ví dụ, khi nhận OrderPlaced, listener có thể phát OrderAuditRecorded để yêu cầu một listener khác ghi nhận lịch sử. Event thứ hai được phát trong lúc event đầu tiên vẫn đang được xử lý.

Hai event có ý nghĩa khác nhau:

- OrderPlaced thông báo rằng đơn hàng đã được tạo.
- OrderAuditRecorded thông báo rằng một bản ghi audit đã được tạo hoặc cần được xử lý.

Event thứ hai không thay thế event đầu tiên. Nó mô tả một sự việc tiếp theo trong chuỗi nghiệp vụ.

Publisher ban đầu không cần biết chuỗi phản ứng này. Nó chỉ phát OrderPlaced. Listener nhận event có thể phát thêm event nếu việc đó thuộc trách nhiệm của nó.

## 2. Luồng xử lý khi listener phát event mới

Với cấu hình mặc định, SimpleApplicationEventMulticaster gọi listener đồng bộ trong luồng đang phát event. Khi listener gọi publishEvent lần nữa, lần publish thứ hai được xử lý ngay trong lời gọi hiện tại.

Ví dụ trình tự:

~~~text
Publisher phát OrderPlaced
        |
        v
OrderPlacedListener bắt đầu xử lý
        |
        | publishEvent(OrderAuditRecorded)
        v
ApplicationContext phân phối OrderAuditRecorded
        |
        v
AuditListener xử lý xong
        |
        v
Quay lại OrderPlacedListener
        |
        v
OrderPlacedListener tiếp tục và kết thúc
~~~

Đây là luồng gọi lồng nhau theo kiểu đồng bộ. AuditListener được gọi trước khi lời gọi publishEvent(OrderAuditRecorded) trả về; sau đó OrderPlacedListener mới tiếp tục dòng lệnh tiếp theo.

Nếu một listener khác cũng nhận OrderPlaced, thứ tự giữa các listener cùng nhận event được điều khiển bằng Ordered hoặc @Order. Với event lồng nhau, listener của event con có thể chạy ngay giữa quá trình xử lý listener của event cha. Vì vậy, không nên suy luận thứ tự toàn cục chỉ từ thứ tự khai báo bean.

### Phân biệt hai thời điểm

- **Event cha được phát**: publisher bắt đầu phân phối OrderPlaced.
- **Event con được phát**: listener của OrderPlaced gọi publishEvent cho OrderAuditRecorded.

Event cha chưa nhất thiết đã hoàn tất toàn bộ quá trình phân phối khi event con được phát. Một listener của event cha có thể còn tiếp tục chạy sau khi event con đã xử lý xong.

## 3. Dữ liệu dẫn xuất là gì?

Dữ liệu dẫn xuất (derived data) là dữ liệu được tính toán hoặc tổng hợp từ dữ liệu của event trước đó để mô tả một kết quả hoặc nhu cầu xử lý tiếp theo.

Ví dụ, OrderPlaced chứa mã đơn hàng và tiền hàng. Listener có thể tính thuế, tổng thanh toán và phát InvoicePreparationRequested với các giá trị đã tính:

~~~java
BigDecimal tax = subtotal.multiply(new BigDecimal("0.10"));
BigDecimal grandTotal = subtotal.add(tax);

return new InvoicePreparationRequested(
        orderId, subtotal, tax, grandTotal);
~~~

Payload của event mới là một snapshot có ý nghĩa nghiệp vụ. Listener nhận event mới không phải tự tính lại cùng công thức hoặc đọc toàn bộ đối tượng của event cũ.

Một event dẫn xuất nên trả lời được ba câu hỏi:

1. Sự việc nào vừa xảy ra hoặc kết quả nào đã được tạo?
2. Dữ liệu tối thiểu nào cần thiết để listener tiếp theo xử lý?
3. Dữ liệu này là snapshot tại thời điểm phát event hay chỉ là định danh để tra cứu trạng thái mới nhất?

Phải chọn rõ ý nghĩa snapshot. Nếu event mang grandTotal đã tính tại thời điểm tạo đơn, listener nên hiểu đó là tổng tiền được ghi nhận tại thời điểm đó. Nếu listener cần trạng thái mới nhất, payload có thể chỉ mang orderId và đọc lại dữ liệu qua service phù hợp.

## 4. Hai cách phát event tiếp theo

Spring hỗ trợ hai cách thường gặp để tạo chuỗi event.

### Cách 1: Gọi publishEvent tường minh

Listener inject ApplicationEventPublisher rồi phát event mới khi cần:

~~~java
@Component
class OrderPlacedListener {

    private final ApplicationEventPublisher publisher;

    OrderPlacedListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    void handle(OrderPlaced event) {
        // Xử lý nghiệp vụ của event hiện tại
        publisher.publishEvent(
                new OrderAuditRecorded(event.orderId()));
    }
}
~~~

Cách này phù hợp khi:

- Listener cần phát nhiều event ở các nhánh điều kiện khác nhau.
- Event mới chỉ được phát sau khi một bước xử lý cụ thể thành công.
- Cần phát event từ callback hoặc một vị trí không thể biểu diễn bằng giá trị trả về.
- Cần thể hiện rõ thời điểm phát event mới trong luồng xử lý.

Lời gọi publishEvent tường minh giúp người đọc thấy chính xác event mới được phát ở dòng nào.

### Cách 2: Trả về event từ @EventListener

Một phương thức @EventListener có thể trả về một đối tượng event. Spring tự động publish giá trị trả về sau khi phương thức listener hoàn tất:

~~~java
@EventListener
InvoicePreparationRequested prepareInvoice(OrderPlaced event) {
    BigDecimal tax = event.subtotal()
            .multiply(new BigDecimal("0.10"));

    BigDecimal total = event.subtotal().add(tax);

    return new InvoicePreparationRequested(
            event.orderId(), event.subtotal(), tax, total);
}
~~~

Cách này phù hợp khi một listener xử lý một event và tạo ra đúng một event dẫn xuất như kết quả trực tiếp của xử lý đó.

Nếu phương thức trả về một array hoặc Collection, Spring publish từng phần tử như một event riêng. Nếu phương thức trả về void, Spring không tạo event dẫn xuất từ giá trị trả về.

**Lưu ý:** Mọi giá trị trả về khác void từ phương thức @EventListener đều được xem là event tiếp theo. Không nên trả về String, boolean hoặc một DTO chỉ để tiện kiểm tra kết quả nếu không muốn Spring publish nó.

### So sánh

| Tiêu chí | publishEvent tường minh | Giá trị trả về |
|---|---|---|
| Thời điểm phát | Ngay tại dòng gọi publishEvent | Sau khi phương thức listener trả về |
| Nhiều event | Có thể phát nhiều lần, theo nhánh | Có thể trả về Collection hoặc array |
| Điều kiện | Viết trực tiếp trong luồng xử lý | Dùng if trước khi return |
| Độ rõ ràng | Thấy rõ lệnh phát event | Thể hiện event mới là kết quả xử lý |
| Async listener | Có thể inject publisher và phát tường minh | Không hỗ trợ follow-up event qua giá trị trả về |

Với listener bất đồng bộ, không dùng giá trị trả về để phát event tiếp theo. Nếu cần phát event từ listener chạy async, hãy inject ApplicationEventPublisher và gọi publishEvent tường minh trong listener.

## 5. Ví dụ hoàn chỉnh: phát event lồng nhau và event dẫn xuất

Ví dụ sau minh họa hai kiểu nối chuỗi trong cùng một luồng:

1. OrderPlacedListener nhận OrderPlaced.
2. Listener phát OrderAuditRecorded tường minh. AuditListener xử lý ngay.
3. OrderPlacedListener tiếp tục tính thuế và tổng tiền.
4. Listener trả về InvoicePreparationRequested. Spring publish event dẫn xuất sau khi phương thức kết thúc.
5. InvoiceListener nhận dữ liệu đã tính.

### Cấu trúc dự án

~~~text
nested-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── NestedEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.NestedEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### NestedEventsDemo.java

~~~java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = NestedEventsDemo.class)
public class NestedEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             NestedEventsDemo.class)) {
            context.publishEvent(
                    new OrderPlaced("DH-4101",
                            new BigDecimal("350000.00")));
            System.out.println("Main: publishEvent returned");
        }
    }
}

record OrderPlaced(String orderId, BigDecimal subtotal) {
}

record OrderAuditRecorded(String orderId, String action) {
}

record InvoicePreparationRequested(
        String orderId,
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal grandTotal) {
}

@Component
class OrderPlacedListener {

    private final ApplicationEventPublisher publisher;

    OrderPlacedListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    InvoicePreparationRequested handle(OrderPlaced event) {
        System.out.println("1. OrderPlaced: start " + event.orderId());

        publisher.publishEvent(
                new OrderAuditRecorded(event.orderId(), "ORDER_PLACED"));

        System.out.println("3. OrderPlaced: continue after nested event");

        BigDecimal tax = event.subtotal()
                .multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal grandTotal = event.subtotal().add(tax);

        return new InvoicePreparationRequested(
                event.orderId(), event.subtotal(), tax, grandTotal);
    }
}

@Component
class AuditListener {

    @EventListener
    void record(OrderAuditRecorded event) {
        System.out.println(
                "2. Nested audit event: " + event.orderId()
                        + ", action=" + event.action());
    }
}

@Component
class InvoiceListener {

    @EventListener
    void prepare(InvoicePreparationRequested event) {
        System.out.println(
                "4. Derived invoice event: " + event.orderId()
                        + ", tax=" + event.tax().toPlainString()
                        + ", total=" + event.grandTotal().toPlainString());
    }
}
~~~

### Chạy chương trình

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Kết quả:

~~~text
1. OrderPlaced: start DH-4101
2. Nested audit event: DH-4101, action=ORDER_PLACED
3. OrderPlaced: continue after nested event
4. Derived invoice event: DH-4101, tax=35000.00, total=385000.00
Main: publishEvent returned
~~~

### Phân tích kết quả

- Dòng 1 xuất hiện khi listener bắt đầu xử lý OrderPlaced.
- Dòng 2 xuất hiện trước dòng 3 vì publishEvent(OrderAuditRecorded) được gọi đồng bộ bên trong listener. AuditListener hoàn tất rồi lời gọi mới quay về.
- Dòng 3 xác nhận listener cha tiếp tục sau khi event lồng nhau đã được xử lý.
- Dòng 4 xuất hiện sau khi phương thức handle trả về InvoicePreparationRequested. Spring nhận giá trị trả về và publish nó như event mới.
- Dòng cuối xuất hiện khi toàn bộ listener đồng bộ của event gốc và các event dẫn xuất đã hoàn tất.

Ví dụ dùng hai cách phát event trong cùng một listener để làm rõ thời điểm. Trong ứng dụng thực tế, nên chọn cách đơn giản nhất phù hợp với luồng nghiệp vụ.

## 6. Thiết kế payload cho event dẫn xuất

Event dẫn xuất nên mô tả một sự việc hoặc kết quả có ý nghĩa độc lập. Đừng chỉ đổi tên event cũ mà giữ nguyên toàn bộ dữ liệu không cần thiết.

### Mang dữ liệu snapshot

Ví dụ InvoicePreparationRequested mang subtotal, tax và grandTotal. Listener tiếp theo có thể xử lý đúng kết quả đã tính mà không phải chạy lại công thức.

Cách này phù hợp khi các giá trị phải nhất quán với thời điểm event được tạo. Nên dùng BigDecimal cho tiền tệ và xác định rõ scale, rounding mode theo quy tắc nghiệp vụ.

### Chỉ mang định danh

Một event khác có thể chỉ mang orderId:

~~~java
record OrderSearchIndexUpdateRequested(String orderId) {
}
~~~

Listener dùng orderId để tải dữ liệu hiện tại qua service hoặc repository. Cách này tránh sao chép một aggregate lớn vào event và phù hợp khi listener cần trạng thái mới nhất.

Đổi lại, dữ liệu có thể đã thay đổi kể từ lúc event được phát. Nếu cần xử lý đúng snapshot ban đầu, chỉ mang ID là chưa đủ.

### Mang metadata để theo dõi chuỗi

Với chuỗi event dài, có thể thêm metadata như:

- eventId: định danh duy nhất của event.
- correlationId: định danh chung cho toàn bộ một luồng nghiệp vụ.
- causationId: event trực tiếp tạo ra event hiện tại.
- occurredAt: thời điểm sự việc xảy ra.

Metadata giúp log, tracing và điều tra khi một event tạo ra nhiều event khác. Không nên nhầm correlationId với eventId: nhiều event có thể cùng correlationId nhưng mỗi event vẫn có eventId riêng.

Không bắt buộc mọi bài toán đều cần một lớp EventEnvelope riêng. Chỉ bổ sung metadata khi có nhu cầu quan sát, đối soát hoặc xử lý trùng lặp rõ ràng.

## 7. Tránh vòng lặp và chuỗi event khó kiểm soát

Event lồng nhau có thể tạo vòng lặp nếu các listener phát event qua lại:

~~~text
OrderPlaced
   |
   v
OrderAuditRecorded
   |
   v
OrderPlaced
   |
   v
OrderAuditRecorded
   |
   +---- lặp vô hạn
~~~

Với phân phối đồng bộ, vòng lặp có thể tạo đệ quy sâu, lặp tác dụng phụ hoặc cuối cùng gây StackOverflowError.

Một số nguyên tắc để tránh:

1. Xác định rõ event nào là kết quả của event nào. Tránh để listener của event dẫn xuất phát ngược lại event cha mà không có điều kiện kết thúc.
2. Dùng tên event mô tả sự việc cụ thể, tránh tên chung như DataChanged nếu không có ngữ cảnh.
3. Nếu cần chống xử lý trùng, dùng eventId hoặc business key và thiết kế listener idempotent.
4. Nếu cần giới hạn số bước, biểu diễn trạng thái hoặc bước xử lý rõ ràng thay vì dựa vào việc listener tự dừng.
5. Giữ chuỗi event ngắn. Khi có nhiều nhánh, điều kiện, retry hoặc trạng thái chờ, cân nhắc một workflow/orchestrator rõ ràng.

Idempotency là khả năng xử lý cùng một yêu cầu nhiều lần mà không tạo ra tác dụng phụ lặp ngoài ý muốn. Ví dụ, ghi audit có thể dùng eventId làm khóa duy nhất; gửi hóa đơn cần có business key để tránh tạo hai hóa đơn cho cùng một đơn hàng.

## 8. Thứ tự, transaction và xử lý bất đồng bộ

### Thứ tự khi chạy đồng bộ

Mặc định, listener của SimpleApplicationEventMulticaster chạy đồng bộ. Nested publish vì vậy tạo lời gọi lồng nhau và event con thường hoàn tất trước khi listener cha tiếp tục.

@Order điều khiển thứ tự giữa các listener cùng phù hợp với một event. Nó không thay đổi vị trí dòng lệnh publishEvent trong listener và không tạo thứ tự tổng thể cho mọi event trong chuỗi.

### Khi dùng @Async hoặc executor

Nếu listener chạy bất đồng bộ, publisher không nhất thiết đợi listener hoàn tất. Nested event có thể được xử lý trên thread khác và thứ tự quan sát log có thể thay đổi.

Một số hệ quả:

- Không giả định event con luôn hoàn tất trước khi listener cha kết thúc.
- Exception từ listener async không truyền ngược về luồng publisher theo cách đồng bộ.
- ThreadLocal, transaction context và logging context không tự được truyền sang thread khác.
- Phải cấu hình cách ghi nhận lỗi, retry và giới hạn executor phù hợp.

Đặc biệt, phương thức @EventListener bất đồng bộ không hỗ trợ publish follow-up event thông qua giá trị trả về. Nếu cần phát event từ listener chạy async, hãy inject ApplicationEventPublisher và gọi publishEvent tường minh trong listener.

### Khi có transaction

Một event được publish bên trong transaction và được xử lý bởi listener đồng bộ thông thường có thể được xử lý trước khi transaction commit. Event lồng nhau cũng không tự chuyển sang sau commit.

Nếu listener chỉ được phép chạy sau khi transaction commit, dùng @TransactionalEventListener với phase phù hợp, thường là AFTER_COMMIT:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void afterOrderCommitted(OrderPlaced event) {
    // Xử lý sau khi transaction commit
}
~~~

Nếu không có transaction đang hoạt động, listener này không được gọi theo mặc định. Chỉ bật fallbackExecution khi đã xác định rõ hành vi mong muốn.

Nếu cần bảo đảm event được lưu bền vững cùng thay đổi dữ liệu và có thể gửi lại sau sự cố, hãy thiết kế transactional outbox hoặc giải pháp tương đương. Application Events tự nó không cung cấp bảo đảm giao nhận bền vững.

## 9. Xử lý lỗi trong chuỗi event

Với listener đồng bộ mặc định, exception runtime từ listener event con có thể truyền ngược qua lời gọi publishEvent trong listener cha. Khi đó listener cha có thể không chạy tiếp đến phần tính toán hoặc trả về event dẫn xuất.

Cần quyết định rõ ranh giới lỗi:

- Nếu ghi audit là bắt buộc để hoàn thành nghiệp vụ, lỗi audit có thể cần làm luồng cha thất bại.
- Nếu gửi email chỉ là tác vụ phụ, có thể cần tách xử lý lỗi, retry hoặc đưa tác vụ vào hàng đợi riêng.
- Không bắt exception rồi bỏ qua nếu điều đó khiến trạng thái hệ thống sai mà không có log hoặc cơ chế bù trừ.

Nếu cấu hình ErrorHandler cho multicaster, hành vi lỗi có thể khác với mặc định. Hãy kiểm tra cấu hình thực tế trước khi dựa vào việc exception truyền ngược hay được xử lý tại chỗ.

Một listener không nên phát event báo thành công trước khi thao tác mà event đó mô tả thực sự thành công. Ví dụ, chỉ phát InvoiceCreated sau khi hóa đơn đã được tạo theo đúng quy tắc nghiệp vụ.

## 10. Khi nào nên dùng event dẫn xuất, khi nào nên điều phối trực tiếp?

Dùng event dẫn xuất khi:

- Kết quả xử lý hiện tại là một sự kiện độc lập mà nhiều thành phần có thể quan tâm.
- Listener tiếp theo không cần trả kết quả bắt buộc cho listener trước.
- Có thể chấp nhận việc các listener phản ứng độc lập theo hợp đồng event.
- Muốn bổ sung một phản ứng mới mà không sửa publisher ban đầu.

Dùng lời gọi service trực tiếp hoặc workflow khi:

- Bước sau bắt buộc phải thành công thì bước trước mới được xem là hoàn tất.
- Cần trả kết quả từ bước sau để quyết định nghiệp vụ tiếp theo.
- Cần transaction nguyên tử bao trùm nhiều bước.
- Chuỗi xử lý có nhiều nhánh, trạng thái chờ, retry hoặc bù trừ.
- Thứ tự giữa các bước là một phần cốt lõi của nghiệp vụ.

Event giúp tách các phản ứng; nó không thay thế mọi hình thức điều phối. Nếu người đọc phải lần qua quá nhiều listener mới hiểu được một nghiệp vụ bắt buộc, một service điều phối rõ ràng có thể dễ bảo trì hơn.

## 11. Các lỗi thường gặp

### Phát event mới trước khi nghiệp vụ cha thành công

Nếu listener phát InvoiceCreated trước khi lưu hóa đơn hoàn tất, tên event không còn phản ánh đúng sự thật. Chỉ phát event sau khi điều kiện thành công của nghiệp vụ đã đạt.

### Vô tình publish giá trị trả về

Một phương thức @EventListener trả về DTO hoặc String cũng làm Spring xem giá trị đó là event. Dùng void nếu không muốn phát event dẫn xuất.

### Dùng return value trong listener async

Giá trị trả về của async listener không được dùng để phát event tiếp theo. Hãy publish tường minh bằng ApplicationEventPublisher.

### Chia sẻ đối tượng mutable giữa các event

Nếu event cha và event con cùng giữ một object mutable, listener có thể quan sát dữ liệu đã bị thay đổi. Ưu tiên record và payload bất biến.

### Dựa vào thứ tự ngầm giữa listener

@Order chỉ điều khiển thứ tự listener cho cùng event. Không dùng nó như một workflow engine hoặc cơ chế đồng bộ transaction.

### Không có cơ chế chống lặp

Nếu event có thể được phát nhiều lần hoặc listener có thể retry, tác dụng phụ như tạo hóa đơn hoặc gửi thông báo cần có khóa chống trùng hoặc cơ chế idempotent.

## 12. Ghi nhớ

Event lồng nhau xảy ra khi listener phát thêm event trong lúc đang xử lý event khác. Với multicaster đồng bộ mặc định, listener của event con chạy ngay trong lời gọi lồng nhau; sau khi xử lý xong, listener cha mới tiếp tục.

Event dẫn xuất có thể được phát tường minh bằng ApplicationEventPublisher hoặc được tạo từ giá trị trả về của @EventListener. Giá trị trả về chỉ phù hợp khi event mới là kết quả trực tiếp của listener; async listener cần publish tường minh.

Payload event nên thể hiện rõ snapshot hoặc định danh, tránh chia sẻ dữ liệu mutable và nên có metadata theo dõi khi chuỗi xử lý dài. Hãy ngăn vòng lặp, thiết kế idempotency, hiểu ranh giới transaction và async, và dùng service/workflow khi cần điều phối nghiệp vụ có tính bắt buộc.

## Tài liệu tham khảo chính thức

- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [ApplicationEventPublisher — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [SimpleApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [TransactionalEventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
