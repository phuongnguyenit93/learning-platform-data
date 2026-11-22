# Yêu cầu gán giá trị trước khi đọc biến cục bộ trong Java

## 1. Quy tắc cốt lõi: definite assignment

Một **biến cục bộ** (*local variable*) được khai báo bên trong phương thức, constructor hoặc block có thể chưa có initializer ngay tại dòng khai báo:

~~~java
int quantity;             // Được phép khai báo
quantity = 4;             // Gán trước khi sử dụng
System.out.println(quantity); // 4
~~~

Tuy nhiên, **Java 17 yêu cầu biến cục bộ phải được gán chắc chắn trước khi đọc giá trị**. Quy tắc này gọi là **definite assignment** (gán chắc chắn). Nó được trình biên dịch `javac` kiểm tra bằng cách phân tích những đường điều khiển có thể đi tới chỗ đọc biến.

Ví dụ cố tình sai:

~~~java
static void invalid() {
    int quantity;
    System.out.println(quantity); // LỖI BIÊN DỊCH
}
~~~

Thông báo của `javac` thường có dạng:

~~~text
error: variable quantity might not have been initialized
~~~

Đây là lỗi **compile-time**, không phải exception chỉ xuất hiện khi chạy. Trình biên dịch không cho phép sử dụng một biến cục bộ mà có thể chưa được gán.

> **Nhớ:** “đã khai báo” khác “đã được gán giá trị”. Không nhất thiết phải khởi tạo ngay ở câu lệnh khai báo, nhưng mọi đường thực thi đi tới nơi đọc phải bảo đảm biến đã được gán.

## 2. Khai báo, gán và đọc giá trị khác nhau thế nào?

~~~java
int score;              // Khai báo, chưa có giá trị được phép đọc
score = 80;             // Gán lần đầu
int copied = score;     // Đọc score hợp lệ; copied được khởi tạo
score = score + 5;      // Đọc score cũ, rồi gán score mới
System.out.println(score); // 85
~~~

| Câu lệnh | Có đọc giá trị cũ của `score`? | Điều kiện |
|---|---|---|
| `int score;` | Không | Khai báo hợp lệ |
| `score = 80;` | Không | Gán giá trị đầu tiên hợp lệ |
| `int x = score;` | Có | `score` phải đã được gán |
| `score = score + 1;` | Có | Đọc vế phải trước khi gán lại |
| `score++;` | Có | Cần giá trị hiện tại để tăng |
| `score += 1;` | Có | Phép gán kết hợp cũng dùng giá trị cũ |

Ví dụ **không biên dịch** dù có dấu `=`:

~~~java
int count;
// count = count + 1; // Sai: vế phải đọc count chưa gán
// count++;           // Sai: cần đọc count hiện tại
// count += 1;        // Sai: cũng cần giá trị cũ
~~~

Sửa bằng cách khởi tạo trước:

~~~java
int count = 0;
count++;
System.out.println(count); // 1
~~~

## 3. Compiler xét mọi nhánh if/else dẫn tới chỗ đọc

Trường hợp **sai**:

~~~java
static String invalid(boolean passed) {
    String result;
    if (passed) {
        result = "PASS";
    }
    return result; // LỖI: passed có thể false
}
~~~

Nếu `passed` là `false`, câu lệnh gán không được thực hiện. Vì thế `return result` có một đường đi đọc biến chưa gán.

Cách sửa 1 — **gán ở cả hai nhánh**:

~~~java
static String status(boolean passed) {
    String result;
    if (passed) {
        result = "PASS";
    } else {
        result = "FAIL";
    }
    return result;
}
~~~

Cách sửa 2 — **đưa giá trị mặc định vào khai báo**:

~~~java
static String status(boolean passed) {
    String result = "FAIL";
    if (passed) {
        result = "PASS";
    }
    return result;
}
~~~

Cách sửa 3 — **dùng biểu thức điều kiện** khi chỉ cần chọn một giá trị:

~~~java
static String status(boolean passed) {
    return passed ? "PASS" : "FAIL";
}
~~~

Cả ba đều có thể hợp lệ, nhưng hãy chọn cách phản ánh đúng yêu cầu. **Không gán giá trị giả chỉ để làm hết lỗi biên dịch** nếu giá trị ấy khiến nghiệp vụ hiểu nhầm.

