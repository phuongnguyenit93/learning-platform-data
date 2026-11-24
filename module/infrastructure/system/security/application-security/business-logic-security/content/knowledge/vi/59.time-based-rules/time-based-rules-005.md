# Expiration boundary: bảo vệ ranh giới hết hạn của quy tắc nghiệp vụ

## 1. Hết hạn là một điều kiện cấp quyền

Trong chương **Time Based Rules**, expiration boundary là ranh giới phân biệt một thao tác còn được phép với một thao tác đã mất hiệu lực do thời gian. Đó có thể là thời điểm cuối để chấp nhận báo giá, dùng ưu đãi, xác nhận phê duyệt, hoàn tất lượt giữ hoặc sử dụng một quyền tạm thời.

Sai sót thường chỉ xuất hiện trong một khoảng rất ngắn:

- Dùng dấu so sánh không thống nhất khiến đúng thời điểm hết hạn vẫn được chấp nhận.
- Kiểm tra trước khi chờ khóa, rồi thực hiện sau khi quyền đã hết hạn.
- Tin thời gian do client gửi hoặc đồng hồ của một máy ứng dụng bị lệch.
- Worker chưa chuyển trạng thái sang EXPIRED nên API tiếp tục cho sử dụng.
- Làm tròn timestamp theo cách kéo dài hiệu lực ngoài chính sách.
- Gia hạn và thu hồi chạy đồng thời, làm sống lại quyền đã kết thúc.
- Phát lại phản hồi thành công rồi vô tình thực hiện tác động nghiệp vụ lần nữa.

Các request này có thể có token đăng nhập hợp lệ và dữ liệu đúng định dạng. Vấn đề nằm ở việc bảo vệ invariant về thời gian tại đúng điểm quyết định nghiệp vụ.

Ví dụ xuyên suốt: một **báo giá ưu đãi** cho khách hàng có hiệu lực từ 10:00 đến 10:05. Khách được dùng giá đó để tạo một đơn hàng trong khoảng cho phép. Máy chủ quản lý giá, nội dung báo giá, chủ thể được dùng và thời hạn. Mỗi báo giá chỉ được chấp nhận một lần.

Mục tiêu bài học là thiết kế một quy tắc mà mọi đường xử lý đều đồng ý về câu hỏi: **tại thời điểm quyết định, quyền này còn hiệu lực hay không?**

## 2. Chốt hợp đồng thời gian trước khi viết code

Một phát biểu như “hết hạn sau 5 phút” chưa đủ để triển khai an toàn. Cần ghi rõ ít nhất các điểm sau:

| Câu hỏi | Quyết định cho ví dụ |
| --- | --- |
| Hiệu lực bắt đầu khi nào? | Tại valid_from |
| Điểm cuối có được tính không? | Không; expires_at là điểm đầu tiên không còn hiệu lực |
| Ai cấp thời hạn? | Máy chủ, theo chính sách của báo giá |
| Thời gian lấy từ đâu? | Nguồn thời gian chuẩn của cơ sở dữ liệu quyết định |
| Kiểm tra tại lúc nào? | Sau khi có các khóa cần thiết, ngay trước quyết định chấp nhận |
| Độ chính xác là bao nhiêu? | Một độ chính xác chuẩn được chọn và dùng xuyên suốt |
| Có gia hạn hoặc ân hạn không? | Chỉ khi chính sách quy định rõ, không ngầm cộng thêm |
| Request đến trước hạn nhưng xử lý sau hạn? | Bị từ chối nếu thời điểm quyết định đã hết hạn |
| Đã chấp nhận trước hạn, commit sau hạn? | Vẫn hợp lệ trong chính sách dựa trên thời điểm quyết định của ví dụ |
| Retry sau hạn có làm lại thao tác không? | Không; chỉ phát lại kết quả của lần đã commit nếu đúng idempotency |

Chính sách có thể chọn thời điểm khác, chẳng hạn thời điểm nhận yêu cầu tại một cổng tin cậy. Khi đó phải xây dựng bằng chứng thời điểm nhận, kiểm soát hàng đợi, chống phát lại và giới hạn khoảng xử lý. Không thể triển khai chính sách đó bằng cách tin trường sentAt từ client.

Bài này dùng chính sách theo **thời điểm quyết định trong transaction**. Việc chọn chính sách khác phải được thể hiện trong yêu cầu nghiệp vụ và mọi thành phần thực thi.

## 3. Khoảng hiệu lực nửa kín

Quy ước:

~~~text
valid_from <= decision_time < expires_at
~~~

Đây là khoảng [valid_from, expires_at): bao gồm điểm đầu và loại trừ điểm cuối.

Giả sử:

~~~text
valid_from = 2026-11-22T03:00:00.000Z
expires_at = 2026-11-22T03:05:00.000Z
~~~

Các mốc này tương ứng 10:00 và 10:05 tại múi giờ UTC+07:00 trong ví dụ.

| decision_time | Kết quả về thời gian |
| --- | --- |
| 02:59:59.999Z | Chưa có hiệu lực |
| 03:00:00.000Z | Có hiệu lực |
| 03:04:59.999Z | Có hiệu lực |
| 03:05:00.000Z | Đã hết hạn |
| 03:05:00.001Z | Đã hết hạn |

Các giá trị trong bảng được minh họa với độ chính xác mili giây. Hệ thống dùng độ chính xác khác phải kiểm thử những điểm lân cận tương ứng.

Một hàm thuần theo phong cách Java:

~~~java
static boolean withinWindow(
        Instant decisionTime,
        Instant validFrom,
        Instant expiresAt) {

    return !decisionTime.isBefore(validFrom)
        && decisionTime.isBefore(expiresAt);
}
~~~

Trước khi sử dụng, dữ liệu phải thỏa valid_from < expires_at. Không coi khoảng bằng nhau hoặc thời hạn đảo ngược là một ưu đãi hợp lệ.

Hai lỗi đối xứng thường gặp:

~~~text
Sai: decision_time <= expires_at
     -> chấp nhận ngay tại điểm hết hạn.

Sai: chỉ coi là hết hạn khi decision_time > expires_at
     -> bỏ lọt trường hợp decision_time = expires_at.
~~~

Cặp điều kiện nhất quán là:

~~~text
còn hiệu lực: decision_time < expires_at
đã hết hạn:   decision_time >= expires_at
~~~

