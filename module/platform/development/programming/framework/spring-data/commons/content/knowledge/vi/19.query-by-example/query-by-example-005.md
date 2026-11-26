# Khớp chuỗi, ignoreCase và tùy chỉnh từng thuộc tính

Trong Query by Example (QBE), một chuỗi đặt vào đối tượng mẫu chưa đủ để diễn đạt chính xác yêu cầu tìm kiếm. Giá trị `"An"` có thể có nghĩa là bằng toàn bộ tên, bắt đầu bằng “An”, kết thúc bằng “An” hoặc chứa “An” ở bất kỳ vị trí nào. Việc có phân biệt chữ hoa và chữ thường cũng là một lựa chọn riêng.

Bài học thuộc chương **Query by Example** của **SPRING_DATA_COMMONS**, tập trung vào cách dùng `ExampleMatcher` để mô tả những lựa chọn đó. Đây là abstraction dùng chung của Spring Data: matcher diễn đạt ý định, còn module Spring Data của từng kho dữ liệu chuyển ý định thành truy vấn cụ thể. Vì vậy, hiểu API phải đi cùng với hiểu giới hạn của store đang sử dụng.

Sau bài học, bạn có thể:

- Chọn kiểu khớp chuỗi phù hợp với yêu cầu nghiệp vụ.
- Thiết lập `ignoreCase` ở mức chung hoặc cho từng thuộc tính.
- Kết hợp nhiều quy tắc trong cùng một `Example`, kể cả đường dẫn thuộc tính lồng nhau.
- Phân biệt cấu hình matcher với chuẩn hóa dữ liệu và với quy tắc so sánh của kho dữ liệu.
- Tránh các điều kiện ngoài ý muốn từ `null`, chuỗi rỗng và kiểu nguyên thủy.

## 1. Tách đối tượng mẫu khỏi quy tắc khớp

Một truy vấn QBE có ba thành phần:

| Thành phần | Vai trò |
|---|---|
| Probe | Đối tượng mẫu chứa giá trị muốn tìm |
| `ExampleMatcher` | Quy tắc chọn thuộc tính, khớp chuỗi, phân biệt hoa/thường và xử lý giá trị |
| `Example<T>` | Kết hợp probe với matcher để chuyển cho repository |

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setDisplayName("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers.startsWith().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
~~~

Ý định của ví dụ là: chọn khách hàng có `displayName` bắt đầu bằng `"An"`, bỏ qua khác biệt hoa/thường theo khả năng so sánh của store.

Các đoạn mã trong bài giả định `Customer` là kiểu miền được module Spring Data đang dùng ánh xạ hợp lệ. Mô hình có các thuộc tính sau và có getter/setter thông thường:

| Thuộc tính Java | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | `Long` | Định danh |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Địa chỉ email |
| `accountCode` | `String` | Mã tài khoản |
| `active` | `Boolean` | Trạng thái hoạt động |
| `address` | `Address` | Đối tượng địa chỉ có thuộc tính `city` kiểu `String` |

Cách ánh xạ `Address` phụ thuộc store; chẳng hạn có thể là giá trị nhúng trong JPA hoặc tài liệu nhúng trong MongoDB. Các ví dụ đường dẫn `address.city` giả định store hỗ trợ truy cập thuộc tính đó bằng QBE.

Giá trị chưa dùng trong probe được để `null`. Với chính sách mặc định bỏ qua `null`, chúng không sinh điều kiện tìm kiếm.

## 2. Các kiểu khớp chuỗi

`ExampleMatcher.StringMatcher` mô tả kiểu khớp cho thuộc tính chuỗi. Các phương thức tiện ích của `GenericPropertyMatchers` giúp cấu hình trực tiếp từng thuộc tính.

| Ý định | `StringMatcher` | Cấu hình theo thuộc tính |
|---|---|---|
| Dùng hành vi mặc định của store | `DEFAULT` | Bỏ cấu hình kiểu khớp hoặc dùng `storeDefaultMatching()` |
| Bằng toàn bộ chuỗi | `EXACT` | `exact()` |
| Bắt đầu bằng chuỗi mẫu | `STARTING` | `startsWith()` |
| Kết thúc bằng chuỗi mẫu | `ENDING` | `endsWith()` |
| Chứa chuỗi mẫu | `CONTAINING` | `contains()` |
| Khớp biểu thức chính quy | `REGEX` | `regex()`, nếu store hỗ trợ |

Ví dụ, với probe `displayName = "An"` và xét phân biệt hoa/thường:

| Giá trị đang lưu | `EXACT` | `STARTING` | `ENDING` | `CONTAINING` |
|---|---|---|---|---|
| `An` | Có | Có | Có | Có |
| `Anh` | Không | Có | Không | Có |
| `Binh An` | Không | Không | Có | Có |
| `Lan Anh` | Không | Không | Không | Có |
| `an` | Không | Không | Không | Không |

Bảng diễn tả ngữ nghĩa mong muốn; kết quả thực tế còn chịu ảnh hưởng của phép so sánh chuỗi tại store. Nếu bật `ignoreCase`, hàng `an` được kỳ vọng khớp với mẫu `An` khi store thực hiện được quy tắc đó.

### 2.1. Khớp chính xác không đồng nghĩa phân biệt hoa/thường

Hai trục cấu hình độc lập là:

1. **Phạm vi khớp:** toàn bộ chuỗi, đầu chuỗi, cuối chuỗi hoặc chuỗi con.
2. **Hoa/thường:** có yêu cầu bỏ qua khác biệt chữ hoa và chữ thường hay không.

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase()
    );
