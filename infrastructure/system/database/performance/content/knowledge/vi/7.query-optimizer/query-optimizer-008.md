# Hint, ép kế hoạch và điều kiện cần theo dõi khi can thiệp bộ tối ưu

Bộ tối ưu truy vấn thường tự chọn đường truy cập dữ liệu, thứ tự phép nối và thuật toán xử lý dựa trên câu SQL, thống kê, tham số và mô hình chi phí. Trong phần lớn trường hợp, để bộ tối ưu lựa chọn tự động là cách vận hành phù hợp. Tuy nhiên, đôi khi kế hoạch được chọn không ổn định hoặc không phù hợp với một workload cụ thể. Khi đó, kỹ sư có thể cân nhắc dùng **optimizer hint** hoặc cơ chế **ép/giữ kế hoạch** để tác động đến lựa chọn của bộ tối ưu.

Can thiệp này cần dựa trên bằng chứng. Một hint có thể cải thiện một truy vấn với bộ tham số đang xét nhưng làm chậm các tham số khác, tăng chi phí ghi, dùng nhiều bộ nhớ hoặc trở nên bất lợi sau khi dữ liệu thay đổi. Vì vậy, bài học tập trung vào cách hiểu hint và plan forcing, thời điểm nên cân nhắc, quy trình kiểm chứng và những điều kiện phải theo dõi sau khi áp dụng.

Bài học thuộc chương **Bộ tối ưu truy vấn** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; các nội dung liên quan gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Do đó, hint và ép kế hoạch chỉ là một phần của quy trình tối ưu có đo đạc, gắn với kế hoạch thực thi và workload thực tế.

## 1. Hint và ép kế hoạch là gì?

### 1.1. Optimizer hint

Optimizer hint là chỉ dẫn được cung cấp cho hệ quản trị để ảnh hưởng đến một hoặc nhiều quyết định khi tối ưu câu SQL. Tùy sản phẩm, hint có thể yêu cầu hoặc ưu tiên:

- Sử dụng hay tránh một chỉ mục hoặc đường truy cập cụ thể.
- Chọn thuật toán nối như nested loop, hash join hoặc merge join.
- Giữ một thứ tự nối nhất định.
- Điều chỉnh mức song song hoặc cách phân bổ tài nguyên cho câu lệnh.
- Tái biên dịch câu lệnh hoặc dùng một chính sách tối ưu khác.

Hint có thể nằm trong comment của câu SQL, phần mệnh đề dành riêng cho hint hoặc cấu hình ở cấp phiên/câu lệnh. Cú pháp, mức độ bắt buộc và cách xử lý hint không hợp lệ khác nhau giữa các hệ quản trị. Có sản phẩm xem hint như chỉ dẫn mạnh, có sản phẩm chỉ xem như gợi ý, và có hint có thể bị bỏ qua nếu không áp dụng được.

### 1.2. Ép hoặc giữ kế hoạch (plan forcing)

Ép kế hoạch là cơ chế yêu cầu hệ quản trị tiếp tục sử dụng một kế hoạch đã được chọn hoặc đã ghi nhận trước đó, trong phạm vi mà sản phẩm hỗ trợ. Cơ chế này thường được dùng khi một câu SQL từng có kế hoạch tốt nhưng sau đó bộ tối ưu chọn kế hoạch khác gây hồi quy hiệu năng.

Ví dụ về cơ chế theo sản phẩm:

- SQL Server có Query Store và khả năng force một plan đã lưu cho một query.
- Oracle có SQL Plan Management với SQL Plan Baseline để quản lý và kiểm soát kế hoạch được chấp nhận.
- MySQL hỗ trợ optimizer hint và các cơ chế điều khiển đường truy cập tùy phiên bản; không nên mặc định rằng mọi cấu hình hint đều tương đương với một cơ chế pin kế hoạch lâu dài.
- PostgreSQL có các thiết lập planner và extension bên ngoài như `pg_hint_plan` ở những môi trường đã cài đặt; khả năng và chính sách hỗ trợ phụ thuộc phiên bản, extension và cấu hình cụ thể.

Plan forcing không phải một tính năng có cùng ngữ nghĩa trên mọi hệ quản trị. Trước khi dùng, cần kiểm tra tài liệu đúng sản phẩm và phiên bản, điều kiện để kế hoạch được force, hành vi khi kế hoạch không còn hợp lệ và cách bỏ force.

### 1.3. Phân biệt hint, ép kế hoạch và sửa nguyên nhân

