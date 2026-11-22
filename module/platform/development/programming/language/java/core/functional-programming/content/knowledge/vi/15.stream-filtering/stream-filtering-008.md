# Thứ tự đặt thao tác lọc và giới hạn làm thay đổi kết quả trong Java Stream

## 1. Vấn đề cốt lõi: lọc trước hay giới hạn trước?

Với Java Stream, hai chuỗi xử lý trông gần giống nhau nhưng có thể trả kết quả **khác hẳn**:

~~~java
numbers.stream().filter(n -> n % 2 == 0).limit(3).toList();

numbers.stream().limit(3).filter(n -> n % 2 == 0).toList();
~~~

Đoạn mã minh họa trên giả định `numbers` là một `List<Integer>`. Nếu danh sách nguồn là:

~~~text
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
~~~

thì kết quả là:

| Pipeline | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `filter(even).limit(3)` | `[2, 4, 6]` | Lấy **3 số chẵn đầu tiên** trong nguồn |
| `limit(3).filter(even)` | `[2]` | Xét **3 phần tử đầu tiên**, rồi chỉ giữ số chẵn |

**Lý do:** các bước trong pipeline được nối theo thứ tự đã viết. `filter` giữ hoặc loại phần tử; `limit(n)` giới hạn **số phần tử đi tới chính bước `limit`**, không phải lúc nào cũng là số phần tử gốc.

Do đó, `filter(...).limit(n)` có thể phải xét **nhiều hơn n phần tử nguồn** để tìm đủ n phần tử phù hợp, còn `limit(n).filter(...)` chỉ cho tối đa n phần tử đầu vào đi qua bước lọc tiếp theo.

Bài học này tập trung vào tác động của **thứ tự đặt thao tác lọc và giới hạn**, đồng thời chỉ ra các trường hợp kết hợp với `skip`, `sorted`, nguồn có thứ tự và parallel stream.

## 2. Hiểu chính xác hợp đồng của filter và limit

### 2.1. filter(Predicate): giữ phần tử thỏa điều kiện

`Stream<T>.filter(Predicate<? super T>)` tạo một Stream gồm những phần tử có kết quả kiểm tra bằng `true`. Ví dụ:

~~~java
List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Đây là mã minh họa nằm trong một phương thức, cần import `java.util.List`. Với nguồn từ 1 đến 10, kết quả là `[2, 4, 6, 8, 10]`.

Với một nguồn có encounter order như `List`, `filter` giữ **thứ tự tương đối** của các phần tử còn lại. Nó không tự sắp xếp các phần tử và không sửa trực tiếp danh sách nguồn.

Điều kiện nên là một hàm **stateless** và **non-interfering**: không cần trạng thái bên ngoài thay đổi giữa các lần gọi và không sửa nguồn trong lúc duyệt. Việc chỉ kiểm tra một phần tử không đòi hỏi sửa các phần tử khác.

### 2.2. limit(maxSize): lấy không quá maxSize phần tử tại vị trí của nó

`Stream<T>.limit(long maxSize)` là một phép toán trung gian **short-circuiting, stateful**: nó tạo Stream tối đa `maxSize` phần tử, tính từ **đầu thứ tự gặp** nếu Stream có encounter order.

~~~java
List<Integer> firstThree = numbers.stream()
        .limit(3)
        .toList();
// [1, 2, 3]
~~~

`maxSize` phải **không âm**; truyền số âm gây `IllegalArgumentException`. `limit(0)` cho một pipeline kết quả rỗng; `limit(n)` không thêm phần tử khi nguồn có ít hơn n phần tử.

Các từ quan trọng:

- **Tối đa**, không phải **luôn đúng n**: nếu nguồn hoặc các bước trước có ít phần tử hơn, đầu ra có thể ít hơn n.
- **Tại vị trí của nó**: limit đếm các phần tử đã vượt qua các bước trước.
- **Encounter order**: “đầu tiên” có nghĩa khi nguồn/pipeline có thứ tự gặp đã được xác định. Với nguồn không có thứ tự, không được dựa vào một nhóm phần tử cụ thể.
- **Short-circuit**: một terminal operation có thể hoàn tất mà không cần xử lý toàn bộ nguồn. Nhưng không được đoán số lần callback chính xác trên mọi implementation hay trong parallel stream.

### 2.3. Cả filter và limit đều là intermediate operations

Hai lời gọi trên chưa tự tạo kết quả danh sách. Ví dụ:

~~~java
Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3);
List<Integer> result = pipeline.toList();
~~~

