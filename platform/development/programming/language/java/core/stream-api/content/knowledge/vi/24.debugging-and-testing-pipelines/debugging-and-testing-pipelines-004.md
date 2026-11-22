# Kiểm thử nguồn rỗng, một phần tử, trùng lặp và null

Trong **Java Stream API**, một pipeline `filter`, `map`, `flatMap`, `distinct`, `reduce` hoặc `collect` có thể chạy đúng với dữ liệu mẫu gồm hàng trăm bản ghi, nhưng lại sai khi chỉ còn **0 phần tử, 1 phần tử, nhiều phần tử trùng nhau hoặc giá trị `null`**. Đây là những trường hợp biên thường làm lộ ra giả định chưa được ghi rõ: “luôn có phần tử đầu tiên”, “mọi trường đều khác null”, “khóa luôn duy nhất” hoặc “trung bình luôn tồn tại”.

Bài học thuộc chương **Gỡ lỗi và kiểm thử pipeline** của mô-đun `JAVA_STREAM_API`. Mục tiêu là thiết kế một bộ kiểm thử có thể tái lập, phân biệt hành vi **được API bảo đảm** với hành vi chỉ tình cờ quan sát được, và kiểm tra kết quả của pipeline thay vì phụ thuộc số lần lambda được gọi.

Đặc biệt, cần học cách xác định **chính sách nghiệp vụ** cho dữ liệu trùng hoặc thiếu. Việc `filter(Objects::nonNull)` chạy không lỗi chưa đủ chứng minh rằng im lặng loại bản ghi là quyết định đúng cho hệ thống thực tế.

## 1. Tạo ma trận kiểm thử trước khi viết assertion

Giả sử cần xử lý danh sách mã sản phẩm thành dạng chuẩn, lọc mã hợp lệ và thống kê theo mã. Hãy kiểm thử ít nhất các tình huống:

| Nhóm đầu vào | Ví dụ | Điều cần xác nhận |
| --- | --- | --- |
| **Nguồn rỗng** | `[]` | Không truy cập phần tử không tồn tại; identity và `Optional` đúng. |
| **Một phần tử hợp lệ** | `[" SKU-01 "]` | Phần tử được chuẩn hóa và giữ đúng một lần. |
| **Một phần tử bị loại** | `["   "]` | Pipeline trả rỗng; không gọi `get(0)` tùy tiện. |
| **Giá trị trùng hoàn toàn** | `["A", "A"]` | Chọn giữ nguyên, `distinct`, đếm hoặc báo lỗi theo yêu cầu. |
| **Trùng sau chuẩn hóa** | `[" a ", "A"]` | Phân biệt hai chuỗi gốc với một khóa chuẩn `"A"`. |
| **Phần tử `null`** | `["A", null]` | Loại, thay thế, từ chối hay giữ `null` có chủ đích. |
| **Trường `null` trong đối tượng** | `Item(null, 2)` | Xử lý riêng trường thiếu, không chỉ `filter` object khác null. |
| **Tất cả phần tử đều bị loại** | `[null, " ", ""]` | Kết quả sau lọc rỗng, dù nguồn gốc không rỗng. |

Một pipeline có thể nhận đầu vào không rỗng nhưng **trở thành rỗng sau `filter`**. Vì thế, kiểm thử nguồn rỗng và kiểm thử **kết quả trung gian rỗng** đều cần thiết.

Nguyên tắc chung: xác định rõ **giá trị mong đợi, ngoại lệ mong đợi hoặc dấu hiệu lỗi nghiệp vụ** cho từng trường hợp. Không chỉ kiểm tra “không ném ngoại lệ” nếu nghiệp vụ cần trả đúng dữ liệu.

## 2. Tạo nguồn kiểm thử đúng cách

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

Stream<String> empty = Stream.empty();
Stream<String> singleton = Stream.of("A");
Stream<String> duplicates = Stream.of("A", "A", "B");

// Arrays.asList có thể chứa phần tử null.
List<String> withNull = Arrays.asList("A", null, "B");
Stream<String> nullableElements = withNull.stream();

// Collections.emptyList cũng tạo nguồn rỗng.
List<String> emptyList = Collections.emptyList();
```

**Không dùng `List.of("A", null)` để tạo nguồn chứa null**: `List.of` (Java 9+) từ chối `null` ngay khi xây danh sách. Nếu mục tiêu là kiểm tra một pipeline nhận phần tử null, hãy chọn nguồn thực sự **cho phép chứa null** như `Arrays.asList` hoặc `Stream.of((String) null)`.

```java
import java.util.stream.Stream;

Stream<String> oneNull = Stream.of((String) null);
System.out.println(oneNull.count()); // 1
```

Ép kiểu `(String) null` giúp thể hiện rõ đây là **một phần tử null**. Tránh viết `Stream.of(null)` trần vì có overload varargs, dễ gây cảnh báo hoặc nhầm ý nghĩa.

### Phân biệt `Stream.empty()` và `Stream.ofNullable`

`Stream.ofNullable(value)` (Java 9+) trả **0 phần tử nếu value là null**, còn `Stream.of((String) null)` tạo **1 phần tử null**:

```java
import java.util.stream.Stream;

String absent = null;

