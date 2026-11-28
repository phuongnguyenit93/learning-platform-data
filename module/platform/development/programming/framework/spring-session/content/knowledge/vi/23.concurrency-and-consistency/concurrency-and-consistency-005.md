# Đọc, kiểm tra rồi ghi không tự trở thành một giao dịch nguyên tử

Một request thường thực hiện ba bước trên trạng thái phiên: đọc giá trị hiện tại, kiểm tra điều kiện rồi ghi giá trị mới. Ba bước này nhìn giống một thao tác đơn giản, nhưng không tự động trở thành một giao dịch nguyên tử. Khi hai request cùng sử dụng một session, chúng có thể đọc cùng một giá trị cũ, cùng vượt qua điều kiện kiểm tra rồi ghi đè kết quả của nhau.

Spring Session giúp nhiều request và nhiều instance truy cập cùng một phiên qua repository dùng chung như Redis hoặc JDBC. Việc chia sẻ dữ liệu này không có nghĩa repository tự tuần tự hóa toàn bộ logic nghiệp vụ của ứng dụng. Nếu một quy tắc cần được bảo đảm nguyên tử, ứng dụng phải chọn cơ chế đồng bộ phù hợp ở nơi lưu dữ liệu có thẩm quyền.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích race condition trong chuỗi read-check-write.
- Nhận biết lost update và kiểm tra điều kiện dựa trên dữ liệu đã cũ.
- Phân biệt thao tác ghi nguyên tử với một quy trình nhiều bước.
- Hiểu vì sao session dùng chung không đồng nghĩa với khóa hoặc transaction cho mọi request.
- Chọn atomic SQL, optimistic locking, pessimistic locking hoặc Redis atomic operation theo tình huống.
- Thiết kế kiểm thử đồng thời trên nhiều request và nhiều instance.

## 1. Chuỗi read-check-write gồm những bước nào?

Giả sử session chứa số lượt thử còn lại. Mỗi request muốn giảm số lượt nếu giá trị vẫn lớn hơn 0:

1. Đọc `remainingAttempts` từ session.
2. Kiểm tra `remainingAttempts > 0`.
3. Ghi `remainingAttempts - 1` trở lại session.

Nếu chỉ có một request chạy tại một thời điểm, kết quả có vẻ đúng. Nhưng trình duyệt có thể gửi nhiều request đồng thời: người dùng mở hai tab, double-click nút, frontend phát request song song hoặc client retry khi mạng chập chờn.

Ví dụ session ban đầu có `remainingAttempts = 1`:

~~~text
Request A                         Request B
---------                         ---------
Đọc giá trị 1
                                  Đọc giá trị 1
Kiểm tra 1 > 0: đúng
                                  Kiểm tra 1 > 0: đúng
Ghi giá trị 0
                                  Ghi giá trị 0

Kết quả: cả A và B đều nghĩ mình đã dùng lượt cuối.
Giá trị lưu cuối cùng là 0, nhưng quy tắc "chỉ một request được dùng lượt cuối"
đã bị vi phạm.
~~~

Vấn đề không nằm ở phép trừ. Vấn đề là việc đọc, kiểm tra và ghi không được thực hiện như một đơn vị nguyên tử.

## 2. Lost update: một request ghi đè kết quả của request khác

Một ví dụ phổ biến là bộ đếm:

~~~java
HttpSession session = request.getSession();

Integer count = (Integer) session.getAttribute("viewCount");
if (count == null) {
    count = 0;
}

session.setAttribute("viewCount", count + 1);
~~~

Giả sử hai request cùng đọc `viewCount = 10`:

| Thời điểm | Request A | Request B |
|---|---|---|
| T1 | Đọc 10 | |
| T2 | | Đọc 10 |
| T3 | Tính 11 | |
| T4 | | Tính 11 |
| T5 | Ghi 11 | |
| T6 | | Ghi 11 |

Kết quả cuối cùng là 11, trong khi có hai request hợp lệ nên kết quả mong muốn là 12. Cập nhật của một request đã bị mất. Đây là lost update.

