# Bảng tạm và kết quả trung gian: khi nào giảm được công việc lặp

Một truy vấn báo cáo hoặc một quy trình nghiệp vụ có thể cần cùng một tập dữ liệu nhiều lần: lọc các đơn hàng đủ điều kiện, tính tổng theo khách hàng, tìm nhóm khách hàng cần xử lý rồi dùng lại nhóm đó cho nhiều phép nối hoặc nhiều bước tính toán. Nếu mỗi bước đều chạy lại cùng một truy vấn tốn kém, hệ quản trị có thể đọc lại nhiều trang, tính lại biểu thức, nối lại bảng lớn và lặp lại cùng một công việc.

Bảng tạm và các dạng kết quả trung gian cho phép lưu một phần kết quả để dùng lại. Khi được thiết kế đúng, chúng có thể giảm công việc lặp, thu hẹp dữ liệu trước khi nối, tạo điểm đo rõ ràng và cho phép bổ sung chỉ mục hoặc thống kê phù hợp. Tuy nhiên, việc lưu kết quả cũng tạo thêm chi phí ghi, đọc, cấp phát bộ nhớ, I/O tạm và quản lý vòng đời. Một bảng tạm không tự động làm truy vấn nhanh hơn.

Trong chương **Mẫu truy vấn** của module **DATABASE_PERFORMANCE**, bài học này giải thích khi nào nên tái sử dụng kết quả trung gian, cách chọn giữa CTE, subquery, materialization và bảng tạm, cùng cách đo lợi ích thực tế. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, quyết định lưu kết quả phải xuất phát từ workload, số lần dùng lại, kích thước dữ liệu, kế hoạch thực thi và chi phí tài nguyên, đồng thời bảo toàn tính nhất quán của dữ liệu.

## 1. Công việc lặp xuất hiện ở đâu?

Một pipeline dữ liệu thường có nhiều bước:

1. Lọc tập đơn hàng theo tenant, trạng thái và thời gian.
2. Tính tổng giá trị đơn hàng.
3. Phân loại khách hàng theo tổng chi tiêu.
4. Tìm các khách hàng có đơn hàng cần rà soát.
5. Tạo báo cáo chi tiết và báo cáo tổng hợp từ cùng tập khách hàng.

Nếu mỗi bước đều viết lại điều kiện lọc ban đầu, cơ sở dữ liệu có thể phải quét và lọc cùng bảng nhiều lần. Nếu truy vấn con chứa nhiều phép nối hoặc hàm tính toán đắt, chi phí lặp có thể lớn hơn chi phí lưu một kết quả đã tính.

Một số dạng công việc lặp phổ biến:

- Cùng một phép lọc được dùng ở nhiều truy vấn hoặc nhiều nhánh của một truy vấn.
- Cùng một phép nối lớn được thực hiện lại để tạo các chỉ số khác nhau.
- Một phép tổng hợp phức tạp được tính nhiều lần với cùng phạm vi dữ liệu.
- Một tập khóa đủ điều kiện được dùng để cập nhật, đối chiếu và xuất báo cáo.
- Một biểu thức chuẩn hóa hoặc tính điểm tốn CPU được dùng trong nhiều bước.
- Một tập dữ liệu trung gian cần được kiểm tra, phân trang hoặc xử lý theo từng giai đoạn.

Trước khi tạo bảng tạm, hãy xác định công việc nào thực sự bị lặp. Nếu bộ tối ưu đã gộp hoặc tái sử dụng phép tính, việc tạo thêm bảng tạm có thể chỉ làm tăng I/O. Nếu hai truy vấn dùng cùng cú pháp nhưng tham số hoặc snapshot khác nhau, kết quả lưu lại có thể không còn đúng cho lần dùng sau.

## 2. Các dạng kết quả trung gian

Không phải mọi kết quả trung gian đều là bảng tạm do ứng dụng tạo. Hệ quản trị có nhiều cách biểu diễn và quản lý dữ liệu trung gian.

