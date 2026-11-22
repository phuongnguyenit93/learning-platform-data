# 13.1 Từ lambda hoặc method reference tới đối tượng thực hiện functional interface

Khi viết Java:

~~~java
Runnable task = () -> System.out.println("Hello");
~~~

biểu thức `() -> ...` **không phải một phương thức đứng riêng**; nó được chuyển thành một **giá trị tham chiếu tới đối tượng thực hiện giao diện hàm** (*functional interface*). Khi gọi `task.run()`, đối tượng này thực thi hành vi được biểu diễn bởi lambda. Tương tự, một *method reference* như `String::trim` có thể được chuyển thành một đối tượng tương thích với `Function<String,String>`.

Cần phân biệt ba tầng:

1. **Tầng ngôn ngữ Java:** compiler kiểm tra **target type** là functional interface, suy ra chữ ký *single abstract method* (SAM) và bảo đảm thân lambda/method reference phù hợp.
2. **Tầng tạo giá trị:** tại runtime, việc đánh giá lambda/method reference đưa ra một **tham chiếu tới instance thực hiện functional interface**. Implementation được phép tái sử dụng instance; không có bảo đảm “mỗi lần đánh giá luôn new một object”.
3. **Tầng JVM điển hình:** `javac` trên Java 17 thường sinh `invokedynamic` liên kết qua `LambdaMetafactory` để tạo hoặc lấy một đối tượng thực hiện giao diện. Chi tiết class ẩn, object cache và bytecode cụ thể là **cách triển khai**, không phải điều kiện để một lambda hợp lệ theo Java Language Specification.

Mục tiêu bài này là đi trọn đường **biểu thức → target type/SAM → linkage và factory → đối tượng giao diện → lời gọi SAM**, bao gồm lambda không capture, lambda capture, method reference static/bound/unbound/constructor và những ngộ nhận về identity, thời điểm gọi và nối chuỗi.

## 1. Functional interface là gì?

Functional interface là một interface có **đúng một phương thức abstract cần được triển khai** sau khi áp dụng các quy tắc của Java (bỏ qua các phương thức tương ứng với `public` method của `Object` khi xác định SAM). Nó có thể có `default` method, `static` method, và các kế thừa tương thích; điểm chính vẫn là một hợp đồng hàm hợp lệ.

~~~java
@FunctionalInterface
interface TextTransform {
    String apply(String input);

    default String describe() {
        return "text transformation";
    }

    static TextTransform identity() {
        return s -> s;
    }
}
~~~

Đây là **khai báo interface minh họa**, cần đặt vào file Java hợp lệ hoặc trong một class phù hợp. `@FunctionalInterface` không bắt buộc về ngữ nghĩa, nhưng giúp compiler báo lỗi nếu ta vô tình làm interface mất tính “functional” (ví dụ thêm một abstract method độc lập).

Ở đây SAM là `String apply(String input)`; `describe()` và `identity()` không tạo thêm abstract method cần implement. Vì vậy ta có thể tạo một giá trị:

~~~java
TextTransform t = s -> s.strip();
String output = t.apply("  Ada  "); // "Ada"
~~~

Điểm quan trọng: biểu thức lambda được **target-typed** bởi `TextTransform`. Không có một “kiểu lambda” độc lập để compiler tự định danh rồi mới gán bừa sang mọi interface; việc lambda hợp lệ phụ thuộc interface đích và ngữ cảnh.

Một số interface tiêu chuẩn:

| Interface | SAM | Ví dụ dùng lambda hoặc method reference |
| --- | --- | --- |
| `Runnable` | `void run()` | `() -> doWork()` |
| `Supplier<T>` | `T get()` | `() -> create()` hoặc `Type::new` khi hợp chữ ký |
| `Consumer<T>` | `void accept(T)` | `System.out::println` |
| `Function<T,R>` | `R apply(T)` | `String::trim` |
| `Predicate<T>` | `boolean test(T)` | `s -> s.isEmpty()` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | `Type::instanceMethod` khi receiver nằm ở tham số đầu |
| `Comparator<T>` | `int compare(T,T)` | `(a,b) -> Integer.compare(a.length(),b.length())` |

Trong Java Generics, chữ ký SAM còn có thể liên quan **type erasure**, boxing/unboxing, covariance và bridge methods. Vì vậy một object lambda có thể thực hiện interface generic mà runtime descriptor của SAM đã bị erase về `Object`; compiler/JVM cung cấp thích nghi cần thiết theo hợp đồng, không phải do mọi lambda tự có `Object apply(Object)` ở source.

## 2. Từ target type tới biểu thức lambda

Xét:

~~~java
java.util.function.Function<String, Integer> length =
        text -> text.length();
~~~

Compiler biết SAM `Function.apply(T)` với `T=String` và `R=Integer` trong ngữ cảnh này. Vì vậy `text` được suy ra là `String`; `text.length()` trả primitive `int`, có thể **boxing** thành `Integer` để đáp ứng return type của functional interface.

Với một target type khác:

~~~java
java.util.function.ToIntFunction<String> lengthAsInt =
        text -> text.length();
~~~

SAM giờ là `int applyAsInt(String)`. Lambda có logic tương tự nhưng target type khác và return type là `int`. Không thể suy luận hai giá trị này nhất định có cùng runtime class hay cùng cơ chế adapter chỉ từ thân biểu thức.

**Lambda là poly expression:** compiler cần target type từ phép gán, đối số method, return statement, cast hoặc ngữ cảnh thích hợp. Ví dụ:

~~~java
java.util.function.Function<String, String> clean =
        String::trim;
~~~

Là hợp lệ; nhưng chỉ viết `var clean = String::trim;` không hợp lệ vì `var` trong khai báo biến cục bộ không cung cấp target type cho method reference. Với lambda cũng tương tự: `var f = x -> x;` không tự suy ra một interface duy nhất.

Một cast rõ ràng có thể cung cấp target type:

~~~java
var clean = (java.util.function.UnaryOperator<String>) String::trim;
~~~

