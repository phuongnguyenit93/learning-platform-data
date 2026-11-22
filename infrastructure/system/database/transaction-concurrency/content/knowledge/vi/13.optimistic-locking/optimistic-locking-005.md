# Giới hạn của dấu thời gian khi dùng thay số phiên bản

Trong optimistic locking (khóa lạc quan), ứng dụng thường đọc một hàng, cho người dùng hoặc một luồng xử lý thay đổi dữ liệu, rồi chỉ ghi nếu hàng vẫn ở phiên bản mà nó đã đọc. Một cách triển khai là dùng cột số phiên bản tăng dần. Một cách khác là dùng dấu thời gian cập nhật gần nhất, chẳng hạn updated_at, làm token để phát hiện dữ liệu đã thay đổi.

Dấu thời gian có vẻ tiện lợi vì nhiều bảng vốn đã có cột created_at hoặc updated_at. Tuy nhiên, thời gian được tạo từ đồng hồ không mặc nhiên là một mã phiên bản duy nhất. Hai lần cập nhật có thể nhận cùng một giá trị thời gian; đồng hồ có thể lệch hoặc bị điều chỉnh; độ chính xác lưu trữ có thể thấp hơn độ chính xác mà ứng dụng tưởng rằng nó đang dùng. Khi token không thay đổi sau một lần ghi, một transaction cũ có thể vẫn vượt qua điều kiện kiểm tra và ghi đè dữ liệu mới.

**Dấu thời gian mô tả thời điểm theo đồng hồ; số phiên bản mô tả thứ tự thay đổi của một đối tượng.** Hai ý nghĩa này có thể liên quan, nhưng không thể mặc định thay thế cho nhau.

## 1. Dùng timestamp làm token optimistic locking

Một mẫu optimistic locking phổ biến là đọc giá trị phiên bản cùng dữ liệu, sau đó đưa phiên bản đã đọc vào điều kiện UPDATE.

Ví dụ bảng tài liệu:

~~~sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Ứng dụng đọc hàng và nhận được:

~~~text
document_id = 42
title       = "Bản kế hoạch"
updated_at  = 2026-11-14 09:30:15.123456
~~~

Khi lưu, ứng dụng yêu cầu DBMS chỉ cập nhật nếu updated_at vẫn bằng giá trị đã đọc:

~~~sql
UPDATE documents
SET title = 'Bản kế hoạch mới',
    body = 'Nội dung đã chỉnh sửa',
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = 42
  AND updated_at = TIMESTAMP '2026-11-14 09:30:15.123456';
~~~

Nếu đúng một hàng được cập nhật, token vẫn khớp và thao tác thành công. Nếu không có hàng nào được cập nhật, hàng có thể đã bị sửa, bị xóa hoặc không còn khớp với điều kiện.

Cách làm này chỉ đáng tin khi mỗi lần thay đổi nội dung đều tạo ra một updated_at khác giá trị trước đó và mọi đường ghi đều cập nhật cột này đúng cách. Nếu hai lần cập nhật được lưu với cùng timestamp, token không thay đổi. Một client cũ có thể gửi lại token đó và câu UPDATE của nó vẫn khớp.

Ngoài ra, ứng dụng phải phân biệt trường hợp không có hàng được cập nhật với lỗi kết nối hoặc lỗi SQL. Số hàng ảnh hưởng bằng 0 thường là tín hiệu xung đột hoặc hàng không tồn tại; nó không phải bằng chứng duy nhất cho một nguyên nhân cụ thể.

## 2. Giới hạn về độ phân giải thời gian

Đồng hồ có thể đọc thời gian với độ chính xác cao, nhưng cột dữ liệu hoặc driver có thể chỉ lưu một số chữ số phần thập phân nhất định. Ví dụ, hệ thống lưu timestamp đến mili giây trong khi hai lần ghi xảy ra trong cùng một mili giây.

Giả sử cột chỉ lưu đến mili giây:

