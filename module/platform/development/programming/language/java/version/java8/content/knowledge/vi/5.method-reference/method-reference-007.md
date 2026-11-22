# Ánh xạ tham số, kiểu trả về và phương thức generic trong Java Method Reference

## Mục tiêu học tập

**Method reference** (tham chiếu phương thức) là cú pháp dùng dấu **::** để chỉ một phương thức hoặc constructor đã tồn tại, khi hành vi của nó phù hợp với một **functional interface**. Một method reference không tự có kiểu hàm độc lập: kiểu đích (target type) giúp Java biết **có bao nhiêu tham số, chúng mang kiểu gì, kết quả cần kiểu gì**, và cách suy luận phương thức generic hoặc chọn một overload.

Sau bài học, bạn có thể:

- Ánh xạ tham số của phương thức trừu tượng duy nhất (SAM) sang phương thức static, phương thức instance có receiver cố định, phương thức instance có receiver là đối số, và constructor.
- Phân biệt **receiver** với các tham số khai báo trong phương thức đích.
- Hiểu điều kiện tương thích kiểu kết quả, gồm boxing/unboxing, widening và mục tiêu trả **void**.
- Dùng method reference đến **phương thức generic** bằng suy luận kiểu từ functional interface; biết khi nào cần type witness tường minh.
- Nhận diện overload, lỗi thiếu kiểu đích, lỗi checked exception và rủi ro tham chiếu đến đối tượng mutable.
- Viết mã rõ nghĩa với **Function**, **BiFunction**, **Supplier**, **Consumer**, **Comparator**, Stream và các giao diện hàm tự định nghĩa.

Những quy tắc sau có từ Java 8 và vẫn là kiến thức thiết yếu trong Java hiện đại. Ví dụ độc lập dùng API Java 8, có thể biên dịch với JDK 8 hoặc mới hơn, trong đó có JDK 17+.

## 1. Bắt đầu bằng functional interface, không bắt đầu bằng dấu ::

Ví dụ quen thuộc:

~~~java
java.util.function.Function<String, Integer> length = String::length;
~~~

Phần **String::length** chưa nói hết mọi thứ nếu đứng riêng lẻ. Nhưng vế trái **Function<String,Integer>** có phương thức trừu tượng **Integer apply(String value)**. Java dùng kiểu đích để kiểm tra tham chiếu phương thức này.

Có thể đọc theo bốn bước:

1. **Nhìn kiểu đích:** Function<String,Integer>.
2. **Tìm SAM:** apply nhận một String, trả một Integer.
3. **Tìm phương thức được tham chiếu:** String.length() không khai báo đối số và trả int.
4. **Ánh xạ:** đối số String của apply được dùng làm **receiver** để gọi length(); kết quả int được boxing thành Integer.

Dạng lambda tương đương về ý nghĩa:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Cả hai chỉ mô tả hành vi; chỉ khi gọi **length.apply("Java")** thì kết quả **4** mới được tính. Method reference không tự thực thi ngay, không tự tạo luồng và cũng không mặc nhiên cache kết quả.

**SAM** là *single abstract method*. Một functional interface có đúng một phương thức trừu tượng cần triển khai, dù có thể thêm phương thức default hoặc static. Method reference, giống lambda, cần tương thích với chữ ký SAM và không thể gán trực tiếp cho một kiểu tùy ý như Object nếu chưa có ngữ cảnh functional interface.

## 2. Bốn dạng method reference cần nhận diện

| Dạng | Ví dụ | Cách ánh xạ |
| --- | --- | --- |
| **Lớp::phươngThứcStatic** | Integer::parseInt | Đối số SAM được chuyển thành đối số của phương thức static |
| **đốiTượng::phươngThứcInstance** | System.out::println | Receiver đã được gắn sẵn; các đối số SAM đi vào tham số của phương thức |
| **Lớp::phươngThứcInstance** | String::length | Đối số SAM đầu tiên thường là receiver; các đối số tiếp theo đi vào tham số phương thức |
| **Lớp::new** | ArrayList::new | Đối số SAM đi vào constructor được chọn; kết quả là đối tượng mới |

Với cú pháp **Lớp::phươngThứcInstance**, người học thường nhầm vì danh sách đối số của functional interface có thể **nhiều hơn một** so với danh sách tham số khai báo của phương thức Java: đối số bổ sung chính là receiver.

Cùng một tên phương thức có nhiều overload vẫn có thể dùng với các functional interface khác nhau. Việc chọn overload diễn ra theo các quy tắc độ phù hợp của lời gọi Java, có xét kiểu đích và các lựa chọn khả dụng; không phải cứ gặp dấu **::** thì compiler tùy ý lấy một phương thức.

## 3. Ánh xạ tham số: phương thức static

Một phương thức static không cần receiver để được gọi. Đối số từ SAM khớp trực tiếp với tham số của phương thức static được chọn.

Ví dụ:

~~~java
java.util.function.ToIntFunction<String> parse = Integer::parseInt;
int number = parse.applyAsInt("42"); // 42
~~~

Đây là **đoạn minh họa**, cần đặt trong phương thức hoặc lớp thích hợp. **ToIntFunction<String>** có SAM **int applyAsInt(String value)**; **Integer.parseInt(String)** nhận String và trả int, nên ánh xạ trực tiếp.