Khi một method overloaded nhận nhiều functional interfaces, việc giải quyết overload và khả năng tương thích lambda có thể phức tạp hơn. Nếu compiler báo *ambiguous method call*, chỉ định type bằng biến trung gian hoặc cast đến functional interface mong muốn.

### Chữ ký SAM có nghĩa gì?

Đối với `Function<String,String>`, ta có thể hiểu về mặt source là `(String)String`. Nhưng khi kiểm tra class file của `Function`, phương thức gốc mang erasure `(Object)Object`. Runtime có thể cần bridge hoặc adaptation để kết nối hai hình ảnh này. Điều quan trọng trong chương trình Java là **lời gọi kiểm tra kiểu theo target type và quy tắc Java**, không phải giả định implementation mang một method có đúng một dạng bytecode duy nhất.

## 3. Sơ đồ từ lambda/method reference tới object

~~~text
Source code:
  Function<String,String> f = s -> "[" + s + "]";
              │
              ▼
Compiler (target typing + SAM analysis)
  SAM abstract contract: Function.apply(T)
  instantiated input/output: (String)String
              │
              ▼
Javac/JVM Java 17 thường dùng invokedynamic
  Bootstrap: LambdaMetafactory.metafactory
  Static bootstrap data: SAM method type,
                         implementation method handle,
                         instantiated method type
              │
              ▼
Runtime liên kết factory call site
  CallSite target tạo / cung cấp Function instance
              │
              ▼
f ──> object implements Function
              │
              ▼
f.apply("Ada")  ──> chạy phần triển khai lambda ──> "[Ada]"
~~~

**Phân tách hai lời gọi:** biểu thức lambda được **đánh giá để thu được object** tại nơi khai báo/gán; sau đó `f.apply(...)` là một lời gọi SAM riêng. Không được nhầm việc *tạo object thực hiện giao diện* với việc *chạy body của lambda*.

Với ví dụ `s -> "[" + s + "]"`, khi gán `f`, body **chưa được thực thi** cho `"Ada"`. Body chỉ thực thi khi gọi `f.apply("Ada")`. Ngay cả khi compiler/JVM tối ưu tạo instance, ngữ nghĩa Java vẫn phải được giữ.

Nếu body có phép nối chuỗi bằng `+`, `javac` Java 17 còn có thể dùng **một `invokedynamic` khác** liên kết qua `StringConcatFactory` bên trong code thực thi lambda. **`LambdaMetafactory` tạo hành vi giao diện; `StringConcatFactory` phục vụ nối chuỗi**. Cùng tên opcode không có nghĩa hai việc là một call site.

## 4. Vai trò của LambdaMetafactory

`java.lang.invoke.LambdaMetafactory` là cơ chế thư viện JVM hỗ trợ liên kết call site cho biểu thức lambda/method reference. Một bootstrap thường nhận:

~~~java
LambdaMetafactory.metafactory(
        lookup,
        invokedName,
        invokedType,
        samMethodType,
        implMethod,
        instantiatedMethodType);
~~~

Đây là **dạng gọi API minh họa**, chưa phải đoạn code độc lập: các biến phải có giá trị phù hợp và cần xử lý ngoại lệ.

Sáu thông số chia hai nguồn:

- `lookup: MethodHandles.Lookup`: JVM cung cấp bối cảnh và quyền truy cập của code chứa điểm gọi.
- `invokedName: String`: tên SAM mà object sẽ thực hiện, ví dụ `"apply"` hay `"run"`.
- `invokedType: MethodType`: chữ ký của **factory** do `invokedynamic` gọi. Return type là functional interface; các parameter type chính là **các captured arguments** cần truyền tại lúc tạo giá trị lambda.
- `samMethodType: MethodType`: chữ ký phương thức chức năng ở dạng erasure của SAM, ví dụ `(Object)Object` với `Function`.
- `implMethod: MethodHandle`: handle của phần triển khai thực tế, có thể là method static, virtual, constructor hoặc synthetic method do compiler tạo.
- `instantiatedMethodType: MethodType`: chữ ký của SAM sau khi tính target generic/kiểu cụ thể, ví dụ `(String)String`.

Ba thông số đầu được JVM cung cấp trong linkage của `invokedynamic`; ba thông số sau là các **bootstrap static arguments** điển hình trong `BootstrapMethods`. BSM trả một `CallSite`, với target có kiểu `invokedType` (factory type). Khi opcode thực thi, factory trả về một đối tượng tương thích với functional interface.

### Phân biệt ba chữ ký không nên nhập làm một

Ví dụ lambda capture `prefix`:

~~~java
String prefix = "Hi ";
java.util.function.Function<String, String> greet =
        name -> prefix + name;
~~~

Từng chữ ký trong cách biên dịch thường gặp:

~~~text
Functional interface SAM after erasure:
  (Object)Object

Instantiated SAM:
  (String)String

Implementation method (conceptual):
  (String capturedPrefix, String name)String

invokedynamic factory type:
  (String capturedPrefix)Function

Call on resulting object:
  Function.apply(name) -> String theo kiểu dùng tại source
~~~

`prefix` là **runtime argument của factory invokedynamic** khi biểu thức lambda được đánh giá; `name` là **argument của SAM invocation** sau khi object đã tồn tại. `prefix` không tự trở thành một static bootstrap argument chỉ vì về sau được object giữ lại.

Chữ ký implementation method không bắt buộc luôn có captured values ở đầu theo đúng thứ tự source; compiler có thể tạo adapter phù hợp và `LambdaMetafactory` áp dụng quy tắc thích nghi. Sơ đồ là **mô hình đọc phổ biến**, không phải một template cố định cho mọi hình dạng compiler-generated method.

## 5. Ví dụ hoàn chỉnh 1: lambda và bốn dạng method reference

Tạo file **LambdaToSamDemo.java**:

~~~java
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Function;

public class LambdaToSamDemo {
    @FunctionalInterface
    interface Converter {
        String convert(String text);
    }

    static class Prefixer {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String add(String text) {
            return prefix + text;
        }
    }

    static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Converter lambda = text -> "[" + text + "]";
        Converter staticMethod = LambdaToSamDemo::upper;

        String code = "ID:";
        Converter capturedLambda = text -> code + text;

