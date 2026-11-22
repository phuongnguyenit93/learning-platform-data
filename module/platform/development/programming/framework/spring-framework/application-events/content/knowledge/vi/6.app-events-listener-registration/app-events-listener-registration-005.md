# Listener của parent và child context trong Spring

Spring cho phép một ứng dụng có nhiều ApplicationContext được tổ chức theo quan hệ cha–con. Mỗi context quản lý bean và listener của riêng nó. Khi một event được publish trong context con, Spring dispatch event trong context con trước, sau đó chuyển tiếp cùng event lên context cha. Chiều chuyển tiếp này chỉ đi lên cây context: event phát ở parent không tự động đi xuống child và event của một child không được gửi sang sibling khác.

Hiểu đúng hai phần riêng biệt — **phạm vi bean** và **đường đi của event** — giúp tránh bỏ lỡ listener, xử lý trùng hoặc chạy logic khởi động nhiều lần.

## 1. Parent và child ApplicationContext là gì?

Một ApplicationContext có thể đặt một context khác làm parent bằng setParent(...). Context con có thể tra cứu bean do parent cung cấp. Parent không thể tra cứu bean chỉ được khai báo trong child.

Ví dụ, một ứng dụng Spring MVC cổ điển có thể tổ chức context như sau:

- **Root context (parent):** service, repository, datasource và các thành phần dùng chung.
- **DispatcherServlet context (child):** controller, handler mapping, view resolver và cấu hình web riêng cho servlet.

Child có thể sử dụng service ở parent. Parent không phụ thuộc vào controller chỉ tồn tại trong child.

Quan hệ này tạo thành cây context. Một ứng dụng có thể có nhiều child cùng trỏ về một parent, hoặc có nhiều tầng parent–child. Mỗi ApplicationContext vẫn có vòng đời, BeanFactory và ApplicationEventMulticaster riêng.

## 2. Quy tắc truyền event giữa các context

Khi một event được publish, Spring xử lý theo quy tắc:

1. Context nơi gọi publishEvent() gửi event đến listener đã đăng ký trong chính context đó.
2. Nếu context có parent, Spring gọi publishEvent() trên parent với cùng event.
3. Parent dispatch event cho listener của parent, rồi tiếp tục chuyển lên parent cấp cao hơn nếu có.
4. Quá trình dừng ở context gốc vì context đó không có parent.

    Root context
    [Root listeners]
           ^
           | event từ child được chuyển lên
      +----+----+
      |         |
    Child A  Child B
    [A listeners] [B listeners]

A publish: A listeners -> Root listeners
B publish: B listeners -> Root listeners
Root publish: Root listeners

Hệ quả cần nhớ:

| Nơi phát event | Listener có thể nhận |
|---|---|
| Child A | Listener của Child A, rồi listener của parent và các ancestor |
| Child B | Listener của Child B, rồi listener của parent và các ancestor |
| Parent | Listener của parent và các ancestor; không đi xuống child |
| Root | Chỉ listener trong Root |

Không có đường truyền ngang giữa hai child. Nếu Child A phát event, Child B không nhận event đó chỉ vì cả hai cùng có parent. Parent có thể nhận event từ cả hai child và thực hiện xử lý chung.

Event được chuyển tiếp là cùng một object. Spring không tạo một bản sao hoặc một wrapper mới chỉ để chuyển event lên parent. Vì vậy, không nên để listener thay đổi trạng thái của event sau khi publish; nhiều context có thể quan sát cùng một object.

## 3. Mỗi context có multicaster và tập listener riêng

ApplicationEventMulticaster là thành phần dispatch event của một ApplicationContext. Listener được đăng ký trong context nào thì được multicaster của context đó quản lý.

Điều này có nghĩa:

- Listener đăng ký trong child được gọi khi child nhận event.
- Listener đăng ký trong parent được gọi khi parent nhận event, kể cả khi event ban đầu được phát ở child và đã được chuyển lên.
- Listener của parent không tự trở thành listener cục bộ của child.
- Listener của child không tự trở thành listener của parent.

Bean visibility và event routing là hai cơ chế khác nhau. Child có thể inject một service bean từ parent, nhưng điều đó không có nghĩa listener được khai báo trong parent sẽ được đăng ký thêm vào multicaster của child. Khi child publish event, parent nhận event nhờ cơ chế chuyển tiếp lên trên.

Cả listener triển khai ApplicationListener và phương thức dùng @EventListener đều tuân theo phạm vi đăng ký của context sở hữu chúng. @EventListener được Spring chuyển thành listener adapter trong context nơi bean chứa phương thức đó được khởi tạo.

