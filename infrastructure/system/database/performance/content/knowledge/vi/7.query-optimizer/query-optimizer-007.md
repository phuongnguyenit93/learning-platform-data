# Tham số nhạy cảm, parameter sniffing và kế hoạch dùng chung theo hệ quản trị

Một câu SQL có thể được thực thi với nhiều giá trị tham số khác nhau. Dù cấu trúc truy vấn không đổi, lượng hàng phù hợp với mỗi giá trị có thể chênh lệch rất lớn. Ví dụ, truy vấn tìm đơn hàng theo trạng thái có thể trả về hàng triệu dòng với trạng thái phổ biến nhưng chỉ vài chục dòng với trạng thái hiếm. Bộ tối ưu truy vấn cần chọn cách truy cập dữ liệu phù hợp với phân bố đó.

Để giảm chi phí biên dịch và tận dụng bộ nhớ, nhiều hệ quản trị có cơ chế lưu hoặc tái sử dụng kế hoạch thực thi. Khi một kế hoạch được tạo dựa trên một giá trị tham số rồi dùng lại cho giá trị khác, kế hoạch có thể không còn phù hợp. Hiện tượng hiệu năng thay đổi mạnh theo giá trị tham số thường được gọi là **parameter sensitivity**; trong SQL Server, quá trình tối ưu dựa trên giá trị tham số tại thời điểm biên dịch thường được gọi là **parameter sniffing**.

Trong module **DATABASE_PERFORMANCE**, hiểu đúng cơ chế này giúp phân tích vì sao cùng một câu SQL có lúc rất nhanh, có lúc rất chậm; vì sao thống kê và độ lệch dữ liệu ảnh hưởng đến kế hoạch; và vì sao cách xử lý phải phù hợp với từng hệ quản trị. Mục tiêu không phải tắt tái sử dụng kế hoạch một cách mặc định, mà là chọn chiến lược cân bằng giữa chi phí biên dịch, chất lượng kế hoạch và độ ổn định dưới tải thực tế.

## 1. Tham số nhạy cảm và phân bố dữ liệu lệch

Một truy vấn được gọi là nhạy cảm với tham số khi hiệu quả của kế hoạch thực thi phụ thuộc đáng kể vào giá trị tham số đầu vào. Điều này thường xảy ra khi dữ liệu có phân bố không đồng đều (*data skew*), số hàng phù hợp với các giá trị khác nhau chênh lệch lớn, hoặc quan hệ giữa nhiều cột không độc lập.

Giả sử bảng `orders` có 20 triệu dòng và cột `status` có phân bố như sau:

| Giá trị `status` | Số dòng ước lượng | Tỷ lệ |
|---|---:|---:|
| `COMPLETED` | 15.000.000 | 75% |
| `PENDING` | 4.500.000 | 22,5% |
| `CANCELLED` | 450.000 | 2,25% |
| `REVIEW` | 50.000 | 0,25% |

