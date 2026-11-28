# Đọc không trả về phiên đã hết hạn và xử lý định danh không tồn tại

Custom Spring Session repository phải phân biệt rõ dữ liệu session còn hợp lệ, session đã hết hạn và định danh session không tồn tại. Theo contract của Spring Session, thao tác tìm phiên theo ID trả về session khi tìm thấy phiên còn hợp lệ; nếu ID không có bản ghi hoặc phiên đã hết hạn thì kết quả là không có session (thông thường là null). Hai trường hợp này giống nhau đối với request đang cần khôi phục phiên, nhưng có thể khác nhau khi chẩn đoán và dọn dữ liệu.

Một repository đúng không được trả về object session đã hết hạn chỉ vì bản ghi vẫn còn trong Redis hoặc database. TTL/cleanup có thể chạy trễ, key có thể còn tồn tại trong một khoảng ngắn, hoặc một định danh có thể đã bị xóa nhưng vẫn được client gửi lại. Vì vậy, việc kiểm tra hết hạn phải được thực hiện ở đường đọc, không chỉ dựa vào tác vụ dọn dữ liệu nền. Đồng thời, lỗi kết nối datastore phải được phân biệt với kết quả không tìm thấy; nếu biến lỗi hạ tầng thành null, ứng dụng có thể coi người dùng đã đăng xuất và tạo phiên mới mà không nhận ra kho session đang gặp sự cố.

## 1. Contract của SessionRepository khi tìm theo ID

Spring Session định nghĩa repository contract với các thao tác cơ bản:

- Tạo một session mới.
- Lưu session đã thay đổi.
- Tìm session theo ID.
- Xóa session theo ID.

Trong API SessionRepository, phương thức tìm theo ID trả về session nếu repository tìm thấy phiên hợp lệ, và trả về null nếu không tìm thấy. Custom repository cần tuân thủ semantics đó. Không nên ném exception nghiệp vụ chỉ vì client gửi một session ID không còn tồn tại; đây là tình huống bình thường trong vòng đời HTTP.

Một cách diễn giải:

| Trạng thái trong kho | Kết quả findById |
| --- | --- |
| ID hợp lệ, session chưa hết hạn | Trả về session |
| Không có bản ghi cho ID | Trả về null |
| Bản ghi còn tồn tại nhưng session đã hết hạn | Trả về null |
| Bản ghi hỏng hoặc không deserialize được | Báo lỗi dữ liệu/hạ tầng theo chính sách, không giả thành session hợp lệ |
| Redis/database không truy cập được | Ném hoặc truyền lỗi repository; không coi là cache miss thông thường |

Phân biệt này quan trọng với SessionRepositoryFilter. Filter dùng repository để khôi phục HttpSession từ session ID trong request. Nếu repository trả về null, request được xử lý như không có phiên cũ; khi ứng dụng gọi getSession() thì có thể tạo session mới. Nếu repository trả về một phiên đã hết hạn, filter có thể khôi phục trạng thái xác thực hoặc attributes mà lẽ ra đã bị thu hồi.

## 2. Session ID là định danh opaque

Session ID thường được gửi trong cookie và hoạt động như bearer credential. Client có thể gửi ID cũ, ID bị sửa, ID đã bị thu hồi hoặc một chuỗi không hợp lệ. Repository không nên giả định ID đến từ một client đáng tin cậy.

Các nguyên tắc:

- Xem ID là chuỗi opaque; không suy luận user ID, quyền hoặc dữ liệu nghiệp vụ từ nội dung của nó.
- Kiểm tra định dạng/độ dài tối đa nếu backend cần giới hạn input.
- Dùng parameterized SQL khi ID được dùng trong truy vấn JDBC.
- Không nối trực tiếp ID vào đường dẫn file hoặc câu lệnh datastore.
- Không log session ID đầy đủ; dùng correlation ID hoặc fingerprint an toàn nếu cần điều tra.
- Không trả lý do chi tiết cho client để tránh tạo oracle giúp dò session.

