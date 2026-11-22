# Kiểm tra definite assignment và biến có thể chưa được gán

Trong Java, một biến cục bộ có thể được khai báo trước khi có giá trị:

~~~java
int total;
~~~

Câu khai báo này tự nó hợp lệ. Vấn đề xuất hiện khi chương trình **đọc** `total` mà trình biên dịch chưa chứng minh được rằng mọi đường thực thi có thể đi tới điểm đọc đều đã gán cho biến một giá trị hợp lệ. Quy tắc này gọi là **definite assignment (DA, chắc chắn đã được gán)**.

DA là một phần của **kiểm tra ngữ nghĩa khi biên dịch**, không phải một phép kiểm tra giá trị bằng cách chạy thử. Trình biên dịch `javac` xem cấu trúc luồng điều khiển (control flow), điều kiện, nhánh, vòng lặp và các điểm thoát để xác định vị trí có thể sử dụng biến. Điều đó giúp chặn nhiều lỗi dùng dữ liệu chưa khởi tạo trước khi ứng dụng chạy.

Sau bài này, bạn cần giải thích được vì sao hai đoạn mã có vẻ gần giống nhau lại biên dịch khác nhau, phân biệt biến cục bộ với field, thiết kế cách khởi tạo rõ ràng và hiểu các trường hợp `final`, `if/else`, vòng lặp, toán tử điều kiện, `switch` và ngoại lệ.

## 1. Mô hình: gán trước khi đọc trên mọi đường đi có thể đến

Hãy tưởng tượng chương trình là một đồ thị gồm các điểm thực hiện và nhánh chuyển hướng. Tại một điểm sử dụng biến, `javac` phải có căn cứ rằng biến ấy đã được gán trên mọi đường đi **có thể hoàn thành và chạm tới vị trí đó**.

~~~text
             [Bắt đầu]
                  |
             [int answer;]
                  |
               [if (ok)]
                /     \
           true         false
            |             |
       [answer=10]    [answer=20]
            \             /
             \           /
             [Đọc answer]
                  |
                [Kết]
~~~

Cả hai nhánh đều gán `answer`, nên điểm đọc được chấp nhận. Nếu bỏ phép gán ở nhánh `false`, tồn tại một đường đi đến điểm đọc mà biến chưa có giá trị, nên `javac` báo lỗi.

Nói chặt hơn, quy tắc là **“definitely assigned trước khi sử dụng giá trị”**, không đơn giản “trong tệp có một dòng gán ở phía trên”. Trình biên dịch xét những điều kiện trong chương trình có thể đưa việc thực thi tới dòng đọc.

Ví dụ **không hợp lệ**:

~~~java
class MissingAssignment {
    static void show(boolean enabled) {
        int result;
        if (enabled) {
            result = 10;
        }
        System.out.println(result); // Lỗi biên dịch
    }
}
~~~

Với `enabled == false`, khối `if` bị bỏ qua; không có giá trị nào được gán cho `result` trước khi in. `javac MissingAssignment.java` (nếu lưu đúng tệp) sẽ báo lỗi kiểu **variable result might not have been initialized**. Thông điệp và vị trí được định dạng có thể khác giữa các bản JDK.

Điều này khác với `NullPointerException`: ở ví dụ trên, **chưa thể tạo classfile hợp lệ để chạy đoạn mã ấy**. Trình biên dịch từ chối ngay việc đọc biến cục bộ chưa chắc chắn đã được gán.

## 2. Biến cục bộ khác field và phần tử mảng

Không phải mọi chỗ khai báo biến trong Java đều chịu cùng yêu cầu khởi tạo.

| Loại dữ liệu | Nếu không viết biểu thức khởi tạo | Ví dụ |
| --- | --- | --- |
| Biến cục bộ trong phương thức/khối | **Không nhận giá trị mặc định**; phải chắc chắn được gán trước khi đọc | `int local;` |
| Tham số phương thức/constructor | Nhận giá trị khi được gọi; coi là đã được gán tại điểm vào phương thức | `void f(int count)` |
| Field instance không `final` | Được JVM khởi tạo mặc định trước khi chạy các initializer/constructor | `int amount;` → ban đầu `0` |
| Field `static` không `final` | Nhận giá trị mặc định khi lớp được khởi tạo theo quy tắc JVM | `static boolean ready;` → ban đầu `false` |
| Phần tử của mảng vừa tạo | Nhận giá trị mặc định của kiểu phần tử | `new int[2]` → hai phần tử `0` |
| Field `final` chưa có initializer (blank final) | Phải được gán theo các quy tắc đặc biệt trong quá trình khởi tạo lớp/đối tượng | `final int id;` |

