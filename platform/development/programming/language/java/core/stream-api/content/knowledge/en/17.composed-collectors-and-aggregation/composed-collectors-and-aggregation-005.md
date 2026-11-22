# Làm phẳng đầu vào Collector bằng flatMapping

Trong Java Stream API, một phần tử đầu vào thường chứa **nhiều giá trị con**: một đơn hàng có nhiều nhãn, một bài viết có nhiều từ khóa, một hóa đơn có nhiều dòng chi tiết. Khi cần tổng hợp các giá trị con **theo nhóm của phần tử cha**, `Collectors.flatMapping` cho phép biến mỗi phần tử cha thành một `Stream` con rồi chuyển **từng phần tử con** cho collector phía sau. Đây là một cách ghép các collector nhiều tầng mà không phải tự tạo danh sách trung gian.

Bài thuộc chương **Collector nhiều tầng và tổng hợp** của module **JAVA_STREAM_API**. Mục tiêu là hiểu chính xác `flatMapping`, phân biệt nó với `Stream.flatMap`, thực hành `groupingBy` với các downstream collector, và xử lý các giới hạn về thứ tự, dữ liệu null, trạng thái, tài nguyên và thực thi song song. Kiến thức này gắn với các pipeline khai báo, lazy, `filter`, `map`, `reduce` và `collect`; đồng thời giúp chuẩn bị cho collector tùy chỉnh, `Spliterator` và những phép biến đổi nâng cao như Stream Gatherers.

## 1. Bài toán: một phần tử cha có nhiều phần tử con

Giả sử có những đơn hàng:

| Mã đơn | Khu vực | Nhãn của đơn |
|---|---|---|
| D01 | Bắc | gấp, dễ vỡ |
| D02 | Bắc | gấp, quà tặng |
| D03 | Nam | *(không có nhãn)* |
| D04 | Trung | *(danh sách nhãn chưa được cung cấp)* |
| D05 | Nam | ưu tiên |

Yêu cầu: với **mỗi khu vực**, tạo tập hợp các nhãn xuất hiện trong đơn hàng của khu vực đó. Kết quả mong đợi về mặt nội dung là:

```text
Bắc   -> {gấp, dễ vỡ, quà tặng}
Nam   -> {ưu tiên}
Trung -> {}
```

Ta cần hai tầng xử lý khác nhau:

1. **Nhóm các đơn hàng** theo khu vực của đơn.
2. **Làm phẳng nhãn** của các đơn trong mỗi nhóm rồi gom nhãn vào tập hợp.

`Collectors.groupingBy` giải quyết tầng thứ nhất. `Collectors.flatMapping` giải quyết tầng thứ hai, còn `Collectors.toSet` quyết định dạng kết quả cuối của mỗi nhóm:

```java
Map<String, Set<String>> tagsByRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> order.getTags().stream(),
                        Collectors.toSet())));
```

Đây là **mẫu ý tưởng** cho dữ liệu có danh sách nhãn không null. Trong thực tế, nếu `getTags()` có thể trả `null`, phải xử lý trước khi gọi `stream()`. Ví dụ hoàn chỉnh và null-safe nằm ở phần 4.

## 2. Chữ ký và cơ chế của Collectors.flatMapping

`Collectors.flatMapping` được bổ sung từ **Java 9** trong `java.util.stream.Collectors`. Chữ ký khái quát:

```java
static <T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream)
```

| Tham số/kiểu | Ý nghĩa |
|---|---|
| `T` | Kiểu phần tử cha đi vào collector |
| `U` | Kiểu phần tử con được mapper phát ra |
| `A` | Kiểu trạng thái tích lũy của downstream collector |
| `R` | Kiểu kết quả cuối cùng của downstream collector |
| `mapper` | Nhận một `T` và trả `Stream` gồm **0, 1 hoặc nhiều** phần tử `U` |
| `downstream` | Nhận từng phần tử `U` và thu thập thành `R` |

Có thể đọc luồng xử lý ở mức khái niệm:

```text
          Stream<Order>
                |
          groupingBy(region)
                |
   +------------+-------------+
   |            |             |
 "Bắc"        "Nam"         "Trung"
   |            |             |
flatMapping   flatMapping    flatMapping
   |            |             |
 [gấp, ...]  [ưu tiên]        []
   |            |             |
  toSet        toSet         toSet
   |            |             |
{gấp, ...}  {ưu tiên}         {}
```

