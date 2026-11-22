# Phân biệt lỗi biên dịch và kết quả `false` với `instanceof`

## 1. Hai kết quả rất khác nhau khi kiểm tra kiểu

Khi học Java Pattern Matching, người mới thường gặp hai tình huống trông giống nhau nhưng bản chất khác hẳn:

- **Lỗi biên dịch (compile-time error):** trình biên dịch nhận thấy biểu thức `instanceof` hoặc cách sử dụng biến pattern không hợp lệ theo quy tắc kiểu và phạm vi của Java. Chương trình **không được biên dịch thành công** để chạy phần mã đó.
- **Kết quả `false` khi chạy (runtime result):** biểu thức `instanceof` **hợp lệ về mặt ngôn ngữ**, chương trình biên dịch được, nhưng giá trị cụ thể tại thời điểm chạy không khớp với kiểu được hỏi. Biểu thức trả về boolean `false`.

Ví dụ sử dụng cùng một type pattern nhưng khác **kiểu tĩnh** của biến đầu vào:

```java
// HỢP LỆ: kiểu tĩnh là Object, kiểu thực tế là Integer.
Object value = 42;
if (value instanceof String text) {
    System.out.println(text.length());
}
// Điều kiện false; không có dòng nào được in.
```

```java
// KHÔNG BIÊN DỊCH trên Java 17:
Integer value = 42;
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
```

Ở ví dụ thứ nhất, biến `value` có kiểu tĩnh `Object`, nên việc nó chứa một `String` là khả năng hợp lệ về kiểu. Trình biên dịch cho phép kiểm tra, dù giá trị hiện tại là `Integer` và phép kiểm tra trả `false`.

Ở ví dụ thứ hai, `Integer` và `String` là những lớp không có quan hệ kế thừa cho phép chuyển kiểu theo yêu cầu; cả hai đều là lớp `final`. Với biến có **kiểu tĩnh `Integer`**, trình biên dịch có thể kết luận phép kiểm tra `String` này không hợp lệ. Vì vậy mã lỗi ngay từ lúc biên dịch, không có kết quả boolean `false` nào được tạo ra từ biểu thức đó.

**Câu hỏi định hướng:** “Biểu thức có hợp lệ để Java cho chạy không?” phải được trả lời **trước** câu hỏi “Khi chạy, giá trị có khớp kiểu không?”.

Bài này tập trung vào `instanceof` với **type pattern** (`value instanceof String text`) trên **Java 17+**. Tính năng này đã ổn định từ Java 16 theo JEP 394. Các ví dụ có chú thích **KHÔNG BIÊN DỊCH** chỉ để phân tích lỗi; chương trình hoàn chỉnh ở phần sau là mã Java 17 chạy được.

## 2. Ba thông tin phải tách biệt: kiểu tĩnh, kiểu runtime và kiểu pattern

Xem đoạn sau:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Có ba thông tin khác nhau:

1. **Kiểu tĩnh của biểu thức bên trái:** `Object`. Trình biên dịch biết `value` được khai báo là `Object`.
2. **Kiểu thực tế của đối tượng khi chạy:** `String`. Giá trị được gán hiện tại là một đối tượng chuỗi.
3. **Kiểu của pattern bên phải:** `String`. Pattern kiểm tra khả năng giá trị thực tế thuộc kiểu này và, nếu khớp, ràng buộc biến `text` có kiểu `String`.

Trình biên dịch xem xét tính **tương thích kiểu** giữa (1) và (3) để quyết định có chấp nhận biểu thức hay không. Chỉ sau khi mã hợp lệ và được thực thi, Java mới xét (2) để trả `true` hoặc `false`.

Điểm dễ nhầm: **kiểu tĩnh không nhất thiết trùng kiểu runtime**. Một biến `Object` có thể chứa `String`, `Integer`, `ArrayList`, một record, hoặc `null`. Cùng một phép kiểm tra trên biến `Object` có thể cho kết quả khác nhau tùy đối tượng được gán.

### Type pattern và phép kiểm tra kiểu truyền thống

Java có hai dạng thường gặp:

```java
// Kiểm tra kiểu truyền thống:
if (value instanceof String) {
    // Chỉ kiểm tra kiểu.
}

// Type pattern:
if (value instanceof String text) {
    // Kiểm tra kiểu và có thêm biến String text.
}
```

