# Phân biệt thứ tự nhóm biểu thức với thứ tự đánh giá trong Java

> **Java core — language-basics / Biểu thức**  
> **Yêu cầu:** Java 17+, một tệp Java độc lập; chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Phân biệt **cách nhóm biểu thức** (*grouping*) theo độ ưu tiên/tính kết hợp với **thứ tự thực thi các phép đánh giá** (*evaluation order*); tự dự đoán cả **kết quả** và **thứ tự tác dụng phụ** trong biểu thức Java.

## 1. Hai câu hỏi phải trả lời riêng

Với biểu thức:

~~~java
int result = 2 + 3 * 4;
~~~

- **Nhóm thế nào?** Toán tử `*` ưu tiên hơn `+` nên biểu thức được nhóm thành `2 + (3 * 4)`; kết quả bằng **14**.
- **Đánh giá các toán hạng theo thứ tự nào?** Java có quy tắc đánh giá riêng: với phép toán hai ngôi thông thường, **toán hạng trái được đánh giá trước toán hạng phải**. Đối với literal như ví dụ trên, không quan sát thấy khác biệt về tác dụng phụ; với lời gọi phương thức thì thấy rõ.

**Sai lầm phổ biến:** “`*` ưu tiên cao nên tất cả lời gọi phương thức quanh dấu `*` chạy trước lời gọi ở phía trái `+`”. Điều đó **không đúng**. Độ ưu tiên quyết định **cấu trúc biểu thức**, không tự đảo thứ tự gọi hàm.

## 2. Độ ưu tiên và tính kết hợp quyết định cách nhóm

| Biểu thức | Cách nhóm | Giá trị `int` |
| --- | --- | ---: |
| `2 + 3 * 4` | `2 + (3 * 4)` | 14 |
| `(2 + 3) * 4` | `(2 + 3) * 4` | 20 |
| `10 - 3 - 2` | `(10 - 3) - 2` | 5 |
| `10 - (3 - 2)` | `10 - (3 - 2)` | 9 |
| `24 / 4 / 2` | `(24 / 4) / 2` | 3 |
| `24 / (4 / 2)` | `24 / (4 / 2)` | 12 |

**Độ ưu tiên** giải thích vì sao `*` được nhóm sát toán hạng hơn `+`. **Tính kết hợp** (*associativity*) giải thích vì sao các toán tử cùng mức như `-` và `/` được nhóm từ **trái sang phải**. Các toán tử gán như `a = b = 5` nhóm từ **phải sang trái**: `a = (b = 5)`.

Dấu ngoặc thay đổi **cách nhóm**, từ đó có thể thay đổi kết quả. Nó không mặc nhiên biến mọi biểu thức thành “đánh giá toán hạng ở trong ngoặc trước mọi thứ nằm ngoài ngoặc”.

## 3. Java đánh giá các toán hạng: ví dụ ghi dấu vết

Tưởng tượng một hàm `step` ghi tên mỗi lần được gọi:

~~~java
static int step(StringBuilder log, String label, int value) {
    log.append(label);
    return value;
}
~~~

Biểu thức:

~~~java
var log = new StringBuilder();
int value = step(log, "A", 2)
        + step(log, "B", 3) * step(log, "C", 4);
~~~

được **nhóm** như:

~~~text
A + (B * C)
~~~

Nhưng các lời gọi `step` thực sự chạy theo thứ tự **A, B, C**, vì Java đánh giá toán hạng trái của phép `+` trước khi đánh giá toán hạng phải là biểu thức nhân. Khi tới vế phải, Java đánh giá B trước C. Kết quả bằng `2 + 3 * 4 = 14`.

Thay cách nhóm:

~~~java
log.setLength(0);
int changed = (step(log, "A", 2) + step(log, "B", 3))
        * step(log, "C", 4);
~~~

Thứ tự ghi dấu vẫn là **A, B, C**, còn kết quả chuyển thành **20** do dấu ngoặc làm đổi phép toán được nhóm.

**Phân biệt thật rõ:**

| Thuộc tính | `A() + B() * C()` | `(A() + B()) * C()` |
| --- | --- | --- |
| Cách nhóm | `A() + (B() * C())` | `(A() + B()) * C()` |
| Thứ tự lời gọi (đánh giá bình thường) | A → B → C | A → B → C |
| Kết quả nếu A=2, B=3, C=4 | 14 | 20 |