| Cách can thiệp | Tác động chính | Ví dụ |
|---|---|---|
| Sửa SQL | Làm rõ ý định truy vấn hoặc giảm công việc phải thực hiện | Viết điều kiện lọc có thể tận dụng chỉ mục |
| Sửa thống kê | Cải thiện thông tin đầu vào cho bộ tối ưu | Cập nhật thống kê hoặc bổ sung thống kê phù hợp |
| Thiết kế chỉ mục | Thay đổi cấu trúc truy cập dữ liệu sẵn có | Tạo chỉ mục ghép theo điều kiện lọc và sắp xếp |
| Optimizer hint | Ảnh hưởng một số lựa chọn khi tối ưu | Gợi ý chỉ mục hoặc thuật toán join |
| Plan forcing | Giữ một kế hoạch cụ thể đã được ghi nhận, nếu sản phẩm hỗ trợ | Force plan tốt trong Query Store |

Hint và plan forcing có thể xử lý triệu chứng trong một bối cảnh nhất định. Nếu nguyên nhân gốc là thống kê sai, dữ liệu lệch, truy vấn không phù hợp hoặc chỉ mục thiếu, việc ép một kế hoạch có thể chỉ che giấu vấn đề và tạo thêm rủi ro về sau.

## 2. Vì sao bộ tối ưu đôi khi chọn kế hoạch không phù hợp?

Bộ tối ưu phải dự đoán lượng công việc và chi phí của nhiều phương án. Dự đoán không phải lúc nào cũng chính xác. Những nguyên nhân thường gặp gồm:

- **Thống kê cũ hoặc chưa đủ:** phân bố dữ liệu đã thay đổi, histogram không phản ánh nhóm giá trị quan trọng hoặc tương quan giữa các cột chưa được mô hình hóa.
- **Độ chọn lọc phụ thuộc tham số:** cùng một câu SQL có thể nhận một giá trị tham số rất hiếm ở lần chạy này và rất phổ biến ở lần chạy khác.
- **Kế hoạch được tái sử dụng:** kế hoạch được tạo trong một bối cảnh tham số có thể không phù hợp với nhóm tham số khác, tùy cơ chế cache và tối ưu của hệ quản trị.
- **Mô hình chi phí khác thực tế:** chi phí ước lượng không phản ánh đầy đủ độ trễ lưu trữ, cache, tranh chấp hoặc đặc điểm phần cứng.
- **Tương tác phức tạp giữa các toán tử:** thứ tự join, parallelism, sort, memory grant và truy cập chỉ mục có thể tạo hiệu ứng cộng hưởng.
- **Thay đổi môi trường:** nâng cấp phiên bản, thay đổi cấu hình, phần cứng, chỉ mục hoặc khối lượng dữ liệu làm thay đổi lựa chọn tối ưu.

Khi gặp truy vấn chậm, hãy xác định trước liệu kế hoạch có thật sự là nguyên nhân. Một kế hoạch nhìn có vẻ khác thường chưa chắc là nút thắt; độ trễ có thể đến từ chờ khóa, I/O, pool kết nối hoặc tầng ứng dụng. Cần ghép kế hoạch với số liệu runtime và trạng thái hệ thống tại cùng thời điểm.

## 3. Các nhóm hint thường gặp

Tên hint và cú pháp không thống nhất giữa các sản phẩm. Có thể phân nhóm theo quyết định mà hint tác động:

| Nhóm | Mục đích | Rủi ro cần đánh giá |
|---|---|---|
| Access path / index hint | Ưu tiên hoặc giới hạn đường truy cập qua chỉ mục | Chỉ mục có thể kém chọn lọc khi dữ liệu hoặc tham số thay đổi |
| Join method hint | Tác động lựa chọn nested loop, hash join hoặc merge join | Thuật toán tốt với một kích thước đầu vào có thể rất tệ với kích thước khác |
| Join order hint | Điều khiển thứ tự kết hợp bảng | Thứ tự cố định có thể không phù hợp với phân bố dữ liệu mới |
| Parallelism hint | Điều chỉnh mức song song hoặc yêu cầu chạy tuần tự | Có thể tăng cạnh tranh CPU, bộ nhớ, I/O hoặc làm giảm khả năng phục vụ workload khác |
| Memory/resource hint | Tác động đến bộ nhớ hoặc tài nguyên dành cho truy vấn | Có thể gây áp lực bộ nhớ, spill hoặc giảm tài nguyên của truy vấn khác |
| Recompile/plan cache hint | Thay đổi cách biên dịch hoặc tái sử dụng kế hoạch | Tái biên dịch thường xuyên có thể tăng CPU và chi phí biên dịch |

