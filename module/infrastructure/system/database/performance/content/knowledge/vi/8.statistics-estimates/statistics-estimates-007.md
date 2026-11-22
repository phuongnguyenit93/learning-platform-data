# Thu thập thống kê bằng lấy mẫu: chi phí và độ chính xác

Bộ tối ưu truy vấn cần ước lượng số hàng phù hợp với điều kiện lọc, số hàng trung gian sau phép nối và lượng dữ liệu phải đọc. Các ước lượng này ảnh hưởng trực tiếp đến lựa chọn index seek hay scan, thứ tự join, thuật toán join, cấp phát bộ nhớ và cách thực thi song song. Để đưa ra ước lượng, hệ quản trị dựa vào thống kê về bảng, cột, chỉ mục và phân bố dữ liệu.

Với bảng lớn, đọc toàn bộ dữ liệu chỉ để xây dựng thống kê có thể tốn I/O, CPU và thời gian. Vì vậy, nhiều hệ quản trị dùng **lấy mẫu** (*sampling*) để suy ra đặc điểm của toàn bộ tập dữ liệu từ một phần quan sát. Lấy mẫu giúp giảm chi phí thu thập, nhưng mẫu nhỏ hoặc không đại diện có thể bỏ sót giá trị hiếm, đánh giá sai độ lệch và làm cardinality estimate thiếu chính xác.

Trong module **DATABASE_PERFORMANCE**, cần hiểu cách chọn kích thước mẫu, nhận diện sai lệch, đánh giá chi phí và kiểm chứng ảnh hưởng của thống kê đến kế hoạch thực thi. Mục tiêu là thu thập đủ thông tin để bộ tối ưu đưa ra quyết định tốt với chi phí vận hành phù hợp.

## 1. Thống kê cơ sở dữ liệu dùng để làm gì?

Thống kê (*statistics*) là bản tóm tắt đặc điểm dữ liệu mà bộ tối ưu sử dụng để ước lượng chi phí của các phương án thực thi. Tùy hệ quản trị, thống kê có thể chứa số hàng, số trang, số giá trị phân biệt, tỷ lệ null, giá trị phổ biến, histogram, mật độ hoặc thông tin tương quan giữa các cột.

