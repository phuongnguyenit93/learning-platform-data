# Xác nhận sự kiện tạo, xóa, hết hạn theo khả năng repository

Spring Session có các sự kiện vòng đời để ứng dụng phản ứng khi session được tạo, bị xóa hoặc hết hạn. Những event này có thể dùng để ghi audit, đóng WebSocket, thu hồi subscription, cập nhật thống kê hoặc dọn dữ liệu phụ trợ. Tuy nhiên, không phải mọi `SessionRepository` đều cung cấp cùng một tập event, cùng thời điểm phát hoặc cùng phạm vi phân phối. Một bài kiểm thử tích hợp đúng phải xác nhận những gì repository đang cấu hình thực sự cam kết, thay vì mặc định rằng mọi thao tác session đều phát event giống nhau.

Bài học này tập trung vào ba loại sự kiện:

- `SessionCreatedEvent`: thông báo session được tạo theo semantics của repository.
- `SessionDeletedEvent`: thông báo session bị xóa chủ động.
- `SessionExpiredEvent`: thông báo repository phát hiện và xử lý session hết hạn.

`SessionDeletedEvent` và `SessionExpiredEvent` là các dạng session destroyed; listener chung có thể dùng `SessionDestroyedEvent` khi cần xử lý mọi kiểu kết thúc. Phần kiểm thử cần xác định event được phát ở node hiện tại hay được phân phối tới các node khác, event có thể trễ/lặp/mất trong tình huống nào, và liệu repository có hỗ trợ expiration event hay chỉ bảo đảm session hết hạn không còn được đọc.

## 1. Event không phải là một phần giống nhau của mọi repository

Spring Session cung cấp các abstraction session và event, nhưng mức hỗ trợ phụ thuộc implementation, cấu hình và phiên bản. Một custom repository có thể lưu, tìm và xóa session mà không publish bất kỳ lifecycle event nào. Một repository khác có thể publish event trong Spring ApplicationContext. Một implementation dựa trên Redis có thể dùng keyspace notification để phát hiện expiration. JDBC có thể dọn các row hết hạn bằng batch SQL mà không dựng lại từng session để phát một event cho từng row.

Vì vậy, trước khi viết assertion, xác định capability thực tế:

| Capability | Câu hỏi phải trả lời |
| --- | --- |
| Created event | Event phát khi gọi `createSession()`, khi `save()` lần đầu hay tại thời điểm khác? |
| Deleted event | `deleteById` hoặc invalidate có phát event sau khi xóa thành công không? |
| Expired event | Repository phát hiện expiration bằng native TTL, keyspace notification, cleanup task hay cách khác? |
| Local delivery | Listener trong ApplicationContext thực hiện thao tác có nhận event không? |
| Distributed delivery | Các node khác có nhận được event không? |
| Delivery guarantee | Event best effort, có thể lặp, có retry hay được lưu bền vững? |
| Timing | Event phát đồng bộ, bất đồng bộ hay trễ theo chu kỳ cleanup? |

Không suy ra capability từ tên repository hoặc việc repository dùng chung Redis/JDBC. Ghi rõ implementation và cấu hình thực tế trong test profile. Nếu repository không cam kết một event, test không được ép nó phải phát event đó; hãy kiểm thử semantics session mà repository có hỗ trợ và ghi nhận event capability là không được cung cấp.

## 2. Phân biệt event với trạng thái session

Event là thông báo về một thay đổi hoặc một thay đổi đã được phát hiện. Nó không thay thế việc kiểm tra trạng thái session trong repository.

| Điều cần xác minh | Bằng chứng chính |
| --- | --- |
| Session đã được tạo và lưu | `findById(id)` đọc lại được session |
| Session đã bị xóa | `findById(id)` không còn trả session sau delete |
| Session đã hết hạn | Repository không còn trả session sau deadline |
| Event created được phát | Listener nhận `SessionCreatedEvent` gắn với đúng ID |
| Event deleted được phát | Listener nhận `SessionDeletedEvent` gắn với đúng ID |
| Event expired được phát | Listener nhận `SessionExpiredEvent` gắn với đúng ID |

