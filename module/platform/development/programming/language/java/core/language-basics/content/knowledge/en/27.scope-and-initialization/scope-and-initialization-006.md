# Kiểm tra biến đã được gán trên mọi nhánh trước khi sử dụng — Java 17+

## 1. Quy tắc definite assignment

Trong Java, **biến cục bộ phải chắc chắn đã được gán giá trị trước khi đọc** (*definite assignment*). Trình biên dịch phân tích các đường điều khiển có thể đi tới phép đọc, thay vì chỉ xét một lần chạy thử.

~~~java
static int choose(boolean flag) {
    int result;                 // Hợp lệ: chỉ khai báo.
    if (flag) {
        result = 10;
    } else {
        result = 20;
    }
    return result;              // Hợp lệ: cả hai nhánh đều gán.
}
~~~

Với `choose(true)`, kết quả là 10; với `choose(false)`, kết quả là 20. Ngược lại:

~~~java
// Không biên dịch nếu bỏ comment:
static int wrong(boolean flag) {
    int result;
    if (flag) {
        result = 10;
    }
    // return result; // variable result might not have been initialized
    return -1; // Dòng này chỉ để ví dụ vẫn biên dịch khi dòng sai bị comment.
}
~~~

**Điểm cốt lõi:** được phép **khai báo trước, gán sau**; nhưng ở mọi đường đi tới chỗ **đọc**, biến phải được gán chắc chắn.

## 2. Biến cục bộ không có giá trị mặc định

~~~java
int[] values = new int[2]; // Hai phần tử mặc định là 0.
int local;                 // Không tự động có giá trị 0.
// System.out.println(local); // Lỗi biên dịch: chưa gán.
local = 5;
System.out.println(local); // 5.
~~~

Phân biệt:

| Nơi lưu dữ liệu | Có giá trị mặc định? |
|---|---|
| Biến cục bộ `int x;` | **Không**; phải gán trước khi đọc |
| Tham số phương thức | Có giá trị do caller truyền vào khi lời gọi bắt đầu |
| Trường instance `int count;` | **Có**: mặc định 0 |
| Trường static `boolean ready;` | **Có**: mặc định false |
| Phần tử `new int[3]` | **Có**: các phần tử mặc định 0 |
| Biến cục bộ kiểu tham chiếu `String s;` | **Không**; không tự nhận null |
| Trường tham chiếu `String s;` | **Có**: mặc định null |

**Scope** (biến đang trong phạm vi) không đồng nghĩa với **definite assignment** (biến đã được gán chắc chắn).

## 3. `if/else`: phải xét mọi nhánh đi tới phép đọc

**Sai:**

~~~java
// static int bad(boolean active) {
//     int score;
//     if (active) score = 90;
//     return score; // Lỗi: active == false chưa gán.
// }
~~~

**Đúng — cả hai nhánh cùng gán:**

~~~java
static int score(boolean active) {
    int value;
    if (active) value = 90;
    else value = 0;
    return value;
}
~~~

**Đúng — khởi tạo trước rồi cập nhật có điều kiện:**

~~~java
int value = 0;
if (active) {
    value = 90;
}
System.out.println(value);
~~~

Trong đoạn sau, `value = 0` cung cấp giá trị cho mọi đường đi; `if` chỉ **ghi đè** khi điều kiện đúng. Hãy chọn cách biểu đạt đúng ý nghĩa dữ liệu, không gán số 0 chỉ để làm compiler hết báo lỗi nếu nghiệp vụ không cho phép số 0.

**Đúng — nhánh không gán thì kết thúc phương thức:**

~~~java
static int doublePositive(int input) {
    int result;
    if (input < 0) return -1;
    result = input * 2;
    return result;
}
~~~

Khi `input < 0`, không có đường đi tới `return result`. Vì vậy nhánh đó không cần gán `result`.

## 4. Nhiều nhánh và phép gán bằng biểu thức

Nếu có chuỗi `if / else if`, đừng quên tình huống **không nhánh nào đúng**.

~~~java
static String band(int n) {
    String result;
    if (n < 0) {
        result = "NEGATIVE";
    } else if (n == 0) {
        result = "ZERO";
    } else {
        result = "POSITIVE";
    }
    return result; // Mọi đường tới đây đã gán.
}
~~~

Nếu bỏ nhánh `else`, compiler không thể khẳng định `n > 0` cũng đã được gán.

Cũng có thể tạo giá trị trực tiếp bằng toán tử ba ngôi:

~~~java
int result = active ? 90 : 0;
~~~

Cả hai toán hạng kết quả cung cấp giá trị cho biểu thức; không cần tạo local chưa khởi tạo rồi tự chứng minh từng nhánh.

## 5. `switch`: dùng `default` hoặc switch expression hợp lệ

Với `switch statement`, các `case` có thể không bao phủ mọi giá trị:

~~~java
// static int badSwitch(int code) {
//     int result;
//     switch (code) {
//         case 1 -> result = 100;
//         case 2 -> result = 200;
//     }
//     return result; // Không chắc đã gán khi code khác 1,2.
// }
~~~

**Sửa bằng `default`:**

~~~java
static int statusCode(int code) {
    int result;
    switch (code) {
        case 1 -> result = 100;
        case 2 -> result = 200;
        default -> result = -1;
    }
    return result;
}
~~~

Hoặc dùng **switch expression** được Java 17 hỗ trợ:

~~~java
static int statusCodeExpression(int code) {
    return switch (code) {
        case 1 -> 100;
        case 2 -> 200;
        default -> -1;
    };
}
~~~

Switch expression bắt buộc cung cấp giá trị theo quy tắc exhaustiveness; với selector `int`, dùng `default` trong ví dụ giúp bao phủ các giá trị còn lại. Đừng lẫn **switch statement** với **switch expression**.

## 6. Vòng lặp: không mặc định body chắc chắn chạy

~~~java
// static int brokenLoop(boolean run) {
//     int result;
//     while (run) {
//         result = 7;
//         break;
//     }
//     return result; // Lỗi: while có thể có 0 lượt.
// }
~~~

Nếu điều kiện vòng lặp false ngay, phần thân không chạy và `result` chưa được gán.

**Cách rõ ràng nhất khi cần giá trị mặc định:**

~~~java
static int loopWithDefault(boolean run) {
    int result = -1;
    while (run) {
        result = 7;
        break;
    }
    return result;
}
~~~

Một vòng `while (true)` mà **mọi đường thoát qua `break` đều đã gán** cũng có thể chứng minh được definite assignment:

~~~java
static int fromLoop() {
    int result;
    while (true) {
        result = 7;
        break;
    }
    return result;
}
~~~

Trong ví dụ này, đường hoàn thành bình thường của vòng đi qua `result = 7` rồi mới `break`. Không suy rộng sang mọi vòng `while(true)`, nhất là khi có nhiều nhánh `break` hoặc ngoại lệ.

## 7. `try/catch`: mỗi đường tới sau khối đều cần gán

~~~java
static int parseOrDefault(boolean fail) {
    int result;
    try {
        if (fail) {
            throw new IllegalArgumentException("simulated");
        }
        result = 40;
    } catch (IllegalArgumentException ex) {
        result = -40;
    }
    return result;
}
~~~

Nếu `fail == false`, nhánh `try` gán 40; nếu `fail == true`, ngoại lệ được bắt và `catch` gán -40. Cả hai đường hoàn thành bình thường tới `return` đều đã gán.

**Lưu ý:** một `catch` không chắc luôn chạy; không nên cho rằng lệnh gán **chỉ trong catch** là đủ cho mọi đường đi. `finally` có quy tắc điều khiển luồng riêng; khi code phức tạp, nên giảm số nhánh hoặc khởi tạo kết quả ở nơi rõ ràng.

## 8. Biến `final`: gán đúng một lần trên từng đường thực thi

Biến cục bộ `final` chưa gán có thể được gán sau khi khai báo, nhưng không được **gán lại** sau khi đã gán:

~~~java
static int finalResult(boolean flag) {
    final int result;
    if (flag) {
        result = 1;
    } else {
        result = 2;
    }
    return result;
}
~~~

Các nhánh loại trừ nhau nên mỗi lần thực thi chỉ có một phép gán. Ngược lại, đoạn dưới không biên dịch:

~~~java
// final int x = 1;
// x = 2; // Lỗi: không thể gán lại final.
~~~

Kiểm tra *definite assignment* bảo đảm local đã được gán trước khi đọc; kiểm tra *definite unassignment* đối với `final` giúp tránh gán lại sai quy tắc. Hai vấn đề liên quan nhưng không giống nhau.

## 9. Chương trình Java 17+ chạy độc lập

Tạo đúng file **`DefiniteAssignmentDemo.java`**:

~~~java
public final class DefiniteAssignmentDemo {
    private static int field; // Giá trị mặc định là 0.

    private DefiniteAssignmentDemo() {}

    static int ifElse(boolean flag) {
        int result;
        if (flag) result = 10;
        else result = 20;
        return result;
    }

    static int earlyExit(int input) {
        int value;
        if (input < 0) return -1;
        if (input == 0) {
            throw new IllegalArgumentException("zero not allowed");
        }
        value = input * 2;
        return value;
    }

    static int switchValue(String mode) {
        int result = switch (mode) {
            case "FAST" -> 100;
            case "SLOW" -> 20;
            default -> 0;
        };
        return result;
    }

    static int loopValue() {
        int result;
        while (true) {
            result = 7;
            break;
        }
        return result;
    }

