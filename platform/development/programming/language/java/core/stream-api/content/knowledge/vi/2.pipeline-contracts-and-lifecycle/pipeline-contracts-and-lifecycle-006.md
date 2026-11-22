# Non-interference: không can thiệp vào nguồn đang được xử lý

## Mục tiêu bài học

Trong Java Stream API, ta mô tả cách xử lý dữ liệu qua một **pipeline**: nguồn dữ liệu, các thao tác trung gian như `filter` và `map`, rồi thao tác kết thúc như `toList`, `collect` hoặc `reduce`. Phần lớn thao tác trung gian được thực thi **lười** (*lazy*): việc tạo pipeline chưa đồng nghĩa dữ liệu đã được duyệt.

Một hợp đồng quan trọng để pipeline hoạt động đúng là **non-interference**: hành vi được truyền vào Stream không được sửa đổi **nguồn dữ liệu mà Stream đang duyệt** trong lúc xử lý. Đây là nền tảng để các thao tác khai báo có thể được tối ưu, thực thi theo những thứ tự khác nhau hoặc chạy song song.

Sau bài này, bạn có thể:

- Nhận ra khi nào một lambda, một thread khác hoặc một phương thức phụ đang can thiệp vào nguồn Stream.
- Phân biệt non-interference với tính *stateless* và vấn đề tác dụng phụ (*side effect*).
- Chọn cách lọc, biến đổi, gom nhóm hoặc cập nhật dữ liệu mà không sửa nguồn giữa lúc pipeline chạy.
- Hiểu ảnh hưởng của tính lazy, các nguồn hỗ trợ đồng thời và `parallelStream()` tới hợp đồng này.

## 1. Non-interference là gì?

Xét một pipeline đơn giản:

```java
List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi"));

List<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList(); // JDK 16+

System.out.println(selected); // [BÌNH, CHI]
```

Ở đây:

1. **Nguồn** là `names`, một `ArrayList` có thể thay đổi.
2. **Thao tác trung gian** `filter` và `map` chỉ đọc từng phần tử để quyết định giữ lại và tạo giá trị mới.
3. **Thao tác kết thúc** `toList` kích hoạt việc duyệt và thu thập kết quả vào một danh sách khác.

Trong khi `toList()` đang xử lý, không có thao tác nào thêm, xóa hay thay đổi nội dung của `names`. Pipeline này tuân thủ non-interference.

```text
ArrayList names ── stream() ── filter() ── map() ── toList()
  (nguồn)                chỉ đọc từng phần tử       (kết quả mới)
```

**Điểm cốt lõi:** không can thiệp vào **nguồn đang được duyệt**. Việc Stream hoặc `Collector` tạo và cập nhật **vùng chứa kết quả riêng** không vi phạm nguyên tắc này.

Đối với các nguồn thông thường không thiết kế để thay đổi đồng thời, hợp đồng non-interference áp dụng cho các hàm hành vi được cung cấp cho Stream (predicate, mapper, comparator, consumer, accumulator...) và cho cả mã chạy ngoài pipeline trong lúc nguồn đang được duyệt. Ngoại lệ cần xét riêng là nguồn có cơ chế duyệt hỗ trợ sửa đổi đồng thời, được giải thích ở mục 6.

## 2. Ví dụ vi phạm: sửa chính danh sách trong `filter`

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> evens = numbers.stream()
        .filter(n -> {
            if (n == 2) {
                numbers.add(99); // SAI: sửa chính nguồn đang được duyệt
            }
            return n % 2 == 0;
        })
        .toList();
