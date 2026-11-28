# Vệ sinh dữ liệu hết hạn, chỉ mục phụ và dữ liệu thử nghiệm theo phạm vi

Spring Session lưu session trong Redis hoặc JDBC, thường bao gồm session ID, thời điểm truy cập cuối, thuộc tính như `SecurityContext` và dữ liệu principal. Khi session hết hạn hoặc bị logout, hệ thống cần làm sạch dữ liệu session và các cấu trúc phụ trợ như principal index, expiration index và session attributes. Đồng thời, kiểm thử cần dọn đúng dữ liệu do chính test tạo ra mà không xóa nhầm session của ứng dụng khác hoặc của người dùng thật.

Vệ sinh session có hai mục tiêu khác nhau: bảo đảm session hết hạn không còn được sử dụng và thu hồi dữ liệu vật lý/metadata sau khi không còn cần thiết. Repository phải từ chối session hết hạn ngay cả khi việc xóa vật lý hoặc event cleanup chưa hoàn tất. Vì vậy, không nên coi TTL, event listener, cleanup job và việc xóa key/row là một thao tác duy nhất.

## 1. Phân biệt hết hạn logic và xóa dữ liệu vật lý

Một session có thể ở nhiều trạng thái:

| Trạng thái | Ý nghĩa | Có được dùng để xác thực không? |
|---|---|---|
| Active | Còn trong thời hạn và repository trả về hợp lệ | Có, nếu authentication/authorization cũng hợp lệ |
| Expired | Đã vượt idle timeout hoặc thời hạn áp dụng | Không |
| Invalidated | Bị logout hoặc thu hồi chủ động | Không |
| Pending cleanup | Không còn hợp lệ nhưng key/row/index còn chờ dọn | Không |
| Orphan metadata | Index hoặc mapping còn sót sau khi session chính đã mất | Không được xem là session hợp lệ |

`SessionRepository.findById` phải không trả về session đã hết hạn theo contract của repository. Với Redis, session key hoặc metadata có thể còn tồn tại một khoảng thời gian để xử lý event và cleanup; điều đó không có nghĩa session còn hợp lệ. Với JDBC, job xóa row hết hạn có thể chạy theo lịch, nhưng request không nên dựa vào việc row đã bị xóa vật lý mới quyết định tính hợp lệ.

Hãy tách hai chỉ số vận hành: số session còn hợp lệ và số bản ghi/key chờ cleanup. Nếu gộp chúng, hệ thống có thể báo “người dùng còn đăng nhập” chỉ vì key chưa được dọn.

## 2. Các loại dữ liệu cần vệ sinh

Spring Session có thể tạo hoặc duy trì nhiều dữ liệu liên quan:

- Session record chứa creation time, last accessed time, max inactive interval và các attribute.
- `SPRING_SECURITY_CONTEXT` cùng principal/authority được lưu trong session.
- Principal index phục vụ tìm session theo tên người dùng.
- Expiration key hoặc expiration mapping dùng để kích hoạt cleanup.
- Session attribute rows trong JDBC.
- Event/listener state và các tài nguyên gắn với session, ví dụ WebSocket connection registry.
- Dữ liệu thử nghiệm do integration test tạo ra.

Khi xóa một session, cần xử lý cả dữ liệu chính và metadata phụ thuộc. Nếu chỉ xóa session hash/row mà bỏ index, truy vấn theo principal có thể trả về ID không còn tồn tại. Nếu chỉ xóa index, session record có thể vẫn tồn tại và tiếp tục được resolve bằng session ID.

## 3. RedisSessionRepository và RedisIndexedSessionRepository

Spring Session Data Redis có các repository với khả năng khác nhau:

| Repository | Khả năng |
|---|---|
| `RedisSessionRepository` | Lưu và tìm session theo ID |
| `RedisIndexedSessionRepository` | Bổ sung index để tìm session theo principal hoặc thuộc tính được hỗ trợ, cùng event cho delete/expiration |

Nếu ứng dụng cần `FindByIndexNameSessionRepository`, quản lý nhiều phiên theo principal hoặc nhận sự kiện vòng đời, cần dùng implementation indexed phù hợp. Trong cấu hình annotation, chọn indexed configuration theo phiên bản Spring Session đang dùng; một số phiên bản dùng `@EnableRedisIndexedHttpSession`, các cấu hình cũ hơn có thể dùng `@EnableRedisHttpSession(enableIndexingAndEvents = true)`.

