# Type pattern với `instanceof` và phạm vi biến mẫu trong Java 27

Khi một biến được khai báo bằng kiểu tổng quát như `Object`, `CharSequence` hoặc một interface, chương trình đôi khi cần xử lý riêng tùy **kiểu thực tế** của đối tượng. **Type pattern** cho phép kiểm tra kiểu và khai báo một biến đã được thu hẹp kiểu trong cùng biểu thức `instanceof`:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Chuỗi có " + text.length() + " ký tự";
    }
    return "Không phải String";
}
```

Nếu `value` thực sự là `String` và khác `null`, phép so khớp thành công, Java gán tham chiếu đó cho biến mẫu `text` (kiểu `String`) và cho phép dùng `text` ở nơi compiler biết chắc phép so khớp đã thành công. Không cần ép kiểu thủ công.

Đây là cú pháp ổn định, được hỗ trợ đầy đủ trong **Java 27**. Điểm quan trọng nhất không chỉ là viết `instanceof String text`, mà là hiểu **phạm vi biến mẫu phụ thuộc vào luồng điều khiển** (*flow scoping*): có những vị trí `text` sử dụng được, có những vị trí dùng sẽ bị lỗi biên dịch.

Bài học thuộc chương **Pattern matching**, tập trung vào **type pattern** của Java SE 27 và các quy tắc còn hiện hành.

## 1. Type pattern là gì?

Một *type pattern* là mẫu kiểm tra một giá trị có phù hợp với kiểu được chỉ định hay không. Khi mẫu có tên biến, việc so khớp thành công sẽ khai báo và khởi tạo biến mẫu (*pattern variable*).

Cú pháp phổ biến:

```java
expression instanceof TargetType variableName
```

Ba thành phần đảm nhiệm ba vai trò:

| Thành phần | Ý nghĩa | Trong `input instanceof String text` |
| --- | --- | --- |
| `expression` | Biểu thức cung cấp giá trị để kiểm tra | `input` |
| `TargetType` | Kiểu mà giá trị cần phù hợp | `String` |
| `variableName` | Biến mẫu được gán giá trị khi khớp | `text` |

Ví dụ:

```java
Object input = "Java 27";

