# Phân biệt `&&` với `&` và `||` với `|` — Java 17+

## 1. Vấn đề cần nắm

Trong Java, `&&` và `||` là **toán tử logic ngắn mạch** (*short-circuit*). `&` và `|` cũng có thể thao tác trên `boolean`, nhưng **không ngắn mạch**: vế phải vẫn được đánh giá dù kết quả logic đã được xác định. Khi dùng với kiểu số nguyên, `&` và `|` còn mang ý nghĩa **bitwise**, không phải phép so điều kiện.

~~~java
boolean a = false;
boolean b = true;

System.out.println(a && b); // false
System.out.println(a & b);  // false
System.out.println(b || a); // true
System.out.println(b | a);  // true
~~~

Bốn kết quả trên **giống nhau về giá trị logic**. Sự khác biệt quan trọng không nằm ở bảng chân trị mà ở **vế phải có được đánh giá hay không**. Vế phải có thể gọi method, sửa trạng thái, tốn tài nguyên hoặc ném ngoại lệ.

**Mục tiêu bài học:** biết chọn đúng toán tử, giải thích thứ tự thực thi, bảo vệ truy cập `null`/mảng, nhận diện side effect, hiểu bitwise trên kiểu nguyên và tránh lỗi do dấu ngoặc/độ ưu tiên.

## 2. Bảng so sánh nhanh

| Toán tử | Toán hạng hợp lệ tiêu biểu | Khi nào bỏ qua vế phải? | Ý nghĩa |
|---|---|---|---|
| `&&` | `boolean` / `Boolean` qua unboxing | Khi vế trái `false` | AND ngắn mạch |
| `&` | `boolean` hoặc số nguyên | **Không bao giờ** bỏ qua theo short-circuit | AND boolean không ngắn mạch hoặc AND từng bit |
| `||` | `boolean` / `Boolean` qua unboxing | Khi vế trái `true` | OR ngắn mạch |
| `|` | `boolean` hoặc số nguyên | **Không bao giờ** bỏ qua theo short-circuit | OR boolean không ngắn mạch hoặc OR từng bit |

**Trong bài này, “không ngắn mạch” nghĩa là** khi đã tới phép toán đó trong luồng thực thi bình thường, Java đánh giá cả hai toán hạng theo thứ tự từ trái sang phải. Nếu đánh giá vế trái đã ném exception, quá trình vẫn dừng; không có quy tắc nào buộc vế phải phải chạy sau một exception.

`&&` và `||` **không áp dụng cho hai toán hạng số nguyên**:

~~~java
int x = 6, y = 3;
int bits = x & y; // Hợp lệ
// int invalid = x && y; // Lỗi compile: toán hạng không phải boolean
~~~

Java không coi số nguyên 0 là `false` và số nguyên khác 0 là `true` như trong một số ngôn ngữ khác.

## 3. Quy tắc ngắn mạch của `&&`

`left && right` hoạt động như sau:

1. Đánh giá `left`.
2. Nếu `left` là `false`, **trả `false` ngay**; không đánh giá `right`.
3. Nếu `left` là `true`, đánh giá `right` và lấy kết quả boolean đó.

Ví dụ:

~~~java
int denominator = 0;
boolean safe = (denominator != 0) && (10 / denominator > 2);

System.out.println(safe); // false
~~~

Do `denominator != 0` là false, Java **không thực hiện** `10 / denominator`; không có `ArithmeticException`.

### Nếu đổi sang `&` sẽ khác hẳn

~~~java
int denominator = 0;
// boolean unsafe = (denominator != 0) & (10 / denominator > 2);
// Nếu chạy: ArithmeticException (chia số nguyên cho 0).
~~~

Với `&` trên boolean, vế phải **bắt buộc được đánh giá** khi vế trái đã hoàn tất bình thường, kể cả khi vế trái false. Đừng coi `&` là cách viết ngắn của `&&`.

## 4. Quy tắc ngắn mạch của `||`

`left || right` hoạt động như sau:

1. Đánh giá `left`.
2. Nếu `left` là `true`, **trả `true` ngay**; không đánh giá `right`.
3. Nếu `left` là `false`, đánh giá `right` và lấy kết quả boolean đó.

~~~java
int denominator = 0;
boolean invalidOrLarge = (denominator == 0)
        || (10 / denominator > 2);

System.out.println(invalidOrLarge); // true
~~~

Vế trái true, nên Java **bỏ qua phép chia**.

Nếu đổi sang `|`:

~~~java
// boolean unsafe = (denominator == 0) | (10 / denominator > 2);
// Nếu chạy: ArithmeticException.
~~~

**Mẹo nhớ:** `&&` dừng khi thấy false; `||` dừng khi thấy true. `&` và `|` trên boolean không có cơ chế bỏ qua vế phải này.

~~~mermaid
flowchart TD
    A["Đánh giá vế trái của &&"] --> B{"left là true?"}
    B -- "Không" --> C["Trả false; bỏ qua right"]
    B -- "Có" --> D["Đánh giá right"]
    E["Đánh giá vế trái của ||"] --> F{"left là true?"}
    F -- "Có" --> G["Trả true; bỏ qua right"]
    F -- "Không" --> H["Đánh giá right"]
    I["& hoặc | trên boolean"] --> J["Đánh giá left rồi right"]
    J --> K["Tính AND/OR từ hai kết quả"]
~~~

## 5. `&` và `|` trên boolean có cùng bảng chân trị

Nếu **cả hai toán hạng là boolean thuần**, không có side effect và không ném lỗi, `&&` và `&` cho cùng giá trị; `||` và `|` cũng vậy.

| `a` | `b` | `a && b` | `a & b` | `a || b` | `a | b` |
|---|---|---|---|---|---|
| false | false | false | false | false | false |
| false | true | false | false | true | true |
| true | false | false | false | true | true |
| true | true | true | true | true | true |

Vì sao không nên thay bừa?

~~~java
boolean result = false && doWork(); // doWork() KHÔNG được gọi
boolean other = false & doWork();   // doWork() ĐƯỢC gọi
~~~

Trong code thật, `doWork()` có thể cập nhật counter, gọi API bên ngoài hoặc phát sinh exception. Hai lệnh không có cùng hành vi, dù cùng cho giá trị false khi method chạy bình thường.

**Chọn ngắn mạch theo mặc định** khi viết điều kiện thông thường. Chỉ chọn `&`/`|` boolean khi **chủ ý yêu cầu đánh giá cả hai vế** và đã xem xét tác dụng phụ, chi phí và ngoại lệ.

## 6. Thứ tự đánh giá và side effect

Java đánh giá vế trái trước; khi phải đánh giá vế phải, nó diễn ra **sau vế trái**. Có thể quan sát bằng một method in ra tên:

~~~java
static boolean trace(String label, boolean answer) {
    System.out.println("called " + label);
    return answer;
}
~~~

Minh họa:

~~~java
boolean a = false && trace("skip-and", true);
boolean b = false & trace("eager-and", true);
boolean c = true || trace("skip-or", false);
boolean d = true | trace("eager-or", false);
~~~

Chỉ hai dòng được in:

~~~text
called eager-and
called eager-or
~~~

Nếu vế trái cũng có side effect:

~~~java
boolean result = trace("left", true) & trace("right", false);
~~~

thứ tự là:

~~~text
called left
called right
~~~

rồi kết quả boolean của phép `&` là false. **Không có việc hai vế được tính song song chỉ vì dùng `&` hoặc `|`**.

## 7. Guard cho tham chiếu có thể null

Khi viết `text != null && !text.isBlank()`, Java chỉ gọi `isBlank()` nếu `text` không null. Điều kiện đối xứng `text == null || text.isBlank()` cũng an toàn: nếu giá trị null, vế phải của `||` không chạy.

~~~java
String text = null;
boolean hasText = text != null && !text.isBlank();  // false
boolean missing = text == null || text.isBlank();    // true
~~~

