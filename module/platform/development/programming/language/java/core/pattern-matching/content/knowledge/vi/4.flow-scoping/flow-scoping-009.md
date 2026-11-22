# Tại sao không thể dùng biến khi match thất bại? — Flow scoping trong Java

Trong Java Pattern Matching, câu lệnh `value instanceof String text` vừa kiểm tra kiểu của một giá trị, vừa có khả năng giới thiệu một **pattern variable** tên `text`. Nhưng tên biến này chỉ được phép dùng ở những vị trí mà trình biên dịch chứng minh được **pattern đã khớp thành công**.

Vì thế, khi match thất bại, ta không thể viết `text.length()` ở nhánh `else` hoặc ở một dòng bất kỳ phía sau điều kiện. Đây là quy tắc **flow scoping**, giúp ngăn chương trình dùng một biến chưa được binding tới giá trị phù hợp kiểu. Quy tắc này được Java kiểm tra **khi biên dịch**, trước khi chương trình chạy.

> Cốt lõi: **Pattern khớp → biến được binding → có thể dùng tại nơi chắc chắn đã khớp. Pattern không khớp → không có binding hợp lệ → không được dùng pattern variable trên đường đi ấy.**

Các ví dụ chính dùng **Java 17+**, với type pattern cho `instanceof` đã trở thành tính năng chính thức từ Java 16.

## 1. Ví dụ đầu tiên: tại sao `else` không đọc được `text`?

Đoạn mã hợp lệ:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
} else {
    System.out.println("Không phải String");
}
```

Ta có thể đọc phép thử thành hai phần:

- **Target expression:** `value`, được đánh giá để lấy một tham chiếu.
- **Type pattern:** `String text`, yêu cầu giá trị khác `null` và tương thích với `String`. Nếu đúng, biến `text` được binding với tham chiếu đó và có kiểu tĩnh `String`.

Nhánh `if` chỉ được thực hiện nếu pattern khớp, nên `text.length()` hợp lệ. Tuy nhiên, thử viết:

```java
Object value = 42;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // System.out.println(text.length()); // LỖI BIÊN DỊCH nếu bỏ //
}
```

Trong nhánh `else`, điều kiện `value instanceof String text` trả về `false`. Ở đây, `42` là `Integer`, không khớp `String`. Java **không binding biến `text`**, và tên `text` không có phạm vi sử dụng hợp lệ ở nhánh ấy. Trình biên dịch từ chối câu lệnh truy cập `text`.

Lỗi này **không phải** một `NullPointerException` phát sinh khi chạy. Chương trình không qua được bước biên dịch nếu bạn đặt lệnh dùng biến ở nơi không thuộc scope của pattern variable.

## 2. Điều gì xảy ra trong phép thử pattern?

Xét:

```java
if (value instanceof String text) {
    // ...
}
```

Có thể hình dung quá trình như sau:

```text
Đánh giá value
      |
      v
Lấy giá trị runtime
      |
      v
Thử type pattern String text
      |
      +-- Khớp (String, không null)
      |      |
      |      +--> Kết quả instanceof = true
      |      +--> Binding text tới đối tượng String
      |      +--> Nhánh đúng được phép dùng text
      |
      +-- Không khớp (khác String hoặc null)
             |
             +--> Kết quả instanceof = false
             +--> Không có binding text
             +--> Không thể dùng text trên đường đi này
