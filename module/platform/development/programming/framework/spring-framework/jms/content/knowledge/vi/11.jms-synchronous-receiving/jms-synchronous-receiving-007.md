# Nhận trong Session có giao dịch (Transacted Session) — Spring Framework JMS

## 1. Mục tiêu và phạm vi

Trong mô hình **nhận đồng bộ** (synchronous receive) của Jakarta Messaging (JMS), thread ứng dụng gọi `MessageConsumer.receive(...)` hoặc `JmsTemplate.receive(...)` và chờ một message. Nếu việc nhận được thực hiện bên trong **Session có giao dịch** (*transacted Session*), message **chưa được xác nhận chỉ vì `receive()` trả về**. Việc xác nhận các message đã nhận trong transaction xảy ra khi **commit**, còn **rollback** đưa các message đã nhận trở lại diện có thể giao lại.

Sau bài học, bạn có thể:

- Phân biệt **đã nhận**, **đã xử lý nghiệp vụ**, **đã commit/acknowledge JMS**.
- Tạo local JMS transaction bằng `Session.SESSION_TRANSACTED`, dùng `receive(timeout)`, `commit()` và `rollback()`.
- Gộp nhiều lần nhận hoặc kết hợp **receive + send** vào cùng một JMS transaction.
- Hiểu message redelivery, `JMSRedelivered`, `JMSXDeliveryCount`, retry, DLQ và thời điểm lỗi.
- Tránh nhầm giữa `JmsTemplate.setSessionTransacted(true)` **không có transaction manager** và `JmsTemplate.receive()` bên trong **`JmsTransactionManager`/`@Transactional`**.
- Nắm giới hạn của local JMS transaction đối với database, HTTP, email, payment, idempotency và trường hợp commit outcome không rõ.
- Chạy một ví dụ Java 17, Spring Boot và ActiveMQ Artemis để tự quan sát **nhận → rollback → nhận lại → commit**.

**Điểm cốt lõi:** Một transaction JMS chỉ đảm bảo atomicity cho **các thao tác JMS thuộc chính transaction đó**. Nó không tự động bao trùm toàn bộ công việc của một method Java hay transaction trong database.

## 2. Nhận đồng bộ khác gì nhận bất đồng bộ?

### 2.1. `receive()` chiếm thread gọi

Với JMS classic API:

~~~java
Message m = consumer.receive(5_000L);
~~~

- Nếu có message phù hợp trước thời hạn, lời gọi trả về `Message`.
- Nếu hết 5.000 ms chưa có message, lời gọi trả về `null`.
- `receive(0)` chờ vô hạn theo JMS API; tránh trong request thread nếu không có cơ chế hủy/dừng.
- `receiveNoWait()` trả ngay message đang sẵn có hoặc `null`.
- Khi dùng classic API, cần `connection.start()` để kích hoạt delivery tới consumer.

Ngược lại, một `@JmsListener` được listener container gọi **bất đồng bộ**. Nó cũng có thể chạy trong JMS transaction, nhưng đó là **luồng khác** với việc tự gọi `receive()`.

### 2.2. Ba mốc cần phân biệt

~~~text
Broker                      Synchronous consumer
  |                                  |
  +--------- deliver M ------------->|
  |                                  | receive() trả M
  |                                  | BUSINESS PROCESSING
  |                                  |
  |   nếu session transacted         |
  |<--------- commit() --------------|  xác nhận M
  |                                  |
  |         hoặc                     |
  |<--------- rollback() ------------|  M có thể được redeliver
~~~

`receive()` hoàn tất chỉ có nghĩa **message đã được giao đến application**. Tính bền vững của tác động nghiệp vụ và trạng thái ACK phụ thuộc transaction boundary. Trong transacted Session, việc gọi `message.acknowledge()` **không thay thế** `session.commit()`.

## 3. Bản chất của JMS transacted Session

### 3.1. Một chuỗi các transaction

Một transacted Session quản lý một chuỗi transaction cục bộ:

~~~text
create transacted Session
          |
          v
Transaction T1 đang mở
   +-- receive M1
   +-- receive M2
   +-- send M3
          |
    commit / rollback
          |
          v
Transaction T2 bắt đầu
   +-- receive ...
          |
    commit / rollback
          |
         ...
~~~

Theo Jakarta Messaging specification, một Session transacted bao gồm cả **input stream** (những message nhận) và **output stream** (những message gửi):

- **Commit:** các message đã nhận trong transaction được acknowledged; những message đã gửi trong transaction được commit và có thể được chuyển đi.
- **Rollback:** những message đã gửi trong transaction bị hủy; những message đã nhận được khôi phục để provider có thể giao lại.
- Mỗi Session có một chuỗi transaction, không phải nhiều transaction chạy đồng thời trong cùng Session.
- Sau `commit()` hoặc `rollback()`, Session chuyển sang transaction kế tiếp.
- Khi Session có một local transaction chưa hoàn tất mà bị `close()`, spec yêu cầu **rollback transaction chưa commit**.

Nếu ứng dụng vừa nhận M1, M2, vừa gửi M3 trong **cùng Session transaction**, nó có thể commit cả ba thao tác cùng nhau. Nhưng nếu M3 được gửi bằng một Session khác, bạn **không thể** suy ra chúng nằm trong cùng local transaction.

### 3.2. Mức đảm bảo

| Điều bạn muốn | JMS local transacted Session có đảm bảo không? |
|---|---|
| Nhận M nhưng chưa ACK trước khi commit | Có |
| Rollback làm M trở lại diện có thể phát lại | Có, theo JMS và policy của provider |
| Nhận M và gửi phản hồi X trong **cùng JMS Session/transaction** là một đơn vị JMS atomic | Có |
| Rollback JDBC transaction cùng lúc | Không, nếu chỉ dùng JMS local tx |
| Rollback HTTP call/payment/email đã thành công | Không |
| Không bao giờ có duplicate business effect khi có network failure | Không |
| `JmsTemplate.receive()` tự giữ transaction mở cho mọi code sau nó | Không mặc định |
| Message được phát lại đúng ngay lần `receive()` kế tiếp | Không có bảo đảm chung về thứ tự/thời gian |

