# Pattern applicability và checked cast compatibility trong Java

## 1. Hai khái niệm trả lời hai câu hỏi khác nhau

Khi viết pattern matching, ví dụ `value instanceof String text`, Java phải trả lời **hai câu hỏi theo đúng thứ tự**:

1. **Tại thời điểm biên dịch:** Pattern `String text` có *applicable* (áp dụng được) cho **kiểu tĩnh** của biểu thức `value` không? Để quyết định, trình biên dịch dựa trên khả năng chuyển kiểu được phép; với reference type, trọng tâm là **checked cast compatibility**.
2. **Khi chương trình chạy:** Nếu phép kiểm tra đã hợp lệ về mặt kiểu, **giá trị thực tế** có khớp pattern không? Chỉ khi khớp, biến mẫu `text` mới được khởi tạo và được sử dụng trong vùng phạm vi thích hợp.

Hai câu hỏi không thể hoán đổi. Một pattern có thể hợp lệ tại compile time nhưng không khớp khi chạy. Ngược lại, một giá trị mà ta `biết chắc` đang giữ `String` cũng không cho phép viết pattern trái các quy tắc kiểu tĩnh.

Bài này lấy **Java 21 (JLS 21)** làm chuẩn để giải thích type patterns, record patterns và pattern `switch`. Các ví dụ chỉ dùng `instanceof` type patterns tương thích Java 17 (tính năng chính thức từ Java 16); ví dụ record patterns cần Java 21 (tính năng chính thức từ Java 21). Những thay đổi ở các bản Java mới hơn và tính năng *preview* không được ngầm áp dụng vào các quy tắc Java 21.

## 2. Pattern applicability là gì?

Trong đặc tả JLS 21 §14.30.3, pattern `p` **applicable at type T** có nghĩa là **kiểu tĩnh T của giá trị đầu vào cho phép thử pattern p**.

Đối với **type pattern khai báo biến kiểu tham chiếu U**, quy tắc chính là:

> Pattern kiểu tham chiếu U áp dụng được tại kiểu tham chiếu T khi **T checked cast convertible to U**.

Ta có thể ghi nhớ theo sơ đồ:

```text
Biểu thức cần kiểm tra
  └── kiểu tĩnh T
         └── có checked cast conversion T → U?
                ├── Không → lỗi biên dịch: pattern không applicable
                └── Có   → được phép biên dịch
                            └── lúc chạy thử giá trị với pattern
                                   ├── Không khớp → false / xét case khác
                                   └── Khớp       → khởi tạo biến mẫu
```

Ví dụ:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`value` có kiểu tĩnh `Object`, không phải `String`, dù đối tượng thực tế là chuỗi. Vì `Object → String` là chuyển kiểu tham chiếu thu hẹp **có kiểm tra**, `String text` applicable tại `Object`. Khi chạy, đối tượng thực sự là `String`, nên nhánh `if` được thực hiện.

Đổi giá trị thành `Integer.valueOf(10)` thì **vẫn biên dịch** vì kiểu tĩnh của biến vẫn là `Object`, nhưng phép kiểm tra `String` trả về `false`. Do đó, `applicable` **không đồng nghĩa** với `luôn khớp`.

### Phân biệt ba thuật ngữ

| Khái niệm | Hỏi điều gì? | Thời điểm |
| --- | --- | --- |
| *Pattern applicability* | Với kiểu tĩnh T, pattern này có được phép dùng không? | Compile time |
| *Checked cast compatibility* | T có thể chuyển theo một phép cast được chấp nhận để làm phép thử kiểu U không? | Compile time |
| *Pattern matching* | Giá trị hiện tại có thật sự thỏa pattern và khởi tạo được biến mẫu không? | Runtime |

Tính applicable là điều kiện để trình biên dịch **chấp nhận biểu thức có pattern**; kết quả true/false đến từ **runtime matching**. Ngoài applicability, một cấu trúc như `switch` còn có các quy tắc riêng về case bị che (*domination*) và tính đầy đủ (*exhaustiveness*).

## 3. Checked cast compatibility: vì sao không phải cast nào cũng dùng được trong pattern?

JLS 21 §5.5 gọi một giá trị là **checked cast compatible** với kiểu tham chiếu đích nếu có casting conversion đến kiểu đó, **ngoại trừ narrowing reference conversion không được kiểm tra đầy đủ (*unchecked*)**.

Đối với nguồn và đích là reference types, những trường hợp thường gặp là:

- **Identity:** cùng kiểu, chẳng hạn `String → String`.
- **Widening reference:** từ lớp con tới lớp cha hoặc interface phù hợp, chẳng hạn `String → CharSequence`.
- **Checked narrowing reference:** từ kiểu tổng quát xuống kiểu cụ thể khi Java có thể kiểm tra tính tương thích cần thiết, chẳng hạn `Object → String`, `Number → Integer`.
- **Unchecked narrowing reference:** một cast chỉ hợp lệ kèm cảnh báo `unchecked` vì thông tin generic bị xóa khi chạy, chẳng hạn `Object → List<String>`. Dạng này **không** đáp ứng checked cast compatibility.

Từ `checked` ở đây là **đặc tính cho phép phép thử dựa trên kiểu**; không có nghĩa *mọi* phép chuyển đổi đều sinh lệnh kiểm tra tại runtime. Identity và widening reference không cần kiểm tra cast động. Ngược lại, một cast `unchecked` có thể vẫn kiểm tra phần kiểu đã bị xóa (ví dụ lớp `List`) nhưng **không xác thực được tham số `String`**.

Phân loại sâu hơn trong JLS §5.1.6.3:

- *Completely unchecked:* sau khi xóa generic, quan hệ kiểu như một phép upcast; JVM không cần runtime check.
- *Partially unchecked:* sau khi xóa generic, quan hệ như một phép downcast; JVM vẫn kiểm tra được kiểu thô nhưng không bảo đảm tham số generic.

Cả hai đều là **unchecked narrowing reference conversions**; không được nhầm `partially unchecked` với **checked cast compatibility**. Nếu phép chuyển đổi cần dùng để áp dụng pattern là unchecked narrowing, pattern bị từ chối khi biên dịch.

### Bảng dự đoán nhanh với Java 21

| Kiểu tĩnh T của biểu thức | Pattern U | Applicable? | Lý do |
| --- | --- | --- | --- |
| `Object` | `String s` | Có | `Object → String` là checked narrowing |
| `CharSequence` | `String s` | Có | `CharSequence → String` có thể kiểm tra |
| `Number` | `Integer n` | Có | `Integer` là lớp con của `Number` |
| `String` | `Integer n` | Không | Hai lớp này không thể có một instance chung |
| `Object` | `List<?> list` | Có | Tham số wildcard không bị đòi xác minh kiểu phần tử cụ thể |
| `Object` | `List<String> list` | Không | Cast từ `Object` cần unchecked narrowing |
| `List<Integer>` | `ArrayList<Integer> list` | Có | Kiểu nguồn giữ thông tin generic tương thích, phép downcast được kiểm tra |
| `List<Integer>` | `ArrayList<String> list` | Không | Hai cách tham số hóa provably distinct, không có casting conversion phù hợp |

Đáng chú ý, **đích có generic không tự động bị cấm**. Ví dụ `List<Integer> → ArrayList<Integer>` được phép bởi quan hệ kiểu tĩnh đủ chặt, trong khi `Object → List<String>` không được. Vì thế quy tắc `pattern không dùng được với bất kỳ kiểu generic nào` là sai.

## 4. Chương trình minh họa các trường hợp hợp lệ (Java 17+)

Lưu thành tệp **`ApplicabilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ApplicabilityDemo {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "String=" + text.length();
        }
        if (value instanceof List<?> items) {
            return "List=" + items.size();
        }
        return "Other=" + String.valueOf(value);
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify(List.of("a", "b")));
        System.out.println(classify(null));

        List<Integer> numbers = new ArrayList<>(List.of(4, 5));
        if (numbers instanceof ArrayList<Integer> concrete) {
            System.out.println("First=" + concrete.get(0));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc JDK 21:

```bash
javac ApplicabilityDemo.java
java ApplicabilityDemo
```

Kết quả chính xác:

```text
String=4
List=2
Other=null
First=4
```

Giải thích từng trường hợp:

1. `Object → String` được phép kiểm tra bằng `instanceof String text`. Giá trị `"Java"` thực sự khớp nên lấy được độ dài 4.
2. `Object → List<?>` là phép thử hợp lệ. Từ `items` ta biết **đây là một `List`**, không biết chắc kiểu từng phần tử.
3. `null` không khớp type pattern ở vế phải của `instanceof`, nên `classify(null)` đi đến nhánh cuối và trả về `Other=null`.
4. `List<Integer> → ArrayList<Integer>` là phép kiểm tra hợp lệ vì nguồn đã có thông tin `Integer` tương thích; đối tượng thực tế là `ArrayList`, nên in `First=4`.

Ví dụ cuối là một điểm dễ nhầm: `ArrayList<Integer>` không phải kiểu reifiable tổng quát, nhưng phép so khớp ở đây vẫn hợp lệ nhờ **kiểu tĩnh của biểu thức nguồn**. Điều kiện là trình biên dịch có thể chứng minh casting conversion cần thiết là checked.

## 5. Những đoạn mã KHÔNG biên dịch và vì sao

**Các mảnh mã bên dưới cố ý có lỗi. Không ghép chúng vào tệp chạy ở phần 4.**

### 5.1. Hai lớp không thể tương thích

```java
String text = "abc";
if (text instanceof Integer n) { // COMPILE ERROR
    System.out.println(n);
}
```

`String` và `Integer` là hai lớp không có quan hệ kế thừa phù hợp; không tồn tại instance có thể đồng thời thuộc cả hai lớp. Compiler từ chối ngay từ **kiểu tĩnh**, không cần chạy đến điều kiện.

Tương tự, `Number n` không thể checked cast convertible sang `String` vì `String` là lớp final, không thể là một dạng con của `Number`.

### 5.2. Cast generic unchecked khác với pattern hợp lệ

```java
Object value = java.util.List.of("A", "B");

