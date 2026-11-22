# Receive và forward trong một transaction

## 1. Mục tiêu và tình huống thực tế

Trong chương **Poller transaction** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách đặt thao tác nhận thông điệp và chuyển tiếp thông điệp vào cùng một transaction. Trọng tâm là quan hệ giữa `Message`, `MessageChannel`, polling endpoint và Java DSL khi xây dựng một luồng tích hợp có thể phục hồi sau lỗi.

Giả sử hệ thống nhận yêu cầu xử lý đơn hàng vào queue `orders.in`, sau đó chuyển yêu cầu sang `orders.ready`. Với mỗi thông điệp, ta muốn duy trì quy tắc:

> Chỉ xác nhận lấy thông điệp khỏi nguồn khi việc bàn giao đến đích trong phạm vi đã chọn cũng thành công.

Nếu tiến trình lỗi sau khi nhận nhưng trước khi bàn giao, thông điệp phải còn khả năng được nhận lại. Nếu bàn giao đã được commit, thông điệp không được xuất hiện đồng thời như một yêu cầu chưa chuyển ở nguồn.

Bài học dùng hai queue lưu trong cùng một cơ sở dữ liệu để minh họa quy tắc này. Đây là mô hình thực hành về transaction; việc chọn công nghệ queue cho hệ thống thực tế còn phụ thuộc tải, yêu cầu vận hành và hạ tầng sẵn có.

Sau bài học, bạn có thể:

- Xác định transaction cần bắt đầu trước thao tác nào.
- Phân biệt việc chuyển tiếp đến channel với việc hoàn tất nghiệp vụ ở consumer.
- Cấu hình poller có transaction bằng Java DSL.
- Giải thích điều kiện để rollback khôi phục trạng thái nguồn.
- Xây dựng kịch bản kiểm chứng commit, rollback và ranh giới bất đồng bộ.

## 2. Receive và forward là hai bước nào?

Trong polling consumer, endpoint chủ động gọi `receive()` trên một `PollableChannel`. Khi có thông điệp, endpoint giao thông điệp cho handler; handler có thể xử lý và gửi tiếp qua output channel.

| Thành phần | Vai trò trong bài |
| --- | --- |
| `Message<?>` | Mang payload và header của yêu cầu đơn hàng |
| Input `PollableChannel` | Nguồn mà polling endpoint lấy thông điệp |
| Poller | Quy định lịch chạy, giới hạn số lần nhận và advice áp dụng |
| Endpoint | Kết nối input channel với handler |
| `BridgeHandler` | Chuyển tiếp thông điệp mà không đổi payload nghiệp vụ |
| Output `MessageChannel` | Điểm bàn giao tiếp theo của luồng |
| Transaction manager | Quản lý transaction của tài nguyên được cấu hình |

