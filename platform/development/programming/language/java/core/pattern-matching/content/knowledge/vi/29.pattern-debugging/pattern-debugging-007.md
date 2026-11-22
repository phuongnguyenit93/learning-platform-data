# Debug nested record pattern trong Java 21+

## 1. Vấn đề: vì sao một nested record pattern không khớp?

**Nested record pattern** là pattern chứa một hoặc nhiều record pattern con, cho phép kiểm tra kiểu và tách dữ liệu qua các tầng record. Chẳng hạn:

```java
// Giả sử Invoice, Customer, Address là những record được khai báo phù hợp.
if (value instanceof Invoice(
        var code,
        Customer(var name, Address(var city, var street)))) {
    System.out.println(code + ":" + name + ":" + city);
}
```

Biểu thức trên được hiểu từ ngoài vào trong:

1. `value` phải là một `Invoice` khác `null`.
2. Component `customer` của `Invoice` phải là một `Customer` khác `null`.
3. Component `address` của `Customer` phải là một `Address` khác `null`.
4. Khi các tầng khớp, `code`, `name`, `city` và `street` được ràng buộc vào các biến pattern theo thứ tự khai báo của record.

**Khó khăn khi debug:** kết quả `false` của toàn bộ `instanceof` không cho biết tầng nào đã thất bại. Nếu thêm điều kiện `&&` hoặc `when`, lại có thể xảy ra tình huống **record pattern đã khớp nhưng điều kiện nghiệp vụ bên ngoài pattern là `false`**. Cần tách bạch hai nguyên nhân.

Record patterns trở thành tính năng chính thức ở **Java 21** (JEP 440), sử dụng được trong `instanceof` và trong `switch`. Pattern matching for `switch` cũng chính thức ở Java 21 (JEP 441). Ví dụ chạy trong bài yêu cầu **JDK 21+**, không cần `--enable-preview`.

## 2. Model minh họa và “cây” kiểm tra

Dùng ba record:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record Invoice(String code, Customer customer) {}
```

Đây là những khai báo minh họa; chương trình chạy đầy đủ nằm ở mục 6.

Với dữ liệu:

```java
Object value = new Invoice(
        "I-1",
        new Customer("Ana", new Address("Ha Noi", "Main")));
```

Cây cần khớp là:

```text
value
└── Invoice
    ├── code: String              -> var code
    └── customer: Customer        -> Customer(...)
        ├── name: String          -> var name
        └── address: Address      -> Address(...)
            ├── city: String      -> var city
            └── street: String    -> var street
