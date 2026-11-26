# Kết quả đơn, Optional và trường hợp nhiều kết quả

## Mục tiêu bài học

Kiểu trả về của một query method là một phần hợp đồng dữ liệu. Khi khai báo `Customer` hoặc `Optional<Customer>`, bạn không chỉ chọn cách trình bày kết quả trong Java: bạn còn thể hiện rằng truy vấn mong đợi tối đa một kết quả phù hợp.

Sau bài học, bạn có thể:

- Phân biệt trường hợp không có, có đúng một và có nhiều kết quả.
- Chọn giữa kết quả đơn, `Optional<T>` và kiểu collection theo nhu cầu nghiệp vụ.
- Giải thích vì sao `Optional` không tự thêm giới hạn một bản ghi và không bảo đảm tính duy nhất trong kho dữ liệu.
- Phân biệt lỗi thiếu dữ liệu với lỗi vi phạm số lượng kết quả.
- Thiết kế truy vấn “mới nhất” hoặc “đầu tiên” có giới hạn và thứ tự rõ ràng.

Các ví dụ sử dụng repository đồng bộ. Kiểu trả về và cơ chế thực thi cụ thể phải được module lưu trữ hỗ trợ; Spring Data Commons cung cấp abstraction chung chứ không thay thế các quy tắc của JPA, MongoDB hoặc store khác.

## 1. Số lượng kết quả là một quyết định nghiệp vụ

Xét domain khách hàng:

```text
Customer
├── id: Long
├── tenantId: String
├── email: String
├── normalizedEmail: String
├── active: boolean
└── createdAt: Instant
```

`normalizedEmail` là giá trị dùng cho tra cứu theo quy tắc chuẩn hóa mà hệ thống đã xác định. Bài học không giả định rằng mọi ứng dụng đều có thể chuẩn hóa email bằng cùng một phép chuyển chữ thường.

Ba yêu cầu sau có hợp đồng khác nhau:

| Yêu cầu | Số kết quả hợp lệ |
| --- | --- |
| Tìm khách hàng theo định danh | Không có hoặc một |
| Tìm khách hàng theo email duy nhất trong tenant | Không có hoặc một, nếu dữ liệu tuân thủ ràng buộc |
| Tìm các khách hàng đang hoạt động trong tenant | Có thể có nhiều |

Nếu một tenant có hàng trăm khách hàng hoạt động, phương thức trả `Optional<Customer>` cho điều kiện `tenantId` và `active` không phù hợp chỉ vì màn hình hiện tại mới có một khách hàng. Cần chọn kiểu trả về theo quy tắc nghiệp vụ và dữ liệu hợp lệ trong tương lai, không theo một bộ dữ liệu mẫu nhỏ.

Một query method nên trả lời rõ hai câu hỏi:

1. Vắng dữ liệu có phải tình huống hợp lệ không?
2. Có nhiều kết quả là tình huống hợp lệ hay dấu hiệu hợp đồng bị vi phạm?

## 2. Bảng hợp đồng 0, 1 và nhiều kết quả

Với các kiểu trả về thông dụng được store hỗ trợ:

| Kiểu trả về | Không có kết quả | Có đúng một | Có nhiều kết quả |
| --- | --- | --- | --- |
| `T` cho kết quả đơn | Thường là `null` khi hợp đồng cho phép; có thể báo lỗi khi bắt buộc khác null | Trả đối tượng | Báo lỗi số lượng kết quả không đúng |
| `Optional<T>` | `Optional.empty()` | `Optional` chứa đối tượng | Báo lỗi số lượng kết quả không đúng |
| `List<T>` | Danh sách rỗng | Danh sách một phần tử | Danh sách nhiều phần tử |

