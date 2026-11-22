# BRIN và dữ liệu lớn có tương quan với vị trí lưu trữ

Với bảng có hàng trăm triệu hoặc hàng tỷ dòng, một chỉ mục B-tree có thể chiếm nhiều dung lượng và tạo thêm chi phí cho mỗi lần ghi. Nếu dữ liệu được lưu theo thứ tự có quan hệ chặt chẽ với một cột, chẳng hạn bản ghi mới luôn được thêm theo thời gian, hệ quản trị có thể dùng một chỉ mục nhỏ hơn để loại bỏ phần lớn vùng dữ liệu không liên quan. Trong PostgreSQL, một lựa chọn dành cho kiểu workload này là BRIN (Block Range INdex).

BRIN phù hợp khi giá trị của cột có tương quan với vị trí vật lý của dòng trong bảng. Ví dụ, các sự kiện được ghi gần theo thứ tự occurred_at thường nằm trong các trang gần nhau; một truy vấn tìm sự kiện trong một khoảng thời gian có thể bỏ qua phần lớn các vùng trang cũ hoặc mới. BRIN lưu tóm tắt cho từng nhóm trang thay vì lưu một mục chỉ mục cho từng dòng.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Bài học này giải thích cách BRIN hoạt động, vai trò của tương quan vật lý, cách chọn kích thước vùng trang, cách duy trì summary, và cách so sánh BRIN với B-tree hoặc quét tuần tự bằng số liệu thực tế.

## 1. BRIN là gì và giải quyết vấn đề nào?

BRIN là viết tắt của Block Range INdex. Một chỉ mục BRIN lưu thông tin tóm tắt về các nhóm trang liên tiếp trong heap table. Với opclass minmax phổ biến, summary của mỗi vùng chứa giá trị nhỏ nhất và lớn nhất của cột trong vùng đó.

Ví dụ, một bảng events được nạp gần theo thứ tự thời gian. Giả sử cứ 128 trang dữ liệu được gom thành một block range. BRIN có thể lưu:

| Vùng trang | Giá trị occurred_at nhỏ nhất | Giá trị occurred_at lớn nhất |
|---|---|---|
| 0–127 | 2026-01-01 00:00 | 2026-01-01 08:10 |
| 128–255 | 2026-01-01 08:10 | 2026-01-01 16:25 |
| 256–383 | 2026-01-01 16:25 | 2026-01-02 00:40 |
| 384–511 | 2026-01-02 00:40 | 2026-01-02 08:55 |

Nếu truy vấn tìm sự kiện trong khoảng ngày 2026-01-01, BRIN có thể xác định các vùng chắc chắn không chứa giá trị phù hợp và loại bỏ chúng. Những vùng có khoảng min/max giao với điều kiện được đưa vào bước truy cập bảng để kiểm tra dòng thực tế.

BRIN không lưu vị trí chính xác của mọi dòng khớp. Nó giúp xác định những vùng trang có khả năng chứa dữ liệu phù hợp. Vì vậy, kết quả từ BRIN có tính chất lossy ở mức block range và cần kiểm tra điều kiện trên các dòng được đọc.

### BRIN phù hợp với loại bảng nào?

BRIN thường hữu ích khi:

- Bảng rất lớn và có nhiều trang dữ liệu.
- Giá trị của cột có tương quan cao với thứ tự vật lý của dòng.
- Dữ liệu thường được thêm theo thời gian hoặc theo một khóa tăng dần.
- Truy vấn lọc theo khoảng giá trị và chỉ cần đọc một phần vùng dữ liệu.
- Chi phí lưu trữ và cập nhật chỉ mục cần thấp so với một chỉ mục ghi nhận từng dòng.

Các ví dụ điển hình gồm bảng log, sự kiện, telemetry, lịch sử giao dịch, dữ liệu cảm biến hoặc bảng fact được nạp theo lô có thứ tự.

BRIN không phải lựa chọn mặc định cho mọi bảng lớn. Nếu các giá trị bị trộn ngẫu nhiên trên toàn bảng, summary min/max của mỗi vùng có thể bao phủ gần như toàn bộ miền giá trị. Khi đó rất ít vùng bị loại bỏ và BRIN mất lợi thế.

