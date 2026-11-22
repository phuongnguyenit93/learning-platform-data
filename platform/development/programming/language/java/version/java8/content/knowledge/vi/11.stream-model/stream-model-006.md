# Stream trong Java: Encounter order và thứ tự thực thi

**Encounter order** là thứ tự logic mà các phần tử của một `Stream` được xem là xuất hiện. **Thứ tự thực thi** là trình tự thực tế mà JVM gọi các thao tác `map`, `filter`, `peek` hoặc hành động ở terminal operation trên thread. Hai khái niệm này **không đồng nhất**, nhất là khi một stream được chạy song song.

Ví dụ, nguồn `List.of(3, 1, 2)` có encounter order là `3 → 1 → 2`. Một pipeline `parallelStream().map(x -> x * 10).toList()` vẫn tạo danh sách `[30, 10, 20]` theo encounter order, dù các lời gọi mapper có thể diễn ra trên nhiều thread và không theo chuỗi `3, 1, 2`.

Từ Java 8, Stream API phân biệt **ordering constraint** với **execution mode**. Những quy tắc này vẫn là nền tảng khi dùng Java 17+ và các JDK hiện đại:

- Stream **ordered** không bắt buộc mọi phần tử được *tính toán* lần lượt theo encounter order.
- Stream **parallel** không tự động làm mất encounter order của kết quả.
- `unordered()` không phải thao tác xáo trộn phần tử; nó loại bỏ yêu cầu giữ encounter order đối với những operation có thể tận dụng điều đó.
- `forEach()` không hứa giữ encounter order, kể cả đầu vào có thứ tự; `forEachOrdered()` giữ thứ tự khi stream có encounter order.
- `findFirst()` và `findAny()` có các contract khác nhau; `limit()`, `skip()`, `distinct()`, `sorted()` cũng chịu ảnh hưởng của ordering.
- **Không dùng thứ tự thực thi hoặc side effects trong lambda làm cơ sở xác định thứ tự kết quả** khi Stream API không bảo đảm điều đó.

Bài này trình bày cơ chế, ví dụ đúng/sai, lưu ý hiệu năng và chương trình Java 17+ chạy độc lập với stdout ổn định.

## 1. Encounter order được quyết định từ đâu?

Một stream có thể có hoặc không có **defined encounter order** tùy nguồn và các intermediate operations:

| Nguồn hoặc thao tác | Tình trạng encounter order | Ghi chú |
| --- | --- | --- |
| `List.stream()`, `List.parallelStream()` | Có | Thứ tự phần tử của List |
| `Arrays.stream(array)` | Có | Thứ tự phần tử theo chỉ số mảng |
| `IntStream.range(start,end)` | Có | Thứ tự giá trị tăng dần |
| `Stream.of(a,b,c)` | Có | Thứ tự các tham số được cung cấp |
| `LinkedHashSet.stream()` | Có | Thứ tự iterator do LinkedHashSet xác định |
| `TreeSet.stream()` | Có | Thứ tự do cấu trúc sorted set xác định |
| `HashSet.stream()` | Không có bảo đảm encounter order | Thứ tự quan sát được không phải contract |
| `Stream.generate(supplier)` | Không có | Nguồn vô hạn unordered theo đặc tả |
| `stream.unordered()` | Bỏ ràng buộc ordering | Không bắt buộc sắp xếp hoặc xáo trộn |
| `stream.sorted()` | Áp đặt thứ tự sắp xếp | Có thể dùng để tạo encounter order từ stream trước đó chưa ordered |

**Điểm tinh tế:** một lần lặp `HashSet` có thể *tình cờ* in kết quả theo một thứ tự quen thuộc. Điều đó **không biến HashSet thành ordered source**. Khi dữ liệu, hash, phiên bản JDK hoặc quá trình thực thi thay đổi, thứ tự có thể khác. Nếu cần order như một phần contract, dùng cấu trúc nguồn có order rõ ràng hoặc đưa một thao tác sắp xếp vào pipeline.

### Ví dụ đơn giản với List

```java
List<Integer> numbers = List.of(3, 1, 2);

List<Integer> mapped = numbers.stream()
        .map(x -> x * 10)
        .toList();

System.out.println(mapped); // [30, 10, 20]
```

Đây là **đoạn minh họa** cần `java.util.List`, đặt trong phương thức của một class. `List` xác định encounter order `[3,1,2]`, `map` tạo phần tử tương ứng mà không tự đổi order, còn `toList()` (từ Java 16) trả phần tử theo encounter order khi stream có thứ tự.

### Không phải List và Set đều giống nhau

```java
Set<String> names = new HashSet<>();
names.add("An");
names.add("Binh");
names.add("Chi");

// Không dự đoán một thứ tự cụ thể:
names.stream().forEach(System.out::println);
```

Đây là đoạn minh họa, cần import `java.util.Set`/`HashSet`. Có thể thấy một thứ tự ổn định trên máy đang chạy nhưng không được dựa vào nó như hợp đồng. Khi cần thứ tự có thể dự đoán, có thể sử dụng:

```java
List<String> sorted = names.stream().sorted().toList();
System.out.println(sorted); // [An, Binh, Chi]
```

Đây là minh họa nối tiếp, dùng cùng `names`. `sorted()` cho kết quả theo thứ tự tự nhiên của `String` bất kể encounter order trước đó của `HashSet`.

## 2. Thứ tự phần tử và thứ tự gọi mapper là hai trục độc lập

Với stream tuần tự:

```java
List<Integer> result = List.of(1, 2, 3).stream()
        .map(x -> x * 2)
        .toList();
```

Kết quả là `[2,4,6]`. Nhưng từ kết quả đó **không nên suy rằng Java có hợp đồng gọi mapper đúng một lần cho từng phần tử ở mọi pipeline khác**. Intermediate operations là lazy, các giai đoạn có thể được fusion, và một số pipeline có thể bị tối ưu hóa để không gọi mapper cho những phần tử không cần thiết.

Với stream song song:

```java
List<Integer> result = List.of(1, 2, 3).parallelStream()
        .map(x -> x * 2)
        .toList();

System.out.println(result); // [2, 4, 6]
```

Đây là minh họa. `parallelStream()` cho phép xử lý song song; nó không làm `List` tự mất encounter order. `toList()` vẫn giữ order của kết quả, mặc dù việc xử lý từng phần tử có thể được lập lịch khác nhau.

