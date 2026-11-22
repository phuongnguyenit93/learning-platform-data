# Ánh xạ không, một hoặc nhiều kết quả bằng mapMulti

## 1. Vì sao cần `mapMulti` trong Java Stream API?

Trong chương **Lọc và biến đổi phần tử** của **JAVA_STREAM_API**, ta thường dùng `filter` để giữ lại những phần tử thỏa điều kiện và `map` để chuyển mỗi phần tử thành một giá trị mới. Nhưng có những phép biến đổi mà **một phần tử đầu vào có thể tạo ra 0, 1 hoặc nhiều phần tử đầu ra**:

- Một dòng trống tạo ra **0 từ khóa**.
- Một dòng chỉ chứa một từ hợp lệ tạo ra **1 từ khóa**.
- Một dòng chứa nhiều từ hợp lệ tạo ra **nhiều từ khóa**.
- Một đơn hàng có số lượng `quantity = 3` có thể tạo ra **3 mã đơn vị hàng**.
- Một đối tượng không đúng kiểu cần xử lý có thể bị bỏ qua; đối tượng đúng kiểu có thể được chuyển thành một hoặc nhiều giá trị.

Từ **Java 16**, `Stream.mapMulti` cung cấp cách diễn đạt trực tiếp cho kiểu ánh xạ này. Thay vì bắt buộc trả về một Stream con ở mỗi phần tử như `flatMap`, lambda của `mapMulti` nhận thêm một **Consumer**; ta gửi kết quả đến Consumer bằng cách gọi `accept` từ **0 đến nhiều lần**.

~~~text
                  MỖI PHẦN TỬ ĐẦU VÀO
                            │
                            ▼
                   mapMulti((x, out) -> ...)
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
          0 lần accept  1 lần accept  N lần accept
               │            │            │
               ▼            ▼            ▼
              []          [y1]     [y1, y2, ..., yn]
               └────────────┴────────────┘
                            │
                            ▼
                     Stream<R> đầu ra
~~~

Mục tiêu của bài là hiểu hợp đồng `mapMulti`, phân biệt nó với `map` và `flatMap`, sử dụng các phiên bản cho kiểu nguyên thủy, và áp dụng an toàn trong pipeline **lazy**, có thể nối tiếp với `filter`, `reduce` và `collect`.

## 2. Chữ ký, tham số và hợp đồng

Chữ ký khái niệm của `Stream<T>.mapMulti`:

~~~java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
);
~~~

Phần tử đang được xử lý có kiểu `T`. Hàm `mapper` nhận hai đối số:

| Đối số | Vai trò |
| --- | --- |
| `T element` | Phần tử đầu vào hiện tại của pipeline. |
| `Consumer<R> downstream` | Nơi gửi các kết quả có kiểu `R`; gọi `downstream.accept(value)` để phát ra một phần tử. |

Ví dụ ánh xạ **mỗi số lẻ thành 0 kết quả, mỗi số chẵn thành 2 kết quả**:

~~~java
import java.util.List;

public class MapMultiBasics {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        List<Integer> result = numbers.stream()
            .<Integer>mapMulti((number, out) -> {
                if (number % 2 == 0) {
                    out.accept(number);
                    out.accept(number * 10);
                }
            })
            .toList();

        System.out.println(result); // [2, 20, 4, 40]
    }
}
~~~

Quan sát:

1. Với `1` và `3`, lambda không gọi `accept` nên không có phần tử đầu ra.
2. Với `2`, lambda gọi `accept(2)` rồi `accept(20)`.
3. Với `4`, lambda gọi `accept(4)` rồi `accept(40)`.
4. `toList()` thu kết quả của pipeline, theo encounter order của nguồn `List`.

`mapMulti` là **intermediate operation**: việc tạo pipeline không tự chạy lambda ngay. Mỗi lần xử lý một phần tử đầu vào, lambda phải phát tất cả kết quả bằng Consumer được cung cấp. Lambda **không trả về** giá trị cho Stream (kiểu trả về của `BiConsumer.accept` là `void`).

Không nên giữ lại Consumer `out` để dùng sau khi callback kết thúc hoặc gửi nó sang tác vụ bất đồng bộ: hợp đồng của `mapMulti` yêu cầu sử dụng Consumer trong lần gọi mapper tương ứng.

## 3. Ví dụ thực tế: tách và lọc từ trong nhiều dòng

