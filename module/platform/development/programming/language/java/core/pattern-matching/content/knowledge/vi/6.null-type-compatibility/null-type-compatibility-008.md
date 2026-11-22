# Pattern không thể áp dụng do quan hệ subtype trong Java

## 1. Vì sao một type pattern có thể bị từ chối?

Với `instanceof`, Java có hai hình thức dễ nhầm lẫn:

```java
value instanceof String       // Kiểm tra kiểu, không khai báo biến
value instanceof String text  // Type pattern, có biến pattern text
```

Dòng trên chỉ là **minh họa biểu thức**; chúng phải xuất hiện trong một vị trí hợp lệ như điều kiện `if` hoặc phép gán Boolean. Đối với type pattern, trình biên dịch xét **kiểu tĩnh** của biểu thức bên trái và **kiểu của pattern** bên phải để quyết định có thể áp dụng pattern hay không.

Gọi:

- **S** là kiểu tĩnh của biểu thức cần kiểm tra, được xác định lúc biên dịch.
- **T** là kiểu được khai báo trong type pattern `T name`.
- **S <: T** nghĩa là `S` là subtype của `T`, bao gồm trường hợp `S` và `T` là cùng một kiểu. Ví dụ: `String <: CharSequence`, `String <: Object`, và `String <: String`.

**Điểm quan trọng theo phiên bản:** trong **Java 16–20 (bao gồm Java 17)**, biểu thức `e instanceof T name` bị **lỗi biên dịch nếu S <: T**. Lý do là phép kiểm tra kiểu này đã được xác định là đúng đối với mọi giá trị **khác `null`** của kiểu `S`, nên không phải phép kiểm tra thu hẹp kiểu cần thiết. Từ **Java 21**, Java cho phép những type pattern như vậy (thường gọi là *unconditional type pattern*); khi dùng với `instanceof`, giá trị `null` vẫn cho kết quả `false`.

Vì thế, **không được nói chung rằng phép thử subtype bằng pattern luôn bị cấm trong mọi phiên bản Java**. Khi học hoặc biên dịch dự án Java 17, phải áp dụng quy tắc Java 17; khi dùng Java 21+, cần hiểu quy tắc đã thay đổi.

## 2. Java 17: kiểu tĩnh đã là subtype thì pattern bị lỗi

Ví dụ minh họa đặt trong một phương thức Java 17:

```java
String text = "java";

// LỖI BIÊN DỊCH trên Java 17:
if (text instanceof String sameText) {
    System.out.println(sameText);
}

// CŨNG LỖI BIÊN DỊCH trên Java 17:
if (text instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

**Vì sao cả hai đều lỗi?**

1. Ở đoạn đầu, kiểu tĩnh của `text` là `String` và kiểu pattern cũng là `String`: `String <: String`.
2. Ở đoạn sau, kiểu tĩnh vẫn là `String`; `String` triển khai `CharSequence`, nên `String <: CharSequence`.
3. Nếu `text` khác `null`, cả hai phép kiểm tra kiểu sẽ đều đúng. Java 17 từ chối việc dùng **type pattern có biến** cho các kiểm tra kiểu này ngay ở bước biên dịch.

Thông báo chẩn đoán có thể thay đổi theo phiên bản trình biên dịch, chẳng hạn nêu rằng kiểu biểu thức là subtype của kiểu pattern hoặc rằng *unconditional patterns in instanceof* không được hỗ trợ trong mức nguồn Java 17. Đây là **lỗi compile time**, không phải `ClassCastException` hay `NullPointerException` lúc chạy.

### Cùng ý định, cách viết đúng trên Java 17

Nếu đã có biến `String` và chỉ muốn xử lý khi nó khác `null`:

```java
String text = "java";

if (text != null) {
    System.out.println(text.length());
}
```

Nếu cần một tên cục bộ khác trong nhánh:

```java
String text = "java";

if (text != null) {
    CharSequence chars = text;
    System.out.println(chars.length());
}
```

Kiểu `String` đã biết ngay từ đầu nên không cần gắn lại bằng type pattern. Phép gán từ `String` sang `CharSequence` là **widening reference conversion**, hợp lệ vì `String` là subtype của `CharSequence`.

### Dùng `instanceof` thông thường vẫn khác type pattern

```java
String text = "java";

