# Chỉ mục theo cây và theo hàm băm ở mức nền tảng

Trong ứng dụng Java có lưu trữ dữ liệu bền vững, **chỉ mục (index)** là cấu trúc hỗ trợ cơ sở dữ liệu tìm và sắp xếp bản ghi mà không phải đọc tuần tự toàn bộ bảng ở mọi truy vấn. Hai họ cấu trúc thường được giới thiệu đầu tiên là **chỉ mục theo cây** (điển hình B-tree/B+ tree) và **chỉ mục theo hàm băm** (hash index). Hiểu cách chúng tổ chức khóa, chi phí đọc/ghi và giới hạn của từng loại giúp thiết kế lớp persistence phù hợp với truy vấn thực tế.

Bài này tập trung vào chỉ mục của cơ sở dữ liệu quan hệ, đặc biệt trong bối cảnh Java dùng JDBC hoặc ORM. SQL minh họa dùng PostgreSQL khi cần chỉ rõ loại chỉ mục; cú pháp và khả năng của từng hệ quản trị có thể khác nhau.

## 1. Chỉ mục giải quyết bài toán gì?

Giả sử bảng **orders** có một triệu đơn hàng và ứng dụng thường hỏi: “Lấy 20 đơn mới nhất của khách hàng 42”. Nếu không có cấu trúc truy cập phù hợp, cơ sở dữ liệu có thể phải đọc nhiều trang dữ liệu, lọc theo **customer_id**, sau đó sắp xếp theo thời gian. Với chỉ mục theo khóa khách hàng và thời gian, bộ máy truy vấn có thể định vị vùng dữ liệu liên quan, duyệt theo thứ tự và dừng khi đủ 20 dòng.

Có thể hình dung chỉ mục như một bảng tra cứu bổ sung:

~~~text
Bảng dữ liệu (các dòng được lưu ở những trang dữ liệu)
  [row A] [row B] [row C] [row D] ...

Chỉ mục theo customer_id, placed_at
  (42, 2026-11-21 10:30) -> vị trí/định danh row D
  (42, 2026-11-20 09:00) -> vị trí/định danh row A
  (51, 2026-11-19 14:00) -> vị trí/định danh row C
~~~

Đó là mô hình khái niệm; giá trị thực tế trong lá chỉ mục phụ thuộc hệ quản trị và cách lưu bảng. Ví dụ, chỉ mục phụ của InnoDB thường chứa khóa chính để tìm dòng dữ liệu, còn chỉ mục trên bảng dạng heap có thể chứa tham chiếu tới vị trí dòng. Không nên mặc định mọi chỉ mục đều lưu “con trỏ vật lý” theo cùng một cách.

**Lợi ích:** giảm số trang phải đọc cho các truy vấn phù hợp, có thể trả dữ liệu theo thứ tự đã lập chỉ mục và hỗ trợ kiểm tra tính duy nhất khi dùng loại chỉ mục thích hợp.

**Đổi lại:** chỉ mục chiếm dung lượng và phải được cập nhật khi chèn, xóa hoặc thay đổi giá trị cột liên quan. Một chỉ mục có ích cho đọc vẫn có thể làm giảm tốc độ ghi; bộ tối ưu truy vấn cũng có thể bỏ qua chỉ mục nếu quét bảng rẻ hơn.

### Ba khái niệm cần phân biệt

- **Khóa tra cứu:** giá trị được lập chỉ mục, ví dụ **customer_id** hoặc cặp **(customer_id, placed_at)**.
- **Độ chọn lọc (selectivity):** khả năng điều kiện lọc chỉ giữ lại phần nhỏ các dòng. Khóa có nhiều giá trị khác nhau thường chọn lọc tốt hơn trường chỉ có vài trạng thái, nhưng phân bố dữ liệu và truy vấn cụ thể mới quyết định chi phí.
- **Thứ tự:** chỉ mục theo cây thường giữ khóa theo thứ tự so sánh; chỉ mục băm phân nhóm theo giá trị hàm băm, nên không mang thứ tự hữu ích cho phép so sánh lớn/nhỏ.

## 2. Chỉ mục theo cây: B-tree và B+ tree