Với query method trả kết quả đơn, lỗi nhiều kết quả thường được biểu đạt qua `org.springframework.dao.IncorrectResultSizeDataAccessException` trong cơ chế Spring Data và dịch ngoại lệ tương ứng. Chi tiết nguyên nhân bên dưới, thông điệp và thời điểm phát hiện còn phụ thuộc module, provider và cách thực thi.

Đối với kết quả đơn bắt buộc khác null có kiểm tra ở runtime, trường hợp không tìm thấy có thể được báo bằng `EmptyResultDataAccessException`. Cần kiểm tra hợp đồng nullability thực tế của dự án trước khi dựa vào hành vi này.

Một lỗi kết nối, một câu truy vấn không hợp lệ hoặc một lỗi chuyển đổi dữ liệu không được biến thành `Optional.empty()` chỉ vì phương thức trả `Optional`. Giá trị rỗng biểu diễn việc không có kết quả, không đại diện cho mọi lỗi truy vấn.

## 3. Trả trực tiếp một đối tượng

Ví dụ chữ ký:

```java
Customer findByTenantIdAndNormalizedEmail(
        String tenantId, String normalizedEmail);
```

Phương thức này biểu đạt truy vấn kết quả đơn. Để sử dụng đúng, người gọi phải biết quy tắc khi không có dữ liệu.

### 3.1. Hợp đồng cho phép null

Trong một repository cho phép trả null, lời gọi có thể cần được xử lý như sau:

```java
Customer customer = repository.findByTenantIdAndNormalizedEmail(
        tenantId, normalizedEmail);

if (customer == null) {
    // Xử lý trường hợp không tìm thấy theo nghiệp vụ.
    return;
}

sendNotification(customer);
```

`sendNotification` đại diện cho xử lý của ứng dụng. Ví dụ chỉ phù hợp khi phương thức thực sự cho phép null.

### 3.2. Hợp đồng bắt buộc khác null

Một dự án có thể dùng annotation hoặc quy ước nullability được phiên bản Spring hỗ trợ để thể hiện rằng kết quả bắt buộc có giá trị. Khi cơ chế kiểm tra runtime tương ứng được áp dụng, việc không tìm thấy có thể tạo ngoại lệ thay vì trả null.

Cần phân biệt:

- Metadata nullability cho công cụ phân tích và trình biên dịch.
- Khả năng kiểm tra hợp đồng ở runtime của cấu hình đang dùng.
- Quy tắc nghiệp vụ về việc có cần một khách hàng hay không.

Chỉ đọc chữ ký `Customer findBy...` mà không biết quy ước nullability của repository thì chưa đủ để kết luận hành vi khi vắng dữ liệu. Với một kết quả có thể vắng mặt hợp lệ, `Optional<Customer>` thường biểu đạt rõ hơn tại điểm gọi.

### 3.3. Tên phương thức không thay thế kiểu trả về

Tiền tố `get`, `read` hoặc `find` của derived query không tự quyết định cách xử lý không có kết quả. Một phương thức tên `getBy...` vẫn có thể trả `Optional`; tên có chữ `find` cũng không tự bảo đảm người gọi luôn nhận một đối tượng.

Các phương thức đã có implementation từ repository cơ sở có hợp đồng riêng. Chẳng hạn, không suy diễn hành vi của API lấy reference JPA chỉ từ những quy tắc của một derived query trả kết quả đơn.

## 4. `Optional<T>` biểu đạt kết quả có thể vắng mặt

Ví dụ repository dùng abstraction Commons:

```java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

interface CustomerRepository extends CrudRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndNormalizedEmail(
            String tenantId, String normalizedEmail);
}
```

Ví dụ giả định domain `Customer` đã được mapping và store hỗ trợ derived query này. `CrudRepository` cũng cung cấp `findById(Long id)` với kiểu trả về `Optional<Customer>`.

Lời gọi:

```java
Optional<Customer> result =
        repository.findByTenantIdAndNormalizedEmail(
                tenantId, normalizedEmail);
```

Có hai trạng thái thành công của lời gọi:

```text
Không có khách hàng phù hợp → Optional.empty()
Có đúng một khách hàng     → Optional chứa khách hàng đó
```

Nếu truy vấn vi phạm hợp đồng một kết quả, lời gọi có thể ném ngoại lệ trước khi bạn có một `Optional` để xử lý.

### 4.1. Chuyển kết quả theo nhu cầu người gọi

```java
Optional<String> email = repository
        .findByTenantIdAndNormalizedEmail(tenantId, normalizedEmail)
        .map(Customer::getEmail);
```

Ví dụ giả định `Customer` có getter tương ứng. `map` cho phép chuyển dữ liệu khi có kết quả và giữ trạng thái rỗng khi không có.

Nếu chỉ cần xử lý trường hợp tìm thấy:

```java
repository.findByTenantIdAndNormalizedEmail(tenantId, normalizedEmail)
        .ifPresent(this::sendNotification);
```

Nếu không tìm thấy là lỗi nghiệp vụ, tầng service có thể chuyển trạng thái rỗng thành ngoại lệ có ý nghĩa.

### 4.2. Ví dụ service yêu cầu phải tìm thấy

```java
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer requireCustomer(
            String tenantId, String normalizedEmail) {

        return repository
                .findByTenantIdAndNormalizedEmail(
                        tenantId, normalizedEmail)
                .orElseThrow(CustomerNotFoundException::new);
    }
}

class CustomerNotFoundException extends RuntimeException {

    CustomerNotFoundException() {
        super("Không tìm thấy khách hàng phù hợp.");
    }
}
```

Service quyết định rằng vắng khách hàng là lỗi cho thao tác này. Cùng repository đó vẫn có thể phục vụ một thao tác khác mà không có khách hàng là tình huống hợp lệ.

`orElseThrow` trong ví dụ chỉ xử lý `Optional` rỗng. Nó không thay thế hoặc che lỗi nhiều kết quả, vì lỗi đó đã xảy ra trong lời gọi repository.

### 4.3. Tránh mở `Optional` mà chưa xử lý trạng thái rỗng

```java
Customer customer = repository
        .findByTenantIdAndNormalizedEmail(tenantId, normalizedEmail)
        .get();
```

Nếu không có kết quả, `get()` ném `NoSuchElementException`. Ngoại lệ này xuất phát từ thao tác mở `Optional`, khác với lỗi sai số lượng kết quả do tầng repository phát hiện.

Hãy chọn một hành vi rõ ràng như `map`, `ifPresent` hoặc `orElseThrow` theo nghiệp vụ. Việc dùng `Optional` chỉ hữu ích khi người gọi thực sự xử lý trạng thái vắng mặt.

## 5. `Optional` không thêm giới hạn và không sửa dữ liệu trùng

Xét dữ liệu:

| id | tenantId | normalizedEmail |
| --- | --- | --- |
| 101 | tenant-a | an@example.com |
| 102 | tenant-a | an@example.com |
| 201 | tenant-b | an@example.com |

Với lời gọi:

```java
repository.findByTenantIdAndNormalizedEmail(
        "tenant-a", "an@example.com");
```

hai khách hàng `101` và `102` cùng phù hợp. `Optional<Customer>` không yêu cầu store tự thêm `LIMIT 1` để chọn một người. Hợp đồng tối đa một kết quả đã bị vi phạm.

Khách hàng `201` thuộc tenant khác nên không phải nguồn gây nhiều kết quả cho truy vấn có đủ điều kiện tenant. Tuy vậy, nếu bỏ `tenantId` khỏi điều kiện, cùng email ở nhiều tenant có thể trở thành nguyên nhân gây lỗi dù dữ liệu hoàn toàn hợp lệ theo quy tắc của ứng dụng.

### 5.1. Những nguyên nhân cần phân biệt

