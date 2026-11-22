# Hàng rộng, cột văn bản lớn và tách dữ liệu ít truy cập

Một bảng có thể chứa nhiều cột phục vụ các mục đích khác nhau. Một số cột được đọc trong gần như mọi yêu cầu, chẳng hạn mã định danh, trạng thái, thời điểm tạo và số tiền. Những cột khác chứa văn bản dài, JSON lớn, ghi chú, payload hoặc dữ liệu chỉ được xem khi người dùng mở màn hình chi tiết. Nếu tất cả nằm trong cùng một hàng, các truy vấn thường xuyên có thể phải đọc và truyền nhiều dữ liệu hơn nhu cầu.

**Hàng rộng** (*wide row*) là hàng có nhiều cột hoặc tổng kích thước cột lớn. **Tách dữ liệu theo chiều dọc** (*vertical partitioning*) là cách chia các nhóm cột của cùng một thực thể sang các bảng hoặc cấu trúc riêng, thường liên kết bằng khóa chính. Mục tiêu là giữ dữ liệu thường xuyên truy cập trong phần lõi gọn nhẹ, chỉ tải dữ liệu lớn hoặc ít dùng khi thật sự cần.

Trong module **DATABASE_PERFORMANCE**, cần hiểu tác động của độ rộng hàng và cột văn bản lớn lên I/O, buffer cache, chỉ mục và kế hoạch thực thi; biết khi nào nên tách bảng, khi nào nên giữ chung; và triển khai thay đổi sao cho toàn vẹn dữ liệu, giao dịch và hiệu năng đều được kiểm chứng. Tách dữ liệu chỉ có lợi khi phù hợp với mẫu truy cập và không tạo thêm chi phí join vượt quá lợi ích thu được.

## 1. Hàng rộng ảnh hưởng hiệu năng như thế nào?

Hệ quản trị cơ sở dữ liệu đọc và ghi dữ liệu theo các đơn vị lưu trữ như page hoặc block. Một page chứa được bao nhiêu hàng phụ thuộc kích thước hàng, overhead của page, cấu trúc quản lý hàng và storage engine. Khi hàng lớn hơn, số hàng trên mỗi page thường giảm.

Giả sử phần dữ liệu sử dụng được của một page là 8 KB. Nếu một hàng trung bình chiếm 400 byte, page có thể chứa nhiều hàng hơn đáng kể so với trường hợp mỗi hàng chiếm 2 KB. Con số thực tế còn phụ thuộc header, null bitmap, alignment, slot array và cách lưu cột biến độ dài.

Hàng rộng có thể gây ra các tác động sau:

- **Mật độ hàng thấp:** một lần đọc page lấy được ít hàng hữu ích hơn.
- **Tăng I/O:** truy vấn quét cùng số lượng bản ghi có thể phải đọc nhiều page hơn.
- **Giảm hiệu quả buffer cache:** cùng dung lượng cache chứa được ít hàng hơn, làm tăng khả năng phải đọc lại từ storage.
- **Tăng chi phí truyền dữ liệu:** nhiều byte hơn đi từ database đến ứng dụng, kể cả khi ứng dụng chỉ dùng một phần nội dung.
- **Tăng chi phí xử lý:** copy, giải mã, chuyển đổi kiểu, serialize và deserialize dữ liệu lớn tiêu tốn CPU và bộ nhớ.
- **Tăng chi phí ghi:** cập nhật hàng lớn có thể phát sinh thêm ghi page, transaction log hoặc dữ liệu phiên bản tùy engine.
- **Ảnh hưởng chỉ mục:** nếu dữ liệu lớn nằm trong khóa hoặc phần dữ liệu của index, cấu trúc chỉ mục có thể phình to và giảm hiệu quả cache.

Không phải mọi cột lớn đều được lưu nguyên vẹn trong page chứa phần còn lại của hàng. Nhiều hệ quản trị có cơ chế lưu giá trị lớn ngoài hàng (*off-row*), nén hoặc chia thành các phần riêng. Cơ chế này giảm áp lực lên page chính nhưng có thể phát sinh lần truy cập bổ sung khi đọc giá trị lớn.

### Mật độ page và số hàng cần đọc

Giả sử một truy vấn cần 100.000 hàng. Nếu page chứa được nhiều hàng phù hợp, số page phải đọc sẽ thấp hơn đáng kể so với trường hợp page chỉ chứa được vài hàng. Trong thực tế, hàng không phân bố đều, một page có thể chứa hàng không thỏa điều kiện, và chỉ mục có thể thay đổi đường truy cập. Tuy nhiên, nguyên lý vẫn đúng: hàng càng rộng, một lần đọc vật lý thường mang theo ít bản ghi hơn.

