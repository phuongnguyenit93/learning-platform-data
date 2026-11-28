# Đổi định danh và giữ nhất quán dữ liệu, chỉ mục liên quan

Custom SessionRepository có thể lưu session theo một định danh do client gửi lên, đồng thời duy trì các cấu trúc phụ để tìm phiên theo principal, thời hạn hoặc thuộc tính nghiệp vụ. Khi session ID thay đổi, ví dụ sau đăng nhập để chống session fixation, repository phải giữ nhất quán toàn bộ dữ liệu liên quan. Nếu chỉ đổi ID ở object hoặc cookie mà không cập nhật bản ghi và index, hệ thống có thể tạo phiên mồ côi, giữ tham chiếu đến ID cũ hoặc làm mất khả năng tìm phiên theo người dùng.

Spring Session cung cấp API chung để tạo, đọc, lưu và xóa session. Repository tùy chỉnh chịu trách nhiệm ánh xạ các thao tác đó vào store cụ thể và bảo toàn hợp đồng khi ID thay đổi. Bài học này trình bày cách thiết kế định danh, khóa nội bộ và secondary index; cách triển khai rotation; cách phối hợp thao tác nguyên tử với transaction; và cách kiểm thử nhiều node cùng cập nhật một phiên.

## 1. Phân biệt ba loại định danh

Một repository có thể có nhiều loại khóa. Không nên coi tất cả đều là session ID:

| Loại | Mục đích | Có thể thay đổi khi rotation? |
|---|---|---|
| Session ID công khai | Giá trị client gửi qua cookie/header để khôi phục phiên | Có |
| Khóa bản ghi nội bộ | Khóa chính của row/document dùng để lưu session | Không nhất thiết |
| Khóa chỉ mục phụ | Liên kết session với principal, expiry bucket hoặc thuộc tính tra cứu | Tùy cách thiết kế index |

Ví dụ với JDBC, bảng session tiêu chuẩn có PRIMARY_ID làm khóa chính nội bộ và SESSION_ID có unique index. Hai cột có vai trò khác nhau. Khi session ID thay đổi, có thể cập nhật SESSION_ID trong khi giữ nguyên PRIMARY_ID, các attribute row vẫn liên kết bằng khóa nội bộ. Với Redis, repository thường dùng session ID trong key; nếu index cũng chứa session ID, cần thay mọi tham chiếu phụ cùng lúc.

Một thiết kế custom repository nên quyết định sớm:

- Session ID có phải khóa chính của dữ liệu lưu trữ hay chỉ là khóa tra cứu?
- Các index phụ lưu session ID hay lưu khóa nội bộ ổn định?
- ID mới có thể va chạm với phiên đang tồn tại không?
- Có hỗ trợ truy vấn theo principal hoặc thuộc tính khác không?
- Một lần lưu session có thể ghi bao nhiêu store hoặc partition?

Nếu có thể, giữ một khóa nội bộ ổn định và coi session ID là bí danh có thể xoay vòng. Khi đó rotation không buộc phải đổi mọi quan hệ nội bộ. Tuy nhiên, các API trả kết quả theo session ID vẫn phải trả ID hiện hành, không trả bí danh cũ.

## 2. Hợp đồng SessionRepository và Session

API cơ bản của Spring Session là SessionRepository<S extends Session>. Các thao tác chính gồm:

- createSession(): tạo một session có thể được repository đó lưu.
- findById(id): đọc session theo ID; trả null nếu không tìm thấy hoặc session đã hết hạn theo hợp đồng implementation.
- save(session): lưu session được tạo hoặc đọc từ cùng repository.
- deleteById(id): xóa session theo ID; nếu không tồn tại thì không làm gì.

Session cung cấp getId() và changeSessionId(). Sau khi gọi changeSessionId(), getId() trả về ID mới. Thao tác này thay đổi định danh trên đối tượng Session; custom repository vẫn phải bảo đảm lần persist tiếp theo cập nhật đúng khóa lưu trữ và mọi index mà nó quản lý.

Không nên tạo một MapSession tùy ý rồi đưa vào repository nếu implementation cần theo dõi dirty attributes, original ID, version hoặc trạng thái xóa. createSession() và findById() nên trả về loại Session mà repository biết cách persist.

Ví dụ sử dụng API ở mức ứng dụng:

