# Giao dịch chỉ đọc và giới hạn của cam kết không thay đổi dữ liệu

Trong một ứng dụng giao dịch, có những thao tác cần **đọc một tập dữ liệu có quan hệ với nhau** nhưng không có ý định cập nhật trạng thái nghiệp vụ: xem số dư tài khoản, tổng hợp doanh thu, dựng báo cáo tồn kho, kiểm tra tiến độ đơn hàng hoặc xuất dữ liệu phục vụ đối soát. Những thao tác này thường được tổ chức dưới dạng **giao dịch chỉ đọc** (*read-only transaction*).

Tên gọi “chỉ đọc” dễ tạo ra một kỳ vọng quá rộng: giao dịch sẽ không sửa dữ liệu, kết quả luôn mới nhất, nhiều câu truy vấn luôn thấy cùng một thời điểm và việc đọc hoàn toàn không gây ảnh hưởng cho các giao dịch khác. Trên thực tế, **cam kết không thay đổi dữ liệu có một phạm vi cụ thể**. Nó không tự quyết định mức cô lập, không làm dữ liệu đứng yên, không bảo đảm kết quả mới nhất, cũng không làm mất đi chi phí hoặc tác động vận hành của một truy vấn.

Bài học này đặt giao dịch chỉ đọc trong **vòng đời giao dịch**, từ lúc bắt đầu, thiết lập chính sách đọc, thực thi các câu truy vấn, đến khi `COMMIT` hoặc `ROLLBACK`. Các ví dụ SQL chính sử dụng PostgreSQL để cho thấy rõ hành vi; khi làm việc với DBMS khác cần áp dụng cú pháp và cơ chế tương ứng.

## 1. Giao dịch chỉ đọc là gì?

Một transaction thông thường chứa các lệnh truy vấn, kiểm tra dữ liệu hoặc thay đổi dữ liệu. Giao dịch chỉ đọc xác định rằng **transaction được dùng để đọc, không được phép thực hiện những thay đổi thuộc phạm vi mà hệ quản trị định nghĩa là thao tác ghi bị cấm**.

Chẳng hạn:

~~~sql
-- PostgreSQL
BEGIN READ ONLY;

SELECT id, balance_cents
FROM accounts
WHERE id = 101;

COMMIT;
~~~

Lệnh `BEGIN READ ONLY` khai báo chế độ giao dịch, `SELECT` thực hiện truy vấn, còn `COMMIT` kết thúc transaction. Dù không có hàng nào được cập nhật, transaction vẫn cần được kết thúc để giải phóng tài nguyên và trạng thái giao dịch.

Có thể phân biệt ba câu phát biểu thường bị dùng thay thế cho nhau:

| Phát biểu | Ý nghĩa thực tế |
| --- | --- |
| “Đoạn mã này chỉ gọi các phương thức đọc.” | **Ý định của ứng dụng**: lập trình viên không chủ đích ghi, nhưng không phải một rào chắn dữ liệu độc lập. |
| “Transaction được gắn `readOnly = true` trong framework.” | **Cấu hình/hint cho tầng transaction và persistence**: có thể tối ưu flush, truyền cờ đọc cho connection hoặc phối hợp cơ chế khác; mức thực thi phụ thuộc stack. |
| “DBMS xác nhận transaction là `READ ONLY`.” | **Chế độ do database thực thi**: các thao tác ghi bị cấm theo quy tắc của engine có thể bị từ chối; phạm vi cấm vẫn tùy DBMS và loại đối tượng. |

Vì thế, khi cần một bảo đảm nghiêm ngặt, phải biết **ai thực thi cam kết**, **những kiểu thay đổi nào bị cấm**, **trạng thái nào còn có thể thay đổi**, và **trường hợp lỗi sẽ được xử lý ra sao**.

### Giao dịch chỉ đọc vẫn là một transaction

Nó vẫn có vòng đời: bắt đầu, xác lập mức cô lập, lấy snapshot hoặc các khóa cần thiết, chạy một hay nhiều câu truy vấn, xử lý lỗi, rồi kết thúc. Những khái niệm như timeout, hủy yêu cầu, rollback, snapshot lifetime và quản lý connection vẫn áp dụng.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đọc"] --> B["Bắt đầu transaction"]
    B --> C["Thiết lập READ ONLY và isolation"]
    C --> D["Đọc dữ liệu dưới cơ chế snapshot/lock"]
    D --> E{"Thành công?"}
    E -- "Có" --> F["COMMIT hoặc kết thúc transaction"]
    E -- "Lỗi / hủy / timeout" --> G["ROLLBACK"]
    F --> H["Giải phóng snapshot, khóa và connection"]
    G --> H
~~~

Nói “không có thay đổi để commit” **không có nghĩa** có thể để transaction mở vô hạn. `COMMIT` trong một giao dịch chỉ đọc chủ yếu xác nhận kết thúc phạm vi giao dịch và giải phóng những tài nguyên gắn với nó. `ROLLBACK` cũng có thể kết thúc một transaction đọc khi cần hủy hoặc xử lý lỗi.

## 2. Phân biệt đọc một câu lệnh và đọc trong một giao dịch

Ở nhiều ứng dụng, mỗi `SELECT` được thực thi trong chế độ *autocommit* (hoặc được database bao bọc bởi một transaction ngầm cho câu lệnh đó). Với một câu truy vấn duy nhất, cách này thường đủ cho nhu cầu đọc thông thường.

Ví dụ:

~~~sql
SELECT status
FROM orders
WHERE id = 5001;
~~~

Một `SELECT` đơn lẻ thường quan sát một view hợp lệ theo mức cô lập của câu lệnh. Nhưng nhu cầu đọc phức tạp có thể gồm nhiều bước:

1. Đọc thông tin đơn hàng.
2. Đọc các dòng sản phẩm của đơn hàng.
3. Đọc số tiền đã thanh toán.
4. Tính số tiền còn phải thu.
5. Tạo nội dung trả về cho người dùng.

Nếu các câu truy vấn không dùng cùng một trạng thái quan sát, báo cáo có thể ghép **những phiên bản dữ liệu không tương ứng với nhau**. Chuyển nhiều câu `SELECT` vào một transaction là một bước cần cân nhắc, nhưng kết quả còn phụ thuộc **mức cô lập**.

