# TTL, dọn dữ liệu và công bố sự kiện theo khả năng được cam kết

Một custom Spring Session repository không chỉ lưu session rồi trả lại theo ID. Nó còn phải thực hiện đúng hợp đồng về thời hạn hiệu lực, cập nhật thời điểm truy cập, xóa session và thông báo các thay đổi vòng đời mà implementation thực sự phát hiện được. Nếu repository tuyên bố hỗ trợ TTL nhưng chỉ xóa dữ liệu theo lịch, session đã hết hạn vẫn phải bị từ chối ngay khi đọc; việc dọn vật lý có thể diễn ra sau. Nếu repository tuyên bố phát sự kiện hết hạn, nó phải có một cơ chế phát hiện expiration và công bố event theo phạm vi được mô tả.

Bài học này tập trung vào cách thiết kế ba khả năng liên quan nhưng không đồng nhất:

- **TTL và expiration:** xác định lúc nào session không còn hợp lệ.
- **Cleanup:** thu hồi dữ liệu vật lý đã hết hạn để giải phóng storage.
- **Event publication:** thông báo session được tạo, xóa hoặc hết hạn cho listener và hệ thống liên quan.

Một repository tốt phải công bố rõ mức đảm bảo của từng khả năng: expiration được kiểm tra lúc đọc hay nhờ TTL native; cleanup chạy chủ động hay thụ động; event chỉ phát trong JVM hay được phân phối tới các node khác; event có thể trễ, lặp hoặc mất trong tình huống nào.

## 1. Hợp đồng SessionRepository và ranh giới trách nhiệm

Spring Session cung cấp abstraction `SessionRepository<S extends Session>`. Một implementation thông thường cung cấp các thao tác:

```java
public interface SessionRepository<S extends Session> {

    S createSession();

    void save(S session);

    S findById(String id);

    void deleteById(String id);
}
```

Đoạn trên minh họa các thao tác chính của repository; hãy dùng đúng interface từ phiên bản Spring Session trong dự án thay vì tự khai báo lại interface.

Ý nghĩa của các thao tác:

| Thao tác | Trách nhiệm |
| --- | --- |
| `createSession()` | Tạo một session mới với ID và trạng thái ban đầu phù hợp |
| `save(session)` | Lưu session và các thay đổi thuộc tính, thời gian truy cập, expiration |
| `findById(id)` | Tải session nếu nó tồn tại và còn hiệu lực; session đã hết hạn phải được xem như không còn tồn tại |
| `deleteById(id)` | Xóa session theo ID và thực hiện các side effect/event mà implementation cam kết |

`SessionRepository` không tự áp đặt một chiến lược cleanup vật lý duy nhất. Repository có thể dùng TTL của Redis, một cột thời gian hết hạn trong JDBC, một scheduled cleanup task hoặc kết hợp các cách trên. Tuy nhiên, implementation phải giữ đúng semantics của session: request không được khôi phục một session đã hết hạn chỉ vì bản ghi vật lý chưa được dọn.

Phân biệt rõ:

- **Expiration là quy tắc hiệu lực:** session đã hết hạn không được dùng để khôi phục SecurityContext.
- **Cleanup là công việc storage:** xóa key hoặc row đã hết hạn.
- **Event là thông báo:** cho listener biết một chuyển đổi vòng đời đã xảy ra hoặc đã được phát hiện.

Không nên coi ba việc này là một thao tác duy nhất hoặc hứa rằng chúng xảy ra cùng một thời điểm.

## 2. TTL của session được tính từ đâu?

Trong Spring Session, thời hạn không hoạt động thường được mô tả bằng `maxInactiveInterval`. Thời điểm hết hạn được tính dựa trên `lastAccessedTime` và khoảng không hoạt động tối đa:

```text
expiresAt = lastAccessedTime + maxInactiveInterval
```

Ví dụ:

```text
lastAccessedTime      = 10:00:00
maxInactiveInterval   = 30 phút
expiresAt             = 10:30:00
```

Nếu một request hợp lệ truy cập session lúc 10:12 và repository cập nhật `lastAccessedTime`, thời điểm hết hạn mới trở thành 10:42. Đây là idle timeout: hoạt động hợp lệ làm mới thời hạn. Nó khác absolute lifetime, là thời điểm hết hạn cố định kể từ lúc tạo session bất kể người dùng hoạt động.

Một ứng dụng có thể áp dụng cả hai:

- Idle timeout giới hạn thời gian session không được sử dụng.
- Absolute lifetime giới hạn tổng tuổi thọ của session, kể cả khi có hoạt động liên tục.

Spring Session repository cần thực hiện semantics của `Session#getMaxInactiveInterval()` và `Session#getLastAccessedTime()` nhất quán. Nếu ứng dụng muốn absolute lifetime, nên lưu thêm thời điểm tạo hoặc một deadline riêng theo chính sách; không diễn giải nhầm idle timeout thành absolute timeout.

### 2.1. Giá trị timeout đặc biệt

Đừng tự đặt ý nghĩa cho giá trị timeout âm, bằng không hoặc null. Hãy tuân theo contract của `Session` và phiên bản đang dùng. Trong nhiều API session, giá trị âm biểu thị không hết hạn theo inactivity timeout; giá trị bằng không có thể khiến session hết hạn ngay. Kiểm tra implementation và test rõ các trường hợp này.

Không để một node hiểu timeout âm là “không hết hạn” trong khi node khác hiểu là “hết hạn ngay”. Nếu custom repository lưu interval thành số giây, phải giữ được giá trị đặc biệt và độ chính xác cần thiết khi chuyển đổi.

## 3. Expiration logic phải được áp dụng ngay khi đọc

TTL native hoặc scheduled cleanup không đủ để bảo đảm session hết hạn bị từ chối ngay. Repository cần kiểm tra expiration khi đọc hoặc dùng storage primitive bảo đảm key hết hạn trước khi được trả về.

Với custom repository tự quản lý, logic khái quát:

```java
public Session findById(String id) {
    StoredSession stored = store.load(id);
    if (stored == null) {
        return null;
    }

    Instant expiresAt = stored.getExpiresAt();
    if (expiresAt != null && !clock.instant().isBefore(expiresAt)) {
        expireAndRemove(stored);
        return null;
    }

    return toSession(stored);
}
```

Đây là pseudocode; `StoredSession`, `store` và `expireAndRemove` thuộc implementation riêng. Điểm quan trọng là so sánh theo một nguồn thời gian nhất quán và không trả session đã hết hạn cho caller.

Nếu repository dùng `Session#isExpired()` trên object được khôi phục, phải bảo đảm object có đúng `lastAccessedTime`, `maxInactiveInterval` và clock semantics. Không chỉ kiểm tra TTL ở cleanup task rồi trả session cũ trong khoảng thời gian chờ dọn.

## 4. TTL vật lý và expiration logic là hai lớp

Một repository có thể lưu deadline tuyệt đối trong record và đặt TTL native ở storage:

| Lớp | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Logical expiration | Từ chối session ngay khi deadline đã qua | `findById` so sánh `expiresAt` với thời điểm hiện tại |
| Physical TTL | Cho storage tự thu hồi key/record sau deadline | Redis `PEXPIRE` hoặc TTL tương đương |
| Cleanup job | Dọn bản ghi hết hạn còn tồn tại | JDBC batch delete theo `EXPIRY_TIME` |
| Event publication | Thông báo session đã kết thúc | `SessionExpiredEvent` |

Nếu TTL native có độ trễ hoặc cleanup job chạy mỗi vài phút, logical expiration vẫn phải bảo vệ request. Cleanup chỉ giúp thu hồi dung lượng, index và metadata.

Đặt TTL storage dài hơn một chút so với logical deadline có thể giúp event/cleanup có thời gian xử lý, nhưng không được làm cho session tiếp tục hợp lệ sau logical deadline. Ngược lại, TTL vật lý ngắn hơn deadline có thể xóa session trước khi chính sách cho phép, gây logout sớm.

Hãy xác định độ chính xác cần thiết: giây hay mili giây. Làm tròn timeout xuống có thể làm session hết hạn sớm; làm tròn lên chỉ có thể chấp nhận nếu logical check vẫn từ chối tại deadline chính xác.

## 5. Cập nhật TTL khi session được truy cập

Mỗi lần request hợp lệ sử dụng session, `lastAccessedTime` có thể được cập nhật theo lifecycle của Spring Session. Custom repository cần lưu thời gian truy cập mới và tính lại expiration theo đúng semantics.

Ví dụ:

```java
public void save(MySession session) {
    Instant lastAccessed = session.getLastAccessedTime();
    Duration inactiveInterval = session.getMaxInactiveInterval();
    Instant expiresAt = calculateExpiry(lastAccessed, inactiveInterval);

    store.save(
            session.getId(),
            serialize(session),
            expiresAt);
}
```

