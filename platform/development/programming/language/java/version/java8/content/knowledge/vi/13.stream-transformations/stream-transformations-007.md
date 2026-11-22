# limit, skip và chi phí theo encounter order trong Java Stream

`Stream.limit(long maxSize)` và `Stream.skip(long n)` là hai **intermediate operations** có từ Java 8 và vẫn được hỗ trợ trong Java hiện hành. Chúng giúp **lấy một số phần tử đầu tiên** hoặc **bỏ qua một số phần tử đầu tiên** của một Stream. Khi kết hợp, chúng tạo thành công cụ cắt đoạn (*slicing*) dùng trong phân trang, lấy mẫu, xử lý cửa sổ theo vị trí và giới hạn lượng dữ liệu đầu ra.

Tuy nhiên, ngữ nghĩa của “đầu tiên” chỉ rõ ràng khi Stream có **encounter order**. Trên Stream song song có thứ tự, việc xác định chính xác phần tử thuộc prefix hay phải bỏ qua có thể tạo chi phí phối hợp, duy trì trạng thái và đệm dữ liệu lớn. Đây là lý do tài liệu Java nhấn mạnh `limit` và `skip` **thường rẻ trên pipeline tuần tự**, nhưng **có thể tốn kém trên pipeline song song có thứ tự**, nhất là khi số lượng cần lấy/bỏ qua lớn.

Bài học phân biệt ngữ nghĩa API với các tối ưu hóa có thể có, giải thích khi nào được dùng `unordered()` hoặc `sequential()`, ảnh hưởng thứ tự các bước trong pipeline, phân trang ổn định, xử lý Stream vô hạn và cách kiểm thử mà không phụ thuộc thuật toán nội bộ.

## 1. Định nghĩa chính xác

### 1.1. limit: giữ tối đa n phần tử

~~~java
Stream<T> first = source.limit(maxSize);
~~~

Đây là **chữ ký sử dụng minh họa**. Với `maxSize >= 0`, kết quả dài **không quá `maxSize`**. Nếu nguồn chỉ có ít phần tử hơn giới hạn thì lấy tất cả; nếu nguồn nhiều phần tử hơn và có encounter order, kết quả là **`maxSize` phần tử đầu theo thứ tự ấy**.

Ví dụ:

~~~java
List<String> names = List.of("A", "B", "C", "D", "E");

List<String> firstThree = names.stream()
        .limit(3)
        .toList();
// [A, B, C]
~~~

Mảnh mã trên chạy trong một phương thức khi có `import java.util.*;`. `toList()` có từ Java 16 và được dùng trong ví dụ JDK 17+; **bản thân `limit` đã có từ Java 8**. Nếu dự án thật đang biên dịch bằng Java 8, có thể kết thúc bằng `collect(Collectors.toList())` thay vì `toList()`.

`limit(0)` tạo một Stream không có phần tử kết quả. `limit(100)` trên nguồn chỉ có 5 phần tử không sinh thêm phần tử giả; nó giữ 5 phần tử đang có.

`limit` là một **short-circuiting stateful intermediate operation**: nó có khả năng khiến pipeline dừng tiêu thụ nguồn sớm khi đủ kết quả. Điều này **không phải lời hứa** rằng mọi nguồn, mọi pipeline và mọi chế độ parallel chỉ chạm đúng n phần tử nguồn; những bước như `filter`, `flatMap`, `sorted` hoặc xử lý song song có thể cần tiêu thụ/đệm nhiều hơn.

### 1.2. skip: loại bỏ n phần tử đầu

~~~java
Stream<T> remaining = source.skip(n);
~~~

Với `n >= 0`, `skip(n)` bỏ qua **n phần tử đầu của Stream tại vị trí nó được gọi** và giữ phần còn lại. Nếu nguồn có ít hơn n phần tử, kết quả rỗng.

~~~java
List<String> names = List.of("A", "B", "C", "D", "E");

List<String> afterTwo = names.stream()
        .skip(2)
        .toList();
// [C, D, E]
~~~

`skip(0)` không bỏ phần tử nào; `skip(99)` trên danh sách 5 phần tử cho Stream rỗng. `skip` là **stateful intermediate operation**, nhưng **không được phân loại là short-circuiting** như `limit`: để biết phần còn lại của nguồn, nó phải loại n phần tử trước rồi mới chuyển những phần tử tiếp theo.

Không suy ra `skip(n)` bắt buộc luôn thực hiện chính xác n lời gọi vào một mapper hoặc source iterator: triển khai có thể tối ưu hóa khi nguồn có thông tin kích thước/chia đoạn. Hãy kiểm chứng **phần tử đầu ra**, không dựa vào số lần callback nội bộ.

### 1.3. Bảng tình huống cơ bản

Giả sử một Stream **có thứ tự** lần lượt chứa `[A, B, C, D, E, F]`.

| Biểu thức | Kết quả | Vì sao |
|---|---|---|
| `limit(3)` | `[A, B, C]` | Giữ ba phần tử đầu |
| `skip(2)` | `[C, D, E, F]` | Bỏ A và B |
| `skip(2).limit(3)` | `[C, D, E]` | Bỏ hai rồi giữ ba |
| `limit(3).skip(2)` | `[C]` | Giữ A,B,C rồi bỏ A,B |
| `limit(0)` | `[]` | Giới hạn bằng không |
| `skip(0)` | `[A, B, C, D, E, F]` | Không bỏ phần tử |
| `skip(99)` | `[]` | Số cần bỏ vượt số phần tử |
| `limit(99)` | `[A, B, C, D, E, F]` | Không thêm phần tử ngoài nguồn |

**Lưu ý:** `limit` và `skip` trả về **Stream mới** để tiếp tục xây pipeline. Chúng không tự thay đổi nguồn `List` hoặc array. Terminal operation như `toList()`, `collect(...)`, `count()` hoặc `forEach(...)` mới kích hoạt việc duyệt pipeline. Một Stream đã dùng terminal operation không thể dùng lại.

## 2. Thứ tự limit và skip thay đổi ý nghĩa

Thứ tự các intermediate operations là một phần hợp đồng pipeline.

### 2.1. Bỏ trước, lấy sau: mô hình trang

~~~java
List<String> page = names.stream()
        .skip(2)
        .limit(3)
        .toList();
// [C, D, E]
~~~

Chúng ta yêu cầu: bỏ 2 phần tử của danh sách có thứ tự, sau đó lấy tối đa 3 phần tử. Đây là cách cắt đoạn thường dùng.

### 2.2. Lấy trước, bỏ sau: đoạn con trong một prefix

~~~java
List<String> tailOfPrefix = names.stream()
        .limit(3)
        .skip(2)
        .toList();
// [C]
~~~

Dòng đầu thu hẹp nguồn xuống `[A,B,C]`; bước tiếp theo bỏ A và B, chỉ còn C. Biểu thức này **không tương đương** với `skip(2).limit(3)`.

### 2.3. Minh họa bằng chỉ số

~~~text
Nguồn:     index 0  1  2  3  4  5
                  A  B  C  D  E  F

