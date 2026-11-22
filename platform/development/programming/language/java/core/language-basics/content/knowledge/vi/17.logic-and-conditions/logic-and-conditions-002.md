# Đánh giá ngắn mạch và những biểu thức không được chạy trong Java

> **Java core — language-basics / Logic và điều kiện**  
> **Yêu cầu:** JDK 17+, một file Java độc lập, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Dự đoán khi nào Java **không đánh giá vế phải** của `&&`, `||` và **nhánh không được chọn** của `?:`; phân biệt chúng với `&`, `|`, `^` trên boolean; viết guard tránh lỗi và kiểm soát side effect.

## 1. Đánh giá ngắn mạch là gì?

**Short-circuit evaluation** (đánh giá ngắn mạch) nghĩa là Java **không cần chạy một biểu thức con** khi vế đã tính đủ để biết kết quả của toàn bộ phép logic.

- `left && right`: nếu `left` là **false**, kết quả chắc chắn false, nên **không đánh giá `right`**.
- `left || right`: nếu `left` là **true**, kết quả chắc chắn true, nên **không đánh giá `right`**.
- Nếu cần biết vế phải để quyết định kết quả, Java **có đánh giá** vế phải.

Ví dụ:

~~~java
boolean andResult = false && expensiveCheck(); // false, không gọi hàm.
boolean orResult = true || expensiveCheck();   // true, không gọi hàm.
~~~

`expensiveCheck()` ở đây chỉ là tên minh họa; hãy xem chương trình runnable bên dưới để có các phương thức thực tế.

**Phân biệt:** “Vế phải không được chạy” là hành vi **lúc thực thi**. Java vẫn phải phân tích cú pháp và kiểm tra kiểu của toàn bộ biểu thức khi **biên dịch**, kể cả một nhánh sẽ bị bỏ qua ở lần chạy cụ thể.

## 2. Bảng quyết định: vế phải có được đánh giá không?

| Toán tử | Vế trái | Có chạy vế phải? | Kết quả |
| --- | --- | --- | --- |
| `&&` | false | **Không** | false |
| `&&` | true | **Có** | Theo giá trị vế phải |
| OR ngắn mạch (`\|\|`) | true | **Không** | true |
| OR ngắn mạch (`\|\|`) | false | **Có** | Theo giá trị vế phải |

Java đánh giá **vế trái trước vế phải**. Nếu vế trái tự ném ngoại lệ thì biểu thức kết thúc bất thường và vế phải cũng không được đánh giá, nhưng đó **không phải** trường hợp short-circuit trả về giá trị boolean bình thường.

Chẳng hạn:

~~~java
boolean first = true && check();  // Phải đánh giá check().
boolean second = false || check(); // Phải đánh giá check().
~~~

Vì vậy không thể khẳng định “`&&` không chạy vế phải” hoặc “`||` không chạy vế phải” trong mọi trường hợp. Điều kiện chính xác là **vế trái đủ quyết định kết quả**.

## 3. Những biểu thức bị bỏ qua không gây side effect hay exception

Khi nhánh bị bỏ qua, các thao tác **bên trong nhánh đó không xảy ra**: không gọi hàm, không tăng biến, không truy cập mảng, không unbox đối tượng và không ném ngoại lệ bắt nguồn từ biểu thức bị bỏ qua.

~~~java
int counter = 0;
boolean a = false && (++counter > 0); // a=false, counter=0.
boolean b = true || (++counter > 0);  // b=true, counter vẫn=0.
~~~

Ví dụ với mẫu số bằng 0:

~~~java
int divisor = 0;
boolean valid = divisor != 0 && (10 / divisor > 2);
// valid=false, phép chia không được chạy, không có ArithmeticException.
~~~

**Không đảo guard:** `10 / divisor > 2 && divisor != 0` sẽ thực hiện phép chia trước và ném ngoại lệ nếu `divisor == 0`.

Các điều kiện trong biểu thức ngắn mạch là các biểu thức `boolean`; Java **không** chuyển ngầm số nguyên 0/1 thành false/true.

## 4. Guard an toàn cho null, mảng và điều kiện phụ thuộc

Short-circuit đặc biệt hữu ích khi một biểu thức chỉ hợp lệ **sau khi đã kiểm tra điều kiện trước đó**.

~~~java
String text = null;
boolean hasText = text != null && !text.isBlank(); // false, không NPE.

int[] numbers = {5, 10, 15};
int index = -1;
boolean validIndex = index >= 0
        && index < numbers.length
        && numbers[index] > 0; // false, không truy cập numbers[-1].
~~~

