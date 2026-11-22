# Checklist review và kiểm thử Java Pattern Matching

**Pattern matching** giúp mã Java giảm ép kiểu thủ công và trình bày các nhánh rõ hơn, nhưng cú pháp ngắn không tự bảo đảm xử lý đúng tất cả dữ liệu. Một `case` viết sai thứ tự có thể bị che; một nested record pattern có thể không khớp vì component `null`; một guard `when` có thể bỏ sót trường hợp biên; và một `default` vô tình có thể giấu việc thiếu xử lý khi thêm subtype. Vì vậy, **code review và kiểm thử Pattern Matching** cần kiểm tra **cả quy tắc compiler lẫn hành vi runtime và hợp đồng nghiệp vụ**.

Bài thuộc **Java Core Pattern Matching → Checklist pattern**, với đề mục **Checklist review và kiểm thử**. Nội dung được thiết kế để dùng khi mở hoặc duyệt một pull request (PR) có `instanceof` type pattern, record pattern, nested deconstruction, sealed hierarchy và pattern matching cho `switch`. Cuối bài có hai chương trình Java 21+ độc lập đã được kiểm chứng: một chương trình **tự chạy 11 test case runtime**, một chương trình dùng **Java Compiler API** kiểm tra hai tình huống phải bị từ chối và một đối chứng phải biên dịch thành công.

**Phiên bản:** Pattern matching for `instanceof` ổn định từ **Java 16** (JEP 394), records từ Java 16 (JEP 395), sealed classes/interfaces từ **Java 17** (JEP 409), record patterns và pattern matching for `switch` từ **Java 21** (JEP 440/441). Các ví dụ sử dụng `case Type(var ...)` và guard `when` yêu cầu **JDK 21+**, không cần bật preview.

## 1. Đọc checklist theo ba tầng

Đừng chỉ hỏi “Code có biên dịch không?”. Hãy phân biệt ba tầng kiểm chứng:

| Tầng | Câu hỏi cần trả lời | Công cụ chủ yếu |
| --- | --- | --- |
| **Biên dịch** | Cú pháp đúng target JDK? Pattern hợp lệ? Có case bị dominated hoặc switch thiếu bao phủ không? | `javac --release 21`, compiler tests |
| **Hành vi** | Dữ liệu match, không match, `null`, guard đúng/sai, nhánh fallback cho kết quả đúng? | Unit tests, parameterized tests, assertions |
| **Thiết kế và nghiệp vụ** | Invariant, quyền truy cập, side effect, trạng thái, compatibility và phạm vi thay đổi có được xử lý đúng? | Code review, integration tests, domain tests |

Compiler có thể phát hiện một số vấn đề như dominance, scope hoặc exhaustiveness. Nhưng **không tự biết** một đơn hàng rỗng phải trả mã lỗi nào, liệu guard gọi payment gateway có an toàn hay không, hoặc hai điều kiện `n > 5` và `n > 3` đang được sắp đúng theo chính sách nghiệp vụ không.

### Checklist một phút trước khi xem chi tiết

- [ ] PR chỉ rõ **JDK/build target** và các tính năng pattern mới sử dụng.
- [ ] Selector và kiểu tĩnh của selector đã rõ (`Object`, sealed type, record, v.v.).
- [ ] Dùng `instanceof` type pattern cho trường hợp đơn giản; không ép mọi kiểm tra thành một `switch` dài.
- [ ] Record pattern lấy component theo **đúng thứ tự** và đúng tên nghiệp vụ.
- [ ] Phạm vi pattern variable đúng với những đường đi đã match.
- [ ] `null` của selector và `null` của component lồng nhau được xem xét riêng.
- [ ] Case có guard/hẹp đứng trước case tổng quát; không có nhánh bị dominated.
- [ ] Với sealed `switch`, biết rõ chiến lược exhaustive và `default` có cần hay không.
- [ ] Guard là điều kiện dễ hiểu, ưu tiên thuần túy, không giấu tác dụng phụ.
- [ ] Test bao gồm ít nhất một **match**, **non-match**, **guard false** và **null** khi chúng liên quan.
- [ ] Code có thể được biên dịch và kiểm thử lại bằng công cụ tự động trong CI.

Đây là phần định hướng. Các phần sau chỉ rõ **vì sao mỗi mục cần kiểm tra** và **cách viết test tương ứng**.

## 2. Review kiểu selector và phiên bản Java trước

Một review tốt bắt đầu ở **đầu vào và công cụ**, không phải ở hình thức của nhánh `case`.

Ví dụ:

~~~java
// Java 21+, trích đoạn; 'input' có kiểu Object.
String result = switch (input) {
    case String text -> "Text";
    case Integer number -> "Number";
    case null -> "Missing";
    default -> "Other";
};
~~~

Trên `Object`, còn rất nhiều kiểu không được liệt kê nên `default` có ý nghĩa. Nếu selector là một **sealed interface** chỉ có vài subtype trực tiếp, có thể dùng các case cụ thể mà không cần `default` để compiler nhắc khi mô hình được mở rộng.

**Checklist review phiên bản:**

1. Dự án thực sự dùng JDK nào cho compiler? `java -version`, `javac -version`, Maven/Gradle toolchains và CI có đồng bộ không?
2. Mức `source/release` là bao nhiêu? `javac --release 17` không biên dịch được record patterns và pattern `switch` theo cú pháp Java 21.
3. Có dùng cú pháp preview cũ hay không? `when` trong pattern `switch` đã ổn định ở Java 21; đừng sao chép ví dụ preview của JDK cũ mà không đối chiếu.
4. Runtime triển khai có hỗ trợ **class-file version** được tạo ra không? Java 21 dùng major version 65; chạy bytecode Java 21 trên JVM 17 có thể dẫn đến `UnsupportedClassVersionError`.
5. Dependency và build plugin có yêu cầu JDK khác với target mà dự án cam kết không?

**Test gợi ý:** chạy build sạch và compiler với target được công bố; chạy unit/integration tests trên JVM tối thiểu được hỗ trợ. `--release` kiểm soát cú pháp và API Java Platform khi biên dịch, nhưng không thay thế kiểm thử runtime/dependency.

## 3. Review `instanceof` type pattern và flow scoping

Cách viết truyền thống:

~~~java
// Trích đoạn trong một phương thức có Object input.
if (input instanceof String) {
    String value = (String) input;
    System.out.println(value.trim());
}
~~~

Từ Java 16 có thể viết:

~~~java
// Java 16+, trích đoạn.
if (input instanceof String value) {
    System.out.println(value.trim());
}
~~~

**Review các điểm sau:**

- Type pattern **không match `null`**: nếu `input == null`, nhánh `if` không chạy.
- `value` chỉ hợp lệ ở nơi flow analysis chứng minh pattern đã khớp.
- Bỏ cast phải **giữ nguyên hành vi**. Không đồng thời xóa một check null, thay exception hay đổi nghiệp vụ chỉ vì cú pháp ngắn hơn.
- Tên biến `value`/`customer`/`text` giúp hiểu vai trò hơn một chữ `x` khi code dài.
- Với kiểu generic, lưu ý type erasure và các ràng buộc về loại pattern hợp lệ; không giả định có thể `instanceof List<String>` như kiểm tra đầy đủ kiểu generic tại runtime.

### Flow-scoping hợp lệ

~~~java
// Java 16+, trích đoạn trong phương thức trả String.
if (!(input instanceof String text)) {
    return "Other";
}
return text.trim();
~~~

Nhánh không match `return` sớm, vì vậy bên dưới compiler biết `text` đã được ràng buộc.

### Flow-scoping cố ý sai

~~~java
// CỐ Ý SAI: không match vẫn có thể đi tiếp.
if (!(input instanceof String text)) {
    System.out.println("Other");
}
return text.trim();
~~~

Compiler không thể bảo đảm `text` tồn tại ở câu `return`. Đây là **lỗi scope/definite match**, không phải lỗi dominance.

**Test:** ít nhất thử input đúng kiểu, sai kiểu và `null`. Nếu pattern có điều kiện kèm `&&`, thử thêm giá trị khiến vế sau sai; nếu điều kiện được refactor từ `if/else`, đối chiếu hành vi trước–sau.

## 4. Review record pattern và thứ tự component

Record pattern dựa vào **cấu trúc và thứ tự các component đã khai báo**:

~~~java
record Point(int x, int y) {}

// Java 21+, trích đoạn trong phương thức có Object input.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + "," + y);
}
~~~

Với `Point(2, 3)`, biến `x` là `int 2` và `y` là `int 3`. `var` ở đây không làm biến mang kiểu `Object`; compiler suy luận kiểu từ component record.

### Bẫy nguy hiểm: tráo tên nhưng vẫn biên dịch

~~~java
record Address(String city, String country) {}

// CỐ Ý SAI VỀ NGỮ NGHĨA, dù có thể biên dịch.
if (input instanceof Address(var country, var city)) {
    System.out.println(city + "/" + country);
}
~~~

`country` trong pattern thực tế nhận **component thứ nhất `city`**, `city` thực tế nhận component `country`. Vì cả hai đều là `String`, compiler có thể không phát hiện ý nghĩa tên biến đã bị tráo.

**Checklist record:**

- [ ] Số lượng component và thứ tự khớp chữ ký record.
- [ ] Tên local variable phản ánh component thật, đặc biệt khi nhiều component có cùng kiểu.
- [ ] Kiểu suy luận của `var` được hiểu đúng; khi mơ hồ, dùng typed pattern hoặc accessor có tên.
- [ ] Record constructor/factory đặt các invariant cần thiết; **pattern không tự validate nghiệp vụ**.
- [ ] Nếu record shape là public API, thay số lượng hoặc thứ tự component đã được đánh giá về tương thích.
- [ ] Không dùng record pattern chỉ để lấy một field nếu `object.field()` rõ ràng và ít phụ thuộc cấu trúc hơn.

**Test:** tạo record có các component phân biệt rõ về giá trị và ý nghĩa, ví dụ `Address("Hue", "VN")`, để dễ phát hiện việc lấy nhầm component. Kiểm thử data contract chứ không chỉ số lượng nhánh.

## 5. Review nested deconstruction: selector `null` khác component `null`

Giả sử:

~~~java
record Address(String city) {}
record Customer(String id, Address address) {}
~~~

Pattern lồng nhau:

~~~java
// Java 21+, trích đoạn; input có kiểu Object.
String result = switch (input) {
    case Customer(var id, Address(var city)) -> id + ":" + city;
    case Customer(var id, var address) -> "Missing address";
    case null -> "No customer";
    default -> "Other";
};
~~~

Phân biệt:

- `input == null`: chọn `case null`.
- `new Customer("C-1", null)`: nested `Address(...)` **không match**, nhánh `Customer(var id, var address)` vẫn có thể match và ràng buộc `address == null`.
- `new Customer("C-2", new Address(null))`: nested `Address(var city)` vẫn có thể match, vì `var city` chấp nhận giá trị tham chiếu null; một guard hoặc validation riêng mới xử lý city null.
- `new Customer("C-3", new Address("Hue"))`: nested pattern match thành công.

**Không tự động đồng nhất** “nested pattern không match” với “dữ liệu không hợp lệ”. Pattern chỉ nói **hình dạng cần khớp không đạt**. Business validation vẫn có thể cần trả `MISSING_CUSTOMER`, `INVALID_CITY` hay lý do khác nhau.

**Test matrix tối thiểu:**

| Đầu vào | Điều cần kiểm chứng |
| --- | --- |
| Selector `null` | Có `case null` hoặc chính sách từ chối null tường minh |
| Record ngoài khác `null`, component lồng `null` | Nested record pattern không match và fallback đúng |
| Record ngoài khác `null`, record lồng có field tham chiếu `null` | `var` ràng buộc null; guard/validation làm đúng |
| Đủ mọi record/component | Nhánh nested thành công |
| Record đúng kiểu nhưng giá trị bị business guard loại | Fall-through logic sang case tiếp theo, không phải Java `case:` fall-through |
| Giá trị selector có kiểu không liên quan | Chính sách default hoặc API type hẹp đúng |

Các nhánh `case ... ->` trong `switch` **không dùng fall-through kiểu switch statement cổ điển**. Khi một guard sai, quá trình matching tiếp tục xét case tiếp theo; khi một nhánh arrow được chọn, không tự chạy tiếp các nhánh phía dưới.

