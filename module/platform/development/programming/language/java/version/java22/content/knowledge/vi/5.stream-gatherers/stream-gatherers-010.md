# Kết hợp gatherer với filter, map, limit và các terminal operation

`Stream.gather(...)` là một intermediate operation cho phép chèn một `Gatherer` vào giữa pipeline. Có thể đặt `filter`, `map`, `limit` trước hoặc sau gatherer, rồi kết thúc pipeline bằng terminal operation như `toList`, `count`, `reduce`, `findFirst` hoặc `forEach`.

Điểm cần hiểu là gatherer có thể biến đổi một luồng đầu vào thành một luồng đầu ra với số phần tử khác nhau: một phần tử đầu vào có thể tạo ra không, một hoặc nhiều phần tử đầu ra; gatherer cũng có thể giữ trạng thái qua nhiều phần tử. Vì vậy, vị trí của mỗi operation làm thay đổi dữ liệu mà operation tiếp theo nhìn thấy. `limit` trước gatherer giới hạn số phần tử đầu vào, còn `limit` sau gatherer giới hạn số phần tử do gatherer phát ra.

Stream Gatherers xuất hiện ở Java 22 dưới dạng preview, được preview lại ở Java 23 và trở thành API chính thức trong Java 24 qua JEP 485. Các ví dụ trong bài dùng API ổn định từ JDK 24 trở lên, không cần `--enable-preview`.

## 1. Vị trí của gatherer trong Stream pipeline

Một pipeline thường có dạng:

```text
Source
  -> filter/map trước gatherer
  -> gather(gatherer)
  -> filter/map/limit sau gatherer
  -> terminal operation
```

`filter` và `map` vẫn là intermediate operations quen thuộc. `gather` cũng là intermediate operation, nhưng điểm khác biệt là một gatherer có thể gom nhiều phần tử, duy trì trạng thái, phát ra nhiều kết quả hoặc quyết định chưa phát ra kết quả nào.

| Operation | Vai trò khi đứng trước gatherer | Vai trò khi đứng sau gatherer |
|---|---|---|
| `filter` | Chọn những phần tử đầu vào mà gatherer sẽ nhận. | Lọc các phần tử do gatherer phát ra. |
| `map` | Chuyển đổi từng phần tử trước khi gatherer xử lý. | Chuyển đổi từng kết quả đầu ra của gatherer. |
| `limit(n)` | Giới hạn tối đa `n` phần tử nguồn đi vào gatherer. | Giới hạn tối đa `n` kết quả được lấy từ gatherer. |
| Terminal operation | Không phải một bước trung gian của pipeline. | Kết thúc pipeline, tiêu thụ kết quả cuối cùng và kích hoạt quá trình xử lý. |

Không nên xem hai vị trí trước và sau gatherer là tương đương. Nếu gatherer tạo cửa sổ, tổng tích lũy hoặc nhóm phần tử, operation phía sau làm việc trên các cửa sổ, tổng hoặc nhóm đó, chứ không còn làm việc trực tiếp trên từng phần tử nguồn.

## 2. Kết hợp `filter` và `map` trước gatherer

Ví dụ sau lọc số âm, nhân đôi các giá trị còn lại rồi gom chúng thành từng cửa sổ cố định gồm hai phần tử:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherBeforeAfterDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(1, -1, 2, 3, 4, 5)
            .filter(number -> number > 0)
            .map(number -> number * 2)
            .gather(Gatherers.windowFixed(2))
            .toList();

        System.out.println(windows);
        // [[2, 4], [6, 8], [10]]
    }
}
```

Trình tự xử lý:

1. Nguồn phát ra `1, -1, 2, 3, 4, 5`.
2. `filter` bỏ `-1`, còn `1, 2, 3, 4, 5`.
3. `map` nhân đôi, tạo `2, 4, 6, 8, 10`.
4. `windowFixed(2)` gom các phần tử thành những cửa sổ không chồng lấn. Cửa sổ cuối có thể ít hơn hai phần tử nếu nguồn còn lại không đủ để tạo cửa sổ đầy.
5. `toList()` thu thập các cửa sổ mà gatherer phát ra.

Ở đây, gatherer nhận dữ liệu đã lọc và biến đổi. Nếu chuyển `filter` hoặc `map` xuống sau `gather`, chúng sẽ tác động lên từng danh sách cửa sổ thay vì từng số nguyên.

## 3. Kết hợp `filter` và `map` sau gatherer

Có thể tiếp tục xử lý kết quả do gatherer tạo ra. Ví dụ, chỉ giữ các cửa sổ đầy đủ, tính tổng từng cửa sổ rồi thu thập hai tổng đầu tiên:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FilterAfterGathererDemo {
    public static void main(String[] args) {
        List<Integer> totals = Stream.of(1, -1, 2, 3, 4, 5)
            .filter(number -> number > 0)
            .map(number -> number * 2)
            .gather(Gatherers.windowFixed(2))
            .filter(window -> window.size() == 2)
            .map(window -> window.get(0) + window.get(1))
            .limit(2)
            .toList();

        System.out.println(totals); // [6, 14]
    }
}
```