Khoảng nửa kín cũng giúp ghép các phiên hiệu lực liên tiếp. Nếu phiên A kết thúc đúng lúc phiên B bắt đầu, không có một thời điểm thuộc cả hai phiên chỉ vì cả hai đều tính điểm cuối.

## 4. Invariants và state machine

Đối với báo giá, các invariant cần bảo vệ gồm:

1. Mỗi báo giá có một tenant, một subject được sử dụng và một nội dung được định danh rõ.
2. valid_from và expires_at do máy chủ quản lý; valid_from < expires_at.
3. Chỉ báo giá OPEN, đủ quyền và đủ điều kiện mới được chấp nhận.
4. Thời điểm chấp nhận thỏa valid_from ≤ accepted_at < expires_at.
5. Một báo giá chỉ tạo tối đa một kết quả chấp nhận có hiệu lực.
6. Giá, tiền tệ và nội dung đơn hàng lấy từ phiên bản báo giá đã được máy chủ xác minh.
7. Báo giá đã EXPIRED hoặc CANCELLED không được tự chuyển lại thành OPEN.
8. Gửi lại yêu cầu không tạo đơn mới hoặc dùng lại quyền đã tiêu thụ.
9. Tác vụ hết hạn không được hủy một lần chấp nhận đã commit hợp lệ.
10. Gia hạn không được dựa trên trạng thái hay thời hạn đã đọc trước một thay đổi đồng thời.

~~~mermaid
stateDiagram-v2
    [*] --> OPEN: Máy chủ phát hành
    OPEN --> ACCEPTED: Đúng quyền, đúng phiên bản, còn hiệu lực
    OPEN --> EXPIRED: Đến hạn và được đánh dấu
    OPEN --> CANCELLED: Thu hồi theo quyền được cấp
~~~

Trạng thái OPEN không đồng nghĩa còn hạn. Nó chỉ cho biết chưa có chuyển trạng thái kết thúc được ghi nhận. API vẫn phải kiểm tra thời gian.

Ngược lại, ACCEPTED không tự biến thành EXPIRED khi thời gian trôi qua. Trong ví dụ, thời hạn giới hạn cơ hội chấp nhận báo giá; nó không tự hủy đơn hàng đã tạo hợp lệ. Nếu sản phẩm có thời hạn thanh toán đơn hàng, đó là một quy tắc riêng với trạng thái và deadline riêng.

Có thể phân biệt:

- **Hiệu lực suy ra:** tính từ trạng thái, phiên bản, quyền và thời gian hiện tại.
- **Trạng thái được lưu:** phục vụ điều phối vòng đời, truy vấn và kiểm toán.

Worker có thể cập nhật trạng thái được lưu chậm hơn thời điểm hết hạn. Sự chậm trễ đó không được kéo dài quyền sử dụng.

## 5. Chọn đúng thời điểm quyết định

### 5.1. Những timestamp không thể dùng thay nhau

Một request có thể đi qua các mốc:

| Mốc | Ý nghĩa |
| --- | --- |
| client_sent_at | Client tự khai lúc gửi |
| edge_received_at | Thành phần tiếp nhận ghi nhận request |
| transaction_started_at | Bắt đầu transaction |
| lock_acquired_at | Có đủ quyền truy cập độc quyền vào dữ liệu cần quyết định |
| decision_time | Thời gian dùng để xét quy tắc nghiệp vụ |
| committed_at | Kết quả transaction trở nên bền vững |
| downstream_processed_at | Dịch vụ sau đó thực hiện tác vụ |

Nếu chính sách dùng decision_time, không thay bằng client_sent_at, transaction_started_at hoặc thời gian đã đọc trước khi chờ khóa.

Ví dụ:

~~~text
10:04:59.900  Request bắt đầu, ứng dụng đọc "chưa hết hạn".
10:04:59.950  Request chờ khóa do transaction khác giữ.
10:05:00.200  Có khóa báo giá.
10:05:00.210  Ứng dụng tạo đơn dựa trên kết quả kiểm tra cũ.
~~~

Request này phải bị từ chối trong chính sách của bài. Thông tin “chưa hết hạn” tại 10:04:59.900 không còn chứng minh điều kiện tại thời điểm quyết định.

### 5.2. Kiểm tra sau khi có đủ dữ liệu được bảo vệ

Trình tự phù hợp:

~~~text
xác thực
-> vào transaction
-> xử lý idempotency
-> lấy các khóa cần thiết
-> đọc lại trạng thái và phiên bản
-> kiểm tra quyền, nội dung, điều kiện phê duyệt
-> lấy decision_time từ nguồn chuẩn
-> kiểm tra cửa sổ thời gian
-> ghi kết quả nghiệp vụ
-> commit
~~~

Nếu việc xác minh điều kiện cần gọi mạng, nên xử lý trước bằng một giao thức riêng rồi tái xác minh bằng chứng trong transaction. Không giữ khóa báo giá để chờ một dịch vụ bên ngoài trả lời.

Nếu nhiều hàng chính sách cần được bảo vệ, chúng cũng phải tham gia giao thức khóa hoặc kiểm tra phiên bản. Không đọc một điều kiện có thể bị thu hồi đồng thời rồi mặc định nó bất biến đến lúc commit.

### 5.3. Quyết định trước hạn và commit sau hạn

Ví dụ:

~~~text
10:04:59.999  Có đủ khóa, kiểm tra hợp lệ, ghi accepted_at.
10:05:00.003  Commit thành công.
~~~

Theo hợp đồng của bài, đây là lần chấp nhận hợp lệ vì accepted_at chính là decision_time trước hạn. Không gắn nhãn “chấp nhận muộn” bằng cách chỉ nhìn giờ trả HTTP.

Nếu nghiệp vụ yêu cầu tác động phải hoàn tất trước deadline, một lần kiểm tra trước commit không chứng minh yêu cầu đó. Cần thiết kế ranh giới thực thi phù hợp và kiểm soát tại nơi phát sinh tác động. Việc ghi accepted_at = thời điểm trước hạn không làm cho một tác động thực tế xảy ra sau hạn trở thành trước hạn.

Tương tự, một tác vụ dài bắt đầu khi quyền còn hạn có được tiếp tục sau hạn hay không phải được quy định riêng. “Được bắt đầu” và “được tiếp tục sử dụng tài nguyên” là hai quyền khác nhau.