| Dạng | Vòng đời và hành vi khái quát | Khi phù hợp |
|---|---|---|
| Derived table (subquery trong FROM) | Kết quả nằm trong một truy vấn lớn; optimizer có thể inline hoặc materialize | Một lần dùng trong một câu SQL |
| CTE | Đặt tên cho một biểu thức truy vấn; có thể được inline hoặc materialize tùy hệ quản trị và cú pháp | Làm rõ truy vấn nhiều bước, tái sử dụng logic trong một câu |
| Spool hoặc worktable nội bộ | Do optimizer tạo trong kế hoạch để lưu hoặc tái dùng dữ liệu | Khi kế hoạch cần lưu kết quả trung gian nội bộ |
| Temporary table | Đối tượng tạm có thể được truy vấn nhiều lần trong phạm vi phiên hoặc transaction tùy hệ quản trị | Khi nhiều câu lệnh cần dùng lại cùng tập kết quả |
| Materialized view | Kết quả truy vấn được lưu bền hơn và làm mới theo cơ chế riêng | Kết quả tổng hợp dùng lặp lại qua nhiều phiên hoặc nhiều request |
| Staging table | Bảng lưu dữ liệu trung gian theo batch hoặc quy trình | Pipeline ETL, nhập dữ liệu và xử lý nhiều giai đoạn |

Các dạng này có semantics khác nhau. Không nên xem CTE là bảng tạm hoặc giả định mọi CTE đều được tính đúng một lần. Một số hệ quản trị inline CTE vào truy vấn bên ngoài; một số hỗ trợ chỉ định materialization; một số có thể tạo spool khi thấy có lợi. Hãy xem kế hoạch và tài liệu của hệ quản trị đang dùng.

## 3. Khi nào kết quả trung gian đáng được lưu lại?

Lưu kết quả có khả năng hữu ích khi chi phí tính lại lớn hơn chi phí tạo, ghi, đọc và duy trì kết quả đó.

Các tình huống thường đáng cân nhắc:

- Một tập dữ liệu tốn kém được dùng trong nhiều câu lệnh.
- Nhiều nhánh xử lý cần cùng một phép lọc hoặc phép nối.
- Kết quả trung gian nhỏ hơn đáng kể so với dữ liệu nguồn.
- Phép tính chứa biểu thức, hàm hoặc phép tổng hợp tốn CPU.
- Cần đặt ranh giới giữa các giai đoạn để quan sát số hàng và thời gian riêng.
- Cần tạo chỉ mục trên tập kết quả trung gian để hỗ trợ nhiều phép nối tiếp theo.
- Cần cố định một tập khóa cho nhiều bước trong cùng một quy trình.

Ngược lại, lưu kết quả có thể không phù hợp khi:

- Tập kết quả rất lớn và chỉ được dùng một lần.
- Truy vấn nguồn vốn đã rẻ và được cache tốt.
- Kết quả cần được tính lại với tham số khác nhau ở mỗi lần dùng.
- Bảng tạm khiến optimizer mất cơ hội đẩy điều kiện hoặc kết hợp các phép toán.
- Chi phí ghi/đọc dữ liệu tạm lớn hơn chi phí tính lại.
- Nhiều phiên đồng thời tạo các bảng tạm lớn làm tăng áp lực lên temp storage.

Một tiêu chí thực tế là số lần dùng lại. Nếu cùng kết quả được dùng bởi ba hoặc bốn câu lệnh trong một batch, việc tính một lần có thể đáng thử. Nhưng số lần sử dụng không đủ để quyết định; kích thước kết quả và chi phí mỗi lần tính lại cũng quan trọng.

## 4. Ước lượng chi phí: tính lại hay materialize?

Có thể mô hình hóa đơn giản:

~~~text
Chi phí tính lại:
  số_lần_dùng × chi_phí_tính_một_lần

Chi phí lưu và dùng lại:
  chi_phí_tạo_kết_quả
  + chi_phí_ghi_kết_quả
  + số_lần_đọc_lại × chi_phí_đọc
  + chi_phí_chỉ_mục/thống_kê (nếu có)
  + chi_phí_quản_lý_vòng_đời
~~~

Đây là mô hình tư duy, không phải công thức cost chính xác của hệ quản trị. Các chi phí có thể chồng lấp với cache, song song hóa hoặc I/O bất đồng bộ. Dù vậy, nó giúp đặt đúng câu hỏi: kết quả có đủ đắt để tính lại không, đủ nhỏ để lưu không và có được dùng lại đủ nhiều không?

Ví dụ, một truy vấn lọc 50 triệu hàng và tổng hợp còn 20.000 khách hàng có thể tạo kết quả nhỏ hơn nhiều so với nguồn. Nếu kết quả đó được dùng trong bốn báo cáo, lưu kết quả tổng hợp có thể giảm đáng kể công việc. Ngược lại, nếu truy vấn chỉ trả 100 hàng từ một chỉ mục hiệu quả và chỉ dùng một lần, tạo bảng tạm có thể đắt hơn.

Đo riêng các giai đoạn tạo và đọc lại. Đừng chỉ đo câu SELECT cuối cùng rồi bỏ qua chi phí tạo bảng tạm, tạo chỉ mục, thu thập thống kê và dọn dẹp.

