# Kiểu kết quả Optional so với biến thể trả giá trị trực tiếp

Khi dùng fluent query của Spring Data Commons, việc lấy một kết quả có hai quyết định riêng: truy vấn có được phép khớp nhiều bản ghi hay không, và cách biểu diễn trường hợp không có bản ghi. Hai quyết định này không nên bị gộp thành câu hỏi đơn giản là “muốn nhận entity hay `Optional`”.

Trong API đồng bộ `FluentQuery.FetchableFluentQuery<T>`, các cặp `one()`/`oneValue()` và `first()`/`firstValue()` thể hiện rõ sự phân biệt đó. `Optional` làm trạng thái vắng mặt xuất hiện trong kiểu trả về; biến thể trả giá trị trực tiếp dùng `null` khi không có kết quả. Cả hai cách đều phải giữ đúng ngữ nghĩa về số lượng bản ghi mà phương thức yêu cầu.

## 1. Tách hai trục quyết định

### Trục thứ nhất: kỳ vọng về số lượng

- Nhóm `one...`: chấp nhận không có hoặc có đúng một kết quả; có nhiều kết quả là lỗi.
- Nhóm `first...`: chấp nhận nhiều kết quả và chọn phần tử đầu theo thứ tự truy vấn áp dụng.

### Trục thứ hai: cách biểu diễn không có kết quả

- `one()` và `first()`: dùng `Optional.empty()`.
- `oneValue()` và `firstValue()`: trả về `null`.

Có thể hình dung bốn lựa chọn như sau:

| Kỳ vọng về tập kết quả | Vắng mặt được biểu diễn bằng Optional | Vắng mặt được biểu diễn bằng null |
| --- | --- | --- |
| Tối đa một kết quả | `one()` | `oneValue()` |
| Chọn một phần tử đầu từ tập có thể nhiều kết quả | `first()` | `firstValue()` |

Điểm quan trọng là hậu tố `Value` không làm thay đổi quy tắc về số lượng. `oneValue()` vẫn không được tùy ý chọn một bản ghi khi có nhiều kết quả.

## 2. Hợp đồng của bốn phương thức

| Phương thức | Kiểu trả về | Không khớp bản ghi | Khớp một bản ghi | Khớp nhiều bản ghi |
| --- | --- | --- | --- | --- |
| `one()` | `Optional<T>` | Optional rỗng | Optional chứa kết quả | Lỗi kết quả không duy nhất |
| `oneValue()` | `T`, có thể null | `null` | Kết quả trực tiếp | Lỗi kết quả không duy nhất |
| `first()` | `Optional<T>` | Optional rỗng | Optional chứa kết quả | Optional chứa phần tử đầu |
| `firstValue()` | `T`, có thể null | `null` | Kết quả trực tiếp | Phần tử đầu |

Đối với nhóm `one...`, lỗi nhiều kết quả thường được biểu đạt bằng `IncorrectResultSizeDataAccessException` trong abstraction truy cập dữ liệu của Spring. Đây là tình huống khác với việc không có bản ghi.

Một kiểu trả về `Optional<T>` hợp lệ không phải là Java `null`. Phía gọi kiểm tra Optional rỗng hay có giá trị, thay vì kiểm tra chính tham chiếu Optional có null hay không.

Ngược lại, một biến có kiểu khai báo là `Customer` nhận kết quả từ `oneValue()` chưa chắc chứa một đối tượng. Không được suy ra “kiểu trả về không có Optional thì luôn có dữ liệu”.

## 3. Đặt các lựa chọn vào callback `findBy`

Một điểm dùng điển hình là `QueryByExampleExecutor.findBy(...)`:

```java
Optional<Customer> result = repository.findBy(
    example,
    query -> query.one()
);
```

Callback quyết định kiểu kết quả của lời gọi `findBy`. Vì vậy, cùng một `Example<Customer>` có thể được dùng theo hai cách:

```java
Optional<Customer> optionalCustomer = repository.findBy(
    example,
    query -> query.one()
);

Customer customerOrNull = repository.findBy(
    example,
    query -> query.oneValue()
);
```

Hai lời gọi trên là hai lần đọc độc lập nếu cùng được thực thi. Không chạy cả hai chỉ để so sánh cách bọc giá trị trong code sản phẩm.