if (input instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Kết quả:

```text
JAVA 27
```

Ở đây:

1. `input` có **kiểu khai báo** là `Object`.
2. Giá trị thực tế là đối tượng `String`.
3. `instanceof String text` kiểm tra kiểu tại thời điểm chạy.
4. Vì phép kiểm tra đúng, `text` được khởi tạo với chính tham chiếu tới đối tượng đó.
5. Trong nhánh đúng, compiler biết `text` có kiểu `String` nên có thể gọi `toUpperCase()`.

Biến mẫu không tạo bản sao đối tượng và không biến đổi kiểu runtime của `input`. Nó chỉ cho ta một tham chiếu có kiểu tĩnh phù hợp sau khi kiểm tra thành công.

### 1.1. Phân biệt kiểm tra kiểu và type pattern

`instanceof` vẫn có dạng chỉ kiểm tra kiểu:

```java
boolean isString = input instanceof String;
```

Dạng trên trả về `boolean` nhưng **không tạo biến mẫu**. Dạng sau vừa kiểm tra vừa có thể đưa biến vào phạm vi khi khớp:

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Hai dạng đều còn hợp lệ. Sử dụng type pattern khi cần làm việc với giá trị sau khi kiểm tra; dùng kiểm tra kiểu thuần khi chỉ cần câu trả lời đúng/sai.

### 1.2. `null` không khớp với type pattern ở vế phải của `instanceof`

```java
Object input = null;

System.out.println(input instanceof String);      // false
System.out.println(input instanceof String text); // false
```

Với `instanceof` theo type pattern, tham chiếu `null` trả về `false` và không khởi tạo biến mẫu. Vì vậy:

```java
static int safeLength(Object input) {
    return input instanceof String text ? text.length() : 0;
}
```

Không cần viết thêm `input != null` trước `instanceof String text`. Tuy nhiên, việc một biến mẫu đã khớp không đảm bảo **những trường hoặc phần tử nằm bên trong đối tượng** đều khác `null`.

### 1.3. Type pattern hoạt động với kế thừa và interface

Kiểu mẫu có thể là một lớp, interface hoặc kiểu tham chiếu phù hợp khác.

```java
static int characterCount(Object input) {
    if (input instanceof CharSequence chars) {
        return chars.length();
    }
    return 0;
}
```

Cả `String` và `StringBuilder` đều triển khai `CharSequence`. Nếu `input` chứa một trong các kiểu đó, mẫu trên có thể khớp và `chars` có kiểu tĩnh `CharSequence`. Vì vậy chỉ nên gọi những phương thức được định nghĩa trên `CharSequence` khi dùng `chars`, trừ khi thực hiện một phép kiểm tra thu hẹp khác.

## 2. “Phạm vi biến mẫu” là một quy tắc dựa trên đường đi điều khiển

Với biến cục bộ khai báo thông thường trong một khối mã, phạm vi chủ yếu được xác định theo vị trí khai báo và ranh giới khối. Với **pattern variable**, Java sử dụng phân tích luồng điều khiển ở thời điểm **biên dịch** để tìm nơi mẫu đã *chắc chắn khớp* (*definitely matched*).

Hãy đọc hai đoạn sau:

```java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ
}
```

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
System.out.println(text.length()); // LỖI BIÊN DỊCH
```

Với đoạn thứ hai, khi chương trình đi tới câu lệnh `println` bên ngoài `if`, `value` có thể không phải `String`. Compiler không cho phép dùng `text` ở vị trí mà mẫu chưa chắc đã được khởi tạo.

**Quy tắc nền tảng:** Chỉ dùng biến mẫu tại những điểm mà compiler có thể chứng minh phép so khớp tương ứng đã thành công theo mọi đường đi tới điểm đó.

Lưu ý đây là quy tắc **phạm vi tên biến** (*scope*), không chỉ là việc biến có thể chứa `null` hay không. Khi biến mẫu không ở trong phạm vi, chương trình không biên dịch được, kể cả lập trình viên tin rằng dữ liệu thực tế luôn hợp lệ.

## 3. `if` và `if/else`: phạm vi ở nhánh đúng

### 3.1. Nhánh `if` nhận biến mẫu khi phép so khớp đúng

```java
static String normalize(Object input) {
    if (input instanceof String text) {
        return text.strip().toLowerCase();
    }
    return "";
}
```

Bên trong khối `if`, `text` chắc chắn đã có giá trị kiểu `String` nên có thể gọi `strip()` và `toLowerCase()`.

### 3.2. Nhánh `else` của phép `instanceof` trực tiếp không có biến mẫu

```java
if (input instanceof String text) {
    System.out.println("Độ dài: " + text.length());
} else {
    System.out.println("Không phải chuỗi");
    // System.out.println(text); // LỖI BIÊN DỊCH
}
```

Nhánh `else` chạy khi `input instanceof String text` là `false`. Do mẫu không khớp, không tồn tại cơ sở để tham chiếu `text` tại đây.

### 3.3. Phủ định `!` đảo nhánh có thể dùng biến

```java
if (!(input instanceof String text)) {
    System.out.println("Đầu vào không phải String");
} else {
    System.out.println(text.length()); // Hợp lệ
}
```

Khi biểu thức `!(input instanceof String text)` là `false`, chính phép `input instanceof String text` phải là `true`; do đó biến `text` được phép dùng ở `else`.

Không nên suy luận bằng “biến chỉ tồn tại trong khối có chữ `instanceof`”. Phạm vi phụ thuộc vào **kết quả logic được chứng minh từ điều kiện**, và có thể đổi khi thêm phủ định.

## 4. `&&`: dùng biến mẫu ở vế phải nhờ đánh giá ngắn mạch

Đây là mẫu dùng rất thường xuyên:

```java
static boolean hasText(Object input) {
    return input instanceof String text && !text.isBlank();
}
```

Toán tử `&&` đánh giá từ trái sang phải:

- Nếu `input instanceof String text` là `false`, biểu thức trả về `false` và không đánh giá vế phải.
- Nếu nó là `true`, `text` đã được khởi tạo và vế phải có thể gọi `text.isBlank()`.

Vì thế, với `a && b`, khi `a` đưa một biến mẫu vào phạm vi **nếu đúng**, biến đó có thể dùng trong `b`.

```java
if (input instanceof String text && text.length() >= 3) {
    System.out.println(text.substring(0, 3));
}
```

Trong phần thân `if`, cả phép khớp kiểu và kiểm tra độ dài đều đã đúng nên `text` cũng ở trong phạm vi.

Một ví dụ kiểm tra nhiều yêu cầu:

```java
static boolean validReference(Object input) {
    return input instanceof String reference
            && !reference.isBlank()
            && reference.length() <= 64
            && reference.chars().allMatch(Character::isLetterOrDigit);
}
```

Mỗi biểu thức kế tiếp chỉ chạy khi các biểu thức trước đúng. Nhờ đó không cần ép kiểu, không cần lặp lại phép kiểm tra kiểu, và có thể đọc các điều kiện theo thứ tự.

### 4.1. Vì sao thay `&&` bằng `&` có thể gây lỗi biên dịch?

```java
// Ví dụ KHÔNG HỢP LỆ:
// if (input instanceof String text & text.length() > 0) {
//     System.out.println(text);
// }
```

`&` trên boolean đánh giá cả hai vế khi đánh giá vế trái hoàn thành bình thường. Nếu `input` không phải `String`, vế phải vẫn có thể chạy. Do đó `text` không được chứng minh đã khởi tạo ở vế phải.

Quy tắc phạm vi biến mẫu được tích hợp với `&&` và `||` theo các trường hợp thích hợp, chứ không áp dụng tương tự với `&` và `|`.

## 5. `||`: vì sao thường không dùng được biến mẫu bên phải?

Xét ý định “chấp nhận giá trị là `String` hoặc thỏa điều kiện khác”:

```java
// Ví dụ KHÔNG HỢP LỆ:
// if (input instanceof String text || text.isBlank()) {
//     ...
// }
```

Khi `input instanceof String text` là `true`, toán tử `||` đã xác định kết quả và **không đánh giá vế phải**. Khi phải đánh giá vế phải, phép `instanceof` ở vế trái đã trả về `false`, nên `text` chưa được khởi tạo.

Vì vậy không thể sử dụng `text` ở vế phải của `||` trong dạng này. Biến cũng không mặc nhiên xuất hiện trong thân `if`, vì biểu thức `||` có thể đúng do vế khác.

### 5.1. Phủ định kết hợp `||`: trường hợp hợp lệ

Nếu yêu cầu là “trả về sớm khi đầu vào **không phải String hoặc là chuỗi rỗng**”, hãy viết:

```java
static String requireNonBlankString(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Cần chuỗi không rỗng");
    }
    return text; // Hợp lệ
}
```

Điều kiện `!(input instanceof String text)` là `false` nghĩa là phép khớp đã thành công, nên nếu Java tiếp tục đánh giá `text.isBlank()` ở vế phải của `||`, `text` đã tồn tại. Sau khi câu `if` kết thúc bình thường, toàn bộ điều kiện phải là `false`, và `text` vẫn ở trong phạm vi ở câu `return`.

Đây là một ví dụ quan trọng: **`||` không tự làm biến mẫu “vô dụng”**. Chỉ cần biết biến được *definitely matched* ở đường đi nơi nó được sử dụng. Phủ định `!` có thể biến điều kiện “khớp khi đúng” thành “khớp khi sai”.

## 6. Early return và guard clause: dùng biến mẫu sau `if`

Phạm vi biến mẫu có thể kéo dài **sau câu lệnh `if`** nếu mọi đường đi tới đó đều chứng minh mẫu đã thành công.

```java
static int requireStringLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ
}
```

Giải thích:

1. Nếu đầu vào không phải `String` hoặc là `null`, nhánh `if` trả về `-1` và phương thức kết thúc.
2. Nếu chương trình chạy tiếp tới `return text.length()`, phép `instanceof String text` phải đã đúng.
3. Vì vậy compiler cho phép dùng `text` ở phần còn lại của khối.

Cách viết này rất hữu ích trong hàm xử lý input: kiểm tra điều kiện tiên quyết trước, kết thúc sớm khi không đạt, rồi xử lý dữ liệu đã được thu hẹp kiểu.

Có thể dùng `throw` thay `return`:

```java
static String requiredCode(Object input) {
    if (!(input instanceof String code)) {
        throw new IllegalArgumentException("Mã phải là String");
    }
    return code.strip();
}
```

Nhánh `if` được xem là **không thể hoàn thành bình thường** (*cannot complete normally*) do lệnh `throw`. Java vì thế chứng minh được `code` đã khớp tại lệnh `return`.

### 6.1. Một nhánh `else` thoát cũng có thể mở phạm vi phía sau

```java
static int readLength(Object input) {
    if (input instanceof String text) {
        System.out.println("Đã nhận chuỗi");
    } else {
        return 0;
    }

    return text.length(); // Hợp lệ: else đã return
}
```

Nếu `else` có thể chạy qua hết và tiến đến câu lệnh cuối, compiler không còn bảo đảm `text` đã được khởi tạo và việc sử dụng sẽ không hợp lệ.

Điều kiện đủ không phải là “đã viết dấu ngoặc hoặc khối `else`”, mà là **không có đường đi không khớp nào vẫn có thể tới chỗ dùng biến**.

## 7. Biểu thức ba ngôi `?:` và biến mẫu

Toán tử điều kiện có thể dùng kết quả so khớp để chọn nhánh:

```java
static String format(Object value) {
    return value instanceof String text
            ? text.strip()
            : "<không phải chuỗi>";
}
```

Biến `text` ở trong phạm vi của nhánh **sau dấu `?`** vì nhánh này chạy khi điều kiện đã đúng. Nhánh sau dấu `:` chạy khi phép khớp sai nên không có `text`.

Với điều kiện phủ định, quy tắc đảo chiều:

```java
static int countChars(Object input) {
    return !(input instanceof String text)
            ? 0
            : text.length();
}
```

Ở nhánh `:`, điều kiện phủ định đã sai nên `instanceof String text` phải đúng. Vì vậy `text.length()` là hợp lệ.

Đừng nhầm quy tắc này với việc biến mẫu tự có phạm vi trong toàn bộ biểu thức hoặc sau biểu thức gán. Compiler chỉ cho dùng biến nơi phép khớp chắc chắn đã thành công.

## 8. `while` và `for`: biến mẫu trong thân vòng lặp

Một biểu thức điều kiện vòng lặp có thể đưa biến mẫu vào phạm vi thân vòng lặp khi nó đúng.

Ví dụ với một iterator:

```java
import java.util.Iterator;
import java.util.List;

