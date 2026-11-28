# Đổi repository cơ bản, có chỉ mục hoặc chuyển kho lưu trữ

Spring Session tách API HttpSession khỏi nơi lưu dữ liệu bằng SessionRepository. Nhờ abstraction này, ứng dụng có thể thay implementation lưu session mà controller và service vẫn làm việc với HttpSession. Tuy nhiên, thay repository không phải lúc nào cũng chỉ là đổi một dependency hoặc một property. Repository cơ bản, repository có chỉ mục và các backend Redis/JDBC có thể khác nhau về khả năng tra cứu, cấu trúc key/bảng, serializer, TTL, event và cách lưu attributes.

Khi nâng cấp hoặc di chuyển, cần phân biệt hai thay đổi:

- **Đổi khả năng repository:** ví dụ từ SessionRepository cơ bản sang FindByIndexNameSessionRepository để tra cứu session theo principal.
- **Đổi kho lưu trữ:** ví dụ từ Redis sang JDBC hoặc ngược lại. Đây là thay đổi backend và thường kéo theo chuyển đổi dữ liệu, schema, serializer, expiration và vận hành.

Một session ID đang nằm trong cookie chỉ là định danh. Dữ liệu session và index nằm trong repository. Nếu đổi sang một kho mới chưa có record tương ứng, request mang cookie cũ sẽ không tìm thấy session và người dùng cần đăng nhập lại hoặc được chuyển dữ liệu bằng một quy trình migration có kiểm soát.

## 1. Hiểu các abstraction của Spring Session

Các API chính:

- Session mô tả một phiên, gồm ID, creation time, last accessed time, max inactive interval và attributes.
- SessionRepository cung cấp createSession, save, findById và deleteById.
- FindByIndexNameSessionRepository mở rộng repository để tra cứu các session theo một index name và index value, thường dùng principal name.
- Các implementation cụ thể lưu session trong Redis, JDBC hoặc một kho do ứng dụng tự xây dựng.

SessionRepository phù hợp khi ứng dụng chỉ cần làm việc với session ID đã biết. FindByIndexNameSessionRepository hữu ích khi cần tìm tất cả session gắn với một principal, ví dụ trang quản lý thiết bị đăng nhập hoặc giới hạn số phiên đồng thời.

Sơ đồ quan hệ:

~~~mermaid
classDiagram
    class SessionRepository {
      +createSession()
      +save(session)
      +findById(id)
      +deleteById(id)
    }
    class FindByIndexNameSessionRepository {
      +findByIndexNameAndIndexValue(name, value)
      +findByPrincipalName(principalName)
    }
    class RedisRepository
    class JdbcRepository
    SessionRepository <|-- FindByIndexNameSessionRepository
    FindByIndexNameSessionRepository <|.. RedisRepository
    FindByIndexNameSessionRepository <|.. JdbcRepository
~~~

Sơ đồ chỉ thể hiện quan hệ khái niệm. Tên class, package, generic type và việc implementation cụ thể hỗ trợ interface nào phụ thuộc phiên bản Spring Session đang dùng. Hãy kiểm tra API của dependency dự án trước khi đổi kiểu bean hoặc import.

## 2. Repository cơ bản và repository có chỉ mục khác nhau ở đâu?

Repository cơ bản biết cách lưu và tìm session bằng ID. Nó không nhất thiết cung cấp khả năng truy vấn ngược từ principal sang các session ID.

Repository có chỉ mục duy trì thêm thông tin tra cứu, ví dụ principal name được ánh xạ đến các session. Nhờ vậy, ứng dụng có thể tìm session của một người dùng mà không cần biết trước ID của từng session.