ID không hợp lệ về định dạng và ID đúng định dạng nhưng không tồn tại đều nên được xử lý an toàn như không có session ở tầng HTTP. Nếu có chính sách rate limit hoặc phát hiện hành vi dò ID, triển khai ở lớp bảo vệ phù hợp mà không biến miss thông thường thành lỗi server.

## 3. Phân biệt không tồn tại với đã hết hạn

Về mặt request, cả hai trường hợp đều không thể khôi phục session. Tuy nhiên, repository và hệ thống quan sát có thể cần phân biệt:

- **Không tồn tại:** chưa từng có record, record đã bị xóa tường minh, hoặc ID sai.
- **Đã hết hạn:** record có tồn tại nhưng thời hạn idle đã qua.
- **Bị thu hồi:** record bị xóa do logout, quản trị hoặc sự kiện bảo mật.
- **Không xác định được:** datastore lỗi, timeout hoặc payload hỏng nên repository chưa thể kết luận.

Không cần tiết lộ các lý do này cho trình duyệt. Nhưng log/metric nội bộ có thể ghi số lượng theo nhóm để tìm lỗi TTL, cleanup hoặc logout. Tránh ghi chính session ID hoặc thuộc tính nhạy cảm.

Nếu repository chỉ dùng TTL tự động và không giữ metadata cho biết nguyên nhân xóa, có thể không phân biệt được một ID đã hết hạn với ID chưa từng tồn tại. Điều đó không vi phạm contract của findById; quan trọng là cả hai đều không trả session. Chỉ thêm bảng audit/tombstone nếu nghiệp vụ hoặc điều tra bảo mật thực sự cần.

## 4. Xác định thời điểm hết hạn

Session timeout thường là idle timeout. Một session có thời điểm truy cập gần nhất và khoảng không hoạt động tối đa. Thời điểm hết hạn có thể được tính theo công thức:

~~~text
expiresAt = lastAccessedTime + maxInactiveInterval
expired   = now >= expiresAt
~~~

Spring Session Session API cung cấp thông tin thời điểm truy cập, khoảng không hoạt động và phương thức isExpired(). Khi custom repository làm việc với một implementation Session tương thích, nên dùng isExpired() để tuân theo semantics của implementation thay vì tự tạo quy tắc khác nhau giữa các backend.

Nếu repository lưu expiresAt riêng, cần bảo đảm giá trị này được tính từ cùng dữ liệu thời gian và được cập nhật đúng khi session được truy cập. Dùng Instant/UTC hoặc một chuẩn thời gian nhất quán; tránh trộn local timezone giữa application node và database. Với hệ thống nhiều node, clock skew có thể làm một node cho rằng session còn hạn trong khi node khác coi đã hết hạn.

Một số điểm biên cần kiểm thử:

- Tại đúng thời điểm hết hạn, session phải được coi là hết hạn theo quy tắc đã chọn.
- Khoảng timeout bằng 0 thường làm phiên hết hạn ngay; xác minh theo implementation/phiên bản đang dùng.
- Khoảng timeout âm thường biểu thị không giới hạn idle timeout theo semantics của Session API; không tự biến nó thành một TTL âm trong datastore.
- Khi session được chạm hợp lệ, lastAccessedTime và expiresAt cần được cập nhật đồng bộ.
- Thay đổi timeout của session phải cập nhật thời điểm hết hạn được lưu.

Không dựa vào TTL vật lý duy nhất nếu datastore có thể trì hoãn việc xóa key/row. Kiểm tra logic expiration tại thời điểm đọc vẫn là lớp bảo vệ cuối cùng.

## 5. Logical expiration và physical cleanup

Hết hạn về logic và xóa vật lý là hai việc khác nhau:

- **Logical expiration:** từ thời điểm hết hạn, repository không còn được phép trả session cho request.
- **Physical cleanup:** dữ liệu hết hạn được xóa khỏi Redis/database để giải phóng bộ nhớ và dung lượng.

