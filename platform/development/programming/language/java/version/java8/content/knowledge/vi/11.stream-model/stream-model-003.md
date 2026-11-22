# Thực thi lười và thời điểm bắt đầu duyệt trong Java Stream

## 1. Hiểu đúng tính lazy của Stream

Một trong những đặc điểm quan trọng nhất của **Java Stream API** là **thực thi lười** (*lazy evaluation*): việc gọi các **intermediate operations** như `filter()`, `map()`, `flatMap()` hoặc `sorted()` mới chỉ **thiết lập một pipeline**. Chúng chưa yêu cầu xử lý lần lượt các phần tử của nguồn ngay tại thời điểm khai báo.

Hầu hết việc duyệt nguồn bắt đầu khi chương trình gọi một **terminal operation** như `collect()`, `forEach()`, `reduce()`, `sum()`, `findFirst()` hoặc `anyMatch()`. Đến lúc này, Stream có thể kết hợp các thao tác, xử lý mỗi phần tử qua nhiều stage, dừng sớm và thậm chí bỏ qua một số stage khi kết quả không thay đổi.

Ví dụ:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi");

Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase);

// Đến đây chưa cần chạy filter hoặc map trên phần tử nào.

List<String> result = pipeline
        .collect(Collectors.toList());

// Lúc collect, pipeline được thực thi để tạo kết quả.
```

Đoạn này cần các import `java.util.*` và `java.util.stream.*`. Với nguồn dữ liệu đã cho, `result` là `["BINH", "CHI"]`. Ví dụ không cần hai vòng lặp riêng để tạo một danh sách đã lọc rồi một danh sách đã viết hoa; Stream có thể kết hợp các stage theo kiểu xử lý tuần tự qua từng phần tử.

**Phân biệt hai thời điểm:**

1. **Xây pipeline:** tạo nguồn Stream và nối các intermediate operations. Java có thể đánh giá các biểu thức đối số, kiểm tra tham số và thiết lập metadata tại đây, nhưng các hàm `filter`/`map` chưa phải duyệt phần tử.
2. **Yêu cầu kết quả:** gọi terminal operation, khiến Stream thực hiện những thao tác cần thiết để cho kết quả. **Không đồng nghĩa terminal luôn duyệt hết mọi phần tử**, vì có short-circuit và tối ưu hóa.

Quy tắc này vẫn được mô tả trong Java SE hiện hành, không phải hành vi chỉ có ở Java 8.

## 2. Cấu trúc một Stream pipeline

Một Stream pipeline thường gồm ba thành phần:

```text
SOURCE
  List / array / generator / file / Spliterator
     |
     v
INTERMEDIATE OPERATIONS
  filter -> map -> distinct -> limit -> ...
     |
     v
TERMINAL OPERATION
  collect / reduce / count / sum / findFirst / ...
     |
     v
RESULT hoặc hiệu ứng đã yêu cầu
```

### 2.1. Source: nơi dữ liệu đến từ đâu?

Nguồn Stream có thể là:

- Collection: `list.stream()`, `set.stream()`.
- Array: `Arrays.stream(array)`.
- Dãy số: `IntStream.range(0, n)`.
- Tập phần tử định sẵn: `Stream.of("a", "b")`.
- Generator: `Stream.generate(supplier)`, `Stream.iterate(seed, next)`.
- I/O: `Files.lines(path)` hoặc những stream khác gắn với tài nguyên.

**Nguồn Stream không nhất thiết đã nằm hoàn toàn trong bộ nhớ.** Một Stream có thể duyệt khi cần hoặc biểu diễn dãy phần tử không hữu hạn. Bởi vậy, chính sách lazy/short-circuit có giá trị đặc biệt đối với nguồn lớn hoặc vô hạn.

Tuy nhiên, **lazy traversal không có nghĩa mọi tác vụ tạo nguồn đều bị trì hoãn**. Ví dụ `Files.lines(path)` có thể mở tài nguyên I/O ngay lúc gọi factory; nó không chờ terminal operation mới mở file. Ngoài ra, các đối số của `Stream.of(...)` được Java đánh giá trước khi phương thức factory được gọi.

### 2.2. Intermediate: mô tả phép biến đổi, chưa xuất kết quả cuối

Một intermediate operation nhận Stream và trả một Stream để ghép tiếp:

```java
Stream<String> filtered = names.stream()
        .filter(s -> s.length() > 2);