Ví dụ, với truy vấn:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PENDING';
```

Bộ tối ưu cần ước lượng có bao nhiêu đơn hàng mang trạng thái `PENDING`. Nếu ước lượng quá thấp, hệ quản trị có thể chọn nested loop và nhiều lần truy cập chỉ mục hoặc bảng. Nếu ước lượng quá cao, nó có thể chọn scan hoặc hash join tốn tài nguyên hơn mức cần thiết. Một ước lượng hợp lý giúp chọn đường truy cập và cách kết hợp dữ liệu phù hợp.

Các loại thông tin thống kê thường gặp:

| Thông tin | Ý nghĩa đối với bộ tối ưu |
|---|---|
| Số hàng và số trang | Quy mô bảng hoặc chỉ mục, chi phí quét và lưu trữ |
| Số giá trị phân biệt (NDV) | Ước lượng độ chọn lọc, số nhóm hoặc số kết quả phân biệt |
| Tỷ lệ null | Ước lượng điều kiện kiểm tra null và phân bố dữ liệu |
| Giá trị phổ biến (MCV) | Nhận diện giá trị xuất hiện thường xuyên |
| Histogram | Mô tả phân bố theo khoảng hoặc theo nhóm giá trị |
| Mật độ và độ chọn lọc | Ước lượng tỷ lệ hàng thỏa điều kiện |
| Thống kê nhiều cột | Mô tả một số dạng tương quan giữa các điều kiện |

Không phải hệ quản trị nào cũng lưu cùng loại thống kê hoặc dùng cùng công thức ước lượng. Tên gọi, cấu trúc histogram, số lượng bucket, cách lấy mẫu và thời điểm cập nhật khác nhau theo sản phẩm và phiên bản.

## 2. Vì sao phải lấy mẫu?

Giả sử bảng `orders` có hàng trăm triệu dòng. Để tính chính xác tần suất từng giá trị của một cột, hệ quản trị có thể phải đọc một phần rất lớn hoặc toàn bộ dữ liệu, xử lý kết quả và xây dựng cấu trúc thống kê. Nếu có nhiều bảng và nhiều cột cần thống kê, chi phí này có thể đáng kể.

Lấy mẫu giảm lượng dữ liệu phải quan sát. Hệ quản trị chọn một tập con, tính toán đặc điểm của tập con rồi dùng phương pháp thống kê để ước lượng cho toàn bảng. Mẫu càng lớn thường cung cấp nhiều thông tin hơn, nhưng chi phí đọc và xử lý cũng tăng.

Có thể hình dung đánh đổi cơ bản như sau:

| Quy mô mẫu | Chi phí thường gặp | Rủi ro về độ chính xác |
|---|---|---|
| Rất nhỏ | Thấp, thu thập nhanh | Dễ bỏ sót giá trị hiếm, histogram thiếu đại diện |
| Vừa phải | Cân bằng hơn giữa đọc và xử lý | Vẫn có sai số ở nhóm hiếm hoặc phân bố phức tạp |
| Lớn | Tốn I/O, CPU và thời gian hơn | Thường giảm biến động do lấy mẫu, nhưng không sửa được mọi sai lệch mô hình |
| Toàn bộ dữ liệu | Có thể rất tốn kém với bảng lớn | Tránh sai số do chỉ quan sát một mẫu, nhưng vẫn phụ thuộc cách xây dựng thống kê và mô hình ước lượng |

Lấy mẫu không có nghĩa là kết quả luôn thiếu chính xác. Một mẫu được chọn đúng cách có thể mô tả tốt tập dữ liệu lớn với chi phí thấp hơn nhiều so với quét toàn bộ. Ngược lại, mẫu lớn nhưng bị lệch hoặc không đại diện vẫn có thể dẫn đến kết luận sai.

## 3. Các cách lấy mẫu và nguy cơ sai lệch

### Lấy mẫu ngẫu nhiên theo hàng

Mỗi hàng có cơ hội được chọn theo quy tắc ngẫu nhiên. Nếu quy trình chọn mẫu phù hợp, mẫu có thể phản ánh phân bố tổng thể. Tuy nhiên, cần đủ số quan sát để có cơ hội gặp các giá trị hiếm.

Giả sử một trạng thái chỉ xuất hiện ở 0,1% số hàng. Nếu chọn ngẫu nhiên 1.000 hàng độc lập, xác suất không gặp giá trị đó xấp xỉ:

\[
P(\text{không gặp}) = (1 - 0,001)^{1000} \approx 36,8\%
\]

Do đó, xác suất gặp ít nhất một hàng thuộc nhóm hiếm chỉ khoảng 63,2%. Mẫu 1.000 hàng có thể đủ để ước lượng xu hướng chung nhưng vẫn bỏ lỡ một giá trị quan trọng với bộ tối ưu. Đây là ví dụ xác suất minh họa; cơ chế lấy mẫu thực tế của từng hệ quản trị có thể không độc lập theo từng hàng.

### Lấy mẫu theo trang hoặc khối dữ liệu

Một số cơ chế chọn trang hoặc khối lưu trữ thay vì chọn từng hàng độc lập. Cách này có thể giảm chi phí truy cập vì hệ quản trị đọc các đơn vị I/O tự nhiên. Tuy nhiên, nếu các giá trị được lưu gần nhau theo thời gian, tenant hoặc khóa, các trang được chọn có thể không đại diện cho toàn bộ phân bố.

Ví dụ, đơn hàng của một tenant lớn được ghi liên tục vào một vùng trang. Nếu mẫu chỉ lấy các trang ở vùng khác, tỷ lệ trạng thái của tenant lớn có thể bị đánh giá thấp. Lấy mẫu theo trang vì vậy có thể có sai số khác với lấy mẫu ngẫu nhiên theo hàng, ngay cả khi số hàng quan sát tương đương.

### Lấy mẫu phân tầng

Khi dữ liệu có các nhóm rõ ràng như partition theo tháng, tenant hoặc vùng địa lý, về mặt thiết kế có thể lấy mẫu từ từng nhóm rồi kết hợp kết quả theo trọng số của quy mô nhóm. Cách này giúp tránh việc nhóm nhỏ hoặc nhóm có cấu trúc khác biệt bị bỏ sót.

Không phải mọi lệnh thu thập thống kê của hệ quản trị đều cho phép người vận hành tự chọn lấy mẫu phân tầng. Đây là nguyên tắc thiết kế thống kê và kiểm thử; khả năng áp dụng trực tiếp phụ thuộc công cụ và nền tảng.

### Mẫu ngẫu nhiên và mẫu có thiên lệch

Mẫu có thể bị thiên lệch khi cách chọn ưu tiên một vùng, một khoảng thời gian hoặc một nhóm dữ liệu. Chẳng hạn, chỉ lấy các bản ghi mới nhất có thể bỏ qua dữ liệu lịch sử; chỉ lấy tenant hoạt động nhiều có thể không đại diện cho tenant nhỏ. Cần biết hệ quản trị lấy mẫu theo hàng, trang, phân vùng hay một phương pháp nội bộ khác trước khi diễn giải kết quả.

## 4. Kích thước mẫu và độ chính xác

Với lấy mẫu ngẫu nhiên đơn giản, sai số ngẫu nhiên thường giảm khi kích thước mẫu tăng. Một quy tắc trực giác quan trọng là sai số chuẩn thường giảm gần theo tỷ lệ nghịch với căn bậc hai của số quan sát. Muốn giảm sai số chuẩn xuống khoảng một nửa có thể cần tăng số quan sát lên khoảng bốn lần, nếu các điều kiện khác không đổi.

Quan hệ này không có nghĩa tăng mẫu bốn lần luôn làm mọi cardinality estimate chính xác gấp đôi. Sai số còn phụ thuộc vào:

- Mức độ lệch của phân bố dữ liệu.
- Số lượng giá trị phân biệt và tần suất của từng giá trị.
- Cách các giá trị được sắp xếp trên trang hoặc phân vùng.
- Tương quan giữa các cột.
- Cách hệ quản trị tạo histogram và chọn giá trị phổ biến.
- Chất lượng thống kê hiện có và mô hình cardinality của bộ tối ưu.

### Giá trị hiếm và histogram

Histogram có số bucket hữu hạn nên không thể mô tả chính xác mọi giá trị trong một cột có hàng triệu giá trị phân biệt. Giá trị xuất hiện thường xuyên có thể được lưu trong danh sách giá trị phổ biến, trong khi các giá trị còn lại được biểu diễn theo khoảng hoặc mô hình tổng quát.

Nếu một giá trị hiếm không xuất hiện trong mẫu, thống kê có thể không nhận diện được nó là trường hợp đặc biệt. Nếu giá trị đó ảnh hưởng đến một truy vấn quan trọng, kế hoạch được chọn có thể dựa trên ước lượng trung bình không phù hợp. Tăng kích thước mẫu hoặc mức chi tiết thống kê có thể giúp, nhưng cần xác định liệu vấn đề là do mẫu bỏ sót, histogram quá thô hay giả định của bộ ước lượng.

### Tương quan giữa các cột

Giả sử `tenant_id` và `status` có tương quan: một tenant có phần lớn đơn hàng đang chờ, tenant khác có phần lớn đơn hàng đã hoàn tất. Thống kê riêng từng cột có thể không đủ để ước lượng điều kiện kết hợp:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Ngay cả khi mẫu của từng cột đủ lớn, giả định hai điều kiện độc lập vẫn có thể làm sai số ước lượng lớn. Một số hệ quản trị hỗ trợ thống kê mở rộng, thống kê nhiều cột hoặc histogram theo nhóm để mô tả một phần tương quan. Hãy kiểm tra tính năng tương ứng của nền tảng đang dùng.

## 5. Đánh giá độ chính xác của ước lượng

Không nên đánh giá chất lượng thống kê chỉ bằng số hàng được lấy mẫu. Cần so sánh ước lượng mà bộ tối ưu sử dụng với số hàng thực tế của các truy vấn đại diện.

### Sai số tương đối

Với cardinality thực tế lớn hơn 0, có thể tính sai số tương đối:

\[
\text{Sai số tương đối} = \frac{|\text{Ước lượng} - \text{Thực tế}|}{\text{Thực tế}}
\]

Ví dụ, bộ tối ưu ước lượng 80.000 hàng trong khi truy vấn thực tế trả về 100.000 hàng. Sai số tương đối là 20%. Nếu ước lượng 10.000 hàng cho cùng kết quả thực tế, sai số tương đối là 90%.

### Q-error

Q-error thường được dùng để so sánh sai số ước lượng cardinality theo cả hai hướng:

\[
Q = \max\left(\frac{\text{Ước lượng}}{\text{Thực tế}},
\frac{\text{Thực tế}}{\text{Ước lượng}}\right)
\]

Với ước lượng 80.000 và thực tế 100.000, Q-error bằng 1,25. Với ước lượng 10.000 và thực tế 100.000, Q-error bằng 10. Chỉ số này đối xứng hơn sai số tương đối khi bộ tối ưu đánh giá quá cao hoặc quá thấp. Trường hợp ước lượng hoặc thực tế bằng 0 cần quy ước xử lý riêng khi tổng hợp.

Q-error lớn là tín hiệu cần điều tra, nhưng không tự động chứng minh truy vấn chậm. Một sai số lớn ở bước trung gian có thể ảnh hưởng mạnh đến join order và memory grant; một sai số lớn ở bước ít ảnh hưởng có thể không tạo khác biệt đáng kể. Hãy đối chiếu sai số với thời gian, I/O, CPU và kế hoạch thực thi.

### Kiểm tra trên nhiều truy vấn

Chọn các truy vấn đại diện cho workload: lọc theo giá trị phổ biến, lọc theo giá trị hiếm, điều kiện kết hợp nhiều cột, join lớn, truy vấn phân trang và truy vấn tổng hợp. Với mỗi truy vấn, lưu estimated rows và actual rows ở các nút quan trọng trong kế hoạch. So sánh trước/sau cập nhật thống kê và theo dõi cả độ trễ lẫn tài nguyên.

Không chỉ kiểm tra một truy vấn dùng cột vừa cập nhật. Thay đổi thống kê có thể làm bộ tối ưu chọn kế hoạch khác cho nhiều câu lệnh cùng tham chiếu bảng hoặc cột đó.

## 6. Chi phí thu thập thống kê

Chi phí thống kê không chỉ là số hàng được đọc. Một lần thu thập có thể bao gồm đọc trang dữ liệu, giải mã hàng, xây dựng histogram, đếm giá trị, tính số liệu phân biệt, xử lý thống kê chỉ mục và ghi metadata mới.

Các thành phần chi phí chính gồm:

| Thành phần | Điều gì làm chi phí tăng? | Cách theo dõi |
|---|---|---|
| I/O đọc | Bảng lớn, mẫu lớn, dữ liệu nằm trên lưu trữ chậm | Read bytes, số trang đọc, độ trễ I/O |
| CPU | Xử lý mẫu, sắp xếp, đếm và xây histogram | CPU time, mức sử dụng CPU trong lúc thu thập |
| Bộ nhớ | Số cột, số bucket, xử lý dữ liệu trung gian | Memory grant hoặc bộ nhớ tiến trình tùy hệ quản trị |
| Thời gian | Khối lượng dữ liệu và mức tải đồng thời | Thời gian bắt đầu/kết thúc, thời gian chờ |
| Tác động vận hành | Tranh chấp tài nguyên với truy vấn nghiệp vụ hoặc tác vụ bảo trì | Throughput, latency và wait của workload trong lúc thu thập |
| Dung lượng metadata | Số bảng, cột, chỉ mục và mức chi tiết thống kê | Số đối tượng thống kê, kích thước metadata nếu có |

Một mẫu nhỏ giúp giảm lượng dữ liệu đọc, nhưng nếu thống kê không đủ tốt thì truy vấn có thể chọn kế hoạch tốn kém trong nhiều giờ hoặc nhiều ngày. Vì vậy, cần so sánh chi phí thu thập với lợi ích vận hành sau đó.

### Tác động đến hệ thống đang phục vụ tải

Thu thập thống kê có thể cạnh tranh I/O và CPU với truy vấn nghiệp vụ. Tùy hệ quản trị và loại thao tác, việc cập nhật thống kê có thể cần khóa hoặc đồng bộ metadata ở một số giai đoạn. Hãy xem tài liệu của nền tảng về chế độ online, mức độ song song và hành vi khóa.

Lập lịch thu thập ngoài giờ cao điểm nếu có thể, nhưng vẫn phải cân nhắc batch nghiệp vụ, backup, rebuild index và các tác vụ bảo trì khác. Một tác vụ thống kê chạy cùng lúc với backup hoặc ETL lớn có thể làm tăng độ trễ I/O dù từng tác vụ riêng lẻ đều hợp lý.

## 7. Chọn kích thước mẫu và tần suất cập nhật

Không nên chọn một tỷ lệ mẫu cố định cho mọi bảng. Quyết định nên dựa trên quy mô bảng, độ lệch dữ liệu, mức độ thay đổi, tầm quan trọng của truy vấn và chi phí thu thập.

Có thể áp dụng quy trình sau:

1. **Đo hiện trạng:** ghi nhận thời gian thu thập thống kê, số trang đọc, CPU và ảnh hưởng lên workload.
2. **Xác định vùng dữ liệu quan trọng:** tìm các cột lọc, join, group by và các giá trị có tần suất rất khác nhau.
3. **Kiểm tra độ chính xác:** so sánh estimated rows với actual rows trên truy vấn đại diện.
4. **Tìm nguồn sai lệch:** mẫu quá nhỏ, histogram thiếu chi tiết, thống kê cũ, tương quan nhiều cột hoặc kiểu dữ liệu không phù hợp.
5. **Thử tăng mẫu hoặc mức chi tiết:** thay đổi trên môi trường kiểm thử hoặc phạm vi nhỏ, rồi đo lại cả chi phí thu thập và chất lượng kế hoạch.
6. **Đặt lịch phù hợp:** cập nhật theo tốc độ thay đổi dữ liệu và cửa sổ vận hành, không chỉ theo lịch cố định.
7. **Theo dõi hồi quy:** sau cập nhật, kiểm tra truy vấn quan trọng và workload có liên quan.

### Khi nào cần mẫu lớn hơn?

Hãy cân nhắc tăng kích thước mẫu hoặc mức chi tiết khi:

- Bảng có phân bố lệch mạnh và các giá trị hiếm ảnh hưởng đến truy vấn quan trọng.
- Estimated rows thường xuyên sai nhiều so với actual rows.
- Histogram không nhận diện được các nhóm giá trị quan trọng.
- Bảng tăng nhanh hoặc có vùng dữ liệu mới làm thay đổi phân bố.
- Truy vấn join nhiều cột có sai số ước lượng đáng kể.

### Khi nào mẫu nhỏ có thể đủ?

Mẫu nhỏ có thể phù hợp khi phân bố dữ liệu tương đối đồng đều, truy vấn không nhạy với sai số nhỏ, bảng ít thay đổi hoặc chi phí thu thập đầy đủ quá cao. Tuy nhiên, cần xác minh bằng truy vấn đại diện. Không nên suy luận rằng bảng lớn thì luôn cần mẫu nhỏ hoặc bảng nhỏ thì luôn cần quét toàn bộ.

### Tần suất cập nhật

Thống kê có thể trở nên lỗi thời sau khi thêm, xóa hoặc cập nhật nhiều dữ liệu. Một bảng giao dịch thay đổi liên tục cần cách theo dõi khác với bảng danh mục ít thay đổi. Hãy dùng số hàng thay đổi, tốc độ cập nhật dữ liệu, lịch sử sai lệch ước lượng và cơ chế auto-statistics của hệ quản trị để quyết định.

Không cập nhật quá thường xuyên nếu mỗi lần thu thập đều tốn kém và phân bố hầu như không đổi. Cũng không nên để thống kê cũ kéo dài khi dữ liệu đã thay đổi đáng kể. Mục tiêu là duy trì độ mới đủ cho các truy vấn quan trọng với chi phí hợp lý.

## 8. Cách cấu hình và kiểm tra theo hệ quản trị

Các hệ quản trị có cách điều khiển lấy mẫu khác nhau. Ví dụ dưới đây cần được điều chỉnh theo phiên bản, quyền và chính sách vận hành thực tế.

### SQL Server

SQL Server hỗ trợ thu thập thống kê với tỷ lệ mẫu chỉ định, quét toàn bộ hoặc để hệ quản trị tự chọn trong một số tình huống. Ví dụ:

```sql
-- Lấy mẫu một phần để giảm chi phí đọc.
UPDATE STATISTICS dbo.Orders IX_Orders_Status
WITH SAMPLE 20 PERCENT;

