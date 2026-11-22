# Đọc cây thực thi: luồng dữ liệu, thứ tự phép toán và số vòng lặp

Kế hoạch thực thi cho biết hệ quản trị cơ sở dữ liệu biến một câu SQL thành các thao tác vật lý như thế nào để lấy, kết hợp, sắp xếp và trả dữ liệu. Đọc được cây thực thi giúp xác định dữ liệu đi qua những bước nào, bước nào tạo ra nhiều hàng trung gian, phép kết hợp nào được chọn và vì sao một thao tác bị lặp lại nhiều lần.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần đặt kế hoạch thực thi cạnh số liệu tải, thống kê truy vấn, chỉ mục, I/O và bộ nhớ. Một kế hoạch có vẻ hợp lý vẫn có thể chậm khi dữ liệu thực tế khác với ước lượng, tham số đầu vào thay đổi hoặc nhiều giao dịch cùng tranh chấp tài nguyên. Mục tiêu của bài học là đọc đúng cấu trúc và bằng chứng trong cây trước khi đề xuất thay đổi SQL hay chỉ mục.

## 1. Kế hoạch thực thi biểu diễn điều gì?

SQL mô tả kết quả mong muốn theo cách khai báo. Người viết câu lệnh nêu dữ liệu cần lấy, điều kiện lọc và cách kết hợp bảng; hệ quản trị quyết định cách thực hiện. Bộ tối ưu hóa (optimizer) có thể đổi thứ tự kết hợp bảng, đẩy điều kiện lọc xuống gần nơi đọc dữ liệu, chọn chỉ mục, chọn thuật toán join hoặc thêm bước sắp xếp.

Kế hoạch thực thi là biểu diễn các lựa chọn đó thành những **toán tử vật lý**. Tên và cách hiển thị phụ thuộc hệ quản trị, nhưng thường có các nhóm thao tác:

- Đọc dữ liệu: quét tuần tự (table/sequence scan), quét chỉ mục (index scan), quét chỉ mục phủ (covering/index-only scan) hoặc truy cập theo khóa.
- Lọc và biến đổi: filter, projection, compute scalar, distinct.
- Kết hợp dữ liệu: nested loop join, hash join, merge join.
- Tổ chức kết quả: sort, aggregate, window operation, limit/top.
- Điều phối: materialize, spool, gather, exchange hoặc các bước phân phối giữa luồng xử lý.

Kế hoạch thường chứa hai loại thông tin. **Ước lượng (estimated plan)** thể hiện dự đoán của optimizer dựa trên thống kê, tham số và mô hình chi phí. **Kế hoạch thực tế (actual plan)** bổ sung những gì xảy ra khi câu lệnh chạy, chẳng hạn số hàng thực tế, số lần thực thi toán tử, thời gian và số khối dữ liệu đã đọc. Một số công cụ hiển thị cả hai trong cùng một cây để có thể so sánh.

Kế hoạch là ảnh chụp của một câu lệnh trong một ngữ cảnh cụ thể: hệ quản trị và phiên bản, cấu hình, thống kê, tham số, trạng thái cache và đặc điểm dữ liệu. Khi các yếu tố này thay đổi, optimizer có thể chọn kế hoạch khác. Vì vậy, cần lưu lại ngữ cảnh khi so sánh hai kế hoạch.

## 2. Hiểu cấu trúc cây và hướng luồng dữ liệu

Trong dạng văn bản phổ biến, mỗi dòng là một toán tử. Các dòng thụt vào là toán tử con (child) cung cấp dữ liệu cho toán tử cha (parent). Toán tử ở trên cùng thường là bước trả kết quả cuối cùng; các toán tử lá ở sâu bên dưới thường là nơi bắt đầu đọc dữ liệu.

Ví dụ minh họa:

```text
Nested Loop
  -> Index Scan on orders
  -> Index Scan on order_items
```

Hai toán tử `Index Scan` là đầu vào của `Nested Loop`. Nested Loop nhận các hàng từ nhánh thứ nhất, sau đó dùng giá trị của mỗi hàng để thực hiện nhánh thứ hai và tạo kết quả kết hợp. Dữ liệu đi từ các nhánh con lên toán tử cha. Khi phân tích, thường đọc từ các nút lá lên gốc để hiểu dữ liệu được tạo ra và biến đổi như thế nào.

Một số giao diện vẽ cây theo chiều ngang hoặc đảo hướng hiển thị. Đừng dựa vào vị trí trái/phải hay trên/dưới một cách máy móc; hãy xác định quan hệ cha-con qua đường nối, dấu thụt dòng hoặc phần mô tả của công cụ. Với mỗi toán tử, hãy hỏi ba câu:

1. Nó nhận dữ liệu từ toán tử con nào?
2. Nó biến đổi, lọc hoặc kết hợp dữ liệu ra sao?
3. Nó phát ra bao nhiêu hàng và được gọi bao nhiêu lần?

### Thứ tự trong cây khác thứ tự viết SQL

Thứ tự bảng xuất hiện trong mệnh đề `FROM` không nhất thiết là thứ tự đọc dữ liệu trong kế hoạch. Optimizer có thể bắt đầu từ bảng có điều kiện lọc chọn lọc nhất, rồi kết hợp với bảng khác. Với các phép join có thể hoán đổi, cây thực thi phản ánh thứ tự vật lý mà optimizer đã chọn.

Ví dụ, câu SQL có thể viết `orders JOIN customers JOIN order_items`, nhưng kế hoạch có thể đọc `customers` trước, tìm `orders` qua chỉ mục rồi mới đọc `order_items`. Đây là lựa chọn của optimizer nhằm giảm số hàng trung gian hoặc chi phí truy cập. Không nên kết luận truy vấn sai chỉ vì thứ tự trong cây khác thứ tự trong câu SQL.

### Toán tử dạng pipeline và toán tử cần tích lũy dữ liệu

Một số toán tử có thể chuyển hàng cho toán tử cha ngay khi đọc được, chẳng hạn nhiều kiểu scan hoặc filter. Một số thao tác cần tích lũy một phần lớn hoặc toàn bộ đầu vào trước khi phát kết quả, chẳng hạn sort, một số kiểu aggregate, hoặc giai đoạn xây dựng bảng băm của hash join. Các bước này có thể cần nhiều bộ nhớ; khi vượt giới hạn, hệ quản trị có thể ghi dữ liệu tạm ra đĩa.

Đặc điểm này giúp giải thích vì sao một truy vấn có thể đọc dữ liệu nhanh nhưng vẫn mất nhiều thời gian trước khi trả hàng đầu tiên. Hãy xem chỉ số startup time, sort method, dung lượng bộ nhớ, số batch và thông tin spill nếu hệ quản trị cung cấp.

## 3. Đọc các trường quan trọng của một toán tử

Tên trường thay đổi theo hệ quản trị và phiên bản, nhưng các khái niệm thường tương đương:

| Trường hoặc thuộc tính | Ý nghĩa | Câu hỏi khi đọc |
|---|---|---|
| Operator / Node type | Phép toán vật lý đang thực hiện | Đây là scan, join, sort, aggregate hay bước điều phối? |
| Estimated rows | Số hàng optimizer dự đoán đầu ra | Ước lượng có gần với dữ liệu thực tế không? |
| Actual rows | Số hàng thực tế được toán tử phát ra | Dữ liệu thực tế khác dự đoán ở bước nào? |
| Loops / Executions | Số lần toán tử được gọi hoặc thực thi | Có toán tử nào bị chạy lặp theo từng hàng của nhánh cha không? |
| Startup cost / time | Chi phí hoặc thời gian trước khi có hàng đầu tiên | Truy vấn có phải chờ tích lũy hoặc sắp xếp đầu vào không? |
| Total cost / time | Chi phí ước lượng hoặc thời gian hoàn tất của toán tử | Bước nào đáng được điều tra sâu hơn? |
| Filter / Predicate | Điều kiện được áp dụng tại toán tử | Điều kiện được dùng để tìm dữ liệu hay chỉ lọc sau khi đọc? |
| Buffers / Logical reads | Số khối hoặc trang dữ liệu được truy cập | Truy vấn đọc nhiều dữ liệu từ cache hay thiết bị lưu trữ? |
| Memory / Spill | Bộ nhớ dùng và dữ liệu tạm ghi ra đĩa | Sort hoặc hash có vượt ngân sách bộ nhớ không? |

Trong kế hoạch PostgreSQL, `cost=startup..total` là đơn vị chi phí nội bộ của optimizer, không phải mili giây. `rows` là số hàng ước lượng; `width` là độ rộng trung bình ước lượng của mỗi hàng. Khi có `EXPLAIN ANALYZE`, phần `actual time`, `rows` và `loops` mô tả hoạt động thực tế. Các hệ quản trị khác có tên trường và quy tắc hiển thị riêng.

Không so sánh trực tiếp giá trị cost giữa hai hệ quản trị hoặc giữa các cấu hình có mô hình chi phí khác nhau. Ngay trong cùng hệ quản trị, cost chủ yếu giúp hiểu lựa chọn tương đối của optimizer; để đánh giá thời gian thật, cần đo thực thi dưới điều kiện tải phù hợp.