- Dữ liệu trùng theo một quy tắc vốn phải duy nhất.
- Điều kiện truy vấn thiếu một phần của khóa nghiệp vụ, chẳng hạn tenant.
- Dùng kết quả đơn cho một yêu cầu vốn cho phép nhiều kết quả.
- Một phép join hoặc projection làm hình dạng kết quả khác với dự đoán.
- Quy tắc chuẩn hóa và so sánh thực tế không trùng với quy tắc duy nhất mong muốn.

Không nên tự động coi mọi lỗi nhiều kết quả là dữ liệu bẩn. Có thể dữ liệu đúng nhưng query method đã đặt hợp đồng quá hẹp.

### 5.2. Không đổi lỗi nhiều kết quả thành “không tìm thấy”

Nếu bắt `IncorrectResultSizeDataAccessException` rồi trả `Optional.empty()`, người gọi không còn phân biệt được hai tình huống:

```text
Không có khách hàng
Có nhiều khách hàng nhưng hệ thống không xác định được khách hàng nào
```

Hai tình huống có cách xử lý khác nhau. Trường hợp thứ hai cần được chẩn đoán và sửa ở điều kiện truy vấn, hợp đồng hoặc dữ liệu. Không nên âm thầm chuyển nó thành nhánh “tạo khách hàng mới”.

Bọc một phương thức trả `Customer` bằng `Optional.ofNullable(...)` cũng chỉ xử lý giá trị null sau lời gọi. Nó không chữa được lỗi nhiều kết quả mà repository đã ném trước đó.

## 6. Tính duy nhất phải được bảo vệ ở đúng nơi

Chữ ký `Optional<Customer>` thể hiện kỳ vọng của người đọc và cơ chế truy vấn. Nó không tạo unique constraint hay unique index trong kho dữ liệu.

Nếu quy tắc là “một email chuẩn hóa chỉ thuộc một khách hàng trong cùng tenant”, các phần cần thống nhất là:

1. Điều kiện tra cứu chứa cả `tenantId` và `normalizedEmail`.
2. Tất cả luồng ghi tạo ra cùng một dạng chuẩn hóa theo quy tắc nghiệp vụ.
3. Kho dữ liệu có ràng buộc duy nhất trên đúng cặp giá trị đó.
4. Chính sách đối với null, dữ liệu thiếu và cập nhật giá trị được xác định rõ.

### 6.1. Ví dụ ràng buộc quan hệ

Với một bảng minh họa có mapping cột tương ứng:

```sql
CREATE UNIQUE INDEX ux_customer_tenant_email
    ON customer (tenant_id, normalized_email);
```

Đây là ví dụ DDL cần điều chỉnh theo database, schema và quy trình migration thực tế. Các cột bắt buộc có giá trị cần ràng buộc không null phù hợp; unique index không tự thiết lập toàn bộ quy tắc đó.

### 6.2. Ví dụ chỉ mục MongoDB

Với collection minh họa dùng các tên trường tương ứng:

```javascript
db.customer.createIndex(
    { tenantId: 1, normalizedEmail: 1 },
    { unique: true }
);
```

Đây là một lựa chọn độc lập với ví dụ SQL. Cần xác định chính sách dữ liệu thiếu/null và bảo đảm index thật sự được tạo trong môi trường triển khai. Mapping hoặc annotation trong mã nguồn không thay thế việc xác minh trạng thái schema/index thực tế.

Ngữ nghĩa so sánh chuỗi, collation và cách lưu giá trị phải phù hợp với query method. Nếu ràng buộc duy nhất bảo vệ một giá trị khác với giá trị dùng để tìm, hệ thống vẫn có thể phát sinh hành vi ngoài mong muốn.

### 6.3. Kiểm tra trước rồi ghi vẫn có cạnh tranh

Luồng sau không tự bảo đảm tính duy nhất:

```text
Yêu cầu A: kiểm tra chưa có email
Yêu cầu B: kiểm tra chưa có email
Yêu cầu A: ghi khách hàng
Yêu cầu B: ghi khách hàng
```

