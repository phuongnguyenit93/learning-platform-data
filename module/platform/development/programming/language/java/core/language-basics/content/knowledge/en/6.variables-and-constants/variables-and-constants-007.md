# `final` trên biến và quy tắc chỉ gán một lần trong Java 17+

## 1. Ý nghĩa chính xác của `final` đối với biến

Một biến Java bình thường có thể được gán lại nếu kiểu và phạm vi cho phép. Khi đặt **`final`** vào khai báo, biến chỉ có thể nhận **một phép gán hợp lệ trên mỗi đường thực thi**; sau khi đã được gán, không thể gán lại chính biến đó.

~~~java
int normal = 10;
normal = 20; // Hợp lệ

final int limit = 10;
// limit = 20; // LỖI BIÊN DỊCH: cannot assign a value to final variable limit
~~~

Điều này áp dụng cho biến kiểu nguyên thủy như `int`, `boolean` và biến kiểu tham chiếu như `StringBuilder`, mảng hoặc object. Nhưng **`final` khóa khả năng gán lại biến, không tự biến đối tượng mà biến trỏ tới thành bất biến**.

| Cách viết | Ý nghĩa | Kết quả |
|---|---|---|
| `int x = 1; x = 2;` | Biến thường, gán lại được | Hợp lệ |
| `final int x = 1;` | Biến đã gán một lần | Hợp lệ |
| `final int x = 1; x = 2;` | Gán lần hai cho biến final | Lỗi compile |
| `final int x; x = 1;` | Khai báo trước, gán lần đầu sau | Hợp lệ |
| `final int x; System.out.println(x);` | Đọc trước khi được gán | Lỗi compile |
| `final StringBuilder b = new StringBuilder(); b.append("A");` | Thay đổi trạng thái object, không gán lại b | Hợp lệ |

**Quy tắc kép:** biến `final` phải **được gán chắc chắn trước khi đọc** (*definitely assigned*) và **chưa từng được gán trước mỗi phép gán cho nó** (*definitely unassigned*). Bộ kiểm tra của `javac` xét các đường đi của chương trình.

## 2. Khởi tạo ngay hoặc gán sau: blank final

Cách thông dụng nhất là vừa khai báo vừa khởi tạo:

~~~java
final double taxRate = 0.10;
final boolean production = true;
final String title = "Java";
~~~

Java cũng cho phép **blank final local variable**: khai báo mà chưa có giá trị ban đầu, rồi gán sau đó:

~~~java
static int calculate(boolean premium) {
    final int price;
    if (premium) {
        price = 200;
    } else {
        price = 100;
    }
    return price;
}
~~~

Dù trong source có **hai câu lệnh gán** khác nhau, ở **mỗi lần chạy** chỉ **một nhánh** thực hiện. Vì thế mỗi đường tới `return price` đều gán biến đúng một lần, nên chương trình hợp lệ.

~~~java
// Sai: một đường đi chưa gán price
final int price;
if (premium) {
    price = 200;
}
// System.out.println(price); // Không thể đọc khi premium có thể false
~~~

Nếu hai phép gán có thể xảy ra **liên tiếp** trên cùng đường đi, compiler sẽ từ chối:

~~~java
// Sai:
final int number;
number = 5;
// number = 5; // Dù giá trị giống nhau vẫn là phép gán thứ hai
~~~

**Chính xác hơn câu “final bắt buộc được gán một lần”:** không được gán **quá một lần trên một đường thực thi**; nếu cần đọc giá trị thì phải bảo đảm đã được gán. Với blank final local không hề được đọc, Java không buộc bạn thêm một phép gán vô nghĩa.

## 3. Vòng lặp: biến final không được cập nhật lặp đi lặp lại

Trong vòng lặp thông thường, biến đếm thường phải thay đổi:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Không thể chỉ thêm `final` vào `i`:

~~~java
// Sai: phần i++ cố gán lại biến final
// for (final int i = 0; i < 3; i++) { }
~~~

Một **blank final** được gán bên trong thân một `while` cũng thường không hợp lệ nếu vòng lặp có thể chạy nhiều lần: compiler không bảo đảm mỗi lần gán xảy ra trên đường mà biến vẫn chưa được gán.

Ngược lại, **enhanced for** có thể khai báo biến phần tử `final`:

~~~java
int sum = 0;
for (final int value : new int[] {1, 2, 3}) {
    sum += value;
}
System.out.println(sum); // 6
~~~

