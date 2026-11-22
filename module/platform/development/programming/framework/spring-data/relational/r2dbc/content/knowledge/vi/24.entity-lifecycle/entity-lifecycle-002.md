# EntityCallback đồng bộ và callback phản ứng

## 1. EntityCallback trong vòng đời thực thể

Spring Data R2DBC cung cấp **EntityCallback** như một điểm mở rộng để ứng dụng can thiệp vào entity tại những thời điểm xác định trong quá trình lưu, đọc hoặc xóa dữ liệu. Callback có thể chuẩn hóa entity, bổ sung metadata, kiểm tra điều kiện hoặc biến đổi giá trị trước khi Spring Data ánh xạ và thực thi thao tác persistence.

Có hai kiểu callback cần phân biệt:

- **Callback đồng bộ (synchronous):** nhận entity và trả trực tiếp entity đã xử lý.
- **Callback phản ứng (reactive):** nhận entity và trả về một Publisher chứa entity sau khi xử lý. Callback có thể kết hợp với những thao tác reactive khác mà không chặn thread.

Ví dụ callback đồng bộ:

~~~java
@Component
class CustomerNormalizationCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer entity,
            SqlIdentifier table) {

        return new Customer(
                entity.id(),
                entity.name().trim(),
                entity.email().trim().toLowerCase(Locale.ROOT),
                entity.status()
        );
    }
}
~~~

Callback được gọi trước khi Spring Data chuyển entity thành dữ liệu ghi. Vì Customer là record bất biến, callback tạo và trả về một instance mới đã chuẩn hóa.

Ví dụ callback reactive:

~~~java
@Component
class CustomerPolicyCallback
        implements ReactiveBeforeConvertCallback<Customer> {

    private final CustomerPolicy policy;

    CustomerPolicyCallback(CustomerPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer entity,
            SqlIdentifier table) {

        return policy.normalize(entity);
    }
}
~~~

Ở ví dụ thứ hai, CustomerPolicy trả về Publisher. Spring Data có thể nối publisher này vào pipeline persistence và chỉ tiếp tục khi callback phát ra entity.

EntityCallback không phải một listener tùy ý chạy sau khi database đã hoàn tất. Callback là một phần của quy trình entity mapping/persistence. Vị trí callback quyết định entity đang ở giai đoạn nào và thay đổi được áp dụng vào đâu.

## 2. Vòng đời callback khi ghi entity

Các callback ghi dữ liệu thường được tổ chức quanh những giai đoạn sau:

~~~text
Entity được đưa vào thao tác lưu
              |
              v
       BeforeConvertCallback
              |
              v
       Chuyển entity thành
          OutboundRow
              |
              v
         BeforeSaveCallback
              |
              v
       Thực thi INSERT/UPDATE
              |
              v
          AfterSaveCallback
              |
              v
       Publisher trả entity
~~~

Tên callback mô tả thời điểm trong vòng đời:

| Callback | Thời điểm | Mục đích thường gặp |
|---|---|---|
| BeforeConvertCallback | Trước khi chuyển entity thành dữ liệu ghi | Chuẩn hóa hoặc bổ sung field trên entity |
| BeforeSaveCallback | Sau bước chuẩn bị dữ liệu ghi, trước khi thực thi SQL | Điều chỉnh entity hoặc OutboundRow |
| AfterSaveCallback | Sau khi thao tác lưu hoàn tất | Bổ sung xử lý hậu lưu dựa trên kết quả persistence |

Các callback reactive có tên tương ứng bắt đầu bằng tiền tố **Reactive**, ví dụ **ReactiveBeforeConvertCallback**.

Thứ tự trên là cách nhìn tổng quát về lifecycle của thao tác ghi. Những chi tiết như generated ID, version và dữ liệu do database sinh phụ thuộc mapping, dialect và driver. Không nên giả định object đầu vào luôn được mutate tại chỗ; với entity immutable, hãy sử dụng entity được phát ra từ publisher save.

### 2.1. BeforeConvertCallback

**BeforeConvertCallback<T>** được gọi trước khi entity được chuyển thành representation dùng để ghi xuống database. Callback nhận entity và tên bảng dưới dạng **SqlIdentifier**.

Đây là vị trí phù hợp để:

- Trim hoặc chuẩn hóa chuỗi.
- Tạo slug hoặc giá trị dẫn xuất đơn giản.
- Bổ sung giá trị mặc định thuộc trách nhiệm persistence.
- Tạo metadata cần được ghi cùng entity.
- Trả về một entity mới nếu mô hình bất biến.

Ví dụ:

~~~java
@Component
class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            SqlIdentifier table) {

        String normalizedCode =
                product.code().trim().toUpperCase(Locale.ROOT);

        return new Product(
                product.id(),
                normalizedCode,
                product.name().trim(),
                product.price()
        );
    }
}
~~~

Thay đổi được thực hiện trên entity trước khi Spring Data tạo dữ liệu ghi. Vì vậy, đây thường là vị trí dễ hiểu nhất khi muốn chuẩn hóa giá trị domain trước khi persistence.