Stream<Integer> lengths = filtered.map(String::length);
```

Các thao tác `filter` và `map` ở đây đều **lazy**: chưa thực hiện hàm predicate/mapper cho các phần tử nguồn. Việc tạo các biến `filtered`, `lengths` cũng không cho phép bạn duyệt cùng một Stream nhiều lần; mỗi pipeline là cơ chế tiêu thụ một lần.

Các intermediate operations quan trọng:

| Operation | Vai trò | Nhóm chính |
| --- | --- | --- |
| `filter(predicate)` | Giữ những phần tử đạt điều kiện | Stateless, lazy |
| `map(mapper)` | Biến đổi mỗi phần tử | Stateless, lazy |
| `mapToInt(mapper)` | Biến đổi sang primitive stream | Stateless, lazy |
| `flatMap(mapper)` | Mở rộng mỗi phần tử thành một stream con rồi làm phẳng | Lazy, dạng nội dung có thể thay đổi số phần tử |
| `peek(action)` | Gắn một hành động quan sát phần tử | Stateless, lazy; lưu ý optimization |
| `distinct()` | Loại phần tử trùng lặp theo `equals` | Stateful, lazy |
| `sorted()` | Tạo thứ tự sắp xếp | Stateful, lazy |
| `limit(n)` | Chỉ cho phép nhiều nhất `n` phần tử qua stage | Short-circuiting intermediate |
| `skip(n)` | Bỏ qua `n` phần tử đầu | Stateful intermediate theo quy định API |
| `takeWhile(predicate)` | Giữ prefix còn đạt điều kiện | Java 9+, short-circuiting intermediate |
| `dropWhile(predicate)` | Bỏ prefix đạt điều kiện đầu tiên | Java 9+, stateful intermediate |

**Phiên bản:** các ví dụ chạy độc lập bên dưới dùng thao tác có từ Java 8. `takeWhile`/`dropWhile` chỉ được nhắc để định hướng Java 9+ và được gắn rõ yêu cầu source level.

### 2.3. Terminal: yêu cầu một kết quả hoặc hành động

Một terminal operation không trả một Stream để nối thêm nữa theo cùng pipeline, mà yêu cầu xử lý hoặc mở quyền duyệt:

| Terminal operation | Kiểu kết quả/vai trò | Có thể kết thúc sớm? |
| --- | --- | --- |
| `collect(collector)` | Gom về collection/summary | Thường cần toàn bộ đầu vào cần thiết |
| `toArray()` | Tạo mảng | Thường cần các phần tử kết quả |
| `reduce(...)` | Gộp các phần tử | Thường cần duyệt các phần tử liên quan |
| `count()` | Đếm phần tử | **Có thể tối ưu mà không duyệt** |
| `forEach(action)` | Thực hiện action trên các phần tử được duyệt | Không phải short-circuit terminal |
| `forEachOrdered(action)` | Action theo encounter order nếu có | Không phải short-circuit terminal |
| `findFirst()` | Lấy phần tử đầu theo encounter order nếu tồn tại | Có |
| `findAny()` | Lấy một phần tử bất kỳ | Có |
| `anyMatch(predicate)` | Có phần tử thỏa điều kiện hay không | Có |
| `allMatch(predicate)` | Mọi phần tử có thỏa không | Có |
| `noneMatch(predicate)` | Không phần tử nào thỏa hay không | Có |
| `min(comparator)` / `max(comparator)` | Giá trị cực trị | Thường cần xét đầu vào cần thiết |
| `iterator()` / `spliterator()` | Trao quyền duyệt cho client | **Ngoại lệ: terminal không eager** |

Các terminal operations thường là eager, theo nghĩa hoàn thành phép tính trước khi trả; hai **escape-hatch** `iterator()` và `spliterator()` là ngoại lệ quan trọng. Chúng trả công cụ duyệt cho code bên ngoài, khiến công việc với phần tử có thể diễn ra khi client sử dụng iterator/spliterator sau đó.

## 3. Ví dụ có thể kiểm chứng: chưa có terminal thì chưa chạy lambda xử lý phần tử

Đoạn mã dưới đây có log trong `filter` và `map` để minh họa sự khác biệt giữa **xây pipeline** và **duyệt pipeline**:

```java
List<String> languages =
        Arrays.asList("java", "go", "kotlin", "js");

System.out.println("build");
Stream<String> pipeline = languages.stream()
        .filter(s -> {
            System.out.println("filter " + s);
            return s.length() > 2;
        })
        .map(s -> {
            System.out.println("map " + s);
            return s.toUpperCase(Locale.ROOT);
        });

System.out.println("before collect");
List<String> result =
        pipeline.collect(Collectors.toList());

System.out.println("result " + result);
```

Với **sequential Stream**, nguồn `List` có encounter order và phần tử chỉ lọc/đổi chuỗi theo đúng nội dung đã định, thứ tự quan sát ở ví dụ này là:

```text
build
before collect
filter java
map java
filter go
filter kotlin
map kotlin
filter js
result [JAVA, KOTLIN]
```

Chú ý:

- `"build"` và `"before collect"` xuất hiện trước mọi log từ `filter`/`map`.
- `filter java` được theo ngay bởi `map java`; pipeline không cần chạy hết `filter` cho tất cả phần tử rồi mới chạy `map` cho tất cả phần tử.
- `"go"` và `"js"` bị loại tại `filter` nên không được đưa sang `map`.
- `collect(Collectors.toList())` làm phát sinh kết quả `[JAVA, KOTLIN]`.

**Nhấn mạnh:** đặt `println` trong callback chỉ phù hợp để *quan sát một ví dụ có kiểm soát*. Không xây logic nghiệp vụ dựa trên việc mỗi callback của `map` hoặc `peek` bắt buộc sẽ được gọi — JDK có quyền loại bỏ stage nếu chứng minh không ảnh hưởng kết quả. Ở trường hợp trên, `filter` cần kiểm tra độ dài và `map` cần tạo chuỗi thực tế cho `collect`, nên đó là ví dụ dạy cơ chế duyệt dễ hiểu; câu chuyện tối ưu hóa ở mục 7 sẽ làm rõ giới hạn.

## 4. Khi terminal được gọi, Stream có luôn duyệt tất cả phần tử?

**Không.** “Terminal operation bắt đầu quá trình đánh giá” không đồng nghĩa “tất cả phần tử nguồn sẽ được thăm” hoặc “mọi callback trong pipeline sẽ được chạy”.

Có ba lý do quan trọng:

1. **Short-circuit:** có thể biết kết quả sau khi duyệt một prefix hoặc một phần nguồn.
2. **Stage stateful:** một số stage như `sorted` có thể cần đọc/buffer gần như toàn bộ nguồn trước khi xuất phần tử tiếp theo; vì vậy mức độ duyệt phụ thuộc thứ tự stage.
3. **Tối ưu hóa dựa vào metadata:** một số terminal như `count()` có thể trả kết quả nhờ kích thước nguồn đã biết mà không áp dụng từng callback.

Ngoài ra, nguồn có thể **rỗng**, nên một terminal như `anyMatch` trả `false` mà không gọi predicate lần nào. Không được suy ra số lần gọi callback chỉ từ tên terminal.

## 5. Short-circuit: dừng ngay khi có đủ thông tin

### 5.1. `limit(n)` cho phép kết thúc một nguồn dài

`limit(2)` là intermediate operation lazy nhưng có khả năng short-circuit. Nó chỉ cho phép tối đa hai phần tử đầu của stream **tại chính vị trí đặt `limit`**.

```java
List<Integer> odds = Stream.of(1, 2, 3, 4, 5, 6)
        .filter(n -> n % 2 != 0)
        .limit(2)
        .collect(Collectors.toList());

// odds = [1, 3]
```

Với nguồn sequential có encounter order, pipeline chỉ cần xem `1`, `2`, `3` để tìm được hai phần tử lẻ. Không phải xử lý `4`, `5`, `6`. Cơ chế này có thể giảm đáng kể thời gian và lượng dữ liệu cần đọc.

**Thứ tự stage rất quan trọng:**

```java
List<Integer> a = Stream.of(1, 2, 3, 4, 5)
        .filter(n -> n % 2 == 0)
        .limit(2)
        .collect(Collectors.toList());
// a = [2, 4]