```

**Binding** ở đây nghĩa là gắn một giá trị phù hợp cho pattern variable. Nó không tạo ra bản sao đối tượng. Với `Object value = "Java"`, trong nhánh khớp, `value` và `text` cùng tham chiếu đến chuỗi `"Java"`; điểm khác biệt là `value` có kiểu tĩnh `Object` còn `text` có kiểu tĩnh `String`.

Từ đó có hai tính chất quan trọng:

1. **Giá trị runtime quyết định match thành công hay thất bại.** Một biến có kiểu tĩnh `Object` vẫn có thể giữ đối tượng `String` và match thành công.
2. **Luồng điều khiển quyết định vị trí được dùng pattern variable.** Đã có một phép thử `instanceof` ở phía trên không có nghĩa là mọi dòng phía dưới đều dùng được biến.

Java không tự gán `null`, chuỗi rỗng hay một giá trị mặc định vào `text` khi phép thử thất bại. Không có binding thì không có giá trị `text` hợp lệ để sử dụng.

## 3. Ba tình huống cần phân biệt

| Giá trị của `value` | Kết quả `value instanceof String text` | Có binding `text`? | Nhánh nào chạy? |
| --- | --- | --- | --- |
| `"Java"` | `true` | Có, `text` trỏ tới `"Java"` | Nhánh `if` |
| `42` | `false` | Không | Nhánh `else` |
| `null` | `false` | Không | Nhánh `else` |

Lưu ý: kiểm tra kiểu bằng `instanceof` với `null` trả về `false`, tự nó **không ném `NullPointerException`**. Tuy nhiên điều đó không có nghĩa biến pattern được binding thành `null`.

Một lỗi suy luận phổ biến là “`text` có kiểu `String` rồi nên có thể dùng như `String` ở mọi nhánh”. Kiểu được khai báo trong pattern chỉ có ích **khi pattern thành công và tại nơi biến nằm trong scope**. Trình biên dịch không cho phép một đường đi thất bại dùng một binding chưa từng được thiết lập.

## 4. Ví dụ Java 17+ chạy được: cùng một phép thử với ba đầu vào

Lưu tệp **`FailedMatchScopeDemo.java`**:

```java
public class FailedMatchScopeDemo {
    static void explain(Object input) {
        if (input instanceof String text) {
            System.out.println("matched: " + text + " (" + text.length() + ")");
        } else {
            System.out.println("no String match: " + input);
        }
    }

    public static void main(String[] args) {
        explain("Java");
        explain(42);
        explain(null);
    }
}
```

Biên dịch và chạy:

```bash
javac FailedMatchScopeDemo.java
java FailedMatchScopeDemo
```

Kết quả chuẩn:

```text
matched: Java (4)
no String match: 42
no String match: null
```

- Lượt 1: `"Java"` khớp type pattern `String text`; `text.length()` được gọi trong nhánh đã khớp, cho kết quả `4`.
- Lượt 2: `42` không khớp, vì đối tượng runtime là `Integer`; nhánh `else` chỉ dùng biến gốc `input`.
- Lượt 3: `null` cũng không khớp; nhánh `else` vẫn in được `input` nhờ phép nối chuỗi của Java.

Ở cả hai lượt thất bại, chương trình **không truy cập `text`**. Điều kiện `instanceof` trả về `false` bình thường, nên chương trình vẫn chạy; chỉ khi cố gắng tham chiếu `text` trong vùng không hợp lệ thì mới có lỗi **biên dịch**.

## 5. Flow scoping: “ở đâu chắc chắn đã match?” quan trọng hơn “đã viết điều kiện ở đâu?”

**Flow scoping** là cách Java xác định scope của pattern variable dựa trên các đường đi điều khiển. Trong trường hợp type pattern cho `instanceof`, ta thường hỏi:

- Để đến vị trí này, bắt buộc phép thử pattern trước đó phải đúng không?
- Có đường đi nào đến đây mà pattern thất bại không?
- Có phép phủ định `!`, nối `&&`, nối `||` hoặc câu lệnh kết thúc sớm thay đổi câu trả lời không?

### 5.1. Vùng an toàn: nhánh đúng của `if`

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // Hợp lệ
}
```

Mọi lần thực thi vào phần thân đều đi qua match thành công. Biến `text` đã được binding.

### 5.2. Vùng không an toàn: nhánh `else`

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    // System.out.println(text.length()); // Sai nếu mở comment
}
```

Đến nhánh `else` nghĩa là phép thử pattern **không khớp**. Không thể dùng `text` ở đây; dùng trực tiếp biến `value` nếu chỉ cần báo lỗi, hoặc xử lý kiểu khác bằng phép thử riêng.

### 5.3. Vùng không an toàn: phía sau `if` thông thường

```java
if (value instanceof String text) {
    System.out.println(text);
}

// System.out.println(text.length()); // Sai nếu mở comment
```

Dòng sau `if` có thể được thực thi dù pattern vừa thất bại, bởi nhánh `if` có thể bị bỏ qua. Việc có một câu lệnh `if` ở phía trên không đủ chứng minh `text` đã được binding.

### 5.4. Vùng an toàn: vế phải của `&&`

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase());
}
```

`&&` được đánh giá **ngắn mạch**: vế phải chỉ được xét khi vế trái là `true`. Nếu Java đã tới `text.length()`, chắc chắn `value instanceof String text` đã khớp. Bởi vậy biến `text` hợp lệ tại vế phải và trong thân nhánh đúng.