**Phân biệt bốn câu hỏi:**

1. **Thứ tự nguồn:** các phần tử có encounter order không?
2. **Ordering constraint của pipeline:** thao tác có giữ, tạo hoặc bỏ ràng buộc này?
3. **Execution mode:** pipeline đang tuần tự hay song song?
4. **Terminal operation:** kết quả/hành động cuối có hứa tôn trọng encounter order không?

Chỉ khi xét cả bốn mới kết luận đúng. Không được suy ra “parallel thì lộn xộn” hoặc “ordered thì lambda luôn chạy lần lượt”.

## 3. Stream là pipeline lazy, không phải vòng lặp thực thi tức thì

Tạo một pipeline thường **chưa xử lý toàn bộ phần tử ngay**:

```java
Stream<Integer> pipeline = List.of(1, 2, 3).stream()
        .filter(x -> x > 1)
        .map(x -> x * 10);

// Một terminal operation mới kích hoạt việc duyệt:
List<Integer> values = pipeline.toList();
System.out.println(values); // [20, 30]
```

Đây là minh họa, cần `java.util.stream.Stream` và `List`. Intermediate operations như `filter`, `map` mô tả pipeline; terminal operation như `toList` kích hoạt traversal cần thiết. Không được **tái sử dụng cùng Stream instance sau terminal operation** để bắt đầu một terminal operation thứ hai.

Một pipeline tuần tự có thể xử lý từng phần tử qua nhiều stage, thay vì chạy toàn bộ `filter` cho tất cả rồi mới chạy toàn bộ `map`. Một pipeline song song có thể phân chia công việc, phối hợp kết quả theo order yêu cầu, hoặc áp dụng các tối ưu hóa khác.

### Vì sao không dùng side effect để suy ra thứ tự?

```java
List<Integer> output = List.of(1, 2, 3).parallelStream()
        .map(x -> {
            System.out.println("mapping " + x);
            return x * 2;
        })
        .toList();
```

Đây là đoạn minh họa chỉ để chỉ ra vấn đề. `output` vẫn giữ encounter order `[2,4,6]`, nhưng **thứ tự các dòng `mapping ...` không được bảo đảm**. Logging từ mapper là tác dụng phụ; không thể coi nó là bằng chứng về thứ tự logic của stream.

Trong thực tế, hãy tách phần biến đổi dữ liệu khỏi logging/tác dụng phụ và test kết quả bằng giá trị, không bằng thứ tự console output từ mapper chạy song song.

## 4. forEach() không bảo đảm giữ encounter order

`forEach(Consumer)` là terminal operation. Theo contract, nó có hành vi **không xác định về thứ tự** với parallel streams; hành động có thể chạy trên bất kỳ thread/thời điểm nào phù hợp với thư viện. Ngay cả khi nguồn là ordered `List`, `forEach` không hứa duy trì encounter order.

```java
List.of("A", "B", "C").parallelStream()
        .forEach(System.out::println);
```

Đây là minh họa. Output có thể là `A,B,C` hoặc một hoán vị khác; **không đưa một stdout duy nhất làm đáp án đúng** cho đoạn này.

### forEachOrdered() khi thứ tự quan sát được là yêu cầu

```java
List.of("A", "B", "C").parallelStream()
        .forEachOrdered(System.out::println);
```

Với nguồn `List` ordered, các dòng được in:

```text
A
B
C
```

`forEachOrdered` thực hiện action theo encounter order khi stream có encounter order. Trong parallel execution, action đối với một phần tử **happens-before** action đối với phần tử kế tiếp. Tuy vậy, nó **không buộc mọi intermediate stage** như `map` hoặc `filter` đều chạy tuần tự/trên cùng một thread.

### Khi nào cần forEachOrdered?

- Bạn thực sự phải **thực hiện một tác vụ quan sát được theo thứ tự**, như tạo log có thứ tự từ danh sách events.
- Bạn không thể biểu diễn thao tác đó thành kết quả collection/reduction đơn giản.
- Bạn chấp nhận ràng buộc order có thể làm mất một phần lợi ích song song.

Nếu chỉ muốn một danh sách kết quả, **ưu tiên `map(...).toList()`** hoặc collector phù hợp thay vì dùng `forEachOrdered` để tự thêm vào list bên ngoài.

## 5. forEachOrdered không “tạo thứ tự” cho unordered stream

`forEachOrdered` chỉ hứa encounter order **nếu stream có defined encounter order**. Nó không tự sắp xếp một `HashSet` hay khôi phục order đã bỏ qua `unordered()`.

```java
Set<Integer> values = new HashSet<>(List.of(4, 1, 3, 2));
values.stream().forEachOrdered(System.out::println);
```

Đây là minh họa. Không được khẳng định các dòng in là `1,2,3,4`; không có defined encounter order từ `HashSet`.

Nếu cần ascending order, hãy khai báo rõ:

```java
values.stream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Đây là minh họa nối tiếp; kết quả được in `1` rồi `2`, `3`, `4`. `sorted()` tạo ràng buộc order theo comparator/natural order trước terminal operation.

## 6. unordered() thay đổi contract, không phải phép shuffle

`BaseStream.unordered()` làm pipeline **không còn bắt buộc giữ encounter order**. Nó không cam kết đổi vị trí phần tử hay random hóa dữ liệu. Trên một số pipeline, output sau `unordered()` vẫn **tình cờ** giống thứ tự đầu vào.

```java
List<Integer> values = List.of(9, 2, 7, 1);

// Không yêu cầu bảo toàn encounter order:
List<Integer> result = values.parallelStream()
        .unordered()
        .map(x -> x * 2)
        .toList();
