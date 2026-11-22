# Sử dụng biến mẫu trong nhánh `if` khớp — phạm vi biến mẫu của `instanceof` (Java 16+)

> Mục tiêu: sử dụng đúng biến mẫu được tạo từ `instanceof` trong nhánh `if` khớp, hiểu tại sao biến không dùng được ở nhánh không khớp, và nắm quy tắc **flow scoping** khi phối hợp `&&`, `||`, `!`, `else if` hoặc kiểm tra sớm rồi `return`. Pattern matching cho `instanceof` đã trở thành tính năng **chính thức ở Java 16**; mọi cú pháp ở đây hợp lệ với JDK 17+ mà không cần `--enable-preview`. Không sử dụng cú pháp Java 14/15 ở giai đoạn preview.

## 1. Biến mẫu được tạo khi nào?

Thông thường `instanceof` trả một giá trị `boolean` cho biết tham chiếu có thuộc một kiểu nhất định hay không. Với **type pattern**, ta kết hợp việc kiểm tra kiểu và khai báo một biến nhận giá trị đã được chuyển sang kiểu ấy:

```java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

Trong `value instanceof String text`:

- `value` là biểu thức được kiểm tra, có kiểu tĩnh `Object`.
- `String` là kiểu tham chiếu được hỏi tới.
- `text` là **pattern variable**, được khai báo và khởi tạo bằng tham chiếu cùng giá trị đối tượng khi phép khớp thành công; kiểu tĩnh của `text` là `String`.
- Nếu kết quả `instanceof` là `true`, Java cho phép dùng `text` ở những vị trí chắc chắn đã khớp.
- Nếu không khớp hoặc `value == null`, `instanceof` cho `false` và không có đường chạy nào được phép đọc biến chưa khởi tạo.

Biến `text` không phải field của class, không phải biến thành viên record và cũng không tự đổi **kiểu tĩnh** của biến `value`; muốn gọi phương thức `String` thì dùng `text`, không viết `value.toUpperCase()` khi `value` vẫn có kiểu `Object`.

### So sánh với cách viết tách kiểm tra và cast

```java
// Cách không dùng pattern: cần cast rõ ràng.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}

// Cách hiện hành gọn hơn: kiểm tra và đặt tên biến cùng một chỗ.
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Hai đoạn là **snippet thay thế**, không đặt trùng tên biến cùng chỗ nếu cấu trúc phương thức làm chúng xung đột. Cách thứ hai tránh viết lại cast và tránh nhầm kiểu giữa lệnh `instanceof` với lệnh ép kiểu thủ công. Không có cast không an toàn khi pattern đã khớp.

## 2. Nhánh `if` nào được phép đọc biến mẫu?

Xét cấu trúc `if (object instanceof String text) { ... } else { ... }`. **Chỉ nhánh `then` (nhánh khớp)** chắc chắn có `text`.

```java
Object object = "cat";
if (object instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: đã khớp String.
} else {
    System.out.println("Not a String");
    // Không được dùng text ở đây.
}
// Không được mặc nhiên dùng text ở đây.
```

Đừng hiểu biến mẫu giống biến khai báo ở đầu phương thức: **phạm vi biến mẫu theo luồng điều khiển** (*flow scoping*) được xác định theo điểm mà compiler chứng minh pattern đã khớp. Một đường đi đi vào `else` là đường mà điều kiện `instanceof String text` không khớp; biến `text` không được phép sử dụng ở đó.

| Vị trí | Có thể sử dụng biến mẫu `text` của `if (o instanceof String text)`? | Lý do |
|---|---|---|
| Trong thân `if` khi điều kiện nguyên bản đúng | **Có** | Pattern đã khớp; `text` được khởi tạo |
| Trong `else` của điều kiện đó | **Không** | Đây là trường hợp pattern không khớp |
| Ngay sau toàn bộ `if/else` thông thường | **Không tự động** | Có đường đi tới đó không qua phép khớp |
| Vế phải `&&` sau `o instanceof String text` | **Có** | Short-circuit bảo đảm vế trái đúng mới xét vế phải |
| Vế phải `||` sau `o instanceof String text` | **Không** | Vế phải chỉ chạy khi vế trái sai |
| Sau `if (!(o instanceof String text)) return ...;` | **Có** | Đường đi còn lại chắc chắn khớp |