skip(2):          [C  D  E  F]
limit(3):         [C  D  E]          -> trang 3 phần tử

limit(3):   [A  B  C]
skip(2):          [C]               -> một phần tử
~~~

Trong một số trường hợp, các phép slicing liên tiếp có thể được tối ưu hóa nội bộ; **không dựa vào** việc JVM chắc chắn hợp nhất chúng theo một cách cụ thể. Cách viết có mục đích rõ ràng giúp review mã và test dễ hơn.

## 3. Encounter order: “đầu tiên” đến từ đâu?

**Encounter order** là thứ tự phần tử được xác định bởi nguồn và các bước trong pipeline, không phải thứ tự thread hoàn tất công việc. Một Stream có thể **có hoặc không có** encounter order.

Ví dụ nguồn thông thường:

- `List.stream()`: có encounter order theo thứ tự List.
- `Arrays.stream(array)`: có encounter order theo thứ tự chỉ số mảng.
- `IntStream.range(start, end)`: có encounter order tăng dần.
- `Stream.iterate(...)`: có encounter order do trình tự tạo phần tử.
- `HashSet.stream()`: không được bảo đảm encounter order từ HashSet.
- `Stream.generate(supplier)`: tài liệu mô tả Stream **vô hạn, tuần tự và unordered**.
- `sorted()`: có thể tạo encounter order dựa trên comparator.
- `unordered()`: gỡ yêu cầu duy trì encounter order của pipeline; **không tự xáo trộn phần tử**.

Điểm quan trọng: **`parallel()` không tự xóa encounter order**. Một List có thứ tự khi gọi `parallelStream()` vẫn là nguồn ordered; ví dụ `list.parallelStream().limit(3).toList()` phải giữ đúng ba phần tử đầu theo encounter order.

### 3.1. Ordered Stream được bảo đảm điều gì?

Giả sử:

~~~java
List<Integer> result = IntStream.range(0, 20)
        .parallel()
        .skip(7)
        .limit(5)
        .boxed()
        .toList();
// [7, 8, 9, 10, 11]
~~~

Đây là đoạn JDK 17+ chạy trong phương thức với `import java.util.stream.*;`. Dù framework có thể dùng nhiều thread và tính toán không theo thứ tự thời gian, **tập phần tử và thứ tự kết quả** phải tương ứng với `[7,8,9,10,11]` vì pipeline có encounter order.

Điều này **không có nghĩa** mỗi lời gọi `map` hoặc `peek` diễn ra theo thứ tự 7,8,9,... trên cùng thread. Java có thể áp dụng toán tử trên nhiều nhánh trong khi vẫn tái tạo kết quả có thứ tự.

### 3.2. Unordered Stream có thể chọn phần tử nào?

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .unordered()
        .limit(7)
        .count();
// 7
~~~

`limit(7)` trên nguồn unordered chỉ cần kết quả **tối đa 7 phần tử**; ở ví dụ có 100 phần tử nên kết quả có 7. **Không được giả định đó là `0,1,2,3,4,5,6`**. Triển khai có thể tình cờ trả những số ấy trong một lần chạy, nhưng đó **không phải hợp đồng** khi yêu cầu thứ tự đã bị bỏ.

Tương tự:

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .unordered()
        .skip(90)
        .limit(3)
        .count();
// 3
~~~

Với 100 phần tử và bỏ 90, còn 10 phần tử, sau đó lấy 3. Tuy nhiên **không được khẳng định những phần tử bị bỏ là `0..89`**. Nếu cần “bỏ 90 dòng đầu tiên của một danh sách ổn định”, **không được dùng `unordered()`**.

### 3.3. Unordered không phải shuffle

`unordered()` là lời tuyên bố rằng thuật toán phía sau **không cần duy trì encounter order**. Nó không buộc dữ liệu bị xáo trộn, không bảo đảm ngẫu nhiên, không lấy mẫu đều và không cho kết quả kết hợp các giá trị khác nhau giữa mọi lần chạy.

Nếu bạn cần lấy mẫu ngẫu nhiên có xác suất rõ ràng, hãy dùng thuật toán sampling đúng yêu cầu; `unordered().limit(k)` **không phải** random sampling có bảo đảm thống kê. Nó chỉ có thể hỗ trợ một số tối ưu khi **thứ tự không quan trọng**.

Nếu bạn gọi `unordered()` rồi thực hiện `sorted()` trước `limit`, `sorted()` lại tạo yêu cầu sắp thứ tự cho dữ liệu; không suy luận rằng thêm `unordered` ở bất kỳ vị trí nào luôn làm pipeline rẻ hơn.

## 4. Vì sao limit/skip có thể đắt trên ordered parallel Stream?

Theo Oracle Java API, cả `limit` và `skip` đều có ghi chú về chi phí trong **ordered parallel pipelines**, nhất là khi giá trị n lớn.

### 4.1. limit: giữ chính xác *n phần tử đầu*

Trong xử lý song song, các nhánh có thể sản xuất kết quả không đồng thời. Tuy nhiên, trên Stream ordered, `limit(n)` **không được lấy n phần tử bất kỳ hoàn thành sớm nhất**: phải chọn đúng n phần tử đầu theo encounter order.

Ví dụ:

~~~java
IntStream.range(0, 1_000_000)
        .parallel()
        .limit(100)
        .toArray();
~~~

Kết quả phải đúng thứ tự `0..99`. Nếu các nhánh sau xử lý nhanh hơn nhánh đầu, implementation vẫn cần tôn trọng ranh giới của prefix đầu; tùy nguồn và pipeline có thể có **chi phí phối hợp, quản lý phân đoạn, đệm dữ liệu hoặc hạn chế song song**.

Không được kết luận mỗi lần gọi sẽ cần duyệt toàn bộ 1 triệu phần tử. Với nguồn `SIZED`/`SUBSIZED` như một dãy số hoặc array, JDK có thể xác định biên mà không phải duyệt tuần tự hết toàn bộ. **Chi phí thực tế phụ thuộc nguồn, pipeline và implementation.**

### 4.2. skip: phải bỏ đúng prefix đầu

~~~java
IntStream.range(0, 1_000_000)
        .parallel()
        .skip(900_000)
        .limit(10)
        .toArray();
~~~

Với encounter order, 10 phần tử cần lấy là `900000..900009`. Không thể tự ý bỏ 900.000 phần tử bất kỳ. Để đưa ra kết quả đúng, pipeline phải quản lý ranh giới dữ liệu đã bỏ và phần dữ liệu giữ lại.

Trong chế độ tuần tự trên nguồn tuần tự, `skip(n)` thường phải đi qua phần tử nằm trước vị trí đầu ra, có thể tốn thời gian với offset rất sâu. Tuy nhiên các nguồn chia được và biết chính xác kích thước có thể được tối ưu; đừng đưa ra tuyên bố tuyệt đối rằng `skip(n)` trên mọi nguồn có độ phức tạp bắt buộc bằng n lần gọi mapper.

**Điều cần nhớ:** chi phí không đến từ cú pháp `skip`, mà từ yêu cầu “bỏ đúng n phần tử đầu” trong pipeline có thứ tự, đặc biệt khi chia công việc cho nhiều nhánh xử lý.