        Prefixer hello = new Prefixer("Hello ");
        Converter boundReceiver = hello::add;

        BiFunction<Prefixer, String, String> unboundReceiver =
                Prefixer::add;
        Function<String, Prefixer> constructorReference =
                Prefixer::new;

        Prefixer made = constructorReference.apply("Dear ");

        System.out.println("lambda: " + lambda.convert("An"));
        System.out.println("static: " + staticMethod.convert("ha"));
        System.out.println("capture: " + capturedLambda.convert("42"));
        System.out.println("bound: " + boundReceiver.convert("Lan"));
        System.out.println("unbound: " +
                unboundReceiver.apply(made, "Minh"));
        System.out.println("constructor: " + made.add("Vy"));
        System.out.println("interface: " +
                (capturedLambda instanceof Converter));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac LambdaToSamDemo.java
java LambdaToSamDemo
~~~

Stdout:

~~~text
lambda: [An]
static: HA
capture: ID:42
bound: Hello Lan
unbound: Dear Minh
constructor: Dear Vy
interface: true
~~~

### Giải thích từng biểu thức

**`text -> "[" + text + "]"`:** compiler kiểm tra target là `Converter`, SAM `String convert(String)`; object trả về triển khai hành vi tạo chuỗi đóng ngoặc. Body chạy khi `convert("An")` được gọi, không phải tại câu lệnh gán.

**`LambdaToSamDemo::upper`:** method reference **static**, trỏ một implementation method nhận `String`, trả `String`. `Converter.convert` tương thích nên caller gọi `staticMethod.convert("ha")` nhận `"HA"`.

**`text -> code + text`:** lambda **capture** giá trị tham chiếu `code` từ vùng bao. Biến cục bộ `code` là *effectively final*: không được gán lại sau đó nếu muốn capture. Sau khi object lambda được tạo, giá trị đã capture được dùng ở các lần `convert` về sau.

**`hello::add`:** method reference dạng **bound receiver**. Biểu thức `hello` được đánh giá khi method reference được tạo, và đối tượng receiver được lưu để các lần gọi `Converter.convert` sử dụng. Do đó SAM chỉ còn một tham số `text`, còn receiver đã được cố định.

**`Prefixer::add`:** method reference dạng **unbound instance method**. Cần một receiver như đối số đầu tiên của functional interface. `BiFunction<Prefixer,String,String>` nhận `(Prefixer receiver,String text)`; gọi `apply(made,"Minh")` tương đương về tác dụng với `made.add("Minh")`.

**`Prefixer::new`:** constructor reference. `Function<String,Prefixer>` nhận một `String`, trả một `Prefixer` mới khi `apply(...)` chạy. **Đánh giá method reference không tự gọi constructor**; lời gọi SAM `apply("Dear ")` mới tạo instance `Prefixer`.

**`instanceof Converter`:** biểu thức cho ra một object tương thích functional interface. Điều này **không** chứng minh nó là anonymous inner class hay một class có tên cố định. Runtime representation có thể khác giữa JDK, compiler, classloader và lần thực thi.

### Vì sao các kiểu đích khác nhau?

Một method reference không có “hình dạng đối tượng” độc lập trước khi nhận target type:

| Biểu thức | Target functional interface | SAM nhận gì? | Cách gọi implementation |
| --- | --- | --- | --- |
| `LambdaToSamDemo::upper` | `Converter` | `String` | static `upper(String)` |
| `hello::add` | `Converter` | `String` | `hello.add(String)` |
| `Prefixer::add` | `BiFunction<Prefixer,String,String>` | `Prefixer, String` | `receiver.add(String)` |
| `Prefixer::new` | `Function<String,Prefixer>` | `String` | tạo `new Prefixer(String)` |
| `text -> code + text` | `Converter` | `String` | synthetic/captured implementation |
| `text -> "[" + text + "]"` | `Converter` | `String` | lambda implementation body |

Lưu ý **tương thích signature** quan trọng hơn tên method. Một method reference có thể được dùng cho nhiều target type nếu overload/generic adaptation cho phép, nhưng không phải mọi target đều hợp lệ.

## 6. Method reference là lựa chọn implementation; SAM vẫn là đường gọi công khai

Có thể nhìn vào method reference như một cách chọn implementation của functional interface:

~~~text
Static reference:
  Type::staticMethod   => SAM(args) gọi Type.staticMethod(args)

Bound instance reference:
  receiver::method     => SAM(args) gọi receiver.method(args)

Unbound instance reference:
  Type::instanceMethod => SAM(receiver, args)
                             gọi receiver.instanceMethod(args)

Constructor reference:
  Type::new            => SAM(args) tạo new Type(args)
~~~

Đây là sơ đồ ngữ nghĩa, **không phải** bản cam kết về số lượng method adapter hoặc hình dạng class do compiler tạo. Đặc biệt, biểu thức `Type::instanceMethod` có thể tham gia overload resolution/generic inference phức tạp; vị trí receiver ở đầu là quy tắc hình dung quan trọng khi chữ ký target phù hợp.

### Ví dụ dễ nhầm: String::length

~~~java
java.util.function.ToIntFunction<String> length =
        String::length;
int result = length.applyAsInt("Java"); // 4
~~~

`String::length` là unbound instance method reference. SAM nhận một `String` làm receiver và trả `int`, không có String object nào bị gắn sẵn tại lúc tạo method reference. Cách đọc tương đương là `s -> s.length()`.

Ngược lại:

~~~java
String word = "Java";
java.util.function.IntSupplier boundLength = word::length;
int result = boundLength.getAsInt(); // 4
~~~

`word::length` đã gắn receiver `word`, nên SAM của `IntSupplier` không cần tham số nào. Nếu cố gán `word::length` cho `ToIntFunction<String>` trong tình huống này, chữ ký không khớp vì target SAM lại yêu cầu nhận một `String` mà method reference đã gắn receiver.

### Bound reference và null

Với biểu thức `receiver::method`, Java yêu cầu đánh giá receiver expression tại lúc **đánh giá method reference**; nếu kết quả là `null`, phát sinh `NullPointerException` ngay tại đó, không đợi SAM invocation. Với dạng `Type::instanceMethod`, không có receiver object được đánh giá tại lúc tạo reference; nếu sau này truyền `null` làm receiver trong SAM invocation thì có thể ném `NullPointerException` tại lúc gọi.

Đây là khác biệt về **thời điểm phát sinh lỗi** có giá trị khi review các pipeline động.

## 7. Capture: thế nào là effectively final?

Lambda có thể sử dụng biến cục bộ từ phạm vi bao ngoài nếu biến ấy là `final` hoặc **effectively final** (sau khi được gán giá trị, không bị gán lại theo quy tắc kiểm tra compiler).

~~~java
String prefix = "Hi ";
java.util.function.Function<String,String> fn =
        name -> prefix + name;
~~~

Hợp lệ vì `prefix` không bị gán lại. Nhưng đoạn sau **không biên dịch**:

~~~java
String prefix = "Hi ";
java.util.function.Function<String,String> fn =
        name -> prefix + name;
prefix = "Bye "; // lỗi: prefix không còn effectively final
~~~

Đây là **ví dụ cố ý lỗi biên dịch**, không phải chương trình chạy. Lý do là lambda capture **giá trị của local variable** tại lúc đánh giá biểu thức; nó không bảo đảm phản ánh những lần gán lại local variable sau đó. Quy tắc effectively final làm ngữ nghĩa rõ ràng và tránh nhiều lỗi khi code chạy sau thời điểm stack frame chứa local variable kết thúc.

### Capture tham chiếu không đồng nghĩa đóng băng trạng thái đối tượng

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.function.IntSupplier size = names::size;
names.add("An");
int first = size.getAsInt(); // 1
names.add("Binh");
int second = size.getAsInt(); // 2
~~~

`names` (receiver của bound method reference `names::size`) không bị gán lại. Nhưng **đối tượng ArrayList** vẫn thay đổi. Khi SAM được gọi, target đọc trạng thái hiện tại nên trả kết quả khác nhau.

Do đó:

- **Captured local variable** không được gán lại nếu dùng trong lambda/method reference.
- **Object được tham chiếu** có thể mutable; capture không tạo snapshot sâu.
- **Thread safety** không tự xuất hiện vì có lambda. Nếu receiver mutable được nhiều thread dùng chung, cần đồng bộ hóa hoặc dùng cấu trúc dữ liệu phù hợp.
- Một object lambda lưu captured reference có thể kéo dài vòng đời của đối tượng được capture; cache callback lâu dài cần xét memory retention.

### Các trường hợp không capture local variable

Lambda có thể truy cập field của object chứa nó thông qua `this`, hoặc static field mà không capture một local variable như ví dụ `prefix`. Trong lambda, `this` là `this` của ngữ cảnh từ vựng bao ngoài, **khác** một anonymous class, nơi `this` bên trong body của anonymous class là chính instance anonymous class đó.

Một lambda không dùng biến từ vùng bao ngoài là **non-capturing** về mặt logic, nhưng implementation có thể có nhiều cách để tạo hoặc dùng lại object tương ứng.

## 8. Thời điểm tạo object, thời điểm chạy body và identity

Xét:

~~~java
java.util.function.Supplier<String> supplier =
        () -> "ready";
~~~

Câu lệnh gán đánh giá lambda và thu được object `Supplier<String>`. **Không có `"ready"` nào cần được trả ra tại thời điểm tạo lambda**; `supplier.get()` mới đánh giá body để trả chuỗi.

Câu hỏi “mỗi lần tạo lambda có new object không?” không có câu trả lời luôn đúng. Java cho phép implementation **tái sử dụng** đối tượng lambda phù hợp (đặc biệt với non-capturing lambda), nhưng cũng có thể tạo instance khác. Vì thế:

~~~java
java.util.function.Supplier<Integer> a = () -> 42;
java.util.function.Supplier<Integer> b = () -> 42;
~~~

Không nên viết unit test khẳng định `a == b` hoặc `a != b` dựa trên việc hai lambda có body giống nhau. Đồng thời, object có thể có identity khi quan sát bằng reference equality, nhưng **không dùng identity làm nghĩa nghiệp vụ** của một lambda hay method reference trừ khi ứng dụng tự quản lý một tham chiếu đã lưu.

**Không dựa vào tên class** bằng `getClass().getName()`: các tên như có hậu tố `$$Lambda$...` là chi tiết runtime có thể thay đổi. Trên các JDK hiện đại, lambda implementation có thể dùng hidden classes; không mặc định JVM luôn sinh một anonymous class “bằng mắt thường” cho từng biểu thức.

**Không dùng `new Runnable() { ... }` như định nghĩa máy móc của lambda.** Anonymous class là một feature khác về scope của `this`, identity và một số quy tắc tên/phạm vi, dù chúng đều có thể tạo object thực hiện interface.

## 9. Ví dụ hoàn chỉnh 2: capture reference, thay đổi trạng thái và thời điểm lỗi null

Tạo file **CaptureReceiverDemo.java**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;

public class CaptureReceiverDemo {
    static class Prefixer {
        private String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String add(String text) {
            return prefix + text;
        }