```

Đây là minh họa. Các giá trị của kết quả vẫn tương ứng `18,4,14,2` theo phép ánh xạ, nhưng thứ tự danh sách **không còn được ràng buộc** theo encounter order nguồn. Đừng viết test bắt buộc `result.equals(List.of(18,4,14,2))`; hãy kiểm tra tập đa giá trị (multiset) hoặc sắp xếp nếu thứ tự không phải yêu cầu.

**Không đồng nghĩa với `Collections.shuffle`:** `unordered()` không yêu cầu tạo ngẫu nhiên một permutation mới. Nếu nghiệp vụ thực sự cần xáo trộn có kiểm soát, dùng thuật toán shuffle trên collection với seed thích hợp, không dùng Stream ordering flag để giả lập randomization.

### Khi nào dùng unordered()?

Chỉ khi bạn đã chứng minh thứ tự không quan trọng với kết quả, ví dụ:

- Tính tổng và những reduction giao hoán/kết hợp thích hợp.
- Lấy một phần tử bất kỳ thỏa điều kiện.
- Loại trùng mà không cần giữ phần tử xuất hiện đầu tiên.
- Thu thập vào tập hợp, nếu ứng dụng không yêu cầu iteration order.

Với pipeline song song có `distinct`, `limit`, `skip` hoặc một số collector concurrent, bỏ ràng buộc order có thể giúp cải thiện hiệu suất. Đó **không phải bảo đảm tăng tốc**; nên benchmark trên dữ liệu và máy thật.

## 7. findFirst() khác findAny() ở hợp đồng lựa chọn

Hai terminal operations đều trả `Optional<T>` và đều là short-circuiting, nhưng ý nghĩa khác nhau.

### findFirst: phần tử đầu theo encounter order

```java
List<Integer> numbers = List.of(8, 3, 5);

int first = numbers.parallelStream()
        .findFirst()
        .orElseThrow();

System.out.println(first); // 8
```

Đây là minh họa. Dù pipeline là parallel, `findFirst()` trên ordered `List` phải tìm **phần tử đầu theo encounter order**.

Sau `filter`:

```java
int firstOdd = numbers.parallelStream()
        .filter(x -> x % 2 != 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstOdd); // 3
```

Trong ordered source, filter giữ thứ tự tương đối của các phần tử còn lại. Vì vậy `3` là phần tử lẻ đầu tiên trong encounter order, không phải “phần tử được thread đầu tiên tính xong”.

### findAny: một phần tử hợp lệ bất kỳ

```java
int any = numbers.parallelStream()
        .findAny()
        .orElseThrow();
```

Đây là minh họa; `any` có thể là `8`, `3` hoặc `5`. Đặc tả **cố ý không bảo đảm** cùng một giá trị giữa các lần gọi. Với stream tuần tự, một implementation có thể thường trả phần tử đầu, nhưng đó không phải hợp đồng để test.

Nếu thứ tự không quan trọng, `findAny()` diễn đạt đúng ý hơn và có thể cho phép tối ưu hóa khi chạy song song. Nếu nghiệp vụ đòi bản ghi đầu tiên, dùng `findFirst()` trên stream có encounter order rõ ràng.

### Không dùng findFirst để định nghĩa “đầu tiên” trên HashSet

Với unordered source, `findFirst()` cũng có thể chọn bất kỳ phần tử nào; vì stream **không có phần tử đầu xác định theo encounter order**. Khi cần phần tử nhỏ nhất hoặc ưu tiên cao nhất, dùng `min(comparator)` hoặc `sorted().findFirst()` nếu phù hợp dữ liệu, không dựa vào cấu trúc nguồn unordered.

## 8. limit() và skip(): order làm thay đổi lựa chọn

`limit(n)` là stateful, short-circuiting intermediate operation. `skip(n)` cũng là stateful intermediate operation. Với **ordered stream**:

- `limit(n)` lấy tối đa **n phần tử đầu tiên** theo encounter order.
- `skip(n)` loại bỏ **n phần tử đầu tiên** theo encounter order.

```java
List<Integer> values = List.of(5, 1, 4, 2, 3);

System.out.println(values.stream().limit(3).toList());
System.out.println(values.stream().skip(2).toList());
```

Kết quả xác định:

```text
[5, 1, 4]
[4, 2, 3]
```

Khi nguồn có order, pipeline parallel vẫn phải tôn trọng những ngữ nghĩa này. Chính vì vậy, `limit`/`skip` có thể đắt hơn khi stream song song: hệ thống phải nhận diện **đúng prefix** hoặc đúng phần tử cần bỏ qua, không thể tùy tiện lấy những phần tử thread xử lý nhanh nhất.

### Với unordered stream

```java
List<Integer> sample = values.parallelStream()
        .unordered()
        .limit(3)
        .toList();
```

Đây là minh họa. Không hứa `sample` là `[5,1,4]`. Nếu nguồn có đủ dữ liệu, `limit(3)` vẫn ràng buộc số lượng tối đa là 3 và với nguồn hữu hạn đủ phần tử thường lấy 3, nhưng **không phải ba phần tử đầu của List** sau khi bạn đã bỏ ordering constraint. Cần thiết kế test theo **số lượng/tính hợp lệ**, không theo thứ tự nguồn.

**Ghi nhớ:** `unordered` không phải cách tăng tốc hợp lệ nếu business logic cần lấy 100 giao dịch **đầu tiên theo thời gian**. Khi đó cần giữ ordering theo thời gian hoặc chọn thuật toán dữ liệu thích hợp.

## 9. distinct(): giữ phần tử xuất hiện trước hay không?

`distinct()` dùng `Object.equals` để loại các phần tử trùng. Với **ordered stream**, operation này **stable**: khi có nhiều phần tử bằng nhau, phần tử xuất hiện trước theo encounter order được giữ.

```java
List<Integer> ids = List.of(4, 2, 4, 1, 2, 3);

List<Integer> unique = ids.stream()
        .distinct()
        .toList();

System.out.println(unique); // [4, 2, 1, 3]
```

Đây là minh họa. Nếu chạy `ids.parallelStream().distinct().toList()`, contract giữ encounter order vẫn áp dụng; thứ tự kết quả tương ứng vẫn là `[4,2,1,3]`.

### Vì sao unordered có thể nhanh hơn?

Với stream song song, bảo toàn tính stable trong `distinct` có thể cần **đồng bộ/đệm dữ liệu** đáng kể. `unordered().distinct()` có thể được thực hiện hiệu quả hơn nếu không cần giữ phần tử đầu.

```java
Set<Integer> uniqueSet = ids.parallelStream()
        .unordered()
        .collect(Collectors.toSet());
