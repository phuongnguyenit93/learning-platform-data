# Phân biệt `final`, `effectively final` và bất biến (immutability) trong Java

Ba khái niệm **`final`**, **`effectively final`** và **bất biến (immutability)** thường xuất hiện cùng nhau trong Java, nhưng chúng trả lời ba câu hỏi khác nhau:

- **`final`**: Java có **cấm gán lại** biến, field, tham số; hoặc cấm override/kế thừa một khai báo cụ thể không?
- **`effectively final`**: Một biến local hoặc tham số **không ghi `final`**, nhưng có thực tế được gán theo cách mà nếu thêm `final` thì chương trình vẫn hợp lệ không?
- **Immutable object**: Sau khi tạo, **trạng thái quan sát được** của object có thể bị thay đổi qua những API/alias hợp lệ không?

Ví dụ:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core"); // Hợp lệ: sửa nội dung object.
// builder = new StringBuilder(); // Không hợp lệ: gán lại biến final.
~~~

`builder` là **biến tham chiếu final**, nhưng `StringBuilder` là **object mutable**. Trong khi đó:

~~~java
String name = "Mai";
Runnable greet = () -> System.out.println(name);
~~~

`name` không được khai báo `final` nhưng **effectively final**, nên lambda có thể capture nó. Giá trị String mà `name` tham chiếu cũng là immutable, nhưng đó là **một tính chất riêng của String**, không phải hệ quả của effectively final.

Bài này thuộc Java Core — **Class & Object / Từ khóa final**, sử dụng Java 17+. Ta sẽ khảo sát đầy đủ từ local variables, parameters, blank final fields, lambda và anonymous classes đến object graph, defensive copying, records, API design và giới hạn trong lập trình đa luồng.

## 1. Mục tiêu học tập

Sau khi học, bạn sẽ có thể:

1. Giải thích chính xác `final` khi áp dụng cho **local variable, method parameter, instance field, static field, method và class**.
2. Phân biệt **không được gán lại reference** với **không được sửa object**.
3. Xác định khi nào một local variable/parameter **effectively final** theo quy tắc Java.
4. Hiểu vì sao local variables được lambda hoặc local/anonymous inner class sử dụng phải final/effectively final.
5. Dự đoán trường hợp gán trong `if/else` hoặc vòng lặp còn đạt effectively final hay không.
6. Phân biệt **final field**, **immutable class**, **shallow immutability** và **deep immutability**.
7. Hiểu vì sao `final List`, `final int[]`, `record` không tự bảo đảm bất biến sâu.
8. Biết dùng **defensive copy**, value objects và API chỉ đọc khi object chứa mutable references.
9. Hiểu quan hệ giữa `final`, **constructor invariant**, **safe publication** và **thread safety**, không khẳng định quá mức.
10. Nắm giới hạn `final` khi kế thừa/override và phân biệt với `static`.
11. Tự chạy các chương trình Java 17+ với stdout, dự đoán chính xác dòng hợp lệ và lỗi compiler.
12. Biết chọn giữa **mutation tại chỗ**, **trả object mới** và **biến local mới** trong code thực tế.

## 2. Bảng so sánh cốt lõi

| Khía cạnh | `final` | `effectively final` | Immutable object |
| --- | --- | --- | --- |
| Là gì? | Từ khóa trong khai báo Java | Tính chất của biến local/parameter theo cách gán | Đặc tính của thiết kế object |
| Áp dụng chính | Biến, field, parameter, method, class | Local variables và parameters, đặc biệt khi capture | Instance và trạng thái quan sát được |
| Chặn gán lại một biến? | Có, sau khi khởi tạo hợp lệ | Biến thực tế không bị gán lại theo quy tắc; compiler không tự khóa bằng từ khóa | Không nhất thiết: biến tham chiếu tới immutable object vẫn có thể gán lại |
| Chặn sửa mutable object qua alias? | **Không** | **Không** | Có, trong phạm vi hợp đồng bất biến được thiết kế |
| Có yêu cầu ghi từ khóa? | Có, `final` | Không | Không nhất thiết; class có thể bảo đảm bất biến qua API |
| Lambda capture local? | Được nếu definite assignment hợp lệ | Được | Bất biến không phải điều kiện bắt buộc của capture |
| Có thể áp dụng cho class/method? | Có | Không | Nói về object/class design, không phải modifier |
| Ví dụ | `final List<String> xs` | `int x = 1;` không gán lại | `String`, `LocalDate`, value object được thiết kế đúng |

**Quy tắc nhớ:** `final` và effectively final chủ yếu nói về **khả năng gán lại một chỗ lưu giá trị**. Immutability nói về **trạng thái của object được tham chiếu**.

## 3. `final` trên biến primitive

Một biến primitive `final` không được gán giá trị khác sau khi đã được khởi tạo hợp lệ.

~~~java
final int maxAttempts = 3;
// maxAttempts = 4; // Lỗi biên dịch.
~~~

Biến `maxAttempts` chứa giá trị primitive `int 3`; nó không phải reference tới một object mutable.

Những cách dùng hợp lệ:

~~~java
final double piApproximation = 3.14;
final boolean enabled = true;
final char grade = 'A';
~~~

Cố gán lại, kể cả gán **chính giá trị cũ**, vẫn là assignment bị cấm:

~~~java
final int x = 5;
// x = 5; // Vẫn lỗi biên dịch.
~~~

Điểm quan trọng: `final` không có nghĩa compiler kiểm tra “giá trị mới có khác giá trị cũ không”. Nó ngăn **những phép gán lại không hợp lệ theo quy tắc definite assignment/final variable**.

### Tăng/giảm cũng là sửa biến

~~~java
final int count = 10;
// count++;  // Lỗi.
// ++count;  // Lỗi.
// count += 2; // Lỗi.
~~~

`++`, `--` và compound assignment `+=` đều cố cập nhật một biến đã final, dù không có dấu `=` riêng biệt ở dạng thường.

## 4. `final` trên biến tham chiếu: giữ reference, không đóng băng object

Xét:

~~~java
final java.util.ArrayList<String> names =
        new java.util.ArrayList<>();

names.add("Mai");      // Hợp lệ.
names.add("An");       // Hợp lệ.
// names = new java.util.ArrayList<>(); // Lỗi.
~~~

Về mặt logic:

~~~text
Biến names (final)
+--------------------+
| reference -> List#1|
+---------+----------+
          |
          v
      List#1 mutable
      ["Mai", "An"]
~~~

Biến `names` giữ nguyên reference tới **List#1**, nhưng nội dung List#1 có thể thay đổi. `final` không ngăn `names.clear()` hoặc `names.set(0, "Binh")` nếu List implementation cho phép.

Một alias khác cũng có thể sửa cùng object:

~~~java
final StringBuilder text = new StringBuilder("A");
StringBuilder alias = text;
alias.append("B");
// text.toString() cho "AB".
~~~

`text` không hề được gán lại. Object được chia sẻ mới là thứ bị sửa. Đây là một trong những khác biệt quan trọng nhất của bài.

## 5. Ví dụ chạy: final primitive và final reference

Tạo tệp **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final int limit = 3;
        final List<String> names = new ArrayList<>();
        final StringBuilder builder = new StringBuilder("Java");

        names.add("Mai");
        names.add("An");
        builder.append(" Core");

        System.out.println("limit=" + limit);
        System.out.println("names=" + names);
        System.out.println("builder=" + builder);

        // limit = 4;                  // Lỗi: final primitive.
        // names = new ArrayList<>();  // Lỗi: final reference.
        // builder = new StringBuilder("X"); // Lỗi.
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Stdout:

~~~text
limit=3
names=[Mai, An]
builder=Java Core
~~~

Kết quả chứng minh: **`final` trên reference không cấm gọi mutator**. Nếu cần nội dung bất biến, phải chọn immutable type hoặc API không cho thay đổi trạng thái và ngăn các alias mutable.

## 6. `final` trên method parameter

Tham số có thể khai báo `final`:

~~~java
static void printLength(final String text) {
    System.out.println(text.length());
    // text = "other"; // Lỗi biên dịch.
}
~~~

`final` ở đây ngăn code của method **gán lại biến tham số `text`**. Nó không thay đổi cơ chế truyền tham số: Java vẫn **pass-by-value**, và với reference parameter thì giá trị được sao chép là **reference value**.

Nếu tham số trỏ object mutable:

~~~java
static void appendSuffix(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder(); // Lỗi.
}
~~~

thì `append` hợp lệ vì sửa **object**, không gán lại **tham số**.

### `final` parameter không biến method thành pure

Một method có `final` parameter vẫn có thể:

- Sửa mutable object mà parameter tham chiếu tới.
- Thay static field.
- Ghi file hoặc gọi API mạng.
- Thay state của object nhận lời gọi qua `this`.
- Ném exception.

Vì vậy `final` giúp giới hạn **rebinding của parameter**, chứ không chứng minh “method không gây side effect”.

## 7. Blank final local variable: khai báo trước, gán đúng một lần

Java cho phép **blank final local variable**: khai báo `final` nhưng chưa gán initializer ngay tại dòng khai báo.

~~~java
final int score;
score = 90;
System.out.println(score);
// score = 95; // Lỗi: đã gán.
~~~

Điều kiện quan trọng là **definite assignment (DA)**: compiler phải chứng minh biến được gán trước khi đọc; với final variable phải thỏa các quy tắc gán đúng một lần trên những đường điều khiển được xét.

Ví dụ if/else:

~~~java
final String label;
if (score >= 50) {
    label = "PASS";
} else {
    label = "FAIL";
}
System.out.println(label);
~~~

Mọi đường đi qua cấu trúc if/else đều gán `label` một lần trước `println`, nên hợp lệ.

Ngược lại:

~~~java
final String label;
if (score >= 50) {
    label = "PASS";
}
// System.out.println(label); // Lỗi: có đường chưa gán.
~~~

Nó không đạt definite assignment khi `score < 50`.

### Đừng diễn giải “final = phải gán ở dòng khai báo”

Một local `final` có thể được khởi tạo muộn nhưng phải tuân theo **definite assignment/unassignment rules**. Điều quan trọng là không cho phép một đường thực thi gán lại final variable sau khi đã được gán hợp lệ.

## 8. Ví dụ chạy: blank final qua hai nhánh

Lưu **`BlankFinalLocalDemo.java`**:

~~~java
public class BlankFinalLocalDemo {
    static String category(int score) {
        final String label;

        if (score >= 80) {
            label = "HIGH";
        } else if (score >= 50) {
            label = "PASS";
        } else {
            label = "RETRY";
        }

        return label;
    }