Tương đương:

~~~java
java.util.function.ToIntFunction<String> parse =
    text -> Integer.parseInt(text);
~~~

Một phương thức static có thể có nhiều đối số:

~~~java
java.util.function.IntBinaryOperator max = Math::max;
int result = max.applyAsInt(7, 4); // 7
~~~

**IntBinaryOperator** mô tả **int applyAsInt(int left, int right)**. Math có nhiều overload max, và ngữ cảnh int/int/int dẫn tới **Math.max(int,int)**. Không nên ghi rằng method reference tự động chọn overload bằng tên; nó cần **hợp đồng kiểu của SAM**.

### Kiểu kết quả có thể chuyển đổi

Khi SAM trả về **Integer** nhưng phương thức đích trả **int**, Java có thể boxing khi hợp lệ:

~~~java
java.util.function.Function<String, Integer> parse =
    Integer::parseInt;
~~~

Khi SAM trả **long**, phương thức trả **int** có thể được mở rộng thành long:

~~~java
java.util.function.ToLongFunction<String> asLong = String::length;
~~~

Điều kiện tương thích không có nghĩa mọi phép đổi số đều hợp lệ. Chẳng hạn việc gán phương thức trả **double** cho SAM trả **int** không được tự động thu hẹp theo ý muốn của người viết. Với số liệu cần chính xác, phải xét riêng nguy cơ tràn số và mất chính xác.

## 4. Receiver được cố định: đốiTượng::phươngThứcInstance

Với cú pháp **mộtĐốiTượng::method**, đối tượng ở bên trái **::** đã là receiver. Các đối số do SAM cung cấp sẽ khớp với tham số của phương thức instance.

~~~java
java.io.PrintStream output = System.out;
java.util.function.Consumer<String> printer = output::println;
printer.accept("Xin chào");
~~~

Đây là đoạn minh họa trong ngữ cảnh Java hợp lệ, in dòng **Xin chào**. **Consumer<String>.accept(String)** nhận một tham số và trả void; phương thức **println(String)** của PrintStream nhận một String và trả void. Receiver output không chiếm đối số SAM nào nữa vì đã được gắn sẵn.

Một ví dụ khác, receiver là chuỗi cố định:

~~~java
String prefix = "ID-";
java.util.function.Function<String, String> label = prefix::concat;
System.out.println(label.apply("07")); // ID-07
~~~

Ở đây chuỗi **prefix** là receiver cho **String.concat(String)**; đối số "07" truyền vào concat. Với lambda, ý tương đương là **value -> prefix.concat(value)**, miễn việc bắt giữ biến trong lambda hợp lệ.

### Receiver được đánh giá khi tạo tham chiếu

Khi phần bên trái **::** là một **biểu thức đối tượng**, biểu thức receiver được đánh giá khi method reference được tạo. Nếu receiver là null, việc tạo tham chiếu dạng này ném **NullPointerException**, không cần đợi gọi SAM.

~~~java
String text = null;
// java.util.function.Supplier<String> invalid = text::toString;
~~~

Dòng tạo tham chiếu được đặt trong comment để không gây lỗi lúc chạy. Cần phân biệt **text::toString** với **String::toString**: trường hợp thứ nhất receiver được cố định ngay, trường hợp thứ hai receiver được lấy từ đối số SAM khi gọi.

Một receiver mutable được gắn cố định không có nghĩa trạng thái đối tượng bị đóng băng. Nếu trạng thái thay đổi trước lần gọi get()/apply()/accept(), phương thức thường nhìn thấy trạng thái mới. Điều này sẽ được minh họa trong chương trình hoàn chỉnh.

## 5. Receiver là đối số: Lớp::phươngThứcInstance

Đây là dạng dễ nhầm nhất. Với **String::length**, String đứng ở bên trái là **kiểu** (reference type), chưa phải đối tượng cụ thể. SAM phải cung cấp một đối số kiểu String để làm receiver.

~~~java
java.util.function.ToIntFunction<String> size = String::length;
int n = size.applyAsInt("hello"); // 5
~~~

Ánh xạ chi tiết:

~~~text
SAM:                 int applyAsInt(String receiver)
Method reference:    String::length
Lời gọi tương đương: receiver.length()
~~~

Với phương thức instance vốn **đã có một tham số**, functional interface thường phải cung cấp **hai** đối số: receiver và tham số thực.

~~~java
java.util.function.BiFunction<String, Integer, String> suffix =
    String::substring;

String result = suffix.apply("Java", 2); // "va"
~~~

Phương thức instance **String.substring(int beginIndex)** có một tham số int. Nhưng **BiFunction<String,Integer,String>** có hai tham số: String receiver và Integer beginIndex (được unboxing phù hợp sang int). Tương đương:

~~~java
java.util.function.BiFunction<String, Integer, String> suffix =
    (text, beginIndex) -> text.substring(beginIndex);
~~~

Nếu phương thức instance có hai tham số thực, SAM có thể cần ba đối số. Java không cung cấp **TriFunction** chuẩn trong java.util.function, nhưng bạn có thể tự khai báo functional interface:

~~~java
@FunctionalInterface
interface TriFunction<A, B, C, R> {
    R apply(A first, B second, C third);
}
~~~

Đây là đoạn khai báo giao diện minh họa, cần nằm ở vị trí được phép khai báo kiểu trong Java. Khi có TriFunction:

~~~java
TriFunction<String, Integer, Integer, String> slice =
    String::substring;
String part = slice.apply("Java", 1, 3); // "av"
~~~

**String.substring(int beginIndex, int endIndex)** nhận hai int. SAM cần cung cấp một **String receiver** cộng hai **Integer** để unboxing thành int. Việc Java chọn overload substring(int,int) thay vì substring(int) dựa vào độ phù hợp với chữ ký SAM.

### Phân biệt với static method

Đối với **Integer::parseInt**, Integer là tên lớp chứa **static method**, nên không có đối số receiver. Với **String::substring**, String là kiểu chứa **instance method**, nên đối số đầu tiên từ SAM là receiver. Không đếm máy móc các dấu phẩy trong tên method reference: hãy kiểm tra phương thức thực sự được tham chiếu và nó có static hay không.

## 6. Ví dụ chạy được: ánh xạ receiver, tham số và kiểu trả về

Tạo tệp **MethodReferenceMappingDemo.java**:

~~~java
import java.util.Comparator;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class MethodReferenceMappingDemo {

    @FunctionalInterface
    interface TriFunction<A, B, C, R> {
        R apply(A first, B second, C third);
    }

    public static void main(String[] args) {
        ToIntFunction<String> length = String::length;
        BiFunction<String, Integer, String> suffix = String::substring;
        TriFunction<String, Integer, Integer, String> slice =
            String::substring;

        Function<String, String> upper = String::toUpperCase;

        String prefix = "Xin ";
        Function<String, String> greeting = prefix::concat;

        Comparator<String> alphabet = String::compareTo;

        System.out.println("Độ dài: " + length.applyAsInt("Java"));
        System.out.println("Phần đuôi: " + suffix.apply("Java", 2));
        System.out.println("Khoảng: " + slice.apply("Java", 1, 3));
        System.out.println("Chữ hoa: " + upper.apply("Java"));
        System.out.println("Ghép: " + greeting.apply("Java"));
        System.out.println("So sánh A/B: " +
            alphabet.compare("A", "B"));

        Consumer<String> line = System.out::println;
        line.accept("Đã in qua Consumer");
    }
}
~~~

Biên dịch và chạy (JDK 8+):

~~~bash
javac -encoding UTF-8 MethodReferenceMappingDemo.java
java MethodReferenceMappingDemo
~~~

Kết quả chính xác:

~~~text
Độ dài: 4
Phần đuôi: va
Khoảng: av
Chữ hoa: JAVA
Ghép: Xin Java
So sánh A/B: -1
Đã in qua Consumer
~~~

Giải thích:

1. **String::length** nhận String receiver từ ToIntFunction, trả int.
2. **String::substring** được dùng ở hai kiểu đích khác nhau: BiFunction chọn overload có một chỉ số; TriFunction chọn overload có hai chỉ số.
3. **String::toUpperCase** được ánh xạ sang Function<String,String>, trong đó đối số SAM là receiver cho phương thức không tham số.
4. **prefix::concat** cố định receiver "Xin ", nên SAM chỉ còn phải cung cấp một đối số String.
5. **String::compareTo** phù hợp Comparator<String> vì SAM **compare(String,String)** có hai tham số: receiver và đối tượng để so sánh.
6. **System.out::println** gắn sẵn receiver PrintStream và phù hợp Consumer<String> nhận một chuỗi, không trả kết quả.

Ví dụ dùng các chuỗi ASCII đơn giản để kết quả không phụ thuộc vào cách xử lý chữ hoa theo locale. Với dữ liệu ngôn ngữ thực tế, hãy kiểm tra yêu cầu locale khi chuyển đổi chữ hoa/chữ thường.

## 7. Kiểu trả về: quy tắc tương thích, không phải trùng chữ tuyệt đối

Method reference phải phù hợp với **kiểu trả về của SAM**, nhưng kiểu trả về của phương thức đích không phải lúc nào cũng giống hệt tên kiểu bên phía functional interface.

Một vài trường hợp:

| Kiểu trả về phương thức đích | Kiểu trả về SAM | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| int | int | ToIntFunction<String> = String::length | Khớp primitive |
| int | Integer | Function<String,Integer> = String::length | Boxing int thành Integer |
| int | long | ToLongFunction<String> = String::length | Mở rộng primitive |
| String | Object | Function<String,Object> = String::toUpperCase | Upcast tham chiếu |
| String | String | Function<String,String> = String::toUpperCase | Khớp tham chiếu |
| Kết quả phương thức bị bỏ qua | void | Consumer<String> = list::add | Phương thức có thể được gọi chỉ để tạo hiệu ứng |

Các trường hợp hợp lệ chịu quy tắc tương thích kết quả của Java; không phải mọi chuyển đổi tùy ý hoặc ép kiểu thu hẹp đều được cho phép. Khi kết quả có thể **null**, việc unboxing sang primitive có thể ném NullPointerException ở thời điểm thực thi; generic và target typing không tự loại bỏ null.

