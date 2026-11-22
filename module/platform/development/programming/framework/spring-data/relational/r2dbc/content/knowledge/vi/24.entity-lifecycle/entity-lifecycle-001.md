# Các giai đoạn chuyển đổi, lưu và đọc thực thể

Trong Spring Data Relational R2DBC, một entity đi qua nhiều giai đoạn từ lúc được tạo trong ứng dụng, chuyển thành dữ liệu ghi, được lưu vào database, rồi được đọc và ánh xạ trở lại thành object Java. Hiểu thứ tự các giai đoạn này giúp xác định đúng nơi đặt logic khởi tạo dữ liệu, auditing, chuyển đổi kiểu, callback và xử lý ID hoặc version.

Vòng đời entity trong Spring Data Relational có một điểm khác với JPA/Hibernate: Spring Data R2DBC không duy trì persistence context để theo dõi mọi object đã đọc, không tự dirty-check và không tự ghi các thay đổi trong bộ nhớ. Khi muốn lưu thay đổi, ứng dụng phải gọi repository hoặc template một cách tường minh.

Có thể chia vòng đời thành hai luồng chính:

- **Luồng ghi:** tạo hoặc nhận entity → xác định entity mới hay đã tồn tại → chạy callback trước khi chuyển đổi/lưu → chuyển entity thành dữ liệu cột → thực thi INSERT hoặc UPDATE → nhận ID/version và entity kết quả.
- **Luồng đọc:** thực thi SELECT → nhận các row từ driver → chuyển cột thành thuộc tính Java → chạy callback sau khi chuyển đổi → phát entity cho reactive pipeline.

## 1. Tổng quan vòng đời entity

