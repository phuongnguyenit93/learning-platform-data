# collect() và tách thao tác tích lũy khỏi Stream pipeline (Java 8)

Trong nhóm **Collector cơ bản**, mục tiêu của bài này là hiểu rõ **Stream mô tả cách xử lý phần tử** còn **`collect(...)` quyết định cách tích lũy kết quả**. Tách hai trách nhiệm giúp code dễ đọc, tránh tác dụng phụ trong `map`/`filter`, dễ thay đổi kiểu kết quả và an toàn hơn khi xử lý song song. Các API trình bày ở đây đã có từ Java 8 và **vẫn được dùng trên các JDK hiện hành**.

## 1. Một pipeline có hai phần trách nhiệm

Xét mẫu tổng quát:

```java
// Minh họa cấu trúc: source, transform và collector do ứng dụng cung cấp.
Result result = source.stream()    // Tạo Stream từ nguồn
    .filter(predicate)             // Chọn phần tử
    .map(mapper)                   // Biến đổi phần tử
    .collect(collector);           // Tích lũy, tạo kết quả cuối cùng
```

Đoạn trên **chỉ là sơ đồ**, không phải chương trình Java độc lập: `Result`, `source`, `predicate`, `mapper` và `collector` là tên đại diện.

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **Nguồn** | `List`, `Set`, mảng, một nguồn dữ liệu khác… | Stream duyệt nguồn; bản thân Stream không phải tập hợp lưu toàn bộ kết quả |
| **Thao tác trung gian** | `filter`, `map`, `flatMap`, `distinct`, `sorted`… | Trả về Stream mới; thường *lazy*, chỉ thực thi khi terminal operation yêu cầu |
| **Terminal `collect`** | Tiêu thụ Stream và tạo `List`, `Set`, `Map`, chuỗi hoặc thống kê… | Là điểm kết thúc pipeline; không thể tiếp tục sử dụng chính Stream đã tiêu thụ |
| **Collector** | Quy định cách tích lũy phần tử vào kết quả | Thư viện `java.util.stream.Collectors` cung cấp các công thức có sẵn |

Cách nhìn dễ hiểu:

```text
Nguồn dữ liệu
    │
    ├── filter: giữ những phần tử đáp ứng điều kiện
    ├── map:    biến đổi từng phần tử
    ├── ...     các bước xử lý tiếp theo
    │
    └── collect(Collector)  ← điểm tích lũy
          │
          ├── List / Set
          ├── Map / nhóm và đếm
          └── String / kết quả tổng hợp khác
```

**Tách trách nhiệm** không nhất thiết phải tách thành nhiều phương thức hoặc nhiều dòng lệnh. Ý chính là tránh nhét việc cập nhật một bộ chứa bên ngoài vào giữa `filter`/`map`. Pipeline tạo phần tử kết quả; collector nhận nhiệm vụ thu chúng thành một kết quả có cấu trúc.

Ví dụ lựa chọn tốt:

```java
// Đoạn minh họa trong một phương thức có sẵn biến names.
List<String> cleaned = names.stream()
    .filter(Objects::nonNull)
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toList());
```

Ở đây `filter` và `map` **không sửa** danh sách `cleaned`; danh sách chỉ được tạo ở terminal `collect`. Khi chưa gọi terminal operation, các bước trung gian thường chưa duyệt phần tử nào. Một phép `collect` bình thường sẽ duyệt những phần tử mà pipeline phát ra và tạo kết quả tương ứng.

## 2. Phân biệt collect, Collector và Collectors

Ba tên rất dễ nhầm nhưng khác nhau:

- **`Stream.collect(...)`** là **terminal operation** thực hiện quá trình tích lũy.
- **`Collector<T, A, R>`** là mô tả cách thu các phần tử kiểu `T`, dùng trạng thái tích lũy kiểu `A` để tạo kết quả kiểu `R`. Hai kiểu `A` và `R` có thể bằng hoặc khác nhau.
- **`Collectors`** là lớp tiện ích có các factory method như `toList()`, `toSet()`, `joining()`, `toMap()`, `groupingBy()`, `counting()` để xây dựng đối tượng `Collector`.

Cú pháp phổ biến:

```java
// Ví dụ trong ngữ cảnh có sẵn List<String> names.
List<String> result = names.stream()
    .collect(Collectors.toList());
```

