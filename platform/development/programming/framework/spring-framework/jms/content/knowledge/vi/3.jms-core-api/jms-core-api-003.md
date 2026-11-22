# Session và ngữ cảnh gửi nhận đơn luồng trong JMS

## Mục tiêu

Sau bài này, bạn cần hiểu:

1. `Session` là ngữ cảnh (context) có trạng thái để tạo, gửi và nhận message trong **Jakarta Messaging (JMS)**.
2. Quy tắc **một luồng điều khiển tại một thời điểm** áp dụng cho `Session`, `MessageProducer`, `MessageConsumer` và `JMSContext`; kết nối (`Connection`) có thể quản lý nhiều session độc lập.
3. Vì sao listener của **cùng một Session** được thực thi tuần tự, trong khi nhiều session cho phép xử lý đồng thời.
4. Acknowledgement và local transaction thuộc phạm vi **Session**, nên chia sẻ session sai cách có thể làm sai cả tính đúng đắn của xử lý.
5. Spring `JmsTemplate` và listener container quản lý session để mã ứng dụng có thể hoạt động đa luồng mà không cần lưu `Session` trong singleton.

**Thông điệp chính:** *Single-threaded Session* không có nghĩa là toàn bộ ứng dụng JMS chỉ có một thread. Nó nghĩa là **mỗi session tại một thời điểm chỉ được một luồng điều khiển sử dụng**. Muốn tăng concurrency, hãy sử dụng nhiều session/consumer phù hợp; trong Spring, để container quản lý chúng.

## 1. Session đứng ở đâu trong chuỗi API?

JMS còn được gọi là Java Message Service. Với Jakarta Messaging 3.x, các interface thuộc package `jakarta.jms`; ví dụ cũ trước khi chuyển namespace có thể dùng `javax.jms`. Tên module ở đây là Spring Framework JMS, nên ta xét cả API nền tảng và lớp tích hợp của Spring.

~~~text
ConnectionFactory
  └─ Connection (kết nối logic tới JMS provider)
      ├─ Session A — một luồng điều khiển tại một thời điểm
      │    ├─ MessageProducer A1 ──send()──► Queue/Topic
      │    └─ MessageConsumer A1 ◄─receive()/onMessage()── Queue/Topic
      ├─ Session B — có thể hoạt động đồng thời với A
      │    └─ MessageConsumer B1 ◄── Queue
      └─ Session C — có thể hoạt động đồng thời với A, B
           └─ MessageProducer C1 ──► Topic
~~~

| Đối tượng | Vai trò | Có thể chia sẻ như thế nào? |
|---|---|---|
| `ConnectionFactory` | Tạo connection/context theo cấu hình provider | Thường được cấp qua DI và gọi từ nhiều thread; hành vi pool/caching phụ thuộc implementation. |
| `Connection` | Quản lý kết nối tới provider, tạo nhiều session, start/stop delivery | Một connection có thể có **nhiều Session** đang hoạt động đồng thời. Đừng suy luận rằng các session vì chung connection mà phải chạy tuần tự. |
| `Session` | Tạo producer, consumer, destination, message; giữ trạng thái giao nhận, ack và local transaction | **Không dùng đồng thời** từ nhiều luồng điều khiển. |
| `MessageProducer` / `MessageConsumer` | Gửi/nhận message, gắn với session đã tạo ra chúng | Chịu quy tắc tuần tự của session sở hữu; tránh dùng chung producer/consumer giữa các thread. |
| `MessageListener` | Callback `onMessage(Message)` khi message được giao bất đồng bộ | Trong **một session**, các callback được tuần tự hóa; giữa nhiều session có thể chạy song song. |
| `JMSContext` | API đơn giản kết hợp kết nối và session ngầm bên dưới | Cũng chịu hạn chế về luồng như session. |

Một `Session` còn cung cấp các thao tác như `createQueue`, `createTopic`, `createTextMessage`, `createProducer`, `createConsumer`, `commit`, `rollback` và `recover` (tùy chế độ). Session có thể phục vụ nhiều producer/consumer, nhưng **không biến chúng thành những tài nguyên được dùng đồng thời độc lập**.

### Session là ngữ cảnh, không phải thread

- Tạo `Session` **không có nghĩa** bạn đã tạo một `java.lang.Thread` hoặc một executor riêng.
- "Single-threaded" là **hợp đồng truy cập**, không phải cam kết rằng một session chỉ có thể được đụng đến bởi một OS thread duy nhất trong toàn bộ vòng đời. Trong chế độ đồng bộ, việc bàn giao quyền sử dụng tuần tự có thể xảy ra, nhưng tự viết cơ chế bàn giao rất dễ sai; thực hành tốt nhất là quản lý ownership rõ ràng.
- Khi một session có listener bất đồng bộ và connection đã start, luồng giao message do provider quản lý nắm quyền điều khiển session đó. Lúc này **không được** tùy tiện điều khiển session từ thread của ứng dụng.
- Khái niệm này **không tương đương** ThreadLocal, Spring request scope hay một transaction của cơ sở dữ liệu. Session có trạng thái JMS riêng và lifecycle riêng.

## 2. Quy tắc cốt lõi: một luồng điều khiển cho một Session