Đây là ví dụ khái quát. Implementation thực tế cần xử lý interval không giới hạn, giá trị bằng không, serialization và thao tác storage nguyên tử phù hợp.

Các lỗi thường gặp:

- Chỉ cập nhật attributes nhưng quên cập nhật TTL.
- Cập nhật `lastAccessedTime` trong object nhưng không persist.
- Gia hạn TTL bằng một giá trị cố định không liên quan `maxInactiveInterval`.
- Tính TTL từ thời điểm save thay vì `lastAccessedTime`, làm request lưu trễ gia hạn session ngoài ý muốn.
- Đặt TTL cho key chính nhưng quên index phụ hoặc metadata.

Nếu repository dùng Redis, `EXPIRE`/`PEXPIRE` phải được áp dụng đúng key và đồng bộ với nội dung session. Nếu dùng JDBC, `EXPIRY_TIME` cần được cập nhật cùng record trong transaction thích hợp.

## 6. Race condition giữa request gia hạn và cleanup

Một vấn đề quan trọng xuất hiện khi hai thao tác chạy đồng thời:

1. Request A tải session và chuẩn bị cập nhật `lastAccessedTime`.
2. Cleanup worker B đọc thấy deadline cũ đã qua.
3. Request A lưu deadline mới.
4. Cleanup worker B xóa session theo kết quả cũ.

Kết quả là một session vừa được gia hạn vẫn bị xóa. Đây là race condition giữa refresh và expiration cleanup.

Các cách giảm rủi ro:

- Xóa có điều kiện theo deadline/version đã đọc, không xóa mù theo ID.
- Dùng optimistic version hoặc compare-and-delete nguyên tử.
- Với JDBC, dùng câu lệnh delete có điều kiện trên `EXPIRY_TIME` và chiến lược khóa/transaction phù hợp database.
- Với Redis, dùng Lua script hoặc thao tác nguyên tử kiểm tra deadline/version rồi xóa.
- Nếu session được gia hạn trước khi cleanup commit, cleanup phải nhận ra deadline đã thay đổi và bỏ qua.

Ví dụ SQL khái quát:

```sql
DELETE FROM APP_SESSION
WHERE SESSION_ID = :sessionId
  AND EXPIRY_TIME <= :observedExpiryCutoff;
```

Đây chỉ là minh họa. Một câu lệnh như trên cần dùng cutoff/version phù hợp và đảm bảo predicate phản ánh deadline mà cleanup đã quan sát; nếu chỉ dùng một cutoff quá rộng, vẫn có thể xóa session đã được gia hạn. Cách khóa row và isolation semantics phụ thuộc database.

Với Redis, không làm theo hai bước client-side `GET` rồi `DEL` nếu có thể có refresh xen giữa. Dùng Lua script hoặc primitive nguyên tử để kiểm tra và xóa trong cùng thao tác.

## 7. Cleanup thụ động và cleanup chủ động

Custom repository có thể kết hợp nhiều chiến lược:

### 7.1. Lazy cleanup khi đọc

Khi `findById` phát hiện session đã hết hạn, repository xóa hoặc đánh dấu để xóa và trả về không có session.

Ưu điểm:

- Không cần một job quét toàn bộ kho.
- Session hết hạn được dọn khi có truy cập.

Hạn chế:

- Session không bao giờ được truy cập lại có thể tồn tại vật lý lâu.
- Event expiration chỉ được phát nếu repository phát hiện được expiration.
- Tải cleanup có thể dồn vào request path.

### 7.2. Scheduled cleanup

Một worker định kỳ truy vấn các session có deadline đã qua rồi xóa theo batch.

Ưu điểm:

- Dọn được session không còn request truy cập.
- Có thể kiểm soát batch size và tải storage.

Hạn chế:

- Dữ liệu vật lý có thể tồn tại sau deadline cho tới lần chạy kế tiếp.
- Nhiều instance cùng chạy job có thể đụng nhau.
- Cần xử lý lock, lease hoặc xóa idempotent.

### 7.3. Native TTL của storage

Redis hoặc storage khác có thể tự thu hồi key sau TTL. Đây là cách hiệu quả để giải phóng key, nhưng thời điểm vật lý bị xóa có thể không chính xác tuyệt đối. Nếu cần event, repository phải biết notification có được bật và nhận hay không.