**Chú ý hai cặp dấu ngoặc:** `Collectors.toList()` tạo collector; `collect(...)` dùng collector đó để tích lũy các phần tử.

Java 8 có **hai overload** quan trọng:

```java
// (1) Một Collector định nghĩa quy tắc tích lũy:
<R, A> R collect(Collector<? super T, A, R> collector)

// (2) Ba hàm riêng cho kết quả tích lũy có thể thay đổi:
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)
```

Hai chữ ký trên là **trích dạng API để học**, không phải lệnh có thể đặt trực tiếp vào thân `main`. Cách thứ nhất thường nên dùng khi có collector chuẩn. Cách thứ hai cho phép tự nêu cách tạo bộ chứa, thêm phần tử và ghép bộ chứa từng phần.

## 3. Ví dụ chạy được: giữ nguyên pipeline, thay cách thu kết quả

Nhiệm vụ: đọc danh sách tên, bỏ phần tử null, bỏ khoảng trắng đầu/cuối, loại chuỗi trống. Từ cùng **một quy tắc biến đổi**, xuất ra ba loại kết quả:

1. Danh sách giữ phần tử trùng.
2. Tập hợp không trùng, theo thứ tự gặp.
3. Một chuỗi ghép tên bằng dấu phẩy.

Tệp **`CollectorFlowDemo.java`** (Java 8 trở lên):

```java
import java.util.*;
import java.util.stream.*;

public class CollectorFlowDemo {
    // Mỗi lời gọi tạo MỘT Stream mới từ nguồn.
    static Stream<String> normalized(List<String> source) {
        return source.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty());
    }

    public static void main(String[] args) {
        List<String> raw =
            Arrays.asList(" Lan ", "An", null, " Lan ", " ", "Minh");

        List<String> all = normalized(raw)
            .collect(Collectors.toList());

        Set<String> unique = normalized(raw)
            .collect(Collectors.toCollection(LinkedHashSet::new));

        String joined = normalized(raw)
            .collect(Collectors.joining(", "));

        System.out.println("list=" + all);
        System.out.println("unique=" + unique);
        System.out.println("joined=" + joined);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CollectorFlowDemo.java
java CollectorFlowDemo
```

Kết quả:

```text
list=[Lan, An, Lan, Minh]
unique=[Lan, An, Minh]
joined=Lan, An, Lan, Minh
```

**Phân tích đúng vai trò:**

- `normalized(...)` định nghĩa **quy tắc biến đổi**, trả về `Stream<String>`; nó chưa tạo danh sách kết quả.
- `Collectors.toList()` giữ các phần tử trùng và duy trì thứ tự gặp nếu nguồn có encounter order như `List` ở ví dụ này.
- `Collectors.toCollection(LinkedHashSet::new)` yêu cầu rõ kiểu tập hợp muốn tạo. `LinkedHashSet` giữ thứ tự chèn; cách này hữu ích nếu đầu ra vừa cần loại trùng vừa cần thứ tự.
- `Collectors.joining(", ")` ghép các chuỗi đã được chuẩn hóa; các bước xử lý đầu vào không cần biết kết quả cuối là chuỗi.
- **Không tái sử dụng một đối tượng `Stream` sau `collect`**. Mã gọi `normalized(raw)` ba lần để tạo ba stream độc lập từ cùng danh sách `raw`.

Không nên thay ba lời gọi bằng:

```java
// Ví dụ SAI: cùng một Stream đã bị tiêu thụ bởi collect thứ nhất.
Stream<String> s = normalized(raw);
List<String> list = s.collect(Collectors.toList());
long count = s.count(); // IllegalStateException
```

Cách sửa là tạo Stream mới từ nguồn, hoặc thu một kết quả rồi xử lý trên kết quả đó nếu phù hợp. Bản thân `List` nguồn vẫn có thể được dùng lại; giới hạn sử dụng một lần áp dụng cho **đối tượng Stream**, không phải danh sách.

**Về `Collectors.toList()`:** hợp đồng API không bảo đảm một loại `List` cụ thể, khả năng chỉnh sửa, tính thread-safe hay serializability của danh sách trả về. Nếu cần chính xác một `ArrayList` có thể sửa, dùng `Collectors.toCollection(ArrayList::new)`. Trên JDK 16+ còn có `Stream.toList()` với kết quả không thể sửa; phương thức đó **không thuộc Java 8**, nên không dùng trong các ví dụ Java 8 ở đây.