Không dùng callback này để thay thế toàn bộ validation của request hoặc quy tắc nghiệp vụ phức tạp. Những quy tắc cần phản hồi rõ cho người dùng thường nên được kiểm tra ở service/domain layer trước khi bắt đầu ghi.

### 2.2. BeforeSaveCallback

**BeforeSaveCallback<T>** được gọi khi Spring Data đã chuẩn bị **OutboundRow** và sắp thực hiện thao tác ghi. Callback nhận:

- Entity đang được lưu.
- OutboundRow chứa các giá trị được ánh xạ sang cột.
- SqlIdentifier đại diện bảng đích.

Ví dụ chữ ký:

~~~java
@Component
class CustomerBeforeSaveCallback
        implements BeforeSaveCallback<Customer> {

    @Override
    public Customer onBeforeSave(
            Customer entity,
            OutboundRow row,
            SqlIdentifier table) {

        // Có thể kiểm tra entity, table và dữ liệu trong row.
        return entity;
    }
}
~~~

Callback này phù hợp khi cần can thiệp ở mức mapping row, ví dụ một giá trị ghi đặc thù hoặc metadata phụ thuộc vào cấu trúc hàng đã được tạo.

OutboundRow là representation dữ liệu ghi của Spring Data Relational. Việc thay đổi row có thể làm dữ liệu được gửi xuống database khác với các property trên entity. Nếu sửa row trực tiếp, cần giữ nhất quán giữa row, entity được trả về và dữ liệu mà caller kỳ vọng. Không nên tùy tiện đổi cột hoặc kiểu dữ liệu mà không hiểu mapping và dialect.

Nếu chỉ cần chuẩn hóa một property của entity, thường nên dùng BeforeConvertCallback để tránh duy trì hai phiên bản dữ liệu khác nhau.

### 2.3. AfterSaveCallback

**AfterSaveCallback<T>** được gọi sau khi thao tác lưu đã được thực hiện. Callback nhận entity, OutboundRow và table identifier.

Ví dụ:

~~~java
@Component
class CustomerAfterSaveCallback
        implements AfterSaveCallback<Customer> {

    @Override
    public Customer onAfterSave(
            Customer entity,
            OutboundRow row,
            SqlIdentifier table) {

        return entity;
    }
}
~~~

Callback này phù hợp với xử lý hậu lưu cần nằm trong lifecycle persistence, chẳng hạn bổ sung một giá trị dẫn xuất cho object trả về hoặc ghi nhận thông tin kỹ thuật phù hợp.

Cần phân biệt callback hậu lưu với việc phát side effect bên ngoài. Gửi email, gọi HTTP hoặc publish message trực tiếp từ AfterSaveCallback có thể tạo trạng thái không nhất quán nếu database rollback hoặc thao tác bên ngoài thất bại. Với yêu cầu phát sự kiện đáng tin cậy, cân nhắc transactional outbox.

Nếu AfterSaveCallback phát lỗi sau khi câu SQL đã chạy, khả năng rollback phụ thuộc transaction đang bao quanh thao tác hay không. Khi cần bảo đảm thay đổi database và bước hậu lưu cùng atomic, hãy đặt toàn bộ publisher trong reactive transaction phù hợp.

## 3. Callback khi đọc entity

Khi đọc dữ liệu, Spring Data lấy các row từ database, ánh xạ chúng thành entity rồi có thể gọi callback sau chuyển đổi:

~~~text
SELECT trả về Row
       |
       v
MappingR2dbcConverter
       |
       v
Entity được tạo
       |
       v
AfterConvertCallback
       |
       v
Entity được phát ra
~~~

**AfterConvertCallback<T>** được gọi sau khi row đã được chuyển thành entity.

Ví dụ:

~~~java
@Component
class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer entity,
            SqlIdentifier table) {

        return new Customer(
                entity.id(),
                entity.name(),
                entity.email(),
                entity.status()
        );
    }
}
~~~

Callback có thể biến đổi entity sau mapping. Tuy nhiên, nên giữ xử lý nhẹ và xác định. Nếu mỗi hàng được đọc lại cần gọi một dịch vụ từ xa, callback có thể tạo một lời gọi mạng cho mỗi row và biến truy vấn danh sách thành chuỗi thao tác chậm.

Đặc biệt với Flux, callback sau convert có thể được thực hiện cho từng entity được phát. Hãy cân nhắc số lượng hàng, concurrency, latency và backpressure khi thêm công việc vào giai đoạn này.

Không nhầm AfterConvertCallback với lazy loading. Spring Data R2DBC không cung cấp persistence context và lazy-loading proxy như JPA. Nếu cần dữ liệu từ bảng khác, hãy viết query phù hợp hoặc kết hợp các publisher một cách có chủ đích.

## 4. Callback khi xóa entity

Spring Data Relational cũng có callback cho lifecycle xóa:

- **BeforeDeleteCallback<T>:** được gọi trước khi xóa entity.
- **AfterDeleteCallback<T>:** được gọi sau khi thao tác xóa hoàn tất.

Ví dụ callback trước khi xóa:

~~~java
@Component
class CustomerBeforeDeleteCallback
        implements BeforeDeleteCallback<Customer> {

    @Override
    public Customer onBeforeDelete(
            Customer entity,
            SqlIdentifier table) {

        return entity;
    }
}
~~~

Callback trước xóa có thể kiểm tra hoặc chuẩn bị thông tin dựa trên entity và bảng. Callback sau xóa phù hợp với xử lý hậu thao tác trong phạm vi lifecycle.

Cần phân biệt việc xóa một entity có đầy đủ dữ liệu với việc chạy SQL DELETE tùy chỉnh qua DatabaseClient. Khi ứng dụng gửi raw SQL bằng DatabaseClient, không có entity lifecycle mapping để Spring Data tự động kích hoạt callback cho câu lệnh đó.

Ngoài ra, không nên giả định mọi lệnh delete theo ID, Criteria hoặc raw SQL đều cung cấp cùng thông tin entity cho callback. Hãy xác định API được dùng và kiểm thử hành vi callback trên phiên bản Spring Data R2DBC của dự án.

## 5. Callback đồng bộ: trả trực tiếp entity

Callback đồng bộ triển khai các interface như:

- **BeforeConvertCallback<T>**.
- **BeforeSaveCallback<T>**.
- **AfterSaveCallback<T>**.
- **AfterConvertCallback<T>**.
- **BeforeDeleteCallback<T>**.
- **AfterDeleteCallback<T>**.

Phương thức callback nhận entity và trả về entity:

~~~java
public interface BeforeConvertCallback<T> {
    T onBeforeConvert(T entity, SqlIdentifier table);
}
~~~

Đây là mô tả chữ ký khái quát. Interface thực tế còn kế thừa callback marker của Spring Data và có thể thay đổi chi tiết package theo module/version.

Ví dụ triển khai callback đồng bộ:

~~~java
@Component
class NormalizeEmailCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        return customer.withEmail(normalized);
    }
}
~~~

Callback đồng bộ phù hợp với các phép biến đổi nhanh, không cần I/O:

- Chuẩn hóa dữ liệu.
- Gán giá trị mặc định.
- Tạo metadata cục bộ.
- Tính giá trị dẫn xuất đơn giản.
- Kiểm tra điều kiện kỹ thuật và phát exception nếu không hợp lệ.

Với entity mutable, callback có thể thay đổi entity rồi trả lại cùng instance. Với record hoặc immutable class, callback nên tạo object mới. Trong cả hai trường hợp, phải trả entity mà pipeline persistence cần tiếp tục sử dụng.

### 5.1. Không thực hiện I/O blocking trong callback đồng bộ

Không nên gọi dịch vụ mạng, đọc file lớn hoặc thực hiện truy vấn database blocking trong callback đồng bộ. Với reactive application, callback có thể được thực thi trên thread đang xử lý pipeline; một thao tác blocking có thể chặn event-loop hoặc làm giảm thông lượng.

Ví dụ không phù hợp:

~~~java
@Override
public Customer onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    // Không nên: chặn thread để gọi dịch vụ bên ngoài.
    RiskResult result = riskClient.check(customer.email()).block();

    return customer.withRiskLevel(result.level());
}
~~~

Nếu công việc cần I/O bất đồng bộ, hãy dùng reactive callback hoặc chuyển bước đó lên service layer trước khi gọi repository.

## 6. Callback phản ứng: trả về Publisher

Reactive callback dùng các interface tương ứng có tiền tố **Reactive**, chẳng hạn:

- **ReactiveBeforeConvertCallback<T>**.
- **ReactiveBeforeSaveCallback<T>**.
- **ReactiveAfterSaveCallback<T>**.
- **ReactiveAfterConvertCallback<T>**.
- **ReactiveBeforeDeleteCallback<T>**.
- **ReactiveAfterDeleteCallback<T>**.

Thay vì trả trực tiếp entity, callback trả về **Publisher<T>**. Trong ứng dụng Reactor, có thể dùng **Mono<T>** vì Mono triển khai Publisher.

Ví dụ chữ ký:

~~~java
public interface ReactiveBeforeConvertCallback<T> {
    Publisher<T> onBeforeConvert(T entity, SqlIdentifier table);
}
~~~

Ví dụ callback reactive:

~~~java
@Component
class ReactiveCustomerCallback
        implements ReactiveBeforeConvertCallback<Customer> {

    private final CustomerPolicy policy;

    ReactiveCustomerCallback(CustomerPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return policy.normalize(customer)
                .map(normalized -> normalized.withStatus(
                        normalized.status().toUpperCase(Locale.ROOT)
                ));
    }
}
~~~

CustomerPolicy.normalize() có thể trả về Mono<Customer>. Callback trả publisher đó để Spring Data nối vào quá trình lưu. Không cần tự subscribe hoặc block để chờ kết quả.