Truy vấn dưới đây có cùng hình dạng nhưng số hàng trả về rất khác nhau:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE status = ?;
```

Với `status = 'REVIEW'`, index seek trên chỉ mục phù hợp có thể đọc một lượng nhỏ trang dữ liệu. Với `status = 'COMPLETED'`, việc đọc phần lớn bảng qua chỉ mục rồi truy cập lại bảng để lấy nhiều cột có thể tốn kém hơn quét bảng hoặc quét chỉ mục phủ. Một kế hoạch duy nhất không chắc tối ưu cho cả hai trường hợp.

Các dấu hiệu thường gặp của tham số nhạy cảm gồm:

- Cùng câu SQL có thời gian thực thi rất khác nhau theo giá trị tham số.
- Kế hoạch dùng chung có ước lượng số hàng lệch đáng kể so với số hàng thực tế ở một số giá trị.
- Một giá trị chạy nhanh sau khi biên dịch lại, nhưng chậm khi kế hoạch đã được tạo bởi giá trị khác.
- Kế hoạch luân phiên giữa seek, scan, nested loop, hash join hoặc cách truy cập khác khi cache bị làm mới.
- Một nhóm truy vấn trong thống kê có thời gian trung bình hoặc độ biến động cao, dù mẫu SQL giống nhau.

Không phải mọi chênh lệch thời gian đều do parameter sniffing. Khóa bị tranh chấp, cache lạnh, I/O, thay đổi tải, chờ lấy kết nối, kế hoạch khác nhau do môi trường hoặc dữ liệu thay đổi cũng có thể tạo ra biểu hiện tương tự. Cần đối chiếu kế hoạch và số liệu thực tế trước khi kết luận.

## 2. Parameter sniffing và vòng đời kế hoạch thực thi

Trong các hệ quản trị có cơ chế tối ưu dựa trên giá trị tham số lúc biên dịch, quá trình khái quát diễn ra như sau:

1. Ứng dụng gửi câu lệnh hoặc thủ tục cùng tham số.
2. Hệ quản trị phân tích câu lệnh, kiểm tra metadata và thống kê cần thiết.
3. Nếu chưa có kế hoạch phù hợp trong cache, bộ tối ưu ước lượng số hàng và chi phí dựa trên thông tin có sẵn, có thể bao gồm giá trị tham số hiện tại.
4. Hệ quản trị tạo kế hoạch và có thể lưu kế hoạch vào cache.
5. Những lần thực thi sau có thể dùng lại kế hoạch nếu chúng khớp các điều kiện nhận diện và tái sử dụng của hệ quản trị.

**Parameter sniffing tự nó không phải lỗi.** Việc xem xét giá trị tham số lúc biên dịch thường giúp bộ tối ưu chọn kế hoạch tốt hơn. Vấn đề xuất hiện khi một kế hoạch được tối ưu cho một nhóm giá trị nhưng tái sử dụng cho nhóm có đặc tính dữ liệu khác xa.

### Ví dụ với stored procedure trong SQL Server

Giả sử ứng dụng gọi thủ tục sau:

```sql
CREATE OR ALTER PROCEDURE dbo.GetOrdersByStatus
    @Status varchar(20)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT order_id, customer_id, created_at, total_amount
    FROM dbo.Orders
    WHERE status = @Status;
