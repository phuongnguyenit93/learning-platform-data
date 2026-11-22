# takeWhile() và dropWhile() trên nguồn Stream có thứ tự trong Java

## 1. Bản chất: xử lý **tiền tố liên tiếp**, không phải lọc toàn bộ

Trong Java Stream API, `takeWhile(Predicate)` và `dropWhile(Predicate)` là hai thao tác trung gian (*intermediate operations*) được bổ sung từ **Java 9**. Chúng đặc biệt hữu ích khi nguồn có **encounter order** (thứ tự phần tử do nguồn và pipeline xác định), ví dụ `List`, `Stream.of(...)` hoặc `IntStream.range(...)`.

Đối với một stream **có thứ tự**, hai phương thức có hành vi chính xác:

- **`takeWhile(predicate)`**: trả về **tiền tố dài nhất gồm các phần tử liên tiếp thỏa predicate**, tính từ **đầu** encounter order. Gặp phần tử đầu tiên **không thỏa**, tiền tố kết thúc. Phần tử đó và các phần tử sau không nằm trong kết quả.
- **`dropWhile(predicate)`**: **loại bỏ tiền tố dài nhất gồm các phần tử liên tiếp thỏa predicate**, rồi giữ **phần còn lại** của encounter order, kể cả các phần tử sau này lại thỏa predicate.

Ví dụ nguồn `[2, 4, 6, 7, 8, 10]` và predicate “là số chẵn”:

```text
Encounter order:       2    4    6   | 7    8    10
Predicate even?:      yes  yes  yes | no  yes   yes
                                     ^
                        ranh giới đầu tiên không thỏa

takeWhile(even):       [2, 4, 6]
dropWhile(even):       [7, 8, 10]
filter(even):          [2, 4, 6, 8, 10]
```

Điều quan trọng là **`takeWhile` không đi tìm mọi phần tử thỏa điều kiện**. Nó lấy **một tiền tố**; `dropWhile` không loại bỏ mọi phần tử thỏa điều kiện mà chỉ bỏ **tiền tố** đó. Nếu bạn chỉ muốn “lấy tất cả số chẵn ở bất kỳ vị trí nào”, hãy dùng `filter()`.

## 2. Encounter order là gì và vì sao cần quan tâm?

**Encounter order** là thứ tự phần tử được nhìn thấy theo ngữ nghĩa của nguồn và các thao tác stream. Khi có encounter order, khái niệm “từ đầu đến phần tử không thỏa đầu tiên” có ý nghĩa rõ ràng.

Một số trường hợp phổ biến:

| Cách tạo nguồn hoặc pipeline | Đặc điểm thứ tự cần nhớ |
| --- | --- |
| `List.of(2, 4, 6).stream()` | Có encounter order theo thứ tự các phần tử của List |
| `Stream.of("a", "b", "c")` | Có encounter order theo thứ tự đối số |
| `IntStream.range(1, 6)` | Có encounter order theo dãy `1, 2, 3, 4, 5` |
| `Stream.iterate(seed, next)` | Có thứ tự theo chuỗi giá trị được tạo |
| `HashSet.stream()` | Không nên trông đợi encounter order có ý nghĩa xác định |
| `source.stream().unordered()` | Bỏ ràng buộc encounter order ở pipeline, dù kết quả quan sát có thể tình cờ cùng thứ tự |

**Có encounter order không có nghĩa dữ liệu đã được sắp xếp tăng dần.** Ví dụ `List.of(2, 4, 6, 7, 8, 10)` có thứ tự ngay cả khi không xét giá trị lớn nhỏ. Stream đi theo thứ tự List, không tự tìm một đoạn “đúng nhất” ở giữa.

Ngược lại, nguồn không có encounter order khiến khái niệm “tiền tố dài nhất” không còn được bảo đảm. Đó là lý do đề bài tập trung vào **nguồn có thứ tự**: hành vi lấy/bỏ tiền tố khi ấy có thể dự đoán bằng mắt và kiểm thử chính xác.

## 3. Chữ ký API và đặc điểm thực thi

Trên `Stream<T>`, hai thao tác có dạng:

```java
Stream<T> takeWhile(Predicate<? super T> predicate);
Stream<T> dropWhile(Predicate<? super T> predicate);
```

Đây là **chữ ký API minh họa**, không phải phương thức cần tự cài đặt. Predicate nhận một phần tử `T` (hoặc kiểu cha tương thích), trả về `boolean`.

