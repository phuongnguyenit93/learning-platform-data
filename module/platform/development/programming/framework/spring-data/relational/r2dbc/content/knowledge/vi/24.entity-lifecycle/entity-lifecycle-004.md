# Can thiệp dữ liệu trước khi lưu và kiểm soát thứ tự callback

Spring Data Relational R2DBC cung cấp entity callback để ứng dụng can thiệp vào dữ liệu tại các mốc trong vòng đời persistence. Callback phù hợp với những thao tác cần chạy nhất quán khi entity được lưu hoặc đọc qua repository và R2dbcEntityTemplate, chẳng hạn chuẩn hóa giá trị, bổ sung metadata, điều chỉnh dữ liệu được ghi xuống database hoặc hoàn thiện entity sau khi đọc.

Hai callback quan trọng trước khi ghi là BeforeConvertCallback và BeforeSaveCallback. Chúng chạy ở hai giai đoạn khác nhau: callback thứ nhất can thiệp vào entity trước khi Spring chuyển entity thành dữ liệu database; callback thứ hai chạy sau khi dữ liệu đã được chuyển thành OutboundRow nhưng trước khi câu lệnh ghi được thực thi. Hiểu đúng thứ tự này giúp chọn đúng điểm can thiệp và tránh sửa dữ liệu quá muộn.

Khi có nhiều callback cùng loại, có thể điều khiển thứ tự bằng Ordered hoặc @Order. Thứ tự giữa các giai đoạn vòng đời vốn được xác định bởi quy trình persistence; @Order dùng để sắp xếp các callback cùng loại. Với R2DBC, callback còn phải tuân thủ reactive model: trả về Publisher, không tự subscribe và không block.

## 1. Entity callback nằm ở đâu trong vòng đời lưu?

Khi gọi repository.save(entity) hoặc thao tác lưu tương ứng qua R2dbcEntityTemplate, Spring Data thực hiện nhiều bước trước và sau khi gửi SQL.

Mô hình khái quát:

~~~mermaid
flowchart TD
    A[Entity được truyền vào save] --> B[BeforeConvertCallback]
    B --> C[Chuyển entity thành OutboundRow]
    C --> D[BeforeSaveCallback]
    D --> E[Thực thi INSERT hoặc UPDATE]
    E --> F[AfterSaveCallback]
    F --> G[Trả kết quả reactive]
~~~

Các giai đoạn có ý nghĩa khác nhau:

1. **Trước convert:** entity vẫn là object Java. Có thể chuẩn hóa, tạo giá trị dẫn xuất hoặc trả về một entity mới.
2. **Convert:** Spring Data mapping entity thành OutboundRow, biểu diễn các cột và giá trị sẽ được bind.
3. **Trước save:** callback nhận entity và OutboundRow; có thể điều chỉnh biểu diễn dữ liệu sắp ghi.
4. **Save:** database thực hiện INSERT hoặc UPDATE.
5. **Sau save:** callback có thể quan sát hoặc hoàn thiện kết quả sau thao tác ghi.

Tên và chữ ký API cụ thể cần khớp phiên bản Spring Data R2DBC của dự án. Các ví dụ bên dưới minh họa API callback reactive phổ biến của Spring Data Relational.

### BeforeConvertCallback

BeforeConvertCallback<T> được gọi trước khi entity được chuyển thành OutboundRow. Callback nhận entity và tên bảng, sau đó trả về một Publisher<T>.

Dùng callback này khi muốn thay đổi chính entity trước khi mapping diễn ra, ví dụ:

- Chuẩn hóa chuỗi trước khi lưu.
- Tạo slug hoặc giá trị tìm kiếm dẫn xuất.
- Bổ sung timestamp hoặc metadata do ứng dụng quản lý.
- Chuẩn hóa mã định danh nghiệp vụ.
- Kiểm tra hoặc chuyển trạng thái dữ liệu trước khi ghi.

Vì callback trả về entity, nó phù hợp với entity bất biến như Java record: tạo và trả về một instance mới chứa các giá trị đã được điều chỉnh.

### BeforeSaveCallback

