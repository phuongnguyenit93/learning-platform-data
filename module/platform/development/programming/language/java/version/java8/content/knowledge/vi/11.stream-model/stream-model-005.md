# Stateless, stateful và short-circuit trong mô hình Java Stream

## 1. Mục tiêu học tập

Stream API, được giới thiệu từ Java 8 và **vẫn được sử dụng rộng rãi trên JDK hiện đại**, cung cấp cách mô tả một chuỗi xử lý dữ liệu dưới dạng **pipeline**. Để viết code đúng và có thể dự đoán hiệu năng, cần phân biệt **ba khái niệm không đồng nghĩa**:

1. **Stateless intermediate operation** — thao tác trung gian xử lý phần tử mà không cần nhớ dữ liệu của phần tử trước đó; ví dụ `filter`, `map`.
2. **Stateful intermediate operation** — thao tác trung gian cần trạng thái giữa nhiều phần tử hoặc phải quan sát một phần/lượng lớn đầu vào; ví dụ `distinct`, `sorted`, `skip`, `limit`.
3. **Short-circuiting operation** — thao tác *có khả năng* kết thúc mà không cần xử lý toàn bộ đầu vào, hoặc biến luồng vô hạn thành luồng hữu hạn. Ví dụ `limit` (intermediate), `findFirst`, `anyMatch` (terminal).

Một operation **có thể vừa stateful vừa short-circuiting**, như `limit(n)`. Ngược lại, `sorted()` là stateful nhưng **không phải short-circuiting**; `skip(n)` cũng stateful nhưng **không** được phân loại là short-circuiting. Đây là khác biệt cốt lõi của bài.

Sau khi học, bạn sẽ:

- Nhận diện pipeline gồm nguồn, intermediate operations và terminal operation.
- Phân loại chính xác những method phổ biến, kể cả `takeWhile`/`dropWhile` của Java 9+.
- Hiểu lazy evaluation, fusion, buffering và vì sao có những thao tác không thể phát output sớm.
- Biết khi nào một pipeline chứa short-circuit vẫn **không thể kết thúc** trên nguồn vô hạn.
- Tránh side effects và stateful lambda, đặc biệt trong parallel stream.
- Phân tích tác động của encounter order tới `distinct`, `limit`, `findFirst` và parallel processing.
- Chạy chương trình Java đầy đủ có stdout xác định và tự thiết kế test cho các tình huống biên.

Bài dùng các quy tắc đang được mô tả trong **Java Stream API chính thức hiện hành**. Ví dụ đầy đủ chỉ cần Java 8 APIs để chạy dễ dàng trên JDK được bảo trì với `--release 8`; những tính năng xuất hiện từ Java 9 trở đi được đánh dấu riêng, không giả vờ có trong Java 8.

## 2. Một Stream pipeline thực sự hoạt động thế nào?

Cấu trúc tổng quát:

~~~text
Source (List / array / IntStream / generator / I/O)
   |
   v
Intermediate 1: filter(...)
   |
   v
Intermediate 2: map(...)
   |
   v
Intermediate 3: limit(...)
   |
   v
Terminal: collect(...) / count() / findFirst() / anyMatch()
   |
   v
Result
~~~

Ví dụ:

~~~java
List<Integer> output = Arrays.asList(1, 2, 3, 4, 5, 6)
    .stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .limit(2)
    .collect(java.util.stream.Collectors.toList());
// output = [20, 40]
~~~

Đoạn trên minh họa pipeline, không phải file Java độc lập. Cách diễn giải:

- **Nguồn:** `List<Integer>` có encounter order `1,2,3,4,5,6`.
- **`filter`:** chỉ giữ số chẵn, một operation trung gian **stateless**.
- **`map`:** nhân 10 cho số đã qua filter, operation trung gian **stateless**.
- **`limit(2)`:** chỉ cho tối đa hai kết quả đi tiếp, operation trung gian **stateful + short-circuiting**.
- **`collect`:** terminal operation bắt đầu thực thi pipeline và tập hợp kết quả.

### Lazy evaluation là đặc tính nền

Intermediate operations nói chung **không xử lý phần tử ngay khi bạn gọi** `filter/map/limit`. Chúng tạo mô tả pipeline; phần lớn công việc xảy ra khi terminal operation khởi chạy.

~~~java
java.util.stream.Stream<Integer> pipeline =
    java.util.stream.Stream.of(1, 2, 3)
        .map(n -> n * 10);       // Chưa bắt đầu duyệt nguồn.

java.util.List<Integer> list =
    pipeline.collect(java.util.stream.Collectors.toList());
// list = [10, 20, 30]
~~~

Với pipeline tuần tự gồm các thao tác stateless, framework thường có thể xử lý một phần tử qua nhiều stage trước khi chuyển sang phần tử tiếp theo. Cách triển khai có thể được tối ưu; **không** xem số lần thực thi lambda hoặc thứ tự side effects là hợp đồng công khai cho mọi pipeline.

**Stream không phải collection.** Stream thường không chứa toàn bộ dữ liệu như một `List` và một đối tượng stream được thiết kế để **tiêu thụ một lần**. Sau khi chạy terminal operation, hãy tạo stream mới nếu cần phân tích cùng dữ liệu theo cách khác.

## 3. Stateless operations: không cần nhớ các phần tử trước

**Stateless intermediate operation** không giữ trạng thái từ các phần tử đã đi qua để quyết định cách xử lý phần tử hiện tại. Các ví dụ phổ biến:

| Operation | Chức năng | Phân loại |
| --- | --- | --- |
| `filter(Predicate)` | Chọn phần tử thỏa predicate | Stateless intermediate |
| `map(Function)` | Chuyển từng phần tử sang giá trị khác | Stateless intermediate |
| `mapToInt`, `mapToLong`, `mapToDouble` | Ánh xạ sang primitive stream | Stateless intermediate |
| `flatMap(Function)` | Thay một phần tử bằng các phần tử từ stream khác | Stateless intermediate |
| `peek(Consumer)` | Quan sát phần tử đi qua để debug/side effect | Stateless intermediate, **không** bảo đảm mọi action đều chạy |

