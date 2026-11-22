# Phân bố tham số, độ chọn lọc, dữ liệu lệch và các khóa được truy cập nhiều

Hiệu năng của một câu SQL phụ thuộc vào dữ liệu mà câu lệnh thực sự gặp phải và cách ứng dụng phân phối các yêu cầu lên dữ liệu đó. Cùng một câu truy vấn có thể chạy rất nhanh với tham số này nhưng chậm hơn nhiều với tham số khác. Một bảng có hàng triệu dòng cũng không nhất thiết khó truy vấn nếu dữ liệu phân bố đều và điều kiện lọc phù hợp; ngược lại, một bảng nhỏ hơn vẫn có thể trở thành điểm nghẽn nếu phần lớn giao dịch cùng cập nhật một vài bản ghi.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu cơ sở dữ liệu cần dựa trên đo đạc tải, thống kê, kế hoạch thực thi và cơ chế truy cập dữ liệu. Bài học này tập trung vào bốn đặc điểm của khối lượng công việc: phân bố tham số, độ chọn lọc, độ lệch dữ liệu và các khóa được truy cập nhiều (hot keys). Hiểu đúng các đặc điểm này giúp giải thích vì sao bộ tối ưu chọn một kế hoạch chưa phù hợp, vì sao chỉ mục có hiệu quả khác nhau giữa các giá trị tham số, và vì sao một số giao dịch bị tranh chấp dù tổng tải chưa cao.

## 1. Phân biệt bốn khái niệm

### Phân bố tham số

Phân bố tham số mô tả các giá trị thực tế mà ứng dụng truyền vào một câu SQL và tần suất xuất hiện của từng nhóm giá trị. Ví dụ, một API tìm đơn hàng theo tenant có thể nhận tenant nhỏ với vài trăm đơn, tenant lớn với hàng triệu đơn, và tenant rất ít hoạt động với gần như không có dữ liệu.

Nếu câu SQL là:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status;
~~~

thì các giá trị của tenant_id và status không nhất thiết xuất hiện đồng đều. Một số tenant có lượng dữ liệu lớn, một số trạng thái đơn hàng phổ biến hơn hẳn các trạng thái khác. Bộ tối ưu cần ước lượng số dòng phù hợp với từng tổ hợp tham số để chọn cách truy cập dữ liệu.

Phân bố tham số là đặc điểm của đầu vào workload. Nó trả lời câu hỏi: ứng dụng thường hỏi những giá trị nào, theo tỷ lệ nào?

### Độ chọn lọc

Độ chọn lọc (selectivity) biểu thị tỷ lệ dòng thỏa mãn một điều kiện lọc so với tổng số dòng trong phạm vi dữ liệu được xét. Với một bảng có N dòng, nếu điều kiện trả về R dòng thì độ chọn lọc quan sát được có thể biểu diễn:

\[
S = \frac{R}{N}
\]

Ví dụ, điều kiện status = 'CANCELLED' trả về 2.000 dòng trong bảng 1.000.000 dòng thì độ chọn lọc là 0,2%. Điều kiện status = 'COMPLETED' trả về 700.000 dòng thì độ chọn lọc là 70%.

Độ chọn lọc thấp thường có nghĩa điều kiện lọc chỉ chọn một phần nhỏ dữ liệu. Trong nhiều tình huống, chỉ mục có thể giúp tránh đọc phần lớn bảng. Độ chọn lọc cao có nghĩa điều kiện khớp với nhiều dòng; khi phải đọc phần lớn bảng, quét tuần tự có thể rẻ hơn việc đi qua chỉ mục rồi truy cập từng dòng.

Cần phân biệt cách dùng thuật ngữ giữa tài liệu và hệ quản trị: một số nơi gọi tỷ lệ dòng khớp là selectivity, trong khi một số tài liệu dùng thuật ngữ này cho tính phân biệt của cột hoặc xác suất lọc. Khi phân tích, hãy ghi rõ công thức hoặc tỷ lệ đang dùng để tránh hiểu ngược.

Độ chọn lọc có thể được xét cho một điều kiện đơn, một tổ hợp điều kiện, hoặc một phạm vi phân vùng. Hai điều kiện riêng lẻ đều chọn ít dòng nhưng có tương quan mạnh có thể tạo ra số dòng kết hợp rất khác với ước lượng dựa trên giả định độc lập.

### Dữ liệu lệch

Dữ liệu lệch (data skew) là tình trạng giá trị hoặc nhóm giá trị không phân bố đều. Một vài giá trị có thể xuất hiện rất nhiều, trong khi phần lớn giá trị khác xuất hiện ít. Ví dụ:

- Một tenant chiếm 45% số đơn hàng, hàng nghìn tenant khác chia nhau 55% còn lại.
- Trạng thái ACTIVE chiếm phần lớn bản ghi, còn trạng thái ARCHIVED rất hiếm.
- Một số mã sản phẩm bán rất chạy, phần lớn mã còn lại ít giao dịch.
- Dữ liệu theo ngày tập trung mạnh vào vài ngày khuyến mãi hoặc đợt nhập dữ liệu.