### Khi nào một giao dịch chỉ đọc thực sự có ích?

- **Báo cáo nhiều truy vấn:** cần thống nhất thông tin header/detail, bảng tổng hợp và bảng chi tiết.
- **Đối soát:** nhiều phép đọc phải dựa trên cùng một thời điểm quan sát được.
- **Phân trang/duyệt dữ liệu theo lô trong một lần xử lý:** muốn tránh các thay đổi giữa các trang, nếu chi phí giữ snapshot là chấp nhận được.
- **Truy vấn nghiệp vụ có nhiều bước phụ thuộc:** đọc dữ liệu đầu vào rồi tính một kết quả, nhưng không tạo thay đổi trong transaction đó.
- **Tối ưu tầng persistence:** framework/DBMS có thể bỏ qua hoặc giảm một số công việc thường phục vụ ghi, tùy cấu hình.

Không phải thao tác đọc nào cũng cần transaction kéo dài qua nhiều lệnh. Giữ một transaction mở để hiển thị danh sách cho người dùng trong vài phút thường làm hệ thống chịu chi phí không cần thiết.

## 3. Cam kết “không ghi” không đồng nghĩa “đọc cùng một snapshot”

Đây là giới hạn quan trọng nhất trong môi trường có nhiều transaction đồng thời.

Giả sử hệ thống có hai tài khoản:

| Tài khoản | Số dư lúc đầu |
| --- | ---: |
| A | 100 |
| B | 100 |
| **Tổng** | **200** |

Một giao dịch khác chuyển 30 đơn vị từ A sang B, nên sau khi nó commit: A = 70, B = 130, tổng vẫn là 200.

Một giao dịch báo cáo chỉ đọc thực hiện hai câu `SELECT` ở mức `READ COMMITTED`:

~~~text
Thời điểm     Transaction báo cáo (READ ONLY)     Transaction chuyển tiền
--------------------------------------------------------------------------------
T1            SELECT balance(A) -> 100
T2                                                 BEGIN
T3                                                 A = A - 30
T4                                                 B = B + 30
T5                                                 COMMIT
T6            SELECT balance(B) -> 130
T7            Tổng trong báo cáo = 230
T8            COMMIT
~~~

Không có transaction nào ghi “một nửa giao dịch chuyển tiền” thành công: việc chuyển tiền vẫn nguyên tử. Nhưng ở PostgreSQL `READ COMMITTED`, **mỗi câu lệnh được phép có một snapshot mới**. Báo cáo có thể đọc A từ trước khi chuyển, B từ sau khi chuyển; tổng 230 không phải tổng ở bất kỳ trạng thái đã commit nào trong ví dụ.

Đây là dạng **read skew** hay *inconsistent analysis* do phối hợp các lần đọc ở các thời điểm khác nhau. Chế độ `READ ONLY` không ngăn hiện tượng này.

### Ví dụ PostgreSQL: READ COMMITTED + READ ONLY

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SET TRANSACTION READ ONLY;

SELECT balance_cents FROM accounts WHERE id = 101;
-- Một giao dịch khác có thể commit ở đây.
SELECT balance_cents FROM accounts WHERE id = 202;

COMMIT;
~~~

Hai câu `SELECT` có thể thấy hai snapshot khác nhau. Dù DBMS từ chối các thao tác ghi bị cấm của transaction, **dữ liệu vẫn thay đổi bởi những transaction khác**.

### Ví dụ PostgreSQL: REPEATABLE READ + READ ONLY

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT balance_cents FROM accounts WHERE id = 101;
SELECT balance_cents FROM accounts WHERE id = 202;

COMMIT;
~~~

Với `REPEATABLE READ` của PostgreSQL, các truy vấn thông thường trong cùng transaction dùng cùng một snapshot được xác lập khi transaction lần đầu cần snapshot. Các giá trị A và B ở ví dụ sẽ tương ứng với một trạng thái quan sát thống nhất: hoặc 100 + 100, hoặc 70 + 130, tùy thời điểm snapshot được lấy.

Điều này cho thấy **chế độ đọc/ghi và mức cô lập là hai lựa chọn khác nhau**:

- `READ ONLY` xác định phạm vi những thay đổi mà transaction được phép thực hiện.
- `READ COMMITTED`, `REPEATABLE READ` hoặc `SERIALIZABLE` xác định cách transaction quan sát những công việc đồng thời và mức bảo đảm tương ứng.

Lưu ý rằng cùng tên mức cô lập chưa chắc có hành vi y hệt ở PostgreSQL, MySQL, SQL Server hoặc Oracle. Khi cần báo cáo nhất quán, phải xác định semantics của **engine đang dùng**.

## 4. Tại sao snapshot là yếu tố quyết định độ nhất quán của báo cáo?

Trong các DBMS có **Multi-Version Concurrency Control (MVCC)**, các phiên bản hàng khác nhau có thể cùng tồn tại trong hệ thống một thời gian. Thay vì luôn đọc trực tiếp phiên bản mới nhất mà một transaction khác vừa ghi, database có thể chọn phiên bản phù hợp với snapshot của transaction đọc.

Ví dụ:

~~~text
Phiên bản ban đầu:              A = 100, B = 100
Transaction ghi commit:         A = 70,  B = 130

Snapshot trước commit:          thấy A = 100, B = 100
Snapshot sau commit:            thấy A = 70,  B = 130
Hai SELECT ở hai snapshot:      có thể thấy A = 100, B = 130
~~~

Snapshot cố định giúp nhiều câu truy vấn đọc cùng một bức ảnh logic. Tuy nhiên:

- Snapshot là hình ảnh **dữ liệu trong database** tại một mốc phù hợp với semantics của engine; nó không đóng băng đồng hồ, cache, API bên ngoài hoặc trạng thái các dịch vụ khác.
- Một snapshot nhất quán có thể **cũ hơn thời điểm phản hồi được gửi**.
- Các lệnh đọc dài có thể khiến database phải giữ các phiên bản hàng cũ lâu hơn, làm tăng chi phí lưu trữ và dọn dẹp.
- Nếu ứng dụng tự mở nhiều transaction hoặc lấy connection khác nhau cho từng truy vấn, không thể mặc nhiên nói các câu truy vấn dùng cùng một snapshot.

