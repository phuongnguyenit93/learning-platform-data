# Giữ phạm vi biến nhỏ và khai báo gần nơi sử dụng trong Java

> **Java core — language-basics / Phạm vi và khởi tạo**  
> **Môi trường:** Java 17+, ví dụ trong một file, chỉ cần JDK.  
> **Mục tiêu:** Khai báo biến tại nơi bắt đầu cần dùng, giới hạn phạm vi của chúng trong khối/nhánh/vòng lặp phù hợp, tránh sử dụng nhầm trạng thái cũ và phân biệt phạm vi (*scope*) với quy tắc phải gán giá trị trước khi đọc (*definite assignment*).

## 1. Nguyên tắc: phạm vi nhỏ nhất nhưng đủ dùng

*Scope* là vùng mã nguồn mà tên biến có hiệu lực. Với biến cục bộ khai báo trong khối `{ ... }`, tên thường có hiệu lực từ vị trí khai báo đến cuối khối. Vì vậy, **khai báo gần lần dùng đầu tiên** giúp người đọc thấy rõ ý nghĩa và tránh kéo dài phạm vi của biến không cần thiết.

~~~java
static void example(int score) {
    System.out.println("received=" + score);

    if (score >= 60) {
        String message = "PASS"; // Chỉ cần trong nhánh này.
        System.out.println(message);
    }

    // System.out.println(message); // Không biên dịch: hết scope.
}
~~~

**Quy tắc thực hành:** Nếu một giá trị chỉ được dùng trong một nhánh, đặt biến trong nhánh. Nếu chỉ dùng trong một lần lặp, đặt nó trong thân lặp. Nếu kết quả phải được dùng sau vòng lặp, khai báo **biến tích lũy/kết quả** ngoài vòng lặp.

Không nên biến quy tắc này thành “nhồi mọi thứ vào một dòng”. Cần đủ chỗ cho tên có nghĩa, các bước kiểm tra rõ ràng, và không ép một biểu thức phức tạp trở nên khó đọc.

## 2. Trước và sau: tránh khai báo quá sớm

**Trước — biến sống trong phạm vi rộng hơn nhu cầu:**

~~~java
static String oldStatus(boolean enabled, int score) {
    String result = "";
    String label = "";
    if (enabled) {
        label = score >= 60 ? "PASS" : "RETRY";
        result = label + ":" + score;
    } else {
        result = "SKIPPED";
    }
    return result;
}
~~~

**Sau — đưa biến vào nhánh cần dùng, trả kết quả sớm:**

~~~java
static String status(boolean enabled, int score) {
    if (!enabled) {
        return "SKIPPED";
    }

    String label = score >= 60 ? "PASS" : "RETRY";
    return label + ":" + score;
}
~~~

Hai phiên bản trả cùng kết quả ở các đầu vào ví dụ, nhưng bản sau không phải duy trì `result` và `label` từ trước khi biết có dùng chúng hay không.

- `label` chỉ tồn tại trong phần còn lại của phương thức sau nhánh `return` sớm; nó không xuất hiện trong nhánh không kích hoạt.
- Nếu giá trị trung gian được dùng ở nhiều nhánh, nên chọn khối chung phù hợp thay vì sao chép tính toán vô ích.
- Một phương thức ngắn, tên biến có nghĩa và kiểm tra đầu vào rõ ràng quan trọng hơn việc giảm số ký tự.

## 3. Khối `if`/`else`: đặt biến nơi thật sự cần

~~~java
static String classify(int number) {
    String result;
    if (number < 0) {
        result = "NEG";
    } else if (number == 0) {
        result = "ZERO";
    } else {
        result = "POS";
    }
    return result;
}
~~~

`result` phải ở ngoài các nhánh vì dùng sau chuỗi `if`/`else`. Đây là **phạm vi rộng có lý do**, không phải lỗi thiết kế. Mỗi nhánh gán giá trị nên Java có thể chứng minh `result` đã được gán trước `return`.

Nếu mỗi nhánh có thể trả về ngay, ta có thể tránh biến `result`:

~~~java
static String classifyDirect(int number) {
    if (number < 0) return "NEG";
    if (number == 0) return "ZERO";
    return "POS";
}
~~~

Trường hợp không biên dịch vì thiếu gán:

~~~java
// KHÔNG BIÊN DỊCH:
// static int broken(boolean flag) {
//     int value;
//     if (flag) value = 5;
//     return value; // flag=false nên value chưa chắc đã gán.
// }
~~~

**Phân biệt:** Biến `value` đã nằm trong *scope* tại `return`, nhưng **chưa đạt definite assignment**. Thêm `else` hợp lý, giá trị mặc định có chủ đích hoặc thay đổi cấu trúc trả về để sửa.

## 4. Vòng `for`: giới hạn biến điều khiển và biến tạm

Khi không cần sử dụng chỉ số sau vòng lặp, khai báo nó ngay trong phần khởi tạo `for`:

~~~java
int sum = 0; // Kết quả cần sau vòng, nên đặt ngoài.
for (int i = 1; i <= 4; i++) {
    int square = i * i; // Chỉ phục vụ lần lặp hiện tại.
    sum += square;
}
System.out.println(sum); // 30.
// System.out.println(i);      // Lỗi: i ngoài scope.
// System.out.println(square); // Lỗi: square ngoài scope.
~~~

Mỗi lần lặp chạy thân, phép khởi tạo `square = i * i` được thực hiện với chỉ số hiện tại. Không nên đưa `square` ra ngoài `for` nếu không có nhu cầu sử dụng ngoài vòng.

Enhanced `for` cũng có biến phần tử chỉ có hiệu lực trong thân vòng:

~~~java
static int sumPositiveTwice(int[] values) {
    int total = 0; // Cần qua nhiều lần lặp.
    for (int number : values) {
        if (number <= 0) {
            continue;
        }
        int contribution = number * 2; // Dùng cho lần lặp này.
        total += contribution;
    }
    return total;
}
~~~

Với `{2, -1, 3, 0, 5}`, tổng là `(2 + 3 + 5) * 2 = 20`. Biến `contribution` chỉ được khởi tạo khi số dương; tránh tạo một biến trống rồi gán lại ở mọi nhánh.

**Ngoại lệ hợp lý:** Nếu cần dùng chỉ số sau vòng để báo vị trí kết thúc hoặc tái sử dụng một đối tượng có chi phí tạo lớn, có thể khai báo bên ngoài; nhưng cần nói rõ lý do và không vô tình giữ trạng thái cũ giữa các lần lặp.

## 5. `while`, duyệt mảng và kiểm tra đầu vào

Với vòng `while`, biến điều khiển có thể cần dùng cả sau vòng:

~~~java
int steps = 0;
while (steps < 3) {
    int nextStep = steps + 1;
    System.out.println("step=" + nextStep);
    steps++;
}
System.out.println("done=" + steps);
~~~

`steps` ở ngoài vì dùng trong điều kiện và sau vòng. `nextStep` chỉ phục vụ phần thân, nên khai báo trong thân.

Khi duyệt mảng chuỗi, đặt biến chuyển đổi **sau kiểm tra null**, ngay trước khi sử dụng:

~~~java
static String firstNonBlank(String[] values) {
    for (String value : values) {
        if (value == null) {
            continue;
        }
        String normalized = value.trim();
        if (!normalized.isEmpty()) {
            return normalized;
        }
    }
    return "NONE";
}
~~~

`normalized` không bị tạo khi `value == null`; nó chỉ tồn tại trong thân vòng lặp sau điểm khai báo. `firstNonBlank` ở trên yêu cầu đối số mảng khác null; nếu hợp đồng cho phép mảng null, hãy kiểm tra thêm ở đầu phương thức.

Để lấy thông tin sau vòng, trả trực tiếp khi tìm được là hợp lý; không cần giữ biến `found` từ đầu nếu chỉ cần kết quả đầu tiên.

## 6. Scope nhỏ không tự làm khai báo trùng tên hợp lệ

Hai khối ngang hàng có thể dùng lại local `attempt`; khai báo `attempt` lần nữa trong khối lồng khi local bên ngoài còn trong scope vẫn là lỗi:

~~~java
{
    int attempt = 1;
    System.out.println(attempt);
}
{
    int attempt = 2; // Hợp lệ: phạm vi trước đã hết.
    System.out.println(attempt);
}
~~~

