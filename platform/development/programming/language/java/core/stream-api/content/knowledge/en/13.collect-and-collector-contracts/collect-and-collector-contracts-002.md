# Sử dụng collect với supplier, accumulator và combiner

## 1. Từ Stream đến một kết quả có thể thay đổi

Trong **Java Stream API**, ta xây dựng một pipeline gồm nguồn dữ liệu, các thao tác trung gian như `filter` và `map`, rồi kích hoạt xử lý bằng thao tác kết thúc. Khi muốn **tích lũy các phần tử vào một vùng chứa kết quả có thể thay đổi**, `collect` là một lựa chọn quan trọng.

Trong chương **Cơ chế collect và Collector**, bài này tập trung vào overload **ba tham số**:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
);
```

Đây là phương thức trên `Stream<T>`. Ý nghĩa của ba thành phần:

- **`supplier`:** tạo một vùng chứa kết quả mới, ví dụ `ArrayList` hoặc `HashMap`.
- **`accumulator`:** đưa một phần tử của nguồn vào vùng chứa kết quả đó.
- **`combiner`:** gộp nội dung của hai vùng chứa kết quả, đặc biệt hữu ích khi pipeline được xử lý song song.

Ba hàm cùng nhau thực hiện **mutable reduction**: tích lũy bằng cách thay đổi vùng chứa kết quả, thay vì phải tạo một đối tượng kết quả mới sau mỗi phần tử.

Ví dụ ngắn:

```java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

List<String> result = words.stream()
        .collect(
                ArrayList::new,                  // supplier
                (list, word) -> list.add(word),  // accumulator
                (left, right) -> left.addAll(right) // combiner
        );

System.out.println(result); // [Java, Stream, API]
```

Kết quả `result` là một danh sách mới; nguồn `words` không bị sửa. Ta có thể viết ngắn hơn bằng `Collectors.toList()` hoặc `Collectors.toCollection(ArrayList::new)`. Giá trị của cách viết ba tham số nằm ở việc hiểu rõ cơ chế tích lũy và khi cần vùng chứa riêng cho bài toán.

**Sau bài này, bạn có thể:**

1. Giải thích chính xác vai trò và kiểu dữ liệu của ba tham số `collect`.
2. Viết mutable reduction thu thập vào `List`, `StringBuilder` hoặc `Map`.
3. Thiết kế `combiner` đúng với pipeline tuần tự lẫn song song.
4. Phân biệt `collect` ba tham số, `collect(Collector)` và `reduce`.
5. Tránh lỗi dùng chung vùng chứa, kết hợp sai, tác dụng phụ lên nguồn và các giả định không đúng về thứ tự thực thi.

Các ví dụ chính sử dụng Java 17+ để dùng `record`, `List.of` và `Stream.toList()`. Overload ba tham số của `collect` đã có từ Java 8.

## 2. Hợp đồng kiểu dữ liệu của ba hàm

Giả sử nguồn là `Stream<T>` và muốn trả về vùng chứa kiểu `R`:

| Tham số | Interface hàm | Nhận gì? | Trả về gì? |
| --- | --- | --- | --- |
| `supplier` | `Supplier<R>` | Không nhận đối số | Một đối tượng `R` mới |
| `accumulator` | `BiConsumer<R, ? super T>` | Vùng chứa `R` và phần tử nguồn `T` | `void` |
| `combiner` | `BiConsumer<R, R>` | Hai vùng chứa kết quả cùng kiểu `R` | `void` |

Điều cần chú ý là **accumulator và combiner không trả về vùng chứa mới**. Chúng phải làm thay đổi vùng chứa đã được truyền vào. Kết quả cuối cùng của `collect` có kiểu `R`.

```text
Stream<T> ── filter/map ── collect(...)
                               │
             supplier() ───────┤ tạo R
                               │
             accumulator(R,T) ─┤ thêm các phần tử T vào R
                               │
             combiner(R,R) ────┤ gộp các kết quả từng phần
                               ▼
                            kết quả R
```

Ví dụ, với `Stream<String>` thu thập vào `ArrayList<String>`:

```java
ArrayList<String> items = words.stream()
        .collect(
                () -> new ArrayList<String>(),
                (list, element) -> list.add(element),
                (destination, source) -> destination.addAll(source)
        );