END;
```

Nếu lần đầu thủ tục được biên dịch với `@Status = 'REVIEW'`, bộ tối ưu có thể ước lượng số dòng nhỏ và chọn index seek cùng nested loop hoặc lookup. Khi thủ tục được gọi tiếp với `@Status = 'COMPLETED'`, kế hoạch đã lưu có thể tiếp tục được dùng dù số dòng thực tế lớn hơn rất nhiều. Truy cập nhiều dòng qua nhiều lần lookup có thể đắt hơn scan.

Nếu lần biên dịch đầu tiên dùng `COMPLETED`, kế hoạch scan có thể phù hợp với giá trị phổ biến nhưng kém hiệu quả khi `REVIEW` chỉ cần một số dòng nhỏ. Thứ tự gọi có thể làm thay đổi kế hoạch được lưu sau khi cache trống hoặc thủ tục cần biên dịch lại. Đây là lý do cùng một truy vấn có thể có biểu hiện khác nhau giữa các môi trường hoặc sau khi triển khai.

### Kế hoạch được dùng chung khi nào?

Không phải mọi câu SQL giống văn bản đều dùng chung một kế hoạch. Việc nhận diện phụ thuộc vào hệ quản trị, dạng câu lệnh, cách tham số hóa, schema, metadata, ngữ cảnh phiên, quyền và các tùy chọn liên quan. Trong SQL Server, chẳng hạn, một số thiết lập `SET`, cơ sở dữ liệu hoặc thay đổi schema có thể ảnh hưởng đến việc tìm và tái sử dụng kế hoạch. Câu SQL ghép literal riêng cho từng giá trị cũng có thể tạo nhiều bản kế hoạch, làm tăng áp lực lên plan cache.

Khi điều tra, hãy xác minh kế hoạch thực sự được tái sử dụng, các tham số lúc biên dịch và lúc thực thi, cùng lý do biên dịch lại nếu có. Đừng suy luận chỉ từ việc hai câu SQL nhìn giống nhau.

## 3. Vì sao bộ tối ưu có thể chọn kế hoạch không phù hợp?

Bộ tối ưu không thử mọi kế hoạch trên toàn bộ dữ liệu mỗi lần chạy. Nó ước lượng số hàng và chi phí dựa trên thống kê, metadata, mô hình cardinality và các giả định của hệ quản trị. Một số yếu tố làm ước lượng khó chính xác:

### Phân bố dữ liệu lệch

Nếu một giá trị xuất hiện rất thường xuyên còn nhiều giá trị khác hiếm, một ước lượng trung bình có thể không đại diện cho cả hai nhóm. Histogram trong thống kê có thể mô tả một phần phân bố, nhưng độ chi tiết bị giới hạn bởi cách hệ quản trị xây dựng thống kê.

### Tương quan giữa nhiều cột

Giả sử truy vấn lọc theo `tenant_id` và `status`. Một tenant có thể có 95% đơn hàng `COMPLETED`, trong khi tenant khác có 5%. Nếu bộ tối ưu giả định hai cột độc lập, ước lượng cho điều kiện kết hợp có thể sai. Thống kê nhiều cột hoặc thống kê mở rộng có thể giúp trong một số hệ quản trị, nhưng khả năng và cách sử dụng khác nhau.

### Thống kê cũ hoặc thiếu thông tin

Khi dữ liệu tăng nhanh, phân bố thay đổi hoặc một giá trị mới trở nên phổ biến, thống kê cũ có thể không phản ánh trạng thái hiện tại. Thống kê không đầy đủ cũng làm bộ tối ưu khó nhận biết giá trị hiếm và phổ biến. Cần kiểm tra thời điểm cập nhật, số dòng được lấy mẫu và cột dẫn đầu của histogram theo khả năng của hệ quản trị.

### Chuyển kiểu và biểu thức trên cột

Ép kiểu không phù hợp hoặc bọc cột trong hàm có thể làm giảm khả năng sử dụng chỉ mục và khiến ước lượng khó chính xác. Hãy kiểm tra kiểu tham số so với kiểu cột, collation, implicit conversion và biểu thức trong điều kiện lọc.

### Giới hạn của chỉ mục

Một chỉ mục phù hợp với giá trị chọn lọc cao có thể trở nên đắt khi giá trị trả về nhiều hàng. Chỉ mục không phủ đủ cột còn có thể gây nhiều lần lookup. Bộ tối ưu phải cân bằng chi phí đọc chỉ mục, truy cập bảng, số trang và bộ nhớ; thay đổi tham số có thể làm điểm cân bằng thay đổi.

## 4. Phân biệt vấn đề tham số nhạy cảm với các nguyên nhân khác

Trước khi điều chỉnh, cần chứng minh rằng chênh lệch hiệu năng liên quan đến giá trị tham số và kế hoạch được chọn.

| Quan sát | Câu hỏi kiểm chứng |
|---|---|
| Cùng mẫu SQL, thời gian khác nhau | Có phải dữ liệu trả về khác số lượng? Tải, cache và I/O có tương đương không? |
| Kế hoạch thay đổi sau khi cache bị làm mới | Tham số lúc biên dịch là gì? Kế hoạch nào được tạo trước? |
| Estimated rows khác actual rows | Thống kê có đủ mới và có mô tả được độ lệch hoặc tương quan không? |
| Chạy lại một giá trị nhanh hơn | Có phải kế hoạch mới phù hợp hơn, hay cache dữ liệu đã nóng lên? |
| Nhiều kế hoạch cho cùng mẫu | Hệ quản trị có tạo nhiều child plan hoặc custom plan có chủ đích không? |
| Chậm khi tải cao | Có chờ khóa, I/O, CPU, memory grant hoặc connection pool không? |

Một phép kiểm tra hữu ích là chạy các giá trị đại diện trong cùng điều kiện, thu thập actual execution plan, số hàng ước lượng/thực tế, logical reads, CPU, elapsed time và các wait liên quan. Nếu hệ thống có Query Store hoặc lịch sử kế hoạch, hãy so sánh kế hoạch theo thời điểm và nhóm tham số.

Không nên xóa toàn bộ plan cache trên production chỉ để thử giả thuyết. Việc đó có thể gây biên dịch đồng loạt, tăng CPU và làm nhiều truy vấn khác chậm tạm thời. Hãy dùng môi trường kiểm thử, thao tác có phạm vi hoặc cơ chế theo dõi kế hoạch được hệ quản trị hỗ trợ.

## 5. Cơ chế theo hệ quản trị

Thuật ngữ và hành vi của từng hệ quản trị khác nhau. Không nên lấy một giải pháp của SQL Server áp dụng nguyên xi cho PostgreSQL, Oracle hoặc MySQL.

### SQL Server: parameter sniffing và plan cache

SQL Server thường sử dụng giá trị tham số lúc biên dịch để ước lượng cardinality. Với stored procedure hoặc câu lệnh tham số hóa, kế hoạch có thể được lưu và dùng lại. Điều này giảm chi phí biên dịch, nhưng kế hoạch được tối ưu cho một giá trị có thể không phù hợp với giá trị khác.

Các lựa chọn xử lý gồm:

- **Cập nhật thống kê và cải thiện chỉ mục:** xử lý nguyên nhân ước lượng sai hoặc đường truy cập không phù hợp trước khi ép kế hoạch.
- **`OPTION (RECOMPILE)`:** biên dịch lại câu lệnh ở mỗi lần thực thi để tối ưu theo tham số hiện tại. Có thể hữu ích với truy vấn ít chạy nhưng rất nhạy cảm; đổi lại là tăng CPU và chi phí biên dịch.
- **`OPTIMIZE FOR`:** hướng bộ tối ưu đến một giá trị tham số cụ thể hoặc một chiến lược ước lượng tổng quát như `OPTIMIZE FOR UNKNOWN`. Giá trị được chọn phải đại diện cho mục tiêu tải; kế hoạch có thể vẫn kém với nhóm khác.
- **Tách nhánh truy vấn:** dùng các nhánh riêng cho nhóm giá trị có đặc tính khác nhau, nếu số nhóm nhỏ, ổn định và có thể kiểm thử.
- **Parameter Sensitive Plan optimization:** ở các phiên bản và mức compatibility hỗ trợ, SQL Server có thể duy trì nhiều biến thể kế hoạch cho các khoảng độ chọn lọc thay vì chỉ một kế hoạch dùng chung. Cần kiểm tra điều kiện hỗ trợ và hành vi thực tế trong phiên bản đang chạy.
- **Query Store:** dùng để theo dõi lịch sử kế hoạch và hiệu năng, xác định thời điểm hồi quy và đánh giá tác động của điều chỉnh. Plan forcing hoặc Query Store hints cần được kiểm soát và theo dõi vì có thể khóa hệ thống vào lựa chọn không còn phù hợp.

Ví dụ `OPTION (RECOMPILE)` áp dụng cho một câu lệnh:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM dbo.Orders
WHERE status = @Status
OPTION (RECOMPILE);
```