        void changePrefix(String updated) {
            prefix = updated;
        }
    }

    public static void main(String[] args) {
        Prefixer target = new Prefixer("A:");
        Function<String, String> bound = target::add;
        Function<String, String> lambda = text -> target.add(text);
        BiFunction<Prefixer, String, String> unbound = Prefixer::add;

        System.out.println("before: " + bound.apply("one"));

        target.changePrefix("B:");
        System.out.println("bound after state change: " +
                bound.apply("two"));
        System.out.println("lambda after state change: " +
                lambda.apply("three"));
        System.out.println("unbound: " +
                unbound.apply(target, "four"));

        Prefixer absent = null;
        try {
            Function<String, String> bad = absent::add;
            System.out.println("unexpected: " + bad.apply("x"));
        } catch (NullPointerException expected) {
            System.out.println("bound null: NullPointerException");
        }

        try {
            unbound.apply(null, "x");
        } catch (NullPointerException expected) {
            System.out.println("unbound null call: NullPointerException");
        }
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac CaptureReceiverDemo.java
java CaptureReceiverDemo
~~~

Stdout:

~~~text
before: A:one
bound after state change: B:two
lambda after state change: B:three
unbound: B:four
bound null: NullPointerException
unbound null call: NullPointerException
~~~

Phân tích:

1. `target::add` đánh giá và **gắn receiver `target`** tại thời điểm tạo method reference; SAM `Function.apply(String)` vẫn chỉ có một input `String`.
2. `text -> target.add(text)` capture cùng tham chiếu `target`, không chép trạng thái của `Prefixer`. Sau `changePrefix("B:")`, cả hai callback đều thấy tiền tố mới.
3. `Prefixer::add` là unbound reference, do đó `BiFunction.apply` nhận receiver tường minh ở vị trí đầu.
4. `absent::add` ném `NullPointerException` **ngay khi đánh giá method reference**; chương trình bắt lỗi trước khi có cơ hội gọi `bad.apply`.
5. `unbound.apply(null,"x")` tạo reference unbound hợp lệ từ trước, nhưng khi gọi SAM với receiver `null` thì ném `NullPointerException` ở **thời điểm invocation**.

Khi thiết kế callback có receiver sống ngắn, việc capture object cần được xem xét theo vòng đời: callback giữ reference càng lâu thì receiver có thể càng lâu được garbage collector giữ sống.

## 10. Nhìn dưới bytecode Java 17: invokedynamic tạo factory

`javac` thường dịch các biểu thức lambda/method reference sang một call site `invokedynamic`. Để quan sát trên máy có JDK 17+, chạy:

~~~bash
javac LambdaToSamDemo.java
javap -p -c -v LambdaToSamDemo
~~~

Đọc các khu vực sau:

1. Trong `main`, tìm những `invokedynamic` gắn với việc tạo `Converter`, `BiFunction`, `Function`. Một số expression có capture sẽ có bytecode nạp captured reference/string trước opcode; non-capturing lambda có thể không có operand factory argument.
2. Trong phần `BootstrapMethods`, tìm entry có `REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory`. Thông thường các bootstrap arguments gồm một SAM method type, method handle cho implementation, và instantiated method type.
3. Với body lambda dạng `text -> "[" + text + "]"`, `javac` có thể sinh một method implementation dạng synthetic như `lambda$main$0`. Một static method reference như `LambdaToSamDemo::upper` có thể trỏ trực tiếp tới method đã khai báo thay vì method synthetic trung gian.
4. Khi code dùng `converter.convert("An")`, thao tác gọi SAM thường được biên dịch thành `invokeinterface`. **Đây không phải opcode `invokedynamic` tạo converter trước đó.**
5. Trong method triển khai lambda có phép nối chuỗi, có thể xuất hiện `invokedynamic` khác trỏ `StringConcatFactory.makeConcatWithConstants`. Cần theo đúng bootstrap index của từng opcode.

Sơ đồ mô phỏng một trường hợp có capture:

~~~text
// Trích lược ý nghĩa, KHÔNG phải stdout javap nguyên văn:
aload <local chứa captured String>
invokedynamic ... // factory (String)Converter
astore <local chứa Converter>

// Về sau:
aload <local chứa Converter>
ldc "42"
invokeinterface ... // Converter.convert:(String)String
~~~

Thông tin chữ ký ở mức JVM có thể dùng descriptor class nội bộ như `Lpkg/Outer$Converter;` và `Ljava/lang/String;`. Đừng phụ thuộc một số constant-pool `#n`, tên synthetic method hay offset bytecode cố định; hãy đọc **mối quan hệ factory type, SAM type và implementation handle**.

### BSM static arguments khác captured arguments

Với một lambda capture `prefix`:

~~~text
BootstrapMethods (cấu hình cố định tại class file):
  LambdaMetafactory.metafactory
  SAM MethodType
  Implementation MethodHandle
  Instantiated MethodType

Runtime khi biểu thức lambda được đánh giá:
  load prefix
  invokedynamic [factory] (String)Converter
       └── nhận prefix ở operand stack
       └── trả một Converter object

Runtime khi dùng object:
  converter.convert(value)
       └── value là SAM invocation argument
~~~

`prefix` là **runtime operand của factory invokedynamic**, không phải phần tử bootstrap argument cố định chỉ vì object có thể giữ prefix lâu dài. Và `value` là đối số của **một lời gọi sau** đến phương thức SAM; không nên gọi cả ba nhóm dữ liệu này là cùng loại “tham số của lambda”.

## 11. Ví dụ hoàn chỉnh 3: gọi LambdaMetafactory bằng tay để thấy factory type

Ở mức API `java.lang.invoke`, ta có thể chủ động gọi `LambdaMetafactory.metafactory` để thấy được **CallSite** có target là factory tạo object thực hiện functional interface.

**Lưu ý phạm vi:** Chương trình này **gọi API metafactory bằng Java thường**; nó **không tự chèn opcode `invokedynamic` cho factory bằng cách viết source thông thường**. Nó minh họa cùng cấu trúc factory/capture mà compiler/JVM có thể dùng, còn ví dụ `javap` ở trên cho thấy bytecode thực sự do compiler tạo.

Tạo file **ManualLambdaFactoryDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ManualLambdaFactoryDemo {
    @FunctionalInterface
    public interface TextOp {
        String apply(String value);
    }

    private static String decorate(String prefix, String value) {
        return prefix + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle implementation = lookup.findStatic(
                ManualLambdaFactoryDemo.class,
                "decorate",
                MethodType.methodType(
                        String.class, String.class, String.class));

        // SAM của TextOp: (String)String
        MethodType samType =
                MethodType.methodType(String.class, String.class);

        // Factory nhận String capturedPrefix, trả TextOp object.
        MethodType factoryType =
                MethodType.methodType(TextOp.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup,
                "apply",
                factoryType,
                samType,
                implementation,
                samType);

        MethodHandle factory = site.getTarget();
        System.out.println("factory parameters: " +
                factory.type().parameterCount());
        System.out.println("returns TextOp: " +
                (factory.type().returnType() == TextOp.class));

        TextOp hello = (TextOp) factory.invokeExact("Hello ");
        TextOp goodbye = (TextOp) factory.invokeExact("Bye ");

        System.out.println("first: " + hello.apply("An"));
        System.out.println("second: " + goodbye.apply("Binh"));
        System.out.println("reuse object: " + hello.apply("Minh"));
    }
}
~~~

Lệnh chạy:

~~~bash
javac ManualLambdaFactoryDemo.java
java ManualLambdaFactoryDemo
~~~

Stdout dự kiến:

~~~text
factory parameters: 1
returns TextOp: true
first: Hello An
second: Bye Binh
reuse object: Hello Minh
~~~

### Mổ xẻ bốn chữ ký

Với chương trình này:

| Thành phần | MethodType | Nghĩa |
| --- | --- | --- |
| `implementation` | `(String,String)String` | Method `decorate(prefix,value)` |
| `samType` | `(String)String` | SAM `TextOp.apply(value)` |
| `factoryType` | `(String)TextOp` | Factory cần captured prefix để tạo `TextOp` |
| `factory.type()` | `(String)TextOp` | Target handle của CallSite tạo object |
| Khi gọi `hello.apply(...)` | `(String)String` | SAM nhận input hiện tại, dùng prefix đã capture |

Giá trị `"Hello "` và `"Bye "` được truyền tới **factory handle**, sinh các object TextOp có hành vi capture khác nhau. Khi gọi `hello.apply("An")`, target implementation nhận cả captured prefix và SAM argument rồi trả `"Hello An"`. Do đó không được đồng nhất `factory.type()` với `samType`: một cái là signature **tạo object**, cái kia là signature **gọi hành vi trên object**.

`invokeExact` có quy tắc call-site signature chặt chẽ. Phép ép kiểu trong `TextOp hello = (TextOp) factory.invokeExact("Hello ");` làm rõ return type `TextOp`; nếu gán trực tiếp sang `Object` với `invokeExact` mà không có adapter, có thể gặp `WrongMethodTypeException` vì call site không khớp kiểu trả về handle.

**Không suy luận số instance từ số lần invoke factory.** Code tạo hai biến trỏ tới hai giá trị TextOp với hai captured prefix khác nhau; điều này không cho phép tổng quát hóa rằng mọi lambda non-capturing luôn tạo object mới hoặc luôn được cache.

## 12. Lambda và method reference khác Anonymous class ở đâu?

Một số điểm dễ nhầm:

| Tiêu chí | Lambda/method reference | Anonymous class |
| --- | --- | --- |
| Vai trò chính | Biểu diễn giá trị hành vi theo target functional interface | Khai báo một lớp không tên và tạo instance |
| Kiểu đích | Cần functional interface phù hợp | Có thể implement interface hoặc extend class phù hợp |
| `this` trong body | `this` của phạm vi từ vựng bao ngoài đối với lambda | `this` là instance anonymous class |
| Khả năng target type | Target-typed/poly expression | Biểu thức tạo object với kiểu khai báo cụ thể |
| Runtime representation | Implementation không bị buộc có class tên ổn định | Có một anonymous class theo ngữ nghĩa khai báo class |
| Identity qua nhiều lần đánh giá | Không bảo đảm mỗi lần đánh giá lambda là một object mới | Mỗi phép `new ... { ... }` tạo một instance mới |
| Method body | Lambda có expression/block body; method reference chọn callable | Body được viết trong định nghĩa anonymous class |
| Capture local | Biến phải final/effectively final | Biến local capture cũng phải final/effectively final |

Ví dụ:

~~~java
Runnable viaLambda = () -> System.out.println(this);
Runnable viaAnonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this);
    }
};
~~~

