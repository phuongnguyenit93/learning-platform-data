# Cập nhật một phần, giá trị null và tránh ghi đè dữ liệu ngoài ý muốn

Cập nhật một phần (partial update) chỉ thay đổi những trường mà client thực sự muốn sửa. Trong API Spring Data JPA, lỗi phổ biến là nhận một DTO có nhiều thuộc tính `null`, tạo entity mới từ DTO rồi gọi `save()`. Các thuộc tính không có trong request có thể bị hiểu thành giá trị null và ghi đè dữ liệu đang có.

Để cập nhật an toàn, cần xác định rõ ba trạng thái của mỗi trường:

1. **Không được gửi (absent):** giữ nguyên giá trị hiện tại.
2. **Được gửi với null:** xóa giá trị nếu nghiệp vụ và schema cho phép.
3. **Được gửi với một giá trị:** thay thế giá trị hiện tại.

Một thuộc tính Java thông thường kiểu `String` sau khi deserialize JSON không thể tự phân biệt trường hợp absent và trường hợp được gửi rõ ràng với `null`. Thiết kế DTO, mapping và transaction phải giữ được ý nghĩa này cho đến lúc cập nhật entity.

## 1. Phân biệt PUT, PATCH và ý nghĩa của null

Theo quy ước HTTP phổ biến:

- `PUT` thường thay thế toàn bộ representation của tài nguyên. Client cần gửi đầy đủ các trường mà representation yêu cầu.
- `PATCH` áp dụng một thay đổi một phần. Trường không xuất hiện thường được giữ nguyên, còn cách diễn giải `null` phụ thuộc định dạng và contract API.

Với JSON thông thường:

```json
{
  "name": "Lan"
}
```

Request chỉ có `name`; client không yêu cầu thay đổi `email`.

```json
{
  "name": "Lan",
  "email": null
}
```

Request thứ hai có mặt trường `email` và gửi giá trị null. Nếu API quy định null có nghĩa xóa email, server phải đặt email thành null. Nếu API quy định email bắt buộc, server phải trả lỗi validation.

Không nên mặc định rằng mọi giá trị null đều có cùng ý nghĩa. Hãy ghi rõ contract cho từng trường, đặc biệt với số, boolean, ngày giờ, quan hệ và collection.

## 2. Vì sao tạo entity từ DTO rồi save() có thể làm mất dữ liệu?

