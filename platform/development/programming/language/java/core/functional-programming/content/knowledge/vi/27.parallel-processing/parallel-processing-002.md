# Chế độ cuối cùng áp dụng cho toàn pipeline trong Java Stream

## 1. Mục tiêu

Trong Java Stream, ta có thể yêu cầu **xử lý tuần tự (sequential)** hoặc **xử lý song song (parallel)** bằng các phương thức:

~~~java
stream.sequential()
stream.parallel()
~~~

Điểm dễ hiểu nhầm là nếu viết `parallel()` ở đầu pipeline rồi `sequential()` ở giữa, **không phải** các công đoạn ở trước chạy song song còn các công đoạn ở sau chạy tuần tự.

**Quy tắc cốt lõi:** đối với một Stream pipeline, **lần đặt chế độ tuần tự/song song sau cùng có hiệu lực cho toàn pipeline khi terminal operation thực thi**. Những phương thức `parallel()` và `sequential()` không chia pipeline thành những “đoạn” vận hành độc lập theo mode khác nhau.

Sau bài học, bạn có thể:

- Đọc đúng `stream()`, `parallelStream()`, `parallel()`, `sequential()` và `isParallel()`.
- Dự đoán **mode cuối cùng** khi pipeline có nhiều lần chuyển đổi.
- Phân biệt **execution mode** với **encounter order** và với các phép toán `unordered()`, `sorted()`, `forEachOrdered()`.
- Hiểu vì sao mode được quyết định cho cả pipeline khi đánh giá, không phải “cố định” tại thời điểm thêm từng intermediate operation.
- Xác định yêu cầu **stateless**, **non-interfering** và tính đúng của reduction/collector khi chạy parallel.
- Tránh lỗi dựa vào số thread, thứ tự log, mutable shared state hoặc nghĩ parallel chắc chắn nhanh hơn.
- Kiểm thử bằng ví dụ Java 17 hoàn chỉnh và đầu ra xác định.

## 2. Một pipeline chỉ có một chế độ thực thi hiệu lực

Ví dụ:

~~~java
List<Integer> result = numbers.stream()
        .parallel()
        .map(n -> n * 2)
        .sequential()
        .filter(n -> n > 5)
        .toList();
~~~

Giả sử `numbers` là một `List<Integer>` hợp lệ. Ở đây:

1. `numbers.stream()` tạo Stream **tuần tự** ban đầu.
2. `parallel()` đặt yêu cầu mode **song song** cho Stream pipeline.
3. `map(...)` thêm một thao tác trung gian lazy.
4. `sequential()` chuyển mode hiệu lực về **tuần tự**.
5. `filter(...)` thêm một thao tác trung gian lazy nữa.
6. `toList()` là terminal operation yêu cầu đánh giá pipeline.

**Kết luận:** toàn bộ pipeline này được đánh giá ở **sequential mode**. Không có yêu cầu rằng `map` ở trước `sequential()` phải chạy song song.

Ngược lại:

~~~java
List<Integer> result = numbers.stream()
        .sequential()
        .map(n -> n * 2)
        .parallel()
        .filter(n -> n > 5)
        .toList();
~~~

Ở đây lần đặt mode sau cùng là `parallel()`, nên **toàn pipeline** được yêu cầu đánh giá ở **parallel mode**. Không có chuyện `map` “đã chạy xong tuần tự” trước khi gặp `parallel()`: intermediate operation vẫn lazy.

### 2.1. “Cuối cùng” là cuối cùng trong các lần đặt mode

Một pipeline có thể có nhiều method call, nhưng không phải method cuối cùng bất kỳ quyết định parallel hay sequential.

~~~java
var pipeline = numbers.stream()
        .parallel()
        .filter(n -> n > 0)
        .map(n -> n * 2);
~~~

Hai bước cuối là filter và map, **không thay đổi execution mode**, nên pipeline vẫn có **parallel mode**.

Trong trường hợp:

~~~java
var pipeline = numbers.stream()
        .parallel()
        .filter(n -> n > 0)
        .sequential()
        .map(n -> n * 2);
~~~

Lần đặt mode sau cùng là sequential, nên **sequential mode** có hiệu lực.

Hãy đọc `parallel()`/`sequential()` như **thiết lập thuộc tính thực thi cho pipeline**, không phải “một thao tác dữ liệu áp dụng riêng cho những bước ngay sau nó”.

## 3. Vì sao quy tắc này gắn với lazy evaluation?

Stream bao gồm:

~~~text
Nguồn -> intermediate A -> intermediate B -> ... -> terminal
                  \                      /
                   \-- mô tả pipeline --/
                             |
                             v
                      lúc terminal chạy
                             |
                             v
                 đánh giá pipeline theo mode hiệu lực
~~~

Các intermediate operation như:

~~~java
filter(...)
map(...)
flatMap(...)
sorted(...)
distinct(...)
limit(...)
peek(...)
~~~

thường **không lập tức duyệt dữ liệu** khi được thêm vào pipeline. Chúng đóng góp quy tắc cho việc thực thi về sau. Chỉ khi terminal operation như `toList()`, `collect(...)`, `reduce(...)`, `sum()`, `count()` hoặc `forEach(...)` được gọi, pipeline mới được yêu cầu tạo kết quả.

Vì các bước trước đó **chưa bị ép phải hoàn tất lúc xây dựng**, một lần gọi `sequential()` ở cuối có thể xác lập chế độ cho việc thực thi toàn chuỗi, kể cả các `map/filter` được khai báo trước.

### 3.1. Parallel mode không phải một stage tên “parallel”

Ví dụ về cách hiểu **sai**:

~~~text
source ---- parallel() ---- map() ---- sequential() ---- filter()
               |            |            |                 |
          bật thread      đã chạy     đóng thread      chạy tiếp
~~~

Đây **không phải** mô hình của Stream. `parallel()` và `sequential()` không có nghĩa tự mở/đóng thread ngay tại vị trí xuất hiện, không tạo barrier và không tự materialize kết quả sau mỗi công đoạn.

Cách hiểu **đúng**:

~~~text
source -> map -> filter -> terminal
            \___pipeline___/
             mode cuối: sequential
~~~

Stream implementation sẽ lập kế hoạch/đánh giá pipeline theo mode đã đặt. Parallel execution có thể dùng nhiều thread và chia công việc, nhưng chi tiết thread là implementation/runtime behavior, không phải hợp đồng “mỗi bước chạy trên thread riêng”.

## 4. Nguồn tạo Stream và chế độ mặc định

Các cách thường gặp:

| Cách tạo | Mode ban đầu | Ví dụ |
| --- | --- | --- |
| `collection.stream()` | Sequential | `orders.stream()` |
| `collection.parallelStream()` | Parallel | `orders.parallelStream()` |
| `Stream.of(...)` | Sequential | `Stream.of(1,2,3)` |
| `IntStream.range(...)` | Sequential | `IntStream.range(0,10)` |
| `stream.parallel()` | Parallel | `orders.stream().parallel()` |
| `stream.sequential()` | Sequential | `orders.parallelStream().sequential()` |

Đây là **mặc định/thiết lập của các cách tạo tiêu chuẩn**, trước khi caller có thể tiếp tục gọi các phương thức chuyển mode. Một số API/nguồn tùy biến có thể tạo Stream với đặc tính riêng, vì thế khi làm việc với một Stream được truyền từ nơi khác, nên kiểm tra hợp đồng nguồn hoặc `isParallel()` khi thực sự cần biết thuộc tính hiện tại.

Ví dụ:

~~~java
List<String> items = List.of("A", "B");

Stream<String> s1 = items.stream();
Stream<String> s2 = items.parallelStream();

System.out.println(s1.isParallel()); // false
System.out.println(s2.isParallel()); // true
~~~

`isParallel()` là phương thức của **BaseStream** và cho biết Stream hiện được đánh dấu parallel hay không. Nó không thực hiện terminal operation để duyệt các phần tử.

### 4.1. Chuyển ngược từ parallelStream()

~~~java
List<String> result = items.parallelStream()
        .map(String::toLowerCase)
        .sequential()
        .toList();
~~~

Mặc dù nguồn được tạo bởi `parallelStream()`, lời gọi `sequential()` sau đó khiến pipeline được đánh giá ở sequential mode.

Và ngược lại:

~~~java
List<String> result = items.stream()
        .map(String::toLowerCase)
        .parallel()
        .toList();
~~~

Bắt đầu từ `stream()` tuần tự không ngăn bạn chuyển sang parallel trước terminal.

**Điểm cần phân biệt:** mode của Stream không phải đặc tính bất biến của collection. Cùng một List có thể tạo **hai Stream riêng** với hai mode khác nhau mà không thay đổi chính List.

## 5. Nhiều lần chuyển mode: thao tác sau cùng thắng

Ví dụ có ba lần đặt mode:

~~~java
var pipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 2)
        .parallel()
        .map(n -> n * 10);
~~~

**Lần cuối** là `parallel()`, nên `pipeline.isParallel()` là **true** và terminal sẽ xử lý pipeline theo parallel mode.

Nếu thêm `sequential()` vào ngay trước terminal:

~~~java
var sequentialPipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 2)
        .parallel()
        .map(n -> n * 10)
        .sequential();
~~~

thì `sequentialPipeline.isParallel()` là **false** và toàn pipeline được yêu cầu xử lý tuần tự.

