# Vì sao thiếu thao tác kết thúc làm lambda không được gọi trong Java Stream?

## 1. Mục tiêu: phân biệt “khai báo công việc” và “thực thi công việc”

Trong Java, một biểu thức như:

```java
Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase);
```

trông giống như đang lọc và đổi chữ hoa ngay lập tức. Thực tế, `filter` và `map` là **intermediate operations**: chúng mô tả các bước xử lý, tạo một pipeline mới, nhưng **thường chưa duyệt dữ liệu và chưa gọi thân lambda**. Nếu chương trình dừng ở dòng khai báo trên mà không có thao tác tiêu thụ, những lambda này sẽ không được gọi.

Khi thêm một **terminal operation**, chẳng hạn:

```java
List<String> result = pipeline.toList();
```

framework mới bắt đầu yêu cầu các phần tử cần thiết từ nguồn, chạy các stage tương ứng và thu kết quả. Với nguồn và các thao tác thông thường, đây là thời điểm các lambda trong `filter` và `map` được gọi.

Nhưng cần hiểu chính xác hơn một câu nói phổ biến: **“Có terminal operation” là điều kiện để pipeline được đánh giá, không bảo đảm mọi lambda sẽ chạy, hoặc mỗi lambda sẽ chạy đúng một lần với mọi phần tử.** Các terminal operation có thể dừng sớm; một số stage có thể bị tối ưu bỏ qua nếu không ảnh hưởng kết quả theo hợp đồng API.

Sau bài này, bạn cần giải thích được:

- Vì sao tạo Stream và gọi `map/filter/peek` không đồng nghĩa đã xử lý dữ liệu.
- Khi nào terminal operation yêu cầu framework duyệt phần tử.
- Thứ tự `filter → map → terminal` trên một pipeline tuần tự.
- Vì sao `count()` hoặc `findFirst()` có thể khiến lambda không chạy hết, dù đã có terminal operation.
- Tại sao biểu thức **tạo nguồn, tạo callback hoặc tính đối số** có thể được đánh giá ngay, khác với **thân callback**.
- Cách viết test/debug đúng thay vì dựa vào side effect trong `map` hoặc `peek`.

## 2. Pipeline Stream: nguồn, intermediate, terminal

Một Stream pipeline thường gồm ba phần:

```text
Nguồn dữ liệu
    │
    ▼
stream() / Stream.of(...) / IntStream.range(...)
    │
    ▼
filter(predicate)     ┐
    │                 │
    ▼                 ├── intermediate operations
map(mapper)           │    (chỉ mô tả cách xử lý)
    │                 │
    ▼                 │
sorted()              ┘
    │
    ▼
toList() / collect() / forEach() / count() / findFirst()
    │
    └── terminal operation: yêu cầu một kết quả/hiệu ứng cuối
```

**Nguồn** quyết định tập phần tử sẵn có. **Intermediate operations** biến đổi cách phần tử được phát qua pipeline. **Terminal operation** yêu cầu đánh giá pipeline cho mục đích cuối cùng.

| Nhóm | Ví dụ | Khi gọi phương thức, điều gì xảy ra? |
| --- | --- | --- |
| Tạo nguồn | `list.stream()`, `Stream.of(...)` | Tạo Stream từ nguồn; biểu thức đối số tạo nguồn vẫn được đánh giá theo quy tắc Java |
| Trung gian | `filter(p)` | Thêm bước giữ/bỏ phần tử; thường chưa gọi `p.test(...)` |
| Trung gian | `map(f)` | Thêm bước chuyển đổi; thường chưa gọi `f.apply(...)` |
| Trung gian | `peek(action)` | Thêm bước quan sát; không phải một cơ chế log bắt buộc |
| Trung gian stateful | `sorted(...)`, `distinct()` | Thêm bước cần quan tâm nhiều phần tử/trạng thái, vẫn không tự kích hoạt tiêu thụ chỉ vì được khai báo |
| Kết thúc | `toList()`, `collect(...)` | Yêu cầu kết quả được thu; xử lý các phần tử cần thiết |
| Kết thúc | `forEach(...)`, `forEachOrdered(...)` | Yêu cầu thực hiện action trên phần tử được duyệt theo hợp đồng |
| Kết thúc ngắn mạch | `findFirst()`, `anyMatch(...)`, `limit(...).findFirst()` | Có thể kết thúc mà không đi hết nguồn |
| Kết thúc có thể tối ưu | `count()` | Có thể trả kết quả từ kích thước đã biết mà không gọi một số intermediate lambda |

