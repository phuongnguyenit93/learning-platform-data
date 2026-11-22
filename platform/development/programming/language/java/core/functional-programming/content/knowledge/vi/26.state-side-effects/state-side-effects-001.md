# Yêu cầu không can thiệp vào nguồn dữ liệu đang duyệt (Stream non-interference)

## 1. Vấn đề: tại sao không nên sửa nguồn trong pipeline Stream?

Java Stream API cho phép mô tả xử lý dữ liệu theo các bước như `filter`, `map`, `sorted` và kết thúc bằng `toList`, `collect`, `sum` hay `forEach`. Stream thường **không sở hữu một bản sao độc lập của dữ liệu nguồn**. Khi tạo stream từ `ArrayList`, mảng hoặc một tập hợp khác, pipeline vẫn gắn với nguồn ấy cho đến khi được tiêu thụ.

Ví dụ đúng:

~~~java
List<String> names = new ArrayList<>(
        List.of("An", "Binh", "Chi"));

List<String> longNames = names.stream()
        .filter(s -> s.length() >= 4)
        .map(String::toUpperCase)
        .toList();

System.out.println(names);     // [An, Binh, Chi]
System.out.println(longNames); // [BINH]
~~~

`filter` và `map` tạo kết quả xử lý qua pipeline; chúng không tự thêm, xóa hay thay thế phần tử trong danh sách `names`. Tuy nhiên, điều gì sẽ xảy ra nếu callback **chủ động sửa danh sách `names` trong lúc chính danh sách đó đang được duyệt**?

~~~java
// SAI về thiết kế; không chạy như một ví dụ an toàn.
List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

names.stream()
        .forEach(name -> {
            if (name.equals("An")) {
                names.add("Dung"); // Sửa nguồn đang được Stream duyệt.
            }
        });
~~~

Đây là hành vi **can thiệp vào nguồn** (*interference*). Nó vi phạm yêu cầu sử dụng Stream đúng cách với nguồn không hỗ trợ sửa đồng thời. Chương trình có thể ném `ConcurrentModificationException`, quan sát kết quả bất thường hoặc có hành vi không được hợp đồng Stream bảo đảm. Không thể lấy việc “máy của tôi chạy được” làm chứng cứ rằng cách viết trên là đúng.

**Quy tắc trung tâm:** với nguồn Stream không được thiết kế cho sửa đồng thời, hành vi truyền vào các operation của Stream phải **không làm thay đổi nguồn trong khi pipeline đang được thực thi** (*non-interfering*).

## 2. Non-interference nghĩa là gì?

Trong ngữ cảnh Java Stream, một hành vi như predicate, mapper hoặc action được gọi là **non-interfering** nếu nó **không sửa nguồn dữ liệu** mà pipeline đang duyệt, trừ trường hợp nguồn thuộc loại hỗ trợ sửa đồng thời một cách rõ ràng theo hợp đồng.

Một số ví dụ:

| Hành vi trong pipeline | Có can thiệp nguồn không? | Giải thích |
| --- | --- | --- |
| `filter(s -> !s.isBlank())` | Không | Chỉ đọc phần tử và quyết định giữ/bỏ |
| `map(String::trim)` | Không | Tạo giá trị biểu diễn mới; không sửa List nguồn |
| `map(s -> s.toUpperCase(Locale.ROOT))` | Không | Tạo giá trị kết quả mới |
| `filter(s -> { source.remove(s); return true; })` | **Có** | Xóa phần tử khỏi nguồn đang duyệt |
| `peek(s -> source.add("X"))` | **Có** | Thêm vào nguồn ngay trong pipeline |
| `forEach(s -> source.clear())` | **Có** | Xóa nội dung nguồn trong khi terminal đang tiêu thụ |
| `map(s -> { source.set(0, "X"); return s; })` | **Có** | Ghi vào cấu trúc nguồn, dù kích thước không đổi |
| `map(s -> { externalCounter++; return s; })` | Chưa chắc can thiệp nguồn, nhưng **có stateful side effect** | Vi phạm kỳ vọng stateless/thread-safe nếu dựa vào counter |

Cần phân biệt hai nguyên tắc có liên quan nhưng **không giống nhau**:

1. **Non-interference:** không sửa **nguồn** của Stream khi pipeline đang được duyệt.
2. **Stateless behavioral parameters:** hành vi của callback không dựa vào trạng thái có thể thay đổi trong khi thực thi pipeline (đặc biệt trạng thái bị các callback khác cập nhật).