Dữ liệu lệch là đặc điểm của nội dung được lưu trong bảng. Nó ảnh hưởng đến độ chọn lọc của tham số và khả năng ước lượng số dòng của bộ tối ưu.

### Khóa được truy cập nhiều (hot key)

Hot key là một giá trị khóa hoặc một vùng dữ liệu nhận tỷ trọng truy cập lớn trong workload. Hot key có thể là một tenant, tài khoản, mã sản phẩm, hàng đợi, bản ghi cấu hình hoặc một dòng tổng hợp. Nhiều phiên cùng đọc hoặc ghi vào khóa đó có thể tạo ra tranh chấp khóa, hàng đợi, điểm nóng CPU hoặc nút thắt ở một phân vùng.

Hot key khác với dữ liệu lệch. Dữ liệu lệch nói về tần suất xuất hiện của giá trị trong dữ liệu lưu trữ; hot key nói về tần suất workload truy cập giá trị đó. Một giá trị có thể xuất hiện rất nhiều nhưng hiếm được truy cập, hoặc chỉ có một dòng nhưng mọi giao dịch đều cập nhật dòng đó.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Phân bố tham số | Ứng dụng truyền những giá trị nào và thường xuyên ra sao? | 60% truy vấn thuộc tenant lớn |
| Độ chọn lọc | Một điều kiện lọc trả về bao nhiêu phần dữ liệu? | Một trạng thái chỉ khớp 0,2% số dòng |
| Dữ liệu lệch | Các giá trị trong cột phân bố đều hay tập trung vào một vài giá trị? | Một tenant sở hữu gần nửa số bản ghi |
| Hot key | Các yêu cầu có tập trung truy cập cùng khóa không? | Nhiều giao dịch đồng thời trừ tồn kho của một sản phẩm |

Bốn khái niệm có liên hệ nhưng không thay thế cho nhau. Cần đo cả phân bố dữ liệu lẫn phân bố truy cập để chẩn đoán chính xác.

## 2. Vì sao cùng một câu SQL có thể có hiệu năng khác nhau?

Giả sử bảng orders có 20 triệu dòng. Tenant A có 8 triệu dòng, Tenant B có 200 dòng. Một truy vấn tìm đơn hàng theo tenant có thể nhận hai giá trị này:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC
LIMIT 50;
~~~

Với tenant B, truy vấn có thể đọc một tập dữ liệu rất nhỏ. Với tenant A, truy vấn phải tìm trong một tập dữ liệu lớn hơn nhiều. Nếu bộ tối ưu ước lượng sai quy mô, nó có thể chọn kế hoạch không phù hợp với một trong hai nhóm.

Một số chiến lược truy cập có chi phí khác nhau:

- **Index seek / index range scan:** phù hợp khi điều kiện lọc chọn một phần nhỏ dữ liệu và chỉ mục có thứ tự hỗ trợ truy vấn.
- **Sequential scan / table scan:** có thể phù hợp khi phải đọc tỷ lệ lớn bảng hoặc bảng nhỏ.
- **Bitmap hoặc kết hợp nhiều chỉ mục:** một số hệ quản trị có thể kết hợp các tập dòng từ nhiều điều kiện.
- **Nested loop:** thường hiệu quả khi tập đầu vào nhỏ và phía tra cứu có chỉ mục phù hợp; có thể rất đắt khi số vòng lặp lớn.
- **Hash join hoặc merge join:** có thể phù hợp với tập dữ liệu lớn, tùy kích thước, thứ tự và tài nguyên.

Không có một loại kế hoạch luôn tốt nhất. Kế hoạch tốt phụ thuộc vào số dòng ước lượng, số dòng thực tế, số lần lặp, lượng dữ liệu phải đọc, bộ nhớ và mức đồng thời.

### Ví dụ về độ chọn lọc thay đổi theo giá trị

Giả sử cột status có phân bố sau:

| Giá trị status | Số dòng | Tỷ lệ |
|---|---:|---:|
| PAID | 7.200.000 | 72% |
| PENDING | 1.800.000 | 18% |
| CANCELLED | 700.000 | 7% |
| REFUNDED | 300.000 | 3% |
| Tổng | 10.000.000 | 100% |

Truy vấn lấy đơn hàng CANCELLED có thể hưởng lợi từ chỉ mục nếu cần một tập nhỏ và truy cập tiếp theo có chọn lọc. Truy vấn lấy PAID có thể phải đọc phần lớn bảng. Nếu chỉ mục có độ bao phủ thấp và mỗi dòng cần truy cập thêm vào bảng, dùng chỉ mục cho PAID có thể tạo nhiều lần truy cập ngẫu nhiên và đắt hơn quét tuần tự.

