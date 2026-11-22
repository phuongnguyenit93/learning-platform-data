# Kế hoạch ước lượng và kế hoạch thực tế: thông tin và mục đích sử dụng

Kế hoạch thực thi cho biết hệ quản trị cơ sở dữ liệu dự định truy cập dữ liệu và kết hợp các bước xử lý như thế nào để trả lời một câu SQL. Kế hoạch ước lượng mô tả lựa chọn của bộ tối ưu dựa trên câu lệnh, thống kê và cấu hình tại thời điểm lập kế hoạch. Kế hoạch thực tế bổ sung dữ liệu thu được trong khi câu lệnh chạy, chẳng hạn số hàng thực sự đi qua từng toán tử, số vòng lặp, thời gian và lượng dữ liệu đọc. Hai loại kế hoạch trả lời những câu hỏi khác nhau và cần được dùng kết hợp khi phân tích hiệu năng.

Bài học thuộc chương **Kế hoạch thực thi** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; các nội dung liên quan gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, kế hoạch thực thi là bằng chứng để hiểu đường đi của dữ liệu, kiểm tra giả thuyết về truy vấn và xác nhận tác động của thay đổi trên workload đại diện.

## 1. Kế hoạch thực thi dùng để làm gì?

Khi nhận một câu SQL, hệ quản trị phải phân tích cú pháp, kiểm tra tên và kiểu dữ liệu, xây dựng các phương án xử lý rồi chọn một kế hoạch theo chi phí ước lượng. Kế hoạch có thể bao gồm cách truy cập bảng, chỉ mục được dùng, thứ tự phép nối, thuật toán nối, thao tác sắp xếp, gom nhóm, lọc và cách phối hợp các toán tử.

Kế hoạch thực thi giúp trả lời các câu hỏi như:

- Cơ sở dữ liệu đang quét toàn bảng hay truy cập qua chỉ mục?
- Điều kiện lọc được áp dụng sớm hay sau khi đọc nhiều hàng?
- Các bảng được nối theo thứ tự nào và dùng thuật toán nối nào?
- Có thao tác sort, aggregate, materialize hoặc ghi dữ liệu trung gian ra đĩa không?
- Bộ tối ưu dự đoán bao nhiêu hàng ở mỗi bước?
- Khi câu lệnh chạy thật, số hàng và số vòng lặp có gần với dự đoán không?
- Thời gian và lượng đọc tập trung ở toán tử nào?

Kế hoạch không tự nó cho biết toàn bộ nguyên nhân của độ trễ. Một toán tử có thể chậm vì chờ I/O, khóa, CPU, bộ nhớ hoặc tài nguyên bên ngoài. Cần kết hợp kế hoạch với thống kê truy vấn, trạng thái chờ, log và số liệu tải tại cùng thời điểm.

## 2. Kế hoạch ước lượng

Kế hoạch ước lượng (estimated execution plan) là phương án do bộ tối ưu tạo ra trước khi câu lệnh được thực thi. Nó thể hiện các toán tử dự kiến, đường truy cập dữ liệu, thứ tự xử lý và những ước lượng mà bộ tối ưu dùng để so sánh các phương án.

Tùy hệ quản trị và công cụ, kế hoạch ước lượng thường có các thông tin:

- **Toán tử (operator):** thao tác như table scan, index scan/seek, nested loop, hash join, merge join, sort hoặc aggregate.
- **Ước lượng số hàng (estimated rows/cardinality):** số hàng mà toán tử được dự đoán sẽ tạo ra.
- **Chi phí ước lượng (estimated cost):** giá trị nội bộ dùng để so sánh phương án theo mô hình chi phí của hệ quản trị.
- **Đường truy cập:** bảng hoặc chỉ mục mà toán tử dự kiến đọc, cùng điều kiện tìm kiếm và điều kiện lọc nếu công cụ hiển thị.
- **Ước lượng tài nguyên:** thông tin về bộ nhớ, I/O hoặc chi phí CPU theo mô hình của hệ quản trị, nếu có.