Một test chỉ xác nhận event đã tới listener nhưng không đọc lại repository có thể bỏ sót trường hợp event được phát sai thời điểm, trước khi storage commit hoặc cho nhầm session. Ngược lại, test xác nhận session đã bị xóa không chứng minh event đã được publish.

Hãy kiểm tra cả hai mặt: trạng thái repository và event stream. Event phải tương quan với đúng session ID, đúng loại thao tác và đúng thời điểm theo contract.

## 3. Các event vòng đời của Spring Session

Spring Session định nghĩa các event phổ biến trong package `org.springframework.session.events`:

| Event | Ý nghĩa |
| --- | --- |
| `SessionCreatedEvent` | Session được tạo theo semantics của repository |
| `SessionDeletedEvent` | Session bị xóa chủ động |
| `SessionExpiredEvent` | Session hết hạn và được repository phát hiện/xử lý |
| `SessionDestroyedEvent` | Event cha dùng để xử lý chung các kiểu session kết thúc |

`SessionDestroyedEvent` thường là kiểu phù hợp khi một listener cần đóng tài nguyên phụ trợ sau mọi kiểu kết thúc. Nếu cần phân biệt logout/revoke với idle expiration, hãy xử lý các kiểu con hoặc ghi audit nghiệp vụ riêng.

Không suy luận rằng `SessionDeletedEvent` luôn có nghĩa người dùng bấm nút logout. Session có thể bị xóa bởi quản trị viên, code nghiệp vụ, cleanup hoặc thao tác invalidate. Nếu cần actor, nguyên nhân và request ID, ghi audit tại nơi phát lệnh xóa thay vì suy ra từ lifecycle event.

## 4. Xác định thời điểm phát event

Thời điểm phát event là một phần của contract cần kiểm thử:

- Với created event, repository có thể phát khi session được persist lần đầu, không nhất thiết ngay lúc tạo object trong memory.
- Với deleted event, event nên phản ánh thao tác xóa đã được chấp nhận theo semantics của repository. Không coi một request delete thất bại là xóa thành công.
- Với expired event, repository phải phát hiện session đã hết hạn. Việc đặt TTL hôm nay không có nghĩa event expiration được phát ngay tại thời điểm cấu hình TTL.
- Với cleanup theo lịch, event có thể trễ tới lần chạy cleanup tiếp theo.
- Với Redis keyspace notification, event phụ thuộc Redis phát notification và listener nhận được notification.

Không viết test đòi event xuất hiện tức thì nếu implementation cam kết xử lý bất đồng bộ hoặc theo chu kỳ. Dùng timeout có giới hạn và đặt ngưỡng theo SLA/cấu hình thực tế.

## 5. Chuẩn bị integration test với repository thật

Test event phải khởi động application context chứa repository và publisher thực tế. Ví dụ với Spring Boot:

```java
@SpringBootTest
class SessionLifecycleEventIntegrationTests {

    @Autowired
    ReactiveSessionRepository<? extends Session> repository;

    @Autowired
    SessionEventProbe eventProbe;
}
```

Đây là khung minh họa; ứng dụng Servlet có thể dùng `SessionRepository` đồng bộ, còn WebFlux dùng `ReactiveSessionRepository`. Chọn đúng abstraction mà module đang kiểm thử. Nếu mục tiêu là xác nhận Redis/JDBC thật, cấu hình test phải trỏ tới storage test riêng và không thay repository bằng mock.

Trước khi chạy test, xác minh:

- Repository bean được nạp là implementation mong muốn.
- Connection trỏ tới Redis/database dành riêng cho test.
- Namespace hoặc schema được cô lập.
- Event listener được đăng ký trong ApplicationContext.
- Các cấu hình keyspace notification, cleanup scheduler hoặc message listener đã bật nếu event phụ thuộc chúng.
- Không có profile test âm thầm thay repository thật bằng in-memory implementation.