| Sự kiện | Thời điểm thực tế | Giá trị lưu được |
|---|---|---|
| Client A đọc hàng | 10:15:20.1231 | 10:15:20.123 |
| Transaction B cập nhật | 10:15:20.1234 | 10:15:20.123 |
| Client A gửi cập nhật cũ | 10:15:20.1238 | Token vẫn là 10:15:20.123 |

B đã thay đổi hàng, nhưng updated_at vẫn bằng giá trị A đã đọc. Điều kiện WHERE updated_at = old_timestamp của A vẫn đúng. Câu UPDATE của A có thể ghi đè nội dung B vừa lưu mà không phát hiện xung đột.

Đây là va chạm timestamp (timestamp collision): nhiều sự kiện khác nhau ánh xạ vào cùng một giá trị thời gian được lưu trữ.

### Độ chính xác khai báo không phải độ chính xác thực tế

Một kiểu timestamp có thể cho phép sáu chữ số phần thập phân, nhưng điều đó không bảo đảm đồng hồ hoặc môi trường chạy tạo ra các giá trị khác nhau cách nhau một microsecond. Độ chính xác thực tế còn phụ thuộc:

- Nguồn đồng hồ của DBMS hoặc hệ điều hành.
- Độ phân giải phần cứng và hệ điều hành.
- Cách DBMS lấy thời gian cho câu lệnh hoặc transaction.
- Độ chính xác kiểu dữ liệu của cột.
- Việc driver hoặc tầng ứng dụng làm tròn, cắt bớt hay chuyển đổi giá trị.
- Cách dữ liệu được serialize và deserialize qua API.

Vì vậy, không nên kết luận rằng timestamp có sáu chữ số phần thập phân thì không thể trùng nhau. Nhiều lần ghi trong cùng khoảng thời gian được biểu diễn vẫn có thể nhận cùng token.

### Làm tròn và cắt bớt có thể tạo va chạm

Giả sử DBMS lưu timestamp với ba chữ số phần thập phân, còn ứng dụng nhận giá trị có sáu chữ số. Nếu driver chuyển đổi không nhất quán, giá trị mà ứng dụng gửi lại trong điều kiện WHERE có thể khác giá trị DBMS lưu, dẫn đến xung đột giả.

Ngược lại, nếu cả hai giá trị được làm tròn về cùng một timestamp, một thay đổi mới có thể không tạo token khác và gây bỏ sót xung đột.

Ứng dụng nên dùng cùng kiểu dữ liệu, cùng độ chính xác và cùng quy tắc chuyển đổi khi đọc và ghi token. Không tự chuyển timestamp sang chuỗi với định dạng hoặc số chữ số khác nhau rồi dùng chuỗi đó để so sánh phiên bản.

## 3. Đồng hồ không phải bộ đếm phiên bản

Một bộ đếm phiên bản tăng dần thể hiện quan hệ trước–sau giữa các lần thay đổi. Đồng hồ thời gian thể hiện thời điểm theo một nguồn đo thời gian. Hai khái niệm có đặc tính khác nhau.

Ví dụ, hai lần cập nhật có thể xảy ra theo thứ tự:

~~~text
Cập nhật A xảy ra trước
Cập nhật B xảy ra sau
~~~

Một version counter có thể tăng từ 17 lên 18 rồi 19. Nhưng timestamp không nhất thiết tăng tương ứng. Hai lần cập nhật có thể nhận cùng timestamp, hoặc lần cập nhật sau có thể nhận thời gian nhỏ hơn nếu đồng hồ bị điều chỉnh.

### Đồng hồ hệ thống có thể bị điều chỉnh

Wall clock (đồng hồ lịch) có thể thay đổi do:

- Đồng bộ NTP.
- Người quản trị chỉnh giờ.
- Máy ảo được khôi phục từ snapshot.
- Đồng hồ phần cứng hoặc hệ điều hành hiệu chỉnh sai lệch.
- Chuyển đổi cấu hình thời gian hoặc lỗi vận hành.

Nếu đồng hồ bị lùi, một lần cập nhật sau có thể tạo updated_at nhỏ hơn giá trị cũ. Nếu ứng dụng giả định timestamp luôn tăng, giả định đó không còn đúng.