### 3.3. Acknowledgement mode bị bỏ qua trong transacted Session

Với classic API, tạo Session bằng:

~~~java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
~~~

Đối số thứ nhất `true` bật local transaction trong Java SE/standalone environment. Khi đã transacted, acknowledgement mode **bị bỏ qua**: `Session.SESSION_TRANSACTED` ở đối số thứ hai chỉ giúp diễn đạt rõ ý định.

Bạn cũng có thể gọi:

~~~java
Session session = connection.createSession(
        Session.SESSION_TRANSACTED);
~~~

Đây là overload một tham số từ JMS 2.0.

**Không nhầm `Session.SESSION_TRANSACTED` với `Session.CLIENT_ACKNOWLEDGE`:**

- Trong `CLIENT_ACKNOWLEDGE` không giao dịch, gọi `message.acknowledge()` xác nhận **các message đã giao trong Session**.
- Trong `AUTO_ACKNOWLEDGE`, provider tự xác nhận sau điều kiện thành công của synchronous receive.
- Trong **transacted Session**, acknowledgement đến từ **commit**; gọi `message.acknowledge()` bị bỏ qua.
- Với session không giao dịch, `Session.recover()` yêu cầu nhận lại message chưa ack; với transacted Session, dùng **rollback** thay vì `recover()`.

## 4. Tạo transacted Session với Jakarta Messaging

### 4.1. Classic API: mở connection, Session và consumer

Đoạn sau là **snippet** bên trong method có `ConnectionFactory` đã được cấu hình; chưa phải file hoàn chỉnh có `main`:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(
             true, Session.SESSION_TRANSACTED)) {

    Queue queue = session.createQueue("orders.queue");

    try (MessageConsumer consumer = session.createConsumer(queue)) {
        connection.start();

        Message message = consumer.receive(5_000L);
        if (message == null) {
            session.rollback();
            return;
        }

        try {
            processMessage(message);
            session.commit();
        } catch (Exception error) {
            session.rollback();
            throw error;
        }
    }
}
~~~

Giải thích:

1. `createConnection()` lấy connection theo provider.
2. `createSession(true, ...)` tạo **local JMS transaction**.
3. `createQueue("orders.queue")` tạo đối tượng tham chiếu `Queue`; destination vật lý phải được provision hoặc provider/broker cho auto-create.
4. `createConsumer(queue)` tạo consumer gắn với Session.
5. `connection.start()` cho phép delivery.
6. `receive(5_000L)` block nhiều nhất 5 giây và có thể trả `null`.
7. Application xử lý message **khi transaction vẫn mở**.
8. Xử lý thành công → `commit()`; lỗi có thể retry → `rollback()`.

`processMessage(...)` là hàm nghiệp vụ giả định. Khi làm sản phẩm thật, cần xác định rõ side effect nào thuộc JMS transaction và side effect nào nằm ngoài phạm vi.

### 4.2. Không dùng Session giữa nhiều thread

Một `Session` được thiết kế cho **một luồng điều khiển tại một thời điểm**. Không nên đặt Session hoặc `MessageConsumer` vào singleton rồi cho các HTTP request/thread gọi `receive()`, `commit()` và `rollback()` đồng thời.

~~~text
ĐÚNG:
  Thread A → Session A → receive/commit
  Thread B → Session B → receive/rollback

SAI:
  Thread A ─┐
            ├─ Session X → race giữa receive và commit
  Thread B ─┘
~~~

Để tăng concurrency, tạo nhiều Session/consumer có ownership rõ hoặc dùng Spring listener container. `CachingConnectionFactory` và pool có thể **tái sử dụng tài nguyên khi không còn đang dùng đồng thời**, nhưng không biến một Session thành thread-safe.

### 4.3. Simplified API `JMSContext`

JMSContext cung cấp cách diễn đạt ngắn hơn:

~~~java
try (JMSContext context =
        connectionFactory.createContext(
                JMSContext.SESSION_TRANSACTED)) {

    Queue queue = context.createQueue("orders.queue");
    JMSConsumer consumer = context.createConsumer(queue);

    Message message = consumer.receive(5_000L);
    if (message == null) {
        context.rollback();
    } else {
        processMessage(message);
        context.commit();
    }
}
~~~

Đây cũng là snippet Java SE/standalone. Nếu `processMessage` ném exception và `JMSContext` đóng khi transaction còn mở, transaction sẽ rollback; để rõ ý định có thể bắt lỗi và gọi `context.rollback()` chủ động.

Trong Jakarta EE container đang quản lý JTA, không suy diễn rằng local transaction API hoạt động giống Java SE; giao dịch thuộc trách nhiệm hạ tầng container và JTA.

## 5. Commit: lúc nào message mới thực sự được ACK?

### 5.1. Timeline

~~~text
t0  connection.start()
t1  consumer.receive(5000) gọi
t2  receive trả Message M
    M đang được nhận trong transaction, CHƯA ACK
t3  business logic xử lý M
t4  session.commit() trả về thành công
    ACK đối với M đã được commit
t5  transaction tiếp theo bắt đầu
~~~

Nếu không có exception trước t4 nhưng ứng dụng **quên commit**, message có thể chưa được ack và sẽ xuất hiện lại khi rollback/close/recovery. Logging “processed” trước commit **không** phải bằng chứng “committed”.

### 5.2. Nếu nhận nhiều message trong một transaction

~~~java
// Snippet: session là transacted Session.
Message first = consumer.receive(2_000L);
Message second = consumer.receive(2_000L);

if (first != null && second != null) {
    processMessage(first);
    processMessage(second);
    session.commit();   // ACK cả hai trong JMS transaction.
} else {
    session.rollback(); // Message nào đã nhận trong tx được khôi phục.
}
~~~

Nếu M1 đã gọi một HTTP service thành công nhưng M2 thất bại, rollback sẽ khiến M1 có thể được phát lại. HTTP side effect **không tự rollback**. Cần idempotency hoặc tránh gom những business effect không thể bù trừ.

