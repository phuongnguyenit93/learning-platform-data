# Phân biệt phép toán không trạng thái và có trạng thái

> **Chương:** Hợp đồng và vòng đời pipeline  
> **Module:** `JAVA_STREAM_API` — học cách xử lý dữ liệu theo lối khai báo qua pipeline lazy, `filter`, `map`, `reduce`, `collect` và các kỹ thuật nâng cao.

Khi đọc một pipeline Stream, ta thường chú ý đến **dữ liệu được biến đổi thành gì**. Tuy nhiên, để dự đoán pipeline sẽ xử lý bao nhiêu phần tử, cần bao nhiêu bộ nhớ và có thể dừng sớm hay không, phải biết một phép toán trung gian (*intermediate operation*) là **không trạng thái** (*stateless*) hay **có trạng thái** (*stateful*).

Phân biệt này là nền tảng để viết pipeline dễ hiểu, tránh xử lý dư thừa, sử dụng Stream song song hợp lý và học tiếp `reduce`, `collect`, `groupingBy`, collector tùy chỉnh, `Spliterator` hoặc Stream Gatherers.

## 1. Bối cảnh: pipeline và phép toán trung gian

Một pipeline Stream thường gồm ba phần:

```text
Nguồn dữ liệu  →  phép toán trung gian  →  phép toán kết thúc
List / Set        filter / map / sorted     toList / collect / count
                  distinct / limit / ...   reduce / findFirst / ...
```

Ví dụ:

```java
List<Integer> result = List.of(5, 1, 5, 2, 3).stream()
        .filter(n -> n > 1)   // trung gian
        .map(n -> n * 2)      // trung gian
        .distinct()           // trung gian
        .toList();            // kết thúc; Java 16+

// result = [10, 4, 6]
```

Phép toán trung gian tạo ra một Stream mới mô tả bước xử lý tiếp theo. **Các bước này thường lazy**: việc khai báo `filter`, `map` hay `sorted` chưa tự chạy qua toàn bộ nguồn. Việc duyệt nguồn bắt đầu khi có phép toán kết thúc, trừ khi Stream implementation có thể tối ưu và bỏ qua một số bước không ảnh hưởng kết quả.

Hai khái niệm cần tách bạch:

- **Không trạng thái/có trạng thái** nói về mức độ một bước xử lý cần biết hoặc lưu thông tin từ các phần tử khác.
- **Lazy/eager** nói về thời điểm công việc được thực hiện. Cả `map()` lẫn `sorted()` đều là phép toán trung gian lazy; nhưng khi pipeline chạy, chúng có cách xử lý rất khác nhau.

## 2. Định nghĩa và dấu hiệu nhận biết

### Phép toán trung gian không trạng thái (*stateless*)

Một phép toán **không trạng thái** có thể quyết định cách xử lý mỗi phần tử mà không phải ghi nhớ các phần tử đã gặp hoặc chờ xem toàn bộ dữ liệu. Kết quả ứng với phần tử hiện tại chỉ phụ thuộc vào phần tử đó và các tham số bất biến của phép toán.

Ví dụ:

```java
numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n);
```

`filter` kiểm tra từng số có chẵn không; `map` bình phương từng số. Với đầu vào là `8`, không bước nào cần hỏi trước đó đã gặp những số nào. Stream thường có thể kết hợp các bước để mỗi phần tử lần lượt đi qua `filter` rồi `map`, thay vì tạo một danh sách trung gian cho từng bước.

### Phép toán trung gian có trạng thái (*stateful*)

Một phép toán **có trạng thái** cần theo dõi thông tin về những phần tử đã xử lý, vị trí trong luồng, hoặc thậm chí tập hợp các phần tử trước khi quyết định đầu ra.

Ví dụ:

```java
numbers.stream()
        .distinct()
        .sorted()
        .limit(3);
```

- `distinct()` cần nhận biết giá trị đã xuất hiện để bỏ trùng.
- `sorted()` cần xét thứ tự của các giá trị; với nguồn chưa sắp xếp, việc xuất phần tử nhỏ nhất nói chung đòi hỏi xem các phần tử còn lại.
- `limit(3)` cần theo dõi số phần tử đã được chuyển tiếp để dừng khi đủ ba phần tử.

**Có trạng thái không đồng nghĩa với lưu toàn bộ dữ liệu.** `limit(3)` chỉ cần theo dõi tiến độ trong trường hợp tuần tự thông thường, còn `sorted()` thường phải giữ nhiều phần tử để sắp xếp.

## 3. Bảng phân loại những phép toán phổ biến