Không bật indexed repository chỉ vì muốn “cleanup nhanh hơn”. Index bổ sung thêm dữ liệu cần được ghi, cập nhật và dọn. Chọn implementation theo nhu cầu truy vấn và event thực tế.

## 4. Redis expiration không đồng nghĩa key bị xóa đúng mili giây

Redis lưu TTL cho key, nhưng thời điểm key hết hạn được phát hiện và event được phát có thể trễ. Redis có thể kiểm tra key hết hạn khi truy cập và qua tác vụ nền; key không được truy cập có thể không phát expired event chính xác tại thời điểm TTL đạt 0.

Spring Session phải phối hợp việc hết hạn với yêu cầu phát `SessionExpiredEvent` hoặc `SessionDestroyedEvent` để dọn index và tài nguyên liên quan. Vì vậy, chỉ đặt TTL trên session hash không đủ cho toàn bộ lifecycle.

Với Redis indexed repository, Spring Session sử dụng expiration key riêng và theo dõi thời điểm hết hạn để cleanup task có thể truy cập các key đến hạn. Việc truy cập expiration key giúp Redis tự xác định TTL đã thực sự hết hay chưa và phát event tương ứng.

## 5. Vì sao session key có thể tồn tại lâu hơn idle timeout?

Trong cơ chế Redis của Spring Session, session data key có thể được đặt TTL muộn hơn thời điểm session hết hạn logic. Tài liệu Spring Session mô tả việc giữ session data thêm khoảng năm phút để dữ liệu vẫn có thể được đọc khi xử lý expiration event.

Một expiration key riêng được đặt TTL theo thời điểm hết hạn thực tế. Khi key này hết hạn hoặc bị xóa, keyspace notification giúp repository tra cứu session và phát sự kiện destruction. Session data được giữ lại trong khoảng grace để listener có thể nhận đầy đủ thông tin session trước khi cleanup.

Do đó:
- `TTL` của session data key không nhất thiết bằng idle timeout chính xác.
- `findById` vẫn phải loại session hết hạn logic.
- Không xóa session key ngay khi nhìn thấy expiration mapping cũ.
- Không coi key còn tồn tại là bằng chứng session còn hợp lệ.

Chi tiết khoảng grace và key layout phụ thuộc implementation/version; hãy dựa vào tài liệu của phiên bản đang triển khai, không viết script vận hành phụ thuộc cứng vào số phút hoặc tên key nội bộ.

## 6. Keyspace notifications và SessionDestroyedEvent

`RedisIndexedSessionRepository` sử dụng Redis keyspace notifications để nhận biết key bị xóa hoặc hết hạn và phát sự kiện Spring Session. Các sự kiện như `SessionDeletedEvent` và `SessionExpiredEvent` là các dạng `SessionDestroyedEvent`.

Sự kiện này có thể được dùng để:
- Xóa principal index và metadata liên quan.
- Đóng WebSocket connection gắn với session.
- Giải phóng tài nguyên ứng dụng theo lifecycle.
- Ghi nhận metric hoặc audit event phù hợp.

Với Redis, cấu hình notification thường cần hỗ trợ generic command events và expired events, ví dụ:

```text
notify-keyspace-events Egx
```

Trong môi trường Redis được quản lý hoặc bảo mật, ứng dụng có thể không được phép chạy `CONFIG SET`. Khi đó, hạ tầng cần cấu hình keyspace notification bên ngoài và ứng dụng có thể khai báo `ConfigureRedisAction.NO_OP` để Spring Session không cố thay đổi cấu hình Redis. Không cấp quyền CONFIG rộng cho ứng dụng chỉ để tự bật notification nếu quy trình vận hành yêu cầu cấu hình tập trung.

Keyspace notification là cơ chế event, không phải hàng đợi bền vững có thể replay tùy ý. Nếu listener ngừng hoạt động hoặc event bị mất, metadata có thể cần reconciliation.

## 7. Cleanup task cho Redis expiration mapping

Spring Session theo dõi các session theo thời điểm hết hạn, thường gom theo mốc phút, để cleanup task truy cập những expiration key có khả năng đã đến hạn. Khi truy cập một key có TTL hết, Redis thực hiện expiration và phát event nếu notification được bật.

