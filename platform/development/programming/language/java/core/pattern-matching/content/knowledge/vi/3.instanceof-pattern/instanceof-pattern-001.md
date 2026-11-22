# Cú pháp `instanceof` với type pattern trong Java

## 1. Từ phép kiểm tra kiểu đến type pattern

Khi một biến được khai báo với kiểu tổng quát như `Object` hoặc một interface, đối tượng thực tế mà biến tham chiếu có thể thuộc nhiều kiểu cụ thể. Java dùng toán tử `instanceof` để kiểm tra kiểu tại thời điểm chạy. **Type pattern** kết hợp phép kiểm tra đó với việc khai báo một biến mang kiểu đã kiểm tra, nhờ vậy không cần ép kiểu tường minh sau khi kiểm tra thành công.

So sánh hai cách xử lý một giá trị có thể là `String`:

**Cách cũ — kiểm tra rồi ép kiểu:**

```java
static int lengthOfString(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return 0;
}
```

**Cách dùng type pattern:**

```java
static int lengthOfString(Object input) {
    if (input instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Hai đoạn có cùng kết quả cho các đầu vào tương ứng. Ở cách mới, trình biên dịch đã biết `text` là `String` trong nhánh khớp; mã nguồn ngắn hơn, tránh việc một người sửa kiểu ở điều kiện nhưng quên sửa phép ép kiểu trong thân nhánh.

Pattern matching cho `instanceof` đã được chuẩn hóa từ **Java 16** (JEP 394); do đó có thể dùng trên **Java 17** mà không bật tính năng preview. Bài này tập trung vào **type pattern của `instanceof`**. Cú pháp record pattern có dạng `Point(int x, int y)` là một tính năng khác, được chuẩn hóa từ Java 21.

## 2. Giải phẫu cú pháp

Cấu trúc cơ bản:

```java
expression instanceof ReferenceType patternVariable
```

Ví dụ cụ thể:

```java
Object value = "Java";
boolean matched = value instanceof String text;
```

Ý nghĩa của từng thành phần:

| Thành phần | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `expression` | `value` | Biểu thức sinh ra giá trị cần kiểm tra |
| `instanceof` | `instanceof` | Toán tử kiểm tra kiểu, cho kết quả `boolean` |
| `ReferenceType` | `String` | Kiểu tham chiếu mà giá trị phải tương thích tại runtime |
| `patternVariable` | `text` | Biến được khởi tạo bằng giá trị vừa khớp, mang kiểu `String` |

Trong đoạn khai báo `matched`, nếu `value` thật sự tham chiếu tới một `String` thì `matched` là `true` và pattern khớp. Tuy nhiên, **việc biểu thức trả về `true` không có nghĩa `text` tự động nằm trong phạm vi hợp lệ ở mọi câu lệnh sau đó**. Phạm vi của `text` phụ thuộc cách viết điều kiện và luồng điều khiển; phần tiếp theo sẽ giải thích chi tiết.

Các điểm cốt lõi:

- **Khớp thành công:** biểu thức trả về `true`, biến pattern nhận tham chiếu đến chính đối tượng đã được kiểm tra. Không tạo bản sao đối tượng.
- **Không khớp:** biểu thức trả về `false`, biến pattern không được khởi tạo để sử dụng ở nhánh không khớp.
- **Đầu vào là `null`:** `null instanceof String text` trả về `false`; không ném `NullPointerException` chỉ vì phép kiểm tra này.
- **Kiểu của biến đã rõ:** trong vùng hợp lệ, `text.length()` gọi trực tiếp API của `String`, không cần `(String) value`.
- **Phạm vi được kiểm tra lúc biên dịch:** trình biên dịch từ chối việc dùng `text` ở nơi chưa chắc type pattern đã khớp.

### Type pattern khác gì phép `instanceof` truyền thống?

```java
if (value instanceof String) {
    // Chỉ biết điều kiện kiểm tra String đúng.
}
```

```java
if (value instanceof String text) {
    // Có thêm biến text có kiểu String, dùng được ở đây.
}
```

Cả hai đều kiểm tra kiểu. Type pattern có **thêm biến ràng buộc với kết quả khớp** (*binding variable*), giúp sử dụng giá trị ngay sau kiểm tra.

### Kiểu và biểu thức nào được phép?

Trên Java 17, type pattern dùng **kiểu tham chiếu**, ví dụ `String`, `Integer`, interface, lớp tự định nghĩa, và kiểu mảng như `int[]`. `int[]` là kiểu tham chiếu (mảng), còn `int` là kiểu nguyên thủy, nên hai trường hợp khác nhau:

```java
Object a = new int[] {1, 2, 3};