## 4. Chọn collector theo kết quả muốn nhận

| Kết quả mong muốn | Collector Java 8 | Lưu ý |
| --- | --- | --- |
| Danh sách phần tử | `Collectors.toList()` | Không cam kết kiểu hoặc khả năng sửa danh sách cụ thể |
| Một loại collection do mình chọn | `Collectors.toCollection(ArrayList::new)` | Cho phép nêu factory rõ ràng; cũng có thể dùng `LinkedHashSet::new` |
| Tập hợp các phần tử không trùng | `Collectors.toSet()` | Không cam kết thứ tự duyệt hoặc kiểu `Set` |
| Chuỗi từ `CharSequence` | `Collectors.joining(", ")` | Có thể chọn delimiter, prefix, suffix theo overload |
| Map từ khóa tới giá trị | `Collectors.toMap(keyFn, valueFn)` | Khóa trùng sẽ gây lỗi nếu không có hàm giải quyết xung đột |
| Map có xử lý khóa trùng | `Collectors.toMap(keyFn, valueFn, mergeFn)` | Merge phải có quy tắc nghiệp vụ rõ |
| Nhóm phần tử theo khóa | `Collectors.groupingBy(classifier)` | Trả về map các nhóm; không bảo đảm loại/thứ tự Map nếu không chỉ định |
| Nhóm rồi thống kê | `Collectors.groupingBy(classifier, Collectors.counting())` | Downstream collector xử lý từng nhóm |
| Chia theo điều kiện đúng/sai | `Collectors.partitioningBy(predicate)` | Hai nhóm khóa Boolean; khác grouping theo nhiều khóa |
| Đếm hoặc tổng hợp số | `Collectors.counting()`, `Collectors.summingInt(mapper)` | Trả kết quả tổng hợp; có thể dùng làm downstream collector |

Lựa chọn dựa vào **hợp đồng kết quả**, không chọn `toList()` chỉ vì nó phổ biến. Nếu tầng gọi cần map, đừng thu danh sách rồi lặp tay để đắp vào map. Nếu chỉ cần số phần tử, `stream.count()` rõ ràng hơn thu toàn bộ danh sách rồi gọi `size()`.

## 5. Ví dụ chạy được: groupingBy và toMap xử lý khóa trùng

Tệp **`CollectorVariantsDemo.java`** minh họa hai kết quả khác nhau từ cùng một nguồn:

- Đếm số từ theo **độ dài**, sắp thứ tự các khóa độ dài.
- Đếm số lần xuất hiện của **từng từ**, giữ thứ tự xuất hiện đầu tiên.

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class CollectorVariantsDemo {
    public static void main(String[] args) {
        List<String> words =
            Arrays.asList("an", "ba", "lam", "minh", "mai", "bao", "an");

        Map<Integer, Long> byLength = words.stream()
            .collect(Collectors.groupingBy(
                String::length,
                TreeMap::new,
                Collectors.counting()
            ));

        Map<String, Long> frequency = words.stream()
            .collect(Collectors.toMap(
                Function.identity(),
                w -> 1L,
                Long::sum,
                LinkedHashMap::new
            ));

        System.out.println("byLength=" + byLength);
        System.out.println("frequency=" + frequency);
    }
}
```

```bash
javac -encoding UTF-8 CollectorVariantsDemo.java
java CollectorVariantsDemo
```

```text
byLength={2=3, 3=3, 4=1}
frequency={an=2, ba=1, lam=1, minh=1, mai=1, bao=1}
```

Phân tích:

- `groupingBy(String::length, TreeMap::new, counting())` tạo nhóm theo độ dài và dùng **downstream collector** để đếm; kết quả `TreeMap` có khóa số tăng dần.
- `toMap(Function.identity(), w -> 1L, Long::sum, LinkedHashMap::new)` đặt chính chuỗi làm khóa, gán giá trị ban đầu bằng 1, cộng dồn khi khóa trùng, giữ thứ tự chèn khóa nhờ `LinkedHashMap`.
- `Long::sum` là quy tắc xung đột của các giá trị ứng với cùng khóa. Nếu bỏ quy tắc này và dùng overload `toMap(keyFn, valueFn)`, phần tử `"an"` lặp sẽ khiến thao tác ném `IllegalStateException`.
- Nếu không cần thứ tự khóa, không nhất thiết phải cấp `TreeMap` hoặc `LinkedHashMap`; nếu **cần** thứ tự, hãy nêu rõ kiểu Map và giả định về thứ tự của nguồn.

Các collector lồng nhau như `groupingBy(..., counting())` vẫn là **một terminal collect**; sau đó không cần chạy thêm một vòng lặp bên ngoài để đếm từng nhóm. Dữ liệu từ ngoài hệ thống cần được chuẩn hóa/kiểm tra trước bước nhóm; một số classifier không chấp nhận khóa null.

## 6. Bên trong một phép tích lũy: supplier, accumulator, combiner, finisher

Một `Collector` mô tả việc biến nhiều phần tử thành kết quả thông qua các vai trò sau:

| Vai trò | Mục đích | Ví dụ khi thu vào danh sách |
| --- | --- | --- |
| **Supplier** | Tạo bộ chứa kết quả ban đầu/trạng thái tích lũy mới | `ArrayList::new` |
| **Accumulator** | Thêm **một phần tử** đầu vào vào bộ chứa | `List::add` |
| **Combiner** | Ghép **hai bộ chứa kết quả từng phần** thành một | `List::addAll` |
| **Finisher** | Chuyển trạng thái tích lũy thành kết quả trả về nếu cần | Có thể là identity, tức trả bộ chứa trực tiếp |

Với collector có sẵn, bạn thường không cần gọi các hàm này. Stream framework quản lý quá trình tích lũy, kể cả việc chia và hợp nhất kết quả khi chạy song song. Không nên giả định `combiner` luôn được gọi trong stream tuần tự, hoặc tự dựa vào thứ tự gọi accumulator để triển khai side effect ra bên ngoài.

Ví dụ dễ hình dung ở mức khái niệm:

```text
Nguồn:                  [a, b, c, d]

