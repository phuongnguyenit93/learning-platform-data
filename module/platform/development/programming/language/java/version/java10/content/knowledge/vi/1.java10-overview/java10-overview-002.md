# Kiến thức nền về kiểu tĩnh, generics, Stream và JVM

*Bối cảnh: Định hướng Java 10. Nội dung tập trung vào các nguyên lý và API vẫn được dùng trong Java hiện đại; mọi chương trình hoàn chỉnh bên dưới chạy với JDK 17 trở lên.*

## 1. Bức tranh tổng thể

Một chương trình Java đi qua các lớp khái niệm liên kết với nhau:

1. **Hệ kiểu tĩnh (static typing)**: trình biên dịch biết và kiểm tra kiểu của biểu thức, biến, tham số và giá trị trả về trước khi chương trình chạy.
2. **Generics**: truyền thông tin kiểu cho lớp, interface và phương thức, giúp thao tác với tập hợp dữ liệu an toàn hơn ở thời điểm biên dịch.
3. **Stream API**: mô tả chuỗi thao tác xử lý dữ liệu, thường lấy từ collection, bằng các bước lọc, biến đổi, tổng hợp.
4. **JVM (Java Virtual Machine)**: nạp và thực thi bytecode, quản lý bộ nhớ, tối ưu mã khi chạy và thu gom rác.

Java 10 bổ sung **suy luận kiểu cho biến cục bộ với `var`**. Kiến thức nền quan trọng ở đây là: suy luận kiểu không biến Java thành ngôn ngữ kiểu động; generics tiếp tục được kiểm tra lúc biên dịch; Stream vẫn vận hành trên các kiểu đã xác định; JVM mới là nơi bytecode được thực thi.

## 2. Kiểu tĩnh và suy luận kiểu cục bộ (`var`)

### 2.1. “Kiểu tĩnh” nghĩa là gì?

Kiểu của một biến hoặc biểu thức được xác định khi biên dịch, kể cả khi bạn không viết tên kiểu tường minh. Trình biên dịch ngăn những phép gán hoặc lời gọi phương thức không phù hợp:

```java
int quantity = 5;
quantity = 7;             // Hợp lệ
// quantity = "bảy";      // Lỗi biên dịch: String không thể gán cho int

String title = "Java";
// title.toUpperCase() trả về String
String upper = title.toUpperCase();
```

**Kiểu tham chiếu lúc biên dịch** và **lớp thực tế của đối tượng lúc chạy** có thể khác nhau do đa hình:

```java
Number number = Integer.valueOf(42); // Biến có kiểu Number; đối tượng là Integer
System.out.println(number.intValue()); // 42
```

Lời gọi được kiểm tra theo kiểu `Number`; phương thức được ghi đè có thể được phân giải động theo đối tượng thực tế. Ép kiểu sai có thể gây `ClassCastException` ở thời điểm chạy: hệ kiểu tĩnh giảm lỗi, nhưng không loại bỏ mọi lỗi runtime.

### 2.2. `var` của Java 10 suy luận một kiểu cố định

`var` được dùng ở **khai báo biến cục bộ có giá trị khởi tạo**, kể cả biến trong vòng `for` và biến lặp `for-each`. Trình biên dịch suy ra kiểu từ biểu thức khởi tạo, sau đó kiểm tra biến đó như khai báo kiểu tường minh.

```java
// StaticTypingDemo.java
import java.util.List;

public class StaticTypingDemo {
    public static void main(String[] args) {
        var count = 3;                // int
        var message = "java";         // String
        List<String> topics = List.of("types", "generics", "streams");

        count += 2;
        System.out.println(count);
        System.out.println(message.toUpperCase());
        System.out.println(topics.get(1));
    }
}
```

Chạy:

```bash
javac StaticTypingDemo.java
java StaticTypingDemo
```

Kết quả:

```text
5
JAVA
generics
```

Điểm cần nhớ:

- `var count = 3;` xác định `count` là `int`. Gán `count = "3";` vẫn lỗi biên dịch.
- `var` không phải kiểu dữ liệu mới, không mang kiểu “động” và không tự thay đổi kiểu khi chạy.
- `var` không dùng để khai báo trường (field), kiểu trả về của phương thức hoặc tham số phương thức thông thường.
- Không thể suy luận kiểu từ `var value = null;` hoặc khai báo `var value;` vì thiếu kiểu suy luận được.
- `final var name = "Java";` là biến cục bộ không thể gán lại; `final` không mặc nhiên khiến đối tượng được tham chiếu trở thành bất biến.

**Chọn `var` hay ghi rõ kiểu?** Dùng `var` khi kiểu hiển nhiên, chẳng hạn `var names = new ArrayList<String>();`. Ghi `List<String> names = ...` khi kiểu interface là hợp đồng muốn nhấn mạnh hoặc biểu thức khởi tạo dài khiến người đọc khó nhận biết kiểu. Tránh suy luận mơ hồ như `var list = new ArrayList<>();`: không có ngữ cảnh kiểu cho toán tử diamond, danh sách đó có thể được suy luận thành `ArrayList<Object>` thay vì loại phần tử bạn định dùng.

### 2.3. Primitive, tham chiếu và `null`