Một `existsBy...` hoặc `findBy...` trước `save` có thể hỗ trợ trải nghiệm và thông báo nghiệp vụ, nhưng hai yêu cầu đồng thời vẫn có thể cùng vượt qua bước kiểm tra. Cần cơ chế bảo vệ ở kho lưu trữ và xử lý lỗi ghi phù hợp.

Chỉ thêm transaction thông thường cũng không tự thay thế ràng buộc duy nhất. Thời điểm phát hiện vi phạm có thể ở lúc ghi, flush hoặc commit tùy công nghệ truy cập dữ liệu.

## 7. Có nhiều kết quả hợp lệ thì dùng kiểu nhiều kết quả

Nếu yêu cầu là “lấy các khách hàng hoạt động của tenant”, chữ ký phù hợp có thể là:

```java
import java.util.List;

List<Customer> findByTenantIdAndActiveTrue(String tenantId);
```

Với repository trả collection theo hợp đồng Spring Data thông dụng, không có dữ liệu được biểu diễn bằng collection rỗng. Không cần thêm `Optional<List<Customer>>` chỉ để thể hiện trường hợp danh sách không có phần tử.

```java
List<Customer> customers =
        repository.findByTenantIdAndActiveTrue(tenantId);

if (customers.isEmpty()) {
    // Không có khách hàng hoạt động phù hợp.
}
```

Với tập kết quả lớn, có thể chọn `Page`, `Slice`, `Stream` hoặc cơ chế khác khi store hỗ trợ. Chúng có hợp đồng về metadata và tài nguyên riêng. Đổi từ `Optional` sang một kiểu nhiều kết quả phải xuất phát từ yêu cầu nghiệp vụ, không chỉ để làm biến mất một ngoại lệ.

### 7.1. Chỉ cần tồn tại hoặc số lượng

```java
boolean existsByTenantIdAndNormalizedEmail(
        String tenantId, String normalizedEmail);

long countByTenantIdAndActiveTrue(String tenantId);
```

Khi store hỗ trợ, các chữ ký này diễn đạt trực tiếp nhu cầu kiểm tra tồn tại hoặc đếm. Nếu chỉ cần câu trả lời có/không, không nhất thiết phải lấy toàn bộ entity vào một `Optional` rồi chỉ gọi `isPresent()`.

Tuy vậy, `existsBy...` không xác nhận rằng số lượng chỉ là một; nó có thể trả true ngay cả khi có dữ liệu trùng. Không dùng phép kiểm tra tồn tại để thay thế việc bảo vệ tính duy nhất.

## 8. “Tối đa một kết quả” khác với “chọn một từ nhiều kết quả”

Hai yêu cầu cần tách biệt:

| Yêu cầu | Cách hiểu |
| --- | --- |
| Tìm theo khóa duy nhất | Nhiều kết quả là lỗi |
| Lấy khách hàng mới nhất của tenant | Nhiều khách hàng là hợp lệ; truy vấn chọn một theo thứ tự |

Với yêu cầu thứ hai, có thể khai báo giới hạn rõ khi store hỗ trợ:

```java
Optional<Customer> findFirstByTenantIdOrderByCreatedAtDescIdDesc(
        String tenantId);
```

Trong tên này:

- `First` giới hạn kết quả cần lấy.
- `TenantId` xác định phạm vi.
- `CreatedAtDesc` ưu tiên khách hàng có thời điểm tạo mới hơn.
- `IdDesc` là tiêu chí phụ khi nhiều khách hàng có cùng thời điểm tạo.
- `Optional` biểu diễn trường hợp tenant chưa có khách hàng.

`Top` cũng là keyword giới hạn thường gặp trong các store hỗ trợ. Cần kiểm tra khả năng của module và kiểu truy vấn đang dùng.

