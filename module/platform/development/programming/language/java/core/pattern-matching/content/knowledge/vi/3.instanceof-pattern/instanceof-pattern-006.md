# Nhiều nhánh `instanceof` liên tiếp trong Java

**Phạm vi:** Java 17 trở lên; ví dụ chính sử dụng **pattern matching for `instanceof`**, tính năng ổn định từ Java 16. Mục tiêu là hiểu cách Java xử lý **nhiều phép kiểm tra `instanceof` trên cùng một đối tượng** theo thứ tự, sự khác biệt giữa `if` độc lập và chuỗi `if / else if`, cách chọn thứ tự kiểu, phạm vi biến pattern và những lỗi dễ gặp. Đây là một kỹ thuật kiểm tra kiểu khi chạy, không phải cơ chế phân phối đa hình thay thế mọi phương thức Java.

## 1. Một đối tượng có thể khớp nhiều phép kiểm tra `instanceof`

Toán tử `instanceof` kiểm tra giá trị một tham chiếu có tương thích với kiểu được chỉ định hay không. Với **type pattern**, phép kiểm tra còn gắn giá trị đã khớp vào một biến:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Trong `value instanceof String text`:

- `value` là biểu thức được kiểm tra; kiểu tĩnh là `Object`.
- `String text` là type pattern: yêu cầu giá trị là một `String` và khai báo biến `text`.
- Khi khớp, biểu thức `instanceof` trả về `true` và biến `text` có thể được dùng trong phạm vi mà trình biên dịch xác định chắc chắn đã khớp.
- Khi không khớp, biểu thức trả về `false`; biến pattern không được dùng ở đường đi chưa khớp.

**Không được nghĩ rằng mỗi đối tượng chỉ khớp duy nhất một kiểu.** Một `String` đồng thời là `CharSequence`, `Comparable<?>`, `Serializable` và `Object`; một `Integer` đồng thời là `Number`. Vì vậy hai lần kiểm tra riêng biệt có thể đều đúng.

Ví dụ minh họa:

```java
Object value = "Java";

System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof String);       // true
System.out.println(value instanceof Number);       // false
```

Ba biểu thức trên đều hợp lệ vì kiểu tĩnh `Object` cho phép kiểm tra các kiểu đích. Kết quả phụ thuộc **kiểu runtime** của giá trị, không đơn thuần phụ thuộc kiểu tĩnh `Object`.

## 2. Trường hợp 1: nhiều câu `if` độc lập liên tiếp

Khi viết các câu `if` **không gắn bằng `else`**, Java đánh giá **từng câu `if` từ trên xuống dưới**. Một điều kiện đúng không tự động bỏ qua các câu `if` phía sau.

```java
Object value = "Java";

if (value instanceof CharSequence chars) {
    System.out.println("CharSequence: " + chars.length());
}

if (value instanceof String text) {
    System.out.println("String: " + text.toUpperCase());
}
```

Kết quả:

```text
CharSequence: 4
String: JAVA
```

Cả hai nhánh chạy, vì `"Java"` thỏa cả hai kiểu. Điều này hữu ích nếu **mỗi nhánh biểu diễn một công việc độc lập**, chẳng hạn ghi nhận những đặc tính khác nhau mà đối tượng hỗ trợ.

Với cấu trúc này:

1. Java kiểm tra điều kiện của `if` thứ nhất.
2. Nếu đúng, Java thực hiện thân nhánh thứ nhất.
3. Khi thoát thân nhánh thứ nhất bình thường, Java **tiếp tục** tới câu `if` thứ hai và kiểm tra điều kiện của nó.
4. Quy trình lặp lại cho các câu `if` kế tiếp.

Một chi tiết quan trọng: nếu nhánh trước có `return`, `throw` hoặc một chuyển hướng điều khiển khác khiến chương trình không đi tiếp, những nhánh phía sau sẽ không được chạy. Và nếu code trong nhánh trước thay đổi trạng thái được nhánh sau đọc, điều kiện sau sẽ được đánh giá theo trạng thái **tại lúc đó**, không phải ảnh chụp trước chuỗi kiểm tra.

