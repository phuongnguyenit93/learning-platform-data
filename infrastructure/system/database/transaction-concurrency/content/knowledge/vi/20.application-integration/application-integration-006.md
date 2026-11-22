# ORM: flush, COMMIT và thời điểm câu lệnh SQL thực sự chạy

Khi dùng ORM như JPA/Hibernate, gọi một phương thức Java để lưu entity không có nghĩa câu lệnh SQL tương ứng được gửi xuống database ngay tại dòng code đó. ORM thường giữ trạng thái entity trong persistence context (ngữ cảnh lưu trữ), theo dõi những thay đổi trong bộ nhớ và đồng bộ chúng xuống database tại một thời điểm gọi là **flush**.

`flush` và `COMMIT` là hai mốc khác nhau. Flush đồng bộ các thay đổi đang được quản lý thành câu lệnh SQL và thực thi chúng trong transaction hiện tại. Commit kết thúc transaction và xác nhận các thay đổi đã commit theo bảo đảm của hệ quản trị. Một transaction có thể flush nhiều lần trước khi commit; sau flush, transaction vẫn có thể rollback.

Hiểu rõ thời điểm SQL thực sự chạy giúp giải thích vì sao lỗi constraint hoặc optimistic locking có thể xuất hiện ở một dòng code tưởng như không liên quan, vì sao một truy vấn có thể kích hoạt INSERT/UPDATE trước khi câu SELECT chạy, và vì sao `saveAndFlush()` không đồng nghĩa với commit.

## 1. Persistence context: ORM giữ thay đổi trong bộ nhớ

Trong JPA, `EntityManager` quản lý một persistence context. Hibernate triển khai persistence context bằng cơ chế theo dõi entity và trạng thái của chúng. Khi một entity được quản lý (managed), ORM có thể phát hiện thay đổi trên các thuộc tính và lên kế hoạch ghi xuống database.

Ví dụ:

```java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.setName(newName);
}
```

Trong đoạn code này:

1. `find()` thường phát sinh SELECT nếu entity chưa có trong persistence context và chưa được cache.
2. `product` trở thành entity managed.
3. `setName()` thay đổi object trong bộ nhớ.
4. ORM ghi nhận entity đã khác trạng thái ban đầu bằng dirty checking.
5. SQL UPDATE thường được tạo và thực thi khi flush xảy ra, có thể là trước commit hoặc do một truy vấn cần flush.

Không cần gọi một phương thức `update()` riêng sau `setName()` trong mô hình managed entity thông thường. ORM sẽ phát hiện thay đổi khi đồng bộ persistence context. Tuy nhiên, điều này chỉ đúng với entity đang được quản lý trong persistence context phù hợp. Một object detached không được tự động theo dõi chỉ vì ứng dụng thay đổi thuộc tính của nó.

### Các trạng thái entity cơ bản

| Trạng thái | Ý nghĩa | ORM tự theo dõi thay đổi? |
| --- | --- | --- |
| New / transient | Object mới, chưa được đưa vào persistence context | Chưa, cho đến khi được `persist()` hoặc cơ chế tương đương |
| Managed | Entity đang được persistence context quản lý | Có, thông qua dirty checking |
| Detached | Entity từng được quản lý nhưng hiện không còn thuộc persistence context | Không |
| Removed | Entity managed đã được đánh dấu xóa | ORM lên kế hoạch DELETE khi flush |

Ví dụ:

```java
Product product = entityManager.find(Product.class, 10L); // managed
product.setName("Mechanical Keyboard");                   // được theo dõi

entityManager.detach(product);                             // detached
product.setName("New Name");                               // thay đổi này không tự được flush
```

Nếu cần đưa dữ liệu detached trở lại persistence context, JPA có `merge()`. Phương thức `merge()` trả về một instance managed chứa trạng thái được hợp nhất; object truyền vào không nhất thiết trở thành managed. Hãy tiếp tục làm việc với object được trả về.

## 2. Flush là gì?

Flush là quá trình ORM đồng bộ những thay đổi trong persistence context với trạng thái database bằng cách phát và thực thi các câu lệnh SQL cần thiết.

Một lần flush có thể bao gồm:

- INSERT cho entity mới đã được `persist()`.
- UPDATE cho entity managed đã thay đổi.
- DELETE cho entity đã được `remove()`.
- Các câu lệnh phụ thuộc quan hệ, khóa ngoại hoặc chiến lược mapping.

Ví dụ:

```java
@Transactional
public void createProduct() {
    Product product = new Product("Mouse", 250_000);
    entityManager.persist(product);

    // Tại đây entity đã được đưa vào persistence context.
    // SQL INSERT có thể chưa được gửi xuống database.

    entityManager.flush();

    // Sau flush, ORM đã đồng bộ thay đổi bằng SQL trong transaction.
    // Transaction vẫn chưa commit.
}
```

Flush không có nghĩa database đã xác nhận transaction cuối cùng. Các thay đổi đã thực thi vẫn thuộc transaction hiện tại và có thể bị rollback. Những transaction khác thường chưa nhìn thấy thay đổi chưa commit, hoặc có thể phải chờ tùy isolation level và loại khóa.

### Flush không phải là commit

| Mốc | Việc xảy ra | Có thể rollback thay đổi của transaction? |
| --- | --- | --- |
| Thay đổi entity trong bộ nhớ | ORM ghi nhận trạng thái mới | Chưa có SQL tương ứng để rollback ở database |
| Flush | SQL INSERT/UPDATE/DELETE được thực thi trong transaction | Có |
| COMMIT | Database hoàn tất transaction theo cấu hình durability | Không thể rollback transaction đã commit bằng `ROLLBACK` thông thường |

Ví dụ, sau flush:

```java
@Transactional
public void updateThenFail(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setPrice(100_000);

    entityManager.flush(); // UPDATE đã chạy trong transaction.

    throw new IllegalStateException("Business validation failed");
}
```

Nếu exception khiến transaction rollback theo cấu hình transaction manager, UPDATE đã flush cũng bị hoàn tác. SQL đã chạy không đồng nghĩa dữ liệu đã commit.

## 3. COMMIT thường kích hoạt flush trước

Khi transaction kết thúc thành công, ORM phải đồng bộ những thay đổi còn pending trước khi database commit. Vì vậy, commit qua JPA/Hibernate thường thực hiện flush trước, sau đó mới yêu cầu database commit.

Luồng khái quát:

```text
Ứng dụng             ORM / EntityManager              Database
    |                         |                           |
    | persist(entity)         |                           |
    |------------------------>| ghi nhận entity mới       |
    |                         |                           |
    | setName(...)            |                           |
    |------------------------>| ghi nhận thay đổi         |
    |                         |                           |
    | commit transaction      |                           |
    |------------------------>| flush persistence context |
    |                         |------ INSERT/UPDATE ------>|
    |                         |<----- SQL result ----------|
    |                         |------ COMMIT ------------->|
    |                         |<----- commit result -------|
    |<------------------------| transaction hoàn tất       |
```

Nếu flush thất bại vì constraint, deadlock hoặc optimistic locking, commit không thể hoàn tất bình thường. Nếu database commit thất bại, transaction có thể bị rollback hoặc client có thể rơi vào tình huống không xác định khi mất kết nối trong lúc chờ phản hồi.

Với Spring `@Transactional`, method body thường chạy trong transaction do proxy/transaction manager quản lý. Khi method kết thúc bình thường, transaction interceptor mới thực hiện commit; commit có thể kích hoạt flush sau khi dòng `return` trong method đã chạy. Vì vậy, lỗi flush/commit có thể xuất hiện ở ranh giới thoát khỏi method gọi, chứ không nhất thiết tại dòng `setName()` hoặc `save()`.

Nếu method tham gia một transaction bên ngoài đã tồn tại, method kết thúc không nhất thiết làm transaction commit. Transaction thực sự chỉ commit khi chủ sở hữu transaction kết thúc theo propagation và cấu hình tương ứng.

## 4. Những thời điểm ORM có thể tự động flush

Không phải ứng dụng luôn phải gọi `entityManager.flush()`. ORM có các quy tắc tự động flush để database và kết quả truy vấn không mâu thuẫn với những thay đổi đang chờ trong persistence context.