### 4.3. Các trường hợp dễ tăng chi phí

| Pipeline | Đặc điểm cần lưu ý | Hướng cân nhắc |
|---|---|---|
| Ordered sequential + `limit(n)` | Thường rẻ; có thể dừng khi đủ n đầu ra | Giữ tuần tự nếu workload nhỏ |
| Ordered sequential + `skip(n)` | Phải đi qua prefix bị bỏ, trừ tối ưu nguồn | Tránh offset rất sâu trên nguồn tốn chi phí |
| Ordered parallel + `limit(n)` | Phải bảo toàn prefix có thứ tự; có thể phối hợp/đệm | Đo hiệu năng; cân nhắc sequential khi cần |
| Ordered parallel + `skip(n)` | Phải xác định chính xác prefix bỏ | Đo memory/time; cân nhắc nguồn truy cập trực tiếp |
| Unordered parallel + `limit(n)` | Được chọn n phần tử không theo vị trí đầu | Chỉ dùng khi bất kỳ n phần tử đều hợp lệ |
| Unordered parallel + `skip(n)` | Được bỏ bất kỳ n phần tử | Không dùng cho offset theo thứ tự |
| Có `sorted()` trước slicing | Thường phải xử lý dữ liệu để xác định thứ tự sort | Không kỳ vọng limit giúp bỏ toàn bộ chi phí sort |
| Có `filter()` trước slicing | Có thể cần kiểm nhiều hơn n phần tử nguồn | Xét độ chọn lọc filter và ý nghĩa pipeline |

Đây là **gợi ý hiệu năng**, không phải phép tính độ phức tạp cứng cho mọi implementation. Gốc dữ liệu, số lượng phần tử, trạng thái SIZED/SUBSIZED, chi phí xử lý, phân bổ thread và bộ nhớ đều tác động kết quả đo.

### 4.4. SIZED/SUBSIZED giúp nhưng không là “bảo đảm miễn phí”

Một Spliterator có `SIZED` có thể báo chính xác số phần tử và `SUBSIZED` giúp biết kích thước các phần sau chia. Nhờ đó, một số pipeline song song có thể phân định vị trí theo nhánh hiệu quả hơn.

Nhưng sau các phép như `filter`, số lượng đầu ra có thể không được biết chính xác từ số lượng đầu vào. Nguồn có `SIZED` không đồng nghĩa **mọi đoạn xử lý phía sau đều giữ SIZED**. Cờ giúp tối ưu nhưng không thay đổi hợp đồng của `limit(n)` hoặc `skip(n)`.

Nếu đầu vào là truy vấn cơ sở dữ liệu, đọc toàn bộ vào JVM rồi `skip` sẽ có đặc tính khác hoàn toàn với việc **phân trang ngay ở tầng truy vấn có thứ tự và index thích hợp**. Chọn nơi thực hiện slicing là một quyết định thiết kế dữ liệu, không chỉ hiệu năng Stream.

## 5. Khi nào nên dùng unordered()?

Chỉ dùng `unordered()` khi quy tắc nghiệp vụ thực sự cho phép **một tập con bất kỳ**.

Ví dụ bạn muốn **xử lý tối đa một số mẫu để thống kê thăm dò** từ một nguồn không cần giữ thứ tự và không đòi random sampling chính xác:

~~~java
long selectedCount = IntStream.range(0, 100)
        .parallel()
        .unordered()
        .limit(12)
        .count();
// 12
~~~

Không kiểm thử **đúng 12 số đầu** trong trường hợp này. Có thể tận dụng tự do lựa chọn phần tử để giảm chi phí phối hợp, nhưng **không hứa tăng tốc** trên mọi nguồn: một range có SIZED/SUBSIZED có thể đã chạy ordered rất nhanh.

Với phân trang người dùng nhìn thấy hoặc hệ thống cần kết quả lặp lại, chọn ordered pipeline và **không thêm unordered chỉ để tăng benchmark**:

~~~java
List<Integer> page = IntStream.range(0, 50)
        .boxed()
        .skip(10)
        .limit(5)
        .toList();
// [10, 11, 12, 13, 14]
~~~

### 5.1. Unordered ảnh hưởng cả skip lẫn limit

~~~java
IntStream.range(0, 100)
        .parallel()
        .unordered()
        .skip(50)
        .limit(5)
        .toArray();
~~~

Kết quả là một tập con 5 phần tử hợp lệ nhưng **không bắt buộc** bắt đầu ở 50. Thêm `unordered()` trước `skip(50)` nghĩa là bạn đã từ bỏ khái niệm “bỏ 50 giá trị đầu theo dãy tăng dần”.

Nếu chỉ cần bất kỳ n phần tử, thường dùng trực tiếp `unordered().limit(n)` thay vì kết hợp `skip` không cần thiết. `skip` chỉ có ý nghĩa nghiệp vụ khi bạn thực sự muốn loại một số phần tử; trên unordered stream, những phần tử nào bị loại không xác định theo encounter order.

### 5.2. Không dùng unordered để “chữa” kết quả không ổn định

Nếu đầu vào có thứ tự không ổn định do đọc từ Set hoặc query không có ORDER BY, `unordered()` không tạo được một thứ tự lặp lại. Nếu cần trang ổn định, **xác định thứ tự nguồn trước** bằng một comparator hoặc truy vấn có khóa sắp xếp được bảo đảm.

Việc một số lần chạy trên một HashSet trả cùng thứ tự không phải hợp đồng cho các bản ghi phân trang. Không xây test bằng cách nhìn kết quả tình cờ rồi mặc định nó là encounter order.

## 6. Khi nào chuyển sang sequential()?

Oracle cũng gợi ý rằng nếu phải **giữ encounter order** và đang gặp vấn đề thời gian/bộ nhớ trên parallel limit/skip, chuyển sang chế độ tuần tự có thể cải thiện hiệu năng.

Ví dụ:

~~~java
List<Integer> page = IntStream.range(0, 1_000_000)
        .parallel()
        .sequential()
        .skip(900_000)
        .limit(10)
        .boxed()
        .toList();
~~~

Đây là mảnh Java chạy được trên JDK 17+. `sequential()` thay execution mode của pipeline. Trong Stream, không nên dựa vào việc đặt `parallel()` hoặc `sequential()` giữa pipeline để “đóng đinh từng stage” vào thread cụ thể; **mode của pipeline** quyết định cách thực thi khi terminal operation diễn ra.

Chuyển sang sequential có thể giảm overhead phối hợp parallel, nhưng vẫn có chi phí bỏ nhiều phần tử nếu nguồn không hỗ trợ tối ưu. Không biến gợi ý này thành quy tắc “sequential luôn nhanh hơn”. Nên benchmark cả hai cấu hình với cùng dữ liệu và tiêu chí tính đúng.

Nếu còn những tính toán tốn CPU trên rất nhiều phần tử, bỏ parallel có thể làm tổng thời gian tăng. Cân nhắc tách bước **lấy đúng trang** ra khỏi bước **xử lý phần tử** khi pipeline và cấu trúc dữ liệu cho phép, nhưng phải giữ semantic và kiểm thực nghiệm.