    public static void main(String[] args) {
        System.out.println(category(90));
        System.out.println(category(60));
        System.out.println(category(20));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlankFinalLocalDemo.java
java BlankFinalLocalDemo
~~~

Stdout:

~~~text
HIGH
PASS
RETRY
~~~

Biến `label` được khai báo final, chưa có giá trị ngay. Mỗi lần method được gọi, chương trình đi qua **một nhánh** và gán `label` đúng một lần. Đoạn code này hợp lệ dù tên `label` có thể nhận các giá trị khác nhau **ở các lần gọi method khác nhau**.

**Không nhầm:** `final` chỉ áp dụng đối với **biến trong mỗi lần gọi**, không biến `label` thành một hằng số toàn ứng dụng.

## 9. `effectively final` là gì?

Một local variable hoặc parameter **không khai báo `final`** có thể được xem là **effectively final** nếu cách gán của nó thỏa điều kiện mà việc thêm `final` vào khai báo sẽ không gây lỗi biên dịch liên quan tới phép gán.

~~~java
String greeting = "Xin chào"; // Không có final.
System.out.println(greeting);
// Không có phép gán lại greeting.
~~~

`greeting` effectively final. Vì thế nó có thể được capture bởi lambda hay local/anonymous class nếu các điều kiện khác đáp ứng.

**Effectively final không phải modifier:** Không có cú pháp:

~~~java
// effectively final int x = 1; // Sai: Java không có modifier này.
~~~

Compiler **suy ra** tính chất ấy từ các phép gán trong mã nguồn.

### Vì sao Java có khái niệm này?

Trước Java 8, nhiều tình huống capture local variables bởi anonymous inner classes yêu cầu viết từ khóa `final`. Từ Java 8, local variable hoặc parameter **effectively final** cũng đủ cho những tình huống capture theo quy tắc hiện hành.

Mục đích là giảm cú pháp bắt buộc trong trường hợp biến thực tế không đổi, **không phải cho phép lambda âm thầm sửa biến local của scope bao ngoài**.

## 10. Ví dụ đơn giản: effectively final và lambda

Tạo file **`EffectivelyFinalLambdaDemo.java`**:

~~~java
public class EffectivelyFinalLambdaDemo {
    public static void main(String[] args) {
        String prefix = "Xin chào";
        String person = "Mai";

        Runnable task = () ->
                System.out.println(prefix + ", " + person + "!");

        task.run();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EffectivelyFinalLambdaDemo.java
java EffectivelyFinalLambdaDemo
~~~

Stdout:

~~~text
Xin chào, Mai!
Xin chào, Mai!
~~~

`prefix` và `person` không ghi `final`, nhưng đều được gán tại khai báo và **không gán lại**, nên effectively final. Lambda sử dụng chúng hợp lệ.

Nếu bổ sung:

~~~java
person = "An";
~~~

vào method có lambda capture `person` ở trên, compiler từ chối: local variable được tham chiếu từ lambda phải **final hoặc effectively final**. Không quan trọng dòng gán lại nằm trước hay sau lời gọi `task.run()`; compiler xét tính chất trong mã nguồn, không chỉ một đường thực thi mà người viết cho là “sẽ chạy”.

## 11. Vì sao gán lại biến làm mất effectively final?

Xét:

~~~java
int amount = 10;
amount = 20;

Runnable task = () -> System.out.println(amount);
~~~

Đây là **đoạn cố ý không biên dịch**. `amount` có initializer 10 rồi bị gán lại 20. Nó không effectively final, nên không được capture bởi lambda.

Đổi thành:

~~~java
final int amount = 20;
Runnable task = () -> System.out.println(amount);
~~~

hoặc:

~~~java
int amount = 20;
Runnable task = () -> System.out.println(amount);
~~~

đều hợp lệ. **Trọng tâm** là biến local được capture không bị gán lại sau khi khởi tạo theo các quy tắc.

### Có thể capture một local không khai báo final nếu nó được gán sau?

Có. Một local chưa được khởi tạo tại dòng khai báo có thể effectively final nếu nó **được gán một lần trên các đường đi hợp lệ** và definite assignment trước khi được dùng.

Ví dụ:

~~~java
String message;

if (System.getProperty("mode") == null) {
    message = "DEFAULT";
} else {
    message = "CONFIGURED";
}

Runnable task = () -> System.out.println(message);
~~~

Đoạn minh họa này có thể biên dịch: `message` không có initializer, được gán bởi đúng một nhánh if/else trên mỗi đường và sau đó không bị gán lại. Không được lẫn với trường hợp **đã gán ở khai báo** rồi còn gán thêm.

## 12. Ví dụ chạy: effectively final dù gán trong nhánh

Lưu **`EffectivelyFinalBranchesDemo.java`**:

~~~java
public class EffectivelyFinalBranchesDemo {
    static Runnable createGreeting(boolean formal) {
        String greeting;

        if (formal) {
            greeting = "Kính chào";
        } else {
            greeting = "Chào";
        }

        return () -> System.out.println(greeting + " bạn!");
    }

    public static void main(String[] args) {
        Runnable formal = createGreeting(true);
        Runnable informal = createGreeting(false);

        formal.run();
        informal.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EffectivelyFinalBranchesDemo.java
java EffectivelyFinalBranchesDemo
~~~

Stdout:

~~~text
Kính chào bạn!
Chào bạn!
~~~

Ở mỗi lần gọi `createGreeting`, biến `greeting` được gán một giá trị theo nhánh tương ứng. Sau đó nó **không bị gán lại**. Lambda trả về giữ được giá trị cần dùng dù lần gọi `createGreeting` đã kết thúc.

Kết quả không có nghĩa lambda chứa reference tới một biến local còn có thể tùy ý được cập nhật về sau. Nó thực hiện việc capture theo ngữ nghĩa Java dành cho những giá trị local đủ điều kiện.

## 13. Bảng nhận diện effectively final

| Đoạn local code | Effectively final? | Lý do |
| --- | --- | --- |
| `int n = 1;` và không gán lại | Có | Chỉ một assignment tại khởi tạo |
| `int n = 1; n = 2;` | Không | Có assignment thứ hai |
| `int n = 1; n++;` | Không | Increment cập nhật biến |
| `int n; n = 1;` và không gán lại | Có nếu DA thỏa | Blank local được gán một lần |
| `int n; if (flag) n=1; else n=2;` | Có nếu DA thỏa | Mỗi nhánh gán một lần |
| `int n=1; if(flag) n=2;` | Không | Đã có initializer, vẫn có đường gán thêm |
| `List<String> xs = new ArrayList<>(); xs.add("A");` | Có thể có | Không gán lại **xs**, chỉ sửa object |
| `int[] a={1}; a[0]=2;` | Có thể có | Không gán lại biến `a` |
| `StringBuilder b=new StringBuilder(); b.append("X");` | Có thể có | Chỉ thay object |
| Parameter `int n` không gán lại | Có | Parameter effectively final |
| Parameter `int n; n++;` trong method | Không | Parameter bị cập nhật |

**“Có thể có”** nhấn mạnh rằng cần kiểm tra **toàn bộ phần mã liên quan**: nếu biến ở một chỗ khác còn bị gán lại, kết luận sẽ đổi.

### Đặc biệt: cập nhật field khác với cập nhật local

~~~java
class Counter {
    int value;

    void run() {
        Counter target = this;
        target.value++; // target vẫn effectively final.
    }
}
~~~

Biến `target` vẫn giữ cùng reference value, trong khi field `value` của Counter object đã thay đổi.

## 14. Effectively final của method parameter

Một parameter không ghi `final` nhưng không bị gán lại trong method có thể effectively final:

~~~java
static Runnable report(int value) {
    return () -> System.out.println(value);
}
~~~

Đây là method minh họa, có thể được đặt trong class hợp lệ. `value` là effectively final, cho nên lambda được trả về vẫn có thể sử dụng nó.

Phản ví dụ:

~~~java
static Runnable invalid(int value) {
    value++;
    // return () -> System.out.println(value); // Lỗi nếu bỏ comment.
    return () -> System.out.println("not captured");
}
~~~

Dòng `value++` khiến parameter không effectively final, dù cú pháp khai báo không có `final`.

### So sánh với `final` parameter

~~~java
static Runnable report(final int value) {
    return () -> System.out.println(value);
}
~~~

Cũng hợp lệ. Trong trường hợp không có phép gán lại, **có hoặc không ghi `final` không làm đổi giá trị được in**. `final` có ích để làm ràng buộc rõ ràng ngay tại khai báo và khiến compiler từ chối những phép gán lại được thêm về sau.

## 15. Lambda capture local và sửa object mutable

Một lambda có thể capture **reference variable effectively final** nhưng vẫn sửa object mà biến ấy tham chiếu:

~~~java
StringBuilder builder = new StringBuilder("A");

Runnable append = () -> builder.append("B");
append.run();
append.run();

System.out.println(builder);
~~~

Đoạn minh họa in `ABB` khi đặt vào main hợp lệ. `builder` không bị gán lại; object StringBuilder có state thay đổi hai lần.

Do đó:

> **Lambda capture yêu cầu local variable final/effectively final, chứ không yêu cầu object được capture là immutable.**

Điểm này cũng giải thích vì sao một lambda có thể thay một `AtomicInteger` hoặc field của object, nhưng không được trực tiếp gán lại local variable của scope bao ngoài.

## 16. Ví dụ chạy: lambda cập nhật object đã capture

Lưu file **`CapturedMutableObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CapturedMutableObjectDemo {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        Runnable first = () -> events.add("A");
        Runnable second = () -> events.add("B");

        first.run();
        second.run();

        System.out.println(events);
        System.out.println("size=" + events.size());

        // events = new ArrayList<>(); // Nếu bỏ comment, lỗi capture:
        // events sẽ không còn effectively final.
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedMutableObjectDemo.java
java CapturedMutableObjectDemo
~~~

Stdout:

~~~text
[A, B]
size=2
~~~

`events` effectively final nên được capture. Cả hai lambdas dùng cùng reference List. Gọi `add` là sửa object, không gán lại `events`.

**Lưu ý về đồng thời:** Nếu chạy hai lambdas này trên hai threads thay vì gọi tuần tự như ví dụ, ArrayList không tự thread-safe chỉ vì reference effectively final. Cần synchronization/concurrent collection hoặc thiết kế ownership đúng.

## 17. Local class và anonymous class cũng có quy tắc capture

Không chỉ lambda. Một **local class** hoặc **anonymous inner class** có thể tham chiếu local variable/parameter từ scope bao ngoài khi chúng final hoặc effectively final theo quy tắc Java.

Ví dụ Java 17:

~~~java
int prefix = 10;

java.util.function.IntSupplier supplier =
        new java.util.function.IntSupplier() {
            @Override
            public int getAsInt() {
                return prefix + 2;
            }
        };
~~~

`prefix` không ghi final nhưng không bị gán lại nên anonymous class sử dụng được.

Đây không phải một lambda; cú pháp tạo instance của một anonymous class. Cả hai cơ chế capture đều có quy tắc liên quan effectively final, nhưng **`this` trong lambda và `this` trong anonymous class khác nhau**:

- Lambda không tạo một ý nghĩa `this` riêng như anonymous class instance; `this` nếu hợp lệ trỏ tới enclosing instance.
- Trong anonymous class, `this` trỏ tới anonymous class instance.

Không dùng sự giống nhau về capture để suy luận mọi cơ chế dispatch/`this` đều giống.

## 18. Ví dụ chạy: anonymous class capture effectively final

Tạo **`AnonymousCaptureDemo.java`**:

~~~java
import java.util.function.IntSupplier;

public class AnonymousCaptureDemo {
    static IntSupplier multiplyBy(int factor) {
        int adjustment = 1;

        return new IntSupplier() {
            @Override
            public int getAsInt() {
                return factor * 3 + adjustment;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier supplier = multiplyBy(4);
        System.out.println("result=" + supplier.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

Stdout:

~~~text
result=13
~~~

`factor` là parameter effectively final; `adjustment` là local effectively final. Anonymous class được trả về có thể sử dụng cả hai khi `multiplyBy` đã hoàn tất.

Nếu bổ sung phép gán `adjustment = 2;` trong method, biến ấy mất effectively final và truy cập nó trong anonymous class không biên dịch.

## 19. For-loop: biến thay đổi không thể được capture trực tiếp

Đoạn này cố ý không hợp lệ:

~~~java
for (int i = 0; i < 3; i++) {
    // Runnable task = () -> System.out.println(i); // Lỗi:
    // i tăng qua i++, nên không effectively final.
}
~~~

Biến `i` của vòng for truyền thống được cập nhật trong mỗi iteration. Muốn tạo một lambda giữ **giá trị iteration hiện tại**, dùng một local mới:

~~~java
for (int i = 0; i < 3; i++) {
    final int snapshot = i;
    Runnable task = () -> System.out.println(snapshot);
    task.run();
}
~~~

Lúc này `snapshot` được gán một lần cho mỗi iteration/body execution và không bị gán lại.

### For-each có điểm khác

~~~java
for (String name : java.util.List.of("Mai", "An")) {
    Runnable task = () -> System.out.println(name);
    task.run();
}
~~~

Một enhanced-for variable có thể đủ điều kiện effectively final **ở từng iteration** nếu không bị gán lại trong body. Vì thế nó có thể được lambda capture theo quy tắc Java, dù các vòng lặp lần lượt có `name` khác nhau.

## 20. Ví dụ chạy: tạo danh sách lambda theo từng iteration

Tạo **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int snapshot = i;
            actions.add(() -> System.out.println("index=" + snapshot));
        }

        for (String name : List.of("Mai", "An")) {
            actions.add(() -> System.out.println("name=" + name));
        }

        for (Runnable action : actions) {
            action.run();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

Stdout:

~~~text
index=0
index=1
index=2
name=Mai
name=An
~~~

Mỗi iteration tạo một local `snapshot` không bị gán lại. Trong enhanced-for, `name` cũng thỏa điều kiện capture. Các Runnable được lưu lại và chỉ gọi **sau khi vòng lặp tạo actions hoàn tất**, nhưng chúng vẫn in những giá trị ứng với iteration khi được tạo.

## 21. Khi cần thay đổi số đếm bên trong lambda

Vì local captured variable phải effectively final, đoạn sau không hợp lệ:

~~~java
int count = 0;
// Runnable increment = () -> count++; // Lỗi capture.
~~~

Có một số thiết kế thay thế:

1. **Dùng kết quả pipeline** nếu có thể: `stream.filter(...).count()` hoặc `mapToInt(...).sum()`.
2. **Dùng một mutable accumulator object** trong code tuần tự khi đó là lựa chọn rõ ràng.
3. **Dùng `AtomicInteger`** nếu cần atomic updates và contract phù hợp, nhưng không dùng chỉ để né compiler mà không hiểu state sharing.
4. **Dùng instance field** nếu counter thuộc object có lifetime rõ ràng.
5. **Viết for-loop thường** nếu logic thay đổi local state rõ ràng hơn lambda.

### Ví dụ accumulator qua object

~~~java
java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

java.util.List.of("A", "B", "C").forEach(
        item -> count.incrementAndGet());

System.out.println(count.get());
~~~

Đoạn trên in `3` nếu đặt trong method. Biến `count` vẫn effectively final; **object AtomicInteger** bị cập nhật. Đây là minh họa cơ chế, không phải khuyến cáo thay mọi local int bằng AtomicInteger.

Nếu không có concurrency, một vòng for với `int count` thường dễ đọc hơn. Nếu có concurrency, chỉ một AtomicInteger không tự làm mọi thao tác trên tập dữ liệu và mọi invariant đa biến trở nên atomic.

## 22. Bất biến (immutability) là gì?

Một object được xem là **immutable** khi trạng thái quan sát được của nó **không thay đổi sau khi object được xây dựng hợp lệ**, theo hợp đồng công khai của kiểu đó.

Ví dụ `String`:

~~~java
String text = "Java";
String other = text;
text = text + " Core";
~~~

`String` ban đầu có nội dung `"Java"` không bị sửa. `text` được gán reference đến String kết quả, còn `other` tiếp tục tham chiếu String cũ.

Phân biệt:

- **Object immutable**: state của chính object không bị thay đổi qua những phép toán được cung cấp.
- **Biến final**: biến không được gán lại sau khi đã được khởi tạo hợp lệ.
- **Biến effectively final**: local/parameter không final nhưng không bị gán lại theo các quy tắc.
- **Reference tới mutable object**: có thể giữ reference cố định mà vẫn thay object state.

Một immutable object có thể được tham chiếu qua **biến không final**:

~~~java
String text = "A";
text = "B"; // Hợp lệ: biến không final.
~~~

Thao tác này không làm String object `"A"` trở nên mutable.

## 23. Ví dụ chạy: String immutable, StringBuilder mutable

Lưu **`ImmutableVsMutableDemo.java`**:

~~~java
public class ImmutableVsMutableDemo {
    public static void main(String[] args) {
        final String first = "A";
        String stringAlias = first;

        String result = first.concat("B");
        System.out.println("first=" + first);
        System.out.println("alias=" + stringAlias);
        System.out.println("result=" + result);

        final StringBuilder builder = new StringBuilder("A");
        StringBuilder builderAlias = builder;
        builder.append("B");

        System.out.println("builder=" + builder);
        System.out.println("builderAlias=" + builderAlias);
        System.out.println("sameBuilder=" + (builder == builderAlias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
~~~

Stdout:

~~~text
first=A
alias=A
result=AB
builder=AB
builderAlias=AB
sameBuilder=true
~~~

`first.concat("B")` không sửa String ban đầu; nó cho kết quả String có nội dung `"AB"`. `StringBuilder.append("B")` sửa state của StringBuilder object, nên alias cùng thấy `"AB"`.

**Không được kết luận “`final` làm String bất biến”.** `String` đã có immutable semantics ngay cả khi biến tham chiếu của nó không final.

## 24. Thiết kế immutable class cơ bản

Một immutable value object thường có:

1. Class `final` hoặc chiến lược không cho subclass phá invariants/immutability.
2. Fields `private final`.
3. Validation và chuẩn hóa dữ liệu trong constructor/factory.
4. Không cung cấp mutator làm thay đổi state sau khởi tạo.
5. Không làm lộ mutable fields hay references có thể thay state từ bên ngoài.
6. Nếu có dữ liệu con mutable, **defensive copy** hoặc ownership strategy thích hợp.
7. Không để `this` thoát khỏi constructor trước khi khởi tạo hoàn tất.

Ví dụ:

~~~java
public final class Temperature {
    private final double celsius;

    public Temperature(double celsius) {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("finite temperature required");
        }
        this.celsius = celsius;
    }

    public double celsius() {
        return celsius;
    }

    public Temperature plus(double delta) {
        return new Temperature(celsius + delta);
    }
}
~~~

Đây là **class độc lập nhưng không có main**. `plus` tạo object mới thay vì sửa object cũ. Constructor kiểm tra `Double.isFinite` nên nếu phép cộng tạo infinity hoặc NaN, constructor ném exception thay vì tạo Temperature không hợp lệ.

### Có phải tất cả immutable classes đều phải final?

Không phải mọi thiết kế immutable đều **bắt buộc** dùng `final class`, nhưng `final` là cách đơn giản để không cho subclass bổ sung mutable behavior phá đi các giả định về object. Nếu class mở kế thừa, cần kiểm soát kỹ contracts, state exposure và methods overridable. Với value objects nhỏ, `final class` hoặc Java `record` thường giúp ý định rõ.

## 25. Ví dụ chạy: immutable value object trả bản mới

Tạo file **`ImmutableCounterDemo.java`**:

~~~java
public class ImmutableCounterDemo {
    static final class Counter {
        private final int value;

        Counter(int value) {
            if (value < 0) {
                throw new IllegalArgumentException("negative value");
            }
            this.value = value;
        }

        Counter increment() {
            return new Counter(Math.addExact(value, 1));
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter second = first.increment();
        Counter third = second.increment();

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("third=" + third.value());
        System.out.println("same=" + (first == second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableCounterDemo.java
java ImmutableCounterDemo
~~~

Stdout:

~~~text
first=1
second=2
third=3
same=false
~~~

`first.increment()` không sửa object `first`. Nó tạo `second` với value 2, rồi `third` có value 3. `first == second` false vì đây là hai objects riêng. Ví dụ cho thấy **immutable design có thể đi cùng `final` fields**, nhưng ý nghĩa “không sửa state” đến từ **API trả object mới** và việc không làm lộ mutator.

## 26. Shallow immutability và deep immutability

Một class có tất cả fields `final` vẫn có thể bị sửa **gián tiếp** qua mutable object graph:

~~~java
class Team {
    private final java.util.List<String> names;

    Team(java.util.List<String> names) {
        this.names = names;
    }

    java.util.List<String> names() {
        return names;
    }
}
~~~

Dù `names` là private final:

- Constructor giữ **cùng List reference** caller truyền vào.
- Caller có thể `source.add("An")` rồi Team quan sát phần tử mới.
- Getter trả nguyên List mutable; caller có thể `team.names().clear()`.
- Field chưa từng được gán lại, nhưng **state mà Team quan sát được** đã thay đổi.

### Deep immutability cần cân nhắc theo từng cấp

~~~text
Team object
  final names -------> List object (mutable)
                         |
                         +-- "Mai" (immutable String)
                         +-- "An"  (immutable String)
~~~

Nếu dùng `List.copyOf(names)` và các elements là String immutable, ta ngăn mutation cấu trúc List qua đường thông thường và tránh alias tới mutable List nguồn. Nếu elements là `Student` objects có setter, copy list **không** deep copy Students.

Không nên phát biểu “`List.copyOf` biến mọi object bên trong thành immutable”. Nó chỉ cung cấp bảo đảm ở **cấp container** theo contract.

## 27. Ví dụ chạy: defensive copy khi nhận và trả dữ liệu

Lưu **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    static final class Team {
        private final List<String> names;

        Team(List<String> input) {
            names = List.copyOf(input);
        }

        List<String> members() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Team team = new Team(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot edit team list");
        }

        System.out.println("team again=" + team.members());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout:

~~~text
input=[Mai, An]
team=[Mai]
cannot edit team list
team again=[Mai]
~~~

Ở đây `List.copyOf(input)` từ chối null source/elements và tạo/nhận một list không sửa được qua các mutator thông thường. Danh sách lưu trong Team không bị ảnh hưởng bởi việc thêm An vào `input` sau khởi tạo. Vì phần tử là immutable `String`, ví dụ tránh được rủi ro sửa element qua alias.

**Không khẳng định `List.copyOf` luôn cấp phát một object mới**: nó có thể tái sử dụng một unmodifiable list thích hợp. Hợp đồng bất biến cấu trúc mới là điều cần quan tâm.

## 28. `final` array là trường hợp dễ nhầm

~~~java
final int[] scores = {80, 90};
scores[0] = 100; // Hợp lệ.
// scores = new int[] {70, 60}; // Lỗi: gán lại reference.
~~~

Array object luôn có mutable elements; `final` chỉ bảo vệ **biến `scores`**.

Nếu cần một class không lộ mảng:

~~~java
final class ScoreBoard {
    private final int[] scores;

    ScoreBoard(int[] input) {
        scores = input.clone();
    }

    int[] snapshot() {
        return scores.clone();
    }
}
~~~

Đây là class minh họa. Khi dùng `int[]`, clone sao chép phần tử primitive nên snapshot array có cấu trúc độc lập. Nhưng với `Person[]`, clone chỉ sao chép các **reference tới Person objects**, không deep copy từng Person.

### Một lớp immutable cần tránh return mutable array trực tiếp

~~~java
int[] getScores() {
    return scores; // Nếu trả nguyên private array, caller có thể sửa.
}
~~~

Ngay cả khi field `private final`, getter ở trên mở đường mutation. Defensive copy thường cần ở cả **input boundary và output boundary**.

## 29. Java `record`: shallowly immutable, không tự deep immutable

Java 17 có records:

~~~java
record Point(int x, int y) {}
~~~

Một record có final component fields và accessor methods; `Point` rất phù hợp làm một value object chứa primitive components.

Nhưng:

~~~java
record Roster(java.util.List<String> names) {}
~~~

component `names` là một **reference**. Nếu caller truyền ArrayList mutable và accessor trả reference đó, content vẫn có thể thay đổi sau record construction.

### Cách xử lý record chứa List

~~~java
record SafeRoster(java.util.List<String> names) {
    SafeRoster {
        names = java.util.List.copyOf(names);
    }
}
~~~

Compact constructor thay reference tham số component bằng list không sửa được cấu trúc, và Java khởi tạo component field từ parameter sau constructor body theo quy tắc record compact constructor. Với String elements immutable, cách này giúp bảo vệ state của Roster.

**Không vì record có fields final mà kết luận mọi component object đã immutable**. Record chỉ hỗ trợ thuận tiện việc xây dựng data carriers; invariant/deep immutability vẫn cần được thiết kế.

## 30. Ví dụ chạy: record cần bảo vệ mutable component

Lưu **`RecordImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordImmutabilityDemo {
    record Roster(List<String> names) {
        Roster {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("record=" + roster.names());

        try {
            roster.names().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list cannot be cleared");
        }

        System.out.println("record again=" + roster.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordImmutabilityDemo.java
java RecordImmutabilityDemo
~~~

Stdout:

~~~text
input=[Mai, An]
record=[Mai]
record list cannot be cleared
record again=[Mai]
~~~

`Roster` record dùng compact constructor để lấy một list có cấu trúc không sửa được. `input` sau đó bị sửa nhưng `roster.names()` vẫn trả `[Mai]`. Caller không thể gọi `clear()` thành công trên list được trả.

Đây là shallow containment phù hợp với phần tử String immutable. Nếu là List chứa mutable elements, cần tiếp tục kiểm tra tầng sâu.

## 31. `final` trên instance field

**Instance final field** phải được khởi tạo đúng theo quy tắc của constructor/initializer; sau đó source Java thông thường không gán lại field được. Ví dụ:

~~~java
class User {
    private final String id;
    User(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }
}
~~~

Đây là một **blank final field**, khác với local effectively final được lambda capture. B144–B145 dạy sâu phân tích mọi nhánh khởi tạo và những vị trí gán final fields; ở bài này chỉ cần nắm sự khác nhau giữa **field gán một lần** và **local không bị gán lại nhưng không viết final**.

## 32. Static final field: hằng số và giới hạn

`static final` kết hợp **field thuộc class** với **không gán lại binding**. Chỉ một số biến final kiểu primitive/`String` khởi tạo bằng constant expression là **constant variables** theo JLS; không phải mọi `static final` đều được inline.

~~~java
static final int MAX_RETRIES = 3;
static final java.time.LocalDate START =
        java.time.LocalDate.of(2026, 1, 1);
~~~

Dòng đầu là compile-time constant candidate, dòng sau được tính lúc khởi tạo runtime. B147 là nơi phân tích đầy đủ constant expression, switch/annotation, class initialization và binary inlining; đây chỉ là ranh giới với immutability.

## 33. `final` method: cấm override, không cấm overload

`final` trên **instance method** ngăn subclass override method ấy, nhưng không ngăn khai một overload khác; `final` không chứng minh method pure hoặc không có side effects.

~~~java
class Parent {
    final void work() {}
    void work(String context) {}
}
~~~

Hai signatures khác nhau đều hợp lệ. Method final cũng không làm object bất biến. B149 là nơi học đầy đủ overriding, static hiding, template method, sealed hierarchy, polymorphism và khi nào khóa extension points.

## 34. `final` class: cấm kế thừa, không tự bất biến

`final class` cấm class khác `extends` nó, **không tự khóa state**:

~~~java
final class Counter {
    private int value;
    void increment() { value++; }
}
~~~

Mặc dù không thể subclass Counter, gọi `increment()` vẫn thay giá trị field. Ngược lại, immutable object có thể tồn tại mà biến tham chiếu không final. Sự khác nhau giữa **hợp đồng kế thừa** và **hợp đồng bất biến dữ liệu** là trọng tâm; B149 dạy chi tiết final method/class.

## 35. Ví dụ chạy: final class vẫn mutable

Tạo **`FinalClassMutableDemo.java`**:

~~~java
public class FinalClassMutableDemo {
    static final class Counter {
        private int value;

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        final Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println("count=" + counter.value());
        System.out.println("type final=" +
                java.lang.reflect.Modifier.isFinal(
                        counter.getClass().getModifiers()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalClassMutableDemo.java
java FinalClassMutableDemo
~~~

Stdout:

~~~text
count=2
type final=true
~~~

Ở đây có **hai nơi dùng `final`**:

1. Nested class `Counter` là final nên không thể subclass.
2. Local variable `counter` là final nên không được gán reference mới.

Cả hai **không cấm** gọi `increment()` làm đổi field `value` của Counter instance.

## 36. `final` và object identity / equality

Một biến final giữ **cùng reference** sau khởi tạo hợp lệ, nhưng identity không đồng nghĩa trạng thái bất biến.

~~~java
final StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");

System.out.println(first == alias); // true
System.out.println(first);          // AB
~~~

Ngược lại, hai immutable values có thể bằng nhau theo `equals()` nhưng là hai objects khác identity:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

`String.equals` so sánh nội dung. **Không dùng `final` để suy luận `==` hoặc equality**. Identity, value equality và immutability là những trục khác nhau.

### Immutable objects có thể chia sẻ an toàn hơn

Nếu object thật sự immutable, nhiều biến/threads có thể cùng đọc nó mà không lo một alias trực tiếp thay đổi state của object. Nhưng **cách publish reference và các dữ liệu liên quan** vẫn phải tuân theo memory-model/visibility rules thích hợp; immutable không phải phép miễn trừ mọi lỗi concurrency.

## 37. `final` field và Java Memory Model: cần hiểu vừa đủ

Java có những bảo đảm đặc biệt về **final fields** trong Java Memory Model. Nếu object được xây dựng đúng cách và **`this` không thoát ra trước khi constructor kết thúc**, giá trị final fields đã khởi tạo có những đảm bảo initialization visibility quan trọng cho threads khác quan sát object.

Tuy nhiên không được rút ra những kết luận quá mạnh:

- **`final` không làm `count++` atomic**.
- **`final` không biến List mutable thành thread-safe**.
- Những thay đổi **sau constructor** lên object mutable được tham chiếu bởi final field vẫn cần visibility/synchronization thích hợp nếu chia sẻ giữa threads.
- Nhiều fields liên quan nhau vẫn có thể cần lock/immutable snapshot để bảo đảm nhất quán.
- Nếu object hoặc `this` bị publish trong lúc constructor chưa hoàn tất, các giả định về safe construction có thể bị phá.
- Reflection/deserialization/unsafe mechanisms có thể có những quy tắc hoặc rủi ro đặc biệt ngoài kiểu code đơn giản này.

### Ví dụ về final reference chứa mutable object

~~~java
class SharedState {
    final java.util.List<String> values =
            new java.util.ArrayList<>();

    void add(String value) {
        values.add(value);
    }
}
~~~

Nếu nhiều threads cùng gọi `add` trên một SharedState instance, `ArrayList` không thread-safe chỉ vì field `values` final. Cần thiết kế concurrency, ownership hoặc immutable copy.

**Thông điệp thực hành:** Final fields có ích cho thiết kế object an toàn và dễ reasoning hơn, nhưng **thread safety là thuộc tính của toàn bộ các thao tác/state sharing**, không phải một từ khóa đơn.

## 38. `final` có phải hằng số không?

**Final variable** bị hạn chế phép gán lại; **compile-time constant variable** còn phải thỏa điều kiện JLS về kiểu primitive/`String` và constant expression.

~~~java
final int runtime = Integer.parseInt("42");
~~~

`runtime` hợp lệ và final, nhưng giá trị được xác định lúc chạy. Nếu cần “ngày hiện tại”, `static final LocalDate TODAY = LocalDate.now()` chỉ chụp ngày khi khởi tạo class, không tự đổi lúc nửa đêm. B147 phân biệt đầy đủ compile-time/runtime constants, còn ở đây không được suy `final` là “object bất biến”.

## 39. Final reference vẫn có thể bằng `null`

`final String name = null;` hợp lệ về luật gán nhưng không có nghĩa `name` non-null hoặc an toàn để gọi methods. `final` và null validation là hai điều kiện độc lập. Khi domain yêu cầu non-null, dùng `Objects.requireNonNull` trong constructor/factory và có tests cho input invalid. Không nhầm final reference với object đã được tạo.

## 40. Final và defensive copies khi constructor nhận mutable input

Khi field `final` giữ tham chiếu đến dữ liệu mutable do caller cung cấp, constructor nên **copy-in** và getter nên cung cấp representation không cho caller sửa state nội bộ.

~~~java
final class Schedule {
    private final java.util.Date date;
    Schedule(java.util.Date date) {
        this.date = new java.util.Date(
                java.util.Objects.requireNonNull(date).getTime());
    }
    java.util.Date date() {
        return new java.util.Date(date.getTime());
    }
}
~~~

Cả hai lần copy ngăn aliases sửa trực tiếp internal `Date`. `List.copyOf` chỉ sao chép **cấu trúc collection**, không deep-copy mutable elements. Các tình huống alias, view/snapshot và ownership được dạy sâu ở bài B146.

## 41. Ví dụ chạy: mutable Date cần copy dù field final

Tạo file **`FinalDateDefensiveCopyDemo.java`**:

~~~java
import java.util.Date;

public class FinalDateDefensiveCopyDemo {
    static final class Snapshot {
        private final Date captured;

        Snapshot(Date source) {
            if (source == null) {
                throw new IllegalArgumentException("source required");
            }
            captured = new Date(source.getTime());
        }

        Date captured() {
            return new Date(captured.getTime());
        }
    }

    public static void main(String[] args) {
        Date source = new Date(1_000L);
        Snapshot snapshot = new Snapshot(source);

        source.setTime(2_000L);

        Date outgoing = snapshot.captured();
        outgoing.setTime(3_000L);

        System.out.println("source=" + source.getTime());
        System.out.println("outgoing=" + outgoing.getTime());
        System.out.println("snapshot=" + snapshot.captured().getTime());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalDateDefensiveCopyDemo.java
java FinalDateDefensiveCopyDemo
~~~

Stdout:

~~~text
source=2000
outgoing=3000
snapshot=1000
~~~

`source` là mutable Date của caller; `Snapshot` sao chép giá trị time khi tạo. Getter trả Date mới, nên sửa `outgoing` cũng không đổi internal Date state. Nhờ vậy Snapshot giữ nghĩa “ảnh chụp thời điểm 1000 milliseconds kể từ epoch” theo ví dụ.

Không khẳng định mọi mutable type đều có thể deep-copy an toàn bằng một constructor đơn giản. Với object graphs có alias/cycle/resources, cần thiết kế ownership và copying policy cụ thể.

## 42. Một object graph có thể chỉ bất biến một phần

Một object graph có thể chỉ **shallow immutable**: field `final List<Student>` và `List.copyOf(source)` ngăn thay reference/list structure, nhưng `Student` mutable vẫn có thể bị sửa qua alias.

Vì vậy, hãy ghi rõ contract: immutable toàn bộ, immutable container hay controlled mutation? Nếu cần deep immutability, chọn immutable element types, deep copies hoặc quản lý quyền sở hữu phù hợp. B146 phân tích sâu các mức aliasing/snapshot; điểm riêng ở đây là **effectively final của biến được capture** không giải quyết mutation ở object graph.

## 43. Khi nào nên dùng `final` nhưng không bắt buộc immutability?

Chọn `final` ngay cả khi object còn mutable khi bạn muốn giữ ổn định **binding** như ID, dependency, private List field, local snapshot hoặc constructor parameter. Điều đó không buộc mọi entity là immutable: một `private final List<String> items = new ArrayList<>();` vẫn có thể được thay đổi bằng các method được kiểm soát.

Ngược lại, dùng **immutable value objects** và defensive copies khi chia sẻ nhiều aliases, truyền kết quả giữa các threads hoặc làm keys. B150 áp dụng toàn bộ các lựa chọn final vào quyết định thiết kế lớp; không nên thêm final theo tỷ lệ/mẫu máy móc.

## 44. Khi nào nên ưu tiên immutable object?

Immutable objects đặc biệt phù hợp với:

- **Value objects** như Money, Quantity, DateRange, Address với hợp đồng cố định.
- Các cấu hình không thay đổi trong vòng đời một operation.
- Dữ liệu trao đổi giữa các threads khi không cần mutation sau tạo.
- Snapshot, audit records, keys trong map/set khi equality/hashCode dựa trên state.
- Những giá trị có nhiều aliases và muốn tránh side effects bất ngờ.
- Hàm thuần có kết quả được xây từ input.

Cần cân nhắc tradeoffs: tạo object mới có thể phát sinh allocation/copying; các mô hình lớn có thể dùng immutable persistent data structures hoặc caching. Tuy nhiên **đừng giả định immutability luôn chậm** — JVM có nhiều tối ưu và lợi ích về reasoning/testability thường đáng kể.

Nếu object cần lifecycle thay đổi rõ ràng, có thể dùng **mutable entity được đóng gói** kết hợp immutable value objects thay vì cố biến mọi entity thành immutable.

## 45. Lỗi compiler thường gặp

| Tình huống | Dạng lỗi / lý do |
| --- | --- |
| Gán lại `final int x` | Cannot assign a value to final variable |
| `final int x;` nhưng đọc trước khi gán | Variable might not have been initialized |
| Blank final field không được gán trong constructor hợp lệ | Might not have been initialized |
| Lambda capture local bị gán lại | Local variables referenced from lambda expression must be final or effectively final |
| Anonymous class capture local bị gán lại | Local variables referenced from an inner class must be final or effectively final |
| Override final method | Cannot override final method |
| `extends` final class | Cannot inherit from final class |
| `final` và `abstract` cùng class/method không phù hợp | Illegal combination of modifiers |
| `final` constructor | Modifier final not allowed for constructor |
| `final` field bị gán ở initializer và thêm lần nữa trong constructor | Cannot assign a value to final variable |

Thông báo thực tế có thể khác theo compiler/version. Hãy kiểm tra **biến được gán ở đâu và bao nhiêu lần, là local/field/parameter hay method/class**, rồi sửa theo ngữ nghĩa.

### Cách xử lý lỗi lambda capture

Nếu local cần thay đổi trước khi tạo lambda:

~~~java
int mutable = 1;
mutable++;
int snapshot = mutable;
Runnable task = () -> System.out.println(snapshot);
~~~

`mutable` không effectively final, nhưng `snapshot` là local mới được gán một lần. Lambda capture `snapshot`. Nếu ý định là lambda đọc state **thay đổi theo thời gian**, nên sử dụng một state-holder object có ownership/synchronization rõ ràng thay vì cố né compiler bằng mẹo khó đọc.

## 46. Ví dụ chạy: snapshot một biến trước lambda

Tạo **`LambdaSnapshotDemo.java`**:

~~~java
public class LambdaSnapshotDemo {
    public static void main(String[] args) {
        int counter = 1;
        counter++;

        final int captured = counter;
        Runnable task = () -> System.out.println("captured=" + captured);

        counter++;
        task.run();

        System.out.println("counter=" + counter);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaSnapshotDemo.java
java LambdaSnapshotDemo
~~~

Stdout:

~~~text
captured=2
counter=3
~~~

`counter` được cập nhật nhiều lần, nên không effectively final. `captured` là final local được gán một lần bằng giá trị `2`. Lambda đọc `captured`, còn `counter` sau đó tăng thành `3`. Đây là **hai biến primitive khác nhau**, không phải hai references tới cùng mutable object.

Nếu `captured` là reference tới một mutable object, snapshot reference vẫn có thể cho thấy thay đổi trạng thái object. Muốn snapshot nội dung immutable, cần copy phù hợp.

## 47. Ví dụ tổng hợp: ba khái niệm trong một chương trình

Tạo file **`FinalEffectivelyImmutableSummaryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FinalEffectivelyImmutableSummaryDemo {
    record Label(String text) {
        Label {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text required");
            }
        }
    }

    public static void main(String[] args) {
        final List<String> mutableList = new ArrayList<>();
        String suffix = "!";

        Runnable add = () -> mutableList.add("Java" + suffix);
        add.run();

        Label immutableLabel = new Label("CORE");
        Label another = new Label(immutableLabel.text() + " 17");

        System.out.println("list=" + mutableList);
        System.out.println("first label=" + immutableLabel.text());
        System.out.println("another=" + another.text());

        // mutableList = new ArrayList<>(); // Không được: final.
        // suffix = "?"; // Nếu bỏ comment, lambda capture lỗi.
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalEffectivelyImmutableSummaryDemo.java
java FinalEffectivelyImmutableSummaryDemo
~~~

Stdout:

~~~text
list=[Java!]
first label=CORE
another=CORE 17
~~~

Ba điểm tương ứng:

1. `mutableList` là **final reference**, nhưng ArrayList object được lambda sửa qua `add`.
2. `suffix` **effectively final** vì không gán lại, nên lambda capture được.
3. `Label` record chứa component String immutable; trong ví dụ không có mutable state lộ ra. `another` là Label object mới, không làm `immutableLabel` đổi.

Chương trình không chứng minh “mọi record đều deep immutable”; chỉ cho thấy một record có **String component** và validation phù hợp.

## 48. Bài tập 1 — Hợp lệ hay lỗi?

Xét:

~~~java
final int a = 10;
final StringBuilder b = new StringBuilder("A");
String c = "C";

b.append("B");

// a = 20;
// b = new StringBuilder();
// c = "D";

Runnable r = () -> System.out.println(c);
~~~

Câu hỏi:

- Dòng `b.append("B")` hợp lệ không?
- Nếu bỏ comment `a = 20` sẽ thế nào?
- Nếu bỏ comment `b = new StringBuilder()` sẽ thế nào?
- Nếu bỏ comment `c = "D"`, lambda có còn hợp lệ không?

**Đáp án:** Append hợp lệ vì chỉ sửa object. Gán lại a/b không hợp lệ do `final`. Gán lại c làm `c` mất effectively final, nên lambda capture c không hợp lệ.

## 49. Bài tập 2 — Biến nào effectively final?

~~~java
int x = 1;
int y;
if (x > 0) {
    y = 10;
} else {
    y = 20;
}
int z = 3;
z++;

Runnable task = () -> System.out.println(x + y);
~~~

**Đáp án:** `x` effectively final (không gán lại); `y` effectively final khi được gán một lần theo nhánh và DA thỏa; `z` **không** effectively final do `z++`. Lambda capture `x` và `y` hợp lệ.

Nếu sửa code để `x++` sau khai báo, `x` mất effectively final và lambda không biên dịch.

## 50. Bài tập 3 — Mảng final có bất biến không?

~~~java
final int[] values = {1, 2};
int[] alias = values;
alias[0] = 9;
System.out.println(values[0]);
~~~

**Đáp án:** In `9`. Biến `values` final giữ cùng array reference, nhưng array mutable. `alias` và `values` cùng trỏ array object. Muốn snapshot độc lập của `int[]`, dùng `clone()` hoặc `Arrays.copyOf` khi phù hợp.

## 51. Bài tập 4 — Record và mutable List

Cho:

~~~java
record Group(java.util.List<String> names) {}

java.util.List<String> input = new java.util.ArrayList<>();
input.add("A");

Group group = new Group(input);
input.add("B");

System.out.println(group.names());
~~~

**Đáp án:** In `[A, B]`. Record component field final nhưng giữ **cùng List reference mutable**. Hãy viết compact constructor dùng `List.copyOf(names)` để bảo vệ cấu trúc và mô tả điều kiện về null, mutable element objects.

## 52. Bài tập 5 — Thiết kế immutable DateRange

Yêu cầu tạo class `DateRange` với:

- Hai fields `private final java.time.LocalDate start` và `end`.
- Constructor dùng `Objects.requireNonNull` cho cả hai.
- Reject `end.isBefore(start)`.
- Getter trả chính LocalDate vì immutable.
- Method `withEnd(LocalDate newEnd)` trả **DateRange mới**.
- Không có public setters.
- Test rằng object cũ không thay đổi sau `withEnd`.

**Gợi ý:** Có thể dùng record `record DateRange(LocalDate start, LocalDate end)` cùng compact constructor validation; record chứa immutable LocalDate components phù hợp với value object này.

## 53. Bài tập 6 — Final method khác immutable class

Cho:

~~~java
final class Counter {
    private int value;

    final void increment() {
        value++;
    }
}
~~~

**Đáp án:** Class không thể bị subclass, method không thể bị override theo quy tắc tương ứng, nhưng Counter object vẫn mutable vì `increment()` làm thay `value`. Không có chuyện hai chữ `final` tự động tạo immutable object.

## 54. Bài tập 7 — Vì sao lambda không thấy “giá trị mới” của local?

Đoạn cố ý lỗi:

~~~java
String status = "PENDING";
Runnable r = () -> System.out.println(status);
status = "DONE";
~~~

Java từ chối vì `status` không effectively final. Muốn báo một snapshot, tạo `String capturedStatus = status;` rồi capture `capturedStatus`. Muốn lambda lấy trạng thái thay đổi tại thời điểm chạy, đặt state ở object có API phù hợp và chú ý concurrency nếu khác threads.

Không dùng mảng một phần tử như một mẹo lách effectively final trong code production khi nó che giấu mutable shared state.

## 55. Checklist tự đánh giá

- [ ] Tôi phân biệt biến primitive final với biến reference final.
- [ ] Tôi hiểu final reference không ngăn mutating method hoặc array element assignment.
- [ ] Tôi biết gán lại cùng giá trị cho final variable vẫn bị cấm.
- [ ] Tôi biết blank final local variable có thể được gán một lần sau khai báo khi DA thỏa.
- [ ] Tôi hiểu mỗi lần gọi method có final local riêng, không phải một constant toàn ứng dụng.
- [ ] Tôi biết effectively final là tính chất **không cần từ khóa**.
- [ ] Tôi phân biệt local có initializer rồi gán tiếp với blank local được gán theo nhánh.
- [ ] Tôi biết method parameter có thể final hoặc effectively final.
- [ ] Tôi biết lambda/anonymous/local classes capture local variables phải final/effectively final.
- [ ] Tôi hiểu mutation object captured không làm local reference mất effectively final.
- [ ] Tôi biết for-index `i++` không effectively final, nhưng local snapshot có thể.
- [ ] Tôi biết enhanced-for variable có thể được capture trong mỗi iteration.
- [ ] Tôi phân biệt immutable `String` và mutable `StringBuilder`.
- [ ] Tôi không suy luận class `final` là immutable.
- [ ] Tôi biết `final` method cấm override, không tự ngăn side effects.
- [ ] Tôi biết constructor không có `final`.
- [ ] Tôi biết blank final instance field phải được khởi tạo qua các constructor hợp lệ.
- [ ] Tôi hiểu `static final` primitive/String constant khác `static final` object reference.
- [ ] Tôi biết record chỉ hỗ trợ shallow immutability theo component references.
- [ ] Tôi biết khi nào cần defensive copy input/output.
- [ ] Tôi phân biệt shallow copy, deep copy, unmodifiable view và immutable element.
- [ ] Tôi hiểu `final` field có memory-model benefits nhưng không tự thread-safe.
- [ ] Tôi biết `final` không thay thế validation/non-null checks.
- [ ] Tôi có thể chọn final local, effectively final capture, immutable value object tùy mục tiêu.
- [ ] Tôi chạy và giải thích được tất cả chương trình Java 17+ trong bài.

**Kết luận:** `final` là **ràng buộc của khai báo**: biến/field/parameter không được gán lại sau khởi tạo hợp lệ; method không bị override, class không bị extends. **`Effectively final`** là tính chất của local variable hoặc parameter không cần ghi final nhưng có thể được capture theo quy tắc Java. **Bất biến** là đặc tính của **object state** do thiết kế API, defensive copying và ownership bảo đảm. Ba khái niệm có thể cùng tồn tại nhưng **không suy ra lẫn nhau**. Nhận diện đúng ranh giới giữa biến, reference và object giúp viết lambda hợp lệ, bảo vệ invariant và chia sẻ dữ liệu Java an toàn hơn.