Khi điều tra, nên xem logical reads, physical reads, page density hoặc chỉ số tương đương của hệ quản trị, kích thước hàng trung bình và số byte trả về. Chỉ nhìn số hàng trả về không đủ để đánh giá chi phí lưu trữ và truyền dữ liệu.

## 2. Cột văn bản lớn và LOB

Các kiểu dữ liệu lưu nội dung dài thường được gọi chung là LOB (*Large Object*). Tên kiểu cụ thể tùy hệ quản trị, ví dụ `TEXT`, `CLOB`, `BLOB`, `VARCHAR(MAX)`, `VARBINARY(MAX)` hoặc kiểu chuỗi có giới hạn lớn.

Ví dụ về dữ liệu lớn:

- Nội dung bài viết hoặc mô tả sản phẩm dài.
- Ghi chú hỗ trợ, lịch sử trao đổi hoặc nội dung email.
- Payload JSON/XML hoặc dữ liệu sự kiện.
- Tệp nhị phân, ảnh, tài liệu PDF hoặc nội dung đính kèm.
- Văn bản trích xuất từ tài liệu hoặc kết quả phân tích.

Các giá trị này thường có độ dài biến động mạnh. Một cột có thể chỉ chứa vài chục ký tự ở đa số hàng nhưng một số hàng chứa hàng trăm kilobyte hoặc lớn hơn. Vì vậy, kích thước hàng trung bình có thể che khuất các trường hợp cực lớn; cần theo dõi cả phân vị và giá trị tối đa.

### Lưu trong hàng và lưu ngoài hàng

Tùy engine và kích thước giá trị, dữ liệu có thể được lưu trực tiếp trong hàng, một phần trong hàng và phần còn lại ở vùng riêng, hoặc ngoài hàng với con trỏ/tham chiếu trong hàng chính.

Lưu ngoài hàng giúp hàng chính gọn hơn nhưng đọc LOB có thể cần thêm lần truy cập. Nếu truy vấn chỉ lấy ID và trạng thái, engine thường không cần đọc toàn bộ LOB; nhưng nếu ứng dụng dùng `SELECT *`, ORM tự tải quan hệ hoặc serializer truy cập thuộc tính LOB, dữ liệu lớn có thể bị đọc ngoài ý muốn.

### Cột lớn không đồng nghĩa luôn phải tách bảng

Nếu nội dung lớn được đọc trong hầu hết yêu cầu và luôn cần nhất quán cùng các cột khác, việc tách riêng có thể làm tăng join mà không giảm I/O thực tế. Nếu engine đã quản lý off-row hiệu quả và truy vấn không lấy LOB, bảng hiện tại có thể đã đủ tốt.

Ngược lại, nếu cột lớn chỉ được đọc trong một tỷ lệ nhỏ yêu cầu, tách nó khỏi bảng lõi có thể giảm lượng dữ liệu phải mang theo khi quét phần lớn bản ghi. Quyết định phải dựa trên tần suất đọc, kích thước, cách engine lưu trữ và kế hoạch thực thi.

## 3. Đo mẫu truy cập trước khi thay đổi mô hình

Trước khi tách bảng, cần xác định cột nào thực sự nóng (*hot*) và cột nào ít truy cập (*cold*). Không nên chỉ dựa vào tên cột hoặc phỏng đoán.

| Nhóm quan sát | Câu hỏi cần trả lời | Dữ liệu nên thu thập |
|---|---|---|
| Tần suất đọc | Cột nào xuất hiện trong phần lớn truy vấn? | Query fingerprint, số lần thực thi, projection/column access nếu công cụ hỗ trợ |
| Kích thước | Cột nào làm hàng lớn bất thường? | Độ dài trung bình, p95/p99, tối đa và số byte theo kiểu dữ liệu |
| Tần suất tải nội dung | Bao nhiêu yêu cầu thật sự cần LOB? | Tỷ lệ endpoint hoặc thao tác đọc nội dung chi tiết |
| Chi phí I/O | Bảng có mật độ page thấp hoặc đọc nhiều page không? | Logical/physical reads, page density, buffer hit và storage latency |
| Chi phí ứng dụng | Có truyền nội dung lớn dù không hiển thị không? | Response size, bytes transferred, thời gian serialize/deserialize |
| Ghi và cập nhật | Nội dung lớn thay đổi thường xuyên đến đâu? | Tần suất update, log bytes, lock wait và transaction duration |