## 2. Tương quan giữa giá trị và vị trí vật lý

Khả năng loại bỏ block range phụ thuộc vào việc các dòng có được lưu gần nhau theo giá trị của cột hay không. Đặc tính này được gọi là physical correlation.

### Tương quan cao

Nếu bảng được nạp theo occurred_at tăng dần, các trang đầu thường chứa thời điểm cũ và các trang sau chứa thời điểm mới. Với mỗi vùng trang, khoảng min/max tương đối hẹp. Truy vấn tìm một ngày cụ thể chỉ cần đọc một vài vùng lân cận.

Tương quan cao không bắt buộc phải tăng theo chiều dương. Nếu dữ liệu được lưu theo thứ tự giảm dần, hệ số tương quan có thể gần -1 nhưng mức tương quan tuyệt đối vẫn cao. Cả thứ tự tăng và giảm đều có thể giúp BRIN loại bỏ vùng dữ liệu.

### Tương quan thấp

Nếu dữ liệu được ghi theo thứ tự ngẫu nhiên, mỗi block range có thể chứa cả giá trị rất nhỏ lẫn rất lớn. Summary min/max của nhiều vùng sẽ chồng lấn trên phần lớn miền giá trị. Truy vấn theo một khoảng nhỏ có thể vẫn phải đọc nhiều vùng.

Ví dụ, nếu mỗi block range chứa sự kiện của nhiều năm khác nhau, summary của nó có thể là từ năm 2020 đến năm 2026. Truy vấn tìm sự kiện trong một ngày năm 2024 không thể loại bỏ vùng đó chỉ dựa trên min/max.

### Xem thống kê correlation trong PostgreSQL

PostgreSQL cung cấp trường correlation trong view pg_stats. Có thể kiểm tra như sau:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'events'
  AND attname = 'occurred_at';
~~~

correlation mô tả mức tương quan giữa thứ tự giá trị cột và thứ tự vật lý của dòng. Giá trị gần 1 hoặc -1 cho thấy tương quan mạnh; giá trị gần 0 cho thấy tương quan yếu.

Đây là thống kê lấy mẫu và được cập nhật bởi ANALYZE. Nó hữu ích để đánh giá ban đầu nhưng không thay thế việc xem execution plan và số trang thực tế phải đọc. Một bảng có thể có tương quan tốt ở một phần dữ liệu nhưng kém ở phần khác do backfill, cập nhật hoặc cách nạp dữ liệu.

## 3. Cấu trúc summary và cách BRIN loại bỏ vùng trang

Trong PostgreSQL, BRIN quản lý các summary theo block range. Chỉ mục có cấu trúc ánh xạ để tìm summary tương ứng với vùng trang và các tuple tóm tắt mô tả giá trị trong vùng.

Quy trình khái quát khi thực thi truy vấn:

1. Optimizer xác định BRIN có thể hỗ trợ điều kiện lọc.
2. BRIN đọc các summary của những block range liên quan.
3. So sánh điều kiện truy vấn với summary để xác định vùng có thể chứa dòng phù hợp.
4. Loại bỏ các vùng mà summary chứng minh chắc chắn không khớp.
5. Trả các vùng có khả năng khớp cho bước bitmap heap scan.
6. Đọc các trang dữ liệu và kiểm tra lại điều kiện trên dòng thực tế.

Sơ đồ khái niệm:

~~~text
Điều kiện: occurred_at trong một khoảng thời gian
                    |
                    v
             Đọc BRIN summary
                    |
          +---------+---------+
          |                   |
          v                   v
  Vùng chắc chắn       Vùng có thể khớp
  không phù hợp               |
          |                   v
          v             Bitmap Heap Scan
     Bỏ qua vùng               |
                              v
                       Recheck điều kiện
                              |
                              v
                         Trả dòng khớp
~~~

### Vì sao BRIN có thể nhỏ hơn B-tree?

B-tree thường lưu các khóa và tham chiếu dòng hoặc trang ở độ chi tiết cao. BRIN chỉ lưu tóm tắt cho một nhóm trang. Nếu một bảng có hàng trăm triệu dòng và mỗi summary đại diện cho nhiều trang, số lượng summary ít hơn rất nhiều số dòng.

