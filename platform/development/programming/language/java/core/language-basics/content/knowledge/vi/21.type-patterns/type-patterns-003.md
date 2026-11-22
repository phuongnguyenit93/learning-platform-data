# Phạm vi biến mẫu phụ thuộc luồng điều kiện — Java 17+

## 1. Phạm vi biến mẫu là gì?

Java 17 hỗ trợ **pattern matching cho `instanceof`** (tính năng ổn định từ Java 16). Cú pháp kiểm tra kiểu và khai báo biến mẫu (*pattern variable*) trong cùng một biểu thức:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

**Exact stdout:**

~~~text
7
~~~

Khi điều kiện `value instanceof String text` đúng, Java đã xác nhận `value` là `String` và gán tham chiếu tương ứng cho biến mẫu `text`, không cần cast thủ công.

Điểm quan trọng của bài: **phạm vi của `text` không chỉ phụ thuộc dấu `{ }` mà còn phụ thuộc luồng điều kiện**. Compiler chỉ cho phép sử dụng biến mẫu ở nơi nó chứng minh được rằng mẫu đã **khớp chắc chắn** (*definitely matched*). Cơ chế đó gọi là **flow scoping**.

## 2. Cách đọc luồng thay vì chỉ nhìn dấu ngoặc

Type pattern tránh phải viết lại phép cast sau `instanceof`; điểm cần phân tích ở đây là **nhánh nào bảo đảm mẫu đã khớp**. Chẳng hạn, trong `if (value instanceof String text)`, thân `if` có thể dùng `text` vì điều kiện đúng, còn `else` không có sự bảo đảm đó. Khi điều kiện không khớp mà luồng vẫn chạy tiếp, không thể dùng `text` sau toàn bộ `if`.

Những phần tiếp theo xem xét riêng phép `&&`, `||`, phủ định, guard thoát sớm, toán tử ba ngôi và `else if` để rút ra quy tắc này từ luồng điều khiển. Với `value == null`, kiểm tra kiểu thất bại mà không ném NPE.

## 3. Trong nhánh `if` đúng, biến mẫu dùng được

~~~java
static String inspect(Object value) {
    if (value instanceof String text) {
        return "LEN:" + text.length();
    }
    return "NOT_STRING";
}
~~~

- Khi điều kiện đúng, `text` chắc chắn là một `String`.
- Khi điều kiện sai, không thể dùng `text` ở nhánh `else` của chính phép kiểm tra dương.
- Sau toàn bộ `if`, nếu vẫn có đường đi mà pattern không khớp, `text` cũng **không được coi là chắc chắn tồn tại**.

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ.
} else {
    System.out.println("not a String");
    // System.out.println(text); // LỖI COMPILE: text không có phạm vi ở đây.
}
// System.out.println(text); // LỖI nếu có đường đi chưa khớp mẫu.
~~~

Trong ví dụ này biến `text` chỉ có thể sử dụng ở nhánh mà compiler biết mẫu khớp. Không dùng tên biến mẫu như một biến cục bộ được khai báo vô điều kiện ở đầu phương thức.

## 4. Kết hợp `instanceof` với `&&`: vế phải biết mẫu đã khớp

Toán tử `&&` đánh giá từ trái sang phải và **ngắn mạch**: nếu vế trái `false`, vế phải không chạy.

~~~java
static boolean isLongString(Object value) {
    return value instanceof String text && text.length() >= 4;
}
~~~

Vế phải `text.length() >= 4` chỉ được đánh giá khi `value instanceof String text` đúng, nên tại đó `text` chắc chắn đã khớp mẫu.

| `value` | Nhánh `instanceof` | Vế phải `text.length()` | Kết quả |
|---|---|---|---|
| `"Java"` | true | Được đánh giá: 4 | true |
| `"Go"` | true | Được đánh giá: 2 | false |
| `Integer.valueOf(7)` | false | **Bỏ qua** | false |
| `null` | false | **Bỏ qua** | false |

Có thể thêm guard hoặc phương thức chỉ dùng biến mẫu sau khi khớp:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.length() <= 20) {
    System.out.println(text.strip());
}
~~~

