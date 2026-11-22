# Chẩn đoán chênh lệch số hàng ước lượng với số hàng thực tế

Optimizer phải dự đoán số hàng đi qua từng bước của truy vấn trước khi chọn cách đọc dữ liệu, thứ tự join, thuật toán kết hợp và lượng bộ nhớ cần dùng. Khi số hàng thực tế khác xa số hàng ước lượng, kế hoạch có thể thực hiện nhiều công việc hơn dự kiến: Nested Loop lặp quá nhiều lần, Hash Join cần nhiều batch, Sort tràn ra đĩa hoặc truy vấn đọc lượng dữ liệu lớn hơn nhiều so với dự báo.

Trong tối ưu hiệu năng cơ sở dữ liệu, chênh lệch giữa **estimated rows** và **actual rows** là một trong những manh mối quan trọng để tìm nguyên nhân kế hoạch kém hiệu quả. Tuy nhiên, không phải mọi chênh lệch đều gây vấn đề, và không phải mọi truy vấn chậm đều bắt nguồn từ thống kê. Cần tìm đúng nút đầu tiên có sai lệch, hiểu cách dữ liệu được lọc và kết hợp, rồi xác minh giả thuyết bằng thống kê, kế hoạch thực tế và phép đo dưới tải phù hợp.

## 1. Estimated rows và actual rows là gì?

**Estimated rows** là số hàng optimizer dự đoán một toán tử sẽ phát ra trong kế hoạch. Dự đoán này được tính từ thống kê, điều kiện truy vấn, ràng buộc, tham số và mô hình ước lượng của hệ quản trị.

**Actual rows** là số hàng toán tử thực sự phát ra khi câu lệnh chạy và công cụ thu thập được kế hoạch thực tế. Giá trị này phụ thuộc dữ liệu tại thời điểm chạy, tham số đầu vào và điều kiện thực thi.

Ví dụ, một truy vấn lọc `orders` theo `status = 'OPEN'` có:

```text
Index Scan on orders
  estimated rows = 100
  actual rows    = 25,000
```

Optimizer dự đoán 100 hàng nhưng toán tử thực tế phát ra 25.000 hàng, tức gấp 250 lần. Nếu toán tử này nằm ở đầu vào của join, các bước phía trên có thể phải xử lý lượng dữ liệu lớn hơn nhiều so với dự kiến.

Estimated rows là dự đoán, không phải cam kết. Actual rows cũng không tự giải thích nguyên nhân: nó cho biết điều gì đã xảy ra trong lần chạy đo được, còn việc tìm lý do cần đọc các nút con, điều kiện lọc, thống kê và bối cảnh truy vấn.

## 2. Vì sao sai lệch cardinality ảnh hưởng đến kế hoạch?

Cardinality là số hàng tại một điểm trong kế hoạch, chẳng hạn sau scan, filter, join hoặc aggregate. Optimizer dùng cardinality để ước lượng chi phí và so sánh các phương án thực thi.

Một số quyết định dễ bị ảnh hưởng:

- **Thứ tự join:** optimizer có thể bắt đầu từ bảng được dự đoán nhỏ nhất. Nếu bảng đó thực tế lớn hơn nhiều, thứ tự join có thể tạo ra tập trung gian lớn.
- **Nested Loop:** nếu nhánh ngoài có nhiều hàng hơn dự kiến, nhánh trong có thể bị gọi hàng nghìn hoặc hàng triệu lần.
- **Hash Join:** nếu đầu vào lớn hơn dự đoán, bảng băm có thể cần nhiều bộ nhớ hoặc chia thành nhiều batch, thậm chí ghi dữ liệu tạm ra đĩa.
- **Sort và Aggregate:** số hàng hoặc độ rộng hàng lớn hơn dự kiến làm tăng bộ nhớ cần thiết, thời gian sắp xếp và khả năng spill.
- **Parallel execution:** ước lượng thấp có thể khiến optimizer không chọn song song hóa khi nó có ích; ước lượng cao cũng có thể dẫn đến chi phí điều phối không cần thiết.
- **Lựa chọn chỉ mục hoặc scan:** nếu dự đoán tỷ lệ hàng trả về sai, optimizer có thể đánh giá sai giữa truy cập chỉ mục và quét tuần tự.

