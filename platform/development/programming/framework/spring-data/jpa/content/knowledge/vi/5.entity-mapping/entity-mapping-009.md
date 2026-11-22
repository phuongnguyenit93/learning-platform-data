# Ánh xạ LOB, dữ liệu nhị phân và chi phí tải dữ liệu lớn

Trong JPA, LOB (Large Object) là dữ liệu có kích thước lớn, thường là văn bản dài hoặc dữ liệu nhị phân như ảnh, PDF, âm thanh và tệp đính kèm. Entity có thể ánh xạ các giá trị này bằng các kiểu Java như String, byte[], Blob hoặc Clob. Tuy nhiên, cách khai báo trường chỉ là một phần của bài toán: cách database lưu LOB, cách Hibernate tải dữ liệu và thời điểm ứng dụng đọc nội dung quyết định đáng kể đến bộ nhớ, thời gian truy vấn và khả năng mở rộng.

Khi thiết kế, cần phân biệt **metadata của tệp** (tên, MIME type, kích thước, chủ sở hữu, thời điểm tải lên) với **nội dung tệp** (toàn bộ byte hoặc văn bản). Nhiều màn hình chỉ cần metadata; tải nội dung lớn trong mọi truy vấn danh sách thường gây chi phí không cần thiết.

## 1. LOB là gì?

LOB là viết tắt của Large Object. Hai nhóm thường gặp:

- **CLOB (Character Large Object):** nội dung dạng ký tự, ví dụ văn bản dài, HTML, XML hoặc nội dung tài liệu.
- **BLOB (Binary Large Object):** nội dung nhị phân, ví dụ ảnh, PDF, file nén, âm thanh hoặc dữ liệu không phải văn bản.

JPA có annotation @Lob để đánh dấu một thuộc tính cần được ánh xạ theo ngữ nghĩa LOB:

~~~java
@Lob
private String articleBody;

@Lob
private byte[] fileContent;
~~~

Ví dụ trên thể hiện ý nghĩa ở mức JPA: một trường văn bản lớn và một trường nhị phân lớn. Kiểu SQL vật lý mà database sử dụng có thể khác nhau theo hệ quản trị và dialect của Hibernate. Không nên giả định @Lob luôn tạo cùng một kiểu cột trên H2, PostgreSQL, MySQL hay Oracle.

LOB không đồng nghĩa với việc dữ liệu được tự động stream. Nếu thuộc tính được ánh xạ thành String hoặc byte[], ứng dụng thường nhận toàn bộ giá trị vào bộ nhớ khi trường được tải.

## 2. Các kiểu Java thường dùng để ánh xạ LOB

### Văn bản dài với String

~~~java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;

@Lob
@Basic(fetch = FetchType.LAZY)
private String body;
~~~

String thuận tiện khi ứng dụng cần xử lý toàn bộ nội dung văn bản như một chuỗi Java. Nhưng nếu văn bản có kích thước hàng chục MB, việc tải một String hoàn chỉnh có thể chiếm nhiều bộ nhớ do dữ liệu được biểu diễn trong heap, ngoài phần dữ liệu và đối tượng liên quan.

### Dữ liệu nhị phân với byte[]

~~~java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;

@Lob
@Basic(fetch = FetchType.LAZY)
private byte[] content;
~~~

byte[] dễ sử dụng khi cần đọc hoặc ghi toàn bộ nội dung. Ví dụ, một ảnh nhỏ có thể được tải vào byte[] rồi trả về trong response. Tuy nhiên, byte[] yêu cầu cấp phát một mảng đủ lớn để chứa toàn bộ nội dung. Khi tải nhiều tệp cùng lúc, tổng bộ nhớ có thể tăng rất nhanh.

### Dùng Blob hoặc Clob

JPA cũng hỗ trợ các kiểu JDBC như java.sql.Blob và java.sql.Clob:

~~~java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;
import java.sql.Blob;

@Lob
@Basic(fetch = FetchType.LAZY)
private Blob content;
~~~

Blob cung cấp các phương thức để lấy BinaryStream hoặc làm việc với độ dài dữ liệu. Clob có API tương tự cho dữ liệu ký tự. Các kiểu này có thể hỗ trợ cách truy cập theo luồng tùy JDBC driver và database, nhưng không đảm bảo rằng toàn bộ chuỗi xử lý luôn không buffer dữ liệu. Cần kiểm tra hành vi của provider và driver đang dùng.