if (a instanceof int[] numbers) { // Hợp lệ trên Java 17
    System.out.println(numbers.length); // 3
}
```

```java
// KHÔNG HỢP LỆ trên Java 17:
// if (a instanceof int number) { ... }
```

Kiểu bên trái và kiểu trong pattern phải cho phép phép kiểm tra kiểu hợp lệ theo quy tắc Java. Trình biên dịch còn từ chối một type pattern luôn đúng với mọi giá trị khác `null` xét từ kiểu tĩnh của biểu thức:

```java
String text = "Java";

// KHÔNG HỢP LỆ trên Java 17: String đã là kiểu tĩnh của text.
// if (text instanceof String anotherText) { ... }
```

Lúc này không cần kiểm tra kiểu; có thể dùng `text` trực tiếp. Ngược lại, `Object value = "Java"` có kiểu tĩnh `Object`, vì vậy `value instanceof String text` là phép thử có ý nghĩa.

## 3. Phạm vi biến pattern: chỉ nơi chắc chắn đã khớp

Phạm vi của biến pattern phụ thuộc **luồng điều khiển** (*flow scoping*), thay vì chỉ dựa vào dấu ngoặc nhọn. Mô hình dễ nhớ: **chỉ được dùng biến khi mọi đường đi tới vị trí đó đều đã xác nhận pattern khớp thành công**.

### 3.1. `if` và `else`

```java
static String describe(Object input) {
    if (input instanceof String text) {
        return "Length: " + text.length(); // Được dùng text
    } else {
        return "Not a string";              // Không được dùng text
    }
}
```

`text` có hiệu lực trong nhánh `if` khi điều kiện đúng, không có hiệu lực ở nhánh `else`. Sau câu lệnh `if/else` thông thường, nếu vẫn có đường đi không khớp, bạn cũng không được dùng `text` như một biến đã biết giá trị.

### 3.2. `&&`: điều kiện ở bên phải được dùng biến đã khớp

Toán tử `&&` đánh giá từ trái sang phải và chỉ đánh giá vế phải khi vế trái là `true`. Do đó, câu lệnh sau hợp lệ:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Nếu `input` không phải `String` hoặc là `null`, vế `text.isBlank()` không được thực hiện. Nếu vế phải được chạy, trình biên dịch đã biết `text` là một `String` hợp lệ. Đây là cách thường dùng để **vừa kiểm tra kiểu, vừa kiểm tra thuộc tính** của giá trị.

Có thể kết hợp nhiều điều kiện ngắn mạch:

```java
if (input instanceof String text
        && text.length() >= 3
        && text.startsWith("J")) {
    System.out.println(text);
}
```

### 3.3. `||`: không thể dùng biến ở vế phải sau một phép khớp dương

Đoạn này **không biên dịch**:

```java
// SAI: Khi phép instanceof là false,
// Java cần xét vế phải nhưng text chưa được gán.
// if (input instanceof String text || text.isEmpty()) {
//     System.out.println("Matched");
// }
```

`||` chỉ xét vế phải khi vế trái là `false`; chính trường hợp đó `text` **chưa khớp**. Đây là lỗi phạm vi biến, không phải lỗi cú pháp của riêng toán tử `||`.

Nếu cần điều kiện theo hướng ngược lại, hãy dùng phủ định kết hợp với `||`:

```java
static String validate(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "Invalid";
    }
    return text.strip();
}
```

Ở vế phải của `||`, điều kiện `!(input instanceof String text)` đã là `false`, nghĩa là pattern thật sự **đã khớp**, nên `text.isBlank()` được phép. Cũng vì nhánh `if` trả về sớm khi điều kiện đúng, phần sau chỉ chạy khi `text` đã khớp và không rỗng.

### 3.4. Dấu `!` và lối thoát sớm

Phép phủ định đổi nhánh đúng/sai nhưng không làm mất khả năng dùng biến trên đường đi đã xác nhận khớp:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "Not a string";
    }

    // Nếu đến đây, điều kiện phủ định đã sai:
    // input là String và text đã được khởi tạo.
    return text.strip();
}
```