**Khi dùng:** cần thực hiện **tất cả hành động phù hợp** với các kiểu/interface mà đối tượng đáp ứng; muốn các điều kiện không loại trừ lẫn nhau.

**Khi không dùng:** chỉ mong một phân loại duy nhất hoặc một nhánh xử lý duy nhất. Dùng nhiều `if` độc lập trong trường hợp này dễ tạo kết quả bị ghi đè, hành động chạy hai lần hoặc log trùng.

## 3. Trường hợp 2: chuỗi `if / else if / else`

Chuỗi `if / else if` là cấu trúc **chọn một nhánh đầu tiên có điều kiện đúng**:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println("String: " + text.length());
} else if (value instanceof CharSequence chars) {
    System.out.println("CharSequence: " + chars.length());
} else if (value instanceof Number number) {
    System.out.println("Number: " + number.doubleValue());
} else {
    System.out.println("Unknown");
}
```

Kết quả:

```text
String: 4
```

Java đánh giá điều kiện từ trên xuống. Ngay khi gặp một nhánh đúng, Java chạy thân nhánh ấy rồi **bỏ qua toàn bộ `else if` và `else` còn lại**. Một đối tượng có thể thỏa nhiều kiểu, nhưng trong **một chuỗi** `if / else if` chỉ có tối đa **một nhánh** được thực hiện.

So sánh hai cấu trúc:

| Đặc điểm | Các `if` độc lập | Chuỗi `if / else if` |
| --- | --- | --- |
| Số nhánh có thể chạy | Không giới hạn ở một nhánh; có thể nhiều nhánh cùng chạy | Tối đa một nhánh |
| Nhánh sau có được kiểm tra nếu nhánh trước đúng? | Có, nếu luồng điều khiển tiếp tục tới đó | Không |
| Thứ tự ảnh hưởng thế nào? | Ảnh hưởng thứ tự hành động và trạng thái được quan sát | Ảnh hưởng trực tiếp nhánh được chọn |
| Phù hợp nhất | Các hành động độc lập, có thể đồng thời áp dụng | Phân loại hoặc chọn một cách xử lý duy nhất |
| Nhánh dự phòng | Mỗi `if` phải được xét riêng | `else` xử lý khi tất cả điều kiện trước đều sai |

### Vì sao thường phải kiểm tra kiểu cụ thể trước kiểu tổng quát?

`Integer` kế thừa `Number`. Nếu kiểm tra `Number` trước trong chuỗi `else if`, một `Integer` sẽ bị nhánh `Number` giữ lại ngay:

```java
Object value = 7;

// Hợp lệ về cú pháp, nhưng nhánh Integer không chạy với giá trị này:
if (value instanceof Number n) {
    System.out.println("Number");
} else if (value instanceof Integer i) {
    System.out.println("Integer");
}
```

Kết quả:

```text
Number
```

Nếu muốn xử lý riêng `Integer`, hãy đảo thứ tự:

```java
Object value = 7;

