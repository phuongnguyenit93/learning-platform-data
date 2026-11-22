# Kiểm thử quyền sở hữu thay đổi trong quá trình xử lý

## Mục tiêu và rủi ro cần phát hiện

Trong hệ thống Spring Security, người dùng có thể **có quyền** ở thời điểm kiểm tra nhưng **mất quyền** trước khi thao tác ghi dữ liệu diễn ra. Ví dụ: Alice yêu cầu sửa tài liệu của mình, request đã qua kiểm tra quyền; quản trị viên chuyển tài liệu sang Bob; request cũ của Alice vẫn tiếp tục lưu và ghi đè dữ liệu. Đây là lỗi **time-of-check/time-of-use (TOCTOU)** trong ủy quyền.

Bài này tập trung vào kiểm thử tình huống *chủ sở hữu hoặc chính sách đổi trong khi request đang chạy*, không chỉ kiểm thử việc request mới nhận 403 khi thiếu quyền. Sau bài học, cần biết: xác định bất biến cần bảo vệ; tổ chức hai transaction để tái hiện race có thứ tự; kiểm tra quyền tại điểm thực thi tác động; xác minh database, version và tác dụng phụ; nhận diện các giới hạn của `@PreAuthorize`, `@Transactional` và optimistic locking.

Giả sử tài liệu `Document` có `id`, `ownerId`, `body`, `status`, `version`; Alice chỉ được sửa khi tài liệu `ACTIVE`, hiện thuộc Alice và chính sách áp dụng cho phép. Client gửi `documentId`, nội dung mới, `expectedVersion`; **định danh Alice phải lấy từ principal đã xác thực trên server**, không tin `actorId` hoặc `ownerId` do client tự khai.

**Bất biến:** mỗi cập nhật được chấp nhận phải thỏa điều kiện quyền ở điểm áp dụng cập nhật theo hợp đồng nhất quán của hệ thống; một yêu cầu được cho phép trước đó không tự mang quyền vĩnh viễn. Nếu chính sách yêu cầu quyền còn hiệu lực tới commit, cơ chế transaction/khóa phải thực sự giữ bất biến tới commit. Mọi đường ghi liên quan (HTTP, chuyển chủ, batch, consumer) phải tuân cùng cơ chế.

## 1. Kịch bản TOCTOU cần tái hiện

1. **T0 — Kiểm tra:** tài liệu D thuộc Alice, `version=1`. Request sửa của Alice qua `@PreAuthorize` hoặc policy service, sau đó được giữ lại trước thao tác ghi.
2. **T1 — Chuyển chủ:** transaction khác đổi `ownerId` của D thành Bob, tăng `version` thành 2 và **commit**.
3. **T2 — Tiếp tục:** request cũ của Alice chạy phần cập nhật dữ liệu với dữ liệu đọc ở T0.
4. **Kỳ vọng:** không sửa `body`, không phát sự kiện “sửa thành công”, quyền chủ mới vẫn thuộc Bob; request bị từ chối hoặc trả xung đột theo contract API.

Nếu ở T2 hệ thống thực hiện `UPDATE document SET body = ? WHERE id = ?`, việc kiểm tra ở T0 không ngăn được thay đổi trái phép. Bài kiểm thử phải điều khiển thứ tự T0–T1–T2 và quan sát **điểm ghi thực tế**.

## 2. Vì sao kiểm tra quyền sớm chưa đủ

Spring Security 6 hỗ trợ `@EnableMethodSecurity`, `@PreAuthorize`, `PermissionEvaluator` và authorization service để chặn request theo principal, role, ACL hoặc chính sách nghiệp vụ. Chúng rất hữu ích, nhưng việc được cho phép ở đầu phương thức không tự khóa bản ghi hoặc tái kiểm tra mọi điều kiện khi database flush.

Ví dụ mã dễ gặp race (mã phác thảo, **không phải cách triển khai an toàn**):

```java
@PreAuthorize("@documentPolicy.isOwner(authentication, #documentId)")
@Transactional
public void editUnsafe(UUID documentId, String newBody) {
    Document document = repository.findById(documentId).orElseThrow();
    document.setBody(newBody); // Owner có thể thay đổi trong lúc xử lý.
}
```