| Phép toán trung gian | Loại | Cần nhớ điều gì? | Lưu ý |
| --- | --- | --- | --- |
| `filter(predicate)` | Không trạng thái | Không cần nhớ các phần tử khác | Giữ hoặc bỏ phần tử hiện tại. |
| `map(mapper)`, `mapToInt(...)` | Không trạng thái | Không cần nhớ các phần tử khác | Chuyển đổi từng phần tử. |
| `flatMap(mapper)`, `mapMulti(...)` | Không trạng thái | Không cần nhớ các phần tử *nguồn* khác | Một đầu vào có thể tạo không, một hoặc nhiều đầu ra. |
| `peek(action)` | Không trạng thái | Không cần trạng thái để quyết định dòng dữ liệu | Chủ yếu dùng quan sát/debug; không nên dựa vào side effect của `peek`. |
| `distinct()` | Có trạng thái | Những giá trị đã gặp hoặc cấu trúc tương đương | Có thể tiêu tốn bộ nhớ theo số giá trị khác nhau. |
| `sorted()`, `sorted(comparator)` | Có trạng thái | Thông tin để xác định thứ tự tổng thể | Thường là bước cần đệm dữ liệu. |
| `limit(n)` | Có trạng thái | Đã chuyển tiếp bao nhiêu phần tử | Có khả năng *short-circuit*: dừng sớm khi đủ đầu ra. |
| `skip(n)` | Có trạng thái | Đã bỏ qua bao nhiêu phần tử | Đặc biệt cần chú ý trên luồng song song có thứ tự. |
| `takeWhile(predicate)` | Có trạng thái | Đang ở trong đoạn đầu liên tiếp thỏa điều kiện hay không | Java 9+; trên luồng có thứ tự, dừng ở phần tử đầu tiên không thỏa. |
| `dropWhile(predicate)` | Có trạng thái | Đã đi qua đoạn đầu liên tiếp thỏa điều kiện hay chưa | Java 9+; sau điểm chuyển trạng thái, giữ mọi phần tử còn lại. |

Ở đây, “không trạng thái” mô tả **hợp đồng của phép toán Stream với các hàm được viết đúng cách**. Nó không có nghĩa là mọi lambda truyền vào `map`/`filter` đều an toàn nếu tự ý đọc và sửa biến dùng chung; vấn đề đó được phân tích ở mục 8.

## 4. Ví dụ thực thi: thay đổi thứ tự là thay đổi kết quả

Chạy chương trình Java 17+ sau để quan sát hai nhóm phép toán trong cùng một nguồn:

```java
import java.util.List;

public class StreamStateDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(5, 1, 5, 2, 3);

        // map và filter: quyết định độc lập trên từng phần tử.
        System.out.println(numbers.stream()
                .map(n -> n * 2)
                .filter(n -> n > 2)
                .toList());

        // distinct cần nhớ số đã gặp; limit cần đếm số đã lấy.
        System.out.println(numbers.stream()
                .distinct()
                .limit(3)
                .toList());

        // Lấy ba phần tử trước, sau đó mới khử trùng.
        System.out.println(numbers.stream()
                .limit(3)
                .distinct()
                .toList());

        // Sắp xếp toàn bộ nguồn, sau đó lấy ba số nhỏ nhất.
        System.out.println(numbers.stream()
                .sorted()
                .limit(3)
                .toList());

        // Chỉ sắp xếp ba phần tử đầu của nguồn.
        System.out.println(numbers.stream()
                .limit(3)
                .sorted()
                .toList());
    }
}
```

Kết quả:

```text
[10, 10, 4, 6]
[5, 1, 2]
[5, 1]
[1, 2, 3]
[1, 5, 5]
```

Từ ví dụ có thể rút ra các điều kiện quan trọng:

1. `distinct().limit(3)` tìm **ba giá trị khác nhau đầu tiên** theo encounter order của nguồn có thứ tự. Nếu có trùng lặp, nó có thể phải đọc hơn ba phần tử để lấy đủ ba giá trị.
2. `limit(3).distinct()` chỉ nhìn **ba phần tử đầu tiên**, vì vậy có thể trả về ít hơn ba giá trị.
3. `sorted().limit(3)` lấy **ba giá trị nhỏ nhất** trên một nguồn hữu hạn chưa sắp xếp; muốn biết chúng là gì thường phải xem toàn bộ nguồn.
4. `limit(3).sorted()` chỉ sắp xếp **ba phần tử được lấy trước**, nên không bảo đảm đó là ba giá trị nhỏ nhất của nguồn.