## 5. CTE và subquery: khi nào chưa cần bảng tạm?

CTE (Common Table Expression) và derived table giúp chia truy vấn thành các phần có tên hoặc có phạm vi rõ ràng. Chúng thường là lựa chọn đầu tiên khi kết quả chỉ cần trong một câu SQL.

Ví dụ:

~~~sql
WITH eligible_orders AS (
    SELECT order_id, customer_id, total
    FROM orders
    WHERE status = 'COMPLETED'
      AND created_at >= :start_time
      AND created_at < :end_time
),
customer_totals AS (
    SELECT customer_id, SUM(total) AS amount_total
    FROM eligible_orders
    GROUP BY customer_id
)
SELECT customer_id, amount_total
FROM customer_totals
WHERE amount_total >= :minimum_amount;
~~~

CTE làm rõ hai bước: chọn đơn hàng đủ điều kiện và tổng hợp theo khách hàng. Hệ quản trị có thể biến đổi chúng thành một kế hoạch liên tục, đẩy điều kiện và kết hợp các toán tử để tránh ghi dữ liệu trung gian ra đĩa.

Một CTE được tham chiếu nhiều lần không nhất thiết có cùng hành vi ở mọi hệ quản trị. Tùy phiên bản và cú pháp, optimizer có thể inline, tính lại, materialize hoặc tạo một cấu trúc nội bộ để tái sử dụng. Vì vậy, đừng suy luận rằng đặt tên CTE đồng nghĩa với việc tính đúng một lần.

### 5.1. Khi nào nên giữ truy vấn liền mạch?

Truy vấn liền mạch thường có lợi khi:

- Kết quả trung gian chỉ dùng một lần.
- Optimizer có thể đẩy điều kiện xuống nguồn.
- Có thể loại bỏ cột không cần thiết trước khi đọc.
- Các phép nối và tổng hợp có thể được sắp xếp lại có lợi.
- Không cần dùng kết quả qua nhiều câu lệnh.

Truy vấn liền mạch giúp optimizer nhìn thấy toàn bộ biểu thức và có cơ hội chọn kế hoạch toàn cục. Tách truy vấn thành bảng tạm có thể làm mất một số cơ hội tối ưu xuyên giai đoạn.

### 5.2. Materialization có thể có ích ngay trong một câu SQL

Một số hệ quản trị hỗ trợ chỉ định hoặc điều khiển việc materialize CTE. Materialization có thể tránh tính lại biểu thức được tham chiếu nhiều lần, nhưng cũng tạo chi phí ghi/đọc và có thể ngăn predicate pushdown.

Ví dụ, cú pháp **MATERIALIZED** hoặc **NOT MATERIALIZED** tồn tại trong một số hệ quản trị và phiên bản, nhưng không phải cú pháp SQL phổ quát. Hãy kiểm tra tài liệu phiên bản cụ thể và so sánh kế hoạch trước khi dùng.

## 6. Bảng tạm: dùng lại kết quả qua nhiều câu lệnh

Bảng tạm phù hợp khi một tập kết quả được dùng trong nhiều câu SQL hoặc nhiều bước xử lý trong cùng một phiên làm việc. Ứng dụng có thể tạo bảng, nạp dữ liệu, tạo chỉ mục, thu thập thống kê rồi dùng bảng đó nhiều lần.

Ví dụ khái quát:

~~~sql
CREATE TEMPORARY TABLE selected_orders AS
SELECT order_id, customer_id, total, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
  AND created_at >= :start_time
  AND created_at < :end_time;
~~~

Sau đó, cùng tập selected_orders có thể được dùng để tạo tổng theo khách hàng:

~~~sql
SELECT customer_id, SUM(total) AS completed_total
FROM selected_orders
GROUP BY customer_id;
~~~

Và dùng lại để lấy danh sách chi tiết:

~~~sql
SELECT order_id, customer_id, total
FROM selected_orders
ORDER BY created_at DESC;
~~~

Nếu truy vấn nguồn tốn kém và cả hai bước cần đúng cùng tập đơn hàng, bảng tạm có thể tránh lọc orders lặp lại. Tuy nhiên, nếu selected_orders có hàng triệu bản ghi và chỉ dùng một lần cho mỗi bước đơn giản, chi phí ghi và đọc bảng tạm có thể lớn.

Cú pháp CREATE TEMPORARY TABLE, phạm vi tồn tại, hỗ trợ index và cơ chế ghi dữ liệu khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ quản trị khác. Ví dụ trên là mẫu khái niệm; cần điều chỉnh cú pháp theo nền tảng.

## 7. Giảm kích thước trước khi lưu