BeforeSaveCallback<T> chạy sau khi entity đã được chuyển thành OutboundRow, nhưng trước khi dữ liệu được ghi xuống database. Callback nhận entity, OutboundRow chứa dữ liệu đã mapping và SqlIdentifier đại diện cho bảng đích.

Callback này phù hợp khi cần điều chỉnh chính dữ liệu database sắp nhận, chẳng hạn bổ sung hoặc thay đổi một cột trong OutboundRow. Việc thay đổi row không nhất thiết làm thay đổi object entity ban đầu; hãy phân biệt dữ liệu ghi xuống database với object được trả về cho caller.

### AfterSaveCallback

AfterSaveCallback<T> chạy sau thao tác lưu. Nó phù hợp với việc quan sát kết quả hoặc bổ sung xử lý hậu lưu nằm trong cùng reactive pipeline. Nếu callback phát lỗi, publisher lưu có thể kết thúc bằng lỗi dù câu lệnh ghi đã được thực thi.

Khi cần một side effect phải xảy ra sau khi transaction commit, không nên mặc định AfterSaveCallback đồng nghĩa với sau commit. Callback này là sau thao tác save, còn transaction ngoài có thể vẫn đang mở và sau đó rollback.

## 2. Chuẩn hóa entity trước khi mapping

Ví dụ entity Customer dùng record:

~~~java
@Table("customers")
public record Customer(
    @Id UUID id,
    String name,
    String normalizedName,
    Instant createdAt
) {
    public Customer withNormalizedName(String value) {
        return new Customer(id, name, value, createdAt);
    }
}
~~~

Ta muốn lưu normalizedName được tạo từ name, nhưng không muốn lặp logic chuẩn hóa ở mọi service.

Tạo callback:

~~~java
@Component
public class NormalizeCustomerBeforeConvert
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.name()
            .trim()
            .toLowerCase(Locale.ROOT);

        return Mono.just(customer.withNormalizedName(normalized));
    }
}
~~~

Các import callback chính xác có thể khác theo phiên bản Spring Data Relational/R2DBC; dùng package callback được cung cấp bởi dependency của dự án. Phần cốt lõi là callback nhận entity, tạo giá trị mới và trả về Publisher<Customer>.

Khi repository lưu Customer, Spring Data nhận entity do callback trả về và tiếp tục mapping entity đó thành row. Vì thế, normalizedName được tính trước khi SQL được tạo.

### Vì sao dùng Locale.ROOT?

Chuẩn hóa dữ liệu không nên phụ thuộc locale mặc định của máy chạy ứng dụng. Với mã kỹ thuật hoặc chuỗi dùng để so sánh không phân biệt hoa thường, Locale.ROOT giúp kết quả ổn định giữa các môi trường.

Tuy nhiên, lower-case không phải quy tắc chuẩn hóa phù hợp cho mọi ngôn ngữ hoặc mọi nghiệp vụ tìm kiếm. Nếu cần Unicode normalization, accent folding hoặc quy tắc collation, hãy xác định rõ hợp đồng dữ liệu và dùng cùng quy tắc ở cả lúc ghi lẫn lúc tìm.

### Không ghi đè dữ liệu nguồn ngoài ý muốn

Nếu name là dữ liệu người dùng nhập, hãy giữ nguyên nó và lưu giá trị dẫn xuất vào normalizedName. Không tự động sửa trường gốc nếu nghiệp vụ cần giữ nguyên cách viết ban đầu.

Nếu entity là mutable class, callback có thể sửa field rồi trả về chính entity. Với record hoặc immutable object, hãy tạo instance mới. Trong cả hai trường hợp, callback nên có hành vi rõ ràng và có thể lặp lại mà không làm dữ liệu biến đổi ngoài dự kiến.

## 3. Điều chỉnh OutboundRow trước khi ghi

BeforeSaveCallback cho phép can thiệp sau mapping. Đây là lựa chọn khi muốn thay đổi giá trị cột mà không cần thay đổi entity Java.

Ví dụ minh họa callback bổ sung cột search_key vào row:

~~~java
@Component
public class AddCustomerSearchKeyBeforeSave
        implements BeforeSaveCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeSave(
            Customer customer,
            OutboundRow row,
            SqlIdentifier table) {

        String searchKey = customer.name()
            .trim()
            .toLowerCase(Locale.ROOT);

        row.put(
            SqlIdentifier.unquoted("search_key"),
            Parameter.from(searchKey)
        );

        return Mono.just(customer);
    }
}
~~~

