# Đánh giá trì hoãn của thao tác trung gian trong Java Stream

## 1. Mục tiêu bài học

Java **Stream** mô tả một quy trình xử lý dữ liệu qua nhiều công đoạn. Điểm quan trọng của mô hình này là **các thao tác trung gian (intermediate operations) được đánh giá trì hoãn — lazy evaluation**: khi gọi `map`, `filter`, `flatMap`, `sorted` hoặc `distinct`, chương trình chủ yếu **xây dựng một pipeline**, chứ chưa lập tức chạy mọi hàm trên từng phần tử.

Việc thực thi thường được kích hoạt bởi **thao tác kết thúc (terminal operation)** như `toList`, `collect`, `forEach`, `count`, `reduce`, `findFirst` hoặc `anyMatch`. Khi đó, Stream xử lý nguồn dữ liệu đủ để tạo ra kết quả được yêu cầu.

Sau bài học, bạn có thể:

- Phân biệt source, intermediate operation và terminal operation.
- Dự đoán **khi nào** lambda trong `map/filter` được gọi.
- Hiểu **thao tác trung gian lazy** không có nghĩa mọi pipeline luôn đọc từng phần tử một theo cùng cách, bởi `sorted` và `distinct` có tính chất khác với `map/filter`.
- Phân tích **short-circuit** như `limit`, `findFirst` và `anyMatch`, cũng như sự thay đổi khi có `sorted`.
- Nhận diện lỗi dựa vào side effect trong `peek/map/filter`, bởi Stream có thể tối ưu và bỏ qua một số lần gọi callback.
- Tránh tái sử dụng Stream đã tiêu thụ, phụ thuộc thứ tự bất định khi parallel, hoặc sửa dữ liệu nguồn trong lúc chạy.
- Kiểm chứng bằng chương trình Java 17 có đầu ra rõ ràng.

## 2. Mô hình: nguồn → thao tác trung gian → thao tác kết thúc

Một pipeline điển hình:

~~~java
List<String> result = names.stream()
        .filter(s -> !s.isBlank())
        .map(String::strip)
        .map(String::toUpperCase)
        .toList();
~~~

Có ba phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Nguồn (source)** | `names.stream()` | Cung cấp dữ liệu để duyệt |
| **Intermediate** | `filter`, `map` | Mô tả cách lọc/biến đổi, trả về Stream để nối bước |
| **Terminal** | `toList()` | Yêu cầu tính kết quả cuối cùng, kích hoạt đánh giá pipeline |

Sơ đồ tư duy:

~~~text
List<String>
    |
    v
stream()  --> filter(...) --> map(...) --> map(...)
                                             |
                                         (chưa duyệt)
                                             |
                                             v
                                          toList()
                                             |
                                   kích hoạt đánh giá
                                             |
                                             v
                                       List<String>
~~~

**Lưu ý:** `stream()` tạo một đối tượng Stream, không có nghĩa một bản sao danh sách đã được tạo. Stream thường chỉ giữ thông tin về nguồn và các công đoạn dự kiến; nó không phải danh sách kết quả trung gian.

Đặc trưng quan trọng trong API Stream là **internal iteration**: thư viện điều phối việc lấy phần tử từ nguồn và đưa chúng qua các bước, thay vì người viết trực tiếp lập từng vòng lặp và danh sách trung gian. Các nguồn khác nhau có đặc tính spliterator, kích thước và thứ tự khác nhau; vì vậy cần diễn giải chính xác bằng hợp đồng Stream, không suy diễn mọi nguồn được duyệt giống nhau.

## 3. Lazy nghĩa là gì?

Hãy xem:

~~~java
Stream<String> pipeline = List.of("  An ", "Binh").stream()
        .map(String::strip)
        .filter(s -> s.length() > 2);
~~~

Sau dòng này, biến `pipeline` biểu diễn một quy trình, nhưng **chưa có terminal operation**. Việc tạo pipeline không yêu cầu `String::strip` hay predicate `length() > 2` được chạy cho mọi chuỗi.

Khi gọi:

~~~java
List<String> output = pipeline.toList();
~~~

Stream mới bắt đầu đánh giá nguồn và các bước cần thiết để tạo `List<String>`.

Một ví dụ có thể quan sát được:

~~~java
AtomicInteger calls = new AtomicInteger();

Stream<String> stream = List.of(" A ", " B ").stream()
        .map(s -> {
            calls.incrementAndGet();
            return s.strip();
        });

