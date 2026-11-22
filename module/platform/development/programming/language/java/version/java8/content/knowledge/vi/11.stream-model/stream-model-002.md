# Nguồn, thao tác trung gian và thao tác kết thúc trong Java Stream

## 1. Tổng quan: một Stream pipeline gồm những gì?

**Java Stream API** (`java.util.stream`) được giới thiệu trong Java 8 và tiếp tục là công cụ quan trọng để xử lý dãy phần tử theo cách khai báo. Thay vì tự viết nhiều vòng lặp và biến tạm, ta mô tả **dữ liệu đi từ đâu, được biến đổi/lọc như thế nào và kết quả cuối cùng được lấy ra ra sao**.

Một *stream pipeline* gồm ba phần:

1. **Nguồn (source)**: dữ liệu hoặc bộ sinh phần tử, ví dụ `List`, mảng, một dãy số hoặc luồng đọc dòng từ tệp.
2. **Không hoặc nhiều thao tác trung gian (intermediate operations)**: trả về một Stream khác để xây pipeline, ví dụ `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`.
3. **Một thao tác kết thúc (terminal operation)**: bắt đầu đánh giá pipeline để tạo kết quả hoặc tác động, ví dụ `toList`, `collect`, `count`, `reduce`, `findFirst`, `anyMatch`, `forEach`.

Sơ đồ tổng quát:

~~~text
SOURCE                     INTERMEDIATE OPERATIONS                 TERMINAL
List<String>  -> stream -> filter(...) -> map(...) -> distinct() -> toList()
                                   \___ pipeline được xây trước ___/
~~~

Ví dụ ngắn, dành cho JDK 17+:

~~~java
import java.util.List;

List<String> names = List.of("An", "Binh", "Anh", "Bao");

List<String> result = names.stream()
        .filter(name -> name.startsWith("A"))
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [AN, ANH]
~~~

Đây là **mảnh mã minh họa** nằm trong một method có ngữ cảnh Java phù hợp; không phải tệp chạy độc lập. Cách đọc pipeline: lấy các tên từ `names`, giữ những tên bắt đầu bằng `A`, biến chúng thành chữ in hoa, rồi gom kết quả vào một danh sách.

**Quan trọng:** `List.of` được bổ sung từ Java 9 và `Stream.toList()` từ Java 16. Khái niệm nguồn — trung gian — kết thúc và các phép `filter`/`map` đã có từ Java 8. Những ví dụ ở đây ưu tiên JDK 17+ và chỉ dùng API còn phù hợp trong Java hiện đại.

## 2. Stream không phải Collection và không chứa dữ liệu độc lập

Một `Stream<T>` là **mô tả một luồng thao tác với các phần tử**, không phải một container giống `List<T>` hoặc `Set<T>`.

| Đặc tính | `Collection` | `Stream` |
| --- | --- | --- |
| Mục tiêu chính | Lưu/truy cập tập phần tử | Khai báo và thực hiện phép xử lý phần tử |
| Có thể duyệt lại | Thông thường có | Không được tái sử dụng một stream đã tiêu thụ |
| Có các phép sửa như `add`/`remove` | Tùy collection | Không |
| Có thể nối các thao tác lazy | Không phải mô hình cốt lõi | Có |
| Tạo kết quả mới | Có thể dùng API collection | Dùng terminal như `collect`, `toList` |
| Tài nguyên bên ngoài | Phụ thuộc implementation | Một số nguồn Stream cần đóng tài nguyên |

Lệnh:

~~~java
Stream<String> stream = names.stream();
~~~

không có nghĩa toàn bộ phần tử được sao chép sang một danh sách khác. Stream lấy nguồn đã khai báo và có cơ chế duyệt nguồn khi pipeline được đánh giá.

Nếu cần **xử lý lại cùng dữ liệu**, hãy tạo **stream mới từ nguồn**:

~~~java
long count = names.stream().count();
List<String> copy = names.stream().toList();
~~~

Đây là hai stream khác nhau. Không lưu một `Stream` vào field rồi kỳ vọng tái sử dụng nhiều lần như một `List`.

## 3. Nguồn Stream phổ biến

### 3.1. Collection

~~~java
List<String> items = List.of("java", "kotlin", "go");
Stream<String> stream = items.stream();
~~~

`Collection.stream()` tạo stream tuần tự; `parallelStream()` tạo stream có chế độ song song. Việc bật parallel không tự đảm bảo nhanh hơn.

### 3.2. Mảng

~~~java
String[] words = {"java", "stream"};
Stream<String> all = java.util.Arrays.stream(words);
~~~

Với mảng primitive, `Arrays.stream(int[])` trả về `IntStream`, không phải `Stream<Integer>`. Các primitive stream như `IntStream`, `LongStream`, `DoubleStream` hỗ trợ tính tổng, trung bình và tránh boxing không cần thiết.

### 3.3. Giá trị được cung cấp trực tiếp

~~~java
Stream<Integer> numbers = Stream.of(1, 2, 3, 4);
Stream<String> empty = Stream.empty();
~~~

`Stream.of(...)` lấy các phần tử đã truyền; `Stream.empty()` tạo một nguồn rỗng.

### 3.4. Dãy số

~~~java
java.util.stream.IntStream range =
        java.util.stream.IntStream.range(1, 5);
~~~

`IntStream.range(1, 5)` sinh các số `1, 2, 3, 4`: đầu **bao gồm**, cuối **không bao gồm**. `IntStream.rangeClosed(1, 5)` bao gồm cả `5`.

### 3.5. Sinh phần tử theo yêu cầu

~~~java
Stream<Double> randoms = Stream.generate(Math::random).limit(3);
~~~

`Stream.generate` có thể sinh dãy vô hạn. `limit(3)` làm nguồn hữu hạn trong pipeline minh họa; kết quả ngẫu nhiên không có stdout cố định. `Stream.iterate` cũng hỗ trợ mô hình sinh dãy; overload có điều kiện dừng từ Java 9.

### 3.6. Nguồn có tài nguyên I/O

~~~java
// Mảnh mã minh họa, cần import java.nio.file.*;
try (Stream<String> lines =
             java.nio.file.Files.lines(
                     java.nio.file.Path.of("input.txt"))) {
    long nonEmpty = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonEmpty);
}
~~~

