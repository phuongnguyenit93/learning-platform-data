# Bộ kiểm thử hợp đồng cho phiên, thời hạn, đồng thời và lỗi kho

Khi tự triển khai Spring Session repository hoặc thay đổi backend lưu trữ, một bài kiểm thử đơn lẻ cho thao tác lưu session là chưa đủ. Repository phải giữ đúng vòng đời của session, thời hạn không hoạt động, cập nhật thuộc tính, xóa phiên, hành vi khi nhiều request chạy đồng thời và cách báo lỗi khi Redis/JDBC hoặc serializer gặp sự cố.

Bộ kiểm thử hợp đồng (contract test suite) mô tả những hành vi mà mọi implementation của ứng dụng phải tuân theo. Cùng một bộ kiểm thử có thể chạy trên repository giả lập, Redis thật trong Testcontainers và JDBC database thật. Nhờ đó, thay backend hoặc tối ưu cách lưu trữ không làm thay đổi ngầm hành vi mà ứng dụng và Spring Security đang phụ thuộc.

## 1. Xác định hợp đồng cần kiểm thử

Spring Session cung cấp các abstraction chính:

- Session: dữ liệu và metadata của một phiên, gồm ID, thời điểm tạo, thời điểm truy cập gần nhất, thời hạn không hoạt động và attributes.
- SessionRepository<S extends Session>: tạo, tìm, lưu và xóa session.
- FindByIndexNameSessionRepository: mở rộng khả năng tra cứu session theo index, thường là principal name.
- Các implementation như repository Redis hoặc JDBC: hiện thực hợp đồng trên một kho dữ liệu cụ thể.

Các thao tác cơ bản của SessionRepository:

| API | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| createSession() | Tạo đối tượng session mới | ID hợp lệ, metadata ban đầu và timeout mặc định |
| save(session) | Lưu mới hoặc cập nhật session | Dữ liệu có thể đọc lại và được lưu theo chính sách |
| findById(id) | Tìm session theo ID | Trả session nếu còn hợp lệ; trả null nếu không tồn tại theo hợp đồng repository |
| deleteById(id) | Xóa session theo ID | Session không còn được tìm thấy sau khi thao tác hoàn tất |

Hợp đồng ứng dụng nên xác định rõ thêm:

- Session hết hạn có được xem như không tồn tại ngay khi đọc hay chỉ được dọn vật lý sau đó?
- Xóa một ID không tồn tại là thao tác idempotent hay báo lỗi?
- Khi hai bản sao session cùng được lưu, quy tắc ghi đè hoặc phát hiện xung đột là gì?
- Khi backend không truy cập được, repository ném lỗi nào và tầng web phản hồi ra sao?
- Serializer hỗ trợ những kiểu attribute nào?
- Có cần hỗ trợ tra cứu principal index, expiration event hoặc các tính năng bổ sung khác không?

Không phải mọi chi tiết vận hành đều được quy định giống nhau bởi mọi implementation. Hãy tách phần hợp đồng chung của SessionRepository khỏi các bảo đảm riêng mà repository tùy chỉnh của dự án cam kết.

## 2. Thiết kế bộ contract test dùng lại

Một cách tổ chức là viết abstract test suite. Mỗi implementation cung cấp factory tạo repository và cơ chế dọn dữ liệu sau test; các kiểm thử vòng đời chung được kế thừa.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.session.MapSession;
import org.springframework.session.SessionRepository;

abstract class SessionRepositoryContractTest {

    protected SessionRepository<MapSession> repository;

    protected abstract SessionRepository<MapSession> createRepository();

    protected abstract void clearRepositoryData();

    @BeforeEach
    void setUpRepository() {
        repository = createRepository();
    }

    @AfterEach
    void cleanUpRepository() {
        clearRepositoryData();
    }