Ví dụ một entity Customer:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private String email;
    private Instant createdAt;
    private Instant updatedAt;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public void rename(String newName) {
        this.name = newName;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity này có:

- ID để xác định bản ghi.
- Version để hỗ trợ optimistic locking và có thể tham gia xác định trạng thái mới.
- Các thuộc tính nghiệp vụ.
- Các thuộc tính thời gian có thể được quản lý bằng auditing hoặc logic ứng dụng.

Luồng khái quát:

~~~text
             TẠO ENTITY
                  |
                  v
        Entity tồn tại trong bộ nhớ
                  |
                  v
          Gọi repository.save()
                  |
                  v
         Xác định new / existing
             /           \
            /             \
           v               v
       INSERT             UPDATE
           \               /
            \             /
             v           v
       Chuyển entity thành cột
                  |
                  v
           Thực thi SQL
                  |
                  v
       Nhận entity đã lưu và ID/version

                  READ
                   |
                   v
              SELECT SQL
                   |
                   v
              Database Row
                   |
                   v
          Chuyển row thành entity
                   |
                   v
           Entity được phát ra
~~~

Đây là mô hình khái niệm. Thứ tự callback cụ thể và việc framework tạo instance mới hay cập nhật instance phụ thuộc mapping metadata, loại entity và thao tác đang thực hiện.

## 2. Giai đoạn 1: tạo entity trong ứng dụng

Entity thường được tạo bởi service, factory hoặc application layer:

~~~java
Customer customer =
    new Customer("An", "an@example.com");
~~~

Ở thời điểm này, object chỉ tồn tại trong bộ nhớ. Chưa có câu SQL nào được thực thi và database chưa biết đến object đó.

Nếu ID được database sinh, ID có thể chưa có giá trị. Nếu ứng dụng tự cấp ID như UUID, entity có thể đã có ID ngay từ lúc tạo. Vì vậy, chỉ nhìn ID không phải lúc nào cũng đủ để nhận diện entity mới.

Một số quy tắc thực hành:

- Tạo entity ở trạng thái hợp lệ theo quy tắc domain.
- Không tự gán version tùy tiện nếu Spring Data đang quản lý version.
- Phân biệt giá trị chưa được cung cấp với giá trị cần lưu SQL NULL.
- Không xem việc tạo object là một thao tác persistence.
- Chỉ gọi save khi muốn bắt đầu quá trình lưu.

### Entity mới không đồng nghĩa với ID luôn null

Nếu ứng dụng cấp UUID trước khi insert, entity mới có thể đã có ID. Spring Data cần chiến lược xác định new state phù hợp, chẳng hạn thuộc tính version hoặc interface Persistable.

Với cơ chế mặc định, Spring Data ưu tiên:

1. Persistable.isNew() nếu entity triển khai Persistable.
2. Thuộc tính @Version nếu entity có version property.
3. ID nếu không có version property.

Ví dụ một entity dùng version dạng wrapper:

~~~java
@Id
private UUID id;

@Version
private Long version;
~~~

Với version wrapper, null biểu thị trạng thái mới theo chiến lược version-based detection. Một version có giá trị biểu thị entity đã tồn tại. Vì thế entity có UUID được gán trước nhưng version còn null vẫn có thể được nhận diện là new.

Nếu dùng Persistable, phương thức isNew() do entity cung cấp quyết định trạng thái mới. Cần quản lý trạng thái này đúng thời điểm và không đánh dấu entity là existing trước khi insert thành công.

## 3. Giai đoạn 2: gọi save() và xác định trạng thái

Repository cung cấp save() cho cả entity mới và entity đã tồn tại:

~~~java
Mono<Customer> saved =
    customerRepository.save(customer);
~~~

save() không có nghĩa là luôn chạy UPDATE và cũng không phải database upsert. Spring Data xác định trạng thái new/existing trước rồi chọn INSERT hoặc UPDATE.

| Trạng thái được nhận diện | Thao tác |
|---|---|
| New | INSERT |
| Existing | UPDATE |

Spring Data không mặc định chạy SELECT để kiểm tra ID có tồn tại trước mỗi lần save. Nếu entity bị nhận diện là existing nhưng dòng đã bị xóa, UPDATE không tự chuyển thành INSERT. Nếu entity bị nhận diện là new nhưng ID đã tồn tại, INSERT có thể lỗi khóa chính hoặc unique constraint.

### Vai trò của ID

ID xác định bản ghi. Khi không có version property và không triển khai Persistable, Spring Data thường dùng trạng thái ID để nhận diện entity mới:

- ID wrapper null thường biểu thị new.
- ID primitive ở giá trị mặc định thường biểu thị new.
- ID đã có giá trị thường biểu thị existing.

Chi tiết phụ thuộc kiểu ID và chiến lược nhận diện mà entity sử dụng.

### Vai trò của @Version

Version vừa hỗ trợ optimistic locking vừa có thể được dùng để nhận diện entity mới:

- Version chưa được thiết lập biểu thị new theo quy tắc version-based detection.
- Version có giá trị biểu thị existing.
- Khi update thành công, version được tăng theo cơ chế Spring Data.
- Khi version trong object không còn khớp database, thao tác có thể thất bại do optimistic locking.

Không dùng version như dữ liệu nghiệp vụ hoặc tự thay đổi nó để ép Spring Data chọn INSERT/UPDATE.

## 4. Giai đoạn 3: callback trước khi chuyển đổi entity

Trước khi chuyển entity thành dữ liệu cột để ghi, Spring Data Relational cung cấp entity callback. Callback cho phép ứng dụng thực hiện một số xử lý có liên quan đến lifecycle, ví dụ:

- Bổ sung giá trị mặc định.
- Chuẩn hóa dữ liệu.
- Gán mã tham chiếu hoặc metadata cần lưu.
- Thực hiện logic auditing thông qua cơ chế auditing được cấu hình.

Một callback thường dùng là BeforeConvertCallback:

~~~java
@Component
public class CustomerBeforeConvert
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        customer.normalizeName();
        return Mono.just(customer);
    }
}
~~~

Callback được gọi trước bước chuyển entity thành dạng dữ liệu ghi. Nó nhận entity và thông tin bảng, rồi trả về Publisher chứa entity sau xử lý.

