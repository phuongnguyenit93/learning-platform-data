# Javadoc cho record, sealed và hợp đồng API trong Java 17

**Chủ đề:** Java 17 → Biên dịch và tài liệu  
**Trọng tâm:** Viết Javadoc cho record components, sealed classes/interfaces và các hợp đồng API; hiểu những phần mà standard doclet tự tạo, cách mô tả điều kiện đầu vào/đầu ra, ngoại lệ, khả năng thay đổi dữ liệu và cách cấu hình các tag bổ sung khi sinh tài liệu bằng JDK 17.

Javadoc là tài liệu gắn trực tiếp với khai báo trong mã nguồn. Công cụ `javadoc` đọc source code và documentation comments rồi tạo HTML API documentation. Với Java 17, standard doclet hiểu cấu trúc record và sealed type: nó tạo mục **Record Components** cho record và **Permitted Subclasses** cho sealed class hoặc interface. Người viết tài liệu cần mô tả ý nghĩa nghiệp vụ của từng thành phần, các subtype được phép và hợp đồng mà người dùng API có thể dựa vào.

Một Javadoc tốt trả lời được những câu hỏi thực tế: đối tượng đại diện cho điều gì, tham số nào hợp lệ, kết quả có thể null không, collection có thể sửa không, ngoại lệ nào được ném và trong điều kiện nào, method có side effect không, thứ tự có được bảo đảm không, và hành vi nào là cam kết công khai. Phần mô tả hợp đồng phải nói về điều người gọi có thể dựa vào; chi tiết triển khai chỉ nên được ghi riêng khi thực sự cần.

## 1. Javadoc trong quy trình phát triển API

Một documentation comment được đặt ngay trước khai báo cần mô tả:

~~~java
/**
 * Returns the current account balance.
 *
 * @return the balance in the account's currency
 */
public BigDecimal balance() {
    return balance;
}
~~~

Javadoc chuẩn thường có hai phần:

1. **Mô tả chính (main description):** câu đầu tiên nên là một câu tóm tắt ngắn, đầy đủ; các đoạn tiếp theo giải thích ngữ cảnh và hành vi.
2. **Block tags:** cung cấp thông tin có cấu trúc như `@param`, `@return`, `@throws`, `@since`, `@deprecated`, `@see`.

Standard doclet tạo các trang HTML từ source code. Tài liệu sinh ra có thể chứa trang module, package, class, constructor, method, record component, danh sách subtype được phép, liên kết và chỉ mục tìm kiếm. Đây là lý do Javadoc nên mô tả API ở mức người dùng thư viện cần hiểu, thay vì chỉ lặp lại tên method hoặc chú thích nội bộ.

### 1.1. Viết câu tóm tắt có ý nghĩa

Ví dụ tốt:

~~~java
/**
 * Returns an immutable snapshot of the configured roles.
 */
public List<String> roles() {
    return roles;
}
~~~

Ví dụ kém:

~~~java
/**
 * Gets roles.
 */
public List<String> roles() {
    return roles;
}
~~~

Từ “Gets” không giải thích được giá trị trả về là snapshot hay view, có thể sửa hay không, hoặc có chứa những role nào. Một câu tóm tắt tốt nên nêu hành vi có ý nghĩa đối với caller.

Trong JDK 17, `{@summary ...}` có thể xác định rõ phần summary nếu không muốn standard doclet dùng câu đầu tiên. Tuy nhiên, câu đầu tiên rõ ràng vẫn là lựa chọn dễ đọc nhất cho phần lớn API.

## 2. Javadoc cho record

Record là kiểu dữ liệu phù hợp để biểu diễn một nhóm giá trị có cấu trúc cố định. Mỗi thành phần được khai báo ngay trong record header:

~~~java
public record CustomerId(String value) {
}
~~~

Compiler tạo các thành viên tương ứng:

- Một field `private final` cho mỗi component.
- Một accessor public có tên giống component, ví dụ `value()`.
- Canonical constructor nhận các component theo đúng thứ tự khai báo.
- Các implementation mặc định của `equals`, `hashCode` và `toString`.

Javadoc của record cần giải thích ý nghĩa của record và từng component. Trong standard doclet của JDK 17, các `@param` tag trên documentation comment của record được hiển thị thành mục **Record Components**. Các mô tả này cũng được dùng cho tham số của canonical constructor được sinh tự động.

### 2.1. Mô tả từng record component bằng @param

~~~java
import java.util.List;
import java.util.Objects;

/**
 * Represents a snapshot of a customer's public profile.
 *
 * <p>The role list is copied when the record is constructed, so changes
 * to the caller's original list are not reflected in this value.
 *
 * @param id the stable customer identifier; must not be blank
 * @param displayName the name shown to users; must not be null
 * @param roles the roles assigned to the customer; the list and its elements must not be null
 * @since 1.0
 */
public record CustomerProfile(
        String id,
        String displayName,
        List<String> roles) {

    public CustomerProfile {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");
        Objects.requireNonNull(roles, "roles");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        roles = List.copyOf(roles);
    }
}
~~~

