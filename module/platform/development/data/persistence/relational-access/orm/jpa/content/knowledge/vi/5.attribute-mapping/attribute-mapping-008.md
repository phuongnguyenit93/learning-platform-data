# Ánh xạ dữ liệu nhị phân và nội dung lớn bằng Lob trong JPA

Trong ứng dụng Java dùng JPA để lưu dữ liệu quan hệ, không phải thuộc tính nào cũng là số, ngày hoặc chuỗi ngắn. Một hệ thống có thể phải lưu **ảnh đại diện, tài liệu PDF, tệp đính kèm, chữ ký số, mẫu hợp đồng dài hoặc nội dung HTML lớn**. Các giá trị này thường vượt phạm vi sử dụng thuận tiện của một cột `VARCHAR` hay `VARBINARY` thông thường.

**LOB** là viết tắt của *Large Object*: dữ liệu có dung lượng lớn được cơ sở dữ liệu quản lý. Jakarta Persistence cung cấp annotation **`@Lob`** để yêu cầu ánh xạ một thuộc tính persistent dưới dạng dữ liệu lớn. Việc chọn kiểu Java và cấu hình JPA quyết định dữ liệu mang ý nghĩa nhị phân hay ký tự; kiểu SQL thực tế còn phụ thuộc cơ sở dữ liệu, JDBC driver và JPA provider.

Bài học này tập trung vào **ánh xạ thuộc tính**: dùng `@Lob` khi nào, phân biệt BLOB và CLOB, lưu/đọc an toàn, giới hạn lazy loading, cũng như cân nhắc lưu trực tiếp dữ liệu lớn vào database hay lưu ở hệ thống tệp/object storage.

## 1. Hiểu BLOB, CLOB và dữ liệu lớn

### 1.1. BLOB là gì?

**BLOB** (*Binary Large Object*) là dạng lưu trữ lượng lớn **byte**. Ví dụ:

- Ảnh JPEG, PNG, WebP.
- Tệp PDF, ZIP, âm thanh, video.
- Dữ liệu nhị phân do một ứng dụng tạo ra.
- Các định dạng mà nội dung chính không nên được diễn giải thành văn bản theo charset.

Một BLOB có thể chứa chuỗi byte:

```text
PDF:
25 50 44 46 2D 31 2E 37 0A ...

PNG:
89 50 4E 47 0D 0A 1A 0A ...

Một byte có giá trị 0xFF vẫn là byte dữ liệu,
không bắt buộc là ký tự văn bản.
```

Mã hóa BLOB thành chuỗi bằng `new String(bytes)` mà không có quy tắc charset hoặc định dạng phù hợp có thể làm hỏng dữ liệu. Trong JPA, biểu diễn thường gặp nhất của BLOB ở mức ứng dụng là `byte[]`.

### 1.2. CLOB là gì?

**CLOB** (*Character Large Object*) là dạng lưu trữ lượng lớn **ký tự**. Ví dụ:

- Nội dung một bài viết dài.
- Văn bản hợp đồng.
- Tài liệu HTML, XML, JSON dài nếu ứng dụng chọn lưu chúng dưới dạng văn bản.
- Nhật ký văn bản, ghi chú dung lượng lớn.

Một CLOB có thể chứa:

```text
<h1>Điều khoản dịch vụ</h1>
<p>Nội dung hợp đồng kéo dài nhiều trang...</p>
```

Ở mức Java, biểu diễn đơn giản nhất của CLOB là `String`. CLOB diễn giải dữ liệu như ký tự theo cơ chế mã hóa và kiểu dữ liệu của database, trong khi BLOB lưu byte chưa mang ngữ nghĩa ký tự.

### 1.3. Bảng so sánh nhanh

| Tiêu chí | BLOB | CLOB |
|---|---|---|
| Loại dữ liệu | Nhị phân, chuỗi byte | Nội dung ký tự |
| Ví dụ | PDF, ảnh, ZIP, video | Văn bản dài, HTML, ghi chú dài |
| Kiểu Java thường dùng với JPA | `byte[]`, `Byte[]`, `java.sql.Blob` | `String`, `char[]`, `Character[]`, `java.sql.Clob` |
| Kiểu SQL biểu đạt ý định | `BLOB` hoặc kiểu LOB nhị phân tương đương | `CLOB` hoặc kiểu LOB ký tự tương đương |
| Đơn vị kích thước thường quan tâm | Byte | Ký tự (dung lượng thực tế theo encoding) |
| Cách khai thác | Đọc/ghi file, tải xuống, xử lý byte | Tìm kiếm, hiển thị và xử lý văn bản |
| Lưu ý | Không chuyển tùy ý sang String | Cần tính đến charset và hỗ trợ Unicode |

**Không nên suy ra tên kiểu cột SQL chỉ từ annotation.** Một số database có tên kiểu riêng như `BYTEA`, `TEXT`, `BLOB`, `CLOB` hoặc cơ chế *large object locator*. Hibernate và JDBC dialect có thể tạo kiểu DDL khác nhau cho cùng một mapping JPA. Việc kiểm tra schema thực tế của hệ quản trị đang dùng rất quan trọng khi triển khai.

## 2. Cơ chế ánh xạ của `@Lob`

Annotation JPA:

```java
import jakarta.persistence.Lob;
```

`@Lob` là một marker annotation: không có tham số như `size` hoặc `maxBytes`. JPA dùng **kiểu Java** để suy ra kiểu LOB phù hợp.

Ví dụ tối giản:

```java
@Entity
public class StoredDocument {
    @Id
    private Long id;

    @Lob
    private byte[] binaryContent; // Nội dung nhị phân lớn.

    @Lob
    private String textualContent; // Nội dung ký tự lớn.

    protected StoredDocument() {
    }
}
```

Tư duy ánh xạ:

```text
                 Entity Java
                     |
          +----------+-----------+
          |                      |
  @Lob byte[]             @Lob String
  binaryContent           textualContent
          |                      |
          v                      v
    BLOB semantics          CLOB semantics
          |                      |
          +----------+-----------+
                     |
          JDBC + JPA provider + dialect
                     |
                     v
       Kiểu cột cụ thể của database
```

