# Kiểm tra hỗ trợ chiến lược sinh khóa theo hệ quản trị và JPA provider

## 1. Vấn đề cần giải quyết

Trong ứng dụng sử dụng **Jakarta Persistence (JPA)**, nhiều entity có khóa chính được tạo tự động. Lập trình viên có thể viết **@GeneratedValue** trên trường **@Id**, nhưng việc sinh giá trị ID thành công phụ thuộc vào nhiều yếu tố: phiên bản JPA, nhà cung cấp ORM (*provider*), SQL dialect, khả năng của hệ quản trị cơ sở dữ liệu (*DBMS*), cấu trúc bảng và sequence, quyền của tài khoản kết nối, cùng cấu hình triển khai.

Ví dụ, cùng một entity được cấu hình **GenerationType.SEQUENCE** có thể hoạt động trực tiếp với sequence trên PostgreSQL, nhưng có thể thất bại hoặc cần cơ chế mô phỏng trên một hệ quản trị không có sequence độc lập. Ngược lại, **GenerationType.IDENTITY** có thể phù hợp với MySQL nhưng ảnh hưởng đến cách Hibernate gom lệnh INSERT thành batch. Dùng **GenerationType.AUTO** có thể chạy ở cả hai nơi nhưng chọn cơ chế sinh khác nhau.

Do đó, yêu cầu “kiểm tra hỗ trợ chiến lược sinh” không chỉ là xem DB có từ khóa SQL tương ứng. Cần xác nhận cả chuỗi thực thi:

~~~text
Java entity + @GeneratedValue
           |
           v
Phiên bản Jakarta Persistence
           |
           v
JPA provider và phiên bản (Hibernate, EclipseLink, ...)
           |
           v
Dialect / cơ chế generator mà provider lựa chọn
           |
           v
JDBC driver + quyền của tài khoản ứng dụng
           |
           v
DBMS + phiên bản + DDL/schema thực tế
           |
           v
INSERT thành công, ID duy nhất, đọc lại được và ổn định khi chạy đồng thời
~~~

**Mục tiêu của bài:** biết các chiến lược chuẩn của JPA, hiểu khả năng của DBMS và provider khác nhau, xây dựng một quy trình kiểm chứng trên môi trường thật, rồi chọn cấu hình phù hợp cho ứng dụng.

## 2. @Id và @GeneratedValue: hai trách nhiệm khác nhau

**@Id** xác định thuộc tính làm định danh entity. **@GeneratedValue** yêu cầu cơ chế sinh định danh cho entity đó:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {}

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

Một số điểm nền tảng:

- **@Id không đồng nghĩa với tự sinh khóa.** Entity chỉ có @Id thường cần ứng dụng gán ID theo cơ chế đã thiết kế.
- **@GeneratedValue không tạo ràng buộc PRIMARY KEY trong một database hiện hữu.** Ràng buộc và cột thực tế vẫn phải được khai báo trong schema; việc sinh DDL tự động, nếu có, là công việc riêng của provider/schema generation.
- **Khóa tự sinh không bảo đảm giá trị liên tiếp không có khoảng trống.** Rollback, lỗi INSERT, cấp ID theo lô và nhiều node ứng dụng đều có thể tạo khoảng cách giữa các ID.
- **ID là định danh kỹ thuật, không mặc nhiên là số thứ tự nghiệp vụ.** Nếu hóa đơn cần số liên tục theo quy định riêng, cần thiết kế đánh số nghiệp vụ ngoài giả định rằng ID tăng không có lỗ hổng.
- **Không dùng giá trị khóa vừa khởi tạo để suy luận entity đã commit.** Provider có thể cấp ID trước khi INSERT; transaction vẫn có thể rollback.

JPA định nghĩa **GenerationType**, nhưng provider đảm nhiệm cách dịch chiến lược thành SQL và các đối tượng schema. Vì vậy, “hỗ trợ theo chuẩn API” và “chạy trên tổ hợp provider + DB” phải được kiểm tra riêng.

## 3. Các chiến lược sinh khóa cần nhận diện

| Strategy | Ý tưởng | Điểm phụ thuộc chính |
|---|---|---|
| **AUTO** | Provider tự chọn cơ chế sinh phù hợp với cấu hình | Provider, dialect, phiên bản, kiểu ID |
| **IDENTITY** | DB cấp ID khi INSERT vào cột có khả năng tự sinh | Hỗ trợ identity/auto-increment, quyền INSERT, cách lấy generated key |
| **SEQUENCE** | Provider nhận giá trị từ sequence trước hoặc trong quá trình ghi | Native sequence hoặc khả năng mô phỏng của provider; cấu hình generator |
| **TABLE** | Dùng một bảng riêng lưu trạng thái cấp ID | Transaction/locking và hiệu năng của bảng cấp ID |
| **UUID** | Sinh định danh dạng UUID theo chiến lược JPA hiện đại | Phiên bản JPA/provider, kiểu Java, JDBC và kiểu cột lưu UUID |

Trong các phiên bản JPA trước khi **Jakarta Persistence 3.1**, enum chuẩn chưa có **GenerationType.UUID**. Với dự án JPA 2.x dùng namespace **javax.persistence** hoặc dự án Jakarta Persistence cũ hơn, cần xác định tính năng UUID cụ thể của provider thay vì sao chép annotation từ dự án mới.

### 3.1. AUTO

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

Đây là cách yêu cầu provider chọn chiến lược. Khai báo **@GeneratedValue** mà bỏ strategy cũng có ý nghĩa chọn AUTO theo mặc định. AUTO giúp ứng dụng ít gắn chặt với một hệ quản trị, nhưng **không cam kết cùng một SQL hoặc cùng một cách cấp ID** giữa các provider/DBMS hay sau khi nâng cấp phiên bản. Khi chuyển database, cần kiểm tra provider đã chọn sequence, table hoặc cơ chế khác và đối tượng schema cần thiết có tồn tại.

### 3.2. IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

IDENTITY dựa vào cột được DB cấp giá trị khi INSERT. Tên tính năng khác nhau giữa các hệ quản trị: **GENERATED ... AS IDENTITY**, **AUTO_INCREMENT**, **IDENTITY** hoặc cơ chế tương đương. Provider thường cần thực hiện INSERT để lấy khóa DB tạo, vì vậy thời điểm SQL và khả năng JDBC batching có thể khác SEQUENCE.

### 3.3. SEQUENCE

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_id_generator"
)
@SequenceGenerator(
    name = "product_id_generator",
    sequenceName = "product_id_seq",
    allocationSize = 1
)
private Long id;
~~~

SEQUENCE tham chiếu đối tượng cấp số trong DB hoặc cơ chế được provider hỗ trợ. **name** của @SequenceGenerator là tên generator trong metadata JPA; **sequenceName** là tên đối tượng sequence trong DB. Hai giá trị không bắt buộc giống nhau. Nếu DB không hỗ trợ native sequence, provider có thể không hỗ trợ chiến lược này hoặc dùng cơ chế mô phỏng; không được mặc định rằng SQL sẽ gọi **NEXTVAL**.

