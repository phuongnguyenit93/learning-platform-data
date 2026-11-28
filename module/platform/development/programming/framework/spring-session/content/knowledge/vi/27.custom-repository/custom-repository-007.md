# Tùy chọn hỗ trợ FindByIndexNameSessionRepository

`SessionRepository` cung cấp các thao tác cơ bản để tạo, tìm, lưu và xóa session theo ID. Một số nghiệp vụ cần tìm phiên theo một thuộc tính khác, phổ biến nhất là principal name để hiển thị các thiết bị đang đăng nhập hoặc thu hồi tất cả phiên của một người dùng. Spring Session định nghĩa hợp đồng `FindByIndexNameSessionRepository` cho khả năng này.

Khi xây dựng repository tùy chỉnh, hỗ trợ interface này có nghĩa là repository phải duy trì một hoặc nhiều chỉ mục tra cứu song song với dữ liệu session. Chỉ thêm một phương thức truy vấn mà không cập nhật index trong mọi đường ghi, xóa, đổi principal và hết hạn sẽ tạo kết quả sai hoặc rò rỉ dữ liệu index. Index phải được xem là một phần của trạng thái session và được cập nhật nhất quán với bản ghi chính.

## 1. Vì sao cần tìm session theo index?

Tra cứu theo ID phù hợp khi client gửi session ID. Nhưng một số chức năng quản trị cần tìm tất cả session thuộc một principal:

- Hiển thị các phiên đăng nhập của người dùng.
- Giới hạn số phiên đồng thời.
- Đăng xuất khỏi các thiết bị khác.
- Thu hồi phiên khi tài khoản bị khóa hoặc đổi mật khẩu.
- Điều tra phiên bất thường theo principal.

Nếu repository chỉ có `findById`, cách đơn giản là quét toàn bộ session, tải từng bản ghi, deserialize và so sánh principal. Cách này có chi phí tăng theo tổng số session, tạo tải lớn lên Redis/JDBC và có thể làm tăng độ trễ khi hệ thống có nhiều người dùng.

Index cho phép ánh xạ một giá trị như principal name tới tập session ID. Truy vấn chỉ đọc các ID phù hợp, sau đó tải những session tương ứng. Với database quan hệ, index có thể là bảng phụ; với Redis, có thể là Set hoặc cấu trúc phù hợp khác.

## 2. Hợp đồng FindByIndexNameSessionRepository

Interface đồng bộ `org.springframework.session.FindByIndexNameSessionRepository` mở rộng `SessionRepository` và bổ sung thao tác tìm theo tên index cùng giá trị:

```java
public interface FindByIndexNameSessionRepository<S extends Session>
        extends SessionRepository<S> {

    String PRINCIPAL_NAME_INDEX_NAME = "...";

    Map<String, S> findByIndexNameAndIndexValue(
            String indexName, String indexValue);

    default Map<String, S> findByPrincipalName(String principalName) {
        return findByIndexNameAndIndexValue(
                PRINCIPAL_NAME_INDEX_NAME, principalName);
    }
}
```

Đoạn mã thể hiện cấu trúc hợp đồng; hãy dùng hằng số do thư viện cung cấp thay vì sao chép chuỗi literal. `findByPrincipalName` là tiện ích cho index principal name. Phương thức tổng quát cho phép repository hỗ trợ thêm các index khác nếu implementation và `IndexResolver` của nó được thiết kế để làm việc đó.

Kết quả là `Map<String, S>`:

- Key là session ID.
- Value là đối tượng session được repository trả về.
- Không tìm thấy phiên phù hợp thì trả map rỗng.
- Không nên trả `null`.

Hợp đồng không quy định repository phải dùng bảng phụ, Redis Set hay một cấu trúc cụ thể. Nó quy định hành vi truy vấn mà implementation phải cung cấp.

## 3. Phân biệt API đồng bộ và reactive

Với ứng dụng Servlet và repository đồng bộ, dùng `FindByIndexNameSessionRepository`. Với WebFlux, có interface riêng là `ReactiveFindByIndexNameSessionRepository`, trong đó thao tác tìm kiếm trả publisher reactive, thường là `Mono<Map<String, S>>`.