Với Jakarta Persistence, `@Lob` chủ yếu làm rõ ý định **large object** cho một persistent basic attribute. Nó không phải công cụ mã hóa dữ liệu, không tự nén file, không xác thực MIME type và cũng không tự áp giới hạn dung lượng upload.

### 2.1. `@Lob` khác `@Column(length = ...)` như thế nào?

Xét hai thuộc tính:

```java
@Column(length = 500)
private String description;

@Lob
private String fullText;
```

- `description` mang ý nghĩa một chuỗi thông thường, giới hạn độ dài được khai báo cho mục đích ánh xạ/schema generation.
- `fullText` mang ý nghĩa nội dung ký tự lớn, được JPA ánh xạ theo ngữ nghĩa CLOB.
- `@Column(length = 500)` **không đồng nghĩa** `@Lob` và không đảm bảo mọi database tự chuyển sang kiểu CLOB khi vượt một ngưỡng cụ thể.
- `@Lob` **không định nghĩa dung lượng tối đa mà hệ thống cho phép nhận**. Giới hạn nghiệp vụ phải được áp dụng riêng.
- Tên kiểu SQL, cách lưu trữ ngoài dòng hay trong dòng, kích thước tối đa và hiệu năng phụ thuộc hệ quản trị.

Có thể dùng `@Column(nullable = false)` cùng `@Lob` để diễn đạt ràng buộc không null, nhưng khả năng hỗ trợ chi tiết của ràng buộc và kiểu cột vẫn cần kiểm tra ở database đích.

### 2.2. Khi nào không cần `@Lob`?

Không phải mọi `byte[]` đều là tệp lớn. Ví dụ:

```java
@Column(name = "checksum")
private byte[] checksum; // Một digest nhị phân cố định, nhỏ.
```

Một checksum SHA-256 có 32 byte, thường có thể lưu ở cột nhị phân cố định hoặc biến độ dài thông thường. Tương tự, tiêu đề ngắn hay mô tả vài trăm ký tự thường không cần CLOB.

Đặt `@Lob` cho tất cả thuộc tính nhị phân có thể gây lựa chọn kiểu SQL không phù hợp, đặc biệt khi một database/provider phân biệt mạnh giữa các loại nhị phân thường và large-object locator. Hãy chọn mapping dựa trên **dung lượng thực tế, cách truy vấn và chiến lược lưu trữ**.

## 3. Ví dụ đầy đủ: entity lưu tệp đính kèm bằng BLOB

Giả sử hệ thống cần lưu một tài liệu nhỏ bên trong database. Mỗi tệp có:

- ID để định danh.
- Tên gốc của tệp.
- MIME type, ví dụ `application/pdf`.
- Kích thước tính theo byte.
- Nội dung nhị phân.
- Thời điểm tạo.

Một entity JPA có thể được viết như sau:

```java
package com.example.persistence;

import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Arrays;

@Entity
@Table(name = "document_attachment")
public class DocumentAttachment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "file_name", nullable = false, length = 255)
    private String fileName;

    @Column(name = "media_type", nullable = false, length = 100)
    private String mediaType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "content", nullable = false)
    private byte[] content;

    protected DocumentAttachment() {
        // JPA.
    }

    public DocumentAttachment(
            String fileName,
            String mediaType,
            byte[] content
    ) {
        if (fileName == null || fileName.isBlank()) {
            throw new IllegalArgumentException("Tên tệp không hợp lệ");
        }
        if (mediaType == null || mediaType.isBlank()) {
            throw new IllegalArgumentException("Thiếu media type");
        }
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("Tệp rỗng");
        }

        this.fileName = fileName;
        this.mediaType = mediaType;
        this.content = Arrays.copyOf(content, content.length);
        this.sizeBytes = content.length;
        this.createdAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getFileName() {
        return fileName;
    }

    public String getMediaType() {
        return mediaType;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public byte[] copyContent() {
        return Arrays.copyOf(content, content.length);
    }
}
```

Các chi tiết có chủ đích:

1. **`@Lob` trên `byte[]`:** biểu thị nội dung lớn ở dạng binary.
2. **`@Basic(fetch = FetchType.LAZY)`:** yêu cầu trì hoãn tải thuộc tính nếu provider hỗ trợ. Đây là **gợi ý (hint)** cho basic attribute, không phải cam kết rằng byte array chắc chắn không được tải.
3. **Metadata ở các cột riêng:** danh sách tài liệu có thể lấy tên, loại và kích thước mà không cần truyền toàn bộ file.
4. **`sizeBytes` tính từ `content.length`:** dùng để hiển thị và kiểm soát dung lượng; giới hạn upload thực tế phải đặt tại biên nhận request trước khi có mảng byte quá lớn.
5. **Sao chép `byte[]` khi nhận và trả nội dung:** tránh code bên ngoài sửa mảng byte mà không đi qua cách quản lý trạng thái của entity. Điều này tốn thêm bộ nhớ, cần cân nhắc với file lớn.
6. **Không đưa `content` vào `toString()`, `equals()` hay `hashCode()`:** tránh tốn bộ nhớ/CPU, rò rỉ nội dung hoặc so sánh mảng dung lượng lớn.

Đây là một mô hình minh họa cho **tệp dung lượng vừa phải**. Nếu upload lên tới hàng trăm MB hoặc GB, `byte[]` thường không phải biểu diễn phù hợp vì phải nắm giữ toàn bộ nội dung trong bộ nhớ.

### 3.1. Field access hay property access?

Vì `@Id` của `DocumentAttachment` đặt trên **field `id`**, entity trong ví dụ dùng **field access** mặc định theo quy tắc JPA. Vì vậy `@Lob` và `@Basic` cũng nằm trên field `content`.

Nếu một entity chọn property access, mapping tương ứng phải đặt ở **getter**:

```java
private byte[] content;

@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "content")
public byte[] getContent() {
    return content;
}

public void setContent(byte[] content) {
    this.content = content;
}
```

Đoạn trên chỉ minh họa vị trí annotation. Để được coi là persistent property đúng cách, lớp còn cần cấu hình access type nhất quán và accessor phù hợp. Không trộn annotation giữa getter với field một cách ngẫu nhiên.

## 4. Ví dụ ánh xạ CLOB cho văn bản dài

Giả sử hệ thống có phần nội dung bài viết dài mà người quản trị có thể chỉnh sửa.

