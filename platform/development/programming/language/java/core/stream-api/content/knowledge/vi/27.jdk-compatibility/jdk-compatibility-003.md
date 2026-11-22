# Collector không sửa đổi được từ Java 10

## 1. Vì sao Java Stream API cần collector không sửa đổi được?

Trong **JAVA_STREAM_API**, ta thường dùng `filter`, `map`, `flatMap`, `reduce` và `collect` để chuyển dữ liệu nguồn thành kết quả. Nhiều kết quả của phép `collect` là `List`, `Set` hoặc `Map`. Vấn đề xuất hiện khi một phương thức công khai kết quả để các phần khác của chương trình sử dụng:

```java
List<String> names = users.stream()
    .map(User::name)
    .collect(Collectors.toList());
```

Đoạn trên thu được danh sách, nhưng **hợp đồng của `Collectors.toList()` không bảo đảm danh sách có thể sửa đổi hay không**. Dùng `names.add(...)` như một điều kiện nghiệp vụ là phụ thuộc vào hành vi không được cam kết. Ngược lại, nếu muốn ngăn caller sửa cấu trúc báo cáo, chỉ dựa vào kiểu `List` cũng chưa đủ.

Từ **Java 10**, lớp `java.util.stream.Collectors` có các factory:

- `Collectors.toUnmodifiableList()`;
- `Collectors.toUnmodifiableSet()`;
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper)`;
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`.

Những collector này tạo **collection không cho phép thao tác sửa đổi**. Chúng đặc biệt phù hợp khi kết quả của pipeline là **snapshot cấu trúc** được gửi đến tầng API, màn hình báo cáo hoặc xử lý nghiệp vụ khác.

### Mục tiêu bài học

Sau bài thuộc chương **Khả năng tương thích JDK**, bạn có thể:

1. Xác định phiên bản JDK tối thiểu có các `toUnmodifiable*` collectors.
2. Đọc chữ ký generic của `Collector<T,A,R>` và loại kết quả `List`, `Set`, `Map`.
3. Phân biệt kết quả **không thể thay đổi cấu trúc** với bất biến sâu của các phần tử.
4. Xử lý đúng phần tử `null`, khóa/giá trị `null` và khóa trùng.
5. Phân biệt `Collectors.toList()`, `Stream.toList()`, `List.copyOf()` và `Collections.unmodifiableList(...)`.
6. Kết hợp collector không sửa đổi được với `groupingBy`, `mapping`, `filtering`.
7. Viết phương án tương đương cho dự án phải giữ Java 8 hoặc Java 9.
8. Kiểm thử hợp đồng `UnsupportedOperationException` và tránh phụ thuộc thứ tự không được cam kết.

Trong bài, đoạn chương trình minh họa tổng hợp chạy với **JDK 17+** vì dùng `record`. Bản thân `Collectors.toUnmodifiable*` chỉ đòi **Java 10+**; không cần nâng tới Java 17 mới dùng được.

## 2. Trục thời gian: đừng nhầm phiên bản của những API giống tên

| API | Phiên bản xuất hiện | Ý nghĩa chính |
| --- | --- | --- |
| `Stream.collect(...)`, `Collectors.toList()`, `toSet()`, `toMap()` | Java 8 | Thu thập kết quả; **không tự cam kết** kết quả bất biến |
| `Collections.unmodifiableList/Set/Map(...)` | Có trước Java 8 | Tạo **view không cho sửa qua wrapper** |
| `List.of(...)`, `Set.of(...)`, `Map.of(...)` | Java 9 | Tạo collection không sửa đổi được từ các giá trị |
| `Collectors.toUnmodifiableList/Set/Map` | **Java 10** | Thu trực tiếp từ `Stream` thành collection không sửa đổi được |
| `List.copyOf(...)`, `Set.copyOf(...)`, `Map.copyOf(...)` | **Java 10** | Tạo bản sao không sửa đổi được từ collection/map sẵn có |
| `Collectors.teeing(...)` | Java 12 | Kết hợp hai downstream collectors; không đồng nghĩa bất biến |
| `Stream.toList()` | **Java 16** | Terminal operation tiện lợi, trả danh sách không sửa đổi được |

Điểm thường bị nhầm:

- `Collectors.toList()` **không được nâng cấp hợp đồng thành bất biến** sau Java 10.
- `Stream.toList()` **không** có từ Java 10; nó được bổ sung ở **Java 16**.
- `List.of` xuất hiện ở **Java 9**, còn `List.copyOf` xuất hiện ở **Java 10**.
- `Collections.unmodifiableList` là API cũ, nhưng **một wrapper view không giống snapshot độc lập**.
- Ba collector không sửa đổi được từ Java 10 nằm trong `Collectors`, **không phải** những đặc tính `IMMUTABLE` của `Spliterator`.