**Quan trọng:** `flatMapping` không phải thao tác trung gian gọi trực tiếp trên `Stream`. Nó là **một Collector** để ghép với collector khác. Hàm mapper ở đây trả một `Stream<U>` chứ không trả một `U` đơn lẻ.

### 2.1. Các trường hợp 0, 1 và nhiều phần tử

Với một đơn hàng có ba nhãn, mapper có thể tạo Stream gồm ba nhãn; downstream nhận cả ba. Nếu danh sách nhãn rỗng, mapper tạo Stream rỗng và downstream **không nhận phần tử nào** từ đơn ấy. Nếu một đơn có đúng một nhãn, downstream nhận một phần tử.

Việc một mapper phát ra **không có phần tử con** không có nghĩa bản thân **đơn hàng cha đã biến mất khỏi phép grouping**. Đây là khác biệt quan trọng với cách làm phẳng đầu vào **trước khi** nhóm.

### 2.2. Đặc điểm vòng đời của Stream con

Theo hợp đồng của `Collectors.flatMapping`, **mỗi Stream do mapper trả về được đóng sau khi các phần tử của nó đã được đưa vào downstream collector**. Nếu mapper trả về **Stream null**, implementation xem đó là Stream rỗng.

Không nên cố tình trả `null` để biểu thị không có dữ liệu; dùng `Stream.empty()` tường minh dễ đọc và tránh che khuất lỗi trong mapper. Cần nhớ thêm rằng việc đóng **Stream con** không có nghĩa tất cả tài nguyên của **Stream nguồn bên ngoài** tự động được đóng. Với nguồn I/O như `Files.lines`, hãy quản lý vòng đời nguồn bằng `try-with-resources`.

## 3. Vì sao đặt flatMapping bên trong groupingBy?

Hai pipeline nhìn tương tự nhưng có thể cho **tập khóa Map khác nhau**.

### 3.1. Làm phẳng trước rồi mới groupingBy

```java
Map<String, List<String>> byRegion = orders.stream()
        .flatMap(order -> order.getTags().stream()
                .map(tag -> new AbstractMap.SimpleEntry<>(
                        order.getRegion(), tag)))
        .collect(Collectors.groupingBy(
                Map.Entry::getKey,
                Collectors.mapping(
                        Map.Entry::getValue,
                        Collectors.toList())));
```

Đoạn minh họa này cũng giả định `getTags()` khác null; ví dụ chạy độc lập ở phần 4 cung cấp phiên bản an toàn.

Ở đây, `flatMap` là thao tác trung gian **trước** `groupingBy`. Một đơn không có nhãn sẽ không tạo ra cặp `(khu vực, nhãn)` nào. Nếu tất cả đơn của một khu vực đều không có nhãn, khóa khu vực đó **có thể không tồn tại trong Map kết quả**.

### 3.2. groupingBy trước, flatMapping ở downstream

```java
Map<String, List<String>> byRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> order.getTags().stream(),
                        Collectors.toList())));
```

`groupingBy` nhận **đơn hàng cha** và tạo nhóm cho khu vực của nó. Collector `flatMapping` chỉ thay đổi **những phần tử được đưa vào downstream**, không quyết định một đơn có thuộc nhóm hay không.

Với một khu vực có đơn nhưng không có nhãn, khóa khu vực vẫn tồn tại và giá trị có thể là **danh sách rỗng**. Nhưng khu vực **không có bất kỳ đơn hàng nào trong nguồn** sẽ không được `groupingBy` tự tạo thành khóa.

| Nguồn dữ liệu | `stream.flatMap(...).collect(groupingBy(...))` | `stream.collect(groupingBy(..., flatMapping(...)))` |
|---|---|---|
| Có đơn và có nhãn | Có nhóm | Có nhóm |
| Có đơn nhưng danh sách nhãn rỗng | Không có nhóm từ đơn ấy | Nhóm tồn tại, downstream rỗng nếu các đơn khác cũng không có nhãn |
| Có đơn và danh sách nhãn null được chuyển thành Stream rỗng | Không có phần tử để lập nhóm | Giữ nhóm của đơn cha |
| Không có đơn thuộc khu vực đó | Không có nhóm | Không có nhóm |