### 3.4. TABLE

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.TABLE,
    generator = "invoice_id_generator"
)
@TableGenerator(
    name = "invoice_id_generator",
    table = "id_allocation",
    pkColumnName = "generator_name",
    valueColumnName = "generator_value",
    pkColumnValue = "invoice",
    allocationSize = 1
)
private Long id;
~~~

TABLE giữ thông tin cấp khóa trong **một bảng thông thường** và dùng cơ chế đồng bộ phù hợp để tránh hai transaction cấp trùng ID. Phương án này có thể dùng trên nhiều DB quan hệ, nhưng tạo thêm truy cập vào bảng cấp ID, phát sinh tranh chấp khi có nhiều transaction, và vẫn phải kiểm tra provider hỗ trợ cú pháp khóa hoặc cập nhật nguyên tử tương ứng.

### 3.5. UUID

~~~java
import java.util.UUID;

@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

UUID là lựa chọn hữu ích khi cần sinh định danh mà không phụ thuộc vào một sequence cấp số tập trung. Trong Jakarta Persistence 3.1 trở lên, chiến lược UUID là một phần của API chuẩn; kiểu khóa **UUID** hoặc **String** có thể được provider hỗ trợ theo quy tắc đặc tả. Tuy nhiên, **cách UUID được lưu trong SQL** có thể là kiểu UUID bản địa, kiểu ký tự hoặc kiểu nhị phân tùy database và provider. Vì vậy, hai việc “sinh UUID” và “đọc/ghi cột UUID đúng kiểu” phải được kiểm tra tách biệt.

## 4. “DB hỗ trợ” cần được hiểu ở nhiều mức

Nhiều lỗi triển khai bắt nguồn từ việc đánh đồng một khả năng SQL với hỗ trợ đầy đủ của JPA.

**Mức 1 — Khả năng nguyên thủy của DBMS.** DB có native sequence không? Có identity column hoặc auto-increment không? Có kiểu UUID không? DDL tạo đối tượng là gì?

**Mức 2 — Khả năng của provider/dialect.** Hibernate hoặc EclipseLink có nhận diện chính xác DB/phiên bản không? Dialect có biết cách tạo, đọc sequence hoặc lấy generated key không? Có trình cấp khóa dựa trên bảng hay mô phỏng sequence không?

**Mức 3 — Cấu hình và quyền runtime.** DataSource có trỏ đúng schema không? Tài khoản chạy ứng dụng có quyền gọi sequence, truy cập bảng cấp ID, INSERT hoặc lấy khóa vừa sinh không? Có đúng JDBC driver không?

**Mức 4 — Tính tương thích schema.** Cột ID có đúng loại, identity, default, PK, sequence, giới hạn numeric và mối liên hệ với generator đã khai báo không? Có một hệ thống khác cùng cấp ID bằng cơ chế khác không?

**Mức 5 — Hành vi thực tế.** Nhiều lần persist, chạy đồng thời, rollback, khởi động lại ứng dụng, triển khai nhiều node và batch insert có sinh khóa duy nhất, đúng phạm vi, không bị lỗi trạng thái hoặc hiệu năng quá kém không?

Ví dụ, database có chức năng **CREATE SEQUENCE** chưa đủ để kết luận GenerationType.SEQUENCE hoạt động. Provider còn phải dùng đúng cú pháp lấy NEXT VALUE, mapping cần đúng tên sequence, và tài khoản phải có quyền đọc sequence đó.

## 5. Ma trận tham khảo theo hệ quản trị

Ma trận dưới đây nói về **tính năng native của DBMS** ở các dòng phiên bản tham khảo, **không phải giấy bảo đảm tương thích JPA**. Việc provider thật sự dùng cơ chế nào phải được xác nhận trên runtime.

| DBMS / phiên bản tham khảo | Identity hoặc auto-increment native | Native sequence | TABLE generator | UUID JPA |
|---|---|---|---|---|
| **PostgreSQL 12+** | Có, identity column; cũng có serial theo kiểu DDL cũ | Có | Có thể dùng bảng cấp ID | Có kiểu UUID native; kiểm tra provider |
| **MySQL 8.x** | Có, AUTO_INCREMENT | Không có sequence độc lập theo cú pháp SQL chuẩn tương tự PostgreSQL | Có thể dùng bảng cấp ID | Sinh ở Java được; kiểu lưu UUID phụ thuộc mapping |
| **MariaDB 10.3+** | Có, AUTO_INCREMENT | Có sequence ở các phiên bản hỗ trợ | Có thể dùng bảng cấp ID | Sinh ở Java được; kiểu lưu phụ thuộc phiên bản/mapping |
| **Oracle Database 12c+** | Có identity column | Có | Có thể dùng bảng cấp ID | Sinh ở Java được; kiểu lưu phụ thuộc bản DB/provider |
| **SQL Server 2012+** | Có IDENTITY | Có CREATE SEQUENCE | Có thể dùng bảng cấp ID | Có uniqueidentifier; kiểm tra mapping UUID |
| **H2 2.x** | Có identity column | Có | Có thể dùng bảng cấp ID | Kiểm tra cấu hình provider và chế độ DB |
| **SQLite** | Có cơ chế ROWID/INTEGER PRIMARY KEY, không hoàn toàn giống DDL của các DB trên | Không có sequence native tương đương | Có thể tự thiết kế bảng, nhưng cần dialect/provider phù hợp | Thường lưu dạng text/blob qua mapping thích hợp |

Đối với từng ô **“Có”**, cần phân biệt tiếp: DB có tính năng nhưng phiên bản provider đã cấu hình có khai thác được hay không. Một số ví dụ:

- **PostgreSQL** có sequence native; IDENTITY cũng thường được provider hỗ trợ với schema thích hợp. Nếu ứng dụng dùng bảng sinh khóa từ đời cũ, chuyển chiến lược phải kiểm tra dữ liệu hiện hữu.
- **MySQL** dùng AUTO_INCREMENT tự nhiên cho IDENTITY. Nếu cấu hình SEQUENCE, một số provider có thể sử dụng cơ chế mô phỏng bằng bảng, provider khác có thể từ chối hoặc yêu cầu generator khác. Không giả định MySQL tự sinh một native sequence.
- **MariaDB** có tính năng sequence ở các phiên bản tương ứng, nhưng provider cần nhận đúng dialect MariaDB và phiên bản; cấu hình nhầm MySQL dialect có thể dẫn tới lựa chọn generator khác.
- **Oracle** có sequence lâu đời và có identity từ dòng 12c. Hệ thống Oracle đời cũ có thể dùng sequence kết hợp trigger hoặc mapping riêng, không nên tự suy ra IDENTITY từ cấu hình mới.
- **SQL Server** có IDENTITY và CREATE SEQUENCE ở các phiên bản hiện đại, nhưng cú pháp đọc sequence và cách lấy generated key khác PostgreSQL/Oracle.
- **H2** rất hữu ích cho ví dụ nhanh, nhưng một bài test thành công trên H2 không chứng minh mapping đó sẽ chạy trên MySQL, PostgreSQL hoặc Oracle sản xuất.
- **SQLite** phụ thuộc mạnh vào provider, dialect và cách mapping rowid; cần xác minh riêng nếu muốn chạy JPA. Không coi nó là một hệ có native sequence chỉ vì tồn tại bảng nội bộ sqlite_sequence cho AUTOINCREMENT.