System.out.println(Stream.ofNullable(absent).count());   // 0
System.out.println(Stream.of((String) absent).count());  // 1
System.out.println(Stream.ofNullable("A").count());      // 1
```

Đây là hai hợp đồng khác nhau; không dùng thay thế cho nhau mà không xét yêu cầu. Khi nghiệp vụ phân biệt “có một hàng rỗng” với “không có hàng”, khác biệt `0` và `1` rất quan trọng.

## 3. Nguồn rỗng: `Optional`, identity và phép toán ngắn mạch

Các terminal operation có hành vi khác nhau khi không có phần tử:

| Terminal operation | Với nguồn rỗng | Lưu ý |
| --- | --- | --- |
| `count()` | `0L` | Không cần phần tử để đếm. |
| `IntStream.sum()` | `0` | Tổng rỗng bằng identity của phép cộng. |
| `IntStream.average()` | `OptionalDouble.empty()` | Không có trung bình quan sát được. |
| `IntStream.min()` / `max()` | `OptionalInt.empty()` | Không có min/max. |
| `Stream.findFirst()` / `findAny()` | `Optional.empty()` | Không được gọi `get()` khi chưa có giá trị. |
| `reduce(identity, op)` | Trả `identity` | Identity phải đúng với phép kết hợp. |
| `reduce(op)` | `Optional.empty()` | Không có identity được cung cấp. |
| `anyMatch(p)` | `false` | Không tồn tại phần tử nào thỏa `p`. |
| `allMatch(p)` | `true` | Đúng một cách *vacuous* (không có phản ví dụ). |
| `noneMatch(p)` | `true` | Không có phần tử nào thỏa `p`. |

Ví dụ Java 8+:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

System.out.println(IntStream.empty().sum());      // 0
System.out.println(IntStream.empty().count());    // 0

OptionalInt minimum = IntStream.empty().min();
System.out.println(minimum.isPresent());           // false

System.out.println(Stream.<Integer>empty()
    .anyMatch(n -> n > 0));                        // false
System.out.println(Stream.<Integer>empty()
    .allMatch(n -> n > 0));                        // true
System.out.println(Stream.<Integer>empty()
    .noneMatch(n -> n > 0));                       // true
```

Kết quả `allMatch == true` trên nguồn rỗng không có nghĩa hệ thống đã xác minh được **ít nhất một** bản ghi hợp lệ. Nếu nghiệp vụ yêu cầu *có dữ liệu và tất cả đều đạt*, cần kiểm tra **cả điều kiện không rỗng**:

```java
import java.util.List;

List<Integer> scores = List.of();

boolean atLeastOneAndAllPassed =
    !scores.isEmpty() && scores.stream().allMatch(n -> n >= 60);

System.out.println(atLeastOneAndAllPassed); // false
```

Với nguồn chỉ được tiêu thụ một lần (ví dụ từ I/O), không thể gọi hai terminal operation trên **cùng một stream** để vừa kiểm tra `count()` vừa gọi `allMatch()`. Có thể thiết kế một collector phù hợp hoặc kiểm tra dữ liệu khi nó được thu vào một cấu trúc có thể duyệt lại.

### Không suy ra giá trị đo từ identity

`sum() == 0` của nguồn rỗng là một quy tắc đại số; nó **không** có nghĩa đã quan sát một giá trị bằng 0. Tương tự, `LongSummaryStatistics.getAverage()` trên bộ thống kê rỗng trả `0.0` theo hợp đồng, nhưng báo cáo dữ liệu nên kiểm tra `getCount() == 0` trước khi coi trung bình là một số đo thực tế.

## 4. Nguồn rỗng khi thu thập: `groupingBy` khác `partitioningBy`

`groupingBy` chỉ tạo nhóm khi có phần tử được phân loại, còn `partitioningBy` **luôn** có hai khóa Boolean ngay cả khi nguồn rỗng:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, List<String>> groups = Stream.<String>empty()
    .collect(Collectors.groupingBy(s -> s));

Map<Boolean, List<String>> partitions = Stream.<String>empty()
    .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(groups.isEmpty());             // true
System.out.println(partitions.size());             // 2
System.out.println(partitions.get(true).isEmpty());  // true
System.out.println(partitions.get(false).isEmpty()); // true
```

Test này giúp phát hiện lỗi khi code gọi `groups.get("SKU-01").size()`: nhóm chưa tồn tại thì `get` có thể trả `null`. Với `partitioningBy`, hai giá trị của khóa Boolean luôn tồn tại, nhưng **giá trị downstream ở mỗi nhánh** còn phụ thuộc collector được truyền vào.

## 5. Một phần tử: kiểm tra điểm đầu, điểm cuối và giới hạn

Nguồn chỉ có một phần tử là cách đơn giản nhất để kiểm tra những giả định về “cặp phần tử”, “ít nhất hai bản ghi” và điều kiện biên.

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" sku-01 ")
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .toList();

System.out.println(normalized);          // [SKU-01]
System.out.println(normalized.size());   // 1
System.out.println(normalized.get(0));   // SKU-01
```

Trong ví dụ Java 16+, `Stream.toList()` tạo danh sách **không sửa đổi được**. Nếu cần một danh sách mutable, chọn một collector/supplier thích hợp; đừng mặc định `toList()` giống `new ArrayList<>()`.

Hãy thử ngưỡng đúng bằng giá trị:

```java
import java.util.stream.Stream;

System.out.println(Stream.of(60).filter(n -> n >= 60).count()); // 1
System.out.println(Stream.of(60).filter(n -> n > 60).count());  // 0
```

Đây là lỗi **off-by-one** phổ biến. Với pipeline tạo cửa sổ, nhóm theo cặp hoặc tính sai phân giữa hai phần tử liên tiếp, một phần tử có thể tạo **không kết quả** hoặc một kết quả đặc biệt; phải đọc đúng hợp đồng phép toán thay vì tự suy đoán.