Query builder phải được sử dụng trong phạm vi callback. Không trả về chính `query` để gọi `one()` hay `first()` sau khi `findBy` đã kết thúc. Giá trị cần đi ra khỏi callback là kết quả của thao tác lấy dữ liệu, chẳng hạn Optional hoặc entity nullable.

Các ví dụ dưới đây dùng QBE để minh họa abstraction chung. Implementation của store phải hỗ trợ QBE, fluent query và các matcher được chọn; chỉ khai báo interface repository không tự bổ sung những khả năng đó cho mọi store.

## 4. Ví dụ tự chứa: tìm khách hàng theo mã hoặc tiền tố tên

### 4.1. Mô hình và repository

Giả sử ứng dụng có mô hình sau:

```java
public class Customer {

    private String id;
    private String customerCode;
    private String displayName;
    private String contactEmail;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getContactEmail() { return contactEmail; }
    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }
}
```

Đây là mô hình Java để giải thích API. Khi tích hợp thực tế, bổ sung mapping và các yêu cầu về entity theo store; Spring Data Commons không tự biến lớp trên thành entity JPA hoặc document đã được cấu hình hoàn chỉnh.

Repository sử dụng các abstraction Commons:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, String>,
                QueryByExampleExecutor<Customer> {
}
```

### 4.2. Tạo hai loại bộ lọc

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.ExampleMatcher.GenericPropertyMatchers;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> byCode(String rawCode) {
        Customer probe = new Customer();
        probe.setCustomerCode(requireText(rawCode, "Mã khách hàng"));

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withIgnorePaths("id", "displayName", "contactEmail")
            .withMatcher("customerCode", GenericPropertyMatchers.exact());

        return Example.of(probe, matcher);
    }

    public static Example<Customer> byNamePrefix(String rawPrefix) {
        Customer probe = new Customer();
        probe.setDisplayName(requireText(rawPrefix, "Tiền tố tên"));

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withIgnorePaths("id", "customerCode", "contactEmail")
            .withMatcher(
                "displayName",
                GenericPropertyMatchers.startsWith().ignoreCase()
            );

        return Example.of(probe, matcher);
    }

    private static String requireText(String value, String label) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(label + " không được trống");
        }
        return value.trim();
    }
}
```

Ứng dụng kỳ vọng mã khách hàng là duy nhất theo quy tắc nghiệp vụ của nó. Factory chỉ tạo điều kiện so khớp; nó không tạo ràng buộc duy nhất trong kho dữ liệu.

Tiền tố tên có thể khớp nhiều khách hàng. Bộ lọc này phù hợp để minh họa việc chọn phần tử đầu, không phù hợp để mặc định kỳ vọng duy nhất.

Trong các đoạn tiếp theo, giả sử `repository` là `CustomerRepository` được ứng dụng cung cấp, còn `Example`, `Optional` và `Sort` đã được import từ các package tương ứng:

```java
import java.util.Optional;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.Sort;
```

## 5. Dùng `one()` khi kỳ vọng tối đa một kết quả

```java
Example<Customer> byCode = CustomerExamples.byCode(" KH-042 ");

Optional<Customer> found = repository.findBy(
    byCode,
    query -> query.one()
);
```

Có ba kết quả cần phân biệt:

1. Không có mã `KH-042`: `found` rỗng.
2. Có đúng một khách hàng khớp: `found` chứa khách hàng đó.
3. Có nhiều khách hàng khớp: truy vấn thất bại vì vi phạm kỳ vọng duy nhất.

Trường hợp thứ ba có thể là dấu hiệu dữ liệu không đáp ứng quy tắc nghiệp vụ hoặc bộ lọc chưa diễn tả đầy đủ khóa tra cứu. Không sửa bằng cách bắt lỗi rồi trả `Optional.empty()`, vì như vậy dữ liệu không nhất quán bị biến thành thông báo “không tìm thấy”.

Cũng không chuyển sang `first()` chỉ để che lỗi trùng dữ liệu nếu yêu cầu nghiệp vụ vẫn là tìm duy nhất theo mã.

### `one()` không có nghĩa bắt buộc tồn tại