```

`destination` và `source` trong combiner **đều là vùng chứa kết quả từng phần**, không phải collection nguồn của Stream.

## 3. Supplier phải cung cấp vùng chứa mới

`supplier` được phép được gọi nhiều lần khi framework cần tạo các kết quả từng phần. Một pipeline tuần tự đơn giản thường chỉ dùng một vùng chứa; trong thực thi song song, có thể có nhiều vùng chứa độc lập. **Không được dựa vào số lần gọi supplier cố định.**

Viết đúng:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

List<Integer> copy = numbers.parallelStream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(copy); // [1, 2, 3, 4]
```

Mỗi lần `ArrayList::new` chạy sẽ tạo một danh sách độc lập. Nhờ vậy, các tác vụ có thể tích lũy riêng và gộp sau.

**Cách viết sai: dùng chung một danh sách bên ngoài.**

```java
List<Integer> shared = new ArrayList<>();

// SAI: supplier trả lại cùng một đối tượng shared cho mọi lần gọi.
List<Integer> invalid = numbers.parallelStream()
        .collect(
                () -> shared,
                List::add,
                List::addAll
        );
```

Ở đây nhiều tác vụ có thể đồng thời thay đổi cùng một `ArrayList` vốn không hỗ trợ cập nhật đồng thời. Tệ hơn, combiner có thể gộp **một vùng chứa với chính nó**, gây lặp phần tử hoặc hành vi không đúng. Dù chương trình có vẻ chạy được khi tuần tự, supplier này không đáp ứng yêu cầu vùng chứa mới độc lập để phép reduction hoạt động đúng trong mọi chế độ.

**Quy tắc:** supplier phải sinh một đối tượng `R` mới mỗi lần cần một vùng chứa tích lũy. Không giữ các kết quả từng phần trong biến toàn cục để tự điều phối.

## 4. Accumulator thay đổi kết quả, không thay đổi nguồn

`accumulator` nhận vùng chứa `R` và một phần tử `T`. Nó xử lý **một phần tử** tại một thời điểm rồi thêm thông tin cần thiết vào `R`.

```java
List<String> raw = List.of(" An ", "  Bình", "Chi  ");

List<String> normalized = raw.stream()
        .collect(
                ArrayList::new,
                (result, name) -> result.add(name.strip()),
                (left, right) -> left.addAll(right)
        );

System.out.println(normalized); // [An, Bình, Chi]
```

Trong accumulator, `result.add(...)` sửa **danh sách kết quả mới**, không sửa `raw`. Điều này phù hợp với hợp đồng non-interference của Stream.

Tuy nhiên, nhiệm vụ biến đổi dữ liệu thông thường nên nằm ở `map` để pipeline rõ ý nghĩa:

```java
List<String> normalizedByPipeline = raw.stream()
        .map(String::strip)
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

Đây là hai cách hợp lệ; cách thứ hai phân biệt rõ **biến đổi phần tử** và **tích lũy kết quả**.

Không được sửa nguồn ngay trong accumulator:

```java
List<String> mutableSource = new ArrayList<>(List.of("A", "B"));

// SAI: đang duyệt mutableSource nhưng lại thêm vào chính nguồn.
List<String> wrong = mutableSource.stream()
        .collect(
                ArrayList::new,
                (result, value) -> {
                    result.add(value);
                    mutableSource.add("X");
                },
                List::addAll
        );
```

Đoạn trên có thể gây `ConcurrentModificationException` hoặc hành vi không đáng tin cậy. Chỉ thay đổi vùng chứa `R` do supplier tạo; cập nhật nguồn ở một giai đoạn khác sau khi terminal operation kết thúc nếu nghiệp vụ cần.

## 5. Combiner là điều kiện để kết quả đúng khi song song

Với Stream song song, framework có thể chia nguồn thành nhiều phần:

```text
Nguồn có thứ tự: [A, B, C, D]
              /             \
        [A, B]               [C, D]
          |                    |
       supplier()           supplier()
          |                    |
       add(A), add(B)       add(C), add(D)
          |                    |
      left=[A,B]          right=[C,D]
              \             /
               combiner(left, right)
                        |
                  [A,B,C,D]