Jakarta Messaging specification, mục `6.2.5 Threading restrictions on a session`, định nghĩa session để sử dụng **tuần tự bởi một thread tại một thời điểm**. Trừ những thao tác đóng tài nguyên phục vụ shutdown, ứng dụng phải tự tránh truy cập đồng thời.

### 2.1. Cách sử dụng hợp lệ: mỗi worker sở hữu session riêng

~~~text
Thread-1 ─► Session-1 ─► Consumer-1 ─► xử lý đơn #101
Thread-2 ─► Session-2 ─► Consumer-2 ─► xử lý đơn #102
Thread-3 ─► Session-3 ─► Producer-3 ─► gửi sự kiện

           Có thể dùng cùng một Connection.
~~~

Với nhiều worker xử lý cùng một queue, mỗi session/consumer là một đơn vị nhận message độc lập. Nếu một worker đang xử lý một message, worker khác có thể tiếp tục vì nó sở hữu **session khác**.

### 2.2. Cách sử dụng sai: nhiều worker cùng dùng một session

~~~text
Thread-1 ─┐
          ├─► cùng một Session ─► cùng MessageConsumer/Producer  ❌
Thread-2 ─┘

Thread-1 đang gọi consumer.receive(10_000) trong khi
Thread-2 gọi session.createProducer(...), commit(), recover() hoặc receive().
~~~

Đây là vi phạm hợp đồng API. Triệu chứng có thể là exception, treo, race condition, delivery không đúng dự tính hoặc transaction/ack của một luồng tác động lên message của luồng khác. Không thể khẳng định provider nào cũng phát hiện lỗi: một đoạn code chạy có vẻ ổn khi tải nhẹ vẫn không trở thành hợp lệ.

**Phân biệt hai tình huống:**

- `Thread A` gửi xong, kết thúc hoàn toàn rồi `Thread B` dùng session *và không có listener đang điều khiển session*: xét về quy tắc "một luồng tại một thời điểm", đây khác với dùng đồng thời, nhưng cần quản lý hand-off, lifecycle và trạng thái rất cẩn thận. Không nên dùng như thiết kế mặc định.
- `Thread A` và `Thread B` truy cập chồng lấn, hoặc thread ứng dụng động vào session đang thuộc quyền xử lý của asynchronous listener: **sai**. Khóa `synchronized` chỉ bao quanh một phần mã không giải quyết được callback bất đồng bộ, vòng đời, ack và giao dịch.

### 2.3. Một Session có thể có nhiều consumer, nhưng vẫn tuần tự

~~~text
                    Session S
             ┌────────────────────┐
Queue A ────►│ Consumer A         │
Queue B ────►│ Consumer B         │──► cùng luồng điều khiển callback
             └────────────────────┘
                  onMessage(A1)
                  onMessage(B1)
                  onMessage(A2)
                   (không chồng lấn trong cùng S)
~~~

Nếu có nhiều `MessageListener` trên các consumer của **cùng session**, provider phải tuần tự hóa việc gọi các callback. Khi `onMessage(A1)` chưa kết thúc, một callback khác trong cùng session không được thực thi song song. Đây là đảm bảo ở phạm vi session, **không có nghĩa** JMS đảm bảo thứ tự tổng thể giữa nhiều queue/topic hay nhiều producer khác nhau.

Muốn các callback xử lý song song, tạo nhiều session. Khi đó thứ tự **kết thúc xử lý** giữa các worker có thể khác thứ tự message đi vào broker.

## 3. Đồng bộ `receive()` và bất đồng bộ `onMessage()`: chọn một mô hình cho mỗi session

### 3.1. Nhận đồng bộ (synchronous receive)

Một thread gọi `MessageConsumer.receive(timeout)`; nó đợi đến khi có message hoặc hết thời hạn. `receive(0)` đợi vô hạn theo JMS API; trong ứng dụng thực tế nên đặt timeout có chủ đích. `receiveNoWait()` quay về ngay nếu chưa có message.

~~~text
Thread T:
  tạo Session S và MessageConsumer C
  connection.start()
  C.receive(5_000) ──(block)──► Message
  xử lý Message
  ack/commit nếu cần
  gọi receive tiếp hoặc đóng tài nguyên
~~~

Trong khi `receive()` đang block, không đưa session ấy cho thread khác dùng. Không cho hai thread gọi `receive()` trên hai consumer của cùng session đồng thời.

### 3.2. Nhận bất đồng bộ (asynchronous listener)

Một thread cấu hình consumer và `consumer.setMessageListener(listener)`. Khi connection start, provider giao message bằng callback `listener.onMessage(message)`. Session có listener đang chạy được dành cho **luồng điều khiển giao message**.

Trình tự nên dùng khi viết JMS thuần:

1. Tạo connection nhưng **chưa** `start()`.
2. Tạo session, destination, producer, consumer và đăng ký các listener liên quan.
3. Hoàn tất cấu hình trạng thái mà callback sẽ sử dụng.
4. Gọi `connection.start()` để provider bắt đầu delivery.
5. Không gọi `receive()` đồng bộ trên chính session đó; không gọi các phương thức session từ thread ứng dụng khác.
6. Khi dừng, để tầng quản lý lifecycle đóng consumer/session/connection một cách có trật tự.