~~~java
Session session = repository.findById(currentId);
if (session == null) {
    throw new IllegalStateException("Session không còn hợp lệ");
}

String oldId = session.getId();
String newId = session.changeSessionId();

repository.save(session);
~~~

Ví dụ chỉ minh họa chuỗi thao tác. Trong ứng dụng web, nên để Servlet container, Spring Session filter và Spring Security thực hiện session ID rotation qua cơ chế chuẩn. Không tự cập nhật cookie hoặc gọi repository trực tiếp trong controller chỉ để thay thế session fixation protection.

## 3. Các index cần giữ nhất quán

Một repository có thể chỉ cần tra cứu theo session ID. Nếu cần tìm theo các tiêu chí khác, nó có thể triển khai FindByIndexNameSessionRepository hoặc một API tra cứu riêng.

Các index thường gặp:

| Index | Dữ liệu được lập chỉ mục | Mục đích |
|---|---|---|
| Session ID unique index | Session ID hiện hành | Tìm đúng một session |
| Principal index | Tên principal đã chuẩn hóa | Tìm các phiên của một người dùng |
| Expiration index | Thời điểm hoặc bucket hết hạn | Cleanup session quá hạn |
| Tenant/application index | Tenant hoặc ứng dụng sở hữu phiên | Phân vùng tra cứu nếu nghiệp vụ cần |
| Custom attribute index | Giá trị thuộc tính đã được duyệt | Tra cứu chức năng chuyên biệt |

FindByIndexNameSessionRepository mở rộng SessionRepository để tìm một Map có khóa là session ID và giá trị là Session theo index name/index value. Với principal, tên index chuẩn là PRINCIPAL_NAME_INDEX_NAME. Spring Session không biết mọi cơ chế xác thực tùy chỉnh của ứng dụng, nên ứng dụng phải bảo đảm principal name được đưa vào session/index; một số repository tích hợp có thể tự suy ra tên người dùng từ Spring Security context.

Không phải custom repository nào cũng bắt buộc phải triển khai index. Chỉ cung cấp FindByIndexNameSessionRepository khi implementation có thể duy trì kết quả tra cứu đúng. Một index không đầy đủ hoặc stale nguy hiểm hơn việc không công bố API index.

## 4. Chọn cách lưu secondary index

Có hai chiến lược thường dùng.

### 4.1. Index trỏ đến session ID

Ví dụ:

~~~text
principal:alice -> { sid-A, sid-B }
expiry:2026-11-26 -> { sid-A, sid-C }
session:sid-A -> session data
~~~

Ưu điểm là truy vấn trực tiếp và dễ triển khai. Nhược điểm là khi đổi sid-A thành sid-Z, repository phải thay sid-A bằng sid-Z trong mọi index liên quan. Nếu bỏ sót một index, tra cứu có thể trả ID cũ.

### 4.2. Index trỏ đến khóa nội bộ ổn định

Ví dụ:

~~~text
principal:alice -> { record-17, record-22 }
expiry:2026-11-26 -> { record-17, record-31 }
record:17 -> { currentSessionId: sid-Z, session data }
~~~

Khi rotation, repository chỉ cập nhật currentSessionId trong bản ghi record-17; index principal và expiry vẫn trỏ đến cùng khóa nội bộ. Khi API cần trả session ID, repository đọc bản ghi và lấy ID hiện hành.

Chiến lược này giảm số index phải thay đổi khi ID công khai được xoay. Đổi lại, mỗi lần tra cứu qua index có thể cần bước ánh xạ từ khóa nội bộ sang session ID và session data. Cần cân nhắc chi phí join/lookup, khả năng phân vùng và cách cleanup.

Không có một chiến lược tối ưu cho mọi store. Điều quan trọng là xác định rõ index chứa loại khóa nào và giữ hợp đồng đó nhất quán trong create, save, rotate, delete và expiration.

## 5. Rotation phải là một thay đổi nhất quán

Khi ID thay đổi từ oldId sang newId, repository cần bảo đảm:

1. ID mới không trùng với một session khác.
2. Dữ liệu session hiện tại được giữ nguyên, trừ các thay đổi hợp lệ của request.
3. Bản ghi chính có thể được tra cứu bằng ID mới.
4. ID cũ không còn tìm được session đã xác thực.
5. Principal index và các index phụ vẫn trỏ đến phiên hiện hành.
6. Expiration metadata và lịch cleanup vẫn gắn đúng session.
7. Attribute data không bị nhân đôi hoặc mất.
8. Cookie/header trả cho client chứa ID mới.