~~~

Cấu hình này vẫn yêu cầu toàn bộ giá trị email khớp. Nó chỉ thêm yêu cầu bỏ qua hoa/thường. Ví dụ, theo chính sách so sánh email mà ứng dụng lựa chọn, `"An@Example.com"` có thể khớp `"an@example.com"`; `"other-an@example.com"` không trở thành kết quả chỉ vì có chứa một phần giống nhau.

Không suy ra từ ví dụ rằng mọi hệ thống đều phải xem toàn bộ địa chỉ email là không phân biệt hoa/thường. Ứng dụng cần quy định chính sách đó trước khi chọn matcher.

### 2.2. Không thêm ký tự đại diện SQL vào probe

~~~java
probe.setDisplayName("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers.contains()
    );
~~~

Hãy truyền `"An"` và dùng `contains()` để diễn đạt “chứa An”. Không tự đổi probe thành `"%An%"` theo thói quen viết SQL `LIKE`.

Probe không phải câu truy vấn SQL. Cách biểu diễn và xử lý ký tự đặc biệt phụ thuộc module Spring Data. Tương tự, `contains()` không biến chuỗi người dùng thành biểu thức chính quy; muốn dùng regex phải chọn kiểu khớp tương ứng và xác nhận store hỗ trợ.

## 3. Cấu hình ở mức chung

Dùng cấu hình chung khi phần lớn thuộc tính chuỗi có cùng chính sách:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase();
~~~

Nếu probe có:

~~~java
probe.setDisplayName("an");
probe.setEmail("example.com");
~~~

thì ý định tìm kiếm là:

~~~text
displayName chứa "an", bỏ qua hoa/thường
AND
email chứa "example.com", bỏ qua hoa/thường
~~~

Chính sách chung này tiện cho một màn hình tìm kiếm văn bản. Tuy nhiên, nó thường quá rộng với mã định danh hoặc email cần so sánh toàn bộ.

`withIgnoreCase()` áp dụng chính sách bỏ qua hoa/thường chung cho các thuộc tính chuỗi được đưa vào ví dụ. Nó không:

- Chuyển các trường số thành chuỗi để so sánh.
- Bỏ dấu tiếng Việt.
- Xóa khoảng trắng đầu/cuối.
- Thay đổi dữ liệu đã lưu.
- Đặt quy tắc so sánh cho mọi truy vấn khác của repository.

## 4. Tùy chỉnh từng thuộc tính và thứ tự ưu tiên

Cấu hình theo thuộc tính ghi đè lựa chọn chung đối với phần mà nó thiết lập. Những lựa chọn chưa được đặt riêng tiếp tục lấy từ cấu hình chung hoặc mặc định.