## 4. Ví dụ: event từ child được parent nhận

Ví dụ Java dưới đây tạo hai AnnotationConfigApplicationContext. Parent được refresh trước; child đặt parent rồi refresh. Mỗi context đăng ký một listener cho cùng loại event.

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ParentChildEventsDemo {

    public static void main(String[] args) {
        try (var parent = new AnnotationConfigApplicationContext()) {
            parent.setId("parent");

            parent.addApplicationListener(
                (ApplicationListener<NoticeEvent>) event ->
                    System.out.println(
                        "parent listener: " + event.getMessage()
                    )
            );

            parent.refresh();

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setId("child");
                child.setParent(parent);

                child.addApplicationListener(
                    (ApplicationListener<NoticeEvent>) event ->
                        System.out.println(
                            "child listener: " + event.getMessage()
                        )
                );

                child.refresh();

                child.publishEvent(
                    new NoticeEvent(child, "from child")
                );

                parent.publishEvent(
                    new NoticeEvent(parent, "from parent")
                );
            }
        }
    }

    static final class NoticeEvent extends ApplicationEvent {
        private final String message;

        NoticeEvent(Object source, String message) {
            super(source);
            this.message = message;
        }

        String getMessage() {
            return message;
        }
    }
}
~~~

Với multicaster mặc định chạy listener đồng bộ, output là:

~~~text
child listener: from child
parent listener: from child
parent listener: from parent
~~~

Giải thích:

- Lần publish đầu tiên được gọi trên child. Child listener chạy trước; sau đó child chuyển event lên parent nên parent listener cũng chạy.
- Lần publish thứ hai được gọi trên parent. Parent listener chạy, nhưng child listener không được gọi vì parent không phát event xuống dưới.
- Không có listener ở context khác nào được gọi ngoài đường đi này.

Đây là ví dụ độc lập về event routing. Nó không yêu cầu cấu hình component scan; listener được đăng ký trực tiếp trước khi refresh để làm rõ context sở hữu listener.

## 5. Sự kiện vòng đời context cũng được chuyển lên parent

Các sự kiện như ContextRefreshedEvent, ContextStartedEvent, ContextStoppedEvent và ContextClosedEvent kế thừa ApplicationContextEvent. Chúng mang theo ApplicationContext đã phát ra sự kiện.

Khi child refresh hoặc close, event tương ứng được publish bởi child và chuyển lên parent. Vì thế, listener nằm trong root context có thể nhận ContextRefreshedEvent của chính root lẫn các child context.

Ví dụ, trong hệ thống có một root context và hai DispatcherServlet context, listener của root có thể nhận nhiều ContextRefreshedEvent:

- Một event khi root context refresh.
- Một event khi child context của servlet thứ nhất refresh.
- Một event khi child context của servlet thứ hai refresh.

Đừng mặc định mỗi ContextRefreshedEvent đồng nghĩa toàn bộ ứng dụng vừa khởi động xong. Event này mô tả một ApplicationContext cụ thể đã hoàn tất refresh. Trong cây context, mỗi context có thể refresh ở thời điểm khác nhau.

Tương tự, khi child đóng, parent có thể nhận ContextClosedEvent của child. Điều đó không có nghĩa parent cũng đã đóng. Hãy kiểm tra context nằm trong event trước khi thực hiện hành động phụ thuộc vào vòng đời.

## 6. Xác định context đã phát event

### Với ApplicationContextEvent

Các lifecycle event cung cấp getApplicationContext(). Listener có thể so sánh context trong event với context mà bean đang thuộc về.

Ví dụ listener chỉ muốn chạy khi root context hoàn tất refresh:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class RootRefreshListener {

    private final ApplicationContext ownContext;

    RootRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }

        System.out.println("Root context refreshed");
    }
}
~~~

Nếu listener bean được tạo trong root context, ApplicationContext được inject vào bean là root context. Khi parent nhận event từ child, phép so sánh identity không khớp và listener bỏ qua event đó.

Có thể so sánh context ID thay vì object identity khi cần đối chiếu qua log hoặc cấu hình. Tuy nhiên, context ID phải được đặt rõ ràng và duy nhất trong cây context; không nên giả định mọi context có ID hữu ích hoặc duy nhất nếu ứng dụng không cấu hình chúng.

### Với custom event

Một custom event kế thừa ApplicationEvent không tự có getApplicationContext(). ApplicationEvent chỉ cung cấp getSource(), mà source có thể là service hoặc publisher bean. Không nên giả định source luôn là context.