Kế hoạch ước lượng hữu ích khi muốn kiểm tra lựa chọn của bộ tối ưu mà không cần chạy câu truy vấn. Nó phù hợp để rà soát truy vấn trên môi trường có dữ liệu lớn, kiểm tra thay đổi SQL hoặc chỉ mục, và tìm những điểm đáng nghi như quét phạm vi quá rộng, nối theo thứ tự bất lợi hoặc ước lượng số hàng bất thường.

### 2.1. Chi phí ước lượng không phải thời gian thực thi

Chi phí trong kế hoạch là thước đo nội bộ của bộ tối ưu, không phải số mili giây dự báo chính xác. Cách tính và đơn vị của chi phí khác nhau giữa các hệ quản trị. Không nên so sánh trực tiếp cost giữa hai hệ quản trị, hoặc kết luận một truy vấn có cost 100 sẽ chạy trong 100 ms.

Chi phí chủ yếu hữu ích để hiểu vì sao bộ tối ưu chọn một phương án thay vì phương án khác trong cùng hệ thống. Nếu một thay đổi làm cost giảm nhưng thời gian thực tế tăng, cần kiểm tra lại giả định về thống kê, cache, tải đồng thời và tài nguyên. Kế hoạch có cost thấp hơn chưa chắc mang lại trải nghiệm tốt hơn ở mọi workload.

### 2.2. Ước lượng số hàng và vai trò của thống kê

Bộ tối ưu dự đoán số hàng dựa trên thống kê như số lượng hàng, số giá trị phân biệt, phân bố dữ liệu, histogram, độ chọn lọc và quan hệ giữa các cột nếu hệ quản trị có thông tin đó. Ước lượng này ảnh hưởng đến việc chọn chỉ mục, thứ tự nối và thuật toán nối.

Ví dụ, nếu bộ tối ưu nghĩ một điều kiện lọc chỉ trả về 10 hàng, nó có thể chọn nested loop. Nếu thực tế điều kiện đó trả về hàng trăm nghìn hàng, nested loop có thể thực hiện rất nhiều lần truy cập lặp. Một ước lượng sai ở đầu kế hoạch có thể lan truyền đến các toán tử phía sau.

Thống kê cũ, phân bố dữ liệu lệch, tương quan giữa các cột, tham số truy vấn hoặc biểu thức khó ước lượng có thể làm sai cardinality. Khi thấy ước lượng chênh lệch lớn với số hàng thực tế, hãy kiểm tra chất lượng thống kê và đặc tính dữ liệu trước khi vội sửa SQL hoặc thêm chỉ mục.

## 3. Kế hoạch thực tế

Kế hoạch thực tế (actual execution plan) là kế hoạch gắn với một lần thực thi cụ thể và có thêm thông tin runtime do hệ quản trị thu thập. Tên gọi và độ chi tiết khác nhau giữa sản phẩm. Một số công cụ cung cấp kế hoạch thực tế sau khi chạy câu lệnh; một số công cụ hiển thị ước lượng và dữ liệu thực tế trên cùng sơ đồ.

Thông tin runtime có thể gồm:

- Số hàng thực tế mà từng toán tử tạo ra hoặc xử lý.
- Số vòng lặp mà toán tử được gọi.
- Thời gian bắt đầu, thời gian thực hiện hoặc thời gian tổng hợp theo cách đo của hệ quản trị.
- Số lần đọc logic, đọc vật lý, số trang hoặc lượng dữ liệu được truy cập.
- Bộ nhớ được cấp và sử dụng, thao tác spill ra đĩa hoặc cảnh báo tràn bộ nhớ.
- Thông tin song song, phân phối công việc và các cảnh báo thực thi nếu công cụ hỗ trợ.

Kế hoạch thực tế giúp kiểm chứng điều gì đã xảy ra trong lần chạy được đo. Nó đặc biệt hữu ích khi truy vấn chậm trong môi trường thực tế, khi cần so sánh số hàng ước lượng với số hàng thật, hoặc khi cần xác định toán tử nào thực hiện nhiều công việc hơn dự kiến.

Kế hoạch thực tế phản ánh một lần chạy với một bộ tham số, trạng thái cache, mức tải và môi trường cụ thể. Nó không đại diện cho mọi lần chạy. Với truy vấn có tham số, dữ liệu lệch hoặc workload biến động, cần đo nhiều giá trị tham số và nhiều trạng thái tải thích hợp.

