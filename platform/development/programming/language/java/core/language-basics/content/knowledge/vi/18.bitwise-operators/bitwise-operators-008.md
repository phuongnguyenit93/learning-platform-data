# Phân biệt phép tính theo bit với điều kiện boolean trong Java

> **Java core — language-basics / Toán tử bit**  
> **Phiên bản:** Java 17+; ví dụ độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Phân biệt phép toán trên **từng bit của số nguyên** với phép toán trên **giá trị đúng/sai**; dùng đúng `&`, `|`, `^`, `~`, `!`, `&&`, `||`; hiểu short-circuit và viết điều kiện kiểm tra bit mask hợp lệ.

## 1. Hai miền dữ liệu khác nhau

Trong Java, số nguyên được biểu diễn bằng các bit 0/1; còn kiểu `boolean` chỉ có giá trị `true` hoặc `false`. Một số ký hiệu toán tử được dùng ở **cả hai miền**, nhưng ý nghĩa được xác định bởi **kiểu toán hạng**.

~~~java
int bitsA = 0b1100; // 12
int bitsB = 0b1010; // 10
int bitResult = bitsA & bitsB; // 0b1000 = 8

boolean ready = true;
boolean allowed = false;
boolean logicResult = ready & allowed; // false
~~~

`&` trong dòng đầu tạo **số nguyên** từ từng cặp bit; `&` trong dòng sau tạo **boolean** từ hai điều kiện. Java **không** tự xem `int 0` là false, hoặc số khác 0 là true.

~~~java
// KHÔNG BIÊN DỊCH:
// if (1) { }
// boolean b = 1;
// int n = true;
// int mixed = 7 & true;
~~~

## 2. Phép bit trên số nguyên trả về số nguyên

Với `byte`, `short`, `char`, `int`, `long` (và wrapper có thể unbox), `&`, `|`, `^` xử lý từng vị trí bit; `~` đảo tất cả bit sau nâng kiểu. Ví dụ với `int a = 0b1100` và `b = 0b1010`:

~~~java
int a = 0b1100;
int b = 0b1010;
int and = a & b;       // 0b1000 = 8.
int or = a | b;        // 0b1110 = 14.
int xor = a ^ b;       // 0b0110 = 6.
int not = ~a;          // -13: đảo đủ 32 bit.
int fourBits = ~a & 0b1111; // 3: chỉ giữ 4 bit thấp.
~~~

Các biểu thức này trả **`int`**, không thể dùng trực tiếp làm điều kiện `if`. `byte`/`short`/`char` thường được nâng lên `int`, và có toán hạng `long` thì phép bit hai ngôi dùng `long`. Bài về AND/OR/XOR/NOT trình bày bảng chân trị chi tiết; phần sau tập trung vào sự khác biệt khi **cùng ký hiệu** nhận toán hạng `boolean`.

## 3. Toán tử logic trên boolean

| Toán tử | Ý nghĩa trên `boolean` | Vế phải có được đánh giá? |
| --- | --- | --- |
| `!a` | NOT: đảo true/false | Một toán hạng |
| `a && b` | AND ngắn mạch | **Chỉ khi `a` true** |
| OR ngắn mạch: `a \|\| b` | OR ngắn mạch | **Chỉ khi `a` false** |
| `a & b` | AND không ngắn mạch | **Luôn** |
| OR không ngắn mạch: `a \| b` | OR không ngắn mạch | **Luôn** |
| `a ^ b` | XOR | **Luôn** |

Ví dụ:

~~~java
boolean ready = true;
boolean allowed = false;

System.out.println(ready && allowed); // false
System.out.println(ready || allowed); // true
System.out.println(ready ^ allowed);  // true
System.out.println(!ready);           // false
~~~

Với `boolean`, `&` và `&&` có cùng **bảng chân trị**; `|` và `||` cũng vậy. **Khác biệt là thứ tự có đánh giá vế phải hay không.** `^` trả true khi đúng một trong hai giá trị là true; `~` không hợp lệ với boolean, phải dùng `!` để phủ định.

## 4. Short-circuit quyết định tác dụng phụ và ngoại lệ

Java đánh giá vế trái trước. Nếu vế trái đủ quyết định kết quả, `&&`/`||` bỏ qua vế phải; `&`/`|` trên boolean thì không.

~~~java
int divisor = 0;

boolean safe = divisor != 0 && 10 / divisor > 1;
// safe=false, không thực hiện phép chia cho 0.

