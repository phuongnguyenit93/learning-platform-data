# Quan hệ giữa method reference với lambda trong Java

**Method reference** (tham chiếu phương thức, dùng cú pháp `::`) và **lambda expression** (biểu thức lambda, dùng cú pháp `->`) là hai cách diễn đạt hành vi khi Java cần một **functional interface**. Method reference thường là cách viết ngắn gọn khi phần thân lambda chủ yếu **chuyển các đối số tới một phương thức hoặc constructor có sẵn**. Lambda tổng quát hơn: có thể kiểm tra điều kiện, xử lý nhiều bước, biến đổi tham số, kết hợp nhiều lời gọi, hoặc chủ động bắt ngoại lệ.

Quan hệ cốt lõi:

- **Giống nhau:** cả hai đều được gõ kiểu theo **target functional interface**; đều có thể tạo đối tượng tương thích với phương thức trừu tượng duy nhất (*single abstract method*, SAM); hành vi chạy khi SAM được gọi, không phải chỉ vì ta vừa khai báo một biến.
- **Khác nhau:** lambda chứa **thân code do bạn viết**; method reference **trỏ tới một phương thức/constructor cụ thể** và để compiler nối chữ ký của nó với chữ ký SAM.
- **Không phải phép thay thế văn bản 100%:** thời điểm tính toán receiver, chọn overload, ràng buộc kiểu generic, checked exception và cả trường hợp có thể viết method reference nhưng không biểu đạt được bằng lambda trực tiếp đều có thể khác.

Bài này tập trung vào mối quan hệ và các điểm **còn áp dụng trong Java hiện đại**. Java 8 đã hỗ trợ cả lambda lẫn method reference; chương trình minh họa có thể biên dịch bằng Java 17 và chỉ rõ API nào đòi phiên bản mới hơn.

## 1. Cùng đích: một hợp đồng functional interface

Java không có kiểu hàm độc lập như `(String) -> String` để khai báo biến theo kiểu đó. Thay vào đó, compiler dựa vào **functional interface** chứa một hợp đồng phương thức trừu tượng, chẳng hạn:

| Target type | Phương thức chức năng | Lambda | Method reference |
| --- | --- | --- | --- |
| `Function<String,String>` | `String apply(String)` | `s -> s.trim()` | `String::trim` |
| `Predicate<String>` | `boolean test(String)` | `s -> s.isEmpty()` | `String::isEmpty` |
| `Consumer<String>` | `void accept(String)` | `s -> System.out.println(s)` | `System.out::println` |
| `Supplier<List<String>>` | `List<String> get()` | `() -> new ArrayList<String>()` | `ArrayList<String>::new` |
| `Comparator<String>` | `int compare(String,String)` | `(a,b) -> a.compareToIgnoreCase(b)` | `String::compareToIgnoreCase` |
| `Function<String,Integer>` | `Integer apply(String)` | `s -> Integer.parseInt(s)` | `Integer::parseInt` |

Các khai báo trên là **minh họa trong một phương thức**; khi tự chạy phải import `java.util.*`, `java.util.function.*` và dùng interface `java.util.Comparator` (được bao gồm trong `java.util.*`). Với `Function<String,Integer>`, phương thức `Integer.parseInt` trả primitive `int`, rồi boxing thành `Integer` khi phù hợp target.

Với `Function<String,String> normalize = String::trim;`, compiler hiểu target cần một phương thức nhận `String`, trả `String`. `String::trim` là tham chiếu tới phương thức instance không có đối số tường minh; chuỗi từ `apply` được dùng làm **receiver** của lời gọi. Ý nghĩa tương ứng thường là `s -> s.trim()`.

**Cả lambda và method reference đều là *poly expressions*.** Chúng không có kiểu được xác định độc lập trong mọi ngữ cảnh; kiểu đích từ phép gán, tham số của phương thức gọi hoặc ép kiểu quyết định chúng có hợp lệ không. Do đó:

~~~java
Function<String, String> trim1 = String::trim;
Function<String, String> trim2 = s -> s.trim();
~~~

là hợp lệ (trong một phương thức, có import `Function`), còn:

~~~java
// SAI: var không đưa ra target functional-interface type.
var unknownReference = String::trim;
var unknownLambda = s -> s.trim();
~~~

không biên dịch. Dùng một target type tường minh hoặc truyền chúng vào API có tham số functional interface rõ ràng.

## 2. Bốn cách viết method reference quan trọng

### 2.1. Tham chiếu phương thức static — `Type::staticMethod`

~~~java
Function<String, Integer> parse1 = Integer::parseInt;
Function<String, Integer> parse2 = text -> Integer.parseInt(text);
~~~

`parse1.apply("42")` và `parse2.apply("42")` cùng trả `42`. Method reference ở đây không cần receiver instance vì `parseInt` là static method.

Ví dụ khác:

~~~java
Predicate<Object> isNull = Objects::isNull;
Function<String, String> uppercase = text -> text.toUpperCase(Locale.ROOT);
~~~

Với `Objects::isNull`, logic tương đương thường là `value -> Objects.isNull(value)`. Với `uppercase`, ta cố ý chọn lambda để truyền `Locale.ROOT`, vì method reference `String::toUpperCase` không tự thêm đối số locale theo ý muốn. Dùng lambda khi cần **chèn tham số cố định, biến đổi tham số, kiểm soát null hoặc ghép thao tác**.

### 2.2. Tham chiếu phương thức instance đã có receiver — `expression::instanceMethod`

~~~java
String prefix = "ID:";
Function<String, String> addPrefixRef = prefix::concat;
Function<String, String> addPrefixLambda = s -> prefix.concat(s);
~~~

Cả hai đều tạo chuỗi có prefix, ví dụ `"ID:A"` khi nhận `"A"`. Ở method reference `prefix::concat`, **receiver là chính đối tượng `prefix` đã được chọn tại thời điểm tạo tham chiếu**; đối số được truyền vào `concat`.

Method reference với receiver đã có cũng rất thường gặp ở callback:

~~~java
List<String> names = new ArrayList<>();
Consumer<String> add = names::add;
Consumer<String> print = System.out::println;
~~~

`names::add` gọi vào **danh sách `names` cụ thể**, còn `System.out::println` chọn PrintStream hiện tại khi biểu thức tạo tham chiếu được đánh giá. `List.add` trả `boolean` nhưng có thể nối vào `Consumer<String>` trả `void`: kết quả boolean bị bỏ, **thao tác thêm vào danh sách vẫn xảy ra**.

Với receiver expression có side effect hoặc có khả năng trả `null`, thời điểm đánh giá rất quan trọng. Phần 5 giải thích và chạy thử chính xác.

### 2.3. Tham chiếu phương thức instance của một kiểu — `Type::instanceMethod`

~~~java
Function<String, String> trimRef = String::trim;
Function<String, String> trimLambda = text -> text.trim();
~~~

Không có đối tượng `String` được cố định khi tạo `String::trim`. Thay vào đó, đối số **đầu tiên** của SAM đóng vai receiver. Nếu instance method còn có tham số, các đối số **tiếp theo** của SAM cung cấp tham số đó:

~~~java
BiFunction<String, String, Boolean> startsWithRef = String::startsWith;
BiFunction<String, String, Boolean> startsWithLambda =
        (text, prefix) -> text.startsWith(prefix);
~~~

Lời gọi `startsWithRef.apply("lambda", "lam")` trả `true`. Đừng nhầm `String::startsWith` là một static method; chữ ký SAM của `BiFunction` có hai đối số vì đối số đầu là **receiver**.

Một trường hợp quen thuộc:

~~~java
Comparator<String> compare = String::compareToIgnoreCase;
List<String> words = new ArrayList<>(List.of("b", "A", "c"));
words.sort(compare);
~~~

`String::compareToIgnoreCase` ở đây tương ứng với `(left,right) -> left.compareToIgnoreCase(right)`. `List.of` có từ Java 9; phần semantics method reference đã có từ Java 8.

### 2.4. Tham chiếu constructor hoặc array constructor — `Type::new`

~~~java
Supplier<ArrayList<String>> makeList = ArrayList::new;
Function<Integer, String[]> makeArray = String[]::new;
Function<String, StringBuilder> makeBuilder = StringBuilder::new;
~~~

Tương ứng theo ý nghĩa với:

~~~java
Supplier<ArrayList<String>> makeList2 = () -> new ArrayList<>();
Function<Integer, String[]> makeArray2 = n -> new String[n];
Function<String, StringBuilder> makeBuilder2 = text -> new StringBuilder(text);
~~~

Method reference constructor **không dựng object ngay khi khai báo**. Mỗi lần gọi `makeList.get()` hoặc `makeArray.apply(n)`, constructor/array creation tương ứng mới thực hiện. Khác với tham chiếu tới **receiver object đã có**, trường hợp `ArrayList::new` không capture một `ArrayList` duy nhất.

Cùng cú pháp `::new`, compiler phải lựa chọn constructor phù hợp theo **đối số và kết quả SAM**. Khi overload nhiều constructor, target functional interface giúp chọn bản tương thích.

**Ghi chú bổ sung:** JLS còn có dạng `super::method` hoặc `TypeName.super::method` trong ngữ cảnh instance hợp lệ để tham chiếu implementation của superclass/superinterface. Chúng không phải một “kiểu hàm” mới; vẫn cần target functional interface. Dùng khi thực sự muốn gọi implementation từ cha, không phải làm mẫu thay cho mọi lambda.

## 3. Quy tắc ánh xạ đối số: nắm receiver và chữ ký SAM

Một cách đọc hữu ích:

| Cú pháp | Có receiver khi tạo tham chiếu? | Đối số SAM đi đâu? | Lambda tương ứng thông thường |
| --- | --- | --- | --- |
| `Util::parse` (static) | Không | Truyền thành tham số cho static method | `x -> Util.parse(x)` |
| `object::save` (bound) | Có, đánh giá ngay | Truyền cho method của object đã chọn | `x -> object.save(x)` (nếu receiver bất biến trong ngữ cảnh) |
| `String::trim` (unbound) | Không | Đối số SAM đầu là receiver | `s -> s.trim()` |
| `String::startsWith` (unbound) | Không | Đối số 1 là receiver, đối số 2 là prefix | `(s,p) -> s.startsWith(p)` |
| `Task::new` (constructor) | Không có instance đích trước | Tham số truyền vào constructor | `x -> new Task(x)` |
| `String[]::new` (array) | Không | Đối số là kích thước array | `size -> new String[size]` |

**Số tham số phải khớp hợp đồng SAM.** Chẳng hạn `String::trim` không phù hợp trực tiếp với `Supplier<String>`, vì Supplier có 0 tham số nhưng phương thức unbound cần một đối tượng String làm receiver. Ngược lại `"  hi  "::trim` là **bound reference**, nên có thể dùng với `Supplier<String>`:

~~~java
Supplier<String> bound = " hi "::trim;
String value = bound.get(); // "hi"
~~~

Với ví dụ khai báo `BiFunction<String,String,Boolean> starts = String::startsWith;`, compiler phải xét overload `startsWith(String)` và `startsWith(String,int)` để tìm ra thành viên phù hợp chữ ký mục tiêu. Không đơn giản cứ thấy một tên method là mặc định compiler chọn một phiên bản tùy ý.

## 4. Lambda và method reference đều dùng target typing

Ví dụ biểu thức truyền trực tiếp vào API:

~~~java
List<String> names = List.of(" Lan ", " An ");
List<String> normalized = names.stream()
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .toList();
~~~

`Stream.map` có tham số kiểu `Function<? super T,? extends R>`, nên `String::trim` được hiểu là function từ `String` sang `String`. `filter` cần `Predicate<? super T>`, nên lambda trả boolean. `toList()` (Java 16+) trả danh sách **không sửa được**; với dữ liệu trên, `normalized` chứa `["Lan", "An"]`. Khi cần danh sách sửa được, dùng `collect(Collectors.toCollection(ArrayList::new))`.

Thay bằng lambda tương đương:

~~~java
List<String> normalizedLambda = names.stream()
    .map(s -> s.trim())
    .filter(s -> !s.isEmpty())
    .toList();
~~~

Kết quả giống nhau trong trường hợp này. Từ góc nhìn người đọc, method reference diễn tả “áp dụng đúng phương thức đang có”; lambda cho thấy trực tiếp đối số và dễ bổ sung logic.

**Không nên ép mọi lambda thành method reference.** Nếu nghiệp vụ cần nhiều bước, viết lambda rõ hơn:

~~~java
Function<String, String> normalizeName = name -> {
    if (name == null) return "(missing)";
    String cleaned = name.strip(); // Java 11+
    return cleaned.isEmpty() ? "(empty)" : cleaned.toUpperCase(Locale.ROOT);
};
~~~

Không có một tham chiếu trực tiếp tới một method có sẵn nào thể hiện đầy đủ quy tắc này nếu không tự viết method helper mới. Nếu helper đã có và tạo tên tốt, lúc đó `ClassName::normalizeName` có thể phù hợp.

## 5. Khác biệt lớn: thời điểm đánh giá receiver và tác dụng phụ

**Method reference dạng `expression::method` đánh giá receiver expression ngay lúc tạo reference.** Phương thức đích chưa được gọi ngay, nhưng phần biểu thức **chọn receiver** đã chạy. Nếu receiver tính ra `null`, Java ném `NullPointerException` ngay tại **thời điểm tạo bound reference**. Ngược lại lambda `() -> expression.method()` chỉ tính `expression` khi SAM được gọi.

Phân biệt:

~~~java
Supplier<String> reference = select()::toUpperCase;   // select() chạy NGAY
Supplier<String> lambda = () -> select().toUpperCase(); // select() chạy khi get()
~~~

Đây là đoạn minh họa phụ thuộc phương thức `select()` và `Supplier` được định nghĩa trước đó, không phải chương trình chạy độc lập. Nếu `select()` có thể trả đối tượng khác ở các thời điểm, hai biến có thể có kết quả khác.

Trong chương trình đầy đủ ở phần 8:

- Ban đầu `active = "alpha"`. Tạo `fixedReceiver = select()::toUpperCase` gọi `select()` ngay và capture chuỗi `"alpha"`.
- Tạo `reevaluate = () -> select().toUpperCase()` không gọi `select()`.
- Đổi `active = "beta"`, rồi gọi `fixedReceiver.get()`: kết quả `"ALPHA"`.
- Gọi `reevaluate.get()`: `select()` chạy lúc này, nên kết quả `"BETA"`.