Nếu listener cần biết event phát từ đâu, hãy đưa thông tin đó vào hợp đồng event. Có thể truyền context ID, tenant ID hoặc một mã nguồn phát phù hợp:

~~~java
import org.springframework.context.ApplicationEvent;

public final class DataImportedEvent extends ApplicationEvent {
    private final String contextId;
    private final int importedRows;

    public DataImportedEvent(
            Object source,
            String contextId,
            int importedRows) {
        super(source);
        this.contextId = contextId;
        this.importedRows = importedRows;
    }

    public String getContextId() {
        return contextId;
    }

    public int getImportedRows() {
        return importedRows;
    }
}
~~~

Một cách khác là cố ý dùng ApplicationContext làm source khi event thực sự mô tả hoạt động của context. Dù chọn cách nào, hãy ghi rõ ý nghĩa source trong hợp đồng; đừng dùng một quy ước ngầm mà listener không thể dựa vào một cách an toàn.

## 7. Tránh xử lý trùng khi có listener ở cả parent và child

Một tình huống thường gặp là cùng một loại listener được component scan trong cả root context và child context. Khi child phát event:

1. Listener của child xử lý event trong child multicaster.
2. Event được chuyển lên parent.
3. Listener cùng loại trong parent xử lý event lần nữa.

Nếu cả hai listener đều gửi email, ghi dữ liệu hoặc cập nhật cùng một tài nguyên, tác dụng phụ có thể xảy ra hai lần.

Cách phòng tránh:

- **Tách phạm vi component scan:** root context chỉ scan package chứa service, repository và thành phần dùng chung; child scan package controller và cấu hình web của nó.
- **Đặt listener ở một context có chủ đích:** nếu xử lý dùng chung cho mọi child, đăng ký listener ở parent; nếu chỉ thuộc servlet cụ thể, đăng ký ở child.
- **Lọc theo nguồn phát:** với lifecycle event, kiểm tra getApplicationContext(); với custom event, dùng context ID hoặc metadata đã định nghĩa.
- **Thiết kế handler idempotent:** nếu cùng một event có thể được quan sát từ nhiều nơi hoặc phát lại, xử lý lặp không được tạo tác dụng phụ sai. Có thể dùng event ID và khóa chống xử lý trùng khi nghiệp vụ yêu cầu.

Không nên chỉ dựa vào tên bean để đoán listener đang chạy ở context nào. Hãy kiểm tra nơi bean thực sự được khởi tạo và context sở hữu multicaster đã dispatch nó.

## 8. Thứ tự listener và xử lý bất đồng bộ

Với cấu hình mặc định, SimpleApplicationEventMulticaster gọi listener đồng bộ trên thread phát event. Khi child publish event, child dispatch hoàn tất trước khi lời gọi chuyển tiếp lên parent bắt đầu. Vì thế, trong ví dụ đồng bộ, output thể hiện child listener trước parent listener.

Có thể dùng @Order hoặc Ordered để sắp thứ tự listener trong cùng một multicaster. Tuy nhiên:

- @Order chỉ sắp thứ tự trong phạm vi danh sách listener của một multicaster.
- Nó không tạo ra một thứ tự toàn cục giữa mọi listener của parent và child.
- Nếu multicaster được cấu hình executor bất đồng bộ, việc listener bắt đầu hoặc hoàn thành theo thứ tự nào không còn được bảo đảm chỉ bằng thứ tự dispatch.
- Không nên dùng event propagation để điều phối một chuỗi công việc bắt buộc có phụ thuộc kết quả.

Nếu một thao tác cần parent hoàn tất trước child hoặc cần kết quả từ listener để tiếp tục, hãy dùng service/interface hoặc một workflow điều phối rõ ràng. Event propagation phù hợp cho việc thông báo và phản ứng, không phải cơ chế RPC giữa các context.

## 9. Transaction và cùng một event được chuyển lên parent

Parent nhận cùng event object mà child đã publish. Việc chuyển event lên parent không tự tạo transaction mới, không sao chép transaction context và cũng không làm event trở thành message bền vững.

Với listener đồng bộ chạy trong cùng thread, một listener ở parent có thể được gọi trong lúc luồng publish của child vẫn đang hoạt động. Nếu event được phát trong transaction, listener đồng bộ có thể chạy trước khi transaction kết thúc. Hãy cân nhắc @TransactionalEventListener khi phản ứng cần gắn với phase transaction, ví dụ AFTER_COMMIT.

Nếu listener dùng @Async hoặc multicaster chạy executor riêng, transaction context của thread phát event không tự chuyển sang thread xử lý. Cần thiết kế transaction và xử lý lỗi cho listener async một cách riêng biệt.