## 4. So sánh hai loại kế hoạch

| Tiêu chí | Kế hoạch ước lượng | Kế hoạch thực tế |
|---|---|---|
| Thời điểm | Được tạo trước khi câu lệnh chạy | Gắn với một lần thực thi đã diễn ra |
| Mục đích chính | Xem phương án mà bộ tối ưu dự định chọn | Xem phương án đã chạy và số liệu runtime |
| Số hàng | Số hàng dự đoán | Số hàng thực tế được ghi nhận |
| Thời gian | Thường không có thời gian thực thi thực tế | Có thể có thời gian thực tế theo toán tử hoặc câu lệnh |
| I/O và bộ nhớ | Có thể có ước lượng hoặc thông tin cấp phát dự kiến | Có thể có số liệu đọc, bộ nhớ dùng, spill và cảnh báo runtime |
| Tác động khi lấy | Thường không cần thực thi câu SQL | Câu lệnh phải được chạy để thu thập dữ liệu thực tế |
| Rủi ro | Thấp hơn vì chỉ lập kế hoạch, nhưng vẫn tiêu thụ tài nguyên phân tích | Có thể tiêu thụ tài nguyên và gây tác động dữ liệu như câu lệnh bình thường |
| Câu hỏi phù hợp | “Bộ tối ưu định làm gì?” | “Lần chạy này thực sự đã làm gì?” |

Kế hoạch thực tế thường chứa hoặc liên kết với cấu trúc kế hoạch được chọn, nhưng hai khái niệm không nên bị đồng nhất. Nếu chỉ có kế hoạch ước lượng, ta chưa biết số hàng và thời gian thực tế. Nếu chỉ nhìn kế hoạch thực tế của một lần chạy, ta có thể bỏ qua biến động của tham số và workload khác.

## 5. Đọc cấu trúc kế hoạch

Kế hoạch thường được trình bày dưới dạng cây toán tử. Mỗi nút mô tả một bước; các nút con cung cấp dữ liệu cho nút cha. Cách đọc và chiều thực thi phụ thuộc công cụ. Trong nhiều kế hoạch dạng cây, kết quả từ nút con được đưa lên nút cha, nên cần hiểu quan hệ cha-con thay vì chỉ đọc từ trên xuống như một danh sách tuần tự.

Các toán tử thường gặp:

| Toán tử | Ý nghĩa | Điều cần xem xét |
|---|---|---|
| Table/Sequential Scan | Đọc nhiều hoặc toàn bộ phạm vi của bảng | Số hàng cần đọc, điều kiện lọc, kích thước bảng và tỷ lệ hàng được giữ lại |
| Index Seek/Lookup | Tìm phạm vi hoặc khóa qua chỉ mục | Điều kiện seek, số lần lookup, số hàng phải đọc thêm từ bảng |
| Index Scan | Duyệt một phần hoặc toàn bộ chỉ mục | Phạm vi duyệt, thứ tự dữ liệu và lượng hàng bị loại |
| Nested Loop Join | Với mỗi hàng bên ngoài, tìm hàng tương ứng ở đầu vào bên trong | Số hàng đầu vào, số vòng lặp và khả năng truy cập chỉ mục ở phía trong |
| Hash Join | Xây dựng bảng băm từ một đầu vào rồi dò đầu vào còn lại | Kích thước đầu vào, bộ nhớ, spill và số hàng thực tế |
| Merge Join | Nối hai đầu vào theo thứ tự khóa | Chi phí tạo/duy trì thứ tự và số hàng hai phía |
| Sort | Sắp xếp dữ liệu theo một hoặc nhiều khóa | Số hàng, kích thước bản ghi, bộ nhớ và khả năng spill ra đĩa |
| Aggregate | Tính tổng hợp hoặc gom nhóm | Số nhóm, số hàng đầu vào và bộ nhớ cần thiết |
| Filter | Loại các hàng không thỏa điều kiện | Điều kiện được áp dụng ở đâu và bao nhiêu hàng bị loại |

