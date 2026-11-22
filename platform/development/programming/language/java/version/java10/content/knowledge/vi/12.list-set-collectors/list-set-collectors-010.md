# Thu thập Stream tuần tự và Stream song song bằng Collector danh sách và tập (Java 10+)

## 1. Mục tiêu: cùng dữ liệu, hai chế độ xử lý, phải hiểu đúng hợp đồng kết quả

Java Stream có thể thực thi pipeline **tuần tự (sequential)** hoặc **song song (parallel)**. Một trong những thao tác kết thúc phổ biến là `collect(Collector)`: gom các phần tử sau `filter`, `map`, `distinct` và những phép biến đổi khác thành `List` hoặc `Set`.

```java
var input = java.util.List.of("An", "Binh", "An", "Chi");

// Stream tuần tự
var sequential = input.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());

// Stream song song
var parallel = input.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(sequential);               // [An, Binh, An, Chi]
System.out.println(parallel);                 // [An, Binh, An, Chi]
System.out.println(sequential.equals(parallel)); // true
```

Với nguồn `List` có **encounter order**, collector `toUnmodifiableList()` giữ thứ tự đó ngay cả khi pipeline được thực thi song song. Song song **không có nghĩa kết quả của collector danh sách bị đảo lộn**.

Nhưng khi thu thập vào `Set`:

```java
var unique = input.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

System.out.println(unique.size());        // 3
System.out.println(unique.contains("An")); // true
// Không được khẳng định unique.toString() luôn in [An, Binh, Chi].
```

`Set` chỉ chứa phần tử phân biệt và **không cam kết thứ tự duyệt** đối với collector này.

Bài học tập trung vào các collector cho danh sách và tập hợp, đặc biệt `Collectors.toList()`, `Collectors.toSet()`, `Collectors.toUnmodifiableList()`, `Collectors.toUnmodifiableSet()` và `Collectors.toCollection(...)`. Hai collector `toUnmodifiableList`/`toUnmodifiableSet` xuất hiện từ Java 10 và vẫn áp dụng trong Java hiện đại. Ví dụ chạy dùng Java 17 trở lên.

**Sau bài học, bạn có thể:**

- Phân biệt `stream()` và `parallelStream()`, cùng `sequential()`/`parallel()`.
- Dự đoán **nội dung, thứ tự và khả năng sửa** của kết quả khi dùng collector List/Set ở hai chế độ.
- Giải thích cơ chế **supplier – accumulator – combiner – finisher** khi thu thập song song.
- Tránh sai lầm về shared mutable state, side effect, `forEach` và `Collectors.toList()`.
- Hiểu `null`, phần tử trùng, `equals/hashCode` và representative của unmodifiable set.
- Biết khi nào cần `LinkedHashSet`, `TreeSet`, `ArrayList` hoặc collector phù hợp hơn.
- Kiểm tra tính đúng và hiệu năng mà không dựa vào lịch chạy thread không được bảo đảm.

## 2. Stream tuần tự và Stream song song khác nhau ở đâu?

Một pipeline gồm **nguồn dữ liệu**, các thao tác trung gian và **terminal operation**:

```java
var result = numbers.stream()       // nguồn + chế độ tuần tự
        .filter(n -> n % 2 == 0)     // intermediate
        .map(n -> n * n)            // intermediate
        .collect(Collectors.toList()); // terminal: thu thập
```

Đoạn này giả sử `numbers` là `List<Integer>` và đã import `Collectors`. `stream()` tạo stream tuần tự; thay bằng `parallelStream()` đề nghị Stream Framework có thể xử lý phần tử trên nhiều luồng.

```java
var sequential = numbers.stream()
        .map(n -> n * n)
        .collect(Collectors.toList());

var parallel = numbers.parallelStream()
        .map(n -> n * n)
        .collect(Collectors.toList());
```

Hai biến có cùng kiểu tĩnh `List<Integer>`. Khi nguồn có thứ tự duyệt xác định (chẳng hạn `ArrayList` hoặc `List.of`) và phép biến đổi không can thiệp trạng thái, hai danh sách có **cùng thứ tự encounter** và phần tử tương ứng.

**Không được suy diễn** `parallelStream()` luôn tạo đúng N thread, mỗi phần tử nhất định chạy trên một thread khác hoặc chắc chắn nhanh hơn. Lịch chạy là chi tiết thực thi.

### Chuyển chế độ bằng `parallel()` và `sequential()`

```java
var seq = numbers.stream().sequential();
var par = numbers.stream().parallel();
```

`BaseStream.isParallel()` cho biết chế độ parallel của stream ở thời điểm gọi:

```java
System.out.println(numbers.stream().isParallel());         // false
System.out.println(numbers.parallelStream().isParallel()); // true
```

Điều này mô tả **chế độ pipeline**, không bảo đảm số thread thực tế hoặc hiệu năng cao hơn. Stream thường được xử lý lười; các intermediate operations chưa thực thi khi chưa có terminal operation.

## 3. Encounter order khác với thứ tự thread thực thi

**Encounter order** là thứ tự logic các phần tử được stream nhận từ nguồn, nếu nguồn có thứ tự.

- `List` hoặc mảng có encounter order theo chỉ số.
- `LinkedHashSet` thường duyệt theo thứ tự chèn; stream từ nó có encounter order đó.
- `HashSet` không có encounter order được bảo đảm bởi hợp đồng.
- `sorted(...)` có thể thiết lập thứ tự logic; `unordered()` cho phép loại bỏ ràng buộc thứ tự.
- Một số terminal operations như `forEach(...)` được phép xử lý theo thứ tự bất kỳ, nhất là ở chế độ parallel.

