# Biến đổi giá trị trước khi đối sánh

Trong Query by Example (QBE), probe chứa các giá trị mẫu, còn `ExampleMatcher` mô tả cách dùng những giá trị đó để tạo điều kiện tìm kiếm. Dữ liệu nhận từ biểu mẫu thường chưa ở dạng phù hợp: email có khoảng trắng ở hai đầu, mã quốc gia viết thường hoặc chuỗi rỗng cần được coi là không có bộ lọc. Biến đổi giá trị giúp chuẩn bị đầu vào của từng thuộc tính trước khi kho dữ liệu thực hiện đối sánh.

Spring Data Commons cung cấp abstraction `ExampleMatcher.PropertyValueTransformer` và phương thức `withTransformer(...)` cho nhu cầu này. Bài học tập trung vào cách sử dụng abstraction chung ấy, đồng thời phân biệt nó với chuẩn hóa dữ liệu khi ghi, chuyển đổi kiểu lưu trữ và các toán tử truy vấn mà từng Spring Data store hỗ trợ.

## 1. Xác định giá trị nào được biến đổi

Giả sử hệ thống lưu email theo chính sách nội bộ: bỏ khoảng trắng ở hai đầu và chuyển về chữ thường. Người dùng nhập:

```text
Giá trị trong probe:          "  LINH@EXAMPLE.COM  "
Giá trị dùng để tìm kiếm:     "linh@example.com"
Giá trị đang được lưu:        "linh@example.com"
```

Transformer xử lý giá trị lấy từ probe để tạo giá trị tìm kiếm. Nó không tự sửa bản ghi đã lưu và cũng không phải lời gọi cập nhật dữ liệu.

Luồng xử lý có thể hình dung như sau:

```text
Đầu vào tìm kiếm
      |
      v
Probe và cấu hình ExampleMatcher
      |
      v
Store đọc thuộc tính, áp dụng transformer và các quy tắc matcher
      |
      v
Điều kiện truy vấn phù hợp với store
      |
      v
Kết quả từ repository
```

Sơ đồ thể hiện vai trò các thành phần; chi tiết dựng truy vấn do module tích hợp với kho dữ liệu thực hiện. Không nên suy ra rằng mọi store dùng cùng biểu thức truy vấn hoặc cùng cơ chế xử lý chuỗi.

Ba điểm cần giữ rõ:

- Transformer nhận giá trị của một property path được chỉ định.
- Kết quả transformer cung cấp giá trị để đối sánh, không định nghĩa tùy ý một toán tử truy vấn mới.
- Việc biến đổi đầu vào không khiến dữ liệu đang lưu tự động được chuẩn hóa theo cùng quy tắc.

## 2. API `withTransformer` và hợp đồng `Optional`

Đăng ký transformer bằng tên thuộc tính Java của probe:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withTransformer("email", source -> source.map(value ->
        ((String) value).trim().toLowerCase(Locale.ROOT)
    ));
```

Đoạn mã sử dụng `ExampleMatcher` từ `org.springframework.data.domain` và `Locale` từ `java.util`.

Hai kiểu dữ liệu của callback là:

```text
Đầu vào:  Optional<Object>
Đầu ra:   Optional<Object>
```

`PropertyValueTransformer` có hành vi của một hàm từ `Optional<Object>` sang `Optional<Object>`. Dùng `Optional` cho phép biểu diễn trường hợp không có giá trị, thay vì buộc callback luôn nhận và trả về một object cụ thể.

| Thành phần | Ý nghĩa khi sử dụng |
| --- | --- |
| `"email"` | Property path trong mô hình Java, không phải tên cột tùy ý |
| `source` có giá trị | Giá trị thuộc tính cần chuẩn bị cho truy vấn |
| `source` rỗng | Trường hợp không có giá trị; callback phải xử lý an toàn |
| `Optional.of(value)` | Có giá trị để store tiếp tục tạo điều kiện đối sánh |
| `Optional.empty()` | Không còn giá trị sau biến đổi; cách tạo điều kiện còn chịu chính sách null |
| Trả về Java `null` | Vi phạm hợp đồng callback; không dùng để biểu diễn giá trị vắng mặt |

Không gọi `source.get()` trước khi kiểm tra. Cách dùng `source.map(...)` trong ví dụ đầu giúp trường hợp rỗng được truyền tiếp an toàn.

Giá trị bên trong `Optional` có kiểu khai báo là `Object`. Điều đó không có nghĩa có thể trả về tùy ý một kiểu khác với thuộc tính. Với `email` kiểu `String`, nên trả về `String`. Với `age` kiểu `Integer`, nên giữ giá trị tương thích với `Integer` và kiểu dữ liệu mà store có thể truy vấn.

### `ExampleMatcher` trả về cấu hình mới

Các phương thức cấu hình matcher trả về matcher mới. Cần giữ giá trị trả về hoặc nối chuỗi lời gọi:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

matcher = matcher.withTransformer("email", source -> source.map(value ->
    ((String) value).trim().toLowerCase(Locale.ROOT)
));
```

