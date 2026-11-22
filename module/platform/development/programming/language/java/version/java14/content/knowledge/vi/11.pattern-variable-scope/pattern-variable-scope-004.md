# Phối hợp với `&&` theo cơ chế đánh giá ngắn mạch — phạm vi biến mẫu trong Java

> **Ngữ cảnh:** Java 14 → *Phạm vi biến mẫu* → **Phối hợp với && theo cơ chế đánh giá ngắn mạch**. Pattern matching cho `instanceof` được giới thiệu dưới dạng preview trong Java 14, nhưng **đã trở thành tính năng chính thức từ Java 16 (JEP 394)**. Nội dung và ví dụ dưới đây sử dụng quy tắc **còn áp dụng trong Java hiện đại**, biên dịch trên Java 17+ mà không cần `--enable-preview`.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích vì sao `obj instanceof String text && text.length() > 3` hợp lệ dù `text` chỉ được khai báo trong phép kiểm tra `instanceof`.
2. Mô tả chính xác thứ tự tính toán và **đánh giá ngắn mạch** (*short-circuit evaluation*) của `&&`.
3. Phân biệt **phạm vi của biến mẫu** (*pattern variable scope*) với phạm vi biến cục bộ thông thường.
4. Sắp xếp điều kiện để tránh kiểm tra kiểu lặp lại, ép kiểu thủ công và truy cập đối tượng khi chưa được bảo đảm về kiểu.
5. Nhận diện lỗi dùng `||`, `&`, đảo thứ tự điều kiện hoặc dùng biến mẫu sau nhánh không chắc đã khớp.
6. Viết chương trình Java 17+ dùng pattern matching có kết quả dự đoán được, không lệ thuộc cú pháp preview của Java 14.

Trọng tâm là **một quan hệ giữa hai quy tắc ngôn ngữ**: `instanceof T t` chỉ gán `t` khi khớp mẫu thành công, còn toán tử `&&` chỉ đánh giá vế phải khi vế trái đúng. Nhờ đó, trình biên dịch biết chắc `t` đã có kiểu và giá trị phù hợp khi sử dụng bên phải.

## 2. Ôn lại hai thành phần trong biểu thức

### 2.1. `instanceof` với biến mẫu

Biểu thức:

~~~java
value instanceof String text
~~~

là **biểu thức Java** đặt trong phương thức, với `value` là biến có kiểu tham chiếu phù hợp, ví dụ `Object value`.

- Nó trả `true` khi giá trị runtime là một `String` có thể khớp mẫu.
- Đồng thời, biến mẫu `text` được gán chính tham chiếu đã kiểm tra, có kiểu tĩnh `String`.
- Nó trả `false` nếu `value == null` hoặc đối tượng không khớp `String`; **không phải** một phép ép kiểu làm phát sinh `ClassCastException`.
- Khi trả `false`, không thể coi `text` là biến đã được gán. Java áp dụng quy tắc *flow scoping* để tránh cho phép đọc biến mẫu ở vị trí không bảo đảm khớp.

So sánh cách viết tách rời trước đây (vẫn là cú pháp Java hợp lệ, chỉ dài dòng):

~~~java
if (value instanceof String) {
    String text = (String) value;
    if (text.length() > 3) {
        System.out.println(text);
    }
}
~~~

với cách viết gọn, hiện đại:

~~~java
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}
~~~

Hai đoạn trên là **minh họa đặt trong phương thức**, không phải file Java độc lập. Ở phiên bản thứ hai, compiler biết `text` là `String` trên vế phải `&&` và trong thân `if` khi toàn bộ điều kiện đúng. Không cần ép kiểu lần hai.

### 2.2. `&&` là conditional AND và đánh giá ngắn mạch

Xét `A && B`:

1. Java **đánh giá `A` trước**.
2. Nếu `A` trả `false`, **không đánh giá `B`**, kết quả chung là `false`.
3. Chỉ khi `A` là `true`, Java mới đánh giá `B`; lúc đó kết quả chung bằng kết quả của `B`.