@SuppressWarnings("unchecked")
java.util.List<String> casted = (java.util.List<String>) value;
// Cast ở trên có thể biên dịch nhưng bản chất là unchecked.

if (value instanceof java.util.List<String> names) { // COMPILE ERROR
    System.out.println(names.size());
}
```

Với `Object → List<String>`, JVM có thể xác nhận đây là `List` nhưng **không thể xác nhận từng phần tử mang kiểu `String`** từ generic đã bị xóa. Ép kiểu tường minh có thể được cho phép cùng cảnh báo unchecked, còn một type pattern cần checked cast compatibility nên **không được phép**.

Thay vào đó, kiểm tra `List<?>` và xác thực phần tử riêng:

```java
static void printStrings(Object value) {
    if (value instanceof java.util.List<?> items) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            } else {
                System.out.println("Không phải String: " + item);
            }
        }
    }
}
```

Đây là **một phương thức minh họa**: đặt trong một class rồi gọi từ chương trình. Pattern `List<?>` chỉ xác nhận kiểu danh sách; pattern `String text` kiểm tra **từng phần tử**. Đừng dùng `@SuppressWarnings("unchecked")` để giả vờ đã kiểm tra kiểu runtime.

### 5.3. Generic `provably distinct` dù dùng lớp con

```java
java.util.List<Integer> numbers = java.util.List.of(1, 2);

if (numbers instanceof java.util.ArrayList<String> wrong) { // COMPILE ERROR
    System.out.println(wrong);
}
```

`List<Integer>` và `ArrayList<String>` khác nhau về tham số kiểu, nên không có phép chuyển tham chiếu được phép. Trình biên dịch biết điều đó mà không cần quan sát nội dung danh sách.

### 5.4. Không tự boxing primitive để dùng instanceof pattern

```java
int number = 42;
if (number instanceof Integer boxed) { // COMPILE ERROR trong Java 21
    System.out.println(boxed);
}
```

Trong Java 21, toán hạng trái của `instanceof` phải là reference type hoặc null type; kiểu `int` không đáp ứng điều kiện đó. Nếu thực sự cần pattern:

```java
Object number = Integer.valueOf(42);
if (number instanceof Integer boxed) {
    System.out.println(boxed.intValue()); // 42
}
```

Đây là `Object` chứa một `Integer` đã được boxing **trước đó**. Không suy diễn rằng `instanceof` tự boxing mọi primitive ở Java 21; một số tính năng primitive patterns ở các JDK mới từng ở trạng thái preview và có quy tắc riêng.

## 6. Record pattern: applicability còn kiểm tra từng component (Java 21)

JLS 21 §14.30.3 nêu điều kiện bổ sung cho **record pattern** có kiểu record `R` và danh sách component patterns `L`. Pattern này applicable tại kiểu tĩnh `T` nếu:

1. `T` **checked cast convertible** sang `R`.
2. Với **từng component pattern** `p` trong `L`, `p` applicable tại **kiểu khai báo của component tương ứng** của record `R`.

Nói cách khác, record pattern phải qua **hai tầng kiểm tra kiểu**: loại record ở ngoài và các pattern của thành phần ở trong. Mẫu lồng nhau sẽ được kiểm tra tiếp theo cùng nguyên tắc.

Ví dụ độc lập, lưu thành **`RecordApplicabilityDemo.java`**, yêu cầu JDK 21:

```java
public class RecordApplicabilityDemo {
    record Packet(Object payload) {}
    record Envelope(Packet packet) {}