### Trước khi transaction commit

Đây là thời điểm phổ biến nhất. Khi transaction được commit, JPA provider phải đồng bộ các thay đổi cần thiết trước khi commit database.

```java
@Transactional
public void createOrder() {
    Order order = new Order();
    entityManager.persist(order);

    // Không gọi flush tường minh.
    // ORM sẽ flush khi transaction commit nếu thay đổi vẫn pending.
}
```

### Trước truy vấn khi FlushMode là AUTO

Với JPA `FlushModeType.AUTO`, provider phải bảo đảm các thay đổi pending có thể ảnh hưởng đến kết quả truy vấn được đồng bộ để truy vấn nhìn thấy trạng thái phù hợp. Provider thường flush trước một JPQL/Criteria query khi cần.

Ví dụ:

```java
@Transactional
public long countProducts() {
    Product product = new Product("Keyboard", 500_000);
    entityManager.persist(product);

    // Truy vấn có thể kích hoạt flush trước khi chạy SELECT.
    return entityManager.createQuery(
            "select count(p) from Product p", Long.class)
        .getSingleResult();
}
```

Nếu truy vấn có thể bị ảnh hưởng bởi entity mới, ORM cần bảo đảm kết quả phản ánh thay đổi pending theo semantics của JPA. Tùy provider và loại query, flush có thể diễn ra ngay trước truy vấn hoặc provider có cách thực hiện tương đương để giữ đúng semantics.

Không nên suy luận rằng mọi truy vấn SQL ở mọi API đều luôn gây flush. Native query, truy vấn qua Hibernate `Session`, flush mode và provider có thể có quy tắc riêng. Hãy kiểm tra tài liệu của phiên bản đang dùng khi thứ tự này ảnh hưởng đến tính đúng đắn hoặc hiệu năng.

### Flush tường minh

Ứng dụng có thể gọi:

```java
entityManager.flush();
```

để buộc ORM đồng bộ các thay đổi pending tại một vị trí xác định. Điều này hữu ích khi muốn phát hiện constraint violation sớm, lấy kết quả từ database trước bước tiếp theo hoặc bảo đảm SQL đã chạy trước một thao tác cần nó.

Flush tường minh không commit transaction. Không nên gọi sau mỗi setter hoặc mỗi entity nếu không có lý do, vì flush thường xuyên có thể làm tăng số lần SQL, round trip, thời gian giữ khóa và chi phí kiểm tra dirty state.

## 5. Flush mode trong JPA và Hibernate

Flush mode quyết định khi nào provider đồng bộ persistence context.

### JPA FlushModeType.AUTO

`AUTO` là chế độ mặc định trong JPA. Provider phải bảo đảm truy vấn trong transaction không trả kết quả bị sai do những thay đổi pending có thể ảnh hưởng đến truy vấn. Provider thường flush trước query liên quan và trước commit.

### JPA FlushModeType.COMMIT

`COMMIT` yêu cầu provider trì hoãn flush đến lúc commit trong phạm vi mà đặc tả cho phép. Tuy nhiên, ứng dụng không nên dựa vào giả định rằng provider tuyệt đối không flush sớm hơn. Đặc tả cho phép provider flush sớm, và truy vấn trước commit có thể không phản ánh mọi thay đổi pending theo cách ứng dụng mong đợi.

Ví dụ:

```java
entityManager.setFlushMode(FlushModeType.COMMIT);
```

Đây không phải lệnh commit và cũng không phải cam kết rằng SQL chỉ được gửi đúng tại một thời điểm duy nhất.

### Hibernate-specific flush modes

Hibernate có các chế độ riêng ngoài hai giá trị JPA, tùy phiên bản. Những tên thường gặp gồm:

- `AUTO`: tự động flush khi cần để giữ kết quả truy vấn nhất quán và trước commit.
- `COMMIT`: ưu tiên flush khi commit; provider vẫn có thể cần đồng bộ sớm trong một số tình huống.
- `ALWAYS`: flush trước mỗi query theo semantics Hibernate.
- `MANUAL`: ứng dụng chịu trách nhiệm gọi flush; thường dùng trong các tình huống chuyên biệt như batch processing.