Cả hai đều có thể trả `false` ở runtime. Nhưng **type pattern còn có quy tắc biên dịch riêng**: nếu kiểu tĩnh của biểu thức bên trái đã là kiểu con của kiểu pattern, Java 17 từ chối pattern đó vì phép kiểm tra sẽ luôn thành công đối với mọi giá trị khác `null` (mục 5). Không nên áp dụng máy móc quy tắc này cho dạng `instanceof String` truyền thống.

## 3. Trường hợp hợp lệ nhưng trả `false`: giá trị `null`

Ví dụ:

```java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không khớp");
}
```

Chương trình in:

```text
Không khớp
```

Lý do:

- Kiểu tĩnh `Object` cho phép thử `String`, nên trình biên dịch chấp nhận.
- Giá trị runtime là `null`. Theo quy tắc `instanceof`, **`null` không khớp type pattern nào**, nên điều kiện là `false`.
- Nhánh `if` không chạy; biến `text` không được khởi tạo để sử dụng. Nhánh `else` chạy.

Đây không phải `NullPointerException`. Bản thân phép kiểm tra `instanceof` trên tham chiếu `null` trả về `false` một cách an toàn.

So sánh:

```java
Object input = null;
boolean isString = input instanceof String;
System.out.println(isString); // false
```

`input instanceof String` và `input instanceof String text` đều không khớp khi giá trị là `null` (với kiểu tĩnh `Object` như ở đây).

### Đừng nhầm với việc gọi phương thức trên `null`

```java
Object input = null;

// An toàn: kiểm tra kiểu, kết quả false.
boolean matched = input instanceof String;

// Nếu bỏ chú thích, dòng sau ném NullPointerException khi chạy:
// System.out.println(input.toString());
```

`NullPointerException` xuất hiện do cố dùng tham chiếu `null` để gọi phương thức/đọc thành viên không phù hợp, chứ không phải do một phép kiểm tra `instanceof` hợp lệ.

### Trường hợp bất ngờ: giá trị là `null` nhưng mã vẫn lỗi biên dịch

```java
String text = null;

// KHÔNG BIÊN DỊCH trên Java 17:
// if (text instanceof String sameText) {
//     System.out.println(sameText);
// }
```

Dù người lập trình nhìn thấy `text` đang là `null`, **trình biên dịch kiểm tra kiểu tĩnh `String`** của biểu thức, không dựa vào việc biến hiện được gán `null`. Mẫu `String sameText` là type pattern không cần thiết vì `String` đã là kiểu tĩnh của `text`; JLS 17 xem đây là lỗi biên dịch.

Nếu chỉ muốn kiểm tra biến `String` có khác `null`, hãy viết trực tiếp:

```java
String text = null;
if (text != null) {
    System.out.println(text.length());
}
```

Hoặc dùng dạng kiểm tra kiểu cũ (về mặt ngôn ngữ vẫn hợp lệ):

```java
String text = null;
System.out.println(text instanceof String); // false
```

**Kết luận cho `null`:** `instanceof` hợp lệ gặp `null` trả `false`; nhưng một **type pattern không hợp lệ vì kiểu tĩnh** vẫn gây lỗi biên dịch, dù giá trị cụ thể là `null`.

## 4. Trường hợp hợp lệ nhưng trả `false`: đối tượng runtime khác kiểu

Một biến có kiểu tĩnh đủ tổng quát có thể chứa nhiều đối tượng khác nhau. Trình biên dịch cho phép kiểm tra các kiểu có khả năng phù hợp, nhưng kết quả phụ thuộc đối tượng thực tế:

```java
Object value = Integer.valueOf(10);

System.out.println(value instanceof String); // false
System.out.println(value instanceof Integer); // true
System.out.println(value instanceof Number); // true
```

Tất cả các phép kiểm tra trên đều **biên dịch được** vì biểu thức bên trái có kiểu tĩnh `Object`. Giá trị runtime là `Integer`, nên nó không phải `String` nhưng đúng là `Integer` và cũng là một `Number`.

Với type pattern:

```java
Object value = Integer.valueOf(10);

if (value instanceof String text) {
    System.out.println("Text: " + text);
} else {
    System.out.println("Không phải chuỗi");
}
```

Kết quả:

```text
Không phải chuỗi
```

`false` có ý nghĩa bình thường trong luồng nghiệp vụ: chương trình có thể chuyển sang `else`, trả giá trị mặc định, hoặc thử một type pattern khác.

