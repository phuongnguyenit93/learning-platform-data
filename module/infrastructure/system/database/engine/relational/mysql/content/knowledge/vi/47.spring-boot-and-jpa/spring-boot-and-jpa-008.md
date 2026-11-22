# IDENTITY, AUTO_INCREMENT, UUID và chiến lược sinh khóa

Trong Spring Boot và JPA, cách sinh khóa chính ảnh hưởng tới schema MySQL, thời điểm Hibernate phải gửi câu `INSERT`, khả năng gom nhiều lệnh ghi thành batch và hiệu năng index của InnoDB. `GenerationType.IDENTITY` thường kết hợp với `AUTO_INCREMENT` của MySQL; `GenerationType.UUID` tạo định danh UUID ở phía ứng dụng/provider; còn `AUTO` để JPA provider tự chọn chiến lược theo dialect và cấu hình.

Không có một chiến lược phù hợp cho mọi bảng. Khóa số tăng dần nhỏ gọn, dễ join và thường có locality tốt trên InnoDB. UUID thuận tiện khi nhiều dịch vụ hoặc node cần tạo ID độc lập trước khi ghi database, nhưng khóa ngẫu nhiên có thể làm index lớn và phân mảnh hơn. Quyết định cần dựa vào cách tạo dữ liệu, số lượng writer, nhu cầu batch insert, cách công bố ID ra API và kế hoạch mở rộng.

## 1. Khóa chính làm gì trong InnoDB?

Trong InnoDB, primary key là clustered index: dữ liệu hàng được tổ chức theo khóa chính. Mỗi secondary index cũng lưu giá trị primary key để tìm tới hàng tương ứng. Do đó, kích thước và thứ tự của khóa chính ảnh hưởng không chỉ primary index mà cả các secondary index.

Ví dụ bảng đơn hàng:

```sql
CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  order_status VARCHAR(24) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
```

Một primary key tốt thường có các đặc điểm:

- Không NULL và duy nhất.
- Ổn định trong suốt vòng đời bản ghi; không thay đổi theo thuộc tính nghiệp vụ có thể chỉnh sửa.
- Nhỏ gọn để giảm kích thước clustered index và secondary index.
- Có thể được dùng nhất quán trong foreign key ở các bảng liên quan.
- Có cách sinh phù hợp với số writer và topology triển khai.

Khóa chính không nhất thiết phải là dữ liệu có ý nghĩa với người dùng. Có thể dùng một surrogate key nội bộ và lưu business key như `order_number`, `email` hoặc mã đối tác trong unique index riêng. Cách này giúp thay đổi quy tắc nghiệp vụ mà không phải thay khóa liên kết của toàn bộ hệ thống.

## 2. IDENTITY trong JPA và AUTO_INCREMENT trong MySQL

`GenerationType.IDENTITY` yêu cầu database sinh giá trị định danh khi insert. Với MySQL, Hibernate thường ánh xạ chiến lược này sang cột `AUTO_INCREMENT`.