Một lỗi thường gặp là lưu toàn bộ hàng và cột từ bảng nguồn rồi mới lọc hoặc tổng hợp ở bước sau. Điều đó làm bảng tạm lớn, tăng I/O và áp lực bộ nhớ.

Trước khi materialize, hãy:

- Áp dụng các điều kiện lọc hợp lệ càng sớm càng tốt.
- Chỉ chọn cột cần dùng ở các bước tiếp theo.
- Tổng hợp về đúng grain nếu không cần chi tiết từng hàng.
- Loại bỏ cột payload lớn, JSON hoặc văn bản dài không cần thiết.
- Chuẩn hóa kiểu dữ liệu để tránh chuyển đổi lặp.
- Xác định có cần giữ khóa duy nhất để nối lại hay không.

Ví dụ, nếu các bước sau chỉ cần customer_id và tổng tiền, không cần lưu mọi cột đơn hàng:

~~~sql
CREATE TEMPORARY TABLE customer_totals AS
SELECT customer_id, SUM(total) AS amount_total
FROM orders
WHERE status = 'COMPLETED'
  AND created_at >= :start_time
  AND created_at < :end_time
GROUP BY customer_id;
~~~

Kết quả này có một hàng cho mỗi customer_id nếu nhóm theo khóa đó. Nó nhỏ hơn nhiều so với việc lưu từng đơn hàng và có thể được tái sử dụng cho nhiều phép kiểm tra hoặc báo cáo tổng hợp.

Không tổng hợp sớm nếu các bước sau cần chi tiết từng đơn hàng hoặc cần áp dụng điều kiện làm thay đổi grain. Hãy xác định rõ ý nghĩa của mỗi hàng trước khi lưu.

## 8. Chỉ mục trên bảng tạm

Một bảng tạm có thể cần chỉ mục nếu nhiều bước sau tìm kiếm hoặc nối theo một khóa. Ví dụ, selected_orders được dùng để nối với order_items theo order_id:

~~~sql
CREATE INDEX idx_selected_orders_order_id
ON selected_orders (order_id);
~~~

Chỉ mục có thể hữu ích khi:

- Bảng tạm đủ lớn.
- Nhiều câu lệnh tìm theo cùng một khóa.
- Phép nối lặp lại nhiều lần.
- Điều kiện lọc có tính chọn lọc.
- Chi phí tạo chỉ mục nhỏ hơn tổng lợi ích từ các lần đọc sau.

Chỉ mục có thể không đáng tạo khi bảng tạm rất nhỏ, chỉ đọc tuần tự một lần hoặc quá trình tạo index tốn gần bằng việc quét toàn bảng. Nếu bảng được nạp rồi mới đọc một lần, quét tuần tự có thể tốt hơn.

Đừng tạo chỉ mục cho mọi cột. Chọn theo mẫu truy vấn tiếp theo, thứ tự khóa và số hàng thực tế. Nếu bảng tạm được thay đổi sau khi tạo chỉ mục, chi phí duy trì index cũng phải được tính vào tổng chi phí.

## 9. Thống kê trên kết quả trung gian

Bộ tối ưu cần biết số hàng và phân bố dữ liệu của bảng tạm để chọn kế hoạch nối và truy cập. Với một số hệ quản trị, thống kê tự động được thu thập hoặc cập nhật; với nền tảng khác, có thể cần lệnh thống kê riêng.

Nếu bảng tạm được nạp từ dữ liệu có phân bố lệch, optimizer có thể ước lượng sai số hàng khi nối với bảng lớn. Điều này có thể dẫn đến nested loop quá nhiều lần, hash table quá lớn hoặc lựa chọn thứ tự nối kém.

Ví dụ với PostgreSQL:

~~~sql
ANALYZE selected_orders;
~~~

Lệnh này thu thập thống kê cho bảng tạm trong phiên hiện tại. Với hệ quản trị khác, dùng cơ chế tương ứng theo tài liệu. Không giả định lệnh ANALYZE hoặc hành vi tự cập nhật giống nhau trên mọi nền tảng.

Hãy kiểm tra kế hoạch sau khi nạp dữ liệu. Nếu số hàng ước lượng khác xa số hàng thực tế, xem xét cập nhật thống kê hoặc điều chỉnh cách tạo tập trung gian. Đừng thêm lệnh thu thập thống kê sau mọi bảng tạm nhỏ nếu chi phí của nó lớn hơn lợi ích.

## 10. Bảng tạm và ranh giới tối ưu hóa

