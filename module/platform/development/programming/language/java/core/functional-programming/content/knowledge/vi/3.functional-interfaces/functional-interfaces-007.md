# Interface generic và giới hạn của phương thức hàm generic khi dùng lambda trong Java

Java hỗ trợ **functional interface** (giao diện chức năng) và **lambda expression** để coi hành vi như một giá trị có kiểu. Khi áp dụng với generics, có một khác biệt dễ nhầm:

- **Functional interface là generic:** tham số kiểu được khai báo ở cấp interface, còn phương thức trừu tượng duy nhất sử dụng tham số kiểu ấy. Trường hợp này **có thể dùng lambda** khi Java xác định được một kiểu đích phù hợp.
- **Phương thức trừu tượng duy nhất là generic:** chính phương thức đó khai báo tham số kiểu riêng, chẳng hạn phương thức có chữ ký <T> T identity(T value). Interface vẫn có thể là functional interface, nhưng **lambda Java không thể trực tiếp triển khai phương thức trừu tượng generic này**.

Bài học giải thích rõ ranh giới giữa hai loại generic, cách compiler suy luận kiểu, lý do một số lambda không hợp lệ, những giải pháp đúng trong Java 17+, và tác động của wildcard, erasure, method reference đến thiết kế API.

## 1. Nhắc lại functional interface và kiểu đích của lambda

Một functional interface có **một phương thức trừu tượng có hiệu lực** (single abstract method, SAM). Có thể sử dụng @FunctionalInterface để trình biên dịch xác minh ràng buộc này. Interface vẫn được phép có các phương thức default, static, private; các phương thức có chữ ký tương ứng phương thức public của Object không tự tạo thêm SAM. Một số trường hợp kế thừa các phương thức tương đương nhau được hợp nhất theo quy tắc của Java, nên định nghĩa chính xác không đơn thuần là đếm số dòng khai báo.

Ví dụ:

~~~java
@FunctionalInterface
interface Formatter {
    String format(int value);
}

Formatter formatter = n -> "N=" + n;
System.out.println(formatter.format(3)); // N=3
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Lambda n -> "N=" + n không tự mang một kiểu hàm chung; trong Java, biểu thức lambda được kiểm tra theo **target type** (kiểu đích) suy ra từ phép gán, đối số phương thức, cast hoặc ngữ cảnh trả về. Tại đây, target type Formatter cho biết SAM nhận int và trả String.

Java không suy ra một kiểu hàm độc lập rồi tự chuyển nó sang bất kỳ interface nào; tính tương thích được quyết định bởi chữ ký SAM và ràng buộc kiểu của ngữ cảnh.

## 2. Interface generic: tham số kiểu thuộc về interface

Khai báo:

~~~java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T value);
}
~~~

T và R được khai báo **ở cấp Mapper**, không phải bên trong phương thức map. Mỗi lần dùng một kiểu tham số hóa cụ thể, ta được một chữ ký SAM cụ thể:

| Kiểu đích | Chữ ký hành vi của map sau khi thay tham số kiểu | Lambda hoặc method reference |
| --- | --- | --- |
| Mapper<String, Integer> | Integer map(String value) | String::length |
| Mapper<Integer, String> | String map(Integer value) | n -> "value=" + n |
| Mapper<String, String> | String map(String value) | String::trim |
| Mapper<Long, Boolean> | Boolean map(Long value) | n -> n > 0 |

Ví dụ:

~~~java
Mapper<String, Integer> length = s -> s.length();
Mapper<Integer, String> label = n -> "length=" + n;

System.out.println(length.map("Java")); // 4
System.out.println(label.map(4));       // length=4
~~~

Tại thời điểm kiểm tra lambda thứ nhất, compiler đã biết T = String, R = Integer. Phương thức map không khai báo tham số kiểu riêng, nên lambda chỉ cần có hành vi tương thích với **một chữ ký đã chuyên biệt hóa**.

Các functional interface tiêu chuẩn như java.util.function.Function<T, R>, Predicate<T>, Consumer<T>, Supplier<T>, UnaryOperator<T> hoạt động theo nguyên tắc tương tự:

~~~java
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.Predicate<String> nonBlank = s -> !s.isBlank();
java.util.function.UnaryOperator<String> normalize = String::trim;
~~~

Một interface có thể có nhiều tham số kiểu, có giới hạn kiểu (bounds) hoặc kế thừa interface generic khác; yếu tố then chốt vẫn là **phương thức trừu tượng duy nhất được chuyên biệt hóa theo target type có thể được lambda biểu diễn hay không**.

### 2.1. Generic interface vẫn có thể chứa phương thức generic khác

Ví dụ:

~~~java
@FunctionalInterface
interface Transform<T, R> {
    R apply(T input);

    default <V> Transform<T, V> andThen(
            Transform<? super R, ? extends V> next) {
        return input -> next.apply(apply(input));
    }

    static <T> Transform<T, T> identity() {
        return input -> input;
    }
}
~~~

Phương thức **apply** là SAM và không khai báo tham số kiểu riêng. Phương thức andThen khai báo V nhưng là **default**, còn identity khai báo T nhưng là **static**; chúng không làm mất tính chất functional interface. Lambda vẫn dùng được cho Transform<String, Integer>.

Ví dụ cách ghép hàm:

~~~java
Transform<String, Integer> length = String::length;
Transform<Integer, String> toLabel = n -> "size=" + n;
Transform<String, String> composed = length.andThen(toLabel);

System.out.println(composed.apply("ABC")); // size=3
~~~

Đây là các đoạn minh họa; chương trình độc lập ở phần 9 có ví dụ tương ứng đã được biên dịch và chạy.

## 3. Phương thức trừu tượng generic: tham số kiểu thuộc về phương thức

Xét một interface khác:

~~~java
@FunctionalInterface
interface UniversalIdentity {
    <T> T same(T value);
}
~~~

**UniversalIdentity là functional interface hợp lệ:** nó có một phương thức trừu tượng duy nhất, tên là same. Khác với Mapper<T, R>, phương thức same **tự khai báo** tham số kiểu T. Mỗi lần gọi same có thể chọn một T mới:

~~~java
class IdentityImpl implements UniversalIdentity {
    @Override
    public <T> T same(T value) {
        return value;
    }
}

UniversalIdentity identity = new IdentityImpl();

String text = identity.same("Java");    // T = String
Integer number = identity.same(123);   // T = Integer
~~~

Trong cùng một đối tượng UniversalIdentity, phương thức same phải có ngữ nghĩa tương thích với **mọi kiểu T mà người gọi có quyền sử dụng** theo chữ ký. Đây là hợp đồng đa hình theo phương thức (*generic method* hoặc *method-level polymorphism*).

Đọc kỹ hai chữ ký:

~~~java
interface PerInstance<T> {
    T same(T value);            // T của interface
}

interface PerInvocation {
    <T> T same(T value);        // T của riêng phương thức
}
~~~

PerInstance<String> ấn định T = String cho instance đó, nên các lời gọi dùng String. PerInvocation cho phép mỗi lời gọi có một tham số kiểu mới. Hai thiết kế có mục đích khác nhau dù cùng chứa tên T.

### 3.1. Vì sao vẫn dùng được @FunctionalInterface?

Điều kiện một SAM không loại bỏ phương thức generic. Annotation @FunctionalInterface chỉ xác nhận số lượng và tính hợp lệ của các phương thức trừu tượng theo quy tắc interface; nó **không bảo đảm mọi biểu thức lambda đều tương thích** với interface đó.

Một kết luận cần nhớ: **mọi lambda cần target type là functional interface, nhưng không phải mọi functional interface đều là target type hợp lệ cho lambda**. Trường hợp SAM generic là ví dụ điển hình cho chiều ngược lại.

## 4. Giới hạn cụ thể: lambda không triển khai trực tiếp generic SAM

Thử viết:

~~~java
@FunctionalInterface
interface UniversalIdentity {
    <T> T same(T value);
}

// KHÔNG BIÊN DỊCH — chỉ minh họa lỗi:
UniversalIdentity identity = value -> value;
~~~

Java từ chối biểu thức lambda này vì **function descriptor là generic**. Lambda không có cú pháp khai báo tham số kiểu của riêng nó để biểu diễn một hàm áp dụng cho mọi T của phương thức same.

