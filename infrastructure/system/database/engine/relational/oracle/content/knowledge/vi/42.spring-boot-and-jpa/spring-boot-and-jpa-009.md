# Ánh xạ LOB, thời gian, enum và converter

Trong ứng dụng Spring Boot dùng Spring Data JPA và Oracle Database, ánh xạ entity không chỉ là đặt `@Column` lên từng thuộc tính. Một số kiểu dữ liệu có cách lưu trữ và vòng đời đặc biệt: nội dung lớn cần CLOB/BLOB, thời gian phải giữ đúng ý nghĩa ngày giờ và múi giờ, enum cần được lưu theo một quy ước ổn định, còn kiểu dữ liệu nghiệp vụ riêng cần được chuyển đổi sang kiểu SQL mà database hiểu được.

Nếu chọn mapping không phù hợp, ứng dụng có thể đọc sai thời gian khi đổi timezone, không tương thích khi đổi tên enum, tải toàn bộ LOB vào heap hoặc tạo schema khác với yêu cầu Oracle. Bài học này trình bày cách chọn mapping, cách cấu hình JPA/Hibernate, các giới hạn cần kiểm tra và ví dụ có thể áp dụng trong dự án.

Các ví dụ dùng `jakarta.persistence` phù hợp Spring Boot 3 trở lên. Với Spring Boot 2, các import JPA thường dùng namespace `javax.persistence`; cần giữ đồng bộ namespace với phiên bản Spring/Hibernate của dự án.

## 1. Bức tranh chung về mapping JPA và Oracle

JPA định nghĩa cách ánh xạ thuộc tính Java sang cột database thông qua annotation hoặc XML. Hibernate là một JPA provider phổ biến trong Spring Boot; Oracle JDBC driver đảm nhiệm việc truyền giá trị giữa Hibernate và Oracle Database.

```text
Java entity attribute
        |
        v
JPA mapping metadata
        |
        v
Hibernate type / converter
        |
        v
Oracle JDBC binding
        |
        v
Oracle SQL data type
```

Mỗi lớp có vai trò riêng:

- **JPA annotation:** mô tả ý nghĩa thuộc tính, ví dụ `@Lob`, `@Enumerated`, `@Convert`, `@Column`.
- **Hibernate:** quyết định kiểu JDBC, cách đọc/ghi, lazy loading, timezone storage và một số extension riêng.
- **Oracle JDBC:** chuyển giá trị Java/JDBC sang Oracle SQL và ngược lại.
- **Oracle Database:** lưu giá trị theo kiểu cột thật như `CLOB`, `BLOB`, `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` hoặc `NUMBER`.

Không phải annotation nào cũng buộc schema có một kiểu cột duy nhất. Kết quả DDL còn phụ thuộc dialect, phiên bản Hibernate, cấu hình schema generation và DDL migration do dự án quản lý. Trong môi trường production, nên dùng Flyway hoặc Liquibase để quản lý schema và xác nhận DDL thực tế trên Oracle.

## 2. Ánh xạ LOB: CLOB, NCLOB và BLOB

### 2.1. LOB là gì?

LOB (Large Object) dùng để lưu nội dung lớn hơn kiểu chuỗi hoặc binary thông thường phù hợp. Oracle có các kiểu LOB chính:

| Kiểu Oracle | Nội dung | Ví dụ |
|---|---|---|
| `CLOB` | Character Large Object, văn bản theo database character set. | Nội dung bài viết, mô tả dài, tài liệu văn bản. |
| `NCLOB` | National Character Large Object, văn bản theo national character set. | Nội dung Unicode cần dùng national character set theo thiết kế. |
| `BLOB` | Binary Large Object. | Ảnh, PDF, file đính kèm, nội dung nhị phân. |
| `BFILE` | Locator tới file nhị phân bên ngoài database, ở chế độ chỉ đọc từ Oracle. | File trên filesystem server được Oracle truy cập qua DIRECTORY. |

Trong ứng dụng nghiệp vụ, `CLOB` và `BLOB` thường là hai kiểu cần quan tâm nhất. `BFILE` có mô hình lưu trữ và quyền truy cập riêng; không nên coi nó như BLOB thông thường vì nội dung file không được lưu trực tiếp trong segment database.

### 2.2. Dùng @Lob với String và byte[]

JPA cung cấp `@Lob` để đánh dấu thuộc tính được lưu bằng large object. Các mapping phổ biến:

| Thuộc tính Java | Annotation | Kiểu Oracle thường dùng |
|---|---|---|
| `String` | `@Lob` | `CLOB` |
| `byte[]` | `@Lob` | `BLOB` |

Ví dụ entity:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "DOCUMENTS")
public class DocumentEntity {
    @Id
    @Column(name = "DOCUMENT_ID")
    private Long id;

    @Column(name = "TITLE", nullable = false, length = 200)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "CONTENT")
    private String content;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "ATTACHMENT")
    private byte[] attachment;
}
```

Hibernate thường ánh xạ `content` thành CLOB và `attachment` thành BLOB trên Oracle. Kiểu cột chính xác cần được xác nhận bằng DDL thực tế hoặc metadata database. Không cần đặt `columnDefinition = "CLOB"` nếu dialect đã tạo đúng kiểu; `columnDefinition` gắn entity với cú pháp DDL cụ thể và có thể làm giảm tính di động.

`@Lob` xác định loại dữ liệu lớn; `@Column` vẫn có thể dùng để đặt tên, nullable và các thuộc tính cột phù hợp. `length` không phải cách giới hạn kích thước LOB theo nghĩa giống `VARCHAR2`.

### 2.3. CLOB và NCLOB

`CLOB` dùng database character set. Trong database Oracle hiện đại, `AL32UTF8` là lựa chọn phổ biến để lưu Unicode trong `VARCHAR2`/`CLOB`. `NCLOB` dùng national character set, thường là `AL16UTF16` hoặc cấu hình national character set khác được Oracle hỗ trợ.

Nếu dự án cần `NCLOB`, Hibernate có extension `@Nationalized`:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;
import org.hibernate.annotations.Nationalized;

@Lob
@Nationalized
@Basic(fetch = FetchType.LAZY)
private String multilingualContent;
```