### Tránh truy cập phần tử đầu tiên không an toàn

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<String> first = Stream.<String>empty().findFirst();

System.out.println(first.orElse("KHÔNG CÓ DỮ LIỆU"));
// KHÔNG CÓ DỮ LIỆU

// Tránh gọi first.get() khi Optional có thể rỗng.
```

`Optional` là cách biểu diễn **có hoặc không có phần tử**. Nếu bản thân phần tử đầu tiên có thể là `null`, `findFirst()` còn có trường hợp ném `NullPointerException`, được phân tích ở mục về null.

## 6. Dữ liệu trùng: phải chọn một trong nhiều chính sách

Có ít nhất bốn bài toán khác nhau với các phần tử trùng:

| Yêu cầu | API phù hợp | Kết quả ví dụ `["A","A","B"]` |
| --- | --- | --- |
| Giữ nguyên từng bản ghi | Không loại trùng | `[A, A, B]` |
| Lấy giá trị duy nhất | `distinct()` | `[A, B]` |
| Đếm tần suất | `groupingBy(identity(), counting())` | `A -> 2, B -> 1` |
| Phát hiện lỗi khóa trùng khi tạo map | `toMap(key, value)` không có merger | Ném `IllegalStateException` nếu cùng khóa. |

Ví dụ:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> unique = Stream.of("A", "A", "B", "A")
    .distinct()
    .toList();

Map<String, Long> frequencies = Stream.of("A", "A", "B", "A")
    .collect(Collectors.groupingBy(
        Function.identity(),
        Collectors.counting()
    ));

System.out.println(unique);               // [A, B]
System.out.println(frequencies.get("A")); // 3
System.out.println(frequencies.get("B")); // 1
```

`distinct()` xác định sự trùng lặp theo `Object.equals`. Với một stream có encounter order, phép `distinct` ổn định: nó giữ **phần tử đầu tiên** trong các phần tử bằng nhau. Không được suy ra thứ tự tương tự cho nguồn vốn không có encounter order; xử lý song song có thể phải giữ thêm trạng thái và chi phí để bảo đảm tính ổn định.

### Trùng sau chuẩn hóa thường nguy hiểm hơn trùng nguyên văn

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

List<String> uniqueCodes = Stream.of(" sku-01 ", "SKU-01", "sku-02")
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .distinct()
    .toList();

System.out.println(uniqueCodes); // [SKU-01, SKU-02]
```

Nếu đặt `distinct()` **trước** bước chuẩn hóa, hai chuỗi `" sku-01 "` và `"SKU-01"` vẫn khác nhau và đều đi tiếp. Vì thế thứ tự `normalize` và `distinct` là một phần của hợp đồng nghiệp vụ.

Nếu một đơn hàng có ID trùng, việc âm thầm dùng `distinct` có thể **làm mất giao dịch cần đối soát**. Nhiều hệ thống phải báo lỗi, giữ cả hai bản ghi và vị trí nguồn, hoặc có quy tắc gộp rõ ràng. Test cần phản ánh chính sách đó, không chỉ “mong số lượng giảm”.

## 7. `equals` và `hashCode` quyết định ý nghĩa của `distinct`

Hai đối tượng khác tham chiếu chưa chắc khác nhau về mặt giá trị:

```java
import java.util.List;
import java.util.stream.Stream;

record Product(String sku, int quantity) {}

List<Product> unique = Stream.of(
        new Product("A", 1),
        new Product("A", 1),
        new Product("A", 2)
    )
    .distinct()
    .toList();

System.out.println(unique.size()); // 2
```

`record` có `equals`/`hashCode` dựa trên **các thành phần giá trị**; hai `Product("A", 1)` bằng nhau, còn `Product("A", 2)` khác nhau. Nếu nghiệp vụ coi **chỉ `sku`** là khóa duy nhất, `distinct()` trên cả `Product` **không đúng yêu cầu**.

Khi muốn duy nhất theo một khóa riêng, có thể nhóm theo khóa, dùng `toMap` với merger đã quy định, hoặc tạo một cấu trúc riêng để phát hiện trùng. Đừng viết predicate `filter(x -> seen.add(x.sku()))` với một `HashSet` dùng chung rồi chạy `parallel()`: cách đó có hiệu ứng phụ, rủi ro race và phụ thuộc thứ tự xử lý.

Nếu tự định nghĩa lớp mutable và thay đổi các trường tham gia `equals`/`hashCode` trong lúc pipeline đang chạy, kết quả `distinct` hoặc các cấu trúc dựa trên hash có thể sai. Hãy dùng khóa ổn định và tránh can thiệp nguồn.

## 8. `Collectors.toMap`: không được lặng lẽ bỏ qua khóa trùng

`toMap(keyMapper, valueMapper)` **ném `IllegalStateException`** nếu nhiều phần tử tạo cùng khóa. Đây là hành vi đáng kiểm thử khi khóa phải duy nhất:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A");

// Lỗi: khóa "A" xuất hiện hai lần.
// Map<String, String> result = codes.stream()
//     .collect(Collectors.toMap(Function.identity(), Function.identity()));
```

Khi trùng khóa được phép, chọn merger rõ ràng:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A");

Map<String, Long> counts = codes.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        ignored -> 1L,
        Long::sum,
        LinkedHashMap::new
    ));