**Quyết định đặt thao tác làm phẳng trước hay sau khi nhóm là quyết định nghiệp vụ:** cần loại bỏ nhóm không có giá trị con, hay cần giữ nhóm đó để báo cáo “có đơn nhưng chưa có nhãn”?

## 4. Ví dụ Java 9 hoàn chỉnh: nhãn đơn hàng theo khu vực

Ví dụ dưới đây tự chạy được từ **Java 9 trở lên**. Nó chuẩn hóa nhãn, loại null và chuỗi trắng, rồi tạo cả **tập nhãn khác nhau** và **số lượt nhãn xuất hiện** theo khu vực.

```java
import java.util.AbstractMap;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FlatMappingCollectorDemo {
    static final class Order {
        private final String id;
        private final String region;
        private final List<String> tags;

        Order(String id, String region, List<String> tags) {
            this.id = id;
            this.region = region;
            this.tags = tags;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        List<String> getTags() {
            return tags;
        }
    }

    // Tạo một Stream con mới cho từng đơn, không sửa danh sách nguồn.
    static Stream<String> normalizedTags(Order order) {
        List<String> tags = order.getTags();
        if (tags == null) {
            return Stream.empty();
        }
        return tags.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(tag -> !tag.isEmpty());
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("D01", "Bắc",
                        Arrays.asList(" gấp ", "dễ vỡ", null)),
                new Order("D02", "Bắc",
                        Arrays.asList("gấp", "quà tặng")),
                new Order("D03", "Nam", Collections.emptyList()),
                new Order("D04", "Trung", null),
                new Order("D05", "Nam",
                        Arrays.asList("ưu tiên", "  "))
        );

        // 1) Nhóm đơn hàng cha, làm phẳng nhãn ở downstream.
        Map<String, Set<String>> uniqueTagsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.toSet())));

        System.out.println(uniqueTagsByRegion.get("Bắc").size()); // 3
        System.out.println(uniqueTagsByRegion.get("Nam").size()); // 1
        System.out.println(uniqueTagsByRegion.containsKey("Trung")); // true
        System.out.println(uniqueTagsByRegion.get("Trung").isEmpty()); // true

        // 2) Đếm SỐ LƯỢT nhãn, bao gồm cả nhãn xuất hiện nhiều lần.
        Map<String, Long> tagCountByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.counting())));

        System.out.println(tagCountByRegion.get("Bắc"));   // 4
        System.out.println(tagCountByRegion.get("Nam"));   // 1
        System.out.println(tagCountByRegion.get("Trung")); // 0

        // 3) Làm phẳng trước khi grouping: nhóm không có nhãn biến mất.
        Map<String, List<String>> flatFirst = orders.stream()
                .flatMap(order -> normalizedTags(order)
                        .map(tag -> new AbstractMap.SimpleEntry<>(
                                order.getRegion(), tag)))
                .collect(Collectors.groupingBy(
                        Map.Entry::getKey,
                        Collectors.mapping(
                                Map.Entry::getValue,
                                Collectors.toList())));

        System.out.println(flatFirst.containsKey("Trung")); // false

        // 4) Với nhóm chỉ có đơn rỗng, kết quả vẫn là giá trị rỗng.
        System.out.println(uniqueTagsByRegion.containsKey("Tây")); // false
    }
}
```

**Giải thích kết quả:**

- Khu vực **Bắc** có bốn lần xuất hiện nhãn hợp lệ: `gấp`, `dễ vỡ`, `gấp`, `quà tặng`. `toSet` bỏ nhãn `gấp` trùng, nên chỉ còn **ba nhãn phân biệt**; `counting` vẫn đếm **bốn lượt**.
- Khu vực **Nam** có một nhãn hợp lệ `ưu tiên`, vì đơn D03 không có nhãn và chuỗi chỉ có khoảng trắng ở D05 bị lọc.
- Khu vực **Trung** có một đơn D04 nhưng danh sách nhãn là null. `normalizedTags` trả `Stream.empty()`, nên downstream `toSet` trả tập hợp rỗng và `counting` trả `0L`. **Khóa "Trung" vẫn tồn tại** khi dùng `groupingBy(..., flatMapping(...))`.
- Khu vực **Tây** không có đơn nào nên không được tạo thành nhóm.
- `toSet` và Map mặc định của `groupingBy` **không cam kết thứ tự duyệt**; ví dụ chỉ kiểm tra nội dung qua `get`, `containsKey` và `size`.