`@Nationalized` là annotation riêng của Hibernate, không phải annotation chuẩn JPA. Hãy xác nhận dialect và DDL để bảo đảm cột đích là NCLOB. Nếu database đã dùng `AL32UTF8` và yêu cầu nghiệp vụ không cần national character type, CLOB thường là lựa chọn đơn giản hơn. Không dùng NCLOB chỉ vì nội dung có tiếng Việt hoặc Unicode; cần dựa trên character set và tiêu chuẩn schema của hệ thống.

### 2.4. Khi nào dùng CLOB thay vì VARCHAR2?

Chọn kiểu cột theo kích thước, cách truy cập và quy tắc nghiệp vụ:

- Dùng `VARCHAR2` cho chuỗi có giới hạn rõ ràng như tên, mã, email hoặc trạng thái.
- Dùng `CLOB` cho nội dung văn bản lớn, có thể vượt giới hạn kích thước cột chuỗi thông thường.
- Dùng `BLOB` cho nội dung nhị phân.
- Không chuyển mọi chuỗi thành CLOB; LOB có chi phí lưu trữ và truy cập riêng, đồng thời có thể hạn chế một số phép so sánh, index hoặc thao tác SQL thông thường.

Nếu nội dung chỉ dài vài trăm ký tự, `VARCHAR2` thường dễ truy vấn và lập chỉ mục hơn. Nếu cần tìm kiếm toàn văn, cân nhắc Oracle Text hoặc kiến trúc tìm kiếm chuyên dụng thay vì cố dùng `LIKE` trên mọi LOB.

### 2.5. Lazy loading đối với LOB

Có thể khai báo:

```java
@Lob
@Basic(fetch = FetchType.LAZY)
private String content;
```

Tuy nhiên, theo JPA, `LAZY` đối với basic attribute là một hint. Provider không bắt buộc phải trì hoãn tải trong mọi cấu hình. Hibernate thường cần bytecode enhancement hoặc cấu hình phù hợp để lazy-load basic field đáng tin cậy. Nếu không, khi đọc entity, nội dung LOB có thể vẫn được tải cùng entity.

Một số lưu ý:

- Kiểm tra SQL thực tế và thời điểm LOB được tải; không suy ra lazy chỉ từ annotation.
- Nếu dùng bytecode enhancement, cấu hình plugin/build phải nhất quán giữa local, CI và production.
- Khi entity detached hoặc transaction đã đóng, truy cập thuộc tính lazy có thể gây `LazyInitializationException` hoặc lỗi tương đương.
- Không trả entity chứa LOB lớn trực tiếp qua REST nếu API chỉ cần metadata.
- Dùng DTO/projection để truy vấn riêng tiêu đề, loại file, kích thước và thời điểm tạo.

Ví dụ projection không lấy nội dung:

```java
public interface DocumentSummary {
    Long getId();
    String getTitle();
}

public interface DocumentRepository
        extends org.springframework.data.jpa.repository.JpaRepository<DocumentEntity, Long> {

    java.util.List<DocumentSummary> findAllProjectedBy();
}
```

Với màn hình danh sách, chỉ tải metadata. Khi người dùng mở tài liệu, dùng truy vấn riêng để lấy LOB.

### 2.6. Stream LOB và quản lý bộ nhớ

Nếu tải một BLOB lớn thành `byte[]`, toàn bộ nội dung sẽ nằm trong heap. Điều này có thể gây áp lực GC hoặc `OutOfMemoryError` khi nhiều request tải file cùng lúc. Với file lớn, cân nhắc stream qua JDBC hoặc API của provider.

Ví dụ JDBC đọc BLOB theo stream trong phạm vi connection/cursor:

```java
String sql = "SELECT ATTACHMENT FROM DOCUMENTS WHERE DOCUMENT_ID = ?";

try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(sql)) {
    statement.setLong(1, documentId);

    try (var resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            try (var input = resultSet.getBinaryStream("ATTACHMENT")) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    outputStream.write(buffer, 0, count);
                }
            }
        }
    }
}
```

`outputStream` ở ví dụ là stream đích do tầng gọi quản lý. Việc đọc stream thường yêu cầu ResultSet và connection còn mở; không trả stream ra khỏi phạm vi rồi đóng connection ngay. Nếu dùng Spring MVC/WebFlux, cần thiết kế transaction và lifecycle của response stream sao cho database resource được đóng sau khi truyền xong.

Với ghi LOB lớn, JDBC có `setBinaryStream()` và `setCharacterStream()`. Dùng stream giúp tránh tạo bản sao toàn bộ file trong heap, nhưng vẫn cần đo kích thước buffer, thời gian giữ connection và giới hạn upload.

### 2.7. Cập nhật và xóa LOB

JPA có thể cập nhật thuộc tính LOB như thuộc tính thông thường:

```java
document.setContent(newContent);
documentRepository.save(document);
```

Với LOB lớn, cần chú ý dirty checking có thể khiến Hibernate phải so sánh hoặc ghi lại nội dung. Không tải rồi ghi lại LOB nếu chỉ thay đổi tiêu đề. Tách thao tác cập nhật metadata và nội dung khi workload cần tối ưu.

Khi xóa entity, LOB thuộc sở hữu của hàng thường được quản lý cùng vòng đời hàng. Nếu LOB được lưu ngoài database bằng object storage, cần thiết kế quy trình xóa file và xử lý orphan riêng; transaction Oracle không tự xóa object trên storage bên ngoài.

## 3. Ánh xạ ngày giờ và múi giờ

### 3.1. Phân biệt kiểu thời gian Java

Không phải mọi giá trị thời gian đều biểu diễn cùng một khái niệm. Chọn kiểu Java theo ý nghĩa nghiệp vụ trước khi chọn kiểu cột:

| Kiểu Java | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `LocalDate` | Ngày lịch, không có giờ và timezone. | Ngày sinh, ngày hóa đơn, ngày hiệu lực theo lịch. |
| `LocalTime` | Giờ trong ngày, không có ngày và timezone. | Giờ mở cửa, giờ hẹn lặp lại. |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương, không có timezone/offset. | Thời điểm nghiệp vụ được định nghĩa theo giờ địa phương cố định. |
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC. | Thời điểm tạo event, audit timestamp, thời điểm giao dịch. |
| `OffsetDateTime` | Ngày giờ kèm UTC offset. | Thời điểm cần giữ offset đã biết. |
| `ZonedDateTime` | Ngày giờ cùng `ZoneId` như `Asia/Ho_Chi_Minh`. | Lịch theo vùng địa lý và quy tắc DST. |
| `Duration` | Khoảng thời gian theo giây/nanosecond. | Thời lượng xử lý, timeout, thời gian trôi qua. |
| `Period` | Khoảng theo năm/tháng/ngày lịch. | Tuổi, kỳ hạn theo tháng hoặc lịch. |

Không dùng `LocalDateTime` cho một sự kiện toàn cầu nếu hệ thống cần xác định chính xác instant. `2026-11-14 09:00` không cho biết đó là UTC, giờ Việt Nam hay giờ của một vùng khác. Ngược lại, không cần lưu timezone cho ngày sinh nếu nghiệp vụ chỉ quan tâm ngày lịch.

### 3.2. Các kiểu thời gian Oracle

Oracle có các kiểu quan trọng:

| Kiểu Oracle | Đặc điểm |
|---|---|
| `DATE` | Lưu năm, tháng, ngày, giờ, phút và giây; không có fractional seconds và timezone. |
| `TIMESTAMP(p)` | Như DATE nhưng có fractional seconds với precision `p` (0–9). |
| `TIMESTAMP(p) WITH TIME ZONE` | Lưu timestamp cùng thông tin timezone/offset theo khả năng của kiểu Oracle. |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Chuẩn hóa theo database timezone khi lưu và hiển thị theo session timezone khi đọc; không giữ nguyên timezone ban đầu của client. |
| `INTERVAL YEAR TO MONTH` | Khoảng thời gian theo năm và tháng. |
| `INTERVAL DAY TO SECOND` | Khoảng theo ngày, giờ, phút, giây và fractional seconds. |

Oracle không có kiểu SQL `TIME` độc lập giống một số hệ quản trị khác. Nếu dùng `LocalTime`, Hibernate phải ánh xạ sang kiểu được dialect hỗ trợ; cần kiểm tra DDL và round-trip thực tế.

Một khác biệt quan trọng: Oracle `DATE` có phần giờ tới giây. Không nên hiểu `DATE` của Oracle là chỉ có ngày như một số kiểu SQL DATE khác.

### 3.3. Mapping java.time phổ biến

Hibernate hiện đại hỗ trợ các kiểu `java.time` và thường ánh xạ như sau, tùy dialect/version/configuration:

| Java | Kiểu SQL thường gặp trên Oracle | Ghi chú |
|---|---|---|
| `LocalDate` | `DATE` | Chỉ có ngày theo ý nghĩa Java. |
| `LocalTime` | Kiểu timestamp/time phù hợp dialect | Oracle không có SQL TIME riêng; kiểm tra schema và precision. |
| `LocalDateTime` | `TIMESTAMP` | Không mang timezone. |
| `Instant` | `TIMESTAMP` chuẩn hóa UTC hoặc kiểu timezone tùy provider/configuration | Phải xác nhận chiến lược timezone storage. |
| `OffsetDateTime` | Thường là `TIMESTAMP WITH TIME ZONE` khi dùng native storage | Kiểm tra driver/dialect và cấu hình Hibernate. |
| `ZonedDateTime` | Phụ thuộc timezone storage strategy | Nếu cần giữ nguyên ZoneId, phải xác định rõ cách lưu. |

Đây là mapping phổ biến chứ không phải cam kết DDL cho mọi phiên bản. Hibernate 5 và 6, Oracle dialect, JDBC driver và thuộc tính `hibernate.timezone.default_storage` có thể làm thay đổi cách lưu. Hãy kiểm tra DDL do migration quản lý và thử ghi/đọc lại với timezone khác nhau.

### 3.4. Ví dụ entity dùng java.time

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

@Entity
@Table(name = "APPOINTMENTS")
public class AppointmentEntity {
    @Id
    @Column(name = "APPOINTMENT_ID")
    private Long id;

    @Column(name = "APPOINTMENT_DATE", nullable = false)
    private LocalDate appointmentDate;

    @Column(name = "LOCAL_START_TIME", nullable = false)
    private LocalDateTime localStartTime;

    @Column(name = "CREATED_AT", nullable = false)
    private Instant createdAt;

