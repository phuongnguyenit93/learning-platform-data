# Stream.builder() và Stream.concat() trong Java

## Mục tiêu bài học

Java Stream API cung cấp nhiều cách tạo nguồn dữ liệu cho pipeline. **`Stream.builder()`** dùng khi cần thêm từng phần tử trong giai đoạn xây dựng nguồn, còn **`Stream.concat(a, b)`** nối hai Stream thành một Stream để xử lý tiếp. Cả hai đều thuộc `java.util.stream.Stream` nhưng giải quyết hai vấn đề khác nhau: một bên **xây nguồn từ các phần tử**, một bên **kết hợp hai nguồn đã có**.

Sau bài này, bạn có thể:

- Khai báo `Stream.Builder<T>`, thêm phần tử bằng `add`/`accept` và gọi `build()`.
- Hiểu vòng đời builder: giai đoạn thêm dữ liệu → `build` → Stream chỉ được tiêu thụ một lần; không tiếp tục sửa builder sau `build`.
- Phân biệt việc **tạo Stream/pipeline** và thời điểm **terminal operation** thực sự yêu cầu duyệt phần tử.
- Nối hai Stream bằng `concat`, giữ đúng thứ tự encounter order khi hai nguồn có thứ tự.
- Hiểu ảnh hưởng của nguồn song song, short-circuit, resource closing và nối nhiều Stream.
- Chọn `builder`, `concat` hoặc giải pháp khác dựa trên cấu trúc dữ liệu và khối lượng xử lý.
- Biên dịch và chạy ví dụ Java 17, xác minh đầu ra chính xác và phòng tránh lỗi thường gặp.

## 1. Đặt vấn đề: tạo Stream không chỉ có Stream.of()

Với các phần tử đã biết, cách đơn giản nhất là:

```java
Stream<String> names = Stream.of("An", "Bình", "Chi");
```

Nếu có một `List<String>` sẵn có, có thể dùng `names.stream()`. Tuy nhiên, có những tình huống nguồn dữ liệu không cố định tại thời điểm viết biểu thức: bạn chỉ thêm phần tử khi thỏa điều kiện, hoặc dữ liệu được chọn bởi nhiều nhánh của thuật toán. `Stream.builder()` phù hợp để xây một nguồn hữu hạn có các phần tử được thêm lần lượt.

Một tình huống khác: bạn đã có **hai Stream** (chẳng hạn dữ liệu từ hai giai đoạn tính) và muốn xử lý chúng bằng **một pipeline**. `Stream.concat(first, second)` cung cấp một Stream ghép, không đòi tự thu cả hai nguồn thành hai danh sách rồi nối trước khi xử lý.

Hai API này **không thay thế lẫn nhau**:

| Câu hỏi | `Stream.builder()` | `Stream.concat(a,b)` |
| --- | --- | --- |
| Đầu vào chính là gì? | Các phần tử kiểu `T` được thêm trong lúc dựng | Hai Stream nguồn kiểu tương thích |
| Kết quả | Một `Stream<T>` khi gọi `build()` | Một `Stream<T>` nối hai nguồn |
| Tính linh hoạt | Thêm 0, 1 hoặc nhiều phần tử theo điều kiện | Kết hợp tất cả phần tử của hai nguồn |
| Thời điểm cung cấp phần tử | Phần tử được đưa vào builder trước `build` | Phần tử của nguồn được duyệt khi pipeline cần |
| Vấn đề vòng đời | Builder chỉ dùng để tạo một Stream | Cả Stream đầu vào lẫn Stream ghép là single-use |
| Cần đóng nguồn có I/O? | Tùy cách cung cấp dữ liệu và nguồn | Đóng Stream ghép sẽ đóng cả hai Stream đầu vào |

**Lưu ý:** Stream là một mô hình các phép toán trên nguồn dữ liệu, không phải một collection cho phép cập nhật tùy ý sau khi đã bắt đầu xử lý. Cả Stream tạo từ builder và Stream ghép đều tuân theo quy tắc sử dụng **một lần** của Stream API.

## 2. Stream.builder(): xây nguồn theo từng phần tử

### 2.1. Chữ ký và vòng đời

API chính:

```java
public static <T> Stream.Builder<T> builder()
```

`Stream.Builder<T>` là một interface nằm bên trong `Stream`; nó mở rộng `Consumer<T>` và có các thành viên quan trọng:

```java
void accept(T element);
Stream.Builder<T> add(T element);
Stream<T> build();
```

Đây là **chữ ký API rút gọn để giải thích**, không phải một class cần tự định nghĩa. Ý nghĩa:

- `accept(element)` thêm một phần tử, trả `void`. Vì Builder triển khai `Consumer<T>`, bạn có thể dùng nó ở vị trí cần nhận một Consumer khi quá trình dựng vẫn đang mở.
- `add(element)` cũng thêm phần tử, nhưng **trả lại Builder** để viết nối chuỗi `builder.add(a).add(b)`.
- `build()` kết thúc giai đoạn thêm phần tử và trả một `Stream<T>` chứa những phần tử đã thêm, theo thứ tự encounter order của builder.

Ví dụ:

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("Java");
builder.accept("Lambda");

Stream<String> words = builder.build();
List<String> result = words.toList(); // [Java, Lambda]
```

Với Java 17, `Stream.toList()` trả một danh sách không cho phép sửa cấu trúc, và giữ encounter order nếu Stream có thứ tự. Không nhầm danh sách kết quả này với một `ArrayList` có thể gọi `add`.

### 2.2. add() nối chuỗi; accept() dùng khi không cần Builder trả về

```java
Stream<Integer> numbers = Stream.<Integer>builder()
        .add(10)
        .add(20)
        .add(30)
        .build();
```

`Stream.<Integer>builder()` chỉ rõ type parameter để compiler hiểu phần tử là `Integer`. Có thể dùng biến có kiểu rõ ràng rồi để compiler suy luận:

```java
Stream.Builder<Integer> builder = Stream.builder();
builder.add(10).add(20);
Stream<Integer> numbers = builder.build();
```

Hai đoạn này là **hai phương án minh họa riêng**, không đặt chung một scope với cùng tên `numbers`. `add` phù hợp khi viết chain, còn `accept` thường tiện khi đưa Builder vào một API có hợp đồng `Consumer<T>`. Không có khác biệt về giá trị phần tử được thêm.

Ví dụ một Consumer nhận dữ liệu:

```java
Stream.Builder<String> builder = Stream.builder();
Consumer<String> sink = builder;

sink.accept("first");
sink.accept("second");

Stream<String> result = builder.build();
```

Đoạn trên minh họa quan hệ kiểu; cần import `java.util.stream.Stream` và `java.util.function.Consumer`. Chỉ truyền builder như Consumer trong **giai đoạn xây dựng**; sau `build` không được tiếp tục `accept`.

### 2.3. Xây nguồn theo điều kiện

Một trường hợp thực tế:

```java
Stream.Builder<String> builder = Stream.builder();

builder.add("header");
if (includeDetails) {
    builder.add("details");
}
if (includeFooter) {
    builder.add("footer");
}

Stream<String> sections = builder.build();
```

Đây là đoạn minh họa, cần khai báo `includeDetails` và `includeFooter`. Nếu hai cờ đều `false`, kết quả chỉ có `header`; nếu cả hai `true`, Stream có ba phần tử theo thứ tự `header`, `details`, `footer`.

Khi các phần tử chỉ được quyết định qua vài nhánh có điều kiện, builder giúp mã dễ đọc hơn việc tạo nhiều Stream nhỏ rồi nối liên tục. Nhưng nếu bạn đã có một collection được xây dựng vì mục đích khác, `collection.stream()` thường đơn giản hơn việc sao chép mọi phần tử vào builder.

### 2.4. Builder có thể tạo Stream rỗng hoặc một phần tử

```java
Stream<String> empty = Stream.<String>builder().build();
Stream<String> one = Stream.<String>builder()
        .add("only")
        .build();
```

Đây là các Stream hữu hạn với lần lượt 0 và 1 phần tử. Khi không có việc xây dữ liệu theo điều kiện, `Stream.empty()` và `Stream.of("only")` thường là cách ngắn và biểu đạt tốt hơn.

## 3. Giới hạn vòng đời của Stream.Builder

Sau khi gọi `build()`, builder chuyển sang trạng thái đã hoàn tất. Gọi `add`, `accept` hoặc `build` lại trên cùng builder **ném `IllegalStateException`** theo hợp đồng API.

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("A");
Stream<String> source = builder.build();

// Không làm: builder đã được build.
builder.add("B"); // IllegalStateException
```

Đừng hiểu rằng builder là một danh sách có thể tái sử dụng. Nếu cần tạo Stream mới, khởi tạo builder mới hoặc lưu dữ liệu ở một collection rồi tạo Stream từ collection đó.

Ngoài ra, **bản thân Stream do `build` trả về cũng chỉ được tiêu thụ một lần**. Ví dụ:

```java
Stream<String> source = Stream.of("A", "B");
long count = source.count();

// Không tiếp tục dùng source để chạy terminal operation khác.
// source.toList() có thể ném IllegalStateException.
```