### 5.3. “Commit một lần cho N message” có tradeoff

Gom batch có thể giảm số lần commit và tăng throughput nếu broker có overhead transaction đáng kể, nhưng:

- Một lỗi ở cuối batch có thể khiến toàn batch được phát lại.
- Transaction dài giữ nhiều tài nguyên.
- Transaction timeout có thể dẫn đến rollback.
- Dễ phát sinh hiệu ứng nghiệp vụ trùng lặp nếu xử lý DB/API không idempotent.
- Khi lấy batch bằng `receive(timeout)`, phải có chính sách rõ: commit partial batch hay rollback nếu không đủ N message.

Không có kích thước batch chung tối ưu. Đo commit latency, broker depth/delivering count, retry, CPU và throughput trên workload của chính hệ thống.

## 6. Rollback và redelivery

Khi `session.rollback()` được gọi trên transacted Session:

- Những lần receive trong transaction được khôi phục.
- Broker/provider có thể phát lại message theo redelivery policy.
- Những lần send trong cùng transaction bị hủy.
- Transaction kế tiếp có thể bắt đầu trên cùng Session.

~~~text
Queue lưu M
    |
    v
receive M: count=1, redelivered=false
    |
    +-- business exception
    |
session.rollback()
    |
    +-- broker redelivery delay / policy
    |
    v
receive M: count=2, redelivered=true
    |
    +-- xử lý thành công
    |
session.commit() → ACK
~~~

Hai header/property hữu ích để điều tra:

~~~java
boolean redelivered = message.getJMSRedelivered();
int deliveryCount =
        message.getIntProperty("JMSXDeliveryCount");
String messageId = message.getJMSMessageID();
~~~

Lần đầu thường có `JMSRedelivered=false`, `JMSXDeliveryCount=1`. Khi phát lại do rollback, provider phải đánh dấu redelivered và tăng delivery count theo specification. Tuy vậy, count không phải chứng cứ tuyệt đối về số lần business code đã chạy; provider có thể giao message nhưng JVM chết trước lúc handler bắt đầu, hoặc có tình huống failover làm count không chính xác tuyệt đối.

**Không kết luận “rollback xong thì receive ngay lần sau chắc chắn là M”.** Broker có thể áp dụng delay/backoff, priority, consumer cạnh tranh, TTL/expiry và DLQ. Nhận lại có thể muộn hoặc không còn ở queue ban đầu.

### 6.1. Exception Java tự nó không phải rollback

Trong raw JMS:

~~~java
Message m = consumer.receive(5_000L);
throw new IllegalStateException("business failed");
~~~

Ném exception **không tự gọi `session.rollback()` ngay lập tức**. Session vẫn có transaction cho đến khi owner commit, rollback hoặc đóng. `close()` của transacted Session yêu cầu rollback transaction đang mở, nhưng ứng dụng nên có nhánh rollback rõ thay vì dựa vào cleanup.

### 6.2. Commit outcome không rõ

Nếu mạng đứt khi `session.commit()` đang thực hiện, broker **có thể đã commit** nhưng client chưa nhận được response; hoặc transaction đã rollback. Jakarta Messaging ghi nhận trường hợp không thể xác định chắc kết quả.

~~~text
Client                  Broker
  |------ commit() ------>|
  |                       | có thể commit thành công
  |       network down    |
  x                       |
Client không chắc transaction đã commit hay chưa
~~~

Không tự động tái thực hiện side effect thanh toán hay ghi DB khi kết quả JMS không rõ. Dùng idempotency key, state reconciliation và quan sát broker/retry.

## 7. Nhận + gửi trong cùng transaction JMS

Một điểm mạnh của JMS transacted Session là **input + output của cùng Session** được commit hoặc rollback cùng nhau:

~~~text
orders.in ──receive──► Transacted Session
                           |
                           +── send(OrderValidated) ──► orders.validated
                           |
                           +── commit:
                               ACK input + publish output
                           |
                           +── rollback:
                               input được khôi phục; output bị hủy
~~~

Snippet:

~~~java
Queue inputQueue = session.createQueue("orders.in");
Queue outputQueue = session.createQueue("orders.validated");

try (MessageConsumer consumer = session.createConsumer(inputQueue);
     MessageProducer producer = session.createProducer(outputQueue)) {

    Message input = consumer.receive(5_000L);
    if (input != null) {
        try {
            String id = input.getStringProperty("orderId");
            TextMessage output =
                    session.createTextMessage("validated:" + id);

            producer.send(output); // Gửi trong JMS transaction.
            session.commit();      // ACK input và commit output.
        } catch (JMSException | RuntimeException ex) {
            session.rollback();
            throw ex;
        }
    }
}
~~~

Code là snippet trong method có `session` được tạo transacted và connection đã `start()`. `JMSException` cần được khai báo/handle ở method bao ngoài. `producer` và `consumer` dùng **cùng Session**, là điều kiện để thao tác thuộc một local JMS transaction.

### 7.1. Tránh deadlock request-reply cùng transaction

Anti-pattern:

~~~text
Session T:
    send(request)     (request chưa được commit)
    receive(reply)    (đợi responder xử lý request)
    commit()          (không chạy tới vì đang chờ reply)
~~~

Responder thường chưa thấy request vì nó chưa commit. Nếu caller đợi reply trước commit, sẽ gây **deadlock logic** hoặc hết timeout. Cách đúng là commit request trước rồi nhận reply ở transaction tiếp theo, có correlation ID và timeout.

### 7.2. Queue và Topic không đổi tính chất vì transaction

JMS transaction điều khiển ACK/commit. Nó **không tự biến** Topic non-durable subscriber thành durable subscriber, không vô hiệu TTL, không đảm bảo mỗi consumer xử lý thành công, và không áp đặt một retry policy chung cho mọi broker.

## 8. Một khác biệt quan trọng của Spring `JmsTemplate`

Spring cho phép nhận đồng bộ bằng:

~~~java
Message raw = jmsTemplate.receive("orders.queue");
Object converted = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Các lời gọi này block caller theo cấu hình `receiveTimeout`. Có thể cấu hình:

~~~java
@Bean
JmsTemplate pollingTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setReceiveTimeout(5_000L);
    return t;
}
~~~

Tuy nhiên, **phải phân biệt hai cách dùng transaction**.

### 8.1. Chỉ gọi `setSessionTransacted(true)` chưa đủ bảo vệ business code sau receive

~~~java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setSessionTransacted(true);
t.setReceiveTimeout(5_000L);

Message m = t.receive("orders.queue");
processMessage(m); // Phần này KHÔNG được bao trong local tx của receive.
~~~

Khi **không có Spring-managed transaction đang hoạt động**, template tạo một local transacted Session cho operation. Theo cách Spring `JmsTemplate` thực thi nhận, nếu Session được tạo cục bộ bởi template, Spring **commit sau receive** rồi mới trả message cho caller.

Hệ quả:

- `receive()` trả message thì local JMS receive đã được commit.
- Code `processMessage(m)` chạy **sau ranh giới transaction đó**.
- Exception phát sinh trong `processMessage` không thể làm rollback lần nhận đã commit.
- `setSessionTransacted(true)` trên template **không tự động tạo một transaction dài bao quanh mọi dòng code nằm bên ngoài method `receive()`**.
- Với `receiveAndConvert()`, cần hiểu rõ bước conversion và transaction boundary; không suy rằng converter failure luôn còn có thể rollback bằng cách bật flag cục bộ này.

Đây là lỗi kiến trúc rất thường gặp: **“session có giao dịch” không đồng nghĩa “toàn bộ quá trình xử lý nghiệp vụ nằm trong một giao dịch”**.

### 8.2. Khi nào nên dùng `JmsTransactionManager`?

Khi cần:

~~~text
Spring-managed JMS transaction bắt đầu
  |
  +-- JmsTemplate.receive(queue)
  |
  +-- validate / business logic
  |
  +-- có thể JmsTemplate.send(output)
  |
  +-- commit hoặc rollback khi toàn bộ scope kết thúc
~~~

Spring cung cấp `JmsTransactionManager`, quản lý **local transaction** cho một `ConnectionFactory` và bind JMS Session với thread. `JmsTemplate` phát hiện session đã được bind và sử dụng nó thay vì tự commit local receive operation trước khi caller xử lý xong.

## 9. Spring `JmsTransactionManager` + `@Transactional`

### 9.1. Cấu hình transaction manager

Trong một class cấu hình Spring:

~~~java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Cần import `org.springframework.jms.connection.JmsTransactionManager`, `jakarta.jms.ConnectionFactory` và `org.springframework.context.annotation.Bean`. Với Boot, cũng cần đảm bảo infrastructure transaction annotation được kích hoạt, ví dụ bằng cấu hình Spring Boot/`@EnableTransactionManagement` khi cần.

`JmsTransactionManager` và `JmsTemplate` **phải tham chiếu cùng ConnectionFactory thích hợp**, nếu không việc bind tài nguyên với thread có thể không đúng.

### 9.2. Transaction bao trọn synchronous receive và business logic

~~~java
@Service
public class TransactionalOrderPoller {

    private final JmsTemplate template;

    public TransactionalOrderPoller(JmsTemplate template) {
        this.template = template;
    }

    @Transactional("jmsTransactionManager")
    public boolean pollAndProcess() {
        Message m = template.receive("orders.queue");
        if (m == null) {
            return false;
        }

        try {
            String eventId = m.getStringProperty("eventId");
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("Missing eventId");
            }

            // Gọi logic xử lý ở đây, trước khi JMS commit.
            System.out.println("processing eventId=" + eventId);
            return true;
            // Method trở về bình thường => manager commit JMS.
        } catch (JMSException ex) {
            throw new IllegalStateException("JMS read failed", ex);
            // RuntimeException => mặc định rollback.
        }
    }
}
~~~

Đây là một **class ví dụ**, cần import `jakarta.jms.Message`, `jakarta.jms.JMSException`, `org.springframework.jms.core.JmsTemplate`, `org.springframework.stereotype.Service` và `org.springframework.transaction.annotation.Transactional`. Hàm in log chỉ minh họa; production cần xử lý idempotent thật sự.

Luồng:

1. Bean Spring **khác** gọi `pollAndProcess()` qua Spring transaction proxy.
2. Manager bắt đầu local JMS transaction.
3. `JmsTemplate.receive()` dùng Session được bind trong transaction.
4. Business logic chạy khi JMS transaction vẫn mở.
5. Kết thúc bình thường → manager commit và ACK message đã nhận.
6. `RuntimeException`/`Error` theo rollback rule mặc định → manager rollback, message có thể được giao lại.

**Không được bắt exception rồi return success** nếu muốn rollback. Spring sẽ thấy method hoàn tất và có thể commit. Nếu không muốn throw, cần đánh dấu transaction rollback-only một cách có chủ đích.

### 9.3. Checked exception và proxy

Spring mặc định rollback trên unchecked exception (`RuntimeException`, `Error`), còn checked exception thường không kích hoạt rollback trừ khi cấu hình. Có thể dùng:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = Exception.class)
public void pollAndProcessChecked() throws Exception {
    Message m = template.receive("orders.queue");
    processChecked(m);
}
~~~

Đây chỉ là **method snippet** cần `processChecked` và `template`. Đừng bật `rollbackFor=Exception.class` một cách máy móc nếu có checked exception biểu thị kết quả nghiệp vụ thành công một phần; chọn rule theo error taxonomy.

Với Spring AOP proxy, gọi `this.pollAndProcess()` trong cùng bean có thể **bỏ qua proxy**, nên transaction không được tạo. `@Transactional` cũng không có tác dụng nếu class tự tạo bằng `new` thay vì bean do Spring quản lý.

### 9.4. Transaction gắn với thread