Đoạn minh họa này cần import `java.util.stream.Stream` và `java.util.List`. Các bước trung gian thông thường được đánh giá theo yêu cầu khi có terminal operation như `toList()`. Vì vậy, nói “filter chạy xong trên toàn bộ danh sách rồi limit mới chạy” là **mô hình quá đơn giản**: các phần tử có thể được xử lý theo pipeline, và phép `limit` có thể khiến quá trình dừng sớm.

Cách diễn đạt đúng là **ngữ nghĩa kết quả tương đương việc lấy dãy sau mỗi phép biến đổi theo thứ tự pipeline**, chứ không nhất thiết trung gian nào cũng được lưu thành một danh sách.

## 3. Truy vết từng phần tử: filter rồi limit

Giả sử nguồn có thứ tự từ 1 đến 10, điều kiện là “số chẵn” và giới hạn là 3:

~~~java
numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
~~~

Bảng lý giải logic trên một pipeline tuần tự:

| Phần tử nguồn | Qua `filter`? | Số phần tử đã tới `limit` | Kết quả được giữ |
| --- | --- | --- | --- |
| 1 | Không | 0 | `[]` |
| 2 | Có | 1 | `[2]` |
| 3 | Không | 1 | `[2]` |
| 4 | Có | 2 | `[2,4]` |
| 5 | Không | 2 | `[2,4]` |
| 6 | Có | 3 | `[2,4,6]` |

Khi đã có 3 phần tử phù hợp, việc lấy danh sách kết quả này không cần xét các số 7–10. Bảng nhằm minh họa **thứ tự logic**, không phải hợp đồng về số lần gọi chính xác của predicate trong mọi chế độ thực thi.

Kết luận: `limit(3)` giới hạn **số phần tử sau filter**, nên ta nhận được ba số chẵn đầu tiên. Đây là lựa chọn đúng cho yêu cầu:

> “Cho tôi ba phần tử đầu tiên **thỏa điều kiện**.”

### 3.1. Nếu không có đủ phần tử phù hợp

Ví dụ:

~~~java
List<Integer> result = List.of(1, 3, 5, 6).stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// [6]
~~~

Chỉ một phần tử đi qua filter, nên giới hạn 3 không tạo thêm hai phần tử. `limit` không có chức năng bù hoặc lặp lại giá trị để đủ số lượng.

## 4. Truy vết ngược lại: limit rồi filter

Vẫn nguồn 1 đến 10, nhưng đổi thứ tự:

~~~java
numbers.stream()
        .limit(3)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Trước hết, `limit(3)` chỉ cho ba phần tử theo encounter order đi tiếp:

~~~text
Nguồn:             [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
Sau limit(3):      [1, 2, 3]
Sau filter(even):  [2]
~~~

Vì bộ lọc chỉ có thể loại phần tử, không thể “đi tìm thêm” các phần tử nguồn đã bị `limit` chặn, kết quả chỉ còn một số chẵn.

Cách viết này đúng khi yêu cầu là:

> “Chỉ xét ba phần tử đầu tiên của nguồn, sau đó lọc những phần tử đáp ứng điều kiện.”

Ví dụ nghiệp vụ: **“Kiểm tra trạng thái thanh toán của 10 đơn mới nhất”** khác **“Tìm 10 đơn mới nhất đã thanh toán”**. Điều kiện thanh toán đứng sau hay trước bước giới hạn làm đổi câu hỏi mà chương trình trả lời.

## 5. Hai bài toán đơn hàng thường bị nhầm

Cho danh sách đơn đã có thứ tự nghiệp vụ mong muốn:

~~~java
record Order(String id, boolean paid) {}

List<Order> orders = List.of(
        new Order("A", false),
        new Order("B", true),
        new Order("C", false),
        new Order("D", true),
        new Order("E", true)
);
~~~

Đây là **đoạn mã minh họa**: `record Order` được khai báo ở cấp kiểu, còn danh sách trong một phương thức; cần import `java.util.List`. Xét hai yêu cầu:

### 5.1. Yêu cầu A: “Hai đơn đầu tiên đã thanh toán”

~~~java
List<String> firstTwoPaid = orders.stream()
        .filter(Order::paid)
        .limit(2)
        .map(Order::id)
        .toList();
// [B, D]
~~~

Quy trình: lọc các đơn đã thanh toán `B,D,E`, lấy hai đơn đầu tiên `B,D`, lấy mã đơn.

### 5.2. Yêu cầu B: “Trong hai đơn đầu tiên, đơn nào đã thanh toán?”

~~~java
List<String> paidAmongFirstTwo = orders.stream()
        .limit(2)
        .filter(Order::paid)
        .map(Order::id)
        .toList();
// [B]
~~~

Quy trình: lấy hai đơn đầu `A,B`, rồi bỏ đơn chưa thanh toán `A`. Chỉ còn `B`. Dù cùng dùng các thao tác `filter`, `limit`, `map`, chương trình trả lời một câu hỏi **khác**.

### 5.3. “Đầu tiên” phải được định nghĩa theo thứ tự gì?

Nếu nguồn là danh sách đã sắp theo thời gian từ mới đến cũ thì “đầu tiên” có thể đồng nghĩa “mới nhất”. Nhưng nếu nguồn `List` đang theo thứ tự tải dữ liệu không được xác định, không nên gán ý nghĩa “mới nhất” cho `limit`.

Muốn lấy đơn mới nhất, hãy bảo đảm thứ tự được thiết lập, chẳng hạn sau khi sắp xếp theo thời gian:

~~~java
// Đoạn minh họa khi Order có trường timestamp:
// orders.stream()
//       .sorted(Comparator.comparing(Order::timestamp).reversed())
//       .filter(Order::paid)
//       .limit(2)
//       .toList();
~~~

Cú pháp trong phần comment là ví dụ thiết kế, **không khớp record Order hai trường ở trên** và không được coi là chương trình độc lập. Trước khi dùng thật, định nghĩa trường thời gian, chính sách xử lý thời điểm bằng nhau và comparator phù hợp. Nếu thứ tự là yêu cầu của nghiệp vụ, hãy đưa nó vào hợp đồng dữ liệu hoặc pipeline một cách tường minh.

## 6. Kết hợp skip và limit: phân trang đúng chỗ

`skip(n)` bỏ qua n phần tử đầu tiên **tại vị trí nó được đặt trong pipeline**; `limit(n)` giữ không quá n phần tử tiếp theo. Cả hai dựa vào thứ tự gặp nếu cần kết quả theo vị trí.

### 6.1. Phân trang trên tập đã lọc

~~~java
List<Integer> page = numbers.stream()
        .filter(n -> n % 2 == 0)
        .skip(2)
        .limit(2)
        .toList();
// [6, 8]
~~~

Nguồn từ 1 đến 10; sau filter là `[2,4,6,8,10]`, bỏ hai số chẵn đầu `2,4`, lấy hai số kế tiếp `6,8`.

Đây là thiết kế đúng cho:

> “Phân trang kết quả **đã lọc**: bỏ hai kết quả khớp trước đó và lấy hai kết quả khớp tiếp theo.”

### 6.2. Chỉ lọc trong một trang đã chọn từ nguồn

~~~java
List<Integer> page = numbers.stream()
        .skip(2)
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();
// [4]
~~~

Sau `skip(2)` còn `3,4,5,...`; `limit(2)` chọn `[3,4]`; lọc số chẵn chỉ còn `[4]`.

Cách này là:

> “Lấy một cửa sổ hai phần tử của nguồn rồi lọc trong cửa sổ ấy.”

Nó **không** tương đương phân trang trên tập đã lọc. Nếu API phân trang trả kết quả theo một điều kiện tìm kiếm, việc `skip`/`limit` trước `filter` có thể làm các trang có quá ít kết quả dù các phần tử phù hợp còn nằm ở phía sau.

### 6.3. Vị trí skip và limit cũng tác động nhau

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .skip(1)
        .toList();
// [4, 6]
~~~

Sau lọc là `[2,4,6,8,10]`, giới hạn 3 còn `[2,4,6]`, rồi bỏ một phần tử đầu còn `[4,6]`. Khác với `filter(...).skip(1).limit(3)`, vốn có thể cho `[4,6,8]`.

**Quy tắc phân trang:** nếu muốn trang thứ p của kết quả đáp ứng điều kiện, thường cần **lọc → sắp xếp theo thứ tự ổn định (nếu cần) → skip(offset) → limit(pageSize)**. Khi dữ liệu lớn và đến từ database, cân nhắc đẩy filter/sort/pagination xuống truy vấn và dùng pagination phù hợp thay vì tải toàn bộ dữ liệu lên bộ nhớ chỉ để phân trang bằng Stream.

## 7. sorted cũng ảnh hưởng tới ý nghĩa của limit

Thứ tự `sorted` và `limit` có thể thay đổi giá trị được chọn:

~~~java
List<Integer> source = List.of(7, 2, 6, 3, 8, 4, 5, 1);

List<Integer> smallestTwoEven = source.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .limit(2)
        .toList();
// [2, 4]

List<Integer> firstTwoEvenThenSorted = source.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .sorted()
        .toList();
// [2, 6]
~~~

Đoạn này cần import `java.util.List`, đặt trong một phương thức. Phân biệt:

- **Lọc → sắp xếp → lấy 2**: chọn hai giá trị nhỏ nhất trong những giá trị hợp lệ.
- **Lọc → lấy 2 → sắp xếp**: chọn hai giá trị hợp lệ xuất hiện đầu tiên trong nguồn, rồi sắp xếp chính hai giá trị được chọn.

Đừng “tối ưu” bằng cách tự chuyển `limit` lên trước `sorted` nếu yêu cầu là top N theo điểm, giá hoặc thời gian. Chỉ an toàn khi chứng minh thứ tự không làm đổi tập kết quả cần chọn.

### 7.1. filter không thay đổi thứ tự, nhưng điều kiện trước/sau limit quan trọng

Với nguồn có thứ tự, `filter` loại phần tử nhưng duy trì thứ tự tương đối; `limit` chọn một **tiền tố** của dãy tại điểm nó được đặt. Vì vậy đặt `limit` trước `filter` giới hạn phạm vi mà điều kiện được xét, không chỉ giới hạn kích thước danh sách đầu ra.

Trong một số trường hợp đặc biệt, cả hai pipeline cho kết quả giống nhau, ví dụ ba phần tử đầu đều thỏa predicate. Nhưng sự trùng hợp với một bộ test **không chứng minh hai pipeline tương đương cho mọi dữ liệu**.

## 8. short-circuit và tác động tới công việc thực thi

`limit` là thao tác trung gian có khả năng **short-circuit**. Khi terminal operation yêu cầu một danh sách có tối đa n phần tử, Stream có thể không cần đánh giá tất cả phần tử nguồn.

Với pipeline tuần tự, giả sử cần 3 số chẵn từ dãy 1 đến 10: về mặt logic, ta có thể dừng khi đã tìm được các số `2,4,6`. Nếu đặt `limit(3)` trước, chỉ ba phần tử `1,2,3` được xét tới bước lọc.

Tuy nhiên, cần thận trọng với các nhận định:

- **Không đoán chắc số lần gọi predicate** trong mọi pipeline. JDK có thể áp dụng tối ưu hợp lệ, và terminal operation khác nhau có thể tiêu thụ dữ liệu khác nhau.
- **Trong parallel stream**, nhiều phần nguồn có thể đã được xử lý khi đủ kết quả; không được kết luận mọi callback dừng ngay sau phần tử khớp thứ n.
- Các thao tác trung gian khác như `sorted()` có thể cần xem nhiều hoặc toàn bộ dữ liệu trước khi cung cấp kết quả phù hợp.
- Việc `limit(n)` ở đâu ảnh hưởng **ngữ nghĩa lựa chọn dữ liệu** trước khi ảnh hưởng tới hiệu năng. Đúng nghiệp vụ là tiêu chí ưu tiên.

### 8.1. Không dùng tác dụng phụ để quan sát và suy luận cứng nhắc

Ví dụ nên tránh:

~~~java
// Phản ví dụ: không dùng số lượt in để làm hợp đồng nghiệp vụ.
// List<Integer> result = numbers.stream()
//     .filter(n -> {
//         System.out.println("check " + n);
//         return n % 2 == 0;
//     })
//     .limit(3)
//     .toList();
~~~

Dòng `println` trong predicate có tác dụng phụ. Khi đổi terminal operation, chế độ parallel hoặc tối ưu, các lần gọi có thể không đúng như giả định. Để đo hiệu năng, sử dụng benchmark/profiler phù hợp; để kiểm tra kết quả, so sánh danh sách đầu ra.

Một predicate thuần như `n -> n % 2 == 0` dễ kiểm thử và có hành vi độc lập hơn. Những hành động ghi log hoặc gọi tài nguyên bên ngoài nên được tổ chức có chủ đích ở ranh giới hệ thống.

## 9. Nguồn có thứ tự, nguồn không có thứ tự và parallelStream

### 9.1. Với List có encounter order

`List.of(...)` có thứ tự gặp; pipeline `filter` giữ thứ tự đó. Do vậy:

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// [2, 4, 6]
~~~

Dù có thể chạy trên nhiều worker thread, **kết quả** phải tuân thủ encounter order của một ordered stream khi thao tác `limit` lấy phần tử đầu và `toList()` materialize theo thứ tự đó. Không đồng nghĩa các callback kiểm tra từng phần tử chạy tuần tự.

Với ordered parallel stream, việc giữ đúng “n phần tử phù hợp đầu tiên” có thể tốn chi phí phối hợp và làm giảm lợi ích song song.

### 9.2. Với nguồn không có encounter order

Không phải Collection nào cũng có thứ tự gặp được bảo đảm; chẳng hạn `HashSet` không hứa thứ tự logic theo giá trị hoặc thứ tự chèn. Trong pipeline không có encounter order, `limit(n)` có thể chọn **bất kỳ n phần tử** phù hợp với yêu cầu về số lượng, không phải “n phần tử đầu” có nghĩa ổn định.

Vì vậy:

~~~java
// Minh họa: không dự đoán chính xác các giá trị được chọn.
Set<Integer> source = new HashSet<>(List.of(1, 2, 3, 4, 5, 6));
List<Integer> selected = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

Đoạn trên cần import `java.util.Set`, `java.util.HashSet` và `java.util.List`. Có thể nói `selected` có không quá hai số chẵn thuộc nguồn, **không** hứa một cặp cụ thể hoặc thứ tự cụ thể cho mọi implementation.

### 9.3. unordered() có phải cách “chữa chậm” không?

`unordered()` thông báo rằng các thao tác sau không cần ràng buộc encounter order. Nó có thể giúp một số pipeline parallel giảm chi phí `limit`/`skip` khi nghiệp vụ **không cần lấy n phần tử đầu theo thứ tự nguồn**.

~~~java
List<Integer> anyTwoEven = numbers.parallelStream()
        .unordered()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

Với nguồn ở ví dụ, chỉ có thể hứa rằng kết quả không quá hai số chẵn đến từ nguồn; không được hứa `[2,4]`. Cách viết `unordered()` **thay đổi hợp đồng về thứ tự**, không phải một tối ưu có thể áp dụng vô điều kiện.

Nếu yêu cầu là “ba đơn mới nhất đã thanh toán”, tuyệt đối không được tùy ý thêm `unordered()`, bởi ý nghĩa của **mới nhất** phụ thuộc thứ tự.

## 10. Ví dụ Java 17 hoàn chỉnh, có stdout chính xác

Tạo file **FilterLimitOrderDemo.java**. Chương trình độc lập so sánh `filter → limit`, `limit → filter`, `skip`, `sorted` và ví dụ đơn hàng.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class FilterLimitOrderDemo {
    record Order(String id, boolean paid) {}

    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 10).boxed().toList();

        List<Integer> filterThenLimit = numbers.stream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .toList();

        List<Integer> limitThenFilter = numbers.stream()
                .limit(3)
                .filter(n -> n % 2 == 0)
                .toList();

        List<Integer> filterSkipLimit = numbers.stream()
                .filter(n -> n % 2 == 0)
                .skip(2)
                .limit(2)
                .toList();

        List<Integer> skipLimitFilter = numbers.stream()
                .skip(2)
                .limit(2)
                .filter(n -> n % 2 == 0)
                .toList();

        List<Integer> filterLimitSkip = numbers.stream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .skip(1)
                .toList();

        System.out.println("filter -> limit: " + filterThenLimit);
        System.out.println("limit -> filter: " + limitThenFilter);
        System.out.println("filter -> skip -> limit: " + filterSkipLimit);
        System.out.println("skip -> limit -> filter: " + skipLimitFilter);
        System.out.println("filter -> limit -> skip: " + filterLimitSkip);

        List<Order> orders = List.of(
                new Order("A", false),
                new Order("B", true),
                new Order("C", false),
                new Order("D", true),
                new Order("E", true)
        );

        List<String> firstTwoPaid = orders.stream()
                .filter(Order::paid)
                .limit(2)
                .map(Order::id)
                .toList();

        List<String> paidAmongFirstTwo = orders.stream()
                .limit(2)
                .filter(Order::paid)
                .map(Order::id)
                .toList();

        System.out.println("first 2 paid: " + firstTwoPaid);
        System.out.println("paid among first 2: " + paidAmongFirstTwo);

        List<Integer> parallelOrdered = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .toList();
        System.out.println("parallel ordered: " + parallelOrdered);

        List<Integer> sortedInput = List.of(7, 2, 6, 3, 8, 4, 5, 1);
        System.out.println("sorted before limit: " + sortedInput.stream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .limit(2)
                .toList());
        System.out.println("limit before sorted: " + sortedInput.stream()
                .filter(n -> n % 2 == 0)
                .limit(2)
                .sorted()
                .toList());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 FilterLimitOrderDemo.java
java FilterLimitOrderDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
filter -> limit: [2, 4, 6]
limit -> filter: [2]
filter -> skip -> limit: [6, 8]
skip -> limit -> filter: [4]
filter -> limit -> skip: [4, 6]
first 2 paid: [B, D]
paid among first 2: [B]
parallel ordered: [2, 4, 6]
sorted before limit: [2, 4]
limit before sorted: [2, 6]
~~~

### 10.1. Phân tích kết quả

- Hai dòng đầu khác nhau vì `filter` trước giới hạn chọn 3 **kết quả khớp**, còn `limit` trước lọc chỉ xét 3 **đầu vào**.
- Ba dòng có `skip` cho thấy mỗi thao tác lấy dữ liệu của pipeline ngay trước nó: `filter → skip → limit` cho một trang trên tập đã lọc; `skip → limit → filter` cho phần tử phù hợp trong một cửa sổ của nguồn; `filter → limit → skip` chọn tập nhỏ trước rồi bỏ phần tử đầu của tập nhỏ đó.
- Hai dòng đơn hàng biểu diễn hai câu hỏi khác nhau: hai đơn đã thanh toán đầu tiên `[B,D]` và các đơn đã thanh toán trong hai đơn đầu `[B]`.
- Dòng `parallel ordered` minh họa rằng với `List` có thứ tự, song song không làm mất hợp đồng kết quả `filter(...).limit(3).toList()`.
- Hai dòng cuối phân biệt top N **theo thứ tự giá trị** với N phần tử phù hợp đầu tiên **theo thứ tự nguồn**, sau đó mới sắp xếp.

Chương trình này dùng các phép chuyển đổi không sửa nguồn và không cần kết quả phụ thuộc vào lịch chạy thread.

## 11. Các tình huống thực tế cần chọn thứ tự đúng

### 11.1. Tìm 10 sản phẩm còn hàng đầu tiên trong bảng đã sắp theo điểm

**Ý định:** giữ bảng sản phẩm có thứ tự điểm ưu tiên rồi chọn 10 sản phẩm đang còn hàng.

~~~java
// Đoạn minh họa với Product có phương thức inStock():
// products.stream()
//         .filter(Product::inStock)
//         .limit(10)
//         .toList();
~~~

Nếu đặt `limit(10)` trước `filter`, có thể nhận ít hơn 10 sản phẩm dù nhiều sản phẩm còn hàng nằm ngoài 10 vị trí đầu. Chỉ làm vậy khi yêu cầu thực sự là “kiểm tra 10 sản phẩm được ưu tiên đầu tiên”.

### 11.2. Phân trang tìm kiếm có bộ lọc

**Ý định:** trang thứ hai của những đơn hợp lệ.

~~~java
// Đoạn minh họa với Order có predicate isValid:
// orders.stream()
//       .filter(this::isValid)
//       .skip(pageSize)
//       .limit(pageSize)
//       .toList();
~~~

Nếu đặt `skip`/`limit` trước `filter`, đó là phân trang của **toàn bộ đơn trước khi lọc**, không phải phân trang kết quả tìm kiếm. Ngoài ra, phải bảo đảm có một thứ tự ổn định; phân trang dữ liệu thay đổi liên tục có thể cần cursor/keyset pagination thay vì offset.

### 11.3. Lấy ba cảnh báo sớm nhất trong luồng sự kiện đã sắp thời gian

**Ý định:** lấy ba sự kiện đầu thỏa điều kiện cảnh báo theo thứ tự thời gian.

~~~java
// Đoạn minh họa với Event có timestamp và severity:
// events.stream()
//       .filter(Event::isAlert)
//       .limit(3)
//       .toList();
~~~

Điều kiện để kết quả thực sự là “sớm nhất” là collection đã có encounter order theo thời gian. Nếu nguồn không có thứ tự, chỉ viết `limit(3)` không tự tạo ý nghĩa thời gian.

### 11.4. Chọn top 5 giá thấp nhất còn bán

**Ý định:** lọc những mặt hàng đủ điều kiện, sắp theo giá rồi chọn 5 sản phẩm rẻ nhất.

~~~java
// Đoạn minh họa với Product có price():
// products.stream()
//         .filter(Product::available)
//         .sorted(Comparator.comparing(Product::price))
//         .limit(5)
//         .toList();
~~~

Đưa `limit(5)` lên trước `sorted` sẽ chỉ sắp và chọn trong 5 phần tử đến trước, bỏ qua những giá tốt xuất hiện sau. Nếu các giá bằng nhau và yêu cầu kết quả ổn định, thêm tiêu chí phụ như ID vào comparator.

## 12. Khi nào hai cách có cùng kết quả?

Hai chuỗi `filter(P).limit(k)` và `limit(k).filter(P)` có thể trùng nhau với một **bộ dữ liệu cụ thể**. Ví dụ:

~~~java
List<Integer> source = List.of(2, 4, 6, 7, 9);
List<Integer> a = source.stream().filter(n -> n % 2 == 0).limit(3).toList();
List<Integer> b = source.stream().limit(3).filter(n -> n % 2 == 0).toList();
// Cả hai đều [2, 4, 6].
~~~

Nhưng nếu đổi nguồn thành `[1,2,3,4,5,6]`, hai cách lại cho kết quả khác. Một phép kiểm thử đúng phải có **ít nhất một giá trị không phù hợp nằm trước các giá trị phù hợp tiếp theo**, để phát hiện lỗi đặt `limit` sai chỗ.

Bài học tổng quát: không được hoán đổi hai thao tác chỉ vì thấy giống nhau về mặt cú pháp. Muốn chuyển đổi pipeline để tối ưu, cần chứng minh tính tương đương theo **mọi dữ liệu và ràng buộc nghiệp vụ** áp dụng.

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đặt `limit` trước `filter` khi cần k kết quả khớp | Có thể thiếu kết quả dù dữ liệu còn nhiều | Đặt `filter` trước `limit` |
| Đặt `skip` trước `filter` khi phân trang kết quả đã lọc | Trang rỗng hoặc số phần tử sai | Lọc trước, rồi `skip`/`limit` |
| Đặt `limit` trước `sorted` khi cần top N theo giá/điểm | Chọn sai tập phần tử cần lấy | Sắp xếp trước khi giới hạn |
| Cho rằng `limit(k)` luôn trả k phần tử | Đọc sai trường hợp ít phần tử phù hợp | Hiểu đúng là tối đa k |
| Cho rằng mọi Collection có thứ tự ổn định | “Đầu tiên” không có nghĩa xác định | Chọn nguồn ordered hoặc `sorted` |
| Thêm `unordered()` khi yêu cầu phần tử đầu | Kết quả thay đổi theo chọn lựa tùy ý | Chỉ bỏ thứ tự nếu nghiệp vụ cho phép |
| Đoán số lần filter được gọi từ số kết quả | Phụ thuộc tối ưu, terminal, parallel | Kiểm thử output; đo riêng khi cần |
| Dùng predicate có side effect | Kết quả/tác dụng phụ khó dự đoán | Dùng phép kiểm tra stateless |
| Dùng `limit(-1)` | Ném `IllegalArgumentException` | Kiểm tra tham số n không âm |
| Chạy lại cùng đối tượng Stream sau `toList()` | Stream đã tiêu thụ | Tạo Stream mới từ Collection |

### 13.1. Sự khác biệt với takeWhile

`takeWhile(predicate)` giữ **tiền tố liên tiếp** của ordered stream còn thỏa predicate và dừng khi gặp phần tử đầu tiên không thỏa. Nó **không giống** `filter(predicate)`, vốn có thể bỏ qua phần tử không thỏa rồi tiếp tục với các phần tử thỏa sau đó.

Ví dụ:

~~~java
List<Integer> values = List.of(2, 4, 5, 6, 8);
List<Integer> filtered = values.stream()
        .filter(n -> n % 2 == 0).toList(); // [2, 4, 6, 8]
List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0).toList(); // [2, 4]
~~~