**Hãy chú ý thời điểm:** chỉ được thay mode **trước khi Stream đã được tiêu thụ**. Sau một terminal operation, Stream không thể được dùng lại như một pipeline mới.

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3);
long count = stream.count();

// Không được tiếp tục dùng stream đã tiêu thụ:
// stream.parallel().toList(); // IllegalStateException (hoặc lỗi dùng lại).
~~~

Tạo **Stream mới từ nguồn** nếu cần một lượt xử lý khác.

## 6. isParallel() xác nhận cờ mode, không đo hiệu năng hoặc số thread

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3).parallel();

boolean parallelMode = stream.isParallel();
System.out.println(parallelMode); // true
~~~

Điều được bảo đảm ở đây là **flag của Stream**. Điều đó **không chứng minh**:

- JVM chắc chắn dùng hơn một thread cho một pipeline nhỏ.
- Mỗi `map` hoặc `filter` sẽ chạy trên một thread khác nhau.
- Tốc độ sẽ nhanh hơn sequential.
- Các callback chạy theo một lịch trình cố định.
- Output sẽ bị đảo thứ tự.

Thư viện có thể quyết định cách chia dữ liệu, mức độ parallelism và thứ tự lập lịch tùy nguồn, terminal, khối lượng công việc và môi trường. Một Stream có `isParallel() == true` có thể không thu được tăng tốc đáng kể.

### 6.1. Không dùng Thread.currentThread() làm test chính

Ví dụ:

~~~java
numbers.parallelStream().forEach(n ->
        System.out.println(Thread.currentThread().getName() + ":" + n));
~~~

Tên thread và thứ tự in có thể thay đổi theo lần chạy. Đoạn này chỉ phù hợp cho **quan sát/debug**, không dùng để khẳng định output chính xác hoặc viết bài kiểm thử luôn phải thấy một số worker thread nhất định.

Muốn kiểm tra quy tắc chuyển mode, hãy test **isParallel()** trên pipeline chưa tiêu thụ. Muốn kiểm tra correctness, hãy test **giá trị đầu ra** và quy tắc rút gọn, thay vì dựa trên log thread.

## 7. Parallel/sequential khác encounter order

Đây là hai khái niệm độc lập:

1. **Execution mode**: pipeline được đánh giá tuần tự hay song song?
2. **Encounter order**: dữ liệu có thứ tự gặp được nguồn/pipeline xác định hay không?

Ví dụ **List** có encounter order; một stream tạo từ List vẫn mang encounter order khi bạn gọi `parallel()`, trừ khi có thao tác hoặc nguồn thay đổi đặc tính ấy.

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> doubled = values.parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
~~~

Dù pipeline parallel, **toList() giữ encounter order nếu Stream có encounter order**. Đây là một lý do không được kết luận “parallel nghĩa là kết quả tự đảo ngẫu nhiên”.

### 7.1. unordered() không biến Stream thành parallel

~~~java
Stream<Integer> p = Stream.of(1, 2, 3)
        .parallel()
        .unordered()
        .sequential();

System.out.println(p.isParallel()); // false
~~~

`unordered()` loại bỏ **ràng buộc encounter order** đối với pipeline khi thích hợp; nó không phải một cách bật parallel hoặc sequential.

Trong ví dụ trên, mode cuối là **sequential**, dù trước đó đã gọi `parallel()` và `unordered()`.

Tương tự:

~~~java
Stream<Integer> p = Stream.of(1, 2, 3)
        .sequential()
        .unordered()
        .parallel();
~~~

Mode cuối là parallel. Việc bỏ ràng buộc encounter order là một **thuộc tính khác** có thể giúp một số phép toán song song tối ưu khi nghiệp vụ không cần thứ tự.

### 7.2. sorted() xác định thứ tự theo Comparator

~~~java
List<Integer> sorted = List.of(4, 1, 3, 2)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 2, 3, 4]
~~~

`sorted()` là intermediate operation **stateful**, tạo phần tử theo thứ tự so sánh. Nó không chuyển parallel mode thành sequential mode. Một bước cần thứ tự hoặc buffer có thể giảm lợi ích của parallel, nhưng không đồng nghĩa pipeline đã bị tách thành “phần sorted tuần tự, phần còn lại song song” theo semantics mode.

### 7.3. limit() và takeWhile() trên ordered parallel stream

Với nguồn List có thứ tự:

~~~java
List<Integer> firstThree = List.of(1, 2, 3, 4, 5)
        .parallelStream()
        .limit(3)
        .toList();

System.out.println(firstThree); // [1, 2, 3]
~~~

Để lấy **đúng tiền tố ba phần tử**, pipeline phải tôn trọng encounter order. Một `limit` trên ordered parallel stream có thể tốn chi phí lớn hơn trên unordered stream. `takeWhile` và `dropWhile` cũng có các yêu cầu tiền tố tương ứng trên ordered stream.