Mỗi lần lặp có một biến phần tử cho lần lặp đó; trong **thân vòng lặp**, bạn không được viết `value = 99;`. Bạn vẫn có thể gán lại `sum` vì `sum` không phải `final`.


## 4. `final` khóa phép gán biến, không khóa object

~~~java
final int count = 5;
// count++; // Lỗi: cố gán lại biến primitive

final int[] scores = {10, 20};
scores[0] = 99; // Hợp lệ: thay phần tử của object mảng
// scores = new int[] {30}; // Lỗi: cố gán lại biến scores
~~~

Với primitive, không gán lại được biến cũng có nghĩa giá trị primitive giữ nguyên. Với reference, **tham chiếu của biến** giữ nguyên nhưng object vẫn có thể mutable. Điều này không tự cấp an toàn đa luồng hay bất biến sâu; bài riêng về tham chiếu `final` sẽ chứng minh bằng alias, `StringBuilder` và collection. Một biến `final String label = null;` vẫn hợp lệ, nhưng đã gán `null` thì không thể gán lại.

## 5. final trên tham số method và biến cục bộ

Có thể đặt `final` cho tham số:

~~~java
static int doubleOf(final int value) {
    // value = 7; // Lỗi compile
    return value * 2;
}
~~~

`final` không ngăn method **đọc** giá trị được truyền vào. Nó chỉ không cho phép gán lại tham số `value` trong thân method.

Với tham số tham chiếu:

~~~java
static void addMark(final StringBuilder text) {
    text.append("!");      // Hợp lệ, thay đổi object
    // text = new StringBuilder(); // Sai, gán lại tham số
}
~~~

Đây là một công cụ giúp diễn tả chủ ý “tham số này không bị thay thế”. Nó **không** ngăn bên gọi giữ tham chiếu đến cùng object và nhìn thấy thay đổi trạng thái.

## 6. final field: cần hoàn tất khởi tạo đúng chỗ

Một field `final` có thể được khởi tạo tại nơi khai báo:

~~~java
class Config {
    final int maxAttempts = 3;
}
~~~

Hoặc để trống lúc khai báo rồi khởi tạo trong constructor, thường gọi là **blank final instance field**:

~~~java
class User {
    private final int id;

    User(int id) {
        this.id = id; // Constructor gán field lần đầu
    }

    int id() {
        return id;
    }
}
~~~

**Mọi constructor hợp lệ phải bảo đảm field final chưa khởi tạo được gán trước khi constructor hoàn thành bình thường.** Nếu lớp có nhiều constructor, phải thiết kế các đường khởi tạo cho thống nhất; không được bỏ một đường hoặc gán hai lần. Có thể dùng instance initializer khi phù hợp, nhưng không nên cố gán lại field đã khởi tạo.

Với **`static final`**, giá trị có thể được gán ngay khi khai báo hoặc thông qua **static initializer**:

~~~java
class Environment {
    static final String APP_NAME;
    static {
        APP_NAME = "Study";
    }
}
~~~

Một `static final` field chưa được gán phải được khởi tạo hợp lệ trong quá trình khởi tạo tĩnh; không thể chờ đến lúc gọi `main` rồi mới tùy ý gán cho nó.

**Khác biệt với field bình thường:** field `int` mặc định có giá trị 0, nhưng một blank final field vẫn phải tuân thủ các yêu cầu gán rõ ràng khi hoàn tất khởi tạo. Không lấy giá trị mặc định trong JVM làm lý do bỏ qua khởi tạo final field.

## 7. `final` không có nghĩa lúc nào cũng là compile-time constant

Một giá trị được gán một lần **không nhất thiết là hằng số lúc biên dịch**:

~~~java
final int fixed = 10;                    // Biểu thức hằng: 10
final int inputLength = "hello".length();// Giá trị từ lời gọi method
~~~

`fixed` là ví dụ về biến `final` kiểu primitive được khởi tạo bằng một **constant expression**. Còn `inputLength` cần lời gọi method; `final` chỉ đảm bảo biến không được gán lại, **không biến method call thành constant expression**.

Trong Java, một *constant variable* có định nghĩa chặt hơn: biến `final` thuộc kiểu nguyên thủy hoặc `String`, khởi tạo bằng một constant expression. Nhờ phân biệt này, bạn sẽ hiểu vì sao một số vị trí đòi hằng số lúc biên dịch (như `case` label truyền thống) không chấp nhận mọi biến `final`.

Ví dụ:

~~~java
final int ten = 10;
final int eleven = Integer.parseInt("11");