Với Spring Session, cả hai request có thể cùng tải một snapshot của session. Việc repository dùng chung cho nhiều instance chỉ bảo đảm các node truy cập cùng kho dữ liệu; nó không tự biến đoạn code Java trên thành một phép tăng nguyên tử.

## 3. Kiểm tra điều kiện trên dữ liệu cũ

Race condition nguy hiểm hơn khi điều kiện kiểm tra liên quan tới giới hạn hoặc quyền sử dụng:

~~~java
Integer seats = (Integer) session.getAttribute("availableSeats");

if (seats != null && seats > 0) {
    session.setAttribute("availableSeats", seats - 1);
    return "Đã giữ chỗ";
}

return "Hết chỗ";
~~~

Hai request có thể cùng thấy còn một chỗ, cùng trả về “Đã giữ chỗ” và cùng ghi số chỗ còn lại bằng 0. Hệ thống đã xác nhận hai người trong khi chỉ có một chỗ.

Các biến thể tương tự:

- Hai request cùng kiểm tra mã khuyến mại còn lượt sử dụng.
- Hai tab cùng kiểm tra người dùng chưa vượt giới hạn phiên hoặc lượt thao tác.
- Hai request cùng kiểm tra trạng thái đơn hàng là `PENDING` trước khi xác nhận.
- Một request kiểm tra quyền trong session, request khác đồng thời thu hồi hoặc thay đổi quyền.
- Hai request cùng cập nhật bước tiếp theo của một quy trình.

Nếu điều kiện quyết định một quy tắc nghiệp vụ, việc kiểm tra phải được thực hiện cùng thao tác cập nhật tại nơi lưu dữ liệu có thẩm quyền. Chỉ kiểm tra trong Java rồi ghi session sau đó là chưa đủ.

## 4. Vì sao Spring Session không tự cung cấp atomicity cho logic ứng dụng?

Spring Session cung cấp abstraction để tạo, tìm, lưu và xóa session. API `HttpSession` giúp ứng dụng đọc/ghi thuộc tính; repository chịu trách nhiệm lưu trạng thái phiên theo implementation đang dùng.

Các bảo đảm sau không tương đương nhau:

| Khả năng | Ý nghĩa | Có tự bảo đảm chuỗi read-check-write không? |
|---|---|---|
| Session repository dùng chung | Các instance đọc/ghi cùng kho session | Không |
| Một lệnh ghi đơn lẻ | Một thao tác lưu được repository thực hiện theo semantics của store | Không bảo vệ các bước đọc và kiểm tra trước đó |
| Transaction JDBC | Nhóm thao tác database nằm trong transaction | Chỉ khi toàn bộ đọc, kiểm tra và ghi tham gia cùng transaction với mức cô lập phù hợp |
| Redis command nguyên tử | Một lệnh Redis được thực hiện như một đơn vị không xen kẽ với lệnh khác | Có thể bảo vệ phép cập nhật đơn lẻ, không tự bao trùm code Java nhiều bước |
| Distributed lock | Các tiến trình phối hợp để chỉ một bên vào vùng tới hạn | Có thể tuần tự hóa vùng code nếu lock được triển khai đúng và mọi bên cùng tuân thủ |

Ví dụ `session.setAttribute("viewCount", count + 1)` chỉ gửi một giá trị đã tính ở phía ứng dụng. Repository không thể suy ra rằng giá trị này được tính từ snapshot cũ hoặc cần cộng thêm một đơn vị vào giá trị mới nhất.

Các chi tiết lưu trữ của Spring Session có thể khác giữa JDBC và Redis, giữa repository tiêu chuẩn và repository tùy chỉnh, cũng như giữa các phiên bản. Không nên dựa vào cấu trúc key, câu SQL hoặc cách ghi field nội bộ để suy ra một bảo đảm đồng thời không được API cam kết.

## 5. Session nên giữ trạng thái điều hướng, không làm kho dữ liệu nghiệp vụ

Session phù hợp với dữ liệu nhỏ, tạm thời và gắn với tương tác của một client, ví dụ:

- Ngôn ngữ hoặc lựa chọn giao diện.
- ID giỏ hàng hoặc ID quy trình đang thực hiện.
- Thông báo flash sau redirect.
- Trạng thái điều hướng có thể tái tạo.