### 6.1. Reactive callback có thể ghép thao tác bất đồng bộ

Ví dụ một callback cần lấy metadata từ một nguồn reactive:

~~~java
@Component
class ReactiveBeforeConvertCallbackImpl
        implements ReactiveBeforeConvertCallback<Customer> {

    private final TenantPolicyRepository tenantPolicyRepository;

    ReactiveBeforeConvertCallbackImpl(
            TenantPolicyRepository tenantPolicyRepository) {
        this.tenantPolicyRepository = tenantPolicyRepository;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return tenantPolicyRepository.findPolicy(customer.tenantId())
                .map(policy -> customer.withRegion(policy.region()));
    }
}
~~~

Đây là ví dụ về khả năng composition reactive. Trong thiết kế thực tế, cần cân nhắc việc callback persistence gọi thêm repository khác:

- Nó làm tăng số query cho mỗi lần lưu.
- Có thể tạo N+1 pattern khi lưu nhiều entity.
- Nó kéo dài transaction và giữ connection lâu hơn nếu các thao tác nằm trong cùng transaction.
- Repository phụ phải dùng đúng ConnectionFactory/transaction context nếu cần tham gia cùng transaction.
- Lỗi từ nguồn metadata sẽ làm publisher lưu thất bại.

Nếu việc lấy policy là một phần quy tắc nghiệp vụ quan trọng, thường dễ hiểu hơn khi thực hiện trong service trước khi gọi persistence. Reactive callback nên được dùng khi logic thực sự gắn với lifecycle entity và có thể dùng chung ở nhiều đường lưu.

### 6.2. Không gọi subscribe() hoặc block() trong reactive callback

Không nên:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    policy.normalize(customer).subscribe();
    return Mono.just(customer);
}
~~~

Subscription tự tạo chạy độc lập với publisher mà Spring Data đang chờ. Spring không thể bảo đảm thao tác normalize hoàn tất trước khi entity được lưu, cũng không thể kết hợp lỗi hoặc transaction của publisher đó.

Cách đúng là trả publisher:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    return policy.normalize(customer);
}
~~~

Tương tự, không dùng block() để lấy giá trị đồng bộ từ một publisher bên trong callback reactive.

### 6.3. Publisher callback phải phát entity để pipeline tiếp tục

Reactive callback được kỳ vọng phát entity tiếp tục xử lý. Nếu trả Mono.empty(), pipeline có thể hoàn tất mà không có entity để thực hiện bước persistence tiếp theo.

Nếu callback phát hiện dữ liệu không hợp lệ, nên phát lỗi rõ ràng:

~~~java
return Mono.error(
        new IllegalArgumentException("Customer email is required")
);
~~~

Nếu callback không cần thay đổi entity, trả Mono.just(entity) hoặc publisher tương đương. Tránh trả empty ngoài ý muốn vì caller có thể nhận completion rỗng mà không hiểu vì sao thao tác lưu không tạo kết quả.

## 7. So sánh callback đồng bộ và callback reactive

| Tiêu chí | Callback đồng bộ | Callback reactive |
|---|---|---|
| Interface | BeforeConvertCallback<T> | ReactiveBeforeConvertCallback<T> |
| Kiểu trả về | T | Publisher<T> |
| Ví dụ với Reactor | Trả entity trực tiếp | Trả Mono<T> |
| Xử lý bất đồng bộ | Không phù hợp | Có thể composition với Publisher |
| I/O | Chỉ nên dùng công việc nhanh, không blocking | Có thể dùng API reactive |
| Error | Throw exception | Mono.error/error signal |
| Thứ tự | Callback đồng bộ hoàn tất trong lời gọi | Pipeline chờ publisher callback |
| Ứng dụng phù hợp | Chuẩn hóa và biến đổi cục bộ | Công việc reactive thật sự gắn với lifecycle |

Không nên chọn reactive callback chỉ vì ứng dụng đang dùng R2DBC. Nếu chỉ trim chuỗi hoặc gán default, callback đồng bộ ngắn gọn hơn. Chọn reactive callback khi thật sự cần kết hợp publisher và muốn giữ toàn bộ xử lý non-blocking.

Với ứng dụng có cả đường truy cập imperative và reactive, cần đăng ký callback phù hợp với API được sử dụng. Đừng giả định một callback đồng bộ có thể thay thế một callback reactive khi cần I/O bất đồng bộ; hãy kiểm tra callback registration và invocation của phiên bản Spring Data đang dùng.

## 8. Đăng ký callback trong Spring ApplicationContext

Thông thường, callback được khai báo thành Spring bean. Có thể dùng @Component:

~~~java
@Component
class ProductCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            SqlIdentifier table) {
        return product;
    }
}
~~~

Hoặc khai báo bằng @Bean:

~~~java
@Configuration
class EntityCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Product> productCallback() {
        return (product, table) -> product.withName(
                product.name().trim()
        );
    }
}
~~~

