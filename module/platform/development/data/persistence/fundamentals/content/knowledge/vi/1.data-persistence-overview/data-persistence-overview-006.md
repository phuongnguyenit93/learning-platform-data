# Phân biệt persistence, serialization, object mapping và ORM

Một ứng dụng Java có thể **biến đối tượng thành JSON**, **chuyển dữ liệu từ JSON thành đối tượng**, **ánh xạ đối tượng sang bảng** và **ghi dữ liệu xuống cơ sở dữ liệu**. Bốn hành động này thường xuất hiện cạnh nhau nhưng không đồng nghĩa với nhau. Phân biệt đúng **persistence**, **serialization**, **object mapping** và **ORM** giúp thiết kế tầng truy cập dữ liệu rõ ràng, tránh hiểu sai về độ bền dữ liệu, giao dịch và trách nhiệm của framework.

Bài học thuộc chương **Định hướng** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Các khái niệm ở đây làm nền cho việc chọn mô hình lưu trữ, thiết kế lược đồ, tối ưu truy vấn và chỉ mục, kiểm soát giao dịch và đồng thời, thiết kế ranh giới persistence trong Java, xử lý lỗi kết nối, tiến hóa schema, bảo mật và sao lưu.

## 1. Nhìn nhanh bốn khái niệm

| Khái niệm | Mục tiêu chính | Đầu vào → đầu ra điển hình | Bản thân có bảo đảm dữ liệu được lưu bền vững không? |
| --- | --- | --- | --- |
| **Persistence** (lưu trữ bền vững) | Duy trì trạng thái cần giữ qua vòng đời tiến trình và cho phép truy xuất lại | Lệnh ghi/đọc ↔ dữ liệu trong database hoặc tệp | **Là mục tiêu và cơ chế lưu giữ**, nhưng mức bảo đảm cụ thể phụ thuộc hệ lưu trữ, giao dịch và cấu hình. |
| **Serialization** (tuần tự hóa) | Biểu diễn dữ liệu/đối tượng ở một định dạng có thể truyền hoặc lưu | Đối tượng Java → JSON, XML, Protobuf hoặc byte | **Không**. Tạo biểu diễn chưa có nghĩa đã ghi vào nơi lưu bền vững. |
| **Object mapping** (ánh xạ đối tượng) | Chuyển dữ liệu giữa các mô hình hoặc kiểu có cấu trúc khác nhau | DTO ↔ domain object; `ResultSet` → đối tượng Java | **Không**. Việc chuyển đổi có thể diễn ra hoàn toàn trong bộ nhớ. |
| **ORM** (Object–Relational Mapping) | Ánh xạ mô hình đối tượng với mô hình cơ sở dữ liệu quan hệ | Entity Java ↔ hàng/cột/bảng và quan hệ | **Không tự nó**. ORM thường hỗ trợ thực hiện persistence, nhưng còn phụ thuộc kết nối, transaction, SQL và database. |

Một câu ngắn để nhận diện: **serialization nói về cách biểu diễn**, **object mapping nói về cách chuyển giữa mô hình**, **ORM nói về ánh xạ đối tượng–quan hệ**, còn **persistence nói về việc lưu và khôi phục trạng thái theo yêu cầu độ bền**.

Các phạm vi có thể giao nhau: thư viện JSON vừa serialize vừa ánh xạ thuộc tính Java sang trường JSON; ORM là một dạng ánh xạ chuyên biệt, đồng thời cung cấp cơ chế tương tác cơ sở dữ liệu; ứng dụng có thể persist dữ liệu qua JDBC mà không dùng ORM.

## 2. Một luồng dữ liệu Java thực tế

Giả sử một API nhận yêu cầu tạo sách:

~~~http
POST /books
Content-Type: application/json

{"title":"Java và dữ liệu"}
~~~

Ứng dụng cần nhận JSON, tạo đối tượng nghiệp vụ, lưu bản ghi sách, rồi phản hồi:

~~~json
{"id": 42, "title": "Java và dữ liệu"}
~~~