## 6. Thu thập event bằng listener trong test

Một probe có thể thu thập event theo loại và session ID. Cách này dùng được cho event đồng bộ và bất đồng bộ nếu test chờ có giới hạn:

```java
record ObservedSessionEvent(String type, String sessionId) {
}

@TestConfiguration
static class EventProbeConfiguration {

    @Bean
    SessionEventProbe sessionEventProbe() {
        return new SessionEventProbe();
    }
}

class SessionEventProbe {

    private final Queue<ObservedSessionEvent> events =
            new ConcurrentLinkedQueue<>();

    @EventListener
    void onCreated(SessionCreatedEvent event) {
        events.add(new ObservedSessionEvent(
                "created", event.getSession().getId()));
    }

    @EventListener
    void onDestroyed(SessionDestroyedEvent event) {
        String type;
        if (event instanceof SessionExpiredEvent) {
            type = "expired";
        }
        else if (event instanceof SessionDeletedEvent) {
            type = "deleted";
        }
        else {
            type = "destroyed";
        }
        events.add(new ObservedSessionEvent(
                type, event.getSession().getId()));
    }

    boolean contains(String type, String sessionId) {
        return events.stream().anyMatch(event ->
                event.type().equals(type)
                        && event.sessionId().equals(sessionId));
    }

    void clear() {
        events.clear();
    }
}
```

Đoạn code minh họa dùng Java record và event API của Spring Session. Nếu dự án dùng Java cũ hơn, thay record bằng class bất biến. Hãy đối chiếu method lấy Session của event với phiên bản thư viện đang dùng.

Listener trên chỉ đăng ký một handler cho `SessionDestroyedEvent`, sau đó phân loại event con bằng `instanceof`. Không đăng ký đồng thời handler cho cả event cha và event con rồi vô tình đếm cùng một event hai lần.

Có thể dùng `@RecordApplicationEvents` của Spring Test nếu phiên bản hỗ trợ. Probe riêng hữu ích khi cần chờ event async, tương quan session ID hoặc quan sát event được phát sau khi test bắt đầu.

Không log session ID trong CI output. Probe giữ ID trong memory để assertion; log chỉ nên dùng event type, correlation ID giả lập và số lượng event.

## 7. Chờ event bất đồng bộ có timeout

Một số event được phát trong cùng thread, số khác đến qua listener container, Redis Pub/Sub hoặc broker. Không dùng `Thread.sleep` cố định rồi giả định event đã tới.

Với Awaitility:

```java
await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(eventProbe.contains("created", sessionId))
                        .isTrue());
```

Timeout 5 giây chỉ là giá trị minh họa. Chọn thời gian phù hợp với môi trường CI và SLA của repository. Nếu event không đến, assertion phải thất bại với thông tin loại event, session fixture và implementation đang kiểm thử, nhưng không in session ID bí mật.

Đối với event có thể đến trễ theo cleanup schedule, dùng deadline dài hơn hoặc kích hoạt cleanup task theo cơ chế test được hỗ trợ. Không tăng timeout vô hạn để che việc event listener chưa được cấu hình.

## 8. Kiểm thử SessionCreatedEvent

Test created event cần chứng minh:

1. Repository tạo và lưu một session mới theo contract.
2. Session có thể được đọc lại bằng ID.
3. Event created được listener nhận nếu repository cam kết hỗ trợ.
4. Event gắn với đúng session ID.
5. Event không bị phát lặp ngoài guarantee đã công bố.

Ví dụ với repository reactive:

```java
Mono<String> createAndPersistSession() {
    return repository.createSession()
            .flatMap(session -> {
                session.setAttribute("test-marker", "created");
                return repository.save(session)
                        .thenReturn(session.getId());
            });
}

@Test
void publishesCreatedEventForPersistedSession() {
    eventProbe.clear();

    String sessionId = createAndPersistSession().block();

    StepVerifier.create(repository.findById(sessionId))
            .assertNext(session ->
                    assertThat(session.getAttribute("test-marker"))
                            .isEqualTo("created"))
            .verifyComplete();

    await().atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                    assertThat(eventProbe.contains("created", sessionId))
                            .isTrue());
}
```

Ví dụ dùng `block()` tại ranh giới test để lấy ID cho các assertion tiếp theo. Trong test reactive thuần, có thể giữ toàn bộ flow trong `Mono` và dùng `StepVerifier`; không đưa `block()` vào production reactive chain.

Điểm cần xác nhận theo repository:

- Created event phát khi `createSession()` hay khi session được lưu lần đầu?
- `save()` nhiều lần có phát thêm created event không?
- Nếu save thất bại, repository có tránh phát event created như thể persist thành công không?
- Nếu session được tạo nhưng chưa từng được persist, implementation có coi đó là created event hay không?

Không assert một thời điểm cụ thể nếu repository không cam kết. Ghi rõ trigger được hỗ trợ trong test name và tài liệu.

## 9. Kiểm thử SessionDeletedEvent

Deleted event thường liên quan thao tác xóa chủ động như `deleteById`, invalidate hoặc logout. Test nên kiểm tra trạng thái sau delete và event tương ứng:

```java
@Test
void publishesDeletedEventAfterSuccessfulDelete() {
    String sessionId = createAndPersistSession().block();
    eventProbe.clear();

    repository.deleteById(sessionId).block();

    StepVerifier.create(repository.findById(sessionId))
            .verifyComplete();

    await().atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                    assertThat(eventProbe.contains("deleted", sessionId))
                            .isTrue());
}
```

Đây là khung cho reactive repository. Với repository đồng bộ, gọi `deleteById` trực tiếp và xác minh `findById` trả `null`.

Các trường hợp bổ sung:

- Delete thành công phải làm session không còn được đọc.
- Delete lỗi không được bị ghi nhận như delete thành công.
- Delete một ID không tồn tại có thể không phát event; hãy theo contract cụ thể.
- Delete lặp phải an toàn. Có phát event cho mỗi lần gọi hay chỉ cho lần chuyển trạng thái đầu tiên là quyết định implementation cần công bố.
- Logout HTTP phải được kiểm tra qua filter/security integration nếu cần chứng minh đường logout thực tế gọi đúng repository.

Không chỉ xóa cookie ở client rồi kết luận session đã bị xóa khỏi storage. Cookie hết hạn là hành vi phía browser; `SessionDeletedEvent` và repository state là bằng chứng phía server.

## 10. Kiểm thử SessionExpiredEvent

Expired event thường khó kiểm thử hơn vì repository cần phát hiện expiration. Test cần phân biệt:

- Session đã hết hạn về mặt logic.
- Key/row đã bị xóa vật lý.
- Event expiration đã được phát.

Ví dụ với repository cho phép đặt idle interval ngắn:

```java
@Test
void publishesExpiredEventWhenRepositorySupportsExpirationEvents() {
    String sessionId = createSessionWithShortIdleTimeout(
            Duration.ofSeconds(1)).block();

    await().atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                    assertThat(repository.findById(sessionId).hasElement()
                            .block()).isFalse());

    await().atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                    assertThat(eventProbe.contains("expired", sessionId))
                            .isTrue());
}
```

Đây là pseudocode cho helper tạo session và polling. Trong implementation thực tế, có thể dùng một polling helper reactive để chờ `Mono.hasElement()` hoàn tất mà không tạo subscription rời. Điều quan trọng là không coi event là bằng chứng duy nhất của expiration.

