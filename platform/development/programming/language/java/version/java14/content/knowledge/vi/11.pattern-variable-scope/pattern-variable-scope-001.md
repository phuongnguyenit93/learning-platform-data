# Phạm vi biến mẫu phụ thuộc kết quả của điều kiện (`instanceof` pattern matching)

## 1. Khái niệm: biến mẫu chỉ tồn tại ở luồng đã khớp

Trong Java hiện đại, `instanceof` có thể đồng thời **kiểm tra kiểu** và **khai báo một biến mẫu** (*pattern variable*), tránh viết ép kiểu lặp lại:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Đây là đoạn đặt trong một phương thức, không phải chương trình độc lập. Biểu thức `value instanceof String text` có hai vai trò:

1. Xác định `value` có tương thích với mẫu `String` hay không.
2. Khi khớp, liên kết giá trị với biến `text` có kiểu tĩnh `String`.

Điểm quan trọng nhất: **biến `text` không có phạm vi đơn giản là “từ vị trí khai báo đến hết khối”**. Phạm vi của nó được Java xác định bằng **flow scoping**: tại điểm sử dụng, trình biên dịch phải biết rằng mẫu đã khớp trên mọi đường thực thi dẫn tới điểm đó. Tính khả dụng của biến vì vậy **phụ thuộc vào kết quả đúng/sai của điều kiện và đường đi của chương trình**.

Trong chương trình có `if`, `&&`, `||`, `!`, nhánh `else` hoặc `return` sớm, khác biệt này đặc biệt quan trọng.

**Phiên bản:** Pattern matching cho `instanceof` được giới thiệu thử nghiệm ở Java 14 và chính thức từ **Java 16** (JEP 394). Bài này dùng cú pháp chuẩn tương thích JDK **17+**, không dùng preview/legacy. Không nhầm phạm vi của pattern `instanceof` với cú pháp pattern trong `switch` ở các phiên bản mới hơn; trọng tâm ở đây là **kết quả điều kiện**.

## 2. Quy tắc cốt lõi: “definitely matched”

Java phân tích xem biến mẫu có được xác định chắc chắn là đã khớp (*definitely matched*) khi một biểu thức Boolean có kết quả **`true`** hoặc **`false`**. Nếu đang ở đường chạy mà một mẫu chưa chắc khớp, mã không được tham chiếu tới biến mẫu đó.

Xét điều kiện cơ bản:

```java
Object obj = "hello";

if (obj instanceof String s) {
    System.out.println(s.toUpperCase()); // Hợp lệ
} else {
    // Không được dùng s ở đây.
}

// Không được mặc định dùng s ở đây.
```

Đây là đoạn minh họa đặt trong phương thức. Nếu điều kiện **đúng**, `obj` là `String` nên `s` tồn tại trong nhánh `then`. Nếu điều kiện **sai**, Java không có bằng chứng để xem `s` là một `String` đã khớp. Sau toàn bộ `if`, cả đường đúng lẫn đường sai có thể đến đó, nên `s` không mặc nhiên khả dụng.

Có thể hiểu khái quát:

- `obj instanceof String s` **đúng** ⇒ `s` đã khớp và dùng được tại những vị trí thuộc luồng đó.
- `obj instanceof String s` **sai** ⇒ `s` chưa được liên kết với một giá trị khớp.
- Một điểm nối nhiều đường chạy chỉ dùng được `s` khi **mọi đường có thể tới đó** đều bảo đảm mẫu đã khớp.

**Phạm vi không phải là kiểm tra ở runtime rồi “hy vọng biến tồn tại”.** Đây là quy tắc kiểm tra tại **thời điểm biên dịch**. Mã vi phạm sẽ không biên dịch, kể cả khi lập trình viên biết dữ liệu thử nghiệm luôn là chuỗi.

## 3. Toán tử `&&`: vế phải chỉ chạy khi vế trái đúng