Các dữ liệu như số dư, số chỗ còn lại, tồn kho, số lượt khuyến mại, trạng thái thanh toán hoặc trạng thái đơn hàng cần nằm trong database nghiệp vụ hoặc một hệ thống có cơ chế cập nhật nguyên tử.

Ví dụ, thay vì lưu số chỗ còn lại trong session:

~~~java
// Không dùng session làm nguồn có thẩm quyền cho số chỗ còn lại.
Integer remaining = (Integer) session.getAttribute("remainingSeats");
~~~

Hãy lưu `remainingSeats` trong bảng nghiệp vụ và dùng một câu lệnh cập nhật có điều kiện. Session chỉ có thể giữ `reservationId` sau khi thao tác giữ chỗ thành công.

## 6. Giải pháp 1: cập nhật có điều kiện trong một câu SQL

Nếu dữ liệu có thẩm quyền nằm trong database quan hệ, cách đơn giản và mạnh thường là đưa điều kiện vào chính câu lệnh cập nhật:

~~~sql
UPDATE EVENT_SEAT
SET AVAILABLE = AVAILABLE - 1
WHERE EVENT_ID = :eventId
  AND AVAILABLE > 0;
~~~

Database thực hiện câu lệnh cập nhật như một thao tác nguyên tử đối với hàng được tác động. Ứng dụng kiểm tra số hàng bị cập nhật:

- `1`: giữ được một chỗ.
- `0`: không còn chỗ hoặc không tìm thấy sự kiện phù hợp.

Ví dụ service:

~~~java
@Transactional
public boolean reserveSeat(long eventId) {
    int updated = jdbcTemplate.update("""
            UPDATE EVENT_SEAT
            SET AVAILABLE = AVAILABLE - 1
            WHERE EVENT_ID = ?
              AND AVAILABLE > 0
            """, eventId);

    return updated == 1;
}
~~~

Đây là mẫu minh họa với `JdbcTemplate`. Cú pháp text block yêu cầu Java 15 trở lên; với Java thấp hơn, dùng chuỗi SQL thông thường. Nếu việc giữ chỗ cần tạo reservation record, thao tác tạo bản ghi và cập nhật số lượng phải nằm trong cùng transaction nghiệp vụ.

Một câu SQL khác có thể dùng để tăng bộ đếm:

~~~sql
UPDATE USER_COUNTER
SET VALUE = VALUE + 1
WHERE USER_ID = :userId;
~~~

Không cần đọc giá trị cũ về Java rồi cộng một. Database thực hiện phép tăng trên giá trị hiện tại trong câu lệnh cập nhật.

## 7. Giải pháp 2: optimistic locking bằng version

Khi cần đọc object, kiểm tra nhiều trường rồi ghi lại, optimistic locking có thể phát hiện request dùng snapshot cũ.

Một bảng có thể có cột `VERSION`:

~~~sql
CREATE TABLE WORKFLOW_STATE (
    ID BIGINT PRIMARY KEY,
    STATUS VARCHAR(30) NOT NULL,
    VERSION BIGINT NOT NULL
);
~~~

Ứng dụng đọc trạng thái cùng version, ví dụ `STATUS=PENDING`, `VERSION=7`. Khi cập nhật:

~~~sql
UPDATE WORKFLOW_STATE
SET STATUS = 'APPROVED',
    VERSION = VERSION + 1
WHERE ID = :id
  AND VERSION = :expectedVersion
  AND STATUS = 'PENDING';
~~~

Nếu chỉ một request cập nhật được version 7, request đó đổi version thành 8. Request khác vẫn dùng version 7 sẽ cập nhật 0 hàng và biết snapshot của nó đã cũ. Ứng dụng có thể tải lại trạng thái và trả lỗi xung đột hoặc thử lại theo chính sách.

Với JPA, `@Version` hỗ trợ optimistic locking:

~~~java
@Entity
public class WorkflowState {

    @Id
    private Long id;

    @Version
    private long version;

    private String status;
}
~~~

Khi hai transaction cùng cập nhật một entity, provider kiểm tra version. Một transaction có thể nhận `OptimisticLockException` hoặc exception tương ứng nếu version đã thay đổi.