Đừng gọi `unordered()` chỉ để tăng tốc nếu nghiệp vụ yêu cầu “ba phần tử đầu” hoặc xử lý một đoạn tiền tố theo thứ tự thời gian.

## 8. forEach và forEachOrdered: thứ tự callback khác execution mode

### 8.1. forEach trên parallel

~~~java
List.of(1, 2, 3, 4).parallelStream()
        .forEach(System.out::print);
~~~

**Không cam kết in theo “1234”**. Callback có thể chạy đồng thời hoặc theo thứ tự khác nhau.

### 8.2. forEachOrdered trên parallel

~~~java
List.of(1, 2, 3, 4).parallelStream()
        .forEachOrdered(System.out::print);
~~~

Với nguồn có encounter order, **forEachOrdered** bảo đảm các hành động thực hiện theo encounter order, nên chuỗi được in có thứ tự “1234” trong ví dụ này. Tuy nhiên, điều đó **không có nghĩa** Stream đã chuyển execution mode sang sequential. Nó là **ràng buộc của terminal operation**, có thể giới hạn hiệu năng và không bảo đảm mọi callback chạy trên main thread.

Nếu cần danh sách kết quả thay vì in/cập nhật state, ưu tiên:

~~~java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

Dữ liệu đầu ra nên được tạo bằng các phép toán rút gọn/collector có hợp đồng rõ, không bằng cách tự thêm vào một ArrayList bên ngoài từ parallel `forEach`.

## 9. Stateful và short-circuiting operation vẫn giữ chung mode

Một pipeline có thể chứa:

~~~java
List<Integer> result = values.stream()
        .parallel()
        .filter(n -> n > 0)
        .distinct()
        .sorted()
        .limit(5)
        .sequential()
        .toList();
~~~

**Mode cuối cùng là sequential** cho cả pipeline, dù các thao tác `distinct`, `sorted`, `limit` có đặc tính riêng.

- **filter** thường stateless, có thể kết hợp xử lý qua từng phần tử.
- **distinct** là stateful, cần phát hiện trùng.
- **sorted** là stateful, thường cần buffer để sắp đúng thứ tự.
- **limit** là short-circuiting, có thể giới hạn phần tử đi tiếp.
- **sequential** đặt mode hiệu lực, không tự sắp xếp, không tự lọc, cũng không phải một terminal.

Thay `sequential()` cuối bằng `parallel()` sẽ yêu cầu toàn pipeline parallel, nhưng không bảo đảm nhanh hơn vì stateful stages và ordering có thể làm tăng chi phí chia/gom.

### 9.1. Short-circuit có thể không kiểm tra tất cả phần tử

~~~java
boolean found = values.parallelStream()
        .anyMatch(n -> n > 100);
~~~

`anyMatch` có thể dừng khi đủ thông tin. Trong parallel, một số tác vụ khác vẫn có thể đang xử lý sau khi một tác vụ đã tìm thấy kết quả. Không được đo sự thành công của nghiệp vụ bằng số lần gọi Predicate.

Mode parallel/sequential quyết định chiến lược đánh giá, nhưng **không biến short-circuit thành một vòng lặp có số callback cố định**.

### 9.2. count có thể không gọi mọi map/peek

~~~java
long count = List.of(1, 2, 3).stream()
        .parallel()
        .peek(System.out::println)
        .sequential()
        .count();
~~~

Kết quả count là 3, nhưng `peek` có thể **không in gì** nếu implementation khai thác kích thước đã biết của nguồn mà không cần traverse pipeline. Không được kết luận “sequential mode khiến mọi lambda chắc chắn chạy”.

**Chế độ cuối cùng là quy tắc về cách đánh giá pipeline**, không phải hợp đồng về số lần gọi các lambda.

## 10. Lambda phải non-interfering và stateless

Những hành vi được truyền cho Stream, đặc biệt khi dùng parallel, thường phải:

- **Non-interfering:** không sửa nguồn đang được duyệt.
- **Stateless:** không phụ thuộc vào mutable state thay đổi theo những lần đánh giá phần tử.
- **Đúng về mặt nghiệp vụ:** cùng dữ liệu đầu vào và cấu hình ổn định tạo kết quả tương ứng.
- **An toàn đồng thời theo cách được sử dụng:** không gây race khi nhiều phần tử được xử lý cùng lúc.

Ví dụ **tốt**:

~~~java
List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

Filter và map chỉ đọc n và tạo kết quả, không cập nhật state chung.

Ví dụ **có vấn đề**:

~~~java
List<Integer> shared = new ArrayList<>();

numbers.parallelStream()
        .forEach(n -> shared.add(n));
~~~

Đây là phản ví dụ cần import ArrayList và có nguồn numbers. `ArrayList` không thread-safe; các lần add có thể race, kết quả thiếu/trùng hoặc dữ liệu nội bộ sai.

