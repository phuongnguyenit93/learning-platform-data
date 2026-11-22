# StoreTimeout và dọn message cũ

Khi Spring Integration lưu message vào bộ nhớ hoặc kho bền vững, một luồng có thể tiếp tục hoạt động sau khi ứng dụng restart. Tuy nhiên, dữ liệu không tự biến mất chỉ vì một message đã nằm trong store quá lâu. Aggregator có thể chờ mãi phần cuối của một nhóm; queue có thể tích tụ message không còn consumer; nhóm đã hoàn tất có thể giữ lại metadata nhằm từ chối các message đến muộn. Nếu không có chính sách hết hạn, kho sẽ tăng dung lượng, thời gian quét tăng và trạng thái runtime ngày càng khó điều tra.

Chủ đề **“StoreTimeout và dọn message cũ”** nằm trong chương **Message store** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ đặt chính sách lưu giữ phù hợp với message flow chạy qua channel, endpoint, consumer, poller và executor; đồng thời tìm hiểu transaction, retry, correlation, lỗi và hiệu năng khi dọn dữ liệu.

> **Lưu ý tên gọi:** Trong Spring Integration không có một thuộc tính <code>StoreTimeout</code> phổ quát để tự đặt TTL cho mọi <code>MessageStore</code>. Ở đây, “StoreTimeout” là tên gọi cho *yêu cầu giới hạn tuổi lưu trữ*. API cụ thể phụ thuộc thành phần sử dụng store: <code>groupTimeout</code> của aggregator, <code>MessageGroupStoreReaper</code>, <code>expireTimeout</code>/<code>expireDuration</code> hoặc cơ chế retention riêng của queue và backend.

## 1. Những gì có thể nằm trong message store?

Spring Integration dùng <code>org.springframework.integration.store.MessageStore</code> và các giao diện chuyên biệt cho thành phần cần buffer message. Hai nhóm trường hợp rất dễ bị đánh đồng:

| Thành phần | Dữ liệu lưu | Khi nào thường được lấy/xóa? | Rủi ro khi dọn sai |
|---|---|---|---|
| Aggregator / resequencer | Các <code>MessageGroup</code> theo correlation key, có thể gồm message chưa đủ để release | Khi release đủ điều kiện, timeout hoặc thao tác expire | Mất dữ liệu đang chờ ghép; release thiếu phần; message đến muộn tạo nhóm khác |
| <code>QueueChannel</code> có <code>ChannelMessageStore</code> | Message đang xếp hàng chờ poller/consumer nhận | Khi consumer nhận thành công theo semantics của store | Xóa công việc chưa xử lý, phá cam kết giao hàng |
| Delayer | Message chờ đến lịch phát | Khi đến thời điểm delay và handler lấy ra gửi | Message trễ bị mất trước khi gửi |
| Claim Check | Payload được lưu và thay bằng token tham chiếu | Khi bước sau lấy payload hoặc chính sách thu hồi yêu cầu | Token tồn tại nhưng không còn dữ liệu gốc |
| Bộ nhớ lưu trạng thái correlation | Metadata nhóm đã hoàn tất, kể cả nhóm rỗng | Khi cấu hình hết hạn metadata, reaper hoặc purge phù hợp | Mất dấu vết nhóm đã xong, message đến muộn bị ghép lại |

<code>SimpleMessageStore</code> lưu trong bộ nhớ, hữu ích khi thử nghiệm nhưng không duy trì dữ liệu sau restart. Các triển khai như <code>JdbcMessageStore</code>, Redis/MongoDB store hoặc <code>JdbcChannelMessageStore</code> phục vụ nhu cầu lưu bền vững theo tính năng hỗ trợ của từng loại. **Có persistent store không đồng nghĩa có TTL tự động.** Muốn xóa message cũ phải định nghĩa rõ điều kiện *được phép xóa* và thành phần sở hữu quyết định đó.