Một lambda ghi log mà không sửa nguồn có thể không vi phạm non-interference, nhưng side effect vẫn có các rủi ro khác về thứ tự, số lần thực thi, tối ưu hóa và thread-safety. Ngược lại, lambda xóa phần tử trong nguồn vi phạm non-interference ngay cả khi chạy tuần tự và không có nhiều thread.

Nguyên tắc áp dụng cho các callback của cả thao tác trung gian và thao tác kết thúc. Việc `forEach` là terminal không tự cho phép nó chỉnh sửa nguồn đang traversal.

## 3. Nguồn của Stream là gì và khi nào nó được đọc?

Nguồn có thể là:

- `Collection`, ví dụ `ArrayList`, `HashSet`, `TreeSet`.
- Mảng đối tượng hoặc mảng nguyên thủy thông qua `Arrays.stream`.
- Dãy sinh ra bằng `IntStream.range`, `Stream.iterate`, `Stream.generate`.
- Một `Spliterator` hoặc nguồn I/O được chuyển thành Stream theo API tương ứng.

Ở các Stream dựa trên collection hoặc mảng, việc gọi `stream()` thường mới **thiết lập mô tả nguồn**, còn traversal thực sự diễn ra khi terminal operation yêu cầu kết quả.

~~~java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

Stream<Integer> pipeline = source.stream()
        .map(n -> n * 10);

// Chưa có terminal ở đây.
List<Integer> result = pipeline.toList();
System.out.println(result); // [10, 20, 30]
~~~

Điều này dẫn đến một phân biệt quan trọng:

- **Thay đổi nguồn trước khi pipeline bắt đầu thực thi:** một số nguồn có tính *late-binding* nên có thể phản ánh thay đổi ấy. Nhưng phải hiểu contract của nguồn/Spliterator và không coi mọi trường hợp giống nhau.
- **Thay đổi nguồn trong lúc pipeline đang thực thi:** với nguồn không concurrent, đây là tình huống bị cấm theo yêu cầu non-interference.

Không nên dùng phép đo “sau `stream()` nhưng trước `toList()`” như một kỹ thuật bắt buộc để thay đổi nguồn; hãy **hoàn tất biến đổi dữ liệu trước**, sau đó tạo và tiêu thụ pipeline. Cách này dễ đọc, an toàn hơn và không phụ thuộc chi tiết late-binding của từng nguồn.

## 4. Sai lầm điển hình: sửa `ArrayList` trong `forEach`

Ví dụ phản diện:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Không làm:
// numbers.stream().forEach(n -> {
//     if (n % 2 == 0) {
//         numbers.remove(n);
//     }
// });
~~~

Dễ nhầm rằng vì chỉ có một thread nên không thể có lỗi “concurrent”. Nhưng `ConcurrentModificationException` không chỉ xuất hiện khi có đa luồng: một Iterator hoặc Spliterator **fail-fast** có thể phát hiện chính thread đang duyệt đã sửa cấu trúc collection ngoài cơ chế được phép.

**Cũng không có bảo đảm rằng lỗi luôn bị phát hiện.** Fail-fast là cơ chế phát hiện trên cơ sở best effort, không phải cơ chế kiểm chứng tính đúng của code. Một pipeline sai có thể không ném exception trong một lần chạy nhưng vẫn vi phạm hợp đồng.

### 4.1. Cách đúng khi chỉ cần lọc: tạo collection kết quả

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4);

List<Integer> odds = numbers.stream()
        .filter(n -> n % 2 != 0)
        .toList();

System.out.println(numbers); // [1, 2, 3, 4]
System.out.println(odds);    // [1, 3]
~~~

`filter` chỉ xác định phần tử đầu ra, không thay đổi nguồn. Trong Java 17, `Stream.toList()` trả một List **unmodifiable**; nếu cần chỉnh sửa kết quả, hãy tạo một `ArrayList` từ nó:

~~~java
List<Integer> mutableOdds = new ArrayList<>(
        numbers.stream()
                .filter(n -> n % 2 != 0)
                .toList());

mutableOdds.add(5); // Hợp lệ: sửa collection kết quả mới.
~~~

### 4.2. Cách đúng khi cần thay đổi collection gốc: thao tác bên ngoài Stream

Nếu mục đích thực sự là xóa số chẵn khỏi một danh sách mutable, dùng `removeIf` **ngoài một lượt duyệt Stream đang hoạt động**:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