Bảng tạm tạo ra một ranh giới giữa các câu lệnh. Điều này có thể có lợi khi muốn cố định tập kết quả, kiểm tra số hàng hoặc cung cấp thống kê riêng cho giai đoạn sau. Nhưng nó cũng có thể làm optimizer mất khả năng tối ưu xuyên suốt toàn bộ truy vấn.

Ví dụ, truy vấn liền mạch có thể đẩy điều kiện từ bước cuối xuống bảng nguồn. Nếu ghi toàn bộ kết quả vào bảng tạm trước, bước sau không thể đẩy điều kiện ngược qua ranh giới đó. Khi chỉ cần một phần nhỏ kết quả cuối, việc materialize toàn bộ tập có thể tạo công việc thừa.

Bảng tạm có thể có lợi khi:

- Phép tính nguồn rất đắt và được dùng nhiều lần.
- Kết quả có thể giảm mạnh kích thước.
- Cần thống kê hoặc chỉ mục riêng cho giai đoạn tiếp theo.
- Cần tách pipeline để kiểm tra hoặc khôi phục từng bước.
- Cần bảo đảm các bước dùng cùng một tập khóa trong phạm vi giao dịch phù hợp.

Bảng tạm có thể bất lợi khi:

- Một câu truy vấn duy nhất có thể được optimizer tối ưu toàn cục.
- Điều kiện phía sau có thể lọc sớm nhưng bị ngăn bởi bước materialize.
- Kết quả trung gian lớn hơn nhiều so với phần cần dùng.
- Chi phí ghi/đọc tạm và tạo index vượt chi phí tính lại.

Hãy so sánh kế hoạch của truy vấn liền mạch với quy trình có bảng tạm. Đo toàn bộ quy trình, không chỉ câu lệnh cuối.

## 11. Vòng đời và phạm vi của bảng tạm

Bảng tạm có thể tồn tại theo phiên kết nối, theo transaction hoặc theo cơ chế riêng của hệ quản trị. Một số nền tảng tự xóa khi phiên kết thúc; một số cho phép cấu hình xóa hàng hoặc giữ hàng sau commit; một số dùng tên và namespace riêng cho từng session.

Cần biết rõ:

- Bảng tồn tại đến khi nào?
- Dữ liệu có bị xóa khi COMMIT không?
- Bảng có được nhìn thấy từ phiên khác không?
- Bảng có được tái sử dụng qua các transaction trong cùng session không?
- Khi kết nối trả về connection pool, bảng tạm còn tồn tại không?
- Có nguy cơ tên bảng hoặc dữ liệu cũ bị dùng lại bởi request sau không?
- Việc rollback ảnh hưởng thế nào đến đối tượng và dữ liệu tạm?

Đặc biệt, ứng dụng dùng connection pool phải chú ý phạm vi phiên. Hai lần gọi repository có thể nhận hai kết nối vật lý khác nhau. Nếu bảng tạm chỉ tồn tại trong một session, bước tạo và bước dùng phải chạy trên cùng connection. Nếu trả connection về pool giữa hai bước, lần sau có thể nhận một session khác và không thấy bảng; hoặc session cũ được tái sử dụng với dữ liệu tạm còn tồn tại ngoài dự kiến.

Hãy quản lý connection, transaction và cleanup rõ ràng. Không dựa vào giả định rằng mọi câu lệnh trong một request luôn dùng cùng một kết nối nếu framework không bảo đảm điều đó.

## 12. Giao dịch, tính nhất quán và dữ liệu thay đổi

Một kết quả trung gian được lưu lại phản ánh dữ liệu tại thời điểm tạo, theo snapshot và isolation level của hệ quản trị. Nếu bảng nguồn thay đổi giữa lúc tạo bảng tạm và lúc dùng kết quả, các câu lệnh sau có thể nhìn thấy một trạng thái dữ liệu khác với trạng thái đã dùng để tạo tập trung gian.

Ví dụ, quy trình tạo selected_orders lúc 10:00 rồi đến 10:05 cập nhật orders và payments. Nếu báo cáo dùng bảng tạm đã tạo trước đó, kết quả có thể không phản ánh thay đổi mới. Đây có thể là hành vi đúng nếu nghiệp vụ cần một snapshot cố định; cũng có thể là lỗi nếu báo cáo phải phản ánh dữ liệu mới nhất.

Cần xác định:

- Các bước có cần cùng một snapshot logic không?
- Transaction isolation level là gì?
- Bảng tạm chứa khóa hay chứa cả giá trị đã tính?
- Nếu bảng nguồn thay đổi, có cần tạo lại kết quả không?
- Có thể chấp nhận độ trễ hoặc dữ liệu cũ đến mức nào?
- Quy trình có cần khóa hoặc kiểm soát đồng thời không?