Một điểm quan trọng: cleanup task không nên xóa mù session key chỉ vì expiration mapping cho rằng session đã hết hạn. Session có thể vừa được gia hạn và mapping cũ chưa được đồng bộ. Truy cập expiration key để Redis tự kiểm tra TTL giúp tránh xóa nhầm session còn hiệu lực.

Spring Session có thể cung cấp `RedisSessionExpirationStore` để quản lý tracking và cleanup. Nếu tùy chỉnh expiration store hoặc lịch cleanup, phải giữ semantics an toàn với việc session được gia hạn đồng thời.

Không tự viết cron `DEL` tất cả key có tên chứa `expires` hoặc xóa session dựa trên timestamp cũ. Cách đó có thể xóa nhầm phiên vừa được cập nhật.

## 8. Tùy chỉnh lịch cleanup Redis

Nếu mặc định không phù hợp với tải hoặc yêu cầu vận hành, có thể tùy chỉnh cleanup theo extension point của phiên bản đang dùng. `RedisIndexedSessionRepository` cung cấp API cấu hình cleanup cron trong các phiên bản hiện hành; API cụ thể và cách cấu hình qua Spring Boot có thể thay đổi theo release.

Ví dụ cấu hình repository trực tiếp:

```java
@Bean
SessionRepositoryCustomizer<RedisIndexedSessionRepository> redisSessionCustomizer() {
    return repository ->
            repository.setCleanupCron("0 * * * * *");
}
```

Ví dụ trên minh họa ý tưởng cấu hình lịch chạy mỗi phút; kiểm tra constructor, customizer và kiểu repository của phiên bản dự án. Nếu Boot auto-configuration đã tạo repository, dùng customizer được hỗ trợ thay vì tạo thêm một repository thứ hai.

Không tăng tần suất quá cao khi chưa đo tải. Cleanup quá dày có thể tạo nhiều lệnh Redis và event; cleanup quá thưa làm index/metadata tồn tại lâu hơn. Chọn lịch dựa trên session volume, expiration rate, event latency và khả năng của Redis.

## 9. Principal index trong Redis Indexed Repository

`RedisIndexedSessionRepository` duy trì index để tìm các session theo principal. `PrincipalNameIndexResolver` có thể đọc tên principal từ `SecurityContext` được lưu trong session. Repository lưu quan hệ giữa principal index và session ID, cùng metadata để biết index nào thuộc về session.

Về khái niệm, có hai hướng:
- Index theo principal chứa tập session ID của principal đó.
- Metadata theo session ghi nhận các index liên quan để có thể gỡ chúng khi session bị xóa hoặc thay đổi.

Điều này hỗ trợ `findByPrincipalName` và `FindByIndexNameSessionRepository`. Khi session logout hoặc hết hạn, các index liên quan cần được gỡ. Nếu event listener không nhận được delete/expire event, index có thể còn entry cũ.

Không dùng principal index như nguồn sự thật duy nhất về session đang hoạt động. Kết quả tra cứu cần được đối chiếu với session record và trạng thái hết hạn; index có thể tạm thời có entry mồ côi trong tình huống event/cluster lỗi.

## 10. Xử lý stale principal index và orphan entry

Một stale index entry là session ID còn trong index nhưng session record không còn hoặc không còn hợp lệ. Một orphan session record là session còn tồn tại nhưng index cần thiết đã mất. Hai trường hợp có cách xử lý khác nhau.

Quy trình reconciliation an toàn:
1. Chọn một namespace hoặc tenant cụ thể.
2. Lấy candidate session ID từ index bằng API repository phù hợp.
3. Gọi `findById` để xác minh session còn tồn tại và hợp lệ.
4. Ghi nhận candidate không còn session.
5. Ưu tiên API repository hoặc cleanup mechanism được hỗ trợ để gỡ metadata.
6. Nếu cần sửa cấu trúc nội bộ, thực hiện bằng công cụ/version-aware migration có dry-run và backup.
7. Giới hạn batch, tốc độ và thời gian chạy.
8. Đối chiếu số lượng trước/sau và kiểm tra không ảnh hưởng principal khác.

Không xóa toàn bộ index set chỉ vì một số member không tìm thấy session. Có thể có session hợp lệ được ghi đồng thời trong lúc reconciliation. Dùng API public và kiểm tra lại trạng thái ngay trước thao tác sửa.