Đây là một ví dụ dùng `flatMapping` đúng với ý nghĩa nghiệp vụ: **giữ nhóm theo phần tử cha**, nhưng cho phép mỗi phần tử cha đóng góp **0 hoặc nhiều phần tử con**.

## 5. Kết hợp flatMapping với các downstream collector khác

`flatMapping` không giới hạn ở `toSet`. Nó chuyển các phần tử `U` cho **bất kỳ downstream collector phù hợp**:

| Downstream | Kết quả theo mỗi nhóm | Trường hợp nhóm có cha nhưng không có con |
|---|---|---|
| `Collectors.toList()` | Danh sách phần tử con, có thể chứa trùng lặp | Danh sách rỗng |
| `Collectors.toSet()` | Tập phần tử con phân biệt | Tập hợp rỗng |
| `Collectors.counting()` | Số lượt phần tử con | `0L` |
| `Collectors.summingInt(String::length)` | Tổng số ký tự nhãn | `0` |
| `Collectors.joining(", ")` | Chuỗi nối các nhãn | Chuỗi rỗng `""` |
| `Collectors.mapping(..., toList())` | Biến đổi thêm sau khi làm phẳng | Danh sách rỗng |
| `Collectors.filtering(..., toSet())` (Java 9+) | Lọc phần tử con trước khi thêm vào tập | Tập hợp rỗng |

### 5.1. Giữ phần tử trùng nhau bằng toList

```java
Map<String, List<String>> allTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.toList())));

System.out.println(allTags.get("Bắc"));
// [gấp, dễ vỡ, gấp, quà tặng]
```

Nếu Stream nguồn là một `List` có encounter order, collector giữ thứ tự tương ứng cho các phần tử trong `List` kết quả; tuy nhiên, thứ tự **duyệt các khóa Map** từ `groupingBy` là chuyện khác và không được mặc định ổn định.

### 5.2. Đếm không trùng lặp bằng collectingAndThen

`Collectors.counting()` đếm **lượt xuất hiện**, trong khi đôi khi cần **số nhãn khác nhau**:

```java
Map<String, Integer> uniqueCount = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.collectingAndThen(
                                Collectors.toSet(),
                                Set::size))));

System.out.println(uniqueCount.get("Bắc"));   // 3
System.out.println(uniqueCount.get("Trung")); // 0
```

Ở đây, `toSet()` tích lũy các nhãn phân biệt; `collectingAndThen` gọi finisher `Set::size` để chuyển tập thành số lượng. Đây là ví dụ **collector lồng nhiều tầng**: `groupingBy → flatMapping → collectingAndThen → toSet`.

### 5.3. Biến đổi hoặc lọc tiếp phần tử con

`Collectors.mapping` biến **mỗi phần tử** thành một phần tử mới; `Collectors.flatMapping` biến **mỗi phần tử** thành một Stream có thể chứa nhiều phần tử. Có thể lồng chúng:

```java
Map<String, Set<String>> upperCaseTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.mapping(
                                String::toUpperCase,
                                Collectors.toSet()))));
```

Với collector `filtering` từ Java 9, có thể chỉ giữ nhãn có độ dài từ bốn ký tự:

```java
Map<String, List<String>> longTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.filtering(
                                tag -> tag.length() >= 4,
                                Collectors.toList()))));

System.out.println(longTags.get("Bắc"));
// [dễ vỡ, quà tặng]; "gấp" có ba ký tự nên bị loại.
System.out.println(longTags.get("Trung")); // []
```

Trên các đoạn code nhỏ trong mục này, `orders` và `FlatMappingCollectorDemo.normalizedTags` dùng từ ví dụ hoàn chỉnh ở phần 4. Việc bỏ phần tử con bằng downstream `filtering` vẫn giữ nhóm đã được tạo cho phần tử cha.

## 6. So sánh mapping, flatMapping, filtering và flatMap

Những tên phương thức gần nhau rất dễ gây nhầm lẫn:

| Cách viết | Cấp hoạt động | Hình dạng biến đổi | Tác động đối với nhóm |
|---|---|---|---|
| `stream.map(f)` | Thao tác trung gian trên Stream | Mỗi `T` → một `U`, kể cả U có thể null | Có thể đổi dữ liệu trước khi lập nhóm |
| `stream.flatMap(f)` | Thao tác trung gian trên Stream | Mỗi `T` → 0..n phần tử `U` | Nếu dùng trước grouping, cha không sinh con có thể không tạo nhóm |
| `Collectors.mapping(f, downstream)` | Collector downstream | Mỗi `T` → một `U` rồi tích lũy | Nhóm được lập từ cha nếu đặt bên trong groupingBy |
| `Collectors.flatMapping(f, downstream)` | Collector downstream (Java 9+) | Mỗi `T` → 0..n phần tử `U` rồi tích lũy | Nhóm được lập từ cha, kể cả khi mapper phát 0 phần tử |
| `Collectors.filtering(p, downstream)` | Collector downstream (Java 9+) | Mỗi `T` → giữ hoặc bỏ trước downstream | Nhóm được lập từ cha, kể cả khi bị downstream lọc hết |

**Quy tắc chọn nhanh:** Nếu nhiệm vụ chỉ là tạo một Stream con chung cho tất cả phần tử, `Stream.flatMap` rất tự nhiên. Nếu nhiệm vụ là **tổng hợp nhiều giá trị con bên trong từng nhóm cha**, `Collectors.flatMapping` thường biểu đạt đúng hơn và có thể giữ những nhóm không có giá trị con.

### 6.1. Không nhầm flatMapping với mapping một giá trị

```java
// Với mapping, mỗi Order chỉ đóng góp một số nguyên:
Map<String, Integer> totalTagLists = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.summingInt(order ->
                        order.getTags() == null ? 0 : 1)));
// Đây là số đơn có danh sách tags khác null, KHÔNG phải số nhãn.

// Với flatMapping + counting, mỗi Order đóng góp mọi nhãn hợp lệ:
Map<String, Long> totalTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.counting())));
```

Hãy kiểm tra **đơn vị đếm**: đếm đơn, đếm danh sách nhãn, đếm lượt nhãn và đếm nhãn phân biệt là bốn phép tính khác nhau.

## 7. Xử lý null và Stream con rỗng

Ba cấp null có thể xuất hiện trong một pipeline lồng nhau:

1. **Đơn hàng cha là null**: `Order::getRegion` hoặc `Order::getTags` sẽ lỗi; phải lọc đơn null trước hoặc xử lý rõ ràng.
2. **Danh sách nhãn của một đơn là null**: không thể gọi `tags.stream()`; cần trả `Stream.empty()` hoặc dùng API null-safe.
3. **Một phần tử bên trong danh sách nhãn là null**: `tags.stream()` vẫn phát ra null; downstream có thể nhận nó nếu không lọc.

```java
Map<String, Set<String>> byRegion = orders.stream()
        .filter(Objects::nonNull) // Bảo vệ chính Order.
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> Stream.ofNullable(order.getTags())
                                .flatMap(List::stream)
                                .filter(Objects::nonNull),
                        Collectors.toSet())));
```

`Stream.ofNullable` cũng có từ **Java 9**: nếu danh sách nhãn null, nó tạo Stream rỗng; nếu không null, nó chứa đúng một danh sách để `flatMap(List::stream)` mở ra các phần tử. `filter(Objects::nonNull)` cuối chỉ loại **phần tử nhãn null**, không loại null của danh sách.

Trong ví dụ này, `region` được giả định không null. Nếu `getRegion()` trả null, `groupingBy` có thể ném `NullPointerException` vì classifier không chấp nhận khóa null; quyết định chính sách lọc đơn hoặc ánh xạ region thiếu thành một nhãn nhóm.

### 7.1. Mapper của flatMapping trả null thì sao?

Hợp đồng của `Collectors.flatMapping` xử lý một **Stream null do mapper trả về** như Stream rỗng. Nhưng đây là cơ chế dự phòng ở mức Collector, không phải lời hứa rằng phép gọi như `order.getTags().stream()` trên danh sách null sẽ an toàn. Biểu thức đó đã ném ngoại lệ **trước khi mapper trả một Stream**.