Một kiến trúc minh họa:

~~~mermaid
flowchart TD
    A["HTTP request chứa JSON"] -->|"Deserialization / JSON mapping"| B["CreateBookRequest (DTO)"]
    B -->|"Object mapping + kiểm tra nghiệp vụ"| C["BookEntity / domain model"]
    C -->|"ORM: ánh xạ lớp ↔ bảng"| D["SQL qua JDBC"]
    D -->|"Persistence: ghi trong transaction"| E[("Cơ sở dữ liệu")]
    E -->|"Truy vấn + ORM hoặc JDBC"| F["Dữ liệu sách được đọc"]
    F -->|"Object mapping"| G["BookResponse (DTO)"]
    G -->|"Serialization"| H["HTTP response chứa JSON"]
~~~

Sơ đồ phân chia trách nhiệm theo mục đích; thực tế ORM thường tạo và thực thi SQL thông qua cơ chế truy cập dữ liệu, còn persistence bao gồm toàn bộ quyết định giữ và khôi phục trạng thái. Không phải ứng dụng nào cũng có đủ các tầng: ứng dụng ghi tệp có thể không cần ORM; một dịch vụ chỉ chuyển tiếp dữ liệu có thể serialize mà không persist.

## 3. Persistence: giữ lại trạng thái để đọc được về sau

**Persistence** là khả năng lưu trạng thái dữ liệu cần được duy trì độc lập với vòng đời một đối tượng trong RAM hoặc tiến trình ứng dụng. Thường ứng dụng cần đọc lại dữ liệu sau khi khởi động lại; với nghiệp vụ quan trọng còn cần mức độ bền vững, tính nhất quán và khả năng phục hồi được xác định rõ.

Ví dụ:

- Gán `book.setTitle("Java và dữ liệu")` chỉ thay đổi một đối tượng Java trong bộ nhớ.
- Chuyển đối tượng thành chuỗi JSON chỉ tạo ra biểu diễn của dữ liệu.
- Ghi dữ liệu vào database và xác nhận giao dịch thành công mới là một hoạt động persistence theo cơ chế cơ sở dữ liệu.
- Ghi JSON vào tệp trên ổ lưu trữ cũng **có thể** là persistence, nếu ứng dụng thực hiện và quản lý việc ghi, đóng, đọc lại và bảo đảm phục hồi theo yêu cầu.

Persistence không bắt buộc dùng SQL hoặc ORM. Các lựa chọn phổ biến gồm cơ sở dữ liệu quan hệ, cơ sở dữ liệu tài liệu, kho khóa–giá trị cấu hình lưu bền, tệp và kho đối tượng. Sự phù hợp tùy cách truy cập, kiểu dữ liệu, mức nhất quán, chi phí và vận hành.

Ví dụ JDBC ghi một bản ghi vào bảng quan hệ:

~~~java
String sql = "INSERT INTO books (title) VALUES (?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "Java và dữ liệu");
    statement.executeUpdate();
}
~~~

Trong ví dụ tối giản này, `dataSource` là nguồn kết nối đã được cấu hình; việc xác nhận giao dịch phụ thuộc chế độ `autoCommit` hoặc transaction do tầng bao ngoài quản lý. Đoạn mã minh họa thao tác ghi không dùng ORM; không diễn đạt toàn bộ chính sách lỗi, số bản ghi, khóa sinh tự động hoặc xử lý yêu cầu lặp.

### Persistence khác tính bền vững tuyệt đối

**Durability** là thuộc tính/cam kết về khả năng giữ các thay đổi đã được xác nhận, chẳng hạn trong giao dịch ACID. Kết quả thực tế còn phụ thuộc cơ chế ghi log, cấu hình đồng bộ đĩa, replication, sao lưu và khả năng phục hồi. Không nên suy ra “đã gọi hàm save” đồng nghĩa “dữ liệu chắc chắn không thể mất”. Cũng cần phân biệt việc ghi thành công với tính nhất quán khi hai yêu cầu cùng sửa một bản ghi.