## 11. Redis Cluster và sự kiện phân tán

Với Redis Cluster, cần đặc biệt kiểm tra cách repository subscribe keyspace events. Tài liệu Spring Session cảnh báo một số cấu hình `RedisIndexedSessionRepository` chỉ subscribe event từ một node Redis được chọn; event xảy ra ở node khác có thể khiến một số session index không được cleanup.

Hệ quả có thể là:
- Principal index chứa session ID cũ.
- SessionDeletedEvent/SessionExpiredEvent không được xử lý trên node ứng dụng mong đợi.
- WebSocket hoặc tài nguyên liên quan chưa được đóng kịp thời.
- Số lượng metadata tăng dù session hợp lệ không tăng.

Không suy ra rằng dùng Redis Cluster là mọi keyspace event tự động được broadcast đầy đủ đến tất cả subscriber. Kiểm tra topology, subscription behavior của Spring Data Redis và phiên bản Spring Session. Với yêu cầu index cleanup nghiêm ngặt, cần monitoring và reconciliation có phạm vi thay vì phụ thuộc duy nhất vào event.

## 12. JDBC cleanup job cho session hết hạn

Spring Session JDBC lưu session và attributes trong các bảng session. `JdbcIndexedSessionRepository` có cleanup job định kỳ xóa session đã hết hạn cùng các session attributes liên quan. Tài liệu hiện hành mô tả lịch mặc định chạy mỗi phút.

Có thể tùy chỉnh lịch bằng `cleanupCron` trên `@EnableJdbcHttpSession` hoặc property Spring Boot tương ứng, ví dụ:

```yaml
spring:
  session:
    jdbc:
      cleanup-cron: "0 0 * * * *"
```

Ví dụ trên đổi cleanup sang chạy đầu mỗi giờ; đây chỉ là ví dụ cấu hình, không phải khuyến nghị chung. Lịch quá thưa có thể khiến dữ liệu hết hạn tồn tại lâu hơn, trong khi lịch quá dày làm tăng tải database.

Nếu cần tắt job mặc định, phải có cơ chế cleanup thay thế được giám sát và có trách nhiệm rõ ràng. Không tắt cleanup chỉ để giảm một truy vấn định kỳ rồi quên lập lịch dọn session/attributes.

## 13. SQL index và principal lookup trong JDBC

Trong JDBC, cần phân biệt hai nghĩa của “index”:
- Index logic của repository để tìm session theo principal, thường dựa vào cột principal trong bảng session.
- SQL index do database quản lý để tăng tốc truy vấn theo expiry time, principal hoặc quan hệ session/attribute.

Khi xóa session row và attribute rows bằng câu lệnh SQL đúng, database tự cập nhật các B-tree index liên quan trong transaction. Không có thao tác “xóa entry trong index” thủ công như cách dọn Redis set.

Schema Spring Session JDBC có các index phục vụ lookup và cleanup. Nếu custom schema/table/query, cần giữ các index phù hợp với query thực tế. Thiếu index trên expiry hoặc principal có thể làm cleanup và tìm session chậm khi bảng lớn.

Sau khi xóa lượng dữ liệu lớn, database engine có thể cần thống kê hoặc bảo trì vật lý như `VACUUM` ở PostgreSQL hoặc cơ chế tương ứng ở DBMS khác. Đây là công việc quản trị database, không phải lệnh xóa session của Spring Session. Không chạy VACUUM/OPTIMIZE tùy tiện trong request path.

## 14. Tùy chỉnh JDBC cleanup query

Spring Session JDBC cho phép tùy chỉnh câu lệnh xóa session hết hạn qua `JdbcIndexedSessionRepository` và `SessionRepositoryCustomizer` trong các phiên bản hỗ trợ.

Ví dụ khung:

```java
@Bean
SessionRepositoryCustomizer<JdbcIndexedSessionRepository> jdbcSessionCustomizer() {
    return repository -> repository.setDeleteSessionsByExpiryTimeQuery("""
        DELETE FROM %TABLE_NAME%
        WHERE EXPIRY_TIME < ?
        """);
}
```

