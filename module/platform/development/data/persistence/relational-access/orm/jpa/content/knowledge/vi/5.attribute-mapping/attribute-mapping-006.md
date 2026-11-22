# Ánh xạ chuỗi, Unicode và giới hạn độ dài trong JPA

Trong ứng dụng dùng **Java Persistence API (JPA)**, thuộc tính `String` thường biểu diễn tên người dùng, địa chỉ, tiêu đề, mã nghiệp vụ hoặc nội dung văn bản. Câu khai báo như `@Column(length = 100)` trông đơn giản, nhưng kết quả lưu trữ còn phụ thuộc vào nhiều tầng: ánh xạ ORM, kiểu cột SQL, bảng mã Unicode, collation của cơ sở dữ liệu và quy tắc kiểm tra dữ liệu đầu vào.

Một ứng dụng có thể gặp các tình huống tưởng như mâu thuẫn:

- Chuỗi tiếng Việt được lưu đúng trong môi trường này nhưng bị biến thành dấu `?` ở môi trường khác.
- `String.length()` trả về `2` cho một emoji mà người dùng nhìn thấy như một ký tự.
- `@Column(length = 50)` đã khai báo nhưng một giá trị quá dài vẫn đi tới database và bị từ chối.
- Hai chuỗi trông giống nhau có độ dài khác nhau và có thể so sánh khác nhau trong truy vấn.
- Cùng mô hình JPA nhưng PostgreSQL, MySQL và SQL Server xử lý độ dài hoặc kiểu chuỗi khác nhau.

Bài học trình bày cách ánh xạ chuỗi, giải thích Unicode và các khái niệm độ dài, rồi kết nối chúng thành một cách thiết kế cột và validation nhất quán.

## 1. Chuỗi trong Java, JPA và cơ sở dữ liệu: Ba tầng khác nhau

Dòng dữ liệu có thể hình dung như sau:

~~~text
Ứng dụng Java
   String displayName = "Nguyễn An 🌿"
          |
          v
JPA Entity Mapping
   @Column(name = "display_name", length = 120)
   private String displayName;
          |
          v
JPA Provider + JDBC Driver
   bind tham số String và truyền đến DB
          |
          v
Database Column
   ví dụ VARCHAR(120) với charset/collation thích hợp
          |
          v
Bộ nhớ và chỉ mục của cơ sở dữ liệu
   byte thực tế, quy tắc so sánh, giới hạn cột
~~~

Phân biệt trách nhiệm:

| Thành phần | Trách nhiệm chính | Không tự bảo đảm |
|---|---|---|
| `String` trong Java | Lưu dãy đơn vị mã UTF-16 và cung cấp API thao tác chuỗi | Số ký tự người dùng nhìn thấy bằng `length()` |
| `@Column` của JPA | Ánh xạ property/field sang cột; cung cấp metadata phục vụ tạo schema | Tự chặn mọi chuỗi vượt độ dài trước SQL |
| Bean Validation, ví dụ `@Size` | Ràng buộc kích thước giá trị theo thuật toán validator | Giới hạn byte/collation của mọi DB |
| JDBC driver | Truyền giá trị giữa Java và database | Sửa cấu hình mã hóa sai của database |
| Kiểu SQL `VARCHAR`/`NVARCHAR`/`TEXT` | Quy định lưu trữ và giới hạn theo DB | Cùng một ý nghĩa độ dài trên mọi hệ quản trị |
| Charset và collation | Biểu diễn ký tự, so sánh, sắp xếp, đôi khi ảnh hưởng UNIQUE | Mọi chuỗi Unicode luôn được nhận diện như nhau |

Vì thế, muốn thiết kế một cột văn bản đúng cần trả lời đồng thời: **dữ liệu có thể chứa ký tự gì, dài tối đa theo đơn vị nào, database sử dụng kiểu/charset nào và validation sẽ đo theo quy tắc nào?**

## 2. Ánh xạ `String` cơ bản với `@Column`