Không phải mọi repository đều phát `SessionExpiredEvent`. Nếu implementation chỉ bảo đảm `findById` không trả session sau deadline và cleanup job xóa dữ liệu, test cần xác minh hai khả năng đó, không ép event không được hỗ trợ.

## 11. Redis: keyspace notification và event expiration

Một số repository Spring Session Redis, đặc biệt implementation có index và event support, dựa vào Redis keyspace notifications để phát hiện key hết hạn hoặc bị xóa. Vì vậy, expiration event phụ thuộc cấu hình Redis và listener container.

Các điểm phải xác minh:

- Redis cho phép và bật nhóm keyspace/keyevent notification mà phiên bản Spring Session yêu cầu.
- `RedisMessageListenerContainer` hoặc thành phần listener tương ứng đã khởi động.
- Ứng dụng subscribe đúng channel và database/namespace.
- Managed Redis không chặn cấu hình notification cần thiết.
- Notification đến được instance đang có listener.
- Nếu repository dùng shadow/phantom key để giữ metadata cho event, TTL của key phụ trợ và cleanup được cấu hình đúng.

Trong một số cấu hình, giá trị notification tương tự `Egx` được dùng để bật keyevent cùng event generic/expired. Đừng chép cứng giá trị này mà không kiểm tra tài liệu phiên bản Spring Session và Redis đang triển khai; yêu cầu chính xác phụ thuộc implementation.

Redis expiration không nhất thiết phát notification đúng thời điểm TTL chạm 0. Redis có thể xử lý expiration sau đó, và event listener có thể nhận trễ hơn nữa. Test cần dùng polling có timeout thay vì đòi event xuất hiện tức thì.

Nếu notification bị tắt, session vẫn có thể hết hạn và không còn đọc được, nhưng event listener không nhận `SessionExpiredEvent`. Đây là khác biệt giữa session semantics và event capability.

## 12. JDBC: cleanup row và khả năng phát event

Với JDBC, repository có thể lưu expiration time trong bảng session và dùng tác vụ cleanup để xóa row đã hết hạn. Một batch SQL xóa nhiều row có thể không tải từng session lên memory; do đó implementation không nhất thiết có đủ dữ liệu để phát một `SessionExpiredEvent` cho từng row.

Khi kiểm thử JDBC:

1. Tạo session với expiration time có thể kiểm soát.
2. Xác nhận session được đọc trước deadline.
3. Đưa thời gian hết hạn qua deadline hoặc dùng fixture/clock hỗ trợ.
4. Xác nhận repository từ chối session đã hết hạn.
5. Chạy cleanup task theo cơ chế thật.
6. Xác nhận row hết hạn được dọn.
7. Chỉ assert `SessionExpiredEvent` nếu repository cụ thể cam kết publish event đó.

Nếu yêu cầu nghiệp vụ cần event cho mỗi session hết hạn nhưng repository JDBC hiện tại chỉ xóa batch mà không publish event, cần bổ sung cơ chế có chủ đích: query candidate trước khi delete, phát event sau commit, hoặc ghi outbox trong cùng transaction. Không thể suy ra event đã được phát chỉ từ việc row biến mất.

Với custom JDBC repository, kiểm tra transaction boundary. Nếu event được publish trước khi transaction commit rồi transaction rollback, consumer có thể xử lý một expiration chưa xảy ra. Nếu publish sau commit nhưng process crash trước publish, event có thể mất. Transactional outbox là lựa chọn khi cần delivery bền vững.

## 13. Local event và distributed event

Spring `ApplicationEventPublisher` phát event trong ApplicationContext hiện tại. Điều này không tự động broadcast event tới các JVM khác.

Ví dụ:

- Node A xử lý logout và xóa session.
- A phát `SessionDeletedEvent` trong context của A.
- Listener local trên A nhận event.
- Listener trên B không tự nhận event chỉ vì B dùng cùng Redis hoặc database.

Một số repository có cơ chế gửi message qua Redis hoặc broker để node khác cũng nhận được event. Không được mặc định capability đó tồn tại cho mọi implementation.