Đăng ký listener sau khi start khiến message có thể đến trước khi setup hoàn chỉnh, dẫn đến race. JMS có một số ngoại lệ và quy định chi tiết về đăng ký listener bổ sung, nhưng khởi tạo toàn bộ trước `start()` vẫn là lựa chọn dễ hiểu, an toàn.

**Không trộn** `consumer.receive()` với `consumer.setMessageListener(...)` trên cùng session đang hoạt động. Hai mô hình này sử dụng session bằng hai luồng điều khiển khác nhau, trái quy tắc JMS.

### 3.3. Producer trong listener

Đôi khi listener cần tạo và gửi message phản hồi. Trong JMS API thuần, có thể tạo producer trước lúc connection start và để **chính callback đang sở hữu session** sử dụng producer đó tuần tự. Không để worker pool bên ngoài lấy producer ấy rồi gửi đồng thời.

Nếu xử lý message và gửi response cần cùng local JMS transaction, chúng có thể nằm trong **cùng transacted session**; transaction vẫn chỉ bao phủ tài nguyên JMS tương ứng và không tự bao gồm database bên ngoài.

### 3.4. Những ngoại lệ về `close()`

Specification cho phép một số thao tác đóng tài nguyên (`Connection.close`, `Session.close`, `MessageConsumer.close` và những phương thức tương ứng của simplified API) từ thread khác để hỗ trợ shutdown có trật tự. Nhưng ngoại lệ này **không cho phép** gửi/nhận/commit/rollback tùy ý từ nhiều thread. Gọi `close()` trên chính session từ bên trong `onMessage()` có hành vi không hoàn toàn portable, nên tránh; để container hoặc thread quản lý lifecycle quyết định việc đóng.

## 4. Phạm vi của acknowledgement gắn với Session

Một session không chỉ giữ producer/consumer. Nó còn giữ **chuỗi message đã giao**, trạng thái acknowledgement và nếu được bật thì **một chuỗi local transaction**. Điều này giải thích vì sao race về session có hậu quả nghiệp vụ.

| Chế độ session | Khi nào message được xác nhận? | Điều cần nhớ |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | JMS API tự ack khi `receive()` thành công hoặc listener xử lý xong theo quy tắc provider/API | Ứng dụng không kiểm soát tường minh từng thời điểm ack; trong listener container Spring, hành vi còn phụ thuộc cách container nhận và gọi listener. |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `message.acknowledge()` | Theo JMS chuẩn, **ack toàn bộ message đã được session giao**, không chỉ message đang gọi method. |
| `DUPS_OK_ACKNOWLEDGE` | Provider có thể ack trì hoãn | Giảm overhead trong một số trường hợp, nhưng phải chấp nhận khả năng nhận lại message. |
| `SESSION_TRANSACTED` | `session.commit()` ack các message nhận được và hoàn tất các send trong local JMS transaction; `rollback()` hoàn tác | Acknowledgement mode riêng không còn ý nghĩa trong session đã transacted. |

### 4.1. Ví dụ bẫy `CLIENT_ACKNOWLEDGE`

Một session nhận `M1` rồi `M2`. Khi mã gọi `M2.acknowledge()`, **cả M1 và M2 đã được giao bởi session ấy đều được ack** (kể cả nếu ứng dụng chưa hoàn tất xử lý M1). Do đó, không nên lấy nhiều message trong cùng session rồi chuyển cho nhiều thread xử lý độc lập và ack lộn xộn.

Để quản lý đơn vị công việc độc lập, mỗi worker nên có session của riêng mình, hoặc dùng một worker tuần tự với ranh giới ack/commit rõ ràng. Nếu muốn "ack từng message" với semantics đặc thù, phải kiểm tra API/vendor; JMS `CLIENT_ACKNOWLEDGE` không đồng nghĩa per-message ack.

### 4.2. Local transaction cũng nằm trong Session

Với session transacted:

~~~text
Session S:
  nhận message X
  kiểm tra nghiệp vụ
  gửi message Y (nếu dùng chính Session S)
  commit()
     ├─ ack X
     └─ hoàn tất gửi Y trong cùng local JMS transaction
~~~

Nếu xảy ra lỗi trước commit, `rollback()` hủy các send trong transaction và khiến các message nhận được được phục hồi theo cơ chế JMS. Một commit xong thì session chuyển sang transaction tiếp theo.

**Ranh giới quan trọng:** `Session.commit()` không tự commit transaction của PostgreSQL, MongoDB hay HTTP call. Nếu đã ghi DB thành công nhưng JMS rollback, X có thể được phát lại và side effect trên DB bị lặp. Dùng idempotency key/unique constraint hoặc transactional outbox; khi thật sự cần transaction phân tán, phải thiết kế JTA/XA và provider hỗ trợ.

### 4.3. Khôi phục và giao lại

- Trong session **không transacted**, `session.recover()` làm phiên nhận quay lại trạng thái sau ack gần nhất và yêu cầu giao lại những message chưa ack.
- Trong session **transacted**, dùng `rollback()` thay vì `recover()` cho message thuộc transaction đang xử lý.
- Redelivery có thể làm message bị xử lý nhiều lần nếu ứng dụng chưa bảo vệ side effect. Cần dùng `JMSMessageID`, `JMSCorrelationID` hoặc business idempotency key cho việc truy dấu/dedup tùy trường hợp; `JMSMessageID` không thay thế business key trong mọi quy trình.

