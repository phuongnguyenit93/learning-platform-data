# Literal boolean trong Java 17+

## 1. Literal boolean là gì?

**Boolean literal** là giá trị đúng hoặc sai được viết trực tiếp trong mã nguồn Java. Java chỉ có **hai boolean literals**:

- `true`: giá trị logic đúng.
- `false`: giá trị logic sai.

Cả hai có kiểu nguyên thủy **`boolean`**. Chúng phải được viết **chính xác bằng chữ thường**. `True`, `FALSE` hay `TRUE` không phải boolean literals.

~~~java
boolean available = true;
boolean soldOut = false;
~~~

Trong đoạn trên, `boolean` là từ khóa chỉ kiểu; `available` và `soldOut` là các định danh; `true` và `false` là **literal**, không phải từ khóa hoặc tên biến.

Đặc biệt, `true` và `false` không được dùng làm tên định danh:

~~~java
// int true = 1;  // Lỗi biên dịch: true không thể là tên biến
// int false = 0; // Lỗi biên dịch
~~~

**Đừng nhầm literal với chuỗi ký tự:** `"true"` và `"false"` có kiểu `String`, không phải `boolean`.

## 2. Kiểu boolean chỉ có hai giá trị

Một biến kiểu nguyên thủy `boolean` chỉ có thể nhận `true` hoặc `false`, hoặc một biểu thức trả về `boolean`:

~~~java
boolean connected = true;
boolean ready = connected;
boolean adult = 20 >= 18;
boolean eligible = connected && adult;
~~~

Các khai báo sau **không hợp lệ**:

~~~java
// boolean a = 1;       // int không tự chuyển thành boolean
// boolean b = 0;       // int không tự chuyển thành boolean
// boolean c = "true";  // String không tự chuyển thành boolean
// boolean d = null;    // null không gán được cho primitive boolean
~~~

Khác với một số ngôn ngữ khác, Java **không có quy tắc tự xem 0 là false và số khác 0 là true**. Vì vậy:

~~~java
// if (1) { } // Không biên dịch: điều kiện if phải có kiểu boolean
if (true) {
    System.out.println("Nhanh dung");
}
~~~

Đoạn `if (true)` in `Nhanh dung`; `if (false)` có thân hợp lệ nhưng không thực thi thân khi chạy.

## 3. Boolean literals và biểu thức boolean

Literal cung cấp giá trị trực tiếp; còn biểu thức có thể **tính ra** giá trị boolean từ toán hạng khác.

| Biểu thức | Kiểu | Kết quả | Lý do |
|---|---|---|---|
| `true` | `boolean` | `true` | Literal |
| `false` | `boolean` | `false` | Literal |
| `5 > 3` | `boolean` | `true` | So sánh số |
| `10 == 7` | `boolean` | `false` | Hai giá trị khác nhau |
| `!false` | `boolean` | `true` | Phủ định |
| `true && false` | `boolean` | `false` | Phép AND |
| `true \|\| false` | `boolean` | `true` | Phép OR |
| `true ^ true` | `boolean` | `false` | XOR: hai giá trị giống nhau |

Biến cũng có thể giữ kết quả biểu thức:

~~~java
int score = 75;
boolean passed = score >= 50;
boolean excellent = score >= 90;

System.out.println(passed);    // true
System.out.println(excellent); // false
~~~

Không phải mọi giá trị `boolean` đều phải được viết thành literal: một phép so sánh, method như `String.isBlank()` hoặc lời gọi method do bạn viết cũng có thể sinh ra `boolean`.

## 4. Các phép toán logic trên boolean

Ba toán tử dùng thường xuyên nhất:

- `!` (NOT) đảo `true` thành `false` và ngược lại.
- `&&` (AND) chỉ trả `true` nếu **cả hai vế** là `true`.
- `||` (OR) trả `true` nếu **ít nhất một vế** là `true`.

| `a` | `b` | `!a` | `a && b` | `a \|\| b` | `a ^ b` |
|---|---|---|---|---|---|
| false | false | true | false | false | false |
| false | true | true | false | true | true |
| true | false | false | false | true | true |
| true | true | false | true | true | false |

`^` là phép **XOR** trên hai boolean: đúng khi **hai toán hạng khác nhau**.

Khi kết hợp nhiều điều kiện, dùng ngoặc để diễn đạt ý định rõ ràng:

~~~java
boolean authenticated = true;
boolean active = true;
boolean blocked = false;

boolean canEnter = authenticated && active && !blocked;
System.out.println(canEnter); // true
~~~

Tránh những biểu thức quá dài, khó kiểm tra. Đặt tên biến trung gian giúp phần logic sát yêu cầu và dễ đọc hơn.