Quy tắc trái sang phải cũng áp dụng cho việc đánh giá các đối số phương thức: `print(computeA(), computeB())` đánh giá `computeA()` trước `computeB()`. Tuy nhiên, mỗi biểu thức con có thể chứa toán tử riêng và các nhánh đánh giá có điều kiện.

## 4. Tác dụng phụ giúp thấy thứ tự thực thi

Toán tử hậu tố `i++` **trả giá trị cũ rồi mới tăng biến**. Vì vậy:

~~~java
int i = 1;
int result = i++ + i++ * i++;
~~~

Java lấy ba toán hạng theo thứ tự trái → phải:

1. `i++` đầu trả **1**, i thành 2.
2. `i++` thứ hai trả **2**, i thành 3.
3. `i++` thứ ba trả **3**, i thành 4.

**Cách nhóm:** `1 + (2 * 3)` nên `result = 7`; sau đó `i = 4`. Không có chuyện phép nhân làm hai lần tăng ở bên phải chạy trước lần tăng ngoài cùng bên trái.

Đây là **bài tập nhận biết thứ tự**, không phải cách viết mã được khuyên dùng. Tránh gom nhiều `++` hoặc lời gọi có tác dụng phụ vào một biểu thức dài; chia thành câu lệnh riêng để dễ đọc và bảo trì.

## 5. Những toán tử đánh giá có điều kiện

Quy tắc **trái sang phải** không có nghĩa **mọi toán hạng hoặc nhánh đều được đánh giá**.

| Biểu thức | Thứ tự/nhánh thực sự đánh giá |
| --- | --- |
| `left && right` | Đánh giá left; chỉ đánh giá right nếu left là `true` |
| `left \|\| right` | Đánh giá left; chỉ đánh giá right nếu left là `false` |
| `condition ? yes : no` | Đánh giá condition, rồi **chỉ một** trong hai nhánh yes/no |
| `left & right` với boolean | Đánh giá **cả hai** vế, không short-circuit |
| `left \| right` với boolean | Đánh giá **cả hai** vế, không short-circuit |

Ví dụ:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
~~~

Kết quả là **false**, vì `name != null` sai và vế gọi `isBlank()` bị bỏ qua. Đổi thứ tự thành `!name.isBlank() && name != null` sẽ ném `NullPointerException`.

Dùng `&&`, `||` hoặc `?:` khi cần đánh giá theo điều kiện, và đừng dùng `&`/`|` thay cho `&&`/`||` nếu yêu cầu bỏ qua vế phải.

## 6. Chương trình Java 17+ runnable

Tạo file **GroupingVsEvaluationDemo.java**:

~~~java
public final class GroupingVsEvaluationDemo {
    private static int step(StringBuilder log, String label, int value) {
        log.append(label);
        return value;
    }

    private static boolean test(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("subtractLeft=" + (10 - 3 - 2));
        System.out.println("subtractRight=" + (10 - (3 - 2)));

        StringBuilder log = new StringBuilder();
        int first = step(log, "A", 2)
                + step(log, "B", 3) * step(log, "C", 4);
        System.out.println("firstValue=" + first);
        System.out.println("firstOrder=" + log);

        log.setLength(0);
        int second = (step(log, "A", 2) + step(log, "B", 3))
                * step(log, "C", 4);
        System.out.println("secondValue=" + second);
        System.out.println("secondOrder=" + log);

        log.setLength(0);
        int left = step(log, "A", 24) / step(log, "B", 4)
                / step(log, "C", 2);
        System.out.println("divisionLeft=" + left + ":" + log);

        log.setLength(0);
        int right = step(log, "A", 24)
                / (step(log, "B", 4) / step(log, "C", 2));
        System.out.println("divisionRight=" + right + ":" + log);

        int i = 1;
        int increments = i++ + i++ * i++;
        System.out.println("increments=" + increments);
        System.out.println("afterIncrements=" + i);

        StringBuilder checks = new StringBuilder();
        boolean and = test(checks, "F", false)
                && test(checks, "X", true);
        boolean or = test(checks, "T", true)
                || test(checks, "Y", false);
        int selected = test(checks, "Q", false)
                ? step(checks, "L", 100)
                : step(checks, "R", 200);
        boolean eager = test(checks, "E", false)
                & test(checks, "G", true);

        System.out.println("shortAnd=" + and);
        System.out.println("shortOr=" + or);
        System.out.println("selected=" + selected);
        System.out.println("eagerAnd=" + eager);
        System.out.println("conditionalTrace=" + checks);
    }
}
~~~

