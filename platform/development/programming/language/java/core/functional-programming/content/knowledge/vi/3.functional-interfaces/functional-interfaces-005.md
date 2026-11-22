# Kế thừa interface và những chữ ký được hợp nhất trong Java

## 1. Vì sao kế thừa nhiều phương thức `abstract` vẫn có thể là functional interface?

Thông thường, ta giới thiệu **functional interface** là một interface có đúng một phương thức trừu tượng (*single abstract method*, SAM). Cách nói này hữu ích để bắt đầu, nhưng cần hiểu chữ **một** theo **hợp đồng phương thức sau khi xét kế thừa**, không đơn giản bằng cách đếm số dòng khai báo `abstract` ở các interface cha.

Một interface có thể `extends` nhiều interface. Nếu các phương thức trừu tượng được thừa kế có **chữ ký tương đương khi ghi đè** (*override-equivalent signatures*) và kiểu trả về tương thích, Java xem chúng như **một hợp đồng hàm về mặt logic**. Interface con vẫn có thể là functional interface, có thể dùng làm kiểu đích của lambda hoặc method reference phù hợp.

Ví dụ về ý tưởng:

~~~java
interface First {
    void execute();
}

interface Second {
    void execute();
}

@FunctionalInterface
interface Combined extends First, Second {
}
~~~

`Combined` thừa kế hai khai báo `execute()`, nhưng một phương thức `execute()` duy nhất đủ để thực hiện cả hai hợp đồng. Vì vậy `Combined` hợp lệ là functional interface:

~~~java
Combined task = () -> System.out.println("Đã chạy");
task.execute();
~~~

Hai đoạn trên là **mã minh họa** đặt trong cùng đơn vị biên dịch với nhau. Chương trình hoàn chỉnh có thể chạy ở phần 6.

**Không có cơ chế “gộp mã thực thi” từ hai phương thức abstract:** chúng không có thân để gộp. Java kiểm tra xem có thể thực hiện tất cả các hợp đồng bằng một phương thức hay không. Lambda cung cấp phần triển khai cho hợp đồng chức năng đó.

## 2. Cách Java xác định hợp đồng hàm sau kế thừa

Theo Java Language Specification (JLS) §9.8, hãy xét tập `M` gồm các phương thức `abstract` là thành viên của interface, **không tính những phương thức có cùng chữ ký với phương thức instance `public` của `Object`**. Một interface thông thường, không `sealed`, là functional interface khi trong `M` tồn tại một phương thức `m` thỏa **đồng thời**:

1. Chữ ký của `m` là **subsignature** của chữ ký **mọi** phương thức trong `M`.
2. Kiểu trả về của `m` là **return-type-substitutable** so với kiểu trả về của **mọi** phương thức trong `M`.

Nếu `M` không có phương thức nào sau phép loại trừ, interface **không phải** functional interface. Nếu có nhiều phương thức không hợp nhất được theo các điều kiện trên, interface cũng không phải functional interface; trong một số trường hợp, chính khai báo interface còn không hợp lệ để biên dịch.

Đặc tả Java phân biệt ba thuật ngữ quan trọng:

- **Method signature (chữ ký phương thức):** bao gồm tên phương thức, các tham số kiểu của phương thức (nếu có), và kiểu tham số hình thức sau khi xét quy tắc tương ứng. **Kiểu trả về và `throws` không phải thành phần dùng để phân biệt overload theo chữ ký**.
- **Override-equivalent:** hai chữ ký tương đương khi ít nhất một chữ ký là *subsignature* của chữ ký kia. Từ góc nhìn Java, chúng có thể biểu diễn cùng một hợp đồng ghi đè.
- **Subsignature:** bao gồm trường hợp chữ ký giống nhau, cùng trường hợp tương thích có tính tới **erasure** để hỗ trợ tương thích giữa code generic và code cũ dùng raw type. **Chỉ cùng tên hoặc cùng erasure chưa đủ** để khẳng định hai phương thức hợp nhất hợp lệ.

Điều kiện kiểu trả về giải thích tại sao `String` có thể đáp ứng hợp đồng trả `CharSequence` (kiểu con có thể thay thế kiểu cha), nhưng `int` và `long` không thể tùy ý hợp nhất dù tên và tham số giống nhau.