`Files.lines` trả stream liên quan một tài nguyên tệp. Nên dùng **try-with-resources** để đóng stream; terminal `count()` không được coi là lời hứa tự đóng tài nguyên. Ví dụ này cần tệp thật `input.txt`, không có stdout cố định. `Path.of` và `String.isBlank` cần Java 11+.

## 4. Thao tác trung gian: xây pipeline và trả về Stream

**Intermediate operation** có đầu vào là một Stream và trả về một Stream khác; nó thường chỉ ghi nhận cách phần tử sẽ được xử lý, **chưa duyệt dữ liệu ngay**.

Ví dụ:

~~~java
Stream<String> pipeline = Stream.of(" java ", "go", "scala")
        .map(String::trim)
        .filter(s -> s.length() > 2);
~~~

Ở thời điểm gán biến `pipeline`, thông thường chưa có lời gọi `trim` hoặc predicate `filter` cho các phần tử; pipeline mới đang được cấu hình. Khi gọi `pipeline.toList()`, quá trình xử lý mới thực sự được yêu cầu.

### Bảng các thao tác trung gian thường gặp

| Thao tác | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `filter(Predicate)` | Chỉ giữ phần tử thỏa điều kiện | Số phần tử có thể giảm |
| `map(Function)` | Biến đổi mỗi phần tử sang một giá trị khác | Có thể đổi kiểu `T -> R` |
| `flatMap(Function)` | Ánh xạ mỗi phần tử thành một Stream rồi trải phẳng | Hữu ích với danh sách lồng nhau |
| `distinct()` | Giữ phần tử không trùng theo `equals` | Có thể cần lưu trạng thái |
| `sorted()`/`sorted(Comparator)` | Sắp xếp phần tử | Có thể cần gom/buffer |
| `limit(n)` | Giới hạn tối đa `n` phần tử | Short-circuit với điều kiện phù hợp |
| `skip(n)` | Bỏ qua `n` phần tử đầu | Trên stream có thứ tự |
| `peek(Consumer)` | Quan sát phần tử trong pipeline | Không nên dùng cho side effect bắt buộc |
| `mapToInt`/`mapToLong`/`mapToDouble` | Chuyển sang primitive stream | Tốt cho tính toán số |

Java 9 thêm `takeWhile` và `dropWhile`; Java 16 thêm `mapMulti`. Đây là các khả năng vẫn được sử dụng hiện nay, nhưng không nên gắn nhãn chúng là API Java 8.

### `filter`: lọc theo predicate

~~~java
Stream.of(1, 2, 3, 4, 5)
        .filter(n -> n % 2 == 0)
        .toList(); // [2, 4]
~~~

### `map`: mỗi phần tử thành một phần tử mới

~~~java
Stream.of("one", "two")
        .map(String::length)
        .toList(); // [3, 3]
~~~

`map` có thể đổi `Stream<String>` thành `Stream<Integer>`. Nó không sửa trực tiếp các chuỗi nguồn. Nếu lambda trong `map` sửa trạng thái của object được tham chiếu thì vẫn có side effect, nhưng đó là lựa chọn của người viết lambda, không phải ý nghĩa cốt lõi của `map`.

### `flatMap`: từ nhiều Stream lồng nhau thành một

~~~java
List<List<Integer>> matrix =
        List.of(List.of(1, 2), List.of(3, 4));
List<Integer> flattened = matrix.stream()
        .flatMap(List::stream)
        .toList(); // [1, 2, 3, 4]
~~~

Nếu chỉ dùng `map(List::stream)`, kiểu kết quả là `Stream<Stream<Integer>>`, không phải dãy `Integer` đã được trải phẳng.

### `sorted`, `distinct`, `limit`

~~~java
Stream.of(5, 2, 5, 1, 2)
        .distinct()
        .sorted()
        .limit(2)
        .toList(); // [1, 2]
~~~

`distinct()` loại trùng theo `Object.equals`; `sorted()` cần phần tử so sánh được hoặc comparator phù hợp. `limit(2)` là thao tác trung gian, **không phải** terminal dù có thể làm việc duyệt nguồn dừng sớm.

## 5. Thao tác kết thúc: nơi đánh giá pipeline được kích hoạt

Terminal operation tạo kết quả, tác động cuối cùng hoặc tín hiệu hoàn thành. Với một stream tuần tự đơn giản, nó thường kích hoạt việc lấy phần tử từ source rồi thực hiện các trung gian theo pipeline.

| Terminal | Kiểu kết quả thường gặp | Mục đích |
| --- | --- | --- |
| `toList()` | `List<T>` | Thu kết quả vào List không sửa được qua API List |
| `collect(Collector)` | Tùy Collector | Gom, phân nhóm, nối chuỗi, tổng hợp |
| `count()` | `long` | Đếm phần tử |
| `reduce(...)` | Tùy overload: `T` hoặc `Optional<T>` | Gộp phần tử bằng phép kết hợp |
| `findFirst()` | `Optional<T>` | Tìm phần tử đầu theo encounter order nếu tồn tại |
| `findAny()` | `Optional<T>` | Tìm một phần tử, nhất là khi parallel |
| `anyMatch`/`allMatch`/`noneMatch` | `boolean` | Kiểm tra điều kiện, có thể dừng sớm |
| `min`/`max` | `Optional<T>` | Chọn cực trị |
| `forEach(Consumer)` | `void` | Thực hiện hành động trên phần tử |
| `forEachOrdered(Consumer)` | `void` | Tôn trọng encounter order nếu stream có thứ tự |

Một số terminal đặc biệt không nhất thiết duyệt toàn bộ nguồn, và một số có thể được tối ưu hóa không gọi các biểu thức trung gian nếu kết quả xác định được. Vì vậy **đừng dùng side effect trong `map`/`peek` để đếm số phần tử thực sự đã được xử lý**.

### `Stream.toList()` và `Collectors.toList()` không tương đương hoàn toàn

- `stream.toList()` (Java 16+) trả một danh sách **unmodifiable**: gọi `add`, `remove` hoặc `set` sẽ ném `UnsupportedOperationException`.
- `stream.collect(Collectors.toList())` đã có từ Java 8; **không cam kết** kiểu implementation, mutability, serializability hay thread safety của danh sách thu được.
- Nếu cần danh sách có thể thay đổi, viết rõ:
  `stream.collect(Collectors.toCollection(ArrayList::new))`.