Giả sử entity:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;

    private String phone;

    // constructors, getters and setters
}
```

DTO chỉ nhận một số trường:

```java
public record CustomerUpdateRequest(
        String name,
        String email
) {
}
```

Một cách xử lý dễ gây lỗi:

```java
@Transactional
public void update(Long id, CustomerUpdateRequest request) {
    Customer customer = new Customer();
    customer.setId(id);
    customer.setName(request.name());
    customer.setEmail(request.email());

    customerRepository.save(customer);
}
```

Nếu client chỉ gửi `name`, `request.email()` sẽ là null. Entity mới cũng có `phone = null`. Khi Spring Data JPA chọn `EntityManager.merge()` cho entity đã tồn tại, trạng thái của entity truyền vào được sao chép sang một entity managed. Những trường null trong đối tượng detached có thể ghi đè giá trị đang có trong database.

Cần nhớ:

- `save()` của Spring Data JPA thường gọi `persist()` nếu entity được nhận diện là mới.
- Với entity không mới, `save()` thường gọi `merge()`.
- `merge()` sao chép trạng thái của đối tượng đầu vào sang instance managed và trả về instance managed.
- Đối tượng truyền vào `merge()` vẫn không trở thành instance managed chỉ vì đã gọi `merge()`.

Vì vậy, không dùng entity được dựng từ một DTO thiếu dữ liệu như một bản ghi đầy đủ để gọi `save()` khi mục tiêu chỉ là cập nhật một vài thuộc tính.

## 3. Cách an toàn: tải entity managed rồi chỉ sửa trường được gửi

Với partial update thông thường, cách dễ kiểm soát là tải entity trong transaction, áp dụng các thay đổi được phép rồi để JPA dirty checking ghi các thuộc tính đã thay đổi.

```java
@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Customer updateName(Long id, String newName) {
        Customer customer = customers.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Customer not found: " + id));

        customer.setName(newName);

        // customer đang managed trong transaction.
        // Dirty checking ghi thay đổi khi flush/commit.
        return customer;
    }
}
```

Entity được tải bằng repository trong transaction đang hoạt động. Khi chỉ gọi setter cho `name`, các trường `email` và `phone` không bị gán lại. Không cần gọi `save()` thêm cho entity managed trong cùng persistence context; dirty checking sẽ phát hiện thay đổi.

Transaction cần bao quanh cả thao tác đọc và cập nhật. Nếu chỉ gọi `findById()` trong một repository transaction ngắn rồi sửa entity sau khi method đó kết thúc, entity có thể đã detached và thay đổi sau đó không được tự động lưu.

Cách này cũng cho phép kiểm tra quyền, trạng thái hiện tại và quy tắc nghiệp vụ trước khi sửa. Không nên nhận entity JPA trực tiếp từ request body rồi gắn nó vào persistence context.

## 4. Giữ được ba trạng thái absent, null và value trong DTO

Một DTO dùng các trường `String` thông thường không phân biệt được absent với explicit null sau khi deserialize. Với Jackson, có thể dùng setter để đánh dấu trường đã xuất hiện trong JSON. Setter được gọi cả khi giá trị là null, còn trường absent thì setter không được gọi.

Ví dụ DTO:

```java
import com.fasterxml.jackson.annotation.JsonSetter;

public class CustomerPatchRequest {

    private boolean nameProvided;
    private String name;

    private boolean emailProvided;
    private String email;

    @JsonSetter("name")
    public void setName(String name) {
        this.nameProvided = true;
        this.name = name;
    }

    @JsonSetter("email")
    public void setEmail(String email) {
        this.emailProvided = true;
        this.email = email;
    }

    public boolean isNameProvided() {
        return nameProvided;
    }

    public String getName() {
        return name;
    }

    public boolean isEmailProvided() {
        return emailProvided;
    }