## 6. Nguồn thời gian và giả định đồng hồ

### 6.1. Client không quyết định đồng hồ nghiệp vụ

Không nhận now, acceptedAt hoặc expiresAt từ request làm căn cứ cấp quyền. Client có thể chỉnh đồng hồ, gửi lại request cũ hoặc sửa trường dữ liệu.

Nếu client gửi mã báo giá, máy chủ phải tra báo giá hoặc xác minh chứng cứ được ký phù hợp. Chữ ký bảo vệ dữ liệu khỏi bị sửa; việc còn hạn vẫn phải được máy chủ đánh giá theo nguồn thời gian của chính sách.

Đồng hồ đếm ngược trên giao diện chỉ hỗ trợ trải nghiệm. Khi UI hiển thị còn một giây nhưng transaction quyết định sau hạn, kết quả đúng vẫn là hết hạn.

### 6.2. Dùng một nguồn chuẩn trong miền nhất quán

Ví dụ chọn thời gian từ cơ sở dữ liệu đang quyết định ghi báo giá. Mọi instance phải tuân theo lựa chọn đó.

Cần phân biệt:

- Thời điểm bắt đầu transaction.
- Thời điểm bắt đầu câu lệnh.
- Đồng hồ thực tại lúc biểu thức được đánh giá.

Các hệ quản trị có thể cung cấp những hàm với ngữ nghĩa khác nhau. Không mặc định một biểu thức tên “current time” trả thời gian thực sau khi chờ khóa. Lớp truy cập dữ liệu phải chọn và kiểm chứng đúng ngữ nghĩa của hệ quản trị đang dùng.

Một abstraction có thể là:

~~~java
interface DecisionTimeSource {
    Instant nowAfterLocks(Connection connection);
}
~~~

Tên phương thức thể hiện hợp đồng cần triển khai; nó không phải API chuẩn của JDBC. Khi kiểm thử tích hợp, phải chứng minh thời gian trả về không bị cố định ở lúc transaction bắt đầu.

### 6.3. UTC không thay thế đồng bộ đồng hồ

Dùng UTC giúp biểu diễn cùng một instant thống nhất. Nó không tự làm hai máy có cùng giờ.

Hai máy cùng dùng UTC nhưng lệch nhau vài giây vẫn có thể cho hai quyết định khác nhau gần deadline. Cần vận hành nguồn thời gian đáng tin cậy, theo dõi sai lệch và xác định phản ứng khi mất độ tin cậy.

Nếu đồng hồ lùi, chỉ so sánh thời gian có thể làm một bản ghi OPEN dường như còn hạn trở lại. Trạng thái EXPIRED đã được ghi bền vững giúp ngăn mở lại bản ghi đó, nhưng không giải quyết mọi sai lệch đồng hồ của các bản ghi chưa được đánh dấu.

Không thêm một khoảng chấp nhận sau hạn chỉ để che lỗi đồng hồ. Nếu cần biên an toàn, phải quy định rõ nó làm quyết định thận trọng hơn như thế nào và ảnh hưởng quyền lợi người dùng ra sao.

### 6.4. Đồng hồ đơn điệu dùng cho mục đích khác

Trong Java, phép đo thời lượng nội bộ bằng nguồn đơn điệu phù hợp để đo timeout hoặc độ trễ trong một tiến trình. Nó không cung cấp timestamp nghiệp vụ có thể lưu rồi so sánh trên nhiều máy.

Không lưu một giá trị như System.nanoTime() làm expires_at, không truyền nó sang máy khác để so sánh với epoch time.

Nên tách:

- Deadline nghiệp vụ: instant tuyệt đối theo nguồn chuẩn.
- Timeout request, thời gian chờ khóa và backoff: ngân sách xử lý kỹ thuật.

Request chưa hết timeout không có nghĩa báo giá vẫn còn hiệu lực.

## 7. Độ chính xác, làm tròn và múi giờ

### 7.1. Timestamp phải có biểu diễn chuẩn

Một ứng dụng có thể nhận Instant chính xác đến nano giây, lưu DB ở micro giây và trả JSON ở mili giây. Nếu không có quy ước, ba nơi có thể đang so sánh ba deadline khác nhau.

Nên quyết định:

1. Độ chính xác nghiệp vụ được hỗ trợ.
2. Quy tắc chuẩn hóa deadline khi phát hành.
3. Cách driver và cột thời gian lưu giá trị.
4. Giá trị chuẩn dùng để ký, trả API, so sánh và kiểm toán.

Ví dụ, nếu hệ thống công bố deadline ở mili giây, hãy lưu và sử dụng cùng deadline chuẩn đó. Không ký một timestamp có nhiều chữ số hơn rồi lưu một giá trị đã được làm tròn khác đi.

Lỗi nguy hiểm:

~~~text
expires_at = 10:05:00.500
now thực   = 10:05:00.900

Ứng dụng cắt riêng now xuống giây:
now dùng để kiểm tra = 10:05:00.000

Kết quả sai: cho rằng now < expires_at.
~~~

Không cắt riêng thời điểm hiện tại về độ chính xác thấp hơn deadline. Nếu việc chuẩn hóa có thể thay đổi quyền ở biên, phải định nghĩa và kiểm thử nó như một phần của chính sách.

Không dùng số thực cho epoch time rồi so sánh tiền hậu tố thập phân bằng cảm tính. Chọn kiểu thời gian hoặc số nguyên đơn vị thời gian đã được thống nhất.

### 7.2. Duration khác quy tắc lịch địa phương

“Hết hạn sau 24 giờ” có thể được mô hình hóa bằng một Duration từ instant phát hành. “Hết hạn cuối ngày tại địa phương của sự kiện” cần một múi giờ và quy tắc lịch cụ thể.

Đối với quy tắc lịch, máy chủ phải xác định ngày, múi giờ, cách xử lý mốc địa phương không tồn tại hoặc xuất hiện hai lần tại nơi có chuyển giờ theo mùa, rồi chuyển thành instant chuẩn.

Không dùng chuỗi thời gian thiếu offset hoặc timezone khi nó làm deadline mơ hồ. Không để timezone của máy triển khai tự thay đổi ý nghĩa thời hạn.

Đối với cuối ngày, có thể biểu diễn bằng **đầu ngày kế tiếp làm điểm cuối loại trừ** thay vì tự tạo “23:59:59.999” rồi giả định đó là độ chính xác lớn nhất của hệ thống.