if (value instanceof Integer i) {
    System.out.println("Integer");
} else if (value instanceof Number n) {
    System.out.println("Number");
}
```

Kết quả:

```text
Integer
```

Nguyên tắc thực hành: **đặt kiểu/điều kiện đặc thù trước, kiểu/điều kiện bao quát sau** trong một chuỗi chọn một nhánh. Ví dụ, xử lý `String` trước `CharSequence`, hoặc `Integer` trước `Number`. Nếu yêu cầu nghiệp vụ cố tình ưu tiên một quy tắc tổng quát, có thể đặt nó trước; khi đó phải hiểu nó sẽ chặn những nhánh đặc thù được bao phủ.

Lưu ý: `if / else if` không yêu cầu mọi kiểu phải liên quan nhau. Có thể kiểm tra `String`, `Number` và `Runnable` liên tiếp trên một giá trị kiểu `Object` miễn là từng biểu thức `instanceof` hợp lệ về mặt kiểu.

## 4. Trường hợp 3: nhiều `if` nối tiếp với `return` sớm

Trong một phương thức trả về giá trị, các `if` độc lập có thể được tổ chức theo dạng **guard clauses**:

```java
static String classify(Object value) {
    if (value instanceof Integer i) {
        return "Integer: " + i;
    }
    if (value instanceof Number n) {
        return "Number: " + n;
    }
    if (value instanceof String s) {
        return "String: " + s;
    }
    return "Other";
}
```

Mỗi khi một nhánh khớp, `return` kết thúc phương thức. Vì thế, xét về hành vi **chọn kết quả**, dạng này tương tự chuỗi `if / else if`; nhưng không cần lồng các mức `else`. Các nhánh sau chỉ được xét khi tất cả nhánh trước đã đi qua mà chưa `return`.

Đừng áp dụng cách suy luận này nếu thân một nhánh không chắc chắn kết thúc phương thức. Ví dụ:

```java
if (value instanceof Number n) {
    System.out.println(n);
}
if (value instanceof Integer i) {
    System.out.println(i + 1);
}
```

Với `value = 7`, **cả hai** dòng đều được in; không có `return` nên không có hành vi chọn đúng một nhánh.

## 5. Nhánh có điều kiện bổ sung: `&&` và phân loại cùng một kiểu

Đôi khi nhiều nhánh liên tiếp kiểm tra **cùng một kiểu** nhưng phân biệt thêm điều kiện về nội dung. Dùng toán tử `&&` để biến pattern có sẵn ở vế phải:

```java
Object value = "  ";

if (value instanceof String s && !s.isBlank()) {
    System.out.println("Non-blank string");
} else if (value instanceof String s2) {
    System.out.println("Blank string");
} else {
    System.out.println("Not a string");
}
```

Kết quả:

```text
Blank string
```

Diễn giải:

- Ở nhánh thứ nhất, `value instanceof String s` đúng nhưng `!s.isBlank()` sai, nên **toàn bộ điều kiện** sai; Java xét nhánh kế.
- Ở nhánh thứ hai, `value instanceof String s2` vẫn đúng, nên nhánh này xử lý chuỗi blank.
- Nếu `value` không phải `String`, cả hai điều kiện đều sai và chương trình tới `else`.
- `s` và `s2` là **hai biến pattern khác nhau**, mỗi biến thuộc phạm vi riêng.

Với `&&`, vế phải chỉ chạy sau khi vế trái đúng (*short-circuit*), nên có thể dùng `s` an toàn. Ngược lại, đoạn sau **không biên dịch**:

```java
// SAI: vế phải của || có thể chạy khi pattern chưa khớp.
// if (value instanceof String s || s.isBlank()) {
//     System.out.println(s);
// }
```

Khi điều kiện khác kiểu loại trừ nhau, có thể dùng `&&` để đưa logic lọc vào đúng nhánh; không cần ép kiểu hoặc gọi `getClass()` thủ công.

## 6. Phạm vi của pattern variable khi có nhiều nhánh

Biến trong `instanceof` được gọi là **pattern variable**; phạm vi của nó được JLS xác định theo **luồng điều khiển** (*flow scoping*), không chỉ theo cặp ngoặc nhọn.

### Trong nhánh khớp

```java
static void printIfString(Object value) {
    if (value instanceof String text) {
        System.out.println(text.toUpperCase()); // Đúng
    } else if (value instanceof Integer number) {
        System.out.println(number + 1); // Đúng
    }
    // text và number không thể dùng tại đây.
}
```

`text` có giá trị ở thân nhánh `String`; `number` có giá trị ở thân nhánh `Integer`. Một nhánh không được tự ý dùng biến khai báo bởi nhánh khác.

### Sau khi nhánh không khớp thoát khỏi phương thức

```java
static void requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    // Đến đây, mọi đường đi bình thường đều đã khớp String text.
    System.out.println(text.length()); // Đúng
}
```

Phép phủ định `!` cùng với `throw` bảo đảm chương trình chỉ đi tiếp khi pattern đã khớp. Đây là một ví dụ khác về flow scoping, đặc biệt hữu ích khi muốn giảm mức lồng nhau.

### Lỗi phạm vi điển hình

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text) {
//     System.out.println(text);
// }
// System.out.println(text); // Không chắc pattern đã khớp.
```