Nếu ứng dụng cần đóng WebSocket hoặc thu hồi tài nguyên nằm trên node khác, kiểm thử riêng:

1. Khởi động hai application context A và B.
2. Đảm bảo hai context dùng cùng repository và cấu hình event.
3. Tạo session qua A.
4. Xóa session qua B.
5. Xác nhận event đến đúng listener/node theo guarantee đã công bố.
6. Kiểm tra duplicate, retry và node disconnect.

Nếu chỉ có local event, bài test phải ghi nhận phạm vi local. Nếu cần distributed event, bổ sung broker, outbox hoặc command routing; shared storage không thay thế event bus.

## 14. Event có thể trễ, lặp hoặc mất

Event pipeline có thể chịu các failure mode:

- Redis keyspace notification bị tắt hoặc listener mất kết nối.
- Cleanup task chạy theo lịch nên phát event trễ.
- Process dừng sau khi storage commit nhưng trước khi publish.
- Broker retry khiến consumer nhận duplicate.
- Node mất mạng trong lúc subscribe.
- Hai worker xử lý cùng một expiration candidate.

Test cần xác định guarantee thực tế:

| Guarantee | Cách kiểm thử |
| --- | --- |
| Best effort local | Xác nhận listener local nhận event trong điều kiện bình thường; không hứa durable delivery |
| At-least-once | Mô phỏng retry/duplicate và xác nhận consumer idempotent |
| Durable outbox | Crash/restart publisher và xác nhận outbox được gửi lại |
| Distributed broadcast | Hai node cùng nhận event theo topology được hỗ trợ |
| No event support | Xác nhận state/cleanup semantics; không đòi lifecycle event |

Không viết assertion exactly-once chỉ vì test chạy một lần không thấy duplicate. Exactly-once end-to-end cần bảo đảm xuyên storage, broker và consumer; thông thường consumer vẫn phải idempotent.

## 15. Kiểm tra event gắn đúng session

Trong môi trường test song song, có nhiều session được tạo và xóa cùng lúc. Chỉ kiểm tra số event tổng thể có thể khiến event của session A vô tình làm test session B pass.

Mỗi test nên:

- Tạo session ID riêng.
- Ghi một marker không nhạy cảm để tìm fixture khi cần.
- Lọc event theo session ID.
- Không dùng principal thật hoặc session ID cố định.
- Dọn fixture trong teardown.
- Dùng namespace test riêng nếu repository hỗ trợ.

Nếu event mang session snapshot, chỉ đọc trường cần thiết như ID hoặc marker. Không assert toàn bộ attribute map nếu repository không cam kết event giữ snapshot đầy đủ.

Event của một session không được làm listener xóa resource thuộc session khác. Với event broker, dùng event key hoặc partition key phù hợp để consumer định tuyến chính xác.

## 16. Kiểm thử event không được phát khi thao tác thất bại

Ngoài happy path, test failure path:

- Save session thất bại: không phát created event như thể session đã persist thành công, nếu contract quy định event sau persistence.
- Delete thất bại: không phát deleted event như thể trạng thái đã xóa.
- Cleanup transaction rollback: không phát expired event xác nhận một row đã xóa.
- Listener/broker lỗi: phân biệt lỗi publish với lỗi storage; không rollback session nếu storage đã commit trừ khi có transaction chung.

Để tạo lỗi, dùng test double ở tầng storage, fault proxy hoặc test database/Redis riêng. Không tắt Redis dùng chung hoặc gây lỗi trên môi trường ngoài test.

Nếu event được publish trước commit theo thiết kế, phải ghi rõ semantics và kiểm thử consumer có thể thấy trạng thái chưa commit hay không. Với event biểu thị trạng thái đã hoàn tất, publish sau commit hoặc dùng outbox thường dễ suy luận hơn.

## 17. Event listener phải idempotent