Bảng tạm không tự đảm bảo tính nhất quán giữa nhiều câu lệnh. Hãy chọn ranh giới transaction và isolation level theo yêu cầu nghiệp vụ, đồng thời đo tác động của việc giữ transaction lâu.

## 13. Bảng tạm có thể làm tăng áp lực I/O và temp storage

Dữ liệu tạm có thể nằm trong bộ nhớ hoặc được ghi ra vùng lưu trữ tạm khi vượt giới hạn. Hệ quản trị cũng có thể dùng temp storage cho sort, hash, spool và các thao tác nội bộ khác. Nhiều truy vấn đồng thời tạo bảng tạm lớn có thể làm tăng I/O và cạnh tranh tài nguyên.

Các dấu hiệu cần theo dõi:

- Thời gian tạo và nạp bảng tạm.
- Số hàng và kích thước dữ liệu tạm.
- Số trang đọc/ghi vào temp storage.
- Sort hoặc hash spill.
- CPU và bộ nhớ dùng cho thao tác trung gian.
- Tình trạng đầy vùng lưu trữ tạm.
- Số phiên đồng thời tạo hoặc dùng bảng tạm.
- Thời gian chờ I/O và ảnh hưởng đến truy vấn khác.

Một bảng tạm nhỏ có thể giảm nhiều lần đọc bảng nguồn. Một bảng tạm lớn có thể làm tăng gấp đôi công việc vì hệ quản trị phải đọc nguồn, ghi kết quả tạm rồi đọc lại. Nếu dữ liệu được dùng nhiều lần, chi phí này có thể được bù lại; nếu chỉ dùng một lần, có thể không.

Đừng chỉ theo dõi thời gian CPU của câu lệnh. Cần xem cả I/O tạm, memory grant, spill và tải đồng thời.

## 14. Các lựa chọn thay thế bảng tạm

Trước khi tạo bảng tạm, hãy xem có lựa chọn đơn giản hơn phù hợp không:

| Lựa chọn | Ưu điểm | Giới hạn cần cân nhắc |
|---|---|---|
| CTE | Cấu trúc truy vấn rõ ràng, ít quản lý vòng đời | Không bảo đảm materialize hoặc chỉ tính một lần |
| Derived table | Gọn trong một câu SQL | Khó tái sử dụng qua nhiều câu lệnh |
| CTE/materialized subquery theo cú pháp hệ quản trị | Có thể lưu kết quả trong một kế hoạch | Tác động đến predicate pushdown và chi phí tạm |
| Temporary table | Tái sử dụng qua nhiều câu lệnh, có thể thêm index | Cần quản lý session, cleanup, I/O và thống kê |
| Materialized view | Tái sử dụng lâu dài qua nhiều phiên | Cần làm mới và kiểm soát độ mới dữ liệu |
| Staging table | Phù hợp batch/ETL nhiều giai đoạn | Cần quản lý dữ liệu, khóa batch và dọn dẹp |
| Cache ở ứng dụng | Có thể tránh truy vấn lặp giữa các request | Cần xử lý invalidation, tính nhất quán và giới hạn bộ nhớ |

Nếu kết quả được dùng qua nhiều request hoặc nhiều phiên, materialized view hoặc cache có thể phù hợp hơn bảng tạm. Nếu dữ liệu cần được làm mới theo batch và có thể kiểm soát trạng thái, staging table có thể rõ ràng hơn. Nếu chỉ dùng trong một câu SQL, CTE hoặc derived table có thể đủ.

## 15. Ví dụ: tái sử dụng tập đơn hàng cho nhiều bước báo cáo

Giả sử một batch cần tạo ba kết quả từ cùng tập đơn hàng đã hoàn tất trong một khoảng thời gian:

- Tổng tiền theo khách hàng.
- Danh sách đơn hàng có giá trị cao.
- Số đơn theo trạng thái giao hàng.

Nếu cả ba câu lệnh đều lọc orders và nối customers theo cùng điều kiện, hệ thống có thể lặp lại một phần công việc. Một bảng tạm được lọc và thu gọn đúng cách có thể giúp tái sử dụng.

Ví dụ theo cú pháp PostgreSQL:

~~~sql
CREATE TEMP TABLE selected_orders
ON COMMIT DROP
AS
SELECT
    order_id,
    customer_id,
    status,
    total,
    created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :start_time
  AND created_at < :end_time
  AND status IN ('COMPLETED', 'SHIPPED');
~~~

Tạo chỉ mục nếu các bước sau tìm theo customer_id hoặc order_id và kích thước tập kết quả đủ lớn:

~~~sql
CREATE INDEX idx_selected_orders_customer
ON selected_orders (customer_id);
~~~

Thu thập thống kê khi cần:

~~~sql
ANALYZE selected_orders;
~~~

Bước tổng tiền theo khách hàng:

~~~sql
SELECT customer_id, SUM(total) AS total_amount
FROM selected_orders
GROUP BY customer_id;
~~~

Bước tìm đơn hàng giá trị cao:

~~~sql
SELECT order_id, customer_id, total
FROM selected_orders
WHERE total >= :high_value_threshold
ORDER BY total DESC;
~~~

Bước đếm theo trạng thái:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM selected_orders
GROUP BY status;
~~~

Với tùy chọn **ON COMMIT DROP**, bảng tạm được xóa khi transaction commit trong PostgreSQL. Cần bảo đảm cả bốn bước chạy trong cùng transaction và cùng connection. Nếu framework tự commit sau câu lệnh tạo bảng, bảng có thể bị xóa trước khi các câu lệnh sau dùng đến.

Cách làm này đáng thử khi truy vấn nguồn đủ tốn kém và ba bước sau cần cùng tập dữ liệu. Nếu tập selected_orders rất lớn, hãy đo chi phí tạo, index, analyze và đọc lại. Nếu chỉ có một báo cáo dùng tập dữ liệu đó, truy vấn liền mạch có thể hiệu quả hơn.

## 16. Quy trình đánh giá bảng tạm

Một quy trình có thể áp dụng:

1. **Nhận diện công việc lặp:** tìm các query fingerprint hoặc các bước batch lặp cùng phép lọc, nối và tổng hợp.
2. **Đo baseline:** ghi thời gian, số lần đọc, CPU, I/O, cardinality và phân vị của toàn quy trình.
3. **Xác định kết quả cần tái sử dụng:** mô tả grain, số hàng, cột cần giữ và thời điểm dữ liệu.
4. **Tính mức thu gọn:** so sánh kích thước dữ liệu nguồn với kết quả trung gian dự kiến.
5. **Chọn cơ chế:** CTE, materialization, bảng tạm, materialized view hay staging table.
6. **Tạo kết quả gọn:** lọc sớm, bỏ cột thừa và tổng hợp đúng grain.
7. **Đánh giá chỉ mục và thống kê:** chỉ tạo index hoặc cập nhật statistics nếu kế hoạch sau đó cần.
8. **Quản lý vòng đời:** xác định session, connection, transaction, cleanup và hành vi connection pool.
9. **Kiểm tra tính nhất quán:** xác định snapshot, isolation level và thay đổi dữ liệu giữa các bước.
10. **Đo chi phí toàn bộ:** tính cả tạo, ghi, index, analyze, đọc lại và dọn dẹp.
11. **So sánh kế hoạch:** xem số hàng ước lượng/thực tế, join order, scan, spill và I/O.
12. **Thử dưới tải đồng thời:** kiểm tra temp storage, bộ nhớ và ảnh hưởng đến workload khác.
13. **Xác nhận kết quả:** so sánh số hàng, tổng hợp và khóa nghiệp vụ với cách thực hiện ban đầu.
14. **Ghi lại quyết định:** lưu lý do, số liệu, phạm vi và giới hạn của phương án.

Không quyết định dựa trên một câu lệnh cuối cùng. Nếu quy trình có ba câu lệnh sau khi tạo bảng tạm, phải đo tổng thời gian từ lúc bắt đầu tạo đến khi hoàn tất câu lệnh cuối và cleanup.

## 17. Đo và đọc kế hoạch trước/sau

Khi so sánh, hãy giữ dữ liệu, tham số, mức đồng thời và trạng thái cache càng tương đồng càng tốt. Theo dõi ít nhất:

| Chỉ số | Truy vấn tính lại | Quy trình dùng bảng tạm |
|---|---|---|
| Tổng elapsed time | Bao gồm mọi lần tính lại | Bao gồm tạo, nạp, đọc và cleanup |
| Logical/physical reads | Đọc bảng nguồn lặp lại | Đọc nguồn và dữ liệu tạm |
| CPU | Tính lại biểu thức và phép nối | Tính một lần, cộng chi phí ghi/đọc |
| Temp I/O | Spill nội bộ nếu có | Ghi/đọc bảng tạm và spill |
| Bộ nhớ | Hash/sort trong từng kế hoạch | Buffer, index và các toán tử sau |
| Số hàng trung gian | Theo từng câu lệnh | Kích thước bảng tạm và các bước dùng |
| Độ trễ đuôi | p95/p99 từng request hoặc batch | p95/p99 toàn quy trình |

