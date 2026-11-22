# Biến được bắt giữ và quy tắc effectively final

Trong Java, lambda expression và lớp cục bộ (local class) hoặc lớp ẩn danh (anonymous class) có thể sử dụng biến được khai báo ở phạm vi bên ngoài. Khi một lambda hay lớp như vậy tham chiếu đến biến cục bộ hoặc tham số bên ngoài, biến đó được gọi là **biến được bắt giữ** (captured variable). Biến cục bộ được bắt giữ phải được khai báo bằng `final` hoặc phải là **effectively final** (final một cách hiệu dụng).

Quy tắc này thường xuất hiện khi viết callback, xử lý collection bằng Stream, tạo tác vụ chạy sau, hoặc định nghĩa lớp bên trong một phương thức.

## 1. Effectively final nghĩa là gì?

Một biến là effectively final khi không được khai báo bằng từ khóa `final` nhưng vẫn đáp ứng quy tắc gán của biến final: sau khi biến được khởi tạo hoặc được gán lần đầu theo luồng điều khiển, chương trình không gán lại giá trị cho biến đó. Các phép gán như `=`, `+=`, `-=` và phép tăng/giảm như `++`, `--` đều có thể khiến biến không còn effectively final.

~~~java
int limit = 10;                 // effectively final
Runnable task = () -> System.out.println(limit);
task.run();
~~~

Đoạn mã hợp lệ vì `limit` không bị gán lại sau khi khởi tạo. Không bắt buộc phải thêm `final`; trình biên dịch xác định được tính effectively final từ cách biến được sử dụng.

~~~java
final int limit = 10;           // final tường minh
Runnable task = () -> System.out.println(limit);
task.run();
~~~

Đoạn mã trên cũng hợp lệ. `final` thể hiện rõ ý định và ngăn việc gán lại ngay tại nơi khai báo.

Một biến chưa có giá trị khởi tạo ngay tại khai báo vẫn có thể effectively final nếu nó được gán đúng một lần trên mọi nhánh có thể đi đến điểm sử dụng:

~~~java
String mode;
if (args.length > 0) {
    mode = "provided";
} else {
    mode = "default";
}

Runnable task = () -> System.out.println(mode);
task.run();
~~~

Ở mỗi nhánh, `mode` chỉ được gán một lần và đã có giá trị trước khi lambda sử dụng. Nếu có một nhánh khiến biến chưa được khởi tạo hoặc có phép gán lại sau đó, đoạn mã sẽ không còn đáp ứng điều kiện.

## 2. Những biến nào chịu quy tắc này?

Quy tắc áp dụng khi lambda, local class hoặc anonymous class bắt giữ một biến cục bộ hay tham số từ phạm vi bên ngoài. Các trường hợp thường gặp gồm:

- Biến cục bộ khai báo trong phương thức.
- Tham số phương thức hoặc constructor.
- Tham số của lambda bên ngoài khi một lambda lồng bên trong sử dụng nó.
- Biến được khai báo trong một phương thức rồi được dùng trong local class hoặc anonymous class.

Ví dụ với tham số phương thức:

~~~java
static Runnable createPrinter(String message) {
    return () -> System.out.println(message);
}
~~~

`message` là tham số của `createPrinter`. Vì phương thức không gán lại tham số này, lambda có thể bắt giữ nó. Lambda có thể được chạy sau khi `createPrinter` trả về; vì vậy biến cục bộ không cần tiếp tục tồn tại như một biến cục bộ đang hoạt động của phương thức.

Các trường instance và static không chịu yêu cầu effectively final này. Lambda có thể đọc hoặc cập nhật một trường theo quy tắc truy cập thông thường. Tuy vậy, khả năng cập nhật trường không tự bảo đảm an toàn luồng; nếu nhiều luồng cùng truy cập, vẫn cần thiết kế đồng bộ phù hợp.

## 3. Ví dụ Java chạy hoàn chỉnh

Lưu mã sau thành `EffectivelyFinalDemo.java`. Ví dụ cho thấy lambda bắt giữ một biến số nguyên, anonymous class bắt giữ một chuỗi, và lambda vẫn có thể thay đổi trạng thái của đối tượng được tham chiếu bởi một biến effectively final.