Optimistic locking phù hợp khi xung đột không thường xuyên và không muốn khóa hàng trong suốt quá trình xử lý. Nó cần xử lý conflict rõ ràng; không được bỏ qua exception rồi báo thành công.

## 8. Giải pháp 3: pessimistic locking khi cần khóa hàng

Với quy trình mà nhiều transaction thường xuyên tranh chấp cùng một bản ghi, có thể dùng khóa pessimistic để tuần tự hóa việc đọc và cập nhật.

Ví dụ SQL trong transaction:

~~~sql
SELECT AVAILABLE
FROM EVENT_SEAT
WHERE EVENT_ID = :eventId
FOR UPDATE;
~~~

Sau khi lấy khóa:

1. Đọc số lượng hiện tại.
2. Kiểm tra điều kiện.
3. Cập nhật số lượng nếu điều kiện hợp lệ.
4. Commit hoặc rollback transaction để giải phóng khóa.

Khóa phải được lấy và giữ trong cùng transaction. Nếu đọc bằng một connection rồi cập nhật bằng transaction khác, bảo đảm khóa không còn hiệu lực.

Pessimistic locking có thể làm request khác chờ, giảm thông lượng hoặc gây deadlock nếu nhiều luồng khóa các hàng theo thứ tự khác nhau. Hãy giữ transaction ngắn, khóa theo thứ tự nhất quán và cấu hình timeout phù hợp. Không giữ khóa database trong khi gọi API ngoài, gửi email hoặc chờ người dùng.

## 9. Giải pháp 4: Redis atomic operations

Nếu dữ liệu cần cập nhật nguyên tử thực sự nằm trong Redis, có thể dùng thao tác Redis phù hợp thay vì read-check-write trong Java.

Với bộ đếm đơn giản, `INCR` hoặc `DECR` là lệnh nguyên tử ở cấp Redis:

~~~text
INCR feature:counter:user-42
~~~

Nếu cần kiểm tra điều kiện và cập nhật trong cùng một thao tác, có thể dùng Lua script để Redis thực thi toàn bộ đoạn script như một đơn vị không xen kẽ với command khác:

~~~lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])

if current < limit then
    current = redis.call('INCR', KEYS[1])
    return current
end

return -1
~~~

Ứng dụng gọi script với key và giới hạn tương ứng. Script trả về giá trị mới nếu thành công hoặc `-1` nếu đã đạt giới hạn.

Không áp dụng `INCR`, `DECR` hoặc Lua trực tiếp lên các key nội bộ của Spring Session để sửa thuộc tính session. Cấu trúc lưu trữ và serialization do repository quản lý; thao tác ngoài có thể làm sai metadata, index hoặc định dạng dữ liệu. Nếu cần một bộ đếm nguyên tử, tạo key hoặc bảng riêng thuộc miền nghiệp vụ và quản lý TTL/namespace của nó một cách tường minh.

Redis `WATCH` kết hợp `MULTI/EXEC` cũng có thể triển khai optimistic concurrency cho nhiều key. Ứng dụng phải xử lý trường hợp transaction bị abort và thử lại có giới hạn; không lặp vô hạn khi tải cao.

## 10. Vì sao synchronized(session) không đủ?

Một số code thử bảo vệ vùng tới hạn bằng:

~~~java
synchronized (session) {
    Integer count = (Integer) session.getAttribute("count");
    if (count == null) {
        count = 0;
    }
    session.setAttribute("count", count + 1);
}
~~~

Khối `synchronized` chỉ khóa object trong cùng JVM. Khi ứng dụng chạy nhiều instance, request A có thể vào instance 1 và request B vào instance 2. Mỗi JVM có object `session` riêng, nên hai monitor không phối hợp với nhau.

Ngay trong một JVM, wrapper hoặc object session có thể được tạo riêng theo từng request. Không nên giả định hai request cùng session ID sẽ dùng chung một object Java và cùng monitor.