**Đổi sang `sequential()` cuối pipeline có thể làm phản ví dụ này tình cờ ít lỗi concurrency hơn, nhưng không biến việc đặt side effect khó quản lý thành thiết kế tốt**. Khi cần tạo danh sách kết quả, dùng `toList()` hoặc collector phù hợp.

### 10.1. synchronized không thay thế ngữ nghĩa

Bọc shared collection trong synchronizedList có thể bảo vệ một số thao tác, nhưng:

- Không tự bảo đảm thứ tự encounter trong parallel `forEach`.
- Không biến một Predicate phụ thuộc bộ đếm thành stateless.
- Không sửa hợp đồng identity/associativity của `reduce`.
- Có thể gây tranh chấp lock, làm mất lợi ích parallel.

Hãy chọn **mô hình tổng hợp đúng**, không chỉ thêm khóa để “chạy được”.

## 11. Reduction và collector trong parallel mode

### 11.1. Tổng có identity và phép kết hợp hợp lệ

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .sum();

System.out.println(sum); // 5050
~~~

Với phép cộng int trong miền giá trị ví dụ, phép tổng hợp có identity 0 và kết quả phù hợp khi chia/gom. Không dùng biến tổng mutable chung ở ngoài `forEach`.

Có thể viết:

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum);
~~~

Kết quả cũng là 5050.

### 11.2. reduce phải có hợp đồng đúng

Với overload ba đối số:

~~~java
<U> U reduce(U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

**Identity** phải là phần tử đơn vị, **combiner** phải có tính kết hợp, accumulator phải tương thích với combiner và không dựa vào shared mutable accumulator.

Không làm:

~~~java
// Phản ví dụ: mutable identity không hợp lệ với reduce.
// stream.parallel().reduce(
//     new ArrayList<T>(),
//     (list, item) -> { list.add(item); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
~~~

Tại parallel reduction, combiner có thể nhận hai tham chiếu dùng chung và dữ liệu bị nhân đôi hoặc race. Dùng **collect** cho mutable accumulation, với supplier tạo container riêng.

### 11.3. Collector thích hợp khi tạo container

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toList());
~~~

Kết quả chứa A, B, C và giữ encounter order cho ordered stream theo semantics của collector. **Collectors.toList()** không cam kết lớp List cụ thể hoặc tính mutable; nếu cần danh sách unmodifiable theo Stream.toList, có thể dùng trực tiếp `toList()` (Java 16+).

Nếu muốn đảm bảo tạo **ArrayList**, dùng:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Các mảnh ghép trên cần import List, Stream, Collectors, ArrayList. Supplier tạo container mới phù hợp cho các phần công việc, khác với việc một shared ArrayList bên ngoài được mọi callback tùy ý thêm vào.

## 12. Parallel có luôn tăng tốc không?

**Không.** Parallel Stream có chi phí:

- Tách nguồn thành phần công việc.
- Lập lịch, điều phối và gom kết quả.
- Buffer/đồng bộ cho các thao tác như sorted, distinct, ordered limit.
- Chia sẻ tài nguyên, cache/memory contention và chi phí boxing.
- Side effect, I/O hoặc một nguồn không chia được hiệu quả.

Parallel có khả năng có ích khi:

1. Nguồn đủ lớn và **phân chia hiệu quả** (ví dụ array hoặc List với Spliterator phù hợp).
2. Mỗi phần tử đòi hỏi công việc tính toán tương đối lớn, độc lập.
3. Các phép toán stateless/non-interfering, dữ liệu ổn định.
4. Reduction/collector có thể gộp kết quả đúng.
5. Có tài nguyên CPU và benchmark thực tế cho thấy lợi ích.

Sequential thường hợp lý khi tập dữ liệu nhỏ, công việc nhẹ, hoặc các bước cần thứ tự nghiêm ngặt và trạng thái phức tạp.

### 12.1. Parallel Stream không phải API async

`parallel()` không trả `Future`. Một terminal operation trên parallel stream thường **chặn cho tới khi phép tổng hợp hoàn tất** (hoặc thất bại) rồi mới trả kết quả cho caller.

Nếu muốn tác vụ chạy bất đồng bộ và trả kết quả sau, cân nhắc **CompletableFuture** hoặc executor theo hợp đồng phù hợp. Không đồng nhất `parallel()` với “nền” hoặc “fire-and-forget”.

### 12.2. I/O và blocking tasks

Parallel Stream không mặc nhiên phù hợp cho gọi database/HTTP ở mỗi phần tử. Blocking I/O có thể gây tranh chấp tài nguyên và làm khó kiểm soát concurrency, retry, timeout và backpressure.