Điều này giúp BRIN có dung lượng nhỏ và chi phí cập nhật thấp. Tuy nhiên, đổi lại BRIN không xác định chính xác từng dòng ngay từ chỉ mục. Truy vấn vẫn phải đọc các block range có khả năng phù hợp và kiểm tra lại điều kiện.

### False positive là điều bình thường

Nếu summary của vùng là min = 10 và max = 100, truy vấn tìm value = 50 sẽ chọn vùng đó. Nhưng có thể không có dòng nào trong vùng mang giá trị 50. BRIN vẫn phải trả vùng vì summary không đủ thông tin để chứng minh không có dòng phù hợp.

Đây là false positive ở mức vùng trang. Nó không làm sai kết quả vì điều kiện được kiểm tra lại trên dữ liệu thực tế. Tỷ lệ false positive cao làm tăng số block phải đọc và chi phí CPU.

## 4. Minmax: summary theo giá trị nhỏ nhất và lớn nhất

BRIN minmax lưu min và max cho từng block range. Với điều kiện:

~~~sql
SELECT event_id, occurred_at, payload
FROM events
WHERE occurred_at >= TIMESTAMP '2026-04-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-04-02 00:00:00';
~~~

Một block range có max nhỏ hơn đầu khoảng hoặc min lớn hơn cuối khoảng có thể bị loại bỏ. Các vùng còn lại được đọc để kiểm tra.

Minmax hoạt động tốt khi giá trị trong mỗi block range tập trung trong một khoảng hẹp. Điều đó thường đúng với dữ liệu được nạp theo thời gian, số thứ tự hoặc một khóa tăng dần.

### Khi minmax mất hiệu quả

Giả sử một block range có 128 trang, nhưng các dòng được nạp ngẫu nhiên từ toàn bộ lịch sử. Summary có thể bao phủ từ 2020 đến 2026. Một truy vấn tìm ngày trong năm 2024 vẫn phải xem xét vùng này.

Nếu hầu hết block range đều có min/max bao phủ cùng một miền rộng, BRIN không thể loại bỏ nhiều trang. Chỉ mục vẫn nhỏ nhưng hiệu quả truy cập thấp.

### Điều kiện truy vấn cần tương thích với operator class

BRIN chỉ hỗ trợ các toán tử được operator class của kiểu dữ liệu cung cấp. Minmax thường phù hợp với các phép so sánh như bằng, nhỏ hơn, lớn hơn và khoảng giá trị đối với các kiểu được hỗ trợ.

Để giúp optimizer dùng index, nên viết điều kiện trực tiếp trên cột và dùng kiểu dữ liệu phù hợp. Ví dụ, với timestamp:

~~~sql
WHERE occurred_at >= TIMESTAMP '2026-04-01'
  AND occurred_at <  TIMESTAMP '2026-04-02'
~~~

Cách viết khoảng nửa mở giúp xác định rõ ranh giới ngày và tránh áp dụng hàm lên từng giá trị cột. Một biểu thức như DATE(occurred_at) = ... có thể làm đường truy cập chỉ mục khó được sử dụng nếu không có expression index hoặc hỗ trợ tương ứng.

## 5. Minmax-multi và dữ liệu có nhiều cụm giá trị

Một số workload có tương quan vật lý nhưng mỗi block range chứa nhiều cụm giá trị tách rời. Ví dụ, dữ liệu được nạp theo lô của nhiều tenant hoặc nhiều cảm biến; một vùng trang có thể chứa các khoảng thời gian khác nhau thay vì một khoảng liên tục.

Minmax-multi lưu nhiều khoảng giá trị trong summary thay vì chỉ một min và một max. Nhờ đó, nó có thể biểu diễn các cụm dữ liệu tốt hơn và giảm false positive trong một số trường hợp.

Ví dụ khái niệm:

| Block range | Minmax thông thường | Minmax-multi có thể biểu diễn |
|---|---|---|
| A | 1–10.000 | 1–100, 4.900–5.100, 9.900–10.000 |
| B | 1–10.000 | 20–80, 6.000–6.100, 9.500–9.600 |