~~~mermaid
flowchart LR
    P["Producer"] --> CH["Channel / Endpoint"]
    CH --> S{"Loại lưu trữ"}
    S -->|Correlation| G["MessageGroupStore"]
    S -->|Queue| Q["ChannelMessageStore"]
    G --> A["Aggregator / Resequencer"]
    Q --> C["Poller / Consumer"]
    A --> D["Release / expire group"]
    C --> E["Nhận và xử lý message"]
    F["Retention policy"] -.-> D
    F -. "Không xóa queue tùy tiện" .-> Q
~~~

## 2. Phân biệt các loại timeout

Tên có chữ “timeout” không nói lên dữ liệu nào sẽ bị xóa.

| Cấu hình / khái niệm | Phạm vi | Hành vi chính |
|---|---|---|
| <code>groupTimeout</code> hoặc <code>groupTimeoutExpression</code> | Một nhóm trong aggregator/resequencer | Lên lịch *force completion* khi nhóm chưa release theo chiến lược thông thường |
| <code>sendPartialResultOnExpiry</code> | Group hết hạn/chạy <code>forceComplete</code> | Quyết định gửi kết quả thiếu phần hay bỏ các message chưa đủ điều kiện |
| <code>expireGroupsUponTimeout</code> | Group hoàn tất vì timeout | Quyết định xóa hẳn group hay giữ metadata đã hoàn tất |
| <code>minimumTimeoutForEmptyGroups</code> | Metadata nhóm rỗng đã hoàn tất | Cho phép dọn nhóm rỗng sau khoảng giữ tối thiểu, tùy cơ chế lên lịch |
| <code>MessageGroupStoreReaper.timeout</code> | Các group thuộc <code>MessageGroupStore</code> | Khi chạy <code>run()</code>, yêu cầu store expire các group cũ vượt ngưỡng tuổi |
| <code>expireTimeout</code> + <code>expireDuration</code> | Nhóm cũ/orphan trong store của correlating handler | Quét khi khởi động và định kỳ để xử lý nhóm tồn đọng |
| Timeout gửi/nhận của channel hoặc poller | Lời gọi gửi/nhận message | Giới hạn thời gian chờ, **không** tự xóa message vì quá tuổi |
| Retention/TTL của database, Redis hay broker | Bản ghi/entry thuộc backend cụ thể | Phụ thuộc cơ chế backend; không mặc nhiên tương thích với semantics của Spring Integration |

Thí dụ: đặt <code>receiveTimeout=1000</code> cho poller nghĩa là đợi tối đa khoảng một giây để nhận message ở thành phần có hỗ trợ; nó **không phải** “xóa message sau một giây”. Tương tự, <code>sendTimeout</code> giới hạn thời gian gửi khi channel có thể block, không thay cho chính sách dọn dữ liệu cũ.

## 3. Group timeout: đợi đủ message rồi xử lý nhóm thiếu

Giả sử hệ thống nhận ba mảnh dữ liệu <code>A</code>, <code>B</code>, <code>C</code> của cùng một batch. Aggregator chờ cả ba; chỉ có <code>A</code> và <code>B</code> đến. Nếu không có timeout, nhóm có thể nằm trong store vô thời hạn.

~~~mermaid
sequenceDiagram
    participant U as Upstream
    participant A as Aggregator
    participant S as MessageGroupStore
    participant T as TaskScheduler
    participant D as Downstream / Discard
    U->>A: batch-42, fragment A
    A->>S: thêm A vào group-42
    U->>A: batch-42, fragment B
    A->>S: thêm B vào group-42
    A->>T: đặt lại hạn groupTimeout
    Note over U,D: Không có fragment C
    T->>A: forceComplete(group-42)
    A->>S: hoàn tất hoặc expire group
    A-->>D: partial result hoặc discard theo cấu hình
~~~