Giả sử ta nhận các dòng văn bản. Mỗi dòng có thể rỗng, chỉ có một từ đủ dài hoặc có nhiều từ. Ta muốn bỏ từ ngắn hơn 4 ký tự, chuẩn hóa về chữ thường và gom kết quả.

~~~java
import java.util.List;
import java.util.Locale;

public class ExtractWords {
    public static void main(String[] args) {
        List<String> lines = List.of(
            "Java Stream API",
            "   ",
            "mapMulti",
            "filter map reduce"
        );

        List<String> words = lines.stream()
            .<String>mapMulti((line, out) -> {
                if (line.isBlank()) {
                    return; // 0 kết quả
                }

                for (String word : line.strip().split("\\s+")) {
                    if (word.length() >= 4) {
                        out.accept(word.toLowerCase(Locale.ROOT));
                    }
                }
            })
            .toList();

        System.out.println(words);
        // [java, stream, mapmulti, filter, reduce]
    }
}
~~~

Ở đây, các dòng lần lượt tạo **2, 0, 1, 2 phần tử**. Ta không phải tạo một `List<String>` tạm cho từng dòng rồi gọi `stream()` trên danh sách đó.

Đoạn `return` bên trong lambda có nghĩa là **kết thúc xử lý dòng hiện tại**; không kết thúc toàn bộ pipeline. Vì lambda không có giá trị trả về, một dòng trống được biểu diễn đơn giản bằng việc **không gọi `out.accept`**.

### Quy trình hoạt động

~~~mermaid
flowchart TD
    A["Một dòng văn bản"] --> B{"Dòng trống?"}
    B -->|Có| C["Không emit phần tử"]
    B -->|Không| D["Tách dòng thành các từ"]
    D --> E{"Từ dài ít nhất 4 ký tự?"}
    E -->|Không| F["Bỏ từ hiện tại"]
    E -->|Có| G["out.accept(từ đã chuẩn hóa)"]
    G --> H["Phần tử đi tiếp xuống pipeline"]
    F --> I["Xét từ tiếp theo"]
    H --> I
~~~

Nếu có nhu cầu lọc tiếp, ta vẫn có thể nối thêm các operation:

~~~java
List<String> distinctWords = lines.stream()
    .<String>mapMulti((line, out) -> {
        for (String word : line.strip().split("\\s+")) {
            if (word.length() >= 4) {
                out.accept(word.toLowerCase(Locale.ROOT));
            }
        }
    })
    .distinct()
    .sorted()
    .toList();

// [filter, java, mapmulti, reduce, stream]
~~~

`distinct()` và `sorted()` là các intermediate operations có trạng thái do Stream quản lý; chúng có thể cần lưu trữ các phần tử và ảnh hưởng đến hiệu năng. Lambda của `mapMulti` nên tiếp tục là phép xử lý độc lập cho từng phần tử đầu vào.

## 4. So sánh `map`, `filter`, `flatMap` và `mapMulti`

| Operation | Một phần tử đầu vào tạo ra | Dạng thường dùng | Đặc điểm |
| --- | --- | --- | --- |
| `map` | Đúng **1 phần tử** | `map(x -> transform(x))` | Biến đổi 1–1. |
| `filter` | **0 hoặc 1** phần tử hiện tại | `filter(x -> predicate(x))` | Giữ hoặc loại; không đổi kiểu phần tử. |
| `flatMap` | **0 đến nhiều** phần tử | `flatMap(x -> streamOfResults(x))` | Mapper trả Stream con rồi Stream làm phẳng. |
| `mapMulti` | **0 đến nhiều** phần tử | `mapMulti((x, out) -> out.accept(...))` | Mapper phát phần tử bằng Consumer. |

Với ví dụ số chẵn ở mục 2, cách viết tương đương bằng `flatMap`:

~~~java
import java.util.stream.Stream;

List<Integer> result = numbers.stream()
    .flatMap(number -> number % 2 == 0
        ? Stream.of(number, number * 10)
        : Stream.<Integer>empty())
    .toList();

// [2, 20, 4, 40]
~~~

**Khác biệt chính:**