Không nên dùng một hint chỉ vì tên toán tử hiện tại không giống kỳ vọng. Hãy đo xem toán tử đang thực hiện bao nhiêu công việc, với bao nhiêu hàng, vòng lặp, bộ nhớ và I/O. Ví dụ, scan có thể hiệu quả khi truy vấn đọc phần lớn bảng; index seek có thể tốn kém nếu kéo theo hàng triệu lần lookup.

## 4. Khi nào nên cân nhắc hint hoặc ép kế hoạch?

Có thể cân nhắc can thiệp khi đã có bằng chứng rõ ràng, chẳng hạn:

1. Một truy vấn quan trọng bị hồi quy sau khi thống kê, dữ liệu, phiên bản hoặc cấu hình thay đổi.
2. Có một kế hoạch tốt đã được đo trên workload đại diện và kế hoạch mới gây suy giảm rõ rệt.
3. Bộ tối ưu liên tục chọn đường truy cập hoặc thuật toán không phù hợp với nhóm tham số đã xác định.
4. Cần biện pháp giảm tác động tạm thời trong lúc điều tra hoặc chuẩn bị sửa nguyên nhân gốc.
5. Hệ quản trị cung cấp cơ chế quản lý kế hoạch có kiểm soát và có thể theo dõi trạng thái áp dụng.

Trước khi can thiệp, hãy kiểm tra các hướng xử lý cơ bản:

- Thống kê có mới và đủ đại diện không?
- Kiểu dữ liệu, ép kiểu ngầm và biểu thức lọc có làm giảm khả năng dùng chỉ mục không?
- Câu SQL có yêu cầu đọc hoặc sắp xếp quá nhiều dữ liệu không?
- Chỉ mục hiện tại có phù hợp với điều kiện lọc, join và thứ tự không?
- Truy vấn có bị chặn bởi khóa hoặc chờ I/O thay vì do lựa chọn kế hoạch không?
- Vấn đề chỉ xuất hiện với một nhóm tham số hay xảy ra với mọi tham số?

Nếu có thể giải quyết bằng cách cập nhật thống kê, sửa SQL hoặc thiết kế chỉ mục phù hợp, hãy đánh giá những lựa chọn đó trước khi khóa cứng kế hoạch. Hint hoặc ép kế hoạch nên có lý do cụ thể, phạm vi áp dụng và điều kiện xem xét lại.

## 5. Khi nào không nên dùng?

Không nên can thiệp bộ tối ưu chỉ vì:

- Một lần chạy riêng lẻ chậm bất thường mà chưa có baseline hoặc chưa lặp lại phép đo.
- Một toán tử scan xuất hiện trong kế hoạch dù truy vấn cần phần lớn dữ liệu.
- Estimated cost cao hơn một truy vấn khác nhưng thời gian và throughput thực tế vẫn đạt mục tiêu.
- Kế hoạch mới khác kế hoạch cũ nhưng chưa có bằng chứng rằng nó gây hồi quy.
- Chưa biết nhóm tham số, tỷ lệ đọc/ghi hoặc workload bị ảnh hưởng.
- Chưa có cách giám sát và khôi phục sau khi áp dụng.

Không dùng hint để thay thế việc hiểu nguyên nhân. Một hint có thể làm một câu truy vấn chạy nhanh trong bài thử nhỏ nhưng khiến hệ thống suy giảm khi tải đồng thời tăng hoặc dữ liệu phát triển.

## 6. Quy trình can thiệp có kiểm soát

### Bước 1: Xác định truy vấn và phạm vi ảnh hưởng

Ghi lại định danh truy vấn, câu SQL đã chuẩn hóa, tham số đại diện, tần suất, nhóm người dùng, tỷ lệ đọc/ghi và mức độ quan trọng nghiệp vụ. Xác định vấn đề xuất hiện ở một câu SQL, một nhóm tham số, một máy chủ hay toàn bộ workload.

Không chỉ lấy một mẫu tham số thuận lợi. Nếu độ chọn lọc thay đổi đáng kể, hãy phân nhóm giá trị phổ biến, trung bình và hiếm để kiểm tra tính ổn định của kế hoạch.

### Bước 2: Thu thập đường cơ sở

Trước khi thay đổi, lưu lại:

- Kế hoạch ước lượng và kế hoạch thực tế, nếu có thể lấy an toàn.
- Estimated rows và actual rows tại các toán tử quan trọng.
- Số loops, logical reads, physical reads, thời gian CPU và elapsed time.
- p50/p95/p99, throughput, timeout và tỷ lệ lỗi ở cấp workload.
- Trạng thái chờ I/O, khóa, bộ nhớ, parallelism và connection pool.
- Thống kê, chỉ mục, cấu hình, phiên bản hệ quản trị và thời điểm thu thập.