Nên phân tích các truy vấn phổ biến và truy vấn chậm riêng biệt. Một cột ít được đọc nhưng mỗi lần đọc rất tốn kém có thể cần giải pháp khác với cột được đọc thường xuyên nhưng giá trị nhỏ. Cũng cần nhận diện ORM hoặc data access layer có tự động lấy toàn bộ cột dù câu lệnh nghiệp vụ chỉ cần một phần.

## 4. Thiết kế bảng lõi và bảng phần mở rộng

Một mô hình phổ biến là giữ các thuộc tính thường xuyên dùng trong bảng lõi và chuyển nhóm dữ liệu lớn hoặc ít truy cập sang bảng phần mở rộng có quan hệ một-một.

Ví dụ ban đầu:

```sql
CREATE TABLE customer (
    customer_id   BIGINT PRIMARY KEY,
    email         VARCHAR(320) NOT NULL,
    display_name  VARCHAR(200) NOT NULL,
    status        VARCHAR(20) NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    profile_text  TEXT,
    preferences   TEXT,
    support_notes TEXT
);
```

Nếu các trường `profile_text`, `preferences` và `support_notes` chỉ được tải trong một số màn hình, có thể tách như sau:

```sql
CREATE TABLE customer (
    customer_id  BIGINT PRIMARY KEY,
    email        VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP NOT NULL
);

CREATE TABLE customer_detail (
    customer_id   BIGINT PRIMARY KEY,
    profile_text  TEXT,
    preferences   TEXT,
    support_notes TEXT,
    CONSTRAINT fk_customer_detail_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
);
```

`customer_detail.customer_id` vừa là khóa chính vừa là khóa ngoại, nên mỗi khách hàng có tối đa một hàng chi tiết. Nếu nghiệp vụ yêu cầu mọi khách hàng luôn có chi tiết, ứng dụng hoặc quy trình tạo dữ liệu cần bảo đảm hàng chi tiết được tạo cùng transaction; foreign key một chiều không bắt buộc mọi hàng cha phải có hàng con.

### Truy vấn chỉ cần dữ liệu lõi

```sql
SELECT customer_id, email, display_name, status, created_at
FROM customer
WHERE status = 'ACTIVE'
ORDER BY created_at DESC;
```

Truy vấn này không cần join `customer_detail`. Bảng lõi gọn hơn, các page và index phục vụ danh sách khách hàng có thể chứa nhiều hàng hữu ích hơn.

### Truy vấn cần dữ liệu chi tiết

```sql
SELECT c.customer_id, c.display_name,
       d.profile_text, d.preferences, d.support_notes
FROM customer AS c
LEFT JOIN customer_detail AS d
  ON d.customer_id = c.customer_id
WHERE c.customer_id = ?;
```

Chỉ màn hình chi tiết mới lấy các cột lớn. Vì `customer_detail.customer_id` là khóa chính, phép join có tối đa một hàng chi tiết cho mỗi khách hàng. Nếu bảng chi tiết chưa tồn tại, `LEFT JOIN` vẫn trả hàng lõi với các cột chi tiết là `NULL`.

### Chọn INNER JOIN hay LEFT JOIN

- Dùng `INNER JOIN` nếu chỉ muốn trả thực thể có hàng chi tiết và sự hiện diện của hàng chi tiết là điều kiện bắt buộc của truy vấn.
- Dùng `LEFT JOIN` nếu dữ liệu chi tiết có thể chưa được tạo hoặc người dùng vẫn cần xem thông tin lõi.
- Nếu chỉ kiểm tra hàng chi tiết có tồn tại, có thể dùng `EXISTS` thay vì lấy các cột của bảng chi tiết.

## 5. Tách theo nhóm truy cập và vòng đời dữ liệu

Không phải mọi cột ít truy cập đều cần tách theo cùng một cách. Hãy phân biệt ít truy cập vì chỉ dùng ở màn hình chi tiết với ít truy cập vì dữ liệu đã cũ hoặc thuộc kho lưu trữ.

### Tách theo chiều dọc

Vertical partitioning chia các cột của cùng thực thể thành nhiều bảng hoặc cấu trúc. Ví dụ, bảng `account` giữ email, trạng thái và thời điểm tạo; bảng `account_document` giữ nội dung xác minh hoặc tệp đính kèm.

Đặc điểm:

- Khóa chính của bảng phần mở rộng liên kết về thực thể lõi.
- Bảng lõi phục vụ truy vấn nóng.
- Nội dung lớn chỉ được tải khi thao tác cần.
- Có thể đặt quyền truy cập khác nhau cho nhóm dữ liệu nhạy cảm.

### Tách theo chiều ngang hoặc lưu trữ lạnh