JLS §9.9 còn mô tả **function type** (còn gọi là *function descriptor*) dùng để kiểm tra khả năng tương thích của lambda: nó xác định tham số, kiểu trả về và các checked exception được phép khai báo sau khi xem xét toàn bộ hợp đồng thừa kế.

> **Ghi nhớ:** Hỏi “mấy dòng `abstract`?” là chưa đủ. Cần hỏi “có một chữ ký phù hợp với mọi chữ ký còn lại, và kiểu trả về có thay thế được không?”.

## 3. Các trường hợp hợp nhất thành công

### 3.1. Kế thừa hai khai báo có chữ ký giống nhau

~~~java
interface LeftAction {
    void run();
}

interface RightAction {
    void run();
}

@FunctionalInterface
interface OneAction extends LeftAction, RightAction {
}
~~~

Cả hai cha khai báo `void run()`. Con không cần khai báo `run()` lần thứ ba. `OneAction` có một hợp đồng chức năng `() -> void`; lambda `() -> ...` có thể hiện thực nó.

Đây là trường hợp dễ quan sát nhất: **cùng tên, cùng danh sách tham số, cùng kiểu trả về**.

### 3.2. Kiểu trả về hiệp biến (covariant return)

~~~java
interface GeneralText {
    CharSequence read();
}

interface SpecificText {
    String read();
}

@FunctionalInterface
interface TextReader extends GeneralText, SpecificText {
}
~~~

`String` triển khai `CharSequence`, vì vậy `String read()` có thể thay thế hợp đồng trả `CharSequence`. Một lambda trả `String` đáp ứng cả hai:

~~~java
TextReader reader = () -> "Java";
String value = reader.read();
~~~

Đoạn sử dụng trên giả định các interface đã được khai báo. Java có thể chọn kiểu trả về cụ thể tương thích cho lời gọi; không cần ép lambda thành hai phương thức khác nhau.

**Phân biệt:** hiệp biến kiểu trả về áp dụng cho **kiểu tham chiếu** có quan hệ thay thế phù hợp. Không thể dùng sự chuyển đổi số nguyên thông thường để cho `int read()` và `long read()` trở thành một hợp đồng tương thích.

### 3.3. Kế thừa phương thức generic rồi cố định tham số kiểu

~~~java
interface Source<T> {
    T get();
}

interface StringSource extends Source<String> {
}

@FunctionalInterface
interface ConfigSource extends StringSource {
}
~~~

Khi `T` được thay bằng `String`, hợp đồng trừu tượng mà `ConfigSource` nhận được là `String get()`. Nó vẫn là một SAM:

~~~java
ConfigSource config = () -> "production";
System.out.println(config.get()); // production
~~~

Điểm này đặc biệt hữu ích khi xây dựng API generic: interface con có thể chuyên biệt hóa kiểu dữ liệu mà không làm phát sinh thêm hợp đồng abstract độc lập.

Có thể nhiều nhánh kế thừa cùng đưa đến một hợp đồng tương thích; Java sẽ kiểm tra kiểu sau khi áp dụng các đối số generic theo quy tắc kế thừa. Tuy nhiên, **nếu các nhánh cố định kiểu khác nhau và gây xung đột chữ ký**, không được giả định trình biên dịch có thể tự chọn một nhánh.

### 3.4. Các phương thức public của Object không làm tăng số SAM

~~~java
@FunctionalInterface
interface NamedCheck {
    boolean test(String name);
    boolean equals(Object other);
}
~~~

`equals(Object)` có cùng chữ ký với phương thức instance `public` của `Object`, vì thế không được tính thành một phương thức chức năng mới. `NamedCheck` vẫn có một SAM thực sự là `test(String)`.

Tương tự, các chữ ký trùng `hashCode()` hoặc `toString()` của `Object` không được tính theo quy tắc này.

**Giới hạn quan trọng:** `clone()` của `Object` là `protected`, không phải phương thức `public` được loại trừ trong quy tắc SAM. Nếu một interface khai báo `public Object clone();` cùng một phương thức abstract khác, đó là hai nghĩa vụ abstract khác nhau. Đừng mở rộng ngoại lệ cho *mọi* phương thức có tên giống phương thức trong `Object`.

