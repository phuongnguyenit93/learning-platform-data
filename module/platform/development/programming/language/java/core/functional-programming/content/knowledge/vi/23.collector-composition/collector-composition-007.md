# `Collectors.collectingAndThen()` để hoàn thiện kết quả trong Java

## 1. Vấn đề: kết quả thu thập cần thêm một bước hoàn thiện

Trong Java Stream, `collect(...)` có thể tổng hợp nhiều phần tử thành danh sách, Map, tổng số, thống kê hoặc một đối tượng kết quả khác. Đôi khi đầu ra trực tiếp của collector **chưa phải hình thức cuối cùng** mà nghiệp vụ muốn nhận.

Ví dụ: ta cần thu các tên thành một `List<String>` rồi trả danh sách không cho phép sửa cấu trúc; nhóm dữ liệu theo khóa và làm cho **mỗi danh sách trong nhóm** không thể thêm/xóa phần tử; hoặc tìm đối tượng có điểm cao nhất, rồi lấy tên của đối tượng đó và báo lỗi khi không có phần tử.

Một cách viết tuần tự:

~~~java
List<String> temporary = names.stream()
        .collect(Collectors.toCollection(ArrayList::new));

List<String> result = List.copyOf(temporary);
~~~

Cách này hợp lý, nhưng khi logic nhận một `Collector` làm tham số — nhất là downstream của `groupingBy` — việc gom “thu thập” và “hoàn thiện” vào một collector có thể rõ và tái sử dụng hơn. Java cung cấp:

~~~java
Collectors.collectingAndThen(downstream, finisher)
~~~

**`collectingAndThen` là collector kết hợp:** dùng một collector con (`downstream`) để tích lũy kết quả trước, sau đó áp dụng một hàm hoàn thiện (`finisher`) lên kết quả ấy.

Sau bài học, bạn cần:

1. Đọc đúng hợp đồng của `collectingAndThen(downstream, finisher)` và hai giai đoạn thu thập → hoàn thiện.
2. Phân biệt **collector's finisher** với `Stream.map`, `Collectors.mapping` và `Function.andThen`.
3. Chọn đầu ra `List` không sửa được một cách rõ ràng bằng `List.copyOf`, hiểu giới hạn về `null` và phần tử mutable.
4. Dùng `collectingAndThen` làm downstream trong `groupingBy` để hoàn thiện **từng nhóm**.
5. Chuyển `Optional<T>` của `maxBy`/`minBy` thành giá trị khác hoặc ném lỗi được định nghĩa.
6. Nắm việc finisher có thể thay đổi kiểu kết quả; hiểu `Collector.Characteristics.IDENTITY_FINISH` không còn áp dụng.
7. Nhận diện trường hợp không cần `collectingAndThen`, exception, chi phí bộ nhớ, parallel pipeline và trách nhiệm giữ dữ liệu bất biến.
8. Biên dịch, chạy ví dụ độc lập **Java 17+** và luyện bài tập với các trường hợp rỗng, `null`, nhiều nhóm.

## 2. Chữ ký tổng quát và ý nghĩa type

### 2.1. Chữ ký API

Theo mô hình kiểu tổng quát, method là:

~~~java
public static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher)
~~~

Đây là **chữ ký minh họa của thư viện Java**, không phải method cần tự cài đặt. Các tham số kiểu có ý nghĩa:

| Ký hiệu | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử đầu vào của Stream |
| `A` | Kiểu cấu trúc tích lũy nội bộ (accumulation type) của downstream |
| `R` | Kiểu kết quả mà downstream tạo ra sau khi hoàn tất |
| `RR` | Kiểu kết quả cuối cùng sau khi finisher áp dụng |
| `Collector<T,A,RR>` | Collector tổng hợp, nhận `T` và trả `RR` |

Điểm quan trọng: `R` **có thể khác `RR`**. Finisher không chỉ dùng để bao bọc List; nó có thể biến một `Optional<Work>` thành `String`, một danh sách `Work` thành `Summary`, hoặc một đối tượng thống kê thành báo cáo nghiệp vụ.

Trong thực tế, người gọi thường không cần viết `A` vì compiler suy luận generic từ downstream collector và finisher. Khi ví dụ lồng nhiều collector, có thể tách chúng thành biến có kiểu rõ để code dễ đọc và lỗi compiler dễ hiểu hơn.

### 2.2. Sơ đồ hai giai đoạn

~~~text
Stream<T>
   |
   v
downstream Collector<T, A, R>
   |  [supplier + accumulator + combiner + finisher của downstream]
   v
Kết quả trung gian R
   |
   v
Function<R, RR> finisher
   |
   v
Kết quả cuối RR
~~~

Ví dụ:

~~~java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

`toCollection(ArrayList::new)` tích lũy phần tử thành một danh sách `ArrayList`. Sau khi downstream hoàn thành, `List.copyOf` tạo một `List` unmodifiable theo cấu trúc hiện tại.

Đây là **mảnh mã trong phương thức** với import `java.util.List`, `java.util.ArrayList`, `java.util.stream.Stream` và `java.util.stream.Collectors`. Không có thao tác tự động in ra màn hình.

### 2.3. Finisher không phải lambda chạy trên từng phần tử

Nếu muốn biến chữ thường thành chữ hoa **cho mỗi tên**, dùng `map`:

~~~java
List<String> names = Stream.of("an", "binh", "chi")
        .map(String::toUpperCase)
        .toList();
~~~

Nếu muốn thay đổi **toàn bộ kết quả sau khi đã thu**, dùng `collectingAndThen`:

~~~java
List<String> names = Stream.of("an", "binh", "chi")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
~~~

Finisher ở ví dụ hai nhận **một List**, không nhận từng `String`. Trong thu thập bình thường không chia nhóm, bước hoàn thiện được áp dụng trên kết quả của downstream sau khi quá trình tích lũy và kết hợp cần thiết đã xong, không phải một lần cho mỗi phần tử đầu vào.

Đừng dùng một finisher để giả vờ thay thế `map`: nó vừa sai tầng xử lý, vừa có thể phải thu toàn bộ dữ liệu trước khi biến đổi.