Ví dụ đặt trong một phương thức đã import `List`:

```java
List<Integer> data = List.of(2, 4, 6, 7, 8, 10);

List<Integer> prefix = data.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

List<Integer> suffix = data.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();
```

`prefix` là `[2, 4, 6]`, còn `suffix` là `[7, 8, 10]`.

Cả `takeWhile` và `dropWhile` đều là **stateful intermediate operations**: kết quả có thể phụ thuộc vào các phần tử ở vị trí khác, đặc biệt vị trí mà predicate thất bại lần đầu. `takeWhile` là thao tác **short-circuiting**; `dropWhile` là thao tác stateful có thể phải đi qua phần đầu trước khi giữ phần còn lại. Việc gọi thao tác trung gian **chưa nhất thiết duyệt nguồn ngay**; terminal operation như `toList()` hoặc `count()` mới kích hoạt pipeline theo các quy tắc đánh giá Stream.

**Không phải `dropWhile` có nghĩa “chỉ bỏ phần tử đầu tiên không thỏa”.** Nó bỏ **mọi phần tử thỏa liên tiếp từ đầu**, giữ nguyên phần tử không thỏa đầu tiên và tất cả phần còn lại.

## 4. So sánh takeWhile(), dropWhile() và filter()

Cùng nguồn `[2, 4, 6, 7, 8, 10]`, cùng predicate `n -> n % 2 == 0`:

| Phương thức | Câu hỏi | Kết quả |
| --- | --- | --- |
| `takeWhile(even)` | Từ đầu có bao nhiêu số chẵn **liên tiếp**? | `[2, 4, 6]` |
| `dropWhile(even)` | Bỏ đoạn số chẵn **liên tiếp ở đầu**, còn gì? | `[7, 8, 10]` |
| `filter(even)` | Có những số chẵn nào **trong cả nguồn**? | `[2, 4, 6, 8, 10]` |
| `filter(n -> n % 2 != 0)` | Có những số lẻ nào **trong cả nguồn**? | `[7]` |

Sự khác nhau thể hiện rõ khi một phần tử **không thỏa** xuất hiện trước những phần tử **lại thỏa** sau đó. `takeWhile` **không lấy lại** số `8`, `10`; `dropWhile` **vẫn giữ** chúng.

Một ví dụ khác:

```java
List<Integer> mixed = List.of(1, 2, 3, 0, 4);
List<Integer> firstPositive = mixed.stream()
        .takeWhile(n -> n > 0)
        .toList(); // [1, 2, 3]
List<Integer> afterFirstNonPositive = mixed.stream()
        .dropWhile(n -> n > 0)
        .toList(); // [0, 4]
```

`filter(n -> n > 0)` sẽ cho `[1, 2, 3, 4]`, **không giống** `takeWhile`.

Tóm lại: **lọc theo thuộc tính ở mọi vị trí → `filter`**; **chia dữ liệu tại ranh giới đầu tiên không thỏa → `takeWhile` / `dropWhile`**.

## 5. Chương trình Java 17 đầy đủ: hành vi có thể kiểm chứng

