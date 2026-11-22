# Phân biệt thay đổi thực thể trong bộ nhớ với ghi thay đổi xuống cơ sở dữ liệu

Trong Spring Data Relational R2DBC, một entity được đọc từ repository là một object Java chứa dữ liệu của hàng tại thời điểm truy vấn. Sau khi nhận object đó, ứng dụng có thể thay đổi field, gọi setter hoặc tạo một instance mới. Những thao tác này chỉ thay đổi trạng thái trong bộ nhớ của ứng dụng. Chúng không tự động cập nhật hàng trong database.

R2DBC không dùng persistence context và cơ chế dirty checking như JPA/Hibernate. Spring Data Relational không theo dõi mọi entity đã đọc để tự phát hiện field nào bị thay đổi rồi tự flush khi transaction kết thúc. Muốn ghi dữ liệu, ứng dụng phải thực hiện một thao tác persistence tường minh như `repository.save(...)`, `R2dbcEntityTemplate.update(...)` hoặc câu SQL qua `DatabaseClient`.

Đây là khác biệt quan trọng khi thiết kế service reactive: thay đổi object là thao tác Java đồng bộ trong bộ nhớ; ghi database là thao tác I/O reactive, thường chỉ bắt đầu khi publisher được subscribe và chỉ được xác nhận bền vững sau khi transaction commit thành công.

## 1. Hai trạng thái khác nhau: object Java và hàng trong database

Giả sử database có hàng:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

INSERT INTO customer (id, name) VALUES (10, 'Lan');
```

Repository đọc hàng đó:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

Khi publisher được tiêu thụ, Spring Data đọc hàng và ánh xạ thành object Java. Ví dụ object nhận được có trạng thái:

```java
Customer customer = new Customer(10L, "Lan");
```

Sau đó ứng dụng gọi:

```java
customer.setName("Lan Nguyen");
```

Giá trị trong object Java bây giờ là `Lan Nguyen`, nhưng hàng trong database vẫn là `Lan`. Setter chỉ gán một field trên object hiện tại; nó không gửi SQL và không thông báo cho database.

Có thể phân biệt như sau:

| Hành động | Trạng thái object Java | Trạng thái database |
| --- | --- | --- |
| Đọc entity bằng `findById` | Tạo/nhận object chứa dữ liệu vừa đọc | Không thay đổi |
| Gọi setter hoặc thay đổi field | Thay đổi ngay trong bộ nhớ | Không thay đổi |
| Tạo object mới với dữ liệu khác | Có instance mới trong bộ nhớ | Không thay đổi |
| Tạo publisher từ `save(entity)` | Có mô tả thao tác lưu | Chưa chắc đã có SQL được thực thi |
| Subscribe publisher `save` | Pipeline bắt đầu xử lý | Thực hiện INSERT/UPDATE theo trạng thái entity |
| Transaction commit thành công | Ứng dụng nhận kết quả lưu | Thay đổi được commit vào database |
| Transaction rollback | Object Java không tự quay lại trạng thái trước đó | Thay đổi trong transaction bị rollback theo database |

Một object Java không phải là bản sao sống liên kết với hàng trong database. Nó chỉ là dữ liệu ứng dụng đang giữ. Nếu một transaction khác cập nhật cùng hàng, object đang nằm trong bộ nhớ cũng không tự thay đổi theo.

## 2. R2DBC không có dirty checking như JPA

Trong JPA/Hibernate, entity được quản lý bởi persistence context. Khi entity đang managed bị thay đổi, ORM có thể phát hiện khác biệt so với snapshot ban đầu và tạo SQL update trong quá trình flush. Với R2DBC/Spring Data Relational, vòng đời entity không hoạt động theo cách đó.

Repository R2DBC thường ánh xạ kết quả truy vấn thành object và phát object qua `Mono` hoặc `Flux`. Sau khi object được phát ra, Spring Data không giữ một persistence context để tiếp tục giám sát các thay đổi Java của object đó.

Ví dụ:

```java
public Mono<Void> renameWithoutSaving(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("Lan Nguyen"))
            .then();
}
```

Phương thức này thực hiện truy vấn đọc, sau đó thay đổi tên trong object nhận được và kết thúc luồng. Không có thao tác `save`, `UPDATE` hoặc lệnh ghi nào khác. Database vẫn giữ tên cũ.

Đặt phương thức trong một service có `@Transactional` cũng không làm thay đổi kết quả:

```java
@Transactional
public Mono<Void> renameWithoutSaving(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("Lan Nguyen"))
            .then();
}
```

Transaction cung cấp ranh giới commit/rollback cho các thao tác database được thực thi trong pipeline. Nó không tự phát hiện field Java bị thay đổi và không tự flush entity. Nếu pipeline chỉ đọc và sửa object trong bộ nhớ, transaction không có câu lệnh ghi nào để commit.

Không nên chuyển nguyên giả định từ JPA sang R2DBC. Trong code reactive, hãy tìm rõ thao tác nào tạo SQL ghi và publisher nào được tiêu thụ để thao tác đó thực sự chạy.

## 3. Ghi thay đổi bằng `repository.save(...)`

Với repository kế thừa `ReactiveCrudRepository`, cách thông dụng để lưu trạng thái entity là gọi `save` và nối publisher trả về vào pipeline:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Customer không tồn tại: " + id)
            ))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
```