Một ví dụ đáng chú ý là **List.add(E)** trả boolean. Nhưng người viết có thể muốn dùng như một hành động qua Consumer<E>, có SAM trả void:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.function.Consumer<String> append = names::add;
append.accept("An"); // Trả về boolean từ add được bỏ qua.
~~~

Đoạn này minh họa trong phương thức. Việc một method reference có thể bỏ qua giá trị kết quả **không** khiến Consumer có kiểu trả về boolean; **Consumer.accept** vẫn là void. Không nên dùng cách này nếu giá trị boolean trả về có ý nghĩa nghiệp vụ cần được kiểm tra.

### Không khớp kiểu trả về là lỗi biên dịch

Ví dụ sau không hợp lệ:

~~~java
// java.util.function.ToIntFunction<String> x = String::toUpperCase;
~~~

**String.toUpperCase()** trả String; **ToIntFunction<String>** cần int. Java không tự chuyển String sang int chỉ vì được giao một kiểu đích trả số. Cần chỉ định phép biến đổi thích hợp, ví dụ **String::length** nếu muốn độ dài, hoặc **Integer::parseInt** nếu nội dung là chữ số hợp lệ.

### Kiểu trả về của phương thức có thể bị bỏ qua khi SAM là void

Trong một số trường hợp, target void cho phép bỏ qua kết quả của phương thức như List.add. Nhưng đừng suy rộng thành “mọi phép tính có giá trị đều gán được cho Runnable”: các quy tắc về dạng biểu thức và chữ ký SAM vẫn áp dụng. Hãy dùng method reference rõ ý định, thay vì cố ép ngữ cảnh void cho một phép tính mà kết quả thực sự quan trọng.

## 8. Generic method reference là gì?

Một phương thức generic có khai báo **tham số kiểu** ngay ở mức phương thức:

~~~java
public static <T> T identity(T value) {
    return value;
}
~~~

Đây là **khai báo phương thức minh họa**, cần đặt trong một lớp Java. T của phương thức chưa được xác định thành String, Integer hay một kiểu cụ thể khi nhìn vào tên **identity**. Khi dùng method reference, trình biên dịch có thể **suy luận T từ kiểu đích**.

Ví dụ nếu phương thức ở trong lớp GenericMethods:

~~~java
Function<String, String> textIdentity = GenericMethods::identity;
Function<Integer, Integer> intIdentity = GenericMethods::identity;
~~~

Hai dòng này chỉ minh họa; cần có lớp GenericMethods và import Function. Cả hai cùng tham chiếu một khai báo generic nhưng tạo chức năng khác nhau vì **Function<String,String>** và **Function<Integer,Integer>** đặt ra các ràng buộc kiểu khác nhau.

### Generic method và generic class khác nhau

- **Phương thức generic** khai báo biến kiểu riêng, ví dụ **static <T> T identity(T item)** hoặc **<U> U convert(...)**.
- **Lớp generic** khai báo biến kiểu ở lớp, ví dụ **Box<T>**; phương thức của Box có thể dùng T của lớp dù bản thân phương thức không khai báo tham số kiểu mới.
- Method reference có thể tham chiếu cả phương thức generic, phương thức của kiểu generic, hoặc constructor generic. Nên xác định tham số kiểu thuộc **lớp** hay **phương thức** để hiểu suy luận kiểu đang xảy ra ở đâu.

Đối với phương thức generic, compiler xét những ràng buộc từ **tham số SAM**, **kiểu trả về SAM**, **giới hạn của type variable (type bounds)** và ngữ cảnh overload. Phải có một phép ánh xạ hợp lệ; không phải mọi tổ hợp kiểu đều được ép buộc tự động cho khớp.

## 9. Suy luận generic từ kiểu đích

Lấy ví dụ API chuẩn Java 8:

~~~java
java.util.function.Supplier<java.util.List<String>> empty =
    java.util.Collections::emptyList;
~~~

**Collections.emptyList()** khai báo dạng generic **<T> List<T> emptyList()**. Supplier không có đối số và yêu cầu trả List<String>; compiler suy luận T là String theo kiểu đích.

Tương tự:

~~~java
java.util.function.Function<String, java.util.List<String>> single =
    java.util.Collections::singletonList;
~~~

**Collections.singletonList(T value)** trả List<T>. Với **Function<String,List<String>>**, tham số SAM là String và kết quả SAM là List<String>, nên T được suy luận phù hợp. Lời gọi **single.apply("A")** cho danh sách một phần tử "A".

Một cách viết rõ type witness khi cần:

~~~java
java.util.function.Supplier<java.util.List<String>> empty =
    java.util.Collections::<String>emptyList;
~~~

Dấu **<String>** sau **::** là **type arguments tường minh của phương thức generic**, không phải generic parameters của Supplier. Trong nhiều trường hợp compiler suy luận đủ nên dạng không có type witness dễ đọc hơn.

**Không đặt type argument vào sai vị trí:** trong biểu thức gọi phương thức trực tiếp, bạn có thể gặp **Collections.<String>emptyList()**; trong method reference, cú pháp tương ứng là **Collections::<String>emptyList**. Hai cách có cùng ý tưởng chỉ định T nhưng là hai cấu trúc cú pháp khác nhau.