Tạo tệp `OrderedTakeDropDemo.java` với nội dung:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class OrderedTakeDropDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 4, 6, 7, 8, 10);
        System.out.println("takeEven=" + numbers.stream().takeWhile(n -> n % 2 == 0).toList());
        System.out.println("dropEven=" + numbers.stream().dropWhile(n -> n % 2 == 0).toList());
        System.out.println("filterEven=" + numbers.stream().filter(n -> n % 2 == 0).toList());
        System.out.println("filterOdd=" + numbers.stream().filter(n -> n % 2 != 0).toList());

        List<Integer> mixed = List.of(1, 2, 3, 0, 4);
        System.out.println("takePositive=" + mixed.stream().takeWhile(n -> n > 0).toList());
        System.out.println("dropPositive=" + mixed.stream().dropWhile(n -> n > 0).toList());
        System.out.println("filterPositive=" + mixed.stream().filter(n -> n > 0).toList());

        System.out.println("sortedTake=" +
                Stream.of(8, 2, 6, 1, 4).sorted().takeWhile(n -> n < 6).toList());
        System.out.println("sortedDrop=" +
                Stream.of(8, 2, 6, 1, 4).sorted().dropWhile(n -> n < 6).toList());

        System.out.println("rangeTake=" +
                IntStream.range(1, 10).takeWhile(n -> n < 5).boxed().toList());
        System.out.println("rangeDrop=" +
                IntStream.range(1, 10).dropWhile(n -> n < 5).boxed().toList());

        System.out.println("iterateTake=" +
                Stream.iterate(1, n -> n + 1).takeWhile(n -> n <= 5).toList());

        System.out.println("parallelTake=" +
                numbers.parallelStream().takeWhile(n -> n % 2 == 0).toList());
        System.out.println("parallelDrop=" +
                numbers.parallelStream().dropWhile(n -> n % 2 == 0).toList());

        System.out.println("noneTake=" + numbers.stream().takeWhile(n -> n < 0).toList());
        System.out.println("noneDrop=" + numbers.stream().dropWhile(n -> n < 0).toList());
        System.out.println("allDrop=" + numbers.stream().dropWhile(n -> n > 0).toList());
        System.out.println("emptyTake=" + Stream.<Integer>empty().takeWhile(n -> n > 0).toList());
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 -encoding UTF-8 OrderedTakeDropDemo.java
java OrderedTakeDropDemo
```

Kết quả chính xác:

```text
takeEven=[2, 4, 6]
dropEven=[7, 8, 10]
filterEven=[2, 4, 6, 8, 10]
filterOdd=[7]
takePositive=[1, 2, 3]
dropPositive=[0, 4]
filterPositive=[1, 2, 3, 4]
sortedTake=[1, 2, 4]
sortedDrop=[6, 8]
rangeTake=[1, 2, 3, 4]
rangeDrop=[5, 6, 7, 8, 9]
iterateTake=[1, 2, 3, 4, 5]
parallelTake=[2, 4, 6]
parallelDrop=[7, 8, 10]
noneTake=[]
noneDrop=[2, 4, 6, 7, 8, 10]
allDrop=[]
emptyTake=[]
```

Giải thích các nhóm kết quả:

1. **Nhóm `takeEven`/`dropEven`/`filterEven`/`filterOdd`:** thấy ngay khác biệt giữa ranh giới tiền tố và điều kiện áp dụng trên toàn bộ nguồn.
2. **Nhóm `takePositive`/`dropPositive`:** số `0` là điểm dừng đầu tiên cho predicate `n > 0`; số `4` ở sau **không được lấy lại** bởi `takeWhile`, cũng **không bị loại** bởi `dropWhile`.
3. **Nhóm `sortedTake`/`sortedDrop`:** `sorted()` đặt lại thứ tự theo giá trị trước khi tìm tiền tố; kết quả khác với việc áp dụng `takeWhile` trực tiếp lên `[8, 2, 6, 1, 4]`.
4. **Nhóm `rangeTake`/`rangeDrop`:** `IntStream.range(1, 10)` là dãy tăng có encounter order; `boxed()` chuyển `IntStream` thành `Stream<Integer>` để thu thành danh sách trong ví dụ.
5. **`iterateTake`:** `Stream.iterate(1, n -> n + 1)` tạo dãy không giới hạn, `takeWhile(n -> n <= 5)` giúp lấy đoạn hữu hạn `[1, 2, 3, 4, 5]`.
6. **`parallelTake`/`parallelDrop`:** `parallelStream()` từ `List` vẫn có encounter order; dù xử lý song song, kết quả phải tuân thủ ranh giới tiền tố theo thứ tự đó.
7. **Các tình huống biên:** predicate sai ngay phần tử đầu cho `takeWhile` trả `[]` và `dropWhile` giữ mọi phần tử. Predicate đúng với mọi phần tử khiến `dropWhile` trả `[]`. Nguồn rỗng luôn cho kết quả rỗng.

Chương trình không dùng `unordered()` để in kết quả làm đáp án, bởi kết quả cụ thể của thao tác `takeWhile` / `dropWhile` trên stream không có thứ tự **không được bảo đảm như tiền tố của danh sách ban đầu**.

## 6. Ranh giới được xác định từ phần tử đầu tiên không thỏa

Giả sử dữ liệu đã được sắp theo thời gian:

```text
[08:00, 08:15, 08:30, 09:10, 08:45]
                 điểm đầu tiên không thỏa điều kiện < 09:00