System.out.println(counts.get("A")); // 2
System.out.println(counts.get("B")); // 1
```

Merger `Long::sum` có ý nghĩa khi cần **đếm bản ghi theo khóa**. Nếu cần giữ bản ghi mới nhất, phải có một quy tắc như timestamp hay version; không nên chọn `(oldValue, newValue) -> newValue` chỉ để che ngoại lệ mà không xác định “mới nhất” theo nghĩa nào.

Trong stream song song, phép gộp cũng phải phù hợp với cách các kết quả bộ phận được kết hợp. Dựa vào một counter mutable bên ngoài hoặc một merger không có tính kết hợp có thể khiến kết quả phụ thuộc lịch thực thi.

## 9. `null`: phần tử null, trường null và nguồn null là ba vấn đề

Hãy phân biệt:

1. **Danh sách nguồn chính nó là null:** gọi `source.stream()` gây `NullPointerException`.
2. **Danh sách khác null nhưng có phần tử null:** `stream()` vẫn tạo được, nhưng mapper có thể dereference null.
3. **Đối tượng khác null nhưng trường bên trong null:** `filter(Objects::nonNull)` không kiểm tra được trường thiếu.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList(" A ", null, " B ");

List<String> cleaned = raw.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .toList();

System.out.println(cleaned); // [A, B]
```

**Thứ tự phép toán quan trọng**: đặt `map(String::strip)` trước `filter(Objects::nonNull)` sẽ gọi phương thức trên null và có thể ném `NullPointerException`.

### Khi phải giữ vị trí tương ứng với đầu vào

Không phải lúc nào `filter(Objects::nonNull)` cũng là đúng. Nếu dòng thứ hai của bảng dữ liệu bị thiếu nhưng vẫn cần giữ đúng số cột/dòng:

```java
import java.util.Arrays;
import java.util.List;

List<String> raw = Arrays.asList(" A ", null, " B ");

List<String> withPlaceholders = raw.stream()
    .map(s -> s == null ? "(MISSING)" : s.strip())
    .toList();

System.out.println(withPlaceholders);
// [A, (MISSING), B]
```

Khi ứng dụng cần báo lỗi có số dòng, giải pháp tốt hơn là **giữ chỉ số nguồn** và tạo một kiểu kết quả thành công/thất bại. Việc `filter` bỏ một dòng sẽ khiến chỉ số của các phần tử còn lại khác số dòng ban đầu.

### Dùng `Objects.requireNonNull` để kiểm tra lỗi hợp đồng

Nếu ứng dụng quy định **nguồn không bao giờ được null**, một ngoại lệ rõ nghĩa có thể tốt hơn việc tự biến null thành nguồn rỗng:

```java
import java.util.List;
import java.util.Objects;

static long countPresent(List<String> source) {
    Objects.requireNonNull(source, "source");
    return source.stream()
        .filter(Objects::nonNull)
        .count();
}
```

Trong thiết kế này, null **collection** là lỗi lập trình được phát hiện sớm; null **element** là dữ liệu bị bỏ qua theo một chính sách đã chọn. Hai điều kiện không nên bị đánh đồng.

## 10. `null` tác động đến `findFirst`, `sorted`, `groupingBy` và collector

Một số thao tác gặp null theo những cách dễ bất ngờ:

| Thao tác | Với null | Điều cần kiểm thử |
| --- | --- | --- |
| `map(String::strip)` | Ném `NullPointerException` khi mapper được gọi với null. | Lọc hoặc xử lý null trước. |
| `findFirst()` / `findAny()` | Ném `NullPointerException` nếu phần tử được chọn là null. | Không giả định Optional chứa được null. |
| `sorted()` theo natural order | Null không so sánh được bằng cách tự nhiên. | Lọc null hoặc chọn comparator hỗ trợ null. |
| `groupingBy(classifier)` | Không cho classifier tạo khóa null. | Chuẩn hóa/đặt khóa đại diện hoặc từ chối bản ghi. |
| `toMap(keyMapper, valueMapper)` | Không chấp nhận giá trị mapped null theo hợp đồng collector. | Xác thực giá trị trước khi thu map. |
| `List.of` / `List.copyOf` | Từ chối phần tử null. | Không dùng để xây dữ liệu thử chứa null. |
| `Collectors.toUnmodifiableList()` | Từ chối phần tử null. | Lọc, thay thế hoặc từ chối có lý do. |
| `mapToInt` với mapper unbox `Integer` | Unbox null ném `NullPointerException`. | Xác định chính sách cho số thiếu. |

Ví dụ bắt lỗi khi `findFirst` nhìn thấy một phần tử null:

```java
import java.util.stream.Stream;

// Ném NullPointerException vì phần tử được chọn là null:
// Stream.of((String) null).findFirst();

System.out.println(Stream.ofNullable((String) null)
    .findFirst().isEmpty()); // true; isEmpty() có từ Java 11
```

Ví dụ sắp xếp có null:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

List<String> ordered = Stream.of("B", null, "A")
    .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
    .toList();

System.out.println(ordered); // [A, B, null]
```

Đừng xem `null` là một “nhóm mặc định” trong `groupingBy`. Nếu nghiệp vụ muốn nhóm dữ liệu thiếu theo một khóa riêng, hãy diễn đạt tường minh:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> counts = Arrays.asList("API", null, "UI", null)
    .stream()
    .collect(Collectors.groupingBy(
        s -> s == null ? "(UNKNOWN)" : s,
        Collectors.counting()
    ));

System.out.println(counts.get("(UNKNOWN)")); // 2
```