## 5. Vòng đời Session và tài nguyên

Chuỗi thuần JMS thường là:

~~~text
ConnectionFactory.createConnection()
  → Connection.createSession(mode)
    → Session.createQueue()/createTopic()
    → Session.createProducer()/createConsumer()
      → producer.send(...)
      → connection.start()
      → consumer.receive(...) / listener.onMessage(...)
    → ack/commit/rollback theo chế độ
  → đóng Session
→ đóng Connection
~~~

**Lưu ý:** Có thể gửi khi connection chưa `start()`; `start()` chủ yếu cho phép **nhận** message. Đăng ký listener trước khi start giúp tránh việc nhận trước khi chuẩn bị đủ. `Session.createQueue("name")` tạo đối tượng tham chiếu tên destination; nó **không phải chuẩn JMS để quản trị và tạo vật lý queue trên broker**. Khả năng broker tự tạo queue còn tùy cấu hình.

Trong Java 17+, `Connection`, `Session`, `MessageProducer` và `MessageConsumer` đều hỗ trợ `AutoCloseable`; dùng `try-with-resources` khi ứng dụng tự sở hữu. Đóng session sẽ đóng tài nguyên con của nó; đóng connection cũng đóng các session liên quan. Với Spring, đừng tự đóng session do `JmsTemplate` hoặc listener container đang quản lý.

### 5.1. Lỗi khi đóng giữa callback

Nếu đang xử lý `onMessage`, tránh gọi `session.close()` ngay từ chính callback. Tài nguyên có thể đang được provider/container quản lý, và việc đóng lúc callback chưa trở về có thể có kết quả phụ thuộc implementation. Để container dừng nhận message, đợi các tác vụ đang chạy và đóng resource theo lifecycle cấu hình.

### 5.2. Kết nối có thể tái sử dụng, Session phải có ownership

Một service có thể chia sẻ `ConnectionFactory`, đôi khi chia sẻ connection được provider/pool quản lý, nhưng cần coi mỗi session là **một đơn vị sở hữu riêng** trong thời gian đang dùng. Pool/caching chỉ tái sử dụng sau khi session đã được trả lại, không có nghĩa là phát cùng một session đang hoạt động cho hai thread.

## 6. `JMSContext`: API đơn giản vẫn tuân thủ giới hạn luồng

Jakarta Messaging 2.0+ bổ sung simplified API. `JMSContext` kết hợp việc tạo connection và session ngầm, cung cấp `createProducer()`, `createConsumer()`, `commit()`, `rollback()`, `acknowledge()` và `close()`.

~~~java
// Mã minh họa nằm trong một method có ConnectionFactory hợp lệ.
// Dùng riêng context trong thread hiện tại; cần broker cung cấp queue.
try (JMSContext ctx = connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue q = ctx.createQueue("lesson.context");
    try (JMSConsumer consumer = ctx.createConsumer(q)) {
        ctx.createProducer().send(q, "hello");
        String payload = consumer.receiveBody(String.class, 5_000);
        if (payload == null) {
            throw new IllegalStateException("Hết thời gian đợi message");
        }
        System.out.println(payload);
    }
}
~~~

Đây là **đoạn nằm trong method đã cấu hình/import đúng `jakarta.jms.*`**, chưa phải một chương trình độc lập. Mặc định, `JMSContext` tự start connection khi tạo consumer theo simplified API; vì vậy không cần bắt buộc gọi `ctx.start()` trong ví dụ trên.

Không lưu `JMSContext` vào singleton để nhiều HTTP request thread cùng dùng. Mỗi luồng công việc nên có context/session do nó sở hữu hoặc do framework cấp phát.

**Ngoại lệ theo specification:** `JMSContext.createContext(...)` tạo context khác mà không sử dụng session ngầm của context hiện tại; do đó phương thức này không chịu cùng hạn chế luồng như các thao tác session. Các phương thức đóng context/consumer cũng có ngoại lệ phục vụ shutdown. Đây là ngoại lệ có phạm vi hẹp, **không phải** lời hứa `JMSContext` thread-safe tổng quát.

## 7. Bản đồ tương ứng trong Spring Framework JMS

Spring JMS giúp ứng dụng tập trung vào nghiệp vụ và tự quản lý việc lấy/trả tài nguyên. Nhưng Spring **không thay đổi quy tắc threading của JMS Session**.

### 7.1. `JmsTemplate` có thể là singleton thread-safe

`JmsTemplate` được thiết kế **thread-safe sau khi cấu hình**. Nó giữ tham chiếu `ConnectionFactory` và các thông số, mỗi thao tác sẽ lấy đúng JMS resources và đóng/trả tài nguyên theo ngữ cảnh.

~~~java
// Trong một Spring bean đã inject JmsTemplate:
jmsTemplate.convertAndSend("lesson.queue", "payload");
~~~

Nhiều thread có thể gọi chung `jmsTemplate.convertAndSend(...)`. Việc này **không đồng nghĩa** nhiều thread chia sẻ một `Session` đang active: template/container/transaction manager chịu trách nhiệm cấp session phù hợp.

