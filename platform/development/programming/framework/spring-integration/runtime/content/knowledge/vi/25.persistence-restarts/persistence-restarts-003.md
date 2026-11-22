# Khôi phục delayed message và pending group sau restart

Trong Spring Integration, một message đã được nhận **chưa chắc đã được xử lý xong**. Delayer có thể giữ message để phát vào một thời điểm trong tương lai; aggregator và resequencer có thể giữ nhiều message trong cùng một nhóm correlation cho tới khi đủ điều kiện release. Nếu ứng dụng dừng giữa chừng, câu hỏi quan trọng là: **message nào còn được lưu, lịch xử lý nào được tái tạo và bước nào có thể bị thực thi lại?**

Bài học thuộc chương **Persistence và restart** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ thực hành cách khôi phục delayed message và pending group qua vòng đời <code>IntegrationFlow</code>, channel, consumer endpoint, poller và executor; đồng thời kiểm tra transaction, retry, message store, error flow, correlation, hiệu năng và khả năng chẩn đoán trạng thái runtime.

> **Nguyên tắc:** Persistent <code>MessageStore</code> giúp giữ **dữ liệu message/group**, nhưng không tự bảo đảm mọi lịch chạy, transaction hay side effect được khôi phục nguyên trạng. Cần thiết kế riêng đường **reschedule** của Delayer và đường **release/expire** của Aggregator.

## 1. Hai loại trạng thái phải khôi phục

| Khía cạnh | Delayed message | Pending group của aggregator/resequencer |
|---|---|---|
| Dữ liệu đang chờ | Từng message có thời điểm cần phát trong tương lai | Các fragment cùng correlation key và metadata nhóm |
| Thành phần quản lý | <code>DelayHandler</code> + <code>TaskScheduler</code> | <code>AbstractCorrelatingMessageHandler</code> + <code>MessageGroupStore</code> |
| Điều kiện tiếp tục | Đến hạn delay, sau đó gửi sang output | Nhóm đủ điều kiện <code>ReleaseStrategy</code> hoặc được force complete |
| Có thể lưu bền vững? | Có, bằng <code>MessageGroupStore</code> persistent | Có, bằng <code>MessageGroupStore</code> persistent |
| Khi restart | Delayer đọc message đã lưu và **lập lịch lại** | Nhóm còn trong store; fragment mới có thể tiếp tục nhóm, nhưng lịch timeout cũ không nên được giả định còn |
| Chống tồn đọng lâu ngày | Retry/recovery và chính sách nghiệp vụ cho message quá hạn | <code>expireTimeout</code>, <code>expireDuration</code>, reaper và chính sách partial/discard |
| Rủi ro nổi bật | Phát thiếu/trùng trong khoảng mất điện giữa xóa store và downstream | Nhóm orphan, release trùng, correlation sai, message đến muộn |

~~~mermaid
flowchart TD
    A["Message đi vào flow"] --> B{"Cần lưu chờ vì lý do gì?"}
    B -->|Chờ thời gian| D["DelayHandler"]
    B -->|Chờ đủ fragment| G["Aggregator / Resequencer"]
    D --> DS[("Persistent delay group")]
    G --> GS[("Persistent correlation groups")]
    DS --> R["Restart: reschedule persisted messages"]
    GS --> P["Restart: nhận fragment mới / purge orphan"]
    R --> O["Release vào downstream"]
    P --> Q["Release / partial / discard"]
~~~

Trong sơ đồ, hai kho dữ liệu được vẽ riêng để thể hiện **quyền sở hữu và vòng đời khác nhau**. Chúng có thể dùng cùng hạ tầng database nhưng nên có bean/region và chính sách xử lý rõ ràng.

## 2. MessageStore bền vững giữ được gì?

Spring Integration có <code>MessageStore</code> cho dữ liệu message và <code>MessageGroupStore</code> cho message group. Một số triển khai như <code>SimpleMessageStore</code> chỉ nằm trong bộ nhớ; <code>JdbcMessageStore</code> dùng cơ sở dữ liệu, nên có thể giữ dữ liệu qua restart khi schema và cấu hình phù hợp.

Những điều cần kiểm tra trước khi kỳ vọng khôi phục:

1. **Đúng store:** Delayer/aggregator thực sự được cấu hình để sử dụng persistent store; dùng JDBC cho một thành phần khác trong ứng dụng không khiến chúng tự persistent.
2. **Đã commit:** Message hoặc group đã được ghi thành công và transaction lưu trữ đã commit trước lúc tiến trình dừng.
3. **Danh tính ổn định:** Region, message group ID, correlation strategy và định danh endpoint không đổi ngoài ý muốn qua deploy.
4. **Đọc được dữ liệu:** Serializer, payload class, header, version ứng dụng và schema database vẫn tương thích.
5. **Có consumer tiếp tục:** Endpoint, scheduler, error flow và downstream đang chạy sau restart.
6. **Cơ chế xử lý lại:** Phải có reschedule, incoming fragment mới hoặc thao tác forceComplete/purge; một bản ghi tồn tại trong DB chưa đồng nghĩa được thực thi.

