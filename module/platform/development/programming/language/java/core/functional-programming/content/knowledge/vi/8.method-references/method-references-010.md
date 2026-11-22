# Khi nào method reference làm mã dễ đọc hơn trong Java?

## 1. Ý tưởng: thể hiện rõ thao tác thay vì lặp lại cách truyền tham số

**Method reference** (tham chiếu phương thức) là một biểu thức Java dùng ký hiệu `::` để tham chiếu đến phương thức hoặc constructor trong một **ngữ cảnh có kiểu đích** là functional interface. Thay vì viết lambda chỉ để gọi tiếp một phương thức đã có tên, ta có thể đưa chính phương thức ấy vào vị trí được yêu cầu.

~~~java
// Lambda chỉ chuyển tiếp đối số đến phương thức.
java.util.function.Function<String, Integer> length1 = text -> text.length();

// Method reference mô tả trực tiếp phép toán đang dùng.
java.util.function.Function<String, Integer> length2 = String::length;
~~~

Cả hai nhận `String` và trả `Integer` (từ `int` được boxing). Ở dòng thứ hai, tên `length` cho người đọc thấy **mục đích chính** ngay lập tức: lấy độ dài chuỗi. Không cần một tên biến `text` tạm thời chỉ để chuyển tiếp nó vào lời gọi.

Tuy nhiên, **method reference không phải mục tiêu bắt buộc của việc refactor**. Dạng nào dễ đọc hơn phụ thuộc vào độ rõ ràng của tên phương thức, kiểu dữ liệu trong ngữ cảnh, mức độ biến đổi thực sự và khả năng hiểu thứ tự tham số. Việc thay `->` bằng `::` không bảo đảm ngắn hơn, nhanh hơn, an toàn hơn hoặc mang tính hàm hơn.

**Quy tắc thực dụng:** Khi lambda chỉ là một lớp bọc đơn giản quanh **một phương thức có tên diễn đạt đúng ý định**, method reference thường đáng dùng. Khi lambda diễn tả **một quy tắc, điều kiện, phép ghép hoặc biến đổi không khớp nguyên xi với lời gọi sẵn có**, giữ lambda thường rõ hơn.

## 2. Các dạng method reference phải nhận diện

| Dạng | Ví dụ | Thường tương đương với lambda |
|---|---|---|
| Phương thức `static` | `Integer::parseInt` | `s -> Integer.parseInt(s)` |
| Phương thức instance trên **đối tượng đã có** (*bound receiver*) | `printer::print` | `s -> printer.print(s)` |
| Phương thức instance trên **tham số đầu tiên** (*unbound receiver*) | `String::trim` | `s -> s.trim()` |
| Constructor | `ArrayList::new` | `() -> new ArrayList<>()` trong ngữ cảnh `Supplier` |
| Constructor mảng | `String[]::new` | `n -> new String[n]` |

Các biểu thức trong bảng chỉ minh họa cách ánh xạ theo những **kiểu đích thích hợp**. Không phải mọi method reference đều có thể chuyển thành một lambda tương đương chỉ bằng thao tác thay chuỗi: overload, generic, thời điểm đánh giá receiver và quy tắc suy luận kiểu có thể ảnh hưởng.

Ví dụ `String::trim` là dạng **unbound instance method reference**: receiver chưa được chỉ định lúc tạo reference; tham số `String` đầu tiên của SAM sẽ là receiver để gọi `trim()`.

Ngược lại, `System.out::println` là **bound instance method reference**: receiver `System.out` là một đối tượng đã có tại thời điểm đánh giá reference. Tham số của SAM được truyền vào `println`; receiver **không chiếm một tham số của SAM**.

## 3. Điều kiện quyết định: lambda có đang chỉ chuyển tiếp thao tác không?

### 3.1. Chuyển tiếp một lời gọi có tên rõ nghĩa

~~~java
// Trước
java.util.List<String> cleaned =
        source.stream().map(s -> s.trim()).toList();

// Sau
java.util.List<String> cleaned =
        source.stream().map(String::trim).toList();
~~~