## 8. Thực thi nguyên tử với dữ liệu nghiệp vụ

### 8.1. Dữ liệu cần gắn với quyền có thời hạn

Một bản ghi price_quote có thể chứa:

| Trường | Vai trò |
| --- | --- |
| tenant_id, quote_id | Định danh và phạm vi đối tượng |
| subject_id | Chủ thể được dùng |
| state | OPEN, ACCEPTED, EXPIRED hoặc CANCELLED |
| valid_from, expires_at | Cửa sổ hiệu lực chuẩn |
| version | Phiên bản nội dung và chính sách cần kiểm tra |
| amount_minor, currency | Giá do máy chủ quyết định |
| items_digest | Định danh nội dung hàng hóa đã báo giá |
| accepted_at, accepted_order_id | Bằng chứng kết quả chấp nhận |

Cần các ràng buộc phù hợp như valid_from < expires_at, trạng thái hợp lệ và không có nhiều đơn dùng cùng một báo giá. Khóa duy nhất theo tenant và quote_id tại quan hệ đơn hàng là một lớp bảo vệ cho invariant dùng một lần.

Nếu client thay danh sách hàng hóa, số lượng, subject hoặc điều kiện làm thay đổi giá, không tiếp tục dùng báo giá cũ chỉ vì expires_at chưa tới. Hạn sử dụng không thay thế kiểm tra nội dung được phê duyệt.

### 8.2. Cập nhật có điều kiện

Sau khi lấy khóa hàng báo giá và các hàng liên quan, ứng dụng lấy decision_time mới. Câu lệnh minh họa:

~~~sql
UPDATE price_quote
SET state = 'ACCEPTED',
    accepted_at = :decision_time,
    accepted_order_id = :order_id,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND quote_id = :quote_id
  AND subject_id = :authorized_subject_id
  AND state = 'OPEN'
  AND version = :expected_version
  AND valid_from <= :decision_time
  AND :decision_time < expires_at;
~~~

Chỉ khi ảnh hưởng đúng một hàng mới được tiếp tục tạo đơn theo dữ liệu báo giá đã xác minh. Cập nhật báo giá, tạo đơn và ghi kết quả idempotency phải cùng transaction. Nếu tạo đơn thất bại, rollback cả việc đánh dấu ACCEPTED.

Không coi “0 hàng bị cập nhật” là thành công. Nguyên nhân có thể là hết hạn, sai phiên bản, sai trạng thái hoặc sai đối tượng; đọc và phân loại dưới cơ chế nhất quán phù hợp, đồng thời tránh tiết lộ đối tượng ngoài quyền.

Câu SQL dùng một tham số decision_time cho toàn bộ quyết định. Nếu mỗi chỗ trong câu lệnh hoặc trong nhiều câu lệnh lấy một now khác nhau, ranh giới có thể trở nên khó giải thích và kiểm toán.

### 8.3. Mã giả Java cho một luồng đầy đủ

Đây là cấu trúc minh họa; tx, idem, quotes, orders và timeSource là abstraction của ứng dụng.

~~~java
AcceptResult acceptQuote(AuthContext auth, AcceptCommand cmd) {
    Subject subject = authorization.resolveSubject(auth, cmd.subjectId());
    String fingerprint = fingerprint(
        subject.id(), cmd.quoteId(), cmd.quoteVersion()
    );

    return tx.required(connection -> {
        IdempotencyDecision key = idem.acquire(
            connection, auth, "ACCEPT_QUOTE",
            cmd.idempotencyKey(), fingerprint
        );

        if (key.hasResult()) {
            authorization.checkResultAccess(auth, key.originalResult());
            return key.originalResult();
        }

        Quote quote = quotes.lock(
            connection, auth.tenantId(), cmd.quoteId()
        );

        authorization.checkAcceptPermission(connection, auth, subject, quote);
        quote.requireVersion(cmd.quoteVersion());
        quote.requireOpen();
        policy.checkContentsAndApproval(connection, quote);

        Instant t = timeSource.nowAfterLocks(connection);

        if (t.isBefore(quote.validFrom())) {
            return idem.complete(
                connection, key, AcceptResult.notYetValid()
            );
        }

        if (!t.isBefore(quote.expiresAt())) {
            quotes.markExpired(connection, quote);
            return idem.complete(
                connection, key, AcceptResult.expired()
            );
        }

        String orderId = ids.newOrderId();
        quotes.acceptExactlyOnce(connection, quote, orderId, t);
        orders.createFromVerifiedQuote(connection, orderId, quote);

        return idem.complete(
            connection, key, AcceptResult.accepted(orderId, t)
        );
    });
}
~~~

Các điều kiện để ví dụ có ý nghĩa:

- Tất cả truy cập dữ liệu có liên quan dùng cùng connection và transaction.
- tx.required chỉ trả kết quả ra ngoài sau commit thành công.
- quotes.acceptExactlyOnce kiểm tra số hàng cập nhật; xung đột làm rollback.
- Giá và nội dung đơn hàng lấy từ quote đã xác minh, không từ giá client gửi.
- Quyền và điều kiện phê duyệt có thể thay đổi phải được bảo vệ theo giao thức đồng thời của ứng dụng.
- Kết quả hết hạn là một giá trị nghiệp vụ để transaction có thể commit EXPIRED, không phải exception mặc định làm rollback việc đánh dấu.
- Ví dụ lưu cả một số kết quả từ chối trong idempotency. Retry cùng key phát lại kết quả ban đầu; muốn thử một lần nghiệp vụ mới sau thay đổi hợp lệ thì cần theo hợp đồng API tương ứng.
- Những lỗi kỹ thuật hoặc vi phạm invariant phải rollback, không bị chuyển thành kết quả thành công.

Sau khi service trả kết quả đã commit, lớp HTTP mới ánh xạ nó thành phản hồi. Tránh nhầm giữa “trả lỗi nghiệp vụ” và “bắt buộc rollback mọi thay đổi”, nhất là khi cần ghi nhận hết hạn.

## 9. Worker hết hạn và gia hạn đồng thời

### 9.1. Worker không quyết định quyền sử dụng thay API

Worker thường quét ứng viên:

~~~sql
SELECT tenant_id, quote_id, version
FROM price_quote
WHERE state = 'OPEN'
  AND expires_at <= :scan_time;