Trong trang Javadoc được sinh, `id`, `displayName` và `roles` xuất hiện trong mục Record Components. Tên trong `@param` phải khớp chính xác với tên component trong record header; viết sai tên có thể làm Javadoc cảnh báo và khiến phần mô tả không gắn đúng component.

Mỗi component nên được mô tả theo ý nghĩa dữ liệu, miền giá trị và chính sách null. Ví dụ “the roles assigned to the customer” hữu ích hơn “the roles list”, vì nó nói rõ dữ liệu đại diện cho điều gì.

### 2.2. Record là shallowly immutable

Record có các component field `final`, nhưng điều đó không tự làm cho object được tham chiếu trở thành immutable. Ví dụ:

~~~java
public record Settings(List<String> allowedHosts) {
}
~~~

Caller vẫn có thể truyền vào một `ArrayList` rồi sửa list đó sau khi tạo record. Record tiếp tục giữ tham chiếu đến cùng list. Nếu API muốn snapshot cấu trúc, cần defensive copy:

~~~java
public record Settings(List<String> allowedHosts) {
    public Settings {
        allowedHosts = List.copyOf(allowedHosts);
    }
}
~~~

Javadoc cần nói rõ chính sách này. Nếu list được sao chép nông, các object mutable bên trong list vẫn có thể được chia sẻ. Không nên mô tả kết quả là “deeply immutable” nếu chỉ gọi `List.copyOf`.

Ví dụ mô tả chính xác:

~~~java
/**
 * Represents a set of runtime settings.
 *
 * <p>The constructor makes an unmodifiable shallow copy of
 * {@code allowedHosts}. The elements are not cloned.
 *
 * @param allowedHosts host names accepted by the application
 */
public record Settings(List<String> allowedHosts) {
    public Settings {
        allowedHosts = List.copyOf(allowedHosts);
    }
}
~~~

Với `String`, chia sẻ phần tử là an toàn vì `String` immutable. Nếu component là `List<MutableType>`, cần cân nhắc sao chép từng phần tử hoặc công khai rõ việc chia sẻ reference.

### 2.3. Mô tả canonical constructor

Nếu record có compact canonical constructor để kiểm tra hoặc chuẩn hóa dữ liệu, có thể viết Javadoc trực tiếp cho constructor:

~~~java
/**
 * Creates a customer profile after validating and copying its values.
 *
 * @param id the stable customer identifier
 * @param displayName the display name
 * @param roles the roles to copy into the profile; the list and its elements must not be null
 * @throws NullPointerException if an argument or a role element is null
 * @throws IllegalArgumentException if {@code id} is blank
 */
public CustomerProfile {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(displayName, "displayName");
    Objects.requireNonNull(roles, "roles");
    if (id.isBlank()) {
        throw new IllegalArgumentException("id must not be blank");
    }
    roles = List.copyOf(roles);
}
~~~

Khi viết documentation cho record type và canonical constructor, tránh lặp lại nội dung một cách máy móc. Comment trên record nên giải thích ý nghĩa tổng thể và components; comment trên constructor nên tập trung vào validation, normalization, copy và các ngoại lệ mà caller có thể gặp.

### 2.4. Accessor mặc định và accessor tùy chỉnh

Javadoc của accessor được compiler tạo tự động sẽ mô tả nó trả về giá trị record component. Nếu accessor có hành vi đặc biệt, ví dụ trả defensive copy hoặc tính toán một dạng biểu diễn khác, hãy khai báo và viết Javadoc riêng:

~~~java
public record Report(List<String> lines) {
    public Report {
        lines = List.copyOf(lines);
    }

    /**
     * Returns the report lines in their original order.
     *
     * @return an unmodifiable list of report lines
     */
    public List<String> lines() {
        return lines;
    }
}
~~~

Chỉ thêm accessor tùy chỉnh khi cần thay đổi hoặc làm rõ hành vi. Với accessor mặc định đơn giản, mô tả component ở record declaration thường đã đủ.

## 3. Javadoc cho sealed class và sealed interface

Sealed class/interface giới hạn những kiểu có thể trực tiếp kế thừa hoặc implement nó. Từ Java 17, sealed classes là tính năng ngôn ngữ chính thức, không cần preview flag.

Ví dụ:

~~~java
/**
 * A geometric shape whose direct implementations are controlled by this API.
 *
 * <p>Use the permitted types to represent supported shape categories.
 */
public sealed interface Shape
        permits Circle, Rectangle, Polygon {

    double area();
}
~~~

Mỗi permitted subtype phải trực tiếp extend/implement sealed type và tiếp tục chính sách sealing bằng đúng một trong ba modifier:

- `final`: không cho subtype tiếp tục kế thừa.
- `sealed`: giới hạn tiếp các subtype được phép.
- `non-sealed`: mở lại khả năng kế thừa cho các kiểu khác.

Một record là implicitly final, vì vậy có thể là permitted subtype mà không cần viết thêm `final`.