```java
package com.example.persistence;

import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "article")
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "body", nullable = false)
    private String body;

    @Version
    private long version;

    protected Article() {
    }

    public Article(String title, String body) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Thiếu tiêu đề");
        }
        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException("Thiếu nội dung");
        }
        this.title = title;
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getBody() {
        return body;
    }

    public void replaceBody(String newBody) {
        if (newBody == null || newBody.isBlank()) {
            throw new IllegalArgumentException("Nội dung rỗng");
        }
        this.body = newBody;
    }
}
```

Ở đây:

- `title` là chuỗi ngắn ánh xạ bình thường.
- `body` là `String` có `@Lob`, mang ngữ nghĩa nội dung ký tự lớn.
- `@Version` hỗ trợ optimistic locking, tránh ghi đè im lặng khi có cập nhật cạnh tranh theo cơ chế version của JPA.
- `@Basic(fetch = LAZY)` cũng chỉ là gợi ý với thuộc tính basic.

**CLOB không có nghĩa ứng dụng được miễn mọi giới hạn kích thước.** Khi nhận HTML hoặc văn bản lớn, ứng dụng vẫn cần giới hạn dung lượng, xác thực nội dung theo nghiệp vụ, bảo đảm charset, và thực hiện escape/sanitization đúng ngữ cảnh nếu đưa HTML do người dùng tạo lên giao diện.

### 4.1. Unicode và mã hóa ký tự

Với `String`, Java biểu diễn văn bản bằng Unicode. Khi dữ liệu đi qua JDBC, database và driver quyết định cách chuyển ký tự sang hệ mã/kiểu cột phù hợp. Không nên giả định số byte của chuỗi bằng số ký tự.

Ví dụ:

```java
String text = "Tiếng Việt có dấu";
int javaUnits = text.length(); // Số đơn vị UTF-16 của Java.

byte[] utf8 = text.getBytes(
    java.nio.charset.StandardCharsets.UTF_8
);
int utf8Bytes = utf8.length; // Số byte sau khi mã hóa UTF-8.
```

Hai giá trị không nhất thiết bằng nhau. Nếu API giới hạn theo byte, phải xác định byte theo charset giao tiếp; nếu giới hạn theo ký tự, phải xác định quy tắc đếm ký tự hoặc code point. Không dùng `String.length()` để khẳng định kích thước byte của CLOB trong database.

Một số hệ quản trị có kiểu LOB quốc gia riêng như NCLOB để xử lý tập ký tự quốc gia. Khả năng ánh xạ chi tiết các loại này phụ thuộc database, JDBC và provider; `@Lob String` không tự đảm bảo một tên cột SQL cụ thể cho mọi nơi.

## 5. Lược đồ SQL tương ứng

Một cách biểu đạt ý định lưu trữ trên hệ quản trị **có hỗ trợ** các tên kiểu `BLOB` và `CLOB`:

```sql
CREATE TABLE document_attachment (
    id          BIGINT PRIMARY KEY,
    file_name   VARCHAR(255) NOT NULL,
    media_type  VARCHAR(100) NOT NULL,
    size_bytes  BIGINT NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    content     BLOB NOT NULL
);

CREATE TABLE article (
    id      BIGINT PRIMARY KEY,
    title   VARCHAR(200) NOT NULL,
    body    CLOB NOT NULL,
    version BIGINT NOT NULL
);
```

Đây là **DDL khái niệm**, không phải script bảo đảm chạy nguyên vẹn trên mọi hệ quản trị: cách tạo cột auto-increment/identity, kiểu timestamp, BLOB/CLOB, độ dài và ràng buộc khác nhau giữa các database.

| Thành phần Java | Ý nghĩa ở mức mapping | Triển khai SQL có thể thay đổi |
|---|---|---|
| `@Lob byte[] content` | Lưu dữ liệu nhị phân lớn | BLOB, binary large object, locator hoặc kiểu riêng của DB |
| `@Lob String body` | Lưu ký tự lớn | CLOB, text large object hoặc kiểu văn bản lớn tương đương |
| `@Column(nullable = false)` | Yêu cầu non-null theo mapping/schema | DB constraint `NOT NULL` khi schema được tạo phù hợp |
| `@GeneratedValue` | Sinh giá trị định danh theo chiến lược | IDENTITY, SEQUENCE, TABLE hoặc cơ chế khác |
| `@Version` | Quản lý phiên bản phục vụ optimistic locking | Cột phiên bản được cập nhật/kiểm tra khi ghi |

Ví dụ đặc biệt cần chú ý: với PostgreSQL, cách Hibernate map `@Lob byte[]` trong một số tổ hợp phiên bản/dialect có thể gắn với cơ chế PostgreSQL large object và cột tham chiếu đối tượng lớn, **không tương đương mặc định với ý định dùng `bytea`**. Nếu muốn kiểm soát chính xác kiểu `bytea`, phải chọn mapping kiểu JDBC/provider thích hợp và kiểm tra dialect thực tế. Ngược lại, một số database khác dùng các biến thể `BLOB` hoặc `LONGBLOB`. Không nên copy DDL từ database này sang database khác mà không xét mapping.

### 5.1. Có nên dùng `@Column(columnDefinition = "...")`?

JPA cho phép khai báo:

```java
@Lob
@Column(name = "content", columnDefinition = "BLOB")
private byte[] content;
```

Nhưng `columnDefinition` là phần **DDL phụ thuộc database**. Một giá trị phù hợp với hệ quản trị A có thể không tồn tại ở hệ quản trị B. Khi dự án sử dụng Flyway/Liquibase hoặc tự quản schema, thường cần đồng bộ entity mapping với migration riêng của hệ quản trị đó. Không nên dùng `columnDefinition` như cách “ép” mọi JDBC driver xử lý BLOB theo cùng một API.

### 5.2. Một LOB có luôn nằm ngoài row không?

Không thể khẳng định. Database có thể lưu phần nhỏ inline, lưu phần lớn ngoài dòng hoặc dùng locator, page/chunk và cơ chế nội bộ khác. Những chi tiết này phụ thuộc engine, kích thước dữ liệu và cấu hình storage. JPA chỉ mô tả **ý định ánh xạ**, không quy định cấu trúc lưu trữ vật lý.

## 6. Luồng lưu tệp vào database