Nếu chỉ gọi `matcher.withTransformer(...)` rồi tiếp tục dùng biến `matcher` cũ, cấu hình mới không được áp dụng vào `Example`.

## 3. Ví dụ đầy đủ: tìm khách hàng theo email và mã quốc gia

Giả sử ứng dụng có hai quy ước dữ liệu:

1. Email dùng cho tìm kiếm được lưu ở dạng đã trim và viết thường theo chính sách của ứng dụng.
2. Mã quốc gia được lưu ở dạng đã trim và viết hoa, chẳng hạn `VN`.

Chính sách viết thường email phải là quyết định của miền nghiệp vụ; không coi đây là quy tắc đúng cho mọi hệ thống email. Nếu sản phẩm cần giữ dạng nhập ban đầu, có thể lưu riêng giá trị hiển thị và giá trị đã chuẩn hóa dùng để tra cứu.

### 3.1. Mô hình dùng làm probe

```java
public class Customer {

    private String id;
    private String email;
    private String countryCode;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }
}
```

Đây là phần mô hình phục vụ minh họa API chung. Khi tích hợp thực tế, cần bổ sung mapping, định danh và yêu cầu khởi tạo đối tượng theo store đang dùng. Ví dụ, mapping entity của JPA và mapping document của MongoDB thuộc trách nhiệm của module tương ứng, không được Spring Data Commons thay thế.

### 3.2. Tạo `Example` với transformer theo thuộc tính

```java
import java.util.Locale;
import java.util.Optional;
import java.util.function.UnaryOperator;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.ExampleMatcher.GenericPropertyMatchers;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> byContact(
            String rawEmail,
            String rawCountryCode) {

        if (isBlank(rawEmail) && isBlank(rawCountryCode)) {
            throw new IllegalArgumentException(
                "Cần ít nhất một tiêu chí tìm kiếm không rỗng"
            );
        }

        Customer probe = new Customer();
        probe.setEmail(rawEmail);
        probe.setCountryCode(rawCountryCode);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id")
            .withIgnoreNullValues()
            .withMatcher("email", GenericPropertyMatchers.exact())
            .withMatcher("countryCode", GenericPropertyMatchers.exact())
            .withTransformer("email", source -> normalizeText(
                source,
                value -> value.trim().toLowerCase(Locale.ROOT)
            ))
            .withTransformer("countryCode", source -> normalizeText(
                source,
                value -> value.trim().toUpperCase(Locale.ROOT)
            ));

        return Example.of(probe, matcher);
    }

    private static Optional<Object> normalizeText(
            Optional<Object> source,
            UnaryOperator<String> normalizer) {

        if (!source.isPresent()) {
            return Optional.empty();
        }

        Object raw = source.get();
        if (!(raw instanceof String)) {
            throw new IllegalArgumentException(
                "Transformer này chỉ nhận thuộc tính String"
            );
        }

        String normalized = normalizer.apply((String) raw);
        if (normalized == null) {
            throw new IllegalArgumentException(
                "Hàm chuẩn hóa không được trả về null"
            );
        }

        if (normalized.isEmpty()) {
            return Optional.empty();
        }

        return Optional.of(normalized);
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
```

Các lựa chọn trong ví dụ có mục đích cụ thể:

- `matchingAll()` yêu cầu các điều kiện được giữ lại cùng thỏa mãn.
- `withIgnorePaths("id")` nói rõ định danh không phải bộ lọc của màn hình này.
- `withIgnoreNullValues()` chọn chính sách bỏ qua các giá trị vắng mặt.
- `exact()` thể hiện ý định so khớp toàn bộ email và mã quốc gia.
- Mỗi transformer áp dụng quy tắc riêng của đúng thuộc tính đó.
- Chuỗi chỉ chứa khoảng trắng trở thành `Optional.empty()` sau chuẩn hóa.
- Kiểm tra đầu phương thức ngăn trường hợp cả hai bộ lọc đều rỗng dẫn đến một truy vấn quá rộng.