Tính generic của functional method khác với việc compiler có thể suy luận một T cụ thể của Mapper<String, String>. Nếu chấp nhận lambda ở trên như một hàm chuyên biệt hóa cho một kiểu bất kỳ, nó sẽ không đáp ứng hợp đồng gọi same với mọi T. Nếu coi nó là một hàm đa hình cho mọi T, Java lại không cung cấp mô hình cú pháp/kiểm tra kiểu tương ứng cho lambda.

Không khắc phục được vấn đề bằng cách thêm kiểu tham số lambda:

~~~java
// VẪN KHÔNG HỢP LỆ đối với UniversalIdentity:
UniversalIdentity identity = (Object value) -> value;
~~~

Cách viết (Object value) chỉ chỉ định kiểu tham số **Object**, không khai báo <T> cho chính phương thức same. Vấn đề ở đây không đơn thuần là Java chưa suy luận được kiểu String hay Integer.

### 4.1. Không nhầm lỗi này với Generic interface

Hai ví dụ sau **hợp lệ**:

~~~java
Mapper<String, String> echoString = value -> value;
Mapper<Integer, Integer> echoNumber = value -> value;
~~~

Chúng là hai đối tượng Mapper với hai kiểu đích riêng. Chúng **không phải** một đối tượng duy nhất có phương thức generic cùng áp dụng cho mọi kiểu như UniversalIdentity.

### 4.2. Giới hạn vẫn có khi phương thức generic có bounds

Ví dụ:

~~~java
@FunctionalInterface
interface NumberIdentity {
    <N extends Number> N same(N value);
}
~~~

Phương thức same vẫn generic vì tự khai báo N. Việc giới hạn N extends Number không loại bỏ giới hạn của lambda. Nếu nghiệp vụ chỉ cần một kiểu cố định, có thể thiết kế lại:

~~~java
@FunctionalInterface
interface NumberTransform<N extends Number> {
    N apply(N value);
}

NumberTransform<Integer> keep = n -> n;
~~~

Ở đây N là tham số kiểu của interface và đã được chọn là Integer tại kiểu đích. Tuy nhiên, lựa chọn này thay đổi hợp đồng: **một instance giữ một kiểu N**, thay vì **mỗi lời gọi tự chọn N**.

## 5. Các cách triển khai đúng với SAM generic

### Cách 1: Dùng lớp hoặc anonymous class triển khai phương thức generic

~~~java
UniversalIdentity identity = new UniversalIdentity() {
    @Override
    public <T> T same(T value) {
        return value;
    }
};
~~~

Đoạn mã này hợp lệ vì phương thức của lớp ẩn danh **có thể tự khai báo <T>**. Một lớp đặt tên cài đặt SAM generic cũng tương tự:

~~~java
final class IdentityImpl implements UniversalIdentity {
    @Override
    public <T> T same(T value) {
        return value;
    }
}
~~~

Thích hợp khi hành vi thực sự phải áp dụng đồng đều cho nhiều kiểu trong cùng instance, hoặc khi cần tên lớp rõ ràng cho kiểm thử và quản lý dependency.

### Cách 2: Dùng method reference tới phương thức generic tương thích

Java cho phép một số **method reference** tới phương thức generic thích ứng với SAM generic:

~~~java
final class Helpers {
    static <T> T identity(T value) {
        return value;
    }
}

UniversalIdentity identity = Helpers::identity;
System.out.println(identity.same("abc")); // abc
System.out.println(identity.same(42));    // 42
~~~

Trường hợp trên **hợp lệ**, dù cách viết identity = x -> x không hợp lệ. Method reference trỏ tới một phương thức generic thực sự đã khai báo <T>, vì vậy compiler có thể kiểm tra rằng phương thức được tham chiếu đáp ứng chữ ký generic của SAM.

Điều này **không** có nghĩa mọi method reference đều dùng được với generic SAM. Một method reference tới phương thức chỉ nhận String, chẳng hạn String::trim, không thể tự đáp ứng hợp đồng <T> T same(T value) cho mọi T. Phải thỏa cả kiểu trả về, tham số, các bounds và checked exceptions.

