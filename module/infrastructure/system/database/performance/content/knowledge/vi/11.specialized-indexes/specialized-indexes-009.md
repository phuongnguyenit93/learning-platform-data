# Tiêu chí lựa chọn loại chỉ mục theo tính năng của từng hệ quản trị

Không có một loại chỉ mục phù hợp cho mọi truy vấn. B-tree thường là lựa chọn mặc định tốt cho tìm kiếm bằng, tìm kiếm theo khoảng và sắp xếp; nhưng truy vấn tìm văn bản, dữ liệu không gian, mảng, dữ liệu theo thời gian hoặc phân tích trên tập dữ liệu lớn có thể cần cấu trúc chuyên biệt. Mỗi hệ quản trị hỗ trợ một tập loại chỉ mục, toán tử và tùy chọn khác nhau, vì vậy lựa chọn cần dựa trên workload, kiểu dữ liệu, điều kiện truy vấn, đặc tính lưu trữ và chi phí vận hành của đúng sản phẩm đang dùng.

Bài học thuộc chương **Chỉ mục chuyên biệt** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Nội dung module bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, việc chọn chỉ mục chuyên biệt phải bắt đầu từ truy vấn thực tế và được xác nhận bằng execution plan, số liệu tải, độ trễ, thông lượng và chi phí ghi/bảo trì.

## 1. Chọn chỉ mục từ nhu cầu truy cập dữ liệu

Chỉ mục là cấu trúc phụ được duy trì để tìm hoặc sắp xếp dữ liệu hiệu quả hơn. Khi truy vấn phù hợp với cấu trúc chỉ mục, hệ quản trị có thể đọc ít trang hơn, giảm lượng dữ liệu phải xử lý hoặc tránh một bước sắp xếp. Đổi lại, chỉ mục chiếm dung lượng, cần cập nhật khi dữ liệu thay đổi và có thể làm tăng chi phí ghi, backup, phục hồi và bảo trì.

Trước khi chọn loại chỉ mục, hãy mô tả workload bằng các câu hỏi:

1. **Truy vấn tìm gì?** Một giá trị chính xác, một khoảng số/thời gian, từ khóa, chuỗi con, vùng địa lý, phần tử trong JSON/mảng hay tổng hợp trên nhiều hàng?
2. **Điều kiện có độ chọn lọc ra sao?** Thường trả về một vài hàng, một tỷ lệ nhỏ, hay phần lớn bảng?
3. **Có cần thứ tự không?** Truy vấn có `ORDER BY`, phân trang, `GROUP BY` hoặc yêu cầu đọc theo thứ tự thời gian không?
4. **Dữ liệu thay đổi thế nào?** Tỷ lệ đọc/ghi, tốc độ thêm dữ liệu, cập nhật khóa, xóa và mức đồng thời ra sao?
5. **Dữ liệu có đặc tính nào?** Bảng nhỏ hay rất lớn, dữ liệu có thứ tự theo thời gian, phân bố lệch, giá trị lặp nhiều hay có kích thước lớn?
6. **Hệ quản trị hỗ trợ gì?** Loại chỉ mục, operator class, kiểu dữ liệu, tùy chọn và phiên bản có đáp ứng truy vấn không?
7. **Kết quả có đo được không?** Có baseline, truy vấn đại diện, execution plan và chỉ số để xác nhận lợi ích không?

Không nên bắt đầu bằng câu hỏi “loại chỉ mục nào nhanh nhất?”. Hãy bắt đầu bằng “truy vấn cần thao tác nào trên dữ liệu?” rồi chọn cấu trúc có thể hỗ trợ chính thao tác đó.

## 2. Các tiêu chí kỹ thuật quan trọng

### 2.1. Kiểu phép toán và toán tử truy vấn

Mỗi cấu trúc chỉ mục được tối ưu cho một số phép toán nhất định:

| Nhu cầu truy vấn | Cấu trúc thường đáng xem xét | Ví dụ |
|---|---|---|
| So sánh bằng, khoảng, tiền tố và thứ tự | B-tree | `id = ?`, `created_at >= ?`, `ORDER BY name` |
| So sánh bằng trên khóa băm | Hash | `session_token = ?` |
| Kiểm tra nhiều giá trị phân loại có độ lặp cao trong workload đọc | Bitmap | `status = 'ACTIVE'` trong truy vấn phân tích |
| Tìm từ, cụm từ, tiền tố hoặc mức liên quan trong văn bản | Full-text / inverted index | Tìm tài liệu chứa các từ khóa |
| Kiểm tra giao nhau, chứa hoặc lân cận dữ liệu không gian | Spatial index, R-tree hoặc cấu trúc tương đương | Tìm điểm trong vùng hoặc hình học giao nhau |
| Tìm phần tử trong mảng, JSON hoặc tập giá trị | Inverted index như GIN hoặc cấu trúc đa giá trị | `tags @> ...`, kiểm tra key/value |
| Lọc trên bảng rất lớn có dữ liệu vật lý tương quan với một cột | BRIN hoặc min-max index | Quét dữ liệu thời gian được ghi gần theo thứ tự |
| Phân tích nhiều hàng và nhiều cột theo lô | Columnstore / columnar index | Tổng doanh thu theo tháng, nhóm sản phẩm |

