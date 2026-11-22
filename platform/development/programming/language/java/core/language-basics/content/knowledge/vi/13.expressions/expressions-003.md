# Độ ưu tiên và tính kết hợp của toán tử trong Java

> **Java core — language-basics / Biểu thức**  
> **Môi trường:** JDK 17+, chỉ cần Java standard library.  
> **Mục tiêu:** Đọc đúng cách Java nhóm biểu thức dựa trên **độ ưu tiên** (*precedence*) và **tính kết hợp** (*associativity*), phân biệt chúng với **thứ tự đánh giá toán hạng** (*evaluation order*), đồng thời dùng dấu ngoặc để code rõ nghĩa.

## 1. Ba khái niệm khác nhau

Cho biểu thức:

~~~java
int result = 2 + 3 * 4;
~~~

Kết quả là **14**, không phải 20, vì `*` có độ ưu tiên cao hơn `+`: biểu thức được hiểu là `2 + (3 * 4)`.

Cần phân biệt ba quy tắc:

- **Độ ưu tiên:** Khi không có ngoặc, toán tử ở mức ưu tiên cao hơn nhóm với toán hạng của nó trước. Ví dụ `a + b * c` được nhóm như `a + (b * c)`.
- **Tính kết hợp:** Khi nhiều toán tử ở cùng mức ưu tiên, quy tắc kết hợp xác định **cách nhóm**. Ví dụ `a - b - c` nhóm từ trái: `(a - b) - c`; còn `a = b = c` nhóm từ phải: `a = (b = c)`.
- **Thứ tự đánh giá:** Java đánh giá các toán hạng từ **trái sang phải** (kèm quy tắc đặc biệt của các toán tử đánh giá có điều kiện). Điều này **không đồng nghĩa** Java luôn tính toán tử ở bên trái trước.

Ví dụ có dấu ngoặc:

~~~java
int first = 2 + 3 * 4;   // 14
int second = (2 + 3) * 4; // 20
~~~

Dấu ngoặc thay đổi **cách nhóm**, giúp người đọc không phải tự nhớ toàn bộ bảng ưu tiên.

## 2. Bảng độ ưu tiên các toán tử thường gặp

Bảng theo thứ tự **cao → thấp**. Đây là bảng học tập cho các biểu thức phổ biến trong Java 17; một số cấu trúc ngữ pháp đặc biệt (như lambda) không được xem là phép toán số học trong bảng.

| Mức | Nhóm/toán tử | Tính kết hợp hoặc ghi chú |
| --- | --- | --- |
| 1 (cao nhất) | Truy cập `.`, `[]`, lời gọi `()`, hậu tố `x++`, `x--` | Gắn với biểu thức nhận/toán hạng |
| 2 | Tiền tố `++x`, `--x`, `+x`, `-x`, `!`, `~`, cast `(Type) x` | Toán tử một ngôi, nhóm từ phải |
| 3 | `*`, `/`, `%` | Trái → phải |
| 4 | `+`, `-` | Trái → phải; `+` cũng có thể nối chuỗi |
| 5 | `<<`, `>>`, `>>>` | Trái → phải |
| 6 | `<`, `<=`, `>`, `>=`, `instanceof` | So sánh/kiểm tra kiểu |
| 7 | `==`, `!=` | Bằng/khác |
| 8 | `&` | Bitwise AND hoặc boolean AND không short-circuit |
| 9 | `^` | Bitwise XOR hoặc boolean XOR |
| 10 | `\|` | Bitwise OR hoặc boolean OR không short-circuit |
| 11 | `&&` | AND logic, short-circuit |
| 12 | `\|\|` | OR logic, short-circuit |
| 13 | `? :` | Toán tử điều kiện, nhóm từ phải |
| 14 (thấp nhất) | `=`, `+=`, `-=`, `*=`, `/=`, v.v. | Các phép gán, nhóm từ phải |

**Ví dụ nhớ nhanh:**

~~~java
boolean ok = 3 + 2 > 4 && 2 * 3 == 6;
// Tương đương về cách nhóm:
// boolean ok = ((3 + 2) > 4) && ((2 * 3) == 6);
// ok = true.
~~~

`==` có ưu tiên **cao hơn** boolean `&` và `&&`. `&&` lại có ưu tiên **cao hơn** `||`. Với biểu thức phức tạp, thêm ngoặc theo ý định nghiệp vụ thay vì dựa vào trực giác.

**Lưu ý về `<<`:** `1 + 2 << 2` nhóm thành `(1 + 2) << 2` nên kết quả **12**, chứ không phải `1 + (2 << 2)` (9).

## 3. Tính kết hợp: cùng mức thì nhóm về phía nào?