public class PatternLoop {
    public static void main(String[] args) {
        Iterator<Object> items = List.<Object>of(
                "Java", "27", 42, "sau-so"
        ).iterator();

        Object current = items.hasNext() ? items.next() : null;

        while (current instanceof String text) {
            System.out.println(text.toUpperCase());
            current = items.hasNext() ? items.next() : null;
        }
    }
}
```

Chương trình in:

```text
JAVA
27
```

Mỗi vòng, điều kiện kiểm tra `current`. Khi gặp số nguyên `42`, biểu thức `instanceof String text` sai và thân vòng lặp không chạy thêm. Biến `text` chỉ có thể được dùng trong thân vòng khi mẫu khớp.

Với vòng `for` cơ bản, biến mẫu khai báo trong điều kiện được phép dùng ở thân và phần cập nhật khi điều kiện đúng; vẫn cần thiết kế điều kiện dừng hợp lý:

```java
for (Object value : new Object[] {"abc", 12, "xyz"}) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Ví dụ thứ hai dùng *enhanced for* để duyệt dữ liệu và kiểm tra type pattern trong mỗi lượt, thường đơn giản hơn cố nhét nhiều logic vào điều kiện vòng lặp.

**Lưu ý:** Với vòng lặp, việc một điều kiện khớp ở lần trước không chứng minh nó khớp trong lần sau. Pattern variable được khởi tạo theo mỗi lần kiểm tra thực sự thành công.