**Ranh giới cần hiểu:**

```java
var data = java.util.List.of(1, 2, 3, 4, 5);

var result = data.parallelStream()
        .map(x -> x * 10)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(result); // [10, 20, 30, 40, 50]
```

Không có cam kết `map` được thực hiện theo thứ tự 1→2→3→4→5 ở các thread. Dù vậy, collector danh sách bảo toàn encounter order trong kết quả.

Trái lại:

```java
data.parallelStream().forEach(System.out::println);
```

Cách in có thể tạo thứ tự khác nhau. Đây không phải phép thu thập vào list. Nếu cần phát output theo encounter order, `forEachOrdered` có thể giúp tôn trọng thứ tự đối với stream ordered, nhưng vẫn nên dùng `collect` khi cần **một tập hợp kết quả**; `forEachOrdered` không tạo collection.

### Nếu nguồn vốn không ordered

```java
var setSource = new java.util.HashSet<Integer>();
setSource.add(3);
setSource.add(1);
setSource.add(2);

var list = setSource.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Đầu ra có ba giá trị nhưng **không nên giả định `[1,2,3]`**, vì nguồn `HashSet` không cam kết encounter order. Đổi từ `parallelStream()` về `stream()` cũng **không** biến nguồn không ordered thành ordered.

Nếu ứng dụng cần thứ tự cụ thể, sắp xếp rõ:

```java
var ordered = setSource.parallelStream()
        .sorted()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
System.out.println(ordered); // [1, 2, 3]
```

## 4. `collect(Collector)` hoạt động thế nào khi parallel?

Một `Collector<T,A,R>` mô tả cách gom các phần tử kiểu `T` vào kết quả kiểu `R`, thường qua vùng tích lũy trung gian kiểu `A`. Các thành phần cơ bản:

1. **supplier:** tạo một container tích lũy mới.
2. **accumulator:** đưa một phần tử vào container trung gian.
3. **combiner:** hợp nhất hai container trung gian sau khi pipeline có thể được chia thành các phần.
4. **finisher:** chuyển trạng thái trung gian thành kết quả cuối; với collector có `IDENTITY_FINISH`, kết quả tích lũy có thể được dùng trực tiếp.
5. **characteristics:** các thuộc tính như `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH` hướng dẫn cách framework được phép triển khai reduction.

Sơ đồ khái niệm cho `parallelStream().collect(...)`:

```text
Nguồn có encounter order: [A, B, C, D]
                   |
              chia phần việc
              /           \
           [A, B]        [C, D]
             |              |
      container X      container Y
      accumulator      accumulator
             \              /
                combiner
                   |
                finisher
                   |
                kết quả
```

Đây chỉ là **mô hình giải thích**; Java không cam kết đúng hai partition hay một cây kết hợp cố định.

**Điểm quan trọng:** một collector không `CONCURRENT` như `Collectors.toList()` có thể được dùng an toàn trong parallel stream. Framework thường tạo và gom các **container riêng** rồi hợp nhất chúng; ứng dụng không phải tự đưa chung một `ArrayList` chưa đồng bộ cho mọi thread.

### Tại sao collector phải tuân thủ tính kết hợp?

Một phép reduction muốn chạy song song cần kết quả đúng dù framework chia và gộp từng phần theo cách khác nhau. `combiner` phải phối hợp đúng với `accumulator` để duy trì tính kết hợp và các ràng buộc nhận dạng theo `Collector`.

Ví dụ gộp danh sách bằng `addAll` không đồng nghĩa việc các thread được phép tự ý viết vào **cùng** `ArrayList` bên ngoài. Chỉ dùng collector có hợp đồng đúng; viết custom collector cần hiểu kỹ supplier/accumulator/combiner/characteristics.

Không dùng một phép reduction có trạng thái phụ thuộc thứ tự thread rồi kỳ vọng `parallel()` cho kết quả giống vòng `for` tuần tự.

## 5. Thu thập vào `List`: thứ tự được bảo toàn khi nguồn ordered

### 5.1. `Collectors.toList()`

```java
var names = java.util.List.of("An", "Binh", "Chi");

var sequential = names.stream()
        .collect(java.util.stream.Collectors.toList());

var parallel = names.parallelStream()
        .collect(java.util.stream.Collectors.toList());

System.out.println(sequential);             // [An, Binh, Chi]
System.out.println(parallel);               // [An, Binh, Chi]
System.out.println(sequential.equals(parallel)); // true
```

`Collectors.toList()` gom phần tử theo **encounter order**. Tuy nhiên, Javadoc **không bảo đảm** kiểu implementation, khả năng sửa, tính serializable hay thread-safety của list kết quả. Đừng viết code phụ thuộc vào việc nó luôn là `ArrayList` hoặc luôn sửa được chỉ vì JDK bạn đang dùng hiện trả một list như thế.

### 5.2. `Collectors.toUnmodifiableList()` (Java 10+)

```java
var names = java.util.List.of("An", "Binh", "Chi");
var result = names.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(result); // [An, Binh, Chi]
// result.add("Du");        // Ném UnsupportedOperationException nếu chạy
```

Đặc điểm:

- Giữ **encounter order** nếu stream có order.
- Kết quả **không cho sửa** qua API danh sách.
- **Từ chối `null`**, ném `NullPointerException` nếu phần tử đầu vào collector là `null`.
- Phần tử tham chiếu mutable vẫn có thể đổi trạng thái qua alias; đây **không phải deep copy**.
- Các đặc điểm trên không đổi chỉ vì stream là parallel.

### 5.3. `Stream.toList()` (Java 16+) không giống `Collectors.toList()`

```java
var result = java.util.List.of("An", "Binh")
        .parallelStream()
        .toList();