Chỉ nên dùng sau khi đo được chi phí biên dịch và lợi ích thực tế. Nếu câu lệnh chạy hàng nghìn lần mỗi giây, biên dịch mỗi lần có thể chuyển nút thắt sang CPU.

### PostgreSQL: custom plan và generic plan

PostgreSQL phân biệt **custom plan** và **generic plan** đối với prepared statement. Custom plan được lập dựa trên giá trị tham số của lần thực thi; generic plan không phụ thuộc một bộ giá trị cụ thể và có thể được dùng lại để giảm chi phí lập kế hoạch.

Với thiết lập mặc định `plan_cache_mode = auto`, PostgreSQL thường đánh giá một số lần thực thi custom plan đầu tiên rồi so sánh chi phí ước lượng với generic plan để quyết định có tiếp tục dùng kế hoạch tổng quát hay không. Chi tiết có thể thay đổi theo phiên bản, vì vậy cần kiểm tra tài liệu của phiên bản đang triển khai.

Ví dụ minh họa:

```sql
PREPARE orders_by_status(text) AS
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE status = $1;

EXPLAIN EXECUTE orders_by_status('REVIEW');
EXPLAIN EXECUTE orders_by_status('COMPLETED');
```

Có thể kiểm tra thử chiến lược bằng `plan_cache_mode` trong phiên hoặc transaction thử nghiệm:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE orders_by_status('REVIEW');

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE orders_by_status('REVIEW');
```

`force_custom_plan` giúp đánh giá chất lượng kế hoạch theo tham số nhưng có thể tăng chi phí lập kế hoạch. `force_generic_plan` giúp đánh giá lợi ích tái sử dụng nhưng có thể bỏ qua độ lệch dữ liệu. Không nên thay đổi thiết lập toàn hệ thống chỉ từ một truy vấn thử; hãy đo theo workload và phạm vi kết nối thực tế.

PostgreSQL còn có thể dùng thống kê mở rộng cho một số dạng tương quan giữa các cột. Nếu điều kiện lọc kết hợp có ước lượng sai, hãy kiểm tra `ANALYZE`, histogram và extended statistics trước khi kết luận vấn đề nằm ở generic plan.

### Oracle Database: bind peeking và adaptive cursor sharing

Oracle hỗ trợ bind variables để giảm phân tích lại câu lệnh và tăng khả năng chia sẻ cursor. Trong quá trình hard parse, cơ chế **bind variable peeking** có thể xem giá trị bind hiện tại để ước lượng cardinality và chọn kế hoạch. Nếu các giá trị bind có độ chọn lọc rất khác nhau, việc chia sẻ một cursor có thể gây hiệu năng không đồng đều.

**Adaptive Cursor Sharing** cho phép Oracle nhận biết một cursor có thể không phù hợp với mọi giá trị bind và, trong điều kiện thích hợp, tạo các child cursor cho những phạm vi độ chọn lọc khác nhau. Thống kê và histogram có vai trò quan trọng trong việc ước lượng phân bố. Cần xem cursor, child cursor, bind sensitivity/bind awareness và lịch sử thực thi bằng công cụ phù hợp với phiên bản.

Không nên bỏ bind variables hoặc ép literal cho mọi truy vấn để tránh bind peeking. Việc đó có thể làm tăng hard parse, tiêu thụ CPU và tạo nhiều cursor. Hãy ưu tiên kiểm tra thống kê, histogram, execution plan và hành vi cursor sharing; chỉ áp dụng hint hoặc thay đổi cấu hình khi có bằng chứng.

### MySQL: không đồng nhất prepared statement với cơ chế của SQL Server

MySQL hỗ trợ prepared statements và các dạng cache liên quan đến metadata hoặc truy vấn, nhưng không nên mặc định rằng nó có cùng mô hình parameter sniffing và chia sẻ kế hoạch như SQL Server. Hành vi tối ưu hóa phụ thuộc phiên bản, giao thức, loại câu lệnh và cách thực thi. Khi phân tích, hãy dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` phù hợp với phiên bản, kiểm tra kiểu tham số, thống kê, chỉ mục và số hàng thực tế. Không áp dụng `OPTION (RECOMPILE)`, `OPTIMIZE FOR` hay giả định generic/custom plan của PostgreSQL cho MySQL.