Ngay cả khi phương thức gắn cả `@PreAuthorize` và `@Transactional`, không thể mặc định rằng quyền được bảo vệ tới commit: thứ tự advice, transaction isolation, lock, persistence context và câu SQL thực tế quyết định hành vi. Với `READ_COMMITTED`, một lần đọc quyền ở T0 không biến điều kiện đó thành bất biến ở T2. Với entity đã nạp, trạng thái trong bộ nhớ có thể cũ hơn database.

Hai chiến lược thường áp dụng tùy nghiệp vụ:

- **Cập nhật có điều kiện nguyên tử:** đưa điều kiện về actor, chủ sở hữu, trạng thái và phiên bản vào chính `WHERE` của `UPDATE`; kiểm tra số hàng bị tác động. Phù hợp với thay đổi có thể diễn đạt bằng một lệnh cập nhật.
- **Khóa có chủ đích trong transaction:** dùng `SELECT ... FOR UPDATE` hoặc JPA `PESSIMISTIC_WRITE` khi cần đọc–tính–ghi nhiều bước; đường chuyển quyền và sửa đều phải tuân cùng chiến lược khóa. Kiểm thử cả lock ordering, deadlock, timeout và retry.

Không có một annotation bảo vệ mọi chính sách động. Nếu quyền phụ thuộc bảng khác, group membership, ABAC hoặc trạng thái workflow, cần kiểm soát nhất quán những dữ liệu quyết định quyền đó, không chỉ `ownerId`.

## 3. Ví dụ Spring Data JPA: điều kiện quyền ngay tại điểm ghi

Các đoạn sau là **thành phần minh họa trong ứng dụng Spring Boot có sẵn** entity `Document`, enum `DocumentStatus` và security principal. Chúng không phải chương trình độc lập.

```java
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Document d
           set d.body = :body,
               d.version = d.version + 1
         where d.id = :documentId
           and d.ownerId = :actorId
           and d.status = :activeStatus
           and d.version = :expectedVersion
        """)
    int updateIfStillOwned(
            @Param("documentId") UUID documentId,
            @Param("actorId") UUID actorId,
            @Param("expectedVersion") long expectedVersion,
            @Param("activeStatus") DocumentStatus activeStatus,
            @Param("body") String body);
}
```

```java
@Service
public class DocumentEditService {
    private final DocumentRepository repository;

    public DocumentEditService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void edit(
            UUID authenticatedActorId,
            UUID documentId,
            long expectedVersion,
            String newBody) {

        int affected = repository.updateIfStillOwned(
                documentId, authenticatedActorId, expectedVersion,
                DocumentStatus.ACTIVE, newBody);

        if (affected != 1) {
            throw new AccessDeniedException("Resource unavailable or changed");
        }
    }
}
```

`authenticatedActorId` **chỉ được server tạo từ danh tính đã xác thực**. Nếu client có trường `ownerId`, trường đó không được dùng làm danh tính thực thi. Với JPA, cú pháp JPQL cần khớp tên thuộc tính entity; `Document.version` là trường số. Nếu entity dùng `@Version`, cần nhớ **bulk JPQL update không tự chạy kiểm tra/tăng version theo cơ chế cập nhật entity thông thường**: ví dụ trên thêm cả điều kiện version và phép tăng version tường minh. Đường chuyển chủ cũng phải tăng version và tuân cùng ràng buộc đồng thời.

`@Modifying` trả số hàng bị cập nhật: giá trị `0` có thể do tài liệu không tồn tại, sai chủ, bị khóa hoặc version cũ. API cần thống nhất cách trả 403, 404 hoặc 409 mà không tiết lộ sự tồn tại/chủ hiện tại cho người không có quyền. Ví dụ chọn một lỗi chung để minh họa, sản phẩm có thể ánh xạ khác theo policy đã định. `flushAutomatically` và `clearAutomatically` có tác động tới persistence context, nên transaction phải đủ hẹp và không tiếp tục dùng entity cache cũ sau bulk update.