**TABLE** về nguyên lý có thể triển khai bằng bảng SQL trong rất nhiều DBMS, nhưng chữ “có thể” chưa nói đến locking, isolation, hỗ trợ generator của provider hay hiệu năng. **UUID** có thể được tạo trong JVM, song kiểu cột, JDBC binding, collation và chỉ mục vẫn phụ thuộc hệ quản trị.

## 6. Ma trận theo JPA provider và phiên bản

JPA là đặc tả API; chính provider triển khai cách cấp ID. Trong hệ sinh thái Java, hai provider phổ biến là **Hibernate ORM** và **EclipseLink**.

| Câu hỏi | Hibernate ORM | EclipseLink |
|---|---|---|
| Chọn generator khi dùng AUTO | Dựa trên metadata, kiểu ID, dialect và phiên bản Hibernate | Dựa trên metadata và cơ chế sequencing của EclipseLink |
| Dịch IDENTITY | Phụ thuộc khả năng identity của Hibernate Dialect và JDBC | Phụ thuộc platform/database adapter của EclipseLink |
| Dịch SEQUENCE | Có thể dùng sequence native hoặc cơ chế thay thế tùy generator và dialect | Có các cơ chế sequencing và platform integration riêng |
| Dịch TABLE | Có generator bảng với các đặc tính cấp phát và đồng bộ riêng | Có cơ chế cấp phát qua bảng riêng |
| UUID | Cần phiên bản có API tương ứng hoặc tính năng UUID riêng của provider | Cần phiên bản hỗ trợ API tương ứng hoặc generator của provider |
| Log để xác minh | SQL logging, category của Hibernate, statistics khi phù hợp | EclipseLink logging và cấu hình SQL/database session |
| Tên class/thuộc tính cấu hình | Có nhiều extension riêng Hibernate | Có nhiều extension riêng EclipseLink |

Không cần kết luận provider nào “hỗ trợ hết” từ tên thương hiệu. **Cùng Hibernate nhưng khác major version hoặc dialect** có thể chọn generator khác. Cùng một JDBC URL nhưng đổi từ Hibernate sang EclipseLink có thể thay đổi SQL và cơ chế cấp phát.

Đặc biệt:

- **GenerationType.UUID** yêu cầu một API Jakarta Persistence đủ mới và provider thực sự triển khai tính năng. Annotation **@UuidGenerator** của Hibernate, nếu dùng, là extension riêng, không tương đương về tính portable với mã chỉ dùng API chuẩn.
- **GenerationType.SEQUENCE** không luôn đồng nghĩa một lệnh **NEXTVAL** native. Một số generator của provider có thể mô phỏng sequence bằng bảng khi DB không có sequence native. Đó là hành vi triển khai, không nên viết tài liệu hệ thống như thể mọi provider bắt buộc mô phỏng giống nhau.
- **GenerationType.AUTO** là lựa chọn tiện lợi nhưng không cố định chiến lược qua nâng cấp provider; mọi thay đổi liên quan ID cần được xem như thay đổi tương thích dữ liệu, không chỉ là refactor Java.

## 7. Thu thập thông tin trước khi quyết định chiến lược

Trước khi thử annotation, nên ghi rõ cấu hình sẽ kiểm chứng:

| Thông tin | Ví dụ | Lý do cần biết |
|---|---|---|
| Jakarta Persistence API | 3.1 hoặc 3.2 | Biết enum/annotation chuẩn khả dụng |
| Provider | Hibernate ORM 6.x, EclipseLink 4.x | Biết cách sinh SQL và đặc tính provider |
| DBMS | PostgreSQL, MySQL, Oracle... | Xác định khả năng DDL và cú pháp cấp ID |
| Phiên bản DBMS | PostgreSQL 16; MySQL 8.0 | Chức năng identity/sequence có thể phụ thuộc phiên bản |
| JDBC driver | PostgreSQL JDBC Driver, MySQL Connector/J... | Hỗ trợ generated keys và kiểu JDBC |
| Dialect/platform | PostgreSQLDialect, MySQLDialect... | Provider chọn generator và SQL đúng |
| Schema | public, app, dbo... | Tên sequence/bảng và search path có thể khác |
| Quyền DB | CREATE/USAGE/SELECT/INSERT/UPDATE... | Generator phải được phép truy cập tài nguyên |
| Cách sinh schema | Migration hoặc schema generation | Cần biết sequence/identity/table do ai tạo |
| Mô hình triển khai | Một instance hay nhiều node | Kiểm tra tránh trùng khóa khi cấp phát đồng thời |

Một ghi chép triển khai mẫu:

~~~text
Persistence unit: catalogPu
JPA API: Jakarta Persistence 3.1
Provider: Hibernate ORM 6.x
Database: PostgreSQL 16
JDBC driver: PostgreSQL JDBC tương thích
Schema: catalog
ID Java type: Long
Proposed strategy: SEQUENCE
Physical sequence: catalog.product_id_seq
allocationSize: 1
Schema ownership: Flyway migration
Validation environment: test database dùng chính PostgreSQL
~~~

Số phiên bản ở ví dụ chỉ để minh họa cách ghi chép, không phải yêu cầu cố định. Khi nâng cấp một thành phần, chạy lại quy trình kiểm tra thay vì tin rằng kết quả cũ chắc chắn còn đúng.

## 8. Kiểm tra cấu hình IDENTITY

### 8.1. Entity mẫu

~~~java
package com.example.idcheck;

import jakarta.persistence.*;

@Entity
@Table(name = "identity_records")
public class IdentityRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String label;

    protected IdentityRecord() {}

    public IdentityRecord(String label) {
        this.label = label;
    }

    public Long getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
~~~

### 8.2. Ví dụ DDL

PostgreSQL hiện đại có thể sử dụng:

~~~sql
CREATE TABLE identity_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

MySQL sử dụng cú pháp khác:

~~~sql
CREATE TABLE identity_records (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

SQL Server dùng cú pháp identity của nó:

~~~sql
CREATE TABLE identity_records (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

Các câu SQL này là **ví dụ riêng cho từng DB**, không chạy cả ba trên cùng một DB. Oracle, H2 và MariaDB cũng có cách khai báo tương ứng theo phiên bản.

### 8.3. Điều cần xác nhận

1. Cột ID được cấu hình để DB tự cấp giá trị, thay vì chỉ là một cột BIGINT có khóa chính.
2. SQL INSERT mà provider phát ra không tự ghi một ID chưa hợp lệ vào cột tự sinh.
3. Provider lấy được khóa sau INSERT và đưa vào **entity.getId()** theo quy tắc lifecycle.
4. Hai bản ghi mới khác nhau nhận ID khác nhau.
5. Lỗi transaction và rollback được xử lý đúng; không yêu cầu ID tái sử dụng sau rollback.
6. Nếu có insert số lượng lớn, đo khả năng JDBC batching thực tế thay vì dựa vào tuyên bố chung rằng IDENTITY luôn nhanh hoặc luôn chậm.

Đối với một số tổ hợp provider/dialect, IDENTITY khiến INSERT phải được thực hiện sớm để lấy khóa. Vì vậy **ID có thể đã có trước khi transaction commit**, và thứ tự SQL có thể khác cơ chế SEQUENCE. Không dùng thời điểm xuất hiện ID để làm tín hiệu rằng bản ghi đã được ghi vĩnh viễn.

## 9. Kiểm tra cấu hình SEQUENCE

### 9.1. Entity và @SequenceGenerator

~~~java
package com.example.idcheck;

import jakarta.persistence.*;

@Entity
@Table(name = "sequence_records")
public class SequenceRecord {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "sequence_record_generator"
    )
    @SequenceGenerator(
        name = "sequence_record_generator",
        sequenceName = "sequence_record_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(nullable = false, length = 120)
    private String label;

    protected SequenceRecord() {}

    public SequenceRecord(String label) {
        this.label = label;
    }

    public Long getId() {
        return id;
    }
}
~~~

### 9.2. DDL tham khảo PostgreSQL

~~~sql
CREATE SEQUENCE sequence_record_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE sequence_records (
    id BIGINT PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

Với ví dụ này, **JPA provider lấy ID từ sequence** rồi dùng giá trị đó để INSERT. Cột **id** không bắt buộc có SQL DEFAULT nextval nếu provider luôn cung cấp ID tường minh cho mọi thao tác INSERT. Nếu hệ thống khác cũng chèn dữ liệu, cần thiết kế một cơ chế cấp ID chung, tránh hai nguồn cấp khác nhau đụng khóa.

Oracle, SQL Server, MariaDB và H2 có thể hỗ trợ native sequence, nhưng cú pháp CREATE SEQUENCE, cách lấy giá trị và các thuộc tính nâng cao khác nhau. Không nên copy DDL PostgreSQL nguyên xi cho mọi hệ quản trị.

### 9.3. Kiểm tra tên và schema

Hai chỗ dễ lệch:

- **sequenceName** trong annotation khác tên sequence vật lý.
- Sequence nằm ở schema khác search path mặc định hoặc tài khoản ứng dụng thiếu quyền truy cập.

Ví dụ:

~~~java
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "order_id_seq",
    schema = "sales",
    allocationSize = 1
)
~~~

Nếu database quản lý sequence trong schema **sales**, provider cần tham chiếu đúng đối tượng và tài khoản cần quyền tương ứng. Cách thiết lập quyền, quoting và search path phụ thuộc DBMS.

### 9.4. allocationSize và increment của sequence

**allocationSize** cho phép provider cấp phát trước hoặc theo nhóm những ID để giảm số lần gọi sequence. Giá trị mặc định của @SequenceGenerator là **50**; nhiều dự án chủ động cấu hình giá trị khác.

~~~java
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
~~~

Không được kết luận rằng với allocationSize = 50 thì provider sẽ chạy đúng một câu SQL lấy sequence sau mỗi 50 INSERT trong mọi trường hợp. Hành vi còn tùy optimizer của provider và cấu hình generator. Một số cách tối ưu yêu cầu **INCREMENT BY** của sequence ở DB phù hợp với allocationSize; cấu hình không khớp có thể gây lỗi validation hoặc khiến các bộ cấp phát hoạt động sai.

Quy tắc thực hành:

1. Nếu muốn ví dụ dễ hiểu, có thể dùng **allocationSize = 1** và sequence DB **INCREMENT BY 1**.
2. Nếu muốn hiệu năng cao, chọn allocationSize theo khả năng provider và tải thực tế, sau đó đồng bộ cấu hình sequence ở DB.
3. Khi **nhiều ứng dụng** cùng dùng sequence, phải bảo đảm cách phân vùng và cấp phát không tạo ID trùng.
4. **Không tái tạo hoặc reset sequence** trong production chỉ vì muốn ID bắt đầu lại từ 1; dữ liệu hiện hữu và các cache cấp phát có thể vẫn sử dụng khoảng giá trị cũ.
5. Chênh lệch ID lớn hoặc có khoảng trống là chuyện bình thường với sequence và cơ chế cấp phát theo lô.

### 9.5. Kiểm chứng provider có dùng native sequence không

Khi bật SQL log của provider, có thể thấy lệnh lấy giá trị từ sequence trước INSERT hoặc SQL liên quan generator. Tên hàm và cú pháp khác nhau giữa PostgreSQL, Oracle, SQL Server.

Nếu chạy trên MySQL, cần đặc biệt chú ý: **không nên kết luận SEQUENCE native chỉ vì INSERT thành công**. Một số provider có thể tự dùng bảng mô phỏng. Hãy xem SQL và các bảng generator thực tế.

## 10. Kiểm tra cấu hình TABLE

### 10.1. Entity mẫu

~~~java
package com.example.idcheck;

import jakarta.persistence.*;

@Entity
@Table(name = "table_records")
public class TableRecord {

    @Id
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "table_record_generator"
    )
    @TableGenerator(
        name = "table_record_generator",
        table = "id_allocation",
        pkColumnName = "generator_name",
        valueColumnName = "generator_value",
        pkColumnValue = "table_record",
        allocationSize = 1
    )
    private Long id;

    @Column(nullable = false, length = 120)
    private String label;

    protected TableRecord() {}

    public TableRecord(String label) {
        this.label = label;
    }

    public Long getId() {
        return id;
    }
}
~~~

### 10.2. Cấu trúc bảng cấp phát

Ví dụ DDL:

~~~sql
CREATE TABLE id_allocation (
    generator_name VARCHAR(100) PRIMARY KEY,
    generator_value BIGINT NOT NULL
);

CREATE TABLE table_records (
    id BIGINT PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

Trong ví dụ, **id_allocation** là bảng dùng làm bộ cấp số; **table_records** là bảng dữ liệu nghiệp vụ. Giá trị **pkColumnValue = "table_record"** giúp generator xác định hàng dành cho loại ID này. Tùy provider, hàng generator có thể được khởi tạo tự động hoặc cần quy trình khởi tạo theo quy tắc của provider/schema; không tự chèn một giá trị bất kỳ nếu chưa xác định ý nghĩa bộ đếm và initialValue.

### 10.3. Các điều kiện cần kiểm tra

- Ứng dụng có quyền **SELECT, INSERT, UPDATE** trên bảng cấp phát không?
- Bảng generator có **khóa duy nhất** trên cột định danh generator không?
- Provider có thực hiện khóa hàng hoặc cập nhật an toàn để hai transaction không cùng nhận ID không?
- Khi bị nhiều luồng hoặc nhiều node truy cập, bảng cấp phát có trở thành điểm nghẽn không?
- Nếu dùng allocationSize lớn, provider giữ cache cấp phát ra sao khi ứng dụng restart?
- Khi schema đã tồn tại, tên và kiểu cột có khớp metadata generator không?

TABLE thường hữu ích khi native sequence không có hoặc muốn một cơ chế mô hình hóa chung, nhưng **đổi lại cần chi phí SQL/locking**. Không nên chọn TABLE chỉ vì thấy nó có mặt trong enum mà bỏ qua khả năng IDENTITY hoặc SEQUENCE native phù hợp hơn.

## 11. Kiểm tra cấu hình UUID

### 11.1. Entity mẫu

~~~java
package com.example.idcheck;

import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "uuid_records")
public class UuidRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 120)
    private String label;

    protected UuidRecord() {}

    public UuidRecord(String label) {
        this.label = label;
    }

    public UUID getId() {
        return id;
    }
}
~~~