## 4. Ước lượng số hàng và số vòng lặp

Số hàng (cardinality) là thông tin trung tâm trong quyết định của optimizer. Nếu optimizer dự đoán một nhánh chỉ trả về vài hàng nhưng thực tế trả hàng trăm nghìn hàng, nó có thể chọn thuật toán join, thứ tự join hoặc cách cấp bộ nhớ không phù hợp.

Hãy phân biệt:

- **Estimated rows:** số hàng dự kiến mỗi lần toán tử chạy.
- **Actual rows:** số hàng thực tế toán tử phát ra trong một lần chạy hoặc giá trị trung bình theo cách công cụ hiển thị.
- **Loops:** số lần toán tử được gọi.

Trong PostgreSQL, khi `loops` lớn hơn 1, `actual rows` và thời gian của toán tử thường được hiển thị dưới dạng trung bình mỗi vòng lặp. Để ước lượng tổng số hàng mà toán tử đã phát ra, có thể nhân `actual rows` với `loops`, lưu ý số hàng được hiển thị có thể đã làm tròn. Hãy kiểm tra quy ước của hệ quản trị đang dùng trước khi áp dụng phép tính này cho công cụ khác.

Ví dụ:

```text
Nested Loop  (cost=... rows=160 ... actual rows=160 loops=1)
  -> Index Scan on orders
       (cost=... rows=80 ... actual rows=80 loops=1)
  -> Index Scan on order_items
       (cost=... rows=2 ... actual rows=2 loops=80)
```

Có thể đọc như sau:

1. Nhánh `orders` trả 80 hàng.
2. Nested Loop dùng từng hàng đó để gọi nhánh `order_items`, vì vậy nhánh trong có 80 vòng lặp.
3. Mỗi vòng lặp của nhánh trong trả trung bình 2 hàng.
4. Nhánh trong phát ra xấp xỉ `2 × 80 = 160` hàng; Nested Loop tạo 160 hàng kết hợp.

Số vòng lặp cao không tự động là lỗi. Với một tập đầu vào nhỏ và một phép tìm kiếm chỉ mục rất rẻ, nhiều lần truy cập có thể là lựa chọn tốt. Nhưng nếu nhánh trong quét một bảng lớn ở mỗi vòng lặp, chi phí có thể tăng nhanh. Hãy đọc `loops` cùng loại toán tử, số hàng mỗi vòng, số khối đọc và thời gian thực tế.

### Tìm sai lệch giữa estimated rows và actual rows

Một cách kiểm tra nhanh là so sánh tỷ lệ giữa số hàng thực tế và ước lượng tại từng nút quan trọng. Ví dụ, optimizer dự đoán 10 hàng nhưng thực tế có 10.000 hàng là sai lệch rất lớn. Sai lệch ở một nút sớm có thể truyền sang các phép join phía trên và làm thay đổi lựa chọn kế hoạch.

Khi thấy sai lệch, hãy xem xét:

- Thống kê bảng hoặc chỉ mục đã cũ sau khi dữ liệu thay đổi nhiều chưa.
- Phân phối dữ liệu có lệch mạnh hay có một vài giá trị xuất hiện rất thường xuyên không.
- Nhiều cột lọc có tương quan với nhau khiến giả định độc lập của optimizer không phù hợp không.
- Kiểu dữ liệu, phép ép kiểu hoặc hàm trên cột có làm điều kiện khó ước lượng hay khó dùng chỉ mục không.
- Giá trị tham số thực tế có khác giá trị mà kế hoạch được tối ưu hóa ban đầu dựa trên đó không.
- Điều kiện join có tạo ra nhiều hàng trùng hoặc quan hệ một-nhiều mà người đọc chưa tính đến không.

Giải pháp có thể liên quan đến cập nhật thống kê, thống kê nhiều cột, điều chỉnh biểu thức SQL, kiểu dữ liệu hoặc chỉ mục. Không nên thêm chỉ mục ngay khi thấy sai lệch: trước hết cần xác định sai lệch bắt đầu ở nút nào và nguyên nhân dữ liệu nào làm optimizer dự đoán sai.

## 5. Hiểu các kiểu scan và điều kiện lọc

### Sequential scan và table scan

Sequential scan đọc lần lượt các trang của bảng. Đây có thể là lựa chọn hợp lý khi truy vấn cần phần lớn dữ liệu, bảng nhỏ hoặc đọc tuần tự rẻ hơn nhiều lần truy cập ngẫu nhiên qua chỉ mục. Thấy `Seq Scan` hoặc `Table Scan` không có nghĩa là kế hoạch xấu.