Đây là quy tắc tĩnh của trình biên dịch: việc thử vài input cho thấy chương trình đi vào một nhánh không làm một tên biến mẫu trở nên hợp lệ ở các nhánh khác.

## 3. Dùng `&&` để kiểm tra điều kiện phụ trên biến vừa khớp

Toán tử **conditional AND** `&&` đánh giá từ trái sang phải và bỏ qua vế phải nếu vế trái `false`. Vì vậy khi vế trái là phép khớp mẫu, vế phải có thể dùng biến mẫu:

```java
Object input = "Java";
if (input instanceof String text && text.length() >= 3) {
    System.out.println("Long text: " + text);
}
```

Điều kiện phụ `text.length() >= 3` **chỉ được đánh giá sau khi** `input` chắc chắn là `String`; không cần cast. Khi toàn bộ điều kiện đúng, `text` tiếp tục có phạm vi trong thân `if`.

Thực tế nên dùng biểu thức kiểm tra ngắn, dễ đọc như:

```java
if (input instanceof String text && !text.isBlank()) {
    String normalized = text.strip();
    System.out.println(normalized);
}
```

**Phân biệt việc khớp và điều kiện phụ:** nếu `input` là chuỗi toàn khoảng trắng, pattern `String text` vẫn **khớp**, nhưng điều kiện phụ `!text.isBlank()` là `false`. Khối `if` không chạy; biến `text` cũng không tự mở rộng phạm vi ra sau điều kiện.

Nếu cần nhiều điều kiện hoặc nghiệp vụ phức tạp, có thể kiểm tra type pattern trước rồi đặt các lệnh tiếp theo **bên trong nhánh** thay vì xây chuỗi `&&` quá dài.

## 4. Vì sao `||` không dùng được như `&&`?

Conditional OR `||` **chỉ kiểm tra vế phải khi vế trái sai**. Nếu vế trái là `input instanceof String text`, đường chạy đến vế phải là đường **không khớp**, nên `text` không có giá trị chắc chắn.

Đoạn **cố ý sai, không biên dịch**:

```java
if (input instanceof String text || text.isEmpty()) {
    System.out.println("matched");
}
```

Ở vế phải `text.isEmpty()` sẽ báo lỗi phạm vi tên biến: compiler không cho dùng `text` khi phép khớp ở vế trái có thể không thành công. Ngay cả khi vế phải chỉ dùng một biến boolean khác, toàn bộ điều kiện `||` có thể đúng do vế phải đúng mà **không** khớp `String`; không được dựa vào `text` trong nhánh `if` như thể mọi đường đi đều khớp.

Sửa tùy mục đích:

```java
// Muốn kiểm tra String không rỗng: dùng &&.
if (input instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

Hoặc tách hai trường hợp độc lập để mỗi trường hợp dùng đúng biến cục bộ của mình. Không thay `&&` bằng `&` khi cần hành vi short-circuit và chắc chắn đã khớp.

## 5. Phủ định `!` và mẫu guard clause (kiểm tra sớm)

Phủ định thay đổi bên nào chứng minh được pattern đã khớp:

```java
if (!(input instanceof String text)) {
    System.out.println("Not a String");
    // text KHÔNG được dùng ở nhánh này.
} else {
    System.out.println(text.length()); // Hợp lệ: phủ định là false => khớp.
}
```

Đây là điểm khác biệt với suy đoán “biến luôn chỉ nằm trong nhánh `if`”: biến có thể nằm trong **nhánh `else`** nếu điều kiện là phủ định của pattern.

Ví dụ dùng guard clause là một cách thiết kế gọn, vẫn hợp lệ với Java hiện đại:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    // Điểm này chỉ đạt tới nếu value đã khớp String.
    return text.length();
}
```