// HỢP LỆ trên Java 17:
if (text instanceof CharSequence) {
    System.out.println(text.length());
}
```

Dạng `instanceof CharSequence` chỉ **kiểm tra kiểu**, không khai báo biến pattern. Quy tắc cấm type pattern trong trường hợp `S <: T` của Java 17 **không được đồng nhất** với quy tắc dành cho phép kiểm tra kiểu `instanceof T` thông thường.

Tuy cú pháp này hợp lệ, nó vẫn là kiểm tra thừa nếu bạn chỉ muốn xác nhận `text` là `CharSequence`: khi `text` khác `null` thì quan hệ subtype đã bảo đảm điều đó.

## 3. Đảo chiều quan hệ: kiểm tra từ supertype sang subtype là hợp lệ

So sánh với đoạn sau trên Java 17:

```java
Object value = "java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Dòng trên **hợp lệ** vì **kiểu tĩnh** của `value` là `Object`, còn pattern yêu cầu `String`. Tại runtime, `value` có thể là một `String`, một `Integer`, một đối tượng khác hoặc `null`. Phép kiểm tra thực sự có ý nghĩa để **thu hẹp từ supertype sang subtype** và chỉ gắn biến `text` khi thành công.

Đoạn tiếp theo cũng hợp lệ:

```java
CharSequence sequence = "java";

if (sequence instanceof String text) {
    System.out.println(text.length());
}
```

Mặc dù đối tượng runtime hiện tại là chuỗi `"java"`, **kiểu tĩnh** của `sequence` vẫn là `CharSequence`. Một `CharSequence` khác, như `StringBuilder`, có thể không phải `String`. Vì vậy Java 17 chấp nhận `sequence instanceof String text`.

Đây là khác biệt quan trọng giữa **kiểu khai báo của biến** và **lớp thực tế của đối tượng**. Trình biên dịch quyết định tính hợp lệ của cú pháp dựa trên kiểu tĩnh; chỉ sau đó, lúc chạy, `instanceof` mới kiểm tra giá trị cụ thể.

### Không nên cố mở rộng kiểu chỉ để “qua” lỗi

Có thể viết:

```java
String text = "java";
Object value = text;

if (value instanceof String matched) {
    System.out.println(matched.length());
}
```

Đoạn này biên dịch được trên Java 17 vì `value` có kiểu tĩnh `Object`. Nhưng nếu dữ liệu vốn đã được biết là `String` thì việc thêm biến `Object` chỉ để sử dụng pattern là **không cần thiết**. Giữ nguyên kiểu `String` và kiểm tra `null` khi cần sẽ rõ ràng hơn.

## 4. Phân biệt hai loại lỗi tương thích kiểu

Đừng gộp mọi lỗi `instanceof` pattern thành một nguyên nhân. Có ít nhất hai tình huống khác nhau.

### Trường hợp A: S đã là subtype của T — kiểm tra thừa trên Java 17

```java
String text = "hello";

// Lỗi Java 17: String là subtype của CharSequence.
// if (text instanceof CharSequence chars) { ... }
```

Pattern đặt ra điều kiện kiểu không cần thu hẹp. Java 17 từ chối type pattern có biến này. Java 21+ cho phép.

### Trường hợp B: kiểu không thể chuyển đổi phù hợp — pattern không thể khớp

```java
String text = "hello";

// Lỗi biên dịch cả Java 17 và Java 21:
// if (text instanceof Integer number) { ... }
```

Ở đây `String` và `Integer` là các lớp không có khả năng chuyển đổi cast giữa nhau theo kiểu kiểm tra này. Kiểm tra không thể thành công, và trình biên dịch từ chối.

**Khác biệt:** trường hợp A là kiểu đã biết *đủ rộng để thỏa pattern* đối với mọi giá trị không `null`. Trường hợp B là kiểu đã biết *không thể thỏa pattern*. Hai lý do đều liên quan đến kiểu, nhưng không giống nhau.

Khi nói hai kiểu “không có quan hệ subtype”, **chưa đủ để kết luận luôn có lỗi**: các quan hệ interface và quy tắc cast compatibility của Java cũng phải được xét. Ví dụ một kiểu giao diện có thể có các lớp triển khai khác nhau, nên phép kiểm tra runtime có thể hợp lệ. Không nên áp dụng công thức đơn giản “không có extends trực tiếp tức là luôn sai”.

