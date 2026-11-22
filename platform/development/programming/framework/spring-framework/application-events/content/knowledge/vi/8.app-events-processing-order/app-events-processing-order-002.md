# Ordered và mức ưu tiên của Application Event Listener trong Spring Framework

## 1. Mục tiêu

Khi một sự kiện được phát bằng `ApplicationEventPublisher.publishEvent(...)`, nhiều listener có thể cùng nhận sự kiện đó. Spring cho phép đặt mức ưu tiên để xác định **listener nào được gọi trước** trong quá trình phân phối sự kiện. Sau bài này, bạn có thể:

- Giải thích quy tắc **giá trị order càng nhỏ, độ ưu tiên càng cao**.
- Dùng `@Order` cho phương thức `@EventListener` và `Ordered#getOrder()` cho listener dạng `ApplicationListener`.
- Kiểm chứng thứ tự thực thi trong ứng dụng Spring chạy đồng bộ.
- Phân biệt **thứ tự gọi listener** với **thứ tự hoàn tất**, đặc biệt khi dùng `@Async` hoặc listener gắn với transaction.
- Nhận diện khi nào không nên biến mức ưu tiên thành một cơ chế phụ thuộc nghiệp vụ.

## 2. Spring sắp thứ tự listener ở đâu?

Luồng cơ bản:

1. Một bean gọi `publisher.publishEvent(event)`.
2. `ApplicationEventMulticaster` tìm các listener phù hợp với loại sự kiện.
3. Các listener được sắp theo thông tin order.
4. Multicaster lần lượt **gọi/điều phối** các listener theo thứ tự đó.

Với cơ chế mặc định `SimpleApplicationEventMulticaster`, các listener thông thường chạy **đồng bộ trên luồng phát sự kiện**. Vì vậy, nếu listener A hoàn tất trước khi multicaster gọi listener B thì ta quan sát được thứ tự rõ ràng. Lệnh `publishEvent(...)` thường chỉ trả về sau khi các listener đồng bộ đã xử lý xong. Nếu một listener xử lý lâu, nơi phát sự kiện cũng phải chờ.

Điều kiện quan trọng: **Chỉ so sánh thứ tự giữa các listener thực sự đủ điều kiện xử lý cùng một sự kiện**. `@Order` không khiến listener nhận sự kiện sai loại, không sắp thứ tự giữa hai lần `publishEvent` độc lập và không thay thế transaction hay workflow engine.

## 3. Quy tắc số thứ tự của `Ordered`

Trong Spring, giao diện `org.springframework.core.Ordered` quy định phương thức `int getOrder()`; annotation `org.springframework.core.annotation.Order` dùng cùng quy tắc giá trị.

| Giá trị | Mức ưu tiên tương đối | Ví dụ |
| --- | --- | --- |
| `-100` | Rất cao | Kiểm tra điều kiện tiền đề |
| `-10` | Cao hơn `0` | Chuẩn hóa dữ liệu |
| `0` | Cao hơn `10` | Ghi audit nội bộ |
| `10` | Thấp hơn `0` | Cập nhật một phần hiển thị |
| `Ordered.LOWEST_PRECEDENCE` | Ưu tiên thấp mặc định | Listener không khai báo order |

- **Số nhỏ được xếp trước số lớn**: `@Order(-10)` trước `@Order(0)` trước `@Order(10)`.
- Số âm hợp lệ; **không cần đánh số liên tiếp**. Bạn có thể dành khoảng cách `-100`, `0`, `100` để dễ thêm listener về sau.
- `Ordered.HIGHEST_PRECEDENCE` bằng `Integer.MIN_VALUE`; `Ordered.LOWEST_PRECEDENCE` bằng `Integer.MAX_VALUE`.
- Listener không cung cấp thông tin order thường được coi như có mức `LOWEST_PRECEDENCE`.
- **Không dựa vào thứ tự ổn định khi hai listener có cùng order**. Thứ tự quan sát được trong một cấu hình cụ thể không phải hợp đồng nghiệp vụ để phụ thuộc lâu dài.

Một giá trị nhỏ thể hiện **độ ưu tiên khi sắp xếp**, không có nghĩa listener được chạy trên CPU ưu tiên hơn, được cấp luồng riêng hay được xử lý thành công hơn.