Nếu thực sự cần khóa phân tán, phải dùng cơ chế lock có phạm vi toàn cụm và có timeout/lease, xử lý owner token, gia hạn, giải phóng an toàn và trường hợp client bị dừng giữa chừng. Distributed lock tăng độ phức tạp và có thể làm giảm tính sẵn sàng. Với cập nhật dữ liệu quan hệ, atomic SQL hoặc optimistic/pessimistic locking thường dễ kiểm chứng hơn.

## 11. Transaction của service không tự bao trùm việc lưu session

Trong ứng dụng Servlet dùng Spring Session JDBC, repository có thể flush thay đổi session ở giai đoạn hoàn tất request. Một service method có `@Transactional` thường kết thúc transaction trước khi filter lưu session ở cuối request.

Do đó, không suy ra rằng:

~~~java
@Transactional
public void update(HttpSession session) {
    // đọc, kiểm tra, cập nhật database nghiệp vụ
    // và setAttribute trong cùng method
}
~~~

sẽ làm cho cả dữ liệu nghiệp vụ và session cùng commit/rollback như một transaction duy nhất. Ranh giới thực tế phụ thuộc transaction manager, repository, flush mode và vòng đời request.

Nếu một quy tắc cần atomicity, hãy đặt phần đọc/kiểm tra/ghi của quy tắc đó vào cùng transaction nghiệp vụ và cập nhật dữ liệu có thẩm quyền trong transaction ấy. Session chỉ nhận kết quả sau khi nghiệp vụ đã quyết định thành công hoặc thất bại.

## 12. Idempotency và retry

Race condition thường đi kèm retry. Người dùng double-click, reverse proxy retry request hoặc client gửi lại vì không nhận được response. Ngay cả khi cập nhật được bảo vệ bằng transaction, một thao tác có thể được thực hiện hai lần nếu API không có idempotency.

Với thao tác tạo reservation hoặc thanh toán, có thể dùng idempotency key:

1. Client gửi một key duy nhất cho một ý định thao tác.
2. Server lưu key cùng kết quả xử lý trong database.
3. Transaction kiểm tra key và tạo nghiệp vụ nếu key chưa tồn tại.
4. Request lặp lại với cùng key nhận lại kết quả đã lưu, không tạo nghiệp vụ lần nữa.

Idempotency key nên gắn với người dùng và loại thao tác, có thời hạn lưu phù hợp và được kiểm tra bằng constraint/transaction ở database. Không chỉ lưu key trong session vì request đồng thời vẫn có thể cùng đọc trạng thái cũ và cùng vượt qua kiểm tra.

## 13. Kiểm thử read-check-write đồng thời

Một test tuần tự không phát hiện được race condition. Cần khởi chạy nhiều request cùng thời điểm và xác minh invariant cuối cùng.

Ví dụ với bộ đếm:

- Giá trị ban đầu là 0.
- Gửi 100 request tăng đồng thời.
- Kết quả mong đợi là 100.
- Nếu kết quả nhỏ hơn 100, có thể đã xảy ra lost update.

Ví dụ với một chỗ còn lại:

- Giá trị ban đầu là 1.
- Gửi 20 request giữ chỗ đồng thời.
- Chính xác một request được thành công.
- Số lượng còn lại không âm.
- Chỉ có một reservation record được tạo.

Kịch bản test nên:

1. Dùng database/Redis test instance thực tế.
2. Dùng barrier hoặc latch để nhiều request cùng bắt đầu gần như đồng thời.
3. Gửi cùng session cookie nếu kiểm tra cạnh tranh trên một session.
4. Chạy qua nhiều instance hoặc nhiều application context khi cần xác minh cụm.
5. Kiểm tra cả response từng request và trạng thái cuối trong kho dữ liệu.
6. Lặp lại test nhiều lần với tải và độ trễ khác nhau.

Với WebFlux, dùng `WebTestClient` hoặc HTTP client bất đồng bộ để phát request song song. Với Servlet, có thể dùng executor và HTTP client nhiều thread. Không chỉ gọi service method song song trong cùng JVM nếu mục tiêu là kiểm tra hành vi qua filter và session repository.

## 14. Ma trận lựa chọn giải pháp