### 2.1. Vì sao dùng cây cân bằng?

Cây tìm kiếm nhị phân thông thường có thể bị lệch và chiều cao tăng rất lớn. Chỉ mục đĩa cần cấu trúc có **chiều cao thấp**, mỗi nút chứa được nhiều khóa và thích hợp với đọc/ghi theo trang (page). B-tree và biến thể B+ tree đáp ứng nhu cầu này: chúng là cây tìm kiếm nhiều nhánh, tự duy trì cân bằng khi dữ liệu thay đổi.

Trong cách gọi của sản phẩm cơ sở dữ liệu, “B-tree index” thường chỉ một họ cấu trúc; triển khai cụ thể có thể gần với B+ tree. Với B+ tree, các khóa tra cứu và tham chiếu đến bản ghi tập trung ở **nút lá**; các nút trong chủ yếu dẫn đường. Các lá được tổ chức theo thứ tự, thường thuận tiện cho duyệt liên tiếp.

~~~text
                         [30 | 60]            <- nút gốc
                        /    |     \
                       /     |      \
              [10, 20]  [30, 40, 50]  [60, 70, 80]  <- các lá có thứ tự
                  <---------- duyệt theo khóa ---------->
~~~

Sơ đồ giản lược: các số ở nút gốc là **khóa phân cách**, không phải ba bản ghi dữ liệu duy nhất. Cấu trúc thật có thể gồm nhiều tầng, nhiều khóa trên mỗi nút và cách liên kết lá tùy hệ quản trị.

### 2.2. Tìm bằng, tìm khoảng và sắp xếp

Đối với điều kiện **customer_id = 42**, bộ máy bắt đầu ở gốc, dựa vào khóa phân cách để đi xuống nhánh phù hợp rồi tìm khóa ở lá. Nó tránh phải so sánh với mọi dòng của bảng.

Đối với điều kiện **placed_at >= mốc_thời_gian**, chỉ mục theo thời gian có thể tìm vị trí bắt đầu và **duyệt các khóa kế tiếp**. Đây là điểm mạnh lớn của cây so với băm: thứ tự của khóa đã được duy trì sẵn.

Nếu cây có trung bình **f** nhánh trên nút và chứa **N** khóa, chiều cao xấp xỉ theo **log cơ số f của N**. Vì **f** có thể khá lớn, một cây chỉ cần ít tầng ngay cả khi bảng có nhiều dòng. Đây là trực giác về số bước định vị; chi phí thực tế còn gồm đọc trang, bộ nhớ đệm, lấy dòng gốc, số dòng khớp điều kiện và việc cần sắp xếp hay không.

Với truy vấn trả **k** dòng liên tiếp theo khoảng, có thể hình dung chi phí gồm **định vị điểm bắt đầu + duyệt phần phù hợp**, thay vì một phép tìm riêng cho từng dòng. Không nên xem công thức độ phức tạp là cam kết về mili giây của truy vấn.

### 2.3. Cập nhật cây và chi phí duy trì

Khi thêm khóa, cơ sở dữ liệu tìm lá tương ứng rồi chèn vào. Nếu trang đầy, có thể xảy ra **tách trang (page split)** và điều chỉnh các nút cha; khi xóa hoặc bảo trì có thể có xử lý gộp, tái cân bằng hoặc thu hồi không gian tùy cơ chế của hệ quản trị. Điều đó giữ cho đường đi tìm kiếm tương đối ngắn nhưng khiến thao tác ghi tốn công hơn.

Các truy vấn liên tục chèn theo khóa thời gian tăng dần thường tập trung vào vùng cuối của cây. Cơ sở dữ liệu có các kỹ thuật điều phối đồng thời, nhưng vẫn cần quan sát tải ghi và tranh chấp thay vì cho rằng chỉ mục theo cây luôn miễn phí.

## 3. Chỉ mục theo hàm băm: hash index

### 3.1. Tổ chức theo bucket

Hash index đưa khóa qua một **hàm băm** để xác định nhóm lưu trữ (bucket) cần kiểm tra. Truy vấn tìm đúng giá trị khóa có thể đi thẳng tới bucket tương ứng và so sánh các mục trong bucket để xác nhận khóa.