```

Đây là **sơ đồ logic**, không phải cam kết rằng Stream luôn chia thành đúng hai phần hoặc gọi combiner theo chính trình tự này. Thực thi song song có thể chia và kết hợp thành nhiều nhánh; thậm chí combiner có thể không được gọi trong một lần thực thi nhất định.

Với danh sách:

```java
List<Integer> output = List.of(1, 2, 3, 4, 5).parallelStream()
        .collect(
                ArrayList::new,
                (list, item) -> list.add(item),
                (left, right) -> left.addAll(right)
        );

System.out.println(output); // [1, 2, 3, 4, 5]
```

Khi nguồn có encounter order như `List`, phép tích lũy bằng `add` rồi kết hợp bằng `addAll` theo hợp đồng tương thích sẽ bảo toàn thứ tự logic đó. Việc các thread thực thi accumulator theo thời điểm nào **không được bảo đảm**.

### Combiner phải gộp vào đối tượng đích

Ở overload này, combiner nhận hai kết quả `left` và `right` rồi **thay đổi `left`** để chứa cả hai. Ví dụ:

```java
(left, right) -> left.addAll(right)
```

Method reference tương ứng là `List::addAll` hoặc `ArrayList::addAll`, tùy kiểu suy luận. Mặc dù `addAll` trả về `boolean`, Java cho phép bỏ qua giá trị đó khi dùng trong ngữ cảnh `BiConsumer` có kiểu trả về `void`.

**Không thể chỉ gán lại biến tham số:**

```java
// SAI về ý nghĩa: chỉ gán biến cục bộ, không gộp nội dung vào left.
(left, right) -> {
    left = new ArrayList<>(right);
}
```

Biến `left` trong lambda là một tham số cục bộ; gán lại nó không thay đổi vùng chứa mà Stream quản lý. Combiner phải trực tiếp thêm dữ liệu vào vùng chứa đích hoặc dùng một cấu trúc tích lũy có giao thức đúng.

## 6. Ba quy tắc cần giữ: độc lập, identity và associativity

Để mutable reduction có thể hoạt động đúng với cách chia nguồn khác nhau, `supplier`, `accumulator` và `combiner` phải **tương thích**.

**1. Vùng chứa độc lập.** Mỗi lời gọi supplier tạo một `R` mới. Accumulator không lấy một collection dùng chung từ bên ngoài để ghi thay cho `R` được truyền vào.

**2. Phần kết quả rỗng là phần tử đơn vị (identity).** Gộp một vùng chứa `R` với kết quả rỗng mới sinh ra từ supplier không được thay đổi ý nghĩa kết quả:

```text
combine(result, empty) ~ result
```

Dấu `~` chỉ **tương đương về nội dung kết quả**, không yêu cầu cùng tham chiếu đối tượng trong mọi kiểu tích lũy.

**3. Kết hợp phải mang tính kết hợp (associativity).** Cách chia nhóm không được làm đổi kết quả logic:

```text
combine(combine(A, B), C) ~ combine(A, combine(B, C))
```

Với `List`, nối danh sách theo đúng thứ tự là phép kết hợp: `[A] + [B] + [C]` không phụ thuộc chỗ đặt ngoặc. Với việc cộng số nguyên trong phạm vi hợp lệ, tổng của các phần cũng có tính kết hợp.

Các quy tắc này liên hệ với accumulator: **tích lũy thêm một phần tử vào một kết quả** phải tương đương với **gộp kết quả đó với một vùng chứa độc lập chỉ gồm phần tử mới**. Chẳng hạn:

```text
accumulate([A,B], C) ~ combine([A,B], [C])
=> [A,B,C]
```

Nếu accumulator thêm phần tử vào cuối danh sách nhưng combiner lại chèn các phần tử vào đầu, kết quả song song có thể đảo lộn thứ tự. Nếu accumulator cộng số lượng nhưng combiner lấy `max` thay vì cộng, kết quả phụ thuộc vào cách chia tác vụ và sẽ sai.

### Ví dụ combiner sai dù pipeline tuần tự trông ổn

```java
List<Integer> source = List.of(1, 2, 3, 4);

// SAI: combiner bỏ qua right.
List<Integer> incorrect = source.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                (left, right) -> { }
        );