Entity đơn giản:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Các thuộc tính khác
}
```

DDL tương ứng:

```sql
CREATE TABLE orders (
  id BIGINT NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Khi insert, MySQL cấp giá trị ID và JDBC/Hibernate lấy lại generated key. Với `IDENTITY`, Hibernate thường phải thực thi insert sớm để biết ID được database cấp. Điều này làm hạn chế JDBC insert batching cho entity dùng IDENTITY; khi import số lượng lớn, nhiều insert có thể không được gom batch như mong muốn.

`IDENTITY` phù hợp khi:

- Ứng dụng có một nguồn ghi chính cho bảng.
- Muốn dùng cơ chế sinh khóa đơn giản, tích hợp trực tiếp với MySQL.
- Tốc độ insert và batching không phải nút thắt chính.
- Các bảng có quan hệ foreign key cần ID sau khi insert.

Không dùng `GenerationType.IDENTITY` với ý nghĩ nó bảo đảm ID liên tục, không có khoảng trống hoặc phản ánh chính xác thứ tự commit. Nó chỉ cung cấp giá trị định danh do MySQL cấp.

## 3. AUTO_INCREMENT không phải bộ đếm liên tục

MySQL cấp giá trị `AUTO_INCREMENT` cho các lần insert. Khoảng trống trong dãy ID là bình thường:

- Transaction cấp ID rồi rollback; số đã cấp có thể không được tái sử dụng.
- Insert thất bại hoặc bị bỏ qua có thể làm bộ đếm tăng.
- Xóa hàng không làm MySQL tự lấp lại số đã mất.
- Nhiều transaction đồng thời có thể nhận ID theo thứ tự cấp phát khác thứ tự commit.
- Restart, phục hồi backup hoặc thay đổi cấu hình có thể làm giá trị tiếp theo khác với suy đoán từ ID lớn nhất đang nhìn thấy.

Vì vậy, không dùng `AUTO_INCREMENT` để biểu diễn số hóa đơn liên tục theo yêu cầu pháp lý hoặc số thứ tự không được phép có khoảng trống. Nếu nghiệp vụ cần số chứng từ liên tục, phải thiết kế một cơ chế cấp số riêng với khóa/transaction, kiểm soát đồng thời, xử lý hủy và audit theo quy định áp dụng.

Không tự sinh ID bằng cách đọc `MAX(id) + 1`:

```sql
-- Không an toàn khi có nhiều transaction đồng thời
SELECT MAX(id) + 1 FROM orders;
```

Hai transaction có thể đọc cùng một giá trị rồi cùng thử insert, gây duplicate key hoặc phải retry. Dùng `AUTO_INCREMENT`, UUID hoặc bộ cấp ID có cơ chế đồng bộ rõ ràng.

Khi cần lấy ID vừa insert, dùng JDBC generated keys hoặc `LAST_INSERT_ID()` trên chính connection đã insert. Không lấy `MAX(id)` sau insert vì một transaction khác có thể đã chèn hàng mới hơn.

## 4. AUTO_INCREMENT trong hệ thống nhiều writer

Một MySQL primary đơn thường là trường hợp dễ nhất: tất cả insert vào cùng một nguồn cấp ID. Trong topology nhiều writer, đặc biệt multi-source hoặc multi-primary, mỗi node có thể cần dải giá trị khác nhau để tránh trùng khóa.

MySQL có các biến:

```sql
SHOW VARIABLES LIKE 'auto_increment_increment';
SHOW VARIABLES LIKE 'auto_increment_offset';
```

`auto_increment_increment` quy định bước tăng và `auto_increment_offset` xác định điểm bắt đầu trong chu kỳ. Chúng có thể được dùng trong một số kiến trúc nhiều nguồn để phân chia dãy ID. Việc cấu hình phải được tính cho số writer tối đa và duy trì nhất quán khi topology thay đổi.

Với Group Replication multi-primary, MySQL có cơ chế điều chỉnh increment/offset theo membership và cấu hình group. Không tự ghi đè các giá trị do Group Replication quản lý nếu chưa theo đúng hướng dẫn của phiên bản. Với kiến trúc có nhiều writer độc lập hoặc cần tạo ID trước khi biết node ghi, UUID hoặc bộ cấp ID phân tán có thể đơn giản hơn.

## 5. GenerationType.AUTO có ý nghĩa gì?

`GenerationType.AUTO` giao việc chọn chiến lược cho JPA provider. Kết quả phụ thuộc provider, phiên bản Hibernate, database dialect và cấu hình generator. Không nên giả định `AUTO` luôn đồng nghĩa với `IDENTITY` chỉ vì database là MySQL.

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

Hibernate có thể chọn một generator dựa trên khả năng của dialect; với database không có native sequence như MySQL, cách triển khai có thể khác so với PostgreSQL hoặc Oracle. Một số cấu hình/provider có thể dùng identity, table-backed generator hoặc cơ chế khác. Hãy kiểm tra DDL được tạo, SQL insert thực tế và log Hibernate khi nâng phiên bản provider.

`AUTO` thuận tiện khi muốn provider quản lý chi tiết, nhưng làm cho hành vi phụ thuộc vào implementation. Nếu hiệu năng batching, khả năng chuyển database hoặc cách sinh ID là yêu cầu quan trọng, khai báo chiến lược cụ thể và kiểm thử trên đúng phiên bản là rõ ràng hơn.

## 6. SEQUENCE và TABLE generator trong MySQL

JPA định nghĩa `GenerationType.SEQUENCE`, nhưng MySQL không có đối tượng sequence native như PostgreSQL hoặc Oracle. Provider có thể từ chối hoặc dùng cơ chế mô phỏng tùy dialect/version. Không viết cú pháp `CREATE SEQUENCE` theo database khác rồi kỳ vọng MySQL hiểu được.

`GenerationType.TABLE` dùng một bảng để lưu bộ đếm ID. Ví dụ JPA:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @TableGenerator(
        name = "orders_id_generator",
        table = "id_generator",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "orders",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "orders_id_generator"
    )
    private Long id;
}
```

Bảng generator có thể có cấu trúc tương tự:

```sql
CREATE TABLE id_generator (
  generator_name VARCHAR(64) NOT NULL,
  next_value BIGINT NOT NULL,
  PRIMARY KEY (generator_name)
) ENGINE=InnoDB;
```

Provider quản lý việc khóa và cập nhật giá trị trong bảng generator. `allocationSize` cho phép cấp trước một khoảng ID để giảm số lần truy cập bảng generator, tùy cách provider triển khai. Tuy nhiên, generator table có thể trở thành điểm tranh chấp khi nhiều transaction cùng xin ID; cần kiểm thử throughput và cấu hình đồng bộ.

Đừng tự cập nhật bảng generator bằng SQL khi Hibernate đang sử dụng nó. Nếu giá trị trong bảng bị đặt thấp hơn ID đã cấp, có thể phát sinh duplicate key. Khi cần thay đổi allocation size hoặc reset generator, phải thực hiện theo quy trình provider và kiểm tra các khoảng ID đã được cấp trước đó.

## 7. UUID và GenerationType.UUID

UUID là định danh 128 bit, có thể được tạo ở ứng dụng mà không cần hỏi MySQL trước khi insert. Điều này hữu ích khi:

- Nhiều dịch vụ hoặc node tạo bản ghi độc lập.
- Muốn tạo ID trước khi ghi database hoặc trước khi gửi sự kiện.
- Cần đồng bộ dữ liệu từ nhiều nguồn mà không dùng chung một bộ đếm.
- Không muốn lộ trực tiếp số thứ tự tăng dần của bản ghi qua API.

Jakarta Persistence 3.1 bổ sung `GenerationType.UUID`. Hibernate cũng có cơ chế UUID generator ở các phiên bản tương ứng. Ví dụ dùng thuộc tính Java `UUID`:

```java
@Entity
@Table(name = "external_events")
public class ExternalEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    // Các thuộc tính khác
}
```

Kiểu cột vật lý phụ thuộc provider và cấu hình mapping. Với MySQL, có thể lưu UUID dưới dạng `CHAR(36)` hoặc `BINARY(16)`. Kiểm tra DDL thực tế và round trip trước khi triển khai; đừng cho rằng annotation JPA tự bảo đảm một biểu diễn byte cụ thể.

Với `String` ID và UUID dạng ký tự, có thể khai báo cột rõ ràng:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
@Column(name = "id", length = 36, nullable = false, updatable = false)
private String id;
```