Đối với kiểu nguyên thủy, giá trị mặc định bao gồm `0`, `false` hoặc ký tự `'\u0000'` tùy kiểu. Với kiểu tham chiếu, giá trị mặc định là `null`. **Giá trị mặc định không đồng nghĩa dữ liệu nghiệp vụ đã hợp lệ.**

Ví dụ Java 17+ chạy độc lập, lưu thành **`DefaultsVsLocals.java`**:

~~~java
public class DefaultsVsLocals {
    private int score;
    private boolean active;
    private String note;

    public static void main(String[] args) {
        DefaultsVsLocals demo = new DefaultsVsLocals();
        int[] numbers = new int[2];

        int local;
        local = 7;

        System.out.println("field int = " + demo.score);
        System.out.println("field boolean = " + demo.active);
        System.out.println("field String la null = " + (demo.note == null));
        System.out.println("array[0] = " + numbers[0]);
        System.out.println("local = " + local);
    }
}
~~~

~~~sh
javac -encoding UTF-8 DefaultsVsLocals.java
java DefaultsVsLocals
~~~

Stdout chính xác:

~~~text
field int = 0
field boolean = false
field String la null = true
array[0] = 0
local = 7
~~~

Biến `local` được phép khai báo không có initializer vì có phép gán `local = 7` trước khi đọc. Nếu xóa phép gán nhưng vẫn giữ lệnh in `local`, mã sẽ không biên dịch. Field `score` và `active`, ngược lại, đã nhận giá trị mặc định theo quy tắc khởi tạo đối tượng.

Nếu `numbers` là **biến cục bộ tham chiếu** chưa được gán (`int[] numbers;`), bản thân nó cũng phải được gán trước khi truy cập `numbers[0]`. Quy tắc mặc định áp dụng cho *phần tử của mảng đã được tạo*, không tự khởi tạo biến tham chiếu tới mảng.

## 3. `if/else`: các nhánh phải hợp nhất đúng cách

Với câu lệnh `if/else`, mỗi nhánh có thể đưa trạng thái gán khác nhau tới điểm hợp nhất. Nếu cả hai nhánh đều có thể kết thúc bình thường, **cả hai phải bảo đảm biến được gán** trước khi dòng sau đọc biến.

Một chương trình hợp lệ, lưu thành **`BranchAssignment.java`**:

~~~java
public class BranchAssignment {
    static String category(int score) {
        String result;
        if (score >= 60) {
            result = "Dat";
        } else {
            result = "Chua dat";
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(category(80));
        System.out.println(category(35));
    }
}
~~~

~~~sh
javac BranchAssignment.java
java BranchAssignment
~~~

Stdout:

~~~text
Dat
Chua dat
~~~

Nếu bỏ `else` và không gán trước cho `result`, đường đi có `score < 60` sẽ chạm tới `return result` mà không có giá trị → lỗi DA.

### Nhánh thoát sớm có thể thay cho phép gán

Một nhánh **không thể đi tiếp** tới điểm đọc vì đã `return` hoặc `throw` sẽ không cần gán biến cho điểm đọc ấy. Ví dụ hợp lệ, lưu thành **`EarlyReturnAssignment.java`**:

~~~java
public class EarlyReturnAssignment {
    static int evaluate(boolean valid) {
        int answer;
        if (!valid) {
            return -1;
        }
        answer = 42;
        return answer;
    }