Với minmax thông thường, truy vấn tìm giá trị 5.000 phải xem xét vùng A và B vì min/max bao phủ toàn bộ miền. Với minmax-multi, summary có thể loại vùng B nếu các khoảng lưu trữ không giao với điều kiện truy vấn.

Số khoảng được giữ bị giới hạn; khi có quá nhiều cụm, summary vẫn phải hợp nhất hoặc nới rộng để kiểm soát kích thước. Vì vậy minmax-multi có thể cải thiện độ chính xác của summary nhưng không loại bỏ hoàn toàn false positive.

Khả năng hỗ trợ và tên operator class phụ thuộc phiên bản PostgreSQL và kiểu dữ liệu. Trước khi sử dụng, kiểm tra operator class khả dụng trong phiên bản triển khai và đo trên dữ liệu thực tế.

## 6. Tạo chỉ mục BRIN trong PostgreSQL

Ví dụ tạo BRIN cho cột thời gian:

~~~sql
CREATE INDEX idx_events_occurred_at_brin
ON events
USING BRIN (occurred_at);
~~~

Câu lệnh trên dùng operator class mặc định phù hợp với kiểu dữ liệu. PostgreSQL sẽ tạo summary theo block range khi các vùng được tổng hợp.

Có thể cấu hình pages_per_range:

~~~sql
CREATE INDEX idx_events_occurred_at_brin
ON events
USING BRIN (occurred_at)
WITH (pages_per_range = 64);
~~~

pages_per_range xác định số trang heap đại diện bởi một summary. Giá trị nhỏ tạo nhiều summary hơn và thường giúp mô tả dữ liệu chi tiết hơn; đổi lại chỉ mục lớn hơn. Giá trị lớn tạo ít summary hơn và chỉ mục nhỏ hơn; đổi lại các khoảng min/max rộng hơn và có thể làm tăng false positive.

Giá trị mặc định thường là 128 trang trong PostgreSQL, nhưng nên kiểm tra phiên bản và workload đang dùng. Không nên chọn pages_per_range chỉ dựa trên một con số cố định.

### Cân nhắc trước khi tạo

- Bảng có đủ lớn để lợi ích về kích thước index có ý nghĩa không?
- Cột có tương quan với thứ tự vật lý không?
- Truy vấn thường lọc theo khoảng hẹp hay đọc phần lớn bảng?
- Dữ liệu có được append theo thứ tự hay thường xuyên backfill?
- Tỷ lệ cập nhật và xóa có làm summary nhanh chóng mất độ chọn lọc không?
- Kích thước block range có phù hợp với độ rộng dữ liệu và kiểu truy vấn không?

BRIN thường phát huy lợi ích rõ hơn khi bảng lớn, dữ liệu có thứ tự và truy vấn loại bỏ được nhiều block range. Với bảng nhỏ, chi phí quét tuần tự có thể thấp hơn.

## 7. Duy trì và cập nhật summary

Summary phải phản ánh an toàn dữ liệu trong block range. Khi các dòng mới được ghi vào các trang mới, vùng trang có thể chưa có summary ngay lập tức nếu chưa được tổng hợp. Nếu không được summarise, hệ quản trị phải xử lý vùng đó một cách thận trọng, làm giảm lợi ích loại bỏ vùng.

### Tự động summarization

BRIN hỗ trợ tùy chọn autosummarize. Có thể bật khi tạo index:

~~~sql
CREATE INDEX idx_events_occurred_at_brin
ON events
USING BRIN (occurred_at)
WITH (
    pages_per_range = 64,
    autosummarize = on
);
~~~

Autosummarize yêu cầu hệ quản trị gửi yêu cầu tổng hợp khi một block range mới được lấp đầy theo cơ chế của PostgreSQL. Việc xử lý yêu cầu phụ thuộc hoạt động nền và cấu hình; không nên giả định summary xuất hiện ngay lập tức sau từng INSERT.

### Tổng hợp thủ công vùng mới

Có thể yêu cầu tổng hợp các vùng mới chưa có summary bằng hàm:

~~~sql
SELECT brin_summarize_new_values(
    'idx_events_occurred_at_brin'
);
~~~

Hàm trả về số block range được tổng hợp. Có thể dùng khi nạp dữ liệu lớn hoặc khi cần chủ động bảo đảm summary đã được cập nhật trước khi đo workload.

PostgreSQL cũng cung cấp hàm brin_summarize_range để tổng hợp một vùng cụ thể theo block number. Cần xác định đúng chỉ mục và vùng trang theo tài liệu của phiên bản đang sử dụng.

### Khi dữ liệu cũ bị cập nhật hoặc nạp lệch thứ tự

Minmax summary phải bao phủ tất cả giá trị của vùng. Nếu một dòng cũ được cập nhật thành giá trị nằm xa khoảng hiện tại, summary cần được mở rộng để không bỏ sót dòng. Điều này có thể khiến vùng trở nên kém chọn lọc.

Nếu workload thường xuyên nạp dữ liệu lịch sử vào vị trí vật lý mới, các block range có thể chứa giá trị rải rác. Minmax-multi có thể giúp trong một số phân bố nhiều cụm, nhưng cần đo mức cải thiện. Khi thứ tự vật lý không còn phù hợp, cần xem lại chiến lược nạp dữ liệu, phân vùng hoặc cách tổ chức bảng.

## 8. BRIN và B-tree: chọn theo workload

BRIN và B-tree giải quyết các bài toán truy cập khác nhau.

| Tiêu chí | BRIN | B-tree |
|---|---|---|
| Cấu trúc | Summary cho nhóm block range | Khóa và tham chiếu ở độ chi tiết cao |
| Kích thước | Thường rất nhỏ với bảng lớn | Thường lớn hơn, phụ thuộc số dòng và độ rộng khóa |
| Tương quan vật lý | Rất quan trọng với minmax | Có thể dùng ngay cả khi dữ liệu không được lưu theo thứ tự khóa |
| Truy vấn theo khoảng | Tốt khi khoảng giá trị tương ứng ít block range | Tốt khi index range scan chọn lọc |
| Truy vấn bằng một khóa | Có thể phải đọc cả block range và recheck | Thường phù hợp hơn cho point lookup |
| Thứ tự kết quả | Không cung cấp thứ tự khóa như B-tree | Có thể trả dòng theo thứ tự khóa |
| Chi phí ghi | Thường thấp | Thường cao hơn do duy trì mục chỉ mục cho khóa |
| False positive | Có thể cao do summary ở mức vùng | Thường xác định vị trí dòng chính xác hơn |
| Unique constraint | Không dùng để bảo đảm uniqueness | Có thể hỗ trợ unique index |

### Khi BRIN thường phù hợp

- Tìm dữ liệu theo khoảng thời gian trong bảng log hoặc sự kiện.
- Quét một vùng lớn nhưng chỉ cần loại bỏ nhiều đoạn trang không liên quan.
- Bảng append-only hoặc dữ liệu được nạp gần theo thứ tự khóa.
- Muốn giảm dung lượng chỉ mục cho bảng rất lớn.

### Khi B-tree thường phù hợp

- Truy vấn point lookup cần tìm một vài dòng.
- Dữ liệu không có tương quan vật lý với cột lọc.
- Truy vấn cần ORDER BY theo khóa và LIMIT nhỏ.
- Cần unique constraint.
- Truy vấn có độ chọn lọc cao và yêu cầu truy cập dòng chính xác.

Có thể sử dụng cả BRIN và B-tree trên cùng bảng nếu workload có nhiều kiểu truy vấn. Chi phí lưu trữ, cập nhật và bảo trì của tất cả chỉ mục cần được đánh giá tổng thể.

## 9. BRIN kết hợp với partitioning

Với bảng rất lớn, partitioning và BRIN có thể bổ trợ nhau.

Ví dụ, bảng events được partition theo tháng dựa trên occurred_at. Partition pruning loại bỏ các partition không giao với khoảng thời gian truy vấn. Trong mỗi partition còn lại, BRIN có thể tiếp tục loại bỏ các block range không phù hợp.

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= TIMESTAMP '2026-04-01'
  AND occurred_at <  TIMESTAMP '2026-05-01';