Đây là đoạn minh họa trong một phương thức, cần import `java.util.List`. Khi kết hợp với `limit`, hãy xác định bạn muốn **lọc mọi phần tử** hay chỉ **lấy một tiền tố liên tục**. Với unordered stream, `takeWhile` có ngữ nghĩa khác về lựa chọn tập con; không suy luận theo tiền tố tuần tự nếu đã loại bỏ encounter order.

## 14. Checklist để đặt đúng thứ tự thao tác

Trước khi viết `filter` và `limit`, tự hỏi:

1. **Tôi muốn k phần tử nào?** “K phần tử đầu tiên đáp ứng điều kiện” hay “trong k phần tử đầu, có phần tử nào đáp ứng điều kiện?”
2. **Nguồn có encounter order đúng nghiệp vụ không?** Nếu không, cần `sorted`/nguồn có thứ tự trước khi giới hạn.
3. **Bộ lọc có phải được áp dụng lên toàn miền dữ liệu hay chỉ trên một cửa sổ đã chọn?** Câu trả lời xác định vị trí `filter`.
4. **Đây có phải phân trang?** Nếu đúng, lọc và xác định thứ tự trước khi tính offset/limit theo contract.
5. **Tôi muốn top N theo tiêu chí xếp hạng?** Phải sắp theo tiêu chí trước khi giới hạn.
6. **Có cần đúng k kết quả không?** Nếu không đủ dữ liệu phù hợp, cần quy định trả ít hơn, thông báo hoặc tìm nguồn khác; `limit` không tự bù.
7. **Đang dùng parallel/unordered stream?** Kiểm tra yêu cầu về “đầu tiên”, thứ tự đầu ra và chi phí phối hợp.
8. **Predicate và nguồn có ổn định, không sửa chung không?** Đảm bảo hành vi có thể dự đoán trước khi bàn tối ưu.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Với `List.of(1,2,3,4,5,6,7,8)`, hai pipeline sau có kết quả gì?