~~~java
java.util.List<String> names =
    java.util.Arrays.asList(" Lan ", "Minh", "  An");

java.util.List<String> normalized = names.stream()
    .map(String::trim)
    .filter(s -> s.length() >= 3)
    .collect(java.util.stream.Collectors.toList());
// [Lan, Minh]
~~~

Lưu ý `"  An".trim()` thành `"An"` có độ dài 2 nên bị loại. Mỗi lần gọi `trim` và kiểm độ dài chỉ cần **giá trị đang xét**, không phải kết quả từ phần tử trước.

### Stateless operation khác stateless lambda

Một thao tác `map` **được định nghĩa** là stateless nhưng **lambda truyền vào có thể vi phạm yêu cầu stateless**:

~~~java
int[] counter = {0};
java.util.List<Integer> bad =
    java.util.Arrays.asList(1, 2, 3).stream()
        .map(n -> n + ++counter[0])
        .collect(java.util.stream.Collectors.toList());
~~~

Code này không phải một lựa chọn an toàn cho stream pipeline: lambda thay đổi trạng thái được chia sẻ, khiến kết quả phụ thuộc cách duyệt, tối ưu hóa và nhất là parallel execution. Dù bạn thấy một output cụ thể trên máy mình, **không nên biến nó thành hợp đồng của pipeline**.

Viết thuần hàm:

~~~java
java.util.List<Integer> good =
    java.util.Arrays.asList(1, 2, 3).stream()
        .map(n -> n * 2)
        .collect(java.util.stream.Collectors.toList());
// [2, 4, 6]
~~~

**Non-interfering** nghĩa là các behavioral parameters không được thay đổi nguồn dữ liệu đang được stream duyệt (trừ trường hợp nguồn concurrent được thiết kế phù hợp). **Stateless** nghĩa là kết quả của phép xử lý không được phụ thuộc trạng thái thay đổi theo quá trình pipeline. Hai điều kiện này liên quan nhưng **không đồng nhất**.

## 4. Stateful operations: phải nhớ, sắp xếp hoặc đếm phần tử

**Stateful intermediate operation** có thể cần nhớ thông tin từ các phần tử trước đó, giữ buffer, hoặc quan sát đủ đầu vào trước khi phát một số kết quả.

| Operation | Vì sao stateful? | Có short-circuit không? |
| --- | --- | --- |
| `distinct()` | Cần biết giá trị nào đã gặp, dùng quan hệ `equals` (và thường `hashCode`) | Không được phân loại short-circuit |
| `sorted()` | Cần đủ dữ liệu để quyết định thứ tự sắp xếp | Không |
| `sorted(Comparator)` | Cần so sánh/sắp xếp nhiều phần tử | Không |
| `limit(n)` | Phải đếm đã phát bao nhiêu phần tử | **Có** |
| `skip(n)` | Phải đếm đã bỏ bao nhiêu phần tử | Không |
| `takeWhile(predicate)` — Java 9+ | Cần biết ranh giới prefix phù hợp | **Có** |
| `dropWhile(predicate)` — Java 9+ | Cần biết đã qua prefix cần bỏ chưa | Không |

**Quan trọng:** Stateful **không tự động** có nghĩa phải buffer **toàn bộ** input. `limit` và `skip` chủ yếu cần trạng thái đếm; `distinct` có thể cần tập giá trị đã thấy; `sorted` thường cần tất cả dữ liệu hữu hạn trước khi có thể sắp xếp chính xác. Nhu cầu bộ nhớ và mức chặn dữ liệu khác nhau rất lớn.

### 4.1. `distinct()`: uniqueness và encounter order

~~~java
java.util.List<Integer> values =
    java.util.Arrays.asList(3, 1, 3, 2, 1);

java.util.List<Integer> unique = values.stream()
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [3, 1, 2]
~~~

Với **ordered stream**, `distinct` giữ phần tử đầu tiên trong encounter order trong nhóm bằng nhau. Với unordered stream, không có bảo đảm “giữ occurrence đầu tiên”. Khi làm việc với object của ứng dụng, correctness của `equals`/`hashCode` đặc biệt quan trọng; một object mutable đổi hash khi đang được xử lý có thể làm kết quả khó dự đoán.

Ở parallel pipeline có encounter order, bảo đảm stable distinct có thể tốn buffer và synchronization hơn sequential processing. Chỉ dùng `unordered()` nếu nghiệp vụ **không cần** bảo toàn thứ tự.

### 4.2. `sorted()`: phải nhìn đủ input

~~~java
java.util.List<Integer> sorted =
    java.util.Arrays.asList(5, 1, 4, 2, 3)
        .stream()
        .sorted()
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 3, 4, 5]
~~~

Muốn khẳng định phần tử nhỏ nhất của dữ liệu, bộ sắp xếp cần xét toàn bộ nguồn hữu hạn tương ứng. Vì thế, với **nguồn vô hạn**, pipeline `Stream.iterate(...).sorted().findFirst()` thường không thể trả về kết quả dù có `findFirst` ở cuối: operation `sorted` phải xác định thứ tự trước.

`sorted()` không comparator yêu cầu các phần tử tương thích với natural ordering; nếu không, việc thực thi có thể ném `ClassCastException`. `sorted(comparator)` yêu cầu comparator nhất quán và không can thiệp vào nguồn; nếu comparator dùng state thay đổi, correctness có thể hỏng.

### 4.3. `limit(n)`: stateful **và** short-circuit

~~~java
java.util.List<Integer> firstThree =
    java.util.stream.Stream.iterate(10, n -> n + 1)
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
// [10, 11, 12]
~~~

`Stream.iterate(seed, next)` có thể sinh vô hạn, nhưng `limit(3)` giữ **tối đa** 3 phần tử nên kết quả của pipeline này hữu hạn. Đây là ví dụ mạnh cho short-circuit intermediate. Nếu `n == 0`, output rỗng; nếu `n < 0`, `limit` ném `IllegalArgumentException`.

Ở parallel ordered stream, `limit(n)` có thể tốn kém vì phải giữ **n phần tử đầu theo encounter order**, không phải bất kỳ n phần tử nào. `unordered()` chỉ thích hợp nếu thay đổi về thứ tự được nghiệp vụ cho phép.