Để biên dịch đoạn mã, project cần dùng **Jakarta Persistence API có GenerationType.UUID**, tức từ phiên bản 3.1. Dự án cũ có thể dùng generator riêng của provider hoặc tự sinh UUID trong Java theo một thiết kế khác.

### 11.2. Hai kiểm tra độc lập

**Kiểm tra A — Sinh giá trị.** Sau khi persist theo cơ chế đã cấu hình, thuộc tính ID có giá trị UUID hợp lệ, không bị để null, và hai entity mới có ID khác nhau.

**Kiểm tra B — Lưu trữ và truy vấn.** JDBC/provider có thể ghi UUID vào cột DB, đọc lại đúng giá trị và dùng trong mệnh đề WHERE để tải entity bằng khóa chính.

PostgreSQL có kiểu SQL **UUID**. SQL Server có **uniqueidentifier**. DB khác có thể lưu trong BINARY, VARBINARY, CHAR hoặc VARCHAR tùy schema và converter. Vì vậy, không áp dụng một DDL UUID duy nhất cho tất cả DB:

~~~sql
-- Ví dụ riêng cho PostgreSQL:
CREATE TABLE uuid_records (
    id UUID PRIMARY KEY,
    label VARCHAR(120) NOT NULL
);
~~~

Khi provider ánh xạ UUID sang kiểu cột khác, schema phải tương thích với quy tắc binding của provider. Nếu sử dụng kiểu chuỗi, cần quy định chuẩn biểu diễn, độ dài, chữ hoa/chữ thường và khả năng index. Nếu dùng dạng nhị phân, cần thống nhất thứ tự byte và cách chuyển đổi khi nhiều dịch vụ cùng đọc dữ liệu.

### 11.3. UUID không tự thay thế kiểm tra tính duy nhất

UUID được thiết kế để có xác suất va chạm cực thấp theo phương thức sinh phù hợp, nhưng bảng vẫn cần **PRIMARY KEY/UNIQUE** để bảo vệ dữ liệu. UUID cũng có đặc tính chỉ mục và locality khác số thứ tự tăng dần; nếu dữ liệu lớn hoặc tốc độ INSERT cao, cần đo trên DB thật. Việc chọn biến thể UUID cụ thể có thể do provider quyết định; đừng mặc định **GenerationType.UUID** luôn phát sinh một version UUID cố định nếu provider/đặc tả không cam kết điều đó.

## 12. AUTO: phải kiểm tra SQL do provider tự chọn

Ví dụ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

Một sai lầm phổ biến là nghĩ AUTO “đọc DB rồi luôn chọn cơ chế tốt nhất” theo cùng quy tắc bất kể provider. Trên thực tế, AUTO trao quyết định cho provider; thuật toán lựa chọn có thể thay đổi theo **major version**, kiểu ID, dialect hoặc metadata generator.

Khi chọn AUTO cần lưu lại:

1. Provider đang chọn generator nào.
2. Có tạo hoặc đòi hỏi sequence/bảng generator riêng không.
3. Tên đối tượng generator và schema thực tế là gì.
4. Giá trị allocation size và ảnh hưởng đến ID hiện hữu.
5. Kết quả khi cập nhật phiên bản provider/dialect hoặc chuyển DBMS.

Đặc biệt, khi chuyển từ provider phiên bản cũ sang phiên bản mới, một chiến lược AUTO có thể chuyển từ TABLE sang SEQUENCE hoặc thay đổi cách đặt tên đối tượng cấp phát. **Nếu schema không được migration tương ứng, ứng dụng có thể không khởi động hoặc phát sinh lỗi tạo ID khi INSERT.**

AUTO phù hợp khi cho phép provider tự quyết định và có kiểm chứng tích hợp rõ ràng. Nếu ứng dụng cần ổn định về DDL, tên sequence, cấp phát ID hoặc tính tương thích dữ liệu lâu dài, thường nên khai báo strategy và generator tường minh.

## 13. Xây dựng phép kiểm chứng tích hợp trên database thật

Một bảng so sánh lý thuyết chưa đủ. Nên có một phép thử sử dụng **đúng DBMS/phiên bản**, **đúng provider** và **đúng schema** dự định triển khai. Trước hết kiểm tra một entity chiến lược, sau đó mở rộng cho các generator còn lại.

### 13.1. Persistence unit cho bài thử

Ví dụ chạy ứng dụng Java SE với PostgreSQL và persistence unit RESOURCE_LOCAL:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="idCheckPu"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.idcheck.IdentityRecord</class>
        <class>com.example.idcheck.SequenceRecord</class>
        <class>com.example.idcheck.TableRecord</class>
        <class>com.example.idcheck.UuidRecord</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/idcheck"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="idcheck_user"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="example_only"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Đoạn cấu hình giả định đã có dependencies tương ứng (Jakarta Persistence API, Hibernate hoặc EclipseLink, JDBC driver) và các bảng/sequence phù hợp. Thông tin kết nối là **ví dụ**, không đưa mật khẩu thật vào mã nguồn. Với DB hoặc provider khác, thay driver, URL, schema và cấu hình phù hợp.

Ví dụ chỉ bật các entity có generator/schema đã chuẩn bị đúng. Trong dự án thực tế, việc thêm một entity sai mapping có thể khiến toàn bộ persistence unit khởi tạo thất bại trước khi phép thử bắt đầu.

### 13.2. Ví dụ JPA smoke test

Đoạn mã sau kiểm tra **SequenceRecord** đã được khai báo ở phần trước:

~~~java
package com.example.idcheck;

import jakarta.persistence.*;
import java.util.Objects;