`source` trong ví dụ là `List<String>` có sẵn; đoạn mã được đặt trong phương thức. Khi không có điều kiện bổ sung, `String::trim` mô tả đúng từng bước của `map`: áp dụng `trim()` cho mỗi phần tử. Phiên bản method reference giảm nhiễu do việc khai báo tham số rồi gọi tiếp chính phương thức ấy.

Tương tự, với phương thức có tên nghiệp vụ:

~~~java
// Giả sử Invoice có phương thức long totalInCents().
long total = invoices.stream()
        .mapToLong(Invoice::totalInCents)
        .sum();
~~~

Kết quả dễ hiểu vì tên `totalInCents` diễn đạt **đại lượng được trích xuất**. Đây là đoạn minh họa cần kiểu `Invoice` và nguồn `invoices` được định nghĩa trong ứng dụng.

### 3.2. Thao tác có tên tốt hơn một phép biến đổi viết tại chỗ

Nếu quy tắc biến đổi không đơn giản, thay vì một lambda dài, có thể **đặt tên quy tắc** bằng phương thức rồi dùng reference:

~~~java
// Giả sử nameNormalizer là một utility có:
// static String normalizeName(String raw)
java.util.List<String> names = rawNames.stream()
        .map(NameNormalizer::normalizeName)
        .toList();
~~~

Trong trường hợp phương thức `normalizeName` có định nghĩa rõ ràng và thực sự thực hiện đúng một khái niệm, chuỗi xử lý đọc gần giống mô tả nghiệp vụ. Tuy nhiên, nếu người đọc phải liên tục mở thêm nhiều file để hiểu các helper đặt tên mơ hồ như `convert`, `fix` hoặc `doIt`, lợi ích có thể giảm.

### 3.3. Các thao tác dựng collection và object

~~~java
java.util.function.Supplier<java.util.ArrayList<String>> factory =
        java.util.ArrayList::new;

java.util.function.IntFunction<String[]> arrayFactory =
        String[]::new;
~~~

`ArrayList::new` mô tả việc tạo một danh sách mới. `String[]::new` mô tả việc nhận độ dài `int` để tạo mảng `String[]`. Các dạng này rất tự nhiên khi làm việc với API nhận *factory*, ví dụ `Stream.toArray(String[]::new)`.

## 4. Chương trình Java 17: tên phương thức làm pipeline dễ đọc

Lưu file **`MethodReferencePipelineDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class MethodReferencePipelineDemo {
    static String normalize(String raw) {
        return raw.trim().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<String> raw = List.of("  ALICE  ", " BOB", " Ana ");

        List<String> names = raw.stream()
                .map(MethodReferencePipelineDemo::normalize)
                .sorted()
                .toList();

        List<Integer> lengths = names.stream()
                .map(String::length)
                .toList();

        ToIntFunction<String> measure = String::length;
        IntFunction<String[]> makeArray = String[]::new;
        Supplier<ArrayList<String>> makeList = ArrayList::new;

        ArrayList<String> scratch = makeList.get();
        scratch.add("ok");

        System.out.println("names=" + names);
        System.out.println("lengths=" + lengths);
        System.out.println("measure=" + measure.applyAsInt("Java"));
        System.out.println("array=" +
                Arrays.toString(names.stream().toArray(makeArray)));
        System.out.println("scratch=" + scratch);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MethodReferencePipelineDemo.java
java MethodReferencePipelineDemo
~~~

Stdout:

~~~text
names=[alice, ana, bob]
lengths=[5, 3, 3]
measure=4
array=[alice, ana, bob]
scratch=[ok]
~~~

**Đọc luồng xử lý:**

1. `MethodReferencePipelineDemo::normalize` gọi phương thức `static normalize(String)` đã đặt tên rõ nghĩa. Người đọc có thể nhìn `map(...::normalize)` để biết pipeline đang chuẩn hóa tên.
2. `sorted()` sắp thứ tự tăng dần tự nhiên của các chuỗi sau chuẩn hóa, cho danh sách `[alice, ana, bob]`.
3. `String::length` là method reference không gắn receiver. `map` của `Stream<String>` yêu cầu kiểu trả về một object, nên `int` từ `length()` được boxing thành `Integer`.
4. `ToIntFunction<String> measure = String::length` minh họa cùng phương thức có thể phục vụ kiểu đích khác: đầu ra của SAM là primitive `int`.
5. `String[]::new` nhận kích thước cần tạo mảng qua `IntFunction<String[]>`; `Stream.toArray(makeArray)` tạo mảng có kiểu `String[]`.
6. `ArrayList::new` tương thích với `Supplier<ArrayList<String>>`, giúp tạo đối tượng khi gọi `makeList.get()`. Method reference ở đây không tạo sẵn danh sách `scratch` lúc gán; constructor được thực hiện khi gọi hàm cung cấp.
7. `toList()` từ Stream ở Java 16+ trả danh sách không sửa được qua các thao tác thay đổi cấu trúc; ví dụ tạo riêng `scratch` khi cần danh sách mutable.

Việc pipeline dễ đọc đến từ **sự kết hợp giữa tên phương thức rõ ràng và thứ tự thao tác**, không chỉ từ số ký tự tiết kiệm được.

## 5. Trường hợp `Comparator`: một reference có thể diễn đạt tiêu chí sắp xếp

So sánh hai cách viết:

~~~java
// Lambda thể hiện đúng, nhưng lặp cú pháp lấy khóa.
items.sort((a, b) -> Integer.compare(a.getPriority(), b.getPriority()));

// Method reference nêu ra khóa để so sánh.
items.sort(java.util.Comparator.comparingInt(Item::getPriority));
~~~

Đây là đoạn minh họa, giả định `Item#getPriority()` trả `int` và `items` là danh sách mutable. Dòng thứ hai nói trực tiếp: **sắp xếp theo priority kiểu int**.