**Phân biệt:** <code>JdbcMessageStore</code> dành cho message/group của delayer/aggregator khác với <code>JdbcChannelMessageStore</code> được sử dụng cho kênh queue lưu bền vững. Mỗi loại có API và semantics lấy/xóa riêng, không thể dùng một thao tác cleanup tùy ý cho cả hai.

## 3. Delayer thực sự khôi phục delayed message ra sao?

<code>DelayHandler</code> đưa delayed message vào một **message group** trong <code>MessageStore</code>. Thời điểm đến hạn được điều phối bằng <code>TaskScheduler</code>; sender thường không phải chờ cho hết thời gian delay. <code>groupId</code> dùng cho delayer phải ổn định để handler mới tìm lại được những message cũ sau restart.

Ở đường release thông thường, scheduled task lấy/xóa message khỏi store **ngay trước khi** gửi sang output channel. Khi dùng persistent store:

- Khi khởi động application context, Delayer đọc các message còn lưu và tạo lại lịch release.
- Với delay tính bằng số mili giây, thời điểm phát lại dựa trên **thời điểm message đến ban đầu**, chứ không bắt đầu đếm lại toàn bộ delay sau restart.
- Nếu delay được xác định bằng một giá trị <code>Date</code>, ngày giờ đó được dùng để lập lịch lại.
- Nếu đến lúc restart message đã quá hạn, nó được lên lịch phát sớm sau khi ứng dụng khởi động và scheduler sẵn sàng.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant D as DelayHandler
    participant DB as Persistent MessageStore
    participant T as TaskScheduler
    participant H as Downstream
    S->>D: message M, delay = 60s
    D->>DB: lưu M vào delay group
    D->>T: lên lịch release
    Note over D,T: Sau 20s: ứng dụng dừng
    Note over DB: M vẫn còn nếu đã commit
    Note over D,T: Ứng dụng khởi động lại sau 15s
    D->>DB: tìm các message đã lưu
    D->>T: lập lịch phần thời gian còn lại
    T->>DB: lấy / remove M khi đến hạn
    T->>H: gửi M tới downstream
~~~

**Không coi lịch trong bộ nhớ của <code>TaskScheduler</code> là dữ liệu bền vững.** Cơ chế khôi phục dựa vào message còn trong persistent store và Delayer tạo lịch mới, không phải việc scheduler giữ nguyên object <code>ScheduledFuture</code> qua tiến trình mới.

### Hai loại ID dễ nhầm

| ID | Chức năng | Quy tắc khi restart |
|---|---|---|
| <code>DelayHandler.messageGroupId</code> | Xác định **nhóm chứa message đang chờ** của một delayer | Giữ cố định qua deploy; không dựa vào bean name tự sinh |
| <code>MessageHeaders.ID</code> | ID của một message cụ thể | Không dùng làm khóa chống trùng nghiệp vụ; message mới/redelivery có thể có ID khác |
| <code>correlationId</code> | Nối các bước xử lý theo hợp đồng của flow | Giữ nếu cần theo dõi; không thay thế messageGroupId của Delayer |
| <code>businessId</code>/<code>idempotencyKey</code> | Định danh một hành động nghiệp vụ | Phải bền vững và được kiểm tra ở downstream khi có replay |

Một lỗi thường gặp là để framework tự sinh tên endpoint rồi dùng tên đó làm group ID. Sau deploy, tên mới có thể khác, khiến message cũ vẫn nằm trong DB nhưng Delayer mới không tìm được nhóm để lập lịch lại.

## 4. Ví dụ Java DSL: reminder được giữ qua restart

Ví dụ minh họa dùng Java 17+, Spring Integration 6.2+ và Spring JDBC. Database được cấp cho <code>JdbcMessageStore</code>, Spring đã có <code>PlatformTransactionManager</code> cùng <code>DataSource</code> và các bảng Spring Integration JDBC được tạo trước bằng script phù hợp dialect. Để lưu bằng Java serialization, payload và các header được giữ cần serializable hoặc ứng dụng phải cấu hình serializer/converter khác.

**Bước 1 — payload có định danh nghiệp vụ ổn định:**

~~~java
public record Reminder(
        String reminderId,
        String recipient,
        String content
) implements java.io.Serializable {}
~~~

**Bước 2 — khai báo persistent store, channel và flow:**

~~~java
@Configuration
@EnableIntegration
public class ReminderFlowConfig {