Chọn `"(UNKNOWN)"` chỉ khi giá trị ấy **không xung đột với một khóa dữ liệu hợp lệ**. Trong hệ thống cần phân biệt chính xác, enum hoặc kiểu đại diện trạng thái thiếu sẽ an toàn hơn chuỗi phép thuật.

## 11. Một pipeline thực tế để kiểm thử bốn loại đầu vào

Ta xây một pipeline nhỏ nhận danh sách dòng hàng thô. Mỗi dòng có mã SKU và số lượng; mục tiêu là:

- Bỏ các dòng null hoặc có trường bắt buộc null.
- Chuẩn hóa SKU bằng `strip()` và `toUpperCase(Locale.ROOT)`.
- Bỏ SKU rỗng hoặc số lượng không dương.
- **Giữ nguyên các dòng có SKU trùng**, vì danh sách sạch vẫn biểu diễn từng giao dịch.
- Nếu muốn xem trùng bao nhiêu lần, gọi một hàm thống kê riêng.

Ví dụ hoàn chỉnh (Java 17+ để sử dụng `record` và `Stream.toList()`):

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class ItemPipeline {
    private ItemPipeline() {}

    public record RawItem(String sku, Integer quantity) {}
    public record Item(String sku, int quantity) {}

    public static List<Item> clean(List<RawItem> rows) {
        Objects.requireNonNull(rows, "rows");

        return rows.stream()
            .filter(Objects::nonNull)
            .filter(row -> row.sku() != null
                && row.quantity() != null)
            .map(row -> new Item(
                row.sku().strip().toUpperCase(Locale.ROOT),
                row.quantity()
            ))
            .filter(item -> !item.sku().isEmpty()
                && item.quantity() > 0)
            .toList();
    }

    public static Map<String, Long> countBySku(List<Item> items) {
        Objects.requireNonNull(items, "items");

        return items.stream()
            .collect(Collectors.groupingBy(
                Item::sku,
                Collectors.counting()
            ));
    }
}
```

Hợp đồng của ví dụ này cố ý **đơn giản** để kiểm thử boundary case, không phải chuẩn nhập liệu production. Nó chỉ loại dòng lỗi, chưa giữ `Reject(rowNumber, reason)`; ứng dụng tài chính hoặc yêu cầu đối soát phải giữ dữ liệu bị từ chối với lý do, không chỉ âm thầm bỏ qua.

Hàm `clean` là phép biến đổi thuần trên đầu vào không bị sửa trong lúc chạy. Hàm `countBySku` thống kê khóa sau chuẩn hóa. Dùng `Map<String, Long>` để so sánh **giá trị map**, không phụ thuộc thứ tự duyệt của `HashMap`.

## 12. Kiểm thử JUnit 5: rỗng, một phần tử, trùng và null

Ví dụ dưới đây sử dụng **JUnit Jupiter 5**; phần parameterized test cần module `junit-jupiter-params` tương ứng. Hãy đặt file kiểm thử trong dự án đã cấu hình JUnit, cùng package với `ItemPipeline` (hoặc bổ sung package/import phù hợp). Chưa cần thêm lệnh build vào bài học để giải thích ngữ nghĩa.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class ItemPipelineTest {

    @Test
    void emptyInputProducesEmptyResults() {
        List<ItemPipeline.Item> result =
            ItemPipeline.clean(List.of());

        assertTrue(result.isEmpty());
        assertTrue(ItemPipeline.countBySku(result).isEmpty());
    }

    @Test
    void singletonValidItemIsNormalizedOnce() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(new ItemPipeline.RawItem(" sku-9 ", 1))
        );

        assertEquals(
            List.of(new ItemPipeline.Item("SKU-9", 1)),
            result
        );
        assertEquals(Map.of("SKU-9", 1L),
            ItemPipeline.countBySku(result));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "\t"})
    void blankOrNullSkuIsRejected(String rawSku) {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(new ItemPipeline.RawItem(rawSku, 2))
        );

        assertTrue(result.isEmpty());
    }

    @Test
    void duplicateSkusRemainTwoTransactions() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(
                new ItemPipeline.RawItem(" a ", 2),
                new ItemPipeline.RawItem("A", 3)
            )
        );

        assertEquals(2, result.size());
        assertEquals(
            Map.of("A", 2L),
            ItemPipeline.countBySku(result)
        );
    }

    @Test
    void collectingDuplicateSkusIntoUniqueMapFails() {
        List<ItemPipeline.Item> result = ItemPipeline.clean(
            List.of(
                new ItemPipeline.RawItem("A", 1),
                new ItemPipeline.RawItem("a", 2)
            )
        );

        assertThrows(IllegalStateException.class,
            () -> result.stream().collect(Collectors.toMap(
                ItemPipeline.Item::sku,
                Function.identity()
            )));
    }

    @Test
    void nullRowsAndFieldsFollowTheDeclaredPolicy() {
        List<ItemPipeline.RawItem> input = Arrays.asList(
            null,
            new ItemPipeline.RawItem(null, 2),
            new ItemPipeline.RawItem("A", null),
            new ItemPipeline.RawItem("A", 1),
            new ItemPipeline.RawItem("B", 0)
        );

        assertEquals(
            List.of(new ItemPipeline.Item("A", 1)),
            ItemPipeline.clean(input)
        );
    }

    @Test
    void nullSourceIsAProgrammingError() {
        assertThrows(NullPointerException.class,
            () -> ItemPipeline.clean(null));
    }
}
```

Đối chiếu kết quả các test:

| Tên test | Điều được chứng minh |
| --- | --- |
| `emptyInputProducesEmptyResults` | Nguồn rỗng không gây truy cập phần tử sai; map thống kê rỗng. |
| `singletonValidItemIsNormalizedOnce` | Một dòng hợp lệ thành một `Item` có SKU chuẩn và count = 1. |
| `blankOrNullSkuIsRejected` | Null/rỗng/trắng đều bị loại theo chính sách ví dụ. |
| `duplicateSkusRemainTwoTransactions` | Hai giao dịch cùng SKU **không bị xóa trùng**; thống kê có count = 2. |
| `collectingDuplicateSkusIntoUniqueMapFails` | Nếu yêu cầu map khóa duy nhất, việc trùng gây lỗi rõ ràng. |
| `nullRowsAndFieldsFollowTheDeclaredPolicy` | Phân biệt null row, null field và quantity không dương. |
| `nullSourceIsAProgrammingError` | Hợp đồng hàm không lặng lẽ coi null collection là danh sách rỗng. |

Trong bài kiểm thử thật, nên thêm cả đầu vào có chữ Unicode, mã vượt giới hạn chiều dài, số lượng rất lớn, bản ghi bị từ chối với nguyên nhân, và chính sách xử lý trùng có nhiều trường. Các trường hợp đó phụ thuộc vào **quy định nghiệp vụ**, không thể tự giả định là lỗi.

## 13. Kiểm thử ngoại lệ: phải kiểm tra sai đúng chỗ

Một lỗi hay gặp là bắt `Exception` quá rộng rồi cho test qua bất kể lỗi nào xảy ra. Hãy kiểm tra **đúng loại ngoại lệ**, và khi phù hợp, thông báo hoặc mã lỗi do ứng dụng tự quy định:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class NullOperationTest {
    @Test
    void findFirstCannotWrapSelectedNull() {
        assertThrows(NullPointerException.class,
            () -> Stream.of((String) null).findFirst());
    }
}
```

Đối với `Collectors.toMap`, test có thể kiểm tra `IllegalStateException` khi khóa trùng, nhưng **đừng phụ thuộc toàn bộ nội dung thông báo của JDK** nếu API không cam kết thông báo ổn định giữa các bản.

Với `List.of(null)`, ngoại lệ xuất hiện **khi tạo nguồn**, không phải trong `filter` hoặc `collect`. Hãy xác định đúng bước gây lỗi để không chẩn đoán nhầm pipeline.

Nếu nghiệp vụ yêu cầu **bản ghi lỗi được giữ lại**, dùng kết quả dạng `Valid/Invalid` (hoặc một record chứa lỗi) thay vì `assertThrows` cho mọi lỗi đầu vào. Ngoại lệ hợp với các vi phạm hợp đồng/điều kiện bất thường; dữ liệu nhập sai có thể là một kết quả dự kiến.

## 14. Đừng dùng `peek` hoặc side effect làm assertion chính

Pipeline Stream là **lazy**: nhiều callback chỉ chạy khi terminal operation yêu cầu kết quả. Một số tối ưu còn có thể **loại bỏ việc thực thi callback** nếu không ảnh hưởng kết quả terminal operation.

```java
import java.util.List;

long count = List.of("A", "B", "C")
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// Không bảo đảm peek sẽ in cả A, B, C.
```

Vì `List` có kích thước biết trước, một triển khai Stream có thể tính `count()` mà **không duyệt từng phần tử**. Test không nên xác nhận “`peek` đã gọi đúng ba lần” hay “`map` luôn chạy một lần cho mỗi phần tử” nếu hành vi ấy không thuộc hợp đồng.

Với các phép ngắn mạch `findFirst`, `anyMatch`, `limit`, pipeline có thể dừng sớm. Trên stream song song, framework còn có thể xử lý những phần tử khác trước khi có kết quả cuối. **Hãy assert kết quả và ràng buộc được bảo đảm**, không assert số callback hoặc thứ tự log ngẫu nhiên.

Khi gỡ lỗi, có thể dùng `peek` tạm thời để quan sát, nhưng việc kiểm thử chính nên dựa vào những hàm biến đổi thuần và đầu ra xác định.

## 15. Tạo lại stream cho mỗi phép thử, không tái sử dụng stream đã đóng

Một đối tượng `Stream` chỉ được vận hành **một lần** sau terminal operation. Ví dụ sai:

```java
import java.util.stream.Stream;

Stream<Integer> source = Stream.of(1, 2, 3);
long count = source.count();

// Không thể tái dùng cùng Stream sau terminal operation:
// int sum = source.mapToInt(Integer::intValue).sum();
```

Khi cần kiểm thử cùng dữ liệu bằng nhiều phép toán, hãy tạo stream mới từ nguồn có thể duyệt lại:

```java
import java.util.List;

List<Integer> source = List.of(1, 2, 3);
long count = source.stream().count();
int sum = source.stream().mapToInt(Integer::intValue).sum();

System.out.println(count); // 3
System.out.println(sum);   // 6
```

Hoặc dùng `Supplier<Stream<T>>` trong test:

```java
import java.util.function.Supplier;
import java.util.stream.Stream;

Supplier<Stream<String>> createStream =
    () -> Stream.of("A", "B", "C");

