# ACID liên hệ với ràng buộc, nhật ký và cơ chế phục hồi như thế nào

Một giao dịch cơ sở dữ liệu có thể cập nhật nhiều hàng, nhiều bảng và phải xử lý cả việc nhiều người cùng thao tác lẫn nguy cơ tiến trình bị dừng giữa chừng. Để hiểu vì sao hệ thống vẫn có thể cam kết một kết quả đúng, cần nối bốn tính chất **ACID** với ba nhóm cơ chế cụ thể:

- **Ràng buộc dữ liệu (constraints)** xác định và cưỡng chế một phần những trạng thái được phép lưu.
- **Nhật ký giao dịch (transaction log / write-ahead log)** lưu thông tin cần thiết để khôi phục các thay đổi khi dữ liệu trên đĩa chưa phản ánh đầy đủ transaction.
- **Cơ chế phục hồi (recovery)** dùng thông tin bền vững và trạng thái giao dịch để tái dựng dữ liệu sau lỗi, bảo toàn những gì đã commit và loại bỏ hiệu lực của công việc chưa commit.

ACID là **bộ tính chất cần đạt**; các ràng buộc, khóa, MVCC, nhật ký và thuật toán phục hồi là những **cơ chế giúp đạt được** các tính chất đó. Không nên đồng nhất bất kỳ một cơ chế đơn lẻ nào với toàn bộ ACID.

## 1. Nắm lại ACID dưới góc nhìn triển khai