Blob/Clob thường gắn với tài nguyên JDBC và vòng đời của persistence context hoặc transaction. Không nên lấy một stream từ Blob rồi đóng transaction/session trước khi đọc xong. Hãy đọc và đóng stream trong phạm vi tài nguyên còn hiệu lực.

## 3. @Lob và @Column khác nhau thế nào?

@Lob biểu thị ngữ nghĩa dữ liệu lớn theo JPA. @Column mô tả thêm thông tin ánh xạ cột như tên cột, nullable, unique hoặc length.

Ví dụ:

~~~java
@Lob
@Column(name = "description")
private String description;
~~~

Một số điểm cần nhớ:

- @Column(length = ...) chủ yếu là thông tin dùng khi sinh DDL; chỉ đặt length lớn không tự bảo đảm database tạo kiểu LOB.
- @Lob không có nghĩa là Hibernate sẽ tự động tải theo luồng.
- @Column(columnDefinition = "...") có thể ép kiểu SQL cụ thể, nhưng làm mapping phụ thuộc database và giảm tính di động.
- Kiểu lưu trữ thực tế cần được xác nhận trên hệ quản trị mục tiêu và schema đã triển khai.

### Lưu ý quan trọng với PostgreSQL

PostgreSQL có nhiều cách lưu dữ liệu lớn, chẳng hạn kiểu text, bytea và cơ chế large object dùng OID. Cách Hibernate ánh xạ @Lob có thể dẫn đến cơ chế OID large object thay vì kiểu text hoặc bytea mà ứng dụng dự kiến. Vì vậy, không nên mặc định rằng @Lob String luôn tương đương với cột TEXT hoặc @Lob byte[] luôn tương đương với BYTEA.

Nếu mục tiêu là dùng kiểu PostgreSQL cụ thể như text hoặc bytea, hãy chọn mapping phù hợp với phiên bản Hibernate và dialect, kiểm tra DDL được sinh ra, rồi xác nhận schema thực tế. Ví dụ, mapping String vào cột text có thể dùng columnDefinition = "text" theo chủ đích PostgreSQL; đây là cấu hình đặc thù hệ quản trị, không phải lựa chọn portable cho mọi database.

Với MySQL, các kiểu như TEXT, MEDIUMTEXT, LONGTEXT, BLOB, MEDIUMBLOB và LONGBLOB có giới hạn kích thước khác nhau. Hãy chọn kiểu cột theo kích thước dự kiến và giới hạn của database. Không chỉ dựa vào tên @Lob để kết luận giới hạn tối đa.

## 4. Ví dụ Entity lưu tài liệu

Ví dụ sau minh họa một Entity lưu metadata và nội dung nhị phân cùng bảng:

~~~java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String fileName;

    @Column(nullable = false, length = 100)
    private String contentType;

    private long sizeBytes;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "file_content")
    private byte[] content;

    protected Document() {
    }

    public Document(
            String fileName,
            String contentType,
            byte[] content) {
        this.fileName = fileName;
        this.contentType = contentType;
        this.content = content;
        this.sizeBytes = content.length;
    }

    public Long getId() {
        return id;
    }

    public String getFileName() {
        return fileName;
    }

    public String getContentType() {
        return contentType;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }

    public byte[] getContent() {
        return content;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {
}
~~~

Đây là ví dụ cơ bản để giải thích mapping. Nếu dùng byte[] thì khi nội dung được tải, toàn bộ mảng byte được tạo trong bộ nhớ. Annotation @Basic(fetch = FetchType.LAZY) là yêu cầu tải trễ, nhưng khả năng thực thi phụ thuộc JPA provider và cấu hình bytecode enhancement. Không được coi annotation này là bảo đảm rằng mọi truy vấn danh sách sẽ bỏ qua trường content.

## 5. FetchType.LAZY trên thuộc tính LOB không phải cam kết tuyệt đối

JPA định nghĩa FetchType.LAZY cho một số thuộc tính cơ bản như một gợi ý cho provider. Với thuộc tính basic, provider có thể không hỗ trợ lazy loading nếu thiếu cơ chế cần thiết.

Trong Hibernate, việc tải trễ thuộc tính cơ bản như byte[] hoặc String thường cần bytecode enhancement được cấu hình phù hợp. Nếu không, trường có thể vẫn được tải cùng Entity dù đã ghi:

~~~java
@Lob
@Basic(fetch = FetchType.LAZY)
private byte[] content;
~~~

Cần kiểm tra cấu hình build enhancement và quan sát SQL thực tế. Không nên suy luận từ annotation rằng câu SELECT chắc chắn không lấy cột LOB.

Một số hệ quả nếu lazy loading hoạt động:

- Khi truy cập content, Hibernate có thể chạy thêm câu SELECT để tải nội dung.
- Nếu Entity đã detached hoặc persistence context đã đóng, truy cập trường lazy có thể gây lỗi lazy initialization.
- Nếu lặp qua danh sách Entity và truy cập content từng phần tử, có thể phát sinh nhiều truy vấn bổ sung (N+1).
- Nếu một request chỉ cần metadata, việc vô tình gọi getter của content trong mapper hoặc serializer có thể làm tải LOB.

Lazy loading giúp trì hoãn thời điểm đọc dữ liệu; nó không tự làm cho dữ liệu nhỏ hơn, không thay thế phân trang và cũng không tự bảo đảm streaming.

## 6. Tách metadata và nội dung thành hai Entity hoặc hai bảng

Khi tệp lớn hoặc màn hình thường xuyên chỉ cần thông tin mô tả, cách rõ ràng là tách metadata và payload. Ví dụ:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "document_metadata")
public class DocumentMetadata {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fileName;
    private String contentType;
    private long sizeBytes;

    protected DocumentMetadata() {
    }

    public Long getId() {
        return id;
    }

    public String getFileName() {
        return fileName;
    }

    public String getContentType() {
        return contentType;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }
}
~~~

Bảng nội dung:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "document_payload")
public class DocumentPayload {

    @Id
    private Long id;

    @Lob
    private byte[] content;

    protected DocumentPayload() {
    }

    public DocumentPayload(Long id, byte[] content) {
        this.id = id;
        this.content = content;
    }

    public Long getId() {
        return id;
    }

    public byte[] getContent() {
        return content;
    }
}
~~~

Hai Repository:

~~~java
public interface DocumentMetadataRepository
        extends JpaRepository<DocumentMetadata, Long> {
}

public interface DocumentPayloadRepository
        extends JpaRepository<DocumentPayload, Long> {
}
~~~

Với cách này, các truy vấn danh sách metadata không cần tải cột payload. Khi người dùng mở hoặc tải tệp, ứng dụng gọi DocumentPayloadRepository theo ID để lấy nội dung.

Trong thiết kế thực tế, nên khai báo khóa ngoại từ document_payload.id đến document_metadata.id và thực hiện thao tác lưu/xóa metadata cùng payload trong transaction phù hợp. Nếu payload lưu ở object storage, việc cập nhật database và object storage không tự động nằm trong cùng một transaction ACID; cần thiết kế xử lý lỗi và dọn dữ liệu mồ côi.

Tách bảng không làm giảm kích thước tệp, nhưng giúp các truy vấn thông thường chỉ đọc dữ liệu cần thiết và làm rõ ranh giới giữa metadata với nội dung.

## 7. Dùng projection để chỉ lấy metadata

Nếu vẫn lưu metadata trong một Entity, có thể dùng projection để chỉ chọn các trường cần hiển thị. Ví dụ projection dạng interface:

~~~java
public interface DocumentSummary {
    Long getId();
    String getFileName();
    String getContentType();
    long getSizeBytes();
}
~~~

Repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    @Query("""
        select d.id as id,
               d.fileName as fileName,
               d.contentType as contentType,
               d.sizeBytes as sizeBytes
        from Document d
        """)
    Page<DocumentSummary> findAllSummaries(Pageable pageable);
}
~~~

JPQL chỉ chọn bốn thuộc tính được liệt kê. Cột content không nằm trong danh sách select nên truy vấn metadata không cần trả toàn bộ nội dung LOB.