    public String getEmail() {
        return email;
    }
}
```

Với cấu hình Jackson mặc định cho setter, `@JsonSetter` nhận explicit null. Nếu cấu hình `Nulls.SKIP` hoặc custom deserializer, hành vi có thể khác; hãy kiểm thử theo cấu hình thực tế của ứng dụng.

Service áp dụng đúng ba trạng thái:

```java
@Transactional
public Customer patch(Long id, CustomerPatchRequest request) {
    Customer customer = customers.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException(
                            "Customer not found: " + id));

    if (request.isNameProvided()) {
        if (request.getName() == null
                || request.getName().isBlank()) {
            throw new IllegalArgumentException(
                    "Name must not be blank");
        }
        customer.setName(request.getName());
    }

    if (request.isEmailProvided()) {
        // null có nghĩa xóa email theo contract của API.
        customer.setEmail(request.getEmail());
    }

    return customer;
}
```

Kết quả:

| JSON gửi lên | `name` | `email` |
|---|---|---|
| `{}` | Giữ nguyên | Giữ nguyên |
| `{"name":"Lan"}` | Đổi thành Lan | Giữ nguyên |
| `{"email":null}` | Giữ nguyên | Đặt null nếu được phép |
| `{"email":"lan@example.com"}` | Giữ nguyên | Đổi thành địa chỉ mới |
| `{"name":null}` | Validation thất bại trong ví dụ | Giữ nguyên |

Đây là một cách triển khai đơn giản. Với DTO có nhiều trường, có thể tạo kiểu wrapper biểu diễn trạng thái `UNSET`, `NULL` và `VALUE`, hoặc dùng thư viện như `JsonNullable<T>` để thể hiện rõ ba trạng thái. Không nên dựa vào `Optional<T>` như một giải pháp mặc định nếu chưa xác minh cách thư viện JSON xử lý absent và explicit null.

## 5. Quy định null theo từng loại dữ liệu

Null cần được định nghĩa theo ý nghĩa nghiệp vụ, không chỉ theo kiểu Java.

| Loại trường | Absent | Explicit null | Giá trị được gửi |
|---|---|---|---|
| Tên bắt buộc | Giữ nguyên | Từ chối | Kiểm tra rồi cập nhật |
| Email tùy chọn | Giữ nguyên | Xóa email | Kiểm tra định dạng rồi cập nhật |
| Số điện thoại tùy chọn | Giữ nguyên | Xóa số điện thoại | Chuẩn hóa rồi cập nhật |
| Số lượng | Giữ nguyên | Thường từ chối | Kiểm tra miền giá trị |
| Boolean | Giữ nguyên | Quy định rõ có cho phép null không | Cập nhật true/false |
| Collection | Giữ nguyên | Quy định giữ, xóa hoặc từ chối | Thay thế hoặc áp dụng phép thêm/xóa |

Cần phân biệt null với chuỗi rỗng `""`, chuỗi chỉ có khoảng trắng và collection rỗng. Ví dụ `email = ""` không tự động giống `email = null`; API nên chuẩn hóa hoặc từ chối theo contract.

Ở tầng database, cột phải cho phép null nếu nghiệp vụ muốn xóa giá trị. Constraint `NOT NULL`, `@NotNull`, validation ở service hoặc trigger có thể khiến thao tác đặt null thất bại. Hãy kiểm tra tất cả các lớp ràng buộc liên quan.

## 6. MapStruct và chiến lược bỏ qua null

MapStruct hỗ trợ `NullValuePropertyMappingStrategy.IGNORE` cho update mapping trên một target hiện có:

```java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    @BeanMapping(
        nullValuePropertyMappingStrategy =
                NullValuePropertyMappingStrategy.IGNORE
    )
    void updateFrom(
            CustomerUpdateRequest request,
            @MappingTarget Customer customer);
}
```

Với cấu hình này, thuộc tính null từ source được bỏ qua và giá trị cũ trên target được giữ nguyên. Điều này hữu ích khi contract của DTO quy định null có nghĩa “không cập nhật”.

Tuy nhiên, chiến lược IGNORE làm mất khả năng dùng null để xóa một trường. Nếu API cần cả hai hành vi absent = giữ nguyên và explicit null = xóa, DTO phải giữ thông tin presence riêng. Có thể dùng `@Condition`, custom mapping method hoặc áp dụng các trường có presence thủ công trước/sau mapping.

Không dùng `NullValuePropertyMappingStrategy.IGNORE` như một cách xử lý toàn cục nếu các trường có quy tắc null khác nhau. Một trường tùy chọn có thể cần được xóa, trong khi trường bắt buộc phải từ chối null.

## 7. JSON Merge Patch và contract của API

Nếu API dùng `Content-Type: application/merge-patch+json`, JSON Merge Patch (RFC 7396) định nghĩa:

- Thuộc tính không có trong patch: giữ nguyên.
- Thuộc tính có giá trị null: xóa thành viên tương ứng.
- Thuộc tính có object: áp dụng merge đệ quy.
- Thuộc tính có array: thay thế toàn bộ array, không tự merge từng phần tử.

Ví dụ:

```json
{
  "email": null,
  "displayName": "Lan Nguyen"
}
```

Theo JSON Merge Patch, `email` được xóa và `displayName` được cập nhật. Ứng dụng vẫn phải kiểm tra quy tắc domain và khả năng lưu null trong database.

Không phải mọi endpoint `PATCH` đều tự động sử dụng JSON Merge Patch. Nếu dùng `application/json` với DTO tùy chỉnh, hãy tự định nghĩa và tài liệu hóa ý nghĩa của absent, null, array rỗng và giá trị mặc định. Không nên tuyên bố API tuân theo RFC 7396 nếu cách xử lý thực tế khác.

## 8. Cập nhật một phần bằng JPQL hoặc SQL

Với khối lượng lớn, có thể cân nhắc bulk update để không phải tải từng entity. Tuy nhiên, bulk DML bỏ qua entity lifecycle callback và không đồng bộ entity đã nằm trong persistence context.

Một query chỉ cập nhật một trường có thể rõ ràng:

```java
@Modifying
@Query("""
    update Customer c
    set c.email = :email
    where c.id = :id
    """)