Các phép toán số học hai ngôi phổ biến như `+`, `-`, `*`, `/` nhóm **trái → phải** khi cùng mức:

~~~java
int a = 20 / 5 * 2;     // (20 / 5) * 2 = 8.
int b = 20 / (5 * 2);   // 20 / 10 = 2.
int c = 10 - 3 - 2;     // (10 - 3) - 2 = 5.
~~~

Tính kết hợp đặc biệt quan trọng khi toán tử **không có tính giao hoán hoặc kết hợp toán học phù hợp**, chẳng hạn trừ, chia, nối chuỗi và phép toán có thể tràn.

Ngược lại, **phép gán kết hợp từ phải sang trái**:

~~~java
int x, y;
x = y = 7; // x = (y = 7), cuối cùng x == 7 và y == 7.
~~~

Biểu thức điều kiện lồng nhau cũng nhóm từ phải:

~~~java
int selected = false ? 10 : true ? 20 : 30;
// Nhóm như: false ? 10 : (true ? 20 : 30)
// selected = 20.
~~~

**Cẩn thận:** Tính kết hợp quyết định **cấu trúc cú pháp**, không quyết định một lời gọi phương thức nào được chạy trước nếu các toán hạng chứa side effect. Quy tắc đánh giá của Java vẫn phải được xem riêng.

## 4. Nhóm phép toán không đảo thứ tự gọi method

Trong `left() + middle() * right()`, phép nhân được nhóm bên trong toán hạng phải của phép cộng; tuy nhiên Java đánh giá lời gọi `left()` trước `middle()` rồi `right()` nếu không có ngoại lệ. Các vế không nhất thiết đều chạy: `&&`, `||` và `?:` có quy tắc bỏ qua nhánh.

~~~java
static int mark(StringBuilder log, String name, int value) {
    log.append(name);
    return value;
}
// Trong một method:
StringBuilder log = new StringBuilder();
int result = mark(log, "A", 1) + mark(log, "B", 2) * mark(log, "C", 3);
// result = 7; log.toString() = "ABC"
~~~

Bảng ưu tiên ở trên giúp xác định **cây nhóm**; dấu vết thực thi giúp xác định **thứ tự đánh giá**. Hai kiểm tra này độc lập.

## 5. Toán tử logic: độ ưu tiên và short-circuit

`&&` ưu tiên cao hơn `||`, nên:

~~~java
boolean value = true || false && false;
// Nhóm như: true || (false && false)
// value = true.
~~~

Với `&&`, nếu vế trái false, Java **không chạy vế phải**. Với `||`, nếu vế trái true, Java **không chạy vế phải**:

~~~java
int zero = 0;
boolean noDivide = false && (10 / zero > 1); // false, không chia 0.
boolean noDivideEither = true || (10 / zero > 1); // true.
~~~

Trái lại, boolean `&` và `|` **không short-circuit**: chúng đánh giá cả hai vế. Ví dụ `false & (10 / zero > 1)` sẽ ném `ArithmeticException` do phép chia cho 0.

**Chọn toán tử theo ý định:**

| Ý định | Toán tử | Đánh giá vế phải? |
| --- | --- | --- |
| AND logic, bỏ qua vế sau khi false | `&&` | Chỉ nếu vế trái true |
| OR logic, bỏ qua vế sau khi true | `\|\|` | Chỉ nếu vế trái false |
| AND boolean bắt buộc xét cả hai | `&` | Luôn |
| OR boolean bắt buộc xét cả hai | `\|` | Luôn |

Khi kiểm tra null, thứ tự guard phải đúng:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank(); // false, an toàn.
// boolean bad = !name.isBlank() && name != null; // NPE.
~~~

## 6. Một số bẫy trong biểu thức

| Biểu thức | Cách hiểu chính xác |
| --- | --- |
| `1 + 2 << 2` | `(1 + 2) << 2` = 12 |
| `10 - 3 - 2` | `(10 - 3) - 2` = 5 |
| `20 / 5 * 2` | `(20 / 5) * 2` = 8 |
| `true \|\| false && false` | `true \|\| (false && false)` = true |
| `1 \| 2 & 3` | `1 \| (2 & 3)` = 3 |
| `"sum=" + 1 + 2` | Nối chuỗi từ trái → phải = `"sum=12"` |
| `"sum=" + (1 + 2)` | Cộng số trong ngoặc trước = `"sum=3"` |
| `false ? 10 : true ? 20 : 30` | `false ? 10 : (true ? 20 : 30)` = 20 |

Dấu ngoặc vừa giúp chống lỗi vừa là tài liệu về ý đồ của lập trình viên. Tuy nhiên, đừng thêm ngoặc bừa bãi vào biểu thức nhiều side effect với giả định rằng nó sẽ đảo thứ tự đánh giá lời gọi hàm.