~~~mermaid
flowchart TD
    A[Đọc session bằng oldId] --> B[Session.changeSessionId()]
    B --> C[Kiểm tra newId chưa được dùng]
    C --> D{Định danh hợp lệ?}
    D -->|Không| E[Rollback và báo xung đột]
    D -->|Có| F[Cập nhật bản ghi session]
    F --> G[Cập nhật hoặc giữ nguyên khóa index]
    G --> H[Xóa alias/bản ghi oldId]
    H --> I[Commit transaction/atomic operation]
    I --> J[Trả cookie/header newId]
~~~

Không gửi ID mới cho client trước khi store đã commit. Nếu response mang ID mới nhưng repository chưa lưu xong, request kế tiếp có thể không tìm thấy session. Ngược lại, nếu store đã commit nhưng response mất, client có thể tiếp tục gửi ID cũ; ứng dụng cần xử lý theo chính sách an toàn, thường yêu cầu xác thực lại nếu không thể khôi phục mapping một cách tin cậy.

## 6. Theo dõi original ID và phiên bản bản ghi

Custom Session implementation nên theo dõi định danh đã được persist gần nhất. Khi getId() khác original ID, repository biết đây là rotation thay vì một session mới.

Một cấu trúc minh họa:

~~~java
final class TrackedSession {
    private final MapSession delegate;
    private String persistedId;
    private long version;

    String getId() {
        return this.delegate.getId();
    }

    String getPersistedId() {
        return this.persistedId;
    }

    long getVersion() {
        return this.version;
    }

    void markPersisted(String currentId, long newVersion) {
        this.persistedId = currentId;
        this.version = newVersion;
    }

    void changeSessionId() {
        this.delegate.changeSessionId();
    }
}
~~~

Đây là khung ý tưởng, không phải implementation đầy đủ của Session. Một custom Session phải delegate các method còn lại, quản lý attributes, thời gian, max inactive interval và dirty tracking. Khi repository đọc session, nó đặt persistedId và version theo dữ liệu đã lưu. Sau khi save thành công, nó cập nhật lại hai giá trị đó.

Version giúp phát hiện request cũ ghi sau request mới. Nếu chỉ theo dõi original ID mà không có version, hai request cùng đọc một ID có thể lần lượt save; request cũ có thể vô tình tạo lại bản ghi hoặc ghi đè dữ liệu sau rotation.

## 7. Cập nhật ID và index trong JDBC transaction

Với JDBC, transaction là cách tự nhiên để cập nhật bản ghi session và các index trong cùng database. Nếu dùng khóa nội bộ ổn định, rotation có thể cập nhật SESSION_ID trên row hiện tại:

~~~sql
UPDATE APP_SESSION
SET SESSION_ID = ?,
    VERSION = VERSION + 1
WHERE PRIMARY_ID = ?
  AND SESSION_ID = ?
  AND VERSION = ?;
~~~

Các tham số gồm ID mới, khóa nội bộ, ID cũ và version đã đọc. Điều kiện SESSION_ID cùng VERSION ngăn request cũ cập nhật row sau khi một request khác đã xoay ID hoặc ghi version mới.

Trong cùng transaction:

1. Khóa hoặc đọc row với version cần thiết.
2. Kiểm tra ID mới chưa tồn tại.
3. Cập nhật SESSION_ID có điều kiện.
4. Lưu delta của attributes và metadata.
5. Cập nhật các bảng index nếu chúng lưu session ID.
6. Commit.

Nếu index phụ dùng PRIMARY_ID ổn định, không cần thay giá trị trong index chỉ vì session ID đổi; nhưng mọi truy vấn index phải join/ánh xạ sang ID hiện hành. Nếu index phụ dùng session ID, phải xóa old ID và thêm new ID trong cùng transaction.

Unique constraint trên SESSION_ID là lớp bảo vệ cuối cùng chống trùng. Không chỉ chạy SELECT kiểm tra ID mới rồi mới UPDATE, vì hai transaction có thể cùng thấy ID chưa tồn tại. Bắt lỗi unique violation và xử lý như xung đột ID.

### 7.1. Ví dụ service ở mức khái niệm