### Trường hợp một lớp cha có nhiều lớp con

```java
Number value = Double.valueOf(2.5);

if (value instanceof Integer number) {
    System.out.println("Integer: " + number);
} else {
    System.out.println("Không phải Integer");
}
```

Kết quả:

```text
Không phải Integer
```

Phép thử `value instanceof Integer number` **hợp lệ**, bởi một biến `Number` có thể chứa `Integer`; tuy nhiên ở lần chạy này nó đang chứa `Double`, nên pattern trả `false`.

Nếu gán `value = Integer.valueOf(7)`, cùng câu lệnh sẽ khớp và biến `number` được ràng buộc với đối tượng `Integer`.

### Với interface cũng vậy

```java
CharSequence sequence = new StringBuilder("Hi");

if (sequence instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Không phải String");
}
```

Mã hợp lệ: `CharSequence` có những triển khai khác nhau, trong đó có `String`. Nhưng đối tượng runtime là `StringBuilder`, nên kết quả là `false` và in `Không phải String`.

Đây là cách phân biệt rõ ràng giữa **tương thích kiểu có thể có** với **phép khớp thực sự thành công**.

## 5. Lỗi biên dịch loại 1: các kiểu tĩnh không thể chuyển đổi phù hợp

Java không chấp nhận mọi phép so sánh kiểu tùy ý. Với type pattern, kiểu tĩnh của biểu thức phải có khả năng tương thích với kiểu pattern theo quy tắc kiểm tra chuyển kiểu của ngôn ngữ.

**Ví dụ không biên dịch trên Java 17:**

```java
Integer count = 12;

// KHÔNG HỢP LỆ:
// if (count instanceof String text) {
//     System.out.println(text.length());
// }
```

`Integer` và `String` đều là các lớp `final` riêng biệt, không có quan hệ kế thừa cho phép một đối tượng `Integer` đồng thời trở thành `String`. Trình biên dịch có đủ thông tin để từ chối trước khi chạy.

So sánh với biến có kiểu `Object`:

```java
Object count = Integer.valueOf(12);
if (count instanceof String text) {
    System.out.println(text);
}
// Hợp lệ, nhưng điều kiện trả false ở runtime.
```

Khi nguồn có kiểu `Object`, trình biên dịch không thể kết luận tất cả giá trị runtime đều không phải `String`: một giá trị `Object` khác có thể trỏ tới `String`. Vì vậy phép thử được chấp nhận.

**Lưu ý:** không phải cứ tên hai kiểu khác nhau là lỗi. Một lớp và lớp con, hoặc một lớp và interface mà các đối tượng có thể triển khai, vẫn có thể tạo ra phép kiểm tra hợp lệ. Hãy xét **khả năng chuyển đổi kiểu theo Java**, không suy luận từ tên kiểu.

### Kiểu nguyên thủy trong bài toán Java 17

Trên Java 17, biểu thức bên trái của `instanceof` phải có kiểu tham chiếu hoặc kiểu `null`; type pattern trong bài này dùng kiểu tham chiếu:

```java
int age = 21;

// KHÔNG BIÊN DỊCH trên Java 17:
// if (age instanceof Integer n) { ... }
```

Muốn dùng `instanceof` ở ví dụ kiểu số đã đóng hộp, có thể khai báo:

```java
Object age = Integer.valueOf(21);

if (age instanceof Integer n) {
    System.out.println(n + 1); // 22
}
```

`int` và `Integer` là hai kiểu khác nhau: `Integer` là kiểu tham chiếu bao đối tượng số nguyên; `int` là kiểu nguyên thủy. Đừng nhầm quy tắc Java 17 này với các thay đổi ngôn ngữ ở phiên bản Java mới hơn.

## 6. Lỗi biên dịch loại 2: type pattern đã chắc chắn khớp theo kiểu tĩnh

Một nguyên tắc đặc biệt của **pattern `instanceof` trong Java 17**: nếu kiểu tĩnh `S` của biểu thức bên trái đã là kiểu con của kiểu `T` trong pattern, biểu thức bị từ chối. Mục đích là loại bỏ một phép kiểm tra mẫu không có ích cho giá trị khác `null`.

```java
String value = "Java";

// KHÔNG BIÊN DỊCH:
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
```

Vì `value` đã có kiểu tĩnh `String`, người viết mã có thể dùng trực tiếp `value.length()`.