Ví dụ, Nested Loop có thể rất hiệu quả khi nhánh ngoài trả 20 hàng và mỗi lần tra cứu nhánh trong chỉ đọc vài hàng. Nếu nhánh ngoài thực tế trả 200.000 hàng, cùng kế hoạch có thể tạo ra số lần truy cập rất lớn. Sai lệch tại nút scan đầu tiên có thể là nguyên nhân sâu xa của chi phí ở nút join phía trên.

## 3. Đọc kế hoạch từ dưới lên và tìm nút sai lệch đầu tiên

Khi điều tra, hãy bắt đầu từ các nút lá và lần theo dữ liệu lên nút gốc. Với mỗi toán tử, ghi lại:

1. Số hàng ước lượng.
2. Số hàng thực tế.
3. Số lần thực thi hoặc `loops`.
4. Điều kiện truy cập và điều kiện lọc.
5. Thời gian, buffer/I/O, số hàng bị loại và dấu hiệu dùng dữ liệu tạm nếu công cụ cung cấp.

Nút đầu tiên có sai lệch lớn thường đáng chú ý hơn nút phía trên chỉ phản ánh sai lệch đã tích lũy từ đầu vào. Ví dụ:

```text
Hash Join  (estimated rows=500, actual rows=48,000)
  -> Seq Scan on customers
       (estimated rows=100, actual rows=12,000)
       Filter: region = 'NORTH'
  -> Index Scan on orders
       (estimated rows=50,000, actual rows=52,000)
       Index Cond: customer_id = customers.id
```

Trong ví dụ, ước lượng của `orders` tương đối gần thực tế. Sai lệch lớn đã xuất hiện ở `customers`: optimizer dự đoán 100 hàng sau điều kiện `region`, nhưng thực tế có 12.000 hàng. Hash Join nhận đầu vào lớn hơn dự kiến và tạo kết quả nhiều hơn dự đoán. Cần điều tra thống kê và phân phối của `customers.region` trước khi kết luận thuật toán join là nguyên nhân.

### Đừng chỉ nhìn nút gốc

Nút gốc cho biết sai lệch tổng thể của kết quả, nhưng thường không cho biết nó bắt đầu ở đâu. Nếu một filter sai lệch rồi join tiếp tục nhân số hàng, chỉ sửa bước join có thể che dấu nguyên nhân. Hãy tìm nút đầu tiên từ dưới lên mà estimated rows khác actual rows đáng kể.

### Phân biệt sai lệch ở một nút với sai lệch lan truyền

Một toán tử cha có thể sai vì một hoặc nhiều toán tử con đã trả số hàng khác dự đoán. Nếu các nút con đều gần đúng nhưng join vẫn sai, hãy điều tra cách ước lượng quan hệ giữa hai đầu vào, độ duy nhất của khóa join, dữ liệu trùng và ràng buộc. Với phép join, số hàng kết quả không chỉ phụ thuộc số hàng của hai bảng mà còn phụ thuộc số khóa khớp và số lần mỗi khóa xuất hiện.

## 4. Định lượng mức sai lệch

Có thể dùng tỷ số giữa số hàng thực tế và ước lượng để sàng lọc các nút cần điều tra:

\[
R=\frac{\text{Actual rows}}{\text{Estimated rows}}
\]

- `R` lớn hơn 1: thực tế nhiều hàng hơn dự đoán.
- `R` nhỏ hơn 1: thực tế ít hàng hơn dự đoán.
- `R` gần 1: dự đoán tương đối sát.

Ví dụ estimated rows = 400 và actual rows = 20.000 thì `R = 50`, nghĩa là thực tế gấp 50 lần ước lượng. Nếu estimated rows = 40.000 và actual rows = 800 thì `R = 0,02`, nghĩa là thực tế chỉ bằng 2% dự đoán.

Khi estimated rows có thể bằng 0 hoặc rất nhỏ, tỷ số đơn giản trở nên khó diễn giải. Có thể dùng sai số tuyệt đối, sai số theo logarit hoặc chỉ báo chênh lệch theo bậc độ lớn. Một thước đo thường gặp trong nghiên cứu optimizer là Q-error:

\[
Q=\max\left(\frac{E}{A},\frac{A}{E}\right)
\]

Trong đó `E` là estimated cardinality và `A` là actual cardinality; với công thức này cần quy ước xử lý giá trị 0 để tránh chia cho 0. Q-error bằng 1 khi ước lượng khớp hoàn toàn, càng lớn thì sai lệch theo bội số càng cao. Đây là chỉ báo định lượng, không thay thế việc xem số hàng tuyệt đối và chi phí của toán tử.