Một messaging bridge phù hợp khi mục đích chỉ là nối hai channel. Nếu cần đổi định dạng, có thể dùng transformer làm endpoint đầu tiên và gắn poller vào endpoint đó. Cấu trúc Java DSL của bridge được mô tả trong [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Cần đọc đúng ý nghĩa của “forward thành công”:

- Gửi vào `DirectChannel` thông thường sẽ gọi handler đăng ký trên cùng luồng gọi. Khi handler trả về bình thường, phần xử lý đồng bộ đó đã kết thúc.
- Gửi vào một queue chỉ xác nhận bước enqueue theo cơ chế của queue. Consumer lấy thông điệp về sau có vòng đời xử lý riêng.
- Gửi qua ranh giới bất đồng bộ không đồng nghĩa mọi công việc phía sau đã hoàn tất.

Vì vậy, trước khi cấu hình transaction, hãy mô tả điểm bàn giao cần bảo vệ bằng một hành động cụ thể: ghi thông điệp vào queue đích, cập nhật bảng nghiệp vụ, hay gọi một consumer đồng bộ.

## 3. Transaction phải bao trùm cả receive

### 3.1. Cửa sổ lỗi khi chỉ bảo vệ xử lý nghiệp vụ

Xét luồng sau:

~~~text
receive từ nguồn
    ↓
gọi service có @Transactional
    ↓
forward đến đích
~~~

Nếu thao tác nhận đã được xác nhận độc lập, transaction bên trong service không thể quay lại bảo vệ thao tác nhận trước đó. Chẳng hạn:

1. Thông điệp `order-1042` bị lấy khỏi nguồn.
2. Service mở transaction cập nhật dữ liệu.
3. Gửi đến đích gặp lỗi.
4. Transaction của service rollback.
5. Nguồn vẫn có thể đã mất thông điệp.

`@Transactional` ở service hữu ích cho phạm vi service, nhưng phải kiểm tra transaction đó bắt đầu ở đâu so với `receive()`.

### 3.2. Phạm vi cần có

Với transactional poller, cấu trúc mong muốn là:

~~~text
BEGIN
    receive từ nguồn có hỗ trợ transaction
    xử lý đồng bộ cần thiết
    forward đến đích có tham gia transaction
COMMIT

Nếu lỗi thỏa quy tắc rollback:
ROLLBACK các thay đổi của tài nguyên tham gia
~~~

Điểm đặc biệt của poller là transaction advice có thể bao quanh cả thao tác `receive()`, thay vì chỉ bắt đầu từ một lời gọi xử lý phía sau. Đây là mục đích được trình bày trong [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-poller).

~~~mermaid
sequenceDiagram
    participant P as Polling endpoint
    participant T as Transaction manager
    participant I as Queue nguồn JDBC
    participant O as Queue đích JDBC

    P->>T: Bắt đầu transaction
    P->>I: receive()
    I-->>P: Message
    P->>O: send(Message)
    alt Thành công đến lúc commit
        P->>T: Commit
        Note over I,O: Xóa ở nguồn và thêm ở đích cùng có hiệu lực
    else Có lỗi cần rollback trước khi commit
        P->>T: Rollback
        Note over I,O: Nguồn được phục hồi, bản ghi mới ở đích bị hủy
    end
~~~

Sơ đồ giả định cả hai queue dùng cùng tài nguyên JDBC được transaction manager quản lý. Nó không mô tả một giao dịch tự động bao phủ mọi hệ thống bên ngoài.

## 4. Bốn điều kiện để tính nguyên tử có ý nghĩa

### 4.1. Nguồn phải hỗ trợ rollback thao tác nhận

`QueueChannel` mặc định chứa thông điệp trong bộ nhớ. Việc có một JDBC transaction ở poller không khiến thao tác lấy phần tử khỏi queue bộ nhớ được hoàn tác.

Khi `QueueChannel` được hỗ trợ bởi `JdbcChannelMessageStore`, thao tác lấy thông điệp tác động đến dữ liệu JDBC. Nếu tham gia đúng transaction, rollback có thể phục hồi dữ liệu đó. Cơ chế này được mô tả trong [Configuring Message Channels — Persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Điều cần hỏi là “tài nguyên thực hiện receive có tham gia transaction không”, thay vì chỉ kiểm tra có lời gọi `transactional(...)` trong cấu hình.

### 4.2. Transaction manager phải quản lý đúng tài nguyên

Trong ví dụ hai JDBC queue, store và transaction manager cùng nhận một bean `DataSource`. `DataSourceTransactionManager` quản lý transaction cho một JDBC `DataSource`; các lớp như `JdbcTemplate` lấy connection theo cơ chế tham gia transaction của Spring. Xem [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

Hai connection tự mở độc lập hoặc hai `DataSource` khác nhau trỏ đến cùng một database không tự trở thành một transaction chung.

Nếu luồng vừa nhận từ JMS vừa ghi JDBC, cần phân tích riêng hai tài nguyên. Chỉ chọn một transaction manager JDBC không làm thao tác nhận JMS trở thành một phần nguyên tử của JDBC transaction.

### 4.3. Các bước cần bảo vệ phải nằm trong phạm vi thực thi phù hợp

Trong mô hình transaction đồng bộ đang xét, context transaction gắn với thread. Những handler nối nhau qua `DirectChannel` có thể tiếp tục dùng context đó; điều này vẫn đòi hỏi tài nguyên và propagation phù hợp.

Khi thông điệp được đưa vào queue để consumer khác lấy, hoặc được chuyển sang executor khác, phần xử lý sau ranh giới đó không tự kế thừa transaction hiện tại. Tài liệu [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries) giải thích giới hạn này.

### 4.4. Lỗi phải dẫn đến quyết định rollback

Một lỗi đã bị bắt và chuyển thành kết quả bình thường có thể làm phần bao transaction coi công việc đã thành công. Ngược lại, exception đi ngược ra ngoài transaction advice được xét theo rollback rules.

Với quy tắc mặc định thông thường của Spring, `RuntimeException` và `Error` dẫn đến rollback; checked exception cần quy tắc phù hợp. Trong Spring Integration, exception từ handler còn có thể được bọc trong `MessagingException`, nên cần xét exception thực tế đến transaction interceptor. Xem [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

## 5. Ví dụ Java DSL: chuyển giữa hai JDBC queue

### 5.1. Chuẩn bị cho bài thực hành

Ví dụ sử dụng các dependency sau, với phiên bản đồng bộ qua BOM hoặc dependency management của dự án:

- `spring-integration-core`.
- `spring-integration-jdbc`.
- `spring-jdbc` và `spring-tx`.
- H2 cho môi trường thực hành.
- JUnit Jupiter và `spring-test` nếu sử dụng đoạn kiểm thử ở phần sau.

Các lớp ứng dụng dưới đây có thể đặt trong cùng một package. Java DSL dùng `IntegrationFlow.from(...)`.

Ví dụ chọn H2 để tập trung vào transaction. Khi đổi database, cần đổi cả schema và `ChannelMessageStoreQueryProvider` tương ứng. Store JDBC cần các bảng được khởi tạo trước khi endpoint chạy; tài liệu [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html) mô tả schema và query provider theo database.

### 5.2. DataSource dành cho môi trường lab

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;

@Configuration
public class JdbcLabConfiguration {

    @Bean
    public EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("classpath:org/springframework/integration/"
                        + "jdbc/store/channel/schema-h2.sql")
                .build();
    }
}
~~~

H2 ở đây là database trong bộ nhớ. Nó cho phép quan sát commit và rollback của JDBC, nhưng không minh họa khả năng giữ dữ liệu qua việc dừng JVM. Muốn thực hành khôi phục sau khi khởi động lại, hãy dùng database lưu trên đĩa và giữ ổn định định danh queue.

### 5.3. Store, channel và transactional poller

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class ReceiveForwardConfiguration {

    @Bean
    public PlatformTransactionManager receiveForwardTxManager(
            DataSource dataSource) {

        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore channelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);

        store.setChannelMessageStoreQueryProvider(
                new H2ChannelMessageStoreQueryProvider());

        return store;
    }

    @Bean
    public QueueChannel incomingOrders(JdbcChannelMessageStore channelStore) {
        return new QueueChannel(
                new MessageGroupQueue(channelStore, "orders.in"));
    }

    @Bean
    public QueueChannel readyOrders(JdbcChannelMessageStore channelStore) {
        return new QueueChannel(
                new MessageGroupQueue(channelStore, "orders.ready"));
    }

    @Bean
    public IntegrationFlow receiveAndForward(
            PlatformTransactionManager receiveForwardTxManager) {

        return IntegrationFlow.from("incomingOrders")
                .bridge(endpoint -> endpoint
                        .id("receiveForwardBridge")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(500)
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(1)
                                .transactional(receiveForwardTxManager)))
                .channel("readyOrders")
                .get();
    }
}
~~~

Hai queue cùng dùng `channelStore` nhưng có group ID khác nhau: `orders.in` và `orders.ready`. Group ID là định danh lưu trữ của queue, không phải tên header của thông điệp. Giữ ID ổn định khi cần sử dụng lại dữ liệu qua các lần chạy; yêu cầu này có trong [MessageGroupQueue API](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

Lệnh `transactional(receiveForwardTxManager)` nằm trên **poller của bridge**, vì bridge nhận từ một pollable input channel. `PollerSpec` cung cấp phương thức này để thêm transaction advice cho polling task. Xem [PollerSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

`autoStartup(false)` giúp bài thực hành chủ động thời điểm chạy endpoint. Khi vận hành với yêu cầu tự khởi động, có thể bỏ thiết lập này hoặc đặt thành `true`.

### 5.4. Chạy luồng và quan sát kết quả

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ReceiveForwardDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                JdbcLabConfiguration.class,
                ReceiveForwardConfiguration.class)) {

            PollableChannel incoming = context.getBean(
                    "incomingOrders", PollableChannel.class);

            PollableChannel ready = context.getBean(
                    "readyOrders", PollableChannel.class);

            Message<String> order = MessageBuilder
                    .withPayload("order-1042")
                    .setHeader("businessKey", "order-1042")
                    .build();

            if (!incoming.send(order)) {
                throw new IllegalStateException("Không ghi được queue nguồn");
            }

            Lifecycle bridge = context.getBean(
                    "receiveForwardBridge", Lifecycle.class);
            bridge.start();

            Message<?> forwarded = ready.receive(5_000);

            if (forwarded == null) {
                throw new IllegalStateException(
                        "Chưa nhận được thông điệp tại queue đích");
            }

            System.out.println(forwarded.getPayload());
        }
    }
}
~~~