```

Khi chạy thao tác kết thúc `toList()`, lambda của `filter` thêm phần tử vào chính `numbers`. `ArrayList` thường phát hiện sửa đổi cấu trúc trong lúc duyệt và có thể ném `ConcurrentModificationException`. Tuy nhiên, **không được lấy việc có/không có exception làm tiêu chuẩn đúng sai**:

- Một nguồn khác có thể không phát hiện thay đổi.
- Thao tác thay thế giá trị như `list.set(index, value)` có thể không tăng bộ đếm sửa đổi cấu trúc, nhưng vẫn khiến kết quả phụ thuộc thời điểm đọc.
- Với pipeline chạy song song, sự thay đổi có thể gây bỏ sót, lặp phần tử hoặc kết quả khó dự đoán; hành vi cụ thể phụ thuộc nguồn và cách duyệt.

Tương tự, các cách sau cũng can thiệp vào nguồn nếu được thực hiện trong lúc pipeline đang duyệt `numbers`:

```java
numbers.removeIf(n -> n < 0);
numbers.clear();
numbers.set(0, 100);
```

Các lời gọi trên **không phải lúc nào cũng sai**. Chúng chỉ không được thực hiện *đồng thời với việc duyệt chính nguồn ấy*, trừ khi nguồn được thiết kế đặc biệt để cho phép. Chẳng hạn, gọi `removeIf` **trước** khi tạo/chạy Stream hoặc **sau** khi terminal operation hoàn thành là cách dùng bình thường.

### Cách sửa: tính kết quả trước, cập nhật nguồn sau

Nếu muốn lấy số chẵn để xử lý và xóa chúng khỏi danh sách ban đầu, hãy tách thành hai giai đoạn:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Giai đoạn 1: chỉ đọc nguồn; tạo kết quả riêng.
List<Integer> evens = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

// Giai đoạn 2: terminal operation đã xong, giờ mới thay đổi nguồn.
numbers.removeIf(n -> n % 2 == 0);

System.out.println(evens);   // [2, 4]
System.out.println(numbers); // [1, 3]
```

Nếu mục tiêu **chỉ** là xóa phần tử, gọi trực tiếp `numbers.removeIf(...)` là rõ ràng và không cần Stream. Nếu mục tiêu là biến đổi hoặc trích xuất dữ liệu, dùng `filter`/`map`/`collect` để tạo đầu ra mới.

## 3. Tính lazy quyết định thời điểm nào phải giữ nguồn ổn định

Lời gọi `stream()` và các thao tác trung gian thường chỉ **mô tả pipeline**. Chúng chưa bắt đầu duyệt toàn bộ nguồn; thao tác kết thúc mới kích hoạt việc xử lý.

```java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 3);

names.add("Chi"); // Trước terminal operation: hợp lệ với nguồn ArrayList này.

List<String> result = pipeline.toList();
System.out.println(result); // [Bình, Chi]
```

Ví dụ này dùng đặc tính *late-binding* của bộ duyệt từ `ArrayList`: nó chưa cố định tập phần tử cần duyệt khi vừa tạo pipeline. Nhiều nguồn Stream hoạt động như vậy, nhưng **không phải mọi nguồn đều bảo đảm cùng thời điểm ràng buộc**. Không nên suy diễn rằng mọi Stream đều phản ánh tất cả thay đổi trước terminal operation.

Phân biệt ba mốc thời gian:

| Thời điểm | Với nguồn `ArrayList` thông thường |
| --- | --- |
| Trước khi tạo pipeline | Có thể thêm, xóa, sửa phần tử như bình thường. |
| Sau khi dựng pipeline nhưng trước khi bắt đầu terminal operation | Có thể thay đổi; nguồn late-binding như `ArrayList` sẽ cho pipeline nhìn thấy thay đổi. |
| Trong lúc terminal operation đang duyệt nguồn | Không sửa nguồn; đây là vùng cần tuân thủ non-interference. |
| Sau khi terminal operation hoàn thành | Có thể cập nhật nguồn. Stream đã dùng thì không được chạy terminal operation lần nữa. |

Vì việc duyệt thường diễn ra bên trong thao tác kết thúc, **đừng** gọi phương thức sửa nguồn từ `filter`, `map`, `peek`, `forEach`, từ comparator truyền vào `sorted` hay từ accumulator của `reduce`. Một thread khác thay đổi nguồn trong cùng khoảng thời gian cũng gây vấn đề tương tự.

Một thao tác kết thúc có thể dừng sớm (`findFirst`, `anyMatch`, `limit` kết hợp terminal operation), hoặc hệ thống có thể bỏ qua một số bước nhờ tối ưu. Do đó không được dựa vào số lần lambda được gọi để thực hiện một chuỗi cập nhật bắt buộc.

## 4. Phân biệt non-interference, stateless và side effect

Ba khái niệm liên quan nhưng giải quyết những vấn đề khác nhau:

| Khái niệm | Câu hỏi cần kiểm tra | Ví dụ |
| --- | --- | --- |
| **Non-interference** | Hàm có sửa **nguồn đang được duyệt** không? | `source.add(...)` trong `filter` là vi phạm. |
| **Stateless** | Kết quả xử lý phần tử này có phụ thuộc trạng thái thay đổi khi xử lý các phần tử khác không? | Dùng biến đếm chung trong `map` thường là *stateful*. |
| **Side effect** | Hàm có làm việc gì ngoài tạo/kiểm tra giá trị đầu ra không? | Ghi log, tăng counter, gửi sự kiện là tác dụng phụ. |