    @Bean(name = "reminderDelayStore")
    JdbcMessageStore reminderDelayStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("reminders.delay.v1");
        return store;
    }

    @Bean(name = "reminders.input")
    MessageChannel remindersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reminderFlow(
            @Qualifier("reminderDelayStore") MessageGroupStore delayStore,
            PlatformTransactionManager txManager,
            ReminderDeliveryService service) {
        return IntegrationFlow.from("reminders.input")
            .delay(d -> d
                .messageGroupId("reminders.delay.pending.v1")
                .messageStore(delayStore)
                .defaultDelay(60_000L)
                .transactionalRelease(txManager)
                .maxAttempts(5)
                .retryDelay(1_000L))
            .handle(service, "recordDelivery")
            .get();
    }
}
~~~

Các kiểu trong ví dụ: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.jdbc.store.JdbcMessageStore</code>, <code>org.springframework.integration.store.MessageGroupStore</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.transaction.PlatformTransactionManager</code>, <code>javax.sql.DataSource</code> và <code>org.springframework.beans.factory.annotation.Qualifier</code>.

<code>recordDelivery</code> được minh họa bằng service ghi DB trong cùng transaction khi Delayer release:

~~~java
@Service
public class ReminderDeliveryService {
    private final JdbcTemplate jdbc;

    public ReminderDeliveryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void recordDelivery(Reminder reminder) {
        jdbc.update(
            "INSERT INTO reminder_delivery(reminder_id, recipient) VALUES (?, ?)",
            reminder.reminderId(),
            reminder.recipient());
    }
}
~~~

Ví dụ cần một bảng <code>reminder_delivery</code> với <code>reminder_id</code> unique/primary key. Service chỉ ghi vào DB để diễn giải transaction; gửi email, SMS hoặc gọi HTTP thực tế **không tự rollback** cùng <code>JdbcMessageStore</code>. Nếu cần thông báo ra ngoài một cách đáng tin cậy, lưu bản ghi outbox trong transaction rồi để worker độc lập gửi với idempotency.

**Bước 3 — gửi reminder:**

~~~java
Message<Reminder> message = MessageBuilder
    .withPayload(new Reminder("REM-42", "user@example.org", "Đến giờ thực hiện"))
    .setHeader("correlationId", "request-42")
    .build();

remindersInput.send(message);
~~~

<code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Để thử restart, gửi message, xác nhận bản ghi delay tồn tại và transaction lưu trữ đã commit, sau đó dừng ứng dụng **trước 60 giây**. Khởi động lại với cùng database, region và <code>messageGroupId</code>: Delayer đọc message, lập lịch và chuyển sang <code>recordDelivery()</code> tại thời điểm còn lại hoặc sớm sau startup nếu đã quá hạn.

**Giới hạn của ví dụ:** <code>.transactionalRelease(txManager)</code> bảo vệ thao tác lấy message khỏi JDBC store và downstream **đồng bộ** tham gia cùng transaction manager. Nếu thêm <code>ExecutorChannel</code> ở giữa Delayer và <code>recordDelivery()</code>, transaction ở scheduled thread không tự bao trùm xử lý của worker thread khác.

## 5. Điều gì xảy ra nếu release của Delayer thất bại?

Delayer có chính sách release retry riêng:

| Cấu hình | Ý nghĩa |
|---|---|
| <code>maxAttempts</code> | Số lần tối đa thử release message khi downstream thất bại; mặc định 5 |
| <code>retryDelay</code> | Thời gian chờ thêm trước lần thử kế tiếp; mặc định 1 giây |
| <code>transactionalRelease</code> / delayed advice | Có thể bao quanh lấy/xóa message và gửi downstream trong một transaction |
| <code>delayedMessageErrorChannel</code> | Channel nhận <code>ErrorMessage</code> riêng cho lỗi khi release message |
| <code>reschedulePersistedMessages()</code> | Cho phép quét và đặt lại lịch cho message còn lưu, ví dụ sau khi scheduler từng dừng |

**Khi không có transaction ở release:** Delayer có thể đã xóa message khỏi store trước khi downstream ném exception. Framework có thể thử release lại trong process còn sống, nhưng một crash ở khoảng không còn bản ghi bền vững tạo ra rủi ro mất message.

**Khi release được bao trong transaction đúng resource:** Nếu downstream đồng bộ ném exception và transaction rollback, thao tác xóa khỏi persistent store có thể rollback, để message tiếp tục tồn tại. Khi quá số lần retry, nó vẫn có thể còn trong store nhưng **không tự tiếp tục được lên lịch nữa** cho tới khi restart hoặc gọi <code>reschedulePersistedMessages()</code>.

Một điểm dễ bỏ sót: nếu sử dụng <code>delayedMessageErrorChannel</code> và consumer của error channel xử lý lỗi rồi **trả về bình thường**, Delayer có thể coi lỗi đã được xử lý; với transactional release, transaction có thể commit và message bị xóa khỏi store. Nếu muốn tiếp tục retry, error consumer phải ném lại exception theo chính sách. Vì thế, error channel là nơi **quyết định recovery**, không mặc nhiên là một dead-letter queue bền vững.