    static String decode(Object input) {
        if (input instanceof Envelope(Packet(String text))) {
            return "Text=" + text;
        }
        if (input instanceof Envelope(Packet(Integer number))) {
            return "Int=" + number;
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(decode(new Envelope(new Packet("OK"))));
        System.out.println(decode(new Envelope(new Packet(7))));
        System.out.println(decode(new Envelope(new Packet(null))));
        System.out.println(decode(null));
    }
}
```

```bash
javac RecordApplicabilityDemo.java
java RecordApplicabilityDemo
```

Kết quả:

```text
Text=OK
Int=7
Other
Other
```

Vì sao chương trình hợp lệ?

- `input` có kiểu tĩnh `Object` và có checked cast conversion đến record `Envelope`.
- Component `packet` của `Envelope` có kiểu `Packet`, nên record pattern `Packet(...)` applicable tại đó.
- Component `payload` của `Packet` có kiểu `Object`, nên cả `String text` và `Integer number` đều applicable tại `Object`.
- Khi chạy, dữ liệu còn phải thực sự khớp **tất cả** tầng pattern. Giá trị `Packet(null)` không khớp các type patterns `String` hoặc `Integer` nên trả về `Other`; `decode(null)` cũng trả về `Other`.

Ngược lại, giả sử record có component đã được khai báo là `String`:

```java
record Label(String value) {}

Object input = new Label("x");
if (input instanceof Label(Integer n)) { // COMPILE ERROR
    System.out.println(n);
}
```

Type pattern `Integer n` **không applicable tại kiểu component `String`**. Dù `Object → Label` là một phép thử được phép ở lớp ngoài, pattern tổng thể vẫn không hợp lệ vì lớp trong sai.

**Lưu ý về null:** `null` ở vị trí *đầu vào của toàn bộ record pattern* không khớp. Đối với component pattern bên trong record, Java 21 có quy tắc riêng cho *null-matching type patterns* khi pattern đó unconditional tại kiểu component. Không nên khái quát đơn giản rằng mọi nested type pattern đều từ chối null; trong ví dụ này component có kiểu `Object`, còn mẫu `String`/`Integer` không unconditional tại `Object`.

## 7. Pattern applicable không đảm bảo switch hợp lệ

Trong Java 21, `switch` có type patterns vẫn yêu cầu **case pattern applicable tại kiểu selector**. Ngoài điều kiện đó, compiler kiểm tra **thứ tự case**, **domination** và **exhaustiveness**.

Ví dụ hợp lệ:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text: " + s;
        case Integer n -> "int: " + n;
        default -> "other";
    };
}
```

Đây là **phương thức minh họa Java 21**, phải đặt trong class để biên dịch. Cả hai pattern `String` và `Integer` đều applicable tại selector `Object`; khi chạy, `switch` chọn case khớp.

Hai nhóm lỗi khác nhau cần phân biệt:

- **Applicability error:** `switch` dùng selector kiểu `String` mà thêm `case Integer n`; không có checked cast conversion thích hợp từ `String` tới `Integer`. Case bị loại vì **kiểu không thể phù hợp**.
- **Dominance error:** selector `Object`, đặt `case Number n` **trước** `case Integer i`; mỗi `Integer` đều là `Number`, nên case `Integer` phía sau đã bị che. Cả hai pattern đều applicable tại `Object`, nhưng **thứ tự case vẫn sai**.

Tương tự, việc thêm `when` là một điều kiện lọc tiếp sau matching; guard không thể biến một pattern vốn không applicable thành hợp lệ. Một `switch expression` còn phải đầy đủ các trường hợp có thể xảy ra; thường dùng `default` hoặc tập pattern được chứng minh là bao phủ.

## 8. Checked cast compatibility không đồng nghĩa với thành công của cast

So sánh ba tình huống với cùng một giá trị có kiểu tĩnh `Object`:

```java
Object value = 123;

boolean matches = value instanceof String s; // false

// Nếu thực hiện dòng dưới sẽ ném ClassCastException:
// String text = (String) value;

// Phép thử generic đặc tả không cho phép:
// if (value instanceof java.util.List<String> strings) { }
```

- Dòng `instanceof String s` **biên dịch được** vì `Object → String` là checked cast convertible, rồi trả về `false` vì đối tượng thực tế là `Integer`.
- Dòng cast `(String) value` **có cú pháp và kiểu hợp lệ** nhưng nếu chạy, nó thất bại bằng `ClassCastException`.
- `List<String>` dùng với đầu vào `Object` trong pattern **không biên dịch**, vì phải dựa vào unchecked narrowing conversion.

Tóm lại, cần phân biệt **cast được phép viết**, **cast có thể kiểm tra đúng theo kiểu đích**, **pattern được phép dùng tại kiểu tĩnh**, và **giá trị thực tế khớp**. Đây là bốn ý liên quan nhưng không đồng nhất.

## 9. Cách tự phân tích một lỗi “inconvertible types” hoặc “unsafe cast”

Khi trình biên dịch từ chối pattern, thực hiện theo thứ tự:

1. **Xác định kiểu tĩnh T**, từ khai báo biến/kiểu trả về/phép suy luận. Không dựa vào `toString()`, dữ liệu debug hoặc `getClass()` của giá trị mà bạn tình cờ biết.
2. **Xác định pattern U hoặc record R**; nếu là record pattern, ghi kiểu khai báo của từng component.
3. **Kiểm tra phép chuyển kiểu T → U/R**: identity, widening hay narrowing? Nếu các kiểu có thể được kiểm tra, pattern có cơ hội applicable; nếu không liên quan hoặc provably distinct, dừng ở lỗi compile time.
4. **Kiểm tra generic:** phép thu hẹp có cần unchecked cast không? Nếu có, cân nhắc `<?>`, thiết kế API mang type phù hợp hơn, hoặc kiểm tra phần tử riêng. Đừng dùng một cast unchecked để khẳng định chắc chắn kiểu dữ liệu.
5. **Nếu là record pattern, lặp lại phép kiểm tra cho mọi component**. Một component không applicable khiến toàn bộ record pattern không applicable.
6. **Nếu là switch, kiểm tra tiếp dominance và exhaustiveness**. Hai lỗi này độc lập với lỗi applicability.
7. **Cuối cùng mới hỏi liệu giá trị runtime sẽ khớp hay không**. Trường hợp không khớp thường trả về `false` hoặc chuyển sang case khác, còn việc dùng cast ép kiểu trực tiếp có thể ném `ClassCastException`.

### Câu hỏi tự kiểm tra

**Câu 1.** `Object x = java.util.List.of("A");` — vì sao `x instanceof List<?> items` hợp lệ nhưng `x instanceof List<String> items` không hợp lệ?

**Giải đáp:** Biểu thức có **kiểu tĩnh `Object`**. Kiểm tra `List<?>` chỉ cần xác nhận kiểu danh sách, còn `List<String>` đòi xác nhận tham số generic mà runtime không mang đủ thông tin. Loại thứ hai cần unchecked narrowing conversion.

**Câu 2.** `List<Integer> numbers = new ArrayList<>();` — vì sao `numbers instanceof ArrayList<Integer> a` hợp lệ?

**Giải đáp:** Kiểu tĩnh nguồn đã ràng buộc `Integer` trong `List<Integer>` và phép chuyển sang `ArrayList<Integer>` là checked narrowing; JVM chỉ cần kiểm tra lớp `ArrayList` tại runtime, còn tính tương thích tham số kiểu được chứng minh từ kiểu tĩnh.

**Câu 3.** Với `record Box(String text) {}`, có thể dùng `Box(Integer n)` làm record pattern để kiểm tra một giá trị `Object` không?

**Giải đáp:** Không. Mặc dù `Object` có thể được kiểm tra có phải `Box` hay không, component `text` có kiểu tĩnh `String` và `Integer n` không applicable tại `String`.

## 10. Tài liệu chuẩn để đối chiếu

Các quy tắc trong bài dựa trên **Java Language Specification, Java SE 21**:

- [JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): định nghĩa applicability, unconditional patterns và dominance.
- [JLS §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): định nghĩa checked cast compatible.
- [JLS §5.1.6.1–5.1.6.3 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.6): phép chuyển được phép, checked/unchecked, completely/partially unchecked.
- [JLS §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện compile time và kết quả runtime của `instanceof`.

**Điểm cần nhớ:** Pattern applicability hỏi liệu **kiểu tĩnh** cho phép phép thử hay không; checked cast compatibility là tiêu chí cốt lõi cho pattern tham chiếu; record patterns kiểm tra cả từng component. Sau khi pattern vượt qua kiểm tra biên dịch, việc khớp dữ liệu vẫn là quyết định của runtime.