~~~java
import java.util.function.IntUnaryOperator;

public class EffectivelyFinalDemo {
    public static void main(String[] args) {
        int multiplier = 3;
        IntUnaryOperator timesMultiplier = value -> value * multiplier;
        System.out.println(timesMultiplier.applyAsInt(4));

        String prefix = "ID-";
        Runnable printId = new Runnable() {
            @Override
            public void run() {
                System.out.println(prefix + 7);
            }
        };
        printId.run();

        int[] counter = {0};
        Runnable increment = () -> counter[0]++;
        increment.run();
        increment.run();
        System.out.println(counter[0]);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac EffectivelyFinalDemo.java
java EffectivelyFinalDemo
~~~

Kết quả stdout chính xác:

~~~text
12
ID-7
2
~~~

`multiplier` và `prefix` được bắt giữ nhưng không bị gán lại. Biến `counter` cũng effectively final: biến tham chiếu vẫn trỏ đến cùng một mảng. Lệnh `counter[0]++` thay đổi phần tử của mảng, không gán lại biến `counter`. Vì thế ví dụ hợp lệ và in ra `2`.

## 4. Gán lại biến sẽ gây lỗi biên dịch

Một khi biến cục bộ được lambda hoặc lớp lồng bắt giữ, không thể gán lại biến đó, kể cả phép gán nằm sau dòng khai báo lambda:

~~~java
int attempts = 1;
Runnable task = () -> System.out.println(attempts);
attempts = 2; // Lỗi biên dịch: attempts không effectively final
~~~

Lỗi không phụ thuộc vào việc lambda đã chạy hay chưa. Trình biên dịch xét toàn bộ cách sử dụng biến. Phép gán kết hợp như `attempts += 1` và phép tăng như `attempts++` cũng vi phạm quy tắc. Cách sửa tùy ý nghĩa mong muốn:

- Nếu giá trị phải cố định, hãy bỏ phép gán lại hoặc khai báo biến là `final`.
- Nếu mỗi tác vụ cần một giá trị riêng, hãy tạo một biến mới, effectively final, cho tác vụ đó.
- Nếu cần trạng thái thay đổi, hãy cân nhắc một đối tượng có trạng thái hoặc một trường phù hợp; vẫn phải xử lý vấn đề đồng bộ nếu có nhiều luồng.

## 5. Vòng lặp và biến được lambda bắt giữ

Biến đếm của vòng `for` cổ điển thường được tăng ở phần cập nhật của vòng lặp, nên không effectively final:

~~~java
for (int i = 0; i < 3; i++) {
    Runnable task = () -> System.out.println(i); // Lỗi biên dịch
}
~~~

`i++` thay đổi chính biến `i` qua mỗi vòng. Nếu cần mỗi lambda dùng giá trị của một vòng cụ thể, hãy sao chép giá trị đó vào biến mới bên trong thân vòng lặp:

~~~java
for (int i = 0; i < 3; i++) {
    int current = i;
    Runnable task = () -> System.out.println(current);
    task.run();
}
~~~

Kết quả:

~~~text
0
1
2
~~~

Mỗi lần chạy qua thân vòng lặp, một biến `current` mới được khởi tạo. Biến đó không bị gán lại sau khi khởi tạo, vì vậy lambda có thể bắt giữ nó. Nếu đưa khai báo `current` ra ngoài vòng lặp rồi gán lại ở mỗi vòng, vấn đề effectively final sẽ xuất hiện trở lại.

## 6. Bắt giữ tham chiếu không đồng nghĩa với đóng băng đối tượng

Effectively final nói về **biến không bị gán lại**, chứ không nói rằng đối tượng mà biến tham chiếu đến là bất biến.

~~~java
var names = new java.util.ArrayList<String>();
Runnable task = () -> names.add("Ada");
task.run();
System.out.println(names);
~~~

Kết quả:

~~~text
[Ada]
~~~

`names` vẫn trỏ đến cùng một danh sách, nên biến tham chiếu effectively final. Nội dung danh sách có thể thay đổi thông qua `add`. Tương tự, `final List<String> names` ngăn gán một danh sách khác cho `names` nhưng không tự ngăn thêm hoặc xóa phần tử.

Cần phân biệt ba việc:

- **Gán lại biến:** `names = anotherList` đổi tham chiếu và vi phạm effectively final nếu `names` đang bị bắt giữ.
- **Thay đổi đối tượng:** `names.add("Ada")` giữ nguyên tham chiếu và được phép.
- **Đảm bảo an toàn luồng:** effectively final không làm cho đối tượng mutable trở nên thread-safe. Dùng chung một đối tượng giữa nhiều luồng vẫn cần cân nhắc đồng bộ, cấu trúc dữ liệu an toàn luồng hoặc quyền sở hữu dữ liệu.

Với kiểu nguyên thủy, lambda nhận giá trị của biến. Với biến tham chiếu, giá trị được bắt giữ là tham chiếu đến đối tượng; lambda không nhận một bản sao sâu của toàn bộ đối tượng.

## 7. Lambda, local class và anonymous class

Cùng một nguyên tắc được áp dụng khi local class hoặc anonymous class sử dụng biến cục bộ bên ngoài.

~~~java
int base = 10;

class Adder {
    int add(int value) {
        return base + value;
    }
}

Adder adder = new Adder();
System.out.println(adder.add(5));
~~~

`base` phải là final hoặc effectively final vì local class `Adder` sử dụng biến khai báo trong phương thức bên ngoài. Anonymous class trong ví dụ hoàn chỉnh cũng bắt giữ `prefix` theo quy tắc đó.

Có một khác biệt đáng nhớ về `this`: bên trong lambda, `this` vẫn chỉ đối tượng bao quanh lambda; bên trong anonymous class, `this` chỉ chính đối tượng anonymous class. Khác biệt này có thể ảnh hưởng đến cách truy cập thành viên, nhưng không thay đổi quy tắc effectively final dành cho biến cục bộ được bắt giữ.

## 8. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lỗi “must be final or effectively final” | Biến cục bộ bị gán lại hoặc tăng/giảm sau khi khởi tạo | Bỏ phép gán lại hoặc dùng biến mới cho mỗi tác vụ |
| Đã gán lại sau dòng lambda nhưng lambda chưa chạy | Trình biên dịch xét quy tắc gán, không chờ đến lúc chạy | Giữ biến effectively final trong toàn bộ phạm vi |
| Đã khai báo `final` nhưng vẫn thay đổi được danh sách | `final` khóa việc gán lại tham chiếu, không khóa trạng thái đối tượng | Dùng kiểu dữ liệu bất biến nếu cần bất biến thực sự |
| Lambda sửa được trường nhưng không sửa được biến cục bộ | Trường và biến cục bộ chịu các quy tắc khác nhau | Chọn nơi lưu trạng thái có chủ đích và xử lý đồng bộ khi cần |
| Sao chép biến nhưng vẫn lỗi | Biến sao chép cũng bị gán lại sau đó, hoặc bản sao nằm ngoài vòng lặp và bị cập nhật liên tục | Khởi tạo biến riêng trong phạm vi mỗi tác vụ và không gán lại |

## 9. Checklist khi đọc hoặc viết code

1. Xác định biến nào được khai báo bên ngoài lambda hoặc local/anonymous class nhưng được sử dụng bên trong.
2. Kiểm tra tất cả đường đi trong mã: biến có được khởi tạo trước khi sử dụng và có bị gán lại, tăng hoặc giảm không?
3. Nếu cần giữ giá trị riêng cho từng vòng lặp, tạo biến cục bộ mới trong thân vòng lặp.
4. Nếu chỉ thay đổi trạng thái của đối tượng được tham chiếu, xác nhận rằng việc đó là chủ đích và có an toàn trong ngữ cảnh chạy hay không.
5. Phân biệt quy tắc biên dịch effectively final với tính bất biến và an toàn luồng; đây là ba thuộc tính khác nhau.

Quy tắc effectively final giúp Java xác định rõ giá trị cục bộ nào có thể được lambda và lớp cục bộ/ẩn danh sử dụng, kể cả khi hành động đó chạy sau khi phương thức ban đầu kết thúc.