**Thứ tự là quan trọng:** đặt kiểm tra mẫu ở bên trái, rồi mới dùng biến mẫu ở những điều kiện tiếp theo.

## 5. Vì sao `||` với kiểm tra mẫu dương không cho dùng biến ở vế phải?

Xét ý định sai:

~~~java
// if (value instanceof String text || text.isEmpty()) {
//     System.out.println("accepted");
// }
~~~

Đây là **lỗi biên dịch**, không phải đơn thuần nguy cơ `NullPointerException`.

Với `A || B`, Java chỉ đánh giá `B` nếu `A` là **false**. Nhưng `A` ở đây chính là `value instanceof String text`, nên khi đi tới `B`, mẫu **chưa khớp**. Vì thế biến `text` không thuộc phạm vi hợp lệ ở vế phải.

**Đối chiếu:**

- `value instanceof String text && text.length() > 0` — **hợp lệ**.
- `value instanceof String text || text.length() > 0` — **không hợp lệ**.
- `value instanceof String text` đứng độc lập trong `if` — biến chỉ dùng được ở nhánh chắc chắn đã khớp.

Đừng tìm cách sửa lỗi biên dịch bằng cast tùy tiện ở vế phải; trước hết hãy xác định xem yêu cầu nghiệp vụ là “và” hay “hoặc”.

## 6. Phủ định `!` làm thay đổi luồng xác định phạm vi

Với biểu thức phủ định:

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
} else {
    System.out.println(text.length()); // Hợp lệ.
}
~~~

Ở nhánh `else`, phủ định `!(...)` là false, tức pattern bên trong **đã khớp**. Vì vậy compiler cho dùng `text`.

Ngược lại:

~~~java
if (!(value instanceof String text)) {
    // System.out.println(text.length()); // Không hợp lệ.
}
~~~

Trong nhánh `if` này, phép kiểm tra kiểu **không khớp**, nên không có biến `text` hợp lệ.

**Mẹo suy luận:** thay vì chỉ nhìn dấu ngoặc, hỏi: *để chương trình đi tới câu lệnh đang xét, biểu thức `instanceof` bắt buộc đã true hay chưa?*

## 7. Guard clause: biến mẫu có thể dùng sau câu `if`

Một mẫu rất hữu ích trong phương thức:

~~~java
static String describe(Object value) {
    if (!(value instanceof String text)) {
        return "NOT_STRING";
    }

    return "TEXT:" + text.strip();
}
~~~

Nếu giá trị không phải String, phương thức **trả về ngay**. Do đó, để đi tới câu `return "TEXT:" + text.strip()`, phép `instanceof` bắt buộc đã đúng, nên `text` thuộc phạm vi hợp lệ **ngay cả sau dấu `}` của `if`**.

Điều đó cho thấy flow scoping **không chỉ là phạm vi từ dấu ngoặc mở đến dấu ngoặc đóng**.

~~~java
if (!(value instanceof String text)) {
    return "NOT_STRING";
}
// text có thể được dùng tại đây vì nhánh thất bại đã return.
~~~

Nhưng nếu nhánh thất bại chỉ ghi log rồi tiếp tục:

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
}
// System.out.println(text.length()); // LỖI: đường đi thất bại vẫn tới đây.
~~~

**Lưu ý:** trong cùng phương thức, đoạn có `return` phải phù hợp kiểu trả về. Các ví dụ với `return` được đặt trong phương thức trả `String`.

## 8. `||` có thể hợp lệ khi kiểm tra bị phủ định

Biểu thức sau là **hợp lệ**:

~~~java
static String validate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return "VALID:" + text.strip();
}
~~~

Giải thích theo luồng:

1. `!(value instanceof String text)` true nếu không phải String; do `||` ngắn mạch nên **không gọi** `text.isBlank()`.
2. Nếu vế trái false, `value instanceof String text` đã true; vì thế vế phải được phép dùng `text`.
3. Sau câu `if`, chỉ có thể đi tiếp khi toàn bộ điều kiện là false. Điều này bảo đảm `text` là String và **không blank**, nên `text.strip()` an toàn.