Tính nhất quán của một báo cáo không chỉ nằm ở việc từng dòng đúng kiểu dữ liệu hoặc từng câu `SELECT` chạy thành công. Nó còn nằm ở **mối quan hệ giữa các dữ kiện được đọc**.

### Đọc một lúc không tương đương hoàn toàn với SERIALIZABLE

Ở PostgreSQL, `REPEATABLE READ` phù hợp cho nhiều báo cáo cần ảnh chụp nhất quán. `SERIALIZABLE` hướng tới một bảo đảm mạnh hơn: kết quả của các transaction phải tương đương một thứ tự thực thi tuần tự hợp lệ. Hệ quản trị có thể phát hiện xung đột và hủy transaction với lỗi serialization để giữ cam kết đó.

Với giao dịch chỉ đọc, yêu cầu thường là tạo một báo cáo ổn định. Khi báo cáo cần ngữ nghĩa serializable vì kết quả phụ thuộc vào quan hệ với các giao dịch ghi đồng thời, có thể cân nhắc:

~~~sql
-- PostgreSQL: transaction chỉ đọc, mức SERIALIZABLE.
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM reservations WHERE event_id = 10;
SELECT SUM(amount_cents) FROM payments WHERE event_id = 10;

COMMIT;
~~~

Ứng dụng vẫn cần chính sách retry nếu transaction bị hủy vì serialization failure. PostgreSQL còn hỗ trợ dạng `SERIALIZABLE READ ONLY DEFERRABLE` cho các tác vụ báo cáo có thể đợi lấy một snapshot an toàn:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET TRANSACTION READ ONLY;
SET TRANSACTION DEFERRABLE;

-- Transaction có thể phải chờ ở lần lấy snapshot ban đầu.
SELECT COUNT(*) FROM reservations WHERE event_id = 10;

COMMIT;
~~~

Với dạng này, engine có thể chờ cho đến khi lấy được snapshot an toàn và sau đó tránh một số chi phí/xung đột thường gặp trong xử lý serializable. `DEFERRABLE` chỉ có ý nghĩa trong phạm vi read-only serializable theo hỗ trợ của PostgreSQL; không phải công tắc tăng độ an toàn chung cho mọi transaction.

## 5. Giao dịch chỉ đọc cấm những gì?

Câu trả lời phụ thuộc **DBMS, chế độ đã bật và loại đối tượng được thao tác**.

Trong PostgreSQL, transaction `READ ONLY` từ chối những câu lệnh có khả năng sửa đối tượng dữ liệu bền vững thuộc phạm vi cấm, ví dụ `INSERT`, `UPDATE`, `DELETE` hoặc `MERGE` trên bảng thường; nhiều lệnh DDL và một số lệnh khóa hàng cũng không được thực hiện trong chế độ này.

~~~sql
-- PostgreSQL
BEGIN READ ONLY;

SELECT COUNT(*) FROM orders;
-- Hợp lệ: đọc dữ liệu.

UPDATE orders
SET status = 'CANCELLED'
WHERE id = 5001;
-- Lỗi: không được thực hiện UPDATE trên bảng thường
-- trong transaction READ ONLY.

ROLLBACK;
~~~

Sau một lỗi SQL trong transaction PostgreSQL, transaction thường ở trạng thái thất bại và cần `ROLLBACK` trước khi tiếp tục trên connection đó. Do vậy ví dụ trên không tiếp tục thực thi thêm truy vấn rồi `COMMIT`.

**Một số ngoại lệ được thiết kế có chủ đích tồn tại.** Ví dụ, PostgreSQL cho phép những thao tác dữ liệu nhất định trên bảng tạm trong transaction chỉ đọc; do đó nói rằng `READ ONLY` “không thể thay đổi bất kỳ trạng thái nào trong phiên” là không chính xác. Việc thay đổi biến phiên, cursor, buffer, thông tin thống kê và tác vụ nội bộ cũng không nhất thiết cùng phạm vi với việc sửa dữ liệu nghiệp vụ bền vững.

### Không được đánh đồng SQL có chữ SELECT với thao tác thuần đọc

Một câu `SELECT` có thể gọi hàm do người dùng định nghĩa, đọc dữ liệu từ nguồn ngoài, hoặc khởi tạo tác dụng phụ khác trong giới hạn mà hệ thống cho phép.

~~~sql
SELECT some_application_function(:input);
~~~

Chỉ nhìn chữ `SELECT` không đủ chứng minh hàm `some_application_function` là thuần túy và không tạo tác dụng phụ. Nếu hàm cố ghi vào bảng thường trong transaction PostgreSQL read-only, database có thể từ chối thao tác ghi đó. Nhưng cơ chế read-only của database **không thể tự thu hồi một HTTP request, email hoặc thay đổi bên ngoài DB** mà một hàm mở rộng hoặc tầng ứng dụng đã thực hiện.

Khi cần bảo đảm không tác dụng phụ, phải xem xét cả **đường gọi thực tế**: stored procedure, foreign data wrapper, extension, callback, cache, API ngoài và thao tác của ứng dụng.

### “Không ghi dữ liệu nghiệp vụ” không có nghĩa “không có bất kỳ I/O ghi đĩa”

Đọc dữ liệu có thể làm database cập nhật bộ đệm, thống kê, dấu vết vận hành, thông tin giao dịch hoặc sử dụng file tạm để sort/hash lượng dữ liệu lớn. Nhật ký ứng dụng, audit hoặc log truy vấn cũng có thể được ghi. Cơ chế cụ thể thay đổi theo engine và cấu hình.

Vì thế, cam kết read-only nói về **những kiểu thay đổi dữ liệu được phép thực hiện trong transaction**, chứ không phải bảo đảm phần cứng sẽ không có hoạt động ghi nào.

## 6. Read-only không có nghĩa là không dùng khóa

Một quan niệm phổ biến: “Transaction chỉ đọc không sửa hàng nên chắc chắn không lấy khóa và không chặn ai.” Điều này sai.

Trong PostgreSQL, một lệnh `SELECT` thông thường có thể lấy khóa quan hệ `ACCESS SHARE` trên bảng được truy cập. Khóa này thường tương thích với các thao tác đọc/ghi hàng thông thường, nhưng xung đột với một số lệnh DDL yêu cầu `ACCESS EXCLUSIVE`, chẳng hạn một số hình thức `ALTER TABLE`.