Đây là ví dụ đơn giản; query thực tế phải tuân theo schema, placeholder và dialect mà repository mong đợi. Nếu thêm điều kiện tenant hoặc partition, cần bảo đảm session hết hạn ở mọi partition được dọn và attributes liên quan không bị bỏ sót.

Không sửa query mặc định nếu chưa đo được vấn đề. Câu lệnh custom có thể làm mất khả năng dùng index hoặc xóa thiếu attribute rows. Hãy chạy explain plan trên database test và kiểm tra số row bị xóa cùng referential integrity.

## 15. Không xóa session bằng SQL hoặc Redis command tùy tiện

Khi cần kết thúc session chủ động, ưu tiên API `SessionRepository.deleteById` hoặc cơ chế logout/invalidating session tương ứng. Repository có thể xử lý index, event và metadata liên quan.

Ví dụ:

```java
sessionRepository.deleteById(sessionId);
```

Không nên:
- `DEL` một session hash Redis mà không xử lý expiration/index keys.
- `FLUSHDB` hoặc `FLUSHALL` trên Redis dùng chung.
- `DELETE FROM SPRING_SESSION` mà không xử lý attribute rows và phạm vi môi trường.
- Xóa Redis set principal index theo phỏng đoán.
- Xóa session theo pattern rộng mà không kiểm tra namespace.
- Chạy `KEYS *` trên Redis production để tìm dữ liệu cần dọn.

Các lệnh trực tiếp có thể bỏ qua event, để lại metadata hoặc xóa nhầm dữ liệu ứng dụng khác. Nếu cần migration/corruption repair ở tầng lưu trữ, phải có script riêng, review, dry-run, backup, giới hạn phạm vi và kế hoạch rollback.

## 16. Dữ liệu thử nghiệm phải có namespace riêng

Test data nên được cô lập trước khi cần cleanup. Với Redis, dùng namespace riêng theo test suite hoặc test run, ví dụ:

```yaml
spring:
  session:
    redis:
      namespace: it:build-4821:spring-session
```

Với JDBC, dùng database/schema riêng cho test hoặc table prefix riêng nếu cấu hình hỗ trợ. Testcontainers tạo datastore tạm thời là lựa chọn tốt vì container và dữ liệu có thể bị hủy sau test run.

Không dùng namespace production trong integration test. Không dùng chung namespace giữa nhiều pipeline CI nếu chúng có thể xóa dữ liệu của nhau. Tên namespace nên chứa build/run identifier do test harness tạo, không chứa credential hoặc thông tin cá nhân.

## 17. Cleanup test data bằng ID đã tạo

Cách an toàn nhất là test lưu session ID ngay khi tạo và dọn đúng các ID đó:

```java
List<String> createdSessionIds = new CopyOnWriteArrayList<>();

@AfterEach
void cleanupSessions() {
    createdSessionIds.forEach(sessionRepository::deleteById);
    createdSessionIds.clear();
}
```

Ví dụ minh họa cho test repository đồng bộ. Với reactive repository, cleanup cần nối các `Mono<Void>` vào chain và verify hoàn tất; không gọi `subscribe()` fire-and-forget trong `@AfterEach` rồi kết thúc test trước khi cleanup chạy.

Nếu test thất bại trước khi ghi ID vào danh sách, có thể còn fixture. Vì vậy, kết hợp cleanup tường minh với namespace riêng và TTL an toàn cho dữ liệu test. TTL là lớp bảo vệ cuối, không thay cleanup chính.

## 18. Không dùng FLUSHDB hoặc DELETE toàn bảng trong test dùng chung

Một test có thể pass riêng nhưng phá hỏng test khác nếu cleanup toàn kho:
- `FLUSHDB` xóa mọi key trong Redis database đang chọn.
- `FLUSHALL` xóa dữ liệu trên mọi database của Redis instance.
- `DELETE FROM SPRING_SESSION` có thể xóa session của mọi ứng dụng dùng cùng bảng.
- Xóa toàn bộ principal index có thể làm mất khả năng tra cứu session còn hoạt động.

Chỉ dùng lệnh hủy toàn bộ dữ liệu khi datastore là container/instance chuyên biệt dành riêng cho đúng test và vòng đời container bảo đảm không có ứng dụng khác dùng chung. Với Redis/JDBC phát triển dùng chung hoặc môi trường tích hợp, luôn giới hạn theo namespace, schema, test run hoặc session ID.