    @Test
    void savesAndFindsSessionById() {
        MapSession session = repository.createSession();
        session.setAttribute("cart-reference", "cart-42");
        String sessionId = session.getId();

        repository.save(session);

        MapSession loaded = repository.findById(sessionId);
        org.assertj.core.api.Assertions.assertThat(loaded).isNotNull();
        org.assertj.core.api.Assertions.assertThat(loaded.getId())
            .isEqualTo(sessionId);
        org.assertj.core.api.Assertions.assertThat(
            loaded.getAttribute("cart-reference"))
            .isEqualTo("cart-42");
    }
}
~~~

Lớp kiểm thử cụ thể cho Redis hoặc JDBC chỉ cần khởi tạo đúng repository với namespace/schema riêng của test. Không dùng chung namespace với ứng dụng đang chạy hoặc test khác, vì dữ liệu còn sót lại có thể khiến test lúc pass lúc fail.

Nếu repository cần DataSource, RedisConnectionFactory hoặc serializer, factory phải dùng cùng cấu hình mà production sử dụng ở các phần quan trọng. Không kiểm thử một serializer đơn giản rồi triển khai production bằng serializer khác mà không có test tương ứng.

## 3. Kiểm thử tạo, lưu và đọc lại session

Kiểm thử đầu tiên xác nhận repository có thể tạo session, lưu thuộc tính và khôi phục đúng dữ liệu. Ví dụ trong contract suite ở trên đã thực hiện vòng create, save và find.

Đây là ví dụ dùng MapSession; generic type thực tế có thể khác nếu repository tùy chỉnh sử dụng session implementation riêng. Nếu createSession() trả về kiểu cụ thể khác, điều chỉnh factory và test type tương ứng.

Ngoài việc đọc lại một chuỗi đơn giản, hãy kiểm thử các kiểu attribute thực sự được ứng dụng lưu. Ví dụ: DTO có version, collection nhỏ hoặc SecurityContext nếu repository có trách nhiệm lưu context đó. Không đưa entity ORM lớn, request object hoặc object graph không ổn định vào session chỉ để làm test phong phú hơn.

Các assertion cơ bản:

- ID sau khi lưu vẫn là ID có thể tra cứu.
- Thuộc tính được giữ đúng tên và giá trị.
- Kiểu dữ liệu được giải mã đúng.
- Một session khác không bị ghi đè.
- Một ID ngẫu nhiên chưa từng lưu trả kết quả không tồn tại.

## 4. Kiểm thử cập nhật và xóa thuộc tính

Repository không chỉ lưu session lần đầu. Nó còn phải lưu thay đổi ở request sau:

~~~java
@Test
void updatesAndRemovesAttributes() {
    MapSession session = repository.createSession();
    session.setAttribute("step", "shipping");
    session.setAttribute("temporary-note", "draft");
    repository.save(session);

    MapSession loaded = repository.findById(session.getId());
    loaded.setAttribute("step", "payment");
    loaded.removeAttribute("temporary-note");
    repository.save(loaded);

    MapSession reloaded = repository.findById(session.getId());
    assertThat(reloaded).isNotNull();
    assertThat(reloaded.getAttribute("step")).isEqualTo("payment");
    assertThat(reloaded.getAttribute("temporary-note")).isNull();
}
~~~

Test thực tế nên xác nhận attribute bị xóa không xuất hiện lại sau khi repository lưu và tải lại.

Nếu implementation có SaveMode chỉ lưu attribute đã thay đổi, test nên bao gồm:

- Thêm attribute mới.
- Thay giá trị attribute hiện có.
- Xóa attribute.
- Đọc session mà không thay đổi gì.
- Cập nhật attribute trong một object mutable rồi lưu theo cách ứng dụng cam kết.

Không giả định mọi object mutable được phát hiện thay đổi tự động. Một số chế độ lưu có thể yêu cầu gọi setAttribute() lại để repository nhận biết thuộc tính cần cập nhật.

## 5. Kiểm thử metadata và timeout

Session có metadata quan trọng ngoài attributes:

- creationTime: thời điểm tạo.
- lastAccessedTime: lần truy cập gần nhất.
- maxInactiveInterval: thời gian không hoạt động tối đa.

Kiểm thử cần xác nhận các trường này được giữ qua vòng save/find:

~~~java
import java.time.Duration;
import java.time.Instant;

@Test
void persistsSessionMetadata() {
    MapSession session = repository.createSession();
    Instant accessedAt = Instant.now();
    Duration timeout = Duration.ofMinutes(12);

    session.setLastAccessedTime(accessedAt);
    session.setMaxInactiveInterval(timeout);
    repository.save(session);

    MapSession loaded = repository.findById(session.getId());
    assertThat(loaded).isNotNull();
    assertThat(loaded.getCreationTime()).isEqualTo(session.getCreationTime());
    assertThat(loaded.getLastAccessedTime()).isEqualTo(accessedAt);
    assertThat(loaded.getMaxInactiveInterval()).isEqualTo(timeout);
}
~~~

Đơn vị và kiểu trả về của timeout phụ thuộc phiên bản Spring Session; API hiện đại sử dụng Duration. Với phiên bản cũ hơn, hãy dùng chữ ký mà dependency của dự án cung cấp. Mục tiêu của test là xác nhận repository giữ đúng giá trị timeout, không ép mọi phiên bản dùng cùng cú pháp.

Không chỉ kiểm tra giá trị timeout trong object vừa tạo. Hãy đọc lại từ repository sau save để chứng minh metadata đã được lưu bền vững.

## 6. Kiểm thử expiration mà không phụ thuộc thời gian chính xác

Session hết hạn khi idle timeout đã trôi qua theo semantics của repository. Một kiểm thử có thể đặt timeout ngắn rồi đợi đến khi findById() không còn trả session:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;

@Test
void expiredSessionIsNoLongerReturned() {
    MapSession session = repository.createSession();
    session.setAttribute("owner", "user-17");
    session.setMaxInactiveInterval(Duration.ofMillis(150));
    String id = session.getId();
    repository.save(session);

    await()
        .pollInterval(Duration.ofMillis(25))
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(repository.findById(id)).isNull()
        );
}
~~~

Thời hạn test phải đủ ngắn để chạy nhanh nhưng không quá sát độ trễ của scheduler, Redis expiration notification hoặc database cleanup. Dùng một giới hạn chờ rõ ràng để test không treo vô hạn.

Phân biệt hết hạn logic với dọn vật lý:

- Repository không nên trả một session đã hết hạn như một session hợp lệ nếu hợp đồng ứng dụng yêu cầu hết hạn ngay khi đọc.
- Redis có thể xóa key theo TTL và có thể có key phụ trợ được dọn theo cơ chế riêng.
- JDBC có thể đánh dấu/kiểm tra expiration trước khi tác vụ cleanup xóa bản ghi vật lý.
- Sự kiện expiration có thể được phát bất đồng bộ hoặc phụ thuộc cấu hình.

Vì vậy, test nên xác nhận API nhìn thấy session như thế nào sau expiration. Nếu cần kiểm tra key Redis hoặc row JDBC đã bị xóa vật lý, viết test backend-specific riêng, không trộn nó với hợp đồng chung.

## 7. Kiểm thử cập nhật lastAccessedTime

Với Spring Session, lastAccessedTime thường được cập nhật khi request sử dụng session đi qua filter. Repository contract test có thể kiểm tra khả năng lưu giá trị thời gian được đặt:

~~~java
import java.time.Instant;

@Test
void savesUpdatedLastAccessedTime() {
    MapSession session = repository.createSession();
    repository.save(session);

    MapSession loaded = repository.findById(session.getId());
    Instant later = loaded.getLastAccessedTime().plusSeconds(30);
    loaded.setLastAccessedTime(later);
    repository.save(loaded);

    MapSession reloaded = repository.findById(session.getId());
    assertThat(reloaded.getLastAccessedTime()).isEqualTo(later);
}
~~~