Nếu trường hợp sử dụng yêu cầu phải có một khách hàng, hãy nâng yêu cầu đó lên rõ ràng tại service:

```java
Customer required = repository.findBy(
    byCode,
    query -> query.one()
).orElseThrow(() -> new java.util.NoSuchElementException(
    "Không tìm thấy khách hàng theo mã đã yêu cầu"
));
```

Ở đây `one()` bảo vệ kỳ vọng tối đa một kết quả. `orElseThrow(...)` bổ sung quy tắc rằng không có kết quả cũng là lỗi đối với trường hợp sử dụng này.

Exception của ứng dụng có thể được thay cho `NoSuchElementException` để mô tả nghiệp vụ rõ hơn. Việc chuyển lỗi đó thành HTTP status hay thông báo giao diện thuộc hợp đồng của tầng API, không do Optional tự quyết định.

Nếu truy vấn có nhiều kết quả, exception của thao tác truy vấn xảy ra trước khi xử lý nhánh Optional rỗng; `orElseThrow` không biến lỗi trùng dữ liệu thành lỗi không tìm thấy.

## 6. Dùng `first()` khi chủ động chọn phần tử đầu

```java
Example<Customer> byName = CustomerExamples.byNamePrefix("Linh");

Sort stableSort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Optional<Customer> first = repository.findBy(
    byName,
    query -> query.sortBy(stableSort).first()
);
```

Ngữ nghĩa là tìm các khách hàng khớp tiền tố, sắp xếp theo tên rồi ID và chọn phần tử đứng đầu. Nếu nhiều người có cùng tên, ID duy nhất đóng vai trò khóa phụ giúp thứ tự được xác định trên tập dữ liệu đang xét, với giả định store hỗ trợ sắp xếp thuộc tính đó.

Không có sort, “đầu tiên” không đồng nghĩa với:

- Bản ghi được tạo sớm nhất.
- Bản ghi có ID nhỏ nhất.
- Bản ghi giống nhất với chuỗi người dùng nhập.
- Cùng một bản ghi trong mọi lần thực thi.

Nếu nghiệp vụ cần một trong các ý nghĩa trên, phải mô tả thứ tự tương ứng bằng thuộc tính và khả năng mà store hỗ trợ. Sort xác định cũng không tạo snapshot giữa nhiều lần đọc khi dữ liệu thay đổi.

### `firstValue()` có cùng cách chọn, khác cách biểu diễn vắng mặt

```java
Customer firstOrNull = repository.findBy(
    byName,
    query -> query.sortBy(stableSort).firstValue()
);
```

Có nhiều khách hàng khớp vẫn là tình huống hợp lệ. Nếu không có ai khớp, `firstOrNull` là null.

Thêm sort trước `one()` hoặc `oneValue()` không biến chúng thành nhóm `first...`. Tập kết quả sau sắp xếp vẫn có thể có nhiều phần tử và vẫn vi phạm kỳ vọng duy nhất.

## 7. Xử lý Optional theo hợp đồng của phía gọi

### 7.1. Trả Optional khi vắng mặt là trạng thái bình thường

Một service tra cứu có thể giữ nguyên hợp đồng:

```java
public final class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> findByCode(String code) {
        return repository.findBy(
            CustomerExamples.byCode(code),
            query -> query.one()
        );
    }

    public Customer requireByCode(String code) {
        return findByCode(code).orElseThrow(() ->
            new java.util.NoSuchElementException("Không tìm thấy khách hàng")
        );
    }
}
```

Hai phương thức phục vụ hai trường hợp sử dụng khác nhau. `findByCode` để phía gọi quyết định cách xử lý vắng mặt; `requireByCode` thể hiện quy tắc cần có dữ liệu.

Không trả Java null từ một phương thức đã công bố kiểu `Optional<Customer>`. Khi không có dữ liệu, trả Optional rỗng.

### 7.2. Ánh xạ và thực hiện hành động có điều kiện

```java
String label = found
    .map(Customer::getDisplayName)
    .orElse("Chưa có khách hàng");

found.ifPresent(customer -> showCustomer(customer));
```