Sau gatherer, kiểu phần tử của pipeline đã đổi từ `Integer` thành `List<Integer>`. Vì thế, lambda trong `filter` nhận một danh sách, còn lambda trong `map` tính tổng các phần tử của danh sách đó.

Kết quả `[6, 14]` được tạo như sau:

| Cửa sổ | `filter(window -> window.size() == 2)` | `map` tính tổng |
|---|---|---:|
| `[2, 4]` | Giữ lại | `6` |
| `[6, 8]` | Giữ lại | `14` |
| `[10]` | Loại bỏ vì không đủ hai phần tử | Không chạy |

Đây là cách kết hợp phổ biến: dùng operation trước gatherer để chuẩn hóa dữ liệu đầu vào; dùng gatherer để gom hoặc tạo kết quả theo trạng thái; rồi dùng operation sau gatherer để lọc và chuyển đổi kết quả đó.

## 4. Vị trí của `limit` làm thay đổi ý nghĩa

`limit` luôn giới hạn số phần tử trong pipeline tại vị trí nó xuất hiện. Với gatherer có thể gom nhiều phần tử đầu vào thành một kết quả, hai cách đặt `limit` có ý nghĩa khác nhau.

### Giới hạn đầu vào trước gatherer

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class LimitBeforeGathererDemo {
    public static void main(String[] args) {
        List<List<Integer>> firstFive = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
            .limit(5)
            .gather(Gatherers.windowFixed(2))
            .toList();

        System.out.println(firstFive); // [[1, 2], [3, 4], [5]]
    }
}
```

`limit(5)` cho gatherer tối đa năm phần tử nguồn. Vì vậy, `windowFixed(2)` tạo hai cửa sổ đầy và một cửa sổ cuối chỉ có một phần tử.

### Giới hạn kết quả sau gatherer

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class LimitAfterGathererDemo {
    public static void main(String[] args) {
        List<List<Integer>> firstTwoWindows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
            .gather(Gatherers.windowFixed(2))
            .limit(2)
            .toList();

        System.out.println(firstTwoWindows); // [[1, 2], [3, 4]]
    }
}
```

Ở đây `limit(2)` giới hạn hai cửa sổ đầu ra. Trong pipeline tuần tự này, khi downstream đã nhận đủ hai cửa sổ, nó có thể yêu cầu dừng xử lý và không cần tiêu thụ các phần tử còn lại của nguồn.

### Khi kết hợp với filter sau gatherer

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FilterThenLimitDemo {
    public static void main(String[] args) {
        List<List<Integer>> fullWindows = Stream.of(1, 2, 3, 4, 5, 6, 7)
            .gather(Gatherers.windowFixed(2))
            .filter(window -> window.size() == 2)
            .limit(2)
            .toList();

        System.out.println(fullWindows); // [[1, 2], [3, 4]]
    }
}
```

`limit(2)` ở cuối yêu cầu hai cửa sổ **đã qua filter**. Nếu một cửa sổ bị loại, pipeline có thể phải đọc thêm dữ liệu nguồn để tìm cửa sổ tiếp theo đáp ứng điều kiện. Vì thế, số phần tử nguồn được tiêu thụ không nhất thiết bằng `2` hoặc `2 × windowSize` trong mọi pipeline.

Hãy dùng `limit` trước gatherer khi yêu cầu nghiệp vụ nói về số phần tử đầu vào cần xử lý. Dùng `limit` sau gatherer khi yêu cầu nói về số kết quả được tạo ra. Nếu gatherer cần đọc nhiều phần tử mới tạo được một kết quả, nó có thể phải tiêu thụ nhiều phần tử nguồn trước khi downstream nhận đủ số kết quả.

## 5. Kết hợp với gatherer tích lũy bằng `scan`

`Gatherers.scan` duy trì trạng thái tích lũy và phát ra kết quả sau mỗi phần tử đầu vào. Các operation sau gatherer vì vậy làm việc trên chuỗi giá trị tích lũy, thay vì trên các giá trị ban đầu.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class ScanPipelineDemo {
    public static void main(String[] args) {
        List<Integer> totals = Stream.of(5, -2, 4, 1)
            .filter(number -> number > 0)
            .gather(Gatherers.scan(() -> 0, Integer::sum))
            .filter(total -> total >= 8)
            .map(total -> "Tổng hiện tại: " + total)
            .limit(2)
            .toList();

        System.out.println(totals);
        // [Tổng hiện tại: 9, Tổng hiện tại: 10]
    }
}
```