Spring Data phát hiện callback bean theo interface callback và đưa vào cơ chế thực thi lifecycle. Constructor injection nên được dùng khi callback cần dependency.

Không tự tạo callback bằng new ở service rồi mong Spring Data tự gọi. Callback cần được đăng ký trong application context hoặc trong cơ chế callback registry tương ứng.

Nếu dùng nhiều persistence configuration hoặc nhiều application context, cần xác nhận callback được đăng ký trong context mà template/repository sử dụng. Với nhiều database, callback dùng chung có thể được gọi ở nhiều persistence path; kiểm tra table/entity để giới hạn logic nếu cần.

## 9. Thứ tự thực thi callback

Một entity có thể đi qua nhiều callback cùng loại hoặc nhiều callback ở các phase khác nhau. Spring hỗ trợ ordering bằng **Ordered** hoặc annotation **@Order**.

Ví dụ:

~~~java
@Component
@Order(10)
class TrimNameCallback implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return customer.withName(customer.name().trim());
    }
}
~~~

~~~java
@Component
@Order(20)
class NormalizeEmailCallback implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return customer.withEmail(
                customer.email().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

Các callback cùng phase được sắp theo thứ tự được cấu hình; giá trị order nhỏ hơn có độ ưu tiên trước theo quy ước Spring. Callback thứ hai nhận entity do callback trước trả về.

Thứ tự quan trọng khi callback phụ thuộc kết quả của callback khác. Ví dụ cần trim chuỗi trước khi kiểm tra độ dài hoặc tạo hash. Nên giữ số callback ít và trách nhiệm rõ ràng để tránh chuỗi biến đổi khó theo dõi.

Không dựa vào thứ tự đăng ký bean tình cờ. Nếu logic cần thứ tự, khai báo @Order hoặc triển khai Ordered rõ ràng.

## 10. Callback và immutable entity

Spring Data R2DBC thường làm việc tốt với entity immutable như Java record. Callback cần trả về một instance mới thay vì dựa vào mutate object.

Ví dụ:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {
    public Customer withEmail(String newEmail) {
        return new Customer(id, name, newEmail, status);
    }
}
~~~

Callback:

~~~java
@Component
class NormalizeCustomerEmail
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return customer.withEmail(
                customer.email().trim().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

Khi gọi save:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Hãy sử dụng Customer được phát ra từ saved:

~~~java
return customerRepository.save(customer)
        .map(savedCustomer ->
                new CustomerResponse(
                        savedCustomer.id(),
                        savedCustomer.email()
                )
        );
~~~

Không giả định biến customer ban đầu đã thay đổi. Callback có thể trả instance mới và Spring Data tiếp tục dùng instance đó trong pipeline.

## 11. Callback và auditing

Auditing là một ứng dụng điển hình của lifecycle callback. Spring Data hỗ trợ các annotation như:

- @CreatedDate.
- @LastModifiedDate.
- @CreatedBy.
- @LastModifiedBy.

Với R2DBC, auditing cần được bật qua cấu hình Spring Data R2DBC phù hợp, ví dụ **@EnableR2dbcAuditing**, cùng nguồn cung cấp auditor nếu cần thông tin người thực hiện.

Ví dụ entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

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

Spring Data auditing sử dụng callback infrastructure để bổ sung metadata thời gian và người thao tác vào lifecycle entity. Nếu ứng dụng dùng reactive security context để xác định auditor, cần cấu hình nguồn auditor reactive phù hợp với phiên bản đang dùng.

Không nên tự viết nhiều callback để tái tạo auditing nếu tính năng auditing chuẩn đáp ứng yêu cầu. Cấu hình auditing tập trung giúp các entity dùng cùng một chính sách và giảm logic lặp.

## 12. Callback không phải là nơi thay thế service/domain logic

EntityCallback hữu ích khi logic thực sự gắn với lifecycle persistence. Tuy nhiên, không nên biến callback thành nơi chứa toàn bộ quy tắc nghiệp vụ.

Ví dụ, các việc sau thường nên nằm ở service/domain layer:

- Kiểm tra người dùng có quyền sửa entity không.
- Tính giá đơn hàng dựa trên nhiều aggregate.
- Kiểm tra hạn mức tài khoản.
- Gọi dịch vụ thanh toán hoặc dịch vụ bên ngoài.
- Điều phối nhiều repository trong một use case.
- Quyết định có gửi thông báo cho khách hàng hay không.

Các việc phù hợp hơn với callback:

- Chuẩn hóa một property trước khi convert.
- Bổ sung metadata persistence dùng chung.
- Áp dụng auditing.
- Chuyển đổi giá trị kỹ thuật trước/sau mapping.
- Xử lý một quy tắc mapping lặp lại ở nhiều nơi.

Callback thường chạy ngầm mỗi khi persistence path tương ứng được sử dụng. Nếu đặt logic nghiệp vụ quan trọng ở đó, caller có thể không nhìn thấy vì sao save phát sinh thêm query, lỗi hoặc side effect. Giữ callback nhỏ giúp hành vi repository dễ dự đoán.

## 13. Callback không thay thế ApplicationEvent hoặc transactional outbox

EntityCallback và ApplicationEvent có mục đích khác nhau.

| Cơ chế | Mục đích |
|---|---|
| EntityCallback | Can thiệp vào entity trong lifecycle mapping/persistence |
| Spring ApplicationEvent | Thông báo một sự kiện cho thành phần khác trong application |
| Transactional outbox | Lưu ý định phát sự kiện cùng transaction database để publisher gửi sau commit |

Callback có thể trả về entity đã biến đổi, nên phù hợp khi muốn thay đổi dữ liệu tiếp tục đi vào persistence pipeline. ApplicationEvent thường dùng để thông báo hoặc tách thành phần xử lý. Outbox phù hợp khi cần bảo đảm ý định phát message được lưu atomic cùng thay đổi nghiệp vụ.

Không gửi email hoặc publish message trực tiếp từ BeforeSave/AfterSave và giả định side effect sẽ rollback cùng database. Nếu message đã được gửi nhưng transaction rollback, hệ thống ngoài database vẫn đã nhận message. Nếu transaction commit nhưng gửi message thất bại, message có thể bị mất.

Với yêu cầu nhất quán, ghi outbox row trong cùng transaction với entity, sau đó để worker/publisher phát message. Consumer nên có cơ chế deduplication vì message delivery có thể lặp.

## 14. Callback có tham gia reactive transaction không?

Khi callback được thực thi như một phần của thao tác repository hoặc template trong reactive transaction, publisher callback nằm trong pipeline persistence đó. Reactive callback có thể sử dụng các thao tác R2DBC khác nếu chúng tham gia cùng transaction context và ConnectionFactory.

Ví dụ service:

~~~java
@Transactional
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return customerRepository.save(toCustomer(command));
}
~~~

Nếu ReactiveBeforeConvertCallback gọi một repository khác bằng cùng ConnectionFactory, publisher đó có thể tham gia transaction hiện tại. Khi callback phát lỗi và lỗi đi ra ngoài transaction boundary, transaction có thể rollback.

Nhưng cần phân biệt:

- Callback không tự tạo transaction mới.
- Callback không bảo đảm một thao tác ngoài database rollback.
- Callback dùng ConnectionFactory khác không tự tham gia transaction manager hiện tại.
- Nếu lỗi bị bắt và chuyển thành completion bình thường, transaction có thể commit.
- Callback chạy sau khi câu SQL đã thực thi có thể cần transaction bao quanh nếu lỗi hậu lưu phải rollback write.

Không gọi subscribe() trong callback. Hãy trả publisher để Spring Data và transaction manager có thể điều phối toàn bộ pipeline.

## 15. Hiệu năng và số lượng thao tác trong callback

Callback được gọi ở mỗi lifecycle tương ứng. Nếu một callback thực hiện một truy vấn phụ cho mỗi entity, chi phí có thể tăng theo số lượng hàng.

Ví dụ đọc 500 Customer và mỗi AfterConvertCallback gọi một repository khác để lấy policy sẽ tạo nguy cơ 500 truy vấn bổ sung. Đây là một dạng N+1 query pattern.

Cần cân nhắc:

- Callback có chạy cho mỗi hàng của Flux không?
- Có thể lấy dữ liệu cần thiết trong một query JOIN hoặc projection không?
- Có thể tải metadata một lần ở service rồi truyền vào thao tác không?
- Có thể cache dữ liệu tham chiếu theo key với TTL/invalidation rõ ràng không?
- Callback reactive có làm transaction kéo dài hoặc giữ connection lâu hơn không?
- Có callback nào thực hiện blocking hoặc CPU-heavy work không?

Reactive callback tránh chặn thread khi dùng đúng reactive API, nhưng không làm I/O miễn phí. Nó vẫn tiêu thụ connection, thời gian database và tài nguyên downstream.

Với AfterConvertCallback, đặc biệt chú ý việc callback chạy trên từng entity trong Flux. Không thêm network call cho từng row nếu có thể giải quyết bằng query hoặc batch lookup.

## 16. Lỗi trong callback và cách xử lý

Callback đồng bộ có thể throw exception. Reactive callback có thể trả error signal. Lỗi đó truyền vào pipeline persistence và thường làm thao tác hiện tại thất bại.

Ví dụ callback đồng bộ:

~~~java
@Override
public Customer onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    return customer;
}
~~~