OutboundRow biểu diễn các giá trị sẽ được bind vào câu lệnh ghi. SqlIdentifier dùng để chỉ định cột, còn Parameter biểu diễn giá trị được bind. Kiểu API và package có thể khác theo phiên bản Spring Data R2DBC; hãy đối chiếu dependency đang sử dụng trước khi sao chép import.

Dùng cách này khi:

- Giá trị chỉ cần tồn tại trong database representation.
- Entity không có field tương ứng.
- Cần điều chỉnh giá trị đã mapping ngay trước khi ghi.
- Muốn can thiệp vào cách bind một cột cụ thể.

Nếu giá trị dẫn xuất cần xuất hiện trong object trả về, được dùng trong logic domain hoặc được serialize cho API, nên đặt nó trong entity trước convert thay vì chỉ sửa OutboundRow.

### Không thêm cột không tồn tại trong schema

Trước khi thêm một giá trị vào OutboundRow, bảo đảm cột đó tồn tại và kiểu dữ liệu tương thích. Callback không thay thế migration. Nếu callback cố ghi cột chưa có trong schema, database sẽ trả lỗi SQL hoặc lỗi cột không tồn tại.

### Xử lý NULL đúng kiểu

Nếu giá trị có thể null, không tự tạo Parameter từ một tham chiếu null mà không xem xét API hỗ trợ. Hãy dùng cách biểu diễn parameter null có type theo API Spring R2DBC của phiên bản dự án. Cột nullable và non-nullable cũng cần có chính sách rõ ràng.

## 4. Phân biệt BeforeConvert và BeforeSave

Hai callback đều chạy trước khi database ghi dữ liệu, nhưng chúng can thiệp ở hai tầng khác nhau.

| Tiêu chí | BeforeConvertCallback | BeforeSaveCallback |
| --- | --- | --- |
| Đầu vào chính | Entity và table identifier. | Entity, OutboundRow và table identifier. |
| Thời điểm | Trước khi mapping entity thành row. | Sau mapping, trước khi thực thi câu lệnh ghi. |
| Có thể thay đổi | Entity Java. | OutboundRow; có thể trả về entity được điều chỉnh theo API. |
| Phù hợp với | Chuẩn hóa domain data, tạo field dẫn xuất. | Điều chỉnh biểu diễn database hoặc giá trị cột cụ thể. |
| Khi nào nên chọn | Giá trị cần tồn tại trong entity và row. | Giá trị chỉ cần thay đổi ở tầng persistence mapping. |

Ví dụ, nếu muốn lưu tên khách hàng đã trim vào chính property name, dùng BeforeConvertCallback. Nếu muốn giữ name gốc trong entity nhưng ghi một cột search_key riêng, BeforeSaveCallback có thể phù hợp.

Không nên dùng cả hai callback để thực hiện cùng một phép biến đổi. Nếu callback đầu đã chuẩn hóa entity rồi callback sau tiếp tục chuẩn hóa cùng trường, logic trở nên khó theo dõi và dễ tạo khác biệt giữa object trả về với dữ liệu database.

## 5. Thứ tự callback giữa các giai đoạn

Thứ tự vòng đời được quyết định bởi persistence pipeline. Với thao tác lưu thông thường:

1. Các BeforeConvertCallback chạy trước khi mapping.
2. Spring Data chuyển entity thành OutboundRow.
3. Các BeforeSaveCallback chạy trước khi SQL được thực thi.
4. Database thực hiện thao tác ghi.
5. Các AfterSaveCallback chạy sau thao tác ghi.

Không thể dùng @Order để đưa một BeforeSaveCallback chạy trước giai đoạn convert. @Order sắp xếp các callback trong cùng một giai đoạn callback; nó không thay đổi thứ tự cố định giữa các giai đoạn lifecycle.

Ví dụ, một callback chuẩn hóa tên cần chạy trước callback tính khóa tìm kiếm. Cả hai có thể cùng là BeforeConvertCallback, và thứ tự được chỉ định bằng @Order.