<code>groupTimeout</code> thường được tính từ lần message cuối cùng đến nhóm (lịch timeout có thể được đặt lại khi nhóm nhận thêm message). Nó **khác** yêu cầu “nhóm phải kết thúc sau đúng 60 giây kể từ lúc tạo”: trường hợp đó cần biểu thức dựa vào timestamp tạo nhóm, hoặc deadline nghiệp vụ được đưa vào tính toán. Các task timeout chạy theo scheduler nên thời điểm thực tế có thể trễ vì pool bận hoặc ứng dụng đang dừng.

### Hết hạn thì gửi thiếu phần hay loại bỏ?

| Chính sách | Khi thiếu một phần | Khi fragment đến muộn |
|---|---|---|
| <code>sendPartialResultOnExpiry=true</code> | Có thể phát một kết quả chỉ gồm các fragment hiện có | Phụ thuộc nhóm có bị xóa hoàn toàn và cơ chế chặn late arrival |
| <code>sendPartialResultOnExpiry=false</code> | Các fragment chưa đủ điều kiện có thể bị discard khi force complete | Không có kết quả partial; vẫn cần quyết định giữ hay xóa metadata |
| <code>expireGroupsUponTimeout=true</code> | Xóa hẳn group sau timeout theo logic hoàn tất | Message đến sau có thể tạo **nhóm mới cùng correlation key** |
| <code>expireGroupsUponTimeout=false</code> | Có thể giữ metadata group đã hoàn tất | Late arrival có thể bị từ chối nhờ dấu vết hoàn tất, cho tới khi metadata được dọn |

Đây là **chính sách dữ liệu nghiệp vụ**: một batch không đủ ba fragment có được coi là hợp lệ để tạo kết quả hay phải vào quarantine? Một hệ thống tài chính có thể cần từ chối batch thiếu phần; hệ thống phân tích có thể chấp nhận kết quả partial kèm cờ “incomplete”.

## 4. Ví dụ Java DSL: timeout và giữ dấu vết nhóm đã hoàn tất

Ví dụ Spring Integration 6.x, Java 17+. Để tập trung vào vòng đời group, phần này dùng <code>SimpleMessageStore</code>; ở production có thể thay bằng <code>JdbcMessageStore</code> đã cấu hình schema/serialization phù hợp.

~~~java
@Configuration
@EnableIntegration
public class FragmentFlowConfig {

    @Bean
    MessageGroupStore fragmentGroups() {
        return new SimpleMessageStore();
    }

    @Bean
    IntegrationFlow fragmentAggregator(
            @Qualifier("fragmentGroups") MessageGroupStore store) {
        return IntegrationFlow.from("fragments.input")
            .aggregate(a -> a
                .messageStore(store)
                .correlationStrategy(m -> m.getHeaders().get("batchId"))
                .releaseStrategy(group -> group.size() >= 3)
                .groupTimeout(60_000L)
                .sendPartialResultOnExpiry(false)
                .expireGroupsUponTimeout(false)
                .minimumTimeoutForEmptyGroups(10 * 60_000L))
            .channel("fragments.completed")
            .get();
    }
}
~~~

Các kiểu chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.store.MessageGroupStore</code>, <code>org.springframework.integration.store.SimpleMessageStore</code>, <code>org.springframework.integration.config.EnableIntegration</code>. Ví dụ cần thêm consumer/subscriber cho <code>fragments.completed</code> và cần tạo message có header <code>batchId</code> hợp lệ. Với phần tử tạo kết quả, strategy mặc định của aggregator sẽ tổng hợp payload, vì vậy downstream phải biết kiểu payload thực tế.

Trong cấu hình này:

1. Group được định danh bằng header <code>batchId</code>; các message cùng key góp chung nhóm.
2. Group đủ ba fragment được release bình thường.
3. Nhóm bị thiếu fragment trong khoảng một phút sau lần nhận cuối được force complete, **không phát kết quả partial**.
4. <code>expireGroupsUponTimeout(false)</code> yêu cầu giữ metadata hoàn tất để ngăn late arrival tạo lại nhóm ngay sau timeout.
5. <code>minimumTimeoutForEmptyGroups</code> cung cấp cơ chế dọn metadata rỗng sau khoảng tối thiểu; khi dấu vết được xóa, late arrival rất muộn có thể được coi là nhóm mới. Nếu nghiệp vụ bắt buộc từ chối trùng vĩnh viễn, cần bản ghi idempotency riêng có thời hạn phù hợp.

Nếu muốn **hủy hoàn toàn group ngay khi timeout**, đổi <code>expireGroupsUponTimeout(true)</code>. Khi đó hãy cân nhắc hậu quả của message đến muộn và phân biệt timeout vì hết hạn với retry/redelivery.

> **Không coi cấu hình trên là retention cho mọi queue trong ứng dụng.** Nó chỉ áp dụng cho group do aggregator này quản lý; <code>QueueChannel</code> hoặc claim-check store khác không chịu ảnh hưởng.

## 5. Dùng MessageGroupStoreReaper để quét nhóm tồn đọng

<code>org.springframework.integration.store.MessageGroupStoreReaper</code> là thành phần chạy được theo lịch. Nó dùng <code>MessageGroupStore.expireMessageGroups(timeout)</code> để kích hoạt callback hết hạn cho các group đủ cũ. Reaper **không tự chạy vào đúng thời điểm timeout** nếu không có ai lên lịch gọi <code>run()</code>.

Ví dụ Java:

~~~java
@Configuration
@EnableScheduling
public class GroupCleanupConfig {

    @Bean
    MessageGroupStoreReaper fragmentReaper(
            @Qualifier("fragmentGroups") MessageGroupStore groupStore) {
        MessageGroupStoreReaper reaper =
            new MessageGroupStoreReaper(groupStore);
        reaper.setTimeout(30 * 60_000L); // 30 phút, đơn vị ms
        reaper.setExpireOnDestroy(false);
        return reaper;
    }
}

@Component
class GroupCleanupJob {
    private final MessageGroupStoreReaper reaper;

    GroupCleanupJob(
            @Qualifier("fragmentReaper") MessageGroupStoreReaper reaper) {
        this.reaper = reaper;
    }

    @Scheduled(fixedDelay = 60_000L)
    public void reap() {
        reaper.run();
    }
}
~~~

Ở đây <code>@EnableScheduling</code>/<code>@Scheduled</code> thuộc Spring Context Scheduling, <code>MessageGroupStoreReaper</code> thuộc Spring Integration. Ví dụ minh họa *một chiến lược thay thế* khi vận hành store của correlating endpoint; không nên vô tình kích hoạt cả group timeout, reaper và tác vụ purge khác trên cùng nhóm nếu chưa đánh giá callback và lịch chạy trùng nhau.

Reaper với ngưỡng 30 phút chạy mỗi phút: một nhóm vừa vượt 30 phút có thể chưa bị xử lý cho tới lượt quét kế tiếp. Nếu scheduler bận, chậm còn lớn hơn; thời gian hết hạn là **gần đúng**. Độ trễ dọn dự kiến có thể được ước lượng:

~~~text
Thời điểm dọn ≈ thời điểm nhóm đủ cũ
               + độ trễ chờ tới lần quét kế tiếp
               + độ trễ scheduler/lock/transaction
~~~

Theo hướng dẫn Spring Integration, nên đặt chu kỳ reaper không dài hơn timeout nếu muốn tránh giữ nhóm cũ quá lâu.

### Reaper không đơn thuần là DELETE

Mỗi correlating handler thường đăng ký callback trên <code>MessageGroupStore</code> để quyết định chuyện gì xảy ra khi group bị expire. Callback có thể:

- force complete group;
- phát kết quả partial khi được phép;
- gửi message tới discard flow;
- xóa group hoặc giữ lại dấu vết hoàn tất theo cấu hình;
- ném exception nếu bước downstream xử lý timeout thất bại.