Ví dụ chỉ minh họa cấu trúc callback; phương thức normalizeName() cần được định nghĩa trong Customer. Với callback reactive, hãy trả Publisher và không tự subscribe hoặc block.

### BeforeSaveCallback

BeforeSaveCallback chạy ở giai đoạn trước khi lưu dữ liệu, khi Spring Data đã chuẩn bị OutboundRow:

~~~java
@Component
public class CustomerBeforeSave
        implements BeforeSaveCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeSave(
            Customer customer,
            OutboundRow row,
            SqlIdentifier table) {

        return Mono.just(customer);
    }
}
~~~

Callback này có thể quan sát hoặc điều chỉnh OutboundRow theo nhu cầu mapping. Nếu sửa row, phải hiểu rõ cột và kiểu dữ liệu mà database/driver mong đợi. Không nên dùng callback để thay thế quy tắc nghiệp vụ phức tạp vốn thuộc service hoặc domain model.

### Callback không phải nơi tự gọi save() lặp lại

Nếu callback gọi lại repository.save() cho chính entity đang được xử lý, có thể tạo vòng lặp callback hoặc phát sinh thao tác ghi lồng khó kiểm soát. Callback nên thực hiện xử lý lifecycle có phạm vi rõ ràng; các nghiệp vụ nhiều bước nên được điều phối ở service.

## 5. Giai đoạn 4: chuyển entity thành dữ liệu ghi

Spring Data Relational dùng mapping metadata để chuyển thuộc tính entity thành các cột trong OutboundRow.

Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String name;

    @Column("email_address")
    private String email;

    @Transient
    private String displayLabel;
}
~~~

Mapping metadata cho biết:

- Entity tương ứng với bảng customer.
- Thuộc tính name tương ứng với cột full_name.
- Thuộc tính email tương ứng với email_address.
- displayLabel không được lưu như một cột của entity.
- id được đánh dấu là định danh.

Trong giai đoạn chuyển đổi, Spring Data sử dụng mapping metadata và conversion service để tạo giá trị phù hợp với R2DBC driver. Các kiểu Java đặc biệt có thể cần custom converter.

### Converter

Khi kiểu Java trong entity không ánh xạ trực tiếp sang kiểu database, có thể đăng ký converter phù hợp.

Ví dụ một enum:

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    CLOSED
}
~~~

Nếu database lưu status dưới dạng VARCHAR, converter có thể chuyển enum thành String khi ghi và chuyển String thành enum khi đọc. Cách cấu hình converter cụ thể phụ thuộc Spring Data Relational version và mapping setup của ứng dụng.

Không nên dùng callback để làm mọi phép chuyển đổi kiểu. Converter là cơ chế phù hợp hơn cho chuyển đổi dữ liệu nhất quán giữa kiểu Java và kiểu lưu trữ.

## 6. Giai đoạn 5: thực thi INSERT hoặc UPDATE

Sau khi xác định trạng thái và chuẩn bị dữ liệu ghi, Spring Data thực thi câu SQL tương ứng.

### INSERT

Với entity mới:

~~~sql
INSERT INTO customer (name, email, created_at)
VALUES (:name, :email, :createdAt);
~~~

Nếu ID do database sinh, framework/driver có thể nhận giá trị được sinh và gán vào entity kết quả theo chiến lược ID cùng khả năng hỗ trợ của database.

Nếu ứng dụng tự cấp ID, ID được đưa vào câu INSERT theo mapping và cấu hình tương ứng.

### UPDATE

Với entity đã tồn tại:

~~~sql
UPDATE customer
SET full_name = :name,
    email_address = :email
WHERE id = :id;
~~~

Nếu có @Version, update được bảo vệ bằng điều kiện version về mặt ngữ nghĩa:

~~~sql
UPDATE customer
SET full_name = :name,
    version = :nextVersion
WHERE id = :id
  AND version = :previousVersion;
~~~