Nếu workload chỉ thường xuyên truy vấn các đơn PAID gần đây, một chỉ mục phù hợp với tenant, status và created_at có thể có ích. Nhưng thiết kế cuối cùng phải dựa trên truy vấn thực tế, kích thước bảng, thứ tự sắp xếp, tỷ lệ cập nhật và kế hoạch đo được.

## 3. Tương quan giữa các điều kiện lọc

Bộ tối ưu thường phải ước lượng số dòng thỏa mãn nhiều điều kiện cùng lúc. Khi không có thống kê về mối quan hệ giữa các cột, một số hệ quản trị có thể dùng giả định gần độc lập để kết hợp xác suất lọc.

Ví dụ, bảng orders có hai cột tenant_id và region. Nếu dữ liệu được phân bố độc lập, xác suất một dòng thuộc tenant T và region NORTH có thể được ước lượng bằng tích của hai xác suất riêng. Nhưng nếu tenant T chỉ hoạt động ở khu vực NORTH, hai cột có tương quan mạnh. Ước lượng dựa trên độc lập sẽ sai lệch.

Tình huống tương tự xuất hiện với:

- country và postal_code;
- tenant_id và status;
- product_category và product_id;
- created_at và event_type;
- account_id và currency;
- region và warehouse_id.

Khi ước lượng cardinality sai, bộ tối ưu có thể chọn sai thứ tự join, sai thuật toán join, sai chiến lược truy cập hoặc cấp phát bộ nhớ không phù hợp.

### Dấu hiệu nhận biết sai lệch cardinality

Trong execution plan, hãy so sánh số dòng ước lượng (estimated rows) với số dòng thực tế (actual rows) ở từng node. Chênh lệch lớn tại một node đầu vào có thể lan truyền qua các node tiếp theo.

Ví dụ:

- Estimated rows = 100, actual rows = 500.000: hệ quản trị đánh giá thấp tập dữ liệu.
- Estimated rows = 1.000.000, actual rows = 200: hệ quản trị đánh giá cao tập dữ liệu.
- Sai lệch nhỏ ở node đầu nhưng tăng mạnh sau join: có thể có tương quan giữa các cột hoặc quan hệ dữ liệu chưa được mô tả đầy đủ trong thống kê.

Không chỉ nhìn node cuối cùng. Hãy tìm node đầu tiên có sai lệch đáng kể, vì đó thường là nơi ước lượng bắt đầu lệch khỏi dữ liệu thực tế. Cần xét số vòng lặp (loops): actual rows hiển thị theo mỗi lần chạy hoặc tổng hợp tùy định dạng công cụ; hãy đọc đúng ý nghĩa của từng cột trong hệ quản trị đang dùng.

## 4. Thống kê dữ liệu giúp bộ tối ưu hiểu phân bố như thế nào?

Bộ tối ưu truy vấn (query optimizer) không thể quét toàn bộ bảng mỗi lần lập kế hoạch. Hệ quản trị sử dụng thống kê để ước lượng số dòng và chi phí của các phương án.

Các loại thống kê thường gặp gồm:

- **Row count / table cardinality:** số dòng ước lượng của bảng hoặc phân vùng.
- **Distinct count:** số lượng giá trị khác nhau của một cột.
- **Histogram:** mô tả phân bố giá trị theo các khoảng hoặc bucket.
- **Most common values (MCV) / top values:** ghi nhận một số giá trị xuất hiện thường xuyên.
- **Null fraction:** tỷ lệ giá trị NULL.
- **Correlation:** trong một số hệ quản trị, thống kê mô tả mức tương quan giữa thứ tự vật lý của dòng và thứ tự giá trị cột.
- **Extended / multicolumn statistics:** thống kê bổ sung về phụ thuộc hoặc tương quan giữa nhiều cột.

Histogram giúp ước lượng các điều kiện phạm vi như created_at BETWEEN ... AND ...; MCV giúp nhận ra một số giá trị phổ biến; distinct count hỗ trợ ước lượng số dòng cho điều kiện bằng. Thống kê nhiều cột có thể cải thiện ước lượng khi các điều kiện lọc tương quan.

Thống kê có thể lỗi thời khi dữ liệu thay đổi nhanh, sau một đợt nạp dữ liệu lớn, xóa hàng loạt hoặc khi một giá trị phổ biến đột ngột tăng. Cập nhật thống kê là một bước điều tra hợp lý khi execution plan có sai lệch cardinality, nhưng không nên coi đây là giải pháp mặc định cho mọi truy vấn chậm.

### Ví dụ xem thống kê trong PostgreSQL

PostgreSQL lưu thống kê cột có thể xem qua view pg_stats. Ví dụ:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status');
~~~