Câu `UPDATE` có điều kiện trên **cùng hàng** kiểm soát race sửa/chuyển chủ hàng đó theo cơ chế khóa của database. Nó không mặc nhiên giải quyết chính sách lưu ở các bảng khác hoặc side effect bên ngoài database. Không nên đặt thao tác gửi email, ghi file hay publish sự kiện thành công **trước** khi xác nhận cập nhật đã thành công.

## 4. Java 17+: mô phỏng race có thứ tự và kết quả xác định

Ví dụ độc lập dùng `CountDownLatch` để request cũ dừng sau khi qua kiểm tra; `ConcurrentHashMap.computeIfPresent` cho phép thao tác cập nhật và chuyển quyền chạy nguyên tử theo cùng key. Đây là mô hình giúp hiểu phép thử, **không thay thế integration test với transaction thật**.

Lưu thành `OwnershipRaceDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class OwnershipRaceDemo {
    record Document(long id, String owner, String body, long version) {}

    private static final ConcurrentHashMap<Long, Document> STORE =
            new ConcurrentHashMap<>();

    static boolean canEdit(long id, String actor) {
        Document d = STORE.get(id);
        return d != null && d.owner().equals(actor);
    }

    static void transferOwner(long id, String newOwner) {
        STORE.computeIfPresent(id, (key, d) ->
                new Document(d.id(), newOwner, d.body(), d.version() + 1));
    }

    static boolean guardedUpdate(
            long id, String actor, long expectedVersion, String newBody) {
        AtomicBoolean changed = new AtomicBoolean(false);
        STORE.computeIfPresent(id, (key, d) -> {
            if (!d.owner().equals(actor) || d.version() != expectedVersion) {
                return d;
            }
            changed.set(true);
            return new Document(d.id(), d.owner(), newBody, d.version() + 1);
        });
        return changed.get();
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        STORE.put(7L, new Document(7L, "alice", "old", 1L));

        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch transferred = new CountDownLatch(1);

        Thread editingRequest = new Thread(() -> {
            boolean allowedAtT0 = canEdit(7L, "alice");
            checked.countDown();
            await(transferred);
            boolean updatedAtT2 = guardedUpdate(7L, "alice", 1L, "new");
            System.out.println("Precheck alice: " + allowedAtT0);
            System.out.println("Guarded update: " + updatedAtT2);
        });

        editingRequest.start();
        checked.await();             // T0: kiểm tra quyền đã diễn ra.
        transferOwner(7L, "bob");    // T1: chủ đã chuyển sang Bob.
        transferred.countDown();     // T2: request cũ tiếp tục.
        editingRequest.join();

        Document finalState = STORE.get(7L);
        System.out.println("Final: " + finalState.owner()
                + ", " + finalState.body()
                + ", v" + finalState.version());
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac OwnershipRaceDemo.java
java OwnershipRaceDemo
```

Kết quả stdout:

```text
Precheck alice: true
Guarded update: false
Final: bob, old, v2
```

Alice **đã có quyền ở T0**, nhưng bị chặn tại điểm ghi T2 sau khi owner đổi. Không dùng `Thread.sleep`: hai latch bảo đảm thứ tự độc lập tốc độ máy. Nếu thay `guardedUpdate` bằng ghi chỉ lọc theo `id`, kết quả cuối có thể thành `body=new` dù Alice đã mất quyền, tức đúng lỗi cần phát hiện.

## 5. Integration test có hai transaction thật

Một test đơn vị mock `updateIfStillOwned(...)` trả `0` chứng minh code xử lý lỗi, nhưng **không chứng minh** database xử lý đúng race. Nên dùng `@SpringBootTest` với database tương tự production (ví dụ PostgreSQL Testcontainers nếu hệ thống dùng PostgreSQL), repository thật và hai transaction độc lập, có commit quan sát được.

Kịch bản dựng test:

1. Tạo Alice, Bob và tài liệu D thuộc Alice, `body="old"`, `version=1`, `status=ACTIVE`. Commit dữ liệu chuẩn bị.
2. Luồng A gọi đường sửa của Alice; dùng test hook/barrier sau kiểm tra sơ bộ nhưng ngay trước thao tác cập nhật. Báo tín hiệu `checked`, rồi chờ `continueWrite`.
3. Luồng B chuyển chủ D sang Bob và tăng version trong transaction khác; đợi **commit thành công** mới mở `continueWrite` cho A.
4. Chờ cả hai luồng với timeout hữu hạn; nếu A dùng cập nhật có điều kiện thì số hàng sửa phải bằng `0` hoặc service phải ném lỗi tương ứng. Lỗi không được biến thành thành công im lặng.
5. Từ **transaction mới**, đọc lại database: `ownerId=Bob`, `body="old"`, version phản ánh chuyển chủ; không có outbox/event/audit “edit succeeded” của A. Kiểm tra status HTTP và message theo hợp đồng, không lộ thông tin Bob nếu Alice không có quyền.

Đặt điểm dừng **đúng ranh giới**: sau precheck, trước thao tác ghi. Khi dùng pessimistic lock, giao dịch B có thể buộc phải chờ A; không dựng barrier bắt B commit trước A nếu A đang giữ lock cản B, vì đó là deadlock do test tự tạo. Khi ấy xác minh tính tuần tự hóa và kết quả theo thứ tự khóa thực tế.

Một lưu ý Spring Test quan trọng: test method bao `@Transactional` mặc định rollback sau test có thể khiến dữ liệu chuẩn bị chưa commit **không hiện ra với thread khác**. Nên quản lý commit rõ bằng `TransactionTemplate` hoặc transaction service riêng và làm test không phụ thuộc rollback ẩn. Không chia sẻ EntityManager giữa các luồng; đóng executor; đặt timeout. Tránh dùng `sleep` để suy đoán thứ tự.

## 6. Ma trận ca kiểm thử

| Trường hợp | Tác động kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Chủ hợp lệ | Alice vẫn sở hữu, version đúng | Ghi đúng một lần; body và version cập nhật; event thành công đúng một lần |
| Không phải chủ ngay từ đầu | Bob sửa tài liệu của Alice | Từ chối; body, version và tác dụng phụ không đổi |
| Thu hồi giữa T0–T2 | Alice qua precheck; D chuyển sang Bob và commit | Alice không sửa được, Bob vẫn là owner, không có event thành công |
| Phiên bản cũ | Alice vẫn là owner nhưng version tăng bởi lần sửa khác | Request cũ không ghi đè nội dung mới; trả lỗi hợp đồng |
| Hai request sửa đồng thời | Cùng `expectedVersion` | Tối đa một request ghi thành công; không mất update |
| Chuyển A → B → A | Quyền quay về Alice sau hai lần chuyển | Version tăng qua mỗi lần; request giữ version cũ vẫn bị chặn |
| Bản ghi bị khóa/xóa mềm | `status` đổi khỏi ACTIVE trước ghi | Không ghi dù `ownerId` vẫn trùng |
| Lỗi trong transaction | Ghi 0 hàng hoặc rollback | Không có cập nhật một phần, outbox thành công hay gửi thông báo thành công |
| Các đường xử lý khác | Batch, consumer, scheduler hoặc admin thay đổi D | Không có đường nào bỏ qua ràng buộc quyền/phiên bản |
| Client giả danh chủ | Principal Bob nhưng gửi `actorId=Alice` | Actor lấy từ principal Bob; yêu cầu bị chặn |
| Cache quyền đã cũ | Quyền trong ACL/group bị thu hồi nhưng cache chưa cập nhật | Hành vi phù hợp hợp đồng hiệu lực quyền đã công bố; không tuyên bố thu hồi tức thời khi cache vẫn cho phép |

Test không chỉ `assertThrows` hoặc `verify(policy).check(...)`. Cần đọc **trạng thái sau commit** từ transaction mới, kiểm tra count của thao tác cập nhật, tác dụng phụ và response. Phải có test cho luồng hợp lệ để tránh “giải pháp” từ chối mọi thao tác.

Nếu dùng JWT chứa quyền, permission cache hoặc ACL cache, phải định nghĩa hiệu lực thu hồi (tức thời hay sau TTL). Test chấp nhận chỉ khi phù hợp hợp đồng đó. Nếu yêu cầu thu hồi tức thời, cần cơ chế đọc phiên bản/chính sách hiện hành ở nơi quyết định quyền; không tin claim stale vô thời hạn.

## 7. Tác dụng phụ và xử lý chạy lâu