Nếu thay `&&` bằng `&`, hoặc `||` bằng `|`, lời gọi trên null vẫn diễn ra và có thể gây `NullPointerException`. Với `Boolean enabled = null`, phép unboxing cũng có rủi ro tương tự; `enabled != null && enabled` hoặc `Boolean.TRUE.equals(enabled)` diễn đạt rõ chính sách cho phép true. Bài **Dùng ngắn mạch để kiểm tra null và giới hạn mảng** hướng dẫn các guard nhiều tầng; ở đây trọng tâm là **sự khác biệt về đánh giá giữa hai cặp toán tử**.

## 8. Mảng: thứ tự guard thay đổi hành vi

Một chỉ số hợp lệ phải không âm và nhỏ hơn độ dài mảng; với mảng nullable, kiểm tra tham chiếu trước:

~~~java
static boolean positiveAt(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length
            && array[index] > 0;
}
~~~

Viết các dấu `&` thay cho `&&` khiến Java có thể đánh giá `array.length` ngay cả khi mảng null, hoặc `array[index]` dù chỉ số ngoài miền, rồi ném ngoại lệ. Ví dụ này đủ để so sánh toán tử; kiểm tra phần tử nullable, mảng hai chiều, các ca biên và cách chọn guard clause được thực hành trong bài riêng ở hàng về **null và giới hạn mảng**.

## 9. Khi nào thật sự muốn đánh giá cả hai vế?

Đôi khi hai phép kiểm tra **độc lập** cần được thực hiện dù kiểm tra đầu không đạt, ví dụ ghi nhận đầy đủ lỗi đầu vào:

~~~java
boolean hasName = validateName();
boolean hasEmail = validateEmail();
boolean allValid = hasName && hasEmail;
~~~

Hai method được gọi **một lần mỗi method**, sau đó `&&` chỉ nối hai giá trị boolean đã tính. Cách này thường **rõ chủ đích hơn**:

~~~java
boolean allValid = validateName() & validateEmail();
~~~

Dòng thứ hai có thể hợp lệ nếu API thật sự muốn **cả hai method chạy**, nhưng kém rõ ràng đối với người đọc vốn quen `&` như toán tử bitwise. Khi việc chạy đầy đủ quan trọng, cách tách method thành các câu lệnh giúp bảo trì, test và log dễ hơn.

**Cẩn thận:** Nếu `validateName()` ném exception, Java không tiếp tục gọi `validateEmail()` trong **cả hai mẫu** trên nếu không có xử lý exception thích hợp. “Không ngắn mạch” không đồng nghĩa “luôn gọi đủ hai method bất kể lỗi”.

## 10. `&` và `|` còn là toán tử bitwise trên số nguyên

Khác với `&&`/`||`, toán tử `&`/`|` cũng có ý nghĩa bitwise với `byte`, `short`, `char`, `int`, `long` (sau numeric promotion).

Ví dụ:

~~~java
int a = 0b1100; // 12
int b = 0b1010; // 10

System.out.println(a & b); // 8: 1000
System.out.println(a | b); // 14: 1110
~~~

Biểu diễn:

~~~text
  1100 (12)
& 1010 (10)
= 1000 (8)

  1100 (12)
| 1010 (10)
= 1110 (14)
~~~

- Bitwise AND `&`: bit kết quả là 1 **khi cả hai bit ở cùng vị trí là 1**.
- Bitwise OR `|`: bit kết quả là 1 **khi ít nhất một bit ở vị trí đó là 1**.

Một ứng dụng thực tế là kiểm tra flag:

~~~java
int flags = 0b1100;
boolean hasRead = (flags & 0b0100) != 0;
System.out.println(hasRead); // true
~~~

**Dấu ngoặc cần thiết để thể hiện ý định:** `(flags & 0b0100) != 0` là phép AND bit trước rồi so khác 0. Dùng `&&` trực tiếp giữa hai số nguyên sẽ lỗi compile.