## 5. `&&` và `||` có tính ngắn mạch

**Short-circuit evaluation** nghĩa là Java bỏ qua vế phải khi vế trái đã đủ quyết định kết quả:

- `false && something()`: không gọi `something()` vì kết quả chắc chắn là `false`.
- `true || something()`: không gọi `something()` vì kết quả chắc chắn là `true`.

Một lợi ích là kiểm tra an toàn trước khi truy cập giá trị có thể null:

~~~java
String name = null;
boolean hasName = name != null && !name.isBlank();
System.out.println(hasName); // false, không ném lỗi
~~~

Sau khi `name != null` là `false`, Java **không đánh giá** `name.isBlank()`.

Trên hai toán hạng boolean, `&` và `|` cũng thực hiện AND/OR, nhưng **đánh giá cả hai vế**, không ngắn mạch. Vì vậy thay `&&` thành `&` trong ví dụ null ở trên có thể gây `NullPointerException`.

### Tự nhìn thấy vế phải bị bỏ qua

~~~java
static boolean trace(String message, boolean result) {
    System.out.println(message);
    return result;
}

// Trong một method:
boolean first = false && trace("RIGHT_1", true);
boolean second = true || trace("RIGHT_2", false);
System.out.println(first);  // false
System.out.println(second); // true
~~~

Hai chuỗi `RIGHT_1` và `RIGHT_2` **không được in** vì các lời gọi `trace` ở vế phải không diễn ra. Điều này quan trọng khi vế phải là lời gọi method tốn tài nguyên hoặc có tác dụng phụ.

**Khuyến nghị:** đừng phụ thuộc vào tác dụng phụ của vế phải `&&`/`||` khi logic cần nó **luôn chạy**. Hãy tách những hành động bắt buộc thành câu lệnh riêng.

## 6. Ví dụ Java 17 chạy được

Tạo tệp **`BooleanLiteralDemo.java`** với toàn bộ nội dung sau:

~~~java
public final class BooleanLiteralDemo {
    private BooleanLiteralDemo() {}

    static final class Settings {
        boolean enabled; // Field primitive có giá trị mặc định false
    }

    static boolean canAccess(
            boolean loggedIn, boolean verified, boolean blocked) {
        return loggedIn && verified && !blocked;
    }

    static boolean hasVisibleText(String text) {
        return text != null && !text.isBlank();
    }