| Stack | Interface | Kiểu kết quả truy vấn |
|---|---|---|
| Servlet/đồng bộ | `FindByIndexNameSessionRepository<S>` | `Map<String, S>` |
| WebFlux/reactive | `ReactiveFindByIndexNameSessionRepository<S>` | `Mono<Map<String, S>>` |

Không triển khai interface đồng bộ rồi gọi nó bằng `.block()` trong WebFlux để giả lập repository reactive. Điều đó có thể chặn event-loop và làm giảm khả năng mở rộng. Nếu cần custom repository cho WebFlux, phải triển khai hợp đồng reactive và compose các thao tác Redis/database bất đồng bộ.

## 4. Principal name index là index chuẩn

Index quan trọng nhất có sẵn là `PRINCIPAL_NAME_INDEX_NAME`. Nó ánh xạ principal name đã được xác thực tới các session chứa principal đó. Các implementation indexed của Spring Session có thể dùng `PrincipalNameIndexResolver` để suy ra index từ session, thường thông qua `SecurityContext` và `Authentication`.

Ví dụ sử dụng hằng số chuẩn:

```java
Map<String, Session> sessions = repository.findByIndexNameAndIndexValue(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName);
```

Hoặc dùng phương thức tiện ích:

```java
Map<String, Session> sessions = repository.findByPrincipalName(principalName);
```

Principal name phải đến từ danh tính đã xác thực ở phía server. Không lấy username do client gửi lên rồi dùng nó làm principal index để cấp quyền hoặc thu hồi session của người khác.

Nếu ứng dụng dùng Spring Security, principal name thường được lấy từ `Authentication.getName()`. Repository tùy chỉnh phải biết cách lấy principal theo đúng mô hình xác thực đang dùng; không giả định mọi ứng dụng đều lưu cùng một class `UserDetails` hoặc cùng cấu trúc `SecurityContext`.

## 5. IndexResolver và cách xác định index từ session

Spring Session có abstraction `IndexResolver<S extends Session>` để xác định các index của một session. `PrincipalNameIndexResolver` là implementation dành cho principal name. Repository có thể dùng resolver này hoặc một resolver tùy chỉnh để xác định index cần duy trì.

Về mặt khái niệm, resolver trả về map giữa tên index và giá trị index:

```java
Map<String, String> indexes = indexResolver.resolveIndexesFor(session);
```

Ví dụ:

```text
PRINCIPAL_NAME_INDEX_NAME -> alice@example.com
tenantId                  -> tenant-42
deviceType                -> mobile
```

Index principal name là quy ước quan trọng để tích hợp với Spring Security và `SpringSessionBackedSessionRegistry`. Các index khác là lựa chọn riêng của ứng dụng; cần thống nhất tên, chuẩn hóa giá trị và cách cập nhật.

Nếu principal được lưu trong `SecurityContext`, resolver cần đọc được context đó. Nếu ứng dụng dùng authentication tùy chỉnh hoặc không lưu `SecurityContext` theo cấu trúc mặc định, có thể cần một resolver phù hợp. Hãy kiểm thử với session thực tế sau khi authentication filter đã lưu context, không chỉ tạo session giả với một chuỗi username.

## 6. Thiết kế cấu trúc dữ liệu index

Một index thường là quan hệ nhiều-nhiều:

- Một principal có thể có nhiều session.
- Một session có thể có một principal và có thể có thêm các index phụ.
- Một index value có thể trỏ tới nhiều session ID.

Với JDBC, có thể dùng bảng phụ tổng quát:

```sql
CREATE TABLE APP_SESSION_INDEX (
    INDEX_NAME  VARCHAR(100) NOT NULL,
    INDEX_VALUE VARCHAR(255) NOT NULL,
    SESSION_ID VARCHAR(36) NOT NULL,
    PRIMARY KEY (INDEX_NAME, INDEX_VALUE, SESSION_ID),
    FOREIGN KEY (SESSION_ID)
        REFERENCES APP_SESSION (SESSION_ID)
        ON DELETE CASCADE
);

CREATE INDEX APP_SESSION_INDEX_BY_SESSION
    ON APP_SESSION_INDEX (SESSION_ID);
```