Nếu `value = "Go"`, pattern `String text` thực ra **đã khớp**, nhưng `text.length() >= 4` là `false`. Do đó toàn bộ điều kiện `if` là sai. Điều này dẫn đến một quy tắc tinh tế: một nhánh `else` sau điều kiện `&&` có thể chạy vì **pattern thất bại** hoặc vì **phần kiểm tra bổ sung thất bại**.

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println(text);
} else {
    // Không được dùng text ở đây:
    // có thể là 42 (pattern fail) hoặc "Go" (pattern match, điều kiện độ dài fail).
}
```

### 5.5. Vùng không an toàn: vế phải của `||`

```java
// Sai nếu mở comment: vế phải chỉ chạy khi vế trái không match.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("...");
// }
```

`||` chỉ đánh giá vế phải khi vế trái là `false`. Khi đó không có bảo đảm `text` đã được binding; Java từ chối sử dụng nó.

Cần phân biệt: Java vẫn có thể dùng **một biểu thức boolean bình thường** ở vế phải `||`, nhưng không thể dùng pattern variable chưa được bảo đảm binding:

```java
if (value instanceof String text || value == null) {
    // value dùng được vì đã được khai báo sẵn.
    // text không được đảm bảo tồn tại ở đây.
}
```

Ở ví dụ này, điều kiện có thể đúng vì `value == null` dù pattern không khớp, nên thân `if` cũng không phải nơi an toàn để dùng `text`.

## 6. Vì sao phủ định `!` và `return` có thể cho phép dùng biến phía sau?

Phủ định thay đổi ý nghĩa các nhánh điều kiện:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải String");
} else {
    System.out.println(text.length()); // Hợp lệ: đi vào else nghĩa là đã match
}
```

Vì biểu thức bên ngoài là `!(...)`, nhánh `else` của `if` phủ định chỉ chạy khi phép thử gốc `value instanceof String text` đã trả về `true`. Flow scoping xét điều kiện **gốc** và phép phủ định, nên `text` hợp lệ trong nhánh `else` này.

Một kỹ thuật rất thường dùng là **guard clause** (nhánh loại bỏ sớm):

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    return text.length(); // Hợp lệ
}
```

Phân tích:

1. Nếu pattern không khớp, điều kiện phủ định là `true` và phương thức **kết thúc ngay** bằng `return -1`.
2. Nếu thực thi đến lệnh `return text.length()` ở cuối, đường đi không khớp **không còn khả năng tới đây**.
3. Vì thế Java biết chắc `text` đã được binding với một `String` phù hợp.

Ở đây, biến không được “hồi sinh” sau thất bại; chính nhánh thất bại **đã rời khỏi phương thức**, còn phần mã phía dưới chỉ dành cho nhánh thành công.

Tương tự, một nhánh phủ định kết thúc bằng `throw` có thể bảo đảm những câu lệnh bình thường phía sau chỉ chạy khi match thành công. Dù dùng `return` hay `throw`, cần xét **mọi đường đi có thể tiếp tục** tới vị trí dùng biến.

## 7. Ví dụ Java 17+ chạy được: xử lý an toàn với guard clause và `&&`

Lưu tệp **`SafeFlowScopeDemo.java`**:

```java
public class SafeFlowScopeDemo {
    static String categorize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isEmpty()) {
            return "empty";
        }
        return "string length=" + text.length();
    }

    static String withConjunction(Object value) {
        if (value instanceof String text && text.length() >= 4) {
            return "long=" + text.toUpperCase();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(categorize("Java"));
        System.out.println(categorize(""));
        System.out.println(categorize(17));
        System.out.println(categorize(null));
        System.out.println(withConjunction("Java"));
        System.out.println(withConjunction("Go"));
        System.out.println(withConjunction(null));
    }
}
```

Biên dịch và chạy:

```bash
javac SafeFlowScopeDemo.java
java SafeFlowScopeDemo
```

Kết quả chuẩn:

```text
string length=4
empty
not a string
not a string
long=JAVA
other
other
```

Trong `categorize`, mọi giá trị không phải `String` (gồm `null`) rời khỏi phương thức trước khi dùng `text`. Các lệnh sau guard clause vì vậy an toàn. Chuỗi rỗng `""` vẫn là một `String` và vẫn khớp pattern; nó chỉ được tách ra ở bước `text.isEmpty()`.

Trong `withConjunction`, lệnh `text.length()` được bảo vệ bởi vế trái `instanceof`. Với `"Go"`, pattern khớp nhưng điều kiện độ dài sai. Với `null`, pattern thất bại và Java không hề đánh giá `text.length()`.

## 8. Vì sao không thể “lấy lại” pattern variable thông qua một biến `boolean`?

Đoạn sau cố ý **không biên dịch** nếu mở comment:

```java
Object value = "Java";
boolean matched = value instanceof String text;