Java phân biệt primitive (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`) với kiểu tham chiếu (như `String`, `List<String>`, lớp tự định nghĩa). Primitive lưu giá trị theo ngữ nghĩa của kiểu; biến tham chiếu có thể trỏ đến đối tượng hoặc chứa `null`. Với `null`, gọi phương thức qua tham chiếu sẽ gây `NullPointerException`.

Wrapper như `Integer` và `Double` cho phép biểu diễn giá trị số dưới dạng đối tượng; **autoboxing/unboxing** chuyển đổi thuận tiện giữa primitive và wrapper trong nhiều tình huống. Tuy nhiên unboxing giá trị `Integer` đang là `null` sẽ gây `NullPointerException`. Khi viết code và đọc lỗi, hãy phân biệt kiểu compile-time, giá trị thực tế và khả năng `null`.

## 3. Generics: hợp đồng kiểu khi làm việc với dữ liệu

### 3.1. Vì sao cần generics?

`List<String>` biểu thị một danh sách phần tử có kiểu `String`. Trình biên dịch có thể phát hiện thao tác sai kiểu trước khi chạy và cho phép lấy phần tử mà không phải ép kiểu thủ công.

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
// names.add(123); // Lỗi biên dịch: không thể thêm Integer vào List<String>
```

`T`, `E`, `K` và `V` thường là các tên tham số kiểu (type parameter), ví dụ `class Box<T>` hay `Map<K, V>`. Chúng đại diện cho kiểu sẽ được truyền vào khi sử dụng một lớp hoặc phương thức; không phải một kiểu đặc biệt có thể nhận mọi giá trị tùy ý.

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

// Sử dụng trong một phương thức:
Box<String> box = new Box<>("Java");
String name = box.get(); // Không cần ép kiểu
```

Đoạn `Box` thể hiện cách định nghĩa lớp generic; phần sử dụng là đoạn mã đặt bên trong một phương thức, không phải chương trình chạy độc lập.

### 3.2. Generics có tính bất biến (invariance)

`Integer` kế thừa `Number` nhưng `List<Integer>` **không** phải kiểu con của `List<Number>`. Nếu có thể thay thế trực tiếp, code nhận `List<Number>` sẽ được phép thêm `Double` vào danh sách vốn chỉ chứa `Integer`.

```java
List<Integer> integers = List.of(1, 2, 3);
// List<Number> numbers = integers; // Lỗi biên dịch
```

Để API linh hoạt mà vẫn an toàn, Java dùng wildcard:

- `List<? extends Number>`: đọc phần tử như `Number`; phù hợp khi nguồn **cung cấp** giá trị. Không thể tự ý thêm một `Integer`/`Double` vì kiểu con cụ thể chưa biết.
- `List<? super Integer>`: có thể thêm `Integer`; phù hợp khi đích **nhận** giá trị. Khi đọc, không thể giả định phần tử có kiểu hẹp hơn `Object`.
- `List<?>`: danh sách phần tử chưa biết kiểu; vẫn có thể đọc dưới dạng `Object`.

Quy tắc ghi nhớ là **PECS — Producer Extends, Consumer Super**. Đây là quy tắc chọn tham số API theo chiều dữ liệu, không phải lời khuyên luôn dùng wildcard ở mọi nơi.

### 3.3. Ví dụ PECS chạy được

```java
// GenericsDemo.java
import java.util.ArrayList;
import java.util.List;

public class GenericsDemo {
    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number value : source) {
            total += value.doubleValue();
        }
        return total;
    }

    static void appendDefaults(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3);
        System.out.println(sum(values));

        List<Number> destination = new ArrayList<>();
        appendDefaults(destination);
        System.out.println(destination);
    }
}
```

Chạy:

```bash
javac GenericsDemo.java
java GenericsDemo
```

Kết quả:

```text
6.0
[10, 20]
```

`sum` chỉ đọc các giá trị số nên nhận `? extends Number`; `appendDefaults` chỉ ghi các giá trị `Integer` nên nhận `? super Integer`. Đối số `List<Integer>` và `List<Number>` phù hợp với vai trò tương ứng.

### 3.4. Type erasure và giới hạn của generics

Java triển khai phần lớn generics bằng **type erasure**: kiểm tra kiểu generic khi biên dịch, sau đó mã thực thi không mang riêng một lớp runtime kiểu `List<String>` khác với `List<Integer>`. Thông tin kiểu trong khai báo vẫn có thể được giữ ở metadata phục vụ reflection, nhưng **đối tượng `ArrayList` thông thường không biết nó đang giữ `String` hay `Integer` theo tham số generic**.

Hệ quả quan trọng:

- `new ArrayList<String>()` và `new ArrayList<Integer>()` có cùng lớp runtime `ArrayList`.
- Không thể kiểm tra `value instanceof List<String>`; có thể kiểm tra `value instanceof List<?>`.
- Không thể dùng primitive làm tham số kiểu: viết `List<Integer>`, không viết `List<int>`.
- Tránh raw type như `List list`, vì bỏ qua một phần kiểm tra kiểu và có thể dẫn đến lỗi ép kiểu lúc chạy.
- Generic method có thể có tham số kiểu riêng: `static <T> T first(List<T> values)`; tham số kiểu phương thức được suy luận từ cách gọi.
- Giới hạn kiểu như `<T extends Number>` cho phép sử dụng các thao tác của `Number` trong phạm vi được ràng buộc.

**Generics tăng an toàn kiểu cho code Java, không tự kiểm chứng dữ liệu bên ngoài.** Dữ liệu JSON, phản hồi API hay dữ liệu nhập từ người dùng vẫn cần được parse, validate và xử lý lỗi phù hợp.

## 4. Stream API: xử lý tập hợp theo pipeline

### 4.1. Collection và Stream khác nhau ở đâu?

**Collection** như `List` giữ các phần tử và cung cấp thao tác thêm, xóa, truy cập. **Stream** biểu diễn một pipeline xử lý phần tử từ nguồn. Pipeline có thể có ba nhóm thành phần:

```text
Nguồn dữ liệu
    -> thao tác trung gian (filter/map/distinct/sorted/flatMap...)
    -> thao tác kết thúc (toList/count/findFirst/reduce/sum...)
    -> kết quả hoặc tác động