Trình tự thực hiện:

1. `findById` đọc hàng và phát ra entity.
2. `flatMap` nhận entity khi có dữ liệu.
3. Setter thay đổi trạng thái object Java trong bộ nhớ.
4. `save(customer)` tạo publisher đại diện cho thao tác lưu.
5. Khi pipeline được subscribe, thao tác lưu được thực thi và kết quả được phát ra.

Ở đây thay đổi object và ghi database là hai bước riêng biệt, dù chúng nằm trong cùng một pipeline. Nếu bỏ `save(customer)`, chỉ có bước thay đổi trong bộ nhớ.

### `save` chọn INSERT hay UPDATE

`save` có thể thực hiện insert hoặc update tùy cơ chế nhận diện entity mới của Spring Data Relational. Với entity thông thường không triển khai `Persistable` và không có `@Version`, identifier được đánh dấu `@Id` tham gia quyết định: ID chưa được gán thường biểu thị entity mới; ID đã có giá trị thường biểu thị entity đã tồn tại. Nếu có `@Version`, version được ưu tiên; nếu triển khai `Persistable`, `isNew()` của entity được dùng.

Vì vậy, `save` không phải lúc nào cũng là câu `UPDATE`. Khi cần hiểu chính xác hành vi, phải xét trạng thái entity và metadata của nó. `save` cũng không mặc định truy vấn database để xác minh rằng ID đang có thực sự tồn tại.

### Dùng object được phát ra từ `save`

Hãy dùng giá trị do publisher `save` phát ra:

```java
return customerRepository.save(customer)
        .map(saved -> new CustomerView(saved.getId(), saved.getName()));
```

Điều này quan trọng khi database sinh ID, Spring Data quản lý `@Version`, hoặc entity bất biến. Với immutable entity, framework có thể tạo instance mới chứa generated ID/version thay vì sửa instance ban đầu. Dùng object được phát ra giúp tầng trên nhận đúng trạng thái sau thao tác lưu.

Không nên chỉ gọi `save` rồi tiếp tục đọc ID hoặc version từ object đầu vào với giả định object đó luôn được cập nhật tại chỗ.

## 4. Publisher reactive và thời điểm ghi thật sự

Các thao tác repository R2DBC thường trả publisher lạnh và trì hoãn I/O database đến khi có subscription. Điều này có nghĩa gọi `save` và thực thi câu lệnh ghi là hai thời điểm khác nhau.

Ví dụ:

```java
Mono<Customer> pendingSave = customerRepository.save(customer);
```

Dòng code trên tạo publisher. Nếu không có thành phần nào subscribe publisher, thao tác ghi không bắt đầu. Một controller WebFlux có thể trả publisher cho framework để framework tiêu thụ; trong kiểm thử, `StepVerifier` subscribe khi chạy verification.

### Nối publisher để thao tác ghi được thực thi

Đúng:

```java
public Mono<Customer> updateName(Long id, String name) {
    return customerRepository.findById(id)
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            });
}
```

Không nên tách subscription khỏi pipeline:

```java
public Mono<Customer> updateName(Long id, String name) {
    customerRepository.findById(id)
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            })
            .subscribe();

    return Mono.empty();
}
```

Trong ví dụ thứ hai, service tự tạo một subscription độc lập rồi trả về một publisher khác. Tầng gọi không thể chờ kết quả lưu thông qua publisher trả về; lỗi và vòng đời của thao tác cũng bị tách khỏi luồng mà framework đang quản lý. Nếu có transaction reactive ở tầng gọi, subscription tự tạo còn có thể nằm ngoài transaction context đó.

Hãy trả publisher hoàn chỉnh cho tầng gọi và để framework hoặc ranh giới ứng dụng phù hợp subscribe. Không cần gọi `subscribe()` bên trong service chỉ để kích hoạt ghi.

### Tránh sửa object trong lúc publisher đang chờ subscription

Thay đổi field Java xảy ra ngay khi setter được gọi, còn thao tác database thường bắt đầu khi publisher được subscribe. Nếu tạo publisher lưu rồi tiếp tục thay đổi cùng object trước khi publisher được tiêu thụ, code trở nên khó hiểu và có nguy cơ ghi dữ liệu không theo ý định ban đầu.

Ví dụ không nên dựa vào:

```java
Mono<Customer> pending = customerRepository.save(customer);
customer.setName("Một tên khác");
return pending;
```

Không nên dựa vào việc pipeline sẽ chụp snapshot entity tại đúng dòng tạo publisher. Hãy hoàn tất thay đổi trước khi tạo publisher lưu, hoặc dùng một instance bất biến riêng cho lần ghi. Tránh chia sẻ cùng một mutable entity giữa nhiều pipeline hoặc thread.

## 5. Dùng entity bất biến để làm rõ trạng thái trước khi ghi

Entity bất biến giúp phân biệt dữ liệu đang có và dữ liệu mới cần lưu. Thay vì thay đổi object hiện tại, ứng dụng tạo một instance mới với giá trị cần cập nhật.

Ví dụ Java record:

```java
@Table("customer")
public record Customer(
        @Id Long id,
        String name
) {
    public Customer withName(String newName) {
        return new Customer(id, newName);
    }
}
```