```

**Điểm mấu chốt:** `var city` không tự từ chối `null`. Nếu `Address` tồn tại nhưng component `city == null`, pattern vẫn có thể **khớp** và `city` được ràng buộc bằng `null`. Trong khi đó, nếu cả đối tượng `Address` là `null`, pattern con `Address(...)` **không khớp**.

Bởi vậy, debug một nested record pattern phải phân biệt:

- **Không khớp cấu trúc:** sai kiểu ở record gốc, hoặc một record con mà pattern yêu cầu lại bằng `null`.
- **Khớp cấu trúc nhưng không đạt guard:** component có `null`/blank, số ngoài khoảng hợp lệ, điều kiện nghiệp vụ trả `false`.
- **Ngoại lệ:** accessor record tự định nghĩa ném lỗi trong quá trình deconstruction, không phải một kết quả `false` bình thường.
- **Lỗi biên dịch:** sai số lượng pattern con, kiểu không phù hợp hoặc sử dụng biến pattern ngoài phạm vi hợp lệ.

## 3. Debug từ ngoài vào trong, không đoán dựa trên `false`

Giả sử yêu cầu nghiệp vụ là: hóa đơn phải có mã, có khách hàng, có địa chỉ, tên khách hàng và tên thành phố khác null/blank. `street` được phép null trong ví dụ này.

Ta dùng biểu thức:

```java
if (value instanceof Invoice(var code,
        Customer(var name, Address(var city, var street)))
        && code != null && !code.isBlank()
        && name != null && !name.isBlank()
        && city != null && !city.isBlank()) {
    // Xử lý hóa đơn hợp lệ.
}
```

### Bước A — Kiểm tra record gốc

```java
if (!(value instanceof Invoice invoice)) {
    System.out.println("not an Invoice");
}
```

Nếu `value == null` hoặc giá trị thực tế là `String`, tầng ngoài đã không khớp. Không cần suy đoán các component phía trong.

`instanceof` trên `null` trả về `false` và bản thân phép thử không ném `NullPointerException`.

### Bước B — Kiểm tra từng record con

```java
if (value instanceof Invoice invoice) {
    Customer customer = invoice.customer();
    if (customer == null) {
        System.out.println("customer is null");
    } else {
        Address address = customer.address();
        if (address == null) {
            System.out.println("address is null");
        }
    }
}
```

Đây là phương pháp **tạm thời dùng accessor và type pattern** để tìm tầng bị hỏng. Khi đã xác định lỗi, có thể quay lại biểu thức record pattern gọn hơn. Không nên thêm `System.out.println` vào mọi chỗ rồi quên gỡ trong code sản xuất.

### Bước C — Kiểm tra các điều kiện nghiệp vụ

Nếu toàn bộ record con khác `null`, tiếp tục kiểm tra riêng `code`, `name`, `city`. Ví dụ `new Address(null, "Main")` vẫn khớp `Address(var city, var street)`; chính guard `city != null` mới từ chối nó.

Toán tử `&&` đánh giá **ngắn mạch** từ trái sang phải. Vì vậy `!city.isBlank()` chỉ chạy sau khi `city != null` đúng. Đảo điều kiện thành `!city.isBlank() && city != null` có thể gây `NullPointerException` khi `city == null`.

### Bước D — So sánh cùng một bộ dữ liệu

Hãy lưu một input và chạy **hai cách**: biểu thức pattern thật và hàm chẩn đoán theo tầng. Không xây một input mới giữa hai lần kiểm tra, đặc biệt nếu dữ liệu có thể thay đổi hoặc accessor được tự định nghĩa có side effect.

## 4. Hàm chẩn đoán có lý do cụ thể

Một biểu thức pattern trả về Boolean không có “mã nguyên nhân thất bại”. Có thể dùng hàm tách bước để chỉ ra **lý do đầu tiên theo thứ tự kiểm tra đã chọn**:

```java
static String diagnose(Object value) {
    if (value == null) return "root-null";
    if (!(value instanceof Invoice invoice)) return "wrong-root";

    Customer customer = invoice.customer();
    if (customer == null) return "customer-null";

    Address address = customer.address();
    if (address == null) return "address-null";

    String code = invoice.code();
    if (code == null || code.isBlank()) return "invalid-code";

    String name = customer.name();
    if (name == null || name.isBlank()) return "invalid-name";

    String city = address.city();
    if (city == null) return "city-null";
    if (city.isBlank()) return "city-blank";
    return "ok";
}
```

Đoạn này là một phương thức minh họa đặt bên trong class có các record đã nêu. Hàm sử dụng **accessor mặc định** của record, là những accessor không được tự sửa trong chương trình hoàn chỉnh.

**Vì sao kiểm tra `customer`, `address` trước `code` và `name`?** Đó là thứ tự ưu tiên chẩn đoán do ví dụ chọn để phân biệt lỗi cấu trúc trước lỗi nội dung. Một hóa đơn có nhiều lỗi đồng thời sẽ được báo **lỗi đầu tiên**, không phải danh sách đầy đủ. Với validation nghiệp vụ cần báo mọi lỗi, hãy xây bộ thu thập lỗi riêng, thay vì coi hàm này là validator tổng quát.

## 5. Test matrix: kiểm thử `null` theo từng tầng

| Dữ liệu đầu vào | Record pattern lồng có khớp cấu trúc? | Guard đủ điều kiện? | Lý do chẩn đoán |
| --- | --- | --- | --- |
| `Invoice("I-1", Customer("Ana", Address("Ha Noi", "Main")))` | Có | Có | `ok` |
| `Invoice("I-2", Customer("Binh", Address("Hue", null)))` | Có; `var street` nhận null | Có | `ok` |
| `Invoice("I-3", null)` | Không; thiếu `Customer(...)` | Không được đánh giá | `customer-null` |
| `Invoice("I-4", Customer("Chi", null))` | Không; thiếu `Address(...)` | Không được đánh giá | `address-null` |
| `Invoice("I-5", Customer("Dung", Address(null, "Main")))` | Có; `var city` nhận null | Không | `city-null` |
| `Invoice("I-6", Customer("Em", Address(" ", "Main")))` | Có | Không | `city-blank` |
| `Invoice(" ", Customer(...))` | Có | Không | `invalid-code` |
| `Invoice("I-8", Customer("", Address(...)))` | Có | Không | `invalid-name` |
| Chuỗi `"not an invoice"` | Không; sai kiểu gốc | Không được đánh giá | `wrong-root` |
| `value == null` | Không | Không được đánh giá | `root-null` |

**Lưu ý thuật ngữ:** Trong phương thức chạy ở mục 6, kết quả `"NO_MATCH"` nghĩa là **toàn bộ biểu thức `instanceof pattern && guards` không đúng**. Nó không chứng minh bản thân record pattern đã thất bại: `city-null`, `city-blank`, `invalid-code` và `invalid-name` đều có thể đạt bước khớp cấu trúc rồi thất bại ở guard.

## 6. Chương trình Java hoàn chỉnh: test có assertion và output chính xác

Tạo file **`NestedRecordPatternDebugDemo.java`**:

```java
public class NestedRecordPatternDebugDemo {
    record Address(String city, String street) {}
    record Customer(String name, Address address) {}
    record Invoice(String code, Customer customer) {}