## 3. Cơ chế hoạt động bên trong collector

### 3.1. Nhắc lại các thành phần của Collector

Một `Collector<T,A,R>` về mặt mô hình có các thành phần chính:

- **supplier:** tạo nơi tích lũy `A`.
- **accumulator:** nhận thêm phần tử `T` vào `A`.
- **combiner:** kết hợp hai kết quả tích lũy, đặc biệt quan trọng cho xử lý song song.
- **finisher:** biến trạng thái tích lũy `A` thành `R`.
- **characteristics:** mô tả các thuộc tính như `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH`.

`collectingAndThen` không yêu cầu bạn tự viết lại các bước supplier/accumulator/combiner. Nó **ủy nhiệm thu thập cho downstream**, rồi thêm một lớp finisher mới áp dụng lên kết quả `R`.

Vì downstream cũng có thể có finisher của riêng nó, thứ tự khái niệm là:

~~~text
supplier -> accumulator (nhiều lần) -> combiner (khi cần)
         -> downstream finisher
         -> collectingAndThen finisher
~~~

Lưu ý đây là **mô hình logic**; Stream framework có thể tối ưu hóa cách thực thi tùy thuộc đặc tính collector. Không dựa vào số lần gọi phương thức nội bộ hay thứ tự thread cụ thể để thực hiện side effect nghiệp vụ.

### 3.2. Đặc tính `IDENTITY_FINISH`

Một collector được đánh dấu `Collector.Characteristics.IDENTITY_FINISH` cho phép bỏ qua bước finisher vì kết quả tích lũy có thể dùng trực tiếp theo hợp đồng tương ứng. Nhưng `collectingAndThen` được tạo ra **để thêm bước hoàn thiện**, nên nó không giữ đặc tính `IDENTITY_FINISH` của downstream, dù downstream ban đầu có đặc tính này.

Điều đó đảm bảo hàm hoàn thiện vẫn nằm trong đường đi logic của collector kết hợp.

Các đặc tính khác có thể được kế thừa từ downstream theo hợp đồng của `collectingAndThen`, nhưng **không** suy ra rằng List trả về thread-safe, hoặc rằng side effect trong finisher sẽ tự được đồng bộ bởi framework. Hành vi an toàn phải dựa trên toàn bộ hợp đồng collector, loại kết quả và cách sử dụng sau thu thập.

### 3.3. Một ví dụ đổi kiểu đầu ra

~~~java
long totalCharacters = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                words -> words.stream()
                        .mapToLong(String::length)
                        .sum()));

System.out.println(totalCharacters); // 9
~~~

Finisher nhận `List<String>` và trả `Long` (qua boxing), nên kết quả `collect(...)` được gán cho primitive `long` qua unboxing. Tuy nhiên, nếu mục tiêu **chỉ** tính số ký tự, cách đơn giản/hiệu quả hơn là:

~~~java
long totalCharacters = Stream.of("An", "Binh", "Chi")
        .mapToLong(String::length)
        .sum();
~~~

Đây là một **ví dụ giới hạn của kỹ thuật**: việc có thể dùng `collectingAndThen` không có nghĩa nên thu List trung gian cho mọi phép tổng hợp.

## 4. Hoàn thiện danh sách bằng `List.copyOf`

### 4.1. Khi cần kết quả unmodifiable

~~~java
List<String> result = Stream.of("Java", "Stream")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

// result.add("Lambda"); // Khi chạy: UnsupportedOperationException.
~~~

Đầu tiên, downstream tích lũy vào `ArrayList`; tiếp đó `List.copyOf` tạo một List **unmodifiable** theo cấu trúc dữ liệu lúc hoàn thiện. Caller không được tự ý thêm/xóa/sửa phần tử thông qua các phương thức sửa của List.

Đoạn mã được trình bày nhằm minh họa sự phân tách: *thu mutable ở bên trong* rồi *trả kết quả không cho sửa ở bên ngoài*. Nếu chỉ cần List unmodifiable, có những API ngắn hơn (phần 6), nên không phải lúc nào cũng cần viết collectingAndThen.

### 4.2. `List.copyOf` là snapshot cấu trúc, không deep copy

~~~java
StringBuilder builder = new StringBuilder("old");

List<StringBuilder> result = Stream.of(builder)
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

builder.append("-new");
System.out.println(result.get(0)); // old-new
~~~

Danh sách `result` không cho sửa các reference phần tử qua API List, nhưng `StringBuilder` bên trong vẫn là **object mutable**. `List.copyOf` không tự sao chép sâu dữ liệu của mọi phần tử. Nếu yêu cầu dữ liệu bất biến đến cấp đối tượng bên trong, hãy chọn element immutable hoặc tạo deep copy có nghĩa nghiệp vụ.

`List.copyOf` cũng có thể tái sử dụng instance khi đầu vào đã là một unmodifiable List thích hợp, nên đừng khẳng định phải luôn cấp phát một List hoàn toàn mới theo identity.

### 4.3. Chính sách `null` quan trọng

`List.copyOf` **không chấp nhận phần tử null**. Ví dụ:

~~~java
List<String> result = Stream.of("A", null)
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

Khi finisher `List.copyOf` chạy, ví dụ ném `NullPointerException`. Downstream `toCollection(ArrayList::new)` cho phép null, nhưng **bước hoàn thiện** có hợp đồng khác.

Nếu muốn List unmodifiable nhưng **cho phép null** (trên Java 17), `Stream.toList()` có hợp đồng phù hợp hơn. Nếu muốn từ chối null và trả List unmodifiable, có thể dùng `Collectors.toUnmodifiableList()` mà không cần thêm finisher.

Không tự ý dùng `filter(Objects::nonNull)` để giấu dữ liệu sai trừ khi việc bỏ phần tử null là quyết định nghiệp vụ chính thức.

### 4.4. Bảo vệ List sau khi thu không bảo vệ mọi dữ liệu liên quan

Một phương thức có thể trả List unmodifiable nhưng vẫn để lộ những object mutable bên trong, hoặc có state bên ngoài bị thay đổi khi callback chạy. Cần phân biệt rõ:

| Điều bạn muốn | `List.copyOf` giải quyết? |
| --- | --- |
| Caller không thể `add/remove/set` trực tiếp trên List | Có |
| Nguồn List mutable thay đổi cấu trúc làm kết quả đổi theo | Không, với snapshot cấu trúc thích hợp |
| Element `StringBuilder` bị đổi trạng thái qua reference khác | Không |
| Object chứa List tự động thread-safe | Không |
| Một phần tử null được chấp nhận | Không |
| Trả identity List mới bằng mọi giá | Không cam kết |

## 5. Finisher kiểu khác: `Optional` thành giá trị nghiệp vụ

### 5.1. `Collectors.maxBy` trả `Optional<T>`

~~~java
Optional<Integer> largest = Stream.of(4, 9, 2)
        .collect(Collectors.maxBy(Integer::compareTo));

System.out.println(largest); // Optional[9]
~~~

Đây là mảnh mã cần import `Optional`, `Stream` và `Collectors`. `maxBy` không thể luôn trả một giá trị kiểu `Integer` trực tiếp, vì Stream có thể rỗng; nên nó trả `Optional<Integer>`.

Nếu business rule yêu cầu “phải có ít nhất một phần tử”, có thể hoàn thiện bằng `Optional::orElseThrow` hoặc lambda tương đương:

~~~java
int largest = Stream.of(4, 9, 2)
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Integer::compareTo),
                value -> value.orElseThrow()));

System.out.println(largest); // 9
~~~

Kết quả cuối không còn là `Optional<Integer>` mà là `Integer`, được gán cho `int`.

### 5.2. Xác định chính sách cho đầu vào rỗng

~~~java
int largest = Stream.<Integer>empty()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Integer::compareTo),
                value -> value.orElseThrow()));
~~~

Đoạn trên **cố ý ném `NoSuchElementException`** vì không có phần tử lớn nhất. Đây là một chính sách hợp lệ **nếu** domain không cho phép tập rỗng và đã xác định lỗi cần trả cho caller. Nếu tập rỗng là bình thường, nên chọn:

~~~java
Optional<Integer> largest = Stream.<Integer>empty()
        .collect(Collectors.maxBy(Integer::compareTo));
~~~

Hoặc lựa chọn một giá trị mặc định được domain chấp thuận, với giải thích rõ. Đừng ép Optional thành giá trị rồi ném lỗi chỉ để làm code ngắn.

### 5.3. Khi giá trị cuối là một trường của object

~~~java
record Work(String title, int points) {}

String topTitle = works.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(
                        Comparator.comparingInt(Work::points)),
                optional -> optional.orElseThrow().title()));
~~~

Đây là **mảnh mã trong class/method** có biến `works` kiểu `List<Work>` và import `Comparator`, `Collectors`. Finisher nhận `Optional<Work>`, buộc có phần tử theo chính sách, sau đó trả `String`. Ví dụ hoàn chỉnh ở phần 9 xác minh trường hợp này.

Nếu chỉ muốn lấy một giá trị lớn nhất và không cần xây Collector để lồng vào API khác, `stream.max(comparator).orElseThrow()` thường ngắn hơn. `collectingAndThen` đặc biệt hữu ích khi cần **một collector hoàn chỉnh làm downstream** của collector khác.

## 6. Không lạm dụng: so với các API ngắn hơn

Một số kết quả có thể tạo trực tiếp bằng terminal operation hoặc collector chuyên dụng:

| Mục tiêu | Cách trực tiếp | Dùng `collectingAndThen` khi nào? |
| --- | --- | --- |
| List unmodifiable, Java 16+ | `stream.toList()` | Cần một `Collector` đem lồng vào `groupingBy`/API khác |
| List unmodifiable, không chứa null | `collect(toUnmodifiableList())` | Cần thêm bước hoàn thiện khác collector có sẵn |
| Tổng số nguyên | `mapToInt(...).sum()` | Finisher thật sự cần đổi một kết quả đã thu phức tạp |
| Số lượng phần tử | `count()` | Cần chuyển một collector downstream khác thành domain result |
| Giá trị lớn nhất | `max(comparator)` | Cần đóng gói thành collector làm thành phần cấu trúc |
| List mutable loại cụ thể | `collect(toCollection(ArrayList::new))` | Sau khi thu cần thao tác hoàn thiện có hợp đồng riêng |

**Ví dụ tối giản:**

~~~java
List<String> direct = Stream.of("A", "B").toList();
~~~

Với Java 17, List này là unmodifiable và có thể chứa null. Không cần viết `collectingAndThen(toList(), List::copyOf)` chỉ để có một List không sửa được, đặc biệt nếu null là dữ liệu hợp lệ.

### 6.1. `Collectors.toList()` không cam kết mutable

~~~java
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

Javadoc của `Collectors.toList()` **không cam kết concrete type, mutability, serializability hoặc thread safety**. Vì vậy, nếu muốn `List.copyOf` làm rõ đầu ra unmodifiable, việc dùng `collectingAndThen(Collectors.toList(), List::copyOf)` là một mẫu khả thi cho dữ liệu không null, nhưng không được nói downstream `toList()` luôn trả mutable `ArrayList`.

Nếu cần mutable `ArrayList` nội bộ theo hợp đồng, chọn `toCollection(ArrayList::new)`. Finisher `List.copyOf` sau đó không phụ thuộc vào một chi tiết implementation vô tình của collector `toList()`.

### 6.2. `Collections.unmodifiableList` khác `List.copyOf`

~~~java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);
List<String> snapshot = List.copyOf(backing);

backing.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
~~~

`Collections.unmodifiableList` trả **view không thể sửa qua wrapper**, nhưng có thể phản ánh thay đổi cấu trúc ở backing source. `List.copyOf` cho snapshot cấu trúc unmodifiable đối với backing mutable trong ví dụ. Cả hai đều không làm element mutable trở thành immutable sâu.