`&&` đánh giá ngắn mạch (*short-circuit*): vế phải chỉ được đánh giá nếu vế trái trả `true`. Vì vậy, sau khi `instanceof` khớp ở vế trái, biến mẫu có thể được dùng ở vế phải:

```java
Object input = "Java";

if (input instanceof String s && s.length() >= 4) {
    System.out.println(s.toUpperCase()); // JAVA
}
```

Giải thích theo luồng:

1. `input instanceof String s` trả `true` ⇒ Java biết `s` là `String` và có thể đánh giá `s.length()`.
2. Nếu điều kiện trái trả `false`, toàn bộ `&&` trả `false`, **không đánh giá vế phải**. Do đó không hề gọi phương thức trên một `s` chưa khớp.
3. Nếu toàn bộ điều kiện `&&` là `true`, `s` có thể được dùng trong nhánh `then`.

Có thể nối thêm nhiều điều kiện, miễn các điều kiện sau chỉ được kiểm tra khi mẫu đã khớp:

```java
if (input instanceof String s
        && !s.isBlank()
        && s.startsWith("J")) {
    System.out.println(s); // Chỉ vào đây khi tất cả điều kiện đúng.
}
```

**Không nhầm:** `s` không được tự động đưa vào scope của nhánh `else` của điều kiện `&&` trên. Toàn biểu thức có thể sai vì `input` không phải `String`, hoặc vì chuỗi không đạt điều kiện phụ. Trong hai đường chạy này, chỉ một đường có `s` đã khớp, nên ở nhánh `else` không thể khẳng định điều đó.

## 4. Toán tử `||`: vì sao dùng trực tiếp biến mẫu thường sai?

`||` cũng ngắn mạch, nhưng vế phải chỉ chạy khi vế trái **sai**. Nếu vế trái là `obj instanceof String s`, khi vế phải được đánh giá thì `s` **chưa** khớp. Vì vậy mã sau **cố ý sai**:

```java
Object value = "Java";
boolean fallback = false;

// Sai: khi phải tính vế sau ||, mẫu String chưa khớp.
if (value instanceof String s || s.isEmpty()) {
    System.out.println("OK");
}
```

Lỗi nằm ở `s.isEmpty()`: vế phải của `||` không có bảo đảm `s` tồn tại.

Ngay cả khi không dùng `s` trong vế phải, nhánh `then` của một biểu thức `||` cũng **không bảo đảm mẫu đã khớp**:

```java
Object value = 123;
boolean fallback = true;

// Câu if sau tự nó hợp lệ.
if (value instanceof String s || fallback) {
    // System.out.println(s.length()); // Sai: s không chắc đã khớp.
    System.out.println("Điều kiện chung đúng");
}
```

Ở đây `value` không phải `String`, nhưng `fallback` là `true`, nên khối `if` vẫn chạy. Do đó không thể sử dụng `s` trong khối ấy.

**Quy tắc thực hành:** nếu cần dùng biến mẫu để lọc thêm điều kiện, phần lớn trường hợp dùng `instanceof ... && predicate` thay vì `instanceof ... || predicate`. Với `||`, hãy xem kỹ điều kiện phủ định ở mục tiếp theo.

## 5. Phủ định `!` đảo đường đúng/sai mà biến được bảo đảm

Toán tử `!` đổi kết quả Boolean. Nếu `obj instanceof String s` khớp khi **đúng**, thì `!(obj instanceof String s)` là **sai** chính khi `s` đã khớp.

Xét một guard clause:

```java
static String upperIfString(Object obj) {
    if (!(obj instanceof String s)) {
        return "not a string";
    }
    return s.toUpperCase();
}
```

Đây là **phương thức đầy đủ**, có thể đặt trong lớp Java. Nếu điều kiện phủ định **đúng**, phương thức kết thúc ngay với `return`. Vì thế mọi đường chạy còn có thể đến dòng `return s.toUpperCase();` đều đã đi qua trường hợp `obj instanceof String s` khớp. Trình biên dịch cho phép sử dụng `s` **sau `if`**.