Không có một ngưỡng sai lệch duy nhất phù hợp cho mọi hệ thống. Sai lệch 10 lần ở một nút chỉ trả 1 hàng có thể ít quan trọng hơn sai lệch 2 lần ở nút xử lý hàng chục triệu bản ghi. Hãy kết hợp tỷ lệ sai lệch với số hàng, số vòng lặp, thời gian, I/O và vị trí của nút trong cây.

## 5. Hiểu đúng `loops` và số hàng thực tế

Một số công cụ hiển thị số hàng trung bình mỗi lần thực thi khi toán tử chạy nhiều vòng. Trong PostgreSQL, khi `loops` lớn hơn 1, `actual rows` và `actual time` thường được hiển thị dưới dạng trung bình cho mỗi vòng lặp. Vì vậy, để ước lượng tổng số hàng được phát ra qua mọi vòng, có thể nhân `actual rows × loops`; cần nhớ số hiển thị có thể đã làm tròn.

Ví dụ:

```text
Nested Loop  (actual rows=10,000 loops=1)
  -> Index Scan on customers
       (actual rows=5,000 loops=1)
  -> Index Scan on orders_customer_idx
       (actual rows=2 loops=5,000)
```

Nhánh trong trả trung bình 2 hàng mỗi vòng và chạy 5.000 vòng, tức phát ra khoảng 10.000 hàng. Nếu chỉ nhìn `actual rows=2`, người đọc có thể đánh giá thấp công việc của nhánh trong. Khi so sánh estimated và actual, hãy xác định công cụ hiển thị estimated rows theo mỗi lần hay theo tổng, rồi dùng quy ước nhất quán.

Số vòng lặp lớn không tự động chứng minh kế hoạch xấu. Nếu mỗi vòng là một index lookup rẻ và nhánh ngoài nhỏ, Nested Loop có thể là lựa chọn tốt. Nếu mỗi vòng phải quét một vùng dữ liệu lớn, tổng công việc có thể rất cao. Hãy đối chiếu loại toán tử, số vòng, lượng dữ liệu đọc và thời gian.

## 6. Nhóm nguyên nhân thường gây sai lệch

### 6.1. Thống kê cũ hoặc chưa đủ đại diện

Thống kê có thể không còn phản ánh dữ liệu sau khi tải mới, xóa hàng loạt, migration hoặc thay đổi phân phối. Một bảng tăng gấp nhiều lần nhưng thống kê chưa được cập nhật có thể làm optimizer dự đoán số hàng thấp. Với bảng có giá trị lệch mạnh, lấy mẫu nhỏ có thể bỏ sót các giá trị phổ biến hoặc vùng dữ liệu bất thường.

Kiểm tra thời điểm thu thập thống kê, số hàng được lấy mẫu, số hàng hiện tại, cơ chế tự động cập nhật và tần suất thay đổi dữ liệu. Việc cập nhật thống kê cần tuân theo cơ chế của hệ quản trị; không giả định một câu lệnh `ANALYZE` có cùng hành vi hoặc phạm vi trên mọi sản phẩm.

### 6.2. Phân phối dữ liệu lệch và giá trị phổ biến

NDV cho biết số giá trị phân biệt, nhưng không nói mỗi giá trị xuất hiện bao nhiêu lần. Nếu optimizer giả định các giá trị phân bố đều, nó có thể đánh giá thấp một giá trị phổ biến hoặc đánh giá cao một giá trị hiếm.

Ví dụ, cột `status` có 5 giá trị khác nhau. Một giá trị `ACTIVE` chiếm 85% hàng, bốn giá trị còn lại chia nhau 15%. Giả định đều sẽ dự đoán mỗi giá trị chiếm 20%, dẫn đến sai lệch lớn với điều kiện `status = 'ACTIVE'`.

Kiểm tra thống kê MCV (most common values), histogram và độ chọn lọc thực tế của giá trị được truy vấn. Nếu phân phối lệch thay đổi thường xuyên, cần đánh giá tần suất cập nhật thống kê và cách optimizer mô hình hóa giá trị ngoài danh sách phổ biến.

### 6.3. Tương quan giữa nhiều cột

Optimizer có thể ước lượng từng điều kiện riêng rồi kết hợp chúng theo giả định độc lập. Nhưng các cột nghiệp vụ thường có quan hệ: `country_code` và `postal_code`, `status` và `closed_at`, `tenant_id` và `region_id`, hoặc `priority` và `assigned_to`.