List<Integer> b = Stream.of(1, 2, 3, 4, 5)
        .limit(2)
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());
// b = [2]
```

`a` giới hạn **hai số chẵn sau khi lọc**; `b` giới hạn **hai phần tử nguồn đầu tiên rồi mới lọc**. Đây là hai nghiệp vụ khác nhau, không thể tùy ý hoán đổi `filter` và `limit` để tối ưu.

### 5.2. `findFirst()` có thể không cần xem hết nguồn

```java
Optional<String> found = Stream.of(
        "go", "js", "java", "kotlin")
    .filter(s -> s.length() >= 4)
    .findFirst();

// found = Optional["java"] về mặt giá trị.
```

Trong source đã cho, `java` là phần tử đầu tiên đạt điều kiện, nên khi pipeline sequential không có stage buộc duyệt hết, chỉ cần xem đến nó. `findFirst()` trả `Optional<String>`; nếu không có phần tử phù hợp, trả `Optional.empty()`.

Không nên suy luận rằng `findFirst` chắc chắn chỉ đọc một phần tử. Nếu trước nó có `sorted()` hoặc một stage stateful cần toàn bộ nguồn, kết quả có thể đòi hỏi duyệt/buffer rất nhiều phần tử.

### 5.3. Các matcher thường kết thúc sớm

```java
boolean any = Stream.of(2, 4, 7, 9)
        .anyMatch(n -> n % 2 != 0); // true

boolean all = Stream.of(2, 4, 6, 7)
        .allMatch(n -> n % 2 == 0); // false

boolean none = Stream.of(2, 4, 7)
        .noneMatch(n -> n < 0); // true
```

- `anyMatch` có thể dừng khi gặp một phần tử **đúng**.
- `allMatch` có thể dừng khi gặp một phần tử **sai**.
- `noneMatch` có thể dừng khi gặp một phần tử **đúng**.

Với Stream rỗng:

| Biểu thức | Kết quả | Predicate được gọi? |
| --- | --- | --- |
| `Stream.empty().anyMatch(p)` | `false` | Không |
| `Stream.empty().allMatch(p)` | `true` | Không |
| `Stream.empty().noneMatch(p)` | `true` | Không |

Trong bảng, `p` đại diện một predicate hợp lệ; các dòng là biểu thức minh họa với kiểu generic phù hợp. Tính chất của `allMatch`/`noneMatch` trên tập rỗng tương ứng với khái niệm “đúng một cách hiển nhiên” (*vacuous truth*) của lượng từ logic.

### 5.4. `findAny()` không có cam kết chọn phần tử đầu

`findAny()` cho phép trả **một** phần tử bất kỳ, đặc biệt để tối ưu trên parallel streams. Đừng dùng nó thay cho `findFirst()` khi nghiệp vụ yêu cầu phần tử đầu theo encounter order.

Trong sequential stream của một implementation cụ thể, `findAny` có thể trùng với phần tử đầu, nhưng **không nên lập hợp đồng dựa vào điều đó**. Việc sắp thứ tự input không tự biến `findAny` thành một terminal có nghĩa “first”.

## 6. Stateless và stateful: đều lazy nhưng chi phí khác nhau

### 6.1. Stateless intermediate operations

`map`, `filter` và nhiều phép biến đổi khác có thể xử lý một phần tử mà không cần nhớ toàn bộ những phần tử đã qua. Với Stream tuần tự, các stage stateless thường được **fuse** thành một đường xử lý trên từng phần tử.

Ví dụ:

```java
long count = Stream.of("a", "abcd", "xy", "java")
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .count();
```

`filter` thay đổi số phần tử, vì vậy để tính đúng `count` trong trường hợp chung, Stream phải xác định phần tử nào qua bộ lọc. Nhưng phép biến đổi `map(String::toUpperCase)` **không thay đổi số lượng**, nên một implementation được phép bỏ việc tạo các chuỗi viết hoa nếu không ảnh hưởng kết quả `count`. Kết quả vẫn là `2`.

Điều này cho thấy **các thao tác không được cam kết chạy từng callback chỉ vì có terminal**.

### 6.2. Stateful intermediate operations

Các stage như `sorted()` và `distinct()` có thể cần thông tin từ nhiều phần tử.

```java
List<Integer> sorted = Stream.of(5, 2, 4, 1)
        .sorted()
        .collect(Collectors.toList());

// sorted = [1, 2, 4, 5]
```

Để sắp xếp đúng một nguồn hữu hạn, implementation nhìn chung cần biết các phần tử đầu vào trước khi có thể xuất phần tử đầu tiên sau sắp xếp. Vì vậy `sorted` **vẫn là một intermediate operation lazy**, nhưng khi pipeline thực sự được duyệt, nó có thể **buffer toàn bộ đầu vào**.

`distinct()` cần theo dõi những phần tử đã gặp để loại trùng. Mức độ bộ nhớ và chiến lược duyệt phụ thuộc nguồn, encounter order, parallel/sequential và các tối ưu hóa có thể áp dụng.

### 6.3. Không dùng `sorted()` vô điều kiện trên nguồn vô hạn

```java
Stream<Integer> infinite =
        Stream.iterate(0, n -> n + 1);

// Thiết kế nguy hiểm: cần xét vô hạn phần tử
// trước khi sorted có thể đưa ra kết quả đầu tiên.
// infinite.sorted().limit(5).collect(Collectors.toList());
```

Đây là đoạn minh họa cảnh báo, **không thực thi** dòng bị comment. Nguồn `iterate` ở ví dụ là vô hạn; một phép sắp xếp đầy đủ trước `limit` không thể chờ “đọc xong nguồn” trong thời gian hữu hạn.

Nếu nghiệp vụ chỉ cần năm phần tử đầu rồi sắp xếp chúng, thứ tự cần là:

```java
List<Integer> finite = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .sorted()
        .collect(Collectors.toList());

// finite = [0, 1, 2, 3, 4]
```

Việc đặt `limit` trước `sorted` không chỉ là tối ưu: nó **thay đổi phạm vi dữ liệu được sắp xếp**, và chỉ đúng nếu đáp ứng yêu cầu nghiệp vụ.

## 7. Trường hợp đặc biệt: `count()` có thể không duyệt nguồn

Oracle Javadoc của `Stream.count()` nêu rõ: implementation **được phép không thực thi pipeline** nếu tính được kết quả trực tiếp từ nguồn. Chẳng hạn, với `List` đã biết kích thước và intermediate operation chỉ thay đổi phần tử mà **không thêm hoặc bỏ phần tử**, số lượng phần tử có thể xác định mà không duyệt.

```java
List<String> values = Arrays.asList("A", "B", "C");