Quy tắc còn áp dụng khi kiểu pattern là kiểu cha:

```java
String value = "Java";

// KHÔNG BIÊN DỊCH trên Java 17:
// if (value instanceof CharSequence chars) {
//     System.out.println(chars.length());
// }
```

`String` triển khai `CharSequence`, nên một giá trị `String` khác `null` luôn là `CharSequence`; type pattern trên bị coi là kiểm tra thừa.

**Nhưng** phép `instanceof` truyền thống không tạo biến pattern có thể vẫn hợp lệ:

```java
String value = "Java";

System.out.println(value instanceof String);       // true
System.out.println(value instanceof CharSequence); // true
```

Vì vậy, hãy phân biệt cụ thể **`value instanceof String`** với **`value instanceof String text`** khi gặp lỗi biên dịch.

### Trường hợp kiểm tra lớp con thì hợp lệ

```java
Number value = Integer.valueOf(5);

if (value instanceof Integer integer) {
    System.out.println(integer * 2); // 10
}
```

Kiểu tĩnh `Number` **không** là kiểu con của `Integer`; đối tượng `Number` có thể là `Integer`, `Double`, v.v. Do đó phép thử có ích và hợp lệ.

## 7. Lỗi biên dịch loại 3: dùng generic không thể kiểm tra đầy đủ khi chạy

Java dùng cơ chế **xóa kiểu (type erasure)** cho phần lớn thông tin tham số hóa generic. Trong trường hợp nguồn có kiểu `Object`, không thể kiểm tra trực tiếp bằng type pattern rằng một giá trị là `List<String>`:

```java
Object value = java.util.List.of("a", "b");

// KHÔNG BIÊN DỊCH:
// if (value instanceof java.util.List<String> texts) {
//     System.out.println(texts.size());
// }
```

Kiểu tham số hóa `List<String>` không phải một kiểu *reifiable* phù hợp để kiểm tra theo cách này tại runtime. Thay vào đó, hãy kiểm tra `List<?>`:

```java
Object value = java.util.List.of("a", "b");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
```

Khi mẫu `List<?> items` khớp, Java chỉ bảo đảm rằng giá trị là một `List`; **không bảo đảm** từng phần tử là `String`:

```java
Object value = java.util.List.of(1, 2);

if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
// Không in gì: list khớp, nhưng từng phần tử Integer không khớp String.
```

Lỗi ở `List<String>` không có nghĩa một danh sách thực tế chứa số nguyên sẽ làm phép `instanceof List<?>` báo lỗi. Phép thử `List<?>` vẫn **hợp lệ** và có thể là `true`; muốn kiểm tra nội dung cần kiểm tra thêm từng phần tử.

## 8. Lỗi biên dịch loại 4: phạm vi của biến pattern không được bảo đảm

Ngay cả khi bản thân phép thử `instanceof` hợp lệ, **cách dùng biến pattern** có thể khiến toàn bộ mã không biên dịch.

Ví dụ lỗi:

```java
Object value = "Java";

// KHÔNG BIÊN DỊCH:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("Done");
// }
```

Toán tử `||` chỉ đánh giá vế phải khi vế trái `false`. Lúc đó type pattern `String text` **không khớp**, nên biến `text` không được sử dụng ở vế phải.

Cách viết hợp lệ khi muốn kiểm tra chuỗi không rỗng:

```java
Object value = "Java";

if (value instanceof String text && !text.isBlank()) {
    System.out.println(text); // Java
}
```

Vế phải của `&&` chỉ chạy khi phép kiểm tra `instanceof` đã thành công. Đây là **quy tắc phạm vi theo luồng điều khiển** (*flow scoping*), không liên quan đến việc runtime có trả `false` hay không. Mã dùng biến pattern sai phạm vi sẽ bị chặn ngay lúc biên dịch.