    static String extract(Object value) {
        if (value instanceof Invoice(var code,
                Customer(var name, Address(var city, var street)))
                && code != null && !code.isBlank()
                && name != null && !name.isBlank()
                && city != null && !city.isBlank()) {
            return "MATCH:" + code + ":" + name + ":"
                    + city.toUpperCase(java.util.Locale.ROOT);
        }
        return "NO_MATCH";
    }

    static String diagnose(Object value) {
        if (value == null) return "root-null";
        if (!(value instanceof Invoice invoice)) return "wrong-root";

        Customer customer = invoice.customer();
        if (customer == null) return "customer-null";

        Address address = customer.address();
        if (address == null) return "address-null";

        String code = invoice.code();
        if (code == null || code.isBlank()) return "invalid-code";

        String name = customer.name();
        if (name == null || name.isBlank()) return "invalid-name";

        String city = address.city();
        if (city == null) return "city-null";
        if (city.isBlank()) return "city-blank";
        return "ok";
    }

    static void verify(String label, Object value,
                       String expectedExtract, String expectedReason) {
        String actualExtract = extract(value);
        String actualReason = diagnose(value);
        if (!expectedExtract.equals(actualExtract)
                || !expectedReason.equals(actualReason)) {
            throw new AssertionError(label + " actual="
                    + actualExtract + "/" + actualReason);
        }
        System.out.println(label + " -> " + actualExtract
                + " [" + actualReason + "]");
    }