```

Nếu thực hiện `takeWhile(t -> t.isBefore(09:00))`, chỉ có ba thời điểm đầu. Thời điểm `08:45` ở cuối **không được lấy**, dù nó vẫn nhỏ hơn `09:00`, vì điểm dừng đã xảy ra tại `09:10`.

Điều này quan trọng khi thiết kế thuật toán: muốn “lấy **tất cả** bản ghi trước 09:00” thì chỉ có thể dùng `takeWhile` khi dữ liệu có thứ tự bảo đảm các bản ghi đạt điều kiện tạo **một tiền tố liên tiếp**. Nếu nguồn thời gian lộn xộn, hãy dùng `filter`, hoặc `sorted` trước rồi `takeWhile` nếu quy tắc nghiệp vụ cho phép sắp xếp lại.

Một đặc trưng hay dùng của predicate là tính **đơn điệu theo encounter order**: một khi predicate đã sai, nó không trở lại đúng trong các phần tử phía sau. Khi nguồn được sắp theo khóa liên quan và predicate có tính đó, `takeWhile` rất phù hợp để tách phần đầu.

**Đừng nhầm encounter order với sorted order:** `List` có thứ tự duyệt nhưng không chứng minh điều kiện có tính đơn điệu. Tính đúng đắn nghiệp vụ phải kiểm tra cả hai.

## 7. Kết hợp sorted() và takeWhile()/dropWhile()

Ví dụ:

```java
List<Integer> values = List.of(8, 2, 6, 1, 4);

List<Integer> small = values.stream()
        .sorted()
        .takeWhile(n -> n < 6)
        .toList();

List<Integer> large = values.stream()
        .sorted()
        .dropWhile(n -> n < 6)
        .toList();
```

Đây là các câu lệnh minh họa trong phương thức đã import `java.util.List`; `small` là `[1, 2, 4]`, `large` là `[6, 8]`. Mỗi lời gọi `values.stream()` tạo stream mới vì một pipeline chỉ được tiêu thụ một lần.

`sorted()` làm tăng chi phí tính toán và thường cần đệm dữ liệu; không nên tự động thêm nó chỉ để “cho `takeWhile` đúng”. Trước tiên cần xác định dữ liệu ban đầu đã có thứ tự cần thiết chưa và có được phép đổi thứ tự bản ghi hay không.

Khi so sánh giá trị chuỗi, ngày giờ hoặc đối tượng phức tạp, cần dùng comparator phù hợp. Ví dụ `sorted(Comparator.comparing(Event::timestamp))` chỉ là **cú pháp minh họa** khi có lớp `Event`, phương thức `timestamp` và import `Comparator` tương ứng; không phải một chương trình độc lập để chạy ngay.

Với nhiều trường hợp mà bạn chỉ muốn phần tử theo tiêu chí chứ không yêu cầu tiền tố, `filter` tránh chi phí sắp xếp và phản ánh ý định tốt hơn.

## 8. Nếu nguồn không có thứ tự hoặc gọi unordered() thì sao?

Đây là điểm dễ hiểu sai nhất khi học `takeWhile` và `dropWhile`.

**Trên stream có encounter order:** Java phải tôn trọng **tiền tố dài nhất**. Ví dụ `Stream.of(2,4,6,7,8,10)` chắc chắn được tách tại `7`.

**Trên stream không có encounter order:** tài liệu Java cho phép:

- `takeWhile(predicate)` chọn **một tập con bất kỳ** gồm các phần tử thỏa predicate, **không bắt buộc** là toàn bộ các phần tử thỏa.
- `dropWhile(predicate)` **bỏ một tập con bất kỳ** gồm các phần tử thỏa predicate; những phần tử không thỏa vẫn được giữ, nhưng có thể giữ hoặc bỏ những phần tử thỏa tùy lựa chọn hợp lệ của triển khai.

Do đó, một ví dụ như:

```java
List<Integer> data = List.of(2, 4, 6, 7, 8, 10);
var result = data.stream()
        .unordered()
        .takeWhile(n -> n % 2 == 0)
        .toList();