-- Quét toàn bộ dữ liệu để đối chiếu trong môi trường phù hợp.
UPDATE STATISTICS dbo.Orders IX_Orders_Status
WITH FULLSCAN;
```

Đây là ví dụ cú pháp cho SQL Server; tên bảng và chỉ mục phải tồn tại. `SAMPLE` có thể giảm chi phí nhưng độ chính xác phụ thuộc phân bố và cách chọn mẫu. `FULLSCAN` tốn tài nguyên hơn, không phải lúc nào cũng cần thiết. SQL Server cũng có cơ chế cập nhật thống kê tự động và các tùy chọn liên quan đến lấy mẫu, do đó cần xem trạng thái thống kê trước khi chạy lệnh thủ công.

Khi kiểm tra, có thể dùng thông tin thống kê trong catalog view và `DBCC SHOW_STATISTICS` để xem histogram, density và thời điểm cập nhật. Không nên chạy `UPDATE STATISTICS` hàng loạt với `FULLSCAN` trên mọi bảng lớn mà chưa đánh giá tác động.

### PostgreSQL

PostgreSQL dùng `ANALYZE` để thu thập thống kê. Người vận hành thường điều chỉnh mức thống kê mục tiêu theo cột bằng `ALTER TABLE ... SET STATISTICS`. Giá trị mục tiêu cao hơn cho phép lưu nhiều thông tin hơn trong histogram và danh sách giá trị phổ biến, đồng thời thường làm mẫu thu thập lớn hơn. Đây không phải cú pháp chỉ định trực tiếp phần trăm mẫu.

```sql
-- Tăng mức chi tiết thống kê cho cột thường được lọc.
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