~~~text
Khóa                         Hàm băm                  Bucket
"REF-A103" ----\
                +--------> h(k) mod số_bucket ----> [bucket 2] -> các mục
"REF-C872" ----/                                  [bucket 3] -> các mục
"REF-B011" --------------------------------------> [bucket 4] -> các mục
~~~

Hai khóa khác nhau **có thể cùng một bucket** (va chạm băm). Điều này không có nghĩa cơ sở dữ liệu nhầm hai khóa là một: hệ thống vẫn phải kiểm tra giá trị khóa thực và áp dụng điều kiện truy vấn. Các kỹ thuật giải quyết va chạm, trang tràn và mở rộng bucket khác nhau theo triển khai; một số loại hash index dùng băm động.

Hash index đặc biệt phù hợp với điều kiện **bằng chính xác**, ví dụ **external_ref = 'REF-A103'**. Trong điều kiện lý tưởng, truy cập bucket có chi phí trung bình gần hằng số theo số khóa, nhưng phải tính cả va chạm, số trang dữ liệu và phân bố khóa; không được suy ra rằng hash index luôn nhanh hơn B-tree.

### 3.2. Tại sao hash index không tốt cho khoảng?

Hàm băm cố tình không duy trì quan hệ thứ tự. Từ **h('REF-A103')** và **h('REF-A104')** không thể suy ra chuỗi nào đứng trước chuỗi nào, cũng không thể duyệt tất cả các giá trị trong một khoảng bằng cách đi sang bucket kế tiếp.

Vì vậy, một hash index thông thường không đáp ứng trực tiếp:

- Điều kiện khoảng: **price > 100**, **created_at BETWEEN ... AND ...**.
- Yêu cầu thứ tự: **ORDER BY created_at DESC**.
- So sánh tiền tố chuỗi: **LIKE 'ABC%'** như một phép duyệt dải khóa.

Nó vẫn có thể được bộ máy dùng cùng các bước lọc khác trong một kế hoạch truy vấn phức tạp, nhưng bản thân cấu trúc băm không cung cấp thứ tự cần thiết.

**Lưu ý về thuật ngữ:** hash index dùng hàm băm để tổ chức khóa tìm kiếm. Nó không đồng nghĩa với việc ứng dụng lưu mật khẩu dưới dạng băm, cũng không yêu cầu lập trình viên băm trước cột khi ghi vào bảng.

## 4. So sánh B-tree/B+ tree và hash index

| Tiêu chí | B-tree / B+ tree | Hash index |
|---|---|---|
| Nguyên tắc | Các khóa có thứ tự, điều hướng qua cây cân bằng | Ánh xạ khóa tới bucket bằng hàm băm |
| Điều kiện **=** | Phù hợp | Phù hợp |
| Điều kiện **<, <=, >, >=, BETWEEN** | Phù hợp nếu thứ tự cột và điều kiện hỗ trợ | Không hỗ trợ duyệt dải khóa trực tiếp |
| **ORDER BY**, **MIN/MAX** | Có thể tận dụng thứ tự khóa | Không cung cấp thứ tự khóa |
| Tìm theo tiền tố chuỗi | Có thể phù hợp với một số mẫu và cấu hình collation/operator class | Không phù hợp để duyệt theo tiền tố |
| Khóa ghép nhiều cột | Phổ biến; thứ tự cột rất quan trọng | Tùy hệ quản trị; PostgreSQL hash index chỉ nhận một biểu thức khóa |
| Ràng buộc **UNIQUE** | Thường được dùng để thực thi | PostgreSQL hash index không thực thi **UNIQUE** |
| Chi phí ghi | Cập nhật và đôi khi tách trang của cây | Cập nhật bucket, xử lý va chạm/tràn/mở rộng |
| Trường hợp mặc định | Linh hoạt cho đa số truy vấn quan hệ | Cân nhắc cho workload chỉ so sánh bằng khi DB hỗ trợ |