Không coi tên database Redis khác nhau là ranh giới bảo mật nếu credential có quyền truy cập database khác hoặc cấu hình Redis Cluster không hỗ trợ database index như standalone.

## 19. SCAN và cleanup theo prefix

Khi phải kiểm kê key Redis trong một namespace test, dùng `SCAN` theo prefix thay vì `KEYS *`:

```text
SCAN 0 MATCH it:build-4821:spring-session:* COUNT 500
```

`SCAN` trả kết quả theo từng trang và có thể trả trùng key giữa các lần gọi; script cần tiếp tục cho đến cursor `0` và xử lý idempotent. `COUNT` là gợi ý số lượng, không phải giới hạn tuyệt đối.

Tuy nhiên, prefix scan chỉ nên dùng để kiểm kê hoặc dọn namespace test do chính test sở hữu. Với key nội bộ của Spring Session, ưu tiên `SessionRepository` để xóa session và metadata đúng cách. Nếu script cần xóa key nội bộ, phải hiểu đầy đủ cấu trúc của phiên bản repository, hỗ trợ Redis Cluster bằng cách scan từng primary và có dry-run.

Không dùng pattern prefix chung như `spring:session:*` trên Redis dùng chung giữa nhiều ứng dụng.

## 20. Dọn JDBC test data theo session ID hoặc schema riêng

Với JDBC, lựa chọn an toàn:
- Dùng database container riêng cho test suite.
- Hoặc tạo schema riêng theo test run.
- Hoặc dùng table prefix riêng được repository hỗ trợ.
- Ghi nhận session ID do test tạo.
- Xóa qua `SessionRepository.deleteById` khi test hoàn tất.
- Nếu cần SQL cleanup, ràng buộc chính xác theo session ID hoặc test schema đã cô lập.

Không thêm một cột test marker vào schema production chỉ để tiện cleanup nếu không có thiết kế migration và query rõ ràng. Không dùng principal test chung làm tiêu chí xóa nếu các test khác hoặc môi trường dùng cùng principal đó.

Nếu dùng transaction rollback để dọn, xác nhận Spring Session JDBC repository tham gia đúng transaction manager và transaction boundary. Không giả định mọi session write tự động rollback cùng transaction nghiệp vụ của test.

## 21. Dọn test data khi test chạy song song

Test parallel cần isolation rõ ràng:
1. Mỗi test run có namespace hoặc schema riêng.
2. Mỗi test tạo ID session riêng.
3. Cleanup chỉ xóa ID hoặc namespace do test sở hữu.
4. Không chia sẻ cookie jar giữa test.
5. Không dùng cùng principal fixture nếu test có thể xóa session của test khác.
6. Không chạy cleanup toàn DB trong `@AfterAll` trên datastore dùng chung.
7. Có TTL dự phòng cho fixture bị bỏ lại khi JVM bị kill.
8. Ghi nhận số fixture còn lại sau suite để phát hiện rò rỉ.

Một cleanup task chạy đồng thời với test cũng có thể xóa session nếu TTL test quá ngắn. Hãy dùng TTL đủ dài cho thời lượng test và chủ động xóa khi hoàn tất.

## 22. Reconciliation định kỳ cho dữ liệu mồ côi

Nếu event có thể bị mất hoặc index có thể stale, vận hành có thể cần reconciliation. Quy trình nên:
- Chọn phạm vi namespace/schema cụ thể.
- Lấy candidate theo batch.
- Xác minh session chính qua repository.
- Xác định index/member nào thực sự mồ côi.
- Dùng API hoặc cơ chế cleanup có hiểu biết về phiên bản.
- Giới hạn tốc độ và số lượng mỗi vòng.
- Ghi metric về candidate, deleted, skipped và error.
- Có dry-run và log kiểm toán.
- Không chạy cùng lúc nhiều bản reconciliation không có phối hợp nếu chúng có thể tranh chấp.

Reconciliation là biện pháp sửa lệch metadata, không thay thế TTL và cleanup job thường xuyên. Với volume lớn, cân nhắc Spring Batch hoặc job vận hành riêng có checkpoint, retry và backpressure thay vì một vòng lặp không giới hạn trong application startup.

## 23. Nhiều application instance và cleanup job