Đường cơ sở cần bao gồm cả truy vấn mục tiêu và các workload có thể bị ảnh hưởng. Nếu chỉ đo thời gian một truy vấn chạy riêng, ta có thể bỏ sót việc hint làm tăng cạnh tranh khi nhiều truy vấn chạy cùng lúc.

### Bước 3: Nêu giả thuyết và chọn mức can thiệp nhỏ nhất

Ví dụ giả thuyết:

> Với nhóm tham số có độ chọn lọc cao, bộ tối ưu chọn scan và xử lý quá nhiều hàng. Nếu ưu tiên đường truy cập qua chỉ mục phù hợp, số hàng đọc và p95 sẽ giảm vì truy vấn chỉ cần đọc một phạm vi nhỏ. Thay đổi được chấp nhận nếu kết quả không đổi, chi phí ghi vẫn trong giới hạn và nhóm tham số phổ biến không bị suy giảm.

Xác định rõ một thay đổi chính: một hint, một plan forcing hoặc một điều chỉnh khác. Không kết hợp đồng thời nhiều hint, thay đổi SQL, chỉ mục và cấu hình máy chủ nếu chưa có thiết kế thí nghiệm riêng để phân tách tác động.

### Bước 4: Thử nghiệm trên môi trường phù hợp

Ưu tiên môi trường có dữ liệu, thống kê, phiên bản và cấu hình gần với môi trường thật. Dùng cùng workload, tham số, mức đồng thời và trạng thái cache có thể so sánh. Chạy đủ lâu để đo được phân bố độ trễ và tác động lên tài nguyên.

Nếu buộc phải thử trên hệ thống đang phục vụ người dùng, tuân thủ quy trình thay đổi, giới hạn phạm vi, theo dõi liên tục và chuẩn bị cách bỏ hint hoặc bỏ force. Không ép kế hoạch trên toàn bộ workload khi bằng chứng chỉ liên quan đến một truy vấn cụ thể.

### Bước 5: So sánh kết quả và kiểm tra tác động phụ

Đối chiếu kế hoạch mới với kế hoạch trước. Xác nhận hint/force có được áp dụng hay không, đường truy cập và thuật toán có thay đổi như dự kiến không, số hàng và số lần đọc có giảm không. Sau đó đánh giá độ trễ, throughput, CPU, I/O, bộ nhớ, khóa và workload liên quan.

Không chỉ nhìn chỉ số của câu SQL mục tiêu. Một kế hoạch có thể giảm thời gian của truy vấn này nhưng giữ nhiều bộ nhớ hơn, tạo thêm I/O ngẫu nhiên hoặc chiếm CPU khiến các truy vấn khác chậm đi.

### Bước 6: Ghi nhận quyết định và thời hạn xem xét

Nếu kết quả tốt và các chỉ số bảo vệ vẫn đạt, ghi lại lý do áp dụng, phạm vi, phiên bản, plan identifier nếu có, ngày triển khai, người phụ trách và điều kiện bỏ can thiệp. Đặt thời điểm xem xét lại sau khi dữ liệu, thống kê, chỉ mục, cấu hình hoặc phiên bản hệ quản trị thay đổi.

Nếu kết quả không ổn định hoặc tác động phụ vượt giới hạn, bỏ hint/force theo quy trình khôi phục và quay lại baseline. Ghi nhận giả thuyết bị bác bỏ để tránh lặp lại cùng một can thiệp mà không có thêm bằng chứng.

## 7. Ví dụ cú pháp theo hệ quản trị

Các ví dụ sau nhằm minh họa cách tiếp cận. Hãy xác nhận cú pháp, tên hint, phiên bản và quyền thực thi trên hệ thống thực tế trước khi sử dụng.

### 7.1. MySQL: optimizer hint cho chỉ mục

Giả sử truy vấn dùng alias `o` và có chỉ mục `idx_orders_customer_created`. Một hint có thể được viết trong comment ngay sau từ khóa `SELECT`:

```sql
SELECT /*+ INDEX(o idx_orders_customer_created) */
       o.order_id, o.created_at
FROM orders AS o
WHERE o.customer_id = 42
ORDER BY o.created_at DESC
LIMIT 50;
```

Hint `INDEX` tác động đến lựa chọn chỉ mục của bảng được chỉ định. Cần kiểm tra trong `EXPLAIN` hoặc `EXPLAIN ANALYZE` (nếu phiên bản hỗ trợ) xem chỉ mục có được dùng và lượng công việc có giảm không. Nếu hint bị bỏ qua, không áp dụng được hoặc làm kế hoạch kém hơn, phải tìm nguyên nhân thay vì giả định rằng chỉ cần thêm hint là kế hoạch sẽ đúng.

### 7.2. PostgreSQL: hint qua extension nếu môi trường có hỗ trợ