## 4. Cách 1: `@Order` trên phương thức `@EventListener`

Với listener khai báo qua annotation, cách trực quan nhất là đặt `@Order` **trên chính phương thức nhận sự kiện**.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class AccountEventHandlers {

    @EventListener
    @Order(-20)
    public void validate(AccountCreatedEvent event) {
        // Được gọi trước listener có @Order(0) cho cùng sự kiện.
    }

    @EventListener
    @Order(0)
    public void recordAudit(AccountCreatedEvent event) {
        // Được gọi sau validate trong cách phân phối đồng bộ.
    }
}
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập: `AccountCreatedEvent` phải được định nghĩa và `AccountEventHandlers` phải được đăng ký thành bean Spring. Ví dụ chạy đầy đủ ở mục 6.

Khi một class có nhiều phương thức `@EventListener`, gắn order trực tiếp lên từng phương thức giúp người đọc thấy rõ mức ưu tiên riêng. Hãy import `@Order` của Spring như trên, tránh nhầm với các annotation order có mục đích khác.

## 5. Cách 2: Implement `Ordered` với `ApplicationListener`

Một listener viết theo giao diện `ApplicationListener<E>` có thể trực tiếp implement `Ordered` để trả về mức ưu tiên:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public class AuditListener
        implements ApplicationListener<AccountCreatedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void onApplicationEvent(AccountCreatedEvent event) {
        // Xử lý sự kiện.
    }
}
~~~

Đoạn trên cũng cần định nghĩa `AccountCreatedEvent` và đăng ký `AuditListener` vào context. Ưu điểm của `getOrder()` là có thể trả về giá trị tính từ cấu hình khi thiết kế yêu cầu mức ưu tiên thay đổi theo từng bean. Tránh để `getOrder()` thay đổi thất thường trong lúc ứng dụng đang chạy vì tập listener có thể được cache/sắp lại theo cơ chế nội bộ.

**So sánh nhanh:**

| Kiểu listener | Cách đặt ưu tiên nên dùng | Đơn vị được sắp |
| --- | --- | --- |
| Phương thức `@EventListener` | `@Order(value)` ở phương thức | Phương thức lắng nghe được Spring chuyển thành listener adapter |
| Class implement `ApplicationListener<E>` | Implement `Ordered` và trả `getOrder()` | Đối tượng listener |
| Không khai báo ưu tiên | Để mặc định | Thường ở mức `LOWEST_PRECEDENCE` |

Có thể gặp `@Order` trên class/bean ở nhiều thành phần Spring. Với bài toán này, đặt `@Order` tại phương thức `@EventListener` hoặc dùng `Ordered` trực tiếp cho `ApplicationListener` là hai cách thể hiện ý định rõ ràng nhất.

## 6. Ví dụ Java 17+ chạy được: ba listener, một sự kiện

Ví dụ sử dụng **Spring Framework thuần**, không cần Spring Boot, không cần database. Hai listener là phương thức `@EventListener`, listener còn lại implement `ApplicationListener` và `Ordered`. Cả ba nhận cùng một `SignupEvent`.

### 6.1. Cấu trúc dự án

~~~text
listener-order-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── ListenerOrderDemo.java
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'example.ListenerOrderDemo'
}
~~~

Phiên bản Spring 6.2.x trong ví dụ tương thích Java 17+. Có thể sử dụng phiên bản Spring Framework được quản lý tập trung bởi dự án thực tế thay cho số phiên bản minh họa này.

### 6.2. Mã nguồn hoàn chỉnh

`src/main/java/example/ListenerOrderDemo.java`:

~~~java
package example;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public class ListenerOrderDemo {

    public static final class SignupEvent extends ApplicationEvent {
        private final String username;

        public SignupEvent(Object source, String username) {
            super(source);
            this.username = username;
        }

        public String username() {
            return username;
        }
    }

    public static class AnnotatedHandlers {

        @EventListener
        @Order(-10)
        public void validate(SignupEvent event) {
            System.out.println("[-10] validate " + event.username());
        }

        @EventListener
        @Order(10)
        public void notifyUser(SignupEvent event) {
            System.out.println("[10] notify " + event.username());
        }
    }

    public static class AuditListener
            implements ApplicationListener<SignupEvent>, Ordered {

        @Override
        public int getOrder() {
            return 0;
        }

        @Override
        public void onApplicationEvent(SignupEvent event) {
            System.out.println("[0] audit " + event.username());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(AnnotatedHandlers.class);
            context.registerBean(AuditListener.class);
            context.refresh();

            context.publishEvent(new SignupEvent(context, "Linh"));
        }
    }
}
~~~

### 6.3. Chạy và đối chiếu kết quả

Tại thư mục gốc dự án, có Java 17+ và Gradle (hoặc Gradle Wrapper đã thiết lập):

~~~bash
gradle run
~~~

Ba dòng do chương trình in ra, theo thứ tự:

~~~text
[-10] validate Linh
[0] audit Linh
[10] notify Linh
~~~

Gradle có thể in thêm log build; ba dòng trên là **stdout của phần xử lý sự kiện** trong chương trình.

Giải thích:

1. `context.refresh()` khởi tạo context và đăng ký các listener.
2. `publishEvent(new SignupEvent(...))` phát một sự kiện cụ thể.
3. `AnnotatedHandlers.validate` có order `-10` nên đứng đầu.
4. `AuditListener.getOrder()` trả về `0` nên đứng giữa.
5. `AnnotatedHandlers.notifyUser` có order `10` nên đứng cuối.

Tên phương thức `validate` hay `notifyUser` và **thứ tự các lệnh `registerBean` trong ví dụ không phải thứ quyết định mức ưu tiên**. Chính order được khai báo mới diễn đạt thứ tự muốn có.

## 7. Listener đồng bộ, bất đồng bộ và ý nghĩa của thứ tự

### 7.1. Mặc định: đồng bộ

Khi dùng multicaster mặc định và các listener đều là đồng bộ, có thể hình dung:

~~~text
Publisher
   |
   +--> listener order=-10  [chạy xong]
   |
   +--> listener order=0    [chạy xong]
   |
   +--> listener order=10   [chạy xong]
   |
   +--> publishEvent(...) trả về
~~~

Ở đây, **thứ tự gọi** và **thứ tự hoàn tất** trùng nhau vì mỗi listener hoàn tất rồi listener kế tiếp mới chạy. Một listener đồng bộ ném exception chưa được xử lý có thể làm lời gọi phát sự kiện thất bại và khiến listener phía sau không được gọi trong lần phát đó; cách xử lý lỗi riêng của multicaster có thể thay đổi hành vi này.

### 7.2. Khi có `@Async`

Nếu một phương thức `@EventListener` còn có `@Async` và ứng dụng bật xử lý async (chẳng hạn `@EnableAsync`), lời gọi listener có thể chỉ lập lịch công việc; phần thân chạy trên luồng khác:

~~~java
@EventListener
@Order(-10)
@org.springframework.scheduling.annotation.Async
public void slowStep(SignupEvent event) {
    // Có thể hoàn tất sau listener order=10.
}
~~~

Đây là **đoạn minh họa riêng**, không nằm trong ví dụ đồng bộ ở mục 6. Dù listener có order `-10` được điều phối trước, **không được suy ra rằng công việc async sẽ hoàn tất trước** listener `10`. Exception trong async listener cũng không tự động được truyền về người gọi `publishEvent` như xử lý đồng bộ.

Tương tự, khi gắn `TaskExecutor` bất đồng bộ cho `SimpleApplicationEventMulticaster`, các listener hỗ trợ async có thể được gửi tới executor. Một số loại listener, đặc biệt listener đồng bộ hóa với transaction, không cho phép chạy async theo cách đó và vẫn thực thi trong luồng phát sự kiện. Việc sắp xếp danh sách listener không biến tác vụ song song thành chuỗi hoàn tất có thứ tự.

**Quy tắc sử dụng:** nếu B **bắt buộc** đợi A tạo dữ liệu, hãy biểu diễn phụ thuộc bằng luồng xử lý tường minh hoặc bằng sự kiện tiếp theo chỉ được phát sau khi A thành công; không chỉ viết `@Order(A=-10)` và `@Order(B=10)` rồi bật async.