SQL thực tế do Spring Data và dialect tạo ra có thể khác cách trình bày minh họa trên. Điểm quan trọng là version cũ được dùng để phát hiện thay đổi cạnh tranh và version mới được thiết lập khi cập nhật thành công.

### save() không phải upsert

Nếu entity được nhận diện là new, Spring Data chọn INSERT. Nếu entity được nhận diện là existing, Spring Data chọn UPDATE. Việc dòng có tồn tại thật hay không không làm Spring tự động đổi nhánh.

Nếu nghiệp vụ cần upsert theo unique key, cần dùng câu SQL hoặc chiến lược database-specific được thiết kế cho upsert. Không dựa vào tên save() để suy luận hành vi này.

## 7. Giai đoạn 6: callback sau khi lưu

Sau khi thao tác ghi thành công, Spring Data cung cấp AfterSaveCallback:

~~~java
@Component
public class CustomerAfterSave
        implements AfterSaveCallback<Customer> {

    @Override
    public Publisher<Customer> onAfterSave(
            Customer customer,
            OutboundRow row,
            SqlIdentifier table) {

        return Mono.just(customer);
    }
}
~~~

Callback này phù hợp cho xử lý lifecycle sau khi lưu, chẳng hạn bổ sung thông tin cho object trả về hoặc ghi nhận metric nhẹ. Không nên giả định một side effect bên ngoài database có thể rollback cùng transaction chỉ vì nó được thực hiện trong callback.

Nếu callback gửi email hoặc gọi HTTP, database transaction không thể tự hoàn tác side effect đó. Với sự kiện cần phát đáng tin cậy sau commit, cân nhắc outbox pattern hoặc cơ chế phát sự kiện sau transaction.

### Dùng entity trả về từ save()

Luôn tiếp tục pipeline bằng entity được trả về:

~~~java
return customerRepository.save(customer)
    .flatMap(saved -> {
        // saved là entity sau persistence,
        // có thể chứa ID hoặc version mới.
        return auditRepository.save(toAudit(saved))
            .thenReturn(saved);
    });
~~~

Điều này quan trọng với entity bất biến hoặc khi framework tạo instance mới để gán ID/version. Không giả định object ban đầu luôn được cập nhật tại chỗ.

## 8. ID được sinh và entity bất biến

Với database-generated ID, giá trị ID chỉ có sau khi INSERT thành công và driver/framework có thể lấy được generated value.

Ví dụ:

~~~java
Customer customer =
    new Customer("An", "an@example.com");

return customerRepository.save(customer)
    .map(saved -> {
        Long generatedId = saved.getId();
        return new CustomerCreatedResponse(
            generatedId,
            saved.getName()
        );
    });
~~~

Không đọc ID từ object đầu vào rồi giả định nó đã có sau insert. Dùng object trả về từ save().

### Entity mutable

Với entity mutable, Spring Data có thể cập nhật thuộc tính ID/version qua cơ chế property access phù hợp. Tuy nhiên, caller vẫn nên dùng kết quả trả về để tránh phụ thuộc vào việc instance có bị thay thế hay không.

### Entity immutable

Với entity immutable, framework có thể tạo instance mới khi cần gán ID hoặc version. Ví dụ entity dùng constructor hoặc record:

~~~java
public record Customer(
    @Id Long id,
    @Version Long version,
    String name,
    String email
) {
}
~~~

Khi insert hoặc update, entity trả về có thể là một instance khác với object ban đầu. Tiếp tục dùng giá trị phát ra từ save() để bảo đảm pipeline có ID/version mới nhất.

## 9. Auditing trong vòng đời ghi

Spring Data Relational hỗ trợ auditing để quản lý các trường như:

- createdDate: thời điểm tạo.
- lastModifiedDate: thời điểm sửa gần nhất.
- createdBy: người tạo.
- lastModifiedBy: người sửa gần nhất.

Ví dụ entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;
}
~~~

Kích hoạt auditing:

~~~java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
~~~

Nếu cần xác định người dùng hiện tại trong reactive application, có thể cung cấp ReactiveAuditorAware phù hợp:

~~~java
@Component
public class CurrentAuditor implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return currentUserService.currentUsername();
    }
}
~~~

Các annotation auditing chỉ có tác dụng khi auditing được kích hoạt và hạ tầng auditor được cấu hình phù hợp. Tên cột database, kiểu thời gian và principal type phải khớp mapping của ứng dụng.

Auditing là một phần của luồng persistence do Spring Data quản lý. Nếu ghi bằng SQL thuần qua DatabaseClient, không nên giả định auditing callback tự chạy; ứng dụng cần tự gán các trường audit hoặc dùng một cơ chế nhất quán riêng.

## 10. Giai đoạn đọc 1: thực thi SELECT

Khi gọi repository:

~~~java
Mono<Customer> customer =
    customerRepository.findById(42L);
~~~

Spring Data tạo và thực thi SELECT qua R2DBC khi publisher được subscribe.

Với truy vấn trả nhiều dòng:

~~~java
Flux<Customer> customers =
    customerRepository.findByStatus("ACTIVE");
~~~

Mỗi row từ database được đọc và chuyển thành một entity. Flux phát các entity theo dòng kết quả; không nhất thiết toàn bộ dữ liệu phải được tải vào một List trước.

Với truy vấn không tìm thấy:

- findById() thường phát Mono.empty().
- Query trả nhiều dòng có thể phát Flux.empty().
- Lỗi kết nối hoặc lỗi SQL đi theo onError.

Không nhầm trường hợp không có dòng với lỗi truy vấn.

## 11. Giai đoạn đọc 2: chuyển row thành entity

Khi nhận row, Spring Data Relational sử dụng mapping metadata để chuyển các cột thành thuộc tính Java.

Ví dụ:

~~~sql
SELECT id, full_name, email_address, version
FROM customer
WHERE id = :id;
~~~

Các cột được ánh xạ:

| Cột database | Thuộc tính Java |
|---|---|
| id | id |
| full_name | name |
| email_address | email |
| version | version |

Mapping có thể cần:

- Chọn constructor phù hợp để tạo object.
- Chuyển đổi kiểu dữ liệu từ driver sang kiểu Java.
- Áp dụng tên cột từ @Column.
- Xử lý embedded value object hoặc các cấu trúc được mapping hỗ trợ.
- Áp dụng custom converter khi kiểu Java và database khác nhau.

Nếu query chỉ SELECT một phần cột nhưng lại ánh xạ vào entity đầy đủ, những thuộc tính không được trả về có thể mang null hoặc giá trị mặc định. Không nên dùng partial object đó như một entity hoàn chỉnh rồi gọi save(), vì có nguy cơ ghi đè dữ liệu.

Với truy vấn đọc một phần, nên ánh xạ sang DTO/projection riêng.

## 12. Giai đoạn đọc 3: callback sau khi chuyển đổi

Spring Data Relational cung cấp AfterConvertCallback để xử lý entity sau khi một row được chuyển thành object:

~~~java
@Component
public class CustomerAfterConvert
        implements AfterConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onAfterConvert(
            Customer customer,
            Row row,
            RowMetadata metadata) {

        return Mono.just(customer);
    }
}
~~~

Callback này nhận entity đã được mapping cùng Row và RowMetadata. Nó có thể thực hiện xử lý sau khi chuyển đổi, ví dụ chuẩn hóa một thuộc tính tính toán hoặc bổ sung trạng thái không được lưu trực tiếp.

Callback phải trả Publisher phù hợp và không tự subscribe hoặc block. Nếu callback phát lỗi, lỗi đi vào reactive pipeline đọc và caller nhận onError.

Không dùng AfterConvertCallback để phát sinh một truy vấn database cho mỗi entity nếu có thể tránh. Làm như vậy có thể tạo N+1. Nếu cần dữ liệu liên quan, cân nhắc JOIN projection hoặc batch query sau khi lấy danh sách ID.

## 13. Đọc entity không đồng nghĩa với theo dõi thay đổi