~~~mermaid
flowchart TD
    S["Scheduled release task"] --> T{"Có transaction release?"}
    T -->|Có| R["Đọc / xóa message trong TX"]
    T -->|Không| N["Xóa trước khi gửi"]
    R --> D["Gửi xuống downstream"]
    N --> D
    D -->|Thành công| C["Commit / kết thúc release"]
    D -->|Lỗi| E["Retry / delayed error flow"]
    E -->|Rollback TX| P["Message có thể còn trong store"]
    E -->|Xử lý xong| X["Kết thúc theo recovery policy"]
    P --> M["Reschedule nếu hết lượt / sau restart"]
~~~

Ngoài ra, từ Spring Integration 5.3.7, nếu việc **lưu** delayed message diễn ra trong một transaction đang mở, lịch release sẽ được đặt trong callback <code>afterCommit()</code> để tránh scheduled task chạy trước khi bản ghi có thể đọc được. Điều này không biến các side effect downstream thành một distributed transaction.

## 6. Khôi phục pending MessageGroup của Aggregator

Aggregator gom các message theo **correlation key** và lưu vào <code>MessageGroupStore</code>. Ví dụ batch <code>B-17</code> cần ba fragment nhưng trước restart mới nhận được hai:

~~~text
MessageGroup(B-17):
  fragment A  ✓
  fragment B  ✓
  fragment C  (chưa đến)
  complete = false
~~~

Với persistent store, hai fragment và metadata có thể tiếp tục tồn tại sau restart. Khi fragment C đến ứng dụng mới, aggregator dùng cùng <code>CorrelationStrategy</code> và region/store để tìm lại group <code>B-17</code>, thêm C và áp dụng <code>ReleaseStrategy</code>. Nếu đủ ba phần, group được release bình thường.

**Tuy nhiên, không được suy luận rằng một <code>groupTimeout</code> đã được đặt trước lúc dừng sẽ tự động tiếp tục đúng thời điểm cũ.** Task scheduler trong bộ nhớ không phải kho bền vững. Nếu fragment C không bao giờ đến, nhóm có thể tiếp tục tồn đọng cho tới khi có cơ chế quét/force completion phù hợp.

### Phân biệt ba cơ chế

| Cơ chế | Khi nào chạy? | Phù hợp với |
|---|---|---|
| <code>ReleaseStrategy</code> | Khi handler nhận thêm message hoặc được kiểm tra trong quá trình force completion | Nhóm được bổ sung fragment sau restart |
| <code>groupTimeout</code> | Lịch timeout của group khi flow đang chạy; thường được đặt lại khi có message mới | Nhóm chưa đủ fragment trong thời gian hoạt động bình thường |
| <code>expireTimeout</code> + <code>expireDuration</code> | Tìm các group già trong store khi startup và định kỳ | Khôi phục xử lý các **orphaned group** sau restart |
| <code>MessageGroupStoreReaper</code> | Task riêng quét các group cũ theo chu kỳ | Chính sách expire/cleanup được quản trị tập trung |

Các đường force completion/expiry cuối cùng vẫn phải tuân theo chính sách **partial result hoặc discard**, thời điểm xóa group và cách xử lý fragment đến muộn. Persistent group không có nghĩa luôn phải chờ vô hạn.

## 7. Ví dụ Aggregator: tiếp tục pending group và xử lý orphan

Để minh họa một flow khác, dùng **store riêng** cho aggregator. Không dùng chung <code>MessageGroupStore</code> của Delayer ở ví dụ trước, và không chia sẻ một store duy nhất cho nhiều correlating endpoint nếu chúng có expiry callback độc lập.

~~~java
@Configuration
@EnableIntegration
public class BatchFlowConfig {

    @Bean(name = "batchGroupStore")
    JdbcMessageStore batchGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("batches.aggregate.v1");
        return store;
    }

    @Bean
    IntegrationFlow batchFlow(
            @Qualifier("batchGroupStore") MessageGroupStore groups) {
        return IntegrationFlow.from("batches.fragments")
            .aggregate(a -> a
                .messageStore(groups)
                .correlationStrategy(
                    m -> m.getHeaders().get("batchId"))
                .releaseStrategy(group -> group.size() >= 3)
                .groupTimeout(2 * 60_000L)
                .sendPartialResultOnExpiry(false)
                .expireGroupsUponTimeout(true)
                .expireTimeout(30 * 60_000L)
                .expireDuration(Duration.ofMinutes(5))
                .discardChannel("batches.discarded"))
            .channel("batches.completed")
            .get();
    }
}
~~~

<code>Duration</code> thuộc <code>java.time</code>. Ví dụ này cần thêm các channel/consumer phù hợp với <code>batches.fragments</code>, <code>batches.completed</code> và <code>batches.discarded</code>; nếu chưa có downstream subscriber, việc release/discard có thể thất bại. Những tên này phải giữ ổn định và thực sự được wiring trong ứng dụng.

**Diễn giải:**