Tên bảng/cột và kiểu ID phải phù hợp với schema session thực tế. Khóa chính tổng hợp ngăn một session bị thêm trùng vào cùng index. Index phụ theo `SESSION_ID` giúp xóa nhanh toàn bộ quan hệ khi session bị xóa hoặc thay đổi index.

Truy vấn theo index có thể dùng join:

```sql
SELECT s.*
FROM APP_SESSION s
JOIN APP_SESSION_INDEX i ON i.SESSION_ID = s.SESSION_ID
WHERE i.INDEX_NAME = ?
  AND i.INDEX_VALUE = ?
  AND s.EXPIRY_TIME > ?;
```

Tham số phải được bind qua `PreparedStatement`, không nối principal hoặc index value vào chuỗi SQL. Điều kiện expiry giúp tránh trả phiên đã hết hạn logic dù cleanup vật lý chưa chạy.

Với Redis, có thể duy trì Set chứa session ID theo index:

```text
SADD app:sessions:index:<index-name>:<index-value> <session-id>
SREM app:sessions:index:<index-name>:<index-value> <session-id>
SMEMBERS app:sessions:index:<index-name>:<index-value>
```

Đây là sơ đồ key minh họa, không phải tên key nội bộ cố định của Spring Session. Giá trị index phải được encode an toàn khi tạo key; không cho dữ liệu tùy ý tạo key pattern ngoài namespace dự kiến.

## 7. Duy trì index khi tạo và lưu session

Repository tùy chỉnh phải cập nhật session record và index như một thao tác logic thống nhất. Với mỗi lần `save(session)`, cần xác định:

1. Session trước đó có tồn tại không?
2. Các index cũ của session là gì?
3. Các index mới được resolver tính ra là gì?
4. Index nào cần giữ nguyên?
5. Index nào cần xóa?
6. Index nào cần thêm?

Ví dụ principal thay đổi từ `alice` sang `bob`:

```text
Trước save:
  principal=alice -> [session-1, session-2]
  session-2       -> principal=alice

Sau save session-2:
  principal=alice -> [session-1]
  principal=bob   -> [session-2]
  session-2       -> principal=bob
```

Nếu chỉ thêm session vào index mới mà không xóa index cũ, truy vấn `alice` vẫn có thể trả session đã thuộc `bob`. Nếu chỉ xóa index cũ mà chưa lưu session/index mới, có thể làm mất khả năng tìm phiên. Cả hai chiều phải được xử lý.

Với JDBC, cập nhật session row và bảng index nên nằm trong cùng transaction. Với Redis, cần thao tác nguyên tử hoặc một chiến lược phục hồi rõ ràng để session hash và Set index không lệch nhau khi một lệnh giữa chừng thất bại.

## 8. Xóa index khi xóa session

Khi `deleteById(sessionId)` được gọi, repository phải loại bỏ:

- Session record chính.
- Các attributes liên quan.
- Tất cả membership của session trong các index.
- Các metadata phụ trợ do implementation tạo ra.

Với JDBC, foreign key `ON DELETE CASCADE` có thể xóa bảng index khi session row bị xóa, nếu quan hệ và schema được thiết kế phù hợp. Nếu không dùng cascade, repository cần xóa bảng index trong cùng transaction.

Với Redis, repository cần biết các index mà session đang tham gia để chạy `SREM` cho từng index. Có thể lưu một tập reverse index theo session ID để tránh quét toàn bộ index keyspace. Không dùng `KEYS *` để tìm tất cả index trên Redis production.

Thao tác xóa nên idempotent: gọi xóa hai lần không tạo trạng thái lỗi. Điều này quan trọng khi cleanup, logout và retry có thể cùng tác động một session.

## 9. Hết hạn và index mồ côi