### Cách 3: Nếu không cần mỗi lời gọi đổi kiểu, đưa generic lên interface

Nhiều bài toán thực tế chỉ cần thao tác trên **một kiểu được xác định tại vị trí dùng**, chẳng hạn parse chuỗi, chuẩn hóa tên, tính giá:

~~~java
@FunctionalInterface
interface Converter<T, R> {
    R convert(T input);
}

Converter<String, Integer> toInteger = Integer::parseInt;
Converter<Integer, String> toText = n -> "ID-" + n;
~~~

Cách này thường đơn giản hơn, sử dụng lambda trực tiếp, và giữ được kiểm tra kiểu mạnh.

### Cách 4: Dùng các functional interface chuẩn khi khớp hợp đồng

~~~java
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.UnaryOperator<String> trim = String::trim;
java.util.function.Predicate<String> hasText = s -> !s.isBlank();
~~~

Function<T,R> có interface generic nhưng apply(T) không phải phương thức generic. Nếu mục tiêu là nhận vào T và trả R đã biết từ ngữ cảnh, không cần tự phát minh interface. Chỉ tạo interface riêng khi tên hành vi, tài liệu hợp đồng hoặc phương thức bổ trợ có giá trị thực sự.

## 6. Phương thức generic thông thường kết hợp với lambda ra sao?

Một phương thức Java có thể khai báo type parameter **ở phương thức chứa lời gọi lambda**, trong khi lambda vẫn nhắm đến SAM không generic:

~~~java
static <T> T choose(T first, T second,
                    java.util.function.Predicate<T> preferFirst) {
    return preferFirst.test(first) ? first : second;
}
~~~

Khi gọi:

~~~java
String longer = choose("Java", "Go",
    s -> s.length() > 2);
~~~

Compiler suy ra T = String cho **một lời gọi choose**; sau đó Predicate<String> là target type của lambda. Đây là cách dùng generic method với lambda hoàn toàn hợp lệ, vì **phương thức SAM Predicate.test(T) không tự khai báo type parameter**.

Phân biệt hai trường hợp:

1. Phương thức chứa lời gọi (choose) generic, nhưng lambda nhận target Predicate<T> đã được suy luận: **hợp lệ**.
2. Phương thức trừu tượng duy nhất mà lambda định cài đặt **tự khai báo <T>**: **không hợp lệ**.

### 6.1. Generic method reference chuyên biệt hóa theo target

~~~java
class Helpers {
    static <T> T identity(T value) {
        return value;
    }
}

java.util.function.Function<String, String> stringId =
    Helpers::identity;
java.util.function.Function<Integer, Integer> intId =
    Helpers::identity;
~~~

Cùng một generic method identity có thể làm method reference cho các target type **không generic ở cấp SAM**. Compiler kiểm tra khả năng áp dụng sau khi suy luận T theo target. Phương thức Java generic và phương thức trừu tượng generic là hai điều khác nhau.

## 7. Bounds và wildcards: an toàn kiểu khi truyền generic functional interface

Trong thiết kế API, cần phân biệt **tham số kiểu T, R** với **wildcard có giới hạn**:

~~~java
@FunctionalInterface
interface Transformer<T, R> {
    R transform(T value);
}
~~~

Một hàm nhận Transformer có thể được khai báo:

~~~java
static <T, R> java.util.List<R> mapAll(
        java.util.List<T> values,
        Transformer<? super T, ? extends R> transformer) {

    return values.stream()
        .<R>map(transformer::transform)
        .toList();
}
~~~

Đây là **đoạn minh họa** có thể đặt cùng với khai báo Transformer; chương trình đầy đủ ở phần 9 sử dụng đúng chữ ký này.

- **? super T** ở đầu vào: transformer nhận được các phần tử T vì nó chấp nhận T hoặc kiểu cha của T.
- **? extends R** ở đầu ra: transformer trả về R hoặc kiểu con của R, phù hợp với nơi cần R.
- Đây là cách áp dụng quy tắc *producer extends, consumer super* (PECS) vào hành vi vừa nhận vừa trả giá trị.
- **.<R>map(...)** là đối số kiểu tường minh của phương thức Stream.map để yêu cầu kết quả Stream<R>. Nếu chỉ để compiler suy luận từ method reference, nó có thể suy ra kiểu capture CAP#1 extends R, và khi gọi Stream.toList() kiểu List<CAP#1> không tự chuyển thành List<R>, vì List là invariant.