```

`Stream.toList()` giữ encounter order (nếu có) và trả list **không sửa được**. API này có từ **Java 16**, không phải tính năng Java 10 gốc. Điểm khác đáng nhớ:

- `Collectors.toList()` **không cam kết** khả năng sửa.
- `Stream.toList()` **cam kết** kết quả unmodifiable và **cho phép `null`** nếu stream phát ra `null`.
- `Collectors.toUnmodifiableList()` **cam kết** kết quả unmodifiable nhưng **không chấp nhận `null`**.

Đừng thay đổi giữa các API chỉ vì tên na ná nhau mà không xem hợp đồng `null` và khả năng sửa.

### 5.4. Cần chắc chắn là `ArrayList` có thể sửa?

```java
var editable = names.parallelStream()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));

editable.add("Du");
```

`Collectors.toCollection(ArrayList::new)` cam kết tạo collection bằng factory cung cấp; `ArrayList` là mutable. Với nguồn `List` ordered, collector này tích lũy theo encounter order, kể cả khi thực thi song song.

Nếu chỉ muốn phần tử được chỉnh sửa về sau, không nên phụ thuộc vào mutability không được tài liệu bảo đảm của `Collectors.toList()`.

## 6. Thu thập vào `Set`: duy nhất theo `equals`, không cam kết thứ tự

### 6.1. `Collectors.toSet()`

```java
var words = java.util.List.of("An", "Binh", "An", "Chi");
var sequential = words.stream()
        .collect(java.util.stream.Collectors.toSet());
var parallel = words.parallelStream()
        .collect(java.util.stream.Collectors.toSet());

System.out.println(sequential.equals(parallel)); // true
System.out.println(parallel.size());             // 3
```

`Collectors.toSet()` là một **UNORDERED collector**; không có bảo đảm về implementation, khả năng sửa, serializability hoặc thread-safety của `Set` được trả về. Không được giả định nó là `HashSet` có thể `add` hay nó luôn duyệt theo thứ tự xuất hiện của nguồn.

Khi input có giá trị trùng theo `equals`, set kết quả biểu diễn các giá trị phân biệt. Quy tắc `equals/hashCode` của phần tử phải nhất quán để tra cứu và gộp trùng đúng.

### 6.2. `Collectors.toUnmodifiableSet()` (Java 10+)

```java
var unique = java.util.List.of("An", "Binh", "An", "Chi")
        .parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

System.out.println(unique.size());          // 3
System.out.println(unique.contains("An")); // true
// unique.add("Du");                       // Ném UnsupportedOperationException
```

Collector này:

- Trả `Set` không cho sửa.
- **Không chấp nhận `null`.**
- Là **UNORDERED collector**; không bảo đảm thứ tự duyệt.
- Khi nhiều phần tử **bằng nhau** nhưng là các đối tượng riêng biệt, một đại diện **bất kỳ** được giữ; **không cam kết phần tử đầu tiên hay cuối cùng**.

Thực thi parallel có thể thay đổi cách các phần kết quả được hợp nhất; càng không được dùng `toUnmodifiableSet()` để chọn “record đầu tiên theo ID”. Nếu cần chọn đại diện theo nghiệp vụ, hãy giải quyết chính sách ấy trước khi tạo set.

### 6.3. Muốn giữ thứ tự xuất hiện và loại trùng? `LinkedHashSet`

```java
var words = java.util.List.of("B", "A", "B", "C");

var inEncounterOrder = words.parallelStream()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.LinkedHashSet::new));

System.out.println(inEncounterOrder); // [B, A, C]
```

`LinkedHashSet` giữ thứ tự chèn. `toCollection` tích lũy theo encounter order, vì nguồn là `List` có thứ tự. **Kết quả này mutable.** Nếu cần không cho sửa qua tham chiếu trả về nhưng vẫn giữ encounter order, có thể tạo bản copy `LinkedHashSet` riêng rồi bọc bằng `Collections.unmodifiableSet(...)`, không làm lộ backing set.

Chú ý: nếu nguồn không ordered, `LinkedHashSet` không thể tự khôi phục “thứ tự xuất hiện thật” không được nguồn cam kết.

### 6.4. Muốn tập được sắp theo comparator? `TreeSet`

```java
var sorted = java.util.List.of("B", "A", "B", "C")
        .parallelStream()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.TreeSet::new));

System.out.println(sorted); // [A, B, C]
```

`TreeSet` có thứ tự theo natural ordering của phần tử hoặc comparator; **mối quan hệ tương đương của comparator** quyết định phần tử nào được coi là trùng trong sorted set. Nếu comparator không nhất quán với `equals`, `TreeSet` có thể cho số phần tử khác `HashSet`/`toUnmodifiableSet`. Cần chọn comparator phản ánh đúng ý nghĩa nghiệp vụ.

## 7. Bảng so sánh collector khi tuần tự và song song

| Terminal/collector | Đặc điểm kết quả | Encounter order của nguồn `List` | Có bảo đảm sửa được? | `null` |
| --- | --- | --- | --- | --- |
| `collect(Collectors.toList())` | `List`; không cam kết implementation/mutability | **Giữ** ở cả tuần tự/song song | **Không cam kết** | Không có lệnh cấm `null` riêng trong collector |
| `collect(Collectors.toUnmodifiableList())` | `List` unmodifiable | **Giữ** ở cả hai | Không | **Từ chối** |
| `stream.toList()` | `List` unmodifiable, Java 16+ | **Giữ** ở cả hai | Không | **Cho phép** |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList` | **Giữ** ở cả hai | Có | `ArrayList` có thể chứa `null` |
| `collect(Collectors.toSet())` | `Set`, UNORDERED | **Không cam kết** thứ tự tập | **Không cam kết** | Không có lệnh cấm `null` riêng trong collector |
| `collect(Collectors.toUnmodifiableSet())` | `Set` unmodifiable, UNORDERED | **Không cam kết** thứ tự tập | Không | **Từ chối** |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet` | **Giữ encounter order** khi nguồn ordered | Có | `LinkedHashSet` có thể chứa `null` |
| `collect(Collectors.toCollection(TreeSet::new))` | `TreeSet` | Sắp theo natural order/comparator, không dựa vào encounter order | Có | Phụ thuộc comparator và kiểu; ví dụ natural-order `String` không chấp nhận `null` |

Dùng `Stream.toList()` và `Collectors.toUnmodifiableList()` theo **hợp đồng cụ thể**, không xem cả hai là alias hoàn toàn vì có khác biệt với `null`. Trong mọi hàng, “giữ encounter order” chỉ có ý nghĩa khi **nguồn stream có encounter order**.

## 8. Xử lý `null` và duplicate trong hai chế độ

### 8.1. `null` không liên quan chuyện stream có chạy song song hay không

```java
var input = java.util.Arrays.asList("A", null, "B");