~~~

Danh sách đó có thể cũ trước khi worker xử lý. Với từng ứng viên, cần:

1. Bắt đầu transaction.
2. Lấy khóa theo cùng giao thức với API chấp nhận và gia hạn.
3. Đọc lại trạng thái, version và expires_at.
4. Lấy decision_time hiện tại sau khi có khóa.
5. Chỉ chuyển OPEN → EXPIRED nếu deadline hiện hành đã tới.
6. Commit rồi mới công bố kết quả xử lý.

Cập nhật có điều kiện minh họa:

~~~sql
UPDATE price_quote
SET state = 'EXPIRED',
    version = version + 1
WHERE tenant_id = :tenant_id
  AND quote_id = :quote_id
  AND state = 'OPEN'
  AND version = :locked_version
  AND expires_at <= :decision_time;
~~~

locked_version phải là phiên bản vừa đọc dưới khóa, không phải giá trị cũ từ lúc quét. Nếu ứng dụng dùng cách cập nhật optimistic thay cho khóa, phải kiểm tra xung đột và đọc lại theo giao thức được thiết kế.

Nếu API đã chấp nhận báo giá trước đó, state không còn OPEN và worker không được đổi ACCEPTED thành EXPIRED. Hai worker cùng xử lý chỉ được có tối đa một chuyển trạng thái hữu hiệu.

Nếu worker dừng một giờ, báo giá quá hạn vẫn phải bị API từ chối ngay bằng predicate thời gian. Không phụ thuộc lịch cron để thi hành điều kiện cấp quyền.

### 9.2. Gia hạn là một quyền nghiệp vụ riêng

Một luồng gia hạn an toàn cần kiểm tra:

- Actor có quyền gia hạn cho subject và báo giá này.
- Báo giá còn OPEN.
- Tại thời điểm quyết định, báo giá chưa hết hạn.
- Phiên bản đúng với nội dung được phép gia hạn.
- Số lần gia hạn và deadline tối đa chưa vượt chính sách.
- Deadline mới do máy chủ tính và thực sự hợp lệ.

Việc đổi expires_at và tăng version phải cùng transaction. Nếu có token hoặc tài liệu được ký theo phiên bản, cần phát hành lại bằng chứng tương ứng.

Không dùng endpoint gia hạn như một cách chuyển EXPIRED → OPEN. Nếu sản phẩm cho phép cấp lại báo giá sau hết hạn, đó phải là quyết định mới: kiểm tra lại giá, nội dung, quyền và điều kiện phê duyệt.

Đặt deadline mới bằng now + TTL trong mọi lần ping có thể tạo quyền sống vô hạn. Một giới hạn tuyệt đối theo thời điểm phát hành hoặc chiến dịch giúp chặn cách lạm dụng đó.

### 9.3. Kịch bản đua cần có kết quả rõ ràng

| Thứ tự quyết định | Kết quả |
| --- | --- |
| Gia hạn có khóa trước hạn, ghi deadline mới và commit | Worker sau đó phải dùng deadline mới |
| Worker có khóa khi đã tới hạn, commit EXPIRED | Gia hạn sau đó bị từ chối |
| Request gia hạn đến trước hạn nhưng chờ khóa đến sau hạn | Bị từ chối theo chính sách thời điểm quyết định |
| Chấp nhận đã commit ACCEPTED | Không gia hạn hoặc thu hồi hết hạn báo giá đó nữa |

Mọi đường ghi phải dùng cùng thứ tự khóa cho các hàng chung. Nếu một endpoint khóa quote trước còn worker khóa một tài nguyên liên quan trước theo thứ tự ngược lại, nguy cơ deadlock tăng. Quy trình retry phải chạy lại toàn bộ transaction với một decision_time mới, không tái sử dụng kết quả kiểm tra thời gian của lần đã rollback.

## 10. Retry và idempotency tại ranh giới hết hạn

### 10.1. Phát lại kết quả không phải chấp nhận lần nữa

Giả sử lần đầu:

~~~text
10:04:59.980  Chấp nhận báo giá và tạo đơn O1.
10:04:59.990  Commit thành công.
10:05:00.100  Client mất phản hồi, gửi lại cùng key.
~~~

Hệ thống nên trả kết quả O1 đã ghi. Không tạo O2; cũng không phủ nhận lần chấp nhận hợp lệ chỉ vì thời điểm phát lại đã qua expires_at.

Lần gọi thứ hai đang hỏi kết quả của quyết định cũ, không xin một quyết định mới. Vì vậy:

- Xử lý idempotency phải có thể nhận diện kết quả đã commit trước khi thực hiện lại thao tác.
- Key phải gắn với tenant, actor, loại thao tác và dấu vân tay nội dung.
- Cùng key nhưng khác quote, subject hoặc version phải bị từ chối xung đột.
- Chỉ người có quyền đọc kết quả mới nhận được nội dung phát lại.

Nếu transaction đầu rollback hoặc chưa commit, không được phát lại một kết quả thành công chưa tồn tại bền vững.

### 10.2. Mỗi kết quả phát lại có phạm vi rõ ràng

Phản hồi “đã tạo đơn O1” không phải một token cho mọi thao tác tương lai. Đơn hàng có thể có trạng thái hoặc thời hạn riêng. Một endpoint mới vẫn phải kiểm tra quyền hiện hành và quy tắc thời gian áp dụng cho hành động đó.

Nếu hệ thống lưu kết quả “chưa có hiệu lực” hoặc “hết hạn” cho một key, retry cùng key phát lại kết quả đó theo hợp đồng. Sau khi báo giá được thay đổi hợp lệ, một lần thử nghiệp vụ mới phải được phân biệt rõ. Đổi key không được vượt ràng buộc một lần chấp nhận cho cùng báo giá.

### 10.3. Retry sau lỗi đồng thời phải lấy giờ mới

Ví dụ:

1. Transaction A quyết định lúc 10:04:59.900.
2. A bị hủy do deadlock.
3. Ứng dụng retry lúc 10:05:00.100.

Lần đầu chưa commit nên không tạo quyền đã chấp nhận. Lần retry phải lấy thời gian mới và bị từ chối nếu đã hết hạn. Không giữ biến decision_time của lần trước ngoài vòng retry rồi dùng lại.