Horizontal partitioning chia hàng theo phạm vi, chẳng hạn tháng, năm hoặc tenant. Archiving chuyển các hàng cũ sang bảng hoặc hệ lưu trữ khác. Đây là vấn đề khác với tách cột theo chiều dọc.

Ví dụ, lịch sử giao dịch cũ được chuyển sang partition lưu trữ ít truy cập. Nếu một hàng vẫn có cùng cấu trúc nhưng chỉ khác tuổi dữ liệu, phân vùng theo thời gian hoặc archival có thể phù hợp hơn việc tách cột.

### Kết hợp hai hướng

Một hệ thống có thể vừa tách cột LOB khỏi bảng lõi, vừa phân vùng bảng lịch sử theo thời gian. Cần kiểm soát số lượng cấu trúc, khóa ngoại, truy vấn hợp nhất và quy trình lưu trữ để tránh mô hình quá phức tạp.

## 6. Cách lưu nội dung rất lớn

Với nội dung hàng trăm kilobyte đến nhiều megabyte, cần đánh giá có nên lưu trực tiếp trong cơ sở dữ liệu hay dùng object storage và chỉ giữ metadata/tham chiếu trong database.

### Lưu LOB trong cơ sở dữ liệu

Ưu điểm:

- Dữ liệu và metadata có thể tham gia cùng transaction.
- Backup, quyền truy cập và lifecycle có thể được quản lý qua nền tảng database.
- Có thể dùng cơ chế replication, mã hóa và kiểm soát nhất quán sẵn có.

Chi phí:

- Database storage, backup và replication có thể tăng đáng kể.
- Ghi LOB có thể làm transaction log lớn và kéo dài thời gian ghi.
- Đọc nội dung lớn có thể tăng I/O và băng thông kết nối.
- Các tác vụ backup/restore hoặc đồng bộ có thể lâu hơn.

### Lưu object storage và giữ metadata

Với tệp lớn hoặc nội dung cần phân phối qua CDN, object storage có thể phù hợp. Database lưu ID, object key, kích thước, content type, checksum, trạng thái và quyền sở hữu.

```sql
CREATE TABLE customer_document (
    document_id  BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    object_key   VARCHAR(500) NOT NULL,
    content_type VARCHAR(150) NOT NULL,
    byte_size    BIGINT NOT NULL,
    checksum     VARCHAR(128),
    created_at   TIMESTAMP NOT NULL,
    CONSTRAINT fk_customer_document_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
);
```

Ứng dụng đọc metadata từ database rồi tải nội dung từ object storage khi được phép. Database transaction không tự động bao trùm thao tác ghi object storage; cần thiết kế trạng thái, retry, cleanup và tính idempotent để xử lý trường hợp một bên thành công còn bên kia thất bại.

### Chọn theo đặc điểm dữ liệu

| Đặc điểm | Lưu LOB trong database | Object storage |
|---|---|---|
| Cần transaction cùng hàng metadata | Thuận lợi hơn | Cần quy trình phối hợp riêng |
| Tệp rất lớn và ít cập nhật | Có thể làm database phình lớn | Thường phù hợp hơn |
| Cần truy vấn nội dung bằng SQL | Có thể phù hợp tùy kiểu dữ liệu/công cụ | Thường phải tải hoặc lập chỉ mục bên ngoài |
| Phân phối tệp qua CDN | Có thể cần tầng bổ sung | Thường thuận tiện |
| Backup/restore | Nằm trong quy trình database | Cần backup và lifecycle riêng |
| Chi phí vận hành | Phụ thuộc dung lượng và I/O database | Phụ thuộc request, storage, egress và chính sách nhà cung cấp |

Không nên chuyển mọi LOB sang object storage chỉ vì kích thước lớn. Cần tính chi phí, yêu cầu nhất quán, bảo mật, độ sẵn sàng và quy trình xóa dữ liệu.

## 7. Tránh đọc dữ liệu lớn ngoài ý muốn

Ngay cả khi chưa tách bảng, nhiều vấn đề có thể được giải quyết bằng cách điều chỉnh projection và cách truy cập dữ liệu.

### Không dùng SELECT * trong truy vấn nóng

```sql
-- Có thể tải cả các cột văn bản lớn không cần thiết.
SELECT *
FROM customer
WHERE status = 'ACTIVE';

-- Chỉ lấy các cột cần cho màn hình danh sách.
SELECT customer_id, email, display_name, status
FROM customer
WHERE status = 'ACTIVE';
```