Tại thư mục chứa file, chạy bằng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 GroupingVsEvaluationDemo.java
java GroupingVsEvaluationDemo
~~~

**Expected output chính xác:**

~~~text
precedence=14
parentheses=20
subtractLeft=5
subtractRight=9
firstValue=14
firstOrder=ABC
secondValue=20
secondOrder=ABC
divisionLeft=3:ABC
divisionRight=12:ABC
increments=7
afterIncrements=4
shortAnd=false
shortOr=true
selected=200
eagerAnd=false
conditionalTrace=FTQREG
~~~

**Đối chiếu với mã:**

- Hai dòng `firstOrder`/`secondOrder` đều là `ABC`; nhưng cách nhóm khác nhau cho `firstValue=14` và `secondValue=20`.
- `divisionLeft` và `divisionRight` đều gọi A, B, C theo thứ tự đó; kết quả 3 và 12 khác vì nhóm phép chia khác.
- `increments=7`, `afterIncrements=4` xác nhận các lần `i++` được đánh giá trái → phải.
- Dấu vết `FTQREG`: F=false nên X bị bỏ qua; T=true nên Y bị bỏ qua; Q=false nên chỉ nhánh R chạy; cuối cùng cả E và G đều chạy vì boolean `&` không short-circuit.

## 7. Sai lầm thường gặp và cách đọc biểu thức

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Nhân ưu tiên cao nên `B()`/`C()` chạy trước `A()` trong `A() + B() * C()`.” | Sai: phép nhân được **nhóm** với nhau, còn lời gọi thường chạy A → B → C |
| “Tính kết hợp trái → phải nghĩa là mọi phép tính chỉ chạy từ trái sang phải.” | Sai: kết hợp nói về **cây biểu thức**; thứ tự đánh giá có quy tắc riêng |
| “Có ngoặc thì lời gọi trong ngoặc luôn chạy đầu tiên.” | Sai: trong `A() + (B() * C())`, A vẫn được đánh giá trước B và C |
| “`&&` luôn đánh giá cả hai vế.” | Sai: vế phải có thể bị bỏ qua |
| “`&` và `&&` tương đương cho mọi boolean.” | Sai khi có lỗi hoặc side effect trong vế phải |
| “Có thể thoải mái viết nhiều `i++` trong biểu thức vì Java quy định rõ thứ tự.” | Hợp lệ nhưng khó đọc; nên tách thao tác có side effect |

**Quy trình tự kiểm tra:** (1) viết lại cách nhóm với ngoặc; (2) tìm các toán hạng có tác dụng phụ; (3) áp dụng thứ tự đánh giá và quy tắc bỏ qua nhánh; (4) tính giá trị; (5) đối chiếu trạng thái biến sau cùng.

## 8. Bài tập

**Bài 1.** Tính `3 + 4 * 5` và `(3 + 4) * 5`. Giải thích thứ tự nhóm, không dùng lập luận “toán tử nào chạy trước” để thay thế.

**Bài 2.** Một hàm `mark("X")` ghi X và trả giá trị. Dự đoán chuỗi log của `mark("A") + mark("B") * mark("C")` khi các hàm chỉ trả số nguyên, và nhóm của phép tính.

**Bài 3.** Cho `int i = 1; int result = i++ + i++ * i++;`. Dự đoán `result` và giá trị cuối của `i`; đề xuất cách tách mã tránh side effect chồng nhau.

**Bài 4.** Với `boolean a = false;` và một hàm ghi log, so sánh `a && logCall()` với `a & logCall()`. Trường hợp nào chạy `logCall()`?

**Bài 5.** Viết hai biểu thức `24 / 4 / 2` và `24 / (4 / 2)` bằng các lời gọi `step` và chứng minh log vẫn là ABC dù hai kết quả khác nhau.

### Ghi nhớ

**Nhóm biểu thức** trả lời “toán tử áp dụng lên biểu thức con nào?”, còn **thứ tự đánh giá** trả lời “toán hạng/lời gọi/side effect nào được thực hiện trước?”. Trong Java, toán hạng của phép toán thông thường được đánh giá từ trái sang phải; `&&`, `||` và `?:` có thể bỏ qua vế hoặc nhánh. Phân tích **cả hai** quy tắc khi đọc biểu thức có phép tính lẫn tác dụng phụ; dùng ngoặc và tách biến trung gian để mã dễ hiểu.