Các chế độ Hibernate-specific không phải enum portable của JPA. API và semantics có thể thay đổi giữa phiên bản Hibernate; hãy dùng tài liệu đúng phiên bản của dự án.

## 6. `persist()`, `save()`, `saveAndFlush()` và `flush()` khác nhau thế nào?

Các tên phương thức có thể gây nhầm lẫn vì chúng không đại diện cùng một mốc trong vòng đời transaction.

| Phương thức | Ý nghĩa phổ biến | Có bảo đảm database commit? |
| --- | --- | --- |
| JPA `persist(entity)` | Đưa entity mới vào trạng thái managed; INSERT được lên kế hoạch | Không |
| JPA `merge(entity)` | Hợp nhất trạng thái vào instance managed và trả instance đó | Không |
| Spring Data `save(entity)` | Lưu qua EntityManager; thường gọi persist hoặc merge tùy entity mới/cũ | Không |
| Spring Data `saveAndFlush(entity)` | Save rồi yêu cầu flush persistence context | Không |
| JPA `flush()` | Đồng bộ thay đổi pending xuống database trong transaction | Không |
| Transaction `commit()` | Hoàn tất transaction; ORM thường flush trước khi database commit | Có, nếu commit thành công |

Ví dụ Spring Data JPA:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    @Transactional
    public void create(Product product) {
        repository.save(product);
        // Thường chưa có cam kết SQL đã chạy tại dòng này.

        repository.flush();
        // SQL pending được đồng bộ, nhưng transaction vẫn mở.
    }
}
```

`saveAndFlush()` hữu ích khi cần đẩy SQL xuống database sớm trong cùng transaction, ví dụ để nhận lỗi unique constraint trước khi chạy phần xử lý tiếp theo. Nhưng nếu method còn nằm trong transaction, thay đổi vẫn có thể rollback sau đó.

## 7. SQL thực sự chạy lúc nào? Không phải lúc nào cũng theo dòng Java

ORM thường gom thay đổi thành một tập hành động rồi thực thi khi flush. Thứ tự SQL được tạo có thể dựa trên dependency, loại thao tác, quan hệ entity, constraint và chiến lược nội bộ của provider. Vì vậy, không nên giả định câu SQL luôn chạy đúng theo thứ tự các lệnh Java đã gọi.

Ví dụ:

```java
entityManager.remove(oldProduct);
entityManager.persist(newProduct);
entityManager.flush();
```

Ứng dụng gọi `remove()` trước `persist()`, nhưng ORM có thể sắp xếp các thao tác SQL theo quy tắc của provider. Nếu hai hàng có cùng giá trị unique, kết quả phụ thuộc thứ tự SQL thực tế và loại constraint. Với một số thay đổi như đổi chỗ hai giá trị unique, có thể cần constraint deferrable hoặc một giá trị trung gian để tránh vi phạm ở bước giữa.

### JDBC batching

Hibernate hoặc provider có thể gom nhiều INSERT/UPDATE cùng dạng vào JDBC batch. Trong trường hợp này:

- ORM xác định các thao tác cần thực hiện.
- Provider đưa câu lệnh và tham số vào batch.
- Driver thực thi batch khi đến điểm phù hợp.
- Lỗi có thể được báo khi batch được gửi/thực thi hoặc khi kết quả batch được kiểm tra.

Do đó, dòng `persist()` có thể chỉ ghi nhận entity, còn SQL thực sự được gửi trong flush. Thậm chí khi flush, driver có thể gom nhiều câu lệnh thành một hoặc vài lần gửi mạng. Thời điểm chính xác còn phụ thuộc provider, driver, cấu hình batching và chiến lược ID.

### Sinh khóa chính có thể làm INSERT chạy sớm

Chiến lược sinh ID ảnh hưởng đến việc ORM có thể trì hoãn INSERT hay không.

- Với sequence, provider có thể lấy trước giá trị sequence rồi trì hoãn INSERT đến flush.
- Với identity/auto-increment, provider thường cần thực thi INSERT để database trả ID được tạo. Vì vậy INSERT có thể chạy sớm hơn, ngay trong lúc gọi persist/save.

Đây là hành vi phụ thuộc database, provider và cấu hình generator. Nếu cần biết chính xác thời điểm, hãy bật SQL logging và kiểm tra với phiên bản thực tế thay vì dựa vào một quy tắc chung.

## 8. Vì sao lỗi có thể xuất hiện tại flush hoặc COMMIT?

Một số lỗi chỉ được database phát hiện khi câu SQL thực sự chạy. Nếu ORM trì hoãn SQL, exception cũng bị trì hoãn.

### Constraint violation

Giả sử cột email có unique constraint. Hai entity được tạo trong bộ nhớ, nhưng chỉ khi flush INSERT mới được gửi đến database và database kiểm tra tính duy nhất.

```java
@Transactional
public void createCustomer(String email) {
    entityManager.persist(new Customer(email));

    // Nếu không flush ở đây, lỗi duplicate có thể xuất hiện
    // khi một query kích hoạt AUTO flush hoặc lúc commit.
}
```

Lỗi có thể xuất hiện khi:

- Ứng dụng gọi `flush()` tường minh.
- ORM tự flush trước một query.
- Transaction commit và ORM flush trước commit.
- Database kiểm tra một deferred constraint tại commit.

Không nên bắt lỗi chỉ quanh dòng `persist()` nếu provider có thể trì hoãn INSERT.

### Optimistic locking failure

Với entity có `@Version`, ORM thường tạo UPDATE có điều kiện theo version cũ:

```sql
UPDATE product
SET name = ?, version = 8
WHERE product_id = ?
  AND version = 7;