## 6. Review guard `when` và thứ tự case

Guard chỉ được kiểm tra **sau khi pattern tương ứng match**:

~~~java
// Java 21+, input có kiểu Object.
String category = switch (input) {
    case Integer n when n >= 100 -> "large";
    case Integer n when n > 0 -> "positive";
    case Integer n -> "non-positive";
    case null -> "missing";
    default -> "unsupported";
};
~~~

Người review nên hỏi:

1. **Boundary có đúng không?** `n == 100` vào nhánh large; `n == 1` vào positive; `n == 0` vào non-positive.
2. **Case có thứ tự hợp lý không?** Nhánh hẹp/điều kiện mạnh thường ở trước nhánh rộng.
3. **Guard có thuần túy không?** Biểu thức như `n >= 100` phù hợp; các thao tác `repository.save(...)` hay `paymentGateway.charge(...)` không phù hợp làm điều kiện chọn nhánh.
4. **Có fallback không?** Với một `Integer` không qua guard, `case Integer n` xử lý; với kiểu khác, `default` hoặc hợp đồng khác phải được xác định.
5. **Không ngầm coi exception là false.** Nếu helper trong guard ném ngoại lệ, `switch` không tự chọn case kế tiếp như khi guard trả Boolean `false`.
6. **Các guard chồng lấp ra sao?** Compiler không chứng minh mọi quan hệ giữa những biểu thức Boolean phức tạp; test các giá trị biên và trường hợp nhiều guard đều đúng.

### Dominance: compiler có thể bắt nhánh bị che

~~~java
// CỐ Ý SAI; input có kiểu Object.
String label = switch (input) {
    case CharSequence text -> "some text";
    case String text -> "string";
    case null -> "missing";
    default -> "other";
};
~~~

`String` là subtype của `CharSequence`, nên `case String text` bị case trước bao phủ. Java 21 compiler từ chối nhánh bị dominated.

Tương tự:

~~~java
// CỐ Ý SAI; nhánh String tổng quát che nhánh guarded.
String label = switch (input) {
    case String text -> "text";
    case String text when text.isBlank() -> "blank";
    case null -> "missing";
    default -> "other";
};
~~~

**Sửa:** đặt `case String text when text.isBlank()` trước `case String text`, và đặt case subtype cụ thể trước supertype tổng quát.

### Nhưng compiler không giải mọi bài toán logic

~~~java
// Java 21+: có thể biên dịch nhưng sai ý định phân loại.
String category = switch (input) {
    case Integer n when n > 10 -> "over ten";
    case Integer n when n > 20 -> "over twenty";
    case Integer n -> "other integer";
    case null -> "missing";
    default -> "other";
};
~~~

`25` thỏa cả hai guard nhưng được case `n > 10` xử lý trước. Compiler không bắt buộc chứng minh mọi quan hệ toán học giữa guards tùy ý. Nếu muốn phân loại hơn 20 riêng, đặt case `n > 20` trước `n > 10` và **kiểm thử runtime**.

**Checklist test guard:** dữ liệu ngay dưới ngưỡng, đúng ngưỡng, ngay trên ngưỡng; guard trả `false`; nhiều guard có thể đúng; null ở các component tham chiếu; helper ném ngoại lệ nếu hợp đồng cho phép. Không chỉ thử một giá trị “đẹp”.

## 7. Review `sealed` và tính exhaustive

Một sealed hierarchy giúp kiểm soát tập subtype được phép:

~~~java
// Java 21+, trích đoạn khai báo trong cùng phạm vi phù hợp.
sealed interface Action permits Create, Cancel {}
record Create(String id) implements Action {}
record Cancel(String id) implements Action {}
~~~

Switch expression:

~~~java
// action có kiểu Action.
String type = switch (action) {
    case Create(var id) -> "create";
    case Cancel(var id) -> "cancel";
    case null -> "missing";
};
~~~

Không cần `default` vì các subtype đã được xử lý, và `case null` giải quyết selector null theo chính sách ví dụ. Nếu thêm một permitted subtype mới mà không cập nhật switch, compiler có thể báo **non-exhaustive** khi biên dịch lại.

**Hai điểm thường nhầm:**

- **`null` không phải permitted subtype.** Một switch exhaustive trên các subtype sealed có thể biên dịch **mà không cần `case null`**, nhưng selector null có thể gây `NullPointerException` khi thực thi nếu không được xử lý rõ. Vì vậy “compiler báo exhaustive” không có nghĩa “null đã an toàn”.
- **`default` có thể che thiếu subtype.** Một `default -> "other"` giúp switch có nhánh dự phòng nhưng có thể làm việc thêm subtype không tạo tín hiệu compile-time yêu cầu xử lý biến thể mới. Dùng nó khi thật sự có chính sách unknown/fallback, không phải chỉ để làm build xanh.

Với sealed hierarchy có `non-sealed` branch hoặc contract mở rộng khác, cần xem chính xác kiểu được phép và khả năng bao phủ. Không được giả định bất kỳ interface có từ khóa `sealed` đều có các nhánh cụ thể đóng kín giống nhau.

**Checklist review sealed switch:**

- [ ] Tập biến thể có thực sự đóng, hay cần plugin bên ngoài mở rộng?
- [ ] Mọi subtype hiện hữu có nhánh xử lý phù hợp?
- [ ] Có nhánh `null` nếu null hợp lệ, hoặc từ chối null một cách chủ động?
- [ ] Có `default` không? Nếu có, tại sao fallback quan trọng hơn việc compiler bắt thiếu subtype?
- [ ] Khi thêm subtype mới, có compile-time regression test và runtime test để kiểm chứng hành vi?
- [ ] Có case rộng như `case Action a` che hết các case cụ thể phía sau không?

## 8. Một chương trình Java 21+ để kiểm thử 11 trường hợp runtime

Ví dụ dưới đây **cố ý dùng mô hình nhỏ** để kiểm tra nhiều quy tắc pattern matching trong một tệp, không cần JUnit, Spring hay thư viện ngoài JDK.

Domain mẫu gồm hai loại command: `Create` và `Ship`. `Ship` chứa `Customer`, rồi `Address`. Guard kiểm tra ID và dữ liệu thành phố; fallback xử lý command chưa đầy đủ. Đây là **mô hình phân loại minh họa**, không phải hệ thống gửi hàng production.