### 4.4. `skip(n)`: stateful nhưng không short-circuit

~~~java
java.util.List<Integer> page =
    java.util.Arrays.asList(1, 2, 3, 4, 5, 6)
        .stream()
        .skip(2)
        .collect(java.util.stream.Collectors.toList());
// [3, 4, 5, 6]
~~~

`skip(2)` nhớ rằng cần bỏ hai phần tử đầu, nhưng sau đó vẫn để các phần tử còn lại đi tiếp: **nó không giới hạn luồng đầu ra thành hữu hạn** nếu nguồn ban đầu vô hạn.

~~~java
// Vẫn tạo ra vô hạn nếu terminal cần thu toàn bộ:
// Stream.iterate(0, n -> n + 1).skip(100).collect(Collectors.toList());
~~~

Khi muốn phân trang trên nguồn hữu hạn, có thể kết hợp `skip(offset).limit(pageSize)` nhưng phải cân nhắc chi phí bỏ qua offset lớn, và semantics ổn định của nguồn giữa nhiều lần phân trang.

## 5. Short-circuit là thuộc tính độc lập với stateful/stateless

Một **intermediate operation** là *short-circuiting* nếu, khi nhận một nguồn vô hạn, nó **có thể** tạo stream hữu hạn. Một **terminal operation** là *short-circuiting* nếu, khi nhận nguồn vô hạn, nó **có thể** hoàn tất trong thời gian hữu hạn.

Từ **có thể** quan trọng: không phải mọi lần chạy đều thoát sớm. Chẳng hạn `anyMatch(x -> x < 0)` trên dãy số nguyên không âm vô hạn sẽ không tìm thấy phần tử phù hợp; dù `anyMatch` là short-circuit terminal, nó có thể **không bao giờ kết thúc**.

### Các terminal short-circuit thường dùng

| Terminal | Trả về | Điều kiện có thể dừng sớm |
| --- | --- | --- |
| `anyMatch(predicate)` | `boolean` | Tìm thấy ít nhất một phần tử phù hợp |
| `allMatch(predicate)` | `boolean` | Tìm thấy ít nhất một phần tử **không** phù hợp |
| `noneMatch(predicate)` | `boolean` | Tìm thấy ít nhất một phần tử phù hợp |
| `findFirst()` | `Optional<T>` | Tìm phần tử đầu theo encounter order nếu được xác định |
| `findAny()` | `Optional<T>` | Tìm một phần tử bất kỳ, hữu ích khi parallel |

~~~java
java.util.List<Integer> numbers =
    java.util.Arrays.asList(1, 2, 3, 4, 5, 6);

boolean hasEven = numbers.stream().anyMatch(n -> n % 2 == 0); // true
boolean allPositive = numbers.stream().allMatch(n -> n > 0);  // true
boolean noNegative = numbers.stream().noneMatch(n -> n < 0);  // true
java.util.Optional<Integer> firstEven =
    numbers.stream().filter(n -> n % 2 == 0).findFirst();      // Optional[2]
~~~

Mỗi terminal dùng **một stream mới**, không tái sử dụng stream sau terminal. Những lời gọi này có thể dừng sớm theo điều kiện, nhưng Stream implementation có thể duyệt/đánh giá khác trong parallel mode và có quyền tối ưu hóa theo hợp đồng.

### Các terminal thường không short-circuit

`collect`, `toArray`, `count`, `reduce`, `sum` (primitive stream), `forEach` thường cần xử lý toàn bộ input còn lại để tạo kết quả tổng thể. Một số terminal như `count` có thể được tối ưu hóa nhờ biết kích thước nguồn mà **không gọi các lambda trung gian**; điều này không khiến `count` trở thành một general short-circuit operation.

Đừng dự đoán số lần gọi `peek`/`map` dựa trên `count`: Java được phép loại bớt các stage khi có thể chứng minh kết quả không đổi.

### Trường hợp stream rỗng: vacuous truth

~~~java
boolean any = java.util.stream.Stream.<Integer>empty()
    .anyMatch(n -> n > 0);    // false

boolean all = java.util.stream.Stream.<Integer>empty()
    .allMatch(n -> n > 0);    // true

boolean none = java.util.stream.Stream.<Integer>empty()
    .noneMatch(n -> n > 0);   // true
~~~

- `anyMatch` là false vì không có phần tử thỏa.
- `allMatch` là true vì **không có phản ví dụ**.
- `noneMatch` là true vì không phần tử nào thỏa.

Đây là quy tắc logic đúng của Stream API, không phải bug. Các predicate ở đây không cần được gọi trên stream rỗng.

## 6. Lazy + short-circuit: vì sao xử lý ít phần tử hơn?

Xét pipeline tuần tự, nguồn ordered:

~~~java
java.util.List<Integer> numbers =
    java.util.Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

java.util.List<Integer> result = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .limit(2)
    .collect(java.util.stream.Collectors.toList());
// result = [20, 40]
~~~

Đối với việc duyệt tuần tự bằng pipeline này, hai giá trị thỏa đầu tiên xuất hiện sau khi đọc `1,2,3,4`. Sau khi có hai phần tử qua `limit`, nguồn không cần được duyệt tiếp để trả kết quả. Khi tối ưu hóa, **đúng kết quả cuối cùng** là hợp đồng; không nên nói mọi implementation/parallel mode chắc chắn gọi một lambda đúng 4 lần trong mọi trường hợp.

Sơ đồ minh họa cho duyệt tuần tự:

~~~text
Source   filter even?   map *10   limit(2)   collect
1        no             —         —          —
2        yes            20        first      [20]
3        no             —         —          [20]
4        yes            40        second     [20,40]
5..8     not needed in this sequential traversal
~~~

Một ưu điểm quan trọng của **stateless intermediate operations** là có thể kết hợp theo từng phần tử (*fusion*) mà không cần materialize list giữa `filter` và `map`. Stateful stages như `sorted` có thể tạo một **barrier** khiến không thể truyền kết quả ngay theo kiểu đó.