Do đó, reaper không nên được coi như một câu lệnh SQL “xóa tất cả dữ liệu cũ”. Nó có thể **tạo message mới và side effect trong downstream**. Error handling, transaction, idempotency và thread scheduler của reaper là các phần cần kiểm thử.

## 6. Dọn nhóm orphan sau restart: expireTimeout và expireDuration

Một tình huống đặc biệt của **persistent MessageGroupStore** là nhóm đang chờ khi ứng dụng dừng. Khi chạy lại, những lịch timeout từng được tạo trong bộ nhớ có thể không còn. Nếu không có fragment mới đến, nhóm cũ có nguy cơ tồn tại mãi.

Spring Integration có cơ chế **purge orphaned groups** tại correlating handler, dùng <code>expireTimeout</code> cho ngưỡng tuổi và <code>expireDuration</code> cho chu kỳ quét. Khi cấu hình phù hợp, handler có thể dọn lúc khởi động và định kỳ; cũng có API <code>purgeOrphanedGroups()</code> phục vụ vận hành theo chủ đích.

Ví dụ phần cấu hình một aggregator sử dụng store bền vững:

~~~java
IntegrationFlow orphanAwareFlow(MessageGroupStore dedicatedStore) {
    return IntegrationFlow.from("batches.input")
        .aggregate(a -> a
            .messageStore(dedicatedStore)
            .correlationStrategy(m -> m.getHeaders().get("batchId"))
            .releaseStrategy(group -> group.size() >= 3)
            .expireTimeout(30 * 60_000L)
            .expireDuration(Duration.ofMinutes(5))
            .sendPartialResultOnExpiry(false))
        .channel("batches.completed")
        .get();
}
~~~

Đây là **mảnh cấu hình minh họa**, không phải một <code>@Bean</code> hoàn chỉnh. Nó cần các bean channel, consumer và một <code>MessageGroupStore</code> được cấp riêng cho aggregator. API thuộc Java DSL của Spring Integration; <code>Duration</code> là <code>java.time.Duration</code>. Các ngưỡng cần chọn dựa trên SLA fragment đến trễ và lịch restart thực tế.

Điểm khác với <code>groupTimeout</code>:

- <code>groupTimeout</code> lập lịch theo nhóm trong lúc flow đang nhận và xử lý message.
- <code>expireTimeout</code> xử lý các group **đã tồn tại đủ cũ trong store**, hữu ích khi ứng dụng restart và không còn sự kiện mới kích hoạt nhóm.
- <code>expireDuration</code> điều khiển chu kỳ purge; nó không có nghĩa xóa mỗi message sau đúng thời lượng đó.
- <code>MessageGroupStoreReaper</code> là cơ chế quét độc lập có thể dùng cho group store phù hợp, nhưng cần hiểu callback và chủ sở hữu của store.

Không sử dụng **một instance <code>MessageGroupStore</code> cho nhiều aggregator/resequencer** rồi để mỗi thành phần tự expire group của nhau. Framework có cơ chế phát hiện một số trường hợp callback trùng, nhưng thiết kế an toàn vẫn là dành store/partition phù hợp cho từng correlating endpoint. Với JDBC có thể dùng <code>region</code>; với MongoDB có thể phân tách collection tùy cách lưu trữ.

## 7. Empty group và late-arriving message: vì sao cần giữ “tombstone”?

Sau khi một group được release thành công, có những flow **giữ lại metadata nhóm rỗng** để nhớ rằng correlation key đó đã hoàn tất. Metadata này thường được gọi mang tính mô tả là *tombstone* (dấu vết hoàn tất).

~~~text
groupId=batch-42
messages=[]
complete=true
~~~