~~~java
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.exact;
import static org.springframework.data.domain.ExampleMatcher
    .GenericPropertyMatchers.startsWith;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase()
    .withMatcher("displayName", startsWith())
    .withMatcher("email", exact())
    .withMatcher("accountCode", exact().caseSensitive());
~~~

Có thể đọc cấu hình trên thành bảng:

| Thuộc tính | Kiểu khớp hiệu lực | Hoa/thường | Nguồn cấu hình |
|---|---|---|---|
| `displayName` | Bắt đầu bằng | Bỏ qua | Kiểu khớp riêng, hoa/thường kế thừa cấu hình chung |
| `email` | Chính xác | Bỏ qua | Kiểu khớp riêng, hoa/thường kế thừa cấu hình chung |
| `accountCode` | Chính xác | Có yêu cầu phân biệt | Cả hai được đặt riêng |
| Thuộc tính chuỗi khác có giá trị trong probe | Chứa | Bỏ qua | Cấu hình chung |

Một cách viết tương đương dùng lambda:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase()
    .withMatcher("displayName", property -> property.startsWith())
    .withMatcher("email", property -> property.exact())
    .withMatcher(
        "accountCode",
        property -> property.exact().caseSensitive()
    );
~~~

`caseSensitive()` diễn đạt lựa chọn ở mức matcher. Với kho dữ liệu sử dụng collation không phân biệt hoa/thường, phép bằng mà store tạo ra có thể vẫn không phân biệt hoa/thường. Cần xác nhận khả năng thực thi của store nếu mã tài khoản bắt buộc phân biệt `"ABC"` và `"abc"`.

### 4.1. Chỉ bỏ qua hoa/thường cho một số thuộc tính

Nếu chỉ tên và thành phố cần bỏ qua hoa/thường, có thể chỉ rõ các đường dẫn:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase("displayName", "address.city")
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers.contains()
    )
    .withMatcher(
        "address.city",
        ExampleMatcher.GenericPropertyMatchers.exact()
    );
~~~

`withIgnoreCase("displayName", "address.city")` thiết lập bỏ qua hoa/thường cho đúng các thuộc tính này. Nó không tương đương với `withIgnoreCase()` rồi tự động loại trừ mọi trường còn lại.

Các tên đường dẫn phải là tên thuộc tính Java của mô hình, chẳng hạn `displayName`. Không thay chúng bằng tên cột SQL như `display_name` hay tên nhãn trên giao diện.

### 4.2. Đặt cùng một quy tắc trong một lần cấu hình

Nên nhóm các lựa chọn của một thuộc tính trong một lệnh để dễ đọc:

~~~java
.withMatcher("displayName", property ->
    property.startsWith().ignoreCase())
~~~

Khi matcher dài hơn, cách này giúp người đọc nhận biết đầy đủ chính sách của trường mà không phải tìm nhiều lệnh cấu hình cùng đường dẫn.

## 5. ExampleMatcher là bất biến

Các phương thức `with...` trả về matcher mới. Chúng không sửa matcher hiện tại tại chỗ.

Ví dụ sai về ý định:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher.withIgnoreCase();

Example<Customer> example = Example.of(probe, matcher);
~~~

Kết quả của `withIgnoreCase()` đã bị bỏ đi; `example` vẫn nhận matcher ban đầu.

Cách đúng:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase();
~~~

Hoặc giữ lại kết quả khi bổ sung cấu hình:

~~~java
matcher = matcher.withMatcher(
    "displayName",
    ExampleMatcher.GenericPropertyMatchers.contains()
);
~~~

Tính bất biến cho phép tái sử dụng một cấu hình nền để tạo nhiều matcher. Tuy nhiên, probe là đối tượng miền thông thường: đừng coi `Example.of(probe, matcher)` là thao tác sao chép sâu probe. Nên tạo probe riêng cho mỗi lần tìm kiếm và tránh sửa nó sau khi đã tạo `Example`.

## 6. Ví dụ kết hợp trong một màn hình tìm kiếm khách hàng

Giả sử màn hình nhận các bộ lọc sau:

| Đầu vào | Chính sách |
|---|---|
| Tên | Bắt đầu bằng, bỏ qua hoa/thường |
| Email | Toàn bộ giá trị, bỏ qua hoa/thường theo quy ước ứng dụng |
| Mã tài khoản | Toàn bộ giá trị, yêu cầu phân biệt hoa/thường |
| Thành phố | Toàn bộ giá trị, bỏ qua hoa/thường |
| Trạng thái hoạt động | Bằng giá trị `Boolean`, bỏ qua nếu không được chọn |

Ứng dụng chuẩn hóa chuỗi đầu vào bằng cách bỏ khoảng trắng đầu/cuối và biến chuỗi rỗng thành `null`. Đây là quyết định của màn hình tìm kiếm, không phải hành vi tự động của QBE.

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> forSearch(
            String displayName,
            String email,
            String accountCode,
            String city,
            Boolean active) {

        Customer probe = new Customer();
        probe.setDisplayName(trimToNull(displayName));
        probe.setEmail(trimToNull(email));
        probe.setAccountCode(trimToNull(accountCode));
        probe.setActive(active);

        String normalizedCity = trimToNull(city);
        if (normalizedCity != null) {
            Address address = new Address();
            address.setCity(normalizedCity);
            probe.setAddress(address);
        }

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withIgnorePaths("id")
            .withMatcher(
                "displayName",
                ExampleMatcher.GenericPropertyMatchers
                    .startsWith().ignoreCase()
            )
            .withMatcher(
                "email",
                ExampleMatcher.GenericPropertyMatchers
                    .exact().ignoreCase()
            )
            .withMatcher(
                "accountCode",
                ExampleMatcher.GenericPropertyMatchers
                    .exact().caseSensitive()
            )
            .withMatcher(
                "address.city",
                ExampleMatcher.GenericPropertyMatchers
                    .exact().ignoreCase()
            );

        return Example.of(probe, matcher);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
~~~

`trim()` ở đây là một chính sách đơn giản; nó không xử lý mọi dạng khoảng trắng Unicode. Với dữ liệu nhập đa ngôn ngữ, hãy xác định rõ phạm vi chuẩn hóa thay vì mặc định coi mọi ký tự trắng đều đã được xử lý.

Phương thức có thể được gọi như sau:

~~~java
Example<Customer> example = CustomerExamples.forSearch(
    " an ",
    "AN@EXAMPLE.COM",
    "KH-001",
    "da nang",
    Boolean.TRUE
);
~~~

Ý định điều kiện là:

~~~text
displayName bắt đầu bằng "an", bỏ qua hoa/thường
AND email bằng "AN@EXAMPLE.COM", bỏ qua hoa/thường
AND accountCode bằng "KH-001", yêu cầu phân biệt hoa/thường
AND address.city bằng "da nang", bỏ qua hoa/thường
AND active = true
~~~

Việc tên là `startsWith` và email là `exact` không thay đổi phép kết hợp giữa các thuộc tính. `matchingAll()` yêu cầu tất cả điều kiện được đưa vào ví dụ cùng đúng.

Nếu thay bằng `matchingAny()`, các điều kiện được kết hợp theo ý định OR. Khi đó, bản ghi chỉ khớp thành phố cũng có thể được chọn dù không khớp email hay mã tài khoản. Không dùng `matchingAny()` nếu yêu cầu thực tế là phối hợp nhiều bộ lọc bắt buộc.

### 6.1. Gọi repository có hỗ trợ QBE

Ví dụ dưới đây chọn Spring Data JPA làm adapter cụ thể:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

`Customer` phải là entity JPA hợp lệ; `Address` phải được ánh xạ phù hợp để đường dẫn `address.city` có thể được truy vấn.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Customer> page = repository.findAll(
    example,
    PageRequest.of(
        0,
        20,
        Sort.by("displayName").ascending()
            .and(Sort.by("id").ascending())
    )
);
~~~

Matcher quyết định bản ghi nào được chọn. `PageRequest` quyết định trang và kích thước trang; `Sort` quyết định thứ tự. Bỏ qua hoa/thường khi lọc không tự động tạo thứ tự sắp xếp không phân biệt hoa/thường.

API QBE thuộc phạm vi chung của Spring Data, nhưng khai báo repository, ánh xạ và khả năng hỗ trợ từng kiểu matcher phải được xác định theo module cụ thể. Không thay tên base repository một cách máy móc giữa các store.

## 7. Thuộc tính lồng nhau cần cả cấu hình và dữ liệu probe

Đường dẫn `address.city` chỉ mô tả cách khớp. Nó không tự tạo giá trị thành phố để truy vấn.

~~~java
Customer probe = new Customer();

Address address = new Address();
address.setCity("Ha Noi");
probe.setAddress(address);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "address.city",
        ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase()
    );