```

Đây là các câu lệnh minh họa đặt trong phương thức đã import `List`. **Không thể khẳng định** `result` nhất định là `[2, 4, 6]`, hoặc `[2, 4, 6, 8, 10]`, hoặc một tập hợp cụ thể nào chỉ dựa vào đầu vào. Những kết quả quan sát được trên một máy không phải lời hứa của API.

Cũng không nên hiểu `unordered()` là thao tác **xáo trộn ngẫu nhiên**. Nó loại bỏ một ràng buộc về thứ tự, không có hợp đồng rằng các phần tử phải bị đổi chỗ. Trong lần chạy thực tế, bạn có thể vẫn nhìn thấy thứ tự giống như đầu vào; điều đó không phục hồi bảo đảm của stream có thứ tự.

Nguồn như `HashSet` thường không có encounter order xác định, nên `takeWhile`/`dropWhile` **không phù hợp** nếu yêu cầu nghiệp vụ là chia theo vị trí trong một danh sách cụ thể. Khi cần một ranh giới xác định, hãy tạo nguồn có encounter order phù hợp hoặc sắp xếp theo khóa nghiệp vụ trước.

## 9. Stream song song: vẫn đúng kết quả nhưng có thể tốn chi phí

Đối với nguồn **có thứ tự**, ví dụ `List.parallelStream()`, Java vẫn phải tôn trọng tiền tố khi dùng `takeWhile` và `dropWhile`. Song song không có nghĩa được bỏ thứ tự encounter order.

Ví dụ từ chương trình chính:

```java
List<Integer> numbers = List.of(2, 4, 6, 7, 8, 10);
List<Integer> head = numbers.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .toList(); // [2, 4, 6]
List<Integer> tail = numbers.parallelStream()
        .dropWhile(n -> n % 2 == 0)
        .toList(); // [7, 8, 10]
```

Đây là các câu lệnh minh họa trong phương thức đã import `List`. Kết quả được bảo đảm theo encounter order trong ví dụ, dù lịch chạy công việc nội bộ có thể khác nhau.

Điều này cũng giải thích một đánh đổi hiệu năng: trên stream song song nhưng có thứ tự, `takeWhile`/`dropWhile` có thể cần **đồng bộ, đệm hoặc xử lý thêm** để xác định đúng ranh giới tiền tố. Trong một số trường hợp, xử lý tuần tự nhanh hơn.

Javadoc gợi ý rằng nếu dữ liệu **không cần** encounter order và chỉ cần hành vi trên unordered stream, bỏ ràng buộc thứ tự có thể giúp hiệu năng. Nhưng **chỉ làm như vậy khi kết quả không cần ranh giới tiền tố cụ thể**; đừng đánh đổi tính đúng đắn để đổi lấy tốc độ.

Không nên dựa vào việc predicate được gọi theo thứ tự hay đúng một lần trên mỗi phần tử trong parallel stream. Predicate nên **không có side effect**, không phụ thuộc biến mutable chia sẻ, và an toàn trong môi trường song song.

## 10. takeWhile() trên dãy có thể vô hạn

Một ứng dụng tự nhiên của `takeWhile` là tạo đầu ra hữu hạn từ nguồn có thể vô hạn:

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n <= 5)
        .toList();
```

Đoạn minh họa đặt trong phương thức đã import `java.util.List` và `java.util.stream.Stream`; kết quả `[1, 2, 3, 4, 5]`.

`Stream.iterate(1, n -> n + 1)` có thứ tự, sinh dãy `1, 2, 3, ...`. Predicate `n <= 5` đúng với năm phần tử đầu, sau đó sai tại `6`; `takeWhile` có ranh giới để dừng. Đây là lý do `takeWhile` thường phù hợp khi bạn cần **lấy đến trước một ngưỡng**.

Tuy nhiên:

- Nếu predicate **luôn đúng** trên nguồn vô hạn, `takeWhile` không có ranh giới để dừng; `toList()` không thể hoàn tất theo cách thông thường.
- Nếu predicate **luôn đúng** trên nguồn vô hạn, `dropWhile` cũng không thể đi tới phần tử đầu tiên không thỏa để bắt đầu phát dữ liệu kết quả.
- Nếu nguồn vô hạn nhưng predicate sớm trở thành sai, `dropWhile` giữ một **hậu tố vẫn có thể vô hạn**. `toList()` trên hậu tố đó vẫn không phù hợp; cần terminal operation giới hạn hoặc xử lý dòng dữ liệu phù hợp.

Không nên lập luận rằng `takeWhile` “luôn nhanh” hoặc “luôn dừng” chỉ vì tên của nó mang ý nghĩa chọn một đoạn đầu.

## 11. Giá trị ở ranh giới: bao gồm hay không bao gồm?

Với nguồn có thứ tự `[1, 2, 3, 4, 5]` và điều kiện `n < 4`:

```text
takeWhile(n < 4) -> [1, 2, 3]
dropWhile(n < 4) -> [4, 5]
```