## 7. Thứ tự với filter, map, sorted, distinct

### 7.1. filter trước hay sau skip/limit?

Giả sử:

~~~text
Nguồn: [A, B, C, D, E, F]
Loại B: [A, C, D, E, F]
~~~

Lời gọi:

~~~java
List<String> result = names.stream()
        .filter(s -> !s.equals("B"))
        .skip(1)
        .limit(2)
        .toList();
// [C, D]
~~~

`skip(1)` ở đây bỏ **một phần tử của Stream đã lọc** (`A`), không phải phần tử ở index 1 của List gốc (`B`). Khi đặt `skip` trước filter, ý nghĩa có thể khác:

~~~java
List<String> changed = names.stream()
        .skip(1)
        .filter(s -> !s.equals("B"))
        .limit(2)
        .toList();
// [C, D] trong dữ liệu này; nhưng vì một lý do khác.
~~~

Hai ví dụ tình cờ cho cùng kết quả ở dữ liệu đã chọn. Đừng suy ra có thể đổi chỗ `skip` và `filter` nói chung. Dùng một trường hợp phản chứng:

~~~java
List<String> a = Stream.of("A", "B", "C", "D")
        .filter(s -> !s.equals("A"))
        .skip(1)
        .limit(2)
        .toList();
// [C, D]

List<String> b = Stream.of("A", "B", "C", "D")
        .skip(1)
        .filter(s -> !s.equals("A"))
        .limit(2)
        .toList();
// [B, C]
~~~

Bước filter trước sẽ thay thứ tự vị trí của những phần tử được giữ; slicing sau đó áp dụng **trên kết quả trung gian**. Đây là nguyên tắc chung: **`skip/limit` dựa trên vị trí trong Stream ngay trước chúng**, không phải vị trí cố định ở nguồn ban đầu.

### 7.2. map và slicing

`map` là phép biến đổi từng phần tử, về bản chất giữ số lượng phần tử nếu mapper trả một giá trị mỗi đầu vào:

~~~java
List<String> lower = names.stream()
        .skip(2)
        .limit(3)
        .map(String::toLowerCase)
        .toList();
// [c, d, e]
~~~

Nếu mapper là hàm thuần, chọn slice trước rồi mới map thường giúp tránh chuyển đổi những phần tử không cần dùng; tuy nhiên **không dựa vào số lần mapper được gọi làm hợp đồng**. Stream implementation có thể tối ưu một số stage hoặc xử lý song song khác với dự đoán.

Nếu mapper có side effect (gửi thông báo, tăng counter...) thì việc đổi thứ tự stage càng thay đổi cả tác động phụ; nhưng đó thường là dấu hiệu phải **tách side effect ra khỏi pipeline** thay vì dùng mapper để ghi thay đổi bất kỳ.

### 7.3. sorted trước limit: chọn top-k khác với sort một prefix

~~~java
List<Integer> smallest = Stream.of(9, 4, 1, 8, 2)
        .sorted()
        .limit(2)
        .toList();
// [1, 2]

List<Integer> sortedPrefix = Stream.of(9, 4, 1, 8, 2)
        .limit(2)
        .sorted()
        .toList();
// [4, 9]
~~~

**Hai biểu thức có ý nghĩa khác**. `sorted().limit(2)` cần biết hai phần tử nhỏ nhất của toàn bộ nguồn, còn `limit(2).sorted()` chỉ sắp hai phần tử đầu của Stream.

Về hiệu năng, `sorted` là stateful operation. Trên một nguồn chưa sắp, nó thường phải xét một lượng dữ liệu lớn, thậm chí toàn bộ nguồn, trước khi đưa ra kết quả theo thứ tự yêu cầu. Không mặc định `limit(2)` sau `sorted` sẽ tránh toàn bộ chi phí sắp xếp. Nếu chỉ cần top-k từ dữ liệu rất lớn, có thể cần thuật toán specialized dựa trên heap/index/query phù hợp.

### 7.4. distinct và slicing

~~~java
List<String> result = Stream.of("a", "a", "b", "c", "c", "d")
        .distinct()
        .skip(1)
        .limit(2)
        .toList();
// [b, c]
~~~

`distinct` biến nhiều phần tử trùng nhau thành giá trị duy nhất. `skip(1)` bỏ **một giá trị distinct đầu tiên**, không phải một bản ghi đầu nguồn. Với ordered Stream, `distinct` ổn định theo encounter order, tức giữ phần tử đầu khi có trùng lặp. Với unordered Stream, không có cam kết giữ bản sao nào đầu tiên.

Kết hợp `distinct`, `sorted`, `skip` và `limit` trên parallel Stream ordered có thể làm tăng chi phí trạng thái/đệm. Không cần gọi `unordered()` chỉ vì pipeline dài: chỉ gỡ order nếu semantic thực sự không cần order.

## 8. Phân trang bằng skip(offset).limit(size)

Mẫu đơn giản:

~~~java
List<T> page = source.stream()
        .skip(offset)
        .limit(pageSize)
        .toList();
~~~

Đây là **mẫu chung** với `source` là collection có thứ tự ổn định, `offset` là `long >= 0` và `pageSize` là `long >= 0`. `toList()` yêu cầu JDK16+; với dự án còn dùng Java8, dùng `collect(Collectors.toList())`.

Nếu các trang đánh số từ 0:

\[
\text{offset} = \text{pageIndex} \times \text{pageSize}
\]

Ví dụ:

~~~java
int pageIndex = 2; // Trang thứ ba nếu bắt đầu đếm từ 0.
int pageSize = 3;

long offset = Math.multiplyExact((long) pageIndex, pageSize);

List<Integer> page = IntStream.range(0, 12)
        .boxed()
        .skip(offset)
        .limit(pageSize)
        .toList();
// [6, 7, 8]
~~~

### 8.1. Tại sao phải cast trước phép nhân?

Sai:

~~~java
long offset = pageIndex * pageSize;
~~~

Nếu cả hai toán hạng là `int`, phép nhân được thực hiện **bằng int trước**, có thể tràn, rồi mới chuyển kết quả sai sang `long`.

Đúng:

~~~java
long offset = Math.multiplyExact((long) pageIndex, pageSize);
~~~

Ít nhất một toán hạng được đổi sang long **trước khi nhân**; `Math.multiplyExact` còn phát hiện tràn long thay vì tạo offset sai. Kiểm thêm `pageIndex >= 0`, `pageSize >= 0` theo hợp đồng input trước khi tính; nếu phép nhân tràn, API cần trả lỗi/giới hạn truy vấn phù hợp.

### 8.2. Phân trang cần một thứ tự ổn định

Khi danh sách được hiển thị cho người dùng, “trang 2” chỉ có ý nghĩa khi **có một thứ tự xác định**. Nếu nguồn là tập hợp không có order, hoặc query database không có `ORDER BY`, việc `skip` theo vị trí có thể trả các phần tử không ổn định qua các lần gọi.

Nên quy định một khóa sắp tăng/giảm và **tie-breaker ổn định** khi có nhiều bản ghi cùng giá trị chính, ví dụ:

~~~java
Comparator<Order> byTimeThenId =
        Comparator.comparing(Order::createdAt)
                .thenComparing(Order::id);
~~~

Đây là **mảnh mã minh họa** với các getter và class `Order` do ứng dụng định nghĩa. Nếu chỉ sort theo `createdAt` khi nhiều bản ghi cùng timestamp, thứ tự giữa chúng có thể phụ thuộc thứ tự đầu vào và gây trùng/bỏ bản ghi giữa các trang; thêm ID giúp tạo thứ tự toàn phần khi ID duy nhất.

### 8.3. Offset pagination trên dữ liệu thay đổi

Ngay cả khi có sort ổn định, hai lần gọi để lấy trang có thể đọc **hai trạng thái nguồn khác nhau**:

- Bản ghi mới thêm vào trước vị trí đang xem có thể khiến một bản ghi bị lặp sang trang sau.
- Bản ghi bị xóa có thể làm một bản ghi bị bỏ qua giữa các trang.
- Việc đổi khóa sort có thể khiến phần tử di chuyển qua ranh giới trang.

Đây là vấn đề **tính nhất quán dữ liệu và thời điểm đọc**, không được `skip/limit` tự giải quyết. Nếu yêu cầu trang nhất quán trong một phiên xem, có thể cần snapshot, phiên bản dữ liệu hoặc chiến lược cursor/keyset pagination ở tầng lưu trữ.

### 8.4. Đừng bắt JVM xử lý toàn bộ query chỉ để skip

Nếu dữ liệu đang nằm trong database hoặc công cụ tìm kiếm, nên xem xét **phân trang tại nguồn**:

~~~sql
SELECT id, created_at, title
FROM items
ORDER BY created_at ASC, id ASC
LIMIT 20 OFFSET 100;
~~~

Đây là **SQL minh họa**, cú pháp và hiệu năng cụ thể khác nhau theo hệ quản trị. Với offset sâu, database vẫn có thể phải xử lý nhiều dòng trước khi trả trang. Nếu có index và thứ tự phù hợp, query có thể tiết kiệm việc chuyển hàng nghìn/millions row lên JVM; với phân trang sâu và dữ liệu thường xuyên thay đổi, cân nhắc keyset pagination thay vì offset.

Điểm chính là **đặt slicing ở nơi phù hợp với nguồn**. `Stream.skip` là công cụ trên một Stream, không phải API database và không tự đẩy `OFFSET` xuống query.

## 9. Stream vô hạn: limit quan trọng để kết thúc

Một Stream có thể sinh ra vô hạn phần tử:

~~~java
Stream<Integer> numbers = Stream.iterate(0, n -> n + 1);
~~~

`Stream.iterate` ở dạng hai tham số tạo **Stream có thứ tự**. Nếu thu thập toàn bộ một Stream vô hạn mà không có cách dừng, terminal operation như `toList` không kết thúc bình thường vì dữ liệu không có điểm cuối. Có `limit` giúp tạo một đoạn hữu hạn:

~~~java
List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();
// [0, 1, 2, 3, 4]
~~~

Kết hợp với skip:

~~~java
List<Integer> fromFive = Stream.iterate(0, n -> n + 1)
        .skip(5)
        .limit(3)
        .toList();
// [5, 6, 7]
~~~

`skip(5)` **không biến nguồn vô hạn thành hữu hạn**. `limit(3)` phía sau mới đặt giới hạn đầu ra. Nếu dùng `skip` mà không có limit hay điều kiện kết thúc phù hợp rồi gọi `toList()` trên Stream vô hạn, chương trình không có điểm dừng bình thường.

### 9.1. Limit là cần thiết nhưng chưa luôn đủ

Java Stream package documentation nêu **sự xuất hiện của một short-circuiting operation là cần nhưng chưa đủ** để mọi pipeline vô hạn có thể kết thúc. Ví dụ:

~~~java
Stream.iterate(0, n -> n + 1)
        .filter(n -> n < 0)
        .limit(5)
        .toList();
~~~

Đây là **phản ví dụ không nên chạy**: nguồn liên tục sinh số không âm (trước khi tràn số học int nếu thực thi đủ lâu có thể đổi dấu), filter ban đầu không sản xuất phần tử; việc đợi 5 phần tử hợp lệ có thể không kết thúc đúng như dự kiến. Để tránh phụ thuộc overflow và nêu một phản ví dụ thực sự vô hạn, hãy xem ví dụ rõ hơn:

~~~java
Stream.generate(() -> 1)
        .filter(x -> x == 2)
        .limit(5)
        .toList(); // Không kết thúc bình thường.
~~~

Nguồn vô hạn chỉ sinh 1 nên filter không cho qua phần tử nào; limit không nhận đủ phần tử và terminal operation không thể hoàn tất. Không chạy đoạn này trong chương trình demo chính.

### 9.2. Skip rất lớn trên nguồn sinh từng phần tử

~~~java
Stream.iterate(0L, n -> n + 1L)
        .skip(1_000_000L)
        .limit(10)
        .toList();
~~~

Đây là mảnh code chỉ dùng để giải thích chi phí; không cần chạy để hiểu. Nguồn `iterate` tạo phần tử theo quy luật tuần tự, nên skip số lượng rất lớn có thể tốn CPU/thời gian so với bắt đầu trực tiếp từ chỉ số mong muốn.

Với dữ liệu dãy số tính được bằng công thức, `LongStream.range(1_000_000, 1_000_010)` thường diễn đạt rõ hơn ý định “chỉ cần đoạn ấy”. Không khẳng định mọi Stream nguồn khác cũng có thể truy cập theo chỉ số: nhiều nguồn là iterator/file/network một chiều và phải duyệt để bỏ qua dữ liệu.

## 10. Limit và skip trên primitive streams

Ba primitive stream đều có hai API tương ứng:

~~~java
IntStream.range(0, 10).skip(3).limit(2);   // IntStream.
LongStream.range(0L, 10L).skip(3).limit(2); // LongStream.
DoubleStream.of(1.0, 2.0, 3.0).limit(2);   // DoubleStream.
~~~

Những dòng trên là **mảnh pipeline**, chưa có terminal operation. `skip/limit` đều nhận `long` không âm, kể cả trên `IntStream`. Không cần `boxed()` khi chỉ tính `sum()`, `average()` hoặc `toArray()` trên primitive; `boxed()` chỉ cần khi API phía sau yêu cầu object, ví dụ `List<Integer>`.

~~~java
int[] result = IntStream.range(0, 10)
        .skip(3)
        .limit(4)
        .toArray();
// [3, 4, 5, 6]
~~~

Kết quả và quy tắc encounter order giống ngữ nghĩa của object Stream. Hợp đồng performance trong ordered parallel pipelines cũng tương tự; không có phép ngoại lệ vì dùng primitive.

### 10.1. Không nhầm limit với giới hạn số byte hay thời gian

`limit(n)` đếm **phần tử của Stream**, không đếm byte, bản ghi nằm trong một phần tử, hay số millisecond chạy. Nếu mỗi phần tử là một chunk chứa nhiều bản ghi, `limit(5)` chỉ giữ 5 chunk, không phải 5 bản ghi bên trong.