Nên viết:

```java
order -> order.getTags() == null
        ? Stream.<String>empty()
        : order.getTags().stream()
```

hoặc dùng `Stream.ofNullable(...)` như trên để ý định bỏ dữ liệu thiếu được thể hiện rõ.

## 8. Thứ tự, tính lazy và vòng đời tài nguyên

`flatMapping` là một Collector dùng trong thao tác kết thúc `collect`. Pipeline bên trên nó như `filter` và `map` vẫn hoạt động theo cơ chế lazy của Stream; hàm ánh xạ trong `flatMapping` được áp dụng khi dữ liệu thực sự được thu thập.

### 8.1. Chọn downstream quyết định cách giữ thứ tự

- `toList` giữ các phần tử theo encounter order nếu có yêu cầu thứ tự từ nguồn và collector.
- `toSet` loại phần tử trùng nhau và **không cam kết thứ tự duyệt**.
- `toCollection(LinkedHashSet::new)` có thể dùng khi cần một tập hợp không trùng nhau **và giữ thứ tự chèn**.
- `toCollection(TreeSet::new)` sắp xếp theo thứ tự tự nhiên hoặc comparator của tập, không nhất thiết là encounter order.

Ví dụ giữ thứ tự nhãn xuất hiện và loại trùng:

```java
Map<String, java.util.LinkedHashSet<String>> orderedTags =
        orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.toCollection(
                                        java.util.LinkedHashSet::new))));

System.out.println(orderedTags.get("Bắc"));
// [gấp, dễ vỡ, quà tặng]
```

Đây là thứ tự phần tử **trong giá trị Set** của khu vực Bắc; Map tạo bởi `groupingBy` vẫn không mặc nhiên duyệt khóa theo thứ tự khu vực.

### 8.2. Các Stream con được đóng; nguồn I/O cần quản lý riêng

Nếu mapper tạo một Stream gắn với tài nguyên, `flatMapping` sẽ đóng Stream con sau khi chuyển các phần tử tới downstream. Tuy nhiên, nên cân nhắc chi phí mở/đóng tài nguyên cho **mỗi phần tử cha**: một nguồn I/O cho từng đơn hàng có thể rất đắt và dễ vượt giới hạn tài nguyên nếu thiết kế không phù hợp.

Khi Stream ngoài được tạo từ một tài nguyên cần đóng, hãy bọc chính nguồn đó:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Path path = java.nio.file.Paths.get("data.txt"); // Cần có tệp này.