Kết quả mong đợi là payload `order-1042`. Đoạn demo chủ động lấy thông điệp khỏi queue đích để hiển thị; vì thế sau khi demo kết thúc, đích không còn giữ thông điệp đã được đọc.

Payload `String` và header `String` giúp ví dụ tránh vấn đề tuần tự hóa dữ liệu phức tạp. Khi đưa đối tượng nghiệp vụ vào persistent store, cần bảo đảm chiến lược lưu trữ hỗ trợ payload và các header cần giữ.

### 5.5. Transaction thực hiện những thay đổi nào?

Với một thông điệp đầu vào đã được lưu thành công, có thể diễn giải trạng thái mong muốn như sau:

| Thời điểm | Queue nguồn | Queue đích |
| --- | --- | --- |
| Trước khi poller xử lý | Có `order-1042` | Chưa có |
| Trong transaction sau receive và send | Thay đổi xóa đang chờ hoàn tất | Thay đổi thêm đang chờ hoàn tất |
| Sau commit thành công | Không còn | Có `order-1042` |
| Sau rollback trước commit | Có lại | Không có bản ghi mới của lần chuyển thất bại |

Hàng “trong transaction” mô tả thay đổi thuộc transaction đang chạy. Khả năng thread khác nhìn thấy dữ liệu hoặc bị chặn còn phụ thuộc isolation và cơ chế khóa của database.