`showCustomer(...)` là hành động của ứng dụng nhận một `Customer`. `ifPresent(...)` phù hợp khi không có dữ liệu thì không cần thực hiện hành động đó. Nếu không có dữ liệu phải là lỗi, dùng `orElseThrow(...)` thay vì im lặng bỏ qua.

Không dùng `found.get()` chỉ để tránh viết nhánh rỗng. `get()` trên Optional rỗng gây `NoSuchElementException` và thường không mô tả được lý do nghiệp vụ như một exception được tạo tường minh.

### 7.3. `orElse` và `orElseGet` có cách đánh giá khác nhau

```java
Customer result = found.orElse(createFallbackCustomer());
```

Java đánh giá đối số `createFallbackCustomer()` trước khi gọi `orElse`, ngay cả khi `found` đang có giá trị.

Nếu việc tạo giá trị mặc định tốn công hoặc chỉ nên thực hiện khi thiếu dữ liệu, dùng supplier:

```java
Customer result = found.orElseGet(() -> createFallbackCustomer());
```

`createFallbackCustomer()` ở đây chỉ là hàm tạo giá trị dự phòng của ứng dụng. Chỉ dùng fallback nếu nó có ý nghĩa nghiệp vụ; không tạo một entity rỗng để che việc dữ liệu bắt buộc bị thiếu.

Với một chuỗi hằng như `"Chưa có khách hàng"`, `orElse(...)` thường là lựa chọn rõ ràng và đủ dùng.

## 8. Khi nào biến thể trả giá trị trực tiếp hợp lý?

`oneValue()` hoặc `firstValue()` có thể phù hợp khi tích hợp với một hợp đồng đã quy định vắng mặt bằng null, hoặc khi code cần rẽ nhánh tường minh ngay tại chỗ.

```java
Customer customerOrNull = repository.findBy(
    byCode,
    query -> query.oneValue()
);

if (customerOrNull == null) {
    showMissingCustomer();
} else {
    showCustomer(customerOrNull);
}
```

`showMissingCustomer()` và `showCustomer(...)` là các hành động tương ứng của ứng dụng. Nhánh null phải là một phần có chủ ý của hợp đồng.

Nếu có dùng công cụ phân tích nullability, đánh dấu kiểu trả về nullable ở ranh giới ứng dụng theo quy ước của dự án. Không tùy ý sao chép package annotation từ một phiên bản Spring khác; lựa chọn annotation cần phù hợp với thư viện và công cụ đang dùng.

### Không dùng `Optional.of` cho kết quả có thể null

```java
// Sai nếu oneValue() không tìm thấy kết quả.
Optional<Customer> result = Optional.of(
    repository.findBy(byCode, query -> query.oneValue())
);
```

`Optional.of(null)` gây `NullPointerException`. Nếu đang bọc một API nullable tại tầng adapter, `Optional.ofNullable(...)` là cách biểu diễn phù hợp:

```java
Optional<Customer> result = Optional.ofNullable(customerOrNull);
```

Nhưng khi nguồn là fluent query đã có `one()` hoặc `first()`, nên chọn trực tiếp phương thức có kiểu trả về mong muốn. Không cần đi vòng qua giá trị nullable rồi bọc lại chỉ để tạo Optional.

### Không chọn vì giả định giảm số truy vấn

Sự khác nhau giữa `one()` và `oneValue()` trước hết nằm ở hợp đồng kết quả khi vắng mặt; cả hai vẫn giữ kỳ vọng tối đa một bản ghi. Tương tự cho `first()` và `firstValue()`.

Không coi việc bỏ wrapper Optional là một chiến lược giảm số lần truy cập dữ liệu. Cách thực thi và tối ưu truy vấn thuộc repository implementation và store. Khi tối ưu, cần nhìn vào điều kiện, chỉ mục, lượng dữ liệu và hình thức lấy kết quả thực tế.

## 9. Optional rỗng khác với một thuộc tính null

Giả sử kho dữ liệu có khách hàng:

```text
customerCode = KH-042
 displayName = Linh Mai
contactEmail = null
```

Khách hàng tồn tại, chỉ chưa có email liên hệ. Nếu truy vấn theo mã tìm được đúng người, `Optional<Customer>` có giá trị. `contactEmail == null` không làm toàn bộ Optional trở thành rỗng.