Redis TTL có thể tự xóa key khi hết hạn, nhưng thời điểm key bị loại khỏi bộ nhớ không nên được dùng làm lý do duy nhất để bỏ qua kiểm tra isExpired(). JDBC thường cần query có điều kiện hoặc scheduled cleanup để xóa row cũ; job cleanup có thể chạy theo chu kỳ nên row đã hết hạn vẫn tồn tại trước khi job chạy.

Một repository đúng có thể trả null cho session hết hạn ngay cả khi record vẫn còn vật lý. Cleanup nền là tối ưu dung lượng, không phải cơ chế duy nhất bảo đảm request không dùng lại session hết hạn.

## 6. Cài đặt findById theo hướng an toàn

Một custom repository thường có ba bước khi tìm session:

1. Xác thực đầu vào ở mức định dạng và giới hạn.
2. Đọc record từ store; nếu không có record thì trả null.
3. Deserialize session, kiểm tra hết hạn; nếu đã hết hạn thì không trả về và có thể dọn record theo cách an toàn.

Ví dụ minh họa, trong đó Store và StoredSession là abstraction do ứng dụng tự định nghĩa:

~~~java
@Override
public S findById(String id) {
    if (!isAcceptableSessionId(id)) {
        return null;
    }

    StoredSession stored = store.find(id);
    if (stored == null) {
        return null;
    }

    S session = deserialize(stored.payload());
    if (session.isExpired()) {
        store.deleteIfUnchanged(id, stored.version());
        return null;
    }

    return session;
}
~~~

Đây là cấu trúc minh họa, không phải một class có thể sao chép nguyên xi vào mọi dự án. deleteIfUnchanged là thao tác compare-and-delete do custom store triển khai, không phải method chuẩn của SessionRepository. Nếu backend không hỗ trợ version, có thể dùng điều kiện theo expiresAt/lastAccessedTime hoặc để cleanup nền xóa record; tránh xóa mù một record có thể vừa được request khác làm mới.

Điểm quan trọng nhất là kiểm tra hết hạn trước khi trả session. Không trả session trước rồi chỉ phát sự kiện expired hoặc chờ cleanup chạy sau đó.

## 7. Tránh race giữa đọc session hết hạn và request làm mới

Giả sử request A đọc một record mà nó thấy đã hết hạn. Gần như cùng lúc, request B có thể đang làm mới session hợp lệ theo một thao tác được chấp nhận trước thời điểm hết hạn, rồi lưu lại record. Nếu A gọi delete(id) vô điều kiện sau khi B đã ghi phiên mới, A có thể xóa nhầm session vừa được làm mới.

Đây là race giữa kiểm tra expiration và cleanup:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant D as Datastore
    A->>D: Đọc record phiên, version 7
    Note over A: A đánh giá snapshot là hết hạn
    B->>D: Lưu phiên được làm mới, version 8
    B-->>D: Ghi thành công
    A->>D: Xóa theo ID không điều kiện
    Note over D: Có thể xóa nhầm version 8
~~~

Các cách giảm rủi ro:

- Xóa có điều kiện theo version/updatedAt/expiresAt đã đọc.
- Dùng transaction hoặc compare-and-set của datastore.
- Dùng câu lệnh DELETE có điều kiện chỉ xóa row vẫn mang giá trị expiry đã quan sát.
- Không xóa đồng bộ trong findById nếu cleanup không thể thực hiện an toàn; trả null và để tác vụ cleanup xử lý.

Với Redis, có thể dùng Lua script hoặc thao tác compare-and-delete phù hợp để so sánh version/expiry và xóa trong cùng thao tác nguyên tử. Với JDBC, có thể dùng câu lệnh DELETE có điều kiện theo session ID và timestamp/version, hoặc transaction/locking theo mức cần thiết. Không giả định một chuỗi GET rồi DEL riêng rẽ là nguyên tử.

## 8. Không để save hồi sinh một session đã hết hạn

Một lỗi khác là repository xóa session hết hạn khi đọc nhưng sau đó một request cũ vẫn gọi save() với object đã tải trước đó. Nếu save() ghi lại object mà không kiểm tra trạng thái, dữ liệu có thể xuất hiện trở lại sau khi logout hoặc expiration.