```

Đây là minh họa cần import `Set` và `Collectors`. Nó lấy **tập giá trị** không trùng, nhưng `Collectors.toSet()` không cam kết iteration order. Không in trực tiếp tập đó rồi so một thứ tự stdout cố định trong unit test.

**Lưu ý đối tượng thực:** hai objects có thể `equals` bằng nhau nhưng khác metadata không tham gia `equals`. Với ordered `distinct`, phần tử đầu tiên trong encounter order là đối tượng được giữ; sau `unordered()`, không được kỳ vọng giữ cùng object representative. Nếu cần quy tắc chọn “bản mới nhất”, phải biểu diễn bằng comparator/reduction có định nghĩa rõ ràng, không dùng `distinct` tùy ý.

## 10. sorted(): áp đặt order, còn stable sort phụ thuộc nguồn

`sorted()` tạo stream theo thứ tự tự nhiên hoặc theo `Comparator`. Với ordered stream, sort là **stable**: các phần tử mà comparator xem là bằng nhau duy trì thứ tự tương đối ban đầu. Với unordered stream, **không có bảo đảm stable** cho các phần tử có cùng key sắp xếp.

```java
List<String> names = List.of("bbb", "a", "cc");

List<String> byLength = names.stream()
        .sorted(Comparator.comparingInt(String::length))
        .toList();

System.out.println(byLength); // [a, cc, bbb]
```

Đây là minh họa cần `java.util.Comparator`. Mặc dù `sorted` có thể dùng trong parallel pipeline, thứ tự logical result vẫn do comparator quyết định. **Không kết luận mapper và comparator đã được gọi tuần tự chỉ từ danh sách đã sắp xếp.**

### Stable sorting với ties

```java
record Item(String code, int rank) {}

List<Item> input = List.of(
        new Item("A", 1),
        new Item("B", 1),
        new Item("C", 2));

List<String> codes = input.stream()
        .sorted(Comparator.comparingInt(Item::rank))
        .map(Item::code)
        .toList();

System.out.println(codes); // [A, B, C]
```

Đây là đoạn minh họa cần đặt trong class/method hợp lệ; `record` là tính năng ổn định từ Java 16. Hai item `A` và `B` có `rank=1` nên, với ordered source, stable sort giữ `A` trước `B`. Nếu bỏ encounter order trước `sorted`, comparator ties không còn được bảo đảm giữ thứ tự cũ. Khi muốn thứ tự **tất định kể cả ties**, dùng comparator bổ sung khóa phân biệt:

```java
Comparator<Item> order = Comparator.comparingInt(Item::rank)
        .thenComparing(Item::code);
```

Đây là minh họa. Lúc ấy comparator quyết định rõ `A` trước `B` ngay cả khi stream ban đầu không ordered.

## 11. map(), filter(), flatMap(): thứ tự logic không phải thứ tự gọi lambda

Các intermediate operations `map` và `filter` không tự loại bỏ encounter order của stream. Với ordered source, kết quả cuối cùng khi được thu thập bằng terminal operation tôn trọng order sẽ giữ vị trí tương đối:

```java
List<String> words = List.of("ab", "x", "java");

List<Integer> lengths = words.parallelStream()
        .filter(s -> s.length() >= 2)
        .map(String::length)
        .toList();

System.out.println(lengths); // [2, 4]
```

Đây là minh họa. Dù `filter`/`map` có thể được gọi ngoài thứ tự hoặc trên các thread khác nhau, danh sách kết quả theo encounter order vẫn là `[2,4]`.

### flatMap với thứ tự lồng nhau

```java
List<String> result = List.of("A", "B").parallelStream()
        .flatMap(x -> Stream.of(x + "1", x + "2"))
        .toList();

System.out.println(result); // [A1, A2, B1, B2]
```

Đây là minh họa, cần `java.util.stream.Stream`. Nguồn ngoài là ordered `[A,B]` và mỗi inner `Stream.of(...)` cũng ordered. `flatMap` tạo chuỗi logic các phần tử của inner streams theo encounter order của outer stream; `toList` bảo toàn thứ tự đó. Không suy từ đó rằng toàn bộ code tạo inner streams được thực thi lần lượt theo timeline.

### Side effects trong map là anti-pattern

```java
List<Integer> output = new ArrayList<>();

// KHÔNG NÊN: shared mutable list + parallel forEach.
List.of(1, 2, 3).parallelStream()
        .map(x -> x * 2)
        .forEach(output::add);
```

Đây là đoạn minh họa **có vấn đề**, cần `ArrayList`; `ArrayList` không thread-safe, nên việc thêm đồng thời gây data race/race condition hoặc kết quả sai. Ngay cả khi thay bằng synchronized list, thứ tự các `add` vẫn không nhất thiết là encounter order.

Phiên bản đúng, ngắn hơn:

```java
List<Integer> output = List.of(1, 2, 3).parallelStream()
        .map(x -> x * 2)
        .toList();
```

Đoạn minh họa trả `[2,4,6]` và không quản lý shared mutable state.

## 12. forEachOrdered có bảo đảm mapper chạy một lần, tuần tự không?

**Không.** `forEachOrdered` chỉ đưa ra ordering contract cho **terminal action**. Nó không biến `parallelStream` thành `stream`, cũng không đảm bảo từng `map`/`filter` stage gọi đúng một lần đối với mỗi phần tử nguồn trong mọi pipeline.

```java
List.of(1, 2, 3).parallelStream()
        .map(x -> {
            // Việc tính toán có thể thực hiện song song.
            return x * 2;
        })
        .forEachOrdered(System.out::println);
```

Đoạn minh họa sẽ in `2`, `4`, `6` theo dòng, nhưng trình tự/cách phân thread cho mapper không được suy ra từ thứ tự terminal action. Do đó, đừng dùng `forEachOrdered` để “chữa” một pipeline chứa mutation nguy hiểm trong `map`.

## 13. peek() không phải công cụ đảm bảo thực thi

`peek` chủ yếu hữu ích để quan sát/debug một pipeline; nó là **intermediate operation**, không phải một terminal operation.

```java
List<Integer> values = List.of(1, 2, 3).stream()
        .peek(x -> System.out.println("seen " + x))
        .toList();
```

Đây là đoạn minh họa. Mặc dù khi chạy nhiều implementation có thể in các dòng quan sát được, **không nên dùng peek như contract thực thi side effect**. Stream implementation được phép tối ưu hóa để tránh evaluation của một số giai đoạn khi điều đó không ảnh hưởng kết quả của terminal operation. Ví dụ `count()` trên nguồn đã biết kích thước có thể không cần gọi `peek` hoặc `map`.

Đây là lý do phải tách **biến đổi có kết quả** và **tác dụng phụ bắt buộc** thành hai công việc rõ ràng. Nếu nghiệp vụ thật sự yêu cầu gọi một hành động trên từng phần tử, hãy chọn một terminal operation thích hợp hoặc dùng vòng lặp dễ quan sát và kiểm soát.

## 14. reduce(), collect() và thứ tự kết hợp

Một phép reduction đúng cho parallel stream cần tuân theo contract của operator/collector. Với `reduce`, phép tích lũy phải có tính **associative** theo quy tắc liên quan, có identity tương thích và không can thiệp nguồn.

```java
int sum = IntStream.rangeClosed(1, 5)
        .parallel()
        .sum();