~~~

Nếu `address` là `null` và chính sách là bỏ qua `null`, riêng việc khai báo matcher cho `address.city` không tạo ra điều kiện “thành phố bằng Ha Noi”.

Cần phân biệt ba lớp:

1. Mô hình có thuộc tính và đường dẫn hợp lệ.
2. Probe có giá trị muốn tìm trên đường dẫn đó.
3. Store có thể chuyển việc so sánh đường dẫn đó thành truy vấn.

Thuộc tính đơn lồng nhau không đồng nghĩa với collection. Đừng suy ra rằng một matcher cho `orders.productName` sẽ truy vấn được collection đơn hàng bằng QBE. Các yêu cầu liên quan collection hoặc nhóm điều kiện phức tạp cần cơ chế truy vấn mà store hỗ trợ rõ ràng.

## 8. null, chuỗi rỗng và giá trị mặc định

### 8.1. null thường có nghĩa là không tham gia điều kiện

Với `withIgnoreNullValues()`, probe có `email = null` sẽ không lọc theo email.

~~~java
Customer probe = new Customer();
probe.setDisplayName("An");
// email vẫn là null
~~~

Một matcher riêng cho email không làm trường này tham gia truy vấn nếu giá trị đã bị chính sách null loại bỏ.

Nếu cần tìm giá trị đang lưu là `null`, hãy lựa chọn chính sách và kiểm tra cách store hỗ trợ truy vấn đó. Không bật `withIncludeNullValues()` tùy tiện cho cả đối tượng nhiều trường, vì các thuộc tính null khác cũng có thể trở thành điều kiện.

### 8.2. Chuỗi rỗng không phải null

Probe có `displayName = ""` vẫn chứa một giá trị chuỗi.

- Với `exact()`, ý định là tìm tên rỗng.
- Với `startsWith()` hoặc `contains()`, mẫu rỗng có thể làm điều kiện rất rộng đối với các giá trị chuỗi.
- Với `"   "`, matcher không tự bỏ khoảng trắng.

Vì thế, cần quyết định rõ ô tìm kiếm trống nghĩa là “không lọc” hay “tìm chuỗi trống”. Hàm `trimToNull` trong ví dụ thực hiện lựa chọn đầu tiên.

### 8.3. Kiểu nguyên thủy dễ sinh điều kiện ngoài ý muốn

Nếu dùng:

~~~java
private boolean active;
~~~

thì đối tượng mới thường có `active = false`; trường này không thể biểu diễn “chưa chọn bộ lọc” bằng `null`. QBE có thể đưa giá trị đó vào ví dụ dù người dùng chỉ nhập tên.

Với màn hình có ba trạng thái “tất cả”, “đang hoạt động”, “ngừng hoạt động”, `Boolean` thuận tiện hơn:

| Giá trị probe | Ý nghĩa với chính sách bỏ qua null |
|---|---|
| `null` | Không lọc theo trạng thái |
| `true` | Chỉ trạng thái hoạt động |
| `false` | Chỉ trạng thái không hoạt động |

Nếu mô hình dùng kiểu nguyên thủy hoặc có trường được khởi tạo mặc định, hãy rà soát và bỏ qua những đường dẫn không thuộc tiêu chí tìm kiếm bằng `withIgnorePaths(...)`.

Cùng một vấn đề xuất hiện nếu constructor tự đặt `active = true`, tự sinh mã hoặc tự tạo đối tượng con có giá trị mặc định. “Không gọi setter” chưa bảo đảm thuộc tính không có giá trị trong probe.

## 9. Chuẩn hóa giá trị và withTransformer