~~~java
@Component
@Order(10)
public class TrimCustomerName
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return Mono.just(customer.withName(customer.name().trim()));
    }
}
~~~

~~~java
@Component
@Order(20)
public class BuildCustomerSearchKey
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String key = customer.name().toLowerCase(Locale.ROOT);
        return Mono.just(customer.withSearchKey(key));
    }
}
~~~

Ví dụ giả định Customer có các method withName và withSearchKey. Callback thứ nhất trim tên; callback thứ hai nhận entity đã được callback thứ nhất cập nhật và tạo search key từ giá trị đó.

Với Spring ordering, giá trị order thấp hơn có độ ưu tiên cao hơn và được thực thi trước. Có thể dùng hằng số Ordered thay cho số magic:

~~~java
@Component
public class TrimCustomerName
        implements BeforeConvertCallback<Customer>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return Mono.just(customer.withName(customer.name().trim()));
    }
}
~~~

### Tránh hai callback cùng sửa một field mà không có hợp đồng

Nếu hai callback cùng ghi normalizedName, kết quả cuối phụ thuộc thứ tự. Hãy quy định rõ callback nào sở hữu field và callback nào chỉ đọc kết quả. Nếu các callback có cùng order, đừng dựa vào thứ tự đăng ký bean hoặc thứ tự scan class để xác định kết quả.

Đối với logic phụ thuộc chặt chẽ, một callback duy nhất điều phối các bước tuần tự có thể dễ hiểu hơn nhiều callback nhỏ cùng sửa một entity.

## 6. Thứ tự giữa các callback cùng loại

Khi có nhiều callback cùng interface, có thể điều khiển thứ tự qua:

- @Order trên class callback.
- Ordered và getOrder().
- Metadata ordering được framework hỗ trợ cho bean.

Ví dụ:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class NormalizeCodeCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

~~~java
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 10)
public class AddAuditMetadataCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Các callback có order nhỏ hơn chạy trước. Dùng hằng số Ordered.HIGHEST_PRECEDENCE và Ordered.LOWEST_PRECEDENCE giúp tránh số magic khi muốn đặt callback gần đầu hoặc cuối chuỗi.

Nếu nhiều callback cùng order, không nên dựa vào thứ tự ngẫu nhiên do container phát hiện bean. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy đặt giá trị order rõ ràng hoặc gộp các bước phụ thuộc vào một callback có thứ tự nội bộ xác định.

### Order không thay đổi transaction boundary

@Order chỉ điều khiển thứ tự callback trong chuỗi được framework gọi. Nó không tạo transaction, không commit dữ liệu và không bảo đảm một callback chạy sau khi transaction commit. Muốn kiểm soát transaction, dùng @Transactional hoặc TransactionalOperator ở ranh giới thích hợp.

## 7. Callback reactive phải trả Publisher

Entity callback của R2DBC là reactive. Callback trả về Publisher<T>, thường dùng Mono<T> khi xử lý một entity.

Không tự gọi subscribe() trong callback:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    auditService.record(customer).subscribe();
    return Mono.just(customer);
}
~~~

Cách này tạo một subscription tách rời. Spring Data không chờ audit hoàn tất, lỗi audit không truyền về thao tác save và transaction context có thể không được chia sẻ như mong muốn.

Nếu một bước bất đồng bộ thực sự cần thiết để tạo entity, hãy nối nó vào publisher trả về:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    return policyService.resolveCustomerTier(customer)
        .map(customer::withTier);
}
~~~

Ví dụ giả định resolveCustomerTier trả Mono<CustomerTier> và withTier tạo entity mới. Spring Data sẽ đợi publisher callback hoàn tất trước khi tiếp tục mapping và lưu.

Tuy nhiên, callback không nên trở thành nơi gọi nhiều dịch vụ từ xa cho mỗi entity. Điều đó làm thao tác persistence phụ thuộc network, tăng latency và tạo side effect khó kiểm soát. Nếu dữ liệu cần thiết để lưu phải được tính từ một dịch vụ khác, thường nên điều phối ở application service trước khi gọi repository.

### Không block trong callback