## 6. Cách chẩn đoán theo quy trình

Một quy trình có thể lặp lại giúp tránh điều chỉnh dựa trên cảm giác:

1. **Xác định mẫu truy vấn:** lấy query fingerprint hoặc mã truy vấn, bảng tham gia, điều kiện lọc và dạng tham số hóa.
2. **Chọn các giá trị đại diện:** gồm giá trị phổ biến, hiếm, biên, null nếu hợp lệ và các nhóm có phân bố khác nhau.
3. **Thu thập kế hoạch và tham số:** ghi nhận giá trị lúc biên dịch nếu hệ quản trị cung cấp, giá trị lúc thực thi, kế hoạch hiện tại và lịch sử kế hoạch.
4. **Đo thực thi:** thu thập actual rows, estimated rows, logical/physical reads, CPU, elapsed time, memory grant, wait và số lần lookup khi có.
5. **Kiểm tra thống kê:** thời điểm cập nhật, độ chi tiết histogram, cột thống kê, độ lệch dữ liệu và tương quan giữa các điều kiện.
6. **Kiểm tra plan reuse:** xác minh kế hoạch được tái sử dụng hay biên dịch lại, các điều kiện cache và số lượng biến thể kế hoạch.
7. **So sánh trong điều kiện tương đương:** cùng dữ liệu, tải, trạng thái cache, cấu hình và mức đồng thời.
8. **Đặt giả thuyết và thử một thay đổi:** cập nhật thống kê, sửa chỉ mục, tách nhánh hoặc thay đổi chiến lược kế hoạch có kiểm soát.
9. **Đo lại và theo dõi hồi quy:** so sánh toàn bộ nhóm giá trị và các truy vấn khác có thể bị ảnh hưởng.