Listener có thể nhận event trùng hoặc event đến sau khi resource đã được dọn. Ví dụ, hai notification cùng báo một session hết hạn, hoặc logout xóa session trước khi WebSocket disconnect event đến.

Listener nên:

- Chấp nhận session/resource đã không còn tồn tại.
- Có thể xử lý cùng event nhiều lần mà không gây lỗi nghiệp vụ.
- Không xóa resource thuộc session khác.
- Dùng idempotency key nếu event đi qua broker.
- Ghi nhận lỗi cleanup để retry theo chính sách.
- Không giữ lock dài trong khi gọi dịch vụ ngoài.

Không dùng event listener làm nơi duy nhất thực hiện một side effect quan trọng mà không có retry hoặc reconciliation. Nếu event bị mất có thể gây rò rỉ resource, cần cleanup định kỳ hoặc outbox.

## 18. Không nhầm lifecycle event với audit nghiệp vụ

Lifecycle event trả lời “session đã được tạo/xóa/hết hạn theo repository”. Nó không nhất thiết trả lời:

- Ai yêu cầu xóa session?
- Vì sao session bị thu hồi?
- Người dùng tự logout hay admin revoke?
- Request nào gây thay đổi?
- Việc xóa có liên quan đổi mật khẩu, khóa tài khoản hay phát hiện gian lận?

Nếu cần audit, ghi một bản ghi nghiệp vụ riêng tại use case tương ứng, với actor, reason, timestamp và correlation ID. Event lifecycle có thể kích hoạt audit consumer, nhưng không nên suy ra actor/reason từ một event chỉ mang session.

Không đưa toàn bộ `SecurityContext`, access token, refresh token hoặc session attributes nhạy cảm vào event. Chỉ phát metadata tối thiểu mà consumer cần.

## 19. Test với Spring Test ApplicationEvents

Spring Test có hỗ trợ ghi nhận application events trong một số phiên bản:

```java
@SpringBootTest
@RecordApplicationEvents
class SessionEventTests {

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void recordsCreatedEvent() {
        // Tạo và persist session bằng repository thật.

        long count = applicationEvents
                .stream(SessionCreatedEvent.class)
                .count();

        assertThat(count).isGreaterThanOrEqualTo(1);
    }
}
```

Đây là mẫu khi phiên bản Spring Test hỗ trợ `@RecordApplicationEvents`. Cần lọc event theo session ID hoặc fixture marker để tránh test khác trong cùng context làm tăng count. Nếu event đến bất đồng bộ sau khi method test kết thúc, recorder có thể không phản ánh event theo cách mong muốn; khi đó dùng listener probe có timeout và đồng bộ lifecycle rõ ràng.

Với event distributed qua broker, `ApplicationEvents` chỉ ghi event được publish trong context đang được recorder theo dõi. Nó không chứng minh message đã đến node khác. Dùng integration test broker/consumer cho phạm vi đó.

## 20. Ma trận test theo repository

Không nên dùng một bộ assertion giống nhau cho mọi repository. Chọn test theo capability:

| Repository/configuration | Created | Deleted | Expired | Phần cần kiểm tra thêm |
| --- | --- | --- | --- | --- |
| Custom in-memory repository | Theo implementation | Theo implementation | Chỉ nếu có expiration detector | Clock và cleanup semantics |
| Redis repository có event support | Theo implementation | Theo implementation | Có thể phụ thuộc keyspace notification | Redis config, listener container, event delay |
| JDBC repository dùng batch cleanup | Theo implementation | Theo implementation | Có thể không phát per-session event | Cleanup SQL, transaction, outbox nếu cần |
| Custom repository có outbox | Theo outbox contract | Theo outbox contract | Theo expiration worker | Retry, duplicate, crash recovery |

Bảng này là khung phân tích, không phải tuyên bố mọi implementation cùng loại đều có đúng capability giống nhau. Xác minh API/version/config thực tế và ghi kết quả vào test suite.