## 5. Bảng đối chiếu các quan hệ subtype

Giả sử kiểm tra với type pattern `instanceof T name`:

| Kiểu tĩnh S | Kiểu pattern T | Java 17 | Java 21+ | Giải thích |
| --- | --- | --- | --- | --- |
| `String` | `String` | Lỗi biên dịch | Hợp lệ | Hai kiểu trùng nhau; giá trị khác `null` khớp |
| `String` | `CharSequence` | Lỗi biên dịch | Hợp lệ | `String` là subtype của `CharSequence` |
| `String` | `Object` | Lỗi biên dịch | Hợp lệ | `String` là subtype của `Object` |
| `Object` | `String` | Hợp lệ | Hợp lệ | Phép kiểm tra thu hẹp kiểu có thể đúng hoặc sai |
| `CharSequence` | `String` | Hợp lệ | Hợp lệ | Không phải mọi `CharSequence` đều là `String` |
| `Number` | `Integer` | Hợp lệ | Hợp lệ | Phép kiểm tra subtype ở runtime có ý nghĩa |
| `Integer` | `Number` | Lỗi biên dịch | Hợp lệ | `Integer` là subtype của `Number` |
| `String` | `Integer` | Lỗi biên dịch | Lỗi biên dịch | Hai lớp không tương thích để kiểm tra kiểu theo pattern |

Trong bảng này, xét type pattern tham chiếu thông thường, không xét các trường hợp generic phức tạp, pattern lồng nhau hay tính năng preview cho primitive. Một pattern còn phải thỏa các quy tắc cú pháp và phạm vi biến khác.

**Lưu ý:** dùng `var text = "java";` sẽ khiến `text` được suy luận kiểu `String`. Vì vậy trên Java 17, `text instanceof CharSequence chars` vẫn bị lỗi như khi khai báo rõ `String text`. Từ khóa `var` không biến kiểu tĩnh thành `Object`.

## 6. Vai trò của `null` trong phép kiểm tra kiểu

Quan hệ subtype nói về các kiểu, nhưng một **biến tham chiếu** có thể mang giá trị `null`:

```java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không khớp");
}
```

Đoạn này hợp lệ trong Java 17 và in:

```text
Không khớp
```

Khi toán hạng của `instanceof` là `null`, phép thử với type pattern tham chiếu như `String text` trả về **`false`** và không gắn biến `text`.

Đối với Java 21+, ngay cả khi kiểu tĩnh của toán hạng đã là subtype của kiểu pattern (nên pattern được phép dùng), **`null` cũng không làm cho `instanceof` thành `true`**. Chẳng hạn một `String` nhận giá trị `null` vẫn không khớp `instanceof String text`.

Đừng nhầm “unconditional type pattern” trong phân tích tính tương thích kiểu với việc `instanceof` chấp nhận `null`. Trong ngữ cảnh `instanceof`, kiểm tra `null` vẫn có tác động đến kết quả. Nếu mục tiêu chỉ là phân biệt một tham chiếu `String` đã biết kiểu với `null` trên Java 17, hãy viết `text != null`.

## 7. Chương trình Java 17 hoàn chỉnh và chạy được

Tạo tệp **`SubtypeRelationDemo.java`**:

```java
public class SubtypeRelationDemo {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(" + text.length() + "): " + text;
        }
        if (value instanceof Integer number) {
            return "Integer next: " + (number + 1);
        }
        return "Other";
    }

    static String describeSequence(CharSequence sequence) {
        if (sequence instanceof String text) {
            return "String chars: " + text.length();
        }
        return sequence == null ? "Sequence null" : "Sequence not String";
    }

    static String handleKnownString(String text) {
        if (text == null) {
            return "Missing";
        }
        return "Upper: " + text.toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(describeSequence("hi"));
        System.out.println(describeSequence(new StringBuilder("ab")));
        System.out.println(handleKnownString("ok"));
        System.out.println(handleKnownString(null));
    }
}
```

Biên dịch với mức nguồn Java 17 (có thể dùng JDK mới hỗ trợ `--release 17`):

```bash
javac --release 17 SubtypeRelationDemo.java
java SubtypeRelationDemo
```

Stdout chính xác:

```text
String(4): java
Integer next: 13
Other
String chars: 2
Sequence not String
Upper: OK
Missing
```

**Giải thích từng nhóm:**