Hãy kiểm tra số hàng và số trang đã đọc, điều kiện lọc, tỷ lệ hàng bị loại và kích thước bảng. Nếu chỉ cần rất ít hàng nhưng scan phải đọc gần như toàn bộ bảng, hãy điều tra khả năng dùng chỉ mục, độ chọn lọc của điều kiện và tính tương thích của biểu thức với chỉ mục.

### Index scan và index-only/covering scan

Index scan dùng cấu trúc chỉ mục để tìm vị trí hàng phù hợp. Sau đó hệ quản trị có thể phải truy cập bảng để lấy các cột còn thiếu. Nếu truy vấn chỉ cần các cột đã có trong chỉ mục và hệ quản trị hỗ trợ, index-only hoặc covering scan có thể giảm truy cập bảng.

Một kế hoạch dùng chỉ mục vẫn có thể chậm nếu điều kiện trả về quá nhiều hàng, truy cập bảng ngẫu nhiên nhiều lần hoặc phải thực hiện lượng lớn phép kiểm tra bổ sung. Cần xem số hàng thực tế, số lần truy cập, buffer reads và các lần heap/table fetch nếu công cụ cung cấp.

### Index condition và filter

Một số hệ quản trị phân biệt điều kiện dùng để tìm vị trí trong chỉ mục với điều kiện được kiểm tra sau khi hàng đã được đọc. Trong PostgreSQL, `Index Cond` là điều kiện áp dụng trong bước truy cập chỉ mục, còn `Filter` là điều kiện lọc bổ sung tại nút đó. `Rows Removed by Filter` cho biết số hàng bị loại sau khi được nút đọc.

Nếu một scan đọc rất nhiều hàng rồi loại gần hết bằng filter, hãy xem điều kiện có thể được biểu diễn phù hợp hơn cho chỉ mục hay không, chỉ mục hiện có có đúng thứ tự cột hay không và thống kê có phản ánh phân phối dữ liệu không. Không phải điều kiện nào cũng nên đưa vào chỉ mục: chỉ mục làm tăng chi phí ghi, dung lượng lưu trữ và công việc bảo trì.

## 6. Đọc thứ tự và thuật toán join

Join là nơi số hàng trung gian và số vòng lặp có thể làm chi phí tăng đáng kể. Kế hoạch thường cho biết thuật toán được chọn và hai nhánh đầu vào. Hãy xác định nhánh nào được đọc trước, nhánh nào được tra cứu hoặc kết hợp, số hàng của mỗi nhánh và số hàng sau join.

### Nested Loop Join

Nested Loop lấy từng hàng từ nhánh ngoài rồi tìm các hàng tương ứng ở nhánh trong. Nó thường phù hợp khi nhánh ngoài nhỏ và nhánh trong có chỉ mục phù hợp hoặc có chi phí truy cập thấp.

Ví dụ, truy vấn lấy vài chục đơn hàng của một khách hàng rồi tìm chi tiết của từng đơn qua chỉ mục `order_items(order_id)`. Nhánh trong có thể chạy vài chục lần nhưng mỗi lần chỉ đọc rất ít hàng.

Nested Loop đáng nghi khi nhánh ngoài lớn, nhánh trong không có đường truy cập chọn lọc hoặc toán tử trong phải quét nhiều dữ liệu ở mỗi vòng lặp. Để đánh giá, tính gần đúng `actual rows × loops` của nhánh trong theo quy ước công cụ, rồi đối chiếu với thời gian và lượng I/O.

### Hash Join

Hash Join thường xây dựng bảng băm từ một đầu vào (build side), sau đó đọc đầu vào còn lại (probe side) để tìm các hàng khớp. Thuật toán này có thể hiệu quả khi kết hợp tập dữ liệu lớn mà không có chỉ mục phù hợp cho phép tra cứu lặp.

Hãy kiểm tra kích thước hai đầu vào, số hàng ước lượng và thực tế, bộ nhớ cấp cho hash, số batch và thông tin ghi dữ liệu tạm. Nếu hash phải chia nhiều batch hoặc spill ra đĩa, bộ nhớ có thể là nút thắt. Tăng bộ nhớ cho một truy vấn có thể giúp nó chạy nhanh hơn nhưng cũng làm giảm bộ nhớ sẵn có cho các truy vấn đồng thời; cần thử dưới tải đại diện.

### Merge Join

Merge Join kết hợp hai đầu vào đã được sắp theo khóa join. Nếu đầu vào đã có thứ tự phù hợp, thuật toán có thể tránh bước sort bổ sung. Nếu chưa có, kế hoạch có thể phải sort một hoặc cả hai nhánh trước khi merge.