Phần tử đầu tiên **không thỏa** (`4`) bị **loại khỏi `takeWhile`** và **được giữ trong `dropWhile`**.

Điều này có ích khi xử lý log, sự kiện hoặc lịch sử giao dịch:

- `takeWhile(event -> event.isBefore(cutoff))`: lấy phần liên tiếp từ đầu **trước** ranh giới (nếu nguồn được sắp theo thời gian tăng dần).
- `dropWhile(event -> event.isBefore(cutoff))`: bỏ phần ấy và giữ từ ranh giới trở đi.

Nếu muốn kết quả **bao gồm** chính phần tử ranh giới vào đoạn đầu, `takeWhile` không có tùy chọn `inclusive` mặc định. Bạn cần thay đổi predicate nếu nghiệp vụ cho phép, hoặc thiết kế thao tác chia phân đoạn có trạng thái riêng. Ví dụ với dãy số đã sắp tăng, dùng `n -> n <= 4` sẽ lấy cả `4`, nhưng cách này chỉ đúng khi tiêu chí ranh giới là một so sánh cho phép điều chỉnh.

Không nên viết predicate **có trạng thái mutable** chỉ để đánh dấu “đã gặp phần tử thất bại” trong stream song song, vì không an toàn và làm mất tính dễ hiểu của code.

## 12. takeWhile/dropWhile có phải là hai nửa bổ sung nhau?

Với **cùng một dãy có encounter order**, cùng một predicate thuần, ta có thể xem `takeWhile` và `dropWhile` là hai phần tại **cùng vị trí ranh giới**:

```text
original = prefix + suffix
prefix = takeWhile(predicate)
suffix = dropWhile(predicate)
```

Đẳng thức này diễn đạt **nội dung theo encounter order** của hai kết quả, không có nghĩa bạn được phép **gọi hai terminal operations trên cùng đối tượng Stream**.

Sai:

```text
Stream<Integer> once = Stream.of(1, 2, 3, 4);
var prefix = once.takeWhile(n -> n < 3).toList();
var suffix = once.dropWhile(n -> n < 3).toList(); // Sai: reuse
```

Đây là **phản ví dụ cố ý sai về vòng đời Stream**, có thể biên dịch nhưng vi phạm hợp đồng Stream. Sửa bằng cách **tạo hai stream độc lập từ cùng nguồn**:

```java
List<Integer> data = List.of(1, 2, 3, 4);
List<Integer> prefix = data.stream()
        .takeWhile(n -> n < 3).toList();
List<Integer> suffix = data.stream()
        .dropWhile(n -> n < 3).toList();
```

Các lệnh này đặt trong phương thức có import `List`. Kết quả `prefix = [1, 2]`, `suffix = [3, 4]`, và ghép theo thứ tự thì thu lại dãy nguồn.

Với nguồn lớn, đắt đỏ hoặc chỉ đọc một lần (file, network cursor), muốn tách mà không phải đọc lại có thể cần thuật toán khác hoặc **materialize** kết quả một cách có chủ đích. Không nên giả định stream đã sử dụng có thể reset.

## 13. Các tình huống biên cần nắm

Với nguồn có thứ tự `[2, 4, 6, 7]`:

| Tình huống | `takeWhile` | `dropWhile` |
| --- | --- | --- |
| Predicate sai ngay phần tử đầu (`n < 0`) | `[]` | `[2, 4, 6, 7]` |
| Predicate đúng với tất cả (`n > 0`) | `[2, 4, 6, 7]` | `[]` |
| Sai tại phần tử thứ tư (`n % 2 == 0`) | `[2, 4, 6]` | `[7]` |
| Nguồn rỗng | `[]` | `[]` |

Hai thao tác không tự trả `null` khi không có phần tử; khi thu bằng `toList()`, kết quả có thể là một danh sách rỗng.

**Không đặt logic bắt buộc vào predicate với side effect.** Khi tối ưu pipeline, việc đánh giá predicate có thể không khớp trực giác “mỗi phần tử gọi đúng một lần theo thứ tự”, nhất là khi xử lý song song. Hãy dùng predicate **stateless** và **non-interfering** (không thay đổi nguồn dữ liệu đang được duyệt).

Nếu predicate ném unchecked exception, pipeline có thể dừng bằng ngoại lệ thay vì trả danh sách. `takeWhile` và `dropWhile` không tự bắt lỗi, chuyển đổi thành giá trị mặc định hay bỏ qua phần tử lỗi.