Nếu dùng `collectingAndThen(toCollection(ArrayList::new), Collections::unmodifiableList)`, backing list vừa thu thường không được phát lộ riêng, nhưng finisher vẫn tạo **view**, không phải lời cam kết deep snapshot. Hãy chọn `List.copyOf` khi muốn hợp đồng snapshot cấu trúc rõ và không có null.

## 7. `collectingAndThen` làm downstream của `groupingBy`

### 7.1. Không nhóm trực tiếp thì chỉ hoàn thiện một kết quả

Với:

~~~java
List<String> result = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
~~~

Finisher hoạt động trên List cuối của **toàn bộ phép collect**. Nó không xử lý từng phần tử và không tạo một kết quả riêng cho từng khóa, vì không có bước nhóm.

### 7.2. Lồng trong `groupingBy` thì hoàn thiện từng nhóm

Ví dụ:

~~~java
Map<String, List<String>> byTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()),
                        List::copyOf)));
~~~

Đây là mảnh mã trong class có `record Person(String name, String team) {}`, biến `people` kiểu `List<Person>`, import `Map`, `Collectors`, `List`. Quy trình cho mỗi khóa nhóm:

~~~text
Tất cả Person đầu vào
         |
         v
groupingBy(Person::team)
         |
         +-- Team A --> mapping(Person::name) --> toList()
         |                                    --> List.copyOf()
         |
         +-- Team B --> mapping(Person::name) --> toList()
                                              --> List.copyOf()
~~~

`Collectors.mapping` biến **từng `Person` thành tên** trước khi downstream nhận; `collectingAndThen` biến **một List tên đã thu xong của nhóm** thành List unmodifiable.

**Quan trọng:** `List.copyOf` trong downstream chỉ bảo vệ **các List giá trị**, không tự biến `Map` chứa các nhóm thành unmodifiable. Bạn vẫn có thể `put` nhóm mới nếu Map kết quả cho phép, tùy hợp đồng map factory/collector được chọn. Nếu muốn Map và từng List đều không sửa được, cần thiết kế bảo vệ **hai cấp**.

### 7.3. Chọn `TreeMap` nếu muốn thứ tự khóa rõ

~~~java
Map<String, List<String>> byTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()),
                        List::copyOf)));
~~~

Đây là ví dụ cần import `TreeMap`. `TreeMap` sắp khóa theo natural ordering hoặc comparator được cung cấp. Vì vậy việc in `Map` có thể có thứ tự nhóm xác định, thay vì giả định `groupingBy` mặc định trả `HashMap` hay theo thứ tự chèn.

Với `Collectors.mapping(Person::name, toList())`, thứ tự tên trong mỗi nhóm trên ordered Stream thường phản ánh thứ tự gặp tương ứng, không tự sort các tên. Nếu cần tên được sắp alphabet, hãy thêm logic phù hợp (ví dụ dùng downstream thu và sắp trong finisher), nhưng lưu ý chi phí và null policy.

### 7.4. Thống kê từng nhóm bằng finisher

Finisher có thể tạo **bản tóm tắt nhóm** chứ không chỉ List:

~~~java
record Summary(int count, int highest) {}

Map<String, Summary> reports = works.stream()
        .collect(Collectors.groupingBy(
                Work::group,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        items -> new Summary(
                                items.size(),
                                items.stream()
                                     .mapToInt(Work::points)
                                     .max()
                                     .orElseThrow()))));
~~~

Đây là đoạn code minh họa nằm trong class định nghĩa `Work` có accessor `group()`/`points()`, có record `Summary`, biến `works` kiểu `List<Work>` và import tương ứng. Mỗi nhóm có một List đã tích lũy; finisher tính số phần tử và điểm cao nhất rồi tạo một record.

**Đánh đổi:** cách này cần **thu từng nhóm vào List**, sau đó mới duyệt List tính maximum. Với dữ liệu lớn, có thể dùng downstream `summarizingInt` hoặc collector tùy biến phù hợp để tránh lưu toàn bộ object, rồi chuyển `IntSummaryStatistics` thành record qua finisher. Tính đúng và chi phí dữ liệu nên cùng được đánh giá.

### 7.5. Hai cấp hoàn thiện: từng List và toàn bộ Map

Một mẫu có thể thấy trong API trả dữ liệu đọc-only:

~~~java
Map<String, List<String>> immutableTopLevel =
        people.stream().collect(
                Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Person::team,
                                Collectors.collectingAndThen(
                                        Collectors.mapping(
                                                Person::name,
                                                Collectors.toList()),
                                        List::copyOf)),
                        Map::copyOf));
~~~

Bước `List.copyOf` hoàn thiện **mỗi List nhóm**; bước `Map.copyOf` hoàn thiện **Map tổng thể**. `Map.copyOf` tạo Map unmodifiable theo mapping tại thời điểm copy, nhưng **không hứa giữ thứ tự iteration của Map nguồn**. Nó từ chối null key và value; `List.copyOf` từ chối null element. Nếu thứ tự khóa là yêu cầu API, hãy thiết kế một kiểu snapshot/Map có hợp đồng thứ tự phù hợp, không mặc định `Map.copyOf` giữ thứ tự `TreeMap`.

## 8. `mapping`, `filtering` và `collectingAndThen`: phân biệt tầng

Các collector kết hợp thường xuất hiện cùng nhau nhưng giải quyết câu hỏi khác:

| Collector | Chạy ở tầng nào? | Ví dụ sử dụng |
| --- | --- | --- |
| `mapping(mapper, downstream)` | Biến đổi **từng phần tử** trước khi downstream thu | Person → name, sau đó thu tên |
| `filtering(predicate, downstream)` | Quyết định từng phần tử có đi vào downstream không | Chỉ giữ Work đạt yêu cầu trong từng nhóm |
| `flatMapping(mapper, downstream)` | Mỗi phần tử mở rộng thành Stream nhiều phần tử | Mỗi Work → danh sách tag |
| `collectingAndThen(downstream, finisher)` | Hoàn thiện **kết quả của downstream** | List tên → unmodifiable List |
| `groupingBy(classifier, downstream)` | Chia phần tử theo khóa; gọi downstream cho mỗi nhóm | Gom các Work theo group |
| `teeing(downstream1, downstream2, merger)` | Thu song song về mặt logic thành hai kết quả rồi ghép | Count + max → Summary |