// Hợp lệ trong switch truyền thống:
int x = 10;
switch (x) {
    case ten -> System.out.println("TEN");
    default -> System.out.println("OTHER");
}
// Không thể dùng eleven làm case label hằng số tại compile time.
~~~

Đừng đánh đồng `final`, `static final` và “object bất biến”: đó là các khái niệm liên quan nhưng **không đồng nghĩa**.

## 8. final và lambda: effectively final

Java 17 cho phép lambda/anonymous class **capture** một biến cục bộ nếu biến đó được khai báo `final` **hoặc là effectively final** (không được gán lại sau lần khởi tạo/gán hợp lệ).

~~~java
int factor = 4; // Không ghi final, nhưng không gán lại
java.util.function.IntUnaryOperator times =
        value -> value * factor;
System.out.println(times.applyAsInt(3)); // 12
~~~

Dù `factor` không ghi `final`, compiler thấy nó không bị gán lại nên cho phép capture.

Nếu bạn thêm `factor = 5;` sau khai báo, biến không còn effectively final và lời gọi lambda sử dụng nó sẽ khiến chương trình không biên dịch. Cách xử lý là thiết kế giá trị capture cố định, hoặc nếu thật sự cần trạng thái thay đổi thì mô hình hóa một object quản lý trạng thái phù hợp. Không nên bọc biến mutable tùy tiện vào mảng chỉ để qua kiểm tra compiler.

## 9. Chương trình Java 17 chạy độc lập

Tạo tệp chính xác **`FinalOnceDemo.java`**:

~~~java
public final class FinalOnceDemo {
    private static final int MAX_RETRIES = 3;
    private static final String APP_NAME;

    static {
        APP_NAME = "Study";
    }

    private final int id;
    private final StringBuilder label;

    private FinalOnceDemo(int id) {
        this.id = id;
        this.label = new StringBuilder("item");
    }

    static String classify(int score) {
        final String outcome; // Blank final local
        if (score >= 50) {
            outcome = "PASS";
        } else {
            outcome = "FAIL";
        }
        return outcome;
    }

    static int twice(final int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        final int attempts = 2;
        System.out.println("attempts=" + attempts);
        System.out.println("max=" + MAX_RETRIES);
        System.out.println("app=" + APP_NAME);
        System.out.println("pass=" + classify(70));
        System.out.println("fail=" + classify(40));

        FinalOnceDemo object = new FinalOnceDemo(7);
        object.label.append("-updated"); // Object mutable
        System.out.println("id=" + object.id);
        System.out.println("label=" + object.label);

        final int[] counts = {1, 2};
        counts[0] = 9; // Không gán lại biến counts
        System.out.println("array=" + counts[0] + "," + counts[1]);

        final StringBuilder text = new StringBuilder("A");
        text.append("B");
        System.out.println("ref=" + text);
        System.out.println("twice=" + twice(5));

        int sum = 0;
        for (final int value : new int[] {1, 2, 3}) {
            sum += value;
        }
        System.out.println("sum=" + sum);

        int factor = 4; // Effectively final: không gán lại
        java.util.function.IntUnaryOperator multiply =
                number -> number * factor;
        System.out.println("lambda=" + multiply.applyAsInt(3));
    }
}
~~~

Tại thư mục chứa tệp, dùng **JDK 17 trở lên**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FinalOnceDemo.java
java -cp . FinalOnceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FinalOnceDemo.java
java -cp . FinalOnceDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
attempts=2
max=3
app=Study
pass=PASS
fail=FAIL
id=7
label=item-updated
array=9,2
ref=AB
twice=10
sum=6
lambda=12
~~~

Những điểm cần tự đối chiếu:

1. `classify` gán một lần ở **đúng một** trong hai nhánh, nên `final outcome` hợp lệ.
2. `id` và `label` là instance final fields được gán khi chạy constructor.
3. `APP_NAME` là static final field được gán trong static initializer.
4. `object.label.append(...)`, `counts[0] = 9` và `text.append(...)` **không phải phép gán lại biến final**.
5. `factor` là effectively final nên có thể được lambda sử dụng.

Đây là một ví dụ duy nhất có thể lưu, biên dịch và chạy độc lập; không cần thư viện hoặc dự án build bên ngoài.

## 10. Các lỗi điển hình và cách xử lý