Nếu mục tiêu là deadline, timeout hoặc dung lượng bộ nhớ, cần cơ chế riêng (backpressure, cancellation, batching, deadline check...) phù hợp với nguồn và hệ thống. `limit` không bảo đảm stop chính xác trong x millisecond.

## 11. Terminal operation có thể ảnh hưởng cách thực thi

Một pipeline chỉ được chạy khi có terminal operation, và **terminal operation có thể tối ưu hóa** dựa trên thông tin source/pipeline. Điều này đặc biệt quan trọng nếu bạn muốn dùng `peek` làm công cụ quan sát.

Ví dụ:

~~~java
long count = List.of("A", "B", "C", "D").stream()
        .peek(System.out::println)
        .limit(2)
        .count();
// count bằng 2; không có bảo đảm đúng 2 dòng println.
~~~

Đây là code chạy được nhưng **không nên dùng để kiểm tra số lần xử lý**. Theo ghi chú Stream API, nếu implementation xác định được kết quả `count()` từ số phần tử nguồn và các stage không làm đổi kích thước, nó có thể bỏ qua một số callback `peek`/`map` mà không ảnh hưởng kết quả.

Tương tự, trong parallel Stream, thời gian và thread thực thi callback có thể khác thứ tự encounter. **Không thiết kế nghiệp vụ dựa trên số callback bị bỏ hoặc thực hiện dư** bởi `limit/skip`.

Muốn kiểm chứng, hãy tạo kết quả bằng terminal operation như `toList()`/`toArray()` hoặc so sánh giá trị đúng nghĩa với một oracle độc lập. Nếu cần tác dụng phụ bắt buộc, đặt chúng trong API xử lý rõ ràng và kiểm soát nguồn/thread, thay vì dùng `peek` để chạy nghiệp vụ khi limit/skip cắt pipeline.

## 12. Chương trình Java hoàn chỉnh: limit, skip, ordered và unordered

Lưu chương trình thành file **`StreamSliceDemo.java`**. Nó chạy trên **JDK 17+**; các API `Stream.limit`, `skip`, `unordered`, `parallel` đã có từ Java 8. Mã dùng `List.of` (Java 9+) và `Stream.toList` (Java 16+), đều là API hiện hành, đúng với định hướng chỉ dùng kiến thức còn áp dụng.

Chương trình chọn các phép thử **có đầu ra xác định**:

- Slicing trên List có encounter order.
- So sánh thứ tự các bước `limit` và `skip`.
- `filter`, `map`, `sorted`, `distinct` trước slicing.
- Ordered parallel Stream vẫn lấy đúng vị trí.
- Unordered parallel Stream **chỉ kiểm số lượng**, không giả định những phần tử cụ thể được chọn.
- Stream vô hạn có `limit` và `skip + limit`.
- Giá trị biên 0, skip quá độ dài và đối số âm.
- Phân trang có phép nhân offset kiểm tràn.

~~~java
import java.util.*;
import java.util.stream.*;