### Chọn giá trị kiểm thử có đại diện

Không nên chỉ thử một giá trị trung bình. Với dữ liệu lệch, một bộ kiểm thử nên bao gồm:

| Nhóm | Mục đích |
|---|---|
| Giá trị rất phổ biến | Kiểm tra kế hoạch khi phải xử lý nhiều hàng |
| Giá trị rất hiếm | Kiểm tra khả năng khai thác index seek hoặc đường truy cập chọn lọc |
| Giá trị trung bình | Đánh giá hiệu năng của nhóm chiếm phần lớn workload |
| Giá trị mới hoặc vừa tăng nhanh | Phát hiện thống kê chưa theo kịp phân bố |
| Giá trị có tương quan với cột khác | Kiểm tra sai lệch ước lượng của điều kiện kết hợp |
| `NULL` hoặc giá trị biên | Kiểm tra ngữ nghĩa và nhánh kế hoạch nếu nghiệp vụ cho phép |

Hãy chọn giá trị theo tần suất và tác động thực tế, đồng thời bảo đảm dữ liệu kiểm thử không làm lộ thông tin người dùng.

## 7. Chiến lược xử lý và đánh đổi

Không có một cách khắc phục phù hợp cho mọi truy vấn. Bảng sau giúp chọn hướng thử nghiệm:

| Chiến lược | Khi cân nhắc | Chi phí hoặc rủi ro |
|---|---|---|
| Cập nhật hoặc bổ sung thống kê | Ước lượng sai do thống kê cũ, thiếu hoặc không mô tả phân bố | Tốn tài nguyên thu thập; thống kê vẫn có giới hạn và có thể cần lịch cập nhật |
| Thiết kế lại chỉ mục | Một nhóm giá trị có đường truy cập không hiệu quả hoặc lookup quá nhiều | Tốn dung lượng, tăng chi phí ghi và bảo trì chỉ mục |
| Tách truy vấn theo nhóm giá trị | Có một số nhóm độ chọn lọc rõ ràng và ổn định | Tăng độ phức tạp SQL và số nhánh cần kiểm thử |
| Biên dịch lại có chọn lọc | Giá trị thay đổi lớn và lợi ích kế hoạch riêng lớn hơn chi phí biên dịch | Tăng CPU, độ trễ compile và tải khi đồng thời cao |
| Dùng kế hoạch tổng quát | Các giá trị có hiệu năng chấp nhận được với một kế hoạch cân bằng | Có thể không tối ưu cho nhóm rất hiếm hoặc rất phổ biến |
| Ép hoặc cố định kế hoạch | Có kế hoạch đã kiểm chứng ổn định và cần kiểm soát hồi quy ngắn hạn | Dễ trở nên lỗi thời khi dữ liệu, schema hoặc tải thay đổi |
| Cơ chế nhiều biến thể kế hoạch | Hệ quản trị hỗ trợ và truy vấn có các vùng độ chọn lọc khác biệt | Tốn thêm bộ nhớ và cần theo dõi việc phân loại, chuyển đổi kế hoạch |