Các callback của template cũng phải có vòng đời đúng:

~~~java
// Spring quản lý Session trong thời gian callback này.
jmsTemplate.execute(session -> {
    Queue queue = session.createQueue("lesson.queue");
    try (MessageProducer producer = session.createProducer(queue)) {
        producer.send(session.createTextMessage("inside-callback"));
    }
    return null;
});
~~~

Đây là mã minh họa trong class đã inject `JmsTemplate` và import `jakarta.jms.Queue`, `jakarta.jms.MessageProducer`. **Không** giữ `session` trong field/static variable, trả nó qua queue công việc hoặc sử dụng nó sau khi callback kết thúc. Session có thể được Spring đóng hoặc trả vào cache/pool.

### 7.2. `@JmsListener` và listener container

`@JmsListener` đặt lên method xử lý message. `DefaultMessageListenerContainer` và các listener container khác của Spring chịu trách nhiệm tạo consumer, session, quản lý các worker, xử lý lỗi và lifecycle.

~~~text
DefaultMessageListenerContainer (concurrency = 3, ví dụ queue)
   ├─ invoker #1 / Session #1 → listenerBean.handle(M1)
   ├─ invoker #2 / Session #2 → listenerBean.handle(M2)
   └─ invoker #3 / Session #3 → listenerBean.handle(M3)
                                 ^
             Cùng một listener bean có thể bị gọi đồng thời!
~~~

Điểm thường bị bỏ qua: trong một session, callback tuần tự; **cùng một instance bean** (mặc định singleton) có thể nhận lời gọi từ **nhiều session** cùng lúc. Vì vậy method listener phải **thread-safe về trạng thái ứng dụng**: ưu tiên biến cục bộ, dependency thread-safe, transaction đúng scope và tránh trường mutable dùng chung.

Ví dụ sai:

~~~java
// Sai nếu listener chạy đồng thời: biến field chung bị ghi đè.
private String currentOrderId;

@JmsListener(destination = "lesson.orders", concurrency = "3")
public void handle(String orderId) {
    currentOrderId = orderId;
    process(currentOrderId);
}
~~~

Sửa:

~~~java
// Mỗi invocation xử lý ngay tham số riêng.
@JmsListener(destination = "lesson.orders", concurrency = "3")
public void handle(String orderId) {
    process(orderId);
}
~~~

Hai đoạn là **ví dụ rút gọn**, giả định trong bean có method `process(String)`. Chúng minh họa thread-safety của bean, không phải file Java độc lập.

**Lưu ý tăng concurrency:** Với queue, nhiều consumer thường dùng để chia tải. Với Topic non-shared, tăng consumer/subscription có thể tạo nhiều bản nhận trên cùng node; phải kiểm tra semantics topic, shared/durable subscription và provider trước khi tăng `concurrency`.

### 7.3. Spring `SessionAwareMessageListener`

Khi listener cần gửi phản hồi trong **cùng session** đang nhận, Spring có interface `SessionAwareMessageListener` với method `onMessage(Message message, Session session)`. Session được cung cấp chỉ để sử dụng **trong callback đang sở hữu nó**; không chuyển qua executor và không tự đóng.

Dùng `SessionAwareMessageListener` phù hợp khi cần kiểm soát thao tác JMS cụ thể, trong khi `@JmsListener` thích hợp cho phần lớn nghiệp vụ nhận payload.

### 7.4. Transaction gắn với thread hiện tại

`JmsTransactionManager` quản lý local transaction của một `ConnectionFactory`, gắn JMS session với **thread đang tham gia transaction** để `JmsTemplate` có thể tái sử dụng đúng transactional session. Khi kết thúc, tài nguyên được giải phóng/trả lại. Nó **không tự truyền transaction** sang thread mới khi bạn gọi `CompletableFuture.supplyAsync`, `new Thread` hoặc executor khác.

Listener container với `sessionTransacted = true` có thể rollback việc nhận nếu listener ném exception, rồi broker redeliver theo chính sách. Transaction JMS **không tự bao phủ database**. Nếu cần atomicity liên tài nguyên, hãy thiết kế JTA/XA đúng điều kiện hoặc outbox và idempotency.

**Đừng giả định** `@Transactional` sử dụng một transaction manager bất kỳ sẽ bao luôn cả JMS và JDBC. Cần biết cụ thể transaction manager nào được chọn và tài nguyên nào tham gia.

### 7.5. Caching và pooling

`CachingConnectionFactory` có thể cache `Connection`, `Session`, `MessageProducer`, `MessageConsumer` để tránh tạo quá nhiều lần; đây là **tái sử dụng tuần tự khi tài nguyên rảnh**, không làm Session thành thread-safe. Listener container cũng có cache riêng tùy thiết lập. Không chủ động bọc tầng caching chồng nhau khi chưa hiểu ownership, recovery, transaction và session cache size.

Nếu cần tối ưu, quan sát số session active, concurrent consumers, thời gian xử lý, redelivery/DLQ và backlog trước khi tăng pool. Một session duy nhất với nhiều consumer vẫn không tạo ra nhiều callback song song.

## 8. Ví dụ đầy đủ: Java 17 + Spring Boot + Artemis

Ví dụ sau có ba mục đích riêng:

1. Một thread sở hữu **Session thuần JMS** để send rồi nhận đồng bộ.
2. Một thread sở hữu **JMSContext** trong `try-with-resources`.
3. Spring `JmsTemplate` gửi message, còn listener container quản lý **nhiều session** và gọi method bean.

Dự án demo dùng **Java 17**, **Maven** và **Spring Boot 3.5.5**. Cần một **ActiveMQ Artemis broker đang chạy trên `localhost:61616`** và cho phép tạo/truy cập các queue ví dụ; sửa username/password theo broker. Đây là ứng dụng chạy được khi đã chuẩn bị provider, không phải demo JMS chạy mà không có broker.

Cấu trúc:

~~~text
session-thread-demo/
├── pom.xml
└── src/main/
    ├── java/example/SessionThreadDemoApplication.java
    └── resources/application.properties
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-thread-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Đây chỉ là thông tin minh họa cho broker cục bộ; cấu hình lại credentials đúng với broker thực tế và dùng secret management ở môi trường production.

`src/main/java/example/SessionThreadDemoApplication.java`:

~~~java
package example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SessionThreadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionThreadDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ConnectionFactory connectionFactory,
                           JmsTemplate jmsTemplate) {
        return args -> {
            // 1. Một Session chỉ được thread hiện tại sử dụng.
            try (Connection connection = connectionFactory.createConnection();
                 Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("lesson.session.sync");

                try (MessageProducer producer = session.createProducer(queue);
                     MessageConsumer consumer = session.createConsumer(queue)) {

                    producer.send(session.createTextMessage("hello-session"));
                    connection.start(); // Cần cho việc nhận message.

                    Message received = consumer.receive(5_000);
                    if (!(received instanceof TextMessage text)) {
                        throw new IllegalStateException(
                            "Không nhận được JMS TextMessage trong 5 giây");
                    }
                    System.out.println("Session: " + text.getText());
                }
            }

            // 2. JMSContext cũng chỉ dùng trong thread hiện tại.
            try (JMSContext context = connectionFactory.createContext(
                    JMSContext.AUTO_ACKNOWLEDGE)) {

                Queue queue = context.createQueue("lesson.context.sync");
                try (JMSConsumer consumer = context.createConsumer(queue)) {

                    context.createProducer().send(queue, "hello-context");
                    String text = consumer.receiveBody(String.class, 5_000);

                    if (text == null) {
                        throw new IllegalStateException(
                            "Không nhận được JMSContext message trong 5 giây");
                    }
                    System.out.println("JMSContext: " + text);
                }
            }

            // 3. JmsTemplate có thể tái sử dụng trong nhiều Spring bean/thread.
            jmsTemplate.convertAndSend("lesson.spring.listener", "hello-spring");
        };
    }

    @Bean
    DefaultJmsListenerContainerFactory lessonListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2");
        factory.setSessionTransacted(true);
        return factory;
    }

    @JmsListener(destination = "lesson.spring.listener",
                 containerFactory = "lessonListenerFactory")
    public void handle(String payload) {
        // Không dùng field mutable chung; mỗi lần gọi chỉ dùng payload.
        System.out.println("Spring listener: " + payload);
    }
}
~~~

Chạy tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Với broker mới/queue rỗng, ba dòng do chương trình in ra thường có dạng:

~~~text
Session: hello-session
JMSContext: hello-context
Spring listener: hello-spring
~~~

Spring Boot còn in log startup; thread xử lý Spring listener được container quản lý nên **không mặc định** có thứ tự tuyệt đối với mọi log khác. Nếu queue còn message cũ, có consumer khác, hoặc broker không tự tạo queue, output có thể thay đổi hoặc demo không nhận đúng message. Dùng destination dành riêng cho bài tập khi thử nghiệm.

**Giải thích từng phần:**

- `connection.createSession(Session.AUTO_ACKNOWLEDGE)` cấp một session. `producer` và `consumer` cùng session, nhưng runner thao tác **tuần tự** trong một thread.
- `producer.send(...)` được gọi trước `connection.start()` vẫn hợp lệ; `start()` cho phép nhận.
- `consumer.receive(5_000)` chỉ đợi tối đa khoảng 5 giây, trả `null` khi timeout; chương trình kiểm tra cả trường hợp null/sai loại message.
- `JMSContext` kết hợp connection+session, và `context.createConsumer(...)` cho phép connection autostart theo API simplified.
- `JmsTemplate` dùng resource phù hợp cho lời gọi gửi; không bị biến thành một `Session` chung trong field.
- `factory.setConcurrency("2")` cho phép container có hai listener consumers/sessions cho queue; chúng có thể xử lý đồng thời. `setSessionTransacted(true)` cho phép rollback/redelivery khi listener thất bại theo cấu hình provider.
- `handle` không giữ trạng thái mutable trên bean. Nếu có hai message tới gần nhau, các invocation trên cùng instance bean có thể diễn ra song song.

**Điều ví dụ không minh họa:** Nó không chứng minh exactly-once của nghiệp vụ, không tự tạo DB transaction, không tự xử lý retry/DLQ và không đảm bảo cả hai listener instances luôn bận với một message duy nhất. Muốn nhìn rõ concurrency, hãy gửi nhiều message và in tên thread cùng timestamp, nhưng **không dựa vào thứ tự stdout** để suy ra thứ tự xử lý toàn hệ thống.