### Thứ tự stage có thể đổi cả hiệu năng và kết quả

~~~java
java.util.List<Integer> a = java.util.Arrays.asList(5, 1, 4, 2, 3)
    .stream().limit(2).sorted()
    .collect(java.util.stream.Collectors.toList());
// [1, 5]

java.util.List<Integer> b = java.util.Arrays.asList(5, 1, 4, 2, 3)
    .stream().sorted().limit(2)
    .collect(java.util.stream.Collectors.toList());
// [1, 2]
~~~

- `limit(2).sorted()` chọn hai phần tử **theo encounter order trước**, rồi sắp xếp chúng.
- `sorted().limit(2)` sắp xếp **toàn bộ nguồn trước**, rồi chọn hai phần tử nhỏ nhất.

Đây là hai bài toán khác nhau. Không “tối ưu” bằng cách hoán vị operations mà chưa chứng minh tương đương về semantics.

## 7. Nguồn vô hạn và nguyên tắc kết thúc

Nguồn vô hạn thường gặp:

~~~java
java.util.stream.Stream<Integer> infinite =
    java.util.stream.Stream.iterate(0, n -> n + 1);
~~~

Đừng gọi một terminal bắt buộc tiêu thụ toàn bộ nguồn trên stream vô hạn, trừ khi pipeline **bảo đảm** chặn lại. So sánh:

~~~java
// Hoàn tất: cắt xuống hữu hạn trước khi sort.
java.util.List<Integer> ok =
    java.util.stream.Stream.iterate(0, n -> n + 1)
        .limit(5)
        .sorted(java.util.Comparator.reverseOrder())
        .collect(java.util.stream.Collectors.toList());
// [4, 3, 2, 1, 0]
~~~

~~~java
// KHÔNG chạy: sorted() cần toàn bộ nguồn vô hạn trước limit().
// Stream.iterate(0, n -> n + 1)
//     .sorted()
//     .limit(5)
//     .collect(Collectors.toList());
~~~

Dòng thứ hai được **comment** vì có thể không kết thúc và/hoặc tiêu tốn tài nguyên. `limit` đứng sau `sorted` không thể giúp `sorted` hoàn thành trên nguồn vô hạn chưa được ràng buộc.

Một ví dụ khác:

~~~java
// Không có phần tử âm nào: dù anyMatch là short-circuit,
// pipeline không tìm được điều kiện dừng trên luồng này.
// Stream.iterate(0, n -> n + 1)
//     .anyMatch(n -> n < 0);
~~~

Ngược lại:

~~~java
boolean found = java.util.stream.Stream.iterate(0, n -> n + 1)
    .anyMatch(n -> n == 3);
// true: có thể dừng khi thấy số 3.
~~~

**Quy tắc thực dụng:** Có short-circuit ở đâu đó trong pipeline là **điều kiện có thể cần**, không phải bảo đảm đủ để một tính toán trên stream vô hạn kết thúc. Xem cả các stage ở trước nó và việc điều kiện dừng có bao giờ được thỏa hay không.

### Nguồn vô hạn thực sự và rủi ro overflow

`Stream.iterate(0, n -> n + 1)` là nguồn không có điều kiện chấm dứt; với `Integer`, nếu một chương trình duyệt đủ lâu, phép cộng có thể overflow theo luật Java. Ví dụ sử dụng nó **chỉ** với giới hạn/dừng sớm ở số rất nhỏ, không gợi ý xây một lịch sử số nguyên vô hạn có giá trị tăng không giới hạn.

## 8. Java 9+: `takeWhile` và `dropWhile` không phải `filter`

Hai operations này xuất hiện từ **Java 9** và vẫn có trong Stream API hiện đại. Chúng hoạt động với **prefix** trên ordered stream, khác `filter` xét từng phần tử độc lập.

~~~java
java.util.List<Integer> values =
    java.util.Arrays.asList(1, 2, 3, 0, 4, 5);

// Dùng JDK 9+:
java.util.List<Integer> taken = values.stream()
    .takeWhile(n -> n > 0)
    .collect(java.util.stream.Collectors.toList());
// [1, 2, 3]

java.util.List<Integer> dropped = values.stream()
    .dropWhile(n -> n > 0)
    .collect(java.util.stream.Collectors.toList());
// [0, 4, 5]

java.util.List<Integer> filtered = values.stream()
    .filter(n -> n > 0)
    .collect(java.util.stream.Collectors.toList());
// [1, 2, 3, 4, 5]
~~~

- `takeWhile` trên ordered stream trả **longest matching prefix**: gặp số 0 thì dừng phần prefix và không lấy 4/5. Đây là **short-circuiting stateful intermediate**.
- `dropWhile` trên ordered stream **bỏ** matching prefix cho đến số 0, rồi cho các phần tử tiếp theo đi qua, kể cả nếu chúng thỏa predicate. Đây là **stateful nhưng không short-circuiting**.
- `filter` giữ mọi số dương ở bất kỳ vị trí nào, là **stateless**, không làm việc theo prefix.

Không biên dịch các đoạn này với `--release 8` vì Java 8 **chưa có** `takeWhile`/`dropWhile`. Sử dụng `javac --release 17` hoặc release khác thật sự được dự án hỗ trợ khi minh họa code Java 9+.

### Với unordered stream, kết quả có thể khác

Trên **unordered stream**, không có “longest prefix” theo encounter order để áp dụng giống `List.stream()`. Javadoc cho phép `takeWhile` lấy một **subset** phù hợp (có thể rỗng), `dropWhile` loại một **subset** phù hợp (có thể rỗng), không có nghĩa lấy/bỏ một prefix ổn định. Nếu nghiệp vụ yêu cầu “lấy mọi phần tử thỏa predicate”, dùng `filter` thay vì `takeWhile` trên unordered stream.

## 9. Encounter order, unordered và parallel stream

**Encounter order** là thứ tự phần tử được nguồn/pipeline xác định. `List.stream()` và array stream có thứ tự; một số nguồn khác như `HashSet` không cung cấp encounter order hữu ích. `unordered()` có thể bỏ yêu cầu duy trì thứ tự, nhưng **không có nghĩa đảo ngược hay ngẫu nhiên hóa dữ liệu một cách bắt buộc**.