System.out.println(createStream.get().count());       // 3
System.out.println(createStream.get().findFirst());   // Optional[A]
```

Supplier phải tạo **stream mới**, không được trả lại cùng một stream đã tiêu thụ. Nếu nguồn là `Files.lines`, việc tạo stream mới có thể mở tệp lại; phải có `try-with-resources` cho mỗi lần đọc và chú ý dữ liệu tệp có thể đã thay đổi.

## 16. Kiểm thử nguồn song song: đúng kết quả, không lệ thuộc lịch chạy

Trong pipeline song song, các lambda có thể chạy trên nhiều worker và không theo thứ tự xuất hiện. Do đó:

- Không kiểm tra `forEach` phải gọi các action theo một thứ tự cố định.
- Không dùng `ArrayList` chia sẻ bên ngoài `parallel().forEach(list::add)` để thu kết quả.
- Không dùng predicate phụ thuộc bộ đếm ngoài để xác định bản ghi thuộc nhóm nào.
- Với `distinct` trên nguồn ordered, kiểm tra **hợp đồng về giá trị và thứ tự** nếu cần; với nguồn unordered, chỉ kiểm tra những bảo đảm thực sự tồn tại.
- Với `groupingByConcurrent`, không mặc định các danh sách giá trị giữ encounter order.
- Với số thực, kết quả reduction song song có thể khác vài bit do thứ tự cộng; dùng chính sách sai số thích hợp thay vì kiểm tra bit-for-bit không cần thiết.

Ví dụ kiểm thử tính đúng của phân nhóm:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Long> counts = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 4,
        Collectors.counting()
    ));

System.out.println(counts);
// Mỗi khóa 0,1,2,3 có đúng 2500 phần tử.
```

Đừng kiểm tra chuỗi `Map.toString()` như một kết quả có thứ tự cố định. Dùng so sánh `Map.equals`, `counts.get(key)` hoặc kiểm tra số lượng từng nhóm.

Đối với mục tiêu bài này, đầu tiên cần bảo đảm **các boundary case đúng ở chế độ tuần tự**. Sau đó chạy song song nếu thuật toán và nguồn phù hợp, so sánh kết quả tương đương theo ngữ nghĩa thay vì giả định mọi chi tiết lịch thực thi là xác định.

## 17. Kiểm thử tính chất thay vì chỉ vài ví dụ cụ thể

Các **bất biến** (*invariants*) thường phát hiện lỗi tốt hơn chỉ một danh sách đầu vào “đẹp”. Chẳng hạn:

| Bất biến | Điều kiện áp dụng | Cách kiểm tra |
| --- | --- | --- |
| `filter` không tăng số phần tử | Pipeline chỉ lọc và không thêm phần tử | `result.size() <= input.size()`. |
| `distinct` không tăng số phần tử | Các phần tử so sánh theo `equals` ổn định | `unique.size() <= input.size()`. |
| `distinct` idempotent | Không sửa phần tử giữa hai lần | `distinct(distinct(xs)).equals(distinct(xs))` nếu thứ tự được xác định. |
| Chuẩn hóa idempotent | Hàm chuẩn hóa được thiết kế như vậy | `normalize(normalize(x)).equals(normalize(x))`. |
| Tổng nhóm bằng tổng nguồn | Mọi phần tử thuộc đúng một nhóm | Tổng `counting()` của các nhóm bằng số phần tử ban đầu. |
| `partitioningBy` bảo toàn số lượng | Mỗi phần tử được phân đúng một phía | `trueCount + falseCount == input.size()`. |
| Chuẩn hóa độc lập với lịch chạy | Hàm thuần và nguồn không bị can thiệp | Kết quả tuần tự/song song tương đương theo hợp đồng. |

Ví dụ một vòng kiểm tra nhỏ cho `distinct`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> input = Arrays.asList("A", "B", "A", null, null);

List<String> first = input.stream().distinct().toList();
List<String> second = first.stream().distinct().toList();