Đây là đoạn minh họa. Một Stream không cho phép fork hoặc reset như danh sách. Nếu cần cả đếm và liệt kê, có thể lưu một kết quả trung gian phù hợp rồi tiếp tục làm việc với collection, hoặc tạo **Stream mới** từ nguồn có thể tạo lại.

**Builder không phải cấu trúc dành cho nhiều thread cùng ghi.** Đừng chia sẻ Builder và đồng thời gọi `add` từ nhiều thread mà không có hợp đồng đồng bộ phù hợp. Nếu dữ liệu được sản sinh đồng thời, hãy thu thập với cơ chế thread-safe theo thiết kế rồi tạo Stream sau khi hoàn tất.

## 4. Stream.concat(): nối hai nguồn đã có

### 4.1. Chữ ký

```java
public static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b)
```

Đây là chữ ký rút gọn. `concat` tạo một Stream gồm các phần tử từ `a`, rồi các phần tử từ `b` theo encounter order nếu hai nguồn có thứ tự.

```java
Stream<String> left = Stream.of("A", "B");
Stream<String> right = Stream.of("C", "D");

Stream<String> combined = Stream.concat(left, right);

System.out.println(combined.toList()); // [A, B, C, D]
```

`concat` **không tự thêm phần tử vào `left` hay `right`**. Nó tạo một Stream mới phụ thuộc vào hai nguồn. Sau khi tạo Stream ghép, không nên sử dụng `left` hoặc `right` riêng để thực hiện pipeline khác: chúng đã tham gia vào một pipeline nối, không được coi là hai nguồn độc lập có thể tiêu thụ tùy ý.

Vì các nguồn có `String`, đầu ra có thể dùng như `Stream<String>`. Với generic, Java có thể suy luận một kiểu cha phù hợp khi hai nguồn có kiểu phần tử khác nhau, nhưng hãy khai báo kiểu rõ nếu quy tắc kiểu quá rộng và mất tính an toàn nghiệp vụ.

### 4.2. Nguồn rỗng

```java
Stream<Integer> all = Stream.concat(
        Stream.<Integer>empty(),
        Stream.of(1, 2)
); // Khi thu thập: [1, 2]
```

Nếu cả hai nguồn rỗng, Stream kết quả rỗng. Nếu chỉ cần một Stream mà không có nguồn thứ hai, không cần gọi `concat` vô ích.

### 4.3. concat không phải merge theo khóa hoặc sort

`Stream.concat(a,b)` nối hai chuỗi phần tử; **nó không tự sắp xếp, loại phần tử trùng, so khớp khóa hoặc trộn xen kẽ theo thứ tự tăng dần**.

```java
Stream<Integer> left = Stream.of(1, 5);
Stream<Integer> right = Stream.of(2, 3);

List<Integer> joined = Stream.concat(left, right).toList();
// [1, 5, 2, 3]
```

Nếu cần sắp xếp toàn bộ, có thể thêm `sorted()` sau `concat`; nếu cần loại trùng, thêm `distinct()`. Cả hai là những thao tác pipeline có chi phí riêng. Trường hợp hai nguồn đã sắp xếp riêng nhưng cần phép **merge có thứ tự tuyến tính**, `concat` đơn thuần không đáp ứng nhiệm vụ đó.

## 5. Lazy traversal: khi nào Stream thật sự xử lý dữ liệu?

Các thao tác trung gian như `filter` và `map` thường lazy: chúng tạo một pipeline mô tả công việc nhưng chưa duyệt từng phần tử cho đến khi terminal operation yêu cầu.

```java
AtomicInteger examined = new AtomicInteger();

Stream<String> first = Stream.of("A", "B")
        .filter(s -> {
            examined.incrementAndGet();
            return true;
        });
Stream<String> second = Stream.of("C", "D")
        .filter(s -> {
            examined.incrementAndGet();
            return true;
        });

Stream<String> combined = Stream.concat(first, second);

System.out.println(examined.get());     // 0
System.out.println(combined.toList());  // [A, B, C, D]
System.out.println(examined.get());     // 4
```

Ở đoạn minh họa, `AtomicInteger` dùng để quan sát số phần tử đã đi qua `filter`. Ngay sau `concat`, chưa có terminal operation nên `examined` vẫn bằng `0`. Khi `toList()` duyệt pipeline, bốn phần tử đi qua bộ lọc và đếm thành `4`.

**Phân biệt:** việc Stream **chưa duyệt phần tử** không có nghĩa tất cả biểu thức tạo nguồn đều lazy. Java đánh giá đối số trước khi gọi phương thức:

```java
Stream<String> combined = Stream.concat(
        loadLeftStream(),
        loadRightStream()
);
```

Nếu `loadLeftStream()` và `loadRightStream()` ghi log hoặc mở tài nguyên khi **tạo đối tượng Stream**, những tác dụng phụ đó đã xảy ra lúc đánh giá đối số, trước terminal operation. Chỉ quá trình duyệt dữ liệu trong pipeline mới có thể được trì hoãn.

Do đó, khi muốn hoãn cả việc tạo nguồn đắt đỏ, không nên tưởng `concat` tự trì hoãn lời gọi factory. Hãy thiết kế factory, Supplier hoặc tầng điều phối phù hợp; không dùng thủ thuật giữ tài nguyên mở tùy tiện.

### Short-circuit có thể không duyệt hết

```java
Optional<Integer> first = Stream.concat(
        Stream.of(1, 2),
        Stream.of(3, 4)
).findFirst(); // Optional[1]
```

`findFirst` chỉ cần phần tử đầu của một Stream có encounter order và có thể hoàn tất trước khi duyệt những phần tử còn lại. Trong ví dụ tuần tự này không cần xử lý toàn bộ đầu vào để tìm kết quả. Tuy nhiên, khi dùng Stream song song, nguồn unordered hoặc intermediate operation có side effect, đừng coi số lần callback chạy là một hợp đồng nghiệp vụ ổn định.

Đặc biệt, **`peek`, `filter` hoặc `map` có side effect** không phải cơ chế đáng tin để tạo hiệu ứng nghiệp vụ đúng một lần trên mọi pipeline: một số terminal operation có thể tối ưu hóa việc duyệt, và short-circuit có thể bỏ qua phần tử. Hãy giữ callback thuần khi có thể.

## 6. Chương trình Java 17 đầy đủ

Ví dụ sau kết hợp builder, concat, kiểm tra vòng đời builder, lazy filter, close handler và trạng thái song song. Nó sử dụng các giá trị cố định nên stdout có thể đối chiếu chính xác.

Tạo tệp **`StreamBuilderConcatDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamBuilderConcatDemo {
    public static void main(String[] args) {
        Stream.Builder<String> builder = Stream.builder();
        builder.add("Java");
        builder.accept("Lambda");
        Stream<String> built = builder.build();
        System.out.println("Builder: " + built.toList());

        try {
            builder.add("Later");
        } catch (IllegalStateException ex) {
            System.out.println("Builder reused: IllegalStateException");
        }

        AtomicInteger examined = new AtomicInteger();
        Stream<String> left = Stream.of("A", "B")
                .filter(s -> {
                    examined.incrementAndGet();
                    return true;
                });
        Stream<String> right = Stream.of("C", "D")
                .filter(s -> {
                    examined.incrementAndGet();
                    return true;
                });
        Stream<String> combined = Stream.concat(left, right);
        System.out.println("Before terminal: " + examined.get());
        System.out.println("Concat: " + combined.toList());
        System.out.println("After terminal: " + examined.get());

        List<Integer> numbers = Stream.concat(
                Stream.of(1, 2),
                Stream.<Integer>builder().add(3).add(4).build()
        ).toList();
        System.out.println("Numbers: " + numbers);

        try (Stream<String> joined = Stream.concat(
                Stream.of("L").onClose(
                        () -> System.out.println("close left")),
                Stream.of("R").onClose(
                        () -> System.out.println("close right"))
        )) {
            System.out.println("Joined: " + joined.toList());
        }

        boolean parallel = Stream.concat(
                Stream.of(1, 2).parallel(),
                Stream.of(3, 4)
        ).isParallel();
        System.out.println("Parallel flag: " + parallel);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StreamBuilderConcatDemo.java
java StreamBuilderConcatDemo
```

**Stdout chính xác:**

```text
Builder: [Java, Lambda]
Builder reused: IllegalStateException
Before terminal: 0
Concat: [A, B, C, D]
After terminal: 4
Numbers: [1, 2, 3, 4]
Joined: [L, R]
close left
close right
Parallel flag: true
```

**Giải thích thứ tự:**