Ngoài cấu hình cách so sánh, `ExampleMatcher` cho phép biến đổi giá trị probe trên từng thuộc tính bằng `withTransformer`.

~~~java
import java.util.Optional;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    )
    .withTransformer("displayName", optionalValue -> {
        if (!optionalValue.isPresent()) {
            return Optional.empty();
        }

        Object rawValue = optionalValue.get();
        if (!(rawValue instanceof String)) {
            return optionalValue;
        }

        String trimmed = ((String) rawValue).trim();
        if (trimmed.isEmpty()) {
            return Optional.empty();
        }

        return Optional.of((Object) trimmed);
    });
~~~

Transformer nhận giá trị dưới dạng `Optional<Object>` và trả về giá trị có thể dùng cho thuộc tính đó. Trong ví dụ, chuỗi chỉ gồm khoảng trắng trở thành không có giá trị; với chính sách bỏ qua null của matcher này, nó không còn đóng góp điều kiện.

Phân biệt vai trò:

| Cơ chế | Trả lời câu hỏi |
|---|---|
| Chuẩn hóa đầu vào hoặc transformer | Giá trị mẫu nào sẽ được dùng? |
| `contains()`, `startsWith()`, `exact()` | Giá trị lưu phải có quan hệ nào với giá trị mẫu? |
| `ignoreCase()` | Có yêu cầu bỏ qua khác biệt hoa/thường khi so sánh không? |

Transformer áp dụng cho giá trị probe, không chuẩn hóa toàn bộ dữ liệu đang lưu. Chỉ chuyển probe thành chữ thường không bảo đảm tìm được dữ liệu viết hoa nếu truy vấn vẫn so sánh phân biệt hoa/thường.

Hãy chọn nơi chuẩn hóa phù hợp với thiết kế ứng dụng. Nếu đầu vào đã được chuẩn hóa đầy đủ trước khi tạo probe, không cần lặp lại transformer chỉ để thực hiện cùng một việc.

## 10. Hoa/thường, dấu tiếng Việt và collation

Ba yêu cầu sau khác nhau:

| Yêu cầu | Ví dụ |
|---|---|
| Không phân biệt hoa/thường | `An` khớp `an` |
| Không phân biệt dấu | `Đà Nẵng` khớp `Da Nang` |
| Chuẩn hóa biểu diễn Unicode | Các chuỗi có cùng hình thức hiển thị nhưng cách mã hóa khác nhau vẫn được xử lý nhất quán |

`ignoreCase` chỉ biểu đạt yêu cầu đầu tiên. Nó không bảo đảm hai yêu cầu còn lại.

Do đó, trong ví dụ tìm kiếm, `city = "da nang"` không mặc nhiên khớp dữ liệu `"Đà Nẵng"`. Nếu sản phẩm cần tìm không dấu, cần thiết kế giải pháp phù hợp với store, chẳng hạn trường tìm kiếm đã chuẩn hóa, collation được lựa chọn có chủ đích hoặc công cụ tìm kiếm chuyên dụng.

Collation có thể ảnh hưởng đến việc so sánh hoa/thường, dấu và thứ tự chuỗi. Ngôn ngữ tự nhiên cũng có những quy tắc chuyển đổi chữ không thể được đánh giá đầy đủ chỉ bằng một vài ví dụ ASCII.

Đừng dùng kết quả chạy trong bộ nhớ hoặc trên một cơ sở dữ liệu thử nghiệm để khẳng định mọi store sẽ trả cùng kết quả.

## 11. Khả năng hỗ trợ phụ thuộc kho dữ liệu

Spring Data Commons định nghĩa abstraction. Nó không bảo đảm mọi module Spring Data hỗ trợ đầy đủ mọi lựa chọn trong `StringMatcher`.

Một vài điểm cần ghi nhớ khi áp dụng:

- Spring Data JPA hỗ trợ những kiểu khớp phổ biến như chính xác, đầu chuỗi, cuối chuỗi và chứa chuỗi; QBE của JPA không hỗ trợ `REGEX`.
- Spring Data MongoDB có thể biểu diễn nhiều kiểu khớp chuỗi bằng truy vấn regex, bao gồm lựa chọn bỏ qua hoa/thường. Cách dịch này không biến probe dùng `contains()` thành regex tùy ý do người dùng tự viết.
- Các store khác có tập khả năng và cách ánh xạ riêng; sự hiện diện của một enum trong Commons không chứng minh store đó triển khai nó.