Projection hẹp giảm số byte cần đọc/trả về ở những engine và kế hoạch có thể tránh truy cập LOB, đồng thời giảm chi phí truyền dữ liệu và xử lý ở ứng dụng. Với một số storage engine, hàng gốc vẫn cần được đọc nhưng LOB ngoài hàng có thể không được tải nếu cột không được tham chiếu.

### Tải chi tiết theo nhu cầu

Thiết kế API có thể tách endpoint danh sách và endpoint chi tiết. Danh sách trả metadata gọn; khi người dùng mở một bản ghi, ứng dụng mới lấy nội dung dài hoặc tệp. Tránh eager loading LOB cho toàn bộ danh sách chỉ để hiển thị một phần nội dung.

### Streaming nội dung lớn

Với tệp hoặc văn bản lớn, cân nhắc streaming thay vì đọc toàn bộ vào bộ nhớ ứng dụng. Streaming giảm peak memory và cho phép gửi dữ liệu theo từng phần. Cần quản lý thời gian giữ connection, timeout, backpressure, retry và việc đóng stream khi client ngắt kết nối.

### Tránh N+1 query khi tải chi tiết

Nếu một trang hiển thị 50 thực thể và ứng dụng gọi thêm một truy vấn riêng cho mỗi bản ghi chi tiết, có thể tạo 51 truy vấn. Việc tách bảng có thể làm N+1 trở nên rõ hơn. Hãy tải chi tiết theo batch cho tập ID cần thiết, hoặc chỉ tải theo từng thực thể khi người dùng thật sự mở nội dung.

## 8. Thiết kế chỉ mục sau khi tách dữ liệu

Sau khi tách bảng, cần bảo đảm cả bảng lõi và bảng chi tiết có chỉ mục phù hợp với đường truy cập.

- Bảng lõi thường có primary key và các index cho bộ lọc/sắp xếp phổ biến.
- Bảng chi tiết dùng primary key trùng khóa thực thể hoặc unique key trên `customer_id` để bảo đảm tối đa một hàng chi tiết.
- Bảng tài liệu nhiều hàng cho một thực thể cần index trên `(customer_id, created_at)` hoặc khóa phù hợp với cách liệt kê.
- Foreign key cần index ở phía tham chiếu nếu workload join, xóa hoặc cập nhật quan hệ cần tìm nhanh hàng con; một số hệ quản trị không tự tạo index cho foreign key.
- Không tạo index trên toàn bộ nội dung LOB nếu truy vấn không cần tìm kiếm theo nội dung. Full-text index hoặc cấu trúc tìm kiếm chuyên biệt có chi phí riêng.

Ví dụ một khách hàng có nhiều tài liệu:

```sql
CREATE TABLE customer_document (
    document_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    title       VARCHAR(300) NOT NULL,
    content     TEXT,
    created_at  TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
);

CREATE INDEX ix_customer_document_customer_created
ON customer_document (customer_id, created_at DESC, document_id DESC);
```

Chỉ mục ghép hỗ trợ lấy danh sách tài liệu mới nhất của một khách hàng và có tie-breaker để thứ tự ổn định khi timestamp trùng. Truy vấn danh sách có thể chỉ lấy `document_id`, `title` và `created_at`; nội dung `content` chỉ được tải khi mở tài liệu.

## 9. Khác biệt lưu trữ theo hệ quản trị

Các hệ quản trị có cách quản lý hàng rộng và LOB khác nhau. Không nên suy luận từ một nền tảng sang nền tảng khác.

### PostgreSQL: TOAST

PostgreSQL dùng cơ chế TOAST cho các giá trị lớn. Tùy kích thước và chiến lược lưu trữ, giá trị có thể được nén hoặc chuyển ra bảng TOAST riêng, trong khi hàng chính giữ thông tin tham chiếu. Các chiến lược như `PLAIN`, `EXTENDED`, `EXTERNAL` và `MAIN` ảnh hưởng đến việc nén và lưu ngoài hàng đối với các kiểu hỗ trợ TOAST.

Điều này giúp hàng chính không phải chứa toàn bộ giá trị rất lớn. Tuy vậy, truy vấn chọn cột lớn vẫn cần truy xuất và có thể giải nén dữ liệu. Khi phân tích, hãy so sánh truy vấn không lấy LOB với truy vấn lấy LOB, xem kích thước dữ liệu, buffer reads và chi phí truyền tải. Không nên giả định mọi cột text đều được đưa ra ngoài hàng; quyết định phụ thuộc kích thước thực tế và chiến lược lưu.

### SQL Server: row-overflow và LOB allocation