| Thao tác | Có order | Không có order |
| --- | --- | --- |
| `findFirst()` | Đảm bảo phần tử đầu theo encounter order nếu có phần tử | Không có phần tử “đầu” có nghĩa cố định |
| `findAny()` | Có thể trả bất kỳ phần tử phù hợp | Có thể trả bất kỳ phần tử phù hợp |
| `distinct()` | Stable: giữ occurrence đầu của mỗi giá trị | Không đảm bảo occurrence đầu |
| `limit(n)` | Lấy n phần tử đầu theo order nếu có | Có thể lấy bất kỳ n phần tử phù hợp của nguồn |
| `skip(n)` | Bỏ n phần tử đầu theo order | Không có khái niệm “n phần tử đầu” ổn định |
| `takeWhile`/`dropWhile` | Xử lý longest matching prefix | Semantics subset theo Javadoc |
| `forEach()` trong parallel | Không đảm bảo thứ tự action | Không đảm bảo thứ tự action |

### `findFirst` và `findAny` trong parallel

~~~java
java.util.List<Integer> numbers =
    java.util.Arrays.asList(10, 20, 30, 40);

int first = numbers.parallelStream()
    .findFirst().orElse(-1);   // 10: List là ordered stream.
~~~

`findFirst()` phải tuân thủ encounter order khi stream có order. `findAny()` cố ý cho phép chọn bất kỳ phần tử nào và thường giảm ràng buộc đồng bộ trong parallel processing. Đừng viết test khẳng định `findAny()` luôn là 10, hoặc luôn chọn phần tử từ thread cụ thể.

### Parallel không đương nhiên nhanh hơn

Các stateful operations có thể đòi buffer/synchronization và xử lý nhiều bước. Với `distinct` trên ordered parallel stream, tính ổn định có thể buộc dùng full barrier/bộ nhớ lớn. Với `limit`/`skip` trên ordered parallel stream, việc đảm bảo **đúng n phần tử đầu** có thể đắt.

Cân nhắc `unordered()` nếu kết quả không cần order, nhưng chỉ sau khi test lại **semantics**. Nếu order là một phần API contract, không thể đổi `unordered()` đơn thuần vì benchmark nhanh hơn.

### Khác biệt giữa `forEach` và `forEachOrdered`

`forEach` ở parallel stream có thể chạy action ở nhiều thread và không theo encounter order. `forEachOrdered` tôn trọng encounter order cho action trên ordered stream, nhưng không có nghĩa tất cả operations trước đó đều được thực hiện tuần tự, hoặc tất cả lambda chạy trên cùng thread. Nếu cần danh sách kết quả có thứ tự, `collect` vào container thích hợp thường rõ hơn một tác dụng phụ `println`.

## 10. Side effects và tối ưu hóa pipeline

Stream API khuyến khích các behavioral parameters **non-interfering** và **stateless**. Những side effects như tăng counter, ghi vào một `ArrayList` dùng chung, gọi network hoặc mutate object đang ở nguồn có thể làm pipeline khó kiểm thử và đặc biệt dễ sai trong parallel mode.

### `peek` không phải contract của chương trình

~~~java
long count = java.util.Arrays.asList(1, 2, 3)
    .stream()
    .peek(System.out::println)
    .count();
~~~

Đừng khẳng định chương trình này luôn in ba dòng. Với một nguồn `SIZED` và pipeline không làm đổi số phần tử, Stream implementation có thể xác định `count() == 3` mà không cần duyệt phần tử hoặc thực hiện action của `peek`. Javadoc nêu rõ một số behavioral parameters có thể **không được gọi** nếu việc bỏ qua không làm đổi kết quả.

Dùng `peek` chủ yếu cho debug, đừng đặt audit, billing, metrics bắt buộc hay cập nhật trạng thái nghiệp vụ chỉ trong `peek`. Muốn bảo đảm xử lý một hành động cho mọi phần tử theo contract, thiết kế terminal operation phù hợp hoặc sử dụng vòng lặp rõ ràng, nhưng vẫn cần quản lý lỗi, concurrency và idempotence.

### Vì sao stateful lambdas nguy hiểm?

~~~java
java.util.List<Integer> output = new java.util.ArrayList<Integer>();

// Tránh dùng trên parallel stream:
// numbers.parallelStream().forEach(output::add);
~~~

`ArrayList` thông thường không thread-safe. Ghi đồng thời có thể mất phần tử, lỗi hoặc kết quả sai. Sử dụng:

~~~java
java.util.List<Integer> output =
    java.util.Arrays.asList(1, 2, 3).parallelStream()
        .map(n -> n * 2)
        .collect(java.util.stream.Collectors.toList());
~~~

Dùng collector thích hợp để tránh mutable shared accumulator do chính ứng dụng quản lý. `Collectors.toList()` không cam kết concrete list type hoặc mutability; nếu cần một `ArrayList` mutable cụ thể, chọn collector phù hợp, ví dụ `Collectors.toCollection(ArrayList::new)`.

### Đừng dựa vào số lần chạy của predicate trong parallel

`anyMatch` và `findAny` có thể đạt kết quả mà không cần đánh giá mọi phần tử, nhưng các tác vụ song song đã bắt đầu có thể chạy đồng thời và kiểm tra nhiều phần tử hơn số tối thiểu. Viết test theo **giá trị trả về** hoặc hiệu ứng được contract bảo đảm, không theo một số đếm predicate tưởng tượng.

## 11. Chương trình Java chạy độc lập: quan sát ba loại operation