System.out.println(sum); // 15
```

Đây là minh họa cần `java.util.stream.IntStream`. Phép cộng số nguyên ở ví dụ này cho kết quả xác định. Chạy song song có thể chia mảng công việc và kết hợp tổng theo cấu trúc khác mà vẫn cho `15`.

### Không dùng operator không associative cho parallel reduce

```java
int result = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, (left, right) -> left - right);
```

Đây là **ví dụ không nên dùng**. Phép trừ không associative: cách nhóm khác nhau có thể cho kết quả khác. Nếu muốn “lấy phần tử đầu trừ lần lượt phần còn lại”, cần một thuật toán tuần tự rõ ràng; đừng dùng parallel reduction sai contract.

### Collector nào giữ order?

`Stream.toList()` (từ Java 16) bảo toàn encounter order nếu stream ordered và trả một `List` **unmodifiable**. Với `Collectors.toList()`, result được thu thập theo encounter order nhưng **không được bảo đảm** về implementation type hoặc khả năng sửa theo contract; đừng mặc định nó phải là một `ArrayList` có thể sửa.

Nếu cần một `ArrayList` mutable theo order:

```java
List<Integer> mutable = List.of(1, 2, 3).parallelStream()
        .collect(Collectors.toCollection(ArrayList::new));
```

Đây là minh họa cần `Collectors` và `ArrayList`. `toCollection(ArrayList::new)` tạo collection loại mong muốn và với ordered stream thì thứ tự phần tử được bảo toàn. Phần thực thi song song quản lý containers trung gian; **không** đồng nghĩa với việc nhiều threads cùng gọi `add` vào một `ArrayList` do code ứng dụng tự chia sẻ.

### Map collectors và iteration order

`Collectors.toMap` và `Collectors.groupingBy` không hứa iteration order của resulting `Map` nếu bạn không chọn nhà cung cấp Map/order rõ ràng. Dù stream đầu vào ordered, không kết luận `map.keySet()` sẽ có cùng order như source.

Nếu key insertion order là yêu cầu cụ thể trong một use case, chọn collector có supplier `LinkedHashMap::new` và định nghĩa cách merge rõ. Với parallel collectors, vẫn phải xem contract của collector và các ràng buộc ordering để xác định kết quả, không dựa vào hành vi thấy tình cờ trên một JVM.

## 15. Concurrent collectors và đánh đổi ordering

Một số collectors hỗ trợ concurrent reduction, như `groupingByConcurrent`. Khi thực hiện concurrent accumulation, ứng dụng phải hiểu rằng thứ tự chèn phần tử vào các collection con hoặc thứ tự duyệt map không nhất thiết theo encounter order.

```java
ConcurrentMap<Integer, List<String>> grouped =
        List.of("A", "BB", "C").parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        String::length));
```

Đây là **đoạn minh họa**, cần import `java.util.concurrent.ConcurrentMap`, `java.util.List` và `Collectors`. Kết quả có nhóm khóa `1` và `2` với các giá trị phù hợp, nhưng không xây test yêu cầu thứ tự iteration của `ConcurrentMap` hay thứ tự phần tử trong từng nhóm tuân theo `[A,C]`.

Nếu business logic cần **thứ tự phần tử trong nhóm** hoặc thứ tự các nhóm khi xuất báo cáo, hãy dùng cấu trúc/collector và bước sắp xếp có contract cụ thể. Không dùng concurrent collector chỉ vì input là parallel; đo kết quả và hiệu suất.

## 16. short-circuit: không hứa xử lý hết mọi phần tử

Các terminal operations như `anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny` có thể **dừng sớm** khi xác định kết quả. Intermediate operations như `limit` hoặc `takeWhile` có semantics short-circuiting riêng.

```java
boolean exists = List.of(1, 2, 3, 4).stream()
        .anyMatch(x -> x > 2);

System.out.println(exists); // true
```

Đây là minh họa. Không được khẳng định predicate được gọi với cả `1,2,3,4` đúng một lần. Khi chạy parallel, một số công việc có thể đã được lập lịch cùng lúc dù kết quả cuối có thể kết thúc sớm. Đây là một lý do khác để **giữ mapper/predicate không có side effect bắt buộc**.

### Stream.count() có thể tối ưu hóa

Trên nguồn có kích thước biết trước và pipeline cho phép suy kích thước trực tiếp, `count()` có thể trả số lượng mà không cần duyệt tất cả phần tử. Vì vậy, code như `stream.peek(sendEmail).count()` không phải cách chắc chắn để gửi email cho mọi phần tử; kết quả count đúng không chứng minh peek đã được gọi.

## 17. takeWhile() và dropWhile(): prefix phụ thuộc encounter order

`takeWhile` và `dropWhile` là operations được chuẩn hóa từ Java 9. Với ordered stream:

- `takeWhile(predicate)` giữ **prefix dài nhất** gồm các phần tử liên tiếp từ đầu còn thỏa predicate.
- `dropWhile(predicate)` bỏ **prefix dài nhất** thỏa predicate, rồi giữ phần còn lại.

```java
List<Integer> values = List.of(2, 4, 5, 6, 8);

System.out.println(values.stream()
        .takeWhile(x -> x % 2 == 0).toList());
System.out.println(values.stream()
        .dropWhile(x -> x % 2 == 0).toList());