### 2.1. Ví dụ entity

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", length = 120, nullable = false)
    private String displayName;

    @Column(name = "email", length = 254)
    private String email;

    protected Customer() {
        // Constructor không tham số cho JPA.
    }

    public Customer(String displayName, String email) {
        this.displayName = displayName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Ở ví dụ này:

- `@Column(name = "display_name")` khai báo tên cột SQL cho thuộc tính Java `displayName`.
- `length = 120` gợi ý kích thước cột dạng chuỗi khi provider tạo DDL phù hợp.
- `nullable = false` mô tả yêu cầu không nhận `NULL` trong metadata cột.
- `email` không đặt `nullable = false` nên mặc định cho phép giá trị `NULL` theo metadata.
- `@Id` xác định danh tính của entity và độc lập với ý nghĩa độ dài chuỗi.

Nếu không đặt `length`, giá trị mặc định của `@Column.length` trong JPA là **255**. Không khai báo `@Column` thì provider vẫn có thể ánh xạ một thuộc tính `String` persistent theo quy tắc mặc định.

### 2.2. `length` điều khiển điều gì?

~~~java
@Column(length = 120)
private String displayName;
~~~

Trong quá trình **schema generation**, provider sử dụng metadata này để chọn kiểu/độ dài cột tương ứng, ví dụ một dạng `VARCHAR(120)`. SQL thật phụ thuộc dialect, phiên bản provider và database.

Điều `length` **không mặc nhiên làm**:

1. Không gọi `String.substring(...)` để cắt chuỗi dài.
2. Không thay thế validation ở tầng giao diện/API và nghiệp vụ.
3. Không tự đổi kích thước cột đã tồn tại khi cơ chế migration/schema update không chạy.
4. Không thống nhất khái niệm “120 ký tự” cho mọi hệ quản trị và charset.
5. Không tự quyết định một chuỗi tiếng Việt hay emoji có lưu chính xác hay không.

Nếu cột database thực tế là `VARCHAR(40)` nhưng entity khai báo `length = 120`, kết quả ghi vẫn chịu giới hạn cột thật. JPA mapping và schema phải được đồng bộ bằng migration hoặc cơ chế quản lý schema thích hợp.

### 2.3. `nullable`, `unique` và `columnDefinition`

| Thuộc tính | Tác dụng thường gặp | Lưu ý |
|---|---|---|
| `name` | Đặt tên cột | Phân biệt tên field Java và cột SQL |
| `length` | Metadata độ dài cho cột chuỗi | Chủ yếu có ý nghĩa trong DDL; mặc định 255 |
| `nullable` | Metadata ràng buộc NULL | Không thay thế `@NotNull` trong Bean Validation |
| `unique` | Metadata UNIQUE của cột | Cơ chế DDL; so sánh chịu ảnh hưởng collation DB |
| `columnDefinition` | Chỉ định đoạn định nghĩa cột SQL dùng khi tạo DDL | Phụ thuộc dialect/DB, làm giảm tính di động |
| `insertable`/`updatable` | Cho biết cột có tham gia SQL INSERT/UPDATE do JPA tạo | Không quyết định kiểu dữ liệu hoặc charset |

Ví dụ:

~~~java
@Column(name = "article_body", columnDefinition = "TEXT")
private String body;
~~~

`TEXT` là tên kiểu được nhiều DB hỗ trợ nhưng không đồng nhất hoàn toàn giữa các hệ. Khi sử dụng `columnDefinition`, ứng dụng đang đưa một phần quyết định DDL trực tiếp về phía database cụ thể. Nếu cần tính di động, ưu tiên cách ánh xạ chuẩn và quản lý schema bằng migration phù hợp môi trường.

## 3. Unicode là gì và vì sao không nên đếm “ký tự” theo cảm giác?

Unicode xác định các *code point* (điểm mã) để biểu diễn ký tự, dấu, emoji và nhiều thành phần văn bản trên thế giới. Trong ứng dụng Java hiện đại, `String` sử dụng giao diện thao tác dựa trên **UTF-16 code units**, còn database thường lưu bằng UTF-8, UTF-16 hoặc encoding khác tùy hệ thống.

Ba cách đếm sau có thể cho kết quả khác nhau:

1. **Số UTF-16 code units:** giá trị trả về của `String.length()` trong Java.
2. **Số Unicode code points:** có thể đếm bằng `String.codePointCount(...)`.
3. **Số grapheme clusters:** cụm ký tự mà người dùng thường xem là một đơn vị hiển thị, chẳng hạn chữ có dấu hoặc một emoji ghép nhiều code points.

Ngoài ra còn có **số byte** sau khi mã hóa một chuỗi thành UTF-8 hoặc một encoding khác. Byte length liên quan đến lưu trữ, băng thông và giới hạn index, không đồng nghĩa độ dài hiển thị.

### 3.1. Ví dụ cụ thể

| Chuỗi | UTF-16 code units trong Java | Unicode code points | Điều người dùng thường nhìn thấy |
|---|---:|---:|---|
| `A` | 1 | 1 | Một chữ A |
| `é` (dạng ghép sẵn U+00E9) | 1 | 1 | Một chữ é |
| `e\u0301` (chữ e + dấu sắc kết hợp) | 2 | 2 | Một chữ é |
| `😀` | 2 | 1 | Một emoji |
| `👍🏽` | 4 | 2 | Một emoji có tông màu da |

Dòng `e\u0301` trong bảng biểu thị chuỗi gồm chữ `e` và dấu kết hợp U+0301, tức hai code points, dù khi hiển thị thường trông như một chữ có dấu. Chuỗi emoji `👍🏽` gồm hai code points nằm ngoài Basic Multilingual Plane nên có tổng cộng bốn UTF-16 code units.

Trong Java:

~~~java
String a = "é";
String b = "e\u0301";
String emoji = "😀";
String tonedThumb = "👍🏽";

System.out.println(a.length()); // 1
System.out.println(b.length()); // 2

System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1

System.out.println(tonedThumb.length()); // 4
System.out.println(
    tonedThumb.codePointCount(0, tonedThumb.length())
); // 2
~~~

**Quy tắc quan trọng:** Không dùng `String.length()` rồi khẳng định đó là số “ký tự người dùng nhìn thấy”. Với tên hiển thị hoặc văn bản đa ngôn ngữ, cần định nghĩa rõ đơn vị đo trước khi thiết kế giới hạn.

### 3.2. Đếm byte UTF-8

~~~java
import java.nio.charset.StandardCharsets;

String text = "😀";
int javaLength = text.length(); // 2 UTF-16 code units
int codePoints = text.codePointCount(0, text.length()); // 1
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length; // 4
~~~

Một ký tự Unicode có thể dùng một đến bốn byte trong UTF-8 đối với code point hợp lệ. Độ dài byte cần thiết cho cột hoặc index còn phụ thuộc cách database lưu và những giới hạn cụ thể của hệ DB.

### 3.3. Grapheme cluster khó hơn code point

Một emoji gia đình hoặc emoji có chuỗi ký tự liên kết bằng Zero Width Joiner có thể gồm nhiều code points nhưng hiển thị thành một hình. Vì thế `codePointCount` cũng chưa tương đương với số ký tự hiển thị.

Nếu sản phẩm yêu cầu “tên tối đa 40 ký tự nhìn thấy” hoặc cần giới hạn độ dài tin nhắn theo cụm ký tự, hãy chọn một **bộ phân đoạn grapheme tuân theo Unicode** và quy định rõ phiên bản/thuật toán; các thư viện như ICU4J có thể phù hợp. API Java `BreakIterator` cũng cung cấp phân đoạn ký tự, nhưng hành vi chi tiết có thể thay đổi theo phiên bản Java/Unicode và locale.

Nếu yêu cầu là “tối đa 40 code points”, `String.codePointCount(...)` mới đúng đơn vị hơn `String.length()`. Nếu database giới hạn byte, phải kiểm tra độ dài sau mã hóa theo encoding tương ứng.

## 4. Charset, encoding và collation: Ba khái niệm không đồng nghĩa

### 4.1. Charset/encoding

*Charset* là tập ký tự hoặc cơ chế biểu diễn mà hệ thống hỗ trợ; *encoding* mô tả cách mã hóa các ký tự thành byte (thuật ngữ đôi khi được dùng gần nhau trong hệ quản trị). UTF-8 và UTF-16 là hai cách biểu diễn Unicode.

Ví dụ byte UTF-8 của chuỗi:

~~~java
String vietnamese = "Tiếng Việt";
byte[] bytes = vietnamese.getBytes(StandardCharsets.UTF_8);
~~~

Không nên cho rằng vì Java dùng `String` nên mọi tầng ngoài Java đều lưu Unicode đúng. Nếu dữ liệu bị ép vào một encoding không biểu diễn được ký tự, thông tin có thể bị thay thế hoặc bị từ chối.

### 4.2. Collation

*Collation* xác định cách cơ sở dữ liệu so sánh hoặc sắp xếp văn bản, có thể bao gồm độ nhạy chữ hoa/chữ thường, dấu và quy tắc ngôn ngữ.

Ví dụ, tùy collation:

- `"An"` và `"an"` có thể được coi là bằng nhau khi so sánh.
- `"a"` và `"á"` có thể được xem là giống nhau trong một số phép so sánh không phân biệt dấu.
- Sắp xếp tiếng Việt có thể khác thứ tự byte hoặc thứ tự code point.
- Ràng buộc `UNIQUE` trên cột văn bản có thể coi hai giá trị là trùng nhau theo quy tắc so sánh của DB.

**Charset trả lời “lưu được ký tự nào?”; collation trả lời “so sánh/sắp xếp ký tự ra sao?”**. Cả hai tác động đến hành vi nhưng không phải một thuộc tính duy nhất của `@Column(length)`.

### 4.3. Unicode normalization

Unicode cho phép một số nội dung có nhiều biểu diễn code point tương đương về mặt hiển thị. Chẳng hạn:

~~~java
String composed = "\u00E9";  // é: một code point
String decomposed = "e\u0301"; // e + dấu kết hợp: hai code points

System.out.println(composed.equals(decomposed)); // false
~~~

Nếu cần so sánh nhất quán theo một dạng Unicode, ứng dụng có thể chuẩn hóa bằng `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC
);

System.out.println(composed.equals(normalized)); // true
~~~

Các dạng normalization phổ biến gồm NFC/NFD (canonical) và NFKC/NFKD (compatibility). **Không nên áp dụng NFKC hoặc tự biến đổi chữ viết một cách mặc định** cho mọi trường hợp: phép chuẩn hóa tương thích có thể làm thay đổi những phân biệt mà ứng dụng muốn giữ. Với dữ liệu như mã định danh, tên hiển thị, tìm kiếm hoặc văn bản được ký số, quy tắc normalization phải được quyết định theo mục đích nghiệp vụ.

Dù hai chuỗi hiển thị tương đương, việc `=` hoặc `UNIQUE` coi chúng là một còn phụ thuộc DB, collation và cách lưu; không được mặc định database luôn chuẩn hóa Unicode giúp ứng dụng.

## 5. Giới hạn độ dài của các hệ cơ sở dữ liệu phổ biến

Dòng annotation JPA:

~~~java
@Column(length = 120)
private String displayName;
~~~

có thể được provider chuyển thành những kiểu SQL khác nhau theo dialect. Ý nghĩa của `120` phụ thuộc vào kiểu cột thật.

### 5.1. PostgreSQL

Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

Trong PostgreSQL, `VARCHAR(n)` áp dụng giới hạn theo **số ký tự** chứ không phải số byte UTF-8. Với database dùng UTF-8, emoji có thể chiếm nhiều byte nhưng không nhất thiết chiếm nhiều “ký tự” theo cách PostgreSQL đếm. Grapheme cluster vẫn có thể chứa nhiều code points.

PostgreSQL còn có `TEXT` cho chuỗi độ dài biến đổi và `CHAR(n)` có cơ chế đệm khoảng trắng. `VARCHAR(n)` không tự bảo đảm giới hạn theo “ký tự người dùng nhìn thấy”.

Khi cần quan sát:

~~~sql
SELECT
    char_length('😀') AS character_count,
    octet_length('😀') AS byte_count;
~~~

Trên cơ sở dữ liệu PostgreSQL UTF-8, kết quả minh họa là `1` ký tự và `4` byte. Với chuỗi kết hợp nhiều code points, `char_length` sẽ tính theo số ký tự ở mức biểu diễn của DB, không phải một bộ đếm grapheme tùy ý.

### 5.2. MySQL

Ví dụ trên MySQL 8 với Unicode đầy đủ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    display_name VARCHAR(120)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
);
~~~

Với `utf8mb4`, MySQL có thể biểu diễn các ký tự Unicode bao gồm emoji có code points ngoài BMP. Trong MySQL, `VARCHAR(120)` giới hạn theo số ký tự theo semantics của kiểu cột, nhưng dung lượng byte thực tế có thể nhiều hơn đáng kể; giới hạn row/index và cấu hình có thể tạo thêm ràng buộc.

Một số điểm thực tế:

- `utf8mb4` thường là lựa chọn an toàn cho Unicode đầy đủ trong MySQL.
- Tên `utf8` cũ trong một số phiên bản/cấu hình MySQL có thể chỉ khả năng 3 byte (`utf8mb3`); không nên dùng nếu cần emoji đầy đủ.
- `utf8mb4_0900_ai_ci` là ví dụ collation của MySQL 8, có tính chất không phân biệt dấu/chữ hoa theo tên và quy tắc của nó; cần chọn collation theo nghiệp vụ.
- Charset của cột, bảng, database và kết nối có thể tương tác với nhau; hãy xác minh kết quả thực tế thay vì chỉ đọc file cấu hình JPA.

Ví dụ đo độ dài:

~~~sql
SELECT
    CHAR_LENGTH('😀') AS character_count,
    LENGTH('😀') AS byte_count;
~~~

Trong ngữ cảnh MySQL với chuỗi được xử lý bằng `utf8mb4`, giá trị tương ứng thường là `1` ký tự và `4` byte.

### 5.3. SQL Server

SQL Server có các kiểu như `VARCHAR(n)` và `NVARCHAR(n)` với hành vi Unicode/encoding phụ thuộc cấu hình. Khi muốn lưu văn bản Unicode đa ngôn ngữ, `NVARCHAR` là lựa chọn thường gặp:

~~~sql
CREATE TABLE dbo.customer (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    display_name NVARCHAR(120) NOT NULL
);
~~~

Ở SQL Server, tham số `n` của `NVARCHAR(n)` chỉ **số cặp byte** (*byte-pairs*), tối đa `2n` byte cho giá trị; nó **không luôn là số Unicode code points**. Ký tự bổ sung như emoji có thể chiếm hai cặp byte (tương ứng cặp surrogate UTF-16), nên `NVARCHAR(120)` không bảo đảm nhận 120 emoji ngoài BMP.

Khi viết literal Unicode trong T-SQL, tiền tố `N` thường quan trọng:

~~~sql
INSERT INTO dbo.customer(display_name)
VALUES (N'Nguyễn An 😀');
~~~

Với các hệ/collation hỗ trợ UTF-8 trên `VARCHAR`, hành vi cũng có thể khác. Vì thế cần biết kiểu cột và collation cụ thể trước khi kết luận cách lưu Unicode.

### 5.4. Oracle Database

Trong Oracle, độ dài `VARCHAR2` có thể mang semantics theo **BYTE** hoặc **CHAR**:

~~~sql
display_name VARCHAR2(120 CHAR)
~~~

Cấu hình này yêu cầu giới hạn theo ký tự theo cơ chế của Oracle, thay vì `VARCHAR2(120 BYTE)`. Oracle còn có các kiểu national character như `NVARCHAR2`, với cách hỗ trợ và giới hạn riêng.

Không nên sao chép `columnDefinition = "VARCHAR2(120 CHAR)"` sang một dự án dùng PostgreSQL hoặc SQL Server. Đây là SQL gắn với vendor. Khi cần hỗ trợ nhiều DB, nên kiểm soát schema theo từng dialect/migration.

### 5.5. So sánh ngắn

| Hệ CSDL/kiểu cột | Đơn vị độ dài cần quan tâm | Lưu ý |
|---|---|---|
| PostgreSQL `VARCHAR(n)` | Ký tự theo semantics PostgreSQL | Dữ liệu UTF-8 có thể chiếm nhiều byte; không tính grapheme |
| MySQL `VARCHAR(n)` với `utf8mb4` | Ký tự theo semantics MySQL | Có giới hạn lưu trữ theo byte và ảnh hưởng index |
| SQL Server `NVARCHAR(n)` | Cặp byte, tối đa `2n` byte | Emoji ngoài BMP thường dùng hai cặp byte |
| Oracle `VARCHAR2(n BYTE)` | Byte | Ký tự nhiều byte khiến ít ký tự hơn giới hạn n |
| Oracle `VARCHAR2(n CHAR)` | Ký tự theo semantics Oracle | Vẫn chịu giới hạn byte/kiểu của DB |
| Java `String.length()` | UTF-16 code units | Không tương đương số code points hoặc graphemes |

Bảng chỉ nói về đơn vị độ dài ở cấp khái niệm. Mỗi hệ DB còn có giới hạn giá trị/row/index, charset, phiên bản và chế độ cấu hình riêng.

## 6. Ánh xạ Unicode trong JPA: Có cần annotation đặc biệt?

### 6.1. JPA chuẩn thường dùng `String` và `@Column`

Với PostgreSQL UTF-8 hoặc MySQL `utf8mb4` được cấu hình đúng, ứng dụng có thể ánh xạ:

~~~java
@Column(name = "full_name", length = 150, nullable = false)
private String fullName;
~~~

`String` trong Java biểu diễn Unicode; JPA provider và JDBC driver chịu trách nhiệm chuyển dữ liệu đến DB theo khả năng kết nối và kiểu cột. **Không có một annotation JPA chuẩn duy nhất có thể sửa mọi cấu hình charset sai của database.**

Nếu chuỗi tiếng Việt hoặc emoji bị sai khi đọc lại, cần kiểm tra cả dữ liệu đầu vào, JDBC driver, kiểu cột, connection charset và cấu hình database.

### 6.2. Hibernate `@Nationalized` là tiện ích của provider

Trong môi trường sử dụng Hibernate, có thể thấy:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Nationalized;

@Entity
public class LocalizedMessage {

    @Id
    private Long id;

    @Nationalized
    @Column(name = "message_text", length = 200)
    private String text;
}
~~~

`@Nationalized` là **annotation riêng Hibernate**, không thuộc `jakarta.persistence` chuẩn. Nó chỉ định ánh xạ đến các kiểu chuỗi “nationalized” khi dialect/database phân biệt nhóm kiểu này, chẳng hạn những kiểu `NCHAR`/`NVARCHAR` trong một số hệ.

- Trên SQL Server, phân biệt `VARCHAR` và `NVARCHAR` có thể đặc biệt đáng chú ý.
- Trên PostgreSQL UTF-8, thường không cần một kiểu nationalized riêng để biểu diễn Unicode.
- Khi đổi Hibernate sang EclipseLink hoặc provider khác, annotation riêng này cần được rà soát.

Dùng `@Nationalized` không thay thế việc chọn đúng charset/collation hoặc kiểm tra giới hạn cột thực tế.

### 6.3. Không nhầm `@Column(length)` với `@Nationalized`

`length` mô tả giới hạn độ dài cột; `@Nationalized` (nếu provider hỗ trợ) tác động tới loại ánh xạ chuỗi. Hai thuộc tính giải quyết hai vấn đề riêng:

~~~java
@Nationalized
@Column(length = 120)
private String displayName;
~~~

Đoạn này không có nghĩa là “luôn đúng 120 grapheme Unicode trên mọi DB”. Kiểu SQL được chọn, đơn vị độ dài và giới hạn byte vẫn phụ thuộc database.

## 7. Validation: `@Column(length)` khác `@Size(max)`

### 7.1. Vì sao cần kiểm tra đầu vào?

Giả sử database có cột `VARCHAR(100)` và một request gửi chuỗi dài hơn giới hạn. Nếu ứng dụng chỉ có:

~~~java
@Column(length = 100)
private String title;
~~~

provider có thể gửi SQL và database trả lỗi khi giá trị không vừa cột. `@Column(length)` không phải bộ kiểm tra đầu vào bắt buộc chạy trước mỗi setter hoặc mỗi lệnh ghi.

Với Jakarta Bean Validation, có thể khai báo thêm:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Entity
public class Article {

    @Id
    private Long id;

    @NotBlank
    @Size(max = 100)
    @Column(name = "title", length = 100, nullable = false)
    private String title;
}
~~~

Trong ví dụ:

- `@Column(length = 100)` cung cấp metadata ánh xạ/DDL.
- `@Size(max = 100)` yêu cầu validator kiểm tra độ dài của `CharSequence`.
- `@NotBlank` yêu cầu chuỗi không `null` và có ít nhất một ký tự không phải khoảng trắng theo quy tắc validator.
- `nullable = false` mô tả yêu cầu ở schema, không thay thế Bean Validation.

**Quan trọng:** Bean Validation dùng `CharSequence.length()` khi kiểm tra kích thước chuỗi; với `String` Java, đây là số UTF-16 code units. Do đó `@Size(max = 100)` không nhất thiết tương ứng với giới hạn 100 code points, 100 graphemes hoặc 100 byte của database.

Tích hợp validation vào vòng đời JPA còn phụ thuộc có Bean Validation provider, chế độ validation và môi trường triển khai hay không. Ở tầng API, có thể kích hoạt validation rõ ràng (ví dụ dùng `@Valid` với Spring MVC) để báo lỗi sớm, song cần hiểu đó là cơ chế của framework/validator.

### 7.2. Trường hợp `@Size(max)` và độ dài database không trùng nhau

Giả sử một cột `VARCHAR(10)` trên PostgreSQL UTF-8 có thể chứa 10 emoji đơn lẻ (với giả định mỗi emoji là một code point). Nhưng 10 emoji `😀` có `String.length() == 20` vì mỗi emoji cần hai UTF-16 code units. `@Size(max = 10)` sẽ từ chối giá trị dù giới hạn ký tự của cột PostgreSQL có thể vẫn cho phép.

Chiều ngược lại: một cột giới hạn **10 byte** có thể không chứa 10 ký tự tiếng Việt trong UTF-8, dù Java `String.length()` trả `10`. Kiểm tra số UTF-16 code units không đủ để bảo vệ giới hạn byte.

Vì vậy, không nên suy ra rằng cùng một số `max = 100` ở mọi tầng là đủ bảo đảm đồng nhất.

### 7.3. Nếu nghiệp vụ giới hạn code points

Ví dụ nghiệp vụ yêu cầu tên có tối đa 40 **Unicode code points**:

~~~java
public final class UnicodeLimits {

    private UnicodeLimits() {
    }

    public static void requireMaxCodePoints(
            String value, int max, String field) {

        if (value == null) {
            throw new IllegalArgumentException(
                field + " must not be null"
            );
        }

        int count = value.codePointCount(0, value.length());
        if (count > max) {
            throw new IllegalArgumentException(
                field + " exceeds " + max + " Unicode code points"
            );
        }
    }
}
~~~

Sử dụng:

~~~java
UnicodeLimits.requireMaxCodePoints(name, 40, "name");
~~~

Nếu giới hạn theo grapheme clusters, cần bộ đếm grapheme thích hợp thay cho `codePointCount`. Nếu giới hạn theo byte, cần mã hóa và đếm byte tương ứng; cũng phải xử lý dữ liệu Unicode không hợp lệ nếu nguồn đầu vào có thể chứa surrogate đơn lẻ.

### 7.4. Nếu nghiệp vụ giới hạn byte UTF-8

~~~java
import java.nio.charset.StandardCharsets;

public static void requireMaxUtf8Bytes(
        String value, int maxBytes) {

    if (value == null) {
        throw new IllegalArgumentException("value is null");
    }

    int bytes = value.getBytes(StandardCharsets.UTF_8).length;
    if (bytes > maxBytes) {
        throw new IllegalArgumentException(
            "Text exceeds " + maxBytes + " UTF-8 bytes"
        );
    }
}
~~~

Đây chỉ là phép kiểm tra byte UTF-8 tại ứng dụng. Nó phù hợp khi hợp đồng dữ liệu quy định cụ thể giới hạn byte UTF-8; không nên dùng nguyên xi để phán đoán dung lượng `NVARCHAR` của SQL Server hoặc những kiểu cột có cách lưu trữ khác.

### 7.5. Một quy tắc thiết kế giới hạn có thể áp dụng

Nêu rõ trong đặc tả API và database:

- **Giới hạn nghiệp vụ:** ví dụ “tên hiển thị tối đa 40 Unicode code points”.
- **Giới hạn lưu trữ:** kiểu cột, charset, collation, kích thước thực tế sau migration.
- **Validation phía ứng dụng:** thuật toán đo độ dài khớp yêu cầu nghiệp vụ.
- **Xử lý lỗi:** mã lỗi rõ ràng khi input quá dài; không âm thầm cắt dữ liệu.
- **Quan sát production:** lưu log an toàn cho lỗi SQL truncation hoặc data validation mà không lộ dữ liệu nhạy cảm.

Nên để database tiếp tục bảo vệ constraint như lớp kiểm soát cuối cùng; validation ở ứng dụng giúp trả lỗi có ý nghĩa cho người dùng.

## 8. Chuỗi dài: `VARCHAR`, `TEXT`, `@Lob` và `CLOB`

Không phải chuỗi nào cũng phù hợp với `VARCHAR(255)`. Nội dung bài viết, mô tả sản phẩm dài hoặc tài liệu HTML có thể cần kiểu lưu trữ văn bản dung lượng lớn.

### 8.1. `@Lob` cho `String`

JPA chuẩn cung cấp `@Lob` để đánh dấu dữ liệu lớn:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;

@Entity
public class Article {

    @Id
    private Long id;

    @Column(name = "title", length = 160, nullable = false)
    private String title;

    @Lob
    @Column(name = "body")
    private String body;
}
~~~

Với `String`, `@Lob` thường biểu thị ánh xạ **character large object (CLOB)**. Loại SQL sinh ra, cách JDBC driver xử lý CLOB và cơ chế lưu trữ thực tế phụ thuộc provider/dialect/database.

Cần phân biệt:

- `String` + `@Column(length = 200)`: chuỗi ngắn với độ dài cột xác định.
- `String` + `@Lob`: nội dung ký tự có thể lớn, ánh xạ kiểu LOB.
- `String` + `@Column(columnDefinition = "TEXT")`: yêu cầu DDL kiểu `TEXT` cụ thể; phụ thuộc DB.
- `byte[]` + `@Lob`: dữ liệu nhị phân lớn, ngữ nghĩa BLOB thay vì văn bản.

Không nên tự động dùng `@Lob` cho tất cả chuỗi “hơi dài”. Các kiểu LOB có thể có đặc tính truy vấn, streaming, transaction, fetching và index khác với `VARCHAR`/`TEXT` thông thường.

### 8.2. Ví dụ về kiểu cột khác nhau

PostgreSQL có thể dùng:

~~~sql
CREATE TABLE article (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    body TEXT
);
~~~

MySQL có các kiểu `TEXT`, `MEDIUMTEXT`, `LONGTEXT` với giới hạn và yêu cầu riêng. SQL Server thường dùng `NVARCHAR(MAX)` cho chuỗi Unicode dài. Oracle có `CLOB` và `NCLOB`.

JPA có thể ánh xạ chuỗi lớn theo cách phù hợp từng dialect, nhưng nếu cần kiểu vật lý cụ thể, dùng migration và xác minh mapping với provider mục tiêu.

### 8.3. Hiệu năng khi làm việc với văn bản dài

- Tránh đọc nguyên nội dung lớn nếu màn hình chỉ cần tiêu đề và vài trường metadata.
- Các hint như `@Basic(fetch = FetchType.LAZY)` trên thuộc tính cơ bản có thể phụ thuộc khả năng hỗ trợ/enhancement của provider; không mặc định rằng chúng luôn trì hoãn tải `String` lớn.
- Truy vấn tìm kiếm toàn văn thường cần full-text index hoặc dịch vụ tìm kiếm chuyên dụng, thay vì `LIKE '%keyword%'` trên một cột lớn.
- Cẩn thận với giới hạn memory, streaming, log SQL và kích thước payload khi xử lý dữ liệu văn bản nhiều MB.

## 9. Quy trình thiết kế một thuộc tính chuỗi từ yêu cầu nghiệp vụ

Giả sử ứng dụng thương mại điện tử có trường “Tên sản phẩm” cho phép tiếng Việt, tiếng Nhật và emoji; nghiệp vụ yêu cầu không quá 80 **Unicode code points**.

### Bước 1: Định nghĩa hợp đồng dữ liệu

Ví dụ:

- Chuỗi không được rỗng hoặc chỉ gồm khoảng trắng.
- Giới hạn hiển thị theo code points: 80.
- Chấp nhận Unicode, bao gồm emoji ngoài BMP.
- Định nghĩa rõ có hay không chuẩn hóa NFC ở biên nhập dữ liệu.
- Tìm kiếm không phân biệt hoa/thường theo một collation phù hợp nhu cầu.

Mỗi quyết định phải được mô tả độc lập: giới hạn số code points không tự đặt collation, và charset không tự quyết định normalization.

### Bước 2: Chọn kiểu cột và charset

Nếu dùng PostgreSQL với database encoding UTF8:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL
);
~~~

Với PostgreSQL, giới hạn `VARCHAR(80)` theo số ký tự thường gần hơn với giới hạn code points so với `String.length()` trong Java. Tuy nhiên nếu ứng dụng muốn đếm graphemes hoặc áp dụng normalization riêng, cần thiết kế/kiểm tra bổ sung. Cũng cần lưu ý giới hạn byte ở những nơi khác trong kiến trúc.

Nếu chuyển sang SQL Server, `NVARCHAR(80)` không tương đương hoàn toàn với “80 code points” khi chứa emoji ngoài BMP. Có thể chọn kích thước lưu trữ rộng hơn theo yêu cầu và vẫn áp dụng giới hạn nghiệp vụ bằng validation.

### Bước 3: Khai báo entity nhất quán

~~~java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_name", length = 80, nullable = false)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

`length = 80` trong ví dụ tương ứng mục tiêu schema PostgreSQL đã nêu. Nếu sử dụng nhiều DB, cấu hình DDL có thể cần khác; đừng buộc metadata `@Column` đóng vai trò xác minh đơn vị đo Unicode của nghiệp vụ.

### Bước 4: Kiểm tra input tại API/service

~~~java
public static String validateProductName(String rawName) {
    if (rawName == null || rawName.isBlank()) {
        throw new IllegalArgumentException(
            "Product name must not be blank"
        );
    }

    String name = rawName.strip();
    int codePoints = name.codePointCount(0, name.length());

    if (codePoints > 80) {
        throw new IllegalArgumentException(
            "Product name must not exceed 80 Unicode code points"
        );
    }

    return name;
}
~~~

Ví dụ này chủ động chọn `strip()` loại bỏ khoảng trắng đầu/cuối theo quy tắc Java. Với ứng dụng cần bảo toàn chính xác khoảng trắng hoặc ngôn ngữ đặc thù, phải xem lại chính sách này; việc trim/normalize là quyết định nghiệp vụ, không phải yêu cầu chung của JPA.

### Bước 5: Lưu qua JPA và xử lý lỗi database

~~~java
@Transactional
public Product createProduct(String rawName) {
    String normalizedName = validateProductName(rawName);
    Product product = new Product(normalizedName);
    return entityManager.merge(product);
}
~~~

Đoạn trên minh họa lời gọi service trong môi trường có transaction manager như Spring; với entity mới, thao tác JPA điển hình là `entityManager.persist(product)`. Một phiên bản dùng `persist` sẽ rõ ý định hơn:

~~~java
@Transactional
public Product createProduct(String rawName) {
    Product product = new Product(validateProductName(rawName));
    entityManager.persist(product);
    return product;
}
~~~

`@Transactional` là annotation quản lý transaction của framework phù hợp, không phải annotation cốt lõi của JPA. Trong ứng dụng JPA thuần dùng resource-local transaction, cần điều phối `EntityTransaction` tương ứng.

Ngay cả khi đã validate, database vẫn có thể từ chối dữ liệu do schema không khớp, constraint khác hoặc thay đổi cấu hình. Service nên chuyển lỗi persistence thành phản hồi hữu ích, đồng thời giữ nguyên rollback transaction khi cần.

### Bước 6: Theo dõi schema qua migration

Không chỉ đổi `@Column(length = 80)` và giả định bảng thực tế sẽ cập nhật. Với schema đã triển khai, tạo migration tương ứng.

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE product
    ALTER COLUMN product_name TYPE VARCHAR(80);
~~~

Nếu đang thu hẹp độ dài, câu lệnh có thể thất bại vì dữ liệu hiện tại vượt giới hạn. Cần kiểm kê dữ liệu trước, quyết định chính sách xử lý và chạy migration ở quy trình quản trị phù hợp. Không tự cắt dữ liệu để migration chạy qua khi chưa có yêu cầu rõ ràng.

## 10. Các vấn đề với so sánh, tìm kiếm và chỉ mục chuỗi

### 10.1. `LIKE`, `LOWER` và collation

JPQL có thể truy vấn:

~~~java
List<Product> products = entityManager.createQuery(
    "SELECT p FROM Product p " +
    "WHERE LOWER(p.name) LIKE LOWER(:keyword)",
    Product.class
).setParameter("keyword", "%cà phê%")
 .getResultList();
~~~

Nhưng kết quả tìm kiếm tiếng Việt vẫn phụ thuộc cách DB xử lý `LOWER` và collation. Điều kiện trên không tự bảo đảm so khớp không phân biệt dấu hoặc tìm kiếm từ khóa đúng theo mọi locale. Việc bọc cột bằng function cũng có thể ảnh hưởng đến khả năng tận dụng index thông thường.

### 10.2. Ràng buộc UNIQUE trên văn bản

~~~java
@Column(name = "email", length = 254, unique = true)
private String email;
~~~

Đây là metadata unique constraint cho việc tạo schema. Khi DB thực thi UNIQUE, các quy tắc về chữ hoa/thường, dấu, Unicode normalization và trailing spaces có thể ảnh hưởng đến việc hai giá trị được xem là trùng nhau.

Nếu nghiệp vụ yêu cầu email không trùng khi bỏ qua chữ hoa/thường, hãy xác định rõ canonicalization, collation/index/constraint và cách migration triển khai. Không suy ra `unique = true` luôn thực hiện đúng một định nghĩa “hai chuỗi giống nhau” ở mọi database.

### 10.3. Chuỗi nhiều byte và index

Với UTF-8, một ký tự có thể chiếm nhiều byte. Index chứa cột văn bản phải tuân thủ giới hạn kích thước key/index của DB và cấu hình lưu trữ. Chẳng hạn, thay đổi một cột từ encoding 3 byte sang `utf8mb4` trên MySQL có thể tác động đến dung lượng index, nhất là trên những phiên bản/cấu hình cũ.

Các giải pháp có thể là điều chỉnh độ dài/index, sử dụng kiểu index thích hợp hoặc thiết kế khóa tìm kiếm riêng; không nên mặc định giảm `@Column(length)` là giải pháp đúng cho mọi trường hợp.

## 11. Những lỗi phổ biến và cách xác định đúng tầng

| Hiện tượng | Nguyên nhân cần xem xét | Hướng xử lý |
|---|---|---|
| Tiếng Việt thành dấu hỏi khi lưu | Charset/driver/kiểu cột không hỗ trợ đầy đủ Unicode hoặc dữ liệu đã hỏng trước đó | Kiểm tra input, JDBC connection, charset DB và kiểu cột; sửa ngay tầng gây mất dữ liệu |
| Emoji lưu thất bại trên MySQL | Charset/collation không hỗ trợ code point ngoài BMP | Kiểm tra sử dụng `utf8mb4` ở cột, bảng, DB và kết nối |
| `@Column(length = 100)` mà DB báo quá dài | Schema thực tế khác metadata, hoặc quy tắc độ dài DB khác Java | Kiểm tra DDL thực tế và đơn vị đo; đồng bộ migration và validation |
| `@Size(max = 10)` từ chối 10 emoji đơn | `String.length()` đếm 20 UTF-16 units | Xác định giới hạn theo code points/graphemes và dùng validator thích hợp |
| Kết quả tìm kiếm/sắp xếp tiếng Việt bất ngờ | Collation hoặc chức năng so sánh không đúng kỳ vọng | Chọn collation và quy tắc tìm kiếm theo nghiệp vụ |
| Hai tên trông giống nhau vẫn khác nhau | Unicode normalization, dấu, khoảng trắng hoặc ký tự ẩn | Xác định chính sách normalization và kiểm tra code points |
| UNIQUE coi `An` và `an` là trùng | Collation không phân biệt hoa/thường | Thiết kế quy tắc định danh/collation/constraint phù hợp |
| `@Lob` làm query chậm hoặc dùng nhiều memory | Tải văn bản lớn cùng entity, tối ưu fetch chưa phù hợp | Thiết kế truy vấn riêng, projection, streaming hoặc giải pháp lưu trữ thích hợp |
| Đổi `length` nhưng DB không thay đổi | JPA không chạy migration/schema update | Áp dụng migration độc lập và xác minh schema |
| `columnDefinition = "TEXT"` không chạy trên DB mới | SQL định nghĩa cột phụ thuộc vendor | Dùng mapping chuẩn hoặc migration theo dialect |
| Chuỗi bị cắt mất ký tự | Ứng dụng hoặc lớp tích hợp đã truncate; đôi khi DB/driver có chế độ xử lý riêng | Tìm chỗ cắt dữ liệu, tránh silent truncation và báo lỗi rõ ràng |

### Khi debug, bắt đầu từ dữ liệu thật

Ví dụ client gửi `"👍🏽"` và lỗi “value too long”:

1. Ở Java, `String.length()` là 4; `codePointCount` là 2; grapheme hiển thị thường là 1.
2. Ở UTF-8, chuỗi này có thể chiếm 8 byte.
3. Cột `VARCHAR(3)` trên PostgreSQL UTF-8 có thể cho phép hai code points; cột `VARCHAR2(3 BYTE)` trên Oracle không đủ byte.
4. Cột `NVARCHAR(3)` của SQL Server có thể không chứa đủ hai ký tự ngoài BMP vì cần 4 byte-pairs.
5. Kết luận lỗi phải dựa trên kiểu cột/charset/validator thực tế, không chỉ đọc annotation.

Trường hợp này cho thấy vì sao một con số độ dài thiếu đơn vị đo có thể gây lỗi khi ứng dụng hỗ trợ Unicode đầy đủ.

## 12. Bài tập thực hành

### Bài 1: Dự đoán độ dài trong Java

Cho đoạn code:

~~~java
String first = "Á";
String second = "A\u0301";
String third = "😀";

System.out.println(first.length());
System.out.println(second.length());
System.out.println(third.length());
~~~

**Đáp án:** `1`, `2`, `2`. `first` chứa một ký tự ghép sẵn, `second` chứa chữ A cùng dấu kết hợp và `third` là một code point ngoài BMP được biểu diễn bằng hai UTF-16 code units.

### Bài 2: Phân biệt mapping và validation

~~~java
@Size(max = 60)
@Column(length = 60, nullable = false)
private String title;
~~~

**Câu hỏi:** Có thể khẳng định chuỗi tối đa 60 Unicode code points sẽ luôn được chấp nhận trên mọi DB không?

**Trả lời:** Không. `@Size` đo độ dài `CharSequence`, thường là UTF-16 units đối với `String`; giới hạn cột thực tế còn tùy DB và encoding. `nullable = false` liên quan khả năng lưu `NULL`. Nếu nghiệp vụ nói rõ “60 Unicode code points”, cần validation theo code point và schema đáp ứng đơn vị đó.

### Bài 3: Chọn kiểu chuỗi theo hệ quản trị

Yêu cầu: lưu tên khách hàng tiếng Việt và emoji, tối đa 100 Unicode code points.

- **PostgreSQL UTF-8:** có thể thiết kế `VARCHAR(100)`, đồng thời kiểm tra ở tầng ứng dụng theo yêu cầu và xác minh schema.
- **MySQL:** cân nhắc `VARCHAR(100)` với `utf8mb4`, chọn collation thích hợp và chú ý giới hạn byte/index.
- **SQL Server:** cân nhắc `NVARCHAR` với độ dài lưu trữ đủ cho các code points ngoài BMP; đừng đồng nhất n với số code points.
- **Oracle:** chọn semantics CHAR/BYTE và kiểu Unicode phù hợp, kiểm tra giới hạn vật lý.

Không có một cách đặt `@Column(length = 100)` duy nhất chứng minh đúng cho cả bốn nền tảng mà không xét cách lưu trữ và validation.

### Bài 4: Phát hiện lỗi cấu hình

Một project dùng Hibernate với PostgreSQL UTF-8, trường `description` là chuỗi ngắn; người viết thêm `@Nationalized` vì nghĩ “JPA phải có annotation này mới lưu được tiếng Việt”.

**Nhận xét:** `@Nationalized` thuộc Hibernate, trong khi một cột PostgreSQL có encoding UTF-8 phù hợp đã có thể lưu tiếng Việt và emoji. Annotation vendor không thay thế cấu hình database; nếu yêu cầu chỉ là văn bản ngắn, có thể dùng `String` và `@Column` chuẩn. Việc cần `@Nationalized` nên dựa trên database/dialect thực tế.

### Bài 5: So sánh normalization

~~~java
String x = "\u00E9";
String y = "e\u0301";

System.out.println(x.equals(y));
~~~

**Đáp án:** `false` vì hai chuỗi chứa các dãy UTF-16 code units khác nhau. Nếu nghiệp vụ cần coi chúng tương đương, hãy định nghĩa rõ phép chuẩn hóa và áp dụng nhất quán tại vị trí thích hợp trong hệ thống, thay vì ngầm tin DB/JPA sẽ tự chuẩn hóa.

## 13. Nguyên tắc ghi nhớ

1. **`String` là kiểu Java; `@Column` là metadata ánh xạ; kiểu SQL thực tế mới quyết định cách lưu ở database.**
2. **`@Column(length = n)` chủ yếu hướng dẫn DDL**, không phải validation tự động hay thao tác cắt chuỗi.
3. **Unicode có nhiều đơn vị đo:** UTF-16 code units, code points, grapheme clusters và byte. Chọn đúng đơn vị theo yêu cầu nghiệp vụ.
4. **Java `String.length()` không đếm grapheme**; `codePointCount` đếm code points và cũng không đếm grapheme.
5. **Charset/encoding quyết định biểu diễn dữ liệu; collation quyết định so sánh/sắp xếp.** Unicode normalization là vấn đề riêng.
6. **Không đồng nhất `VARCHAR(n)` của mọi DB.** Đặc biệt lưu ý `NVARCHAR(n)` của SQL Server, semantics BYTE/CHAR của Oracle và `utf8mb4` của MySQL.
7. **`@Nationalized` là phần mở rộng Hibernate; `@Lob` là annotation JPA chuẩn cho dữ liệu lớn.** Chọn chúng theo nhu cầu và dialect cụ thể.
8. **Kết hợp validation nghiệp vụ với constraint database**, quản lý schema bằng migration và kiểm tra bằng dữ liệu Unicode đại diện trước khi triển khai.

Một thiết kế ánh xạ chuỗi tốt bắt đầu từ câu hỏi “người dùng được phép nhập những gì và dài bao nhiêu theo đơn vị nào?”, sau đó mới đến annotation JPA, kiểu cột SQL và cấu hình database để giữ nguyên dữ liệu đó một cách an toàn.