Bảng nói về khả năng cấu trúc và một số giới hạn của PostgreSQL, **không phải** bảng xếp hạng tốc độ tuyệt đối. Mỗi DBMS có cơ chế riêng: PostgreSQL cung cấp cả B-tree và hash index; InnoDB của MySQL chủ yếu dùng B+ tree cho chỉ mục thông thường và có cơ chế adaptive hash index nội bộ trong một số cấu hình; không thể suy ra cú pháp **USING HASH** áp dụng giống nhau trên mọi công cụ.

## 5. Ví dụ: thiết kế chỉ mục cho bảng đơn hàng

Giả sử ứng dụng Java quản lý các đơn hàng với cấu trúc sau. Đây là DDL minh họa theo PostgreSQL.

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    external_ref VARCHAR(64) NOT NULL,
    placed_at    TIMESTAMP NOT NULL,
    status       VARCHAR(20) NOT NULL,
    amount       NUMERIC(12, 2) NOT NULL
);
~~~

Khóa chính **id** có ràng buộc **PRIMARY KEY**, nên PostgreSQL tự tạo chỉ mục B-tree tương ứng. Không cần tạo lại chỉ mục đơn cột cùng mục đích.

### 5.1. Truy vấn khách hàng và khoảng thời gian: chọn cây ghép

Tình huống: trang “Đơn hàng của tôi” lấy 20 đơn gần nhất của một khách hàng kể từ một thời điểm.

~~~sql
SELECT id, placed_at, amount
FROM orders
WHERE customer_id = 42
  AND placed_at >= TIMESTAMP '2026-11-01 00:00:00'
ORDER BY placed_at DESC
LIMIT 20;
~~~

Chỉ mục phù hợp:

~~~sql
CREATE INDEX idx_orders_customer_placed
    ON orders (customer_id, placed_at DESC);
~~~

Cột **customer_id** đứng trước để xác định nhóm khách hàng bằng điều kiện bằng. Trong nhóm đó, **placed_at** có thứ tự thuận tiện cho lọc khoảng và lấy đơn mới nhất. Tùy số dòng, trạng thái cache và cách truy cập bảng, bộ tối ưu có thể chọn quét chỉ mục rồi lấy dòng, hoặc chọn kế hoạch khác.

**Quy tắc tiền tố trái (leftmost prefix):** với chỉ mục cây **(customer_id, placed_at)**, điều kiện chỉ trên **placed_at** thường không tận dụng được phần dẫn đầu để thu hẹp vùng tìm kiếm hiệu quả như khi có **customer_id**. Nếu ứng dụng thường xuyên truy vấn đơn của **tất cả** khách hàng theo thời gian, hãy đánh giá nhu cầu một chỉ mục riêng bắt đầu bằng **placed_at**. Không tạo tự động nếu workload chưa cần.

Thứ tự tăng/giảm trong chỉ mục và khả năng quét ngược còn phụ thuộc cơ chế DBMS; với một số mẫu ORDER BY, cây theo thứ tự ngược vẫn trả được kết quả hiệu quả. Không phải lúc nào cũng cần hai chỉ mục ASC và DESC.

### 5.2. Tra cứu theo mã tham chiếu: hai lựa chọn

Tình huống: dịch vụ tra một đơn theo mã đến từ đối tác.

~~~sql
SELECT id, customer_id, status
FROM orders
WHERE external_ref = 'REF-A103';
~~~

Lựa chọn mặc định linh hoạt là B-tree:

~~~sql
CREATE INDEX idx_orders_external_ref
    ON orders (external_ref);
~~~

Nếu mỗi **external_ref** bắt buộc chỉ có một dòng, thay bằng **UNIQUE** để cơ sở dữ liệu **thực thi** quy tắc toàn vẹn:

~~~sql
-- Dùng phương án này thay cho chỉ mục thường khi dữ liệu bảo đảm duy nhất.
ALTER TABLE orders
    ADD CONSTRAINT uq_orders_external_ref UNIQUE (external_ref);
~~~

Với PostgreSQL và một workload tra bằng chuyên biệt, có thể **thử nghiệm** hash index:

~~~sql
-- PostgreSQL: ví dụ lựa chọn thay thế để benchmark, không tạo
-- đồng thời với B-tree trên cùng cột chỉ vì "hash chắc sẽ nhanh hơn".
CREATE INDEX idx_orders_external_ref_hash
    ON orders USING HASH (external_ref);