PostgreSQL lõi cung cấp các thiết lập planner để thử nghiệm lựa chọn một số loại kế hoạch; việc điều khiển ở cấp truy vấn bằng comment hint thường cần extension như `pg_hint_plan`. Ví dụ minh họa cú pháp của extension:

```sql
/*+
  IndexScan(o idx_orders_customer_created)
*/
SELECT o.order_id, o.created_at
FROM orders AS o
WHERE o.customer_id = 42
ORDER BY o.created_at DESC
LIMIT 50;
```

Đoạn hint chỉ có tác dụng khi extension phù hợp đã được cài đặt và cấu hình theo phiên bản PostgreSQL đang dùng. Không được giả định rằng PostgreSQL lõi sẽ tự hiểu comment này. Các thiết lập như `enable_seqscan` có thể hữu ích trong chẩn đoán ở một phiên thử nghiệm, nhưng không nên được xem là cách pin kế hoạch ổn định cho ứng dụng.

### 7.3. SQL Server: hint tái biên dịch

SQL Server hỗ trợ query hint trong mệnh đề `OPTION`. Ví dụ dưới đây yêu cầu biên dịch lại câu truy vấn ở mỗi lần thực thi:

```sql
SELECT order_id, created_at
FROM dbo.Orders
WHERE customer_id = @customer_id
ORDER BY created_at DESC
OPTION (RECOMPILE);
```

`RECOMPILE` có thể hữu ích khi kế hoạch cần phản ánh giá trị tham số hiện tại, nhưng làm phát sinh chi phí biên dịch và có thể tăng CPU nếu câu lệnh chạy rất thường xuyên. Phải đo cả lợi ích về thực thi lẫn chi phí biên dịch, đồng thời kiểm tra các nhóm tham số khác nhau.

### 7.4. SQL Server: ép kế hoạch đã lưu trong Query Store

Khi Query Store đã thu thập query và plan phù hợp, quản trị viên có thể force một plan đã lưu bằng thủ tục hệ thống. Ví dụ minh họa:

```sql
EXEC sys.sp_query_store_force_plan
    @query_id = 123,
    @plan_id = 456;
```

Để bỏ ép kế hoạch:

```sql
EXEC sys.sp_query_store_unforce_plan
    @query_id = 123,
    @plan_id = 456;
```

Các ID trong ví dụ là giá trị minh họa; phải lấy đúng `query_id` và `plan_id` từ Query Store của cơ sở dữ liệu đích. Cần kiểm tra trạng thái force, thông tin lỗi hoặc lý do không thể áp dụng kế hoạch qua các view và công cụ quản trị tương ứng. Plan forcing có thể thất bại hoặc không còn phù hợp khi schema, chỉ mục, thống kê hay môi trường thay đổi.

### 7.5. Oracle: quản lý kế hoạch bằng SQL Plan Baseline

Oracle SQL Plan Management cho phép quản lý các SQL plan baseline nhằm kiểm soát những kế hoạch được chấp nhận cho câu lệnh. Quy trình thường gồm thu thập kế hoạch, đánh giá và chấp nhận kế hoạch phù hợp, theo dõi việc sử dụng baseline và xử lý khi kế hoạch không còn hiệu quả. Cách tải, bật, tiến hóa hoặc loại bỏ baseline phụ thuộc phiên bản Oracle và cấu hình; hãy dùng package và tài liệu quản trị đúng phiên bản thay vì sao chép lệnh từ môi trường khác.

Điểm quan trọng là baseline cung cấp cơ chế quản trị vòng đời kế hoạch. Nó vẫn cần được theo dõi khi dữ liệu, thống kê, chỉ mục hoặc phiên bản thay đổi.

## 8. Điều kiện cần theo dõi sau khi can thiệp

Áp dụng hint hoặc ép kế hoạch không kết thúc công việc. Cần theo dõi để xác nhận can thiệp tiếp tục có lợi và không tạo tác động phụ.