Khi thấy Merge Join, hãy xem hai nhánh có bước Sort hay không, sort có dùng bộ nhớ hay ghi tạm ra đĩa, và thứ tự của chỉ mục có thể cung cấp dữ liệu theo đúng khóa cần thiết không.

Không có thuật toán join nào luôn tốt nhất. Lựa chọn phụ thuộc số hàng, phân phối dữ liệu, thứ tự đầu vào, chỉ mục, bộ nhớ và chi phí truy cập. Thay vì ép optimizer dùng một thuật toán chỉ vì tên của nó có vẻ nhanh, hãy tìm bằng chứng cho thấy ước lượng hoặc điều kiện truy cập đang khiến lựa chọn hiện tại tốn kém.

## 7. Ví dụ đọc một cây thực thi hoàn chỉnh

Giả sử ứng dụng cần tìm đơn hàng của một khách hàng trong một khoảng thời gian và lấy các dòng hàng tương ứng:

```sql
SELECT o.order_id, o.created_at, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
WHERE o.customer_id = 42
  AND o.created_at >= DATE '2026-01-01';
```

Một kế hoạch PostgreSQL minh họa có thể có dạng:

```text
Nested Loop  (cost=0.85..120.00 rows=160 width=32)
             (actual time=0.05..1.80 rows=160 loops=1)
  -> Index Scan using orders_customer_created_idx on orders o
       (cost=0.42..8.00 rows=80 width=16)
       (actual time=0.03..0.40 rows=80 loops=1)
       Index Cond: ((customer_id = 42)
                    AND (created_at >= '2026-01-01'::date))
  -> Index Scan using order_items_order_id_idx on order_items i
       (cost=0.43..1.30 rows=2 width=16)
       (actual time=0.01..0.01 rows=2 loops=80)
       Index Cond: (order_id = o.order_id)
```

Các con số ở đây chỉ minh họa cách đọc, không phải ngưỡng hiệu năng chuẩn. Có thể phân tích theo thứ tự sau:

1. Gốc là `Nested Loop`, vì vậy kết quả cuối được tạo bằng cách kết hợp hai nhánh.
2. Nhánh `orders` dùng chỉ mục tổng hợp theo khách hàng và thời gian. Điều kiện lọc xuất hiện trong `Index Cond`, nên được dùng ngay khi truy cập chỉ mục.
3. Nhánh `orders` trả 80 hàng thực tế, gần với 80 hàng ước lượng. Đây là dấu hiệu ước lượng cardinality ở nhánh này khá sát trong lần chạy minh họa.
4. Nhánh `order_items` được gọi 80 lần, mỗi lần trả trung bình 2 hàng. Tổng đầu ra của nhánh trong xấp xỉ 160 hàng.
5. Chỉ mục trên `order_items(order_id)` cho phép tra cứu theo từng đơn hàng. Với số hàng ngoài chỉ là 80 và mỗi lần tra cứu nhỏ, Nested Loop có thể là lựa chọn hợp lý.
6. Gốc trả 160 hàng. Nếu ứng dụng chỉ cần 10 đơn hàng đầu tiên hoặc chỉ cần đếm, có thể xem lại yêu cầu và cách viết SQL để tránh đọc dữ liệu không cần thiết; không nên thay đổi chỉ mục khi chưa xác định phần công việc thừa.

Giả sử ở một phiên bản khác, nhánh trong lại là `Seq Scan on order_items` với `loops=80`. Điều đó có nghĩa hệ quản trị quét bảng chi tiết nhiều lần. Đây là dấu hiệu cần điều tra, nhưng vẫn phải xem kích thước bảng, số hàng được đọc, buffer reads và chi phí thực tế trước khi kết luận. Có thể thiếu chỉ mục trên khóa join, kiểu dữ liệu hai cột không tương thích, hoặc optimizer đánh giá sai số hàng.

## 8. Nhận biết sort, aggregate và thao tác dùng bộ nhớ

Các toán tử tổ chức dữ liệu thường giải thích phần lớn độ trễ ở những truy vấn báo cáo hoặc truy vấn trả nhiều hàng.