Không có toán tử nào luôn tốt hoặc luôn xấu. Sequential scan có thể là lựa chọn hiệu quả khi bảng nhỏ hoặc truy vấn cần phần lớn hàng. Index seek có thể kém hiệu quả nếu phải thực hiện quá nhiều lookup ngẫu nhiên. Hash join phù hợp với nhiều tình huống nhưng có thể tốn bộ nhớ hoặc spill. Cần đánh giá toán tử trong bối cảnh cardinality, dữ liệu, workload và tài nguyên.

### 5.1. Đọc từ lá đến nút gốc

Khi phân tích cây, bắt đầu ở các nút lá để hiểu dữ liệu được lấy từ đâu, sau đó đi lên các nút nối, lọc, sắp xếp và tổng hợp. Với mỗi nút, hãy hỏi:

1. Nút nhận dữ liệu từ đâu?
2. Nó đọc hoặc tạo ra bao nhiêu hàng?
3. Nó có áp dụng điều kiện lọc nào không?
4. Có bao nhiêu lần gọi hoặc vòng lặp?
5. Nó tiêu tốn thời gian, I/O hoặc bộ nhớ ra sao?
6. Nút cha có làm số hàng tăng mạnh hoặc phải xử lý một tập dữ liệu lớn không?

Tập trung vào những nút có lượng công việc lớn, ước lượng sai đáng kể hoặc chiếm nhiều thời gian/tài nguyên. Một nút có thời gian riêng nhỏ nhưng được gọi hàng nghìn lần vẫn có thể đóng góp đáng kể vào tổng chi phí.

### 5.2. Số hàng và số vòng lặp

Một sai lầm thường gặp là nhìn số hàng thực tế mà bỏ qua số vòng lặp. Trong một số hệ quản trị, trường `actual rows` và `actual time` ở toán tử có thể là giá trị trung bình mỗi lần lặp; cần nhân với số loops để ước lượng tổng lượng hàng hoặc tổng công việc. Hệ quản trị khác có thể trình bày tổng số hàng theo cách khác. Hãy đọc chú giải của công cụ đang dùng trước khi tính toán.

Ví dụ minh họa: một nút bên trong nested loop trả trung bình 3 hàng mỗi lần và được gọi 2.000 lần. Nếu công cụ báo số hàng theo mỗi vòng lặp, nút đó đã cung cấp khoảng 6.000 hàng cho nút cha. Nếu chỉ nhìn số 3, ta sẽ đánh giá thấp công việc thực tế.

Trong kế hoạch của SQL Server, có thể gặp các trường như Actual Number of Rows và Actual Number of Rows for All Executions; cần phân biệt giá trị theo lần thực thi với tổng qua các lần. Không áp dụng máy móc quy tắc nhân loops cho mọi sản phẩm hoặc mọi trường hiển thị.

## 6. Đối chiếu ước lượng với thực tế

Một trong những cách hữu ích nhất để đọc kế hoạch là so sánh số hàng ước lượng với số hàng thực tế tại từng toán tử. Chênh lệch nhỏ có thể không ảnh hưởng đến lựa chọn kế hoạch. Chênh lệch rất lớn, nhất là ở các nút đầu vào phép nối, có thể khiến bộ tối ưu chọn sai thuật toán hoặc thứ tự xử lý.

Ví dụ:

| Toán tử | Số hàng ước lượng | Số hàng thực tế | Nhận xét |
|---|---:|---:|---|
| Lọc theo trạng thái | 20 | 18 | Ước lượng khá sát |
| Lọc theo khách hàng | 10 | 80.000 | Sai lệch lớn; cần kiểm tra phân bố và tham số |
| Đầu vào nested loop | 10 | 80.000 | Sai lệch có thể làm số lần truy cập phía trong tăng mạnh |

Các con số trên chỉ là ví dụ. Khi gặp sai lệch, hãy lần ngược từ nút có ước lượng sai đầu tiên về nguồn dữ liệu và điều kiện lọc. Nếu ước lượng ở nút lá đã sai, các nút phía trên có thể tiếp tục nhân sai số. Đừng chỉ sửa toán tử cuối cùng khi nguyên nhân nằm ở thống kê hoặc phân bố dữ liệu đầu vào.

### 6.1. Nguyên nhân thường làm ước lượng sai