-- Thu thập lại thống kê cho bảng.
ANALYZE orders;
```

Giá trị `500` chỉ là ví dụ để minh họa. Mức mặc định thường đủ cho nhiều cột; chỉ tăng khi đo được sai lệch ước lượng và có lợi ích rõ ràng. Có thể xem thông tin thống kê trong `pg_stats`, gồm histogram bounds, most common values và số giá trị phân biệt ước lượng.

Nếu điều kiện lọc kết hợp có tương quan giữa các cột, hãy tìm hiểu extended statistics thay vì chỉ tăng target cho từng cột riêng lẻ. Việc tạo thống kê mở rộng không thay thế việc kiểm tra kế hoạch và số hàng thực tế.

### Oracle Database

Oracle cung cấp `DBMS_STATS` để thu thập thống kê bảng, cột và chỉ mục. `DBMS_STATS.AUTO_SAMPLE_SIZE` cho phép Oracle tự chọn kích thước mẫu phù hợp theo cơ chế của phiên bản. Ví dụ:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'SALES',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

Tên schema và bảng trong ví dụ cần được thay bằng đối tượng thực tế. `AUTO_SAMPLE_SIZE` thường là lựa chọn nên xem xét trước khi tự đặt một tỷ lệ cố định. `method_opt` quyết định cách thu thập histogram; histogram chỉ nên được tạo khi có lợi cho ước lượng và workload. Cần theo dõi thời gian thu thập, trạng thái thống kê và tác động của việc thay đổi histogram lên kế hoạch.

### MySQL và InnoDB

MySQL có thống kê chỉ mục của InnoDB và, ở các phiên bản hỗ trợ, histogram cho cột. Việc thu thập thống kê InnoDB có thể lấy mẫu các trang dữ liệu; số trang mẫu được điều khiển bởi các thiết lập như `innodb_stats_persistent_sample_pages` hoặc tùy chọn cấp bảng `STATS_SAMPLE_PAGES`, tùy phiên bản và cấu hình.

```sql
-- Thu thập lại thống kê của bảng.
ANALYZE TABLE orders;