~~~java
@Transactional
public long saveRotatedSession(TrackedSession session) {
    String oldId = session.getPersistedId();
    String newId = session.getId();

    SessionRow row = dao.findBySessionIdForUpdate(oldId)
        .orElseThrow(SessionNotFoundException::new);

    if (dao.existsBySessionId(newId)) {
        throw new SessionIdCollisionException();
    }

    int changed = dao.updateSessionId(
        row.primaryId(), oldId, newId, session.getVersion()
    );

    if (changed != 1) {
        throw new ConcurrentSessionUpdateException();
    }

    attributeDao.saveChanges(row.primaryId(), session);
    indexDao.replaceSessionIdReferences(row.primaryId(), oldId, newId);

    return session.getVersion() + 1;
}
~~~

Tên DAO và method là minh họa. Thứ tự khóa và câu SQL phải được thiết kế theo database thực tế. Nếu indexDao dùng khóa nội bộ ổn định, method replace có thể không cần thay các index; nếu index chứa session ID, cập nhật phải nằm trong cùng transaction. Sau khi lời gọi qua Spring proxy trả về thành công (nghĩa là transaction đã commit), caller mới gọi `session.markPersisted(newId, committedVersion)`. Nếu dùng transaction API khác, chỉ cập nhật trạng thái tracked object trong callback after-commit tương ứng.

Không đánh dấu session.markPersisted bên trong phần thân method transactional trước khi commit hoàn tất. Nếu commit thất bại, object trong memory không được coi là đã lưu với ID mới.

## 8. Cập nhật index trong Redis

Nếu custom repository dùng Redis và index lưu session ID, rotation phải phối hợp nhiều key:

~~~text
session:{sid-old}
principal:{alice} -> sid-old
expiry:{bucket} -> sid-old
custom-index:{tenant-7} -> sid-old
~~~

Một thao tác atomic có thể:

1. Xác nhận key cũ tồn tại và version còn đúng.
2. Xác nhận key mới chưa tồn tại.
3. Ghi session data dưới ID mới.
4. Thay old ID bằng new ID trong principal/custom indexes.
5. Cập nhật expiration index.
6. Xóa key cũ.
7. Tăng version.

Lua script hoặc transaction phù hợp có thể thực hiện nhóm lệnh trong Redis. Tuy nhiên, Redis Cluster yêu cầu các key tham gia một Lua script/transaction nhiều key phải tương thích slot; có thể dùng hash tag để đặt các key liên quan vào cùng slot. Nếu các index nằm ở nhiều slot, một script không thể tự biến chúng thành transaction phân tán.

Trong trường hợp không thể cập nhật mọi key atomically, cần chọn một thiết kế khác:

- Dùng khóa nội bộ ổn định làm giá trị trong secondary index.
- Dùng một bản ghi ánh xạ ID hiện hành làm nguồn có thẩm quyền.
- Dùng trạng thái pending/committed và cơ chế repair có thể chạy lại an toàn.
- Chấp nhận eventual consistency chỉ với index không ảnh hưởng quyết định xác thực hoặc quyền truy cập, và có quy trình reconciliation rõ ràng.

Không xóa key cũ trước khi dữ liệu mới và index mới đã được ghi thành công. Nếu xóa trước rồi lỗi, session có thể biến mất. Nếu ghi mới rồi không xóa cũ, phải bảo đảm old ID không còn được chấp nhận; một alias tạm chỉ được giữ nếu có chính sách rotation rõ ràng và không cho phép old ID tiếp tục truy cập ngoài ý muốn.

## 9. Principal index và thay đổi danh tính

Principal index thường dùng để tìm các phiên của một người dùng, ví dụ giới hạn concurrent sessions hoặc logout tất cả thiết bị. Giá trị index phải ổn định và được chuẩn hóa giống nhau trên mọi node.

Khi session ID thay đổi nhưng principal không đổi:

- Nếu index trỏ đến khóa nội bộ ổn định, giữ nguyên liên kết.
- Nếu index chứa session ID, thay old ID bằng new ID.

Khi principal thay đổi, ví dụ người dùng đăng xuất rồi đăng nhập tài khoản khác trong cùng session:

1. Xác định principal cũ từ dữ liệu đã persist.
2. Xác định principal mới từ trạng thái xác thực mới.
3. Xóa session khỏi index principal cũ.
4. Thêm session vào index principal mới.
5. Lưu SecurityContext/session attributes tương ứng.