    @Column(name = "CONFIRMED_AT")
    private OffsetDateTime confirmedAt;
}
```

Trong ví dụ, `appointmentDate` là ngày lịch; `localStartTime` là giờ địa phương không có offset; `createdAt` là một instant; `confirmedAt` giữ offset đã biết. Tên thuộc tính không tự xác định timezone. Hợp đồng nghiệp vụ và cấu hình Hibernate mới quyết định cách lưu.

### 3.5. Chọn LocalDate, LocalDateTime hay Instant

**Dùng LocalDate** khi giá trị là ngày lịch và không có thời điểm trong ngày:

```java
private LocalDate invoiceDate;
```

**Dùng LocalDateTime** khi nghiệp vụ thực sự định nghĩa một thời gian địa phương không gắn với vùng timezone, ví dụ giờ mở cửa theo đồng hồ tại một địa điểm đã biết. Nếu hệ thống phục vụ nhiều vùng địa lý, cần lưu thêm `ZoneId` hoặc dùng một kiểu khác.

**Dùng Instant** cho timestamp kỹ thuật và sự kiện cần so sánh trên timeline:

```java
private Instant createdAt;
private Instant processedAt;
```

**Dùng OffsetDateTime** khi cần giữ offset đi kèm giá trị. Nếu cần giữ tên vùng như `Asia/Ho_Chi_Minh`, chỉ lưu offset có thể chưa đủ vì offset không chứa toàn bộ quy tắc vùng và lịch sử DST.

### 3.6. TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE

Hai kiểu Oracle này không tương đương:

- `TIMESTAMP WITH TIME ZONE` lưu timestamp kèm offset hoặc vùng timezone theo cú pháp/khả năng Oracle. Nó phù hợp khi cần bảo toàn thông tin timezone của giá trị.
- `TIMESTAMP WITH LOCAL TIME ZONE` chuẩn hóa thời điểm theo database timezone khi lưu và chuyển sang session timezone khi truy xuất. Kiểu này không giữ nguyên timezone/offset ban đầu mà client gửi.

Ví dụ một thời điểm được ghi từ session ở UTC+07 có thể hiển thị khác khi truy vấn từ session UTC. Đây là hành vi theo thiết kế, không nhất thiết là mất dữ liệu. Nhưng nếu ứng dụng hiểu giá trị trả về là giờ gốc của người dùng, kết quả có thể bị diễn giải sai.

Với audit/event timestamp, thường nên thống nhất lưu một instant UTC và quy định cách chuyển đổi ở tầng ứng dụng. Với lịch theo vùng địa lý, cần giữ `ZoneId` nếu nghiệp vụ phụ thuộc quy tắc vùng. Với giờ địa phương không có timezone, dùng LocalDateTime nhưng phải xác định vùng áp dụng ở một nơi khác.

### 3.7. Hibernate timezone storage

Hibernate có chiến lược lưu trữ các kiểu có timezone. Tùy phiên bản, có thể cấu hình thuộc tính như:

```properties
# Ví dụ cấu hình Hibernate 6; xác nhận theo phiên bản provider.
spring.jpa.properties.hibernate.timezone.default_storage=NATIVE
```

Các chiến lược thường gặp gồm:

- `NATIVE`: dùng kiểu SQL có timezone nếu dialect hỗ trợ.
- `NORMALIZE`: chuẩn hóa thời điểm và lưu không giữ nguyên offset ban đầu.
- `COLUMN`: lưu timezone/offset riêng theo cơ chế provider hỗ trợ, có thể cần thêm cột.

Tên chiến lược, mặc định và khả năng hỗ trợ phụ thuộc phiên bản Hibernate. Không sao chép cấu hình này vào dự án mà chưa kiểm tra phiên bản thực tế và DDL. Nếu schema đã có cột `TIMESTAMP WITH TIME ZONE`, hãy cấu hình mapping tương thích thay vì để Hibernate tự tạo kiểu khác.

### 3.8. DST, timezone và giờ địa phương

Với vùng có daylight saving time (DST), một giờ địa phương có thể không tồn tại khi đồng hồ tiến lên hoặc xuất hiện hai lần khi đồng hồ lùi lại. `LocalDateTime` không tự giải quyết được sự mơ hồ đó.

Ví dụ lịch hẹn lúc 01:30 ở một vùng DST có thể ánh xạ tới hai instant khác nhau vào ngày chuyển giờ. Nếu cần xác định chính xác thời điểm, dùng `ZonedDateTime`/`OffsetDateTime` theo quy tắc nghiệp vụ và lưu thông tin cần thiết.

Việt Nam hiện dùng UTC+07 và không áp dụng DST trong quy tắc hiện hành, nhưng hệ thống vẫn có thể lưu dữ liệu cho khách hàng hoặc sự kiện ở quốc gia khác. Không hard-code `+07:00` cho mọi thời điểm nếu ứng dụng đa vùng.

### 3.9. Legacy Date và Calendar với @Temporal

`@Temporal` áp dụng cho `java.util.Date` và `Calendar`, không áp dụng cho các kiểu `java.time`:

```java
import jakarta.persistence.Temporal;
import jakarta.persistence.TemporalType;
import java.util.Date;

@Temporal(TemporalType.TIMESTAMP)
private Date createdAt;
```

Các giá trị:

- `TemporalType.DATE`: chỉ phần ngày theo mapping.
- `TemporalType.TIME`: phần giờ theo mapping.
- `TemporalType.TIMESTAMP`: ngày và giờ.

Với ứng dụng mới, ưu tiên `LocalDate`, `LocalDateTime`, `Instant` hoặc `OffsetDateTime` vì ý nghĩa rõ hơn và API tốt hơn. Không đặt `@Temporal` lên `LocalDateTime`; provider không yêu cầu annotation đó cho `java.time`.

## 4. Ánh xạ enum

### 4.1. Enum trong Java

Enum biểu diễn một tập giá trị hữu hạn:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
```

Trong database, cần quyết định lưu ordinal, tên enum hay một mã nghiệp vụ riêng. JPA hỗ trợ `@Enumerated` với hai chiến lược chuẩn.

### 4.2. EnumType.ORDINAL

Nếu dùng:

```java
@Enumerated(EnumType.ORDINAL)
@Column(name = "STATUS")
private OrderStatus status;
```

JPA lưu vị trí enum bắt đầu từ 0:

| Enum | Giá trị lưu |
|---|---:|
| `PENDING` | 0 |
| `PAID` | 1 |
| `CANCELLED` | 2 |

Vấn đề là thứ tự enum trở thành hợp đồng dữ liệu. Nếu thêm giá trị vào giữa:

```java
public enum OrderStatus {
    PENDING,
    PROCESSING,
    PAID,
    CANCELLED
}
```

Các ordinal cũ từ 1 trở đi đổi ý nghĩa. Dữ liệu `1` trước đây là `PAID`, nhưng sau thay đổi có thể được đọc thành `PROCESSING`. Đây là lỗi dữ liệu nguy hiểm vì không nhất thiết phát sinh exception.