```

Nếu transaction khác đã tăng version, câu UPDATE có thể tác động 0 hàng. ORM nhận biết stale state và phát sinh optimistic locking exception. Vì UPDATE thường chạy lúc flush, lỗi có thể xuất hiện ở query kích hoạt flush hoặc tại commit, thay vì ở dòng setter.

### Foreign key violation

Nếu một entity tham chiếu đến hàng cha không tồn tại, INSERT/UPDATE có thể bị từ chối khi flush. Với quan hệ entity, ORM có thể sắp xếp thứ tự INSERT theo dependency để ghi hàng cha trước hàng con; nhưng nếu dữ liệu tham chiếu không hợp lệ hoặc thao tác ngoài ORM tạo race condition, lỗi vẫn có thể xảy ra.

### Deadlock và lock timeout

SQL UPDATE/DELETE được gửi trong flush có thể phải chờ khóa. Deadlock hoặc lock timeout vì thế có thể xuất hiện ở flush. Nếu ORM chỉ gửi SQL khi commit, lỗi có thể được nhìn thấy trong lời gọi commit.

## 9. Flush ảnh hưởng đến khóa và concurrency như thế nào?

Flush có thể làm database lấy khóa trước khi transaction commit. Nếu transaction flush UPDATE một hàng, khóa ghi thường được giữ theo quy tắc của engine đến khi transaction kết thúc. Transaction khác có thể bị chặn dù ứng dụng Java vẫn đang thực hiện thêm công việc sau flush.

Ví dụ:

```java
@Transactional
public void updateProduct(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setPrice(200_000);

    entityManager.flush(); // UPDATE và khóa ghi có thể đã được thực thi/lấy.

    callRemoteService();   // Không nên giữ transaction/lock trong lúc chờ mạng.

    // Commit xảy ra sau khi method kết thúc.
}
```

Nếu `callRemoteService()` mất vài giây, transaction có thể giữ khóa trong suốt thời gian chờ. Các transaction khác cần cập nhật cùng hàng sẽ phải đợi. Nếu dịch vụ ngoài bị treo, lock wait có thể kéo dài và làm giảm throughput.

Thực hành tốt:

1. Tính toán hoặc gọi dịch vụ ngoài trước transaction nếu không cần giữ tính nguyên tử với database.
2. Mở transaction sát với thời điểm đọc/ghi.
3. Flush khi có lý do rõ ràng, không dùng như một thao tác “cho chắc” sau mọi thay đổi.
4. Commit sớm khi mọi thay đổi database đã hoàn tất.
5. Nếu cần phối hợp tác dụng phụ ngoài database, cân nhắc outbox hoặc workflow thay vì giữ transaction mở trong lúc chờ mạng.

## 10. Flush và visibility: ai nhìn thấy dữ liệu sau flush?

Sau flush, SQL đã chạy trong transaction hiện tại. Vì vậy:

- Transaction hiện tại có thể đọc lại thay đổi của chính nó theo quy tắc read-your-writes.
- Transaction khác thường không nhìn thấy thay đổi chưa commit ở mức cô lập phổ biến như READ COMMITTED hoặc cao hơn.
- Transaction khác có thể bị chặn nếu cần khóa xung đột, hoặc tiếp tục đọc phiên bản đã commit trước đó nếu engine dùng MVCC.
- Sau commit, transaction khác có thể nhìn thấy thay đổi theo snapshot và isolation level của chúng.

Ví dụ hai transaction:

```text
T1: UPDATE product SET price = 200000 WHERE id = 10
T1: FLUSH (SQL chạy, chưa COMMIT)