System.out.println(calls.get());   // 0: mới xây pipeline.
System.out.println(stream.toList()); // [A, B]
System.out.println(calls.get());   // 2: terminal đã chạy.
~~~

Đoạn này cần import `AtomicInteger`, `List`, `Stream` và đặt trong phương thức. Bộ đếm chỉ là **công cụ quan sát phục vụ học tập**; code nghiệp vụ không nên dựa vào side effect bên trong `map` để đếm tác vụ hoàn thành.

### 3.1. “Đánh giá trì hoãn” khác “chạy ở thread khác”

Lazy **không phải** bất đồng bộ. Trên một sequential stream thông thường, terminal operation được gọi và thực hiện trên luồng đang gọi (trừ khi có cơ chế thực thi khác do chương trình sử dụng). Stream không tự tạo `Future`, không tự gọi API mạng và không tự làm pipeline chạy nền.

~~~java
var filtered = numbers.stream().filter(n -> n > 0);
// Đây là Stream được mô tả, không phải tác vụ đã hoàn tất ở thread nền.
long count = filtered.count();
// Terminal được gọi đồng bộ.
~~~

Nếu muốn chạy công việc bất đồng bộ, cần cơ chế như executor/CompletableFuture, tách biệt với khái niệm lazy. Nếu dùng **parallel stream**, việc xử lý có thể dùng nhiều thread và thứ tự thực thi callback cần xem xét riêng.

### 3.2. Lazy không phải caching

Stream không mặc nhiên lưu kết quả của `map/filter` để dùng nhiều lần. Nó **không tương đương cache**, cũng không phải collection duyệt lặp mãi. Mỗi đối tượng Stream chỉ dành cho một pipeline tiêu thụ **một lần**.

Nếu muốn tái sử dụng kết quả, hãy **materialize** kết quả ở terminal, ví dụ `toList()`, rồi tạo stream mới từ danh sách khi cần.

## 4. Thao tác trung gian và thao tác kết thúc

### 4.1. Các intermediate operation thường gặp

| Thao tác | Tác dụng | Lazy? | Đặc điểm |
| --- | --- | --- | --- |
| `filter(Predicate)` | Giữ phần tử đạt điều kiện | Có | Thường stateless |
| `map(Function)` | Biến đổi từng phần tử | Có | Thường stateless |
| `mapToInt(...)` | Chuyển sang IntStream | Có | Thường stateless |
| `flatMap(...)` | Trải stream con thành luồng phần tử | Có | Có thể tạo/đóng các stream con khi duyệt |
| `peek(Consumer)` | Quan sát phần tử đi qua | Có | Không đáng tin để thực thi hiệu ứng bắt buộc |
| `distinct()` | Loại trùng theo `equals/hashCode` | Có | Stateful, có thể cần ghi nhớ đã gặp |
| `sorted()` | Sắp xếp | Có | Stateful, thường cần đệm toàn bộ đầu vào của giai đoạn sort |
| `limit(n)` | Lấy tối đa n phần tử | Có | Short-circuiting intermediate |
| `skip(n)` | Bỏ qua n phần tử đầu | Có | Cần xử lý trạng thái vị trí/đếm |

Dù `sorted` và `distinct` là **lazy**, khi terminal yêu cầu dữ liệu đi qua chúng, nội bộ có thể cần giữ buffer/trạng thái để bảo đảm kết quả. “Lazy” chỉ nói rằng **việc dựng pipeline không tức thì tính kết quả**, không nói rằng mọi bước đều không có trạng thái hoặc chỉ tốn O(1) bộ nhớ.

### 4.2. Các terminal operation phổ biến

| Thao tác | Kết quả | Ghi chú |
| --- | --- | --- |
| `toList()` | `List<T>` | Java 16+; danh sách trả về không hỗ trợ mutation |
| `collect(...)` | Kết quả theo Collector | Có thể tạo List, Map hoặc summary |
| `forEach(...)` | `void` | Có side effect; parallel không bảo đảm encounter order |
| `count()` | `long` | Có thể tối ưu từ kích thước nguồn mà không duyệt callback |
| `reduce(...)` | Giá trị tổng hợp | Phải hiểu identity, associativity |
| `findFirst()` | `Optional<T>` | Short-circuiting terminal, ưu tiên phần tử đầu theo encounter order |
| `findAny()` | `Optional<T>` | Có thể chọn phần tử bất kỳ; không dựa vào thứ tự |
| `anyMatch(...)` | `boolean` | Có thể dừng khi tìm thấy phần tử thỏa |
| `allMatch(...)` | `boolean` | Có thể dừng khi gặp phần tử không thỏa |
| `noneMatch(...)` | `boolean` | Có thể dừng khi gặp phần tử thỏa |

