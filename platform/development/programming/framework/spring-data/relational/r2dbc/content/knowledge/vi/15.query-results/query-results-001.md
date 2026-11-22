# Chọn thực thể đầy đủ hay chỉ các cột cần dùng

Khi truy vấn bằng Spring Data Relational R2DBC, ứng dụng có thể lấy một entity đầy đủ hoặc chỉ chọn một số cột cần thiết. Hai cách đều hợp lệ, nhưng phục vụ những mục đích khác nhau.

**Nên lấy entity đầy đủ khi nghiệp vụ cần làm việc với trạng thái và hành vi của entity hoặc aggregate. Nên chỉ lấy các cột cần dùng khi mục tiêu là đọc, hiển thị, tìm kiếm, thống kê hoặc xuất dữ liệu.** Kết quả đọc một phần thường nên được ánh xạ thành DTO hoặc projection riêng, không nên giả làm entity đầy đủ rồi đưa lại vào repository để lưu.

Lựa chọn này ảnh hưởng đến lượng dữ liệu truyền qua mạng, công việc mapping, bộ nhớ, khả năng bảo vệ dữ liệu và độ an toàn khi cập nhật. Trong R2DBC, ứng dụng thường chủ động viết SQL và mapping kết quả, vì vậy cần hiểu rõ dữ liệu nào được chọn và kiểu đối tượng nào đang nhận dữ liệu đó.

## 1. Entity đầy đủ và projection khác nhau thế nào?

Giả sử bảng customer có các cột:

| Cột | Ý nghĩa |
|---|---|
| id | Mã khách hàng |
| name | Tên hiển thị |
| email | Địa chỉ email |
| status | Trạng thái nghiệp vụ |
| active | Có đang hoạt động hay không |
| created_at | Thời điểm tạo |
| internal_note | Ghi chú nội bộ |
| profile_json | Dữ liệu hồ sơ có thể khá lớn |
| version | Phiên bản dùng cho optimistic locking |

Một entity Customer có thể ánh xạ các thuộc tính persistence tương ứng:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private String email;
    private String status;
    private boolean active;
    private Instant createdAt;
    private String internalNote;
    private String profileJson;

    public void changeStatus(String newStatus) {
        // Áp dụng quy tắc nghiệp vụ tại đây.
        this.status = newStatus;
    }
}
~~~

Nếu ứng dụng tải một Customer đầy đủ, truy vấn cần lấy những cột được mapping cho entity:

~~~sql
SELECT id, version, name, email, status, active,
       created_at, internal_note, profile_json
FROM customer
WHERE id = :id;
~~~

Ngược lại, trang danh sách khách hàng có thể chỉ cần mã, tên và trạng thái:

~~~sql
SELECT id, name, status
FROM customer
WHERE active = :active;
~~~

Kết quả truy vấn thứ hai không phải Customer đầy đủ. Nó chỉ là một phần dữ liệu phục vụ một mục đích đọc cụ thể. Nên ánh xạ nó thành một kiểu riêng như CustomerListItem.

## 2. Khi nào nên lấy entity đầy đủ?

Lấy entity đầy đủ khi code cần trạng thái và hành vi của đối tượng domain, đặc biệt nếu cần lưu thay đổi sau đó.

Các tình huống thường phù hợp:

- Người dùng mở chi tiết một khách hàng để thực hiện thao tác nghiệp vụ.
- Service cần kiểm tra trạng thái hiện tại trước khi cho phép thay đổi.
- Nghiệp vụ cần nhiều thuộc tính của aggregate để đánh giá invariant.
- Ứng dụng thay đổi entity rồi gọi repository save().
- Cần dùng thuộc tính version hiện tại để optimistic locking.
- Cần làm việc với các thành phần thuộc aggregate mà mapping của Spring Data Relational hỗ trợ.

Ví dụ tải khách hàng, kiểm tra điều kiện và cập nhật trạng thái:

~~~java
public Mono<Customer> deactivate(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            if ("CLOSED".equals(customer.getStatus())) {
                return Mono.error(
                    new IllegalStateException(
                        "A closed customer cannot be deactivated"
                    )
                );
            }

            customer.changeStatus("INACTIVE");
            return customerRepository.save(customer);
        });
}
~~~

Trong luồng này, service cần trạng thái hiện tại để áp dụng quy tắc nghiệp vụ. Entity đầy đủ phù hợp hơn một projection chỉ có tên và ID.

Một repository có thể trả entity:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
~~~

Phương thức findByStatus trả các Customer được mapping theo entity metadata. Nếu caller cần thay đổi và lưu các Customer này, việc lấy entity là hợp lý. Nếu caller chỉ cần đếm hoặc hiển thị một vài trường, tải toàn bộ entity có thể là công việc không cần thiết.

## 3. Khi nào chỉ nên lấy các cột cần dùng?

Chỉ lấy một phần cột khi truy vấn phục vụ đọc và caller không cần hành vi hoặc toàn bộ trạng thái của entity.

Ví dụ:

- Bảng danh sách chỉ hiển thị ID, tên, email và trạng thái.
- Dropdown chỉ cần ID và nhãn.
- Dashboard chỉ cần tổng số khách hàng theo trạng thái.
- Báo cáo cần dữ liệu từ nhiều bảng qua JOIN và GROUP BY.
- File export chỉ cần một tập trường đã xác định.
- Tìm kiếm chỉ cần các trường dùng để hiển thị kết quả.
- Một màn hình không được phép nhận dữ liệu nội bộ như internal_note.

Lợi ích:

1. Giảm số byte database phải gửi về ứng dụng.
2. Giảm dữ liệu driver phải giải mã và framework phải mapping.
3. Giảm số object hoặc lượng bộ nhớ cần giữ khi kết quả có nhiều dòng.
4. Hạn chế đưa dữ liệu không cần thiết hoặc nhạy cảm vào tầng ứng dụng.
5. Làm rõ hợp đồng dữ liệu mà một use case đọc cần.

Ví dụ, một trang danh sách 5.000 khách hàng chỉ cần ba trường. Nếu mỗi dòng còn chứa một cột JSON lớn hoặc ghi chú nội bộ, tải toàn bộ entity sẽ tốn tài nguyên mà giao diện không sử dụng.

## 4. Dùng DTO hoặc projection cho kết quả đọc một phần

Một DTO có thể mô tả chính xác dữ liệu mà màn hình cần:

~~~java
public record CustomerListItem(
    Long id,
    String name,
    String status
) {
}
~~~

Truy vấn và mapping bằng DatabaseClient:

~~~java
Flux<CustomerListItem> items =
    databaseClient.sql(
        "SELECT id, name, status " +
        "FROM customer " +
        "WHERE active = :active " +
        "ORDER BY name"
    )
    .bind("active", true)
    .map((row, metadata) -> new CustomerListItem(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    ))
    .all();
~~~

Đoạn code thể hiện rõ bốn bước:

1. Chọn đúng cột cần dùng trong SELECT.
2. Bind điều kiện active như một giá trị, không nối dữ liệu vào SQL.
3. Đọc từng cột theo tên và kiểu Java.
4. Tạo CustomerListItem cho mỗi dòng.

Vì kết quả có thể có nhiều dòng nên dùng Flux. Nếu truy vấn chỉ trả về một kết quả, có thể dùng one() hoặc first() theo semantics mong muốn của DatabaseClient.

### Đặt alias cho cột

Khi truy vấn có JOIN hoặc biểu thức tính toán, nên đặt alias rõ ràng:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id
GROUP BY c.id, c.name;
~~~

DTO tương ứng:

~~~java
public record CustomerOrderSummary(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

Mapping thủ công:

~~~java
Flux<CustomerOrderSummary> summaries =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderSummary(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
~~~

Alias làm cho mapping dễ đọc và tránh nhầm hai cột cùng tên từ các bảng khác nhau. Kiểu Java của các giá trị như COUNT hoặc SUM cần phù hợp với kiểu trả về của database và R2DBC driver.

## 5. Projection là gì?

Projection là cách biểu diễn một phần dữ liệu cần đọc từ một đối tượng hoặc kết quả truy vấn. DTO là một cách phổ biến để định nghĩa projection bằng class hoặc record.

Ví dụ một projection chỉ chứa thông tin hiển thị:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

Trong những phiên bản và kiểu truy vấn Spring Data R2DBC hỗ trợ interface projection, repository có thể trả về projection thay vì entity:

~~~java
@Query("SELECT id, name FROM customer WHERE status = :status")
Flux<CustomerNameView> findNamesByStatus(
    @Param("status") String status
);
~~~

Khả năng và cách ánh xạ projection cụ thể phụ thuộc phiên bản Spring Data Relational đang dùng và dạng query. Với truy vấn JOIN, alias hoặc biểu thức phức tạp, DTO cùng DatabaseClient thường giúp mapping tường minh hơn.

Không nên giả định mọi projection đều tự động hoạt động giống JPA. Cần kiểm tra kiểu projection, tên cột, constructor và API thực tế của phiên bản framework trong dự án.

## 6. Vì sao không nên map thiếu cột vào entity đầy đủ?

Một lỗi nguy hiểm là chọn ít cột nhưng vẫn yêu cầu mapping vào Customer:

~~~sql
SELECT id, name
FROM customer
WHERE id = :id;
~~~

~~~java
Mono<Customer> customer =
    databaseClient.sql(sql)
        .map((row, metadata) -> /* map một Customer */)
        .one();
~~~

Hoặc dùng một query mapping entity nhưng chỉ chọn một phần thuộc tính. Khi các cột không được trả về, những thuộc tính tương ứng trong object có thể mang giá trị mặc định như null, false hoặc 0, tùy kiểu thuộc tính và cách mapping.

Object này không còn đại diện an toàn cho trạng thái đầy đủ của dòng dữ liệu. Ví dụ:

| Thuộc tính | Giá trị trong database | Giá trị trên object đọc thiếu cột |
|---|---|---|
| id | 42 | 42 |
| name | An | An |
| email | an@example.com | null |
| status | ACTIVE | null |
| active | true | false |
| internalNote | Gọi lại tuần sau | null |

Nếu sau đó ứng dụng gọi repository save() với object thiếu dữ liệu, các trường chưa được đọc có thể bị ghi thành null hoặc giá trị mặc định tùy cơ chế persistence và mapping. Điều này có thể làm mất dữ liệu đang có trong database.

Ngay cả khi entity có @Version, optimistic locking chỉ kiểm tra bản ghi có còn ở version mong đợi hay không. Nó không tự khôi phục những trường đã bị bỏ khỏi object. Một update partial object có thể vẫn khớp version và ghi các giá trị mặc định vào cột khác.

**Quy tắc thực hành:** nếu kết quả chỉ có một phần cột, ánh xạ nó thành DTO/projection chỉ dùng để đọc. Không đưa object đó vào luồng save như một entity đầy đủ.

## 7. Không nhầm partial projection với partial update

Hai khái niệm này khác nhau:

- **Partial projection:** truy vấn chỉ lấy một số cột để đọc.
- **Partial update:** câu lệnh chỉ cập nhật một số cột được chỉ định.

Ví dụ partial projection:

~~~sql
SELECT id, name
FROM customer
WHERE id = :id;
~~~

Ví dụ partial update:

~~~sql
UPDATE customer
SET name = :name
WHERE id = :id;
~~~

Partial projection không tự tạo ra một cơ chế partial update an toàn. Nếu map kết quả thiếu cột vào entity rồi save, ứng dụng có thể vô tình ghi đè các cột khác.

Nếu use case chỉ cần đổi tên và không cần toàn bộ entity, có thể viết một lệnh update tường minh:

~~~java
public Mono<Long> rename(Long id, String newName) {
    return databaseClient.sql(
            "UPDATE customer SET name = :name WHERE id = :id"
        )
        .bind("name", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

Ứng dụng cần diễn giải số dòng được cập nhật. Nếu cần optimistic locking, câu SQL tự viết cũng phải thêm điều kiện version và tăng version tương ứng. Annotation @Version trên entity không tự sửa một câu SQL tùy chỉnh trong DatabaseClient.

## 8. Full entity không có nghĩa là tải mọi quan hệ như ORM

Trong Spring Data Relational, entity được ánh xạ theo mapping metadata và mô hình aggregate. Không nên suy luận rằng lấy một entity đầy đủ sẽ có toàn bộ object graph được tải lazy hoặc tự động như một ORM JPA/Hibernate.

Một entity có thể chứa:

- Các thuộc tính scalar được ánh xạ thành cột.
- Value object được embedded.
- Các thành phần aggregate mà mapping Spring Data Relational hỗ trợ.
- Tham chiếu đến aggregate khác thông qua ID.

Các quan hệ và aggregate cần được thiết kế theo quy tắc Spring Data Relational. Nếu màn hình cần dữ liệu từ nhiều aggregate hoặc nhiều bảng, một truy vấn projection với JOIN có thể phù hợp hơn việc cố tải một entity graph lớn.

Full entity nghĩa là đủ các thuộc tính persistence mà mô hình entity yêu cầu cho use case, không có nghĩa database phải trả tất cả cột của mọi bảng liên quan.

## 9. Tác động đến hiệu năng

Chọn ít cột có thể cải thiện hiệu năng, đặc biệt khi bảng có nhiều cột lớn hoặc truy vấn trả về nhiều dòng.

### Lượng dữ liệu truyền về

Nếu truy vấn trả 10.000 dòng và mỗi dòng có cột JSON lớn, lấy thêm cột đó có thể làm tăng đáng kể lượng dữ liệu truyền qua mạng. Nếu màn hình chỉ cần ID và tên, các cột còn lại không đem lại giá trị cho use case.

### Mapping và cấp phát object

Lấy entity đầy đủ có thể cần đọc và chuyển đổi nhiều cột, tạo object có nhiều trường và giữ dữ liệu trong bộ nhớ. Projection nhỏ hơn thường giảm công việc mapping và lượng dữ liệu sống trong heap.

### Index-only access

Trong một số database, nếu các cột được truy vấn nằm trong index phù hợp, optimizer có thể đọc dữ liệu từ index mà không cần truy cập toàn bộ row. Khả năng này phụ thuộc database, index, visibility và execution plan; chỉ bỏ cột khỏi SELECT không bảo đảm query sẽ dùng index-only scan.

### Không nên tối ưu bằng cách bỏ cột một cách máy móc

Nếu use case cần trạng thái, version hoặc các trường dùng để kiểm tra invariant, bỏ chúng có thể khiến logic nghiệp vụ sai. Hiệu năng cần được cân bằng với tính đúng đắn và khả năng bảo vệ cập nhật đồng thời.

## 10. Tác động đến bảo mật và quyền riêng tư

Chọn cột có chủ đích cũng giúp hạn chế dữ liệu được đưa vào tầng ứng dụng.

Ví dụ một màn hình danh sách không cần internal_note hoặc profile_json. Không truy vấn các cột này sẽ giảm nguy cơ chúng bị ghi log, được serialize nhầm hoặc truyền đến một thành phần không cần biết.

DTO còn giúp định nghĩa rõ hợp đồng đầu ra:

~~~java
public record CustomerPublicView(
    Long id,
    String displayName,
    String status
) {
}
~~~

API có thể trả CustomerPublicView mà không phơi bày email nội bộ, ghi chú hoặc dữ liệu hồ sơ. Không nên dựa vào việc serializer “chắc sẽ bỏ qua” các trường nhạy cảm trong entity.

Tuy vậy, projection không thay thế authorization. Query vẫn phải có điều kiện tenant, ownership và quyền truy cập bắt buộc. Chọn ít cột không giúp ích nếu truy vấn lấy dữ liệu của người dùng không có quyền.

## 11. Chọn giữa Repository, R2dbcEntityTemplate và DatabaseClient

Các abstraction trong Spring Data R2DBC phù hợp với những kiểu truy vấn khác nhau:

| Công cụ | Phù hợp với | Kết quả thường gặp |
|---|---|---|
| ReactiveCrudRepository | CRUD và thao tác theo ID hoặc query method | Entity hoặc aggregate |
| Repository projection | Truy vấn method có projection được framework hỗ trợ | Interface projection hoặc DTO |
| R2dbcEntityTemplate | Các thao tác entity có điều kiện động và mapping theo metadata | Entity |
| DatabaseClient | SQL tùy chỉnh, JOIN, aggregate query và read model | DTO hoặc kiểu dữ liệu tự ánh xạ |

Ví dụ dùng repository để tải entity đầy đủ:

~~~java
Mono<Customer> customer = customerRepository.findById(id);
~~~

Ví dụ dùng DatabaseClient để lấy một read model:

~~~java
Mono<CustomerHeader> header =
    databaseClient.sql(
            "SELECT id, name, status " +
            "FROM customer WHERE id = :id"
        )
        .bind("id", id)
        .map((row, metadata) -> new CustomerHeader(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("status", String.class)
        ))
        .one();
~~~

Hai kết quả có mục đích khác nhau. Customer phù hợp với thao tác domain/persistence; CustomerHeader chỉ cung cấp dữ liệu cần hiển thị.

## 12. Chọn entity hay DTO theo từng use case

| Use case | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Đọc chi tiết để thực hiện nghiệp vụ | Entity đầy đủ | Cần trạng thái và hành vi domain |
| Đổi trạng thái có kiểm tra điều kiện | Entity đầy đủ, thường có version | Cần kiểm tra invariant và optimistic locking |
| Hiển thị bảng danh sách | DTO/projection | Chỉ cần một số trường |
| Dropdown chọn khách hàng | Projection nhỏ | Chỉ cần ID và nhãn |
| Báo cáo tổng số theo trạng thái | DTO kết quả tổng hợp | Kết quả không phải entity |
| Xuất file với các cột xác định | DTO/projection | Hợp đồng dữ liệu rõ và hạn chế cột |
| Cập nhật một cột độc lập | Direct UPDATE có bind | Không cần tải toàn bộ entity nếu nghiệp vụ cho phép |
| Xử lý aggregate có nhiều quy tắc | Entity/aggregate đầy đủ | Cần dữ liệu để bảo vệ tính nhất quán nghiệp vụ |
| Tìm kiếm trên nhiều bảng | Projection/DTO qua JOIN | Kết quả đọc có cấu trúc riêng |

Một ứng dụng có thể dùng cả hai cách trong cùng một module. Không cần chọn một chiến lược duy nhất cho tất cả truy vấn.

## 13. Thiết kế hai mô hình đọc và ghi

Với ứng dụng có nhiều truy vấn đọc, có thể tách kiểu dữ liệu cho command và query:

~~~text
                    COMMAND / WRITE
API request
    |
    v
Application Service
    |
    v
Load Customer aggregate
    |
    v
Kiểm tra invariant và thay đổi trạng thái
    |
    v
CustomerRepository.save()
    |
    v
Database

                     QUERY / READ
API query
    |
    v
Query Service
    |
    v
DatabaseClient / projection query
    |
    v
CustomerListItem / CustomerSummary
    |
    v
API response
~~~

Đây là cách phân chia trách nhiệm, không bắt buộc phải triển khai CQRS đầy đủ. Command cần mô hình phù hợp để bảo vệ quy tắc nghiệp vụ; query có thể chọn cấu trúc dữ liệu phù hợp với màn hình hoặc báo cáo.

Tách read model giúp tránh ép mọi truy vấn phải trả về entity. Ngược lại, không nên tạo một DTO cho mọi trường hợp nếu repository trả entity đơn giản đã đủ và không gây tải dư thừa đáng kể.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng SELECT * cho mọi truy vấn | Đọc cột không cần thiết | Chọn cột theo use case |
| Chọn ít cột nhưng map vào entity đầy đủ | Trường không đọc có thể thành null hoặc giá trị mặc định | Dùng DTO/projection riêng |
| Lưu object được tạo từ partial projection | Có thể ghi đè dữ liệu không được tải | Không đưa read projection vào save() |
| Dùng DTO cho nghiệp vụ cần invariant | Thiếu trạng thái cần kiểm tra | Tải aggregate/entity phù hợp |
| Tải full entity cho bảng danh sách lớn | Tăng I/O, mapping và bộ nhớ | Dùng projection nhỏ |
| Dùng DTO nhưng truy vấn vẫn SELECT * | Không giảm lượng dữ liệu đọc | Đồng bộ SELECT list với DTO |
| Quên alias trong JOIN | Nhầm cột trùng tên | Đặt alias và map rõ ràng |
| Bỏ cột version khi định cập nhật entity | Thiếu token optimistic locking | Tải entity đầy đủ hoặc quản lý version tường minh |
| Cho rằng full entity tự tải lazy relation | Hiểu sai hành vi Spring Data Relational | Thiết kế aggregate và query theo mapping của module |
| Dùng projection thay cho authorization | Vẫn có thể đọc dữ liệu ngoài quyền | Giữ predicate quyền truy cập trong query |

## 15. Quy trình quyết định

Trước khi viết một truy vấn, có thể lần lượt tự hỏi:

1. Caller cần thực hiện nghiệp vụ hay chỉ đọc để hiển thị?
2. Có cần kiểm tra trạng thái, invariant hoặc hành vi trên aggregate không?
3. Có cần lưu lại object bằng repository save() không?
4. Cần những thuộc tính nào để hoàn thành use case?
5. Có cột lớn hoặc nhạy cảm nào không cần lấy không?
6. Kết quả có phải dữ liệu ghép từ nhiều bảng hoặc phép tổng hợp không?
7. Nếu chỉ lấy một phần cột, đã tạo DTO/projection riêng chưa?
8. Nếu cần cập nhật trực tiếp, đã kiểm tra affected rows và version chưa?
9. Query có predicate tenant/authorization bắt buộc không?
10. Đã kiểm thử mapping và kiểu dữ liệu với R2DBC driver/database thực tế chưa?

Nếu use case cần thay đổi entity, hãy lấy đủ trạng thái mà mô hình yêu cầu. Nếu use case chỉ đọc, hãy lấy đúng dữ liệu mà caller cần và ánh xạ vào kiểu kết quả phù hợp.

## 16. Ghi nhớ

- Lấy entity đầy đủ khi cần hành vi domain, invariant, aggregate state hoặc cập nhật qua repository.
- Chỉ lấy các cột cần dùng khi truy vấn phục vụ đọc, danh sách, dropdown, báo cáo hoặc export.
- Projection/DTO là kiểu kết quả đọc; không mặc định là entity persistence.
- Không map một phần cột vào entity đầy đủ rồi gọi save(), vì trường bị thiếu có thể mang null hoặc giá trị mặc định và gây ghi đè dữ liệu.
- Partial projection và partial update là hai khái niệm khác nhau.
- DatabaseClient phù hợp với SQL tùy chỉnh và mapping DTO tường minh; repository phù hợp với CRUD và aggregate.
- Chọn cột phù hợp giúp giảm I/O, mapping, bộ nhớ và dữ liệu nhạy cảm đi qua ứng dụng.
- Full entity không đồng nghĩa với lazy-loading object graph như JPA/Hibernate.
- Projection không thay thế authorization; tenant và quyền truy cập vẫn phải được áp dụng trong truy vấn.
- Một ứng dụng có thể kết hợp mô hình entity cho ghi và DTO/projection cho đọc tùy use case.