~~~

PostgreSQL hash index dùng cho phép so sánh bằng; không thực thi UNIQUE và không thay thế các nhu cầu sắp xếp/khoảng. Nếu phải bảo đảm mã duy nhất, ưu tiên ràng buộc **UNIQUE** (với B-tree hỗ trợ). Trong triển khai thực tế, **chọn một phương án dựa trên yêu cầu và đo đạc**; các lệnh trên là phương án so sánh chứ không phải bộ lệnh cần chạy lần lượt trên production.

### 5.3. Cột ít giá trị khác nhau chưa chắc là chỉ mục tốt

Giả sử trạng thái chỉ gồm **PENDING**, **PAID**, **CANCELLED** và phần lớn bảng có trạng thái **PAID**. Truy vấn **WHERE status = 'PAID'** có thể trả quá nhiều dòng; đọc qua chỉ mục và liên tục quay lại trang bảng có thể đắt hơn quét bảng.

Vì vậy, **“có điều kiện bằng” không đủ để kết luận “phải dùng hash index”**. Cần biết tỷ lệ dòng phù hợp, cột nào được SELECT, có thêm giới hạn thời gian hoặc LIMIT hay không và thống kê hiện hành. Với điều kiện đặc biệt phổ biến, có thể đánh giá chỉ mục ghép hoặc **partial index** của PostgreSQL, nhưng đó là bước tối ưu dựa trên truy vấn thật.

## 6. Cách đọc kế hoạch truy vấn thay vì đoán

Trước khi tạo một chỉ mục trên hệ thống thật, lấy các truy vấn điển hình và xem kế hoạch của cơ sở dữ liệu. Ví dụ trong PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, placed_at, amount
FROM orders
WHERE customer_id = 42
  AND placed_at >= TIMESTAMP '2026-11-01 00:00:00'
ORDER BY placed_at DESC
LIMIT 20;
~~~

Trong kết quả, chú ý:

1. **Seq Scan / Index Scan / Index Only Scan / Bitmap Index Scan:** trình tối ưu đã chọn cách đọc nào. “Có index” không bảo đảm “chắc chắn có Index Scan”.
2. **Index Cond** và **Filter:** điều kiện nào dùng để xác định phạm vi đọc trong chỉ mục, điều kiện nào còn phải lọc sau đó.
3. **rows** ước lượng và **actual rows:** sai lệch lớn có thể liên quan thống kê cũ, dữ liệu lệch hoặc mối tương quan giữa các cột.
4. **Buffers**, số trang đã đọc hay được tìm thấy trong cache, cùng thời gian thực thi: giúp hiểu chi phí I/O thay vì chỉ nhìn tổng thời gian một lần chạy.
5. **Sort** và số dòng trả về: chỉ mục phù hợp có thể giảm hoặc bỏ bước sắp xếp, đặc biệt khi **LIMIT** nhỏ.

**EXPLAIN ANALYZE thực thi câu truy vấn thật.** Khi khảo sát các câu INSERT, UPDATE hoặc DELETE, cần có môi trường kiểm thử/transaction phù hợp để không vô tình ghi dữ liệu ngoài ý muốn. Với ví dụ SELECT ở trên, việc thực thi là truy vấn đọc.

So sánh trên dữ liệu đủ đại diện, cùng điều kiện và với nhiều lần đo vì cache làm thay đổi kết quả. Nếu bảng nhỏ hoặc điều kiện trả phần lớn dòng, **Seq Scan** có thể là lựa chọn hợp lý. Tránh ép bộ tối ưu chỉ để nhìn thấy tên chỉ mục mong muốn.

## 7. Liên hệ với tầng persistence trong Java

ORM như JPA/Hibernate hoặc mã JDBC không tự làm truy vấn SQL trở nên có chỉ mục. Cơ sở dữ liệu nhìn vào **SQL thực tế**, tham số, thống kê và cấu trúc chỉ mục khi lập kế hoạch. Vì vậy, cần xem SQL do ORM sinh ra nếu hiệu năng truy vấn không như mong đợi.