### 8.1. Thứ tự phải phản ánh ý nghĩa nghiệp vụ

Một phương thức `findFirstByTenantId(...)` không có thứ tự rõ không bảo đảm “mới nhất”. Backend có thể chọn kết quả theo một thứ tự không được hợp đồng xác định.

Khóa phụ giúp phân biệt các bản ghi trùng thời điểm. Nó không ngăn kết quả thay đổi giữa hai lần gọi nếu dữ liệu được thêm hoặc cập nhật. Nếu cần tính nhất quán đặc biệt, phải thiết kế cùng transaction và khả năng của backend.

### 8.2. Không dùng giới hạn để che lỗi khóa duy nhất

Thay:

```java
Optional<Customer> findByTenantIdAndNormalizedEmail(
        String tenantId, String normalizedEmail);
```

bằng một truy vấn `findFirstBy...` có thể khiến ứng dụng ngừng báo nhiều kết quả, nhưng dữ liệu trùng vẫn tồn tại. Việc chọn tùy một khách hàng theo email có thể dẫn đến thao tác trên sai tài khoản.

Chỉ dùng giới hạn khi nghiệp vụ thật sự cho phép nhiều ứng viên và có quy tắc chọn. Nếu email phải duy nhất, cần sửa nguyên nhân trùng hoặc điều kiện truy vấn.

## 9. Phân biệt kết quả truy vấn với số dòng vật lý

Một phép join có thể tạo nhiều dòng SQL cho cùng một entity gốc. Ngược lại, một projection có thể tạo những kết quả khác nhau dù cùng tham chiếu một khách hàng.

Vì vậy, cần phân tích:

- Truy vấn đang trả entity gốc, scalar hay projection?
- Provider có khử trùng entity trong dạng truy vấn đó không?
- Phép join có làm tăng số kết quả logic không?
- `distinct` được áp dụng trên điều gì?

Không thể chỉ thấy nhiều dòng ở SQL log rồi kết luận chắc chắn repository sẽ trả nhiều entity khác nhau. Cũng không nên thêm `Distinct` một cách máy móc để sửa mọi lỗi kết quả đơn.

Nếu có hai khách hàng với hai định danh khác nhau cùng dùng email trong tenant, chúng vẫn là hai entity khác nhau. Khử trùng các dòng join không tạo ra ràng buộc duy nhất về email.

### Projection vẫn có hợp đồng số lượng

```java
interface CustomerSummary {
    String getEmail();
}

Optional<CustomerSummary> findSummaryByTenantIdAndNormalizedEmail(
        String tenantId, String normalizedEmail);
```

Ví dụ giả định store hỗ trợ interface projection này. Trả một projection thay vì entity không tự chuyển truy vấn nhiều kết quả thành một kết quả. Cần kiểm tra số kết quả theo chính hình dạng truy vấn và kiểu trả về đó.

## 10. Phân loại lỗi theo ý nghĩa

| Biểu hiện | Ý nghĩa cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Nhận `Optional.empty()` | Không có kết quả phù hợp | Xử lý nhánh vắng mặt theo nghiệp vụ |
| Kết quả đơn trả null | Hợp đồng cho phép vắng kết quả dưới dạng null | Xác nhận nullability và xử lý trước khi sử dụng |
| `EmptyResultDataAccessException` trong hợp đồng bắt buộc có giá trị | Không có dữ liệu nhưng phương thức yêu cầu kết quả | Kiểm tra kỳ vọng và điều kiện truy vấn |
| `IncorrectResultSizeDataAccessException` | Nhiều kết quả hơn hợp đồng cho phép | Kiểm tra cardinality, bộ lọc, join và dữ liệu |
| `NoSuchElementException` từ `Optional.get()` | Người gọi mở một `Optional` rỗng | Chọn hành vi xử lý vắng dữ liệu rõ ràng |
| Lỗi ghi do vi phạm ràng buộc duy nhất | Kho lưu trữ từ chối dữ liệu trùng | Xử lý xung đột ghi và kiểm tra quy tắc khóa |
| Lỗi kết nối hoặc cú pháp | Truy vấn chưa thực thi thành công | Xử lý lỗi hạ tầng hoặc sửa truy vấn, không coi là không có dữ liệu |