    public static void main(String[] args) {
        System.out.println(evaluate(false));
        System.out.println(evaluate(true));
    }
}
~~~

~~~sh
javac EarlyReturnAssignment.java
java EarlyReturnAssignment
~~~

Stdout:

~~~text
-1
42
~~~

Từ đây thấy rằng “mọi nhánh đều phải có câu lệnh gán” là cách nói quá đơn giản: chỉ các đường đi có thể đến điểm đọc mới liên quan. `return` chấm dứt luồng thực thi của phương thức hiện tại.

### Toán tử ba ngôi và gán ngay lúc khai báo

Đôi khi cách đơn giản hơn là biểu diễn đầy đủ hai khả năng trong một biểu thức:

~~~java
String result = score >= 60 ? "Dat" : "Chua dat";
~~~

Đây là **đoạn minh họa trong ngữ cảnh đã có biến `score`**, không phải chương trình độc lập. Biểu thức điều kiện chọn một trong hai giá trị rồi gán ngay cho `result`, nên không có đường đi bỏ sót việc khởi tạo.

**Không gán giá trị mặc định giả** chỉ để “cho compiler hết báo lỗi”, ví dụ `int result = 0;` khi `0` không có ý nghĩa nghiệp vụ. Có thể làm mã biên dịch nhưng khiến một nhánh bị quên trả về kết quả sai một cách im lặng.

## 4. Vì sao trình biên dịch không chỉ xem giá trị chạy thực tế?

Đoạn sau **không hợp lệ** dù người viết nghĩ `enabled` “rõ ràng là true”:

~~~java
class LocalBooleanCondition {
    static void test() {
        boolean enabled = true;
        int count;
        if (enabled) {
            count = 5;
        }
        System.out.println(count); // Lỗi DA
    }
}
~~~

`enabled` là biến cục bộ thông thường, không phải hằng biểu thức (constant expression) tại điểm mà quy tắc phân tích cần. Kiểm tra DA của Java dựa trên các quy tắc cú pháp/luồng điều khiển xác định, **không phải phép suy luận tổng quát rằng mọi giá trị biến trong mọi chương trình luôn có thể tính trước**.

Có một số trường hợp đặc biệt với biểu thức boolean hằng, nhưng không nên học DA như một engine “thực thi giả mọi phép toán”. Việc bạn đã quan sát một lần chạy đi vào nhánh `if` cũng không chứng minh nhánh ấy luôn được đi vào với đầu vào khác.

Chẩn đoán đúng là xem vị trí đọc biến và liệt kê các đường có thể đến đó, thay vì chỉ nhìn dòng gán gần nhất.

## 5. Vòng lặp: không được giả định thân vòng lặp chắc chắn chạy

Ví dụ **không hợp lệ**:

~~~java
class LoopAssignmentError {
    static void test(int limit) {
        int last;
        for (int i = 0; i < limit; i++) {
            last = i;
        }
        System.out.println(last); // Lỗi DA
    }
}
~~~

Nếu `limit <= 0`, thân `for` có thể chạy **0 lần**, nên `last` chưa được gán. Trình biên dịch không dựa vào hy vọng rằng người gọi luôn truyền số dương.

Cách sửa tùy ý nghĩa nghiệp vụ:

- Nếu “không có lần lặp” là trường hợp hợp lệ, hãy xác định giá trị kết quả của nó, chẳng hạn `int last = -1;` kèm hợp đồng rõ.
- Nếu yêu cầu là phải có ít nhất một lần lặp, hãy **kiểm tra đầu vào** hoặc thiết kế thuật toán thể hiện điều đó.
- Nếu chỉ cần giá trị sau lần lặp cuối, cân nhắc đổi cách tính để không sử dụng biến chưa chắc đã có giá trị.

Ví dụ chạy được, lưu thành **`LoopAssignment.java`**:

~~~java
public class LoopAssignment {
    static int lastIndex(int length) {
        if (length <= 0) {
            throw new IllegalArgumentException("length phai duong");
        }

        int last;
        for (int i = 0; i < length; i++) {
            last = i;
            if (i == length - 1) {
                return last;
            }
        }
        throw new IllegalStateException("Khong tim thay gia tri");
    }