Khi cần giới hạn số request đồng thời, điều phối hàng đợi hoặc xử lý lỗi theo từng tác vụ, một executor được cấu hình rõ ràng hoặc mô hình concurrency chuyên dụng thường dễ kiểm soát hơn. Không bật parallel vì muốn “cùng lúc tải nhiều dữ liệu” mà chưa xét mức tải của dịch vụ đích.

### 12.3. Không giả định parallelism cố định

Chi tiết pool/thực thi phụ thuộc JDK và môi trường. Không viết logic nghiệp vụ yêu cầu chính xác n worker hoặc dựa vào tên `ForkJoinPool.commonPool-worker-N`.

Một benchmark hợp lệ cần warm-up, dữ liệu đại diện, tránh tối ưu sai và đánh giá cả throughput, latency, memory. Với các bài đo nghiêm túc, dùng công cụ chuyên biệt như **JMH** thay vì `System.currentTimeMillis()` cho một lần chạy duy nhất.

## 13. Chương trình Java 17 độc lập

Ví dụ này minh họa **mode cuối thắng cho toàn pipeline**, xác minh flag bằng `isParallel()`, nhưng chỉ in **kết quả xác định** chứ không phụ thuộc tên thread hoặc thứ tự thực thi callback.

Tạo file **PipelineModeDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PipelineModeDemo {
    static Stream<Integer> numbers() {
        return IntStream.rangeClosed(1, 6).boxed();
    }

    public static void main(String[] args) {
        Stream<Integer> lastSequential = numbers()
                .parallel()
                .map(n -> n * 2)
                .sequential()
                .filter(n -> n % 3 == 0);

        System.out.println("A parallel: "
                + lastSequential.isParallel());
        System.out.println("A result: " + lastSequential.toList());

        Stream<Integer> lastParallel = numbers()
                .sequential()
                .filter(n -> n % 2 == 0)
                .parallel()
                .map(n -> n * 10);

        System.out.println("B parallel: "
                + lastParallel.isParallel());
        System.out.println("B result: " + lastParallel.toList());

        Stream<Integer> manySwitches = numbers()
                .parallel()
                .map(n -> n + 1)
                .sequential()
                .filter(n -> n >= 4)
                .parallel()
                .map(n -> n * 2);

        System.out.println("C parallel: "
                + manySwitches.isParallel());
        System.out.println("C result: " + manySwitches.toList());

        Stream<Integer> unorderedThenSequential = numbers()
                .parallel()
                .unordered()
                .sequential();

        System.out.println("D parallel: "
                + unorderedThenSequential.isParallel());
        System.out.println("D sorted: "
                + unorderedThenSequential.sorted().toList());

        List<Integer> orderedResult = numbers()
                .parallel()
                .map(n -> n * n)
                .toList();

        System.out.println("parallel ordered result: "
                + orderedResult);

        int sum = IntStream.rangeClosed(1, 6)
                .parallel()
                .sum();

        System.out.println("parallel sum: " + sum);

        Stream<Integer> finalSequential = numbers()
                .parallel()
                .sequential()
                .parallel()
                .sequential();

        System.out.println("E parallel: "
                + finalSequential.isParallel());
        System.out.println("E result: " + finalSequential.toList());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac PipelineModeDemo.java
java PipelineModeDemo
~~~

**Đầu ra dự kiến:**

~~~text
A parallel: false
A result: [6, 12]
B parallel: true
B result: [20, 40, 60]
C parallel: true
C result: [8, 10, 12, 14]
D parallel: false
D sorted: [1, 2, 3, 4, 5, 6]
parallel ordered result: [1, 4, 9, 16, 25, 36]
parallel sum: 21
E parallel: false
E result: [1, 2, 3, 4, 5, 6]
~~~

### 13.1. Giải thích A

~~~java
numbers().parallel()
        .map(n -> n * 2)
        .sequential()
        .filter(n -> n % 3 == 0)
~~~

- Nguồn ban đầu là 1, 2, 3, 4, 5, 6.
- `map(n -> n*2)` tạo 2, 4, 6, 8, 10, 12.
- `filter(n % 3 == 0)` giữ 6 và 12.
- **sequential() là lần đặt mode cuối**, nên `isParallel()` là false.

Tuy `map` nằm **trước** `sequential()`, nó không được yêu cầu chạy trong một “pha parallel” riêng.

### 13.2. Giải thích B

~~~java
numbers().sequential()
        .filter(n -> n % 2 == 0)
        .parallel()
        .map(n -> n * 10)
~~~

- Lọc số chẵn: 2, 4, 6.
- Nhân 10: 20, 40, 60.
- **parallel() là lần đặt mode cuối**, nên `isParallel()` là true.
- `toList()` vẫn trả thứ tự [20, 40, 60] vì Stream có encounter order từ nguồn.

Không suy luận rằng `filter` đã chạy xong tuần tự trước khi bật parallel.

### 13.3. Giải thích C

Với dãy 1..6:

1. `map(n -> n+1)` tạo 2..7.
2. `filter(n >= 4)` giữ 4, 5, 6, 7.
3. `map(n*2)` tạo 8, 10, 12, 14.
4. Lần chuyển mode cuối là `parallel()`, nên **C parallel: true**.

Sự có mặt của `sequential()` trước đó không làm các stage đứng trước nó có mode riêng.

### 13.4. Giải thích D

Pipeline D có `parallel().unordered().sequential()`:

- `unordered()` **không** phải thay đổi execution mode.
- `sequential()` là lần đặt mode cuối → false.
- `sorted()` xác định kết quả tăng dần → [1, 2, 3, 4, 5, 6].

Nếu bỏ `sorted()` khỏi ví dụ unordered, không nên đặt kỳ vọng chính xác về thứ tự cho mọi cách kết hợp nguồn/terminal.

### 13.5. Giải thích kết quả ordered và tổng

- `numbers().parallel().map(n*n).toList()` trả [1,4,9,16,25,36] theo encounter order. Đây là kết quả không đổi dù trình tự thực thi callback có thể khác.
- `IntStream.rangeClosed(1,6).parallel().sum()` cho 21. Phép cộng số nguyên trong ví dụ có kết quả xác định, không cần mutable counter chia sẻ.

### 13.6. Giải thích E

Pipeline E có bốn lần chuyển mode: parallel → sequential → parallel → sequential. **Lần cuối cùng** là sequential. Dữ liệu không qua filter/map, nên danh sách vẫn [1..6]. **isParallel() là false**, không phụ thuộc số lần chuyển mode trước đó.

## 14. Kiểm thử semantics, không kiểm thử trace

Có thể viết unit test kiểm tra:

1. Stream tạo bằng `stream()` mặc định có `isParallel()==false`.
2. Stream tạo bằng `parallelStream()` mặc định có `isParallel()==true`.
3. `parallel().sequential()` trả mode false.
4. `sequential().parallel()` trả mode true.
5. `parallel().map(...).sequential()` trả mode false, vì mode cuối áp dụng cho pipeline.
6. Cùng pipeline xử lý giá trị thuần cho kết quả phù hợp cả sequential/parallel.
7. `unordered()` không tự đổi mode.
8. `forEachOrdered` có ràng buộc thứ tự cho ordered stream mà không nhất thiết đổi flag parallel.
9. Pipeline với `sorted/limit` vẫn đúng kết quả nghiệp vụ theo encounter order.
10. Parallel reducer/collector phải tương thích với việc chia và ghép công việc, không dùng shared mutable state.

Một test gọn:

~~~java
boolean expectedSequential = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n * 2)
        .sequential()
        .isParallel();

if (expectedSequential) {
    throw new AssertionError("Expected final sequential mode");
}
~~~

Đoạn này cần import Stream và nằm trong phương thức. `isParallel()` chỉ đọc mode; không phải terminal duyệt dữ liệu.

**Không test** “phải thấy 4 thread” hoặc “phần tử 1 phải được in trước phần tử 2 từ parallel forEach”. Đó không phải hợp đồng của execution mode.

### 14.1. So kết quả của sequential và parallel

Nếu phép toán có logic thuần và reduction thích hợp:

~~~java
int sequential = IntStream.rangeClosed(1, 1000)
        .sequential()
        .sum();

int parallel = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

if (sequential != parallel || parallel != 500_500) {
    throw new AssertionError("Unexpected sum");
}
~~~

Trong ví dụ, tổng nằm trong miền int. Với double, sai số rounding có thể phụ thuộc thứ tự kết hợp; không được mặc định mọi kết quả floating-point luôn trùng chính xác từng bit.

## 15. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Tưởng stage trước `sequential()` vẫn parallel | Mode cuối áp dụng toàn pipeline | Đọc toàn chuỗi trước terminal |
| Tưởng `parallel()` lập tức chạy công việc | Intermediate vẫn lazy | Terminal mới yêu cầu đánh giá |
| Nghĩ `parallelStream()` không thể chuyển sequential | Có thể gọi `sequential()` sau đó | Dùng mode phù hợp cho mục tiêu |
| Nghĩ `unordered()` tương đương `parallel()` | Order và execution mode độc lập | Phân biệt thuộc tính |
| Nghĩ `parallel()` làm `toList()` mất thứ tự | Ordered stream có encounter order | Dựa vào hợp đồng terminal |
| Nghĩ `forEachOrdered()` làm mode sequential | Nó ràng buộc thứ tự hành động | Không suy luận mode từ thứ tự |
| Gọi `isParallel()==true` rồi đòi nhiều thread | Đây là flag, không phải số thread | Không test tên/số lượng thread |
| Dùng `parallel().peek(...).count()` cho audit | Callback có thể bị bỏ qua/đánh giá khác | Tách bước xử lý bắt buộc |
| Dùng ArrayList chung trong parallel forEach | Có thể race và sai dữ liệu | Dùng collect/toList |
| Dùng mutable object chung trong reduce | Sai identity/associativity/alias | Reduce thuần hoặc collect đúng |
| Nghĩ parallel luôn nhanh | Có overhead và giới hạn do thứ tự/stateful | Benchmark thực tế |
| Bật parallel cho I/O không kiểm soát | Có thể cạn tài nguyên/khó retry | Dùng executor/thiết kế concurrency rõ |
| Dùng lại Stream sau terminal | Stream chỉ tiêu thụ một lần | Tạo Stream mới |
| Đổi `sorted().limit(3)` thành `limit(3).sorted()` | Đổi nghĩa top-k | Giữ thứ tự nghiệp vụ |

## 16. Bài tập

### Bài 1 — Mode cuối là gì?

~~~java
var s = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n + 1)
        .sequential()
        .filter(n -> n > 0);