~~~text
Thread A, Spring JMS Tx A
    JmsTemplate.receive() -> Session A
    process()
    JmsTemplate.send()    -> Session A
    commit/rollback Tx A

Thread B, Spring JMS Tx B
    JmsTemplate.receive() -> Session B
    process()
    commit/rollback Tx B
~~~

Không giả định transaction của Thread A tự lan sang `ExecutorService`, `CompletableFuture` hoặc callback chạy thread khác. Khi cần nhiều worker, mỗi worker tạo transaction riêng.

### 9.5. `TransactionTemplate` cho chương trình muốn quản lý scope

~~~java
TransactionTemplate tx = new TransactionTemplate(jmsTransactionManager);

Boolean didWork = tx.execute(status -> {
    Message m = jmsTemplate.receive("orders.queue");
    if (m == null) {
        return false;
    }

    try {
        String eventId = m.getStringProperty("eventId");
        if (eventId == null) {
            status.setRollbackOnly();
            return false;
        }
        return true;
    } catch (JMSException ex) {
        throw new IllegalStateException(ex);
    }
});
~~~

Đây là snippet có các dependency được inject sẵn. `TransactionTemplate` là một cách rõ ràng để giữ **receive + xử lý** trong một transaction JMS đúng scope. Nó không kéo transaction JDBC vào local JMS transaction.

## 10. JMS local transaction KHÔNG phải DB transaction

### 10.1. Cửa sổ lỗi DB commit trước JMS commit

~~~text
JMS receive M trong local transaction
          |
          v
Cập nhật database
          |
          v
DB COMMIT thành công
          |
          v
JVM / network hỏng trước JMS COMMIT
          |
          v
Broker rollback/recovery, redeliver M
          |
          v
Một consumer khác có thể chạy side effect DB lần nữa
~~~

Local `JmsTransactionManager` quản lý JMS Session; nó không tự rollback JDBC. Ngược lại, transaction manager của database không tự xác nhận message JMS. Đây là lý do **JMS transacted receive chưa đủ tạo exactly-once business effect**.

### 10.2. Idempotency key phải là ID nghiệp vụ ổn định

Producer nên gắn `eventId` có nghĩa độc lập với ID do JMS provider cấp, ví dụ `eventId=order-created:42:v1`. Một JMSMessageID riêng có thể khác khi producer gửi trùng logical event.

Consumer có thể dùng bảng `processed_events` với unique constraint và business update trong **cùng database transaction**. PostgreSQL ví dụ:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('order-created:42:v1')
ON CONFLICT (event_id) DO NOTHING;

-- CHỈ khi INSERT mới thật sự thêm một dòng,
-- ứng dụng mới chạy business UPDATE trong cùng DB transaction.
UPDATE orders
SET state = 'PROCESSED'
WHERE id = 42;

COMMIT;
~~~

**Quan trọng:** Script trên chỉ minh họa ý tưởng; **không chạy vô điều kiện hai statement** rồi tưởng đã chống trùng. Ứng dụng cần kiểm tra số dòng insert và chỉ làm business update khi event chưa được xử lý, cả hai trong một DB transaction.

Nếu DB commit thành công nhưng JMS rollback, lần nhận tiếp theo thấy eventId đã xử lý và kết thúc thành công để JMS commit/ack, không thực hiện side effect thêm lần nữa. Đối với payment/email/HTTP external API, cần idempotency token mà dịch vụ đích hỗ trợ hoặc một kiến trúc outbox/saga phù hợp.

### 10.3. Khi nào cân nhắc JTA/XA?

Với yêu cầu một transaction bao gồm JMS và database, có thể dùng JTA/XA nếu transaction manager, JDBC driver và JMS ConnectionFactory **đều** hỗ trợ và được cấu hình đúng. JTA có tradeoff về latency, recovery log, coordinator, timeout, monitoring và vận hành. Nó không tự làm cho các HTTP call không hỗ trợ transaction trở nên atomic.

Nhiều ứng dụng microservices ưu tiên **transactional outbox + idempotent consumer** thay vì XA. Quyết định phải dựa trên yêu cầu nhất quán, failure scenarios và khả năng vận hành.

## 11. Retry, DLQ và poison message

### 11.1. Transient failure

Ví dụ dependency tạm thời không phản hồi:

~~~text
receive M -> xử lý thất bại -> rollback
              |
              v
      redelivery delay/backoff
              |
              v
receive M lại -> xử lý thành công -> commit
~~~

Không viết vòng lặp rollback liên tục với tốc độ cao làm nghẽn broker/DB. Số attempts, delay, exponential backoff, dead-letter queue và re-drive thường thuộc **broker policy**, không phải JDBC hay annotation mặc định.

### 11.2. Permanent failure / poison message

Một message thiếu schemaVersion bắt buộc hoặc có chữ ký sai có thể **không bao giờ** được xử lý thành công chỉ bằng retry. Cần quy định:

- Phân loại transient vs permanent.
- Giới hạn số lượt và độ trễ phát lại.
- Chuyển DLQ/quarantine sau khi hết attempts hoặc có chiến lược không retry.
- Log correlation/eventId, queue, delivery count, exception type và service instance.
- Re-drive có kiểm soát sau khi sửa dữ liệu, không tự nhân bản message ngoài dự kiến.

Một cách hợp lệ nếu cùng broker/Session là **receive poison message → send bản quarantine trong cùng transacted Session → commit**. Khi commit, message gốc được ACK và bản quarantine được gửi nguyên tử ở tầng JMS; nhưng phải kiểm soát payload nhạy cảm và chống ghi nhiều bản.

### 11.3. Không bỏ qua tất cả message `JMSRedelivered=true`

Provider có thể đã giao message lần đầu nhưng consumer bị kill **trước khi code chạy**. Message phát lại không nhất thiết là đã xử lý rồi. Hãy dedup bằng business eventId bền vững, không dùng redelivery flag làm điều kiện “đã xử lý”.

## 12. Timeout: nhận, giao dịch và xử lý