Chỉ cân nhắc ordinal khi thứ tự là bất biến, enum không thay đổi và schema được kiểm soát chặt. Với hệ thống nghiệp vụ lâu dài, thường nên tránh.

### 4.3. EnumType.STRING

```java
@Enumerated(EnumType.STRING)
@Column(name = "STATUS", nullable = false, length = 20)
private OrderStatus status;
```

JPA lưu tên enum:

| Enum | Giá trị lưu |
|---|---|
| `PENDING` | `PENDING` |
| `PAID` | `PAID` |
| `CANCELLED` | `CANCELLED` |

Ưu điểm là thêm enum mới không làm thay đổi ý nghĩa của các giá trị cũ. Tuy nhiên, đổi tên `PAID` thành `SETTLED` sẽ khiến dữ liệu cũ không còn khớp enum mới nếu chưa migration. Tên enum Java trở thành một phần hợp đồng lưu trữ.

Để thay đổi an toàn, cần migration dữ liệu trước hoặc đồng thời với việc triển khai code mới, có thể dùng giai đoạn tương thích đọc cả giá trị cũ và mới nếu cần rolling deployment.

### 4.4. Dùng mã ổn định bằng AttributeConverter

Nếu database cần mã ngắn hoặc mã nghiệp vụ không phụ thuộc tên enum Java, dùng `AttributeConverter`. Ví dụ:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        for (OrderStatus status : values()) {
            if (status.databaseCode.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown order status code: " + code);
    }
}
```

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.databaseCode();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String databaseValue) {
        return databaseValue == null
            ? null
            : OrderStatus.fromDatabaseCode(databaseValue);
    }
}
```

Entity:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "STATUS_CODE", nullable = false, length = 1)
private OrderStatus status;
```

Database lưu `P`, `S`, `C`; Java vẫn dùng enum có tên dễ hiểu. Mã lưu trữ có thể giữ ổn định ngay cả khi tên enum Java được refactor.

Không đặt `@Enumerated` cùng `@Convert` trên một thuộc tính. Hãy chọn một chiến lược duy nhất: `@Enumerated` để lưu ordinal/string hoặc `@Convert` để chuyển đổi mã riêng.

### 4.5. Xử lý mã enum không biết

Converter có thể gặp giá trị trong database mà phiên bản code hiện tại chưa biết, ví dụ dữ liệu mới được ghi bởi phiên bản ứng dụng khác. Có hai chiến lược:

- **Fail fast:** ném exception để phát hiện dữ liệu hoặc deployment không tương thích.
- **Unknown sentinel:** ánh xạ về `UNKNOWN` nếu nghiệp vụ cho phép và mọi logic xử lý đều biết cách đối phó.

Không âm thầm ánh xạ mã lạ về `PENDING` hoặc một trạng thái hợp lệ bất kỳ. Điều đó có thể biến dữ liệu lỗi thành hành vi nghiệp vụ sai.

Nếu chọn sentinel:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C"),
    UNKNOWN("?");

    // Các phương thức như ví dụ trước.
}
```

Converter cần ghi nhận mã không biết theo cách không làm lộ dữ liệu nhạy cảm và cần quy trình xử lý dữ liệu đó. Khi ghi `UNKNOWN`, chỉ cho phép nếu database và nghiệp vụ định nghĩa rõ mã tương ứng.

### 4.6. Converter tự động với autoApply

Có thể đặt `autoApply = true`:

```java
@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {
    // Implementation như ví dụ trên.
}
```

Khi đó converter có thể được áp dụng tự động cho các thuộc tính có kiểu `OrderStatus` trong phạm vi persistence unit, trừ khi bị override hoặc disable theo mapping. Dùng `autoApply` khi mọi thuộc tính của kiểu đó có cùng quy tắc lưu trữ.

Nếu một enum được lưu bằng mã ở bảng này nhưng lưu bằng tên ở bảng khác, không nên bật `autoApply` toàn cục. Dùng `@Convert` tường minh ở từng thuộc tính để tránh áp dụng sai.

## 5. AttributeConverter cho kiểu dữ liệu nghiệp vụ

### 5.1. Converter làm gì?

JPA `AttributeConverter<X,Y>` chuyển kiểu thuộc tính Java `X` sang kiểu cơ bản `Y` mà provider có thể bind vào database, và chuyển ngược lại khi đọc:

```text
Entity attribute (X)
        |
        | convertToDatabaseColumn
        v
Database/JDBC value (Y)
        |
        | Oracle column
        v
Stored value

Stored value
        |
        v
Database/JDBC value (Y)
        |
        | convertToEntityAttribute
        v
Entity attribute (X)
```

Converter phù hợp với kiểu giá trị đơn (single-column value), chẳng hạn enum code, mã tiền tệ, phone number chuẩn hóa hoặc value object có thể biểu diễn bằng một cột. Nó không thay thế quan hệ `@OneToMany`, `@ManyToOne` hay một entity riêng nếu dữ liệu cần khóa và vòng đời độc lập.

### 5.2. Ví dụ converter cho mã tiền tệ

Giả sử domain dùng enum `CurrencyCode`, database lưu mã ISO dạng chuỗi:

```java
public enum CurrencyCode {
    VND,
    USD,
    EUR
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {

    @Override
    public String convertToDatabaseColumn(CurrencyCode attribute) {
        return attribute == null ? null : attribute.name();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : CurrencyCode.valueOf(dbValue);
    }
}
```

Ở ví dụ này `name()` được dùng vì mã domain trùng với mã ISO. Nếu tên enum Java có thể thay đổi, nên lưu mã riêng ổn định như ví dụ `OrderStatus` thay vì phụ thuộc `name()`.

### 5.3. Ví dụ converter cho value object

Giả sử ứng dụng muốn biểu diễn mã bưu chính đã chuẩn hóa:

```java
public record PostalCode(String value) {
    public PostalCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Postal code is required");
        }
        value = value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class PostalCodeConverter
        implements AttributeConverter<PostalCode, String> {

    @Override
    public String convertToDatabaseColumn(PostalCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public PostalCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new PostalCode(dbValue);
    }
}
```