## 9. Phạm vi tên biến và trùng tên

Pattern variable là biến cục bộ được khai báo bởi mẫu. Tên của nó chịu các quy tắc về phạm vi và *shadowing* giống các biến cục bộ khác, có thêm điều kiện luồng điều khiển.

Ví dụ không hợp lệ:

```java
void printValue(Object input) {
    String text = "mặc định";

    // LỖI BIÊN DỊCH: pattern variable trùng với biến cục bộ text
    // if (input instanceof String text) {
    //     System.out.println(text);
    // }
}
```

Biến mẫu `text` sẽ trùng với một biến cục bộ đang ở trong phạm vi. Đổi tên biến mẫu hoặc tái cấu trúc mã:

```java
void printValue(Object input) {
    String fallback = "mặc định";

    if (input instanceof String text) {
        System.out.println(text);
    } else {
        System.out.println(fallback);
    }
}
```

Ở các vùng điều khiển riêng biệt, việc tái sử dụng một tên biến mẫu có thể hợp lệ khi các phạm vi không chồng lấn; tuy nhiên dùng tên phản ánh dữ liệu như `name`, `sequence`, `number` sẽ dễ đọc hơn.

Không nên lạm dụng một biến mẫu như biến tạm để thay đổi giá trị sau khi khớp. Trong Java hiện hành, pattern variable có thể không được khai báo `final` và có thể bị gán lại nếu luật gán của biến cho phép, nhưng làm vậy khiến ý nghĩa “giá trị được kiểm tra kiểu” không còn rõ. Nếu cần biến thay đổi, nên khai báo một biến mới.