Tham khảo Javadoc chính thức: [`Collectors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html), [`Stream.toList()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#toList()), [`List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html), [`Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

## 3. Chữ ký generic và ý nghĩa của chữ “unmodifiable”

Các chữ ký chính có dạng:

```java
static <T> Collector<T, ?, List<T>> toUnmodifiableList()

static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
)

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
)
```

Trong `Collector<T,A,R>`:

- `T` là kiểu phần tử stream nguồn.
- `A` là trạng thái tích lũy nội bộ, được biểu diễn bằng wildcard `?` vì không phải hợp đồng công khai.
- `R` là collection kết quả; lần lượt `List<T>`, `Set<T>` hoặc `Map<K,U>`.

“Unmodifiable” ở đây là **không cho sửa collection thông qua các thao tác thêm, xóa, thay thế phần tử/entry**. Nếu thực hiện một thao tác sửa không được hỗ trợ, API ném `UnsupportedOperationException`.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> labels = Stream.of("A", "B", "C")
    .collect(Collectors.toUnmodifiableList());

System.out.println(labels); // [A, B, C]
// labels.add("D");          // UnsupportedOperationException
// labels.set(0, "Z");       // UnsupportedOperationException
// labels.remove("B");       // UnsupportedOperationException
```

**Hai giới hạn quan trọng:**

1. Không sửa được **cấu trúc collection** không đồng nghĩa phần tử `T` bên trong luôn bất biến.
2. Đừng phụ thuộc vào tên implementation hoặc ép kiểu kết quả sang `ArrayList`, `HashSet`, `HashMap`: API chỉ cam kết interface tương ứng.

## 4. `Collectors.toUnmodifiableList()`

### 4.1. Bảo toàn encounter order khi nguồn có thứ tự

`toUnmodifiableList()` thu phần tử vào danh sách không sửa đổi được, theo **encounter order** nếu pipeline có thứ tự ấy:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> result = Stream.of(8, 3, 8, 1)
    .filter(n -> n > 1)
    .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [8, 3, 8]
```

Danh sách **giữ phần tử trùng nhau**, giống một `List` thông thường. Collector không tự loại trùng hoặc sắp xếp:

- `filter` quyết định phần tử nào được giữ.
- `sorted` (nếu gọi) quyết định thứ tự mới.
- `distinct` (nếu gọi) loại trùng theo `equals`.
- `toUnmodifiableList()` thu kết quả cuối và **không cho sửa danh sách**.

Ví dụ:

```java
List<String> names = Stream.of("Chi", "An", "An", "Bình")
    .distinct()
    .sorted()
    .collect(Collectors.toUnmodifiableList());

System.out.println(names); // [An, Bình, Chi]
```

### 4.2. Không chấp nhận `null`

`Collectors.toUnmodifiableList()` **từ chối phần tử `null`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> nullable = Arrays.asList("A", null, "B");

// Ném NullPointerException khi terminal operation thực hiện:
// nullable.stream().collect(Collectors.toUnmodifiableList());
```

Nếu miền dữ liệu cho phép bỏ phần tử thiếu, hãy lọc tường minh:

```java
List<String> nonNull = nullable.stream()
    .filter(java.util.Objects::nonNull)
    .collect(Collectors.toUnmodifiableList());
// [A, B]
```

Nếu `null` là dấu hiệu dữ liệu lỗi, lọc sẽ **làm mất dấu hiệu lỗi**. Trường hợp đó nên validate và ném ngoại lệ có thông điệp, hoặc trả báo cáo lỗi riêng, chứ không mặc định bỏ qua.

### 4.3. Nguồn rỗng và bản sao

`Stream.<String>empty().collect(Collectors.toUnmodifiableList())` trả danh sách rỗng không sửa được. Bạn có thể lưu nó, truyền qua API và duyệt nhiều lần như một kết quả bình thường. Tuy nhiên, đừng đặt điều kiện rằng **mỗi lần thu phải tạo một object khác nhau** hoặc rằng nó có class cụ thể: JDK có thể tái sử dụng các instance bất biến khi thích hợp.

```java
List<String> empty = Stream.<String>empty()
    .collect(Collectors.toUnmodifiableList());

System.out.println(empty.isEmpty()); // true
```

## 5. `Collectors.toUnmodifiableSet()`

`toUnmodifiableSet()` dùng để thu phần tử thành một `Set` không sửa đổi được.

```java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> regions = Stream.of("HN", "HCM", "HN", "DN")
    .collect(Collectors.toUnmodifiableSet());

System.out.println(regions.size()); // 3
System.out.println(regions.contains("HN")); // true
// regions.add("HP"); // UnsupportedOperationException
```

### 5.1. Phần tử trùng được loại theo `equals`

Nếu nhiều phần tử được coi là bằng nhau theo `equals`, `Set` giữ một đại diện. Với các object bằng nhau nhưng là các instance khác nhau, **không được dựa vào việc instance nào được giữ**:

```java
record Tag(String code) {}

Tag first = new Tag("VIP");
Tag second = new Tag("VIP");

Set<Tag> tags = Stream.of(first, second)
    .collect(Collectors.toUnmodifiableSet());

System.out.println(tags.size()); // 1
// Không khẳng định tags.iterator().next() == first.
```

Điều này khác với “giữ bản ghi đầu tiên” trong một báo cáo cần thứ tự cụ thể. Nếu muốn chọn một đại diện theo thời gian ưu tiên, phải định nghĩa cách gộp/sắp với tiêu chí nghiệp vụ, không trông cậy vào `Set`.

### 5.2. Không có thứ tự duyệt được cam kết

`toUnmodifiableSet()` là collector **unordered**. Thứ tự phần tử khi lặp `Set` có thể khác thứ tự nguồn và có thể thay đổi giữa các cách triển khai hoặc lần chạy. Test đúng:

```java
Set<String> expected = Set.of("HN", "HCM", "DN");
assertEquals(expected, regions); // JUnit: so giá trị Set
```

Test sai về hợp đồng:

```java
// Không dùng kiểm thử này:
// assertEquals(List.of("HN", "HCM", "DN"),
//     new ArrayList<>(regions));
```

Nếu nghiệp vụ cần **thứ tự**, hãy giữ `List` (có thể `distinct` rồi `toUnmodifiableList`), hoặc dùng cấu trúc được chọn có quy tắc sắp xếp và bọc snapshot phù hợp.

### 5.3. `null` và tập rỗng

`Collectors.toUnmodifiableSet()` từ chối phần tử `null`. Nguồn rỗng tạo một `Set` rỗng không sửa đổi được. Tránh thử `Set.of("HN", null)` để tạo dữ liệu test, vì `Set.of` cũng tự ném `NullPointerException` trước khi pipeline chạy; muốn kiểm tra collector, dùng `ArrayList` hoặc `Arrays.asList` có phần tử null.

## 6. `Collectors.toUnmodifiableMap()`: khóa, giá trị và xung đột

Với `Stream<Order>`, nhu cầu thường gặp là tra cứu theo `id`:

```java
Map<String, Order> byId = orders.stream()
    .collect(Collectors.toUnmodifiableMap(
        Order::id,
        java.util.function.Function.identity()
    ));
```

Chữ ký có hai mapper:

- `keyMapper` sinh `K`.
- `valueMapper` sinh `U`.
- Kết quả là `Map<K,U>` không sửa đổi được.

### 6.1. Overload hai tham số: khóa trùng là lỗi

Khi hai phần tử tạo ra cùng một khóa theo `equals`, `toUnmodifiableMap(keyMapper, valueMapper)` ném `IllegalStateException`.

```java
record Product(String sku, int price) {}

List<Product> products = List.of(
    new Product("P-01", 100),
    new Product("P-01", 200)
);

// Ném IllegalStateException do cùng khóa P-01:
// products.stream().collect(Collectors.toUnmodifiableMap(
//     Product::sku, Product::price
// ));
```

Điều này tốt cho mô hình **khóa phải duy nhất**. Đừng âm thầm lấy phần tử cuối nếu duplicate SKU là dấu hiệu nhập dữ liệu lỗi.

### 6.2. Overload ba tham số: quyết định cách hợp nhất giá trị

Nếu trùng khóa là điều hợp lệ, dùng overload có `mergeFunction`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("HN", 100L),
    new Sale("HCM", 50L),
    new Sale("HN", 80L)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.toUnmodifiableMap(
        Sale::region,
        Sale::amountVnd,
        (a, b) -> Math.addExact(a, b)
    ));

System.out.println(totals.get("HN")); // 180
System.out.println(totals.get("HCM")); // 50
```

Ở đây, `Long` được suy ra từ mapper trả `long` bằng autoboxing. `Math.addExact` phát hiện tràn `long` thay vì lặng lẽ wrap-around. Với input có các số tiền **không âm**, phép cộng chính xác trên miền không tràn tương thích với cách chia/gộp các phần của pipeline.

Trong trường hợp giá trị là object mutable và merge function sửa object hiện có, cần kiểm tra kỹ hợp đồng **không chia sẻ state** và tác dụng phụ. Tốt nhất là dùng một giá trị hoặc bộ tích lũy có nghĩa nghiệp vụ rõ ràng.

### 6.3. `null` không được cho phép

Cả **khóa** và **giá trị** trả về bởi mapper đều không được là `null`:

```java
import java.util.ArrayList;
import java.util.List;

record Row(String key, String value) {}

List<Row> rows = new ArrayList<>();
rows.add(new Row("a", "x"));
rows.add(new Row(null, "y"));

// Ném NullPointerException:
// rows.stream().collect(Collectors.toUnmodifiableMap(
//     Row::key, Row::value
// ));
```

Giá trị `null` cũng bị từ chối. Đây là khác biệt quan trọng so với một số implementation map mutable có thể chấp nhận null; **không suy ra chính sách null từ một loại map quen thuộc**.

Nên xác định một trong ba chiến lược: **từ chối**, **bỏ bản ghi nếu nghiệp vụ cho phép**, hoặc **chuẩn hóa thành kiểu giá trị đại diện hợp lệ**. Không nên tự biến một khóa thiếu thành chuỗi `"UNKNOWN"` nếu có nguy cơ trùng với mã hợp lệ.

### 6.4. `toUnmodifiableMap` không có `mapFactory`

`Collectors.toUnmodifiableMap` không có overload chọn `LinkedHashMap::new` hoặc `TreeMap::new`. Vì vậy **không cam kết thứ tự duyệt các khóa** trong map cuối.

```java
Map<String, Long> byRegion = sales.stream()
    .collect(Collectors.toUnmodifiableMap(
        Sale::region, Sale::amountVnd, Long::sum
    ));

// Không khẳng định:
// new ArrayList<>(byRegion.keySet()) == [HN, HCM]
```

Nếu thứ tự khóa là một phần hợp đồng, xem mục 13 về thu vào `LinkedHashMap`/`TreeMap` rồi tạo bản sao và bọc view không sửa đổi được.

## 7. Chọn đúng collector theo mục tiêu

| Đầu vào và yêu cầu | Collector phù hợp | Kết quả |
| --- | --- | --- |
| Giữ mọi phần tử, kể cả giá trị trùng; giữ encounter order | `toUnmodifiableList()` | `List<T>` |
| Lấy tập giá trị phân biệt, không yêu cầu thứ tự | `toUnmodifiableSet()` | `Set<T>` |
| Ánh xạ khóa duy nhất sang giá trị, trùng phải báo lỗi | `toUnmodifiableMap(key, value)` | `Map<K,U>` |
| Ánh xạ khóa có thể trùng, cần phép gộp rõ ràng | `toUnmodifiableMap(key, value, merge)` | `Map<K,U>` |
| Muốn map có thứ tự duyệt khóa cụ thể | `toMap(..., mapFactory)` rồi snapshot/bọc view | Map theo loại đã chọn |
| Muốn caller có thể thêm/xóa kết quả | `toCollection(ArrayList::new)` hoặc map mutable đúng loại | Collection mutable |
| Muốn bất biến sâu từng record | Collection không sửa đổi được **và** phần tử immutable | Bảo đảm ở cả hai tầng |

**Câu hỏi quyết định đầu tiên:** bản báo cáo cần được coi là một snapshot cố định hay một container tiếp tục được cập nhật? Nếu yêu cầu cập nhật, đừng chọn collector không sửa đổi rồi phải copy lại ngay lập tức mà không có lý do.

## 8. Ví dụ hoàn chỉnh Java 17: tạo báo cáo chỉ đọc

Mô hình bán hàng sau có record `Order` bất biến. Chương trình cho thấy cách dùng cả `List`, `Set` và `Map` được thu bằng collector Java 10.

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public final class UnmodifiableCollectorsDemo {

    private UnmodifiableCollectorsDemo() {}

    public record Order(
        String id,
        String region,
        long amountVnd,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0L) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
        }
    }

    public record Report(
        List<Order> paidOrders,
        Set<String> regions,
        Map<String, Order> ordersById,
        Map<String, Long> paidTotalsByRegion
    ) {}

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 120_000L, true),
            new Order("O-2", "HCM", 80_000L, true),
            new Order("O-3", "HN", 40_000L, false),
            new Order("O-4", "DN", 50_000L, true),
            new Order("O-5", "HCM", 20_000L, true)
        );
    }

    public static Report buildReport(List<Order> source) {
        Objects.requireNonNull(source, "source");

        List<Order> paid = source.stream()
            .filter(Order::paid)
            .collect(Collectors.toUnmodifiableList());

        Set<String> regions = source.stream()
            .map(Order::region)
            .collect(Collectors.toUnmodifiableSet());

        Map<String, Order> byId = source.stream()
            .collect(Collectors.toUnmodifiableMap(
                Order::id,
                java.util.function.Function.identity()
            ));

        Map<String, Long> paidTotals = source.stream()
            .filter(Order::paid)
            .collect(Collectors.toUnmodifiableMap(
                Order::region,
                Order::amountVnd,
                (a, b) -> Math.addExact(a, b)
            ));

        return new Report(paid, regions, byId, paidTotals);
    }

    public static void main(String[] args) {
        Report report = buildReport(sample());

        System.out.println(report.paidOrders().stream()
            .map(Order::id).toList());
        // [O-1, O-2, O-4, O-5]

        System.out.println(report.regions().size()); // 3
        System.out.println(report.ordersById().get("O-3").amountVnd());
        // 40000

        System.out.println(report.paidTotalsByRegion().get("HCM"));
        // 100000
        System.out.println(report.paidTotalsByRegion().get("HN"));
        // 120000

        // Cả bốn collection không cho sửa trực tiếp:
        // report.paidOrders().add(...);
        // report.regions().add("HP");
        // report.ordersById().put("O-6", ...);
        // report.paidTotalsByRegion().clear();
    }
}
```

### 8.1. Phân tích kết quả

- `paidOrders` giữ encounter order từ `List<Order>` nguồn; chỉ chứa bốn đơn `paid == true`.
- `regions` có ba vùng `HN`, `HCM`, `DN`, nhưng **không cam kết thứ tự khi duyệt**.
- `ordersById` tra cứu năm đơn theo khóa duy nhất `id`; trùng ID sẽ **báo lỗi**, không ghi đè âm thầm.
- `paidTotalsByRegion` chỉ tính đơn đã thanh toán, với `HCM = 100_000`, `HN = 120_000`, `DN = 50_000`. Thứ tự in các entry map không có cam kết.
- `Report` là record, và các collection bên trong đều là kết quả không sửa đổi được; các `Order` cũng là record chứa chuỗi và primitive nên trong mô hình này không có state mutable bên trong phần tử.

### 8.2. Một lượt duyệt hay nhiều lượt?

Hàm `buildReport` duyệt lại `List` nguồn bốn lần, phù hợp với ví dụ nhỏ, dễ hiểu. Nhưng **một `Stream` đã được tiêu thụ không thể dùng lại**:

```java
// Sai:
// Stream<Order> stream = source.stream();
// var list = stream.collect(Collectors.toUnmodifiableList());
// var set = stream.map(Order::region)
//     .collect(Collectors.toUnmodifiableSet());
```

Khi nguồn rất lớn hoặc chỉ đọc một lượt, cần thiết kế một collector tổng hợp hoặc các downstream `teeing`, `groupingBy` phù hợp. Kết quả chỉ đọc không tự giải quyết bài toán chi phí duyệt nhiều lần.

## 9. Không sửa được collection khác với bất biến sâu

Xét một kiểu đối tượng **mutable**:

```java
final class MutableUser {
    private String name;