| Nhu cầu | Repository cơ bản | Repository có chỉ mục |
| --- | --- | --- |
| Tải session từ cookie/session ID | Có | Có |
| Lưu và cập nhật attributes | Có | Có |
| Xóa session theo ID | Có | Có |
| Tìm tất cả session theo principal | Không được bảo đảm | Có qua index API |
| Quản lý nhiều thiết bị đăng nhập | Cần tự xây thêm dữ liệu | Có thể dùng principal index |
| Giới hạn số session của người dùng | Cần tự tra cứu | Có thể tra cứu qua index rồi áp dụng chính sách |

Index không thay thế session record. Nó là dữ liệu phụ trợ để tìm session. Nếu index thiếu hoặc stale, thao tác findById vẫn có thể hoạt động trong khi tìm theo principal cho kết quả không đầy đủ hoặc chứa ID không còn hợp lệ.

Không dùng một repository có index chỉ vì tên implementation có chữ Indexed. Hãy xác định chức năng thực tế mà ứng dụng cần, loại index được hỗ trợ và chi phí duy trì index.

## 3. Khi nào cần chuyển sang repository có chỉ mục?

Các trường hợp phổ biến:

- Hiển thị danh sách thiết bị hoặc phiên đang đăng nhập của người dùng.
- Đăng xuất một phiên cụ thể từ trang quản lý tài khoản.
- Đăng xuất tất cả thiết bị sau khi đổi mật khẩu hoặc phát hiện credential bị lộ.
- Giới hạn số session đồng thời cho một principal.
- Thu hồi session theo người dùng khi tài khoản bị khóa.
- Giám sát số session đang hoạt động theo principal.

Nếu ứng dụng chỉ nhận session ID từ cookie và tải đúng session đó, repository cơ bản có thể đủ. Index làm tăng chi phí lưu và cập nhật metadata, do đó không nên thêm chỉ mục nếu không có use case cần truy vấn ngược.

## 4. API tra cứu theo principal

Spring Session định nghĩa tên index chuẩn cho principal:

~~~java
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

class ActiveSessionQuery {

    private final FindByIndexNameSessionRepository<? extends Session>
            sessionRepository;

    ActiveSessionQuery(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.sessionRepository = repository;
    }

    Map<String, ? extends Session> findSessions(String principalName) {
        return sessionRepository.findByPrincipalName(principalName);
    }
}
~~~

Đoạn code minh họa kiểu API. Generic type và khả năng inject bean phụ thuộc repository implementation/version. Nếu ứng dụng chỉ inject SessionRepository, không thể gọi phương thức principal lookup một cách an toàn bằng cách ép kiểu tùy tiện.

Giá trị principalName phải được lấy từ danh tính đã xác thực và được chuẩn hóa nhất quán. Không nhận một username tùy ý từ request rồi trả về danh sách session của người đó nếu người gọi không có quyền quản trị tương ứng.

Tra cứu principal index cũng không tự động xác minh quyền trên từng session. Trước khi thu hồi hoặc hiển thị thông tin, ứng dụng cần kiểm tra quyền và phạm vi tenant.

## 5. Principal index được tạo và duy trì như thế nào?

Repository có index cần biết principal name của session. Trong ứng dụng Spring Security, principal thường nằm trong SecurityContext được lưu trong session. Spring Session có cơ chế tích hợp để trích xuất principal name từ session theo implementation và cấu hình.

Các yếu tố cần đồng bộ:

- Principal name phải ổn định qua các lần đăng nhập.
- Cách chuẩn hóa chữ hoa/thường phải nhất quán.
- Nếu username có thể trùng giữa tenant, cần định danh principal không nhập nhằng, ví dụ subject ID toàn cục hoặc giá trị có tenant scope.
- Thay đổi principal name hoặc cách resolver trích principal cần có kế hoạch cập nhật index.
- Logout, expiration và delete phải dọn index phụ trợ theo implementation.

Không tự lưu principal index bằng một attribute tùy ý rồi giả định repository sẽ lập chỉ mục. Dùng cơ chế index mà implementation hỗ trợ và kiểm tra tài liệu của đúng phiên bản.

## 6. Chuyển từ repository cơ bản sang repository có chỉ mục

