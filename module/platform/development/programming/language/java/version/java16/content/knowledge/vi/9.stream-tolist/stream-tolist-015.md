# Pipeline song song và kiểm chứng thứ tự kết quả của `toList()`

`Stream.toList()` giữ thứ tự gặp (*encounter order*) nếu stream có thứ tự. Điều này vẫn đúng khi pipeline chạy song song: `parallelStream()` có thể xử lý các phần tử trên nhiều thread và theo thứ tự thực thi khác nhau, nhưng danh sách kết quả vẫn được sắp theo encounter order của nguồn nếu pipeline còn giữ đặc tính có thứ tự.

Cần phân biệt **thứ tự xử lý** với **thứ tự kết quả**. Parallel stream không bảo đảm mapper hoặc action được gọi theo thứ tự nguồn. `toList()` có thể trả danh sách đúng thứ tự dù các phần tử được xử lý đồng thời; `forEach()` thì không bảo đảm thứ tự action. Nếu cần thực hiện action theo encounter order, dùng `forEachOrdered()`.

## 1. Encounter order là gì?

Encounter order là thứ tự mà stream quy định các phần tử được gặp. Thứ tự này phụ thuộc vào nguồn và các operation của pipeline.

| Nguồn | Encounter order |
| --- | --- |
| `List` và mảng | Có, theo thứ tự phần tử trong nguồn. |
| `LinkedHashSet` | Có, theo thứ tự chèn. |
| `TreeSet` | Có, theo thứ tự sắp xếp của set. |
| `HashSet` | Không có bảo đảm thứ tự duyệt. |
| `Stream.generate()` | Không có encounter order được bảo đảm. |
| `Stream.iterate()` | Có, theo thứ tự các giá trị được sinh ra. |

Ví dụ với `List`, stream có encounter order giống thứ tự của list:

```java
import java.util.List;

List<String> source = List.of("A", "B", "C", "D");
List<String> result = source.stream().toList();

System.out.println(result); // [A, B, C, D]
```

`toList()` không tự sắp xếp theo alphabet, thời gian hoặc một thuộc tính nghiệp vụ. Nó giữ encounter order mà pipeline cung cấp.

## 2. Parallel stream vẫn giữ thứ tự kết quả của nguồn có thứ tự

Khi gọi `parallelStream()` trên một `List`, nguồn vẫn có encounter order. Nếu pipeline không loại bỏ yêu cầu thứ tự, `toList()` phải trả kết quả theo thứ tự đó:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

List<Integer> sequential = source.stream()
    .map(number -> number * 10)
    .toList();

List<Integer> parallel = source.parallelStream()
    .map(number -> number * 10)
    .toList();

System.out.println(sequential); // [10, 20, 30, 40, 50, 60]
System.out.println(parallel);   // [10, 20, 30, 40, 50, 60]
```

Các phép ánh xạ trong pipeline song song có thể được thực hiện đồng thời, nhưng kết quả vẫn được ghép theo encounter order. Không cần tự đánh số phần tử hoặc sắp xếp lại chỉ để khôi phục thứ tự của một stream có thứ tự.

Đây là bảo đảm về kết quả của pipeline, không phải bảo đảm các lambda được gọi lần lượt theo thứ tự nguồn. Nếu mapper ghi log, cập nhật biến dùng chung hoặc gọi hệ thống bên ngoài, thứ tự các side effect có thể khác với thứ tự danh sách kết quả.

## 3. Thứ tự thực thi không phải thứ tự encounter order

Đoạn mã sau có thể chạy action trên nhiều thread và không bảo đảm thứ tự in ra:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

source.parallelStream()
    .forEach(System.out::println);
```

Kết quả trên console có thể xuất hiện theo thứ tự khác nhau giữa các lần chạy. Đây không phải lỗi của `parallelStream()`: `forEach()` không cam kết action được gọi theo encounter order trên parallel stream.

Nếu muốn action được thực hiện theo thứ tự nguồn, dùng `forEachOrdered()`:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

source.parallelStream()
    .forEachOrdered(System.out::println);
```

Các action của `forEachOrdered()` được thực hiện theo encounter order. Chúng không nhất thiết chạy trên cùng một thread; điều được bảo đảm là thứ tự action. Việc yêu cầu thứ tự có thể làm giảm mức song song hiệu quả vì các action phải được điều phối theo thứ tự.

| Terminal operation | Trên ordered parallel stream |
| --- | --- |
| `toList()` | Trả danh sách theo encounter order. |
| `forEach()` | Không bảo đảm thứ tự thực hiện action. |
| `forEachOrdered()` | Thực hiện action theo encounter order. |
| `findFirst()` | Trả phần tử đầu tiên theo encounter order. |
| `findAny()` | Có thể trả bất kỳ phần tử phù hợp nào; không bảo đảm phần tử đầu tiên. |

## 4. Dùng mapper không có side effect để kết quả dễ dự đoán

Một mapper nên chuyển đổi phần tử và trả về giá trị, không nên phụ thuộc vào thứ tự thực thi hoặc trạng thái dùng chung:

```java
import java.util.List;