if (!first.equals(second)) {
    throw new AssertionError("distinct không idempotent");
}
if (first.size() > input.size()) {
    throw new AssertionError("distinct tăng số phần tử");
}
System.out.println(first); // [A, B, null]
```

`distinct` có thể giữ một phần tử null trong stream tham chiếu; nhưng một terminal operation khác như `findFirst` nếu chọn null lại không chấp nhận giá trị đó. Đó là lý do không thể kiểm thử `null` bằng một assertion chung cho mọi thao tác Stream.

Đối với nghiệp vụ, cũng cần thử input có `equals`/key không ổn định, nhiều phần tử trùng liên tiếp, trùng không liên tiếp, trùng sau chuẩn hóa, toàn bộ input null và null chỉ xuất hiện ở đầu/cuối.

## 18. Quy trình gỡ lỗi khi test thất bại

Khi một test boundary case bị lỗi, đi theo trình tự:

1. **Tái hiện với đầu vào nhỏ nhất**: thường `[]`, `[x]`, `[x,x]` hoặc `[null]` đã đủ.
2. **Xác định bước xảy ra lỗi**: tạo nguồn, `map`, `filter`, terminal operation hay finisher của collector.
3. **Kiểm tra kiểu phần tử sau mỗi bước**: sau `map` có thể sinh null; sau `flatMap` số phần tử có thể tăng/giảm.
4. **Đọc hợp đồng terminal operation**: một số trả `Optional`, một số dùng identity, một số ném ngoại lệ với null.
5. **Rà soát khóa và equality**: `distinct` nhìn toàn bộ phần tử; `groupingBy`/ `toMap` nhìn khóa được tạo bởi mapper.
6. **Xác định dữ liệu bị loại có cần báo lỗi không**: nếu có, thay `filter` im lặng bằng mô hình kết quả chứa lý do.
7. **Chỉ tối ưu sau khi đúng**: parallel, concurrent collector hoặc cache có thể làm lỗi khó tái hiện hơn.

Không nên “sửa nhanh” bằng `filter(Objects::nonNull)` ở mọi chỗ. Nếu `null` là dấu hiệu quan trọng (ví dụ thiếu mã giao dịch), việc bỏ nó có thể làm báo cáo tổng số dòng sai mà không có cảnh báo.

## 19. Bài tập thực hành

**Bài 1 — Empty truth.** Dự đoán kết quả `anyMatch`, `allMatch`, `noneMatch` trên `Stream.empty()`. Giải thích vì sao `allMatch` trả `true` không chứng minh đã kiểm tra được một bản ghi nào. Viết một điều kiện yêu cầu **ít nhất một phần tử** và tất cả đều đạt.

**Bài 2 — Một phần tử và ngưỡng.** Với `Stream.of(60)`, so sánh `filter(n -> n >= 60)` và `filter(n -> n > 60)`. Thêm test cho `59`, `60`, `61`.

**Bài 3 — Trùng trước/sau chuẩn hóa.** Với `[" SKU-01 ", "sku-01", "SKU-02"]`, kiểm tra kết quả khi `distinct` đứng trước và sau phép `strip().toUpperCase(Locale.ROOT)`. Phương án nào phù hợp nếu SKU không phân biệt hoa/thường?

**Bài 4 — Khóa trùng `toMap`.** Tạo hai `Item` cùng SKU nhưng số lượng khác nhau. Kiểm tra overload hai mapper ném `IllegalStateException`, sau đó xây map tổng số lượng bằng merger `Integer::sum`. Lý giải vì sao cần chính sách gộp.

**Bài 5 — Null theo ba tầng.** Phân biệt `source == null`, `source = Arrays.asList("A", null)`, và `RawItem(null, 2)`. Chọn cho mỗi tình huống một chính sách rõ ràng: lỗi hợp đồng, bỏ phần tử hoặc tạo bản ghi từ chối.

**Bài 6 — `findFirst` với null.** Thử `Stream.of((String) null).findFirst()` và `Stream.ofNullable((String) null).findFirst()`. Cách nào tạo một phần tử null, cách nào tạo stream rỗng? Vì sao kết quả khác nhau?

**Bài 7 — JUnit tham số hóa.** Bổ sung `@ParameterizedTest` cho các SKU `null`, `""`, `" "`, `"a"`, `" A "`. Ghi rõ các trường hợp nào tạo một `Item`, trường hợp nào bị loại.

**Bài 8 — Test song song.** Chạy `IntStream.range(0, 10_000).parallel().boxed().collect(groupingBy(n -> n % 4, counting()))` và xác nhận bốn nhóm mỗi nhóm 2.500 phần tử. Không so sánh chuỗi in của map hoặc lịch gọi lambda.

**Bài 9 — Bảo toàn bản ghi lỗi.** Mở rộng `ItemPipeline.clean` để trả `ImportResult(accepted, rejected)` và giữ `rowNumber`/ `reason` cho mỗi dòng bị loại. Kiểm thử bất biến `accepted.size() + rejected.size() == source.size()`.

## 20. Checklist kiểm thử pipeline trước khi đưa vào sử dụng

- [ ] Đã kiểm tra nguồn rỗng **và** kết quả rỗng sau khi lọc.
- [ ] Đã kiểm tra nguồn một phần tử, một phần tử bị loại, và giá trị sát ngưỡng.
- [ ] Đã kiểm tra trùng nguyên văn, trùng không liền nhau, trùng sau chuẩn hóa.
- [ ] Đã xác định `equals/hashCode` hoặc khóa nghiệp vụ nào dùng để nhận diện trùng.
- [ ] `toMap` có chính sách rõ ràng khi khóa trùng; không nuốt ngoại lệ tùy tiện.
- [ ] Đã phân biệt null collection, null element và null field.
- [ ] Đã chọn rõ giữa loại null, thay thế null và giữ lỗi có lý do.
- [ ] Không giả định `findFirst` hoặc `min` luôn có giá trị; biết kiểm tra `Optional`.
- [ ] Đã kiểm tra `allMatch` trên nguồn rỗng và yêu cầu “ít nhất một” nếu cần.
- [ ] Không dùng `List.of` để tạo test data có phần tử null.
- [ ] Không phụ thuộc số callback `peek`, `map` hoặc thứ tự log trong pipeline lazy.
- [ ] Không dùng lại cùng một `Stream` sau terminal operation.
- [ ] Không dùng shared mutable state trong lambda song song.
- [ ] Assertion tập trung vào giá trị/ngoại lệ/hợp đồng, không phụ thuộc thứ tự map không được bảo đảm.
- [ ] Đã cân nhắc dữ liệu thật bị từ chối cần truy vết và thống kê chất lượng dữ liệu.

**Ghi nhớ:** Kiểm thử Stream API tốt không chỉ là cho một danh sách đẹp chạy qua `collect` mà còn phải kiểm tra **nguồn rỗng, một phần tử, trùng lặp và null**. Phân biệt kết quả rỗng với lỗi, identity với giá trị đo, trùng theo `equals` với trùng theo khóa nghiệp vụ, và null ở từng tầng dữ liệu. Hãy viết assertion theo hợp đồng đã xác định, giữ nguyên nhân loại dữ liệu khi cần đối soát và chỉ đánh giá hiệu năng hoặc song song hóa khi kết quả tuần tự đã đúng.

**Tài liệu tham khảo:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [Collectors — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Collectors.html), [Objects — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/Objects.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
