# Chia lô, flush và clear khi nhập tập dữ liệu lớn

## 1. Vì sao nhập dữ liệu lớn cần chia lô?

Khi nhập hàng chục nghìn hoặc hàng triệu bản ghi bằng Spring Data JPA, cách viết đơn giản là đọc từng dòng rồi gọi `repository.save()`. Cách này có thể đúng về nghiệp vụ nhưng hiệu năng và mức sử dụng bộ nhớ thường không tốt nếu toàn bộ công việc chạy trong một persistence context lớn.

JPA duy trì persistence context (bộ nhớ đệm cấp một) để theo dõi các entity đang được quản lý. Khi nhập nhiều entity trong cùng một transaction, số object được giữ lại tăng dần. Hibernate còn phải kiểm tra trạng thái entity để phát hiện thay đổi và chuẩn bị câu SQL. Nếu không kiểm soát, ứng dụng có thể tốn nhiều heap, chạy chậm do dirty checking, hoặc gặp lỗi hết bộ nhớ.

Cần kết hợp ba ý tưởng:

- **JDBC batching:** gom nhiều lần thực thi câu lệnh cùng loại thành batch gửi xuống JDBC driver, giảm số lần trao đổi với database.
- **Chia lô dữ liệu (chunking):** xử lý một nhóm bản ghi ở mỗi lượt để kiểm soát lượng dữ liệu đang nằm trong bộ nhớ và kích thước công việc.
- **`flush()` và `clear()`:** đồng bộ thay đổi đang chờ xuống database, sau đó giải phóng các entity khỏi persistence context để tránh giữ toàn bộ object trong bộ nhớ.

Ba cơ chế có liên quan nhưng không thay thế nhau. Bật JDBC batching không tự giải phóng entity khỏi persistence context; gọi `clear()` cũng không tự tạo JDBC batch hay commit transaction.

Sau bài học, bạn có thể chọn kích thước batch phù hợp, cấu hình Hibernate, viết vòng lặp import có flush/clear đúng thứ tự và xác định khi nào nên commit theo từng chunk.

## 2. Phân biệt JDBC batch, chunk và transaction

Một luồng nhập dữ liệu có thể có ba kích thước khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| JDBC batch size | Số câu lệnh JDBC cùng nhóm được gom vào một batch | 50 câu INSERT |
| Flush/clear interval | Số entity được xử lý trước khi đồng bộ và giải phóng persistence context | 50 hoặc 100 entity |
| Transaction chunk size | Số bản ghi được commit trong một transaction | 500 hoặc 1.000 bản ghi |

Không bắt buộc ba giá trị phải giống nhau. Chẳng hạn, một transaction có thể xử lý 1.000 bản ghi, flush/clear mỗi 50 bản ghi, còn Hibernate gom tối đa 50 câu INSERT vào một JDBC batch. Khi đó một transaction có thể phát nhiều JDBC batch.

Hãy bắt đầu với các giá trị nhỏ, đo thời gian, heap, số lần round-trip và tải database rồi điều chỉnh. Một JDBC batch size khoảng 25–50 là điểm khởi đầu thường dùng, nhưng giá trị phù hợp phụ thuộc driver, database, độ rộng bản ghi và quan hệ giữa các bảng. Kích thước chunk của transaction thường lớn hơn JDBC batch size và cần được chọn theo yêu cầu rollback, thời gian xử lý và tài nguyên database.

## 3. Bật JDBC batching trong Hibernate

Với Spring Boot, cấu hình Hibernate trong `application.properties`:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Ý nghĩa:

- `hibernate.jdbc.batch_size`: giới hạn số câu lệnh JDBC được gom vào một batch.
- `hibernate.order_inserts`: sắp xếp thao tác INSERT để các câu lệnh cùng loại dễ được gom nhóm.
- `hibernate.order_updates`: sắp xếp thao tác UPDATE nhằm cải thiện khả năng batching và có thể giảm một số xung đột khóa.

Hai tùy chọn sắp xếp có thể làm tăng chi phí xử lý trong bộ nhớ. Hãy đo hiệu năng trước và sau khi bật chúng trên dữ liệu đại diện.

### Chiến lược sinh khóa ảnh hưởng đến batching