| `A` | `B` có được chạy? | Kết quả `A && B` |
| --- | --- | --- |
| `false` | Không | `false` |
| `true` | Có, trả `false` | `false` |
| `true` | Có, trả `true` | `true` |

Toán tử `&&` kết hợp từ trái qua phải, các toán hạng được tính **theo thứ tự trái đến phải**. Với `A && B && C`, nếu `A` sai thì cả `B`/`C` đều bị bỏ qua; nếu `A` đúng nhưng `B` sai thì `C` bị bỏ qua.

**Đánh giá ngắn mạch là cơ chế runtime.** Còn việc `text` được phép dùng ở đâu là quy tắc **compile-time**. Hai quy tắc phối hợp với nhau, nhưng không phải cùng một khái niệm.

## 3. Vì sao biến mẫu hợp lệ ở bên phải `&&`?

Xét đoạn:

~~~java
Object value = "Java";

if (value instanceof String text && text.length() > 3) {
    System.out.println(text.toUpperCase());
}
~~~

Đây là đoạn code đặt trong phương thức. Trình biên dịch suy luận theo logic:

1. Kiểm tra `value instanceof String text`. Khi phép kiểm tra **đúng**, `text` chắc chắn được gán một `String`, không phải `null`.
2. Theo `&&`, vế phải `text.length() > 3` **chỉ được thực thi khi phép kiểm tra trên đúng**. Vì vậy, dùng `text.length()` tại đây hợp lệ.
3. Khi toàn bộ điều kiện `if` trả `true`, cả phép khớp và phép kiểm tra độ dài đều đúng, nên `text` cũng được dùng trong **thân `if`**.
4. Nếu phép khớp thất bại, vế phải không chạy và thân `if` cũng không chạy, nên không có truy cập sai kiểu hoặc null.

Khái niệm hình thức của Java Language Specification (JLS) là: **một pattern variable được giới thiệu khi biểu thức bên trái `&&` là đúng thì biến ấy được xem là đã khớp chắc chắn tại biểu thức bên phải** (`definitely matched at the right-hand operand`). Đây là *flow scoping*, không phải quy tắc “biến khai báo trong ngoặc luôn có phạm vi toàn bộ ngoặc”.

### 3.1. Đọc điều kiện theo luồng

~~~text
value instanceof String text
            |
          true  ───────────────► text.length() > 3
            |                            |
          false                         true
            |                            |
        bỏ qua RHS                   chạy thân if
            |                            |
        bỏ qua thân if          text là String hợp lệ
~~~

Nếu một `String` ngắn như `"Hi"`, phép kiểm tra kiểu đã đúng nên `text.length() > 3` **vẫn chạy**, nhưng nó trả `false`; thân `if` không chạy. Nếu `value` là số `42` hoặc `null`, phép kiểm tra kiểu sai nên `length()` **không được gọi**.

### 3.2. Có thể viết nhiều điều kiện liên tiếp

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 4
        && text.startsWith("J")) {
    System.out.println("Accepted: " + text);
}
~~~

Đoạn trên cũng đặt trong phương thức. Sau khi `instanceof` thành công, biến `text` có phạm vi thích hợp cho **tất cả** những điều kiện phía sau trong chuỗi `&&`. Nếu `isBlank()` đúng, điều kiện `!text.isBlank()` sai và hai phép kiểm tra còn lại bị bỏ qua.

Không cần viết `value != null` trước `value instanceof String text` chỉ để tránh null: toán tử `instanceof` đã trả `false` với giá trị null. Nếu có một yêu cầu **riêng** về null (ví dụ báo lỗi cụ thể), hãy xử lý tường minh theo hợp đồng API.

## 4. Ví dụ chạy được: quan sát đánh giá ngắn mạch

Lưu toàn bộ mã sau trong **`PatternAndDemo.java`**:

~~~java
public class PatternAndDemo {
    private static int checks = 0;

    private static boolean longEnough(String text) {
        checks++;
        return text.length() > 3;
    }

    private static String inspect(Object value) {
        if (value instanceof String text
                && longEnough(text)
                && text.startsWith("J")) {
            return "MATCH:" + text;
        }
        return "NO_MATCH";
    }