Khi local trùng tên field, Java cho phép *shadowing*, nhưng phải phân biệt tên ngắn với `this.field` hoặc `ClassName.staticField`. Trong mã dễ bảo trì, ưu tiên tên thể hiện đúng mục đích và phạm vi nhỏ; các quy tắc khai báo trùng và shadowing vẫn phải được tuân thủ.

## 7. `final`, `var` và ranh giới của lời khuyên

Trong Java 17, `final` và `var` có thể giúp ý định của biến rõ hơn nhưng **không thay đổi quy tắc phạm vi**:

~~~java
static String upper(String raw) {
    if (raw == null) return "MISSING";

    final String cleaned = raw.trim();
    if (cleaned.isEmpty()) return "EMPTY";

    var result = cleaned.toUpperCase(java.util.Locale.ROOT);
    return result;
}
~~~

- `final` cấm gán lại `cleaned` sau khi đã gán, không tự làm đối tượng được tham chiếu trở nên bất biến và không nới rộng scope.
- `var` suy luận kiểu biến cục bộ từ biểu thức khởi tạo; `result` vẫn có phạm vi như local thông thường. Không thể dùng `var x;` mà không có initializer.
- Nếu kiểu không rõ khi đọc biểu thức khởi tạo, khai báo tường minh như `String result = ...` thường dễ hiểu hơn.
- Không đưa mọi kết quả trung gian thành field hay biến static chỉ để “dùng được ở khắp nơi”: đó là thay đổi trạng thái/chế độ chia sẻ dữ liệu, không phải đơn giản hóa phạm vi.

*Scope* chỉ nói **vị trí tên có thể được tham chiếu**. Đối tượng được biến local trỏ tới vẫn có thể sống tiếp nếu có tham chiếu khác sau khi local hết scope; dấu `}` không quyết định thời điểm garbage collection.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **SmallScopeDemo.java**:

~~~java
import java.util.Locale;

public final class SmallScopeDemo {
    private static String status(boolean enabled, int score) {
        if (!enabled) {
            return "SKIPPED";
        }
        String label = score >= 60 ? "PASS" : "RETRY";
        return label + ":" + score;
    }

    private static int sumPositiveTwice(int[] values) {
        int total = 0;
        for (int number : values) {
            if (number <= 0) {
                continue;
            }
            int contribution = number * 2;
            total += contribution;
        }
        return total;
    }

    private static int squareSum(int limit) {
        int sum = 0;
        for (int i = 1; i <= limit; i++) {
            int square = i * i;
            sum += square;
        }
        return sum;
    }

    private static String firstNonBlank(String[] values) {
        for (String value : values) {
            if (value == null) {
                continue;
            }
            String normalized = value.trim();
            if (!normalized.isEmpty()) {
                return normalized;
            }
        }
        return "NONE";
    }

    private static String classify(int number) {
        String result;
        if (number < 0) {
            result = "NEG";
        } else if (number == 0) {
            result = "ZERO";
        } else {
            result = "POS";
        }
        return result;
    }

    private static String upper(String raw) {
        if (raw == null) {
            return "MISSING";
        }
        final String cleaned = raw.trim();
        if (cleaned.isEmpty()) {
            return "EMPTY";
        }
        var result = cleaned.toUpperCase(Locale.ROOT);
        return result;
    }

    public static void main(String[] args) {
        System.out.println("statusOff=" + status(false, 78));
        System.out.println("statusPass=" + status(true, 78));
        System.out.println("statusRetry=" + status(true, 42));

        System.out.println("positiveTwice="
                + sumPositiveTwice(new int[] {2, -1, 3, 0, 5}));
        System.out.println("positiveEmpty="
                + sumPositiveTwice(new int[0]));
        System.out.println("squareSum=" + squareSum(4));

        System.out.println("firstNonBlank=" + firstNonBlank(
                new String[] {" ", null, " Java ", "Other"}));
        System.out.println("firstMissing=" + firstNonBlank(
                new String[] {null, "   "}));

        System.out.println("negative=" + classify(-2));
        System.out.println("zero=" + classify(0));
        System.out.println("positive=" + classify(9));

        System.out.println("upper=" + upper(" java "));
        System.out.println("upperEmpty=" + upper("   "));
        System.out.println("upperMissing=" + upper(null));

        {
            int attempt = 1;
            System.out.println("firstBlock=" + attempt);
        }
        {
            int attempt = 2;
            System.out.println("secondBlock=" + attempt);
        }

        int steps = 0;
        while (steps < 3) {
            int nextStep = steps + 1;
            System.out.println("step=" + nextStep);
            steps++;
        }
        System.out.println("done=" + steps);
    }
}
~~~