| Nhóm theo dõi | Chỉ số hoặc tín hiệu | Điều cần xác nhận |
|---|---|---|
| Kế hoạch | Plan identifier, plan hash, toán tử, đường truy cập, trạng thái hint/force | Kế hoạch dự kiến có thực sự được áp dụng và có ổn định không? |
| Độ trễ | p50, p95, p99, elapsed time | Người dùng có nhận được cải thiện bền vững không? |
| Thông lượng | Số truy vấn/giao dịch hoàn thành mỗi giây | Hệ thống có xử lý được nhiều công việc hơn không? |
| CPU | CPU theo truy vấn và toàn máy chủ, chi phí biên dịch | Hint có chuyển chi phí sang CPU hoặc compile không? |
| I/O | Logical reads, physical reads, IOPS, throughput, độ trễ và hàng đợi | Lượng đọc hoặc chờ lưu trữ có tăng không? |
| Bộ nhớ | Memory grant, bộ nhớ sử dụng, spill và áp lực bộ nhớ | Kế hoạch có dùng quá nhiều bộ nhớ hoặc spill ra đĩa không? |
| Đồng thời | Wait events, blocking, deadlock, thời gian giữ khóa | Kế hoạch có làm tăng tranh chấp hoặc thời gian giao dịch không? |
| Kết nối | Pool utilization, thời gian chờ lấy kết nối, timeout | Truy vấn có giữ kết nối lâu hơn không? |
| Tác động workload | Độ trễ và throughput của các truy vấn khác | Tối ưu một truy vấn có làm workload khác suy giảm không? |
| Tính đúng đắn | Số hàng, kết quả, lỗi và bất biến nghiệp vụ | Kết quả dữ liệu có giữ nguyên không? |

### 8.1. Theo dõi theo nhóm tham số

Nếu câu SQL nhận nhiều giá trị tham số, hãy phân nhóm theo đặc tính chọn lọc. Một kế hoạch tốt cho khách hàng có ít đơn hàng có thể kém với khách hàng có hàng triệu đơn hàng. Sau khi áp dụng hint hoặc force, đo ít nhất các nhóm tham số phổ biến và những trường hợp cực trị có ý nghĩa nghiệp vụ.

Theo dõi cả độ trễ ở phân vị cao. Giá trị trung bình có thể tốt lên trong khi p99 xấu đi do một nhóm tham số bị ảnh hưởng. Cần xác định rõ nhóm nào được cải thiện, nhóm nào suy giảm và liệu chính sách can thiệp có phù hợp với tỷ trọng workload hay không.

### 8.2. Theo dõi sau thay đổi dữ liệu và môi trường

Kế hoạch bị ép có thể trở nên kém hiệu quả khi bảng tăng kích thước, phân bố dữ liệu thay đổi, chỉ mục được thêm/xóa, thống kê cập nhật, cấu hình tài nguyên thay đổi hoặc hệ quản trị nâng cấp. Sau những sự kiện này, cần kiểm tra lại kế hoạch và so sánh với phương án mà bộ tối ưu tự chọn.

Nên đặt điều kiện đánh giá lại, ví dụ khi p95 vượt SLO trong một khoảng thời gian, logical reads tăng đáng kể, tỷ lệ lỗi tăng, plan forcing báo không áp dụng được hoặc có thay đổi schema/phiên bản. Ngưỡng cụ thể phải dựa trên baseline và SLO của hệ thống.

## 9. Rủi ro của hint và plan forcing

### 9.1. Tối ưu cục bộ làm workload tổng thể kém hơn

Một hint có thể giảm thời gian của truy vấn mục tiêu nhưng làm tăng CPU, I/O ngẫu nhiên hoặc bộ nhớ. Khi nhiều phiên chạy đồng thời, lợi ích của một truy vấn có thể biến mất do tranh chấp tài nguyên. Vì vậy, cần đo ở mức workload, không chỉ chạy đơn lẻ.

### 9.2. Kế hoạch bị khóa trở nên lỗi thời

Kế hoạch từng tốt có thể không còn tốt khi bảng lớn hơn, phân bố dữ liệu thay đổi hoặc chỉ mục mới xuất hiện. Ép giữ kế hoạch cũ có thể ngăn bộ tối ưu tận dụng thông tin hoặc khả năng mới. Mỗi can thiệp cần có chủ sở hữu và thời điểm xem xét lại.

### 9.3. Hint không còn hợp lệ hoặc bị bỏ qua

Hint có thể tham chiếu chỉ mục đã bị đổi tên/xóa, dùng alias không đúng, xung đột với hint khác hoặc không tương thích với cấu trúc truy vấn. Một số hệ quản trị bỏ qua hint không hợp lệ; một số trường hợp khác có thể báo lỗi. Phải kiểm tra kế hoạch thực tế và thông báo của hệ quản trị sau khi áp dụng.

### 9.4. Che giấu vấn đề thống kê hoặc thiết kế

Nếu thống kê sai, ép một kế hoạch có thể che giấu lỗi ước lượng. Khi dữ liệu thay đổi, kế hoạch bị ép có thể trở nên rất tệ. Hãy sửa thông tin thống kê hoặc thiết kế dữ liệu nếu đó là nguyên nhân gốc và có thể giải quyết an toàn.

### 9.5. Tăng chi phí bảo trì và độ phức tạp