Persistence bao gồm các quyết định vượt xa chuyển đổi dữ liệu: **khóa định danh**, **ràng buộc**, **giao dịch**, **cô lập**, **retry**, **migrations**, **quyền truy cập**, **giám sát**, **backup/restore** và **hiệu năng truy vấn**.

## 4. Serialization: chuyển dữ liệu sang biểu diễn có thể lưu hoặc truyền

**Serialization** (tuần tự hóa) chuyển trạng thái hoặc giá trị dữ liệu sang một biểu diễn có định dạng. **Deserialization** (giải tuần tự hóa) diễn giải biểu diễn đó trở lại thành dữ liệu/đối tượng có cấu trúc.

Ví dụ một Java `record` được biểu diễn thành JSON:

~~~java
public record BookResponse(long id, String title) {}
~~~

~~~json
{
  "id": 42,
  "title": "Java và dữ liệu"
}
~~~

Với thư viện Jackson hỗ trợ Java records:

~~~java
ObjectMapper mapper = new ObjectMapper();

BookResponse book = new BookResponse(42L, "Java và dữ liệu");
String json = mapper.writeValueAsString(book);        // serialization
BookResponse copy = mapper.readValue(json, BookResponse.class); // deserialization
~~~

Đoạn mã giả định project có dependency Jackson phù hợp và xử lý ngoại lệ theo hợp đồng của thư viện. **Cả `json` và `copy` ở đây vẫn chỉ tồn tại trong bộ nhớ**. Chúng không tự được ghi xuống tệp hoặc database. Nếu ghi chuỗi JSON vào một nơi lưu trữ bền vững, việc ghi đó thuộc phạm vi persistence, còn biến đổi đối tượng → JSON vẫn là serialization.

Các định dạng thường thấy:

| Định dạng | Đặc điểm đáng chú ý | Ứng dụng thường gặp |
| --- | --- | --- |
| JSON | Dạng văn bản, dễ trao đổi và kiểm tra | REST API, cấu hình, tài liệu |
| XML | Dạng văn bản có cấu trúc, namespace/schema | Tích hợp hệ thống, tài liệu |
| Protocol Buffers | Định dạng nhị phân theo schema, gọn | Giao tiếp giữa dịch vụ, message |
| Avro | Biểu diễn theo schema, hỗ trợ tiến hóa schema theo quy tắc | Stream và xử lý dữ liệu |
| Java native serialization | Cơ chế nhị phân đặc thù Java | Một số hệ thống cũ; không ưu tiên làm định dạng lưu trữ dài hạn hoặc dữ liệu không tin cậy |

Những điều serialization **không tự bảo đảm**:

1. **Persistence:** chuỗi JSON có thể bị mất khi tiến trình kết thúc.
2. **Tính hợp lệ nghiệp vụ:** JSON hợp cú pháp vẫn có thể mang `price = -100` hoặc thiếu trường bắt buộc.
3. **Bảo mật:** JSON không mặc nhiên mã hóa, ký số hay phân quyền truy cập.
4. **Tương thích theo thời gian:** đổi tên hoặc kiểu trường có thể khiến bản dữ liệu cũ không còn đọc được nếu không quản lý phiên bản.

**Lưu ý bảo mật:** không giải tuần tự hóa đầu vào không tin cậy bằng các cơ chế cho phép tạo loại đối tượng tùy ý; đặc biệt cần tránh dùng Java native deserialization cho dữ liệu không tin cậy. Với JSON, giới hạn kiểu dữ liệu được ánh xạ, kích thước đầu vào và kiểm tra validation sau deserialization.

## 5. Object mapping: chuyển giữa các mô hình dữ liệu

**Object mapping** là quá trình xác định cách thuộc tính/giá trị của một đối tượng hoặc cấu trúc dữ liệu tương ứng với một đối tượng hoặc cấu trúc khác. Hai bên không nhất thiết có tên trường hoặc kiểu dữ liệu giống nhau.