~~~java
// A
values.stream().filter(n -> n % 2 == 0).limit(2).toList();
// B
values.stream().limit(2).filter(n -> n % 2 == 0).toList();
~~~

**Đáp án:** A trả `[2,4]`, B trả `[2]` vì B chỉ xem hai phần tử 1 và 2.

**Câu 2.** Một danh sách theo thời gian mới → cũ chứa 2 đơn chưa thanh toán ở đầu. Muốn lấy 5 đơn đã thanh toán mới nhất, dùng thứ tự nào?

**Đáp án:** `filter(Order::paid).limit(5)`, với điều kiện nguồn có encounter order mới → cũ. Nếu nguồn không có thứ tự, phải sắp xếp trước.

**Câu 3.** Vì sao `filter(...).skip(10).limit(10)` khác `skip(10).limit(10).filter(...)`?

**Đáp án:** cách đầu lấy trang 10 kết quả từ **tập đã lọc**; cách sau lấy một cửa sổ từ toàn nguồn rồi mới lọc, có thể còn rất ít phần tử.

**Câu 4.** Với `[7,2,6,3,8,4,5,1]`, số chẵn nhỏ nhất là 2 và 4. Muốn lấy đúng hai số chẵn nhỏ nhất, đặt `sorted` trước hay sau `limit(2)`?