**Không phải cứ thấy dấu ngoặc `(...)` là một thao tác kết thúc.** `map(...)` và `filter(...)` là lời gọi phương thức có thật, nhưng chúng chỉ tạo tiếp pipeline. Tên và hợp đồng của operation mới quyết định nó có làm pipeline được tiêu thụ hay không.

## 3. Ví dụ Java 17+ hoàn chỉnh: không terminal thì không chạy lambda

Tạo tệp `LazyPipelineDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        System.out.println("before pipeline");

        Stream<String> pipeline = names.stream()
                .filter(name -> {
                    System.out.println("filter: " + name);
                    return name.length() >= 3;
                })
                .map(name -> {
                    System.out.println("map: " + name);
                    return name.toUpperCase();
                });

        System.out.println("pipeline created");
        System.out.println("before terminal");

        List<String> result = pipeline.toList();

        System.out.println("result=" + result);
    }
}
```

Biên dịch và chạy:

```bash
javac LazyPipelineDemo.java
java LazyPipelineDemo
```

Kết quả chính xác với pipeline tuần tự trên Java 17:

```text
before pipeline
pipeline created
before terminal
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
result=[BINH, CHI]
```

Đọc kết quả theo từng giai đoạn:

1. `"before pipeline"` được in ngay.
2. Lời gọi `names.stream().filter(...).map(...)` xây pipeline. **Chưa có dòng `filter: ...` hoặc `map: ...` nào xuất hiện.**
3. `"pipeline created"` và `"before terminal"` được in tiếp.
4. `pipeline.toList()` là terminal operation. Framework bắt đầu lấy phần tử qua chuỗi xử lý.
5. Với `"An"`, `filter` trả false (độ dài 2), nên `map` không gọi cho phần tử này.
6. Với `"Binh"` và `"Chi"`, bộ lọc trả true, mapper mới chuyển sang chữ hoa.
7. `toList()` trả danh sách `[BINH, CHI]`.

Nếu **xóa dòng `List<String> result = pipeline.toList();` và dòng in `result` tương ứng**, phần thân hai lambda sẽ không chạy trong chương trình này: bạn chỉ còn những dòng log trước/sau lúc tạo pipeline.

Điểm thứ hai cũng quan trọng: ngay cả khi có terminal operation, mapper **không chạy cho An** bởi `filter` đã loại phần tử đó. Vậy số lần gọi lambda phụ thuộc vào việc phần tử **có đi đến stage ấy** hay không.

## 4. “Lazy” nghĩa là gì và không có nghĩa là gì?

Laziness của Stream chủ yếu chỉ việc **hoãn thực hiện các stage trung gian cho tới khi kết quả được yêu cầu**. Nó không có nghĩa:

- Mọi biểu thức xuất hiện trên dòng code đều bị hoãn.
- Mọi operation đều xử lý từng phần tử ngay khi được gọi.
- Có terminal operation thì toàn bộ source chắc chắn được duyệt.
- Lambda chắc chắn được gọi đúng một lần cho từng phần tử của nguồn.
- Có `peek(...)` thì log chắc chắn được in ra.
- Có pipeline rồi là nó tự chạy trong nền khi Java rảnh.
- Stream tự nhớ/cache kết quả để một lần dùng lại nhiều lần.

Thực tế, một pipeline như:

```java
Stream<Integer> s = Stream.of(1, 2, 3)
        .map(n -> n * 10);
```

chỉ mô tả cách nhận các giá trị sau ánh xạ. Nó không tạo một tác vụ chạy nền. Dòng code tiếp theo của cùng thread vẫn chạy bình thường. Khi chương trình không tiêu thụ `s`, mapper không có lý do để thực hiện.

Trong Stream tuần tự thông thường, processing thường đi **theo từng phần tử qua các stage**, chứ không nhất thiết “lọc hết tất cả dữ liệu rồi mới map hết”. Tuy vậy `sorted()` hay `distinct()` là stateful operations và có thể thay đổi cách framework đệm/quan sát dữ liệu. Không suy ra lịch thực thi cố định cho mọi pipeline, nhất là parallel stream.

## 5. Phân biệt tham chiếu lambda với việc gọi thân lambda

Xét:

```java
Predicate<String> valid = s -> s.length() > 2;
Stream<String> pipeline = Stream.of("a", "long")
        .filter(valid);
```

Tại đây:

- Biểu thức `s -> s.length() > 2` tạo một đối tượng/hành vi tương thích `Predicate<String>`.
- `filter(valid)` nhận Predicate và tạo một stage.
- Phương thức `Predicate.test(...)` **chưa nhất thiết được gọi**.
- Khi terminal operation tiêu thụ phần tử và cần quyết định giữ/bỏ, framework mới gọi `valid.test(element)`.

Tương tự:

```java
Function<String, Integer> length = String::length;
Stream<Integer> lengths = Stream.of("a", "long").map(length);
```

Đây là các đoạn khai báo trong phương thức có import `Stream`, `Predicate`, `Function`. Tạo method reference không phải là gọi `String.length()` trên phần tử cụ thể; mapper được gọi khi stage cần xử lý phần tử.

**Cần phân biệt thêm:** các expression dùng để **tạo ra** callback vẫn được đánh giá theo quy tắc bình thường của Java. Ví dụ:

```java
Stream<String> pipeline = source.stream()
        .map(makeMapper());
```

Nếu `makeMapper()` tự in log và trả một `Function<String, String>`, việc **gọi `makeMapper()`** xảy ra khi xây pipeline để tính đối số đưa vào `map`. Nhưng phần thân `Function.apply(...)` mà `makeMapper()` trả về có thể chưa được gọi. Lời gọi này không được tự động hoãn chỉ bởi vì nó là đối số của intermediate operation.

Nếu muốn hoãn cả quá trình tạo mapper đến khi xử lý phần tử, về mặt mã nguồn có thể đặt công việc trong thân lambda, ví dụ `map(x -> makeMapper().apply(x))`; nhưng cách đó tạo mapper **cho mỗi phần tử** đi qua stage, có thể không mong muốn. Cần hiểu chi phí và vòng đời callback thay vì áp dụng mẹo máy móc.

## 6. Ví dụ riêng về thời điểm tạo mapper và thời điểm thực thi mapper

Lưu tệp `MapperTimingDemo.java`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class MapperTimingDemo {
    private static Function<String, String> makeMapper() {
        System.out.println("makeMapper called");
        return value -> {
            System.out.println("apply: " + value);
            return value.toUpperCase();
        };
    }

    public static void main(String[] args) {
        System.out.println("start");

        Stream<String> pipeline =
                List.of("java", "stream").stream()
                        .map(makeMapper());

        System.out.println("pipeline ready");

        List<String> result = pipeline.toList();

        System.out.println("result=" + result);
    }
}
```

Chạy:

```bash
javac MapperTimingDemo.java
java MapperTimingDemo
```

Output:

```text
start
makeMapper called
pipeline ready
apply: java
apply: stream
result=[JAVA, STREAM]
```

Chính `makeMapper()` là một lời gọi phương thức **được tính ngay khi xây pipeline**. Chỉ việc gọi `apply(...)` trên mapper trả về mới được trì hoãn cho tới khi `toList()` tiêu thụ pipeline. Điều này cũng đúng về nguyên tắc với nhiều biểu thức tạo predicate, comparator hoặc nguồn dữ liệu.

Đừng nhầm với:

```java
Stream<String> s = Stream.of(loadNameFromDatabase());
```

Trong đoạn này, `loadNameFromDatabase()` là biểu thức đối số dùng để tạo **giá trị đầu vào** cho `Stream.of(...)`, vì vậy Java gọi nó **ngay** để có một String truyền vào factory; tính lazy của các stage tiếp theo không hoãn I/O đó.

Nếu thật sự cần nguồn được tạo khi tiêu thụ, một cách có thể sử dụng là `Stream.generate(() -> loadNameFromDatabase())` cùng giới hạn số phần tử rõ ràng. Khi đó công việc đặt trong thân Supplier và chỉ xảy ra theo nhu cầu tiêu thụ nguồn. Nhưng `generate` mặc định tạo nguồn vô hạn; đừng gọi `toList()` trực tiếp trên Stream vô hạn mà không giới hạn hoặc có điều kiện dừng phù hợp.

## 7. Terminal operation nào thực sự yêu cầu duyệt dữ liệu?

Các thao tác thường gặp:

| Terminal operation | Mục đích | Điều cần nhớ |
| --- | --- | --- |
| `toList()` | Thu các giá trị còn lại thành List | Trả kết quả; không làm mutable list |
| `collect(collector)` | Thu thành List, Map, String, số liệu... | Cách duyệt phụ thuộc pipeline và collector |
| `forEach(action)` | Gọi action khi tiêu thụ từng phần tử | Trên parallel stream không cam kết thứ tự action |
| `forEachOrdered(action)` | Tiêu thụ theo encounter order khi stream có thứ tự | Có thể đòi hỏi đồng bộ/chi phí bổ sung |
| `reduce(...)` | Gộp các phần tử theo phép toán | Identity, associativity và kiểu phép gộp quan trọng |
| `min/max(...)` | Tìm cực trị | Không cần trả toàn bộ danh sách |
| `findFirst()` | Tìm phần tử đầu tiên theo encounter order | Có thể dừng sau khi thấy kết quả hợp lệ |
| `anyMatch(p)` | Kiểm tra có phần tử thỏa | Có thể dừng ngay khi tìm thấy true |
| `allMatch(p)` | Kiểm tra tất cả thỏa | Có thể dừng khi gặp false |
| `noneMatch(p)` | Kiểm tra không phần tử nào thỏa | Có thể dừng khi gặp true |
| `count()` | Đếm số phần tử kết quả | Có thể tính từ kích thước nguồn và bỏ qua một số stage |
| `iterator()` / `spliterator()` | Lấy đối tượng dùng để duyệt | Được phân loại terminal, nhưng **việc đi qua phần tử xảy ra khi consumer duyệt iterator/spliterator**, không nhất thiết ngay tại lời gọi lấy nó |

Vì vậy, một lời giải thích chính xác hơn là: **terminal operation kích hoạt hoặc thiết lập việc tiêu thụ pipeline theo hợp đồng của nó**. Đối với `iterator()`, việc thực sự đi qua các phần tử có thể bị hoãn tới các lời gọi `hasNext()`, `next()` hoặc các phương thức duyệt spliterator.

Không dùng định nghĩa “terminal operation luôn trả List” hay “terminal operation luôn chạy mọi lambda”: cả hai đều sai.

## 8. Có terminal nhưng lambda vẫn không được gọi: tối ưu `count()`

Đây là ngoại lệ rất quan trọng đối với cách debug bằng `peek` hoặc dùng `map` để tạo side effect.

Với một nguồn có kích thước xác định, framework đôi khi biết số phần tử mà không cần chạy pipeline trung gian. Chẳng hạn `map` biến **mỗi phần tử thành đúng một phần tử**, nên không làm thay đổi số lượng. Khi gọi `count()`, việc chạy mapper có thể không cần thiết để tính kết quả.

Tạo `CountOptimizationDemo.java`:

```java
import java.util.List;