Ví dụ:

```sql
SELECT ticket_id
FROM tickets
WHERE priority = 'URGENT'
  AND assigned_to IS NULL;
```

Nếu 8% ticket là khẩn cấp và 25% ticket chưa được phân công, giả định độc lập dự đoán 2% tổng bảng thỏa cả hai điều kiện. Nhưng nếu 60% ticket khẩn cấp chưa được phân công, tỷ lệ kết hợp thực tế là 4,8% tổng bảng. Sai lệch có thể lớn hơn hai lần.

Kiểm tra thống kê nhiều cột hoặc extended statistics nếu hệ quản trị hỗ trợ. Với PostgreSQL, extended statistics có thể mô tả NDV của tổ hợp, phụ thuộc giữa các cột và tổ hợp giá trị phổ biến. Chúng cải thiện một số ước lượng nhưng không mô tả mọi quan hệ hay áp dụng cho mọi dạng biểu thức.

### 6.4. Histogram và điều kiện theo khoảng

Điều kiện như `created_at >= ...`, `price BETWEEN ...` hoặc `score > ...` phụ thuộc phân phối giá trị. Nếu histogram quá thưa, dữ liệu tập trung ở một số khoảng hoặc có nhiều giá trị mới nằm ngoài phạm vi thống kê, ước lượng có thể sai.

Kiểm tra biên histogram, số bucket, giá trị ngoài phạm vi và cách hệ quản trị xử lý giá trị mới. Tăng statistics target hoặc mức lấy mẫu có thể giúp mô tả chi tiết hơn, nhưng cũng làm tăng chi phí thu thập và lưu trữ.

### 6.5. NULL và điều kiện ba giá trị

Điều kiện `column IS NULL` hoặc `column IS NOT NULL` phụ thuộc tỷ lệ NULL. Với so sánh bằng thông thường, hàng có NULL không thỏa điều kiện theo logic SQL. Nếu tỷ lệ NULL thay đổi đáng kể mà thống kê chưa cập nhật, số hàng sau filter có thể bị dự đoán sai.

Kiểm tra `null_frac`, quy tắc nghiệp vụ về NULL và sự khác biệt giữa `COUNT(*)` với `COUNT(column)`. Đừng coi NULL như một giá trị mặc định hoặc chuỗi rỗng.

### 6.6. Join, khóa trùng và ràng buộc

Ước lượng join phụ thuộc số hàng mỗi phía, NDV của khóa join, số giá trị trùng và các ràng buộc duy nhất/khóa ngoại. Nếu khóa phía được giả định là duy nhất nhưng thực tế có nhiều bản ghi trùng, kết quả join có thể lớn hơn dự đoán.