`trim()` trong bài dùng để bỏ khoảng trắng thông thường ở hai đầu. Nếu sản phẩm cần xử lý các dạng khoảng trắng Unicode hoặc ký tự đặc biệt, cần quy định rõ tập ký tự và dùng hàm chuẩn hóa tương ứng; không mặc định `trim()` xử lý mọi ký tự trông giống khoảng trắng.

### 3.3. Thực thi qua repository có hỗ trợ QBE

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, String>,
                QueryByExampleExecutor<Customer> {
}
```

Một đoạn sử dụng tại service có thể là:

```java
Example<Customer> example = CustomerExamples.byContact(
    "  LINH@EXAMPLE.COM  ",
    " vn "
);

Iterable<Customer> customers = repository.findAll(example);
```

Ở đây `repository` là `CustomerRepository` được ứng dụng cung cấp. Trước khi tích hợp, phải xác nhận module Spring Data và repository implementation đang dùng hỗ trợ QBE cùng các matcher được chọn. Khai báo thêm `QueryByExampleExecutor` vào interface không tự bổ sung khả năng QBE cho một store chưa hỗ trợ nó.

Với dữ liệu lưu đúng hai quy ước ở đầu ví dụ, ý nghĩa tìm kiếm mong muốn là:

```text
email bằng "linh@example.com"
VÀ
countryCode bằng "VN"
```

Đây là mô tả điều kiện, không phải cam kết rằng mọi store sinh cùng một câu SQL. Việc so sánh cụ thể còn chịu quy tắc chuỗi, collation và khả năng của kho dữ liệu.

## 4. Phân biệt transformer với quy tắc đối sánh chuỗi

Transformer trả lời câu hỏi: “Giá trị nào sẽ được dùng để tìm?”. String matcher trả lời câu hỏi: “Giá trị đó được so sánh như thế nào?”.

| Nhu cầu | Cấu hình hoặc nơi xử lý phù hợp |
| --- | --- |
| Bỏ khoảng trắng ở hai đầu giá trị nhập | Transformer hoặc bước chuẩn hóa đầu vào |
| Chuẩn hóa mã định danh về chữ hoa | Transformer theo chính sách miền nghiệp vụ |
| So sánh toàn bộ chuỗi | `GenericPropertyMatchers.exact()` nếu store hỗ trợ |
| So sánh tiền tố hoặc chuỗi con | `startsWith()` hoặc `contains()` nếu store hỗ trợ |
| Bỏ qua hoa thường khi đối sánh | `ignoreCase()` theo khả năng của store |
| Chuẩn hóa tất cả bản ghi khi ghi | Luồng ghi dữ liệu và chính sách lưu trữ |
| Chuyển một thuộc tính sang kiểu lưu trữ khác | Cơ chế conversion/mapping của store |

Ví dụ, một trường tên có thể cần bỏ khoảng trắng ở hai đầu nhưng vẫn tìm theo tiền tố và bỏ qua hoa thường:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "displayName",
        GenericPropertyMatchers.startsWith().ignoreCase()
    )
    .withTransformer("displayName", source -> source.map(value ->
        ((String) value).trim()
    ));
```

Đoạn mã áp dụng cho mô hình có thuộc tính `displayName` kiểu `String`. Nếu dữ liệu nhập có thể toàn khoảng trắng, cần bổ sung chính sách bỏ tiêu chí như helper ở ví dụ đầy đủ.

Không nên tự thêm `%` vào giá trị để giả lập `contains()`:

```java
// Tránh: phụ thuộc cách store hiểu hoặc escape ký tự phần trăm.
.withTransformer("displayName", source -> source.map(value ->
    "%" + value + "%"
));
```

Dấu `%` trong SQL, biểu thức chính quy và phép tìm kiếm chuỗi của các store không có cùng ngữ nghĩa. Hãy mô tả cách đối sánh bằng matcher được hỗ trợ, thay vì nhét cú pháp truy vấn vào dữ liệu.

Tương tự, chuyển giá trị tìm kiếm sang chữ thường không tương đương với cấu hình bỏ qua hoa thường ở phía kho dữ liệu. Nếu bản ghi chứa `Linh@Example.com`, transformer tạo `linh@example.com` chưa đủ bảo đảm tìm thấy bản ghi đó trong một phép so sánh có phân biệt hoa thường.