Đây là đoạn **minh họa**, chỉ hợp lệ trong một **instance method hoặc instance initializer** của class bao ngoài (không phải static main). Với lambda, `this` chỉ instance của class chứa biểu thức. Với anonymous class, `this` chỉ object anonymous Runnable. Ví dụ chủ ý cho thấy khác biệt `this`; không nên tự chép nguyên vào static context rồi kết luận lambda “hỏng”.

Một lambda không phải “anonymous class viết ngắn” theo nghĩa đồng nhất tất cả đặc tính. Việc dùng `LambdaMetafactory` và `invokedynamic` là một đường triển khai giúp tách call site khỏi class implementation cụ thể.

## 13. Khi nào dùng lambda, khi nào dùng method reference?

**Method reference** là lựa chọn tốt nếu một method/constructor đã có chính xác hành vi cần truyền và chữ ký khớp target type:

~~~java
java.util.function.Function<String, String> normalize =
        String::strip;
~~~

**Lambda** rõ hơn khi cần kết hợp biểu thức, đổi tên đối số hoặc thêm logic:

~~~java
java.util.function.Function<String, String> normalize =
        input -> "[" + input.strip() + "]";
~~~

Không có quy tắc “method reference luôn nhanh hơn lambda”. Compiler có thể tạo những adapter tương tự; hiệu năng phụ thuộc target, JIT, khả năng escape analysis, captured objects, boxing, mức độ ổn định đường gọi. Ưu tiên khả năng đọc hiểu và kiểm tra hợp đồng trước; nếu hiệu năng quan trọng, benchmark đúng ứng dụng.