Session có thể hết hạn logic trước khi dữ liệu vật lý bị cleanup. Khi đó, index có thể còn chứa session ID đã hết hạn. Truy vấn `findByIndexNameAndIndexValue` không nên trả session đã hết hạn chỉ vì membership còn trong index.

Một chiến lược an toàn gồm:

1. Lấy các session ID từ index.
2. Tải session tương ứng và kiểm tra `isExpired()` hoặc thời điểm expiry theo repository.
3. Chỉ đưa session còn hợp lệ vào kết quả.
4. Xóa membership đã lỗi thời theo cách an toàn.
5. Có cleanup định kỳ để dọn index mồ côi ngay cả khi không có truy vấn principal.

Với JDBC, điều kiện `EXPIRY_TIME` trong truy vấn giúp lọc session hết hạn logic. Cleanup task xóa session và index row theo transaction. Với Redis indexed repository, expiration marker, keyspace notifications và cleanup task có thể phối hợp xử lý index; custom repository cần có cơ chế tương đương nếu nó duy trì index riêng.

Không dựa hoàn toàn vào Redis keyspace notifications vì subscriber có thể mất kết nối hoặc notification có thể đến trễ. Không dựa hoàn toàn vào một cleanup job chạy định kỳ vì index stale có thể xuất hiện trong khoảng giữa hai lần chạy. Kết hợp kiểm tra hợp lệ lúc truy vấn với cleanup nền thường bền vững hơn.

## 10. Truy vấn theo principal và quản lý nhiều phiên

Một service có thể dùng interface để tìm phiên:

```java
@Service
class UserSessionService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    UserSessionService(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    Map<String, ? extends Session> findSessions(String principalName) {
        return this.repository.findByPrincipalName(principalName);
    }
}
```

Map trả về có thể được dùng để hiển thị thời điểm tạo, lần truy cập gần nhất, timeout và các metadata an toàn khác. Không hiển thị toàn bộ attributes của session cho người dùng cuối; một số attributes có thể chứa SecurityContext hoặc dữ liệu nội bộ.

Đăng xuất khỏi các phiên khác có thể thực hiện bằng cách lấy map rồi xóa từng session ID:

```java
repository.findByPrincipalName(principalName)
        .keySet()
        .stream()
        .filter(id -> !id.equals(currentSessionId))
        .forEach(repository::deleteById);
```

Đây là ví dụ đồng bộ đơn giản. Trong production, cần xác thực principal từ SecurityContext, phân biệt giữ phiên hiện tại hay xóa tất cả, giới hạn số phiên xử lý và ghi nhận lỗi từng thao tác. Với reactive repository, dùng `flatMap`/`concatMap` và trả publisher; không block event-loop.

## 11. Tích hợp Spring Security SessionRegistry

Spring Security có các chức năng quản lý phiên đồng thời. `SpringSessionBackedSessionRegistry` là cầu nối giữa `SessionRegistry` của Spring Security và `FindByIndexNameSessionRepository` của Spring Session.

Nhờ index principal, Spring Security có thể tìm các session đang hoạt động của một người dùng thay vì chỉ biết những session được ghi nhận trong bộ nhớ cục bộ của một JVM. Điều này hữu ích khi ứng dụng chạy nhiều instance và cần giới hạn số phiên đăng nhập đồng thời.

Ví dụ khai báo registry:

```java
@Bean
SpringSessionBackedSessionRegistry<? extends Session> sessionRegistry(
        FindByIndexNameSessionRepository<? extends Session> repository) {
    return new SpringSessionBackedSessionRegistry<>(repository);
}
```

Generic signature và cách kết hợp với cấu hình concurrent session control phụ thuộc phiên bản Spring Security/Spring Session. Điều cốt lõi là repository phải hỗ trợ tìm theo principal và index phải được duy trì chính xác. Nếu repository tùy chỉnh chỉ triển khai `SessionRepository`, nó không đáp ứng contract cần thiết cho registry này.

## 12. Index tùy chỉnh ngoài principal

Interface tổng quát cho phép tìm theo `indexName` và `indexValue`, nhưng việc hỗ trợ index phụ cần có quy ước rõ ràng. Ví dụ ứng dụng có thể muốn tìm session theo tenant hoặc loại thiết bị.