Trong cụm nhiều instance, mỗi application context có thể đăng ký scheduler hoặc listener tùy cấu hình repository. Không giả định cleanup task tự động chỉ chạy một lần trên toàn cluster.

Nếu nhiều node cùng chạy cleanup:
- Xác minh công việc có idempotent không.
- Đo số lệnh Redis/SQL phát sinh khi scale node.
- Tránh chạy reconciliation nặng đồng thời trên mọi instance.
- Dùng scheduler leader hoặc job coordinator nếu cần chỉ một worker xử lý batch.
- Bảo đảm mọi node vẫn nhận session events cần thiết nếu listener được thiết kế theo node.

Không tắt listener ở các node chỉ để tránh xử lý event lặp nếu mỗi node cần nhận sự kiện để đóng WebSocket hoặc dọn local resource. Phân biệt event fan-out tới từng node với cleanup batch toàn cục.

## 24. Dữ liệu hết hạn, event và audit không phải một thứ

`SessionExpiredEvent` hoặc `SessionDeletedEvent` phục vụ lifecycle và cleanup. Không nên dùng chúng như audit log bền vững:
- Event có thể đến trễ.
- Listener có thể tạm dừng hoặc lỗi.
- Pub/sub event có thể không replay sau khi subscriber offline.
- Cleanup job có thể xóa vật lý sau khi event đã được xử lý hoặc ngược lại.

Nếu cần audit đăng nhập/logout hoặc bằng chứng tuân thủ, ghi sự kiện vào hệ thống audit bền vững với retention riêng. Không giữ session record hết hạn mãi chỉ để làm audit; session chứa dữ liệu xác thực và nên được xóa theo chính sách retention.

## 25. Monitoring cho cleanup và index

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Session active count | Số session còn hợp lệ theo repository |
| Expired candidates | Số session đến hạn cleanup |
| Cleanup duration | Thời gian mỗi vòng cleanup |
| Cleanup failures | Lỗi Redis/JDBC hoặc listener |
| Stale index candidates | Index member không còn session hợp lệ |
| Orphan session records | Session record thiếu index cần thiết |
| JDBC expired row count | Số session/attribute row được xóa |
| Redis keyspace event lag | Độ trễ hoặc tình trạng mất event |
| Test fixture residue | Dữ liệu thử nghiệm còn lại sau suite |
| Session repository latency | Thời gian find/save/delete |

Metric label không nên chứa session ID, username, email hoặc cookie. Dùng tag có cardinality thấp như repository type, environment, namespace class và operation. Log cần che session ID; không log serialized session payload hoặc `SecurityContext` đầy đủ.

## 26. Runbook khi phát hiện dữ liệu session tăng bất thường

Khi số key/row tăng dù active session không tăng:
1. Xác định Redis hay JDBC và namespace/schema bị ảnh hưởng.
2. Kiểm tra session active count và expired candidate count riêng.
3. Kiểm tra cleanup job có chạy và hoàn tất không.
4. Với Redis, kiểm tra keyspace notifications, listener health, expiration store và Redis Cluster topology.
5. Kiểm tra principal index có stale member hay không.
6. Với JDBC, kiểm tra cleanup cron, query plan, lock/wait và số row attributes.
7. Chạy reconciliation ở chế độ dry-run trên một phạm vi nhỏ.
8. Ước lượng số dữ liệu sẽ bị xóa và kiểm tra session còn hoạt động.
9. Chạy cleanup theo batch có rate limit.
10. Đối chiếu active sessions, index và row/key count sau xử lý.

Không chạy `FLUSHDB` hoặc xóa toàn bộ bảng để xử lý nhanh. Nếu không thể xác định chính xác session nào hết hạn, hãy dừng thao tác xóa và khôi phục quan sát/backup trước.

## 27. Kiểm thử cleanup Redis

Integration test Redis nên kiểm tra:
- Session được tạo trong namespace test riêng.
- Session active vẫn tìm thấy qua `findById`.
- `deleteById` làm session không còn được trả về.
- Principal index không còn session ID đã xóa sau khi event/cleanup xử lý.
- Session hết hạn không được trả về dù physical cleanup có thể trễ.
- Expiration event được nhận khi Redis keyspace notifications cấu hình đúng.
- Cleanup task xử lý expiration mapping mà không xóa nhầm session vừa gia hạn.
- Test không đụng đến namespace của suite khác.

