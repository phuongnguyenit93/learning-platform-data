# Giữ API generic dễ dùng mà không làm lỗi thông báo khó hiểu trong Java

## Mục tiêu học tập

Một API generic tốt cho phép người gọi dùng các kiểu dữ liệu khác nhau mà vẫn được trình biên dịch kiểm tra an toàn. Nhưng nếu chữ ký có quá nhiều biến kiểu, wildcard không đúng chỗ hoặc overload khó phân biệt, người sử dụng có thể gặp những thông báo như **cannot infer type-variable(s)**, **incompatible bounds** hay **reference to method is ambiguous** mà rất khó biết phải sửa ở đâu.

Trong Java hiện đại, mục tiêu không phải là làm cho trình biên dịch “suy luận mọi thứ bằng mọi giá”, mà là **thiết kế hợp đồng generic đủ rõ để cách gọi thông thường ngắn, đúng kiểu, dễ đọc và dễ chẩn đoán khi sai**.

Bài học thuộc chủ đề *Suy luận kiểu* của Java 8, tập trung vào:

- Thiết kế các **type parameter** thực sự thể hiện mối quan hệ giữa đầu vào và đầu ra.
- Chọn **wildcard** theo vai trò producer/consumer, tránh làm người gọi phải ép kiểu không an toàn.
- Tận dụng **target typing**, **diamond** và khả năng suy luận với lambda/method reference.
- Giảm overload chỉ khác functional interface, vì đây là nguồn báo lỗi mơ hồ.
- Đọc thông báo javac theo từng ràng buộc: tham số kiểu, giới hạn kiểu, kiểu kết quả và vị trí lỗi.
- Tách **lỗi kiểu khi biên dịch** khỏi **lỗi giá trị khi chạy**, để API có thể đưa thông báo nghiệp vụ hữu ích.
- Xây một quy trình kiểm thử các cách gọi API, gồm cả trường hợp hợp lệ và trường hợp cố ý sai.

Những quy tắc này vẫn được sử dụng trên JDK 17+, 21+ và những phiên bản Java hiện đại khác. Các chương trình đầy đủ trong bài chỉ dùng API đã có từ Java 8, nên có thể chạy với JDK 8 trở lên.

## 1. “Dễ dùng” đối với một API generic nghĩa là gì?

Một API generic được coi là dễ dùng khi người gọi có thể xác định nhanh **nó nhận gì, trả gì và những kiểu nào có thể phối hợp với nhau**. Đồng thời, lời gọi hợp lệ nên được viết tự nhiên mà không cần raw type hoặc một chuỗi ép kiểu phức tạp.

Hãy so sánh một API dùng kiểu quá rộng:

~~~java
static Object convert(Object value, java.util.function.Function mapper) {
    return mapper.apply(value);
}
~~~

Đây là **phương thức minh họa**, không phải chương trình độc lập. Nó dùng raw **Function** và kiểu **Object** ở nhiều nơi. Người gọi có thể phải ép kiểu kết quả, và một số lỗi chỉ xuất hiện khi chạy. Kiểu đầu vào, kiểu đầu ra và quan hệ giữa chúng không được mô tả đầy đủ.

Một cách diễn đạt tốt hơn:

~~~java
static <T, R> R convert(
        T value,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}
~~~

Chữ ký thứ hai nói rõ: nhận giá trị kiểu T, gọi một function tiêu thụ được T, trả một giá trị tương thích R. Cách viết thường dùng:

~~~java
String result = convert(42, number -> "ID-" + number);
~~~

Đây là đoạn minh họa đặt trong phương thức/lớp có định nghĩa convert. Java có thể suy luận T phù hợp Integer do boxing số 42, đồng thời R phù hợp String nhờ thân lambda và ngữ cảnh gán.

**Lưu ý:** số type parameter không phải thước đo chất lượng. Có hai biến kiểu T và R ở đây vì **đầu vào và đầu ra có thể khác kiểu**. Nếu không có mối quan hệ kiểu cần diễn đạt, thêm nhiều biến kiểu chỉ khiến chữ ký và lỗi biên dịch phức tạp hơn.

## 2. Bắt đầu thiết kế từ hợp đồng dữ liệu

Trước khi viết **<T, R, K>**, hãy trả lời:

1. Tham số nào là **nguồn cung cấp dữ liệu**?
2. Tham số nào là **đích nhận dữ liệu**?
3. Những vị trí nào **bắt buộc có cùng kiểu** và những vị trí nào chỉ cần kiểu cha/con tương thích?
4. Kiểu nào được **trả về** cho bên gọi?
5. Có giới hạn thật sự như **Number**, **Comparable**, một interface nghiệp vụ hay không?
6. Người gọi thường dùng lambda, method reference hoặc collection kiểu gì?

Một type parameter có tác dụng lớn nhất khi nó liên kết **ít nhất hai vị trí có mối quan hệ kiểu**. Ví dụ:

~~~java
static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
~~~

T nối kiểu phần tử trong List với kiểu trả về. Người gọi nhận String từ List<String> mà không cần cast:

~~~java
String name = first(java.util.Arrays.asList("An", "Binh"));
~~~

Một trường hợp ngược lại:

~~~java
static <T> void log(T value) {
    System.out.println(value);
}
~~~

Đây cũng là mã generic hợp lệ, nhưng nếu phương thức chỉ in **toString()** và không cần giữ quan hệ kiểu với vị trí nào khác, tham số **Object** có thể đơn giản và rõ nghĩa tương đương:

~~~java
static void log(Object value) {
    System.out.println(value);
}
~~~

Điều này không có nghĩa “type parameter chỉ xuất hiện một lần luôn sai”: có những hợp đồng và API cần giới hạn kiểu ngay trên một tham số. Đây là một **câu hỏi thiết kế**, không phải quy tắc máy móc.

## 3. Suy luận kiểu nhìn vào cả đối số và kiểu đích

Xem một phương thức generic:

~~~java
static <T> java.util.List<T> singleton(T value) {
    return java.util.Collections.singletonList(value);
}
~~~

Lời gọi:

~~~java
java.util.List<Number> numbers = singleton(7);
~~~

Java không đơn giản lấy T là Integer rồi kết thúc. Trình biên dịch giải ràng buộc từ **đối số 7** (có thể boxing thành Integer) và từ **ngữ cảnh List<Number>** để tìm một T tương thích với toàn bộ lời gọi. Trong ngữ cảnh này phép gán hợp lệ.

Ngược lại, nếu kiểu đích không tương thích:

~~~java
// java.util.List<String> invalid = singleton(7);
~~~

thì đây là lỗi kiểu: Java không tự biến giá trị số 7 thành String chỉ vì vế trái muốn List<String>. Thêm ép kiểu không kiểm tra có thể khiến lỗi chuyển sang runtime, không cải thiện thiết kế.

### Poly expression giúp giảm lặp type argument

Ví dụ quen thuộc:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List<String> empty = java.util.Collections.emptyList();
~~~

**new ArrayList<>()** dùng diamond, còn **Collections.emptyList()** là lời gọi phương thức generic. Cả hai có thể nhận thông tin từ kiểu đích List<String> trong những ngữ cảnh Java cho phép. Người gọi không cần viết lặp **new ArrayList<String>()** hoặc **Collections.<String>emptyList()** trừ khi muốn làm rõ kiểu.

Với lambda:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Functional interface cung cấp kiểu tham số String và kết quả Integer. Lambda không tự có một “kiểu hàm” độc lập để gán cho Object. Đây là lý do chữ ký generic của API nhận callback nên đủ rõ, thay vì dựa vào Object hay raw Function.

**Giới hạn của target typing:** không phải mọi expression đều là poly expression; không phải mọi generic method đều suy luận được mọi tổ hợp kiểu. Khi compiler báo lỗi, hãy đối chiếu **toàn bộ ràng buộc**, không đoán rằng mọi thông tin đều phải đến từ vế trái.

## 4. Khai báo biến kiểu đúng quan hệ, không ép đầu vào phải giống nhau vô ích

Giả sử bạn thiết kế API biến đổi một danh sách:

~~~java
static <T, R> java.util.List<R> mapCopy(
        java.util.List<T> source,
        java.util.function.Function<T, R> mapper) {
    java.util.List<R> result = new java.util.ArrayList<>();
    for (T value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
~~~

Chữ ký này đã tốt hơn raw type: T là phần tử đầu vào, R là kết quả. Tuy nhiên, nếu nguồn là một collection của subtype hoặc mapper được định nghĩa nhận một supertype, chữ ký chặt có thể gây cản trở không cần thiết.

Một phiên bản linh hoạt hơn:

~~~java
static <T, R> java.util.List<R> mapCopy(
        Iterable<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    java.util.List<R> result = new java.util.ArrayList<>();
    for (T value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
~~~

Đây là phương thức minh họa cần đặt trong lớp thích hợp. Phân tích:

- **Iterable<? extends T>** cho phép một nguồn có phần tử thuộc T hoặc subtype của T, vì API chỉ **đọc** dữ liệu từ nguồn.
- **Function<? super T, ? extends R>** nhận được T và có thể trả R hoặc subtype của R.
- **List<R>** cho người gọi biết chính xác kiểu phần tử kết quả; không cần trả List<Object> rồi cast.
- Không sử dụng wildcard cho kiểu kết quả List<R> nếu không có yêu cầu đặc biệt, bởi việc trả **List<? extends R>** thường khiến bên gọi khó sử dụng hơn.

Đây là cách cân bằng: khai báo linh hoạt ở **đầu vào**, kết quả rõ ràng ở **đầu ra**.

## 5. PECS và những wildcard thực sự cần thiết

Một quy tắc hữu ích khi thiết kế API generic là **PECS: Producer Extends, Consumer Super**.

| Vai trò | Kiểu tham số thường phù hợp | Thao tác chính |
| --- | --- | --- |
| Nguồn cung cấp T | **? extends T** | Đọc phần tử như T |
| Đích nhận T | **? super T** | Thêm phần tử T |
| Vừa đọc vừa sửa với cùng kiểu chính xác | **T** cụ thể | Phụ thuộc hợp đồng |

Ví dụ copy số nguyên từ một collection vào collection rộng hơn:

~~~java
static <T> void copyTo(
        java.util.Collection<? super T> destination,
        java.lang.Iterable<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

Có thể gọi:

~~~java
java.util.List<Number> numbers = new java.util.ArrayList<>();
copyTo(numbers, java.util.Arrays.asList(1, 2, 3));
~~~

Compiler tìm kiểu T phù hợp để nguồn Integer cung cấp cho đích Number. Không cần ép **List<Integer>** sang **List<Number>**.

### Invariance: chỗ mà API dễ khiến người dùng khó hiểu

Một ví dụ không hợp lệ:

~~~java
// List<Number> list = new ArrayList<Integer>();
~~~

Java generics **invariant**: List<Integer> không phải subtype của List<Number>, dù Integer là subtype của Number. Nếu phép gán này hợp lệ, bạn có thể thêm Double vào danh sách thật ra chỉ dành cho Integer.

Nếu một API chỉ đọc các giá trị Number, dùng **List<? extends Number>** có thể phù hợp. Nếu API cần thêm Integer vào đích, **Collection<? super Integer>** thường đúng hơn. Nhưng đừng dùng wildcard chỉ để “chữa” mọi lỗi: nếu hợp đồng thực sự cần danh sách đồng nhất T ở cả đầu vào và đầu ra, một type parameter T nhất quán có thể rõ ràng hơn.

### Không trả wildcard tùy tiện

Hãy so sánh:

~~~java
static <T> java.util.List<T> distinctCopy(
        java.util.Collection<? extends T> input) {
    return new java.util.ArrayList<>(
        new java.util.LinkedHashSet<T>(input));
}
~~~

với một API trả **List<? extends T>** khi không cần thiết. Phiên bản trả List<T> giúp người gọi thao tác với kết quả theo kiểu T đã chọn. Đây là đoạn minh họa về chữ ký, chưa phải chương trình đầy đủ. Lựa chọn trả List<T> chỉ đúng nếu implementation thật sự có thể bảo đảm danh sách chứa các phần tử được đọc như T.

## 6. Chương trình hoàn chỉnh: API mapCopy dễ suy luận và dễ sử dụng

Tạo tệp **FriendlyGenericApiDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class FriendlyGenericApiDemo {

    static <T, R> List<R> mapCopy(
            Iterable<? extends T> items,
            Function<? super T, ? extends R> mapper) {

        Objects.requireNonNull(items, "items");
        Objects.requireNonNull(mapper, "mapper");

        List<R> result = new ArrayList<>();
        for (T item : items) {
            result.add(mapper.apply(item));
        }
        return Collections.unmodifiableList(result);
    }

    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi");

        List<Integer> lengths = mapCopy(names, String::length);
        List<String> uppercase = mapCopy(names, String::toUpperCase);
        List<CharSequence> labels = mapCopy(
            names, name -> "[" + name + "]");

        System.out.println("Độ dài: " + lengths);
        System.out.println("Chữ hoa: " + uppercase);
        System.out.println("Nhãn: " + labels);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FriendlyGenericApiDemo.java
java FriendlyGenericApiDemo
~~~

Kết quả:

~~~text
Độ dài: [2, 4, 3]
Chữ hoa: [AN, BINH, CHI]
Nhãn: [[An], [Binh], [Chi]]
~~~

Các điểm đáng học:

1. Người gọi không cần viết **FriendlyGenericApiDemo.<String,Integer>mapCopy(...)**; compiler suy luận dựa trên nguồn String, callback và kiểu kết quả mong đợi.
2. **String::length** trả int, nhưng với Function trả kiểu generic R, kết quả có thể boxing thành Integer.
3. Cùng một API chuyển danh sách String thành List<Integer>, List<String> hoặc List<CharSequence>.
4. Chữ ký của mapper cho phép một function tiêu thụ **supertype của T** và trả **subtype của R** nếu tương thích.
5. Hàm **trả một danh sách mới không cho sửa cấu trúc** qua Collections.unmodifiableList. Đây là bản sao cấu trúc danh sách; nếu phần tử R là mutable, phần tử không tự trở thành bất biến.

**Thông điệp thiết kế:** thuận tiện nhất là một chữ ký thật sự mô tả quan hệ dữ liệu. Suy luận kiểu hoạt động tốt hơn khi lời hứa của API rõ và nhất quán, không cần che lỗi bằng kiểu Object.

## 7. Type bounds nên diễn đạt năng lực cần thiết

Nếu một thuật toán cần so sánh hai đối tượng với nhau, khai báo chung **<T>** là chưa đủ để gọi compareTo. Một ràng buộc phổ biến:

~~~java
static <T extends Comparable<? super T>> T greatest(
        java.util.List<? extends T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }

    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
~~~

Đây là phương thức minh họa cần đặt trong một lớp. **Comparable<? super T>** linh hoạt hơn **Comparable<T>** khi kiểu T có thể so sánh thông qua một supertype. Giới hạn này đúng với yêu cầu thuật toán, không phải một ràng buộc “thêm cho chắc”.

### Không dùng upper bound vô cớ

Ví dụ:

~~~java
static <T extends Number> java.util.List<T> copyNumbers(
        java.util.Collection<? extends T> input) {
    return new java.util.ArrayList<>(input);
}
~~~

Nếu implementation chỉ copy phần tử, nó không gọi hành vi nào của Number. Khi API không có yêu cầu phải nhận **chỉ các số**, bound **extends Number** có thể hạn chế người sử dụng vô ích. Một chữ ký tổng quát hơn là **<T> List<T> copy(Collection<? extends T>)**.

Ngược lại, nếu thuật toán thực sự cần **doubleValue()** hoặc thuộc tính do Number bảo đảm, bound Number truyền đạt đúng hợp đồng.

### Suy luận không thể vượt type bounds

Nếu phương thức yêu cầu **T extends Number**, một lời gọi với String sẽ không hợp lệ chỉ vì nơi nhận kết quả khai báo Object. Java phải thỏa **đồng thời** ràng buộc từ input, output và khai báo generic. Khi javac báo **incompatible bounds**, hãy kiểm tra xem API có đặt bound quá chặt so với điều nó thực sự làm hay không.

## 8. Chương trình hoàn chỉnh: bounds và collection linh hoạt

Tạo tệp **GenericBoundsAndCopyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

public class GenericBoundsAndCopyDemo {

    static <T> void copyTo(
            Collection<? super T> destination,
            Iterable<? extends T> source) {

        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");

        for (T item : source) {
            destination.add(item);
        }
    }

    static <T extends Comparable<? super T>> T greatest(
            List<? extends T> values) {

        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }

        T best = values.get(0);
        for (T item : values) {
            if (item.compareTo(best) > 0) {
                best = item;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Number> target = new ArrayList<>();
        copyTo(target, Arrays.asList(2, 4, 6));

        String lastAlphabetically =
            greatest(Arrays.asList("apple", "pear", "fig"));

        System.out.println("Số: " + target);
        System.out.println("Lớn nhất theo chữ: " +
            lastAlphabetically);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericBoundsAndCopyDemo.java
java GenericBoundsAndCopyDemo
~~~

Kết quả:

~~~text
Số: [2, 4, 6]
Lớn nhất theo chữ: pear
~~~

**Giải thích:** copyTo liên kết nguồn Integer với đích Number an toàn, trong khi greatest chỉ chấp nhận các phần tử đáp ứng quan hệ Comparable cần thiết. Một API có type bounds phù hợp giúp phát hiện dữ liệu không thể so sánh **ngay lúc biên dịch**. Nó không cần bỏ generic chỉ để cho người dùng đi qua lỗi.

Phương thức greatest cũng kiểm tra danh sách rỗng ở **runtime** vì đó là điều kiện về **giá trị**, không phải lỗi mà generic inference có thể biết chắc từ kiểu List<T>.

## 9. Đừng tạo overload mơ hồ chỉ để nhận nhiều kiểu lambda

Lambda và method reference phụ thuộc vào **functional interface target**. Nếu một API có nhiều overload nhận các interface có chữ ký gần giống, người gọi có thể khó biết overload nào được chọn.

Ví dụ phác thảo:

~~~java
static String evaluate(
        String input,
        java.util.function.Function<String, Integer> function) {
    return "boxed=" + function.apply(input);
}

static String evaluate(
        String input,
        java.util.function.ToIntFunction<String> function) {
    return "primitive=" + function.applyAsInt(input);
}
~~~

Đây là **hai phương thức minh họa** cần đặt trong cùng lớp; chúng hợp lệ vì hai loại tham số functional interface khác nhau sau erasure. Với một lambda/method reference ngắn, compiler phải xét cách chọn overload. Một số trường hợp có thể ambiguous, và người đọc mã có thể không đoán được ý định.

### Cách thiết kế thường rõ hơn

Khi hai thao tác có ý nghĩa nghiệp vụ khác nhau, hãy dùng **tên khác nhau**:

~~~java
static String evaluateBoxed(
        String value,
        java.util.function.Function<String, Integer> fn) {
    return "boxed=" + fn.apply(value);
}

static String evaluatePrimitive(
        String value,
        java.util.function.ToIntFunction<String> fn) {
    return "primitive=" + fn.applyAsInt(value);
}
~~~

Nếu hai overload là chủ đích của thư viện và không thể đổi, bên gọi có thể chỉ định kiểu rõ:

~~~java
java.util.function.Function<String, Integer> boxed =
    String::length;

java.util.function.ToIntFunction<String> primitive =
    String::length;
~~~

Sau đó truyền **boxed** hoặc **primitive** vào phương thức tương ứng. Đây là các đoạn minh họa; xem chương trình hoàn chỉnh sau.

**Không khẳng định mọi overload nhận lambda đều ambiguous.** Java có những quy tắc chọn overload dựa trên tính áp dụng và tính cụ thể hơn. Tuy nhiên, tránh nhiều overload có thể sử dụng cùng một lambda là một **nguyên tắc API ergonomics** hữu ích vì giúp cả người lẫn compiler có ít lựa chọn khó phân biệt hơn.

### Đặc biệt cẩn thận với quá nhiều tham số type variable

Các overload khác nhau chỉ ở **List<String>** và **List<Integer>** không thể được khai báo như hai phương thức tách biệt với cùng tên và cùng số tham số do **type erasure**: chúng có cùng chữ ký sau xóa kiểu. Đừng thiết kế API dựa trên ý tưởng “để overload phân biệt generic type argument lúc chạy”. Hãy chọn tên hoặc hình dạng tham số khác, hay gom chức năng vào một phương thức generic an toàn.

## 10. Chương trình hoàn chỉnh: chọn overload bằng kiểu rõ ràng

Tạo tệp **GenericOverloadClarityDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class GenericOverloadClarityDemo {

    static String evaluate(
            String input,
            Function<String, Integer> mapper) {
        return "Function: " + mapper.apply(input);
    }

    static String evaluate(
            String input,
            ToIntFunction<String> mapper) {
        return "ToIntFunction: " + mapper.applyAsInt(input);
    }

    static String evaluateInt(
            String input,
            ToIntFunction<String> mapper) {
        return "Named API: " + mapper.applyAsInt(input);
    }

    public static void main(String[] args) {
        Function<String, Integer> boxed = String::length;
        ToIntFunction<String> primitive = String::length;

        System.out.println(evaluate("Java", boxed));
        System.out.println(evaluate("Java", primitive));
        System.out.println(evaluateInt("Java", String::length));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericOverloadClarityDemo.java
java GenericOverloadClarityDemo
~~~

Kết quả:

~~~text
Function: 4
ToIntFunction: 4
Named API: 4
~~~

Hai biến **boxed** và **primitive** là cách đơn giản để bộc lộ kiểu đích. Phiên bản **evaluateInt** cho thấy một tên API khác biệt có thể làm lời gọi **String::length** trực tiếp dễ đọc hơn. Trong thư viện công khai, chọn tên và chữ ký rõ thường mang lại lợi ích lớn hơn việc tiết kiệm vài ký tự trong khai báo.

## 11. Tham số kiểu nào nên đặt trên lớp, tham số nào nên đặt trên method?

Nếu một đối tượng luôn làm việc với một loại dữ liệu thống nhất trong suốt vòng đời, generic ở **lớp** thường phù hợp:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Nhưng một hàm chuyển đổi tổng quát có kiểu đầu ra thay đổi ở mỗi lời gọi có thể nên khai báo type variable **ở phương thức**:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    <R> R map(java.util.function.Function<? super T, ? extends R> f) {
        return f.apply(value);
    }
}
~~~

Hai đoạn trên là **hai phiên bản minh họa thay thế**, không khai báo đồng thời hai class Box trong cùng tệp. Với phiên bản thứ hai, **T** thuộc lớp Box, còn **R** thuộc phương thức map: mỗi lời gọi map có thể trả loại khác nhau.

Nếu đặt cả T và R lên class dù R chỉ xuất hiện ở một method, bạn có thể buộc người dùng phải mang thêm type argument khắp nơi mà không đem lại lợi ích. Ngược lại, nếu T là trạng thái/chính sách xuyên suốt đối tượng, khai báo T ở lớp giúp tránh viết lại và làm rõ hợp đồng.

## 12. Vì sao compiler thường báo lỗi generic khó đọc?

Khi kiểm tra lời gọi, javac không chỉ kiểm tra một phép gán T. Nó phải tổng hợp nhiều **constraint** từ:

- Kiểu của tất cả đối số.
- Type variable và upper/lower bounds liên quan.
- Quan hệ subtype và generic invariance.
- Wildcard, capture conversion và các giới hạn.
- Functional interface target cho lambda/method reference.
- Kiểu kết quả mà ngữ cảnh đang yêu cầu.
- Tập các overload có thể áp dụng.

Khi các ràng buộc mâu thuẫn, thông báo của compiler thường mô tả **những biến kiểu nó không thể suy luận**, chứ không giải thích trực tiếp theo ngôn ngữ nghiệp vụ. Nội dung chính xác của thông báo cũng có thể khác giữa các phiên bản javac, tùy đoạn mã và tùy thiết lập build.

Ví dụ lỗi:

~~~java
// List<Number> wrong = new ArrayList<Integer>();
~~~

Vấn đề không phải thiếu một cast mà là **invariance**. Compiler không cho List<Integer> gán thẳng sang List<Number>. Sửa đúng có thể là **new ArrayList<Number>()**, hoặc thay chữ ký nơi nhận thành wildcard nếu chỉ cần đọc dữ liệu Number.

Một ví dụ khác:

~~~java
// ToIntFunction<String> wrong = value -> value.toUpperCase();
~~~

Thân lambda trả String, trong khi SAM **applyAsInt(String)** yêu cầu int. Nếu muốn độ dài, dùng **String::length**; nếu muốn chuỗi hoa, dùng **Function<String,String>**. Cần sửa hợp đồng hoặc biểu thức, không phải ép String sang int.

**Quan điểm thực hành:** thông báo kiểu generic là manh mối để tìm constraint mâu thuẫn; đừng vội tắt type checking.

## 13. Quy trình giải lỗi “cannot infer type-variable(s)”

Khi gặp lỗi suy luận kiểu trong một lời gọi dài, hãy thử theo thứ tự:

**Bước 1: Viết lại chữ ký phương thức.** Tìm tất cả **T**, **R**, **K**, wildcard và bounds. Phân biệt type variable của class với type variable của method.

**Bước 2: Ghi kiểu thật của từng đối số.** Ví dụ một danh sách là **List<Integer>** chứ không phải chỉ “danh sách số”, và một callback nhận **Number** có thể tiêu thụ Integer hay không?

**Bước 3: Ghi kiểu đích của kết quả.** Kết quả được gán cho **List<Number>**, **List<String>** hay đi thẳng vào một method khác? Thông tin này có thể tác động đến inference của poly expression.

**Bước 4: Kiểm tra quan hệ subtype và invariance.** **Integer <: Number** đúng, nhưng **List<Integer> <: List<Number>** không đúng.

**Bước 5: Kiểm tra SAM của lambda/method reference.** Số tham số, kiểu tham số, kiểu trả về, checked exception và overload của phương thức được tham chiếu có phù hợp không?

**Bước 6: Tách lời gọi thành biến trung gian có kiểu rõ ràng.** Đây là công cụ chẩn đoán, không phải lúc nào cũng là thay đổi cuối cùng. Nếu lỗi chuyển sang một dòng nhỏ, bạn đã khoanh vùng được constraint.

**Bước 7: Xem lại thiết kế API.** Nếu mọi người dùng đều phải thêm cast hoặc explicit type arguments, có thể chữ ký đang quá chặt, quá rộng hoặc overload gây khó hiểu.

**Bước 8: Chỉ dùng explicit type witness khi thực sự có ích.** Cú pháp **SomeClass.<String>method(...)** hoặc **SomeClass::<String>method** có thể làm rõ type argument của generic method. Nhưng type witness không biến một lời gọi sai hợp đồng thành đúng.

### Mẫu kiểm tra lỗi từng lớp

Giả sử có lời gọi:

~~~java
List<Integer> result = mapCopy(
    names,
    String::length
);
~~~

Nếu compiler không suy luận được, hãy thử:

~~~java
java.util.function.Function<String, Integer> length =
    String::length;

List<Integer> result = mapCopy(names, length);
~~~

Hai đoạn là **minh họa thay thế**, cần có khai báo names và mapCopy. Nếu phiên bản với biến trung gian hoạt động, điều đó cho biết việc chỉ định SAM rõ hơn giúp compiler và người đọc. Nếu vẫn thất bại, kiểm tra chính chữ ký mapCopy hoặc kiểu names, thay vì liên tục ép kiểu ở nơi gọi.

## 14. Checked exception, null và validation: hai tầng lỗi khác nhau

**Generic type error** là lỗi compiler phát hiện từ chữ ký kiểu. Thư viện không thể tự viết lại mọi thông báo kiểu của javac thành câu tiếng Việt nghiệp vụ chỉ bằng việc ném một exception trong thân phương thức, vì compiler không thể chạy thân phương thức trước khi biên dịch thành công.

**Validation error** là lỗi phát hiện khi chương trình đã chạy, chẳng hạn null, danh sách rỗng, key trùng hoặc dữ liệu không hợp lệ. Với loại này, API **có thể** cung cấp thông báo chính xác.

Vì vậy một API chất lượng nên có cả hai:

- **Chữ ký generic rõ** để lỗi kiểu bị chặn ở compile time.
- **Kiểm tra dữ liệu cụ thể** để lỗi runtime có thông báo nêu tên tham số, giá trị hoặc điều kiện vi phạm.

Ví dụ kiểm tra null:

~~~java
java.util.Objects.requireNonNull(source, "source must not be null");
java.util.Objects.requireNonNull(mapper, "mapper must not be null");
~~~

Đây là hai dòng minh họa trong thân phương thức có biến tương ứng. Một lỗi khác là danh sách rỗng, có thể dùng:

~~~java
if (values.isEmpty()) {
    throw new IllegalArgumentException("values must not be empty");
}
~~~

**Không dùng exception tùy tiện** chỉ vì người dùng “không hiểu compiler”: lỗi compile-time và lỗi runtime ở hai tầng khác nhau, phải sửa đúng tầng.

### Tài liệu hợp đồng cũng là một phần của khả năng sử dụng

Khi viết API công khai, nên ghi rõ:

- Tham số nào không được null?
- Danh sách rỗng có hợp lệ không?
- Callback có được trả null không?
- Kết quả có sửa được không?
- Có thể có key trùng không?
- Có giữ thứ tự đầu vào không?
- Có thể có checked exception nào được khai báo không?
- Khi nào API gọi callback, có thể gọi lại nhiều lần không?

Đây là những điều compiler không thể suy luận từ generic signature một cách đầy đủ.

## 15. Chương trình hoàn chỉnh: generic signature rõ và lỗi runtime hữu ích

Ví dụ tạo bản đồ tra cứu theo khóa. Người gọi cung cấp danh sách các giá trị cùng function trích khóa. Nếu hai giá trị có cùng khóa, chương trình từ chối thay vì âm thầm ghi đè.

Tạo tệp **GenericIndexApiDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class GenericIndexApiDemo {

    static <K, V> Map<K, V> indexBy(
            Iterable<? extends V> items,
            Function<? super V, ? extends K> keyExtractor) {

        Objects.requireNonNull(items, "items must not be null");
        Objects.requireNonNull(
            keyExtractor, "keyExtractor must not be null");

        Map<K, V> result = new LinkedHashMap<>();
        for (V value : items) {
            K key = Objects.requireNonNull(
                keyExtractor.apply(value),
                "keyExtractor must not return null");

            if (result.containsKey(key)) {
                throw new IllegalArgumentException(
                    "Duplicate key: " + key);
            }
            result.put(key, value);
        }
        return Collections.unmodifiableMap(result);
    }

    public static void main(String[] args) {
        Map<String, String> good = indexBy(
            Arrays.asList("a-1", "b-2"),
            value -> value.substring(0, 1));

        System.out.println("Hợp lệ: " + good);

        try {
            indexBy(
                Arrays.asList("x-1", "x-2"),
                value -> value.substring(0, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericIndexApiDemo.java
java GenericIndexApiDemo
~~~

Kết quả:

~~~text
Hợp lệ: {a=a-1, b=b-2}
Lỗi: Duplicate key: x
~~~

Phân tích:

1. **V** là kiểu phần tử dữ liệu, **K** là kiểu khóa. Chữ ký trả **Map<K,V>** giúp bên gọi biết rõ hợp đồng.
2. **Iterable<? extends V>** là nguồn dữ liệu, **Function<? super V,? extends K>** là phép trích khóa; compiler suy luận được K và V từ danh sách, lambda và kiểu kết quả.
3. **LinkedHashMap** duy trì thứ tự chèn để kết quả ví dụ dễ dự đoán.
4. Với hai khóa "x", API ném **IllegalArgumentException("Duplicate key: x")**, rõ hơn việc chỉ trả một map đã mất dữ liệu.
5. **Collections.unmodifiableMap** ngăn sửa cấu trúc map thông qua tham chiếu trả về. Nó không tự biến mọi đối tượng khóa/giá trị thành immutable nếu các đối tượng ấy vốn mutable.
6. **Objects.requireNonNull** xử lý lỗi đầu vào và kết quả keyExtractor. Đây là kiểm tra runtime; không thay thế type checking.

Khi thiết kế lỗi, thông điệp như **"Duplicate key: x"** có thể hữu ích hơn câu chung chung **"invalid argument"**, nhưng tránh vô tình in thông tin nhạy cảm trong exception/log của hệ thống thật.

## 16. Một vài quyết định thiết kế rất dễ tạo API khó dùng

| Mẫu thiết kế | Vì sao dễ gây khó hiểu | Cách cải thiện |
| --- | --- | --- |
| Trả **Object** dù kết quả có quan hệ với đầu vào | Người gọi phải cast | Dùng **<T> T** hoặc **<T,R> R** thích hợp |
| Nhận **raw List** hoặc **raw Function** | Mất kiểm tra type argument | Khai báo generic đầy đủ |
| Dùng **List<T>** cho tham số chỉ đọc | Từ chối nhiều collection subtype | Cân nhắc **List<? extends T>** |
| Dùng **Collection<T>** cho đích chỉ nhận thêm | Có thể chặn đích supertype | Cân nhắc **Collection<? super T>** |
| Trả **List<? extends T>** dù có thể trả **List<T>** | Người gọi khó thao tác kết quả | Trả kiểu kết quả cụ thể nhất mà API bảo đảm |
| Thêm **extends Number** dù không cần thao tác Number | Giới hạn sai mục đích | Bỏ bound nếu hợp đồng thật sự chung |
| Dùng nhiều overload nhận SAM có hình dạng giống nhau | Có thể mơ hồ khi gọi với lambda | Dùng tên khác hoặc biến đích rõ |
| Tạo nhiều type variable không có quan hệ thực | Chữ ký dài và thông báo lỗi khó đọc | Chỉ giữ biến cần thiết |
| Dùng unchecked cast để “sửa” inference | Dời lỗi sang runtime | Sửa ràng buộc kiểu hoặc API |
| Không kiểm tra null ở đầu vào quan trọng | Lỗi xảy ra sâu trong implementation | Kiểm tra sớm với thông báo rõ |
| Không nói rõ hành vi dữ liệu trùng | Có thể mất dữ liệu âm thầm | Đặt chính sách và ngoại lệ rõ |
| Trả collection unmodifiable mà không ghi hợp đồng | Người gọi bất ngờ khi sửa | Tài liệu hóa và đặt tên phù hợp |
| Nhầm **var** với generic target typing | Thiếu ngữ cảnh phần tử mong muốn | Dùng type cụ thể khi giúp suy luận rõ hơn |

### Không lạm dụng builder hoặc factory nếu chỉ cần một phương thức đơn giản

Một builder có thể giúp API chứa nhiều tùy chọn dễ gọi hơn một constructor dài hoặc nhiều overload khó hiểu. Tuy nhiên, một hoạt động như **mapCopy(source, mapper)** chỉ có hai thành phần rõ ràng thì thường không cần thêm builder phức tạp. Sự dễ dùng không đồng nghĩa tăng số lượng lớp trung gian.

### Không phụ thuộc vào tên type variable để compiler hiểu

Đổi T thành ElementType có thể giúp người đọc, nhưng không đổi quy tắc generic inference của Java. Compiler dựa trên **vị trí, quan hệ subtype, wildcard, bounds và kiểu đích**, không dựa vào ý nghĩa tên biến kiểu.

## 17. Viết tài liệu API để người dùng không phải đoán

Một bản JavaDoc tốt cho phương thức generic nên mô tả **quan hệ kiểu** cùng với hành vi:

~~~java
/**
 * Tạo danh sách kết quả bằng cách áp dụng mapper cho từng phần tử.
 *
 * @param <T> kiểu phần tử nguồn đọc được
 * @param <R> kiểu phần tử kết quả
 * @param source nguồn dữ liệu, không được null
 * @param mapper phép biến đổi, không được null
 * @return danh sách kết quả mới, không sửa được về cấu trúc
 * @throws NullPointerException nếu source hoặc mapper là null
 */
static <T, R> java.util.List<R> mapCopy(
        Iterable<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    java.util.List<R> result = new java.util.ArrayList<>();
    for (T item : java.util.Objects.requireNonNull(source)) {
        result.add(java.util.Objects.requireNonNull(mapper).apply(item));
    }
    return java.util.Collections.unmodifiableList(result);
}
~~~

Đây là đoạn **minh họa tài liệu và chữ ký**, không phải phiên bản được khuyến nghị thay cho chương trình mapCopy ở trên. Nếu dùng trong thư viện, nên kiểm tra null mapper ngay đầu phương thức thay vì kiểm tra lặp trong vòng lặp; cũng cần định nghĩa hành vi khi mapper trả null.

Lời mô tả **không sửa được về cấu trúc** chính xác hơn nói “mọi phần tử bất biến”, vì unmodifiable list chỉ ngăn thao tác thay đổi danh sách qua wrapper; nó không làm deep copy các phần tử mutable.

Đừng viết JavaDoc trái với implementation. Ví dụ nếu API ghi nhận key trùng bằng cách giữ bản cuối, không được tài liệu hóa rằng API luôn ném IllegalArgumentException.

## 18. Kiểm thử khả năng dùng của API generic

Đừng chỉ kiểm tra body chạy đúng. Hãy thử **cách người dùng thực sự gọi API**.

**Kiểm thử positive:** xác nhận những lời gọi mong muốn biên dịch và chạy.

- Truyền List<String> cùng **String::length** để nhận List<Integer>.
- Truyền **Function<CharSequence,String>** vào API nhận **Function<? super String,? extends String>**, khi quan hệ kiểu cho phép.
- Copy từ List<Integer> sang List<Number> qua **Collection<? super T>** và **Iterable<? extends T>**.
- Truyền phương thức generic có type bounds thỏa mãn, và dùng diamond trong vị trí có target type.

**Kiểm thử negative:** tạo một số ví dụ cố ý **không được biên dịch**, rồi kiểm tra javac báo tại lời gọi dễ xác định. Các đoạn âm tính nên được giữ trong test tài liệu hoặc kiểm thử compile-fail riêng, không để lẫn trong mã chương trình chạy.

Ví dụ không hợp lệ:

~~~java
// List<Number> bad = new ArrayList<Integer>();
// ToIntFunction<String> badFn = text -> text.toUpperCase();
~~~

Điều quan trọng là **báo lỗi đúng tầng và đủ gần nơi người dùng viết sai**. Nội dung chính xác của thông điệp javac có thể thay đổi theo phiên bản; không nên xây tài liệu yêu cầu đúng từng chữ của error message.

### Mẹo tạo một “consumer sample” nhỏ

Tạo một project test dùng API công khai như thư viện thực, không sử dụng internal helper. Viết các lời gọi ngắn với **kiểu suy luận**, **method reference**, **lambda**, **wildcards** và **generic return assignment**. Nếu hầu hết ví dụ cần cast hoặc khai báo type witness dài, hãy xem lại chữ ký.

Một số lỗi chỉ lộ ra khi người dùng thêm overload hoặc dùng API trong một ngữ cảnh nested. Kiểm thử thêm trường hợp **mapCopy(source, mapper)** nằm trong lời gọi một phương thức khác có thể giúp phát hiện API quá khó suy luận.

## 19. Java 8 và những điều vẫn quan trọng trên JDK mới

Những kiến thức không lỗi thời:

- **Generic invariance** và wildcard PECS.
- **Type parameter bounds** và generic method inference.
- **Lambda/method reference target typing**.
- **Diamond operator** trong ngữ cảnh phù hợp.
- **Type erasure** và giới hạn overload.
- **Những quy tắc kiểm tra compile-time** so với validation runtime.
- **JavaDoc và kiểm thử lời gọi API** như một phần chất lượng thư viện.

Java 10 bổ sung **var** cho suy luận kiểu biến cục bộ, nhưng var không làm mất yêu cầu về functional interface target của lambda. Trên JDK mới, viết **var result = new ArrayList<>()** không tự cung cấp target List<String> để suy luận phần tử String; kiểu của initializer được suy luận từ thông tin sẵn có và có thể là ArrayList<Object>. Nếu kiểu phần tử quan trọng cho người đọc và suy luận, khai báo **List<String> result = new ArrayList<>()** vẫn là một lựa chọn rất tốt.

Java 9+ và các phiên bản sau có thêm những API collection hữu ích như **List.of(...)** và **List.copyOf(...)** (copyOf từ Java 10). Chúng không thay đổi nguyên tắc thiết kế generic trong bài; nếu dự án phải biên dịch bằng JDK 8, không dùng các API đó trong ví dụ chạy trên JDK 8. Các ví dụ hoàn chỉnh tại đây cố ý không phụ thuộc vào cú pháp hoặc API mới hơn.

## 20. Câu hỏi thực hành có đáp án

### Bài 1 — Thiết kế mapper

Bạn cần một phương thức nhận danh sách kiểu T và function trả kiểu R, rồi tạo List<R>. Người gọi cần dùng được lambda và method reference tự nhiên. Hãy nêu chữ ký phù hợp.

**Đáp án:** ví dụ **static <T,R> List<R> mapCopy(Iterable<? extends T> source, Function<? super T,? extends R> mapper)**. Bên trong tạo danh sách mới, gọi mapper và trả List<R>. Cần xác định rõ null, tính sửa được và xử lý ngoại lệ.

### Bài 2 — Vì sao List<Integer> không thể gán cho List<Number>?

**Đáp án:** Java generic invariance. Nếu cho phép phép gán, bên giữ List<Number> có thể thêm Double vào đối tượng List<Integer> thật. Hãy dùng List<Number> ngay từ đầu, hoặc wildcard nếu chỉ đọc/ghi theo vai trò.

### Bài 3 — Copy giữa các kiểu cha con

Bạn có **List<Number> destination** và **List<Integer> source**. Chữ ký nào thể hiện việc đọc Integer từ nguồn và ghi sang đích?

**Đáp án:** **<T> void copyTo(Collection<? super T> destination, Iterable<? extends T> source)**; T liên kết hai phía và PECS cho phép subtype/supertype hợp lệ.

### Bài 4 — Bound cho phép so sánh

Bạn cần hàm greatest(T,T). Tại sao không chỉ khai báo **<T>** rồi gọi a.compareTo(b)?

**Đáp án:** một T không giới hạn không bảo đảm có phương thức compareTo. Dùng bound kiểu **<T extends Comparable<? super T>>** nếu thuật toán thật sự cần so sánh tự nhiên.

### Bài 5 — Lỗi của lambda nằm ở đâu?

Cho **ToIntFunction<String> f = s -> s.toUpperCase()**. Bạn sẽ sửa kiểu trả về hay sửa expression?

**Đáp án:** quyết định yêu cầu thực tế. Nếu cần kết quả String, dùng **Function<String,String>**. Nếu cần int, dùng phép tính int như **s.length()**. Đừng cố ép String thành int.

### Bài 6 — Vì sao overload API khó dùng?

Hai overload nhận **Function<String,Integer>** và **ToIntFunction<String>** đều có thể liên quan một method reference trích số. Đâu là cách thiết kế dễ hiểu?

**Đáp án:** nên cân nhắc đặt tên API riêng nếu khác ngữ nghĩa, hoặc hướng dẫn người gọi khai báo biến có functional interface target rõ. Không khẳng định mọi lời gọi đều ambiguous, vì compiler có quy tắc chọn overload riêng.

### Bài 7 — Lỗi compiler và lỗi runtime khác nhau thế nào?

**Đáp án:** lỗi generic inference phải sửa bằng chữ ký/kiểu đúng ở compile time; **IllegalArgumentException** trong implementation chỉ xảy ra sau khi đã biên dịch và chạy, hữu ích cho dữ liệu rỗng/key trùng/null chứ không sửa được compiler message.

### Bài 8 — Khi nào type witness là có ích?

**Đáp án:** khi cần làm rõ một generic method invocation như **Collections.<String>emptyList()** hoặc generic method reference tương ứng, đặc biệt lúc compiler thiếu thông tin. Nhưng nếu thiếu quan hệ subtype hợp lệ, type witness không thể tạo ra chuyển đổi không tồn tại.

### Bài 9 — Chọn generic ở class hay method?

**Đáp án:** kiểu cố định trong vòng đời đối tượng thường đặt ở class; kiểu thay đổi theo từng lời gọi, như R của **<R> R map(Function<? super T,? extends R>)**, thường đặt ở method.

### Bài 10 — Kiểm thử API tốt nhất chỉ cần chạy unit test thành công?

**Đáp án:** chưa đủ. Với generic API cần kiểm tra **ergonomics tại compile time**: các lời gọi bình thường biên dịch không cần cast; các lời gọi sai bị loại đúng; ví dụ có lambda, method reference, target typing, wildcard và overload phản ánh trải nghiệm thư viện thật.

## Tổng kết

Giữ API generic dễ dùng không có nghĩa xóa hết type parameter, bỏ qua wildcard hay biến mọi thứ thành Object. Ngược lại, một API tốt **dùng kiểu để mô tả quan hệ dữ liệu chính xác**, cho compiler đủ ràng buộc để suy luận và ngăn lỗi sớm.

Hãy nhớ quy trình ngắn:

1. **Tìm quan hệ kiểu thực sự** giữa nguồn, đích, callback và kết quả.
2. **Khai báo type parameter và bounds vừa đủ**; dùng PECS khi có producer/consumer rõ ràng.
3. **Để target typing làm công việc hợp lý**, nhưng đừng che khuất ý nghĩa bằng overload SAM gần giống nhau.
4. **Trả kiểu kết quả dễ sử dụng**, tránh raw type, unchecked cast và wildcard đầu ra không cần thiết.
5. **Tách lỗi compile-time khỏi validation runtime**, viết thông báo nghiệp vụ cụ thể khi dữ liệu sai.
6. **Kiểm thử trải nghiệm của người gọi** bằng các ví dụ ngắn cả đúng lẫn cố ý sai.

Nếu người dùng API thường xuyên phải viết cast, gặp **cannot infer type-variable(s)** hoặc không hiểu overload được chọn, hãy xem đó là tín hiệu cần xem lại **chữ ký và cách tổ chức API**, không đơn thuần là lý do thêm một mẹo để trình biên dịch chấp nhận mã.