Có ít nhất bốn timeout/độ trễ cần tách:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Receive timeout | Thời gian thread chờ `receive()` | `receive(5_000L)` |
| Transaction timeout | Giới hạn transaction do manager/provider đặt | 30 giây, tùy cấu hình |
| Business request timeout | Thời gian gọi DB/API khi xử lý | 2 giây |
| Broker redelivery delay | Đợi trước khi phát lại sau rollback | 1 giây, tùy policy |

Với `receive()` timeout trả `null`, nếu chưa nhận message nào trong transaction thì commit/rollback thường không có tác động đáng kể. Nhưng nếu trước đó đã nhận M1 trong **cùng transaction**, quyết định này có thể ACK hoặc khôi phục M1.

**Tránh `receive()` vô hạn trong HTTP request thread** nếu không có cơ chế hủy hoặc giới hạn server thread pool. Polling liên tục thường thích hợp với service background; nhu cầu push/stream lâu dài phù hợp hơn với listener container bất đồng bộ.

## 13. Ví dụ thực hành Java 17 + Spring Boot 3.5 + Artemis

Demo có một message trong queue thử nghiệm và một consumer **synchronous**. Sau lần nhận đầu, code cố tình `rollback()`, rồi nhận lại và `commit()`. Nó cho thấy ranh giới giao dịch JMS bằng phương thức API thật, không dựa vào annotation listener bất đồng bộ.

### 13.1. Yêu cầu môi trường

Cần JDK 17+, Maven 3.9+, Docker và port `61616`, `8161` đang rảnh.

Khởi chạy broker ActiveMQ Artemis:

~~~bash
docker run --detach --rm --name jms-tx-receive-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Đợi broker startup, kiểm tra:

~~~bash
docker logs jms-tx-receive-lab
~~~

Broker lab thường cho phép auto-create queue. Trong môi trường tắt auto-create, hãy provision trước queue `lesson.jms.tx.receive` và quyền send/consume. Chỉ dùng credential demo trong môi trường cô lập.

### 13.2. Cấu trúc project

~~~text
jms-tx-receive-lab/
├── pom.xml
└── src/main/
    ├── java/example/TransactedReceiveApplication.java
    └── resources/application.properties
~~~

### 13.3. `pom.xml`

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
  <artifactId>jms-tx-receive-lab</artifactId>
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

### 13.4. `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 13.5. `src/main/java/example/TransactedReceiveApplication.java`