Một ứng dụng thường có nhiều mô hình với mục đích khác nhau:

- **API DTO:** biểu diễn hợp đồng dữ liệu nhận/trả qua HTTP.
- **Domain model:** thể hiện khái niệm và quy tắc nghiệp vụ.
- **Persistence model:** thể hiện dữ liệu phù hợp bảng, cột, khóa và quan hệ.
- **Read model:** tập trường chuyên dùng cho hiển thị hoặc truy vấn.

Ví dụ một API trả giá bằng đơn vị nhỏ nhất:

~~~java
public record ProductResponse(long id, String displayName, long priceInCents) {}

public final class Product {
    private final long id;
    private final String name;
    private final long unitPriceInCents;

    public Product(long id, String name, long unitPriceInCents) {
        this.id = id;
        this.name = name;
        this.unitPriceInCents = unitPriceInCents;
    }

    public long id() { return id; }
    public String name() { return name; }
    public long unitPriceInCents() { return unitPriceInCents; }
}
~~~

Ánh xạ thủ công:

~~~java
ProductResponse toResponse(Product product) {
    return new ProductResponse(
        product.id(),
        product.name(),
        product.unitPriceInCents()
    );
}
~~~

Ở đây `name` của domain model được đưa sang `displayName` của DTO. Phương thức không gọi database và cũng không tạo JSON. Nếu sau đó dùng Jackson để biến `ProductResponse` thành JSON, đó là một bước serialization riêng.

### Ánh xạ một hàng SQL sang đối tượng Java

Khi dùng JDBC, ứng dụng có thể tự đọc `ResultSet` và tạo DTO:

~~~java
BookResponse mapRow(ResultSet rows) throws SQLException {
    return new BookResponse(
        rows.getLong("id"),
        rows.getString("title")
    );
}
~~~

Phương thức này là **object mapping**, cụ thể là *row mapping*. Còn lệnh `SELECT`, kết nối, quản lý transaction và việc dữ liệu đã có trong database thuộc trách nhiệm truy cập/persistence. Có thể dùng thư viện hỗ trợ mapping (ví dụ Spring JDBC `RowMapper`, MapStruct cho ánh xạ Java-to-Java), nhưng bản chất không thay đổi.

**Object mapping rộng hơn ORM.** Chuyển `CreateBookRequest` thành `Book`, chuyển đối tượng sang DTO, hoặc đọc hàng SQL thủ công đều là ánh xạ mà không cần ORM. Jackson cũng làm mapping trường JSON với thuộc tính Java trong quá trình serialize/deserialize; một thư viện có thể tham gia nhiều khâu cùng lúc.

### Vì sao không dùng một kiểu đối tượng cho mọi tầng?

Dùng chung một entity của database làm request và response có thể dẫn đến:

- Lộ trường nội bộ như mật khẩu băm, trạng thái nội bộ hoặc khóa không cần công khai.
- Bị phụ thuộc vào cấu trúc bảng khi thay đổi hợp đồng API.
- Vô tình ghi những trường người dùng không được phép sửa (*mass assignment*).
- Kéo theo quan hệ dữ liệu lớn hoặc vòng lặp khi serialize entity.
- Khó kiểm soát validation ở ranh giới nhập và bất biến nghiệp vụ.

Vì vậy, khi yêu cầu đủ phức tạp, DTO và lớp mapping rõ ràng thường giúp giới hạn dữ liệu đi qua từng ranh giới. Điều này không bắt buộc mọi ứng dụng phải có nhiều lớp: chọn mức tách biệt theo độ phức tạp và rủi ro thật sự.

## 6. ORM: một kiểu mapping chuyên cho cơ sở dữ liệu quan hệ

**Object–Relational Mapping (ORM)** là kỹ thuật và bộ công cụ ánh xạ dữ liệu giữa **đối tượng trong ứng dụng** và **bảng, cột, khóa, quan hệ** trong cơ sở dữ liệu quan hệ.

Ví dụ ánh xạ:

| Mô hình Java | Mô hình quan hệ |
| --- | --- |
| Lớp `BookEntity` | Bảng `books` |
| Trường `id` | Cột `id`, khóa chính |
| Trường `title` | Cột `title` |
| Tham chiếu `BookEntity` → `AuthorEntity` | Khóa ngoại hoặc bảng liên kết, tùy quan hệ |
| `EntityManager.find(...)` | Truy vấn tải hàng có khóa tương ứng, có xét persistence context/cache |

Trong hệ sinh thái Java:

- **JPA/Jakarta Persistence** định nghĩa API và quy tắc ánh xạ, vòng đời entity và quản lý persistence context.
- **Hibernate ORM** là một triển khai ORM/JPA phổ biến, có thêm các khả năng riêng.
- **EclipseLink** là một triển khai khác.
- **JDBC** là API truy cập cơ sở dữ liệu ở mức câu lệnh/kết nối; dùng JDBC không có nghĩa đang dùng ORM.
- **jOOQ** hỗ trợ xây dựng SQL có kiểu và ánh xạ kết quả nhưng không phải ORM theo mô hình entity lifecycle giống JPA/Hibernate.

Một entity JPA đơn giản, giả sử database đã có bảng `books`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "books")
public class BookEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    protected BookEntity() {
        // Constructor để ORM khởi tạo entity.
    }

    public BookEntity(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
~~~

Khi ứng dụng gọi `entityManager.persist(book)` trong một persistence context hợp lệ, provider ORM quản lý entity mới và lên lịch ghi dữ liệu. Provider tạo câu lệnh SQL phù hợp (có thể gửi SQL khi cần lấy khóa sinh hoặc khi `flush`). **`persist()` hoặc `flush()` chưa tương đương một giao dịch đã `COMMIT` thành công**. Kết quả cuối cùng phụ thuộc vào transaction, lỗi ràng buộc và cơ chế lưu trữ.

ORM thường cung cấp:

1. **Ánh xạ metadata:** bảng, cột, khóa, quan hệ, converter.
2. **Quản lý entity:** trạng thái mới, managed, detached, removed.
3. **Persistence context / identity map:** theo dõi các entity trong phạm vi context; thường một định danh entity ánh xạ tới một đối tượng managed trong context đó.
4. **Dirty checking:** phát hiện thay đổi của managed entity và phát sinh cập nhật khi flush nếu cần.
5. **Quan hệ và chiến lược tải:** liên kết one-to-many, many-to-one; lazy/eager fetching theo cấu hình và provider.
6. **Truy vấn:** JPQL, Criteria hoặc SQL trực tiếp; ORM không loại bỏ nhu cầu hiểu SQL.

ORM **không phải** database, cũng không phải một phương án thay thế cho tư duy về SQL, chỉ mục hoặc giao dịch. Nó che bớt mã lặp, nhưng truy vấn và chi phí I/O vẫn tồn tại.

## 7. Ví dụ xuyên suốt: từ JSON đến bản ghi và ngược lại

Thiết kế một API tạo sách có thể dùng **DTO để trao đổi**, **object mapping để chuyển dữ liệu**, **ORM để tương tác với bảng** và **database để persist**.

### Bước A — Deserialize dữ liệu HTTP thành request DTO

~~~java
// Giả sử class được khai báo trong file riêng:
public record CreateBookRequest(String title) {}

ObjectMapper mapper = new ObjectMapper();
CreateBookRequest request =
    mapper.readValue("{\"title\":\"Java và dữ liệu\"}", CreateBookRequest.class);
~~~

Jackson đọc JSON và tạo đối tượng `CreateBookRequest`. Đây là deserialization và JSON-to-object mapping; chưa có câu lệnh SQL.

### Bước B — Kiểm tra và chuyển DTO sang entity; ORM ghi theo transaction

Trong môi trường Jakarta EE có CDI và quản lý transaction, phần service có thể viết theo dạng:

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class BookService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public BookResponse create(CreateBookRequest request) {
        if (request == null || request.title() == null
                || request.title().isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không được rỗng");
        }

        String title = request.title().trim();
        if (title.length() > 200) {
            throw new IllegalArgumentException("Tiêu đề quá dài");
        }

        BookEntity book = new BookEntity(title); // DTO -> entity
        entityManager.persist(book);             // ORM quản lý entity mới
        entityManager.flush();                   // Đồng bộ SQL trong transaction

        return new BookResponse(book.getId(), book.getTitle());
    }
}
~~~