try (Stream<String> lines = Files.lines(path)) {
    List<String> nonEmpty = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .collect(Collectors.toList());
}
```

Đây là đoạn minh họa cú pháp quản lý nguồn; khi thực thi phải có tệp `data.txt` tại thư mục làm việc (hoặc thay bằng đường dẫn phù hợp). `collect` tự nó không thay thế `try-with-resources` cho nguồn tệp bên ngoài.

### 8.3. Không tái sử dụng một Stream con

`Stream` thường chỉ tiêu thụ được một lần. Mapper nên **tạo Stream mới cho mỗi lần gọi**, thay vì trả cùng một biến `Stream` đã được dùng ở đơn trước. Trả một Stream đã đóng hoặc đã tiêu thụ có thể gây `IllegalStateException`.

Một `List` có thể được duyệt nhiều lần bằng các Stream mới, miễn danh sách không bị thay đổi trái quy tắc trong khi duyệt. Điều này khác với tái sử dụng chính đối tượng `Stream`.

## 9. Hiệu năng và xử lý song song

Khi dùng `groupingBy(..., flatMapping(...))` trên parallel stream, framework có thể tạo các container tích lũy trung gian cho từng nhánh, chuyển các phần tử con tới downstream, rồi gộp các container. Điều này yêu cầu downstream collector tuân thủ **hợp đồng đơn vị, kết hợp và tương đương** để kết quả hợp lệ qua nhiều cách chia.

```java
Map<String, Set<String>> parallelResult = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.toSet())));
```

Đoạn trên không chia sẻ một `HashSet` mutable bên ngoài pipeline. Các container do collector quản lý được tạo và kết hợp theo quy tắc của framework, nên không cần dùng `Collections.synchronizedSet` chỉ để viết một phép thu thập thông thường.

Để an toàn và dễ kiểm chứng:

- Mapper và các hàm của downstream nên **không can thiệp vào nguồn** và tránh trạng thái mutable được chia sẻ giữa nhiều worker.
- Không giả định thứ tự gọi mapper hoặc thứ tự chạy các worker khi dùng `parallelStream()`; dùng kết quả có ngữ nghĩa không phụ thuộc thứ tự nếu nghiệp vụ cho phép.
- `groupingBy` song song có thể phải **gộp nhiều Map**, gây chi phí đáng kể nếu nhiều nhóm hoặc dữ liệu phân bố phức tạp.
- `groupingByConcurrent` có thể thích hợp nếu thứ tự không quan trọng và downstream tương thích, nhưng bản thân việc chuyển sang concurrent collector **không bảo đảm nhanh hơn**.
- Với số lượng phần tử con lớn, `toList` có thể giữ toàn bộ dữ liệu trong bộ nhớ, còn `counting` hay `summingInt` thường chỉ cần trạng thái tích lũy nhỏ cho mỗi nhóm.

Đặt `flatMapping` bên trong collector tránh phải tự vật chất hóa một danh sách trung gian để grouping, nhưng mỗi lần gọi mapper vẫn có chi phí tạo và duyệt Stream con. Đừng xem việc dùng Stream đồng nghĩa tự động tiết kiệm bộ nhớ nếu downstream cuối vẫn phải giữ nhiều phần tử.

## 10. Khi nào không nên dùng flatMapping?

Không cần cố ép mọi bài toán sang `Collectors.flatMapping`:

| Bài toán | Cách phù hợp hơn |
|---|---|
| Cần làm phẳng một danh sách danh sách rồi trả một Stream mới | `Stream.flatMap` |
| Chỉ ánh xạ mỗi cha thành đúng một giá trị rồi thu thập theo nhóm | `Collectors.mapping` |
| Chỉ lọc phần tử trước downstream | `Collectors.filtering` hoặc `Stream.filter` theo chính sách nhóm |
| Chỉ cần đếm số đơn theo khu vực | `groupingBy(Order::getRegion, counting())` |
| Chỉ cần tính tổng một trường nguyên thủy | `summingInt`/`summingLong` hoặc primitive stream |
| Cần báo cáo nhóm theo cha, trong mỗi nhóm gom các con | `groupingBy(..., flatMapping(...))` |

Nếu nghiệp vụ **không muốn giữ nhóm rỗng**, đôi khi `Stream.flatMap` trước grouping sẽ đơn giản hơn. Nếu nghiệp vụ **bắt buộc giữ nhóm rỗng**, downstream `flatMapping` thể hiện ý nghĩa rõ hơn.

## 11. Lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân | Cách sửa |
|---|---|---|
| `NullPointerException` ở `order.getTags().stream()` | Danh sách con null | Trả `Stream.empty()` hoặc dùng `Stream.ofNullable` |
| `NullPointerException` khi gọi getter trên `Order` | Phần tử cha null | Lọc `Objects::nonNull` trước grouping |
| Nhóm không có nhãn bị mất khỏi Map | Làm phẳng trước `groupingBy` | Đặt `flatMapping` làm downstream của `groupingBy` |
| Tưởng `counting` đếm số đơn | Thực ra nó đếm phần tử **sau** `flatMapping` | Xác định đơn vị đếm; đặt `counting` ở đúng tầng |
| Số nhãn không trùng vẫn bị lặp | Dùng `toList` | Dùng `toSet` hoặc `toCollection(LinkedHashSet::new)` |
| Thứ tự nhãn không ổn định | `toSet` không có cam kết thứ tự | Dùng collection có thứ tự hoặc sắp xếp rõ ràng |
| Stream con dùng chung bị lỗi `already operated upon or closed` | Mapper trả lại Stream cũ | Tạo Stream mới cho từng phần tử cha |
| Nhãn bên trong danh sách null vẫn đi qua | Chỉ kiểm tra danh sách con khác null | Lọc phần tử con bằng `Objects::nonNull` |
| Collector song song có side effect bất ngờ | Mapper sửa biến chung hoặc nguồn | Dùng hàm thuần, để collector quản lý trạng thái |
| Dùng `flatMapping` trên Java 8 | API chưa tồn tại ở Java 8 | Nâng lên Java 9+ hoặc tự triển khai chiến lược khác |

## 12. Bài tập tự kiểm tra có đáp án

### Bài 1. Xác định số lượt nhãn

Hai đơn của khu vực A có danh sách nhãn `["x", "y"]` và `["x"]`. Kết quả của `groupingBy(region, flatMapping(tagsStream, counting()))` cho khu vực A là bao nhiêu?

**Đáp án:** `3L`, vì `counting` nhận **ba lượt nhãn**, kể cả nhãn `"x"` lặp lại. Nếu dùng `toSet` thì khu vực A chỉ có hai nhãn phân biệt.

### Bài 2. Nhóm không có giá trị con

Khu vực B có một đơn nhưng danh sách nhãn rỗng. Khu vực C không có đơn nào. Kết quả `groupingBy(Order::getRegion, flatMapping(..., toList()))` có những khóa nào?

**Đáp án:** Khu vực B **có khóa** với danh sách rỗng. Khu vực C **không có khóa** vì không có phần tử cha để tạo nhóm.

### Bài 3. So sánh hai thứ tự pipeline

Vì sao `orders.stream().flatMap(...).collect(groupingBy(...))` có thể làm mất một nhóm, còn `orders.stream().collect(groupingBy(..., flatMapping(...)))` vẫn giữ?

**Đáp án:** Ở cách thứ nhất, phần tử cha bị thay bằng các phần tử con **trước** khi phân nhóm. Cha có 0 con không tạo phần tử nào. Ở cách thứ hai, `groupingBy` nhìn thấy cha trước, tạo nhóm, còn việc làm phẳng chỉ ảnh hưởng các giá trị trong nhóm.

### Bài 4. Chọn downstream

Một khu vực có các nhãn `["gấp", "quà tặng", "gấp"]`. Muốn giữ ba lượt theo thứ tự ban đầu thì chọn `toList` hay `toSet`? Muốn hai nhãn phân biệt thì chọn gì?

**Đáp án:** `toList` giữ ba lượt khi đầu vào có encounter order. `toSet` giữ hai nhãn phân biệt nhưng không cam kết thứ tự. Nếu cần cả phân biệt và thứ tự chèn, dùng `toCollection(LinkedHashSet::new)`.

### Bài 5. Xử lý null ở đúng cấp

`order.getTags()` có thể null, và bên trong một danh sách không null vẫn có phần tử null. Có đủ nếu chỉ viết `Stream.ofNullable(order.getTags())`?

**Đáp án:** Chưa đủ. `ofNullable` cho Stream gồm **một danh sách** hoặc Stream rỗng. Còn phải làm phẳng danh sách thành nhãn bằng `flatMap(List::stream)`, rồi lọc nhãn null bằng `filter(Objects::nonNull)`.

### Bài 6. Đếm ký tự nhãn theo nhóm

Hãy tính tổng độ dài nhãn hợp lệ của mỗi khu vực, sử dụng `Collectors.flatMapping` và downstream `summingInt`.

```java
Map<String, Integer> charactersByRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.summingInt(String::length))));
```

**Đáp án:** Mỗi nhãn đã chuẩn hóa đóng góp `length()` ký tự vào tổng của nhóm. Nhóm có đơn nhưng không có nhãn hợp lệ nhận kết quả `0`. Đây là số ký tự của **các lượt nhãn**, không phải tổng độ dài các nhãn phân biệt.

## 13. Ghi nhớ

`Collectors.flatMapping(mapper, downstream)` (Java 9+) là **bộ chuyển đổi Collector**: mỗi phần tử cha tạo một Stream gồm **0 hoặc nhiều phần tử con**, rồi từng phần tử con được đưa vào downstream. Dùng nó đặc biệt hiệu quả về cách diễn đạt khi cần `groupingBy` các đối tượng cha nhưng tổng hợp các giá trị con, **giữ cả những nhóm có cha mà không có con**. Hãy phân biệt rõ làm phẳng **trước grouping** bằng `Stream.flatMap` với làm phẳng **bên trong grouping** bằng `Collectors.flatMapping`; chọn đúng downstream, xử lý null theo từng cấp, tạo Stream con mới và kiểm soát thứ tự, tài nguyên, trạng thái cũng như chi phí song song.