Không nên tạo nhiều biến pattern cùng tên ở những phạm vi chồng lấn, hoặc giả định biến trong nhánh trên còn sử dụng được tại nhánh dưới. Khi mỗi nhánh có vai trò riêng, đặt tên như `text`, `integer`, `number` giúp đọc code và giảm nhầm lẫn.

## 7. Xử lý `null`, kiểu không khớp và kiểu chồng lấn

### Giá trị `null`

Với các ví dụ `instanceof` ở đây, `null` không khớp bất kỳ type pattern nào:

```java
Object value = null;

System.out.println(value instanceof String); // false
System.out.println(value instanceof Number); // false
```

Trong chuỗi `if / else if` có `else`, `null` đi đến `else` nếu không có điều kiện kiểm tra `value == null` trước đó. Nếu cần phân biệt `null` với một đối tượng lạ, thêm nhánh `value == null` riêng, thường ở đầu chuỗi khi đó là trường hợp nghiệp vụ ưu tiên. Không gọi phương thức trên `value` trước khi đã kiểm tra null.

### Các kiểu cùng khớp

Không chỉ quan hệ kế thừa lớp, các **interface** cũng tạo vùng chồng lấn. `String` vừa khớp `String`, vừa khớp `CharSequence`; `StringBuilder` khớp `CharSequence` nhưng không khớp `String`.

| Giá trị đầu vào (kiểu tĩnh `Object`) | `instanceof String` | `instanceof CharSequence` | `instanceof Number` | `instanceof Integer` |
| --- | --- | --- | --- | --- |
| `"Java"` | `true` | `true` | `false` | `false` |
| `new StringBuilder("Hi")` | `false` | `true` | `false` | `false` |
| `7` (đã boxing thành `Integer`) | `false` | `false` | `true` | `true` |
| `2.5` (đã boxing thành `Double`) | `false` | `false` | `true` | `false` |
| `null` | `false` | `false` | `false` | `false` |

Bảng này giúp dự đoán kết quả khi **nhiều phép kiểm tra cùng dùng một đối tượng**. Trong chuỗi `else if`, dù nhiều cột có thể là `true`, chỉ nhánh phù hợp xuất hiện sớm nhất mới chạy.

## 8. Ví dụ Java 17 hoàn chỉnh: chuỗi nhiều nhánh và nhiều `if` độc lập

Tạo tệp **`InstanceofBranchesDemo.java`** với nội dung sau:

```java
public class InstanceofBranchesDemo {
    static String describe(Object value) {
        // Chọn một nhánh: nhánh đầu tiên có điều kiện đúng sẽ thắng.
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text + " (" + text.length() + ")";
        } else if (value instanceof String blankText) {
            return "String blank";
        } else if (value instanceof Integer integer) {
            // Integer được xét trước Number vì Integer là Number.
            return "Integer: " + (integer + 1);
        } else if (value instanceof Number number) {
            return "Number: " + number.doubleValue();
        } else if (value instanceof CharSequence chars) {
            // StringBuilder đi vào nhánh này, không phải nhánh String.
            return "CharSequence: " + chars.length();
        } else if (value == null) {
            return "null";
        } else {
            return "Other";
        }
    }

    static void independentChecks(Object value) {
        // Cả hai câu if có thể cùng chạy với một String.
        if (value instanceof CharSequence chars) {
            System.out.println("CharSequence: " + chars.length());
        }
        if (value instanceof String text) {
            System.out.println("String: " + text.toUpperCase());
        }
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("   "));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(new StringBuilder("Hi")));
        System.out.println(describe(null));
        System.out.println(describe(true));
        independentChecks("abc");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 InstanceofBranchesDemo.java
java InstanceofBranchesDemo
```