- **Sort:** xem số hàng và độ rộng hàng đi vào sort, khóa sắp xếp, phương pháp sort, bộ nhớ sử dụng và việc ghi dữ liệu tạm. Nếu truy vấn chỉ cần một phần nhỏ kết quả, kiểm tra khả năng giới hạn số hàng sớm hoặc dùng thứ tự có sẵn từ chỉ mục.
- **Aggregate:** xem aggregate xử lý bao nhiêu hàng đầu vào để tạo ra bao nhiêu nhóm. Nếu một nhóm tổng hợp đọc hàng triệu hàng, cần kiểm tra điều kiện lọc, phân nhóm và khả năng giảm dữ liệu trước khi tổng hợp.
- **Hash:** xem số hàng ở build side, bộ nhớ, số bucket/batch và spill. Ước lượng sai có thể khiến bộ nhớ dự trù không phù hợp.
- **Materialize / spool:** toán tử có thể lưu kết quả trung gian để dùng lại. Kiểm tra số lần đọc lại và dung lượng dữ liệu được lưu.
- **Parallel / gather / exchange:** xem số worker thực sự tham gia, lượng hàng mỗi worker xử lý và chi phí gom hoặc trao đổi dữ liệu. Có kế hoạch song song không đồng nghĩa mọi truy vấn đều nhanh hơn; với đầu vào nhỏ, chi phí điều phối có thể lớn hơn lợi ích.

Khi kế hoạch cho thấy ghi dữ liệu tạm ra đĩa, cần đối chiếu với thống kê I/O và cấu hình bộ nhớ của hệ quản trị. Không nên tăng giới hạn bộ nhớ toàn hệ thống chỉ dựa trên một truy vấn; hãy kiểm tra số truy vấn đồng thời và mức tiêu thụ bộ nhớ tổng thể.

## 9. Đọc thời gian và I/O mà không kết luận vội

Thời gian tại một nút thường bao gồm thời gian xử lý các nút con theo quy ước của hệ quản trị. Vì vậy, không cộng thời gian của mọi nút trong cây để tính tổng: làm như vậy có thể đếm lặp thời gian của các nhánh con. Hãy dùng tổng thời gian thực thi do công cụ báo cáo và dùng số liệu từng nút để định vị phần việc đáng chú ý.