numbers.removeIf(n -> n % 2 == 0);

System.out.println(numbers); // [1, 3]
~~~

`removeIf` được thiết kế để xử lý việc loại bỏ phần tử của collection theo predicate. Không đặt `removeIf` trên cùng collection bên trong một callback của `source.stream()`.

Tương tự, `List.replaceAll` và `List.sort` là các API thích hợp khi **muốn biến đổi trực tiếp List**; hãy gọi chúng ở một giai đoạn riêng, không chạy chồng lên Stream đang duyệt danh sách đó.

## 5. Thay đổi kích thước không phải dạng can thiệp duy nhất

Nhiều người chỉ lo `add`/`remove` làm thay đổi `size()`, nhưng **ghi đè phần tử hiện có** trong nguồn cũng không phải cách xây dựng Stream đúng:

~~~java
List<String> data = new ArrayList<>(List.of("A", "B", "C"));

// SAI: vẫn sửa nguồn dù kích thước giữ nguyên.
// data.stream().map(s -> {
//     data.set(0, "X");
//     return s;
// }).toList();
~~~

Một collection có thể không coi `set` là *structural modification* nên cơ chế fail-fast không báo lỗi, nhưng điều đó **không biến việc sửa nguồn trong callback thành hợp lệ**. Predicate/mapper có thể đọc giá trị đã bị thay đổi theo cách không được bảo đảm hoặc gây kết quả khó dự đoán.

Đối với mảng:

~~~java
String[] array = {"A", "B", "C"};

// Cũng tránh:
// Arrays.stream(array).map(s -> {
//     array[1] = "changed";
//     return s;
// }).toList();
~~~

Mảng không có `modCount` hay fail-fast giống `ArrayList`, nhưng việc vừa duyệt vừa chỉnh sửa mảng nguồn vẫn là interference. Không ném `ConcurrentModificationException` **không** chứng minh an toàn.

Nếu muốn biến đổi giá trị, để mapper tạo giá trị đầu ra:

~~~java
String[] array = {"A", "B", "C"};

List<String> lower = Arrays.stream(array)
        .map(s -> s.toLowerCase(Locale.ROOT))
        .toList();

System.out.println(Arrays.toString(array)); // [A, B, C]
System.out.println(lower);                   // [a, b, c]
~~~

## 6. Sửa trạng thái đối tượng phần tử: phân biệt hai tầng dữ liệu

Giả sử nguồn là `List<User>`, mỗi `User` là một đối tượng mutable:

~~~java
class User {
    String name;
    User(String name) { this.name = name; }
}

List<User> users = new ArrayList<>(List.of(
        new User("An"), new User("Binh")));
~~~

Thao tác `users.remove(...)` hoặc `users.add(...)` thay đổi cấu trúc List nguồn. Còn `user.name = ...` thay đổi **trạng thái của đối tượng phần tử**, không nhất thiết thay đổi cấu trúc List.

Tuy nhiên, điều đó **không có nghĩa mutation bên trong mapper luôn là thiết kế an toàn**:

~~~java
// Không khuyến khích dùng Stream để thay đổi User:
// users.stream().forEach(user -> user.name = user.name.toUpperCase());
~~~

Tùy cách dùng dữ liệu, sửa trạng thái các phần tử có thể ảnh hưởng đến những callback khác, tới tiêu chí lọc/sắp xếp, hoặc dữ liệu ở thread khác. Nó làm hành vi khó suy luận, nhất là với parallel stream. Trong trường hợp phần tử cũng là một phần của nguồn hoặc cấu trúc phân loại (ví dụ sửa trường được dùng làm khóa của `HashSet`), mutation có thể phá invariant của collection ngay cả khi không gọi `add`/`remove`.

**Thiết kế dễ kiểm chứng hơn:** biến đổi sang đối tượng mới hoặc DTO bất biến:

~~~java
record UserView(String name) {}

List<UserView> views = users.stream()
        .map(user -> new UserView(
                user.name.toUpperCase(Locale.ROOT)))
        .toList();
~~~

Giá trị mới được tạo mà không sửa `User` ban đầu. Với dữ liệu có quan hệ phức tạp, cần phân biệt shallow copy và deep copy; tạo một List mới không tự sao chép sâu tất cả object bên trong.

## 7. Snapshot trước khi duyệt và giới hạn của bản sao