Ví dụ service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {

    private final DocumentRepository documentRepository;

    public DocumentQueryService(DocumentRepository documentRepository) {
        this.documentRepository = documentRepository;
    }

    @Transactional(readOnly = true)
    public Page<DocumentSummary> listDocuments(Pageable pageable) {
        return documentRepository.findAllSummaries(pageable);
    }
}
~~~

Projection phù hợp cho danh sách, bảng tìm kiếm và màn hình quản trị chỉ cần metadata. Với truy vấn cần tải nội dung, hãy tạo phương thức riêng để thể hiện rõ chi phí và mục đích của thao tác.

## 8. Vì sao tải LOB có thể tốn kém?

Một truy vấn trả về nhiều Entity có LOB có thể tiêu tốn tài nguyên ở nhiều tầng:

1. **Database I/O:** database phải đọc dữ liệu lớn từ vùng lưu trữ.
2. **Network transfer:** dữ liệu được truyền qua kết nối JDBC, làm tăng lượng byte và thời gian truyền.
3. **JDBC và Hibernate:** driver/provider có thể buffer hoặc materialize nội dung trong quá trình chuyển đổi.
4. **Java heap:** byte[] và String cần vùng nhớ đủ lớn; nhiều bản sao tạm thời có thể xuất hiện khi chuyển đổi hoặc xử lý.
5. **Garbage collection:** các mảng và chuỗi lớn tạo áp lực lên heap và có thể làm tăng thời gian GC.
6. **HTTP response:** nếu trả nhiều nội dung cùng lúc, response lớn làm tăng thời gian truyền, băng thông và số kết nối đang bận.

Ví dụ, nếu một truy vấn tải 100 tệp, mỗi tệp trung bình 5 MB, riêng payload đã là khoảng 500 MB dữ liệu trước khi tính chi phí object, buffer, metadata và các bản sao tạm thời. Nếu nhiều request diễn ra đồng thời, nhu cầu bộ nhớ và băng thông tăng theo số request.

Đây là lý do không nên dùng findAll() để tải toàn bộ Entity chứa LOB cho một trang danh sách. Cần giới hạn dữ liệu được chọn và số bản ghi được trả về.

## 9. Phân trang và chỉ tải nội dung khi cần

Danh sách metadata nên được phân trang:

~~~java
Page<DocumentSummary> page =
        documentRepository.findAllSummaries(
                PageRequest.of(0, 20)
        );
~~~

Với truy vấn chỉ lấy metadata, mỗi trang giới hạn số dòng và không kéo theo toàn bộ payload. Khi người dùng chọn một tài liệu, ứng dụng mới tải nội dung theo ID.

Các nguyên tắc hữu ích:

- Chỉ chọn cột cần dùng bằng projection hoặc DTO query.
- Dùng Pageable để giới hạn số bản ghi trả về.
- Tách endpoint danh sách metadata và endpoint tải nội dung.
- Tránh serialize trực tiếp Entity có byte[] vào JSON.
- Không gọi getter LOB trong mapper cho danh sách nếu màn hình không cần nội dung.
- Không dùng JOIN FETCH hoặc EntityGraph rộng để kéo nội dung lớn vào truy vấn danh sách nếu không có nhu cầu rõ ràng.
- Kiểm soát kích thước tệp tải lên và giới hạn request ở tầng web, reverse proxy và ứng dụng.

Phân trang chỉ giới hạn số bản ghi; nếu mỗi bản ghi vẫn chứa LOB lớn, một trang nhỏ vẫn có thể rất nặng. Vì vậy, phân trang cần kết hợp với projection hoặc chiến lược tách payload.

## 10. Đọc dữ liệu theo luồng với Blob

Khi cần xử lý tệp lớn mà không muốn tạo một byte[] chứa toàn bộ nội dung, có thể dùng Blob và stream từ JDBC. Ví dụ ở mức JPA:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;
import java.io.InputStream;
import java.sql.Blob;

public class DocumentBlobReader {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void processDocument(Long id) throws Exception {
        DocumentBlob document =
                entityManager.find(DocumentBlob.class, id);

        if (document == null) {
            throw new IllegalArgumentException("Document not found");
        }

        Blob blob = document.getContent();

        try (InputStream input = blob.getBinaryStream()) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                processChunk(buffer, count);
            }
        }
    }

    private void processChunk(byte[] buffer, int count) {
        // Xử lý tối đa count byte hiện có trong buffer.
    }
}
~~~