Đây là kiểm thử repository lưu metadata. Một integration test khác nên gửi HTTP request qua SessionRepositoryFilter để xác nhận truy cập thực tế làm mới last accessed time theo cấu hình. Gọi findById() trực tiếp trong test không nhất thiết mô phỏng đầy đủ request lifecycle.

## 8. Kiểm thử delete và hành vi idempotent

Sau khi xóa một session, các lần đọc tiếp theo phải không còn tìm thấy phiên đó:

~~~java
@Test
void deletedSessionCannotBeFound() {
    MapSession session = repository.createSession();
    String id = session.getId();
    repository.save(session);

    repository.deleteById(id);

    assertThat(repository.findById(id)).isNull();
}
~~~

Nên xác định rõ hành vi khi xóa một ID không tồn tại. Nhiều implementation coi delete là thao tác idempotent và không làm gì nếu không có bản ghi, nhưng nếu repository tùy chỉnh có chính sách khác thì cần ghi rõ và kiểm thử theo chính sách đó.

Kiểm tra thêm:

- Xóa một session không làm ảnh hưởng session khác.
- Xóa hai lần không làm hỏng repository nếu hợp đồng yêu cầu idempotent.
- Xóa session đã hết hạn không tạo lại session.
- Logout hiện tại xóa session ở backend và resolver xử lý cookie/header.
- Xóa một session từ node A khiến node B không tải được session ở request tiếp theo.

## 9. Kiểm thử nhiều session độc lập

Một lỗi phổ biến của custom repository là dùng nhầm key, ghi đè record hoặc chia sẻ mutable state giữa hai session. Tạo hai session với attributes khác nhau rồi xác nhận chúng độc lập:

~~~java
@Test
void keepsDifferentSessionsIsolated() {
    MapSession first = repository.createSession();
    MapSession second = repository.createSession();
    first.setAttribute("owner", "user-A");
    second.setAttribute("owner", "user-B");

    repository.save(first);
    repository.save(second);

    assertThat(repository.findById(first.getId())
        .getAttribute("owner")).isEqualTo("user-A");
    assertThat(repository.findById(second.getId())
        .getAttribute("owner")).isEqualTo("user-B");
}
~~~

Đảm bảo hai ID khác nhau và việc cập nhật một session không thay đổi session còn lại. Với repository multi-tenant hoặc multi-application, mở rộng test để xác nhận namespace/schema và principal index không trộn dữ liệu giữa các phạm vi.

## 10. Kiểm thử đồng thời trên các session khác nhau

Nhiều request thường thao tác trên nhiều session khác nhau cùng lúc. Repository phải xử lý đồng thời mà không làm dữ liệu của session A ghi đè session B.

Một test concurrency cơ bản có thể:

1. Tạo một tập session với ID riêng.
2. Dùng ExecutorService chạy các thao tác save/find/delete song song.
3. Dùng latch hoặc barrier để các luồng bắt đầu gần như đồng thời.
4. Xác nhận mỗi ID chỉ đọc được dữ liệu của chính nó.
5. Xác nhận không có exception serialization hoặc lỗi cấu trúc dữ liệu.

Ví dụ phác thảo:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
CountDownLatch start = new CountDownLatch(1);

List<Future<?>> tasks = sessions.stream()
    .map(session -> pool.submit(() -> {
        start.await();
        repository.save(session);
        return null;
    }))
    .toList();

start.countDown();
for (Future<?> task : tasks) {
    task.get(5, TimeUnit.SECONDS);
}
pool.shutdown();
~~~

Đây là khung minh họa; cần tạo session fixture và dọn executor trong finally. Không dùng chung một mutable Session object giữa nhiều thread trừ khi implementation và API có bảo đảm thread-safety rõ ràng. Mỗi worker nên thao tác trên bản session riêng được tải từ repository.

## 11. Kiểm thử đồng thời trên cùng một session

Trường hợp khó hơn là hai request cùng tải một session, mỗi request sửa một thuộc tính rồi lưu:

~~~text
Request A: findById(S) -> state version 1
Request B: findById(S) -> state version 1
Request A: setAttribute("cart", cart-A); save
Request B: setAttribute("locale", "vi"); save
~~~

Nếu repository ghi đè toàn bộ bản ghi, lần save của B có thể làm mất cập nhật cart của A. Nếu repository lưu từng attribute hoặc dùng version/optimistic locking, kết quả có thể khác.

SessionRepository không tự định nghĩa một chính sách merge nghiệp vụ chung cho mọi custom repository. Do đó, hãy chọn và ghi rõ một trong các chính sách:

- Last write wins: bản lưu cuối cùng thay thế trạng thái trước; đơn giản nhưng có thể mất cập nhật.
- Attribute-level merge: thay đổi các attribute độc lập được hợp nhất; cần theo dõi chính xác attribute nào thay đổi.
- Optimistic locking: mỗi bản ghi có version; lưu với version cũ bị từ chối và caller phải tải lại/xử lý conflict.
- Serialization/locking: tuần tự hóa thao tác trên một session ID; tăng độ nhất quán nhưng có thể giảm throughput.

Không viết test yêu cầu mọi thay đổi từ mọi request phải được giữ nếu repository chưa cam kết merge hoặc locking. Test phải phản ánh chính sách được chọn và chứng minh implementation thực hiện đúng chính sách đó.

## 12. Kiểm thử save/delete race

Một tình huống bảo mật quan trọng là request đang chạy trong khi người dùng logout hoặc quản trị viên thu hồi session:

~~~text
Request A: findById(S)
Admin:     deleteById(S)
Request A: save(S)
~~~

Nếu save của A chạy sau delete, session có thể được tạo lại tùy cách repository xử lý. Không giả định deleteById() tự ngăn mọi request đã tải session từ trước ghi lại dữ liệu.

Hãy định nghĩa kết quả mong muốn:

- Nếu yêu cầu delete là thu hồi mạnh, một save từ bản session cũ không được làm session sống lại.
- Nếu repository không thể bảo đảm điều này một mình, cần version/revocation marker hoặc kiểm tra trạng thái tài khoản trước khi cho request hoàn tất.
- Nếu chấp nhận last-write-wins, phải hiểu rằng logout không phải thao tác thu hồi nguyên tử đối với request đang chạy.

Viết test race có latch để điều khiển thứ tự save/delete và xác nhận hành vi. Không dựa vào test ngẫu nhiên chạy nhiều lần; nó có thể không tái hiện được đúng interleaving gây lỗi.

## 13. Kiểm thử lỗi backend: phân biệt không tồn tại và không truy cập được

Một repository cần phân biệt hai tình huống:

- Session ID không tồn tại hoặc đã hết hạn: trả kết quả không tìm thấy theo hợp đồng, thường là null.
- Redis/database không truy cập được hoặc query timeout: phát sinh lỗi lưu trữ để ứng dụng có thể xử lý như lỗi hạ tầng.

Không chuyển lỗi kết nối thành null. Nếu Redis đang down mà findById() giả vờ session không tồn tại, ứng dụng có thể làm người dùng bị logout hàng loạt và che giấu sự cố backend. Tệ hơn, nếu hệ thống tạo session mới hoặc cho phép truy cập theo fallback không an toàn, có thể gây sai lệch bảo mật.

Các kiểm thử lỗi nên bao gồm:

- Backend unavailable khi findById().
- Backend unavailable khi save().
- Backend unavailable khi deleteById().
- Timeout khi đọc hoặc ghi.
- Pool JDBC hết connection.
- Redis authentication/TLS failure.
- Transaction rollback hoặc deadlock.
- Serialization/deserialization failure.

Với API đồng bộ SessionRepository, lỗi thường được ném dưới dạng runtime exception từ tầng data access/client. Không bắt mọi exception rồi trả về session rỗng. Nếu ứng dụng có lớp exception riêng, giữ nguyên cause để quan sát và phân loại.

