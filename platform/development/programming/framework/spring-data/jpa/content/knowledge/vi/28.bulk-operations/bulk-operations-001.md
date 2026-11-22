# Phân biệt saveAll, JDBC batching và bulk DML

Khi cần ghi hoặc cập nhật hàng nghìn bản ghi bằng Spring Data JPA, có ba khái niệm dễ bị nhầm lẫn: `saveAll()`, JDBC batching và bulk DML. Chúng giải quyết những vấn đề khác nhau:

- `saveAll()` là API của Spring Data JPA để lưu một tập entity. Bản thân nó không có nghĩa là chỉ phát ra một câu SQL.
- JDBC batching là cách Hibernate gom nhiều câu lệnh SQL cùng dạng vào một batch JDBC để giảm số lần trao đổi với database. Có thể kết hợp JDBC batching với `saveAll()`.
- Bulk DML là câu lệnh `UPDATE` hoặc `DELETE` tác động trực tiếp lên nhiều hàng ở database, thường không cần nạp từng entity vào persistence context.

Chọn đúng cách phụ thuộc vào việc nghiệp vụ có cần xử lý từng entity, gọi lifecycle callback, áp dụng cascade và giữ trạng thái entity đồng bộ hay chỉ cần thay đổi hàng loạt theo một điều kiện.

## 1. `saveAll()` thực sự làm gì?

`saveAll(Iterable<S> entities)` là phương thức của `JpaRepository`. Trong implementation thông dụng `SimpleJpaRepository`, Spring Data JPA duyệt qua các entity và gọi `save()` cho từng phần tử.

Với mỗi entity, `save()` quyết định gọi `EntityManager.persist()` hay `EntityManager.merge()` dựa trên cơ chế nhận diện entity mới của Spring Data JPA:

- Entity được nhận diện là mới: gọi `persist()`.
- Entity được nhận diện là đã tồn tại: gọi `merge()`.

Vì vậy, `saveAll()` là thao tác lưu nhiều entity theo mô hình JPA. Nó không tự chuyển toàn bộ danh sách thành một câu lệnh SQL duy nhất.

Ví dụ:

~~~java
@Service
@RequiredArgsConstructor
public class ProductService {
    private final ProductRepository productRepository;

    @Transactional
    public List<Product> createProducts(List<Product> products) {
        return productRepository.saveAll(products);
    }
}
~~~

Trong ví dụ này, mỗi entity vẫn được quản lý theo quy tắc persist/merge của JPA. SQL thường được phát ra khi Hibernate flush persistence context, chẳng hạn khi transaction commit hoặc khi có thao tác buộc flush.

### Lưu ý về persist và merge

`persist()` đưa entity mới vào trạng thái managed. `merge()` sao chép trạng thái của entity đầu vào vào một instance managed và trả về instance đó. Với entity detached, đối tượng truyền vào `save()` có thể vẫn là detached; hãy sử dụng đối tượng được trả về nếu cần tiếp tục thao tác trên instance managed.

Spring Data JPA nhận diện entity mới theo quy tắc của `EntityInformation`, thường dựa trên thuộc tính version có thể null hoặc identifier. Nếu entity dùng quy tắc đặc biệt, có thể triển khai `Persistable` và cung cấp `isNew()` phù hợp.

Do đó, đừng chỉ nhìn tên `saveAll()` rồi giả định mọi phần tử chắc chắn được insert. Danh sách có thể chứa entity mới và entity đã tồn tại, khiến một số phần tử được persist còn phần khác được merge.

## 2. JDBC batching là gì?

JDBC batching là cơ chế của JDBC cho phép gom nhiều lần thực thi câu lệnh cùng dạng thành một batch. Thay vì gửi từng câu lệnh qua nhiều lần trao đổi riêng, ứng dụng thêm nhiều bộ tham số vào batch rồi thực thi batch đó.

Ví dụ về ý tưởng, cùng một câu lệnh insert được dùng với nhiều bộ giá trị:

~~~sql
INSERT INTO product (id, name, price) VALUES (?, ?, ?)
~~~

Hibernate có thể gom các bộ tham số khác nhau của câu lệnh này thành một JDBC batch. Database vẫn thực hiện nhiều thao tác insert, nhưng số lần gửi batch qua JDBC có thể ít hơn số bản ghi.