~~~

**Hỏi:** `s.isParallel()` là gì? **Đáp án:** false. Lần đặt mode cuối là sequential; map ở trước không tạo pha parallel độc lập.

### Bài 2 — Đảo vị trí chuyển mode

~~~java
var s = Stream.of(1, 2, 3)
        .sequential()
        .filter(n -> n > 1)
        .parallel()
        .map(n -> n * 10);
~~~

**Đáp án:** `s.isParallel()` là true; kết quả `s.toList()` là [20,30] vì Stream.of có encounter order.

### Bài 3 — Phân biệt order và mode

~~~java
var s = Stream.of(3, 1, 2)
        .parallel()
        .unordered()
        .sequential()
        .sorted();
~~~

**Hỏi:** mode cuối, và kết quả `toList()`? **Đáp án:** mode sequential, kết quả [1,2,3]. `unordered()` không đổi mode; `sorted()` tạo thứ tự tăng dần.

### Bài 4 — Có nên dùng shared List?

Một lập trình viên dùng `numbers.parallelStream().forEach(sharedList::add)` với ArrayList. **Đáp án:** không nên, vì ArrayList không thread-safe và forEach không bảo đảm encounter order. Dùng `map(...).toList()` hoặc collector phù hợp.

### Bài 5 — Thiết kế tiêu chí performance