Điểm bàn giao được bảo vệ trong cấu hình này là **lưu thông điệp vào `readyOrders`**. Nếu một consumer khác nhận từ `readyOrders` rồi xử lý lỗi, đó là thất bại ở đơn vị công việc tiếp theo. Nó không tự rollback transaction đã chuyển thông điệp từ `incomingOrders` sang `readyOrders`.

## 6. Phạm vi thay đổi khi chọn loại channel

Xét hai cấu trúc:

~~~text
A. JDBC queue nguồn
       → transactional poller
       → DirectChannel
       → handler ghi JDBC cùng DataSource
~~~

~~~text
B. JDBC queue nguồn
       → transactional poller
       → JDBC queue đích
       → một consumer khác xử lý
~~~

Ở cấu trúc A, nếu handler ghi JDBC đồng bộ và tham gia transaction hiện tại, lỗi từ handler có thể làm rollback cả thao tác nhận lẫn cập nhật nghiệp vụ.

Ở cấu trúc B, transaction đầu tiên bảo vệ việc di chuyển thông điệp giữa hai queue. Consumer phía sau cần transaction và chính sách lỗi của chính nó.

| Đích được forward đến | Việc có thể hoàn tất trong lời gọi hiện tại | Phạm vi cần xem xét tiếp |
| --- | --- | --- |
| `DirectChannel` với handler đồng bộ | Handler trả về kết quả hoặc ném lỗi | Tài nguyên và propagation trong handler |
| JDBC-backed `QueueChannel` cùng DataSource | Ghi thông điệp vào queue trong transaction | Transaction của consumer queue đích |
| `QueueChannel` chỉ dùng bộ nhớ | Thêm phần tử vào bộ nhớ | Không có rollback JDBC cho phần tử đó |
| `ExecutorChannel` dùng executor bất đồng bộ | Bàn giao task cho executor | Kết quả xử lý trên thread khác |
| Adapter gọi HTTP | Nhận phản hồi theo giao thức HTTP | Side effect ở hệ thống HTTP |