| Đầu vào | Kết quả |
|---|---|
| `" Java "` | `VALID:Java` |
| `"   "` | `INVALID` |
| `Integer.valueOf(3)` | `INVALID` |
| `null` | `INVALID` |

So sánh nhanh:

~~~java
// Hợp lệ: kiểm tra mẫu dương và dùng &&.
value instanceof String text && !text.isBlank()

// Hợp lệ: phủ định mẫu, rồi dùng || trong guard.
!(value instanceof String text) || text.isBlank()

// Sai: mẫu dương với ||, dùng text ở vế phải.
// value instanceof String text || text.isBlank()
~~~

Cơ chế của compiler dựa trên **luồng logic** chứ không dựa vào việc biến có tên giống nhau trong biểu thức.

## 9. Dùng `||` để trả boolean khi không phải String hoặc chuỗi rỗng

~~~java
static boolean emptyOrNotString(Object value) {
    return !(value instanceof String text) || text.isEmpty();
}
~~~

Kết quả:

- `42` → true vì không phải String; vế phải được bỏ qua.
- `""` → true vì là String rỗng.
- `"ok"` → false vì là String không rỗng.

Trong ví dụ này, yêu cầu là “**không phải String HOẶC String rỗng**”, nên dùng `||` với mẫu bị phủ định là phù hợp.

**Không suy ra** rằng mọi trường hợp `||` đều cho phép dùng biến mẫu. Điều quyết định là khi chương trình bắt buộc phải đánh giá vế phải, pattern đã **definitely matched** hay chưa.

## 10. Biến mẫu trong toán tử điều kiện `?:`

Toán tử ba ngôi cũng có nhánh true/false rõ ràng:

~~~java
static int stringLengthOrMinusOne(Object value) {
    return value instanceof String text ? text.length() : -1;
}
~~~

Nhánh true của `?:` chỉ chạy khi `value instanceof String text` đúng nên `text.length()` hợp lệ. Nhánh false không có bảo đảm mẫu khớp:

~~~java
// int n = value instanceof String text
//         ? text.length()
//         : text.length(); // Không hợp lệ ở nhánh false.
~~~

Trường hợp này phù hợp khi biểu thức trả kết quả đơn giản. Với nhiều lệnh kiểm tra hoặc cần báo lỗi, một `if/else` rõ ràng có thể dễ đọc hơn.

## 11. Scope trong `else if` và biến mẫu khác

~~~java
static String describeValue(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "TEXT:" + text.strip();
    } else if (value instanceof Integer number) {
        return "INTEGER:" + (number + 1);
    }
    return "OTHER";
}
~~~

- `text` chỉ hợp lệ trong những vị trí được nhánh kiểm tra String đảm bảo.
- `number` chỉ hợp lệ trong nhánh kiểm tra Integer.
- Không được dùng `text` ở nhánh Integer khi điều kiện String có thể false.
- Sau toàn bộ chuỗi, không có bảo đảm một trong hai mẫu đã khớp, nên các biến mẫu không trở thành biến chung của phương thức.

**Lưu ý về điều kiện phụ:** một String có thể khớp `instanceof String text` nhưng bị loại do `text.isBlank()`. Khi đó nó không tự trở thành Integer; cuối cùng ví dụ trả `OTHER`.

Trong các biểu thức phức tạp, việc dùng cùng tên biến cho nhiều mẫu có phạm vi chồng lấn có thể gây lỗi khai báo trùng. Hãy đặt tên theo kiểu hoặc ý nghĩa (`text`, `number`) và giữ điều kiện dễ đọc.

## 12. Các giới hạn và điểm cần tránh