Khi cần sắp giảm dần, có thể dùng `Comparator.comparingInt(Item::getPriority).reversed()` thay vì đảo thủ công dấu của kết quả so sánh. Không nên viết `(a,b) -> a.getPriority() - b.getPriority()` cho số nguyên tổng quát vì phép trừ có thể tràn và phá vỡ thứ tự so sánh.

Tuy nhiên, khi phép sắp có nhiều mức ưu tiên hoặc quy tắc đặc biệt, comparator đặt tên hoặc lambda diễn giải các điều kiện có thể dễ hiểu hơn một chuỗi method reference dài.

### Chương trình hoàn chỉnh: khi nên kết hợp method reference và lambda

Lưu **`MethodReferenceChoiceDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;

public class MethodReferenceChoiceDemo {
    record Task(String label, int priority) {}

    public static void main(String[] args) {
        List<Task> tasks = List.of(
                new Task("Write", 2),
                new Task("Test", 1),
                new Task("Deploy", 3)
        );

        List<String> important = tasks.stream()
                .filter(task -> task.priority() >= 2)
                .sorted(Comparator.comparingInt(Task::priority))
                .map(Task::label)
                .toList();

        String prefix = "item:";
        Function<String, String> withPrefix = prefix::concat;

        System.out.println("important=" + important);
        System.out.println("prefix=" + withPrefix.apply("7"));
    }
}
~~~

Chạy:

~~~bash
javac MethodReferenceChoiceDemo.java
java MethodReferenceChoiceDemo
~~~

Stdout:

~~~text
important=[Write, Deploy]
prefix=item:7
~~~

**Vì sao dùng kết hợp là tốt?**

- `filter(task -> task.priority() >= 2)` giữ lambda vì đây là **điều kiện nghiệp vụ có ngưỡng 2**, không đơn giản chỉ chuyển tiếp một lời gọi `boolean`.
- `Comparator.comparingInt(Task::priority)` dùng method reference để chỉ rõ khóa sắp xếp.
- `map(Task::label)` trích nhãn bằng phương thức accessor có tên rõ.
- `prefix::concat` là reference đến phương thức instance trên đối tượng `prefix` đã có. SAM `Function<String,String>` nhận chuỗi đối số và trả chuỗi nối; `prefix` chính là receiver đã được gắn.

Không nên cố “chuyển mọi lambda sang method reference”. Sự kết hợp ở trên cho thấy **reference phù hợp với việc chỉ tên thao tác; lambda phù hợp với việc diễn đạt quy tắc cần viết ngay tại chỗ**.

## 6. Khi nào lambda dễ đọc hơn method reference?

### 6.1. Có thêm điều kiện hoặc phép tính

~~~java
java.util.function.Predicate<String> meaningful =
        text -> text != null && !text.isBlank();

java.util.function.Function<Integer, Integer> adjusted =
        value -> value * 2 + 1;
~~~

Ở đây không có sẵn một phương thức duy nhất có tên rõ ràng đại diện đúng quy tắc và tham số. Lambda thể hiện trực tiếp điều kiện và công thức. Nếu chỉ viết `String::isBlank`, logic của `meaningful` bị thay đổi: nó không kiểm tra `null` và trả `true` cho chuỗi trắng, trong khi `meaningful` phải trả `false`.

Method reference chỉ là phương tiện **cung cấp hành vi tương thích**, không phải phép biến đổi tự động tương đương cho bất kỳ lambda.

### 6.2. Cần kết hợp tham số hoặc thay thứ tự đối số

~~~java
java.util.function.BiFunction<String, String, String> pair =
        (left, right) -> right + ":" + left;
~~~

Một biểu thức lambda mô tả rõ **thứ tự xử lý**. Với `String::concat`, kiểu đích `BiFunction<String,String,String>` cũng có thể phù hợp nhưng nó chỉ nối `left + right`, **không** tự thêm dấu `:` hoặc đảo thứ tự. Nếu đổi sang method reference đơn thuần, hành vi nghiệp vụ sẽ không giống nhau.

### 6.3. Cần biến cục bộ, kiểm tra lỗi hoặc logging

~~~java
java.util.function.Function<String, Integer> safeParse = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    }
};
~~~

`Integer::parseInt` trả `int` hợp kiểu đích `Function<String,Integer>`, nhưng **không** chứa chính sách trả `-1` khi đầu vào sai. Lambda biểu diễn rõ bước bắt ngoại lệ và fallback. Hợp đồng `-1` chỉ là minh họa: ứng dụng thực tế nên chọn cơ chế báo lỗi tránh nhầm lẫn với giá trị hợp lệ, chẳng hạn `OptionalInt`, kết quả có trạng thái hoặc exception theo yêu cầu.

Nếu logic quá dài, hãy cân nhắc tách thành phương thức có tên rõ như `parseOrDefault` rồi mới dùng method reference. Lý do tách là **quy tắc đáng đặt tên**, không phải vì mọi lambda dài đều sai.

### 6.4. Tên phương thức quá chung hoặc kiểu đích không rõ

~~~java
records.stream().map(this::process).toList();
~~~

Đây là đoạn minh họa trong phương thức instance. Nếu `process` có nhiều overload hoặc tên không nói rõ biến đổi gì, người đọc có thể khó biết chuyện gì xảy ra. Viết lambda với lời gọi rõ đối số, đổi tên phương thức, hoặc trích một hàm chuyên trách có thể giúp hơn:

~~~java
records.stream().map(record -> enrichForDisplay(record)).toList();
~~~

Cần có `records` và `enrichForDisplay` trong chương trình thực tế; ví dụ nhằm so sánh cách diễn đạt. Sự rõ ràng của kiểu dữ liệu và tên API quan trọng hơn việc cú pháp có dấu `::` hay `->`.

## 7. Một quy tắc review: “chỉ chuyển tiếp” phải thật sự chỉ chuyển tiếp

Các cặp thường đáng đổi:

| Lambda | Method reference | Điều kiện |
|---|---|---|
| `x -> x.trim()` | `String::trim` | Kiểu đích nhận `String` |
| `x -> x.length()` | `String::length` | Kiểu đích phù hợp tham số và kết quả |
| `s -> Integer.parseInt(s)` | `Integer::parseInt` | Cùng overload và chính sách lỗi |
| `x -> validator.validate(x)` | `validator::validate` | Receiver đã có, ngữ cảnh chọn đúng phương thức |
| `x -> new ArrayList<>(x)` | `ArrayList::new` | Kiểu đích nhận đối số constructor tương thích |
| `() -> new ArrayList<>()` | `ArrayList::new` | Kiểu đích là supplier không tham số |
| `n -> new String[n]` | `String[]::new` | Kiểu đích nhận `int`, trả `String[]` |
| `x -> System.out.println(x)` | `System.out::println` | Receiver và overload phù hợp |

Đọc bảng theo hướng **điều kiện**: một method reference có thể tham chiếu tới phương thức overloaded, nên kiểu đích giúp chọn chữ ký cụ thể. Trong trường hợp overload mơ hồ, trình biên dịch có thể yêu cầu bổ sung ngữ cảnh, biến có kiểu hoặc cast.

Ngoài ra, đừng biến những cặp trên thành quy tắc máy móc. Một lambda có tên đối số diễn đạt tốt ý nghĩa nghiệp vụ đôi khi dễ đọc hơn, nhất là với interface generic phức tạp.

### Trường hợp method reference có thể làm mờ vai trò receiver

So sánh:

~~~java
// Nếu không quen cú pháp unbound instance method:
java.util.function.BiPredicate<String, String> begins =
        String::startsWith;

// Lambda thể hiện rõ đối số nào là receiver:
java.util.function.BiPredicate<String, String> beginsExplicit =
        (text, prefix) -> text.startsWith(prefix);
~~~

Cả hai cần `BiPredicate<String,String>`, với SAM `boolean test(String,String)`. Ở `String::startsWith`, **đối số thứ nhất** là receiver `text` và đối số thứ hai là `prefix`. Người mới học dễ đọc nhầm thành một lời gọi static. Lambda `(text,prefix) -> text.startsWith(prefix)` dài hơn nhưng dễ chỉ rõ vai trò từng tham số.

## 8. Không thay lambda bằng reference khi khác thời điểm đánh giá

Dạng **bound receiver** có một chi tiết về runtime cần hiểu. Khi đánh giá biểu thức method reference `object::method`, biểu thức receiver `object` được đánh giá lúc tạo reference và phải khác `null`. Với lambda `x -> object.method(x)`, biểu thức `object` nằm trong thân lambda và được đánh giá khi lambda được gọi.

Ví dụ minh họa cố ý có lỗi:

~~~java
String prefix = null;

// Việc đánh giá bound method reference ném NullPointerException ngay.
// java.util.function.Function<String,String> a = prefix::concat;

// Tạo lambda này có thể thành công; gọi nó sẽ ném NullPointerException.
// java.util.function.Function<String,String> b = x -> prefix.concat(x);
~~~

Không nên chạy hai dòng bị bình luận. Dù cả hai mô tả “nối với prefix”, **thời điểm thất bại khác nhau**. Nếu receiver là một biến hoặc biểu thức có tác dụng phụ, thời điểm lấy receiver cũng có thể ảnh hưởng hành vi.

Vì vậy, câu “method reference chỉ là cú pháp rút gọn của lambda” hữu ích ở mức giới thiệu, nhưng không nên dùng như bảo đảm tương đương trong mọi tình huống. Khi refactor, hãy kiểm tra cách capture receiver, null, overload và ngoại lệ.

## 9. Kiểu đích vẫn quyết định method reference nào hợp lệ

Method reference giống lambda ở chỗ cần một **functional interface type** và phải tương thích với SAM. Nó không phải lời gọi phương thức đã thực thi.

~~~java
java.util.function.Function<String, Integer> parse =
        Integer::parseInt;

java.util.function.ToIntFunction<String> parsePrimitive =
        Integer::parseInt;

java.util.function.Consumer<String> print =
        System.out::println;
~~~

Trong ví dụ:

- `parse` nhận `String`, trả `Integer`; `parseInt` thực tế trả `int` rồi boxing theo hợp đồng.
- `parsePrimitive` cũng nhận `String` nhưng trả primitive `int` theo `ToIntFunction`.
- `print` có SAM trả `void`, nên overload `println(String)` thích hợp được chọn từ kiểu tham số của `Consumer<String>`.

Nếu không có kiểu đích, `var parse = Integer::parseInt;` không hợp lệ vì method reference cũng không tự có kiểu độc lập đủ cho `var` suy ra. Đưa vào biến có kiểu hoặc phép cast thích hợp sẽ xác định descriptor.

Có thể một method reference phù hợp với nhiều overload nhận functional interface khác nhau. Nếu compiler không tìm được lựa chọn duy nhất, việc chuyển từ lambda sang method reference không tự sửa được tính mơ hồ. Hãy xem chữ ký overload và cung cấp kiểu đích rõ ràng.

## 10. Method reference không tự mang đặc tính hàm thuần

Cả lambda và method reference đều có thể gây **tác dụng phụ**:

~~~java
// Minh họa trong một phương thức có repository và auditLogger.
// entities.forEach(repository::save);
// items.forEach(auditLogger::record);
~~~

`repository::save` vẫn là thao tác ghi dữ liệu; `auditLogger::record` vẫn có thể làm I/O. Ký hiệu `::` không bảo đảm an toàn luồng, không loại bỏ lỗi kiểm tra ngoại lệ, không tự xử lý `null` và không biến thao tác bên ngoài thành hàm thuần khiết.

Ví dụ `String::trim` có thể thích hợp trong pipeline biến đổi dữ liệu không gây tác dụng phụ. Nhưng nếu collection nguồn đang bị thay đổi đồng thời hoặc callback được cung cấp có trạng thái thay đổi, việc thay lambda bằng method reference không giải quyết vấn đề thiết kế.

**Hiệu năng:** Đừng giả định `String::length` chắc chắn nhanh hơn `s -> s.length()`. Java compiler và JVM có nhiều cách triển khai/ tối ưu hóa lambda và method reference; kết quả phụ thuộc ngữ cảnh, phiên bản JDK và tải thực. Chọn cách viết theo tính đúng đắn và khả năng bảo trì trước; nếu hiệu năng là yêu cầu, đo bằng benchmark phù hợp.

## 11. Khi method reference bị lạm dụng

### 11.1. Tạo helper chỉ để bỏ dấu `->`

Một helper tên `f`, `doSomething` hoặc `processValue` được thêm chỉ để đổi `x -> x.strip().toLowerCase(Locale.ROOT)` thành `Utils::f` có thể khiến người đọc mất thông tin. Nếu quy tắc đủ đơn giản và chỉ dùng một chỗ, giữ lambda là hợp lý. Chỉ tách phương thức khi nó **có một ý nghĩa riêng có thể đặt tên tốt** hoặc cần kiểm thử/tái sử dụng.

### 11.2. Dây chuyền method reference không nói rõ nghiệp vụ

~~~java
stream.map(this::stepA)
      .map(this::stepB)
      .map(this::stepC);
~~~

Không có gì sai về cú pháp, nhưng tên `stepA`, `stepB`, `stepC` có thể che mất mục đích. Cải thiện tên phương thức và tổ chức các bước trước khi quan tâm tới số lượng `::`. Nếu việc biến đổi phụ thuộc vào một điều kiện tại vị trí đang đọc, lambda rõ ràng có thể tốt hơn.

### 11.3. Dùng method reference khiến người đọc phải đoán tham số

`String::substring` có các overload nhận vị trí bắt đầu hoặc cặp vị trí; `String::startsWith` nhận receiver cùng prefix. Với các API có nhiều tham số và receiver chưa gắn, lambda có tên tham số rõ có thể giúp truyền đạt thứ tự. Chẳng hạn `(text, offset) -> text.substring(offset)` thường trực quan hơn `String::substring` đối với người chưa quen unbound receiver.

### 11.4. Method reference che giấu chính sách lỗi

Khi cần xử lý lỗi parsing, fallback, retry, mapping exception hay thêm ngữ cảnh lỗi, `Integer::parseInt` không chứa các bước đó. Thêm method reference đơn thuần có thể làm mất chính sách sẵn có trong lambda. Giữ lambda, hoặc tạo phương thức nghiệp vụ được đặt tên đầy đủ và đã xử lý lỗi.

## 12. Checklist thực tế khi đổi lambda sang method reference

Trước mỗi thay đổi, thử trả lời:

1. **Lambda đang làm gì?** Chỉ gọi một phương thức hoặc constructor với cùng đối số, hay còn kiểm tra, tính toán, ghi log, bắt lỗi?
2. **Tên phương thức có tự mô tả ý nghĩa không?** `User::email` rõ hơn `this::get` trong pipeline dùng để lấy email.
3. **Kiểu đích là gì?** SAM yêu cầu mấy tham số, kiểu nào, trả kết quả gì, có checked exception nào?
4. **Receiver là ai?** Đã gắn như `service::run` hay lấy từ đối số đầu tiên như `String::trim`?
5. **Thứ tự tham số và overload có giữ nguyên không?** Có chuyển đổi boxing/unboxing hoặc varargs cần kiểm tra không?
6. **Thời điểm đánh giá có thay đổi không?** Với bound receiver, nhất là khi receiver có thể `null` hoặc biểu thức tính toán động.
7. **Điều kiện, fallback và side effects có giữ nguyên không?** Việc bỏ thân lambda không được làm mất hành vi nghiệp vụ.
8. **Người đọc có hiểu nhanh hơn không?** Nếu reference gây khó hiểu, lambda với tên tham số rõ ràng có thể tốt hơn.
9. **Biên dịch và kiểm thử ở mức phù hợp:** Với thay đổi đơn giản, kiểm tra compiler và đầu ra; với logic nghiệp vụ, thử dữ liệu biên, `null`, lỗi và các tác dụng phụ.

Không cần đổi toàn bộ codebase sang method reference. Sự nhất quán quan trọng hơn là **chọn biểu thức dễ hiểu cho từng ý định**, không phải dùng một kiểu cú pháp tuyệt đối.

## 13. Bài tập tự đánh giá

**Câu 1.** Trong `Stream<String>`, khi nào `map(String::trim)` trực quan hơn `map(s -> s.trim())`?

**Câu 2.** `filter(s -> s != null && !s.isBlank())` có thể đổi thành `filter(String::isBlank)` mà không thay hành vi không?

**Câu 3.** Với `Comparator.comparingInt(Item::getPriority)`, lợi ích của method reference nằm ở chỗ nào? Vì sao tránh so sánh bằng hiệu số hai `int`?

**Câu 4.** `String::startsWith` dùng cho `BiPredicate<String,String>` sẽ nhận đối số đầu tiên làm gì?

**Câu 5.** `prefix::concat` và `x -> prefix.concat(x)` có luôn cùng thời điểm gây `NullPointerException` khi `prefix == null` không?

**Câu 6.** Tại sao `String[]::new` được dùng trong `Stream.toArray`, và kiểu SAM nhận bao nhiêu tham số?

**Câu 7.** `repository::save` có tự động an toàn hơn `x -> repository.save(x)` về transaction hoặc side effects không?

**Đáp án gợi ý:**

1. Khi thao tác chỉ là chuyển tiếp `trim()`, không thêm điều kiện hoặc xử lý nào khác, và kiểu đầu vào là `String`.
2. Không: logic `null` và điều kiện đúng/sai thay đổi; `String::isBlank` không kiểm tra null và trả true khi chuỗi trắng.
3. Nó nêu trực tiếp khóa sắp xếp; lấy hiệu số dễ tràn `int` và vi phạm thứ tự comparator.
4. Là receiver `text` để gọi `text.startsWith(prefix)`, đối số thứ hai là `prefix`.
5. Không: bound reference kiểm tra receiver khi đánh giá reference; lambda đánh giá receiver khi được gọi.
6. `toArray` cần factory nhận một `int` biểu diễn độ dài và trả `String[]`; kiểu phù hợp là `IntFunction<String[]>`.
7. Không. Hai dạng đều có thể thực hiện I/O; phải thiết kế riêng transaction, xử lý lỗi và trạng thái.

## 14. Tài liệu Java để đối chiếu

- [Java SE 17 Language Specification, `15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): cú pháp, kiểu đích, receiver và quy tắc đánh giá method reference.
- [Java SE 17 Language Specification, `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): đặc điểm của lambda và target typing.
- [Java SE 17 API — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): `comparingInt`, `reversed` và các phép kết hợp comparator.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): các phép `map`, `sorted` và `toArray`.

**Ghi nhớ:** Method reference làm mã dễ đọc hơn khi nó **chỉ tên một thao tác đã có tên rõ nghĩa**, đặc biệt trong `map`, `Comparator`, callback và factory. Lambda thường tốt hơn khi phải **diễn đạt quy tắc tại chỗ**, có điều kiện, tham số cần đặt tên, hoặc cần xử lý thêm. Hãy ưu tiên **ý định rõ ràng, hành vi đúng và kiểu đích chính xác** thay vì thay mọi dấu `->` bằng `::`.