Custom repository cần xác định rõ semantics của save:

- Nếu session đã hết hạn theo trạng thái được lưu và không có access hợp lệ làm mới nó, không được ghi nó trở lại như một phiên mới.
- Nếu request hợp lệ đã cập nhật lastAccessedTime theo lifecycle của Spring Session, việc lưu phải phản ánh thời gian mới và timeout tương ứng.
- Nếu record đã bị thu hồi hoặc ID đã bị rotate, không được để snapshot cũ tạo lại phiên với ID cũ.
- Nếu cần ngăn stale write, dùng version/compare-and-set hoặc quy tắc cập nhật có điều kiện.

Ví dụ minh họa:

~~~java
@Override
public void save(S session) {
    if (session.isExpired()) {
        store.deleteIfCurrent(session.getId(), session.getLastAccessedTime());
        return;
    }

    StoredSession stored = serialize(session);
    store.save(stored);
}
~~~

Điều kiện deleteIfCurrent ở đây là ví dụ cho custom store; không phải API Spring Session. Một repository thực tế cần xác định cách request touch session và thời điểm save theo Spring Session integration. Không nên tự thêm logic làm mới TTL trong mọi lần gọi findById, vì truy vấn quản trị hoặc tác vụ nền có thể vô tình kéo dài session.

## 9. ID không tồn tại không được tạo session ngầm

findById chỉ là thao tác tìm. Nếu ID không tồn tại, repository phải trả null. Không tạo session mới trong findById và không thay thế ID đã gửi bằng một session mới ở bên trong repository.

Việc tạo session thuộc thao tác createSession hoặc do Servlet request gọi getSession() khi cần. Phân tách rõ hai trách nhiệm giúp tránh các lỗi:

- Request chỉ muốn kiểm tra session hiện tại nhưng repository lại tạo phiên mới.
- ID sai tạo ra nhiều session rác.
- Client gửi một ID không tồn tại nhưng repository vô tình gắn nó với một phiên mới.
- Các request không xác thực làm tăng số session và dung lượng store.

Trong Servlet API:

- getSession(false) trả null nếu request không có session hợp lệ.
- getSession() có thể tạo session mới nếu chưa có session hợp lệ.

Do đó, controller/filter cần dùng đúng biến thể. Dùng getSession() trong endpoint kiểm tra trạng thái có thể tạo session mới và làm sai kết quả đo. Với Spring Session, request wrapper phối hợp repository để khôi phục hoặc tạo session theo các API này.

## 10. Xử lý định danh không tồn tại và cookie cũ

Trình duyệt có thể gửi cookie session ID đã hết hạn hoặc đã bị xóa phía server. Đây là hành vi bình thường: browser không tự biết session record đã bị thu hồi. Ứng dụng cần coi ID đó như không có phiên, đồng thời có thể yêu cầu resolver hết hạn cookie cũ trong response theo integration đang dùng.

Không coi cookie có mặt là bằng chứng người dùng đã đăng nhập. Phải khôi phục session từ repository và xác minh trạng thái xác thực. Nếu session không tồn tại, request bảo vệ phải tiếp tục qua quy trình authentication phù hợp; không khôi phục principal từ cookie hoặc dữ liệu client khác.

Một số tình huống:

| Request | Hành vi mong đợi |
| --- | --- |
| Không có cookie session | Không có session; chỉ tạo mới nếu ứng dụng yêu cầu |
| Có cookie với ID không tồn tại | Không khôi phục session; có thể xóa cookie cũ |
| Có cookie với ID đã hết hạn | Không khôi phục session; xử lý như không có phiên |
| Có cookie với ID bị logout/invalidate | Không khôi phục session đã thu hồi |
| Có cookie hợp lệ | Khôi phục session từ repository |
| Repository không truy cập được | Báo lỗi hạ tầng; không coi như ID không tồn tại |