if (matched) {
    // System.out.println(text.length()); // Sai
}
```

Mặc dù `matched` chứa kết quả `true` trong ví dụ cụ thể, quy tắc flow scoping **không suy diễn scope của pattern variable từ một biến boolean được khai báo riêng**. `text` không có scope hợp lệ trong thân `if (matched)`. Java xét các quy tắc ngữ pháp và luồng điều khiển của biểu thức pattern nơi biến được khai báo, không xem một giá trị `boolean` bất kỳ như bằng chứng để mang binding sang phạm vi mới.

Cách đúng là dùng biến ngay trong nhánh mà pattern bảo đảm thành công:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Hoặc dùng guard clause để chỉ cho luồng đã match đi tiếp:

```java
if (!(value instanceof String text)) {
    return; // hợp lệ trong phương thức kiểu void
}
System.out.println(text.length());
```

*Đoạn thứ hai là phần thân minh họa của một phương thức `void`; không phải một lớp Java độc lập để biên dịch trực tiếp.*

## 9. Khi match thất bại, nên xử lý giá trị bằng cách nào?

Tùy yêu cầu chương trình, có ba cách xử lý rõ ràng.

**Cách A — Dùng target ban đầu trong nhánh sai.** Mục đích là log, báo lỗi hoặc xử lý mặc định:

```java
if (value instanceof String text) {
    System.out.println("length=" + text.length());
} else {
    System.out.println("Unsupported value: " + value);
}
```

`value` là biến đã khai báo ngoài điều kiện, vì vậy có thể dùng ở cả hai nhánh.

**Cách B — Khớp một mẫu khác.** Nếu đầu vào có nhiều kiểu được hỗ trợ, mỗi type pattern giới thiệu **một biến riêng** trong nhánh thành công của nó:

```java
if (value instanceof String text) {
    System.out.println("String length=" + text.length());
} else if (value instanceof Integer number) {
    System.out.println("Integer value=" + number);
} else {
    System.out.println("Unsupported or null");
}
```

`number` không phải giá trị mặc định của `text`. Nó được binding khi **pattern `Integer number` riêng** khớp.

**Cách C — Kiểm tra sớm và kết thúc ở nhánh thất bại.** Dùng khi phần còn lại của phương thức chỉ phục vụ kiểu được hỗ trợ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.strip();
}
```

Không có đường đi thất bại nào tới lời gọi `text.strip()`. Lưu ý `strip()` thực hiện thao tác trên chuỗi đã khớp; nó không liên quan đến việc đánh giá lại pattern.

Nếu muốn nhận một giá trị dự phòng thật sự, hãy **khai báo một biến dự phòng riêng với quy tắc gán rõ ràng**. Đừng giả định Java tạo `text = null` khi match không thành công.

## 10. Liên hệ với `switch` pattern matching (Java 21+)