    public static void main(String[] args) {
        System.out.println(lastIndex(3));
    }
}
~~~

~~~sh
javac LoopAssignment.java
java LoopAssignment
~~~

Stdout:

~~~text
2
~~~

Phương thức này trả về `last` **ngay trong nhánh đã gán**; nếu vòng lặp hoàn tất mà không quay về, đường đi còn lại `throw` một ngoại lệ. Nó làm rõ cấu trúc luồng điều khiển, không chỉ sửa lỗi compiler bằng một giá trị tùy tiện. Ví dụ cũng phù hợp với JDK 17+.

### `do-while` và `break`

`do-while` thực thi thân vòng ít nhất một lần trước khi kiểm tra điều kiện. Ví dụ độc lập:

~~~java
public class DoWhileAssignment {
    public static void main(String[] args) {
        int value;
        do {
            value = 9;
        } while (false);
        System.out.println(value);
    }
}
~~~

~~~sh
javac DoWhileAssignment.java
java DoWhileAssignment
~~~

Stdout:

~~~text
9
~~~

Trường hợp này có thể chứng minh `value` đã được gán trước khi in. Nhưng nếu thân `do` có các nhánh `break`/`continue` phức tạp hoặc phép gán chỉ ở một số đường, phải xét lại từng đường đi; không thể kết luận “cứ do-while là mọi biến đều được gán”.

## 6. Short-circuit: nhánh của `&&` và `||` cũng quyết định trạng thái gán

Các toán tử logic **`&&`** và **`||`** thực hiện đánh giá ngắn mạch (short-circuit):

- Với `a && b`, nếu `a` là `false`, `b` không được đánh giá.
- Với `a || b`, nếu `a` là `true`, `b` không được đánh giá.

Do đó, một phép gán nằm trong `b` không nhất thiết xảy ra ở mọi lần thực thi.

Ví dụ **không hợp lệ**:

~~~java
class ShortCircuitError {
    static void test(boolean enabled) {
        int count;
        boolean ok = enabled && ((count = 5) > 0);
        System.out.println(count); // Lỗi DA
    }
}
~~~

Nếu `enabled` là `false`, biểu thức `count = 5` không chạy. `ok` vẫn có giá trị boolean hợp lệ, nhưng `count` không chắc đã được gán.

Có thể viết lại để phép gán xảy ra rõ ràng trên mọi đường đi:

~~~java
int count = 5;
boolean ok = enabled && count > 0;
~~~

Đây là hai câu lệnh minh họa bên trong phương thức có tham số `boolean enabled`. Với mã thực tế, nên tránh nhúng phép gán trong biểu thức logic nếu điều đó khiến việc suy luận gán trở nên khó đọc.

### DA có thể khác giữa nhánh true và false

Java có quy tắc chi tiết để phân tích **biến chắc chắn đã được gán khi biểu thức boolean là true hoặc false**. Chẳng hạn, một phép gán trong vế phải của `&&` có thể được bảo đảm trên đường đi chỉ tồn tại khi toàn bộ biểu thức là `true`.

Ví dụ chạy được, lưu thành **`BooleanFlowAssignment.java`**:

~~~java
public class BooleanFlowAssignment {
    static void show(boolean enabled) {
        int count;
        if (enabled && ((count = 5) > 0)) {
            System.out.println("count = " + count);
        }
    }