Ví dụ về variance:

~~~java
Transformer<CharSequence, Integer> countChars =
    CharSequence::length;

java.util.List<String> names =
    java.util.List.of("An", "Binh");

// Transformer nhận CharSequence, nên cũng nhận từng String.
java.util.List<Number> lengths =
    mapAll(names, countChars);
~~~

Phép gọi có thể suy luận T = String và R = Number (được trợ giúp bởi target type của phép gán); đầu ra Integer là subtype của Number. Cần nhớ rằng **List<Integer> không phải subtype của List<Number>**. Chữ ký mapAll trả List<R> và được kiểm tra kiểu ngay lúc gọi, không có phép chuyển đổi List bất biến kiểu một cách tùy tiện.

### 7.1. Không tự ý thay wildcard bằng raw type

~~~java
Transformer raw = (Object value) -> value;
~~~

Cú pháp raw type có thể biên dịch với cảnh báo ở ngữ cảnh phù hợp, nhưng làm mất thông tin generic và dễ dẫn đến ClassCastException do cast do compiler chèn khi sử dụng kết quả. Dùng raw type để “né” lỗi generic SAM cũng không làm lambda triển khai được phương thức có type parameter riêng. Ưu tiên type parameter/wildcard cụ thể và kiểm tra cảnh báo biên dịch.

### 7.2. Bounds còn ràng buộc khả năng gọi

Ví dụ:

~~~java
@FunctionalInterface
interface NumberFunction<N extends Number, R> {
    R apply(N number);
}

NumberFunction<Integer, String> format = n -> "n=" + n;
~~~

NumberFunction<String, String> sẽ không hợp lệ do String không kế thừa Number. Lambda không được phép bỏ qua các bounds hay tự khiến interface chấp nhận mọi kiểu. Bounds của generic SAM (ví dụ <N extends Number> N same(N n)) vẫn phải tuân thủ dù được triển khai bằng lớp đặt tên hoặc method reference.

## 8. Type erasure, overload và giới hạn runtime

Java generics chủ yếu được kiểm tra ở **thời điểm biên dịch**; đối số kiểu thường bị xóa (type erasure) khi tạo bytecode. Với Mapper<T,R>, chữ ký sau erasure về cơ bản làm việc với Object theo bound của tham số kiểu, còn compiler bảo đảm các phép chuyển kiểu phù hợp tại điểm sử dụng.

Ví dụ:

~~~java
interface Mapper<T, R> {
    R map(T value);
}

final class Uppercase implements Mapper<String, String> {
    @Override
    public String map(String value) {
        return value.toUpperCase();
    }
}
~~~

Ở mức bytecode, trình biên dịch có thể tạo **bridge method** để duy trì polymorphism sau erasure. Đây là việc thực thi generic interface bình thường, không phải bằng chứng rằng lambda/generic bị mất an toàn kiểu nếu viết đúng.

Một hệ quả quan trọng: không thể overload hai phương thức chỉ dựa vào đối số generic khác nhau của cùng một interface vì chữ ký sau erasure trùng nhau:

~~~java
// KHÔNG BIÊN DỊCH — hai overload có cùng erasure:
void run(Mapper<String, String> mapper) { }
void run(Mapper<Integer, Integer> mapper) { }
~~~

Không nên “sửa” bằng raw type hoặc cast thiếu kiểm soát. Đổi tên phương thức, thiết kế một generic method run<T> hoặc bổ sung tham số phân biệt có ý nghĩa nghiệp vụ.

**Generic interface không phải reified type:** ở runtime, thông thường không thể hỏi trực tiếp một instance Mapper<String, Integer> để lấy đầy đủ đối số kiểu String/Integer như một Class<T> được lưu sẵn. Nếu cần thông tin kiểu runtime cho parse, serialize hoặc reflection, thiết kế API để nhận Class<T> hoặc một type token phù hợp. Giới hạn này độc lập với quy tắc lambda không triển khai SAM generic.