    MutableUser(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String next) {
        this.name = next;
    }
}

MutableUser user = new MutableUser("An");
List<MutableUser> users = Stream.of(user)
    .collect(Collectors.toUnmodifiableList());

// users.add(new MutableUser("Bình")); // UnsupportedOperationException
user.rename("Chi");                    // Hợp lệ: phần tử vẫn mutable.
System.out.println(users.get(0).name()); // Chi
```

Collector không sửa đổi được bảo vệ **collection membership**, chứ không làm bất biến đối tượng đang được tham chiếu. Hệ quả:

1. List không thể thêm/xóa/sắp lại phần tử qua list đó.
2. Nếu phần tử mutable bị sửa từ nơi khác, giá trị quan sát trong list có thể thay đổi.
3. Nếu phần tử được dùng làm **khóa của map/set**, sửa các trường tham gia `equals/hashCode` có thể phá khả năng tra cứu hoặc tính đúng.
4. Nếu giá trị của map là `List` mutable, `Map` không sửa đổi được **không** làm các list đó bất biến.

Muốn bất biến sâu, hãy thiết kế value object bất biến (`record` với thành phần bất biến, defensive copy cho collection lồng nhau), hoặc sao chép dữ liệu vào các DTO bất biến trước khi thu.

### 9.1. Không có thao tác “đóng băng toàn bộ object graph”

`toUnmodifiableList`, `toUnmodifiableSet`, `toUnmodifiableMap` không phải deep-copy utilities. Chúng không tự sao chép mỗi `Order`, không clone một object graph và không biến tất cả trường mutable thành final.

Đặc biệt, record:

```java
record Group(String name, List<String> members) {}
```

có field `members` final theo nghĩa tham chiếu, nhưng nếu nhận một `ArrayList` mutable từ caller, nội dung list vẫn có thể đổi. Nếu muốn bất biến cấu trúc:

```java
record SafeGroup(String name, List<String> members) {
    SafeGroup {
        members = List.copyOf(members); // Java 10+, không nhận null.
    }
}
```

Tuy nhiên, nếu phần tử bên trong list cũng mutable thì `List.copyOf` vẫn **không sao chép sâu** các phần tử đó.

## 10. View không sửa được và snapshot độc lập: một khác biệt rất lớn

`Collections.unmodifiableList(existing)` trả một **view** không cho sửa thông qua wrapper, nhưng **phản ánh thay đổi trên collection gốc**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

ArrayList<String> mutable = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(mutable);

mutable.add("C");
System.out.println(view); // [A, B, C]
// view.add("D");          // UnsupportedOperationException
```