Một số API cung cấp monotonic clock để đo khoảng thời gian trong một tiến trình. Monotonic clock không bị lùi theo các lần chỉnh đồng hồ lịch, nhưng thường không phải timestamp lịch có thể lưu vào database và so sánh xuyên máy. Nó không tự tạo thành token phiên bản dùng chung giữa nhiều instance.

### UTC giải quyết múi giờ, không giải quyết tính duy nhất

Lưu thời gian ở UTC giúp tránh nhầm lẫn khi nhiều service ở các múi giờ khác nhau. Tuy nhiên, UTC không làm đồng hồ có độ phân giải vô hạn và cũng không bảo đảm mỗi lần ghi có một giá trị khác nhau.

UTC trả lời câu hỏi “thời điểm được biểu diễn theo múi giờ nào?”. Nó không trả lời câu hỏi “đây là lần cập nhật thứ mấy của hàng?”.

## 4. Đồng hồ của nhiều máy có thể lệch nhau

Nếu ứng dụng tạo timestamp ở phía client, nhiều máy có thể có thời gian khác nhau. Máy A có thể nhanh hơn máy B vài giây; khi B cập nhật sau A, timestamp do B gửi có thể nhỏ hơn timestamp đã lưu.

Ví dụ:

| Máy | Thời gian thực gần đúng | Đồng hồ cục bộ |
|---|---|---|
| App server A | 12:00:00 | 12:00:03 |
| App server B | 12:00:01 | 11:59:58 |

B thực hiện cập nhật sau A nhưng tạo timestamp nhỏ hơn. Nếu logic ứng dụng dùng timestamp để xác định bản ghi mới nhất hoặc để suy luận thứ tự cập nhật, kết quả có thể sai.

Ngay cả khi cả hai máy đồng bộ NTP, vẫn tồn tại sai số đồng bộ và độ trễ cập nhật. NTP làm giảm độ lệch đồng hồ; nó không tạo ra một bộ đếm toàn cục, duy nhất và tăng nghiêm ngặt cho mọi lần ghi.

### Tạo timestamp ở DBMS có tốt hơn không?

Tạo updated_at ở DBMS thường giúp thống nhất nguồn thời gian cho các writer đi qua cùng database. Ví dụ:

~~~sql
UPDATE documents
SET body = 'Nội dung mới',
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = 42;
~~~

Điều này tránh việc mỗi application server tự gửi một giờ khác nhau. Tuy nhiên, nó vẫn không bảo đảm hai câu UPDATE trong cùng một khoảng thời gian nhận timestamp khác nhau. Nó cũng không tự bảo vệ những đường ghi bỏ qua cột updated_at.

Một số DBMS còn phân biệt thời gian bắt đầu transaction, thời gian bắt đầu câu lệnh và thời gian đồng hồ thực tại thời điểm gọi hàm. Ví dụ trong PostgreSQL, CURRENT_TIMESTAMP/now() phản ánh thời điểm bắt đầu transaction; clock_timestamp() đọc thời gian thực tại lúc hàm được gọi. Chọn hàm thời gian khác có thể thay đổi ý nghĩa thời điểm được ghi, nhưng không biến timestamp thành version counter duy nhất.

## 5. Cùng timestamp khiến optimistic locking bỏ sót xung đột

Xem hai client cùng đọc một tài liệu với token T:

~~~text
Client A                         Client B
--------                         --------
Đọc body = "Bản 1"               Đọc body = "Bản 1"
updated_at = T                   updated_at = T
                                 |
                                 v
                                 Ghi "Bản 2"
                                 updated_at vẫn = T
Gửi bản chỉnh sửa từ "Bản 1"
WHERE updated_at = T
                                 |
                                 v
Điều kiện vẫn khớp
A ghi "Bản A"
~~~

Nếu B và A được lưu trong cùng một giá trị timestamp T, A không nhận ra B đã cập nhật. Kết quả cuối có thể làm mất nội dung B.

Một optimistic locking token phải thay đổi mỗi khi đối tượng thay đổi theo quy tắc của hệ thống. Timestamp chỉ đáp ứng điều kiện này nếu hệ thống có bảo đảm rõ ràng rằng mỗi lần cập nhật sẽ tạo giá trị khác token trước, kể cả khi nhiều writer cập nhật rất gần nhau. Nhiều hệ thống không có bảo đảm đó.

