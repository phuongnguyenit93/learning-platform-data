# Poly expression và ràng buộc generic trong suy luận kiểu Java

## Mục tiêu học tập

Trong Java, không phải lúc nào trình biên dịch cũng xác định kiểu của một biểu thức chỉ bằng cách nhìn vào chính biểu thức đó. Với **poly expression**, kiểu của biểu thức có thể phụ thuộc vào **kiểu đích (target type)** của ngữ cảnh sử dụng. Từ Java 8, đặc tính này đặc biệt quan trọng với lambda, method reference, lời gọi phương thức generic, toán tử điều kiện và cú pháp diamond **<>**.

Đồng thời, Java phải suy luận các **tham số kiểu generic** sao cho những ràng buộc từ đối số, kết quả mong đợi và khai báo **extends / wildcard** đều thỏa mãn. Hai cơ chế gắn chặt với nhau: kiểu đích có thể góp thêm ràng buộc cho generic inference; ngược lại, việc giải ràng buộc generic có thể quyết định kiểu của lambda hoặc method reference lồng bên trong.

Sau bài này, bạn sẽ:

- Phân biệt **standalone expression** và **poly expression** ở những ngữ cảnh thông dụng.
- Biết cách tìm kiểu đích khi có phép gán, lời gọi phương thức, câu lệnh return và phép ép kiểu.
- Hiểu vai trò của tham số kiểu **T**, ràng buộc **upper bound**, quan hệ kiểu con, wildcard và suy luận kiểu của generic method.
- Giải thích vì sao lambda/method reference cần functional interface, và vì sao một biểu thức có thể hợp lệ ở ngữ cảnh này nhưng không hợp lệ ở ngữ cảnh khác.
- Sử dụng **Collections.emptyList()**, **new ArrayList<>()**, **Comparator.comparingInt(...)** và các API generic hiện đại một cách đúng kiểu.
- Nhận diện lỗi **invariance**, lỗi giới hạn kiểu, lỗi overload mơ hồ và những cách khắc phục không cần raw type hoặc ép kiểu không an toàn.

Các quy tắc nền tảng dưới đây vẫn áp dụng trong Java hiện đại. Ví dụ chương trình đầy đủ sử dụng Java 8-compatible API và biên dịch trên JDK 8 trở lên, gồm JDK 17+.

## 1. Poly expression: kiểu đến từ ngữ cảnh

Hãy xét:

~~~java
java.util.function.Function<String, Integer> length = String::length;
~~~

Bên trái dấu bằng có kiểu **Function<String,Integer>**. Nhờ kiểu này, Java biết method reference **String::length** cần triển khai phương thức trừu tượng **Integer apply(String)**. Đối số String trở thành receiver gọi **length()**, kết quả nguyên thủy int được boxing thành Integer.

Nếu chỉ viết:

~~~java
// Object value = String::length; // Không hợp lệ.
~~~

thì **Object không phải functional interface**, nên không cung cấp đủ hợp đồng chức năng làm kiểu đích. Bản thân method reference **không phải một đối tượng Function tự có kiểu độc lập**.

**Poly expression** là biểu thức được kiểm tra trong một **ngữ cảnh yêu cầu kiểu**; kiểu của nó có thể phụ thuộc vào kiểu đích trong ngữ cảnh đó. Ngược lại, một **standalone expression** có kiểu xác định theo quy tắc riêng, không cần lấy kiểu trả về từ vế trái phép gán theo cách của poly expression.

Ví dụ:

~~~java
int number = 42;
~~~

Literal **42** có kiểu int theo quy tắc của literal. Nó không trở thành một poly expression chỉ vì có một phép gán xung quanh.

Còn:

~~~java
java.util.List<String> empty =
    java.util.Collections.emptyList();
~~~

là ví dụ quan trọng về **generic method invocation** ở ngữ cảnh poly: phương thức **Collections.<T>emptyList()** trả **List<T>**, và **List<String>** ở vế trái góp phần khiến T được suy luận là String.

**Không phải mọi method invocation hay mọi constructor invocation đều là poly expression**. Ngôn ngữ có những điều kiện cụ thể về ngữ cảnh, dạng lời gọi, kiểu trả về, diamond và các thông tin kiểu có sẵn. Hãy dùng các nhóm điển hình trong bài để suy luận; không nên áp đặt nhận định “mọi biểu thức bên phải dấu bằng đều poly”.

## 2. Các ngữ cảnh thường cung cấp target type

Những vị trí hữu ích nhất:

| Ngữ cảnh | Ví dụ | Kiểu đích có ích |
| --- | --- | --- |
| Khai báo/gán | **Function<String,Integer> f = String::length;** | Function<String,Integer> |
| Truyền đối số | **words.sort(Comparator.comparingInt(String::length));** | Kiểu tham số API, được giải cùng inference |
| Trả về từ phương thức | **return () -> "ok";** trong phương thức trả Supplier<String> | Supplier<String> |
| Ép kiểu | **(Runnable) () -> work()** | Runnable |
| Toán tử điều kiện dạng tham chiếu | **List<String> x = flag ? Collections.emptyList() : names;** | List<String> cho các nhánh phù hợp |
| Khởi tạo generic bằng diamond | **List<String> x = new ArrayList<>();** | List<String> góp phần suy luận phần tử String |

Hai ví dụ trong bảng gọi **work()**, **words**, **flag**, **names** là các **đoạn minh họa**, cần các khai báo phù hợp để chạy.

### Assignment context

~~~java
java.util.function.Supplier<String> produce = () -> "Sẵn sàng";
java.util.function.Predicate<String> nonEmpty = s -> !s.isEmpty();
~~~

Đây là hai dòng minh họa trong phương thức. Kiểu đích quyết định lambda nhận mấy tham số, kiểu tham số là gì, và kết quả phải tương thích với **get()** hoặc **test(String)**.

### Invocation context

~~~java
java.util.List<String> names = java.util.Arrays.asList("An", "Binh");
names.removeIf(name -> name.length() < 3);
~~~