Khi cần **snapshot cấu trúc** không còn bị caller khác sửa:

```java
List<String> snapshot = Collections.unmodifiableList(
    new ArrayList<>(mutable)
);

mutable.add("D");
System.out.println(snapshot); // [A, B, C]
```

Ở đây `new ArrayList<>(mutable)` tách container, còn `unmodifiableList` bảo vệ container đã tách. Nếu không sao chép, một phần code khác giữ tham chiếu `mutable` vẫn có thể làm thay đổi view.

So sánh:

| Cách tạo | Cấu trúc sửa qua kết quả? | Gốc đổi thì kết quả đổi? | JDK tối thiểu |
| --- | --- | --- | --- |
| `Collections.unmodifiableList(mutable)` | Không | **Có**, vì là view | Trước Java 8 |
| `Collections.unmodifiableList(new ArrayList<>(mutable))` | Không | Không, với thành phần cấu trúc | Trước Java 8 |
| `List.copyOf(mutable)` | Không | Không, với thành phần cấu trúc | Java 10 |
| `mutable.stream().collect(toUnmodifiableList())` | Không | Không, với thành phần cấu trúc | Java 10 |

Trong mọi hàng, các **phần tử mutable bên trong** vẫn có thể đổi; bảng chỉ nói về **container**.

## 11. `List.copyOf`, `Set.copyOf` và `Map.copyOf` từ Java 10

Ba phương thức `copyOf` tạo **collection không sửa đổi được** từ collection/map đã tồn tại. Chúng khác `Collectors.toUnmodifiable*` ở **điểm xuất phát**:

- `Collectors.toUnmodifiableList()` nhận các phần tử do một **stream** phát ra.
- `List.copyOf(collection)` nhận một **collection** sẵn có.
- `Set.copyOf(collection)` nhận một **collection** sẵn có và tạo tập phần tử.
- `Map.copyOf(map)` nhận một **map** sẵn có.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

ArrayList<String> source = new ArrayList<>(List.of("HN", "HCM"));
List<String> immutableList = List.copyOf(source);

source.add("DN");
System.out.println(immutableList); // [HN, HCM]

Set<String> immutableSet = Set.copyOf(source);
System.out.println(immutableSet.size()); // 3

Map<String, Integer> mutableMap = new HashMap<>();
mutableMap.put("HN", 1);
Map<String, Integer> immutableMap = Map.copyOf(mutableMap);

mutableMap.put("HN", 5);
System.out.println(immutableMap.get("HN")); // 1
```

### 11.1. Những chính sách nhất định phải biết

| Factory | Có nhận `null`? | Có giữ phần tử trùng? | Có giữ thứ tự? |
| --- | --- | --- | --- |
| `List.copyOf(collection)` | Không | Có | Giữ thứ tự duyệt của collection nguồn |
| `Set.copyOf(collection)` | Không | Không; có thể giữ đại diện bất kỳ trong số phần tử bằng nhau | Không cam kết thứ tự duyệt |
| `Map.copyOf(map)` | Không cho khóa/giá trị null | Map đầu vào tự đã có khóa duy nhất | Không cam kết thứ tự duyệt khóa |

Nếu collection truyền vào đã là dạng không sửa đổi được phù hợp, implementation có thể **không tạo container mới**. Không kiểm thử kiểu `copy != original` hoặc kết luận `copyOf` luôn cấp phát; điều quan trọng là hợp đồng nội dung và khả năng sửa đổi, không phải identity của instance.

### 11.2. `copyOf` không phải lời hứa sao chép sâu

Ví dụ `List.copyOf(List<MutableUser>)` sao chép cấu trúc danh sách, nhưng các `MutableUser` bên trong vẫn là những đối tượng cũ. Cùng nguyên tắc áp dụng cho `toUnmodifiable*`.

### 11.3. Đừng dùng `Map.copyOf` nếu cần giữ thứ tự khóa

`Map.copyOf(linkedHashMap)` tạo một map không sửa đổi được nhưng **không cam kết giữ insertion order**. Muốn giữ thứ tự duyệt của `LinkedHashMap`, dùng một **bản sao `LinkedHashMap`** và bọc bằng `Collections.unmodifiableMap`. Với `TreeMap`, bọc bản sao `TreeMap` bằng `Collections.unmodifiableSortedMap`.

## 12. So sánh `Collectors.toList()`, `Stream.toList()` và collector Java 10

Ba biểu thức nhìn gần giống nhau nhưng **hợp đồng khác nhau**:

```java
List<String> a = source.stream()
    .collect(Collectors.toList());                // Java 8+

List<String> b = source.stream()
    .collect(Collectors.toUnmodifiableList());    // Java 10+

List<String> c = source.stream()
    .toList();                                    // Java 16+
```

| Tiêu chí | `Collectors.toList()` | `Collectors.toUnmodifiableList()` | `Stream.toList()` |
| --- | --- | --- | --- |
| Phiên bản xuất hiện | Java 8 | **Java 10** | Java 16 |
| Kết quả có thể sửa không? | **Không có bảo đảm** | Không | Không |
| Encounter order | Có, nếu nguồn ordered | Có, nếu nguồn ordered | Có, nếu nguồn ordered |
| Nhận phần tử `null`? | Không có ràng buộc từ chối null như collector bất biến | **Không**, ném `NullPointerException` | Có thể chứa null; trên JDK 17 giữ được null |
| Cam kết kiểu triển khai | Không | Không | Không |
| Có dùng được trực tiếp làm downstream collector? | Có | Có | **Không**, vì là terminal method của `Stream` |
| Dễ dùng khi chỉ cần một danh sách cuối | Có | Có | Có, ngắn gọn từ Java 16 |

### 12.1. Ví dụ quan trọng về `null`

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("A", null, "B");

List<String> fromStreamToList = values.stream().toList();
System.out.println(fromStreamToList.size()); // 3 (JDK 17)
System.out.println(fromStreamToList.get(1) == null); // true

// Ném NullPointerException:
// values.stream().collect(Collectors.toUnmodifiableList());
```

Không đổi máy móc `collect(Collectors.toList())` thành `collect(Collectors.toUnmodifiableList())` nếu pipeline từng chứa `null` hợp lệ. **Chính sách dữ liệu đã đổi**. Cũng không đổi `Stream.toList()` thành `toUnmodifiableList()` rồi tin rằng hai phương thức tương đương trong mọi ca.

### 12.2. Muốn chắc chắn sửa được danh sách thì sao?

Dùng một collector có factory tạo collection cụ thể:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

ArrayList<String> mutable = source.stream()
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("New"); // Được phép.
```

`toCollection(ArrayList::new)` diễn đạt **rõ ý định cần `ArrayList` mới có thể sửa được**. Không dựa vào implementation tình cờ của `Collectors.toList()` ở một JDK cụ thể.

### 12.3. Tại sao không có `toUnmodifiableList` trên primitive stream?

`IntStream`/`LongStream`/`DoubleStream` có các terminal operation chuyên biệt như `sum`, `average`, `toArray`, nhưng không có overload `collect(Collector<T,A,R>)` như `Stream<T>`. Muốn dùng `Collectors.toUnmodifiableList` cho các số nguyên, có thể:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

List<Integer> squares = IntStream.rangeClosed(1, 4)
    .map(n -> n * n)
    .boxed()
    .collect(Collectors.toUnmodifiableList());

System.out.println(squares); // [1, 4, 9, 16]
```

`boxed()` chuyển các giá trị `int` sang `Integer`. Điều đó tạo thêm công việc boxing; nếu chỉ cần `int[]` hoặc tổng số, hãy ở lại primitive stream thay vì thu wrapper vào list.

## 13. Collector không sửa đổi được trong `groupingBy` và `mapping`