long count = values.stream()
        .peek(System.out::println)
        .count();

System.out.println("count=" + count);
```

**Không được dựa vào việc ba chữ `A`, `B`, `C` sẽ được in.** `peek` chỉ có side effect, còn `count` có thể được tính trực tiếp bằng kích thước 3; implementation hiện đại có thể bỏ hẳn `peek`. Phần in duy nhất mà chương trình được bảo đảm ở ví dụ là `count=3`.

Tương tự, với `map` không làm đổi số lượng, callback có thể không được gọi nếu kết quả cuối cùng chỉ cần đếm. Điều này là **hành vi hợp lệ theo hợp đồng Stream**, không phải bug.

### 7.1. Vì sao thêm `filter` làm tình huống khác?

`filter` có thể loại phần tử; số lượng sau lọc không thể luôn suy ra chỉ từ kích thước nguồn:

```java
long longNames = Arrays.asList("A", "AB", "ABC")
        .stream()
        .filter(s -> s.length() >= 2)
        .count(); // 2
```

Để trả kết quả đúng nói chung, Stream phải biết những phần tử đạt predicate; `count` không thể đơn giản dùng kích thước nguồn 3 như ở ví dụ `peek`.

Tuy nhiên, **vẫn không nên dùng side effect trong predicate như một hợp đồng đếm số lần gọi**. Các tối ưu hóa và hình thức thực thi là quyền của implementation, trong khi kết quả nghiệp vụ phải biểu đạt bằng phép toán thuần.

### 7.2. Hướng dẫn thực tế

- Cần **đếm**: dùng `count()` và sử dụng giá trị trả về.
- Cần **chuyển đổi dữ liệu**: dùng `map` rồi `collect`/`reduce` tùy mục tiêu.
- Cần **ghi log từng phần tử được xử lý** theo hợp đồng cụ thể: thiết kế cơ chế logging tại vị trí tiêu thụ phù hợp và kiểm soát parallelism, không trông chờ `peek().count()`.
- Cần **hiệu ứng cho mỗi phần tử**: `forEach`/`forEachOrdered` có ngữ nghĩa terminal phù hợp hơn, nhưng vẫn phải quan tâm thứ tự và thread-safety.

**Nội dung chính cần nhớ:** terminal operation là **điểm bắt đầu đánh giá kết quả** theo mô hình pipeline, không phải một lệnh bắt buộc “gọi toàn bộ lambda trong từng stage”.

## 8. `iterator()` và `spliterator()`: ngoại lệ của tính eager

Đa số terminal operations thực hiện phép tính trước khi trả về. Nhưng `BaseStream.iterator()` và `spliterator()` là hai **escape-hatch terminal operations**: chúng cung cấp quyền điều khiển việc duyệt cho bên ngoài pipeline.

```java
Stream<String> stream = Stream.of("a", "b")
        .map(String::toUpperCase);

Iterator<String> it = stream.iterator();

// Các phần tử được yêu cầu khi client duyệt iterator.
String first = it.next();  // "A"
String second = it.next(); // "B"
```

Gọi `iterator()` không đồng nghĩa với việc đã tự động hoàn tất toàn bộ công việc của stream như `collect()`. Với một số pipeline, việc chuẩn bị nguồn hoặc buffer có thể xảy ra ở các thời điểm khác nhau; điểm quan trọng là **client còn điều khiển quá trình lấy phần tử**.

`spliterator()` tương tự ở chỗ cho phép code bên ngoài gọi `tryAdvance`, `forEachRemaining`, v.v. Nhưng khi tự quản lý spliterator, bạn cũng phải tự xử lý vấn đề tiêu thụ, encounter order, đặc tính chia tách và đóng tài nguyên nếu có.

Không suy luận rằng `stream.iterator()` trả về một iterator có thể dùng để “reset stream”. Một Stream đã lấy terminal theo mô hình tiêu thụ một lần; nó không phải collection tái duyệt vô hạn.

## 9. Stream không được tái sử dụng sau khi đã tiêu thụ

Một Stream thường chỉ có **một vòng đời duyệt**. Sau terminal operation, pipeline được xem là đã tiêu thụ. Không gọi terminal khác trên cùng đối tượng Stream để dùng lại nguồn.

```java
Stream<String> s = Stream.of("x", "y");
long count = s.count(); // 2

// KHÔNG ĐƯỢC TÁI SỬ DỤNG STREAM:
// s.forEach(System.out::println);
```

Một implementation có thể phát hiện và ném `IllegalStateException`, nhưng tài liệu API cũng nhấn mạnh không phải mọi trường hợp reuse đều dễ phát hiện. Viết đúng là tạo Stream mới từ nguồn:

```java
List<String> values = Arrays.asList("x", "y");

long count = values.stream().count();
List<String> copy =
        values.stream().collect(Collectors.toList());
```

Ở đây có **hai Stream độc lập** từ cùng `List`, không phải một Stream được reset sau terminal.

### 9.1. Intermediate operations cũng là một phần của mô hình single-use

Không nên dùng một Stream chung làm hai nhánh:

```java
Stream<String> base = Stream.of("a", "bb", "ccc");

Stream<String> longer = base.filter(s -> s.length() > 1);

// SAI VỀ MÔ HÌNH SỬ DỤNG STREAM:
// Stream<Integer> sizes = base.map(String::length);
```

Đừng hiểu “filter chưa chạy vì lazy” thành “base vẫn có thể tạo nhiều pipeline rẽ nhánh”. Hợp đồng yêu cầu một Stream được vận hành một lần, gồm cả intermediate operations. Nếu cần hai kết quả độc lập, hãy tạo hai Stream từ nguồn có thể tái tạo hoặc sử dụng một collector thích hợp.

## 10. Nguồn dữ liệu và thời điểm bắt đầu duyệt

### 10.1. Pipeline lazy nhưng biểu thức tạo nguồn vẫn có thể chạy ngay

```java
static String createValue() {
    System.out.println("createValue called");
    return "value";
}