Ví dụ sau **không sửa danh sách nguồn** nhưng vẫn dùng trạng thái chung nên không phù hợp với yêu cầu *stateless* của nhiều thao tác Stream:

```java
List<String> names = List.of("An", "Bình", "Chi");
AtomicInteger sequence = new AtomicInteger();

List<String> labels = names.parallelStream()
        .map(name -> sequence.incrementAndGet() + ": " + name)
        .toList();
```

`AtomicInteger` giúp phép tăng là nguyên tử nhưng **không bảo đảm** người nào nhận số thứ tự nào khi các phần tử được xử lý song song. Bài toán đánh số theo vị trí nên dùng vòng lặp theo chỉ số hoặc `IntStream.range` trên dữ liệu có chỉ số ổn định, thay vì phụ thuộc thời điểm thực thi mapper.

Một lỗi khác là ghi vào danh sách kết quả dùng chung:

```java
List<Integer> source = List.of(1, 2, 3, 4);
List<Integer> output = new ArrayList<>();

source.parallelStream()
        .map(n -> n * 2)
        .forEach(output::add); // SAI: nhiều thread cùng sửa ArrayList output.
```

Ở đây `output` **không phải nguồn**, nên lỗi trực tiếp là tác dụng phụ và truy cập đồng thời không an toàn, dù `source` không bị can thiệp. Cách viết đúng là để Stream quản lý việc tích lũy:

```java
List<Integer> output = source.parallelStream()
        .map(n -> n * 2)
        .toList(); // [2, 4, 6, 8], giữ encounter order của nguồn có thứ tự.
```

`peek` cũng không phải nơi đặt thao tác cập nhật nghiệp vụ: nó có thể hữu ích để quan sát khi debug, nhưng việc gọi lambda của `peek` không được bảo đảm cho mọi phần tử trong mọi pipeline. Khi cần kết quả có thể kiểm chứng, dùng `map` để tạo giá trị mới, `filter` để chọn phần tử và `collect` để tích lũy.

### Còn việc sửa thuộc tính của đối tượng trong nguồn?

```java
orders.stream()
        .peek(order -> order.setStatus("PROCESSED"))
        .toList();
```

Dù không gọi `orders.add/remove`, ví dụ trên vẫn mang tác dụng phụ lên các đối tượng đang thuộc nguồn. Nếu các thuộc tính ấy ảnh hưởng tới predicate, comparator, `equals/hashCode` hoặc đang được thread khác đọc, kết quả có thể không nhất quán. Hơn nữa, `peek` không bảo đảm chạy như một bước cập nhật. Cách an toàn là tạo bản ghi/DTO mới bằng `map`, hoặc thực hiện việc cập nhật đối tượng thành **giai đoạn riêng** có kiểm soát sau khi hoàn tất việc tính toán.

## 5. `collect` có sửa dữ liệu, vậy tại sao vẫn hợp lệ?

Non-interference không cấm **mọi** sự thay đổi. Nó cấm thay đổi **nguồn trong khi Stream đang xử lý nguồn đó**. Việc `Collector` xây dựng một `List`, `Map` hoặc cấu trúc kết quả mới là cơ chế tích lũy hợp lệ.

```java
List<String> words = List.of("java", "stream", "map", "reduce", "filter");

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(byLength);
// Ví dụ: {3=[map], 4=[java], 6=[stream, reduce, filter]}
```

Trong ví dụ trên, `groupingBy` tạo và cập nhật một `Map` kết quả; `words` không bị sửa. Với Stream song song, framework sử dụng cơ chế tích lũy và kết hợp của Collector theo hợp đồng, giúp tránh việc tự viết `forEach` rồi cập nhật một `HashMap` dùng chung không an toàn.

Cần chọn đúng dạng kết quả:

- `stream.toList()` (JDK 16+) trả về một `List` **không cho phép chỉnh sửa**; đừng gọi `add`/`remove` trên nó.
- `collect(Collectors.toList())` không cam kết kiểu triển khai hoặc khả năng chỉnh sửa của danh sách trả về.
- `collect(Collectors.toCollection(ArrayList::new))` phù hợp khi **cần một danh sách kết quả có thể thay đổi**.