1. `builder.add` và `builder.accept` đưa vào hai chuỗi. `build().toList()` cho danh sách theo thứ tự `Java`, `Lambda`.
2. Builder đã ở trạng thái built. `builder.add("Later")` ném `IllegalStateException` và được bắt để chương trình tiếp tục.
3. Hai pipeline `filter` được tạo nhưng chưa được tiêu thụ; `examined` bằng `0` khi dòng `Before terminal` được in.
4. `combined.toList()` yêu cầu duyệt cả hai nguồn. Với filter luôn trả `true` và không có short-circuit, `examined` tăng lên `4`; danh sách là `[A, B, C, D]`.
5. `Stream.concat` có thể nhận một Stream trực tiếp từ `Stream.of` và một Stream xây bằng Builder. Kết quả `[1, 2, 3, 4]`.
6. `joined.toList()` in danh sách `[L, R]`. Khi thoát `try-with-resources`, `joined.close()` được gọi và chạy hai handler `onClose` theo thứ tự liên quan đến hai nguồn, in `close left` rồi `close right`.
7. Theo hợp đồng của `Stream.concat`, Stream kết quả song song nếu **một trong hai** Stream đầu vào song song; `isParallel()` trả `true`. Không có nghĩa mọi terminal operation chắc chắn dùng nhiều thread hay luôn nhanh hơn.

Ví dụ đã được kiểm tra bằng compiler với mức tương thích **`--release 17`**; các phương thức `Stream.toList()`, `Stream.Builder` và `Stream.concat` đều có trong Java 17.

## 7. Quản lý tài nguyên và onClose()

Một Stream từ `List.stream()` hoặc `Stream.of(...)` thường không nắm tài nguyên I/O cần đóng. Nhưng Stream đến từ `Files.lines(path)` có thể giữ một tài nguyên mở. Với loại Stream này, **terminal operation không tự động đóng Stream**. Nên dùng `try-with-resources`.

```java
// Minh họa: pathA, pathB là các java.nio.file.Path hợp lệ;
// phương thức bao quanh phải xử lý hoặc khai báo IOException.
try (Stream<String> all = Stream.concat(
        java.nio.file.Files.lines(pathA),
        java.nio.file.Files.lines(pathB)
)) {
    all.forEach(System.out::println);
}
```

Đoạn minh họa này không độc lập: cần khai báo `pathA`, `pathB` và xử lý `IOException`. Khi `all.close()` chạy, Stream ghép đóng cả hai Stream nguồn. `Stream.concat` không có nghĩa “mỗi lần duyệt xong là nguồn tự đóng”.

### 7.1. Đóng Stream ghép đóng cả hai nguồn

Theo hợp đồng API, đóng Stream trả về từ `concat(a,b)` sẽ gọi `close` trên cả `a` và `b`. Mã mẫu hoàn chỉnh đã minh họa bằng hai `onClose` handler.

Hãy quản lý tài nguyên **ở đúng điểm sở hữu**. Không nên dựa vào việc garbage collector dọn Stream để đóng file; cũng không nên đóng một Stream nguồn quá sớm trong khi vẫn dự kiến xử lý Stream ghép.

### 7.2. Ngoại lệ khi tạo nguồn thứ hai

Với biểu thức:

```java
Stream<String> all = Stream.concat(
        Files.lines(pathA),
        Files.lines(pathB)
);
```

Java đánh giá hai đối số từ trái sang phải. Nếu mở nguồn A thành công nhưng mở nguồn B ném `IOException` **trước khi lời gọi `concat` diễn ra**, đối tượng Stream ghép chưa được tạo để quản lý việc đóng A. Để tránh rò rỉ khi việc mở nhiều nguồn có thể thất bại, nên quản lý tài nguyên ngay từ lúc mở:

```java
// Minh họa trong phương thức throws IOException, có pathA/pathB.
try (Stream<String> first = Files.lines(pathA)) {
    try (Stream<String> second = Files.lines(pathB)) {
        Stream.concat(first, second).forEach(System.out::println);
    }
}
```

Hai khối `try` đảm bảo nếu việc mở B thất bại thì A vẫn được đóng. Với một Stream ghép được quản lý tại outer `try`, có thể có thiết kế sở hữu tài nguyên khác; điều quan trọng là đảm bảo **mọi nguồn đã mở đều có đường đóng**, kể cả khi việc tạo nguồn kế tiếp thất bại.

Khi một handler `close` ném ngoại lệ, Java dùng quy tắc ngoại lệ và suppressed exceptions tương ứng. Đừng dựa vào side effect của close handler để cập nhật nghiệp vụ bắt buộc trong trường hợp hệ thống có thể gặp lỗi đóng tài nguyên.

## 8. Nối Stream trong xử lý tuần tự và song song

`Stream.concat(a,b)` trả về một Stream song song nếu một trong hai Stream đầu vào là song song:

```java
boolean parallel = Stream.concat(
        Stream.of(1, 2).parallel(),
        Stream.of(3, 4)
).isParallel(); // true
```