List<String> names = List.of("an", "binh", "chi", "dung");

List<String> normalized = names.parallelStream()
    .map(String::toUpperCase)
    .toList();

System.out.println(normalized); // [AN, BINH, CHI, DUNG]
```

Mỗi lần ánh xạ độc lập với các phần tử khác. Pipeline có thể thực hiện công việc đồng thời và vẫn trả danh sách theo encounter order.

Tránh dùng biến đếm hoặc collection mutable dùng chung bên trong mapper:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

// Không nên: nhiều thread cùng cập nhật một biến mutable không đồng bộ.
int[] counter = { 0 };
List<Integer> result = source.parallelStream()
    .map(value -> ++counter[0])
    .toList();
```

Thứ tự tăng của `counter` phụ thuộc lịch chạy thread và có thể xảy ra race condition. Nếu cần đánh số theo thứ tự nguồn, hãy thực hiện bước đó theo cách bảo toàn thứ tự, chẳng hạn dùng `IntStream.range()` trên danh sách có chỉ số hoặc xử lý tuần tự. Không dùng side effect trong lambda để suy ra thứ tự của phần tử.

Nếu cần tích lũy dữ liệu, hãy dùng collector thay vì tự thêm vào `ArrayList` dùng chung trong `forEach()`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("an", "binh", "chi", "dung");

List<String> result = source.parallelStream()
    .map(String::toUpperCase)
    .collect(Collectors.toCollection(ArrayList::new));
```

Collector quản lý các container tích lũy và kết hợp chúng theo hợp đồng reduction. Với ordered stream, collector phù hợp sẽ giữ encounter order. `ArrayList` kết quả vẫn là collection thông thường, không tự trở thành thread-safe sau khi thu thập.

## 5. Nguồn không có encounter order thì `toList()` không tạo ra thứ tự ổn định

Với nguồn như `HashSet`, không có thứ tự gặp được bảo đảm. `toList()` chỉ thu thập các phần tử theo cách stream cung cấp; không thể giả định kết quả luôn có một thứ tự cụ thể:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

Set<String> source = new HashSet<>(List.of("An", "Bình", "Chi", "Dung"));
List<String> result = source.parallelStream().toList();

System.out.println(result); // Thứ tự không được HashSet bảo đảm
```

Không viết test yêu cầu kết quả của ví dụ này phải đúng một thứ tự cố định. Nếu nghiệp vụ yêu cầu thứ tự cụ thể, hãy chọn nguồn có encounter order hoặc sắp xếp rõ ràng.

Ví dụ dùng `sorted()` để tạo thứ tự theo natural order:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

Set<String> source = new HashSet<>(List.of("An", "Bình", "Chi", "Dung"));

List<String> sorted = source.stream()
    .sorted()
    .toList();

System.out.println(sorted); // [An, Bình, Chi, Dung]
```

Hoặc chỉ định comparator:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

Set<String> source = new HashSet<>(List.of("An", "Bình", "Chi", "Dung"));

Comparator<String> byLengthThenName = Comparator.comparingInt(String::length)
    .thenComparing(Comparator.naturalOrder());

List<String> byLength = source.stream()
    .sorted(byLengthThenName)
    .toList();
```

Comparator thứ hai giúp xác định thứ tự khi hai chuỗi có cùng độ dài. Nếu chỉ so sánh độ dài mà không có tiêu chí phụ, các phần tử bằng nhau theo comparator có thể không có thứ tự tương đối được bảo đảm khi nguồn không có encounter order.

## 6. `unordered()` loại bỏ ràng buộc thứ tự, không phải thao tác xáo trộn

`unordered()` trả về một stream không cam kết encounter order. Phương thức này không có nghĩa là xáo trộn phần tử theo một thuật toán ngẫu nhiên; nó cho phép các operation phía sau không phải bảo toàn thứ tự nguồn.

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

List<Integer> ordered = source.parallelStream().toList();
List<Integer> withoutOrderGuarantee = source.parallelStream()
    .unordered()
    .toList();
```

`ordered` giữ thứ tự của list nguồn. Với `withoutOrderGuarantee`, không được dựa vào thứ tự cụ thể của kết quả, dù một lần chạy có thể tình cờ trả về thứ tự ban đầu.

Chỉ gọi `unordered()` khi nghiệp vụ không quan tâm encounter order. Một số operation có thể được triển khai hiệu quả hơn khi không phải phối hợp thứ tự, đặc biệt trong pipeline song song. Tuy nhiên, lợi ích thực tế phụ thuộc nguồn, pipeline và workload; cần đo thay vì mặc định rằng thêm `unordered()` luôn nhanh hơn.

## 7. `limit()` trên parallel stream và yêu cầu lấy đúng prefix

Với ordered stream, `limit(n)` phải chọn đúng `n` phần tử đầu theo encounter order. Trong parallel pipeline, việc phối hợp để xác định prefix này có thể tốn chi phí đáng kể:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);

List<Integer> firstTen = source.parallelStream()
    .limit(10)
    .toList();
```