Hibernate không thể batching INSERT theo cách thông thường khi entity dùng khóa chính sinh bằng `GenerationType.IDENTITY`, vì database phải thực hiện INSERT ngay để trả về ID được sinh. Điều này làm mất lợi ích của JDBC insert batching trong Hibernate.

Nếu database hỗ trợ sequence, chiến lược `SEQUENCE` thường phù hợp hơn cho batch insert. Ví dụ:

```java
@Entity
@SequenceGenerator(
    name = "product_seq_generator",
    sequenceName = "product_seq",
    allocationSize = 50
)
public class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_seq_generator"
    )
    private Long id;

    private String sku;
    private String name;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }
}
```

Đây là entity minh họa. Sequence `product_seq` phải tồn tại hoặc được tạo đúng theo cấu hình schema; `allocationSize` phải phù hợp với cách cấp giá trị sequence của database và Hibernate. UUID hoặc khóa do ứng dụng cấp cũng có thể tránh việc phải chờ database trả ID sau từng INSERT. Không đổi chiến lược khóa chỉ vì batching nếu điều đó xung đột với thiết kế dữ liệu hiện tại.

## 4. Hiểu đúng flush() và clear()

### flush(): đồng bộ persistence context xuống database

`EntityManager.flush()` yêu cầu JPA provider đồng bộ các thay đổi đang chờ trong persistence context thành câu lệnh SQL. Với Hibernate, đây là thời điểm các INSERT, UPDATE hoặc DELETE cần thiết được phát xuống database; khi JDBC batching được cấu hình, các câu lệnh phù hợp có thể được gom thành batch.

`flush()` không commit transaction. Transaction vẫn mở và có thể rollback. Các thay đổi đã flush vẫn thuộc transaction hiện hành; chúng chưa trở thành dữ liệu đã commit cho các transaction khác theo cách thông thường.

Flush có thể xảy ra tự động trước khi commit và, tùy flush mode, trước một số truy vấn. Gọi flush tường minh giúp kiểm soát thời điểm đồng bộ và tránh để persistence context giữ quá nhiều thay đổi chờ xử lý.

Flush cũng có thể làm lộ lỗi sớm, chẳng hạn vi phạm unique constraint hoặc lỗi dữ liệu. Tuy nhiên, commit vẫn có thể thất bại vì các ràng buộc hoặc lỗi khác được kiểm tra ở thời điểm commit.

### clear(): tách tất cả entity khỏi persistence context

`EntityManager.clear()` xóa toàn bộ entity đang được quản lý khỏi persistence context. Những entity đó trở thành detached. Persistence context không còn theo dõi thay đổi trên các object này; nếu tiếp tục sửa một object đã detached, thay đổi đó không tự động được lưu.

`clear()` không xóa dữ liệu trong database, không rollback transaction và không commit các thay đổi đang chờ. Vì thế, phải flush trước khi clear nếu muốn giữ các thay đổi đã thực hiện:

```java
entityManager.flush();
entityManager.clear();
```

Sau `clear()`, các entity đang giữ trong biến Java không còn managed. Nếu cần cập nhật tiếp, hãy truy vấn lại hoặc dùng `merge` có chủ đích trong transaction phù hợp. Không giả định các quan hệ lazy trên entity detached vẫn có thể tải dữ liệu.

### Vì sao cần gọi cả hai?

Nếu chỉ gọi `flush()`, SQL được đồng bộ nhưng entity vẫn nằm trong persistence context. Bộ nhớ vẫn tăng khi nhập thêm dữ liệu.

Nếu chỉ gọi `clear()`, entity bị detach trước khi các thay đổi đang chờ được đồng bộ; những thay đổi chưa flush có thể không được lưu.

Mẫu an toàn khi xử lý theo lô là:

1. Tạo hoặc cập nhật một nhóm entity.
2. Gọi `flush()` để đồng bộ nhóm đó.
3. Gọi `clear()` để giải phóng entity khỏi persistence context.
4. Tiếp tục nhóm tiếp theo trong transaction hiện tại hoặc transaction mới theo thiết kế.

## 5. Mẫu persist theo lô trong một transaction

Nếu nghiệp vụ yêu cầu toàn bộ lần import thành công hoặc rollback cùng nhau, có thể giữ một transaction cho toàn bộ công việc nhưng flush/clear định kỳ để giới hạn số entity đang managed.