Bảng chỉ đưa ra hướng ban đầu. Cùng một phép toán có thể được hỗ trợ bởi nhiều loại chỉ mục, và hệ quản trị có thể chọn scan nếu phạm vi kết quả rộng hoặc chi phí chỉ mục cao.

### 2.2. Độ chọn lọc và số giá trị phân biệt

Độ chọn lọc (selectivity) cho biết điều kiện lọc thu hẹp tập dữ liệu đến mức nào. Chỉ mục thường hữu ích khi nó giúp loại bỏ phần lớn dữ liệu trước khi xử lý tiếp. Một cột có nhiều giá trị phân biệt thường phù hợp với point lookup; một cột chỉ có vài giá trị như `is_active` có thể ít hữu ích cho B-tree nếu mỗi giá trị khớp với một phần lớn bảng.

Tuy nhiên, số giá trị phân biệt không quyết định một mình. Bitmap index có thể kết hợp hiệu quả nhiều điều kiện phân loại trong workload đọc; partial/filtered index có thể lưu chỉ một nhóm hàng hiếm; B-tree trên cột ít giá trị vẫn có ích khi một giá trị rất hiếm hoặc khi nó là tiền tố của chỉ mục ghép phù hợp.

Hãy đo phân bố thật, không chỉ xem số lượng giá trị. Một cột có 100 giá trị có thể phân bố đều hoặc một giá trị chiếm 95% dữ liệu. Histogram và thống kê của hệ quản trị giúp bộ tối ưu ước lượng độ chọn lọc; dữ liệu lệch hoặc thống kê cũ có thể khiến lựa chọn sai.

### 2.3. Tỷ lệ đọc/ghi và chi phí duy trì

Mỗi chỉ mục thêm công việc cho thao tác ghi. Khi thêm hàng, xóa hàng hoặc cập nhật cột liên quan, hệ quản trị phải duy trì các cấu trúc chỉ mục. Với workload ghi cao, nhiều chỉ mục hoặc chỉ mục rộng có thể làm giảm throughput ghi, tăng I/O và gây tranh chấp nội bộ.

Vì vậy:

- Workload đọc nhiều, truy vấn ổn định và chỉ mục nhỏ thường có nhiều cơ hội hưởng lợi.
- Workload ghi nhiều cần hạn chế chỉ mục dư thừa, cột khóa rộng và cấu trúc có chi phí cập nhật cao.
- Chỉ mục chuyên biệt có thể tốn thời gian xây dựng, dung lượng và chi phí cập nhật khác đáng kể so với B-tree.
- Lợi ích của truy vấn mục tiêu phải được cân bằng với ảnh hưởng lên các truy vấn và thao tác ghi khác.

### 2.4. Thứ tự vật lý, tương quan dữ liệu và kích thước bảng

Một số chỉ mục tận dụng tương quan giữa thứ tự lưu trữ vật lý và giá trị của cột. BRIN trong PostgreSQL là ví dụ: nó lưu tóm tắt giá trị theo các dải block, nên rất nhỏ và hiệu quả khi dữ liệu có tương quan vật lý tốt với khóa, chẳng hạn sự kiện được ghi gần theo thời gian. Nếu dữ liệu bị xáo trộn ngẫu nhiên, mỗi dải block có thể chứa phạm vi giá trị rộng và BRIN loại bỏ được ít block.

Columnstore phù hợp với truy vấn phân tích quét nhiều hàng nhưng chỉ cần một số cột, vì dữ liệu theo cột hỗ trợ nén và đọc chọn cột. Với truy vấn giao dịch lấy một hàng theo khóa, B-tree hoặc chỉ mục dạng hàng thường phù hợp hơn.

## 3. B-tree: lựa chọn mặc định cho nhiều truy vấn giao dịch

B-tree hỗ trợ so sánh bằng, so sánh theo khoảng, tiền tố có thể lập phạm vi, và truy vấn cần thứ tự khóa. Nó thường là lựa chọn đầu tiên cho khóa chính, khóa ngoại được tra cứu thường xuyên, điều kiện lọc có chọn lọc và `ORDER BY`.

Ví dụ:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
```

Chỉ mục này có thể hỗ trợ truy vấn lọc equality theo `customer_id`, sau đó quét khoảng `created_at`:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC;
```