### 3.5. Default, static và private không phải các phương thức abstract thứ hai

~~~java
@FunctionalInterface
interface Validator {
    boolean isValid(String text);

    default boolean isInvalid(String text) {
        return !isValid(text);
    }

    static Validator notBlank() {
        return text -> text != null && !text.isBlank();
    }

    private static String label() {
        return "validation";
    }
}
~~~

`isValid` là hợp đồng abstract. `isInvalid` là phương thức `default` có thân; `notBlank` là phương thức `static`; `label` là phương thức private helper (Java 9+). Chúng không tạo thêm nghĩa vụ abstract, nên `Validator` vẫn là functional interface.

`static` methods của interface không được thừa kế như phương thức instance; một lambda cũng không “triển khai” chúng. Khi kế thừa nhiều phương thức `default` có chữ ký xung đột, cần xử lý theo quy tắc xung đột `default`, không coi chúng là các abstract method được hợp nhất.

## 4. Các trường hợp không hợp nhất được

### 4.1. Hai phương thức abstract độc lập

~~~java
interface Startable {
    void start();
}
interface Stoppable {
    void stop();
}

// Interface hợp lệ, nhưng KHÔNG phải functional interface:
interface Lifecycle extends Startable, Stoppable {}
~~~

`start()` và `stop()` là hai hợp đồng khác nhau. Lớp triển khai phải thực hiện cả hai; lambda không thể đại diện cho `Lifecycle`.

Đoạn sau **cố ý không biên dịch**, chỉ để minh họa lỗi:

~~~java
// @FunctionalInterface
// interface BadLifecycle extends Startable, Stoppable {}
// -> annotation sẽ báo interface không có đúng một hợp đồng SAM.

// Lifecycle obj = () -> System.out.println("start");
// -> lambda không có một function descriptor để tương thích.
~~~

### 4.2. Overload không trở thành một chữ ký

~~~java
interface CountByNumber {
    int count(int number);
}
interface CountByText {
    int count(String text);
}
interface BothCounts extends CountByNumber, CountByText {}
~~~

`count(int)` và `count(String)` có cùng tên nhưng danh sách tham số khác nhau. Đây là **overloading**: `BothCounts` có hai phương thức abstract, vẫn là interface hợp lệ nhưng **không** phải functional interface.

### 4.3. Cùng tham số nhưng kiểu trả về không tương thích

Ví dụ **không biên dịch được** nếu bỏ dấu chú thích:

~~~java
// interface A {
//     int value();
// }
// interface B {
//     long value();
// }
// interface Invalid extends A, B {}
~~~

Chữ ký `value()` giống nhau nhưng `int` không return-type-substitutable cho `long` và ngược lại. Vì vậy khai báo `Invalid` không hợp lệ. Đây là lỗi **kế thừa interface**, không đơn thuần là một interface hợp lệ nhưng không dùng được với lambda.

Tương tự, hai hợp đồng trả về các kiểu tham chiếu không có quan hệ thay thế phù hợp có thể gây xung đột. Cần kiểm tra quy tắc return-type-substitutable, không suy luận chỉ từ tên kiểu.

### 4.4. Trùng erasure nhưng các chữ ký không phải subsignature của nhau

Java generics dùng **type erasure**. Hai khai báo khác nhau có thể thành cùng dạng JVM sau khi xóa tham số kiểu, nhưng không có nghĩa chúng có thể tự hợp nhất thành một SAM.

Ví dụ sau **cố ý không biên dịch**:

~~~java
// interface ForStrings {
//     void accept(java.util.List<String> values);
// }
// interface ForIntegers {
//     void accept(java.util.List<Integer> values);
// }
// interface Invalid extends ForStrings, ForIntegers {}
~~~

Hai lời khai `accept(List<String>)` và `accept(List<Integer>)` có cùng erasure `accept(List)` nhưng không có subsignature phù hợp trong cặp này. Chúng tạo xung đột tên/erasure, nên `Invalid` không phải một interface hợp lệ.

**Không nhầm:** trường hợp một khai báo raw `Iterable` và một khai báo `Iterable<String>` có thể hợp lệ theo quy tắc subsignature trong những cấu trúc phù hợp. Nhưng hai chuyên biệt hóa không tương thích, ví dụ `List<String>` so với `List<Integer>`, không được xem như cùng hợp đồng.