Đọc EXPLAIN hoặc công cụ tương đương cho từng câu lệnh. Kiểm tra optimizer có quét bảng tạm tuần tự hay dùng chỉ mục, estimated rows có gần actual rows và có phát sinh sort/hash spill không.

Một bảng tạm có thể giúp kế hoạch sau tốt hơn vì optimizer có thống kê trực tiếp trên tập đã lọc. Nhưng nếu tập kết quả thay đổi liên tục, thống kê có thể không còn đại diện hoặc chi phí thu thập lại quá cao. Hãy đánh giá theo chu kỳ sử dụng thực tế.

## 18. Các sai lầm thường gặp

- **Tạo bảng tạm cho mọi CTE.** CTE có thể được inline và tối ưu tốt trong một kế hoạch duy nhất.
- **Cho rằng CTE luôn chỉ chạy một lần.** Hành vi phụ thuộc hệ quản trị, phiên bản và cách tham chiếu.
- **Materialize toàn bộ bảng nguồn.** Lưu quá nhiều hàng và cột làm tăng I/O không cần thiết.
- **Không tính chi phí tạo và dọn dẹp.** Đo riêng câu lệnh cuối khiến kết quả có vẻ nhanh giả tạo.
- **Tạo index trên mọi cột tạm.** Index có chi phí tạo và duy trì, chỉ hữu ích khi bước sau thực sự dùng.
- **Không cập nhật thống kê khi cần.** Optimizer có thể ước lượng sai cardinality của tập trung gian.
- **Dùng bảng tạm qua nhiều connection.** Bảng có thể chỉ tồn tại trong session đã tạo.
- **Không kiểm soát transaction và connection pool.** COMMIT hoặc trả connection có thể làm bảng bị xóa hoặc để lại trạng thái ngoài dự kiến.
- **Bỏ qua snapshot dữ liệu.** Bảng tạm có thể phản ánh dữ liệu cũ trong khi bảng nguồn đã thay đổi.
- **Tạo quá nhiều bảng tạm đồng thời.** Temp storage và I/O có thể trở thành nút thắt mới.
- **Cắt rời truy vấn quá sớm.** Ranh giới materialization có thể ngăn optimizer đẩy điều kiện xuống nguồn.
- **Chỉ đo một lần hoặc một tham số.** Cache, phân bố dữ liệu và tải đồng thời làm kết quả thay đổi.

## 19. Checklist quyết định có nên lưu kết quả trung gian

- [ ] Đã xác định cùng phép tính hoặc tập dữ liệu đang bị thực hiện lặp.
- [ ] Đã đo chi phí tính lại và số lần sử dụng kết quả.
- [ ] Đã xác định grain, số hàng và các cột cần giữ.
- [ ] Đã đánh giá mức thu gọn so với dữ liệu nguồn.
- [ ] Đã so sánh CTE, derived table và materialization trước khi tạo bảng tạm.
- [ ] Đã tính chi phí tạo, ghi, đọc, index, statistics và cleanup.
- [ ] Đã kiểm tra khả năng predicate pushdown và tối ưu toàn cục.
- [ ] Đã xác định phạm vi session, connection, transaction và connection pool.
- [ ] Đã kiểm tra snapshot và isolation level giữa các bước.
- [ ] Đã tạo index và cập nhật statistics chỉ khi kế hoạch cần.
- [ ] Đã đo temp I/O, spill, CPU, memory và tải đồng thời.
- [ ] Đã so sánh toàn bộ quy trình trước/sau.
- [ ] Đã xác nhận kết quả và các phép tổng hợp không thay đổi.
- [ ] Đã có cách cleanup và xử lý lỗi giữa chừng.

## 20. Nguyên tắc cần ghi nhớ

Bảng tạm và kết quả trung gian có giá trị khi chúng tránh được công việc lặp đủ lớn để bù chi phí tạo, ghi, đọc, lập chỉ mục và quản lý vòng đời. Hãy xác định chính xác tập dữ liệu được dùng lại, giảm kích thước trước khi lưu và giữ đúng grain để các bước sau không làm thay đổi ngữ nghĩa.

Bắt đầu bằng việc xem CTE hoặc truy vấn liền mạch có đủ hay không. Chỉ materialize khi có lý do đo được như tái sử dụng qua nhiều câu lệnh, cần thống kê riêng hoặc cần cố định một tập khóa. Quản lý session, connection, transaction và snapshot cẩn thận; đo toàn bộ quy trình dưới tải đại diện và so sánh cả CPU, I/O, temp storage, độ trễ lẫn tính đúng đắn.