Không gọi block() để chờ dữ liệu reactive:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    CustomerTier tier = policyService.resolveCustomerTier(customer).block();
    return Mono.just(customer.withTier(tier));
}
~~~

Cách này phá vỡ non-blocking execution, có thể gây deadlock trên event-loop thread và tách callback khỏi reactive transaction context. Hãy trả publisher và kết hợp bằng map, flatMap, then hoặc operator phù hợp.

## 8. Callback có thể phát lỗi và ảnh hưởng thao tác save

Nếu BeforeConvertCallback hoặc BeforeSaveCallback phát lỗi, pipeline lưu thường dừng trước khi câu lệnh ghi được thực hiện. Đây là vị trí thích hợp cho các kiểm tra hoặc biến đổi bắt buộc phải hoàn thành trước khi ghi.

Ví dụ:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        SqlIdentifier table) {

    if (product.price().signum() < 0) {
        return Mono.error(
            new InvalidProductPriceException(product.price())
        );
    }

    return Mono.just(product);
}
~~~

Nếu callback phát lỗi, repository save trả publisher lỗi. Application service có thể chuyển exception thành lỗi domain/API phù hợp.

AfterSaveCallback có đặc điểm khác: câu lệnh ghi có thể đã được thực thi trước khi callback chạy. Nếu callback sau lưu phát lỗi:

- Khi save nằm trong transaction và lỗi truyền ra ngoài transaction boundary, transaction có thể rollback.
- Khi không có transaction bao quanh, database write có thể đã thành công dù publisher trả lỗi do callback.
- Caller có thể retry và tạo thao tác lặp nếu không có idempotency.

Vì vậy, không nên đặt một thao tác network không ổn định trong AfterSaveCallback rồi coi lỗi của nó là bằng chứng database chưa lưu.

### Callback không phải nơi gửi email hoặc phát thông báo tùy tiện

Nếu cần phát sự kiện sau khi dữ liệu commit, AfterSaveCallback không đồng nghĩa với after-commit. Transaction ngoài có thể rollback sau callback. Dùng transaction synchronization phù hợp hoặc transactional outbox để bảo đảm thông điệp được phát dựa trên trạng thái đã commit.

## 9. Callback và auditing

Spring Data R2DBC có hỗ trợ auditing để tự động điền các trường như:

- CreatedDate: thời điểm tạo.
- LastModifiedDate: thời điểm cập nhật gần nhất.
- CreatedBy: người tạo.
- LastModifiedBy: người cập nhật cuối.

Ví dụ entity:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    String status,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant updatedAt,
    @CreatedBy String createdBy,
    @LastModifiedBy String modifiedBy
) {}
~~~

Kích hoạt auditing bằng cấu hình tương ứng của Spring Data R2DBC:

~~~java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
~~~

Nếu cần xác định người dùng hiện tại trong reactive security context, cấu hình một ReactiveAuditorAware<T> trả về Mono<T>:

~~~java
@Component
public class CurrentAuditor implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

Ví dụ trên giả định ứng dụng dùng Spring Security reactive và có authentication trong Reactor Context. Nếu không có người dùng hiện tại, cần quyết định có trả Mono.empty() hay cung cấp actor hệ thống theo hợp đồng ứng dụng.

Auditing được triển khai dựa trên entity callback nội bộ. Không nên đồng thời tự điền cùng trường bằng một callback khác nếu không có chủ đích, vì có thể tạo hai nguồn giá trị và phụ thuộc thứ tự không cần thiết.

### Thời gian tạo và cập nhật phải có semantics rõ

Không nên luôn ghi đè createdAt mỗi lần save. Trường này cần giữ thời điểm tạo ban đầu. updatedAt có thể thay đổi mỗi lần cập nhật thành công. Nếu entity immutable, auditing infrastructure cần được cấu hình để tạo bản sao mới phù hợp với constructor/property mapping.

Không lấy thời gian từ nhiều nguồn không đồng nhất. Nếu database có default timestamp hoặc trigger, hãy quyết định nguồn dữ liệu chính là application hay database và mapping kết quả tương ứng.

## 10. Callback khi đọc dữ liệu

Ngoài callback trước và sau khi lưu, Spring Data Relational còn có các callback ở quá trình load/convert, tùy phiên bản và API:

- Callback sau khi row được load.
- Callback sau khi row được chuyển thành entity.

Chúng có thể hữu ích khi cần hoàn thiện object sau khi đọc, nhưng không nên dùng để che giấu một schema mapping sai. Nếu cột không được SELECT hoặc converter không đúng, hãy sửa mapping trước.

Phân biệt callback đọc và ghi:

| Nhóm | Mục đích | Ví dụ |
| --- | --- | --- |
| BeforeConvert | Chuẩn bị entity trước khi ghi. | Trim tên, tạo normalized field. |
| BeforeSave | Điều chỉnh row trước khi ghi. | Bổ sung giá trị database representation. |
| AfterSave | Xử lý sau thao tác ghi. | Quan sát kết quả lưu hoặc bổ sung metadata cho object trả về. |
| AfterLoad/AfterConvert | Hoàn thiện entity trong pipeline đọc. | Tạo giá trị dẫn xuất không được lưu riêng. |

Tên callback cụ thể, thứ tự và chữ ký cần xác minh theo phiên bản Spring Data Relational. Không giả định callback đọc có thể thay thế SELECT join hoặc lazy loading; R2DBC không tự cung cấp lazy loading như ORM blocking truyền thống.

## 11. Callback được gọi ở đâu và khi nào?

Callback được tích hợp vào các thao tác entity mapping của Spring Data, chẳng hạn repository và R2dbcEntityTemplate. Nếu ứng dụng dùng DatabaseClient để viết SQL thuần và tự map row, không nên giả định các entity lifecycle callback sẽ tự chạy.

Ví dụ repository:

~~~java
return customerRepository.save(customer);
~~~

Hoặc template:

~~~java
return template.insert(Customer.class)
    .using(customer);
~~~

Các thao tác này đi qua mapping lifecycle của Spring Data và là nơi callback entity được áp dụng theo cấu hình.

Trong khi đó:

~~~java
return databaseClient.sql("""
        INSERT INTO customers (id, name)
        VALUES (:id, :name)
        """)
    .bind("id", customer.id())
    .bind("name", customer.name())
    .fetch()
    .rowsUpdated();
~~~

Đây là SQL trực tiếp. Ứng dụng tự chịu trách nhiệm chuẩn hóa dữ liệu, bind tham số và mapping kết quả; không nên trông chờ callback entity tự được gọi.

Điều này quan trọng khi một dự án trộn repository với SQL thuần. Nếu quy tắc chuẩn hóa chỉ nằm trong callback repository, các lệnh ghi qua DatabaseClient có thể bỏ qua quy tắc đó. Hãy đưa quy tắc nghiệp vụ dùng chung vào domain/application service hoặc một thành phần dùng chung mà mọi đường ghi đều gọi.

## 12. Callback và repository saveAll

Khi lưu nhiều entity, callback có thể được gọi cho từng entity theo đường mapping tương ứng. Không nên giả định một callback chỉ chạy một lần cho cả batch.

Điều này ảnh hưởng đến:

- Hiệu năng nếu callback thực hiện truy vấn phụ.
- Thứ tự xử lý từng entity.
- Side effect nếu callback gửi thông báo.
- Tính nhất quán nếu một entity trong batch phát lỗi.
- Việc tạo timestamp hoặc giá trị dẫn xuất cho từng phần tử.

Ví dụ callback chỉ chuẩn hóa chuỗi thường nhẹ và phù hợp. Callback gọi dịch vụ từ xa cho từng entity có thể tạo hàng trăm request trong một lần saveAll. Nếu cần nạp dữ liệu tham chiếu, hãy cân nhắc lấy một lần ở service rồi truyền kết quả vào entity trước khi gọi repository.

Nếu dùng DatabaseClient với một câu SQL batch hoặc custom bulk insert, lifecycle callback entity không tự động được bảo đảm. Kiểm tra đường thực thi cụ thể.

## 13. Tránh đệ quy và side effect trong callback

Callback được gọi trong pipeline persistence. Nếu callback gọi lại repository để lưu chính entity đang được xử lý, nó có thể kích hoạt callback lần nữa và tạo vòng lặp.

Ví dụ không nên làm:

~~~java
@Component
public class UpdateCustomerCallback
        implements BeforeConvertCallback<Customer> {

    private final CustomerRepository repository;

    public UpdateCustomerCallback(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return repository.save(customer)
            .thenReturn(customer);
    }
}
~~~

Callback này gọi lại save, từ đó có thể gọi lại chính callback và lặp vô hạn. Callback nên biến đổi entity hoặc row được truyền vào, không gọi lại persistence operation của chính entity đó.

Cũng nên tránh:

- Gửi email hoặc gọi webhook.
- Publish message trực tiếp trước commit.
- Thực hiện truy vấn phụ cho từng entity nếu có thể tính trước.
- Đọc trạng thái toàn cục hoặc dùng mutable singleton để truyền dữ liệu giữa callback.
- Dùng callback để thực hiện quy trình nghiệp vụ nhiều bước.

Callback nên tập trung vào persistence concern nhỏ, đồng bộ và có thể kiểm thử.

## 14. Đăng ký callback trong Spring context

Callback có thể được đăng ký như Spring bean qua @Component hoặc cấu hình @Bean. Spring Data dùng entity callback infrastructure để phát hiện và thực thi callback tương ứng với loại entity.

Ví dụ đăng ký bằng cấu hình:

~~~java
@Configuration
public class CustomerCallbackConfiguration {

    @Bean
    NormalizeCustomerBeforeConvert normalizeCustomerBeforeConvert() {
        return new NormalizeCustomerBeforeConvert();
    }
}
~~~

Nếu callback cần dependency, có thể dùng constructor injection:

~~~java
@Component
public class NormalizeCustomerBeforeConvert
        implements BeforeConvertCallback<Customer> {

    private final CustomerNameNormalizer normalizer;

    public NormalizeCustomerBeforeConvert(
            CustomerNameNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return Mono.just(
            customer.withNormalizedName(
                normalizer.normalize(customer.name())
            )
        );
    }
}
~~~

Không tạo callback bằng new trong service nếu muốn Spring quản lý ordering và dependency injection. Đăng ký callback như bean giúp framework áp dụng cơ chế callback nhất quán.

## 15. Kiểm thử callback và thứ tự thực thi

Kiểm thử callback nên xác nhận hai điều: callback được gọi ở đúng giai đoạn, và dữ liệu cuối cùng được ghi đúng như mong muốn.

### Unit test cho BeforeConvertCallback

Có thể gọi trực tiếp callback để kiểm tra phép biến đổi:

~~~java
@Test
void normalizesNameBeforeConversion() {
    Customer input = new Customer(
        UUID.randomUUID(),
        "  Alice Example  ",
        null,
        Instant.now()
    );

    Customer result = Mono.from(
        callback.onBeforeConvert(input, SqlIdentifier.unquoted("customers"))
    ).block();

    assertEquals("alice example", result.normalizedName());
    assertEquals("  Alice Example  ", result.name());
}
~~~

Đây là unit test cho logic callback; block trong test đồng bộ có thể chấp nhận được nếu không nằm trong production reactive flow. Nếu test chạy theo reactive style, có thể dùng StepVerifier thay thế.

### Integration test xác nhận dữ liệu đã được lưu

Gọi repository thật và đọc lại:

~~~java
@Test
void savesNormalizedName() {
    Customer customer = new Customer(
        UUID.randomUUID(),
        "  Alice Example  ",
        null,
        Instant.now()
    );

    StepVerifier.create(
        customerRepository.save(customer)
            .flatMap(saved ->
                customerRepository.findById(saved.id())
            )
    )
    .assertNext(saved ->
        assertEquals("alice example", saved.normalizedName())
    )
    .verifyComplete();
}
~~~

Test này xác nhận callback được tích hợp vào repository mapping path và giá trị normalizedName được ghi xuống database.

### Kiểm thử thứ tự callback

Nếu thứ tự có ý nghĩa, hãy dùng hai callback có @Order khác nhau và xác minh kết quả. Ví dụ callback A trim chuỗi trước, callback B tạo slug từ chuỗi đã trim. Nếu đảo thứ tự, test cần phát hiện kết quả khác.