Bạn có 1.000 phần tử, mỗi phần tử chỉ cộng 1. Có nên dùng parallel? **Gợi ý:** chưa đủ căn cứ; overhead có thể lớn hơn công việc. Hãy so sánh cả sequential và parallel bằng benchmark có warm-up và dữ liệu đại diện, không giả định parallel nhanh hơn.

### Bài 6 — Chọn terminal để giữ thứ tự

Một danh sách có thứ tự cần in từng phần tử theo encounter order. Trên parallel stream, `forEach` hay `forEachOrdered` phù hợp hơn? **Đáp án:** `forEachOrdered` nếu thật sự yêu cầu thứ tự hành động, nhưng không có nghĩa mode chuyển thành sequential và vẫn cần xử lý side effect/lỗi đúng hợp đồng.

## 17. Ghi nhớ

**Chế độ `parallel()` hoặc `sequential()` được đặt sau cùng có hiệu lực cho toàn Java Stream pipeline khi terminal operation thực thi.** Nó không chia pipeline thành các công đoạn được chạy theo những mode khác nhau chỉ vì vị trí gọi phương thức.

- **parallel()** đặt chế độ song song; **sequential()** đặt chế độ tuần tự; **isParallel()** đọc flag hiệu lực.
- **Intermediate operations lazy**, vì thế mode cuối có thể áp dụng cho những bước được khai báo trước đó.
- **Execution mode độc lập với encounter order**: parallel không mặc nhiên đảo thứ tự kết quả; unordered không mặc nhiên bật parallel.
- **forEachOrdered** ràng buộc thứ tự hành động, không phải công tắc chuyển sang sequential.
- **Stateless, non-interfering và reduction đúng hợp đồng** là điều kiện quan trọng cho xử lý song song đáng tin.
- **Parallel không mặc nhiên nhanh hơn và không tự bất đồng bộ**; hãy đo hiệu năng và kiểm soát tài nguyên.
- **Không dựa vào số thread, thứ tự log, số lần callback hay shared mutable state** để quyết định correctness của nghiệp vụ.

Khi review một pipeline dài, hãy tìm **lần gọi `parallel()` hoặc `sequential()` sau cùng trước terminal**, xác định mode chung; sau đó kiểm tra encounter order, stateful/short-circuit operations và tính đúng của các callback theo mode ấy.