Các trường most_common_vals và most_common_freqs cho biết một số giá trị phổ biến cùng tần suất ước lượng. histogram_bounds mô tả các ranh giới histogram. Đây là thông tin lấy từ thống kê đã thu thập, không phải phép đếm chính xác tại thời điểm truy vấn.

Có thể cập nhật thống kê bằng ANALYZE trong PostgreSQL:

~~~sql
ANALYZE orders;
~~~

Trong môi trường thực tế, cần cân nhắc tải do thu thập thống kê và chính sách tự động cập nhật của hệ quản trị. Cú pháp, cách lấy mẫu và loại thống kê khác nhau giữa các nền tảng.

## 5. Tham số nhạy cảm với kế hoạch thực thi

Một câu SQL có thể được chuẩn bị một lần và thực thi nhiều lần với các tham số khác nhau. Nếu hệ quản trị tái sử dụng cùng một kế hoạch cho mọi giá trị, kế hoạch đó có thể phù hợp với nhóm tham số phổ biến nhưng kém hiệu quả với nhóm còn lại.

Hiện tượng này thường được gọi là parameter-sensitive plan, parameter sniffing hoặc vấn đề kế hoạch dùng chung, tùy nền tảng.

Ví dụ, truy vấn theo tenant có hai nhóm:

- Tenant nhỏ chỉ có vài trăm đơn.
- Tenant lớn có hàng triệu đơn.

Kế hoạch tối ưu cho tenant nhỏ có thể chọn index seek rồi nested loop. Khi dùng cho tenant lớn, cùng kế hoạch có thể tạo ra rất nhiều lần truy cập chỉ mục và truy cập bảng. Ngược lại, kế hoạch tối ưu cho tenant lớn có thể quét nhiều dữ liệu; khi dùng cho tenant nhỏ, chi phí khởi tạo và đọc dư thừa trở nên không cần thiết.

### Cách nhận diện

- So sánh execution plan của cùng câu SQL với các nhóm tham số khác nhau.
- Ghi nhận actual rows, estimated rows, logical reads, physical reads, CPU và thời gian thực thi.
- Xem lịch sử plan cache hoặc query store nếu hệ quản trị có hỗ trợ.
- Kiểm tra xem một kế hoạch có được dùng cho các giá trị có độ chọn lọc rất khác nhau không.
- Phân nhóm tham số theo quy mô dữ liệu, không chỉ lấy một giá trị đại diện.

Không nên chỉ chạy lại truy vấn với một tham số và kết luận toàn bộ workload. Cần kiểm tra cả giá trị phổ biến, hiếm, biên và các nhóm có quy mô dữ liệu khác nhau.

### Hướng xử lý

Tùy hệ quản trị và bằng chứng, có thể xem xét:

1. Cập nhật thống kê hoặc tăng chất lượng thống kê cho cột bị lệch.
2. Tách các nhóm truy vấn có đặc điểm chọn lọc khác nhau thành các câu SQL hoặc nhánh xử lý riêng.
3. Dùng cơ chế kế hoạch theo tham số hoặc kế hoạch riêng cho một số nhóm giá trị nếu hệ quản trị hỗ trợ và chi phí lập kế hoạch chấp nhận được.
4. Thiết kế chỉ mục phục vụ mẫu truy vấn thực tế.
5. Viết lại điều kiện hoặc cấu trúc truy vấn để optimizer có thể ước lượng và truy cập dữ liệu tốt hơn.
6. Dùng cơ chế gợi ý kế hoạch hoặc hint chỉ sau khi đã đo, hiểu hệ quả và có quy trình theo dõi.

Không nên ép một kế hoạch cố định cho mọi giá trị chỉ vì nó chạy nhanh trong một lần thử. Kế hoạch có thể thay đổi theo dữ liệu, thống kê, phiên bản hệ quản trị, bộ nhớ và tải đồng thời.

## 6. Dữ liệu lệch ảnh hưởng đến thiết kế chỉ mục

Chỉ mục giúp tìm dòng nhanh hơn khi điều kiện lọc đủ chọn lọc và cấu trúc chỉ mục phù hợp với truy vấn. Khi dữ liệu lệch, chỉ mục có thể hữu ích với một số giá trị nhưng ít hữu ích với giá trị khác.

### Chỉ mục ghép và thứ tự cột

Giả sử workload thường truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC
LIMIT 50;
~~~

Một chỉ mục ghép có thể được đánh giá theo dạng:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Đây chỉ là một phương án để phân tích. Thứ tự cột cần phản ánh điều kiện lọc, khả năng chọn lọc, thứ tự sắp xếp và các truy vấn khác cùng sử dụng chỉ mục. Cần kiểm tra khả năng tận dụng tiền tố trái của chỉ mục theo quy tắc của hệ quản trị, đồng thời đo chi phí ghi và dung lượng.