Và response DTO (định nghĩa ở một file nguồn riêng):

~~~java
public record BookResponse(Long id, String title) {}
~~~

Những chú ý khi đọc ví dụ:

- `@Transactional` cần môi trường/framework thực thi interceptor transaction; annotation tự nó không mở giao dịch trong một chương trình Java độc lập.
- `entityManager.persist(...)` chuyển entity mới vào trạng thái managed; ORM chuyển trạng thái thành SQL theo vòng đời của persistence context.
- `flush()` có thể phát hiện lỗi ràng buộc và đồng bộ SQL **trước khi commit**, nhưng **chưa xác nhận giao dịch**. Một lỗi ở `COMMIT` vẫn có thể khiến thao tác thất bại. Tầng gọi API chỉ nên công bố thành công sau khi transaction thực sự hoàn tất.
- Ví dụ lược bỏ các chi tiết cấu hình `DataSource`, JPA provider, xử lý lỗi HTTP, logging và chính sách rollback. Trong triển khai thực, cần đối chiếu transaction semantics với framework đang dùng.
- Kiểm tra tiêu đề trong service hữu ích cho nghiệp vụ; ràng buộc `NOT NULL` và chiều dài cột ở database là lớp bảo vệ dữ liệu khác.

### Bước C — Serialize DTO thành JSON phản hồi

~~~java
BookResponse result = new BookResponse(42L, "Java và dữ liệu");
String responseBody = mapper.writeValueAsString(result);
~~~

Việc chuyển `BookResponse` thành JSON là serialization. Bản ghi đã được lưu (nếu giao dịch đã commit thành công) là vấn đề persistence. Giá trị `42` ở đây chỉ minh họa cho khóa được cấp bởi database.

### Bước D — Đọc dữ liệu mà không dùng ORM cũng được

Nếu bỏ Hibernate/JPA, ứng dụng vẫn có thể thực hiện persistence bằng JDBC:

~~~java
String sql = "SELECT id, title FROM books WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, bookId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            BookResponse book = new BookResponse(
                rows.getLong("id"),
                rows.getString("title")
            );
            // Dùng book để xây dựng phản hồi.
        }
    }
}
~~~

Ở đây `connection` đã được cấp và quản lý bởi mã gọi. JDBC gửi truy vấn, còn khối tạo `BookResponse` thực hiện row mapping. Không có ORM, nhưng dữ liệu vẫn có thể được lưu, đọc và trả về bình thường.

## 8. ORM giải quyết điều gì và tạo ra chi phí gì?

ORM phù hợp khi có nhiều entity, quan hệ và thao tác CRUD theo một mô hình thống nhất, hoặc khi nhóm cần cơ chế quản lý entity và transaction tích hợp với framework. Tuy vậy cần nhận biết các tình huống khiến ORM phát sinh SQL khó đoán:

| Hiện tượng | Vì sao xảy ra | Cách tiếp cận |
| --- | --- | --- |
| **N+1 queries** | Tải danh sách `N` entity rồi tải riêng quan hệ cho từng entity | Kiểm tra SQL thực thi; cân nhắc fetch join, entity graph, batch fetching hoặc query DTO. |
| **Lazy loading ngoài context** | Truy cập thuộc tính/quan hệ chưa tải khi entity đã detached/context đóng | Thiết kế ranh giới transaction và truy vấn dữ liệu cần dùng trước khi rời tầng persistence. |
| **Ghi ngoài ý muốn** | Thay đổi thuộc tính của managed entity được dirty checking phát hiện | Kiểm soát chặt lệnh cập nhật, trạng thái entity và phạm vi giao dịch. |
| **Tải quá nhiều cột/hàng** | Tải full entity hoặc quan hệ khi chỉ cần vài trường | Sử dụng projection/DTO query và phân trang; kiểm tra execution plan. |
| **Xung đột đồng thời** | Nhiều transaction cùng cập nhật một hàng | Cân nhắc optimistic locking (ví dụ `@Version`), khóa phù hợp và chính sách thử lại. |
| **Lược đồ lệch với entity** | Schema database và annotation thay đổi không đồng bộ | Quản lý migration và kiểm thử tương thích; không mặc định dựa vào tự động tạo schema ở production. |