## 11. Độ ưu tiên toán tử và dấu ngoặc

Các toán tử có **độ ưu tiên khác nhau**. Với các nhóm đang học, theo thứ tự từ cao xuống thấp:

| Nhóm toán tử | Ví dụ | Ghi chú |
|---|---|---|
| So sánh bằng | `==`, `!=` | Ưu tiên cao hơn bitwise AND/OR |
| Bitwise/boolean AND | `&` | Ưu tiên cao hơn `^` và `|` |
| Bitwise/boolean XOR | `^` | Nằm giữa `&` và `|` |
| Bitwise/boolean OR | `|` | Ưu tiên cao hơn `&&` |
| AND ngắn mạch | `&&` | Ưu tiên cao hơn `||` |
| OR ngắn mạch | `||` | Thấp hơn `&&` |

Ví dụ:

~~~java
boolean a = true;
boolean b = false;
boolean c = false;

System.out.println(a || b && c);   // true: a || (b && c)
System.out.println((a || b) && c); // false
~~~

**Đặt ngoặc theo yêu cầu nghiệp vụ** khi trộn `&&` và `||`, hoặc `&`, `|` với so sánh số. Dấu ngoặc không tự biến `&` thành ngắn mạch và cũng không xóa side effect.

Lưu ý toán tử `!` (phủ định) áp dụng trên boolean: `!(a && b)` tương đương `!a || !b` về kết quả logic. Tuy nhiên, khi các toán hạng có side effect, **cần giữ thứ tự và số lần đánh giá** khi refactor.

## 12. Phép gán kết hợp `&=` và `|=` cũng không ngắn mạch

Trên biến `boolean`:

~~~java
boolean good = false;
good &= expensiveCheck(); // expensiveCheck() vẫn chạy

boolean ready = true;
ready |= expensiveCheck(); // expensiveCheck() vẫn chạy
~~~

`&=`/`|=` là **compound assignment** ứng với `&`/`|`, không phải `&&`/`||`.

Java **không có** các toán tử `&&=` hoặc `||=`.

Nếu mục tiêu là giữ ngắn mạch và cập nhật biến:

~~~java
good = good && expensiveCheck();
ready = ready || expensiveCheck();
~~~

Tuy nhiên, đây là **thay đổi ngữ nghĩa** nếu code gốc cần thực hiện `expensiveCheck()` dù giá trị `good`/ `ready` đã quyết định kết quả. Chỉ refactor sau khi xác nhận điều đó.

## 13. Tách việc cập nhật trạng thái khỏi guard

Toán tử ngắn mạch không tự sửa lỗi khi guard **thay đổi chính chỉ số đang kiểm tra**. Với `index = 1` và `values.length = 2`, phép `index++ < values.length` đúng rồi tăng `index` lên 2, khiến lần đọc `values[index]` tiếp theo vượt miền.

~~~java
int[] values = {10, 20};
int index = 1;
boolean valid = index >= 0 && index < values.length;
if (valid) {
    int current = values[index];
    index++; // Tách thay đổi khỏi điều kiện bảo vệ.
}
~~~

Guard cũng không tạo tính nguyên tử trước thay đổi từ thread khác; khi chia sẻ dữ liệu, cần đồng bộ hoặc snapshot đúng cách. Trọng tâm so sánh ở đây là **trình tự và số lần đánh giá**, không chỉ bảng chân trị.

## 14. Chương trình Java 17 hoàn chỉnh, chạy độc lập

Lưu file đúng tên **`ShortCircuitVsEagerDemo.java`**:

~~~java
public final class ShortCircuitVsEagerDemo {
    private ShortCircuitVsEagerDemo() {}

    static boolean trace(String label, boolean answer) {
        System.out.println("called " + label);
        return answer;
    }

    static boolean positiveAt(int[] array, int index) {
        return array != null
                && index >= 0
                && index < array.length
                && array[index] > 0;
    }