    public static void main(String[] args) {
        Object[] samples = {null, 42, "Hi", "Java", "Kotlin"};

        for (Object sample : samples) {
            int before = checks;
            System.out.println(
                    inspect(sample)
                    + "|checked=" + (checks - before));
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 PatternAndDemo.java
java PatternAndDemo
~~~

**Stdout chính xác:**

~~~text
NO_MATCH|checked=0
NO_MATCH|checked=0
NO_MATCH|checked=1
MATCH:Java|checked=1
NO_MATCH|checked=1
~~~

Giải thích từng phần tử:

| Giá trị truyền vào | `instanceof String text` | `longEnough(text)` được gọi? | Kết quả |
| --- | --- | --- | --- |
| `null` | `false` | Không, bộ đếm tăng 0 | `NO_MATCH|checked=0` |
| `42` (`Integer`) | `false` | Không, bộ đếm tăng 0 | `NO_MATCH|checked=0` |
| `"Hi"` | `true` | Có, trả `false` | `NO_MATCH|checked=1` |
| `"Java"` | `true` | Có, trả `true`; `startsWith` đúng | `MATCH:Java|checked=1` |
| `"Kotlin"` | `true` | Có, trả `true`; `startsWith` sai | `NO_MATCH|checked=1` |

Biến tĩnh `checks` được dùng **chỉ để quan sát** vế phải có chạy hay không. Trong mã ứng dụng, nên ưu tiên các phép kiểm tra **không có tác dụng phụ**, để luồng điều kiện dễ đọc, dễ kiểm thử; không dựa vào việc một hàm có tác dụng phụ sẽ “chắc chắn được gọi” trong một chuỗi `&&`.

### Một lưu ý về lỗi từ biểu thức bên phải

`&&` **không nuốt ngoại lệ**. Nếu vế trái đúng và vế phải ném ngoại lệ thì ngoại lệ vẫn lan ra bình thường. Ví dụ:

~~~java
if (value instanceof String text && text.charAt(5) == 'a') {
    // Có thể ném StringIndexOutOfBoundsException
}
~~~

Đoạn minh họa này có thể ném `StringIndexOutOfBoundsException` nếu `text` là chuỗi quá ngắn. Hãy đặt điều kiện miền chỉ số trước:

~~~java
if (value instanceof String text
        && text.length() > 5
        && text.charAt(5) == 'a') {
    // Chỉ truy cập charAt(5) khi chỉ số 5 hợp lệ.
}
~~~

Pattern matching chỉ bảo đảm **kiểu và điều kiện khớp mẫu**, không tự chứng minh mọi bất biến khác như độ dài chuỗi, miền số, quyền truy cập dữ liệu hay kết quả I/O.

## 5. Biến mẫu có phạm vi ở đâu sau khi dùng `&&`?

### 5.1. Trong thân `if` khi điều kiện đúng

~~~java
Object input = "Java";

if (input instanceof String text && text.length() > 3) {
    System.out.println(text); // Hợp lệ
}
~~~

Trong nhánh `then`, toàn bộ điều kiện đúng ⇒ phép khớp mẫu chắc chắn thành công ⇒ `text` được dùng hợp lệ. Tên biến này là một **biến mẫu có scope theo luồng**, không phải một field hay biến toàn cục.

### 5.2. Không giả định rằng biến dùng được khi điều kiện sai

~~~java
Object input = "Hi";

if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
} else {
    // System.out.println(text); // LỖI BIÊN DỊCH
}
~~~

Nhánh `else` xảy ra vì **ít nhất một** điều kiện sai: có thể input không phải `String`, hoặc input là `String` nhưng độ dài ≤ 3. Trình biên dịch không được phép giả định biến `text` đã được gán khi rơi vào `else`.

Cũng không thể lấy tên biến ra dùng tự do sau khối `if`:

~~~java
Object input = "Java";
boolean accepted =
        input instanceof String text && text.length() > 3;

// System.out.println(text); // LỖI BIÊN DỊCH
~~~

Biểu thức boolean đã được tính, nhưng trong câu lệnh tiếp theo không có đảm bảo nào rằng `accepted` là true. Nếu muốn sử dụng giá trị đã kiểm tra, hãy dùng nó bên trong nhánh chắc chắn khớp hoặc **tách thành guard clause**.

### 5.3. Guard clause và phạm vi sau nhánh thoát sớm

Có thể đảo phép kiểm tra để rời khỏi phương thức khi không khớp:

~~~java
static String describe(Object value) {
    if (!(value instanceof String text)) {
        return "NOT_STRING";
    }

    // Đi đến đây nghĩa là instanceof chắc chắn đã đúng.
    if (text.isBlank()) {
        return "BLANK";
    }
    return "TEXT:" + text.strip();
}
~~~

Đây là **một phương thức đặt trong lớp**. Vì nhánh thất bại đã `return`, compiler biết mọi đường đi đến các dòng tiếp theo đều có `value instanceof String text` thành công. Vậy `text` hợp lệ **sau** guard. Điều này minh họa rõ vì sao Java dùng phân tích luồng thay vì đóng khung scope theo cặp dấu ngoặc một cách máy móc.

## 6. Phân biệt `&&` với `||` và `&`

### 6.1. `||` không đảm bảo điều kiện khớp mẫu ở vế phải

Đoạn sau **cố ý không biên dịch**:

~~~java
Object value = "Java";

boolean accepted =
        value instanceof String text || text.length() > 3;
~~~

Với `A || B`, vế phải `B` chỉ chạy khi `A` **sai**. Nếu `A` là `value instanceof String text` thì tại thời điểm `B` chạy, phép khớp mẫu **chưa thành công**; không thể dùng `text` ở đây. Compiler báo lỗi không tìm thấy biến/biến không ở trong phạm vi hợp lệ. Không dùng `||` chỉ vì muốn “nối thêm điều kiện cho chuỗi” khi điều kiện sau phụ thuộc biến mẫu được gán khi đúng.

Tuy nhiên, trường hợp **phủ định** sau đây là hợp lệ:

~~~java
static boolean absentOrBlank(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
~~~

Đây là phương thức minh họa. Nếu vế trái `!(value instanceof String text)` là `false`, nghĩa là phép khớp đã **thành công**, nên vế phải `text.isBlank()` có thể dùng `text`. Nếu value là null/khác `String` thì vế trái true và vế phải được bỏ qua. Việc này cũng được giải thích bởi flow scoping và short-circuit, nhưng ở một điều kiện **phủ định**.

### 6.2. `&` với boolean không có short-circuit

Đoạn sau **cố ý không biên dịch**:

~~~java
Object value = "Java";

boolean accepted =
        value instanceof String text & text.length() > 3;
~~~

Toán tử `&` áp dụng trên boolean sẽ **đánh giá cả hai vế**, kể cả khi vế trái false. Vì không có bảo đảm vế trái khớp mẫu trước khi thực thi vế phải, `text` **không thuộc scope hợp lệ** ở vế phải như trường hợp `&&`. Với ví dụ này, cách làm đúng là dùng `&&`.

Bảng phân biệt:

| Toán tử | Khi vế trái false | Khi vế trái true | Dùng biến mẫu từ `instanceof T t` ở vế phải? |
| --- | --- | --- | --- |
| `&&` | Bỏ qua vế phải | Đánh giá vế phải | **Có**, vì vế phải chỉ chạy khi mẫu khớp |
| `||` | Đánh giá vế phải | Bỏ qua vế phải | **Không** với mẫu khớp **dương** ở vế trái |
| `&` (boolean) | Vẫn đánh giá vế phải | Vẫn đánh giá vế phải | **Không** theo quy tắc chắc chắn khớp này |
| `|` (boolean) | Vẫn đánh giá vế phải | Vẫn đánh giá vế phải | **Không** theo quy tắc chắc chắn khớp này |

`&` và `|` vẫn có vai trò hợp lệ với bitwise operations hoặc bài toán cần tính cả hai boolean operands. Chúng chỉ **không thay thế `&&`/`||`** khi ý định là bỏ qua điều kiện phía sau và dùng pattern variable an toàn.

### 6.3. Thứ tự điều kiện không được tùy tiện đảo

~~~java
// LỖI: text chưa có scope ở vế trái.
if (text.length() > 3 && value instanceof String text) {
    // ...
}
~~~

Cú pháp `&&` đọc từ trái qua phải: phải **kiểm tra mẫu trước**, sau đó mới dùng biến đã khớp.

~~~java
// ĐÚNG:
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}
~~~

Đây là yêu cầu của **luồng dữ liệu**, không phải quy ước phong cách tùy chọn. Những toán hạng độc lập đôi khi đổi thứ tự được, nhưng các toán hạng có phụ thuộc biến mẫu thì cần thứ tự đáp ứng definite match.

### 6.4. Kết hợp dấu ngoặc và độ ưu tiên

`&&` có độ ưu tiên **cao hơn** `||`. Nếu muốn dùng biến `text` ở nhiều nhánh kiểm tra thay thế, hãy đặt các phép kiểm tra đó **bên trong vế phải của `&&`**:

~~~java
if (value instanceof String text
        && (text.startsWith("J") || text.startsWith("K"))) {
    System.out.println(text);
}
~~~

Cả hai phép `startsWith` nằm trong phần chỉ chạy khi pattern match đã đúng, nên scope hợp lệ. Đừng viết thiếu ngoặc rồi giả định rằng một nhánh `||` bất kỳ cũng được bảo vệ bằng `instanceof`.

## 7. Chương trình hoàn chỉnh thứ hai: guard clause và biến thể logic

Lưu mã trong **`PatternScopeDemo.java`**:

~~~java
public class PatternScopeDemo {
    static String decide(Object value) {
        if (!(value instanceof String text)) {
            return "NOT_STRING";
        }

        if (text.isBlank()) {
            return "BLANK";
        }
        return "TEXT:" + text.strip();
    }

    static boolean nonBlank(Object value) {
        return value instanceof String text && !text.isBlank();
    }

    static boolean negativeForm(Object value) {
        return !(value instanceof String text) || text.isBlank();
    }

    public static void main(String[] args) {
        System.out.println(decide(42));
        System.out.println(decide("   "));
        System.out.println(decide(" Java "));
        System.out.println(nonBlank("Java"));
        System.out.println(nonBlank(null));
        System.out.println(negativeForm(null));
        System.out.println(negativeForm("ok"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PatternScopeDemo.java
java PatternScopeDemo
~~~

**Stdout chính xác:**

~~~text
NOT_STRING
BLANK
TEXT:Java
true
false
true
false
~~~

Giải thích:

- `decide(42)` trả ngay `NOT_STRING`, không chạm vào `text`.
- `decide("   ")` đã khớp `String`; `text.isBlank()` true nên trả `BLANK`.
- `decide(" Java ")` dùng `text.strip()` sau guard; trả `TEXT:Java`.
- `nonBlank("Java")` là true; `nonBlank(null)` false và **không gọi `isBlank()`**.
- `negativeForm(null)` true vì phép khớp thất bại và phủ định thành true; `negativeForm("ok")` false vì phép khớp đúng và `isBlank()` false.

Ở đây, `nonBlank` và `negativeForm` không mang cùng ý nghĩa khi đầu vào không phải String: hàm đầu yêu cầu có String và không blank, hàm sau hỏi “không phải String **hoặc** là String blank”. Chọn biểu thức đúng **ý định nghiệp vụ**, không chỉ biểu thức biên dịch được.

## 8. Dùng `&&` với những mẫu kiểu khác

Pattern matching cho `instanceof` không chỉ dành cho `String`. Có thể kiểm tra interface, class hoặc kiểu tham chiếu thích hợp khác. Ví dụ **đoạn đặt trong phương thức**:

~~~java
if (value instanceof java.util.List<?> items
        && !items.isEmpty()) {
    System.out.println(items.size());
}
~~~

`items` có kiểu `List<?>`, và biểu thức `items.isEmpty()` chỉ chạy khi value là một List. Dùng `List<?>` trong `instanceof` vì kiểu tham số generic cụ thể như `List<String>` **không phải kiểu reifiable dùng trực tiếp cho kiểm tra này** trong trường hợp thông thường. Việc List không rỗng **không chứng minh** phần tử có loại hoặc nội dung nào; cần validate thêm nếu nghiệp vụ yêu cầu.

Một ví dụ về giao diện:

~~~java
if (value instanceof CharSequence sequence
        && sequence.length() > 0) {
    System.out.println(sequence.charAt(0));
}
~~~

Ở đây `sequence` có API của `CharSequence` (không mặc định có mọi phương thức riêng của `String`). Nếu cần `strip()`, phải khớp kiểu `String`, chuyển đổi dữ liệu, hoặc dùng cách phù hợp với giao diện. Luôn sử dụng phương thức đúng **kiểu tĩnh của biến mẫu**.

## 9. Những sai lầm thường gặp

| Sai sót | Điều xảy ra | Cách viết đúng |
| --- | --- | --- |
| Dùng `text.length()` trước `value instanceof String text` | Không có scope/không bảo đảm gán | Kiểm tra `instanceof` trước trong `&&` |
| Dùng `value instanceof String text || text.isBlank()` | Vế phải chỉ chạy khi mẫu **không** khớp | Dùng `&&` nếu muốn kiểm tra thêm sau khi khớp |
| Thay `&&` bằng `&` | Vế phải không còn được bỏ qua khi vế trái false; biến mẫu không đủ scope | Dùng `&&` |
| Truy cập `text` trong `else` của điều kiện `instanceof && thêm_guard` | Nhánh false có thể do mismatch hoặc guard false | Tổ chức lại nhánh hoặc dùng guard clause |
| Dùng `text` sau một phép gán boolean `ok = instanceof && ...` | Phạm vi sau câu lệnh không chứng minh mẫu đã khớp | Đặt thao tác trong thân `if` hoặc guard clause |
| Kiểm tra `charAt(5)` ngay sau `instanceof` | String đúng kiểu nhưng có thể ngắn | Đặt `length() > 5` trước `charAt(5)` |
| Giả định `&&` bắt/nuốt exception | RHS vẫn có thể ném lỗi nếu LHS đúng | Xử lý lỗi theo API, giới hạn phạm vi guard |
| Giả định `instanceof` ném NPE với null | `instanceof` trên null trả `false` | Không cần null check riêng để bảo vệ `instanceof` |
| Dùng pattern `List<String>` trên một `Object` tùy ý | Generic type argument không kiểm tra được bằng `instanceof` kiểu đó | Dùng `List<?>` và validate phần tử riêng |
| Nhầm Java 14 preview với yêu cầu của Java hiện đại | Dễ dùng lệnh biên dịch preview lỗi thời | Dùng JDK 17+, `--release 17`, không cần `--enable-preview` |

### Đọc lỗi của compiler

Khi biên dịch đoạn sai như:

~~~java
Object value = 42;
boolean result = value instanceof String text || text.length() > 3;
~~~

compiler sẽ phàn nàn về tên `text` không thể được phân giải ở vế phải vì không có scope hợp lệ tại đó. Hãy sửa **điều kiện logic và đường đi bảo đảm khớp**, thay vì cố gán null hoặc ép kiểu để che lỗi biên dịch. Để compiler kiểm tra flow scoping là một ưu điểm của Java hiện đại.

## 10. Checklist để viết điều kiện rõ ràng, an toàn

- [ ] Mẫu được kiểm tra **trước lần sử dụng** biến mẫu trong một chuỗi `&&`.
- [ ] Các điều kiện sau có thực sự **phụ thuộc** vào kết quả khớp trước không?
- [ ] Nếu input là `null` hoặc khác kiểu, vế phải có được bỏ qua như mong muốn không?
- [ ] Mọi thao tác trên biến mẫu dùng API phù hợp kiểu tĩnh (`String`, `List<?>`, `CharSequence`...).
- [ ] Các phép kiểm tra giới hạn, chỉ số hoặc bất biến cần thiết được đặt trước truy cập có thể lỗi.
- [ ] Thân `if` và các đoạn sau guard clause chỉ dùng biến ở chỗ **definitely matched**.
- [ ] Không dùng nhầm `||`, `&`, `|` hoặc đảo thứ tự làm mất cơ chế ngắn mạch.
- [ ] Không lạm dụng side effects trong điều kiện; các phép thử ưu tiên ngắn gọn, dễ đọc và có tên rõ ràng.
- [ ] Bài toán có thể giải thích được ngay cả khi nhánh bị bỏ qua và không gọi một số hàm.
- [ ] Mã được biên dịch trên Java 17+ ổn định, không dựa vào preview của Java 14.

## 11. Bài tập tự luyện

1. Với ba giá trị `null`, `"A"` và `"Java"`, cho biết khi nào `text.length() > 3` chạy trong `value instanceof String text && text.length() > 3`; giải thích từng đường đi.
2. Viết hàm `isNonEmptyString(Object)` chỉ trả true cho `String` không blank, bằng một dòng `instanceof ... && ...`. Thử `String` rỗng, whitespace, `Integer` và `null`.
3. Viết chuỗi `&&` để kiểm tra một `String` dài ít nhất 6 ký tự trước khi gọi `charAt(5)`. Thử đầu vào ngắn để thấy chương trình không ném `StringIndexOutOfBoundsException`.
4. Thử thay `&&` bằng `&` và quan sát lỗi biên dịch khi dùng biến mẫu ở RHS. Sau đó viết hai boolean method độc lập để quan sát `&` gọi vế phải kể cả khi trái sai.
5. Viết điều kiện **cố ý sai** dùng `instanceof String text || text.isBlank()`. Giải thích vì sao compiler chặn nó; sửa bằng `&&` nếu mục tiêu là String không blank.
6. Đặt `if (!(input instanceof String text)) return;` trong phương thức, sau đó dùng `text.strip()`. Nêu vì sao `text` được phép dùng sau guard, còn `else` của một điều kiện `instanceof && guard` chưa đủ.
7. Viết biểu thức kết hợp hai prefix `"J"` và `"K"`: `value instanceof String text && (text.startsWith("J") || text.startsWith("K"))`. Thử bỏ dấu ngoặc và giải thích rủi ro về thứ tự/logic.
8. Viết hàm nhận `Object`, kiểm tra `List<?> items && !items.isEmpty()`, rồi trả kích thước. Giải thích vì sao không thể kết luận mọi phần tử đều có kiểu `String`.
9. Dự đoán stdout của `PatternAndDemo` mà không chạy máy. So sánh số lần gọi `longEnough`; tự thêm một điều kiện vào cuối chuỗi `&&` và xem khi nào nó bị bỏ qua.

## 12. Tài liệu chuẩn để đối chiếu

- [JLS `6.3.1.1 — Conditional-And Operator && (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1.1): khi biểu thức trái giới thiệu biến mẫu **nếu đúng**, biến chắc chắn khớp ở biểu thức phải.
- [JLS `15.23 — Conditional-And Operator && (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.23): đánh giá toán hạng theo thứ tự và ngắn mạch.
- [JLS `6.3.2.2 — if Statements (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.2.2): scope biến mẫu theo nhánh câu lệnh.
- [Oracle: Java Language Changes, Java SE 16](https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html): pattern matching cho `instanceof` trở thành tính năng chính thức trong Java 16 (JEP 394).
- [OpenJDK JEP 394](https://openjdk.org/jeps/394): nền tảng thiết kế `instanceof` pattern matching và flow scoping.

**Kết luận kiến thức:** `value instanceof String text && text.length() > 3` đúng vì Java bảo đảm **khớp kiểu trước, dùng biến sau**. Khi phép khớp sai, `&&` bỏ qua RHS; khi toàn bộ điều kiện đúng, `text` có scope trong thân `if`. Đó là lý do cú pháp này vừa ngắn, vừa loại bỏ cast lặp, vừa được compiler kiểm tra an toàn trong Java hiện đại.