| Yêu cầu | Giải pháp phù hợp để đánh giá | Lý do |
|---|---|---|
| Tăng/giảm một bộ đếm trong database | Atomic SQL `SET value = value + 1` | Không cần round trip đọc rồi ghi |
| Giữ chỗ nếu số lượng còn lớn hơn 0 | SQL update có điều kiện | Kiểm tra và cập nhật cùng một câu lệnh |
| Cập nhật entity có version | Optimistic locking | Phát hiện snapshot cũ |
| Tranh chấp cao trên một hàng | Pessimistic row lock | Tuần tự hóa transaction trên hàng đó |
| Bộ đếm Redis đơn giản | `INCR`/`DECR` | Một Redis command nguyên tử |
| Kiểm tra điều kiện và cập nhật nhiều key Redis | Lua hoặc `WATCH`/`MULTI` | Thực hiện có điều kiện và xử lý conflict |
| Lưu lựa chọn giao diện theo request | Session attribute | Dữ liệu tạm, không cần quy tắc nghiệp vụ nguyên tử |

Không có một cơ chế duy nhất phù hợp cho mọi trường hợp. Chọn nơi lưu dữ liệu có thẩm quyền trước, xác định invariant cần bảo vệ, sau đó chọn transaction hoặc atomic operation của chính kho dữ liệu đó.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bộ đếm tăng thiếu | Nhiều request cùng đọc một giá trị rồi ghi cùng kết quả | Dùng atomic increment tại database hoặc Redis |
| Hai người cùng giữ một tài nguyên cuối | Điều kiện kiểm tra và cập nhật nằm ở hai bước riêng | Dùng conditional update hoặc lock trong transaction |
| synchronized không ngăn được lỗi khi scale out | Monitor chỉ có phạm vi một JVM | Dùng atomic store operation hoặc distributed coordination |
| Transaction service rollback nhưng session vẫn thay đổi | Session flush có transaction boundary riêng | Không lưu trạng thái nghiệp vụ có thẩm quyền trong session |
| Retry tạo hai bản ghi nghiệp vụ | API không idempotent | Dùng idempotency key và unique constraint |
| Test đơn lẻ luôn pass nhưng production mất cập nhật | Chưa test request song song hoặc nhiều instance | Tạo concurrency integration test với shared store |
| Redis command trực tiếp làm session không đọc được | Tự sửa key/hash nội bộ của Spring Session | Chỉ cập nhật qua API repository; dùng key nghiệp vụ riêng cho atomic counter |

## 16. Checklist trước khi triển khai

- [ ] Xác định dữ liệu nào là trạng thái session và dữ liệu nào là sự thật nghiệp vụ.
- [ ] Xác định invariant phải được bảo vệ khi nhiều request chạy đồng thời.
- [ ] Không giả định chuỗi đọc–kiểm tra–ghi trong Java là nguyên tử.
- [ ] Đưa điều kiện vào câu SQL cập nhật khi phù hợp.
- [ ] Dùng optimistic hoặc pessimistic locking khi cần kiểm soát xung đột.
- [ ] Dùng Redis atomic command/Lua cho dữ liệu Redis nghiệp vụ phù hợp.
- [ ] Không dựa vào `synchronized(session)` để khóa giữa nhiều instance.
- [ ] Không sửa key nội bộ của Spring Session bằng Redis command tùy tiện.
- [ ] Kiểm tra transaction boundary giữa service và session repository.
- [ ] Thiết kế idempotency cho thao tác có thể được retry.
- [ ] Kiểm thử nhiều request cùng session cookie và nhiều instance.
- [ ] Đo tỷ lệ conflict, số lần retry, độ trễ và lỗi lưu trữ.

Đọc, kiểm tra rồi ghi là ba bước riêng biệt cho tới khi kho dữ liệu thực hiện chúng trong một transaction hoặc atomic operation có bảo đảm phù hợp. Spring Session chia sẻ trạng thái phiên giữa request và instance, nhưng không tự khóa toàn bộ logic ứng dụng. Hãy giữ session cho trạng thái tạm thời; với quy tắc nghiệp vụ, dùng conditional SQL, optimistic/pessimistic locking hoặc Redis atomic operation tại nơi lưu dữ liệu có thẩm quyền, rồi kiểm thử bằng request đồng thời để chứng minh invariant vẫn được giữ.