Kỹ thuật này thường được gọi là *guard clause* (điều kiện loại trừ sớm): xử lý đầu vào không hợp lệ trước, rồi viết luồng chính ở mức thụt đầu dòng thấp hơn. Có thể dùng `throw` thay `return` tùy hợp đồng của phương thức.

**Lưu ý về dấu ngoặc:** Viết `!(input instanceof String text)` để phủ định toàn bộ kết quả kiểm tra. Không nhầm với `(!input) instanceof String text`: toán tử `!` không áp dụng được cho đối tượng bất kỳ.

### 3.5. Biểu thức điều kiện `?:`

Type pattern cũng dùng được trong biểu thức ba ngôi khi nhánh sử dụng biến được bảo đảm khớp:

```java
static int textLength(Object input) {
    return input instanceof String text ? text.length() : -1;
}
```

Ở nhánh sau `?`, `text` luôn có kiểu `String`. Nhánh sau dấu `:` không thể dựa vào cùng biến pattern, vì nhánh đó biểu thị kiểm tra thất bại.

### 3.6. Dùng lại tên biến ở những nhánh không giao nhau

Tên biến pattern tuân theo các quy tắc phạm vi của Java. Hai nhánh riêng có thể dùng lại tên khi phạm vi của chúng không chồng lấn:

```java
static String label(Object value) {
    if (value instanceof String item) {
        return "Text: " + item;
    } else if (value instanceof Integer item) {
        return "Number: " + item;
    }
    return "Unknown";
}
```

Tuy nhiên, khai báo một biến pattern trùng với biến cục bộ **đang ở trong phạm vi** sẽ gây lỗi biên dịch. Để mã dễ bảo trì, nên đặt tên có nghĩa như `text`, `number`, `order`, thay vì cố dùng lại tên ở nhiều nhánh.

## 4. Ví dụ hoàn chỉnh, chạy với Java 17+

Tạo tệp **`TypePatternDemo.java`** với nội dung sau:

```java
import java.util.List;

public class TypePatternDemo {
    static String classify(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text.strip();
        }

        if (value instanceof Integer number) {
            return "Integer doubled: " + (number * 2);
        }

        if (value instanceof List<?> elements) {
            return "List size: " + elements.size();
        }

        if (value instanceof int[] numbers) {
            return "Array length: " + numbers.length;
        }

        return "Unknown";
    }

    static String requireNonBlankText(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Invalid";
        }
        return "Valid: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(classify("  Java  "));
        System.out.println(classify(7));
        System.out.println(classify(List.of("a", "b")));
        System.out.println(classify(new int[] {2, 4, 6}));
        System.out.println(classify(""));
        System.out.println(classify(null));
        System.out.println(requireNonBlankText("  hello  "));
        System.out.println(requireNonBlankText("   "));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac --release 17 TypePatternDemo.java
java TypePatternDemo
```

**Kết quả chuẩn:**

```text
String: Java
Integer doubled: 14
List size: 2
Array length: 3
Unknown
Unknown
Valid: hello
Invalid
```