1. Fragment được ghép vào group bằng header <code>batchId</code> ổn định qua restart.
2. Khi nhận đủ ba fragment, aggregator release bình thường.
3. Khi đang chạy, <code>groupTimeout</code> có thể force complete nhóm sau hai phút thiếu message mới.
4. Nếu sau restart còn group rất cũ, <code>expireTimeout</code> cùng <code>expireDuration</code> giúp tìm nhóm orphan khi startup và tiếp tục quét định kỳ.
5. Với <code>sendPartialResultOnExpiry(false)</code>, nhóm thiếu phần được discard theo cấu hình, **không** phát batch hoàn chỉnh giả. <code>expireGroupsUponTimeout(true)</code> cho phép xóa metadata sau timeout, nên fragment đến muộn có thể tạo nhóm mới.

**Đây là một lựa chọn nghiệp vụ để minh họa, không phải một retention mặc định nên áp dụng nguyên xi.** Nếu thiếu một fragment đồng nghĩa phải chờ nhân viên xác minh, hãy lưu nhóm lâu hơn, đưa dữ liệu vào quarantine có thể replay hoặc chọn <code>sendPartialResultOnExpiry(true)</code> kèm cờ “incomplete” rõ ràng. Nếu không muốn fragment đến muộn tạo lại nhóm, cần giữ dấu vết hoàn tất hoặc sử dụng idempotency store độc lập.

### Sự khác biệt giữa delay và pending group khi restart

~~~mermaid
sequenceDiagram
    participant APP as Application mới
    participant DEL as DelayHandler
    participant AGG as Aggregator
    participant DB as JdbcMessageStore
    participant IN as New fragment
    APP->>DEL: context đã khởi động
    DEL->>DB: đọc delay group cũ
    DEL->>DEL: reschedule từng delayed message
    APP->>AGG: endpoint ready
    IN->>AGG: fragment C, batch B-17
    AGG->>DB: đọc group B-17 (A, B)
    AGG->>DB: thêm C và đánh giá release
    AGG-->>APP: batch đủ điều kiện được xử lý
    Note over AGG,DB: Orphan purge/reaper xử lý các nhóm cũ không bao giờ có C
~~~

## 8. Orphan group, nhóm rỗng và message đến muộn

Sau restart, một số group có thể không còn khả năng hoàn tất: publisher đã dừng, phần cuối bị mất hoặc upstream chuyển sang batch ID mới. Chúng được gọi là *orphaned group* khi đã tồn đọng đủ lâu và không còn được hoạt động thường ngày giải phóng.

Trong Spring Integration, <code>expireTimeout</code> (giá trị dương, tính theo ms) xác định ngưỡng tuổi, còn <code>expireDuration</code> đặt chu kỳ kiểm tra. <code>purgeOrphanedGroups()</code> có thể được gọi khi startup, theo lịch và qua thao tác quản trị khi cần. Expiry sẽ đi qua logic <code>forceComplete</code>, chứ không phải một câu lệnh xóa thẳng mọi row cũ.

<code>MessageGroupStoreReaper</code> cũng có thể gọi <code>expireMessageGroups(timeout)</code> theo lịch. **Không nên bật đồng thời nhiều đường purge cho cùng một group store** nếu chưa kiểm chứng callback, locking, transaction và việc gửi kết quả. Chu kỳ scheduler còn làm thời gian expire thực tế có thể muộn hơn ngưỡng cấu hình.

Khi nhóm đã hoàn tất, aggregator có thể giữ một **empty group/tombstone** để ngăn late arrival tạo batch mới. Các lựa chọn liên quan:

- <code>expireGroupsUponCompletion(false)</code>: có thể giữ dấu vết hoàn tất sau release bình thường.
- <code>expireGroupsUponTimeout(true)</code>: có thể xóa group sau force completion do timeout.
- <code>minimumTimeoutForEmptyGroups</code>: giới hạn thời gian tối thiểu giữ metadata nhóm rỗng khi sử dụng cơ chế dọn phù hợp.
- Store/region riêng và <code>LockRegistry</code> nhất quán: tránh concurrent release hoặc callback của endpoint khác tác động nhầm group.

Nếu ứng dụng bắt buộc “batch B-17 chỉ xử lý một lần” ngay cả sau nhiều tháng, tombstone có TTL ngắn **không đủ**. Hãy lưu idempotency key theo nghiệp vụ với thời hạn phù hợp yêu cầu lưu trữ.

## 9. Ma trận crash: lưu, lấy, gửi và commit

Khôi phục qua restart phải dựa trên **thời điểm crash**, không chỉ dựa vào câu hỏi “DB còn row không?”.