Một `ExecutorChannel` có thể có hành vi khác tùy executor và chính sách thực thi; không nên dựa vào khả năng tình cờ chạy trên thread gọi để thiết kế transaction. Khi cần bảo đảm đồng bộ, hãy chọn cấu trúc thể hiện rõ yêu cầu đó.

Một gateway cũng cần được phân tích theo cách này. Chỉ xuất hiện phương thức gateway trong code chưa đủ để kết luận lời gọi, reply và mọi side effect đều thuộc cùng transaction.

## 7. Lỗi khi forward và các kết quả dễ nhầm

### 7.1. Lỗi ghi queue đích trước khi commit

Giả sử việc ghi `readyOrders` gặp lỗi SQL. Nếu exception thoát khỏi xử lý đồng bộ và transaction rollback:

- Thao tác xóa ở `incomingOrders` được hoàn tác.
- Dữ liệu mới ghi ở `readyOrders` trong cùng transaction bị hủy.
- Lần polling tiếp theo có thể nhận lại thông điệp nguồn.

Lần nhận lại là một lần xử lý mới. Không nên mặc định các biến đếm trong RAM hay header đã sửa ở lần thất bại được lưu lại sau rollback.

### 7.2. Lỗi sau khi đã enqueue nhưng trước khi commit

Đây là kịch bản quan trọng để kiểm chứng tính nguyên tử. Enqueue đã trả về không có nghĩa transaction đã commit.

Nếu sau enqueue còn một bước đồng bộ ném lỗi, transaction JDBC chung vẫn có thể rollback cả việc xóa ở nguồn và thêm ở đích. Trong bài thực hành, có thể cố ý tạo lỗi sau lệnh `ready.send(message)` để quan sát trạng thái này.

### 7.3. Catch lỗi rồi tiếp tục

~~~java
try {
    forwardToDestination(message);
}
catch (RuntimeException ex) {
    logger.error("Chuyển tiếp thất bại", ex);
    // Trả về bình thường: transaction có thể vẫn được commit.
}
~~~

Nếu mục tiêu là thử lại từ nguồn, cần để lỗi phù hợp đi ra transaction boundary, hoặc có quyết định rollback rõ ràng. Nếu chọn chuyển thông điệp lỗi sang một queue cách ly rồi commit, đó là một kết quả nghiệp vụ khác và phải được thiết kế có chủ đích.

Đừng nhầm thao tác log với quyết định rollback.

### 7.4. Filter và router có thể kết thúc luồng bình thường

Một filter loại thông điệp mà không ném exception có thể làm lần nhận được commit, dù không có thông điệp nào đến đích mong đợi. Router gửi sang nhánh khác cũng có thể hoàn thành bình thường.