**Collection.removeIf(Predicate<? super E>)** cung cấp kiểu đích cho lambda. Với danh sách String, Java suy luận tham số name tương thích với String và yêu cầu kết quả boolean. Lệnh trên xóa "An", giữ "Binh".

### Return context

~~~java
static java.util.function.Supplier<String> messageFactory() {
    return () -> "Xin chào";
}
~~~

Đây là **phương thức minh họa** cần đặt trong một lớp. Kiểu trả về của messageFactory cung cấp kiểu đích cho lambda trong câu lệnh return.

### Cast context

~~~java
java.util.function.IntUnaryOperator twice =
    (java.util.function.IntUnaryOperator) x -> x * 2;
~~~

Đây là đoạn minh họa. Phép ép kiểu tường minh có thể dùng để chỉ rõ ý định trong những trường hợp target typing/overload phức tạp. Thông thường, khai báo biến có kiểu rõ ràng dễ đọc hơn việc rải nhiều phép ép kiểu.

## 3. Lambda và method reference là poly expression

Với lambda:

~~~java
java.util.function.Function<String, Integer> a =
    text -> text.length();

java.util.function.ToIntFunction<String> b =
    text -> text.length();
~~~

Cùng cú pháp thân **text -> text.length()**, nhưng:

- **a.apply("Java")** trả một **Integer** theo hợp đồng Function<String,Integer>; kết quả int từ length() được boxing khi thích hợp.
- **b.applyAsInt("Java")** trả **int** nguyên thủy theo hợp đồng ToIntFunction<String>.

Với method reference:

~~~java
java.util.function.Function<String, Integer> a = String::length;
java.util.function.ToIntFunction<String> b = String::length;
~~~

Tương tự, kiểu đích quyết định chữ ký SAM cần khớp. Method reference không mang một “kiểu hàm String -> int” độc lập để có thể gán cho mọi kiểu Object.

### Tham số lambda được suy luận từ SAM

~~~java
java.util.Comparator<String> byLength =
    (left, right) -> Integer.compare(left.length(), right.length());
~~~

SAM của Comparator<String> là **int compare(String,String)**. Vì vậy left/right đều được hiểu là String, và Java kiểm tra kết quả int. Nếu gán lambda này cho **Predicate<String>**, nó sẽ sai số tham số và kiểu kết quả, không phải lỗi do tên biến.

Bạn có thể ghi rõ tham số:

~~~java
java.util.Comparator<String> byLength =
    (String left, String right) ->
        Integer.compare(left.length(), right.length());
~~~

Hai phiên bản là đoạn minh họa độc lập (không nên khai báo trùng tên trong cùng block). Java không cho kiểu tường minh một tham số và để tham số khác suy luận tùy tiện trong cùng một lambda khai báo kiểu truyền thống.

### Vì sao không thể suy luận lambda từ "var"?

Từ Java 10, **var** suy luận kiểu biến cục bộ từ initializer. Nhưng một lambda không có kiểu target độc lập đủ để viết:

~~~java
// var action = x -> x; // Không hợp lệ: thiếu target type.
~~~

Hãy khai báo functional interface:

~~~java
java.util.function.UnaryOperator<String> action = x -> x;
~~~

**Java 11+** cho phép dùng **var** trong khai báo tham số lambda với một số quy tắc nhất quán của danh sách tham số, ví dụ **(var x) -> x** khi đã có kiểu đích phù hợp. Điều đó **không** thay thế yêu cầu functional interface ở ngữ cảnh lambda. Nếu dự án cần biên dịch bằng JDK 8 thì không dùng hai cú pháp var này.

## 4. Generic type parameter và các ràng buộc

Hãy xem một phương thức generic:

~~~java
static <T> T choose(T first, T second) {
    return first;
}
~~~

Đây là **phương thức minh họa** cần đặt trong một lớp. **T** là một **type variable** do phương thức khai báo. Mỗi lần gọi, compiler phải tìm một cách gán kiểu cho T sao cho cả đối số và kiểu kết quả theo ngữ cảnh cùng hợp lệ.

Ví dụ:

~~~java
String selected = choose("A", "B");
~~~

Cả hai đối số là String, và kiểu đích là String. Trong tình huống này, T có thể được suy luận thành String.

Nhưng khi các đối số khác kiểu:

~~~java
Object chosen = choose("A", 5);
~~~

compiler có thể tìm một kiểu chung phù hợp các ràng buộc, ví dụ một kiểu cha hoặc một giao của các kiểu phù hợp; **không nên khẳng định luôn chọn Object** cho mọi cặp. Trong Java, việc suy luận có thể liên quan đến least upper bound và intersection types. Trên thực tế nên để IDE/javac kiểm tra chính xác kiểu suy luận của những trường hợp phức tạp.

### Ràng buộc từ đầu vào và đầu ra

Với:

~~~java
static <T> java.util.List<T> single(T element) {
    return java.util.Collections.singletonList(element);
}
~~~

Lời gọi:

~~~java
java.util.List<Number> numbers = single(7);
~~~

**7** là literal int được boxing thành Integer khi đi vào generic method; ngữ cảnh **List<Number>** góp phần ràng buộc T, nên Java có thể suy luận một T phù hợp (Number) để phép gán hợp lệ. Không có nghĩa biến numbers trực tiếp chứa Number kiểu nguyên thủy; phần tử 7 được lưu dưới dạng đối tượng Integer tương thích Number.

Nếu bỏ kiểu đích và đặt lời gọi vào một ngữ cảnh khác, suy luận có thể khác. Vì vậy khi phân tích generic method invocation, hãy xem **cả đối số lẫn nơi sử dụng kết quả**.

## 5. Một ví dụ hoàn chỉnh về poly expressions

Tạo tệp **PolyTargetTypingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;

public class PolyTargetTypingDemo {

    static <T> T same(T value) {
        return value;
    }

    static <T> List<T> single(T value) {
        return Collections.singletonList(value);
    }