Lưu database rollback **không hoàn tác** email đã gửi, file đã ghi, message đã publish hoặc API bên ngoài đã gọi. Một request có thể qua kiểm tra lúc T0, phát sự kiện thành công, rồi cập nhật database bị chặn ở T2; khi đó hệ thống vẫn sai. Với event thành công, cân nhắc **transactional outbox**: lưu kết quả nghiệp vụ cùng outbox trong một transaction và publish sau commit. Với I/O bên ngoài, cần thiết kế idempotency/bù trừ hoặc trạng thái trung gian theo nghiệp vụ; kiểm thử những khả năng này riêng.

Tác vụ bất đồng bộ/queue có hai thời điểm quyền: **quyền gửi job** và **quyền thực thi tác động khi worker chạy**. Cần quyết định rõ liệu quyền bị thu hồi khi job đang chờ có hủy job không; truyền actor ID đáng tin và dữ liệu phiên bản; kiểm tra lại tại điểm tác động theo contract; retry không được bỏ qua kiểm tra hay tạo tác dụng phụ trùng lặp. Việc worker có SecurityContext hay không không tự giải quyết quyền bị đổi.

Với xử lý nhiều tài nguyên, kiểm tra quyền một lần trước vòng lặp không đủ nếu từng tài nguyên có thể đổi chủ độc lập. Test giữa mỗi bước hoặc dùng transaction/khóa, câu cập nhật có điều kiện, batch guarded write tùy bất biến cần giữ. Nếu quyền phụ thuộc bảng liên quan, cần kiểm soát concurrency của **chính dữ liệu chính sách đó**.

## 8. Những lỗi kiểm thử dễ bỏ sót

**Chỉ kiểm tra request mới:** thử Alice sau khi Bob đã nhận quyền chỉ xác nhận chặn thông thường; không kiểm tra khoảng hở giữa T0 và T2.

**Tin annotation thay cho bằng chứng:** `@PreAuthorize` và `@Transactional` không mô tả đủ thứ tự locking/flush. Đối chiếu SQL, version và integration test.

**Hiểu sai `@Version`:** cập nhật entity bình thường và JPQL bulk update có cơ chế khác nhau. Bulk update phải tự mang điều kiện/tăng version nếu đó là chiến lược đã chọn; đường chuyển chủ cũng phải tuân thủ.

**Dùng mock/sleep:** mock bỏ qua isolation/lock của database, `sleep` làm test flakey. Dùng hai transaction thật, latch/barrier và commit rõ ràng.

**Đọc dữ liệu cũ:** persistence context hoặc cache giữ entity stale khiến assert sai. Dùng transaction mới/refresh sau commit.

**Chỉ assert mã lỗi:** vẫn có thể ghi file, gửi message hay thay một phần tài nguyên trước khi ném exception. Kiểm tra trạng thái và side effect.

**Bỏ qua đường batch, consumer hoặc admin:** một đường ghi theo `id` mà không bảo vệ quyền/phiên bản có thể phá bất biến của đường REST.

**Tiết lộ tài nguyên qua lỗi:** thông báo khác nhau cho “không tồn tại” và “thuộc Bob” có thể lộ thông tin; chọn phản hồi nhất quán theo chính sách sản phẩm.

## 9. Tiêu chí nghiệm thu

Kiểm thử đạt khi có bằng chứng lặp lại ổn định rằng: người có quyền sửa thành công; người không có quyền bị chặn; quyền chuyển đã commit giữa kiểm tra và ghi làm yêu cầu cũ không còn tác dụng; trạng thái database, version, mã lỗi và tác dụng phụ nhất quán; các đường ghi đều thực hiện cùng ràng buộc; và test đã tái hiện **thứ tự race thật** bằng đồng bộ xác định.

Câu hỏi tự đánh giá: nếu `@PreAuthorize` đã cho phép ở T0 nhưng `ownerId` đổi ở T1, **câu SQL, phiên bản hoặc khóa nào** bảo đảm thao tác T2 không sử dụng quyền hết hiệu lực? Nếu không thể trả lời bằng bằng chứng tại điểm ghi/commit và integration test, kiểm thử quyền sở hữu vẫn còn thiếu.