    public static void main(String[] args) {
        show(false);
        show(true);
    }
}
~~~

~~~sh
javac BooleanFlowAssignment.java
java BooleanFlowAssignment
~~~

Stdout của chương trình chỉ có một dòng:

~~~text
count = 5
~~~

Nhánh `if` chỉ thực thi khi vế phải đã được đánh giá và gán `count`, nên điểm đọc **bên trong nhánh ấy** hợp lệ. Nếu chuyển `System.out.println(count)` ra ngoài `if`, đường đi `enabled == false` khiến DA thất bại. Đây là ví dụ cho thấy **vị trí đọc biến** có ảnh hưởng trực tiếp đến kết luận compiler.

## 7. `switch`: mỗi lối vào và lối ra đều quan trọng

Với `switch` dạng statement, số lượng case, `default`, `break` và khả năng đi xuyên qua các case quyết định xem biến đã được gán ở điểm tiếp theo hay chưa. Một ví dụ hợp lệ, lưu thành **`SwitchAssignment.java`**:

~~~java
public class SwitchAssignment {
    static String label(int code) {
        String value;
        switch (code) {
            case 1:
                value = "Mot";
                break;
            case 2:
                value = "Hai";
                break;
            default:
                value = "Khac";
                break;
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println(label(1));
        System.out.println(label(9));
    }
}
~~~

~~~sh
javac SwitchAssignment.java
java SwitchAssignment
~~~

Stdout:

~~~text
Mot
Khac
~~~

Nếu xóa nhánh `default`, trường hợp `code` không khớp `1` hoặc `2` có thể rời `switch` mà chưa gán `value`. Lệnh `return value` ở cuối khi đó không hợp lệ.

Với Java 17+, **switch expression** thường diễn đạt việc tính giá trị kết quả rõ hơn:

~~~java
String value = switch (code) {
    case 1 -> "Mot";
    case 2 -> "Hai";
    default -> "Khac";
};
~~~

Đây là **đoạn minh họa trong phương thức có biến `int code`**, không phải chương trình độc lập. Mỗi đường hoàn thành switch expression tạo một giá trị gán cho `value`. Tùy kiểu của biểu thức chọn và các case, Java có yêu cầu về tính bao phủ (exhaustiveness). Nó tránh một lớp lỗi quên gán kết quả khi thiết kế dạng statement nhiều nhánh.

## 8. `try/catch`: phải xét cả đường đi khi có ngoại lệ

Đối với khối `try`, một câu lệnh có thể ném exception trước khi đi tới phép gán tiếp theo. Vì thế, không thể coi “có dòng gán bên trong `try`” là đủ cho tất cả đường đi.

Ví dụ chạy được, lưu thành **`TryCatchAssignment.java`**:

~~~java
public class TryCatchAssignment {
    static int parseOrDefault(String input) {
        int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            value = -1;
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println(parseOrDefault("42"));
        System.out.println(parseOrDefault("abc"));
    }
}
~~~

~~~sh
javac TryCatchAssignment.java
java TryCatchAssignment
~~~

Stdout:

~~~text
42
-1
~~~

Nếu `parseInt` thành công thì `value` nhận kết quả; nếu ném `NumberFormatException` thì nhánh `catch` gán `-1`. Cả hai đường đi tiếp tục tới `return value` đều đã gán biến.

Một trường hợp **không hợp lệ**:

~~~java
class IncompleteCatchAssignment {
    static int parse(String input) {
        int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("Gia tri khong hop le");
        }
        return value; // Lỗi DA: nhánh catch không gán value
    }
}
~~~

Nếu ý định là báo lỗi rồi kết thúc, có thể `throw` một ngoại lệ phù hợp hoặc `return` giá trị khác theo hợp đồng. Không nên tự động dùng `-1` nếu `-1` là dữ liệu hợp lệ trong miền nghiệp vụ.

Khối `finally` có các quy tắc luồng điều khiển riêng, nhất là khi kết hợp `return`, `throw` và gán biến `final`. Khi gặp cấu trúc phức tạp, hãy liệt kê từng đường có thể hoàn thành bình thường; tránh suy luận chỉ bằng thứ tự dòng chữ trên màn hình.

## 9. Biến `final`: definite assignment và definite unassignment

Đối với biến cục bộ `final` chưa có initializer (blank final), Java còn cần bảo đảm **không gán lại** sau lần gán hợp lệ.

Hai ý liên quan nhưng khác nhau:

- **Definitely assigned (DA):** Biến đã chắc chắn có giá trị trước lúc đọc.
- **Definitely unassigned (DU):** Trước phép gán cho blank final, trình biên dịch phải bảo đảm biến chưa được gán trên đường đi liên quan.

Ví dụ hợp lệ, lưu thành **`FinalAssignment.java`**:

~~~java
public class FinalAssignment {
    static int choose(boolean priority) {
        final int limit;
        if (priority) {
            limit = 100;
        } else {
            limit = 20;
        }
        return limit;
    }

    public static void main(String[] args) {
        System.out.println(choose(true));
        System.out.println(choose(false));
    }
}
~~~

~~~sh
javac FinalAssignment.java
java FinalAssignment
~~~

Stdout:

~~~text
100
20
~~~

Mỗi lần gọi chỉ thực thi một nhánh; ở cả hai nhánh, `limit` được gán đúng một lần trước khi đọc. Ngược lại, đoạn sau **không hợp lệ**:

~~~java
class FinalReassignment {
    static void test() {
        final int limit;
        limit = 10;
        limit = 20; // Lỗi: biến final đã được gán
    }
}
~~~

Với biến `final` đã được gán ngay khi khai báo, phép gán tiếp theo cũng bị từ chối:

~~~java
final int max = 10;
// max = 11; // Không hợp lệ nếu bỏ chú thích
~~~

Một tham chiếu `final` không có nghĩa đối tượng nó trỏ tới là bất biến: bạn có thể thay đổi trạng thái đối tượng nếu API cho phép; quy tắc `final` ở đây hạn chế **gán lại chính biến tham chiếu**.

### Blank final field khác blank final local

Field `final` không có initializer cũng cần được gán đúng quy tắc khởi tạo. Với field instance, constructor/initializer phải bảo đảm mỗi đối tượng có giá trị cho field khi khởi tạo hoàn tất; với static final field, khởi tạo lớp phải đáp ứng yêu cầu tương ứng. Đây không phải quyền tự do đọc field chưa khởi tạo.

Ví dụ chạy được, lưu thành **`FinalFieldDemo.java`**:

~~~java
public class FinalFieldDemo {
    private final int code;