public class StreamSliceDemo {
    public static void main(String[] args) {
        List<String> names = List.of("A", "B", "C", "D", "E", "F");

        System.out.println("limit 3: "
                + names.stream().limit(3).toList());
        System.out.println("skip 2: "
                + names.stream().skip(2).toList());
        System.out.println("page: "
                + names.stream().skip(2).limit(3).toList());
        System.out.println("reverse order: "
                + names.stream().limit(3).skip(2).toList());

        System.out.println("filtered slice: "
                + names.stream().filter(s -> !s.equals("B"))
                        .skip(1).limit(2).toList());
        System.out.println("mapped slice: "
                + names.stream().skip(2).limit(3)
                        .map(String::toLowerCase).toList());
        System.out.println("sorted slice: "
                + Stream.of(9, 4, 1, 8, 2).sorted()
                        .skip(1).limit(2).toList());
        System.out.println("distinct slice: "
                + Stream.of("a", "a", "b", "c", "c", "d")
                        .distinct().skip(1).limit(2).toList());

        System.out.println("ordered parallel: "
                + IntStream.range(0, 20).parallel()
                        .skip(7).limit(5).boxed().toList());
        System.out.println("unordered limit count: "
                + IntStream.range(0, 100).parallel()
                        .unordered().limit(7).count());
        System.out.println("unordered skip+limit count: "
                + IntStream.range(0, 100).parallel()
                        .unordered().skip(90).limit(3).count());

        System.out.println("infinite limit: "
                + Stream.iterate(0, n -> n + 1)
                        .limit(5).toList());
        System.out.println("infinite slice: "
                + Stream.iterate(0, n -> n + 1)
                        .skip(5).limit(3).toList());
        System.out.println("skip past end: "
                + names.stream().skip(99).toList());
        System.out.println("limit zero: "
                + names.stream().limit(0).toList());

        int pageIndex = 2;
        int pageSize = 3;
        long offset = Math.multiplyExact((long) pageIndex, pageSize);
        System.out.println("numeric page: "
                + IntStream.range(0, 12).boxed()
                        .skip(offset).limit(pageSize).toList());

        try {
            names.stream().limit(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative limit rejected");
        }
        try {
            names.stream().skip(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative skip rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamSliceDemo.java
java StreamSliceDemo
~~~

Stdout:

~~~text
limit 3: [A, B, C]
skip 2: [C, D, E, F]
page: [C, D, E]
reverse order: [C]
filtered slice: [C, D]
mapped slice: [c, d, e]
sorted slice: [2, 4]
distinct slice: [b, c]
ordered parallel: [7, 8, 9, 10, 11]
unordered limit count: 7
unordered skip+limit count: 3
infinite limit: [0, 1, 2, 3, 4]
infinite slice: [5, 6, 7]
skip past end: []
limit zero: []
numeric page: [6, 7, 8]
Negative limit rejected
Negative skip rejected
~~~

### 12.1. Đọc kết quả theo ngữ nghĩa

1. `limit 3: [A,B,C]` và `skip 2: [C,D,E,F]` xác minh hai phép độc lập trên List có thứ tự.
2. `page: [C,D,E]` khác `reverse order: [C]`, minh họa thứ tự các intermediate operations là một phần ngữ nghĩa.
3. `filtered slice: [C,D]` và `mapped slice: [c,d,e]` chứng minh slicing áp dụng theo vị trí ở **stage hiện tại**.
4. `sorted slice: [2,4]` và `distinct slice: [b,c]` cho thấy sort/khử trùng lặp trước khi cắt có thể thay danh sách ứng viên.
5. `ordered parallel: [7,8,9,10,11]` chứng minh parallel **không tự xóa encounter order**.
6. `unordered limit count: 7` và `unordered skip+limit count: 3` chỉ kiểm số phần tử. **Không suy luận tập giá trị chính xác** vì pipeline đã bỏ yêu cầu thứ tự.
7. `infinite limit` và `infinite slice` kết thúc vì có `limit` sau số bước hữu hạn đáp ứng điều kiện.
8. `skip past end: []` và `limit zero: []` là những trường hợp hợp lệ.
9. `numeric page: [6,7,8]` dùng offset tính từ chỉ số trang và kích thước trang.
10. Các lời gọi có số âm bị từ chối bằng `IllegalArgumentException`; những lỗi input này xảy ra khi xây pipeline tương ứng, trước khi dùng kết quả.

**Không thiết kế test phụ thuộc số lần callback `map`, `filter` hoặc `peek` chạy khi framework dùng parallel hoặc tối ưu hóa pipeline.** Chương trình chỉ khẳng định phần kết quả mà hợp đồng API bảo đảm.

## 13. Kiểm thử đúng encounter order và số lượng

Một bộ test hữu ích cần phân biệt **kết quả xác định của Stream ordered** và **điều kiện bất biến khi Stream unordered**.

| Ca thử | Kỳ vọng chính |
|---|---|
| Ordered List + `limit(3)` | Đúng ba phần tử đầu theo thứ tự List |
| Ordered List + `skip(2)` | Bỏ đúng hai phần tử đầu |
| `skip(2).limit(3)` | Giữ đoạn vị trí 2..4 nếu đủ dữ liệu |
| `limit(3).skip(2)` | Giữ tối đa một phần tử trong prefix ba |
| `limit(0)` | Kết quả rỗng |
| `skip(0)` | Kết quả giữ nguyên |
| `skip(n)` với n lớn hơn size | Kết quả rỗng |
| `limit(-1)` hoặc `skip(-1)` | Ném `IllegalArgumentException` |
| Ordered parallel | Tập giá trị và thứ tự như ngữ nghĩa ordered |
| Unordered parallel + limit | Đúng số lượng và thuộc nguồn; không assert “n phần tử đầu” |
| Unordered parallel + skip | Giữ lại số lượng theo ngữ nghĩa, không assert những ID nào bị bỏ |
| `filter` trước slicing | Vị trí tính trên dãy đã lọc |
| `sorted` trước slicing | Đầu ra theo thứ tự đã sort, không phải thứ tự gốc |
| Stream vô hạn + limit | Có thể kết thúc nếu pipeline tạo đủ phần tử cho giới hạn |
| Stream vô hạn + filter không bao giờ đạt | Có thể không kết thúc dù có limit phía sau |
| Phân trang trên nguồn đang thay đổi | Cần test snapshot/tie-breaker, không chỉ skip/limit |

### 13.1. Test oracle bằng List.subList

Với `List<T>` có thứ tự, có thể tính kết quả mong đợi bằng chỉ số:

~~~java
List<Integer> source = List.of(4, 8, 15, 16, 23, 42);

int from = 2;
int max = 3;
int to = Math.min(source.size(), from + max);

List<Integer> expected = source.subList(from, to);
List<Integer> actual = source.stream()
        .skip(from)
        .limit(max)
        .toList();

if (!expected.equals(actual)) {
    throw new AssertionError("Ordered slice mismatch");
}
~~~

Đây là mảnh Java 17+ chạy được khi import `java.util.*;`. Trong code production với `from/max` không tin cậy, **validate không âm và chống overflow** trước phép cộng như mục phân trang. Ở đây giá trị nhỏ đã biết nên an toàn.

So sánh List theo giá trị và vị trí khi nguồn ordered. Không dùng một unordered Stream rồi ép kỳ vọng bằng `subList`: đó là sai hợp đồng.

### 13.2. Test bất biến khi unordered

Nếu nguồn hữu hạn chứa 100 phần tử khác nhau và gọi `unordered().limit(7)`, điều bạn có thể kiểm là:

- Số lượng đúng 7 trong ví dụ nguồn có ít nhất 7 phần tử.
- Các phần tử kết quả đều thuộc tập nguồn.
- Không có giá trị mới được tạo bởi limit.
- Nếu nguồn không chứa trùng lặp, limit không tự tạo ra bản sao trùng của một phần tử.

**Không kiểm** kết quả phải là `[0,1,2,3,4,5,6]` hoặc lặp lại giống hệt giữa các JDK/CPU. Một implementation có thể tình cờ cho danh sách ấy, nhưng không phải bảo đảm portable.

### 13.3. Test hiệu năng độc lập với test tính đúng

Benchmark nên đo những phương án phù hợp:

1. Sequential ordered skip/limit.
2. Parallel ordered skip/limit.
3. Parallel unordered skip/limit **chỉ khi ngữ nghĩa cho phép**.
4. Cắt trực tiếp trên nguồn có random access hay query được phân trang tại nguồn.

Dùng cùng dữ liệu, warm-up JIT, tránh tác dụng phụ làm thay đổi điều kiện thử, đo time/memory và lặp lại đủ lần. Với Java, JMH hữu ích hơn một lần gọi `System.nanoTime()`. So sánh **độ đúng trước**, sau đó mới tối ưu thời gian.

Không benchmark trường hợp unordered rồi dùng một tập kết quả khác bài toán ordered và kết luận “nhanh hơn nên thay được”. Hai chương trình như vậy có **hợp đồng kết quả khác nhau**.

## 14. Những sai lầm thường gặp

**Lỗi 1 — Nghĩ limit(n) luôn chỉ xử lý n phần tử nguồn.** `filter` có thể bỏ nhiều phần tử, `sorted` có thể cần xét nguồn rộng, parallel có thể xử lý theo nhánh; limit chỉ đảm bảo đầu ra tối đa n.

**Lỗi 2 — Gọi skip(n) là short-circuiting.** `skip` là stateful nhưng không short-circuit như `limit`; nó bỏ prefix và để phần còn lại tiếp tục.

**Lỗi 3 — Đổi chỗ skip và limit.** `skip(2).limit(3)` khác `limit(3).skip(2)`; thay vị trí vì “cho dễ đọc” có thể làm mất phần tử.

**Lỗi 4 — Đổi chỗ filter và skip vì tưởng vẫn đúng.** Vị trí sau filter được tính trên dãy đã lọc, không phải index gốc; phải kiểm theo nghiệp vụ.

**Lỗi 5 — Dùng unordered() để tối ưu phân trang có thứ tự.** Khi bỏ encounter order, những phần tử được skip/limit có thể là bất kỳ; pagination không còn nghĩa “trang tiếp theo”.

**Lỗi 6 — Coi parallel là tự động bỏ order.** `list.parallelStream()` vẫn giữ encounter order; giới hạn và skip phải tuân theo order ấy.

**Lỗi 7 — Coi unordered là shuffle/random sampling.** Nó chỉ loại ràng buộc thứ tự; không cung cấp phân phối ngẫu nhiên hay reproducibility.

**Lỗi 8 — Dựa vào thứ tự xuất hiện của log trong peek/map.** Callback có thể được gọi ở nhiều thread và một số stage có thể bị tối ưu bỏ; không đặt nghiệp vụ quan trọng vào side effect.

**Lỗi 9 — Phân trang không có tie-breaker.** Nếu thứ tự không toàn phần hoặc dữ liệu đổi giữa các lần đọc, bản ghi có thể lặp/bỏ qua trang. Cần khóa sort ổn định và chính sách nhất quán.

**Lỗi 10 — Offset phép nhân overflow.** `long offset = intPage * intSize` có thể tràn int trước khi cast; dùng cast sớm và `Math.multiplyExact` với input validation.

**Lỗi 11 — Bỏ dữ liệu khối lượng lớn trong JVM dù nguồn hỗ trợ truy vấn theo trang.** `skip` không tự biến thành SQL OFFSET; cân nhắc đẩy slicing xuống DB hoặc nguồn có cấu trúc phù hợp.

**Lỗi 12 — Gọi limit trên Stream vô hạn rồi mặc định luôn kết thúc.** Nếu filter không cho phần tử nào qua, pipeline không đạt điều kiện dừng dù limit có mặt.

**Lỗi 13 — Dùng lại cùng Stream sau terminal operation.** Stream chỉ dùng một lần; cần tạo Stream mới từ nguồn cho mỗi truy vấn.

**Lỗi 14 — Giả định sorted().limit(k) giống limit(k).sorted().** Biểu thức đầu tìm k phần tử nhỏ nhất của toàn bộ nguồn, biểu thức sau chỉ sort k phần tử gốc đầu.

**Lỗi 15 — Dùng sequential() như mệnh lệnh từng stage.** Chế độ tuần tự/song song áp dụng cho pipeline khi thực thi, không là hợp đồng lịch chạy chính xác của callback.

## 15. Bài tập tự luyện

1. Cho Stream ordered `[10,20,30,40,50,60]`. Dự đoán `skip(2).limit(3)` và `limit(3).skip(2)`.
2. Vì sao `IntStream.range(0,100).parallel().limit(5)` phải trả `0..4`, còn thêm `unordered()` thì không còn bắt buộc?
3. Một nguồn có 10 triệu bản ghi, cần lấy 20 bản ghi sau 8 triệu bản ghi đầu. Những yếu tố nào quyết định `skip(8_000_000).limit(20)` có tốn kém?
4. Một website dùng `HashSet.stream().skip(20).limit(10)` để hiển thị trang 3. Vấn đề gì có thể xảy ra?
5. Dùng `filter` để chọn bản ghi active rồi `skip/limit`. Cần hiểu offset theo danh sách gốc hay theo các bản ghi active?
6. Khi nào `limit(5)` không đủ để kết thúc một Stream vô hạn?
7. Tại sao `Stream.of(9,4,1,8,2).sorted().limit(2)` khác `limit(2).sorted()`?
8. Viết công thức tính offset an toàn cho trang đánh số từ 0 với hai biến int không âm.
9. `Stream.generate(...)` khác `Stream.iterate(...)` thế nào về encounter order?
10. Tại sao nên kiểm dữ liệu đầu ra thay vì đếm số lời gọi trong `peek`?
11. Một ứng dụng chỉ cần bất kỳ 100 phần tử từ tập lớn. Có thể cân nhắc `unordered().limit(100)` không? Có phải random sample đồng đều không?
12. Nếu cơ sở dữ liệu đã hỗ trợ `ORDER BY` + phân trang, tại sao đôi khi nên làm slicing tại DB thay vì tải toàn bộ lên JVM?
13. Dữ liệu thay đổi giữa lúc người dùng xem hai trang. Vì sao chỉ có `skip + limit` không tránh được trùng/mất phần tử?
14. Với `List` có thứ tự, viết một oracle kiểm tra `skip(from).limit(size)` bằng chỉ số `subList`.

**Gợi ý đáp án:**

1. `[30,40,50]` và `[30]`.
2. Vì encounter order của range vẫn được giữ trong parallel; unordered loại ràng buộc lấy prefix đầu chính xác.
3. Nguồn có hỗ trợ chia/sized hay random access không, pipeline có filter/sort không, chế độ parallel/ordered, chi phí upstream, memory/đệm.
4. HashSet không bảo đảm encounter order, trang có thể không ổn định; phải định nghĩa sort với tie-breaker nếu muốn phân trang lặp lại.
5. Nếu filter trước skip thì offset tính trên các bản ghi **đã qua filter**; không tự áp dụng index gốc.
6. Khi các stage phía trước không tạo đủ phần tử (ví dụ filter luôn loại bỏ) hoặc xử lý bị chặn.
7. Một bên sort toàn nguồn để chọn hai nhỏ nhất; bên kia chỉ sort hai phần tử ban đầu.
8. `long offset = Math.multiplyExact((long) pageIndex, pageSize);` sau khi validate không âm.
9. `iterate` có encounter order theo chuỗi; `generate` mô tả nguồn vô hạn unordered.
10. Stream có thể tối ưu stage hoặc xử lý trên nhiều thread; số lần/ thứ tự gọi không phải hợp đồng của slicing.
11. Có nếu thứ tự không cần, nhưng **không** được coi là random sampling có phân phối bảo đảm.
12. Để giảm dữ liệu truyền qua mạng và tận dụng bộ lọc/index/order tại nguồn, dù offset sâu vẫn có thể đắt.
13. Dữ liệu bị thêm/xóa/đổi sort-key làm dịch ranh giới; cần snapshot/cursor hoặc mô hình nhất quán khác.
14. Xác định đoạn hợp lệ theo `from` và `from + size` sau validate, so sánh List kết quả với `subList`.

## Ghi nhớ

- `limit(n)` giữ tối đa n phần tử; **short-circuiting stateful**.
- `skip(n)` bỏ n phần tử đầu; **stateful nhưng không short-circuiting**. Cả hai yêu cầu n không âm.
- Với **encounter order**, chọn/bỏ đúng prefix đầu. Parallel không xóa order, nên ordered parallel slicing có thể tốn phối hợp và bộ nhớ.
- `unordered()` có thể giảm chi phí khi **thứ tự thực sự không quan trọng**, nhưng thay đổi ngữ nghĩa; không dùng để lấy trang ổn định hay thay thuật toán sampling.
- `sequential()` đôi khi tốt hơn parallel khi phải giữ thứ tự; hiệu năng phải đo trên dữ liệu và môi trường thực.
- Vị trí của `filter`, `sorted`, `distinct`, `skip` và `limit` trong pipeline **có ý nghĩa**, không tùy tiện đổi chỗ.
- Phân trang cần input validation, offset chống tràn, sort ổn định và chính sách xử lý dữ liệu thay đổi.
- Với Stream vô hạn, limit có thể giúp kết thúc nhưng không đủ nếu các stage phía trước không bao giờ cho phần tử đi qua.
- Kiểm **giá trị đầu ra** theo hợp đồng API; không kiểm số lần/đúng thread thực thi mapper, filter hay peek.

### Tài liệu chính thức đang được hỗ trợ

- [Oracle Java SE 26 — Stream.limit/skip, API Note về ordered parallel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — java.util.stream: Ordering, short-circuiting, side effects](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — BaseStream.unordered/sequential/parallel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
- [Oracle Java SE 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle Java SE 26 — LongStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html)
- [Oracle Java SE 26 — DoubleStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html)
- [Oracle Java SE 26 — Spliterator.SIZED/SUBSIZED](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html)