Tạo file **`StreamOperationModesDemo.java`** với UTF-8. Chương trình dùng APIs có từ Java 8; biên dịch được trên một JDK hiện đại có hỗ trợ target Java 8.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class StreamOperationModesDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
            Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

        AtomicInteger visited = new AtomicInteger();

        Stream<Integer> pipeline = numbers.stream()
            .filter(n -> {
                visited.incrementAndGet();
                return n % 2 == 0;
            })
            .map(n -> n * 10)
            .limit(2);

        System.out.println("lazy-before: " + visited.get());

        List<Integer> result =
            pipeline.collect(Collectors.toList());

        System.out.println("result: " + result);
        System.out.println("visited: " + visited.get());

        List<Integer> unique = Arrays.asList(3, 1, 3, 2, 1)
            .stream()
            .distinct()
            .collect(Collectors.toList());
        System.out.println("distinct: " + unique);

        List<Integer> sorted = Arrays.asList(5, 1, 4, 2, 3)
            .stream()
            .sorted()
            .collect(Collectors.toList());
        System.out.println("sorted: " + sorted);

        List<Integer> page = numbers.stream()
            .skip(2)
            .limit(3)
            .collect(Collectors.toList());
        System.out.println("skip-limit: " + page);

        Optional<Integer> first = numbers.stream()
            .filter(n -> n > 3)
            .findFirst();
        System.out.println("findFirst: " + first);

        boolean any = numbers.stream().anyMatch(n -> n == 7);
        System.out.println("anyMatch: " + any);

        System.out.println("anyMatch-empty: "
            + Stream.<Integer>empty().anyMatch(n -> n > 0));
        System.out.println("allMatch-empty: "
            + Stream.<Integer>empty().allMatch(n -> n > 0));
        System.out.println("noneMatch-empty: "
            + Stream.<Integer>empty().noneMatch(n -> n > 0));

        List<Integer> finite = Stream.iterate(10, n -> n + 1)
            .limit(4)
            .collect(Collectors.toList());
        System.out.println("infinite-first: " + finite);
    }
}
~~~

**Chạy bằng javac/java:**

~~~text
javac --release 8 -encoding UTF-8 StreamOperationModesDemo.java
java StreamOperationModesDemo
~~~

**Stdout dự kiến chính xác (12 dòng):**

~~~text
lazy-before: 0
result: [20, 40]
visited: 4
distinct: [3, 1, 2]
sorted: [1, 2, 3, 4, 5]
skip-limit: [3, 4, 5]
findFirst: Optional[4]
anyMatch: true
anyMatch-empty: false
allMatch-empty: true
noneMatch-empty: true
infinite-first: [10, 11, 12, 13]
~~~

### Giải thích tại sao ra đúng output

1. Trước terminal `collect`, lazy pipeline chưa được duyệt: counter bằng 0.
2. Trên **sequential ordered pipeline trong ví dụ**, `filter` xét `1,2,3,4` để tìm hai số chẵn đầu tiên; `map` tạo 20 và 40; `limit(2)` chặn các phần tử tiếp theo. Vì vậy in `visited: 4`. Đây là **minh họa việc duyệt của trường hợp cụ thể**, không phải lời hứa số lần gọi với mọi optimizer/parallel stream.
3. `distinct` trên ordered stream giữ các giá trị lần đầu gặp: `3,1,2`.
4. `sorted` đợi các giá trị hữu hạn để sắp xếp tự nhiên: `1,2,3,4,5`.
5. `skip(2).limit(3)` bỏ 1 và 2, lấy 3,4,5.
6. `findFirst` sau filter `n > 3` trả `Optional[4]`.
7. `anyMatch(n -> n == 7)` trả true vì có phần tử 7.
8. Ba kết quả trên stream rỗng là false/true/true theo logic `anyMatch`/`allMatch`/`noneMatch`.
9. `Stream.iterate` tạo nguồn không có giới hạn nội tại; `limit(4)` đưa ra bốn giá trị 10–13 rồi dừng.

**Không dùng AtomicInteger như một thiết kế stream production chỉ để đếm predicate calls.** Nó được dùng để biểu diễn lazy evaluation và điểm dừng trong một test giáo dục tuần tự. Một chương trình thật thường không cần quan sát side effects của lambda như một output nghiệp vụ.

## 12. Test sau khi hiểu khái niệm: phân loại đúng hơn là nhớ tên

### Tình huống A — Pipeline toàn stateless, terminal đầy đủ

~~~java
long count = java.util.Arrays.asList("a", "bb", "ccc").stream()
    .map(String::length)
    .filter(length -> length >= 2)
    .count();
// 2
~~~

`map` và `filter` là stateless. `count` là terminal; pipeline hữu hạn nên kết thúc. **Không** suy ra map luôn được gọi một lần cho mọi phần tử trong mọi biến thể, vì optimizer được phép thay đổi cách duyệt nếu kết quả giữ nguyên.

### Tình huống B — Stateful sorted trước limit

~~~java
java.util.List<Integer> topTwo = java.util.Arrays.asList(9, 1, 8, 2)
    .stream().sorted().limit(2)
    .collect(java.util.stream.Collectors.toList());
// [1, 2]
~~~

Hai operation trung gian đều stateful, nhưng chỉ `limit` là short-circuit. `sorted` phải có đủ dữ liệu đầu vào để xác định đầu ra. Trên nguồn vô hạn, `limit` đứng sau `sorted` không “cứu” được pipeline.

### Tình huống C — Kết hợp filter và anyMatch

~~~java
boolean result = java.util.Arrays.asList(1, 2, 3, 4, 5)
    .stream()
    .filter(n -> n % 2 == 0)
    .anyMatch(n -> n >= 4);
// true
~~~

`filter` stateless; `anyMatch` terminal short-circuit. Nó có thể trả true khi gặp số 4 và không cần xét giá trị 5 ở pipeline tuần tự này.

### Tình huống D — `distinct` trước limit

~~~java
java.util.List<Integer> result =
    java.util.Arrays.asList(2, 2, 2, 4, 4, 6, 8)
        .stream()
        .distinct()
        .limit(2)
        .collect(java.util.stream.Collectors.toList());
// [2, 4]
~~~

`distinct` nhớ giá trị đã gặp, `limit` đếm kết quả **sau khi distinct**. Vì vậy cần xét đủ phần tử để thấy **hai giá trị khác nhau**, không chỉ hai phần tử đầu tiên của nguồn.

### Tình huống E — `limit` trước distinct