## 21. Những lỗi kiểm thử thường gặp

- **Giả định mọi repository đều phát ba event:** abstraction repository không đồng nghĩa mọi implementation có cùng event publisher.
- **Chỉ kiểm tra event count:** event có thể thuộc session khác.
- **Không kiểm tra repository state:** event có thể được phát trước commit hoặc sai thao tác.
- **Dùng sleep cố định:** event async hoặc cleanup theo lịch có thể đến trễ hơn.
- **Nhầm local event với distributed event:** listener ở node khác không tự nhận application event.
- **Giả định Redis TTL phát event ngay lập tức:** expiration notification có thể trễ và phụ thuộc cấu hình.
- **Giả định JDBC batch delete phát event cho từng row:** câu lệnh xóa hàng loạt không tự tạo event nghiệp vụ.
- **Assert event khi repository không hỗ trợ:** test phản ánh giả định sai thay vì contract.
- **Không test failure path:** event có thể được phát dù save/delete rollback.
- **Không xử lý duplicate:** listener có thể chạy side effect nhiều lần.
- **Đưa session ID vào log:** làm lộ định danh nhạy cảm trong CI.
- **Dùng cùng session fixture giữa test song song:** event của test khác làm assertion pass sai.

## 22. Checklist trước khi merge

- [ ] Đã xác định implementation và phiên bản repository thực tế.
- [ ] Đã ghi rõ repository hỗ trợ event created, deleted và expired nào.
- [ ] Đã xác định trigger và thời điểm phát từng event.
- [ ] Test dùng storage thật dành riêng cho test khi cần xác minh Redis/JDBC.
- [ ] Event probe lọc theo đúng session ID.
- [ ] Created test xác nhận session đã persist và đọc lại được.
- [ ] Deleted test xác nhận session không còn đọc được sau delete.
- [ ] Expired test xác nhận session không còn hợp lệ sau deadline.
- [ ] Chỉ assert expired event khi repository thực sự cam kết hỗ trợ.
- [ ] Redis keyspace notifications/listener được cấu hình nếu implementation cần.
- [ ] JDBC cleanup và event publication được kiểm tra riêng.
- [ ] Event bất đồng bộ được chờ bằng timeout có giới hạn.
- [ ] Có test thao tác thất bại và rollback không phát event thành công giả.
- [ ] Có test duplicate/idempotency nếu delivery có thể lặp.
- [ ] Phân biệt local và distributed event; test đúng phạm vi cam kết.
- [ ] Không log session ID, cookie, token hoặc toàn bộ session attributes.

## 23. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- Vì sao không thể mặc định mọi `SessionRepository` phát `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent`?
- `SessionDestroyedEvent` giúp gom xử lý những trường hợp nào?
- Vì sao test event cần kiểm tra cả repository state và session ID trong event?
- Event created có thể phát ở thời điểm nào trong lifecycle tạo/lưu session?
- Vì sao Redis expiration notification có thể đến trễ hoặc không đến?
- Vì sao JDBC batch cleanup không đồng nghĩa có event expiration cho từng session?
- `ApplicationEventPublisher` khác distributed event bus như thế nào?
- Khi nào cần outbox để bảo đảm event không mất sau commit?
- Vì sao event listener phải idempotent?
- Làm thế nào test một repository không hỗ trợ expiration event mà vẫn xác nhận session hết hạn đúng?

Kiểm thử lifecycle event phải bắt đầu từ capability thật của repository. Hãy xác minh session state độc lập với event, tương quan event theo session ID, chờ event bất đồng bộ có timeout và kiểm tra riêng created, deleted, expired. Redis có thể cần keyspace notification; JDBC cleanup có thể chỉ xóa row mà không phát event cho từng session; local application event không tự phân phối tới node khác. Chỉ công bố và kiểm thử những guarantee mà implementation, cấu hình và hạ tầng thực sự cung cấp.