Một hợp đồng nội bộ có thể định nghĩa:

```text
tenantId -> tenant-42
deviceType -> mobile
applicationId -> customer-portal
```

Không phải index nào cũng phù hợp để đưa vào session repository. Chỉ tạo index khi có truy vấn thực tế và có chính sách quyền truy cập. Index theo email, số điện thoại hoặc dữ liệu cá nhân có thể làm tăng khả năng liên kết danh tính và cần được bảo vệ như dữ liệu cá nhân.

Index value nên được chuẩn hóa nhất quán. Ví dụ, nếu principal name không phân biệt chữ hoa/thường, việc ghi `Alice` nhưng truy vấn `alice` phải có một quy tắc chuẩn hóa rõ ràng. Không tự lowercase principal nếu hệ thống identity phân biệt chữ hoa/thường hoặc quy tắc đó làm thay đổi danh tính.

## 13. Bảo vệ index khỏi truy vấn và ghi không đáng tin

Index không phải một cơ chế authorization. Người gọi `findByIndexNameAndIndexValue` phải được phép tra cứu giá trị đó. Nếu endpoint nhận principal name từ client mà không kiểm tra quyền, người dùng có thể liệt kê phiên của người khác.

Các nguyên tắc:

- Lấy principal hiện tại từ SecurityContext đã xác thực.
- Với thao tác quản trị, kiểm tra authority và phạm vi tenant.
- Không trả session attributes nhạy cảm; chỉ trả DTO đã chọn lọc.
- Dùng truy vấn tham số hóa cho JDBC.
- Encode index value khi dùng trong Redis key.
- Giới hạn kích thước index value và số kết quả.
- Không log principal hoặc session ID đầy đủ nếu không cần.
- Không cho phép client tùy ý chọn `indexName` để truy vấn mọi cấu trúc nội bộ.

Nếu một repository hỗ trợ nhiều index, service layer nên expose các truy vấn được phép thay vì đưa API tổng quát cho client.

## 14. Xử lý cập nhật đồng thời trên index

Hai request có thể cùng lưu một session, cùng thay đổi principal hoặc cùng xóa phiên. Một lịch lỗi điển hình:

1. A đọc session với principal `alice`.
2. B đọc cùng session.
3. A đổi principal thành `bob` và cập nhật index.
4. B lưu snapshot cũ vẫn có principal `alice`.
5. Index và session record có thể lệch hoặc trạng thái cuối phụ thuộc thứ tự ghi.

Repository cần cập nhật session và index theo cùng một quy tắc nhất quán. Các lựa chọn gồm transaction JDBC, optimistic locking/version, khóa phù hợp hoặc thao tác nguyên tử Redis. Nếu không có versioning, phải xác định rõ last-write-wins và đảm bảo index được tái đồng bộ từ trạng thái cuối.

Các trường hợp phải kiểm thử:

- Principal đổi từ A sang B trong khi request khác lưu session cũ.
- Hai request cùng thêm session vào principal index.
- Một request xóa session trong khi request khác save.
- Cleanup xóa session đúng lúc query index.
- Hai request logout cùng một session.
- Retry sau lỗi một phần giữa ghi session và ghi index.

Đừng chỉ kiểm tra kết quả ngay sau `save()`. Hãy đọc lại session và index bằng một truy vấn mới, tốt nhất qua instance khác nếu hệ thống chạy phân tán.

## 15. Phục hồi khi session và index không đồng bộ

Index là dữ liệu phụ có thể tái tạo từ session nếu session record chứa đủ thông tin để resolver xác định index. Tuy nhiên, việc tái tạo có thể tốn kém và cần kiểm soát tải.

Các chiến lược phục hồi:

- **Lazy repair:** khi query tìm thấy ID nhưng session không tồn tại hoặc không còn index value tương ứng, xóa membership stale.
- **Periodic reconciliation:** quét theo batch session records và tái xây dựng index trong giờ tải thấp.
- **Transactional write:** giữ session và index trong cùng transaction nếu cùng database.
- **Atomic Redis update:** dùng script hoặc transaction phù hợp để cập nhật session key và index keys.
- **Version marker:** ghi version của index/schema để phát hiện dữ liệu cũ trong rolling migration.