Tạo tệp **`PatternReviewChecklistDemo.java`**:

~~~java
public class PatternReviewChecklistDemo {
    sealed interface Command permits Create, Ship {}

    record Create(String orderId, int units) implements Command {}
    record Address(String city) {}
    record Customer(String id, Address address) {}
    record Ship(String orderId, Customer customer) implements Command {}

    static boolean hasText(String text) {
        return text != null && !text.isBlank();
    }

    static String route(Command command) {
        return switch (command) {
            case Create(var id, var units)
                    when hasText(id) && units > 0 ->
                    "CREATE:" + id + ":" + units;

            case Create(var id, var units) -> "REJECT_CREATE";

            case Ship(var id, Customer(var customerId, Address(var city)))
                    when hasText(id) && hasText(customerId) && hasText(city) ->
                    "SHIP:" + id + ":" + city;

            case Ship(var id, var customer) -> "REJECT_SHIP";

            case null -> "MISSING";
        };
    }

    static void verify(String label, Command input, String expected) {
        String actual = route(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) {
        verify("create-valid", new Create("O-1", 2), "CREATE:O-1:2");
        verify("create-zero", new Create("O-2", 0), "REJECT_CREATE");
        verify("create-blank-id", new Create("  ", 3), "REJECT_CREATE");

        verify("ship-valid",
                new Ship("O-3", new Customer("C-1", new Address("Hue"))),
                "SHIP:O-3:Hue");

        verify("ship-null-customer",
                new Ship("O-3", null), "REJECT_SHIP");

        verify("ship-null-address",
                new Ship("O-3", new Customer("C-2", null)),
                "REJECT_SHIP");

        verify("ship-blank-city",
                new Ship("O-3", new Customer("C-3", new Address("  "))),
                "REJECT_SHIP");

        verify("ship-null-city",
                new Ship("O-3", new Customer("C-3", new Address(null))),
                "REJECT_SHIP");

        verify("ship-blank-customer-id",
                new Ship("O-3", new Customer(" ", new Address("Hue"))),
                "REJECT_SHIP");

        verify("ship-null-order-id",
                new Ship(null, new Customer("C-1", new Address("Hue"))),
                "REJECT_SHIP");

        verify("null-selector", null, "MISSING");
    }
}
~~~

Biên dịch và chạy với **JDK 21+**:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewChecklistDemo.java
java PatternReviewChecklistDemo
~~~

Kết quả đã kiểm chứng:

~~~text
create-valid=CREATE:O-1:2
create-zero=REJECT_CREATE
create-blank-id=REJECT_CREATE
ship-valid=SHIP:O-3:Hue
ship-null-customer=REJECT_SHIP
ship-null-address=REJECT_SHIP
ship-blank-city=REJECT_SHIP
ship-null-city=REJECT_SHIP
ship-blank-customer-id=REJECT_SHIP
ship-null-order-id=REJECT_SHIP
null-selector=MISSING
~~~

### Vì sao dùng `verify(...)` thay vì chỉ in kết quả?

Mỗi lời gọi có **expected output** rõ ràng. Nếu `route` trả kết quả khác, `verify` ném `AssertionError`, khiến test không hoàn thành bình thường. Không cần bật cờ `-ea` vì ta **chủ động ném `AssertionError`**, khác với câu lệnh `assert` của Java vốn có thể bị vô hiệu hóa khi không bật assertions.

Trong CI, chạy chương trình và kiểm tra exit code: một test thất bại phải khiến job báo lỗi. Việc in stdout phục vụ **đọc hiểu đường chạy**, còn assertion phục vụ **xác nhận**.

### Vì sao có hai case `Create`?

`case Create(var id, var units) when hasText(id) && units > 0` là nhánh hợp lệ. Nhánh `Create` không guard phía sau nhận `units <= 0` hoặc ID trống/null. Nếu đặt nhánh không guard trước, nhánh guarded sau bị dominated.

### Vì sao có nhiều trường hợp `Ship`?

`Ship(var id, Customer(var customerId, Address(var city)))` cần cả `Customer` và `Address` khác null. Nhưng `new Address(null)` vẫn tạo được theo record declaration ở đây; nested pattern match **về cấu trúc**, rồi guard `hasText(city)` trả false. Điều đó khác với `new Customer("C-2", null)`, nơi nested `Address(...)` không match ngay từ bước cấu trúc.

### Bài kiểm thử chưa bao phủ điều gì?

11 test minh họa những quy tắc trọng tâm, **không** chứng minh một hệ thống giao hàng đã an toàn. Nó không kiểm tra tồn tại đơn, xác thực người dùng, trạng thái đơn hàng, quyền truy cập, địa chỉ thật, concurrency, database, retry hoặc idempotency. Những điều đó cần **integration/domain tests riêng** khi có nghiệp vụ thực.

## 9. Ma trận test: biến checklist thành ca kiểm thử

Khi kiểm tra một phương thức dùng pattern `switch`, đừng viết test theo số dòng `case` mà hãy tìm **các đường matching khác nhau**.

| Nhóm test | Input điển hình | Kỳ vọng cần khẳng định |
| --- | --- | --- |
| Type pattern khớp | Giá trị có runtime subtype đúng | Nhánh được chọn, pattern variable có giá trị đúng |
| Type pattern không khớp | Runtime type khác | Fallback/nhánh khác đúng |
| Selector `null` | `null` | Chính sách `case null` hoặc ngoại lệ rõ |
| Nested component `null` | `Ship(..., null)` | Nested record không match, fallback đúng |
| Component trong nested record `null` | `Address(null)` | `var` ràng buộc null và guard/validation quyết định |
| Guard đúng | ID hợp lệ, số lượng dương | Nhánh guarded |
| Guard sai | ID trắng, số lượng 0 | Nhánh sau/fallback |
| Điều kiện biên | `-1, 0, 1` hoặc ngưỡng cụ thể | Phân loại đúng ở hai phía ranh giới |
| Nhiều guard đều đúng | Giá trị thỏa nhiều ngưỡng | Nhánh ưu tiên theo thứ tự đúng |
| Sealed subtype mới | Thêm biến thể được phép | Compile-time hoặc runtime regression phát hiện thiếu xử lý |
| Record component đổi thứ tự/số lượng | Sửa record declaration | Kiểm tra compiler và semantic tests |
| Helper ném lỗi | Dữ liệu hoặc dependency gây exception | Đường ngoại lệ đúng hợp đồng, không ngầm coi guard false |
| Custom accessor | Accessor có logic quan sát được | Không phụ thuộc vô tình vào số lần gọi |
| Side effect | Mock repository/payment/notification | Không ghi/thu tiền chỉ để chọn nhánh |
| Toolchain | Build với target thực | Source/API và runtime tương thích |

Không cần test mọi tích Descartes của mọi trường hợp nếu hệ thống rất lớn; hãy chọn **đại diện cho mỗi nhánh và mỗi ranh giới rủi ro**, rồi bổ sung theo tính chất domain.

### Partitioning và boundary-value testing

Với `units > 0`, chia giá trị thành âm, bằng 0 và dương; thử ít nhất `-1`, `0`, `1`. Với `amount >= 10_000`, thử `9_999`, `10_000`, `10_001`. Nếu guard chứa nhiều điều kiện, nên thử mỗi điều kiện sai độc lập trước khi thử tổ hợp nhiều điều kiện sai cùng lúc.

### Khi nhiều guard giao nhau

Nếu `when n >= 100` đứng trước `when n > 0`, test `n=101` khẳng định nhánh đầu ưu tiên; test `n=1` khẳng định nhánh thứ hai vẫn nhận giá trị hợp lệ của nó. **Compile success không chứng minh thứ tự nghiệp vụ đúng**.

## 10. Compile-failure tests cho dominance và exhaustiveness

Một số quy tắc của pattern matching cần được kiểm tra ở **compile-time**, thay vì cố chạy một source mà compiler phải từ chối.

### Trường hợp 1 — dominated case

~~~java
// CỐ Ý SAI, Java 21+, selector có kiểu Object.
String kind = switch (input) {
    case CharSequence text -> "text";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
~~~

Lý do: `case CharSequence` bao phủ `String` trước đó. Compiler phải từ chối nhánh `case String` bị dominated.

### Trường hợp 2 — sealed switch không exhaustive

~~~java
// CỐ Ý SAI: chỉ có một trong hai subtype được xử lý.
sealed interface Action permits Open, Close {}
record Open() implements Action {}
record Close() implements Action {}

static String describe(Action input) {
    return switch (input) {
        case Open() -> "open";
        // Thiếu Close().
    };
}
~~~

Lý do: `switch expression` không bao phủ hết subtype của `Action`. **Đây là lỗi exhaustiveness, không phải lỗi dominance**.

### Trường hợp 3 — positive control

~~~java
// HỢP LỆ khi đặt trong class/phạm vi thích hợp.
static String describe(Action input) {
    return switch (input) {
        case Open() -> "open";
        case Close() -> "close";
        case null -> "missing";
    };
}
~~~

Trường hợp 3 phải biên dịch thành công. **Positive control** quan trọng: nếu tất cả đoạn source đều thất bại vì compiler target sai hoặc thiếu class, thì “negative test đã fail” chưa chắc chứng minh quy tắc cần kiểm tra.

**Cảnh báo:** Đừng đặt những ví dụ cố ý sai vào `src/main/java` khiến build chính luôn đỏ. Với kiểm thử tự động, giữ source fixture riêng và gọi compiler từ test harness.

## 11. Chương trình kiểm chứng biên dịch bằng Java Compiler API

Chương trình này dùng `javax.tools.JavaCompiler` để biên dịch ba đoạn source độc lập **trong bộ nhớ**, không cần tạo tệp `Sample.java` cho từng negative test. Nó kiểm tra:
- Dominance: phải bị từ chối.
- Non-exhaustiveness: phải bị từ chối.
- Positive control: phải biên dịch thành công.

Để giữ tập trung vào kết quả success/failure, harness dưới đây **không phân loại mã diagnostic**. Trong một bộ test compile-failure chất lượng cao, nên tăng cường kiểm tra chẩn đoán để tránh trường hợp negative test “đạt” vì lỗi cú pháp không liên quan.

Tạo tệp **`PatternCompileCheckDemo.java`**:

~~~java
public class PatternCompileCheckDemo {
    private static boolean compile(String source) {
        var compiler = javax.tools.ToolProvider.getSystemJavaCompiler();
        var diagnostics = new javax.tools.DiagnosticCollector<
                javax.tools.JavaFileObject>();

        var file = new javax.tools.SimpleJavaFileObject(
                java.net.URI.create("string:///Sample.java"),
                javax.tools.JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignored) {
                return source;
            }
        };

        try (var standard = compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8)) {
            var memory = new javax.tools.ForwardingJavaFileManager<
                    javax.tools.StandardJavaFileManager>(standard) {
                @Override
                public javax.tools.JavaFileObject getJavaFileForOutput(
                        Location location, String className,
                        javax.tools.JavaFileObject.Kind kind,
                        javax.tools.FileObject sibling) {
                    return new javax.tools.SimpleJavaFileObject(
                            java.net.URI.create("mem:///"
                                    + className.replace('.', '/')
                                    + kind.extension),
                            kind) {
                        @Override
                        public java.io.OutputStream openOutputStream() {
                            return new java.io.ByteArrayOutputStream();
                        }
                    };
                }
            };

            return Boolean.TRUE.equals(compiler.getTask(
                    null, memory, diagnostics,
                    java.util.List.of("--release", "21", "-proc:none"),
                    null, java.util.List.of(file)).call());
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }

    static void check(String name, boolean result, boolean expected) {
        if (result != expected) {
            throw new AssertionError(name + " expected " + expected
                    + ", got " + result);
        }
        System.out.println(
                name + "=" + (result ? "compiled" : "rejected"));
    }

    public static void main(String[] args) {
        String dominance = """
                public class Sample {
                    static String describe(Object input) {
                        return switch (input) {
                            case CharSequence text -> "text";
                            case String text -> "string";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """;

        String exhaustive = """
                public class Sample {
                    sealed interface Action permits Open, Close {}
                    record Open() implements Action {}
                    record Close() implements Action {}
                    static String describe(Action input) {
                        return switch (input) {
                            case Open() -> "open";
                        };
                    }
                }
                """;

        String valid = """
                public class Sample {
                    sealed interface Action permits Open, Close {}
                    record Open() implements Action {}
                    record Close() implements Action {}
                    static String describe(Action input) {
                        return switch (input) {
                            case Open() -> "open";
                            case Close() -> "close";
                            case null -> "missing";
                        };
                    }
                }
                """;

        check("dominance", compile(dominance), false);
        check("non-exhaustive", compile(exhaustive), false);
        check("valid exhaustive", compile(valid), true);
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac --release 21 -encoding UTF-8 PatternCompileCheckDemo.java
java PatternCompileCheckDemo
~~~

Output kiểm chứng:

~~~text
dominance=rejected
non-exhaustive=rejected
valid exhaustive=compiled
~~~

### Điểm cần review trong compiler test

- `--release 21` yêu cầu JDK đang chạy compiler hỗ trợ target Java 21.
- `ToolProvider.getSystemJavaCompiler()` cần một môi trường có compiler, thường là **JDK**, không phải runtime không cung cấp công cụ biên dịch.
- `SimpleJavaFileObject` cung cấp source từ chuỗi; `ForwardingJavaFileManager` thu output trong `ByteArrayOutputStream` để không làm bẩn thư mục build.
- Mỗi fixture dùng tên lớp `Sample` nhưng được biên dịch trong một tác vụ riêng nên không cần đổi tên file cho từng test.
- `false` chỉ xác nhận **compilation failed**. Với các negative test nghiêm túc, hãy dùng `DiagnosticCollector` để kiểm tra thêm mã/vị trí lỗi dominance hoặc non-exhaustiveness.
- Mã diagnostic của `javac` và câu chữ lỗi **không nên coi là API ổn định giữa mọi compiler/JDK**. Nếu pin JDK trong CI, có thể kiểm tra một tập mã cụ thể đã xác minh cho phiên bản đó; tránh ràng buộc cả một thông báo tiếng Anh dài.
- Một test cần **positive control** để phát hiện việc mọi compile attempt thất bại do environment setup.

Nếu muốn kiểm tra từng trường hợp ở console, có thể đưa snippet hoàn chỉnh vào file riêng rồi dùng `javac --release 21 ...`, đọc exit code và diagnostic. Không nên coi một lệnh `javac` thất bại bất kỳ là bằng chứng chắc chắn về dominance.

## 12. So sánh với hành vi trước khi refactor

Một PR thường chuyển code cũ kiểu:

~~~java
// Trích đoạn Java kiểu cũ, selector có kiểu Object.
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "Other";
~~~

sang:

~~~java
// Java 16+, trích đoạn trong phương thức trả String.
if (input instanceof String text) {
    return text.trim();
}
return "Other";
~~~

Đây là refactor nhỏ; vẫn phải bảo toàn các đường chạy:

| Input | Trước | Sau | Kỳ vọng |
| --- | --- | --- | --- |
| `"  A  "` | `"A"` | `"A"` | Tương đương |
| `""` | `""` | `""` | Không được thêm validation nếu chưa được yêu cầu |
| `42` | `"Other"` | `"Other"` | Tương đương |
| `null` | `"Other"` | `"Other"` | Tương đương |

Với refactor lớn hơn (`if/else` → `switch`; cast → nested deconstruction), cần lập bảng test trước–sau bao gồm **trường hợp không match** và **thứ tự ưu tiên nhánh**. Một thay đổi “làm code ngắn hơn” có thể vô tình đổi exception, bỏ bước validation hoặc biến trường hợp null thành fallback mới.

**Khuyến nghị review:** tách PR đổi cú pháp khỏi PR đổi nghiệp vụ khi có thể. Nếu cần thay đổi đồng thời, ghi rõ phần nào được kỳ vọng bảo toàn và phần nào cố ý đổi hành vi, mỗi phần có test riêng.

## 13. Từ unit test đến integration test

Không phải mọi rủi ro đều được phát hiện bằng một lớp test duy nhất.

### Unit test thuần túy

Dùng cho:
- Phân loại theo runtime type và record shape.
- Chọn case có `when` theo giá trị biên.
- Xử lý selector/component null.
- Kiểm tra kết quả từ một `switch expression`.

Có thể dùng chương trình `verify(...)` như phần 8 hoặc framework unit test dự án đang sử dụng. Với JUnit 5, có thể viết parameterized tests; nhưng **không cần phụ thuộc JUnit để hiểu bản chất pattern matching**. Nếu dùng JUnit thật, hãy khai báo dependency và phiên bản theo build của dự án.

### Integration test

Cần khi pattern được dùng tại ranh giới:
- JSON deserialization đến nhiều subtype record.
- HTTP request/event từ message broker với biến thể mới.
- Persistence và schema evolution.
- Authorization, policy, transaction hoặc retry.
- Thư viện được compile ở target Java khác JVM runtime.

Những vấn đề này **không tự được giải quyết** bởi `case Record(...)` hoặc sealed hierarchy. Ví dụ `record` không tự cung cấp polymorphic JSON discriminator; serializer còn cần cấu hình/contract riêng.

### Property-based và metamorphic tests

Với classifier có điều kiện đơn giản, có thể kiểm tra tính chất như:

> Với mọi `Create(id, units)` mà `id` có nội dung và `units > 0`, kết quả phải bắt đầu bằng `"CREATE:"`; với `units <= 0`, kết quả phải là `"REJECT_CREATE"`.

Đây là **đặc tả tính chất**, không phải source code đã chạy. Công cụ property-based testing có thể sinh nhiều dữ liệu để tìm giá trị biên hoặc chuỗi Unicode bất thường. Hãy giữ invariant đúng theo contract; đừng viết property rộng hơn hành vi mong muốn.

### Mutation tests

Có thể cố ý thay `units > 0` thành `units >= 0`. Nếu bộ test có input `units == 0` thì mutation sẽ bị phát hiện. Tương tự, đảo thứ tự hai guard hoặc bỏ fallback null giúp đánh giá khả năng test suite bảo vệ logic nhánh. Không cần triển khai mutation-testing framework để hiểu nguyên tắc: **mỗi điều kiện quan trọng phải có test phân biệt đúng/sai**.

## 14. Chất lượng của guard và accessor trong code review

Một guard phù hợp:

~~~java
// Trích đoạn; id và count đến từ pattern đã match.
when id != null && !id.isBlank() && count > 0
~~~

Một guard có rủi ro:

~~~java
// ANTI-PATTERN, chỉ minh họa ý tưởng, không phải nguồn độc lập.
case PayOrder(var id, var amount)
        when paymentGateway.charge(id, amount) -> "Paid";
~~~

Nếu `charge` tác động đến hệ thống bên ngoài, nó có thể chạy trong lúc Java **đang kiểm tra điều kiện**, kể cả khi guard trả `false` rồi chuyển sang case sau. `switch` không tự rollback hành động đó. Hãy tách **phân loại/validation thuần túy** và **thực thi có side effect** trong service/handler có hợp đồng rõ.

Record accessor cũng nên đơn giản và nhất quán. Một custom accessor có thể được gọi khi deconstruct; nếu code chạy qua nhiều pattern trước khi chọn nhánh, những lần đọc component có thể lặp. Đừng giấu cập nhật trạng thái trong accessor và rồi viết test dựa trên giả định “deconstruction luôn chỉ gọi getter một lần”.

**Review thêm đường ngoại lệ:** nếu helper trong guard/accessor ném ngoại lệ, `switch` có thể hoàn tất bất thường. Đó không phải “guard false”. Test exception khi nó có ý nghĩa nghiệp vụ, và không catch bỏ qua chỉ để pass test.

## 15. Checklist CI cho module dùng Java Pattern Matching

Một pipeline tối thiểu thường cần:

1. Chọn **JDK chính xác** (ví dụ JDK 21) và ghi version trong log.
2. Dùng Maven/Gradle **wrapper** thay vì phụ thuộc tool version trên máy cá nhân.
3. Build từ thư mục output sạch, đúng source/release target.
4. Chạy unit tests bao phủ `null`, guard, branch và nested record shape.
5. Chạy compile-failure/compile-success tests cho các quy tắc được tài liệu hóa, với compiler version kiểm soát.
6. Chạy integration tests cần thiết cho serializer, DB, policy và runtime.
7. Nếu phát hành thư viện, kiểm tra class-file target và dependency compatibility.
8. Báo rõ ca test nào thất bại, không gộp mọi lỗi compiler thành một nhóm “pattern matching failed”.

Ví dụ lệnh local với hai chương trình ở bài này:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewChecklistDemo.java
java PatternReviewChecklistDemo

javac --release 21 -encoding UTF-8 PatternCompileCheckDemo.java
java PatternCompileCheckDemo
~~~

Nếu dùng Maven Wrapper:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nếu dùng Gradle Wrapper:

~~~bash
./gradlew --no-daemon clean test
~~~

Các lệnh wrapper chỉ áp dụng khi repo có cấu hình build tương ứng. Không nên coi chúng là bảo đảm framework test đã chạy mọi compiler fixture: bộ kiểm thử compile failure phải được **tích hợp rõ ràng** vào build.

### Một mẫu báo cáo PR ngắn có thể dùng

~~~text
Target Java: 21
Thay đổi: instanceof/cast -> record pattern + switch expression
Contract cần giữ: output với selector null và nested component null
Guard: điều kiện thuần túy, không I/O
Exhaustiveness: sealed hierarchy, không dùng default che subtype mới
Đã kiểm: compile success, các đường match/non-match, boundary,
          guard false, null, fallback, exception liên quan
Rủi ro còn lại: dependency/serialization/integration (nếu có)
~~~

Đây là **khung mô tả PR**, không phải một file cấu hình. Người review nên có thể đọc nó và biết **hành vi nào có khả năng bị ảnh hưởng**.

## 16. Các lỗi kiểm thử thường gặp

| Sai sót | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ test happy path | Không phát hiện guard false, component null và fallback | Lập ma trận đường match/fail |
| Chỉ kiểm tra compile success | Vẫn có thể sai ưu tiên nhánh/logic nghiệp vụ | Thêm runtime boundary tests |
| Negative test chỉ kiểm tra `!compiled` | Dương tính giả do lỗi syntax/classpath | Xác nhận diagnostic và positive control |
| Test dominance nhưng dùng source thiếu `default` cho `Object` | Có thể xuất hiện lỗi exhaustiveness không liên quan | Giữ fixture tối thiểu, hoàn chỉnh ngoài lỗi chủ đích |
| Chỉ test selector `null`, bỏ component `null` | Không phát hiện nested pattern fail | Kiểm thử cả hai loại null |
| Nhầm `var` với kiểm tra non-null component | Chấp nhận hoặc từ chối dữ liệu không mong muốn | Viết test component null và guard |
| Bỏ test giá trị đúng ngưỡng | Không bắt lỗi `>` thành `>=` | Test ngay dưới/bằng/trên ngưỡng |
| Dùng `default` cho mọi sealed switch | Có thể che thiếu subtype sau này | Xem lại chiến lược exhaustive |
| Dùng `assert` Java mà quên bật `-ea` | Test không chạy assertion | Dùng framework/`AssertionError` hoặc bật `-ea` rõ ràng |
| Mock quá mức một classifier thuần túy | Test khó hiểu, phụ thuộc implementation | Kiểm tra kết quả theo input/output |
| Thực hiện I/O trong guard | Test branch kéo theo side effect | Tách decision khỏi execution |
| Chỉ đo coverage theo dòng | Dòng được chạy nhưng nhiều nhánh/guard chưa được test | Dùng branch/boundary coverage và ma trận ca |
| Dùng JDK IDE mới nhưng CI cũ | Build fail ngoài môi trường cá nhân | Chốt toolchain và target trong CI |
| Trộn thay đổi cú pháp với đổi business rule | Khó kết luận regression bắt nguồn từ đâu | Tách PR hoặc viết test đặc tả từng thay đổi |

## 17. Bài tập tự luyện và đáp án

### Bài 1 — Thiết kế ba test `instanceof`

Cho hàm:

~~~java
// Java 16+, trích đoạn trong class/phương thức phù hợp.
static String normalize(Object input) {
    if (input instanceof String text) {
        return text.trim();
    }
    return "Other";
}
~~~

Chọn ba input để bảo vệ contract.

**Đáp án:** `"  A  "` cho `"A"`; số `42` cho `"Other"`; `null` cho `"Other"`. Có thể thêm `""` để chứng minh hàm không tự thay đổi policy chuỗi rỗng.

### Bài 2 — Phân biệt hai kiểu null của record

Với `record Container(RecordItem item) {}` và `record RecordItem(String code) {}`, dự đoán nhánh được chọn khi `input = new Container(null)` và khi `input = new Container(new RecordItem(null))`:

~~~java
String result = switch (input) {
    case Container(RecordItem(var code)) -> "Record " + code;
    case Container(var item) -> "Incomplete";
    case null -> "Missing";
    default -> "Other";
};
~~~

**Đáp án:** `Container(null)` chọn `"Incomplete"` vì nested record không match. `Container(RecordItem(null))` chọn nhánh đầu và tạo `"Record null"` do `var code` ràng buộc null; nếu không mong muốn, thêm guard `code != null` hoặc validation.

### Bài 3 — Thứ tự case có guard

~~~java
// CỐ Ý SAI: nhánh String rộng đứng trước.
String label = switch (input) {
    case String s -> "text";
    case String s when s.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Nhánh thứ hai bị dominated; phải đặt `case String s when s.isBlank()` trước `case String s`. Thêm runtime test `"   "` và `"A"` cho bản sửa.

### Bài 4 — Test nào cần compiler, test nào cần runtime?

Một `switch expression` trên sealed `Action` thiếu subtype `Close`; một `switch` khác có hai guard `n > 3` và `n > 5` đặt sai thứ tự. Công cụ nào phù hợp?

**Đáp án:** Thiếu subtype là lỗi **exhaustiveness** cần test compile failure. Guard sai thứ tự toán học có thể vẫn biên dịch; cần **runtime behavior test** với giá trị như `n=6` và review logic.

### Bài 5 — Tìm điểm yếu trong test suite

Một suite chỉ kiểm tra `Create("O-1", 1)`. Code bị sửa từ `units > 0` thành `units >= 0` mà suite vẫn xanh. Vì sao?

**Đáp án:** Không có boundary test cho `units == 0`. Bổ sung `Create("O-2", 0)` với expected `REJECT_CREATE`; có thể thêm `-1` và một giá trị dương để phân biệt ba lớp.

### Bài 6 — Có nên ghi audit ở guard?

Một reviewer thấy:

~~~java
// Chỉ minh họa ý tưởng.
case Ship(var id, var customer) when auditAndCheck(id) -> ...
~~~

`auditAndCheck` ghi audit rồi trả Boolean. Nên làm gì?

**Đáp án:** Yêu cầu tách **predicate quyết định** khỏi **hành động ghi audit**. Guard false không rollback side effect; các nhánh fallback và retry có thể gây ghi ngoài ý định. Nếu audit là yêu cầu hệ thống, đặt tại luồng xử lý có chính sách rõ ràng, không giấu trong điều kiện.

### Bài 7 — `default` và mở rộng sealed hierarchy

Một `switch` sealed hiện xử lý `Create`, `Ship` và có `default -> "other"`. Nhóm thêm `Refund`. Compiler có chắc chắn yêu cầu thêm nhánh `Refund` không?

**Đáp án:** Không. `default` bao phủ các trường hợp còn lại nên có thể che yêu cầu xử lý biến thể mới. Nếu mục tiêu là buộc code xem xét subtype mới khi build, hạn chế default và viết các case exhaustive cụ thể.

## 18. Checklist cuối cùng cho reviewer

Có thể sao chép checklist này vào template PR:

- [ ] **Target:** source/release/JDK/toolchains đã xác định.
- [ ] **Selector:** kiểu tĩnh và tập giá trị có thể nhận được rõ ràng.
- [ ] **Pattern:** type/record/nested pattern hợp lệ; các biến được ràng buộc đúng component.
- [ ] **Scope:** pattern variables không được dùng ngoài đường chắc chắn match.
- [ ] **Null:** đã xét selector null, component null và payload rỗng riêng biệt.
- [ ] **Guard:** đúng điều kiện và biên, không giấu side effect; exception được xử lý đúng.
- [ ] **Dominance:** nhánh cụ thể/hẹp trước nhánh rộng; không có case bị compiler từ chối.
- [ ] **Exhaustive:** sealed switch bao phủ mọi biến thể; default có lý do rõ.
- [ ] **Domain:** constructor/factory validation và business invariants không bị gán nhầm cho pattern.
- [ ] **Readability:** tên component rõ; nested pattern không quá sâu; tránh refactor chỉ vì ngắn.
- [ ] **Runtime tests:** happy path, non-match, guard false, null, boundary, fallback.
- [ ] **Compile tests:** negative cases đúng nguyên nhân và có positive control khi cần.
- [ ] **Regression:** trước–sau refactor giữ contract hoặc nêu rõ hành vi cố ý thay đổi.
- [ ] **Integration:** serializer, dependency, I/O và runtime được test nếu phạm vi PR liên quan.
- [ ] **CI:** test chạy bằng build wrapper và JVM hỗ trợ target.
- [ ] **Evidence:** tác giả ghi được lệnh kiểm chứng, test results và rủi ro còn lại.

## 19. Ghi nhớ và nguồn chính thức

**Review pattern matching là review của một quyết định phân nhánh**, không chỉ review cú pháp `case`. Compiler giúp giữ những ràng buộc như scope, dominance và exhaustiveness; test runtime giúp kiểm tra `null`, guard, dữ liệu biên và ưu tiên nhánh; code review bảo vệ invariant, side effect và khả năng bảo trì.

Khi phân vân nên viết thêm test nào, hãy hỏi: **“Có loại đầu vào nào khác khiến chương trình đi vào một đường matching khác?”**. Nếu có, hãy xét thêm đại diện của loại đó. Nếu thêm subtype, đổi cấu trúc record hoặc đổi thứ tự case, hãy chạy lại **cả kiểm thử biên dịch và kiểm thử hành vi**.

**Tài liệu tham khảo chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java Language Specification SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JavaCompiler API (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html).
