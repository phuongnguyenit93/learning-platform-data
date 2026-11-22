# Đối tượng nhận lời gọi trở thành tham số đầu tiên của kiểu hàm

Trong Java, tham chiếu phương thức dạng `TênKiểu::phươngThứcThểHiện` (unbound instance method reference) cho phép biểu diễn lời gọi một phương thức **instance** mà chưa cố định đối tượng nhận lời gọi. Khi tham chiếu này được gán cho một functional interface, **tham số đầu tiên của phương thức trừu tượng duy nhất (SAM)** chính là đối tượng nhận lời gọi (receiver). Các tham số tiếp theo được truyền vào danh sách tham số thực sự của phương thức instance.

Đây là quy tắc quan trọng khi đọc các biểu thức như `String::length`, `String::startsWith`, `String::substring` hoặc `String::compareToIgnoreCase`. Ký hiệu `::` không tự gọi phương thức; nó tạo ra một giá trị có kiểu functional interface phù hợp với ngữ cảnh.

## 1. Quy tắc ánh xạ receiver-first

Giả sử kiểu `T` có phương thức instance:

~~~java
R method(P1 p1, P2 p2);
~~~

Một functional interface có SAM tương đương:

~~~java
R apply(T receiver, P1 p1, P2 p2);
~~~

có thể nhận tham chiếu `T::method`, nếu các kiểu tham số, kiểu trả về, quyền truy cập và quy tắc chuyển đổi kiểu của Java tương thích. Ý nghĩa khi gọi là:

~~~java
(receiver, p1, p2) -> receiver.method(p1, p2)
~~~

Lưu ý: `receiver` **không phải** tham số bổ sung trong phần khai báo của `method`. Nó chỉ là tham số đầu tiên của SAM, dùng làm đối tượng đứng bên trái dấu chấm khi thực thi.

| Phương thức instance | Functional interface đích | Lambda tương đương | Lời gọi SAM |
| --- | --- | --- | --- |
| `String.length()` | `ToIntFunction<String>` | `s -> s.length()` | `applyAsInt(s)` |
| `String.startsWith(String)` | `BiPredicate<String, String>` | `(s, prefix) -> s.startsWith(prefix)` | `test(s, prefix)` |
| `String.substring(int)` | `BiFunction<String, Integer, String>` | `(s, from) -> s.substring(from)` | `apply(s, from)` |
| `String.compareToIgnoreCase(String)` | `Comparator<String>` | `(a, b) -> a.compareToIgnoreCase(b)` | `compare(a, b)` |

Trong bảng, `s`/`a` là đối tượng nhận lời gọi; `prefix`, `from` và `b` mới là đối số khai báo của phương thức gốc. Hai đối tượng `a` và `b` đều là `String` nhưng có vai trò khác nhau trong `Comparator.compare`.

## 2. Ví dụ hoàn chỉnh trên Java 17+

Lưu đoạn mã sau vào tệp `UnboundMethodReferenceDemo.java`:

~~~java
import java.util.Comparator;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class UnboundMethodReferenceDemo {
    static class Animal {
        String sound() {
            return "animal";
        }
    }

    static class Dog extends Animal {
        @Override
        String sound() {
            return "dog";
        }
    }

    @FunctionalInterface
    interface Slice {
        String apply(String text, int from, int to);
    }

    public static void main(String[] args) {
        ToIntFunction<String> length = String::length;
        BiPredicate<String, String> startsWith = String::startsWith;
        BiFunction<String, Integer, String> suffix = String::substring;
        Comparator<String> ignoringCase = String::compareToIgnoreCase;
        Slice slice = String::substring;
        Function<Animal, String> sound = Animal::sound;

        System.out.println(length.applyAsInt("Java"));
        System.out.println(startsWith.test("method reference", "method"));
        System.out.println(suffix.apply("functional", 4));
        System.out.println(ignoringCase.compare("java", "JAVA"));
        System.out.println(slice.apply("functional", 0, 4));
        System.out.println(sound.apply(new Dog()));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac UnboundMethodReferenceDemo.java
java UnboundMethodReferenceDemo
~~~

Kết quả chính xác:

~~~text
4
true
tional
0
func
dog
~~~

Giải thích từng lời gọi:

1. `length.applyAsInt("Java")` tương đương `"Java".length()`, nên trả về `4`.
2. `startsWith.test("method reference", "method")` tương đương `"method reference".startsWith("method")`, nên là `true`.
3. `suffix.apply("functional", 4)` gọi `"functional".substring(4)`. Chỉ số bắt đầu từ 0, nên kết quả là `"tional"`.
4. `ignoringCase.compare("java", "JAVA")` gọi `"java".compareToIgnoreCase("JAVA")`, cho kết quả `0`.
5. `slice.apply("functional", 0, 4)` gọi overload `substring(0, 4)`, trả về đoạn `"func"` (đầu bao gồm, cuối loại trừ).
6. `sound.apply(new Dog())` sử dụng `Animal::sound` nhưng đối tượng thực tế là `Dog`. Phương thức được override ở `Dog` được dispatch động, nên in `dog`.

Ví dụ này cũng cho thấy kiểu của receiver có thể là lớp cha hoặc interface tương thích, trong khi phương thức instance được chọn lúc chạy theo kiểu thực của đối tượng đối với phương thức có cơ chế dynamic dispatch.

## 3. Tại sao SAM có nhiều hơn một tham số?

Xét phương thức `String.startsWith(String prefix)`: bản thân nó có **một** tham số `prefix`. Nhưng kiểu đích `BiPredicate<String, String>` có SAM `boolean test(String first, String second)` với **hai** tham số.

Khi viết:

~~~java
BiPredicate<String, String> check = String::startsWith;
boolean result = check.test("functional", "fun");
~~~

Java hiểu theo lambda tương đương:

~~~java
BiPredicate<String, String> check =
        (receiver, prefix) -> receiver.startsWith(prefix);
~~~

`receiver` nhận `"functional"`; `prefix` nhận `"fun"`. Không có tham số nào bị bỏ qua, và Java cũng không tự tạo một đối tượng `String`. Giá trị nhận lời gọi phải được truyền khi thực thi SAM.

Tương tự, nếu phương thức instance cần hai đối số thực, SAM sẽ cần **ba** đối số: receiver cộng hai đối số của phương thức. Vì `java.util.function` không có sẵn functional interface tổng quát ba tham số, ta có thể khai báo `@FunctionalInterface` riêng như `Slice` trong ví dụ. `String::substring` sau đó được ánh xạ tới overload `substring(int beginIndex, int endIndex)`.

## 4. Phân biệt tham chiếu chưa gắn receiver với tham chiếu đã gắn receiver

Hai cách viết gần giống nhau nhưng có chữ ký SAM khác nhau:

| Cú pháp | Receiver được xác định lúc nào? | Ví dụ kiểu đích |
| --- | --- | --- |
| `TênKiểu::instanceMethod` | Khi gọi SAM, qua đối số đầu tiên | `Function<String, Integer> f = String::length;` |
| `đốiTượng::instanceMethod` | Khi đánh giá biểu thức tham chiếu | `Supplier<Integer> f = "Java"::length;` |

Ví dụ minh họa trong một phương thức Java (đã import `Function` và `Supplier`):

~~~java
Function<String, Integer> unbound = String::length;
Supplier<Integer> bound = "Java"::length;

int x = unbound.apply("Hello"); // 5: receiver = "Hello"
int y = bound.get();            // 4: receiver đã cố định = "Java"
~~~

`unbound` yêu cầu người gọi truyền `String`; `bound` không yêu cầu tham số receiver nữa, vì đối tượng `"Java"` đã được giữ khi tạo tham chiếu. Nếu thay đổi biến dùng để tạo bound reference sau đó (khi mã hợp lệ về quy tắc effectively final), receiver mà tham chiếu đã giữ không đổi.

Ngoài ra, `TênKiểu::staticMethod` là tham chiếu tới phương thức `static`: phương thức static **không có receiver** và không nhận thêm tham số đầu. Ví dụ `Function<Integer, String> f = String::valueOf;` tương đương `x -> String.valueOf(x)`. Cú pháp `TênKiểu::new` lại tham chiếu constructor. Vì vậy cần xem **phương thức được chọn và kiểu functional interface đích**, không suy đoán receiver-first từ ký tự `::` một cách máy móc.

## 5. Trình biên dịch chọn phương thức và kiểu đích như thế nào?

Tham chiếu phương thức là một **poly expression**: bản thân biểu thức `String::substring` chưa có functional-interface type cụ thể khi đứng một mình. Kiểu đích từ phép gán, tham số của lời gọi hàm, phép ép kiểu hoặc biểu thức trả về sẽ cung cấp chữ ký SAM để Java kiểm tra tính tương thích.

Quy trình đọc một tham chiếu unbound:

1. Xác định functional interface mà ngữ cảnh yêu cầu và phương thức SAM của nó.
2. Với phương thức instance, lấy tham số **đầu tiên** của SAM làm kiểu receiver, bảo đảm có thể dùng kiểu đó để gọi phương thức.
3. Ghép các tham số SAM còn lại với các tham số của phương thức instance; giải quyết overload, generic type và các chuyển đổi hợp lệ.
4. Kiểm tra kiểu trả về của phương thức với kiểu trả về SAM; với SAM trả về `void`, kết quả của lời gọi có thể bị bỏ đi theo quy tắc tương thích thích hợp.
5. Khi SAM được gọi, đánh giá receiver và truyền các đối số, rồi thực thi phương thức, bao gồm dispatch động khi áp dụng.

Ví dụ, cùng `String::substring` trong chương trình trên đã chọn hai overload khác nhau nhờ chữ ký SAM: `BiFunction<String, Integer, String>` chọn `substring(int)`, còn `Slice` chọn `substring(int, int)`.

Java có thể tự boxing/unboxing trong những trường hợp hợp lệ: `BiFunction<String, Integer, String>` truyền `Integer` tới tham số `int` của `substring(int)` qua unboxing. Nếu receiver hoặc kiểu đối số không tương thích, phép gán method reference không biên dịch; method reference không ép kiểu tùy ý.

## 6. Lỗi thường gặp và cách sửa

**Nhầm số lượng tham số của functional interface.**

~~~java
// Sai: String::length còn cần receiver, Supplier.get() không có tham số.
java.util.function.Supplier<Integer> wrong = String::length;

// Đúng: receiver được truyền qua Function.apply().
java.util.function.Function<String, Integer> ok = String::length;
~~~

Nếu muốn `Supplier<Integer>` thì phải gắn receiver: `Supplier<Integer> fixed = "Java"::length;`. Hai dòng gắn `wrong` và `ok` được đặt để đối chiếu; **không biên dịch dòng `wrong`** trong một chương trình thực.

**Đảo receiver với đối số phương thức.** `String::startsWith` cùng `BiPredicate<String, String>` được gọi qua `test(text, prefix)`, không phải `test(prefix, text)`. Vì cả hai đều là `String`, trình biên dịch không phát hiện được sai ngữ nghĩa này.

**Cho rằng đã gắn receiver khi tạo unbound reference.** `String::length` chưa giữ bất cứ chuỗi nào; giá trị chuỗi chỉ xuất hiện trong `apply` hay `applyAsInt`.

**Receiver `null`.** Tạo `Function<String, Integer> f = String::length;` vẫn hợp lệ dù sau đó truyền `null`. Gọi `f.apply(null)` sẽ ném `NullPointerException` khi cố gọi `length()` trên đối tượng null. Ngược lại, với `String s = null; Supplier<Integer> f = s::length;`, việc đánh giá tham chiếu đã gắn receiver ném `NullPointerException` ngay lúc tạo tham chiếu.

**Lẫn static với instance hoặc áp sai overload.** `String::valueOf` chỉ tới các phương thức static, không thêm receiver. Với tên phương thức có overload, hãy để kiểu SAM thể hiện rõ số và kiểu tham số; một số ngữ cảnh overload có thể mơ hồ và không biên dịch.

**Bỏ quên quyền truy cập và checked exception.** Method reference vẫn phải tuân thủ access modifier. Nếu phương thức được tham chiếu khai báo checked exception, SAM của functional interface cần cho phép exception phù hợp; các interface thông dụng như `Function` không khai báo checked exception trên `apply`.

**Nhầm việc tạo tham chiếu với việc chạy phương thức.** `String::length` không tính độ dài ngay khi được gán. Lời gọi chỉ diễn ra khi SAM được thực thi; đó là lúc receiver được cung cấp và kết quả/ngoại lệ được tạo ra.

## 7. Khi nào nên dùng?

Tham chiếu unbound đặc biệt hữu ích khi API truyền **đối tượng sẽ xử lý** qua tham số của SAM, ví dụ với Stream:

~~~java
import java.util.List;

List<String> words = List.of("one", "three", "seven");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();
// lengths = [3, 5, 5]
~~~

`Stream.map` cần `Function<? super String, ? extends Integer>`; mỗi phần tử được truyền vào SAM như receiver của `length()`. Mã trên là đoạn sử dụng trong một phương thức và cần import `java.util.List`.

Một ví dụ khác là sắp xếp không phân biệt hoa thường:

~~~java
List<String> names = new java.util.ArrayList<>(List.of("beta", "Alpha"));
names.sort(String::compareToIgnoreCase);
// names = [Alpha, beta]
~~~

`List.sort` cần `Comparator<String>` với hai tham số; tham số đầu là chuỗi nhận lời gọi `compareToIgnoreCase`, tham số thứ hai là đối số của phương thức này.

Nên ưu tiên `TênKiểu::instanceMethod` khi ánh xạ receiver-first rõ ràng, dễ đọc và đúng chữ ký SAM. Khi cần biến đổi đối số, kiểm tra điều kiện, xử lý `null` hoặc diễn đạt thêm logic, lambda tường minh thường dễ hiểu hơn. Dù viết theo cách nào, quy tắc cốt lõi vẫn là: **tham số đầu tiên của SAM cung cấp receiver; những tham số còn lại đi vào phương thức instance**.