Các collector Java 10 có thể làm **downstream** của những collector khác. Ví dụ, gom ID đơn hàng theo vùng:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> idsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.mapping(
                UnmodifiableCollectorsDemo.Order::id,
                Collectors.toUnmodifiableList()
            )
        ));
```

Phân biệt **hai tầng**:

- `idsByRegion` là **map ngoài** do `groupingBy` tạo. Hợp đồng mặc định **không** bảo đảm map ngoài không sửa đổi được.
- Mỗi `List<String>` được tạo bởi `toUnmodifiableList()` là **danh sách không sửa đổi được**.

Vì vậy đoạn:

```java
// Hợp đồng nhóm trong không cho sửa:
// idsByRegion.get("HN").add("O-9"); // UnsupportedOperationException.

// Không được kết luận map ngoài cũng bất biến:
// idsByRegion.clear(); // Có thể được hỗ trợ, tùy loại map.
```

### 13.1. Biến cả map ngoài thành không sửa đổi được

Với **Java 10+**, bọc collector ngoài bằng `collectingAndThen`:

```java
Map<String, List<String>> immutableGroups =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.collectingAndThen(
            Collectors.groupingBy(
                UnmodifiableCollectorsDemo.Order::region,
                Collectors.mapping(
                    UnmodifiableCollectorsDemo.Order::id,
                    Collectors.toUnmodifiableList()
                )
            ),
            Map::copyOf
        ));

// immutableGroups.put("HP", List.of()); // UnsupportedOperationException
// immutableGroups.get("HN").add("X");    // UnsupportedOperationException
```

`Map.copyOf` tạo map ngoài không sửa đổi được; giá trị của map là các list đã không sửa đổi được. Vì các ID là chuỗi bất biến, đây là một kết quả có thể công bố như snapshot cấu trúc theo hai tầng.

**Lưu ý:** `Map.copyOf` không cam kết thứ tự duyệt khóa. Nếu vùng phải theo thứ tự xuất hiện, cần lựa chọn ở mục tiếp theo.

### 13.2. Kết hợp `filtering` cho nhóm rỗng

Với JDK 10, `Collectors.filtering` (có từ JDK 9) có thể đặt bên trong `groupingBy`:

```java
Map<String, List<String>> paidIdsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.filtering(
                UnmodifiableCollectorsDemo.Order::paid,
                Collectors.mapping(
                    UnmodifiableCollectorsDemo.Order::id,
                    Collectors.toUnmodifiableList()
                )
            )
        ));
```

Nếu một vùng chỉ có đơn chưa thanh toán, nhóm ấy vẫn tồn tại với **danh sách rỗng không sửa đổi được**. Trong khi đó, `stream.filter(Order::paid)` **trước** `groupingBy` có thể làm mất hẳn khóa vùng đó. Các collector không sửa đổi được không làm thay đổi ý nghĩa của vị trí lọc.

### 13.3. Nhóm thành `Set` không sửa đổi được

```java
Map<String, Set<String>> uniqueIdsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.mapping(
                UnmodifiableCollectorsDemo.Order::id,
                Collectors.toUnmodifiableSet()
            )
        ));
```

Kết quả loại ID trùng theo `equals` trong từng nhóm. Nhưng nếu duplicate ID là **dữ liệu lỗi**, `toUnmodifiableSet` có thể che vấn đề vì nó tự loại trùng; hãy chọn collector và policy kiểm tra duplicate cho phù hợp.

## 14. Cần thứ tự khóa xác định? Tách việc thu dữ liệu khỏi việc đóng băng

`toUnmodifiableMap` không có `mapFactory` và không bảo đảm insertion order. Nếu báo cáo phải hiển thị thứ tự vùng được gặp lần đầu, dùng `toMap` với `LinkedHashMap::new`, rồi sao chép/bọc:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

LinkedHashMap<String, Long> orderedMutable =
    UnmodifiableCollectorsDemo.sample().stream()
        .filter(UnmodifiableCollectorsDemo.Order::paid)
        .collect(Collectors.toMap(
            UnmodifiableCollectorsDemo.Order::region,
            UnmodifiableCollectorsDemo.Order::amountVnd,
            (a, b) -> Math.addExact(a, b),
            LinkedHashMap::new
        ));

Map<String, Long> orderedSnapshot =
    Collections.unmodifiableMap(
        new LinkedHashMap<>(orderedMutable)
    );

System.out.println(List.copyOf(orderedSnapshot.keySet()));
// [HN, HCM, DN]
```

Với ordered sequential stream lấy từ `List`, `LinkedHashMap` giữ thứ tự chèn khóa đầu tiên. **Bản sao** tách map khỏi biến `orderedMutable`, wrapper không cho sửa map snapshot qua kết quả được công bố.

Đừng thay bước snapshot bằng `Map.copyOf(orderedMutable)` nếu cần một **hợp đồng thứ tự**; nó không cam kết thứ tự duyệt của map gốc.

### 14.1. Cần khóa sắp tăng hoặc theo comparator?

`TreeMap` giúp sắp theo khóa:

```java
import java.util.Collections;
import java.util.SortedMap;
import java.util.TreeMap;

TreeMap<String, Long> sorted = new TreeMap<>(orderedMutable);
SortedMap<String, Long> immutableSorted =
    Collections.unmodifiableSortedMap(new TreeMap<>(sorted));

System.out.println(List.copyOf(immutableSorted.keySet()));
// [DN, HCM, HN]
```

Đối với comparator tùy chỉnh, chú ý `TreeMap` dùng kết quả so sánh để xác định **khóa tương đương**. Comparator trả 0 cho hai khóa khác nhau có thể làm chúng gộp thành một entry; đây là vấn đề **ngữ nghĩa khóa**, không chỉ là sắp xếp.

### 14.2. Sắp theo giá trị: dùng danh sách kết quả

Nếu muốn vùng có doanh thu cao nhất trước, `TreeMap` **không** tự sắp theo giá trị. Có thể tạo:

```java
List<Map.Entry<String, Long>> ranking =
    orderedSnapshot.entrySet().stream()
        .sorted(
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey())
        )
        .toList(); // Java 16+: list không sửa đổi được.
```

Danh sách entry này có thứ tự theo **doanh thu giảm dần**, phá hòa bằng **tên vùng tăng dần**. `Map.Entry` của map snapshot không cho sửa thông qua map; nếu muốn tách biệt hoàn toàn khỏi view hoặc schema bên ngoài, có thể ánh xạ sang một `record RegionTotal(String region, long total)`.

## 15. Chuyển đổi dự án Java 8/9 lên Java 10 một cách an toàn

### 15.1. Dự án vẫn dùng `--release 8`

Không thể gọi `Collectors.toUnmodifiableList()` trực tiếp khi biên dịch đích **Java 8**, kể cả khi máy phát triển chạy JDK 17 hoặc mới hơn:

```bash
javac --release 8 LegacyCollectors.java
```

Nếu file `LegacyCollectors.java` chứa lời gọi `toUnmodifiableList()`, biên dịch sẽ thất bại vì API chưa tồn tại trong Java 8. Không thể giải quyết bằng cách chỉ đổi cờ nguồn cú pháp nhưng vẫn khai ứng dụng tương thích Java 8.

Một phương án có **hợp đồng cấu trúc không sửa đổi được** dùng API đã có trên Java 8:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LegacyCollectors {
    public static List<String> labels() {
        return Stream.of("A", "B")
            .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                values -> Collections.unmodifiableList(
                    new ArrayList<>(values)
                )
            ));
    }
}
```

Đoạn code này **không sử dụng `List.of`, record hay `Stream.toList`**, nên tương thích cú pháp/API Java 8. Hai bước tạo danh sách mutable và bản sao wrapper thực hiện cùng mục đích **không cho sửa cấu trúc đầu ra**, nhưng **không tự từ chối phần tử null** như collector Java 10. Nếu muốn khớp cả chính sách null, phải validate hoặc áp dụng `Objects.requireNonNull` trước/sau khi thu.

### 15.2. Tương đương cho `Set` và `Map` trên Java 8

`Set` có thể được đóng băng sau khi thu bằng `LinkedHashSet`, nếu bạn muốn giữ thứ tự lặp xác định theo lần chèn, hoặc bằng một loại set phù hợp khác:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> immutableSet = Stream.of("HN", "HCM", "HN")
    .collect(Collectors.collectingAndThen(
        Collectors.toCollection(LinkedHashSet::new),
        set -> Collections.unmodifiableSet(
            new LinkedHashSet<>(set)
        )
    ));
```