B-tree không phải lựa chọn tốt nhất cho mọi truy vấn tìm kiếm. Tìm chuỗi con với ký tự đại diện đầu, tìm văn bản theo mức liên quan hoặc truy vấn không gian phức tạp có thể cần cấu trúc khác. Nếu phạm vi lọc lớn, scan vẫn có thể nhanh hơn.

## 4. Hash index: tìm kiếm bằng khóa bằng

Hash index ánh xạ giá trị khóa qua hàm băm để tìm bucket chứa các mục có giá trị đó. Cấu trúc này hướng đến so sánh bằng (`=`), không duy trì thứ tự khóa như B-tree.

Ví dụ về loại truy vấn có dạng phù hợp:

```sql
SELECT session_id, expires_at
FROM sessions
WHERE session_token = :token;
```

Hash index có thể phù hợp nếu hệ quản trị hỗ trợ loại này cho kiểu dữ liệu và toán tử đang dùng. Nó không hỗ trợ range scan hoặc `ORDER BY` theo thứ tự khóa như B-tree. Xử lý va chạm băm, mở rộng cấu trúc, logging, khả năng phục hồi và giới hạn kiểu dữ liệu phụ thuộc sản phẩm.

Không nên mặc định hash index luôn nhanh hơn B-tree cho equality. B-tree cũng hỗ trợ equality lookup, có thể phục vụ thêm range và order, đồng thời thường có hành vi vận hành quen thuộc hơn. Hãy so sánh bằng execution plan và phép đo trên đúng phiên bản. Trong PostgreSQL, hash index hiện đại có WAL logging và phục hồi được, nhưng khả năng và đặc điểm cụ thể vẫn cần xem tài liệu phiên bản; ở hệ quản trị khác, đặc tính có thể khác.

## 5. Bitmap index: nhiều điều kiện phân loại trong workload đọc

Bitmap index biểu diễn sự hiện diện của giá trị bằng bitmap, trong đó các bit tương ứng với hàng hoặc vị trí dữ liệu. Khi truy vấn kết hợp nhiều điều kiện trên cột có số giá trị phân biệt thấp, hệ quản trị có thể kết hợp bitmap bằng các phép AND/OR để xác định hàng phù hợp.

Ví dụ một kho dữ liệu có các cột `region`, `channel`, `status` với số lượng giá trị hữu hạn và truy vấn phân tích thường lọc kết hợp các cột này. Bitmap có thể tiết kiệm không gian và kết hợp điều kiện hiệu quả trong workload đọc.

Tuy nhiên, bitmap index không phù hợp mặc định cho bảng có cập nhật đồng thời cao. Một cập nhật có thể ảnh hưởng bitmap và khóa phạm vi dữ liệu lớn hơn, tùy cách triển khai. Trong Oracle, bitmap index thường được dùng trong môi trường kho dữ liệu và workload đọc nhiều; cần thận trọng với OLTP có nhiều phiên cập nhật cùng lúc. Không được suy rộng đặc tính này thành một quy tắc chung cho mọi sản phẩm.

Tiêu chí cân nhắc:

- Nhiều truy vấn phân tích kết hợp điều kiện trên các cột phân loại.
- Số giá trị phân biệt thấp hoặc vừa phải và mẫu lọc lặp lại.
- Tỷ lệ cập nhật thấp hoặc dữ liệu chủ yếu đọc.
- Hệ quản trị hỗ trợ bitmap index cho kiểu dữ liệu và workload đó.

## 6. Full-text và inverted index: tìm kiếm nội dung

Tìm kiếm văn bản thường không chỉ là so sánh bằng một chuỗi. Người dùng có thể tìm theo từ, cụm từ, tiền tố, biến thể từ, ngôn ngữ, mức liên quan và toán tử logic. Full-text index thường phân tích văn bản thành token rồi xây dựng cấu trúc đảo (inverted index) ánh xạ token đến tài liệu hoặc hàng chứa token đó.

Ví dụ về nhu cầu:

```sql
SELECT document_id, title
FROM documents
WHERE full_text_matches(content, :search_terms);
```

Tên hàm trên chỉ minh họa ý tưởng; cú pháp thật phụ thuộc hệ quản trị. Full-text index có thể hỗ trợ tìm từ và xếp hạng mức liên quan, trong khi B-tree trên toàn bộ chuỗi thường không đáp ứng tốt truy vấn tìm từ ở bất kỳ vị trí nào.

### 6.1. Tokenization, stemming và ngôn ngữ

Trước khi lập chỉ mục, hệ thống có thể tách văn bản thành token, chuẩn hóa chữ hoa/thường, loại stop words và stemming theo ngôn ngữ. Các quyết định này ảnh hưởng trực tiếp kết quả tìm kiếm. Từ tiếng Việt có dấu, cách tách từ, tên riêng, mã sản phẩm và chuỗi hỗn hợp cần được thử trên cấu hình parser thực tế.