Một pipeline có thể có **không hoặc nhiều** intermediate operation, nhưng thường chỉ có **một** terminal operation cho chính đối tượng Stream đó.

## 5. Terminal kích hoạt đánh giá toàn pipeline theo nhu cầu

Hãy nhìn đoạn code:

~~~java
List<Integer> answer = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10)
        .toList();
~~~

Kết quả `[10, 30, 50]`. Đối với pipeline stateless cơ bản trên một ordered source và terminal như `toList`, thao tác thực tế thường được **fusion** theo từng phần tử:

~~~text
1 -> filter(true)  -> map(10) -> collector
2 -> filter(false)            -> bỏ qua
3 -> filter(true)  -> map(30) -> collector
4 -> filter(false)            -> bỏ qua
5 -> filter(true)  -> map(50) -> collector
~~~

Không nhất thiết có một danh sách tạm chứa tất cả số lẻ rồi mới map. Việc ghép các bước vào một lần duyệt có thể giảm chi phí lưu kết quả trung gian và số lượt duyệt nguồn.

Tuy nhiên, đây là **mô hình trực giác** về thực thi tuần tự thường gặp, không phải cam kết về số lần gọi callback nếu terminal có thể tối ưu, nếu pipeline có thao tác stateful, hoặc nếu chạy song song. Hợp đồng chính xác là **kết quả quan sát được theo semantics của Stream**, không phải một trace callback cố định.

## 6. Short-circuit: không nhất thiết xử lý hết dữ liệu

Lazy kết hợp với các thao tác dừng sớm giúp Stream tránh công việc không cần thiết.

### 6.1. anyMatch

~~~java
boolean hasEven = List.of(1, 3, 4, 6).stream()
        .anyMatch(n -> n % 2 == 0);
~~~

Kết quả `true`. Trên sequential stream thông thường, `anyMatch` có thể dừng sau khi thấy 4 mà không cần xem 6. `anyMatch` trả `false` cho một stream rỗng; `allMatch` và `noneMatch` trên stream rỗng trả `true` theo quy tắc chân trị rỗng.

Trường hợp cần thực thi callback cho **mọi** phần tử thì `anyMatch` không phải công cụ thích hợp: chính mục đích của nó là xác định câu trả lời boolean và dừng khi đã đủ dữ liệu.

### 6.2. findFirst và findAny

~~~java
Optional<Integer> first = List.of(2, 4, 6).stream()
        .filter(n -> n >= 4)
        .findFirst();
~~~

`first` chứa 4. Với một ordered stream, `findFirst` trả phần tử đầu theo encounter order. **Không có kết quả** thì trả `Optional.empty()`.

`findAny` có thể linh hoạt hơn, nhất là parallel, và **không nên dùng khi quy tắc cần đúng phần tử đầu tiên**. Cả hai đều là short-circuiting terminal operation.

### 6.3. limit

~~~java
List<Integer> firstTwo = List.of(10, 20, 30, 40).stream()
        .limit(2)
        .toList();
~~~

Kết quả `[10, 20]`. `limit(2)` là intermediate operation lazy có tính short-circuiting. Với nguồn có thứ tự và pipeline đơn giản, hệ thống có thể tránh xử lý phần tử phía sau khi đã lấy đủ hai phần tử. Với ordered parallel stream, việc giữ chính xác thứ tự có thể gây chi phí đáng kể.

**Không có nghĩa** luôn chỉ gọi từng callback đúng 2 lần: các phép toán phía trước, stateful stage, tối ưu và execution mode có thể ảnh hưởng. Dựa vào **giá trị kết quả**, không dựa vào đếm side effect.

## 7. Stateful intermediate operation: sorted và distinct

Một pipeline chỉ gồm `filter` và `map` thường có thể xử lý kiểu từng phần tử. Nhưng `sorted()` cần biết thứ tự so sánh của những phần tử đi vào giai đoạn sort.

~~~java
int minimum = Stream.of(9, 2, 5)
        .sorted()
        .findFirst()
        .orElseThrow();
~~~

Kết quả `2`. Để chắc chắn phần tử nào nhỏ nhất theo thứ tự sắp xếp, một bước sort tổng quát thường phải **tiêu thụ tất cả phần tử đến giai đoạn ấy** trước khi xuất phần tử đầu tiên. Vì vậy, `findFirst()` không đồng nghĩa “luôn chỉ duyệt một phần tử nguồn”.