### Cải thiện thống kê trước khi ép kế hoạch

Nếu estimated rows sai nhiều so với actual rows, hãy xác minh thống kê và kiểu dữ liệu trước. Với SQL Server, kiểm tra histogram, statistics date, sample và các cột trong thống kê. Với PostgreSQL, kiểm tra `ANALYZE`, `pg_stats` và extended statistics nếu có tương quan. Với Oracle, kiểm tra optimizer statistics, histogram và trạng thái cursor. Mỗi hệ quản trị có cách thu thập và diễn giải khác nhau.

Không tăng tần suất cập nhật thống kê một cách máy móc. Việc thu thập quá thường xuyên có thể tốn I/O và CPU, trong khi một số workload thay đổi chậm không cần cập nhật liên tục. Lịch cập nhật cần dựa trên tốc độ biến động dữ liệu và mức sai lệch ước lượng quan sát được.

### Tách nhánh theo độ chọn lọc

Nếu có hai nhóm tham số rõ ràng, có thể cân nhắc truy vấn hoặc nhánh xử lý riêng. Ví dụ, giá trị hiếm dùng truy vấn có chỉ mục chọn lọc, giá trị phổ biến dùng đường truy cập phù hợp với nhiều dòng. Cần kiểm tra rằng điều kiện phân nhóm ổn định và không làm thay đổi kết quả nghiệp vụ.

Đừng tách nhánh chỉ vì một lần chạy chậm. Số lượng nhóm lớn, phân bố liên tục hoặc thường xuyên thay đổi có thể làm mã khó bảo trì và tạo thêm nhiều kế hoạch cần theo dõi.

### Dùng recompile hoặc hint có giới hạn

Biên dịch lại hoặc hint có thể giải quyết một trường hợp cụ thể, nhưng cũng có thể che khuất nguyên nhân gốc. Trước khi áp dụng, hãy đo chi phí compile, tần suất chạy, độ đồng thời, số giá trị khác nhau và tác động lên workload tổng thể. Ưu tiên phạm vi nhỏ nhất có thể và ghi lại lý do, điều kiện gỡ bỏ cùng cách theo dõi.

## 8. Đánh giá kết quả sau điều chỉnh

Một điều chỉnh chỉ có ích nếu cải thiện chất lượng phục vụ trên workload đại diện. Không chỉ đo thời gian của một giá trị tham số. Cần chạy cả nhóm phổ biến, hiếm, trung bình và các truy vấn liên quan.

Các chỉ số nên so sánh trước và sau:

- Thời gian thực thi trung vị, p95 và p99 theo nhóm tham số.
- Số hàng ước lượng so với số hàng thực tế.
- Logical reads, physical reads, CPU, elapsed time và số lần lookup.
- Chi phí biên dịch, số lần biên dịch lại và mức sử dụng plan cache.
- Memory grant, spill, wait và tranh chấp khi có tải đồng thời.
- Throughput, tỷ lệ lỗi và mức tiêu thụ tài nguyên toàn hệ thống.

Thử nghiệm cần bao gồm cả cache nóng và tình huống khởi động hoặc biên dịch lại nếu điều đó xảy ra trong vận hành. Giữ nguyên phiên bản hệ quản trị, cấu hình, dữ liệu và mức tải. Nếu có thể, lặp lại nhiều lần và ghi lại độ biến động.

Một ví dụ minh họa cách đánh giá:

| Nhóm tham số | Trước điều chỉnh | Sau điều chỉnh | Nhận xét |
|---|---:|---:|---|
| Hiếm | 12 ms | 8 ms | Cải thiện |
| Trung bình | 40 ms | 25 ms | Cải thiện |
| Phổ biến | 1.800 ms | 620 ms | Cải thiện đáng kể |
| Chi phí compile | 2 ms/lần, ít lần | 2 ms/lần, mỗi lần chạy | Cần đánh giá tải CPU tổng thể |