Ví dụ callback reactive:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        return Mono.error(
                new IllegalArgumentException("Email is required")
        );
    }

    return Mono.just(customer);
}
~~~

Không nên bắt mọi exception trong callback rồi trả entity ban đầu. Làm như vậy có thể che lỗi mapping, lỗi nguồn dữ liệu hoặc lỗi toàn vẹn.

Nếu validation là quy tắc đầu vào của API, nên thực hiện ở boundary/service để caller nhận lỗi sớm và rõ ràng. Callback có thể giữ một số invariant kỹ thuật cuối cùng trước persistence, nhưng không nên là lớp validation duy nhất.

Với AfterSaveCallback, cần nhớ SQL có thể đã được thực thi. Nếu callback phát lỗi và không có transaction bao quanh, không thể mặc định rằng thao tác ghi đã được rollback. Dùng transaction khi tính atomic giữa write và xử lý hậu lưu là yêu cầu nghiệp vụ.

## 17. Callback có được gọi khi dùng DatabaseClient không?

DatabaseClient là API SQL-oriented. Khi ứng dụng viết raw SQL và map Row thủ công:

~~~java
databaseClient.sql("""
        INSERT INTO customers (name, email, status)
        VALUES (:name, :email, :status)
        """)
    .bind("name", name)
    .bind("email", email)
    .bind("status", status)
    .fetch()
    .rowsUpdated();