Với `distinct()`, Stream có thể cần lưu thông tin những phần tử đã gặp để tránh lặp. `distinct` dựa trên `equals` và `hashCode` của phần tử. Trên ordered stream, kết quả `distinct` ổn định theo thứ tự gặp; khi parallel, việc bảo đảm ổn định có thể làm tăng chi phí.

### 7.1. sorted trước limit và limit trước sorted

~~~java
List<Integer> bestTwo = List.of(7, 1, 9, 3).stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> sortedPrefix = List.of(7, 1, 9, 3).stream()
        .limit(2)
        .sorted()
        .toList();
~~~

Kết quả:

- `bestTwo = [1, 3]`: sắp **toàn bộ nguồn** rồi lấy hai giá trị nhỏ nhất.
- `sortedPrefix = [1, 7]`: chỉ lấy **hai phần tử đầu nguồn**, sau đó sắp hai phần tử đó.

Thay vị trí thao tác không chỉ đổi hiệu năng mà có thể **đổi hẳn ý nghĩa nghiệp vụ**. Không tùy ý đẩy `limit` lên trước `sorted`.

### 7.2. filter trước sorted thường có lợi khi đúng ngữ nghĩa

~~~java
List<Integer> positive = numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();
~~~

Khi nhiệm vụ là “chỉ sắp các số dương”, lọc trước thường giảm số phần tử phải sắp. Nhưng nếu điều kiện phụ thuộc vào **vị trí sau khi sắp xếp**, không được chuyển filter lên trước một cách tùy ý. Cần xác định yêu cầu nghiệp vụ và chứng minh hai cách viết tương đương trước khi tối ưu.

## 8. Đừng đặt tác dụng phụ bắt buộc vào map, filter hoặc peek

Một ví dụ dễ gây hiểu lầm:

~~~java
long size = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
~~~

Một số người kỳ vọng ba dòng A/B/C luôn được in trước khi `count` trả 3. **Kỳ vọng đó không được API bảo đảm**. Với một nguồn có kích thước đã biết và các bước không thay đổi kích thước, `count()` có thể suy ra kết quả mà không duyệt pipeline. Trong trường hợp ấy, callback của `peek` **có thể không chạy**.

Bản chất tối ưu này không làm sai kết quả terminal; `size` vẫn là 3. Java Stream API cho phép elide một số bước khi kết quả cuối không bị ảnh hưởng, nên **không được dùng `peek` để ghi giao dịch, gọi thanh toán, cập nhật trạng thái bắt buộc hoặc kiểm soát correctness**.

### 8.1. peek không phải terminal

`peek` là intermediate operation và bản thân nó **không kích hoạt pipeline**:

~~~java
Stream<Integer> s = Stream.of(1, 2, 3)
        .peek(n -> System.out.println("seen: " + n));
// Không có terminal => chưa yêu cầu traversing nguồn.
~~~

`peek` thường được dùng để quan sát/debug, với ý thức rằng số lần và thời điểm callback chạy có thể thay đổi bởi việc tối ưu hoặc mode thực thi.

### 8.2. Nếu nghiệp vụ thật sự yêu cầu hành động

Phần tính toán:

~~~java
List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .toList();
~~~

Phần thực hiện hành động:

~~~java
cleaned.forEach(thisService::publish);
~~~

Hai đoạn là mảnh ghép có `names` và `thisService` trong ngữ cảnh. Ngay cả `forEach` cũng cần xử lý lỗi và thứ tự theo yêu cầu; các lời gọi I/O riêng lẻ không tự tạo transaction chung. Nhưng việc tách **tạo kết quả** khỏi **hiệu ứng xuất kết quả** giúp ý định của code rõ ràng và dễ kiểm thử hơn.

### 8.3. Side effect trong predicate/filter

~~~java
AtomicInteger checked = new AtomicInteger();
boolean found = IntStream.rangeClosed(1, 10)
        .filter(n -> {
            checked.incrementAndGet();
            return n % 3 == 0;
        })
        .anyMatch(n -> n > 4);
~~~

Đây là phép đo minh họa trong một sequential pipeline: điều kiện tìm được phần tử 6 sau khi xét lần lượt 1 đến 6. Trong code nghiệp vụ, không dùng `checked` như một nguồn ghi nhận bắt buộc, bởi Stream cho phép short-circuit và các phép tối ưu. Nếu cần đếm chính xác mọi đầu vào vì nghiệp vụ, hãy làm điều đó trong một quy trình điều phối có hợp đồng rõ, không nhờ số lần callback tình cờ.

