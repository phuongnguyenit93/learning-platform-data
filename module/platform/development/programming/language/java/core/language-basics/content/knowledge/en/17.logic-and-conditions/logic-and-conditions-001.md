# `&&`, `||` và `!` trong biểu thức boolean — Java 17+

Trong Java, ba toán tử logic này kết hợp hoặc đảo các **biểu thức `boolean`** để tạo ra kết quả `boolean`:

- `a && b` (*conditional AND*): đúng khi **cả hai** điều kiện đúng; nếu `a` sai thì **không đánh giá `b`**.
- `a || b` (*conditional OR*): đúng khi **ít nhất một** điều kiện đúng; nếu `a` đúng thì **không đánh giá `b`**.
- `!a` (*logical complement/NOT*): đảo giá trị logic, `true` thành `false` và ngược lại.

~~~java
boolean loggedIn = true;
boolean isAdmin = false;

boolean canManage = loggedIn && isAdmin; // false.
boolean canView = loggedIn || isAdmin;   // true.
boolean guest = !loggedIn;              // false.
~~~

**Quan trọng:** `&&` và `||` là toán tử **ngắn mạch** (*short-circuit*). Vế phải chỉ chạy nếu kết quả chưa xác định được từ vế trái. Điều này ảnh hưởng cả **tính đúng đắn** lẫn **tác dụng phụ** trong biểu thức.

## 1. Bảng chân trị

| `a` | `b` | `a && b` | `a || b` | `!a` |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

Cách nhớ:

- **AND `&&`**: “tất cả điều kiện đều phải đúng”.
- **OR `||`**: “chỉ cần một điều kiện đúng”.
- **NOT `!`**: “điều kiện không đúng”; `!!a` có cùng giá trị boolean với `a` khi được đánh giá bình thường.

Ví dụ xét quyền truy cập:

~~~java
boolean hasPermission = true;
boolean suspended = false;
boolean allowed = hasPermission && !suspended; // true.
~~~

Chủ thể phải có quyền **và** không bị đình chỉ. `!suspended` áp dụng cho riêng `suspended`; việc đặt tên biến rõ nghĩa giúp tránh phủ định nhầm.

## 2. Chương trình Java 17+ runnable

Tạo tệp UTF-8 tên **`BooleanLogicDemo.java`**:

~~~java
public class BooleanLogicDemo {
    static boolean mark(String name, boolean result) {
        System.out.println("eval=" + name);
        return result;
    }