```

Trong đường chạy tuần tự, accumulator có thể thêm đủ bốn phần tử vào một danh sách nên che giấu lỗi. Khi song song, các kết quả từng phần bị bỏ mất vì combiner không gộp `right`. **Đừng dùng việc chạy tuần tự thành công để xác nhận một combiner là đúng.**

## 7. Ví dụ với StringBuilder: ghép chuỗi không tạo chuỗi mới mỗi bước

`StringBuilder` là vùng chứa có thể thay đổi, hữu ích để minh họa mutable reduction:

```java
import java.util.List;
import java.util.Locale;

List<String> codes = List.of("a1", "b2", "c3");

StringBuilder builder = codes.stream()
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(
                StringBuilder::new,
                (target, code) -> target.append(code).append(";"),
                (left, right) -> left.append(right)
        );

System.out.println(builder.toString()); // A1;B2;C3;
```

Supplier tạo `StringBuilder` mới; accumulator nối dữ liệu; combiner nối nội dung hai builder vào builder bên trái. `StringBuilder` **không thread-safe**, nhưng cách viết đúng dùng các vùng chứa độc lập, nên không yêu cầu nhiều thread đồng thời ghi cùng một builder.

Không nên dùng một builder toàn cục:

```java
StringBuilder shared = new StringBuilder();

// SAI với parallelStream: mọi nhánh cùng dùng shared.
String text = codes.parallelStream()
        .collect(
                () -> shared,
                (target, code) -> target.append(code),
                (left, right) -> left.append(right)
        )
        .toString();
```

Trong code ứng dụng, nếu mục tiêu chỉ là ghép chuỗi với dấu phân cách, `Collectors.joining(";")` thường gọn và tránh tự quản lý dấu phân cách:

```java
String joined = codes.stream()
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(java.util.stream.Collectors.joining(";"));

System.out.println(joined); // A1;B2;C3
```

## 8. Ví dụ với Map: cộng số liệu theo khóa

Giả sử mỗi bản ghi chứa mã bộ phận và số lượng kiện hàng. Mục tiêu là tạo Map tổng số lượng của từng bộ phận.

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Shipment(String department, int items) {}

List<Shipment> shipments = List.of(
        new Shipment("A", 3),
        new Shipment("B", 5),
        new Shipment("A", 2),
        new Shipment("C", 4)
);

Map<String, Integer> totals = shipments.parallelStream()
        .collect(
                HashMap::new,
                (map, shipment) -> map.merge(
                        shipment.department(),
                        shipment.items(),
                        Integer::sum
                ),
                (left, right) -> right.forEach(
                        (department, items) ->
                                left.merge(department, items, Integer::sum)
                )
        );

System.out.println(totals);
// {A=5, B=5, C=4} (thứ tự khóa không được bảo đảm)
```

Phân tích:

1. **Supplier:** `HashMap::new` tạo Map mới cho từng kết quả từng phần.
2. **Accumulator:** `Map.merge` cộng số kiện vào khóa bộ phận, tạo mới khóa khi chưa tồn tại.
3. **Combiner:** duyệt từng cặp khóa/giá trị của `right` và cộng vào `left` bằng **cùng quy tắc cộng**.
4. **Terminal operation:** trả về một `Map<String, Integer>` đã tổng hợp; không sửa `shipments`.

Phép cộng dùng ở cả accumulator và combiner nên tương thích. Nếu combiner dùng `left.putAll(right)`, các bộ phận trùng khóa sẽ bị ghi đè thay vì cộng, làm sai tổng khi chạy song song.

`HashMap` không cam kết thứ tự khóa. Nếu nghiệp vụ cần sắp xếp hiển thị, hãy sắp rõ ràng ở bước sử dụng kết quả, không suy đoán thứ tự từ thời điểm các nhánh song song hoàn thành.

### Khi nào nên dùng Collector có sẵn?

Với bài toán trên, thư viện cung cấp cách biểu đạt ngắn hơn:

```java
Map<String, Integer> byDepartment = shipments.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                Shipment::department,
                java.util.stream.Collectors.summingInt(Shipment::items)
        ));
```