Đây là thay đổi khả năng tra cứu, nhưng dữ liệu hiện có không nhất thiết tự động có index mới. Cần trả lời:

1. Repository cũ và mới có cùng định dạng session record không?
2. Các session hiện hữu có principal metadata cần thiết không?
3. Index có được tạo khi session được save tiếp theo hay cần backfill?
4. Có API công khai để rebuild index không?
5. Nếu không thể xác định principal của session cũ, chính sách là giữ session nhưng không tra cứu được, hay yêu cầu đăng nhập lại?

Không giả định việc đổi bean từ basic sang indexed sẽ tự quét toàn bộ session cũ và dựng index. Một số implementation chỉ cập nhật index khi session được lưu hoặc khi có sự kiện tương ứng. Các session không hoạt động có thể không bao giờ được backfill trước khi hết hạn.

### Chiến lược chuyển đổi

| Chiến lược | Cách làm | Khi phù hợp |
| --- | --- | --- |
| Chờ session mới | Deploy repository có index; index được tạo khi session được cập nhật hoặc tạo mới | Chấp nhận index chưa đầy đủ trong giai đoạn chuyển tiếp |
| Re-authentication | Xóa/để hết hạn session cũ, người dùng đăng nhập lại để tạo session mới có index | Ưu tiên đơn giản và tính đúng đắn |
| Backfill có kiểm soát | Dùng migration job đọc session cũ, xác định principal rồi tạo index | Có cách đọc dữ liệu được hỗ trợ và cần giữ session |
| Dual-write tạm thời | Ghi cả cấu trúc cũ và mới theo một giao thức rõ ràng | Chỉ khi cần giảm downtime và có cơ chế nhất quán, đối soát |

Không viết trực tiếp key index nội bộ nếu không có hợp đồng được hỗ trợ. Key layout có thể thay đổi theo phiên bản. Nếu không có API backfill an toàn, lựa chọn re-authentication thường ít rủi ro hơn so với tự dựng index bằng cách ghi key thủ công.

## 7. Chuyển giữa Redis repository cơ bản và indexed repository

Spring Session Redis có các implementation với khả năng khác nhau. Trong các phiên bản hỗ trợ, repository cơ bản tập trung vào session ID; indexed repository bổ sung principal index và khả năng tra cứu theo principal.

Trước khi đổi:

- Kiểm tra class implementation và interface mà nó triển khai.
- Xác nhận namespace Redis.
- Kiểm tra serializer và cấu trúc session hash.
- Kiểm tra key phụ trợ, TTL và expiration handling.
- Xác nhận cách principal được trích xuất và index được cập nhật.
- Đọc migration note của phiên bản Spring Session đang nâng cấp.

Không giả định hai implementation dùng chung toàn bộ key schema chỉ vì cùng lưu ở Redis. Nếu schema tương thích theo tài liệu phiên bản, vẫn cần test trên bản sao dữ liệu thực tế. Nếu không có cam kết tương thích, hãy coi đó là một thay đổi storage format.

Ví dụ cấu hình Redis repository thường được quản lý qua Spring Boot auto-configuration hoặc annotation cấu hình của Spring Session. Chọn đúng một đường cấu hình và kiểm tra repository thực tế được inject vào SessionRepositoryFilter. Không tạo hai SessionRepositoryFilter hoặc hai repository bean cùng cạnh tranh xử lý request.

## 8. Chuyển giữa JDBC repository cơ bản và indexed repository

JDBC repository sử dụng schema bảng để lưu metadata và attributes. Repository có index có thể cần thêm cột, index SQL hoặc cấu trúc phụ trợ để tra cứu principal. Chi tiết schema thay đổi theo phiên bản.

Trước khi migration:

- Lấy schema mẫu từ đúng phiên bản Spring Session đang dùng.
- So sánh schema hiện tại với schema đích.
- Xác định migration SQL cần thiết và thứ tự deploy.
- Kiểm tra index database có phù hợp query pattern không.
- Kiểm tra dữ liệu session cũ có thể gắn principal hay không.
- Dùng Flyway/Liquibase hoặc quy trình migration có kiểm soát.

Không sửa bảng Spring Session bằng cách thêm cột tùy ý rồi kỳ vọng repository tự dùng nó. Dùng schema được hỗ trợ và migration theo tài liệu phiên bản. Chạy migration trước khi deploy code mới nếu code mới yêu cầu schema mới; tránh để node cũ ghi vào schema mà nó không hiểu.

## 9. Khi nào chuyển cả kho lưu trữ?

Các tình huống:

- Redis sang JDBC để dùng database quan hệ hiện có.
- JDBC sang Redis để giảm độ trễ hoặc tách tải session khỏi database nghiệp vụ.
- Redis cluster này sang cluster khác hoặc sang managed Redis.
- Database/schema cũ sang database/schema mới.
- Custom repository sang implementation Spring Session chuẩn.

Đổi backend có nhiều khác biệt hơn đổi capability:

| Thành phần | Cần kiểm tra |
| --- | --- |
| Session ID | ID có được giữ nguyên hoặc ánh xạ sang ID mới? |
| Attributes | Serializer và kiểu dữ liệu có tương thích? |
| Metadata | creationTime, lastAccessedTime, maxInactiveInterval có được giữ? |
| Expiration | TTL và idle timeout có giữ đúng thời điểm hết hạn? |
| Principal index | Index có được tái tạo và cập nhật? |
| Events | SessionCreated/Deleted/Expired có hành vi tương ứng? |
| Cookie/header | Resolver có tiếp tục đọc đúng ID? |
| SecurityContext | Phiên bản class và cách serialize có tương thích? |
| Cleanup | Job dọn session hết hạn có được cấu hình lại? |
| HA | Backup, replication, failover và monitoring có tương đương? |

Nếu các điểm trên không được xác minh, không coi việc đổi connection string là một migration hoàn chỉnh.

## 10. Vì sao không nên mặc định session record có thể copy nguyên dạng?

Redis và JDBC có cách biểu diễn dữ liệu khác nhau. Redis repository có thể lưu session trong hash và key phụ trợ; JDBC repository có thể chia metadata và attributes thành nhiều hàng. Serializer cũng có thể khác.

Ngay cả khi cả hai backend đều lưu cùng tên attribute:

- Byte serialization có thể khác.
- Class name hoặc package có thể đã đổi.
- Một backend có thể lưu metadata ở cột riêng, backend khác lưu trong hash.
- Principal index có thể không tồn tại ở nguồn.
- TTL có thể được biểu diễn bằng expiration của key hoặc thời điểm trong metadata.
- Event và cleanup có thể phụ thuộc cơ chế riêng.

Không copy trực tiếp Redis dump sang bảng JDBC hoặc ngược lại. Cần migration tool hiểu schema nguồn và đích, hoặc chọn cutover yêu cầu người dùng xác thực lại.

## 11. Lựa chọn cutover: giữ session hay yêu cầu đăng nhập lại?

Với nhiều ứng dụng, session có vòng đời ngắn và có thể tạo lại bằng login. Khi đó, cutover rõ ràng và an toàn thường là:

1. Thông báo maintenance hoặc triển khai trong cửa sổ phù hợp.
2. Dừng hoặc drain request ghi session vào repository cũ.
3. Chuyển toàn bộ instance sang repository mới cùng lúc hoặc qua một cơ chế rollout tương thích.
4. Dùng namespace/schema mới để tránh đọc nhầm dữ liệu cũ.
5. Xóa cookie/định danh cũ nếu cần, hoặc để request cũ nhận session miss.
6. Yêu cầu xác thực lại.
7. Theo dõi login success, session creation và repository error.