```java
@Service
public class ProductImportService {

    private static final int BATCH_SIZE = 50;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importAll(Iterator<ProductImportRow> rows) {
        int count = 0;

        while (rows.hasNext()) {
            ProductImportRow row = rows.next();
            entityManager.persist(
                new Product(row.sku(), row.name())
            );

            count++;
            if (count % BATCH_SIZE == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
    }
}

public record ProductImportRow(String sku, String name) {}
```

Đây là ví dụ tích hợp cần có entity `Product`, Spring context và nguồn dữ liệu cung cấp `Iterator`. Phương thức `importAll` mở một transaction cho toàn bộ lần nhập. Các lần flush gửi SQL xuống database, còn clear giải phóng persistence context. Khi kết thúc phương thức, Spring commit transaction; nếu có lỗi làm transaction rollback, các nhóm đã flush trong transaction đó cũng bị rollback.

Ưu điểm là bảo đảm tính nguyên tử cho toàn bộ import ở mức transaction. Nhược điểm là transaction vẫn kéo dài trong suốt quá trình nhập: connection bị giữ lâu, transaction log tăng, khóa có thể tồn tại lâu và database phải duy trì trạng thái transaction lớn. Flush/clear giảm áp lực heap của persistence context nhưng không làm transaction ngắn hơn.

Nếu nguồn dữ liệu là file lớn, hãy đọc và phân tích dữ liệu theo luồng thay vì nạp toàn bộ file thành một danh sách trước khi gọi service. Cần xác định rõ việc đọc file, kiểm tra dữ liệu và ghi database có nằm trong cùng transaction hay không.

## 6. Mỗi chunk là một transaction riêng

Nếu chấp nhận commit từng nhóm bản ghi, hãy tách phần điều phối import và phần ghi một chunk thành hai Spring bean. Mỗi lần gọi writer sẽ chạy trong transaction riêng:

```java
@Service
public class ProductChunkWriter {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void insertChunk(List<ProductImportRow> rows) {
        for (ProductImportRow row : rows) {
            entityManager.persist(
                new Product(row.sku(), row.name())
            );
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

```java
@Service
public class ProductImportCoordinator {

    private static final int CHUNK_SIZE = 500;

    private final ProductChunkWriter writer;

    public ProductImportCoordinator(ProductChunkWriter writer) {
        this.writer = writer;
    }