int updateEmail(
        @Param("id") Long id,
        @Param("email") String email);
```

Phương thức này đặt email thành giá trị được truyền, kể cả null nếu mapping và database cho phép. Nó không biểu diễn trạng thái absent. Chỉ gọi query này khi request thực sự có trường email.

Nếu cần cập nhật nhiều trường có presence flag, có thể dùng biểu thức `CASE WHEN :fieldProvided THEN :fieldValue ELSE c.field END`, hoặc tạo các query riêng theo tập trường được phép cập nhật. Kiểm tra khả năng suy luận kiểu tham số null với provider và database cụ thể.

Không dùng `COALESCE(:email, c.email)` nếu explicit null phải xóa email. `COALESCE` trả về giá trị đầu tiên không null nên khi tham số null, nó giữ nguyên cột và không thể phân biệt “xóa” với “không gửi”.

Bulk update cần được gọi trong transaction. Cân nhắc `flushAutomatically` và `clearAutomatically` trên `@Modifying` để đồng bộ persistence context khi có entity đã tải. Nếu entity dùng `@Version`, bulk update không tự thực hiện kiểm tra version như cập nhật entity thông thường; phải thiết kế chiến lược version và audit phù hợp.

## 9. @DynamicUpdate không thay thế thiết kế PATCH

Hibernate cung cấp `@DynamicUpdate` để tạo câu UPDATE chỉ chứa các cột được xác định là thay đổi:

```java
@Entity
@DynamicUpdate
public class Customer {
    // fields, mapping and accessors
}
```

Điều này có thể giảm số cột được ghi khi entity được cập nhật. Tuy nhiên:

- `@DynamicUpdate` không phân biệt absent với explicit null.
- Nếu mapping đã gán null vào entity, null vẫn là thay đổi và có thể được ghi xuống database.
- Nó không sửa lỗi dựng entity detached từ DTO thiếu trường rồi merge.
- Nó không thay thế optimistic locking khi nhiều request cập nhật đồng thời.
- Nó có thể làm Hibernate phải tạo nhiều dạng SQL UPDATE hơn, tùy tập trường thay đổi.

Hãy dùng DTO presence và cập nhật entity có chủ đích để bảo đảm semantics. Xem `@DynamicUpdate` như một tùy chọn về câu SQL và hiệu năng, không phải giải pháp cho contract partial update.

## 10. Tránh ghi đè do cập nhật đồng thời

Ngay cả khi mỗi request chỉ sửa một phần, hai request đồng thời vẫn có thể đọc cùng trạng thái cũ và cập nhật cạnh tranh. Để phát hiện stale write, dùng optimistic locking với `@Version`:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;

    @Version
    private Long version;
}
```

Khi entity được cập nhật, JPA dùng version hiện tại trong điều kiện UPDATE và tăng version. Nếu transaction khác đã cập nhật entity trước đó, lần cập nhật sau không còn khớp version và sẽ phát sinh lỗi optimistic locking khi flush/commit.