```

Kết quả xác định:

```text
[2, 4]
[5, 6, 8]
```

Điểm mấu chốt là `takeWhile` **không tương đương `filter`**. `filter(x -> even)` sẽ giữ `2,4,6,8`, còn `takeWhile` dừng prefix khi gặp `5`.

Trên **unordered stream**, không có ý nghĩa prefix xác định theo encounter order. Theo contract, `takeWhile` có thể lấy một subset hợp lệ từ các phần tử thỏa predicate; `dropWhile` có thể bỏ một subset hợp lệ. Đừng dùng `unordered().takeWhile(...)` như một cách biểu diễn “lấy các phần tử đầu tiên” theo thứ tự dữ liệu ban đầu.

## 18. Parallel stream không tự đảm bảo nhanh hơn

Bật `parallel()` hoặc dùng `parallelStream()` cho phép stream pipeline thực thi song song, nhưng không cam kết được cấp nhiều threads, không cam kết thứ tự completion, cũng **không cam kết tăng tốc**.

Hiệu quả phụ thuộc:

- Kích thước dữ liệu, chi phí mỗi phần tử và khả năng tách nguồn.
- Mức contention, allocation, boxing và locality của bộ nhớ.
- Stateful operations: `sorted`, ordered `distinct`, `limit`, `skip` và `takeWhile` có thể có chi phí đồng bộ/đệm.
- Side effects: I/O, khóa, truy cập shared state hoặc external services có thể làm pipeline chậm và khó dự đoán.
- Các tác vụ khác cùng dùng tài nguyên parallel execution.

### Khi nào giữ sequential?

- Dữ liệu ít, phép tính rẻ.
- Phải tương tác theo thứ tự với hệ thống ngoài.
- Cần debug đơn giản hoặc semantics tuần tự rõ ràng.
- Pipeline có nhiều stateful ordered operations khiến parallel overhead đáng kể.
- Không có benchmark cho thấy parallel đáng giá.

### Khi nào cân nhắc parallel?

- Dữ liệu đủ lớn, nguồn dễ chia.
- Per-element computation tương đối nặng, pure/stateless/non-interfering.
- Reduction hỗ trợ kết hợp đúng.
- Có benchmark và test tính đúng trên những điều kiện xử lý phù hợp.

Không nên tự bật `unordered()` chỉ để tối ưu nếu business requirement thực chất phụ thuộc thứ tự; có thể đổi semantics mà test không phát hiện ngay.

## 19. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây tách **ordering logic** khỏi **thứ tự tính toán**, chỉ in những đầu ra có thể dự đoán. Không dùng `parallel forEach` để tạo stdout ngẫu nhiên.

Lưu toàn bộ vào **StreamEncounterOrderDemo.java**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class StreamEncounterOrderDemo {

    public static void main(String[] args) {
        List<Integer> source = List.of(4, 1, 3, 2, 3);

        List<Integer> mapped = source.parallelStream()
                .map(x -> x * 10)
                .toList();
        System.out.println("source=" + source);
        System.out.println("parallelMap=" + mapped);

        System.out.println("distinct=" +
                source.parallelStream().distinct().toList());

        System.out.println("sortedDistinct=" +
                source.parallelStream().sorted().distinct().toList());

        System.out.println("first=" +
                source.parallelStream().findFirst().orElseThrow());

        System.out.println("firstSorted=" +
                source.parallelStream().sorted()
                        .findFirst().orElseThrow());

        System.out.println("skipLimit=" +
                source.parallelStream().skip(1).limit(3).toList());

        List<String> words = List.of("bbb", "a", "cc");
        System.out.println("byLength=" +
                words.parallelStream()
                        .sorted(Comparator.comparingInt(String::length))
                        .toList());

        int sum = IntStream.rangeClosed(1, 5)
                .parallel().unordered().sum();
        System.out.println("unorderedSum=" + sum);

        Set<Integer> unique = source.parallelStream()
                .unordered()
                .collect(Collectors.toSet());
        System.out.println("uniqueCount=" + unique.size());

        List<Integer> prefix = List.of(2, 4, 5, 6, 8)
                .parallelStream()
                .takeWhile(x -> x % 2 == 0)
                .toList();
        System.out.println("takeWhile=" + prefix);

        List<Integer> suffix = List.of(2, 4, 5, 6, 8)
                .parallelStream()
                .dropWhile(x -> x % 2 == 0)
                .toList();
        System.out.println("dropWhile=" + suffix);

        System.out.print("forEachOrdered=");
        source.parallelStream()
                .forEachOrdered(x -> System.out.print(x + " "));
        System.out.println();
    }
}
```

Lệnh biên dịch và chạy, dùng JDK 17 trở lên:

```bash
javac StreamEncounterOrderDemo.java
java StreamEncounterOrderDemo
```

**Stdout xác định:**

```text
source=[4, 1, 3, 2, 3]
parallelMap=[40, 10, 30, 20, 30]
distinct=[4, 1, 3, 2]
sortedDistinct=[1, 2, 3, 4]
first=4
firstSorted=1
skipLimit=[1, 3, 2]
byLength=[a, cc, bbb]
unorderedSum=15
uniqueCount=4
takeWhile=[2, 4]
dropWhile=[5, 6, 8]
forEachOrdered=4 1 3 2 3 
```

*Lưu ý:* dòng cuối có **một dấu cách sau số `3`**, vì lambda in `x + " "` trước khi gọi `println()`. Đây là khác biệt nhỏ nhưng cần giữ nếu kiểm tra stdout exact.

### Giải thích theo từng nhóm

1. **`parallelMap`**: pipeline parallel nhưng `toList` giữ encounter order của `source`; không cam kết mapper được gọi theo thứ tự nguồn.
2. **`distinct`**: trên ordered List, operation giữ phần tử đầu tiên theo encounter order cho mỗi giá trị, nên `[4,1,3,2]`.
3. **`sortedDistinct`**: `sorted` đặt thứ tự tự nhiên `[1,2,3,3,4]` trước khi loại trùng; kết quả `[1,2,3,4]`.
4. **`findFirst`**: phần tử đầu theo nguồn là `4`, dù chạy song song.
5. **`firstSorted`**: phần tử đầu sau sorting là `1`.
6. **`skipLimit`**: bỏ phần tử đầu `4` rồi lấy ba phần tử `1,3,2` theo order.
7. **`byLength`**: sắp xếp `a` (1), `cc` (2), `bbb` (3) bằng comparator.
8. **`unorderedSum`**: bỏ ordering constraint nhưng tính tổng không phụ thuộc thứ tự; giá trị là `15`.
9. **`uniqueCount`**: chỉ kiểm tra số phần tử duy nhất; không in trực tiếp Set vì thứ tự iteration không được bảo đảm.
10. **`takeWhile`/`dropWhile`**: lấy hoặc bỏ prefix chẵn `2,4` trước phần tử lẻ `5`.
11. **`forEachOrdered`**: terminal action in các phần tử theo encounter order của source List, dù stream là parallel.