// boolean unsafe = divisor != 0 & 10 / divisor > 1;
// Nếu chạy dòng này: ArithmeticException.
~~~

Điều tương tự xảy ra khi kiểm tra null:

~~~java
String name = null;
boolean hasText = name != null && !name.isBlank(); // false
boolean missing = name == null || name.isBlank();  // true
~~~

**Không** chuyển `&&` thành `&` hoặc `||` thành `|` chỉ vì kết quả logic thường giống nhau. Khi vế phải có lời gọi hàm, phép tăng biến, truy cập mảng hoặc unboxing `Boolean` nullable, sự khác biệt có thể làm thay đổi kết quả chương trình.

## 5. Bit mask: biến số nguyên không tự thành điều kiện

Một bit mask thường dùng để lưu các cờ bật/tắt trong **một số nguyên**:

~~~java
final int READ  = 0b0001;
final int WRITE = 0b0010;
final int EXEC  = 0b0100;

int permissions = READ | EXEC; // 0b0101
~~~

Muốn hỏi người dùng có quyền đọc không, phép `permissions & READ` trả về **int** (1 hoặc 0), chứ không trả boolean:

~~~java
boolean canRead = (permissions & READ) != 0;   // true
boolean canWrite = (permissions & WRITE) != 0; // false
boolean hasBoth = (permissions & (READ | EXEC))
        == (READ | EXEC);                      // true
~~~

| Mục đích | Biểu thức đúng | Kiểu kết quả |
| --- | --- | --- |
| Lọc các bit chung | `permissions & mask` | `int` |
| Có **ít nhất một** bit được chọn | `(permissions & mask) != 0` | `boolean` |
| Có **tất cả** bit được chọn | `(permissions & mask) == mask` | `boolean` |
| Bật bit | `permissions \| mask` | `int` |
| Tắt bit | `permissions & ~mask` | `int` |
| Đảo bit | `permissions ^ mask` | `int` |
| Kết hợp hai điều kiện boolean | `canRead && canWrite` | `boolean` |

Không viết `if (permissions & READ)`: `if` yêu cầu boolean nên Java báo lỗi biên dịch. Hãy chuyển **kết quả số nguyên** thành một phép so sánh boolean như `(permissions & READ) != 0`.

**Chú ý dấu ngoặc:** Java ưu tiên `==` và `!=` **cao hơn** `&` bitwise. Luôn viết `(permissions & mask) != 0`, không viết `permissions & mask != 0`.

## 6. Đừng trộn lẫn toán tử và ngữ nghĩa

| Biểu thức | Hợp lệ? | Vì sao? |
| --- | --- | --- |
| `5 & 3` | Có | Kết quả `int` là 1 |
| `true & false` | Có | Kết quả `boolean` false, hai vế đều chạy |
| `true && false` | Có | Kết quả boolean false, có short-circuit |
| `true ^ false` | Có | XOR logic là true |
| `~5` | Có | Bù bit `int`: -6 |
| `!true` | Có | Phủ định boolean: false |
| `5 && 3` | **Không** | `&&` chỉ nhận boolean |
| `~true` | **Không** | `~` chỉ nhận số nguyên |
| `!5` | **Không** | `!` chỉ nhận boolean |
| `5 & true` | **Không** | Không có phép `&` giữa int và boolean |

Khi hai vế của `&`/`|`/`^` đều là boolean thì Java áp dụng logic boolean; khi cả hai là số nguyên thì áp dụng phép toán bit. Không có kiểu kết quả “vừa int vừa boolean”, và không chuyển ngầm hai miền này.

Với `Boolean` wrapper, cần nhớ phép logic có thể **unbox**, gây `NullPointerException` khi tham chiếu là null. Dùng điều kiện bảo vệ như `value != null && value` nếu cần.

## 7. Chương trình Java 17+ runnable

Tạo file **BitwiseVsBooleanDemo.java**:

~~~java
public final class BitwiseVsBooleanDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean result) {
        log.append(label);
        return result;
    }

    public static void main(String[] args) {
        int a = 0b1100;
        int b = 0b1010;
        System.out.println("bitAnd=" + (a & b));
        System.out.println("bitOr=" + (a | b));
        System.out.println("bitXor=" + (a ^ b));
        System.out.println("bitNot=" + (~a));
        System.out.println("bitNotLow4=" + ((~a) & 0b1111));

        final int READ = 0b0001;
        final int WRITE = 0b0010;
        final int EXEC = 0b0100;
        int flags = READ | EXEC;
        System.out.println("readAllowed=" + ((flags & READ) != 0));
        System.out.println("writeAllowed=" + ((flags & WRITE) != 0));
        System.out.println("hasReadExec="
                + ((flags & (READ | EXEC)) == (READ | EXEC)));
        System.out.println("setWrite=" + Integer.toBinaryString(flags | WRITE));

        boolean ready = true;
        boolean allowed = false;
        System.out.println("boolAnd=" + (ready & allowed));
        System.out.println("boolOr=" + (ready | allowed));
        System.out.println("boolXor=" + (ready ^ allowed));
        System.out.println("boolNot=" + (!ready));
        System.out.println("shortAnd=" + (ready && allowed));
        System.out.println("shortOr=" + (ready || allowed));

        StringBuilder trace = new StringBuilder();
        boolean scAnd = mark(trace, "F", false)
                && mark(trace, "X", true);
        boolean scOr = mark(trace, "T", true)
                || mark(trace, "Y", false);
        boolean eagerAnd = mark(trace, "A", false)
                & mark(trace, "B", true);
        boolean eagerOr = mark(trace, "C", true)
                | mark(trace, "D", false);
        boolean eagerXor = mark(trace, "E", true)
                ^ mark(trace, "G", true);
        System.out.println("scAnd=" + scAnd + ",scOr=" + scOr);
        System.out.println("eagerAnd=" + eagerAnd
                + ",eagerOr=" + eagerOr + ",eagerXor=" + eagerXor);
        System.out.println("trace=" + trace);

        int divisor = 0;
        System.out.println("divideGuard="
                + (divisor != 0 && 10 / divisor > 1));
        try {
            boolean error = divisor != 0 & 10 / divisor > 1;
            System.out.println("error=" + error);
        } catch (ArithmeticException e) {
            System.out.println("eagerDivide=ArithmeticException");
        }
    }
}
~~~

Chạy từ thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 BitwiseVsBooleanDemo.java
java BitwiseVsBooleanDemo
~~~

**Expected stdout chính xác:**

~~~text
bitAnd=8
bitOr=14
bitXor=6
bitNot=-13
bitNotLow4=3
readAllowed=true
writeAllowed=false
hasReadExec=true
setWrite=111
boolAnd=false
boolOr=true
boolXor=true
boolNot=false
shortAnd=false
shortOr=true
scAnd=false,scOr=true
eagerAnd=false,eagerOr=true,eagerXor=false
trace=FTABCDEG
divideGuard=false
eagerDivide=ArithmeticException
~~~

Để hiểu `trace=FTABCDEG`: `&&` bỏ qua X, `||` bỏ qua Y; còn `&`, `|`, `^` luôn chạy đủ hai vế. `divideGuard=false` không thực hiện phép chia, nhưng `eagerDivide` ném ngoại lệ vì `&` vẫn đánh giá vế phải.

## 8. Bài tập tự kiểm tra

**Bài 1.** Với `int a = 0b0110, b = 0b1010;`, tính `a & b`, `a | b`, `a ^ b` dưới dạng nhị phân 4 bit.

**Bài 2.** Cho `boolean a = true, b = false;`, dự đoán `a & b`, `a | b`, `a ^ b`, `!a`; phân biệt với các toán tử bit trên số.

**Bài 3.** Vì sao `if (flags & 0b0100)` không biên dịch? Viết lại để kiểm tra bit thứ hai (đếm từ bit 0).

**Bài 4.** Giải thích sự khác nhau giữa `false && check()` và `false & check()` nếu `check()` thay đổi biến hoặc ném ngoại lệ.

**Bài 5.** Viết điều kiện kiểm tra quyền READ **và** WRITE khi quyền lưu trong `int flags`. Phân biệt cách này với kiểm tra **ít nhất một** trong hai quyền.

### Ghi nhớ

**`&`, `|`, `^` có hai cách dùng tùy kiểu:** bitwise với số nguyên, logic không ngắn mạch với boolean. `~` chỉ đảo **bit số nguyên**, còn `!` chỉ phủ định **boolean**. `&&` và `||` chỉ dùng cho boolean và có short-circuit. Muốn biến kết quả bit mask thành điều kiện `if`, so sánh với 0 hoặc với mask, chẳng hạn `(flags & mask) != 0`.