    public int importAll(Iterator<ProductImportRow> rows) {
        List<ProductImportRow> chunk = new ArrayList<>(CHUNK_SIZE);
        int imported = 0;

        while (rows.hasNext()) {
            chunk.add(rows.next());

            if (chunk.size() == CHUNK_SIZE) {
                writer.insertChunk(List.copyOf(chunk));
                imported += chunk.size();
                chunk.clear();
            }
        }

        if (!chunk.isEmpty()) {
            writer.insertChunk(List.copyOf(chunk));
            imported += chunk.size();
        }

        return imported;
    }
}
```

Ví dụ dùng Java 17 với `record`; cần có các import, entity, nguồn dữ liệu và cấu hình Spring tương ứng. Hai lớp phải là các Spring bean riêng để lời gọi `writer.insertChunk()` đi qua proxy transaction. Nếu đặt hai phương thức trong cùng bean và gọi bằng `this.insertChunk()`, proxy-based transaction interception sẽ không được kích hoạt cho lời gọi nội bộ đó.

Với `REQUIRES_NEW`, mỗi chunk có transaction riêng. Khi phương thức writer trả về thành công, transaction của chunk được commit trước khi coordinator tiếp tục. Nếu chunk thứ tư lỗi, các chunk đã commit trước đó vẫn tồn tại; chunk lỗi được rollback. Do đó, import cần có khả năng tiếp tục hoặc chạy lại an toàn, ví dụ dùng khóa nghiệp vụ duy nhất, trạng thái tiến độ, mã lô và thao tác idempotent.

Nếu coordinator được gọi từ một transaction bên ngoài, `REQUIRES_NEW` sẽ tạm ngưng transaction ngoài trong lúc ghi chunk. Transaction ngoài rollback sau đó không thể hoàn tác các chunk đã commit độc lập. Vì vậy, coordinator thường nên được gọi ngoài một transaction bao trùm khi mục tiêu là commit từng chunk.

Kích thước 500 ở ví dụ là kích thước chunk nghiệp vụ, không phải JDBC batch size. Với `hibernate.jdbc.batch_size=50`, một chunk 500 entity có thể phát nhiều JDBC batch. Điều chỉnh hai giá trị độc lập theo kết quả đo.

## 7. Dùng Spring Data repository đúng cách

`JpaRepository.saveAll()` thuận tiện khi lưu một collection, nhưng bản thân phương thức này không bảo đảm một JDBC batch duy nhất. Trong triển khai thông dụng, Spring Data JPA lặp qua các phần tử và gọi `save()` cho từng entity. Việc Hibernate có gom INSERT/UPDATE thành JDBC batch hay không còn phụ thuộc cấu hình, chiến lược ID, trạng thái entity và loại SQL.

`saveAllAndFlush()` lưu collection rồi flush persistence context. Phương thức này không tự chia collection thành nhiều chunk và cũng không tự clear persistence context. Nếu truyền vào một danh sách rất lớn, tất cả entity vẫn có thể nằm trong persistence context cho đến khi được clear hoặc transaction kết thúc.

Nếu cần tiếp tục dùng repository, hãy chia dữ liệu thành các chunk, gọi `saveAll(chunk)`, sau đó gọi `flush()` và clear qua EntityManager hoặc dùng `JpaRepository.flush()` rồi clear. Cần nhớ rằng clear sẽ detach tất cả entity trong persistence context hiện tại, kể cả entity được nạp trước đó cho nghiệp vụ khác.

Với các object chắc chắn là entity mới, `EntityManager.persist()` diễn đạt rõ ý định tạo mới. `save()` phải xác định entity mới hay đã tồn tại; tùy cách nhận diện trạng thái, Spring Data có thể gọi `persist` hoặc `merge`. `merge` có thể tạo thêm công việc đọc/ghi và trả về một instance được quản lý khác với object truyền vào. Hãy kiểm tra cách nhận diện entity mới và SQL thực tế khi tối ưu import.

## 8. Quan hệ entity và các lưu ý khi import

### Entity có quan hệ

Nếu entity có `cascade = PERSIST` hoặc `cascade = ALL`, gọi `persist` cho entity gốc có thể kéo theo nhiều entity liên quan. Điều này làm số câu lệnh SQL và số object trong persistence context tăng nhanh. Cần xác định rõ quan hệ nào thực sự cần cascade khi nhập.

Khi tham chiếu đến một entity đã tồn tại, `EntityManager.getReference()` có thể tạo một tham chiếu proxy theo ID mà chưa cần tải toàn bộ entity ngay. Cách này hữu ích khi gán khóa ngoại cho bản ghi mới, nhưng truy cập thuộc tính của proxy có thể kích hoạt truy vấn; hãy kiểm tra SQL thực tế và xử lý trường hợp ID tham chiếu không hợp lệ.

### Cập nhật entity thay vì insert

Với import có cả insert và update, cần phân loại bản ghi theo khóa nghiệp vụ. Việc tìm từng entity bằng một truy vấn riêng rồi cập nhật có thể tạo ra N+1 truy vấn ở chiều đọc. Có thể đọc các ID hiện có theo nhóm, dùng truy vấn projection hoặc staging table để đối chiếu. Sau khi cập nhật theo lô, tiếp tục flush/clear định kỳ.

Nếu chỉ cần cập nhật hàng loạt theo một điều kiện, JPQL bulk update hoặc SQL native có thể phù hợp hơn việc tải từng entity. Tuy nhiên, bulk DML tác động trực tiếp lên database và không đồng bộ trạng thái các entity đang managed trong persistence context; nó cũng không đi qua đầy đủ vòng đời entity như cập nhật từng object. Sau bulk DML, cân nhắc flush trước và clear hoặc refresh các entity bị ảnh hưởng để tránh đọc trạng thái cũ.

### Ràng buộc và tính hợp lệ

Ràng buộc unique, foreign key, not-null và check constraint ở database vẫn là lớp bảo vệ cuối cùng. Kiểm tra dữ liệu ở ứng dụng giúp đưa ra thông báo dễ hiểu, nhưng không thay thế ràng buộc database khi nhiều import chạy đồng thời. Với lỗi ở giữa chunk, hãy ghi nhận số dòng, khóa nghiệp vụ và nguyên nhân để có thể sửa và chạy lại.

## 9. Kiểm tra xem batching có thực sự hoạt động

Không nên kết luận JDBC batching hoạt động chỉ vì đã cấu hình `hibernate.jdbc.batch_size`. Hãy xác minh bằng dữ liệu và môi trường gần production:

- Bật Hibernate statistics trong môi trường kiểm thử phù hợp bằng `spring.jpa.properties.hibernate.generate_statistics=true`.
- Dùng log SQL hoặc công cụ quan sát JDBC để kiểm tra các lần `executeBatch`, số câu lệnh và thời gian round-trip.
- So sánh số bản ghi mỗi giây, thời gian hoàn thành, heap sử dụng và tải database khi bật/tắt batching.
- Kiểm tra riêng với chiến lược ID thực tế, đặc biệt nếu đang dùng `IDENTITY`.
- Thử cả insert, update và entity có quan hệ/cascade giống dữ liệu production.

Log SQL thường hiển thị nhiều câu INSERT giống nhau. Điều đó tự nó không chứng minh mỗi câu được gửi thành một round-trip riêng hay được gom thành batch; hãy dùng thống kê hoặc công cụ theo dõi JDBC để xác minh hành vi thực tế.

## 10. Chọn chiến lược transaction theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược phù hợp | Đánh đổi |
|---|---|---|
| Toàn bộ import phải thành công cùng nhau | Một transaction, flush/clear định kỳ | Tốn thời gian giữ transaction và connection |
| Dữ liệu rất lớn, chấp nhận một phần đã commit | Transaction riêng cho mỗi chunk | Cần tiến độ, retry và chống xử lý trùng |
| Cần tốc độ cao cho dữ liệu đơn giản | JDBC batching và có thể dùng bulk SQL/staging | Cần quản lý vòng đời entity và trạng thái persistence context |
| Cần cập nhật entity có quan hệ và callback | JPA persist/update theo chunk | Có chi phí dirty checking và cascade |

Đừng chọn transaction riêng từng chunk chỉ vì muốn giảm bộ nhớ. Nếu nghiệp vụ yêu cầu tính nguyên tử toàn bộ file, việc commit từng chunk sẽ thay đổi kết quả khi lỗi xảy ra. Ngược lại, một transaction khổng lồ có thể gây áp lực lên connection pool và database. Hãy xác định rõ yêu cầu rollback trước khi chọn cách chia transaction.

## 11. Checklist trước khi chạy import lớn

- [ ] Nguồn dữ liệu được đọc theo luồng hoặc theo trang, không giữ toàn bộ file trong heap.
- [ ] Đã cấu hình và đo `hibernate.jdbc.batch_size`.
- [ ] Đã kiểm tra chiến lược sinh ID có hỗ trợ insert batching hay không.
- [ ] Đã chọn riêng JDBC batch size, flush/clear interval và transaction chunk size.
- [ ] Mỗi nhóm được `flush()` trước khi `clear()`.
- [ ] Đã hiểu `clear()` detach toàn bộ entity trong persistence context hiện tại.
- [ ] Đã quyết định import là một transaction hay commit theo từng chunk.
- [ ] Nếu commit từng chunk, đã có cơ chế theo dõi tiến độ, idempotency và retry.
- [ ] Đã kiểm tra cascade, khóa ngoại, unique constraint và lỗi dữ liệu.
- [ ] Đã đo SQL batching, heap, throughput và thời gian transaction trên dữ liệu đại diện.

## 12. Ghi nhớ

JDBC batching giảm số lần gửi câu lệnh xuống database; chunking giới hạn lượng dữ liệu xử lý trong một lượt; `flush()` đồng bộ thay đổi đang chờ và `clear()` giải phóng entity khỏi persistence context. Mẫu JPA thường dùng là `persist` theo nhóm, `flush()`, rồi `clear()`. Nếu cần commit theo từng nhóm, đặt mỗi chunk trong một transaction riêng và thiết kế import có thể tiếp tục sau lỗi. Luôn phân biệt flush với commit và chọn ranh giới transaction theo yêu cầu toàn vẹn dữ liệu.