Pipeline hoạt động như sau:

1. `filter` loại `-2`, nên gatherer nhận `5, 4, 1`.
2. `scan` bắt đầu từ `0`, cộng từng phần tử và phát ra `5, 9, 10`.
3. `filter` phía sau chỉ giữ các tổng từ `8` trở lên, còn `9, 10`.
4. `map` chuyển mỗi tổng thành chuỗi.
5. `limit(2)` giới hạn hai chuỗi đầu ra; `toList()` thu thập chúng.

Nếu đặt `filter(total -> total >= 8)` trước gatherer thì lambda sẽ nhận từng số nguồn, không nhận tổng tích lũy. Đặt operation đúng phía là cách thể hiện chính xác ý nghĩa của dữ liệu đang được xử lý.

## 6. Kết hợp gatherer với terminal operations

Gatherer không kết thúc stream. Nó biến đổi dữ liệu trong pipeline; terminal operation mới kích hoạt quá trình xử lý và tiêu thụ kết quả cuối cùng.

| Terminal operation | Tác dụng sau gatherer |
|---|---|
| `toList()` | Thu thập toàn bộ phần tử mà gatherer và các operation sau nó phát ra. |
| `collect(collector)` | Thu thập các kết quả đầu ra bằng một `Collector`, chẳng hạn gom vào set hoặc map. |
| `count()` | Đếm số phần tử đầu ra sau gatherer, không phải số phần tử nguồn ban đầu. |
| `reduce(...)` | Gộp các phần tử đầu ra thành một giá trị tổng hợp. |
| `findFirst()` | Tìm phần tử đầu ra đầu tiên theo encounter order nếu stream có thứ tự. |
| `anyMatch(...)`, `allMatch(...)`, `noneMatch(...)` | Kiểm tra điều kiện trên các phần tử đầu ra; có thể dừng sớm khi kết quả đã xác định. |
| `forEach(...)` | Thực hiện hành động với từng phần tử đầu ra. Với stream song song, thứ tự thực thi không được bảo đảm. |

Ví dụ, đếm số cửa sổ đầy đủ thay vì đếm số phần tử nguồn:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class CountGatheredResultsDemo {
    public static void main(String[] args) {
        long fullWindowCount = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(2))
            .filter(window -> window.size() == 2)
            .count();

        System.out.println(fullWindowCount); // 2
    }
}
```

Nguồn có năm số, nhưng gatherer tạo ba cửa sổ (`[1, 2]`, `[3, 4]`, `[5]`). Filter loại cửa sổ cuối chưa đầy nên terminal operation `count()` trả về `2`.

Ví dụ dùng `reduce` để cộng tổng các cửa sổ:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class ReduceGatheredResultsDemo {
    public static void main(String[] args) {
        int sumOfWindowTotals = Stream.of(1, 2, 3, 4, 5, 6)
            .gather(Gatherers.windowFixed(2))
            .filter(window -> window.size() == 2)
            .map(window -> window.get(0) + window.get(1))
            .reduce(0, Integer::sum);

        System.out.println(sumOfWindowTotals); // 21
    }
}
```

Các cửa sổ đầy tạo tổng `3`, `7`, `11`; `reduce` cộng ba kết quả thành `21`.

## 7. Short-circuit và giới hạn xử lý

Một số operation như `limit`, `findFirst`, `anyMatch` và `noneMatch` có thể kết thúc sớm. Khi downstream không cần thêm kết quả, yêu cầu dừng có thể truyền ngược qua pipeline để gatherer và nguồn ngừng xử lý.

Tuy nhiên, mức độ dừng sớm phụ thuộc vào cách gatherer tạo kết quả:

- Gatherer phát ra kết quả sau mỗi phần tử có thể đáp ứng `findFirst` hoặc `limit` sớm.
- Gatherer gom nhiều phần tử mới phát ra một kết quả phải đọc đủ dữ liệu cần thiết trước khi downstream nhận được kết quả.
- Gatherer chỉ phát ra kết quả khi hoàn tất (ví dụ gatherer dạng fold) có thể phải tiêu thụ toàn bộ đầu vào trước khi `findFirst` nhận được kết quả.
- Một gatherer có thể phát ra nhiều kết quả từ một phần tử đầu vào; downstream có thể dừng giữa quá trình phát kết quả khi không cần thêm kết quả nữa.