Nhưng điều này **không** có nghĩa mọi trường hợp `if (!(obj instanceof String s))` đều tạo scope sau `if`. Ví dụ, nếu nhánh `then` có thể tiếp tục bình thường thay vì `return`/`throw`, sau `if` vẫn có đường chạy không khớp mẫu và `s` không chắc khả dụng.

Ví dụ nhánh sai dừng bằng ngoại lệ:

```java
static int lengthRequired(Object value) {
    if (!(value instanceof String s)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return s.length(); // Hợp lệ.
}
```

`return` hoặc `throw` là hai ví dụ của **abrupt completion**: đường không khớp không đi tiếp tới điểm sử dụng biến.

### Khi nhánh `else` là đường đã khớp

```java
if (!(obj instanceof String s)) {
    System.out.println("Không phải String");
} else {
    System.out.println(s.length()); // Hợp lệ.
}
```

Ở nhánh `else`, điều kiện `!(obj instanceof String s)` đã là `false`; tương đương `obj instanceof String s` là `true`. Phạm vi của `s` gắn với **đường kết quả sai của biểu thức phủ định**, chứ không gắn cứng với vị trí của chữ `if`.

## 6. Kết hợp `!` và `||`: guard có nhiều điều kiện

Một mẫu thường gặp là kiểm tra "không phải chuỗi, **hoặc** chuỗi chỉ có khoảng trắng" rồi trả về sớm:

```java
static int nonBlankLength(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return 0;
    }
    return text.length();
}
```

Phương thức Java này **hợp lệ trên JDK 17+**. Diễn giải:

- Nếu `input` **không** phải `String`: `!(input instanceof String text)` là `true`; `||` dừng sớm, không gọi `text.isBlank()`. Nhánh `if` trả `0`.
- Nếu `input` là `String`: biểu thức phủ định là `false`; lúc này biến `text` chắc chắn đã khớp nên **vế phải của `||` được phép gọi `text.isBlank()`**.
- Nếu chuỗi blank: điều kiện `||` là `true`, trả `0`.
- Nếu chuỗi không blank: toàn bộ `||` là `false`, nghĩa là đối tượng đã khớp `String` và không blank. Sau nhánh `if` kết thúc bằng `return`, `text` vẫn khả dụng để lấy `length()`.

Bảng diễn biến:

| `input` | `!(input instanceof String text)` | Vế phải `text.isBlank()` có chạy? | Trả về |
| --- | --- | --- | --- |
| `123` | `true` | Không | `0` |
| `"   "` | `false` | Có, trả `true` | `0` |
| `"Java"` | `false` | Có, trả `false` | `4` |
| `null` | `true` | Không | `0` |

Với `null`, phép `instanceof String text` trả `false`; `instanceof` ở đây không tự ném `NullPointerException`. Tuy nhiên, khi đã có một biến `text` hợp lệ, phương thức như `isBlank()` chỉ được gọi trong luồng bảo đảm khớp.

Đối chiếu hai dạng:

```java
// Hợp lệ: RHS của || chỉ chạy khi !(...) là false => mẫu khớp.
if (!(input instanceof String s) || s.isBlank()) {
    return;
}

// Sai: RHS của || chỉ chạy khi instanceof là false => không có s.
if (input instanceof String s || s.isBlank()) {
    return;
}
```

Đây là các đoạn để đối chiếu **trong một phương thức `void`** và không nên đặt hai dòng khai báo `s` vào cùng một scope như chương trình thực tế; dòng thứ hai được nêu rõ **cố ý sai** để chỉ ra lỗi biên dịch.

## 7. `if`/`else` và các điểm nối luồng

Cùng một `instanceof` có thể khiến biến mẫu khả dụng ở những nơi khác nhau tùy hình dạng câu lệnh:

**Dạng A — dùng trong nhánh đúng:**

```java
static String describeA(Object value) {
    if (value instanceof String s) {
        return "String: " + s;
    }
    return "Other";
}
```

`s` chỉ được dùng ở nhánh đã khớp. Sau `if`, ta không cần biến đó.