Full-text index không tự động tương đương tìm chuỗi con tùy ý. Nếu yêu cầu tìm một đoạn ký tự nằm giữa từ, có thể cần trigram, n-gram hoặc cơ chế chuyên biệt. Hãy xác định yêu cầu tìm kiếm và kiểm tra chất lượng kết quả, không chỉ thời gian truy vấn.

### 6.2. Các ví dụ hỗ trợ theo hệ quản trị

- PostgreSQL cung cấp kiểu `tsvector`/`tsquery` và GIN hoặc GiST để lập chỉ mục tìm kiếm toàn văn.
- SQL Server cung cấp Full-Text Search với full-text catalog/index và các hàm tìm kiếm tương ứng.
- MySQL cung cấp `FULLTEXT` index cho các engine và kiểu cột được hỗ trợ, với parser và giới hạn theo phiên bản.
- Oracle Text cung cấp khả năng lập chỉ mục và truy vấn văn bản với nhiều cấu hình lexer/filter.

Khả năng tìm kiếm, parser, ngôn ngữ, cú pháp và cách cập nhật index khác nhau. Cần kiểm tra phiên bản, engine lưu trữ, collation và cấu hình ngôn ngữ của môi trường thực tế.

## 7. GIN và GiST trong PostgreSQL: chỉ mục cho kiểu dữ liệu và toán tử chuyên biệt

PostgreSQL hỗ trợ nhiều access method. Hai loại thường gặp ngoài B-tree là GIN và GiST; lựa chọn phụ thuộc operator class và toán tử mà truy vấn sử dụng.

### 7.1. GIN (Generalized Inverted Index)

GIN phù hợp với giá trị chứa nhiều phần tử mà truy vấn cần tìm theo từng phần tử, ví dụ mảng, `jsonb` hoặc `tsvector`. Nó lưu khóa cho các phần tử và danh sách vị trí/tài liệu tương ứng, gần với mô hình inverted index.

Ví dụ chỉ mục cho tìm kiếm toàn văn:

```sql
CREATE INDEX idx_documents_search
ON documents USING GIN (to_tsvector('simple', content));
```

Truy vấn tương ứng cần dùng biểu thức phù hợp với chỉ mục:

```sql
SELECT document_id, title
FROM documents
WHERE to_tsvector('simple', content)
      @@ plainto_tsquery('simple', 'database performance');
```

GIN cũng thường được dùng với `jsonb` và array khi operator class hỗ trợ các toán tử như containment hoặc kiểm tra phần tử. GIN có thể có chi phí cập nhật và dung lượng đáng kể vì một hàng có thể tạo nhiều mục index. Các cơ chế như `fastupdate` và pending list trong PostgreSQL ảnh hưởng đến đặc tính ghi và cần được giám sát theo workload.

### 7.2. GiST (Generalized Search Tree)

GiST là khung cấu trúc cây tổng quát, cho phép operator class định nghĩa cách phân vùng và tìm kiếm dữ liệu. Nó được dùng trong nhiều bài toán như dữ liệu không gian, khoảng giá trị và tìm kiếm gần đúng. GiST không phải một thuật toán duy nhất; hiệu quả phụ thuộc cách operator class biểu diễn dữ liệu và toán tử.

Ví dụ khái niệm dùng extension PostGIS:

```sql
CREATE INDEX idx_places_geom
ON places USING GIST (geom);
```

Chỉ mục này có thể hỗ trợ các truy vấn không gian dùng toán tử tương thích, chẳng hạn kiểm tra bounding box hoặc tìm các đối tượng giao nhau. Với PostGIS, một số hàm quan hệ chính xác thường kết hợp bước lọc ứng viên bằng bounding box từ index rồi kiểm tra hình học chính xác. Cần xem execution plan để xác nhận index condition và bước recheck.

### 7.3. GIN hay GiST?

| Tiêu chí | GIN | GiST |
|---|---|---|
| Mô hình phù hợp | Tập phần tử, token, key/value và inverted lookup | Cây tìm kiếm tổng quát với vùng hoặc biểu diễn có thể phân cấp |
| Ví dụ | Full-text, array, JSONB containment | Spatial, range và một số kiểu tìm kiếm gần đúng |
| Đặc tính truy vấn | Tìm theo phần tử hoặc membership | Tìm theo quan hệ do operator class định nghĩa |
| Chi phí ghi | Có thể cao khi một hàng tạo nhiều entry | Phụ thuộc phân chia cây, độ chồng lấn và operator class |
| Cần kiểm tra | Pending list, kích thước index, recheck và số entry | Độ chọn lọc, độ chồng lấn, recheck và chất lượng operator class |