## 5. `null`, chuỗi rỗng và `Optional.empty()`

Đây là phần dễ gây lỗi nhất khi thiết kế transformer.

### 5.1. Chuỗi rỗng vẫn là một giá trị

Trong Java, `""` và `null` khác nhau. Nếu transformer trả về `Optional.of("")`, matcher vẫn nhận được một giá trị chuỗi. Không thể mặc định rằng QBE sẽ hiểu đó là yêu cầu bỏ qua thuộc tính. Cách store biểu diễn chuỗi rỗng cũng có thể khác nhau.

Nếu sản phẩm quy định ô tìm kiếm trống nghĩa là không lọc theo trường đó, cần chủ động biến chuỗi rỗng sau chuẩn hóa thành `Optional.empty()` và chọn chính sách null phù hợp.

### 5.2. Ý nghĩa của giá trị vắng mặt phụ thuộc null handler

Với chính sách bỏ qua null như ví dụ, giá trị vắng mặt sau biến đổi được dùng để bỏ tiêu chí tương ứng trong triển khai QBE hỗ trợ cơ chế này. Không mở rộng kết luận đó thành quy tắc “`Optional.empty()` luôn bỏ điều kiện”.

Nếu đổi sang `withIncludeNullValues()`, giá trị vắng mặt có thể được diễn giải thành điều kiện tìm dữ liệu null theo cách triển khai của store. Khi cần bỏ qua một thuộc tính bất kể giá trị và chính sách null, dùng `withIgnorePaths(...)`.

| Đầu vào hoặc kết quả | Chính sách trong ví dụ | Ý định truy vấn |
| --- | --- | --- |
| Email `"  LINH@EXAMPLE.COM "` | Chuẩn hóa rồi đối sánh chính xác | Lọc theo `linh@example.com` |
| Email `"   "` | Chuẩn hóa thành vắng mặt, bỏ qua null | Không lọc theo email |
| Email `null` | Giữ trạng thái vắng mặt, bỏ qua null | Không lọc theo email |
| Mã quốc gia `" vn "` | Chuẩn hóa rồi đối sánh chính xác | Lọc theo `VN` |
| Cả hai đầu vào rỗng | Kiểm tra trước khi tạo `Example` | Từ chối yêu cầu tìm kiếm thiếu tiêu chí |

Bảng mô tả chính sách của ví dụ, không thay cho việc xác nhận hành vi của store tích hợp.

### 5.3. Chú ý các thuộc tính primitive

Một probe lớn có thể chứa `boolean enabled` hoặc `int score`. Các trường này luôn có giá trị mặc định như `false` hay `0`; chúng không biểu diễn được trạng thái vắng mặt bằng `null`.