~~~

DatabaseClient không tự tạo entity lifecycle operation như R2dbcEntityTemplate. Vì vậy, không nên mong đợi BeforeConvertCallback, BeforeSaveCallback hoặc AfterSaveCallback tự chạy cho raw SQL này.

Nếu muốn dùng callback, hãy đi qua API entity-oriented có callback support, hoặc chủ động gọi service/domain logic trước khi thực thi SQL. Đừng giả định một câu SQL raw sẽ tự kích hoạt callback chỉ vì bảng trùng với @Table của entity.

Tương tự, nếu callback là nơi duy nhất chuẩn hóa email nhưng một phần ứng dụng ghi bằng DatabaseClient, đường ghi raw SQL có thể bỏ qua quy tắc đó. Logic cần áp dụng cho mọi đường ghi nên được đặt ở service/domain hoặc được tái sử dụng rõ ràng trong cả hai đường.

## 18. Chọn callback đúng theo mục đích

| Nhu cầu | Callback hoặc tầng phù hợp |
|---|---|
| Chuẩn hóa property trước khi mapping | BeforeConvertCallback / ReactiveBeforeConvertCallback |
| Can thiệp vào OutboundRow trước SQL | BeforeSaveCallback / ReactiveBeforeSaveCallback |
| Xử lý entity sau khi lưu | AfterSaveCallback / ReactiveAfterSaveCallback |
| Biến đổi entity sau khi đọc | AfterConvertCallback / ReactiveAfterConvertCallback |
| Xử lý trước khi xóa entity | BeforeDeleteCallback / ReactiveBeforeDeleteCallback |
| Xử lý sau khi xóa entity | AfterDeleteCallback / ReactiveAfterDeleteCallback |
| Tính toán domain cần nhiều aggregate | Service/domain layer |
| Kiểm tra authorization | Security/service layer |
| Gửi message đáng tin cậy sau commit | Transactional outbox |
| Gọi dịch vụ ngoài qua reactive I/O | Thường đặt trong service; chỉ dùng reactive callback khi thật sự thuộc lifecycle |
| Chạy SQL tùy chỉnh qua DatabaseClient | Tự gọi logic cần thiết; không trông đợi entity callback tự chạy |

Khi chọn callback, hãy hỏi: logic này có thực sự cần chạy mỗi khi entity đi qua phase đó không? Nếu chỉ một use case cần logic, service thường thể hiện ý định rõ hơn.

## 19. Kiểm thử callback đồng bộ

Có thể kiểm thử callback đồng bộ trực tiếp bằng cách gọi method và xác nhận entity trả về:

~~~java
@Test
void shouldNormalizeEmailBeforeConvert() {
    NormalizeEmailCallback callback = new NormalizeEmailCallback();

    Customer input = new Customer(
            10L,
            "An",
            "  AN@EXAMPLE.TEST ",
            "ACTIVE"
    );

    Customer result = callback.onBeforeConvert(
            input,
            SqlIdentifier.unquoted("customers")
    );

    assertThat(result.email()).isEqualTo("an@example.test");
}
~~~

Unit test này xác nhận logic biến đổi. Nó chưa chứng minh Spring Data thực sự phát hiện và gọi callback trong persistence pipeline.

Có thể bổ sung integration test với repository hoặc template để xác nhận callback được đăng ký trong ApplicationContext và dữ liệu sau lưu có giá trị đã chuẩn hóa.

## 20. Kiểm thử callback reactive

Với callback reactive, dùng StepVerifier để kiểm tra giá trị, empty và error signal:

~~~java
@Test
void shouldNormalizeCustomerReactively() {
    ReactiveBeforeConvertCallback<Customer> callback =
            new ReactiveCustomerCallback(policy);

    Customer input = sampleCustomer();

    StepVerifier.create(
            Mono.from(callback.onBeforeConvert(
                    input,
                    SqlIdentifier.unquoted("customers")
            ))
    )
    .assertNext(customer ->
            assertThat(customer.email()).isEqualTo("an@example.test")
    )
    .verifyComplete();
}
~~~

Nếu callback gọi repository hoặc dịch vụ reactive khác, cần kiểm tra:

- Publisher có được trả về và được tiêu thụ không?
- Không có subscribe/block nội bộ.
- Lỗi từ dependency được truyền đúng.
- Thứ tự callback được áp dụng đúng.
- Transaction context có được giữ khi cần không?
- Cancellation có dừng công việc downstream phù hợp không?

Dùng integration test với database tương thích để kiểm tra callback thực sự được gọi khi dùng R2dbcEntityTemplate hoặc repository. Mock callback trực tiếp không xác nhận lifecycle wiring.

## 21. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Callback không được gọi | Bean chưa được đăng ký hoặc thao tác không đi qua entity lifecycle API | Đăng ký callback trong ApplicationContext và kiểm tra repository/template path |
| Dữ liệu không được chuẩn hóa trước khi lưu | Đặt logic ở AfterSave hoặc raw DatabaseClient path | Dùng BeforeConvert hoặc service dùng chung |
| Reactive callback chạy nhưng save không tiếp tục | Callback trả Mono.empty() | Phát entity hoặc error signal rõ ràng |
| Callback tạo truy vấn lặp | Callback gọi repository cho từng entity | Batch, JOIN hoặc chuyển lookup lên service |
| Event loop bị chặn | Callback đồng bộ gọi blocking API hoặc callback reactive dùng block | Dùng logic đồng bộ nhẹ hoặc reactive API không blocking |
| Entity ban đầu không thay đổi | Callback trả instance mới nhưng caller dùng object cũ | Dùng entity được phát ra từ save publisher |
| Row và entity không nhất quán | BeforeSave sửa OutboundRow nhưng không đồng bộ entity | Ưu tiên sửa entity trước convert hoặc quản lý mapping rõ ràng |
| Lỗi AfterSave nhưng dữ liệu vẫn còn | Không có transaction bao quanh write và callback | Dùng reactive transaction nếu cần atomic |
| Callback chạy sai thứ tự | Dựa vào thứ tự bean tình cờ | Khai báo @Order/Ordered |
| Callback không chạy với raw SQL | DatabaseClient không thực hiện entity lifecycle mapping | Gọi logic tường minh hoặc dùng entity API phù hợp |
| Side effect bị lặp hoặc không rollback | Gửi message/email trực tiếp trong callback | Dùng outbox và consumer deduplication |
| Callback áp dụng cho nhiều database ngoài dự kiến | Callback bean dùng chung trong context | Kiểm tra entity/table và giới hạn logic rõ ràng |

## 22. Quy trình triển khai callback

Khi thêm callback vào ứng dụng, có thể làm theo trình tự:

1. Xác định lifecycle phase cần can thiệp: trước convert, trước save, sau save, sau convert hoặc delete.
2. Xác định logic là biến đổi đồng bộ hay cần Publisher.
3. Chọn interface callback tương ứng.
4. Đăng ký callback thành Spring bean.
5. Dùng constructor injection cho dependency.
6. Với entity immutable, trả về instance mới.
7. Với BeforeSaveCallback, chỉ sửa OutboundRow khi thật sự cần và giữ dữ liệu nhất quán.
8. Nếu có nhiều callback cùng phase, khai báo thứ tự.
9. Tránh block, subscribe thủ công và side effect ngoài database.
10. Kiểm tra callback có bị gọi cho từng row hoặc từng entity trong batch/aggregate không.
11. Đảm bảo raw SQL path không bỏ qua logic bắt buộc.
12. Kiểm thử trực tiếp callback và integration test qua repository/template.
13. Nếu callback lỗi sau khi SQL chạy, xác định transaction có bảo đảm rollback hay không.

## 23. Kết luận

EntityCallback cung cấp các điểm mở rộng trong vòng đời entity của Spring Data R2DBC. Callback đồng bộ trả trực tiếp entity và phù hợp với những phép biến đổi nhanh, cục bộ như chuẩn hóa dữ liệu hoặc bổ sung metadata. Callback reactive trả về Publisher, cho phép kết hợp thao tác bất đồng bộ trong pipeline mà không chặn thread.

Các phase chính gồm BeforeConvert, BeforeSave, AfterSave, AfterConvert, BeforeDelete và AfterDelete. Chọn callback theo đúng thời điểm: sửa entity trước khi convert thường dễ hiểu nhất; BeforeSave dành cho can thiệp ở mức OutboundRow; AfterConvert chạy sau mapping khi đọc. Đăng ký callback như Spring bean và dùng @Order nếu cần kiểm soát thứ tự.

Callback là một phần của entity persistence lifecycle, không tự tạo transaction và không thay thế service/domain logic, ApplicationEvent hoặc transactional outbox. Không dùng subscribe/block trong reactive callback, không thực hiện I/O blocking trong callback đồng bộ và không giả định raw SQL qua DatabaseClient sẽ kích hoạt entity callback. Kiểm thử cả callback độc lập lẫn đường repository/template thực tế để xác nhận hành vi theo đúng phiên bản Spring Data R2DBC.