Một điểm khác biệt quan trọng so với JPA/Hibernate:

- Spring Data R2DBC không duy trì persistence context theo kiểu identity map.
- Không có dirty checking tự động cho object đã đọc.
- Sửa thuộc tính của entity trong bộ nhớ không tự phát UPDATE.
- Không có lazy-loading proxy tự động tải quan hệ khi getter được gọi.
- Muốn lưu thay đổi, phải gọi save() hoặc một câu lệnh update tường minh.

Ví dụ:

~~~java
return customerRepository.findById(id)
    .map(customer -> {
        customer.rename("An Nguyen");
        return customer;
    });
~~~

Publisher trên chỉ phát một object đã thay đổi trong bộ nhớ. Nó không tự lưu thay đổi vào database.

Muốn lưu:

~~~java
return customerRepository.findById(id)
    .flatMap(customer -> {
        customer.rename("An Nguyen");
        return customerRepository.save(customer);
    });
~~~

save() là thao tác persistence tường minh. Nếu entity có @Version, giữ nguyên version đã đọc để Spring Data kiểm tra optimistic locking.

## 14. Entity callback và domain logic có vai trò khác nhau

Callback là điểm mở rộng quanh các giai đoạn mapping/persistence. Nó phù hợp với logic kỹ thuật gắn với lifecycle:

- Chuẩn hóa dữ liệu trước khi ghi.
- Gán metadata.
- Bổ sung giá trị auditing.
- Chuyển đổi trạng thái kỹ thuật trước hoặc sau mapping.

Domain logic là quy tắc nghiệp vụ quyết định entity được phép làm gì:

- Không cho đóng khách hàng đang có giao dịch chưa hoàn tất.
- Không cho đặt đơn hàng nếu tồn kho không đủ.
- Không cho thay đổi trạng thái sau khi đã chốt.

Những quy tắc này nên nằm trong entity/domain service/application service để có thể gọi và kiểm thử độc lập. Không nên giấu nghiệp vụ quan trọng trong callback mà caller không nhận ra.

Callback cũng không phải nơi thích hợp để điều phối nhiều repository call. Nếu một use case cần đọc, kiểm tra, ghi nhiều aggregate, hãy tổ chức trong service và nối các Publisher rõ ràng.

## 15. Callback reactive và thứ tự thực thi

Các callback của Spring Data Relational có dạng reactive và tham gia pipeline persistence. Một số callback tiêu biểu:

| Callback | Giai đoạn |
|---|---|
| BeforeConvertCallback | Trước khi chuyển entity thành dạng dữ liệu ghi |
| BeforeSaveCallback | Trước khi lưu, khi có OutboundRow |
| AfterSaveCallback | Sau thao tác lưu thành công |
| AfterConvertCallback | Sau khi row được chuyển thành entity |

Spring Data có thể áp dụng callback theo thứ tự được cấu hình thông qua cơ chế ordering của callback. Khi có nhiều callback cùng loại, hãy đặt thứ tự rõ ràng nếu callback sau phụ thuộc kết quả callback trước.

Không nên giả định callback được gọi khi mọi đường truy cập database đều đi qua cùng abstraction:

- Repository và R2dbcEntityTemplate sử dụng mapping infrastructure của Spring Data.
- SQL thuần qua DatabaseClient với mapping thủ công không mặc định chạy toàn bộ entity lifecycle callback như thao tác entity của template.
- SQL trực tiếp không tự động thực hiện auditing hoặc cập nhật version nếu ứng dụng không viết logic tương ứng.

## 16. R2dbcEntityTemplate và DatabaseClient trong vòng đời entity

Hai abstraction này có mức hỗ trợ mapping khác nhau.

### Repository

Repository phù hợp với CRUD và query method:

~~~java
Mono<Customer> findById(Long id);
Mono<Customer> save(Customer customer);
Flux<Customer> findByStatus(String status);
~~~

Repository làm việc với entity metadata và các quy tắc new-state detection, version cùng lifecycle mà Spring Data hỗ trợ.