`isParallel()` chỉ cho biết chế độ của pipeline; không chứng minh rằng thời gian thực thi nhanh hơn. Với hai nguồn mất cân đối, overhead và khả năng chia công việc có thể khiến parallel performance không như kỳ vọng.

**Encounter order:** nếu hai nguồn có thứ tự, kết quả nối có thứ tự gồm các phần tử nguồn A trước rồi nguồn B. Với pipeline song song, các phần tử có thể được xử lý trên những thread khác nhau và việc quan sát side effect trong `forEach` có thể không theo thứ tự encounter order. Nếu bắt buộc xử lý side effect theo thứ tự trên Stream có thứ tự, cân nhắc `forEachOrdered` và hiểu chi phí tuần tự hóa.

**Kích thước và đặc tính spliterator:** API `concat` không bảo đảm giữ lại tất cả đặc tính tối ưu của hai nguồn, đặc biệt `DISTINCT` và `SORTED` của từng Stream riêng không có nghĩa toàn bộ Stream ghép cũng distinct/sorted. Khi tổng kích thước ước lượng có nguy cơ tràn `long`, đặc tính `SIZED` có thể bị mất. Đừng dựa vào metadata của spliterator như hợp đồng nghiệp vụ.

**Nối nhiều lần:** một cây `Stream.concat(Stream.concat(a,b),c)` nhỏ thường dùng được. Nhưng ghép quá sâu nhiều Stream có thể dẫn tới call chain dài hoặc `StackOverflowError` khi truy cập/duyệt; tài liệu Stream API cũng cảnh báo trường hợp nối sâu. Nếu có nhiều nguồn, cân nhắc giải pháp phù hợp với cấu trúc nguồn và vòng đời tài nguyên thay vì lặp `concat` hàng chục nghìn lần.

## 9. Khi có nhiều hơn hai nguồn

Giả sử cần kết hợp ba nguồn:

```java
Stream<Integer> first = Stream.of(1);
Stream<Integer> second = Stream.of(2);
Stream<Integer> third = Stream.of(3);

List<Integer> result = Stream.concat(
        Stream.concat(first, second),
        third
).toList(); // [1, 2, 3]
```

Cách viết này hợp lý cho số lượng nguồn nhỏ và cố định. Nhưng nếu nguồn là một **collection các Stream**, có thể dùng `flatMap`:

```java
List<Stream<Integer>> sources = List.of(
        Stream.of(1, 2),
        Stream.of(3),
        Stream.of(4, 5)
);

List<Integer> result = sources.stream()
        .flatMap(s -> s)
        .toList(); // [1, 2, 3, 4, 5]
```

Trong một pipeline theo encounter order, `flatMap` giúp làm phẳng những nguồn đã có mà không tạo chuỗi `concat` lồng nhiều cấp. `flatMap` xử lý/đóng mỗi Stream được map theo hợp đồng của thao tác; nếu các nguồn có I/O, vẫn phải thiết kế quyền sở hữu, xử lý lỗi khi tạo nguồn và đóng tài nguyên tổng thể rõ ràng.

Nếu không thực sự cần giữ mỗi nguồn như một Stream riêng, có thể tạo một Stream từ các phần tử ngay bằng `Stream.builder()` hoặc trực tiếp từ collection. Đừng xây nhiều Stream rồi ghép chỉ để tránh một vòng thêm phần tử đơn giản.

## 10. Giá trị null và tính an toàn kiểu

### 10.1. Stream.Builder có thể nhận phần tử null

Với Stream tham chiếu, builder có thể thêm `null`:

```java
Stream<String> values = Stream.<String>builder()
        .add("A")
        .add(null)
        .build();
```

Mã trên tạo Stream có một phần tử `null`. Việc một terminal operation có chấp nhận null hay không tùy thao tác tiếp theo. Chẳng hạn `.map(String::length)` trên Stream chứa null có thể ném `NullPointerException` khi tới phần tử null. Không nhầm với `List.of(...)`, vốn không cho phép phần tử null khi tạo list.

### 10.2. Bản thân đối số Stream của concat không được null

```java
Stream<String> all = Stream.concat(
        null,
        Stream.of("A")
); // NullPointerException
```

Đây là đoạn minh họa cho lỗi. Một Stream **rỗng** nên được biểu diễn bằng `Stream.empty()`, không phải reference Stream bằng `null`.

Nếu nguồn có thể không tồn tại, hãy quyết định tại tầng tạo nguồn:

```java
Stream<String> left = available
        ? obtainStream()
        : Stream.empty();
Stream<String> all = Stream.concat(left, Stream.of("fallback"));
```

Đoạn trên giả định `available` và `obtainStream()` đã có. Nếu `obtainStream()` có thể trả `null`, cần sửa hợp đồng nguồn hoặc kiểm tra rõ ràng trước khi `concat`; `available == true` không tự đảm bảo non-null.