Service:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .map(customer -> customer.withName(newName))
            .flatMap(customerRepository::save);
}
```

`withName` tạo một object mới. `save` nhận object đó và thực hiện ghi. Khi database sinh ID hoặc Spring Data cập nhật version, hãy dùng instance được phát ra từ `save` vì nó biểu diễn kết quả persistence.

Entity bất biến không tự làm dữ liệu được lưu. Nó chỉ làm rõ cách tạo trạng thái mới trong bộ nhớ; thao tác persistence tường minh vẫn cần thiết.

## 6. Ghi một phần thay đổi hay lưu toàn bộ entity?

`repository.save(entity)` là thao tác lưu entity theo metadata mapping. Khi mục tiêu chỉ là thay đổi một vài cột, không nên mặc định rằng `save` tương đương một câu lệnh patch chỉ ghi các field vừa đổi. Tùy API và mapping, thao tác lưu entity có thể tạo update cho các property persistent của entity.

Nếu cần cập nhật rõ ràng một số cột, có thể dùng `R2dbcEntityTemplate` hoặc `DatabaseClient` để mô tả update cụ thể.

### Cập nhật một cột bằng `R2dbcEntityTemplate`

```java
public Mono<Long> renameCustomer(Long id, String newName) {
    return entityTemplate.update(Customer.class)
            .matching(query(where("id").is(id)))
            .apply(update("name", newName));
}
```

Đoạn code minh họa API fluent của `R2dbcEntityTemplate`: xác định entity/table, điều kiện khớp và property cần cập nhật. Cần import các helper `query`, `where` và `update` tương ứng của Spring Data Relational trong phiên bản dự án.

### Cập nhật một cột bằng `DatabaseClient`

```java
public Mono<Long> renameCustomer(Long id, String newName) {
    return databaseClient.sql(
                "UPDATE customer SET name = :name WHERE id = :id"
            )
            .bind("name", newName)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

Ở cách này, SQL nói rõ chỉ cột `name` được cập nhật. Publisher `rowsUpdated()` phát số hàng bị tác động khi thao tác được subscribe.

Chọn API theo ý định:

| Nhu cầu | API thường phù hợp |
| --- | --- |
| Lưu entity mới hoặc lưu trạng thái entity theo mapping | `repository.save(entity)` |
| Cập nhật rõ một vài property theo điều kiện | `R2dbcEntityTemplate.update(...)` |
| SQL đặc thù, biểu thức database hoặc update phức tạp | `DatabaseClient` |
| Tạo hàng mới với ý định insert rõ ràng | `R2dbcEntityTemplate.insert(...)` hoặc SQL `INSERT` |

Với update tùy chỉnh bằng template hoặc SQL, hãy nhớ rằng object Java đang giữ trong bộ nhớ không tự được cập nhật theo kết quả SQL. Nếu cần object mới phản ánh database, hãy đọc lại hàng hoặc tự tạo giá trị kết quả có kiểm soát.

## 7. Transaction không đồng nghĩa với theo dõi thay đổi object

Reactive transaction quản lý các thao tác database trong cùng transaction context. Nó giúp nhiều lệnh ghi có thể commit hoặc rollback như một đơn vị. Nó không theo dõi field của entity và không tự tạo SQL update.

Ví dụ:

```java
@Transactional
public Mono<Customer> renameAndRecord(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Customer không tồn tại")
            ))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            })
            .flatMap(saved -> auditRepository.save(
                    new AuditRecord(saved.getId(), "CUSTOMER_RENAMED")
            ).thenReturn(saved));
}
```

Khi publisher được subscribe, thao tác tìm customer, lưu customer và lưu audit record được thực hiện trong reactive transaction do Spring quản lý, nếu transaction manager và cấu hình phù hợp. Nếu một thao tác phát lỗi, transaction có thể rollback các thay đổi database trong transaction đó.

Nếu bỏ lời gọi `customerRepository.save(customer)` và chỉ thay đổi `customer.setName(...)`, transaction không có lệnh update customer để commit. Transaction không tự phát hiện setter đã được gọi.

### Thay đổi trong bộ nhớ không được rollback tự động

Giả sử service thay đổi object Java, lưu một hàng, rồi một thao tác tiếp theo làm transaction thất bại. Database rollback các câu lệnh trong transaction, nhưng Java object đang nằm trong bộ nhớ không tự được khôi phục về snapshot trước transaction.

Ví dụ, sau khi rollback, biến `customer` có thể vẫn giữ tên mới dù database đã trở lại tên cũ. Điều này không phải lỗi của transaction; transaction quản lý trạng thái database, không quản lý snapshot object Java.

Nếu cần trạng thái chắc chắn sau rollback, hãy đọc lại entity từ database trong một transaction/luồng phù hợp hoặc tạo lại object từ dữ liệu nguồn. Đừng giả định object đã truyền qua `save` sẽ tự quay lại trạng thái trước khi lưu.

### Transaction chỉ có tác dụng khi publisher nằm trong pipeline được quản lý

Tránh gọi `subscribe()` thủ công ở giữa phương thức `@Transactional`. Subscription mới có thể tách thao tác khỏi transaction context của pipeline do Spring quản lý. Hãy nối tất cả thao tác database bằng `flatMap`, `then`, `zip` hoặc các toán tử reactive thích hợp rồi trả publisher cuối cùng.

## 8. Trạng thái entity sau khi lưu

Sau thao tác lưu, có thể có khác biệt giữa object đầu vào và object được phát ra:

- Với entity dùng khóa do database sinh, kết quả lưu có thể chứa ID mới.
- Với entity có `@Version`, kết quả có thể chứa version mới do Spring Data quản lý.
- Với entity bất biến, framework tạo instance mới chứa các giá trị sau khi lưu.
- Với custom conversion hoặc entity callback, dữ liệu được chuyển đổi hoặc điều chỉnh trong quá trình persistence theo cấu hình.

Do đó, hãy coi object được phát ra từ `save` là kết quả cần dùng:

```java
return customerRepository.save(customer)
        .flatMap(saved -> notificationService.prepare(saved.getId(), saved.getName())
                .thenReturn(saved));
```

Không nên dùng object đầu vào như bằng chứng rằng database đã ghi thành công. Việc tạo object, gọi setter hoặc tạo publisher không chứng minh câu SQL đã chạy hay transaction đã commit.

Nếu cần xác minh dữ liệu sau ghi, có thể đọc lại bằng repository trong cùng transaction hoặc sau khi commit, tùy mục tiêu kiểm thử. Đọc lại đặc biệt hữu ích khi database có trigger, default value hoặc generated column có thể thay đổi giá trị so với object gửi vào.

## 9. Cập nhật đồng thời và entity stale

Vì entity được đọc ra không còn được quản lý tự động, nhiều request có thể cùng đọc một hàng và giữ các object riêng trong bộ nhớ.

Giả sử hai request cùng đọc customer có tên `Lan`:

1. Request A đổi tên thành `Lan A`.
2. Request B đổi tên thành `Lan B`.
3. A lưu thành công.
4. B lưu sau đó với object cũ của mình.

Nếu không có cơ chế kiểm soát đồng thời, update sau có thể ghi đè thay đổi trước. Đây là tình huống lost update.

### Dùng `@Version` để phát hiện cập nhật cũ

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
}
```

Spring Data sử dụng version trong điều kiện update. Nếu một request lưu phiên bản mới trước, request còn lại đang giữ version cũ sẽ không cập nhật được hàng theo điều kiện version và có thể nhận `OptimisticLockingFailureException`.

`@Version` không phải dirty checking. Ứng dụng vẫn phải gọi `save` hoặc thực hiện lệnh update tường minh. Version chỉ giúp phát hiện một cập nhật dựa trên trạng thái đã cũ.

Khi gặp optimistic locking failure, cần xử lý theo nghiệp vụ: thông báo xung đột, đọc lại dữ liệu và yêu cầu người dùng thử lại, hoặc tính lại thay đổi trên phiên bản mới. Không nên retry mù quáng một update nếu phép cập nhật không còn đúng với trạng thái mới nhất.

## 10. Entity callback không thay thế thao tác lưu

Spring Data Relational có các lifecycle callback cho những thời điểm trong quá trình persistence, ví dụ trước khi convert entity hoặc sau khi đọc entity. Callback có thể bổ sung metadata, chuẩn hóa giá trị hoặc áp dụng logic phụ trợ trong phạm vi thao tác Spring Data đang thực hiện.

Callback không có nghĩa Spring Data theo dõi mọi entity trong bộ nhớ. Nếu ứng dụng đọc entity rồi gọi setter nhưng không gọi repository/template/SQL để lưu, callback ghi cũng không tự chạy chỉ vì object đã thay đổi.

Hãy phân biệt:

- Callback được kích hoạt như một phần của thao tác persistence mà Spring Data thực sự thực hiện.
- Thay đổi object thuần Java không phải một thao tác persistence và không tự kích hoạt quá trình ghi.

Nếu dùng auditing để cập nhật `createdDate`, `lastModifiedDate` hoặc người sửa, cần bảo đảm thao tác lưu thực sự được thực hiện và auditing được cấu hình đúng. Chỉ thay đổi object trong bộ nhớ sẽ không làm database tự cập nhật cột auditing.

## 11. Những mẫu code dễ gây hiểu nhầm

### Sửa entity trong `map` rồi kết thúc pipeline

```java
return customerRepository.findById(id)
        .map(customer -> {
            customer.setName("New name");
            return customer;
        })
        .then();