## 14. Hiệu năng và lựa chọn API đúng mục tiêu

Một nguyên tắc thiết kế là mô tả chính xác **ý định dữ liệu** trước khi tối ưu:

- **Lấy phần đầu liên tiếp thỏa điều kiện theo encounter order:** `takeWhile`.
- **Bỏ phần đầu liên tiếp thỏa điều kiện rồi xử lý đoạn còn lại:** `dropWhile`.
- **Lọc tất cả phần tử thỏa điều kiện ở mọi vị trí:** `filter`.
- **Lấy N phần tử đầu bất kể giá trị:** `limit(N)`.
- **Bỏ N phần tử đầu bất kể giá trị:** `skip(N)`.
- **Muốn ranh giới theo giá trị nhưng nguồn chưa được sắp phù hợp:** cân nhắc `sorted(...)` trước, hoặc dùng `filter` tùy yêu cầu.

`takeWhile` có thể tiết kiệm việc duyệt cả nguồn tuần tự nếu predicate sớm sai; nhưng chi phí thực tế còn phụ thuộc nguồn, pipeline, terminal operation, cách thực thi và việc stream có thứ tự hay song song. `dropWhile` phải tìm ranh giới đầu trước khi giữ phần còn lại, nên không mặc định rẻ hơn `filter`.

Đặc biệt, `sorted()` trước `takeWhile` có chi phí và có thể làm thay đổi ngữ nghĩa khi người dùng quan tâm **thứ tự ban đầu** của log, giao dịch hoặc sự kiện. Chỉ áp dụng khi thứ tự sắp xếp đúng với mục tiêu.

Nếu không cần bảo đảm về tiền tố, bạn có thể dùng một thao tác khác đơn giản hơn và ít bị ràng buộc thứ tự hơn; không nên dùng `unordered()` như một mẹo tối ưu mặc định.

## 15. Các lỗi thường gặp

| Hiểu sai hoặc lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `takeWhile` giống `filter` | `takeWhile` ngừng lấy khi tiền tố gặp phần tử sai đầu tiên | Dùng `filter` nếu muốn mọi phần tử thỏa |
| `dropWhile` giống `filter(predicate.negate())` | `dropWhile` giữ cả phần tử thỏa nằm sau ranh giới | Dùng `filter` nếu muốn loại mọi phần tử thỏa |
| Stream từ `List` luôn được sắp theo giá trị | Encounter order khác sorted order | Dùng `sorted` khi nghiệp vụ yêu cầu sắp xếp |
| `takeWhile` luôn lấy đủ phần tử thỏa trên unordered stream | Không có bảo đảm tiền tố ở stream không thứ tự | Giữ encounter order hoặc đổi sang `filter` |
| Gọi `unordered()` để “xáo trộn” dữ liệu | `unordered()` chỉ bỏ ràng buộc order, không phải shuffle | Dùng thuật toán xáo trộn riêng nếu thật sự cần |
| Predicate luôn được gọi đúng một lần/phần tử theo thứ tự | Pipeline có thể short-circuit, tối ưu hoặc chạy song song | Dùng predicate không có side effect |
| `takeWhile` tự bao gồm phần tử đầu không thỏa | Chính phần tử này là điểm kết thúc tiền tố | Dùng tiêu chí khác nếu cần inclusive boundary |
| `dropWhile` bỏ cả những phần tử thỏa xuất hiện sau ranh giới | Nó chỉ bỏ tiền tố, không lọc toàn bộ stream | Dùng `filter` nếu cần lọc ở mọi vị trí |
| Cùng `Stream` chạy cả `takeWhile(...).toList()` và `dropWhile(...).toList()` | Stream dùng một lần | Tạo hai stream từ nguồn hoặc thiết kế một lần duyệt |
| Nguồn vô hạn + predicate luôn đúng vẫn có thể `toList()` nhanh | Không có ranh giới hữu hạn | Chọn predicate có điểm dừng hoặc giới hạn dữ liệu |
| Chuyển stream song song sang unordered nhưng vẫn kỳ vọng prefix cố định | Bỏ encounter order làm mất ràng buộc tiền tố | Giữ ordered khi kết quả phụ thuộc thứ tự |
| Thêm `sorted` vô điều kiện để “sửa” takeWhile | Đổi ngữ nghĩa nguồn và tốn chi phí | Kiểm tra lại ý nghĩa dữ liệu và điều kiện trước |