## 8. Kết hợp với `@TransactionalEventListener`

`@TransactionalEventListener` là cơ chế riêng để xử lý sự kiện tại **giai đoạn của transaction**. Mặc định nó lắng nghe ở `TransactionPhase.AFTER_COMMIT`, tức là sau khi transaction commit thành công. Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class TransactionBoundHandlers {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(0)
    public void updateIndex(SignupEvent event) {
        // Thực hiện sau commit thành công.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(10)
    public void sendNotification(SignupEvent event) {
        // Có độ ưu tiên thấp hơn updateIndex trong cùng phase.
    }
}
~~~

Đây là **đoạn minh họa**, cần bean Spring và một transaction thực sự. Nếu không có transaction đang hoạt động, `@TransactionalEventListener` **không được gọi theo mặc định**; có thể thay đổi bằng `fallbackExecution = true` nếu nghiệp vụ thật sự chấp nhận điều đó.

Hai trục phải phân biệt:

- **Phase** quyết định **khi nào** listener transaction chạy tương ứng với transaction (trước commit, sau commit, sau rollback...).
- **Order** quyết định **ưu tiên giữa các listener có thể thực thi tại cùng giai đoạn**; nó không khiến listener `AFTER_COMMIT` chạy trước một listener `BEFORE_COMMIT` chỉ vì số order nhỏ hơn.

Ví dụ: `AFTER_COMMIT @Order(-100)` vẫn đợi commit; `BEFORE_COMMIT @Order(100)` thuộc giai đoạn trước commit. Không dùng `@Order` để thay thế yêu cầu “chỉ gửi thông báo sau khi ghi dữ liệu thành công”.

## 9. Điểm dễ nhầm và cách tránh

| Hiểu nhầm | Điều đúng / cách xử lý |
| --- | --- |
| `@Order(100)` ưu tiên cao hơn `@Order(1)` vì số lớn hơn | Ngược lại: **1 được xếp trước 100**. |
| Bỏ `@Order` thì listener chắc chắn chạy theo thứ tự bean khai báo | Không có hợp đồng thứ tự nghiệp vụ; khai báo order riêng nếu thứ tự quan trọng. |
| Hai listener cùng `@Order(0)` luôn chạy theo thứ tự tên class | Không bảo đảm; dùng các giá trị khác nhau hoặc thiết kế một chuỗi tường minh. |
| `@Order` làm các công việc `@Async` hoàn tất theo đúng thứ tự | Chỉ xếp thứ tự điều phối; hoàn tất phụ thuộc lịch chạy, thời gian xử lý và executor. |
| `@Order` đảm bảo transaction commit giữa listener A và B | Không; transaction boundary được quyết định bởi cấu hình transaction. |
| `@Order` trên listener giống thứ tự khởi tạo bean | Không; thứ tự khởi tạo phụ thuộc vào quan hệ bean, dependency và cơ chế lifecycle. |
| Listener ưu tiên trước sẽ chắc chắn thành công | Không; listener có thể ném exception, timeout hoặc thất bại do hệ thống ngoài. |
| `@Order` bảo đảm message delivery bền vững | Không; application event mặc định là cơ chế trong ứng dụng, không phải hàng đợi bền vững. |

**Lưu ý về `PriorityOrdered`:** Spring còn có marker interface `PriorityOrdered extends Ordered`, dùng cho trường hợp cần một nhóm đối tượng được ưu tiên trước nhóm `Ordered` thông thường, bất kể giá trị order. Đây là cơ chế ưu tiên đặc biệt thường gặp ở hạ tầng framework. Khi thiết kế application event listener thông thường, bắt đầu với `@Order` hoặc `Ordered` là đủ; chỉ dùng `PriorityOrdered` nếu thực sự hiểu và cần ngữ nghĩa phân nhóm đó.

## 10. Thiết kế listener có thứ tự trong thực tế

Dùng order có chủ đích cho những listener **độc lập về dữ liệu nhưng có yêu cầu ưu tiên khi gọi**, chẳng hạn ghi log kiểm tra trước khi tác vụ phụ ít quan trọng hơn được thực hiện trong cùng luồng đồng bộ. Đặt mức ưu tiên bằng hằng số có tên nếu nhiều listener cần chia sẻ một quy ước:

~~~java
public final class ListenerPriorities {
    private ListenerPriorities() {}

    public static final int VALIDATION = -100;
    public static final int AUDIT = 0;
    public static final int NOTIFICATION = 100;
}
~~~

Sau đó sử dụng `@Order(ListenerPriorities.VALIDATION)` để tránh “số ma thuật”. Giá trị truyền cho annotation cần là hằng số biên dịch, nên các hằng `public static final int` như trên phù hợp; giá trị lấy trực tiếp từ cấu hình chạy thời gian thực thì không thể đưa vào tham số của `@Order`.

Đối với listener dạng `Ordered`, có thể dùng cấu hình để quyết định `getOrder()` theo mỗi bean, nhưng hãy giữ giá trị ổn định trong vòng đời hoạt động bình thường. Tránh giải quyết một chuỗi nghiệp vụ nhiều bước chỉ bằng order:

~~~text
Không nên phụ thuộc ngầm:
Event X -> Listener A (ghi database) -> Listener B (đọc kết quả A)

Rõ ràng hơn:
Service xử lý và xác nhận A -> phát Event Y
                            -> Listener B nhận Event Y
~~~

Nếu cần đảm bảo thông điệp đến hệ thống khác ngay cả khi ứng dụng dừng hoặc giao dịch rollback, cân nhắc cơ chế bền vững như **transactional outbox + message broker** theo yêu cầu nghiệp vụ. Đây là yêu cầu độ tin cậy, không phải một mức `@Order` đặc biệt.

### Checklist trước khi dùng `@Order`

1. Các listener có thật sự nhận **cùng loại event** trong **cùng application context** không?
2. Chúng chạy đồng bộ hay có `@Async`/executor riêng?
3. Có listener nào phụ thuộc dữ liệu do listener khác tạo ra không? Nếu có, có nên chuyển phụ thuộc đó vào service hoặc sự kiện tiếp theo không?
4. Sự kiện có được phát trong transaction? Handler nào phải chạy sau commit?
5. Có hai handler cùng order gây phụ thuộc không rõ ràng không?
6. Đã kiểm chứng thứ tự thực tế bằng một lần publish và đo/log rõ ràng chưa?

## 11. Tự kiểm tra hiểu bài

**Tình huống 1.** Ba listener đồng bộ cho cùng event có order `5`, `-1`, `0`. Thứ tự gọi dự kiến là gì?

**Đáp án:** `-1 → 0 → 5`.

**Tình huống 2.** Listener A có `@Order(-10)` và `@Async`; listener B có `@Order(10)` và chạy đồng bộ. Có thể bảo đảm A hoàn tất trước B không?

**Đáp án:** Không. Việc A được điều phối trước không ràng buộc thời điểm hoàn tất công việc async.

**Tình huống 3.** Một listener `AFTER_COMMIT` có order `-100`, một listener `BEFORE_COMMIT` có order `100`. Listener nào thuộc giai đoạn trước commit?

**Đáp án:** Listener `BEFORE_COMMIT`. Phase và order là hai quy tắc khác nhau.

**Tình huống 4.** Hai listener đồng bộ có cùng order `0`; chức năng của B cần dữ liệu mới do A tạo. Cách sửa nào tốt?

**Đáp án:** Không dựa vào thứ tự khi order bằng nhau. Nếu sự phụ thuộc mang ý nghĩa nghiệp vụ, để service điều phối A rồi B hoặc phát sự kiện mới sau khi A thành công. Việc dùng hai số order khác nhau chỉ phù hợp khi sự phụ thuộc nhỏ, trong cùng luồng và được chấp nhận rõ ràng trong thiết kế.

## 12. Tài liệu tham khảo

- Spring Framework Reference — ApplicationContext: Application Events và **Ordering Listeners**: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Javadoc `Ordered`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/Ordered.html
- Javadoc `@Order`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/annotation/Order.html
- Javadoc `SimpleApplicationEventMulticaster`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