- `flatMap` thích hợp khi phép biến đổi **tự nhiên đã trả về Stream**, ví dụ `list.stream()`, `Optional.stream()` hoặc một API trả `Stream<R>`.
- `mapMulti` thích hợp khi có thể **phát trực tiếp một vài kết quả** bằng `accept`; người viết không cần tạo Stream con tại mỗi lần gọi.
- Trong một số trường hợp cần tạo rất nhiều Stream con nhỏ, `mapMulti` **có thể** giảm chi phí cấp phát và cải thiện hiệu năng. Không được khẳng định nó luôn nhanh hơn: tối ưu hóa phụ thuộc JDK, pipeline và khối lượng dữ liệu; cần benchmark nếu hiệu năng là mục tiêu.
- Mặc dù cách sử dụng `mapMulti` tránh việc người dùng tự tạo Stream con, triển khai mặc định của API có thể sử dụng vùng đệm bên trong. Vì vậy không nên hiểu `mapMulti` là bảo đảm **không cấp phát bộ nhớ**.

Không có quy tắc bắt buộc luôn chọn `mapMulti`. Chọn operation thể hiện ý định rõ nhất và đo thực tế khi cần tối ưu hóa.

## 5. Phát 0 hoặc 1 giá trị: parse, kiểm tra và loại dữ liệu sai

`mapMulti` có thể kết hợp việc biến đổi và chọn phần tử. Giả sử chỉ chấp nhận mã là số nguyên dương; chuỗi sai định dạng hoặc số không hợp lệ được phép bỏ qua.

~~~java
import java.util.List;

public class ValidIds {
    public static void main(String[] args) {
        List<String> rawIds = List.of(
            "12", "x", " 7 ", "-3", "0", "25"
        );

        List<Integer> validIds = rawIds.stream()
            .<Integer>mapMulti((raw, out) -> {
                try {
                    int value = Integer.parseInt(raw.trim());
                    if (value > 0) {
                        out.accept(value); // Phát đúng 1 số hợp lệ.
                    }
                } catch (NumberFormatException ex) {
                    // Đầu vào không hợp lệ: không phát phần tử nào.
                }
            })
            .toList();

        System.out.println(validIds); // [12, 7, 25]
    }
}
~~~

Cách viết trên mô tả chính sách **bỏ qua đầu vào không hợp lệ**. Trong nghiệp vụ mà chuỗi không hợp lệ phải được báo lỗi, lưu lý do hoặc tính vào báo cáo chất lượng dữ liệu, không nên âm thầm bỏ qua với `mapMulti`; cần mô hình hóa cả kết quả thành công lẫn lỗi.

Tương đương bằng `map` kết hợp `Optional.stream`:

~~~java
import java.util.Optional;

static Optional<Integer> positiveNumber(String raw) {
    try {
        int value = Integer.parseInt(raw.trim());
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}

// Bên trong lớp có phương thức positiveNumber:
List<Integer> validIds = rawIds.stream()
    .map(YourClass::positiveNumber)
    .flatMap(Optional::stream)
    .toList();
~~~

Trong đoạn minh họa, thay `YourClass` bằng tên lớp thực tế chứa phương thức `positiveNumber`; biến `rawIds` là danh sách ở ví dụ trước. Cả hai cách đều biểu diễn 0–1 kết quả; chọn `Optional` nếu kết quả tùy chọn còn cần dùng ở chỗ khác, hoặc `mapMulti` khi chỉ muốn đưa trực tiếp giá trị có mặt xuống Stream.

### Lưu ý về suy luận kiểu với `mapMulti`

Bởi lambda nhận một `Consumer<R>` và không trả về `R`, Java đôi khi **không suy ra được kiểu đầu ra cụ thể**. Đặc biệt, khi dùng `var` hoặc gọi chuỗi phương thức tiếp theo mà không có ngữ cảnh kiểu đủ mạnh, kết quả có thể bị suy ra thành `Stream<Object>`.

Nêu rõ tham số kiểu khi cần:

~~~java
List<Integer> result = List.of("1", "2").stream()
    .<Integer>mapMulti((raw, out) -> out.accept(Integer.parseInt(raw)))
    .toList();

// result có kiểu List<Integer>.
~~~

Phần `.<Integer>mapMulti(...)` gọi **generic method `mapMulti` với R = Integer**; đây không phải ép kiểu runtime.

## 6. Phát nhiều kết quả từ dữ liệu lồng nhau

Một danh sách nhóm có thể chứa nhóm rỗng hoặc nhiều phần tử. `mapMulti` có thể làm phẳng một tầng bằng cách phát trực tiếp từng phần tử:

~~~java
import java.util.List;

List<List<String>> teams = List.of(
    List.of("An", "Bình"),
    List.of(),
    List.of("Chi"),
    List.of("Dung", "Hà")
);

List<String> members = teams.stream()
    .<String>mapMulti((team, out) -> team.forEach(out))
    .toList();

System.out.println(members); // [An, Bình, Chi, Dung, Hà]
~~~

Tương đương bằng `flatMap`, thường ngắn hơn nếu dữ liệu đã có `stream()`:

~~~java
List<String> members = teams.stream()
    .flatMap(List::stream)
    .toList();
~~~

Không phải trường hợp nào `mapMulti` cũng rõ ràng hơn. Khi xử lý nhóm lồng nhau đơn giản, `flatMap(List::stream)` thường dễ đọc; `mapMulti` phát huy tác dụng khi **một phép duyệt cần điều kiện, chuyển đổi hoặc phát nhiều phần tử** mà không cần tạo đối tượng trung gian.

### Ví dụ nghiệp vụ: nở đơn hàng theo số lượng

Mỗi dòng đơn hàng có mã sản phẩm và số lượng. Ta muốn danh sách mã sản phẩm theo từng đơn vị để chuẩn bị tạo nhãn kho:

~~~java
import java.util.List;

public class ExpandOrderItems {
    record OrderLine(String sku, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 2),
            new OrderLine("PEN", 1),
            new OrderLine("PAD", 0)
        );

        List<String> unitSkus = lines.stream()
            .<String>mapMulti((line, out) -> {
                for (int i = 0; i < line.quantity(); i++) {
                    out.accept(line.sku());
                }
            })
            .toList();

        System.out.println(unitSkus); // [BOOK, BOOK, PEN]
    }
}
~~~

