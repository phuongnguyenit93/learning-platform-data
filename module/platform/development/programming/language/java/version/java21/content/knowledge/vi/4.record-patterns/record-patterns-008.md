# Xử lý record có giá trị null và component có thể null

Record pattern trong Java 21 giúp kiểm tra kiểu record và lấy các component trong cùng một biểu thức. Tuy nhiên, record pattern không tự làm cho dữ liệu trở nên non-null. Một đối tượng record có thể là `null`, từng component kiểu tham chiếu cũng có thể là `null`, và một component lại có thể chứa record khác với component tiếp tục bị `null`.

Để dùng record pattern an toàn, cần phân biệt giá trị `null` của chính record với giá trị `null` bên trong record. Java 21 đã chuẩn hóa record patterns và pattern matching for `switch`, vì vậy các ví dụ dưới đây dùng cú pháp chính thức, không cần bật preview feature.

## 1. Hai vị trí có thể xuất hiện null

Xét hai record lồng nhau:

```java
record Address(String city) {}

record Person(String name, Address address) {}
```

Java không tự áp đặt ràng buộc non-null lên component kiểu tham chiếu. Nếu constructor không kiểm tra, cả ba trường hợp sau đều hợp lệ:

```java
Person missingPerson = null;
Person missingAddress = new Person("An", null);
Person missingCity = new Person("An", new Address(null));
```

| Dữ liệu | Giá trị null | Ý nghĩa |
|---|---|---|
| `missingPerson` | Chính đối tượng `Person` | Không có đối tượng record để phân rã. |
| `missingAddress` | Component `address` | Có `Person`, nhưng không có `Address`. |
| `missingCity` | Component `city` của `Address` | Có cả `Person` và `Address`, nhưng chưa có tên thành phố. |

Record pattern xử lý từng tầng theo quy tắc riêng. Không nên giả định rằng kiểm tra được record bên ngoài đồng nghĩa mọi component bên trong đều khác `null`.

## 2. Quy tắc null của record pattern trong Java 21

Quy tắc quan trọng nhất là: **một record pattern không bao giờ khớp với giá trị `null` của chính record đang được kiểm tra**. Ví dụ:

```java
Person person = null;

if (person instanceof Person(var name, var address)) {
    // Không chạy: person là null.
}
```

Biểu thức `instanceof` trả về `false` khi toán hạng là `null`; nó không ném `NullPointerException` chỉ vì phép kiểm tra này.

Đối với component, quy tắc tinh tế hơn. Một type pattern nằm trực tiếp trong danh sách component sẽ khớp với `null` nếu pattern đó là *unconditional* đối với kiểu khai báo của component. Ví dụ, với component khai báo là `String`, cả `String name` và `var name` đều có thể nhận giá trị `null`:

```java
Person person = new Person(null, null);

if (person instanceof Person(String name, var address)) {
    // Pattern khớp.
    // name == null và address == null.
}
```

Điều này không có nghĩa mọi type pattern đều khớp `null`. Nếu component được khai báo là `Object`, pattern `String value` là pattern hẹp hơn kiểu component; nó không khớp khi giá trị component là `null`.

```java
record Envelope(Object value) {}

Envelope envelope = new Envelope(null);

boolean broadPattern = envelope instanceof Envelope(Object value);
// true: Object là kiểu rộng, unconditional đối với component Object.

boolean narrowPattern = envelope instanceof Envelope(String value);
// false: String không unconditional đối với component Object.
```

Các trường hợp thường gặp có thể tóm tắt như sau:

| Pattern | Khi giá trị tương ứng là null |
|---|---|
| Record pattern bên ngoài, ví dụ `Person(...)` | Không khớp. |
| Nested record pattern, ví dụ `Address(...)` | Không khớp nếu component `address` là null. |
| `var value` đặt trực tiếp trong danh sách component | Khớp và biến `value` nhận null. |
| Type pattern unconditional với kiểu component, ví dụ `String s` cho component khai báo `String` | Khớp và biến `s` nhận null. |
| Type pattern hẹp hơn kiểu component, ví dụ `String s` cho component khai báo `Object` | Không khớp. |

Vì vậy, việc một record pattern khớp không đảm bảo các biến được lấy ra đều non-null. Nếu code cần gọi phương thức trên một component, hãy kiểm tra null riêng hoặc dùng guard trước khi sử dụng.

Khi phân rã, Java lấy giá trị component bằng cách gọi accessor tương ứng của record. Nếu một accessor được tùy biến và ném exception, quá trình pattern matching có thể kết thúc bằng `MatchException` với exception gốc làm nguyên nhân. Đây là lỗi trong quá trình lấy component, khác với trường hợp component trả về `null` bình thường.

## 3. Kiểm tra record bằng instanceof

Khi dùng `instanceof`, hãy xem phép kiểm tra record bên ngoài và giá trị của từng component là hai việc khác nhau.

### Lấy component mà không giả định non-null

`var` trong danh sách component suy luận kiểu từ khai báo record và có thể nhận `null`:

```java
static String describe(Object value) {
    if (value instanceof Person(var name, var address)) {
        String safeName = java.util.Objects.toString(name, "(không có tên)");
        String addressState = address == null
                ? "chưa có địa chỉ"
                : "đã có địa chỉ";

        return safeName + ": " + addressState;
    }

    return value == null
            ? "Không có Person"
            : "Giá trị không phải Person";
}
```

Nếu `value` là `null`, record pattern không khớp và nhánh `if` bị bỏ qua. Nếu `value` là một `Person`, pattern khớp ngay cả khi `name` hoặc `address` là `null`; do đó phần thân vẫn cần xử lý các component có thể null.

### Phân rã record lồng nhau

Có thể viết nested record pattern để chỉ đi tiếp khi component lồng bên trong tồn tại:

```java
static String cityOf(Object value) {
    if (value instanceof Person(var name, Address(var city))) {
        if (city == null) {
            return "Chưa có thành phố";
        }

        return city;
    }

    return "Không có Person hoặc Address";
}
```

Trong ví dụ này:

- `Person` phải khác `null`, nếu không pattern bên ngoài không khớp.
- `name` có thể là `null`, vì `var name` là component pattern unconditional.
- `address` phải khác `null`, vì `Address(...)` là nested record pattern và record pattern không khớp `null`.
- `city` vẫn có thể là `null`; `var city` nhận giá trị đó và cần được kiểm tra trước khi trả về hoặc gọi phương thức.

Nếu cần yêu cầu cả `name` và `city` đều có giá trị, dùng điều kiện kết hợp với `&&`:

```java
if (value instanceof Person(var name, Address(var city))
        && name != null
        && city != null) {
    return name + " sống tại " + city;
}
```

Pattern variable chỉ được dùng trong phạm vi mà pattern đã khớp. Với biểu thức `&&`, các điều kiện phía sau có thể dùng `name` và `city`; chúng đồng thời kiểm tra null trước khi phần thân được thực hiện.

## 4. Xử lý null bằng switch pattern matching

Java 21 cho phép dùng `case null` trong `switch` có selector là kiểu tham chiếu. Đây là cách rõ ràng để xử lý trường hợp chính record được truyền vào là `null`.

```java
static String describe(Person person) {
    return switch (person) {
        case null -> "Không có Person";

        case Person(var name, var address) -> {
            String safeName = java.util.Objects.toString(name, "(không có tên)");

            String addressText = switch (address) {
                case null -> "chưa có địa chỉ";
                case Address(var city) ->
                        java.util.Objects.toString(city, "chưa có thành phố");
            };

            yield safeName + ": " + addressText;
        }
    };
}
```

Switch bên ngoài xử lý hai trường hợp: `person` là `null`, hoặc là một `Person`. Trong nhánh record pattern, `var address` nhận được cả giá trị null. Switch bên trong tiếp tục phân biệt `address == null` và một `Address` tồn tại. Khi `Address` tồn tại, `var city` vẫn có thể nhận `null`, vì vậy `Objects.toString` cung cấp giá trị thay thế an toàn.

Với selector kiểu tham chiếu, nếu giá trị selector là `null` mà switch không có nhãn `case null`, Java ném `NullPointerException`. Chỉ có `default` là chưa đủ để xử lý selector null; `default` xử lý các giá trị không null còn lại. Có thể viết `case null, default` khi muốn gộp cả hai trường hợp vào cùng một nhánh.

### Dùng guard để nhận diện component null

Nếu cần tách riêng trường hợp một component null ngay trong switch, có thể dùng `when` với một pattern tổng quát:

```java
static String addressState(Person person) {
    return switch (person) {
        case null -> "Không có Person";

        case Person(var name, var address) when address == null ->
                java.util.Objects.toString(name, "(không có tên)")
                        + " chưa có địa chỉ";

        case Person(var name, Address(var city)) ->
                java.util.Objects.toString(name, "(không có tên)")
                        + " ở "
                        + java.util.Objects.toString(city, "chưa rõ thành phố");
    };
}
```

Pattern `Person(var name, var address)` khớp với mọi `Person` không null, kể cả khi `address` null. Guard `address == null` chọn nhánh cần xử lý. Nếu guard không đúng, switch tiếp tục xét nested record pattern `Address(var city)`, pattern này chỉ khớp khi `address` chứa một `Address` khác null.

Guard có từ khóa `when` là cú pháp ổn định của pattern matching for `switch` trong Java 21. Không dùng cú pháp guard preview cũ trong mã mới.

## 5. Những lỗi null thường gặp