Kiểm tra ràng buộc `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, dữ liệu trùng, NULL ở khóa và điều kiện join có áp dụng hàm hoặc ép kiểu hay không. Một phép join không dùng đúng kiểu dữ liệu hoặc biểu thức có thể làm optimizer khó sử dụng thống kê và chỉ mục dự kiến.

### 6.7. Biểu thức, ép kiểu và hàm trên cột

Điều kiện như `LOWER(email) = ...`, `DATE(created_at) = ...` hoặc so sánh hai kiểu dữ liệu khác nhau có thể khiến thống kê cột gốc không mô tả đúng biểu thức được lọc. Tùy hệ quản trị, optimizer có thể không dùng chỉ mục thông thường hoặc không có thống kê phù hợp cho biểu thức.

Kiểm tra kiểu dữ liệu hai vế, implicit cast, hàm được gọi, collation và khả năng dùng expression index hoặc computed column. Trước khi sửa SQL, xác nhận thay đổi giữ nguyên ngữ nghĩa, múi giờ, collation và quy tắc NULL.

### 6.8. Tham số và kế hoạch dùng lại

Một câu SQL có thể chạy với tham số rất khác nhau. `status='ACTIVE'` có thể trả 85% bảng, còn `status='PENDING_REVIEW'` chỉ trả 0,01%. Một kế hoạch được tối ưu cho giá trị này có thể không phù hợp với giá trị kia.

Một số hệ quản trị hoặc cơ chế driver sử dụng prepared statement và tái sử dụng kế hoạch; có thể có kế hoạch tổng quát hoặc kế hoạch chuyên biệt theo tham số. Cách lựa chọn phụ thuộc sản phẩm, phiên bản, cấu hình và driver. Hãy kiểm tra kế hoạch với nhiều nhóm tham số đại diện, đặc biệt giá trị phổ biến, hiếm và NULL nếu được phép.

### 6.9. Thống kê phân vùng hoặc dữ liệu mới

Trong bảng phân vùng, optimizer có thể dùng thống kê toàn cục hoặc thống kê riêng từng phân vùng tùy hệ quản trị. Một phân vùng mới có thể chứa phân phối khác rõ rệt so với các phân vùng cũ. Nếu thống kê không được thu thập hoặc tổng hợp đúng, ước lượng sau partition pruning hoặc trên toàn bảng có thể sai.

Kiểm tra phân vùng được truy cập, thống kê của từng phân vùng và thống kê tổng hợp. Với bảng tăng theo thời gian, dữ liệu của phân vùng mới nhất thường có phân phối khác các khoảng lịch sử.

## 7. Quy trình chẩn đoán theo từng bước

Một quy trình có thể lặp lại giúp phân biệt nguyên nhân thay vì thay đổi chỉ mục hoặc cấu hình theo cảm tính.

### Bước 1: Chọn truy vấn và tham số đại diện

Chọn truy vấn từ thống kê tải hoặc trace dựa trên tổng thời gian tiêu tốn, p95/p99, tần suất và mức độ ảnh hưởng nghiệp vụ. Ghi lại fingerprint truy vấn, phiên bản ứng dụng, tham số, thời điểm, số lần chạy và điều kiện dữ liệu. Một truy vấn chạy 1 lần với tham số hiếm không đại diện cho workload chạy hàng nghìn lần với tham số phổ biến.

### Bước 2: Thu thập estimated và actual plan

Lưu kế hoạch ước lượng và kế hoạch thực tế nếu hệ quản trị hỗ trợ. Với PostgreSQL, có thể dùng `EXPLAIN` và `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn đọc trong môi trường phù hợp. `EXPLAIN ANALYZE` thực thi câu lệnh; cần cân nhắc chi phí và tác dụng phụ, đặc biệt với DML hoặc hàm có side effect.

Không so sánh kế hoạch được tạo từ các tham số, dữ liệu, cấu hình hoặc trạng thái cache khác nhau mà không ghi lại khác biệt đó. Nếu đo trên môi trường production, tuân thủ quy trình vận hành và đánh giá tác động trước.

### Bước 3: Đánh dấu các nút sai lệch

Đọc từ nút lá lên gốc. Tạo bảng ghi nhận ngắn:

| Nút | Estimated rows | Actual rows | Loops | Sai lệch sơ bộ | Ghi chú |
|---|---:|---:|---:|---:|---|
| Filter `customers.region` | 100 | 12.000 | 1 | 120 lần | Sai lệch bắt đầu ở filter |
| Index lookup `orders` | 20 | 18 | 12.000 | Gần đúng mỗi vòng | Nhiều lần gọi do nhánh ngoài |
| Join result | 2.000 | 216.000 | 1 | 108 lần | Sai lệch tích lũy |

Các con số trên chỉ là ví dụ minh họa. Với toán tử lặp, phải hiểu actual rows được hiển thị mỗi vòng hay tổng cộng. Không kết luận từ phép chia nếu hai đại lượng không cùng đơn vị.

### Bước 4: Tìm nguyên nhân tại nút đầu tiên

Xem điều kiện filter hoặc join, thống kê liên quan, phân phối dữ liệu và tham số. Phân loại nguyên nhân: thống kê cũ, lệch phân phối, tương quan nhiều cột, NULL, join key không duy nhất, biểu thức/ép kiểu, phân vùng hoặc parameter sensitivity.

### Bước 5: Đặt giả thuyết và chọn phép kiểm tra nhỏ nhất

Ví dụ: “Optimizer ước lượng thấp số hàng `region='NORTH'` vì MCV không phản ánh dữ liệu mới.” Kiểm tra thời điểm thống kê và tần suất giá trị trong một mẫu đại diện. Hoặc: “Ước lượng filter kết hợp thấp vì `status` và `closed_at` tương quan.” Kiểm tra thống kê nhiều cột và tỷ lệ giao nhau. Mỗi giả thuyết nên có một phép đo có thể bác bỏ hoặc xác nhận.

### Bước 6: Chọn biện pháp tương ứng