Nếu không thuộc phạm vi tìm kiếm, khai báo rõ:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "enabled", "score");
```

Nếu nghiệp vụ cần phân biệt “không lọc” với “lọc bằng false”, có thể cân nhắc kiểu wrapper như `Boolean` trong mô hình phù hợp hoặc thiết kế bước dựng probe riêng. Transformer cho email không tự loại bỏ các điều kiện phát sinh từ thuộc tính khác.

## 6. Không sửa probe bên trong transformer

Transformer nên là hàm thuần: cùng đầu vào cho cùng kết quả, không có tác dụng phụ và không phụ thuộc trạng thái thay đổi.

Không nên viết:

```java
.withTransformer("email", source -> {
    probe.setEmail("linh@example.com");
    auditService.recordSearch();
    return source;
});
```

Đoạn mã vừa thay đổi đối tượng tìm kiếm vừa ghi nhận sự kiện ngay trong lúc dựng điều kiện. Điều này khiến hành vi khó dự đoán nếu matcher được tái sử dụng, truy vấn được thực thi lại hoặc repository đi qua các nhánh xử lý khác nhau.

Hãy để transformer chỉ tính giá trị trả về. Ghi log nghiệp vụ, kiểm tra quyền và ghi audit của hành động tìm kiếm ở service hoặc cơ chế phù hợp. Auditing entity của Spring Data cũng là một trách nhiệm khác với việc biến đổi giá trị của QBE.

Không dùng callback để gọi repository khác, gọi API từ xa hoặc tra bảng quy đổi thay đổi liên tục. Nếu cần ánh xạ mã bên ngoài sang mã nội bộ, hoàn thành bước đó trước khi tạo probe và xử lý lỗi ngay tại bước chuẩn bị đầu vào.

`ExampleMatcher` có thể được dùng lại khi các callback an toàn để dùng chung. Tuy nhiên, probe thường là một đối tượng mutable và `Example.of(...)` không phải cam kết tạo bản sao sâu của probe. Vì vậy, không thay đổi probe sau khi đã tạo `Example`, đặc biệt khi có nhiều luồng cùng sử dụng.

## 7. Property path, kiểu dữ liệu và phạm vi hỗ trợ

### 7.1. Dùng tên thuộc tính của mô hình

`withTransformer("email", ...)` tham chiếu thuộc tính Java `email`. Nó không đổi tên thuộc tính truy vấn và không ánh xạ `email` thành một trường khác như `emailNormalized`.

Nếu mô hình có trường tra cứu riêng, cần đặt giá trị trên đúng trường đó trong probe và cấu hình transformer cho đúng property path.

Với thuộc tính lồng nhau, có thể gặp cấu hình dạng:

```java
.withTransformer("address.city", source -> source.map(value ->
    ((String) value).trim()
));
```

Chỉ dùng cách này khi mô hình và store hỗ trợ đường dẫn đó trong QBE. Cú pháp có dấu chấm không tự tạo khả năng truy vấn mọi association, collection, map hoặc phần tử mảng.

### 7.2. Transformer không phải bộ chuyển đổi mọi kiểu dữ liệu

Giả sử thuộc tính `age` là `Integer`. Không nên trả về chuỗi `"18"` rồi kỳ vọng store tự sửa mọi khác biệt về kiểu. Càng không nên đưa một DTO như `AgeRange(18, 30)` vào vị trí giá trị tuổi để mong sinh điều kiện khoảng.

Nếu biểu mẫu gửi tuổi dưới dạng chuỗi, luồng xử lý nên là:

```text
Chuỗi đầu vào
    -> kiểm tra và parse thành Integer
    -> đặt Integer lên probe
    -> dùng QBE với ngữ nghĩa mà store hỗ trợ
```

Với ngày giờ, xác định múi giờ và đơn vị nghiệp vụ trước khi truy vấn. Biến đổi timestamp về đầu ngày rồi dùng đối sánh bằng không đồng nghĩa với việc tìm toàn bộ bản ghi trong ngày đó.

### 7.3. Không mở rộng QBE thành ngôn ngữ truy vấn tùy ý

Transformer không tự biểu diễn được:

- Khoảng giá trị như tuổi từ 18 đến 30.
- Nhóm điều kiện lồng nhau theo mọi biểu thức Boolean.
- Join hoặc đối sánh collection tùy ý.
- Tìm kiếm toàn văn, bỏ dấu hoặc xếp hạng độ liên quan.
- Một toán tử mới chỉ bằng cách trả về object hoặc chuỗi đặc biệt.

Khi yêu cầu vượt khả năng QBE của store, chọn cơ chế truy vấn phù hợp mà module đó cung cấp, chẳng hạn derived query, truy vấn khai báo hoặc API truy vấn động tương ứng. Việc chọn cơ chế dựa trên ngữ nghĩa cần diễn đạt, không dựa trên độ dài callback.

## 8. Chuẩn hóa đầu vào và chuẩn hóa dữ liệu lưu trữ

Giả sử kho dữ liệu đang có ba giá trị:

```text
linh@example.com
Linh@Example.com
  linh@example.com