| Thời điểm crash | Trạng thái khả dĩ | Việc cần kiểm chứng |
|---|---|---|
| Trước khi ghi message/group commit | Message có thể chưa tồn tại trong store | Source có redeliver không? ACK đã xảy ra chưa? |
| Delayer đã lưu và commit, chưa đến hạn | Message còn trong persistent group | Sau restart cùng group ID có được reschedule không? |
| Delayer vừa đến hạn, chưa xóa store | Message vẫn có thể còn | Lịch/lock có thể tạo attempt mới sau restart |
| Delayer xóa khỏi store, chưa gửi downstream, **không có transaction release** | Có thể mất message nếu tiến trình chết ngay khoảng này | Không được quảng bá delivery guarantee cao hơn cơ chế thực tế |
| Delayer xóa trong transaction, downstream ném lỗi đồng bộ | Rollback có thể giữ message trong store | Kiểm tra transaction manager, cùng resource và retry/reschedule |
| Downstream đã thực hiện side effect ngoài DB, rồi crash trước khi xác nhận | Không biết side effect đã xảy ra hay chưa | Idempotency phía nhận, outbox/inbox và đối soát |
| Aggregator lưu hai fragment, chưa đủ release | Pending group tồn tại | Fragment mới có thể ghép tiếp cùng correlation key |
| Aggregator release nhưng crash quanh commit/output | Có thể gặp output trùng hoặc trạng thái group chưa hoàn tất | Transaction, lock, idempotency và hậu quả side effect |
| Scheduler dừng nhưng process/store vẫn sống | Message vẫn có thể tồn tại mà không chạy đúng hạn | Trạng thái scheduler và thao tác reschedule có kiểm soát |

**Tính bền vững của store không tương đương exactly-once delivery.** Trong các khoảng crash quanh bước gửi ra ngoài, thường chỉ có thể thiết kế at-least-once kết hợp idempotency hoặc workflow bù trừ. Đừng khẳng định một message sẽ “không bao giờ mất/trùng” chỉ từ một dòng <code>messageStore(jdbcStore)</code>.

## 10. Transaction và ranh giới threading

Một delayed message được release trên **thread của scheduled task**. Một pending group có thể được cập nhật bởi consumer endpoint trên thread caller, worker executor hoặc poller. Transaction gắn với thread và phạm vi đã mở, nên:

| Topology | Điều cần lưu ý |
|---|---|
| Delayer → <code>DirectChannel</code> → JDBC service | Có thể bao quanh thao tác remove và downstream đồng bộ bằng release transaction cùng manager |
| Delayer → <code>ExecutorChannel</code> | Release transaction kết thúc ở ranh giới giao task; lỗi xử lý ở worker đến sau |
| Aggregator nhận qua <code>DirectChannel</code> | Transaction bên gửi có thể bao gồm cập nhật group nếu handler dùng cùng transaction manager |
| Aggregator nhận qua <code>QueueChannel</code> + poller | Poller transaction quyết định receive và cập nhật group có chung commit hay không |
| Persistent queue qua <code>JdbcChannelMessageStore</code> | ACK/remove semantics của queue phải kiểm tra riêng, không suy từ group store |
| Nhiều JVM cùng group store | Cần distributed lock/partition strategy để tránh nhiều node cùng sửa/release group |

Khi transaction đang mở lúc Delayer **lưu** message, Spring Integration đặt scheduled release ở callback sau commit (đối với các phiên bản đã hỗ trợ), tránh lịch chạy sớm hơn dữ liệu có thể đọc được. Khi Delayer **release**, transaction advice là một biên khác; cả hai không thể thay thế nhau.

Một consumer bất đồng bộ có thể tiếp tục xử lý sau khi sender đã timeout hoặc trả thành công. Khi restart, các request đang đợi reply qua gateway đồng bộ không thể tự “nối lại” thread/socket cũ. Hãy dùng correlation ID, trạng thái nghiệp vụ bền vững và API truy vấn kết quả riêng cho công việc kéo dài.

## 11. Cluster, leader và tránh khôi phục trùng

Một instance duy nhất với JDBC store là điểm bắt đầu đơn giản. Với nhiều pod cùng dùng persistent store, có thể có các tình huống:

- Hai Delayer cùng khởi động và nhìn thấy message trong **cùng delay group**, rồi đều lập lịch release.
- Hai aggregator cùng thấy group đủ điều kiện và cùng chạy force completion nếu không dùng lock chung.
- Một pod đổi <code>region</code>/<code>messageGroupId</code> trong rolling deployment, khiến message cũ chỉ có pod đời trước biết xử lý.
- Một node giữ distributed lock quá lâu, lease hết hạn và node khác bắt đầu thao tác trên cùng group.

Đối với Delayer, cần có **chiến lược sở hữu/partition rõ ràng** cho các message delay (ví dụ chỉ một active owner cho một group, hoặc chia partition/group ID theo pod/workload và có cơ chế chuyển owner). Không giả định <code>JdbcMessageStore</code> tự điều phối mọi lịch scheduler trong cluster.