```

Phần lớn thao tác trung gian là **lazy**: mô tả công việc nhưng chưa duyệt phần tử ngay. Thao tác kết thúc mới khởi động đánh giá pipeline. Một đối tượng Stream đã có thao tác kết thúc không được tái sử dụng; muốn chạy pipeline khác, hãy tạo Stream mới từ nguồn.

`map` biến đổi từng phần tử theo ánh xạ một-một; `filter` giữ phần tử thỏa điều kiện; `distinct` loại phần tử trùng theo `equals`; `sorted` sắp xếp theo thứ tự thích hợp; `flatMap` chuyển mỗi phần tử thành một stream rồi làm phẳng thành một luồng phần tử.

### 4.2. Ví dụ pipeline chạy được

```java
// StreamDemo.java
import java.util.List;

public class StreamDemo {
    public static void main(String[] args) {
        List<String> names = List.of(" An ", "Bình", "Chi", "Anh", "An");

        var selected = names.stream()
                .map(String::trim)
                .filter(name -> name.startsWith("An"))
                .distinct()
                .sorted()
                .toList();

        System.out.println(selected);
        System.out.println(names.size());

        long count = names.stream()
                .map(String::trim)
                .filter(name -> name.length() >= 3)
                .count();
        System.out.println(count);

        List<List<Integer>> groups = List.of(List.of(1, 2), List.of(3));
        System.out.println(groups.stream().flatMap(List::stream).toList());

        String firstC = names.stream()
                .map(String::trim)
                .filter(name -> name.startsWith("C"))
                .findFirst()
                .orElse("Không có");
        System.out.println(firstC);
    }
}
```

Chạy:

```bash
javac StreamDemo.java
java StreamDemo
```

Kết quả:

```text
[An, Anh]
5
3
[1, 2, 3]
Chi
```

Diễn giải:

1. `map(String::trim)` loại khoảng trắng ở hai đầu từng tên.
2. `filter` chọn tên bắt đầu bằng `An`, `distinct` bỏ `An` lặp, `sorted` sắp xếp trước khi `toList` tạo kết quả.
3. Danh sách gốc vẫn có 5 phần tử; pipeline không mặc định sửa nguồn.
4. `count` tính 3 tên có độ dài ít nhất 3 sau khi trim: `Bình`, `Chi` và `Anh`.
5. `flatMap` biến `List<List<Integer>>` thành một luồng `Integer` phẳng.
6. `findFirst` trả `Optional<String>`; `orElse` dùng giá trị thay thế nếu không tìm thấy.

`Stream.toList()` có từ Java 16 và trả danh sách **không thể sửa bằng add/remove/set**. Nếu thật sự cần danh sách mutable, dùng `collect(Collectors.toCollection(ArrayList::new))`; không nên giả định `Collectors.toList()` bảo đảm tính mutable theo hợp đồng API.

### 4.3. Các nhóm thao tác cần phân biệt

| Mục đích | Công cụ thường dùng | Ghi chú |
| --- | --- | --- |
| Chọn phần tử | `filter(predicate)` | Predicate trả về `boolean` |
| Biến đổi | `map(function)`, `mapToInt` | `mapToInt` tạo `IntStream`, hỗ trợ `sum`, `average` |
| Làm phẳng | `flatMap(function)` | Hữu ích với danh sách lồng nhau |
| Kiểm tra điều kiện | `anyMatch`, `allMatch`, `noneMatch` | Có thể kết thúc sớm |
| Tìm kiếm | `findFirst`, `findAny` | Trả `Optional`, tránh giả định luôn có phần tử |
| Tổng hợp | `count`, `sum`, `reduce`, `collect` | Chọn phép tổng hợp theo loại kết quả |
| Biến thành danh sách | `toList`, `collect(...)` | Hiểu rõ yêu cầu về khả năng sửa dữ liệu |

**Ví dụ tổng hợp số không cần boxing bổ sung:**

```java
int total = List.of(2, 3, 4).stream()
        .mapToInt(Integer::intValue)
        .sum(); // 9