### 10.3. Generic và kiểu phần tử

`Stream.concat` nhận hai `Stream<? extends T>`. Nếu bạn vô ý trộn nguồn có kiểu phần tử không tương thích với kiểu kết quả mong muốn, compiler có thể từ chối hoặc suy luận kiểu cha quá rộng. Khai báo type argument, dùng mapping để chuẩn hóa về kiểu miền dữ liệu hoặc chọn collection chung có cùng `T`.

Ví dụ:

```java
Stream<Number> values = Stream.concat(
        Stream.of(1, 2),
        Stream.of(3.5, 4.5)
);
```

`Integer` và `Double` đều là subtype của `Number`, nên việc dùng `Stream<Number>` ở đây có ý nghĩa. Nhưng nếu logic phía sau cần phép tính chỉ dành cho `Integer`, nên chuyển đổi dữ liệu có chủ đích thay vì ép kiểu khi duyệt.

## 11. Builder hay concat, hay API khác?

| Trường hợp | Ưu tiên | Lý do |
| --- | --- | --- |
| Vài phần tử cố định | `Stream.of(a,b,c)` | Ngắn, không cần builder |
| Không có phần tử | `Stream.empty()` | Diễn đạt rỗng trực tiếp |
| Một phần tử có thể null | `Stream.ofNullable(value)` | Trả 0 hoặc 1 phần tử một cách rõ ràng |
| Phần tử được thêm theo các nhánh điều kiện | `Stream.builder()` | Xây nguồn trước khi xử lý |
| Đã có collection | `collection.stream()` | Không sao chép dữ liệu sang builder |
| Hai Stream có sẵn cần duyệt lần lượt | `Stream.concat(a,b)` | Nối trực tiếp hai nguồn |
| Một danh sách các Stream | `streamOfStreams.flatMap(...)` | Tránh chuỗi concat lồng sâu |
| Sinh dãy số có quy luật, hữu hạn | `IntStream.range / rangeClosed` | Tránh mutable counter trong Builder |
| Sinh dữ liệu theo Supplier | `Stream.generate(supplier)` kèm điều kiện dừng | Phù hợp sinh theo nhu cầu |
| Tính lặp theo trạng thái chuyển tiếp | `Stream.iterate(...)` | Biểu đạt phép tiến hóa giá trị |

Đánh giá cấu trúc dữ liệu và ngữ nghĩa trước khi chọn. Một nguồn phải giữ tài nguyên mở khác với các phần tử String trong bộ nhớ, dù cả hai đều được gọi là Stream.

## 12. Sai lầm phổ biến

1. **Gọi `add` sau `build`:** Builder đã hoàn tất, sẽ ném `IllegalStateException`.
2. **Dùng một Stream cho nhiều terminal operation:** Stream là single-use; phải tạo mới hoặc lưu kết quả.
3. **Nghĩ `concat` tự chạy toàn bộ pipeline:** Không; các intermediate operation thường lazy đến khi có terminal.
4. **Nghĩ `concat` trì hoãn cả việc gọi factory tạo đối số:** Java vẫn đánh giá các biểu thức đối số ngay khi gọi `concat`.
5. **Tin rằng `concat` tự sort hoặc deduplicate:** Kết quả chỉ là phép nối; cần `sorted`, `distinct` nếu hợp đồng đòi hỏi.
6. **Dùng `Stream.concat` với một trong hai đối số null:** Ném `NullPointerException`, hãy dùng `Stream.empty()` khi rỗng.
7. **Quên đóng Stream chứa I/O:** Terminal operation không tự close; dùng `try-with-resources`.
8. **Mở hai nguồn ngay trong đối số và không xử lý lỗi mở nguồn sau:** Nếu nguồn sau ném lỗi, nguồn trước có thể bị bỏ quên; quản lý từng nguồn đã mở.
9. **Nối quá sâu một số lượng lớn Stream:** Có thể tạo cây pipeline sâu và rủi ro lỗi stack; chọn `flatMap` hoặc cách thiết kế nguồn khác.
10. **Giả định tất cả thao tác chạy tuần tự:** `concat` sẽ là parallel nếu bất kỳ đầu vào parallel; chú ý order và side effects.
11. **Thêm dữ liệu mutable mà quên nguồn không an toàn concurrent:** Builder và collection mutable không tự thread-safe.
12. **Nhầm Builder với accumulator của parallel reduction:** Builder chủ yếu dành cho giai đoạn tạo nguồn; đừng dùng một Builder chia sẻ để thu thập các phần tử từ parallel Stream.
13. **Nghĩ close handler được gọi sau `toList` mà không cần `close`:** Close handler chỉ được gọi khi Stream được đóng (trực tiếp hoặc qua try-with-resources).
14. **Giữ lại Stream nguồn sau concat để dùng tiếp:** Các Stream đã được liên kết với pipeline; không coi chúng là các nguồn độc lập có thể tái tiêu thụ.