Không chọn GIN/GiST chỉ dựa trên tên cấu trúc. Phải xác nhận toán tử truy vấn được operator class hỗ trợ và so sánh với workload thật.

## 8. BRIN: chỉ mục tóm tắt cho bảng rất lớn có dữ liệu tương quan vật lý

BRIN (Block Range INdex) trong PostgreSQL lưu tóm tắt giá trị của một cột theo các nhóm block thay vì một entry cho từng hàng. Với cột có giá trị tương quan với thứ tự vật lý của bảng, ví dụ dữ liệu sự kiện thường được thêm theo thời gian, BRIN có thể loại bỏ nhiều nhóm block không chứa giá trị trong khoảng cần tìm.

Ví dụ:

```sql
CREATE INDEX idx_events_created_brin
ON events USING BRIN (created_at);
```

Truy vấn:

```sql
SELECT event_id, created_at, event_type
FROM events
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-10-02 00:00:00';
```

BRIN thường nhỏ hơn nhiều so với B-tree vì lưu tóm tắt theo block range. Nó phù hợp với bảng lớn, dữ liệu có thứ tự vật lý hoặc tương quan tốt và truy vấn lọc theo phạm vi. Nó có thể kém hiệu quả khi dữ liệu bị ghi/xáo trộn ngẫu nhiên, vì nhiều block range có thể có min/max chồng lấn phạm vi truy vấn.

Các yếu tố cần đo gồm `pages_per_range`, độ chọn lọc, số block được loại bỏ, số block phải đọc lại, chi phí recheck và mức tương quan vật lý. BRIN không thay thế B-tree cho point lookup cần định vị một hàng nhanh; nó là công cụ lọc block thô trên dữ liệu lớn.

## 9. Spatial index: truy vấn vị trí và hình học

Dữ liệu không gian như điểm, đường và đa giác có quan hệ phức tạp: chứa, giao nhau, nằm trong bán kính hoặc gần nhất. B-tree có thể sắp xếp tọa độ đơn lẻ, nhưng không mô tả tốt các quan hệ không gian nhiều chiều.

Spatial index thường dùng cấu trúc như R-tree hoặc biến thể, hoặc operator class không gian trên GiST. Nó tổ chức bounding box để nhanh chóng loại bỏ các đối tượng không thể thỏa quan hệ truy vấn. Sau đó hệ quản trị có thể phải kiểm tra hình học chính xác trên tập ứng viên.

Ví dụ khái niệm:

```sql
-- Ví dụ PostgreSQL/PostGIS
CREATE INDEX idx_places_location
ON places USING GIST (location);

SELECT place_id, name
FROM places
WHERE ST_DWithin(
    location,
    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography,
    :radius_meters
);
```

Khi dùng dữ liệu không gian, cần kiểm tra hệ tọa độ (SRID), đơn vị đo, kiểu geometry/geography, tính hợp lệ của hình học và toán tử có hỗ trợ index. Một truy vấn có thể dùng spatial index để lấy ứng viên rồi recheck khoảng cách chính xác. Nếu SRID hoặc đơn vị không phù hợp, kết quả có thể sai dù truy vấn chạy nhanh.

## 10. Columnstore: truy vấn phân tích theo cột

Rowstore lưu các cột của một hàng gần nhau; columnstore tổ chức dữ liệu theo cột hoặc nhóm cột để đọc hiệu quả khi truy vấn chỉ cần một phần cột trên rất nhiều hàng. Columnstore thường hỗ trợ nén tốt, batch/vectorized execution và giảm I/O cho workload phân tích.

Ví dụ truy vấn tổng hợp:

```sql
SELECT product_category, SUM(net_amount) AS revenue
FROM sales
WHERE sale_date >= :start_date
  AND sale_date < :end_date
GROUP BY product_category;
```

Nếu bảng `sales` rất lớn và phần lớn workload là phân tích, columnstore có thể giảm lượng dữ liệu đọc và tăng tốc tổng hợp. SQL Server có clustered/nonclustered columnstore index; Oracle có các dạng table/index tổ chức theo cột tùy phiên bản và tính năng; các hệ thống phân tích khác có kiến trúc columnar riêng.

Columnstore không phải lựa chọn mặc định cho mọi bảng giao dịch. Các thao tác point update, delete và truy vấn lấy một vài hàng có thể phù hợp hơn với rowstore/B-tree. Một số sản phẩm hỗ trợ kết hợp rowstore và columnstore, delta store hoặc cơ chế maintenance để cân bằng ghi và phân tích. Cần đánh giá độ trễ ghi, kích thước batch, nén, segment elimination và cách cập nhật dữ liệu.

## 11. Partial/filtered index và expression/function-based index