public class CountOptimizationDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc");

        System.out.println("before count");

        long count = words.stream()
                .map(word -> {
                    System.out.println("map: " + word);
                    return word.toUpperCase();
                })
                .count();

        System.out.println("count=" + count);
    }
}
```

Chạy trên Java 17:

```bash
javac CountOptimizationDemo.java
java CountOptimizationDemo
```

Kết quả đối với implementation Stream chuẩn của JDK 17:

```text
before count
count=3
```

Trong trường hợp này, `count()` biết nguồn có 3 phần tử và `map` không thay đổi cardinality, nên **có thể tính kết quả mà không gọi mapper**. Đây là tối ưu được hợp đồng Stream cho phép; đừng biến số lần in log của `map` thành yêu cầu nghiệp vụ. Tài liệu API `Stream.count()` lưu ý rõ rằng nếu implementation tính được tổng số phần tử trực tiếp từ nguồn thì có thể không thực hiện các intermediate operations.

Suy ra:

- Không đúng nếu nói “hễ có `count()` thì mọi lambda được gọi”.
- Không đúng nếu xem `map(x -> { audit(x); return x; })` là cách bảo đảm audit xảy ra.
- Không đúng nếu dùng `peek(System.out::println)` rồi đếm số log để xác nhận mọi phần tử được duyệt trong mọi pipeline.

Nếu mục tiêu thực sự là **kiểm thử phép biến đổi**, hãy gọi terminal operation có ý nghĩa đối với giá trị biến đổi, ví dụ `toList()`, rồi **assert nội dung kết quả**. Nếu mục tiêu là side effect bắt buộc, thiết kế một bước xử lý có hợp đồng riêng thay vì giấu trong mapper/peek.

## 9. Có terminal nhưng chỉ gọi một phần lambda: short-circuit

Các terminal operation như `findFirst()`, `anyMatch()`, `allMatch()`, `noneMatch()` có thể dừng khi đủ dữ liệu để kết luận. Các intermediate operations như `limit(n)` cũng có thể khiến pipeline không cần toàn bộ nguồn.

Tạo `ShortCircuitDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class ShortCircuitDemo {
    public static void main(String[] args) {
        Optional<Integer> first = List.of(1, 2, 3, 4)
                .stream()
                .filter(n -> {
                    System.out.println("filter: " + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    System.out.println("map: " + n);
                    return n * 10;
                })
                .findFirst();

        System.out.println("first=" + first);
    }
}
```

Chạy:

```bash
javac ShortCircuitDemo.java
java ShortCircuitDemo
```

Output tuần tự xác định:

```text
filter: 1
filter: 2
map: 2
first=Optional[20]
```

Vì sao không thấy số 3 và 4?

1. Phần tử 1 bị `filter` loại nên không đi tới `map`.
2. Phần tử 2 qua `filter` và được `map` thành 20.
3. `findFirst()` đã có phần tử đầu tiên cần tìm nên dừng pipeline, không cần yêu cầu 3 hoặc 4.

Với `anyMatch(p)`, framework có thể dừng ngay khi tìm thấy phần tử thỏa. Với `allMatch(p)` có thể dừng khi gặp phần tử không thỏa. Với `noneMatch(p)` có thể dừng khi gặp phần tử thỏa. Trên **parallel stream**, các phần tử và callback có thể chạy trên nhiều luồng, và số phần tử thực sự được xử lý trước khi dừng có thể khác với trực giác từ pipeline tuần tự.

Đặc biệt, đối với stream rỗng, `anyMatch` trả false, `allMatch` trả true và `noneMatch` trả true mà không cần gọi Predicate; đó là quy tắc lượng từ toán học trong API. Vì vậy lời gọi terminal không luôn kéo theo một lời gọi lambda.

## 10. Intermediate `limit(0)` và nguồn rỗng

Hai trường hợp sau đều không cần chạy một mapper trên phần tử nào:

```java
Stream.of("A", "B").limit(0)
        .map(s -> expensiveTransform(s))
        .toList();

Stream.<String>empty()
        .map(s -> expensiveTransform(s))
        .toList();
```

Đây là **mã minh họa**, giả sử có phương thức `expensiveTransform(String)` trả `String`. Ở trường hợp đầu, `limit(0)` cho kết quả không có phần tử; ở trường hợp thứ hai, nguồn vốn rỗng. Dù đã gọi `toList()`, sẽ không có phần tử đi đến mapper.

Điều này khác với việc thiếu terminal: ở đây có terminal, nhưng số phần tử cần xử lý ở stage `map` bằng **0**. Hãy luôn hỏi hai câu riêng biệt:

1. Có thao tác kết thúc hoặc hoạt động duyệt nào yêu cầu pipeline cho ra dữ liệu chưa?
2. Nếu có, những phần tử nào **thực sự đến được lambda** và kết quả terminal có đòi gọi nó không?

## 11. Vì sao `peek` dễ tạo hiểu lầm khi debug?

`peek(Consumer<T>)` thường được dùng để quan sát phần tử đang đi qua một stage:

```java
List<Integer> values = List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .toList();
```

Đây là đoạn trong phương thức có import `List`. Với terminal `toList()` thông thường, log có thể giúp hiểu phần tử đang chảy qua pipeline. Nhưng `peek` không phải cơ chế để bảo đảm một side effect quan trọng xảy ra, vì:

- Khi **chưa có terminal**, không có phần tử được yêu cầu.
- Với terminal như `count()` trên nguồn sized và các stage không đổi số lượng, framework **có thể bỏ qua `peek`**.
- Với short-circuit, một số phần tử có thể không bao giờ đi đến `peek`.
- Với parallel stream, log có thể xuất hiện không đúng thứ tự nguồn; số lần thực hiện phụ thuộc pipeline.
- Khi các nguồn/terminal được tối ưu, không nên lấy side effect của intermediate operations làm chuẩn hành vi.

Để kiểm thử, nên so sánh **giá trị trả về của terminal operation** và trạng thái cần thiết. Nếu muốn log xử lý của ứng dụng, đặt log ở một vị trí có hợp đồng rõ ràng, ví dụ trong một vòng lặp xử lý chủ động, một method nghiệp vụ được gọi chắc chắn, hoặc một terminal operation phù hợp với yêu cầu (có kiểm soát thứ tự/đồng thời nếu cần).

## 12. Khi nào exception từ lambda xuất hiện?

Nếu mapper chuyển chuỗi thành số nguyên:

```java
Stream<Integer> numbers = Stream.of("12", "bad", "7")
        .map(Integer::parseInt);
```

dòng này có thể tạo pipeline mà **chưa ném `NumberFormatException`**: mapper chưa được gọi.

Nhưng:

```java
List<Integer> values = numbers.toList();
```

khi terminal cần chuyển chuỗi `"bad"`, `Integer.parseInt("bad")` ném exception. Đây là đoạn minh họa trong phương thức có import `Stream`, `List`.

Không dựa vào việc `count()` hay một terminal có thể tối ưu để “né” lỗi dữ liệu. Nếu cần validate tất cả bản ghi, hãy thiết kế một bước kiểm tra thực sự yêu cầu đi qua dữ liệu và có chiến lược xử lý lỗi rõ ràng.

**Checked exception:** các functional interface phổ biến như `Function.apply` và `Predicate.test` không khai báo checked exception. Một lambda gọi API ném checked exception cần bắt/biến đổi exception theo hợp đồng, hoặc sử dụng abstraction phù hợp. Laziness không thay đổi quy tắc biên dịch checked exception của Java.

**Thời điểm lỗi không đồng nghĩa lỗi bị mất:** lỗi trong lambda thường xuất hiện khi lambda thực sự được gọi. Không có terminal thì lỗi chưa phát sinh; điều đó không biến pipeline thành an toàn nếu sau này có terminal yêu cầu xử lý phần tử lỗi.

## 13. Không tiêu thụ một Stream nhiều lần

Một Stream được thiết kế để sử dụng cho **một chuỗi xử lý** rồi hoàn thành. Nếu đã gọi terminal operation:

```java
Stream<String> s = Stream.of("a", "b");
List<String> result = s.toList();
```

không dùng lại `s` để gọi `s.count()`. Lời gọi sau thông thường ném `IllegalStateException` vì stream đã bị vận hành/đóng. Tạo stream mới từ nguồn nếu cần xử lý lần nữa:

```java
List<String> source = List.of("a", "b");
List<String> upper = source.stream()
        .map(String::toUpperCase)
        .toList();
long count = source.stream().count();
```

Các đoạn ở trên thuộc một phương thức, với import `List`, `Stream`.

Ngay cả việc đã thêm intermediate operation cũng có thể khiến đối tượng Stream gốc được coi là đã liên kết vào pipeline và không được dùng lại theo cách khác. Tránh chia nhánh từ **cùng một instance Stream** để rồi kỳ vọng nó như collection có thể đọc đi đọc lại.

Nếu cần tái chạy pipeline với logic giống nhau, một `Supplier<Stream<T>>` có thể tạo **stream mới** mỗi lần:

```java
Supplier<Stream<String>> sourceFactory =
        () -> names.stream();
```

Đoạn trên giả định `names` là collection có thể lấy stream nhiều lần và đã import `Supplier`, `Stream`. Mỗi lần gọi `sourceFactory.get()` tạo một pipeline mới; **đừng lưu và tái sử dụng Stream đã tiêu thụ**.

## 14. Statefulness, nguồn vô hạn và lý do cần thiết kế terminal cẩn thận

Tính lazy không có nghĩa stream luôn tiết kiệm toàn bộ bộ nhớ hoặc có thể tạo kết quả ngay.

Ví dụ:

```java
Stream<Integer> natural = Stream.iterate(1, n -> n + 1);
```

Đây là nguồn vô hạn, không tự in ra hay tự sinh vô hạn số nguyên chỉ vì được tạo. Nếu gọi `natural.sorted().findFirst()`, phép sắp xếp toàn bộ một nguồn vô hạn **không thể hoàn tất để trả kết quả theo nghĩa thông thường**. Khi cần xử lý, hãy đặt giới hạn phù hợp:

```java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted()
        .toList();
```

Kết quả là `[1, 2, 3, 4, 5]`.

Các operation stateful như `sorted`, `distinct` có thể phải quan sát nhiều phần tử trước khi phát ra kết quả. Với `limit`, `takeWhile`, `dropWhile`, `findFirst`, vị trí trong pipeline có thể đổi **những phần tử nào được yêu cầu**. Chẳng hạn `limit(5).sorted()` có ý nghĩa “lấy năm phần tử rồi sắp”, không luôn giống `sorted().limit(5)` trên mọi nguồn; với nguồn vô hạn, khác biệt còn quyết định việc pipeline có thể hoàn tất hay không.

Không gắn một terminal như `toList()` vào nguồn vô hạn mà không có giới hạn hoặc điều kiện dừng, vì chương trình có thể tiếp tục sinh dữ liệu không kết thúc và tiêu tốn tài nguyên.

## 15. Parallel stream: có terminal không có nghĩa có thứ tự log

Với:

```java
numbers.parallelStream()
        .map(n -> {
            System.out.println("mapped " + n);
            return n * 2;
        })
        .toList();
```

đây là đoạn minh họa trong một phương thức có collection `numbers`. Các mapper có thể chạy trên nhiều thread và thứ tự log có thể không theo encounter order. Mặc dù `toList()` trên ordered stream trả kết quả theo encounter order, side effect trong từng lambda không vì thế được bảo đảm xuất hiện tuần tự.

Để lập trình Stream có thể dự đoán:

- Ưu tiên lambda **stateless, non-interfering** (không sửa nguồn đang được stream duyệt).
- Không chia sẻ biến mutable không đồng bộ để đếm số lần mapper được gọi.
- Nếu muốn thống kê, dùng collector hoặc terminal operation có ý nghĩa rõ.
- Không suy rằng terminal nhất định thực hiện callback đúng một lần mỗi phần tử. Cả tối ưu và short-circuit đều có thể ảnh hưởng.
- Nếu chương trình yêu cầu thứ tự xử lý side effect, thiết kế cách duyệt và đồng bộ phù hợp thay vì dùng `peek` hoặc `map` với side effect.

Đây là khác biệt giữa **hợp đồng dữ liệu cuối cùng** và **dấu vết nội bộ quá trình chạy**.

## 16. Ví dụ so sánh nguồn eager và Supplier lazy

Tạo tệp `SourceTimingDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class SourceTimingDemo {
    private static String load() {
        System.out.println("load()");
        return "value";
    }

    public static void main(String[] args) {
        System.out.println("before of");
        Stream<String> eagerInput = Stream.of(load());
        System.out.println("after of");

        System.out.println("before eager terminal");
        List<String> eagerResult = eagerInput.toList();
        System.out.println("eager result=" + eagerResult);

        System.out.println("before generate");
        Stream<String> lazySource = Stream.generate(
                () -> load()).limit(2);
        System.out.println("after generate");

        List<String> lazyResult = lazySource.toList();
        System.out.println("lazy result=" + lazyResult);
    }
}
```

Chạy:

```bash
javac SourceTimingDemo.java
java SourceTimingDemo
```

Output:

```text
before of
load()
after of
before eager terminal
eager result=[value]
before generate
after generate
load()
load()
lazy result=[value, value]
```

Giải thích: trong `Stream.of(load())`, Java gọi `load()` ngay để tính đối số tạo stream. Trong `Stream.generate(() -> load())`, phần thân Supplier được framework gọi khi phần tử được yêu cầu, ở đây đúng hai lần do `limit(2).toList()`.

**Không nên coi `generate` là phép thay thế mặc định cho `of`.** Một bên tạo nguồn bằng Supplier theo nhu cầu, bên kia tạo nguồn từ các giá trị đã được đánh giá; chúng phục vụ những trường hợp khác nhau và nguồn generate có thể vô hạn nếu không giới hạn.

## 17. Phân biệt lỗi thiếu terminal và lỗi pipeline không có dữ liệu

Đọc ba đoạn sau:

```java
// A: Không có terminal.
Stream.of("a", "bb")
      .map(s -> {
          System.out.println("A mapper: " + s);
          return s.toUpperCase();
      });

// B: Có terminal, nhưng lọc hết dữ liệu.
Stream.of("a", "bb")
      .filter(s -> s.length() > 10)
      .map(s -> {
          System.out.println("B mapper: " + s);
          return s.toUpperCase();
      })
      .toList();

// C: Có terminal, nhưng chỉ cần kết quả đầu tiên.
Stream.of("a", "bb")
      .map(s -> {
          System.out.println("C mapper: " + s);
          return s.toUpperCase();
      })
      .findFirst();
```

Đây là các đoạn trong một phương thức có import `Stream`, minh họa trên stream tuần tự.

- **A:** không terminal; mapper không chạy.
- **B:** terminal chạy, nhưng `filter` không cho phần tử nào qua; mapper không chạy.
- **C:** terminal `findFirst()` dừng sau phần tử đầu tiên; mapper chỉ cần chạy với `"a"`, không cần `"bb"`.

Vậy “không có log” không đủ để kết luận một pipeline **chưa có terminal**. Có thể terminal tồn tại nhưng không phần tử nào đến stage có log, hoặc framework bỏ qua stage do tối ưu hợp lệ.

## 18. Cách kiểm thử và debug đáng tin

Nếu muốn kiểm tra pipeline chuyển tên thành chữ hoa, hãy kiểm tra **kết quả**, không bắt buộc callback phải in bao nhiêu dòng:

```java
List<String> actual = List.of("an", "binh", "chi")
        .stream()
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .toList();

if (!actual.equals(List.of("BINH", "CHI"))) {
    throw new AssertionError("Unexpected result: " + actual);
}
```

Đoạn mã này nằm trong phương thức đã import `List`. Test dùng hợp đồng kết quả của Stream. Các chi tiết nội bộ như số đối tượng lambda, thứ tự scheduling hoặc việc thực thi một intermediate stage bị bỏ qua không phải tiêu chí kiểm thử, trừ khi API của chính ứng dụng cam kết một side effect cụ thể.

Khi debug một pipeline không cho kết quả mong muốn:

1. Kiểm tra có terminal operation hay cách duyệt thực tế chưa.
2. Xem nguồn có rỗng không; nguồn `Stream.empty()` sẽ không gọi mapper.
3. Xem `filter` hoặc `limit(0)` có ngăn phần tử đi tới mapper không.
4. Xem terminal có ngắn mạch không, như `findFirst()` / `anyMatch()`.
5. Với `count()`, xét tối ưu dựa trên kích thước nguồn có làm bỏ qua intermediate lambda không.
6. Nếu dùng parallel stream, tách yêu cầu kết quả khỏi thứ tự log.
7. Xem lambda có thực sự nằm **bên trong** callback hay công việc đã chạy sớm để tạo đối số/callback.
8. Tránh tái sử dụng stream đã tiêu thụ; tạo stream mới cho mỗi lần thử.
9. Với Stream kết nối file, HTTP hay database, quản lý resource và error theo đúng API nguồn, không trông chờ pipeline tự đóng tài nguyên.

## 19. Câu hỏi tự kiểm tra

### Câu 1: Tìm nơi lambda bắt đầu chạy

```java
List<Integer> values = List.of(2, 3, 4);

Stream<Integer> pipeline = values.stream()
        .map(n -> {
            System.out.println("map " + n);
            return n * n;
        });

System.out.println("ready");
List<Integer> result = pipeline.toList();
System.out.println(result);
```

Kết quả?

**Đáp án:**

```text
ready
map 2
map 3
map 4
[4, 9, 16]
```

Các log `map ...` chỉ xuất hiện khi `toList()` tiêu thụ pipeline. Tạo lambda và gọi `map(...)` chỉ nối thêm stage.

### Câu 2: Khi nào mapper không chạy?

Xét:

```java
long count = List.of("a", "bb", "ccc")
        .stream()
        .map(s -> {
            System.out.println("visited " + s);
            return s.toUpperCase();
        })
        .count();
```

Tại sao có thể không thấy log `visited` mặc dù có terminal?

**Đáp án:** nguồn list có kích thước biết trước và `map` không thay đổi số phần tử. Framework có thể tối ưu `count()` để trả 3 mà không đánh giá mapper. Hãy đo đầu ra/hợp đồng thay vì bắt mapper phải có side effect.

### Câu 3: Terminal có xử lý hết nguồn?

```java
boolean anyEven = List.of(1, 3, 4, 6)
        .stream()
        .anyMatch(n -> {
            System.out.println("check " + n);
            return n % 2 == 0;
        });
```

Với stream tuần tự, Predicate được gọi trên các số nào?

**Đáp án:** kiểm tra 1, 3 rồi 4; khi 4 thỏa, `anyMatch` trả true và không cần kiểm tra 6. Với parallel stream, không dựa vào số lần gọi hay thứ tự callback như trên.

### Câu 4: Phân biệt eager với lazy

```java
Stream<String> a = Stream.of(load());
Stream<String> b = Stream.generate(() -> load()).limit(1);
```

Giả sử `load()` trả String và in log, nó được gọi ở thời điểm nào?

**Đáp án:** dòng tạo `a` gọi `load()` ngay để tính đối số cho `Stream.of`. Dòng tạo `b` chỉ tạo Supplier và pipeline; `load()` chạy khi cần sinh phần tử, ví dụ lúc gọi `b.toList()`. Khi không tiêu thụ `b`, không có lời gọi từ Supplier.

## 20. Quy tắc ghi nhớ

```text
Lời gọi tạo pipeline:
    stream()
      .filter(predicate)
      .map(mapper)
      .peek(observer)
          ↓
    Chưa cần gọi thân callback để có kết quả

Terminal operation:
    .toList() / .collect() / .findFirst() / .anyMatch(...)
          ↓
    Yêu cầu xử lý những phần tử cần thiết
          ↓
    Callback có thể chạy, bị bỏ qua do filter/short-circuit,
    hoặc bị tối ưu bỏ qua nếu không ảnh hưởng kết quả
```

**Kết luận:** Thiếu terminal operation là lý do thường gặp nhất khiến lambda trong `map/filter/peek` không được gọi: bạn mới **mô tả pipeline**, chưa yêu cầu **tiêu thụ dữ liệu**. Nhưng ngay cả khi có terminal, không có bảo đảm chung rằng mọi callback chạy cho mọi phần tử. Hãy đọc hợp đồng của stage, tính short-circuit, tối ưu như `count()`, thời điểm đánh giá các đối số và chọn cách kiểm thử dựa trên kết quả.

**Tham khảo:** Java SE API của `java.util.stream.Stream` (intermediate/terminal operations, `map`, `filter`, `peek`, `toList`, `count`, `findFirst`, `anyMatch`), tài liệu package `java.util.stream` về laziness/side effects, Java Language Specification về thời điểm đánh giá đối số phương thức.