supplier:               tạo collection rỗng
accumulator(a):          thêm a vào collection
accumulator(b):          thêm b vào collection
...                      thực hiện theo chiến lược Stream
combiner (nếu cần):     nối kết quả các phần
finisher (nếu cần):     đổi trạng thái tạm thành kiểu kết quả

collect trả về:          collection hoặc kết quả tổng hợp
```

Với stream song song và collector **không khai báo CONCURRENT**, framework có thể tạo những bộ chứa riêng cho các phần, sau đó kết hợp chúng. Điều này khác căn bản với việc mọi worker tùy ý ghi vào **cùng một `ArrayList` bên ngoài**.

### Ví dụ Java 8: collect ba tham số

Tệp **`ThreeArgCollectDemo.java`**:

```java
import java.util.*;

public class ThreeArgCollectDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList("red", "blue", "green");

        ArrayList<String> result = source.stream()
            .map(s -> s.toUpperCase(Locale.ROOT))
            .collect(
                ArrayList::new,  // supplier: tạo list mới
                ArrayList::add,  // accumulator: thêm một phần tử
                ArrayList::addAll // combiner: ghép hai list
            );

        System.out.println(result);
    }
}
```

```bash
javac -encoding UTF-8 ThreeArgCollectDemo.java
java ThreeArgCollectDemo
```

```text
[RED, BLUE, GREEN]
```

Hai cách viết sau tương đương về **mục tiêu thu vào ArrayList** trong ví dụ này:

```java
// Có sẵn một Stream<String> stream chưa từng bị tiêu thụ:
ArrayList<String> a = stream.collect(
    ArrayList::new, ArrayList::add, ArrayList::addAll);

// Trong lời gọi riêng, tạo stream mới từ cùng nguồn:
ArrayList<String> b = source.stream()
    .collect(Collectors.toCollection(ArrayList::new));