Việc child chuyển event lên parent cũng không cung cấp retry hoặc bảo đảm giao nhận khi process dừng. Nếu công việc bắt buộc phải được xử lý kể cả sau sự cố, hãy dùng outbox/message broker hoặc cơ chế lưu bền phù hợp thay vì chỉ dựa vào ApplicationContext hierarchy.

## 10. Cách kiểm tra parent-child event routing

Một kiểm tra nhỏ có thể xác nhận hướng truyền event và tránh hiểu nhầm:

1. Tạo parent context và đăng ký một listener cho NoticeEvent.
2. Refresh parent trước khi tạo hoặc refresh child.
3. Đặt parent bằng child.setParent(parent), sau đó đăng ký listener riêng cho child.
4. Publish NoticeEvent từ child; xác nhận child listener và parent listener đều nhận.
5. Publish NoticeEvent từ parent; xác nhận chỉ parent listener nhận.
6. Nếu có Child A và Child B, publish từ A; xác nhận B không nhận.
7. Phát ContextRefreshedEvent qua quá trình refresh thật; kiểm tra listener ở parent có lọc đúng context nguồn.
8. Nếu listener được scan ở cả hai context, xác nhận có thể xảy ra xử lý hai lần và điều chỉnh phạm vi đăng ký.

Trong ứng dụng lớn, log nên ghi context ID, event type và event ID. Điều này giúp phân biệt event phát từ root, servlet context hoặc một child khác, nhất là khi nhiều context refresh gần nhau.

## 11. Những lỗi thường gặp

**Cho rằng parent listener được đăng ký tự động vào child.** Bean parent có thể được child tra cứu, nhưng listener vẫn thuộc multicaster của parent. Child nhận event của parent chỉ khi parent tự publish; chiều event không đi xuống child.

**Cho rằng child event chỉ được xử lý ở child.** Spring chuyển tiếp event lên parent. Nếu listener dùng chung tồn tại ở cả hai context, nó có thể chạy hai lần.

**Cho rằng sibling nhận event của nhau.** Child A không publish trực tiếp sang Child B. Event chỉ đi từ A lên parent; parent không tự phát ngược xuống B.

**Dùng ContextRefreshedEvent như tín hiệu ứng dụng sẵn sàng duy nhất.** Mỗi context có thể refresh riêng. Nếu cần mốc ứng dụng Spring Boot đã sẵn sàng, hãy cân nhắc ApplicationReadyEvent và xác định rõ context hoặc application lifecycle đang quan tâm.

**Dựa vào event.getSource() để lấy ApplicationContext.** Source của custom event có thể là publisher bean. Chỉ ApplicationContextEvent mới cung cấp getApplicationContext() theo hợp đồng của nó; custom event cần metadata nguồn riêng nếu cần.

**Dựa vào @Order để sắp thứ tự xuyên parent-child.** @Order áp dụng trong một multicaster. Nếu cần thứ tự toàn cục giữa các context, hãy tạo một điểm điều phối duy nhất.

**Dùng mutable event hoặc thay đổi payload trong listener.** Parent và child có thể nhận cùng object. Thay đổi trạng thái trong listener có thể làm listener ở context sau nhìn thấy dữ liệu đã bị sửa. Ưu tiên event bất biến và payload chỉ đọc.

## 12. Quy tắc ghi nhớ

- Child publish: child listeners trước, rồi parent và các ancestor.
- Parent publish: parent và các ancestor; không đi xuống child.
- Hai sibling không nhận event của nhau chỉ vì có chung parent.
- Mỗi context có multicaster và tập listener riêng.
- Bean visibility từ parent xuống child không đồng nghĩa listener được đăng ký ở cả hai context.
- Lifecycle event mang ApplicationContext nguồn; custom event cần quy ước metadata riêng.
- Nếu listener xuất hiện ở cả parent và child, kiểm tra nguy cơ xử lý trùng.
- Mặc định listener đồng bộ; async làm thay đổi thời điểm hoàn thành và cách xử lý lỗi.

**Ghi nhớ:** event đi lên cây ApplicationContext. Child có thể thông báo cho parent; parent không phát event xuống child. Hãy đặt listener ở đúng context, lọc context nguồn khi cần và thiết kế handler chịu được việc nhận event từ nhiều child.

## Tài liệu tham khảo

- [AbstractApplicationContext — Spring Framework source](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
- [ApplicationContext — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContext.html)
- [ApplicationContextEvent — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [ApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)