Không thực hiện full scan đồng bộ trong request người dùng. Rebuild index nên chạy theo batch, có giới hạn tốc độ, checkpoint và metric tiến độ. Nếu index bị thiếu, endpoint liệt kê session có thể trả kết quả thiếu; cần có cảnh báo và quy trình sửa.

## 16. Phân trang và giới hạn kết quả

Interface `FindByIndexNameSessionRepository` trả một map cho index value; nó không định nghĩa tham số phân trang chuẩn trong hợp đồng cơ bản. Nếu một principal có hàng nghìn session, việc tải toàn bộ map có thể tiêu tốn bộ nhớ và tạo nhiều truy vấn.

Với repository tùy chỉnh, có thể cung cấp API mở rộng cho service nội bộ:

```java
Page<SessionSummary> findSessionSummaries(
        String principalName, Pageable pageable);
```

API này là phần mở rộng do ứng dụng định nghĩa, không phải method của `FindByIndexNameSessionRepository`. Dùng projection/summary để chỉ tải metadata cần thiết, phân trang theo key ổn định và tránh deserialize toàn bộ attributes nếu không cần.

Nếu cần giữ nguyên contract Spring Session cho tích hợp framework, có thể triển khai method map bằng cách gọi truy vấn index và giới hạn kết quả theo chính sách repository. Tuy nhiên, không âm thầm cắt bớt kết quả nếu caller kỳ vọng đầy đủ danh sách; hãy cung cấp API phân trang riêng và nêu rõ semantics.

## 17. Kiểm thử contract FindByIndexNameSessionRepository

Một bộ test cho repository tùy chỉnh nên bao gồm:

1. Tạo session có principal đã xác thực và lưu; `findByPrincipalName` phải trả session ID đó.
2. Tạo nhiều session cho cùng principal; map phải chứa tất cả session còn hiệu lực.
3. Tạo session cho principal khác; kết quả không được lẫn session.
4. Thay đổi principal; index cũ phải bỏ ID và index mới phải thêm ID.
5. Xóa session; mọi index membership phải được loại bỏ.
6. Để session hết hạn; truy vấn không được trả session đã hết hạn dù cleanup vật lý chưa chạy.
7. Gửi index name không hỗ trợ; trả map rỗng hoặc lỗi theo contract đã định nghĩa, không quét toàn bộ dữ liệu tùy tiện.
8. Gửi index value rỗng/quá dài hoặc chứa ký tự đặc biệt; repository phải xử lý an toàn.
9. Ép hai save đồng thời và kiểm tra session record/index không bị lệch.
10. Mô phỏng lỗi sau khi ghi session nhưng trước khi cập nhật index; xác nhận transaction/repair xử lý đúng.
11. Kiểm tra restart/reconnect và cleanup stale index.
12. Chạy kiểm thử qua hai instance cùng repository để xác nhận index dùng chung.

Nếu repository hỗ trợ cả principal index và index tùy chỉnh, viết test riêng cho mỗi index và kiểm tra quy tắc chuẩn hóa. Test cần đọc lại từ repository sau mỗi thao tác thay vì chỉ kiểm tra map nội bộ trong implementation.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `findByPrincipalName` luôn rỗng | Repository không duy trì principal index hoặc SecurityContext không được resolver đọc | Kiểm tra interface, resolver và attributes sau login |
| Kết quả có session đã logout | Delete không xóa index hoặc query không xác minh session còn tồn tại | Kiểm tra reverse index, delete transaction và lazy cleanup |
| Một principal chỉ thấy một trong nhiều session | Index dùng kiểu map ghi đè thay vì tập session ID | Kiểm tra cardinality và khóa dữ liệu index |
| Session xuất hiện dưới principal cũ | Save principal mới không xóa membership cũ | So sánh index trước/sau save |
| Query principal quét toàn bộ session | Không có index vật lý hoặc query không dùng index | Kiểm tra SQL execution plan/Redis commands |
| Chỉ lỗi sau restart | Index không bền vững hoặc không được khôi phục cùng session data | Kiểm tra persistence và reconciliation |
| Kết quả khác giữa các instance | Namespace, resolver hoặc serializer khác nhau | So sánh cấu hình và phiên bản |
| Logout mọi thiết bị thiếu một số phiên | Race giữa query index và delete hoặc index stale | Kiểm tra kết quả từng delete và cơ chế retry |
| Truy vấn chậm khi principal có nhiều phiên | Không phân trang, tải full session attributes hoặc thiếu index DB | Dùng projection, giới hạn kết quả và tối ưu index |