Đừng gộp tất cả các lỗi này thành một thông báo “không tìm thấy”. Phân loại đúng giúp tránh tạo dữ liệu mới khi thực tế đã có dữ liệu trùng hoặc khi hệ thống đang không truy cập được backend.

Khi chẩn đoán, đối chiếu điều kiện với đúng phạm vi tenant và cùng quy tắc chuẩn hóa. Việc log giá trị cần tuân theo chính sách dữ liệu của ứng dụng; có thể dùng dữ liệu thử để tái hiện thay vì đưa thông tin khách hàng thật vào log.

## 11. Chọn chữ ký theo yêu cầu thực tế

| Yêu cầu | Kiểu hoặc phương thức có thể chọn | Điều phải bảo đảm |
| --- | --- | --- |
| Tìm một khách hàng có thể chưa tồn tại | `Optional<Customer>` | Điều kiện kỳ vọng tối đa một kết quả |
| Service bắt buộc có khách hàng | Repository trả `Optional`, service dùng `orElseThrow` | Ngoại lệ nghiệp vụ rõ và dữ liệu không trùng |
| API cũ cho phép null | `Customer` theo hợp đồng nullable | Người gọi biết và xử lý null |
| Lấy mọi khách hàng phù hợp | `List<Customer>` hoặc kiểu nhiều kết quả phù hợp | Chấp nhận nhiều kết quả và kiểm soát kích thước |
| Lấy khách hàng mới nhất | Truy vấn giới hạn một, có thứ tự, trả `Optional` | Thứ tự có ý nghĩa và store hỗ trợ |
| Chỉ cần biết có dữ liệu không | `existsBy...` | Không nhầm tồn tại với duy nhất |
| Chỉ cần số lượng | `countBy...` | Điều kiện đếm đúng phạm vi |

Abstraction của Commons giúp diễn đạt các hợp đồng này nhất quán. Store vẫn quyết định kiểu nào được hỗ trợ, cách triển khai truy vấn và cơ chế bảo vệ dữ liệu phù hợp.

Auditing có thể cung cấp `createdAt` cho truy vấn mới nhất, nhưng trường đó phải được mapping và điền dữ liệu đúng. Auditing không tự sắp xếp, không tạo khóa phụ và không bảo đảm email duy nhất.

## 12. Các ca dữ liệu nên dùng để xác minh

Một bộ ca có ý nghĩa cho truy vấn kết quả đơn gồm:

1. Không có bản ghi phù hợp.
2. Có đúng một bản ghi phù hợp.
3. Có hai bản ghi phù hợp khi ràng buộc thực tế cho phép tạo tình huống đó.
4. Có cùng email ở hai tenant, mỗi tenant chỉ có một khách hàng.
5. Có các giá trị khác nhau theo quy tắc hoa thường hoặc chuẩn hóa mà nghiệp vụ quan tâm.
6. Có hai khách hàng cùng `createdAt` cho truy vấn mới nhất.

Nếu backend đã bảo vệ khóa duy nhất, ca ghi hai bản ghi trùng nên xác minh rằng lần ghi vi phạm bị từ chối theo cơ chế của store. Không cần vô hiệu hóa ràng buộc của môi trường thật để tạo ca kiểm tra query method.

Với truy vấn theo khóa tự nhiên, hãy kiểm tra cả ràng buộc schema/index lẫn hành vi đọc. Với truy vấn lấy phần tử đầu tiên, hãy kiểm tra thứ tự và tình huống không có dữ liệu. Hai loại truy vấn có tiêu chí thành công khác nhau.