Trong hệ thống thật, cần kiểm tra `quantity` không âm và có giới hạn hợp lý **trước khi nở dữ liệu**. Nếu chỉ muốn tính tổng số lượng, có thể dùng `mapToLong(OrderLine::quantity).sum()` thay vì phát hàng triệu phần tử. Chọn Stream giúp diễn đạt bài toán, không thay thế việc kiểm soát kích thước đầu ra.

## 7. Các phiên bản cho kiểu nguyên thủy

`Stream<T>` hỗ trợ thêm ba biến thể khi kết quả là primitive:

| Operation trên `Stream<T>` | Consumer bên trong lambda | Stream trả về |
| --- | --- | --- |
| `mapMultiToInt` | `IntConsumer` | `IntStream` |
| `mapMultiToLong` | `LongConsumer` | `LongStream` |
| `mapMultiToDouble` | `DoubleConsumer` | `DoubleStream` |

Ví dụ tính tổng của một số phép đo, mỗi nhóm có 0–n giá trị `int`:

~~~java
import java.util.List;

public class SensorSum {
    public static void main(String[] args) {
        List<List<Integer>> batches = List.of(
            List.of(4, 5),
            List.of(),
            List.of(10, 2)
        );

        int sum = batches.stream()
            .mapMultiToInt((batch, out) -> {
                for (int value : batch) {
                    out.accept(value);
                }
            })
            .sum();

        System.out.println(sum); // 21
    }
}
~~~

`mapMultiToInt` tạo `IntStream`, nên `sum()` hoạt động trực tiếp trên `int`, tránh việc tạo thêm một `Stream<Integer>` đầu ra để rồi mới `mapToInt`.

Với đơn giá kiểu `long`, có thể tạo các khoản tiền theo số lượng và tính tổng:

~~~java
record Purchase(long unitPrice, int quantity) {}

List<Purchase> purchases = List.of(
    new Purchase(20_000L, 2),
    new Purchase(15_000L, 1)
);

long total = purchases.stream()
    .mapMultiToLong((purchase, out) -> {
        for (int i = 0; i < purchase.quantity(); i++) {
            out.accept(purchase.unitPrice());
        }
    })
    .sum();

System.out.println(total); // 55000
~~~

Nếu muốn tổng tiền mà không cần từng dòng đơn vị, `mapToLong(p -> p.unitPrice() * p.quantity()).sum()` sẽ đơn giản và hiệu quả hơn. Với giá trị tiền thực tế, cần kiểm soát tràn số và quy tắc làm tròn; ví dụ chỉ minh họa API, không thay thế thiết kế tính tiền.