### Có thể cộng thêm một đơn vị thời gian để tránh trùng không?

Một cách thường được đề xuất là đặt:

~~~sql
updated_at = GREATEST(CURRENT_TIMESTAMP, updated_at + INTERVAL '1 millisecond')
~~~

Cách này cố buộc timestamp mới lớn hơn timestamp cũ. Tuy nhiên, nó có một số giới hạn:

- Độ dài khoảng thời gian phải phù hợp với kiểu dữ liệu và cú pháp của DBMS.
- Khi đồng hồ lùi, giá trị có thể đi trước thời gian thực.
- Nếu nhiều writer không được điều phối trên cùng hàng, phép tính vẫn cần được thực hiện nguyên tử.
- Timestamp lúc này không còn phản ánh chính xác thời điểm thực tế mà phản ánh một thứ tự nhân tạo.
- Mọi đường ghi phải tuân thủ cùng công thức.
- Việc so sánh với giá trị timestamp được chuyển đổi qua API vẫn phải giữ nguyên độ chính xác.

Nếu mục tiêu là tạo thứ tự thay đổi duy nhất cho một hàng, tăng một version counter trong cùng câu UPDATE thường rõ ràng và dễ bảo vệ hơn.

## 6. Timestamp có thể gặp vấn đề ABA

ABA là tình huống giá trị dữ liệu thay đổi từ A sang B rồi quay lại A. Một client đọc giá trị A trước đó có thể chỉ so sánh nội dung và tưởng rằng dữ liệu chưa thay đổi.

Ví dụ:

1. Client X đọc tiêu đề là “Draft”.
2. Client Y đổi tiêu đề thành “Review”.
3. Client Z đổi tiêu đề trở lại “Draft”.
4. Client X gửi cập nhật dựa trên nội dung “Draft” đã đọc từ đầu.

Nếu chỉ so sánh giá trị tiêu đề, X không thể biết hàng đã trải qua hai lần thay đổi. Version counter tăng từ 5 lên 7 sẽ phát hiện sự thay đổi này dù nội dung quay lại giống ban đầu.

Timestamp có thể phát hiện ABA nếu mỗi lần thay đổi tạo ra timestamp khác nhau. Nhưng nếu hai lần thay đổi xảy ra trong cùng khoảng độ phân giải, hoặc timestamp được khôi phục về giá trị cũ, token có thể quay lại giá trị trước đó. Khi đó, timestamp không cung cấp bảo đảm chống ABA như một version counter được tăng ở mọi lần ghi.

Một token phiên bản tốt phản ánh lịch sử thay đổi của đối tượng, không chỉ giá trị nội dung hiện tại hoặc thời điểm gần đúng.

## 7. Timestamp không nhất thiết đại diện cho mọi đường ghi

Một cột updated_at thường được cập nhật bởi code ứng dụng hoặc trigger. Nếu có một đường ghi quên cập nhật cột này, token không phản ánh thay đổi dữ liệu.

Ví dụ:

~~~sql
-- Đường ghi A cập nhật cả dữ liệu và timestamp.
UPDATE documents
SET body = 'Nội dung mới',
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = 42;

-- Đường ghi B chỉ cập nhật dữ liệu.
UPDATE documents
SET body = 'Nội dung khác'
WHERE document_id = 42;
~~~

Đường ghi B làm thay đổi nội dung nhưng giữ nguyên updated_at. Client đang giữ token cũ có thể không phát hiện được thay đổi.

Các nguồn ghi cần kiểm tra gồm:

- API của ứng dụng.
- Batch job và scheduled job.
- Worker xử lý message.
- Script quản trị hoặc migration.
- Stored procedure.
- Service khác dùng chung database.
- Trigger hoặc thao tác cập nhật trực tiếp từ công cụ vận hành.