Nếu status có ít giá trị nhưng tenant_id phân bố rất lệch, chỉ mục ghép có thể có hiệu quả khác nhau theo tenant. Nếu một số tenant chiếm phần lớn dữ liệu, chỉ mục vẫn có thể giảm phạm vi tìm kiếm đáng kể hoặc vẫn có thể kém hiệu quả tùy truy vấn, thứ tự cột và lượng dữ liệu cần trả về.

### Chỉ mục có điều kiện hoặc chỉ mục một phần

Nếu ứng dụng thường xuyên truy vấn một tập con nhỏ và ổn định, chỉ mục có điều kiện (partial/filtered index) có thể giảm dung lượng và chi phí duy trì so với chỉ mục toàn bộ bảng.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_pending_by_tenant
ON orders (tenant_id, created_at DESC)
WHERE status = 'PENDING';
~~~

Chỉ mục này chỉ chứa các dòng thỏa mãn điều kiện. Nó có thể hữu ích khi PENDING là nhóm nhỏ và workload thường truy vấn nhóm đó. Nếu PENDING trở thành trạng thái chiếm phần lớn dữ liệu hoặc truy vấn không thể chứng minh điều kiện phù hợp, lợi ích có thể giảm hoặc planner không chọn chỉ mục.

### Chỉ mục bao phủ

Nếu truy vấn chỉ cần một số cột, chỉ mục bao phủ có thể giảm truy cập bảng trong hệ quản trị hỗ trợ. Tuy nhiên, thêm nhiều cột vào chỉ mục làm chỉ mục lớn hơn, tăng chi phí ghi và tiêu thụ bộ nhớ đệm. Hãy ưu tiên các cột lọc và sắp xếp; chỉ thêm cột trả về khi phép đo cho thấy lợi ích đáng kể.

### Không dùng chỉ mục để chữa mọi dạng lệch

Một cột có rất ít giá trị khác nhau, chẳng hạn boolean, thường không tự động là ứng viên tốt cho chỉ mục độc lập. Chỉ mục trên cột có độ phân biệt thấp có thể không giúp khi truy vấn phải đọc phần lớn bảng. Nhưng chỉ mục ghép, chỉ mục một phần hoặc truy vấn có thêm điều kiện khác vẫn có thể hữu ích.

Quyết định dựa trên execution plan, tỷ lệ dòng thực tế được chọn, lượng dữ liệu đọc và workload ghi. Sequential scan không phải lỗi; đó có thể là phương án rẻ nhất với điều kiện lọc trả về nhiều dòng.

## 7. Hot key và tranh chấp khi truy cập đồng thời

Hot key xuất hiện khi nhiều yêu cầu tập trung vào cùng một khóa hoặc vùng dữ liệu. Ví dụ:

- Nhiều khách hàng cùng xem số lượt truy cập của một bài viết nổi bật.
- Nhiều giao dịch cùng cập nhật tồn kho của một sản phẩm bán chạy.
- Một tài khoản tổng hợp nhận mọi khoản ghi của một nhóm lớn người dùng.
- Nhiều worker cùng lấy hoặc cập nhật một bản ghi hàng đợi.
- Một dòng lưu số dư hoặc trạng thái chung bị cập nhật liên tục.

Nếu thao tác chỉ đọc, hot key có thể gây áp lực lên cache, CPU, mạng hoặc một phân vùng dữ liệu. Nếu nhiều giao dịch cùng ghi, chúng có thể phải chờ khóa hoặc tuần tự hóa tại một điểm nóng.

### Dấu hiệu nhận diện

- Thời gian chờ khóa tăng trong khi CPU tổng thể chưa bão hòa.
- Nhiều phiên cùng chờ trên một dòng, trang, khóa logic hoặc phân vùng.
- Một số giá trị khóa chiếm tỷ trọng lớn trong log truy cập hoặc telemetry ứng dụng.
- Throughput không tăng khi tăng số worker vì tất cả cùng tranh một tài nguyên.
- Độ trễ p95/p99 cao hơn nhiều so với p50.
- Một shard hoặc partition chịu tải cao hơn hẳn các shard hoặc partition khác.

Cần phân biệt hot row với hot page hoặc hot partition. Nhiều khóa logic khác nhau vẫn có thể nằm trên cùng trang vật lý hoặc cùng phân vùng và gây tranh chấp ở tầng thấp hơn. Tên wait event và cách đo phụ thuộc hệ quản trị.

### Ví dụ: cập nhật tồn kho

Một sản phẩm đang được khuyến mãi có thể nhận hàng nghìn yêu cầu mua trong một khoảng ngắn. Mọi giao dịch đều thực hiện:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
~~~

Điều kiện cập nhật nguyên tử giúp tránh đọc rồi ghi tách rời gây sai lệch tồn kho, nhưng các giao dịch cùng product_id vẫn có thể tuần tự chờ nhau. Nếu khóa trên dòng tồn kho trở thành điểm nóng, tăng số worker có thể làm hàng đợi dài hơn.

Các hướng thiết kế cần cân nhắc:

- Giữ transaction ngắn và tránh thực hiện xử lý bên ngoài khi đang giữ khóa.
- Gom hoặc điều tiết yêu cầu cập nhật theo lô nếu nghiệp vụ cho phép.
- Dùng hàng đợi để kiểm soát tốc độ cập nhật cho một khóa nóng.
- Phân bổ bộ đếm thành nhiều bucket rồi tổng hợp khi đọc, nếu mô hình nghiệp vụ cho phép và chấp nhận độ trễ nhất quán phù hợp.
- Dùng reservation hoặc mô hình giữ chỗ để kiểm soát cạnh tranh khi bán hàng.
- Thiết kế lại cách biểu diễn dữ liệu để tránh mọi giao dịch cùng ghi một dòng.
- Đặt giới hạn concurrency theo khóa hoặc theo nhóm tài nguyên.

Mỗi kỹ thuật có đánh đổi. Sharding một bộ đếm thành nhiều bucket có thể giảm tranh chấp ghi nhưng làm truy vấn đọc tổng phải cộng nhiều bucket. Hàng đợi giúp điều tiết nhưng có thể tăng độ trễ. Cache giúp giảm tải đọc nhưng không tự giải quyết tranh chấp ghi và cần chính sách nhất quán rõ ràng.

### Phân vùng và sharding có giải quyết hot key không?

Phân vùng (partitioning) giúp chia bảng thành các phần theo khóa hoặc phạm vi để quản lý và truy cập dữ liệu. Sharding phân phối dữ liệu qua nhiều nút. Hai kỹ thuật có thể tăng khả năng mở rộng khi workload được phân bố hợp lý.

Tuy nhiên, nếu mọi yêu cầu đều truy cập cùng một khóa, phân vùng theo chính khóa đó vẫn có thể đưa toàn bộ yêu cầu về một partition hoặc shard. Phân vùng chỉ giúp giảm điểm nóng khi khóa phân phối truy cập được chọn phù hợp hoặc khi dữ liệu nóng được chia nhỏ có chủ đích. Cần đo tải từng partition, số lần chờ và phân bố khóa trước khi quyết định.

Read replica có thể giảm tải truy vấn đọc nếu độ trễ sao chép và yêu cầu nhất quán cho phép, nhưng không chuyển tải ghi khỏi primary theo cách tương tự. Một hot key ghi vẫn cần thay đổi mô hình ghi, điều tiết hoặc phân phối thao tác cập nhật.

## 8. Đo workload theo nhóm tham số và khóa

Một báo cáo tổng hợp theo query fingerprint thường chưa đủ để nhìn thấy vấn đề do phân bố tham số. Hai lần chạy cùng một fingerprint có thể có số dòng đọc và độ chọn lọc rất khác nhau.

Nên bổ sung các góc nhìn sau:

### Nhóm tham số

Chia tham số thành nhóm có đặc điểm dữ liệu tương đồng, ví dụ:

- Tenant nhỏ, trung bình và lớn.
- Trạng thái hiếm và trạng thái phổ biến.
- Khoảng thời gian ngắn và dài.
- Mã sản phẩm ít giao dịch và mã sản phẩm có lượng giao dịch cao.
- Tham số có giá trị NULL, rỗng, biên hoặc không tồn tại.

Không cần ghi lại mọi giá trị tham số thô. Có thể phân nhóm theo quy mô, mức độ phổ biến hoặc bucket để giảm dữ liệu telemetry và hạn chế lưu thông tin nhạy cảm.

### Chỉ số nên theo dõi

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Độ trễ | p50, p95, p99 theo query và nhóm tham số | Nhận biết nhóm giá trị có trải nghiệm chậm |
| Khối lượng | calls, rows returned, rows read hoặc logical reads | Đo tần suất và lượng dữ liệu phải xử lý |
| Tài nguyên | CPU time, buffer reads, physical I/O, temp I/O | Xác định chi phí xử lý và truy cập dữ liệu |
| Kế hoạch | estimated rows, actual rows, loops, plan identifier | Phát hiện sai lệch ước lượng hoặc kế hoạch khác nhau |
| Đồng thời | active sessions, lock wait, transaction age | Phát hiện tranh chấp và giao dịch kéo dài |
| Phân bố | tần suất theo tenant/key/value bucket | Tìm dữ liệu lệch và hot key |
| Phân vùng | throughput, I/O, queue và wait theo partition/shard | Tìm điểm nóng trong kiến trúc phân tán |

Để tìm giá trị xuất hiện phổ biến, có thể dùng thống kê hệ quản trị, log truy vấn hoặc telemetry ở tầng ứng dụng. Với hot key, số lượng dòng trong bảng không đủ; cần đếm tần suất truy cập theo khóa trong một khoảng thời gian. Có thể dùng sampling, histogram hoặc top-K counter để giảm chi phí ghi nhận.