Kết quả:

```text
String: Java (4)
String blank
Integer: 8
Number: 2.5
CharSequence: 2
null
Other
CharSequence: 3
String: ABC
```

Giải thích theo đúng thứ tự:

1. `"Java"` khớp `String text`, không blank nên trả về từ nhánh đầu tiên.
2. `"   "` khớp kiểu `String` nhưng không qua được `!text.isBlank()`; nhánh `String blankText` thứ hai được chọn.
3. Số nguyên `7` được boxing thành `Integer`; nhánh `Integer` được ưu tiên trước `Number` và cộng thêm 1.
4. Số thực `2.5` được boxing thành `Double`; không khớp `Integer` nhưng khớp `Number`.
5. `StringBuilder("Hi")` không phải `String`, nhưng là `CharSequence`, nên trả về độ dài 2.
6. `null` không khớp các type pattern và đi vào nhánh kiểm tra `value == null`.
7. `true` được boxing thành `Boolean`, không khớp các kiểu đã kiểm tra nên vào `else`.
8. `independentChecks("abc")` chạy cả nhánh `CharSequence` và nhánh `String`, in hai dòng cuối.

Ví dụ dùng các tính năng ổn định của Java 17 và không cần `--enable-preview`. Mỗi nhánh đều dùng trực tiếp biến pattern; không phải ép kiểu thủ công như `(String) value` hay `(Number) value`.

## 9. Các lỗi thường gặp khi xếp nhiều nhánh

**Lỗi 1 — dùng nhiều `if` nhưng mong chỉ chạy một nhánh.** Một `String` có thể khớp cả `CharSequence` và `String`. Hãy thay bằng chuỗi `else if` hoặc thêm `return` khi thực sự chỉ muốn một lựa chọn.

**Lỗi 2 — để kiểu cha/interface tổng quát trước kiểu cụ thể.** Ví dụ `Number` trước `Integer` trong chuỗi `else if` khiến giá trị `Integer` vào nhánh `Number` ngay, không đi xuống nhánh riêng. Thứ tự càng quan trọng khi nhiều nhánh cùng kiểm tra interface hoặc kiểu cha.

**Lỗi 3 — cho rằng `else if` luôn chạy sau nhánh trước.** Nó chỉ được đánh giá khi các điều kiện trước đều sai; nếu nhánh đầu đã đúng, phần còn lại của chuỗi bị bỏ qua.

**Lỗi 4 — dùng pattern variable ở nhánh chưa chắc khớp.** `text` chỉ sử dụng được ở vị trí mà trình biên dịch chứng minh nó đã được khởi tạo; không lấy biến từ nhánh `if` đầu tiên để dùng thẳng ở một nhánh `else if` khác.

**Lỗi 5 — nhầm `&&` và `||`.** Với `obj instanceof String s && s.length() > 0`, `s` hợp lệ ở vế phải; với `||` thì điều đó không đúng vì vế phải chạy khi pattern vế trái có thể thất bại.

**Lỗi 6 — thiếu trường hợp `null` và kiểu lạ.** Thêm `else`/giá trị mặc định; thêm điều kiện `obj == null` nếu cần xử lý `null` riêng.

**Lỗi 7 — kiểm tra các kiểu không thể chuyển đổi ngay từ kiểu tĩnh.** Ví dụ sau **không hợp lệ** về kiểu vì `String` là lớp `final`, không thể đồng thời là `Integer`:

```java
// KHÔNG BIÊN DỊCH:
// String value = "Java";
// if (value instanceof Integer n) { // Kiểu không tương thích
//     System.out.println(n);
// }
```

Nếu đầu vào cần chấp nhận nhiều loại dữ liệu, dùng kiểu tĩnh chung phù hợp (ví dụ `Object` hoặc interface/kiểu cha thích hợp) rồi kiểm tra tại runtime.