Vì thế, không được tùy tiện hoán đổi các phép toán có trạng thái chỉ để làm pipeline trông gọn hơn.

## 5. `filter` khác gì `takeWhile` và `dropWhile`?

Ba phép toán đều nhận `Predicate<T>`, nhưng ý nghĩa rất khác:

```java
List<Integer> values = List.of(2, 4, 1, 6, 8);

List<Integer> a = values.stream()
        .filter(n -> n % 2 == 0)
        .toList();
// [2, 4, 6, 8]

List<Integer> b = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();
// [2, 4]

List<Integer> c = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();
// [1, 6, 8]
```

- `filter`: với **mỗi phần tử**, kiểm tra điều kiện riêng và giữ các phần tử thỏa, dù chúng nằm ở vị trí nào.
- `takeWhile`: trên Stream có thứ tự, chỉ giữ **đoạn đầu liên tiếp** thỏa điều kiện; khi gặp `1`, đoạn này kết thúc.
- `dropWhile`: trên Stream có thứ tự, bỏ **đoạn đầu liên tiếp** thỏa điều kiện; từ `1` trở đi giữ cả `1`, `6` và `8`, dù một số sau đó vẫn là số chẵn.

Để hiểu hai phép toán `*While`, phải biết các phần tử **đã đi qua điểm ranh giới hay chưa**. Đây là trạng thái của quá trình duyệt, khác với phép kiểm tra độc lập của `filter`.

## 6. Lazy, cơ chế xử lý từng phần tử và dừng sớm

Xét một pipeline tuần tự với nguồn có thứ tự:

```java
List<Integer> firstTwo = List.of(5, 1, 4, 2, 3).stream()
        .filter(n -> n > 1)
        .map(n -> n * 10)
        .limit(2)
        .toList();

// [50, 40]
```

Về mặt logic, các bước `filter` và `map` có thể xử lý lần lượt: `5` đi qua và tạo `50`; `1` bị loại; `4` tạo `40`; `limit(2)` đã có đủ hai kết quả nên pipeline có thể dừng mà không cần xử lý tiếp `2`, `3`. Kiểu phối hợp này thường được gọi là **fusion**: nhiều phép toán trung gian được thực hiện trong cùng lượt duyệt.

Nếu chèn `sorted()` trước `limit(2)`:

```java
List<Integer> smallest = List.of(5, 1, 4, 2, 3).stream()
        .sorted()
        .limit(2)
        .toList();

// [1, 2]
```

Trong trường hợp tổng quát, `sorted()` phải xét mọi phần tử trước khi biết hai phần tử đầu tiên theo thứ tự tăng dần. **`limit(2)` vẫn là phép toán short-circuit nhưng không thể buộc `sorted()` phía trước bỏ qua phần còn lại của nguồn.**

Điều này đặc biệt quan trọng với nguồn vô hạn:

```java
// Có thể kết thúc: chỉ cần đủ ba phần tử.
List<Integer> ok = java.util.stream.Stream.generate(() -> 7)
        .limit(3)
        .toList();

// Không thể kết thúc trên nguồn vô hạn như thế này:
// java.util.stream.Stream.generate(() -> 7)
//         .sorted()
//         .limit(3)
//         .toList();
```

Một lời gọi terminal như `count()` hoặc `findFirst()` cũng có thể kích hoạt tối ưu khác nhau, tùy đặc tính nguồn (`SIZED`, `SORTED`, `DISTINCT`, ...) và implementation. Vì vậy, **đừng dùng số lần `peek()` được gọi làm bằng chứng cố định về lượng công việc** của mọi pipeline: `peek` có thể không chạy cho những phần tử bị tối ưu bỏ qua.

## 7. Trạng thái, bộ nhớ và xử lý song song

Không có một mức chi phí chung cho mọi phép toán stateful:

| Nhóm | Trạng thái điển hình trong xử lý tuần tự | Ảnh hưởng thực tế |
| --- | --- | --- |
| `filter`, `map` | Không cần nhớ các phần tử khác | Thường xử lý theo từng phần tử, chi phí bộ nhớ phụ nhỏ. |
| `distinct` | Tập giá trị đã thấy; thường tỉ lệ với số giá trị khác nhau | Có thể làm tăng dùng bộ nhớ khi nguồn lớn hoặc có nhiều giá trị phân biệt. |
| `sorted` | Vùng đệm để sắp xếp các phần tử | Thường tốn bộ nhớ theo số phần tử và chi phí sắp xếp; nên thận trọng với nguồn rất lớn. |
| `limit`, `skip` | Bộ đếm hoặc thông tin vị trí | Trong xử lý tuần tự có thể rất gọn; với parallel stream có thứ tự, việc phối hợp nhánh có thể tốn chi phí. |
| `takeWhile`, `dropWhile` | Trạng thái trước/sau ranh giới của đoạn đầu | Cần tôn trọng ranh giới theo thứ tự, khiến xử lý song song có thứ tự khó mở rộng hơn. |