Ưu điểm là không cần chuyển đổi serialized attributes hay principal index cũ. Nhược điểm là người dùng phải đăng nhập lại và các workflow tạm trong session có thể mất. Dữ liệu nghiệp vụ quan trọng không nên chỉ tồn tại trong session.

Nếu phải giữ session, cần kế hoạch migration dữ liệu có kiểm soát, xác định TTL còn lại, principal, attributes, index và rollback. Không reset toàn bộ timeout về thời lượng mới trong lúc copy; làm vậy có thể kéo dài session vượt thời hạn bảo mật ban đầu.

## 12. Migration có thời gian chuyển tiếp

Khi không thể yêu cầu tất cả người dùng đăng nhập lại cùng lúc, có thể thiết kế read-through migration:

1. Request mang session ID được tìm trong repository mới.
2. Nếu không có, migration layer có thể tìm trong repository cũ.
3. Nếu tìm thấy và dữ liệu được xác minh tương thích, chuyển session sang repository mới.
4. Lưu session mới với TTL còn lại, không khởi động lại idle timeout tùy tiện.
5. Chỉ xóa bản cũ sau khi bản mới đã được ghi và kiểm tra thành công.

Đây là kiến trúc migration tùy chỉnh, không phải hành vi mặc định của Spring Session. Phải giải quyết:

- Hai request đồng thời cùng migrate một ID.
- Logout/delete ở kho cũ trong lúc migrate.
- Session cũ hết hạn giữa read và write.
- Ghi mới thành công nhưng xóa cũ thất bại.
- Ghi mới thất bại nhưng ID cookie vẫn được trả về.
- Một node chạy phiên bản mới, node khác vẫn dùng repository cũ.
- Rollback khi một phần session đã chuyển.

Nếu triển khai read-through, dùng migration marker/version, thao tác idempotent và cơ chế khóa hoặc compare-and-set phù hợp. Tránh dual-write không có transaction phân tán: hai backend có thể lệch trạng thái nếu một write thành công còn write kia thất bại.

## 13. Bảo toàn TTL và thời hạn session

Session có idle timeout; repository có thể lưu lastAccessedTime và maxInactiveInterval. Khi migrate, cần tính thời gian còn lại:

\[
remaining = maxInactiveInterval - (now - lastAccessedTime)
\]

Nếu remaining nhỏ hơn hoặc bằng 0, session đã hết hạn và không nên được migrate thành phiên mới có thời hạn đầy đủ.

Ví dụ:

- maxInactiveInterval: 30 phút.
- lastAccessedTime: 12 phút trước.
- Thời gian còn lại: khoảng 18 phút.

Nếu migration ghi session đích với timeout 30 phút tính từ lúc copy, session được kéo dài thêm 12 phút so với chính sách ban đầu. Đây là lỗi có thể mở rộng cửa sổ sử dụng credential.

Tính toán cần dùng clock nhất quán và xử lý độ lệch đồng hồ giữa instance. Với migration offline, dừng ghi hoặc chụp snapshot nhất quán giúp tránh thời gian truy cập thay đổi trong lúc tính TTL.

## 14. Giữ nguyên session ID hay phát ID mới?

Giữ session ID có thể giúp browser tiếp tục gửi cookie hiện tại, nhưng chỉ an toàn khi:

- Dữ liệu đích được chuyển đúng và đầy đủ.
- ID vẫn duy nhất trong namespace đích.
- Không có nguy cơ session fixation hoặc ID bị lộ.
- Các node cũ/mới không diễn giải ID theo kho khác nhau.

Phát ID mới có thể giảm rủi ro khi đổi security boundary hoặc định dạng lưu trữ. Tuy nhiên, cần phát cookie mới, ánh xạ request và đảm bảo ID cũ bị thu hồi.

Trong Spring Security, đăng nhập thường có session fixation protection để đổi session ID sau authentication. Migration giữa repository không tự thay thế cơ chế này. Không tự tái sử dụng ID cũ nếu yêu cầu bảo mật hoặc chính sách session fixation yêu cầu rotate.