Vì vậy, không nên suy luận rằng `limit(1)` luôn có nghĩa chỉ đọc một phần tử nguồn. Nó chỉ yêu cầu tối đa một phần tử ở vị trí pipeline đặt `limit`; gatherer ở phía trước có thể cần nhiều đầu vào để tạo phần tử đó.

Tránh đặt side effect quan trọng trong lambda của `map`, `filter` hoặc gatherer để đếm số phần tử đã đọc. Stream có tính lazy, có thể dừng sớm và một số pipeline có thể được tối ưu hóa. Nếu cần quan sát hiệu năng hoặc lượng dữ liệu đọc, hãy dùng công cụ profiling hoặc instrumentation phù hợp thay vì dựa vào side effect trong pipeline.

## 8. Chọn thứ tự operation theo yêu cầu

| Yêu cầu | Cách bố trí pipeline |
|---|---|
| Chỉ gom những phần tử hợp lệ | `filter(...).gather(...)` |
| Chuẩn hóa từng phần tử trước khi gom | `map(...).gather(...)` |
| Lọc những nhóm/cửa sổ sau khi gom | `gather(...).filter(...)` |
| Chuyển mỗi nhóm thành một kết quả đơn giản | `gather(...).map(...)` |
| Chỉ xử lý tối đa N phần tử nguồn | `limit(N).gather(...)` |
| Chỉ lấy tối đa N kết quả được gatherer phát ra | `gather(...).limit(N)` |
| Đếm hoặc tổng hợp kết quả đã tạo | `gather(...).count()` hoặc `gather(...).reduce(...)` |
| Tìm kết quả đầu tiên đáp ứng điều kiện | `gather(...).filter(...).findFirst()` |

Trước khi viết pipeline, hãy xác định kiểu dữ liệu ở từng điểm: kiểu của nguồn, kiểu gatherer nhận, kiểu gatherer phát ra và kiểu terminal operation tiêu thụ. Việc ghi rõ các kiểu này giúp tránh đặt nhầm `filter` hoặc `map` ở phía trước/sau gatherer.

## 9. Các lưu ý khi kết hợp với stream song song

Các operation trước và sau gatherer vẫn tuân theo quy tắc của Stream API. Nếu dùng `.parallel()`, cần hiểu đặc tính của nguồn, encounter order và khả năng kết hợp của gatherer. Một số gatherer có thể xử lý song song hiệu quả nhờ combiner; gatherer tuần tự hoặc có trạng thái phụ thuộc thứ tự có thể hạn chế lợi ích song song.

Không giả định `forEach` giữ thứ tự encounter khi chạy song song. Nếu cần hành động theo thứ tự, cân nhắc `forEachOrdered` hoặc giữ pipeline tuần tự. Cũng không chia sẻ mutable state bên ngoài giữa các lambda nếu không có cơ chế đồng bộ phù hợp.

## 10. Kết luận

`gather` kết hợp với `filter`, `map`, `limit` và terminal operations bằng cách giữ nguyên mô hình pipeline của Stream API, nhưng cho phép một bước xử lý có trạng thái và có thể thay đổi số lượng phần tử. Hãy nhớ ba quy tắc:

1. Operation trước gatherer xử lý dữ liệu đầu vào mà gatherer nhận; operation sau gatherer xử lý dữ liệu mà gatherer phát ra.
2. `limit` giới hạn số phần tử tại vị trí nó xuất hiện: trước gatherer là số đầu vào, sau gatherer là số kết quả.
3. Terminal operation tiêu thụ kết quả cuối cùng; short-circuit có thể dừng sớm, nhưng gatherer có thể cần nhiều phần tử nguồn trước khi phát ra kết quả.

Stream Gatherers là API chính thức từ Java 24. Khi phát triển với JDK hiện đại, hãy dùng `Stream.gather` và `java.util.stream.Gatherers` mà không bật preview; các giai đoạn preview Java 22/23 chỉ có ý nghĩa lịch sử.

## Tài liệu tham khảo

- [JEP 485 – Stream Gatherers](https://openjdk.org/jeps/485)
- [JEP 461 – Stream Gatherers (Java 22 Preview)](https://openjdk.org/jeps/461)
- [JEP 473 – Stream Gatherers (Java 23 Second Preview)](https://openjdk.org/jeps/473)
- [Stream – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Gatherer – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherer.html)
- [Gatherers – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherers.html)