Với số đo `double`:

~~~java
List<List<Double>> readings = List.of(
    List.of(1.5, 2.5),
    List.of(),
    List.of(3.0)
);

double total = readings.stream()
    .mapMultiToDouble((batch, out) -> batch.forEach(out::accept))
    .sum();

System.out.println(total); // 7.0
~~~

### Phân biệt với `IntStream.mapMulti`

`Stream<T>.mapMultiToInt` biến **Stream tham chiếu** thành `IntStream`. Nếu đầu vào vốn đã là `IntStream`, ta dùng `IntStream.mapMulti` với hai tham số kiểu primitive, không cần chuyển sang `Stream<Integer>`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> doubledPairs = IntStream.rangeClosed(1, 3)
    .mapMulti((number, out) -> {
        out.accept(number);
        out.accept(number * 10);
    })
    .boxed()
    .toList();

System.out.println(doubledPairs); // [1, 10, 2, 20, 3, 30]
~~~

Các primitive stream `LongStream` và `DoubleStream` cũng có dạng `mapMulti` tương ứng. Tùy thao tác cần thực hiện, chọn đúng loại Stream sẽ giúp tránh boxing không cần thiết.

## 8. Pipeline lazy, thứ tự và xử lý song song

`mapMulti` là **stateless intermediate operation** theo hợp đồng của Stream API: phép ánh xạ nên độc lập giữa các phần tử, không sửa nguồn dữ liệu đang duyệt và không dựa vào trạng thái mutable dùng chung.

### 8.1. Lambda chỉ chạy khi có terminal operation

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(1, 2, 3).stream()
    .<Integer>mapMulti((n, out) -> {
        System.out.println("Xử lý " + n);
        out.accept(n * 2);
    });

// Chưa có terminal operation nên chưa cần xử lý các phần tử.
List<Integer> result = pipeline.toList(); // [2, 4, 6]
~~~

Đoạn `println` dùng để **minh họa quan sát khi chạy**, không phải cam kết mọi intermediate operation đều gọi callback đúng một lần cho mọi phần tử. Stream có thể tối ưu hóa các bước không ảnh hưởng kết quả terminal hoặc dừng sớm ở terminal dạng short-circuit. Không dùng tác dụng phụ trong `mapMulti` để cập nhật nghiệp vụ bắt buộc.

### 8.2. Phát nhiều giá trị và encounter order

Với nguồn có thứ tự như `List`, kết quả của pipeline tuần tự giữ thứ tự các phần tử đầu vào; trong một lần gọi mapper, các kết quả được đưa xuống Consumer theo thứ tự gọi `accept`:

~~~java
List<String> output = List.of("A", "B").stream()
    .<String>mapMulti((letter, out) -> {
        out.accept(letter + "1");
        out.accept(letter + "2");
    })
    .toList();

// [A1, A2, B1, B2]
~~~

Không suy ra encounter order từ những nguồn vốn không có thứ tự. Trên parallel stream, `mapMulti` vẫn tham gia pipeline có hợp đồng thứ tự khi nguồn và terminal yêu cầu, nhưng **thời điểm hoặc thread gọi mapper** có thể khác nhau. `forEach` không cam kết thứ tự thực thi hành động trên parallel stream.

### 8.3. Short-circuit không bảo đảm chỉ xử lý đúng số kết quả cần lấy

~~~java
List<Integer> firstThree = List.of(1, 2, 3, 4).stream()
    .<Integer>mapMulti((n, out) -> {
        out.accept(n);
        out.accept(n * 100);
    })
    .limit(3)
    .toList();

// [1, 100, 2]
~~~

`limit(3)` chỉ yêu cầu **ba phần tử đầu ra**, nhưng không bảo đảm callback `mapMulti` được gọi chính xác với bao nhiêu phần tử đầu vào hoặc dừng vòng lặp ngay giữa một callback phát nhiều giá trị. Vì mapper có thể phát nhiều đầu ra trong một lần gọi, hãy giữ vòng lặp bên trong mapper hữu hạn và có chi phí phù hợp; đừng dùng cơ chế này để giả định đã giải quyết bài toán sinh vô hạn phần tử hay điều khiển luồng I/O.

### 8.4. Tránh trạng thái mutable chia sẻ giữa các mapper

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> sideResults = new ArrayList<>();