```

Đây là ví dụ minh họa, không phải mã độc lập có thể chạy nếu chưa khai báo `stream` và `source`. Trong ứng dụng, **ưu tiên collector chuẩn** khi nó đã diễn tả đúng hành vi; dùng overload ba tham số khi muốn điều khiển cách tích lũy riêng một cách rõ ràng.

### Hai nguyên tắc cho combiner đúng

1. **Cộng dồn và ghép phần phải nhất quán**: kết quả thu toàn bộ dữ liệu phải tương đương về ý nghĩa với việc thu từng phần rồi ghép lại. Tránh combiner làm mất phần tử, nhân đôi dữ liệu hoặc thay đổi phép tính.
2. **Không chia sẻ bộ chứa ngoài pipeline**: supplier phải cung cấp bộ chứa mới khi được gọi; accumulator sửa bộ chứa được giao cho nó, không lén sửa một singleton hay biến toàn cục.

Khi viết `Collector.of(...)` tùy biến hoặc collector chạy song song, còn phải bảo đảm các ràng buộc về **identity, associativity và characteristics** theo hợp đồng `Collector`. Các đặc tính `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` chỉ được khai báo nếu thật sự đúng; gắn nhãn sai có thể làm thay đổi hành vi khi chạy song song. Trong bài Collector cơ bản, dùng factory method có sẵn là lựa chọn đầu tiên.

## 7. Tích lũy bằng collect khác gì reduce?

Cả `reduce` và `collect` đều là terminal operation, nhưng mô hình sử dụng khác nhau:

| Tiêu chí | `reduce` | `collect` |
| --- | --- | --- |
| Ý tưởng | Kết hợp các giá trị theo một phép giảm (*reduction*) | Tích lũy có quản lý trạng thái, thường là *mutable reduction* |
| Ví dụ thường gặp | Tổng, tích, min/max, phép kết hợp bất biến | List, Set, Map, nhóm, ghép chuỗi, nhiều trường thống kê |
| Trạng thái | Hàm giảm nên không sửa các đối tượng tích lũy dùng chung | Collector được phép sửa **bộ chứa riêng** do supplier cấp |
| Khả năng song song | Phép kết hợp phải thỏa hợp đồng kết hợp phù hợp | Accumulator/combiner phải tuân thủ hợp đồng Collector |
| Điểm chọn | Chỉ cần phép kết hợp rõ ràng, không cần bộ chứa có thể sửa | Cần tích lũy vào cấu trúc dữ liệu hoặc collector có sẵn |

Ví dụ minh họa trong phương thức có `List<Integer> amounts`:

```java
int totalWithReduce = amounts.stream()
    .reduce(0, Integer::sum);

int totalWithPrimitiveStream = amounts.stream()
    .mapToInt(Integer::intValue)
    .sum();

List<Integer> copy = amounts.stream()
    .collect(Collectors.toList());
```

Hai dòng đầu tính tổng; dòng cuối **lưu lại các phần tử**. Nếu chỉ cần tổng các `int`, `mapToInt(...).sum()` thường trực tiếp hơn việc tạo danh sách tạm để lặp cộng sau đó.

**Không** dùng `reduce` với cùng một đối tượng `StringBuilder`/`ArrayList` bị mutate làm identity trong phép giảm song song: mutable identity có thể vi phạm giả định của phép reduce. Dùng `collect`/collector phù hợp với mutable result.

## 8. Vì sao không nên tích lũy bằng forEach hoặc peek vào biến ngoài?

Ví dụ có vấn đề:

```java
// Ví dụ phản diện, KHÔNG chạy để xây dựng kết quả.
List<String> output = new ArrayList<>();
source.parallelStream()
    .map(String::trim)
    .forEach(output::add); // Ghi đồng thời vào ArrayList không thread-safe.
```

Vấn đề là các luồng có thể cùng lúc sửa `output` mà không được đồng bộ; có thể mất dữ liệu, sai thứ tự, kết quả thiếu ổn định. Ngay cả khi chạy tuần tự, việc nhồi kết quả qua `forEach` khiến logic thu gom phân tán, không diễn tả trực tiếp mục đích và khó thay đổi.

Mẫu phù hợp:

```java
// source là List<String> không chứa null trong ví dụ này.
List<String> output = source.parallelStream()
    .map(String::trim)
    .collect(Collectors.toList());