**Đáp án:** `filter(even).sorted().limit(2)`. Nếu limit trước sorted, chỉ chọn hai số chẵn xuất hiện đầu là 2 và 6.

**Câu 5.** `parallelStream().filter(...).limit(3).toList()` trên `List` có thể bảo toàn ba kết quả đầu tiên thỏa predicate không?

**Đáp án:** Có, với ordered stream, `limit` chọn các phần tử đầu theo encounter order và `toList()` bảo toàn thứ tự. Callback có thể chạy theo thời gian khác nhau.

**Câu 6.** Có nên thêm `unordered()` trước `limit(3)` để tăng tốc khi yêu cầu “ba đơn mới nhất” không?

**Đáp án:** Không; bỏ ràng buộc thứ tự làm mất ý nghĩa “mới nhất”. Chỉ dùng nếu mọi phần tử khớp tương đương nhau đối với yêu cầu.

**Câu 7.** `limit(5)` trên Stream chỉ có hai phần tử sẽ làm gì?

**Đáp án:** trả tối đa hai phần tử sẵn có, không thêm phần tử.

**Câu 8.** Vì sao không nên đếm số lần gọi predicate bằng một biến chia sẻ để khẳng định Stream tối ưu ra sao?

**Đáp án:** pipeline có thể lazy, short-circuit, parallel và được tối ưu; side effect làm phép đo gây nhiễu, đồng thời có thể có vấn đề race. Hãy kiểm tra output và dùng công cụ đo phù hợp.

## 16. Tài liệu đối chiếu

- [Java SE 17 — Stream.filter(Predicate), Stream.limit(long), Stream.skip(long)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Stream API về encounter order, short-circuit và non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Java SE 17 — Collection.stream() và parallelStream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [Java SE 17 — Stream.takeWhile(Predicate)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#takeWhile(java.util.function.Predicate)).

**Kết luận:** **`filter(P).limit(k)` chọn tối đa k phần tử phù hợp đầu tiên**, còn **`limit(k).filter(P)` chỉ xét k phần tử đầu tiên rồi giữ những phần tử phù hợp**. Thứ tự này còn chi phối việc phân trang, chọn top N và hành vi trên nguồn song song/không thứ tự. Hãy quyết định theo câu hỏi nghiệp vụ trước, sau đó mới cân nhắc tối ưu hiệu năng.