List<Integer> result = List.of(1, 2, 3).parallelStream()
    .<Integer>mapMulti((n, out) -> {
        sideResults.add(n); // Không an toàn khi nhiều thread ghi ArrayList.
        out.accept(n * 2);
    })
    .toList();
~~~

Giá trị mục tiêu ở đây là `result`; việc ghi `sideResults` làm lambda có tác dụng phụ và có thể gây race condition. Đừng dùng `synchronizedList` hoặc `AtomicInteger` như cách mặc định để biến một phép ánh xạ phụ thuộc state thành đúng hợp đồng; nên thiết kế kết quả bằng operation như `collect`, `groupingBy` hoặc giữ phần xử lý cần thay đổi trạng thái bên ngoài pipeline, tại một bước có kiểm soát.

**Hiệu năng:** `mapMulti` thích hợp cho 0–n kết quả trên mỗi phần tử, nhất là khi mỗi mapper phát ít giá trị. Nhưng nếu mapper tính toán tốn kém, phát lượng dữ liệu lớn, xử lý I/O hoặc tranh chấp state, việc chuyển sang `parallel()` không mặc nhiên nhanh hơn. Hãy đo thời gian, mức cấp phát và bộ nhớ với tập dữ liệu đại diện trước khi tối ưu.

## 9. Các lỗi thường gặp khi dùng `mapMulti`

### Lỗi 1: Dùng `mapMulti` như `map` và quên gọi `accept`

~~~java
List<String> result = List.of("a", "b").stream()
    .<String>mapMulti((value, out) -> {
        value.toUpperCase(); // Không phát kết quả nào.
    })
    .toList();

// result == []
~~~

Để phát giá trị, phải gọi `out.accept(value.toUpperCase())`. Nếu luôn phát đúng một giá trị, `map(String::toUpperCase)` thường rõ nghĩa hơn.

### Lỗi 2: Coi `mapMulti` như phiên bản có hai tham số của `flatMap`

~~~java
// Không đúng ý tưởng: mapper của mapMulti không trả về Stream.
// .mapMulti((item, out) -> Stream.of(item, item))

// Đúng: phát từng giá trị qua Consumer.
List<String> doubled = List.of("a", "b").stream()
    .<String>mapMulti((item, out) -> {
        out.accept(item);
        out.accept(item);
    })
    .toList();

// [a, a, b, b]
~~~

### Lỗi 3: Trả dữ liệu không kiểm soát kiểu hoặc `null`

Cần xác định rõ kiểu `R` và chỉ phát giá trị hợp lệ cho các bước sau. `Stream` tham chiếu có thể chứa `null` ở một số operation, nhưng nhiều operation hoặc hàm tiếp theo không chấp nhận nó (ví dụ `findFirst` sẽ ném `NullPointerException` nếu phần tử được chọn là `null`). Nếu mục tiêu là **bỏ dữ liệu thiếu**, hãy kiểm tra trước khi `out.accept`:

~~~java
List<String> results = List.of("alpha", " ", "beta").stream()
    .<String>mapMulti((value, out) -> {
        String cleaned = value.strip();
        if (!cleaned.isEmpty()) {
            out.accept(cleaned);
        }
    })
    .toList();

// [alpha, beta]
~~~

Nếu nguồn có thể chứa `null`, phải bảo vệ lời gọi `strip()` tương ứng. `List.of(...)` không chấp nhận phần tử `null`, nhưng một collection khác hoặc API ngoài có thể cung cấp giá trị đó.

### Lỗi 4: Dùng `mapMulti` cho biến đổi có trạng thái giữa các phần tử

Một yêu cầu như đánh số tuần tự tất cả phần tử, chia lô theo kích thước cố định, giữ cửa sổ trượt hoặc xây dựng bộ đếm dùng chung **không nên** được triển khai bằng việc tăng một biến mutable bên ngoài `mapMulti`. Điều này phá vỡ giả định stateless, khó bảo toàn khi chạy song song và ảnh hưởng tính đúng đắn.

Tùy mục tiêu, hãy cân nhắc `IntStream.range(...)` để lấy chỉ số, collector đúng hợp đồng, hoặc cơ chế xử lý trạng thái chuyên dụng. **Stream Gatherers** (API chuẩn từ Java 24) cung cấp các công cụ khác cho một số phép biến đổi có trạng thái hoặc tích hợp nhiều phần tử, nhưng không thay đổi ý nghĩa của `mapMulti`: mỗi mapper xử lý phần tử hiện tại và phát các kết quả tương ứng.