public final class SequenceSmokeTest {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("idCheckPu");
        try {
            Long firstId = save(emf, "first");
            Long secondId = save(emf, "second");

            if (Objects.equals(firstId, secondId)) {
                throw new AssertionError("Duplicate generated IDs");
            }

            EntityManager readEm = emf.createEntityManager();
            try {
                SequenceRecord a = readEm.find(SequenceRecord.class, firstId);
                SequenceRecord b = readEm.find(SequenceRecord.class, secondId);
                if (a == null || b == null) {
                    throw new AssertionError("Saved entities not found");
                }
            } finally {
                readEm.close();
            }

            System.out.println("Generated IDs: " + firstId + ", " + secondId);
        } finally {
            emf.close();
        }
    }

    private static Long save(EntityManagerFactory emf, String label) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            SequenceRecord record = new SequenceRecord(label);
            em.persist(record);
            em.flush();

            Long generatedId = record.getId();
            if (generatedId == null) {
                throw new AssertionError("ID is null after flush");
            }

            tx.commit();
            return generatedId;
        } catch (RuntimeException | Error ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Ở ví dụ này, **flush()** được gọi để phát hiện lỗi SQL trước khi commit và kiểm tra ID sau khi đồng bộ. **flush không phải commit**: entity chỉ được xác nhận bền vững sau khi commit thành công. Đoạn kiểm tra dành cho entity có khóa **Long**; với UUID cần đổi kiểu biến ID tương ứng.

Đây là một smoke test kỹ thuật, chưa kiểm tra được tải lớn, race condition hoặc toàn bộ migration. Trên môi trường kiểm chứng nên mở rộng thành integration test tự động, có setup/teardown database và không dùng dữ liệu production.

### 13.3. Danh sách tình huống phải kiểm chứng

| Tình huống | Quan sát mong đợi | Vì sao quan trọng |
|---|---|---|
| Persist một entity mới | Không lỗi; ID được tạo đúng kiểu | Khả năng cơ bản của generator |
| Persist hai entity liên tiếp | Hai ID khác nhau | Không trùng khóa trong một lần chạy |
| Flush trước commit | Không lỗi mapping/DDL/SQL | Phát hiện vấn đề generator sớm |
| Commit rồi tạo EntityManager mới | Tìm lại theo ID thành công | Giá trị ID được DB lưu và provider đọc được |
| Đóng rồi tạo lại EntityManagerFactory | ID không bị reset bất thường | Trạng thái cấp số được quản lý bền vững đúng cách |
| Rollback một INSERT | Không commit dữ liệu | Phân biệt cấp ID và tính bền vững transaction |
| Hai transaction song song | Không sinh trùng ID | Kiểm tra concurrency, nhất là TABLE |
| Hai instance ứng dụng | Không đụng khóa do cache cấp phát | Kiểm tra môi trường nhiều node |
| Insert theo lô | Tốc độ và số roundtrip chấp nhận được | Kiểm tra hiệu năng IDENTITY/SEQUENCE/TABLE |
| Nâng cấp provider hoặc DB | Hành vi generator vẫn phù hợp | Tránh thay đổi cơ chế cấp ID âm thầm |

Với test concurrency, có thể dùng hai EntityManager riêng trong hai thread hoặc hai tiến trình khác nhau; **không chia sẻ một EntityManager giữa các thread**. Đừng chỉ chạy một transaction duy nhất rồi kết luận TABLE đã an toàn trong môi trường nhiều node.

## 14. Đối chiếu DDL và SQL thực tế

### 14.1. Xem schema

Đối với PostgreSQL:

~~~sql
-- Kiểm tra tên và increment của sequence đã được tạo.
SELECT schemaname, sequencename, increment_by
FROM pg_sequences
WHERE schemaname = current_schema();

-- Kiểm tra column identity của một bảng.
SELECT table_name, column_name, is_identity, identity_generation
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'identity_records';
~~~

Đối với MySQL:

~~~sql
SHOW CREATE TABLE identity_records;
~~~

Cần kiểm tra ID có **AUTO_INCREMENT** thực sự hay chỉ được khai báo BIGINT PRIMARY KEY.

Đối với SQL Server, có thể xem metadata về sequence và identity:

~~~sql
SELECT name
FROM sys.sequences
WHERE name = 'sequence_record_id_seq';

SELECT
    c.name AS column_name,
    c.is_identity
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID('dbo.identity_records');
~~~

Đối với Oracle, có thể truy vấn metadata phù hợp, ví dụ **USER_SEQUENCES**, **USER_TAB_COLUMNS**, tùy quyền và schema hiện tại. Tên đối tượng trong catalog có thể phân biệt chữ hoa/chữ thường nếu được tạo với quoted identifiers.

### 14.2. Xem SQL phát sinh

Với Hibernate, có thể bật log SQL trên môi trường dev/test bằng cấu hình provider tương ứng, chẳng hạn:

~~~properties
# Thuộc tính riêng Hibernate (không phải chuẩn JPA).
hibernate.show_sql=true
hibernate.format_sql=true
~~~

Trong Spring Boot, việc cấu hình logger Hibernate thường được thực hiện ở namespace logger của framework, và tên category có thể đổi giữa Hibernate 5/6. Với EclipseLink, dùng logger/cấu hình SQL của EclipseLink. Không nên áp dụng nguyên các property riêng Hibernate cho EclipseLink.

Khi quan sát:

- **IDENTITY**: kiểm tra lệnh INSERT cùng cơ chế nhận generated key.
- **SEQUENCE**: xem có câu SQL đọc sequence native, hay các câu SELECT/UPDATE trên bảng generator.
- **TABLE**: xem truy cập bảng cấp phát, khóa hoặc update được provider tạo.
- **UUID**: xem ID được provider cấp và bind vào cột SQL kiểu gì.
- **AUTO**: xác định chiến lược được chọn thực tế bằng cả log và schema.

Khi bật log, chú ý không ghi mật khẩu hoặc dữ liệu nhạy cảm. Trong production, logging chi tiết SQL/bind parameter có thể gây chi phí và rủi ro bảo mật; dùng có kiểm soát trên môi trường kiểm chứng.

### 14.3. Không dùng một API metadata đơn lẻ làm bằng chứng đầy đủ

Ví dụ JDBC **DatabaseMetaData.supportsGetGeneratedKeys()** là thông tin hữu ích về khả năng lấy khóa DB sinh, nhưng không tự trả lời provider sẽ dùng SEQUENCE hay TABLE. Tương tự, việc DB hỗ trợ **CREATE SEQUENCE** không chứng minh JPA provider biết cách dùng sequence trong phiên bản dialect đang chạy.

Kết luận đáng tin cậy phải dựa trên **DDL đúng + cấu hình provider đúng + transaction persist thành công + đọc lại được + hành vi dưới tải phù hợp**.

## 15. Các yếu tố provider-specific cần kiểm tra

### 15.1. Dialect

Một ORM provider dùng **dialect** hoặc **database platform** để chọn câu SQL phù hợp. Nếu Hibernate xác định sai database hoặc ứng dụng ép dùng dialect không khớp, generator có thể sử dụng cú pháp sai.

Ví dụ, **MySQLDialect** không phải là lựa chọn tương đương cho mọi phiên bản MariaDB khi cần sequence native. Khi gặp lỗi “sequence not found”, “syntax error near NEXT VALUE” hoặc câu SQL tạo cột ID không hợp lệ, cần xem lại dialect/platform, JDBC metadata và phiên bản server.

Ở những phiên bản Hibernate hiện đại, dialect có thể được tự nhận diện qua JDBC; đừng ép cấu hình một dialect cũ chỉ vì ví dụ trên mạng. Khi dùng EclipseLink, kiểm tra loại database platform và cấu hình sequencing tương ứng.

### 15.2. Generator và optimizer riêng của provider

Provider có thể có generator đặc thù, như generator cấp ID theo khối, theo UUID version nhất định hoặc theo một bảng riêng. Những tính năng đó có thể cải thiện hiệu năng nhưng làm code gắn chặt hơn với provider. Nếu sử dụng extension:

1. Ghi lại tên và phiên bản provider.
2. Xác định extension có còn được hỗ trợ sau khi nâng cấp không.
3. Xác định DDL và giá trị cấu hình generator (allocation, increment, table name).
4. Kiểm tra ranh giới phân bổ giữa các node ứng dụng.
5. Chuẩn bị migration nếu đổi từ generator riêng sang API chuẩn.

Đặc biệt, tên class nội bộ của generator hoặc phương thức kiểm tra Dialect có thể thay đổi giữa các major version; không nên thiết kế code ứng dụng phụ thuộc vào class nội bộ khi chỉ cần API JPA chuẩn.

### 15.3. Bytecode enhancement không phải điều kiện của generator

Các tính năng ORM như lazy loading và dirty checking có thể phụ thuộc enhancement, nhưng **không nên nhầm chúng với hỗ trợ chiến lược sinh ID**. Kiểm tra generator tập trung vào DDL, dialect, JDBC và lifecycle, không suy ra kết quả chỉ từ cấu hình enhancement.

## 16. Đổi chiến lược trên hệ thống đã có dữ liệu

Việc chuyển chiến lược ID của một bảng đang vận hành có thể nguy hiểm hơn việc tạo bảng mới. Một số tình huống:

### 16.1. Từ IDENTITY sang SEQUENCE

Nếu IDENTITY đã cấp đến 50.000 nhưng sequence mới bắt đầu ở 1, lần INSERT tiếp theo có thể vi phạm khóa chính. Cần tạo sequence trong schema với điểm bắt đầu **cao hơn vùng ID đang sử dụng**, xét transaction đang chạy, cache cấp phát và nhiều node. Không nên chỉ chạy **CREATE SEQUENCE ... START 1** rồi đổi annotation.

### 16.2. Từ TABLE sang SEQUENCE

Bảng generator có thể lưu giá trị cấp phát kế tiếp hoặc giá trị biên của một khối ID, tùy provider. Không nên copy đơn giản số đang có từ bảng generator sang START WITH của sequence mà chưa hiểu ý nghĩa của giá trị đó và optimizer.

### 16.3. Đổi allocationSize

Nếu trước đây provider phân bổ ID theo khối 50, còn phiên bản mới dùng khối 100, cấu hình **sequence increment**, giá trị sequence hiện tại và các node đang chạy phải được xét cùng nhau. Triển khai rolling upgrade khi nhiều phiên bản còn cùng ghi dữ liệu cần kế hoạch tương thích.

### 16.4. Đổi từ Long sang UUID

Đây là thay đổi **kiểu khóa** chứ không chỉ đổi thuật toán sinh. Nó có thể ảnh hưởng:

- Kiểu cột và chỉ mục PRIMARY KEY.
- Tất cả khóa ngoại tham chiếu tới entity.
- DTO, API path, cache key và giao thức trao đổi giữa dịch vụ.
- Dữ liệu lịch sử, job batch, log và hệ thống tích hợp.

Thay đổi nên có migration và kế hoạch chuyển đổi dữ liệu cụ thể; không đơn giản chỉ đổi **Long id** thành **UUID id** và strategy thành UUID.

## 17. Rủi ro đặc biệt khi có nhiều hệ thống cùng ghi một bảng

Giả sử ứng dụng A dùng JPA **GenerationType.SEQUENCE**, ứng dụng B dùng SQL INSERT và một job ETL lại tự tính **MAX(id) + 1**. Dù ứng dụng A có generator đúng, B hoặc ETL vẫn có thể sinh giá trị trùng hoặc vượt vùng cấp phát của A.

**MAX(id) + 1 không an toàn khi có nhiều transaction** vì hai transaction có thể đọc cùng MAX rồi cùng chọn một ID.

Khi nhiều hệ thống cùng ghi một bảng cần:

- Thống nhất một nguồn cấp ID, chẳng hạn cùng sequence hoặc identity của DB.
- Nếu có vùng ID riêng, phải thiết kế phân vùng rõ ràng và kiểm tra giới hạn của từng vùng.
- Bảo đảm schema có PRIMARY KEY để chặn mọi trường hợp trùng khóa còn sót.
- Cân nhắc UUID khi cần định danh độc lập giữa các hệ thống, đồng thời chuẩn hóa kiểu lưu và cơ chế chuyển đổi.
- Tính đến transaction rollback và retry; yêu cầu ID tăng liên tục không có khoảng trống thường không phù hợp với generator kỹ thuật.

## 18. Các triệu chứng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách tiếp cận |
|---|---|---|
| Table không tồn tại khi chạy AUTO | Provider tự chọn table generator nhưng schema chưa tạo | Xem SQL, generator và migration |
| Sequence không tồn tại | sequenceName/schema sai hoặc chưa triển khai DDL | Xác nhận tên trong catalog và quyền |
| SQL sequence báo lỗi cú pháp | DB không có native sequence hoặc dialect sai | Kiểm tra DB version và dialect; cân nhắc generator khác |
| IDENTITY INSERT thất bại vì cột không tự sinh | Cột DB chỉ là BIGINT PRIMARY KEY thông thường | Kiểm tra DDL thực của cột |
| ORM không lấy được ID sau INSERT | Generated-key support/driver/provider/schema không khớp | Kiểm tra SQL, driver, IDENTITY DDL và logs |
| Trùng primary key sau migration | Sequence/counter thấp hơn dữ liệu hiện có hoặc hai nguồn cấp ID | Đối chiếu dữ liệu, generator và plan migration |
| Startup báo mismatch increment/sequence | allocationSize và increment DB không nhất quán theo optimizer | Đồng bộ cấu hình provider và sequence DDL |
| TABLE generator chậm | Tranh chấp trên hàng cấp ID, nhiều roundtrip | Đo tải; cân nhắc SEQUENCE/IDENTITY khi phù hợp |
| Hibernate chạy H2 nhưng lỗi ở MySQL | Tính năng SQL/dialect khác nhau | Test với DB production tương đương |
| UUID persist được nhưng find theo ID không trả kết quả | Cột UUID, converter hoặc JDBC mapping không khớp | Kiểm tra biểu diễn và type binding |
| Đổi AUTO sau nâng cấp provider bị lỗi | Provider đổi generator hoặc tên sequence/table | Xem release notes và chạy migration tương thích |
| Hai node sinh trùng ID | Generator thủ công/caching/optimizer sai, chia vùng cấp phát lỗi | Kiểm tra concurrency và nhất quán nguồn cấp ID |

Không kết luận lỗi chỉ từ thông điệp “could not execute statement”. Cần nhìn **root cause**, tên đối tượng DB, SQL phát sinh, SQLState nếu có, và metadata của provider/driver.

## 19. Lựa chọn chiến lược theo bối cảnh

| Bối cảnh | Hướng lựa chọn thường gặp | Kiểm tra quyết định |
|---|---|---|
| PostgreSQL và khóa số tăng, cần batch nhiều | SEQUENCE là ứng viên mạnh | Native sequence, allocationSize, batching và schema |
| MySQL với cột AUTO_INCREMENT | IDENTITY thường tự nhiên | Generated keys và batching thực tế |
| Oracle dùng schema có sẵn với sequence | SEQUENCE thường phù hợp | Sequence name, quyền và increment |
| SQL Server với identity column hiện hữu | IDENTITY thường hợp với schema | IDENTITY property, driver và DDL |
| DB không có sequence native nhưng cần cơ chế dùng chung | TABLE hoặc cơ chế DB/provider phù hợp | Locking, hiệu năng và migration |
| Nhiều dịch vụ cần sinh ID độc lập | UUID là ứng viên | Phiên bản JPA, lưu UUID, index, tính tương thích |
| Ứng dụng cần portable và chấp nhận provider chọn | AUTO | SQL/DDL thực tế sau mỗi lần thay provider/DB |

Đây là **định hướng**, không phải luật tuyệt đối. Nếu dự án đang dùng một cơ chế ổn định, có migration đầy đủ và đạt yêu cầu hiệu năng, không cần thay đổi chỉ vì thấy một strategy khác phổ biến hơn.

## 20. Tình huống thực hành

### Tình huống 1: SEQUENCE trên MySQL

Một entity khai báo:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_seq_gen"
)
@SequenceGenerator(
    name = "product_seq_gen",
    sequenceName = "product_id_seq"
)
private Long id;
~~~