- Thống kê chưa được cập nhật sau khi dữ liệu thay đổi mạnh.
- Phân bố dữ liệu lệch, có một số giá trị xuất hiện rất thường xuyên.
- Các cột có tương quan nhưng mô hình thống kê không phản ánh đầy đủ tương quan đó.
- Tham số truy vấn có độ chọn lọc khác nhau giữa các lần chạy.
- Biểu thức, hàm, ép kiểu hoặc điều kiện phức tạp khiến bộ tối ưu khó ước lượng.
- Dữ liệu thay đổi liên tục hoặc thống kê lấy mẫu chưa đại diện.
- Kế hoạch được biên dịch với tham số hoặc bối cảnh khác với lần chạy đang quan sát.

Hướng xử lý có thể gồm cập nhật hoặc mở rộng thống kê, kiểm tra histogram và độ chọn lọc, xem xét thống kê đa cột khi hệ quản trị hỗ trợ, chuẩn hóa kiểu dữ liệu, viết lại biểu thức để bộ tối ưu hiểu rõ hơn, hoặc kiểm tra cơ chế cache kế hoạch và tham số. Mỗi thay đổi cần có giả thuyết và phép đo riêng.

### 6.2. Ước lượng sai có thể dẫn đến kế hoạch kém như thế nào?

Giả sử bảng `orders` có 20 triệu hàng. Bộ tối ưu dự đoán điều kiện `status = 'PENDING'` chỉ trả về vài hàng, nhưng thực tế trạng thái này chiếm 40% bảng. Bộ tối ưu có thể chọn truy cập chỉ mục rồi thực hiện nhiều lookup để lấy các cột còn lại. Khi thực tế có hàng triệu kết quả, phương án đó có thể đắt hơn một lần quét tuần tự.

Trong trường hợp này, cần xác nhận tỷ lệ dữ liệu thực tế, thống kê về cột `status`, số hàng đọc và kế hoạch được chọn. Thêm một chỉ mục khác mà không hiểu độ chọn lọc có thể làm tăng chi phí ghi và dung lượng nhưng không giải quyết nguyên nhân.

## 7. Lấy kế hoạch trên các hệ quản trị phổ biến

Cú pháp và khả năng hiển thị khác nhau giữa các hệ quản trị. Các ví dụ dưới đây minh họa cách tiếp cận; hãy dùng tài liệu và phiên bản của hệ quản trị đang vận hành để xác nhận tùy chọn cụ thể.

### 7.1. PostgreSQL

Kế hoạch ước lượng có thể lấy bằng:

```sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Để thu thập số liệu thực thi và bộ đệm trong một lần chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN` thông thường chỉ lập kế hoạch, không chạy câu truy vấn. `EXPLAIN ANALYZE` thực thi câu lệnh rồi ghi nhận dữ liệu runtime. `BUFFERS` bổ sung số liệu về truy cập bộ đệm. Các tùy chọn như `VERBOSE`, `SETTINGS` hoặc định dạng JSON có thể hữu ích khi cần thêm chi tiết, tùy phiên bản.

### 7.2. MySQL

MySQL hỗ trợ `EXPLAIN` để xem cách bộ tối ưu dự định xử lý câu lệnh:

```sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Ở các phiên bản hỗ trợ, `EXPLAIN ANALYZE` chạy câu lệnh và hiển thị thông tin thực tế theo dạng cây:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Các trường trong `EXPLAIN` truyền thống có thể gồm access type, possible keys, key được chọn, key length, rows và filtered. Đây là thông tin ước lượng và lựa chọn truy cập; không nên nhầm `rows` ước lượng với số hàng thực tế. Khả năng và cú pháp của `EXPLAIN ANALYZE` phụ thuộc phiên bản MySQL.

### 7.3. Microsoft SQL Server

SQL Server Management Studio cung cấp lựa chọn hiển thị estimated execution plan và actual execution plan. Estimated plan cho biết phương án được tối ưu dự kiến chọn. Actual plan được thu thập khi câu lệnh chạy và có thêm số liệu runtime như actual rows, số lần thực thi và cảnh báo toán tử.

Trong SSMS, có thể bật **Include Actual Execution Plan** trước khi chạy câu lệnh để xem kế hoạch thực tế. Lựa chọn **Display Estimated Execution Plan** cho phép xem kế hoạch ước lượng mà không thực thi truy vấn. Tên menu và vị trí có thể khác theo phiên bản công cụ.

Các hệ quản trị khác cũng cung cấp công cụ tương tự nhưng cách gọi toán tử, định nghĩa cost và mức chi tiết runtime có thể khác nhau. Không nên so sánh trực tiếp tên toán tử hoặc cost giữa các sản phẩm.

## 8. Quy trình phân tích một truy vấn chậm

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Xác định truy vấn và workload.** Thu thập câu SQL, tham số đại diện, tần suất, độ trễ p95/p99, throughput và thời điểm vấn đề xảy ra.
2. **Lấy kế hoạch ước lượng.** Xem đường truy cập, toán tử, số hàng dự đoán và chi phí tương đối; ghi lại phiên bản DB và cấu hình liên quan.
3. **Lấy kế hoạch thực tế trong môi trường phù hợp.** Chạy với tham số và dữ liệu đại diện; thu thập actual rows, loops, thời gian, I/O và cảnh báo runtime nếu có.
4. **So sánh cardinality.** Tìm nút đầu tiên có chênh lệch lớn giữa ước lượng và thực tế.
5. **Xác định phần công việc đáng kể.** Kiểm tra scan, lookup lặp, join, sort, aggregate, spill, đọc dữ liệu và các trạng thái chờ.
6. **Đưa ra một giả thuyết nguyên nhân.** Ví dụ thống kê sai làm ước lượng thấp, chỉ mục không phù hợp hoặc giao dịch gây chờ khóa.
7. **Chọn một thay đổi có chủ đích.** Có thể cập nhật thống kê, điều chỉnh SQL, thử chỉ mục hoặc thay đổi cách truy cập dữ liệu. Ghi rõ chỉ số dự kiến thay đổi.
8. **Đo lại cùng điều kiện.** So sánh kế hoạch và số liệu runtime trước/sau; đánh giá thêm workload liên quan và chi phí phụ.
9. **Ghi kết luận.** Nêu giả thuyết được hỗ trợ hay bị bác bỏ, phạm vi đã thử, biến gây nhiễu và giới hạn của dữ liệu.

Đừng tối ưu chỉ vì một toán tử có tên `Seq Scan`, `Table Scan` hoặc `Sort`. Một scan có thể là cách đọc hiệu quả nhất nếu cần phần lớn dữ liệu; sort có thể xử lý một tập nhỏ; index lookup lặp lại có thể đắt hơn scan. Quyết định cần dựa trên lượng công việc thực tế và mục tiêu của workload.

## 9. Cảnh báo khi lấy kế hoạch thực tế

Kế hoạch thực tế thường cần thực thi câu SQL. Vì vậy, nó có thể tạo tải CPU, I/O, giữ khóa, chiếm bộ nhớ và làm thay đổi dữ liệu giống như lần chạy thông thường.

Đặc biệt lưu ý:

- `EXPLAIN ANALYZE` trong PostgreSQL thực thi câu lệnh. Với `INSERT`, `UPDATE` hoặc `DELETE`, dữ liệu có thể bị thay đổi.
- Kế hoạch thực tế trong công cụ khác cũng có thể yêu cầu chạy câu lệnh, kể cả khi giao diện chỉ gọi thao tác đó là “include actual plan”.
- Không chạy câu lệnh ghi hoặc thao tác có tác động ngoài trên môi trường sản xuất chỉ để lấy kế hoạch nếu chưa đánh giá tác động.
- Một transaction rollback không phải lúc nào cũng hoàn tác mọi tác động: sequence, lời gọi bên ngoài, trigger có side effect hoặc tác động không transactional có thể vẫn tồn tại; transaction cũng có thể giữ khóa và tạo tải.
- Truy vấn đọc lớn vẫn có thể làm tăng I/O, CPU và ảnh hưởng người dùng khác.
- Kế hoạch và số liệu runtime có thể chứa literal hoặc thông tin nhạy cảm; xử lý và chia sẻ theo chính sách bảo vệ dữ liệu.

Ưu tiên môi trường thử nghiệm có dữ liệu đại diện. Nếu cần đo trên hệ thống thật, hãy chọn truy vấn đọc an toàn, giới hạn phạm vi, dùng thời điểm phù hợp và tuân thủ quy trình vận hành. Xác định trước cách dừng nếu câu lệnh gây tải ngoài dự kiến.

## 10. Những giới hạn cần hiểu khi diễn giải kế hoạch

### 10.1. Kế hoạch phụ thuộc tham số và trạng thái hệ thống

Một truy vấn có thể nhận tham số khác nhau về độ chọn lọc. Với một khách hàng có vài đơn hàng, index seek có thể phù hợp; với khách hàng có hàng triệu đơn hàng, scan hoặc một phương án khác có thể hiệu quả hơn. Một kế hoạch được biên dịch hoặc đo với một tham số không nhất thiết tối ưu cho mọi tham số.

Ngoài tham số, kế hoạch còn chịu ảnh hưởng của thống kê, phiên bản hệ quản trị, cấu hình, kiểu dữ liệu, trạng thái cache, mức đồng thời và tài nguyên sẵn có. Khi vấn đề chỉ xuất hiện ở một nhóm tham số, hãy phân nhóm workload và kiểm tra kế hoạch cho từng nhóm đại diện.

### 10.2. Thời gian trong kế hoạch không phải lúc nào cũng cộng được

Trong kế hoạch có thực thi song song hoặc pipeline, các toán tử có thể chạy chồng lấp. Thời gian hiển thị tại các nút có thể là thời gian riêng, thời gian tích lũy hoặc trung bình theo vòng lặp tùy hệ quản trị. Cộng tất cả thời gian của mọi nút có thể tạo ra con số lớn hơn thời gian thực tế của câu lệnh.

Hãy đọc chú giải của công cụ, xác định thời gian ở mức toán tử hay câu lệnh, và đối chiếu với thời gian đo từ ứng dụng. Nếu ứng dụng ghi nhận độ trễ cao hơn nhiều so với thời gian thực thi trong kế hoạch, phần chênh lệch có thể nằm ở mạng, hàng đợi connection pool, thời gian lấy kết nối, serialization hoặc các bước ở tầng ứng dụng.

### 10.3. Kế hoạch không hiển thị mọi loại chờ

Một kế hoạch có thể cho biết truy vấn đọc nhiều dữ liệu hoặc thực hiện nhiều vòng lặp, nhưng không phải lúc nào cũng chỉ rõ thời gian bị mất do chờ khóa, chờ mạng lưu trữ, giới hạn I/O hoặc tranh chấp tài nguyên. Để xác định nguyên nhân, kết hợp wait events, blocking sessions, thống kê I/O, log truy vấn và telemetry của hệ điều hành hoặc nền tảng lưu trữ.

### 10.4. Cảnh báo và thông tin ước lượng cần được đọc đúng ngữ cảnh

Một cảnh báo spill, memory grant hoặc implicit conversion là tín hiệu cần điều tra, không phải kết luận tự động rằng nó là nút thắt chính. Ví dụ, một sort nhỏ spill trong truy vấn hiếm có thể ít quan trọng hơn một lookup đơn giản được thực hiện hàng triệu lần mỗi phút. Ưu tiên theo tác động lên workload và mục tiêu dịch vụ.

## 11. Ví dụ tổng hợp: ước lượng sai dẫn đến join tốn kém

Giả sử truy vấn kết hợp `customers` với `orders` để lấy đơn hàng của một nhóm khách hàng. Kế hoạch ước lượng cho rằng bộ lọc trên `customers` chỉ trả về 5 hàng và chọn nested loop. Kế hoạch thực tế ghi nhận 60.000 hàng đầu vào; toán tử bên trong được gọi rất nhiều lần và thời gian tăng mạnh.

Phân tích theo trình tự:

1. Tìm nút đầu tiên có estimated rows khác xa actual rows.
2. Kiểm tra điều kiện lọc, phân bố giá trị và thống kê của bảng `customers`.
3. Xác định tham số gây ra sai lệch: giá trị phổ biến, hiếm hay một nhóm dữ liệu lệch.
4. Kiểm tra số loops và số hàng được xử lý ở phía trong nested loop.
5. Xem xét cập nhật thống kê hoặc cải thiện thông tin thống kê nếu nguyên nhân là ước lượng sai.
6. Nếu cần, thử cách viết truy vấn hoặc cấu trúc chỉ mục khác trong thí nghiệm riêng.
7. Đo lại với cả tham số phổ biến và hiếm, đồng thời kiểm tra các workload liên quan.

Không nên ép một thuật toán join cụ thể chỉ vì nó nhanh hơn trên một bộ tham số. Mục tiêu là giúp bộ tối ưu có đủ thông tin để chọn kế hoạch phù hợp với phân bố workload, hoặc thiết kế cách thực thi xử lý được các nhóm tham số khác nhau.

## 12. Bài tập tự kiểm tra

### Bài tập 1: Chọn loại kế hoạch phù hợp

Bạn cần xem bộ tối ưu dự định truy cập bảng `orders` bằng chỉ mục nào nhưng chưa muốn chạy truy vấn trên dữ liệu lớn.

**Câu hỏi:** nên bắt đầu bằng kế hoạch ước lượng hay kế hoạch thực tế? Vì sao?

**Gợi ý trả lời:** bắt đầu bằng kế hoạch ước lượng để xem phương án dự kiến mà không thực thi truy vấn. Khi cần biết số hàng và thời gian thực tế, có thể lấy kế hoạch thực tế trong môi trường phù hợp sau khi đánh giá tác động thực thi.

### Bài tập 2: Phát hiện sai lệch cardinality

Một nút lọc có estimated rows = 20 nhưng actual rows = 50.000. Nút phía trên dùng nested loop và thực hiện hàng chục nghìn lần truy cập vào bảng khác.

**Câu hỏi:** nên điều tra điều gì trước khi thêm chỉ mục mới?

**Gợi ý trả lời:** tìm nguyên nhân ước lượng sai tại nút lọc: thống kê, histogram, phân bố dữ liệu, tương quan cột và giá trị tham số. Sau đó kiểm tra loops và lượng công việc ở nhánh bên trong. Chỉ mục mới không tự động sửa được cardinality estimate sai.

### Bài tập 3: Diễn giải toán tử scan

Một truy vấn cần trả về 75% số hàng trong bảng. Kế hoạch ước lượng chọn sequential scan, trong khi bạn dự định tạo chỉ mục để tránh scan.

**Câu hỏi:** có thể kết luận bộ tối ưu chọn sai chỉ vì nó dùng sequential scan không?

**Gợi ý trả lời:** không. Nếu truy vấn cần phần lớn hàng, đọc tuần tự có thể ít tốn kém hơn việc đi qua chỉ mục rồi truy cập bảng nhiều lần. Cần xem lượng dữ liệu, số trang, chi phí thực tế và workload trước khi quyết định.

### Checklist khi đọc execution plan

- [ ] Đã xác định đây là kế hoạch ước lượng hay kế hoạch thực tế.
- [ ] Đã hiểu cách công cụ hiển thị estimated rows, actual rows và loops.
- [ ] Đã lần theo cây toán tử từ nguồn dữ liệu đến kết quả.
- [ ] Đã kiểm tra scan, seek, lookup, join, sort, aggregate và filter trong ngữ cảnh workload.
- [ ] Đã tìm nút đầu tiên có chênh lệch lớn giữa số hàng ước lượng và thực tế.
- [ ] Đã xem thời gian, I/O, bộ nhớ, spill và các cảnh báo runtime có liên quan.
- [ ] Đã đối chiếu tham số, thống kê, trạng thái cache và mức tải lúc đo.
- [ ] Đã kết hợp kế hoạch với wait events và telemetry khi cần.
- [ ] Đã đánh giá tác động của việc thực thi câu lệnh trước khi lấy kế hoạch thực tế.
- [ ] Đã đo lại sau thay đổi bằng workload và điều kiện có thể so sánh.

Kế hoạch ước lượng cho biết bộ tối ưu dự định làm gì; kế hoạch thực tế cho biết một lần chạy đã thực hiện ra sao. Khi so sánh đúng hai nguồn thông tin này, kỹ sư có thể phát hiện sai lệch thống kê, hiểu chi phí của từng toán tử, chọn hướng tối ưu phù hợp và kiểm chứng kết quả bằng dữ liệu thay vì chỉ dựa vào tên toán tử hoặc cảm giác truy vấn đã nhanh hơn.