Ví dụ khái niệm:

~~~text
Phiên A:
BEGIN READ ONLY;
SELECT * FROM large_table LIMIT 100;
-- Transaction vẫn đang mở.

Phiên B:
ALTER TABLE large_table ADD COLUMN note TEXT;
-- Có thể phải chờ khóa mà phiên A chưa giải phóng.

Phiên A:
COMMIT;
-- Giải phóng khóa của transaction A.
~~~

Không cần có `UPDATE` trong phiên A để tạo chờ đợi. Điều quan trọng là transaction có thể **giữ khóa lâu đến khi kết thúc**.

Ngoài khóa quan hệ, read-only còn ảnh hưởng gián tiếp đến hệ thống MVCC:

- Một snapshot tồn tại lâu có thể trì hoãn việc thu hồi phiên bản hàng cũ, làm tăng kích thước lưu trữ hoặc công việc dọn dẹp.
- Một truy vấn lớn có thể dùng nhiều CPU, bộ nhớ, I/O và tài nguyên thực thi, gây cạnh tranh với thao tác ghi.
- Trên bản sao phục vụ truy vấn, các read-only query kéo dài có thể xung đột với việc áp dụng thay đổi từ primary hoặc chịu chính sách hủy truy vấn riêng.

Do đó, “chỉ đọc” không có nghĩa “miễn phí”, “không có lock”, “không ảnh hưởng độ trễ” hay “an toàn để giữ transaction trong thời gian tùy ý”.

## 7. Read-only không khiến dữ liệu đứng yên

Khi một transaction báo cáo mở ở chế độ read-only, **giao dịch khác vẫn có thể ghi** nếu cơ chế cô lập và khóa cho phép. Dữ liệu “đang được xem” có thể cũ so với thực tại sau một vài mili giây.

Có ba khái niệm cần phân biệt:

| Khái niệm | Câu hỏi nó trả lời | Điều không được suy ra |
| --- | --- | --- |
| Read-only | Transaction này có được ghi dữ liệu thuộc phạm vi bị cấm không? | Không kết luận gì về thay đổi do transaction khác thực hiện. |
| Consistent snapshot | Các lần đọc có đang nhìn cùng một trạng thái logic không? | Không nói trạng thái đó là mới nhất tại thời điểm trả kết quả. |
| Freshness | Dữ liệu được đọc gần với trạng thái thực tế hiện tại tới mức nào? | Không tự bảo đảm nhiều lệnh đọc thuộc cùng một snapshot. |

Ví dụ, một transaction `REPEATABLE READ READ ONLY` bắt đầu lúc 10:00:00 có thể tiếp tục đọc cùng snapshot vào 10:00:10. Báo cáo của nó nhất quán với thời điểm snapshot, nhưng đã cũ 10 giây so với các transaction ghi có thể đã commit trong thời gian đó.

Một hệ thống phục vụ đọc từ replica bất đồng bộ còn có thể thấy dữ liệu cũ hơn primary do độ trễ sao chép. Cấu hình read-only **không biến replica thành nguồn dữ liệu cập nhật ngay lập tức**.

### Chọn độ mới hay một ảnh chụp ổn định?

Nhiều trường hợp không cần cả hai yêu cầu ở mức mạnh nhất. Ví dụ:

- Trang chi tiết một đơn hàng: thường muốn dữ liệu gần hiện tại; một truy vấn đơn giản trên nguồn đọc phù hợp có thể đủ.
- Bảng thống kê nhiều truy vấn: có thể ưu tiên nhất quán giữa các con số hơn là mới tuyệt đối.
- Quyết định cấp tín dụng hoặc trừ tồn kho: không được chỉ dựa trên một bản đọc read-only rồi tin dữ liệu vẫn hợp lệ lúc ghi; bước quyết định ghi cần cơ chế cạnh tranh riêng.

Không thể giải quyết tất cả bằng cách luôn dùng read-only. Phải làm rõ **tính đúng đắn cần ở thời điểm nào** và **đọc để hiển thị hay đọc để ra quyết định thay đổi dữ liệu**.

## 8. Đọc để quyết định ghi: ranh giới không thể bỏ qua

Giả sử ứng dụng kiểm tra còn hàng trong một giao dịch đọc, sau đó đóng transaction và mở một giao dịch mới để tạo đơn:

~~~text
T1 (READ ONLY):
    Đọc stock = 5
    Kết luận có thể bán 4 sản phẩm
    COMMIT

T2 (READ WRITE, phiên khác):
    Bán 4 sản phẩm
    COMMIT

T3 (READ WRITE, phiên đầu):
    Dựa trên kết luận từ T1, bán tiếp 4 sản phẩm
    COMMIT nếu không có biện pháp bảo vệ
~~~

Giao dịch đọc ở T1 không hề ghi dữ liệu, nhưng kết luận “còn hàng” đã **hết giá trị** tại thời điểm T3. Không một thuộc tính nào của read-only bảo lưu quyền sử dụng 4 sản phẩm cho giao dịch sau.

Một thiết kế an toàn chuyển **kiểm tra + thay đổi** thành thao tác có điều kiện trong cùng một giao dịch ghi:

~~~sql
-- Ví dụ PostgreSQL, transaction ghi thực sự.
BEGIN;

UPDATE inventory
SET stock = stock - 4
WHERE sku = 'SKU-1'
  AND stock >= 4
RETURNING stock;

-- Chỉ tạo order line nếu UPDATE trả về đúng một hàng.
-- Nếu không có hàng nào, từ chối đơn hoặc ROLLBACK.

COMMIT;
~~~

Ở đây, thao tác ghi chịu trách nhiệm giải quyết tranh chấp. Một `CHECK (stock >= 0)` còn có thể bảo vệ bất biến trên hàng tồn kho. Kết quả đọc trong một transaction read-only trước đó có ích để hiển thị hoặc gợi ý, **không thay thế xác nhận tại thời điểm ghi**.

Đây cũng là lý do không nên dùng read-only transaction như một cách “đặt trước” tài nguyên. Nếu nghiệp vụ cần giữ ghế, quota hoặc số tiền, phải có thao tác ghi được thiết kế để ghi nhận quyền giữ đó.

## 9. Read-only ở database, driver và framework khác nhau ra sao?

Ứng dụng Java/Spring thường gặp annotation:

~~~java
@Service
public class AccountReportService {
    private final JdbcTemplate jdbc;

    public AccountReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        readOnly = true,
        isolation = Isolation.REPEATABLE_READ
    )
    public long totalOfTwoAccounts(long firstId, long secondId) {
        Long first = jdbc.queryForObject(
            "SELECT balance_cents FROM accounts WHERE id = ?",
            Long.class, firstId
        );
        Long second = jdbc.queryForObject(
            "SELECT balance_cents FROM accounts WHERE id = ?",
            Long.class, secondId
        );

        if (first == null || second == null) {
            throw new IllegalStateException("Account has no balance");
        }
        return Math.addExact(first, second);
    }
}
~~~

Đoạn mã minh họa mục đích **nhiều lần đọc trong cùng một transaction**. Với PostgreSQL, `REPEATABLE READ` cung cấp một snapshot giao dịch cho các truy vấn thông thường trong phạm vi transaction đó.

Tuy nhiên, ý nghĩa `@Transactional(readOnly = true)` phải được hiểu theo từng tầng:

1. **Spring transaction abstraction:** truyền ý định read-only tới transaction manager và các resource được quản lý. Một số transaction manager coi đây là *hint*, không phải hàng rào ngăn mọi phương thức ghi.
2. **Persistence provider/ORM:** ví dụ một tích hợp Hibernate có thể thay đổi flush mode hoặc chính sách dirty checking để tối ưu việc đọc; cơ chế và mức áp dụng phụ thuộc phiên bản/tích hợp.
3. **JDBC driver:** khi được cấu hình bởi transaction manager, `Connection.setReadOnly(true)` cung cấp hint hoặc cờ chế độ cho driver; cách driver áp dụng tùy triển khai.
4. **Database server:** nếu chế độ read-only thực sự được kích hoạt trên session/transaction của server, engine mới trực tiếp từ chối những thao tác ghi mà chế độ của nó cấm.

Vì vậy, **annotation read-only không thể được coi là cơ chế phân quyền hoặc một bằng chứng tuyệt đối rằng SQL ghi sẽ bị từ chối**. Nó có thể giúp hiệu năng và truyền ý định, nhưng cần xác minh hành vi ở đúng DBMS và transaction manager của hệ thống.

### Ranh giới proxy và transaction thực tế

Với Spring proxy transaction thông dụng, việc gọi trực tiếp một phương thức được gắn `@Transactional` từ phương thức khác **trong cùng object** (*self-invocation*) có thể đi vòng qua proxy. Khi đó annotation có thể không mở transaction mới như người viết kỳ vọng.

~~~java
@Service
public class ReportService {
    public void runJob() {
        // Gọi nội bộ có thể không đi qua proxy @Transactional.
        readSnapshot();
    }

    @Transactional(readOnly = true)
    public void readSnapshot() {
        // ...
    }
}
~~~

Phải đảm bảo phương thức được gọi qua cơ chế quản lý transaction thực tế; nếu không, nhiều truy vấn có thể chạy trong những transaction implicit riêng. Đặc tính này của proxy là lý do một annotation trông đúng trên source chưa đủ chứng minh việc đọc đang dùng cùng snapshot.

### Đã ở trong một transaction ghi thì sao?

Nếu một phương thức read-only tham gia **transaction có sẵn** (ví dụ propagation `REQUIRED`), thuộc tính read-only của phương thức bên trong không nhất thiết biến transaction ghi đã mở thành read-only. Chính sách của transaction bao ngoài và transaction manager đang sử dụng quyết định phạm vi thực tế. Vì vậy, không nên suy ra mỗi phương thức có annotation riêng sẽ được database bảo vệ như một transaction độc lập.

Mặt khác, một phương thức đọc dài gọi các dịch vụ khác có thể vô tình mở rộng thời gian sống của transaction, giữ snapshot và khóa lâu hơn mong muốn.

## 10. Vòng đời đọc trong ứng dụng: begin, sử dụng, kết thúc

Một giao dịch chỉ đọc cần được quản lý giống một tài nguyên có thời gian sống rõ ràng.

### Bắt đầu

Xác lập phạm vi transaction trước các truy vấn cần nằm cùng snapshot. Chọn `READ COMMITTED` nếu mỗi câu truy vấn có thể đọc một trạng thái mới; chọn snapshot cố định phù hợp nếu báo cáo yêu cầu nhiều lần đọc nhất quán.

~~~sql
-- PostgreSQL: tạo một ảnh chụp thống nhất cho nhiều truy vấn.
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT id, status FROM orders WHERE id = 5001;
SELECT order_id, product_id, quantity
FROM order_items
WHERE order_id = 5001;

COMMIT;
~~~

Các lệnh `SET TRANSACTION` cần được gọi trước khi transaction đã thực hiện truy vấn hoặc thao tác dữ liệu có ảnh hưởng đến việc thay đổi thiết lập transaction. Nếu đang dùng framework, cấu hình nên được thực hiện bằng transaction manager thay vì tùy tiện gửi các lệnh `SET` giữa chừng.

### Trong lúc đọc

Một truy vấn có thể cần nhiều giây hoặc trả về hàng triệu hàng. Trong khoảng đó, session có thể giữ transaction, snapshot, con trỏ hoặc tài nguyên thực thi. Đặt timeout và giới hạn số lượng dữ liệu phù hợp; đọc theo lô và thiết kế export cần cân nhắc tuổi thọ snapshot.

### Kết thúc thành công

Gửi `COMMIT` và bảo đảm resource được đóng/trả về pool. Với read-only transaction, `COMMIT` không đồng nghĩa phải có thay đổi dữ liệu được ghi, nhưng có ý nghĩa kết thúc transaction. Trong Java, dùng transaction manager hoặc cấu trúc `try/finally` ở tầng JDBC để chắc chắn connection và các trạng thái cần thiết được khôi phục.

### Kết thúc lỗi

Nếu một câu SQL thất bại, transaction bị hủy hoặc timeout, cần rollback và giải phóng connection. Ví dụ PostgreSQL sau lỗi trong transaction, các truy vấn sau thường không thể chạy bình thường cho đến khi transaction lỗi được rollback.

### Đừng duy trì transaction qua thời gian chờ người dùng