```

Collector chuẩn được thiết kế để phối hợp với cơ chế tích lũy của Stream. **Điều này không đồng nghĩa rằng `ArrayList` tự nhiên trở nên thread-safe**: framework kiểm soát trạng thái tích lũy phù hợp hợp đồng của collector.

Tương tự, đừng dùng `peek(output::add)` làm cách bắt buộc để tạo kết quả. `peek` là thao tác trung gian, có thể không chạy nếu không có terminal operation; đặc biệt các tối ưu hóa và terminal operation dừng sớm có thể khiến không phải phần tử nào cũng đi qua action như bạn kỳ vọng. `peek` chỉ nên hỗ trợ quan sát/debug trong phạm vi phù hợp, không làm nguồn sự thật của kết quả.

**Nguyên tắc thực dụng:** `filter`/`map` nên diễn tả biến đổi không có side effect; `collect` chịu trách nhiệm thu kết quả. Nếu cần ghi log, gửi sự kiện hoặc lưu cơ sở dữ liệu, nên đặt tác vụ bên ngoài phép biến đổi thuần hoặc quản lý side effect có chủ đích với hợp đồng rõ ràng.

## 9. Thứ tự, trùng lặp, null và tính ổn định của kết quả

Việc chọn collector ảnh hưởng đến ý nghĩa kết quả. Trước khi thu, cần quyết định:

**Có giữ thứ tự không?** Nguồn như `List` có encounter order; `Collectors.toList()` trên ordered stream bảo toàn encounter order. Nhưng `Collectors.toSet()` không cam kết thứ tự duyệt của tập hợp. Nếu bắt buộc loại trùng và giữ thứ tự, chọn `Collectors.toCollection(LinkedHashSet::new)` như ví dụ đầu.

**Có cho phép phần tử trùng không?** `toList()` giữ trùng; `toSet()` loại trùng dựa trên `equals` và `hashCode`; `toMap()` cần chính sách khi khóa trùng. Việc loại trùng đôi khi làm mất thông tin nghiệp vụ (ví dụ hai lần nhập tên giống nhau vẫn là hai bản ghi).

**Có thể có null không?** `Stream` không mặc định bỏ null. Trước khi đưa dữ liệu vào collector, nên xác định null có ý nghĩa gì và lọc/chuyển đổi theo hợp đồng. Các collector khác nhau không có cùng cách xử lý null; đặc biệt `toMap`/`groupingBy` có thể không chấp nhận một số khóa hoặc giá trị null. Tránh coi null là giá trị hợp lệ một cách ngầm định.

**Có nguồn quá lớn không?** Thu vào `List`/`Map` tạo kết quả lưu trong bộ nhớ. Nếu dữ liệu quá lớn, không chọn collect-to-list chỉ để đọc hết rồi bỏ phần lớn phần tử: cân nhắc lọc sớm, giới hạn khối lượng, xử lý theo lô hoặc luồng tiêu thụ khác có kiểm soát tài nguyên. Đừng tạo stream vô hạn rồi `collect(toList())` mà không có giới hạn.

**Có cần chỉnh sửa kết quả không?** Không suy luận tính mutable từ `Collectors.toList()`. Khi hợp đồng yêu cầu collection cụ thể, dùng `toCollection(factory)`; khi muốn bảo vệ dữ liệu không đổi, quyết định bất biến hóa ở ranh giới API phù hợp.

## 10. Quy trình thiết kế collector cho một bài toán thực tế

Giả sử một hệ thống có danh sách chuỗi tên sản phẩm đến từ API. Trách nhiệm nên được tổ chức như sau:

1. **Định nghĩa nguồn và hợp đồng:** đầu vào có thể null không; thứ tự đầu vào có quan trọng không; trùng lặp có được phép không.
2. **Viết phép biến đổi độc lập:** lọc dữ liệu không hợp lệ, chuẩn hóa giá trị, ánh xạ sang kiểu domain. Tránh sửa collection ngoài trong `map`.
3. **Chọn hình dạng đầu ra:** nếu hiển thị danh sách, dùng `toList`; nếu cần unique, dùng `toCollection(LinkedHashSet::new)`; nếu báo cáo số lượng, dùng `groupingBy(..., counting())`.
4. **Chọn cơ chế giải quyết xung đột:** nhất là `toMap`, không bỏ mặc khóa trùng nếu dữ liệu có thể trùng. Nếu cần thứ tự, chọn kiểu Map phù hợp.
5. **Gọi một terminal operation cho một Stream:** kiểm tra đúng số phần tử, thứ tự, các trường hợp null/chuỗi trống và tính hợp lệ của kết quả.
6. **Chỉ dùng parallel nếu có lý do:** dữ liệu, chi phí biến đổi và yêu cầu hiệu năng cần chứng minh lợi ích; mỗi helper/collector phải tuân thủ hợp đồng khi chạy song song.

Một dấu hiệu thiết kế tốt là bạn có thể **giữ nguyên đoạn `filter`/`map` nhưng thay `collect(Collectors.toList())` bằng `collect(Collectors.joining(", "))`** khi yêu cầu đầu ra thay đổi và kiểu phần tử tương thích.

## 11. Lỗi phổ biến và hướng khắc phục

| Lỗi | Biểu hiện/hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `map` với `collect` | Dùng `map` để sửa danh sách ngoài | Giữ mapper thuần; để collector tạo kết quả |
| Quên terminal operation | Pipeline không được thực thi như mong đợi | Thêm terminal phù hợp khi thực sự cần kết quả |
| Tái sử dụng Stream | `IllegalStateException` | Tạo Stream mới từ nguồn hoặc từ kết quả đã thu |
| Ghi `forEach(list::add)` với `parallelStream` | Data race, kết quả không ổn định | Dùng `collect` và collector phù hợp |
| Dùng `toSet()` nhưng trông đợi thứ tự | Thứ tự thay đổi theo implementation | Dùng `toCollection(LinkedHashSet::new)` khi cần |
| Dùng `toMap(key,value)` với khóa trùng | `IllegalStateException` | Đặt hàm merge hoặc xác minh tính duy nhất trước |
| Mặc định `toList()` luôn trả ArrayList có thể sửa | Phụ thuộc implementation | `toCollection(ArrayList::new)` nếu cần ArrayList |
| Dùng `reduce` để mutate chung một bộ chứa | Vi phạm hợp đồng, dễ sai khi parallel | Dùng mutable reduction qua `collect` |
| Tạo danh sách trung gian rồi lại nhóm bằng vòng lặp | Tốn bộ nhớ, tăng trách nhiệm mỗi khối code | Ưu tiên `collect(groupingBy(...))` khi phù hợp |
| Dùng collector khi chỉ cần `count()`/`sum()` | Tạo kết quả trung gian không cần thiết | Dùng terminal đơn giản hoặc primitive stream |

## 12. Tự kiểm tra kiến thức

**Câu 1.** `map` có tạo `List` kết quả ngay khi được gọi không?  
**Đáp án:** Không. `map` là thao tác trung gian trả về Stream; việc duyệt phần tử thường do terminal operation như `collect` kích hoạt.

**Câu 2.** Cùng một pipeline chuẩn hóa tên, làm thế nào vừa tạo danh sách có trùng vừa tạo chuỗi ghép tên?  
**Đáp án:** Tạo **hai Stream mới** từ cùng nguồn, dùng lần lượt `collect(Collectors.toList())` và `collect(Collectors.joining(", "))`.

**Câu 3.** Khi nào `Collectors.toCollection(LinkedHashSet::new)` phù hợp hơn `Collectors.toSet()`?  
**Đáp án:** Khi cần loại trùng **và** giữ thứ tự chèn/encounter order trong kết quả cho nguồn có thứ tự.

**Câu 4.** Ba tham số của `collect(supplier, accumulator, combiner)` làm gì?  
**Đáp án:** Tạo bộ chứa mới, thêm phần tử vào bộ chứa và ghép các bộ chứa từng phần.

**Câu 5.** Với các từ `["an", "ba", "an"]`, tại sao `Collectors.toMap(Function.identity(), s -> 1)` gây lỗi?  
**Đáp án:** Khóa `"an"` trùng; overload hai tham số không có hàm merge. Cần chính sách xung đột như `Integer::sum` nếu muốn đếm.

**Câu 6.** Vì sao `parallelStream().forEach(externalArrayList::add)` không phải cách thu kết quả an toàn?  
**Đáp án:** Nhiều luồng ghi đồng thời vào cùng `ArrayList` không được bảo vệ; dùng `collect` để framework quản lý trạng thái tích lũy.

## Tài liệu chuẩn (API còn áp dụng)

- [Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): các terminal `collect`, `reduce`, `count` và thao tác trung gian.
- [Java SE 8 — Collector](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): hợp đồng supplier, accumulator, combiner, finisher, characteristics.
- [Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): `toList`, `toCollection`, `joining`, `toMap`, `groupingBy`, `counting`.
- [Java SE 8 — java.util.stream package](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): quy tắc pipeline, laziness và side effect.

**Ghi nhớ:** pipeline xác định **phần tử được chọn và biến đổi thế nào**; `collect` xác định **chúng được tích lũy thành kết quả gì**. Đưa trách nhiệm tích lũy về terminal operation giúp mã rõ ràng, bớt trạng thái chia sẻ và dễ chọn đầu ra đúng hợp đồng.