## 10. Giới hạn với generic, kiểu `var` và kiểu nguyên thủy

### 10.1. Không kiểm tra tham số generic không thể xác minh lúc chạy

Do **type erasure**, không thể dùng type pattern để kiểm tra phần tử của một `List<String>` theo cách sau:

```java
// LỖI BIÊN DỊCH:
// if (value instanceof java.util.List<String> names) {
//     ...
// }
```

Dạng phù hợp khi chỉ cần xác nhận đối tượng là một danh sách:

```java
if (value instanceof java.util.List<?> elements) {
    System.out.println("Số phần tử: " + elements.size());
}
```

`List<?>` không khẳng định mọi phần tử là `String`. Nếu cần kiểm tra nội dung, hãy xét từng phần tử bằng type pattern:

```java
static boolean allStrings(Object input) {
    if (!(input instanceof java.util.List<?> values)) {
        return false;
    }

    for (Object element : values) {
        if (!(element instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Với logic nghiệp vụ cần danh sách chuỗi, chỉ sau khi xác minh các phần tử mới nên chuyển đổi hoặc xây dựng một cấu trúc có kiểu phù hợp. Không dùng unchecked cast chỉ vì `instanceof List<?>` đã đúng.

### 10.2. `var` không phải type pattern cấp cao nhất của `instanceof`

Dạng dưới đây không hợp lệ:

```java
// LỖI BIÊN DỊCH:
// if (value instanceof var item) {
//     ...
// }
```

Ở type pattern trực tiếp sau `instanceof`, Java cần chỉ ra **kiểu tham chiếu** cần kiểm tra; không thể dùng `var` thay cho kiểu đó. Cú pháp `var` có thể xuất hiện trong một số *record component patterns* theo quy tắc riêng, nhưng đó là nội dung khác.

### 10.3. Kiểu nguyên thủy trong `instanceof` có quy tắc riêng

Các ví dụ ổn định của bài này dùng **reference type patterns** như `String text`, `CharSequence chars`, `Number number`. Không được coi `int n`, `long n`... trong `instanceof` là cú pháp chuẩn mặc định giống reference type pattern.

Java 27 có tài liệu riêng về **primitive patterns trong `instanceof` và `switch` ở trạng thái preview**; sử dụng các cú pháp đó phải theo hướng dẫn bật preview tương ứng và không nên nhập nhằng với tính năng chuẩn trong bài. Với code Java thông thường khi có dữ liệu `Object` mang số, có thể làm việc với wrapper hoặc kiểu cha như `Number`:

```java
Object value = 27;  // autobox thành Integer