ORM không quyết định thay ứng dụng về quy tắc nghiệp vụ. Chẳng hạn, ORM có thể cập nhật hai tài khoản, nhưng vẫn phải xác định nghiệp vụ chuyển tiền, điều kiện đủ số dư, khóa yêu cầu, ranh giới transaction và xử lý kết quả không chắc chắn khi kết nối đứt lúc commit.

## 9. Khi nào chọn cách nào?

Các câu hỏi thiết kế nên được giải đáp độc lập:

| Câu hỏi | Công cụ/kỹ thuật liên quan |
| --- | --- |
| Dữ liệu có cần tồn tại sau khi chương trình kết thúc? | Thiết kế **persistence** và chọn kho lưu trữ thích hợp. |
| Dữ liệu phải trao đổi qua HTTP, hàng đợi hay tệp theo định dạng nào? | **Serialization** và versioning của hợp đồng dữ liệu. |
| API dùng tên trường khác domain; ai chuyển đổi và kiểm tra? | **Object mapping** cùng validation/nghiệp vụ. |
| Ứng dụng truy cập bảng quan hệ bằng mô hình entity? | Cân nhắc **ORM** như JPA/Hibernate. |
| Chỉ cần SQL rõ ràng hoặc truy vấn báo cáo phức tạp? | Có thể chọn **JDBC**, Spring JDBC hoặc **jOOQ**, không nhất thiết dùng ORM. |
| Cần nhiều thay đổi cùng thành công, có xử lý đồng thời? | **Transaction**, isolation, locking và ràng buộc ở tầng persistence/database. |
| Dữ liệu cũ phải đọc được sau thay đổi phiên bản? | **Schema migration** ở storage và **schema evolution** của định dạng serialize. |

Chọn ORM hay SQL trực tiếp là quyết định triển khai truy cập quan hệ; nó **không thay thế** câu hỏi chọn loại kho dữ liệu hoặc yêu cầu persistence. Một ứng dụng thực tế hoàn toàn có thể kết hợp ORM cho CRUD và SQL thủ công cho truy vấn cần tối ưu.

## 10. Các nhầm lẫn cần tránh

**Nhầm lẫn 1: “Đã serialize thành JSON là đã persist.”** Sai. JSON là cách biểu diễn. Chỉ khi dữ liệu được ghi vào một hệ lưu trữ phù hợp và hoàn tất theo cơ chế của hệ đó, ứng dụng mới đạt hành vi persistence mong muốn.

**Nhầm lẫn 2: “Serialization và object mapping là hai thứ luôn tách rời.”** Không hẳn. Thư viện JSON ánh xạ trường vào thuộc tính Java trong quá trình chuyển định dạng. Hai khái niệm mô tả **hai trách nhiệm**, có thể cùng được một thư viện thực hiện.

**Nhầm lẫn 3: “Object mapping đồng nghĩa ORM.”** Sai. DTO-to-domain, entity-to-response và JDBC row mapping đều là mapping, nhưng không tự động là ORM.

**Nhầm lẫn 4: “Dùng ORM thì không cần biết SQL.”** Sai. Truy vấn sinh ra có chi phí thực, cần chỉ mục, kế hoạch thực thi, phân trang và chiến lược tải quan hệ phù hợp.