**Dạng B — bảo vệ nhánh sai rồi tiếp tục:**

```java
static String describeB(Object value) {
    if (!(value instanceof String s)) {
        return "Other";
    }
    return "String: " + s;
}
```

Ở đây `s` dùng được ở phần sau do đường không khớp đã `return`.

**Dạng C — nếu không khớp, nhánh `else` kết thúc:**

```java
static String describeC(Object value) {
    if (value instanceof String s) {
        // Không cần làm gì; mẫu đã khớp.
    } else {
        return "Other";
    }
    return "String: " + s;
}
```

Dạng C cũng **hợp lệ** vì từ điểm nối sau `if` chỉ còn đường điều kiện đúng đi tiếp. Sự khác nhau nằm ở **khả năng hoàn tất bình thường** của các nhánh, không phải chỉ ở việc có hay không có chữ `else`.

**Dạng sai — nhánh không khớp vẫn đi tiếp:**

```java
static String invalid(Object value) {
    if (value instanceof String s) {
        System.out.println(s);
    }
    // return s; // Sai: có đường đi không khớp vẫn tới đây.
    return "done";
}
```

Ở đoạn này, phương thức minh họa **biên dịch được vì dòng sai đã được comment**. Nếu bỏ comment ở `return s;`, Java sẽ báo lỗi phạm vi biến mẫu.

## 8. Biểu thức ba ngôi cũng phụ thuộc kết quả Boolean

Biến mẫu có thể được sử dụng ở nhánh tương ứng của toán tử điều kiện `?:`:

```java
static int safeLength(Object value) {
    return value instanceof String s ? s.length() : -1;
}
```

Đây là phương thức hợp lệ: vế sau dấu `?` chỉ chạy khi `instanceof` **đúng**, nên có thể gọi `s.length()`. Vế sau `:` chạy khi mẫu **không khớp**, do đó không thể dùng `s` ở đó.

```java
// Cố ý sai: nhánh sau : không bảo đảm String đã khớp.
// return value instanceof String s ? 0 : s.length();
```

Không nên áp dụng quy tắc "cứ ở sau ký tự `instanceof` trong cùng dòng thì dùng được" — vị trí chính xác là **nhánh của biểu thức mà đường đi đã chứng minh mẫu khớp**.

## 9. Chương trình Java 17+ hoàn chỉnh và kết quả thực thi

Lưu đoạn sau vào **`Main.java`**. Chương trình chứa cả kiểm tra nhiều điều kiện với `&&`, guard phủ định, `||` với điều kiện phủ định, toán tử `?:` và hai nhánh `if/else`.

```java
import java.util.Locale;

public class Main {
    static String classify(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "string(" + text.length() + "):" + text;
        }
        if (input instanceof Integer number && number > 0) {
            return "positive int:" + number;
        }
        return "other";
    }

    static String afterGuard(Object input) {
        if (!(input instanceof String text)) {
            return "not text";
        }
        return text.toUpperCase(Locale.ROOT);
    }

    static int nonBlankLength(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return 0;
        }
        return text.length();
    }

    static int ternaryLength(Object input) {
        return input instanceof String text ? text.length() : -1;
    }

    static String branch(Object input) {
        if (input instanceof String text) {
            return "text:" + text;
        } else {
            return "not-text";
        }
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify(""));
        System.out.println(classify(5));
        System.out.println(classify(-1));
        System.out.println(classify(null));
        System.out.println(afterGuard("java"));
        System.out.println(afterGuard(20));
        System.out.println(nonBlankLength("  ok  "));
        System.out.println(nonBlankLength(" "));
        System.out.println(nonBlankLength(20));
        System.out.println(ternaryLength("hi"));
        System.out.println(ternaryLength(10));
        System.out.println(branch("A"));
        System.out.println(branch(3));
    }
}
```

Biên dịch bằng cú pháp Java 17, không cần bật preview:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout thực tế đã được kiểm tra:**