## 15. Cấu hình repository và resolver phải thay đổi nhất quán

Các instance trong cùng một cụm phải đồng nhất:

- Repository implementation.
- Backend endpoint/database/schema.
- Redis namespace hoặc JDBC table/schema.
- Serializer và classpath.
- FlushMode/SaveMode nếu backend hỗ trợ.
- Session timeout.
- HttpSessionIdResolver và cookie/header name.
- Principal index resolver.
- Expiration/cleanup configuration.

Không deploy một node dùng Redis repository mới và node khác dùng JDBC repository cũ nếu cả hai cùng nhận request với một cookie mà không có routing/migration layer được thiết kế rõ. Request có thể đến node bất kỳ và một node sẽ không tìm thấy session.

Nếu rolling deployment buộc chạy song song hai phiên bản, cần giữ khả năng tương thích dữ liệu hoặc tách traffic/namespace rõ ràng. Không dựa vào sticky session để che giấu schema mismatch.

## 16. Kiểm thử trước và sau migration

Một migration test cần dùng dữ liệu đại diện:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Session cơ bản | ID và attributes được đọc lại đúng |
| Session có SecurityContext | Principal và authentication state được xử lý đúng |
| Session có nhiều attributes | Serializer tương thích |
| Session gần hết hạn | TTL còn lại không bị kéo dài |
| Session đã hết hạn | Không được migrate thành phiên hợp lệ |
| Principal index | Tra cứu theo principal trả đủ session mong đợi |
| Logout | Delete ở kho mới không để session cũ tiếp tục được dùng |
| Hai request đồng thời | Không tạo hai bản migration mâu thuẫn |
| Redis/JDBC outage | Không trả session giả hoặc fail-open |
| Rollback | Phiên bản cũ có thể đọc dữ liệu mới hoặc có kế hoạch invalidation |
| Cookie/header | Client tiếp tục dùng đúng resolver hoặc nhận định danh mới |
| Expiration event | Event/cleanup hoạt động theo implementation mới |

Chạy test trên Redis/JDBC thật hoặc Testcontainers. Mock repository không xác nhận schema SQL, TTL Redis, index key, serialization và transaction behavior.

## 17. Kế hoạch triển khai an toàn

Một kế hoạch migration nên có các giai đoạn:

### Giai đoạn 1: Khảo sát

- Xác định repository hiện tại và interface đang dùng.
- Đếm session hoạt động, kích thước attributes và TTL.
- Xác định use case cần principal index.
- Kiểm tra serializer, schema, namespace và event behavior.
- Chọn cutover yêu cầu login lại hay giữ session.

### Giai đoạn 2: Chuẩn bị đích

- Tạo Redis/database/schema đích.
- Thiết lập ACL, TLS, backup và monitoring.
- Áp dụng schema migration nếu dùng JDBC.
- Cấu hình namespace, timeout, serializer và index.
- Chạy contract/integration tests trên repository đích.

### Giai đoạn 3: Chuyển đổi

- Drain request hoặc bật migration layer đã kiểm thử.
- Chuyển cấu hình tất cả instance theo kế hoạch.
- Kiểm tra health, session lookup, save/delete và principal index.
- Theo dõi login failures, session misses, repository latency và errors.

### Giai đoạn 4: Xác nhận và dọn kho cũ

- Xác nhận không còn node ghi vào kho cũ.
- Đối chiếu số session/index nếu có migration dữ liệu.
- Giữ backup theo retention và bảo vệ dữ liệu cũ.
- Chỉ xóa kho cũ sau thời gian rollback đã thống nhất.

## 18. Rollback cần tính đến dữ liệu đã ghi ở kho mới

Rollback code không tự đưa dữ liệu từ repository mới về repository cũ. Nếu người dùng đã đăng nhập hoặc cập nhật session trong kho mới, phiên bản cũ có thể không nhìn thấy những thay đổi đó.