    public static void main(String[] args) {
        List<String> empty = Collections.emptyList();

        List<String> items = new ArrayList<>();
        items.add("Java");

        Function<String, Integer> length = String::length;

        List<Number> numbers = single(9);

        String selected = true ? same("A") : same("B");

        List<String> branch = false
            ? Collections.emptyList()
            : Collections.singletonList("X");

        System.out.println("empty: " + empty);
        System.out.println("items: " + items);
        System.out.println("length: " + length.apply("Java"));
        System.out.println("numbers: " + numbers);
        System.out.println("selected: " + selected);
        System.out.println("branch: " + branch);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PolyTargetTypingDemo.java
java PolyTargetTypingDemo
~~~

Kết quả:

~~~text
empty: []
items: [Java]
length: 4
numbers: [9]
selected: A
branch: [X]
~~~

Phân tích:

1. **Collections.emptyList()** là generic method; ngữ cảnh **List<String>** góp phần suy luận T.
2. **new ArrayList<>()** dùng diamond. Khi tạo trong assignment context, thông tin từ kiểu đích giúp suy luận đối số kiểu String.
3. **String::length** được áp vào Function<String,Integer>; kiểu tham số và kết quả tương ứng được xác định nhờ SAM.
4. **single(9)** hoạt động với **List<Number>**, mặc dù đối số được boxing từ int thành Integer. Compiler giải ràng buộc của T để đầu vào và đầu ra đều phù hợp.
5. Các nhánh toán tử điều kiện trả về tham chiếu có thể sử dụng kiểu đích; với **branch**, mục tiêu là List<String>, hai nhánh generic tạo danh sách String.
6. Kiểu đích không làm chương trình đổi nhánh khi chạy: **true/false** quyết định giá trị cụ thể ở runtime; type inference là kiểm tra tại compile time.

**Phân biệt ba việc:** suy luận kiểu của biểu thức, lựa chọn nhánh lúc chạy và dispatch phương thức không phải cùng một cơ chế.

## 6. Ba dạng ràng buộc thường gặp khi suy luận generic

Bạn không cần thuộc toàn bộ thuật toán trong Java Language Specification để đọc mã ứng dụng, nhưng phải hiểu ba nhóm câu hỏi:

**(1) Kiểu bằng nhau hoặc tương ứng (equality/compatibility):** một biến kiểu được dùng ở những vị trí yêu cầu cùng kiểu hoặc kiểu có khả năng chuyển đổi tương thích. Chẳng hạn **List<T>** cần phù hợp với **List<String>**, thường ràng buộc T rất chặt vì generic class bất biến theo kiểu tham số (invariant).

**(2) Quan hệ kiểu con (subtyping):** nếu một vị trí yêu cầu Number mà giá trị là Integer, quan hệ **Integer <: Number** giúp giá trị hợp lệ. Tuy nhiên **List<Integer> không phải subtype của List<Number>**; phải xét generic invariance và wildcard riêng.

**(3) Giới hạn kiểu (type bounds):** khai báo **<T extends Number>** yêu cầu T là Number hoặc subtype phù hợp. Mọi suy luận còn phải thỏa giới hạn này.

Trình biên dịch hình thành các ràng buộc từ kiểu đối số, kiểu tham số formal, các expression lồng nhau và kiểu đích rồi giải theo quy tắc của ngôn ngữ. Khi có lambda/method reference lồng trong lời gọi generic, việc suy luận có thể trì hoãn phân tích một phần expression cho đến khi một số type variable đã được xác định đủ.

**Đừng hình dung compiler chỉ chạy một phép gán T = kiểu của đối số đầu tiên.** Nó có thể phải tổng hợp thông tin từ nhiều đối số, các bounds, wildcard và context ở đầu ra.

## 7. Upper bound: <T extends ...> không có nghĩa là chỉ đúng kiểu đó

Một phương thức tìm giá trị lớn hơn có thể khai báo:

~~~java
static <T extends Comparable<? super T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

Đây là **phương thức minh họa** cần đặt trong lớp. Ràng buộc **T extends Comparable<? super T>** yêu cầu T có khả năng so sánh với T qua một loại Comparable thích hợp, kể cả trường hợp Comparable được khai báo cho một supertype.

Ví dụ:

~~~java
String value = larger("cat", "dog"); // "dog"
~~~

String đáp ứng ràng buộc so sánh; compiler có thể suy luận T phù hợp. Một kiểu do bạn tạo không thực hiện hợp đồng Comparable tương ứng **không trở nên hợp lệ chỉ vì có cùng tên phương thức**.

### Nhiều giới hạn kiểu

Java cho phép nhiều bounds như:

~~~java
static <T extends Number & Comparable<T>> int compareAndCount(
        T first, T second) {
    return first.compareTo(second);
}
~~~

Đây là **phương thức minh họa**. T phải là subtype của Number và thực hiện Comparable<T> tương ứng. Thứ tự trong khai báo nhiều bounds quan trọng: nếu có bound là **class**, nó phải xuất hiện đầu tiên; tiếp theo có thể là interfaces.

Không thể dùng kiểu nguyên thủy trực tiếp làm type argument của generic: **List<int>** không hợp lệ; dùng **List<Integer>** hoặc API primitive chuyên biệt. Boxing có thể góp phần vào quá trình suy luận nhưng không thay đổi quy tắc generics chỉ nhận kiểu tham chiếu.

## 8. Generic invariance: List<Integer> không phải List<Number>

Một lỗi rất phổ biến:

~~~java
// List<Number> values = new ArrayList<Integer>(); // Lỗi biên dịch.
~~~

Dù Integer là subtype của Number, quan hệ ấy **không tự nâng** thành quan hệ List<Integer> <: List<Number>. Nếu Java cho phép điều đó, bạn có thể thêm Double vào danh sách vốn được tạo để chứa Integer, phá vỡ kiểu phần tử.

Cách đúng phụ thuộc mục đích:

- Cần một danh sách chứa nhiều subtype Number và có thể thêm vào: tạo **List<Number>** ngay từ đầu.
- Cần **đọc số** từ danh sách Number hoặc subtype Number: xem **List<? extends Number>**.
- Cần một nơi **nhận Integer để thêm**: xem **List<? super Integer>**.

Ví dụ minh họa:

~~~java
List<Integer> integers = java.util.Arrays.asList(2, 4);
List<? extends Number> readable = integers;
Number first = readable.get(0); // 2
~~~

**readable** có thể tham chiếu tới List<Integer>; không được tùy ý **readable.add(3)** vì một wildcard extends không cung cấp thông tin chính xác về kiểu phần tử cho phép thêm (ngoại trừ null theo các quy tắc liên quan). Cách này chỉ giải quyết việc đọc/tiêu thụ dữ liệu, không đổi kiểu gốc của danh sách.

Với consumer:

~~~java
List<Number> numbers = new java.util.ArrayList<>();
List<? super Integer> destination = numbers;
destination.add(5);
~~~

Có thể thêm Integer vì đích được bảo đảm nhận được Integer. Nhưng khi lấy phần tử từ **destination.get(0)**, kiểu biết chắc theo khai báo wildcard super chỉ là **Object**, không mặc nhiên là Integer.

Quy tắc dễ nhớ: **PECS — Producer Extends, Consumer Super**. Nếu collection là nguồn cung cấp giá trị kiểu T, thường dùng **? extends T**; nếu là nơi nhận thêm giá trị T, thường dùng **? super T**. Đây là mẹo thiết kế API, không thay thế việc kiểm tra toàn bộ các thao tác cần thực hiện.

## 9. Wildcard và generic method kết hợp

Một API copy an toàn có thể viết:

~~~java
static <T> void appendAll(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

Đoạn này cần đặt trong một lớp. **source** là producer các giá trị T nên dùng extends, còn **destination** là consumer của T nên dùng super.

Cách dùng:

~~~java
java.util.List<Integer> integers =
    java.util.Arrays.asList(2, 4, 6);

java.util.List<Number> numbers =
    new java.util.ArrayList<>();

appendAll(numbers, integers);
~~~

Compiler có thể suy luận T phù hợp và kiểm tra cả hai vị trí. **Không cần ép kiểu List<Integer> sang List<Number>**, và cũng không nên sử dụng raw List chỉ để vượt qua lỗi invariance.

### Capture conversion — một điểm đáng biết

Với wildcard **?**, compiler có thể tạo ra một biến kiểu tạm được gọi là **capture** để suy luận và kiểm tra quan hệ giữa các phần tử bên trong những thao tác generic. Đây là cơ chế compile time, không phải đối tượng mới được tạo ở runtime.

Đôi khi một thao tác trên **List<?>** thất bại vì kiểu phần tử chưa xác định. Một **generic helper method** có thể giúp compiler đặt tên capture đó bằng type variable để thực hiện thao tác an toàn. Tuy nhiên, với List<?> bạn vẫn không được tùy ý thêm một giá trị Object không rõ kiểu.

Trong bài thực tế, trước khi dùng cast không an toàn để chữa lỗi capture, hãy xét liệu phương thức nhận **List<? extends T>**, **List<? super T>** hoặc một type parameter T rõ ràng có thể diễn đạt hợp đồng chính xác hơn không.

## 10. Chương trình hoàn chỉnh: bounds, wildcard và method reference

Tạo tệp **GenericConstraintsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Function;

public class GenericConstraintsDemo {

    static <T extends Comparable<? super T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T> void appendAll(
            List<? super T> target,
            List<? extends T> source) {
        for (T value : source) {
            target.add(value);
        }
    }

    static <T, R> List<R> mapCopy(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();
        for (T element : source) {
            result.add(mapper.apply(element));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> integers = Arrays.asList(2, 4, 6);
        List<Number> numbers = new ArrayList<>();

        appendAll(numbers, integers);

        List<String> words = Arrays.asList("Java", "API");
        List<Integer> lengths = mapCopy(words, String::length);

        String largerWord = larger("alpha", "zeta");

        System.out.println("numbers: " + numbers);
        System.out.println("lengths: " + lengths);
        System.out.println("larger: " + largerWord);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericConstraintsDemo.java
java GenericConstraintsDemo
~~~

Kết quả:

~~~text
numbers: [2, 4, 6]
lengths: [4, 3]
larger: zeta
~~~

Phân tích:

1. **appendAll(numbers, integers)** ràng buộc T thông qua **List<? super T>** và **List<? extends T>**. Java chọn được T phù hợp để nhận các Integer trong một List<Number>.
2. **mapCopy(words, String::length)** kết hợp generic inference với target typing của method reference. Kiểu nguồn là String, kiểu kết quả R là Integer; **String.length()** trả int và được boxing phù hợp.
3. **larger("alpha","zeta")** suy luận kiểu đủ điều kiện **Comparable**, rồi so sánh theo String.compareTo.
4. **new ArrayList<>()** trong phần thân **mapCopy** sử dụng diamond và thông tin từ biến **List<R> result** để suy luận kiểu phần tử.
5. Tất cả những quyết định kiểu xảy ra khi biên dịch; lúc chạy, danh sách được điền theo vòng lặp thông thường và kết quả được in đúng thứ tự thêm.

### Khi nào phương thức nhận wildcard linh hoạt hơn?

So sánh:

~~~java
static <T> void strictCopy(List<T> out, List<T> in) { /* ... */ }
~~~

với:

~~~java
static <T> void flexibleCopy(
    List<? super T> out, List<? extends T> in) { /* ... */ }
~~~

Đây là các **khai báo minh họa**, không phải chương trình độc lập; cần khai báo import List và đặt trong một lớp. **strictCopy** yêu cầu cùng một đối số kiểu T cho cả hai List, nên không chấp nhận trực tiếp cặp **List<Number>** / **List<Integer>** theo cách bạn mong muốn. **flexibleCopy** mô tả rõ phương án “đọc T từ nguồn, ghi T vào đích” và chấp nhận tình huống subtype/supertype an toàn.

Không nên dùng wildcard tràn lan: khi cả hai vị trí phải có **cùng kiểu chính xác**, ràng buộc List<T> có thể là đúng ý thiết kế hơn.

## 11. Generic method invocation nhận thông tin từ target type

Xem phương thức chuẩn:

~~~java
static <T> List<T> emptyList()
~~~

Đây là **chữ ký lược giản** của phương thức chuẩn **Collections.emptyList()**, không phải dòng Java hoàn chỉnh để chạy độc lập. T thường được suy luận từ ngữ cảnh:

~~~java
List<String> words = Collections.emptyList();
List<Integer> numbers = Collections.emptyList();
~~~

Hai dòng trên là đoạn minh họa cần import List, Collections. Không phải Collections có hai overload riêng cho String/Integer; cùng một phương thức generic được chuyên biệt hóa ở compile time theo **kiểu đích**.

Có thể truyền type argument rõ ràng:

~~~java
List<String> words = Collections.<String>emptyList();
~~~

Cú pháp **Collections.<String>emptyList()** là *explicit type witness*. Trong method reference, cách viết tương ứng là **Collections::<String>emptyList**; không được lẫn vị trí dấu chấm/dấu hai chấm.

### Suy luận không luôn lấy từ vế trái

Khi dùng phương thức generic lồng trong lời gọi khác, compiler có thể nhận ràng buộc từ kiểu formal parameter của API bên ngoài:

~~~java
static void acceptStrings(List<String> values) { /* ... */ }

acceptStrings(Collections.emptyList());
~~~

Đây là đoạn minh họa. Kiểu đích của đối số mà acceptStrings cần là List<String>, giúp suy luận T cho emptyList.

Không nên tách biểu thức thành biến kiểu **Object** nếu bạn vẫn muốn giữ thông tin generic để truyền tiếp:

~~~java
Object unknown = Collections.emptyList();
// acceptStrings(unknown); // Không hợp lệ: Object không phải List<String>.
~~~

Bạn có thể tạo một biến với **List<String>** ngay từ đầu để giữ hợp đồng kiểu tường minh.

## 12. Ràng buộc khi suy luận lambda trong phương thức generic

Xét phương thức:

~~~java
static <T, R> List<R> transform(
        List<T> input,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> result = new java.util.ArrayList<>();
    for (T item : input) {
        result.add(mapper.apply(item));
    }
    return result;
}
~~~

Đây là phương thức minh họa cần đặt trong một lớp, cùng import List. Khi gọi:

~~~java
List<Integer> lengths = transform(
    java.util.Arrays.asList("One", "Two"),
    word -> word.length()
);
~~~

Compiler cần suy luận **T** và **R**. Nguồn là List<String>, nên T phù hợp String. Mapper được mong đợi hoạt động như Function từ String sang một kiểu kết quả tương thích; **word** được hiểu là String. Thân lambda trả int, kết quả có thể boxing thành Integer cho R theo ngữ cảnh **List<Integer>**.

**Điều quan trọng:** không nên yêu cầu Java suy luận trước kiểu của **word -> word.length()** như một lambda đứng tự do. Kiểu của lambda chỉ có nghĩa khi đặt trong **functional interface target**, mà target đó lại có thể chứa các inference variable do phương thức generic cung cấp. Compiler giải hệ ràng buộc này **liên kết**, không phải hoàn toàn tuần tự.

### Độ phù hợp của lambda còn phụ thuộc kiểu trả về

Ví dụ:

~~~java
java.util.function.Predicate<String> valid =
    text -> !text.isEmpty();
~~~

SAM yêu cầu boolean. Nếu đổi vế trái thành Function<String,Integer>, cùng lambda đó không phù hợp vì **boolean** không tự chuyển thành Integer. Việc Java cho suy luận generic không có nghĩa kiểm tra kiểu trở nên lỏng lẻo.

Khi expression body là một lời gọi có trả giá trị và SAM trả void, Java có những quy tắc **statement expression** cho phép bỏ giá trị trong các trường hợp phù hợp; đừng suy rộng rằng mọi biểu thức trả kết quả đều có thể dùng làm body cho Runnable.

## 13. Wildcard và ràng buộc của method reference

Một **method reference** cũng cần target type phù hợp:

~~~java
Function<String, Integer> size = String::length;
java.util.function.ToIntFunction<String> primitiveSize =
    String::length;
~~~

Cùng một phương thức String.length() được ánh xạ thành hai SAM khác nhau. Cách hoạt động này giúp Java chấp nhận method reference bên trong API generic:

~~~java
List<Integer> sizes = transform(
    java.util.Arrays.asList("Java", "API"),
    String::length
);
~~~

Ví dụ minh họa cần có định nghĩa transform như phần trước. Compiler xét cùng lúc kiểu generic của transform và cách method reference phù hợp Function<? super T,? extends R>.

Trong một số trường hợp, **method reference nhiều overload** chưa đủ thông tin để suy luận nếu kiểu đích còn chưa xác định chặt, dẫn tới lỗi ambiguous hoặc cannot infer type-variable(s). Dùng lambda tường minh hoặc khai báo target variable trung gian thường giúp tạo thêm ràng buộc rõ ràng.

### Phương thức generic được tham chiếu

Giả sử có:

~~~java
static <T> T normalize(T value) {
    return value;
}
~~~

Chữ ký trên minh họa một generic method. Nếu đưa vào **Function<String,String>** hoặc **Function<Integer,Integer>** qua method reference tới lớp sở hữu nó, compiler có thể chuyên biệt hóa T theo target type. Tương tự, **Collections::emptyList** có thể làm **Supplier<List<String>>** vì Supplier yêu cầu List<String> và emptyList không nhận tham số.

Điều đó không có nghĩa mọi phương thức generic đều phù hợp với mọi SAM: nếu khai báo có **<T extends Number>**, việc cần đầu vào String sẽ không thỏa type bound.

## 14. Suy luận kiểu và overload: tại sao đôi khi phải làm rõ?

Một method overload có thể nhận hai functional interface khác nhau:

~~~java
static String inspect(Function<String, Integer> f) { /* ... */ }
static String inspect(java.util.function.ToIntFunction<String> f) {
    /* ... */
}
~~~

Đây là **khai báo phác họa**, không phải hai phương thức chạy độc lập: mỗi phương thức cần trả một String thực tế. Khi một method reference như **String::length** có thể phù hợp với nhiều functional interface, lời gọi trực tiếp có thể trở nên khó hiểu hoặc mơ hồ theo quy tắc overload resolution.

Cách an toàn là đặt kiểu đích rõ ràng:

~~~java
Function<String, Integer> boxed = String::length;
java.util.function.ToIntFunction<String> primitive = String::length;

inspect(boxed);
inspect(primitive);
~~~

Việc chọn overload giờ dựa trên **kiểu khai báo của biến**, không phải phỏng đoán từ phần thân String.length(). Trong những trường hợp cần gọn, phép ép kiểu chính xác cũng có thể làm rõ overload:

~~~java
inspect((java.util.function.ToIntFunction<String>) String::length);
~~~

**Lưu ý:** không phải cứ có nhiều overload nhận functional interface thì trình biên dịch luôn báo ambiguous. Java có các quy tắc cụ thể về tính áp dụng, tính cụ thể hơn và khả năng dùng kết quả của lambda/method reference. Hãy để javac/IDE kiểm tra trường hợp thật; mục tiêu ở đây là **cung cấp kiểu rõ ràng khi cần**.

## 15. Chương trình chạy được: chọn overload bằng target type

Tạo tệp **TargetOverloadDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.ToIntFunction;

public class TargetOverloadDemo {

    static String inspect(Function<String, Integer> function) {
        return "Function: " + function.apply("Java");
    }

    static String inspect(ToIntFunction<String> function) {
        return "ToIntFunction: " + function.applyAsInt("Java");
    }

    static boolean hasText(String text) {
        return text != null && !text.isEmpty();
    }

    public static void main(String[] args) {
        Function<String, Integer> boxed = String::length;
        ToIntFunction<String> primitive = String::length;

        Predicate<String> nonEmpty = TargetOverloadDemo::hasText;

        System.out.println(inspect(boxed));
        System.out.println(inspect(primitive));
        System.out.println("nonEmpty: " + nonEmpty.test("Java"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TargetOverloadDemo.java
java TargetOverloadDemo
~~~

Kết quả:

~~~text
Function: 4
ToIntFunction: 4
nonEmpty: true
~~~

Hai overload cùng dùng String::length, nhưng mỗi biến trung gian đã có kiểu functional interface xác định. Với **Function<String,Integer>**, kết quả int được boxing; với **ToIntFunction<String>**, kết quả là int. **Predicate<String>** yêu cầu boolean, phù hợp phương thức **hasText(String)** trả boolean.

Trong hệ thống lớn, lạm dụng các overload chỉ khác functional interface có thể khiến mã gọi khó đọc; thiết kế tên API rõ ý nghĩa cũng là cách phòng ngừa vấn đề inference.

## 16. Toán tử điều kiện và diamond trong Java 8

### Toán tử điều kiện ba ngôi

Trong ngữ cảnh thích hợp, một **reference conditional expression** có thể nhận kiểu đích, và các nhánh được kiểm tra tương thích với kiểu đó:

~~~java
List<String> selected =
    flag ? Collections.emptyList()
         : Collections.singletonList("ready");
~~~

Đây là đoạn minh họa có biến boolean flag. Kiểu đích List<String> giúp phương thức generic trong hai nhánh được hiểu theo kiểu phần tử mong đợi.

Không nên áp quy tắc này một cách mù quáng cho mọi toán tử điều kiện: **numeric conditional expressions** và **boolean conditional expressions** có quy tắc typing riêng; **reference conditional** mới là nhóm có thể là poly expression trong các ngữ cảnh phù hợp.

### Diamond operator

~~~java
List<String> records = new ArrayList<>();
~~~

Compiler dùng ngữ cảnh để suy luận type argument cho ArrayList. Không cần ghi lặp lại **new ArrayList<String>()**, nhưng điều đó không có nghĩa kiểu generic bị mất ở compile time.

Tránh:

~~~java
// List<String> broken = new ArrayList<Integer>(); // Không hợp lệ.
~~~

**new ArrayList<Integer>()** đã có type argument Integer tường minh; kiểu đích List<String> không có quyền biến Integer thành String. Chỉ có diamond **<>** cho phép compiler suy luận type arguments từ ngữ cảnh theo quy tắc tương ứng.

### Khác biệt với Java 10+ local-variable inference

Trên JDK mới hơn, **var list = new ArrayList<String>()** suy luận kiểu biến dựa vào initializer. **var list = new ArrayList<>()** không có target **List<String>** bên trái để suy luận phần tử String; kiểu phần tử có thể là Object theo những ràng buộc sẵn có.

Đây là khác biệt quan trọng giữa:
- **Type inference của biến cục bộ var**: biến nhận kiểu suy ra từ initializer.
- **Target typing của poly expression**: expression có thể dùng thông tin kiểu được yêu cầu từ ngữ cảnh.

Không nên dùng var chỉ để làm ngắn mọi khai báo generic nếu việc bỏ kiểu đích khiến mã kém rõ nghĩa.

## 17. Chương trình hoàn chỉnh: generic method reference và lời gọi lồng nhau

Tạo tệp **GenericPipelineDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

public class GenericPipelineDemo {

    static <T> T first(T left, T right) {
        return left;
    }

    static <T> List<T> pair(T left, T right) {
        return Arrays.asList(left, right);
    }

    static <T extends CharSequence> int measuredLength(T text) {
        return text.length();
    }

    public static void main(String[] args) {
        BiFunction<String, String, List<String>> pairMaker =
            GenericPipelineDemo::pair;

        BiFunction<String, String, String> firstMaker =
            GenericPipelineDemo::first;

        Function<String, Integer> length =
            GenericPipelineDemo::measuredLength;

        Supplier<List<String>> emptyMaker =
            Collections::<String>emptyList;

        System.out.println("pair: " + pairMaker.apply("L", "R"));
        System.out.println("first: " + firstMaker.apply("L", "R"));
        System.out.println("length: " + length.apply("Java"));
        System.out.println("empty: " + emptyMaker.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericPipelineDemo.java
java GenericPipelineDemo
~~~

Kết quả:

~~~text
pair: [L, R]
first: L
length: 4
empty: []
~~~

Phân tích:

1. **pair(T,T)** là phương thức generic; kiểu đích BiFunction<String,String,List<String>> ràng buộc cả hai đầu vào là String và đầu ra List<String>.
2. **first(T,T)** được dùng với BiFunction<String,String,String>; compiler suy luận T phù hợp.
3. **measuredLength(T extends CharSequence)** nhận String vì String triển khai CharSequence; kết quả int được boxing cho Function<String,Integer>.
4. **Collections::<String>emptyList** dùng type witness tường minh, cho thấy cách chỉ định tham số kiểu ngay trong method reference. Có thể bỏ **<String>** khi compiler có đủ thông tin từ Supplier<List<String>>.
5. Mỗi method reference là biểu thức được kiểm tra ở compile time theo kiểu đích; các phương thức thật chỉ được gọi khi **apply** hoặc **get** được gọi.

## 18. Một số lỗi biên dịch phổ biến và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| **incompatible types: Object is not a functional interface** | Lambda/method reference không có kiểu đích chức năng | Khai báo FunctionalInterface cụ thể |
| **cannot infer type-variable(s)** | Ràng buộc generic từ đối số/kết quả/bounds không khớp hoặc thiếu thông tin | Xem toàn bộ lời gọi, thêm kiểu biến hoặc type witness |
| **bad return type in lambda expression** | Thân lambda trả kiểu không tương thích với SAM | Đọc SAM của target interface và sửa kết quả |
| **no suitable method found** | Không có overload đáp ứng các tham số và ràng buộc | Kiểm tra chữ ký, kiểu đối số và bounds |
| **reference to method is ambiguous** | Nhiều overload phương thức được tham chiếu cùng áp dụng mà compiler không chọn được | Dùng lambda tường minh hoặc chỉ định kiểu mục tiêu |
| **reference to overloaded API is ambiguous** | Nhiều overload nhận functional interface đều khả thi | Tách biến có kiểu tường minh hoặc cast đúng |
| **List<Integer> cannot be converted to List<Number>** | Generic invariance, không tự mở rộng loại phần tử | Dùng List<Number> hoặc wildcard phù hợp |
| **capture of ?** | Kiểu wildcard chưa xác định đủ cho thao tác đang làm | Xét helper generic hoặc ràng buộc extends/super |
| **type argument not within bounds** | Kiểu được chọn không đáp ứng extends/Comparable... | Chọn kiểu đáp ứng bounds hoặc đổi hợp đồng |
| **bad operand types** trong lambda | Đã suy luận sai kiểu tham số hoặc dùng phép toán không phù hợp | Kiểm tra SAM và kiểu thực tế |
| **variable might not have been initialized** | Luật definite assignment độc lập với generic inference | Khởi tạo hợp lệ theo control flow |
| **local variables referenced from a lambda expression must be final or effectively final** | Biến cục bộ bị gán lại khi được lambda bắt giữ | Tránh gán lại biến captured; không “lách” bằng trạng thái mutable khó kiểm soát |

### Cách đọc thông báo compiler hiệu quả

Khi javac báo lỗi inference, hãy tìm theo trình tự:

1. **Phương thức nào đang được gọi?** Nó generic không? Có những type variable nào?
2. **Kiểu các đối số thực tế là gì?** Có lambda, method reference, conditional hay lời gọi generic lồng không?
3. **Formal parameters có wildcard/bounds không?** Những nơi nào phải cùng T, những nơi nào nhận super/subtype?
4. **Kiểu đích là gì?** Kết quả đang gán cho biến, trả về từ phương thức hay truyền vào API khác?
5. **Overload nào được xem xét?** Có hai functional interface gần giống nhau không?
6. **Có thể làm rõ bằng một biến trung gian có kiểu chính xác không?** Cách này thường tốt hơn raw type hay cast không kiểm tra.

**Cẩn trọng:** thêm một cast có thể khiến chương trình biên dịch nhưng mất an toàn kiểu và gây **ClassCastException** khi chạy. Ưu tiên mô hình generic đúng, không dùng **@SuppressWarnings("unchecked")** để che lỗi khi chưa chứng minh được tính an toàn.

## 19. Suy luận kiểu không phải tự động tạo generic ở runtime

Java generics chủ yếu được kiểm tra tại compile time và sử dụng **type erasure** ở runtime. Khi viết **List<String>**, kiểu phần tử String có vai trò quan trọng cho type checking, nhưng JVM không giữ mọi type argument theo cách cho phép kiểm tra **instanceof List<String>** tại runtime.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
// if (names instanceof List<String>) { } // Không hợp lệ.
~~~

Dòng instanceof được comment lại vì Java không cho kiểm tra type argument tham số hóa như vậy. Bạn có thể kiểm tra **instanceof List<?>**, nhưng việc đó chỉ xác nhận cấu trúc là List, không xác nhận từng phần tử là String.

**Poly expression cũng là vấn đề typing tại compile time**, không có nghĩa trình biên dịch tạo hàng loạt object wrapper đặc biệt ở runtime chỉ để duy trì kiểu target. Boxing thực tế có thể xảy ra ở một số điểm, nhưng không phải lúc nào cũng như nhau.

### Type safety và runtime casts

Compiler có thể chèn cast thích hợp sau erasure khi cần, nhưng nếu dùng **raw type** hoặc phép cast không kiểm tra, việc phá vỡ type safety có thể chỉ bộc lộ thành lỗi khi thực thi. Do đó kỹ thuật giải inference tốt nhất là khai báo ràng buộc và kiểu đích rõ ràng, không phải tắt kiểm tra kiểu.

## 20. Những nguyên tắc thiết kế API tổng quát

**Dùng wildcard đúng chỗ:** nếu một API chỉ đọc T từ một nguồn, cân nhắc **? extends T**; nếu chỉ ghi T vào một đích, cân nhắc **? super T**. Đừng làm phức tạp API bằng nhiều type variable nếu chúng không thể hiện một mối liên hệ hữu ích.

**Dùng type parameter khi các vị trí cần ràng buộc với nhau:** một phương thức chuyển đổi dữ liệu phải liên kết T ở đầu vào với R ở đầu ra; một helper copy cần liên kết nguồn và đích qua T. Một chữ ký quá rộng bằng Object có thể làm mất an toàn kiểu và khiến nơi gọi phải ép kiểu.

**Đặt functional interface target cụ thể:** khi API nhận một lambda, kiểu tham số nên mô tả đúng số đối số và kiểu kết quả: Function, Predicate, Supplier, Consumer, Comparator hoặc interface riêng nếu hợp đồng đặc biệt.

**Tránh overload phức tạp dựa hoàn toàn trên lambda:** nếu các overload nhận các SAM rất giống nhau, compiler có thể gặp mơ hồ và người đọc cũng khó đoán. Hãy cân nhắc tên phương thức khác hoặc builder API rõ hơn.

**Không lạm dụng type witness và cast:** phần lớn lời gọi generic hiện đại có thể suy luận đúng; chỉ thêm khai báo tường minh khi muốn tăng khả năng đọc hiểu hoặc giải trường hợp inference không đủ.

**Giữ generic contract sát ngữ nghĩa:** **<T extends Comparable<? super T>>** nói rằng phép so sánh có thể làm trên kiểu tương thích; **<T extends Number>** nói rằng T phải thuộc họ số; **List<? extends T>** nói rằng nguồn tạo các giá trị có thể được đọc như T. Đây là những lời hứa khác nhau, không nên thay nhau chỉ để mã vừa biên dịch.

## 21. Bài tập kiểm tra kiến thức

**Bài 1 — Poly hay standalone?** Với **int x = 10** và **Function<String,Integer> f = String::length**, đâu là trường hợp phụ thuộc vào target functional interface? Đáp án: **String::length**; literal 10 có kiểu int theo quy tắc standalone của nó.

**Bài 2 — Generic return context.** Vì sao **List<String> xs = Collections.emptyList()** hợp lệ? Đáp án: Collections.emptyList là generic method trả List<T> và kiểu đích List<String> góp phần suy luận T = String.

**Bài 3 — Invariance.** Vì sao **List<Number> nums = new ArrayList<Integer>()** không hợp lệ dù Integer extends Number? Đáp án: List<Integer> không phải subtype của List<Number>; nếu phép gán ấy được phép, có thể thêm Double vào danh sách vốn chỉ chứa Integer.

**Bài 4 — Wildcard.** Nếu cần copy phần tử Integer từ List<Integer> vào List<Number>, nên viết tham số nguồn/đích theo hướng nào? Đáp án: **List<? extends T> source**, **List<? super T> destination** với type variable T được liên kết phù hợp.

**Bài 5 — Bounds.** Với **<T extends Comparable<? super T>> T larger(T a,T b)**, kiểu T cần đáp ứng điều gì? Đáp án: T phải so sánh được với T thông qua một Comparable thích hợp; không phải mọi Object đều đủ điều kiện.

**Bài 6 — Lambda trong generic method.** Với **List<Integer> lengths = transform(words, s -> s.length())**, thông tin nào giúp xác định s là String và kết quả là Integer? Đáp án: kiểu phần tử List<String> của words, chữ ký Function<? super T,? extends R> và kiểu đích List<Integer> cùng tham gia suy luận.

**Bài 7 — Overload.** Vì sao đặt **Function<String,Integer> f = String::length** rồi gọi overload **inspect(f)** thường rõ hơn truyền method reference trực tiếp? Đáp án: biến đã có kiểu đích rõ ràng, nên chọn overload nhất quán với hợp đồng chức năng được khai báo.

**Bài 8 — Diamond với var.** Trên JDK mới, **var xs = new ArrayList<>()** có tự biết xs là ArrayList<String> không? Đáp án: không có ràng buộc String từ bên trái; đừng dựa vào var để khôi phục một target type không được viết ra.

**Bài 9 — Method reference generic.** **Supplier<List<String>> s = Collections::<String>emptyList** có tác dụng gì? Đáp án: type witness <String> chỉ định tham số kiểu của generic method được tham chiếu, phù hợp kết quả List<String> mà Supplier yêu cầu.

**Bài 10 — Xử lý lỗi compiler.** Nếu javac báo **cannot infer type-variable(s)**, bạn nên bắt đầu ở đâu? Đáp án: xem chữ ký generic, bounds/wildcards, kiểu thực tế của tất cả đối số và kiểu đích; khai báo một biến trung gian có kiểu chính xác để làm rõ trước khi nghĩ tới raw type/cast.

## Tổng kết

**Poly expression** nhận thông tin kiểu từ một **ngữ cảnh đích**, đặc biệt quan trọng đối với lambda, method reference, lời gọi generic và diamond trong các trường hợp Java cho phép. **Generic type inference** thu thập ràng buộc từ tham số, giá trị trả về kỳ vọng, quan hệ subtype, wildcard và type bounds để tìm kiểu hợp lệ cho các type variable.

Khi đọc đoạn mã Java khó suy luận kiểu, hãy hỏi bốn câu: **(1) Target type là gì? (2) Những type variable nào cần suy luận? (3) Ràng buộc đến từ input, output và bounds là gì? (4) Lambda hoặc method reference phải phù hợp SAM nào?**

Trả lời được bốn câu đó sẽ giúp bạn hiểu các API Java hiện đại, tránh raw type, dùng wildcard đúng vai trò và giải các lỗi compile-time một cách có cơ sở.