1. `describe(Object)` nhận kiểu tĩnh `Object`; kiểm tra `String` và `Integer` đều là phép kiểm tra thu hẹp kiểu hợp lệ trên Java 17. `12` được autoboxing thành `Integer` khi truyền vào tham số `Object`.
2. `describe(null)` trả `Other` vì `null` không khớp với bất kỳ type pattern tham chiếu nào trong hai điều kiện.
3. `describeSequence(CharSequence)` nhận kiểu tĩnh `CharSequence`. Một đối tượng `String` như `"hi"` khớp; một `StringBuilder` không khớp `String` mặc dù nó cũng triển khai `CharSequence`.
4. `handleKnownString(String)` đã nhận tham số kiểu `String`. Thay vì một type pattern dư thừa và không hợp lệ với Java 17, phương thức kiểm tra `text == null` rồi dùng trực tiếp `String.toUpperCase()`.

Điểm mấu chốt là **cùng một đối tượng chuỗi vẫn có thể xuất hiện trong biểu thức pattern hợp lệ hay không hợp lệ tùy kiểu tĩnh của toán hạng và phiên bản Java**. Ví dụ `Object value = "java"` cho phép thu hẹp kiểu bằng pattern trong Java 17, còn `String value = "java"` không cho phép type pattern `String text` ở mức nguồn Java 17.

## 8. Java 21+: subtype type pattern đã được chấp nhận

Trong Java 21, quy tắc áp dụng pattern đã được điều chỉnh. Đoạn sau **biên dịch trực tiếp với Java 21**, không cần bật preview:

Tạo tệp **`UnconditionalPatternJava21.java`**:

```java
public class UnconditionalPatternJava21 {
    static String describe(String input) {
        if (input instanceof CharSequence chars) {
            return "Length: " + chars.length();
        }
        return "Null";
    }

    static String sameType(String input) {
        if (input instanceof String text) {
            return "Text: " + text;
        }
        return "Null";
    }

    public static void main(String[] args) {
        System.out.println(describe("abc"));
        System.out.println(describe(null));
        System.out.println(sameType("ok"));
    }
}
```

Lệnh chạy:

```bash
javac --release 21 UnconditionalPatternJava21.java
java UnconditionalPatternJava21
```

Stdout chính xác:

```text
Length: 3
Null
Text: ok
```

Ở `describe("abc")`, kiểu tĩnh của `input` là `String` và pattern là `CharSequence chars`: Java 21 cho phép dùng pattern kiểu rộng hơn. Với `describe(null)`, `instanceof` trả `false` và hàm trả `"Null"`. Ở `sameType("ok")`, pattern và kiểu tĩnh đều là `String` nhưng vẫn hợp lệ trong Java 21.

Điều này **khác với quy tắc từ Java 16 đến Java 20**, nơi kiểu tĩnh là subtype của pattern sẽ gây lỗi. Nếu bạn chạy `javac --release 17 UnconditionalPatternJava21.java`, trình biên dịch sẽ từ chối những biểu thức pattern này vì mức nguồn 17. Cũng vì vậy, chỉ nhìn vào **phiên bản JDK đang cài** mà bỏ qua cờ `--release` hoặc mức ngôn ngữ của dự án có thể dẫn đến kết luận sai.

Dù Java 21+ cho phép, việc kiểm tra từ `String` sang `CharSequence` thường không bổ sung thông tin kiểu mới. Nếu chỉ xử lý một `String` đã biết kiểu, một điều kiện `input != null` vẫn có thể rõ ràng hơn.

## 9. Cách đọc lỗi và sửa đúng nguyên nhân

Khi thấy lỗi quanh `instanceof T name`, kiểm tra theo trình tự:

1. **Xác định phiên bản ngôn ngữ:** dự án dùng `--release 17`, `--source 17`, Java 21 hay cấu hình nào khác? Với quan hệ subtype, đây là yếu tố quyết định.
2. **Xác định kiểu tĩnh S của toán hạng:** xem khai báo biến, kiểu trả về của phương thức hoặc kiểu suy luận từ `var`. Đừng suy luận chỉ từ đối tượng đang chứa lúc chạy.
3. **Xác định kiểu pattern T:** chẳng hạn `String`, `CharSequence`, `Integer`.
4. **So sánh chiều subtype:** nếu `S <: T`, Java 17 cấm type pattern đó, còn Java 21+ cho phép. Nếu `T <: S` và phép cast tương thích, đây thường là phép kiểm tra thu hẹp hợp lệ.
5. **Nếu hai kiểu không thể cast phù hợp:** biểu thức có thể bị từ chối ở mọi phiên bản vì bất tương thích kiểu. Cần sửa kiểu dữ liệu hoặc điều kiện, thay vì ép compiler chấp nhận một phép thử không thể đúng.
6. **Xác định yêu cầu nghiệp vụ:** muốn kiểm tra `null`, kiểm tra subtype runtime, hay chỉ cần truy cập thành viên của một kiểu đã biết? Viết điều kiện phản ánh đúng mục tiêu.

### Ví dụ sửa một lỗi subtype trong Java 17

**Trước — lỗi biên dịch theo Java 17:**

```java
static int lengthOrZero(String text) {
    // Không hợp lệ trên Java 17:
    // if (text instanceof CharSequence chars) {
    //     return chars.length();
    // }
    return 0;
}
```

Đây là đoạn minh họa lỗi đã được chú thích, chưa phải hàm thực hiện nghiệp vụ đúng với mọi đầu vào.

**Sau — đúng mục tiêu và hợp lệ trên Java 17:**

```java
static int lengthOrZero(String text) {
    return text == null ? 0 : text.length();
}
```

Hàm sửa trả về `0` nếu tham chiếu là `null`; nếu khác `null`, gọi trực tiếp `String.length()`. Không có phép kiểm tra kiểu thừa và không cần tạo biến pattern.

### Lỗi liên quan generic là câu chuyện khác

Ví dụ `value instanceof java.util.List<String> list` với `value` kiểu `Object` không hợp lệ trên Java 17 vì kiểu tham số `List<String>` không thể được kiểm tra đầy đủ ở runtime do **type erasure**. Cách kiểm tra hình dạng danh sách là `value instanceof java.util.List<?> list`, sau đó kiểm tra phần tử theo yêu cầu.

Lỗi về **type erasure** khác với lỗi **`S <: T`** nêu trong bài. Khi thấy một lỗi biên dịch, cần xác định chính xác quy tắc đang bị vi phạm thay vì mặc định mọi lỗi pattern đều do quan hệ subtype.

## 10. Tự kiểm tra

**Câu hỏi 1:** Dự án chạy Java 17. Mã sau biên dịch được không?

```java
CharSequence data = "abc";
if (data instanceof String text) {
    System.out.println(text.length());
}
```

**Đáp án:** Có. Kiểu tĩnh của `data` là `CharSequence`, pattern là `String`, nên đây là kiểm tra thu hẹp kiểu có ý nghĩa. Kết quả in ra là `3`.

**Câu hỏi 2:** Nếu đổi khai báo thành `String data = "abc";` và giữ `data instanceof String text` thì sao?

**Đáp án:** Trên **Java 17**, không biên dịch được vì `String <: String`. Từ **Java 21**, type pattern này được chấp nhận; khi giá trị khác `null`, điều kiện đúng.

**Câu hỏi 3:** `Object value = null;` đi với `value instanceof String text` có làm phát sinh `NullPointerException` không?

**Đáp án:** Không. Biểu thức trả `false`. Nhánh cần dùng `text` sẽ không chạy, nên không có tham chiếu `text` chưa được gắn.

**Ghi nhớ:** quan hệ subtype có **chiều**. Ở Java 17, khi kiểu tĩnh đã là subtype của kiểu pattern, type pattern `instanceof` có biến bị từ chối; còn khi toán hạng có kiểu rộng và pattern kiểm tra kiểu hẹp hơn, đó thường là trường hợp sử dụng đúng. Từ Java 21, quy tắc với pattern “đã chắc kiểu” được nới lỏng, nhưng ý nghĩa của `null` và các trường hợp hai kiểu bất tương thích vẫn phải được xem xét riêng.

### Tham khảo đặc tả ngôn ngữ

- [Java Language Specification 17, §15.20.2 — The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): nêu quy tắc lỗi biên dịch nếu kiểu toán hạng là subtype của kiểu pattern.
- [Java Language Specification 21, §15.20.2 — The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): áp dụng tính tương thích của pattern theo quy tắc mới.
- [Java Language Specification 21, §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): trình bày tính áp dụng được của pattern đối với một kiểu.