Với những bài toán nhóm, đếm, cộng hoặc thu thập phổ biến, `Collectors.groupingBy`, `counting`, `summingInt` và các collector có sẵn thường dễ đọc và đã định nghĩa cơ chế kết hợp thích hợp. Overload ba tham số hữu ích khi vùng chứa và quy tắc tích lũy thực sự cần được điều khiển trực tiếp.

## 9. So sánh collect ba tham số với collect(Collector)

`Stream` có hai dạng `collect` thường dùng:

```java
// Mutable reduction với ba hàm.
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);

// Thu thập qua một Collector chứa đầy đủ các quy tắc.
<R, A> R collect(Collector<? super T, A, R> collector);
```

Ở dạng ba tham số, kiểu vùng chứa tích lũy `R` cũng là kiểu được trả về. Với `Collector<T, A, R>`, **`A` là kiểu tích lũy trung gian** và **`R` là kiểu kết quả cuối**; chúng có thể khác nhau nhờ **finisher**.

| Khía cạnh | `collect(supplier, accumulator, combiner)` | `collect(collector)` |
| --- | --- | --- |
| Mô tả logic | Truyền trực tiếp ba hàm vào terminal operation | Đóng gói vào một đối tượng `Collector` |
| Vùng chứa trung gian | Cùng kiểu với kết quả `R` | `A` có thể khác `R` |
| Finisher | Không có tham số finisher riêng | Có thể chuyển `A` sang `R` ở bước cuối |
| Kết hợp từng phần | `BiConsumer<R, R>`, gộp bằng thay đổi vùng chứa | `BinaryOperator<A>`, trả về vùng chứa đã kết hợp |
| Characteristics | Không khai báo trực tiếp | Có `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` theo hợp đồng collector |
| Tái sử dụng | Ba hàm thường viết tại nơi gọi | Có thể định nghĩa collector và dùng lại ở nhiều pipeline |

Một collector tương đương để thu thập vào `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> copied = words.stream()
        .collect(Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        ));
```

**Chú ý khác biệt của combiner:** trong `Collector.of`, nó có kiểu `BinaryOperator<A>` và **phải trả về** kết quả kết hợp. Trong `collect` ba tham số, combiner là `BiConsumer<R,R>` và **không trả về** giá trị.

Khi muốn chuyển `StringBuilder` thành `String` trong quá trình kết thúc thu thập, dạng `Collector.of` có finisher là một công cụ phù hợp:

```java
String result = words.stream()
        .collect(Collector.of(
                StringBuilder::new,
                (builder, word) -> builder.append(word),
                (left, right) -> {
                    left.append(right);
                    return left;
                },
                StringBuilder::toString
        ));
```

Với `collect` ba tham số, ta có thể nhận `StringBuilder` rồi gọi `toString()` bên ngoài; không có đối số finisher trong chính lời gọi `collect` đó.

Không tự gán `CONCURRENT` hay `UNORDERED` khi xây dựng collector tùy chỉnh nếu accumulator hoặc ngữ nghĩa kết quả không thỏa yêu cầu. Khai báo sai characteristics có thể dẫn tới hành vi không đúng khi chạy song song.

## 10. collect và reduce: khác nhau ở đâu?

`reduce` thường phù hợp với phép **giảm giá trị** để tạo kết quả mới theo quy tắc kết hợp, còn `collect` ba tham số phù hợp với việc **thay đổi vùng chứa kết quả mới**:

```java
List<Integer> values = List.of(2, 3, 5);

int sum = values.stream()
        .reduce(0, Integer::sum); // 10

List<Integer> copy = values.stream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

Với tổng số nguyên, `mapToInt(Integer::intValue).sum()` hoặc `reduce` diễn đạt trực tiếp mục tiêu. Không cần dựng `ArrayList` chỉ để tính tổng.

**Phản ví dụ thường gặp:** dùng `reduce` với một danh sách mutable làm identity rồi sửa nó trong accumulator:

```java
// SAI về hợp đồng reduction, đặc biệt nguy hiểm khi song song.
List<Integer> bad = values.parallelStream()
        .reduce(
                new ArrayList<Integer>(),
                (list, value) -> {
                    list.add(value);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

Với `reduce`, identity là một giá trị được dùng trong các phần tính, và phép reduction cần không thay đổi identity dùng chung. Cập nhật `ArrayList` này có thể làm hỏng kết quả. **Đúng nhiệm vụ tích lũy mutable thì dùng `collect` với supplier tạo container mới.**

## 11. Pipeline lazy và yêu cầu không can thiệp nguồn

`collect` là **thao tác kết thúc**: nó kích hoạt các thao tác trung gian được xây dựng trước đó.

```java
List<String> source = List.of("a", "bb", "ccc");

Stream<String> pipeline = source.stream()
        .filter(word -> word.length() >= 2)
        .map(String::toUpperCase);

// Chưa duyệt nguồn theo pipeline tại dòng trên.
List<String> collected = pipeline.collect(
        ArrayList::new,
        List::add,
        List::addAll
);

System.out.println(collected); // [BB, CCC]
```

Sau khi `collect` đã hoàn thành, `pipeline` không được tái sử dụng cho terminal operation khác. Muốn xử lý thêm lần nữa, tạo Stream mới từ `source`.

Các hàm `supplier`, `accumulator`, `combiner` không phải nơi để cập nhật một nguồn mutable đang được duyệt; chúng chỉ nên tạo/tích lũy/kết hợp **vùng chứa kết quả**. Với nguồn như `ArrayList` và `HashMap`, sửa nguồn trong lúc duyệt vi phạm non-interference. Trong xử lý song song, tránh luôn trạng thái dùng chung không có hợp đồng đồng bộ phù hợp.

Nếu cần làm phẳng, gom nhóm hoặc tạo báo cáo, có thể phối hợp `filter`/`map` với `collect`; với nguồn concurrent hoặc nguồn I/O, phải đọc đúng hợp đồng vòng đời và mức nhất quán của từng nguồn. `collect` không tự biến một nguồn đang thay đổi thành ảnh chụp dữ liệu nguyên tử.

## 12. Thứ tự, bộ nhớ và hiệu năng

### Thứ tự của kết quả

Với Stream có encounter order, một phép thu thập `List` bằng `add` và `addAll` tương thích có thể giữ thứ tự nguồn ngay cả khi chia để chạy song song. Nhưng nếu nguồn không có thứ tự, ví dụ một số `Set`, thì không được giả định danh sách kết quả có thứ tự ổn định.

Đối với `HashMap` được tích lũy theo nhóm, thứ tự duyệt khóa không được bảo đảm, bất kể số lần supplier hoặc combiner được gọi.

### Chi phí bộ nhớ

`collect` vào `List` hoặc `Map` thường cần lưu kết quả vào bộ nhớ. Nếu chỉ cần một số tổng hợp, `count`, `sum`, `reduce` hoặc `summaryStatistics` có thể tránh xây dựng tập kết quả lớn.

Trong Stream song song, có thể có **nhiều vùng chứa tích lũy tạm thời** trước khi gộp. Ví dụ `HashMap` cho từng nhánh phải giữ các khóa tạm thời, gây thêm chi phí bộ nhớ và combiner. Không mặc định rằng `parallelStream()` nhanh hơn.

### Phép kết hợp có tính toán phức tạp

Nếu combiner sao chép lại toàn bộ dữ liệu ở mỗi lần gộp hoặc luôn tạo collection mới, việc kết hợp có thể tốn nhiều cấp phát và sao chép. Với `ArrayList`, `left.addAll(right)` thường phù hợp hơn cách liên tục tạo danh sách mới chứa hai danh sách cũ.

### Độ chính xác và kết hợp

Không phải mọi phép toán đều kết hợp chính xác. Với `double`, phép cộng có sai số làm tròn; thay đổi cách nhóm có thể khiến chữ số cuối khác nhau. Với `int` và `long`, cộng quá phạm vi kiểu số có thể bị tràn. Khi thu thập dữ liệu tiền tệ hoặc cần tổng chính xác, chọn `BigDecimal` hay loại dữ liệu và chính sách phù hợp, đồng thời bảo đảm accumulator và combiner dùng **cùng quy tắc số học**.

## 13. Ví dụ nghiệp vụ đầy đủ: tổng hợp đơn hàng đã thanh toán

Ví dụ Java 17+ dưới đây trình bày cả việc thu thập vào danh sách và vào Map, sử dụng đúng ba tham số. Bài toán: lọc đơn đã thanh toán, chuẩn hóa mã khách, lấy danh sách giao dịch hợp lệ và tính tổng số lượng sản phẩm theo khách.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ThreeArgumentCollectDemo {
    record Order(String id, String customer, int quantity, boolean paid) {}
    record PaidOrder(String id, String customer, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-01", " An ", 3, true),
                new Order("O-02", "Bình", 8, false),
                new Order("O-03", " Chi ", 4, true),
                new Order("O-04", "an", 2, true)
        );

        List<PaidOrder> paidOrders = orders.stream()
                .filter(Order::paid)
                .map(order -> new PaidOrder(
                        order.id(),
                        order.customer().strip().toUpperCase(Locale.ROOT),
                        order.quantity()
                ))
                .collect(
                        ArrayList::new,
                        List::add,
                        List::addAll
                );

        Map<String, Integer> totalsByCustomer = paidOrders.parallelStream()
                .collect(
                        HashMap::new,
                        (map, order) -> map.merge(
                                order.customer(),
                                order.quantity(),
                                Integer::sum
                        ),
                        (left, right) -> right.forEach(
                                (customer, quantity) ->
                                        left.merge(customer, quantity, Integer::sum)
                        )
                );

        System.out.println(paidOrders);
        // [PaidOrder[id=O-01, customer=AN, quantity=3],
        //  PaidOrder[id=O-03, customer=CHI, quantity=4],
        //  PaidOrder[id=O-04, customer=AN, quantity=2]]

        System.out.println(totalsByCustomer);
        // {CHI=4, AN=5} hoặc cùng các cặp khóa/giá trị theo thứ tự khác

        System.out.println(orders.size()); // 4: nguồn không bị sửa.
    }
}
```

Các quyết định kỹ thuật trong ví dụ:

1. `filter` chọn đơn đã thanh toán để tránh xử lý đơn không cần thiết.
2. `map` tạo `PaidOrder` mới, chỉ chứa các trường phục vụ báo cáo.
3. `collect(ArrayList::new, List::add, List::addAll)` tạo danh sách kết quả theo encounter order.
4. Phép thu thập thứ hai dùng `HashMap::new` cho vùng chứa độc lập trong từng nhánh.
5. Accumulator và combiner cùng sử dụng `Integer::sum`, nên không làm mất số lượng của khách có nhiều đơn.
6. `orders` vẫn nguyên vẹn. Phần mềm thực tế cần kiểm tra dữ liệu thiếu, mã khách hợp lệ và phạm vi số lượng trước khi tính.

Trong hệ thống cần tổng chính xác lớn, thay kiểu `int` bằng kiểu số đủ phạm vi và thiết kế quy tắc overflow rõ ràng. Với bài toán nhiều nhóm hoặc giá trị phức tạp, một `Collector` tùy chỉnh có finisher hoặc collector có sẵn có thể dễ tái sử dụng hơn.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả sai khi chuyển từ `stream()` sang `parallelStream()` | Combiner bỏ qua hoặc gộp sai kết quả từng phần | Dùng cùng quy tắc tích lũy, kiểm tra identity và associativity. |
| Danh sách xuất hiện phần tử lặp | Supplier trả về cùng một collection hoặc combiner tự gộp collection với chính nó | Mỗi supplier phải tạo vùng chứa mới, độc lập. |
| `ConcurrentModificationException` | Accumulator sửa collection nguồn đang được duyệt | Chỉ sửa vùng chứa kết quả; cập nhật nguồn sau terminal operation. |
| Combiner tạo collection mới nhưng kết quả không thay đổi | `BiConsumer<R,R>` không nhận giá trị trả về | Thay đổi vùng chứa đích `left` trực tiếp. |
| Map có tổng sai khi chạy song song | Combiner dùng `putAll` làm mất giá trị cùng khóa | Dùng `merge` với phép cộng hay quy tắc gộp đúng. |
| Giữ trạng thái trong biến bên ngoài để đếm lần gọi | Không có cam kết số lần và thứ tự gọi callback | Dùng vùng chứa `R` của supplier và kết quả terminal operation. |
| Hiểu nhầm kết quả luôn giữ thứ tự | Nguồn unordered hoặc phép tích lũy không bảo toàn thứ tự | Xác định encounter order và yêu cầu kết quả trước khi chọn cấu trúc. |
| Muốn chuyển kiểu kết quả ngay trong `collect` ba tham số | Overload này không có finisher | Dùng `collect(Collector)` với finisher hoặc chuyển đổi sau khi collect. |
| Dùng `reduce` với `ArrayList` identity mutable | Phép giảm vi phạm hợp đồng identity và cập nhật chung | Dùng mutable reduction qua `collect`. |
| Parallel chậm hơn tuần tự | Quá nhiều vùng chứa từng phần và chi phí combiner | Đo thực tế, đơn giản hóa tích lũy, cân nhắc collector có sẵn. |

## 15. Bài tập thực hành

Cho danh sách các điểm số:

```java
record Score(String group, int value, boolean valid) {}

List<Score> scores = List.of(
        new Score("A", 8, true),
        new Score("B", 5, true),
        new Score("A", 7, true),
        new Score("C", 2, false)
);
```

**Yêu cầu:**

1. Dùng `collect(supplier, accumulator, combiner)` thu thập các điểm hợp lệ thành `List<Integer>`.
2. Dùng `collect` ba tham số tạo `Map<String, Integer>` lưu tổng điểm của mỗi nhóm.
3. Thử chuyển Stream sang `parallelStream()`. Giải thích vì sao combiner phải gộp các giá trị trùng nhóm.
4. Cố ý thay combiner Map thành `left.putAll(right)` rồi phân tích vì sao kết quả có thể sai.
5. Viết lại câu 2 bằng `Collectors.groupingBy` và `Collectors.summingInt`.

**Lời giải tham khảo:**

```java
List<Integer> validScores = scores.stream()
        .filter(Score::valid)
        .map(Score::value)
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
// [8, 5, 7]

Map<String, Integer> totals = scores.parallelStream()
        .filter(Score::valid)
        .collect(
                HashMap::new,
                (map, score) ->
                        map.merge(score.group(), score.value(), Integer::sum),
                (left, right) -> right.forEach(
                        (key, value) -> left.merge(key, value, Integer::sum)
                )
        );
// A=15, B=5 (thứ tự khóa không được bảo đảm)

Map<String, Integer> totalsWithCollector = scores.stream()
        .filter(Score::valid)
        .collect(java.util.stream.Collectors.groupingBy(
                Score::group,
                java.util.stream.Collectors.summingInt(Score::value)
        ));
```

Giải thích câu 4: `putAll` chỉ giữ một giá trị cho khóa `A` nếu `A` xuất hiện ở hai vùng chứa khác nhau. Quy tắc nghiệp vụ yêu cầu **cộng** điểm của `A` nên cần `merge(key, value, Integer::sum)`. Không nên dựa vào dữ liệu nhỏ hoặc một lần chạy song song cụ thể để chứng minh combiner sai/đúng, mà phải xét các cách chia nguồn hợp lệ.

**Tự mở rộng:** Viết phép collect tạo danh sách mã nhóm theo thứ tự xuất hiện rồi loại trùng. Thử so sánh với `distinct()` và `Collectors.toCollection(LinkedHashSet::new)`: cách nào diễn tả mục tiêu dễ hiểu hơn? Khi dùng tập hợp để loại trùng, cần giải thích rõ thuộc tính thứ tự của loại Set được chọn.

## Ghi nhớ

`Stream.collect(supplier, accumulator, combiner)` thực hiện **mutable reduction**: supplier tạo vùng chứa mới, accumulator thêm từng phần tử vào vùng chứa và combiner gộp những kết quả từng phần. Combiner phải thay đổi vùng chứa đích, tương thích với accumulator và thỏa các quy tắc identity, associativity để việc chia tác vụ không làm đổi kết quả. Các callback không được sửa nguồn đang duyệt hoặc phụ thuộc trạng thái mutable dùng chung.

Khi cần một tập hợp, một Map hay một bộ đệm có thể thay đổi, overload ba tham số giúp điều khiển cơ chế trực tiếp. Với bài toán phổ biến hoặc yêu cầu finisher và characteristics, `collect(Collector)` và các `Collectors` dựng sẵn thường rõ ràng hơn. Ưu tiên tính đúng đắn của phép kết hợp, sau đó mới đo lợi ích từ xử lý song song.