Nếu một collection có thể được sửa giữa các giai đoạn của ứng dụng và bạn muốn xử lý một phiên bản cố định, có thể tạo **snapshot trước khi bắt đầu Stream**:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> snapshot = new ArrayList<>(source);
source.set(0, "X");

List<String> upper = snapshot.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(upper); // [A, B]
System.out.println(source); // [X, B]
~~~

Ở đây `snapshot` chứa các phần tử như tại thời điểm sao chép; việc thay một vị trí trong `source` sau đó không ảnh hưởng danh sách snapshot. Nhưng có hai giới hạn:

1. `new ArrayList<>(source)` tạo bản sao **nông** (*shallow copy*). Nếu phần tử là object mutable, snapshot có thể vẫn tham chiếu cùng object, nên thay đổi trạng thái bên trong object đó sẽ được quan sát qua cả hai List.
2. Nếu thread khác đang sửa một `ArrayList` trong lúc snapshot được tạo, thao tác copy tự nó **không mặc nhiên tạo một snapshot nhất quán theo đồng bộ hóa**. Cần phối hợp đồng bộ hoặc chọn một thiết kế nguồn dữ liệu phù hợp.

`List.copyOf(source)` tạo List unmodifiable và từ chối phần tử `null`, nhưng vẫn không phải deep copy. Lựa chọn `copyOf`, `new ArrayList<>(...)` hoặc mô hình immutable phải căn cứ vào hợp đồng dữ liệu, nhất là null và sự thay đổi của phần tử.

### 7.1. Bản sao và kết quả Stream không phải cùng khái niệm

~~~java
List<String> source = new ArrayList<>(List.of(" a ", " b "));

List<String> result = source.stream()
        .map(String::trim)
        .toList();
~~~

`result` là List được tạo bằng terminal, không phải List nguồn đang được sửa tại chỗ. Nó chứa kết quả mapper, còn `source` giữ nguyên các chuỗi có khoảng trắng. `Stream.toList()` tạo List unmodifiable; điều đó **không có nghĩa** phần tử của List đã được deep-copy.

## 8. Parallel Stream: thêm các vấn đề về trạng thái chia sẻ

Khi gọi `parallel()` hoặc `parallelStream()`, các callback có thể được thực thi trên nhiều thread. Nếu sửa nguồn trong callback, bạn vừa vi phạm non-interference vừa có thể tạo **data race** hoặc làm sai cấu trúc dữ liệu.

~~~java
List<Integer> source = new ArrayList<>(
        IntStream.rangeClosed(1, 1_000).boxed().toList());

// TUYỆT ĐỐI KHÔNG DÙNG CÁCH NÀY:
// source.parallelStream().forEach(n -> source.remove(n));
~~~

Ngay cả sửa một **collection khác** từ callback cũng có thể gây lỗi khi collection đó không thread-safe:

~~~java
List<Integer> shared = new ArrayList<>();

// Sai với parallel stream vì ArrayList không an toàn cho add đồng thời:
// IntStream.range(0, 1_000).parallel().forEach(shared::add);
~~~

Ví dụ thứ hai không nhất thiết sửa **nguồn** của Stream (nguồn là dãy số từ `IntStream.range`), nhưng là **side effect dùng trạng thái chia sẻ** và có thể làm mất phần tử, gây race hoặc hỏng kết quả. Vì thế phải phân biệt:

- **Non-interference:** không sửa nguồn.
- **Statelessness / side-effect safety:** callback không phụ thuộc hoặc cập nhật trạng thái mutable chia sẻ không được đồng bộ.

Cách phù hợp hơn khi muốn thu thập số từ parallel stream:

~~~java
List<Integer> values = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(values.size()); // 1000
~~~

Collector hoặc terminal được Stream API thiết kế để thu thập kết quả sẽ quản lý việc chia và hợp nhất dữ liệu theo hợp đồng của nó. Với nguồn có encounter order như `IntStream.range`, kết quả `toList` giữ thứ tự encounter order dù các phép xử lý có thể chạy song song.

Không nên kết luận “có `synchronizedList` thì sửa nguồn trong Stream được phép”. Đồng bộ hóa một List không biến các mutation xảy ra trong callback thành non-interfering với nguồn đang được traversal.

## 9. Ngoại lệ: nguồn được thiết kế cho truy cập/sửa đồng thời