## 13. Bài tập tự luyện

**Bài 1.** Viết `Stream.Builder<String>` thêm `"core"`, thêm `"optional"` chỉ nếu một cờ bằng `true`, rồi `build().toList()`. Dự đoán kết quả khi cờ lần lượt `true` và `false`.

**Bài 2.** Tạo Stream số nguyên bằng `Stream.<Integer>builder().add(1).add(2).build()`. Giải thích vì sao không được thêm `3` sau `build()`.

**Bài 3.** Với `Stream.concat(Stream.of(2,4), Stream.of(1,3))`, kết quả `toList()` là gì? Có tự sorted không?

**Bài 4.** Giải thích sự khác nhau giữa tạo `Stream.concat(openA(), openB())` và gọi `toList()` sau đó. Nếu `openA()` và `openB()` có log khi tạo nguồn, dòng log được in lúc nào?

**Bài 5.** Dùng `AtomicInteger` để đếm các phần tử thực sự đi qua `filter` của hai nguồn đã nối; vì sao giá trị bộ đếm vẫn bằng `0` trước terminal operation?

**Bài 6.** Nếu nguồn A có file I/O và nguồn B có file I/O, vì sao cần `try-with-resources`? Làm sao tránh rò rỉ nếu mở file B thất bại sau khi mở A thành công?

**Bài 7.** Nối ba Stream bằng `concat`; sau đó viết lại bằng `Stream.of(s1,s2,s3).flatMap(s -> s)`. Nêu lợi ích của cách thứ hai khi số lượng nguồn tăng nhiều.

**Bài 8.** `Stream.concat(Stream.of(1).parallel(), Stream.of(2)).isParallel()` trả gì? Điều đó có đảm bảo chương trình xử lý trên nhiều thread không?

**Bài 9.** Phân biệt `Stream.<String>builder().add(null).build()` và `Stream.concat(null, Stream.empty())`: trường hợp nào có thể tạo Stream, trường hợp nào ném lỗi?

**Bài 10.** Một pipeline dùng `peek` để ghi sự kiện thanh toán cho từng phần tử. Vì sao không nên dựa vào `peek` để thực hiện tác dụng phụ nghiệp vụ quan trọng?

### Gợi ý đáp án

1. Cờ true → `[core, optional]`; false → `[core]`.
2. Builder chuyển sang trạng thái built và từ chối thao tác thêm phần tử tiếp theo.
3. `[2, 4, 1, 3]`; concat không sắp xếp.
4. Các lời gọi `openA/openB` diễn ra trong lúc đánh giá đối số tạo nguồn; duyệt phần tử xảy ra khi terminal operation yêu cầu.
5. `filter` là intermediate operation; chưa duyệt thì chưa thực thi body trên phần tử.
6. Stream có thể giữ resource; quản lý từng nguồn ở phạm vi try hoặc cơ chế đóng tương đương để xử lý cả lỗi mở nguồn sau.
7. Cách `flatMap` tránh một cây `concat` lồng nhiều cấp.
8. `true`, nhưng chỉ là chế độ parallel; không đảm bảo số thread hay tốc độ.
9. Builder có thể chứa phần tử null; concat yêu cầu chính các object Stream đầu vào không null.
10. Các tối ưu hóa và short-circuit có thể không thực thi callback theo cách dự kiến; sử dụng nơi điều phối riêng cho thao tác nghiệp vụ bắt buộc.

## Kết luận

**`Stream.builder()` tạo nguồn từ các phần tử được đưa vào trước `build()`; `Stream.concat(a,b)` kết hợp hai Stream đã có để tạo một pipeline nối.** Cả hai được dùng trong Java 17 và cùng chịu nguyên tắc Stream chỉ tiêu thụ một lần.

Khi áp dụng thực tế, hãy phân biệt rõ **thời điểm xây nguồn** với **thời điểm duyệt nguồn**, bảo toàn thứ tự nếu yêu cầu, quản lý close với nguồn I/O và tránh tác dụng phụ không kiểm soát trong pipeline. Nếu bài toán chỉ có vài phần tử hoặc đã có một collection, hãy chọn API ngắn gọn hơn thay vì dùng Builder hoặc concat một cách hình thức.