**Lỗi 8 — nghĩ `instanceof` hỗ trợ mọi tham số generic cụ thể.** Do *type erasure*, `Object value; value instanceof java.util.List<String> strings` là ví dụ không hợp lệ. Khi cần xác định một đối tượng là danh sách, có thể kiểm tra `List<?> list` rồi xác thực từng phần tử riêng nếu nghiệp vụ yêu cầu.

**Lỗi 9 — dùng `instanceof` thay mọi thiết kế đa hình.** Nếu mọi subtype đều cần một hành động cùng ý nghĩa, phương thức được override trên lớp/interface có thể biểu đạt rõ hơn. Chuỗi `instanceof` hữu ích nhất khi mã cần phân loại dữ liệu đầu vào không kiểm soát được, ở ranh giới API hoặc trong thao tác thích ứng nhiều kiểu.

## 10. Cách chọn cấu trúc và bài tập tự kiểm tra

Trước khi viết nhiều nhánh, trả lời ba câu hỏi:

1. **Có cần thực hiện nhiều tác vụ trên cùng đối tượng không?** Nếu có, cân nhắc nhiều `if` độc lập; nếu chỉ chọn một tác vụ, dùng `if / else if / else` hoặc `return` sớm.
2. **Các kiểu có chồng lấn không?** Kiểm tra quan hệ `extends` và `implements`. Với chuỗi chọn một nhánh, đặt những điều kiện cụ thể cần ưu tiên ở trước.
3. **Có cần dùng biến đã khớp ở đâu?** Đặt code sử dụng biến bên trong vùng flow scoping hợp lệ; dùng `&&` cho điều kiện bổ sung hoặc thoát sớm ở đường không khớp.

**Bài tập 1.** Đoán kết quả rồi kiểm tra:

```java
Object value = new StringBuilder("xy");

if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
}
if (value instanceof String text) {
    System.out.println(text);
}
```

Đáp án: chỉ in `2`. `StringBuilder` là `CharSequence` nhưng không phải `String`.

**Bài tập 2.** Thay `value` bằng `7` và thử hai phiên bản `else if`: kiểm tra `Number` trước `Integer`, rồi đảo ngược. Đáp án: thứ tự đầu chọn nhánh `Number`; thứ tự đảo chọn nhánh `Integer`. Hãy giải thích tại sao không có chuyện hai nhánh cùng chạy.

**Bài tập 3.** Xem giá trị `value = " "` khi viết:

```java
if (value instanceof String s && !s.isBlank()) {
    System.out.println("A");
} else if (value instanceof String other) {
    System.out.println("B");
} else {
    System.out.println("C");
}
```

Đáp án: in `B`. Kiểu `String` khớp ở cả hai chỗ, nhưng nhánh đầu sai vì điều kiện `!s.isBlank()`; chỉ nhánh `else if` thứ hai chạy. Đây là khác biệt giữa **pattern khớp** và **toàn bộ biểu thức điều kiện khớp**.

**Khi nào cần cân nhắc `switch`?** Nếu có rất nhiều kiểu đầu vào, mã sử dụng Java 21 trở lên có thể xem xét *pattern matching for `switch`*, guard `when` và kiểm tra tính bao phủ. Tuy nhiên, cần hiểu các quy tắc riêng của `switch` (dominance và xử lý `null`); không nên chuyển máy móc các `if` độc lập thành `switch` vì `switch` chọn nhánh theo ngữ nghĩa khác.

## Tài liệu đối chiếu

- [JLS Java SE 17 `15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): kiểm tra kiểu và pattern matching bằng `instanceof`.
- [JLS Java SE 17 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi của pattern variable và phân tích luồng điều khiển.
- [JLS Java SE 17 `14.9 — The `if` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.9): lựa chọn nhánh `if`/`else`.
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): lý do thiết kế và trạng thái ổn định từ Java 16.
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441): mở rộng cho Java 21 khi cần chuyển sang cấu trúc phân nhánh bằng `switch`.