Đây là ví dụ minh họa vòng đời stream. Entity DocumentBlob cần ánh xạ trường content bằng @Lob với kiểu java.sql.Blob. Phương thức processDocument chạy trong transaction để stream được đọc khi tài nguyên persistence/JDBC còn hiệu lực.

Lưu ý:

- Đóng InputStream bằng try-with-resources.
- Không trả stream ra khỏi phương thức rồi kết thúc transaction trước khi bên gọi đọc xong.
- Không giả định mọi JDBC driver đều stream hoàn toàn từ database; một số driver hoặc provider có thể buffer dữ liệu.
- Cần kiểm thử với đúng database, JDBC driver và cấu hình connection pool đang dùng.
- Không gọi Blob.free() trước khi stream đã đọc xong; nếu chủ động giải phóng Blob, thực hiện sau khi hoàn tất xử lý và theo hợp đồng của driver/provider.

Nếu chỉ cần trả tệp qua HTTP, có thể dùng cơ chế streaming của Spring MVC như StreamingResponseBody, nhưng phải giữ transaction và tài nguyên JDBC mở trong lúc callback đọc stream, đồng thời đóng stream đúng cách. Không nên mở transaction trong một service, trả về Blob/stream, rồi để transaction kết thúc trước khi controller ghi response.

## 11. Lưu nội dung trong database hay object storage?

Không có một lựa chọn phù hợp cho mọi ứng dụng. Cần cân nhắc kích thước tệp, tần suất đọc, nhu cầu transaction, backup, phân quyền và vận hành.

| Tiêu chí | Lưu LOB trong database | Lưu file trong object storage |
|---|---|---|
| Metadata và nội dung | Có thể cùng nằm trong database | Metadata trong database, nội dung ở object storage |
| Transaction | Có thể quản lý metadata và LOB trong cùng transaction tùy database | Ghi database và object storage không tự động là một transaction |
| Truy vấn metadata | Cần tránh chọn cột LOB khi không cần | Thường nhẹ vì database chỉ chứa metadata |
| Tải nội dung lớn | Qua database và JDBC | Có thể tải trực tiếp từ object storage |
| Backup | Nằm trong chiến lược backup database | Cần backup/versioning/lifecycle riêng cho object storage |
| Phân quyền | Theo quyền database và tầng ứng dụng | Có thể dùng policy, signed URL hoặc quyền truy cập của dịch vụ lưu trữ |
| Vận hành | Đơn giản hơn khi dữ liệu nhỏ và hệ thống đã có database | Thêm dịch vụ và quy trình đồng bộ, xóa, retry |

Lưu trong database có thể hợp lý khi tệp nhỏ, số lượng vừa phải, cần transaction chặt hoặc muốn backup dữ liệu cùng database. Object storage thường phù hợp hơn với file lớn, số lượng nhiều, tải xuống thường xuyên hoặc cần phân phối nội dung độc lập với database.

Một mô hình phổ biến là lưu metadata và object key trong database, còn file nằm trong object storage. Không nên lưu URL có chữ ký tạm thời (signed URL) làm định danh lâu dài; lưu object key ổn định và tạo signed URL khi cần.

Vì hai hệ thống không cùng transaction, cần xử lý các tình huống như upload thành công nhưng ghi metadata thất bại, hoặc metadata đã ghi nhưng upload thất bại. Có thể dùng quy trình trạng thái, retry và tác vụ dọn object mồ côi để bảo đảm nhất quán cuối cùng.

## 12. Bảo mật và kiểm soát dữ liệu tải lên

LOB có thể chứa nội dung do người dùng gửi lên. Ngoài mapping và hiệu năng, cần kiểm soát:

- Giới hạn dung lượng tối đa ở cả reverse proxy, web server và ứng dụng.
- Kiểm tra loại nội dung dựa trên dữ liệu thực tế khi cần; không tin hoàn toàn vào phần mở rộng hoặc Content-Type do client gửi.
- Kiểm tra quyền sở hữu và quyền truy cập trước khi đọc hoặc tải tệp.
- Tránh đưa nội dung nhị phân vào log, exception message hoặc trace.
- Đặt tên lưu trữ an toàn; không dùng trực tiếp đường dẫn do client cung cấp.
- Có chính sách retention, xóa và backup phù hợp.
- Nếu cho phép tải nội dung HTML hoặc tài liệu có thể thực thi, cần cân nhắc cách phục vụ an toàn để tránh content injection hoặc thực thi ngoài ý muốn.