Entity:

```java
@Convert(converter = PostalCodeConverter.class)
@Column(name = "POSTAL_CODE", length = 20)
private PostalCode postalCode;
```

Converter không nên phụ thuộc request, security context, repository hoặc gọi database khác. Nó cần là phép biến đổi xác định, dễ kiểm thử và không tạo side effect. Nếu dữ liệu cũ có định dạng không hợp lệ, constructor có thể ném exception khi hydrate entity; cần có migration/cleanup trước khi bật converter.

### 5.4. Xử lý null

Converter nên xác định rõ hành vi với `null`. JPA provider thường không gọi converter cho giá trị null trong một số trường hợp theo đặc tả; dù vậy, viết null-safe giúp code rõ ràng và tránh lỗi khi converter được gọi trực tiếp trong unit test hoặc qua đường xử lý khác.

Không biến `null` thành chuỗi rỗng nếu database phân biệt hai giá trị đó. Oracle hiện xử lý chuỗi rỗng `VARCHAR2` như `NULL`, nhưng quy tắc này không nên được dùng để thay thế thiết kế nullability của ứng dụng. Với kiểu số hoặc mã, `null` cũng có thể mang ý nghĩa khác với giá trị mặc định.

### 5.5. Không dùng converter để mã hóa bí mật tùy tiện

`AttributeConverter` có thể được dùng để chuyển đổi dữ liệu, nhưng không nên tự viết thuật toán mã hóa mật khẩu, token hoặc dữ liệu nhạy cảm trong converter. Mã hóa cần quản lý key, rotation, IV/nonce, authentication tag, version format và khả năng khôi phục. Với mật khẩu người dùng, dùng password hashing chuyên dụng; với dữ liệu cần giải mã, dùng cơ chế mã hóa được tổ chức phê duyệt hoặc Oracle TDE ở lớp database.

Converter cũng không thay thế kiểm soát quyền truy cập, audit hoặc masking. Nếu converter mã hóa dữ liệu bằng key lấy từ một static constant trong source code, key có thể bị lộ cùng artifact.

### 5.6. Converter và truy vấn JPQL/Criteria

Khi thuộc tính có converter, JPA provider thường áp dụng conversion khi bind giá trị tham số và đọc kết quả của thuộc tính đó. Ví dụ:

```java
List<OrderEntity> findByStatus(OrderStatus status);
```

Spring Data JPA có thể bind `status` qua converter tương ứng. Tuy nhiên, native SQL làm việc trực tiếp với tên cột và kiểu database; cần truyền giá trị đúng kiểu/mã lưu trữ theo SQL và driver. Không giả định mọi phép toán JPQL/Criteria trên thuộc tính converted đều có thể dịch giống thuộc tính primitive, đặc biệt với biểu thức, function hoặc kiểu phức tạp.

### 5.7. Converter không phải cách ánh xạ nhiều cột

`AttributeConverter` chuyển một thuộc tính thành một giá trị database cơ bản. Nếu value object gồm nhiều cột, có thể dùng `@Embeddable`/`@Embedded`:

```java
@Embeddable
public class Address {
    @Column(name = "STREET")
    private String street;

    @Column(name = "CITY")
    private String city;

    @Column(name = "POSTAL_CODE")
    private String postalCode;
}
```

Nếu dữ liệu có identity riêng hoặc được tham chiếu từ nhiều entity, dùng entity và relationship thay vì ép tất cả thành một converter.

## 6. Kết hợp các mapping trong một entity

Ví dụ sau ghép LOB, java.time, enum code và converter trong một entity đơn giản:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Table(name = "CUSTOMER_CASES")
public class CustomerCaseEntity {
    @Id
    @Column(name = "CASE_ID")
    private Long id;

    @Column(name = "OPENED_DATE", nullable = false)
    private LocalDate openedDate;

    @Column(name = "CREATED_AT", nullable = false)
    private Instant createdAt;

    @Column(name = "CONTACTED_AT")
    private OffsetDateTime contactedAt;

    @Convert(converter = CaseStatusConverter.class)
    @Column(name = "STATUS_CODE", nullable = false, length = 2)
    private CaseStatus status;

    @Column(name = "SUBJECT", nullable = false, length = 250)
    private String subject;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "DESCRIPTION")
    private String description;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "ATTACHMENT")
    private byte[] attachment;
}
```

Trong schema Oracle, migration script có thể khai báo rõ kiểu cột và precision:

```sql
CREATE TABLE CUSTOMER_CASES (
    CASE_ID       NUMBER(19)       NOT NULL,
    OPENED_DATE   DATE              NOT NULL,
    CREATED_AT    TIMESTAMP(6)      NOT NULL,
    CONTACTED_AT  TIMESTAMP(6) WITH TIME ZONE,
    STATUS_CODE   VARCHAR2(2 CHAR)  NOT NULL,
    SUBJECT       VARCHAR2(250 CHAR) NOT NULL,
    DESCRIPTION   CLOB,
    ATTACHMENT    BLOB,
    CONSTRAINT PK_CUSTOMER_CASES PRIMARY KEY (CASE_ID)
);
```

DDL chỉ là ví dụ. Cần căn chỉnh kiểu số, độ dài, character semantics, precision, timezone type và tên constraint với quy ước của database thật. Nếu dùng Hibernate schema generation trong development, so sánh DDL tạo ra với migration script; production nên dùng schema migration được version hóa.

## 7. Cấu hình Spring Boot và Hibernate

### 7.1. Dialect và schema management

Spring Boot thường tự phát hiện dialect từ JDBC metadata. Nếu dự án phải khai báo dialect, chọn dialect phù hợp với phiên bản Hibernate và Oracle Database. Không dùng class dialect cũ sau khi nâng Hibernate mà chưa kiểm tra.

Trong production, thường nên để:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

`validate` yêu cầu Hibernate kiểm tra mapping với schema hiện có nhưng không tự tạo hoặc sửa schema. Các môi trường phát triển có thể dùng `create`/`update` trong phạm vi kiểm soát, nhưng không nên dùng `update` như công cụ migration production. Dùng Flyway/Liquibase để tạo `CLOB`, `BLOB`, kiểu timestamp và thay đổi cột enum có lịch sử rõ ràng.

### 7.2. SQL logging và bind logging

Trong development có thể bật SQL logging để quan sát câu SQL:

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
```