## 4. Nhánh return sớm có thể giúp bảo đảm đã gán

Compiler quan tâm đến **những đường có thể đi đến lệnh đọc**, không nhất thiết mọi nhánh đều phải gán cùng một biến.

~~~java
static String sign(int number) {
    if (number < 0) {
        return "NEGATIVE";
    }

    String label;
    if (number == 0) {
        label = "ZERO";
    } else {
        label = "POSITIVE";
    }
    return label;
}
~~~

Nhánh `number < 0` đã `return`, không thể đi xuống `return label`. Những nhánh còn lại đều gán `label`, nên mã hợp lệ.

Một ví dụ ngắn hơn:

~~~java
static int nonnegative(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("Negative value");
    }
    int accepted = value;
    return accepted;
}
~~~

`return` hoặc `throw` có thể kết thúc đường điều khiển hiện tại. Nhưng nếu một nhánh **chỉ in lỗi rồi tiếp tục**, nó vẫn cần bảo đảm biến được gán trước khi đọc.

## 5. Vòng lặp có thể không chạy lần nào

Một `while` hoặc `for` với điều kiện kiểm tra trước có thể thực hiện **0 vòng**, nên không được mặc định xem việc gán bên trong loop là đủ.

~~~java
static void invalid(int limit) {
    int last;
    for (int i = 0; i < limit; i++) {
        last = i;
    }
    // System.out.println(last); // Nếu mở comment: lỗi compile
}
~~~

Nếu `limit <= 0`, không vòng nào chạy. Cách đúng khi cần đọc kết quả sau vòng lặp là định nghĩa một giá trị khởi tạo có ý nghĩa:

~~~java
static long sumFromOneTo(int limit) {
    long sum = 0L;
    for (long i = 1; i <= limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

Với `limit = 4`, kết quả là `10`; với `limit = 0`, kết quả là `0`. Dùng `long` cho cả biến đếm và tổng để tránh tràn `int` khi `limit` rất lớn; vòng lặp vẫn có chi phí thời gian tỷ lệ với `limit` và ví dụ này chủ yếu minh họa quy tắc gán biến.

**Phân biệt:** biến `int i = 1` trong phần khởi tạo của `for` được gán rõ ràng, nên có thể đọc ở điều kiện và thân loop. Vấn đề nảy sinh khi bạn **chỉ** gán một biến khác ở bên trong loop rồi đọc **sau** loop, trong khi loop có thể không chạy.

## 6. Biến final cục bộ: được gán lần đầu nhưng không gán lại

`final` cho phép viết một **blank final local** (khai báo mà chưa gán), miễn là trước khi đọc nó đã được gán hợp lệ và không bị gán lại trên đường thực thi.

~~~java
static String mode(boolean custom) {
    final String selected;
    if (custom) {
        selected = "CUSTOM";
    } else {
        selected = "DEFAULT";
    }
    return selected;
}
~~~

Đoạn trên hợp lệ: mỗi đường thực thi gán `selected` đúng một lần trước khi đọc.

Ngược lại:

~~~java
final int limit = 5;
// limit = 6; // LỖI: biến final không thể được gán lại
~~~

**`final` không tự cấp giá trị ban đầu.** Nếu khai báo `final int limit;` rồi đọc mà chưa có phép gán chắc chắn, `javac` vẫn báo lỗi.


## 7. Phạm vi áp dụng: biến cục bộ và những chỗ dễ nhầm

*Definite assignment* được kiểm tra với biến cục bộ. **Tham số** đã nhận giá trị từ bên gọi; **field** được mặc định theo kiểu (số là 0, `boolean` là `false`, tham chiếu là `null`); **phần tử mảng mới** cũng được mặc định theo kiểu.

~~~java
int[] numbers = new int[2];  // Local numbers đã được gán reference
System.out.println(numbers[0]); // 0: phần tử mảng được mặc định
int[] missing;
// System.out.println(missing[0]); // Lỗi compile: local missing chưa gán
~~~

Đọc được một field tham chiếu có giá trị mặc định `null` không bảo đảm gọi method trên nó an toàn. Bài về giá trị mặc định sẽ giải thích trường hợp mảng nhiều chiều và các kiểu cụ thể.

## 8. `var` cần initializer để suy ra kiểu

Với Java 17, biến cục bộ có thể dùng `var` khi compiler suy ra kiểu từ biểu thức khởi tạo:

~~~java
var count = 5;        // Suy ra int
var name = "Java";    // Suy ra String
count = 6;            // Đúng, vẫn là int
~~~

Các dòng sau không hợp lệ:

~~~java
// var count;          // Sai: thiếu initializer để suy ra kiểu
// var name = null;    // Sai: không thể suy ra kiểu phù hợp chỉ từ null
// count = "six";      // Sai: kiểu String không gán được cho int
~~~

`var` không bỏ kiểm tra kiểu và cũng không làm giảm yêu cầu gán trước khi đọc. Nếu cần khai báo trước và gán sau ở một nhánh điều khiển, hãy dùng **kiểu tường minh** như `String label;`.

## 9. Chương trình Java 17 hoàn chỉnh, chạy được

Tạo tệp chính xác tên **`DefiniteAssignmentDemo.java`**:

~~~java
public final class DefiniteAssignmentDemo {
    private DefiniteAssignmentDemo() {}

    static final class Settings {
        int attempts;       // Field mặc định 0
        boolean enabled;    // Field mặc định false
        String note;        // Field mặc định null
    }

    static String review(boolean accepted) {
        String result;      // Khai báo chưa gán
        if (accepted) {
            result = "ACCEPT";
        } else {
            result = "REJECT";
        }
        return result;      // Cả hai nhánh đều đã gán
    }

    static String classify(int number) {
        if (number < 0) {
            return "NEGATIVE";
        }
        String label;
        if (number == 0) {
            label = "ZERO";
        } else {
            label = "POSITIVE";
        }
        return label;
    }

    static long sum(int limit) {
        long result = 0L;   // Cần giá trị kể cả khi loop không chạy
        for (long i = 1; i <= limit; i++) {
            result += i;
        }
        return result;
    }

    static String chooseMode(boolean custom) {
        final String mode;
        if (custom) {
            mode = "CUSTOM";
        } else {
            mode = "DEFAULT";
        }
        return mode;
    }

    public static void main(String[] args) {
        int quantity;
        quantity = 4;
        System.out.println("quantity=" + quantity);

        System.out.println("review(true)=" + review(true));
        System.out.println("review(false)=" + review(false));
        System.out.println("classify(-2)=" + classify(-2));
        System.out.println("classify(0)=" + classify(0));
        System.out.println("classify(5)=" + classify(5));

        System.out.println("mode=" + chooseMode(args.length > 0));
        System.out.println("sum(4)=" + sum(4));
        System.out.println("sum(0)=" + sum(0));

        int[] numbers = new int[2];
        System.out.println("array[0]=" + numbers[0]);

        Settings settings = new Settings();
        System.out.println("field attempts=" + settings.attempts);
        System.out.println("field enabled=" + settings.enabled);
        System.out.println("field note=" + settings.note);
    }
}
~~~

Dùng **JDK 17 trở lên**, mở terminal tại thư mục chứa tệp nguồn.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
java -cp . DefiniteAssignmentDemo custom
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
java -cp . DefiniteAssignmentDemo custom
~~~

Đầu ra **lần chạy không có đối số**:

~~~text
quantity=4
review(true)=ACCEPT
review(false)=REJECT
classify(-2)=NEGATIVE
classify(0)=ZERO
classify(5)=POSITIVE
mode=DEFAULT
sum(4)=10
sum(0)=0
array[0]=0
field attempts=0
field enabled=false
field note=null
~~~

Khi chạy lệnh có đối số `custom`, mọi dòng vẫn như trên, **trừ dòng `mode=CUSTOM`**. Trong ví dụ này chỉ kiểm tra sự hiện diện của đối số qua `args.length > 0`; bản thân từ `custom` không được phân tích thêm.

## 10. Cách tự chẩn đoán lỗi gán trước khi đọc

Khi gặp thông báo gần giống `variable x might not have been initialized`, hãy kiểm tra:

1. **Biến thuộc loại nào?** Nếu là biến cục bộ, không giả định có giá trị mặc định giống field.
2. **Vị trí đọc ở đâu?** Đọc có thể ẩn trong `x++`, `x += 1`, `return x` hoặc tham số truyền cho method.
3. **Mọi nhánh có dẫn tới dòng đọc đều đã gán chưa?** Kiểm tra `if/else`, `switch` và các đường `return`/`throw`.
4. **Vòng lặp có thể không chạy không?** Nếu có, giá trị gán *chỉ* trong loop chưa bảo đảm an toàn sau loop.
5. **Đã vô tình khai báo `final` rồi gán lại chưa?** Blank final được gán lần đầu đúng đường đi; không được gán lần nữa.
6. **Có đang dùng `var` mà thiếu initializer không?** Đổi sang kiểu tường minh hoặc khởi tạo ngay.
7. **Giá trị mặc định bạn chọn có đúng ý nghĩa không?** Đừng dùng `0`, `false` hoặc `null` chỉ để che thiếu dữ liệu hợp lệ.

Compiler kiểm tra **tính chắc chắn của phép gán**, chứ không biết giá trị ấy có đúng nghiệp vụ hay không. Chương trình có thể gán một giá trị sai hoàn toàn mà vẫn qua kiểm tra definite assignment.

## 11. Bài tập ngắn kèm đáp án

### Bài A — nhánh thiếu gán

~~~java
static int score(boolean passed) {
    int result;
    if (passed) {
        result = 100;
    }
    return result;
}
~~~

**Đáp án:** lỗi compile vì `passed=false` khiến `result` chưa gán. Có thể thêm `else { result = 0; }` **nếu 0 đúng yêu cầu**, hoặc xử lý nhánh sai bằng `return`/`throw` hợp lý.

### Bài B — phép tăng có đọc biến không?

~~~java
int counter;
// counter++;
~~~

**Đáp án:** có. `counter++` phải đọc giá trị cũ nên chưa hợp lệ. Đặt `int counter = 0;` trước khi tăng.

### Bài C — vì sao field không lỗi?

~~~java
class Sample {
    int value;
    void show() {
        System.out.println(value);
    }
}
~~~

**Đáp án:** `value` là **instance field**, mặc định là `0`. Nếu `value` là biến cục bộ chưa được gán trong method, hành vi compile sẽ khác.

### Bài D — vòng lặp chạy 0 lần

~~~java
int last;
for (int i = 0; i < 0; i++) {
    last = i;
}
// System.out.println(last);
~~~

**Đáp án:** khi bỏ comment dòng in, biến `last` chưa chắc đã được gán. Loop không thực hiện vòng nào nên không thể dựa vào phép gán trong thân để đọc `last` sau đó.

### Bài E — final được gán ở hai nhánh?

~~~java
final String state;
if (ok) {
    state = "YES";
} else {
    state = "NO";
}
System.out.println(state);
~~~

**Đáp án:** hợp lệ nếu `ok` là một biến boolean đã được định nghĩa. Trên mỗi đường chạy, `state` được gán **đúng một lần** trước khi đọc.

## 12. Checklist hoàn thành

- [ ] Biết khai báo biến cục bộ không đồng nghĩa được phép đọc trước khi gán.
- [ ] Nhận ra thông báo `might not have been initialized` là lỗi biên dịch.
- [ ] Phân tích được đường chạy qua `if/else`, `return` và `throw`.
- [ ] Hiểu vòng lặp có thể thực hiện 0 lần.
- [ ] Biết `x++`, `x += 1`, `x = x + 1` đều cần đọc giá trị cũ.
- [ ] Phân biệt biến cục bộ với tham số, field và phần tử mảng.
- [ ] Hiểu `final` có thể gán lần đầu sau khai báo nhưng không gán lại.
- [ ] Hiểu `var` cần initializer để suy ra kiểu.
- [ ] Biên dịch/chạy `DefiniteAssignmentDemo.java` và đối chiếu từng dòng kết quả.
- [ ] Chọn giá trị khởi tạo theo yêu cầu thực, không tùy tiện để tránh lỗi compiler.

**Kết luận:** Java yêu cầu biến cục bộ phải **được gán chắc chắn trên mọi đường có thể đi tới nơi đọc**. `javac` kiểm tra điều này trước khi chạy; field và phần tử mảng có giá trị mặc định nhưng biến cục bộ thì không được đọc khi chưa gán. Hiểu definite assignment giúp viết luồng `if/else`, vòng lặp và `final` chính xác mà không cần khởi tạo giả tạo.