```

`map` chỉ chuyển đổi phần tử được phát ra. Không có lệnh ghi database.

### Gọi `save` nhưng không nối publisher

```java
return customerRepository.findById(id)
        .doOnNext(customer -> {
            customer.setName("New name");
            customerRepository.save(customer); // Publisher bị bỏ đi
        })
        .then();
```

Publisher do `save` trả về không được tiêu thụ. Thao tác lưu không được khởi động. Hãy dùng `flatMap` để nối publisher:

```java
return customerRepository.findById(id)
        .flatMap(customer -> {
            customer.setName("New name");
            return customerRepository.save(customer);
        })
        .then();
```

### Tự subscribe rồi trả về thành công giả định

```java
customerRepository.save(customer).subscribe();
return Mono.just(customer);
```

Publisher trả về không đại diện cho kết quả lưu. Caller có thể nhận object trước khi thao tác database hoàn tất, và lỗi ghi không được truyền qua publisher trả về. Hãy trả thẳng publisher `save` hoặc nối thêm các bước sau nó.

### Nghĩ rằng transaction commit sẽ tự flush object

```java
@Transactional
public Mono<Void> rename(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("New name"))
            .then();
}
```

Transaction chỉ thấy thao tác đọc. Không có dirty checking để tạo update khi commit. Cần gọi `save` hoặc API ghi khác.

## 12. Kiểm thử phân biệt thay đổi trong bộ nhớ và thay đổi trong database

Một integration test có thể chứng minh setter không tự ghi dữ liệu:

```java
StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer -> customer.setName("Changed in memory"))
        .verifyComplete();

StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer ->
                assertThat(customer.getName()).isEqualTo("Lan")
        )
        .verifyComplete();
```

Kiểm thử đầu đọc entity và sửa object trong bộ nhớ. Kiểm thử thứ hai đọc lại từ database và xác nhận giá trị chưa đổi.

Kiểm thử ghi tường minh:

```java
Mono<Customer> rename = customerRepository.findById(10L)
        .flatMap(customer -> {
            customer.setName("Lan Nguyen");
            return customerRepository.save(customer);
        });

StepVerifier.create(rename)
        .assertNext(saved ->
                assertThat(saved.getName()).isEqualTo("Lan Nguyen")
        )
        .verifyComplete();

StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer ->
                assertThat(customer.getName()).isEqualTo("Lan Nguyen")
        )
        .verifyComplete();
```

Các kiểm thử khác nên bao gồm:

- Publisher `save` không được subscribe thì không có thao tác ghi.
- Ghi thành công rồi đọc lại để xác nhận dữ liệu đã commit.
- Rollback transaction và xác nhận database giữ dữ liệu cũ, đồng thời object Java không được giả định tự phục hồi.
- Dùng `@Version` để kiểm tra một entity stale không thể âm thầm ghi đè phiên bản mới hơn.
- Dùng entity bất biến để xác nhận kết quả `save` có ID/version mới được sử dụng ở bước tiếp theo.
- Dùng `DatabaseClient` hoặc `R2dbcEntityTemplate` để xác nhận update một phần chỉ tác động cột được chỉ định.

Các test repository cần subscribe publisher, ví dụ bằng `StepVerifier`. Tạo `Mono` hoặc `Flux` trong test mà không verify/subscribe không chứng minh SQL đã được thực thi.

## 13. Quy trình xử lý thay đổi entity trong service

Một service cập nhật entity thường có thể được tổ chức theo trình tự:

1. Đọc entity bằng repository hoặc template.
2. Xác thực dữ liệu đầu vào và các điều kiện nghiệp vụ.
3. Tạo trạng thái mới trong bộ nhớ bằng setter hoặc tạo instance immutable mới.
4. Gọi `save`, `R2dbcEntityTemplate.update` hoặc `DatabaseClient` để mô tả thao tác ghi.
5. Nối publisher ghi vào pipeline để thao tác thực sự được subscribe.
6. Dùng kết quả được phát ra từ thao tác lưu cho bước tiếp theo.
7. Nếu nhiều thao tác database cần cùng commit/rollback, đặt chúng trong reactive transaction và trả toàn bộ pipeline cho framework quản lý.
8. Xử lý lỗi ghi, lỗi optimistic locking và rollback theo quy tắc nghiệp vụ.

Ví dụ tổng hợp:

```java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final AuditRepository auditRepository;

    public CustomerService(
            CustomerRepository customerRepository,
            AuditRepository auditRepository
    ) {
        this.customerRepository = customerRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Customer> rename(Long id, String newName) {
        return customerRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("Customer không tồn tại")
                ))
                .flatMap(customer -> {
                    customer.setName(newName);
                    return customerRepository.save(customer);
                })
                .flatMap(saved -> auditRepository.save(
                        new AuditRecord(saved.getId(), "RENAMED")
                ).thenReturn(saved));
    }
}
```

Ví dụ này cho thấy setter thay đổi object trong bộ nhớ, `save` tạo thao tác ghi customer, và thao tác lưu audit được nối sau khi customer đã được lưu. Khi publisher được tiêu thụ trong reactive transaction, các câu lệnh database được phối hợp trong cùng transaction. Entity không tự được flush; mỗi lần ghi đều được thể hiện rõ trong pipeline.

## 14. Ghi nhớ

- Entity được đọc từ R2DBC là object Java chứa dữ liệu tại thời điểm đọc; nó không được giữ trong persistence context để dirty checking.
- Gọi setter, sửa field hoặc tạo object mới chỉ thay đổi bộ nhớ ứng dụng, không tự tạo SQL.
- `@Transactional` quản lý commit/rollback các thao tác database trong pipeline; nó không tự phát hiện thay đổi object và không tự flush entity.
- Muốn ghi, phải gọi `repository.save`, `R2dbcEntityTemplate.insert/update` hoặc `DatabaseClient` và nối publisher tương ứng vào pipeline.
- Publisher ghi reactive thường chỉ bắt đầu I/O khi được subscribe; không bỏ publisher và không tự subscribe tách khỏi pipeline service.
- Dùng object được phát ra từ `save` để nhận ID, version và trạng thái sau persistence, nhất là với entity bất biến.
- Nếu chỉ cần thay đổi một vài cột, dùng update tường minh để mô tả chính xác các cột được ghi.
- Rollback database không khôi phục object Java trong bộ nhớ; cần đọc lại hoặc tạo lại trạng thái sau rollback nếu cần đồng bộ.
- `@Version` giúp phát hiện cập nhật đồng thời nhưng không thay thế thao tác save/update và không phải dirty checking.
- Kiểm thử bằng cách subscribe publisher và đọc lại từ database để phân biệt thay đổi bộ nhớ với dữ liệu đã được commit.

Khi đọc một service R2DBC, hãy lần theo hai việc riêng biệt: nơi object Java được thay đổi và nơi lệnh ghi database được tạo rồi tiêu thụ. Nếu không có thao tác persistence được nối vào pipeline, trạng thái mới chỉ tồn tại trong bộ nhớ, kể cả khi phương thức đang chạy trong một reactive transaction.