var allowNull = input.parallelStream().toList();
System.out.println(allowNull.size());      // 3
System.out.println(allowNull.get(1) == null); // true
```

Nhưng:

```java
// Ném NullPointerException:
// input.parallelStream().collect(Collectors.toUnmodifiableList());
// input.parallelStream().collect(Collectors.toUnmodifiableSet());
```

Cả `toUnmodifiableList` và `toUnmodifiableSet` đều chặn `null` **ở cả tuần tự và song song**. Khi parallel, ngoại lệ có thể xuất hiện trong task khác rồi được truyền về terminal operation; đừng dựa vào thông báo, thứ tự hay vị trí phát hiện ngoại lệ.

Nếu dữ liệu phải loại `null` theo nghiệp vụ, lọc **trước** khi collect:

```java
var nonNull = input.parallelStream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(nonNull); // [A, B]
```

Việc lọc là chính sách của ứng dụng, không phải điều collector tự thực hiện.

### 8.2. Trùng phần tử: List giữ, Set gộp

```java
var input = java.util.List.of("A", "B", "A");

var asList = input.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());

var asSet = input.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

System.out.println(asList.size()); // 3
System.out.println(asSet.size());  // 2
```

Việc chạy parallel **không** có nghĩa `List` tự loại trùng, cũng không khiến `Set` cho phép trùng. Hai collector tuân thủ **các hợp đồng dữ liệu khác nhau**.

### 8.3. Các object riêng biệt nhưng `equals` bằng nhau

```java
record Key(String id) {}

var one = new Key("K-1");
var two = new Key("K-1");

var items = java.util.List.of(one, two);
System.out.println(items.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableList()).size()); // 2
System.out.println(items.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet()).size()); // 1
```

`record` có `equals/hashCode` dựa trên components (trong ví dụ `id` là `String`), được hỗ trợ trên Java 17+. Nếu muốn so sánh kiểu nghiệp vụ riêng, phải định nghĩa `equals/hashCode` phù hợp; collector không tự đoán business key.

## 9. Thu thập song song vào `ArrayList` có an toàn không?

**Có, khi dùng collector chuẩn đúng cách.** Ví dụ:

```java
var result = java.util.stream.IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));

System.out.println(result.size()); // 1000
```

`ArrayList` không phải concurrent collection, nhưng `Stream.collect(Collector)` có thể dùng nhiều container trung gian được tách biệt và kết hợp chúng. **Không cần** tự bọc `synchronizedList` chỉ vì đang gọi `parallelStream().collect(toCollection(ArrayList::new))`.

Khác hẳn là việc tự chia sẻ một `ArrayList` ngoài pipeline:

```java
// Ví dụ KHÔNG NÊN sử dụng:
var shared = new java.util.ArrayList<Integer>();
java.util.stream.IntStream.range(0, 1_000)
        .parallel()
        .forEach(shared::add);
```

Ở đây nhiều thread có thể đồng thời gọi `add` vào **cùng object shared** không được đồng bộ; đây là data race và có thể làm mất phần tử, hỏng dữ liệu hoặc gây lỗi. Đừng dùng kết quả một lần thử “vẫn đúng 1000 phần tử” để kết luận an toàn.

Cách đúng:

```java
var collected = java.util.stream.IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toList());
```

Hoặc, nếu cần chắc chắn một `ArrayList` có thể sửa:

```java
var collected = java.util.stream.IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
```

**Không nhầm lẫn** việc standard collector gom an toàn với tính thread-safe của **list trả về sau khi collect**. Nếu nhiều thread tiếp tục sửa chính list kết quả, bạn vẫn phải có thiết kế đồng bộ hóa phù hợp.

## 10. Hàm trung gian nên stateless và non-interfering

Framework có thể chia việc, thực hiện ở các thread hoặc thời điểm khác nhau. Các hàm trong `filter`, `map` và các thao tác trung gian nên:

- **Stateless:** không phụ thuộc trạng thái ngoài thay đổi theo quá trình xử lý.
- **Non-interfering:** không sửa nguồn stream khi pipeline đang chạy (trừ những trường hợp API nguồn có thiết kế đồng thời đặc biệt).
- **Có mục đích rõ ràng:** chỉ trả về/kiểm tra dữ liệu, không dùng side effect làm kết quả thay cho `collect`.

Ví dụ tốt:

```java
var upper = words.parallelStream()
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Nếu `words` là `List<String>` và không bị chỉnh sửa trong quá trình chạy, đây là phép biến đổi từng phần tử dễ suy luận và giữ encounter order.