Cần thống nhất cửa sổ đo và tránh so sánh nhóm tham số ở mức tải khác nhau. Nếu nhóm tenant lớn chỉ được đo trong giờ cao điểm còn tenant nhỏ được đo lúc ít tải, kết luận về ảnh hưởng của tham số có thể bị nhiễu.

## 9. Quy trình điều tra một truy vấn nhạy cảm với phân bố dữ liệu

Có thể áp dụng quy trình sau khi một câu SQL chạy nhanh với một số tham số nhưng chậm với các tham số khác.

### Bước 1: Xác định workload thực tế

Thu thập query fingerprint, tần suất gọi, nhóm tham số và khoảng thời gian. Xác định giá trị phổ biến, hiếm, giá trị biên và nhóm có lượng dữ liệu lớn.

### Bước 2: Đo độ chọn lọc thực tế

Với từng nhóm tham số đại diện, đo số dòng phù hợp và lượng dữ liệu phải đọc. So sánh tỷ lệ dòng trả về với tổng số dòng trong phạm vi truy vấn. Đối với nhiều điều kiện lọc, kiểm tra cả tương quan giữa các cột.

### Bước 3: Kiểm tra thống kê

Xem thống kê cột, histogram, giá trị phổ biến, distinct count và thống kê nhiều cột nếu hệ quản trị hỗ trợ. Xác định thống kê có cũ hoặc không đủ chi tiết cho nhóm giá trị lệch hay không.

### Bước 4: So sánh kế hoạch

Chạy hoặc thu thập kế hoạch cho các nhóm tham số khác nhau. Đối chiếu estimated rows với actual rows, node truy cập, join strategy, loops, buffer reads, sort/hash và temporary I/O.

### Bước 5: Xác định điểm nghẽn

Phân biệt chi phí do đọc quá nhiều dữ liệu, kế hoạch không phù hợp, CPU, I/O, bộ nhớ hay tranh chấp khóa. Nếu nhiều yêu cầu cùng tập trung vào một key, phân tích wait theo key và thời gian giữ khóa.

### Bước 6: Chọn thay đổi nhỏ có thể đo

Có thể thử cập nhật thống kê, thay đổi chỉ mục, điều chỉnh cấu trúc truy vấn, tách nhóm tham số, giảm concurrency hoặc thiết kế lại điểm nóng. Chọn một thay đổi có giả thuyết rõ ràng để kết quả có thể giải thích.

### Bước 7: Đo lại và kiểm tra tác động phụ

So sánh cùng nhóm tham số, cùng mức tải và cùng dữ liệu. Đánh giá độ trễ, throughput, tài nguyên, lock wait, dung lượng chỉ mục và hiệu năng của các truy vấn liên quan.

## 10. Ví dụ phân tích tổng hợp

### Tình huống A: Tenant lớn làm truy vấn danh sách chậm

Ứng dụng dùng một câu SQL cho mọi tenant. Với tenant nhỏ, p95 là 25 ms; với tenant lớn, p95 tăng lên 1,8 giây. Kế hoạch của tenant nhỏ dùng index range scan, còn kế hoạch được tái sử dụng cho tenant lớn tạo nhiều lần tra cứu dòng.

Điều tra cho thấy tenant lớn chiếm tỷ lệ dữ liệu rất cao và có phân bố created_at khác với tenant còn lại. Cần so sánh kế hoạch riêng cho từng nhóm, kiểm tra thống kê tenant_id, created_at và khả năng dùng chỉ mục ghép phù hợp. Nếu hệ quản trị đang dùng kế hoạch dùng chung, đánh giá cơ chế kế hoạch theo tham số hoặc tách câu truy vấn cho các nhóm quy mô khác nhau. Sau điều chỉnh, đo riêng tenant nhỏ và tenant lớn để bảo đảm một nhóm không được cải thiện bằng cách làm nhóm kia chậm đi.

### Tình huống B: Trạng thái phổ biến khiến chỉ mục kém hiệu quả

Một báo cáo lọc theo status. Khi status = 'CANCELLED', chỉ vài phần nghìn dòng được trả về và chỉ mục giúp truy vấn nhanh. Khi status = 'PAID', phần lớn bảng được trả về, nhưng kế hoạch vẫn đi qua chỉ mục rồi truy cập bảng nhiều lần.

Phân tích histogram và MCV cho thấy PAID là giá trị phổ biến. Cần xem liệu sequential scan có rẻ hơn không, hoặc truy vấn có thể giới hạn theo tenant và khoảng thời gian để tăng độ chọn lọc. Nếu workload thường truy vấn nhóm hiếm, chỉ mục có điều kiện cho nhóm đó có thể giảm chi phí. Không nên buộc mọi giá trị status đi theo cùng một chiến lược truy cập.

### Tình huống C: Một sản phẩm tạo hot row