JDBC batching là tối ưu hóa ở tầng thực thi SQL. Nó không thay đổi ý nghĩa nghiệp vụ của việc lưu entity bằng JPA: Hibernate vẫn quản lý entity, dirty checking, mapping, cascade và các lifecycle callback theo quy tắc thông thường.

### Bật JDBC batching với Hibernate

Trong ứng dụng Spring Boot dùng Hibernate, có thể cấu hình trong `application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Ý nghĩa:

- `hibernate.jdbc.batch_size`: số câu lệnh cùng dạng tối đa Hibernate gom vào một batch trước khi thực thi. Giá trị 50 là ví dụ khởi đầu để đo thử, không phải con số tối ưu cho mọi database.
- `hibernate.order_inserts`: yêu cầu Hibernate sắp xếp insert để các câu lệnh cùng dạng có cơ hội nằm cạnh nhau và tạo batch hiệu quả hơn.
- `hibernate.order_updates`: tương tự với update.

Có thể đặt các thuộc tính Hibernate qua `spring.jpa.properties.*` trong Spring Boot. Nếu cấu hình trực tiếp Hibernate, dùng tên thuộc tính `hibernate.jdbc.batch_size`, `hibernate.order_inserts` và `hibernate.order_updates`.

JDBC batching cần được hỗ trợ bởi provider, JDBC driver và database. Ngoài ra, Hibernate không thể gom hiệu quả các câu lệnh có cấu trúc SQL khác nhau vào cùng một batch. Ví dụ, các entity được insert với tập cột khác nhau có thể tạo ra nhiều nhóm SQL.

### Kết hợp saveAll và JDBC batching

Đây là điểm quan trọng nhất: `saveAll()` và JDBC batching không phải hai lựa chọn loại trừ nhau. Ta có thể dùng `saveAll()` để lưu entity theo JPA, đồng thời cấu hình Hibernate để batch các câu lệnh SQL phát sinh khi flush.

~~~java
@Transactional
public void importProducts(List<Product> products) {
    productRepository.saveAll(products);
    productRepository.flush();
}
~~~

`flush()` đồng bộ thay đổi đang chờ trong persistence context xuống database. Nó không commit transaction. Nếu transaction còn hoạt động, các câu lệnh đã flush vẫn có thể bị rollback sau đó.

`saveAllAndFlush()` cũng lưu danh sách rồi flush. Phương thức này tiện khi cần buộc SQL được gửi xuống database trước khi phương thức kết thúc, nhưng nó không tự bật JDBC batching và cũng không xóa entity khỏi persistence context.

### Chú ý chiến lược sinh ID

Với Hibernate, chiến lược sinh khóa chính có thể ảnh hưởng trực tiếp đến batching:

- `GenerationType.IDENTITY`: Hibernate thường phải thực thi insert ngay để lấy ID do database sinh. Điều này ngăn Hibernate gom insert theo JDBC batch trong nhiều trường hợp.
- Sequence generator: thường cho phép Hibernate lấy trước các ID và gom insert tốt hơn, tùy database và cấu hình sequence.
- Các chiến lược khác phụ thuộc provider, database và cách triển khai.

Nếu insert batching không hoạt động như mong đợi, hãy kiểm tra chiến lược sinh ID trước khi chỉ tăng `batch_size`.

## 3. Vì sao cần flush và clear khi ghi dữ liệu lớn?

Mỗi entity được quản lý thường được giữ trong persistence context của EntityManager. Hibernate cần theo dõi trạng thái entity để dirty checking và thực hiện các thao tác liên quan. Khi import hàng chục nghìn entity trong một transaction, persistence context có thể chiếm nhiều bộ nhớ.

Một cách xử lý phổ biến là chia danh sách thành các chunk, lưu từng chunk, flush rồi clear:

~~~java
@Service
@RequiredArgsConstructor
public class ProductImportService {
    private static final int CHUNK_SIZE = 500;

    private final ProductRepository productRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importProducts(List<Product> products) {
        for (int start = 0; start < products.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, products.size());
            List<Product> chunk = products.subList(start, end);

            productRepository.saveAll(chunk);
            productRepository.flush();
            entityManager.clear();
        }
    }
}
~~~

Quy trình của mỗi vòng lặp:

1. Lấy tối đa 500 entity.
2. Gọi `saveAll()` để đưa chúng vào quá trình persist/merge.
3. Gọi `flush()` để Hibernate phát các câu lệnh đang chờ; JDBC batching có thể gom chúng theo `hibernate.jdbc.batch_size`.
4. Gọi `clear()` để detach toàn bộ entity đang được quản lý trong persistence context, giải phóng phần lớn trạng thái mà EntityManager theo dõi.

Trong ví dụ, chunk size là 500 còn JDBC batch size là 50. Hai giá trị phục vụ hai mục tiêu khác nhau: chunk size kiểm soát lượng entity giữ trong persistence context; batch size kiểm soát số câu lệnh cùng dạng được gom vào một batch JDBC.

### Flush không phải commit

Đây là khác biệt cần ghi nhớ:

| Thao tác | Ý nghĩa |
|---|---|
| `saveAll()` | Đưa các entity vào quy trình persist/merge |
| `flush()` | Đồng bộ thay đổi đang chờ xuống database |
| `clear()` | Detach toàn bộ entity khỏi persistence context |
| Commit | Hoàn tất transaction; các thay đổi được xác nhận |
| Rollback | Hủy các thay đổi thuộc transaction |

Trong ví dụ chunk ở trên, toàn bộ vòng lặp vẫn nằm trong một transaction vì phương thức có `@Transactional`. Flush và clear theo từng chunk giúp kiểm soát bộ nhớ, nhưng không tạo commit riêng cho mỗi chunk. Transaction vẫn có thể kéo dài tới cuối phương thức và giữ lock lâu.

Nếu muốn mỗi chunk commit độc lập, phải thiết kế ranh giới transaction riêng, ví dụ gọi một bean khác có phương thức `@Transactional` phù hợp hoặc dùng `TransactionTemplate`. Việc này thay đổi tính nguyên tử: nếu chunk sau thất bại, các chunk đã commit trước đó vẫn có thể được giữ lại. Chỉ chọn cách này khi nghiệp vụ chấp nhận xử lý từng phần.

Sau khi gọi `clear()`, mọi entity trước đó trở thành detached. Nếu còn cần thay đổi chúng, phải nạp lại hoặc merge phù hợp. Đừng giữ tham chiếu tới entity cũ rồi giả định nó vẫn được EntityManager quản lý.

## 4. Bulk DML là gì?

Bulk DML là câu lệnh thao tác trực tiếp lên nhiều hàng của database dựa trên một điều kiện, thường là `UPDATE` hoặc `DELETE`. Với Spring Data JPA, cách phổ biến là dùng `@Modifying` cùng `@Query`.

Ví dụ, thay vì tải từng sản phẩm hết hạn về Java, sửa thuộc tính rồi lưu lại, có thể cập nhật trực tiếp bằng một câu JPQL:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Product p
           set p.active = false
         where p.lastPurchasedAt < :cutoff
        """)
    int deactivateBefore(@Param("cutoff") Instant cutoff);
}
~~~

Service gọi repository trong transaction:

~~~java
@Service
@RequiredArgsConstructor
public class ProductMaintenanceService {
    private final ProductRepository productRepository;

    @Transactional
    public int deactivateExpiredProducts(Instant cutoff) {
        return productRepository.deactivateBefore(cutoff);
    }
}
~~~

Câu JPQL trên yêu cầu database cập nhật các hàng phù hợp trong một thao tác DML. Giá trị trả về là số entity instance bị ảnh hưởng theo kết quả thực thi của provider/database.

Bulk delete cũng được viết tương tự:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    delete from Product p
     where p.active = false
       and p.lastPurchasedAt < :cutoff
    """)
int deleteInactiveBefore(@Param("cutoff") Instant cutoff);
~~~

Trong Spring Data JPA, `@Modifying` cho Spring biết rằng query khai báo bằng `@Query` là thao tác thay đổi dữ liệu, không phải truy vấn đọc thông thường. Phương thức cần được thực thi trong transaction đang hoạt động; có thể đặt `@Transactional` ở service như ví dụ trên.

JPQL bulk DML chuẩn tập trung vào `UPDATE` và `DELETE`. Nếu cần insert hàng loạt theo dạng `INSERT ... SELECT`, hãy kiểm tra khả năng của Hibernate HQL, native SQL hoặc JDBC vì đây không phải cú pháp insert chuẩn của JPQL.

## 5. Bulk DML khác gì với thao tác lưu từng entity?

Bulk DML thường nhanh khi cần thay đổi nhiều hàng theo cùng một quy tắc, nhưng nó bỏ qua một phần lớn cơ chế quản lý entity của JPA.

Khi thực hiện bulk update/delete:

- JPA không nạp từng entity bị ảnh hưởng vào persistence context.
- Dirty checking của từng entity không được chạy để tạo câu lệnh cho thao tác bulk đó.
- Entity lifecycle callback như `@PreUpdate`, `@PostUpdate`, `@PreRemove` và listener tương ứng không được gọi cho từng entity bị tác động.
- Cascade remove và `orphanRemoval` không được áp dụng như khi xóa entity qua EntityManager.
- Các entity đang managed trong persistence context có thể vẫn chứa giá trị cũ.
- Thuộc tính `@Version` không tự động được tăng như khi cập nhật entity thông thường; nếu cần, phải thiết kế cập nhật version rõ ràng.

Database vẫn thực thi constraint, trigger và các quy tắc ở tầng database theo cấu hình của nó. Điều bị bỏ qua ở đây là các cơ chế vòng đời entity của JPA, không phải toàn bộ logic ở database.

### Ví dụ về persistence context bị stale

Giả sử service đã nạp một sản phẩm:

~~~java
Product product = productRepository.findById(10L).orElseThrow();
boolean oldActiveValue = product.isActive();
~~~

Sau đó một bulk query cập nhật `active = false` cho sản phẩm đó. Đối tượng `product` đang nằm trong persistence context có thể vẫn trả về giá trị `active` cũ, vì bulk DML chạy trực tiếp ở database và không cập nhật từng object đang managed.

Nếu tiếp tục đọc hoặc sửa entity cũ, ứng dụng có thể làm việc với trạng thái không đồng bộ. Có thể dùng `clearAutomatically = true` để Spring Data JPA clear persistence context sau query, hoặc chủ động gọi `EntityManager.clear()` hay `refresh()` theo tình huống.

### Vai trò của flushAutomatically và clearAutomatically

Hai thuộc tính trong `@Modifying` giải quyết hai thời điểm khác nhau:

- `flushAutomatically = true`: flush persistence context trước khi thực thi query. Những thay đổi JPA đang chờ được gửi xuống database trước bulk DML.
- `clearAutomatically = true`: clear persistence context sau khi query thực thi để tránh tiếp tục dùng các entity managed có thể đã lỗi thời.

Clear tác động lên toàn bộ persistence context của EntityManager hiện tại, không chỉ entity bị query tác động. Các entity khác cũng bị detach. Vì vậy, chỉ bật clear tự động khi luồng xử lý hiểu rõ hệ quả đó.

Nếu không clear, có thể chủ động flush rồi thực hiện bulk DML, sau đó refresh hoặc clear những entity cần thiết. Cần chọn một cách đồng bộ trạng thái rõ ràng thay vì giả định bulk query tự cập nhật các object Java.

## 6. Bulk DML và @Version, auditing, cascade

Bulk DML không đi qua quy trình cập nhật entity thông thường. Một số hệ quả nghiệp vụ cần được xử lý riêng.

### Optimistic locking với @Version

Khi cập nhật entity qua JPA, provider có thể dùng cột version để kiểm tra và tăng version. Bulk JPQL update không tự động thực hiện đầy đủ quy trình đó.

Nếu cần tăng version trong bulk update, có thể đưa phép tăng vào query:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update Product p
       set p.active = false,
           p.version = p.version + 1
     where p.lastPurchasedAt < :cutoff
    """)
int deactivateBefore(@Param("cutoff") Instant cutoff);
~~~

Đây chỉ là ví dụ minh họa. Nếu cần bảo đảm optimistic locking cho từng bản ghi, query còn phải có điều kiện version thích hợp và ứng dụng phải xử lý số hàng bị ảnh hưởng. Không nên xem việc tăng version hàng loạt là tương đương hoàn toàn với kiểm tra version trên từng entity.

### Auditing và lifecycle callback

Các trường được cập nhật thông qua entity listener, chẳng hạn `@LastModifiedDate`, không tự động được gán chỉ vì bulk query thay đổi hàng loạt dữ liệu. Nếu nghiệp vụ cần cập nhật thời gian sửa đổi hoặc người sửa, hãy đưa các giá trị đó trực tiếp vào câu query hoặc xử lý ở tầng database theo chính sách đã chọn.

Tương tự, các listener `@PreUpdate` và `@PreRemove` không chạy cho từng entity trong bulk DML. Nếu listener đang chứa logic bắt buộc, chuyển sang bulk query có thể làm mất hành vi đó.

### Cascade và xóa hàng loạt

Xóa entity thông thường qua `EntityManager.remove()` có thể kích hoạt cascade remove và orphan removal theo mapping. Bulk delete JPQL không gọi `remove()` cho từng entity, nên không áp dụng các cơ chế đó. Hãy bảo đảm quan hệ được xử lý phù hợp bằng câu lệnh riêng, constraint/foreign key hoặc thao tác xóa entity theo cách thông thường.

## 7. Derived delete query và bulk delete khác nhau

Spring Data JPA có thể tạo phương thức xóa từ tên phương thức, ví dụ:

~~~java
void deleteByActiveFalseAndLastPurchasedAtBefore(Instant cutoff);
~~~

Derived delete query kiểu này có thể truy vấn các entity phù hợp rồi xóa từng entity để cho phép lifecycle callback được gọi. Cách làm đó có thể tốn bộ nhớ và nhiều thao tác hơn khi số lượng bản ghi lớn.

Trong khi đó, phương thức dùng `@Modifying` và JPQL `delete` là bulk DML, thực hiện lệnh xóa trực tiếp theo điều kiện và không gọi lifecycle callback cho từng entity.

Ngoài ra, `JpaRepository` cung cấp các phương thức batch delete như `deleteAllInBatch()` hoặc `deleteAllByIdInBatch()`. Chúng cũng thực hiện xóa hàng loạt ở database và có các giới hạn đồng bộ persistence context tương tự bulk operation. Hãy đọc rõ hợp đồng của phương thức trước khi dùng thay cho thao tác xóa entity thông thường.

## 8. So sánh ba cách tiếp cận

| Tiêu chí | `saveAll()` | JDBC batching | Bulk DML |
|---|---|---|---|
| Tầng hoạt động | API Spring Data JPA | Tầng JDBC/provider | JPQL hoặc SQL trực tiếp |
| Đối tượng xử lý | Entity | Nhiều câu SQL cùng dạng | Nhiều hàng theo điều kiện |
| Cần nạp entity | Có, theo quy trình persist/merge | Thường có khi kết hợp JPA | Không cần nạp từng entity |
| Số câu SQL | Có thể nhiều câu | Nhiều câu được gom thành batch | Thường một câu DML cho mỗi query |
| Lifecycle callback | Có theo quy trình JPA | Có khi dùng JPA entity | Không gọi cho từng entity |
| Cascade JPA | Theo mapping | Theo mapping khi dùng JPA | Không chạy như thao tác entity |
| Đồng bộ persistence context | JPA quản lý entity | JPA quản lý entity | Cần tự xử lý trạng thái stale |
| Phù hợp | Lưu nhiều entity cần semantics JPA | Tối ưu lưu/update entity theo lô | Cập nhật/xóa tập dữ liệu theo điều kiện |

Điểm quan trọng: JDBC batching có thể được dùng cùng `saveAll()`. Bulk DML là chiến lược khác, đánh đổi một số semantics của entity để thực hiện thay đổi trực tiếp và hiệu quả ở database.

## 9. Chọn phương án nào trong thực tế?

**Chọn `saveAll()` khi:**

- Bạn có một danh sách entity cần lưu theo mapping JPA.
- Cần cascade persist/merge hoặc lifecycle callback.
- Cần dùng các giá trị và quan hệ của entity trong luồng nghiệp vụ.
- Số lượng entity vừa phải hoặc có thể chia chunk để quản lý bộ nhớ.

**Kết hợp `saveAll()` với JDBC batching khi:**

- Vẫn cần semantics của JPA nhưng muốn giảm số lần gửi SQL.
- Nhiều entity phát sinh câu lệnh SQL cùng dạng.
- Provider, JDBC driver và chiến lược ID hỗ trợ batching.
- Đã đo và xác nhận cấu hình batch cải thiện thời gian xử lý.

**Chọn bulk DML khi:**

- Cần cập nhật hoặc xóa nhiều hàng theo một điều kiện đơn giản.
- Không cần nạp từng entity và không cần lifecycle callback cho từng entity.
- Đã xử lý rõ version, auditing, cascade và trạng thái persistence context.
- Có thể kiểm thử đầy đủ tác động của query trực tiếp lên dữ liệu.

Ví dụ, import 20.000 sản phẩm mới thường phù hợp với `saveAll()` kết hợp JDBC batching và flush/clear theo chunk. Ngược lại, vô hiệu hóa toàn bộ sản phẩm không được mua trong 2 năm có thể phù hợp với một bulk update JPQL, nếu nghiệp vụ không phụ thuộc vào callback của từng sản phẩm.

## 10. Kiểm tra batching và hiệu năng

Không nên kết luận batching đã hoạt động chỉ vì đã cấu hình `hibernate.jdbc.batch_size`. Hãy kiểm tra thực tế bằng log Hibernate phù hợp với phiên bản, Hibernate statistics hoặc công cụ quan sát JDBC như datasource proxy/P6Spy.

Các điểm cần đo:

1. Số lượng SQL insert/update/delete thực tế.
2. Số lần thực thi batch và số câu lệnh trong mỗi batch.
3. Thời gian tổng thể và thời gian chờ database.
4. Mức sử dụng heap khi import dữ liệu lớn.
5. Thời gian giữ transaction và lock.
6. Tính đúng đắn của dữ liệu, callback, cascade, version và auditing.

Có thể bật Hibernate statistics trong môi trường kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics giúp quan sát hoạt động của Hibernate, nhưng không thay thế việc đo ở JDBC driver hoặc database. Tắt cấu hình thống kê nếu không cần trong môi trường production vì việc thu thập số liệu cũng có chi phí.

Không tăng batch size vô hạn. Batch quá lớn có thể làm tăng bộ nhớ, thời gian flush hoặc áp lực lên driver/database. Hãy thử một vài giá trị, đo trên dữ liệu và database gần với môi trường thật, rồi chọn theo kết quả.

## 11. Checklist trước khi triển khai thao tác hàng loạt

- Xác định cần lưu entity theo semantics JPA hay chỉ cập nhật/xóa hàng theo điều kiện.
- Nếu dùng `saveAll()`, kiểm tra entity mới/đã tồn tại và hành vi persist/merge.
- Nếu dùng JDBC batching, kiểm tra Hibernate version, JDBC driver, database và chiến lược sinh ID.
- Đặt batch size và chunk size theo hai mục tiêu riêng biệt.
- Với dữ liệu lớn, cân nhắc flush/clear để giới hạn persistence context.
- Nhớ rằng flush/clear không commit; transaction vẫn có thể rất dài.
- Với bulk DML, kiểm tra callback, cascade, orphan removal, auditing và `@Version`.
- Xử lý persistence context stale sau bulk update/delete.
- Kiểm tra số hàng bị ảnh hưởng và ràng buộc dữ liệu.
- Viết integration test và đo hiệu năng trước khi áp dụng trên khối lượng production.

## Kết luận

`saveAll()` là API lưu nhiều entity của Spring Data JPA; nó thường gọi persist hoặc merge cho từng entity. JDBC batching là tối ưu hóa ở tầng JDBC, có thể kết hợp với `saveAll()` để gom các câu lệnh SQL cùng dạng. Bulk DML thực hiện update/delete trực tiếp trên tập hàng của database, nhanh và ít tốn bộ nhớ hơn trong nhiều trường hợp nhưng bỏ qua lifecycle callback, cascade và đồng bộ entity trong persistence context. Hãy chọn dựa trên semantics nghiệp vụ cần giữ, sau đó xác minh batching và hiệu năng bằng số liệu thực tế.