Sự khác biệt này cũng xuất hiện với projection:

```java
public interface CustomerContactView {
    String getCustomerCode();
    String getContactEmail();
}
```

Nếu store hỗ trợ projection này:

```java
Optional<CustomerContactView> contact = repository.findBy(
    byCode,
    query -> query.as(CustomerContactView.class).one()
);
```

`contact` có thể chứa một projection hợp lệ mà `getContactEmail()` trả null. `as(...)` đổi kiểu biểu diễn kết quả, không đảm bảo mọi thuộc tính bên trong đều khác null và không đổi quy tắc số lượng của `one()`.

### Cẩn thận khi `map` sang thuộc tính nullable

```java
Optional<String> email = found.map(Customer::getContactEmail);
```

`Optional.map(...)` cho kết quả rỗng nếu hàm ánh xạ trả null. Vì vậy, `email` rỗng có thể xuất phát từ hai tình huống:

1. Không tìm thấy khách hàng.
2. Tìm thấy khách hàng nhưng người đó chưa có email.

Nếu nghiệp vụ cần phân biệt, phải xử lý trạng thái tồn tại của khách hàng trước:

```java
if (!found.isPresent()) {
    showMissingCustomer();
} else {
    Customer customer = found.get();
    String email = customer.getContactEmail();

    if (email == null) {
        showCustomerWithoutEmail(customer);
    } else {
        showCustomerEmail(customer, email);
    }
}
```

Các hàm `show...` minh họa ba nhánh xử lý khác nhau. Việc dùng `get()` ở nhánh đã xác nhận có giá trị không giống với gọi `get()` vô điều kiện. Cũng có thể ánh xạ sang một DTO đầu ra chứa cả định danh và email để giữ thông tin tồn tại của cả kết quả.

## 10. Đừng đổi ngữ nghĩa truy vấn bằng cách xử lý Optional phía sau

Optional mô tả sự hiện diện của một kết quả đã được lấy. Các thao tác trên nó không tự trở thành điều kiện truy vấn trong kho dữ liệu.

Ví dụ:

```java
Optional<Customer> selected = repository.findBy(
    byName,
    query -> query.sortBy(stableSort).first()
).filter(customer -> customer.getContactEmail() != null);
```

Đoạn mã chọn phần tử đầu rồi kiểm tra email của phần tử đó trong Java. Nếu người đầu không có email, `selected` rỗng, dù người thứ hai trong tập kết quả có email.

Nó không có nghĩa “tìm phần tử đầu tiên trong số những người có email”. Để diễn đạt yêu cầu sau, phải dùng điều kiện truy vấn phù hợp với store. Nếu QBE không mô tả được điều kiện cần thiết, chọn cơ chế truy vấn khác thay vì kỳ vọng `Optional.filter(...)` được đẩy xuống kho dữ liệu.

Tương tự, `Optional.map(...)` ánh xạ kết quả phía Java. Nó không có cùng vai trò với `as(...)` trong fluent query khi implementation hỗ trợ projection tại quá trình truy vấn và ánh xạ dữ liệu.

## 11. Những hiểu lầm và cách xử lý

| Hiểu lầm hoặc biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `oneValue()` báo lỗi khi có hai bản ghi | Tưởng Value sẽ tự chọn một bản ghi | Dùng nhóm first chỉ khi nghiệp vụ cho phép chọn đầu; nếu cần duy nhất, sửa dữ liệu hoặc điều kiện |
| `one()` được coi là bắt buộc có dữ liệu | Nhầm “tối đa một” với “đúng một” | Bổ sung `orElseThrow(...)` ở trường hợp sử dụng cần tồn tại |
| Gọi phương thức trên kết quả trực tiếp gây NPE | Quên oneValue hoặc firstValue có thể trả null | Xử lý nhánh null hoặc dùng biến thể Optional |
| Kiểm tra `optional != null` để xác nhận có entity | Nhầm tham chiếu Optional với phần tử bên trong | Dùng thao tác trên Optional theo hợp đồng |
| Có khách hàng nhưng Optional email lại rỗng | `map` sang thuộc tính nullable | Giữ riêng trạng thái tồn tại của khách hàng và trạng thái email |
| `first()` trả bản ghi khác qua nhiều lần đọc | Thiếu thứ tự đủ rõ hoặc dữ liệu thay đổi | Chọn sort phù hợp, có khóa phụ và hiểu tính nhất quán của lần đọc |
| Sort rồi one vẫn báo trùng | Sắp xếp không làm giảm số phần tử | Chọn đúng kỳ vọng số lượng |
| Nhánh fallback vẫn chạy khi có dữ liệu | Dùng `orElse` với lời gọi hàm được đánh giá sớm | Dùng `orElseGet` nếu cần tạo fallback khi vắng mặt |
| Trùng dữ liệu bị báo thành không tìm thấy | Bắt lỗi kích thước rồi trả Optional rỗng | Giữ riêng lỗi dữ liệu không duy nhất với trạng thái không có dữ liệu |
| Optional rỗng sau filter bị hiểu là không có ai phù hợp trong store | Filter chạy sau khi đã lấy một kết quả | Đưa yêu cầu lọc vào cơ chế truy vấn phù hợp |