Hệ quản trị là MySQL 8.x. Hãy dự đoán vấn đề.

**Phân tích:** MySQL 8.x không có native sequence độc lập như PostgreSQL/Oracle. Một số provider có cơ chế bảng mô phỏng cho chiến lược SEQUENCE, nhưng đó không phải bằng chứng về sequence native. Cần xem provider/dialect có thực sự hỗ trợ đường đi này không. Nếu database dùng AUTO_INCREMENT và không có yêu cầu đặc biệt, IDENTITY là lựa chọn dễ hiểu hơn; nếu dùng TABLE, cần đo khả năng chịu tải.

### Tình huống 2: Sequence trên PostgreSQL, sai allocation

JPA khai báo **allocationSize = 50**, trong khi migration tạo sequence **INCREMENT BY 1**. Một phiên bản Hibernate có thể báo mismatch khi khởi động.

**Cách xử lý:** xác định optimizer và contract của Hibernate phiên bản đang chạy. Chỉnh annotation hoặc DDL để khớp cơ chế cấp phát; với dữ liệu đã có, cần xem cả sequence value và nhiều instance trước khi thay đổi. Không tự tắt validation như biện pháp đầu tiên.

### Tình huống 3: IDENTITY có ID dù transaction rollback

Đoạn mã:

~~~java
tx.begin();
IdentityRecord record = new IdentityRecord("temporary");
em.persist(record);
em.flush();
Long id = record.getId();
tx.rollback();
~~~