Log bind parameter có thể hữu ích khi điều tra nhưng dễ làm lộ dữ liệu cá nhân, LOB metadata hoặc thông tin nhạy cảm. Không bật mức log bind chi tiết trên production một cách tùy tiện. Nếu cần, giới hạn thời gian, quyền đọc log và dữ liệu được phép ghi.

### 7.3. Bytecode enhancement cho lazy basic attributes

Nếu muốn Hibernate lazy-load LOB basic field, cần kiểm tra cấu hình bytecode enhancement của phiên bản Hibernate. Cơ chế này có thể được bật qua plugin build hoặc cấu hình provider. Tên option và plugin thay đổi theo version; tham khảo tài liệu Hibernate đang dùng.

Sau khi cấu hình, kiểm tra SQL bằng integration test: truy vấn entity mà không truy cập LOB, xác nhận cột LOB chưa được tải; sau đó truy cập thuộc tính trong transaction và xác nhận nó được tải theo dự kiến. Không dùng unit test mock để kết luận lazy loading hoạt động với Oracle.

## 8. Quản lý schema và thay đổi enum/time/LOB

### 8.1. Thay đổi enum ordinal sang string hoặc code

Đổi từ ordinal sang string/code cần migration dữ liệu. Không chỉ thay annotation rồi deploy vì các số cũ sẽ không tự biến thành tên enum.

Một quy trình an toàn có thể gồm:

1. Xác định mapping cũ: ordinal nào đại diện cho trạng thái nào.
2. Thêm cột mới, ví dụ `STATUS_CODE`, nếu cần triển khai chuyển tiếp.
3. Backfill mã tương ứng từ giá trị cũ.
4. Kiểm tra số lượng và phân bố từng mã.
5. Deploy code đọc/ghi tương thích theo chiến lược rolling deployment.
6. Chuyển ứng dụng sang cột mới và dừng ghi cột cũ.
7. Sau thời gian xác nhận, xóa cột cũ bằng migration riêng.

Nếu bảng nhỏ và có downtime, có thể cập nhật trực tiếp nhưng vẫn cần backup, mapping chính xác và kiểm tra kết quả trước khi deploy code mới.

### 8.2. Thay đổi VARCHAR2 sang CLOB

Khi nội dung vượt giới hạn cột hiện tại, cần đánh giá:

- Kích thước dữ liệu hiện có và lớn nhất dự kiến.
- Index, constraint, trigger, view và procedure phụ thuộc cột.
- API, DTO, report và truy vấn đang giả định chuỗi có độ dài hữu hạn.
- Khả năng tìm kiếm/sắp xếp và cách đọc stream.
- Tác động của Hibernate mapping và JDBC driver.

Không chỉ thay `@Column(length=...)` thành một con số rất lớn rồi mong Oracle tự tạo CLOB. Dùng migration DDL rõ ràng và kiểm tra dữ liệu sau chuyển đổi.

### 8.3. Thay đổi kiểu thời gian

Nếu chuyển `DATE` sang `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE`, cần xác định ý nghĩa dữ liệu cũ. Một giá trị `DATE` không chứa timezone; không thể khôi phục timezone ban đầu nếu trước đây ứng dụng đã ghi giờ địa phương mà không lưu vùng.

Trước migration, xác định timezone giả định cho dữ liệu cũ, cách chuyển sang UTC hoặc offset, và xử lý các thời điểm DST nếu có. Không thêm `+00:00` cho mọi giá trị chỉ để hoàn tất DDL nếu dữ liệu gốc thực ra là giờ địa phương.

## 9. Kiểm thử mapping

### 9.1. Kiểm thử round-trip

Với từng kiểu, cần kiểm tra ghi entity, flush, clear persistence context, đọc lại từ database và so sánh giá trị. Nếu chỉ đọc lại cùng entity còn trong persistence context, test có thể trả giá trị Java ban đầu mà chưa chứng minh dữ liệu lưu đúng.

Ví dụ luồng kiểm tra:

```java
entityManager.persist(entity);
entityManager.flush();
entityManager.clear();

CustomerCaseEntity loaded = entityManager.find(CustomerCaseEntity.class, entity.getId());
```

Sau đó so sánh các trường LOB, thời gian và enum. Test timezone nên chạy với session timezone khác nhau nếu hệ thống có thể kết nối từ nhiều vùng.

### 9.2. Các trường hợp LOB

- Nội dung rỗng, `NULL`, ASCII, tiếng Việt và Unicode ngoài BMP.
- Nội dung gần giới hạn ứng dụng và nội dung lớn.
- File binary rỗng, PDF/ảnh hợp lệ và dữ liệu lớn.
- Đọc metadata mà không đọc LOB.
- Đọc LOB sau khi entity detach hoặc transaction kết thúc để xác nhận hành vi lazy rõ ràng.
- Nhiều request tải file đồng thời để đo heap, connection usage và thời gian giữ cursor.

### 9.3. Các trường hợp thời gian

- Ngày không có giờ.
- LocalDateTime có phần fractional seconds.
- Instant trước và sau nửa đêm UTC.
- OffsetDateTime có offset khác UTC.
- Session timezone khác database timezone.
- TIMESTAMP WITH LOCAL TIME ZONE được đọc từ hai session timezone khác nhau.
- Thời điểm DST gap/overlap nếu nghiệp vụ phục vụ vùng có DST.
- Giá trị `NULL` và precision của fractional seconds.

### 9.4. Các trường hợp enum/converter

