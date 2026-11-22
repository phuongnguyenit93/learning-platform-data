# Phạm vi biến trong conditional expression (toán tử ? :) của Java

## 1. Vì sao kiểm tra đúng kiểu mà vẫn có thể gặp lỗi biến không tồn tại?

Pattern matching cho phép kiểm tra kiểu và đặt tên cho giá trị trong một biểu thức:

~~~java
value instanceof String text
~~~

Nếu phép kiểm tra khớp, `text` là biến kiểu `String`. Nhưng điều đó **không có nghĩa `text` xuất hiện ở mọi vị trí sau chỗ khai báo**. Java sử dụng *flow scoping*: trình biên dịch dựa vào đường đi mà chương trình có thể thực hiện để xác định tại vị trí nào pattern variable chắc chắn đã được gắn giá trị (*definitely matched*).

Chủ đề này tập trung vào **conditional expression** sử dụng toán tử ba ngôi `? :`:

~~~java
condition ? expressionWhenTrue : expressionWhenFalse
~~~

Khi `condition` đúng, Java đánh giá nhánh sau `?`; khi sai, Java đánh giá nhánh sau `:`. Nếu `condition` có `instanceof` pattern, nhánh nào được dùng biến pattern phụ thuộc vào việc nhánh đó **chắc chắn tương ứng với một lần khớp thành công**.

Sau bài học, bạn có thể:

- Giải thích khi nào biến khai báo trong điều kiện của `? :` dùng được ở nhánh đúng và nhánh sai.
- Đọc được phạm vi pattern variable khi điều kiện có phủ định `!`, toán tử `&&` hoặc `||`.
- Hiểu vì sao một biểu thức `? :` hoàn chỉnh **không đưa** pattern variable ra ngoài để sử dụng ở câu lệnh kế tiếp, ngay cả khi kết quả của biểu thức là `boolean`.
- Phân biệt kiểm tra khả năng khớp ở runtime với phép phân tích phạm vi tại compile time.
- Viết mã Java 17+ rõ ràng, an toàn và nhận diện các lỗi biên dịch điển hình.

## 2. Quy tắc cốt lõi của biểu thức a ? b : c

Với một conditional expression:

~~~java
a ? b : c
~~~

Java áp dụng hai quy tắc về pattern variable:

1. Biến pattern được **`a` giới thiệu khi đúng** (*introduced by a when true*) sẽ được đảm bảo đã khớp tại **`b`**.
2. Biến pattern được **`a` giới thiệu khi sai** (*introduced by a when false*) sẽ được đảm bảo đã khớp tại **`c`**.

Hai điều này không có nghĩa là mọi biểu thức ở nhánh `b` hoặc `c` đều được dùng mọi biến xuất hiện trong `a`. Phải xác định **đúng trạng thái true/false mà ở đó pattern đã khớp**.

Sơ đồ luồng thực thi:

~~~text
        a (điều kiện)
         /         \
       true        false
        |            |
        v            v
        b            c
   dùng các biến   dùng các biến
   đã khớp khi    đã khớp khi
   a == true      a == false
        \            /
         \          /
       kết quả của toàn biểu thức
       (không đưa pattern variable
        ra phạm vi bên ngoài)
~~~

**Quy tắc thứ ba rất quan trọng:** bản thân toàn bộ `a ? b : c` **không giới thiệu pattern variable theo trạng thái true hoặc false**. Ngay cả nếu `b` và `c` đều trả về `boolean`, Java không suy ra rằng một biến khai báo trong `a` sẽ chắc chắn tồn tại ở câu lệnh bên ngoài conditional expression.