Do đó, “không thấy ở queue đích” chưa chứng minh transaction đã rollback. Cần kiểm tra kết quả được cấu hình cho từng endpoint: loại bỏ, chuyển sang discard channel, định tuyến nhánh khác hay phát sinh lỗi.

## 8. errorChannel, retry và thông điệp lỗi lặp lại

`errorChannel` phục vụ việc phát và xử lý thông tin lỗi; việc có thông điệp tại đó không phải cơ chế hoàn tác dữ liệu.

Trong cấu hình poller đồng bộ thông thường, lỗi đi ra khỏi transaction advice để transaction được xử lý, rồi hạ tầng polling báo lỗi. Nếu bên trong luồng có một advice hoặc recovery handler bắt lỗi và trả về bình thường trước khi lỗi đến transaction advice, kết quả commit/rollback có thể khác.

Vì thế cần phân biệt:

1. Quyết định commit hay rollback của tài nguyên.
2. Việc gửi thông tin lỗi cho luồng giám sát.
3. Chính sách thử lại thông điệp.

Không giả định bản ghi audit hoặc thông điệp gửi từ error flow luôn thuộc transaction ban đầu. Hãy xác định nó chạy lúc nào, trên thread nào và dùng transaction nào.

Khi nguồn đã được khôi phục sau rollback, poller có thể tiếp tục nhận lại thông điệp lỗi. Nếu lỗi là vĩnh viễn, ví dụ payload không thể chuyển đổi, lặp lại vô hạn chỉ tiêu tốn tài nguyên.

Một chính sách xử lý có thể gồm:

- Thử lại có giới hạn đối với lỗi tạm thời.
- Đưa thông điệp không xử lý được vào queue cách ly.
- Lưu số lần thử ở nơi có vòng đời phù hợp, thay vì trông chờ một thay đổi cũng bị rollback.
- Cảnh báo khi cùng business key thất bại liên tục.

Retry quanh handler và retry quanh toàn bộ đơn vị nhận–xử lý có phạm vi khác nhau. Khi kết hợp retry advice với transaction advice, thứ tự advice quyết định một lần retry dùng lại transaction hiện tại hay mở transaction mới. Cần chọn phạm vi trước khi thêm cấu hình.

## 9. Một lịch chạy có phải là một transaction cho nhiều message?

`maxMessagesPerPoll` giới hạn số lần xử lý nhận thông điệp trong một chu kỳ được kích hoạt. Nó không mặc định biến tất cả message của chu kỳ thành một batch transaction.