## 14. Kiểm thử serialization và dữ liệu không hợp lệ

Redis/JDBC repository thường phải serialize session attributes. Một serializer contract nên xác định:

- Kiểu dữ liệu được hỗ trợ.
- Dữ liệu có thể đọc lại sau khi restart ứng dụng.
- Dữ liệu do phiên bản trước ghi có thể được phiên bản mới đọc trong rolling deployment.
- Attribute không hợp lệ hoặc không tương thích tạo lỗi có thể chẩn đoán.
- Lỗi serialize không để lại bản ghi session nửa vời hoặc index sai.

Test nên dùng DTO nhỏ, version rõ ràng và các kiểu ứng dụng thực sự cần. Nếu serializer chỉ hỗ trợ Serializable, test nên xác nhận các class cần lưu đáp ứng yêu cầu. Không dùng Java native serialization cho dữ liệu không tin cậy mà không đánh giá rủi ro deserialization.

Một test negative có thể cố ý lưu kiểu không được serializer hỗ trợ. Kết quả mong muốn là lỗi được phát hiện, không báo save thành công trong khi dữ liệu không thể đọc lại. Cũng cần kiểm tra trạng thái record trước đó có còn nhất quán sau lỗi hay không.

## 15. Kiểm thử transaction và tính nhất quán JDBC

Với JDBC repository, test cần bao gồm:

- Lưu session và attributes trong transaction theo cơ chế implementation.
- Rollback khi một phần thao tác ghi thất bại.
- Không để metadata session và attribute rows lệch nhau.
- Xóa session dọn dữ liệu liên quan theo schema.
- Cleanup job không xóa session còn hiệu lực.
- Index và query hoạt động ở quy mô dữ liệu dự kiến.
- Connection pool timeout được báo thành lỗi thay vì giả vờ session không tồn tại.

Nếu repository dùng transaction manager của Spring, xác nhận transaction boundary trong request có đúng như mong muốn. Không giả định transaction nghiệp vụ của controller tự động bao trùm mọi thao tác session filter; thứ tự filter và transaction có thể khác.

Với Redis, transaction semantics và atomicity khác JDBC. Nếu custom repository dùng nhiều command để ghi session, hãy xác định trạng thái có thể quan sát giữa các command và cách xử lý khi command giữa chừng thất bại.

## 16. Kiểm thử expiration event và cleanup

Nếu repository có phát SessionExpiredEvent hoặc SessionDeletedEvent, kiểm thử:

- Sự kiện tương ứng được phát trong đúng tình huống.
- Listener nhận được dữ liệu cần thiết mà không lộ credential.
- Xử lý listener idempotent vì event có thể được retry hoặc lặp trong một số kiến trúc.
- Cleanup phụ trợ không xóa nhầm session khác.
- Listener lỗi không làm trạng thái session chính bị hiểu sai.

Expiration event có thể phụ thuộc Redis keyspace notifications, scheduler, JDBC cleanup job hoặc cơ chế riêng của implementation. Không giả định mọi backend phát event cùng thời điểm hoặc cùng cách. Hợp đồng chung nên kiểm tra session không còn hợp lệ; test event nên là backend-specific.

## 17. Kiểm thử qua SessionRepositoryFilter và HTTP

Repository contract test xác nhận API lưu trữ. Nhưng ứng dụng thực tế còn phụ thuộc filter, cookie/header resolver và Spring Security. Cần một lớp integration test gửi HTTP request:

1. Gửi request tạo session hoặc đăng nhập.
2. Lấy cookie/header session ID từ response.
3. Gửi request tiếp theo với cùng định danh.
4. Xác nhận controller đọc được attribute/principal.
5. Gửi logout và xác nhận repository không còn session.
6. Gửi lại cookie/header cũ và xác nhận request được bảo vệ bị từ chối.
7. Nếu có nhiều instance, gửi request kế tiếp đến instance khác.