Khi cấu hình một kiểu khớp không được hỗ trợ, không dựa vào giả định rằng framework sẽ tự chuyển sang một kiểu gần giống. Cần chọn API truy vấn khác hoặc cấu hình được store hỗ trợ.

Regex cũng không đồng nghĩa với tìm kiếm toàn văn. Nếu yêu cầu gồm nhiều từ, xếp hạng độ liên quan, sửa lỗi chính tả hoặc bộ phân tích ngôn ngữ, nên đánh giá chức năng tìm kiếm chuyên biệt thay vì cố nhồi mọi thứ vào QBE.

## 12. Hiệu năng và phạm vi sử dụng

Những lựa chọn dễ dùng nhất chưa chắc phù hợp nhất với dữ liệu lớn.

| Lựa chọn | Điểm cần đánh giá |
|---|---|
| `exact()` | Thường thuận lợi hơn cho tra cứu định danh; còn tùy chỉ mục và phép so sánh |
| `startsWith()` | Có thể tận dụng cấu trúc chỉ mục phù hợp; phụ thuộc store, collation và cách dịch |
| `contains()`, `endsWith()` | Có nguy cơ quét nhiều dữ liệu do mẫu không có tiền tố cố định |
| `ignoreCase()` | Có thể tạo phép biến đổi hoặc cơ chế so sánh làm thay đổi khả năng dùng chỉ mục |
| `regex()` | Chi phí phụ thuộc mẫu, cách neo biểu thức và khả năng của store |

Không thể kết luận có chỉ mục là truy vấn `contains().ignoreCase()` sẽ nhanh. Cần xem truy vấn thực tế và kế hoạch thực thi của kho dữ liệu khi triển khai.

Với màn hình tìm kiếm, có thể đặt độ dài tối thiểu cho phần tên, giới hạn kích thước trang và ưu tiên `startsWith()` nếu đáp ứng đúng nhu cầu. Nếu toàn bộ đầu vào sau chuẩn hóa đều trống, ví dụ không có điều kiện có thể chọn toàn bộ tập dữ liệu. Ứng dụng cần chủ động quyết định có cho phép thao tác đó hay yêu cầu ít nhất một bộ lọc.

QBE cũng không phải công cụ phù hợp cho mọi biểu thức. Yêu cầu như:

~~~text
(active = true)
AND (displayName bắt đầu bằng q OR email bằng q)
~~~

có nhóm điều kiện kết hợp AND/OR mà một lựa chọn `matchingAll()` hay `matchingAny()` cho toàn bộ ví dụ không diễn đạt đủ. Khi đó, hãy dùng cơ chế phù hợp với module, chẳng hạn Specification hoặc truy vấn được khai báo trong một ứng dụng JPA.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Tên “An” không tìm thấy “Binh An” | Đang dùng `exact()` hoặc `startsWith()` | Chọn `contains()` nếu đúng nghiệp vụ |
| Tìm đúng email lại ra nhiều địa chỉ khác | Đặt `CONTAINING` chung mà chưa ghi đè email | Dùng `exact()` cho email |
| Cấu hình bỏ qua hoa/thường không có tác dụng | Bỏ kết quả trả về của `withIgnoreCase()` | Gán matcher mới hoặc nối chuỗi lời gọi |
| Mã tài khoản phân biệt hoa/thường không đúng | Quy tắc store/collation không đáp ứng yêu cầu | Kiểm tra ánh xạ, phép so sánh và thiết kế chỉ mục |
| Không tìm được tên có dấu bằng đầu vào không dấu | Nhầm `ignoreCase` với bỏ dấu | Thiết kế chính sách tìm không dấu riêng |
| Tìm tên nhưng chỉ thấy khách ngừng hoạt động | Probe có `boolean active = false` ngoài ý muốn | Dùng `Boolean` hoặc bỏ qua đường dẫn |
| Matcher cho thành phố không lọc kết quả | Probe chưa có `address.city` | Tạo đối tượng con và đặt giá trị cần tìm |
| Nhập khoảng trắng làm kết quả bất thường | Chuỗi trắng vẫn được coi là giá trị | Chuẩn hóa theo quy ước đầu vào |
| Cấu hình đường dẫn không đúng | Dùng tên cột thay cho tên thuộc tính Java | Dùng đường dẫn thuộc tính của mô hình |
| Regex không chạy trên JPA | Store không hỗ trợ kiểu matcher đó | Chọn truy vấn khác phù hợp |