### 8.1. Kiểu đích và overload ảnh hưởng suy luận

Ví dụ sau dùng cast để cung cấp ngữ cảnh rõ ràng:

~~~java
Mapper<String, Integer> length = (String s) -> s.length();
~~~

Thông thường, không cần ghi String trong lambda khi phép gán đã rõ. Nhưng nếu một lời gọi overloaded có nhiều functional interface SAM tương thích, compiler có thể báo *ambiguous method call*. Khi đó nên cung cấp biến có kiểu khai báo rõ hoặc cast tới functional interface dự định, đồng thời cân nhắc thiết kế overload dễ đọc hơn.

Đừng nhầm lỗi overload mơ hồ với giới hạn của generic SAM: hai lỗi có nguyên nhân khác nhau.

## 9. Chương trình hoàn chỉnh: generic interface, method reference và generic SAM

Ví dụ này có thể biên dịch với **Java 17 trở lên**. Nó minh họa:

1. Transformer<T,R> là generic functional interface dùng lambda/method reference.
2. andThen là generic default method, vẫn giữ Transformer là functional interface.
3. mapAll là generic method nhận transformer với variance thích hợp.
4. UniversalIdentity có **generic SAM**; được triển khai bằng lớp đặt tên và method reference tới phương thức generic.
5. Chuyên biệt hóa một generic method theo target Transformer<String,String>.

Tạo tệp **GenericFunctionalDemo.java**:

~~~java
import java.util.List;

public class GenericFunctionalDemo {
    @FunctionalInterface
    interface Transformer<T, R> {
        R transform(T value);

        default <V> Transformer<T, V> andThen(
                Transformer<? super R, ? extends V> next) {
            return value -> next.transform(transform(value));
        }
    }

    @FunctionalInterface
    interface UniversalIdentity {
        <T> T same(T value);
    }

    static final class IdentityImpl implements UniversalIdentity {
        @Override
        public <T> T same(T value) {
            return value;
        }
    }

    static final class Helpers {
        static <T> T identity(T value) {
            return value;
        }
    }

    static <T, R> List<R> mapAll(
            List<T> values,
            Transformer<? super T, ? extends R> transformer) {
        return values.stream()
            .<R>map(transformer::transform)
            .toList();
    }

    public static void main(String[] args) {
        Transformer<String, Integer> length = String::length;
        Transformer<Integer, String> label = n -> "length=" + n;
        Transformer<String, String> pipeline = length.andThen(label);
        System.out.println(pipeline.transform("Java"));

        System.out.println(
            mapAll(List.of("A", "BC", "DEF"), length)
        );

        Transformer<String, String> specialized = Helpers::identity;
        System.out.println(specialized.transform("typed"));

        UniversalIdentity generic = new IdentityImpl();
        System.out.println(generic.same(7));
        System.out.println(generic.same("seven"));

        UniversalIdentity genericRef = Helpers::identity;
        System.out.println(genericRef.same(42));
    }
}
~~~

Trong thư mục chứa tệp, biên dịch và chạy:

~~~bash
javac GenericFunctionalDemo.java
java GenericFunctionalDemo
~~~

Stdout chính xác:

~~~text
length=4
[1, 2, 3]
typed
7
seven
42
~~~

Giải thích theo từng nhóm:

- length là Transformer<String,Integer>: SAM transform có đầu vào String, kết quả Integer. String::length trả int được boxing thành Integer theo target type.
- label là Transformer<Integer,String>; andThen nối hai hành vi: "Java" → 4 → "length=4".
- mapAll dùng cùng transformer length trên danh sách ba chuỗi; dòng .<R>map(...) cung cấp kiểu đích đầu ra để tương thích wildcard.
- Helpers::identity là method reference tới generic static method. Khi target là Transformer<String,String>, compiler chuyên biệt hóa nó cho String.
- IdentityImpl thực sự có phương thức public <T> T same(T), nên một instance generic xử lý được cả Integer 7 và String "seven".
- UniversalIdentity genericRef = Helpers::identity cũng hợp lệ, vì method reference tới phương thức generic đáp ứng được SAM generic. Dòng cuối in 42.