Nếu timestamp được dùng làm token concurrency, phải bảo đảm mọi đường ghi liên quan đều cập nhật nó. Có thể dùng trigger hoặc một quy ước tập trung ở tầng database, nhưng vẫn phải xử lý vấn đề độ phân giải và tính duy nhất của timestamp.

## 8. So sánh timestamp, version counter và token phiên bản của DBMS

| Đặc điểm | Timestamp làm token | Version counter | Token phiên bản do DBMS cấp |
|---|---|---|---|
| Ý nghĩa | Thời điểm theo đồng hồ | Số thứ tự thay đổi | Mã phiên bản theo cơ chế DBMS |
| Có thể trùng? | Có, tùy độ phân giải và nguồn đồng hồ | Không nếu tăng nguyên tử đúng cách trong phạm vi đối tượng | Phụ thuộc cơ chế; cần hiểu phạm vi và hợp đồng |
| Có bảo đảm tăng? | Không mặc nhiên | Có nếu mỗi lần ghi tăng đúng cách | Tùy DBMS |
| Phụ thuộc đồng hồ | Có | Không | Thường không nếu token là counter |
| Chống ABA | Chỉ khi token chắc chắn thay đổi mỗi lần ghi | Có nếu mọi lần ghi đều tăng | Tùy token và cách sử dụng |
| Dễ đọc với con người | Có | Có thể đọc như số | Có thể là giá trị nhị phân hoặc mã kỹ thuật |
| Dùng cho audit | Phù hợp để ghi thời điểm | Không biểu diễn thời điểm | Không nhất thiết biểu diễn thời điểm |
| Dùng cho optimistic locking | Có điều kiện, cần kiểm soát chặt | Thường phù hợp | Phù hợp nếu DBMS cam kết token thay đổi theo cập nhật |

### Version counter

Một version counter thường là số nguyên tăng mỗi lần cập nhật:

~~~sql
UPDATE documents
SET body = 'Nội dung mới',
    version = version + 1
WHERE document_id = 42
  AND version = 17;
~~~

Nếu một hàng được cập nhật, phiên bản trở thành 18. Client khác còn giữ version 17 sẽ không cập nhật được nữa.

Phép so sánh và tăng version diễn ra trong cùng một câu lệnh UPDATE, nên DBMS có thể điều phối các writer. Cần bảo đảm mọi đường ghi đều tăng version; không được có một service sửa body mà bỏ qua version.

Với một hàng được cập nhật thường xuyên, BIGINT cung cấp không gian giá trị lớn. Nếu có nguy cơ tràn số, cần có chính sách kiểu dữ liệu và vòng đời token phù hợp. Không được reset version tùy tiện trong khi client cũ còn có thể gửi token trước đó.

### SQL Server rowversion

SQL Server cung cấp kiểu dữ liệu rowversion, một giá trị nhị phân do DBMS tự sinh và thay đổi khi hàng có cột rowversion được cập nhật. Ứng dụng có thể đọc giá trị đó rồi đưa vào điều kiện WHERE khi cập nhật.

~~~sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY,
    body NVARCHAR(MAX) NOT NULL,
    row_version ROWVERSION
);
~~~

Mẫu cập nhật:

~~~sql
UPDATE documents
SET body = @newBody
WHERE document_id = @id
  AND row_version = @versionRead;
~~~

Nếu không có hàng nào được cập nhật, token đã thay đổi hoặc hàng không còn tồn tại. SQL Server rowversion không phải thời gian lịch; nó không cho biết ngày giờ cập nhật. Tên cũ TIMESTAMP trong SQL Server là synonym của rowversion, không phải kiểu lưu ngày giờ. Vì vậy, không được nhầm timestamp trong SQL Server với timestamp thời gian ở các hệ quản trị khác.

### HTTP ETag

Ở tầng HTTP, ETag có thể làm token cho optimistic concurrency. Client đọc tài nguyên và nhận ETag, sau đó gửi PUT/PATCH với điều kiện If-Match:

~~~http
GET /documents/42
ETag: "v17"
~~~

~~~http
PATCH /documents/42
If-Match: "v17"
Content-Type: application/json
~~~