Đối với aggregator/resequencer, Spring Integration hỗ trợ <code>LockRegistry</code> theo group. Nếu các replica dùng chung group store, dùng distributed registry phù hợp như JDBC/Redis và cùng namespace. Khóa không thay thế idempotency hoặc transaction; nếu lock lease hết hạn trong lúc xử lý, vẫn có khả năng stale writer.

Khi muốn thay đổi schema hoặc cấu hình giữa các đợt deploy, hãy xác định rõ:

1. Message đang chờ do phiên bản nào ghi?
2. Version mới có đọc được payload/header cũ không?
3. Ai sở hữu group ID/region cũ?
4. Có cần drain nhóm cũ trước khi đổi region hoặc chuyển dữ liệu sang region mới?
5. Nếu hai phiên bản cùng chạy, chúng có dùng cùng quy tắc correlation, khóa và idempotency không?

## 12. Chẩn đoán khi restart xong nhưng message không chạy

Trước khi sửa scheduler hoặc xóa dữ liệu, hãy tìm nơi message đã dừng:

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần kiểm tra |
|---|---|---|
| Delayed message có trong JDBC store nhưng không phát | <code>messageGroupId</code>/region đổi; Delayer chưa start; scheduler không chạy | Group ID thực, bean lifecycle, logs reschedule |
| Delayed message được phát ngay sau restart | Đã quá hạn so với thời gian nhận gốc | Header delay, arrival timestamp, thời gian downtime |
| Delayed message phát nhiều lần | Concurrent recovery, crash/rollback, downstream side effect không idempotent | Lock/owner, transaction logs, idempotency key |
| Delayed message biến mất dù downstream lỗi | Release không transactional hoặc error flow nuốt lỗi | Thời điểm remove/commit và chính sách <code>delayedMessageErrorChannel</code> |
| Group đủ fragment nhưng không release | Sai <code>correlationId</code>, release strategy, store region hoặc endpoint chưa start | Nội dung group, tên bean, metric consumer |
| Group thiếu fragment tồn tại mãi | Timeout task mất qua restart, không có orphan purge/reaper | Tuổi group, <code>expireTimeout</code>, lịch scheduler |
| Batch bị release partial sau startup | Orphan purge/timeout đã force complete | Cấu hình partial/discard và callback |
| Message cũ không deserialize được | Đổi class, serializer, schema | Stack trace, payload version, trạng thái migration |
| Có group trùng giữa hai pod | Thiếu distributed lock hoặc partition | Node ID, lock registry, group lifecycle |

Các bước kiểm tra theo thứ tự:

1. Xác minh **số bản ghi còn trong persistent store** và phân loại delay group, pending group, completed group.
2. Kiểm tra bean store có đúng datasource, region, schema và có quyền đọc dữ liệu cũ không.
3. Kiểm tra Delayer/aggregator endpoint đã start, <code>TaskScheduler</code> có worker và không bị rejected task.
4. Đối với Delayer, xác nhận <code>messageGroupId</code> ổn định và quá trình reschedule khi startup; chỉ gọi <code>reschedulePersistedMessages()</code> thủ công khi hiểu trạng thái scheduler hiện tại.
5. Đối với aggregator, kiểm tra correlation/release strategy; xác minh orphan purge hoặc reaper nếu không có fragment mới.
6. Đọc exception ở scheduled task, error channel, retry/recovery và transaction rollback; không suy luận thành công chỉ từ log “scheduled”.
7. Kiểm tra idempotency và trạng thái downstream để tránh gửi lại một side effect đã xảy ra.
8. Trên cluster, xác nhận chỉ đúng owner đang thực hiện recovery hoặc mọi instance dùng cơ chế khóa/phân vùng an toàn.

### Quan sát runtime

Các chỉ số hữu ích gồm: số delayed message còn lưu, **tuổi message quá hạn lâu nhất**, scheduled task queue, thời gian từ hạn đến lúc release, số lần release/retry, số lỗi publisher, số pending group, group age p95, orphan purge count, partial/discard count, lock wait, executor saturation và thời gian rollback.

<code>DelayHandler</code> có API quản trị như <code>getDelayedMessageCount()</code> và <code>reschedulePersistedMessages()</code>, có thể được xuất qua JMX/Control Bus khi đã cấu hình. Không để thao tác reschedule trở thành một lệnh vận hành được gọi lặp vô hạn: cần kiểm tra đang có task nào active và thực thi dưới quyền kiểm soát.

## 13. Bài thực hành kiểm thử restart

Kiểm thử thực sự cần **hai vòng đời application context** dùng **cùng một database bền vững**. Unit test chỉ mock <code>MessageStore</code> không chứng minh được dữ liệu sống qua restart hoặc việc lên lịch đúng.