Chương trình không chứa ví dụ cố ý sai để vẫn biên dịch toàn bộ. Các đoạn không hợp lệ trước đó chỉ phục vụ phân tích quy tắc compile-time và không nên dán chung vào tệp chạy.

## 10. Thiết kế API nên chọn loại generic nào?

| Nhu cầu | Thiết kế ưu tiên | Lý do |
| --- | --- | --- |
| Một instance biến đổi T sang R cố định | Mapper<T,R> hoặc Function<T,R> | Lambda tự nhiên; type inference rõ |
| Một instance nhận đầu vào T rồi trả cùng T | UnaryOperator<T> hoặc custom interface generic | Một kiểu T tại target type |
| Mỗi lần gọi cùng instance phải chọn T riêng | SAM với method-level <T>, nếu thực sự cần | Đa hình ở mức phương thức; triển khai bằng class/method reference phù hợp |
| Chỉ một phương thức tiện ích cần generic | static <T> T helper(T value) | Không cần tạo SAM generic |
| Cần kết hợp pipeline với đầu vào/đầu ra linh hoạt | Function.compose/andThen hoặc custom default method dùng PECS | Có thể ghép hàm và giữ type safety |
| Muốn dùng Java lambda nhưng hợp đồng SAM generic gây trở ngại | Xác định có thể chuyên biệt hóa T ở cấp interface hay không | Đổi hợp đồng khi nghiệp vụ cho phép, tránh cast/raw type |

### 10.1. Đừng thiết kế SAM generic chỉ để “tái sử dụng tối đa”

Một interface có chữ ký <T> T same(T value) có cam kết rất mạnh: caller có thể yêu cầu kết quả cùng T với nhiều kiểu khác nhau. Phần lớn phép chuyển đổi hữu ích như parse String thành Integer, đọc file, chuyển JSON thành DTO **không đáp ứng cùng một hợp đồng cho mọi T** mà không có Class<T>, type token hoặc dữ liệu bổ sung.

Ví dụ Converter<T,R> phản ánh đúng việc đầu vào và đầu ra có thể khác kiểu. Nếu dùng generic SAM <T> T convert(T), một hàm chỉ nhận chuỗi lại bị ép phải xử lý tất cả T; đó thường là thiết kế sai dù có thể viết lớp triển khai với cast nguy hiểm.

### 10.2. Có thể để generic ở phương thức bao ngoài

Nếu nhu cầu là áp dụng callback đã được chuyên biệt hóa cho mỗi lần gọi, viết phương thức generic bình thường:

~~~java
static <T, R> R applyOnce(
        T input,
        java.util.function.Function<? super T, ? extends R> fn) {
    return fn.apply(input);
}
~~~

Mỗi lần gọi applyOnce có thể chọn T/R mới và nhận một lambda phù hợp:

~~~java
int size = applyOnce("Java", s -> s.length());
String text = applyOnce(12, n -> "n=" + n);
~~~

Ở đây lambda vẫn nhắm vào **Function<T,R> sau khi suy luận kiểu của từng lời gọi**, không cần một SAM có phương thức trừu tượng generic.

### 10.3. Giới hạn ngoại lệ checked vẫn áp dụng

Một SAM có khai báo throws cho phép lambda có phần thân ném checked exception tương ứng; SAM không khai báo throws thì lambda không được tự do ném checked exception chưa xử lý. Generic type parameter, bounds hoặc method reference không tự động bỏ qua quy tắc checked exceptions.

~~~java
@FunctionalInterface
interface Loader<T> {
    T load(String path) throws java.io.IOException;
}
~~~

Đây là **generic interface với SAM không generic**; một lambda đọc file có thể dùng Loader<String> nếu trả String và tuân thủ khai báo IOException. Không nên giải quyết bằng cách bắt hết Exception rồi trả null, vì làm mất ý nghĩa lỗi.

## 11. Lỗi thường gặp và cách chẩn đoán

**Lỗi 1 — đánh đồng interface generic và SAM generic.** Thấy <T> trong bất kỳ vị trí nào rồi kết luận “lambda không dùng được” là sai. Hỏi cụ thể: <T> được khai báo sau tên interface, hay ngay trước kiểu trả về của SAM?