~~~

Quy trình có thể là:

1. Partition pruning chọn partition tháng 4.
2. BRIN trong partition đó xác định các block range có thể chứa dữ liệu.
3. Bitmap Heap Scan đọc các trang được chọn.
4. Điều kiện được recheck trên dòng thực tế.

Partitioning giảm phạm vi dữ liệu ở mức partition; BRIN giảm phạm vi ở mức block range trong partition. Cả hai đều cần khóa phân vùng và điều kiện truy vấn tương thích để đạt hiệu quả.

Cần cân nhắc kích thước partition. Quá nhiều partition làm tăng chi phí quản lý và lập kế hoạch; partition quá lớn có thể vẫn cần chỉ mục để loại bỏ vùng dữ liệu bên trong.

## 10. Đọc execution plan để kiểm chứng BRIN

Không thể kết luận BRIN hiệu quả chỉ vì index được tạo thành công. Hãy kiểm tra optimizer có chọn nó và số trang thực tế phải đọc có giảm hay không.

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= TIMESTAMP '2026-04-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-04-02 00:00:00';
~~~

Một kế hoạch có thể có dạng:

~~~text
Bitmap Heap Scan on events
  Recheck Cond: (occurred_at >= ... AND occurred_at < ...)
  -> Bitmap Index Scan on idx_events_occurred_at_brin
       Index Cond: (occurred_at >= ... AND occurred_at < ...)
~~~

Các trường cần đọc:

- **Bitmap Index Scan:** xác nhận BRIN được sử dụng và xem số dòng/vị trí được đưa vào bitmap theo cách hiển thị của plan.
- **Bitmap Heap Scan:** xem số dòng thực tế, thời gian và số vòng lặp.
- **Recheck Cond:** điều kiện được kiểm tra lại trên dữ liệu heap.
- **Rows Removed by Index Recheck:** số dòng được đọc nhưng không thỏa điều kiện sau recheck.
- **Buffers:** số buffer hit/read và lượng trang được truy cập.
- **Planning Time và Execution Time:** phân biệt thời gian lập kế hoạch với thời gian chạy.

Một BRIN có thể trả về nhiều block range và có số dòng bị loại sau recheck lớn. Điều đó không nhất thiết là lỗi correctness; nó cho thấy summary chưa đủ chọn lọc cho workload.

### So sánh với sequential scan và B-tree

Để đánh giá đúng, hãy so sánh:

1. Kế hoạch dùng BRIN.
2. Kế hoạch dùng B-tree nếu có đường truy cập phù hợp.
3. Sequential scan khi tỷ lệ dữ liệu cần đọc lớn.

Nếu cần tắt một loại scan để khảo sát kế hoạch thay thế, chỉ thực hiện trong phiên thử nghiệm và hiểu rằng thay đổi planner setting không phản ánh lựa chọn mặc định của hệ thống. Không dùng cấu hình ép buộc trong production chỉ để chứng minh một chỉ mục có lợi.

Hãy đo cùng tham số, cùng dữ liệu, cùng trạng thái cache và mức tải tương đương. Một lần chạy nhanh hơn do dữ liệu đã nằm trong cache không đủ để kết luận chỉ mục mới tốt hơn.

## 11. Điều chỉnh pages_per_range

pages_per_range là một trong những quyết định quan trọng khi thiết kế BRIN.

### Range nhỏ hơn

- Có nhiều summary hơn.
- Mỗi summary đại diện ít trang, nên min/max thường hẹp hơn.
- Có thể loại bỏ nhiều vùng hơn khi truy vấn chọn lọc.
- Chỉ mục lớn hơn và có thêm công việc duy trì summary.

### Range lớn hơn

- Có ít summary hơn.
- Chỉ mục thường nhỏ hơn.
- Summary bao phủ khoảng dữ liệu rộng hơn.
- Có thể có nhiều false positive và phải đọc thêm trang heap.

Không có một giá trị phù hợp cho mọi bảng. Có thể thử một vài cấu hình trên bản sao dữ liệu hoặc môi trường staging, sau đó so sánh:

- Kích thước index.
- Số block range được chọn.
- Số heap block đọc.
- Rows Removed by Index Recheck.
- Buffers read/hit.
- Execution time và CPU.
- Chi phí INSERT và cập nhật summary.

Nếu dữ liệu được nạp theo thứ tự rất chặt, range lớn vẫn có thể hoạt động tốt. Nếu mỗi vùng chứa nhiều cụm giá trị, range nhỏ hoặc minmax-multi có thể cải thiện khả năng loại bỏ.

## 12. Ví dụ thiết kế bảng sự kiện lớn

Một hệ thống thu thập telemetry có bảng events với các cột:

~~~sql
CREATE TABLE events (
    event_id      bigint,
    occurred_at   timestamptz NOT NULL,
    source_id     bigint NOT NULL,
    event_type    text NOT NULL,
    payload       jsonb
);
~~~

Dữ liệu chủ yếu được ghi liên tục theo occurred_at. Phần lớn truy vấn lấy sự kiện theo một khoảng thời gian, đôi khi lọc thêm source_id hoặc event_type.

### Tạo BRIN trên thời gian

~~~sql
CREATE INDEX idx_events_occurred_at_brin
ON events
USING BRIN (occurred_at)
WITH (
    pages_per_range = 64,
    autosummarize = on
);
~~~

Sau khi tạo index và thu thập thống kê:

~~~sql
ANALYZE events;
~~~

Có thể kiểm tra correlation trong pg_stats, sau đó chạy truy vấn đại diện bằng EXPLAIN ANALYZE, BUFFERS.

### Khi truy vấn thêm source_id

~~~sql
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-04-02 00:00:00+00'
  AND source_id = 9001;
~~~

BRIN trên occurred_at có thể loại bỏ các vùng thời gian không liên quan. Trong những vùng còn lại, hệ quản trị tiếp tục kiểm tra source_id. Nếu truy vấn theo source_id rất chọn lọc và thường xuyên, một B-tree riêng hoặc chỉ mục ghép có thể cần thiết.

Không nên giả định rằng BRIN trên thời gian thay thế chỉ mục cho mọi điều kiện. Một truy vấn chỉ lọc source_id mà không có thời gian có thể phải xem phần lớn bảng qua BRIN vì summary thời gian không giúp loại bỏ block range.

### Dữ liệu backfill

Nếu ứng dụng thường nạp dữ liệu cũ vào cuối bảng, các block range mới có thể chứa thời gian rất cũ xen lẫn thời gian hiện tại. Minmax summary mở rộng và trở nên kém chọn lọc. Hãy đo lại correlation và false positive sau các đợt backfill; có thể cần thay đổi chiến lược nạp, dùng partition theo thời gian hoặc đánh giá minmax-multi.

## 13. Những sai lầm thường gặp

- **Tạo BRIN chỉ vì bảng rất lớn:** nếu cột không tương quan với thứ tự vật lý, summary có thể không loại bỏ được vùng nào đáng kể.
- **Nhầm correlation cao với dữ liệu luôn tăng:** tương quan mạnh có thể là tăng hoặc giảm; điều quan trọng là giá trị có tập trung theo vùng trang hay không.
- **Chọn pages_per_range quá lớn mà không đo:** index nhỏ hơn nhưng có thể đọc nhiều heap block hơn.
- **Chọn pages_per_range quá nhỏ cho mọi bảng:** summary nhiều hơn làm index lớn và tăng chi phí duy trì mà chưa chắc giảm thời gian.
- **Quên summarization:** vùng mới chưa được tổng hợp có thể làm giảm lợi ích của BRIN.
- **Cho rằng BRIN trả chính xác từng dòng:** BRIN chọn vùng có khả năng khớp và cần recheck trên heap.
- **Dùng BRIN cho point lookup hoặc ORDER BY top-N:** B-tree thường phù hợp hơn nếu cần tìm dòng chính xác hoặc trả dữ liệu theo thứ tự khóa.
- **Bỏ qua backfill và cập nhật ngẫu nhiên:** dữ liệu mới có thể làm summary min/max rộng hơn.
- **Tăng work_mem để xử lý mọi vấn đề:** bộ nhớ không thể khắc phục tương quan vật lý thấp hoặc summary quá rộng.
- **Đánh giá bằng một lần chạy:** cache, tải đồng thời và phân bố tham số có thể làm kết quả sai lệch.
- **Coi BRIN và partitioning là hai lựa chọn loại trừ:** chúng có thể phối hợp ở hai cấp độ loại bỏ dữ liệu khác nhau.