    static boolean trace(String label, boolean value) {
        System.out.println("evaluated: " + label);
        return value;
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean paused = false;

        System.out.println("literal true: " + enabled);
        System.out.println("literal false: " + paused);
        System.out.println("negation: " + !enabled);
        System.out.println("comparison: " + (5 > 3));
        System.out.println("allow: " + canAccess(true, true, false));
        System.out.println("blocked: " + canAccess(true, true, true));

        System.out.println("null valid: " + hasVisibleText(null));
        System.out.println("blank valid: " + hasVisibleText("   "));
        System.out.println("name valid: " + hasVisibleText("Lan"));

        boolean skippedAnd = false && trace("AND right", true);
        boolean skippedOr = true || trace("OR right", false);
        System.out.println("short AND: " + skippedAnd);
        System.out.println("short OR: " + skippedOr);

        System.out.println("parse TRUE: "
                + Boolean.parseBoolean("TRUE"));
        System.out.println("parse yes: "
                + Boolean.parseBoolean("yes"));
        System.out.println("default field: " + new Settings().enabled);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**, từ thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 BooleanLiteralDemo.java
java -cp . BooleanLiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\BooleanLiteralDemo.java
java -cp . BooleanLiteralDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
literal true: true
literal false: false
negation: false
comparison: true
allow: true
blocked: false
null valid: false
blank valid: false
name valid: true
short AND: false
short OR: true
parse TRUE: true
parse yes: false
default field: false
~~~

Hãy chú ý: **không có dòng `evaluated:` nào** vì hai lời gọi `trace` đều nằm trong vế phải được ngắn mạch bỏ qua. Kết quả của `hasVisibleText(null)` cũng an toàn nhờ `&&`.

Đầu ra trên là giá trị dự kiến để người học tự chạy đối chiếu. Không cần Maven, Gradle hoặc thư viện bên ngoài.

## 7. Boolean literal khác String và Boolean wrapper

Ba cách viết này có ý nghĩa khác nhau:

~~~java
boolean primitive = true;
String text = "true";
Boolean wrapper = Boolean.TRUE;
~~~

| Giá trị | Kiểu | Ý nghĩa |
|---|---|---|
| `true` | `boolean` | Boolean literal |
| `"true"` | `String` | Chuỗi bốn ký tự |
| `Boolean.TRUE` | `Boolean` | Hằng field chứa wrapper object |
| `Boolean.parseBoolean("true")` | `boolean` | Kết quả chuyển đổi chuỗi |

Với đầu vào dạng chuỗi, có thể dùng `Boolean.parseBoolean(text)`. Cần nắm rõ hợp đồng của API:

~~~java
System.out.println(Boolean.parseBoolean("true"));  // true
System.out.println(Boolean.parseBoolean("TRUE"));  // true
System.out.println(Boolean.parseBoolean("false")); // false
System.out.println(Boolean.parseBoolean("yes"));   // false
System.out.println(Boolean.parseBoolean(null));    // false
~~~

`parseBoolean` chỉ trả `true` nếu chuỗi biểu diễn `"true"` theo so sánh không phân biệt chữ hoa/thường. Nó **không báo lỗi** khi gặp chuỗi khác, mà trả `false`. Nếu ứng dụng bắt buộc người dùng nhập chính xác `true` hoặc `false`, cần kiểm tra input hợp lệ **trước hoặc ngoài** lời gọi `parseBoolean`.

Lớp wrapper `Boolean` là **kiểu tham chiếu**, nên một biến `Boolean` có thể giữ `null`; primitive `boolean` thì không:

~~~java
Boolean optional = null;
// boolean invalid = null; // Không biên dịch
~~~

Nếu dùng `if (optional)`, Java cố **unbox** `Boolean` sang `boolean`; khi `optional` là `null`, lệnh này ném `NullPointerException`. Nếu chỉ muốn kiểm tra giá trị là true, có thể dùng:

~~~java
Boolean optional = null;
boolean on = Boolean.TRUE.equals(optional); // false
~~~

Không tự xem `null` là “literal boolean thứ ba”: kiểu nguyên thủy `boolean` chỉ có `true` và `false`.

## 8. Giá trị mặc định và biến cục bộ

**Field** kiểu primitive `boolean` được Java khởi tạo mặc định thành `false` khi đối tượng được tạo (hoặc trong quá trình chuẩn bị class đối với static field).

~~~java
class Flags {
    boolean active;
}

Flags flags = new Flags();
System.out.println(flags.active); // false
~~~

Tuy nhiên, **biến cục bộ trong phương thức** phải được gán chắc chắn trước khi đọc:

~~~java
// Trong một method:
// boolean ready;
// System.out.println(ready); // Lỗi biên dịch: có thể chưa khởi tạo
~~~

Vì vậy cần phân biệt:

- Literal `false` là giá trị viết trong source.
- Giá trị mặc định `false` của field là quy tắc khởi tạo của Java.
- Biến cục bộ `boolean` không tự cho phép đọc “false mặc định” khi chưa gán.

## 9. Những lỗi dễ mắc khi dùng boolean literals

| Mã hoặc hành vi | Vấn đề | Cách viết đúng |
|---|---|---|
| `boolean ready = True;` | `True` không phải literal; có thể lỗi tên chưa khai báo | `boolean ready = true;` |
| `boolean ready = 1;` | Java không coi `1` là true | Dùng `true` hoặc điều kiện tạo boolean |
| `if (1) { }` | Điều kiện không có kiểu boolean | `if (count > 0) { }` |
| `boolean ready = "false";` | Chuỗi khác literal boolean | Chuyển đổi/validate input |
| `boolean ready = null;` | Primitive không nhận null | Dùng true/false phù hợp |
| `if (flag = true)` | **Biên dịch được**, nhưng là phép gán, làm điều kiện thành true | `if (flag)` khi muốn kiểm tra giá trị |
| `if (flag == true)` | Thường dư thừa | `if (flag)` |
| `if (flag == false)` | Có thể thay bằng cách đọc dễ hơn | `if (!flag)` |
| `Boolean.parseBoolean("yes")` cho kết quả false | API không hiểu “yes” là true | Validation nếu chỉ chấp nhận true/false |
| `Boolean b = null; if (b)` | NPE lúc unbox | Xử lý null có chủ đích |

### Lỗi nguy hiểm: gán trong điều kiện

~~~java
boolean approved = false;
if (approved = true) {
    System.out.println("APPROVED");
}
System.out.println(approved); // true
~~~

Đoạn này **hợp lệ** vì biểu thức gán `approved = true` có giá trị boolean là `true`; nhưng nó **thay đổi biến** và có thể làm sai logic nghiệp vụ.

Nếu chỉ muốn kiểm tra trạng thái hiện có, viết `if (approved)`. Khi đọc lại code, chú ý phân biệt toán tử gán `=` với so sánh `==`.

## 10. Khi nào nên dùng literal trực tiếp?

Hai literal hữu ích khi chúng diễn tả đúng ý định:

~~~java
boolean featureEnabled = false; // Tạm vô hiệu hóa một tính năng
boolean hasPermission = true;   // Cho phép theo một điều kiện đã kiểm chứng
~~~

Tuy nhiên, không dùng `true` hoặc `false` thay cho những phép kiểm tra bắt buộc:

~~~java
// Sai về nghiệp vụ nếu không kiểm tra thực tế:
boolean authenticated = true;

// Tốt hơn: kết quả từ lời gọi kiểm chứng có nghĩa
// boolean authenticated = verifyCredentials(user, password);
~~~

Đối với method trả boolean, đặt tên thể hiện một câu hỏi rõ ràng:

~~~java
static boolean isAdult(int age) {
    return age >= 18;
}

static boolean isEven(int n) {
    return n % 2 == 0;
}
~~~

Trong biểu thức `return age >= 18;`, không cần viết dạng dài:

~~~java
// Không cần thiết:
if (age >= 18) {
    return true;
} else {
    return false;
}
~~~

Trực tiếp trả biểu thức boolean ngắn hơn và thường rõ ý hơn. Tuy vậy, nếu từng nhánh có lý do nghiệp vụ khác nhau hoặc cần xử lý thêm, `if/else` vẫn có thể phù hợp.

## 11. Bài tập có đáp án

### Bài A — phân loại literal

Cho `true`, `false`, `"true"`, `Boolean.TRUE`, `True`.

**Đáp án:** chỉ `true` và `false` là boolean literals; `"true"` là String literal; `Boolean.TRUE` là field của wrapper class; `True` không phải literal và chỉ hợp lệ nếu có một định danh tương ứng được khai báo.

### Bài B — dự đoán biểu thức

~~~java
boolean a = true;
boolean b = false;
System.out.println(a && b);
System.out.println(a || b);
System.out.println(!a);
System.out.println(a ^ b);
~~~

**Đáp án:**

~~~text
false
true
false
true
~~~

### Bài C — ngắn mạch bảo vệ null

~~~java
String value = null;
boolean ok = value != null && value.length() > 2;
System.out.println(ok);
~~~

**Đáp án:** in `false`, không ném `NullPointerException`, vì vế phải `&&` không được đánh giá. Nếu thay bằng boolean `&`, vế phải bị đánh giá và lời gọi `length()` gây lỗi.

### Bài D — kết quả parseBoolean

Dự đoán `Boolean.parseBoolean("TRUE")`, `Boolean.parseBoolean("1")`, `Boolean.parseBoolean("false")`.

**Đáp án:** lần lượt `true`, `false`, `false`. API không mặc định coi `1` là true.

### Bài E — nhận diện lỗi logic

~~~java
boolean paid = false;
if (paid = true) {
    System.out.println("SHIP");
}
~~~

**Đáp án:** in `SHIP` vì phép gán làm `paid` thành `true`. Nếu muốn chỉ giao hàng khi biến đã true từ trước, sửa thành `if (paid)` (và cần quy trình xác minh thanh toán thật).

## 12. Checklist tự đánh giá

- [ ] Biết chỉ có hai boolean literals trong Java: `true` và `false`.
- [ ] Viết đúng chữ thường và hiểu chúng **không phải từ khóa**.
- [ ] Không nhầm `boolean`, `Boolean`, `"true"` và literal `true`.
- [ ] Hiểu phép so sánh và toán tử logic tạo biểu thức kiểu `boolean`.
- [ ] Dùng `!`, `&&`, `||`, `^` chính xác.
- [ ] Giải thích được vì sao `&&`/`||` không phải lúc nào cũng đánh giá vế phải.
- [ ] Biết `Boolean.parseBoolean` không tự báo lỗi với chuỗi lạ.
- [ ] Biết field boolean mặc định false nhưng local variable phải được gán trước khi đọc.
- [ ] Tránh viết `if (flag = true)` khi muốn kiểm tra giá trị.
- [ ] Biên dịch/chạy `BooleanLiteralDemo.java` trên JDK 17+ và đối chiếu kết quả.

**Kết luận:** `true` và `false` là hai literal kiểu `boolean` dùng để biểu diễn đúng/sai trong mã Java. Kiểu boolean giúp diễn tả điều kiện một cách tường minh; Java không tự đổi số nguyên hoặc chuỗi thành boolean. Khi sử dụng literals trong biểu thức, cần hiểu các toán tử logic, tính ngắn mạch và khác biệt giữa `boolean` primitive với `Boolean` wrapper để tránh lỗi điều kiện và xử lý null sai.