Các mức trên là **mô hình tư duy**, không phải cam kết về cấu trúc dữ liệu hay độ phức tạp tuyệt đối: Java có thể sử dụng tối ưu dựa trên `Spliterator`, đặc tính của nguồn và loại Stream. Ví dụ, một nguồn vốn đã báo `SORTED` có thể giúp triển khai tránh công việc sắp xếp không cần thiết.

Với Stream song song, cần chú ý **encounter order** (thứ tự gặp phần tử) của nguồn:

- Trên nguồn có thứ tự như `List`, `limit(10)`, `skip(10)`, `takeWhile(...)`, `dropWhile(...)` phải giữ đúng ngữ nghĩa liên quan đến thứ tự; việc phối hợp giữa các nhánh song song có thể tốn kém.
- Nếu thứ tự **không quan trọng về nghiệp vụ**, có thể cân nhắc `.unordered()` trước một số phép toán stateful để cho phép triển khai linh hoạt hơn. `.unordered()` không có nghĩa là tráo ngẫu nhiên dữ liệu; nó chỉ gỡ yêu cầu giữ thứ tự gặp phần tử.
- Khi đã bỏ yêu cầu thứ tự, `limit(n)` không còn cam kết lấy **n phần tử đầu tiên của danh sách gốc**; `takeWhile`/`dropWhile` cũng không còn ngữ nghĩa đoạn tiền tố như trên nguồn có thứ tự. Chỉ dùng khi ứng dụng chấp nhận kết quả đó.
- `parallel()` không đảm bảo nhanh hơn: overhead phân chia, gộp kết quả và quản lý trạng thái có thể lớn hơn phần công việc được song song hóa.

Ví dụ chỉ dùng `unordered()` khi mục tiêu là **lấy bất kỳ 100 phần tử nào**:

```java
List<Integer> sample = hugeList.parallelStream()
        .unordered()
        .limit(100)
        .toList();

// Không bảo đảm đây là 100 phần tử đầu tiên của hugeList.
```

Nếu ứng dụng cần trang dữ liệu ổn định, top-N chính xác hoặc kết quả tái lập theo thứ tự, hãy giữ encounter order và ưu tiên thiết kế thuật toán rõ ràng trước khi cân nhắc song song.

## 8. Đừng nhầm trạng thái của phép toán với trạng thái do lambda tự tạo

`filter()` là một **phép toán không trạng thái**, nhưng ta vẫn có thể viết một lambda **có trạng thái và không phù hợp với hợp đồng Stream**:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

List<String> unreliable = names.parallelStream()
        .filter(name -> counter.incrementAndGet() % 2 == 0)
        .toList();
```

Ví dụ này cố chọn “mỗi phần tử thứ hai” bằng một bộ đếm dùng chung. Dù `AtomicInteger` tránh mất cập nhật, thứ tự các lambda chạy trong `parallelStream()` không nhất thiết trùng thứ tự của `names`, nên **những tên được chọn có thể thay đổi giữa các lần chạy**. Dùng biến `int` có thể thay đổi từ nhiều luồng còn gây tranh chấp dữ liệu.

Nếu yêu cầu thật sự là chọn phần tử ở chỉ số chẵn của một `List` hỗ trợ truy cập theo chỉ số hiệu quả, hãy diễn đạt quy tắc bằng chỉ số:

```java
import java.util.stream.IntStream;

List<String> evenIndexNames = IntStream.range(0, names.size())
        .filter(i -> i % 2 == 0)
        .mapToObj(names::get)
        .toList();