Hint trong SQL làm câu lệnh gắn với một quyết định tối ưu cụ thể; người bảo trì cần hiểu lý do và điều kiện để bỏ nó. Plan forcing tạo thêm cấu hình vận hành phải quản lý, kiểm tra sau nâng cấp và theo dõi trạng thái. Nếu không có tài liệu và người phụ trách, các can thiệp tạm thời có thể tồn tại vô thời hạn.

## 10. Quản lý vòng đời và khôi phục

Trước khi áp dụng, ghi lại:

- Câu SQL hoặc định danh truy vấn được can thiệp.
- Hint hoặc plan identifier cụ thể, hệ quản trị và phiên bản.
- Bằng chứng cho thấy kế hoạch cũ gây vấn đề và kế hoạch thay thế tốt hơn.
- Nhóm tham số và workload đã được thử.
- Chỉ số chính, chỉ số bảo vệ và ngưỡng rollback.
- Người phụ trách, thời điểm bắt đầu và ngày xem xét lại.
- Cách gỡ hint hoặc bỏ force.

Sau khi áp dụng, xác nhận hệ quản trị đã tiếp nhận can thiệp, theo dõi dashboard và log, rồi so sánh với baseline. Nếu độ trễ, throughput, lỗi hoặc tài nguyên vượt ngưỡng đã định, thực hiện rollback theo quy trình và xác nhận kế hoạch trước đó hoặc kế hoạch tự tối ưu đã hoạt động trở lại.

Không xóa ngay bằng chứng của kế hoạch cũ. Lưu lại plan, số liệu trước/sau và lý do rollback để phục vụ điều tra và đánh giá ở lần thay đổi tiếp theo. Khi đã khắc phục nguyên nhân gốc hoặc hệ quản trị có kế hoạch tốt hơn, hãy đánh giá việc bỏ hint/force thay vì giữ can thiệp theo thói quen.

## 11. Ví dụ tình huống: truy vấn hồi quy sau thay đổi thống kê

Một truy vấn báo cáo từng hoàn thành trong khoảng 300 ms nhưng sau một đợt cập nhật thống kê, p95 tăng lên 2 giây. Kế hoạch mới dùng nested loop với số lần truy cập bảng bên trong tăng mạnh. Kế hoạch lịch sử cho thấy một hash join từng xử lý workload này tốt hơn.

Quy trình điều tra:

1. Xác nhận p95 tăng trên cùng nhóm tham số và cùng thời điểm workload.
2. Lấy kế hoạch hiện tại và kế hoạch trước đó từ công cụ lưu lịch sử nếu có.
3. So sánh estimated rows với actual rows, số loops, logical reads, CPU, memory grant và spill.
4. Kiểm tra thống kê vừa thay đổi, phân bố dữ liệu và nhóm tham số đã dùng khi biên dịch.
5. Thử kế hoạch cũ trong môi trường tương đương hoặc dùng cơ chế plan forcing được hệ quản trị hỗ trợ.
6. Chạy workload đại diện gồm tham số phổ biến và hiếm; đo cả truy vấn mục tiêu lẫn các truy vấn cùng chia sẻ tài nguyên.
7. Nếu kế hoạch cũ cải thiện kết quả và không tạo tác động phụ, áp dụng có kiểm soát với ngưỡng rollback và ngày xem xét lại.
8. Tiếp tục điều tra vì sao ước lượng hoặc lựa chọn kế hoạch thay đổi; đánh giá cập nhật thống kê, thiết kế chỉ mục hoặc cách xử lý tham số để có giải pháp bền vững.

Kế hoạch cũ không mặc nhiên tốt chỉ vì nó từng nhanh. Cần xác nhận rằng dữ liệu, schema, workload và tài nguyên hiện tại vẫn phù hợp với kế hoạch đó. Nếu kết quả thử nghiệm không xác nhận lợi ích, không nên ép kế hoạch chỉ dựa trên lịch sử.

## 12. Những sai lầm thường gặp

- **Dùng hint ngay khi thấy scan:** scan có thể là lựa chọn hiệu quả khi cần đọc phần lớn dữ liệu.
- **Ép kế hoạch dựa trên một lần chạy:** một mẫu đơn lẻ không đại diện cho nhiều tham số và mức tải.
- **Chỉ đo truy vấn mục tiêu:** bỏ qua tác động lên workload chia sẻ CPU, bộ nhớ, I/O và khóa.
- **Không kiểm tra hint có được áp dụng:** cú pháp sai, xung đột hoặc phiên bản không hỗ trợ có thể khiến hint bị bỏ qua hoặc gây lỗi.
- **Nhầm cost với thời gian:** cost là mô hình nội bộ, không phải số mili giây thực tế.
- **Bỏ qua chi phí biên dịch:** hint tái biên dịch có thể làm CPU tăng khi truy vấn chạy thường xuyên.
- **Không theo dõi theo tham số:** một kế hoạch cố định có thể tốt cho nhóm tham số này nhưng tệ cho nhóm khác.
- **Không đặt thời hạn xem xét:** can thiệp tạm thời trở thành cấu hình vĩnh viễn dù điều kiện đã thay đổi.
- **Không có rollback:** khi kế hoạch gây hồi quy, nhóm không có cách quay lại trạng thái ổn định nhanh chóng.