Java Stream documentation thừa nhận một ngoại lệ có điều kiện: nguồn có Spliterator mang đặc tính **`CONCURRENT`** được thiết kế để hỗ trợ việc sửa đồng thời khi duyệt. Ví dụ điển hình là các collection concurrent phù hợp, như dữ liệu lấy từ `ConcurrentHashMap`.

~~~java
ConcurrentHashMap<String, Integer> scores =
        new ConcurrentHashMap<>();
scores.put("A", 1);
scores.put("B", 2);

List<String> keys = scores.keySet().stream()
        .sorted()
        .toList();

System.out.println(keys); // [A, B]
~~~

Trong ví dụ trên không có mutation đồng thời: `sorted` được dùng để tạo đầu ra ổn định. Mục đích là nhận diện loại nguồn. Với những collection hỗ trợ duyệt concurrent, một iterator/spliterator có thể **weakly consistent**: nó không nhất thiết ném `ConcurrentModificationException` và không hứa snapshot đầy đủ, bất biến của thời điểm duyệt.

**Không suy ra rằng mọi loại Map hoặc mọi loại Stream đều chấp nhận mutation concurrent.** Cần đọc hợp đồng của collection/spliterator cụ thể: một số nguồn có đặc tính `IMMUTABLE`, một số có `CONCURRENT`, một số có cơ chế fail-fast; mỗi loại có semantics khác.

Nếu yêu cầu kết quả thống kê **nhất quán tại một thời điểm**, chỉ sử dụng collection concurrent không đủ; cần snapshot, locking hoặc thiết kế nhất quán phù hợp. Việc một nguồn cho phép vừa sửa vừa duyệt không có nghĩa phép toán tổng hợp sẽ quan sát chính xác một ảnh chụp tức thời.

### 9.1. `CopyOnWriteArrayList` khác `ConcurrentHashMap`

`CopyOnWriteArrayList` tạo cơ chế sao chép mảng khi có mutation, còn quá trình duyệt có thể dựa trên snapshot của mảng. Nó không có cùng hợp đồng quan sát với `ConcurrentHashMap`. Vì vậy, kể cả đều được thiết kế cho những mô hình sử dụng nhiều thread, **không được gộp chúng thành một quy tắc “concurrent nghĩa là nhìn thấy mọi thay đổi tức thời”**.

Bài học cốt lõi vẫn là: khi muốn viết Stream pipeline tổng quát, hãy **giữ source ổn định trong lúc duyệt** trừ khi một thiết kế concurrent có mục đích thực sự yêu cầu khác và bạn nắm rõ contract của nguồn.

## 10. Side effects, `peek`, `map` và tối ưu hóa pipeline

Một lambda có thể không sửa nguồn nhưng vẫn có hiệu ứng phụ:

~~~java
AtomicInteger counter = new AtomicInteger();

long count = List.of("a", "b", "c").stream()
        .map(s -> {
            counter.incrementAndGet();
            return s.toUpperCase(Locale.ROOT);
        })
        .count();
~~~

Đừng kỳ vọng `counter.get() == 3`. Khi nguồn có kích thước đã biết và `map` không thay đổi số phần tử, một số implementation có thể tính `count()` mà **không cần thực thi mapper**. Đây là tối ưu hóa hợp lệ theo hợp đồng Stream. Vì vậy, đặt side effect cần chắc chắn diễn ra trong `map` hoặc `peek` là cách thiết kế sai.

`peek` thường được dùng để quan sát/debug:

~~~java
List<String> result = List.of(" a ", " b ").stream()
        .peek(s -> System.out.println("raw=" + s))
        .map(String::trim)
        .toList();
~~~

Trong ví dụ này, `toList` cần các giá trị nên có thể quan sát log khi traversal, nhưng không nên dựa vào số lần hoặc thứ tự `peek` trong mọi pipeline, đặc biệt khi có short-circuit, parallel hoặc tối ưu hóa terminal.

Lời khuyên:

- Dùng `map` để **tạo giá trị mới**.
- Dùng `filter` để **giữ/bỏ phần tử trong kết quả**, không phải để sửa collection nguồn.
- Dùng `collect`, `toList` hoặc một terminal phù hợp để **tạo kết quả**.
- Nếu thực sự cần một hành động side effect được thực thi như mục tiêu chính, dùng terminal như `forEach`/`forEachOrdered` trên nguồn **không bị sửa**, cùng với đánh giá thread-safety của hành động. `forEachOrdered` liên quan thứ tự encounter, không tự làm các thao tác mutation ngoài source trở thành an toàn với mọi thread.
- Không đặt correctness của nghiệp vụ lên những log/counter/tác động phụ trong intermediate operation.