| Trường hợp | Hợp lệ? | Nguyên nhân |
|---|---|---|
| `if (o instanceof String s) { s.length(); }` | Có | Mẫu khớp ở nhánh true |
| `if (o instanceof String s && s.length() > 2)` | Có | Vế phải chỉ chạy khi mẫu khớp |
| `if (o instanceof String s || s.length() > 2)` | **Không** | Vế phải chỉ chạy khi mẫu không khớp |
| `if (!(o instanceof String s)) { return; } use(s);` | Có, trong phương thức `void` phù hợp | Đường đi chưa khớp đã thoát |
| `if (!(o instanceof String s)) { log(); } use(s);` | **Không** | Nhánh không khớp vẫn có thể đi tiếp |
| `if (!(o instanceof String s)) ... else use(s);` | Có | Nhánh else bảo đảm mẫu khớp |
| `!(o instanceof String s) || s.isEmpty()` | Có | Muốn đánh giá vế phải phải có mẫu khớp |
| `o instanceof String s ? s.length() : -1` | Có | Nhánh true bảo đảm khớp |
| `o instanceof String s ? 0 : s.length()` | **Không** | Nhánh false không bảo đảm khớp |

Một số điểm Java 17 đáng nhớ:

- Với `Object candidate = null;`, biểu thức `candidate instanceof String s` trả `false` mà không ném NPE; không có biến mẫu `s` trên đường đi đó. **Không viết trực tiếp literal `null instanceof String s` trong Java 17**: đó là type pattern bị từ chối khi biên dịch (mẫu vô điều kiện đối với kiểu của literal `null`). Kiểm tra kiểu không ràng buộc mẫu `null instanceof String` lại hợp lệ và cho `false`.
- Không dùng `switch` pattern matching như một tính năng ổn định mặc định của Java 17: ở phiên bản này nó thuộc **preview**; bài dùng `instanceof` pattern ổn định, biên dịch `--release 17` bình thường.
- Compiler thường từ chối mẫu `instanceof` hiển nhiên luôn đúng về mặt kiểu tĩnh (ví dụ biến đã khai báo `String` lại thử `instanceof String s`). Dùng mẫu kiểm tra kiểu tại nơi biểu thức có kiểu đủ rộng, như `Object` hoặc interface phù hợp.
- Chỉ dùng biến mẫu trong luồng đã xác nhận kiểu; đừng ép cast hoặc khai báo lại biến chỉ để “qua compiler” nếu biểu thức logic thực sự sai.

## 13. Chương trình Java 17 hoàn chỉnh

Tạo file đúng tên **`PatternFlowScopeDemo.java`**:

~~~java
import java.util.Locale;

public final class PatternFlowScopeDemo {
    private PatternFlowScopeDemo() {}