## 9. Một đối tượng Stream chỉ tiêu thụ một lần

~~~java
Stream<Integer> stream = Stream.of(1, 2, 3);
long size = stream.count();

// IllegalStateException nếu thử dùng lại:
// long sum = stream.mapToInt(Integer::intValue).sum();
~~~

Sau một terminal operation, Stream được xem là **đã tiêu thụ**. Không nên dùng lại một đối tượng Stream để gọi terminal khác, hoặc tiếp tục thêm intermediate operation.

Nếu cần hai kết quả từ cùng nguồn, tạo hai Stream riêng:

~~~java
List<Integer> numbers = List.of(1, 2, 3);

long size = numbers.stream().count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
~~~

Hoặc nếu phù hợp, dùng một collector tổng hợp nhiều chỉ số trong **một lượt duyệt**. Chọn theo yêu cầu hiệu năng và tính dễ đọc.

**Lưu ý thêm:** việc một pipeline tạo ra kết quả không có nghĩa nó tự snapshot toàn bộ nguồn. Khi duyệt dữ liệu mutable, các quy tắc về nguồn và non-interference vẫn cần tuân thủ.

## 10. Không can thiệp vào nguồn khi đang chạy

Stream documentation yêu cầu các behavioral parameter thường **non-interfering** (không sửa nguồn đang duyệt) và trong nhiều trường hợp **stateless** để tránh phụ thuộc trạng thái giữa các lần chạy.

Không nên viết:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
numbers.stream().forEach(n -> numbers.add(n));
// Can thiệp vào nguồn khi duyệt: có thể ném ConcurrentModificationException
// hoặc gây hành vi không mong muốn.
~~~

Đây là **phản ví dụ**, không chạy trong bài thực hành. Tùy nguồn và cơ chế phát hiện sửa đổi, kết quả có thể khác nhau; không nên khẳng định mọi stream đều ném đúng một loại exception.

Nếu muốn tạo dữ liệu mới:

~~~java
List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();
~~~

Cách này tạo một list kết quả riêng, không thêm phần tử vào list nguồn.

### 10.1. Nguồn thay đổi giữa lúc tạo Stream và terminal

Vì pipeline lazy, một số nguồn có đặc tính **late-binding** và có thể phản ánh thay đổi xảy ra trước khi terminal bắt đầu. Nhưng hành vi cụ thể còn tùy nguồn/spliterator; **không nên dựa vào việc sửa nguồn rồi kỳ vọng một snapshot hay một trace nhất định**.

Cần kết quả nhất quán tại thời điểm cụ thể? Hãy tạo snapshot dữ liệu dưới quyền sở hữu rõ ràng, chẳng hạn một danh sách mới chứa các phần tử cần xử lý, rồi không thay đổi nó trong lúc duyệt. `List.copyOf` là bản sao không hỗ trợ mutation của cấu trúc list, nhưng **không tự sao chép sâu** các phần tử mutable.

## 11. Sequential và parallel: lazy vẫn đúng, thứ tự callback có thể khác

Cả sequential và parallel stream đều mô tả pipeline có intermediate operation lazy. Khác biệt là cách terminal điều phối thực thi:

- **Sequential:** xử lý theo luồng tuần tự; với ordered source, nhiều phép toán giữ encounter order.
- **Parallel:** có thể chia dữ liệu cho nhiều thread, duyệt callback ở các thời điểm và thứ tự khác nhau.
- `forEach` trên parallel stream không bảo đảm thứ tự encounter; nếu phải giữ encounter order, `forEachOrdered` có hợp đồng thứ tự nhưng có thể giảm lợi ích song song.
- `findAny` có thể trả bất kỳ phần tử phù hợp, nhất là trong parallel; `findFirst` cần tuân thủ encounter order nếu có.
- Stateful operation như `sorted` và `distinct`, hoặc `limit` trên ordered parallel stream, có thể tạo rào cản và tốn tài nguyên.

Một lambda có mutation lên một biến chung không tự trở thành thread-safe vì chạy qua Stream API:

~~~java
// Tránh dùng trong parallel khi shared không được bảo vệ:
// source.parallelStream().forEach(x -> shared.add(x));
~~~