## 11. Các trường hợp thường gây nhầm về thứ tự sửa dữ liệu

| Tình huống | Đánh giá |
| --- | --- |
| Gọi `list.removeIf(p)` trước khi tạo stream | Cách hợp lý nếu muốn sửa List gốc và chưa có traversal đồng thời |
| Gọi `list.sort(c)` rồi sau đó `list.stream()` | Hợp lý, thao tác sửa dữ liệu hoàn tất trước khi duyệt |
| Gọi `list.replaceAll(f)` sau khi một terminal đã hoàn tất | Hợp lý nếu không còn traversal đồng thời khác |
| Gọi `list.add(x)` ngay trong `list.stream().forEach(...)` | Vi phạm non-interference |
| Gọi `list.clear()` trong `list.stream().map(...)` | Vi phạm non-interference |
| Gọi `list.set(i,x)` từ callback đang duyệt cùng List | Vi phạm non-interference, kể cả khi không tăng `modCount` |
| Gọi `array[i] = x` từ callback duyệt chính mảng | Vi phạm non-interference |
| Gọi `otherList.add(x)` từ parallel Stream | Không nhất thiết sửa source, nhưng có rủi ro dữ liệu chia sẻ; nên dùng collector |
| Tạo `new ArrayList<>(list)` rồi duyệt bản sao | Thường phù hợp nếu copy được tạo nhất quán trước traversal |
| Duyệt một nguồn có spliterator `CONCURRENT` theo contract | Có thể hỗ trợ mutation đồng thời; semantics phải theo nguồn cụ thể |

**Đừng diễn giải bảng thành “List không được thay đổi trong toàn bộ vòng đời chương trình”.** Collection mutable có thể được cập nhật bình thường **trước hoặc sau** lần traversal. Giới hạn quan trọng là **không thay đổi nguồn trong lúc pipeline đang sử dụng nguồn ấy**.

## 12. Chương trình Java 17+ hoàn chỉnh và stdout xác định