Stream<String> s = Stream.of(createValue());
```

Đây là đoạn minh họa: `createValue()` được đánh giá **trước khi** `Stream.of(...)` được gọi vì quy tắc đánh giá đối số của Java. Không có terminal operation nào ở đây, nhưng side effect của **biểu thức tạo nguồn** đã xảy ra.

Khác với generator:

```java
Stream<String> generated = Stream.generate(() -> {
    System.out.println("generate value");
    return "value";
});
```

`Supplier` của `Stream.generate` được dùng **khi pipeline cần phần tử**. Chỉ gọi `Stream.generate(supplier)` không có nghĩa generator đã chạy để tạo toàn bộ dữ liệu. `generate` là nguồn vô hạn theo hợp đồng trừ khi bị giới hạn/short-circuit; đừng dùng `collect(toList())` trực tiếp trên một generator vô hạn mà không có cách hoàn tất.

### 10.2. Một ví dụ về late-binding trên collection

Theo Oracle package documentation, những nguồn collection well-behaved thường tránh duyệt nguồn cho tới khi terminal bắt đầu. Với `ArrayList`:

```java
List<String> items =
        new ArrayList<>(Arrays.asList("A", "B"));

Stream<String> stream = items.stream();
items.add("C"); // Thay đổi trước khi bắt đầu terminal.

List<String> collected =
        stream.collect(Collectors.toList());

// Với nguồn collection chuẩn này: [A, B, C].
```

Lưu ý:

- Đây không phải giấy phép **thay đổi collection khi traversal đang diễn ra**.
- `ArrayList` không phải concurrent collection; sửa nguồn trong callback hoặc từ thread khác trong lúc pipeline đang chạy có thể gây kết quả sai hoặc `ConcurrentModificationException`.
- Không phải mọi source do thư viện bên ngoài tạo đều late-binding giống nguồn collection chuẩn. Cần xem hợp đồng `Spliterator`/supplier cụ thể.
- Nếu bạn thực sự cần snapshot, hãy sao chép dữ liệu thành cấu trúc snapshot trước khi xây pipeline, thay vì trông chờ thời điểm đánh giá ngầm.

### 10.3. I/O Streams: lazy không tự đóng tài nguyên

`Files.lines(Path)` có thể mở file hoặc tài nguyên gắn với I/O khi tạo stream. Dù các dòng có thể được đọc khi pipeline duyệt, **người gọi vẫn phải đóng Stream**:

```java
static long nonEmptyLines(java.nio.file.Path path)
        throws java.io.IOException {

    try (Stream<String> lines =
                 java.nio.file.Files.lines(
                         path, java.nio.charset.StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.trim().isEmpty())
                .count();
    }
}
```

Đây là **một method minh họa** cần import `java.util.stream.Stream` hoặc tên đầy đủ tương ứng. `try-with-resources` bảo đảm đóng stream ngay cả khi có exception; một terminal operation như `count()` **không tự đồng nghĩa close stream**. Với stream dựa trên collection/array, thường không có tài nguyên bên ngoài cần đóng; với stream gắn với I/O, cần quản lý vòng đời cụ thể.

## 11. Stream vô hạn: lazy kết hợp short-circuit

Một Stream có thể đại diện một dãy vô hạn:

```java
Stream<Integer> numbers = Stream.iterate(1, n -> n + 1);
```

Nếu chỉ yêu cầu năm phần tử:

```java
int sum = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .mapToInt(Integer::intValue)
        .sum();

// sum = 1 + 2 + 3 + 4 + 5 = 15
```

`limit(5)` là stage short-circuit; terminal `sum` nhận tập hữu hạn được giới hạn, nên kết thúc.

Nhưng:

```java
// TRÁNH: pipeline không có điều kiện kết thúc hữu hạn.
// Stream.iterate(1, n -> n + 1).count();
```

Trong ví dụ cảnh báo, nguồn không kết thúc và không có short-circuit hữu hiệu. `count()` không thể tự đoán số phần tử vô hạn để hoàn tất bình thường. Tránh chạy ví dụ đó trong ứng dụng.

### 11.1. `takeWhile` và `dropWhile` là tiện ích Java 9+

Nếu dự án dùng Java 9 trở lên:

```java
List<Integer> prefix = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n < 5)
        .collect(Collectors.toList());

// prefix = [1, 2, 3, 4]
```

`takeWhile` lấy prefix còn thỏa điều kiện, nên có thể kết thúc khi gặp một phần tử không đạt. **Cú pháp/API này không có trong Java 8**, vì vậy chương trình minh họa độc lập vẫn dùng `limit` để bảo toàn khả năng biên dịch với Java 8.

`dropWhile` cũng được giới thiệu từ Java 9, nhưng không tự bảo đảm một Stream vô hạn sẽ kết thúc: nếu điều kiện luôn đúng và nguồn vô hạn, operation có thể tiếp tục bỏ phần tử mãi. Không thể gộp mọi operation mang chữ “while” thành short-circuit trong mọi bối cảnh.

## 12. Sequential và parallel: lazy như nhau, thứ tự duyệt có thể khác

`stream()` thường tạo **sequential stream**; `parallelStream()` hoặc `parallel()` yêu cầu **parallel execution mode**. Cả hai đều dùng mô hình intermediate lazy và terminal.

Tuy nhiên, trong parallel pipeline:

- Phần tử có thể được xử lý trên nhiều thread.
- Thứ tự chạy side effects trong `map`/`filter`/`peek` không nhất thiết giống encounter order.
- Các stage stateful như `sorted`/`distinct` hoặc ordered `limit` có thể làm tăng buffering/synchronization.
- `findAny()` có thể trả một phần tử khác giữa các lần chạy.
- Short-circuit có thể **đụng tới nhiều phần tử hơn mức nhỏ nhất** vì công việc song song đã được lên lịch.

**Không nên suy ra** rằng `parallel().limit(2)` chỉ luôn gọi predicate đúng hai lần, hoặc rằng `peek` của các phần tử sẽ in theo thứ tự nguồn.

### 12.1. `forEach` và `forEachOrdered`

`forEach` là terminal operation dùng cho side effect trên mỗi phần tử được duyệt, nhưng trên parallel stream thứ tự có thể khác:

```java
Stream.of("a", "b", "c")
        .parallel()
        .forEach(System.out::println);
```

Đầu ra có thể khác thứ tự `a,b,c`. Nếu cần thứ tự theo encounter order:

```java
Stream.of("a", "b", "c")
        .parallel()
        .forEachOrdered(System.out::println);