    public static void main(String[] args) {
        boolean hasTicket = true;
        boolean adult = false;
        boolean blocked = false;

        System.out.println("and=" + (hasTicket && adult));
        System.out.println("or=" + (hasTicket || adult));
        System.out.println("not=" + (!blocked));
        System.out.println("combined="
                + (hasTicket && (adult || !blocked)));

        System.out.println("== truth table ==");
        System.out.println("FF=" + (false && false)
                + "," + (false || false));
        System.out.println("FT=" + (false && true)
                + "," + (false || true));
        System.out.println("TF=" + (true && false)
                + "," + (true || false));
        System.out.println("TT=" + (true && true)
                + "," + (true || true));

        System.out.println("== short circuit ==");
        boolean shortAnd = mark("and-left", false)
                && mark("and-right-skipped", true);
        System.out.println("shortAnd=" + shortAnd);

        boolean shortOr = mark("or-left", true)
                || mark("or-right-skipped", false);
        System.out.println("shortOr=" + shortOr);

        System.out.println("== eager alternatives ==");
        boolean eagerAnd = mark("eager-and-left", false)
                & mark("eager-and-right", true);
        System.out.println("eagerAnd=" + eagerAnd);

        boolean eagerOr = mark("eager-or-left", true)
                | mark("eager-or-right", false);
        System.out.println("eagerOr=" + eagerOr);

        System.out.println("== grouping ==");
        System.out.println("precedence="
                + (true || false && false));
        System.out.println("parenthesized="
                + ((true || false) && false));
        System.out.println("notAnd="
                + (!(true && false)));
        System.out.println("deMorganAnd="
                + ((!true) || (!false)));
        System.out.println("notOr="
                + (!(true || false)));
        System.out.println("deMorganOr="
                + ((!true) && (!false)));

        System.out.println("== guards ==");
        String name = null;
        boolean nonBlank = name != null && !name.isBlank();
        System.out.println("nonBlank=" + nonBlank);

        int divisor = 0;
        boolean safeDivision =
                divisor != 0 && 12 / divisor > 2;
        System.out.println("safeDivision=" + safeDivision);

        Boolean preference = null;
        System.out.println("nullableSafe="
                + Boolean.TRUE.equals(preference));
        try {
            boolean unsafe = !preference;
            System.out.println("unexpected=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("nullableNot=NullPointerException");
        }

        boolean access = hasTicket && (!blocked || adult);
        if (access) {
            System.out.println("access=allowed");
        } else {
            System.out.println("access=denied");
        }

        System.out.println("doubleNot=" + (!!hasTicket));
    }
}
~~~

Dùng **JDK 17 trở lên**. Mở PowerShell hoặc Bash tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 BooleanLogicDemo.java
java BooleanLogicDemo
~~~

**Exact expected stdout** của riêng lệnh `java BooleanLogicDemo`:

~~~text
and=false
or=true
not=true
combined=true
== truth table ==
FF=false,false
FT=false,true
TF=false,true
TT=true,true
== short circuit ==
eval=and-left
shortAnd=false
eval=or-left
shortOr=true
== eager alternatives ==
eval=eager-and-left
eval=eager-and-right
eagerAnd=false
eval=eager-or-left
eval=eager-or-right
eagerOr=true
== grouping ==
precedence=true
parenthesized=false
notAnd=true
deMorganAnd=true
notOr=false
deMorganOr=false
== guards ==
nonBlank=false
safeDivision=false
nullableSafe=false
nullableNot=NullPointerException
access=allowed
doubleNot=true
~~~

Hai lệnh `java -version` và `javac -version` hiển thị thông tin JDK tùy môi trường, không thuộc khối stdout cố định trên. Các phương thức `mark(...)` chỉ được sử dụng để in dấu vết và quan sát thứ tự thực thi, **không phải** phong cách khuyến nghị cho điều kiện nghiệp vụ.

## 3. Ngắn mạch: tại sao có lời gọi bị bỏ qua?

### `&&`: bên trái false thì không cần xét bên phải

~~~java
boolean result = mark("A", false) && mark("B", true);
~~~

Lời gọi `mark("A", false)` trả false nên `result` chắc chắn false. Java **không gọi** `mark("B", true)`. Dòng `eval=B` không xuất hiện.

### `||`: bên trái true thì không cần xét bên phải

~~~java
boolean result = mark("A", true) || mark("B", false);
~~~

Lời gọi `mark("A", true)` đã xác định kết quả true; `mark("B", false)` không được gọi.

Nếu vế phải được đánh giá, Java đánh giá **vế trái trước rồi mới đến vế phải**, không hoán đổi hai vế tùy ý. Với chuỗi `a && b && c`, các toán hạng được kiểm tra theo thứ tự từ trái sang phải và dừng tại false đầu tiên; chuỗi `a || b || c` dừng tại true đầu tiên. Quy tắc này đặc biệt quan trọng nếu biểu thức con có thể ném ngoại lệ hoặc tác động tới trạng thái.

**Không nên dựa vào tác dụng phụ của vế phải** để cập nhật dữ liệu bắt buộc:

~~~java
// Khong nen: updateCounter() co the khong duoc goi.
// boolean ok = condition || updateCounter();
~~~

Nếu cập nhật là bắt buộc, hãy đặt thành câu lệnh độc lập; dùng `&&`/`||` để mô tả điều kiện chứ không để giấu thao tác nghiệp vụ.

## 4. `&&` so với `&`, `||` so với `|`

Java còn có toán tử `&` và `|` áp dụng cho `boolean`. Kết quả logic **giống bảng chân trị** AND/OR, nhưng khác ở **việc đánh giá toán hạng**:

| Với toán hạng boolean | Kết quả logic | Đánh giá vế phải nếu vế trái đã đủ quyết định? |
| --- | --- | --- |
| `a && b` | AND | **Không** nếu `a == false` |
| `a & b` | AND | **Có** |
| `a || b` | OR | **Không** nếu `a == true` |
| `a | b` | OR | **Có** |

Trong demo, `eagerAnd` và `eagerOr` đều in hai dòng `eval=...`; các phép ngắn mạch chỉ in vế trái.

`&` và `|` cũng có nghĩa **phép toán bit** với các kiểu số nguyên, không giống `&&` và `||`: toán tử logic ngắn mạch **chỉ nhận boolean**, không nhận số nguyên để làm “truthy/falsy”.

Nếu không có lý do rõ ràng để buộc cả hai điều kiện boolean thực thi, hãy ưu tiên `&&` và `||` vì chúng phản ánh điều kiện kết hợp và tránh thao tác không cần thiết.

## 5. Dùng điều kiện ngắn mạch để bảo vệ thao tác nguy hiểm

### Tránh truy cập `null`

~~~java
String name = null;
boolean hasText = name != null && !name.isBlank(); // false.
~~~

Vế trái false khiến lời gọi `name.isBlank()` **bị bỏ qua**, nên không gây `NullPointerException`. Đảo thứ tự là không an toàn:

~~~java
// Sai khi name == null:
// boolean hasText = !name.isBlank() && name != null;
~~~

Điều kiện gác cổng (*guard condition*) phải được đặt **trước** biểu thức phụ thuộc vào nó.

### Tránh chia số nguyên cho 0

~~~java
int divisor = 0;
boolean valid = divisor != 0 && (12 / divisor > 2); // false.
~~~

Nếu mẫu số bằng 0, Java không đánh giá phép chia phía sau. Để mã dễ đọc, có thể thêm ngoặc quanh phép so sánh bên phải.

Đây là cách bảo vệ phù hợp với **biến cục bộ không bị thay đổi bất ngờ giữa hai phép kiểm tra**. Khi trạng thái được chia sẻ giữa nhiều luồng, cần thiết kế đồng bộ/đọc snapshot phù hợp; không mặc nhiên coi hai lần đọc một trường dùng chung là một giao dịch nguyên tử.

### Xử lý `Boolean` có thể null

~~~java
Boolean enabled = null;
// boolean disabled = !enabled; // Nem NullPointerException do unboxing.
boolean enabledSafely = Boolean.TRUE.equals(enabled); // false.
~~~

`!` yêu cầu `boolean`; nếu vế toán hạng là `Boolean` thì Java unbox. `null` không thể unbox thành boolean và sẽ ném `NullPointerException`. `Boolean.TRUE.equals(value)` là cách kiểm tra rõ ý khi chỉ muốn đúng với `Boolean.TRUE`.

## 6. Độ ưu tiên: `!` trước `&&` trước `||`

Java nhóm ba toán tử theo thứ tự độ ưu tiên:

1. `!`: phủ định.
2. `&&`: AND ngắn mạch.
3. `||`: OR ngắn mạch.

~~~java
boolean result = true || false && false; // true.
// Nhom nhu: true || (false && false).

boolean different = (true || false) && false; // false.
~~~

Dấu ngoặc trong biểu thức phức tạp thường đáng dùng ngay cả khi compiler đã biết độ ưu tiên, vì chúng làm **ý nghĩa điều kiện rõ hơn cho người đọc**.

~~~java
boolean canEnter = hasTicket && (!blocked || adult);
~~~

Cách viết này thể hiện yêu cầu có vé **và** (không bị chặn **hoặc** đủ tuổi). Nếu bỏ ngoặc, `hasTicket && !blocked || adult` được nhóm khác: người đủ tuổi có thể vượt qua điều kiện vé, khiến ý đồ phân quyền thay đổi.

**Độ ưu tiên quyết định cách nhóm**, không tự thay đổi thứ tự chạy thành “tính phép trong ngoặc ưu tiên trước mọi toán hạng ngoài ngoặc”. Trong `a || (b && c)`, Java vẫn đánh giá `a` trước; chỉ khi `a` false mới cần đánh giá `b && c`.

## 7. Phủ định `!` và quy tắc De Morgan

`!` đảo boolean:

~~~java
boolean ready = true;
boolean notReady = !ready; // false.
boolean stillReady = !!ready; // true.
~~~

Khi phủ định biểu thức ghép, có hai quy tắc quan trọng:

| Biểu thức | Dạng tương đương |
| --- | --- |
| `!(a && b)` | `!a || !b` |
| `!(a || b)` | `!a && !b` |

Các công thức áp dụng với biểu thức boolean; chúng cũng giữ quy luật ngắn mạch và thứ tự đánh giá trái-sang-phải khi biến đổi đúng. Ví dụ:

~~~java
boolean isAdult = false;
boolean hasGuardian = true;

boolean rejected = !(isAdult || hasGuardian); // false.
boolean equivalent = !isAdult && !hasGuardian; // false.
~~~

**Lỗi phổ biến:** `!(a && b)` **không** tương đương `!a && !b`. Khi phủ định toàn bộ điều kiện, phải đổi AND ↔ OR và phủ định **từng toán hạng**.

Ngoài ra, `!` khác `~`: `~` đảo bit số nguyên, còn `!` phủ định boolean. `!0` hoặc `!1` **không hợp lệ** trong Java; Java không tự coi số 0 là false và số khác 0 là true.

## 8. Kết hợp điều kiện trong `if` và `while`

~~~java
int age = 20;
boolean hasIdentityCard = true;

if (age >= 18 && hasIdentityCard) {
    System.out.println("eligible");
}
~~~

Dùng `&&` để diễn đạt các điều kiện bắt buộc cùng đúng; dùng `||` cho các lựa chọn thay thế; dùng `!` để phủ định một điều kiện:

~~~java
boolean expired = false;
boolean locked = false;
boolean needsRenewal = expired || locked; // false.
boolean usable = !needsRenewal;          // true.
~~~

Cũng có thể dùng trong `while`, nhưng phải bảo đảm điều kiện cuối cùng có khả năng chuyển thành false nếu cần kết thúc vòng lặp; ngắn mạch **không tự bảo đảm** vòng lặp dừng.

Khi điều kiện quá dài, nên tách các phần thành biến tên rõ ràng như `hasValidSession`, `hasPermission`, `isBlocked` để hạn chế phủ định chồng nhau.

## 9. Các lỗi thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “`&&` và `&` với boolean hoàn toàn giống nhau.” | Kết quả logic thường giống, nhưng `&` **luôn đánh giá** vế phải nếu không có ngoại lệ |
| “`||` luôn đánh giá hai vế.” | Không, vế phải bị bỏ qua khi vế trái true |
| “`!` đảo một số như `!0`.” | Sai kiểu; `!` yêu cầu boolean |
| “`!a && !b` luôn bằng `!(a && b)`.” | Sai; dạng đúng là `!a || !b` |
| “`true || false && false` giống `(true || false) && false`.” | Không; kết quả lần lượt true và false |
| “`name != null && name.isBlank()` vẫn gọi phương thức khi null.” | Không; vế phải bị bỏ qua nếu null |
| “`Boolean` null tự được coi là false.” | Không; unboxing null ném `NullPointerException` |
| “Có thể dựa vào vế phải `&&` để luôn cập nhật bộ đếm.” | Không; vế phải có thể không được đánh giá |
| “Thứ tự các điều kiện AND không quan trọng.” | Khi có exception/tác dụng phụ, thứ tự và guard rất quan trọng |

## 10. Bài tập tự kiểm tra

1. `true && false`, `true || false`, `!true` cho gì?  
   *Đáp án:* false, true, false.
2. `true || false && false` bằng gì? Thêm ngoặc `(true || false) && false` thì sao?  
   *Đáp án:* true và false.
3. Trong `false && expensive()`, phương thức `expensive()` có được gọi không?  
   *Đáp án:* Không.
4. Trong `true | check()` với hai toán hạng boolean, `check()` có được gọi không?  
   *Đáp án:* Có, nếu việc đánh giá tới vế phải bình thường.
5. Với `String s = null`, `s != null && !s.isBlank()` có gây `NullPointerException` không?  
   *Đáp án:* Không; ngắn mạch bỏ qua vế phải.
6. Viết lại `!(isAdmin || isOwner)` theo De Morgan.  
   *Đáp án:* `!isAdmin && !isOwner`.
7. `Boolean flag = null; boolean b = !flag;` gây gì?  
   *Đáp án:* `NullPointerException` khi unbox.
8. Cần đủ tuổi **và** (có vé **hoặc** có giấy mời). Viết điều kiện.  
   *Đáp án:* `isAdult && (hasTicket || hasInvitation)`.

## Checklist

- [ ] Phân biệt `&&` (AND), `||` (OR), `!` (NOT), tất cả đều làm việc với boolean.
- [ ] Hiểu hai toán tử `&&`/`||` **đánh giá ngắn mạch từ trái sang phải**.
- [ ] Biết `&` và `|` boolean **không ngắn mạch**.
- [ ] Dùng điều kiện guard trước khi truy cập nullable hoặc chia nguyên.
- [ ] Ghi nhớ thứ tự ưu tiên: `!` rồi `&&` rồi `||`.
- [ ] Áp dụng đúng De Morgan khi phủ định điều kiện ghép.
- [ ] Không dùng số hoặc String như boolean; kiểm tra `Boolean` có thể null.
- [ ] Tránh phụ thuộc vào tác dụng phụ ẩn trong một biểu thức logic.

**Kết luận:** `&&`, `||` và `!` là nền tảng của biểu thức điều kiện Java. Muốn dùng đúng, không chỉ thuộc bảng chân trị mà còn cần hiểu **đánh giá ngắn mạch**, **thứ tự ưu tiên**, **phủ định điều kiện ghép** và **các rủi ro null/exception**.