Thời gian lưu idempotency cũng phải phù hợp khoảng retry được hỗ trợ. Xóa bản ghi quá sớm có thể khiến request muộn bị nhận diện là lần mới; ràng buộc dùng báo giá một lần vẫn phải bảo vệ dữ liệu ngay cả khi bản ghi idempotency đã được dọn.

## 11. Cache, token và việc dọn dữ liệu

### 11.1. Cache không phải nơi quyết định cuối cùng

Cache có thể chứa báo giá OPEN trước khi nó hết hạn hoặc bị thu hồi. TTL của cache chủ yếu quyết định lúc hệ thống nên bỏ bản sao; nó không thay thế điều kiện cấp quyền.

Đối với thao tác có tác động như chấp nhận báo giá:

- Không chỉ đọc cache hoặc replica có thể trễ để kết luận còn hiệu lực.
- Tái xác minh tại nơi quyết định ghi có cơ chế nhất quán phù hợp.
- Luôn kiểm tra expires_at; không chờ key biến mất khỏi cache.
- Nếu cache phục vụ hiển thị, phản hồi có thể mang deadline chuẩn để UI tự cập nhật.

Thời điểm hệ thống cache hoặc cơ sở dữ liệu vật lý xóa bản ghi có thể muộn hơn deadline. Bản ghi còn tồn tại không chứng minh quyền còn hiệu lực.

### 11.2. Token có chữ ký vẫn cần đúng ngữ nghĩa

Một token báo giá có thể ràng buộc quote_id, tenant, subject, version, nội dung và expires_at. Máy chủ cần kiểm tra chữ ký cùng các điều kiện sử dụng theo chính sách.

Các vấn đề chữ ký không tự giải quyết:

- Token đúng nhưng đã hết hạn.
- Token của tenant hoặc subject khác.
- Báo giá đã bị thu hồi.
- Token phiên bản cũ sau khi báo giá đổi giá hoặc deadline.
- Token hợp lệ được dùng lặp để tạo nhiều đơn.

Nếu cần thu hồi tức thời, dùng một lần hoặc kiểm tra phiên bản hiện hành, thiết kế thường cần trạng thái máy chủ hoặc cơ chế tương đương. Một token chỉ có chữ ký không tự ghi nhận lần tiêu thụ.

Không cho deadline trong token ghi đè thời hạn hiện hành của bản ghi. Phải xác định rõ token là bằng chứng cho phiên bản nào và nguồn nào có thẩm quyền quyết định khi dữ liệu khác nhau.

### 11.3. Hết hiệu lực khác hết thời gian lưu

Một báo giá hết hạn có thể cần giữ để kiểm toán, đối soát hoặc giải quyết retry. Bản ghi idempotency và sự kiện liên quan cũng có thời gian lưu riêng.

Tách ít nhất:

- valid_from: bắt đầu được sử dụng.
- expires_at: kết thúc quyền thực hiện thao tác.
- retention deadline: lúc dữ liệu đủ điều kiện được dọn theo chính sách lưu trữ.

Không xóa ngay toàn bộ bằng chứng tại expires_at nếu việc đó làm mất khả năng nhận diện retry hoặc điều tra quyết định đã xảy ra.

## 12. Thông điệp bất đồng bộ và bằng chứng đến muộn

### 12.1. event_time khác processing_time

Một callback có thể nói “đã phê duyệt lúc 10:04:59” nhưng chỉ đến hệ thống lúc 10:05:02.

Có hai loại chính sách:

| Chính sách | Điều phải chứng minh |
| --- | --- |
| Quyết định tại lúc hệ thống xử lý | decision_time hiện tại vẫn trong cửa sổ hiệu lực |
| Công nhận sự kiện đã xảy ra trước hạn | Nguồn event_time đáng tin cậy, ràng buộc nội dung, điều kiện tiếp nhận muộn và chống phát lại |

Chữ ký callback chỉ giúp xác minh nguồn và tính toàn vẹn theo giao thức; nó không tự quyết định sản phẩm có chấp nhận thông điệp đến muộn hay không.

Theo chính sách của bài, một callback tới sau hạn không được tự đặt accepted_at về quá khứ để vượt predicate. Nếu nghiệp vụ chọn công nhận sự kiện trước hạn, cần mô hình hóa bằng chứng và thời điểm nghiệp vụ đó rõ ràng, thay vì sửa timestamp cho vượt kiểm tra.

Client tự gửi một timestamp trong quá khứ không phải bằng chứng hợp lệ.

### 12.2. Kết quả đã quyết định trước hạn có thể được xử lý sau

Nếu transaction đã chấp nhận hợp lệ và ghi outbox trước hạn, một consumer xử lý outbox sau hạn đang thực hiện hệ quả của quyết định đã ghi.

Consumer cần:

- Xác thực sự kiện và ánh xạ tới quyết định đã commit.
- Chống xử lý trùng theo định danh sự kiện hoặc nghiệp vụ.
- Không tự tạo thêm quyết định chấp nhận.
- Kiểm tra điều kiện hiện hành riêng nếu tác động đó còn phụ thuộc trạng thái mới.

Ví dụ gửi email xác nhận sau hạn không làm lần chấp nhận trước hạn trở thành sai. Ngược lại, cấp một quyền sử dụng mới sau hạn không được ngụy trang thành phát lại email hoặc xử lý lại callback.

Outbox hỗ trợ liên kết quyết định local với việc phát thông điệp; nó không tự bảo đảm dịch vụ nhận chỉ gây tác động một lần. Nơi nhận vẫn cần idempotency hoặc cơ chế tương đương.

## 13. Ân hạn và các quy tắc dễ kéo dài quyền ngoài ý muốn

### 13.1. Ân hạn phải là chính sách công khai trong hệ thống

Nếu có grace period G, cần xác định một deadline hiệu lực duy nhất:

~~~text
effective_expires_at = nominal_expires_at + G
hợp lệ khi valid_from <= t < effective_expires_at
~~~

G do máy chủ quản lý, có giới hạn và gắn với phiên bản chính sách. Nếu ân hạn phụ thuộc actor hoặc trường hợp đặc biệt, phải kiểm tra quyền hưởng ân hạn và lưu căn cứ.

Không để API dùng nominal_expires_at, worker dùng effective_expires_at còn UI hiển thị một giờ thứ ba. Các thành phần phải chia sẻ cùng định nghĩa.