```

Điều kiện `i % 2 == 0` độc lập cho mỗi chỉ số nên rõ nghĩa và ổn định. Với danh sách liên kết không truy cập ngẫu nhiên hiệu quả, hãy cân nhắc cách duyệt khác để tránh chi phí `get(i)` lớn.

Các hàm truyền vào `map`, `filter`, `sorted(comparator)` và các phép toán khác thường cần **không can thiệp vào nguồn** (*non-interfering*), đồng thời tránh phụ thuộc trạng thái biến đổi từ bên ngoài. Đừng thay đổi collection nguồn trong lúc pipeline đang chạy; đừng dùng `peek` hoặc side effect của lambda làm cơ chế tích lũy dữ liệu. Khi cần tổng hợp, hãy sử dụng terminal operation thích hợp như `reduce()` hoặc `collect()`.

**Lưu ý:** `reduce()` và `collect()` có thể tích lũy trạng thái, nhưng chúng là **phép toán kết thúc**, không thuộc bảng phân loại *phép toán trung gian* ở trên. Ví dụ `collect(groupingBy(...))` xây dựng các nhóm có trạng thái trong quá trình thu thập; đó là một khía cạnh khác so với `distinct()` hoặc `sorted()`.

## 9. Cách quyết định khi xây dựng pipeline

Khi chọn và sắp xếp phép toán, hãy tự trả lời các câu hỏi sau:

1. **Mỗi đầu ra có phụ thuộc phần tử khác không?** Nếu không, ưu tiên diễn đạt bằng `filter`, `map`, `flatMap` hoặc `mapMulti`. Nếu có, xác định rõ cần nhớ giá trị đã gặp, vị trí, ranh giới hay thứ tự toàn cục.
2. **Có cần đúng thứ tự gặp phần tử không?** `distinct().limit(n)` và `limit(n).distinct()` khác nhau; `takeWhile` và `filter` cũng khác nhau. Đừng đổi thứ tự bước mà chưa chứng minh kết quả tương đương.
3. **Có thể dừng sớm không?** Đặt các điều kiện loại bỏ phần tử phù hợp trước bước tốn nhiều tài nguyên nếu ngữ nghĩa cho phép. `sorted().limit(n)` thường vẫn phải xử lý cả nguồn, trong khi `filter().limit(n)` tuần tự có thể dừng khi đủ kết quả.
4. **Nguồn lớn, vô hạn hay chạy song song?** Cẩn trọng với `sorted`, `distinct` và các phép toán giữ ranh giới theo thứ tự. Ưu tiên đo với dữ liệu đại diện nếu hiệu năng là yêu cầu quan trọng.
5. **Lambda có đọc/ghi trạng thái dùng chung không?** Nếu có, tìm cách diễn đạt thuần hàm hoặc dùng collector/reduction theo đúng hợp đồng thay vì trộn side effect vào pipeline.

## 10. Tự kiểm tra

**Câu 1.** Vì sao `limit(5)` là stateful dù không cần lưu năm phần tử?  
**Trả lời:** Vì nó phải nhớ đã chuyển tiếp bao nhiêu phần tử để biết khi nào dừng. *Stateful* mô tả sự phụ thuộc vào tiến độ xử lý, không bắt buộc phải lưu toàn bộ phần tử.

**Câu 2.** Với `[2, 4, 1, 6]`, `filter(n -> n % 2 == 0)` và `takeWhile(n -> n % 2 == 0)` khác nhau thế nào?  
**Trả lời:** `filter` trả `[2, 4, 6]`; `takeWhile` trả `[2, 4]` vì dừng ở phần tử `1` đầu tiên không thỏa.

**Câu 3.** Vì sao `numbers.stream().sorted().limit(3)` không đảm bảo chỉ đọc ba phần tử nguồn?  
**Trả lời:** Để biết ba phần tử nhỏ nhất trong nguồn chưa sắp xếp, `sorted` thường cần xem tất cả phần tử; `limit` đứng sau chỉ giới hạn đầu ra.

**Câu 4.** `filter()` có tự trở thành một stateful intermediate operation nếu lambda của nó tăng biến đếm dùng chung không?  
**Trả lời:** Không. `filter` vẫn được định nghĩa là stateless intermediate operation; lambda đó tự tạo sự phụ thuộc trạng thái bên ngoài, có thể làm kết quả không ổn định hoặc sai khi song song.

## Ghi nhớ

- **Stateless:** xử lý phần tử hiện tại độc lập với các phần tử khác (`filter`, `map`, `flatMap`).
- **Stateful:** cần nhớ giá trị đã gặp, vị trí, ranh giới hoặc thứ tự toàn cục (`distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`).
- **Cả hai đều có thể lazy:** sự khác biệt chủ yếu xuất hiện khi chạy pipeline, ở cách duyệt nguồn, khả năng dừng sớm, chi phí bộ nhớ và xử lý song song.
- **Tính đúng đắn đi trước tối ưu:** thay đổi thứ tự các phép toán có thể thay đổi kết quả; không dùng side effect của lambda để thay thế các phép toán tổng hợp đúng hợp đồng.