| Tình huống | Bước kiểm tra | Kết quả mong đợi |
|---|---|---|
| Delay chưa tới hạn | Gửi M, commit, dừng context A, khởi động context B sau 10 giây | M được phát theo phần delay còn lại, không đếm lại từ đầu |
| Delay đã quá hạn trong downtime | Dừng A tới sau deadline, khởi động B | M được lên lịch phát sớm sau startup |
| Release transactional, downstream ném lỗi | Gây lỗi đồng bộ, kiểm tra JDBC store sau rollback | Bản ghi còn nếu transaction đúng và rollback xảy ra |
| Release hết <code>maxAttempts</code> | Tạo lỗi liên tục rồi khôi phục downstream | Hiểu rõ tình trạng message còn lưu nhưng chưa có lịch; reschedule có kiểm soát |
| Error flow nuốt lỗi | Cho <code>delayedMessageErrorChannel</code> xử lý rồi return | Quan sát commit/recovery như hợp đồng; không giả định retry |
| Aggregator pending group | A nhận 2/3 fragment, dừng; B nhận fragment cuối | Group cũ được tiếp tục và release một lần |
| Aggregator orphan group | A nhận fragment thiếu, B không nhận thêm | Purge/reaper áp dụng đúng timeout và partial/discard |
| Rolling deploy đổi class payload | Khởi động B đọc store do A ghi | Có migration/serializer tương thích hoặc quarantine rõ ràng |
| Hai replica recovery song song | Cả hai mở cùng backend/region | Không duplicate side effect; ownership/lock đúng |
| Message trùng do redelivery | Gửi lại cùng business event sau restart | Idempotency ngăn xử lý ngoài ý muốn |

Ví dụ phác thảo kiểm thử delayed message (không phải một test độc lập có thể chạy ngay):

~~~java
// contextA và contextB là hai Spring ApplicationContext khởi tạo
// cùng JDBC database nhưng dùng các scheduler/process lifecycle riêng.
contextA.start();
MessageChannel input = contextA.getBean(
    "reminders.input", MessageChannel.class);
input.send(MessageBuilder.withPayload(
    new Reminder("REM-99", "test@example.org", "payload")).build());

// Đảm bảo việc ghi MessageStore đã commit.
contextA.close();

// Khởi động lại contextB với CÙNG database, region và messageGroupId.
contextB.start();
// Chờ theo điều kiện có timeout; assert bản ghi reminder_delivery
// xuất hiện đúng một lần và thời điểm phát theo SLA.
contextB.close();
~~~

Khi viết integration test thật, cần một cách tạo context mới thay vì gọi <code>start()</code> trên context đã đóng, database/Testcontainers giữ nguyên trong suốt hai vòng, và một cơ chế chờ có timeout thay cho <code>Thread.sleep()</code> cố định. Dùng unique key để phát hiện duplicate và ghi lại transaction/metric trong từng vòng chạy.

## 14. Checklist production cho persistence và restart

- [ ] Delayer và aggregator đều dùng persistent <code>MessageGroupStore</code> phù hợp; schema và serializer được quản lý qua deploy.
- [ ] Delayer có <code>messageGroupId</code> ổn định, đồng thời biết khi nào tự reschedule và khi nào cần khôi phục thủ công.
- [ ] Lịch delay được hiểu theo thời điểm gốc, có hành vi rõ với message quá hạn trong downtime.
- [ ] Delayer release có transaction/advice phù hợp với store và downstream đồng bộ; retry/recovery không nuốt lỗi ngoài chủ đích.
- [ ] Pending group có cùng correlation strategy/region sau restart; biết khi nào sẽ chờ fragment mới và khi nào được force complete.
- [ ] Có chính sách orphan purge hoặc <code>MessageGroupStoreReaper</code> với tuổi, chu kỳ và partial/discard phù hợp nghiệp vụ.
- [ ] Late arrival, group tombstone và idempotency key được định nghĩa cho mọi đường replay.
- [ ] Các ranh giới <code>ExecutorChannel</code>, poller, broker ACK và transaction manager được kiểm tra thực tế.
- [ ] Mỗi instance/pod có owner/partition/lock rõ khi dùng shared store; đã thử crash và restart đồng thời.
- [ ] Có metric và cảnh báo cho backlog, quá hạn, orphan, retry, release failure và lỗi deserialize.
- [ ] Bộ kiểm thử xác nhận cùng một persistent database qua **ít nhất hai vòng đời ứng dụng**.

**Kết luận:** Khôi phục runtime của Spring Integration gồm hai việc khác nhau: **khôi phục delayed message bằng cách đọc store và lập lịch release lại**, và **khôi phục pending group bằng cách tiếp tục correlation hoặc xử lý orphan theo chính sách expiry**. Persistent store cung cấp dữ liệu đầu vào cho cả hai, nhưng chỉ một thiết kế có transaction, retry/recovery, idempotency, lifecycle và cơ chế giám sát rõ ràng mới giúp flow tiếp tục an toàn sau restart.

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html)
- [Spring Integration Reference — Aggregator và group timeout](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Javadoc — DelayerEndpointSpec (6.4)](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/DelayerEndpointSpec.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec (6.5)](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