```

Transformer chỉ biến đổi đầu vào thành `linh@example.com`. Trong phép đối sánh có phân biệt hoa thường và khoảng trắng, không có cơ sở để coi cả ba bản ghi đều khớp.

Một thiết kế nhất quán cần quyết định:

1. Dữ liệu có được chuẩn hóa ngay khi ghi không?
2. Có cần giữ giá trị nhập ban đầu để hiển thị không?
3. Có trường riêng phục vụ tra cứu hoặc ràng buộc duy nhất không?
4. Dữ liệu cũ sẽ được chuẩn hóa như thế nào?
5. Phép so sánh và chỉ mục của store có phù hợp với quy tắc đó không?

`Locale.ROOT` giúp quy tắc chuyển hoa thường cho mã kỹ thuật không phụ thuộc locale mặc định của máy chạy. Tuy vậy, đây không phải lựa chọn tự động cho mọi loại văn bản ngôn ngữ tự nhiên. Tên người, nội dung tiếng Việt và mã định danh có thể cần các chính sách khác nhau.

Việc chỉ chuẩn hóa giá trị tham số cũng không bảo đảm một truy vấn luôn dùng chỉ mục. Collation, các thao tác phía store khi bỏ qua hoa thường, kiểu matcher và cấu trúc chỉ mục đều có thể ảnh hưởng kế hoạch thực thi.

## 9. Những lỗi thường gặp và cách sửa

| Biểu hiện | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Khoảng trắng vẫn khiến tìm kiếm không khớp | Không giữ matcher trả về hoặc cấu hình sai property path | Gán lại matcher, kiểm tra tên thuộc tính và `Example` thực sự được truyền |
| Email đã lowercase nhưng vẫn không tìm thấy | Dữ liệu lưu có dạng khác; đối sánh đang phân biệt hoa thường | Kiểm tra chính sách lưu, collation và khả năng `ignoreCase()` của store |
| Xóa nội dung ô tìm kiếm nhưng kết quả bị lọc lạ | Trả `Optional.of("")` hoặc đang include null | Định nghĩa rõ chính sách bỏ tiêu chí, dùng empty cùng null handler phù hợp |
| Truy vấn trả về quá nhiều dữ liệu | Mọi điều kiện đều bị loại bỏ sau chuẩn hóa | Kiểm tra bộ lọc còn hiệu lực trước khi gọi repository |
| Phát sinh lỗi ép kiểu | Dùng transformer chuỗi cho thuộc tính khác kiểu | Tách transformer theo kiểu thuộc tính và kiểm tra hợp đồng giá trị |
| Kết quả khác giữa các máy | Dùng locale mặc định cho chuyển hoa thường | Chọn locale rõ ràng theo chính sách nghiệp vụ |
| Có điều kiện `false` hoặc `0` ngoài ý muốn | Probe có thuộc tính primitive chưa được bỏ qua | Dùng `withIgnorePaths(...)` hoặc thiết kế dữ liệu biểu diễn được trạng thái vắng mặt |
| Dữ liệu thay đổi trong lúc tìm kiếm | Transformer có tác dụng phụ hoặc probe bị sửa sau khi tạo example | Giữ callback thuần và ổn định probe trong suốt lần thực thi |

Không ghi trực tiếp email, số điện thoại hoặc dữ liệu nhạy cảm vào log chỉ để quan sát transformer. Khi cần chẩn đoán, ưu tiên ghi tên thuộc tính, việc tiêu chí có được giữ lại hay không và giá trị đã che phù hợp.

## 10. Tự thực hành và đối chiếu hành vi

Dùng store hỗ trợ QBE của ứng dụng và chuẩn bị dữ liệu theo chính sách đã chọn. Có thể lần lượt kiểm tra các tình huống sau:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Nhập `"  LINH@EXAMPLE.COM  "` cùng `" vn "` | Giá trị tìm kiếm tương ứng là email đã chuẩn hóa và mã `VN` |
| Chỉ nhập mã quốc gia | Không xuất hiện điều kiện email ngoài ý muốn |
| Nhập email toàn khoảng trắng và mã quốc gia hợp lệ | Email được coi là thiếu tiêu chí theo null handler đã chọn |
| Để trống cả hai trường | Bước kiểm tra đầu vào từ chối trước khi gọi repository |
| Có bản ghi email lưu khác quy tắc chuẩn hóa | Phân biệt được ảnh hưởng của dữ liệu lưu và matcher |
| Chuyển sang include null trong một ví dụ riêng | Quan sát cách store diễn giải giá trị vắng mặt, không dùng giả định cũ |
| Mô hình có thêm trường primitive | Không phát sinh bộ lọc ngoài phạm vi màn hình tìm kiếm |

Khi kiểm tra callback riêng, tập trung vào giá trị đầu vào, đầu ra và kiểu dữ liệu. Khi kiểm tra repository, tập trung vào tập bản ghi thực sự khớp trên store đích. Hai lớp kiểm tra giải quyết hai câu hỏi khác nhau: transformer chuẩn bị gì và store diễn giải điều kiện như thế nào.

`withTransformer` phù hợp khi cần điều chỉnh giá trị của từng thuộc tính trước đối sánh trong QBE. Dùng nó hiệu quả đòi hỏi thống nhất ba quyết định: quy tắc chuẩn hóa đầu vào, matcher dùng để so sánh và khả năng thực tế của kho dữ liệu.