Ngay cả khi source concurrent, code phía trong callback vẫn phải tuân theo hợp đồng an toàn luồng của đối tượng được sửa. Không bật `parallel()` chỉ vì nghe “nhanh hơn”; phải xem khối lượng công việc, chi phí chia/gom, thứ tự và benchmark thực tế.

## 12. Các bước tối ưu và giới hạn suy luận

### 12.1. count() và kích thước nguồn đã biết

~~~java
long total = List.of(10, 20, 30).stream()
        .map(n -> n * 2)
        .count();
~~~

Kết quả 3. Trong trường hợp không có thao tác làm thay đổi số phần tử và kích thước nguồn đã biết, Java có thể suy ra count mà không gọi mapper. Điều này **không làm sai count**, nhưng nhắc rằng `map` không phải nơi đặt hiệu ứng bắt buộc.

### 12.2. filter làm số phần tử không còn biết từ đầu

~~~java
long positiveCount = List.of(-1, 0, 2, 3).stream()
        .filter(n -> n > 0)
        .count();
~~~

Kết quả 2. Để xác định bao nhiêu phần tử đạt điều kiện, hệ thống thông thường phải đánh giá predicate tương ứng. Nhưng việc gọi các callback vẫn không phải hợp đồng để báo cáo nghiệp vụ: nếu cần thông tin kiểm toán, hãy mô hình hóa nó trong kết quả hoặc một quy trình rõ ràng.

### 12.3. Lý do tối ưu không phải bảo đảm về thuật toán

Đừng suy luận “Java 17 chắc chắn chỉ chạy đúng n callback trong ví dụ X” cho mọi JDK và mọi nguồn. Đặc tả tập trung vào **kết quả và tính đúng đắn**, trong khi implementation có thể tối ưu, fusion, hoán đổi chiến lược hoặc bỏ những phần không cần thiết trong phạm vi cho phép.

Số lần gọi các behavioral parameter và thread chạy chúng có thể thay đổi, đặc biệt với short-circuiting và parallel pipeline. Hãy dùng side effect trong ví dụ để **hiểu cách hiện thực phổ biến đang hoạt động**, nhưng không dùng trace ấy như bất biến của business logic.

## 13. Chương trình Java 17 hoàn chỉnh

Ví dụ dưới đây làm rõ ba hiện tượng:

1. Tạo pipeline không làm chạy mapper ngay.
2. Terminal `toList()` kích hoạt biến đổi phần tử.
3. `anyMatch` có thể dừng sớm trên sequential pipeline.
4. `sorted` có thể cần đọc toàn bộ phần tử đầu vào trước `findFirst`.