SQL Server có cơ chế lưu dữ liệu row-overflow khi tổng kích thước các cột biến độ dài trong hàng vượt giới hạn lưu trong hàng, và cơ chế lưu LOB cho các kiểu dữ liệu lớn. Cách lưu cụ thể phụ thuộc kiểu dữ liệu, tùy chọn và phiên bản. `VARCHAR(MAX)`, `NVARCHAR(MAX)` và `VARBINARY(MAX)` có thể được lưu trong hàng hoặc ngoài hàng tùy kích thước và thiết lập liên quan.

Khi truy vấn chỉ lấy các cột thông thường, engine có thể tránh đọc toàn bộ LOB ngoài hàng. Nhưng việc lấy LOB có thể phát sinh thêm I/O. Hãy kiểm tra logical reads, LOB logical reads trong thống kê I/O khi có, kích thước hàng và execution plan. Không nên dùng `TEXT`/`NTEXT` cho thiết kế mới khi các kiểu hiện đại phù hợp hơn.

### MySQL/InnoDB: off-page storage

InnoDB có thể lưu một phần hoặc toàn bộ giá trị cột biến độ dài lớn ngoài page chính, tùy row format, kích thước hàng và cấu hình. Với một số row format, một phần tiền tố của giá trị có thể vẫn ở hàng chính cùng con trỏ đến dữ liệu ngoài trang; chi tiết khác nhau giữa `COMPACT`, `DYNAMIC`, `COMPRESSED` và phiên bản.

Hàng rộng có thể làm giảm số hàng trên một page và tăng số lần truy cập trang ngoài khi lấy cột lớn. Hãy kiểm tra row format, kích thước thực tế, buffer pool reads và lượng dữ liệu trả về. Không nên mặc định mọi `TEXT` đều luôn nằm hoàn toàn ngoài hàng.

### Oracle Database: LOB locator và SecureFiles

Oracle cung cấp các kiểu LOB như `CLOB`, `NCLOB` và `BLOB`. Một hàng có thể giữ LOB locator, còn nội dung được lưu trong segment LOB riêng. Cấu hình lưu trữ, SecureFiles/BasicFiles, inline threshold và tùy chọn nén hoặc deduplicate ảnh hưởng đến cách lưu và hiệu năng. Các khả năng cụ thể phụ thuộc phiên bản và cấu hình tablespace.

Khi truy vấn chỉ lấy metadata, tránh truy cập LOB locator hoặc đọc nội dung nếu không cần. Khi tải LOB, đánh giá cách driver đọc, streaming, chunk size, buffer và thời gian giữ kết nối. Cần xem kế hoạch và thống kê I/O ở cả segment bảng lẫn segment LOB.

## 10. Giao dịch và tính nhất quán khi tách bảng

Nếu dữ liệu lõi và dữ liệu chi tiết phải được tạo hoặc cập nhật cùng nhau, hãy thực hiện trong cùng transaction khi cả hai nằm trong cùng database:

```sql
BEGIN;

INSERT INTO customer (
    customer_id, email, display_name, status, created_at
)
VALUES (?, ?, ?, 'ACTIVE', ?);

INSERT INTO customer_detail (
    customer_id, profile_text, preferences, support_notes
)
VALUES (?, ?, ?, ?);

COMMIT;
```

Cú pháp transaction cụ thể có thể khác theo driver và hệ quản trị; ví dụ thể hiện hai thao tác thuộc cùng một đơn vị nguyên tử. Nếu thao tác thứ hai thất bại, transaction cần rollback để không tạo thực thể lõi ở trạng thái không hợp lệ theo quy tắc nghiệp vụ.

### Ràng buộc quan hệ

Primary key và foreign key bảo đảm hàng chi tiết tham chiếu đến hàng lõi hợp lệ. Nếu quan hệ là một-một, khóa chính hoặc unique constraint trên khóa ngoại ở bảng chi tiết ngăn tạo nhiều hàng chi tiết cho cùng một thực thể. Nếu quan hệ là một-nhiều, khóa chính riêng cho bảng con và index trên khóa cha phù hợp hơn.

### Xóa và cập nhật

Khi xóa hàng lõi, cần xác định chính sách với dữ liệu chi tiết: cascade delete, restrict, soft delete hay chuyển sang lưu trữ. Cascade có thể tiện nhưng xóa hàng loạt nhiều LOB có thể tạo transaction lớn và nhiều log. Với dữ liệu lớn, có thể cần xóa theo batch hoặc quy trình archival có kiểm soát.

### Tách sang object storage

Nếu nội dung nằm ngoài database, không có transaction ACID chung tự động giữa database và object store. Có thể dùng trạng thái `PENDING`, ghi object trước rồi cập nhật metadata, hoặc ghi metadata trước rồi xử lý upload qua outbox/background worker. Cần xử lý retry idempotent, object mồ côi, metadata trỏ đến object chưa tồn tại và cleanup khi thất bại.