- Nếu cần kết quả cố định không sửa được, `toList()` thể hiện ý đồ rõ trên JDK 16+.

Đừng chuyển toàn bộ ví dụ Java 8 sang `toList()` mà không ghi phiên bản tối thiểu; ngược lại, một codebase Java 17+ không cần tránh `toList()` chỉ vì nó được bổ sung sau Java 8.

## 6. Tính lazy và sự khác nhau giữa pipeline được tạo với pipeline được chạy

Một điểm dễ nhầm: **việc gọi intermediate operation chưa có nghĩa logic đã được thực thi trên dữ liệu**.

~~~java
Stream<Integer> prepared = Stream.of(1, 2, 3)
        .filter(n -> {
            System.out.println("checking " + n);
            return n > 1;
        });
// Đến đây thông thường chưa in "checking ..."
~~~

Khi gọi terminal:

~~~java
List<Integer> answer = prepared.toList();
~~~

mới có yêu cầu đánh giá predicate. Với pipeline tuần tự không có stateful stage phức tạp, việc đánh giá thường **fused**: lấy từng phần tử, lọc, biến đổi, đưa đến downstream, rồi mới lấy phần tử tiếp theo. Nó không cần tạo một list tạm sau từng thao tác.

Tuy nhiên **không nên khẳng định mọi intermediate luôn chạy đúng một lần cho mỗi phần tử**. Stream API cho phép tối ưu hóa pipeline, đặc biệt khi terminal biết kết quả từ kích thước nguồn hoặc khi thao tác short-circuit; `peek` không phải một callback bắt buộc được chạy nếu không cần đánh giá phần tử.

### Vì sao `count()` là ví dụ cần thận trọng?

Với một nguồn đã biết số lượng và pipeline không thay đổi kích thước, `count()` có thể trả kết quả mà **không duyệt** từng phần tử, nên các side effect trong `peek` hoặc `map` có thể không xảy ra. Đó không phải bug. Nếu có logic nghiệp vụ phải chạy cho từng phần tử, hãy thiết kế logic đó tường minh thay vì dựa vào `peek` được gọi khi `count()` thực hiện.

## 7. Ví dụ chạy đầy đủ 1 — một pipeline có nguồn, trung gian và kết thúc

Tạo file **StreamPipelineDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;

public class StreamPipelineDemo {