Ví dụ sai về ý tưởng:

```java
// Không nên:
var external = new java.util.ArrayList<String>();
words.parallelStream()
        .map(s -> {
            external.add(s); // side effect vào shared mutable state
            return s.toUpperCase(java.util.Locale.ROOT);
        })
        .collect(java.util.stream.Collectors.toList());
```

Khi muốn cả output đầu vào lẫn output biến đổi, dùng collector riêng cho mỗi kết quả hoặc gọi `collect` từ các pipeline rõ ràng; đừng dựa vào side effect ngoài collector.

### `peek` và log

`peek(...)` có thể hữu ích cho chẩn đoán, nhưng không nên xây chức năng chính dựa vào thứ tự side effect của nó. Trong pipeline parallel, log từ các thread có thể xen kẽ; các optimization/lazy evaluation còn làm cho kỳ vọng “peek chắc chắn chạy đúng một lần cho mọi phần tử” không phải hợp đồng nên dựa vào.

## 11. `Collector.Characteristics` và thế nào là concurrent reduction?

Một số collector cho phép framework tích lũy đồng thời vào một result container chung khi an toàn. Điều này không xảy ra với mọi collector.

Ba characteristic thường gặp:

- **`CONCURRENT`:** accumulator có thể được gọi đồng thời trên cùng result container.
- **`UNORDERED`:** collector không cam kết phải bảo toàn encounter order.
- **`IDENTITY_FINISH`:** kết quả trung gian có thể dùng trực tiếp làm kết quả cuối theo ràng buộc của API.

Theo hợp đồng Stream, **concurrent reduction** chỉ phù hợp khi:

1. Stream chạy parallel.
2. Collector có `CONCURRENT`.
3. Stream là unordered **hoặc** collector có `UNORDERED`.

`Collectors.toList()` và `Collectors.toUnmodifiableList()` **không** được xem là concurrent collectors chỉ vì chúng chạy được với `parallelStream`. Chúng vẫn có thể được thực thi song song thông qua các partial containers và combiner.

`Collectors.toSet()` có đặc tính `UNORDERED` nhưng **`UNORDERED` không đồng nghĩa `CONCURRENT`**. Không nên sửa mã để chạy nhanh bằng cách tự cho nhiều thread đẩy vào một `HashSet` chung.

Với một số bài toán khác ngoài phạm vi danh sách/tập, Java có collector như `groupingByConcurrent`. Chúng có trade-off về order và concurrency; không nên thay collector chỉ vì muốn nhìn thấy tên “Concurrent” mà không xét yêu cầu thứ tự dữ liệu.

## 12. Giữ thứ tự khi cần, bỏ thứ tự khi có cơ sở

### Cần thứ tự List gốc

```java
var ids = java.util.List.of(5, 1, 3);
var output = ids.parallelStream()
        .map(id -> "id=" + id)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(output); // [id=5, id=1, id=3]
```

Phù hợp khi người dùng cần kết quả theo vị trí/đơn hàng/ưu tiên đầu vào.

### Không cần thứ tự, chỉ cần tập giá trị duy nhất

```java
var unique = ids.parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

System.out.println(unique.equals(java.util.Set.of(1, 3, 5))); // true
```

Không cần in `unique` rồi so sánh thứ tự; `Set.equals` so sánh phần tử theo hợp đồng tập hợp.

### Muốn bỏ ràng buộc thứ tự để hỗ trợ tối ưu hóa