## 13. Bài tập tự kiểm tra

### Bài tập 1: Có nên ép index seek?

Một truy vấn hiện dùng table scan và trả về 65% số hàng trong bảng. Người vận hành muốn ép index seek vì cho rằng seek luôn nhanh hơn scan.

**Câu hỏi:** cần kiểm tra gì trước khi dùng hint?

**Gợi ý trả lời:** xác định tỷ lệ dữ liệu cần trả về, số trang phải đọc, chi phí lookup, logical/physical reads và thời gian thực tế. Scan có thể phù hợp hơn khi truy vấn cần phần lớn bảng. Chỉ dùng hint nếu phép đo workload đại diện cho thấy đường truy cập thay thế tốt hơn và không gây tác động phụ.

### Bài tập 2: Kế hoạch cũ nhanh hơn

Một truy vấn có kế hoạch mới chậm hơn kế hoạch cũ. Kế hoạch cũ có thể được force trong Query Store.

**Yêu cầu:** liệt kê các kiểm tra trước khi force và các chỉ số cần theo dõi sau khi force.

**Gợi ý trả lời:** kiểm tra cùng nhóm tham số, dữ liệu, schema, chỉ mục, thống kê và cấu hình; so sánh actual rows, loops, reads, CPU, thời gian và memory grant. Sau khi force, theo dõi plan identifier, p95/p99, throughput, CPU, I/O, bộ nhớ, wait events, lỗi và workload liên quan; chuẩn bị thủ tục unforce.

### Bài tập 3: Hint cải thiện một nhóm tham số nhưng làm nhóm khác chậm

Một hint làm p95 giảm từ 800 ms xuống 250 ms với khách hàng có ít đơn hàng, nhưng p95 tăng từ 1 giây lên 4 giây với khách hàng có dữ liệu rất lớn.

**Câu hỏi:** có nên áp dụng hint cho toàn bộ câu SQL không?

**Gợi ý trả lời:** chưa nên. Kết quả cho thấy kế hoạch phụ thuộc độ chọn lọc của tham số. Cần phân nhóm workload, xem xét cơ chế tối ưu theo tham số hoặc cách xử lý riêng phù hợp với hệ quản trị, rồi thử lại trên toàn bộ phân bố tải. Không đánh đổi một nhóm người dùng mà không đánh giá tác động nghiệp vụ.

### Checklist trước và sau khi can thiệp bộ tối ưu

- [ ] Có baseline và bằng chứng về hồi quy hoặc lựa chọn kế hoạch không phù hợp.
- [ ] Đã kiểm tra thống kê, tham số, SQL, chỉ mục và trạng thái chờ.
- [ ] Giả thuyết nêu rõ kế hoạch hoặc quyết định nào cần tác động và vì sao.
- [ ] Đã xác nhận cú pháp, phạm vi hỗ trợ và hành vi của hint/plan forcing trên đúng phiên bản.
- [ ] Đã thử trên workload và nhóm tham số đại diện.
- [ ] Đã đo độ trễ, throughput, CPU, I/O, bộ nhớ, khóa và tác động workload liên quan.
- [ ] Đã xác nhận hint/force thực sự được áp dụng.
- [ ] Có ngưỡng rollback, cách gỡ can thiệp, người phụ trách và ngày xem xét lại.
- [ ] Đã kiểm tra tính đúng đắn dữ liệu và kết quả nghiệp vụ.
- [ ] Tiếp tục theo dõi sau thay đổi dữ liệu, thống kê, schema, cấu hình hoặc nâng cấp.

Hint và ép kế hoạch là công cụ can thiệp có chủ đích vào quá trình tối ưu truy vấn. Chúng chỉ nên được giữ khi có bằng chứng cho thấy kế hoạch được điều khiển phù hợp với workload hiện tại, cải thiện mục tiêu hiệu năng và không vượt giới hạn về tài nguyên, tính đúng đắn hoặc các truy vấn khác. Theo dõi liên tục và quản lý vòng đời giúp can thiệp tiếp tục có giá trị khi dữ liệu và môi trường thay đổi.