    public static void main(String[] args) {
        List<String> source = List.of(
                "  java  ", "kotlin", "java",
                "  go ", "scala", "JAVA");

        List<String> result = source.stream()        // SOURCE
                .map(String::trim)                   // INTERMEDIATE
                .filter(s -> s.length() >= 4)       // INTERMEDIATE
                .map(s -> s.toUpperCase(Locale.ROOT))// INTERMEDIATE
                .distinct()                         // INTERMEDIATE
                .sorted()                           // INTERMEDIATE
                .toList();                          // TERMINAL

        System.out.println("source-size=" + source.size());
        System.out.println("source-unchanged="
                + source.get(0).equals("  java  "));
        System.out.println("result=" + result);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac StreamPipelineDemo.java
java StreamPipelineDemo
~~~

**Stdout chính xác:**

~~~text
source-size=6
source-unchanged=true
result=[JAVA, KOTLIN, SCALA]
~~~

Đọc theo từng bước:

1. `List.of(...)` tạo **nguồn** có 6 phần tử.
2. `source.stream()` tạo `Stream<String>`.
3. `map(String::trim)` bỏ khoảng trắng hai đầu; không sửa `source` vì `String` immutable và `map` tạo ra giá trị mới.
4. `filter(s -> s.length() >= 4)` bỏ `"go"`.
5. `map(...toUpperCase(Locale.ROOT))` tạo chữ hoa theo locale ổn định, tránh bất ngờ phụ thuộc locale mặc định trên máy.
6. `distinct()` bỏ các bản `JAVA` lặp, dựa trên `equals`.
7. `sorted()` sắp xếp thứ tự tự nhiên của `String`.
8. `toList()` **kích hoạt pipeline** và tạo danh sách kết quả không sửa được.

Điểm kiểm tra `source-unchanged=true` chứng minh trong ví dụ này pipeline không sửa dữ liệu gốc. Không suy ra mọi lambda đều không có tác dụng phụ: một lambda có thể cố ý sửa object có thể thay đổi, nhưng đó thường là thiết kế rủi ro.

## 8. Short-circuit: terminal có thể dừng trước khi hết nguồn

Không phải terminal nào cũng cần toàn bộ phần tử. Những terminal như `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` có thể **short-circuit** — ngừng lấy thêm phần tử khi đã biết kết quả.

Ví dụ ngắn:

~~~java
boolean exists = Stream.of(1, 3, 6, 8)
        .anyMatch(n -> n % 2 == 0);
// true: có thể dừng khi gặp 6.
~~~

Với stream tuần tự có encounter order như `Stream.of`, `findFirst()` trả phần tử đầu tiên thỏa pipeline. Với stream **unordered** hoặc parallel, đặc điểm dừng và lịch đánh giá có thể khác; không dựa vào nhật ký side effect để suy thứ tự chung.

### Ví dụ chạy đầy đủ 2 — thời điểm thật sự thực thi

Tạo file **StreamLazyDemo.java**:

~~~java
import java.util.Optional;
import java.util.stream.Stream;

public class StreamLazyDemo {

    public static void main(String[] args) {
        System.out.println("building");

        Stream<Integer> pipeline = Stream.of(1, 2, 3, 4, 5)
                .filter(n -> {
                    System.out.println("filter=" + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    System.out.println("map=" + n);
                    return n * 10;
                });

        System.out.println("before-terminal");
        Optional<Integer> result = pipeline.findFirst();
        System.out.println("first=" + result.orElse(-1));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StreamLazyDemo.java
java StreamLazyDemo
~~~

**Stdout chính xác:**

~~~text
building
before-terminal
filter=1
filter=2
map=2
first=20
~~~

Giải thích:

- Khi viết `Stream.of(...).filter(...).map(...)`, chỉ đang tạo pipeline; trước `findFirst()` chưa in `filter` hoặc `map`.
- `findFirst()` bắt đầu lấy phần tử. `1` bị loại nên không qua `map`.
- `2` qua filter, `map` chuyển thành `20`; vì đây là phần tử đầu tiên đi đến cuối pipeline, `findFirst` có kết quả và dừng.
- `3, 4, 5` không bị xử lý trong ví dụ tuần tự này.
- `Optional<Integer>` có giá trị; `orElse(-1)` là fallback khi rỗng. Nó không làm `findFirst` chọn `-1` nếu phần tử `0` hợp lệ.

**Lưu ý:** thứ tự output này được xác định cho chính ví dụ **stream tuần tự có thứ tự**. Không dùng thứ tự này để cam kết logging khi chuyển sang `parallel()`.

## 9. Intermediate stateless và stateful: vì sao `sorted` khác `filter`?

Một số intermediate operation có thể xử lý từng phần tử tương đối độc lập:

- `filter`: quyết định giữ/bỏ một phần tử từ predicate.
- `map`: chuyển một phần tử bằng mapper.
- `peek`: thực hiện action khi phần tử được tiêu thụ (nhưng không bảo đảm action luôn được gọi nếu pipeline tối ưu).

Các thao tác này thường được gọi là **stateless intermediate operations** nếu chức năng được truyền vào cũng tuân theo yêu cầu không dựa vào trạng thái thay đổi bên ngoài.

Ngược lại:

- `sorted` cần hiểu thứ tự tương đối, thường phải gom/buffer nhiều phần tử trước khi đưa ra kết quả đã sắp xếp.
- `distinct` cần biết phần tử nào đã gặp để loại trùng; việc lưu trạng thái có thể đáng kể.
- `limit`/`skip` xử lý phần cắt, liên quan số lượng và encounter order; đối với parallel ordered streams có thể phát sinh chi phí phối hợp.

Vì vậy **lazy không có nghĩa không dùng bộ nhớ** và **pipeline không có list trung gian** không có nghĩa mọi phép đều xử lý online từng phần tử với bộ nhớ O(1). `sorted()` trên nguồn lớn có thể cần bộ nhớ để sắp xếp.

### Thứ tự intermediate ảnh hưởng chi phí và kết quả

Ví dụ:

~~~java
Stream.of(9, 1, 8, 2, 7)
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList(); // [2, 8]
~~~

Lọc trước sắp xếp giúp `sorted` nhìn thấy ít phần tử hơn. Nhưng đổi `limit` và `sorted` có thể **đổi ý nghĩa**:

~~~java
Stream.of(9, 1, 8, 2, 7)
        .limit(3)
        .sorted()
        .toList(); // [1, 8, 9]

Stream.of(9, 1, 8, 2, 7)
        .sorted()
        .limit(3)
        .toList(); // [1, 2, 7]
~~~

Đây là các mảnh mã minh họa. Việc tối ưu thứ tự pipeline phải giữ **ngữ nghĩa yêu cầu**, không chỉ nghĩ đến tốc độ.

## 10. `flatMap` và stream lồng nhau

Nguồn có thể là tập các danh sách. Muốn xử lý **từng phần tử trong mọi danh sách**, dùng `flatMap`:

~~~java
List<List<Integer>> groups = List.of(
        List.of(1, 2), List.of(3, 4), List.of(5));

List<Integer> flattened = groups.stream()
        .flatMap(List::stream)
        .toList();

// [1, 2, 3, 4, 5]
~~~

Nhìn vào kiểu:

- `groups.stream()`: `Stream<List<Integer>>`.
- `map(List::stream)`: `Stream<Stream<Integer>>`.
- `flatMap(List::stream)`: `Stream<Integer>`.
- `toList()`: `List<Integer>`.

`flatMap` thích hợp khi mỗi phần tử nguồn tương ứng **0, 1 hoặc nhiều phần tử đầu ra**. Khi cần lọc và biến đổi mà vẫn giữ số phần tử (trừ filter), `map` thường đủ.

### Ví dụ chạy đầy đủ 3 — flatten và danh sách kết quả unmodifiable

Tạo file **StreamFlatMapDemo.java**:

~~~java
import java.util.List;

public class StreamFlatMapDemo {

    public static void main(String[] args) {
        List<List<Integer>> groups = List.of(
                List.of(1, 2),
                List.of(3, 4),
                List.of(5));

        List<Integer> result = groups.stream()
                .flatMap(List::stream)
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .toList();

        System.out.println("groups=" + groups.size());
        System.out.println("result=" + result);

        try {
            result.add(60);
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable=true");
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac StreamFlatMapDemo.java
java StreamFlatMapDemo
~~~

**Stdout chính xác:**

~~~text
groups=3
result=[20, 40]
unmodifiable=true
~~~

Khi `toList()` trả một danh sách unmodifiable, `result.add(60)` ném `UnsupportedOperationException`, được bắt để in kết quả. **Không** suy từ đó rằng các phần tử object bên trong danh sách cũng bất biến sâu; ví dụ này dùng `Integer` bất biến.

Nếu cần danh sách chỉnh sửa được, chọn terminal `collect(Collectors.toCollection(ArrayList::new))` và import `Collectors`, `ArrayList` phù hợp.

## 11. Các terminal quan trọng ngoài `toList()`

### `count`

~~~java
long count = Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .count(); // 2
~~~

`count()` có kiểu kết quả `long`, không phải `int`. Nó có thể tối ưu hóa theo đặc tính source/pipeline, nên không dùng side effect để suy số lần mapper được gọi.

### `reduce`

~~~java
int sum = Stream.of(2, 3, 5)
        .reduce(0, Integer::sum); // 10
~~~

`0` là identity; `Integer::sum` là phép kết hợp phù hợp. Đặc biệt với stream parallel, accumulator/combiner phải thỏa các yêu cầu liên quan identity, associativity và tương thích để kết quả đúng. Không viết reduce phụ thuộc thứ tự không được đảm bảo hoặc dùng biến global mutable làm bộ tích lũy.

Overload không có identity trả `Optional<T>` vì stream có thể rỗng:

~~~java
java.util.Optional<Integer> max =
        Stream.<Integer>empty().reduce(Integer::max);
// Optional.empty()
~~~

### `collect`

~~~java
String joined = Stream.of("Java", "Stream", "API")
        .collect(java.util.stream.Collectors.joining(" | "));
// "Java | Stream | API"
~~~

`collect` nhận collector để tổ chức kết quả; có thể gom vào list, set, map, nhóm, phân vùng hoặc tổng hợp số liệu. Nó là **terminal**: khác với `map`/ `filter` vốn trả stream để tiếp tục pipeline.

### `findFirst` và `findAny`

- `findFirst` chọn phần tử đầu tiên theo **encounter order** nếu có thứ tự; kết quả là `Optional<T>`.
- `findAny` có thể chọn bất kỳ phần tử phù hợp; hữu ích trong một số pipeline parallel khi không cần ưu tiên phần tử đầu.
- Nếu stream chứa `null` và terminal cố đưa `null` vào `Optional`, một số phép như `findFirst` có thể ném `NullPointerException`; tránh giả định Stream luôn tự chuyển null thành `Optional.empty()`.

### `anyMatch`, `allMatch`, `noneMatch`

~~~java
boolean anyEven = Stream.of(1, 3, 4).anyMatch(n -> n % 2 == 0);
// true

boolean allPositive = Stream.of(1, 2, 3).allMatch(n -> n > 0);
// true

boolean noneNegative = Stream.of(1, 2, 3).noneMatch(n -> n < 0);
// true
~~~

Trên stream rỗng: `anyMatch` trả `false`; `allMatch` và `noneMatch` trả `true` theo quy tắc logic tương ứng. Đừng viết một validator “allMatch” mà hiểu sai stream rỗng sẽ tự bị từ chối. Nếu nghiệp vụ bắt buộc có ít nhất một phần tử, phải kiểm tra điều kiện đó riêng.

## 12. Ví dụ chạy đầy đủ 4 — terminal `collect`, `sum`, `count`, `max`

Tạo file **StreamTerminalDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StreamTerminalDemo {

    record Sale(String category, int units) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("book", 2),
                new Sale("pen", 3),
                new Sale("book", 5),
                new Sale("pen", 1));

        Map<String, Integer> totals = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::units)));

        int totalUnits = sales.stream()
                .mapToInt(Sale::units)
                .sum();

        long biggerThanTwo = sales.stream()
                .filter(sale -> sale.units() > 2)
                .count();

        String categoryOfMax = sales.stream()
                .max(Comparator.comparingInt(Sale::units))
                .map(Sale::category)
                .orElse("none");

        System.out.println("totals=" + totals);
        System.out.println("sum=" + totalUnits);
        System.out.println("count=" + biggerThanTwo);
        System.out.println("max-category=" + categoryOfMax);
    }
}
~~~

Lệnh chạy bằng JDK 17+ (record được chuẩn hóa từ Java 16):

~~~bash
javac StreamTerminalDemo.java
java StreamTerminalDemo
~~~

**Stdout chính xác:**

~~~text
totals={book=7, pen=4}
sum=11
count=2
max-category=book
~~~

Giải thích:

1. `sales.stream()` tạo **stream mới cho mỗi lần xử lý**; không dùng lại một stream đã tiêu thụ.
2. `collect(groupingBy(...))` gom theo `category`, dùng `TreeMap` để thứ tự key `book`, `pen` ổn định và `summingInt` cộng `units`.
3. `mapToInt(Sale::units).sum()` dùng `IntStream` và terminal `sum()` để tính `2 + 3 + 5 + 1 = 11`.
4. `filter(...).count()` đếm hai sale có units lớn hơn 2 (3 và 5).
5. `max(...)` trả `Optional<Sale>` cho sale có units lớn nhất (5); `map(Sale::category)` lấy `book`. `orElse("none")` xử lý trường hợp rỗng.
6. Dùng `TreeMap` ở đây là lựa chọn **cố ý** để stdout không phụ thuộc thứ tự duyệt của `HashMap` trong một ví dụ giảng dạy.

**Góc nhìn thiết kế:** khi pipeline cần nhiều phép tổng hợp khác nhau, các terminal riêng trên các stream mới là một cách rõ ràng. Nếu nguồn cực lớn hoặc tốn I/O, có thể thiết kế một collector tổng hợp nhiều chỉ số trong một lượt, nhưng cần đảm bảo collector đúng với quy tắc kết hợp, nhất là khi xử lý parallel.

## 13. Stream chỉ dùng một lần

Một trong những lỗi điển hình là cố gọi hai terminal lên cùng một stream:

~~~java
Stream<String> values = Stream.of("A", "B");
long count = values.count();
List<String> list = values.toList(); // Sai: stream đã consumed.
~~~

Mã trên **cố ý không biên dịch/chạy thành công toàn bộ** theo ý nghĩa runtime: nó biên dịch được, nhưng lời gọi terminal thứ hai ném `IllegalStateException` khi stream đã bị tiêu thụ. Chỉ dùng một terminal trên mỗi stream; tạo stream mới khi cần chạy lại.

### Ví dụ chạy đầy đủ 5 — tái sử dụng stream và xử lý lỗi

Tạo file **StreamSingleUseDemo.java**:

~~~java
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSingleUseDemo {

    public static void main(String[] args) {
        Stream<String> pipeline = Stream.of("A", "B");

        String joined = pipeline.collect(Collectors.joining(","));
        System.out.println("joined=" + joined);

        try {
            pipeline.count();
        } catch (IllegalStateException expected) {
            System.out.println("reused=blocked");
        }

        long freshCount = Stream.of("A", "B").count();
        System.out.println("fresh-count=" + freshCount);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StreamSingleUseDemo.java
java StreamSingleUseDemo
~~~

**Stdout chính xác:**

~~~text
joined=A,B
reused=blocked
fresh-count=2
~~~

Sau `collect`, `pipeline` đã được tiêu thụ; không có thao tác `reset` để chạy lại. Với nguồn dữ liệu có thể duyệt lại như `List`, gọi `list.stream()` lần nữa. Với nguồn I/O tiêu thụ một lần, phải hiểu cách mở hoặc tái tạo nguồn, không cố tái sử dụng stream đã đóng.

### Không tiếp tục gắn trung gian sau khi stream đã tiêu thụ

Cũng không hợp lệ khi xây thêm `filter`, `map` hoặc một operation khác từ stream đã được vận hành trước đó. Một stream pipeline về bản chất dành cho **một lượt đánh giá**; việc thao tác trên object đã sử dụng có thể ném `IllegalStateException`.

Không cố sửa bằng `parallel()`, `sequential()` hay `unordered()` trên stream đã được dùng; những phép đổi chế độ không reset dữ liệu.

## 14. Nguồn vô hạn và điều kiện kết thúc

`Stream.generate` và một số biến thể `iterate` có thể tạo dãy không giới hạn:

~~~java
Stream.generate(() -> 7);
~~~

Lệnh trên chỉ **tạo một nguồn**, không tự lặp vô hạn ngay lập tức. Nhưng nếu áp terminal cần xử lý tất cả phần tử trên một dãy vô hạn:

~~~java
// CỐ Ý KHÔNG CHẠY: terminal có thể không bao giờ kết thúc.
Stream.generate(() -> 7).count();
~~~

kết quả sẽ không thể được xác định bằng cách duyệt hết phần tử. Cần thêm điều kiện kết thúc khi bài toán yêu cầu xử lý hữu hạn:

~~~java
long count = Stream.generate(() -> 7)
        .limit(4)
        .count(); // 4
~~~

Tùy pipeline, short-circuit terminal như `findFirst` hoặc `anyMatch` có thể kết thúc trên nguồn vô hạn nếu điều kiện được tìm thấy; nhưng nếu điều kiện không bao giờ đạt và nguồn không kết thúc, `anyMatch` có thể chạy mãi.

### Đừng nghĩ `limit` tự làm mọi thứ rẻ

Với `sorted` đặt trước `limit` trên một nguồn vô hạn, `sorted` có thể cần xem toàn bộ nguồn trước khi biết thứ tự; pipeline có nguy cơ không kết thúc hoặc dùng rất nhiều bộ nhớ. Ngược lại, `limit(n)` trước `sorted` chỉ sắp xếp n phần tử đầu nguồn, nhưng **kết quả không giống** “n phần tử nhỏ nhất toàn bộ nguồn”.

Chọn thứ tự dựa trên semantics: cần top-N của nguồn hữu hạn hay chỉ cần lấy N phần tử đầu rồi xử lý?

## 15. Encounter order và xử lý song song

Một Stream có thể có **encounter order** tùy nguồn:

- `List.stream()` thường có encounter order theo thứ tự phần tử trong List.
- `Stream.of(...)` có thứ tự theo các phần tử cung cấp.
- `HashSet.stream()` không bảo đảm encounter order ổn định như `List`.
- `sorted()` áp một thứ tự kết quả theo comparator.
- `unordered()` có thể bỏ ràng buộc encounter order, không có nghĩa tự động xáo trộn phần tử.

Khi xử lý tuần tự, nhiều ví dụ quan sát được các phần tử theo thứ tự nguồn. Nhưng không nên thiết kế logic phụ thuộc vào thứ tự gọi side effect của intermediate, nhất là khi chuyển sang parallel.

### `forEach` và `forEachOrdered`

~~~java
// Mảnh mã minh họa:
List.of(1, 2, 3).parallelStream()
        .forEach(System.out::println);
~~~

`forEach` trên parallel stream **không bảo đảm thứ tự in**. Không nêu stdout cố định cho đoạn này.

Nếu cần giữ encounter order:

~~~java
List.of(1, 2, 3).parallelStream()
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` tuân theo encounter order (nếu stream có thứ tự), nhưng việc duy trì thứ tự có thể giảm lợi ích song song. Đừng mặc định `parallelStream()` giúp code chạy nhanh hơn: chi phí phân chia/ghép kết quả, kích thước dữ liệu và các thao tác stateful có thể khiến nó kém hiệu quả.

### `findFirst` so với `findAny`

Với ordered stream, `findFirst` có nghĩa “phần tử đầu tiên theo encounter order”. `findAny` được phép trả một phần tử bất kỳ, cho phép linh hoạt hơn trong xử lý song song. Nếu thuật toán yêu cầu một phần tử đầu rõ ràng, dùng `findFirst` và xác định order của nguồn; không giả định `findAny` sẽ luôn trả phần tử đầu chỉ vì vài lần chạy trên máy mình như vậy.

## 16. Hàm truyền cho Stream nên non-interfering và stateless

Stream API kỳ vọng các behavioral parameters của phần lớn thao tác, như predicate, mapper và comparator, **không gây can thiệp nguồn** (*non-interfering*) và **không phụ thuộc trạng thái thay đổi làm sai kết quả** (*stateless*) trừ khi API cụ thể quy định khác.

Ví dụ thiết kế rủi ro:

~~~java
// CỐ Ý minh họa thói quen không nên dùng:
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

List<Integer> output = numbers.stream()
        .peek(n -> numbers.add(n * 10))
        .toList();
~~~

Đoạn trên cần import `List` và `ArrayList`; **không chạy nó như logic hợp lệ**. Việc sửa collection nguồn trong lúc stream đang duyệt có thể gây `ConcurrentModificationException`, hành vi không nhất quán hoặc lỗi khác tùy nguồn/đường thực thi.

Một cách rõ ràng hơn:

~~~java
List<Integer> numbers = List.of(1, 2, 3);
List<Integer> output = numbers.stream()
        .map(n -> n * 10)
        .toList(); // [10, 20, 30]
~~~

Đây là mảnh mã minh họa JDK 17+. Kết quả được biến đổi riêng mà không sửa nguồn.

### Đừng dùng `peek` cho side effect quan trọng

`peek` hữu ích khi quan sát/debug pipeline, nhưng không cam kết callback của nó luôn được gọi theo cách nghiệp vụ yêu cầu. Một terminal có thể short-circuit; một pipeline khác có thể được tối ưu để không duyệt từng phần tử. Không dùng `peek` để ghi audit bắt buộc, gửi email, lưu database hoặc cộng tiền vào shared state.

Nếu thật sự cần side effect cho từng phần tử, hãy định nghĩa thao tác xử lý tường minh, chọn mô hình `forEach` có kiểm soát hoặc một vòng lặp phù hợp, chú ý thứ tự và ngoại lệ. Việc dùng stream không miễn trừ yêu cầu thread-safety và idempotence.

### Mutability của phần tử không biến mất

Dù Stream không trực tiếp sửa nguồn khi dùng mapper thuần, phần tử bên trong có thể là object mutable. Lambda như `item.setPrice(...)` vẫn sửa state. Đừng hiểu “functional pipeline” là bảo đảm bất biến về mặt ngôn ngữ; sự an toàn đến từ thiết kế behavioral parameters và dữ liệu.

## 17. Resource management: terminal không đồng nghĩa `close`

Phần lớn stream từ `List`, `Stream.of`, `Arrays.stream` không sở hữu tài nguyên ngoài cần đóng. Nhưng một số source I/O như `Files.lines(Path)` giữ tài nguyên cần được đóng.

Ví dụ đúng:

~~~java
// Mảnh mã minh họa, sử dụng khi tệp thực sự tồn tại:
try (Stream<String> lines = Files.lines(path)) {
    List<String> nonBlank = lines
            .filter(line -> !line.isBlank())
            .toList();
    use(nonBlank);
}
~~~

Đoạn này cần import `Files`, `Stream`, `List`, biến `path` kiểu `Path` và method `use`. Try-with-resources bảo đảm gọi `close()` khi rời block, kể cả khi có exception phù hợp. Không nên lưu `lines` ra ngoài rồi sử dụng sau khi block đóng.

### Cơ chế đóng stream và onClose

Có thể đăng ký handler qua `BaseStream.onClose(Runnable)`, rồi gọi `close()` hoặc dùng try-with-resources. **Terminal không tự đóng stream** chỉ vì pipeline đã kết thúc. Với nguồn tài nguyên, ranh giới sở hữu và lifecycle cần được ghi rõ.

Trong code có nhiều cấp stream, tránh để nguồn I/O bị đóng quá sớm. Nếu dùng `flatMap` với nested streams, Java có cơ chế đóng stream con theo trình tự được định nghĩa, nhưng vẫn phải quản lý việc đóng **outer resource stream** nếu outer stream sở hữu tài nguyên.

### Xử lý ngoại lệ trong pipeline I/O

Không biến checked exception từ I/O thành kết quả giả mà không có chính sách. `Files.lines` có thể ném `IOException` khi mở; lỗi I/O trong quá trình đọc có thể xuất hiện dưới dạng unchecked I/O exception phù hợp. Hãy xác định nơi catch/log/retry và cách đóng tài nguyên khi xảy ra lỗi.

## 18. Stream rỗng, null và `Optional`

### Stream rỗng

~~~java
long total = Stream.<String>empty().count(); // 0
java.util.Optional<String> first =
        Stream.<String>empty().findFirst();   // Optional.empty()
~~~

Không dereference `Optional.get()` mà không kiểm tra có giá trị. Thường dùng `orElse`, `orElseGet`, `ifPresent`, `map` hoặc `orElseThrow` phù hợp hợp đồng.

### Null trong nguồn

`Stream.of((String) null)` có một phần tử `null`, **không phải** stream rỗng:

~~~java
// Mảnh mã minh họa:
Stream.of((String) null)
        .filter(java.util.Objects::nonNull)
        .toList(); // []
~~~

Nếu gọi `map(String::length)` mà gặp null, pipeline có thể ném `NullPointerException`. Lọc null hoặc thiết kế nguồn không có null theo yêu cầu.

`Stream.ofNullable(value)` có từ Java 9 và giúp sinh stream 0/1 phần tử tùy `value` có null hay không:

~~~java
Stream.ofNullable(null).count(); // 0
Stream.ofNullable("x").count();  // 1
~~~

### `allMatch` trên nguồn rỗng

Như đã nói, `allMatch` trả `true` với stream rỗng. Nếu nghiệp vụ yêu cầu “danh sách không rỗng và mọi phần tử hợp lệ”, hãy kiểm tra độ rỗng ở nguồn hoặc thiết kế collector/predicate xử lý rõ hai điều kiện; không coi `allMatch` là phép xác nhận có dữ liệu.

## 19. Lựa chọn giữa vòng lặp và Stream

Stream mạnh khi các thao tác là **lọc — biến đổi — nhóm/tổng hợp** rõ ràng, không có nhiều side effect và có thể mô tả pipeline dễ đọc:

~~~java
List<String> valid = names.stream()
        .filter(s -> s != null && !s.isBlank())
        .map(String::trim)
        .toList();
~~~

Mảnh mã JDK 17+ này không ép buộc phải dùng Stream. Với một vòng lặp ngắn có nhiều nhánh, tác vụ I/O từng bước, xử lý lỗi phức tạp, phải giữ state hoặc cần early-exit có ngữ nghĩa rõ, vòng lặp truyền thống đôi khi dễ hiểu và đáng tin hơn.

Khi tối ưu hiệu năng, đo bằng benchmark và dữ liệu đại diện. Không tự giả định Stream nhanh hơn vòng lặp, hoặc `parallel()` nhanh hơn `sequential()`. Các yếu tố như boxing, allocation, kích thước nguồn, trạng thái pipeline, encounter order và chi phí collector đều ảnh hưởng.

## 20. Các lỗi phổ biến và cách sửa

| Ngộ nhận / lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `map` hoặc `filter` chạy ngay khi tạo pipeline | Intermediate thường lazy | Gắn terminal, hiểu lúc đánh giá |
| `limit` là terminal | Nó vẫn trả Stream | Thêm terminal phù hợp |
| `Stream` giữ dữ liệu như `List` | Stream là abstraction xử lý, không phải container có API sửa phần tử | Giữ nguồn Collection nếu cần dữ liệu lâu dài |
| Gọi hai terminal trên cùng Stream | Stream chỉ dùng một lần | Tạo Stream mới từ nguồn |
| `count` chắc chắn gọi `peek` một lần cho mỗi phần tử | Có thể tối ưu bỏ duyệt | Không đặt side effect quan trọng trong `peek` |
| Mọi intermediate đều dùng O(1) bộ nhớ | `sorted`/`distinct` có thể stateful | Kiểm tra chi phí và quy mô nguồn |
| `sorted().limit(3)` giống `limit(3).sorted()` | Kết quả có thể khác | Chọn thứ tự theo ý nghĩa |
| `map(List::stream)` cho phần tử phẳng | Trả stream lồng nhau | Dùng `flatMap(List::stream)` |
| `findAny` luôn trả phần tử đầu | Không có cam kết này | Dùng `findFirst` nếu cần đầu tiên |
| `parallel().forEach` luôn in đúng thứ tự | Không bảo đảm encounter order | Dùng `forEachOrdered` nếu cần |
| `Stream.toList()` trả List mutable | Từ Java 16 trả unmodifiable | Dùng collector toCollection khi muốn sửa |
| `Collectors.toList()` luôn trả `ArrayList` | Không có cam kết implementation/mutability | Đặt collector cụ thể |
| `Files.lines` tự đóng sau `count()` | Terminal không tự close resource | Dùng try-with-resources |
| `allMatch` trên nguồn rỗng phải false | Vacuous truth: kết quả true | Kiểm tra non-empty riêng |
| Stream vô hạn với terminal toàn phần luôn kết thúc | Không có điểm dừng | Dùng limit/điều kiện ngắt hợp lệ |
| Java 8 có `Stream.toList()` | `toList()` xuất hiện từ Java 16 | Dùng `collect(Collectors.toList())` nếu thực sự target Java 8 |

## 21. Bài tập tự luyện

**Bài 1 — Phân loại operation.** Trong chuỗi `list.stream().map(...).filter(...).distinct().sorted().toList()`, chỉ ra nguồn, các trung gian và terminal. Nêu lúc nào công việc xử lý bắt đầu.

**Bài 2 — Dự đoán output.** Với `Stream.of(5, 2, 5, 1).distinct().sorted().limit(2).toList()`, viết kết quả và giải thích. Đổi `limit(2)` lên trước `sorted()`, so sánh.

**Bài 3 — Kiểm tra lazy.** Đặt `System.out.println` trong `filter` và `map`, xây pipeline rồi mới gọi `findFirst`. Dự đoán thứ tự in trên nguồn tuần tự có thứ tự. Thử `anyMatch` và phân tích lúc short-circuit.

**Bài 4 — Flatten.** Với `List<List<Integer>>` gồm `[1,2]`, `[3]`, `[4,5]`, dùng `flatMap` tạo List các số lẻ. So sánh kiểu trả về khi thay bằng `map`.

**Bài 5 — Nhiều terminal.** Viết chương trình gọi `count()` rồi `toList()` trên cùng stream, quan sát exception. Sửa bằng hai lần `source.stream()` hoặc bằng một phép thu gom có kiểm soát.

**Bài 6 — Collect.** Với danh sách đơn hàng có nhóm `category` và số lượng `units`, dùng `groupingBy` + `summingInt` để tính tổng theo nhóm. Khi muốn stdout ổn định, dùng `TreeMap`.

**Bài 7 — Stream rỗng.** Kiểm tra `findFirst`, `anyMatch`, `allMatch`, `noneMatch` trên stream rỗng. Giải thích vì sao `allMatch` đúng nhưng không chứng minh rằng dữ liệu đầu vào có phần tử.

**Bài 8 — Nguồn vô hạn.** Tạo `Stream.generate(() -> "x")`, thêm `limit(3)` rồi thu về List. Phân tích điều gì xảy ra nếu bỏ `limit` và gọi terminal yêu cầu duyệt toàn phần.

**Bài 9 — Tài nguyên.** Đọc các dòng từ một tệp bằng `Files.lines`, lọc dòng rỗng và tính số lượng. Viết try-with-resources, xử lý lỗi mở/đọc theo hợp đồng I/O.

**Bài 10 — Chạy song song.** Thử `List.of(1,2,3,4).parallelStream().forEach(System.out::println)` vài lần và so với `forEachOrdered`. Không suy từ một lượt chạy rằng `forEach` đã có cam kết thứ tự.

**Bài 11 — Chọn API phù hợp phiên bản.** Dùng Java 8 thật, viết pipeline trả `List` bằng `collect(Collectors.toList())`. Dùng Java 17, thay bằng `toList()` và xác định khác biệt mutability qua thử nghiệm.

## 22. Checklist trước khi merge một Stream pipeline

- Nguồn dữ liệu có rõ ràng, hữu hạn và có encounter order phù hợp không?
- Có bao nhiêu intermediate; chúng có lazy, stateful hay short-circuit không?
- Terminal nào thật sự cần: list, count, collect, sum, find, match hay side effect?
- Nếu dùng `sorted`/`distinct`, chi phí bộ nhớ và dữ liệu lớn đã được xem xét chưa?
- Thứ tự `limit`, `sorted`, `filter` có giữ đúng ngữ nghĩa không?
- Lambda có non-interfering/stateless và tránh sửa source đang duyệt không?
- Có vô tình dựa vào `peek` hoặc `map` để thực hiện side effect bắt buộc không?
- Có dùng lại Stream sau terminal hoặc sau khi đã đóng không?
- Có xử lý null, empty stream và `Optional` đúng hợp đồng không?
- Nguồn `Files.lines` hoặc I/O khác đã đóng bằng try-with-resources chưa?
- Nếu dùng parallel, có thực sự cần, có bảo đảm tính đúng đắn và order phù hợp không?
- API chọn theo JDK mục tiêu chưa: Java 8 cơ sở, `List.of` Java 9, `toList` Java 16, record Java 16?
- Có kiểm thử output, ngoại lệ, hiệu năng và trường hợp biên với dữ liệu thực tế không?

## 23. Tóm tắt cốt lõi

Một **Stream pipeline** bắt đầu từ **source**, nối **không hoặc nhiều intermediate operations** và hoàn tất bằng **một terminal operation**. Intermediate như `filter`, `map`, `flatMap`, `distinct`, `sorted` thường lazy; terminal như `toList`, `collect`, `count`, `sum`, `findFirst`, `anyMatch` yêu cầu đánh giá pipeline.

Hiểu mô hình này giúp tránh ba lỗi lớn: tưởng intermediate chạy ngay, dùng lại một Stream đã tiêu thụ, và dùng side effect bên trong lambda mà không hiểu short-circuit/tối ưu hóa. Khi nguồn có tài nguyên, hãy đóng đúng lúc; khi dùng parallel hoặc nguồn vô hạn, hãy định nghĩa thứ tự và điều kiện kết thúc. Các nguyên tắc này từ Java 8 vẫn áp dụng đầy đủ trong Java hiện đại.