Với polling endpoint đồng bộ và transaction advice thông thường, advice bao quanh từng lần thực hiện đơn vị receive-and-forward. Vòng lặp lịch chạy gọi đơn vị đó nhiều lần. Có thể đối chiếu cách tạo polling task và vòng lặp trong [AbstractPollingEndpoint](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

Ví dụ, khi không có transaction bên ngoài bao phủ:

~~~text
maxMessagesPerPoll = 3

Lần nhận 1: message A → commit transaction A
Lần nhận 2: message B → commit transaction B
Lần nhận 3: message C → rollback transaction C
~~~

A và B không bị hoàn tác chỉ vì C thất bại. Nếu một `MessageSource` trả về một message có payload là một danh sách, đó lại là một đơn vị nhận chứa nhiều phần tử; cần phân biệt với nhiều lần receive.

Ví dụ chính đặt `maxMessagesPerPoll(1)` để việc quan sát dễ hiểu. Muốn một lô message cùng thành công hoặc cùng thất bại, cần thiết kế batch và transaction boundary tương ứng, thay vì chỉ tăng tham số này.

`receiveTimeout` là thời gian chờ nhận, còn transaction timeout là giới hạn transaction do transaction manager áp dụng. Hai giá trị phục vụ hai mục đích khác nhau. Nếu transaction đã mở trong lúc chờ nguồn, thời gian chờ cũng ảnh hưởng thời lượng giữ tài nguyên của đơn vị công việc.

## 10. Kiểm chứng tính nguyên tử bằng bài thực hành

Kiểm chứng cần quan sát trạng thái tài nguyên sau khi transaction kết thúc. Việc handler được gọi hoặc log xuất hiện chưa đủ.

### 10.1. Kiểm thử store với transaction chủ động

Đoạn kiểm thử sau dùng cùng cấu hình JDBC ở trên. Bridge vẫn dừng nhờ `autoStartup(false)`, nên scheduler không cạnh tranh lấy thông điệp với test.

Test cố ý nhận, gửi thành công, rồi ném lỗi trước commit. Nó kiểm chứng hai queue cùng tham gia transaction JDBC. Nó chưa kiểm chứng wiring transaction advice của poller.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig({
        JdbcLabConfiguration.class,
        ReceiveForwardConfiguration.class
})
@DirtiesContext
class ReceiveForwardRollbackTest {

    @Autowired
    @Qualifier("incomingOrders")
    PollableChannel incoming;

    @Autowired
    @Qualifier("readyOrders")
    PollableChannel ready;

    @Autowired
    @Qualifier("receiveForwardTxManager")
    PlatformTransactionManager transactionManager;

    @Test
    void restoresSourceAndRemovesDestinationInsertOnRollback() {
        // Seed được commit trước transaction dùng để mô phỏng lỗi.
        Message<String> original = MessageBuilder
                .withPayload("order-1042")
                .setHeader("businessKey", "order-1042")
                .build();

        assertTrue(incoming.send(original));

        TransactionTemplate transaction =
                new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class, () ->
                transaction.executeWithoutResult(status -> {
                    Message<?> message = incoming.receive(0);
                    assertNotNull(message);

                    assertTrue(ready.send(message));

                    // Lỗi sau forward nhưng trước commit.
                    throw new IllegalStateException("Lỗi mô phỏng");
                }));

        assertNull(ready.receive(0));

        Message<?> restored = incoming.receive(0);
        assertNotNull(restored);
        assertEquals("order-1042", restored.getPayload());
        assertEquals(
                "order-1042",
                restored.getHeaders().get("businessKey"));

        assertNull(incoming.receive(0));
    }
}
~~~

Không đặt test này trong một transaction test bao ngoài, vì dữ liệu seed cần tồn tại độc lập và ta muốn quan sát kết quả thật của transaction đang kiểm chứng.

Các lệnh `receive(0)` trong phần assertion là thao tác lấy ra, có thay đổi queue. Chúng phù hợp với fixture cô lập này; không dùng chúng như một cách quan sát vô hại trong môi trường thật.

### 10.2. Kiểm chứng cấu hình poller thật

Để kiểm chứng toàn bộ endpoint, cần thêm các kịch bản sử dụng scheduler và transaction advice thực:

| Kịch bản | Cách tạo điều kiện | Điều cần quan sát sau khi hoàn tất |
| --- | --- | --- |
| Commit bình thường | Chạy bridge như demo | Nguồn hết message, đích nhận đúng business key |
| Lỗi tại đích | Dùng đích thử nghiệm ném exception đồng bộ | Message nguồn vẫn nhận lại được |
| Lỗi sau enqueue | Trong flow thử nghiệm, handler ghi queue đích rồi ném lỗi | Nguồn được khôi phục, không còn bản ghi đích của lần lỗi |
| Nguồn bộ nhớ | Thay riêng nguồn bằng `new QueueChannel()` | Rollback JDBC không phục hồi phần tử nguồn |
| Đích bất đồng bộ | Bàn giao sang executor rồi tạo lỗi ở worker | Lỗi worker không tự đảo ngược transaction đã hoàn tất |

Khi thử kịch bản lỗi, cần giới hạn lần chạy hoặc dừng endpoint sau lần thất bại đã được ghi nhận và transaction đã kết thúc. Nếu để poller tự chạy liên tục, một lần nhận lại có thể chen vào lúc đang kiểm tra kết quả.