## 5. Quy tắc throws khi hợp nhất

Khác biệt trong mệnh đề `throws` **không tự nó tạo ra một chữ ký overload mới** và không nhất thiết khiến hai phương thức abstract không thể được kế thừa. Tuy nhiên, checked exception mà *function descriptor* cho phép phụ thuộc vào **tập các `throws` của tất cả phương thức thành phần**.

Ví dụ minh họa:

~~~java
import java.io.IOException;
import java.sql.SQLException;

interface FileJob {
    void execute() throws IOException;
}
interface DatabaseJob {
    void execute() throws SQLException;
}
@FunctionalInterface
interface UnifiedJob extends FileJob, DatabaseJob {}
~~~

`UnifiedJob` vẫn có một hợp đồng `execute()`. Nhưng một lambda triển khai `UnifiedJob` không thể tùy ý ném `IOException` hay `SQLException` đã kiểm tra: chúng không nằm trong khả năng khai báo checked exception chung được phép của cả hai nhánh. Một lambda không ném checked exception thì phù hợp:

~~~java
UnifiedJob job = () -> System.out.println("OK");
~~~

**Ví dụ lỗi khi bỏ comment (không biên dịch):**

~~~java
// UnifiedJob bad = () -> {
//     throw new IOException("failed");
// };
~~~

Ở tình huống khác, khi cả hai hợp đồng cho phép một checked exception chung hoặc loại con phù hợp, function descriptor có thể cho phép checked exception đó. Việc kết hợp còn phải tuân thủ quy tắc khai báo `throws` khi ghi đè. Unchecked exception (`RuntimeException` và hậu duệ) không bị ràng buộc bởi các `throws` checked theo cách trên.

## 6. Chương trình Java 17 hoàn chỉnh đã kiểm chứng

Tạo file **InterfaceInheritanceDemo.java**. Toàn bộ interface được khai báo lồng trong class để có một tệp độc lập, không cần thêm nguồn khác. Chương trình kiểm chứng ba trường hợp: kiểu trả về hiệp biến, hai chữ ký abstract trùng nhau cùng phương thức `equals` thuộc `Object`, và generic specialization.

~~~java
public class InterfaceInheritanceDemo {
    interface TextA { CharSequence get(); }
    interface TextB { String get(); }

    @FunctionalInterface
    interface MergedText extends TextA, TextB {
        default String boxed() { return "[" + get() + "]"; }
        static String description() { return "merged"; }
    }

    interface ActionA { void run(); }
    interface ActionB { void run(); }

    @FunctionalInterface
    interface MergedAction extends ActionA, ActionB {
        boolean equals(Object obj);
    }

    interface Data<T> { T data(); }
    interface FixedData extends Data<String> {}

    @FunctionalInterface
    interface DataView extends FixedData {
        default int length() { return data().length(); }
    }

    public static void main(String[] args) {
        MergedText text = () -> "Java";
        MergedAction action = () -> System.out.println("run once");
        DataView data = () -> "SAM";

        System.out.println(text.boxed());
        System.out.println(MergedText.description());
        action.run();
        System.out.println(data.data() + ": " + data.length());
    }
}
~~~

Biên dịch với Java 17 hoặc JDK cao hơn hỗ trợ `--release 17`:

~~~bash
javac --release 17 InterfaceInheritanceDemo.java
java InterfaceInheritanceDemo
~~~

**Stdout:**

~~~text
[Java]
merged
run once
SAM: 3
~~~

Giải thích theo từng dòng:

1. `MergedText` kế thừa `CharSequence get()` và `String get()`; kiểu `String` có thể thay thế `CharSequence`. `text.boxed()` gọi `get()` qua method `default`, nên trả `[Java]`.
2. `MergedText.description()` là method `static` trong chính interface, trả `merged`. Nó không phải nhiệm vụ của lambda.
3. `MergedAction` kế thừa hai `void run()`, được xem là một hợp đồng. `equals(Object)` là chữ ký của phương thức public trong `Object`, không tăng số SAM. Lời gọi `action.run()` thực hiện thân lambda một lần.
4. `DataView` nhận `String data()` qua `Data<String>`; `length()` là `default`, không tăng số abstract method. `"SAM".length()` trả 3.