```text
string(4):Java
other
positive int:5
other
other
JAVA
not text
6
0
0
2
-1
text:A
not-text
```

Giải thích các nhóm kết quả:

- `classify("Java")`: khớp `String`, `!text.isBlank()` đúng, trả `string(4):Java`.
- `classify("")`: khớp mẫu, nhưng điều kiện phụ với `&&` sai, kết quả `other`. Biến mẫu vẫn hợp lệ khi đánh giá `isBlank()`, nhưng nhánh nhận kết quả đúng không được chạy.
- `classify(5)`: không khớp `String`, sau đó khớp `Integer`, nên `positive int:5`.
- `classify(-1)` và `classify(null)`: không thỏa những điều kiện ghép, đều cho `other`. Với `null`, không có mẫu `String` hay `Integer` nào khớp.
- `afterGuard("java")`: biểu thức phủ định sai nên `text` khả dụng sau guard và được in hoa thành `JAVA`; `afterGuard(20)` trả `not text` sớm.
- `nonBlankLength("  ok  ")`: trả `6`, vì phương thức lấy độ dài của **chuỗi gốc**, không tự gọi `strip()`. Chuỗi một khoảng trắng và số nguyên đều trả `0`.
- `ternaryLength("hi")` là `2`; `ternaryLength(10)` là `-1`.
- `branch("A")` thuộc nhánh đã khớp, trả `text:A`; `branch(3)` thuộc `else`, trả `not-text`.

Các ví dụ trên không dùng ép kiểu `(String) input` vì pattern variable đã cung cấp tham chiếu có kiểu phù hợp **trong đường chạy được chứng minh là đã khớp**.

## 10. Các lỗi biên dịch thường gặp

| Tình huống | Trạng thái | Nguyên nhân |
| --- | --- | --- |
| `if (o instanceof String s) { s.length(); }` | Hợp lệ | Nhánh điều kiện đúng bảo đảm `s` khớp |
| `if (o instanceof String s && s.length() > 3)` | Hợp lệ | Vế phải `&&` chỉ chạy khi mẫu khớp |
| `if (o instanceof String s || s.isEmpty())` | Sai | Vế phải `||` chỉ chạy khi mẫu không khớp |
| `if (o instanceof String s || fallback) { dùng s; }` | Sai khi dùng `s` | Điều kiện chung đúng có thể do `fallback` |
| `if (!(o instanceof String s)) return; dùng s;` | Hợp lệ trong ngữ cảnh thích hợp | Đường không khớp đã kết thúc |
| `if (!(o instanceof String s) || s.isBlank()) return; dùng s;` | Hợp lệ trong ngữ cảnh thích hợp | Khi tới phần sau, mẫu đã khớp và không blank |
| `if (o instanceof String s) {...} else { dùng s; }` | Sai khi dùng `s` trong `else` | Nhánh sai không bảo đảm khớp |
| `o instanceof String s ? s.length() : 0` | Hợp lệ | Nhánh `?` chạy khi khớp |
| `o instanceof String s ? 0 : s.length()` | Sai | Nhánh `:` chạy khi không khớp |

Các dòng trích dẫn trong bảng là **mẫu cú pháp rút gọn**, không phải những chương trình độc lập; các ký hiệu `o`, `fallback` và `dùng s` chỉ diễn đạt ngữ cảnh.

### Tên biến bị trùng trong vùng scope

Vì biến mẫu là biến cục bộ có quy tắc phạm vi, cũng phải tránh khai báo một biến khác cùng tên trong phạm vi chồng lấn:

```java
Object value = "Java";
if (value instanceof String s) {
    // String s = "Khác"; // Sai: cùng tên biến trong phạm vi đã có s.
    System.out.println(s);
}
```

Tên `s` có thể được dùng lại ở những vùng không chồng lấn nếu quy tắc đặt tên Java cho phép, nhưng tránh lạm dụng vì làm code khó đọc.

### Kiểu kiểm tra và phạm vi là hai việc khác nhau