### R2dbcEntityTemplate

R2dbcEntityTemplate cung cấp API tường minh hơn cho thao tác entity:

~~~java
Mono<Customer> customer =
    r2dbcEntityTemplate.selectOne(
        Query.query(Criteria.where("id").is(42L)),
        Customer.class
    );
~~~

Template sử dụng mapping infrastructure của Spring Data Relational và phù hợp khi cần tạo query động hoặc thao tác entity mà không muốn tự viết toàn bộ SQL.

### DatabaseClient

DatabaseClient phù hợp với SQL tùy chỉnh, JOIN, aggregate query và mapping DTO:

~~~java
Mono<CustomerSummary> summary =
    databaseClient.sql(
        "SELECT id, full_name, status " +
        "FROM customer WHERE id = :id"
    )
    .bind("id", 42L)
    .map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("full_name", String.class),
        row.get("status", String.class)
    ))
    .one();
~~~

Khi dùng DatabaseClient, ứng dụng chịu trách nhiệm rõ hơn về câu SQL, bind parameter, mapping và các thuộc tính cần cập nhật như version hoặc auditing.

## 17. Transaction bao quanh các giai đoạn ghi

Một use case có thể cần lưu Customer rồi ghi Audit. Nếu hai thao tác phải cùng thành công hoặc cùng thất bại, dùng reactive transaction:

~~~java
@Transactional
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .thenReturn(saved)
        );
}
~~~

Các thao tác được nối trong cùng reactive pipeline. Nếu bước lưu audit thất bại với lỗi làm rollback, thay đổi Customer cũng rollback.

Không gọi subscribe() bên trong phương thức transactional. Việc đó có thể tạo subscription ngoài transaction context và khiến phương thức hoàn tất trước khi persistence kết thúc.

Transaction database không rollback được side effect bên ngoài như email hoặc HTTP call. Với sự kiện cần phát sau khi dữ liệu commit, hãy cân nhắc outbox hoặc cơ chế xử lý hậu commit.

## 18. Xử lý lỗi và cancellation trong vòng đời

Các giai đoạn có thể kết thúc bằng:

- Complete: thao tác thành công hoặc không có row.
- Error: lỗi mapping, conversion, SQL, connection hoặc callback.
- Cancel: subscriber hủy việc tiêu thụ publisher.

Ví dụ:

~~~java
return customerRepository.findById(id)
    .map(CustomerSummary::from)
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerReadException(error)
    );
~~~

onErrorMap đổi loại lỗi nhưng vẫn giữ tín hiệu onError. Nếu pipeline nằm trong transaction, transaction manager vẫn có thể nhận biết lỗi.

Nếu dùng onErrorResume để chuyển lỗi thành Mono.empty() bên trong transaction, publisher có thể hoàn tất bình thường và transaction có thể commit. Chỉ recover lỗi khi nghiệp vụ có chủ đích.

Cancellation cũng quan trọng trong reactive transaction. Nếu subscriber hủy luồng ghi trước khi hoàn tất, transaction manager có thể rollback. Không dùng take(), next() hoặc cancel sớm trong một luồng ghi nếu yêu cầu là commit toàn bộ công việc.