Chương trình dùng API hiện đại: `Stream.toList()` từ Java 16, `takeWhile`/`dropWhile` từ Java 9, còn ordering semantics của Stream có từ Java 8 và vẫn được duy trì. Không sử dụng hành vi đã lỗi thời hoặc chi tiết triển khai nội bộ để suy ra kết quả.

## 20. Thử nghiệm hành vi không xác định mà không viết test sai

Để quan sát sự khác biệt giữa thứ tự logic và thứ tự thực thi, có thể chạy đoạn sau riêng biệt:

```java
List.of(1, 2, 3, 4, 5).parallelStream()
        .forEach(x -> System.out.print(x + " "));
```

Đây là đoạn minh họa, **không có một stdout duy nhất được bảo đảm**. Việc quan sát `1 2 3 4 5` ở một lần chạy cũng không chứng minh `forEach` có contract về order. Dùng đoạn này để khám phá, không dùng để chứng minh kết quả chương trình chính.

Một kiểm thử đúng khi kết quả không có order:

```java
List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
        .unordered()
        .map(x -> x * 2)
        .toList();

List<Integer> sorted = result.stream().sorted().toList();
System.out.println(sorted); // [2, 4, 6, 8]
```

Đây là đoạn minh họa; kiểm tra **multiset qua sắp xếp** thay vì kiểm tra thứ tự không được bảo đảm. Với dữ liệu có phần tử trùng, so sánh sorted lists (gồm cả tần suất) thích hợp hơn so sánh sets vì set bỏ mất số lần xuất hiện.

### Kiểm thử không nên dựa vào tên thread

Ngay cả khi parallel pipeline dùng nhiều thread, tên thread, số lượng thread và cách phân công phần tử là chi tiết thực thi. Không viết bài test như “`map(1)` phải chạy trên worker-1” hoặc “`map(2)` luôn chạy trước `map(3)`”. Test cần dựa trên hợp đồng của Stream API, không dựa vào scheduler.

## 21. Bảng quyết định: chọn operation theo yêu cầu

| Yêu cầu | Operation hoặc cấu trúc phù hợp | Lưu ý |
| --- | --- | --- |
| Biến đổi dữ liệu và giữ thứ tự của List | `map(...).toList()` | Kể cả parallel, nếu pipeline còn ordered |
| In/gửi hành động theo thứ tự của List | `forEachOrdered(...)` | Terminal action được ordered; intermediate stages không nhất thiết |
| Thực hiện một hành động trên mọi phần tử, không cần thứ tự | `forEach(...)` | Side effects phải thread-safe nếu chạy parallel |
| Lấy bản ghi đầu tiên theo encounter order | `findFirst()` | Nguồn phải có order xác định |
| Lấy bất kỳ bản ghi phù hợp | `findAny()` | Không kiểm tra một giá trị cố định |
| Lấy n phần tử đầu | `limit(n)` trên ordered stream | Parallel có thể tốn chi phí |
| Bỏ n phần tử đầu | `skip(n)` trên ordered stream | Chỉ có ý nghĩa đầu khi có order |
| Loại trùng, giữ đại diện đầu tiên | `distinct()` trên ordered stream | Có thể đắt trên parallel |
| Sắp xếp có tie-breaker ổn định | `sorted(comparator)` | Dùng comparator đủ khóa |
| Tính tổng không phụ thuộc thứ tự | `sum()` hoặc associative reduce | Tránh side effects |
| Thu thập set không quan tâm order | `Collectors.toSet()` | Set iteration order không có guarantee |
| Nhóm kết quả song song, không cần thứ tự nhóm | `groupingByConcurrent` | Hiểu unordered/concurrent collector |
| Lấy prefix đáp ứng điều kiện | `takeWhile` trên ordered stream | Khác `filter` |
| Muốn bỏ ordering constraint để benchmark | `unordered()` | Chỉ khi semantics cho phép |

## 22. Các nhầm lẫn điển hình

### Nhầm lẫn 1: “parallelStream() luôn trả danh sách lộn xộn”

**Sai.** Với ordered source và terminal operation bảo toàn order như `toList()`, kết quả vẫn theo encounter order. Việc tính toán là chuyện khác.

### Nhầm lẫn 2: “stream() luôn đảm bảo mọi tác dụng phụ xảy ra đúng thứ tự”

**Không nên suy ra vậy.** Hợp đồng Stream API tập trung vào kết quả và những bảo đảm cụ thể của từng operation; tối ưu hóa hoặc short-circuit có thể bỏ qua việc gọi các lambda khi không cần. Đừng biến `peek` thành cơ chế bảo đảm gửi thông báo.

### Nhầm lẫn 3: “unordered() xáo trộn dữ liệu để random”

**Sai.** Nó loại bỏ ordering constraint; implementation không bắt buộc đổi thứ tự nào cả.

### Nhầm lẫn 4: “forEachOrdered() làm mọi map/filter tuần tự”

**Sai.** Nó sắp thứ tự **hành động terminal** theo encounter order nếu có; không cam kết thứ tự gọi các intermediate operations.

### Nhầm lẫn 5: “findAny() trên List vẫn luôn lấy phần tử đầu tiên”

**Không được dựa vào.** `findAny` có contract nondeterministic; dùng `findFirst` nếu cần first.

### Nhầm lẫn 6: “HashSet có thứ tự vì lần nào in cũng giống”

**Sai về hợp đồng.** Trường hợp quan sát ổn định không thay thế guarantee. `HashSet` không có defined encounter order.

### Nhầm lẫn 7: “ordered distinct lúc parallel có thể giữ bản duplicate bất kỳ”

**Sai.** Với ordered stream, `distinct` stable. Việc loại bỏ ordering constraint mới cho phép không bảo đảm representative đầu tiên.

### Nhầm lẫn 8: “Set hoặc Map kết quả collect luôn theo source order”

**Sai.** `Collectors.toSet`, `toMap` và một số map collectors không hứa iteration order theo encounter order nếu không chọn cấu trúc/collector phù hợp.

### Nhầm lẫn 9: “Một stream có thể gọi hai terminal operations”

**Sai.** Stream là một pipeline tiêu thụ một lần; để tính hai kết quả độc lập, tạo hai stream mới từ collection gốc hoặc thiết kế collector tổng hợp thích hợp.

### Nhầm lẫn 10: “Giữ order luôn nhanh hơn, hoặc bỏ order luôn nhanh hơn”

**Không có bảo đảm hiệu năng chung.** Ordered parallel stateful operations có thể đắt; với những pipeline khác, chi phí ordering không đáng kể. Benchmark mới quyết định.