    public FinalFieldDemo(int code) {
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    public static void main(String[] args) {
        System.out.println(new FinalFieldDemo(7).getCode());
    }
}
~~~

~~~sh
javac FinalFieldDemo.java
java FinalFieldDemo
~~~

Stdout:

~~~text
7
~~~

Nếu bỏ phép gán `this.code = code` trong constructor, compiler sẽ báo blank final field có thể chưa được khởi tạo. Các constructor gọi nhau qua `this(...)` cũng phải tuân thủ quy tắc gán đúng một lần; đừng tự thêm phép gán ở cả constructor gọi và constructor được gọi.

## 10. DA không bảo đảm giá trị có ý nghĩa nghiệp vụ

DA **chỉ xác nhận đã có phép gán hợp lệ**, không xác nhận giá trị được gán là tốt. Ví dụ:

~~~java
int divisor = 0;
int result = 100 / divisor;
~~~

`divisor` đã được gán chắc chắn, nhưng phép chia số nguyên cho 0 gây `ArithmeticException` khi chạy. Tương tự:

~~~java
String name = null;
// name.length(); // Nếu chạy sẽ ném NullPointerException
~~~

`name` đã được gán, nhưng giá trị null vẫn có thể gây lỗi khi dùng. Với Java, phân tích DA không phải một hệ thống phân tích nullability tổng quát.

Đặc biệt, mã sau biên dịch được nhưng có thể trả kết quả sai ý định:

~~~java
int price = -1;
System.out.println(price);
~~~

Nó đáp ứng DA vì đã gán `-1` trước khi in; việc đơn giá âm có hợp lệ hay không phải đến từ kiểm tra dữ liệu và quy tắc nghiệp vụ.

| Cơ chế | Câu hỏi chính |
| --- | --- |
| Kiểm tra cú pháp | Câu lệnh có đúng ngữ pháp Java không? |
| Kiểm tra kiểu | Phép gán, toán tử, lời gọi phương thức có kiểu hợp lệ không? |
| Definite assignment | Biến đã chắc chắn được gán trên các đường đi tới điểm đọc chưa? |
| Definite unassignment cho blank final | Có chắc biến chưa bị gán trước phép gán này không? |
| Kiểm tra runtime | Dữ liệu, ngoại lệ, tài nguyên có an toàn khi thực thi không? |
| Kiểm thử nghiệp vụ | Kết quả có đúng theo yêu cầu độc lập với code không? |

Không nên xử lý lỗi DA bằng cách gán một giá trị tùy tiện rồi xem đó là “đã giải quyết bug”. Nếu một nhánh thiếu phép gán, có thể bản thân nhánh đó thiếu hành vi nghiệp vụ cần định nghĩa.

## 11. Kỹ thuật đọc lỗi DA và sửa đúng nguyên nhân

Khi `javac` báo biến có thể chưa được gán:

1. **Xác định điểm đọc:** Dòng `return result` hoặc `System.out.println(result)` là nơi cần chắc chắn đã có giá trị.
2. **Tìm khai báo:** Biến nằm trong scope nào? Có phải local chưa có initializer, hay field/parameter với quy tắc khác?
3. **Liệt kê đường đi:** `if/else`, `switch`, vòng lặp 0 lần, `break`, `continue`, `return`, `throw`, `try/catch` và short-circuit có tạo đường bỏ qua phép gán không?
4. **Kiểm tra hợp đồng:** Trường hợp thiếu giá trị có hợp lệ? Nếu có, cần một giá trị mặc định có nghĩa hoặc kiểu thể hiện sự vắng mặt; nếu không, cần từ chối dữ liệu/thoát phương thức có chủ đích.
5. **Đơn giản hóa:** Ưu tiên khai báo với initializer đúng nghĩa, rút gọn nhánh bằng `return`, hoặc tách phương thức để giảm số trạng thái cần theo dõi.
6. **Biên dịch và thử cả hai đường:** Một bản sửa hợp lệ theo DA vẫn có thể sai nghiệp vụ; cần test nhánh thường, nhánh biên và nhánh lỗi.

Ví dụ, nếu yêu cầu chỉ cho phép dùng giá trị khi `enabled` là `true`, cách làm rõ ràng là đặt lệnh đọc **trong nhánh đã gán**, hoặc trả về sớm khi không enabled. Nếu giá trị bắt buộc phải tồn tại dù `enabled` là `false`, cần bổ sung giá trị/hành vi cho nhánh đó.

### Vì sao có lúc lỗi xuất hiện “ở cuối phương thức”?

Compiler thường chỉ rõ **điểm đọc đầu tiên chưa thỏa DA**, không nhất thiết ở nơi tác giả “quên gán”. Vì thế đừng chỉ sửa dòng được gạch đỏ: cần nhìn lên các nhánh có thể bỏ qua phép gán.

Một lỗi DA cũng có thể nổi lên khi bạn thêm một nhánh `if` mới, sửa `break` hoặc đưa lệnh in ra ngoài vùng nhánh. Đó là hệ quả của thay đổi **đồ thị luồng điều khiển**, dù khai báo biến không đổi.

## 12. Thực hành củng cố

**Bài 1 — Hai nhánh.** Từ `MissingAssignment`, thêm `else { result = 20; }`; dự đoán trạng thái DA ở điểm in. Sau đó thay nhánh else bằng `return;` và tự giải thích vì sao cũng hợp lệ.

**Bài 2 — Không mặc định chạy vòng lặp.** Từ `LoopAssignmentError`, thử `limit = 3` và `limit = 0` *trong suy luận*, rồi giải thích vì sao compiler từ chối trước khi chạy. Chọn một hợp đồng hợp lệ để sửa.

**Bài 3 — Short-circuit.** Với `ShortCircuitError`, chứng minh `enabled == false` có thể bỏ qua gán `count`. Di chuyển điểm in vào nhánh `if` như `BooleanFlowAssignment` và đối chiếu.

**Bài 4 — Switch.** Xóa `default` trong `SwitchAssignment` rồi thử biên dịch. Trường hợp nào của `code` làm biến `value` thiếu phép gán? Viết lại bằng switch expression và so sánh tính rõ ràng.

**Bài 5 — Final.** Thử gán `limit` lần thứ hai trong `FinalAssignment`; giải thích vi phạm DU. Với `FinalFieldDemo`, bỏ phép gán field trong constructor rồi xác nhận lỗi biên dịch.

**Bài 6 — Kiểm thử nghiệp vụ.** Trong `DefaultsVsLocals`, giá trị `0` của field có thể biểu thị “chưa có dữ liệu” hay đơn giá hợp lệ? Hãy viết điều kiện kiểm tra phù hợp với yêu cầu của một ứng dụng cụ thể.

### Câu hỏi tự đánh giá

1. **DA trả lời câu hỏi gì?** — Mọi đường đi có thể tới một điểm đọc biến có bảo đảm biến đã được gán trước đó không?
2. **Biến local `int x;` có tự có giá trị `0` không?** — Không; phải gán chắc chắn trước khi đọc.
3. **Field `int score;` có giá trị gì trước initializer/constructor gán thêm?** — Giá trị mặc định `0` của `int`.
4. **Tại sao gán trong `for` vẫn có thể không đủ?** — Vòng lặp có thể chạy 0 lần.
5. **Tại sao đọc trong nhánh true của `&&` có thể hợp lệ?** — Nhánh ấy có thể chỉ đến được khi biểu thức có phép gán đã thực thi.
6. **Blank final cần gì ngoài DA?** — Quy tắc definite unassignment trước khi được gán, để tránh gán lại.
7. **DA có bảo đảm biến khác `null` hoặc không bằng 0 không?** — Không; nó không chứng minh giá trị hợp lệ lúc chạy hay đúng nghiệp vụ.

**Kết nối kiến thức:** Definite assignment là ví dụ cụ thể về cách `javac` dùng **luồng điều khiển và quy tắc ngôn ngữ** để phát hiện lỗi trước runtime. Khi hiểu kỹ quy tắc này, bạn sẽ dễ đọc hơn các lỗi liên quan biến local, `final`, nhánh `if`, vòng lặp và exception, đồng thời biết trường hợp nào cần sửa thiết kế điều khiển thay vì chỉ thêm giá trị mặc định.