### Type bounds có thể ngăn kiểu không hợp lệ

Giả sử phương thức được định nghĩa:

~~~java
public static <T extends Comparable<? super T>> T larger(
        T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
~~~

T phải đáp ứng ràng buộc Comparable phù hợp. Một kiểu không triển khai khả năng so sánh theo ràng buộc sẽ không dùng được với method reference này chỉ vì bạn khai báo BiFunction theo ý muốn. Compiler phải giải được các ràng buộc generic **và** tương thích chữ ký SAM.

## 10. Ví dụ Java hoàn chỉnh: phương thức generic và type inference

Tạo tệp **GenericMethodReferenceDemo.java**:

~~~java
import java.util.Collections;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

public class GenericMethodReferenceDemo {

    public static <T> T identity(T value) {
        return value;
    }

    public static <T> List<T> twice(T value) {
        return java.util.Arrays.asList(value, value);
    }

    public static <T extends Comparable<? super T>> T larger(
            T first, T second) {
        return first.compareTo(second) >= 0 ? first : second;
    }

    public static void main(String[] args) {
        Function<String, String> echoText =
            GenericMethodReferenceDemo::identity;

        Function<Integer, Integer> echoNumber =
            GenericMethodReferenceDemo::identity;

        Supplier<List<String>> emptyStrings =
            Collections::emptyList;

        Supplier<List<String>> explicitEmpty =
            Collections::<String>emptyList;

        Function<String, List<String>> singleton =
            Collections::singletonList;

        Function<String, List<String>> repeat =
            GenericMethodReferenceDemo::twice;

        BiFunction<Integer, Integer, Integer> max =
            GenericMethodReferenceDemo::larger;

        System.out.println("Text: " + echoText.apply("Java"));
        System.out.println("Number: " + echoNumber.apply(7));
        System.out.println("Empty: " + emptyStrings.get());
        System.out.println("Explicit: " + explicitEmpty.get());
        System.out.println("Singleton: " + singleton.apply("A"));
        System.out.println("Twice: " + repeat.apply("B"));
        System.out.println("Larger: " + max.apply(4, 9));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericMethodReferenceDemo.java
java GenericMethodReferenceDemo
~~~

Kết quả:

~~~text
Text: Java
Number: 7
Empty: []
Explicit: []
Singleton: [A]
Twice: [B, B]
Larger: 9
~~~

Cần chú ý:

1. Cùng phương thức generic **identity** có thể phục vụ Function<String,String> và Function<Integer,Integer>; kiểu T được suy luận theo từng kiểu đích.
2. **Collections::emptyList** và **Collections::<String>emptyList** đều phù hợp Supplier<List<String>>.
3. **Collections::singletonList** nhận một giá trị String từ Function rồi trả List<String>.
4. **twice** là phương thức generic do chương trình khai báo; method reference không tự gọi nó cho đến lúc Function.apply được thực thi.
5. **larger** có **type bound** và phải nhận các đối tượng có thể so sánh theo ràng buộc; Integer đáp ứng điều kiện đó.
6. Method reference không làm mất kiểm tra kiểu generic. Nếu kiểu tham số và kiểu kết quả không thỏa ràng buộc, chương trình sẽ không biên dịch.

**Lưu ý về generic và primitive:** type parameter của Function/Collections là kiểu tham chiếu, không thể khai báo Function<int,int>. Khi cần API primitive chuyên biệt, hãy dùng **IntUnaryOperator**, **ToIntFunction<T>**, v.v. Boxing/unboxing có thể xuất hiện khi method reference liên kết primitive với wrapper ở vị trí tương thích.

## 11. Constructor reference cũng ánh xạ tham số và kiểu kết quả

Method reference có thể trỏ tới constructor qua **Type::new**:

~~~java
java.util.function.Supplier<java.util.ArrayList<String>> create =
    java.util.ArrayList::new;
~~~

Constructor không đối số phù hợp **Supplier<ArrayList<String>>**: không nhận tham số SAM, trả một ArrayList<String> mới.

Với constructor cần hai tham số, ví dụ một lớp User có constructor **User(String name, int level)**, kiểu đích có thể là:

~~~java
BiFunction<String, Integer, User> factory = User::new;
~~~

Đây là **đoạn minh họa**, cần có lớp User với constructor phù hợp. BiFunction cung cấp String và Integer; giá trị Integer được unboxing thành int khi ánh xạ tới constructor; kết quả là User.

Một ví dụ khác: **IntFunction<String[]> builder = String[]::new** tương đương **size -> new String[size]**, hữu ích trong các API tạo mảng như **toArray(String[]::new)**. **String[]::new** là tham chiếu tới bộ tạo mảng, nhận kích thước int và trả mảng String[].

**Constructor reference không tự tạo đối tượng ngay lúc khai báo**. Đối tượng mới được xây khi gọi phương thức SAM, chẳng hạn **factory.apply("An", 3)**. Nếu constructor có overload, compiler chọn constructor phù hợp kiểu đích như với các method reference khác.

## 12. Ví dụ hoàn chỉnh: constructor, overload và receiver mutable

Tạo tệp **ConstructorAndOverloadDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.DoubleBinaryOperator;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.Supplier;

public class ConstructorAndOverloadDemo {

    static final class Member {
        private final String name;
        private final int level;

        Member(String name, int level) {
            this.name = name;
            this.level = level;
        }

        String label() {
            return name + ":" + level;
        }
    }

    public static void main(String[] args) {
        BiFunction<String, Integer, Member> factory = Member::new;
        Function<Member, String> label = Member::label;

        Member member = factory.apply("An", 3);
        System.out.println("Thành viên: " + label.apply(member));

        List<String> names = new ArrayList<>();
        Consumer<String> add = names::add;
        add.accept("A");
        add.accept("B");
        System.out.println("Danh sách: " + names);

        IntBinaryOperator maxInt = Math::max;
        DoubleBinaryOperator maxDouble = Math::max;

        System.out.println("Max int: " + maxInt.applyAsInt(3, 7));
        System.out.println("Max double: " +
            maxDouble.applyAsDouble(2.5, 1.5));

        StringBuilder builder = new StringBuilder("A");
        Supplier<String> current = builder::toString;
        builder.append("B");
        System.out.println("Receiver hiện tại: " + current.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConstructorAndOverloadDemo.java
java ConstructorAndOverloadDemo
~~~

Kết quả:

~~~text
Thành viên: An:3
Danh sách: [A, B]
Max int: 7
Max double: 2.5
Receiver hiện tại: AB
~~~

Diễn giải:

- **Member::new** chọn constructor cần String và int, dựa vào SAM của BiFunction<String,Integer,Member>.
- **Member::label** là tham chiếu instance chưa gắn receiver: Member được truyền vào Function.apply là receiver, label() trả String.
- **names::add** là tham chiếu instance **đã gắn receiver** vào một ArrayList cụ thể. SAM Consumer.accept trả void; kết quả boolean từ add được bỏ qua.
- **Math::max** có overload int và double; các giao diện IntBinaryOperator/DoubleBinaryOperator chỉ rõ overload phù hợp.
- **builder::toString** gắn receiver StringBuilder tại lúc tạo Supplier. Sau khi builder.append("B"), Supplier gọi toString trên **cùng đối tượng**, nên trả "AB". Tham chiếu cố định không có nghĩa đối tượng là immutable.

Đây là ví dụ chạy tuần tự, không có dữ liệu được sửa đồng thời. Khi một method reference gắn receiver mutable được nhiều luồng sử dụng, an toàn luồng phụ thuộc vào đối tượng và cách truy cập, không phụ thuộc riêng cú pháp **::**.

## 13. Chọn overload: cùng tên nhưng không phải cùng chữ ký

Một lớp có thể khai báo nhiều phương thức cùng tên với danh sách tham số khác nhau. Method reference chỉ phù hợp nếu Java chọn được một phương thức đáp ứng ngữ cảnh kiểu đích.

Ví dụ **Math::max**:

~~~java
java.util.function.IntBinaryOperator integers = Math::max;
java.util.function.LongBinaryOperator longs = Math::max;
java.util.function.DoubleBinaryOperator doubles = Math::max;
~~~

Ba dòng là đoạn minh họa trong ngữ cảnh Java, cần import đúng các giao diện. Mỗi SAM có hai tham số primitive và một kết quả primitive tương ứng, nên Java chọn overload tương thích.

**System.out::println** cũng có nhiều overload: có bản không đối số, có bản nhận String, int, long, Object, v.v. Ngữ cảnh **Consumer<String>** cung cấp một String, nên có thể chọn overload println(String). Nếu ngữ cảnh khác, overload được chọn có thể khác.

Các trường hợp khó hơn có thể **mơ hồ**: có nhiều phương thức cùng tên áp dụng được và không có một lựa chọn hợp lệ duy nhất. Giải pháp thường hữu ích:

1. Khai báo biến trung gian với kiểu functional interface mong muốn.
2. Làm rõ kiểu tham số/kiểu trả về hoặc dùng lambda tường minh thay method reference.
3. Nếu cần, thêm type witness cho phương thức generic hoặc ép kiểu đúng chỗ.
4. Thiết kế lại overload trong API do mình kiểm soát nếu việc chọn overload thường xuyên gây khó hiểu.

Không nên chọn một overload “theo cảm giác” khi trình biên dịch báo ambiguous. Mã có thể hoạt động khác mong muốn chỉ vì API thay đổi hoặc thêm overload mới; ngữ cảnh kiểu rõ ràng là một phần của khả năng bảo trì.

## 14. Method reference trong Stream và Comparator

Method reference thường rất có ích với Stream vì API sẵn có các chữ ký functional interface chính xác.

Ví dụ, với danh sách các String:

~~~java
java.util.List<String> words =
    java.util.Arrays.asList("Java", "API", "Lambda");

java.util.List<Integer> lengths = words.stream()
    .map(String::length)
    .collect(java.util.stream.Collectors.toList());
~~~

Đây là đoạn minh họa trong phương thức. **Stream<String>.map(...)** nhận Function<? super String,? extends R>. **String::length** dùng phần tử String làm receiver, trả int được boxing thành Integer; danh sách kết quả chứa **[4, 3, 6]**.

Nếu cần tính tổng độ dài không cần boxing kết quả từng phần tử:

~~~java
int totalLength = words.stream()
    .mapToInt(String::length)
    .sum(); // 13
~~~

**mapToInt** nhận ToIntFunction<? super String>; kết quả là IntStream. Những giao diện như **Function**, **ToIntFunction**, **Comparator** cung cấp kiểu đích, còn method reference chỉ cung cấp cách thực hiện.

Đối với Comparator:

~~~java
java.util.Comparator<String> byLength =
    java.util.Comparator.comparingInt(String::length);
~~~

**Comparator.comparingInt** nhận ToIntFunction<? super String>, vì vậy String::length được ánh xạ thành phép trích khóa primitive int. Trong khi đó:

~~~java
java.util.Comparator<String> natural = String::compareTo;
~~~

**String::compareTo** phù hợp Comparator<String> vì SAM compare(String,String) có hai đối số: String receiver và String đối tượng cần so sánh. Hai ví dụ đều về sắp xếp, nhưng cách ánh xạ khác nhau.

### Khi nào nên dùng lambda thay vì method reference?

- Khi cần thêm điều kiện, lọc null, biến đổi tham số hoặc ghép nhiều thao tác.
- Khi phương thức đã tồn tại có tên khó hiểu so với ngữ cảnh.
- Khi có overload hoặc generic inference khiến cú pháp **::** kém rõ ràng.
- Khi cần thể hiện rõ ý nghĩa receiver và tham số, nhất là với instance method có nhiều đối số.

Ví dụ **(left, right) -> left.compareToIgnoreCase(right)** đôi khi dễ đọc hơn **String::compareToIgnoreCase** đối với người mới học. Cả hai có thể làm Comparator<String>, nhưng lựa chọn dựa vào mức độ dễ hiểu trong ngữ cảnh.

## 15. Checked exception và những hạn chế của kiểu đích

Method reference phải phù hợp không chỉ tham số/kết quả, mà còn các **checked exception** do phương thức đích có thể ném. Ví dụ **Function<T,R>.apply** không khai báo checked exception, nên không thể gán thẳng method reference tới một phương thức đòi xử lý IOException nếu ngoại lệ đó không được hợp đồng SAM cho phép.

Khi cần ngoại lệ đã kiểm tra, có thể:

- Xử lý ngoại lệ bên trong một phương thức wrapper trả kết quả phù hợp.
- Dùng một functional interface do ứng dụng định nghĩa có chữ ký **throws** tương ứng.
- Dùng **Callable<V>** nếu đó là một tác vụ không đối số có kết quả và checked exception, đồng thời API sử dụng đúng Callable.

**Không tự bọc mọi checked exception thành RuntimeException** để chỉ làm compiler ngừng báo lỗi: cần có chính sách rõ ràng về ngữ cảnh, log, truyền lỗi, hủy tác vụ và xử lý dữ liệu.

Phương thức bị tham chiếu cũng phải **có thể truy cập được** tại nơi viết method reference (quy tắc private, protected, package-private và public). Method reference không bỏ qua quy tắc truy cập Java.

## 16. Những lỗi thường gặp

| Lỗi/nhầm lẫn | Nguyên nhân | Cách hiểu hoặc sửa |
| --- | --- | --- |
| Gán **String::length** cho Supplier<Integer> | Chưa có receiver String | Dùng **ToIntFunction<String>** hoặc cố định receiver bằng **someString::length** |
| Gán **someString::length** cho Function<String,Integer> | Receiver đã cố định nhưng SAM lại đòi một tham số | Dùng **Supplier<Integer>** hoặc dạng unbound **String::length** |
| Gán **String::substring** cho Function<Integer,String> | Cần String receiver nhưng SAM chỉ có Integer | Cố định receiver **text::substring** hoặc dùng BiFunction<String,Integer,String> |
| Tưởng **String::substring** luôn là một phương thức | Có overload 1 và 2 chỉ số | Chọn theo chữ ký SAM; cần 2 hoặc 3 tham số tương ứng |
| Tưởng **Integer::parseInt** nhận receiver Integer | parseInt là static | SAM cung cấp chuỗi cần parse, không có receiver |
| Tưởng method reference gọi ngay phương thức | Nó mô tả hành vi cho SAM | Phần thân chạy khi API gọi SAM |
| Dùng Function<String,String> cho String::length | length trả int, không phải String | Dùng Function<String,Integer> hoặc ToIntFunction<String> |
| Dùng Function<int,int> | Generics chỉ nhận kiểu tham chiếu | Dùng Function<Integer,Integer> hoặc IntUnaryOperator |
| Tưởng method reference luôn tránh boxing | Tùy kiểu SAM và phương thức đích | Dùng API primitive nếu phù hợp; đừng suy đoán hiệu năng |
| Tưởng generic method bắt buộc ghi type witness | Compiler thường suy luận được từ kiểu đích | Chỉ ghi rõ nếu giúp giải nghĩa hoặc giải mơ hồ |
| Dùng phương thức generic với type bound không thỏa | Không thể suy luận T hợp lệ | Kiểm tra giới hạn kiểu của phương thức |
| Dùng **Object o = String::length** | Object không phải functional interface | Khai báo một target functional interface trước |
| Dùng method reference tới API ném IOException trong Function | SAM không khai báo checked exception | Bọc xử lý hoặc chọn hợp đồng throws đúng |
| Gắn receiver mutable rồi tưởng dữ liệu không đổi | Chỉ tham chiếu receiver được chốt | Xem trạng thái đối tượng tại thời điểm gọi |
| Tin rằng phương thức nào trả giá trị cũng dùng được với mọi SAM void | Quy tắc tương thích không tùy tiện | Kiểm tra chính xác chữ ký và ý định bỏ kết quả |
| Dùng comparator có quy tắc không nhất quán | Có thể gây sắp xếp sai hoặc lỗi thực thi | Chọn phép so sánh ổn định, có hợp đồng rõ ràng |

### Khác biệt giữa reference và lời gọi thực tế

- **Integer::parseInt** là method reference; **Integer.parseInt("7")** là lời gọi phương thức ngay.
- **Collections::emptyList** là method reference; **Collections.emptyList()** tạo/lấy danh sách ngay theo hợp đồng phương thức.
- **User::new** là constructor reference; **new User(...)** trực tiếp xây đối tượng.
- **obj::method** chốt receiver khi tạo tham chiếu, nhưng phần thân method thường chạy khi SAM được gọi.

Đừng nhầm **thời điểm tìm/đánh giá receiver** với **thời điểm chạy phương thức**.

## 17. Bài tập và đáp án

**Bài 1 — Xác định receiver.** Với **Function<String,Integer> f = String::length**, đối số nào đi vào length()? Đáp án: String từ **f.apply("Java")** là receiver; length() không nhận tham số khai báo và trả int, được boxing thành Integer trong Function.

**Bài 2 — Phương thức có một tham số thực.** Với **BiFunction<String,Integer,String> f = String::substring**, lời gọi **f.apply("hello",2)** trả gì? Đáp án: **"llo"**. String đầu tiên làm receiver; Integer thứ hai được unboxing thành chỉ số bắt đầu int.

**Bài 3 — Phương thức có hai tham số thực.** Tạo giao diện TriFunction<A,B,C,R> rồi gán **TriFunction<String,Integer,Integer,String> f = String::substring**. **f.apply("abcdef",1,4)** trả **"bcd"** vì receiver "abcdef", beginIndex 1 và endIndex 4 (không bao gồm vị trí 4).

**Bài 4 — Generic inference.** Giải thích vì sao **Supplier<List<String>> s = Collections::emptyList** hợp lệ dù emptyList là phương thức generic. Đáp án: kiểu đích yêu cầu List<String> nên compiler suy luận type argument tương ứng; lời gọi s.get() trả danh sách rỗng có kiểu List<String> theo hợp đồng.

**Bài 5 — Type witness.** Viết lại bài 4 với type argument tường minh. Đáp án: **Supplier<List<String>> s = Collections::<String>emptyList**. Kiểu tham số generic được đặt sau dấu **::** của method reference.

**Bài 6 — Kết quả bị bỏ qua.** Với **List<String> list = new ArrayList<>(); Consumer<String> add = list::add;**, phương thức List.add trả boolean, vậy Consumer có trả boolean không? Đáp án: không; accept() vẫn void, giá trị boolean từ add không được dùng.

**Bài 7 — Overload.** Math::max được gán cho **IntBinaryOperator** hay **DoubleBinaryOperator** thì chọn cùng overload? Đáp án: không. SAM của từng kiểu đích quy định tham số/kết quả primitive, dẫn tới overload Math.max tương ứng.

**Bài 8 — Quy tắc kiểm tra nhanh.** Khi thấy một biểu thức **Type::instanceMethod**, hãy viết ra lambda có receiver tường minh: **(receiver, arg1, ...) -> receiver.instanceMethod(arg1, ...)**, sau đó so với SAM. Đây là công cụ suy luận hữu ích, không có nghĩa mọi method reference đều bắt buộc viết được thành đúng một lambda ngắn trong mọi trường hợp overload/generic phức tạp.

## Tổng kết

Một method reference được kiểm tra trong **ngữ cảnh kiểu đích**. Để đọc đúng, hãy xác định SAM rồi xét bốn yếu tố:

1. **Phương thức static hay instance?** Static nhận trực tiếp đối số SAM; instance có thể đã gắn receiver hoặc dùng đối số SAM đầu tiên làm receiver.
2. **Có bao nhiêu tham số và kiểu gì?** Tính cả receiver nếu dạng **Type::instanceMethod**; xét boxing/unboxing và các chuyển đổi Java cho phép.
3. **Kết quả có tương thích không?** Xét primitive, wrapper, kiểu tham chiếu, chuyển đổi hợp lệ và trường hợp giá trị được bỏ qua khi đích trả void.
4. **Có generic, overload, checked exception hoặc giới hạn truy cập không?** Kiểu đích hỗ trợ suy luận và chọn phương thức, nhưng không bỏ qua các ràng buộc của ngôn ngữ.

Học cách ánh xạ **receiver → tham số → kiểu kết quả → generic type arguments** giúp bạn đọc và thiết kế method reference chính xác trong Stream, Comparator, constructor factory và các API Java hiện đại.