Ví dụ:

```java
List<String> editable = words.stream()
        .filter(word -> word.length() >= 5)
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("pipeline"); // Sửa kết quả mới, không ảnh hưởng words.
```

Cũng cần phân biệt **thao tác trung gian có trạng thái bên trong** (`distinct`, `sorted`, `limit`) với **lambda phụ thuộc trạng thái ngoài**. Các thao tác thư viện được thiết kế để quản lý trạng thái của chính chúng; chúng không cho phép predicate/mapper tự ý thay đổi nguồn.

## 6. Nguồn có hỗ trợ thay đổi đồng thời: ngoại lệ phải hiểu đúng

Một số nguồn được thiết kế để có thể sửa đổi trong khi duyệt. Ví dụ, `ConcurrentHashMap` có `Spliterator` hỗ trợ đặc tính `CONCURRENT` và cơ chế duyệt *weakly consistent*: thay đổi đồng thời không nhất thiết gây `ConcurrentModificationException`, nhưng các phần tử vừa được thêm/xóa có thể được quan sát hoặc bỏ qua tùy thời điểm.

```java
ConcurrentHashMap<String, Integer> live = new ConcurrentHashMap<>();
live.put("A", 10);
live.put("B", 20);

// Nếu thread khác thay đổi live khi đang duyệt:
long matching = live.keySet().parallelStream()
        .filter(key -> key.startsWith("A"))
        .count();
```

Ở đây việc nguồn hỗ trợ concurrent traversal giải quyết **an toàn của cơ chế duyệt**, nhưng **không cung cấp ảnh chụp dữ liệu nguyên tử** và cũng không bảo đảm một kết quả cố định khi nội dung nguồn thay đổi. Phải chọn semantics phù hợp với nghiệp vụ:

- Chấp nhận một góc nhìn dữ liệu có thể thay đổi: dùng collection có hợp đồng concurrent traversal và chấp nhận kết quả tùy thời điểm.
- Cần tập dữ liệu ổn định để tính toán: tạo bản sao, bản dữ liệu bất biến hoặc khóa/phiên bản hóa dữ liệu theo thiết kế hệ thống trước khi xử lý.
- Cần tính nhất quán tại **một thời điểm duy nhất**: việc sao chép một collection đang bị cập nhật chưa đủ để bảo đảm snapshot nguyên tử; phải có cơ chế đồng bộ hoặc snapshot do hệ thống cung cấp.

Lưu ý, gọi `parallelStream()` trên `ArrayList` **không biến** `ArrayList` thành nguồn an toàn cho việc sửa đổi đồng thời. Tương tự, bọc danh sách bằng `Collections.synchronizedList(...)` không tự động biến mọi pipeline trên nó thành một phép duyệt có snapshot.

## 7. Ví dụ nghiệp vụ hoàn chỉnh: tổng hợp đơn hàng rồi cập nhật danh sách