## 9. Những anti-pattern cần tránh

### 9.1. Lưu Session thành field trong Spring singleton

~~~java
// MÃ SAI VỀ OWNERSHIP — chỉ để nhận diện lỗi.
@Service
class UnsafeSender {
    private final Session sharedSession;

    UnsafeSender(Session sharedSession) {
        this.sharedSession = sharedSession;
    }

    void send(String text) throws JMSException {
        MessageProducer producer = sharedSession.createProducer(
            sharedSession.createQueue("orders"));
        producer.send(sharedSession.createTextMessage(text));
    }
}
~~~

Khi hai request cùng gọi `send`, session bị dùng đồng thời. Đoạn này là minh họa anti-pattern (giả định bean Session được cấp), không phải chương trình độc lập. Thay bằng singleton `JmsTemplate` và gọi `convertAndSend`, hoặc tạo session riêng cho từng luồng sở hữu.

### 9.2. Chuyển Session ra executor từ listener

~~~java
// MÃ SAI — không chuyển Session sang worker thread.
public void onMessage(Message message, Session session) {
    executor.submit(() -> {
        session.commit(); // Sai: dùng Session từ luồng khác.
    });
}
~~~

Nếu cần chạy việc tốn thời gian theo kiểu async, nên cân nhắc cấu trúc job/task riêng. Không ack/commit message trước khi biết kết quả, cũng không để listener return rồi hy vọng callback trên worker khác còn quyền thao tác với cùng session. Với broker-driven concurrency, tăng số session do listener container quản lý thường đơn giản và đúng semantics hơn.

### 9.3. Giữ Message hoặc Producer sau khi session bị đóng

Producer và consumer được sở hữu bởi session. Sau khi session/connection đóng, không dùng lại producer/consumer đã tạo. Các message có thể vẫn truy cập được một số nội dung sau khi đóng, nhưng gọi `acknowledge()` trên message thuộc session đã đóng là không hợp lệ.

### 9.4. Coi `synchronized` là giải pháp mặc định

~~~java
synchronized (sharedSession) {
    sharedSession.commit();
}
~~~

Khóa chỉ có thể tuần tự hóa các luồng **cũng tuân theo khóa đó**. Nó không kiểm soát callback từ provider, không sửa ownership của session đã được listener quản lý và không ngăn commit tác động lên message do công việc khác nhận. Thiết kế đúng là một owner/session hoặc một session mỗi worker, không chia state JMS một cách tùy tiện.

### 9.5. Coi `@JmsListener(concurrency = "5")` là bảo đảm giữ thứ tự

Nhiều session có thể xử lý đồng thời và hoàn tất lệch thứ tự. Với yêu cầu theo `accountId` hoặc `orderId`, cần xem broker có cơ chế partition/grouping, message group, chọn số consumer, khóa nghiệp vụ hay sequencing riêng hay không. JMS không định nghĩa thứ tự tổng thể giữa nhiều session xử lý song song.

### 9.6. Tin rằng AUTO_ACK và transaction bảo đảm mọi side effect một lần

Một listener có thể gọi dịch vụ ngoài thành công rồi JVM dừng trước khi commit JMS. Message có thể đến lại; nếu không có idempotency, hệ thống gửi email/thu tiền/lưu dữ liệu lặp. Cần thiết kế theo failure window thay vì chỉ chọn chế độ acknowledgement.

## 10. Bảng quyết định nhanh

| Nhu cầu | Cách dùng Session phù hợp | Vì sao |
|---|---|---|
| Một thread gửi nhiều message tuần tự | Một session sở hữu trong phạm vi công việc, hoặc `JmsTemplate` | Tránh chi phí và quản lý resource sai. |
| Nhiều request HTTP cùng gửi JMS | Singleton `JmsTemplate` đã cấu hình | Template thread-safe; tự lấy/trả session. |
| Một consumer kéo message bằng `receive()` | Session riêng cho thread polling; đặt timeout hợp lý | Không chồng lấn phương thức trên session. |
| Xử lý song song nhiều message từ queue | Nhiều listener invoker, mỗi invoker dùng session riêng | Mở concurrency mà giữ đúng ranh giới session. |
| Listener cần gửi phản hồi trong cùng JMS transaction | Dùng session hiện tại **bên trong callback** hoặc cấu hình Spring JMS transaction | Cùng transaction JMS; không chuyển session sang thread khác. |
| Kết hợp JMS với database | Idempotency/outbox, hoặc JTA/XA khi phù hợp | Session local transaction chỉ bao phủ JMS. |
| Tái sử dụng tài nguyên để giảm overhead | Container/pool/cache đúng cấu hình | Session chỉ được tái sử dụng khi không còn được dùng. |
| Muốn tất cả message theo thứ tự nghiệp vụ | Xác định scope order, giới hạn concurrency hoặc cơ chế grouping của broker | Thứ tự trên nhiều session không tự được bảo toàn. |

## 11. Checklist thiết kế và quan sát production

Trước khi đưa một JMS consumer vào vận hành, hãy kiểm tra:

1. **Ownership:** ai tạo session, ai đóng, listener/container nào đang giữ session? Có field static/singleton nào lưu trực tiếp `Session`, `JMSContext`, `MessageProducer` hoặc `MessageConsumer` không?
2. **Thread model:** một session có bị gọi bởi executor, virtual thread, request thread hoặc callback ngoài ngữ cảnh không? Một listener bean có mutable shared fields không?
3. **Delivery model:** đang dùng polling `receive()`, provider `MessageListener` hay Spring `@JmsListener`? Có vô tình mix các chế độ trên cùng session không?
4. **Ack/transaction:** mode nào đang bật? `CLIENT_ACKNOWLEDGE` có vô tình ack nhiều message trong cùng session? Local transaction nào đảm bảo atomicity, và tài nguyên nào nằm ngoài transaction?
5. **Failure/replay:** nếu xử lý thành công nhưng ack/commit thất bại, có side effect trùng không? Retry/backoff/DLQ được thiết kế ở broker/container ra sao?
6. **Concurrency và order:** mỗi listener có bao nhiêu session active? Số instance có làm đổi thứ tự xử lý? Queue/Topic và durable/shared subscription có semantics phù hợp không?
7. **Lifecycle:** khi ứng dụng dừng, đang có callback chạy hoặc `receive()` block không? Container có graceful stop và tránh đóng resource từ sai thread không?
8. **Quan sát:** thu thập backlog/queue depth, active consumers, thời gian xử lý, lỗi listener, số lần redelivery, transaction rollback và DLQ; không chỉ nhìn số lượng message gửi thành công.

### Cách tự tái hiện vấn đề

- Chạy một listener container concurrency 1, gửi nhiều message và làm listener xử lý chậm: trong cùng invoker/session, callback sẽ không chồng lấn.
- Tăng concurrency lên 2 hoặc 3 trên **queue**, gửi đủ message và quan sát nhiều invoker xử lý song song: các invoker dùng session khác nhau; thứ tự stdout có thể đổi.
- Tạo test riêng với `CLIENT_ACKNOWLEDGE`: nhận hai message trong cùng session, ack message thứ hai rồi quan sát tác động ack lên cả session. Không dùng queue production để thử vì sẽ thay đổi trạng thái delivery thật.
- Buộc listener ném lỗi khi dùng `sessionTransacted=true` để quan sát rollback/redelivery; cấu hình retry/DLQ và giới hạn số lần thử để tránh loop vô hạn.

## 12. Câu hỏi tự kiểm tra

**1. Một Connection có hai Session, chúng có thể nhận message song song không?** Có. Quy tắc single-thread áp dụng **cho từng session**, không buộc mọi session chung connection phải chạy cùng một thread.

**2. Một Session có hai MessageConsumer với hai MessageListener thì callback có chạy đồng thời không?** Không. Những callback được giao qua cùng session phải được tuần tự hóa.

**3. Đã có `JmsTemplate` singleton, nhiều request cùng gọi `convertAndSend` có vi phạm không?** Không, nếu template đã cấu hình đúng; Spring quản lý JMS resources cho mỗi thao tác.

**4. Một `@JmsListener` bean singleton cấu hình concurrency 4 có thể bị gọi cùng lúc không?** Có. Bốn session/invoker khác nhau có thể gọi cùng một bean song song, nên trạng thái của bean phải thread-safe.

**5. Vì sao `message.acknowledge()` với CLIENT_ACKNOWLEDGE không phải ack riêng từng message?** Vì acknowledgement được định nghĩa theo **session**, bao phủ các message đã giao trong session đó.

**6. Có thể dùng JMSContext chung giữa các thread vì API trông đơn giản hơn Session không?** Không. Nó chứa session ngầm và chịu cùng hạn chế threading, trừ những phương thức đặc biệt được specification chỉ rõ.

**7. Tại sao callback của một listener không nên submit `session.commit()` sang executor?** Session có ownership và transaction state gắn với luồng điều khiển đang xử lý message; executor thread khác không có quyền dùng song song.

**8. Rollback JMS có đảo ngược được một lệnh INSERT vào DB độc lập không?** Không. Phải có transaction coordination phù hợp hoặc thiết kế idempotency/outbox.

## 13. Tài liệu chính thức để đối chiếu

- [Jakarta Messaging 3.1 specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — đặc biệt các mục **6.2.5** (threading restrictions on Session), **6.2.6** (JMSContext), **6.2.7** (transactions), **6.2.10** (acknowledgement), **6.2.13–14** (serial/concurrent delivery).
- [Jakarta JMS Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session) — tài nguyên, các mode ack và vòng đời.
- [Jakarta JMS MessageListener API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener) — callback tuần tự theo session.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `JmsTemplate` thread-safe, caching và transaction manager.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — listener container, `SessionAwareMessageListener` và local transaction.
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — cấu hình Spring Boot, `JmsTemplate`, `@JmsListener`.

**Ghi nhớ cốt lõi:** `Session` là một *đơn vị trạng thái giao nhận và giao dịch* có quyền sở hữu tuần tự. **Một session → một luồng điều khiển tại một thời điểm; nhiều session → khả năng xử lý đồng thời.** Spring cung cấp template và listener container để thực thi quy tắc này mà mã nghiệp vụ không cần tự chia sẻ session.