Một số hệ quản trị cho phép chỉ lập chỉ mục một phần hàng hoặc một biểu thức, giúp giảm kích thước index và tập trung vào mẫu truy vấn cụ thể.

### 11.1. Partial hoặc filtered index

Partial index (PostgreSQL) hoặc filtered index (SQL Server) chỉ chứa các hàng thỏa một predicate. Ví dụ chỉ mục cho các đơn hàng còn mở:

```sql
-- PostgreSQL
CREATE INDEX idx_orders_open_created
ON orders (created_at)
WHERE status = 'OPEN';
```

Truy vấn có predicate tương thích có thể dùng chỉ mục nhỏ này:

```sql
SELECT order_id, created_at
FROM orders
WHERE status = 'OPEN'
ORDER BY created_at;
```

Partial/filtered index hữu ích khi tập hàng mục tiêu nhỏ và predicate ổn định. Bộ tối ưu phải chứng minh điều kiện truy vấn bao hàm predicate của chỉ mục; nếu điều kiện được viết theo cách không thể chứng minh tương đương, index có thể không được dùng. Các hệ quản trị có quy tắc hỗ trợ khác nhau.

### 11.2. Expression hoặc function-based index

Nếu workload thường xuyên tìm theo biểu thức, một số hệ quản trị cho phép lập chỉ mục trên biểu thức hoặc cột tính toán. Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_users_lower_email
ON users (lower(email));
```

Truy vấn cần dùng biểu thức tương thích:

```sql
SELECT user_id, email
FROM users
WHERE lower(email) = lower(:email);
```

Oracle hỗ trợ function-based indexes; SQL Server có thể dùng indexed computed columns khi đáp ứng điều kiện; MySQL hỗ trợ functional key parts trong các phiên bản phù hợp. Cần xác nhận tính xác định (determinism), collation, kiểu dữ liệu, quy tắc null và yêu cầu cấu hình theo sản phẩm.

## 12. Bản đồ hỗ trợ chỉ mục theo hệ quản trị

Bảng dưới đây là định hướng khái quát, không phải ma trận hỗ trợ đầy đủ. Tên gọi, engine, phiên bản, kiểu dữ liệu và toán tử được hỗ trợ có thể khác nhau; trước khi thiết kế, hãy kiểm tra tài liệu của đúng phiên bản.

| Hệ quản trị | Các loại/cơ chế thường gặp | Workload tiêu biểu |
|---|---|---|
| PostgreSQL | B-tree, Hash, GiST, SP-GiST, GIN, BRIN; partial, expression và covering qua `INCLUDE` | OLTP, JSONB/array, full-text, spatial, bảng lớn theo thời gian |
| MySQL (InnoDB) | B-tree/secondary index, FULLTEXT, SPATIAL; functional key parts và multi-valued index tùy phiên bản | OLTP, tìm kiếm toàn văn, dữ liệu không gian, JSON/mảng giá trị |
| SQL Server | Rowstore clustered/nonclustered, filtered, columnstore, full-text, spatial; indexed computed columns | OLTP, báo cáo phân tích, full-text và dữ liệu không gian |
| Oracle Database | B-tree, bitmap, function-based, domain, spatial, text và các tùy chọn chuyên biệt theo phiên bản | OLTP, data warehouse, văn bản, spatial và workload hỗn hợp |

Một số lưu ý:

- “Clustered” không có cùng ý nghĩa vật lý ở mọi hệ quản trị. Trong SQL Server, clustered index xác định cách hàng của bảng được tổ chức theo khóa; trong InnoDB, dữ liệu bảng được tổ chức theo clustered primary key; PostgreSQL có lệnh `CLUSTER` để sắp xếp lại bảng theo một index nhưng không duy trì thứ tự đó tự động sau các lần ghi.
- MySQL InnoDB dùng B-tree cho nhiều secondary index; không nên nhầm việc lưu dữ liệu dạng cây với việc hỗ trợ mọi access method như PostgreSQL.
- PostgreSQL GIN, GiST, SP-GiST và BRIN là các access method khác nhau; khả năng dùng phụ thuộc operator class.
- Full-text và spatial thường cần cấu hình/parser/extension riêng. Việc tạo được chỉ mục không đảm bảo mọi toán tử truy vấn đều sử dụng được.
- Tính năng thay đổi theo phiên bản và edition; cần xác minh trên môi trường đích.

## 13. Quy trình lựa chọn và kiểm chứng

Một quy trình có thể áp dụng cho từng truy vấn hoặc nhóm workload:

1. **Thu thập truy vấn thực tế.** Lấy SQL, tham số, tần suất, tỷ lệ đọc/ghi, độ trễ và yêu cầu nghiệp vụ.
2. **Phân loại phép toán.** Xác định point lookup, range, sort, full-text, spatial, membership, phân tích theo cột hay lọc một tập con.
3. **Kiểm tra khả năng của hệ quản trị.** Xác nhận phiên bản, access method, kiểu dữ liệu, operator class, engine và giới hạn liên quan.
4. **Đọc thống kê và execution plan.** Xem số hàng ước lượng/thực tế, scan/seek, filter/recheck, sort, lookup, số trang đọc và spill.
5. **Đề xuất chỉ mục nhỏ nhất đáp ứng workload.** Cân nhắc cột khóa, thứ tự, predicate, cột bao phủ và khả năng dùng chung với truy vấn khác.
6. **Thiết lập baseline.** Đo p50/p95/p99, throughput, CPU, bộ nhớ, I/O, thời gian ghi và dung lượng trước thay đổi.
7. **Thử nghiệm có kiểm soát.** Dùng dữ liệu và workload đại diện; thay đổi một yếu tố chính; kiểm tra kết quả và tính đúng đắn.
8. **Đo cả lợi ích và chi phí.** Đánh giá truy vấn mục tiêu, workload liên quan, chi phí ghi, cache, dung lượng, maintenance và backup.
9. **Quyết định giữ hoặc loại bỏ.** Ghi lý do, phạm vi, phiên bản, cách rollback và thời điểm đánh giá lại.

Không nên tạo nhiều loại chỉ mục cùng lúc rồi chỉ so sánh thời gian cuối cùng. Nếu tạo B-tree, GIN và BRIN đồng thời, sẽ khó biết cấu trúc nào tạo ra cải thiện và chi phí nào đến từ từng index. Tách phép thử hoặc dùng thiết kế thử nghiệm có kiểm soát để xác định tác động.

## 14. Ví dụ lựa chọn theo tình huống

| Tình huống | Hướng lựa chọn ban đầu | Cần xác minh |
|---|---|---|
| Tra cứu tài khoản theo email bằng | B-tree hoặc unique B-tree | Tính duy nhất, collation, chuẩn hóa email và tần suất ghi |
| Lọc log theo khoảng thời gian trên bảng append gần tuần tự rất lớn | BRIN hoặc B-tree tùy độ chọn lọc và nhu cầu point lookup | Tương quan vật lý, block range, số block bị loại và độ trễ |
| Tìm tài liệu chứa nhiều từ khóa và xếp hạng liên quan | Full-text/inverted index | Parser/ngôn ngữ, stemming, chất lượng kết quả và cập nhật index |
| Tìm các địa điểm trong bán kính hoặc hình học giao nhau | Spatial index như R-tree/GiST theo sản phẩm | SRID, đơn vị, bounding box, recheck và độ chính xác |
| Phân tích doanh thu theo nhóm trên hàng trăm triệu bản ghi | Columnstore hoặc nền tảng columnar | Tỷ lệ cập nhật, segment elimination, nén, batch execution |
| Lọc các bản ghi đang hoạt động chiếm tỷ lệ nhỏ | Partial/filtered index | Predicate có tương thích với truy vấn và phân bố có ổn định không |
| Tìm JSON theo key/value hoặc containment | GIN hoặc multi-valued/JSON index theo hệ quản trị | Toán tử được hỗ trợ, kích thước document, chi phí cập nhật |
| Kết hợp nhiều cột phân loại trong kho dữ liệu đọc nhiều | Bitmap index ở hệ quản trị hỗ trợ | Tỷ lệ ghi, đồng thời cập nhật và khả năng kết hợp predicate |

Các hướng trên chỉ là giả thuyết ban đầu. Nếu truy vấn trả về phần lớn dữ liệu, table scan có thể tốt hơn; nếu dữ liệu không có đặc tính giả định, cấu trúc chuyên biệt có thể không đem lại lợi ích.

## 15. Các sai lầm thường gặp

- **Chọn theo tên gọi thay vì toán tử:** tạo GIN, GiST hoặc FULLTEXT mà không xác nhận toán tử truy vấn được hỗ trợ.
- **Mặc định chỉ mục chuyên biệt luôn nhanh hơn B-tree:** cấu trúc chuyên biệt có chi phí và phạm vi sử dụng riêng.
- **Bỏ qua phiên bản:** cú pháp hoặc tính năng có thể chỉ tồn tại ở một số phiên bản/engine.
- **Không kiểm tra độ chọn lọc:** index có thể đọc gần như toàn bảng và còn phải recheck nhiều hàng.
- **Bỏ qua chi phí ghi:** chỉ mục cải thiện đọc nhưng làm insert/update chậm hơn.
- **Tạo chỉ mục trùng lặp:** nhiều index cùng phục vụ mẫu truy vấn tương tự làm tăng dung lượng và bảo trì.
- **Không xem execution plan:** index tồn tại nhưng bộ tối ưu có thể không dùng vì cost hoặc predicate không tương thích.
- **Chỉ đo một tham số:** phân bố dữ liệu lệch có thể làm hiệu quả khác nhau giữa các nhóm truy vấn.
- **Bỏ qua tính đúng đắn:** spatial index, full-text parser, collation và expression index có thể thay đổi ngữ nghĩa kết quả nếu cấu hình không đúng.
- **Không có kế hoạch bảo trì:** bỏ qua cập nhật thống kê, vacuum/rebuild/reorganize hoặc cơ chế dọn pending list/segment tùy sản phẩm.

## 16. Bài tập tự kiểm tra

### Bài tập 1: Chọn chỉ mục cho log theo thời gian

Một bảng `events` có vài tỷ hàng. Ứng dụng chủ yếu ghi thêm sự kiện theo thời gian; truy vấn báo cáo đọc các khoảng ngày, còn một số truy vấn tra cứu `event_id` chính xác.

**Yêu cầu:** đề xuất loại chỉ mục để thử nghiệm và nêu các dữ liệu cần thu thập.

**Gợi ý trả lời:** có thể thử BRIN trên `created_at` nếu dữ liệu có tương quan vật lý tốt với thời gian, đồng thời dùng B-tree trên `event_id` cho point lookup. Đo kích thước index, block range bị loại, số block đọc, p95 truy vấn khoảng thời gian, độ trễ ghi và chi phí duy trì. Không giả định BRIN thay thế B-tree cho tra cứu điểm.

### Bài tập 2: Chọn chỉ mục cho tìm kiếm nội dung

Một bảng `articles` có cột `body`. Người dùng cần tìm bài chứa các từ “database” và “performance”, có xếp hạng theo mức liên quan.

**Câu hỏi:** B-tree trên `body` có phải lựa chọn đầu tiên không? Cần xem những yếu tố nào?

**Gợi ý trả lời:** full-text/inverted index thường phù hợp hơn vì truy vấn tìm token và mức liên quan. Cần chọn parser/ngôn ngữ, cách tokenization, stemming, stop words, hỗ trợ tiếng Việt và cách cập nhật index; kiểm tra chất lượng kết quả và hiệu năng trên bộ truy vấn thực tế.

### Bài tập 3: Bitmap hay B-tree cho cột trạng thái?

Một kho dữ liệu có cột `status` với bốn giá trị. Truy vấn phân tích kết hợp `status`, `region` và `channel`; dữ liệu hầu như chỉ đọc theo lô. Một ứng dụng OLTP khác lại cập nhật trạng thái liên tục.

**Câu hỏi:** loại chỉ mục nào có thể đáng thử cho kho dữ liệu và vì sao cần thận trọng với OLTP?

**Gợi ý trả lời:** bitmap index có thể phù hợp với workload đọc phân tích có số giá trị phân biệt thấp và nhiều predicate kết hợp trên hệ quản trị hỗ trợ. Với OLTP cập nhật đồng thời, chi phí duy trì và khóa/đồng bộ có thể làm giảm khả năng ghi; cần kiểm tra đặc tính triển khai và đo trên workload thật.

### Checklist trước khi chọn chỉ mục chuyên biệt

- [ ] Đã mô tả truy vấn, tham số, tần suất và workload đọc/ghi.
- [ ] Đã xác định phép toán: equality, range, full-text, spatial, membership hay analytics.
- [ ] Đã xem độ chọn lọc và phân bố dữ liệu thực tế.
- [ ] Đã xác nhận hệ quản trị, engine và phiên bản hỗ trợ loại index cùng toán tử cần dùng.
- [ ] Đã kiểm tra execution plan và điều kiện index/recheck/filter.
- [ ] Đã đo baseline và xác định chỉ số thành công trước thử nghiệm.
- [ ] Đã đánh giá dung lượng, chi phí ghi, cache, đồng thời và bảo trì.
- [ ] Đã thử trên nhiều tham số và workload đại diện.
- [ ] Đã xác nhận kết quả dữ liệu và ngữ nghĩa tìm kiếm vẫn đúng.
- [ ] Đã ghi lại cách rollback và thời điểm xem xét lại chỉ mục.

Lựa chọn chỉ mục chuyên biệt là quyết định gắn với phép toán truy vấn, phân bố dữ liệu, tỷ lệ đọc/ghi và khả năng cụ thể của hệ quản trị. B-tree là nền tảng hữu ích cho nhiều truy vấn giao dịch, trong khi hash, bitmap, full-text, GIN/GiST, BRIN, spatial, columnstore và partial/expression index phục vụ những mẫu truy cập khác nhau. Chỉ mục phù hợp phải được chứng minh bằng kế hoạch thực thi và phép đo workload, đồng thời duy trì được chi phí ghi, bộ nhớ, I/O và bảo trì trong giới hạn chấp nhận được.