### Một số lựa chọn thực tế

- Dùng `User::getId` thay vì `user -> user.getId()` nếu receiver được truyền từ SAM và mapping trực tiếp, không làm mờ ý nghĩa.
- Dùng `repository::save` nếu một repository instance đã được chọn và callback cần gọi trên instance đó.
- Dùng `type -> new Service(type, config)` nếu constructor reference `Service::new` không biểu diễn đủ giá trị cấu hình.
- Dùng lambda khi có bước kiểm tra null, exception translation hoặc nhiều thao tác không thể biểu diễn bằng một method reference duy nhất.
- Dùng functional interface tùy biến khi tên SAM và kiểu tham số cần thể hiện một hợp đồng nghiệp vụ rõ hơn `Function<A,B>` quá tổng quát.

Không nhất thiết biến mọi method thành lambda chỉ để chạy qua `invokedynamic`. Java method call trực tiếp vẫn phù hợp khi không có nhu cầu truyền hành vi như một giá trị.

## 14. Kiểm tra được điều gì khi quan sát một instance lambda?

Khi có:

~~~java
java.util.function.Predicate<String> nonEmpty =
        s -> !s.isEmpty();
~~~

Bạn có thể kiểm tra:

- `nonEmpty instanceof Predicate` đúng, bởi object phải thực hiện interface đích.
- `nonEmpty.test("A")` trả `true`; `nonEmpty.test("")` trả `false`.
- `nonEmpty.getClass()` tồn tại như mọi object, nhưng **tên class không được xem là API ổn định**.
- `nonEmpty == someOtherLambda` không có ý nghĩa xác thực logic tương đương giữa hai lambda có body giống nhau.