- Mọi mã enum hợp lệ.
- `NULL` nếu cột cho phép.
- Mã không biết hoặc dữ liệu cũ.
- Thay đổi tên enum Java nhưng giữ database code.
- Query repository theo enum đã convert.
- Native query và bulk update có truyền mã đúng kiểu.
- Migration dữ liệu khi đổi chiến lược ORDINAL/STRING/CODE.

### 9.5. Kiểm thử trên Oracle thật hoặc môi trường tương thích

H2 và các database khác không mô phỏng đầy đủ Oracle LOB, DATE semantics, timezone type, JDBC driver và dialect. Có thể dùng H2 cho test logic thuần, nhưng các mapping Oracle quan trọng nên có integration test với Oracle Database tương thích phiên bản, chẳng hạn môi trường Oracle Free/XE phù hợp hoặc Testcontainers nếu nền tảng và image được hỗ trợ.

Kiểm tra cả DDL thực tế, kiểu JDBC, dữ liệu round-trip và SQL do Hibernate phát sinh. Test chỉ chạy trên H2 có thể bỏ sót lỗi chỉ xuất hiện khi deploy Oracle.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| LOB bị tải cùng entity dù có `LAZY` | Basic lazy là hint; bytecode enhancement chưa bật hoặc provider không áp dụng. | Kiểm tra enhancement và SQL thực tế; dùng projection/query riêng. |
| `ORA-01461` hoặc lỗi bind chuỗi dài | Giá trị vượt giới hạn kiểu bind/cột hoặc mapping không phải LOB như mong đợi. | Kiểm tra DDL, JDBC type và mapping `@Lob`; dùng CLOB/BLOB phù hợp. |
| Heap tăng mạnh khi tải file | Đọc toàn bộ BLOB vào `byte[]` hoặc nhiều entity chứa LOB cùng lúc. | Dùng streaming, giới hạn concurrency và tách metadata khỏi nội dung. |
| `LazyInitializationException` | Truy cập LOB lazy sau khi session/transaction đã đóng. | Đọc trong transaction hoặc dùng query/service chuyên biệt trả stream có lifecycle rõ. |
| Thời gian lệch khi deploy ở timezone khác | Dùng LocalDateTime cho instant hoặc cấu hình storage/session timezone không thống nhất. | Chọn kiểu theo ý nghĩa, thống nhất UTC/zone và test round-trip. |
| Mất offset/ZoneId | Dùng kiểu/cấu hình chỉ lưu local timestamp hoặc offset không giữ region. | Chọn TSTZ hoặc lưu ZoneId riêng nếu nghiệp vụ cần. |
| Enum đọc sai sau khi thêm phần tử | Dùng `EnumType.ORDINAL` và đổi thứ tự enum. | Dùng STRING hoặc converter mã ổn định; migration dữ liệu. |
| `No enum constant ...` | Giá trị STRING trong database không khớp tên enum hiện tại. | Migration tên cũ/mới hoặc dùng converter với mã ổn định. |
| Converter ném exception khi load entity | Dữ liệu cũ có mã không hợp lệ hoặc converter giả định giá trị luôn hợp lệ. | Thống kê và migration dữ liệu; quyết định fail-fast hay UNKNOWN có chủ đích. |
| DDL tạo sai kiểu cột | Dialect/provider/version hoặc `columnDefinition` không khớp. | Dùng migration script rõ ràng và xác nhận schema trên Oracle. |

## 11. Quy tắc thiết kế thực tế

- Chọn kiểu Java theo ý nghĩa nghiệp vụ trước khi chọn kiểu Oracle.
- Dùng `@Lob String` cho văn bản lớn và `@Lob byte[]` cho dữ liệu nhị phân; xác nhận CLOB/BLOB trong schema.
- Chỉ dùng NCLOB khi national character set là yêu cầu thực sự; `@Nationalized` là Hibernate-specific.
- Xem `@Basic(fetch = LAZY)` là hint cho tới khi kiểm chứng provider và bytecode enhancement.
- Không tải LOB lớn trong truy vấn danh sách; dùng DTO/projection và endpoint riêng.
- Dùng stream cho nội dung lớn và giữ connection/cursor mở đúng thời gian cần thiết.
- Dùng `LocalDate` cho ngày lịch, `Instant` cho thời điểm tuyệt đối, `LocalDateTime` cho giờ địa phương không có zone, và `OffsetDateTime`/`ZonedDateTime` khi cần timezone semantics.
- Hiểu rõ khác biệt `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE`.
- Tránh `EnumType.ORDINAL` cho enum nghiệp vụ có thể thay đổi; ưu tiên STRING hoặc mã ổn định qua converter.
- Không kết hợp `@Enumerated` với `@Convert` trên cùng thuộc tính.
- Giữ converter đơn giản, xác định, null-safe và không có side effect.
- Quản lý thay đổi schema bằng Flyway/Liquibase; không dựa vào Hibernate `update` cho production.
- Kiểm thử round-trip sau `flush`/`clear` trên Oracle tương thích phiên bản.

## Kết luận

Ánh xạ LOB, thời gian, enum và converter cần bắt đầu từ ý nghĩa dữ liệu và yêu cầu lưu trữ. `@Lob` kết hợp `String`/`byte[]` thường tạo CLOB/BLOB; lazy loading và streaming phải được kiểm chứng với Hibernate và Oracle JDBC. Các kiểu `java.time` giúp phân biệt ngày lịch, giờ địa phương và instant, nhưng mapping timezone còn phụ thuộc Oracle SQL type, dialect và cấu hình Hibernate. `@Enumerated(STRING)` dễ đọc hơn ordinal nhưng vẫn phụ thuộc tên enum; `AttributeConverter` cho phép lưu mã ổn định và value object. Khi quản lý schema có version, kiểm thử round-trip trên Oracle và kiểm soát vòng đời tài nguyên, ứng dụng Spring Boot/JPA sẽ giữ dữ liệu chính xác và vận hành ổn định hơn.