| Cách viết hoặc tình huống | Kết quả | Cách xử lý |
|---|---|---|
| `value instanceof Person(...)` khi `value == null` | Trả về `false`. | Xử lý nhánh không khớp nếu cần phân biệt null với sai kiểu. |
| `switch (person)` không có `case null`, trong khi `person == null` | Ném `NullPointerException`, kể cả khi có `default`. | Thêm `case null` hoặc `case null, default`. |
| `Person(..., Address(...))` khi component `address == null` | Nested record pattern không khớp. | Bắt component bằng `var` rồi kiểm tra, hoặc dùng guard. |
| Pattern `Person(String name, ...)` khớp nhưng `name == null` | Hợp lệ nếu component khai báo là `String`; `name` nhận null. | Kiểm tra null trước khi gọi `name.length()`, `name.trim()` hoặc phương thức khác. |
| `Envelope(String value)` khi component `value` khai báo là `Object` và đang null | Pattern không khớp vì `String` không unconditional với `Object`. | Dùng `var` hoặc type pattern đủ rộng, sau đó kiểm tra kiểu/giá trị riêng. |
| Component lồng sâu hơn bị null | Nested record pattern ở đúng tầng đó không khớp. | Kiểm tra từng tầng hoặc phân rã từng bước. |

Java 21 không cung cấp `null` như một component pattern trong danh sách record pattern. Muốn phân biệt component null, hãy dùng component pattern có thể nhận null như `var` rồi kiểm tra bằng guard hoặc câu lệnh điều kiện. `case null` là nhãn của switch selector, không phải cú pháp để đặt trực tiếp vào từng vị trí component.

## 6. Thiết kế record với hợp đồng null rõ ràng

Record pattern giúp xử lý dữ liệu hiện có, nhưng không thay thế việc xác định hợp đồng dữ liệu. Nếu một component bắt buộc phải có giá trị, hãy xác thực ngay tại ranh giới tạo record.

```java
import java.util.Objects;

record RequiredPerson(String name, Address address) {
    RequiredPerson {
        Objects.requireNonNull(name, "name must not be null");
        Objects.requireNonNull(address, "address must not be null");
    }
}
```

Compact canonical constructor kiểm tra dữ liệu khi tạo record. Nếu truyền null cho `name` hoặc `address`, constructor ném `NullPointerException` ngay tại nơi dữ liệu đi vào hệ thống. Các đoạn xử lý sau đó có thể dựa vào hợp đồng này, miễn là mọi đường tạo đối tượng đều tuân thủ constructor.

Nếu null là trạng thái hợp lệ của nghiệp vụ, hãy thể hiện rõ điều đó trong tên component, tài liệu hoặc API và xử lý bằng pattern/guard như các ví dụ trước. Với dữ liệu có tính tùy chọn, có thể dùng `Optional<Address>` và quy ước component `Optional` bản thân nó không null:

```java
import java.util.Objects;
import java.util.Optional;

record PersonWithOptionalAddress(String name, Optional<Address> address) {
    PersonWithOptionalAddress {
        Objects.requireNonNull(address, "address must not be null");
    }
}
```

Khi đó, không có địa chỉ được biểu diễn bằng `Optional.empty()`, còn một địa chỉ tồn tại được biểu diễn bằng `Optional.of(address)`. Kiểm tra null cho chính component `Optional` vẫn cần thiết nếu muốn giữ hợp đồng nhất quán. `Optional` phù hợp khi miền nghiệp vụ thực sự có giá trị tùy chọn; không cần bọc mọi component chỉ để tránh viết kiểm tra null.

Các annotation như `@Nullable` hoặc `@NonNull` có thể bổ sung thông tin cho IDE, static analysis hoặc framework, nhưng Java 21 không tự áp đặt null-safety chỉ từ kiểu khai báo hay tên annotation. Cần biết công cụ nào đang đọc và kiểm tra các annotation đó.

## 7. Checklist khi viết record pattern có dữ liệu nullable

- [ ] Đã xác định selector của `instanceof` hoặc `switch` có thể là null hay không.
- [ ] Với switch trên kiểu tham chiếu, đã có `case null` nếu selector null là trường hợp cần xử lý.
- [ ] Đã phân biệt record pattern ngoài với nested record pattern: cả hai đều không khớp khi chính giá trị record tương ứng là null.
- [ ] Đã kiểm tra kiểu khai báo của component trước khi kết luận type pattern có khớp null hay không.
- [ ] Không giả định pattern khớp đồng nghĩa mọi pattern variable đều non-null.
- [ ] Đã dùng guard hoặc điều kiện để kiểm tra component trước khi gọi phương thức.
- [ ] Đã xác thực trong constructor đối với component bắt buộc non-null.
- [ ] Đã ghi rõ component nào được phép null theo hợp đồng dữ liệu.

## Tài liệu tham khảo

- [Record Patterns — Java Language Updates, Java SE 21](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): cách khai báo, lồng và suy luận kiểu trong record pattern; record pattern không khớp giá trị null.
- [Pattern Matching for switch Expressions and Statements — Java SE 21](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): guard `when`, pattern label và nhãn `case null`.
- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): quy tắc null-matching của type pattern trong component list, record pattern và quá trình khớp pattern.
- [Java Language Specification, Java SE 21 — §14.11.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): cách switch xác định nhãn áp dụng tại runtime.
- [MatchException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): ngoại lệ có thể xuất hiện trong quá trình pattern matching, bao gồm trường hợp accessor của record hoàn tất bất thường.