Không tiết lộ cho client rằng ID cụ thể từng tồn tại hay bị thu hồi. Response nên giữ semantics nhất quán để tránh tạo session enumeration oracle.

## 11. Phân biệt cache miss với lỗi datastore

Đây là một trong những quy tắc quan trọng nhất của custom repository. Kết quả null có nghĩa repository đã thực hiện truy vấn và xác định không có session hợp lệ. Nó không có nghĩa Redis/database đang lỗi nên không thể kiểm tra.

Ví dụ xử lý sai:

~~~java
try {
    return store.find(id);
}
catch (RuntimeException ex) {
    return null;
}
~~~

Đoạn mã trên biến mọi lỗi thành session miss. Nếu Redis mất kết nối, mọi request có thể bị xem như chưa đăng nhập; request tiếp theo có thể tạo session mới, làm mất trạng thái và che giấu sự cố. Với endpoint cần authentication, hành vi này có thể dẫn đến fail-open nếu ứng dụng xử lý không đúng.

Hành vi nên có:

- Không có record: trả null.
- Record hết hạn: trả null.
- ID sai định dạng: trả null hoặc kết quả miss theo contract và policy.
- Serialization/data corruption: báo lỗi rõ ràng, ghi metric và xử lý theo error policy.
- Timeout/connection failure: ném exception repository phù hợp hoặc để tầng tích hợp xử lý lỗi 5xx.
- Không retry vô hạn trong request thread.

Fail closed có nghĩa request không được tiếp tục như đã xác thực khi không thể xác minh session. Tuy nhiên, cũng không nên âm thầm coi tất cả người dùng đã logout; cần quan sát và trả lỗi dịch vụ phù hợp khi datastore unavailable.

## 12. Xóa session theo ID phải idempotent

deleteById thường được gọi khi logout, session fixation hoặc cleanup. Nếu ID không tồn tại hoặc đã bị xóa, thao tác xóa lần nữa nên an toàn và không làm hỏng request chỉ vì không có record.

Idempotent delete có nghĩa:

- Xóa một ID đang tồn tại: session bị xóa.
- Xóa cùng ID lần thứ hai: không còn gì để xóa, thao tác vẫn hoàn tất an toàn.
- Xóa ID chưa từng tồn tại: không tạo record và không gây lỗi nghiệp vụ.
- Xóa ID đã hết hạn: có thể no-op hoặc dọn record vật lý nếu còn.

Với JDBC, DELETE theo primary key thường trả số hàng bị xóa; số hàng bằng 0 là kết quả hợp lệ. Với Redis, DEL trả 0 nếu key không tồn tại; không nên coi đó là lỗi. Nếu cần xóa index phụ hoặc expiration metadata, thao tác dọn cần nhất quán và có thể retry.

## 13. Thiết kế lưu expiry trong Redis

Một custom Redis repository có thể lưu session data trong key có TTL. Khi tạo/lưu session, repository tính TTL từ maxInactiveInterval và lastAccessedTime hoặc dùng expiresAt được lưu rõ ràng. Khi session được truy cập hợp lệ, thời hạn cần được cập nhật theo lifecycle của session.

Các lưu ý:

- TTL phải gắn với đúng session key hoặc record tương ứng.
- Nếu session có nhiều key phụ, cần quy tắc dọn index/metadata.
- TTL không thay thế kiểm tra isExpired() khi đọc.
- TTL bằng 0/âm phải được xử lý theo semantics session, không truyền máy móc thành lệnh EXPIRE.
- Nếu dùng nhiều lệnh để ghi payload và TTL, cần tránh trạng thái payload tồn tại mà không có TTL do lệnh thứ hai thất bại.
- Dùng transaction/Lua hoặc cách ghi phù hợp nếu cần cập nhật payload và expiration cùng nhau.

Ví dụ khái niệm:

~~~text
session key: app:sessions:{id}
payload: serialized Session
ttl: remaining inactivity interval
~~~