~~~java
java.util.List<Integer> result =
    java.util.Arrays.asList(2, 2, 2, 4, 4, 6, 8)
        .stream()
        .limit(2)
        .distinct()
        .collect(java.util.stream.Collectors.toList());
// [2]
~~~

Lúc này `limit(2)` lấy `2,2`, rồi `distinct` rút còn một giá trị. Hai pipeline D và E **không tương đương**.

### Tình huống F — Invalid arguments

~~~java
// Khi terminal kích hoạt operation, các giá trị âm là không hợp lệ:
// Stream.of(1, 2, 3).limit(-1);
// Stream.of(1, 2, 3).skip(-2);
~~~

`limit` và `skip` nhận số nguyên không âm; truyền số âm ném `IllegalArgumentException`. Không đưa offset/page size chưa validate từ người dùng thẳng vào pipeline.

## 13. Hiệu năng, bộ nhớ và cách chọn pipeline

Không có quy tắc “stateful luôn xấu” hoặc “parallel luôn nhanh”. Chọn operations theo **nghĩa vụ nghiệp vụ** trước, rồi benchmark trường hợp thực:

1. **Đẩy filter hợp lý lên trước một phép sort đắt tiền**, nếu việc đổi thứ tự giữ nguyên semantics, để giảm số phần tử cần sắp xếp.
2. Nếu chỉ cần top-k, đánh giá thuật toán heap/selection thay vì luôn `sorted().limit(k)` trên dataset cực lớn; nhưng phải giữ đúng comparator, tie-breaking và contract.
3. **`distinct` có thể dùng bộ nhớ theo số giá trị duy nhất**; với dữ liệu rất lớn hoặc không giới hạn, xác định rõ chiến lược kích thước/tài nguyên.
4. **`skip(offset)` với offset lớn** vẫn cần đi qua phần bị bỏ; trên nguồn lớn hoặc DB pagination, cân nhắc pagination tại nguồn/kho dữ liệu thay vì stream toàn bộ rồi skip.
5. Với **ordered parallel stream**, `distinct`/`limit`/`skip` có thể tạo overhead do stable encounter order. Chỉ bỏ order khi bảo đảm được tính đúng.
6. Nếu nguồn là I/O, stream traversal có thể mở tài nguyên; dùng `try-with-resources` khi Stream cần đóng (ví dụ `Files.lines`). Không giả định short-circuit làm resource tự đóng; phải đóng stream theo hợp đồng nguồn.
7. Tránh pipeline trên nguồn vô hạn đặt trước các **blocking stateful operations** không thể hoàn tất.
8. Benchmark có warm-up và workload đại diện; đừng đánh giá tốc độ dựa trên một lần chạy nhỏ hoặc số thread quan sát được từ `peek`.

Ví dụ bảo vệ resource khi chỉ cần dòng đầu tiên phù hợp:

~~~java
// Java 8+, fragment trong method có xử lý IOException:
try (java.util.stream.Stream<String> lines =
         java.nio.file.Files.lines(path)) {
    java.util.Optional<String> found = lines
        .filter(s -> s.startsWith("ERROR"))
        .findFirst();
    // Xử lý found; stream được đóng sau block.
}
~~~

`findFirst` có thể dừng traversal sớm, nhưng **không thay thế** `close()` cho stream do I/O tạo ra. Với stream từ `List` thông thường, close thường không cần cho tài nguyên bên ngoài.

## 14. Các lỗi thường gặp và cách sửa

| Hiểu sai | Điều đúng |
| --- | --- |
| “Stateful nghĩa là short-circuit.” | `sorted` và `distinct` stateful nhưng không short-circuit; `limit` vừa stateful vừa short-circuit |
| “`skip(n)` cắt luồng vô hạn về hữu hạn.” | `skip` chỉ bỏ prefix số lượng n; phần còn lại vẫn có thể vô hạn |
| “Đặt `limit` sau `sorted` là đủ cho stream vô hạn.” | `sorted` phải xem toàn bộ nguồn đầu vào trước, nên không hoàn tất |
| “`takeWhile` giống `filter`.” | Trên ordered stream, `takeWhile` xử lý prefix; `filter` giữ phần tử thỏa ở mọi vị trí |
| “`dropWhile` short-circuit.” | `dropWhile` là stateful, nhưng vẫn để phần sau prefix đi tiếp |
| “`map` luôn chạy ngay khi được gọi.” | Intermediate operations lazy; terminal khởi chạy việc tiêu thụ |
| “`peek` luôn được gọi trên mọi phần tử.” | Optimizer hoặc short-circuit có thể bỏ qua các lời gọi |
| “`findAny` trong parallel trả phần tử đầu.” | Không có bảo đảm đó; cần `findFirst` nếu bắt buộc encounter order |
| “Thêm `unordered()` không đổi semantics.” | Có thể đổi phần tử được chọn và tính ổn định; chỉ dùng khi order không quan trọng |
| “Lambda dùng mutable counter là an toàn vì `map` stateless.” | Operation stateless nhưng lambda có shared mutable state là sai thiết kế |
| “Có short-circuit nên vô hạn luôn kết thúc.” | Chỉ có khả năng; điều kiện không thỏa hoặc stage trước chặn vẫn có thể không kết thúc |
| “Có thể dùng lại một stream đã terminal.” | Stream dùng một lần; tạo stream mới từ source |
| “Parallel chắc chắn nhanh hơn.” | Stateful barriers, ordering, thread scheduling có thể làm chậm |
| “`Collectors.toList()` luôn trả `ArrayList` mutable.” | API không cam kết implementation/mutability cụ thể |

### Checklist review code

- [ ] Source hữu hạn hay có thể vô hạn; terminal operation có chặn được không?
- [ ] Các intermediate được phân loại stateless/stateful, có barrier hay buffer lớn không?
- [ ] Short-circuit nằm trước hay sau blocking stateful stage?
- [ ] Có cần encounter order không? Có dùng `findFirst` hay `findAny` phù hợp không?
- [ ] Predicate/mapper/comparator không can thiệp nguồn và không phụ thuộc mutable shared state?
- [ ] Không đặt logic quan trọng trong `peek` hoặc giả định số lần gọi lambda?
- [ ] Tài nguyên I/O stream được đóng ngay cả khi short-circuit?
- [ ] Các giới hạn `limit/skip` không âm, đã được validate?
- [ ] Stream chỉ được tiêu thụ một lần?
- [ ] Dùng API phù hợp release: `takeWhile`/`dropWhile` chỉ Java 9+, `toList()` của Stream chỉ Java 16+?
- [ ] Nếu dùng parallel, đã kiểm cả correctness, ordering, memory và performance trên dữ liệu thực?