Với nhiều `&&` liên tiếp, Java đánh giá từ trái sang phải và **dừng tại điều kiện false đầu tiên**; mọi điều kiện còn lại đều không chạy.

Với `||`, điều kiện có thể được viết theo dạng có giá trị mặc định:

~~~java
String name = null;
boolean missingOrBlank = name == null || name.isBlank();
// true, không gọi name.isBlank().
~~~

Điều kiện bảo vệ phải nằm ở **bên trái** phép logic tương ứng. Nếu `name` là null mà viết `name.isBlank() || name == null`, ngoại lệ xảy ra trước khi tới phép kiểm tra null.

## 5. `&`, `|` và `^` trên boolean không ngắn mạch

`&`, `|` và `^` có thể dùng cho boolean, nhưng khác với `&&`/`||` ở việc **vẫn đánh giá cả hai vế**:

| Toán tử boolean | Ý nghĩa | Đánh giá vế phải |
| --- | --- | --- |
| `&&` | AND ngắn mạch | Chỉ khi vế trái true |
| `\|\|` | OR ngắn mạch | Chỉ khi vế trái false |
| `&` | AND không ngắn mạch | **Luôn** |
| `\|` | OR không ngắn mạch | **Luôn** |
| `^` | XOR | **Luôn** |

~~~java
int counter = 0;
boolean result = false & (++counter > 0);
// result=false, nhưng counter=1 vì vế phải vẫn chạy.
~~~

Nếu vế phải ném ngoại lệ, `false & right` **vẫn ném**, còn `false && right` bỏ qua vế phải.

**Ghi nhớ về kiểu dữ liệu:** `&`, `|` và `^` cũng có cách dùng *bitwise* với số nguyên; `&&` và `||` không phải toán tử bitwise và chỉ dùng với boolean. Không tùy tiện thay cặp toán tử ngắn mạch bằng loại một ký tự khi vế phải chứa thao tác tốn kém hoặc có thể lỗi.

## 6. Toán tử điều kiện `?:` cũng bỏ qua nhánh không chọn

Biểu thức `condition ? whenTrue : whenFalse` đánh giá `condition` trước và **chỉ đánh giá một trong hai nhánh**:

~~~java
int x = 5;
int result = x > 0 ? computePositive() : computeNonPositive();
// Nếu x > 0: chỉ gọi computePositive().
// Nếu x <= 0: chỉ gọi computeNonPositive().
~~~

Đây là **đánh giá có điều kiện**, tương tự cơ chế chỉ chạy nhánh được chọn trong `if/else`. Không nên đánh đồng `?:` với việc chạy cả hai phép tính rồi chọn một kết quả.

Ví dụ với log:

~~~java
StringBuilder log = new StringBuilder();
int result = false
        ? markInt(log, "X", 10)
        : markInt(log, "R", 20);
// result=20, log="R"; markInt(...,"X",...) không được gọi.
~~~

Khi hai nhánh có tác dụng phụ đáng kể, `if/else` thường diễn đạt ý đồ dễ đọc và debug hơn toán tử ba ngôi lồng nhau.

## 7. Code Java 17+ runnable: quan sát nhánh bị bỏ qua

Tạo file **ShortCircuitDemo.java**:

~~~java
public final class ShortCircuitDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    private static int markInt(
            StringBuilder log, String label, int value) {
        log.append(label);
        return value;
    }

    private static boolean fail() {
        throw new IllegalStateException("executed");
    }

    public static void main(String[] args) {
        StringBuilder trace = new StringBuilder();

        boolean and = mark(trace, "F", false)
                && mark(trace, "X", true);
        boolean or = mark(trace, "T", true)
                || mark(trace, "Y", false);
        boolean eagerAnd = mark(trace, "A", false)
                & mark(trace, "B", true);
        boolean eagerOr = mark(trace, "C", true)
                | mark(trace, "D", false);
        boolean xor = mark(trace, "E", true)
                ^ mark(trace, "G", false);

        System.out.println("and=" + and);
        System.out.println("or=" + or);
        System.out.println("eagerAnd=" + eagerAnd);
        System.out.println("eagerOr=" + eagerOr);
        System.out.println("xor=" + xor);
        System.out.println("trace=" + trace);

        String name = null;
        System.out.println("nullGuard="
                + (name != null && !name.isBlank()));
        System.out.println("nullOr="
                + (name == null || name.isBlank()));

        int[] numbers = {5, 10, 15};
        int index = -1;
        System.out.println("indexGuard="
                + (index >= 0 && index < numbers.length
                    && numbers[index] > 0));

        int zero = 0;
        System.out.println("divideGuard="
                + (zero != 0 && 10 / zero > 2));

        boolean skippedAnd = false && fail();
        boolean skippedOr = true || fail();
        System.out.println("skippedAnd=" + skippedAnd);
        System.out.println("skippedOr=" + skippedOr);

        try {
            boolean eager = false & fail();
            System.out.println("eager=" + eager);
        } catch (IllegalStateException ex) {
            System.out.println("eagerThrows=IllegalStateException");
        }

        StringBuilder branches = new StringBuilder();
        int selected = false
                ? markInt(branches, "X", 10)
                : markInt(branches, "R", 20);
        int other = true
                ? markInt(branches, "L", 30)
                : markInt(branches, "Y", 40);
        System.out.println("conditional=" + selected + "," + other);
        System.out.println("branchTrace=" + branches);

        int[] visits = {0};
        boolean short1 = false && (++visits[0] > 0);
        boolean short2 = true || (++visits[0] > 0);
        System.out.println("shortCount=" + visits[0]);
        boolean eager = false & (++visits[0] > 0);
        System.out.println("eagerCount=" + visits[0]);

        Boolean unknown = null;
        boolean boxedGuard = unknown != null && unknown;
        System.out.println("boxedGuard=" + boxedGuard);
        try {
            boolean unsafe = true && unknown;
            System.out.println("unsafe=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("boxedNull=NullPointerException");
        }
    }
}
~~~

Biên dịch/chạy ở thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ShortCircuitDemo.java
java ShortCircuitDemo
~~~

**Expected stdout chính xác:**

~~~text
and=false
or=true
eagerAnd=false
eagerOr=true
xor=true
trace=FTABCDEG
nullGuard=false
nullOr=true
indexGuard=false
divideGuard=false
skippedAnd=false
skippedOr=true
eagerThrows=IllegalStateException
conditional=20,30
branchTrace=RL
shortCount=0
eagerCount=1
boxedGuard=false
boxedNull=NullPointerException
~~~

Dấu vết `FTABCDEG`: `&&` bỏ qua X, `||` bỏ qua Y, còn `&`, `|`, `^` đều chạy cả hai vế. `branchTrace=RL` chỉ có nhánh được chọn; `shortCount=0` xác nhận hai thao tác `++` bị bỏ qua, còn `eagerCount=1` thể hiện tác dụng phụ của `&`.

## 8. Sai lầm thường gặp và bài tập

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| `obj.method() && obj != null` | Có thể gọi method trên null trước khi guard | `obj != null && obj.method()` |
| `array[i] > 0 && i >= 0` | Có thể truy cập chỉ số không hợp lệ | `i >= 0 && i < array.length && array[i] > 0` |
| `divisor != 0 & 10 / divisor > 1` | `&` vẫn tính phép chia khi divisor=0 | Dùng `&&` |
| `true \|\| validate()` mà muốn validate luôn chạy | `validate()` không được gọi | Gọi riêng `validate()` nếu bắt buộc có side effect |
| `flag = cond && updateState()` và luôn muốn updateState | Hàm bị bỏ qua khi cond=false | Tách việc cập nhật thành câu lệnh riêng |
| Dùng `?:` với hai nhánh side effect dài | Khó đọc khi nhánh nào chạy không rõ | Dùng `if/else` |

**Bài 1.** Dự đoán bao nhiêu lần `check()` được gọi trong `false && check()`, `true && check()`, `true || check()`, `false || check()`.

**Bài 2.** Cho `int x = 0;`. So sánh `false && (++x > 0)` với `false & (++x > 0)`. Giá trị `x` cuối mỗi trường hợp là gì?

**Bài 3.** Với `String s = null;`, điều gì xảy ra trong `s != null && s.length() > 0` và `s.length() > 0 && s != null`?

**Bài 4.** Tạo biểu thức ba ngôi với hai hàm ghi dấu vết. Xác định nhánh nào được chạy ở mỗi giá trị điều kiện.

**Bài 5.** Phân biệt `false && fail()` với `false & fail()` nếu `fail()` ném exception.

### Ghi nhớ

**`&&` bỏ vế phải khi vế trái false; `||` bỏ vế phải khi vế trái true.** `?:` chỉ chạy nhánh được chọn. Biểu thức bị bỏ qua **không thực hiện tác dụng phụ, lời gọi hay exception của chính nó**, nhưng vẫn phải hợp lệ khi biên dịch. `&`, `|`, `^` trên boolean đánh giá cả hai vế. Đặt guard đúng phía và không dựa vào short-circuit nếu một thao tác **bắt buộc phải chạy**.