Nếu đến một message trễ cũng mang <code>batchId=batch-42</code>, dấu vết hoàn tất giúp aggregator không vô tình tạo lần xử lý thứ hai. Nhưng nếu giữ tất cả tombstone mãi mãi, store vẫn phình to dù không còn payload.

Ba quyết định phải liên kết:

1. **Sau release bình thường:** có xóa hẳn group qua <code>expireGroupsUponCompletion</code> hay giữ metadata?
2. **Sau timeout:** có xóa group qua <code>expireGroupsUponTimeout</code> hay giữ metadata?
3. **Khi metadata rỗng già đi:** dùng <code>minimumTimeoutForEmptyGroups</code> và cơ chế cleanup phù hợp để giới hạn thời gian lưu?

Ví dụ nghiệp vụ cho phép message trễ trong 24 giờ: chỉ dọn tombstone sau khi đã có chính sách chống trùng độc lập hoặc sau khoảng retention lớn hơn 24 giờ cộng biên an toàn. Nếu xóa tombstone sớm, việc message đến muộn tạo nhóm mới là **hành vi có thể xảy ra theo thiết kế**, không phải bug ngẫu nhiên.

## 8. Còn message cũ trong QueueChannel thì sao?

<code>QueueChannel</code> dùng <code>ChannelMessageStore</code> khác với tập group mà aggregator giữ. Một message trong queue có thể “cũ” vì consumer ngừng hoạt động, vì xử lý chậm hoặc vì dữ liệu không còn hợp lệ. Spring Integration **không cung cấp một nút TTL thống nhất** để áp đặt chính sách xóa an toàn cho mọi queue store.

| Tình huống | Điều cần làm |
|---|---|
| Queue có nhiều message nhưng consumer vẫn xử lý chậm | Chẩn đoán poller cadence, pool/executor, downstream latency, backpressure trước khi xóa |
| Message hết giá trị nghiệp vụ (ví dụ giá báo đã hết hạn) | Định nghĩa expiry header/deadline tại lúc nhận hoặc trước khi xử lý, đưa message quá hạn sang quarantine/discard theo hợp đồng |
| Hàng đợi lưu bằng JDBC/Redis | Xem API, transaction và cơ chế retention được triển khai store hỗ trợ; không giả định <code>MessageGroupStoreReaper</code> có thể xóa queue messages như aggregator |
| Message bị poison và lặp lại | Phân loại lỗi, retry có giới hạn, dead-letter/quarantine; không dùng xóa hàng loạt để che lỗi |
| Message đã ở queue khi deploy version mới | Đảm bảo compatibility serialization/schema và chính sách migration/replay trước khi thao tác cleanup |

**Không trực tiếp chạy DELETE theo timestamp trên bảng message store khi consumer còn chạy** trừ khi đã nghiên cứu schema, khóa, transaction và hành vi concurrent của đúng store implementation. Xóa một hàng database có thể phá index/metadata, khiến consumer đang giữ tham chiếu tới message hoặc gây mất công việc trước ACK.

Nếu muốn hỗ trợ TTL nghiệp vụ, có thể tách *retention* khỏi *delivery*: consumer đọc message, kiểm tra deadline rồi định tuyến sang processing hoặc expired flow. Với queue bền vững, việc nhận/ACK và ghi expired record cần phối hợp transaction/outbox để không đánh mất dữ liệu khi crash.

## 9. Transaction, retry và lỗi trong tác vụ cleanup

Hết hạn nhóm có thể kích hoạt <code>forceComplete</code> và gửi output. Nếu downstream ném exception trong scheduler task, cần biết:

- **Transaction scope:** tác vụ cleanup không tự tham gia transaction của một producer đã kết thúc. Nếu phải bảo đảm thay đổi trạng thái group và phát sự kiện liên quan nhất quán, dùng transaction advice/transaction synchronization phù hợp với store và downstream.
- **Retry:** retry một lần force completion có thể phát output trùng nếu lần trước đã có side effect ngoài transaction. Dùng idempotency key theo correlation/group và hợp đồng “đã release”.
- **Error channel:** scheduled task nên có error handler thích hợp. Spring Integration khuyến nghị scheduler dùng <code>MessagePublishingErrorHandler</code> khi việc expire có thể tạo message downstream, để exception được quan sát qua error flow.
- **Lock và concurrency:** khi nhiều instance cùng quét persistent store, cần cơ chế khóa theo group, thống nhất owner/partition, hoặc distributed lock theo khả năng backend. Đừng để hai scheduler cùng hoàn tất một group.
- **Lifecycle:** stop endpoint hay shutdown ứng dụng không tự đồng nghĩa đã dọn sạch tất cả group. Cần chính sách shutdown/startup rõ ràng, đặc biệt khi muốn tránh mất dữ liệu đang chờ.

~~~mermaid
flowchart TD
    T["Scheduler kích hoạt timeout / reaper"]
    L{"Đã giữ lock group?"}
    P{"Nhóm đủ điều kiện?"}
    F["forceComplete / callback"]
    O{"Phát partial / discard?"}
    S["Cập nhật store theo transaction"]
    E["Error handling + retry policy"]
    T --> L
    L -->|Có| P
    L -->|Không| E
    P -->|Không| S
    P -->|Có| F
    F --> O
    O --> S
    F -. "Exception" .-> E
~~~

Sơ đồ khái quát các điểm cần kiểm soát, không phải một implementation transaction nguyên tử có sẵn. Chọn retry và rollback dựa trên thực tế message source, scheduler, JDBC/Redis transaction và kênh output.

## 10. Quan sát và chẩn đoán message store đang tăng

Không nên chỉ nhìn “số message còn lại” rồi kết luận chúng đều cũ hoặc vô dụng. Nên theo dõi thêm:

| Chỉ số | Ý nghĩa chẩn đoán |
|---|---|
| Số group đang mở, số group hoàn tất/rỗng | Phân biệt backlog chưa đủ fragment với tombstone |
| Tuổi group cũ nhất, phân bố tuổi theo correlation key | Phát hiện orphan và scheduler không quét |
| Số message đang chờ trong queue và tốc độ vào/ra | Xác định nghẽn consumer hay không có consumer |
| Số lần timeout/partial release/discard | Đo tác động chính sách quá hạn lên nghiệp vụ |
| Thời gian quét store, số group xử lý mỗi lượt | Phát hiện scan chậm, query chưa có index hoặc contention |
| Số lần scheduler task lỗi, rejected, lock timeout | Phát hiện cleanup bị bỏ lỡ hoặc nhiều instance tranh nhau |
| Transaction rollback khi cleanup | Đánh giá side effect có thể được thực thi lại |
| DB/Redis storage size, IO, serialization failures | Theo dõi chi phí vận hành và lỗi tương thích dữ liệu |

### Quy trình điều tra theo thứ tự

1. Xác định store đang phục vụ **aggregator, queue, delayer hay claim-check**; đọc đúng hợp đồng thành phần.
2. Xác nhận các endpoint/poller đã start, executor còn hoạt động, và không có sự cố upstream khiến group mãi không đủ fragment.
3. Tách số group đang chờ, group đã hoàn tất và message queue chưa được consumer lấy.
4. Kiểm tra cấu hình timeout, lịch scheduler thực tế, log callback <code>expire</code>, metric quét và exception.
5. Xác minh correlation key, schema serialization và chính sách message đến muộn.
6. Nếu bật purge, thử nghiệm trên dữ liệu mẫu, đối chiếu message được release, discard và thông tin còn trong store.
7. Với ứng dụng nhiều instance, kiểm tra lock, cùng region/partition và lịch chạy chồng nhau.
8. Sau điều chỉnh, so sánh tuổi nhóm cũ nhất, tốc độ cleanup, tỷ lệ timeout và backlog trong nhiều chu kỳ scheduler.