Nếu nghiệp vụ chỉ cần bất kỳ 10 phần tử nào và không cần giữ thứ tự, có thể bỏ ràng buộc trước `limit()`:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);

List<Integer> anyTen = source.parallelStream()
    .unordered()
    .limit(10)
    .toList();
```

Hai đoạn mã có hợp đồng khác nhau. `firstTen` là prefix theo thứ tự nguồn; `anyTen` có thể là bất kỳ 10 phần tử nào. Không thay đổi sang `unordered()` nếu người dùng cần trang đầu, top-N theo thứ tự, hoặc một tập con xác định theo encounter order.

## 8. Kiểm chứng thứ tự bằng test có tính xác định

Khi nguồn có thứ tự và pipeline giữ encounter order, test nên kiểm tra chính xác danh sách kết quả bằng `equals()` hoặc assertion tương đương:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class ParallelToListTest {
    @Test
    void preservesEncounterOrderForParallelStream() {
        List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

        List<Integer> result = source.parallelStream()
            .map(number -> number * 10)
            .toList();

        assertEquals(List.of(10, 20, 30, 40, 50, 60), result);
    }
}
```

Test này không kiểm tra thread nào xử lý phần tử trước. Nó kiểm tra hợp đồng quan trọng với caller: danh sách đầu ra giữ encounter order của nguồn.

Nếu pipeline đã gọi `unordered()` hoặc nguồn không có encounter order, hãy kiểm tra đúng thuộc tính nghiệp vụ thay vì so sánh một thứ tự không được bảo đảm. Nếu thứ tự không quan trọng nhưng phần tử trùng lặp vẫn quan trọng, có thể so sánh tần suất từng giá trị; chuyển thành `Set` sẽ làm mất thông tin về số lần xuất hiện.

Không dùng `Thread.sleep()` để cố tạo một lịch chạy mong muốn rồi khẳng định thứ tự. Scheduler có thể khác giữa máy, tải và lần chạy; test phải dựa trên bảo đảm của API, không dựa vào thời gian thực thi tình cờ.

## 9. Chọn cách xử lý theo yêu cầu thứ tự

| Yêu cầu | Cách làm |
| --- | --- |
| Giữ thứ tự nguồn trong danh sách kết quả | Dùng ordered stream và `toList()`, kể cả khi pipeline là parallel. |
| Chạy action theo thứ tự nguồn | Dùng `forEachOrdered()` hoặc xử lý tuần tự nếu phù hợp. |
| Không quan tâm thứ tự, muốn nới ràng buộc cho pipeline | Cân nhắc `unordered()` và đo hiệu năng. |
| Cần thứ tự nghiệp vụ cụ thể | Dùng `sorted(comparator)` trước `toList()`. |
| Chỉ cần phần tử đầu tiên theo nguồn | Dùng `findFirst()`. |
| Chấp nhận bất kỳ phần tử phù hợp nào | Dùng `findAny()`, đặc biệt khi parallel. |
| Cần kiểm tra kết quả ổn định | Assertion nội dung và thứ tự chỉ khi API bảo đảm encounter order. |

## 10. Những điểm cần nhớ

- `toList()` giữ encounter order nếu stream có encounter order.
- Parallel stream có thể xử lý phần tử theo thứ tự bất kỳ nhưng vẫn trả danh sách theo encounter order.
- `forEach()` không bảo đảm thứ tự action trên parallel stream; `forEachOrdered()` thì có.
- `unordered()` bỏ ràng buộc thứ tự, không phải thao tác xáo trộn.
- `HashSet` không bảo đảm thứ tự duyệt; dùng `sorted()` hoặc nguồn có thứ tự khi cần kết quả ổn định.
- `unordered().limit(n)` có thể chọn tập con khác với `limit(n)` trên ordered stream.
- Giữ mapper/stateless operation không có side effect để tránh race condition và kết quả khó dự đoán.
- Kiểm thử hợp đồng kết quả, không kiểm thử lịch chạy thread.

Hãy tách bạch hai yêu cầu: danh sách cuối cần có thứ tự nào và các hành động trong lúc xử lý cần chạy theo thứ tự nào. `toList()` giải quyết thứ tự kết quả theo encounter order; nếu cần điều khiển thứ tự side effect, hãy chọn terminal operation phù hợp và tránh phụ thuộc vào lịch chạy thread.

## Tài liệu tham khảo

- [Stream.toList(), parallel streams và encounter order – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [Stream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [java.util.stream package – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Spliterator – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html)
- [Collection.stream() và Collection.parallelStream() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html)