Không chỉ thêm vào index mới mà quên xóa index cũ. Khi đó logout-all hoặc concurrent-session control có thể tìm phiên dưới cả hai principal.

Nếu repository triển khai FindByIndexNameSessionRepository, method findByIndexNameAndIndexValue phải trả map keyed bằng session ID hiện hành. Không trả old ID hoặc khóa nội bộ trong map key trừ khi đó chính là contract mà API công bố.

## 10. Expiration index và cleanup

Nhiều repository duy trì index theo thời gian hết hạn để tìm session cần cleanup. Khi rotation chỉ thay ID mà không đổi thời gian hết hạn, index expiry vẫn phải tham chiếu đúng session hiện hành.

Nếu expiry index lưu session ID:

- Xóa old ID khỏi bucket hoặc sorted set cũ.
- Thêm new ID với cùng expiration score.
- Nếu interval thay đổi trong cùng request, tính score mới và cập nhật đúng bucket.

Nếu expiry index lưu khóa nội bộ ổn định, rotation không cần thay phần tử index, nhưng cleanup phải đọc ID hiện hành trước khi xóa bản ghi. Không để cleanup xóa theo ID cũ rồi bỏ sót bản ghi mới.

Khi xóa session hoặc hết hạn, cần xóa tất cả index tương ứng. TTL của key chính không đảm bảo mọi secondary index tự được dọn nếu store không có cơ chế đồng bộ. Cần listener, scheduled cleanup hoặc tác vụ repair theo thiết kế.

## 11. Save delta để tránh ghi đè thay đổi đồng thời

Spring Session có thể persist HttpSession nhiều lần trong một request: lần đầu để session sẵn sàng khi client nhận ID, và lần nữa sau khi request hoàn tất vì attributes có thể tiếp tục thay đổi. Tài liệu Spring Session khuyến nghị custom repository theo dõi thay đổi và chỉ lưu delta khi có thể, thay vì ghi đè toàn bộ snapshot.

Điều này quan trọng khi nhiều request cùng thao tác một session:

- Request A thêm attribute cartHint.
- Request B cập nhật attribute locale.
- Cả hai cùng tải snapshot cũ.
- Nếu mỗi request ghi toàn bộ snapshot, lần ghi sau có thể xóa thay đổi của request trước.

Một tracked session nên ghi nhận:

- Attribute mới hoặc đã thay đổi.
- Attribute bị xóa.
- Thay đổi metadata như last accessed time và max inactive interval.
- Original ID và current ID.
- Version đã đọc.

Khi save, repository chỉ áp dụng thay đổi có chủ đích và kiểm tra version. Delta tracking giảm lost update do ghi toàn bộ object cũ, nhưng không tự giải quyết xung đột khi hai request cùng sửa một attribute. Với dữ liệu quan trọng, vẫn cần version, transaction hoặc invariant ở store nghiệp vụ.

## 12. Xử lý ID collision và retry

Generator có xác suất va chạm rất thấp nhưng repository vẫn phải xử lý collision đúng cách. Các tình huống:

- ID mới đã tồn tại do lỗi generator hoặc va chạm hiếm.
- Request retry sau timeout và không biết lần rotation trước đã commit chưa.
- Hai request cùng rotation một session từ cùng old ID.
- Node cũ ghi session với old ID sau khi node mới đã rotation.

Quy tắc:

- Không ghi đè một session khác khi new ID đã tồn tại.
- Dùng unique constraint hoặc atomic create-if-absent cho ID mới.
- Kiểm tra old ID và version trong cùng thao tác update.
- Nếu update không khớp, tải trạng thái mới và xử lý như conflict; không tự tạo lại old record.
- Retry chỉ khi thao tác idempotent và biết được trạng thái commit.
- Không gửi ID mới tới client trước khi store xác nhận commit.

Nếu client mất response sau commit, request sau có thể gửi old ID. Tùy kiến trúc, ứng dụng có thể từ chối và yêu cầu đăng nhập lại, hoặc giữ một alias rotation rất ngắn có kiểm soát. Alias phải bị giới hạn thời gian, không làm old ID có thể dùng như một credential đầy đủ sau khi rotation.

## 13. Tránh ghi đè từ request cũ sau rotation

Một race condition nguy hiểm:

1. Request A và B cùng tải session sid-old, version 10.
2. A đăng nhập và đổi ID thành sid-new, ghi version 11.
3. B kết thúc muộn và lưu snapshot version 10.
4. Nếu repository cho phép ghi mù, B có thể tạo lại sid-old hoặc ghi đè dữ liệu của A.