## 11. Kiểm thử tình huống hết hạn và dọn dữ liệu

Nên có các ca kiểm thử sau trước khi bật cleanup cho persistent store:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Đủ fragment trước timeout | Aggregator release bình thường; không có partial timeout |
| Thiếu fragment qua timeout | Có partial hoặc discard đúng policy; group được xóa/giữ metadata đúng cấu hình |
| Message đến ngay sau timeout | Không tạo duplicate side effect ngoài ý muốn |
| Không có message mới sau restart | <code>expireTimeout</code> hoặc reaper tìm và xử lý group cũ |
| Chu kỳ scheduler lớn hơn timeout | Cleanup diễn ra ở lần quét, không kỳ vọng đúng mili giây |
| Empty group nhiều ngày | Dấu vết hoàn tất được giữ đủ lâu rồi dọn theo chính sách |
| Consumer queue tạm dừng | Message vẫn tồn tại để tiếp tục xử lý; không bị dọn nhầm bởi policy dành cho group |
| Downstream nhận partial rồi lỗi | Error flow thấy exception; transaction/retry không tạo side effect trùng |
| Hai instance quét cùng một persistent store | Không double-release; lock/partition đúng |
| Chuyển phiên bản ứng dụng | Store cũ còn giải mã được; có kế hoạch migration hoặc quarantine cho schema cũ |

Với test timeout, nên dùng khoảng thời gian nhỏ và một cơ chế chờ theo điều kiện có timeout; tránh giả định scheduler thực thi tại thời điểm tuyệt đối. Với JDBC store, test cần database thực hoặc Testcontainers để kiểm tra transaction và concurrent cleanup. Không dùng unit test chỉ mock <code>MessageGroupStore</code> để chứng minh message sẽ được rollback hoặc giữ qua restart.

## 12. Checklist triển khai production

- [ ] Đã xác định rõ “cũ” theo **thời gian nào**: kể từ tạo group, kể từ message cuối, kể từ hoàn tất hay từ deadline nghiệp vụ.
- [ ] Đã phân biệt message đang chờ xử lý với metadata nhóm đã hoàn tất; không đặt một TTL chung thiếu căn cứ.
- [ ] Với aggregator, cấu hình rõ <code>groupTimeout</code>, partial/discard, <code>expireGroupsUponTimeout</code> và retention cho empty group.
- [ ] Với persistent store, đã đánh giá reaper hoặc <code>expireTimeout</code>/<code>expireDuration</code> để xử lý orphan sau restart.
- [ ] Mỗi correlating endpoint có store/partition và correlation key phù hợp; tránh callback hết hạn tác động nhầm group.
- [ ] Lịch cleanup, transaction, distributed lock và error handler được kiểm thử ở tải thực tế.
- [ ] Có chính sách xử lý message trễ, retry/redelivery, idempotency và lưu bản tin lỗi khi cần.
- [ ] Queue/channel/delayer/claim-check được quản lý theo semantics riêng, không xóa raw records tùy tiện.
- [ ] Có metric, cảnh báo, log correlation và kế hoạch khôi phục nếu retention quá ngắn; tránh log payload nhạy cảm.

**Kết luận:** Dọn message cũ trong Spring Integration là quản lý **vòng đời dữ liệu gắn với từng endpoint**, không phải chỉ thêm một cấu hình thời gian rồi xóa tất cả bản ghi quá hạn. Với aggregator, kết hợp <code>groupTimeout</code>, expiry callback, reaper hoặc orphan purge theo yêu cầu. Với queue và các store khác, cần retention ở đúng tầng cùng transaction, idempotency và chính sách replay rõ ràng. Cách tách ranh giới này giúp giới hạn dung lượng lưu trữ mà không phá vỡ cam kết xử lý message.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Aggregator (Group Timeout, Expiring Groups)](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
- [Spring Integration Javadoc — MessageGroupStoreReaper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/store/MessageGroupStoreReaper.html)