### 7.4. Kết hợp

Thiết kế thường dùng logical expiration khi đọc, native TTL để tự thu hồi key và cleanup job để sửa index/mapping phụ. Mỗi lớp có mục tiêu riêng; đừng dựa vào một cleanup job trễ để bảo vệ authorization.

## 8. Thiết kế scheduled cleanup cho custom repository

Một cleanup job an toàn nên:

1. Chọn batch session có deadline nhỏ hơn hoặc bằng thời điểm hiện tại.
2. Giới hạn số record mỗi batch.
3. Xóa có điều kiện để không xóa session vừa được gia hạn.
4. Commit thao tác xóa trước khi công bố event nếu event mô tả trạng thái đã xóa.
5. Tiếp tục batch kế tiếp theo giới hạn thời gian/tải.
6. Có metric cho số candidate, số xóa thành công, số bỏ qua do refresh và lỗi.

Ví dụ pseudocode:

```java
public CleanupResult cleanExpired(Instant now, int batchSize) {
    List<ExpiredCandidate> candidates =
            store.findExpiredCandidates(now, batchSize);

    int deleted = 0;
    for (ExpiredCandidate candidate : candidates) {
        boolean removed = store.deleteIfStillExpired(
                candidate.id(),
                candidate.observedVersion(),
                now);
        if (removed) {
            deleted++;
            publishExpired(candidate.snapshot());
        }
    }
    return new CleanupResult(candidates.size(), deleted);
}
```

Các kiểu `ExpiredCandidate`, `CleanupResult` và phương thức store ở đây là abstraction minh họa. Một implementation cần bảo đảm `deleteIfStillExpired` là atomic hoặc có transaction/locking phù hợp. Event không nên được phát chỉ vì record nằm trong danh sách candidate; nó chỉ nên được phát khi thao tác chuyển trạng thái đã được xác nhận.

Không quét toàn bộ bảng/keyspace mỗi giây. Với JDBC, tạo index phù hợp cho cột expiration và dùng batch delete. Với Redis, tận dụng TTL native và chỉ quét metadata cần thiết. Chọn chu kỳ cleanup theo dung lượng, SLA và độ trễ chấp nhận được.

## 9. Cleanup nhiều instance

Nếu mỗi application node chạy một scheduled cleanup job, nhiều node có thể cùng chọn một session hết hạn. Điều này không nhất thiết sai nếu delete idempotent và event consumer chịu được duplicate, nhưng có thể tăng tải và phát event lặp.

Các lựa chọn:

- **Single leader/lease:** chỉ một worker giữ lease chạy cleanup; cần xử lý lease expiry và leader failover.
- **Partitioned work:** chia shard hoặc key range để các worker xử lý phần riêng.
- **Concurrent batch với atomic delete:** nhiều worker cùng chạy nhưng thao tác delete có điều kiện và chỉ worker xóa thành công phát event.
- **Database locking/skip locked:** dùng khả năng database hỗ trợ để claim batch mà không tranh cùng row.

Không dùng một biến static hoặc synchronized lock trong JVM để bảo đảm chỉ có một cleanup worker trên toàn cluster. Lock local chỉ bảo vệ một process.

Khi worker crash sau khi xóa session nhưng trước khi publish event, event có thể bị mất nếu hai thao tác không có transaction chung. Phần tiếp theo trình bày cách xác định guarantee event và xử lý khoảng trống này.

## 10. Session lifecycle events trong Spring Session

Spring Session định nghĩa các event vòng đời thường gặp:

| Event | Ý nghĩa |
| --- | --- |
| `SessionCreatedEvent` | Một session mới được tạo/lưu theo cơ chế repository |
| `SessionDeletedEvent` | Một session bị xóa chủ động |
| `SessionExpiredEvent` | Một session hết hạn được phát hiện và xử lý |
| `SessionDestroyedEvent` | Nhóm event tổng quát cho session đã kết thúc; listener có thể dùng kiểu cha để xử lý delete và expire |

Event thường chứa session hoặc thông tin định danh session. Listener có thể dùng event để:

- Đóng WebSocket gắn với session.
- Thu hồi subscription hoặc resource phụ trợ.
- Cập nhật số liệu phiên đang hoạt động.
- Ghi audit lifecycle.
- Xóa index hoặc mapping do ứng dụng quản lý.