**Câu hỏi:** Nếu id có giá trị, record có chắc tồn tại trong DB không?

**Trả lời:** Không. Provider có thể đã INSERT để lấy ID, nhưng rollback vẫn hủy ghi dữ liệu trong transaction. ID có thể bị tiêu hao và không được tái sử dụng, tùy DB.

### Tình huống 4: AUTO sau khi nâng cấp provider

Trước khi nâng cấp, DB có bảng generator; sau khi nâng cấp, log cho thấy provider tìm một sequence không tồn tại.

**Phân tích:** AUTO không cam kết chọn cùng cơ chế qua các phiên bản. Phải xem metadata generator mới, release notes và schema hiện có; nếu muốn ổn định, cân nhắc khai báo strategy/generator tường minh và migration.

### Tình huống 5: UUID sinh thành công nhưng cột sai kiểu

Java entity có **UUID id**, DB lưu ID trong **VARCHAR(16)**.

**Phân tích:** UUID dưới dạng chuỗi chuẩn thường dài hơn 16 ký tự; một mapping mặc định UUID có thể sử dụng nhị phân hoặc kiểu native, không khớp VARCHAR(16). Cần quyết định kiểu lưu được hỗ trợ, sửa schema/converter tương ứng và kiểm tra persist/find qua JDBC.

### Tình huống 6: Một ứng dụng dùng TABLE generator trên ba node

Tất cả node ghi vào bảng cấp phát nhưng hiện tượng chậm rõ khi tải cao.

**Phân tích:** Một hàng cấp số chung có thể trở thành điểm tranh chấp. Đo SQL, thời gian chờ khóa và số lượt cấp phát. Có thể cân nhắc allocation theo khối, native sequence, IDENTITY hoặc UUID tùy database và yêu cầu, nhưng phải xác minh cơ chế cấp phát tránh trùng khóa khi thay đổi.

## 21. Mẫu hồ sơ kiểm chứng chiến lược sinh ID

Sau khi thử nghiệm, một quyết định có thể được ghi lại để người khác vận hành hoặc nâng cấp:

~~~text
Entity: SequenceRecord
Java ID type: Long
JPA strategy: SEQUENCE
Generator name: sequence_record_generator
Sequence name: sequence_record_id_seq
allocationSize: 1
Provider/version: [điền kết quả kiểm tra]
DBMS/version: [điền kết quả kiểm tra]
JDBC driver/version: [điền kết quả kiểm tra]
Dialect/platform: [điền kết quả kiểm tra]
Schema & permissions: [điền kết quả kiểm tra]
Schema creation: migration đã áp dụng
SQL observed: [mô tả lệnh lấy ID và INSERT]
Persist/readback: PASS / FAIL
Restart: PASS / FAIL
Concurrency: PASS / FAIL
Rollback behavior: PASS / FAIL
Load/batching: [số liệu nếu có]
Decision: giữ SEQUENCE hoặc chọn phương án khác
~~~

Mẫu này giúp phân biệt **một strategy hoạt động trên máy phát triển** với **một strategy được xác nhận đủ điều kiện cho môi trường triển khai**. Nếu nâng cấp DBMS, provider hoặc driver, nên tái sử dụng hồ sơ để kiểm tra đúng những giả định có thể thay đổi.

## 22. Ghi nhớ

**GenerationType là yêu cầu trừu tượng của JPA; DBMS và provider quyết định việc triển khai cụ thể.** Một lựa chọn thành công chỉ khi có đủ ba điều kiện: **database có cơ chế hoặc đường mô phỏng được provider hỗ trợ; schema và quyền được cấu hình đúng; ứng dụng xác nhận được tính duy nhất và hành vi transaction qua kiểm thử thực tế**.

Khi phải chọn:

1. **IDENTITY** thường hợp với cột auto-increment/identity có sẵn.
2. **SEQUENCE** thường hợp với hệ có native sequence, nhất là khi muốn chủ động cấp phát theo nhóm và tối ưu batching.
3. **TABLE** có thể dùng như phương án dựa trên bảng khi cần, nhưng phải xem locking và tải.
4. **UUID** phù hợp khi cần sinh ID độc lập, với điều kiện API/provider và biểu diễn SQL tương thích.
5. **AUTO** để provider quyết định, nhưng cần kiểm tra lại khi nâng cấp hoặc chuyển DB.

**Đừng chọn chỉ bằng bảng so sánh:** hãy chạy thử trên đúng bộ **JPA API + provider + dialect + JDBC driver + DBMS + schema**. Quan sát SQL phát sinh, dữ liệu lưu, khả năng đọc lại, rollback, đồng thời và hiệu năng. Kết quả kiểm chứng đó mới là cơ sở xác nhận chiến lược sinh khóa phù hợp cho dự án.