Khi muốn kiểm thử callback, nên gọi SAM với input cụ thể và assert output/side effect hoặc exception. Nếu test việc capture, thay đổi trạng thái một object capture hợp lệ và quan sát kết quả; **không** test tên synthetic method, số lượng class được load hay địa chỉ tham chiếu.

### Serialization có phải mặc định không?

Không. Lambda object **không tự serializable** chỉ vì có một SAM. Khả năng serialization phụ thuộc target functional interface và các điều kiện liên quan, ví dụ khi có marker `java.io.Serializable` trong target type được dùng. Kể cả khi tạo lambda serializable, biểu diễn serialized lambda và method reference chịu ràng buộc phiên bản và chi tiết implementation; không nên coi nó như một schema ổn định để lưu trữ dài hạn.

Với application cần lưu nhiệm vụ qua process restart, thường nên lưu **dữ liệu mô tả công việc** (operation id, tham số, version) rồi dựng lại hành vi trong process, thay vì lưu thẳng object lambda và phụ thuộc vào class nội bộ của JVM.

## 15. Lỗi phổ biến khi chuyển lambda/reference sang functional interface

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `incompatible types: ... is not a functional interface` | Interface có nhiều abstract methods độc lập | Thiết kế SAM hợp lệ, cân nhắc `@FunctionalInterface` |
| `var f = x -> x` không biên dịch | Lambda thiếu target type để suy ra interface | Khai báo `Function<T,R>` hoặc cast rõ ràng |
| Method reference không tương thích | Sai số lượng tham số, kiểu trả về hoặc receiver bound/unbound | Viết chữ ký SAM và method được tham chiếu cạnh nhau |
| `Prefixer::add` gán vào `Function<String,String>` lỗi | Unbound reference cần một receiver `Prefixer` làm tham số đầu | Dùng `BiFunction<Prefixer,String,String>` hoặc `instance::add` |
| `instance::method` ném NPE khi tạo | Receiver expression đánh giá thành null | Xác nhận receiver không null **trước** khi tạo bound reference |
| Lambda gọi field mutable cho kết quả khác | Capture giữ reference, không snapshot mọi field | Làm rõ hợp đồng về thời điểm đọc trạng thái |
| `local variables referenced ... must be final or effectively final` | Gán lại local variable được capture | Không gán lại; dùng object state có kiểm soát nếu thực sự cần mutable |
| `this` không trỏ tới callback object | Lambda dùng lexical `this` | Đừng dùng `this` như trong anonymous class |
| Test `a == b` chập chờn theo JDK | Identity/caching của lambda không được bảo đảm | Kiểm tra hành vi thông qua SAM thay vì reference identity |
| Lộ tên kiểu `$$Lambda...` trong log rồi hardcode | Phụ thuộc tên class triển khai nội bộ | Log tên functional interface/call site hoặc định danh nghiệp vụ |
| Lẫn `LambdaMetafactory` và `StringConcatFactory` | Cùng class có nhiều `invokedynamic` | Theo từng bootstrap index và implementation method |
| `WrongMethodTypeException` khi gọi factory handle bằng tay | Kiểu call site `invokeExact` khác `factory.type()` | Kiểm tra cả tham số và return type, dùng cast hoặc adapter phù hợp |
| `LambdaConversionException` khi dùng metafactory thủ công | SAM type, instantiated type, implMethod hoặc captured args không hợp lệ | Kiểm tra quan hệ giữa 3 chữ ký và quyền truy cập của `Lookup` |
| Lambda ném checked exception không được phép | SAM không khai báo loại checked exception đó | Chọn interface phù hợp hoặc xử lý/map exception có chủ đích |
| Callback giữ đối tượng lâu ngoài ý muốn | Capture receiver/context trong object callback | Xem lại ownership và vòng đời callback, tránh global cache không kiểm soát |
| Hiệu năng kém vì boxing | Chọn generic `Function<String,Integer>` thay vì primitive-specialized interface | Cân nhắc `ToIntFunction<String>`, benchmark sau khi đúng |

### Kiểm tra method reference bị ràng buộc sai receiver

Khi viết `obj::method`, receiver đã bị bind. Khi viết `Type::method` cho instance method, receiver thường là tham số đầu của functional interface. Một phép đổi dấu `obj` thành `Type` có thể chuyển từ `Function<String,String>` sang `BiFunction<Type,String,String>`. Đừng chỉ so sánh tên method trùng nhau.

### Tránh suy luận runtime class từ source code

Compiler/JVM có quyền chọn các cấu trúc triển khai khác nhau để đáp ứng cùng hợp đồng Java. Khi debug, thứ đáng tin là **SAM, captured arguments và hành vi khi invoke**, không phải class name hoặc số object tạo trong bộ nhớ. Các thay đổi implementation giữa JDKs không nên làm test nghiệp vụ thất bại.

## 16. Tự kiểm tra (có đáp án)

**Câu 1.** Vì sao `() -> System.out.println("x")` có thể gán cho `Runnable`?  
**Đáp án:** Vì `Runnable` là functional interface với SAM `void run()`; lambda không có tham số và có body phù hợp void-returning method.