Khi trả file qua HTTP, nên đặt Content-Type phù hợp, Content-Disposition theo nhu cầu inline/attachment và tên file đã được xử lý an toàn. Không trả toàn bộ byte[] trong một JSON response chỉ để thuận tiện.

## 13. Những lỗi thường gặp và cách xử lý

**Danh sách tài liệu chậm dù chỉ hiển thị tên và kích thước**

- Kiểm tra câu SQL có chọn cột LOB hay không.
- Kiểm tra mapper, serializer hoặc getter có vô tình truy cập nội dung không.
- Dùng projection chỉ lấy metadata.
- Xác nhận lazy loading có thực sự hoạt động bằng SQL log.

**Ứng dụng hết bộ nhớ khi tải nhiều file**

- Tránh tải nhiều byte[] lớn cùng lúc.
- Giới hạn số bản ghi và kích thước file.
- Đọc theo stream hoặc chuyển nội dung lớn sang object storage.
- Kiểm soát số request tải đồng thời và kích thước buffer.

**LazyInitializationException khi truy cập nội dung**

- Xác định nội dung được tải ở đâu và persistence context kết thúc lúc nào.
- Đọc LOB trong transaction phù hợp.
- Không trả Blob/Clob hoặc lazy entity ra khỏi transaction rồi mới đọc.
- Cân nhắc phương thức service chuyên biệt để tải nội dung.

**@Lob không tạo kiểu cột mong muốn**

- Kiểm tra database dialect và DDL thực tế.
- Với PostgreSQL, phân biệt OID large object, text và bytea.
- Với MySQL, kiểm tra giới hạn của các kiểu TEXT/BLOB.
- Chỉ dùng columnDefinition khi chấp nhận mapping phụ thuộc hệ quản trị.

**Tải danh sách gây ra nhiều truy vấn bổ sung**

- Kiểm tra SQL log để phát hiện N+1 khi lazy field hoặc quan hệ được truy cập trong vòng lặp.
- Không gọi getter nội dung trong mapper danh sách.
- Dùng projection, truy vấn theo trang và tải payload theo yêu cầu.

## 14. Quy trình thiết kế và kiểm tra

Khi thêm trường LOB vào Entity, hãy xác định trước:

1. Nội dung là văn bản hay nhị phân?
2. Kích thước trung bình, tối đa và số lượng dữ liệu dự kiến là bao nhiêu?
3. Những truy vấn nào cần metadata và những thao tác nào cần nội dung?
4. LOB có cần tải thường xuyên cùng Entity không?
5. Database đích ánh xạ @Lob thành kiểu vật lý nào?
6. Provider có thực hiện lazy loading cho basic field không? Có cần bytecode enhancement không?
7. Có thể tách metadata/payload hoặc dùng object storage không?
8. Đọc nội dung có cần streaming không và tài nguyên JDBC sẽ được giữ trong bao lâu?
9. Cần kiểm tra giới hạn upload, phân quyền, backup và xóa dữ liệu như thế nào?

Sau khi triển khai, kiểm tra SQL sinh ra, kích thước response, heap usage, số lượng truy vấn và hành vi với nhiều request đồng thời. Hãy thử với dữ liệu có kích thước gần giới hạn thực tế, không chỉ với file mẫu vài KB.

## 15. Kết luận

JPA có thể ánh xạ văn bản lớn và dữ liệu nhị phân bằng @Lob với các kiểu như String, byte[], Blob hoặc Clob. Tuy nhiên, annotation không tự bảo đảm streaming hay lazy loading, và kiểu lưu trữ vật lý phụ thuộc database cùng Hibernate dialect. Để tránh tải dữ liệu lớn không cần thiết, hãy tách metadata khỏi payload trong truy vấn, phân trang danh sách, chỉ tải nội dung khi người dùng yêu cầu, và cân nhắc stream hoặc object storage cho tệp lớn.