## 19. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ tạo entity là đã lưu | Database không có dữ liệu | Gọi save() hoặc template insert |
| Cho rằng save() luôn UPDATE | Chọn sai nhánh persistence | Hiểu new-state detection |
| Cho rằng save() là upsert | Insert/update không như mong đợi | Thiết kế upsert riêng nếu cần |
| Entity có ID gán trước nhưng bị nhận diện existing | Framework chọn UPDATE | Dùng version hoặc Persistable phù hợp |
| Tự gán version tùy tiện | Sai optimistic locking hoặc new-state detection | Để Spring Data quản lý version |
| Không dùng entity trả về từ save() | Bỏ lỡ ID/version mới hoặc instance mới | Tiếp tục pipeline bằng saved entity |
| Map thiếu cột vào entity đầy đủ | Trường thiếu có thể thành null/default | Dùng DTO/projection |
| Mong đợi dirty checking như JPA | Thay đổi trong bộ nhớ không được lưu | Gọi save() tường minh |
| Mong đợi lazy loading | Quan hệ không tự truy vấn khi getter được gọi | JOIN hoặc truy vấn riêng/batch |
| Gọi subscribe() trong callback/service | Tách khỏi lifecycle và transaction | Trả Publisher |
| Dùng callback cho nghiệp vụ phức tạp | Logic khó thấy và khó kiểm thử | Đưa vào domain/service |
| Dùng DatabaseClient rồi mong auditing tự chạy | Trường audit có thể không được gán | Gán tường minh hoặc dùng entity infrastructure |
| Callback phát lỗi nhưng bị recover nhầm | Lỗi persistence bị che giấu | Giữ onError hoặc xử lý có chủ đích |
| Gửi email trong callback sau save | Email không rollback cùng database | Outbox hoặc xử lý hậu commit |

## 20. Quy trình thực hành khi đọc và lưu entity

Khi triển khai một use case, có thể lần lượt xác định:

1. Entity được tạo mới hay được đọc từ database?
2. ID do database sinh hay do ứng dụng cấp?
3. Spring Data sẽ nhận diện new state qua Persistable, version hay ID?
4. Có cần callback trước khi chuyển đổi hoặc trước khi lưu không?
5. Có cần auditing hoặc converter không?
6. Entity được ghi bằng INSERT hay UPDATE?
7. Có version và optimistic locking không?
8. Sau save(), pipeline có dùng entity trả về không?
9. Khi đọc, query có chọn đủ cột cho entity không?
10. Nếu chỉ cần một phần dữ liệu, đã dùng DTO/projection chưa?
11. Có đang kỳ vọng dirty checking hoặc lazy loading không?
12. Các thao tác có cần cùng transaction không?
13. Lỗi và cancellation được xử lý thế nào?
14. Có đường ghi SQL thuần nào cần tự quản lý auditing/version không?

Quy trình này giúp phân biệt rõ trách nhiệm của domain object, mapping infrastructure, callback, repository, transaction manager và database.

## 21. Ghi nhớ

- Entity được tạo trong bộ nhớ chưa có nghĩa là đã được lưu trong database.
- save() xác định entity mới hay đã tồn tại rồi chọn INSERT hoặc UPDATE; nó không mặc định là upsert.
- New-state detection dùng Persistable.isNew(), version property hoặc ID theo thứ tự ưu tiên tương ứng.
- BeforeConvertCallback chạy trước khi chuyển entity thành dữ liệu ghi; BeforeSaveCallback có thể làm việc với OutboundRow.
- Mapping metadata, converter và annotation quyết định cách thuộc tính Java trở thành cột database.
- Sau khi lưu, AfterSaveCallback có thể tham gia xử lý lifecycle; hãy dùng entity được trả về từ save() để nhận ID/version mới.
- @Version hỗ trợ optimistic locking; không tự gán version tùy tiện.
- Auditing cần được kích hoạt và cấu hình auditor phù hợp; SQL thuần không tự động chạy entity auditing callback.
- Khi đọc, row được ánh xạ thành entity và có thể đi qua AfterConvertCallback.
- Partial projection không phải entity đầy đủ; không đưa object thiếu cột vào save().
- Spring Data R2DBC không có persistence context/dirty checking/lazy loading theo cách JPA thường cung cấp.
- Muốn lưu thay đổi sau khi đọc phải gọi save() hoặc câu lệnh update tường minh.
- Callback phù hợp với xử lý kỹ thuật gắn lifecycle; domain rule và use case nhiều bước thuộc domain/service.
- Reactive pipeline cần được compose; không tự subscribe hoặc block trong service/callback.
- Transaction chỉ bảo vệ các thao tác database tham gia cùng transaction manager/ConnectionFactory; side effect bên ngoài cần thiết kế riêng.