Giả sử cần tính tổng giá trị các đơn đã thanh toán theo khách hàng, sau đó loại các đơn đã xử lý khỏi danh sách chờ. Hai nhiệm vụ có thể thực hiện tuần tự, mỗi nhiệm vụ rõ trách nhiệm:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NonInterferenceDemo {
    record Order(String customer, int amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> pending = new ArrayList<>(List.of(
                new Order("An", 100, true),
                new Order("Bình", 80, false),
                new Order("An", 50, true),
                new Order("Chi", 40, true)
        ));

        // Bước 1: chỉ đọc pending, tổng hợp vào Map riêng.
        Map<String, Integer> paidTotalByCustomer = pending.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::customer,
                        Collectors.summingInt(Order::amount)
                ));

        System.out.println(paidTotalByCustomer);
        // {An=150, Chi=40} (thứ tự khóa không được bảo đảm)

        // Bước 2: cập nhật pending sau khi terminal operation kết thúc.
        pending.removeIf(Order::paid);

        System.out.println(pending);
        // [Order[customer=Bình, amount=80, paid=false]]
    }
}
```

Điều cần quan sát:

1. `filter` chỉ kiểm tra trạng thái đơn hàng; không thay đổi `pending`.
2. `groupingBy` và `summingInt` tích lũy vào `Map` kết quả do Collector quản lý.
3. `removeIf` cập nhật nguồn **sau** khi `collect` đã hoàn thành.
4. Khi muốn xử lý nguồn bằng parallel stream, cách tách giai đoạn này vẫn giúp pipeline tránh phụ thuộc vào việc sửa nguồn trong lúc duyệt. Nếu có thread khác cùng cập nhật `pending`, vẫn phải có chiến lược đồng bộ riêng.

Ví dụ sử dụng `record` và `Stream.toList` trong bài cần Java 16 trở lên. Các ví dụ dùng `List.of` cần Java 9 trở lên; với Java 8 có thể dùng `Arrays.asList` để tạo dữ liệu ban đầu và `collect(Collectors.toList())` khi cần tạo danh sách từ Stream.

## 8. Dấu hiệu nhận biết lỗi và cách kiểm tra

Khi review một pipeline, hãy đi theo thứ tự sau:

1. **Xác định nguồn thực tế.** `source.stream()`, `map.keySet().stream()`, `Files.lines(path)` hoặc một `Spliterator` tùy chỉnh đang lấy dữ liệu từ đâu? Với view như `map.keySet()`, thay đổi `map` cũng là thay đổi nguồn.
2. **Tìm mọi đường ghi tới nguồn.** Kiểm tra `add`, `remove`, `clear`, `set`, thay đổi phần tử có trạng thái, lời gọi hàm phụ và mã chạy ở thread khác. Không chỉ nhìn vào body của `filter`.
3. **Xác định thời điểm ghi.** Sự thay đổi xảy ra trước, trong hay sau terminal operation? Các thao tác trung gian lazy khiến thời điểm khác với vị trí dòng lệnh tạo pipeline.
4. **Kiểm tra trạng thái dùng chung.** Nếu không sửa nguồn, lambda vẫn có thể dùng biến đếm, danh sách hoặc map bên ngoài; khi chạy song song, đó là rủi ro riêng.
5. **Kiểm tra hợp đồng nguồn.** Nếu dựa vào sửa đổi đồng thời, collection/Spliterator có cam kết hỗ trợ hay không? Có yêu cầu snapshot nhất quán không?

Một số triệu chứng cần truy nguyên:

| Triệu chứng | Điều cần xem lại |
| --- | --- |
| `ConcurrentModificationException` | Có sửa cấu trúc collection nguồn trong lúc pipeline duyệt không? |
| Không báo lỗi nhưng kết quả thất thường | Có `set`, thay đổi đối tượng, thread khác hoặc nguồn concurrent weakly consistent không? |
| Chạy tuần tự đúng, chạy `parallel` sai | Có trạng thái mutable dùng chung hoặc phụ thuộc thứ tự gọi lambda không? |
| `peek` không chạy cho mọi phần tử | Có tối ưu pipeline hoặc terminal operation dừng sớm không? |
| Kết quả trả về không sửa được | Có dùng `Stream.toList()` thay vì tạo collection mutable có chủ đích không? |

## 9. Tự luyện tập

Đoạn mã sau muốn lấy tất cả số lớn hơn 10 và đồng thời xóa chúng khỏi nguồn:

```java
List<Integer> values = new ArrayList<>(List.of(4, 12, 7, 18, 3));

List<Integer> large = values.stream()
        .filter(n -> {
            if (n > 10) {
                values.remove(n);
            }
            return n > 10;
        })
        .toList();
```

**Câu hỏi:** Đâu là vi phạm? Làm sao vẫn thu được `large = [12, 18]` và giữ `values = [4, 7, 3]`?

**Gợi ý đáp án:**

```java
List<Integer> large = values.stream()
        .filter(n -> n > 10)
        .toList();

values.removeIf(n -> n > 10);
```

Phần tử đã được lọc xong trước khi danh sách nguồn bị sửa. Không cần dựa vào thứ tự xử lý ngầm hay exception để đạt kết quả.

## Ghi nhớ

**Non-interference là hợp đồng về nguồn dữ liệu:** trong thời gian Stream đang duyệt một nguồn thông thường, các hàm hành vi và mã khác không được thay đổi nguồn ấy. Sự thay đổi của vùng kết quả do Collector quản lý là chuyện khác; một lambda không sửa nguồn vẫn có thể sai vì trạng thái chia sẻ hoặc tác dụng phụ. Hãy giữ `filter`/`map` thuần đọc, dùng `collect` để tạo kết quả và chuyển việc thay đổi nguồn thành một giai đoạn rõ ràng ngoài pipeline. Với nguồn concurrent, đọc đúng hợp đồng nhất quán của nguồn trước khi dựa vào việc cập nhật trong lúc duyệt.