**Lỗi 2 — nghĩ @FunctionalInterface bảo đảm gán lambda thành công.** Annotation xác nhận một phương thức trừu tượng có hiệu lực. Nó không xóa tham số kiểu của phương thức generic, nên trường hợp UniversalIdentity vẫn bị compiler từ chối khi dùng lambda trực tiếp.

**Lỗi 3 — sửa lỗi bằng cast Object.** Với generic SAM, tham số Object chỉ mô tả một chữ ký cụ thể; nó không tạo phương thức có khai báo <T>. Nếu API thực sự cần hoạt động cho mọi T, hãy giữ phương thức generic và triển khai bằng class hoặc method reference generic tương thích.

**Lỗi 4 — thay Function<T,R> bằng Function<Object,Object>.** Thiết kế này làm mất quan hệ tĩnh giữa kiểu đầu vào/đầu ra, buộc nơi gọi ép kiểu và có thể gây ClassCastException. Hãy giữ type parameter ở interface hoặc phương thức generic bao ngoài.

**Lỗi 5 — dùng List<? extends R> nhưng mong tự gán thành List<R>.** Wildcard producer không có nghĩa hai kiểu List là subtype của nhau. Cần xem lại chữ ký trả về, dùng phép biến đổi tạo List<R> hợp lệ, hoặc dùng đối số kiểu tường minh khi suy luận bị capture.

**Lỗi 6 — overload chỉ khác tham số kiểu.** Hai phương thức nhận Mapper<String,String> và Mapper<Integer,Integer> thường xung đột do erasure. Tạo một generic method, dùng tên rõ hơn hoặc thay đổi cấu trúc tham số.

**Lỗi 7 — mong generic lambda trở thành một “higher-rank polymorphic function”.** Java lambda không có cú pháp khai báo một type parameter mới cho chính function descriptor của nó. Generic methods, method references và các kiểu hàm khác nhau đáp ứng những bài toán khác nhau; không có một phép cast thần kỳ để thay thế.

**Lỗi 8 — bỏ qua tên/giới hạn của target type khi debug.** Khi lỗi lambda xuất hiện, hãy kiểm tra target functional interface, chữ ký SAM đã thay type parameter, return type, overloaded method và checked exceptions. Lỗi có thể do suy luận kiểu, không nhất thiết do chính khái niệm generic SAM.

## 12. Câu hỏi tự kiểm tra

1. Vì sao Mapper<T,R> với phương thức R map(T value) nhận lambda khi target là Mapper<String,Integer>?
2. Vì sao UniversalIdentity có phương thức <T> T same(T value) vẫn hợp lệ với @FunctionalInterface nhưng không thể gán trực tiếp value -> value?
3. Tại sao một generic method reference Helpers::identity lại có thể triển khai UniversalIdentity trong khi lambda tương tự bị từ chối?
4. Một default method <V> Transform<T,V> andThen(...) có làm mất tính functional interface hay không? Vì sao?
5. Tại sao Transformer<? super T,? extends R> phù hợp với một hàm chuyển đổi, và vì sao List<? extends R> không tự động chuyển thành List<R>?
6. Nếu mỗi lần gọi thao tác trên một kiểu T khác nhau, nên dùng generic method ở đâu để vừa giữ hợp đồng đúng vừa dùng được lambda?
7. Vì sao generic erasure khiến hai overload chỉ khác đối số kiểu của cùng Mapper không hợp lệ?

**Kết luận kiến thức:** Java lambda làm việc hiệu quả với **functional interface generic ở cấp interface** vì compiler xác định một SAM cụ thể từ target type. Khi **SAM tự khai báo tham số kiểu**, interface vẫn có thể là functional interface nhưng Java lambda không biểu diễn trực tiếp được phương thức đa hình đó. Dùng **lớp triển khai, anonymous class hoặc method reference tới generic method tương thích** nếu cần giữ generic SAM; chọn **Function<T,R>, UnaryOperator<T> hoặc custom functional interface generic** khi nghiệp vụ chỉ cần kiểu được cố định tại từng vị trí sử dụng.