Ví dụ phương thức JDBC truy vấn theo đúng thứ tự cột của chỉ mục ghép ở mục 5.1:

~~~java
// Giả định đã có Connection hợp lệ và import java.sql.*,
// java.time.LocalDateTime, java.util.ArrayList, java.util.List.
public List<Long> findRecentOrderIds(
        Connection connection,
        long customerId,
        LocalDateTime fromTime) throws SQLException {

    String sql = "SELECT id FROM orders "
            + "WHERE customer_id = ? AND placed_at >= ? "
            + "ORDER BY placed_at DESC LIMIT ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, customerId);
        statement.setObject(2, fromTime); // JDBC 4.2: LocalDateTime -> TIMESTAMP
        statement.setInt(3, 20);

        List<Long> ids = new ArrayList<>();
        try (ResultSet result = statement.executeQuery()) {
            while (result.next()) {
                ids.add(result.getLong("id"));
            }
        }
        return ids;
    }
}
~~~

**PreparedStatement** truyền tham số an toàn và tránh ghép dữ liệu người dùng trực tiếp vào chuỗi SQL. Nó không tự bảo đảm sử dụng chỉ mục: dạng điều kiện và index vẫn phải phù hợp. Nếu hệ thống lưu thời điểm tuyệt đối qua nhiều múi giờ, cân nhắc kiểu dữ liệu và ánh xạ thời gian thích hợp (ví dụ **TIMESTAMPTZ** cùng **OffsetDateTime** trong PostgreSQL) thay vì dùng **TIMESTAMP** không múi giờ một cách tùy tiện.

Ở ranh giới persistence, cần thêm ba nguyên tắc:

- **Nhất quán giao dịch:** hệ quản trị chịu trách nhiệm duy trì chỉ mục phù hợp với thay đổi dữ liệu khi transaction commit/rollback; ứng dụng không tự cập nhật cấu trúc chỉ mục.
- **Lỗi kết nối và timeout:** xử lý tài nguyên JDBC bằng try-with-resources, quản lý transaction rõ ràng và không tự động lặp vô hạn các thao tác ghi không idempotent. Việc thêm chỉ mục không chữa được lỗi kết nối.
- **Tiến hóa schema:** tạo hoặc thay đổi chỉ mục bằng migration có kiểm soát; cân nhắc thời gian xây chỉ mục và tác động khóa/tải I/O trên bảng lớn. Cú pháp tạo chỉ mục trực tuyến và giới hạn transaction tùy DBMS.

## 8. Những sai lầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Hash luôn O(1), nên luôn nhanh hơn cây.” | O(1) là trực giác trung bình cho tìm bucket; va chạm, cache, lấy dòng và tối ưu truy vấn quyết định hiệu năng thực. |
| “B-tree không tốt cho tìm bằng.” | B-tree hỗ trợ **=** rất tốt và thường là lựa chọn mặc định. |
| “Có chỉ mục là mọi truy vấn sẽ nhanh.” | Điều kiện lọc có thể kém chọn lọc; bảng nhỏ, truy vấn cần quá nhiều dòng hoặc kế hoạch khác có thể nhanh hơn. |
| “Chỉ mục ghép (A, B) tương đương (B, A).” | Thứ tự cột thay đổi cách tìm theo tiền tố và khả năng trả kết quả có thứ tự. |
| “Thêm chỉ mục không ảnh hưởng ghi.” | INSERT/UPDATE/DELETE liên quan đến khóa chỉ mục có thêm công việc và tốn dung lượng, WAL/redo và bảo trì. |
| “Hash index kiểm tra tính duy nhất cho mọi hệ.” | Khả năng UNIQUE là tính năng của hệ quản trị và loại chỉ mục; PostgreSQL hash index không thực thi UNIQUE. |
| “Khóa có cùng giá trị băm sẽ trả sai bản ghi.” | Bộ máy tra cứu vẫn kiểm tra khóa thực để xử lý va chạm. |
| “Lập chỉ mục cột nhạy cảm làm dữ liệu an toàn hơn.” | Chỉ mục là cấu trúc truy cập, không thay thế phân quyền, mã hóa hay chính sách dữ liệu. |