Trong đợt khuyến mãi, nhiều phiên cập nhật cùng dòng inventory của một product_id. CPU trung bình còn thấp nhưng lock wait tăng và throughput cập nhật gần như không tăng khi tăng số worker.

Điều tra cho thấy thời gian giữ transaction bao gồm cả bước kiểm tra dịch vụ khác. Rút ngắn transaction giúp giảm thời gian giữ khóa. Nếu tải vẫn tập trung quá cao, có thể đưa yêu cầu cập nhật vào hàng đợi theo sản phẩm hoặc dùng mô hình reservation phù hợp với nghiệp vụ. Sau thay đổi, đo lock wait, số giao dịch hoàn thành mỗi giây, p99 và tính đúng đắn của tồn kho dưới tải đồng thời.

## 11. Những sai lầm thường gặp

- **Chỉ dùng một tham số đại diện:** bỏ qua khác biệt giữa tenant lớn và tenant nhỏ, giá trị phổ biến và giá trị hiếm.
- **Coi bảng có nhiều dòng là dữ liệu lệch:** kích thước bảng và độ lệch phân bố là hai thuộc tính khác nhau.
- **Đồng nhất dữ liệu lệch với hot key:** phân bố giá trị trong bảng không cho biết đầy đủ tần suất truy cập đồng thời.
- **Chỉ xem thời gian trung bình:** nhóm tham số nhỏ có p99 rất cao có thể bị che khuất trong số liệu tổng hợp.
- **Giả định các điều kiện lọc độc lập:** tương quan giữa các cột có thể làm cardinality estimate sai nghiêm trọng.
- **Thêm chỉ mục cho mọi cột có điều kiện WHERE:** chỉ mục có chi phí lưu trữ và ghi, và có thể không hữu ích khi điều kiện chọn phần lớn bảng.
- **Tăng số worker để xử lý hot key:** nhiều worker hơn có thể làm tăng tranh chấp trên cùng một dòng.
- **Chia shard theo khóa đang nóng mà không đo lại:** mọi yêu cầu cùng một khóa vẫn có thể tập trung vào một shard.
- **Chỉ kiểm tra kế hoạch mà không kiểm tra dữ liệu thực tế:** estimated rows có thể khác xa actual rows khi thống kê lỗi thời hoặc dữ liệu lệch.
- **Thay nhiều yếu tố cùng lúc:** khó xác định thay đổi nào tạo ra cải thiện hoặc hồi quy.

## 12. Checklist thực hành

Khi tối ưu truy vấn hoặc workload có dấu hiệu nhạy cảm với phân bố dữ liệu, hãy trả lời:

1. Ứng dụng truyền những nhóm tham số nào và tỷ lệ của từng nhóm ra sao?
2. Có tenant, trạng thái, tài khoản hoặc mã sản phẩm chiếm tỷ lệ dữ liệu lớn bất thường không?
3. Độ chọn lọc thực tế thay đổi thế nào theo từng nhóm tham số?
4. Các điều kiện lọc có tương quan khiến giả định độc lập không còn phù hợp không?
5. Thống kê có phản ánh giá trị phổ biến, histogram, distinct count và dữ liệu mới nhất không?
6. Estimated rows và actual rows sai lệch từ node nào?
7. Kế hoạch thực thi có thay đổi theo tham số không; nếu không thay đổi, kế hoạch dùng chung có phù hợp với tất cả nhóm không?
8. Có một hoặc vài khóa nhận phần lớn lượt đọc/ghi hoặc gây lock wait không?
9. Chỉ mục, phân vùng hoặc cấu trúc truy vấn có phù hợp với workload đọc và ghi thực tế không?
10. Sau điều chỉnh, p95/p99, throughput, tài nguyên và tính đúng đắn của dữ liệu có được cải thiện ở cùng mức tải không?

## Kết luận

Phân bố tham số cho biết ứng dụng thường truy vấn những giá trị nào; độ chọn lọc cho biết điều kiện lọc giữ lại bao nhiêu dòng; dữ liệu lệch mô tả sự tập trung của giá trị trong bảng; hot key mô tả sự tập trung truy cập của workload vào một khóa hoặc vùng dữ liệu. Những đặc điểm này ảnh hưởng trực tiếp đến ước lượng cardinality, lựa chọn kế hoạch, hiệu quả chỉ mục và mức tranh chấp khi nhiều giao dịch chạy đồng thời.

Một phương pháp tối ưu đáng tin cậy cần đo riêng từng nhóm tham số và khóa, so sánh số dòng ước lượng với số dòng thực tế, kiểm tra thống kê và execution plan, rồi mới chọn thay đổi phù hợp. Kết quả cần được xác minh dưới cùng điều kiện tải và trên toàn bộ nhóm workload liên quan. Đây là cách xây dựng cơ sở dữ liệu hoạt động ổn định khi quy mô dữ liệu, mức độ tập trung truy cập và số giao dịch đồng thời tiếp tục tăng.