Không log toàn bộ session object để chẩn đoán. Ghi loại index, thời gian truy vấn, số kết quả, số stale membership và trạng thái cleanup; che principal/session ID nếu metric hoặc log có thể được truy cập rộng.

## 19. Khi nào repository tùy chỉnh nên hỗ trợ interface này?

Nên triển khai `FindByIndexNameSessionRepository` khi ứng dụng cần các tích hợp hoặc nghiệp vụ phụ thuộc truy vấn theo principal, ví dụ quản lý phiên người dùng, concurrent session control hoặc logout nhiều thiết bị. Nếu repository chỉ phục vụ một ứng dụng nhỏ không có truy vấn index, có thể giữ `SessionRepository` cơ bản và tránh chi phí duy trì index.

Trước khi thêm interface, hãy xác định:

- Index nào thực sự cần hỗ trợ?
- Ai tạo và xác minh index value?
- Dữ liệu index nằm ở đâu và được cập nhật nguyên tử thế nào?
- Cách xử lý principal thay đổi, session delete và expiration?
- Có hỗ trợ phân trang hoặc giới hạn số kết quả không?
- Cách phục hồi index stale hoặc thiếu là gì?
- Có tương thích với `SpringSessionBackedSessionRegistry` không?
- Nếu là WebFlux, cần triển khai reactive interface nào?

## 20. Quy trình triển khai

1. Xác định use case cần tìm session theo principal hoặc index khác.
2. Chọn interface đồng bộ hoặc reactive phù hợp stack.
3. Dùng `PRINCIPAL_NAME_INDEX_NAME` và resolver thích hợp cho principal.
4. Thiết kế bảng phụ hoặc Redis Set/structure có index ngược theo session ID.
5. Cập nhật session record và index trong cùng transaction/atomic operation khi có thể.
6. Xóa index khi session bị xóa, hết hạn hoặc principal thay đổi.
7. Lọc session hết hạn ngay khi query và dọn membership stale theo batch.
8. Bảo vệ endpoint tra cứu, giới hạn kết quả và không trả attributes nhạy cảm.
9. Kiểm thử nhiều session cùng principal, principal change, delete, expiry, concurrency và multi-instance.
10. Theo dõi query latency, index cardinality, stale entries và lỗi repair.

## 21. Tài liệu chính thức để đối chiếu

API và implementation có thể thay đổi theo phiên bản Spring Session. Khi viết repository tùy chỉnh, đối chiếu Javadoc và tài liệu của đúng phiên bản:

- [FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [IndexResolver API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/IndexResolver.html)
- [SpringSessionBackedSessionRegistry API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/security/SpringSessionBackedSessionRegistry.html)
- [Spring Session — Redis indexed repository](https://docs.spring.io/spring-session/reference/configuration/redis.html)

`FindByIndexNameSessionRepository` mở rộng khả năng của `SessionRepository` bằng truy vấn theo index, đặc biệt là principal name. Repository tùy chỉnh phải duy trì index xuyên suốt create, save, principal change, delete và expiration; nếu không, danh sách session và chức năng thu hồi có thể sai. Hãy thiết kế index như một phần dữ liệu cần nhất quán với session chính, bảo vệ truy vấn theo principal và kiểm thử các lịch đồng thời cũng như lỗi một phần trước khi dùng nó cho quản lý phiên hoặc concurrent session control.