Không chỉ test getOrder(); hãy kiểm tra kết quả cuối của pipeline vì điều cần bảo đảm là callback thực sự được framework phát hiện và chạy theo thứ tự.

### Kiểm thử lỗi callback

Kiểm tra callback trước save phát lỗi thì database không có bản ghi tương ứng. Với lỗi từ AfterSaveCallback, kiểm tra cả trường hợp có transaction và không có transaction để hiểu trạng thái ghi thực tế. Đừng suy luận rằng publisher lỗi luôn có nghĩa INSERT chưa xảy ra.

## 16. Các lỗi thường gặp khi dùng callback

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Callback không chạy | Callback không được đăng ký thành bean hoặc thao tác đi qua SQL thuần. | Đăng ký bean và dùng repository/template mapping path. |
| Chuẩn hóa không xuất hiện trong DB | Callback sửa entity nhưng không trả entity mới, hoặc sửa sai OutboundRow. | Trả đúng entity đã cập nhật và kiểm thử readback. |
| Callback chạy sai thứ tự | Không khai báo order hoặc nhiều callback có cùng order. | Dùng @Order/Ordered rõ ràng. |
| Dữ liệu trong entity khác DB | Chỉ sửa OutboundRow mà không sửa entity. | Chọn đúng tầng callback theo nơi cần thay đổi. |
| Save bị chậm bất thường | Callback gọi network hoặc query phụ cho từng entity. | Giữ callback nhẹ; điều phối I/O ở service. |
| Callback tạo vòng lặp | Gọi repository.save lại trong callback. | Chỉ biến đổi entity/row được truyền vào. |
| Lỗi callback sau save khiến caller thấy lỗi | AfterSaveCallback phát error sau khi SQL đã chạy. | Xem xét transaction, idempotency và vị trí side effect. |
| Sự kiện phát ra dù transaction rollback | Nhầm AfterSave với after-commit. | Dùng outbox hoặc cơ chế after-commit phù hợp. |
| Bulk SQL bỏ qua quy tắc callback | DatabaseClient không đi qua entity lifecycle mapping. | Chia sẻ logic ở service/domain hoặc gọi rõ ràng ở đường bulk. |
| Auditing bị ghi đè | Nhiều callback cùng cập nhật trường audit. | Dùng auditing infrastructure hoặc xác định một nơi sở hữu trường. |

## 17. Quy trình thiết kế callback

Khi cần can thiệp vào dữ liệu trước khi lưu, hãy đi theo trình tự:

1. **Xác định dữ liệu cần thay đổi:** field Java hay giá trị database representation?
2. **Chọn giai đoạn:** dùng BeforeConvertCallback nếu cần sửa entity trước mapping; dùng BeforeSaveCallback nếu cần sửa OutboundRow.
3. **Giữ callback thuần và nhỏ:** tránh network, side effect và gọi lại repository.
4. **Dùng reactive composition:** trả Publisher, không subscribe hoặc block trong production.
5. **Xác định thứ tự:** đặt @Order/Ordered cho callback cùng loại nếu có phụ thuộc.
6. **Tránh nhiều nguồn ghi:** mỗi field dẫn xuất hoặc audit nên có chủ sở hữu rõ ràng.
7. **Xem xét transaction:** AfterSave không đồng nghĩa after-commit; dùng outbox cho side effect cần bảo đảm.
8. **Kiểm tra đường ghi:** repository/template có callback; SQL thuần cần xử lý riêng.
9. **Kiểm thử logic và tích hợp:** test callback độc lập, sau đó save/readback qua database thật.
10. **Đo hiệu năng:** đặc biệt với saveAll và callback có I/O.

Entity callback giúp tập trung những quy tắc persistence cần chạy nhất quán trong vòng đời entity. BeforeConvertCallback phù hợp khi muốn thay đổi entity trước mapping; BeforeSaveCallback phù hợp khi cần điều chỉnh row được ghi; AfterSaveCallback chạy sau thao tác save nhưng không bảo đảm transaction đã commit. Dùng @Order hoặc Ordered để xác định thứ tự giữa các callback cùng giai đoạn, giữ reactive publisher liền mạch và kiểm thử qua repository/template thực tế để dữ liệu được can thiệp đúng thời điểm.