Ví dụ đã được kiểm thử bằng trình biên dịch với `--release 17` và thực thi; kết quả hiển thị đúng như trên.

## 7. Một số trường hợp nâng cao với generic và chữ ký phương thức

### 7.1. Tham số kiểu của phương thức khác tên vẫn có thể tương đương

Hai generic method có thể dùng tên biến kiểu khác nhau mà vẫn có chữ ký tương đương về mặt khai báo. Ví dụ minh họa:

~~~java
interface FirstGeneric {
    <T> T copy(T source);
}
interface SecondGeneric {
    <U> U copy(U source);
}
@FunctionalInterface
interface GenericCopy extends FirstGeneric, SecondGeneric {}
~~~

`T` và `U` ở đây chỉ là tên khác nhau cho tham số kiểu tương ứng; quy tắc so sánh chữ ký generic xét cấu trúc sau khi điều chỉnh tên biến kiểu, không so chữ cái một cách máy móc.

**Lưu ý:** một generic SAM như `<T> T copy(T)` có function descriptor mang tham số kiểu riêng. Nó là functional interface về mặt định nghĩa, nhưng lambda bình thường không thể biểu diễn một generic function descriptor như vậy. Khi cần triển khai, có thể dùng class hoặc anonymous class cài phương thức generic:

~~~java
GenericCopy copier = new GenericCopy() {
    @Override
    public <T> T copy(T source) {
        return source;
    }
};
~~~

Đây là đoạn minh họa giả định đã có ba interface ở trên. Không suy luận rằng mọi interface đánh dấu `@FunctionalInterface` đều có thể triển khai trực tiếp bằng bất kỳ lambda nào.

### 7.2. Trường hợp raw type hợp lệ không áp dụng cho mọi erasure collision

Một ví dụ nâng cao theo hướng của JLS:

~~~java
interface ParameterizedView {
    Iterable view(Iterable<String> values);
}
interface RawView {
    Iterable<String> view(Iterable values);
}
@FunctionalInterface
interface UnifiedView extends ParameterizedView, RawView {}
~~~

`RawView.view(Iterable)` có subsignature tương thích với `ParameterizedView.view(Iterable<String>)`; kiểu trả về `Iterable<String>` tương thích với `Iterable` theo quy tắc return-type-substitutable. Ví dụ này dùng raw type có chủ đích để giải thích quy tắc tương thích với mã cũ; trong ứng dụng mới, ưu tiên thiết kế generic nhất quán và tránh raw type vì có thể làm mất kiểm tra kiểu.

**Phải phân biệt:** raw-vs-parameterized có thể hợp lệ khi quan hệ subsignature và return-type-substitutable cùng được đáp ứng; còn hai tham số hóa `List<String>` và `List<Integer>` chỉ giống nhau sau erasure nhưng không đáp ứng điều kiện, gây xung đột.

## 8. Mối liên hệ với kế thừa default method và cách khắc phục xung đột

Các phương thức `abstract` có thể tạo một hợp đồng duy nhất mà không có thân triển khai. Với `default`, vấn đề khác: nó mang **thân phương thức thực sự**.

Ví dụ **không biên dịch** vì thừa kế hai default method trùng chữ ký:

~~~java
// interface Friendly {
//     default String greet() { return "Hi"; }
// }
// interface Formal {
//     default String greet() { return "Hello"; }
// }
// interface Conflicted extends Friendly, Formal {}
~~~

Interface con cần giải quyết xung đột tường minh, ví dụ ghi đè `greet()` và chọn hành vi mong muốn. Không nên áp dụng suy luận “hai chữ ký như nhau nên tự hợp nhất” của abstract methods cho hai default bodies.

Ngược lại, khi interface con có thêm các phương thức `default` mới với thân riêng và không gây xung đột, chúng không làm mất tính SAM. Đây là cách API thường cung cấp một điểm mở rộng trừu tượng duy nhất, kèm các thao tác tiện ích:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String text);

    default String formatNonNull(String text) {
        return format(text == null ? "" : text);
    }
}
~~~

Hành vi `format(...)` do lambda cung cấp; `formatNonNull(...)` là hành vi dùng lại trong interface.