```

`forEachOrdered` bảo đảm tôn trọng encounter order **nếu nguồn có encounter order**; điều này có thể làm giảm lợi ích parallel. Cả hai không phải cách thay thế phù hợp cho `collect` khi mục tiêu là tạo dữ liệu mới để tiếp tục xử lý.

### 12.2. Side effects nên stateless và không can thiệp nguồn

`Predicate`/`Function` truyền cho Stream nên **non-interfering** (không sửa nguồn đang duyệt) và trong hầu hết trường hợp **stateless**.

Thiết kế dễ gây lỗi:

```java
List<String> source = new ArrayList<>(
        Arrays.asList("a", "b", "c"));

// KHÔNG NÊN: sửa chính source trong pipeline.
// source.stream()
//       .peek(source::remove)
//       .count();
```

Ví dụ trên là anti-pattern. Một số terminal hoặc metadata có thể loại bỏ `peek`, khiến code có vẻ “không sao” ở lần chạy này, nhưng chuyển terminal hoặc nguồn dữ liệu sẽ bộc lộ hành vi không hợp lệ. Không dùng side effect trong intermediate operation để làm nghiệp vụ quan trọng.

Đúng hơn:

```java
List<String> normalized = source.stream()
        .map(s -> s.toUpperCase(Locale.ROOT))
        .collect(Collectors.toList());
```

Pipeline tạo collection mới mà không sửa collection gốc. Cách này dễ kiểm thử, dễ reason và có khả năng tối ưu tốt hơn.

## 13. Lỗi và thời điểm xuất hiện exception

Tính lazy cũng ảnh hưởng **khi nào exception phát sinh**. Nếu một lambda trong intermediate operation ném exception khi xử lý phần tử, lỗi thường xảy ra **khi pipeline đánh giá phần tử đó**, chứ không phải ngay lúc đăng ký lambda.

```java
Stream<Integer> pipeline = Stream.of("2", "bad", "4")
        .map(Integer::parseInt);

// Đến đây map chưa parse các chuỗi.

// terminal cần giá trị nên sẽ gặp "bad":
// List<Integer> values = pipeline.collect(Collectors.toList());
```

Đoạn bị comment, nếu chạy, thường ném `NumberFormatException` tại lúc xử lý `"bad"` trong terminal. Nhưng không rút ra rằng mọi terminal chắc chắn ném lỗi từ `map`:

- Short-circuit có thể **không bao giờ chạm tới** phần tử gây lỗi.
- Tối ưu hóa (như `count` trên nguồn có kích thước biết trước) có thể **bỏ qua cả mapper** nếu không ảnh hưởng kết quả.
- Một số exception do **tham số đầu vào không hợp lệ của intermediate method** hoặc **biểu thức đối số** có thể xuất hiện **ngay khi xây pipeline**.

Ví dụ:

```java
// Có thể ném NullPointerException ngay khi gọi filter
// vì predicate không được phép null:
// Stream.of("a").filter(null);
```

Do đó, khi debug lỗi, phân biệt **thời điểm cấu hình pipeline** với **thời điểm xử lý từng phần tử**. Không dựa vào side effect hay exception chưa xuất hiện để khẳng định một stage “đã chạy”.

## 14. Chương trình Java hoàn chỉnh: thời điểm bắt đầu duyệt

Tạo file **`LazyStreamTraversalDemo.java`**. Chương trình dùng Java 8-compatible Stream API và hoạt động trên JDK 17+. Các output minh họa được chọn trong ngữ cảnh **sequential**, với nguồn `List`/`Stream.of` có encounter order, để kiểm tra rõ thời điểm thực thi.

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LazyStreamTraversalDemo {

    public static void main(String[] args) {
        System.out.println("1. create");

        Stream<String> pipeline =
                Arrays.asList("java", "go", "kotlin", "js")
                      .stream()
                      .filter(s -> {
                          System.out.println("filter " + s);
                          return s.length() > 2;
                      })
                      .map(s -> {
                          System.out.println("map " + s);
                          return s.toUpperCase(Locale.ROOT);
                      });

        System.out.println("2. before collect");

        List<String> result =
                pipeline.collect(Collectors.toList());
        System.out.println("3. result " + result);

        System.out.println("4. short circuit");
        List<Integer> odds = Stream.of(1, 2, 3, 4, 5, 6)
                .filter(n -> {
                    System.out.println("test " + n);
                    return n % 2 != 0;
                })
                .limit(2)
                .collect(Collectors.toList());
        System.out.println("odds " + odds);

        System.out.println("5. anyMatch");
        boolean found = Stream.of(4, 7, 8, 9)
                .anyMatch(n -> {
                    System.out.println("checking " + n);
                    return n % 2 != 0;
                });
        System.out.println("found " + found);

        System.out.println("6. infinite limited");
        int sum = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("sum " + sum);

        System.out.println("7. iterator");
        Iterator<String> it = Stream.of("a", "b")
                .map(s -> s.toUpperCase(Locale.ROOT))
                .iterator();
        System.out.println("next " + it.next());
        System.out.println("next " + it.next());

        System.out.println("8. new stream");
        System.out.println("count "
                + Stream.of("a", "bb", "ccc").count());
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac LazyStreamTraversalDemo.java
java LazyStreamTraversalDemo
```

**Stdout của chương trình:**

```text
1. create
2. before collect
filter java
map java
filter go
filter kotlin
map kotlin
filter js
3. result [JAVA, KOTLIN]
4. short circuit
test 1
test 2
test 3
odds [1, 3]
5. anyMatch
checking 4
checking 7
found true
6. infinite limited
sum 15
7. iterator
next A
next B
8. new stream
count 3
```

**Đọc output theo từng phần:**

1. `1. create` xuất hiện trước khi tạo pipeline. Sau bước này, không có log `filter` hay `map`.
2. `2. before collect` tiếp tục xuất hiện mà không có log từ callback. Điều đó minh họa **xây pipeline không duyệt nguồn**.
3. Khi `collect` thực thi, từng phần tử đi qua `filter`; các phần tử đạt điều kiện mới đi qua `map`; cuối cùng tạo `[JAVA, KOTLIN]`.
4. Ở `filter(...).limit(2)`, chỉ cần kiểm tra `1`, `2`, `3` để lấy hai số lẻ; dừng trước `4`. Kết quả `[1, 3]`.
5. `anyMatch` gặp số lẻ `7` ngay ở phần tử thứ hai. Predicate không cần xét `8` hoặc `9`; trả `true`.
6. `Stream.iterate` là nguồn vô hạn nhưng `limit(5)` tạo phần dữ liệu hữu hạn để `sum` trả 15.
7. `iterator()` trao quyền duyệt cho client; hai lời gọi `next()` lần lượt trả `A` rồi `B`. Không có việc thu thập sẵn toàn bộ danh sách kết quả.
8. `count()` trên một Stream mới trả 3. Ví dụ không đoán callback nào sẽ được gọi khi tính đếm; nó chỉ quan tâm kết quả.