Tùy nguyên nhân, có thể:

- Cập nhật thống kê hoặc điều chỉnh tần suất auto analyze.
- Tăng statistics target cho cột có phân phối lệch hoặc cần histogram chi tiết hơn.
- Tạo thống kê nhiều cột hoặc thống kê biểu thức nếu hệ quản trị hỗ trợ.
- Sửa kiểu dữ liệu hoặc biểu thức SQL để tránh ép kiểu không cần thiết.
- Điều chỉnh điều kiện lọc hoặc cách join nhưng phải giữ nguyên kết quả nghiệp vụ.
- Thiết kế chỉ mục phù hợp với mẫu truy vấn, sau khi xác nhận lợi ích truy cập.
- Xem xét chiến lược kế hoạch theo tham số nếu cùng truy vấn có phân phối tham số rất khác nhau.

Không áp dụng nhiều thay đổi cùng lúc nếu chưa có lý do rõ ràng. Khi thay đổi từng yếu tố, ta dễ xác định điều gì đã cải thiện hoặc làm xấu kế hoạch.

### Bước 7: Đo lại và theo dõi workload

Chạy lại cùng truy vấn với cùng nhóm tham số và điều kiện tải tương đương. So sánh estimated rows, actual rows, join order, loops, thời gian, buffer reads, I/O, CPU, sort/hash spill và độ trễ p95/p99. Đồng thời theo dõi các truy vấn liên quan, thao tác ghi và dung lượng chỉ mục. Một thay đổi có thể cải thiện truy vấn đơn lẻ nhưng làm tăng chi phí ghi hoặc ảnh hưởng workload khác.

## 8. Ví dụ: thống kê cũ làm optimizer đánh giá thấp một giá trị mới

Giả sử bảng `orders` có 10 triệu hàng. Trước đây, `status='PENDING'` chỉ chiếm 1% dữ liệu. Sau một thay đổi nghiệp vụ, nhiều đơn hàng chuyển sang trạng thái `PENDING` và tỷ lệ hiện tại tăng lên 25%, nhưng thống kê chưa được cập nhật.

Truy vấn:

```sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00';
```

Giả sử optimizer ước lượng điều kiện `status` trả 100.000 hàng, trong khi thực tế có 2.500.000 hàng trước khi xét điều kiện thời gian. Nhánh truy cập có thể được đánh giá là nhỏ và được đưa vào Nested Loop hoặc một kế hoạch có nhiều thao tác tra cứu lặp. Khi chạy, số hàng lớn làm tăng số vòng lặp, I/O và thời gian.

Quy trình điều tra:

1. Xác nhận actual rows và estimated rows tại filter `status`.
2. Xem thống kê MCV, histogram và thời điểm thu thập gần nhất.
3. Đo tỷ lệ hiện tại của `PENDING` trên môi trường phù hợp; đối chiếu với thống kê đã lưu.
4. Cập nhật thống kê theo cơ chế của hệ quản trị.
5. Thu thập lại kế hoạch và xem optimizer có chọn scan/join phù hợp hơn không.
6. Đo độ trễ, I/O, CPU và tác động tới các trạng thái khác.

Nếu thống kê mới vẫn không mô tả tốt dữ liệu do lấy mẫu hoặc giá trị lệch, hãy đánh giá tăng mức thống kê cho cột đó. Nếu truy vấn có thêm điều kiện tương quan theo thời gian, có thể cần histogram phù hợp hoặc thống kê bổ sung. Không nên mặc định thêm chỉ mục là cách sửa đầu tiên: khi 25% bảng cần đọc, quét tuần tự có thể vẫn là lựa chọn hợp lý.

## 9. Ví dụ: tương quan cột làm sai ước lượng join

Một hệ thống nhiều tenant có bảng `users` và `orders`. Mỗi `tenant_id` có tập người dùng riêng. Truy vấn lấy đơn hàng của một tenant ở một khu vực:

```sql
SELECT o.order_id
FROM users AS u
JOIN orders AS o ON o.user_id = u.user_id
WHERE u.tenant_id = 77
  AND u.region_id = 3;
```

Nếu optimizer ước lượng `tenant_id=77` và `region_id=3` độc lập, nó có thể dự đoán số người dùng thấp hoặc cao hơn thực tế. Sai lệch ở `users` tiếp tục ảnh hưởng số lần tra cứu `orders` và số hàng sau join.