Dùng latch, tín hiệu hoàn tất có vị trí rõ ràng hoặc cơ chế đợi theo điều kiện với timeout. Không kết luận transaction đã hoàn tất chỉ vì callback lỗi được gọi bên trong handler; callback đó có thể xảy ra trước rollback.

Bổ sung business key trong payload/header để đối chiếu thông điệp theo ý nghĩa nghiệp vụ. Message ID của framework không thay thế khóa chống xử lý trùng của hệ thống.

## 11. Những ranh giới transaction không tự giải quyết

### 11.1. JDBC transaction và HTTP side effect

Giả sử handler gọi HTTP để trừ tiền, sau đó ghi queue đích. Nếu HTTP đã thành công nhưng ghi queue lỗi, JDBC rollback có thể khôi phục nguồn; nó không tự hoàn trả khoản tiền ở hệ thống HTTP.

Khi nhận lại thông điệp, lời gọi HTTP có thể lặp lại. Từ tình huống này, cần cân nhắc khóa idempotency, cơ chế bù hoặc một quy trình nhiều bước phù hợp.

### 11.2. Hai tài nguyên độc lập

Nếu nhận từ broker và ghi database độc lập, phải xác định cơ chế phối hợp được từng tài nguyên hỗ trợ. Các hướng thiết kế có thể bao gồm distributed transaction khi có hỗ trợ và yêu cầu phù hợp, hoặc outbox/inbox kết hợp xử lý idempotent.

Riêng việc bật transaction trên poller không chứng minh hai hệ thống đã có chung một atomic commit.

### 11.3. Gửi sau commit

Chuyển việc gửi ra ngoài sang callback `afterCommit` tránh gửi trước khi database commit, nhưng tạo ra khoảng trống khác: database đã commit mà thao tác gửi tiếp có thể thất bại hoặc tiến trình có thể dừng.

Nếu yêu cầu không bỏ sót việc gửi, cần lưu ý định gửi bền vững và có cơ chế phát lại. Callback sau commit tự nó chưa cung cấp bảo đảm đó.

### 11.4. Exactly-once ở cấp nghiệp vụ

Transaction cục bộ có thể bảo vệ rất tốt việc di chuyển giữa hai JDBC queue của ví dụ. Tuy nhiên, điều đó không tự tạo bảo đảm exactly-once cho toàn bộ nghiệp vụ gồm các consumer, hệ thống từ xa và các lần thử lại.

Hãy định nghĩa việc nào không được lặp theo business key, rồi thiết kế cơ chế lưu và kiểm tra phù hợp cho việc đó.

## 12. Những lỗi cấu hình thường gặp

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Nguồn mất message dù JDBC rollback | Nguồn có phải queue bộ nhớ, hoặc receive xảy ra trước transaction? |
| Dữ liệu ở đích vẫn còn sau lỗi | Đích có dùng cùng DataSource, transaction và propagation không? |
| Lỗi phía sau không làm nguồn nhận lại | Có queue, executor hoặc recovery handler nằm giữa không? |
| Không có gì chạy | Endpoint có đang dừng do `autoStartup(false)` không? |
| JDBC store không khởi động | Schema đã được tạo và query provider đã đúng database chưa? |
| Message lỗi được xử lý lặp lại liên tục | Chính sách retry và cách ly đã xử lý lỗi vĩnh viễn chưa? |
| Đổi cấu hình rồi không thấy dữ liệu cũ | Group ID, database và vùng lưu trữ của store có thay đổi không? |
| Mất dữ liệu sau khi đóng demo | Có đang dùng H2 trong bộ nhớ không? |
| Test khi đúng khi sai | Scheduler có đang cạnh tranh receive với phần assertion không? |

Khi phân tích một flow, hãy vẽ transaction boundary trực tiếp lên các thao tác: bắt đầu transaction, receive, gọi handler, send, commit. Sau đó đánh dấu tài nguyên tham gia và từng chỗ chuyển thread. Với cách đọc này, có thể xác định chính xác một lỗi sẽ hoàn tác việc gì và thông điệp sẽ được xử lý tiếp từ đâu.