    static String inspect(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.strip().toUpperCase(Locale.ROOT);
        } else if (input instanceof Integer number) {
            return "INTEGER:" + (number + 1);
        }
        return "OTHER";
    }

    static String positiveBranch(Object value) {
        if (value instanceof String text) {
            return "STRING:" + text.length();
        }
        return "NOT_STRING";
    }

    static boolean longEnough(Object value) {
        return value instanceof String text && text.length() >= 4;
    }

    static String afterGuard(Object value) {
        if (!(value instanceof String text)) {
            return "NO_STRING";
        }
        return "AFTER_GUARD:" + text.length();
    }

    static String rejectInvalid(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "REJECT";
        }
        return "ACCEPT:" + text.strip();
    }

    static boolean emptyOrNotString(Object value) {
        return !(value instanceof String text) || text.isEmpty();
    }

    static int conditionalLength(Object value) {
        return value instanceof String text ? text.length() : -1;
    }

    static String negativeElse(Object value) {
        if (!(value instanceof String text)) {
            return "ELSE:NO";
        } else {
            return "ELSE:YES:" + text.length();
        }
    }

    static boolean traced(String label, boolean answer) {
        System.out.println("checked " + label);
        return answer;
    }

    static boolean tracedAnd(Object value) {
        return value instanceof String text
                && traced("length", text.length() >= 2);
    }

    public static void main(String[] args) {
        Object[] inputs = {
            " Java ", "   ", Integer.valueOf(41), null, "Go"
        };
        for (Object value : inputs) {
            System.out.println("inspect=" + inspect(value));
        }

        System.out.println("positive String=" + positiveBranch("Hi"));
        System.out.println("positive Integer=" + positiveBranch(5));

        System.out.println("long Java=" + longEnough("Java"));
        System.out.println("long Go=" + longEnough("Go"));
        System.out.println("long null=" + longEnough(null));

        System.out.println("guard String=" + afterGuard("abc"));
        System.out.println("guard Integer=" + afterGuard(5));

        System.out.println("reject blank=" + rejectInvalid("  "));
        System.out.println("reject number=" + rejectInvalid(5));
        System.out.println("accept text=" + rejectInvalid(" x "));

        System.out.println("empty non-string=" + emptyOrNotString(5));
        System.out.println("empty String=" + emptyOrNotString(""));
        System.out.println("nonempty String=" + emptyOrNotString("ok"));

        System.out.println("length hello=" + conditionalLength("hello"));
        System.out.println("length other=" + conditionalLength(5));

        System.out.println("negated else String=" + negativeElse("abc"));
        System.out.println("negated else null=" + negativeElse(null));

        System.out.println("traced Integer=" + tracedAnd(5));
        System.out.println("traced String=" + tracedAnd("Hi"));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục chứa file; không dùng thư viện ngoài JDK, Maven, Gradle hoặc tính năng preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PatternFlowScopeDemo.java
java -cp . PatternFlowScopeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PatternFlowScopeDemo.java
java -cp . PatternFlowScopeDemo
~~~

### Exact expected stdout

~~~text
inspect=TEXT:JAVA
inspect=OTHER
inspect=INTEGER:42
inspect=OTHER
inspect=TEXT:GO
positive String=STRING:2
positive Integer=NOT_STRING
long Java=true
long Go=false
long null=false
guard String=AFTER_GUARD:3
guard Integer=NO_STRING
reject blank=REJECT
reject number=REJECT
accept text=ACCEPT:x
empty non-string=true
empty String=true
nonempty String=false
length hello=5
length other=-1
negated else String=ELSE:YES:3
negated else null=ELSE:NO
traced Integer=false
checked length
traced String=true
~~~

**Vì sao output như vậy?**

1. `inspect` chỉ dùng `text` khi mẫu String khớp và chuỗi không blank; `Integer` được xử lý bằng biến `number` ở nhánh riêng.
2. `longEnough` minh họa `&&` cho phép truy cập `text.length()` ở vế phải và bỏ qua vế phải với null hoặc Integer.
3. `afterGuard` dùng được `text` sau `if`, do đường đi không khớp đã `return`.
4. `rejectInvalid` dùng `||` với phủ định pattern và từ chối String blank; sau guard chỉ còn chuỗi hợp lệ.
5. `emptyOrNotString` trả true với object không phải String hoặc chuỗi rỗng; bỏ qua `text.isEmpty()` nếu không khớp.
6. `conditionalLength` dùng biến mẫu trong nhánh true của `?:`.
7. `negativeElse` dùng `text` ở nhánh `else` khi phép phủ định false.
8. `tracedAnd(5)` **không in `checked length`** vì `instanceof` false; `tracedAnd("Hi")` mới gọi `traced`.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Lý do | Cách sửa |
|---|---|---|
| Dùng biến mẫu ở `else` của kiểm tra dương | Nhánh else có thể không khớp | Dùng biến ở nhánh true |
| Viết `o instanceof String s || s.isBlank()` | Vế phải của OR chỉ chạy khi mẫu không khớp | Dùng `&&` cho nhánh dương, hoặc `!(...) || ...` nếu logic yêu cầu |
| Dùng `s` sau `if` nhưng nhánh không khớp vẫn chạy tiếp | Không bảo đảm definitely matched | Guard clause `return`/`throw` ở nhánh thất bại |
| Tưởng dấu `{ }` là quy tắc duy nhất xác định scope | Java dùng phân tích luồng điều kiện | Xét các đường đi true/false |
| Dùng `s` trong nhánh true của `!(o instanceof String s)` | Nhánh đó nghĩa là không khớp | Dùng trong `else` hoặc sau guard thoát sớm |
| Dùng `s` ở nhánh false của `?:` kiểm tra dương | Không bảo đảm mẫu khớp | Chỉ dùng trong nhánh true |
| Nghĩ `null instanceof String s` sẽ ném NPE | `instanceof` trả false với null | Có thể dùng như một null-safe type guard |
| Viết cast lặp dù đã có pattern variable | Dễ dư code/cast sai | Dùng trực tiếp biến mẫu ở phạm vi hợp lệ |
| Giấu side effect trong điều kiện kiểu | Khó suy luận luồng/đầu ra | Tách kiểm tra và side effect khi cần |
| Dùng pattern switch preview mà không bật cờ trên JDK 17 | Lỗi compile/tính năng chưa ổn định | Dùng `instanceof` pattern ổn định |

## 15. Bài tập có đáp án

### Bài A — biến mẫu trong `&&`

~~~java
Object value = "Java";
boolean valid = value instanceof String text && text.length() == 4;
System.out.println(valid);
~~~

**Đáp án:** in `true`. Vế phải chỉ chạy khi pattern khớp.

### Bài B — tại sao `||` sai?

~~~java
// boolean bad = value instanceof String text || text.isEmpty();
~~~

**Đáp án:** nếu vế phải của `||` được đánh giá, pattern ở vế trái đã false; `text` chưa khớp chắc chắn nên không thuộc phạm vi. Sửa tùy ý định:

~~~java
boolean nonempty = value instanceof String text && !text.isEmpty();
~~~

Hoặc khi muốn “không phải String **hoặc** String rỗng”:

~~~java
boolean emptyOrWrongType =
        !(value instanceof String text) || text.isEmpty();
~~~

### Bài C — dùng biến sau guard clause

~~~java
static String uppercase(Object value) {
    if (!(value instanceof String text)) {
        return "UNKNOWN";
    }
    return text.toUpperCase(Locale.ROOT);
}
~~~

**Đáp án:** hợp lệ, vì đường đi thất bại đã `return`. Với `value = "hi"`, trả `"HI"`.

### Bài D — so sánh hai cấu trúc phủ định

~~~java
if (!(value instanceof String text)) {
    System.out.println("not a String");
} else {
    System.out.println(text.length());
}
~~~

**Đáp án:** `text` dùng được trong `else`, vì tới `else` có nghĩa pattern đã khớp.

### Bài E — toán tử điều kiện

~~~java
Object value = "abc";
int length = value instanceof String text ? text.length() : -1;
System.out.println(length);
~~~

**Đáp án:** `3`. Biến `text` thuộc phạm vi nhánh true của `?:`, không thuộc phạm vi nhánh false.

## 16. Checklist và kết luận

- [ ] Biết cú pháp `object instanceof Type variable` của Java 17.
- [ ] Hiểu biến mẫu chỉ tồn tại ở luồng mà compiler chứng minh pattern khớp.
- [ ] Dùng biến mẫu ở nhánh true của `if (o instanceof T t)`.
- [ ] Hiểu `&&` cho dùng biến mẫu ở vế phải của kiểm tra dương.
- [ ] Biết vì sao `||` với kiểm tra dương không cho dùng biến mẫu ở vế phải.
- [ ] Hiểu phủ định `!` thay đổi nhánh nào bảo đảm pattern khớp.
- [ ] Dùng guard `if (!(o instanceof T t)) return/throw` để dùng `t` sau guard.
- [ ] Biết `!(o instanceof T t) || ... t ...` có thể hợp lệ với short-circuit.
- [ ] Biết biến mẫu dùng được ở nhánh true của toán tử `?:` kiểm tra dương.
- [ ] Không sử dụng biến mẫu ở đường đi thất bại hoặc sau `if` khi đường đi thất bại còn tiếp tục.
- [ ] Biết `instanceof` trên null trả false, không ném NPE.
- [ ] Biên dịch và chạy `PatternFlowScopeDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Phạm vi biến mẫu trong Java 17 được quyết định bởi **luồng điều khiển và thông tin kiểu mà compiler chứng minh được**. Với `instanceof` dương, biến có sẵn ở nhánh đúng và vế phải `&&`; với phủ định, biến có thể xuất hiện ở `else`, vế phải của `||` phù hợp hoặc sau guard clause thoát sớm. Hiểu flow scoping giúp giảm cast thừa mà không sử dụng biến ở đường đi chưa được kiểm tra kiểu.