## 14. Thực hành và tự kiểm tra

Tạo tập dữ liệu minh họa dưới đây trong store bạn đang học. Bảng chỉ thể hiện các thuộc tính dùng cho bài tập:

| id | displayName | email | accountCode | address.city | active |
|---|---|---|---|---|---|
| 1 | `An` | `an@example.com` | `KH-001` | `Da Nang` | `true` |
| 2 | `Anh` | `anh@example.com` | `KH-002` | `Ha Noi` | `true` |
| 3 | `Binh An` | `binh.an@example.com` | `KH-003` | `Da Nang` | `false` |
| 4 | `an` | `an@other.com` | `kh-001` | `DA NANG` | `true` |
| 5 | `Đà Nẵng Travel` | `travel@example.com` | `KH-005` | `Đà Nẵng` | `true` |

Thực hiện từng truy vấn bằng probe mới để tránh giữ giá trị từ bước trước:

1. Chỉ đặt `displayName = "an"`, dùng `startsWith().ignoreCase()`. Với hành vi bỏ qua hoa/thường thông thường, các dòng 1, 2 và 4 được kỳ vọng khớp.
2. Giữ giá trị `"an"` nhưng đổi thành `contains().ignoreCase()`. Dòng 3 được thêm vì tên chứa “An” ở cuối.
3. Chỉ đặt `email = "AN@EXAMPLE.COM"`, dùng `exact().ignoreCase()`. Kỳ vọng chỉ dòng 1.
4. Kết hợp tên `"an"` theo tiền tố với email của bước 3 bằng `matchingAll()`. Kỳ vọng vẫn chỉ dòng 1.
5. Đổi cùng probe của bước 4 sang `matchingAny()`. Kỳ vọng có các dòng 1, 2 và 4; giải thích vì sao email không còn là bộ lọc bắt buộc.
6. Chỉ đặt `accountCode = "KH-001"`, dùng `exact().caseSensitive()`. Kiểm tra store có phân biệt dòng 1 với dòng 4 không. Nếu không, xác định quy tắc so sánh thực tế thay vì kết luận matcher tự bảo đảm yêu cầu.
7. Chỉ đặt `address.city = "da nang"`, dùng `exact().ignoreCase()`. Dòng 1 và 4 được kỳ vọng khớp khi bỏ qua hoa/thường; việc dòng 5 có khớp hay không phụ thuộc khả năng xử lý dấu của store, không do `ignoreCase` bảo đảm.
8. Gửi `displayName = "   "` qua `CustomerExamples.forSearch` và để các đầu vào còn lại là `null`. Nhận diện đây là probe không có bộ lọc hữu hiệu; quyết định chính sách cho phép hay từ chối tại tầng ứng dụng.

Khi kiểm tra trên store thực, hãy quan sát cả kết quả và truy vấn được tạo. Các câu hỏi cốt lõi là: giá trị nào đã vào probe, thuộc tính nào tham gia điều kiện, quy tắc riêng nào ghi đè quy tắc chung và store thực sự thực hiện phép so sánh nào.

Với QBE, cấu hình rõ ràng thường bắt đầu bằng một probe gọn và chính sách khớp sát nghiệp vụ: tên có thể tìm theo tiền tố hoặc chuỗi con, email có thể cần bằng toàn bộ giá trị, mã tài khoản có thể yêu cầu phân biệt hoa/thường. Khi giữ các quyết định đó tách biệt, bạn có thể tái sử dụng abstraction của Spring Data Commons mà vẫn áp dụng đúng khả năng của từng kho dữ liệu.