-- Với phiên bản hỗ trợ histogram, cập nhật histogram cho cột.
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 64 BUCKETS;
```

Số bucket `64` chỉ là ví dụ. Histogram giúp mô tả phân bố cột cho bộ tối ưu nhưng không thay thế mọi loại thống kê chỉ mục. Hãy kiểm tra tài liệu đúng phiên bản về cách lấy mẫu trang, độ bền thống kê, histogram và phạm vi áp dụng trước khi thay đổi biến hệ thống.

## 9. Ví dụ điều tra thống kê chưa đủ chính xác

Giả sử truy vấn lọc đơn hàng theo `status` thường chạy tốt nhưng chậm rõ rệt sau khi dữ liệu tăng. Actual execution plan cho thấy:

| Chỉ số | Trước cập nhật thống kê | Sau cập nhật thống kê |
|---|---:|---:|
| Estimated rows | 8.000 | 95.000 |
| Actual rows | 100.000 | 100.000 |
| Q-error | 12,5 | khoảng 1,05 |
| Logical reads | 18.000 | 6.500 |
| Elapsed time | 1.200 ms | 420 ms |

Các số liệu trên là ví dụ minh họa, không phải cam kết rằng cập nhật thống kê sẽ tạo ra mức cải thiện như vậy. Trong tình huống này, thống kê mới giúp bộ tối ưu ước lượng gần hơn với số hàng thực tế và chọn kế hoạch phù hợp hơn.

Quy trình điều tra cần xác nhận thêm:

1. Thống kê cũ được thu thập khi nào và bảng đã thay đổi bao nhiêu kể từ đó?
2. Mẫu cũ có bỏ sót giá trị phổ biến hoặc vùng dữ liệu mới không?
3. Histogram sau cập nhật có mô tả được phân bố cần quan tâm không?
4. Kế hoạch thực thi có thay đổi và thay đổi đó có giải thích được mức giảm logical reads không?
5. Các truy vấn khác dùng cùng thống kê có bị chậm hơn không?
6. Chi phí thu thập mới có chấp nhận được khi chạy trong cửa sổ vận hành dự kiến không?

Nếu ước lượng vẫn sai sau khi tăng mẫu, hãy kiểm tra tương quan nhiều cột, biểu thức lọc, kiểu dữ liệu, partition và giới hạn của mô hình cardinality. Tăng mẫu liên tục mà không xác định nguyên nhân có thể chỉ làm tăng chi phí bảo trì.

## 10. Những sai lầm thường gặp

1. **Cho rằng mẫu càng lớn luôn càng tốt:** độ chính xác tăng có thể không đáng với chi phí I/O và CPU.
2. **Chọn tỷ lệ mẫu giống nhau cho mọi bảng:** bảng có phân bố, kích thước và tốc độ thay đổi khác nhau.
3. **Chỉ nhìn số hàng mẫu:** cần đánh giá estimated rows, actual rows và chất lượng kế hoạch.
4. **Bỏ qua dữ liệu lệch:** mẫu ngẫu nhiên nhỏ có thể không gặp giá trị hiếm hoặc vùng dữ liệu quan trọng.
5. **Không xét cách lấy mẫu theo trang:** các trang có thể tập trung theo thời gian, tenant hoặc khóa.
6. **Chỉ cập nhật thống kê đơn cột:** điều kiện nhiều cột có tương quan vẫn có thể ước lượng sai.
7. **Thu thập quá thường xuyên:** thống kê có thể không thay đổi đáng kể nhưng vẫn tiêu thụ tài nguyên.
8. **Dùng FULLSCAN trên mọi bảng:** quét toàn bộ có thể làm tăng I/O, CPU và ảnh hưởng workload.
9. **Không kiểm tra kế hoạch sau cập nhật:** thống kê mới có thể làm thay đổi kế hoạch theo hướng không mong muốn.
10. **Áp dụng cùng một cú pháp cho mọi hệ quản trị:** SQL Server, PostgreSQL, Oracle và MySQL có cơ chế và tham số lấy mẫu khác nhau.

## 11. Danh sách kiểm tra khi thiết kế thu thập thống kê

- [ ] Đã xác định bảng, cột, chỉ mục và truy vấn quan trọng cần thống kê.
- [ ] Đã xem xét độ lệch dữ liệu, giá trị hiếm, phân bố theo vùng và tương quan nhiều cột.
- [ ] Đã hiểu hệ quản trị lấy mẫu theo hàng, trang hoặc cơ chế nội bộ nào.
- [ ] Đã đo chi phí I/O, CPU, bộ nhớ và thời gian của lần thu thập hiện tại.
- [ ] Đã so sánh estimated rows với actual rows trên các truy vấn đại diện.
- [ ] Đã chọn kích thước mẫu hoặc mức chi tiết phù hợp với mức sai số chấp nhận được.
- [ ] Đã xem xét cơ chế auto-statistics và lịch cập nhật của hệ quản trị.
- [ ] Đã kiểm tra thống kê nhiều cột khi workload có điều kiện lọc tương quan.
- [ ] Đã thử nghiệm cập nhật thống kê trong điều kiện tải có kiểm soát.
- [ ] Đã xác nhận kế hoạch, độ trễ, throughput và tài nguyên sau cập nhật.

Thu thập thống kê bằng lấy mẫu là bài toán cân bằng giữa chi phí quan sát và chất lượng ước lượng. Mẫu nhỏ giúp giảm I/O, CPU và thời gian bảo trì nhưng có thể bỏ sót giá trị hiếm hoặc không đại diện cho dữ liệu lệch. Mẫu lớn và thống kê chi tiết hơn có thể cải thiện cardinality estimate, song vẫn cần kiểm tra tương quan giữa các cột và giới hạn của mô hình tối ưu. Hãy chọn chiến lược theo đặc điểm workload, kiểm chứng bằng actual execution plan và số liệu vận hành, đồng thời sử dụng đúng cơ chế lấy mẫu của từng hệ quản trị.