**Câu 2.** Khi gán `Function<String,String> f = s -> s.trim();`, `trim()` đã chạy chưa?  
**Đáp án:** Chưa. Biểu thức lambda được đánh giá thành object thực hiện `Function`; body chạy khi `f.apply(...)` được gọi.

**Câu 3.** `String::length` dùng với `ToIntFunction<String>` có receiver ở đâu?  
**Đáp án:** Receiver là `String` được truyền làm tham số SAM `applyAsInt(String)`; đó là unbound reference.

**Câu 4.** `someString::length` dùng với `IntSupplier` có cần tham số SAM không?  
**Đáp án:** Không; receiver đã được gắn khi method reference được tạo, SAM `getAsInt()` không có tham số.

**Câu 5.** `Prefixer::new` đã chạy constructor khi tạo reference chưa?  
**Đáp án:** Chưa. Khi gọi SAM của factory function với argument phù hợp, constructor mới chạy.

**Câu 6.** Có thể viết `var f = x -> x;` không?  
**Đáp án:** Không; lambda là poly expression cần một functional-interface target type cụ thể. Có thể dùng `var f = (Function<String,String>) (x -> x);`.

**Câu 7.** Biến local `prefix` được lambda dùng có thể gán lại sau đó không?  
**Đáp án:** Không, nếu làm mất tính `final`/`effectively final`. Tuy nhiên nếu capture một object, trạng thái của object có thể thay đổi.

**Câu 8.** `LambdaMetafactory` factory handle trả về loại giá trị gì?  
**Đáp án:** Một đối tượng tương thích functional interface; factory signature có thể nhận captured arguments rồi trả interface type.

**Câu 9.** Factory signature `(String)TextOp` có nghĩa SAM là `(String)TextOp`?  
**Đáp án:** Không. Đó là chữ ký **tạo object** với captured `String`. SAM riêng có thể là `(String)String`.

**Câu 10.** Các bootstrap static arguments `samMethodType`, `implMethod` và `instantiatedMethodType` có chứa captured prefix cụ thể `"Hi "` không?  
**Đáp án:** Thông thường không; captured prefix là runtime argument được đưa cho factory invokedynamic khi biểu thức lambda được đánh giá.

**Câu 11.** Nếu hai lambda có body giống nhau, có thể so sánh bằng `==` để biết chúng tương đương không?  
**Đáp án:** Không. Java không bảo đảm cách tạo/cache instance hoặc object identity theo body; kiểm tra hành vi qua SAM.

**Câu 12.** `obj::method` với `obj == null` lỗi lúc nào?  
**Đáp án:** Ngay khi đánh giá bound method reference. Với unbound `Type::method`, null receiver được truyền vào SAM mới gây lỗi khi gọi.

**Câu 13.** Vì sao trong một class có thể thấy hai kiểu `invokedynamic` khác nhau?  
**Đáp án:** `javac` có thể dùng `LambdaMetafactory` để liên kết lambda factory và `StringConcatFactory` để thực hiện nối chuỗi; chúng phục vụ hai điểm gọi khác nhau.

**Câu 14.** Java buộc một lambda phải là anonymous class mới được không?  
**Đáp án:** Không. Java định nghĩa hành vi biểu thức và object functional interface, không buộc một anonymous class có tên/hình dạng cụ thể.

**Câu 15.** Khi đánh giá capture trong môi trường đa luồng, lỗi có thể ở đâu?  
**Đáp án:** Object được capture có thể mutable và chia sẻ, nên có thể xảy ra data race nếu không bảo vệ trạng thái. Quy tắc effectively final của biến cục bộ không tự làm object thread-safe.

## 17. Checklist đọc code và bytecode

- [ ] Xác định **functional interface target type** từ phép gán, parameter method, return hoặc cast.
- [ ] Tìm **SAM** và chữ ký input/output thực sự cần theo generic instantiation.
- [ ] Phân biệt lambda body với method reference chọn static/bound instance/unbound instance/constructor.
- [ ] Ghi rõ **captured values** nếu lambda/reference sử dụng dữ liệu từ vùng bao.
- [ ] Phân biệt **khi đánh giá expression để có object** với **khi gọi SAM để chạy hành vi**.
- [ ] Nếu dùng `javap`, tìm `invokedynamic` ở call site tạo lambda, `LambdaMetafactory` ở `BootstrapMethods` và `invokeinterface` khi gọi SAM.
- [ ] Đọc riêng `invokedType` của **factory**, `samMethodType`, `implMethod` và `instantiatedMethodType`; đừng nhập chúng thành một.
- [ ] Nếu thân lambda nối chuỗi, nhận diện `StringConcatFactory` là một bootstrap khác.
- [ ] Không phụ thuộc identity/class name/synthetic method name của lambda object.
- [ ] Kiểm thử hành vi và exceptions thông qua SAM, có ca capture và mutation khi cần.
- [ ] Chọn interface primitive-specialized khi muốn tránh boxing có ý nghĩa, nhưng ưu tiên correctness rồi mới benchmark.
- [ ] Xem xét vòng đời receiver/context khi callback bị lưu lâu hoặc chuyển qua các thread.

## 18. Kết luận

Lambda và method reference là **biểu thức tạo giá trị hành vi có target type là functional interface**. Compiler dùng SAM để kiểm tra chữ ký; runtime tạo hoặc cung cấp một object triển khai interface; caller dùng method của interface để thực thi hành vi. Với `javac` Java 17, đường triển khai điển hình là `invokedynamic` được liên kết qua `LambdaMetafactory`, nơi target của call site có nhiệm vụ tạo/cung cấp object chức năng và có thể nhận **captured runtime arguments**.

Để đọc đúng một lambda, hãy tự hỏi lần lượt: **interface nào? SAM nào? đối tượng được tạo/nhận lúc nào? có capture gì? khi nào SAM được gọi?** Với method reference, thêm câu hỏi **receiver đã gắn sẵn hay là tham số SAM?** Trả lời được sáu điều đó sẽ giúp bạn hiểu cả cú pháp Java thông thường lẫn cơ chế `java.lang.invoke` phía dưới mà không phụ thuộc vào class name hoặc thủ thuật cụ thể của một JVM.