**Capture receiver không đồng nghĩa đóng băng trạng thái của receiver.** Nếu đó là một đối tượng có thể thay đổi, method reference giữ **tham chiếu tới cùng object**, và các thay đổi nội bộ sau đó vẫn được quan sát khi phương thức được gọi. Trường hợp string ở trên dễ quan sát vì `String` bất biến và biến `active` được trỏ tới chuỗi khác.

### Null receiver: hai thời điểm khác nhau

~~~java
String missing = null;

// Nếu thực sự thực thi dòng sau, NPE xảy ra NGAY tại đây:
Supplier<String> invalid = missing::trim;

// Chỉ tạo lambda thì chưa ném lỗi:
Supplier<String> delayed = () -> missing.trim();
// NPE chỉ xuất hiện khi gọi delayed.get().
~~~

Đây là **minh họa về thời điểm lỗi**, không đặt hai biến vào đường chạy bình thường nếu muốn chương trình không ném exception. Với kiểu `Type::instanceMethod` không capture receiver cụ thể, ví dụ `Function<String,String> trim = String::trim;`, lỗi vì đối số nhận vào `null` sẽ xuất hiện khi gọi `trim.apply(null)`.

Điểm thực hành: khi chuyển `() -> obtainService().run()` thành `obtainService()::run`, hãy kiểm tra xem `obtainService()` có side effect, lựa chọn service động, null hoặc throw exception không; **không mặc định hai biểu thức hoàn toàn thay thế được nhau**.

## 6. Method reference không phải phép chuyển đổi lambda bằng tìm-và-thay

### 6.1. Hành vi lambda có thể gồm nhiều bước

~~~java
Function<String, String> safeTrim = value ->
    value == null ? "" : value.trim();
~~~

`String::trim` không thay thế trực tiếp cho hành vi **null thành chuỗi rỗng**. Nếu tạo utility `static String safeTrim(String)` riêng, `Utils::safeTrim` có thể gọn, nhưng lúc đó logic nằm ở utility, không biến mất.

### 6.2. Lambda có thể sắp xếp lại/thêm đối số

~~~java
BiFunction<String, String, String> join =
    (left, right) -> right.concat(left);
~~~

Không thể thay nguyên nghĩa bằng `String::concat` vì dạng unbound mặc định ánh xạ đối số đầu thành receiver `left` và kết quả là `left.concat(right)`. Nếu muốn đảo thứ tự đối số hoặc gán một hằng số vào giữa, giữ lambda hoặc tạo helper rõ nghĩa.

### 6.3. Không phải reference nào cũng có một lambda cùng hình thức

JLS `15.13.2` chỉ rõ method reference có thể tương thích với một số **generic function types** mà cú pháp lambda không trực tiếp diễn tả được, do lambda không được tự khai báo type parameters ở mức phương thức trừu tượng. Đây là trường hợp nâng cao, nhưng là lý do quan trọng để không đồng nhất khái niệm method reference với “lambda chỉ được viết tắt”.

~~~java
interface ListFactory {
    <T> List<T> make();
}

ListFactory factory = ArrayList::new;
List<String> words = factory.make();
List<Integer> numbers = factory.make();
~~~

Đây là đoạn **minh họa đặt trong lớp/phương thức thích hợp**: `ListFactory` được khai báo ở phạm vi kiểu, các biến trong phương thức, import `java.util.*`. Compiler chấp nhận constructor reference `ArrayList::new` cho method generic của interface; ta không thể viết cú pháp lambda kiểu `<T>() -> new ArrayList<T>()` vì Java không hỗ trợ khai báo tham số kiểu của SAM ngay ở đầu lambda. Trong khi viết API, ưu tiên thiết kế target type rõ ràng; kiến thức ngoại lệ này chủ yếu giúp hiểu đặc tả.

### 6.4. Đừng suy luận bằng việc compiler chọn overload “có vẻ hợp lý”

Khi tham chiếu đến một tên phương thức có nhiều overload, compiler dựa trên **số/kiểu đối số của functional interface**, cách target type được suy ra, khả năng áp dụng và quy tắc chọn phương thức cụ thể nhất. Method reference có thể là *exact* hoặc *inexact* theo JLS; với một số lời gọi overload chứa lambda hoặc inexact method reference, thông tin kiểu chỉ trở nên rõ sau khi biết target type.

~~~java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> parsePrimitive = Integer::parseInt;
~~~

Cả hai hợp lệ; chúng có hợp đồng khác nhau (`Integer` và `int`). Khi gọi `parse.apply("10")` kết quả boxed; `parsePrimitive.applyAsInt("10")` trả primitive. Không nên đọc `Integer::parseInt` rồi kết luận nó có một kiểu Java duy nhất, độc lập với ngữ cảnh.