## 23. Quy trình phân tích thứ tự cho một pipeline

Khi đọc một chuỗi `source.stream().op1().op2().terminal()`, làm theo thứ tự:

1. **Xác định nguồn:** `List`, array, `HashSet`, `LinkedHashSet`, `TreeSet`, generator hay custom spliterator?
2. **Xác định encounter order nguồn:** có contract hay chỉ quan sát tình cờ?
3. **Theo dõi các operations:** `unordered()` loại bỏ order, `sorted()` tạo thứ tự, `filter/map` thường giữ vị trí tương đối nếu source ordered.
4. **Xác định execution mode:** tuần tự hay song song? Có `parallel()` hoặc `sequential()` ở phía sau không?
5. **Xem terminal operation:** `toList`, `forEach`, `forEachOrdered`, `findFirst`, `findAny` hay collector concurrent?
6. **Xem stateful/short-circuit:** `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile` có yêu cầu prefix hoặc ordering barrier không?
7. **Xem side effects:** lambda có viết ra mutable shared state, log, I/O hoặc sửa source không? Nếu có, cần thiết kế lại.
8. **Xác định kết quả có thể test:** so đúng list khi order bảo đảm; so set/multiset/aggregation khi không cần order.
9. **Nếu hiệu năng là vấn đề:** đo nhiều kích thước dữ liệu và mức song song khác nhau; không dựa vào phỏng đoán từ tên method.

### Hỏi trước khi chuyển stream sang parallel

“Dữ liệu này cần giữ encounter order ở kết quả hay không?” là một câu hỏi **độc lập** với “Có thể tính toán nhiều phần tử cùng lúc hay không?”. Nếu câu trả lời là **cần order nhưng tính toán độc lập**, parallel + order-preserving terminal có thể hợp lệ. Nếu cần **side effects tuần tự**, vòng lặp đơn giản hoặc một worker có hàng đợi theo thứ tự có thể dễ bảo trì hơn.

## 24. Bài tập tự luyện có đáp án

**Bài 1 — parallel map.** Cho `List.of(2,1,3).parallelStream().map(x -> x*10).toList()`. Thứ tự danh sách kết quả là gì? **Đáp án:** `[20,10,30]`. Không suy ra thứ tự gọi lambda.

**Bài 2 — foreach.** Vì sao `parallelStream().forEach(System.out::println)` không thích hợp cho log cần theo nguồn? **Đáp án:** `forEach` không đảm bảo encounter order; dùng `forEachOrdered` hoặc thu thập kết quả có order rồi log.

**Bài 3 — HashSet.** `new HashSet<>(List.of(3,1,2)).stream().findFirst()` có trả `1` theo contract không? **Đáp án:** không. HashSet không cung cấp defined encounter order.

**Bài 4 — findAny.** Thay `findFirst` bằng `findAny` trong parallel stream ordered có giữ lựa chọn phần tử đầu không? **Đáp án:** không; `findAny` có thể chọn bất kỳ phần tử nào.

**Bài 5 — unordered.** `unordered()` có bắt buộc sinh ra thứ tự khác input không? **Đáp án:** không, chỉ bỏ yêu cầu giữ order.

**Bài 6 — limit.** `List.of(8,4,7,2).parallelStream().limit(2).toList()` trả gì? **Đáp án:** `[8,4]` vì ordered List. Nếu thêm `unordered()` trước `limit`, không được hứa hai phần tử đó.

**Bài 7 — distinct.** `List.of(3,1,3,2,1).parallelStream().distinct().toList()` trả gì? **Đáp án:** `[3,1,2]` theo encounter order và stable distinct.

**Bài 8 — takeWhile.** `List.of(2,4,5,6).stream().takeWhile(x -> x%2==0).toList()` trả gì? **Đáp án:** `[2,4]`, không phải `[2,4,6]`. Đây là prefix, không phải filter.

**Bài 9 — reduce.** Vì sao `parallel().reduce(0,(a,b)->a-b)` sai về mặt thiết kế? **Đáp án:** phép trừ không associative, nên kết quả phụ thuộc cách nhóm các phép tính.

**Bài 10 — collection result.** Vì sao không so trực tiếp `Collectors.toSet()` bằng chuỗi `[1,2,3]` khi in? **Đáp án:** iteration order của Set kết quả không được bảo đảm.

**Bài 11 — ordered terminal.** `parallelStream().map(...).forEachOrdered(...)` bảo đảm thứ tự ở đâu? **Đáp án:** ở terminal action đối với encounter order, không phải từng lời gọi mapper.

**Bài 12 — performance.** Khi nào `unordered().distinct()` đáng thử? **Đáp án:** khi không cần representative đầu tiên/order và pipeline parallel với dữ liệu đủ lớn; cần benchmark và correctness tests.

## 25. Ghi nhớ cốt lõi

- **Encounter order** là *thứ tự logic* của phần tử; **execution order** là *lịch thực thi* các bước tính toán và callback.
- `parallel` và `ordered` **không đối lập**; một pipeline có thể parallel mà vẫn có kết quả ordered.
- `forEach` không hứa giữ order; `forEachOrdered` giữ encounter order cho terminal actions nếu order tồn tại.
- `unordered()` loại ordering constraint; nó không shuffle hay sort.
- `findFirst` lấy first theo encounter order; `findAny` cho phép chọn bất kỳ phần tử.
- `limit`/`skip` trên ordered streams nói về **prefix**. `takeWhile`/`dropWhile` cũng dựa vào prefix, khác `filter`.
- `distinct` stable khi stream ordered; `sorted` stable đối với ties khi input ordered.
- `toList` giữ encounter order nếu có; iteration order của Set/Map không tự nhiên giống List.
- Lambda trong stream nên **stateless, non-interfering**, tránh side effects phụ thuộc lịch thread.
- Chỉ bỏ order để tối ưu khi domain cho phép; test dựa trên API contract, benchmark trên workload thật.

### Tài liệu chính thức

- [Java SE 25 — java.util.stream package: Ordering và Parallelism](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Java SE 25 — Stream: forEach, forEachOrdered, findFirst, findAny, distinct, sorted, limit](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 — BaseStream: unordered, parallel, sequential](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html)
- [Java SE 25 — Collectors: toList, toSet, groupingByConcurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 25 — Spliterator characteristics (ORDERED)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html)