## 15. Bài tập và hướng dẫn đáp án

**Bài 1 — Phân loại.** Với `filter`, `map`, `distinct`, `sorted`, `limit`, `skip`, `findFirst`, `anyMatch`, lập bảng stateless/stateful/intermediate/terminal/short-circuit. Đáp án cốt lõi: `filter/map` stateless intermediate; `distinct/sorted/skip` stateful intermediate không short-circuit; `limit` stateful intermediate short-circuit; `findFirst/anyMatch` terminal short-circuit.

**Bài 2 — Thứ tự operation.** Tính kết quả `Stream.of(5,1,4,2,3).limit(2).sorted()` so với `sorted().limit(2)`. Đáp án: `[1,5]` và `[1,2]`; hai pipeline không tương đương.

**Bài 3 — Distinct vs limit.** Trên `[2,2,2,4,4,6]`, tính `distinct().limit(2)` so với `limit(2).distinct()`. Đáp án: `[2,4]` và `[2]`.

**Bài 4 — Dừng sớm trên tập hữu hạn.** Từ `1..100`, tìm số chia hết cho 13 bằng `anyMatch`. Đáp án: true; trên sequential stream có thể dừng khi gặp 13. Không dùng biến side-effect để xác định số lần gọi như API contract.

**Bài 5 — Stream rỗng.** Dự đoán `anyMatch`, `allMatch`, `noneMatch` trên `Stream.empty()`. Đáp án: false/true/true.

**Bài 6 — Nguồn vô hạn.** Giải thích vì sao `Stream.iterate(0,n->n+1).sorted().limit(5).collect(...)` không hoàn tất trong mô hình thông thường. Đáp án: blocking stateful sort cần toàn bộ nguồn; đổi thành `limit(5).sorted()` nếu ý nghĩa cần sắp xếp năm phần tử đầu.

**Bài 7 — Java 9+ prefix.** Cho `[1,2,0,3,4]`, tính `takeWhile(n>0)`, `dropWhile(n>0)`, `filter(n>0)` trên ordered stream. Đáp án: `[1,2]`, `[0,3,4]`, `[1,2,3,4]`.

**Bài 8 — Parallel ordering.** So sánh `findFirst`/`findAny` trên parallel stream lấy từ `List`. Kết luận: `findFirst` bảo toàn first theo encounter order; `findAny` không bảo đảm phần tử nào. Không viết test cố định kết quả `findAny` khi có nhiều phần tử.

**Bài 9 — Debugging.** Giải thích tại sao `stream.peek(System.out::println).count()` không nhất thiết in mọi phần tử từ `List`. Đáp án: optimizer có thể dùng kích thước đã biết để trả `count` mà không gọi `peek`.

**Bài 10 — Side effects.** Sửa code `parallelStream().forEach(sharedArrayList::add)`. Đáp án: dùng `collect(Collectors.toList())` (với yêu cầu thứ tự phù hợp) hoặc collector được thiết kế, không mutate list không thread-safe từ nhiều task.

**Bài 11 — Pagination.** Với ordered `1..10`, tính `skip(3).limit(4)`. Đáp án: `[4,5,6,7]`; `skip` không short-circuit nhưng `limit` đặt sau làm output hữu hạn.

**Bài 12 — I/O stream.** Viết `try-with-resources` dùng `Files.lines`, `filter`, `findFirst`. Chứng minh stream được đóng khi kết thúc scope, kể cả khi findFirst dừng sớm.

**Bài 13 — Lựa chọn thuật toán.** Cần lấy 100 bản ghi có điểm cao nhất từ 10 triệu bản ghi. Nêu khi nào `sorted().limit(100)` hợp lệ về semantics, và vì sao có thể dùng heap top-k để giảm bộ nhớ/chi phí nếu dữ liệu, comparator và tie-breaking cho phép.

**Bài 14 — Runtime mới, syntax cũ.** Viết ví dụ `takeWhile/dropWhile` dưới `javac --release 8` và ghi nhận compile không hỗ trợ. Đổi target sang Java 17 hoặc mới hơn được dự án hỗ trợ; giải thích sự khác nhau giữa giới thiệu Stream ở Java 8 và thêm operations ở Java 9.

**Tiêu chí đạt:** Bạn không đánh đồng stateful với short-circuit; dự đoán đúng kết quả khi hoán đổi `sorted/limit` và `distinct/limit`, hiểu lazy và side effects, phân tích nguồn vô hạn, giữ được semantics order trong parallel stream, và chạy chương trình ở mục 11 khớp **12 dòng stdout**.

## 16. Tài liệu chính thức còn áp dụng

- **Java SE 25, package `java.util.stream`** — pipeline, stateless/stateful, short-circuit, non-interference, ordering, side effects: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- **Java SE 25, `java.util.stream.Stream`** — Javadoc cho `filter`, `map`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`, `findFirst`, `findAny`, `anyMatch`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **Dev.java — Intermediate operations** (tài liệu học Java hiện đại): https://dev.java/learn/api/streams/intermediate-operation/
- **Java SE 25, `BaseStream`** — encounter order và sequential/parallel: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html
- **Java SE 25, `Collectors`** — các collector và hợp đồng kết quả: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html

**Ghi nhớ:** **Stateless/stateful** mô tả lượng trạng thái mà *intermediate stage* cần giữ trong quá trình xử lý; **short-circuit** mô tả *khả năng dừng mà không tiêu thụ hết nguồn*. Hãy kiểm cả ba yếu tố — **stage type, encounter order và điều kiện kết thúc** — trước khi tối ưu hóa pipeline, đặc biệt với nguồn vô hạn hoặc parallel streams.