Giải thích:

1. `"  Java  "` khớp với `String text`; `!text.isBlank()` đúng; `strip()` loại khoảng trắng đầu/cuối.
2. `7` được tự đóng hộp thành `Integer` khi truyền cho tham số `Object`; type pattern `Integer number` khớp và phép nhân `number * 2` dùng cơ chế tự mở hộp.
3. `List.of("a", "b")` khớp `List<?> elements`; phép kiểm tra chỉ đảm bảo đây là một `List`, không khẳng định kiểu của từng phần tử.
4. `new int[] {2, 4, 6}` khớp `int[] numbers`, bởi vì mảng là một kiểu tham chiếu.
5. Chuỗi rỗng `""` khớp về **kiểu** nhưng không qua được điều kiện `!text.isBlank()`, nên tiếp tục xuống `Unknown`.
6. `null` không khớp pattern nào và rơi vào kết quả mặc định; riêng phép `instanceof` không ném ngoại lệ.
7. `requireNonBlankText` loại sớm giá trị sai kiểu hoặc chuỗi trắng, sau đó dùng `text` trong nhánh chắc chắn đã khớp.

Ví dụ này có thể biên dịch trên Java 17 không bật preview. Nếu dùng IDE, chọn Java language level 17 trở lên; với Maven/Gradle, cấu hình đúng phiên bản phát hành tương ứng.

## 5. Type pattern với kế thừa và interface

Đối tượng thuộc lớp con cũng có thể khớp type pattern của lớp cha hoặc interface mà nó triển khai. Ví dụ:

```java
interface Printable {
    String render();
}

final class Receipt implements Printable {
    @Override
    public String render() {
        return "Receipt #42";
    }
}
```

Trong một phương thức nhận `Object value`, có thể viết:

```java
if (value instanceof Printable printable) {
    System.out.println(printable.render());
}
```

Nếu `value` trỏ đến `new Receipt()`, mẫu `Printable printable` khớp; kiểu tĩnh của `printable` là `Printable`, nên gọi được phương thức `render()` khai báo trên interface. Cú pháp không yêu cầu một lớp cụ thể: type pattern có thể nêu kiểu trừu tượng phù hợp.

### Phân biệt kiểu tĩnh với kiểu runtime

```java
Object input = "hello";
if (input instanceof CharSequence chars) {
    System.out.println(chars.length()); // 5
}
```

Biến `input` có kiểu tĩnh `Object`, còn đối tượng runtime là `String`. `String` triển khai `CharSequence`, nên pattern khớp. Trong nhánh `if`, `chars` có kiểu tĩnh `CharSequence`, tức chỉ các thành viên thuộc kiểu `CharSequence` được bảo đảm gọi trực tiếp. Mục đích của type pattern là lấy một biến có kiểu kiểm tra được, **không tự nâng cấp biến thành tất cả kiểu cụ thể mà đối tượng triển khai**.

### Không đồng nghĩa với kiểm tra đúng bằng một lớp duy nhất

`obj instanceof BaseType b` cũng đúng khi `obj` là một lớp con hợp lệ của `BaseType`; nó không yêu cầu `obj.getClass() == BaseType.class`. Nếu nghiệp vụ cần phân biệt chính xác lớp runtime, đó là một yêu cầu khác và phải cân nhắc thiết kế riêng.

## 6. Type pattern với generic và giới hạn xóa kiểu

Ở runtime, Java không giữ đầy đủ tham số kiểu generic do cơ chế *type erasure* (xóa kiểu). Vì thế không thể dựa vào `instanceof` để xác nhận một danh sách chứa toàn `String` chỉ nhờ cú pháp tham số hóa.

**Hợp lệ:**

```java
if (value instanceof List<?> items) {
    System.out.println(items.size());
}
```