Giải pháp:

- Mỗi session có version tăng đơn điệu.
- Save yêu cầu version đã đọc phải khớp version trong store.
- Rotation cập nhật ID và version trong một thao tác có điều kiện.
- Khi conflict, request cũ không được ghi lại bản ghi đã bị thay thế.
- Nếu cần, dùng fencing token để ngăn worker cũ tiếp tục ghi sau khi lease/ownership thay đổi.

Không coi last-write-wins là chính sách mặc định an toàn cho session ID hoặc trạng thái xác thực. Nếu request cũ mang SecurityContext cũ, nó không được phép khôi phục một định danh đã bị thu hồi.

## 14. Quy trình migration khi thay cấu trúc định danh

Nếu thay cách tạo ID, định dạng ID hoặc schema/index của custom repository, hãy triển khai theo giai đoạn:

1. Xác định format cũ/mới và tất cả nơi lưu hoặc parse ID.
2. Thêm schema/index mới theo hướng tương thích ngược.
3. Triển khai code có thể đọc cả ID cũ và mới.
4. Chỉ sau khi mọi node đọc được cả hai, bật generator hoặc rotation format mới.
5. Theo dõi lookup miss, unique conflict và index mismatch.
6. Chờ session cũ hết hạn hoặc được thu hồi theo chính sách.
7. Chạy reconciliation để tìm index stale và bản ghi mồ côi.
8. Chỉ bỏ hỗ trợ format cũ khi không còn dữ liệu hợp lệ dùng format đó.

Nếu dùng index lưu session ID, có thể cần backfill index hoặc xây dựng lại từ primary records. Nếu index lưu khóa nội bộ ổn định, migration có thể đơn giản hơn, nhưng vẫn cần kiểm tra truy vấn trả đúng session ID hiện hành.

Không xóa dữ liệu cũ chỉ vì phiên bản ứng dụng mới đã được triển khai. Trong rolling deployment, node cũ có thể còn phục vụ request và session cũ vẫn có thể hợp lệ.

## 15. Reconciliation và tự sửa index

Secondary index nên được xem là dữ liệu có thể tái tạo từ session record nếu kiến trúc cho phép. Một job reconciliation có thể:

- Tìm index entry trỏ đến session ID không tồn tại.
- Tìm session còn hạn nhưng thiếu principal/expiry index.
- Tìm một session xuất hiện nhiều lần trong cùng index.
- So sánh principal/expiry metadata trong bản ghi chính với index.
- Sửa sai lệch theo batch có giới hạn.

Job phải idempotent và có checkpoint. Không quét hoặc sửa toàn bộ store trong một transaction dài. Ghi metric về số entry được kiểm tra, sửa, bỏ qua và lỗi; không ghi session ID hoặc principal nhạy cảm vào log nếu không cần thiết.

Nếu repository dùng khóa nội bộ ổn định, reconciliation có thể so sánh index key với metadata của bản ghi chính. Nếu index dùng session ID, cần xác nhận ID đó là current ID chứ không phải alias cũ.

## 16. Kiểm thử tính nhất quán khi đổi ID

Unit test cho Session.changeSessionId() chưa đủ. Cần kiểm tra cả dữ liệu chính, index và hành vi qua HTTP:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Rotation cơ bản | Tạo, lưu, đổi ID, lưu lại | ID mới tìm thấy; ID cũ không tìm thấy |
| Giữ attributes | Ghi nhiều attribute trước rotation | Tất cả attribute hợp lệ còn nguyên |
| Principal index | Tìm theo principal trước/sau rotation | Vẫn tìm thấy session bằng ID hiện hành |
| Principal đổi | Chuyển principal trong cùng session | Index cũ bị xóa, index mới được thêm |
| Expiry index | Rotation khi thời gian hết hạn giữ nguyên | Cleanup vẫn tìm đúng session |
| Xóa sau rotation | Delete bằng ID mới | Bản ghi và mọi index được dọn |
| ID collision | Ép generator trả ID đang tồn tại | Không ghi đè session khác |
| Hai request cùng rotation | Gửi song song cùng old ID/version | Một cập nhật thắng; request còn lại conflict |
| Request cũ save sau rotation | Cố tình trì hoãn save version cũ | Không tạo lại old ID hoặc ghi đè dữ liệu mới |
| Store lỗi giữa chừng | Làm transaction/script thất bại | Rollback hoặc repair đưa dữ liệu về trạng thái nhất quán |
| Multi-node | Rotate ở node A, đọc/xóa ở node B | B thấy ID mới và không chấp nhận ID cũ |
| Rolling deployment | Node cũ và mới cùng chạy | Cả hai đọc được format được hỗ trợ theo kế hoạch |