Nếu một lời gọi overload khó hiểu hoặc báo `reference to ... is ambiguous`, hãy:
1. Xác định chữ ký từng overload và target functional interface.
2. Khai báo biến có type tường minh trước khi truyền, hoặc ép kiểu functional interface nếu thực sự cần.
3. Dùng lambda có tham số và thân rõ ràng khi cần chọn overload/chuyển đổi tham số.
4. Cân nhắc đổi thiết kế API nếu nhiều overload nhận functional interface rất dễ gây nhầm.

## 7. Return type `void`, method reference và kiểu kết quả

Target trả `void` có thể nhận tham chiếu đến một method **có giá trị trả về** nếu phần gọi tương thích về tham số; kết quả sẽ bị bỏ. Đây cũng là điều xảy ra với lambda expression body là một **method invocation**.

~~~java
List<String> names = new ArrayList<>();
Consumer<String> add1 = names::add;        // List.add trả boolean
Consumer<String> add2 = s -> names.add(s); // lambda cũng bỏ boolean
Function<String, Boolean> testAdd = names::add; // Function giữ boolean
~~~

Đây là đoạn minh họa trong phương thức; hai dạng Consumer chỉ thích hợp khi mục tiêu là **thực hiện hành động thêm phần tử**, không quan tâm boolean `add` trả về. `Function<String,Boolean>` là lựa chọn khác khi cần kết quả, nhưng hãy chú ý gọi các biến này sẽ thêm phần tử thật, không chỉ kiểm tra giả lập.

Ngược lại, target cần kết quả không thể được đáp ứng bởi một method trả `void`:

~~~java
// SAI – println trả void, Function cần String:
Function<String, String> broken = System.out::println;

// ĐÚNG – có side effect, không trả dữ liệu:
Consumer<String> print = System.out::println;
~~~

Sự tương thích còn đòi hỏi **return type phải gán được** với kiểu trả về của SAM (bao gồm boxing/unboxing khi phù hợp). Ví dụ `Predicate<String> p = String::isEmpty;` trả primitive `boolean` phù hợp; nhưng `Function<String,String> f = String::length;` không hợp lệ, vì `int` không chuyển thành `String`.

## 8. Chương trình độc lập: các dạng tham chiếu, lambda và capture receiver

Ví dụ sau kiểm chứng trên **JDK 17** và minh họa static, unbound instance, bound instance, constructor, array constructor, callback void, giới hạn của method reference và thời điểm receiver expression được đánh giá.

Lưu thành **MethodRefLambdaDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;

public class MethodRefLambdaDemo {
    private static String active = "alpha";

    private static String select() {
        System.out.println("select=" + active);
        return active;
    }

    private static String normalize(String text) {
        return text.trim().toUpperCase(Locale.ROOT);
    }

    private static final class Code {
        private final String value;

        private Code(String value) { this.value = value; }

        @Override public String toString() {
            return "Code(" + value + ")";
        }
    }