    public static void main(String[] args) {
        verify("valid", new Invoice("I-1",
                new Customer("Ana", new Address("Ha Noi", "Main"))),
                "MATCH:I-1:Ana:HA NOI", "ok");

        verify("street-null", new Invoice("I-2",
                new Customer("Binh", new Address("Hue", null))),
                "MATCH:I-2:Binh:HUE", "ok");

        verify("customer-null", new Invoice("I-3", null),
                "NO_MATCH", "customer-null");

        verify("address-null", new Invoice("I-4",
                new Customer("Chi", null)),
                "NO_MATCH", "address-null");

        verify("city-null", new Invoice("I-5",
                new Customer("Dung", new Address(null, "Main"))),
                "NO_MATCH", "city-null");

        verify("city-blank", new Invoice("I-6",
                new Customer("Em", new Address(" ", "Main"))),
                "NO_MATCH", "city-blank");

        verify("invalid-code", new Invoice(" ",
                new Customer("Giau", new Address("Da Nang", "Main"))),
                "NO_MATCH", "invalid-code");

        verify("invalid-name", new Invoice("I-8",
                new Customer("", new Address("Da Nang", "Main"))),
                "NO_MATCH", "invalid-name");

        verify("wrong-root", "not an invoice",
                "NO_MATCH", "wrong-root");

        verify("root-null", null,
                "NO_MATCH", "root-null");

        System.out.println("10/10 tests passed");
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 NestedRecordPatternDebugDemo.java
java NestedRecordPatternDebugDemo
```

**Stdout chính xác:**

```text
valid -> MATCH:I-1:Ana:HA NOI [ok]
street-null -> MATCH:I-2:Binh:HUE [ok]
customer-null -> NO_MATCH [customer-null]
address-null -> NO_MATCH [address-null]
city-null -> NO_MATCH [city-null]
city-blank -> NO_MATCH [city-blank]
invalid-code -> NO_MATCH [invalid-code]
invalid-name -> NO_MATCH [invalid-name]
wrong-root -> NO_MATCH [wrong-root]
root-null -> NO_MATCH [root-null]
10/10 tests passed
```

Chương trình đã được chạy bằng JShell của JDK 24 với logic và 10 ca input trên; `Locale.ROOT` được dùng ở đoạn trình bày để phép chuyển chữ hoa không phụ thuộc locale hệ thống. Hai phương thức `extract` và `diagnose` cho ra kết quả mong đợi trên tất cả ca; nếu một expected khác actual, `verify` ném `AssertionError` thay vì in “passed”.

### Vì sao mỗi ca có giá trị?

- `valid` kiểm tra đường đi chuẩn qua toàn bộ ba tầng record.
- `street-null` chứng minh component bắt bằng `var` có thể null mà không làm hỏng record pattern, nếu nghiệp vụ cho phép.
- `customer-null` và `address-null` cô lập hai tầng deconstruction không thể khớp record con null.
- `city-null` và `city-blank` chứng minh **pattern khớp** không có nghĩa **guard đúng**.
- `invalid-code` và `invalid-name` kiểm tra thứ tự và điều kiện nghiệp vụ sau khi deconstruction thành công.
- `wrong-root` và `root-null` phân biệt sai kiểu nguồn với việc selector không có giá trị.

Vì `Invoice`, `Customer` và `Address` là những record không có constructor xác thực trong chương trình minh họa, ta **cố tình** có thể tạo dữ liệu null/blank để test. Trong domain model thực tế, nên cân nhắc đặt invariant trong constructor/factory để không sinh đối tượng sai từ đầu; khi đó các lỗi dữ liệu không hợp lệ sẽ được test tại **ranh giới tạo đối tượng**.

## 7. Debug trong `switch`: một case không chạy chưa chắc do pattern

Pattern matching for `switch` thường dùng cùng record patterns:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "root-null";
        case Invoice(var code,
                Customer(var name, Address(var city, var street)))
                when code != null && !code.isBlank()
                        && name != null && !name.isBlank()
                        && city != null && !city.isBlank() ->
                "valid:" + code;

        case Invoice(var code,
                Customer(var name, Address(var city, var street))) ->
                "guard-failed";

        case Invoice(var code, Customer(var name, var address)) ->
                "address-null";

        case Invoice(var code, var customer) ->
                "customer-null";

        default -> "wrong-root";
    };
}
```

Đây là **phương thức minh họa** cần đặt trong class có ba record đã khai báo; không phải một file Java độc lập. Nó tách các nhóm nguyên nhân:

1. `case null` xử lý selector null.
2. Nhánh có `when` trả `valid` khi cấu trúc và guard đều đúng.
3. Nhánh cùng cấu trúc nhưng không có guard nhận trường hợp record đã deconstruct được nhưng guard thất bại.
4. Nhánh `Invoice(..., Customer(..., var address))` nhận trường hợp `Address(...)` không khớp (trong model này là `address == null`).
5. Nhánh `Invoice(var code, var customer)` nhận tình huống `customer == null` còn lại.
6. `default` nhận giá trị không phải `Invoice`.

**Thứ tự các case là quan trọng.** Đặt pattern tổng quát `Invoice(var code, var customer)` trước các pattern lồng sẽ che khuất những nhánh cụ thể phía dưới. Compiler có thể báo *dominated case*. Đặt case có guard cụ thể trước case không guard của cùng cấu trúc.

**Chú ý khi debug nhánh `when`:** guard chỉ được đánh giá **sau khi pattern khớp**. Không thể kết luận một component null đã làm pattern thất bại chỉ vì nhánh có guard không chạy.

## 8. Lỗi biên dịch của nested record pattern khác với runtime non-match

Một số lỗi phải sửa **trước khi chạy test**, vì compiler chặn ngay.

### 8.1. Số lượng component không đúng

`Customer` khai báo hai component: `name` và `address`. Đoạn sau **cố tình sai**:

```java
// Sai: Customer có hai component, nhưng chỉ cung cấp một pattern con.
static boolean badArity(Object value) {
    return value instanceof Invoice(var code, Customer(var name));
}
```

Kết quả mong đợi: compiler báo sai số lượng nested patterns. Số lượng, **thứ tự** và kiểu của các pattern con phải phù hợp với record component được khai báo. Đoạn này không nằm trong file chạy ở mục 6.

### 8.2. Dùng pattern variable ngoài phạm vi

```java
// Sai: city không tồn tại trên các đường đi mà instanceof thất bại.
static void badScope(Object value) {
    if (value instanceof Invoice(var code,
            Customer(var name, Address(var city, var street)))) {
        System.out.println(city);
    }
    System.out.println(city); // Lỗi biên dịch.
}
```

Java sử dụng **flow scoping**: biến pattern chỉ được dùng ở vị trí mà compiler chứng minh pattern đã khớp. Biến `city` hợp lệ trong nhánh `if` đúng và ở vế phải của `&&` khi pattern là vế trái; không hợp lệ sau `if` trong ví dụ này.

**Đã đối chiếu bằng JDK 24:** một biến thể `badArity` được compiler từ chối với lỗi `incorrect number of nested patterns`; biến thể `badScope` bị từ chối vì biến `city` không hợp lệ tại vị trí dùng. Đây là **negative compilation tests**, không phải kết quả `false` của `instanceof`.

### 8.3. Kiểu component và tên biến

`var` được suy luận từ kiểu tĩnh của component. `var city` ở đây là `String`, nhưng `var` không biến Java thành ngôn ngữ dynamic. Nếu thay `city.toUpperCase()` bằng thao tác chỉ có trên một kiểu khác, compiler sẽ báo lỗi kiểu.

Tên biến có thể khác tên component, nhưng **thứ tự pattern** vẫn tuân theo khai báo record. Đổi vị trí `name` và `address`, hoặc viết record pattern lồng sai tầng, sẽ gây lỗi biên dịch khi không tương thích kiểu; với các component cùng kiểu, viết sai thứ tự thậm chí có thể biên dịch nhưng tạo lỗi logic. Dùng tên rõ nghĩa và review khai báo record gốc.

## 9. Accessor ném ngoại lệ: không nhầm với “pattern không khớp”

Record pattern thực hiện deconstruction thông qua các accessor của record. Nếu một accessor **được tự định nghĩa** và ném ngoại lệ trong quá trình match, xử lý không còn đơn thuần là `false`.

Ví dụ **minh họa riêng trong JShell hoặc một class phù hợp**:

```java
record AccessorBomb(String data) {
    @Override
    public String data() {
        throw new IllegalStateException("bomb");
    }
}

Object bomb = new AccessorBomb("x");

try {
    System.out.println(bomb instanceof AccessorBomb(var x));
} catch (MatchException e) {
    System.out.println("accessor-exception -> "
            + e.getClass().getSimpleName() + ":"
            + e.getCause().getClass().getSimpleName());
}
```

**Kết quả của ví dụ trên (JDK 24):**

```text
accessor-exception -> MatchException:IllegalStateException
```

`MatchException` là ngoại lệ của Java khi một thao tác deconstruction gây lỗi trong lúc thực hiện pattern matching. **Không nên coi nó là một non-match bình thường** hay lặng lẽ trả `false` trong mọi tình huống.

Khi debug một lỗi xảy ra giữa việc match, hãy xem **stack trace**, loại ngoại lệ gốc và `getCause()`. Kiểm tra xem accessor có tính toán, đọc trạng thái mutable hay ném ngoại lệ không. Trong hầu hết model dữ liệu đơn giản, nên giữ accessor record rõ ràng, ít side effect và để kiểm tra invariant ở constructor/factory thích hợp.

## 10. Quy trình debug thực tế bằng IDE và logging

1. **Lưu một input tái hiện được lỗi.** Ghi giá trị kiểu gốc, ba tầng record và dữ liệu quan trọng. Đừng dựa vào mô tả “hóa đơn bị null” nếu chưa biết tầng nào null.
2. **Đặt breakpoint tại `if`/`switch`.** Quan sát selector trước khi match. Với `value instanceof Invoice(...)`, nếu selector null hoặc sai kiểu, việc inspect sâu hơn không có ý nghĩa.
3. **Tạm viết một hàm chẩn đoán như `diagnose`.** Dừng tại từng `return "..."` để xác định tầng đầu tiên thất bại. Đây thường là cách đáng tin hơn việc đoán điều kiện lồng nào trả `false`.
4. **Theo dõi guard riêng.** Một nhánh `case ... when ...` bị bỏ qua có thể do pattern không khớp hoặc do `when` không đạt. Dùng một case pattern không guard sau case có guard hoặc log các điều kiện qua biến đã tách.
5. **So sánh với bộ test nhỏ.** Dùng ít nhất root null, sai kiểu, mỗi record con null, component null, blank và đường đi hợp lệ.
6. **Kiểm tra thứ tự case và dominance.** Trong `switch`, case tổng quát có thể che case cụ thể; compiler giúp phát hiện nhiều lỗi kiểu này.
7. **Tách lỗi runtime exception.** Nếu thấy `MatchException`, xem nguyên nhân accessor; nếu thấy `NullPointerException`, xác định có gọi phương thức trên component null trong guard/body hay không.
8. **Rút gọn thành minimum reproducible example.** Giữ đúng vài record, phương thức match và dữ liệu gây lỗi; thử lại trên đúng JDK/toolchain của dự án.
9. **Sau khi sửa, chạy regression tests.** Một ca hợp lệ vẫn chạy không chứng minh các tầng null và guard đã được xử lý đúng.

Có thể dùng `javac --release 21 -g NestedRecordPatternDebugDemo.java` khi cần biên dịch kèm thông tin debug. Trên IDE, đặt breakpoint ở `diagnose` và các nhánh nhận kết quả; record pattern có thể được compiler triển khai thành các thao tác nội bộ, nên không nhất thiết có điểm dừng trực quan cho từng pattern con trong một biểu thức dài.

**Logging an toàn:** Đừng in toàn bộ đối tượng trong ứng dụng thực tế nếu chúng chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm. Ưu tiên chỉ ghi loại input, nhánh lỗi, mã correlation đã được cho phép và thông tin cần thiết để tái hiện lỗi.

## 11. Một số “bẫy” debug phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `instanceof Invoice(...)` là `false` | Sai kiểu selector, selector null hoặc một record con null | Kiểm tra tầng ngoài rồi từng accessor |
| Nested pattern trông đúng nhưng `if` vẫn không chạy | Guard `&&` không đạt | Tách pattern-only và guard; thử `city == null`/`city.isBlank()` |
| `Address(null, "Main")` bị coi là “record không khớp” | Nhầm component null với record con null | Thử pattern không guard: `Address(var city, var street)` vẫn có thể match |
| `street == null` mà match vẫn đúng | `var street` cho phép null và nghiệp vụ không cấm | Xác nhận quy tắc nullable của component |
| `case` đặc biệt không tới được | Case tổng quát trước đó che khuất | Đổi thứ tự case có guard/cấu trúc cụ thể lên trước |
| Compiler báo `incorrect number of nested patterns` | Record pattern thiếu hoặc thừa component | Đối chiếu khai báo `record` |
| Compiler báo không tìm thấy biến `city` | Biến pattern ngoài flow scope | Chỉ dùng ở nhánh/đường đi đã khớp |
| Có `MatchException` | Accessor ném lỗi khi deconstruction | Xem cause/stack trace, kiểm tra accessor tự định nghĩa |
| Có `NullPointerException` trong guard | Gọi `isBlank()` trước khi kiểm tra null hoặc dùng toán tử sai | Dùng `city != null && !city.isBlank()` |
| Test chỉ có “happy path” đều xanh | Chưa có ca null theo từng tầng | Thêm ma trận và assertion có tên ca như mục 5–6 |

## 12. Bài tập tự luyện

Cho:

```java
record Coordinates(Double lat, Double lon) {}
record Place(String label, Coordinates coordinates) {}
record Trip(String tripId, Place destination) {}
```

Cần kiểm tra một `Object input` là `Trip` hợp lệ, có destination, coordinates, `lat` và `lon` khác null và trong khoảng:

- Vĩ độ trong khoảng từ -90 đến 90.
- Kinh độ trong khoảng từ -180 đến 180.
- `label` không null/blank.

**Yêu cầu:**

1. Viết `instanceof Trip(var tripId, Place(var label, Coordinates(var lat, var lon)))` và guard để kiểm tra các giá trị. Đặt điều kiện null **trước** khi so sánh số thực để tránh unboxing `null`.
2. Viết `diagnoseTrip(Object input)` dùng các accessor để phân biệt: root null, sai kiểu, thiếu destination, thiếu coordinates, thiếu lat/lon, tọa độ ngoài phạm vi và label blank.
3. Xây test matrix cho mỗi trường hợp và so sánh kết quả của pattern với chẩn đoán theo tầng.
4. Cân nhắc thêm test `Double.NaN` và vô cực: điều kiện “nằm trong khoảng” nếu viết dưới dạng phủ định không đúng có thể bỏ lọt `NaN`; dùng `Double.isFinite(...)` khi domain yêu cầu tọa độ hữu hạn.
5. Đặt thử một `case Trip(...)` tổng quát trước case có `when`, quan sát compiler/dominance, sau đó sửa thứ tự.

**Gợi ý biểu thức** (trong phương thức có biến `Object input`):

```java
boolean valid = input instanceof Trip(
        var tripId,
        Place(var label, Coordinates(var lat, var lon)))
        && label != null && !label.isBlank()
        && lat != null && lon != null
        && Double.isFinite(lat) && Double.isFinite(lon)
        && lat >= -90 && lat <= 90
        && lon >= -180 && lon <= 180;
```

Đây là **đoạn code minh họa** sử dụng ba record của bài tập, chưa phải class Java độc lập. Hãy chú ý: pattern khớp được `Coordinates(null, ...)` vì `var lat` có thể null, nhưng guard phải từ chối trước khi unboxing.

## 13. Ghi nhớ và tài liệu tham khảo

Khi debug nested record pattern, hãy **xác định tầng khớp trước, kiểm tra guard sau, rồi tách ngoại lệ và lỗi biên dịch**. Dùng model có tên rõ nghĩa, hàm chẩn đoán từng tầng, test có expected/actual và ca null ở mọi cấp. Không suy diễn từ một kết quả `false` rằng record pattern ở tầng sâu nhất đã sai.

Tài liệu chính thức:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java 21 API — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