Tạo file **LazyStreamDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class LazyStreamDemo {
    public static void main(String[] args) {
        AtomicInteger mapped = new AtomicInteger();

        Stream<String> pipeline = List.of(
                " An ", " ", "Binh", " Chi "
        ).stream()
                .map(s -> {
                    mapped.incrementAndGet();
                    return s.strip();
                })
                .filter(s -> !s.isEmpty())
                .map(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("after building: " + mapped.get());

        List<String> values = pipeline.toList();
        System.out.println("after toList: " + mapped.get());
        System.out.println("values: " + values);

        AtomicInteger inspected = new AtomicInteger();
        boolean matched = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    inspected.incrementAndGet();
                    return n % 3 == 0;
                })
                .anyMatch(n -> n > 4);

        System.out.println("anyMatch: " + matched);
        System.out.println("inspected: " + inspected.get());

        AtomicInteger sortedInput = new AtomicInteger();
        int first = Stream.of(9, 2, 5)
                .map(n -> {
                    sortedInput.incrementAndGet();
                    return n;
                })
                .sorted()
                .findFirst()
                .orElseThrow();

        System.out.println("sorted first: " + first);
        System.out.println("sorted input: " + sortedInput.get());

        List<Integer> smallestTwo = List.of(7, 1, 9, 3)
                .stream()
                .sorted()
                .limit(2)
                .toList();

        System.out.println("smallest two: " + smallestTwo);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac LazyStreamDemo.java
java LazyStreamDemo
~~~

**Đầu ra khi chạy chương trình tuần tự này:**

~~~text
after building: 0
after toList: 4
values: [AN, BINH, CHI]
anyMatch: true
inspected: 6
sorted first: 2
sorted input: 3
smallest two: [1, 3]
~~~

### 13.1. Giải thích từng dòng

- **after building: 0** — mapper vẫn chưa chạy chỉ vì pipeline đã được khai báo.
- **after toList: 4** — source có bốn chuỗi; mapper đầu tiên được thực thi cho chúng trong pipeline Java tuần tự cụ thể này. Một chuỗi chỉ chứa khoảng trắng bị filter loại, nhưng vẫn được xử lý bởi mapper đứng trước filter.
- **values: [AN, BINH, CHI]** — dữ liệu đã strip, lọc chuỗi trống và uppercase. `toList()` tạo danh sách kết quả không hỗ trợ mutation.
- **anyMatch: true** — có số chia hết cho 3 và lớn hơn 4: số 6.
- **inspected: 6** — với pipeline tuần tự này, predicate `filter` xem lần lượt 1 tới 6 rồi terminal đã đủ kết luận, nên dừng trước 7 tới 10.
- **sorted first: 2** — phần tử đầu sau khi sắp các số 9, 2, 5 là 2.
- **sorted input: 3** — giai đoạn sort đã xử lý cả ba số trong nguồn để xác định thứ tự.
- **smallest two: [1, 3]** — sắp tăng dần rồi mới lấy hai số nhỏ nhất.

Các bộ đếm ở đây phục vụ quan sát **một pipeline với thao tác tuần tự xác định**. Trong code nghiệp vụ, không nên dựa vào việc callback luôn chạy một số lần nhất định khi thay terminal, source, mode hoặc JDK.

## 14. Kiểm thử lazy evaluation như thế nào?

Với bài học hoặc ví dụ trong unit test, có thể dùng bộ đếm để quan sát rằng việc dựng pipeline **chưa thực hiện biến đổi**:

~~~java
AtomicInteger invoked = new AtomicInteger();

Stream<String> pending = Stream.of("A", "B")
        .map(s -> {
            invoked.incrementAndGet();
            return s.toLowerCase(Locale.ROOT);
        });

if (invoked.get() != 0) {
    throw new AssertionError("Unexpected eager evaluation");
}

List<String> result = pending.toList();

if (!result.equals(List.of("a", "b"))) {
    throw new AssertionError("Unexpected result: " + result);
}
~~~

Đây là mảnh ghép trong phương thức có import `AtomicInteger`, `Stream`, `List`, `Locale`; không phải file chạy độc lập.

Bài test nên ưu tiên **giá trị đầu ra**, việc không tiêu thụ nguồn trước terminal và hợp đồng nghiệp vụ. Đừng viết test mong `peek` luôn in chính xác n dòng trước `count`, bởi đặc tả cho phép tối ưu khác.

Nếu cần kiểm thử rằng một hành động quan trọng **phải xảy ra** với từng phần tử, nên làm hành động ấy thuộc trách nhiệm của một lớp điều phối/terminal có hợp đồng rõ, rồi kiểm tra kết quả quan sát được thay vì gián tiếp dựa vào side effect trong `map`.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tin rằng `map` chạy ngay khi gọi | Dễ ghi log/tính công việc tại thời điểm sai | Nhớ intermediate lazy, terminal mới yêu cầu thực thi |
| Nghĩ lazy nghĩa chạy ở thread nền | Nhầm hiệu năng/concurrency | Lazy và async/parallel là các khái niệm khác nhau |
| Đặt hiệu ứng nghiệp vụ vào `peek` | Callback có thể bị bỏ qua khi tối ưu | Dùng bước thực thi có chủ đích |
| Kỳ vọng `count()` luôn duyệt mọi phần tử | Có nguồn sized thì có thể tính ngay | Dựa vào giá trị count, không dựa vào side effect |
| Nghĩ `findFirst` chỉ đọc một phần tử nguồn | `sorted` có thể cần tất cả phần tử | Xem cả pipeline, không chỉ terminal |
| Đổi `sorted().limit(2)` thành `limit(2).sorted()` | Kết quả/ý nghĩa thay đổi | Giữ thứ tự thao tác theo hợp đồng |
| Dùng lại Stream sau `toList`/`count` | `IllegalStateException` | Tạo stream mới từ nguồn hoặc lưu kết quả |
| Sửa collection nguồn trong callback | Có thể sai hành vi hoặc exception | Không can thiệp vào nguồn khi duyệt |
| Dùng shared mutable state trong parallel callback | Race condition/mất cập nhật | Tách state, dùng collector hoặc đồng bộ |
| Dựa vào thứ tự của `findAny` | Kết quả có thể không phải phần tử đầu | Dùng `findFirst` nếu cần encounter order |
| Nghĩ tất cả intermediate stateless | `sorted/distinct` có state, buffer | Xem đặc tính từng phép toán |
| Đo hiệu năng bằng số dòng `peek` | Log không phản ánh lượng công việc thực | Benchmark đúng kịch bản, đo kết quả/chi phí |

## 16. Bài tập tự luyện

### Bài 1: Đoán thời điểm chạy

~~~java
AtomicInteger counter = new AtomicInteger();
Stream<Integer> pipeline = Stream.of(2, 4, 6)
        .map(n -> {
            counter.incrementAndGet();
            return n * 10;
        });
System.out.println(counter.get());
System.out.println(pipeline.toList());
~~~

Hãy dự đoán hai dòng in trong chương trình tuần tự này.

**Đáp án:** `0`, sau đó `[20, 40, 60]`. Lambda `map` chưa cần chạy trước terminal `toList`.

### Bài 2: Short-circuit theo điều kiện

~~~java
boolean result = IntStream.rangeClosed(1, 100)
        .filter(n -> n % 7 == 0)
        .anyMatch(n -> n > 20);
~~~

**Đáp án:** `true`, vì 21 là số chia hết cho 7 đầu tiên lớn hơn 20. Một sequential implementation có thể dừng khi thấy 21; không cần duyệt tới 100 để quyết định boolean.

### Bài 3: Thứ tự thao tác

Với dãy `[10, 2, 8, 1]`, tính:

~~~java
numbers.stream().sorted().limit(2).toList();
numbers.stream().limit(2).sorted().toList();
~~~

**Đáp án:** lần lượt `[1, 2]` và `[2, 10]`. Cách thứ nhất tìm hai giá trị nhỏ nhất; cách thứ hai chỉ sắp hai giá trị xuất hiện đầu nguồn.

### Bài 4: Có nên dùng peek cho audit?

Một ứng dụng muốn bảo đảm mỗi đơn hàng hợp lệ đều được ghi audit. Người viết dùng:

~~~java
long total = orders.stream()
        .peek(thisService::audit)
        .count();
~~~

Đây là mảnh ghép với `orders` và `thisService` giả định. **Đáp án:** không phù hợp. `count` có thể tối ưu mà không traverse, nên audit không được bảo đảm chạy. Hãy tách việc ghi audit thành một thao tác có hợp đồng thực thi rõ, xử lý transaction/lỗi nếu cần.

### Bài 5: Thiết kế một pipeline

Bạn có danh sách giao dịch. Yêu cầu: chọn giao dịch hợp lệ, lấy ba giao dịch có số tiền cao nhất, chuyển sang DTO hiển thị.

**Hướng giải:** `filter(valid)` → `sorted(byAmountDescending)` → `limit(3)` → `map(toDto)` → `toList()`. Cân nhắc thứ tự nếu rule hợp lệ phụ thuộc tiền sau quy đổi, và chọn kiểu số phù hợp để tránh overflow hoặc lỗi làm tròn. Lưu ý `sorted` thường có chi phí lưu/bộ đệm, đặc biệt nếu nguồn rất lớn.

## 17. Ghi nhớ

**Intermediate operation của Stream được đánh giá trì hoãn**: khai báo `map/filter/sorted` chủ yếu tạo pipeline, chưa đồng nghĩa đã xử lý toàn bộ dữ liệu. Terminal operation kích hoạt đánh giá **đủ để tạo kết quả**, và short-circuit/tối ưu có thể khiến một số phần tử hoặc callback không được xét tới.

- **Lazy không phải async hay cache.**
- **Stateless** như `map/filter` có thể được ghép xử lý theo từng phần tử; **stateful** như `sorted/distinct` có thể cần thêm bộ nhớ hoặc tiêu thụ nhiều đầu vào.
- **Short-circuit** như `limit/findFirst/anyMatch` giúp dừng sớm khi ngữ nghĩa cho phép.
- **Side effect trong callback không phải hợp đồng chạy đủ số lần**; đặc biệt tránh dùng `peek` cho việc bắt buộc.
- **Mỗi Stream chỉ được tiêu thụ một lần**; tránh sửa nguồn trong lúc duyệt.
- **Kết quả và hợp đồng nghiệp vụ** quan trọng hơn trace thực thi của từng callback.

Khi đọc code Stream, hãy luôn tìm **terminal operation**, kiểm tra thứ tự các bước, đặc tính stateful/short-circuit và xem có logic nào sai khi JVM tối ưu hoặc khi chuyển sang parallel không.