T2: SELECT price FROM product WHERE id = 10
    -> thường thấy giá đã commit trước đó hoặc phải chờ,
       tùy engine/isolation; không mặc định thấy 200000.

T1: COMMIT
T2: truy vấn tiếp theo có thể thấy 200000,
    tùy snapshot/isolation level của T2.
```

Trong REPEATABLE READ hoặc snapshot isolation, T2 có thể tiếp tục thấy snapshot cũ trong suốt transaction dù T1 đã commit. Flush không làm dữ liệu trở nên visible toàn cục; commit và semantics isolation mới quyết định điều đó.

## 11. Flush, clear, refresh và detach

Các phương thức này tác động đến persistence context theo cách khác nhau:

- `flush()`: đồng bộ các thay đổi pending xuống database trong transaction.
- `clear()`: loại tất cả entity khỏi persistence context; entity trở thành detached.
- `detach(entity)`: loại một entity cụ thể khỏi persistence context.
- `refresh(entity)`: tải lại trạng thái entity từ database và ghi đè trạng thái trong bộ nhớ.

Ví dụ batch processing:

```java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    int batchSize = 100;

    for (int i = 0; i < inputs.size(); i++) {
        Product product = map(inputs.get(i));
        entityManager.persist(product);

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Flush theo batch giúp đẩy SQL xuống database định kỳ. Clear giải phóng các entity khỏi persistence context để tránh bộ nhớ tăng quá lớn. Nếu chỉ clear mà chưa flush, các thay đổi pending có thể bị mất khỏi persistence context mà chưa được gửi xuống database.

Sau `clear()`, những object cũ trong danh sách vẫn tồn tại trong bộ nhớ Java nhưng đã detached. Thay đổi tiếp theo trên chúng không tự được ORM theo dõi. Nếu cần cập nhật, hãy tải lại hoặc merge đúng cách.

`refresh()` có thể hữu ích khi cần lấy lại giá trị do database tạo hoặc thay đổi, nhưng nó ghi đè trạng thái chưa flush của entity. Nếu có thay đổi pending mà muốn giữ, hãy cân nhắc flush trước khi refresh.

## 12. Bulk UPDATE/DELETE và native SQL

JPQL bulk update/delete và native SQL thường đi thẳng xuống database, không thực hiện dirty checking cho từng entity như thao tác trên managed object.

Ví dụ:

```java
@Modifying
@Query("update Product p set p.active = false where p.lastSoldAt < :cutoff")
int deactivateOldProducts(Instant cutoff);
```

Câu lệnh bulk update thay đổi nhiều hàng trong database, nhưng các entity `Product` tương ứng đang nằm trong persistence context có thể vẫn giữ giá trị cũ. Điều này tạo ra trạng thái lệch giữa database và bộ nhớ.

Có thể xử lý bằng cách flush trước bulk operation nếu cần bảo toàn thứ tự các thay đổi pending, sau đó clear hoặc refresh các entity bị ảnh hưởng:

```java
entityManager.flush();

int updated = repository.deactivateOldProducts(cutoff);

entityManager.clear(); // Cẩn thận: tất cả managed entity trở thành detached.
```

Một số API Spring Data có tùy chọn `flushAutomatically` hoặc `clearAutomatically`; semantics cần kiểm tra theo phiên bản. Native query và query qua Hibernate Session cũng có quy tắc flush phụ thuộc API và flush mode. Không nên giả định mọi native SQL luôn tự flush hoặc luôn không flush.

Bulk update thường không tự áp dụng cơ chế `@Version` giống dirty checking entity thông thường. Nếu cần optimistic locking, phải đưa điều kiện version và thao tác tăng version vào câu SQL, đồng thời xử lý số hàng bị cập nhật.

## 13. Lỗi xảy ra tại đâu trong Spring/JPA?

Một điểm khó trong ứng dụng Spring là exception có thể được ném ra sau khi method service đã chạy hết phần thân. Ví dụ:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    @Transactional
    public void create(Product product) {
        repository.save(product);
        // Có thể chỉ đưa entity vào persistence context.
    }
}
```

Transaction interceptor thường thực hiện commit khi lời gọi method qua proxy kết thúc bình thường. Nếu flush lúc commit gặp unique constraint violation, caller có thể nhận exception từ ranh giới proxy sau khi thân method đã return.

Vì vậy, đoạn sau có thể không bắt được lỗi commit:

```java
@Transactional
public void create(Product product) {
    try {
        repository.save(product);
    } catch (DataIntegrityViolationException ex) {
        // Không chắc bắt được lỗi nếu INSERT chỉ chạy khi commit.
    }
}
```

Nếu cần bắt lỗi tại một vị trí trong method, có thể flush tường minh và xử lý theo quy tắc transaction:

```java
@Transactional
public void create(Product product) {
    repository.save(product);

    try {
        repository.flush();
    } catch (DataIntegrityViolationException ex) {
        // Lỗi được phát hiện tại flush nếu constraint được kiểm tra ngay.
        // Transaction có thể đã bị đánh dấu rollback-only.
        throw ex;
    }
}
```

Không phải lúc nào cũng có thể tiếp tục transaction sau lỗi flush. Với nhiều database/provider, lỗi SQL làm transaction không còn khả năng commit. Cách an toàn thường là để lỗi thoát ra, rollback transaction và chuyển đổi thành phản hồi nghiệp vụ ở tầng phù hợp bên ngoài transaction.

Nếu cần xử lý lỗi mà vẫn tiếp tục một transaction lớn, phải dùng savepoint hoặc transaction phụ với semantics được hỗ trợ rõ ràng. Không nên bắt exception rồi tiếp tục ghi như thể persistence context và transaction vẫn ở trạng thái bình thường.

## 14. Cách quan sát thời điểm SQL thực sự chạy

Khi cần biết SQL chạy ở đâu, hãy bật logging của ORM và theo dõi cả SQL lẫn bind parameter. Chỉ nhìn log câu lệnh Java không đủ.

Với Hibernate, các cấu hình logging thường dùng gồm category SQL và bind parameter; tên logger cụ thể thay đổi theo phiên bản. Trong môi trường phát triển có thể bật:

```properties
# Ví dụ cấu hình logging cho Hibernate 6 trong Spring Boot.
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Hãy lưu ý:

- Log SQL cho biết câu lệnh ORM gửi/thực thi, không chứng minh transaction đã commit.
- Log bind parameter giúp thấy giá trị thực tế nhưng có thể chứa dữ liệu nhạy cảm; không bật ở production nếu chưa kiểm soát.
- JDBC batch có thể khiến thời điểm thực thi khác thời điểm ORM lên lịch từng câu lệnh.
- Log transaction hoặc datasource cần được đối chiếu để thấy commit/rollback.
- Database-side monitoring, transaction log hoặc tracing có thể cần thiết khi điều tra lỗi mất kết nối trong commit.

Một bài kiểm thử hữu ích là ghi log ở các mốc `persist`, `flush`, query, method return và transaction completion, rồi đối chiếu với SQL log. Có thể dùng datasource proxy hoặc JDBC instrumentation để quan sát lúc driver gọi `execute`, `executeBatch` và `commit`.

## 15. Ví dụ tổng hợp: lỗi unique xuất hiện lúc flush

Giả sử email có unique constraint:

```sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
```

Ứng dụng tạo khách hàng:

```java
@Transactional
public void register(String email) {
    Customer customer = new Customer(email);
    entityManager.persist(customer);

    auditService.recordRegistrationAttempt(email);

    entityManager.flush();

    // Chỉ chạy đến đây nếu flush thành công.
}
```