    public static void main(String[] args) {
        List<String> raw = Arrays.asList(" an ", " Binh ");
        Function<String, String> asLambda = s -> normalize(s);
        Function<String, String> asReference = MethodRefLambdaDemo::normalize;
        System.out.println("lambda=" + raw.stream().map(asLambda).toList());
        System.out.println("reference=" + raw.stream().map(asReference).toList());

        Function<String, String> trim = String::trim;
        BiFunction<String, String, Boolean> startsWith = String::startsWith;
        System.out.println("unbound=" + trim.apply(" x ") + "," + startsWith.apply("lambda", "lam"));

        String prefix = "ID:";
        Function<String, String> addPrefix = prefix::concat;
        System.out.println("bound=" + addPrefix.apply("A"));

        Supplier<ArrayList<String>> createList = ArrayList::new;
        ArrayList<String> names = createList.get();
        Consumer<String> add = names::add; // add trả boolean; Consumer bỏ kết quả
        add.accept("Lan");
        Function<Integer, String[]> createArray = String[]::new;
        Function<String, Code> createCode = Code::new;
        System.out.println("constructors=" + names + ",length=" + createArray.apply(3).length);
        System.out.println("object=" + createCode.apply("A"));

        Supplier<String> fixedReceiver = select()::toUpperCase;
        Supplier<String> reevaluate = () -> select().toUpperCase();
        active = "beta";
        System.out.println("fixed=" + fixedReceiver.get());
        System.out.println("dynamic=" + reevaluate.get());

        Predicate<String> nonBlank = s -> s != null && !s.isBlank();
        System.out.println("lambdaOnly=" + nonBlank.test("A"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 MethodRefLambdaDemo.java
java MethodRefLambdaDemo
~~~

Stdout **đã biên dịch và xác minh thực tế**:

~~~text
lambda=[AN, BINH]
reference=[AN, BINH]
unbound=x,true
bound=ID:A
constructors=[Lan],length=3
object=Code(A)
select=alpha
fixed=ALPHA
select=beta
dynamic=BETA
lambdaOnly=true
~~~

### Giải thích

1. Hai `Function<String,String>` đầu cùng gọi `normalize` trên mỗi phần tử. `Stream.toList()` có từ **Java 16**; nó giữ dữ liệu đã biến đổi thành danh sách không sửa được. `Locale.ROOT` tránh phụ thuộc locale mặc định khi viết hoa.
2. `String::trim` lấy đối số `" x "` làm receiver, trả `"x"`. `String::startsWith` dùng đối số `"lambda"` làm receiver và `"lam"` làm tham số; kết quả `true`.
3. `prefix::concat` cố định receiver `"ID:"` khi tạo tham chiếu, nên `apply("A")` cho `"ID:A"`.
4. `ArrayList::new`, `String[]::new` và `Code::new` là constructor/array constructor references. `Supplier.get` và `Function.apply` tạo instance ở lúc gọi; `createArray.apply(3)` tạo array dài 3.
5. `names::add` là bound method reference tới danh sách đã tạo; `Consumer<String>` gọi `List.add` nhưng bỏ giá trị boolean. Bản thân danh sách thay đổi thành `[Lan]`.
6. Khi tạo `fixedReceiver`, receiver expression `select()` chạy **ngay lập tức** và in `select=alpha`. `reevaluate` chỉ là lambda, nên chưa in gì.
7. Sau khi đổi `active`, `fixedReceiver.get()` gọi phương thức trên receiver chuỗi `"alpha"` đã capture, còn `reevaluate.get()` chạy lại `select()` tại thời điểm gọi và nhận `"beta"`.
8. Cuối cùng, `nonBlank` là một lambda có điều kiện và kiểm tra null. Ở đây lambda diễn đạt logic kết hợp rõ hơn một method reference đơn lẻ. `String.isBlank()` có từ **Java 11**, phù hợp JDK 17+.

Ví dụ trên dùng các API và cơ chế vẫn được hỗ trợ; các dòng cố ý không biên dịch nằm ở những phần giải thích riêng, không được đưa vào tệp thực thi.

## 9. Stream, Comparator và Optional: khi nào nên dùng dạng nào?

Trong code nghiệp vụ, method reference giúp pipeline ngắn gọn khi gọi **đúng method hiện có**:

~~~java
List<String> names = List.of(" Lan ", " An ", " ");
List<String> cleaned = names.stream()
    .map(String::strip)         // String.strip: Java 11+
    .filter(Predicate.not(String::isBlank)) // Predicate.not: Java 11+
    .sorted(String::compareToIgnoreCase)
    .toList();                  // Java 16+
~~~

Đây là đoạn minh họa trong phương thức, cần import `java.util.*`, `java.util.function.*`. Kết quả là `["An", "Lan"]`, vì strip bỏ khoảng trắng, filter bỏ chuỗi rỗng, sorted sắp theo alphabet không phân biệt hoa/thường. Không nên viết `forEach(String::strip)` để mong “cập nhật chuỗi”: `String` bất biến; nếu kết quả bị bỏ thì không có danh sách được chuẩn hóa.

Đôi khi lambda khiến ý nghĩa rõ hơn:

~~~java
List<String> cleaned = names.stream()
    .map(s -> s.strip())
    .filter(s -> !s.isBlank())
    .sorted((a, b) -> a.compareToIgnoreCase(b))
    .toList();
~~~

Hai cách trong ngữ cảnh này giống về **kết quả dữ liệu**, nhưng không mặc nhiên cam kết đối tượng callback có cùng identity, cùng biểu diễn runtime hoặc cùng chi tiết triển khai.

Tương tự với `Optional`:

~~~java
Optional<String> maybe = Optional.of(" ok ");
String value = maybe.map(String::trim).orElse("missing");
maybe.ifPresent(System.out::println);
~~~

`map` nhận `Function` để biến đổi và giữ kết quả `String`; `ifPresent` nhận `Consumer` để thực thi side effect và không trả giá trị. Nếu cần xử lý giá trị `null` hoặc nhiều nhánh logic, lambda thường phù hợp hơn một method reference đơn giản.

**Một tiêu chí đáng tin:** chọn hình thức nào giúp người đọc nhận ra nguồn dữ liệu, biến đổi, side effect và thứ tự thực thi dễ nhất. “Ít ký tự hơn” không phải luôn là “tốt hơn”.

## 10. Checked exceptions và khả năng tương thích chữ ký

Method reference không giúp bỏ qua kiểm tra checked exception. Nếu phương thức được tham chiếu khai báo ném checked exception, chữ ký SAM target phải cho phép nó (hoặc cần viết adapter xử lý lỗi).

Ví dụ giả lập:

~~~java
static String load(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Với `Function<Path,String>`, `apply` không khai báo checked exception. Do đó trong một lớp chứa `load`:

~~~java
// SAI – Function.apply không khai báo IOException:
Function<java.nio.file.Path, String> broken = MyClass::load;
~~~

Nếu cần chuẩn hóa lỗi ở ranh giới, lambda có thể bắt lỗi và biến thành unchecked exception có ý nghĩa:

~~~java
Function<java.nio.file.Path, String> safe = path -> {
    try {
        return load(path);
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
~~~

Đây là **các đoạn minh họa không độc lập**: `MyClass` tượng trưng cho lớp thực sự chứa `load`; đoạn `safe` cũng phải được đặt trong lớp nhìn thấy `load`. `Files.readString` từ Java 11. Đừng tự chuyển mọi checked exception sang unchecked chỉ để dùng method reference hay lambda: lựa chọn theo hợp đồng API, xử lý retry/lỗi nghiệp vụ, hoặc định nghĩa functional interface có `throws` khi cần.

Khác với method reference trỏ thẳng vào method ném lỗi, lambda cung cấp không gian để **bắt ngoại lệ, ghi log có ngữ cảnh, chuyển dạng lỗi, fallback và thực hiện nhiều bước**. Nhưng lambda cũng không miễn trừ quy tắc checked exception; phải xử lý hợp lệ.

## 11. Một số khác biệt cần chú ý ngoài cú pháp

### 11.1. Capture và *effectively final*

Cả hai có thể dùng đối tượng từ phạm vi ngoài, nhưng lambda được phép capture biến local chỉ nếu biến đó **final hoặc effectively final**. Bound method reference dùng receiver expression được đánh giá lúc tạo; vẫn phải tuân thủ quy tắc Java về truy cập/biến local và target type.

~~~java
String prefix = "id:";
Function<String, String> a = value -> prefix.concat(value);
Function<String, String> b = prefix::concat;
~~~

Khi `prefix` là biến local được capture, không được gán lại biến này rồi vẫn mong cả lambda và method reference ở trên biên dịch. Nếu cần thay đổi receiver theo thời gian, có thể tham chiếu một field hoặc hàm truy xuất receiver **và chủ động kiểm tra thời điểm đánh giá**, như ví dụ `select()`.

### 11.2. Không có cam kết identity tương đương

Cả lambda và method reference đều tạo đối tượng thực thi functional interface với chi tiết implementation do JVM/compiler quyết định. Không nên dùng `==`, `System.identityHashCode` hay tên lớp runtime của callback để quyết định tính đúng đắn của nghiệp vụ. **Tương đương về kết quả không đồng nghĩa là cùng một đối tượng hoặc cùng identity**.

### 11.3. Không thể nhận xét hiệu năng chỉ từ cách viết

Method reference không tự động nhanh hơn lambda. Với code tương đương, JVM có thể dùng các cơ chế chuyển đổi/biên dịch tối ưu hóa, và chi phí quan sát được phụ thuộc đường gọi thực tế. Ưu tiên độ rõ ràng, dữ liệu cần thiết, allocation/boxing và hiệu năng đo được bằng benchmark phù hợp nếu đó là điểm nghẽn.

### 11.4. Overload, generic và boxing

Method reference được liên kết với target type: `ToIntFunction<String> f = Integer::parseInt;` trả `int`, còn `Function<String,Integer> g = Integer::parseInt;` cho `Integer` sau boxing. Nếu overload hoặc generic làm compiler khó suy diễn, **khai báo target type rõ ràng** hoặc viết lambda có tham số tường minh khi cần thiết. Đừng tự chọn overload dựa vào tên phương thức mà không xem SAM signature.

### 11.5. Tác dụng phụ của bound reference có thể bị bỏ qua khi refactor

Nếu đoạn code `() -> serviceProvider.get().send()` được thay bằng `serviceProvider.get()::send`, lời gọi `get()` đổi từ *mỗi invocation* sang *ngay lúc tạo reference*. Điều này có thể đổi service thực hiện hành động, thời điểm xảy ra exception, số lần truy xuất, tính chất cache hoặc kết quả khi cấu hình chạy thay đổi. Đặc biệt cẩn thận trong dependency injection, đa tenant và callback có vòng đời dài.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao không đúng | Giải pháp |
| --- | --- | --- |
| `var trim = String::trim;` | Không có target functional-interface type | Khai báo `Function<String,String>` hoặc truyền vào API có target |
| Xem `String::trim` là static method | Đây là unbound instance method | Đối số SAM đầu trở thành receiver |
| Xem `prefix::concat` giống hệt mọi `() -> obtainPrefix().concat(...)` | Receiver expression trong bound reference được đánh giá sớm | Phân tích thời điểm capture, dùng lambda nếu cần chọn lại receiver |
| Đổi mọi lambda thành method reference | Lambda có thể có nhiều bước/đảo đối số/kiểm tra null | Chỉ đổi khi giữ đúng hành vi và rõ hơn |
| `Supplier<String> s = String::trim;` | Unbound instance method cần receiver từ SAM, Supplier không có đối số | Dùng `Function<String,String>`, hoặc bound `"abc"::trim` với Supplier |
| Mong `Consumer<String> c = list::add;` trả boolean | Consumer trả void, boolean bị bỏ | Dùng `Function<String,Boolean>` nếu cần giá trị |
| `Function<String,String> f = System.out::println;` | `println` trả void, không cung cấp String | Dùng `Consumer<String>` hoặc lambda có return String thật |
| `Function<String,String> f = String::length;` | `length` trả int, không chuyển thành String | Chọn `ToIntFunction<String>` hoặc `Function<String,Integer>` |
| Tham chiếu checked-exception method vào `Function` | `Function.apply` không khai báo checked throws | Bắt lỗi trong lambda adapter hoặc đổi interface |
| Dùng `String::strip` trong dự án khóa ở Java 8 | `strip` được thêm vào Java 11 | Kiểm tra JDK target, dùng API được hỗ trợ phù hợp |
| Dùng `Stream.toList()` trong JDK 8 | `toList()` là API của Java 16+ | Với Java 8: `collect(Collectors.toList())`; trong code mới, dùng `toList()` nếu cần list không sửa được |
| Mong `Class::method` tránh được lỗi overload | Target type vẫn chi phối chọn method | Khai báo target tường minh, kiểm tra overload |
| So sánh callbacks bằng `==` để suy ra hai cách viết “giống nhau” | JLS không cam kết identity của lambda/reference | So sánh **hành vi**, không dựa identity |
| Cho rằng reference tạo từ object biến đổi state sẽ snapshot toàn bộ object | Bound reference giữ receiver, không đóng băng fields | Phân biệt receiver identity với mutable state |

## 13. Câu hỏi luyện tập và bài tập tự thực hành

1. Viết một cặp `Function<String,String>`: bản lambda `s -> s.trim()` và bản method reference. Giải thích SAM target và đối số làm receiver trong mỗi trường hợp.
2. So sánh `Integer::parseInt` và `s -> Integer.parseInt(s)` khi gán cho `ToIntFunction<String>`. Kết quả nhận được là primitive hay wrapper?
3. Với `String::startsWith`, giải thích vì sao `BiFunction<String,String,Boolean>` là target phù hợp. Đối số thứ nhất và thứ hai đi vào vị trí nào?
4. Viết method reference constructor tạo `StringBuilder` từ `String` và tạo `String[]` từ kích thước `int`. So sánh với lambda dùng `new`.
5. Vì sao `Supplier<String> s = " abc "::trim;` hợp lệ nhưng `Supplier<String> s = String::trim;` không khớp?
6. Dự đoán thời điểm gọi `getService()` trong `getService()::run` và `() -> getService().run()`. Điều gì thay đổi nếu `getService()` trả null?
7. Nếu `List.add` trả boolean, vì sao `Consumer<String> c = list::add;` vẫn biên dịch? Khi nào cách này là lỗi logic?
8. Viết lambda kiểm tra null rồi `strip` và uppercase với `Locale.ROOT`. Giải thích vì sao `String::strip` một mình không biểu diễn toàn bộ yêu cầu.
9. Trong Stream, thay `map(s -> s.trim())` bằng `map(String::trim)`. Khi nào việc thay sẽ không làm đổi kết quả và khi nào nên giữ lambda để diễn đạt logic khác?
10. Với một API overload nhận hai functional interfaces khác nhau, giải thích vai trò của target typing và cách khai báo biến trung gian để tránh ambiguous overload.
11. Vì sao `Function<Path,String> f = MyClass::load;` có thể lỗi nếu `load` khai báo `throws IOException`? Đưa ra cách viết lambda xử lý lỗi có ngữ cảnh.
12. Có nên so sánh hai function được tạo từ `String::trim` và `s -> s.trim()` bằng `==` để kết luận chúng tương đương? Vì sao không?

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification, `15.13 – Method Reference Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.13)
- [Java Language Specification, `15.13.3 – Run-Time Evaluation of Method References](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.13.3)
- [Java Language Specification, `15.27 – Lambda Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.27)
- [Java Language Specification, `9.8 – Functional Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.8)
- [Java SE 17 – `java.util.function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)

**Ghi nhớ:** Method reference thường là **cách diễn đạt gọn cho một lambda chuyển thẳng lời gọi**, nhưng cả hai đều phải phù hợp **functional interface đích**. Khi refactor, hãy kiểm tra receiver là **bound hay unbound**, đối số được ánh xạ như thế nào, return/throws có phù hợp không, và thời điểm đánh giá receiver có bị thay đổi không. Chọn method reference khi nó nói rõ ý định; giữ lambda khi cần logic hoặc kiểm soát hành vi tường minh.