Client có thể gửi version đã đọc trước đó hoặc dùng HTTP ETag/If-Match để báo rằng patch chỉ áp dụng trên phiên bản tài nguyên mà client đã xem. Nếu version không còn mới, API có thể trả `409 Conflict` hoặc `412 Precondition Failed` tùy contract.

Không tự động retry mọi optimistic lock exception. Chỉ tải lại và áp dụng lại patch nếu thao tác có thể được diễn giải an toàn trên trạng thái mới. Nếu người dùng sửa cùng một trường, cần quyết định rõ ưu tiên dữ liệu hoặc yêu cầu client giải quyết xung đột.

## 11. Bảo vệ trường được phép cập nhật

Không bind request trực tiếp vào entity JPA. Client không nên được quyền thay đổi các trường nội bộ chỉ vì chúng có setter hoặc xuất hiện trong JSON.

Các trường thường cần bảo vệ:

- Primary key và foreign key quan trọng.
- `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`.
- `version`.
- Role, permission, trạng thái phê duyệt hoặc trạng thái thanh toán.
- Trường dùng để liên kết entity với tenant hoặc chủ sở hữu.

Dùng DTO riêng cho từng use case và chỉ áp dụng các trường nằm trong allow-list. Kiểm tra quyền truy cập đối tượng trước khi cập nhật; việc biết ID không đồng nghĩa có quyền sửa bản ghi. Với quan hệ, hãy tải entity liên quan và xác minh quyền/tenant thay vì gán ID do client gửi vào một object mới.

## 12. Kiểm thử partial update

Nên kiểm thử ba trạng thái cho từng trường quan trọng:

1. **Absent:** gửi request không chứa trường và xác nhận giá trị database được giữ nguyên.
2. **Explicit null:** gửi trường với null và xác nhận trường được xóa hoặc request bị validation từ chối theo contract.
3. **Value:** gửi giá trị mới và xác nhận dữ liệu được cập nhật.

Ngoài ra, kiểm thử:

- Trường bắt buộc, chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Boolean false và số 0 để bảo đảm không bị xem là absent.
- Collection rỗng, null và absent.
- Mapping MapStruct với null và presence flag.
- Transaction rollback khi validation hoặc cập nhật thất bại.
- Hai transaction cùng cập nhật một entity có `@Version`.
- Bulk update và trạng thái persistence context sau query.
- Client gửi thêm trường không được phép như role hoặc audit metadata.

Nên đọc lại dữ liệu từ transaction hoặc persistence context mới trong integration test để xác nhận giá trị đã thực sự được lưu.

## 13. Quy trình triển khai an toàn

1. Xác định endpoint là PUT thay thế toàn bộ hay PATCH cập nhật một phần.
2. Định nghĩa rõ absent, null, empty string và empty collection cho từng trường.
3. Dùng request DTO riêng, không nhận trực tiếp entity JPA.
4. Giữ presence của từng trường bằng setter, wrapper ba trạng thái hoặc định dạng patch đã chọn.
5. Tải entity trong service transaction và kiểm tra quyền, trạng thái hiện tại.
6. Chỉ gọi setter cho trường được gửi; validate explicit null theo nghiệp vụ.
7. Dùng `@Version` hoặc cơ chế ETag/If-Match khi cần phát hiện cập nhật đồng thời.
8. Dùng bulk DML chỉ khi có lý do hiệu năng và đã xử lý audit, version cùng persistence context.
9. Kiểm thử absent/null/value và đọc lại từ database.

## Kết luận

Partial update an toàn đòi hỏi phân biệt trường không được gửi, trường được gửi với null và trường có giá trị. Tránh tạo entity thiếu dữ liệu rồi gọi `save()` vì `merge()` có thể sao chép các giá trị null sang entity managed. Cách dễ kiểm soát là tải entity trong transaction, dùng DTO có presence flag và chỉ sửa các trường được phép. Kết hợp validation, `@Version`, allow-list và kiểm thử cả ba trạng thái để tránh mất dữ liệu ngoài ý muốn.