```java
var unique = ids.parallelStream()
        .unordered()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

`unordered()` cho biết ứng dụng **không yêu cầu encounter order** cho đoạn pipeline còn lại. Điều này *có thể* giúp một số phép toán parallel giảm ràng buộc, nhưng **không bảo đảm tăng tốc** và cũng không khiến collector `toUnmodifiableSet` mang thứ tự duyệt xác định.

Nếu cần trả một `List` được sắp xếp, hãy dùng `sorted(...)` trước khi collect hoặc chỉ định bước sắp xếp sau khi thu thập. Đừng dùng `unordered()` nếu một bước phía sau thật sự phụ thuộc thứ tự encounter.

## 13. Song song có chắc nhanh hơn không?

**Không.** `parallelStream()` là một lựa chọn có đánh đổi:

- Chia việc, lên lịch task, tạo các partial containers và gộp kết quả có chi phí.
- Dữ liệu ít hoặc phép xử lý mỗi phần tử rất nhẹ có thể **chậm hơn** so với tuần tự.
- Collector có thứ tự (đặc biệt List) có thêm ràng buộc duy trì encounter order.
- Công việc liên quan I/O, khóa chung hoặc resource khan hiếm có thể không hưởng lợi; side effect còn tạo rủi ro đúng đắn.
- Tốc độ phụ thuộc kích thước input, Spliterator của nguồn, chi phí tính toán, số core và tải hệ thống.
- Trên server ứng dụng, nhiều pipeline parallel có thể cạnh tranh CPU/thread với các công việc khác.

Java không cam kết rằng `parallelStream()` sẽ dùng tối đa mọi core hoặc nhanh hơn tuần tự. Hãy **ưu tiên tính đúng**, rồi benchmark bài toán thực tế với JVM đã warm-up, input đại diện và độ biến động hợp lý (ví dụ dùng JMH cho microbenchmark). Không dựa vào một lần đo `System.nanoTime()` của ví dụ rất nhỏ để kết luận.

**Quy tắc thực dụng:** bắt đầu từ tuần tự cho code dễ hiểu; bật parallel khi dữ liệu/chi phí đủ lớn, phép xử lý độc lập, collector phù hợp và có số liệu đo chứng minh lợi ích.

## 14. Chương trình Java 17+ chạy độc lập và kết quả ổn định

Tạo tệp **`SequentialParallelCollectorsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class SequentialParallelCollectorsDemo {
    public static void main(String[] args) {
        var words = List.of("An", "Binh", "An", "Chi", "Binh");

        var sequentialList = words.stream()
                .collect(Collectors.toUnmodifiableList());
        var parallelList = words.parallelStream()
                .collect(Collectors.toUnmodifiableList());

        System.out.println("sequentialList=" + sequentialList);
        System.out.println("parallelList=" + parallelList);
        System.out.println("listsEqual=" + sequentialList.equals(parallelList));

        var sequentialSet = words.stream()
                .collect(Collectors.toUnmodifiableSet());
        var parallelSet = words.parallelStream()
                .collect(Collectors.toUnmodifiableSet());

        System.out.println("setsEqual=" + sequentialSet.equals(parallelSet));
        System.out.println("setSize=" + parallelSet.size());
        System.out.println("sortedSet=" + new TreeSet<>(parallelSet));

        var orderedSet = words.parallelStream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println("orderedSet=" + orderedSet);

        var editable = words.parallelStream()
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Du");
        System.out.println("editableLast=" + editable.get(editable.size() - 1));
        System.out.println("editableSize=" + editable.size());

        var numbers = IntStream.range(0, 100).boxed().toList();
        var sequentialSquares = numbers.stream()
                .map(n -> n * n)
                .collect(Collectors.toList());
        var parallelSquares = numbers.parallelStream()
                .map(n -> n * n)
                .collect(Collectors.toList());

        System.out.println("squaresEqual="
                + sequentialSquares.equals(parallelSquares));
        System.out.println("squareCount=" + parallelSquares.size());
        System.out.println("squareEndpoints=" + parallelSquares.get(0)
                + "," + parallelSquares.get(99));

        var even = IntStream.range(0, 10)
                .parallel()
                .filter(n -> n % 2 == 0)
                .boxed()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("even=" + even);

        var withNull = Arrays.asList("A", null, "B");
        var tolerantList = withNull.parallelStream().toList();
        System.out.println("streamToListNull="
                + (tolerantList.get(1) == null));

        try {
            withNull.parallelStream()
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            System.out.println("rejectListNull=true");
        }

        try {
            withNull.parallelStream()
                    .collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException expected) {
            System.out.println("rejectSetNull=true");
        }

        var filtered = withNull.parallelStream()
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("filtered=" + filtered);

        try {
            parallelList.add("Extra");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiableList=true");
        }

        var unique = words.parallelStream()
                .unordered()
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("unorderedEqual=" + unique.equals(
                Set.of("An", "Binh", "Chi")));

        System.out.println("parallelFlag="
                + words.parallelStream().isParallel());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 SequentialParallelCollectorsDemo.java
java SequentialParallelCollectorsDemo
```

**Kết quả stdout được xác định từ hợp đồng API (không phụ thuộc thứ tự Set):**

```text
sequentialList=[An, Binh, An, Chi, Binh]
parallelList=[An, Binh, An, Chi, Binh]
listsEqual=true
setsEqual=true
setSize=3
sortedSet=[An, Binh, Chi]
orderedSet=[An, Binh, Chi]
editableLast=Du
editableSize=6
squaresEqual=true
squareCount=100
squareEndpoints=0,9801
even=[0, 2, 4, 6, 8]
streamToListNull=true
rejectListNull=true
rejectSetNull=true
filtered=[A, B]
unmodifiableList=true
unorderedEqual=true
parallelFlag=true
```

### Phân tích từng nhóm

1. `sequentialList` và `parallelList` giữ encounter order của `words`. Phần tử trùng **không** bị loại khỏi List.
2. `toUnmodifiableSet` chỉ chứa ba chuỗi phân biệt. Vì không in trực tiếp set, output không phụ thuộc thứ tự không cam kết. `TreeSet` chỉ được dùng để **sắp xếp lúc hiển thị**.
3. `LinkedHashSet` do `toCollection` tạo giữ encounter order của danh sách nguồn dù thực thi song song.
4. `editable` chắc chắn là `ArrayList` được tạo bằng factory; có thể thêm phần tử sau thu thập.
5. `numbers` là list có encounter order từ `IntStream.range`; `toList` của stream tạo danh sách không sửa được. `Collectors.toList` ở nhánh bình phương vẫn phải giữ encounter order, nên hai kết quả bằng nhau.
6. `even` lọc số chẵn song song nhưng thứ tự list kết quả vẫn là `0, 2, 4, 6, 8`.
7. `Stream.toList()` giữ `null`, trong khi hai collector `toUnmodifiable...` từ chối `null`.
8. `unorderedEqual` so sánh theo **nội dung Set**, không theo thứ tự. `parallelFlag=true` nói về chế độ, không chứng minh số thread dùng trong phiên chạy.

## 15. Mẫu code lỗi và cách sửa

### Lỗi A: Tự dùng một `ArrayList` chung làm đích của `parallelStream().forEach`

```java
var output = new ArrayList<String>();
words.parallelStream().forEach(output::add); // Không an toàn
```

**Sửa:**

```java
var output = words.parallelStream()
        .collect(Collectors.toCollection(ArrayList::new));
```

Phân biệt collector quản lý các container trung gian với nhiều thread gọi `add` trực tiếp lên một object chung.

### Lỗi B: Coi `Collectors.toList()` mặc định mutable

```java
var result = words.stream().collect(Collectors.toList());
// result.add("Du"); // Không được cam kết sẽ luôn được hỗ trợ
```

**Sửa:** dùng `toCollection(ArrayList::new)` khi thực sự cần danh sách mutable, hoặc `toUnmodifiableList()` nếu muốn chắc chắn read-only.

### Lỗi C: Coi `parallelStream()` làm mất thứ tự ở mọi collector

```java
var result = List.of(1, 2, 3)
        .parallelStream()
        .collect(Collectors.toUnmodifiableList());
System.out.println(result); // [1, 2, 3]
```

**Sửa cách hiểu:** với collector list và nguồn ordered, encounter order vẫn được giữ. Thứ tự các thread làm việc có thể khác nhưng **kết quả logic vẫn theo nguồn**.

### Lỗi D: Coi `Collectors.toSet()` hoặc `toUnmodifiableSet()` có thứ tự cố định

```java
var set = words.parallelStream()
        .collect(Collectors.toUnmodifiableSet());
// Không so sánh set.toString() với "[An, Binh, Chi]".
```

**Sửa:** so sánh `Set.equals`/`contains`/`size`; khi cần order, dùng `LinkedHashSet` hoặc `TreeSet` tùy yêu cầu.

### Lỗi E: Coi `Collectors.toUnmodifiableList()` chấp nhận `null` giống `Stream.toList()`

```java
var source = Arrays.asList("A", null);
var accepted = source.parallelStream().toList(); // cho phép null
// source.parallelStream().collect(Collectors.toUnmodifiableList()); // NPE
```

**Sửa:** dùng API đúng với chính sách dữ liệu, hoặc lọc `null` tường minh nếu được phép bỏ dữ liệu.

### Lỗi F: `equals/hashCode` không nhất quán khi gộp Set

Nếu hai object bằng nhau theo `equals` nhưng có `hashCode` khác, class vi phạm hợp đồng Java; `HashSet`/collector `toSet` có thể gộp/tra cứu sai kỳ vọng. **Sửa:** định nghĩa cả `equals` và `hashCode` nhất quán trên field bất biến.

### Lỗi G: Dựa vào phần tử đại diện của tập unmodifiable

Hai record nghiệp vụ có cùng key theo `equals` nhưng khác payload có thể cho tập một phần tử. `toUnmodifiableSet()` không hứa giữ bản đầu tiên, cả tuần tự lẫn song song.

**Sửa:** nếu cần “first-wins”, “last-wins” hoặc “mới nhất”, chọn đại diện bằng quy tắc rõ trước khi tạo tập; tránh dùng collector set làm thuật toán chọn bản ghi.

### Lỗi H: Dùng `parallel()` khi mapper gây side effect ngoài

```java
var logs = new ArrayList<String>();
var result = words.parallelStream()
        .map(s -> {
            logs.add(s); // cạnh tranh thread / không an toàn
            return s.toUpperCase();
        })
        .collect(Collectors.toList());
```

**Sửa:** tách tác vụ, loại side effect và dùng `collect`/`map` thuần, hoặc một API concurrency được thiết kế riêng nếu yêu cầu bắt buộc chia sẻ trạng thái.

### Lỗi I: Chọn tốc độ thay cho correctness

Parallel có thể làm overhead lớn hơn với tập nhỏ hoặc làm code khó suy luận. **Sửa:** kiểm thử correctness của kết quả và benchmark trong workload thực tế trước khi bật parallel; không lấy ví dụ nhỏ làm số liệu hiệu năng.

## 16. Quy trình chọn collector và review trước khi bật parallel

1. **Xác định dữ liệu đầu vào có encounter order không.** Nguồn là `List`, mảng, `LinkedHashSet`, `HashSet` hay kết quả đã `sorted`/`unordered`?
2. **Cần giữ phần tử trùng không?** Cần thì dùng List; cần loại trùng theo `equals` thì chọn Set.
3. **Cần thứ tự đầu ra nào?** Encounter order, sorted order hay không quan trọng? Dùng `toUnmodifiableList`, `toCollection(LinkedHashSet::new)`, `toCollection(TreeSet::new)` đúng nhu cầu.
4. **Kết quả cần mutable không?** `toCollection(ArrayList::new)` cho list mutable; `toUnmodifiableList` và `toUnmodifiableSet` chặn sửa. `Collectors.toList/toSet` không cam kết mutability.
5. **Có phần tử `null` không?** Biết rõ khác biệt với `Stream.toList()`; làm sạch dữ liệu theo chính sách, không ngầm bỏ dữ liệu.
6. **Các object có `equals/hashCode` đúng không?** Đặc biệt khi set cần deduplicate.
7. **Mapper và filter có stateless, non-interfering không?** Đừng sửa nguồn hoặc shared container ngoài pipeline.
8. **Collector có đúng hợp đồng parallel không?** Với collector chuẩn Java, sử dụng theo API; nếu tự viết custom collector, phải thiết kế supplier/accumulator/combiner nhất quán.
9. **Kiểm tra nội dung bằng test xác định.** List ordered dùng `List.equals`; Set dùng `Set.equals` và size; đừng dựa vào thứ tự log hoặc `Set.toString()`.
10. **Đo hiệu năng sau khi đúng.** Dùng workload/benchmark đại diện; không giả định parallel luôn nhanh hơn.
11. **Cân nhắc memory và chi phí merging.** Một số collector và phép toán cần tạo nhiều container trung gian khi parallel.
12. **Bảo đảm kết quả sau collect được sử dụng đúng cách.** Parallel collection không tự bảo đảm thread safety nếu nhiều thread sau đó cùng sửa list/set đã trả.

## 17. Bài tập tự kiểm tra

**Câu 1.** Với `List.of("A","B","A")`, kết quả `toUnmodifiableList()` tuần tự và song song có cùng thứ tự không? Có trùng không?

**Câu 2.** Với cùng nguồn, `toUnmodifiableSet()` cho bao nhiêu phần tử? Có thể khẳng định thứ tự duyệt không?

**Câu 3.** Tại sao `parallelStream().collect(Collectors.toCollection(ArrayList::new))` an toàn hơn `parallelStream().forEach(sharedArrayList::add)`?

**Câu 4.** `Collectors.toList()` có cam kết trả về `ArrayList` mutable hay không?

**Câu 5.** `Collectors.toUnmodifiableList()` và `Stream.toList()` khác nhau thế nào khi stream chứa `null`?

**Câu 6.** Làm sao loại trùng theo `equals` nhưng vẫn duyệt theo thứ tự xuất hiện ban đầu của `List`?

**Câu 7.** Nếu nguồn là `HashSet`, chuyển từ stream tuần tự sang parallel có đảm bảo List kết quả có thứ tự tăng dần không?

**Câu 8.** `Collectors.toSet()` có đặc tính `UNORDERED`. Điều đó có nghĩa nó `CONCURRENT` và có thể tích lũy lên cùng `HashSet` không?

**Câu 9.** Vì sao `parallelStream()` không nhất thiết nhanh hơn `stream()` với 30 chuỗi ngắn?

**Câu 10.** Một test in `parallelSet.toString()` rồi so sánh chuỗi thứ tự cố định có bền vững không?

**Câu 11.** Nếu muốn xử lý dữ liệu ở nhiều thread nhưng giữ thứ tự phần tử trong list đích, bạn chọn collector nào?

**Câu 12.** Với hai object `equals` bằng nhau nhưng có metadata khác nhau, `toUnmodifiableSet()` có giữ object xuất hiện trước không?

**Đáp án:**

1. Có cùng encounter order `[A, B, A]` khi nguồn là `List` ordered; list vẫn giữ trùng.
2. Hai phần tử phân biệt; không có bảo đảm thứ tự duyệt.
3. Collector được Framework tổ chức các partial containers và combiner; `forEach` bên ngoài tạo concurrent write vào cùng một `ArrayList` không an toàn.
4. Không; Javadoc không cam kết implementation hoặc mutability.
5. `Stream.toList()` cho phép phần tử `null` và trả list unmodifiable; `toUnmodifiableList()` từ chối `null` bằng `NullPointerException`.
6. `collect(Collectors.toCollection(LinkedHashSet::new))` với nguồn ordered. Kết quả mặc định mutable.
7. Không. `HashSet` không cam kết encounter order; cần `sorted(...)` khi muốn thứ tự xác định.
8. Không. `UNORDERED` ≠ `CONCURRENT`. Không tự đưa các thread vào một `HashSet` chung.
9. Overhead scheduling/partition/combiner có thể lớn hơn chi phí xử lý dữ liệu nhỏ.
10. Không; `Set` collector không cam kết iteration order. Kiểm tra content bằng `Set.equals`, `contains` và `size`.
11. `Collectors.toUnmodifiableList()` hoặc `Collectors.toList()`, hoặc `toCollection(ArrayList::new)` nếu cần mutable; với nguồn có encounter order, ba cách đều phải bảo toàn order.
12. Không. Collector `toUnmodifiableSet()` có thể giữ bất kỳ một object đại diện; cần chính sách chọn riêng nếu metadata quan trọng.

## 18. Ghi nhớ và tài liệu Java hiện hành

- **Tuần tự/parallel là chế độ thực thi; nội dung và thứ tự kết quả phải tuân theo hợp đồng collector và nguồn stream.**
- Với **List collector**, nếu nguồn ordered thì kết quả giữ encounter order, dù các task chạy song song.
- Với **Set collector**, trùng được gộp và thứ tự duyệt không được cam kết. `toUnmodifiableSet()` còn có quy tắc chọn đại diện bất kỳ khi các object bằng nhau.
- **`Collectors.toUnmodifiableList()` và `toUnmodifiableSet()` có từ Java 10**, vẫn là API hiện hành; chúng không chấp nhận `null`.
- **`Stream.toList()` có từ Java 16**, trả List không sửa được nhưng cho phép `null`.
- `Collectors.toList()/toSet()` không cam kết mutability; dùng `toCollection(...)` khi cần loại collection cụ thể.
- `parallelStream().collect(collector)` an toàn với collector chuẩn ngay cả khi container tích lũy bình thường không thread-safe; khác hoàn toàn với việc tự chia sẻ mutable state qua `forEach` hoặc `map`.
- **Không dựa vào thứ tự log/thread, không mặc định parallel nhanh hơn**; test correctness trước, benchmark sau.

Nguồn chính thức (các quy tắc vẫn áp dụng):

1. [Java SE 27 – `Collectors`: `toList`, `toSet`, `toCollection`, `toUnmodifiableList`, `toUnmodifiableSet`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html): đặc điểm về encounter order, unmodifiable, null, duplicate và characteristics.
2. [Java SE 27 – `Stream.collect(Collector)` và `Stream.toList()`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): reduction song song và list output.
3. [Java SE 27 – `java.util.stream` package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html): ordering, non-interference, statelessness, reduction và concurrent collectors.
4. [Java SE 27 – `Collector`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collector.html): supplier/accumulator/combiner/finisher, các characteristic và ràng buộc reduction.
5. [Java SE 27 – `List`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): hợp đồng List và thứ tự phần tử.
6. [Java SE 27 – `Set`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): tính duy nhất phần tử và các unmodifiable set.