Tránh mở transaction lúc render trang, sau đó giữ nó trong khi chờ người dùng bấm nút “Xác nhận”. Đến khi người dùng phản hồi, snapshot đã cũ, tài nguyên còn bị giữ và quyết định có thể không còn hợp lệ. Hãy đóng transaction đọc sau khi có kết quả, rồi kiểm tra lại trong một transaction ghi thích hợp khi người dùng thật sự thực hiện hành động.

## 11. Đọc từ replica chỉ đọc khác gì transaction chỉ đọc?

Hai cơ chế cùng dùng từ “chỉ đọc” nhưng có phạm vi khác nhau.

**Read-only transaction** là một chế độ trong phạm vi transaction. Nó xác định transaction được phép thực hiện những gì trên server đang kết nối, và có thể dùng ngay trên primary nếu DBMS hỗ trợ.

**Read-only replica** là một nút hoặc endpoint được vận hành để phục vụ truy vấn thay vì nhận những thay đổi nghiệp vụ theo cách của primary. Replica có thể áp dụng log hoặc luồng thay đổi nhận từ primary và do đó trạng thái của nó vẫn tiến triển theo thời gian.

| Câu hỏi | Transaction READ ONLY trên primary | Đọc từ replica bất đồng bộ |
| --- | --- | --- |
| Có thể cấm ghi từ transaction đang chạy? | Có theo chế độ DBMS | Thường có theo vai trò/cấu hình endpoint |
| Dữ liệu chắc chắn mới bằng primary? | Phụ thuộc snapshot và thời điểm đọc | Không; replica có thể trễ |
| Nhiều câu truy vấn chắc chắn có chung snapshot? | Chỉ khi isolation/cơ chế snapshot bảo đảm | Cũng phải chọn isolation phù hợp |
| Có chi phí truy vấn và snapshot? | Có | Có, đồng thời có thể chịu xung đột với quá trình áp dụng thay đổi |
| Có thay thế kiểm tra cạnh tranh ở transaction ghi? | Không | Không |

Ví dụ vừa thanh toán thành công trên primary, sau đó chuyển ngay sang replica để kiểm tra trạng thái giao dịch: replica có thể chưa nhận commit mới và tạm thời hiển thị `PENDING`. Một transaction read-only trên replica không tự bảo đảm *read-your-writes* từ primary.

Khi nghiệp vụ yêu cầu **đọc lại chắc chắn thấy giao dịch vừa ghi**, phải sử dụng routing/consistency mechanism phù hợp: đọc từ primary, chờ replica bắt kịp một vị trí log đã biết, hoặc giải pháp khác do hệ thống hỗ trợ. Không thể suy ra điều đó chỉ từ nhãn read-only.

## 12. Các hệ quản trị không có một cú pháp read-only chung

SQL được minh họa trong bài học chủ yếu dành cho PostgreSQL. Các hệ quản trị khác có cơ chế khác nhau; không nên sao chép lệnh mà không kiểm tra dialect.

| DBMS | Ví dụ/cơ chế tiêu biểu | Lưu ý |
| --- | --- | --- |
| **PostgreSQL** | `BEGIN READ ONLY` hoặc `SET TRANSACTION READ ONLY` | Được database thực thi theo quy tắc riêng; isolation xác định snapshot. |
| **MySQL/InnoDB** | `START TRANSACTION READ ONLY` | Có thể tối ưu transaction đọc; ngoại lệ đối với bảng tạm và chi tiết snapshot phụ thuộc InnoDB/cấu hình. |
| **Oracle Database** | `SET TRANSACTION READ ONLY` | Hướng đến một ảnh chụp nhất quán cho các truy vấn trong transaction; cú pháp và thời điểm thiết lập cần tuân theo Oracle. |
| **SQL Server** | Kết hợp mức isolation như `SNAPSHOT` (khi được bật), quyền truy cập và cấu hình DB/replica | Không có cú pháp transaction `BEGIN READ ONLY` tương đương trực tiếp với PostgreSQL; phải tách yêu cầu không ghi khỏi yêu cầu snapshot. |
| **SQLite** | Mở connection ở chế độ chỉ đọc hoặc cấu hình `PRAGMA query_only` cho các loại thao tác phù hợp | Cơ chế lock, snapshot và journal/WAL khác với PostgreSQL; `BEGIN` không tự mang nhãn read-only chung. |

Trong MySQL/InnoDB, `REPEATABLE READ` thường được dùng cho consistent nonlocking reads nhưng việc kết hợp với locking reads, autocommit và các dạng truy vấn khác có khác biệt; cần đọc đúng hành vi của workload. Ở Oracle, read-only transaction cũng có semantics riêng. Bảng trên nhằm phân biệt **cơ chế**, không phải khẳng định mọi hệ đều có cùng một mức bảo đảm chỉ bằng một câu SQL.

## 13. Read-only không phải cơ chế bảo mật thay cho quyền truy cập

Một service dùng `@Transactional(readOnly = true)` vẫn có thể chạy với tài khoản database được cấp `INSERT`, `UPDATE` và `DELETE`. Nếu một code path khác mở transaction ghi hoặc bỏ qua annotation, tài khoản ấy có thể ghi.

Nếu yêu cầu hệ thống là **“dịch vụ báo cáo tuyệt đối không được thay đổi các bảng nghiệp vụ”**, nên bổ sung kiểm soát ở cấp đặc quyền:

~~~sql
-- PostgreSQL: ví dụ định hướng cấu hình quyền.
-- DBA phải đánh giá quyền hiện có, schema, view,
-- routine và quyền mặc định trước khi áp dụng.

GRANT CONNECT ON DATABASE reporting_db TO report_reader;
GRANT USAGE ON SCHEMA public TO report_reader;
GRANT SELECT ON TABLE accounts, orders TO report_reader;
~~~

Những lệnh `GRANT` trên **chỉ minh họa quyền đọc được phép**, không tự thu hồi quyền ghi đã được cấp trực tiếp hoặc thừa kế từ role khác. Việc đảm bảo quyền chỉ đọc thực tế còn cần kiểm soát membership, owner, routine, default privileges và các schema liên quan. Không nên đưa nguyên ví dụ vào hệ thống thật mà không rà soát chính sách cấp quyền.

Một mô hình bảo vệ có thể gồm:

1. **Thiết kế ứng dụng:** các phương thức báo cáo không gọi đường ghi ngoài ý muốn.
2. **Framework hint/read-only mode:** giảm rủi ro flush ngoài ý muốn và tối ưu cách truy cập.
3. **DB read-only transaction:** từ chối các thao tác ghi bị cấm ở cấp transaction.
4. **Role chỉ có quyền cần thiết:** hạn chế khả năng ghi dù transaction mode bị cấu hình sai.
5. **Endpoint báo cáo/replica phù hợp:** phân tách nguồn truy vấn khi kiến trúc và yêu cầu dữ liệu cho phép.

Các lớp kiểm soát này bổ sung cho nhau nhưng không thay thế việc thiết kế bảo mật tổng thể, đặc biệt khi có stored procedure hoặc quyền truy cập tới hệ thống bên ngoài.

## 14. Hiệu năng: đọc không ghi vẫn có chi phí

Read-only transaction có thể giúp DBMS hoặc ORM thực hiện một số tối ưu, nhưng **không có bảo đảm mọi truy vấn sẽ nhanh hơn**.

### Những lợi ích có thể có

- Một số engine có thể giảm công việc quản lý transaction ghi khi biết trước transaction không sửa dữ liệu.
- ORM có thể bớt flush hoặc dirty checking trong những cấu hình thích hợp.
- Snapshot nhất quán giúp tránh việc ứng dụng phải tự chắp vá các kết quả đọc không đồng bộ.
- Đọc từ nút/endpoint được thiết kế riêng có thể phân tách một phần tải truy vấn khỏi primary.

### Những chi phí còn tồn tại

- CPU để lọc, join, sort, aggregate, JSON encode và truyền dữ liệu qua mạng.
- I/O đọc dữ liệu và có thể I/O ghi file tạm hoặc log vận hành.
- Bộ nhớ cho kết quả trung gian, hash join, sort và buffer.
- Khóa quan hệ, snapshot và metadata cần quản lý.
- Việc giữ phiên bản MVCC lâu hơn nếu transaction đọc kéo dài.
- Độ trễ do tranh chấp resource hoặc xung đột replication.

Một giao dịch read-only lấy toàn bộ 10 triệu hàng để xuất báo cáo có thể gây tải lớn hơn rất nhiều so với một transaction ghi cập nhật một hàng. Vì thế, hiệu năng phải được đánh giá bằng lượng dữ liệu, truy vấn, chỉ mục, kế hoạch thực thi, transaction duration và cấu hình server, không chỉ qua nhãn read-only.

### Read-only lâu có thể làm hệ thống ghi chậm hơn gián tiếp

Trong PostgreSQL, một snapshot cũ còn sống có thể trì hoãn việc dọn dẹp một số phiên bản hàng đã chết (*dead tuples*) mà transaction đó có thể cần nhìn thấy. Khi các transaction cập nhật tiếp tục tạo phiên bản mới, dữ liệu và chỉ mục có thể phình ra, gây tăng chi phí đọc/ghi.

Điều này không có nghĩa mỗi read-only transaction đều gây bloat đáng kể. Rủi ro tăng với transaction dài, tần suất update cao, lượng dữ liệu lớn hoặc vận hành autovacuum chưa phù hợp. Do đó, giới hạn thời gian sống transaction là một phần của thiết kế báo cáo đáng tin cậy.

## 15. Ví dụ thiết kế: báo cáo đơn hàng nhất quán

Giả sử endpoint cần trả về:

- Trạng thái đơn hàng.
- Tổng tiền từ các dòng hàng.
- Tổng khoản thanh toán đã được ghi nhận.
- Số tiền còn phải thanh toán.

Các giá trị có thể được cập nhật bởi những giao dịch khác. Thiết kế báo cáo chỉ đọc cần trả lời ba câu hỏi trước khi viết code:

**Thứ nhất: các số có cần cùng một snapshot không?** Nếu chỉ là dashboard gần thời gian thực, ứng dụng có thể chấp nhận những giá trị được lấy ở thời điểm khác nhau và hiển thị thời gian cập nhật. Nếu là báo cáo đối soát, thường cần các giá trị nhất quán trong cùng một ảnh chụp.

**Thứ hai: nguồn dữ liệu phải mới đến mức nào?** Báo cáo sau thanh toán vừa thành công có thể cần đọc primary để tránh replication lag; báo cáo tổng hợp hàng giờ có thể chấp nhận dữ liệu cũ hơn.

**Thứ ba: có phát sinh thao tác ghi nào từ luồng báo cáo không?** Nếu thao tác xuất cần ghi “đã xuất lần cuối”, đó là một thay đổi nghiệp vụ. Có thể tách thành transaction ghi độc lập theo thiết kế hoặc xác định lại luồng nghiệp vụ; không nên âm thầm giả định nó nằm trong read-only transaction.

Một transaction đọc nhất quán ở PostgreSQL:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT id, status, customer_id
FROM orders
WHERE id = :order_id;

SELECT COALESCE(SUM(quantity * unit_price_cents), 0)
       AS total_items_cents
FROM order_items
WHERE order_id = :order_id;

SELECT COALESCE(SUM(amount_cents), 0)
       AS total_paid_cents
FROM payments
WHERE order_id = :order_id
  AND status = 'CAPTURED';

COMMIT;
~~~

Trong trường hợp này, các kết quả nhìn cùng snapshot PostgreSQL. Nhưng tổng tiền có đúng theo nghiệp vụ hay không còn phụ thuộc quy tắc định giá, giảm giá, hoàn tiền, thuế, currency và những bất biến mà schema/transaction ghi cưỡng chế. **Snapshot nhất quán không thay thế định nghĩa nghiệp vụ đúng**.

Có thể dùng một câu truy vấn tổng hợp nếu điều đó phù hợp và đơn giản hơn. Khi chỉ có một câu lệnh, nhiều DBMS cung cấp tính nhất quán theo snapshot câu lệnh ở isolation tương ứng, giảm nhu cầu giữ transaction mở qua nhiều lần round trip.

## 16. Một số trường hợp dễ hiểu nhầm

### “Read-only thì không cần COMMIT hoặc ROLLBACK”

Không đúng ở mức quản lý vòng đời. Dù không tạo thay đổi bền vững, transaction vẫn giữ tài nguyên và trạng thái. Một transaction mở không kết thúc có thể làm connection pool cạn kiệt hoặc trì hoãn cleanup.