Không dùng tên key ví dụ như một contract cố định của Spring Session. Key format thực tế thuộc implementation. Không thao tác trực tiếp key nội bộ từ code nghiệp vụ.

## 14. Thiết kế expiry trong JDBC

Với JDBC, record session thường chứa creation time, last access time và max inactive interval. Custom repository có thể tính expiry trong truy vấn:

~~~sql
SELECT SESSION_ID, CREATION_TIME, LAST_ACCESS_TIME,
       MAX_INACTIVE_INTERVAL, SESSION_ATTRIBUTES
FROM APP_SESSION
WHERE SESSION_ID = ?
  AND (
      MAX_INACTIVE_INTERVAL < 0
      OR LAST_ACCESS_TIME + MAX_INACTIVE_INTERVAL > CURRENT_TIMESTAMP
  );
~~~

SQL trên chỉ là minh họa vì cách cộng interval và kiểu cột khác nhau giữa PostgreSQL, MySQL, SQL Server và các database khác. Có thể thay bằng cột EXPIRES_AT được cập nhật cùng last access time:

~~~sql
SELECT SESSION_ID, PAYLOAD, EXPIRES_AT, VERSION
FROM APP_SESSION
WHERE SESSION_ID = ?
  AND (EXPIRES_AT IS NULL OR EXPIRES_AT > CURRENT_TIMESTAMP);
~~~

Nếu query không trả row, repository trả null. Scheduled cleanup có thể xóa các row hết hạn theo batch:

~~~sql
DELETE FROM APP_SESSION
WHERE EXPIRES_AT IS NOT NULL
  AND EXPIRES_AT <= CURRENT_TIMESTAMP;
~~~

Trong hệ thống lớn, cleanup nên chạy theo batch có giới hạn và index phù hợp trên EXPIRES_AT. Không xóa hàng loạt toàn bảng trong mỗi request. Cần bảo đảm timezone/clock và cách cập nhật expiresAt thống nhất giữa các application node.

## 15. Dùng thời gian nhất quán và tránh clock skew

Nếu application node A và B có clock lệch nhau, cùng một session có thể được coi là hết hạn ở node này nhưng còn hạn ở node khác. Có hai hướng:

- Dùng clock đồng bộ bằng NTP và theo dõi độ lệch giữa node.
- Để datastore/database làm nguồn thời gian cho expiresAt/expiry query nếu thiết kế phù hợp.

Không trộn Instant từ JVM với timestamp local của database mà không quy định timezone. Ưu tiên UTC và kiểu dữ liệu có semantics rõ ràng. Nếu dùng database current timestamp để lọc, mọi node sẽ dựa vào cùng clock database; nếu dùng application clock, bảo đảm node đồng bộ và có test cho clock skew.

Trong unit test, nên có thể kiểm soát clock hoặc tạo session với timestamp xác định. Tránh chờ thật nhiều phút để kiểm tra timeout; dùng test clock hoặc timeout ngắn có giới hạn và xác minh thời điểm biên.

## 16. Race giữa expiration và refresh

Một request có thể bắt đầu ngay trước khi session hết hạn. Nếu request được chấp nhận, Spring Session integration có thể cập nhật lastAccessedTime theo lifecycle request. Một tác vụ cleanup chạy đồng thời có thể nhìn thấy giá trị cũ và xóa record trước khi thay đổi mới được lưu.

Để giảm race:

- Xác định điểm linearization của thao tác touch/save.
- Cập nhật lastAccessedTime và expiresAt trong cùng transaction hoặc thao tác nguyên tử khi có thể.
- Cleanup chỉ xóa row/key còn hết hạn tại thời điểm xóa, không xóa dựa trên snapshot cũ.
- Dùng version hoặc compare-and-set nếu request có thể cập nhật đồng thời.
- Kiểm thử request bắt đầu sát thời điểm expiry và cleanup chạy đồng thời.

Không kéo dài session chỉ vì một tiến trình background đọc record để báo cáo. Chỉ hoạt động được xem là activity theo chính sách mới làm mới idle timeout.

## 17. Xử lý payload hỏng hoặc phiên bản dữ liệu không tương thích