Với map, có thể thu vào `LinkedHashMap` rồi tạo bản sao wrapper:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> immutableMap = Stream.of("HN", "HCM", "HN")
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            value -> value,
            value -> 1,
            Integer::sum,
            LinkedHashMap::new
        ),
        map -> Collections.unmodifiableMap(
            new LinkedHashMap<>(map)
        )
    ));
```

Các công thức trên cho **snapshot cấu trúc không sửa được**, nhưng không tự làm bất biến phần tử và không tự có chính sách null giống `toUnmodifiable*`. Khi migration cần **khớp chính xác contract**, hãy viết test cho `null`, duplicate, thứ tự và khả năng sửa, không chỉ so sánh output thông thường.

### 15.3. Hệ thống đích là Java 9

Java 9 có `List.of`, `Set.of`, `Map.of` và `Stream.ofNullable`, nhưng **chưa có `Collectors.toUnmodifiable*`** hay `List.copyOf`. Đừng nhầm việc có factory literal không sửa đổi được với việc đã có collector không sửa đổi được.

Nếu dự án được phép nâng **runtime và compile target** lên Java 10, có thể dùng các collector mới. Khi vẫn yêu cầu chạy trên Java 8/9, giữ phương án tương thích cũ và kiểm chứng trên môi trường đích.

### 15.4. Thay đổi hành vi phải được xem như thay đổi API

Giả sử code cũ:

```java
List<Customer> result = stream.collect(Collectors.toList());
result.sort(comparator);
```

Nếu thay collector bằng `toUnmodifiableList()`, lệnh `sort` sẽ thất bại. Tùy nghiệp vụ:

1. Nếu muốn kết quả **đã được sắp và không sửa**: đặt `sorted(comparator)` **trước** `collect(toUnmodifiableList())`.
2. Nếu caller cần sửa danh sách: dùng `toCollection(ArrayList::new)`.
3. Nếu muốn bản gốc không sửa nhưng caller có bản làm việc: caller có thể dùng `new ArrayList<>(immutableResult)`.

Việc nâng JDK không đủ để suy ra rằng mọi collection **nên** trở thành unmodifiable; đó là một lựa chọn hợp đồng.

## 16. Kiểm thử JUnit 5: bất biến, null, duplicate và thứ tự

Các test dưới đây tham chiếu chương trình `UnmodifiableCollectorsDemo` ở mục 8. Giả sử có JUnit Jupiter trong dự án và dùng JDK 17+.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class UnmodifiableCollectorsDemoTest {

    @Test
    void listPreservesEncounterOrderAndDuplicates() {
        List<Integer> actual = Stream.of(3, 1, 3, 2)
            .collect(Collectors.toUnmodifiableList());
        assertEquals(List.of(3, 1, 3, 2), actual);
        assertThrows(UnsupportedOperationException.class, () ->
            actual.add(99)
        );
        assertThrows(UnsupportedOperationException.class, () ->
            actual.set(0, 99)
        );
    }

    @Test
    void setRemovesDuplicatesWithoutOrderPromise() {
        Set<String> actual = Stream.of("HN", "DN", "HN")
            .collect(Collectors.toUnmodifiableSet());

        assertEquals(Set.of("HN", "DN"), actual);
        assertThrows(UnsupportedOperationException.class, () ->
            actual.add("HP")
        );
        // Không assert thứ tự khi lặp actual.
    }

    @Test
    void uniqueKeyMapCannotBeMutated() {
        var report = UnmodifiableCollectorsDemo.buildReport(
            UnmodifiableCollectorsDemo.sample()
        );

        assertEquals(5, report.ordersById().size());
        assertEquals(100_000L, report.paidTotalsByRegion().get("HCM"));

        assertThrows(UnsupportedOperationException.class, () ->
            report.ordersById().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.paidTotalsByRegion().put("HP", 10L)
        );
    }

    @Test
    void toUnmodifiableListAndSetRejectNull() {
        List<String> nullable = Arrays.asList("A", null, "B");

        assertThrows(NullPointerException.class, () ->
            nullable.stream().collect(
                Collectors.toUnmodifiableList()
            )
        );
        assertThrows(NullPointerException.class, () ->
            nullable.stream().collect(
                Collectors.toUnmodifiableSet()
            )
        );
    }

    @Test
    void unmodifiableMapRejectsNullKeyAndNullValue() {
        record Row(String key, String value) {}

        List<Row> nullKey = List.of(new Row(null, "x"));
        List<Row> nullValue = List.of(new Row("a", null));

        assertThrows(NullPointerException.class, () ->
            nullKey.stream().collect(
                Collectors.toUnmodifiableMap(Row::key, Row::value)
            )
        );
        assertThrows(NullPointerException.class, () ->
            nullValue.stream().collect(
                Collectors.toUnmodifiableMap(Row::key, Row::value)
            )
        );
    }

    @Test
    void duplicateMapKeyFailsWithoutMergeFunction() {
        record Row(String key, int value) {}
        List<Row> rows = List.of(
            new Row("A", 1),
            new Row("A", 2)
        );

        assertThrows(IllegalStateException.class, () ->
            rows.stream().collect(
                Collectors.toUnmodifiableMap(
                    Row::key, Row::value
                )
            )
        );
    }

    @Test
    void duplicateMapKeyCanBeMergedExplicitly() {
        record Row(String key, long value) {}
        List<Row> rows = List.of(
            new Row("A", 1L),
            new Row("A", 2L),
            new Row("B", 4L)
        );

        Map<String, Long> actual = rows.stream()
            .collect(Collectors.toUnmodifiableMap(
                Row::key, Row::value, Math::addExact
            ));

        assertEquals(Map.of("A", 3L, "B", 4L), actual);
    }

    @Test
    void collectedSnapshotDoesNotTrackSourceStructure() {
        ArrayList<String> source = new ArrayList<>(
            List.of("A", "B")
        );

        List<String> immutable = source.stream()
            .collect(Collectors.toUnmodifiableList());

        source.add("C");
        assertEquals(List.of("A", "B"), immutable);
    }

    @Test
    void unmodifiableCollectionDoesNotFreezeMutableElements() {
        StringBuilder mutable = new StringBuilder("A");
        List<StringBuilder> result = Stream.of(mutable)
            .collect(Collectors.toUnmodifiableList());

        mutable.append("B");
        assertEquals("AB", result.get(0).toString());
        assertThrows(UnsupportedOperationException.class, () ->
            result.remove(0)
        );
    }

    @Test
    void streamToListAndCollectorDifferOnNullInJdk17() {
        List<String> nullable = Arrays.asList("A", null);

        List<String> result = nullable.stream().toList();
        assertEquals(2, result.size());
        assertTrue(result.get(1) == null);
        assertThrows(UnsupportedOperationException.class, () ->
            result.add("B")
        );
    }

    @Test
    void emptySourceReturnsEmptyUnmodifiableResults() {
        List<String> values = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableList());
        Set<String> unique = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableSet());
        Map<String, String> mappings = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableMap(
                value -> value,
                value -> value
            ));

        assertTrue(values.isEmpty());
        assertTrue(unique.isEmpty());
        assertTrue(mappings.isEmpty());

        assertThrows(UnsupportedOperationException.class, () ->
            values.add("A")
        );
    }
}
```