Dùng MockMvc hoặc WebTestClient tùy stack Servlet/WebFlux, nhưng kiểm thử repository và filter cần có wiring thật tương ứng. Một test gọi repository trực tiếp không chứng minh cookie được phát hoặc xóa đúng.

## 18. Chạy cùng contract suite trên nhiều backend

Một cấu trúc test có thể dùng lớp trừu tượng và các lớp con:

~~~java
class JdbcSessionRepositoryContractTest
        extends SessionRepositoryContractTest {
    // createRepository() trả repository JDBC dùng database test riêng.
    // clearRepositoryData() dọn bảng/session namespace của test.
}

class RedisSessionRepositoryContractTest
        extends SessionRepositoryContractTest {
    // createRepository() trả repository Redis dùng namespace test riêng.
    // clearRepositoryData() chỉ xóa key thuộc namespace của test.
}
~~~

Không để contract suite xóa toàn bộ Redis database hoặc toàn bộ bảng production. Mỗi test run cần namespace/schema riêng và cleanup có giới hạn. Khi chạy song song trên CI, mỗi worker phải có dữ liệu cô lập.

Nếu backend có semantics riêng, giữ contract chung ở phần bắt buộc và bổ sung test riêng cho:

- Redis TTL, keyspace notifications, failover và serialization.
- JDBC schema, transaction, cleanup query, index và connection pool.
- Custom repository versioning, lock hoặc merge policy.

## 19. Ma trận kiểm thử tối thiểu

| Nhóm | Ca kiểm thử bắt buộc |
| --- | --- |
| Lifecycle | Create, save, find, update, remove attribute, delete |
| Identity | ID duy nhất, session độc lập, lookup ID không tồn tại |
| Metadata | Creation time, last accessed time, max inactive interval |
| Expiration | Hết hạn logic, TTL/backend cleanup, timeout thay đổi |
| Concurrency | Nhiều session, nhiều writer cùng session, save/delete race |
| Storage errors | Connection failure, timeout, pool exhaustion, transaction/command failure |
| Serialization | Round-trip, compatibility, unsupported type, corrupt payload |
| Security | Logout, stale ID, principal/tenant isolation, không fail-open |
| Integration | Filter, cookie/header resolver, Spring Security, nhiều instance |
| Operations | Restart, failover, cleanup, metrics và log redaction |

## 20. Nguyên tắc triển khai bộ kiểm thử hợp đồng

- Dùng một contract suite chung cho mọi implementation của repository.
- Kiểm tra create/save/find/delete và round-trip attributes.
- Kiểm tra metadata, idle timeout và expiration với thời gian chờ có giới hạn.
- Tách kiểm thử hết hạn logic khỏi kiểm thử dọn vật lý key/row.
- Định nghĩa rõ concurrency policy; không mặc định SessionRepository cung cấp merge hoặc optimistic locking.
- Kiểm tra save/delete race nếu logout phải thu hồi mạnh.
- Phân biệt session không tồn tại với backend unavailable.
- Không nuốt lỗi Redis/JDBC hoặc biến lỗi kho thành kết quả không tìm thấy.
- Kiểm tra serializer và transaction/atomicity theo backend.
- Chạy test với Redis/JDBC thật trong môi trường cô lập.
- Bổ sung integration test qua filter, resolver và Spring Security.
- Dùng dữ liệu test nhỏ, ổn định, không chứa credential production.

Bộ kiểm thử hợp đồng giúp custom SessionRepository duy trì cùng hành vi qua các thay đổi backend và phiên bản. Các test lifecycle xác nhận session được lưu và khôi phục đúng; test expiration xác nhận timeout; test concurrency xác định chính sách cập nhật; test failure bảo đảm sự cố kho được báo rõ ràng. Khi kết hợp contract suite chung với test riêng cho Redis/JDBC và integration test qua HTTP filter, ứng dụng có thể thay đổi implementation mà vẫn kiểm soát được tính đúng đắn của session trong vận hành nhiều instance.