Các số liệu trên chỉ là ví dụ. Trong hệ thống thật, nếu độ trễ một nhóm giảm nhưng CPU tăng mạnh do biên dịch liên tục, cần xem xét trade-off. Nếu p99 hoặc throughput của workload khác xấu đi, thay đổi có thể chỉ chuyển nút thắt sang nơi khác.

## 9. Những sai lầm thường gặp

1. **Coi parameter sniffing luôn là lỗi:** tối ưu theo tham số thường giúp chọn kế hoạch tốt; vấn đề là kế hoạch dùng lại không phù hợp với nhóm khác.
2. **Chỉ thử một giá trị tham số:** không phát hiện được độ lệch dữ liệu và hồi quy giữa các nhóm.
3. **Xóa plan cache để chữa triệu chứng:** có thể gây biên dịch hàng loạt và làm toàn hệ thống tăng tải.
4. **Dùng `RECOMPILE` cho mọi truy vấn:** chi phí CPU và biên dịch có thể lớn hơn lợi ích.
5. **Ép một kế hoạch cố định lâu dài:** kế hoạch tốt hôm nay có thể kém khi dữ liệu hoặc tải thay đổi.
6. **Bỏ qua thống kê và kiểu dữ liệu:** sai lệch cardinality có thể là nguyên nhân gốc.
7. **Đồng nhất cơ chế giữa các hệ quản trị:** SQL Server, PostgreSQL và Oracle có cách xử lý bind parameter, plan cache và nhiều biến thể kế hoạch khác nhau.
8. **Chỉ nhìn elapsed time:** thiếu logical reads, CPU, waits và throughput sẽ khiến kết luận không đầy đủ.
9. **Không kiểm thử dưới tải đồng thời:** biên dịch lại, memory grant hoặc plan cache có thể ảnh hưởng khác khi nhiều phiên chạy cùng lúc.
10. **Không theo dõi sau triển khai:** thay đổi phân bố dữ liệu có thể làm kế hoạch lại mất phù hợp.

## 10. Danh sách kiểm tra khi điều tra tham số nhạy cảm

- [ ] Đã xác định query fingerprint, cách tham số hóa và hệ quản trị cùng phiên bản.
- [ ] Đã chọn các giá trị tham số phổ biến, hiếm, trung bình và có tương quan dữ liệu.
- [ ] Đã thu thập actual plan, estimated rows, actual rows và tham số thực thi.
- [ ] Đã xác minh kế hoạch được dùng lại, biên dịch lại hay có nhiều biến thể.
- [ ] Đã kiểm tra thống kê, histogram, kiểu dữ liệu và chỉ mục liên quan.
- [ ] Đã loại trừ các nguyên nhân như khóa, I/O, CPU, cache lạnh và connection pool.
- [ ] Đã chọn biện pháp phù hợp với cơ chế của hệ quản trị đang dùng.
- [ ] Đã đo chi phí biên dịch, logical reads, CPU, độ trễ phân vị và throughput.
- [ ] Đã kiểm thử toàn bộ nhóm giá trị và workload đồng thời trước khi triển khai.
- [ ] Đã có cách theo dõi hồi quy và điều kiện gỡ bỏ hint hoặc cấu hình tạm thời.

Tham số nhạy cảm xuất hiện khi các giá trị đầu vào có đặc tính dữ liệu khác nhau đủ lớn để cần những kế hoạch truy cập khác nhau. Parameter sniffing và tái sử dụng kế hoạch có thể cải thiện hiệu năng nhờ giảm chi phí tối ưu, nhưng cũng có thể làm một kế hoạch phù hợp với giá trị này trở nên kém hiệu quả với giá trị khác. Hãy kiểm chứng bằng thống kê, kế hoạch thực thi và tải đại diện; sau đó chọn giải pháp theo đúng cơ chế của SQL Server, PostgreSQL, Oracle hoặc hệ quản trị đang vận hành. Mọi điều chỉnh cần được đánh giá trên toàn bộ nhóm tham số cùng chi phí tài nguyên và độ ổn định của hệ thống.