Nếu record có nhưng deserialize thất bại, không nên trả một session rỗng rồi tiếp tục như thể người dùng chưa đăng nhập mà không ghi nhận lỗi. Payload hỏng có thể là dấu hiệu serializer không tương thích, deploy lệch phiên bản, dữ liệu bị cắt hoặc lỗi bảo mật.

Chính sách cần xác định:

- Ghi metric/log về deserialize failure nhưng không ghi payload/session ID.
- Không trả object session một phần hoặc mặc định authentication.
- Có thể xóa record hỏng nếu chắc chắn không thể khôi phục, nhưng nên cân nhắc audit/diagnostic trước khi xóa.
- Trả lỗi phù hợp hoặc yêu cầu xác thực lại theo error policy.
- Giữ serializer và DTO contract tương thích trong rolling deployment.

Đối với session data quan trọng cho trải nghiệm, có thể lưu dữ liệu nghiệp vụ trong database riêng để có khả năng phục hồi khi session bị xóa hoặc không deserialize được.

## 18. Kiểm thử contract của custom repository

Nên viết bộ contract test độc lập cho mọi implementation custom. Cùng một test suite có thể chạy trên Redis store, JDBC store hoặc in-memory store để xác nhận semantics thống nhất.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| findById với ID hợp lệ | Trả đúng session và attributes |
| findById với ID chưa từng tồn tại | Trả null |
| findById với ID sai định dạng | Không khôi phục session; không gây lỗi bất ngờ |
| findById với session đã hết hạn | Trả null ngay cả khi record còn vật lý |
| findById sau deleteById | Trả null |
| deleteById hai lần | An toàn, idempotent |
| save session còn hạn | Lưu và khôi phục được |
| save session đã hết hạn | Không hồi sinh session đã hết hạn |
| TTL hết hạn nhưng cleanup chưa chạy | findById vẫn trả null |
| Store timeout/connection failure | Lỗi hạ tầng được truyền/quan sát, không biến thành null |
| Payload deserialize lỗi | Lỗi dữ liệu được xử lý theo policy, không trả session giả |
| Refresh đồng thời cleanup | Không xóa nhầm session vừa được làm mới |
| Hai node dùng cùng store | Kết quả lookup và expiry nhất quán theo cấu hình |

Ví dụ cấu trúc test:

~~~java
@Test
void findByIdReturnsNullWhenSessionIsExpired() {
    Session session = repository.createSession();
    session.setMaxInactiveInterval(Duration.ofSeconds(1));
    session.setLastAccessedTime(Instant.now().minusSeconds(5));
    repository.save(session);

    Session found = repository.findById(session.getId());

    assertThat(found).isNull();
}
~~~

Đây là test minh họa; kiểu session cụ thể và cách đặt thời gian cần khớp implementation đang dùng. Một số repository có thể chuẩn hóa timeout hoặc thời điểm lưu. Để tránh flaky test, dùng Clock có thể điều khiển nếu custom implementation hỗ trợ, hoặc đặt timestamp rõ ràng thay vì sleep.

## 19. Kiểm thử qua SessionRepositoryFilter và HTTP

Contract test của repository chưa đủ để chứng minh request thực tế xử lý cookie đúng. Cần integration test qua Servlet filter:

1. Gửi request không có cookie tới endpoint chỉ kiểm tra session bằng getSession(false); xác minh không có session mới.
2. Gửi request tạo session; lấy cookie từ response.
3. Xóa session trực tiếp qua repository test API hoặc đợi expiry có kiểm soát.
4. Gửi lại cookie cũ; xác minh request không khôi phục session cũ.
5. Gọi getSession(false); xác minh trả null nếu ứng dụng không tạo session mới.
6. Gọi endpoint cần session mới; xác minh ID mới được phát, không tái sử dụng ID cũ.
7. Mô phỏng datastore unavailable; xác minh ứng dụng không coi lỗi là một miss bình thường.