    public static void main(String[] args) {
        boolean leftFalse = false;
        boolean rightTrue = true;

        System.out.println("AND short=" + (leftFalse && rightTrue));
        System.out.println("AND eager=" + (leftFalse & rightTrue));
        System.out.println("OR short=" + (rightTrue || leftFalse));
        System.out.println("OR eager=" + (rightTrue | leftFalse));

        boolean skipAnd = false && trace("skip-and", true);
        System.out.println("skip &&=" + skipAnd);

        boolean eagerAnd = false & trace("eager-and", true);
        System.out.println("eager &=" + eagerAnd);

        boolean skipOr = true || trace("skip-or", false);
        System.out.println("skip ||=" + skipOr);

        boolean eagerOr = true | trace("eager-or", false);
        System.out.println("eager |=" + eagerOr);

        boolean both = trace("left", true)
                & trace("right", false);
        System.out.println("both evaluated=" + both);

        int zero = 0;
        boolean safeAnd = zero != 0 && 10 / zero > 2;
        boolean safeOr = zero == 0 || 10 / zero > 2;
        System.out.println("safe division &&=" + safeAnd);
        System.out.println("safe division ||=" + safeOr);

        try {
            boolean invalid = zero != 0 & 10 / zero > 2;
            System.out.println(invalid);
        } catch (ArithmeticException ex) {
            System.out.println("eager division=ArithmeticException");
        }

        String text = null;
        System.out.println("safe null &&="
                + (text != null && !text.isBlank()));
        System.out.println("safe null ||="
                + (text == null || text.isBlank()));
        try {
            boolean invalid = text != null & !text.isBlank();
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("eager null=NullPointerException");
        }

        Boolean boxed = null;
        System.out.println("nullable Boolean="
                + (boxed != null && boxed));
        System.out.println("boxed skipped &&=" + (false && boxed));
        System.out.println("boxed skipped ||=" + (true || boxed));
        try {
            boolean invalid = false & boxed;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("eager unboxing=NullPointerException");
        }

        int[] scores = {7, 0};
        System.out.println("array[0]=" + positiveAt(scores, 0));
        System.out.println("array end=" + positiveAt(scores, 2));
        System.out.println("array null=" + positiveAt(null, 0));

        try {
            boolean invalid = scores != null & scores[99] > 0;
            System.out.println(invalid);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("eager array=ArrayIndexOutOfBoundsException");
        }

        int first = 0b1100;
        int second = 0b1010;
        System.out.println("bitwise &=" + (first & second));
        System.out.println("bitwise |=" + (first | second));
        System.out.println("flag present="
                + ((first & 0b0100) != 0));

        boolean a = true, b = false, c = false;
        System.out.println("precedence default=" + (a || b && c));
        System.out.println("precedence grouped=" + ((a || b) && c));

        boolean compoundAnd = false;
        compoundAnd &= trace("compound-and", true);
        System.out.println("compound &=" + compoundAnd);

        boolean compoundOr = true;
        compoundOr |= trace("compound-or", false);
        System.out.println("compound |=" + compoundOr);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục chứa file. Không cần Maven, Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ShortCircuitVsEagerDemo.java
java -cp . ShortCircuitVsEagerDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShortCircuitVsEagerDemo.java
java -cp . ShortCircuitVsEagerDemo
~~~

**Exact expected stdout:**

~~~text
AND short=false
AND eager=false
OR short=true
OR eager=true
skip &&=false
called eager-and
eager &=false
skip ||=true
called eager-or
eager |=true
called left
called right
both evaluated=false
safe division &&=false
safe division ||=true
eager division=ArithmeticException
safe null &&=false
safe null ||=true
eager null=NullPointerException
nullable Boolean=false
boxed skipped &&=false
boxed skipped ||=true
eager unboxing=NullPointerException
array[0]=true
array end=false
array null=false
eager array=ArrayIndexOutOfBoundsException
bitwise &=8
bitwise |=14
flag present=true
precedence default=true
precedence grouped=false
called compound-and
compound &=false
called compound-or
compound |=true
~~~

### Đối chiếu ý nghĩa của output

1. Bốn dòng đầu chứng minh `&&`/`&`, `||`/`|` có **cùng bảng chân trị** trên boolean thuần.
2. Không có `called skip-and` hoặc `called skip-or`: vế phải của `&&`/`||` đã bị bỏ qua.
3. `called eager-and` và `called eager-or` xuất hiện: `&`/`|` boolean vẫn đánh giá vế phải.
4. `called left` trước `called right`: hai toán hạng của phép `&` được đánh giá từ trái sang phải.
5. Guard chia nguyên và null tránh exception; dùng eager boolean thì exception xuất hiện như in ra.
6. Wrapper `Boolean` null được bỏ qua bởi ngắn mạch nhưng gây NPE nếu buộc phải unbox.
7. Mảng truy cập an toàn nhờ đủ ba điều kiện; toán tử `&` với chỉ số ngoài miền gây exception.
8. `0b1100 & 0b1010 = 8`; `0b1100 | 0b1010 = 14`; đây là **bitwise**, không phải boolean short-circuit.
9. Hai dòng precedence khác nhau vì dấu ngoặc thay đổi nhóm logic.
10. Compound `&=`/`|=` vẫn gọi method ở vế phải, kể cả khi giá trị biến đã quyết định kết quả.

## 15. Lỗi thường gặp và cách xử lý

| Lỗi / ngộ nhận | Vì sao sai? | Hướng xử lý |
|---|---|---|
| `&&` và `&` boolean giống nhau trong mọi trường hợp | `&` đánh giá cả vế phải | Dùng `&&` nếu cần short-circuit |
| `||` và `|` boolean giống nhau trong mọi trường hợp | `|` đánh giá cả vế phải | Dùng `||` nếu cần short-circuit |
| `obj != null & obj.ready()` | Gọi method trên null | `obj != null && obj.ready()` |
| `array == null | array.length == 0` | Có thể đọc length của null | `array == null || array.length == 0` |
| `i < array.length && array[i] > 0` | Chưa kiểm tra `i >= 0` | Thêm guard chỉ số âm |
| Dùng `&` để buộc cả hai validation chạy, nhưng không xét exception | Exception vế trái vẫn dừng toàn biểu thức | Gọi từng validation có xử lý lỗi phù hợp |
| Nghĩ `&`/`|` chạy hai vế đồng thời | Java đánh giá tuần tự từ trái sang phải | Không giả định parallel |
| `int result = a && b;` | `&&` không thao tác trên int | `a & b` nếu mục tiêu là bitwise |
| `flags & MASK != 0` viết không ngoặc | Dễ hiểu nhầm precedence; có thể lỗi kiểu | `(flags & MASK) != 0` |
| `a || b && c` xem như `(a || b) && c` | `&&` ưu tiên cao hơn `||` | Dùng ngoặc theo ý định |
| `Boolean flag = null; false & flag` | Vế phải bị unbox dù vế trái false | Dùng `false && flag` nếu thật sự muốn skip |
| `flag &= check()` là ngắn mạch | `&=` không short-circuit | `flag = flag && check()` khi phù hợp |
| Đưa `index++` vào điều kiện guard | Chỉ số đổi trước lần đọc sau | Tách cập nhật thành câu lệnh riêng |
| Tin rằng short-circuit tạo thread safety | Guard không đồng bộ trạng thái giữa thread | Có chính sách đồng bộ/ownership |

## 16. Bài tập có đáp án

### Bài A — null guard

~~~java
String text = null;
boolean result = text != null && text.length() > 0;
System.out.println(result);
~~~

**Đáp án:** `false`, không ném NPE. Nếu đổi `&&` thành `&`, vế phải vẫn chạy và có thể ném NPE.

### Bài B — OR ngắn mạch

~~~java
int divisor = 0;
boolean invalid = divisor == 0 || 10 / divisor > 2;
System.out.println(invalid);
~~~

**Đáp án:** `true`; phép chia không chạy. Với `|`, phép chia sẽ được đánh giá và ném `ArithmeticException`.

### Bài C — side effect

~~~java
int[] calls = {0};
boolean result = false & (++calls[0] > 0);
System.out.println(result);
System.out.println(calls[0]);
~~~

**Đáp án:**

~~~text
false
1
~~~

Dù vế trái false, `&` vẫn tăng bộ đếm. Nếu thay bằng `&&`, kết quả false nhưng bộ đếm là 0.

### Bài D — bitwise

~~~java
int a = 0b0101;
int b = 0b0011;
System.out.println(a & b);
System.out.println(a | b);
~~~

**Đáp án:**

~~~text
1
7
~~~

Đây là phép toán trên **các bit**, không phải logic `&&`/`||`.

### Bài E — compound assignment

~~~java
int[] calls = {0};
boolean ready = true;
ready |= (++calls[0] > 0);
System.out.println(ready);
System.out.println(calls[0]);
~~~

**Đáp án:**

~~~text
true
1
~~~

`|=` vẫn đánh giá vế phải. Nếu chỉ muốn tăng khi `ready` false, có thể xem xét `ready = ready || (++calls[0] > 0);`, nhưng phải bảo đảm việc thay đổi side effect là đúng yêu cầu.

### Bài F — chọn cách kiểm tra đủ hai trường

Yêu cầu chạy cả `validateName()` và `validateEmail()` để thu thập thông báo lỗi từ mỗi hàm. Nên viết gì?

**Một đáp án dễ đọc:**

~~~java
boolean nameValid = validateName();
boolean emailValid = validateEmail();
boolean valid = nameValid && emailValid;
~~~

Hai lời gọi độc lập đều chạy khi thực hiện bình thường; biểu thức cuối chỉ tổng hợp boolean. Nếu từng validator có thể ném exception, cần xử lý exception theo hợp đồng để bảo đảm mục tiêu thu thập đủ lỗi.

## 17. Checklist và kết luận

- [ ] Biết `&&` bỏ qua vế phải khi trái false, còn `||` bỏ qua vế phải khi trái true.
- [ ] Biết `&`/`|` trên boolean **luôn đánh giá vế phải khi phép toán được thực hiện bình thường**.
- [ ] Phân biệt cùng **kết quả bảng chân trị** với khác **side effect/exception/chi phí**.
- [ ] Biết Java đánh giá vế trái trước vế phải, không tự chạy song song.
- [ ] Dùng `&&` cho null guard, index guard và phép toán có thể lỗi.
- [ ] Dùng `||` cho điều kiện loại trừ: null hoặc giá trị không hợp lệ.
- [ ] Tránh dùng `&`/`|` boolean thay toán tử ngắn mạch trong guard.
- [ ] Nhớ `&`/`|` còn là bitwise trên kiểu số nguyên.
- [ ] Dùng ngoặc khi kết hợp bitwise với so sánh và khi trộn `&&`/`||`.
- [ ] Biết `&=`/`|=` không ngắn mạch; Java không có `&&=`/`||=`.
- [ ] Không dùng side effect như `index++` làm thay đổi trạng thái giữa guard và truy cập.
- [ ] Hiểu short-circuit không thay thế xử lý exception hoặc đồng bộ đa luồng.
- [ ] Chạy `ShortCircuitVsEagerDemo.java` bằng Java 17+ và đối chiếu từng dòng stdout.

**Kết luận:** `&&` và `||` là lựa chọn mặc định cho **điều kiện logic có bảo vệ**, vì Java bảo đảm bỏ qua vế phải khi kết quả đã được quyết định. `&` và `|` trên boolean cho cùng bảng chân trị nhưng **đánh giá cả hai vế**, nên có thể làm thay đổi tác dụng phụ và ngoại lệ; trên số nguyên, chúng là **toán tử bitwise**. Chọn toán tử dựa trên **ngữ nghĩa đánh giá** chứ không chỉ nhìn vào kết quả true/false.