**Cách đọc test:** không so sánh tên class triển khai hoặc identity của kết quả, vì JDK không cam kết những điều đó. Với `List` ordered, so sánh toàn bộ danh sách. Với `Set` và `Map`, so sánh tập phần tử/các cặp khóa–giá trị mà không áp thứ tự duyệt.

### 16.1. Ca kiểm thử nên bổ sung trong dự án thật

- Phần tử đầu vào có `equals/hashCode` dựa trên field mutable.
- Hai object bằng nhau nhưng khác tham chiếu trong `toUnmodifiableSet`.
- `toUnmodifiableMap` với mã định danh có ký tự hoa/thường; quyết định có chuẩn hóa khóa hay không.
- Merge function có side effect hoặc phép toán không kết hợp; kiểm tra tính đúng ở parallel stream.
- Các giá trị `long` sát giới hạn và lỗi `Math.addExact`.
- Nested `groupingBy`: map ngoài mutable, list trong unmodifiable; sau `Map.copyOf` cả hai tầng unmodifiable.
- Snapshot có thứ tự bằng `Collections.unmodifiableMap(new LinkedHashMap<>(...))`.
- Nguồn đã lọc hết, không có phần tử, hoặc có phần tử null do dữ liệu bên ngoài.

## 17. Luồng song song, encounter order và những điều không được suy luận

Collector không sửa đổi được **không đồng nghĩa** collector `CONCURRENT`. Ta có thể dùng chúng trong một parallel stream, vì Stream framework có cơ chế tạo và gộp các trạng thái tích lũy theo hợp đồng; không cần tự sửa một `ArrayList` chung từ nhiều thread:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

List<Integer> values = IntStream.range(0, 100_000)
    .boxed().parallel()
    .collect(Collectors.toUnmodifiableList());

System.out.println(values.size());  // 100000
System.out.println(values.get(0)); // 0, vì nguồn có encounter order
```

Nếu pipeline là ordered, `toUnmodifiableList` phải có nội dung theo encounter order; **thứ tự các worker gọi mapper** có thể khác. Đừng dùng log từ `peek`, timestamp của thread hoặc biến chia sẻ trong mapper để suy luận vị trí kết quả.

### 17.1. `Set` và `Map` không bảo đảm thứ tự dù nguồn là `List`

`toUnmodifiableSet` là unordered collector, `toUnmodifiableMap` không cam kết thứ tự khóa. Ngay cả khi bắt đầu từ `List` có thứ tự, hai kết quả này không có một lời hứa “giữ thứ tự nguồn”.

Nếu cần báo cáo các cặp khóa–giá trị **có thứ tự**, chọn collector với `mapFactory` và snapshot phù hợp, hoặc tạo một `List<record>` đã được `sorted`.

### 17.2. Không được thay nguồn mutable dưới chân pipeline

`parallelStream()` không cho phép sửa collection nguồn một cách tùy tiện trong lúc duyệt. `toUnmodifiableList` ở cuối không sửa được kết quả, nhưng **không bảo vệ collection nguồn khỏi concurrent modification**.

Tương tự, nếu `map` trả một object mutable được nhiều thread cùng sửa, danh sách cuối không sửa được cũng không giải quyết race bên trong từng object.

### 17.3. `groupingByConcurrent` có downstream unmodifiable

Có thể dùng:

```java
var groups = UnmodifiableCollectorsDemo.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        UnmodifiableCollectorsDemo.Order::region,
        Collectors.mapping(
            UnmodifiableCollectorsDemo.Order::id,
            Collectors.toUnmodifiableList()
        )
    ));
```

Collector ngoài trả **`ConcurrentMap` mutable**; mỗi nhóm bên trong là **`List` không sửa đổi được** sau khi collector hoàn tất. Hợp đồng collector ngoài có `UNORDERED`, nên không giả định các list nhóm giữ thứ tự gặp phần tử.

Chọn cách này khi muốn phân nhóm đồng thời mà không yêu cầu thứ tự list con, không phải chỉ để “nhanh hơn”; hãy kiểm thử và đo hiệu năng với phân bố khóa thực.

## 18. Hiệu năng, tài nguyên và giới hạn

### 18.1. Không sửa được không có nghĩa không cấp phát

Một collector vẫn có thể cần container tích lũy tạm thời để chứa các phần tử, gộp các nhánh và tạo kết quả cuối. `toUnmodifiableList` không có lời hứa “zero-copy” hoặc loại implementation cụ thể. `List.copyOf` có thể tái sử dụng một instance đã unmodifiable trong một số trường hợp, nhưng không nên viết logic phụ thuộc tối ưu hóa đó.

Trên dữ liệu lớn, chênh lệch tốc độ/bộ nhớ giữa `Collectors.toList`, `toUnmodifiableList` và `Stream.toList` nên được đánh giá bằng benchmark đáng tin (ví dụ JMH), không suy từ tên phương thức.

### 18.2. `List` giữ mọi phần tử, `Set` cần kiểm tra trùng, `Map` cần khóa

| Collector | Trạng thái dữ liệu cần giữ | Chi phí đáng lưu ý |
| --- | --- | --- |
| `toUnmodifiableList` | Mọi phần tử sau pipeline | Bộ nhớ theo số phần tử |
| `toUnmodifiableSet` | Các giá trị phân biệt | `equals/hashCode` và lưu tập giá trị |
| `toUnmodifiableMap` | Các ánh xạ khóa–giá trị | Key mapping, kiểm tra khóa trùng hoặc merge |

Nếu chỉ cần **số lượng, tổng hoặc thống kê**, ưu tiên `count()`, `sum()`, `counting()`, `summingLong()`, `summarizingLong()` thay vì materialize hàng triệu phần tử vào list bất biến.

### 18.3. Chỉ đóng băng kết quả không đóng nguồn I/O

Một nguồn từ `Files.lines` phải đóng bằng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> nonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .collect(Collectors.toUnmodifiableList());
    }
}
```

`collect` là terminal operation **nhưng không tự đóng stream nguồn**. Nếu lỗi đọc phát sinh khi tiêu thụ, `try-with-resources` vẫn bảo đảm đóng tài nguyên. Kết quả không sửa được chỉ nói về **collection cuối**, không giải quyết vòng đời I/O của nguồn.

### 18.4. Không có bảo đảm bất biến sâu và an toàn luồng cho phần tử

Sau khi công bố một kết quả unmodifiable an toàn, nhiều thread có thể đọc **cấu trúc collection** mà không có thao tác sửa cấu trúc qua API. Nhưng nếu các phần tử hoặc value mutable vẫn được nơi khác cập nhật, chúng có thể có race và vấn đề visibility; cần đối tượng bất biến hoặc cơ chế đồng bộ và công bố đối tượng đúng cách.

Không coi `unmodifiable` là một công cụ thay thế `synchronized`, `ConcurrentHashMap` hay một thiết kế dữ liệu immutable.