Đoạn trên là **phương thức minh họa** cần đặt trong một class. Nhánh phủ định thoát bằng `return`, nên mọi đường đi còn lại sau `if` phải là trường hợp khớp; compiler cho phép đọc `text` ở sau. Nếu thay `return -1;` bằng lệnh in rồi tiếp tục chạy, điều kiện bảo đảm này mất đi, và dùng `text` ngay sau `if` sẽ lỗi biên dịch.

Viết `throw new IllegalArgumentException(...)` trong nhánh không khớp cũng là cách hợp lệ khi API muốn **từ chối đầu vào sai kiểu** thay vì trả giá trị dự phòng. Điểm quan trọng không phải có cặp dấu `{}` hay không, mà là **đường đi khi không khớp không thể tiếp tục đến chỗ dùng biến mẫu**.

## 6. `else if`, tên biến và phạm vi độc lập

Trong chuỗi điều kiện, mỗi nhánh được xét theo thứ tự, và biến mẫu của nhánh thành công chỉ có hiệu lực tại đường đi mà nhánh ấy khớp:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Text:" + text;
    } else if (value instanceof Integer number) {
        return "Integer:" + number;
    } else {
        return "Other";
    }
}
```

`text` thuộc nhánh `String`, `number` thuộc nhánh `Integer`; nhánh `else` không thể đọc cả hai. Do các phạm vi có thể không chồng nhau, Java cho phép **dùng lại cùng tên pattern variable** ở các nhánh `else if` độc lập khi quy tắc đặt tên vẫn được đáp ứng, tuy nhiên trong bài học nên chọn tên khác nhau để diễn đạt kiểu rõ ràng.

Không được cố ý khai báo một biến mẫu cùng tên với biến cục bộ đã có và vẫn nằm trong phạm vi, chẳng hạn:

```java
String text = "outside";
if (value instanceof String text) { // LỖI: text bị khai báo trùng.
    System.out.println(text);
}
```

Những mẫu ở đây là **pattern variable** có phạm vi theo luồng, không giống một biến thành viên `this.text`. Nếu code có tên bị trùng, đổi tên biến mẫu hoặc cấu trúc lại các khối; không dựa vào việc `if` có thể `false` để lờ xung đột tên.

## 7. Biến mẫu ở toán tử điều kiện `? :`

Toán tử ba ngôi có thể dùng trực tiếp một type pattern trong điều kiện; biến mẫu có phạm vi ở nhánh mà compiler biết pattern đúng:

```java
Object input = " ready ";
String label = input instanceof String text ? text.strip() : "unknown";
// label = "ready"; text không tự có phạm vi ngoài biểu thức ba ngôi.
```

Phần trước `:` tương ứng điều kiện true nên được dùng `text`; phần sau `:` là điều kiện false nên không được dùng `text` từ pattern dương. Với trường hợp nhiều bước hoặc thông báo lỗi phức tạp, cấu trúc `if/else` thường dễ đọc hơn ternary dài.

## 8. `null`, kiểu tĩnh và những giới hạn cần nhớ

- `value == null` khiến `value instanceof String text` là `false`; không có trường hợp khớp rồi tạo biến mẫu `text` trỏ `null` trong type pattern `instanceof` này. Có thể xử lý null trong nhánh `else` hoặc trước `if`.
- Type pattern sử dụng kiểu tham chiếu tương thích với toán hạng. Với các kiểu generic, không thể dùng `instanceof List<String> names` theo cách kiểm tra toàn bộ tham số kiểu tại runtime vì **type erasure**. Có thể dùng `List<?> list` rồi kiểm tra phần tử phù hợp.
- Biến mẫu có kiểu tĩnh là kiểu được nêu trong pattern. Ví dụ `Object value` vẫn có kiểu tĩnh `Object` ngay trong nhánh; `text` mới có kiểu `String`. Đừng gán nhầm sự thu hẹp kiểu tĩnh cho biến nguồn.
- Pattern matching cho `instanceof` không thay đổi `equals()` hay logic nghiệp vụ; nó chỉ kiểm tra runtime type và cung cấp biến đã được gán tương ứng.
- Từ Java 16, pattern variable của `instanceof` **không mặc định là `final`**. Dù cú pháp có thể cho phép gán lại tên biến mẫu trong phạm vi của nó, việc giữ giá trị đã khớp ổn định và tạo biến mới cho dữ liệu chuẩn hóa thường dễ đọc hơn.
- Phạm vi biến mẫu là **quy tắc biên dịch**. Runtime sẽ không “cấp quyền truy cập” một biến khi code ở ngoài phạm vi; lỗi là lỗi biên dịch chứ không phải `ClassCastException` xảy ra muộn.

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`PatternIfScopeDemo.java`**. Chương trình minh họa nhánh `if` khớp, `else if`, `&&`, kiểm tra `null`, guard clause phủ định và xử lý số nguyên:

```java
public class PatternIfScopeDemo {
    record Customer(String name, int points) {}

    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(" + text.strip() + "):" + text.length();
        } else if (value instanceof Customer customer) {
            return "Customer:" + customer.name() + ":" + customer.points();
        } else {
            return "Other";
        }
    }

    static String classify(Object candidate) {
        if (candidate instanceof String text && !text.isBlank()) {
            return "nonblank:" + text.strip();
        }
        return "not-nonblank";
    }

    static int positiveLength(Object candidate) {
        if (!(candidate instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static String choose(Object candidate) {
        if (candidate instanceof String text && text.length() >= 3) {
            return "long:" + text;
        }
        return "short-or-other";
    }

    static String asType(Object candidate) {
        if (candidate instanceof Integer number) {
            return "int:" + (number + 1);
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(describe(" code "));
        System.out.println(describe(new Customer("Mai", 40)));
        System.out.println(describe(null));
        System.out.println(classify("  ok  "));
        System.out.println(classify("   "));
        System.out.println(positiveLength("abc"));
        System.out.println(positiveLength(42));
        System.out.println(choose("ABCD"));
        System.out.println(choose(9));
        System.out.println(asType(41));
    }
}
```

Biên dịch và chạy từ thư mục chứa file (JDK 17+):

```bash
javac -encoding UTF-8 PatternIfScopeDemo.java
java PatternIfScopeDemo
```

**Stdout chính xác:**

```text
String(code):6
Customer:Mai:40
Other
nonblank:ok
not-nonblank
3
-1
long:ABCD
short-or-other
int:42
```

Giải thích nhanh: `describe(" code ")` khớp `String`, `strip()` loại khoảng trắng nhưng độ dài gốc của `" code "` là 6. `Customer` khớp ở nhánh `else if`. `null` không khớp. `classify` dùng `&&` để kiểm tra `isBlank` chỉ sau khi thành `String`. `positiveLength` chỉ dùng `text` sau guard clause đã loại kiểu khác. `choose` kết hợp kiểm tra kiểu và độ dài; `asType` tạo `Integer number` trong nhánh khớp.

## 10. Lỗi biên dịch thường gặp và cách sửa

Các đoạn dưới đây **cố ý sai** để minh họa phạm vi; không ghép trực tiếp vào chương trình ở mục 9.

### Sai 1 — dùng biến mẫu ở `else` khi điều kiện không phủ định

```java
if (object instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println(text); // Sai: nhánh này không bảo đảm khớp.
}
```

**Sửa:** xử lý `object` như một giá trị chưa được khớp trong nhánh `else`, hoặc kiểm tra một pattern khác. Không chuyển `text` ra khỏi `if` chỉ để né compiler nếu dữ liệu có thể không phải String.

### Sai 2 — dùng biến mẫu sau `if` dù đường không khớp vẫn tiếp tục

```java
if (object instanceof String text) {
    System.out.println("String value");
}
System.out.println(text.length()); // Sai: object có thể không là String.
```

**Sửa:** đặt lệnh đọc `text` vào nhánh true; hoặc dùng `if (!(object instanceof String text)) return;` trong phương thức `void`, rồi tiếp tục đọc `text` sau câu guard.

### Sai 3 — dùng biến mẫu ở vế phải `||`

```java
if (object instanceof String text || text.isBlank()) {
    System.out.println("check");
}
```

**Sửa:** thay bằng `&&` nếu cần thêm điều kiện phụ cho String đã khớp; hoặc tách logic không liên quan thành các nhánh độc lập.

### Sai 4 — dùng tên đã được khai báo

```java
String text = "existing";
if (object instanceof String text) {
    System.out.println(text);
}
```

**Sửa:** chọn tên mới như `matchedText`; pattern variable không được che khuất biến cục bộ cùng tên đang ở trong phạm vi.

### Sai 5 — giả định biến nguồn đã tự thành kiểu String

```java
Object object = "hello";
if (object instanceof String text) {
    System.out.println(object.toUpperCase()); // Sai: Object không có phương thức này.
}
```

**Sửa:** gọi `text.toUpperCase()`; tên `text` có kiểu tĩnh `String` do pattern bảo đảm.

### Sai 6 — dùng pattern generic không kiểm tra được tại runtime

```java
if (object instanceof java.util.List<String> strings) {
    System.out.println(strings.size());
}
```

**Sửa:** dùng `object instanceof java.util.List<?> list` rồi xử lý từng phần tử hoặc áp dụng kiểm tra dữ liệu rõ ràng. Type erasure không cho xác nhận toàn bộ danh sách là `List<String>` qua type pattern runtime.

## 11. Checklist trước khi sử dụng trong mã thực tế

1. `instanceof` có kiểm tra đúng kiểu tham chiếu cho miền dữ liệu? Đầu vào `null` đã có chính sách xử lý?
2. Biến mẫu có được **đọc** tại nơi compiler chắc chắn phép khớp thành công (`then` của điều kiện dương, `else` của điều kiện phủ định, vế phải `&&` hợp lệ)?
3. Nếu dùng biến mẫu **sau** `if`, đường đi không khớp đã chấm dứt bằng `return` hoặc `throw` thật sự?
4. Có tránh dùng biến mẫu ở vế phải `||` hoặc nhánh có thể vào mà không khớp?
5. Tên biến mẫu có xung đột với biến cục bộ hoặc tham số đang trong phạm vi?
6. Trong `else if`, có giữ biến của từng nhánh độc lập và không nhầm lẫn giữa các kiểu?
7. Có dùng biến mẫu đúng kiểu thay vì gọi phương thức chuyên biệt trên biến nguồn kiểu `Object`?
8. Không dùng type pattern generic không thể kiểm tra vì erasure?
9. Đã test ít nhất các trường hợp: đúng kiểu, sai kiểu, `null`, chuỗi rỗng/trắng, điều kiện phụ đúng/sai và guard clause?
10. Đã biên dịch bằng Java 17+ mà không dùng tính năng preview và kiểm tra stdout của ví dụ?

## Tài liệu chính thức

- Oracle, *Pattern Matching with instanceof* (Java SE 25): https://docs.oracle.com/en/java/javase/25/language/pattern-matching-instanceof.html
- Oracle, *Pattern Matching for instanceof* (Java SE 17): https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html
- Java Language Specification, §6.3 *Scope of a Declaration* (flow-scoping pattern variables): https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-6.html#jls-6.3
- Java Language Specification, §15.20.2 *Type Comparison Operator instanceof*: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.20.2
- OpenJDK JEP 394, *Pattern Matching for instanceof* (tính năng được hoàn thiện ở Java 16): https://openjdk.org/jeps/394