Cũng có thể viết điều kiện loại trừ sớm:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip();
}
```

`text` hợp lệ ở vế phải `||` vì để tới đó, biểu thức phủ định `!(value instanceof String text)` phải là `false`, tức pattern đã khớp. Sau `if`, các đường đi không hợp lệ đều đã `return`, nên `text` được bảo đảm.

## 9. Bảng đối chiếu: khi nào lỗi biên dịch, khi nào trả `false`?

Các ví dụ trong bảng được xét theo Java 17; mỗi dòng giả sử biến được khai báo như mô tả, không trộn khai báo trùng tên vào cùng block.

| Đầu vào và biểu thức | Biên dịch? | Kết quả/giải thích |
| --- | --- | --- |
| `Object x = null; x instanceof String s` | Có | `false`: `null` không khớp |
| `Object x = 7; x instanceof String s` | Có | `false`: runtime là `Integer` |
| `Object x = "Hi"; x instanceof String s` | Có | `true`: runtime là `String` |
| `Number n = 2.5; n instanceof Integer i` | Có | `false`: runtime là `Double` |
| `Number n = 2; n instanceof Integer i` | Có | `true`: runtime là `Integer` |
| `CharSequence c = new StringBuilder("a"); c instanceof String s` | Có | `false`: runtime là `StringBuilder` |
| `Integer n = 7; n instanceof String s` | Không | Kiểu tĩnh và kiểu pattern không chuyển đổi phù hợp |
| `String s = "Hi"; s instanceof String t` | Không | Type pattern thừa: kiểu tĩnh đã là `String` |
| `String s = null; s instanceof String t` | Không | Vẫn lỗi theo kiểu tĩnh, dù giá trị đang là `null` |
| `String s = "Hi"; s instanceof String` | Có | `true`: đây là phép kiểm tra kiểu truyền thống |
| `Object x = List.of("a"); x instanceof List<String> l` | Không | Không thể kiểm tra kiểu tham số hóa này |
| `Object x = List.of("a"); x instanceof List<?> l` | Có | `true`: kiểm tra `List`, không kiểm tra kiểu phần tử |
| `int n = 1; n instanceof Integer i` | Không | Kiểu nguồn nguyên thủy không hợp lệ theo Java 17 |
| `x instanceof String s || s.isEmpty()` với `Object x` | Không | Vế phải có thể chạy khi pattern chưa khớp |

`List` trong bảng viết tắt cho `java.util.List` hoặc được import từ `java.util.List`. Các ô bảng là **mảnh biểu thức minh họa**, không phải một tệp Java độc lập.

## 10. Ví dụ Java 17 hoàn chỉnh: những phép thử hợp lệ và kết quả thực tế

Tạo tệp **`FalseVsCompileDemo.java`**:

```java
import java.util.List;

public class FalseVsCompileDemo {

    static String describe(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text.length();
        }
        if (value instanceof Integer number) {
            return "INTEGER:" + number;
        }
        if (value instanceof List<?> items) {
            return "LIST:" + items.size();
        }
        return "NO_MATCH";
    }

    static String numberKind(Number value) {
        if (value instanceof Integer number) {
            return "INT:" + number;
        }
        return "OTHER_NUMBER";
    }

    static String normalize(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "INVALID";
        }
        return "OK:" + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(3.14));
        System.out.println(describe(List.of("a", "b")));
        System.out.println(describe(null));

        System.out.println(numberKind(3));
        System.out.println(numberKind(3.0));

        System.out.println(normalize("  X  "));
        System.out.println(normalize("   "));
        System.out.println(normalize(null));
    }
}
```

Biên dịch bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 FalseVsCompileDemo.java
java FalseVsCompileDemo
```

Kết quả đầu ra chính xác:

```text
TEXT:4
INTEGER:7
NO_MATCH
LIST:2
NO_MATCH
INT:3
OTHER_NUMBER
OK:X
INVALID
INVALID
```

Giải thích:

1. `"Java"` khớp `String`, `text.length()` là 4.
2. `7` được đóng hộp thành `Integer` khi truyền vào tham số `Object`; nhánh `Integer number` khớp.
3. `3.14` được đóng hộp thành `Double`; vì không phải `String`, `Integer` hay `List`, các phép thử đều trả `false` và phương thức chọn `NO_MATCH`.
4. `List.of("a", "b")` khớp `List<?> items` và có 2 phần tử.
5. `null` không khớp bất kỳ type pattern nào trong `describe`.
6. Với tham số kiểu tĩnh `Number`, kiểm tra `Integer` hợp lệ; `3` khớp `Integer`, còn `3.0` là `Double` nên trả `OTHER_NUMBER`.
7. `normalize` kết hợp `instanceof` phủ định, `||` và `return` để bỏ dữ liệu sai kiểu, chuỗi trắng hoặc `null` mà không truy cập biến pattern chưa khớp.