Mọi permitted subtype phải nằm trong cùng named module với sealed type. Nếu sealed type thuộc unnamed module, các permitted subtype phải nằm trong cùng package. Khi tất cả subtype được khai báo trong cùng compilation unit, có thể bỏ mệnh đề `permits` để compiler suy ra danh sách; Javadoc vẫn có thể trình bày danh sách subtype được phép.

### 3.1. Javadoc tự tạo mục Permitted Subclasses

Standard doclet của JDK 17 nhận biết sealed type và tạo mục **Permitted Subclasses** trong trang tài liệu. Danh sách được lấy từ cấu trúc sealed type trong source/class metadata.

`permits` là **mệnh đề trong cú pháp Java**, không phải block tag Javadoc. JDK 17 standard doclet không định nghĩa tag chuẩn `@permits`. Không nên viết `@permits` rồi giả định nó tự được xử lý như `@param` hoặc `@throws`.

Ví dụ cách viết phù hợp:

~~~java
/**
 * Describes a supported payment method.
 *
 * <p>The API currently supports card payments and bank transfers.
 * Each permitted subtype defines its own payment data and validation rules.
 *
 * @see CardPayment
 * @see BankTransfer
 * @since 1.0
 */
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}
~~~

Mục Permitted Subclasses do doclet tạo sẽ liệt kê `CardPayment` và `BankTransfer`; phần mô tả chính giải thích ý nghĩa nghiệp vụ của hierarchy. Dùng `@see` hoặc `{@link ...}` để liên kết tới subtype có mô tả chi tiết.

### 3.2. Mỗi permitted subtype cũng cần tài liệu riêng

~~~java
/**
 * Represents a payment made with a card token.
 *
 * <p>The token is an opaque reference managed by the payment provider.
 *
 * @param token the provider-issued token; must not be blank
 * @param amount the amount to charge; must be positive
 * @see PaymentMethod
 */