| Thuộc tính | Cam kết ở mức giao dịch | Cơ chế liên quan trực tiếp | Điều dễ hiểu nhầm |
| --- | --- | --- | --- |
| **Atomicity — Tính nguyên tử** | Một transaction được áp dụng như một đơn vị: toàn bộ thay đổi hợp lệ được commit hoặc không có hiệu lực như một transaction đã hoàn tất. | Quản lý trạng thái transaction, rollback, thông tin undo hoặc cơ chế MVCC kết hợp phục hồi. | Mỗi câu lệnh SQL thành công không có nghĩa toàn bộ quy trình đã commit. |
| **Consistency — Tính nhất quán** | Transaction hợp lệ chuyển database từ trạng thái thỏa những quy tắc được bảo vệ sang trạng thái vẫn thỏa chúng. | `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, logic nghiệp vụ, thiết kế transaction. | Cơ sở dữ liệu không tự biết các quy tắc nghiệp vụ chưa được biểu diễn. |
| **Isolation — Tính cô lập** | Giao dịch đồng thời không được tương tác theo cách vi phạm mức cô lập đã chọn. | Khóa, MVCC, kiểm soát phiên bản, phát hiện xung đột, mức cô lập. | Chỉ viết `BEGIN`/`COMMIT` không ngăn được mọi race condition. |
| **Durability — Tính bền vững** | Khi database đã xác nhận commit theo chính sách độ bền đã cấu hình, kết quả phải sống sót qua các loại sự cố mà chính sách đó bao phủ. | Nhật ký bền vững, cơ chế flush/sync, redo, checkpoint, phục hồi sau crash. | Dữ liệu chưa cần được ghi hết vào các trang bảng vật lý trước khi ứng dụng nhận commit thành công. |

Bốn thuộc tính liên quan nhưng không thay thế nhau. Ví dụ, hai giao dịch cùng cập nhật hai hàng khác nhau theo một quyết định đã đọc từ trước có thể gây **write skew**: cả hai đều được ghi và phục hồi bền vững, nhưng kết quả vi phạm bất biến nghiệp vụ. Đó là vấn đề ở cơ chế cô lập và bảo vệ bất biến; WAL không tự giải quyết được.

### Consistency cần được hiểu cho đúng

Giả sử `I(S)` là mệnh đề “trạng thái `S` thỏa các bất biến bắt buộc”. Ý nghĩa của một giao dịch hợp lệ có thể mô tả bằng:

~~~text
I(S_trước) = true
giao dịch T biến đổi S_trước thành S_sau
I(S_sau_commit) = true
~~~

Điều kiện này chỉ có nghĩa khi đã xác định **những bất biến nào phải đúng** và **cách nào cưỡng chế chúng**. Database có thể đảm bảo khóa ngoại và khóa duy nhất, nhưng sẽ không mặc nhiên biết “mỗi ca trực luôn có ít nhất một bác sĩ” nếu ứng dụng chưa thiết kế cơ chế bảo vệ quy tắc đó.

Tính *Consistency* trong ACID cũng khác với thuật ngữ *replica consistency* trong hệ phân tán. Một primary có thể giữ dữ liệu hợp lệ trong mỗi transaction trong khi một replica bất đồng bộ còn trễ vài giây; hai khái niệm nhất quán đang nói về hai loại cam kết khác nhau.

## 2. Theo dõi một transaction từ SQL tới commit

Với một cơ sở dữ liệu quan hệ dùng write-ahead logging (WAL), luồng xử lý có thể khái quát như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng gửi BEGIN và các câu lệnh SQL"] --> B["DB kiểm tra cú pháp, quyền và ràng buộc liên quan"]
    B --> C["Đọc/ghi dưới cơ chế khóa hoặc MVCC"]
    C --> D["Ghi thông tin thay đổi vào vùng đệm nhật ký"]
    D --> E{"Transaction có thể commit?"}
    E -- "Không" --> R["ROLLBACK / giao dịch không có hiệu lực"]
    E -- "Có" --> F["Ghi trạng thái commit vào nhật ký"]
    F --> G["Đảm bảo nhật ký commit bền vững theo cấu hình"]
    G --> H["Thông báo COMMIT thành công"]
    H --> I["Các trang dữ liệu được ghi xuống lưu trữ theo lịch riêng"]
    I --> K["Checkpoint và cơ chế quản lý nhật ký"]
~~~

Sơ đồ thể hiện **quan hệ chức năng**, không phải thứ tự CPU cố định của mọi hệ quản trị. Database có thể kiểm tra ràng buộc tại từng câu lệnh hoặc khi commit; sinh bản ghi nhật ký trong lúc sửa trang; ghi các trang dữ liệu ra đĩa trước hoặc sau commit nếu giao thức phục hồi cho phép. Thứ tự bắt buộc về mặt an toàn là thông tin nhật ký cần để khôi phục một thay đổi phải được làm bền vững **trước khi trang dữ liệu chứa thay đổi tương ứng được ghi bền vững**. Trong cấu hình WAL an toàn thông thường, record commit cũng phải được làm bền vững trước khi báo commit thành công.

Hãy chú ý hai lớp khác nhau:

1. **Trạng thái logic đã commit:** transaction được công nhận là hoàn tất; các transaction khác sẽ nhìn thấy kết quả theo quy tắc cô lập.
2. **Trạng thái vật lý của trang dữ liệu:** thay đổi có thể còn ở buffer pool và chưa xuất hiện trên file bảng. WAL đã đủ để hệ thống khôi phục lại sau crash.

Vì thế, một transaction không cần chờ mọi trang dữ liệu liên quan được ghi xuống file bảng mới có thể đáp ứng durability. Đây là một lý do WAL giúp database thực hiện nhiều commit hiệu quả.

## 3. Ràng buộc dữ liệu hỗ trợ Consistency như thế nào?

Ràng buộc là những quy tắc được database kiểm tra trên đường ghi. Chúng là tuyến bảo vệ quan trọng vì có hiệu lực cả khi dữ liệu được sửa qua API, batch job, công cụ quản trị hoặc một ứng dụng khác.

| Ràng buộc | Quy tắc điển hình | Phạm vi bảo vệ |
| --- | --- | --- |
| `NOT NULL` | Một thuộc tính bắt buộc phải có giá trị | Một cột trên mỗi hàng |
| `CHECK` | `balance_cents >= 0`, `quantity >= 0` | Biểu thức hợp lệ trên hàng; khả năng cụ thể tùy DBMS |
| `PRIMARY KEY` / `UNIQUE` | Không có hai tài khoản cùng ID; một mã yêu cầu không bị cấp hai lần | Tính duy nhất trên khóa hoặc tổ hợp khóa |
| `FOREIGN KEY` | Đơn hàng phải tham chiếu đến khách hàng tồn tại | Mối quan hệ giữa bảng cha và bảng con |
| Ràng buộc tùy hệ quản trị | Chẳng hạn exclusion constraint hoặc chỉ mục unique một phần của PostgreSQL | Quy tắc nâng cao cần diễn tả bằng cấu trúc tương ứng |

Ví dụ lược đồ PostgreSQL của hệ thống thanh toán nội bộ:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL
        CHECK (balance_cents >= 0)
);

CREATE TABLE transfers (
    request_id UUID PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES accounts(id),
    target_id BIGINT NOT NULL REFERENCES accounts(id),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    CHECK (source_id <> target_id)
);
~~~

Các ràng buộc chặn những tình huống khác nhau:

- Số dư âm bị `CHECK` từ chối khi dữ liệu không thỏa điều kiện.
- Một lệnh chuyển có số tiền bằng 0 hoặc âm không được ghi vào bảng `transfers`.
- Chuyển đến tài khoản không có thật sẽ vi phạm `FOREIGN KEY`.
- Hai lần ghi cùng `request_id` sẽ tranh chấp ràng buộc `PRIMARY KEY`; database không chấp nhận hai hàng đã commit cùng khóa.

Nhưng lược đồ này **chưa tự chứng minh** số tiền trừ ở tài khoản nguồn đúng bằng số tiền cộng ở tài khoản đích. Đó là một bất biến liên quan đến nhiều thay đổi. Phải bảo đảm nó bằng đường ghi trong transaction, thiết kế sổ cái phù hợp hoặc một biện pháp cưỡng chế mạnh hơn nếu có nhiều đường cập nhật.

### Một yêu cầu nghiệp vụ, nhiều lớp bảo vệ

Giả sử khách chuyển 7.000 đơn vị tiền nhỏ nhất từ tài khoản 101 sang 202. Một giao dịch có thể được ứng dụng điều khiển như sau:

~~~sql
BEGIN;

UPDATE accounts
SET balance_cents = balance_cents - 7000
WHERE id = 101
  AND balance_cents >= 7000
RETURNING id;

-- Nếu không trả về đúng một hàng:
-- ROLLBACK; báo không đủ tiền hoặc tài khoản không tồn tại.

UPDATE accounts
SET balance_cents = balance_cents + 7000
WHERE id = 202
RETURNING id;

-- Nếu không trả về đúng một hàng:
-- ROLLBACK; tài khoản đích không tồn tại.

INSERT INTO transfers (
    request_id, source_id, target_id, amount_cents
) VALUES (
    :request_id, 101, 202, 7000
);

COMMIT;
~~~

Đây là **minh họa luồng do ứng dụng điều khiển**, không phải một script chạy liên tục mà bỏ qua các nhánh chú thích. Ứng dụng phải kiểm tra số hàng chịu tác động, kiểm tra lỗi SQL và chỉ phát `COMMIT` khi mọi thao tác cần thiết đều thành công.

Mỗi phần đóng vai trò khác nhau:

- **Atomicity:** nếu bước cộng tiền thất bại, transaction rollback cả bước trừ tiền trước đó; không để lại việc trừ tiền riêng lẻ đã commit.
- **Consistency:** ràng buộc bảo vệ số dư và các trường của bản ghi chuyển. Ứng dụng phải giữ thêm quy tắc số tiền ghi nợ bằng ghi có.
- **Isolation:** hai giao dịch cùng trừ tiền từ tài khoản 101 phải được phối hợp. Câu `UPDATE ... WHERE balance_cents >= 7000` của PostgreSQL lấy khóa hàng và kiểm tra điều kiện trong thao tác ghi; giao dịch cạnh tranh sẽ chờ và kiểm tra lại điều kiện khi cần, thay vì dựa vào một lần `SELECT` cũ.
- **Durability:** sau khi commit được xác nhận bền vững, nhật ký và cơ chế recovery có thể phục hồi các thay đổi ngay cả khi trang bảng chưa kịp được flush.

Trong luồng chuyển tiền hai chiều giữa nhiều tài khoản, các transaction có thể giữ khóa theo thứ tự đối nghịch và gây deadlock. Một giao thức khóa các tài khoản theo cùng thứ tự ID, kết hợp xử lý rollback/retry, giúp giảm rủi ro này. Nên dùng số nguyên theo đơn vị tiền nhỏ nhất hoặc kiểu decimal phù hợp và xử lý giới hạn số học.

`request_id` còn giúp định danh yêu cầu khi client gửi lại do mất phản hồi. Nếu khóa đã tồn tại, hệ thống cần đọc kết quả đã ghi và so sánh nội dung yêu cầu; việc dùng trùng khóa với thông số khác phải được xử lý là xung đột, không được tự diễn giải thành chuyển tiền mới.

### Ràng buộc tức thời và ràng buộc được hoãn

Không phải mọi vi phạm trung gian đều buộc transaction thất bại ngay tại mỗi câu lệnh. Một số DBMS hỗ trợ **ràng buộc có thể trì hoãn** (*deferrable constraints*), cho phép transaction tạo ra trạng thái trung gian chưa hợp lệ nhưng bắt buộc giải quyết trước commit.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE parents (
    id BIGINT PRIMARY KEY
);

CREATE TABLE children (
    id BIGINT PRIMARY KEY,
    parent_id BIGINT REFERENCES parents(id)
        DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

INSERT INTO children (id, parent_id)
VALUES (1, 42);

-- Chưa có parent_id = 42, nhưng FK đang được hoãn đến commit.
INSERT INTO parents (id) VALUES (42);

COMMIT;
~~~

Hai câu lệnh riêng lẻ không tương ứng với một chuỗi luôn hợp lệ nếu kiểm tra FK tức thời, nhưng **trạng thái cuối transaction** thỏa khóa ngoại. Nếu không có hàng cha khi commit, việc kiểm tra FK sẽ làm transaction thất bại.

Cần phân biệt phạm vi hỗ trợ: trong PostgreSQL, `FOREIGN KEY` và một số ràng buộc như `UNIQUE` có thể được khai báo deferrable theo điều kiện hỗ trợ, trong khi `NOT NULL` và `CHECK` không phải là các ràng buộc có thể trì hoãn theo cách này. Hành vi các DBMS khác có thể khác.

## 4. Khi ràng buộc không diễn tả được toàn bộ quy tắc

Xét quy định: **Mỗi ca trực phải có ít nhất một bác sĩ đang trực**. Bảng `shift_doctors(shift_id, doctor_id, on_call)` có hai bác sĩ A và B cùng trực.

~~~text
Trạng thái ban đầu:
Ca 7: A = on_call, B = on_call   => số bác sĩ trực = 2

Transaction T1: thấy COUNT = 2, cho A nghỉ
Transaction T2: thấy COUNT = 2, cho B nghỉ

Cả hai commit:
Ca 7: A = off, B = off          => số bác sĩ trực = 0
~~~

Ở PostgreSQL `REPEATABLE READ` (dựa trên snapshot isolation), T1 và T2 có thể đọc cùng snapshot, sau đó cập nhật hai hàng khác nhau. Không có xung đột ghi trực tiếp trên cùng một hàng, nên kết quả *write skew* có thể xuất hiện. Mỗi hàng vẫn thỏa kiểu dữ liệu và các `CHECK` cục bộ, nhưng bất biến tổng hợp bị phá vỡ.

Giải pháp không nằm ở việc bật WAL mạnh hơn. Cần bảo vệ phép ra quyết định giữa các giao dịch:

- **Khóa chung theo ca trực:** mọi đường ghi thay đổi lịch phải lấy khóa trên một hàng `shifts(id)` tồn tại trước khi đếm và sửa. Với cách dùng phù hợp ở `READ COMMITTED`, giao dịch sau chờ giao dịch trước và đọc lại số bác sĩ.
- **`SERIALIZABLE`:** cơ chế quản lý xung đột của DBMS phát hiện những lịch thực thi không phù hợp và có thể hủy một transaction. Ứng dụng phải retry **toàn bộ** transaction theo chính sách giới hạn.
- **Thay đổi mô hình dữ liệu:** đưa thông tin quyết định vào một hàng có thể cập nhật có điều kiện hoặc một cấu trúc mà database cưỡng chế được.

Điểm cốt lõi: **Consistency của ACID phụ thuộc đồng thời vào bất biến được diễn tả và mức Isolation đủ mạnh để giữ bất biến khi có cạnh tranh**. Việc database kiểm tra ràng buộc trước commit không có nghĩa nó biết mọi quy tắc nghiệp vụ đa hàng.

## 5. Nhật ký giao dịch thực sự lưu gì?

Nhật ký trong ngữ cảnh ACID thường là **nhật ký phục hồi** của DBMS, không đơn thuần là dòng thông báo ứng dụng như “người dùng đã chuyển tiền”. Cách biểu diễn khác nhau giữa các hệ quản trị, nhưng những nhóm thông tin thường cần thiết gồm:

- **Danh tính/vị trí thay đổi:** transaction ID, vị trí log (chẳng hạn LSN), thông tin trang hoặc đối tượng liên quan.
- **Thông tin phục hồi:** mô tả thay đổi vật lý, bản ghi đủ để tái áp dụng, hoặc thông tin phục vụ hoàn tác, tùy kiến trúc.
- **Trạng thái transaction:** dấu mốc commit/abort và thông tin cho phép khôi phục trạng thái nhất quán.
- **Thông tin checkpoint:** xác định vị trí và trạng thái hữu ích để rút ngắn quá trình khởi động lại.

Một mô hình khái niệm đơn giản:

~~~text
LSN 100: T42 bắt đầu
LSN 110: T42 thay đổi tài khoản 101
LSN 120: T42 thay đổi tài khoản 202
LSN 130: T42 thêm bản ghi chuyển tiền
LSN 140: T42 commit
        (nhật ký tương ứng đã bền vững)
...
Các trang dữ liệu liên quan được ghi xuống file bảng sau đó.
~~~

Danh sách này **không phải định dạng WAL chuẩn** của PostgreSQL, MySQL hay SQL Server; nó chỉ cho thấy những sự kiện mà cơ chế phục hồi cần phân biệt. WAL thực tế có thể ghi ở mức trang, cấu trúc dữ liệu, hoặc chuỗi thay đổi nội bộ.

### Nguyên tắc write-ahead

Giả sử buffer pool chứa một trang dữ liệu đã sửa, còn file bảng trên đĩa vẫn cũ. Nếu database muốn flush trang đã sửa, nó phải bảo đảm thông tin nhật ký cần để khôi phục thay đổi đó đã bền vững trước. Đây là nguyên tắc **write-ahead**: **log đi trước trang dữ liệu**.

Trong cách triển khai WAL có commit bền vững thông thường:

1. Transaction tạo những thay đổi trong bộ nhớ và các record nhật ký tương ứng.
2. Khi commit, hệ thống đánh dấu transaction hoàn tất theo giao thức của nó và bảo đảm phần nhật ký cần thiết, gồm thông tin commit, đã được ghi bền vững.
3. Database có thể xác nhận commit mà chưa flush hết các trang bảng.
4. Khi tiến trình hoặc máy chủ khởi động lại sau crash, recovery đọc nhật ký để xử lý những trang còn thiếu cập nhật.

Việc ghi nhật ký một lần theo kiểu tuần tự thường hiệu quả hơn yêu cầu ghi đồng bộ nhiều trang nằm rải rác trong file dữ liệu. Một hệ quản trị còn có thể **group commit**: gom việc đồng bộ nhật ký của nhiều giao dịch để giảm chi phí I/O, trong khi vẫn giữ cam kết độ bền của từng lần commit được xác nhận.

### WAL không phải audit log, cũng không đồng nghĩa replication log

| Loại nhật ký | Mục tiêu chính | Điều cần chú ý |
| --- | --- | --- |
| Recovery/WAL/redo log | Phục hồi trạng thái database sau sự cố; phục vụ độ bền và cơ chế nội bộ | Định dạng và vòng đời do DBMS quản lý; không phải tài liệu nghiệp vụ dễ đọc. |
| Undo log / thông tin undo | Hoàn tác hoặc cung cấp phiên bản cũ theo kiến trúc DBMS | Không phải DBMS nào cũng có file undo tách biệt hoặc dùng cùng cơ chế. |
| Audit log | Ghi ai đã thực hiện thao tác nào, khi nào, phục vụ kiểm toán | Cần thiết kế chính sách, quyền truy cập, lưu giữ và độ tin cậy riêng. |
| Application log | Chẩn đoán luồng ứng dụng, lỗi, thời gian xử lý | Một dòng “đã thành công” không chứng minh dữ liệu đã commit bền vững. |
| Change stream / CDC | Cung cấp thay đổi đã ghi cho hệ thống khác | Có thể sử dụng thông tin từ log nội bộ nhưng có contract và cơ chế tiêu thụ riêng. |
| Replication log / luồng sao chép | Truyền hoặc tái thực thi thay đổi tới bản sao | Quan hệ với WAL tùy DBMS; chế độ đồng bộ/bất đồng bộ quyết định điểm bảo đảm. |

Không nên xóa, sửa hoặc đọc trực tiếp các file recovery log như một dữ liệu ứng dụng thông thường. Giữ log quá ít có thể làm hỏng quy trình recovery/PITR; giữ vô hạn lại tạo rủi ro đầy đĩa. Việc quản lý log là trách nhiệm vận hành có cấu hình và công cụ riêng.

## 6. Recovery làm gì sau một sự cố?

Một database có thể tắt do mất điện, crash process, máy chủ bị khởi động lại hoặc lỗi thiết bị. Khi khởi động lại, DBMS phải trả lời hai câu hỏi: **giao dịch nào đã được commit hợp lệ** và **trạng thái vật lý nào cần hoàn tất hoặc loại bỏ để dữ liệu khớp với kết quả đó**?

Ở mức khái niệm có hai loại công việc:

- **Redo:** áp dụng lại các thay đổi mà trạng thái bền vững cho thấy cần có, nhưng trang dữ liệu hiện lưu trữ chưa phản ánh đầy đủ.
- **Undo / loại bỏ hiệu lực chưa commit:** ngăn các thay đổi của transaction chưa hoàn tất trở thành trạng thái đã commit; có thể bằng ghi undo, phục hồi trang, đánh dấu transaction không hợp lệ hoặc quy tắc nhìn thấy phiên bản.

Nhiều tài liệu về thuật toán phục hồi họ ARIES mô tả các pha **analysis → redo → undo**. Đây là mô hình quan trọng để hiểu phục hồi kiểu WAL/undo-redo, **không phải** mô tả chính xác thuật toán của mọi hệ quản trị.

Ví dụ về khác biệt cơ chế:

- **InnoDB của MySQL** dùng redo log và undo log; undo còn có vai trò hỗ trợ các phiên bản đọc nhất quán của MVCC.
- **PostgreSQL** dùng WAL và trạng thái transaction cùng cơ chế MVCC; dữ liệu của transaction chưa commit không trở thành phiên bản hợp lệ để giao dịch khác nhìn thấy. PostgreSQL không triển khai một undo log truyền thống giống InnoDB cho mọi cập nhật hàng. Recovery dùng WAL để khôi phục các trang/trạng thái cần thiết và trạng thái commit để xác định khả năng nhìn thấy.

Điều ứng dụng quan sát được là hợp đồng ACID, còn cách lưu phiên bản cũ, cách phục hồi trang và cách đánh dấu commit là chi tiết đặc thù của engine.

### Checkpoint giúp gì, và không giúp gì?

Một **checkpoint** là điểm mốc mà hệ quản trị đã đồng bộ đủ trạng thái liên quan để biết từ đâu cần bắt đầu hoặc giới hạn công việc phục hồi. Checkpoint giúp giảm lượng nhật ký phải quét hoặc redo khi khởi động lại, đồng thời phối hợp việc flush trang và tái sử dụng/loại bỏ log theo chính sách lưu giữ.

Checkpoint **không phải** là lệnh `COMMIT` của mọi transaction và không có nghĩa chỉ transaction trước checkpoint mới bền vững. Một transaction commit sau checkpoint vẫn được phục hồi nhờ nhật ký đã được đồng bộ đúng giao thức.

### Bốn thời điểm xảy ra sự cố

| Thời điểm crash | Điều đã chắc chắn xảy ra | Kết quả cần hiểu |
| --- | --- | --- |
| Trước khi giao dịch được commit | Transaction còn dang dở hoặc đã rollback | Các thay đổi chưa commit không được công nhận là kết quả hoàn tất; recovery loại bỏ hiệu lực của chúng. |
| Đã có commit bền vững nhưng client chưa nhận được phản hồi | Database đã đạt điểm cam kết; gói phản hồi có thể mất | Transaction có thể đã commit; client phải truy vấn lại bằng khóa idempotency thay vì mặc định thử lại là một giao dịch mới. |
| Client đã nhận “commit thành công”, nhưng một số trang bảng còn trong buffer | Nhật ký chứa đủ thông tin cần phục hồi theo chính sách bền vững đã bật | Sau crash, recovery đưa các trang/trạng thái về kết quả đã commit. |
| Dữ liệu đã được checkpoint/flush đầy đủ | Các trang đã phản ánh trạng thái tại mốc liên quan | Recovery có thể cần ít công việc hơn, nhưng vẫn phải xử lý thay đổi sau mốc đó. |

Bảng giả định storage và cấu hình database tuân thủ cam kết durability. Nếu cố ý tắt cơ chế đồng bộ bền vững hoặc phần cứng báo sai về việc ghi dữ liệu, hệ thống có thể không bảo đảm kết quả như trên.

## 7. Ràng buộc, WAL và recovery phối hợp khi lỗi xảy ra

Lấy lại giao dịch chuyển 7.000 đơn vị giữa hai tài khoản. Giả sử sau câu `UPDATE` thứ nhất, trước khi ghi có cho tài khoản đích, database process đột ngột dừng.

Về mặt **Atomicity**, transaction chưa commit nên lần chạy ứng dụng sau không được thấy một kết quả chuyển tiền đã hoàn tất chỉ gồm việc trừ tiền. Hệ thống phục hồi hoặc loại bỏ hiệu lực của thay đổi chưa commit, tùy cơ chế engine.

Về mặt **Consistency**, khi transaction chỉ được phép commit sau khi cả hai cập nhật thành công, dữ liệu cuối cùng không rơi vào trạng thái chỉ trừ một phía. Ràng buộc `CHECK (balance_cents >= 0)` còn bảo vệ riêng việc số dư âm. Tuy nhiên, nếu ứng dụng **cố ý commit sau khi chỉ trừ tiền**, recovery sẽ phục hồi chính transaction sai đó; nó không thể tự suy ra nghiệp vụ còn thiếu lệnh cộng tiền.

Về mặt **Isolation**, trong khi giao dịch chuyển còn đang xử lý, cơ chế khóa/MVCC giữ cho các transaction khác không xử lý sai kết quả trung gian theo mức cô lập và đường ghi đã thiết kế. Một công việc khác trừ tiền cùng tài khoản phải giải quyết tranh chấp theo cơ chế DB.

Về mặt **Durability**, nếu cả hai cập nhật, bản ghi chuyển tiền và commit đều đã được hệ quản trị xác nhận bền vững rồi mới crash, recovery có đủ thông tin để giữ kết quả đã commit. Việc một số trang bảng chưa flush không làm mất giao dịch hợp lệ đó.

Có thể tóm tắt sự phối hợp như sau:

~~~text
                      BẤT BIẾN NGHIỆP VỤ
                              |
                 Ràng buộc DB + logic giao dịch
                              |
                  Isolation bảo vệ cạnh tranh
                              |
           Atomicity quyết định commit/rollback cùng nhau
                              |
             WAL ghi nhận thông tin phục hồi bền vững
                              |
             Recovery duy trì hiệu lực của commit
                              |
             Durability trước sự cố thuộc phạm vi cam kết
~~~

Cơ chế phục hồi **bảo toàn quyết định giao dịch** của hệ thống. Nó không phải trình kiểm định nghiệp vụ thay cho ràng buộc, giao thức đồng thời hay logic ứng dụng.

## 8. Transaction commit có cần mọi thứ nằm trên đĩa?

Không. Database thường dùng **buffer pool/page cache** để tránh ghi đĩa đồng bộ ở từng bước sửa hàng. Có thể phân biệt các mốc:

1. **Câu lệnh đã chạy:** thay đổi đã được áp dụng trong trạng thái transaction và những cấu trúc bộ nhớ liên quan.
2. **Transaction đã commit về logic:** engine đã chấp nhận các điều kiện hoàn tất và ghi nhận trạng thái commit.
3. **Nhật ký commit đã bền vững:** đủ bằng chứng để phục hồi kết quả đã commit; đây là mốc then chốt của durability trong cấu hình WAL thông thường.
4. **Trang dữ liệu đã được flush:** file bảng chính đã phản ánh thay đổi tương ứng. Bước này có thể đến muộn hơn.

Khi cấu hình cho phép **asynchronous commit**, lời xác nhận có thể đến trước khi record commit được đồng bộ bền vững. Chẳng hạn PostgreSQL có tùy chọn `synchronous_commit = off`: transaction vẫn được quản lý nhất quán khi database đang chạy, nhưng một crash gần thời điểm commit có thể làm mất các transaction vừa được báo thành công. Vì thế, không nên mô tả durability của mọi cấu hình bằng cùng một cam kết tuyệt đối.

Một cách phân biệt hữu ích:

- **Commit latency**: ứng dụng mất bao lâu để nhận kết quả commit.
- **Data-page flush latency**: khi nào trang dữ liệu cụ thể xuống file bảng.
- **Recovery time**: khi crash xảy ra, database mất bao lâu để dùng checkpoint/log đưa hệ thống về trạng thái phục vụ được.

Ba giá trị liên quan đến hoạt động I/O, nhưng không phải cùng một phép đo.

## 9. Isolation và logging giải quyết hai bài toán khác nhau

Một sai lầm phổ biến là cho rằng **cứ có WAL thì mọi giao dịch đồng thời sẽ an toàn**. WAL chủ yếu hỗ trợ trạng thái bền vững và phục hồi. Nó không tự chọn thứ tự hợp lệ cho các quyết định nghiệp vụ.

Xét bảng `inventory(sku, stock)` với tồn kho 5 đơn vị. Hai đơn hàng đều muốn mua 4 đơn vị:

~~~sql
-- Cách cập nhật có điều kiện ở PostgreSQL:
BEGIN;

UPDATE inventory
SET stock = stock - 4
WHERE sku = 'SKU-1'
  AND stock >= 4
RETURNING stock;

-- Chỉ tạo đơn hàng và COMMIT nếu UPDATE trả về một hàng.
-- Nếu không có hàng nào, ROLLBACK hoặc kết thúc không tạo đơn.

COMMIT;
~~~

Câu `UPDATE` có điều kiện giải quyết **tranh chấp trên cùng một hàng**. Ràng buộc `CHECK (stock >= 0)` có thể bổ sung tuyến phòng vệ. Còn WAL giúp database khôi phục một lần trừ kho đã commit ngay cả khi crash trước khi flush hết trang dữ liệu.

Nếu đơn hàng giữ nhiều SKU trong một transaction, phải cùng lúc giải quyết tính nguyên tử của các cập nhật và cơ chế khóa phù hợp. Nếu quy tắc liên quan tới nhiều hàng như “tổng giới hạn tín dụng của một nhóm khách hàng”, cần thêm chiến lược xử lý bất biến tổng hợp, chẳng hạn điểm khóa chung hoặc serializable.

| Câu hỏi | Cơ chế thường trả lời |
| --- | --- |
| Có cho phép số lượng tồn âm không? | `CHECK` hoặc quy tắc schema và cập nhật có điều kiện |
| Hai người cùng mua có vượt số hàng trong kho không? | Khóa hàng, cập nhật có điều kiện, OCC hoặc mức cô lập phù hợp |
| Có được giữ kho mà chưa tạo đơn thành công không? | Atomicity trong cùng transaction |
| Nếu máy chủ crash sau khi commit, đơn và tồn kho có còn không? | Durability qua log bền vững và recovery |
| Nếu gửi sự kiện ra broker bị lỗi thì sao? | Outbox, retry và xử lý trùng lặp; transaction DB cục bộ không bao trùm broker |

## 10. Những giới hạn của recovery cần biết khi vận hành

### Durability không đồng nghĩa với mọi dạng an toàn dữ liệu

Durability sau **crash process hoặc khởi động lại** khác với việc bảo vệ dữ liệu trước hỏng đĩa vật lý, lỗi firmware, thao tác xóa nhầm, mã độc, ứng dụng commit sai hoặc mất cả cụm máy. Cần tách các biện pháp:

- **WAL/redo:** giúp phục hồi sau crash và tái dựng những thay đổi đã commit trong phạm vi lưu trữ được bảo toàn.
- **Backup và kiểm thử restore:** bảo vệ trước mất mát, xóa nhầm, hỏng hóc lớn hoặc cần trở lại mốc trước đó.
- **Point-in-time recovery (PITR):** kết hợp bản sao lưu nền và chuỗi WAL/archive phù hợp để khôi phục tại một mốc thời gian trong phạm vi dữ liệu còn đủ.
- **Replication:** tăng khả năng phục vụ và thay thế nút; cam kết sau failover tùy chế độ đồng bộ, độ trễ và quy trình chuyển vai trò.

Với **replication bất đồng bộ**, một primary có thể báo commit thành công trước khi replica nhận được thay đổi. Nếu primary mất vĩnh viễn và failover lên replica còn trễ, một số commit gần cuối có thể không tồn tại trên replica mới. Điều này không phủ nhận quy tắc ACID cục bộ của primary; nó chỉ ra rằng cam kết độ bền **trên toàn hệ thống failover** cần thêm cơ chế và cấu hình riêng.

### Nhật ký có vòng đời và chi phí

WAL phải được tạo, flush, lưu giữ, archive hoặc giải phóng theo chính sách. Nếu disk log đầy, replication slot giữ WAL quá lâu hoặc checkpoint bị chậm, database có thể giảm hiệu năng, từ chối ghi hoặc ngừng phục vụ. Nếu archive log bị mất, kế hoạch PITR có thể không đạt điểm phục hồi mong muốn.

Các chỉ số vận hành hữu ích gồm độ trễ commit, thời gian đồng bộ WAL, số lần checkpoint, dung lượng WAL, replication lag, thời gian recovery, tỷ lệ transaction bị abort/retry và số lần deadlock. Chỉ số cụ thể và tên metric phải tra theo DBMS đang sử dụng.

### Ứng dụng phải sẵn sàng trước lỗi “không biết đã commit chưa”

Một kết nối mạng có thể bị ngắt đúng lúc database vừa commit. Client nhận lỗi timeout, nhưng **không thể suy ra** transaction đã rollback. Với các nghiệp vụ như chuyển tiền, tạo đơn, trừ tồn hoặc cấp tài nguyên, cần:

1. Gán khóa yêu cầu/idempotency ổn định trước khi thực hiện.
2. Lưu kết quả hoặc dấu vết xử lý với khóa đó trong phạm vi transaction thích hợp.
3. Khi retry, tra cứu khóa để xác định yêu cầu trước đã được áp dụng hay chưa.
4. Chỉ thực hiện lại khi giao thức xác nhận an toàn; mọi nhánh chạy lại phải giữ được bất biến.

Đây là nơi durability và thiết kế API gặp nhau: DB có thể đã commit đúng, nhưng ứng dụng vẫn cần cách biết kết quả khi phản hồi bị mất.

## 11. Khi giao dịch liên quan tới message broker hoặc dịch vụ khác

Ví dụ transaction tạo đơn hàng trong database, rồi ứng dụng phát sự kiện `OrderCreated` sang broker. Có hai lịch lỗi kinh điển:

- **Commit trước, gửi sau:** database đã có đơn, nhưng tiến trình crash trước khi gửi sự kiện.
- **Gửi trước, commit sau:** broker đã nhận sự kiện về đơn, nhưng database transaction rollback.

Một database transaction cục bộ không tự làm cho việc ghi database và gửi thông điệp thành một thao tác ACID chung. Giải pháp phổ biến là **transactional outbox**:

~~~sql
BEGIN;

INSERT INTO orders (id, status)
VALUES (:order_id, 'CREATED');

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload
) VALUES (
    :event_id, :order_id, 'OrderCreated', :payload
);

COMMIT;
~~~

Vì bản ghi đơn hàng và bản ghi outbox nằm trong cùng transaction database, ACID bảo vệ quan hệ **“đơn hàng được commit thì ý định phát sự kiện cũng được commit”**. Một publisher độc lập lấy bản ghi outbox và thử gửi tới broker, có thể gửi lại sau lỗi. Consumer phải có cách chống xử lý trùng, thường dựa trên `event_id` và một bảng ghi nhận đã xử lý.

Bằng cách này, WAL/recovery tiếp tục làm nhiệm vụ giữ bản ghi đơn và outbox sau crash. Việc phân phối thông điệp, retry và xử lý trùng là **giao thức ở tầng ứng dụng/hệ phân tán**, không phải thuộc tính tự sinh từ WAL.

Một số kiến trúc dùng distributed transaction hoặc two-phase commit, nhưng điều đó cần hỗ trợ từ các thành phần tham gia, có chi phí phối hợp và cơ chế xử lý lỗi riêng. Không nên giả định một annotation `@Transactional` của framework tự mở rộng giao dịch ACID sang tất cả API, broker và hệ thống thanh toán bên ngoài.

## 12. Đối chiếu lỗi với thuộc tính cần bảo vệ

| Tình huống | Rủi ro trực tiếp | Lớp cần xử lý |
| --- | --- | --- |
| Câu cập nhật tài khoản nguồn thành công, cập nhật tài khoản đích lỗi | Chuyển tiền một phía | Atomicity: rollback cả transaction |
| Hai request cùng dùng một mã đặt chỗ | Bản ghi trùng | Consistency: `UNIQUE` hoặc khóa nghiệp vụ |
| Hai giao dịch đồng thời cùng đọc còn hàng trước khi đặt | Bán quá tồn kho | Isolation và cập nhật có điều kiện/ràng buộc phù hợp |
| Hai bác sĩ ở hai hàng cùng xin nghỉ | *Write skew* và vi phạm bất biến tổng hợp | Isolation đủ mạnh và chiến lược bảo vệ quy tắc đa hàng |
| Process crash sau commit, trang bảng còn trong bộ nhớ | Nguy cơ mất thay đổi nếu không có log bền vững | WAL và recovery cho Durability |
| Database commit nhưng HTTP response bị mất | Client không biết kết quả | Idempotency và truy vấn lại trạng thái |
| Primary chết trước khi replica bất đồng bộ nhận WAL | Mất commit mới nhất khi failover | Chính sách replication và mục tiêu RPO/RTO |
| Một người dùng xóa nhầm dữ liệu rồi commit | Thay đổi sai nhưng hợp lệ về transaction | Phân quyền, backup/PITR, audit, quy trình phục hồi nghiệp vụ |

Trong các trường hợp này, **phục hồi sau crash không tự sửa được một transaction nghiệp vụ đã commit sai**. Nếu ứng dụng hợp lệ hóa một chuyển tiền sai, WAL sẽ trung thành lưu và phục hồi chính kết quả sai ấy. Muốn tránh lỗi cần thiết kế ràng buộc, điều kiện cập nhật, quyền, transaction boundary và isolation từ đầu.

## 13. Cách áp dụng khi thiết kế một nghiệp vụ mới

Có thể đi từ cam kết nghiệp vụ đến cơ chế database theo trình tự sau.

**Bước 1 — Diễn đạt bất biến.** Chẳng hạn “số dư không âm”, “một ghế chỉ có một chủ đang giữ”, hoặc “tổng các bút toán của một lệnh chuyển cân bằng”. Phân biệt quy tắc bắt buộc đúng tại commit với trạng thái tạm thời được nghiệp vụ cho phép.

**Bước 2 — Tìm điểm cưỡng chế gần dữ liệu nhất.** Dùng `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` khi diễn đạt được. Nếu quy tắc trải nhiều hàng, xác định dữ liệu đại diện, hàng khóa chung, trình tự cập nhật hoặc mức cô lập phù hợp.

**Bước 3 — Đặt transaction bao trùm quyết định và các thay đổi phải đồng thành công.** Ví dụ vừa giảm tồn kho vừa tạo đơn. Kiểm tra số hàng trả về; không commit một phần khi một bước bắt buộc thất bại.

**Bước 4 — Xác định cách ứng xử khi hai transaction cạnh tranh.** Tranh chấp khóa đơn, số dư, ghế, lịch trực hoặc quota có thể cần cập nhật có điều kiện, locking, optimistic concurrency control hoặc serializable với retry. WAL không thay thế bước này.

**Bước 5 — Xác nhận chính sách durability thực tế.** Hiểu cơ chế flush log, tùy chọn asynchronous commit, replication, backup và mức mất dữ liệu có thể chấp nhận. Thiết kế phục hồi theo cả crash lẫn mất nút lưu trữ.

**Bước 6 — Thiết kế retry và việc ngoài database.** Dùng khóa idempotency khi kết quả commit có thể không rõ, dùng outbox khi cần phát sự kiện và chuẩn bị các bước đối soát cho quy trình nhiều hệ thống.

Trong thiết kế thực tế, hãy luôn hỏi hai câu: **“Điều gì ngăn một transaction commit trạng thái sai?”** và **“Nếu hệ thống dừng ngay sau khi báo commit thành công, bằng cách nào dữ liệu được phục hồi?”**. Câu đầu dẫn tới ràng buộc, isolation và transaction boundary; câu sau dẫn tới WAL, durability và recovery.

## Kết luận

Mối liên hệ giữa ACID và các cơ chế bên dưới là một chuỗi bảo đảm có trách nhiệm rõ ràng: **ràng buộc cùng logic nghiệp vụ xác định trạng thái hợp lệ; isolation bảo vệ quyết định dưới đồng thời; atomicity kết hợp các thay đổi thành một kết quả commit hoặc rollback; nhật ký bền vững và recovery bảo tồn kết quả commit qua sự cố**. Một hệ thống chỉ thực sự đáng tin khi những lớp này khớp với cùng một bất biến nghiệp vụ, với cấu hình độ bền và phạm vi lỗi được hiểu chính xác.