## 19. Những lỗi thường gặp khi nâng phiên bản JDK

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Collectors.toUnmodifiableList` với `--release 8` | Không biên dịch | Dùng API cũ hoặc nâng target Java 10 |
| Gọi `Stream.toList()` trên Java 10 | Không biên dịch | Dùng `collect(toUnmodifiableList())` |
| Cho rằng `Collectors.toList()` luôn mutable | Phụ thuộc implementation | Dùng `toCollection(ArrayList::new)` |
| Cho rằng `Collectors.toList()` luôn unmodifiable | Không được cam kết | Dùng `toUnmodifiableList` hoặc `Stream.toList` |
| Đổi collector nhưng dữ liệu có `null` | `NullPointerException` | Xác định chính sách null |
| Dùng `toUnmodifiableMap(key,value)` khi khóa trùng hợp lệ | `IllegalStateException` | Thêm merge function phù hợp |
| Dùng merge để “chọn ngẫu nhiên một giá trị” | Có thể che dữ liệu lỗi | Xác định ưu tiên hoặc báo lỗi |
| Test thứ tự của `Set`/`Map` bất biến | Test mong hành vi không được cam kết | So sánh nội dung, sắp nếu cần |
| Dùng `Map.copyOf(LinkedHashMap)` và đòi insertion order | Không được bảo đảm | Snapshot/bọc `LinkedHashMap` |
| Bọc `Collections.unmodifiableList(mutable)` rồi sửa `mutable` | View đổi theo gốc | Copy container trước khi bọc |
| Nghĩ collection unmodifiable làm element immutable | Giá trị bên trong vẫn có thể đổi | Defensive copy/value object |
| Thay `toList()` bằng `toUnmodifiableList()` mà không test | Khác biệt null/khả năng sửa | Viết compatibility tests |
| Dùng collector mới rồi đòi toàn pipeline “không có side effect” | Mapper nguồn có thể vẫn can thiệp state | Giữ pipeline stateless, non-interfering |
| Dùng `collect` với file rồi quên close | Rò rỉ tài nguyên | `try-with-resources` |

## 20. Bài tập thực hành

### Bài 1 — Chọn collector đúng hợp đồng

Cho `Stream<String>` có giá trị `["HN", "HCM", "HN", "DN"]`. Viết ba pipeline:

1. Giữ nguyên thứ tự và cả hai `"HN"` trong `List` không sửa được.
2. Lấy `Set` các vùng phân biệt, không phụ thuộc thứ tự khi lặp.
3. Tạo map đếm số lần xuất hiện mỗi vùng bằng `toUnmodifiableMap` ba tham số.

Viết test cho `UnsupportedOperationException` của cả ba kết quả.

### Bài 2 — So sánh Java 10 với Java 16

Tạo `List<String>` có phần tử `null` bằng `Arrays.asList("A", null)`. Trên JDK 17:

- Quan sát `stream().toList()`.
- Quan sát `stream().collect(Collectors.toUnmodifiableList())`.
- Giải thích vì sao việc thay một API bằng API kia có thể làm đổi hành vi lỗi.

Không dùng `List.of("A", null)`, vì lỗi sẽ xảy ra ngay khi dựng nguồn.

### Bài 3 — Tìm duplicate ID trước khi phát hành báo cáo

Tạo hai `Order` có cùng `id`. Thu `Map<String,Order>` bằng `toUnmodifiableMap(Order::id, identity())` và xác minh có `IllegalStateException`. Sau đó xem xét một yêu cầu nghiệp vụ khác: khi trùng ID, bản mới nhất theo `Instant` sẽ thắng. Đề xuất merge function **có thứ tự ưu tiên tường minh**, không phụ thuộc phần tử nào được mapper gặp đầu.

### Bài 4 — Snapshot giữ insertion order

Từ `Stream<Sale>`, cộng tiền theo vùng bằng `toMap` với `LinkedHashMap::new`. Tạo snapshot không sửa đổi được **vẫn giữ thứ tự vùng đầu tiên**, rồi thay đổi map gốc và chứng minh snapshot không đổi. Giải thích vì sao `Map.copyOf` không đáp ứng hợp đồng thứ tự này.

### Bài 5 — Bất biến theo hai tầng

Dùng `groupingBy(Order::region, mapping(Order::id, toUnmodifiableList()))`. Chứng minh map ngoài chưa được bảo đảm là unmodifiable. Sau đó thêm `collectingAndThen(..., Map::copyOf)`, kiểm thử không sửa được cả map ngoài và list trong.

### Bài 6 — Java 8 compatibility

Viết một lớp `LegacyReport` chỉ dùng cú pháp Java 8, tạo một danh sách không sửa đổi được bằng `Collectors.collectingAndThen`, `ArrayList` và `Collections.unmodifiableList`. Kiểm tra bằng `javac --release 8` khi có JDK hỗ trợ. Bổ sung bước reject `null` để khớp chính sách của `toUnmodifiableList` Java 10.

### Bài 7 — Bất biến sâu

Tạo `MutableUser` có thể đổi `name`, thu vào `toUnmodifiableList` rồi đổi tên qua tham chiếu gốc. Giải thích vì sao danh sách vẫn phản ánh tên mới. Thay bằng `record UserView(String name)` được tạo qua `map` trước khi thu, sau đó thử đổi object gốc để chứng minh snapshot giá trị không bị ảnh hưởng.

### Bài 8 — Song song và tính đúng

Tạo 100.000 ID duy nhất, dùng `parallelStream().collect(toUnmodifiableList())` và đối chiếu với dãy gốc. Tiếp tục thu `Set` và `Map` từ các ID; so sánh **nội dung**, không kiểm thử thứ tự lặp. Giải thích tại sao tính đúng không có nghĩa song song chắc chắn nhanh hơn.

### Bài 9 — Dữ liệu từ file

Đọc các dòng từ `Files.lines(path)`, loại dòng trắng và thu thành `List` không sửa đổi được. Dùng `try-with-resources`, phân biệt lỗi đọc file với file rỗng, và đánh giá nguy cơ hết bộ nhớ khi file rất lớn.

## 21. Bảng quyết định cuối bài

| Bạn cần gì? | Giải pháp thường phù hợp |
| --- | --- |
| Một danh sách từ stream, không sửa được và **không nhận null** | `Collectors.toUnmodifiableList()` (Java 10+) |
| Một tập giá trị phân biệt, không sửa được | `Collectors.toUnmodifiableSet()` (Java 10+) |
| Một map khóa duy nhất, trùng phải báo lỗi | `Collectors.toUnmodifiableMap(key,value)` |
| Một map có khóa trùng, gộp được theo quy tắc | `Collectors.toUnmodifiableMap(key,value,merge)` |
| Một danh sách không sửa được từ stream trên JDK 16+ | `Stream.toList()` |
| Một danh sách chắc chắn mutable | `collect(toCollection(ArrayList::new))` |
| Một bản sao không sửa đổi được từ collection có sẵn | `List.copyOf` / `Set.copyOf` / `Map.copyOf` (Java 10+) |
| Một **view** không sửa được của collection đang có | `Collections.unmodifiableList/Set/Map` |
| Snapshot giữ insertion order của map | `Collections.unmodifiableMap(new LinkedHashMap<>(source))` |
| Snapshot có khóa sắp tăng | `Collections.unmodifiableSortedMap(new TreeMap<>(source))` |
| Bất biến cả map nhóm và list con | `collectingAndThen(groupingBy(..., mapping(..., toUnmodifiableList())), Map::copyOf)` |
| Phần tử bên trong có thể đổi | Map phần tử sang DTO immutable, defensive copy cần thiết |
| Chạy trên Java 8/9 | `collectingAndThen` với container copy và `Collections.unmodifiable*`, test bổ sung null/duplicate |
| Cần kiểm soát bộ nhớ thay vì giữ mọi bản ghi | Dùng collector thống kê như `counting`/`summingLong` |

## 22. Tổng kết

**`Collectors.toUnmodifiableList`, `toUnmodifiableSet` và `toUnmodifiableMap` xuất hiện từ Java 10** để chuyển kết quả của Java Stream API thành các collection không cho sửa cấu trúc. Chúng có chính sách dữ liệu rõ: **không nhận `null`**; `Set` loại phần tử trùng theo `equals`; `Map` từ chối khóa trùng trừ khi cung cấp `mergeFunction`; chỉ `List` cam kết bảo toàn encounter order khi nguồn có thứ tự.

Sự khác biệt giữa **snapshot** và **view**, giữa **không sửa được collection** và **bất biến sâu**, cũng như giữa **collector Java 10** với `Stream.toList()` từ Java 16 có tác động trực tiếp đến việc nâng JDK và thiết kế API. Hãy xác định trước hợp đồng dữ liệu, null, duplicate, thứ tự, quyền sửa và yêu cầu hiệu năng; sau đó chọn collector và kiểm thử tương ứng. Nhờ vậy, pipeline `filter`, `map`, `reduce` và `collect` không chỉ ngắn gọn mà còn trả kết quả có ý nghĩa ổn định khi ứng dụng phát triển qua nhiều phiên bản JDK.