Nếu một transaction khác đã chèn email đó và commit, INSERT tại flush có thể bị từ chối. Lỗi không nhất thiết xuất hiện tại `persist()`. Nếu bỏ flush tường minh, lỗi có thể xuất hiện khi query kích hoạt AUTO flush hoặc khi transaction commit.

Nếu `auditService` tham gia cùng transaction, bản ghi audit cũng có thể rollback khi transaction đăng ký thất bại. Nếu audit cần lưu cả lần đăng ký thất bại, nó phải được ghi bằng một transaction độc lập hoặc cơ chế logging phù hợp; không nên giả định dữ liệu trong cùng transaction sẽ tồn tại sau rollback.

## 16. Thực hành tốt khi làm việc với flush và commit

1. Hiểu persistence context và dirty checking: thay đổi managed entity có thể chỉ nằm trong bộ nhớ cho đến flush.
2. Xem flush là điểm đồng bộ SQL, không phải điểm commit.
3. Đặt ranh giới transaction rõ ràng và tránh transaction kéo dài.
4. Dùng flush tường minh khi cần phát hiện lỗi sớm hoặc cần SQL đã chạy trước bước kế tiếp.
5. Không flush sau mọi thay đổi một cách máy móc; flush nhiều lần có thể tăng round trip và thời gian giữ khóa.
6. Kiểm tra flush mode và hành vi query theo JPA provider/version; không giả định native SQL có cùng quy tắc với JPQL.
7. Khi dùng batch processing, kết hợp flush và clear theo lô; không clear trước khi đồng bộ thay đổi cần giữ.
8. Với bulk update/native SQL, quản lý sự lệch giữa database và persistence context; cân nhắc version check thủ công.
9. Bắt lỗi ở ranh giới phù hợp. Lỗi commit có thể xuất hiện sau khi thân method `@Transactional` đã kết thúc.
10. Khi flush thất bại, thường rollback toàn bộ transaction thay vì tiếp tục dùng persistence context như bình thường.
11. Dùng SQL logging và transaction tracing để xác nhận thời điểm câu lệnh thực sự chạy.
12. Không giữ transaction mở trong lúc gọi dịch vụ bên ngoài sau khi đã flush và lấy khóa database.

## 17. Những điểm cần ghi nhớ

- ORM thường giữ thay đổi của managed entity trong persistence context và dùng dirty checking để xác định SQL cần thực thi.
- `persist()` hoặc `save()` không phải lúc nào cũng gửi INSERT ngay; thời điểm phụ thuộc flush, query, ID generation và provider.
- Flush đồng bộ thay đổi pending bằng SQL trong transaction hiện tại; các thay đổi đã flush vẫn có thể rollback.
- Commit thường kích hoạt flush trước, sau đó database mới hoàn tất transaction.
- JPA `AUTO` có thể flush trước query khi thay đổi pending ảnh hưởng đến kết quả; `COMMIT` trì hoãn flush nhưng không phải cam kết tuyệt đối rằng không flush sớm.
- `saveAndFlush()` và `EntityManager.flush()` không commit transaction.
- Constraint violation, optimistic locking failure, deadlock hoặc lock timeout có thể xuất hiện tại flush thay vì dòng Java đã thay đổi entity.
- Flush có thể lấy khóa và bắt đầu thời gian chờ trước commit; tránh giữ transaction lâu sau flush.
- JDBC batching, thứ tự action của provider và chiến lược sinh ID làm thời điểm SQL thực thi khác nhau giữa hệ thống.
- Bulk JPQL/native SQL có thể không đồng bộ managed entity hoặc tự áp dụng `@Version`; cần quản lý persistence context và version rõ ràng.
- SQL log xác nhận câu lệnh đã được thực thi, nhưng chỉ kết quả commit mới xác nhận transaction hoàn tất.