```

`reduce` thích hợp khi kết hợp các phần tử bằng phép toán có tính chất phù hợp; `collect` phù hợp khi thu kết quả vào cấu trúc tổng hợp. Với các pipeline chạy song song, phép kết hợp cần được thiết kế đúng để kết quả không phụ thuộc lịch chạy.

### 4.4. Lazy, side effect và parallel stream

- **Không phụ thuộc side effect trong `map`/`filter`/`peek`.** Pipeline nên ưu tiên biến đổi thuần và kết quả từ terminal operation; JVM/Stream implementation có quyền tối ưu hóa khiến việc quan sát side effect ở một số thao tác không như kỳ vọng.
- **Đừng dùng lại Stream:** `var s = names.stream(); s.count(); s.findFirst();` không hợp lệ theo hợp đồng vì Stream đã được tiêu thụ.
- **Thứ tự có ý nghĩa:** với nguồn có encounter order, `forEach` trên parallel stream không bảo đảm thực thi theo thứ tự; `forEachOrdered` dành cho trường hợp cần giữ thứ tự quan sát.
- **`parallel()` không đồng nghĩa nhanh hơn:** xử lý song song có chi phí chia việc, phối hợp luồng và kết hợp kết quả; phép toán có shared mutable state có thể gây race condition. Chỉ cân nhắc khi bài toán đủ lớn, thao tác phù hợp và có đo hiệu năng.
- **Đóng nguồn cần tài nguyên:** Stream từ `Files.lines(...)` nên được dùng trong try-with-resources để đóng file; Stream từ `List.stream()` không có tài nguyên I/O bên ngoài cần đóng theo cách đó.

Stream là mô hình xử lý dữ liệu; một pipeline `stream()` tuần tự không tự chạy bất đồng bộ. Hãy phân biệt nó với `CompletableFuture` hoặc công cụ concurrency khi thiết kế ứng dụng.

## 5. JVM: từ mã nguồn đến lúc chương trình chạy

### 5.1. Biên dịch và thực thi

```text
Tệp .java
    -- javac -->
Bytecode .class
    -- JVM nạp lớp, kiểm tra bytecode và thực thi -->
Kết quả chương trình
    (trình thông dịch và/hoặc JIT tối ưu những đoạn thích hợp)