**Không hợp lệ với đối tượng `Object value` trên Java 17:**

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof List<String> items) {
//     System.out.println(items.size());
// }
```

`List<?> items` cho biết giá trị là một `List` với kiểu phần tử chưa biết. Có thể kiểm tra phần tử khi cần:

```java
if (value instanceof List<?> items) {
    for (Object element : items) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

Đừng suy ra rằng mọi phần tử là `String` chỉ vì một vài phần tử khớp. Nếu ứng dụng yêu cầu danh sách đồng nhất, hãy kiểm tra toàn bộ phần tử hoặc dùng hợp đồng kiểu ở ranh giới dữ liệu.

## 7. Những khác biệt cần nhớ khi đọc và viết mã

| Vấn đề | Cách hiểu đúng |
| --- | --- |
| `instanceof String` | Chỉ trả về kết quả kiểm tra kiểu |
| `instanceof String text` | Trả về kết quả kiểm tra kiểu **và** ràng buộc biến `text` trong phạm vi hợp lệ |
| `instanceof` gặp `null` | Trả về `false`, không tự ném `NullPointerException` |
| `if (x instanceof String s && s.length() > 3)` | Hợp lệ vì vế phải chỉ chạy khi `s` đã khớp |
| `if (x instanceof String s || s.length() > 3)` | Không hợp lệ vì vế phải có thể chạy khi `s` chưa khớp |
| `if (!(x instanceof String s)) return; ... s ...` | Có thể hợp lệ vì các đường đi tiếp đều đã khớp |
| `List<?> list` | Có thể kiểm tra ở runtime nhưng không bảo đảm kiểu phần tử |
| `String text = ...; text instanceof String s` | Trình biên dịch từ chối một phép khớp luôn đúng theo kiểu tĩnh trên Java 17 |
| `instanceof Point point` | Type pattern, gắn tên cho đối tượng `Point`; không tự tách các trường |
| `instanceof Point(int x, int y)` | Record pattern của Java 21+, khác cú pháp type pattern cơ bản |

Một biến pattern **không mặc nhiên là `final`** trong Java 16+, nhưng trong thực tế nên tránh gán lại biến này nếu không cần thiết: dùng tên mới cho giá trị đã chuyển đổi giúp không nhầm đối tượng gốc với dữ liệu được chuẩn hóa.

## 8. Lỗi thường gặp và cách sửa

### Lỗi 1: thử dùng biến ở nhánh không khớp

```java
// KHÔNG HỢP LỆ:
// if (value instanceof String text) {
//     System.out.println(text);
// } else {
//     System.out.println(text.length());
// }
```

**Sửa:** dùng `text` trong nhánh đã khớp; ở nhánh `else`, xử lý `value` theo kiểu gốc hoặc chọn một giá trị mặc định.

### Lỗi 2: cho rằng `instanceof` đã đổi kiểu biến nguồn

```java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.length()); // Đúng
    // System.out.println(value.length()); // SAI: value vẫn có kiểu tĩnh Object
}
```

**Sửa:** gọi phương thức chuyên biệt qua `text`, vì chỉ biến này được khai báo với kiểu `String`.

### Lỗi 3: lẫn `&&` với `||`

```java
// SAI:
// if (value instanceof String text || text.startsWith("A")) { ... }

// ĐÚNG:
if (value instanceof String text && text.startsWith("A")) {
    System.out.println(text);
}
```

**Sửa:** chọn toán tử theo ngữ nghĩa thực sự, đồng thời kiểm tra nhánh nào bảo đảm biến đã được khởi tạo.

### Lỗi 4: dùng kiểu primitive ở vị trí pattern

```java
// SAI trên Java 17:
// if (value instanceof int n) { ... }

// ĐÚNG khi value là Object có thể chứa Integer:
if (value instanceof Integer n) {
    System.out.println(n.intValue());
}
```

**Sửa:** trên Java 17, dùng kiểu tham chiếu như `Integer` khi cần kiểm tra đối tượng đóng hộp.

### Lỗi 5: nhầm type pattern với record pattern

Nếu có:

```java
record Point(int x, int y) {}
```

thì trên Java 17 vẫn có thể viết:

```java
if (value instanceof Point point) {
    System.out.println(point.x() + point.y());
}
```

Đoạn này dùng **type pattern** `Point point`. Nó không tạo sẵn biến `x`, `y`; phải gọi accessor của record. Cú pháp `Point(int x, int y)` dùng để phân rã thành phần chỉ ổn định từ Java 21.

### Lỗi 6: kiểm tra kiểu khi kiểu tĩnh đã đủ rõ

```java
String name = "Java";
System.out.println(name.length());
```

Ở đây không cần `name instanceof String otherName`. Khi trình biên dịch đã biết kiểu cụ thể, type pattern chỉ làm đoạn mã dài thêm và có thể bị từ chối vì phép thử vô điều kiện đúng với giá trị khác `null`.

## 9. Thực hành kiểm tra hiểu bài

**Bài 1 — dự đoán kết quả.**

```java
static String result(Object value) {
    if (value instanceof String s && s.length() >= 4) {
        return s.substring(0, 2);
    }
    return "NO";
}
```

Hỏi `result("Java")`, `result("Go")`, `result(null)` trả về gì?

Đáp án lần lượt là **`"Ja"`**, **`"NO"`**, **`"NO"`**. Chuỗi `"Go"` vẫn là `String` nhưng không đạt điều kiện chiều dài; `null` không khớp type pattern.

**Bài 2 — sửa lỗi biên dịch.**

```java
// SAI:
// if (value instanceof String s || s.isBlank()) {
//     System.out.println("Invalid");
// }
```

Nếu ý định là phát hiện đầu vào không phải chuỗi **hoặc** chuỗi toàn khoảng trắng, có thể viết:

```java
if (!(value instanceof String s) || s.isBlank()) {
    System.out.println("Invalid");
}
```

Khi `value` không phải `String`, vế trái là `true`, nên không cần đánh giá `s.isBlank()`. Nếu phải đánh giá vế phải thì pattern đã khớp.

**Bài 3 — tự viết phương thức.** Viết `String summary(Object value)` có các quy tắc: nếu là `String` thì trả về chuỗi đã `strip()`; nếu là `Integer` thì trả về `"number:"` ghép với giá trị; trường hợp còn lại trả về `"unknown"`. Dùng hai type pattern và chạy thử với `"  hi "`, `5`, `null`. Kết quả mong đợi lần lượt: `"hi"`, `"number:5"`, `"unknown"`.

## 10. Khi nào nên dùng?

Type pattern rất phù hợp khi mã nhận giá trị có kiểu tổng quát, phải phân loại một vài khả năng, hoặc cần thêm điều kiện dựa trên phương thức của kiểu đã khớp. Với một nhánh đơn giản, `if (value instanceof T t)` thường dễ đọc hơn kiểm tra và ép kiểu thành hai câu lệnh.

Nếu có rất nhiều nhánh phân loại, hãy xem lại thiết kế kiểu dữ liệu trước khi kéo dài chuỗi `if/else`. Trong hệ kiểu đóng, `switch` pattern (ổn định từ Java 21) có thể giúp thể hiện các nhánh rõ hơn; còn với các đối tượng có hành vi đa hình, gọi phương thức qua interface đôi khi phù hợp hơn. Đây là lựa chọn thiết kế, không phải yêu cầu bắt buộc khi dùng `instanceof`.

**Điểm ghi nhớ:** Cú pháp `value instanceof String text` thực hiện hai việc — kiểm tra runtime type của `value` và gán giá trị đã khớp cho biến `text`. Năng lực quan trọng tiếp theo là hiểu **phạm vi phụ thuộc luồng điều khiển**: chỉ dùng `text` tại nơi trình biên dịch chứng minh pattern chắc chắn đã thành công.

## Tài liệu tham khảo

- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 17 Language Specification — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