Cơ chế binding chỉ khi khớp cũng xuất hiện trong pattern matching cho `switch`, được chuẩn hóa từ **Java 21**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "text=" + text;
        case String text -> "blank String";
        case Integer number -> "number=" + number;
        case null -> "null";
        default -> "other";
    };
}
```

Đây là phương thức minh họa dùng được trong một lớp Java 21+. Với `case String text`, `text` được binding trong guard `when` và nhánh áp dụng khi pattern đã khớp. Nếu nhánh ấy không được chọn, không thể tùy tiện dùng tên `text` ở nhánh `Integer`, `null` hoặc `default`. Mỗi nhánh có các binding của pattern tương ứng.

Với `"   "`, type pattern `String text` ở nhánh đầu có thể khớp nhưng guard `!text.isBlank()` là sai; nhánh `case String text` kế tiếp sẽ được chọn. Đây là một ví dụ nữa cho thấy **khớp kiểu thành công** và **điều kiện bổ sung thành công** là hai chuyện khác nhau.

Cần phân biệt hai mốc phiên bản: type pattern cho `instanceof` dùng được trong Java 17; `when` trong `switch` như trên cần Java 21+. Những ví dụ Java 17 ở các phần trước không yêu cầu cú pháp `switch` này.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Pattern thất bại thì `text` được gán `null`.” | Không có binding khi type pattern thất bại; Java không cung cấp giá trị `text` mặc định. |
| “Đã khai báo `String text` thì dùng `text` ở `else` được.” | Tên pattern variable chỉ nằm trong flow scope nơi match được bảo đảm. |
| “`instanceof` trả về `false` là một lỗi chạy.” | Với type pattern, kết quả `false` là bình thường; cố dùng pattern variable ngoài scope mới gây lỗi biên dịch. |
| “Sau `if` lúc nào cũng dùng được biến của pattern.” | Chỉ khi mọi đường đi tới vị trí ấy bảo đảm match, chẳng hạn nhánh không khớp đã `return`. |
| “`instanceof String text && ...` vào `else` nghĩa là `String` không khớp.” | Có thể pattern đã khớp nhưng điều kiện sau `&&` sai. |
| “Vế phải `||` sẽ có `text` của vế trái.” | Vế phải `||` chỉ chạy khi vế trái sai, nên không bảo đảm binding. |
| “Lưu kết quả vào `boolean matched` sẽ mang scope của `text` theo.” | Flow scoping không truyền binding bằng cách suy diễn từ biến boolean độc lập. |
| “`null` là `String` có giá trị rỗng.” | `null` không khớp type pattern `String text`. Chuỗi `""` thì khớp và có độ dài 0. |

Một lỗi khác là dùng phép ép kiểu thủ công trong nhánh sai:

```java
if (!(value instanceof String text)) {
    // String wrong = (String) value; // Có thể ném ClassCastException
}
```

Pattern matching không làm phép ép kiểu không hợp lệ trở nên an toàn. Khi giá trị không phải `String`, cần xử lý trường hợp ấy hoặc từ chối đầu vào.

## 12. Tự kiểm tra flow scoping trước khi chạy

Đối với mỗi chỗ dùng pattern variable, hãy thử lần lượt:

1. **Xác định pattern được khai báo ở đâu.** Ví dụ `value instanceof String text`.
2. **Xác định điều kiện match của pattern.** Với type pattern `String`: giá trị khác `null` và phù hợp kiểu `String`.
3. **Liệt kê các đường đi có thể tới dòng dùng biến.** Từ nhánh đúng? Nhánh sai? Sau `&&` hay `||`? Có `!` không?
4. **Tìm đường đi chưa match.** Nếu tồn tại một đường đi đến dòng đó mà pattern không được bảo đảm thành công, không nên viết code phụ thuộc vào binding của biến.
5. **Sửa cấu trúc điều khiển.** Đặt code vào nhánh match; dùng `&&` để bảo vệ điều kiện bổ sung; dùng `return`/`throw` ở nhánh thất bại; hoặc kiểm tra một pattern mới cho kiểu khác.

Ví dụ tự kiểm tra nhanh:

```java
// HỢP LỆ: sử dụng khi chắc chắn match.
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}

// KHÔNG HỢP LỆ nếu bỏ comment ở câu lệnh in:
// if (value instanceof String text || value == null) {
//     System.out.println(text);
// }
```

Ở ví dụ thứ hai, điều kiện có thể đúng chỉ vì `value == null`, nên không có bảo đảm `text` đã được binding.

## Kết luận

Không dùng được pattern variable khi match thất bại vì **chưa có binding hợp lệ cho biến**, và Java kiểm tra trước khi chạy để bảo đảm mọi chỗ sử dụng biến đều có đường đi đã match. **Flow scoping** nối việc khớp mẫu với luồng điều khiển: nhánh đúng, vế phải `&&` và mã sau guard clause có thể được bảo đảm; nhánh sai, vế phải `||` hoặc dòng phía sau một `if` thông thường thường không có bảo đảm đó.

Khi cần viết code an toàn, hãy luôn hỏi: **“Có con đường nào đến đây mà pattern chưa khớp không?”** Nếu có, phải thay đổi vị trí sử dụng biến hoặc tổ chức lại nhánh điều khiển.