Nếu representation đã thay đổi và ETag không còn khớp, server trả về lỗi precondition failed, thường là HTTP 412. ETag có thể được tạo từ version counter, hash nội dung hoặc một token khác. Nếu ETag được tạo từ timestamp, nó kế thừa các giới hạn va chạm và đồng hồ của timestamp đó.

## 9. Nếu vẫn phải dùng timestamp làm token

Có những hệ thống muốn tận dụng cột updated_at sẵn có để giảm thay đổi schema hoặc tương thích API. Trong trường hợp đó, cần làm rõ hợp đồng của token và giới hạn còn lại.

### Tạo thời gian ở một nơi thống nhất

Ưu tiên DBMS tạo timestamp nếu tất cả writer dùng cùng database. Tránh để nhiều application server tự tạo giờ nếu không cần thiết. Lưu UTC để giảm lỗi biểu diễn múi giờ.

Tuy vậy, đây chỉ là giảm một số nguồn sai lệch. Nó không bảo đảm mỗi lần ghi có token duy nhất.

### Giữ độ chính xác nhất quán từ database đến client

Xác định precision của cột, kiểu dữ liệu trong driver, format JSON và cách client gửi lại token. Không làm tròn hoặc cắt bớt giá trị khi serialize.

Nếu timestamp được truyền qua chuỗi, hãy dùng định dạng chuẩn có timezone/UTC và giữ đủ phần thập phân mà database trả về. Tốt hơn là giữ token nguyên dạng được API cấp thay vì tự parse rồi tái tạo.

### Cập nhật token trong cùng câu lệnh có điều kiện

Không thực hiện kiểm tra timestamp bằng SELECT riêng rồi mới UPDATE không có điều kiện. Việc so sánh token phải nằm trong cùng thao tác ghi:

~~~sql
UPDATE documents
SET body = :new_body,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = :id
  AND updated_at = :old_updated_at;
~~~

Kiểm tra số hàng bị ảnh hưởng. Nếu không có hàng nào, trả kết quả xung đột hoặc không tìm thấy theo quy ước API.

### Bảo đảm timestamp thay đổi mỗi lần ghi

Nếu tiếp tục dùng timestamp làm token, cần có cơ chế bảo đảm giá trị mới khác giá trị trước đó trong mọi lần ghi. Có thể phối hợp timestamp với một counter hoặc token phụ, nhưng khi đã có counter thì counter mới là phần cung cấp tính duy nhất và thứ tự thay đổi.

Một lựa chọn là dùng cặp (updated_at, version). Điều kiện UPDATE so sánh version; timestamp chỉ phục vụ hiển thị và audit. Cách này giữ rõ hai mục đích thay vì bắt một giá trị thời gian đảm nhiệm cả hai.

### Kiểm thử các tình huống biên

- Hai transaction cập nhật cùng một hàng trong cùng mili giây hoặc microsecond.
- Nhiều application instance có đồng hồ lệch nhau.
- Đồng hồ bị chỉnh lùi hoặc tiến nhanh.
- Driver làm tròn timestamp khi đọc và gửi lại.
- Một batch job cập nhật dữ liệu nhưng quên updated_at.
- Client giữ token cũ lâu rồi gửi cập nhật.
- Dữ liệu được khôi phục từ backup hoặc import có timestamp cũ.
- Hai lần cập nhật đưa nội dung về lại giá trị trước đó (ABA).

Nếu không thể chứng minh timestamp thay đổi duy nhất cho mọi lần ghi, không nên xem nó là concurrency token có bảo đảm.

## 10. Một thiết kế thực tế: tách thời gian cập nhật và phiên bản

Thông thường nên giữ hai trường với hai trách nhiệm riêng:

~~~sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY,
    body TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL
);
~~~

Câu UPDATE:

~~~sql
UPDATE documents
SET body = :new_body,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = :id
  AND version = :version_read;
~~~

Ở đây:

- version dùng để phát hiện cập nhật cạnh tranh.
- updated_at ghi lại thời điểm cập nhật gần nhất để hiển thị, tìm kiếm hoặc audit.
- Nếu số hàng bị ảnh hưởng bằng 1, cập nhật thành công.
- Nếu số hàng bị ảnh hưởng bằng 0, client đã dùng version cũ hoặc hàng không tồn tại.