~~~java
package example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class TransactedReceiveApplication {

    private static final String QUEUE = "lesson.jms.tx.receive";

    public static void main(String[] args) {
        SpringApplication.run(TransactedReceiveApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate template,
                              ConnectionFactory connectionFactory) {
        return args -> {
            // Gửi trước bằng template; đây là send operation riêng.
            template.convertAndSend(QUEUE, "order-42");

            try (Connection connection =
                         connectionFactory.createConnection();
                 Session session = connection.createSession(
                         true, Session.SESSION_TRANSACTED)) {

                Queue queue = session.createQueue(QUEUE);

                try (MessageConsumer consumer =
                             session.createConsumer(queue)) {
                    connection.start();

                    // Transaction T1: nhận rồi cố tình rollback.
                    Message first = consumer.receive(5_000L);
                    if (!(first instanceof TextMessage text1)) {
                        throw new IllegalStateException(
                                "First TextMessage not received");
                    }

                    System.out.println("firstBody=" + text1.getText());
                    System.out.println("firstRedelivered="
                            + first.getJMSRedelivered());
                    System.out.println("firstDeliveryCount="
                            + first.getIntProperty("JMSXDeliveryCount"));

                    session.rollback();
                    System.out.println("rolledBack=true");

                    // Transaction T2: nhận lại rồi commit.
                    Message second = consumer.receive(15_000L);
                    if (!(second instanceof TextMessage text2)) {
                        throw new IllegalStateException(
                                "Redelivered TextMessage not received");
                    }

                    System.out.println("secondBody=" + text2.getText());
                    System.out.println("secondRedelivered="
                            + second.getJMSRedelivered());
                    System.out.println("secondDeliveryCount="
                            + second.getIntProperty("JMSXDeliveryCount"));

                    if (!"order-42".equals(text2.getText())) {
                        session.rollback();
                        throw new IllegalStateException("Unexpected body");
                    }

                    session.commit();
                    System.out.println("committed=true");
                }
            }
        };
    }
}
~~~

Đây là **file Java đầy đủ** có một public class trùng tên file, dùng Java 17 `instanceof` pattern matching và Spring Boot auto-configured `JmsTemplate`, `ConnectionFactory`.

Điểm cần quan sát:

1. `convertAndSend` được gọi trước để queue có đúng một `TextMessage`.
2. `Connection.createSession(true, Session.SESSION_TRANSACTED)` tạo local JMS transaction trong standalone Java.
3. `connection.start()` trước `consumer.receive(...)`.
4. Lần đầu nhận M nhưng **không** ack; `rollback()` làm broker có thể phát lại.
5. Lần thứ hai đọc `JMSRedelivered` và `JMSXDeliveryCount`.
6. Chỉ sau khi kiểm tra payload, `session.commit()` mới xác nhận M.
7. Không có shared mutable `Session`, và việc đóng dùng try-with-resources.
8. Ví dụ chưa có DB transaction, nên không suy nó bảo đảm exactly-once business processing.

### 13.6. Chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ở môi trường lab một broker rỗng, một consumer, redelivery mặc định không delay quá lớn, **những dòng do chương trình in ra** thường là:

~~~text
firstBody=order-42
firstRedelivered=false
firstDeliveryCount=1
rolledBack=true
secondBody=order-42
secondRedelivered=true
secondDeliveryCount=2
committed=true
~~~

Console còn có logs của Spring Boot/Artemis. Đây là **output kỳ vọng trong điều kiện cụ thể**, không phải bảo đảm cứng trên mọi provider/version: có thể broker thiết lập delay, DLQ, prefetch hoặc có consumer khác. `JMSXDeliveryCount` không phải bản ghi kiểm toán tuyệt đối trong mọi failure/failover.

### 13.7. Cách kiểm tra broker sau commit

Dùng Artemis management console ở `http://localhost:8161` hoặc CLI/metrics:

- Queue `lesson.jms.tx.receive` có được tạo đúng không?
- Consumer count có như dự kiến không?
- Message có từng ở trạng thái delivering/unacknowledged trước commit không?
- Sau commit thành công và không có traffic khác, queue còn backlog không?
- Có message bị chuyển DLQ vì policy hay không?

Lưu ý queue depth bằng 0 **trong lúc message đang được deliver** không tự chứng minh đã ACK; broker có thể hiển thị delivering count riêng.

Kết thúc:

~~~bash
docker stop jms-tx-receive-lab
~~~

Container chạy với `--rm`, không mount persistent volume. Khi dừng, dữ liệu broker demo không được giữ; không dùng cấu hình này cho production.

## 14. So sánh các cách nhận với transaction

| Phương pháp | Chủ thể commit/rollback | Code xử lý sau khi receive nằm trong JMS transaction? |
|---|---|---|
| Raw `MessageConsumer.receive()` trên transacted Session do app sở hữu | Ứng dụng gọi `session.commit()`/`rollback()` | **Có**, nếu chưa commit/close trước khi xử lý |
| `JMSContext.SESSION_TRANSACTED` trong Java SE | Ứng dụng gọi `context.commit()`/`rollback()` | **Có** trong phạm vi transaction của context |
| `JmsTemplate.receive()` với `sessionTransacted=true`, không có Spring transaction manager | `JmsTemplate` tự commit local receive | **Không**, phần code sau `receive()` chạy ngoài tx đó |
| `JmsTemplate.receive()` trong `@Transactional("jmsTransactionManager")` | Spring transaction manager | **Có với JMS resource**, nếu gọi qua proxy đúng cách |
| `JmsTemplate.receive()` trong `TransactionTemplate` JMS | Spring transaction manager | **Có với JMS resource** trong callback |
| `@JmsListener` dùng transacted listener container | Listener container | Có cho callback listener, nhưng **đây là nhận bất đồng bộ** |

Việc chọn giải pháp cần dựa vào nhu cầu polling đồng bộ, số lượng worker, transaction duration, quy tắc retry, database effects và tính rõ ràng của resource ownership.

## 15. Những lỗi thường gặp

### Lỗi 1 — Gọi `message.acknowledge()` trong transacted Session

~~~java
Message m = consumer.receive(5_000L);
if (m != null) {
    m.acknowledge(); // KHÔNG thay thế Session.commit().
}
~~~

Theo JMS, `acknowledge()` bị bỏ qua trên transacted Session. Nếu muốn ACK, gọi `session.commit()` sau xử lý thành công.

### Lỗi 2 — Ghi log “committed” trước khi commit

~~~java
Message m = consumer.receive(5_000L);
System.out.println("received=true");  // Đúng nếu m != null.
System.out.println("committed=true"); // Sai nếu chưa commit.
~~~

Đặc biệt khi commit có lỗi network, phải phân biệt `COMMITTED`, `ROLLED_BACK` và `UNKNOWN_OUTCOME`.

### Lỗi 3 — Đóng Session với kỳ vọng auto-commit

~~~java
try (Session session =
        connection.createSession(true, Session.SESSION_TRANSACTED)) {
    // receive...
    // Không có commit.
}
// Đóng transacted Session phải rollback transaction còn mở.
~~~

Đừng coi `try-with-resources` là công cụ tự động xác nhận message.

### Lỗi 4 — `JmsTemplate.setSessionTransacted(true)` rồi xử lý bên ngoài `receive()`

Spring template có thể commit ngay trong receive operation trước khi trả message. Dùng transaction manager bao trọn workflow hoặc raw Session nếu cần xử lý trước JMS ACK.

### Lỗi 5 — `catch` exception rồi return bình thường

Trong method `@Transactional`, nếu nuốt lỗi và return thành công, framework có thể commit message dù business processing đã thất bại. Ném exception kích hoạt rollback hoặc đánh dấu rollback-only theo kế hoạch rõ.

### Lỗi 6 — Tưởng `Session.recover()` là rollback transaction

`recover()` thuộc phiên không giao dịch. Trong transacted Session dùng `rollback()`.

### Lỗi 7 — Không gọi `Connection.start()` trước receive thuần JMS

Với classic API, khởi động connection là điều kiện để consumer nhận message. Spring template/container quản lý khác; không nhầm hai API.

### Lỗi 8 — Không kiểm tra `null` khi `receive(timeout)` hết hạn

~~~java
Message m = consumer.receive(500L);
String id = m.getJMSMessageID(); // Có thể NullPointerException.
~~~

Phải kiểm tra `m == null` trước khi đọc body/header/property.

### Lỗi 9 — Dùng một Session cho nhiều thread

Các thread có thể commit hoặc rollback transaction của nhau; JMS Session không phải tài nguyên chia sẻ song song. Mỗi worker có session riêng hoặc use manager/container phù hợp.

### Lỗi 10 — Gửi request rồi chờ reply trước commit cùng Session

Responder thường không thấy request chưa commit; có thể gây deadlock logic hoặc timeout. Tách transaction phát request và transaction chờ reply.

### Lỗi 11 — Nghĩ một local JMS transaction bao trùm JDBC

Không. Dùng idempotency/outbox, hoặc JTA/XA khi cơ sở hạ tầng và yêu cầu thực sự cần.

### Lỗi 12 — Rollback vô hạn poison message

Có thể gây loop và nghẽn broker. Hãy định nghĩa retry delay, tối đa attempts, DLQ, triage và re-drive.

### Lỗi 13 — `@Transactional` bị bypass do self-invocation

`this.pollAndProcess()` trong cùng bean có thể không qua proxy AOP và không mở transaction như mong muốn. Gọi qua bean được Spring quản lý hoặc dùng `TransactionTemplate`.

### Lỗi 14 — Dùng sai transaction manager hoặc ConnectionFactory

JMS manager có thể dùng factory khác với `JmsTemplate`, làm tài nguyên không được bind đúng. Kiểm tra cấu hình nhiều broker, wrapper, caching/pooling và tên manager.

## 16. Checklist triển khai production

- [ ] Chọn rõ synchronous polling hay `@JmsListener`; tránh vô tình cùng tranh nhận một queue.
- [ ] Với JMS raw, `Session` thực sự transacted và connection được `start()`.
- [ ] Nhận message có timeout hợp lý, có xử lý `null`.
- [ ] Commit **sau** khi toàn bộ thao tác JMS của transaction hoàn tất; rollback ở lỗi cần retry.
- [ ] Không dùng `acknowledge()` hoặc `recover()` thay cho commit/rollback trên transacted Session.
- [ ] Với `JmsTemplate`, có transaction boundary **bao trọn receive + business process**, không chỉ `setSessionTransacted(true)` nếu cần ACK sau xử lý.
- [ ] `JmsTransactionManager`/`JmsTemplate` dùng ConnectionFactory phù hợp.
- [ ] `@Transactional` hoạt động qua proxy và có rollback rule thích hợp.
- [ ] Không chia sẻ Session/JMSContext đồng thời giữa nhiều thread.
- [ ] DB/external side effect có idempotency/business event ID ổn định.
- [ ] Có cấu hình retry, delay, max attempts, DLQ và quy trình re-drive an toàn.
- [ ] Có metrics queue depth, delivering count, redelivery, DLQ, transaction failures và latency.
- [ ] Có log eventId, JMSMessageID, JMSRedelivered, JMSXDeliveryCount, outcome và consumer instance.
- [ ] Đã kiểm thử rollback, process crash, timeout, broker restart, commit unknown outcome và DB-before-JMS-commit.
- [ ] Không dùng credential/lifecycle của broker demo trong production.
- [ ] Không dùng message delivery count như bằng chứng chắc chắn business effect đã xảy ra.

## 17. Câu hỏi tự kiểm tra

**1. `receive()` trong transacted Session trả message thành công đã ACK chưa?** Chưa. Commit mới xác nhận message đã nhận trong transaction.

**2. Vì sao `message.acknowledge()` không có tác dụng?** JMS quy định phương thức này bị bỏ qua trong transacted Session, acknowledgement do commit/rollback quyết định.

**3. Nếu nhận M1 và M2 rồi rollback, message nào được khôi phục?** Cả những message đã nhận trong cùng transaction, gồm M1 và M2, theo policy của broker.

**4. Nếu nhận M rồi gửi X trên cùng Session và commit, điều gì xảy ra?** M được ACK và X được commit như một đơn vị JMS local atomic.

**5. Nếu `JmsTemplate.setSessionTransacted(true)` được bật nhưng không có manager, processing sau `receive()` có rollback được nhận không?** Không mặc định; template có thể đã commit local transaction bên trong receive operation.

**6. Cách dùng Spring để xử lý trước ACK?** Đặt `JmsTemplate.receive()` bên trong giao dịch do `JmsTransactionManager` quản lý bao trọn xử lý, hoặc dùng raw transacted Session.

**7. Khi nào `receive(timeout)` trả `null`?** Hết thời hạn chưa có message phù hợp; vẫn phải xem transaction có message đã nhận trước đó hay không.

**8. `Session.recover()` có thay `rollback()` trong transacted Session không?** Không. Dùng rollback.

**9. Nếu JMS rollback nhưng DB update đã commit, liệu DB có tự rollback không?** Không. Cần idempotency, outbox hoặc distributed transaction thích hợp.

**10. Vì sao `JMSRedelivered=true` không chứng minh code đã chạy trước đó?** Provider có thể đã giao message nhưng application chết trước callback/business code.

**11. Request-reply cùng local transaction trước commit có vấn đề gì?** Responder có thể không nhìn thấy request chưa commit nên caller chờ reply vô hạn.

**12. Khi JMS commit lỗi mạng, tại sao phải thận trọng retry?** Kết quả commit có thể không rõ; việc lặp lại side effect không kiểm soát tạo duplicate.

**13. Tại sao `@Transactional` không hoạt động khi self-invocation?** Lời gọi nội bộ có thể bỏ qua Spring proxy chứa transaction advice.

**14. Có nên tạo một Session singleton cho 20 polling threads?** Không. Session phải dùng tuần tự; nhiều workers cần các Session riêng.

**15. Vì sao poison message cần DLQ?** Retry cùng lỗi không thể sửa dễ gây rollback loop, lãng phí tài nguyên và ngăn message khác.

## 18. Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): transactions, message acknowledgement, recovery và commit outcome ambiguity.
- [Jakarta Messaging 3.1 API — Session](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session): `SESSION_TRANSACTED`, `commit()`, `rollback()`, `close()` và threading rules.
- [Jakarta Messaging 3.1 API — MessageConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer): `receive()`, `receive(timeout)`, `receiveNoWait()`.
- [Jakarta Messaging API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): acknowledgement, headers, redelivery.
- [Jakarta EE Tutorial — JMS concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): local JMS transactions và tránh deadlock send-then-receive.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous `JmsTemplate.receive` và receive timeout.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): transaction manager, binding resources và threading.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receive`, `receiveAndConvert`, `setSessionTransacted`.
- [Spring Framework 6.2 — JmsTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html): local JMS transaction manager.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): `spring-boot-starter-artemis` và `ConnectionFactory`.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker thử nghiệm.

**Kết luận:** Với **nhận đồng bộ trong transacted Session**, việc nhận thành công chỉ là bước đầu. **Commit** mới xác nhận các message đã nhận; **rollback** khôi phục chúng để broker có thể phát lại. Trong Spring, cần phân biệt `JmsTemplate` tự commit một local receive với một **`JmsTransactionManager` transaction bao trọn receive + processing**. Khi nghiệp vụ liên quan DB hoặc API ngoài JMS, phải bổ sung idempotency và cơ chế nhất quán phù hợp để chống duplicate.