## 7. Chương trình Java 17+ runnable

Tạo tệp **OperatorPrecedenceDemo.java**:

~~~java
public final class OperatorPrecedenceDemo {
    private static int mark(StringBuilder order, String label, int value) {
        order.append(label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("leftAssociative=" + (20 / 5 * 2));
        System.out.println("rightGrouped=" + (20 / (5 * 2)));
        System.out.println("subtraction=" + (10 - 3 - 2));
        System.out.println("shift=" + (1 + 2 << 2));
        System.out.println("relational="
                + (3 + 2 > 4 && 2 * 3 == 6));
        System.out.println("andOr=" + (true || false && false));
        System.out.println("bitwise=" + (1 | 2 & 3));

        StringBuilder order = new StringBuilder();
        int evaluated = mark(order, "A", 1)
                + mark(order, "B", 2) * mark(order, "C", 3);
        System.out.println("operandOrder=" + order);
        System.out.println("operandValue=" + evaluated);

        int zero = 0;
        boolean shortAnd = false && (10 / zero > 1);
        boolean shortOr = true || (10 / zero > 1);
        System.out.println("shortCircuit=" + shortAnd + "," + shortOr);

        try {
            boolean evaluatedBoth = false & (10 / zero > 1);
            System.out.println("eagerResult=" + evaluatedBoth);
        } catch (ArithmeticException ex) {
            System.out.println("eagerAndThrows=true");
        }

        int x, y;
        x = y = 7;
        System.out.println("assignment=" + x + "," + y);

        int selected = false ? 10 : true ? 20 : 30;
        System.out.println("conditional=" + selected);

        System.out.println("concat=" + ("" + 1 + 2)
                + "," + (1 + 2));
    }
}
~~~

Biên dịch/chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 OperatorPrecedenceDemo.java
java OperatorPrecedenceDemo
~~~

**Expected output chính xác:**

~~~text
precedence=14
parentheses=20
leftAssociative=8
rightGrouped=2
subtraction=5
shift=12
relational=true
andOr=true
bitwise=3
operandOrder=ABC
operandValue=7
shortCircuit=false,true
eagerAndThrows=true
assignment=7,7
conditional=20
concat=12,3
~~~

Dòng `operandOrder=ABC` minh họa **thứ tự thực thi lời gọi từ trái qua phải**, dù `*` ưu tiên `+`. `eagerAndThrows=true` chỉ ra khác biệt giữa `&` với `&&` cho toán hạng boolean. `assignment=7,7` và `conditional=20` minh họa cách **nhóm từ phải**.

## 8. Bài tập và quy tắc viết mã dễ đọc

**Bài 1.** Tính `5 + 2 * 3` và `(5 + 2) * 3`. Giải thích vì sao kết quả khác.

**Bài 2.** Tính `24 / 4 / 2` và `24 / (4 / 2)`. Toán tử `/` có tính kết hợp theo hướng nào?

**Bài 3.** Dự đoán `1 + 2 << 2`. Viết lại bằng ngoặc để không cần tra bảng ưu tiên.

**Bài 4.** Cho `int z = 0;`. Dự đoán hành vi `false && (10 / z > 0)`, `true || (10 / z > 0)` và `false & (10 / z > 0)`.

**Bài 5.** Viết `int a, b; a = b = 5;` và giải thích vì sao gán từ phải không có nghĩa mọi toán hạng nói chung đều được thực thi từ phải sang trái.

**Bài 6.** Dùng hàm ghi log hoặc in ra tên trong ba toán hạng để chứng minh `methodA() + methodB() * methodC()` gọi các method theo thứ tự A, B, C.

**Nguyên tắc:** Với công thức toán học hoặc logic dài, đặt ngoặc ở những chỗ **ý đồ nhóm biểu thức cần được thể hiện rõ**. Không trông cậy vào cách “đọc từ trái sang phải” để quyết định ưu tiên; đồng thời tránh nhầm ưu tiên/kết hợp với thứ tự chạy của lời gọi có side effect.

### Ghi nhớ

**Độ ưu tiên** quyết định cách nhóm toán tử khác mức; **tính kết hợp** quyết định cách nhóm toán tử cùng mức; **thứ tự đánh giá** của Java là quy tắc riêng, thông thường thực hiện các toán hạng từ trái sang phải. `&&`/`||` và `?:` có thể bỏ qua nhánh không cần đánh giá. Dùng dấu ngoặc để viết rõ nghĩa, đặc biệt khi trộn số học, dịch bit, so sánh, logic và phép gán.