Có thể đọc version và updated_at cùng nhau trong API. Client không cần tự suy ra thứ tự cập nhật từ timestamp.

Nếu database hỗ trợ token phiên bản riêng như SQL Server rowversion, có thể dùng token đó thay cho version counter tự quản lý. Dù chọn cách nào, mọi đường ghi phải tuân theo cùng một hợp đồng.

## 11. Các lỗi thường gặp khi dùng timestamp thay version

### Cho rằng timestamp luôn duy nhất

Timestamp biểu diễn thời gian, không phải sequence. Nhiều lần ghi có thể cùng giá trị nếu chúng nằm trong cùng khoảng độ phân giải.

### Chỉ tăng precision của cột

Tăng từ mili giây lên microsecond hoặc nanosecond có thể giảm khả năng va chạm, nhưng không loại bỏ nó. Độ chính xác khai báo không đồng nghĩa nguồn thời gian tạo ra giá trị duy nhất.

### Dùng giờ từ application server

Nhiều instance có thể lệch đồng hồ. Client B cập nhật sau nhưng timestamp nhỏ hơn client A. UTC không giải quyết sai lệch đồng hồ giữa máy.

### So sánh timestamp đã chuyển đổi

Client có thể cắt bớt phần thập phân hoặc chuyển múi giờ khi serialize. Token gửi lại không còn đúng giá trị DBMS đã trả. Một số trường hợp gây conflict giả; trường hợp khác làm token không đổi sau cập nhật.

### Có đường ghi bỏ qua updated_at

Một batch job hoặc service khác cập nhật nội dung nhưng không đổi timestamp. Optimistic locking không phát hiện thay đổi đó.

### Dùng timestamp để xác định thứ tự toàn cục

Ngay cả khi timestamp tăng trên một hàng, nó không nhất thiết cho thứ tự nhất quán giữa nhiều hàng hoặc nhiều database. Không nên dùng nó như một sequence toàn cục nếu hệ thống không có cơ chế cấp thứ tự tương ứng.

## 12. Cách lựa chọn token cho optimistic locking

| Nhu cầu | Lựa chọn |
|---|---|
| Chỉ cần biết thời điểm cập nhật để hiển thị hoặc audit | updated_at |
| Cần phát hiện mọi lần thay đổi của một hàng | Version counter hoặc token phiên bản do DBMS cấp |
| Cần đồng bộ cập nhật từ HTTP client | ETag dựa trên version hoặc hash có hợp đồng rõ ràng |
| Muốn dùng cột timestamp sẵn có | Chỉ dùng nếu có bảo đảm token thay đổi mỗi lần ghi; kiểm thử precision và mọi đường ghi |
| Cần thứ tự thay đổi trong một đối tượng | Counter tăng nguyên tử |
| Cần thứ tự toàn cục giữa nhiều đối tượng hoặc node | Sequence/ordering service phù hợp với phạm vi yêu cầu, không suy luận từ wall clock |

Khi thiết kế optimistic locking, hãy hỏi token có thay đổi ở mọi lần cập nhật không, có thể bị tái sử dụng không, phạm vi duy nhất là gì, và thao tác so sánh token có nguyên tử với thao tác ghi không. Những câu hỏi này quan trọng hơn việc timestamp có bao nhiêu chữ số phần thập phân.

Dấu thời gian vẫn rất hữu ích để mô tả thời điểm dữ liệu được tạo hoặc sửa. Nhưng nếu dùng nó thay số phiên bản, hệ thống phải đối mặt với độ phân giải hữu hạn, va chạm, sai lệch đồng hồ, điều chỉnh thời gian và các đường ghi không cập nhật token. Với concurrency control, version counter tăng nguyên tử hoặc token phiên bản chuyên dụng thường cung cấp hợp đồng rõ ràng hơn. Tách updated_at cho mục đích thời gian và version cho mục đích phát hiện xung đột giúp dữ liệu dễ hiểu, dễ kiểm thử và đáng tin cậy hơn.