Chương trình chỉ chứa các biểu thức hợp lệ; **các đoạn cố ý gây lỗi biên dịch ở những phần trước không được chép vào tệp này**. Nếu muốn quan sát thông báo của `javac`, hãy thử từng đoạn lỗi trong một tệp thí nghiệm riêng và sửa lại trước khi chạy chương trình hoàn chỉnh.

## 11. `false` của `instanceof` khác với ngoại lệ ép kiểu

Một phép `instanceof` hợp lệ **không ném `ClassCastException` chỉ vì mẫu không khớp**:

```java
Object value = Integer.valueOf(9);

if (value instanceof String text) {
    System.out.println(text);
} else {
    System.out.println("Không phải String");
}
```

Đoạn trên in `Không phải String`.

Ngược lại, một phép ép kiểu tường minh có thể được trình biên dịch cho phép nhưng **thất bại khi chạy**:

```java
Object value = Integer.valueOf(9);

// Có thể biên dịch, nhưng nếu chạy sẽ ném ClassCastException:
// String text = (String) value;
```

Khi ép kiểu `Object` thành `String`, trình biên dịch cho phép vì kiểu tĩnh `Object` không bác bỏ khả năng runtime là `String`. Nhưng đối tượng hiện tại là `Integer`, nên phép ép kiểu thất bại ở runtime.

Có thể phân biệt ba loại kết quả:

| Trường hợp | Ví dụ | Điều xảy ra |
| --- | --- | --- |
| Lỗi biên dịch | `Integer n = 1; n instanceof String s` | Không chạy được |
| Kiểm tra kiểu hợp lệ, không khớp | `Object x = 1; x instanceof String s` | Kết quả `false`; không ném ngoại lệ |
| Ép kiểu tường minh hợp lệ về cú pháp nhưng sai runtime | `Object x = 1; String s = (String) x;` | Ném `ClassCastException` |

Điều này giải thích vì sao `instanceof` thường được dùng để **kiểm tra an toàn trước khi truy cập** một đối tượng dưới kiểu cụ thể.

## 12. Cách tự chẩn đoán khi thấy một phép `instanceof` không hoạt động

Thực hiện theo thứ tự sau:

1. **Xác nhận phiên bản Java.** Type pattern của `instanceof` đã ổn định từ Java 16; dùng JDK 17 trở lên và cấu hình đúng language level hoặc `--release 17`.
2. **Đọc kiểu tĩnh bên trái.** Biến khai báo là `Object`, `Number`, `String`, `Integer` hay interface nào? Đây là thông tin trình biên dịch nhìn thấy, khác đối tượng runtime.
3. **Kiểm tra kiểu trong pattern.** Kiểu bên phải có thể tương thích theo quy tắc Java không? Nếu hoàn toàn không thể chuyển kiểu thì lỗi biên dịch; nếu nguồn đã là kiểu con của kiểu pattern, type pattern cũng bị từ chối trên Java 17.
4. **Kiểm tra tính hợp lệ của generic.** `List<String>` không tự nhiên kiểm tra được ở runtime từ một `Object`; thử `List<?>` nếu cần nhận diện đối tượng danh sách.
5. **Kiểm tra phạm vi biến pattern.** Biến chỉ được dùng khi các đường đi tới vị trí đó đều đã xác nhận mẫu khớp. Lỗi `||`, `else` hoặc dùng biến ngoài nhánh thường là lỗi biên dịch riêng.
6. **Nếu mã đã biên dịch, quan sát giá trị runtime.** Giá trị có phải `null` không? Đối tượng là kiểu nào? Nó có thực sự thuộc kiểu pattern hoặc lớp con/triển khai phù hợp không? Khi không khớp, `instanceof` trả `false`.
7. **Không gộp `false` với ngoại lệ.** `false` là giá trị boolean hợp lệ; `ClassCastException` thường liên quan đến ép kiểu sai khi chạy; `NullPointerException` có thể đến từ việc sử dụng tham chiếu `null` sai cách.

Không nên “sửa” lỗi biên dịch bằng cách ép kiểu bừa bãi. Nếu một phép kiểm tra không thể có ý nghĩa với kiểu tĩnh hiện tại, hãy xem lại cách khai báo kiểu, thiết kế interface, hoặc đường đi dữ liệu.

## 13. Thực hành: dự đoán “lỗi biên dịch”, `true` hay `false`