Điều kiện `o instanceof String s` không chỉ kiểm tra cú pháp: mã sau `&&` dùng API của `String`, còn mã sau nhánh không khớp không có biến ấy. Đó là lý do pattern matching giúp loại bỏ ép kiểu lặp lại **mà vẫn giữ an toàn kiểu tĩnh**, thay vì biến `s` thành kiểu động.

## 11. Cách viết dễ đọc, hạn chế lỗi scope

**Ưu tiên điều kiện dương với `&&`** khi cần xác minh kiểu rồi kiểm tra thêm đặc điểm của dữ liệu:

```java
if (value instanceof String s && s.length() >= 3) {
    System.out.println("Độ dài: " + s.length());
}
```

**Ưu tiên guard phủ định + `return`/`throw`** nếu phần còn lại của phương thức chỉ có ý nghĩa với kiểu đó:

```java
static String requiredString(Object value) {
    if (!(value instanceof String s)) {
        throw new IllegalArgumentException("A String is required");
    }
    return s.strip();
}
```

**Đặt điều kiện phủ định bên trái `||`** nếu muốn kết thúc sớm khi kiểu sai hoặc dữ liệu không hợp lệ:

```java
static boolean validNonBlankText(Object value) {
    if (!(value instanceof String s) || s.isBlank()) {
        return false;
    }
    return true;
}
```

Có thể viết ngắn hơn trong những trường hợp đơn giản:

```java
static boolean validNonBlankText(Object value) {
    return value instanceof String s && !s.isBlank();
}
```

Đây là hai phương án **thay thế nhau** cho cùng chữ ký phương thức, không đặt chung trong một lớp. Cả hai đều trả đúng khi giá trị là `String` không blank và đúng quy tắc ngắn mạch.

Khi điều kiện quá dài hoặc có nhiều đường rẽ, ưu tiên **tách phương thức nhỏ, dùng guard clause rõ ràng**. Đừng cố biến mọi điều kiện thành một biểu thức Boolean rối chỉ để giữ biến mẫu trong scope.

## 12. Tự kiểm tra kiến thức

Xét bốn câu hỏi dưới đây, với `obj` là `Object` và `s` là biến mẫu:

**Câu 1.** `if (obj instanceof String s && s.isEmpty()) { ... }` có hợp lệ không?

Có. Vế phải `&&` chỉ chạy khi mẫu khớp, nên có thể gọi `s.isEmpty()`.

**Câu 2.** `if (obj instanceof String s || isEnabled) { System.out.println(s); }` có dùng được `s` trong nhánh đúng không?

Không. `isEnabled` có thể làm toàn bộ biểu thức đúng ngay cả khi `obj` không phải `String`.

**Câu 3.** Vì sao `if (!(obj instanceof String s)) throw ...; System.out.println(s);` có thể hợp lệ?

Vì đường không khớp mẫu đã kết thúc bằng `throw`; tại dòng tiếp theo, mọi đường chạy còn lại đều bảo đảm mẫu `String` đã khớp.

**Câu 4.** `if (!(obj instanceof String s) || s.isBlank()) return;` có thể dùng `s` ở phần tiếp theo không?

Có, trong một phương thức mà nhánh `return` kết thúc luồng đó. Nếu tới phần tiếp theo, điều kiện ghép là `false`, nghĩa là `obj` đã khớp `String` và không blank.

**Ghi nhớ:** Phạm vi của biến mẫu phụ thuộc vào **kết quả điều kiện và những đường chạy còn đi tiếp**. `&&` cho phép dùng biến ở vế sau khi `instanceof` đúng; `||` trực tiếp không bảo đảm biến khớp; `!` đảo điều kiện và hỗ trợ guard sớm. Trình biên dịch kiểm tra việc biến **đã chắc chắn được liên kết với giá trị đúng kiểu** tại mỗi điểm sử dụng.

### Tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof (chuẩn từ Java 16)](https://openjdk.org/jeps/394).
- [Java Language Specification — Scope of Pattern Variables (`6.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3).
- [Java Language Specification — instanceof (`15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2).