Ví dụ có log trong `filter` để dạy cơ chế sequential pipeline; việc đưa các callback có side effect vào logic thực tế không được khuyến nghị. Với những callback có thể bị loại bỏ trong tối ưu hóa, đặc biệt `peek` hoặc `map` chỉ phục vụ một `count`, không được dựa vào log như hành vi được bảo đảm.

## 15. Bảng thời điểm: lời gọi nào thực sự gây duyệt?

| Lời gọi | Có duyệt phần tử nguồn ngay không? | Ghi chú |
| --- | --- | --- |
| `list.stream()` | Thông thường chưa | Tạo Stream từ collection; các nguồn chuẩn thường late-binding |
| `Stream.of(value)` | Không duyệt pipeline | Nhưng các biểu thức đối số đã được đánh giá trước |
| `Stream.generate(supplier)` | Chưa gọi generator chỉ vì tạo Stream | Supplier được yêu cầu khi cần phần tử |
| `stream.filter(predicate)` | **Không** | Intermediate lazy |
| `stream.map(mapper)` | **Không** | Intermediate lazy |
| `stream.sorted()` | **Không** | Intermediate lazy nhưng khi duyệt có thể buffer toàn nguồn |
| `stream.limit(n)` | **Không** | Intermediate short-circuiting |
| `stream.collect(...)` | Bắt đầu yêu cầu kết quả | Thường duyệt các phần tử cần thiết |
| `stream.findFirst()` | Bắt đầu yêu cầu kết quả | Có thể dừng sớm |
| `stream.anyMatch(...)` | Bắt đầu yêu cầu kết quả | Có thể dừng sớm |
| `stream.count()` | **Có thể không cần duyệt** | Dùng kích thước nguồn/metadata nếu hợp lệ |
| `stream.iterator()` | **Không eager theo nghĩa terminal thông thường** | Client chủ động duyệt iterator |
| `stream.spliterator()` | **Không eager theo nghĩa terminal thông thường** | Client chủ động duyệt spliterator |
| `Files.lines(path)` | Có thể mở tài nguyên ở lúc tạo | Phải close sau sử dụng |
| `stream.close()` | Không phải terminal xử lý phần tử | Giải phóng tài nguyên/thực thi close handlers theo hợp đồng |

Trong bảng, “chưa duyệt” chỉ là **chưa xử lý các phần tử nguồn theo pipeline**. Nó không phủ nhận việc biểu thức đối số, factory source, validation hoặc tạo resource có thể chạy ngay.

## 16. Những hiểu lầm phổ biến

### Hiểu lầm 1: “`map()` chạy ngay khi gọi”

Sai. `map` tạo một stage trung gian. Callback được đánh giá khi phần tử thực sự cần được xử lý, và có thể không chạy trong pipeline mà implementation tối ưu bỏ được stage.

### Hiểu lầm 2: “Cứ gọi terminal là duyệt hết nguồn”

Sai. `findFirst`, `anyMatch`, `limit` và nhiều tình huống short-circuit giúp dừng sớm. `count` còn có thể trả kết quả từ metadata mà không duyệt.

### Hiểu lầm 3: “Lazy tức là không tốn CPU/memory khi pipeline chạy”

Sai. `sorted`/`distinct` là intermediate lazy nhưng có thể cần xử lý và lưu nhiều phần tử **sau khi traversal bắt đầu**. Lazy không đồng nghĩa không có chi phí hay tự tối ưu mọi trường hợp.

### Hiểu lầm 4: “`peek()` được bảo đảm in mọi phần tử”

Sai. `peek` là intermediate; khi terminal có thể tính kết quả bằng cách bỏ qua traversal, side effect có thể không được thực hiện. Không dùng `peek` làm logging bắt buộc, audit, ghi database hoặc cập nhật counter nghiệp vụ.

### Hiểu lầm 5: “Stream luôn là danh sách trong bộ nhớ”

Sai. Stream có thể biểu diễn generator vô hạn hoặc các dòng từ file. Nó là **mô hình tính toán/duyệt**, không phải collection lưu trữ toàn bộ phần tử.

### Hiểu lầm 6: “Một Stream lazy nên dùng đi dùng lại được”

Sai. Dù callback chưa thực thi, Stream không được thiết kế như một collection có thể rewind hoặc chia nhánh tùy ý. Tạo Stream mới từ nguồn khi cần một lượt xử lý khác.

### Hiểu lầm 7: “`iterator()` không phải terminal”

Không chính xác. `iterator()` và `spliterator()` thuộc nhóm **terminal escape-hatch operations**, nhưng khác nhiều terminal khác vì việc duyệt có thể được client điều khiển sau khi phương thức trả về.

### Hiểu lầm 8: “`Files.lines` lazy nên không cần close”

Sai. Tạo nguồn có thể mở tài nguyên, còn terminal không tự bảo đảm close. Dùng `try-with-resources` cho Stream gắn với I/O.

### Hiểu lầm 9: “Có thể đổi thứ tự `limit` và `filter` tùy ý”

Sai. `filter(...).limit(2)` lấy hai phần tử phù hợp đầu tiên; `limit(2).filter(...)` chỉ lọc trên hai phần tử đầu nguồn. Kết quả và số phần tử được xét có thể khác.

### Hiểu lầm 10: “`parallel` vẫn thực thi predicate theo thứ tự in ra”

Sai. Parallel stream vẫn lazy trước terminal, nhưng thứ tự chạy callback và thread được dùng không phải hợp đồng encounter order giống log sequential. Dùng các terminal có ngữ nghĩa thứ tự rõ khi thật sự cần.

### Hiểu lầm 11: “Nguồn collection không thể thay đổi từ lúc gọi `stream()`”

Không đúng một cách tổng quát. Nhiều nguồn chuẩn có tính late-binding và có thể phản ánh thay đổi trước terminal. Nhưng **không** vì thế mà được sửa nguồn khi pipeline đang duyệt.