### “Read-only luôn cho kết quả giống nhau khi SELECT lại”

Không đúng. Ở PostgreSQL `READ COMMITTED`, hai câu `SELECT` trong cùng read-only transaction có thể thấy các commit khác nhau. Cần mức cô lập/snapshot phù hợp nếu yêu cầu lặp lại cùng kết quả.

### “Read-only bảo đảm đọc dữ liệu mới nhất”

Không đúng. `REPEATABLE READ` có thể giữ snapshot cũ; replica bất đồng bộ có thể trễ primary. Freshness là yêu cầu riêng.

### “Read-only không thể gây khóa hoặc làm chậm writer”

Không đúng. Plain `SELECT` có thể giữ khóa quan hệ, và snapshot dài ảnh hưởng MVCC garbage collection; truy vấn nặng cạnh tranh CPU/I/O.

### “Ứng dụng đã gắn readOnly nên SQL ghi chắc chắn bị chặn”

Không chắc chắn. Framework hint, driver mode và enforcement tại DBMS là các cơ chế khác nhau. Nếu cần giới hạn đặc quyền, phải thiết kế permission ở cấp database và xác nhận hành vi thật.

### “Không thay đổi bảng nghiệp vụ đồng nghĩa không có tác dụng phụ”

Không đúng. Gửi thông điệp, ghi log, gọi HTTP, thay đổi cache hoặc thao tác trên đối tượng tạm có thể xảy ra ngoài phạm vi cấm của transaction read-only.

### “Dữ liệu đọc trong read-only transaction có thể dùng để quyết định ghi bất kỳ lúc nào sau đó”

Không an toàn. Sau khi transaction đọc kết thúc, transaction khác có thể cập nhật trạng thái. Quyết định ghi phải bảo vệ điều kiện trong transaction ghi tương ứng, ví dụ bằng unique constraint, conditional update, lock hoặc serializable khi thích hợp.

### “SERIALIZABLE READ ONLY luôn nhanh và không bao giờ cần xử lý lỗi”

Không đúng như một mệnh đề chung. Serializable có thể tốn chi phí và xuất hiện serialization failure; chế độ `DEFERRABLE` đặc thù PostgreSQL dành cho các transaction serializable read-only chấp nhận chờ snapshot an toàn. Vẫn cần xử lý timeout, hủy truy vấn, lỗi connection và những sự cố khác.

## 17. Cách chọn chế độ đọc cho từng nhu cầu

| Nhu cầu | Điểm khởi đầu hợp lý | Điều cần kiểm soát thêm |
| --- | --- | --- |
| Đọc một trường của một bản ghi để hiển thị | Một `SELECT` ngắn; có thể dùng autocommit | Nguồn đọc và độ mới phù hợp |
| Dashboard gồm nhiều số liệu tương đối độc lập | Các truy vấn đọc ngắn | Ghi rõ độ trễ/khả năng lệch thời điểm |
| Báo cáo cần nhiều bảng cùng một thời điểm | Read-only transaction với snapshot transaction phù hợp | Thời gian giữ snapshot, timeout và dung lượng dữ liệu |
| Báo cáo cần tính tuần tự mạnh với giao dịch ghi | Serializable read-only theo khả năng engine | Retry/deferrable và chi phí chờ |
| Đọc từ replica nhằm giảm tải primary | Connection được định tuyến tới replica chỉ đọc | Replication lag, read-your-writes, failover |
| Kiểm tra điều kiện trước khi trừ tồn kho/chuyển tiền | Xác nhận trực tiếp trong transaction ghi | Conditional update/lock/ràng buộc; idempotency |
| Service báo cáo không được phép sửa dữ liệu nghiệp vụ | Role DB giới hạn quyền + read-only mode phù hợp | Kiểm soát role, stored routine, đường gọi bên ngoài |
| Xuất dữ liệu rất lớn | Batch/cursor theo thiết kế và thời hạn xử lý rõ ràng | Snapshot quá dài, resource, tính nhất quán khi chia lô |

### Quy trình suy nghĩ trước khi triển khai

1. **Xác định mục tiêu đọc:** cần xem thông tin mới nhất, cần snapshot nhất quán, hay cần một phép đọc để ra quyết định nghiệp vụ?
2. **Chọn phạm vi:** một câu lệnh, một transaction đọc nhiều câu lệnh, hoặc nhiều batch có điểm checkpoint riêng.
3. **Chọn isolation theo DBMS:** xem rõ mức cô lập có snapshot theo câu lệnh hay toàn transaction.
4. **Xác lập read-only ở đúng tầng:** code intent, transaction manager, DB server và quyền truy cập nếu cần.
5. **Thiết kế thời điểm kết thúc:** đóng transaction ngay sau khi lấy dữ liệu cần thiết, xử lý cả lỗi, timeout và hủy.
6. **Chọn nguồn đọc phù hợp:** primary/replica và cơ chế đảm bảo freshness nếu nghiệp vụ cần.
7. **Không tái sử dụng kết luận đọc cũ làm bảo đảm cho thao tác ghi:** xác nhận điều kiện trong transaction ghi, với cơ chế concurrency control phù hợp.

## Kết luận

**Giao dịch chỉ đọc là một cam kết giới hạn quyền thay đổi của chính transaction đang chạy; nó không phải cam kết rằng toàn bộ cơ sở dữ liệu ngừng thay đổi.** Độ nhất quán của nhiều câu truy vấn phụ thuộc isolation và snapshot, độ mới phụ thuộc thời điểm đọc cùng nguồn dữ liệu, còn tác động vận hành phụ thuộc khóa, MVCC, resource và tuổi thọ transaction.

Về mặt vòng đời, giao dịch chỉ đọc vẫn cần **bắt đầu với cấu hình rõ ràng, chạy các truy vấn trong phạm vi phù hợp và kết thúc bằng commit hoặc rollback**. Về mặt tính đúng đắn nghiệp vụ, cần phối hợp read-only mode với quyền database, kiểm soát concurrency, dữ liệu nhất quán và giới hạn tác dụng phụ. Khi hiểu đúng phạm vi của lời hứa “không thay đổi dữ liệu”, ta mới biết chính xác nó bảo đảm điều gì và những gì phải được thiết kế bổ sung.