## 13. Bài tập tự kiểm tra

### Bài 1: `Optional` có giới hạn truy vấn không?

```java
Optional<Customer> findByTenantId(String tenantId);
```

Tenant có ba khách hàng. Phương thức có tự chọn một khách hàng để đặt vào `Optional` không?

**Gợi ý đáp án:** Không. Chữ ký đang yêu cầu kết quả đơn trong khi điều kiện cho phép nhiều kết quả. Cần kiểu nhiều kết quả hoặc một yêu cầu chọn một phần tử có giới hạn và thứ tự rõ ràng.

### Bài 2: Vắng dữ liệu và dữ liệu trùng

Một service dùng `orElseThrow(CustomerNotFoundException::new)` sau lời gọi repository trả `Optional`. Nếu repository tìm thấy hai khách hàng, service có chuyển lỗi đó thành `CustomerNotFoundException` không?

**Gợi ý đáp án:** Không. `orElseThrow` xử lý `Optional` rỗng. Lỗi số lượng xảy ra trong quá trình thực hiện query method và cần được phân biệt với không tìm thấy.

### Bài 3: Chọn khóa đúng phạm vi

Nghiệp vụ cho phép cùng email ở các tenant khác nhau nhưng cấm trùng trong một tenant. Truy vấn theo email toàn hệ thống trả `Optional<Customer>` có phù hợp không?

**Gợi ý đáp án:** Không đủ điều kiện để bảo đảm một kết quả. Cần đưa tenant vào điều kiện và bảo vệ tính duy nhất theo cặp tenant cùng email chuẩn hóa.

### Bài 4: Lấy mới nhất

Có nhiều khách hàng trong tenant và yêu cầu chỉ lấy khách hàng mới nhất. Nên giữ kết quả đơn không giới hạn rồi hy vọng provider chọn bản ghi mới nhất, hay khai báo `First`/`Top` với `OrderBy`?

**Gợi ý đáp án:** Dùng giới hạn và thứ tự tường minh khi store hỗ trợ. Thêm tiêu chí phụ nếu thời điểm tạo có thể trùng. `Optional` xử lý trường hợp tenant chưa có khách hàng.

### Bài 5: Phòng ghi trùng

Hai request cùng kiểm tra chưa có email rồi cùng ghi. Chữ ký repository trả `Optional` và bước kiểm tra trước có ngăn được trùng không?

**Gợi ý đáp án:** Không. Cần ràng buộc duy nhất phù hợp ở kho dữ liệu và xử lý xung đột ghi. Kỳ vọng của kiểu trả về không thay thế cơ chế bảo vệ dữ liệu.

### Bài 6: Chuyển sang danh sách

Một phương thức thường ném lỗi nhiều kết quả. Có nên luôn đổi nó sang `List<Customer>` không?

**Gợi ý đáp án:** Chỉ khi nghiệp vụ thật sự cho phép nhiều kết quả. Nếu điều kiện phải duy nhất, cần sửa dữ liệu, bộ lọc hoặc ràng buộc. Đổi kiểu trả về đơn thuần có thể che mất vi phạm quan trọng.

## Những điểm cần nhớ

- `T` và `Optional<T>` cho query method kết quả đơn đều thể hiện kỳ vọng tối đa một kết quả.
- `Optional.empty()` biểu đạt không có kết quả, còn nhiều kết quả là một tình huống khác cần được phát hiện.
- `Optional` không tự thêm giới hạn, không tạo unique index và không xử lý thay các lỗi hạ tầng.
- Dùng kiểu nhiều kết quả khi nhiều đối tượng là hợp lệ; dùng giới hạn kèm thứ tự khi nghiệp vụ muốn chọn một từ nhiều ứng viên.
- Tính duy nhất phải thống nhất giữa điều kiện truy vấn, phạm vi tenant, quy tắc chuẩn hóa và ràng buộc của đúng store.