Các lựa chọn:

- Nếu cutover đã invalidated session, rollback cũng yêu cầu người dùng đăng nhập lại.
- Nếu dùng read-through migration, giữ bản cũ cho đến khi hết cửa sổ rollback và có quy trình reconcile.
- Nếu hai định dạng không tương thích, không bật node cũ đọc dữ liệu mới.
- Không xóa kho mới trước khi xác nhận rollback không còn cần dữ liệu đó.

Định nghĩa trước điều kiện rollback, thời gian giữ kho cũ, cách xử lý session được tạo sau cutover và việc logout trong cửa sổ chuyển đổi.

## 19. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| API tìm session theo principal trả rỗng | Repository cơ bản không hỗ trợ index hoặc session cũ chưa được index | Dùng indexed repository và backfill/re-auth theo kế hoạch |
| findById vẫn hoạt động nhưng findByPrincipalName thiếu session | Index chưa được tạo hoặc stale | Kiểm tra principal resolver và index lifecycle |
| Sau đổi repository người dùng bị logout | Kho mới chưa có session ID cũ | Migration dữ liệu hoặc cutover yêu cầu đăng nhập lại |
| Session lỗi deserialize | Serializer/classpath không tương thích | Chuyển đổi DTO hoặc invalidation có kế hoạch |
| Session được kéo dài sau migration | TTL được reset thay vì giữ thời gian còn lại | Tính remaining lifetime từ lastAccessedTime |
| Logout ở repository mới nhưng phiên cũ vẫn còn | Dual-write/delete không đồng bộ | Thu hồi ở cả hai nơi hoặc dùng migration marker/tombstone |
| Một số node đọc được, node khác không | Cấu hình repository/namespace/schema khác nhau | Đồng bộ cấu hình trước khi mở traffic |
| JDBC query principal chậm | Thiếu index SQL hoặc query không phù hợp | Kiểm tra schema/index và query plan |
| Principal index nhầm tenant | Principal name không duy nhất hoặc resolver sai | Dùng subject/tenant-qualified key và kiểm tra quyền |

## 20. Checklist nâng cấp và di chuyển

- [ ] Xác định ứng dụng cần SessionRepository cơ bản hay FindByIndexNameSessionRepository.
- [ ] Xác minh implementation thực tế hỗ trợ interface và index nào.
- [ ] Kiểm tra cách principal name được trích xuất, chuẩn hóa và lưu.
- [ ] Xác định session cũ có index hay cần backfill/re-authentication.
- [ ] Kiểm tra key schema Redis hoặc table/schema JDBC theo đúng phiên bản.
- [ ] Kiểm tra serializer, DTO, SecurityContext và classpath.
- [ ] Lập kế hoạch giữ session hay yêu cầu người dùng đăng nhập lại.
- [ ] Nếu migrate dữ liệu, bảo toàn TTL còn lại và xử lý race/logout.
- [ ] Đồng bộ repository, namespace, resolver, timeout và cleanup trên mọi node.
- [ ] Kiểm thử find/save/delete, principal index, expiration, failover và rollback.
- [ ] Giữ backup kho cũ và chỉ xóa sau khi hết cửa sổ rollback.
- [ ] Theo dõi session miss, login failure, repository latency và index consistency.

Đổi từ repository cơ bản sang repository có chỉ mục chủ yếu bổ sung khả năng tra cứu và dữ liệu index; đổi Redis sang JDBC hoặc ngược lại còn thay đổi schema, serializer, TTL và vận hành. Spring Session cung cấp abstraction để ứng dụng dùng HttpSession nhất quán, nhưng không tự động chuyển mọi session record hoặc principal index giữa các implementation. Hãy kiểm tra hợp đồng của repository, chọn cutover phù hợp, bảo toàn thời hạn session nếu migrate dữ liệu và kiểm thử logout, index, concurrency cùng rollback trước khi chuyển production.