### Bài 1: cùng một giá trị, hai kiểu tĩnh

**A:**

```java
Object x = Integer.valueOf(10);
boolean result = x instanceof String s;
```

**B:**

```java
Integer x = Integer.valueOf(10);
// boolean result = x instanceof String s;
```

**Đáp án:** A biên dịch được và `result == false`. Nếu bỏ chú thích ở B thì lỗi biên dịch do kiểu `Integer` và `String` không tương thích cho phép thử này. Giá trị runtime đều là `Integer`, nhưng kiểu tĩnh khác nhau.

### Bài 2: `null` và quy tắc type pattern dư thừa

**A:**

```java
Object x = null;
boolean result = x instanceof String s;
```

**B:**

```java
String x = null;
// boolean result = x instanceof String s;
```

**Đáp án:** A hợp lệ, trả `false`. B vẫn lỗi biên dịch nếu bỏ chú thích, vì kiểu tĩnh `String` đã là kiểu con (chính nó) của kiểu pattern `String`. `null` không phải ngoại lệ đối với quy tắc biên dịch đó.

### Bài 3: kiểm tra lớp con của `Number`

```java
Number a = Double.valueOf(4.5);
Number b = Integer.valueOf(4);

boolean one = a instanceof Integer i;
boolean two = b instanceof Integer j;
```

**Đáp án:** Cả hai biểu thức đều biên dịch. `one == false` vì `a` thực tế là `Double`, còn `two == true` vì `b` thực tế là `Integer`.

### Bài 4: generic và phạm vi biến

Giả sử `Object x = java.util.List.of("hi")`:

```java
// Không biên dịch trong trường hợp này:
// if (x instanceof java.util.List<String> words) { ... }

// Hợp lệ:
if (x instanceof java.util.List<?> words) {
    System.out.println(words.size());
}
```

Kết quả đoạn hợp lệ là `1`. Mẫu `List<?>` xác nhận kiểu danh sách, không xác nhận từng phần tử là `String`.

### Bài 5: chọn cách xử lý hợp lệ

Viết một phương thức `String greeting(Object candidate)` thỏa:

- Nếu `candidate` là một `String` không rỗng sau `strip()`, trả `"Hello "` ghép với chuỗi đã chuẩn hóa.
- Với đối tượng khác kiểu, chuỗi trắng và `null`, trả `"UNKNOWN"`.
- Không dùng ép kiểu tường minh và không gọi phương thức trên biến pattern ở nhánh chưa khớp.

Một lời giải:

```java
static String greeting(Object candidate) {
    if (!(candidate instanceof String name) || name.isBlank()) {
        return "UNKNOWN";
    }
    return "Hello " + name.strip();
}
```

Hàm trả `"Hello An"` cho `"  An "`, và `"UNKNOWN"` cho `null`, `123` hoặc `"   "`. Mã biên dịch trên Java 17.

## 14. Ghi nhớ cốt lõi

Đối với type pattern trong Java 17, hãy tách **hai giai đoạn** rõ ràng:

**Giai đoạn biên dịch:** Java kiểm tra tính hợp lệ của kiểu tĩnh bên trái so với pattern bên phải; loại các phép thử không thể tương thích, các type pattern đã thừa theo kiểu tĩnh, các kiểu generic không phù hợp và các trường hợp dùng biến pattern sai phạm vi. Khi có lỗi ở giai đoạn này, chương trình không có kết quả `true` hoặc `false` cho biểu thức bị lỗi.

**Giai đoạn chạy:** Sau khi đã biên dịch hợp lệ, `instanceof` xét đối tượng thực tế. Nếu là `null` hoặc không phù hợp với kiểu pattern, biểu thức trả `false`; nếu phù hợp thì trả `true` và biến pattern được ràng buộc để dùng ở phạm vi hợp lệ.

**Câu nhớ nhanh:** *“Không thể kiểm tra hợp lệ theo kiểu tĩnh” là lỗi biên dịch; “kiểm tra hợp lệ nhưng giá trị runtime không khớp” là `false`.* Hiểu đúng ranh giới này giúp chẩn đoán lỗi Java nhanh hơn và tránh nhầm `null`, không tương thích kiểu với các lỗi runtime do ép kiểu.

## Tài liệu tham khảo chính thức

- [Java SE 17 Language Specification §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [Java SE 17 Language Specification §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
- [Java SE 17 Language Specification §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