Không ghi cookie hoặc session ID đầy đủ ra test report. Có thể kiểm tra cookie jar trong bộ nhớ và chỉ assert rằng ID thay đổi/được xóa mà không in giá trị.

## 20. Quan sát production

Các metric có ích:

- Số lookup hit, miss, expired và invalid-format theo nhóm.
- Tỷ lệ session hết hạn được phát hiện khi đọc so với cleanup nền.
- Số lỗi deserialize và lỗi datastore.
- Latency findById, save và deleteById.
- Số lần cleanup conditional delete không xóa được do version thay đổi.
- Số request tạo session mới sau khi cookie cũ không hợp lệ.
- Chênh lệch giữa số session logic còn hạn và số record vật lý trong store.

Không đưa session ID hoặc principal nhạy cảm làm metric label vì cardinality cao và rò rỉ thông tin. Ghi nhận node ID, repository type, exception class và correlation ID đã được bảo vệ.

Khi thấy nhiều session miss bất thường, phân biệt người dùng gửi cookie cũ với repository unavailable, namespace sai hoặc lỗi serializer. Nếu chỉ theo dõi số lượng null mà không theo dõi lỗi datastore, một sự cố Redis/JDBC có thể bị hiểu nhầm là hàng loạt người dùng đăng xuất.

## 21. Quy trình triển khai custom repository

1. Xác định contract findById phải trả session, null hay lỗi ở từng tình huống.
2. Dùng Session API isExpired() hoặc một quy tắc expiry tương thích và thống nhất.
3. Thiết kế lưu lastAccessedTime, maxInactiveInterval và expiresAt/TTL.
4. Kiểm tra expiration ở đường đọc; không phụ thuộc hoàn toàn vào cleanup nền.
5. Trả null cho ID không tồn tại hoặc session hết hạn.
6. Phân biệt miss với datastore timeout, serialization failure và lỗi schema.
7. Làm deleteById idempotent.
8. Ngăn save stale snapshot làm hồi sinh session đã hết hạn/thu hồi.
9. Dùng compare-and-delete hoặc transaction để tránh cleanup xóa nhầm phiên vừa refresh.
10. Viết contract test, HTTP integration test và test race trên đúng backend.
11. Theo dõi hit/miss/expired/error và bảo vệ session ID trong log.

## 22. Checklist

- [ ] findById trả null cho ID không tồn tại.
- [ ] findById trả null cho session đã hết hạn dù record còn vật lý.
- [ ] Repository không tạo session mới trong thao tác tìm.
- [ ] Expiration dựa trên lastAccessTime và maxInactiveInterval theo semantics thống nhất.
- [ ] TTL/cleanup chỉ là physical cleanup; đường đọc vẫn kiểm tra logic expiry.
- [ ] Clock/timezone nhất quán giữa các application node và datastore.
- [ ] deleteById an toàn khi ID không tồn tại và có thể gọi lặp.
- [ ] save không hồi sinh session cũ đã hết hạn hoặc bị thu hồi.
- [ ] Cleanup không xóa nhầm session vừa được request khác làm mới.
- [ ] Datastore unavailable không bị biến thành session miss.
- [ ] Payload hỏng/serializer mismatch được phát hiện và xử lý có kiểm soát.
- [ ] HTTP test gửi lại cookie cũ và xác minh session không được khôi phục.
- [ ] Log/metric không làm lộ session ID, cookie hoặc session attributes.

Custom Spring Session repository phải coi session hết hạn và định danh không tồn tại là hai trường hợp không thể khôi phục, nên findById trả null cho cả hai. Nhưng repository vẫn phải phân biệt chúng với lỗi datastore hoặc dữ liệu hỏng. Kiểm tra expiry ngay khi đọc, dùng cleanup an toàn trước race với refresh, không tạo phiên trong thao tác tìm và không cho save cũ hồi sinh session đã thu hồi. Khi contract này được kiểm thử ở cả tầng repository lẫn HTTP filter, ứng dụng sẽ xử lý cookie cũ và session hết hạn nhất quán trên mọi instance.