Một vấn đề thường gặp khác là dùng biểu thức lên cột: **WHERE LOWER(email) = ...** không nhất thiết sử dụng hiệu quả B-tree thông thường trên **email**. Tùy DBMS, có thể cần chuẩn hóa dữ liệu, chỉ mục biểu thức hoặc cơ chế so sánh phù hợp. Tương tự, việc B-tree giúp một số truy vấn **LIKE 'prefix%'** phụ thuộc collation/operator class và cách tối ưu của hệ quản trị, không phải mọi kiểu LIKE đều dùng tốt.

## 9. Quy trình chọn chỉ mục trong thực tế

1. **Thu thập truy vấn thật:** điều kiện WHERE, JOIN, ORDER BY, LIMIT, số dòng trả về và tần suất.
2. **Nhận diện kiểu truy cập:** tìm bằng đơn lẻ; kết hợp bằng + khoảng; sắp xếp; hay duyệt phạm vi liên tiếp.
3. **Chọn cấu trúc ban đầu:** ưu tiên B-tree cho tính linh hoạt và các truy vấn có thứ tự/khoảng; chỉ cân nhắc hash cho truy vấn bằng chuyên biệt nếu DBMS hỗ trợ rõ ràng.
4. **Xác định khóa và thứ tự cột:** xét độ chọn lọc, các cột so sánh bằng trước phần khoảng/thứ tự theo kế hoạch truy vấn, tránh tạo nhiều chỉ mục trùng chức năng.
5. **Đo và kiểm tra mặt trái:** xem EXPLAIN, độ trễ đọc, tốc độ ghi, dung lượng, việc xây index và chi phí bảo trì.
6. **Đưa qua migration và giám sát:** thử trên dữ liệu đại diện, triển khai có kiểm soát, theo dõi thay đổi của workload và điều chỉnh khi cần.

### Bài tập tự kiểm tra

**Tình huống A.** Bảng có mười triệu giao dịch. API tìm theo **transaction_code = ?**, không sắp xếp, nhưng mã giao dịch phải duy nhất. Bạn bắt đầu bằng loại nào?

**Gợi ý:** một **UNIQUE B-tree** (hoặc cơ chế UNIQUE mặc định thích hợp của DBMS) vừa tìm bằng vừa bảo đảm ràng buộc; không đổi sang hash chỉ vì câu truy vấn có dấu bằng.

**Tình huống B.** Báo cáo lọc **account_id = ?**, **created_at BETWEEN ? AND ?**, rồi **ORDER BY created_at**. Loại nào thuận tiện hơn?

**Gợi ý:** B-tree ghép bắt đầu bằng **account_id**, tiếp đến **created_at**, vì có thể định vị tài khoản và duyệt dải thời gian theo thứ tự. Đo lại với dữ liệu thực.

**Tình huống C.** API lọc **status = 'PAID'** và trả 80% số dòng. Có nên thêm hash index?

**Gợi ý:** chưa có cơ sở. Khả năng chọn lọc thấp khiến đọc qua index có thể không lợi; cần xem số dòng, cột trả về, kế hoạch và khả năng điều chỉnh truy vấn.

## 10. Ghi nhớ

**B-tree/B+ tree** là cấu trúc cân bằng, giữ thứ tự khóa và phù hợp cả tìm bằng lẫn tìm theo khoảng, sắp xếp và khóa ghép. **Hash index** định vị theo bucket, chủ yếu phục vụ tìm bằng chính xác, nhưng không duy trì thứ tự khóa. Cấu trúc nào nhanh hơn phụ thuộc mẫu truy vấn, phân bố dữ liệu, chi phí I/O, tải ghi và hệ quản trị cụ thể.

Trong ứng dụng Java, hãy xuất phát từ **SQL thật và ràng buộc dữ liệu**, thiết kế chỉ mục tương ứng, xác minh bằng kế hoạch thực thi rồi quản lý thay đổi qua migration. Chỉ mục là một phần của thiết kế persistence bền vững: nó cần cân bằng hiệu năng đọc, chi phí ghi, toàn vẹn dữ liệu và khả năng vận hành lâu dài.