## 9. Quy trình tự kiểm tra khi thiết kế một functional interface kế thừa

| Câu cần hỏi | Nếu câu trả lời là... | Hệ quả |
| --- | --- | --- |
| Interface con kế thừa bao nhiêu phương thức abstract thực sự? | Chỉ một sau khi loại chữ ký public của Object | Có khả năng là SAM |
| Có nhiều khai báo abstract? | Chữ ký trùng hoặc có subsignature phù hợp | Có thể hợp nhất |
| Kiểu trả về có tương thích? | Có return-type-substitutable chung | Kế thừa có thể hợp lệ |
| Có overload khác danh sách tham số? | Có nhiều hợp đồng độc lập | Không phải SAM |
| Có cùng erasure nhưng tham số hóa không tương thích? | Có name clash | Khai báo interface có thể không biên dịch |
| Có các default method xung đột? | Có | Phải giải quyết xung đột thân triển khai |
| Có nhiều `throws` checked? | Có | Xét function descriptor và checked exception hợp lệ |
| Có `@FunctionalInterface`? | Có | Compiler kiểm tra giao diện thực sự là SAM; annotation không tự làm hợp đồng hợp lệ |

Khi thiết kế, nên chạy `javac` với `@FunctionalInterface` trên interface dự kiến để nhận cảnh báo lỗi sớm nếu việc bổ sung một phương thức trừu tượng phá vỡ hợp đồng. Việc bỏ annotation **không khiến** một interface không có SAM trở thành dùng được với lambda; annotation chỉ là cách xác nhận chủ đích ở thời điểm biên dịch.

Đừng dựa vào *đếm số interface cha*. Một interface con có thể extends nhiều interface mà vẫn có đúng một hợp đồng chức năng, hoặc extends một interface cha nhưng có nhiều abstract method không thể hợp nhất.

## 10. Bài tập tự kiểm tra

**Bài 1.** Cho:

~~~java
interface A { Number get(); }
interface B { Integer get(); }
@FunctionalInterface interface C extends A, B {}
~~~

`C` có là SAM không? **Có.** `Integer` là kiểu con của `Number`, nên một kết quả `Integer` đáp ứng cả hai hợp đồng.

**Bài 2.** Cho:

~~~java
interface A { void run(String text); }
interface B { void run(int count); }
interface C extends A, B {}
~~~

`C` có hợp lệ không và có là SAM không? **Có, interface hợp lệ; không phải SAM.** Hai chữ ký khác nhau là overload, cần hai phần triển khai.

**Bài 3.** Cho:

~~~java
interface A { void run(); }
interface B { void run(); }
@FunctionalInterface interface C extends A, B {
    default String name() { return "C"; }
}
~~~

`C` có thể nhận `C action = () -> {};` không? **Có.** Hai `run()` trùng hợp đồng; `name()` là default method.

**Bài 4.** Nếu hai interface khai báo `List<String> save(List<String>)` và `List<Integer> save(List<Integer>)`, có thể nói chúng tương đương chỉ vì erasure giống `save(List)` không? **Không.** Cùng erasure chưa đủ cho subsignature, và có thể gây name clash.

**Bài 5.** Tại sao `@FunctionalInterface` hữu ích trong thiết kế API? **Vì** compiler kiểm tra rằng interface vẫn thỏa hợp đồng chức năng khi thêm phương thức hoặc thay đổi cây kế thừa. Đây là biện pháp kiểm tra, không phải một cơ chế tự động hợp nhất phương thức.

## Tài liệu tham khảo

- [Java Language Specification 17, §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).
- [JLS 17, §9.4.1.3 — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3).
- [JLS 17, §9.9 — Function Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.9).
- [JLS 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).

**Kết luận:** **Kế thừa nhiều khai báo abstract không đồng nghĩa có nhiều hợp đồng chức năng.** Java xét chữ ký sau kế thừa, subsignature, kiểu trả về có thể thay thế và ngoại lệ cho các phương thức `public` của Object. Khi mọi nghĩa vụ abstract quy về một hợp đồng hợp lệ, interface con vẫn có thể là functional interface; khi có overload độc lập, xung đột kiểu trả về hoặc name clash do erasure, cần sửa thiết kế thay vì trông chờ lambda giải quyết.