Tạo tệp **`StreamNonInterferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class StreamNonInterferenceDemo {
    record Person(String name, int age) {}
    record PersonView(String name, boolean adult) {}

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of(" an ", " ", " binh ", "chi "));

        List<String> normalized = source.stream()
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();

        System.out.println("source=" + source);
        System.out.println("normalized=" + normalized);

        List<Integer> numbers = List.of(1, 2, 3, 4);
        List<Integer> odd = numbers.stream()
                .filter(n -> n % 2 != 0)
                .toList();
        System.out.println("originalNumbers=" + numbers);
        System.out.println("odd=" + odd);

        List<Integer> mutable = new ArrayList<>(numbers);
        mutable.removeIf(n -> n % 2 == 0);
        System.out.println("removedOutsideStream=" + mutable);

        List<String> snapshot = new ArrayList<>(source);
        source.set(0, "changed");
        List<String> saved = snapshot.stream()
                .map(String::trim)
                .toList();
        System.out.println("snapshot=" + saved);
        System.out.println("modifiedSourceFirst=" + source.get(0));

        List<Person> people = List.of(
                new Person("An", 20),
                new Person("Binh", 17));
        List<PersonView> views = people.stream()
                .map(p -> new PersonView(
                        p.name().toUpperCase(Locale.ROOT),
                        p.age() >= 18))
                .toList();
        System.out.println("views=" + views);

        long parallelSum = IntStream.rangeClosed(1, 100)
                .parallel()
                .mapToLong(n -> n)
                .sum();
        System.out.println("parallelSum=" + parallelSum);

        List<Integer> generated = IntStream.range(0, 5)
                .parallel()
                .boxed()
                .toList();
        System.out.println("parallelList=" + generated);

        String[] letters = {"A", "B", "C"};
        List<String> lower = Arrays.stream(letters)
                .map(s -> s.toLowerCase(Locale.ROOT))
                .toList();
        System.out.println("arraySource=" + Arrays.toString(letters));
        System.out.println("arrayResult=" + lower);

        ConcurrentHashMap<String, Integer> scores =
                new ConcurrentHashMap<>();
        scores.put("B", 2);
        scores.put("A", 1);
        System.out.println("concurrentKeys=" + scores.keySet().stream()
                .sorted()
                .toList());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac StreamNonInterferenceDemo.java
java StreamNonInterferenceDemo
~~~

Stdout:

~~~text
source=[ an ,  ,  binh , chi ]
normalized=[AN, BINH, CHI]
originalNumbers=[1, 2, 3, 4]
odd=[1, 3]
removedOutsideStream=[1, 3]
snapshot=[an, , binh, chi]
modifiedSourceFirst=changed
views=[PersonView[name=AN, adult=true], PersonView[name=BINH, adult=false]]
parallelSum=5050
parallelList=[0, 1, 2, 3, 4]
arraySource=[A, B, C]
arrayResult=[a, b, c]
concurrentKeys=[A, B]
~~~

Giải thích các phần:

1. Pipeline `map`/`filter` tạo `normalized` nhưng không sửa `source`; dấu cách của các chuỗi nguồn vẫn còn.
2. `odd` là danh sách mới chứa phần tử được giữ, còn `numbers` không đổi.
3. `removeIf` thay đổi `mutable` trong một thao tác độc lập, **không** xảy ra bên trong traversal của cùng collection.
4. Snapshot được tạo trước khi `source.set`, nên `saved` vẫn dựa trên dữ liệu cũ; thay source sau khi copy không làm thay đổi List snapshot (với `String` bất biến).
5. `map` tạo `PersonView` mới thay vì đổi dữ liệu nguồn.
6. Parallel stream thực hiện phép cộng kết hợp vào terminal `sum` thay vì ghi vào bộ đếm mutable chia sẻ.
7. `parallel().boxed().toList()` giữ encounter order của `IntStream.range` trong kết quả.
8. Biến đổi từ mảng tạo List mới, không viết vào `letters`.
9. `ConcurrentHashMap` được minh họa như một loại nguồn có semantics concurrent riêng; ở đây không sửa trong lúc traversal. `sorted` bảo đảm thứ tự output khi in key.

Chương trình **không cố ý thực thi** những đoạn sai có thể ném `ConcurrentModificationException` hoặc gây race. Thay vào đó, ví dụ cho thấy hành vi đúng và đầu ra có thể so sánh trực tiếp.

## 13. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Sửa `ArrayList` trong `stream().forEach` | Vi phạm non-interference, có thể ném CME | Dùng `removeIf` ngoài traversal hoặc tạo collection kết quả |
| Sửa phần tử bằng `set` trong `map` | Sửa nguồn dù kích thước không đổi | Trả giá trị mới bằng `map` |
| Sửa phần tử mảng trong khi `Arrays.stream` duyệt | Nguồn mảng bị thay đổi | Biến đổi sang List/mảng kết quả mới |
| Dựa vào `ConcurrentModificationException` để phát hiện mọi lỗi | Fail-fast best effort, không phải bảo đảm | Thiết kế non-interfering |
| Cho rằng stream tuần tự an toàn khi sửa nguồn | Một thread vẫn có thể gây interference | Không sửa nguồn trong callback |
| Cho rằng `Collections.synchronizedList` cho phép thay nguồn khi duyệt | Đồng bộ một API không thay hợp đồng Stream | Tách mutation và traversal hoặc thiết kế đồng bộ riêng |
| `parallelStream().forEach(sharedArrayList::add)` | Side effect trên List không thread-safe | `collect`/`toList` |
| Tưởng `peek` luôn chạy trên mọi phần tử | Lazy/short-circuit/tối ưu hóa | Không dùng peek cho side effect bắt buộc |
| Tưởng nguồn concurrent có snapshot tức thì | Nhiều nguồn concurrent có weak consistency | Đọc contract, snapshot/locking nếu cần nhất quán |
| Tưởng `new ArrayList<>(source)` deep-copy objects | Chỉ tạo shallow copy | Tạo object mới/defensive copy nếu cần |
| Sửa trường dùng làm hash key của phần tử trong Set | Phá invariant tìm kiếm của Set | Dùng đối tượng khóa bất biến, tạo cấu trúc mới |
| Tái sử dụng Stream sau terminal | Stream chỉ tiêu thụ một lần | Tạo stream mới khi cần xử lý tiếp |

## 14. Bài tập tự kiểm tra

**Câu 1.** Vì sao cách sau không hợp lệ về mặt thiết kế Stream?

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
values.stream().forEach(v -> values.add(v * 10));
~~~

**Đáp án:** Callback thêm vào chính nguồn `values` trong lúc terminal đang duyệt nó. Đây là interference; có thể xảy ra lỗi hoặc kết quả không được bảo đảm. Nếu muốn danh sách giá trị gấp 10, dùng `values.stream().map(v -> v * 10).toList()`.

**Câu 2.** Nếu `List.set` không tăng `modCount`, có thể gọi nó trong `map` trên chính danh sách không?

**Đáp án:** Không. Không ném `ConcurrentModificationException` không chứng minh việc sửa nguồn là hợp lệ. Non-interference không chỉ kiểm tra thay đổi cấu trúc làm đổi `size()`.

**Câu 3.** `IntStream.range(0,1000).parallel().forEach(sharedList::add)` có sửa nguồn Stream không?

**Đáp án:** Nguồn là dãy số do `IntStream.range` tạo, nên không nhất thiết sửa nguồn. Nhưng nó cập nhật một List chia sẻ từ nhiều thread, vi phạm yêu cầu an toàn trạng thái nếu List không được bảo vệ. Dùng `boxed().toList()` hoặc collector phù hợp.

**Câu 4.** Khi cần loại bỏ số âm khỏi `ArrayList` gốc, API nào nên dùng ngoài Stream?

**Đáp án:** `list.removeIf(n -> n < 0)`, thực hiện khi không có traversal đồng thời của List đó.

**Câu 5.** Có thể sửa `ConcurrentHashMap` khi duyệt key stream không?

**Đáp án:** Một số nguồn từ concurrent collection có hợp đồng hỗ trợ sửa đồng thời và Spliterator thích hợp, nhưng kết quả thường không phải snapshot cố định. Phải đọc contract cụ thể; không áp dụng kết luận đó cho `ArrayList`/mảng hoặc yêu cầu nhất quán tuyệt đối.

**Câu 6.** Copy `List<User>` sang `new ArrayList<>(users)` có tách hoàn toàn dữ liệu User không?

**Đáp án:** Không. Đây là shallow copy. Nếu `User` mutable, hai danh sách vẫn có thể cùng tham chiếu đến các đối tượng User. Muốn tách trạng thái phải copy từng object theo thiết kế domain.

**Câu 7.** Vì sao tăng counter trong `stream.map(...)` rồi gọi `count()` không phải cách đếm đáng tin?

**Đáp án:** Intermediate operations là lazy và Stream có thể tối ưu hóa: với nguồn có kích thước đã biết và mapper không đổi số phần tử, `count()` có thể trả kết quả mà không gọi mapper. Counter side effect không phải sản phẩm có hợp đồng bảo đảm của pipeline.

## 15. Ghi nhớ

**Non-interference là yêu cầu cơ bản của Stream:** hành vi được truyền vào pipeline phải **không sửa nguồn dữ liệu đang được duyệt**, trừ những nguồn có hợp đồng concurrent rõ ràng. Với collection hoặc mảng thông thường, việc sửa nguồn trong `filter`, `map`, `peek`, `forEach` hoặc callback khác đều không nên làm.

- Dùng `filter` và `map` để tạo dữ liệu kết quả mới, không chỉnh sửa collection nguồn.
- Nếu cần sửa collection gốc, thực hiện mutation trước hoặc sau traversal bằng API thích hợp như `removeIf`, `replaceAll` hoặc `sort`.
- Không dựa vào `ConcurrentModificationException` như một cơ chế bảo đảm phát hiện sai: fail-fast thường chỉ là best effort.
- Phân biệt **sửa nguồn** với **side effect trên trạng thái chia sẻ**. Cả hai đều gây vấn đề, đặc biệt trong parallel streams, nhưng lý do và cách xử lý không hoàn toàn giống nhau.
- Snapshot trước traversal có thể hữu ích, nhưng thường chỉ shallow copy và cần đồng bộ khi sao chép nguồn đang bị thread khác sửa.
- Concurrent collections có semantics riêng; có thể hỗ trợ duyệt khi sửa nhưng không đồng nghĩa với snapshot nhất quán.
- Ưu tiên callback stateless, không can thiệp và ít side effect để pipeline đúng, dễ hiểu và có thể tối ưu hoặc chạy song song an toàn hơn.

Mục tiêu không phải “không bao giờ được sửa List”, mà là **tách rõ pha sửa dữ liệu và pha duyệt bằng Stream**, giữ sự ổn định của nguồn trong mỗi lần traversal.