## 16. Tự kiểm tra và đáp án

**Bài 1 — Ranh giới.** Với nguồn `[1, 3, 5, 2, 7]` và predicate `n -> n % 2 == 1`, hãy cho kết quả của `takeWhile`, `dropWhile` và `filter`.

Đáp án: `takeWhile` → `[1, 3, 5]`; `dropWhile` → `[2, 7]`; `filter` → `[1, 3, 5, 7]`.

**Bài 2 — Điểm đầu tiên không thỏa.** Với `List.of(2, 4, 6, 7, 8, 10)`, tại sao `dropWhile(n -> n % 2 == 0)` vẫn giữ `8` và `10`?

Đáp án: vì `7` đã kết thúc **tiền tố số chẵn liên tiếp**; `dropWhile` giữ nguyên toàn bộ hậu tố bắt đầu từ `7`, bất kể có phần tử chẵn trong hậu tố.

**Bài 3 — Sắp xếp.** Với nguồn `[8, 2, 6, 1, 4]`, kết quả của `stream().sorted().takeWhile(n -> n < 6)` là gì?

Đáp án: `sorted()` tạo thứ tự `[1, 2, 4, 6, 8]`; tiền tố thỏa `n < 6` là `[1, 2, 4]`.

**Bài 4 — Short circuit.** Với `IntStream.range(1, 10).takeWhile(n -> n < 5).boxed().toList()`, kết quả là gì? Phần tử `5` có xuất hiện không?

Đáp án: `[1, 2, 3, 4]`. `5` là phần tử đầu tiên **không** thỏa, nên bị loại khỏi kết quả.

**Bài 5 — Unordered.** Có thể khẳng định `Stream.of(1, 2, 3, 4).unordered().takeWhile(n -> n < 3)` luôn cho `[1, 2]` không?

Đáp án: **Không**. Bỏ encounter order khiến API không còn bảo đảm lấy tiền tố theo thứ tự ban đầu; kết quả có thể là một tập con hợp lệ của các phần tử thỏa điều kiện.

**Bài 6 — Chọn API.** Muốn lấy **tất cả** phần tử có `score >= 80` trong danh sách chưa sắp xếp, nên dùng thao tác nào?

Đáp án: `filter(score -> score >= 80)`, vì yêu cầu không giới hạn vào một tiền tố. `takeWhile` có thể bỏ lỡ phần tử hợp lệ xuất hiện phía sau một phần tử `score < 80`.

**Bài 7 — Hai phần của cùng nguồn.** Một stream đã được dùng để `takeWhile(...).toList()`. Có thể gọi tiếp `dropWhile` trên **cùng đối tượng stream** không?

Đáp án: **Không**. Mỗi stream được tiêu thụ một lần. Hãy gọi `list.stream()` hai lần hoặc dùng thuật toán chia dữ liệu một lần tùy yêu cầu.

## 17. Ghi nhớ

1. Với nguồn **có encounter order**, `takeWhile(P)` lấy **tiền tố liên tiếp dài nhất** thỏa `P`.
2. `dropWhile(P)` **bỏ chính tiền tố ấy**, rồi giữ toàn bộ hậu tố từ phần tử đầu tiên không thỏa trở đi.
3. `filter(P)` khác biệt vì xét **mọi phần tử** trong nguồn, không chỉ tiền tố.
4. **Encounter order không đồng nghĩa sorted order**; nếu nghiệp vụ cần một ngưỡng theo giá trị, phải bảo đảm thứ tự đầu vào phù hợp.
5. Trên unordered stream, không được suy ra tiền tố xác định; `unordered()` cũng không phải shuffle.
6. Trên ordered parallel stream, kết quả vẫn phải tuân thủ ranh giới tiền tố nhưng có thể tốn chi phí hơn.
7. `takeWhile` có thể dừng một dãy vô hạn khi predicate trở nên sai; không tự bảo đảm mọi pipeline trên nguồn vô hạn kết thúc.
8. Muốn lấy cả prefix và suffix để xử lý độc lập, hãy **tạo stream mới cho mỗi pipeline**, không dùng lại cùng một `Stream`.

Tài liệu chính thức: [Java SE 17 Stream.takeWhile/dropWhile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#takeWhile(java.util.function.Predicate)), [Stream.dropWhile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#dropWhile(java.util.function.Predicate)), [IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).