Với PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` bổ sung số block được truy cập. Có thể phân biệt block lấy từ cache và block cần đọc từ thiết bị theo các trường mà phiên bản hiển thị. Một truy vấn có nhiều buffer hit vẫn có thể tốn CPU; một truy vấn có ít hàng đầu ra vẫn có thể đọc nhiều block để tìm chúng.

Khi đọc I/O, hãy phân biệt:

- Số hàng được phát ra với số hàng hoặc trang phải đọc để tạo ra chúng.
- Đọc từ cache với đọc từ thiết bị lưu trữ.
- I/O do truy vấn tạo ra với thời gian chờ do các truy vấn khác đang sử dụng thiết bị.
- Thời gian thực thi bên trong cơ sở dữ liệu với thời gian ứng dụng chờ lấy kết nối, truyền dữ liệu hoặc xử lý kết quả.

Kế hoạch thực thi thường không cho thấy đầy đủ tranh chấp khóa và thời gian chờ bên ngoài câu lệnh. Nếu ứng dụng chậm nhưng thời gian thực thi trong kế hoạch thấp, hãy đối chiếu thời gian chờ connection pool, wait events, lock waits, mạng và thời gian xử lý ở ứng dụng. Không quy mọi độ trễ cho SQL chỉ dựa trên thời gian người dùng quan sát.

## 10. Quy trình đọc cây thực thi trong công việc tối ưu

Hãy dùng một quy trình nhất quán để tránh thay đổi theo cảm tính:

1. **Chọn truy vấn đại diện.** Lấy truy vấn từ thống kê tải hoặc trace, ưu tiên truy vấn có tổng thời gian tiêu tốn lớn, p95/p99 cao hoặc tần suất cao. Ghi lại fingerprint, tham số, tần suất và bối cảnh gọi.
2. **Thu thập kế hoạch ước lượng.** Xem cấu trúc toán tử, thứ tự join, scan, filter, sort và aggregate. Ghi lại ước lượng số hàng tại các nút quan trọng.
3. **Thu thập kế hoạch thực tế an toàn.** Chọn tham số đại diện và điều kiện tải phù hợp. Với PostgreSQL có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn đọc. Lưu ý `ANALYZE` thực sự thực thi câu lệnh; không chạy tùy tiện với DML hoặc câu lệnh có tác dụng phụ trong môi trường thật.
4. **Đọc từ lá lên gốc.** Xác định dữ liệu được đọc ở đâu, lọc ở đâu, kết hợp theo thứ tự nào và bước nào cần tích lũy dữ liệu.
5. **So sánh estimated với actual.** Tìm nút có sai lệch cardinality lớn, đặc biệt các nút sớm trước join. Ghi lại `rows`, `loops` và số hàng gần đúng được xử lý qua mọi vòng lặp.
6. **Xác định công việc tốn kém.** Đối chiếu thời gian, buffer reads, số hàng bị loại, số vòng lặp, sort/hash spill và mức dùng worker. Đừng chỉ nhìn một phần trăm cost của nút.
7. **Đưa ra giả thuyết có thể kiểm chứng.** Ví dụ: điều kiện lọc không dùng được chỉ mục; nhánh ngoài của Nested Loop trả quá nhiều hàng; thống kê sai lệch; sort tràn ra đĩa; hoặc ứng dụng chờ pool trước khi truy vấn bắt đầu.
8. **Thay đổi từng yếu tố có kiểm soát.** Có thể cập nhật thống kê, sửa biểu thức SQL, điều chỉnh thứ tự hoặc phạm vi lọc, hay thiết kế chỉ mục phù hợp. Ghi lại thay đổi và lý do.
9. **Đo lại trong điều kiện tương đương.** Dùng cùng tham số đại diện, dữ liệu, mức tải và cấu hình. So sánh kết quả, p95/p99, số hàng, loops, buffer, I/O, CPU và tác động lên thao tác ghi.
10. **Xác nhận tính đúng đắn.** Kiểm tra kết quả truy vấn, tính nhất quán dữ liệu và hành vi khi nhiều giao dịch chạy đồng thời. Một kế hoạch nhanh hơn nhưng trả kết quả sai hoặc làm thao tác ghi suy giảm không phải là cải thiện hợp lệ.

### Thận trọng với EXPLAIN ANALYZE

`EXPLAIN` thông thường thường chỉ yêu cầu optimizer tạo kế hoạch mà không thực thi truy vấn. `EXPLAIN ANALYZE` thực thi câu lệnh để thu thập số liệu thực tế. Với câu `SELECT`, việc chạy vẫn tiêu thụ CPU, bộ nhớ và I/O; truy vấn nặng có thể ảnh hưởng tải hệ thống. Với `INSERT`, `UPDATE`, `DELETE` hoặc câu lệnh gọi hàm có tác dụng phụ, câu lệnh có thể thay đổi dữ liệu hoặc kích hoạt hành động khác.

Chỉ đo thực tế khi đã đánh giá tác động và chọn môi trường phù hợp. Một transaction có rollback không bảo đảm đảo ngược mọi tác dụng phụ bên ngoài cơ sở dữ liệu. Hãy tuân theo quy trình kiểm thử và vận hành của hệ thống.

## 11. Khác biệt giữa các hệ quản trị

Các khái niệm về cây, cardinality, join và số lần thực thi tương đồng, nhưng tên trường và cách hiển thị khác nhau:

| Hệ quản trị | Cách xem thường dùng | Chi tiết cần chú ý |
|---|---|---|
| PostgreSQL | `EXPLAIN`, `EXPLAIN ANALYZE`, thường kết hợp `BUFFERS` | Cây thụt dòng; estimated/actual rows, loops, actual time, buffers; actual rows/time có quy ước trung bình mỗi loop khi loops lớn hơn 1 |
| MySQL | `EXPLAIN`, `EXPLAIN FORMAT=TREE`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Dạng tree thể hiện iterator; chú ý actual rows và loops, access type, key, filter và thời gian iterator |
| SQL Server | Estimated Execution Plan và Actual Execution Plan trong công cụ quản trị | Xem Estimated/Actual Number of Rows, Actual Number of Executions, seek/scan, join operator, warnings, spill và thuộc tính song song |

Không chuyển nguyên cách diễn giải một trường của hệ quản trị này sang hệ quản trị khác. Ví dụ, cost phần trăm trong giao diện SQL Server là ước lượng tương đối trong kế hoạch, không phải phần trăm thời gian thực tế đã đo. Luôn đọc chú giải và tài liệu của phiên bản đang vận hành.

## 12. Những cách đọc sai thường gặp

- **Thấy table scan là kết luận thiếu chỉ mục.** Scan có thể rẻ hơn khi cần phần lớn bảng hoặc bảng nhỏ. Cần xem tỷ lệ hàng cần lấy và số trang đọc.
- **Thấy index scan là kết luận truy vấn đã tối ưu.** Chỉ mục có thể trả quá nhiều hàng, gây nhiều lần truy cập bảng hoặc tạo lượng I/O ngẫu nhiên lớn.
- **Bỏ qua loops.** Một toán tử nhanh trong một lần gọi có thể trở nên đắt khi được gọi hàng trăm nghìn lần.
- **Nhầm estimated rows với actual rows.** Ước lượng là dự đoán của optimizer; cần số liệu thực tế để kiểm chứng.
- **Cộng thời gian của mọi nút.** Thời gian ở nút cha có thể bao gồm thời gian của nút con; dùng tổng thời gian truy vấn và đọc từng nút để định vị.
- **So sánh cost với mili giây.** Cost là đơn vị nội bộ, không phải thời gian thực.
- **Chỉ nhìn kế hoạch của một bộ tham số.** Tham số có phân phối khác nhau có thể cần kế hoạch khác nhau.
- **Ép join hoặc index hint quá sớm.** Hint có thể che vấn đề thống kê và trở nên bất lợi khi dữ liệu thay đổi.
- **Xem kế hoạch mà bỏ qua tải đồng thời.** Kế hoạch đơn lẻ không mô tả đầy đủ tranh chấp khóa, cạn pool, nghẽn mạng hoặc cạnh tranh I/O từ truy vấn khác.
- **Chạy EXPLAIN ANALYZE trên câu lệnh có tác dụng phụ mà không đánh giá rủi ro.** Công cụ thực thi câu lệnh để đo số liệu thực tế.

## 13. Bài tập đọc cây thực thi

Cho cây minh họa sau:

```text
Nested Loop  (estimated rows=500, actual rows=4000, loops=1)
  -> Seq Scan on customers
       (estimated rows=20, actual rows=2000, loops=1)
       Filter: region = 'NORTH'
  -> Index Scan on orders_customer_id_idx
       (estimated rows=25, actual rows=2, loops=2000)
       Index Cond: customer_id = customers.id