if (value instanceof Integer number) {
    System.out.println(number + 1);
}
```

### 10.4. Không biến type pattern thành cơ chế kiểm tra mọi bất biến

`value instanceof String text` chỉ cho biết giá trị là `String`. Nó không cho biết chuỗi có hợp lệ về định dạng, chiều dài, bảo mật hay miền giá trị. Các quy tắc nghiệp vụ vẫn phải được kiểm tra riêng.

Tương tự, `value instanceof Customer customer` không đảm bảo mọi thuộc tính bên trong `customer` khác `null`, đã được xác minh hay an toàn để dùng đồng thời từ nhiều thread.

## 11. Type pattern và `switch`/record pattern khác nhau thế nào?

Trong Java hiện đại, pattern matching còn xuất hiện ở `switch` và trong các *record pattern*. Cần phân biệt phạm vi của bài này.

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| Kiểm tra kiểu thuần | `value instanceof String` | Chỉ cần giá trị boolean. |
| Type pattern với `instanceof` | `value instanceof String text` | Kiểm tra kiểu và khai báo biến khi khớp. |
| Type pattern trong `switch` | `case String text -> ...` | Chọn nhánh theo kiểu trong một `switch` phù hợp. |
| Record pattern | `value instanceof Point(int x, int y)` | Kiểm tra record và tách các component. |

Dạng `case String text` dùng chính ý tưởng pattern binding, nhưng quy tắc phạm vi của biến trong `switch` gắn với nhánh `case` tương ứng. Với record pattern, biến có thể được tạo từ các thành phần bên trong record, không chỉ từ toàn đối tượng. Các khái niệm này dùng được ở Java 27; nội dung chi tiết nên học ở bài riêng về `switch`/record patterns để tránh nhầm với type pattern trực tiếp sau `instanceof`.

## 12. Chương trình ví dụ hoàn chỉnh

Tạo file `TypePatternDemo.java`:

```java
public class TypePatternDemo {

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text (" + text.length() + "): " + text.strip();
        }

        if (value instanceof Number number) {
            return "Number: " + number.doubleValue();
        }

        return value == null
                ? "<null>"
                : "Other: " + value.getClass().getSimpleName();
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static String requireText(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("Cần chuỗi không rỗng");
        }
        return text.strip();
    }

    public static void main(String[] args) {
        Object[] values = {" Java 27 ", 42, null, ""};

        for (Object value : values) {
            System.out.println(describe(value));
        }

        System.out.println(lengthOrMinusOne("hello"));
        System.out.println(lengthOrMinusOne(42));
        System.out.println(requireText("  pattern  "));
    }
}
```

Biên dịch và chạy bằng JDK 27:

```bash
javac TypePatternDemo.java
java TypePatternDemo
```

Kết quả:

```text
Text (9): Java 27
Number: 42.0
<null>
Other: String
5
-1
pattern
```

Giải thích:

- Chuỗi đầu tiên khớp type pattern `String text`; điều kiện `!text.isBlank()` được đánh giá; `length()` đếm cả khoảng trắng trước khi `strip()` hiển thị nội dung.
- Giá trị số nguyên `42` được autobox thành `Integer`, cũng là `Number`; mẫu `Number number` khớp và `doubleValue()` trả về `42.0`.
- `null` không khớp các type pattern, đi đến nhánh trả về `"<null>"`.
- Chuỗi rỗng khớp `String` nhưng không thỏa điều kiện `!text.isBlank()`; sau đó không khớp `Number`, nên trả về `Other: String`.
- `lengthOrMinusOne` minh họa nhánh `return` sớm để dùng `text` sau `if`.
- `requireText` minh họa `!` phối hợp `||` mà vẫn có thể dùng biến mẫu ở vế phải và sau guard clause.

## 13. Những lỗi biên dịch và lỗi tư duy thường gặp

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Dùng `text` trong `else` của `if (value instanceof String text)` | Mẫu chưa chắc khớp ở `else` | Chỉ dùng `text` trong nhánh đúng hoặc đảo điều kiện phù hợp. |
| Dùng `text` ngoài `if` có thể hoàn thành cả hai nhánh | Không có chứng minh chắc chắn rằng mẫu khớp | Dùng guard `return`/`throw` hoặc giới hạn phạm vi. |
| `value instanceof String text || text.isBlank()` | Vế phải chạy khi phép kiểm tra kiểu sai | Dùng `&&` hoặc viết guard `!(...) || ...` theo đúng nghiệp vụ. |
| Dùng `&` thay `&&` | Không có ngắn mạch; biến không chắc có giá trị ở vế phải | Dùng `&&`. |
| `value instanceof List<String> names` | Type erasure: không kiểm tra được tham số generic này lúc chạy | Kiểm tra `List<?>` và kiểm tra từng phần tử. |
| `value instanceof var item` | Top-level type pattern của `instanceof` không dùng `var` | Ghi rõ kiểu tham chiếu. |
| Tên pattern variable trùng biến cục bộ đang trong scope | Lỗi khai báo do shadowing | Đổi tên hoặc tách phạm vi. |
| Tin rằng type pattern kiểm tra toàn bộ object graph | Nó chỉ kiểm tra kiểu và bind biến | Tự kiểm tra validation, field nullable và các bất biến khác. |
| Cho rằng pattern luôn tạo bản sao hoặc object mới | Chỉ bind tham chiếu phù hợp | Xem pattern variable như tham chiếu đã thu hẹp kiểu. |

Khi một chương trình bị lỗi “cannot find symbol” ở tên biến mẫu, hãy kiểm tra nơi sử dụng biến và **tất cả đường đi điều khiển** tới vị trí đó. Khi compiler báo không thể kiểm tra kiểu, hãy kiểm tra tính áp dụng của mẫu đối với kiểu tĩnh của biểu thức và các giới hạn generic/preview.

## 14. Cách tư duy về flow scoping

Một quy trình ngắn khi đọc điều kiện phức tạp:

1. Xác định biểu thức tạo type pattern, ví dụ `input instanceof String text`.
2. Tìm điều kiện chắc chắn làm mẫu **đúng** hoặc **sai**.
3. Với `&&`, vế phải chỉ chạy khi vế trái đúng; với `||`, vế phải chỉ chạy khi vế trái sai.
4. Với `!`, hoán đổi ý nghĩa đúng/sai của điều kiện.
5. Với `if/else`, quan sát nhánh nào có thể được thực thi khi mẫu khớp.
6. Với `return`/`throw`, loại những đường đi đã kết thúc và xét các đường đi còn đến được câu lệnh tiếp theo.
7. Nếu còn một đường đi tới vị trí đang xét mà mẫu **chưa chắc thành công**, không dùng biến mẫu ở đó.

Ví dụ thực tế:

```java
static String normalizeCode(Object input) {
    if (!(input instanceof String code) || code.isBlank()) {
        return "INVALID";
    }

    // Mọi đường đi đến đây đều có code là String không rỗng.
    String normalized = code.strip().toUpperCase();

    return normalized.length() <= 32 ? normalized : "TOO_LONG";
}
```

Ở nhánh sau `if`, compiler chắc chắn `code` đã khớp; còn yêu cầu nghiệp vụ “không rỗng” đến từ kiểm tra `isBlank()` và cần được lập trình viên duy trì. **Compiler theo dõi phạm vi biến theo cấu trúc logic; compiler không tự hiểu mọi điều kiện nghiệp vụ của ứng dụng.**

## 15. Tài liệu tham khảo chính thức

- [Java Language Specification 27 — §15.20.2: The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.20.2): phân biệt kiểm tra kiểu với pattern matching, xử lý `null` và kết quả so khớp.
- [Java Language Specification 27 — §14.30: Patterns](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.30): type pattern, record pattern và quá trình so khớp.
- [Java Language Specification 27 — §6.3: Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.3): nguyên tắc `definitely matched` và phạm vi của pattern variable.
- [Java Language Specification 27 — §6.3.1: Scope for Pattern Variables in Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.3.1): quy tắc chi tiết cho `&&`, `||`, `!` và `?:`.
- [Java Language Specification 27 — §6.3.2: Scope for Pattern Variables in Statements](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.3.2): phạm vi trong `if`, `while` và `for`.
- [Java Language Specification 27 — §6.4: Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.4): giới hạn đặt tên trùng nhau.
- [Java SE 27 Preview — Primitive Types in Patterns, `instanceof`, and `switch`](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html): phần mở rộng primitive patterns ở trạng thái preview, tách biệt với type pattern tham chiếu ổn định trình bày ở đây.