Không assert rằng mọi key nội bộ biến mất ngay đúng mili giây timeout. Hãy poll với deadline hữu hạn và phân biệt “repository không còn trả session hợp lệ” với “mọi metadata vật lý đã được dọn”.

## 28. Kiểm thử cleanup JDBC

Integration test JDBC nên kiểm tra:
- Session và attribute rows được ghi vào schema test.
- Session hết hạn không được trả về bởi repository.
- Cleanup job xóa session và attributes theo expiry time.
- Principal lookup không trả session đã bị xóa.
- Custom cleanup query giữ đúng điều kiện và index.
- Transaction/lock không làm cleanup chặn request quá lâu.
- Cleanup chỉ tác động schema/table test.
- Test parallel không xóa session của test khác.

Có thể đặt `cleanupCron` ngắn trong test profile hoặc gọi cleanup API được hỗ trợ nếu implementation cung cấp. Không dựa vào cron production chạy đúng lịch trong một test ngắn; kiểm tra trực tiếp repository và job theo cách có thể điều khiển.

## 29. Chính sách retention và bảo vệ dữ liệu

Session thường chứa principal, thông tin xác thực hoặc dữ liệu cá nhân. Chính sách retention cần:
- Idle timeout phù hợp với mức nhạy cảm.
- Absolute session lifetime nếu sản phẩm yêu cầu.
- Thu hồi ngay khi logout hoặc sự kiện bảo mật quan trọng.
- Cleanup physical data và attributes theo lịch hợp lý.
- Tách audit retention khỏi session retention.
- Giới hạn quyền đọc Redis/JDBC và dùng TLS.
- Không lưu thông tin nhạy cảm không cần thiết trong session.
- Xử lý backup/restore để tránh khôi phục session đã bị thu hồi theo chính sách.
- Có quy trình xóa dữ liệu test sau khi pipeline hoàn tất.

Dữ liệu session hết hạn không nên được giữ vô thời hạn để thuận tiện debug. Dùng correlation ID và audit record đã lọc thay vì giữ cookie, session ID hoặc payload nhạy cảm.

## 30. Checklist trước khi vận hành

- Xác định repository Redis thường hay Redis indexed.
- Bảo đảm keyspace notifications cần thiết được cấu hình đúng.
- Có cleanup task cho expiration mapping và theo dõi lỗi.
- Hiểu rằng Redis expired event có thể trễ; không dùng event làm quyết định xác thực.
- Kiểm tra principal index cleanup và Redis Cluster event subscription.
- Với JDBC, xác nhận cleanup cron xóa cả session và attributes.
- Giữ SQL index phù hợp với expiry/principal queries.
- Không custom cleanup query nếu chưa test schema và query plan.
- Dùng repository API để delete session thay vì xóa key/row thủ công.
- Dùng namespace/schema riêng cho test.
- Không dùng FLUSHDB, FLUSHALL hoặc DELETE toàn bảng trên datastore dùng chung.
- Cleanup test theo session ID do test tạo.
- Dùng SCAN có phạm vi khi kiểm kê Redis, không dùng KEYS * production.
- Có reconciliation dry-run, batch limit và audit.
- Theo dõi active sessions, expired data, stale indexes và cleanup latency.
- Tách session retention khỏi audit retention.
- Kiểm thử event loss, cleanup lag và parallel test isolation.

Spring Session cần quản lý đồng thời session record, expiration metadata và các index phụ. Redis indexed repository dựa vào keyspace events cùng expiration tracking để cleanup có kiểm soát; JDBC repository có job xóa session hết hạn và attributes theo lịch. Event hoặc cleanup vật lý có thể trễ, vì vậy repository phải từ chối session hết hạn độc lập với việc key/row đã biến mất hay chưa. Trong vận hành và kiểm thử, hãy xóa qua API repository, cô lập namespace/schema, dọn đúng ID do test tạo và dùng reconciliation có dry-run cho metadata mồ côi. Tuyệt đối không dùng thao tác xóa toàn kho trên Redis/JDBC dùng chung.

## Tài liệu tham khảo

- [Spring Session — Redis Configurations and Expiration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — RedisIndexedSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [Spring Session — JDBC Cleanup Job](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — API and SessionRepository semantics](https://docs.spring.io/spring-session/reference/api.html)