Ân hạn không nên là vài giây cộng rải rác trong code để làm kiểm thử hết lỗi. Nó thực sự kéo dài quyền nghiệp vụ và có thể ảnh hưởng giá, ưu tiên hoặc tài nguyên.

### 13.2. Giới hạn TTL và kiểm tra phép tính

Khi phát hành hoặc gia hạn:

- Không nhận duration âm, bằng 0 hoặc vượt giới hạn chính sách.
- Kiểm tra phép cộng thời gian không tràn hoặc vượt miền được hỗ trợ.
- Không cho deadline vượt mốc kết thúc chiến dịch nếu chính sách cấm.
- Tính một deadline chuẩn rồi lưu, không tính lại ở từng lần đọc.
- Không cho client chọn một giá trị quá lớn bằng cách sửa đơn vị giây thành mili giây hoặc ngược lại.

Một API nhận timeout kỹ thuật không được dùng thẳng trường đó làm TTL nghiệp vụ.

### 13.3. Quyền đặc biệt phải có dấu vết

Nếu hỗ trợ duyệt ngoại lệ sau hạn, nên có thao tác quản trị riêng với điều kiện, người phê duyệt và lý do. Không để một cờ force = true trong API công khai bỏ qua tất cả kiểm tra.

Ngoại lệ có thể cần phát hành một báo giá mới hoặc một phiên bản phê duyệt mới. Việc chỉnh accepted_at về trước deadline làm mất tính trung thực của nhật ký và che lấp quyết định ngoại lệ thực tế.

## 14. Kiểm thử ranh giới và tình huống tấn công

### 14.1. Kiểm thử hàm cửa sổ thời gian

Ví dụ Java dùng JUnit, giả sử withinWindow là hàm ở phần 3:

~~~java
@Test
void expirationBoundaryIsExclusive() {
    Instant start = Instant.parse("2026-11-22T03:00:00Z");
    Instant end = Instant.parse("2026-11-22T03:05:00Z");

    assertFalse(withinWindow(start.minusMillis(1), start, end));
    assertTrue(withinWindow(start, start, end));
    assertTrue(withinWindow(end.minusMillis(1), start, end));
    assertFalse(withinWindow(end, start, end));
    assertFalse(withinWindow(end.plusMillis(1), start, end));
}
~~~

Đây chỉ là unit test của predicate. Nó chưa chứng minh transaction lấy đúng thời gian, idempotency đúng hoặc worker không tranh chấp sai.

Độ lệch một mili giây trong ví dụ cần thay bằng đơn vị phù hợp độ chính xác chuẩn của hệ thống. Cũng cần kiểm thử đường parse, lưu DB và đọc lại để xác nhận deadline không đổi ngoài quy tắc chuẩn hóa.

### 14.2. Ma trận kiểm thử nghiệp vụ

| Tình huống | Cách tạo điều kiện | Kết quả cần chứng minh |
| --- | --- | --- |
| Trước valid_from | Quyết định ngay trước mốc bắt đầu | Không tạo đơn |
| Đúng valid_from | Quyết định bằng điểm đầu | Có thể chấp nhận nếu đủ điều kiện khác |
| Ngay trước expires_at | Dùng mốc nhỏ hơn một đơn vị chuẩn | Có thể chấp nhận |
| Đúng expires_at | Hai instant bằng nhau | Từ chối vì hết hạn |
| Ngay sau expires_at | Lớn hơn một đơn vị chuẩn | Từ chối |
| Chờ khóa qua hạn | Chặn request trước khi có khóa | Đọc giờ mới và từ chối |
| Transaction bắt đầu trước hạn | Cho lấy khóa sau hạn | Không dùng giờ bắt đầu transaction |
| Quyết định trước hạn, commit sau | Trì hoãn commit có kiểm soát | Theo đúng hợp đồng thời điểm quyết định |
| Hai request chấp nhận | Hai connection cùng dùng một báo giá | Tối đa một đơn có hiệu lực |
| Retry sau mất phản hồi | Commit rồi mất kết nối, gửi lại cùng key | Cùng đơn, không có tác động mới |
| Retry sau rollback | Hủy lần đầu, retry sau deadline | Lấy giờ mới và từ chối |
| Cùng key khác version | Đổi phiên bản trong cùng key | Từ chối xung đột |
| Worker chạy muộn | Không chạy worker sau deadline | API vẫn từ chối |
| Worker chạy lặp | Hai worker xử lý cùng báo giá | Không có hai lần chuyển hoặc tác động trùng |
| Gia hạn đua worker | Gia hạn trước khi worker có khóa | Worker đọc lại deadline mới |
| Gia hạn đã quá hạn | Giữ OPEN nhưng thời gian đã qua | Không hồi sinh báo giá |
| Chấp nhận đua hết hạn | Điều phối hai transaction | Một kết quả kết thúc hợp lệ |
| Sửa thời gian client | Gửi now hoặc sentAt trong quá khứ | Không ảnh hưởng nguồn thời gian quyết định |
| Sai subject hoặc tenant | Dùng mã báo giá của người khác | Từ chối theo quyền đối tượng |
| Đổi giá hoặc hàng hóa | Giữ deadline, sửa nội dung request | Không dùng báo giá cho nội dung khác |
| Token phiên bản cũ | Gia hạn hoặc sửa báo giá rồi dùng token cũ | Xử lý theo quy tắc phiên bản, không ghi đè dữ liệu chuẩn |
| Cache còn OPEN | Dùng bản sao cũ sau deadline | Đường ghi vẫn từ chối |
| Callback đến muộn | event_time trước hạn, xử lý sau hạn | Theo chính sách đã công bố, không âm thầm backdate |
| Độ chính xác khác nhau | Đi qua JSON, driver và DB | Không kéo dài quyền ngoài deadline chuẩn |
| Mốc lịch địa phương | Ngày có thay đổi offset tại timezone áp dụng | Chuyển đúng thành instant đã quy định |
| Deadline bị tràn | TTL quá lớn hoặc sai đơn vị | Bị từ chối khi phát hành hoặc gia hạn |

### 14.3. Điều phối kiểm thử đồng thời

Dùng hệ quản trị mục tiêu và nhiều connection thật cho các kịch bản khóa. Một cách tổ chức:

1. Transaction A giữ khóa báo giá.
2. Transaction B bắt đầu trước deadline và bị chặn ở bước lấy khóa.
3. Điều khiển nguồn thời gian thử nghiệm hoặc mốc thực thi để B có khóa sau deadline.
4. Nhả A cho B tiếp tục.
5. Xác nhận B dùng thời gian sau chờ khóa và không tạo đơn.

Bài kiểm thử tích hợp với nguồn thời gian thật của DB còn phải kiểm tra ngữ nghĩa của hàm lấy giờ. Chỉ mock timeSource trả giá trị mong muốn sẽ không phát hiện implementation dùng giờ bắt đầu transaction.

Không dựa hoàn toàn vào sleep ngẫu nhiên. Dùng barrier, latch hoặc cơ chế điều phối để chứng minh đã chạm đúng điểm tranh chấp. Nếu cần chờ đồng hồ thật trong một kiểm thử tích hợp, phải quan sát và khẳng định các mốc liên quan thay vì đoán bằng thời gian ngủ.

Sau mỗi kịch bản, kiểm tra dữ liệu đã commit:

- Có tối đa một đơn gắn với báo giá.
- accepted_at nằm trong khoảng hiệu lực của phiên bản đã dùng.
- Báo giá ACCEPTED không bị worker đổi thành EXPIRED.
- Báo giá bị từ chối không có đơn tạo dở.
- Idempotency trỏ đến đúng kết quả đã commit.
- Các thay đổi phiên bản và deadline có dấu vết phù hợp.

## 15. Quan sát quyết định gần deadline

Audit log hữu ích nên thể hiện:

- Tenant, quote_id, actor và subject theo quyền truy cập log.
- Trạng thái và phiên bản đã quyết định.
- valid_from, expires_at và decision_time theo biểu diễn chuẩn.
- Kết quả, mã lý do và order_id nếu có.
- Thông tin liên kết request, idempotency và transaction phù hợp.
- Dấu hiệu replay, gia hạn hoặc ngoại lệ được phê duyệt.

Có thể đo khoảng cách decision_time − expires_at để biết các lần từ chối nằm sát biên hay có dấu hiệu cố dùng quyền từ lâu. Chỉ số này cần được diễn giải cùng trạng thái và hợp đồng thời gian, không dùng giờ phản hồi HTTP để thay thế.

Metric vận hành có thể gồm:

- Tỷ lệ hết hạn, chưa có hiệu lực và sai phiên bản.
- Số lượng request phải chờ khóa qua deadline.
- Độ trễ worker đánh dấu hết hạn.
- Tỷ lệ retry, idempotency replay và xung đột key.
- Sai lệch đồng hồ hoặc tình trạng không tin cậy của nguồn thời gian.
- Số lần gia hạn và ngoại lệ theo nhóm chính sách.

Không ghi token, chữ ký bí mật hoặc dữ liệu thanh toán nhạy cảm vào log. Tránh dùng từng quote_id hay subject_id làm nhãn metric có số lượng giá trị không giới hạn.

Nếu người dùng phản ánh “tôi bấm trước khi hết giờ”, audit phải giúp phân biệt lúc client bấm, lúc request tới và lúc hệ thống quyết định. Cách thông báo lỗi nên phù hợp hợp đồng sản phẩm, chẳng hạn cung cấp lựa chọn xin báo giá mới nếu chính sách cho phép.

## 16. Tự phân tích một chuỗi thời gian

Báo giá Q có deadline 10:05:00.000, state OPEN, version 7. Chính sách dùng thời điểm quyết định sau khi có khóa.

| Tình huống | Kết luận |
| --- | --- |
| A gửi lúc 10:04:59.800, có khóa và quyết định lúc 10:05:00.010 | Hết hạn; thời điểm gửi không cứu được quyền |
| B quyết định lúc 10:04:59.990, commit lúc 10:05:00.020 | Hợp lệ theo chính sách của bài |
| C đã tạo đơn thành công trước hạn, retry cùng key lúc 10:05:02 | Trả kết quả cũ, không tạo đơn mới |
| D thấy Q vẫn OPEN lúc 10:05:10 vì worker dừng | Vẫn hết hạn; OPEN chưa đủ |
| E gia hạn hợp lệ trước hạn lên version 8, rồi có request mới dùng version 7 | Không được dùng phiên bản cũ để bỏ qua kiểm tra hiện hành |
| F gửi callback có timestamp cũ sau deadline | Không tự đặt accepted_at lùi lại; áp dụng chính sách tiếp nhận sự kiện |

Nếu không thể giải thích nhất quán các trường hợp này bằng một tập quy tắc ngắn, hệ thống có thể đang dùng nhiều định nghĩa hết hạn khác nhau.

## 17. Checklist áp dụng

- Cửa sổ hiệu lực có ghi rõ điểm đầu bao gồm và điểm cuối loại trừ không?
- Mọi đường xử lý có coi đúng expires_at là hết hạn không?
- Deadline có do máy chủ cấp và gắn với đúng tenant, subject, nội dung, phiên bản không?
- Nguồn thời gian nào có thẩm quyền và có đáng tin cậy không?
- decision_time được lấy sau khi có đủ khóa hay chỉ sau khi bắt đầu request?
- Implementation của hàm lấy giờ có đúng ngữ nghĩa sau khi chờ khóa không?
- Độ chính xác giữa ứng dụng, DB, token và API có thống nhất không?
- State OPEN có được kiểm tra cùng thời gian thay vì dùng riêng không?
- Quyết định, tạo đơn và idempotency có cùng ranh giới commit không?
- Retry sau rollback có lấy giờ mới không?
- Gia hạn và worker có đọc lại dữ liệu hiện hành theo cùng giao thức đồng thời không?
- Phát lại kết quả thành công có tránh tạo thêm tác động không?
- Cache, dọn dữ liệu và callback muộn có đang vô tình kéo dài quyền không?
- Grace period hoặc ngoại lệ có được định nghĩa, kiểm soát quyền và kiểm toán không?
- Kiểm thử có bao phủ trước biên, đúng biên, sau biên và chờ khóa qua biên không?

Ranh giới hết hạn được bảo vệ khi một quyết định có thể chỉ ra rõ quyền nào, phiên bản nào, nguồn thời gian nào và instant nào đã được dùng. Cùng định nghĩa đó phải tiếp tục đúng khi request chạy đồng thời, worker chậm, đồng hồ khác độ chính xác và người dùng cố phát lại thao tác.