Biên dịch/chạy tại thư mục chứa file (PowerShell, Command Prompt hoặc Bash):

~~~bash
javac -encoding UTF-8 SmallScopeDemo.java
java SmallScopeDemo
~~~

**Expected stdout chính xác:**

~~~text
statusOff=SKIPPED
statusPass=PASS:78
statusRetry=RETRY:42
positiveTwice=20
positiveEmpty=0
squareSum=30
firstNonBlank=Java
firstMissing=NONE
negative=NEG
zero=ZERO
positive=POS
upper=JAVA
upperEmpty=EMPTY
upperMissing=MISSING
firstBlock=1
secondBlock=2
step=1
step=2
step=3
done=3
~~~

Các phương thức `status`, `firstNonBlank` và `upper` chỉ khai báo biến khi thực sự cần. `sumPositiveTwice` và `squareSum` đặt biến tích lũy bên ngoài vòng nhưng biến tạm bên trong. `attempt` được phép khai báo hai lần ở hai khối không chồng scope. `steps` vẫn có thể đọc sau vòng vì đã khai báo bên ngoài.

## 9. Lỗi phổ biến, checklist và bài tập

| Dấu hiệu | Điều chỉnh phù hợp |
| --- | --- |
| Khai báo nhiều biến ở đầu phương thức, mãi sau mới dùng | Đưa khai báo về gần lần dùng đầu |
| Biến chỉ dùng trong một nhánh `if` nhưng nằm ngoài | Đưa vào nhánh nếu không cần kết quả sau nhánh |
| Biến tạm chỉ dùng cho một lượt lặp nhưng đặt ngoài `for` | Khai báo và khởi tạo bên trong thân vòng |
| Cần tổng/số đếm sau vòng nhưng khai báo bên trong | Đưa accumulator ra khối bao ngoài |
| Dùng biến `i` sau `for (int i = ...)` | Nếu thật sự cần, khai báo `i` trước vòng; nếu không, dùng kết quả riêng |
| Local còn scope bị khai báo lại trong khối con | Đổi tên hoặc bố trí lại các khối |
| Biến đã trong scope nhưng chưa chắc có giá trị | Sửa *definite assignment* ở mọi đường đi |
| Dùng field/static để tránh giới hạn scope của local | Cân nhắc tham số/giá trị trả về trước khi mở rộng trạng thái chia sẻ |

**Bài 1.** Viết hàm đếm số chẵn trong `int[]`, chỉ khai báo biến `even` ở nơi cần dùng và giữ biến `count` đủ rộng để trả về cuối vòng.

**Bài 2.** Viết hàm tìm chuỗi đầu tiên không trống trong `String[]`, tránh giữ biến `normalized` ngoài vòng lặp. Vì sao cần kiểm tra null trước `trim()`?

**Bài 3.** Với hai nhánh `if` gán cho một kết quả chung, thử đặt biến `result` trong nhánh và giải thích lỗi khi `return result` sau nhánh. Viết lại có definite assignment hợp lệ hoặc return sớm.

**Bài 4.** Biến `int i` cần in sau vòng `for`. Hãy so sánh `for (int i = ...)` với `int i = 0; for (; ...)` để chọn phạm vi phù hợp.

**Bài 5.** Viết hai khối anh em cùng dùng local `temp`; sau đó lồng khối thứ hai trong khối thứ nhất để quan sát lỗi khai báo trùng tên. Giải thích vì sao field có thể bị shadow bởi local nhưng local-local chồng lấn thì không.

### Ghi nhớ

**Khai báo local gần nơi sử dụng và giữ phạm vi hẹp nhất đủ nhu cầu.** Biến tạm thuộc nhánh hoặc lượt lặp nên ở trong khối đó; accumulator dùng sau vòng cần ở ngoài vòng. Scope nhỏ giúp giảm dùng nhầm tên và trạng thái, nhưng không thay thế quy tắc definite assignment, khả năng đọc hiểu hay thiết kế API rõ ràng.