DDL minh họa:

```sql
CREATE TABLE external_events (
  id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`CHAR(36)` dễ đọc và tương thích với nhiều công cụ, nhưng lớn hơn khóa số và tốn không gian hơn `BINARY(16)`. Định dạng ký tự nên dùng charset ASCII và collation nhất quán để tránh các quy tắc so sánh ngôn ngữ không cần thiết.

## 8. CHAR(36) hay BINARY(16)?

UUID có 16 byte dữ liệu. Dạng chuỗi chuẩn thường dài 36 ký tự vì có dấu gạch nối. Lưu `BINARY(16)` giúp giảm kích thước khóa và các secondary index so với `CHAR(36)`.

| Tiêu chí | `CHAR(36)` | `BINARY(16)` |
|---|---|---|
| Dung lượng giá trị | 36 ký tự | 16 byte |
| Dễ đọc/debug | Dễ đọc trực tiếp | Cần chuyển đổi khi hiển thị |
| So sánh/index | Tốn không gian hơn | Nhỏ gọn hơn |
| Mapping ứng dụng | Dễ dùng `String`; UUID mapping phụ thuộc provider | Cần mapping UUID/byte nhất quán |
| Tích hợp hệ thống khác | Thường đơn giản | Cần thống nhất byte order và quy tắc encode/decode |

MySQL có hàm chuyển đổi:

```sql
SELECT UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db');
SELECT BIN_TO_UUID(UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db'));
```

Nếu dùng `UUID_TO_BIN(uuid, 1)` để hoán đổi các trường thời gian của UUID version 1 nhằm cải thiện locality, khi đọc phải dùng `BIN_TO_UUID(value, 1)` tương ứng. Cờ `swap_flag=1` được thiết kế cho bố cục UUID v1; không áp dụng máy móc cho UUID v4 hoặc UUID v7.

Ví dụ với UUID v1 do MySQL tạo:

```sql
INSERT INTO event_keys (id, description)
VALUES (UUID_TO_BIN(UUID(), 1), 'source event');
```

`UUID()` của MySQL tạo UUID version 1. Nếu UUID được tạo ở Java bằng một generator khác, hãy xác định version và byte layout rồi lưu theo cùng một quy ước; không vừa hoán đổi trong SQL vừa hoán đổi thêm ở ứng dụng.

## 9. UUID v4, v7 và locality của index

Không phải mọi UUID đều có cùng đặc tính sắp xếp:

- **UUID v4:** phần lớn bit được tạo ngẫu nhiên. Khó đoán và dễ tạo độc lập, nhưng thứ tự insert phân tán trên B-tree.
- **UUID v1:** có thành phần thời gian và thông tin node; MySQL có thể hoán đổi các trường thời gian với `UUID_TO_BIN(..., 1)` để cải thiện thứ tự lưu. UUID v1 có thể để lộ thông tin về thời gian và node.
- **UUID v7:** bố trí timestamp Unix ở phần đầu và phần ngẫu nhiên ở phần sau, thường có thứ tự gần thời gian tạo. Cần generator hỗ trợ UUIDv7; không giả định mọi JDK/JPA provider đều tạo v7 mặc định.

UUID v4 có thể làm insert vào clustered index phân tán hơn, gây page split và giảm locality khi bảng lớn. UUID v7 hoặc dạng UUID có thứ tự thời gian có thể cải thiện locality, nhưng không làm các ID trở thành số thứ tự commit tuyệt đối; nhiều node có clock lệch hoặc cùng timestamp vẫn có thể tạo thứ tự khác.

UUID v7 có thể tiết lộ thời điểm tạo gần đúng. Nếu ID công khai và thời gian tạo là thông tin nhạy cảm, đánh giá tác động này. UUID nói chung cũng không thay thế kiểm tra quyền truy cập; một endpoint vẫn phải xác minh người dùng được phép xem hoặc sửa bản ghi.

Đo trên workload thật: tốc độ insert, page split, kích thước index, buffer pool hit rate và hiệu năng join. Không quyết định chỉ dựa trên benchmark tạo UUID trong bộ nhớ.

## 10. Chi phí khóa chính lan sang foreign key và secondary index

InnoDB lưu primary key trong mỗi secondary index để định vị hàng. Nếu bảng có nhiều secondary index, thay primary key từ `BIGINT` 8 byte sang `CHAR(36)` làm tăng dung lượng của tất cả các index đó và các bảng con lưu foreign key tương ứng.

Ví dụ một bảng `order_items` có ba secondary index và foreign key tới `orders.id`. Nếu primary key của `orders` là UUID chuỗi, `order_items` phải lưu khóa lớn hơn cho mỗi dòng. Khi dữ liệu lên hàng trăm triệu dòng, phần chênh lệch có thể ảnh hưởng đáng kể đến disk, buffer pool và I/O.

Với UUID, cân nhắc:

- Dùng `BINARY(16)` nếu hệ sinh thái ứng dụng có mapping ổn định.
- Giữ cùng kiểu, signedness và độ dài ở cột foreign key.
- Đánh giá kích thước toàn bộ index, không chỉ primary key.
- Tránh chuyển sang UUID chỉ để ID khó đoán nếu có thể dùng public ID riêng.
- Kiểm tra hiệu năng join và replication sau khi thay đổi kiểu khóa.

## 11. Tạo UUID ở Java hay MySQL?

Có thể tạo UUID ở ứng dụng hoặc database. Điều quan trọng là chỉ có một nguồn sinh ID cho mỗi entity và mọi thành phần thống nhất định dạng.

Tạo trong Java trước khi insert:

```java
UUID id = UUID.randomUUID();
```

`UUID.randomUUID()` của Java tạo UUID version 4. Cách này cho phép ứng dụng biết ID trước khi gọi `persist`, tạo message/event có ID nhất quán và không phải chờ generated key từ database.

Với JPA, có thể dùng `GenerationType.UUID` để provider sinh UUID:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
```

Hoặc tự gán ID và bỏ `@GeneratedValue`:

```java
@Id
@Column(nullable = false, updatable = false)
private UUID id;

public ExternalEvent() {
    this.id = UUID.randomUUID();
}
```

Hai ví dụ là hai cách quản lý khác nhau. Nếu ứng dụng tự gán ID, không đồng thời yêu cầu provider sinh ID cho cùng thuộc tính. Nếu dùng generator tùy chỉnh cho UUIDv7, cấu hình generator đó rõ ràng và kiểm thử tính duy nhất, thứ tự cùng khả năng tương thích.

Sinh UUID ở MySQL bằng `UUID()` cũng có thể dùng trong SQL thuần hoặc ETL. Tuy nhiên, nếu Hibernate quản lý entity, không nên để database tự sinh mà mapping JPA lại giả định provider đã có ID trước insert, trừ khi đã cấu hình generated column/key retrieval tương ứng.

## 12. Batching và throughput khi chọn generator

Một khác biệt thực tế giữa IDENTITY và UUID là thời điểm biết ID:

| Chiến lược | Thời điểm có ID | Ảnh hưởng insert batching |
|---|---|---|
| `IDENTITY` | Sau khi MySQL thực thi insert | Hibernate thường không gom insert của entity IDENTITY thành JDBC batch vì phải lấy generated key |
| UUID do ứng dụng/provider tạo | Trước insert | Có thể gom insert theo batch nếu các điều kiện Hibernate/JDBC khác cho phép |
| TABLE generator | Sau khi lấy/cấp khoảng từ generator table | Có thể preallocate ID theo `allocationSize`; có chi phí đồng bộ generator |
| ID tự gán từ dịch vụ/segment | Trước insert | Có thể batch; cần bảo đảm thuật toán cấp ID không trùng và vận hành được |

UUID không tự động làm ứng dụng nhanh hơn. Nếu UUID là ngẫu nhiên, chi phí index và storage có thể lớn hơn. Lợi ích về batching có thể bị triệt tiêu nếu bảng có nhiều index, transaction quá lớn hoặc disk là nút thắt.

Với Hibernate, kiểm tra cấu hình batch và SQL thực tế. Ví dụ:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Các thuộc tính này chỉ là cấu hình gợi ý; hiệu quả phụ thuộc generator, dialect, driver, transaction và entity mapping. `IDENTITY` vẫn có giới hạn batching riêng, nên không thể chỉ đặt `hibernate.jdbc.batch_size` rồi kỳ vọng insert identity được gom batch.

## 13. Chọn chiến lược theo bài toán

| Bối cảnh | Lựa chọn có thể phù hợp | Lý do và điều kiện |
|---|---|---|
| CRUD với một MySQL primary, bảng giao dịch thông thường | `IDENTITY` + `BIGINT AUTO_INCREMENT` | Đơn giản, khóa nhỏ, locality tốt; chấp nhận hạn chế batching |
| Import số lượng lớn cần batch insert | UUID sinh trước hoặc ID được cấp trước theo block | Biết ID trước khi insert; cần đánh giá chi phí index và generator |
| Nhiều service/node tạo bản ghi offline | UUID hoặc distributed ID | Không cần hỏi chung một bộ đếm tại thời điểm tạo |
| ID cần gọn, có thứ tự gần thời gian | BIGINT từ một nguồn cấp hoặc UUIDv7 | Cân nhắc clock, nhiều writer và mức độ lộ timestamp |
| Bảng cần khóa công khai khó đoán | Public UUID riêng, primary key nội bộ có thể vẫn là BIGINT | Tách định danh API khỏi khóa liên kết nội bộ |
| Muốn portability qua nhiều database | `AUTO` hoặc generator được JPA/provider hỗ trợ | Phải kiểm tra generator được chọn và DDL ở từng dialect |

Một thiết kế thường hiệu quả là giữ `BIGINT AUTO_INCREMENT` làm primary key nội bộ để join/index nhỏ gọn, đồng thời thêm `public_id BINARY(16)` hoặc `CHAR(36)` với unique index cho ID công khai. Cách này tăng thêm một index và cột, nhưng tránh lan khóa UUID lớn qua mọi foreign key. Đánh giá chi phí này theo workload và yêu cầu API.

## 14. Migration từ AUTO_INCREMENT sang UUID

Chuyển khóa chính của một hệ thống đang chạy là migration lớn vì primary key xuất hiện trong secondary index, foreign key, cache, message, URL và code ứng dụng. Không nên đổi kiểu cột trực tiếp trên toàn bộ bảng trong một lần nếu dữ liệu lớn.

Một quy trình expand-and-contract có thể là:

1. Thêm cột UUID mới nullable vào bảng cha và các bảng con cần tham chiếu.
2. Triển khai code tương thích với cả khóa số và UUID; xác định một nguồn sinh UUID duy nhất.
3. Backfill UUID theo chunk, lưu checkpoint và tạo unique index sau khi kiểm tra không trùng.
4. Đồng bộ UUID cho bản ghi mới trong giai đoạn chuyển tiếp, bằng code hoặc cơ chế database đã được kiểm thử.
5. Backfill khóa UUID tương ứng ở bảng con; xác minh mọi quan hệ và orphan.
6. Chuyển đọc/ghi theo từng service và theo dõi lỗi join, lookup, message và API.
7. Chỉ sau khi mọi consumer đã chuyển mới cân nhắc đổi foreign key/primary key và bỏ đường tương thích cũ.

Kiểm tra dữ liệu:

```sql
SELECT COUNT(*) AS missing_public_id
FROM orders
WHERE public_id IS NULL;

SELECT public_id, COUNT(*) AS occurrences
FROM orders
WHERE public_id IS NOT NULL
GROUP BY public_id
HAVING COUNT(*) > 1;
```

Trước khi thay foreign key, so sánh số lượng bản ghi cha/con, phát hiện orphan và xác nhận mọi ID cũ ánh xạ đúng một ID mới. DDL tạo index hoặc thay primary key có thể rebuild bảng và tăng replication lag; lập kế hoạch dung lượng, khóa và bảo trì riêng.

## 15. Kiểm thử và quan sát sau triển khai

Kiểm thử generator cần xác nhận cả correctness lẫn hiệu năng:

- Tạo nhiều entity đồng thời từ nhiều thread và nhiều instance; xác nhận không trùng ID.
- Kiểm tra ID đã được gán vào entity trước hay sau `persist`/`flush` theo chiến lược.
- Kiểm tra `getGeneratedKeys` hoặc JPA entity ID sau insert với đúng driver.
- Đo số câu SQL, số round trip và batch size thực tế.
- Đo tốc độ insert, kích thước primary/secondary index, page split và buffer pool.
- Kiểm tra foreign key và join khi dùng UUID.
- Với multi-writer, thử failover hoặc node restart và xác nhận không cấp trùng ID.
- Với UUID có thứ tự thời gian, thử clock skew và các node tạo ID cùng thời điểm.

Trong Hibernate, bật SQL logging ở staging hoặc dùng datasource proxy/APM để quan sát câu insert. Tránh bật log bind parameter có dữ liệu nhạy cảm trong production. Dùng Performance Schema và `information_schema.tables` để theo dõi dung lượng bảng/index, đồng thời đo latency insert và transaction ở tầng ứng dụng.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hibernate không lấy được ID sau insert | Mapping generator không phù hợp DDL hoặc driver không trả generated key như mong đợi | Kiểm tra annotation, DDL, dialect và Connector/J; thử insert/flush trên staging |
| Insert hàng loạt chậm dù đã bật batch | Entity dùng `IDENTITY`, flush quá thường xuyên hoặc batch bị chia nhỏ | Quan sát SQL thực tế; cân nhắc UUID sinh trước hoặc generator cấp trước nếu phù hợp |
| `AUTO` tạo generator table ngoài dự kiến | Provider/dialect chọn chiến lược khác mong đợi | Kiểm tra DDL và Hibernate log; khai báo strategy rõ ràng nếu cần |
| Duplicate key trong hệ thống nhiều writer | Các node dùng chung dải AUTO_INCREMENT hoặc thuật toán ID tự sinh bị trùng | Xác định topology; phân dải ID đúng cách hoặc dùng UUID/distributed ID |
| UUID insert chậm và index lớn | UUID ngẫu nhiên, `CHAR(36)` và nhiều secondary index | Đo thử `BINARY(16)` hoặc UUID có locality; đánh giá public ID riêng |
| UUID không đọc được sau khi lưu binary | Byte order hoặc quy tắc swap không thống nhất | Chuẩn hóa encode/decode; chỉ dùng cùng swap flag cho cả `UUID_TO_BIN` và `BIN_TO_UUID` |
| Foreign key không tạo được | Kiểu, signedness hoặc độ dài cột cha/con không tương thích | Đồng bộ định nghĩa cột và kiểm tra index/engine |
| ID bị hở số | Rollback, delete hoặc insert lỗi | Chấp nhận gap nếu dùng AUTO_INCREMENT; thiết kế bộ cấp số riêng nếu nghiệp vụ yêu cầu |

## 17. Tình huống thực hành

Một ứng dụng Spring Boot bán hàng hiện dùng `Long` với `GenerationType.IDENTITY`. Hệ thống bắt đầu import hàng trăm nghìn sự kiện từ nhiều nguồn, và nhóm phát triển muốn tạo ID trước khi insert để gom batch và gửi message cùng transaction.

**Bước 1 — Đo baseline.** Ghi nhận tốc độ insert hiện tại, số câu SQL, thời gian flush, kích thước index và replication lag. Xác nhận `IDENTITY` đang ngăn Hibernate batch insert cho entity cần import.

**Bước 2 — Chọn phạm vi.** Không đổi toàn bộ khóa chính của `orders` ngay. Thử với bảng `external_events` độc lập, nơi UUID là định danh tự nhiên của sự kiện đến từ nhiều nguồn.

**Bước 3 — Chọn biểu diễn.** Dùng `UUID` sinh ở ứng dụng/provider. So sánh `CHAR(36)` dễ quan sát với `BINARY(16)` nhỏ gọn; xác nhận Hibernate mapping và byte order.

**Bước 4 — Cấu hình batch.** Bật batch size phù hợp và `order_inserts`, sau đó kiểm tra log SQL để xác nhận JDBC batch thực sự được sử dụng. Đo lại với lượng dữ liệu và index tương đương.

**Bước 5 — Kiểm tra nhiều instance.** Chạy nhiều worker cùng tạo event, xác nhận không trùng ID, retry message không tạo bản ghi trùng và unique constraint bảo vệ dữ liệu.

**Bước 6 — Đối soát hiệu năng.** So sánh throughput, p95 insert latency, dung lượng index, page split và replication lag. Chỉ mở rộng khi lợi ích batch lớn hơn chi phí UUID và kết quả ổn định.

## 18. Checklist trước khi chọn generator

- [ ] Đã xác định số lượng writer, topology và nơi tạo ID.
- [ ] Đã phân biệt primary key nội bộ với public/business identifier.
- [ ] Đã chọn `IDENTITY`, `UUID`, `TABLE`, `AUTO` hoặc ID tự gán theo yêu cầu rõ ràng.
- [ ] Đã kiểm tra hành vi thực tế của `GenerationType.AUTO` với Hibernate version và MySQL dialect.
- [ ] Đã tính tới việc IDENTITY hạn chế Hibernate JDBC insert batching.
- [ ] Đã xác định ID có cần được biết trước khi insert hay không.
- [ ] Nếu dùng UUID, đã chọn version, biểu diễn `CHAR(36)`/`BINARY(16)` và byte order nhất quán.
- [ ] Nếu dùng `UUID_TO_BIN(..., 1)`, chỉ áp dụng cho bố cục UUID v1 và dùng cùng cờ khi giải mã.
- [ ] Đã đồng bộ kiểu và signedness giữa primary key và foreign key.
- [ ] Đã kiểm thử sinh ID đồng thời trên nhiều thread/node và xử lý retry.
- [ ] Đã đo batching, insert throughput, index size và replication lag.
- [ ] Có kế hoạch migration/backfill nếu thay đổi chiến lược trên bảng đang chạy.

`IDENTITY` và `AUTO_INCREMENT` là lựa chọn đơn giản, nhỏ gọn cho nhiều ứng dụng Spring Boot dùng MySQL primary đơn. UUID phù hợp khi cần tạo định danh độc lập ở nhiều node hoặc trước khi ghi database, nhưng cần tính tới kích thước và locality của index. `AUTO` phụ thuộc JPA provider và dialect; TABLE generator có chi phí đồng bộ riêng. Chọn generator theo luồng ghi, topology, batching và cách khóa được dùng trong toàn bộ quan hệ dữ liệu sẽ giúp hệ thống duy trì tính duy nhất mà không tạo chi phí lưu trữ hoặc vận hành ngoài dự kiến.