## 11. Di chuyển từ bảng rộng sang mô hình tách

Thay đổi schema trên bảng lớn cần kế hoạch để tránh downtime, mất dữ liệu hoặc làm các phiên bản ứng dụng không tương thích.

1. **Đo baseline:** kích thước bảng, phân bố độ dài cột, query workload, page density, I/O và độ trễ.
2. **Tạo bảng chi tiết:** tạo primary key, foreign key, index và quyền truy cập phù hợp.
3. **Triển khai tương thích:** cập nhật ứng dụng để đọc được cấu trúc cũ và mới trong giai đoạn chuyển đổi nếu cần.
4. **Backfill theo batch:** chuyển dữ liệu cũ sang bảng chi tiết theo khóa, giới hạn kích thước batch và theo dõi log/I/O.
5. **Đồng bộ ghi mới:** dùng dual-write có kiểm soát, trigger hoặc change-data capture nếu cần; phải có cơ chế đối soát.
6. **Đối chiếu dữ liệu:** so sánh số hàng, khóa, checksum hoặc giá trị đại diện giữa nguồn và đích.
7. **Chuyển đọc:** chuyển từng nhóm truy vấn sang bảng mới, theo dõi lỗi, latency và tải.
8. **Ngừng ghi cột cũ:** chỉ thực hiện khi mọi ứng dụng và job đã chuyển sang mô hình mới.
9. **Xóa cột cũ theo giai đoạn:** sau khi xác minh backup, rollback và thời gian ổn định.

### Backfill an toàn

Không nên chuyển toàn bộ hàng trong một transaction khổng lồ nếu bảng lớn. Batch theo khóa tăng dần hoặc theo khoảng khóa giúp giới hạn transaction log, lock duration và khả năng rollback. Mỗi batch cần idempotent để có thể chạy lại sau lỗi.

Nếu dữ liệu vẫn được cập nhật trong lúc backfill, cần tránh ghi đè giá trị mới bằng bản sao cũ. Có thể dùng cột version/update timestamp, CDC hoặc khóa/đồng bộ phù hợp. Sau backfill phải có bước đối soát cuối trước khi chuyển đọc hoàn toàn.

### Kế hoạch rollback

Giữ khả năng đọc dữ liệu cũ trong giai đoạn quan sát, ghi nhận trạng thái backfill và chuẩn bị cách đưa ứng dụng về phiên bản tương thích. Không xóa cột nguồn ngay khi vừa chuyển một endpoint. Chỉ loại bỏ cấu trúc cũ khi đã xác nhận không còn consumer và có backup/khả năng phục hồi phù hợp.

## 12. Đo lường kết quả sau khi tách

Mục tiêu là giảm chi phí của truy vấn nóng mà vẫn giữ trải nghiệm truy cập chi tiết ở mức chấp nhận được. So sánh trước và sau trên cùng tập dữ liệu và cùng kịch bản tải.

| Nhóm | Chỉ số cần so sánh |
|---|---|
| Truy vấn lõi | p50/p95/p99, logical reads, physical reads, rows per page nếu có |
| Truy vấn chi tiết | thời gian join, LOB reads, bytes trả về và độ trễ tải nội dung |
| Tài nguyên | CPU, buffer/cache hit, storage latency, memory và temp I/O |
| Ghi dữ liệu | insert/update latency, transaction log bytes, lock wait và throughput |
| Ứng dụng | response size, peak memory, thời gian serialize/deserialize, số query mỗi request |
| Vận hành | dung lượng bảng/index/LOB, backup size, replication lag và thời gian restore |

### Ví dụ đánh giá

Giả sử endpoint danh sách khách hàng trước đây trả cả `profile_text` và `support_notes`, dù giao diện chỉ hiển thị tên và trạng thái. Sau khi tách bảng chi tiết, endpoint danh sách chỉ đọc bảng lõi.

| Chỉ số minh họa | Trước tách | Sau tách |
|---|---:|---:|
| Bytes trung bình trả về mỗi hàng | 18 KB | 0,7 KB |
| Logical reads mỗi yêu cầu | 420 | 95 |
| p95 endpoint danh sách | 180 ms | 62 ms |
| p95 endpoint chi tiết | 180 ms | 195 ms |