### Hiểu lầm 12: “Chưa thấy exception tức là mapper không có lỗi”

Không chắc. Mapper có thể chưa được gọi hoặc đã bị tối ưu bỏ qua, đặc biệt khi terminal không cần giá trị biến đổi. Test cần chọn terminal thực sự sử dụng kết quả mapper, không chỉ gọi `count()`.

## 17. Cách thiết kế pipeline dễ hiểu và an toàn

Khi code xử lý dữ liệu bằng Stream, hãy làm theo trình tự:

1. **Xác định mục tiêu kết quả** trước khi chọn terminal: thu collection, tổng, đếm, tìm phần tử hay phát sinh hiệu ứng.
2. **Tạo nguồn** phù hợp với khả năng hữu hạn/vô hạn và tài nguyên cần quản lý.
3. **Giữ intermediate operations là phép biến đổi thuần** nếu có thể: không sửa source, không phụ thuộc biến mutable bên ngoài.
4. **Đặt các stage đúng thứ tự ngữ nghĩa**: `filter` trước hay sau `limit` có thể đổi kết quả; `sorted` trước `limit` có thể tạo chi phí lớn.
5. **Chọn short-circuit khi chỉ cần một phần kết quả**: `findFirst`, `anyMatch`, `limit` thay vì tự động thu toàn bộ vào List.
6. **Không làm logic quan trọng trong `peek`**: tối ưu hóa có thể bỏ các callback.
7. **Đừng giả định số lần gọi callback**: tập trung kiểm tra giá trị kết quả, đặc biệt với `parallel`/`count`.
8. **Tạo Stream mới cho mỗi lượt tiêu thụ** nếu nguồn cho phép, không tái sử dụng Stream đã có intermediate/terminal.
9. **Đóng nguồn I/O** trong `try-with-resources`, đừng kỳ vọng laziness xử lý vòng đời tài nguyên.
10. **Test cả nguồn rỗng, nguồn dài, lỗi mapper, short-circuit và ordering** để tránh hành vi tình cờ từ một runtime.
11. **Kiểm thử hiệu năng với dữ liệu thật**: stateful stages có thể gây buffering; parallelism không mặc nhiên nhanh hơn.
12. **Dùng API đúng phiên bản**: `filter/map/limit/collect/findFirst` có từ Java 8; `takeWhile/dropWhile` cần Java 9+; `Stream.toList()` là Java 16+.

### 17.1. Khi nào nên dùng for-loop thay cho Stream?

Stream rất phù hợp khi mô hình là **lọc → chuyển đổi → tổng hợp** với hàm thuần. Một vòng lặp có thể dễ đọc hơn nếu nghiệp vụ phụ thuộc nhiều state được cập nhật tuần tự, có nhiều nhánh break/continue phức tạp hoặc cần kiểm soát tài nguyên theo từng bước. Không nên đổi mọi vòng lặp thành Stream chỉ để có “cú pháp hiện đại”.

Ngược lại, không nên từ chối Stream vì hiểu sai rằng tất cả intermediate stages luôn tạo collection tạm. Các stage stateless có thể được fuse trong một lần duyệt, giúp giảm công việc không cần thiết.

## 18. Tự kiểm tra

1. Với `stream.filter(p).map(f)` nhưng chưa gọi terminal, predicate `p` và mapper `f` đã xử lý các phần tử nguồn chưa?
2. Vì sao `filter` và `map` thường có thể chạy xen kẽ trên từng phần tử thay vì cần hai vòng lặp toàn bộ?
3. `findFirst()` có được phép dừng trước khi xem hết nguồn không? Trường hợp nào `sorted()` đứng trước làm chi phí tăng mạnh?
4. `Stream.iterate(0,n->n+1).limit(5).count()` có luôn chạy mapper hoặc hàm next đúng số lần mà bạn tự đoán không?
5. Vì sao `stream.peek(log).count()` không phải một cơ chế log bắt buộc?
6. Tại sao `iterator()` được xếp là terminal nhưng vẫn cho phép client duyệt sau đó?
7. Nếu nguồn là `List` và muốn chạy hai phép tính độc lập, nên dùng cùng Stream hai lần hay tạo hai Stream mới?
8. Sự khác nhau giữa `filter(even).limit(2)` và `limit(2).filter(even)` là gì?
9. `Files.lines(path)` có thể tạo tài nguyên gì ngay khi gọi factory? Khi nào cần đóng?
10. Với một nguồn vô hạn và stage `sorted` trước `limit`, điều gì khiến chương trình có thể không kết thúc?
11. Nếu source có encounter order, `parallel().forEach(...)` có bảo đảm in đúng thứ tự đó không?
12. Tại sao thay đổi một `ArrayList` từ bên trong callback Stream là hành vi không an toàn?
13. Nếu `count()` trả đúng kích thước nhưng `map` không chạy, đó là lỗi hay hành vi hợp lệ?
14. Khi nào `Stream.generate` gọi Supplier của nó so với việc đánh giá một biểu thức truyền vào `Stream.of(...)`?
15. Vì sao “lười” không đồng nghĩa “không có side effect nào trong lúc tạo pipeline”?

**Kết luận:** intermediate operations của Java Stream là **lazy**: chúng dựng kế hoạch tính toán, không thực hiện duyệt phần tử nguồn ngay. Terminal operation thường là **điểm kích hoạt yêu cầu kết quả**, nhưng việc duyệt có thể dừng sớm, cần buffer ở stage stateful hoặc được tối ưu tránh hoàn toàn. Hai escape hatches `iterator()` và `spliterator()` đặc biệt cho phép client điều khiển thời điểm lấy phần tử. Viết pipeline hiệu quả đòi hỏi hiểu **thời điểm dữ liệu thực sự được yêu cầu, thứ tự stage, khả năng short-circuit, ràng buộc single-use và quản lý tài nguyên**, chứ không chỉ nhớ câu “Stream chạy khi có terminal”.

## Tài liệu chuẩn

- Java SE 26, **`java.util.stream` package summary** — laziness, nguồn, intermediate/terminal, stateful, short-circuit, non-interference, side effects: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- Java SE 26, **`Stream` API** — terminal operations, `count()` optimization và stream reuse: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Java SE 26, **`BaseStream` API** — `iterator()`, `spliterator()` và `close()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html
- Java SE 26, **`Files.lines` API** — tài nguyên I/O và yêu cầu close: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)