    static int tryCatch(boolean fail) {
        int result;
        try {
            if (fail) {
                throw new IllegalArgumentException("simulated");
            }
            result = 40;
        } catch (IllegalArgumentException ex) {
            result = -40;
        }
        return result;
    }

    static int finalOnce(boolean flag) {
        final int result;
        if (flag) result = 1;
        else result = 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println("field=" + field);
        System.out.println("if true=" + ifElse(true));
        System.out.println("if false=" + ifElse(false));

        System.out.println("early positive=" + earlyExit(3));
        System.out.println("early negative=" + earlyExit(-3));
        try {
            earlyExit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("early zero=" + ex.getMessage());
        }

        System.out.println("switch FAST=" + switchValue("FAST"));
        System.out.println("switch SLOW=" + switchValue("SLOW"));
        System.out.println("switch OTHER=" + switchValue("OTHER"));
        System.out.println("loop=" + loopValue());
        System.out.println("try normal=" + tryCatch(false));
        System.out.println("try catch=" + tryCatch(true));
        System.out.println("final true=" + finalOnce(true));
        System.out.println("final false=" + finalOnce(false));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; không cần thư viện ngoài hay preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
~~~

### Exact expected stdout

~~~text
field=0
if true=10
if false=20
early positive=6
early negative=-1
early zero=zero not allowed
switch FAST=100
switch SLOW=20
switch OTHER=0
loop=7
try normal=40
try catch=-40
final true=1
final false=2
~~~

Kết quả cho thấy biến local có thể khai báo rồi gán ở các nhánh, nhánh `return`/`throw` không cần gán cho code phía sau mà nó không thể tới, và field mặc định bằng 0 không đồng nghĩa local cũng bằng 0.

## 10. Lỗi thường gặp và bài tập

| Sai lầm | Vì sao lỗi? | Cách sửa |
|---|---|---|
| `int x; println(x);` | Local chưa được gán | Gán trước phép đọc |
| Chỉ gán `x` khi `if(flag)` | Nhánh false chưa gán | Thêm `else` hoặc mặc định |
| `if/else if` không bao phủ mọi nhánh | Có đường bỏ qua mọi phép gán | Thêm `else` hoặc đổi cấu trúc |
| `switch statement` thiếu nhánh bao phủ | Có selector không khớp `case` | Thêm `default` khi phù hợp |
| Chỉ gán trong `while` | Vòng có thể chạy 0 lượt | Gán mặc định hoặc chứng minh đường thoát |
| Chỉ gán trong `catch` | `catch` có thể không chạy | Xử lý cả đường `try` bình thường |
| Nghĩ local tự nhận 0/null như field | Local không có giá trị mặc định | Gán rõ ràng |
| Gán hai lần vào biến `final` | Vi phạm quy tắc final | Đảm bảo một lần trên từng đường |

**Bài A:** `int n; if (flag) n=1; else n=2; System.out.println(n);` hợp lệ không? **Có**, vì hai nhánh đã bao phủ mọi đường.

**Bài B:** `int n; if (flag) n=1; System.out.println(n);` hợp lệ không? **Không**, vì flag có thể false.

**Bài C:** `int n; if (flag) return; n=3; System.out.println(n);` trong phương thức `void` có hợp lệ không? **Có**, vì mọi đường tới `println` đều đã gán `n=3`.

**Bài D:** Có thể đọc `private int count;` của object trước khi gán tường minh không? **Có**, giá trị mặc định của field `int` là 0.

**Bài E:** Nếu `final int result;` được gán trong cả hai nhánh loại trừ nhau, có được không? **Có**, miễn biến chắc chắn được gán trước khi đọc và không bị gán lại trên cùng đường thực thi.

## 11. Checklist và kết luận

- [ ] Phân biệt **phạm vi tên biến** với **đã gán chắc chắn**.
- [ ] Biết local không có giá trị mặc định, khác field và phần tử mảng.
- [ ] Kiểm tra tất cả đường `if/else` có thể đi tới phép đọc.
- [ ] Biết `return` hoặc `throw` có thể chấm dứt một nhánh chưa gán.
- [ ] Hiểu `switch statement` và `switch expression` khác nhau.
- [ ] Không mặc định thân vòng lặp hoặc `catch` luôn được thực thi.
- [ ] Với `final`, kiểm soát cả gán trước khi đọc và không gán lại.
- [ ] Chạy `DefiniteAssignmentDemo.java` với JDK 17+, đối chiếu exact stdout.

**Kết luận:** Java 17 yêu cầu một biến cục bộ phải được **gán chắc chắn trên mọi đường thực thi có thể dẫn đến phép đọc**. Để code rõ và an toàn, hãy bao phủ các nhánh, dùng guard clause khi hợp lý, và phân biệt *definite assignment* với phạm vi biến cũng như giá trị mặc định của field.