Không nên mặc định repository tự phát đủ mọi event. Hỗ trợ event phụ thuộc implementation và cách tích hợp. Một custom repository phải mô tả rõ event nào được hỗ trợ, event được phát ở thao tác nào, và điều kiện nào khiến event không thể được phát.

## 11. Công bố event từ custom repository

Trong Spring, một component có thể nhận `ApplicationEventPublisher` để công bố application event:

```java
public class CustomSessionRepository
        implements SessionRepository<CustomSession> {

    private final ApplicationEventPublisher eventPublisher;

    public CustomSessionRepository(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    private void publishCreated(CustomSession session) {
        eventPublisher.publishEvent(
                new SessionCreatedEvent(this, session));
    }

    private void publishDeleted(CustomSession session) {
        eventPublisher.publishEvent(
                new SessionDeletedEvent(this, session));
    }
}
```

Đây là đoạn minh họa phần publish; constructor, generic type và cách lấy session snapshot cần đối chiếu với API của Spring Session version đang dùng. Không copy class ví dụ vào dự án mà bỏ qua contract thực tế của repository.

Các nguyên tắc:

- Chỉ phát `SessionCreatedEvent` sau khi tạo/lưu session thành công theo semantics đã chọn.
- Chỉ phát `SessionDeletedEvent` khi delete đã được xác nhận.
- Chỉ phát `SessionExpiredEvent` khi repository phát hiện session hết hạn và đã xử lý chuyển trạng thái tương ứng.
- Không phát event expiration chỉ vì TTL được đặt; đặt deadline không có nghĩa session đã hết hạn.
- Không phát `SessionDeletedEvent` cho một delete thất bại.
- Event listener phải chịu được duplicate hoặc được guarantee khác một cách rõ ràng.

Với `save`, cần quyết định event created phát lúc `createSession()` hay lúc session được lưu lần đầu. Hãy theo semantics của Spring Session implementation tương thích và tránh phát hai lần cho cùng một session. Nếu session được tạo trong memory nhưng chưa được persist, không nên mô tả event như thể storage đã xác nhận tạo thành công.

## 12. Local application event không phải distributed event

`ApplicationEventPublisher` phát event trong Spring ApplicationContext hiện tại. Nó không tự broadcast event tới các JVM khác.

Trong hệ thống nhiều instance:

1. Node A xóa session trong Redis hoặc JDBC.
2. A phát `SessionDeletedEvent` trong ApplicationContext của A.
3. Listener ở A nhận event.
4. Listener ở B không tự động nhận event chỉ vì B dùng cùng repository.

Nếu event chỉ phục vụ cleanup local trên node thực hiện delete, local event có thể đủ. Nếu cần đóng WebSocket hoặc thu hồi resource đang nằm trên node khác, phải dùng kênh phân phối:

- Redis Pub/Sub hoặc message broker.
- Database outbox và publisher worker.
- Một event bus nội bộ được cấu hình cho cluster.
- Cơ chế command routing tới node sở hữu resource.

Đừng nhầm việc session data được chia sẻ với việc application event được chia sẻ. Shared storage không tự biến event local thành cluster-wide event.

## 13. Event guarantee: best effort, at-least-once và outbox

Khi thiết kế custom repository, phải công bố rõ guarantee:

| Mô hình | Đặc điểm | Hệ quả |
| --- | --- | --- |
| Best effort local event | Publish trong JVM sau thao tác storage | Có thể mất khi process dừng; node khác không nhận |
| Broker publish trực tiếp | Gửi message sau khi storage thay đổi | Có khoảng trống nếu process crash giữa commit và publish |
| At-least-once delivery | Message có thể được retry | Consumer phải idempotent và chấp nhận duplicate |
| Transactional outbox | Ghi trạng thái session và outbox record trong cùng transaction DB | Publisher có thể gửi lại sau crash; consumer vẫn nên idempotent |
| Exactly-once end-to-end | Cần semantics mạnh xuyên storage, broker và consumer | Không nên hứa nếu không có thiết kế và bằng chứng cụ thể |

Nếu custom repository dùng cùng relational database cho session và outbox, có thể ghi một outbox row trong cùng transaction với delete. Worker riêng đọc outbox và publish tới broker; sau khi broker xác nhận, đánh dấu event đã gửi. Nếu worker crash sau publish nhưng trước khi đánh dấu, event có thể được gửi lại, vì vậy consumer cần idempotency key.