Các quy tắc này được nêu trong *Java Language Specification* (JLS) `6.3.1.4, áp dụng cho Java 17 và các phiên bản mới hơn.

## 3. Pattern khớp khi điều kiện đúng: biến có phạm vi ở nhánh ?

Ví dụ thường gặp:

~~~java
String result = value instanceof String text
    ? text.toUpperCase()
    : "Not a String";
~~~

Đây là code **minh họa đặt bên trong phương thức**, với `value` có kiểu tĩnh `Object`.

- `value instanceof String text` **giới thiệu `text` khi điều kiện đúng**.
- Nhánh `? text.toUpperCase()` chỉ được chạy sau khi kiểm tra thành công, nên `text` có kiểu `String` và được dùng hợp lệ.
- Nhánh `: "Not a String"` dành cho giá trị không khớp (bao gồm `null`); biến `text` **không** ở trong phạm vi của nhánh này.
- Sau khi hoàn tất biểu thức `? :`, không được dùng `text` ở câu lệnh tiếp theo chỉ dựa trên việc nó từng được khai báo trong điều kiện.

Ví dụ đối xứng nhưng **cố ý không biên dịch**:

~~~java
static String invalid(Object value) {
    return value instanceof String text
        ? text.toUpperCase()
        : text.toLowerCase(); // LỖI: text không tồn tại trong nhánh sai
}
~~~

Ở nhánh sai, `value` có thể là `Integer` hoặc `null`. Java không thể cho phép đọc `text` vì không có giá trị `String` nào được gắn.

Để dùng cùng một kết quả ở cả hai nhánh, hãy tính giá trị đó **sau khi** kiểm tra/chuẩn hóa theo đường đi hợp lệ, hoặc dùng biến cục bộ thông thường có phạm vi phù hợp; không cố kéo pattern variable sang nhánh không khớp.

## 4. Khi có dấu !, nhánh dùng được biến đảo lại

Toán tử phủ định `!` đảo chiều của điều kiện; do đó nó cũng đảo trạng thái mà ở đó biến được đảm bảo đã khớp.

~~~java
String result = !(value instanceof String text)
    ? "Not a String"
    : text.toUpperCase();
~~~

Cách đọc:

- `value instanceof String text` khớp khi giá trị là `String`.
- `!(value instanceof String text)` **đúng** khi `value` không phải `String`. Khi đó nhánh `?` chạy và **không thể** dùng `text`.
- Điều kiện phủ định **sai** nghĩa là phép `instanceof` ban đầu đã khớp. Do đó nhánh `:` được dùng `text`.

Bảng ghi nhớ:

| Điều kiện đứng trước ? | Nhánh được dùng biến pattern | Vì sao? |
| --- | --- | --- |
| `value instanceof String text` | Nhánh sau `?` | Điều kiện đúng chứng minh đã khớp `String` |
| `!(value instanceof String text)` | Nhánh sau `:` | Điều kiện sai chứng minh phép `instanceof` bên trong đúng |

Hãy đọc “biến được giới thiệu khi biểu thức đúng/sai” theo *giá trị của cả điều kiện*, chứ đừng chỉ nhìn thấy tên biến ở vế trái của toán tử.

## 5. Ví dụ chạy được: các dạng ternary trong cùng một chương trình

Lưu mã sau thành tệp `ConditionalScopeDemo.java`. Đây là chương trình đầy đủ, dùng **Java 17+**, không cần bật preview.

~~~java
public class ConditionalScopeDemo {
    static String describe(Object value) {
        return value instanceof String text
            ? "String length=" + text.length()
            : "Other";
    }

    static String normalize(Object value) {
        return !(value instanceof String text)
            ? "Not text"
            : text.isBlank() ? "Blank" : text.trim().toUpperCase();
    }

    static String filtered(Object value) {
        return value instanceof String text && text.length() >= 3
            ? "Long:" + text
            : "Other";
    }

    static String validate(Object value) {
        return !(value instanceof String text) || text.isBlank()
            ? "Invalid"
            : "Valid:" + text.trim();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
        System.out.println(normalize(123));
        System.out.println(normalize("   "));
        System.out.println(normalize("  Java  "));
        System.out.println(filtered("Java"));
        System.out.println(filtered("Hi"));
        System.out.println(filtered(13));
        System.out.println(validate(null));
        System.out.println(validate(" "));
        System.out.println(validate(" hi "));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 ConditionalScopeDemo.java
java ConditionalScopeDemo
~~~

Kết quả chính xác:

~~~text
String length=4
Other
Other
Not text
Blank
JAVA
Long:Java
Other
Other
Invalid
Invalid
Valid:hi
~~~

Giải thích theo từng phương thức:

**`describe`:** Điều kiện `value instanceof String text` đúng thì nhánh `?` mới đọc `text.length()`. Với `42` và `null`, mẫu không khớp, kết quả là `Other`.

**`normalize`:** Điều kiện có dấu `!` nên nhánh `:` là đường đã được chứng minh `value` là `String`. Trong nhánh này có một conditional expression **lồng nhau**: `text.isBlank() ? "Blank" : text.trim().toUpperCase()`. Ở cả hai nhánh của biểu thức lồng nhau, `text` đã ở trong phạm vi nhờ nhánh ngoài; vì vậy cả `text.isBlank()` và `text.trim()` đều hợp lệ. Chuỗi chỉ có khoảng trắng cho kết quả `Blank`; chuỗi `"  Java  "` cho `JAVA`.

**`filtered`:** Điều kiện là `value instanceof String text && text.length() >= 3`. `&&` chỉ đánh giá toán hạng bên phải khi toán hạng bên trái đúng. Vì vậy `text` được dùng an toàn ngay trong vế phải của `&&`; toàn điều kiện đúng cũng bảo đảm đã khớp, cho phép dùng `text` trong nhánh `?`.

**`validate`:** Điều kiện là `!(value instanceof String text) || text.isBlank()`. `||` chỉ đánh giá toán hạng phải khi vế trái sai; nếu vế trái sai, nghĩa là `value instanceof String text` đã khớp. Nhánh `:` chỉ chạy khi toàn điều kiện sai, tức là giá trị phải là một `String` **không blank**, nên có thể dùng `text.trim()`.

## 6. Khi điều kiện kết hợp && và ||, hãy lần theo luồng short-circuit

Cách nghĩ “cứ nằm bên phải pattern là có thể dùng biến” không đủ chính xác. Vấn đề là **có đường thực thi nào tới vị trí đó mà mẫu chưa khớp hay không**.

### 6.1. Toán tử &&

~~~java
value instanceof String text && text.length() > 3
~~~

Vế phải `text.length() > 3` chỉ chạy nếu `instanceof` đúng; như vậy `text` hợp lệ ở vế phải.

Dùng với ternary:

~~~java
String answer = value instanceof String text && text.length() > 3
    ? text.toUpperCase()
    : "Other";
~~~

Nhánh `?` dùng được `text`, vì toàn điều kiện đúng đòi hỏi `instanceof` đúng.

Nhưng **không được** suy ra rằng nhánh `:` cũng dùng được `text`. Toàn điều kiện có thể sai ngay từ phép `instanceof` (ví dụ `value = 123`), hoặc sai sau khi `text.length() > 3` được kiểm tra (ví dụ `value = "Hi"`). Nhánh `:` không bảo đảm `text` đã khớp.

### 6.2. Toán tử ||

Dùng phủ định trước `||`:

~~~java
!(value instanceof String text) || text.isBlank()
~~~

Nếu vế trái đúng, toàn biểu thức đúng ngay và vế phải không chạy; `text` chưa được gắn. Nếu vế trái sai, `instanceof` đã đúng và vế phải được phép đọc `text`.

Với ternary:

~~~java
String answer = !(value instanceof String text) || text.isBlank()
    ? "Invalid"
    : text.trim();
~~~

Nhánh `:` hợp lệ vì **toàn điều kiện sai** có nghĩa là:
- `!(value instanceof String text)` sai, nên `text` chắc chắn được gắn;
- `text.isBlank()` sai, nên có thể xử lý một chuỗi không blank.

So với mã cố ý sai:

~~~java
static boolean invalid(Object value) {
    return value instanceof String text || text.isBlank();
}
~~~

Vế phải của `||` chạy khi `instanceof` **sai**; lúc ấy `text` không tồn tại. Compiler từ chối biểu thức thay vì đợi lỗi runtime.

### 6.3. Bảng quyết định nhanh

| Biểu thức điều kiện `a` | Trạng thái bảo đảm `text` đã khớp | Nhánh ternary dùng `text` |
| --- | --- | --- |
| `value instanceof String text` | `a == true` | `?` |
| `!(value instanceof String text)` | `a == false` | `:` |
| `value instanceof String text && text.length() > 3` | `a == true` | `?` |
| `!(value instanceof String text) || text.isBlank()` | `a == false` | `:` |

Cách diễn giải này dựa trên *definitely matched*, không dựa vào phỏng đoán về một đầu vào cụ thể.

## 7. Ternary không làm biến pattern tiếp tục có phạm vi ngoài biểu thức

Đây là điểm phân biệt conditional expression với cách phân tích luồng ở một số dạng câu lệnh `if`.

Đoạn dưới **cố ý không biên dịch**:

~~~java
static int invalid(Object value) {
    boolean ok = value instanceof String text
        ? !text.isBlank()
        : false;
    return text.length(); // LỖI: text nằm ngoài phạm vi của ? :
}
~~~

Dù `ok == true` chỉ xảy ra với `String` không blank, tên biến `text` **không tồn tại** ở câu lệnh `return`. Compiler không biến một giá trị `boolean` đã tính thành bằng chứng rằng pattern variable trong biểu thức trước vẫn có phạm vi.

Một biến thể khác cũng **cố ý không biên dịch**:

~~~java
static String invalid(Object value) {
    if (value instanceof String text ? !text.isBlank() : false) {
        return text.toUpperCase(); // LỖI: text không ở trong if-body
    }
    return "Other";
}
~~~

Ngay cả khi điều kiện tổng thể của `if` là `true`, cấu trúc `a ? b : c` không **giới thiệu** `text` khi đúng hoặc khi sai theo quy tắc JLS. Vì vậy `if` không nhận được biến này để dùng trong thân câu lệnh.

Nếu cần dùng biến trong `if`, có thể viết đúng và rõ hơn:

~~~java
static String corrected(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.toUpperCase();
    }
    return "Other";
}
~~~

Ở đây `&&` giới thiệu `text` khi điều kiện đúng và `if` cho phép dùng biến ở nhánh đúng.

Nếu chỉ cần trả về giá trị từ toán tử `? :`, hãy dùng biến **ngay trong nhánh phù hợp**:

~~~java
static String correctedWithTernary(Object value) {
    return value instanceof String text
        ? text.toUpperCase()
        : "Other";
}
~~~

Trong cả hai ví dụ sửa, không cần ép kiểu thủ công.

## 8. Conditional expression lồng nhau và thứ tự kết hợp

Toán tử điều kiện `? :` kết hợp **từ phải sang trái**. Ví dụ sau thường được hiểu theo dạng:

~~~java
a ? b : c ? d : e
// tương đương về cách nhóm:
// a ? b : (c ? d : e)
~~~

Nếu pattern được khai báo ở điều kiện của biểu thức **bên ngoài**, bạn có thể dùng nó trong nhánh của biểu thức bên ngoài khi đường đi đảm bảo đã khớp. Biểu thức lồng bên trong không tự động làm biến bị mất phạm vi.

Ví dụ đã được dùng trong chương trình chạy ở phần 5:

~~~java
return !(value instanceof String text)
    ? "Not text"
    : text.isBlank() ? "Blank" : text.trim().toUpperCase();
~~~

Cách đọc rõ ràng hơn khi có nhiều tầng là đặt dấu ngoặc:

~~~java
return !(value instanceof String text)
    ? "Not text"
    : (text.isBlank() ? "Blank" : text.trim().toUpperCase());
~~~

Đây là đoạn nằm trong phương thức có kiểu trả về `String` và tham số `Object value`, không phải một chương trình Java độc lập.

Các mẫu trong ngoặc tròn vẫn giữ quy tắc giới thiệu biến theo true/false. Tuy nhiên, dấu ngoặc chỉ **nhóm phép tính**, không biến nhánh sai thành nhánh đã khớp và không mở rộng phạm vi của biến ra ngoài conditional expression.

Với ternary nhiều tầng, đặc biệt khi có `!`, `&&` và `||` kết hợp, hãy cân nhắc chuyển thành `if/else` để người đọc thấy rõ đường đi và điều kiện khớp. Sự dễ đọc quan trọng hơn việc giảm số dòng.

## 9. Compile-time và runtime giải quyết những câu hỏi khác nhau

Giả sử `value` có kiểu khai báo `Object`. Với điều kiện `value instanceof String text`:

- Compiler biết **khi biểu thức đúng** thì `text` có kiểu `String`. Vì vậy trong nhánh đúng, `text.length()` an toàn về kiểu.
- Compiler không cần biết trước `value` sẽ là `"Java"`, `42` hay `null`.
- Lúc chạy, phép `instanceof` quyết định biểu thức đúng hay sai dựa trên giá trị thực tế.
- `null` làm phép `instanceof String text` sai, nên nhánh sai được chọn và `text` không có giá trị để dùng.
- Tính “chắc chắn đã khớp” là phân tích đường đi của **biểu thức Java**, không phải lời hứa rằng dữ liệu từ bên ngoài luôn đúng kiểu.

Chỉ một trong hai nhánh `?` và `:` của conditional expression được đánh giá ở runtime. Điều này giải thích vì sao dùng biến trong nhánh đã khớp an toàn, nhưng **phạm vi** vẫn do compiler quyết định trước.

Một lỗi khác là nghĩ rằng nếu ternary có kết quả kiểu `String` thì biến pattern tên `text` trở thành kết quả đó. Không phải vậy:

~~~java
String result = value instanceof String text
    ? text
    : "fallback";
~~~

Biến `result` là **biến cục bộ thông thường** chứa kết quả của phép chọn nhánh và có phạm vi theo khai báo của nó. Pattern variable `text` chỉ tồn tại tại các vị trí flow scoping cho phép trong biểu thức, không phải ở tất cả các câu lệnh đọc `result`.

## 10. Những lỗi thường gặp

1. **Dùng biến ở nhánh ngược với trạng thái match.** Với `value instanceof String text`, chỉ nhánh đúng dùng được `text`. Với `!(value instanceof String text)`, nhánh sai mới dùng được.
2. **Dùng biến pattern sau toán tử `? :`.** Cả biểu thức ternary không giới thiệu pattern variable ra phần code tiếp theo, kể cả khi kết quả có kiểu `boolean`.
3. **Cho rằng `||` giống `&&`.** `x instanceof String s && s.length() > 0` hợp lệ; `x instanceof String s || s.length() > 0` không hợp lệ vì vế phải chạy khi mẫu không khớp.
4. **Dùng biến trong nhánh sai của `&&`.** Toàn điều kiện sai có nhiều nguyên nhân; không thể suy ra `instanceof` đã khớp.
5. **Nhầm với phạm vi biến khai báo bình thường.** Phạm vi của pattern variable phụ thuộc luồng, không chỉ phụ thuộc cặp ngoặc nhọn `{}`.
6. **Bỏ qua `null`.** `null` không khớp `instanceof String s`; nếu dùng đúng flow scoping, nhánh khớp mới được truy cập `s`.
7. **Nhồi nhiều ternary lồng nhau.** Những biểu thức có nhiều dấu `? :` rất khó kiểm tra đúng phạm vi và thứ tự đánh giá; chuyển thành `if/else` khi cần thiết.
8. **Đọc một ví dụ không biên dịch như mã chạy được.** Các đoạn được đánh dấu “LỖI” trong bài cố ý minh họa compile-time error; chỉ `ConditionalScopeDemo.java` là chương trình đầy đủ có lệnh chạy và stdout ở phần 5.

## 11. Tự luyện tập và đáp án

### Bài 1 — Dự đoán vị trí dùng được biến

~~~java
String label = value instanceof String s
    ? "length=" + s.length()
    : "not string";
~~~

**Câu hỏi:** Có thể dùng `s` trong nhánh `:` không? Nếu giá trị là `null`, nhánh nào chạy?

**Đáp án:** Không thể dùng `s` trong nhánh `:`. Với `null`, `instanceof` sai nên nhánh `"not string"` được chọn.

### Bài 2 — Đảo điều kiện

~~~java
String label = !(value instanceof String s)
    ? "unknown"
    : s.trim();
~~~

**Câu hỏi:** Vì sao `s.trim()` hợp lệ dù ở nhánh `:`?

**Đáp án:** Toàn điều kiện phủ định sai nghĩa là `value instanceof String s` đúng. Vì vậy `s` chắc chắn đã được gắn.

### Bài 3 — Phát hiện lỗi với ||

~~~java
String label = value instanceof String s || s.length() > 0
    ? "yes"
    : "no";
~~~

**Câu hỏi:** Đoạn trên biên dịch được không? Cách viết nào hợp lý nếu chỉ cần xác nhận giá trị là chuỗi không rỗng?

**Đáp án:** Không biên dịch vì `s` chưa được gắn ở vế phải của `||`. Có thể đổi thành:

~~~java
String label = value instanceof String s && !s.isEmpty()
    ? "yes"
    : "no";
~~~

### Bài 4 — Ternary boolean nằm trong if

~~~java
if (value instanceof String s ? s.length() >= 2 : false) {
    System.out.println(s);
}
~~~

**Câu hỏi:** Vì sao `s` không được dùng trong khối `if`?

**Đáp án:** Biểu thức `? :` không giới thiệu `s` khi toàn biểu thức đúng. Để dùng `s` ở thân `if`, thay điều kiện bằng:

~~~java
if (value instanceof String s && s.length() >= 2) {
    System.out.println(s);
}
~~~

### Bài 5 — Kết quả thực thi

Với phương thức `normalize` trong chương trình chính, hãy tính kết quả cho các đầu vào `null`, `"   "` và `"  Java  "`.

**Đáp án:** Lần lượt là `Not text`, `Blank` và `JAVA`. Phép `instanceof` loại `null` trước khi có bất kỳ lời gọi phương thức `String`; nhánh còn lại xử lý chuỗi đã được kiểm tra kiểu.

## 12. Nguyên tắc ghi nhớ

Trong `a ? b : c`, chỉ dựa vào **đường đi đã chứng minh pattern khớp** để sử dụng biến:

- `a` giới thiệu biến khi **true** ⇒ dùng tại `b`.
- `a` giới thiệu biến khi **false** ⇒ dùng tại `c`.
- **Toàn bộ `a ? b : c` không giới thiệu biến pattern ra ngoài biểu thức.**

Khi gặp code khó, hãy tự hỏi: “Để chạy tới vị trí này, Java đã bắt buộc phải đi qua một lần khớp pattern thành công chưa?” Nếu câu trả lời không chắc chắn, đừng dùng biến ở đó; cấu trúc lại điều kiện cho rõ.

### Tài liệu tham khảo

- Java SE 17 JLS `6.3.1.4 — Conditional Operator `? :`, quy tắc scope của pattern variables: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.4
- Java SE 21 JLS `6.3.1 — Scope for Pattern Variables in Expressions (`&&`, `||`, `!`, `? :`): https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1
- Java SE 21 JLS `15.25 — Conditional Operator: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.25