Với entity `DocumentAttachment`, luồng điển hình là:

```text
Client gửi multipart/form-data
          |
          v
Controller/API
          |
          | Xác thực quyền, giới hạn dung lượng,
          | kiểm tra loại tệp và đọc dữ liệu
          v
byte[] + metadata
          |
          v
new DocumentAttachment(...)
          |
          | EntityManager.persist(...)
          v
Persistence context
          |
          | flush + transaction commit
          v
Bảng document_attachment
          |
          +--> Metadata: tên, MIME, size, thời gian
          |
          +--> LOB: nội dung byte
```

Một ví dụ đơn giản khi dùng `EntityManager` với transaction do ứng dụng quản lý (*resource-local transaction*):

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

public Long store(
        EntityManager em,
        String fileName,
        String mediaType,
        byte[] data
) {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        DocumentAttachment attachment =
            new DocumentAttachment(fileName, mediaType, data);

        em.persist(attachment);
        em.flush(); // Bảo đảm đồng bộ trước khi đọc ID trong ví dụ.

        Long id = attachment.getId();
        tx.commit();
        return id;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Đoạn code giả định `EntityManager` được tạo và quản lý ở bên ngoài phương thức, không bị đóng giữa lúc chạy; chiến lược sinh ID `IDENTITY` được database/provider hỗ trợ. Trong ứng dụng Spring hoặc Jakarta EE dùng JTA/container-managed transaction, không gọi `em.getTransaction()` theo cách trên; tầng service/container quản lý transaction phù hợp.

**Điểm cần phân biệt:** `persist()` đưa entity vào persistence context; `flush()` đồng bộ thay đổi với database trong transaction; `commit()` xác nhận transaction. `flush` **không có nghĩa** dữ liệu đã được commit hay nhìn thấy từ transaction khác.

### 6.1. Kiểm tra đầu vào trước khi tạo `byte[]` lớn

Nếu controller gọi `MultipartFile.getBytes()` hoặc API tương tự, toàn bộ tệp có thể bị vật thể hóa thành mảng byte trong heap. Vì vậy cần áp giới hạn sớm ở:

- Reverse proxy/API gateway.
- Cấu hình multipart của HTTP framework.
- Logic validation theo loại tệp và nhu cầu nghiệp vụ.
- Chính sách timeout, tổng kích thước request và số lượng file trong một request.

Ví dụ kiểm tra kích thước tệp sau khi đọc chỉ là **lớp bảo vệ bổ sung**, không thay thế giới hạn tại đầu request:

```java
long maxFileSize = 10L * 1024 * 1024; // Ví dụ 10 MiB.

if (data.length > maxFileSize) {
    throw new IllegalArgumentException(
        "Tệp vượt giới hạn kích thước cho phép"
    );
}
```

Tương tự, trường `mediaType` do client cung cấp có thể sai hoặc bị giả mạo. Hệ thống cần kiểm tra định dạng thực tế nếu file type ảnh hưởng đến bảo mật hoặc quá trình xử lý.

## 7. Đọc và tải xuống LOB

Để đọc nội dung từ database:

```java
DocumentAttachment attachment =
    entityManager.find(DocumentAttachment.class, documentId);

if (attachment == null) {
    throw new IllegalArgumentException("Không tìm thấy tài liệu");
}

byte[] bytes = attachment.copyContent();
String fileName = attachment.getFileName();
String mediaType = attachment.getMediaType();
```

Khi entity đang managed và nội dung đã được tải, `copyContent()` trả một bản sao mảng byte. Nếu thuộc tính LOB chưa được tải và provider hỗ trợ lazy basic attribute, lần truy cập này có thể kích hoạt truy vấn tải LOB.

Để trả file qua HTTP, endpoint thường cần:

- Kiểm tra quyền truy cập đối với tài liệu được yêu cầu.
- Trả `Content-Type` hợp lệ, sau khi xác minh/kiểm soát MIME.
- Trả `Content-Disposition` phù hợp (thường `attachment` cho tệp tải xuống), với xử lý tên file an toàn.
- Cân nhắc `Content-Length`, caching, ETag, yêu cầu Range/partial content khi có nhu cầu.
- Cấu hình tránh browser diễn giải dữ liệu không tin cậy thành script hoặc HTML theo cách nguy hiểm.

Không nên để API mặc định serialize toàn bộ entity có `byte[]` thành JSON: một số serializer như Jackson biểu diễn `byte[]` dưới dạng **Base64**, khiến payload phình ra và ràng buộc client vào mô hình lưu trữ. Hãy tách endpoint **metadata** và endpoint **download nội dung** khi phù hợp.

## 8. Lazy loading với `@Lob`: hiểu đúng giới hạn

Một trong những hiểu nhầm phổ biến nhất là:

```java
@Lob
@Basic(fetch = FetchType.LAZY)
private byte[] content;
```

**không đảm bảo** mỗi truy vấn lấy entity sẽ bỏ qua cột `content`.

Trong JPA, `FetchType.EAGER` biểu thị yêu cầu tải eagerly; `FetchType.LAZY` với basic attribute là **gợi ý**. Provider có thể chọn tải ngay. Hibernate thường cần cơ chế bytecode enhancement hoặc điều kiện triển khai thích hợp để lazy-load từng basic attribute. Phiên bản provider và cấu hình dự án có thể khiến hành vi khác nhau.

### 8.1. Hệ quả nếu tin nhầm lazy loading

Giả sử có 1.000 hàng tài liệu, mỗi tệp 5 MiB. Nếu load full content cùng entity:

```text
1.000 x 5 MiB = khoảng 5.000 MiB dữ liệu nhị phân
```

Chỉ để hiển thị tên file, việc kéo hàng gigabyte dữ liệu từ database vào ứng dụng có thể gây trễ mạng, bộ nhớ tăng mạnh hoặc lỗi out-of-memory.

Kể cả khi provider hỗ trợ lazy LOB, đọc nội dung khi persistence context đã đóng có thể phát sinh lỗi lazy initialization, tùy provider và cấu hình. Việc giữ context mở đến tầng JSON serializer cũng không phải cách thay thế cho một chiến lược tải dữ liệu rõ ràng.

### 8.2. Projection metadata là cách giảm tải có chủ đích

Định nghĩa DTO chỉ chứa metadata:

```java
package com.example.api;

import java.time.Instant;

public record AttachmentSummary(
    Long id,
    String fileName,
    String mediaType,
    long sizeBytes,
    Instant createdAt
) { }
```

Truy vấn JPQL lấy đúng các trường cần dùng:

```java
List<AttachmentSummary> summaries =
    entityManager.createQuery(
        """
        select new com.example.api.AttachmentSummary(
            a.id,
            a.fileName,
            a.mediaType,
            a.sizeBytes,
            a.createdAt
        )
        from DocumentAttachment a
        order by a.createdAt desc
        """,
        AttachmentSummary.class
    ).getResultList();
```

Truy vấn này chọn các thuộc tính metadata, không chọn `a.content`. Vì vậy nó thể hiện ý định không tải LOB ngay trong câu truy vấn, không phụ thuộc vào việc provider có thực hiện basic lazy loading khi gọi `find()` hay không.

**Lưu ý:** nếu có quan hệ khác hoặc cơ chế fetch thêm dữ liệu, kế hoạch thực thi thực tế vẫn cần được xem xét khi triển khai; projection chỉ giải quyết rõ phần cột LOB được nêu ở ví dụ.

### 8.3. Tách metadata và content thành các entity/bảng

Với ứng dụng có nhiều truy vấn danh sách và rất ít lần tải file, có thể tách:

```text
document
+----+----------------+------------------+-----------+
| id | file_name      | media_type       | size      |
+----+----------------+------------------+-----------+
| 21 | invoice.pdf    | application/pdf  | 500000    |
+----+----------------+------------------+-----------+
                       1
                       |
                       | liên kết theo id/document_id
                       v
                       1
document_content
+-------------+----------------+
| document_id | content (LOB)  |
+-------------+----------------+
| 21          | [PDF bytes]    |
+-------------+----------------+
```

Khi đó việc truy vấn metadata không cần bảng chứa LOB. Có thể ánh xạ bằng entity riêng và quan hệ một-một, hoặc cấu trúc truy vấn thích hợp; hiệu quả lazy của quan hệ cũng cần xét provider, nhưng **ràng buộc truy vấn tại tầng schema** trở nên rõ hơn.

Giải pháp này đánh đổi thêm join hoặc truy vấn riêng lấy content khi thực sự cần. Nó đặc biệt đáng cân nhắc nếu bảng metadata được truy cập thường xuyên, còn LOB hiếm khi được đọc.

## 9. `byte[]`, `Blob`, `String` và `Clob`: khác nhau về bộ nhớ

JPA có thể ánh xạ nhiều kiểu Java thành LOB, nhưng chúng có đặc điểm truy cập khác nhau.

| Kiểu Java | Ý nghĩa | Thực tế khi truy cập |
|---|---|---|
| `byte[]` | Toàn bộ dữ liệu nhị phân trong mảng Java | Dễ sử dụng; thường vật thể hóa đầy đủ vào heap |
| `Byte[]` | Mảng wrapper byte | Có overhead lớn, khả năng hỗ trợ/hiệu quả phụ thuộc provider; thường không ưu tiên cho file lớn |
| `java.sql.Blob` | Giao diện JDBC với dữ liệu nhị phân lớn | Có thể dùng stream/locator theo driver, chịu ràng buộc vòng đời kết nối/transaction |
| `String` với `@Lob` | Toàn bộ nội dung ký tự | Dễ thao tác; thường vật thể hóa thành String |
| `char[]` | Nội dung ký tự dưới dạng mảng | Có thể dùng với mapping ký tự; phải xét tương thích |
| `java.sql.Clob` | Giao diện JDBC với dữ liệu ký tự lớn | Có thể đọc bằng character stream/locator, phụ thuộc driver |

### 9.1. Mảng byte dễ viết nhưng không tự streaming

Ví dụ:

```java
@Lob
private byte[] payload;
```

Đọc `payload` nghĩa là ứng dụng nhận một mảng chứa dữ liệu. Nếu file dài 100 MiB, mảng tiêu tốn khoảng 100 MiB bộ nhớ cho chính dữ liệu, chưa kể buffer của JDBC, ORM, serialization và các bản copy trung gian.

`@Lob` **không tự biến `byte[]` thành một luồng `InputStream`** và không tự loại bỏ nhu cầu đủ heap.

### 9.2. `Blob` và `Clob` có thể cung cấp giao diện dạng luồng

JDBC định nghĩa:

```java
import java.sql.Blob;
import java.sql.Clob;
```

Một entity có thể ánh xạ một property dạng:

```java
@Lob
private Blob fileContent;

@Lob
private Clob textContent;
```

Các API tương ứng bao gồm:

```java
try (java.io.InputStream stream =
         blob.getBinaryStream()) {
    // Đọc từng phần từ stream theo cơ chế driver.
}

try (java.io.Reader reader =
         clob.getCharacterStream()) {
    // Đọc từng phần ký tự từ reader.
}
```

Tuy nhiên, đây là **khả năng của JDBC interface**, không phải cam kết rằng mọi provider/database đều stream thực sự từ đĩa đến client mà không đệm trong bộ nhớ.

Cần lưu ý:

- Locator hoặc stream có thể chỉ hoạt động khi JDBC connection và transaction cần thiết vẫn còn mở.
- Driver có thể đọc trước hoặc buffer dữ liệu.
- Cách tạo `Blob`/`Clob` và gán vào entity có thể phụ thuộc provider. JDBC có `Connection.createBlob()`/`createClob()`, nhưng đưa locator này vào JPA entity không phải một giải pháp streaming portable cho mọi hệ quản trị.
- `Blob`/`Clob` có phương thức `free()` để giải phóng tài nguyên theo hợp đồng JDBC; việc ai sở hữu và khi nào giải phóng locator do ORM cấp cần phù hợp cơ chế của provider.
- Việc truyền trực tiếp một stream phản hồi HTTP sau khi transaction đã đóng có thể làm stream không còn đọc được.

Với file lớn và yêu cầu streaming chặt chẽ, cần cân nhắc driver/JDBC API phù hợp, quản lý transaction rõ ràng hoặc dùng object storage chuyên dụng.

## 10. Mỗi thao tác với LOB có ảnh hưởng gì đến transaction?

### 10.1. Lưu và cập nhật

Khi persist một entity có `@Lob`, nội dung LOB tham gia quá trình ghi vào database trong transaction. Một số database dùng các thao tác nội bộ riêng cho large object hoặc locator; điều đó có thể ảnh hưởng cách rollback, isolation và resource cleanup.

Nếu một tài liệu được thay bằng phiên bản mới:

```java
DocumentAttachment attachment =
    entityManager.find(DocumentAttachment.class, id);

// Cần thiết kế phương thức thay nội dung trong entity
// nếu nghiệp vụ cho phép cập nhật file.
```

Ứng dụng cần cân nhắc đây là **cập nhật tài liệu hiện hữu** hay **tạo một phiên bản mới**, vì dữ liệu file thường khó hợp nhất khi hai người sửa đồng thời. `@Version` giúp phát hiện ghi đè cạnh tranh theo mapping JPA nếu dùng đúng.

### 10.2. Chỉ gọi `flush()` chưa đủ

```java
entityManager.persist(attachment);
entityManager.flush();
```

Sau `flush()`, JDBC/DB có thể đã nhận lệnh ghi, nhưng transaction vẫn có thể rollback. Một client bên ngoài chưa chắc thấy nội dung file trước commit.

Với file đặt trong object storage còn metadata nằm ở database, không có transaction phân tán tự động chỉ nhờ JPA. Cần thiết kế cách xử lý thất bại giữa hai hệ thống, ví dụ dùng khóa lưu trữ tạm, trạng thái pending, retry và cleanup theo quy trình của ứng dụng.

### 10.3. Đọc nội dung và lifetime của persistence context

Khi đọc một thuộc tính LOB lazily hoặc dùng locator `Blob`/`Clob`, truy cập dữ liệu sau khi kết thúc transaction/session có thể lỗi hoặc làm ứng dụng phụ thuộc vào tính năng không portable.

Vì vậy tầng service nên kiểm soát rõ thời điểm đọc nội dung và truyền dữ liệu tới nơi tiêu thụ, tránh trả về một entity có lazy LOB rồi để tầng presentation vô tình tải dữ liệu khi context đã đóng.

## 11. Quyết định lưu LOB trong database hay lưu ngoài

Không phải hệ thống nào cũng nên đặt file trong database. Lựa chọn còn tùy kích thước, lưu lượng, backup, truy cập theo range và yêu cầu nhất quán.

| Tiêu chí | LOB trong relational database | File/object storage, database chỉ lưu metadata |
|---|---|---|
| **Tính nhất quán dữ liệu** | Metadata và content có thể nằm trong cùng transaction DB | Cần phối hợp trạng thái giữa database và storage |
| **Quản lý truy cập** | Có thể gắn quyền với truy vấn DB | Cần chính sách bucket/object, URL ký số, quyền ứng dụng |
| **Backup/restore** | File tăng dung lượng backup và thời gian restore DB | Có cơ chế sao lưu/lifecycle riêng cho object |
| **Khả năng mở rộng lưu lượng tải file** | Tốn I/O và kết nối database | Dịch vụ lưu trữ/CDN có thể phù hợp hơn |
| **Tìm kiếm theo metadata** | Thuận tiện qua bảng quan hệ | Vẫn thuận tiện nếu metadata ở DB |
| **Dung lượng file lớn** | Có thể làm tăng áp lực transaction, cache, WAL/redo/log | Thường thuận lợi hơn cho file lớn và streaming |
| **Triển khai ứng dụng nhỏ** | Đơn giản hơn vì ít hệ thống phụ trợ | Thêm thành phần quản lý storage |
| **Bảo trì/lifecycle** | DBA quản cả metadata và content | Cần xử lý object mồ côi và database reference lỗi |

**Thường cân nhắc lưu LOB trong DB khi** tệp không quá lớn, số lượng và lưu lượng có kiểm soát, yêu cầu transaction chung cao hoặc quy trình backup/restore gắn với dữ liệu nghiệp vụ.

**Thường cân nhắc object storage khi** có nhiều ảnh/video/tệp lớn, cần streaming/download số lượng lớn, cần CDN, versioning/lifecycle riêng hoặc chi phí mở rộng dung lượng DB trở nên đáng kể.

### 11.1. Mô hình lưu metadata trong JPA, content ở object storage

Một phương án:

```text
Entity DocumentMetadata
   id
   fileName
   mediaType
   sizeBytes
   storageKey  --------------------+
                                     |
                                     v
                             Object storage
                             object <storageKey>
                             [file bytes]
```

Entity khi đó có thể chỉ chứa:

```java
@Entity
public class DocumentMetadata {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String storageKey;

    @Column(nullable = false)
    private String mediaType;

    @Column(nullable = false)
    private long sizeBytes;

    protected DocumentMetadata() {
    }
}
```

Ở mô hình này, `storageKey` là tham chiếu tới object bên ngoài, **không phải `@Lob`**. Việc tải nội dung do client SDK/storage adapter đảm nhiệm. Dữ liệu metadata vẫn được JPA quản lý, nhưng file không nằm trong một cột SQL.

## 12. Bảo mật và vận hành dữ liệu lớn

Khi dùng `@Lob` cho file từ người dùng, cần xem đây là nội dung có thể không đáng tin cậy.

### 12.1. Xác thực loại và kích thước

- Giới hạn kích thước request/tệp ở tầng HTTP trước khi vật thể hóa thành `byte[]`.
- Xác thực định dạng thực tế khi cần; phần mở rộng và `Content-Type` do client cung cấp chỉ là thông tin đầu vào.
- Với hệ thống cần tiếp nhận tệp không tin cậy, cân nhắc quy trình quét mã độc phù hợp.
- Quy định loại tệp được phép và ngăn thực thi nội dung tải lên như mã ứng dụng.
- Không dùng tên gốc do người dùng gửi làm đường dẫn filesystem khi chưa chuẩn hóa/kiểm tra.

### 12.2. Tránh lộ nội dung qua log và JSON

Không nên viết:

```java
// Không nên với nội dung lớn/nhạy cảm:
log.info("attachment={}", attachment);
```

Nếu `toString()` đưa toàn bộ `byte[]`/String CLOB vào log, ứng dụng có thể lộ dữ liệu và tạo log khổng lồ. DTO metadata nên chỉ gồm ID, tên, loại, kích thước và thông tin được phép công bố.

Với CLOB chứa HTML người dùng soạn, lưu trữ dưới dạng CLOB **không đồng nghĩa** HTML an toàn để hiển thị. Cần chống XSS khi render; sanitize hay escape theo ngữ cảnh sử dụng.

### 12.3. Kiểm soát quyền và vòng đời

- API download phải kiểm tra người dùng có quyền trên **tài liệu cụ thể** hay không.
- Quyền đọc metadata và quyền tải nội dung có thể khác nhau.
- Xác định chính sách giữ, xóa, sao lưu và phục hồi tài liệu.
- Nội dung nhạy cảm có thể cần mã hóa ở rest và in transit; `@Lob` không cung cấp mã hóa tự động.
- Nếu lưu hash SHA-256 để kiểm tra integrity hoặc nhận diện trùng lặp, hash nên nằm ở cột metadata riêng; không xem hash là cơ chế chống giả mạo hay xác thực quyền truy cập.

## 13. Tối ưu hiệu năng khi làm việc với LOB

### 13.1. Không tải toàn bộ file khi chỉ cần danh sách

Một danh sách tài liệu thông thường chỉ cần:

```text
id | fileName | mediaType | sizeBytes | createdAt
```

Hãy dùng projection/DTO hoặc bảng metadata riêng. Tránh `SELECT *` khi bảng chứa cột LOB lớn nếu cơ sở dữ liệu và driver khiến LOB bị tải kèm.

### 13.2. Chú ý số bản sao bộ nhớ

Luồng xử lý có thể vô tình tạo nhiều bản copy:

```text
HTTP upload buffer
       |
       v
Multipart byte[]
       |
       v
Entity byte[] (defensive copy)
       |
       v
JDBC buffer
       |
       v
Database
```

Một file 50 MiB có thể chiếm hơn 50 MiB trong process vì có nhiều buffer và đối tượng trung gian. Nếu số request đồng thời cao, áp lực heap/GC tăng rất nhanh. Không dùng `@Lob` như bảo đảm rằng chỉ có một bản sao trong RAM.

### 13.3. Truy cập dữ liệu lớn theo đợt và giới hạn phân trang

Nếu cần duyệt nhiều tài liệu, phân trang theo metadata và xử lý có kiểm soát. Không dùng `findAll()` để lấy hàng chục nghìn entity chứa LOB rồi lặp serialize chúng.

### 13.4. Đánh chỉ mục metadata, không giả định index toàn bộ LOB

Các truy vấn phổ biến như tìm theo người sở hữu, trạng thái, ngày tạo, MIME hoặc checksum nên có cột và index thích hợp. Việc tìm trong nội dung CLOB/BLOB có thể cần full-text index, expression index, search engine hoặc cơ chế DB riêng, không mặc định có nhờ `@Lob`.

### 13.5. Chú ý backup và replication

LOB tăng kích thước database, log ghi (WAL/redo), replication traffic và thời gian backup/restore. Cần đánh giá theo lưu lượng thực tế, retention và khả năng phục hồi, nhất là khi tài liệu thường xuyên được sửa toàn bộ.

## 14. Các lỗi phổ biến với `@Lob`

### 14.1. “`@Lob` chắc chắn tạo cột `BLOB` trên mọi database”

**Sai.** JPA diễn đạt ngữ nghĩa LOB. Provider và dialect chọn kiểu JDBC/SQL phù hợp; database khác nhau có kiểu và cơ chế riêng. Với PostgreSQL, còn phải phân biệt `bytea` và large object API theo mapping sử dụng.

### 14.2. “Đã có `@Lob` thì không cần giới hạn upload”

**Sai.** Dung lượng tối đa nghiệp vụ, network request, heap và giới hạn database là những vấn đề riêng. Một request quá lớn vẫn có thể gây out-of-memory hoặc làm cạn tài nguyên.

### 14.3. “`@Basic(fetch = LAZY)` luôn giúp tránh đọc BLOB”

**Sai.** Đây là hint cho basic attribute. Một số provider/cấu hình vẫn tải cùng entity. Projection metadata và mô hình bảng tách riêng là những cách diễn đạt chiến lược đọc rõ ràng hơn.

### 14.4. “Có BLOB thì luôn stream được”

**Sai.** `@Lob byte[]` thường đòi hỏi toàn bộ mảng. Giao diện JDBC `Blob` có API stream, nhưng hiệu quả streaming và thời gian sống locator còn phụ thuộc driver/provider/transaction.

### 14.5. “Đổi `byte[]` thành `String` là tương đương”

**Sai.** `byte[]` mô tả dữ liệu nhị phân; `String` mô tả văn bản Unicode. Chuyển tùy tiện có thể làm mất byte và thay đổi ngữ nghĩa. Nếu dữ liệu thực sự là văn bản, phải biết charset; nếu là file nhị phân, giữ dưới dạng byte.

### 14.6. “Đổi `@Lob` qua `@Column(length = 1000000)` không ảnh hưởng schema”

**Sai.** Mapping thường và LOB có thể dùng kiểu JDBC/SQL khác nhau, cách lưu trữ và ràng buộc khác nhau. Thay đổi mapping trên hệ thống đang có dữ liệu cần một kế hoạch migration rõ ràng.

### 14.7. “Có `@Lob` là dữ liệu được nén và mã hóa”

**Sai.** JPA không tự nén hoặc mã hóa file. Database có thể có tính năng riêng, nhưng không được suy ra chỉ từ annotation.

### 14.8. “Một Java entity chứa LOB nên được trả trực tiếp qua JSON”

**Không nên giả định phù hợp.** Serializer có thể đọc thuộc tính lazy, encode byte thành Base64 và đưa cả file vào JSON; điều này ảnh hưởng hiệu năng và hợp đồng API. Nên dùng DTO metadata và endpoint download có kiểm soát.

### 14.9. “Có thể dùng LOB locator sau khi đóng mọi connection”

**Không bảo đảm.** Nhiều driver yêu cầu transaction/connection còn hiệu lực khi đọc `Blob`/`Clob`. Không để API trả stream phụ thuộc connection đã đóng.

### 14.10. “`@Column(length)` đảm bảo giới hạn byte tệp”

**Sai.** Độ dài cột và số byte của file không đồng nhất. Validation phải làm ở tầng request/service; ràng buộc database tùy kiểu cột và dialect.

## 15. Bài tập thực hành có hướng dẫn

### Bài 1: Chọn kiểu Java và annotation

Hệ thống lưu: (a) ảnh PNG, (b) mô tả 120 ký tự, (c) nội dung bài viết dài, (d) checksum SHA-256 gồm 32 byte.

Đề xuất:

| Dữ liệu | Mapping gợi ý | Vì sao |
|---|---|---|
| Ảnh PNG | `@Lob byte[]` hoặc storage ngoài | Dữ liệu nhị phân lớn, không phải văn bản |
| Mô tả 120 ký tự | `@Column(length = 120) String` | Chuỗi ngắn thông thường |
| Bài viết dài | `@Lob String` | Văn bản ký tự dài |
| SHA-256 (32 byte) | `byte[]` ở cột binary phù hợp | Dung lượng nhỏ, không nhất thiết dùng LOB |

Lưu ý rằng kích thước ảnh thực tế và tần suất tải file có thể khiến object storage phù hợp hơn việc lưu BLOB.

### Bài 2: Phát hiện nguy cơ khi lấy danh sách

Cho mapping:

```java
@Lob
private byte[] content;
```

Service đang làm:

```java
List<DocumentAttachment> attachments =
    entityManager.createQuery(
        "select a from DocumentAttachment a",
        DocumentAttachment.class
    ).getResultList();

return attachments;
```

**Vấn đề:** trả các entity đầy đủ có thể tải dữ liệu nhị phân lớn và để JSON serializer truy cập chúng; không kiểm soát rõ nội dung được gửi.

**Hướng xử lý:** tạo một DTO metadata chỉ chứa `id`, `fileName`, `mediaType`, `sizeBytes` và `createdAt`, lấy bằng projection như mục 8.2; chỉ đọc content khi có request download cụ thể và đã kiểm tra quyền.

### Bài 3: Đọc schema có kiểu khác mong đợi

Trong môi trường A, mapping `@Lob byte[]` hoạt động với cột BLOB. Khi chuyển sang PostgreSQL, migration tạo cột `bytea` nhưng Hibernate lại tìm mapping theo cơ chế large object khác.

**Câu hỏi:** Có nên đổi ngay tên cột thành `BLOB`?

**Hướng xử lý:** kiểm tra phiên bản Hibernate/JPA, dialect, JDBC type thực tế và migration/schema hiện tại. Chọn mapping phù hợp với kiểu cột mong muốn của PostgreSQL; có thể cần cấu hình kiểu JDBC chuyên biệt cho provider. Không giả định cùng annotation có cùng DDL trên mọi DB.

### Bài 4: So sánh bộ nhớ khi đọc tệp

Hệ thống có 200 file PDF, mỗi file 8 MiB. Nếu tải toàn bộ vào `byte[]` cùng lúc:

```text
200 × 8 MiB = 1.600 MiB dữ liệu thô
```

Đây mới là kích thước mảng dữ liệu, chưa kể overhead và copy. **Hướng xử lý:** truy vấn metadata, phân trang, tải file theo yêu cầu, hoặc đổi sang lưu trữ/streaming phù hợp quy mô.

### Bài 5: Xử lý hai người cập nhật CLOB

Hai người cùng sửa nội dung `Article.body`. Người A lưu trước; người B lưu bản cũ sau đó.

**Hướng xử lý:** dùng `@Version` để phát hiện optimistic locking conflict, yêu cầu người B xử lý xung đột, tải lại hoặc tạo phiên bản tài liệu mới theo nghiệp vụ. CLOB không tự giải quyết xung đột đồng thời.

### Bài 6: Phân biệt CLOB với lưu JSON có cấu trúc

Ứng dụng lưu JSON dài dưới dạng `@Lob String` nhưng thường xuyên truy vấn theo trường `$.customerId` bên trong JSON.

**Hướng xử lý:** Nếu cần truy vấn cấu trúc, cân nhắc kiểu JSON native hoặc tách dữ liệu cần index thành cột quan hệ tùy database/provider. `@Lob String` đơn thuần chỉ mô tả văn bản lớn và không tự cung cấp JSON index hay validation nội dung JSON.

## 16. Ghi nhớ khi sử dụng `@Lob`

| Câu hỏi thiết kế | Điều cần xác định |
|---|---|
| Dữ liệu là byte hay văn bản? | `byte[]`/`Blob` cho binary; `String`/`Clob` cho text |
| Có cần LOB không? | Kích thước, tần suất truy cập, mục đích lưu trữ |
| Database đích là gì? | Dialect, JDBC driver, kiểu SQL thực tế và migration |
| Có dùng lazy loading? | `@Basic(fetch = LAZY)` chỉ là hint; kiểm soát projection |
| Tệp có thể rất lớn? | Tránh vật thể hóa `byte[]` quá lớn; cân nhắc streaming/storage ngoài |
| Danh sách có cần nội dung file? | Thường chỉ lấy metadata; nội dung qua request riêng |
| Đầu vào có đáng tin? | Validation size/type, quyền truy cập, xử lý an toàn |
| Giao dịch có bao trùm content không? | DB LOB và transaction; object storage cần điều phối riêng |
| Có nhiều người sửa cùng tài liệu? | Versioning/optimistic locking và quy tắc xử lý xung đột |
| Cần tìm kiếm bên trong nội dung? | Chọn cơ chế full-text/index riêng; `@Lob` không đủ |

**Kết luận:** `@Lob` là công cụ mô tả **một thuộc tính persistent chứa dữ liệu lớn** trong JPA. `@Lob byte[]` phù hợp với nội dung nhị phân; `@Lob String` phù hợp với văn bản dài. Tuy nhiên, annotation chỉ là một phần của thiết kế: loại cột SQL do database/provider quyết định, tải lazy không luôn được bảo đảm và chiến lược lưu trữ ảnh hưởng trực tiếp đến bộ nhớ, truy vấn, transaction, backup và API. Khi dữ liệu lớn, hãy xác định rõ **cần lưu gì, tải lúc nào, giới hạn bao nhiêu và ai có quyền truy cập** trước khi lựa chọn BLOB/CLOB trong database hoặc object storage bên ngoài.