Nếu session nằm ở Redis còn outbox nằm ở database khác, không có transaction nguyên tử mặc định giữa hai kho. Cần chọn một source of truth, chấp nhận consistency model rõ ràng hoặc dùng một workflow bền vững phù hợp; không gọi đó là transactional outbox nguyên tử khi hai thao tác không cùng transaction.

## 14. Thứ tự publish và snapshot event

Event cần mang đủ thông tin để listener thực hiện cleanup nhưng không nên mang toàn bộ session attributes nhạy cảm.

Thông tin thường cần:

- Session ID hoặc định danh event cần thiết cho consumer.
- Event type: created, deleted hoặc expired.
- Thời điểm event được tạo.
- Phiên bản/sequence nếu cần xử lý ordering.
- Principal name nếu chính sách cho phép và listener thực sự cần.
- Correlation ID hoặc source node.

Session ID là định danh nhạy cảm; không ghi nó vào log thông thường và không gửi ra client. Tránh serialize toàn bộ SecurityContext, access token, refresh token hoặc attribute chứa dữ liệu cá nhân vào event message.

Với event xóa/hết hạn, có thể cần một snapshot tối thiểu trước khi xóa để listener biết principal hoặc resource liên quan. Snapshot phải được lấy trước delete nhưng chỉ publish sau khi delete được xác nhận. Nếu cần audit, hãy lưu metadata tối thiểu riêng thay vì giữ toàn bộ session object.

Event có thể đến sai thứ tự nếu publish qua nhiều worker hoặc broker partition khác nhau. Nếu consumer cần thứ tự theo session, dùng key partition ổn định hoặc sequence/version và bỏ qua event cũ. Không giả định global ordering giữa tất cả session.

## 15. Expired event khác deleted event

Hai trường hợp có thể cùng kết thúc session nhưng nguyên nhân khác:

- **Deleted:** logout, quản trị viên revoke, hoặc ứng dụng gọi delete.
- **Expired:** idle timeout/absolute expiration được repository phát hiện.

Listener có thể xử lý cả hai qua `SessionDestroyedEvent`, nhưng audit và nghiệp vụ đôi khi cần phân biệt nguyên nhân:

| Nhu cầu | Cách xử lý |
| --- | --- |
| Đóng WebSocket sau mọi kiểu kết thúc | Lắng nghe event cha `SessionDestroyedEvent` |
| Thống kê logout chủ động | Lắng nghe `SessionDeletedEvent` hoặc audit logout riêng |
| Thống kê idle expiration | Lắng nghe `SessionExpiredEvent` |
| Revoke resource theo account | Dùng principal/session metadata đã xác thực, không suy ra từ event thiếu dữ liệu |

Không suy luận rằng mọi `SessionDeletedEvent` đều là người dùng bấm logout. Session có thể bị xóa bởi quản trị viên, cleanup hoặc code nghiệp vụ. Nếu cần biết actor và lý do, ghi audit command riêng khi thực hiện thao tác.

## 16. Cleanup index và dữ liệu phụ trợ

Repository thường lưu thêm index hoặc metadata:

- Principal name → session IDs.
- Session ID → node/resource mapping.
- WebSocket session registry.
- Outbox event.
- Session activity metadata.

Khi session hết hạn, cần dọn hoặc làm cho index phụ trở nên an toàn:

- Nếu xóa session nhưng không xóa principal index, truy vấn có thể trả ID mồ côi.
- Nếu xóa index trước rồi delete session thất bại, session còn tồn tại nhưng không tìm được theo principal.
- Nếu cleanup event được phát trước khi commit, consumer có thể xóa resource trong khi session vẫn hợp lệ.
- Nếu event bị lặp, cleanup phụ trợ phải idempotent.

Với Redis, nhiều key có thể liên kết với session; cần bảo đảm TTL và cleanup áp dụng đúng cho key chính lẫn index. Với JDBC, foreign key/cascade hoặc batch cleanup phải được thiết kế để không tạo row mồ côi và không xóa nhầm dữ liệu mới.

## 17. Đồng hồ và độ chính xác thời gian

Expiration phụ thuộc thời gian. Nếu node A và B lệch clock, chúng có thể đưa ra kết luận khác nhau về cùng một session:

- A thấy session còn hạn và gia hạn.
- B thấy session đã hết hạn và xóa.

Các nguyên tắc:

- Đồng bộ clock của node bằng NTP hoặc dịch vụ thời gian hạ tầng.
- Lưu thời gian dưới dạng UTC/Instant, tránh phụ thuộc timezone địa phương.
- Chọn độ chính xác thống nhất khi lưu deadline.
- Dùng một Clock có thể inject vào code để test.
- Không trộn thời gian client với thời gian server để quyết định session expiration.
- Với cleanup nhiều node, dùng cutoff nhất quán hoặc thời gian do storage/database cung cấp nếu thiết kế yêu cầu.

Không thêm một grace period tùy tiện để “chữa” clock drift. Nếu chính sách có grace period, định nghĩa rõ nó áp dụng cho logical expiration hay chỉ cho cleanup vật lý.

## 18. Quan sát TTL, cleanup và event pipeline

Các metric cần thiết:

| Metric | Mục đích |
| --- | --- |
| Session count theo trạng thái | Theo dõi số session active/expired/pending cleanup |
| Expired candidates | Số session được cleanup worker phát hiện |
| Physical deletes | Số session thực sự được xóa |
| Cleanup lag | Khoảng cách giữa deadline và thời điểm xóa vật lý |
| Cleanup batch duration | Phát hiện batch quá chậm |
| Cleanup errors/retries | Phát hiện lỗi storage hoặc contention |
| Created/deleted/expired events | Theo dõi event publication |
| Event publish failures | Phát hiện khoảng trống giữa storage và event |
| Event delivery lag/backlog | Đo thời gian consumer nhận event |
| Duplicate event count | Đánh giá retry và idempotency |
| Orphan index count | Phát hiện metadata không còn session |

Không gắn session ID hoặc principal name làm metric label vì cardinality cao và rủi ro lộ dữ liệu. Dùng node ID, repository type, operation và event type làm dimension có kiểm soát.

Log nên có correlation ID, batch ID, node ID và số lượng record. Không log session attributes hoặc SecurityContext.

## 19. Kiểm thử TTL, cleanup và event

Không chỉ kiểm tra rằng `findById` trả null sau khi chờ timeout. Cần kiểm tra cả expiration logic, physical cleanup và event guarantee.

Các kịch bản:

1. **Idle timeout:** tạo session, đặt lastAccessedTime và maxInactiveInterval, xác nhận session hợp lệ trước deadline và không hợp lệ sau deadline.
2. **Access refresh:** truy cập session trước deadline, xác nhận lastAccessedTime/TTL được cập nhật và cleanup không xóa session đã gia hạn.
3. **Expired read:** session đã hết hạn nhưng bản ghi vật lý còn; findById vẫn phải coi như không tồn tại.
4. **Lazy cleanup:** đọc session hết hạn và xác nhận metadata được dọn hoặc đưa vào cleanup theo thiết kế.
5. **Scheduled cleanup:** tạo nhiều session hết hạn, chạy batch và xác nhận chỉ các record hết hạn bị xóa.
6. **Concurrent refresh/delete:** chạy request save đồng thời cleanup; session được gia hạn không bị xóa bởi candidate cũ.
7. **Multiple cleanup workers:** nhiều worker chạy cùng lúc không xóa nhầm session mới và event không tạo tác động lặp nguy hiểm.
8. **Created event:** chỉ phát event theo đúng thời điểm repository cam kết tạo/persist session.
9. **Deleted event:** delete thành công phát event; delete thất bại không được báo như đã xóa.
10. **Expired event:** event chỉ phát khi repository phát hiện và xử lý expiration theo implementation.
11. **Crash window:** mô phỏng process dừng sau delete nhưng trước publish; xác nhận outbox/reconciliation đáp ứng guarantee đã công bố.
12. **Duplicate delivery:** consumer xử lý event lặp an toàn.
13. **Multi-instance:** event từ node A đến được node B nếu implementation tuyên bố distributed event.
14. **Clock boundary:** kiểm tra deadline chính xác, rounding và clock skew có kiểm soát.
15. **Index cleanup:** principal index và metadata phụ không còn trỏ tới session đã xóa.

Dùng fake/injectable Clock cho unit test expiration để không phải chờ thời gian thật. Integration test với Redis/JDBC thật để kiểm tra TTL, cleanup query, notification và transaction. Với event async, dùng latch hoặc polling có timeout thay vì sleep cố định dài.

## 20. Những lỗi thiết kế thường gặp