Các bước kiểm tra:

- Xem NDV và phân phối của `tenant_id`, `region_id`.
- Xác định một tenant có thể thuộc bao nhiêu region và dữ liệu có tương quan ra sao.
- Kiểm tra ràng buộc, khóa join và số hàng trùng của `user_id`.
- Kiểm tra thống kê nhiều cột hoặc thống kê tổ hợp có thể mô tả mối quan hệ.
- Đánh giá chỉ mục `(tenant_id, region_id)` trên `users` hoặc chỉ mục join trên `orders` nếu mẫu truy vấn và workload biện minh.
- So sánh actual rows ở filter `users` và join sau điều chỉnh.

Ví dụ này nhấn mạnh rằng sai lệch ở join có thể bắt nguồn từ thống kê filter trên bảng đầu vào. Hãy tìm nơi sai lệch bắt đầu trước khi thay đổi thuật toán join.

## 10. Khác biệt giữa các hệ quản trị

Khái niệm estimated/actual cardinality có ở nhiều hệ quản trị, nhưng tên trường và cách thu thập khác nhau:

| Hệ quản trị | Công cụ thường dùng | Nội dung cần xem |
|---|---|---|
| PostgreSQL | `EXPLAIN`, `EXPLAIN ANALYZE`, `BUFFERS`, `pg_stats`, extended statistics | `rows`, `actual rows`, `loops`, `null_frac`, `n_distinct`, MCV, histogram và sai lệch giữa các nút |
| MySQL | `EXPLAIN`, `EXPLAIN FORMAT=TREE`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ, `ANALYZE TABLE` | `rows` ước lượng, actual rows/loops trong iterator plan, access type, key và histogram khi có |
| SQL Server | Estimated/Actual Execution Plan, `SET STATISTICS XML`, `DBCC SHOW_STATISTICS` | Estimated/Actual Number of Rows, Actual Number of Executions, histogram, density, statistics date và cảnh báo spill |

Đối với SQL Server, execution plan có thể hiển thị chênh lệch estimated/actual tại từng operator và số lần thực thi. Đối với MySQL, cần kiểm tra phiên bản hỗ trợ `EXPLAIN ANALYZE` và định dạng đầu ra. Với PostgreSQL, chú ý quy ước `actual rows` theo `loops`. Không áp dụng nguyên xi tên trường hoặc cách diễn giải của một sản phẩm cho sản phẩm khác.

## 11. Cảnh báo khi dùng kế hoạch thực tế

Kế hoạch thực tế cần chạy câu lệnh để thu thập số liệu. Trong PostgreSQL, `EXPLAIN ANALYZE` thực thi câu lệnh. Với truy vấn đọc, nó vẫn tiêu thụ CPU, bộ nhớ và I/O; truy vấn nặng có thể làm tăng tải. Với DML, câu lệnh có thể thay đổi dữ liệu. Rollback không bảo đảm đảo ngược mọi tác dụng phụ bên ngoài cơ sở dữ liệu, chẳng hạn gọi dịch vụ ngoài từ hàm.

Trước khi đo:

- Chọn môi trường và cửa sổ tải phù hợp.
- Dùng tham số đại diện và ghi rõ giá trị hoặc nhóm phân phối tham số.
- Đánh giá thời gian chạy và lượng dữ liệu có thể đọc.
- Tránh chạy DML có tác dụng phụ trên production chỉ để lấy actual plan.
- Nếu cần đo truy vấn nặng trên production, tuân thủ quy trình phê duyệt và giới hạn tài nguyên của hệ thống.
- Lưu lại phiên bản hệ quản trị, cấu hình liên quan, trạng thái thống kê và thời điểm đo.

## 12. Đánh giá kết quả sau điều chỉnh

Không coi việc estimated rows gần actual rows hơn là bằng chứng duy nhất cho hiệu năng tốt hơn. Mục tiêu là cải thiện hành vi của workload trong khi giữ kết quả đúng và chi phí vận hành chấp nhận được.

Sau thay đổi, hãy so sánh:

| Nhóm đo | Chỉ số | Câu hỏi |
|---|---|---|
| Cardinality | Estimated rows, actual rows, Q-error hoặc tỷ số sai lệch | Ước lượng có sát hơn tại nút gây vấn đề không? |
| Cấu trúc kế hoạch | Join order, scan type, join algorithm, loops | Kế hoạch có giảm công việc không cần thiết không? |
| Độ trễ | Thời gian tổng, p50, p95, p99 | Trải nghiệm có cải thiện ổn định dưới tải không? |
| Tài nguyên | CPU, logical reads, physical reads, I/O, memory, spill | Chi phí chuyển sang tài nguyên khác hay đã giảm thực sự? |
| Workload | Tần suất truy vấn, throughput, chi phí ghi, truy vấn liên quan | Thay đổi có làm xấu các thao tác khác không? |
| Tính đúng | Số hàng, kết quả, ràng buộc và hành vi đồng thời | Kết quả có giữ nguyên ngữ nghĩa và tính nhất quán không? |

Đo trong điều kiện tương đương: cùng tập dữ liệu, nhóm tham số, mức tải, cấu hình và khoảng thời gian. Nếu điều kiện khác nhau, ghi lại để không quy nhầm cải thiện hoặc suy giảm cho thay đổi vừa thực hiện.

## 13. Những kết luận sai thường gặp

- **Mọi sai lệch đều do thống kê cũ.** Có thể nguyên nhân là tương quan cột, tham số, biểu thức, kiểu dữ liệu, join key hoặc phân vùng.
- **Nút sai lệch lớn nhất luôn là nguyên nhân gốc.** Nút phía trên có thể chỉ nhận sai lệch đã lan truyền từ nút dưới; cần tìm nút đầu tiên từ lá lên.
- **Actual rows thấp hơn estimated rows nghĩa là truy vấn luôn tốt.** Ước lượng cao có thể khiến optimizer chọn kế hoạch tốn kém hoặc cấp tài nguyên quá mức.
- **Estimated rows gần actual rows bảo đảm kế hoạch tối ưu.** Chi phí mô hình, I/O, tranh chấp và tham số vẫn có thể khiến kế hoạch chậm.
- **Chỉ cần thêm index hint để sửa.** Hint có thể che nguyên nhân và không thích ứng khi dữ liệu thay đổi.
- **Một bộ tham số đủ đại diện.** Truy vấn có thể có phân phối tham số lệch mạnh và cần được kiểm tra theo nhiều nhóm.
- **Tăng thống kê hoặc lấy mẫu luôn tốt.** Thu thập thống kê cũng tiêu tốn tài nguyên; cần điều chỉnh theo bằng chứng.
- **Thời gian các operator cộng lại bằng tổng thời gian truy vấn.** Thời gian ở nút cha có thể bao gồm nút con; không cộng máy móc.

## 14. Checklist chẩn đoán

- [ ] Đã chọn truy vấn có ảnh hưởng rõ ràng và tham số đại diện.
- [ ] Đã thu thập kế hoạch ước lượng và kế hoạch thực tế trong điều kiện phù hợp.
- [ ] Đã đọc cây từ nút lá lên gốc và xác định nút đầu tiên có sai lệch.
- [ ] Đã hiểu quy ước `actual rows` và `loops` của hệ quản trị.
- [ ] Đã định lượng sai lệch và xem cả số hàng tuyệt đối.
- [ ] Đã kiểm tra NDV, NULL fraction, MCV, histogram và độ mới của thống kê.
- [ ] Đã kiểm tra tương quan nhiều cột, khóa join, dữ liệu trùng và ràng buộc.
- [ ] Đã kiểm tra biểu thức, ép kiểu, tham số và thống kê phân vùng.
- [ ] Đã hình thành giả thuyết cụ thể và chọn phép kiểm tra có thể xác nhận hoặc bác bỏ.
- [ ] Đã thay đổi có kiểm soát và đo lại độ trễ, I/O, CPU, bộ nhớ cùng workload.
- [ ] Đã xác nhận kết quả truy vấn và hành vi đồng thời không thay đổi sai lệch.

Chênh lệch giữa estimated rows và actual rows là tín hiệu cho biết mô hình dữ liệu của optimizer có thể không phản ánh đúng lần chạy thực tế. Cách chẩn đoán hiệu quả là lần theo cây từ dưới lên, tìm nút đầu tiên sai lệch, kiểm tra thống kê và giả định tại chính nút đó, rồi xác minh một giả thuyết bằng phép đo có kiểm soát. Khi đánh giá cả cardinality, số vòng lặp, độ trễ, I/O, bộ nhớ và workload, nhóm phát triển có thể cải thiện kế hoạch thực thi dựa trên bằng chứng thay vì dựa vào phỏng đoán.