## 14. Quy trình đánh giá BRIN cho workload thực tế

Có thể áp dụng trình tự sau:

1. **Xác định mẫu truy vấn:** ghi lại điều kiện lọc, khoảng giá trị, tần suất, p50/p95/p99 và tỷ lệ dữ liệu trả về.
2. **Đo quy mô bảng:** số dòng, số trang, dung lượng heap và dung lượng chỉ mục hiện tại.
3. **Kiểm tra physical correlation:** xem pg_stats.correlation sau ANALYZE và hiểu cách dữ liệu được nạp.
4. **Xem cách dữ liệu thay đổi:** append-only, backfill, update, delete hoặc batch load có làm trộn giá trị không?
5. **Chọn operator class:** minmax cho dữ liệu có khoảng liên tục theo block; đánh giá minmax-multi khi mỗi vùng có nhiều cụm giá trị và phiên bản hỗ trợ.
6. **Chọn pages_per_range:** thử các mức hợp lý dựa trên độ chọn lọc và dung lượng index.
7. **Tạo và tổng hợp index:** bảo đảm các block range mới được summarise theo chính sách vận hành.
8. **Đọc execution plan:** kiểm tra Bitmap Index Scan, Bitmap Heap Scan, recheck, số heap block và buffers.
9. **So sánh đường truy cập:** BRIN, B-tree và sequential scan với cùng workload.
10. **Đo tác động phụ:** thời gian ghi, dung lượng index, overhead bảo trì và hiệu năng truy vấn khác.
11. **Theo dõi sau triển khai:** correlation, tỷ lệ block được chọn, recheck và latency khi dữ liệu tăng.
12. **Điều chỉnh khi dữ liệu thay đổi:** đánh giá lại sau backfill lớn, thay đổi cách ingest hoặc tăng trưởng đáng kể.

## 15. Checklist trước khi đưa BRIN vào production

- Bảng đủ lớn để BRIN có lợi ích về dung lượng và loại bỏ vùng dữ liệu.
- Cột được lập chỉ mục có tương quan tốt với thứ tự vật lý.
- Truy vấn thực tế dùng các toán tử được BRIN operator class hỗ trợ.
- Dữ liệu mới có cơ chế summarization phù hợp.
- pages_per_range được lựa chọn dựa trên phép đo.
- Execution plan có dùng BRIN cho các truy vấn mục tiêu.
- Số heap block đọc và false positive ở mức chấp nhận được.
- Đã so sánh với B-tree và sequential scan.
- Đã đo cả workload đọc và ghi.
- Đã đánh giá tác động của backfill, update và delete.
- Đã có cách theo dõi khi correlation hoặc selectivity thay đổi.
- Đã lưu lại baseline để so sánh sau khi triển khai.

## Kết luận

BRIN là chỉ mục gọn nhẹ dành cho bảng lớn khi giá trị của cột có tương quan với vị trí vật lý của dòng. Thay vì lưu một mục cho mỗi dòng, BRIN lưu summary cho các block range và loại bỏ những vùng chắc chắn không chứa dữ liệu phù hợp. Minmax phù hợp khi mỗi vùng có khoảng giá trị hẹp; minmax-multi có thể mô tả nhiều cụm giá trị tốt hơn trong những workload được hỗ trợ.

Hiệu quả của BRIN phụ thuộc vào correlation, kích thước block range, chất lượng summary, điều kiện truy vấn và cách dữ liệu tiếp tục được nạp hoặc cập nhật. Hãy kiểm tra thống kê, duy trì summarization, đọc execution plan và so sánh với B-tree hoặc sequential scan bằng cùng điều kiện tải. Đó là cách xác định BRIN có thực sự giảm I/O và chi phí truy cập dữ liệu cho workload hay không.