public record CardPayment(String token, BigDecimal amount)
        implements PaymentMethod {

    public CardPayment {
        Objects.requireNonNull(token, "token");
        Objects.requireNonNull(amount, "amount");
        if (token.isBlank()) {
            throw new IllegalArgumentException("token must not be blank");
        }
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

~~~java
/**
 * Represents a payment collected from a bank account.
 *
 * @param iban the account identifier accepted by the payment provider
 * @param amount the amount to collect; must be positive
 * @see PaymentMethod
 */
public record BankTransfer(String iban, BigDecimal amount)
        implements PaymentMethod {
}
~~~

Mỗi subtype nên nói rõ:

- Nó đại diện cho biến thể nào trong domain.
- Những invariant hoặc giới hạn riêng.
- Dữ liệu bổ sung so với sealed parent.
- Hành vi nào được kế thừa và hành vi nào có semantics riêng.

Đừng chỉ dựa vào danh sách permitted subclasses trên trang parent. Người đọc có thể mở trực tiếp trang subtype từ IDE hoặc API browser.

### 3.3. Sealed hierarchy nhiều tầng

Một permitted subtype có thể tiếp tục là sealed:

~~~java
/**
 * Represents a polygonal shape.
 *
 * <p>Only triangle and quadrilateral shapes are supported by this branch.
 */
public sealed interface Polygon extends Shape
        permits Triangle, Quadrilateral {
}
~~~

Subtype cuối cùng có thể là `final` record:

~~~java
/**
 * A triangle defined by its three side lengths.
 *
 * @param a the first side length; must be positive
 * @param b the second side length; must be positive
 * @param c the third side length; must be positive
 */
public record Triangle(double a, double b, double c)
        implements Polygon {
}
~~~

Trang Javadoc của `Shape` liệt kê subtype trực tiếp; trang `Polygon` tiếp tục liệt kê `Triangle` và `Quadrilateral`. Mô tả hierarchy theo từng cấp giúp người đọc hiểu ranh giới mở rộng và trách nhiệm của mỗi nhánh.

### 3.4. Vì sao sealed hierarchy là một phần của hợp đồng API?

Danh sách permitted subtype kiểm soát khả năng mở rộng của API. Khi thay đổi danh sách này, cần cân nhắc ảnh hưởng tới:

- Code client đang giả định tập biến thể hiện có.
- Serialization hoặc mapping dữ liệu theo subtype.
- Các thư viện plugin và integration.
- Logic xử lý exhaustive trong ứng dụng.
- Khả năng tương thích source/binary khi thay đổi hierarchy.

Trong Java 17, pattern matching `switch` vẫn là preview feature. Khi viết tài liệu cho Java 17, không nên trình bày pattern switch như một tính năng đã ổn định. Có thể giải thích sealed hierarchy giúp caller biết tập subtype được phép và hỗ trợ phân tích exhaustive ở các công cụ/ngôn ngữ phù hợp, nhưng phải nêu rõ nếu ví dụ dùng preview feature.

## 4. Viết hợp đồng API rõ ràng

Hợp đồng API mô tả những điều caller được phép kỳ vọng và những điều implementation phải tuân thủ. Một method public không nên chỉ ghi “Processes data” hoặc “Gets value”; hãy mô tả hành vi quan sát được.

Các khía cạnh thường cần làm rõ:

| Khía cạnh | Câu hỏi cần trả lời |
| --- | --- |
| Input | Tham số nào bắt buộc? Miền giá trị hợp lệ là gì? Có chấp nhận null không? |
| Output | Kết quả biểu diễn gì? Có thể null hoặc empty không? |
| Mutation | Method có sửa đối tượng đầu vào hoặc trạng thái receiver không? |
| Ownership | Collection/array trả về là bản sao, view hay reference nội bộ? Ai được sửa? |
| Ordering | Thứ tự có được bảo đảm không? |
| Exceptions | Điều kiện cụ thể nào làm phát sinh exception? |
| Side effects | Có ghi file, gọi mạng, cập nhật database hoặc phát event không? |
| Concurrency | Có thread-safe không? Caller cần đồng bộ thế nào? |
| Lifecycle | Có cần đóng resource hoặc gọi method theo thứ tự nhất định không? |
| Compatibility | API có từ phiên bản nào? Có deprecated hoặc dự kiến loại bỏ không? |

Không phải method nào cũng cần mô tả mọi khía cạnh. Chỉ ghi những điều có ảnh hưởng tới cách caller sử dụng API, và tránh biến một chi tiết triển khai hiện tại thành cam kết lâu dài nếu API không muốn bảo đảm điều đó.

### 4.1. @param

`@param` mô tả từng tham số theo tên khai báo:

~~~java
/**
 * Finds an active customer by its identifier.
 *
 * @param customerId the stable identifier to search for; must not be blank
 */
public Optional<Customer> findActiveCustomer(String customerId) {
    // ...
}
~~~

Với generic type, mô tả type parameter bằng tên đặt trong dấu ngoặc nhọn:

~~~java
/**
 * Stores values under unique keys.
 *
 * @param <K> the key type
 * @param <V> the value type
 */
public interface Store<K, V> {
}
~~~

Mô tả tham số nên nêu rõ:

- Ý nghĩa nghiệp vụ.
- Đơn vị đo nếu là số lượng, thời gian hoặc tiền tệ.
- Miền giá trị hợp lệ.
- Quy tắc null.
- Collection có được đọc ngay hay giữ reference để sử dụng sau.

Không cần lặp lại kiểu dữ liệu đã hiện trong signature. Thay vì `@param count an int`, hãy mô tả `@param count the maximum number of records to return; must be positive`.

### 4.2. @return

`@return` mô tả ý nghĩa và điều kiện của giá trị trả về:

~~~java
/**
 * Finds an active customer by its identifier.
 *
 * @param customerId the stable identifier to search for
 * @return the matching customer, or an empty result if no active customer exists
 */
public Optional<Customer> findActiveCustomer(String customerId) {
    // ...
}
~~~

Không viết `@return the customer` nếu thực tế method trả `Optional<Customer>` và caller cần hiểu điều gì xảy ra khi không tìm thấy. Nếu method trả collection, nói rõ có thể empty không, có giữ thứ tự không và caller có thể sửa không.

### 4.3. @throws

`@throws` cần nêu điều kiện gây lỗi:

~~~java
/**
 * Parses an ISO date.
 *
 * @param text the date in ISO-8601 format
 * @return the parsed date
 * @throws NullPointerException if {@code text} is null
 * @throws DateTimeParseException if {@code text} is not a valid ISO date
 */
public LocalDate parseDate(String text) {
    return LocalDate.parse(text);
}
~~~

Không chỉ liệt kê tên exception. Caller cần biết điều kiện nào làm method ném lỗi để có thể validate hoặc xử lý phù hợp. Có thể mô tả cả unchecked exception nếu nó là phần quan trọng của hợp đồng.

### 4.4. @since

`@since` ghi phiên bản API xuất hiện:

~~~java
/**
 * Returns the immutable customer snapshot.
 *
 * @since 2.1
 */
public CustomerSnapshot snapshot() {
    // ...
}
~~~

Đối với thư viện có version riêng, dùng phiên bản thư viện, ví dụ `2.1`. Không mặc định ghi `@since 17` chỉ vì code biên dịch bằng Java 17; chỉ ghi số phiên bản Java nếu API thực sự gắn với phiên bản nền tảng đó.

### 4.5. @deprecated và annotation Deprecated

Khi API không nên được dùng nữa, kết hợp annotation với Javadoc:

~~~java
/**
 * Loads a customer using the legacy identifier format.
 *
 * @deprecated since 2.0; use {@link #findCustomer(CustomerId)} instead
 */
@Deprecated(since = "2.0", forRemoval = false)
public Customer findCustomer(String legacyId) {
    // ...
}
~~~

`@deprecated` giải thích lý do và hướng thay thế; `@Deprecated` đánh dấu trong metadata để compiler và IDE có thể cảnh báo. Nếu API dự kiến bị loại bỏ ở bản sau, có thể đặt `forRemoval = true` khi quyết định đó đã được công bố.

## 5. Các tag Javadoc hữu ích khác

| Tag | Mục đích | Ví dụ |
| --- | --- | --- |
| `@see` | Tạo mục See Also tới API liên quan. | `@see CustomerId` |
| `{@link ...}` | Tạo liên kết trong câu, thường hiển thị tên code. | `Use {@link #close()} before shutdown.` |
| `{@linkplain ...}` | Tạo liên kết với nhãn văn bản thường. | `See {@linkplain #close() the close operation}.` |
| `{@code ...}` | Hiển thị code mà không parse HTML/Javadoc bên trong. | `{@code null}` |
| `{@literal ...}` | Hiển thị literal, không diễn giải markup. | `{@literal <T>}` |
| `{@inheritDoc}` | Kế thừa mô tả method từ method được override/implement. | `{@inheritDoc}` |
| `{@summary ...}` | Chỉ định rõ câu summary. | `{@summary Returns a stable identifier.}` |
| `@hidden` | Ẩn một element khỏi generated API docs. | Dùng có chủ đích cho API không công khai. |
| `@author` | Ghi tác giả khi bật tùy chọn tương ứng. | `@author API Team` |

`@param`, `@return` và `@throws` giúp tài liệu có cấu trúc để IDE và công cụ khác trình bày riêng từng mục. `{@link}` hữu ích hơn việc viết tên class như văn bản thường vì người đọc có thể mở trực tiếp API liên quan.

### 5.1. Dùng @inheritDoc cho method override

Khi triển khai interface hoặc override superclass, có thể kế thừa hợp đồng đã viết ở cấp trên:

~~~java
public interface CustomerRepository {
    /**
     * Finds a customer by identifier.
     *
     * @param id the stable customer identifier
     * @return the customer, or empty if no matching customer exists
     */
    Optional<Customer> find(CustomerId id);
}

public final class SqlCustomerRepository implements CustomerRepository {
    /**
     * {@inheritDoc}
     */
    @Override
    public Optional<Customer> find(CustomerId id) {
        // ...
    }
}
~~~

Standard doclet có thể kế thừa phần mô tả, `@param`, `@return` và `@throws` của method được override hoặc implement. Nếu implementation có thêm điều kiện, side effect hoặc hạn chế cụ thể, hãy bổ sung chúng sau `{@inheritDoc}`. Không dùng `{@inheritDoc}` cho constructor hoặc field vì các declaration này không kế thừa Javadoc theo cơ chế method inheritance.

## 6. @apiNote, @implSpec và @implNote trong JDK 17

Javadoc của Java SE thường có các heading:

- **API Note:** ghi chú, ví dụ hoặc lý do hữu ích cho người dùng API.
- **Implementation Requirements:** mô tả yêu cầu đối với implementation mặc định hoặc implementation có thể override.
- **Implementation Note:** chi tiết triển khai của một implementation cụ thể.

Các tên `@apiNote`, `@implSpec` và `@implNote` thường xuất hiện trong tài liệu JDK. Tuy nhiên, trong JDK 17, chúng **không nằm trong danh sách standard block tags** của standard doclet. Bản build tài liệu OpenJDK đăng ký chúng như custom tags qua tùy chọn `-tag`.

Nếu muốn dùng các heading này trong dự án riêng, phải cấu hình Javadoc:

~~~shell
javadoc ^
  -tag 'apiNote:a:API Note:' ^
  -tag 'implSpec:a:Implementation Requirements:' ^
  -tag 'implNote:a:Implementation Note:' ^
  -d docs ^
  -sourcepath src ^
  com.example.api
~~~

Trên Windows Command Prompt, dấu `^` dùng để xuống dòng. Trong PowerShell có thể dùng backtick hoặc viết thành một dòng. Cú pháp `-tag name:locations:heading` cho phép chỉ định vị trí áp dụng và heading được hiển thị; `a` nghĩa là áp dụng cho mọi vị trí hợp lệ.

Nếu không đăng ký các tag này, Javadoc có thể báo unknown tag. Một custom `Taglet` cũng có thể được viết và truyền qua `-taglet`/`-tagletpath` khi cần xử lý nâng cao.

### 6.1. Phân biệt hợp đồng và ghi chú triển khai

Ví dụ:

~~~java
/**
 * Returns an unmodifiable view of the configured endpoints.
 *
 * @apiNote Callers should retain the returned view only while this
 *          configuration remains active.
 * @implSpec The default implementation delegates to the configuration
 *           object and does not make a defensive copy.
 * @implNote This implementation stores endpoints in a LinkedHashMap.
 */
public Map<String, URI> endpoints() {
    // ...
}
~~~

Đây là ví dụ minh họa cách phân loại nội dung khi dự án đã đăng ký custom tags. Với API công khai, hãy đưa những cam kết bắt buộc vào mô tả chính. Không để một điều kiện quan trọng như “caller không được sửa map” chỉ xuất hiện trong ghi chú triển khai.

`@implNote` thường nói về chi tiết có thể thay đổi theo implementation hoặc phiên bản. Caller không nên dựa vào nó như một bảo đảm phổ quát. `@implSpec` phù hợp khi cần mô tả yêu cầu của implementation mặc định hoặc cách một method có thể được override. `@apiNote` cung cấp ngữ cảnh bổ sung cho người dùng API, không thay thế mô tả hợp đồng.

## 7. Viết hợp đồng cho collection và dữ liệu mutable

Các method trả `List`, `Set`, `Map` hoặc array nên nói rõ caller có thể sửa kết quả hay không và kết quả có phản ánh thay đổi của nguồn không.

Ví dụ hợp đồng rõ:

~~~java
/**
 * Returns an unmodifiable snapshot of the configured roles.
 *
 * <p>The returned list preserves the configured order and does not reflect
 * later changes to this configuration.
 *
 * @return an unmodifiable list containing the roles at the time of the call
 */
public List<String> roles() {
    return List.copyOf(roles);
}
~~~

Ví dụ khác nếu API trả view:

~~~java
/**
 * Returns an unmodifiable view of the current role mapping.
 *
 * <p>Changes made through this object's update methods are visible in the
 * returned view. The caller cannot modify the mapping through the view.
 *
 * @return an unmodifiable view backed by this configuration
 */
public Map<String, Role> roleView() {
    return Collections.unmodifiableMap(roles);
}
~~~

Hai hợp đồng này khác nhau rõ ràng:

| Cách trả về | Caller sửa qua kết quả | Nguồn thay đổi sau lời gọi |
| --- | --- | --- |
| Snapshot không thể sửa | Không | Không phản ánh thay đổi cấu trúc tiếp theo của nguồn mutable. |
| Unmodifiable view | Không | View phản ánh thay đổi từ nguồn backing collection. |
| Mutable copy | Có | Thay đổi kết quả không tác động nguồn nếu đã copy cấu trúc. |
| Reference trực tiếp tới collection mutable | Có thể | Caller và owner cùng nhìn thấy thay đổi. |

Nếu API trả object mutable, hãy ghi rõ quyền sở hữu, thời điểm dữ liệu được đọc và cách đồng bộ. Câu “returns a list of roles” chưa đủ để caller biết liệu có thể giữ list qua nhiều lần cập nhật hay không.

## 8. Hợp đồng cho thread safety và side effects

Một API có thể đúng về kiểu dữ liệu nhưng vẫn gây hiểu nhầm nếu tài liệu không nói về đồng thời và side effects.

Ví dụ method thread-safe:

~~~java
/**
 * Adds a role to this account.
 *
 * <p>This operation is thread-safe. Concurrent calls are serialized by
 * the account implementation.
 *
 * @param role the role to add; must not be null
 * @return {@code true} if the role was added, or {@code false} if it
 *         was already present
 * @throws NullPointerException if {@code role} is null
 */
public boolean addRole(Role role) {
    // ...
}
~~~

Chỉ ghi “thread-safe” khi đó là cam kết thực sự. Nếu caller phải tự đồng bộ, hãy nêu rõ phạm vi khóa hoặc quy tắc truy cập đồng thời.

Với side effect:

~~~java
/**
 * Persists the account and commits the current transaction.
 *
 * @throws SQLException if the database operation fails
 */
public void save() throws SQLException {
    // ...
}
~~~

Nếu method thực hiện I/O, cập nhật trạng thái, phát event, tiêu thụ stream hoặc đóng resource, tài liệu nên nêu tác động mà caller cần biết. Không nên che giấu việc method có side effect sau một tên chung như `process()`.

## 9. Tài liệu cho sealed hierarchy và record cùng nhau

Một API domain có thể dùng sealed interface làm gốc và record làm các biến thể dữ liệu. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

/**
 * Represents a command that can be submitted to the billing service.
 *
 * <p>The supported command variants are listed in the permitted
 * subclasses section.
 *
 * @see Charge
 * @see Refund
 * @since 1.0
 */
public sealed interface BillingCommand permits Charge, Refund {
    BigDecimal amount();
}

/**
 * Requests a new charge.
 *
 * @param amount the amount to charge; must be positive
 * @param reference the external reference; must not be blank
 */
public record Charge(BigDecimal amount, String reference)
        implements BillingCommand {

    public Charge {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(reference, "reference");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (reference.isBlank()) {
            throw new IllegalArgumentException("reference must not be blank");
        }
    }
}

/**
 * Requests a refund for a previous charge.
 *
 * @param amount the amount to refund; must be positive
 * @param originalReference the reference of the original charge
 */
public record Refund(BigDecimal amount, String originalReference)
        implements BillingCommand {
}
~~~

Ví dụ này minh họa cách chia trách nhiệm:

- `BillingCommand` giải thích khái niệm chung và liên kết tới các biến thể.
- Javadoc tự sinh liệt kê permitted subclasses.
- `Charge` và `Refund` giải thích semantics riêng và dùng `@param` cho record components.
- Constructor ghi rõ validation và exception khi đó là phần caller cần dựa vào.

Trong dự án thật, mỗi public top-level type thường nằm trong file riêng. Các đoạn trên được ghép trong cùng một ví dụ để dễ đọc; hãy tách file theo quy tắc Java khi biên dịch.

## 10. Tài liệu package và module

Javadoc không chỉ dành cho class và method. Có thể viết:

### 10.1. package-info.java

`package-info.java` mô tả mục đích và quy ước chung của package:

~~~java
/**
 * Provides public billing commands and result types.
 *
 * <p>All monetary values use {@link java.math.BigDecimal}. Public command
 * records validate their required fields during construction.
 *
 * @since 1.0
 */
package com.example.billing.api;
~~~

Tài liệu package hữu ích để giải thích:

- Phạm vi trách nhiệm của package.
- Quy tắc naming hoặc validation chung.
- Quy ước nullability và ownership.
- Quan hệ giữa các type chính.
- Cách sử dụng package theo workflow.

### 10.2. module-info.java

Với ứng dụng modular, có thể đặt Javadoc trước module declaration:

~~~java
/**
 * Defines the public billing API.
 *
 * <p>The module exports the API package and uses the configured payment
 * provider service.
 *
 * @uses com.example.billing.spi.PaymentProvider
 */
module com.example.billing.api {
    exports com.example.billing.api;
    uses com.example.billing.spi.PaymentProvider;
}
~~~

Các tag `@uses` và `@provides` được standard doclet hỗ trợ cho module documentation, giúp mô tả service mà module sử dụng hoặc cung cấp. Tài liệu module nên giải thích vai trò của module, package được export và service boundary mà người tích hợp cần biết.

## 11. Chạy Javadoc với JDK 17

Giả sử source tree:

~~~text
src/
  com/example/billing/api/
    package-info.java
    BillingCommand.java
    Charge.java
    Refund.java
~~~

Có thể sinh tài liệu:

~~~shell
javadoc --release 17 ^
  -encoding UTF-8 ^
  -Xdoclint:all ^
  -Werror ^
  -d build/docs ^
  -sourcepath src ^
  -tag 'apiNote:a:API Note:' ^
  -tag 'implSpec:a:Implementation Requirements:' ^
  -tag 'implNote:a:Implementation Note:' ^
  -subpackages com.example.billing.api
~~~

Lệnh trên viết theo kiểu xuống dòng của Windows Command Prompt với dấu `^`. Trong PowerShell có thể dùng backtick hoặc viết thành một dòng.

Ý nghĩa các tùy chọn:

| Tùy chọn | Công dụng |
| --- | --- |
| `--release 17` | Dùng API/platform release 17 khi phân tích source. |
| `-encoding UTF-8` | Đọc source documentation theo UTF-8. |
| `-Xdoclint:all` | Bật kiểm tra doc comment và HTML ở các nhóm kiểm tra. |
| `-Werror` | Kết thúc với lỗi nếu có warning. |
| `-d build/docs` | Thư mục chứa HTML được sinh. |
| `-sourcepath src` | Vị trí source packages. |
| `-tag ...` | Đăng ký custom tags như API Note/Implementation Requirements. |
| `-subpackages ...` | Sinh tài liệu cho package và subpackages được chỉ định. |

Với project modular, có thể dùng `--module-source-path` và `--module` theo cấu trúc source module:

~~~shell
javadoc --release 17 ^
  --module-source-path src ^
  --module com.example.billing.api ^
  -d build/docs ^
  -Xdoclint:all
~~~

Tùy cấu trúc project, cần bổ sung module path hoặc module nguồn phụ thuộc phù hợp. Hãy xem `javadoc --help` và `javadoc --help-extra` của JDK 17 đang dùng để xác nhận tùy chọn.

## 12. Doclint và lỗi thường gặp

Doclint giúp phát hiện lỗi trong documentation comments trước khi xuất bản. Một số vấn đề phổ biến:

| Vấn đề | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Thiếu `@param` cho method public | Người đọc không biết ý nghĩa tham số; doclint có thể cảnh báo. | Mô tả từng tham số bằng đúng tên trong signature. |
| Thiếu `@return` cho method non-void | Không rõ kết quả biểu diễn gì. | Nêu nội dung, null/empty semantics và mutability. |
| `@throws` không nêu điều kiện | Caller không biết khi nào cần xử lý exception. | Ghi rõ điều kiện gây lỗi. |
| Tên `@param` sai | Tag không gắn được với tham số/component. | Đồng bộ tên tag với source declaration. |
| Dùng `@permits` như tag chuẩn | Standard doclet JDK 17 không định nghĩa tag này. | Dùng `permits` trong source; mô tả subtype bằng main description và `@see`. |
| Dùng `@apiNote` mà không cấu hình | Javadoc có thể báo unknown tag. | Đăng ký bằng `-tag` hoặc cung cấp Taglet. |
| HTML không hợp lệ | Trang generated docs có thể hiển thị sai hoặc doclint cảnh báo. | Dùng HTML5 hợp lệ và đóng tag đúng. |
| Câu đầu quá dài hoặc mơ hồ | Summary/index khó đọc và khó tìm kiếm. | Viết câu đầu ngắn, mô tả hành vi cốt lõi. |
| Copy Javadoc của superclass nhưng không dùng `{@inheritDoc}` | Tài liệu dễ lệch khi hợp đồng cha thay đổi. | Kế thừa phần chung và bổ sung khác biệt thực tế. |
| Đưa chi tiết triển khai vào main contract | Caller có thể phụ thuộc nhầm vào hành vi không được bảo đảm. | Phân biệt hợp đồng công khai với ghi chú implementation. |

## 13. Checklist viết Javadoc cho public API

Trước khi công bố API, hãy kiểm tra:

1. Câu summary có nói đúng mục đích của type/method không?
2. Record có mô tả đầy đủ mọi component bằng `@param` không?
3. Record có nói rõ null policy, validation và defensive copy không?
4. Sealed type có giải thích khái niệm chung và vai trò của các permitted subtype không?
5. Mỗi permitted subtype có trang Javadoc riêng và liên kết ngược tới parent không?
6. Method có mô tả input, return, exception và side effects không?
7. Collection/array có nói rõ thứ tự, mutability và snapshot/view semantics không?
8. Thread-safety và concurrency assumptions có được ghi khi caller cần biết không?
9. `@since`, `@deprecated`, `@see` và `{@link}` có dùng đúng nơi không?
10. Các custom tags có được đăng ký trong lệnh Javadoc của dự án không?
11. `javadoc -Xdoclint:all -Werror` có chạy thành công trong build không?
12. Generated HTML có được xem lại ở trang type, component, constructor và method không?

Checklist này giúp bảo đảm tài liệu mô tả hợp đồng mà caller có thể dựa vào, đồng thời phản ánh chính xác cấu trúc mới của Java 17.

## 14. Câu hỏi thường gặp

**Record component được tài liệu hóa bằng tag nào?**  
Dùng `@param` trên Javadoc của record declaration. Standard doclet tạo mục Record Components từ các tag này.

**Có thể viết @param cho compact constructor không?**  
Có. Compact canonical constructor có các tham số tương ứng record components. Có thể mô tả validation và exception của constructor; phần ý nghĩa component tổng thể nên được ghi trên record declaration.

**Javadoc có tự tạo trang cho record accessor không?**  
Có. Accessor là method của record và được hiển thị như method. Nếu accessor mặc định, doclet có thể mô tả rằng nó trả về giá trị component; nếu accessor có hành vi đặc biệt, hãy viết Javadoc riêng.

**Sealed class có cần @permits không?**  
Không. `permits` là mệnh đề của ngôn ngữ Java, không phải tag Javadoc chuẩn JDK 17. Standard doclet tự tạo mục Permitted Subclasses.

**Làm sao giải thích ý nghĩa từng permitted subtype?**  
Viết Javadoc riêng trên subtype, dùng `@see` hoặc `{@link ...}` ở parent và mô tả vai trò nghiệp vụ trong main description.

**@apiNote, @implSpec, @implNote có dùng mặc định được không?**  
Không nên giả định như vậy. Trong JDK 17 chúng là custom tags được JDK build đăng ký; dự án riêng cần khai báo bằng `-tag` hoặc cung cấp Taglet.

**Có nên đặt điều kiện null trong @param hay @throws?**  
Nên mô tả cả hai khía cạnh: `@param` nói tham số có được phép null không; `@throws` nói exception nào phát sinh nếu caller vi phạm điều kiện.

**Có cần viết Javadoc cho mọi method private không?**  
Không nhất thiết. Ưu tiên public/protected API và những phần private có thuật toán hoặc invariant khó hiểu. Javadoc chủ yếu là hợp đồng và tài liệu cho người dùng API.

**Javadoc có kiểm tra implementation có đúng hợp đồng không?**  
Không. Javadoc sinh tài liệu và doclint kiểm tra cấu trúc comment/HTML; unit test, integration test và review mới xác minh hành vi thực thi.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): cú pháp comment, block tags, inline tags, inheritance và các tag được standard doclet hỗ trợ.
- [Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): tùy chọn sinh tài liệu, `-tag`, `-taglet`, `-Xdoclint`, `-Werror`, module path và source path.
- [Java SE 17 API — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): ngữ nghĩa record, component, canonical constructor và các method được sinh.
- [Java SE 17 Language Guide — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): cú pháp, giới hạn và cách sử dụng record.
- [Java SE 17 Language Guide — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): `sealed`, `permits`, `final`, `sealed`, `non-sealed` và các ràng buộc subtype.
- [Java SE 17 API — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): metadata runtime của permitted subclasses.
- [Java SE 17 API — jdk.javadoc.doclet.Taglet](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.javadoc/jdk/javadoc/doclet/Taglet.html): API tạo custom Javadoc taglet.
- [Oracle — How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html): hướng dẫn thực hành viết documentation comments và các tag cơ bản.

**Nguyên tắc áp dụng:** Dùng `@param` để tài liệu hóa record components; mô tả sealed hierarchy bằng phần giải thích và liên kết tới subtype, đồng thời tận dụng mục Permitted Subclasses do standard doclet tạo; viết hợp đồng API bằng mô tả chính cùng `@param`, `@return`, `@throws`, `@since` và `@deprecated`. Chỉ dùng `@apiNote`, `@implSpec`, `@implNote` khi build đã đăng ký các custom tags này.