**Nhầm lẫn 5: “Gọi `save()`, `persist()` hoặc `flush()` là dữ liệu đã commit.”** Không nhất thiết. Hành vi cụ thể phụ thuộc API và transaction; flush chỉ đồng bộ thay đổi trong bối cảnh giao dịch, không thay thế commit.

**Nhầm lẫn 6: “Đối tượng vừa deserialize chắc chắn an toàn và hợp lệ.”** Sai. Deserialization không thay thế xác thực kiểu, giới hạn dữ liệu, kiểm tra quyền hoặc các bất biến nghiệp vụ.

**Nhầm lẫn 7: “Entity nên được trả thẳng thành JSON để tiết kiệm mapping.”** Có thể gây lộ dữ liệu, kéo theo lazy loading, quan hệ vòng và phụ thuộc schema. DTO riêng thường cần thiết khi hợp đồng API và model lưu trữ có yêu cầu khác nhau.

## 11. Tự kiểm tra và bài tập tình huống

**Tình huống 1.** Ứng dụng tạo `String json = mapper.writeValueAsString(order)`, sau đó kết thúc mà không ghi chuỗi vào database/tệp. Đơn hàng có được giữ lại không?

**Đáp án:** Không, nếu không có cơ chế lưu trữ khác. Phương thức chỉ serialization; biến `json` trong RAM không phải bằng chứng persistence.

**Tình huống 2.** Một lập trình viên dùng `PreparedStatement` để `INSERT` vào bảng và dùng `ResultSet` tạo đối tượng Java. Công việc đó có persistence và ORM không?

**Đáp án:** Có persistence khi dữ liệu được ghi/đọc qua cơ sở dữ liệu theo bảo đảm cần thiết; có row mapping khi dựng đối tượng từ `ResultSet`; **không bắt buộc có ORM**.

**Tình huống 3.** `BookEntity` có annotation `@Entity`. Một hàm `entityManager.persist(book)` đã chạy, nhưng transaction sau đó rollback. Có thể khẳng định sách đã được lưu thành công không?

**Đáp án:** Không. ORM đã quản lý entity và có thể đã gửi SQL, nhưng thay đổi của transaction bị rollback nên không trở thành kết quả commit của giao dịch đó.

**Tình huống 4.** API cần trả tên hiển thị `displayName`, còn entity lưu `fullName`. Cần giải quyết ở đâu?

**Đáp án:** Tạo phép object mapping từ entity/domain model sang response DTO rồi serialize DTO. Không cần đổi tên cột database chỉ để hợp với tên trường phản hồi.

**Tình huống 5.** Dịch vụ thay JSON `{"title":"..."}` thành `{"name":"..."}` trong một phiên bản mới. Đây là vấn đề schema migration của database hay của serialization?

**Đáp án:** Chủ yếu là **hợp đồng định dạng trao đổi/serialization** và mapping ở API. Chỉ là schema migration của database nếu cấu trúc bảng hoặc dữ liệu lưu trữ cũng thay đổi.

**Bài thực hành:** Viết một API tạo đơn hàng trong Java. Hãy mô tả riêng (1) DTO nhận JSON và validation, (2) phép mapping sang domain/entity, (3) truy vấn SQL hoặc ORM thực hiện ghi, (4) ranh giới transaction nếu đơn hàng có nhiều dòng, (5) DTO phản hồi được serialize. Sau đó thử thay ORM bằng JDBC và giải thích bước nào vẫn giữ nguyên. Bài tập không yêu cầu triển khai ngay mọi cơ chế nâng cao, nhưng phải gọi đúng tên trách nhiệm của từng bước.

Khi đọc bất kỳ luồng dữ liệu nào, hãy lần lượt hỏi: **dữ liệu được biểu diễn thế nào, chuyển đổi giữa các mô hình ra sao, ai truy cập kho lưu trữ và tại thời điểm nào trạng thái được xác nhận bền vững?** Trả lời được bốn câu hỏi sẽ giúp sử dụng serialization, object mapping và ORM đúng chỗ trong thiết kế persistence của Java.