```

Hãy trả lời:

1. Toán tử nào là gốc và hai nhánh nào cung cấp dữ liệu cho nó?
2. Vì sao nhánh `orders` có 2.000 loops?
3. Nhánh `customers` có sai lệch cardinality theo hướng nào?
4. Nhánh `orders` trả trung bình 2 hàng mỗi lần gọi. Ước lượng tổng số hàng đầu ra của nhánh này theo cách hiển thị minh họa là bao nhiêu?
5. Cần kiểm tra những dữ liệu hoặc thống kê nào trước khi quyết định thêm chỉ mục?

Gợi ý phân tích:

- `Nested Loop` là toán tử gốc; hai nhánh scan là đầu vào. Dữ liệu đi từ hai nhánh con lên phép join.
- Nhánh `customers` trả 2.000 hàng, nên nhánh trong của Nested Loop được gọi một lần cho mỗi khách hàng; vì vậy `orders` có 2.000 loops.
- Optimizer dự đoán 20 khách hàng nhưng thực tế có 2.000, tức thấp hơn thực tế 100 lần. Sai lệch ở nhánh ngoài làm số lần tra cứu đơn hàng cao hơn dự kiến.
- Nhánh `orders` trả trung bình 2 hàng mỗi vòng, tương đương khoảng `2 × 2.000 = 4.000` hàng trước khi tính các bước phía trên.
- Cần kiểm tra thống kê của `customers.region`, độ chọn lọc của giá trị `NORTH`, phân phối dữ liệu, thống kê có cũ không và chỉ mục hiện tại. Nếu truy vấn thường lọc theo `region` rồi join theo `customer_id`, có thể đánh giá chỉ mục phù hợp sau khi hiểu tần suất và kiểu truy vấn; đồng thời cân nhắc chi phí ghi và dung lượng của chỉ mục mới.

## 14. Checklist trước khi đề xuất thay đổi

- [ ] Đã xác định đúng toán tử gốc, các nhánh con và hướng luồng dữ liệu.
- [ ] Đã phân biệt kế hoạch ước lượng với kế hoạch thực tế.
- [ ] Đã kiểm tra estimated rows, actual rows và loops ở các nút quan trọng.
- [ ] Đã hiểu thứ tự join và lý do nhánh ngoài/nhánh trong được chọn.
- [ ] Đã xem điều kiện truy cập chỉ mục, filter và số hàng bị loại.
- [ ] Đã kiểm tra sort, hash, aggregate, bộ nhớ và dữ liệu tạm.
- [ ] Đã đối chiếu thời gian, buffer/I/O và tải đồng thời.
- [ ] Đã kiểm tra thống kê, phân phối dữ liệu và tham số đại diện.
- [ ] Đã đánh giá tác động của phép đo thực tế trước khi chạy câu lệnh.
- [ ] Đã có giả thuyết cụ thể và cách đo lại sau điều chỉnh.

Đọc cây thực thi hiệu quả là lần theo dữ liệu từ các toán tử lá lên nút trả kết quả, hiểu số hàng được tạo ra ở mỗi bước và nhân đúng với số vòng lặp theo quy ước của hệ quản trị. Khi đặt luồng dữ liệu cạnh ước lượng, thời gian, I/O và bộ nhớ, ta có thể chỉ ra chính xác bước nào đang làm tăng công việc, hình thành giả thuyết có căn cứ và kiểm chứng thay đổi hiệu năng bằng số liệu thực tế.