- **Chỉ dựa vào scheduled cleanup để xác định session hợp lệ:** session quá hạn vẫn có thể được đọc trong thời gian chờ job.
- **Chỉ đặt TTL native mà không kiểm tra expiration:** repository tùy chỉnh có thể trả session không còn hợp lệ nếu storage chưa xóa key.
- **Gia hạn key nhưng không cập nhật lastAccessedTime:** các node có thể tính expiration khác nhau.
- **Tính TTL từ thời điểm save thay vì last access:** request lưu trễ làm thay đổi semantics idle timeout.
- **Cleanup xóa theo candidate cũ:** request vừa refresh session vẫn bị xóa.
- **Quét toàn bộ storage quá thường xuyên:** tăng tải và ảnh hưởng request path.
- **Mọi node phát event local và tưởng là cluster-wide:** listener trên node khác không nhận được event.
- **Publish event trước khi delete commit:** consumer phản ứng với thay đổi chưa thực sự hoàn tất.
- **Không có outbox nhưng hứa event bền vững:** process crash có thể làm mất event sau khi session đã bị xóa.
- **Giả định exactly-once:** retry và crash thường tạo duplicate; consumer cần idempotent.
- **Đưa toàn bộ session vào event/log:** có thể làm lộ SecurityContext, token và dữ liệu cá nhân.
- **Không dọn index phụ:** session đã xóa vẫn xuất hiện trong principal index hoặc registry.
- **Không kiểm soát clock:** node khác nhau về kết luận expiration.

## 21. Checklist công bố khả năng của custom repository

Trước khi đưa repository vào dùng, tài liệu implementation cần nói rõ:

- [ ] Cách tính deadline từ lastAccessedTime và maxInactiveInterval.
- [ ] Cách xử lý timeout đặc biệt như không hết hạn hoặc hết hạn ngay.
- [ ] findById có từ chối session hết hạn ngay cả khi record chưa bị dọn hay không.
- [ ] TTL native có được sử dụng không và độ chính xác của nó.
- [ ] Cleanup là lazy, scheduled, native TTL hay kết hợp.
- [ ] Chu kỳ, batch size, locking/lease và retry của cleanup.
- [ ] Cách ngăn cleanup xóa session vừa được gia hạn.
- [ ] Cách dọn principal index và metadata phụ.
- [ ] Các event created/deleted/expired nào được hỗ trợ.
- [ ] Event được phát sau khi thao tác storage được xác nhận như thế nào.
- [ ] Event local hay distributed; node nào nhận được.
- [ ] Guarantee delivery: best effort, at-least-once hoặc guarantee khác có bằng chứng.
- [ ] Cách xử lý crash giữa commit và publish, ví dụ outbox/reconciliation.
- [ ] Consumer phải xử lý duplicate và ordering ra sao.
- [ ] Metric, log và cảnh báo không làm lộ session ID hoặc attributes.
- [ ] Có test expiration boundary, concurrent refresh/cleanup và multi-instance event.

## 22. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- TTL của session idle được tính từ lastAccessedTime và maxInactiveInterval như thế nào?
- Vì sao logical expiration phải được kiểm tra khi đọc dù storage có native TTL?
- Cleanup vật lý khác expiration semantics ra sao?
- Làm thế nào để cleanup không xóa session vừa được request khác gia hạn?
- Vì sao scheduled cleanup trên nhiều node cần claim/lease, partition hoặc atomic delete?
- SessionExpiredEvent khác SessionDeletedEvent ở nguyên nhân nào?
- Vì sao ApplicationEventPublisher không tự gửi event sang JVM khác?
- Transactional outbox giải quyết crash window nào và vì sao consumer vẫn cần idempotency?
- Những thông tin nào nên và không nên có trong lifecycle event?
- Repository cần công bố guarantee gì về TTL, cleanup và event để người dùng không hiểu quá mức khả năng thực tế?

Một custom Spring Session repository phải từ chối session hết hạn ngay cả khi cleanup vật lý chưa chạy, cập nhật TTL theo đúng thời điểm truy cập và xóa dữ liệu theo cách không đụng với request vừa gia hạn. Event chỉ nên phản ánh chuyển đổi mà repository đã phát hiện và xử lý; local event không phải distributed event, còn bảo đảm giao nhận bền vững cần outbox hoặc cơ chế tương đương. Hãy công bố rõ phạm vi, độ trễ và failure mode của TTL, cleanup và event thay vì hứa một guarantee mà implementation không thực hiện được.