### Lỗi 5: Phát một lượng dữ liệu quá lớn chỉ để tính một đại lượng

~~~java
// Không cần nở số lượng sản phẩm thành nhiều dòng chỉ để tính tổng.
// Sử dụng phép tính trực tiếp:
long totalUnits = lines.stream()
    .mapToLong(OrderLine::quantity)
    .sum();
~~~

Ví dụ dùng lại `OrderLine` và `lines` trong mục 6. `mapMulti` giải quyết việc tạo nhiều giá trị, còn `mapToLong` phù hợp hơn khi dữ liệu cuối cùng chỉ là một tổng.

## 10. Tiêu chí chọn `mapMulti` trong thực tế

| Bài toán | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Một phần tử luôn thành một giá trị khác | `map` | Gọn và diễn đạt đúng phép biến đổi 1–1. |
| Giữ/bỏ phần tử mà không đổi kiểu | `filter` | Điều kiện được thể hiện trực tiếp. |
| Mapper đã trả Stream hoặc có sẵn `List::stream` | `flatMap` | Dễ đọc khi cần làm phẳng nguồn con. |
| 0–n giá trị được phát qua vòng lặp nhỏ | `mapMulti` | Tránh phải tự tạo Stream con ở mỗi input. |
| 0–n giá trị primitive từ Stream tham chiếu | `mapMultiToInt/Long/Double` | Thuận tiện cho `sum`, `average`, `summaryStatistics`. |
| Cần trạng thái xuyên suốt nhiều phần tử | Collector, phép toán chuyên dụng, Gatherer phù hợp | Bảo toàn hợp đồng của phép toán có trạng thái. |
| Chỉ cần tổng/đếm thay vì nở nhiều kết quả | `mapToLong`, `count`, `sum`, `reduce` | Tránh tạo các phần tử không cần thiết. |

## 11. Câu hỏi tự kiểm tra

1. **`mapMulti` khác `map` ở điểm nào?** `map` luôn sinh một kết quả cho mỗi input; `mapMulti` có thể sinh 0, 1 hoặc nhiều kết quả bằng những lần gọi `accept`.
2. **Vì sao không phải trả Stream trong lambda của `mapMulti`?** Mapper nhận Consumer đầu ra; mỗi lần gọi `out.accept(...)` sẽ phát một phần tử vào pipeline.
3. **Khi nào `flatMap` thường rõ hơn `mapMulti`?** Khi đã có một phương thức trả Stream con, chẳng hạn `List::stream` hoặc `Optional::stream`.
4. **Phép nào phù hợp để phát nhiều `int` từ một `Stream<Order>`?** `mapMultiToInt`, vì kết quả là `IntStream`.
5. **Vì sao đôi khi viết `.<String>mapMulti(...)`?** Để chỉ rõ kiểu `R` trong trường hợp trình biên dịch không suy luận đủ kiểu từ lambda và chuỗi phương thức.
6. **Có nên sửa một `ArrayList` dùng chung trong callback của parallel stream?** Không; đây là mutation chung không an toàn và phá vỡ hợp đồng stateless.
7. **`limit(3)` sau `mapMulti` có bảo đảm chỉ xử lý đúng ba giá trị trong mapper không?** Không; terminal và tối ưu hóa có thể chỉ yêu cầu một phần đầu ra, còn mapper có thể phát nhiều giá trị trong một lời gọi.
8. **Nếu chỉ cần tổng số lượng sản phẩm, có nên nhân bản SKU theo số lượng với `mapMulti` không?** Thường không; `mapToLong(...).sum()` diễn đạt trực tiếp và tránh sinh dữ liệu trung gian.

**Ghi nhớ:** `mapMulti` là phép ánh xạ **một đầu vào sang 0–n đầu ra** trong Java Stream API. Hãy gọi `out.accept(...)` đúng số lần cần phát kết quả, chọn biến thể primitive nếu phù hợp, giữ mapper không trạng thái và không can thiệp nguồn, rồi dùng terminal operation để nhận kết quả. Khi ứng dụng các nguyên tắc này, pipeline vừa dễ đọc vừa có thể tận dụng cơ chế lazy và tối ưu hóa của Stream.