### 16.1. Kiểm thử repository thật

Với JDBC, chạy test trên cùng hệ quản trị production để kiểm tra transaction, unique constraint, row lock, index và rollback. Với Redis, kiểm tra Lua/MULTI, key slot trong Redis Cluster, TTL và hành vi khi một lệnh thất bại.

Mock store không chứng minh tính nguyên tử của database hoặc Redis. Nên tạo test tích hợp có barrier/latch để hai request bắt đầu đồng thời và xác minh invariant cuối cùng: chỉ có một ID hiện hành, không còn index stale và không mất attribute.

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ID mới dùng được nhưng tìm theo principal không thấy | Principal index vẫn trỏ old ID | Cập nhật index cùng transaction hoặc dùng khóa nội bộ ổn định |
| ID cũ vẫn khôi phục session | Không xóa alias/key cũ hoặc request cũ ghi lại | Xóa/thu hồi old ID và dùng version check |
| Session biến mất sau rotation | Xóa old record trước khi new record/index được commit | Ghi và xác nhận dữ liệu mới trước; transaction/atomic script |
| Thuộc tính bị mất | Ghi snapshot cũ hoặc save delta sai | Theo dõi dirty attributes, version và conflict |
| Logout-all bỏ sót phiên | Principal index không được cập nhật hoặc index stale | Sửa index lifecycle và reconciliation |
| Cleanup xóa nhầm hoặc bỏ sót phiên | Expiry index vẫn chứa old ID | Cập nhật expiry reference hoặc dùng internal key ổn định |
| Hai session bị gộp | ID collision và không có unique constraint | Enforce uniqueness tại store |
| Lỗi chỉ xảy ra trên một node | Node chạy code/schema/index format khác | Đồng bộ phiên bản và migration tương thích |
| Redis script lỗi trong cluster | Các key liên quan nằm ở slot khác nhau | Thiết kế hash tag hoặc chuyển index về khóa ổn định |
| Request cũ khôi phục ID đã thu hồi | Không kiểm tra version/fencing | Conditional save và từ chối stale write |

## 18. Nguyên tắc triển khai

- Phân biệt session ID client dùng, khóa bản ghi nội bộ và khóa secondary index.
- Dùng Session.changeSessionId() qua cơ chế Spring Session/Servlet chuẩn; không tự sửa cookie hoặc key nội bộ.
- Xác định rõ secondary index lưu session ID hay khóa nội bộ ổn định.
- Khi index lưu session ID, thay old ID bằng new ID trong cùng transaction hoặc atomic operation.
- Khi dùng khóa nội bộ ổn định, mọi API index phải ánh xạ về session ID hiện hành.
- Enforce uniqueness tại database/Redis; không chỉ kiểm tra trước bằng một lệnh đọc riêng.
- Theo dõi original ID và version để chặn stale save sau rotation.
- Lưu delta attributes và metadata; tránh ghi toàn bộ snapshot cũ lên dữ liệu mới.
- Cập nhật principal index, expiry index và custom index trong create/save/rotate/delete/expire.
- Chỉ phát cookie/header ID mới sau khi store commit thành công.
- Với nhiều store hoặc Redis Cluster, xác định rõ phạm vi atomicity và cách repair khi một bước thất bại.
- Kiểm thử rotation, collision, concurrent requests, rollback, cleanup, nhiều node và rolling deployment.
- Có reconciliation idempotent để phát hiện và sửa index stale hoặc bản ghi mồ côi.

Đổi session ID là một thay đổi định danh xuyên suốt repository. Custom implementation phải bảo đảm bản ghi chính, attributes, principal index, expiry index và mọi tham chiếu phụ cùng phản ánh ID hiện hành. Thiết kế khóa nội bộ ổn định, cập nhật nguyên tử, version check và reconciliation giúp rotation an toàn ngay cả khi nhiều request hoặc nhiều instance cùng thao tác một phiên.