Ngoài những trạng thái kết quả trên, truy vấn còn có thể thất bại vì lỗi kết nối, timeout, mapping hoặc khả năng store không hỗ trợ. Không bắt mọi exception rồi chuyển thành Optional rỗng; việc không có dữ liệu và việc không đọc được dữ liệu là hai kết quả khác nhau.

## 12. Giới hạn của abstraction chung

Các quy tắc Optional, null và số lượng thuộc hợp đồng của fluent query đồng bộ. Những chi tiết sau vẫn phụ thuộc store và cấu hình:

- Điều kiện so sánh chuỗi, collation và khả năng bỏ qua hoa thường.
- Việc hỗ trợ property path và projection cụ thể.
- Cách triển khai chọn phần tử đầu hoặc phát hiện nhiều kết quả.
- Câu truy vấn, giới hạn truy xuất và chi phí thực thi.
- Vòng đời entity, giao dịch và mức cô lập khi dữ liệu thay đổi đồng thời.

`one()` không tự tạo ràng buộc duy nhất, `first()` không khóa phần tử đã chọn, và việc nhận entity không tự cấp quyền sửa entity đó. Nếu đọc rồi ghi ở một bước tiếp theo, luồng ghi vẫn cần kiểm tra nghiệp vụ, quyền và cơ chế kiểm soát đồng thời phù hợp.

Không áp dụng trực tiếp ngữ nghĩa trả null của các biến thể đồng bộ sang API reactive. API reactive có kiểu kết quả và hợp đồng biểu diễn vắng mặt riêng; cần sử dụng đúng abstraction của nó.

## 13. Bài tập đối chiếu hành vi

Chuẩn bị dữ liệu nhỏ trong store hỗ trợ các chức năng đang dùng và lần lượt đối chiếu:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Không có mã khách hàng cần tìm | one trả Optional rỗng; oneValue trả null |
| Có đúng một mã khớp | Cả hai biến thể cung cấp cùng ý nghĩa bản ghi, khác kiểu biểu diễn |
| Có hai bản ghi cùng khớp bộ lọc duy nhất | Cả one và oneValue đều báo lỗi kỳ vọng số lượng |
| Nhiều người cùng tiền tố tên | first và firstValue chọn theo sort, không báo trùng chỉ vì nhiều người khớp |
| Khách hàng tồn tại nhưng email null | Optional khách hàng có giá trị; Optional email sau map có thể rỗng |
| Fallback là một hàm có bộ đếm số lần gọi | Phân biệt cách đánh giá của orElse và orElseGet |
| Người đầu không có email, người thứ hai có email | Optional.filter sau first không thay thế điều kiện lọc trước khi chọn đầu |
| Có lỗi truy cập kho dữ liệu | Lỗi được giữ riêng với trạng thái không có bản ghi |

Khi chọn kiểu trả về, trước hết xác định truy vấn cần tối đa một kết quả hay chủ động chọn phần tử đầu. Sau đó xác định vắng mặt là trạng thái bình thường, lỗi nghiệp vụ hay giá trị nullable tại một ranh giới tích hợp. Hai quyết định rõ ràng này giúp Optional và các biến thể trả trực tiếp thể hiện đúng hợp đồng của API.