Các số liệu chỉ minh họa. Endpoint chi tiết có thể tăng nhẹ do join hoặc truy vấn bổ sung, trong khi endpoint danh sách giảm đáng kể. Cần đánh giá theo tỷ lệ sử dụng thực tế: nếu 95% yêu cầu là danh sách và 5% là chi tiết, lợi ích tổng thể có thể rõ rệt. Nếu hầu hết yêu cầu luôn lấy cả nội dung, việc tách có thể không có lợi.

### Kiểm tra kế hoạch thực thi

- Xác nhận truy vấn nóng không còn đọc bảng chi tiết hoặc LOB ngoài nhu cầu.
- Xác nhận join chi tiết dùng primary key/index phù hợp và không gây scan ngoài ý muốn.
- So sánh estimated rows với actual rows sau khi thay đổi cardinality và quan hệ.
- Kiểm tra có phát sinh N+1 query hoặc round trip bổ sung ở tầng ứng dụng không.
- Kiểm tra truy vấn lấy LOB có streaming hoặc projection phù hợp.
- Đo dưới tải đồng thời để phát hiện connection pool, I/O hoặc lock wait mới.

## 13. Những sai lầm thường gặp

1. **Tách bảng chỉ vì có cột TEXT:** cần đo kích thước và tần suất truy cập trước.
2. **Tách quá nhiều nhóm cột:** mỗi yêu cầu phải join nhiều bảng, làm tăng độ phức tạp và round trip.
3. **Giữ cột lớn trong truy vấn danh sách:** `SELECT *` hoặc ORM eager loading có thể tiếp tục tải dữ liệu không cần thiết.
4. **Không tạo unique key ở bảng chi tiết:** quan hệ một-một có thể biến thành một-nhiều và nhân bản hàng khi join.
5. **Quên index khóa ngoại:** join, xóa hoặc cập nhật quan hệ có thể phải quét bảng con.
6. **Tạo index trên toàn bộ LOB:** tăng chi phí và dung lượng mà không phù hợp với kiểu tìm kiếm.
7. **Tách sang object storage mà thiếu quy trình nhất quán:** database và object store có thể lệch trạng thái khi một bước thất bại.
8. **Backfill trong một transaction quá lớn:** gây log tăng, khóa kéo dài, replication lag và khó rollback.
9. **Dual-write không đối soát:** hai bản dữ liệu có thể lệch mà không được phát hiện.
10. **Chỉ đo endpoint danh sách:** endpoint chi tiết hoặc workload ghi có thể bị chậm hơn.
11. **Nhầm vertical partitioning với archival:** tách cột và chuyển hàng cũ giải quyết hai mẫu truy cập khác nhau.
12. **Giả định mọi hệ quản trị lưu LOB giống nhau:** TOAST, row-overflow, off-page storage và LOB segment có cơ chế riêng.

## 14. Danh sách kiểm tra trước khi triển khai

- [ ] Đã đo kích thước hàng và phân bố độ dài của các cột văn bản lớn.
- [ ] Đã xác định tỷ lệ truy vấn cần đọc nội dung lớn so với truy vấn chỉ cần dữ liệu lõi.
- [ ] Đã kiểm tra cơ chế lưu LOB/off-row của hệ quản trị và phiên bản đang dùng.
- [ ] Đã xác định nhóm cột nóng/lạnh theo workload thực tế.
- [ ] Đã chọn mô hình tách một-một, một-nhiều, archival hoặc object storage phù hợp.
- [ ] Đã thiết kế primary key, unique constraint, foreign key và index cho các đường truy cập.
- [ ] Đã sửa projection/API/ORM để không tải nội dung lớn ngoài nhu cầu.
- [ ] Đã xác định transaction, xóa dữ liệu và xử lý lỗi giữa database với object storage.
- [ ] Đã có kế hoạch backfill theo batch, đồng bộ ghi, đối soát và rollback.
- [ ] Đã đo lại I/O, buffer cache, độ trễ, throughput, response size và chi phí ghi.
- [ ] Đã kiểm tra cả truy vấn danh sách lẫn truy vấn chi tiết dưới tải đại diện.

Hàng rộng và cột văn bản lớn có thể làm giảm mật độ page, tăng I/O, chiếm buffer cache và khiến ứng dụng truyền dữ liệu không cần thiết. Khi một nhóm cột chỉ được truy cập ở một phần nhỏ yêu cầu, tách chúng sang bảng chi tiết hoặc kho đối tượng có thể giúp bảng lõi gọn hơn. Quyết định cần dựa trên mẫu truy cập, cơ chế lưu LOB của hệ quản trị, chi phí join và yêu cầu nhất quán. Hãy triển khai theo giai đoạn, đo cả đường đọc nóng, đường đọc chi tiết và workload ghi để xác nhận lợi ích thực tế.