```

- **JDK** cung cấp công cụ phát triển như `javac`, `java` và `javap` cùng những thành phần cần thiết để phát triển/chạy Java.
- **Bytecode** là dạng trung gian theo đặc tả JVM; cùng một tệp bytecode có thể chạy trên các JVM tương thích với phiên bản lớp và phụ thuộc của chương trình.
- **Class loading** nạp định nghĩa lớp khi cần; **bytecode verification** kiểm tra những ràng buộc an toàn của mã trước khi thực thi.
- **JIT (Just-In-Time compilation)** có thể biên dịch các đoạn bytecode được thực thi thường xuyên sang mã máy để tối ưu hiệu năng. Không nên giả định mọi phương thức đều được JIT, hoặc một ngưỡng “nóng” cố định cho mọi JVM.
- `javap -c StaticTypingDemo` cho phép quan sát phần hướng dẫn bytecode của lớp đã biên dịch. Output chi tiết có thể khác theo phiên bản trình biên dịch, vì vậy dùng để phân tích thay vì học thuộc.

Suy luận kiểu bằng `var` diễn ra **khi biên dịch**. Không có “đối tượng `var`” trong JVM; biểu thức và thao tác sau khi biên dịch tuân theo kiểu thực mà trình biên dịch đã suy ra.

### 5.2. Bộ nhớ: heap, stack và class metadata

| Thành phần | Vai trò cần nắm | Ví dụ |
| --- | --- | --- |
| Heap | Vùng bộ nhớ được JVM quản lý cho đối tượng/array về mặt mô hình chương trình | `new ArrayList<>()` tạo đối tượng; chi tiết bố trí có thể được JVM tối ưu |
| Stack của mỗi thread | Các frame của lời gọi phương thức, giá trị cục bộ và thông tin thực thi | Lời gọi lồng nhau, biến cục bộ |
| Class metadata / Metaspace (trên HotSpot hiện đại) | Thông tin cấu trúc lớp và phương thức phục vụ runtime | Lớp được nạp, liên kết và sử dụng |

Bảng là **mô hình khái niệm**, không phải cam kết mỗi biến luôn nằm ở một địa chỉ stack hoặc mọi cấp phát luôn tồn tại vật lý trên heap. JVM có thể tối ưu lưu trữ và loại bỏ cấp phát trung gian nếu giữ nguyên hành vi quan sát được.

Phân biệt hai trường hợp lỗi:

- `StackOverflowError` thường liên quan đến lời gọi đệ quy quá sâu hoặc dùng vượt khả năng stack của thread.
- `OutOfMemoryError` xuất hiện khi JVM không thể đáp ứng yêu cầu bộ nhớ/cấp phát; cần đọc thông báo thực tế để tìm vùng và nguyên nhân.

### 5.3. Garbage collection không thay thế quản lý tài nguyên

**GC (garbage collection)** có nhiệm vụ thu hồi bộ nhớ đối tượng không còn reachable theo những gốc tham chiếu mà JVM xét. Nó không có nghĩa mọi đối tượng “không dùng nữa theo ý định của lập trình viên” đều tự biến mất: một collection hoặc cache vẫn giữ tham chiếu có thể khiến dữ liệu tiếp tục sống và chiếm bộ nhớ.

GC cũng không thay thế việc đóng file, socket, kết nối hoặc những tài nguyên có vòng đời rõ ràng. Dùng try-with-resources cho kiểu triển khai `AutoCloseable`:

```java
// Đoạn minh họa bên trong phương thức có thể ném IOException:
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    String firstLine = reader.readLine();
    // Xử lý firstLine (có thể là null nếu file trống)
}
```

Ở đây `path` là đối tượng `java.nio.file.Path` đã được tạo trước đó; đây là **đoạn minh họa**, không phải chương trình độc lập. Reader được đóng khi ra khỏi khối try, kể cả khi có ngoại lệ.

Không dựa vào thời điểm chạy GC hay dùng `System.gc()` làm cơ chế giải phóng tài nguyên bắt buộc.

### 5.4. JVM, thread và an toàn dữ liệu

Mỗi thread có luồng thực thi và stack riêng, nhưng nhiều thread có thể truy cập cùng đối tượng. **GC tự động không khiến thao tác dùng chung dữ liệu trở nên thread-safe.**

- `synchronized` hỗ trợ loại trừ tương hỗ và các bảo đảm visibility khi các thread dùng cùng cơ chế khóa đúng cách.
- `volatile` hỗ trợ bảo đảm visibility và thứ tự bộ nhớ cho truy cập một biến, nhưng `counter++` vẫn là chuỗi đọc–tính–ghi, **không phải phép tăng atomic**.
- `AtomicInteger.incrementAndGet()` hoặc cơ chế đồng bộ phù hợp giúp tăng bộ đếm dùng chung đúng cách.

Đây là nền tảng để hiểu lỗi race condition, đồng thời tránh ngộ nhận rằng dùng `parallelStream()` sẽ mặc nhiên an toàn hoặc nhanh hơn.

## 6. Kết nối cả bốn kiến thức qua một ví dụ

Trong chương trình sau:

- `var` suy luận kiểu `List<Integer>` từ giá trị khởi tạo, đồng thời kiểu của `selected` là `List<Integer>`.
- Generics buộc các phần tử là `Integer` trong compile-time API.
- Stream lọc, loại trùng và sắp xếp các số.
- JVM thực thi bytecode được biên dịch từ chương trình.

```java
// KnowledgeDemo.java
import java.util.ArrayList;
import java.util.List;