| Hiện tượng | Vì sao? | Sửa thế nào? |
|---|---|---|
| `final int x = 1; x = 2;` | Gán lần thứ hai | Chỉ gán một lần, hoặc bỏ `final` nếu phải thay đổi |
| `final int x; println(x);` | Đọc blank final chưa gán | Gán chắc chắn trước khi đọc |
| `final int x; if (c) x = 1; println(x);` | Nhánh `c=false` chưa gán | Thêm nhánh `else`/đường xử lý phù hợp |
| `final int x; x = 1; x = 1;` | Gán lại dù cùng giá trị | Bỏ phép gán thứ hai |
| `final int i = 0;` rồi `i++` | Phép tăng phải gán lại `i` | Dùng biến đếm không final |
| Constructor quên gán một blank final field | Không bảo đảm khởi tạo trên mọi đường hoàn thành bình thường | Khởi tạo field hoặc sửa constructor |
| `final List ...` rồi gọi API thêm phần tử | Có thể **hợp lệ**; chỉ object đổi | Dùng collection bất biến nếu cần bất biến thật |
| Lambda dùng biến cục bộ đã gán lại | Không còn effectively final | Tách dữ liệu capture cố định hoặc thiết kế lại |
| `final String s = null;` rồi muốn gán s thành chuỗi | `s` đã được gán null một lần | Chọn giá trị đúng lúc khởi tạo; không dùng null làm giá trị tạm |
| Dùng final method-local như constant expression dù initializer gọi method | Final không tự biến kết quả thành hằng compile-time | Dùng constant expression ở vị trí yêu cầu |

Một lỗi kiểu `cannot assign a value to final variable` thường có nghĩa compiler đã nhận diện **biến cụ thể bị gán lại**, không phải cấm thay đổi mọi thứ liên quan đến đối tượng.

## 11. Bài tập có đáp án

### Bài A — final gán ở if/else

~~~java
final String state;
if (ok) {
    state = "ON";
} else {
    state = "OFF";
}
System.out.println(state);
~~~

**Đáp án:** hợp lệ nếu `ok` là boolean đã khai báo. Mỗi đường chạy gán `state` một lần trước khi in.

### Bài B — phân biệt biến và object

~~~java
final StringBuilder sb = new StringBuilder("Hi");
sb.append("!");
// sb = new StringBuilder("Bye");
System.out.println(sb);
~~~

**Đáp án:** in `Hi!`; `append` hợp lệ, gán lại `sb` không hợp lệ.

### Bài C — final array có bất biến không?

~~~java
final int[] values = {1, 2};
values[0] = 7;
System.out.println(values[0]);
~~~

**Đáp án:** in `7`. Biến `values` không đổi tham chiếu nhưng phần tử mảng vẫn có thể đổi.

### Bài D — tham số final

~~~java
static int plusOne(final int x) {
    // x++; // Sai
    return x + 1;
}
~~~

**Đáp án:** `return x + 1;` hợp lệ vì không thay đổi `x`. `x++` không hợp lệ vì gán lại tham số final.

### Bài E — capture trong lambda

~~~java
int factor = 3;
java.util.function.IntUnaryOperator op = x -> x * factor;
// factor = 4;
~~~

**Đáp án:** hợp lệ nếu không thêm phép gán lại. Nếu bỏ comment của `factor = 4;`, compiler không cho lambda capture biến vì nó không còn effectively final.

## 12. Checklist ghi nhớ

- [ ] `final` cấm gán lại **biến** sau khi được gán hợp lệ, không mặc định cấm thay đổi object.
- [ ] Blank final local có thể khai báo trước, rồi gán một lần trên từng đường đi hợp lệ.
- [ ] Biến final cần được gán chắc chắn trước khi đọc.
- [ ] Câu lệnh `x++`, `x += 1`, `x = x` cũng là gán lại.
- [ ] Enhanced for có thể dùng `final` cho biến phần tử, khác với biến đếm cần `i++`.
- [ ] Blank final field được khởi tạo hợp lệ tại điểm khai báo, initializer hoặc constructor phù hợp.
- [ ] Phân biệt `final` variable với **compile-time constant** và **immutable object**.
- [ ] Hiểu final parameter và effectively final khi capture trong lambda.
- [ ] Tự biên dịch/chạy `FinalOnceDemo.java` và giải thích toàn bộ output.

**Kết luận:** `final` đặt trên biến bảo đảm **không gán lại biến sau khi đã gán một lần hợp lệ**. Java kiểm tra điều này ngay lúc biên dịch, bao gồm các nhánh điều khiển và các đường khởi tạo. Với tham chiếu, `final` cố định **giá trị tham chiếu**, không tự làm dữ liệu bên trong bất biến.