### Ví dụ dễ nhầm

~~~java
Collectors.mapping(Work::title, Collectors.toList())
~~~

Nó biến **mỗi Work** thành `String` rồi thu. Còn:

~~~java
Collectors.collectingAndThen(
        Collectors.toList(),
        items -> items.size())
~~~

Nó thu **toàn bộ List** rồi trả kích thước. Nếu mục tiêu chỉ đếm, `Collectors.counting()` thường gọn hơn và không yêu cầu giữ các object trong bộ nhớ.

Cả hai collector có thể kết hợp trong `groupingBy` khi cần vừa biến đổi phần tử vừa hoàn thiện kết quả cuối, nhưng không nên tạo pipeline lồng sâu chỉ để thể hiện kỹ thuật.

## 9. Chương trình Java 17 hoàn chỉnh và kiểm chứng stdout

Chương trình dưới đây minh họa ba trường hợp có ích: tạo List unmodifiable, hoàn thiện kết quả **theo nhóm**, và chuyển `Optional<Work>` thành tên của Work. Nó cũng kiểm tra hai nhánh lỗi: tập rỗng với `orElseThrow` và dữ liệu null với `List.copyOf`.

Tạo tệp **`CollectingAndThenDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectingAndThenDemo {

    record Work(String group, String title, int points) {}
    record Summary(int count, int highest) {}

    public static void main(String[] args) {
        List<Work> input = List.of(
                new Work("core", "A", 10),
                new Work("web", "B", 20),
                new Work("core", "C", 30),
                new Work("web", "D", 40)
        );

        // 1. Thu vào ArrayList, hoàn thiện thành List unmodifiable.
        List<String> titles = input.stream()
                .map(Work::title)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        List::copyOf));
        System.out.println("titles=" + titles);

        try {
            titles.add("E");
        } catch (UnsupportedOperationException ex) {
            System.out.println("titles-add=blocked");
        }

        // 2. Hoàn thiện List của từng nhóm sau khi mapping.
        Map<String, List<String>> byGroup = input.stream()
                .collect(Collectors.groupingBy(
                        Work::group,
                        TreeMap::new,
                        Collectors.collectingAndThen(
                                Collectors.mapping(
                                        Work::title,
                                        Collectors.toList()),
                                List::copyOf)));
        System.out.println("groups=" + byGroup);

        // 3. Biến List trong từng nhóm thành record Summary.
        Map<String, Summary> summaries = input.stream()
                .collect(Collectors.groupingBy(
                        Work::group,
                        TreeMap::new,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                items -> new Summary(
                                        items.size(),
                                        items.stream()
                                             .mapToInt(Work::points)
                                             .max()
                                             .orElseThrow()))));
        System.out.println("summaries=" + summaries);

        // 4. Biến Optional<Work> thành String.
        String top = input.stream()
                .collect(Collectors.collectingAndThen(
                        Collectors.maxBy(
                                Comparator.comparingInt(Work::points)),
                        optional -> optional.orElseThrow().title()));
        System.out.println("top=" + top);

        // 5. Không có Work: orElseThrow xác định chính sách lỗi.
        try {
            Stream.<Work>empty()
                    .collect(Collectors.collectingAndThen(
                            Collectors.maxBy(
                                    Comparator.comparingInt(Work::points)),
                            optional -> optional.orElseThrow().title()));
        } catch (NoSuchElementException ex) {
            System.out.println("empty=failed");
        }

        // 6. Finisher List.copyOf từ chối phần tử null.
        try {
            Stream.of("A", null)
                    .collect(Collectors.collectingAndThen(
                            Collectors.toCollection(ArrayList::new),
                            List::copyOf));
        } catch (NullPointerException ex) {
            System.out.println("null=rejected");
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 CollectingAndThenDemo.java
java CollectingAndThenDemo
~~~

**Stdout chính xác:**

~~~text
titles=[A, B, C, D]
titles-add=blocked
groups={core=[A, C], web=[B, D]}
summaries={core=Summary[count=2, highest=30], web=Summary[count=2, highest=40]}
top=D
empty=failed
null=rejected
~~~

### 9.1. Vì sao `titles` giữ thứ tự A, B, C, D?

Nguồn `List<Work>` có encounter order, `map(Work::title)` giữ thứ tự, rồi downstream `toCollection(ArrayList::new)` thu lần lượt các tên. `List.copyOf` tạo List unmodifiable với cùng thứ tự phần tử. Vì vậy `titles=[A, B, C, D]`.

### 9.2. Vì sao `titles.add("E")` bị chặn?

Finisher `List.copyOf` trả List unmodifiable. Lời gọi `add` ném `UnsupportedOperationException` và chương trình in `titles-add=blocked`. Sự chặn này đến từ **finisher được chọn**, không phải từ `Collectors.toList()` hay tính chất vốn có của mọi List.

### 9.3. Vì sao hai nhóm theo thứ tự core, web?

`groupingBy(Work::group, TreeMap::new, downstream)` dùng `TreeMap` làm Map kết quả; khóa `"core"` đứng trước `"web"` theo thứ tự tự nhiên của `String`. Từng nhóm dùng `mapping(Work::title, toList())` để thu tên, rồi `List.copyOf` hoàn thiện List của nhóm đó. Do đó `groups={core=[A, C], web=[B, D]}`.

Việc List bên trong không thể sửa không tự bảo đảm Map ngoài không sửa được. Ở đây `TreeMap` vẫn là một Map mutable; API cần ranh giới bất biến hai cấp thì phải thiết kế riêng.

### 9.4. Vì sao Summary được tạo cho từng nhóm?

Nhóm core gồm hai Work có `points=10,30`, nhóm web có `points=20,40`. Finisher trên mỗi List nhóm tạo `Summary[count=2, highest=30]` hoặc `Summary[count=2, highest=40]`. Nó không chạy một lần trên từng Work, mà trên **kết quả đã thu cho nhóm tương ứng**.

### 9.5. Vì sao top là D, và tập rỗng gây lỗi?

`maxBy(comparingInt(Work::points))` trả `Optional<Work>`. Phần tử có điểm cao nhất là D với 40 điểm; finisher lấy `title` nên in `top=D`. Khi nguồn rỗng, `maxBy` trả `Optional.empty()`; chính sách `orElseThrow` dẫn đến `NoSuchElementException`, được bắt để in `empty=failed`.

### 9.6. Vì sao null bị từ chối?

`toCollection(ArrayList::new)` có thể thu `null` trong `ArrayList`, nhưng bước finisher `List.copyOf` không cho null. Ngoại lệ phát sinh ở thời điểm hoàn thiện và được bắt để in `null=rejected`. Điều này cho thấy downstream và finisher có thể có **hợp đồng khác nhau**.

## 10. Empty input, `null`, exception và side effect

### 10.1. Empty Stream vẫn có thể có kết quả hoàn chỉnh

~~~java
List<String> result = Stream.<String>empty()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

System.out.println(result); // []
~~~

Downstream tạo danh sách rỗng, finisher biến nó thành List unmodifiable rỗng. Tập rỗng **không mặc nhiên là lỗi** của `collectingAndThen`; lỗi chỉ xảy ra nếu downstream hoặc finisher không xử lý được trạng thái rỗng, chẳng hạn `Optional::orElseThrow`.

### 10.2. Finisher có thể ném ngoại lệ

~~~java
List<String> result = Stream.of(" A ", " B ")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                values -> {
                    if (values.size() != 2) {
                        throw new IllegalArgumentException("Expected two");
                    }
                    return List.copyOf(values);
                }));
~~~

Đây là mảnh mã với nguồn hai phần tử, nên không ném lỗi kiểm tra kích thước. Nhưng nếu giá trị đầu vào khác quy tắc, finisher có thể ném unchecked exception; `Stream.collect` chuyển ngoại lệ đến caller. **Không có rollback tự động** cho side effect đã xảy ra trước bước hoàn thiện.

Nếu validation có thể thực hiện **trước hoặc trong quá trình thu** hiệu quả hơn, hãy cân nhắc làm sớm; không bắt buộc phải thu toàn bộ dữ liệu mới kiểm tra được mọi điều kiện.

### 10.3. Không đặt side effect quan trọng trong finisher

Không nên dùng finisher để gửi email, ghi tiền, ghi database hay mutate state dùng chung chỉ vì “sau collect thì chắc chắn đúng một lần”. Với xử lý song song, nhóm dữ liệu và vòng đời collector phức tạp hơn; các thao tác side effect cần hợp đồng transaction/idempotency rõ. Dùng finisher để **tạo đối tượng kết quả** hoặc chuẩn hóa có thể dự đoán là phù hợp hơn.

### 10.4. Khi dùng Stream song song

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

Đây là mảnh mã trong method, cần import `java.util.stream.IntStream`. Stream framework thu và kết hợp kết quả theo hợp đồng collector rồi hoàn thiện. Với nguồn ordered và collector tương thích encounter order, List đầu ra giữ thứ tự các số `0..99`. Nhưng kết quả unmodifiable **không đồng nghĩa các object phần tử luôn bất biến sâu**, và không cho phép suy luận về an toàn của mọi shared mutable state bên ngoài pipeline.

Nếu chỉ cần List không sửa được, `IntStream.range(0,100).boxed().toList()` từ Java 16+ thường ngắn hơn. Đừng dùng `parallel().forEach(sharedArrayList::add)` để tự thay thế collector: shared mutable accumulator có thể race.

## 11. Tính hiệu quả: chi phí thu rồi hoàn thiện

### 11.1. Có thể xuất hiện danh sách trung gian

Với:

~~~java
List<String> output = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

Downstream tạo một `ArrayList`, và finisher tạo List unmodifiable theo cấu trúc tại thời điểm copy. Điều này có thể phát sinh thêm cấp phát và copy reference, đặc biệt khi danh sách rất lớn. Không coi `collectingAndThen` là giải pháp tối ưu bộ nhớ mặc định.

Khi chỉ cần trả unmodifiable List, `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` có thể rõ hơn và giúp implementation sử dụng chiến lược phù hợp. Không khẳng định phương án nào nhanh hơn tuyệt đối; benchmark với dữ liệu, JDK, pipeline và đặc điểm phần tử thật khi hiệu năng là mục tiêu.

### 11.2. Đếm và lấy maximum không nhất thiết cần List

Ví dụ `groupingBy(..., collectingAndThen(toList(), items -> items.size()))` có thể hoạt động, nhưng `groupingBy(..., counting())` không cần lưu toàn bộ phần tử nhóm chỉ để đếm.

Nếu muốn record gồm count và maximum, có thể:

~~~java
record ScoreSummary(long count, int highest) {}

Map<String, ScoreSummary> summaries = works.stream()
        .collect(Collectors.groupingBy(
                Work::group,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(Work::points),
                        stats -> new ScoreSummary(
                                stats.getCount(),
                                stats.getMax()))));
~~~

Đây là mảnh mã trong class có `Work` và biến `works` phù hợp. `summarizingInt` thu số liệu thống kê; finisher đổi `IntSummaryStatistics` thành record có ít field hơn. Cần xác định chính sách cho nhóm rỗng nếu dùng thống kê ngoài `groupingBy`: `IntSummaryStatistics.getMax()` có sentinel khi chưa có giá trị, không nên gán ý nghĩa nghiệp vụ cho nó mà không kiểm tra `getCount()`.

### 11.3. Tránh giữ reference đến accumulator mutable ở bên ngoài

Nếu finisher trả trực tiếp accumulator mutable và code khác giữ reference, kết quả có thể thay đổi sau khi collect. Khi mục tiêu là đóng băng cấu trúc, nên tạo unmodifiable snapshot phù hợp thay vì trao một List sửa được rồi yêu cầu các bên “tự giác” không thay đổi.

Đồng thời, không tạo deep copy cho mọi đối tượng theo thói quen nếu domain chỉ cần copy cấu trúc; hãy thiết kế mức bất biến theo yêu cầu thật.

## 12. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao chưa đúng | Cách sửa |
| --- | --- | --- |
| Dùng `collectingAndThen` để xử lý từng element | Finisher nhận kết quả `R` của downstream, không phải `T` | `Stream.map` hoặc `Collectors.mapping` |
| Tưởng `List.copyOf` deep-copy mọi element | Chỉ tạo snapshot cấu trúc, có thể chia sẻ element mutable | Element immutable hoặc deep-copy khi cần |
| Dùng `List.copyOf` với null và mong giữ null | `List.copyOf` từ chối null | Chọn chính sách null phù hợp; `Stream.toList()` cho phép null |
| Tin `Collectors.toList()` luôn trả ArrayList mutable | Javadoc không cam kết implementation/mutability | `toCollection(ArrayList::new)` nếu cần |
| Gọi `Optional.orElseThrow` trên dữ liệu có thể rỗng | Có thể ném `NoSuchElementException` | Xác định fallback hoặc giữ Optional |
| Cho rằng khóa List con cũng khóa Map ngoài | Các cấp mutable độc lập | Hoàn thiện từng List và Map nếu cần |
| Mong `Map.copyOf` giữ thứ tự TreeMap | Map copy không cam kết iteration order | Chọn Map/view có hợp đồng thứ tự riêng |
| Dùng finisher để tính tổng từ List rất lớn | Cần lưu trung gian vô ích | `summingInt`/`summarizingInt`/reduction |
| Cho rằng finisher có thể là mọi kiểu callback | Finisher cần `Function<R,RR>` và type-compatible | Khai báo đúng kiểu kết quả downstream |
| Dùng `collectingAndThen` chỉ để gọi `toList()` ngắn hơn | Làm API phức tạp, có thể tốn copy | `Stream.toList()` khi đúng hợp đồng |
| Dùng parallel `forEach` mutate chung một List | Có race condition | Dùng collector/`toList` |
| Dựa vào side effect trong finisher để bảo đảm transaction | Collector không có rollback nghiệp vụ | Thiết kế transaction/idempotency ngoài Stream |
| Xử lý lỗi khi collection chưa hoàn tất như thể đã có kết quả | Exception có thể dừng collect trước finisher | Catch ở ranh giới phù hợp và kiểm thử lỗi |

### 12.1. Khi nào nên tách collector thành biến?

Nếu lồng quá nhiều tầng, kiểu dữ liệu tường minh có thể giúp đọc:

~~~java
Collector<String, ?, List<String>> immutableList =
        Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf);

List<String> result = Stream.of("A", "B").collect(immutableList);
~~~

Đây là mảnh mã trong method, cần import `java.util.stream.Collector`, `Collectors`, `Stream` và `List`/`ArrayList`. Việc định nghĩa tên `immutableList` diễn đạt ý định tạo List unmodifiable ở **cấp cấu trúc**, không bảo đảm immutable sâu. Đặt tên rõ trách nhiệm và tránh tạo helper generic rộng hơn yêu cầu.

## 13. Bài tập tự luyện

### Bài 1 — Biến List thành unmodifiable

Thu `Stream.of("An","Binh")` thành `ArrayList` rồi dùng `collectingAndThen` và `List.copyOf`. In danh sách và thử `add("Chi")` trong `try/catch`. Giải thích vì sao `UnsupportedOperationException` đến từ kết quả finisher, không phải từ tính năng tự nhiên của mọi `Collector`.

### Bài 2 — Downstream và finisher có kiểu gì?

Phân tích:

~~~java
Collector<String, ?, List<String>> c =
        Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf);
~~~

Nêu `T`, `R`, `RR` trong trường hợp này; giải thích vì sao `A` được wildcard và compiler có thể suy luận kiểu accumulator. Nếu không có khác biệt lớn giữa `R` và `RR` ở đây, hãy nêu một ví dụ thay đổi kiểu thật sự (như `Optional<Work> -> String`).

### Bài 3 — Max và đầu vào rỗng

Dùng `Collectors.maxBy(Integer::compareTo)`, hoàn thiện bằng `value -> value.orElseThrow()`. Thử với `[3,8,5]` và Stream rỗng. Nêu rõ vì sao chỉ một trường hợp có kết quả và trường hợp khác ném `NoSuchElementException`.

### Bài 4 — Grouping và tên thành viên

Tạo `record Person(String team,String name) {}`. Dùng `groupingBy(Person::team, collectingAndThen(mapping(Person::name,toList()), List::copyOf))`. Với mỗi nhóm, thử sửa List kết quả và quan sát ngoại lệ. Tiếp tục thử thêm một key mới vào Map (nếu loại Map cho phép) để thấy hai cấp khác nhau.

### Bài 5 — Map và List cùng unmodifiable

Hoàn thiện List theo nhóm rồi dùng một finisher cấp ngoài `Map::copyOf`. Giải thích vì sao Map và List đều chặn sửa qua API tương ứng; đồng thời nêu rằng `Map.copyOf` không cam kết giữ thứ tự iteration, và các object phần tử mutable vẫn cần chính sách riêng.

### Bài 6 — Tính thống kê theo nhóm

Tạo record `Summary(long count,int highest)`. Sử dụng `groupingBy` kết hợp `summarizingInt`, rồi `collectingAndThen` biến thống kê thành record. So sánh với việc thu cả nhóm bằng `toList` rồi duyệt thêm lần nữa. Nêu ưu/nhược điểm về bộ nhớ.

### Bài 7 — Phân biệt tầng xử lý

So sánh `mapping(Person::name,toList())` với `collectingAndThen(toList(), List::copyOf)`. Cái nào xử lý từng element, cái nào xử lý List đã thu? Viết một pipeline kết hợp cả hai, sau đó giải thích thứ tự xử lý.

### Bài 8 — Chính sách null

Cho nguồn `["A", null, "B"]`. Dùng `toCollection(ArrayList::new)` và `List.copyOf` trong finisher; dự đoán `NullPointerException`. Chọn một cách khác nếu yêu cầu giữ null trong List unmodifiable, và một cách khác nếu nghiệp vụ muốn từ chối null sớm.

### Bài 9 — Parallel collect

So sánh thứ tự kết quả từ `IntStream.range(0,100).parallel().boxed().toList()` và pipeline dùng `collectingAndThen(toCollection(ArrayList::new), List::copyOf)`. Kiểm tra hai List bằng `equals`, không dùng `parallel().forEach(System.out::println)` để đo thứ tự dữ liệu.

### Bài 10 — Refactor quá mức

Cho:

~~~java
long count = records.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> (long) list.size()));
~~~

Đề xuất viết lại bằng `records.stream().count()`, hoặc `Collectors.counting()` nếu cần downstream của `groupingBy`. Giải thích lợi ích giảm collection trung gian và làm rõ mục đích.

## 14. Câu hỏi tự kiểm tra

1. **`collectingAndThen` nhận những gì?** Một downstream Collector và một `Function` để hoàn thiện kết quả downstream.
2. **Finisher nhận từng phần tử `T` hay kết quả `R`?** Kết quả `R` đã được downstream thu.
3. **`R` và `RR` bắt buộc cùng kiểu?** Không; finisher có thể biến `Optional<Work>` thành `String` hoặc statistics thành record.
4. **`IDENTITY_FINISH` còn được giữ trong collector kết hợp không?** Không, do có bước finisher bổ sung.
5. **Trong `groupingBy`, finisher downstream chạy cho từng Work hay mỗi nhóm?** Trên kết quả downstream của mỗi nhóm.
6. **`List.copyOf` có chấp nhận null?** Không.
7. **`List.copyOf` có deep-copy StringBuilder trong List?** Không.
8. **`List.copyOf` bảo vệ Map ngoài khi dùng làm downstream của groupingBy?** Không.
9. **`Optional::orElseThrow` có hợp lý với Stream rỗng?** Chỉ nếu chính sách nghiệp vụ chấp nhận lỗi khi không có phần tử.
10. **Có cần collectingAndThen chỉ để lấy List unmodifiable từ một Stream đơn giản?** Không nhất thiết; `Stream.toList()` trên Java 17 thường đơn giản hơn.
11. **Làm sao hoàn thiện Map và List con đều unmodifiable?** Dùng finisher ở từng tầng, với kiểm soát null và thứ tự nếu có yêu cầu.
12. **Dùng finisher để tạo counter trên List lớn có tối ưu không?** Không tự động; thường có collector đếm/tổng hợp hiệu quả hơn.

## 15. Checklist khi review code

1. `downstream` trả kiểu gì? Finisher được khai báo nhận **đúng kiểu `R`** đó chưa?
2. Finisher có tạo `RR` đúng hợp đồng bên gọi cần hay đang chỉ đổi kiểu vì thuận tay?
3. Mục tiêu là xử lý **từng element** hay **kết quả đã thu**? Có nhầm `mapping`/`map` với `collectingAndThen` không?
4. Nếu cần unmodifiable List, có thể dùng `Stream.toList()`/`toUnmodifiableList()` đơn giản hơn không?
5. Nếu dùng `List.copyOf`, dữ liệu có null không và object phần tử có mutable không?
6. Nếu lồng trong `groupingBy`, finisher áp dụng từng nhóm; Map ngoài cần được bảo vệ riêng không?
7. Nếu cần thứ tự group, đã chọn Map factory thích hợp thay vì trông đợi `groupingBy` mặc định chưa?
8. Nếu dùng `Map.copyOf`, có đang giả định thứ tự iteration được giữ không?
9. Có nguy cơ rỗng làm `Optional.orElseThrow` ném exception không? Đó là chính sách đúng chứ?
10. Có đang tích lũy toàn bộ List chỉ để tính `count`, `sum` hoặc `max` có collector trực tiếp không?
11. Nếu chạy parallel, side effect trong lambda/finisher có được kiểm soát và có tránh shared mutable state không?
12. Có dùng chi tiết implementation của `Collectors.toList()` thay cho hợp đồng Javadoc không?
13. Có unit test bao phủ kết quả thường, nhiều nhóm, nhóm rỗng, null, thứ tự và khả năng sửa không?

## 16. Tổng kết và nguồn tham khảo

**`Collectors.collectingAndThen(downstream, finisher)` tạo một collector kết hợp: trước tiên downstream thu dữ liệu thành `R`, sau đó finisher biến `R` thành `RR`.** Nó phù hợp khi đầu ra collector cần bước hoàn thiện rõ ràng, đặc biệt ở **downstream của `groupingBy`** hoặc khi chuyển `Optional`/thống kê thành giá trị nghiệp vụ.

Hãy phân biệt các tầng: `map`/`Collectors.mapping` xử lý từng phần tử; `collectingAndThen` xử lý **kết quả đã thu**. Có thể dùng `List.copyOf` để trả List unmodifiable, nhưng nó **từ chối null và không deep-copy element**. Nếu nhóm dữ liệu, hoàn thiện List con không tự làm Map ngoài unmodifiable; Map cần chính sách riêng. `Map.copyOf` cũng không cam kết giữ thứ tự iteration.

Cuối cùng, không dùng `collectingAndThen` cho mọi pipeline: `Stream.toList()`, `toUnmodifiableList()`, `count()`, `summingInt()` hoặc `summarizingInt()` có thể trực tiếp, dễ đọc và ít phải lưu trung gian hơn. Chọn kỹ thuật theo **hợp đồng dữ liệu cần trả**, đặc biệt kiểu kết quả, khả năng sửa, null, hiệu năng và vòng đời ngoại lệ.

Tài liệu chính thức: Javadoc Java SE 17 của `java.util.stream.Collectors` (mục `collectingAndThen`, `mapping`, `groupingBy`, `summarizingInt`, `maxBy`), `java.util.stream.Collector` và `Collector.Characteristics`, `java.util.stream.Stream`, `java.util.List.copyOf`, `java.util.Map.copyOf` và `java.util.Optional`.