public class KnowledgeDemo {
    public static void main(String[] args) {
        var scores = new ArrayList<Integer>(List.of(8, 6, 9, 8));

        var selected = scores.stream()
                .filter(score -> score >= 8)
                .distinct()
                .sorted()
                .toList();

        int total = selected.stream()
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println(selected);
        System.out.println(total);
        System.out.println(scores.size());
    }
}
```

Chạy:

```bash
javac KnowledgeDemo.java
java KnowledgeDemo
```

Kết quả:

```text
[8, 9]
17
4
```

`selected` là danh sách kết quả không cho sửa bằng `add`; `scores` là `ArrayList<Integer>` có thể sửa. Vì pipeline không sửa `scores`, danh sách nguồn vẫn chứa bốn phần tử. Không có chuyển kiểu động nào được thực hiện chỉ vì dùng `var`.

## 7. Những nhầm lẫn phổ biến và cách tránh

1. **“`var` là `Object` hoặc `dynamic`.”** Sai: `var` yêu cầu trình biên dịch suy ra kiểu tĩnh từ initializer; vẫn kiểm tra gán và gọi phương thức theo kiểu đó.
2. **“`List<Integer>` có thể truyền vào mọi chỗ nhận `List<Number>`.”** Sai: generics invariant; dùng wildcard có chủ đích khi API cần đọc/ghi trên họ kiểu.
3. **“Generic type còn nguyên trên từng đối tượng lúc runtime.”** Sai trong trường hợp generics dựa trên type erasure; không viết `instanceof List<String>`.
4. **“Stream tạo ra danh sách mới ngay khi gọi `filter`.”** Sai: thao tác trung gian thường lazy; chỉ terminal operation mới đánh giá pipeline.
5. **“`toList()` trả danh sách mutable.”** Sai với `Stream.toList()`; hãy chọn collector có bảo đảm cụ thể nếu cần thay đổi.
6. **“Stream luôn nhanh hơn vòng lặp và `parallel()` luôn nhanh hơn `stream()`.”** Sai: chọn theo độ rõ ràng, chi phí và số đo thực tế.
7. **“Có GC thì không cần đóng tài nguyên.”** Sai: đóng tài nguyên bằng API có vòng đời xác định, ví dụ try-with-resources.
8. **“`volatile` biến mọi phép toán trên biến thành atomic.”** Sai: tăng biến kiểu `counter++` cần cơ chế đồng bộ/atomic phù hợp nếu nhiều thread cùng cập nhật.

## 8. Tự kiểm tra sau bài học

- Khi gặp `var data = List.of("A", "B");`, kiểu biên dịch của `data` là gì? **`List<String>`**, không phải “dynamic”.
- Vì sao `List<Integer>` không truyền trực tiếp thành `List<Number>`? **Để tránh thêm một phần tử `Number` không phải `Integer` vào tập hợp gốc.**
- API chỉ cần duyệt danh sách số nên nhận `List<? extends Number>` hay `List<? super Number>`? **`? extends Number`** khi tham số đóng vai trò nguồn đọc.
- Hai pipeline gọi `source.stream()` riêng rẽ có độc lập không? **Có**; chúng tạo hai Stream mới từ cùng nguồn. Một Stream đã tiêu thụ thì không tái sử dụng.
- Với `List.of(1, 2, 3).stream().filter(n -> n > 1).mapToInt(n -> n).sum()`, kết quả là gì? **5**.
- Một đối tượng không còn biến cục bộ trỏ tới có chắc được GC ngay không? **Không**; có thể còn tham chiếu reachable khác, và thời điểm GC không được cam kết.
- `javac` và `java` khác nhau thế nào? **`javac` biên dịch nguồn thành bytecode; `java` khởi động runtime để thực thi chương trình đã biên dịch.**

**Thực hành gợi ý:** chạy ba chương trình `StaticTypingDemo`, `GenericsDemo` và `StreamDemo` với JDK 17+; sau đó tự thay một chỗ gán sai kiểu để quan sát lỗi biên dịch, thay `? extends` bằng `? super` để hiểu quyền đọc/ghi, và thêm/bỏ một terminal operation để quan sát tính lazy của Stream. Các thí nghiệm này nối trực tiếp kiểm tra kiểu khi biên dịch với hành vi khi JVM thực thi.