# Chọn loại Map bằng mapFactory

Trong Java Stream API, `Collectors.toMap` và `Collectors.groupingBy` có thể chuyển dữ liệu qua một pipeline `filter`, `map`, `collect` thành `Map<K, V>`. Kết quả đúng về **khóa và giá trị** chưa chắc đã đủ: có bài toán cần giữ thứ tự xuất hiện, có bài toán cần khóa được sắp xếp, có bài toán sử dụng enum làm khóa, và có bài toán cần một `ConcurrentMap` để tích lũy đồng thời. Khi đó, **`mapFactory`** cho phép chỉ định kiểu Map được tạo ra.

Bài học thuộc chương **Thu thập thành Map** của mô-đun **JAVA_STREAM_API**. Ta sẽ phân tích cách dùng `mapFactory` trong các overload của `toMap`, `groupingBy` và các collector đồng thời; thực hành `HashMap`, `LinkedHashMap`, `TreeMap`, `EnumMap`, `ConcurrentHashMap` và `ConcurrentSkipListMap`. Đồng thời, bài làm rõ hợp đồng về khóa trùng, giá trị `null`, comparator, thứ tự, trạng thái tích lũy, tính lazy và chi phí khi xử lý song song.

## 1. Vì sao cần chọn loại Map?

Giả sử ứng dụng cần chuyển danh sách bản ghi đơn hàng thành các báo cáo:

- Tra cứu đơn theo mã, không quan tâm thứ tự duyệt khóa.
- Hiển thị các mã đơn theo **thứ tự xuất hiện lần đầu**.
- Xuất báo cáo doanh thu có mã khu vực **sắp xếp theo khóa**.
- Thống kê số đơn theo một `enum Status`, theo thứ tự khai báo của enum.
- Gom dữ liệu từ Stream song song vào một cấu trúc đồng thời.

Tất cả đều có dạng kết quả `Map`, nhưng yêu cầu về **loại Map** khác nhau:

| Loại Map | Đặc tính nổi bật | Khi nên cân nhắc |
| --- | --- | --- |
| `HashMap` | Không bảo đảm thứ tự duyệt; tra cứu hash thông thường | Tra cứu khóa, không cần thứ tự |
| `LinkedHashMap` | Duyệt theo thứ tự chèn mặc định | Kết quả hiển thị cần nhớ thứ tự khóa được gặp |
| `TreeMap` | Khóa theo thứ tự comparator hoặc natural ordering | Báo cáo cần sắp xếp khóa |
| `EnumMap<E, V>` | Chỉ dùng khóa thuộc một enum; duyệt theo thứ tự khai báo enum | Thống kê theo tập trạng thái cố định |
| `ConcurrentHashMap` | Các thao tác cập nhật đồng thời được hỗ trợ; không bảo đảm thứ tự | Thu thập concurrent, khóa dùng hash |
| `ConcurrentSkipListMap` | `ConcurrentNavigableMap` có thứ tự khóa | Cần đồng thời và thứ tự theo comparator |

**Chọn Map không tự giải quyết logic gom dữ liệu.** Để thu thập đúng, còn cần quyết định khóa lấy từ đâu, giá trị lấy từ đâu, xử lý khóa trùng như thế nào và có chấp nhận `null` hay không.

## 2. `mapFactory` là gì?

Trong các collector, `mapFactory` là **`Supplier<M>`**, tức hàm tạo ra một Map **mới** khi collector cần container tích lũy.

Ví dụ:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.TreeMap;
import java.util.function.Supplier;

Supplier<HashMap<String, Integer>> hashFactory = HashMap::new;
Supplier<LinkedHashMap<String, Integer>> linkedFactory = LinkedHashMap::new;
Supplier<TreeMap<String, Integer>> treeFactory = TreeMap::new;
```

Không nên đưa một Map đã có dữ liệu và dùng lại cùng đối tượng cho mọi lần thu thập:

```java
// Sai về thiết kế: mọi lần gọi supplier trả về cùng một container.
HashMap<String, Integer> shared = new HashMap<>();
Supplier<HashMap<String, Integer>> unsafeFactory = () -> shared;
```

Một collector có thể tạo nhiều Map khi xử lý song song hoặc khi có nhiều lời gọi `collect` độc lập. Supplier trả về cùng một Map dùng chung dễ làm lẫn dữ liệu và gây lỗi đồng thời.

Sơ đồ ý nghĩa:

```text
List<Order>
    |
    | stream().filter(...): thao tác trung gian lazy
    v
Stream<Order>
    |
    | collect(toMap(..., mapFactory)): terminal operation
    v
mapFactory.get() ---> Map mới ---> thêm/gộp các entry ---> Map kết quả
```

## 3. `Collectors.toMap` với `mapFactory`

Overload quan trọng nhất ở đây có dạng:

```java
public static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
)
```

Bốn tham số có vai trò khác nhau:

| Tham số | Vai trò | Ví dụ |
| --- | --- | --- |
| `keyMapper` | Tạo khóa `K` từ phần tử `T` | `Order::id` |
| `valueMapper` | Tạo giá trị `U` | `Function.identity()` |
| `mergeFunction` | Xử lý khi hai phần tử có khóa trùng theo Map đang dùng | `(oldValue, newValue) -> newValue` |
| `mapFactory` | Quyết định kiểu container `M` | `LinkedHashMap::new` |

`mergeFunction` là thành phần **bắt buộc trong overload này**, kể cả khi dữ liệu hiện tại có khóa duy nhất. Nếu muốn dùng overload hai tham số `toMap(keyMapper, valueMapper)`, cần chấp nhận Map được triển khai bằng loại không được bảo đảm và ngoại lệ khi gặp khóa trùng.

### 3.1. Dùng `HashMap` cho tra cứu thông thường

```java
import java.util.HashMap;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(String sku, String name) {}

List<Product> products = List.of(
    new Product("P-01", "Bàn"),
    new Product("P-02", "Ghế")
);

HashMap<String, Product> bySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Function.identity(),
        (first, second) -> second,
        HashMap::new
    ));

System.out.println(bySku.get("P-01").name()); // Bàn
```

`HashMap` thích hợp khi chỉ cần tra cứu `get(key)` và **không dùng thứ tự duyệt làm hợp đồng**. Việc kết quả có vẻ được sắp xếp ở một lần chạy không có nghĩa `HashMap` bảo đảm thứ tự.

### 3.2. Dùng `LinkedHashMap` để giữ thứ tự chèn

Giả sử dữ liệu đến theo thứ tự `P-03`, `P-01`, `P-02` và màn hình cần duyệt các SKU theo chính thứ tự xuất hiện:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

List<Product> products = List.of(
    new Product("P-03", "Đèn"),
    new Product("P-01", "Bàn"),
    new Product("P-02", "Ghế")
);

LinkedHashMap<String, String> namesBySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (existing, incoming) -> incoming,
        LinkedHashMap::new
    ));

System.out.println(namesBySku.keySet()); // [P-03, P-01, P-02]
```

`LinkedHashMap` mặc định duyệt theo **thứ tự chèn khóa**, không tự sắp xếp theo giá trị hoặc khóa. Trong pipeline **tuần tự** và nguồn `List` có thứ tự như ví dụ, thứ tự đó phản ánh lần gặp đầu của mỗi SKU.

Với khóa trùng, một lần thay giá trị bằng `Map.merge` không khiến khóa cũ tự chuyển xuống cuối trong `LinkedHashMap` mặc định. Nếu nghiệp vụ muốn thứ tự **truy cập gần nhất**, đó là cơ chế khác của `LinkedHashMap` (access order) và phải thiết kế riêng; đừng mặc nhiên hiểu `LinkedHashMap::new` là access order.

### 3.3. Dùng `TreeMap` để sắp xếp theo khóa

```java
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

List<Product> products = List.of(
    new Product("P-03", "Đèn"),
    new Product("P-01", "Bàn"),
    new Product("P-02", "Ghế")
);

TreeMap<String, String> sorted = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (first, second) -> second,
        TreeMap::new
    ));

System.out.println(sorted.keySet()); // [P-01, P-02, P-03]
```

`TreeMap::new` ở đây dùng thứ tự tự nhiên của `String`. Thứ tự tự nhiên này **không phải bộ quy tắc xếp chữ theo ngôn ngữ Việt**. Nếu nghiệp vụ yêu cầu so sánh theo ngôn ngữ hoặc kiểu không có natural ordering, cần chọn comparator phù hợp.

Ví dụ sắp xếp khóa theo thứ tự ngược:

```java
import java.util.Comparator;

TreeMap<String, String> descending = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Product::name,
        (oldValue, newValue) -> newValue,
        () -> new TreeMap<>(Comparator.reverseOrder())
    ));

System.out.println(descending.keySet()); // [P-03, P-02, P-01]
```

Với `TreeMap`, comparator **không chỉ ảnh hưởng thứ tự**; nó còn xác định hai khóa nào được xem là tương đương thông qua `compare(k1, k2) == 0`. Đây là điểm rất quan trọng khi xử lý khóa trùng.

## 4. Comparator của `TreeMap` có thể làm xuất hiện khóa trùng

Xét hai chuỗi `"API"` và `"api"`. `String.equals` xem chúng khác nhau, nhưng `String.CASE_INSENSITIVE_ORDER` so sánh chúng bằng 0.

```java
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

List<String> tags = List.of("API", "api", "Java");

TreeMap<String, Integer> counts = tags.stream()
    .collect(Collectors.toMap(
        tag -> tag,
        tag -> 1,
        Integer::sum,
        () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(counts.size());       // 2
System.out.println(counts.get("API"));   // 2
System.out.println(counts.get("api"));   // 2
System.out.println(counts.get("Java"));  // 1
```

Dù `"API"` và `"api"` khác nhau khi gọi `equals`, Map này xem chúng là một khóa logic. Hàm `Integer::sum` gộp hai giá trị thành 2.

Đây có thể là chủ đích nghiệp vụ (gộp khóa không phân biệt hoa/thường), nhưng cũng có thể là lỗi nếu mã định danh phải phân biệt chữ hoa. Một comparator không nhất quán với `equals` còn có thể làm việc tuân thủ đầy đủ hợp đồng `Map` trở nên khó khăn khi trao đổi với các kiểu Map khác; hãy chọn ngữ nghĩa khóa có chủ đích và kiểm thử.

Không dùng comparator chỉ để “trang trí cách hiển thị” nếu nó có thể hợp nhất các khóa cần giữ riêng. Nếu chỉ muốn hiển thị theo thứ tự tùy chỉnh, đôi khi nên giữ Map gốc và **sắp xếp tập entry khi xuất báo cáo**.

## 5. `mergeFunction` giải quyết va chạm khóa thế nào?

Bất kỳ collector đưa nhiều phần tử vào Map đều cần một chiến lược khi khóa bị lặp.

```java
record Price(String sku, long amountVnd) {}

List<Price> prices = List.of(
    new Price("P-01", 100_000L),
    new Price("P-02", 200_000L),
    new Price("P-01",  50_000L)
);
```

Các lựa chọn:

| Chính sách | Hàm merge | Kết quả cho `P-01` |
| --- | --- | --- |
| Giữ giá trị cũ trong pipeline tuần tự | `(oldValue, incoming) -> oldValue` | `100000` |
| Giữ giá trị mới trong pipeline tuần tự | `(oldValue, incoming) -> incoming` | `50000` |
| Cộng giá trị | `Long::sum` | `150000` |
| Lấy lớn nhất | `Long::max` | `100000` |
| Báo lỗi nếu khóa trùng | Ném `IllegalStateException` | Thu thập thất bại |

Ví dụ cộng giá trị và giữ thứ tự xuất hiện của từng khóa:

```java
import java.util.LinkedHashMap;
import java.util.stream.Collectors;

LinkedHashMap<String, Long> totals = prices.stream()
    .collect(Collectors.toMap(
        Price::sku,
        Price::amountVnd,
        Long::sum,
        LinkedHashMap::new
    ));

System.out.println(totals); // {P-01=150000, P-02=200000}
```

Nếu khóa phải **duy nhất**, không nên âm thầm lấy bản ghi đầu hoặc cuối. Hãy khai báo chính sách phát hiện lỗi:

```java
HashMap<String, Price> unique = prices.stream()
    .collect(Collectors.toMap(
        Price::sku,
        java.util.function.Function.identity(),
        (left, right) -> {
            throw new IllegalStateException(
                "Trùng SKU: " + left.sku()
            );
        },
        HashMap::new
    ));
// Ví dụ cố ý phát sinh ngoại lệ vì P-01 xuất hiện hai lần.
```

**Lưu ý về song song:** Các phép gộp như `Long::sum`, `Long::max` có tính kết hợp theo phép toán được chọn và dễ lý giải khi chia nhóm. Chính sách “giữ giá trị mới nhất theo thời gian” nên so sánh **timestamp hoặc revision thực sự** trong dữ liệu thay vì dựa mơ hồ vào thời điểm một nhánh song song chạy xong. Nếu phải phân xử các bản ghi có cùng revision, hãy định nghĩa rõ cách phá hòa.

Một merge function trả về `null` có thể khiến entry bị xóa theo hợp đồng `Map.merge`; đây thường **không phải** cách mong muốn để xử lý khóa trùng và cần được tránh nếu nghiệp vụ không có quy tắc xóa cụ thể.

## 6. Chọn Map cho `Collectors.groupingBy`

`groupingBy` thường có dạng nhận **classifier** (hàm chọn khóa) và downstream collector. Overload cho phép chọn Map:

```java
public static <T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Khác biệt đáng nhớ: `groupingBy` **không nhận mergeFunction trực tiếp**. Nó đưa các phần tử cùng khóa vào **downstream collector** của nhóm đó. `mapFactory` được đặt ở **tham số thứ hai**, trước downstream.

### 6.1. `LinkedHashMap`: nhóm theo thứ tự gặp lần đầu

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, String sku, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("Nam",   "P-01", 100_000L),
    new Sale("Bắc",   "P-02",  50_000L),
    new Sale("Nam",   "P-03", 150_000L),
    new Sale("Trung", "P-04",  70_000L)
);

LinkedHashMap<String, Long> revenueByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(revenueByRegion);
// {Nam=250000, Bắc=50000, Trung=70000}
```

Với nguồn `List` và pipeline tuần tự, khóa được thêm theo thứ tự lần đầu gặp: `Nam`, `Bắc`, `Trung`. Trong mỗi nhóm, `summingLong` cộng toàn bộ doanh thu. Lưu ý tổng `long` vẫn có thể tràn nếu dữ liệu vượt giới hạn số nguyên 64 bit.

### 6.2. `TreeMap`: thống kê theo khóa đã sắp xếp

```java
import java.util.TreeMap;

TreeMap<String, Long> sortedRevenue = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(sortedRevenue.keySet());
// [Bắc, Nam, Trung] theo natural ordering của String.
```

`TreeMap` giữ thứ tự khóa theo comparator hoặc natural ordering, không theo thứ tự gặp dữ liệu. Nếu cần bảng xuất báo cáo có thứ tự khóa ổn định, đây là một lựa chọn rõ ý nghĩa.

### 6.3. `EnumMap`: nhóm theo enum

Khi khóa thuộc một enum xác định, `EnumMap` là lựa chọn phù hợp và thường gọn hơn Map dựa trên hash tổng quát.

```java
import java.util.EnumMap;
import java.util.List;
import java.util.stream.Collectors;

enum Status { CREATED, PAID, CANCELLED }
record Order(String id, Status status) {}

List<Order> orders = List.of(
    new Order("O-01", Status.PAID),
    new Order("O-02", Status.CREATED),
    new Order("O-03", Status.PAID)
);

EnumMap<Status, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::status,
        () -> new EnumMap<>(Status.class),
        Collectors.counting()
    ));

System.out.println(counts);
// {CREATED=1, PAID=2}
```

`EnumMap` duyệt theo **thứ tự khai báo của enum**, không theo thứ tự gặp bản ghi. Nhóm `CANCELLED` không có phần tử nên **không tự có entry** trong kết quả.

Nếu báo cáo yêu cầu đầy đủ tất cả trạng thái kể cả số lượng bằng 0, có thể bổ sung tường minh sau khi thu thập:

```java
for (Status status : Status.values()) {
    counts.putIfAbsent(status, 0L);
}

System.out.println(counts);
// {CREATED=1, PAID=2, CANCELLED=0}
```

Khi đó mọi khóa hợp lệ của enum đều hiện diện. Nếu chỉ quan tâm trạng thái có dữ liệu, không cần bước bổ sung.

## 7. `MapFactory` và collector đồng thời

Khi cần thu thập trên nhiều luồng và thực sự muốn cơ chế concurrent accumulation, Java cung cấp các collector khác:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction, mapFactory)
Collectors.groupingByConcurrent(classifier, mapFactory, downstream)
```

Điểm khác biệt quan trọng:

- `toMap` và `groupingBy` có thể dùng với **parallel Stream**, bằng cách tạo các Map trung gian rồi kết hợp. Việc chúng dùng `HashMap` hoặc `LinkedHashMap` không có nghĩa từng Map được nhiều luồng cập nhật đồng thời.
- `toConcurrentMap` và `groupingByConcurrent` cung cấp các collector **concurrent, unordered**. Khi được phép về mặt ngữ nghĩa, việc tích lũy có thể diễn ra đồng thời trong cùng một container.
- `mapFactory` của các collector concurrent phải cung cấp kiểu `M extends ConcurrentMap<K, V>`, không phải `HashMap` hay `LinkedHashMap`.

### 7.1. Dùng `ConcurrentHashMap`

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

record Payment(String region, long amountVnd) {}

List<Payment> payments = List.of(
    new Payment("Nam", 100_000L),
    new Payment("Bắc",  50_000L),
    new Payment("Nam", 200_000L)
);

ConcurrentHashMap<String, Long> totals = payments.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Payment::region,
        Payment::amountVnd,
        Long::sum,
        ConcurrentHashMap::new
    ));

System.out.println(totals.get("Nam")); // 300000
System.out.println(totals.get("Bắc")); // 50000
```

`ConcurrentHashMap` không bảo đảm thứ tự duyệt các khóa. Phép cộng `Long::sum` là chính sách merge phù hợp cho tổng nhóm khi phạm vi `long` đủ.

**Không** dùng `ConcurrentHashMap` chỉ để được phép gọi `parallelStream()`. Nếu dữ liệu nhỏ hoặc yêu cầu giữ thứ tự, phương án tuần tự với Map thích hợp có thể đơn giản và nhanh hơn.

### 7.2. Dùng `ConcurrentSkipListMap` khi cần vừa concurrent vừa sắp khóa

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> sortedTotals =
    payments.parallelStream()
        .collect(Collectors.toConcurrentMap(
            Payment::region,
            Payment::amountVnd,
            Long::sum,
            ConcurrentSkipListMap::new
        ));

System.out.println(sortedTotals.keySet()); // [Bắc, Nam]
```

`ConcurrentSkipListMap` là một `ConcurrentNavigableMap`, nên việc duyệt khóa tuân theo thứ tự đã định của comparator/natural ordering. Nhưng collector vẫn có đặc tính `UNORDERED`: thứ tự **gặp phần tử nguồn** không được bảo đảm như một danh sách. Thứ tự của `keySet()` ở ví dụ là **thứ tự khóa đã sắp xếp**, hai khái niệm khác nhau.

### 7.3. `groupingByConcurrent` với mapFactory

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> countsByRegion =
    payments.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            Payment::region,
            ConcurrentSkipListMap::new,
            Collectors.counting()
        ));
```

Bảng kết quả `countsByRegion` sắp khóa theo thứ tự tự nhiên. `Collectors.counting()` là downstream collector cho số phần tử mỗi nhóm. Không suy từ chữ “Concurrent” rằng mọi downstream collector hoặc mỗi thao tác tích lũy trên từng giá trị đều **không khóa**; việc triển khai có thể cần phối hợp để giữ tính đúng.

## 8. Một ví dụ Java 17 hoàn chỉnh với bốn lựa chọn Map

Ví dụ bên dưới có thể biên dịch và chạy độc lập; các phần khác trong bài là snippet dùng các kiểu được khai báo trong mục tương ứng.

```java
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapFactoryDemo {

    enum Status { NEW, PAID, REFUNDED }

    record Order(String id, String region, Status status, long amountVnd) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-02", "Nam", Status.PAID,     120_000L),
            new Order("O-01", "Bắc", Status.NEW,       80_000L),
            new Order("O-02", "Nam", Status.REFUNDED,  120_000L),
            new Order("O-03", "Trung", Status.PAID,    200_000L)
        );

        // 1. Mã đơn theo thứ tự xuất hiện lần đầu; bản ghi sau ghi đè
        // giá trị cũ nếu trùng mã trong luồng tuần tự.
        LinkedHashMap<String, Order> byId = orders.stream()
            .collect(Collectors.toMap(
                Order::id,
                Function.identity(),
                (existing, incoming) -> incoming,
                LinkedHashMap::new
            ));

        // 2. Nhóm doanh thu đơn PAID; khóa region được sắp xếp.
        TreeMap<String, Long> paidByRegion = orders.stream()
            .filter(order -> order.status() == Status.PAID)
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                Collectors.summingLong(Order::amountVnd)
            ));

        // 3. Nhóm theo enum, duyệt theo thứ tự khai báo enum.
        EnumMap<Status, Long> countByStatus = orders.stream()
            .collect(Collectors.groupingBy(
                Order::status,
                () -> new EnumMap<>(Status.class),
                Collectors.counting()
            ));

        // 4. Tổng hợp song song vào ConcurrentMap có thứ tự khóa.
        ConcurrentSkipListMap<String, Long> paidParallel =
            orders.parallelStream()
                .filter(order -> order.status() == Status.PAID)
                .collect(Collectors.toConcurrentMap(
                    Order::region,
                    Order::amountVnd,
                    Long::sum,
                    ConcurrentSkipListMap::new
                ));

        System.out.println(byId.keySet());
        System.out.println(byId.get("O-02").status());
        System.out.println(paidByRegion);
        System.out.println(countByStatus);
        System.out.println(paidParallel);
    }
}
```

Kết quả dự kiến:

```text
[O-02, O-01, O-03]
REFUNDED
{Nam=120000, Trung=200000}
{NEW=1, PAID=2, REFUNDED=1}
{Nam=120000, Trung=200000}
```

Bốn Map có mục đích khác nhau: `LinkedHashMap` giữ thứ tự chèn khóa, `TreeMap` sắp khóa khu vực, `EnumMap` sắp khóa theo enum, còn `ConcurrentSkipListMap` cho phép tích lũy concurrent và giữ thứ tự khóa. Không phải mọi bài toán đều cần bốn collector; ví dụ chỉ giúp so sánh tác động của lựa chọn `mapFactory`.

## 9. `null`, khóa trùng và hợp đồng của từng Map

### 9.1. `null` không được xử lý giống nhau ở mọi collector

`HashMap` cho phép một khóa `null` trong API Map thông thường; `ConcurrentHashMap` và `ConcurrentSkipListMap` không cho phép khóa/giá trị `null`. `TreeMap` dùng natural ordering không cho phép khóa `null`. `EnumMap` không cho phép khóa `null`.

Hơn nữa, **collector có hợp đồng riêng**:

- `Collectors.groupingBy` không chấp nhận classifier trả về `null`, ngay cả khi `mapFactory` trả về `HashMap`. Nhãn nhóm phải được chuẩn hóa, lọc hoặc thay bằng khóa có ý nghĩa.
- `Collectors.toMap` không nên được dùng với `valueMapper` có thể trả về `null`. Các overload có merge dùng `Map.merge`, vốn từ chối giá trị được đưa vào là `null`. Để biểu diễn “thiếu giá trị”, cân nhắc `Optional` hoặc xử lý dữ liệu trước.
- Với `Collectors.toConcurrentMap`, khóa và giá trị `null` không hợp lệ theo hợp đồng `ConcurrentMap` tương ứng.

Ví dụ chuẩn hóa khóa nhóm rỗng thành nhãn có ý nghĩa:

```java
import java.util.HashMap;
import java.util.stream.Collectors;

record User(String city) {}

List<User> users = List.of(
    new User("Hà Nội"), new User(null), new User("Hà Nội")
);

HashMap<String, Long> counts = users.stream()
    .collect(Collectors.groupingBy(
        user -> user.city() == null ? "CHUA_XAC_DINH" : user.city(),
        HashMap::new,
        Collectors.counting()
    ));

System.out.println(counts.get("CHUA_XAC_DINH")); // 1
```

Khi dùng giá trị đại diện cho `null`, phải chọn một khóa không xung đột với giá trị hợp lệ của nghiệp vụ. Trong các hệ thống lớn, có thể dùng kiểu khóa riêng thay vì một chuỗi cố định.

### 9.2. Coi Comparator là một phần của quy tắc khóa

Trong `TreeMap`, hai khóa trùng nếu comparator báo bằng 0, ngay cả khi `equals` khác. Vì vậy phải kiểm thử cả **so sánh khóa**, **mergeFunction** và **loại Map** như một bộ thống nhất.

### 9.3. Vì sao không dùng `IdentityHashMap` tùy tiện?

`IdentityHashMap` so sánh khóa theo **tham chiếu (`==`)** thay vì `equals`. Đây là hợp đồng khác với phần lớn quy tắc tra cứu khóa nghiệp vụ. `mapFactory` không phải nơi thay đổi ngữ nghĩa khóa một cách vô tình; chỉ dùng cấu trúc như vậy khi bài toán thật sự cần so sánh danh tính đối tượng.

## 10. Khi muốn Map không thể sửa

`mapFactory` quyết định cấu trúc Map **được tạo**, nhưng không mặc nhiên tạo một Map bất biến.

Có hai mục tiêu riêng:

1. Chọn cách lưu khóa (`LinkedHashMap`, `TreeMap`, `EnumMap`,...).
2. Quy định bên nhận kết quả có được phép `put`/`remove` hay không.

Để tạo kết quả không thể sửa, có thể dùng `collectingAndThen` với bước hoàn tất:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> stableNames = products.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            Product::sku,
            Product::name,
            (first, second) -> second,
            LinkedHashMap::new
        ),
        collected -> Collections.unmodifiableMap(
            new LinkedHashMap<>(collected)
        )
    ));

// stableNames.put("P-99", "Mới"); // UnsupportedOperationException
```

Bản sao `new LinkedHashMap<>(collected)` giữ thứ tự duyệt và tách kết quả khỏi Map tích lũy bên trong; `Collections.unmodifiableMap` cung cấp một **view không cho phép chỉnh sửa** trên bản sao đó. Nếu các *giá trị* là đối tượng mutable, việc bọc Map không làm đối tượng giá trị trở nên bất biến sâu.

`Map.copyOf(map)` tạo kết quả không thể sửa nhưng **không bảo đảm thứ tự duyệt giống `LinkedHashMap`**. Đừng dùng nó nếu thứ tự là một phần bắt buộc của hợp đồng đầu ra.

`Collectors.toUnmodifiableMap` cũng tạo Map không thể sửa và có overload xử lý khóa trùng, nhưng **không có tham số mapFactory**. Nếu yêu cầu vừa sắp khóa theo một comparator vừa đóng băng khả năng chỉnh sửa, hãy thiết kế bước hoàn tất phù hợp.

## 11. Stream tuần tự, song song và điều kiện về thứ tự

Cần phân biệt ba khái niệm:

- **Encounter order**: thứ tự phần tử của nguồn Stream, chẳng hạn thứ tự phần tử của `List`.
- **Insertion order**: thứ tự mà Map lưu lần thêm **khóa mới**, như `LinkedHashMap`.
- **Key order**: thứ tự khóa theo comparator hoặc natural ordering, như `TreeMap`.

Ba thứ tự này không tương đương. Ví dụ mã xuất hiện `P-03, P-01, P-02`:

```text
Nguồn List (encounter)       : P-03 → P-01 → P-02
LinkedHashMap (insertion)    : P-03 → P-01 → P-02
TreeMap (key order)          : P-01 → P-02 → P-03
ConcurrentHashMap            : không có thứ tự duyệt được bảo đảm
```

Một collector có `mapFactory` trả về `LinkedHashMap` không tự làm mọi nguồn song song đều có thứ tự ngữ nghĩa rõ ràng. Nếu thứ tự nguồn vốn không được định nghĩa (ví dụ dữ liệu từ một `HashSet`), không thể khôi phục thứ tự có ý nghĩa bằng cách chỉ đổi Map.

Với các collector concurrent có đặc tính `UNORDERED`, không dùng thứ tự tích lũy để diễn giải “phần tử đầu”, “phần tử cuối” hoặc “phiên bản mới nhất”. Nếu cần điều kiện đó, định nghĩa tiêu chí so sánh trực tiếp trong giá trị hoặc đưa ra cách sắp xếp trước khi xuất kết quả.

### Vì sao `parallel()` không tự động cải thiện hiệu năng?

Đối với `toMap` không concurrent, việc ghép nhiều Map trung gian có thể tốn thời gian khi số lượng khóa rất lớn. Đối với `toConcurrentMap`, nhiều luồng tranh chấp cùng khóa cũng có thể làm giảm hiệu năng. Kết quả phụ thuộc phân bố khóa, số phần tử, chi phí ánh xạ, kiểu Map và cách chia dữ liệu qua `Spliterator`.

Nếu tốc độ quan trọng, hãy đo bằng dữ liệu đại diện và công cụ phù hợp như JMH, sau khi kiểm tra kết quả đúng. Tránh bật `parallelStream()` chỉ vì collector có chữ “Concurrent”.

## 12. Chọn `toMap` hay `groupingBy`?

| Bài toán | Collector thường hợp lý | Map factory ví dụ |
| --- | --- | --- |
| Mỗi khóa có đúng một giá trị và khóa duy nhất | `toMap(keyMapper, valueMapper, mergeFunction, factory)` | `HashMap::new` |
| Khóa có thể trùng, muốn chọn/gộp **một giá trị** | `toMap(..., mergeFunction, factory)` | `LinkedHashMap::new` |
| Muốn một `List<T>` cho mỗi khóa | `groupingBy(classifier, factory, toList())` | `LinkedHashMap::new` |
| Muốn số lượng/tổng/giá trị tổng hợp cho mỗi khóa | `groupingBy(classifier, factory, counting()/summingLong(...))` | `TreeMap::new` |
| Khóa là enum | `groupingBy(classifier, EnumMap supplier, downstream)` | `() -> new EnumMap<>(Status.class)` |
| Muốn cập nhật concurrent và không phụ thuộc encounter order | `toConcurrentMap(...)` hoặc `groupingByConcurrent(...)` | `ConcurrentHashMap::new` |
| Cần Map có thứ tự khóa và hỗ trợ concurrent | Collector concurrent với `ConcurrentSkipListMap` | `ConcurrentSkipListMap::new` |

`groupingBy` không bắt buộc phải tạo danh sách. Downstream collector có thể là `counting`, `summingLong`, `mapping`, `reducing` hoặc một collector tùy chỉnh. Chọn `mapFactory` giải quyết lớp **container ngoài**, còn downstream giải quyết cách tạo **giá trị cho mỗi khóa**.

Nếu chỉ có một giá trị cho mỗi khóa và không cần nhóm nhiều phần tử, `toMap` thường trực tiếp hơn.

## 13. Lưu ý tính lazy, tài nguyên và dữ liệu

`filter` và `map` là thao tác trung gian; `collect` là **terminal operation** kích hoạt pipeline.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> data = List.of("a", "bb", "ccc");

var pipeline = data.stream()
    .filter(text -> !text.isBlank()); // Chưa xử lý cho đến terminal.

Map<Integer, String> byLength = pipeline.collect(Collectors.toMap(
    String::length,
    text -> text,
    (first, second) -> first,
    HashMap::new
));

// pipeline.count(); // Không được tiêu thụ Stream thêm lần nữa.
```

Map thường cần giữ ít nhất một entry cho mỗi khóa khác nhau, nên bộ nhớ có thể tỷ lệ với **số khóa duy nhất**; với `groupingBy(..., toList())`, bộ nhớ còn phải lưu các phần tử của từng nhóm.

Khi nguồn gắn với I/O, ví dụ `Files.lines(path)`, sử dụng `try-with-resources` để đóng Stream dù terminal operation là `collect`. Việc gọi `mapFactory` không có nghĩa tài nguyên đọc tệp tự đóng.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Đặt trong phương thức khai báo throws IOException hoặc xử lý ngoại lệ.
try (Stream<String> lines = Files.lines(Path.of("codes.txt"))) {
    Map<String, Long> frequency = lines
        .filter(line -> !line.isBlank())
        .collect(Collectors.groupingBy(
            line -> line,
            TreeMap::new,
            Collectors.counting()
        ));
    System.out.println(frequency);
}
```

Nếu nguồn dữ liệu có thể thay đổi khi pipeline chạy, hãy xác định chính sách đọc nhất quán; `mapFactory` không xử lý tranh chấp khi nguồn bị thay đổi. Không sửa `List` nguồn trong `keyMapper` hay `valueMapper`.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Mong `Collectors.toMap(key, value)` luôn trả `HashMap` có thứ tự nhất định | Không có bảo đảm về kiểu/thứ tự | Dùng overload có `mapFactory` nếu kiểu Map là yêu cầu |
| Truyền `LinkedHashMap::new` làm tham số thứ ba của `toMap` | Sai overload: tham số thứ ba là merge function | Dùng đủ bốn tham số `toMap(key, value, merge, factory)` |
| Truyền `mergeFunction` vào vị trí thứ hai của `groupingBy` | Sai API | Dùng `groupingBy(classifier, mapFactory, downstream)` |
| Bỏ qua khóa trùng trong `toMap` | Có thể ném `IllegalStateException` hoặc mất dữ liệu theo chính sách sai | Định nghĩa rõ merge function, kiểm thử trùng |
| Chọn `TreeMap` comparator coi hai khóa khác nhau là bằng nhau | Hai khóa bị gộp bất ngờ | Kiểm tra quy tắc so sánh và ý nghĩa khóa |
| Dùng `HashMap` rồi dựa vào thứ tự vòng `entrySet()` | Thứ tự hiển thị không được bảo đảm | Dùng `LinkedHashMap` hoặc `TreeMap` đúng mục đích |
| Dùng `groupingBy` với classifier trả `null` | Ngoại lệ | Chuẩn hóa hoặc lọc khóa trước |
| Dùng `toMap` với `valueMapper` trả `null` | Có thể ném `NullPointerException` | Xử lý dữ liệu thiếu tường minh |
| Dùng `HashMap::new` làm factory cho `toConcurrentMap` | Không khớp ràng buộc `ConcurrentMap` | Dùng `ConcurrentHashMap::new` hoặc `ConcurrentSkipListMap::new` |
| Bật `CONCURRENT` bằng cách tự chia sẻ một `HashMap` | Race condition, sai kết quả | Dùng collector concurrent đúng hợp đồng |
| Dùng merge “giá trị cuối” để chọn bản mới nhất trong luồng unordered | Không xác định theo thời gian nghiệp vụ | So sánh timestamp/revision tường minh |
| Coi `mapFactory` là cách tạo Map không thể sửa | Map vẫn có thể sửa | Dùng finisher/bản sao không thể sửa |
| Cho rằng `Map.copyOf(LinkedHashMap)` giữ thứ tự duyệt | Thứ tự Map copy không được bảo đảm | Dùng bản sao `LinkedHashMap` và wrapper phù hợp |
| Cho rằng song song luôn nhanh với `ConcurrentHashMap` | Tranh chấp khóa và overhead có thể tăng | Đo trên dữ liệu đại diện |

## 15. Bài tập thực hành

### Bài 1: Tra cứu sản phẩm theo SKU

Tạo danh sách sản phẩm có `sku` và `name`; dùng `toMap` với `HashMap::new` để tra cứu. Thử trùng SKU và xây chính sách ném ngoại lệ. Giải thích vì sao không nên âm thầm chọn một giá trị nếu SKU phải duy nhất.

### Bài 2: Giữ thứ tự hiển thị

Cho SKU `P-04`, `P-02`, `P-01` trong `List`. Dùng `LinkedHashMap::new` rồi dùng `TreeMap::new` cho cùng dữ liệu. In `keySet()` và giải thích khác nhau giữa insertion order và key order.

### Bài 3: Cộng tiền theo khu vực

Tạo `List<Sale>` với nhiều đơn trùng vùng. So sánh `toMap(Sale::region, Sale::amountVnd, Long::sum, TreeMap::new)` với `groupingBy(Sale::region, TreeMap::new, summingLong(Sale::amountVnd))`. Hai cách giải quyết vấn đề khác nhau ở điểm nào?

### Bài 4: Khóa enum

Tạo enum `Level { LOW, MEDIUM, HIGH }` và danh sách cảnh báo. Dùng `EnumMap` với `groupingBy` để đếm cảnh báo theo cấp. Tại sao cấp không có cảnh báo không tự xuất hiện trong Map, và làm thế nào để thêm cấp đó với giá trị 0?

### Bài 5: Comparator và khóa trùng

Gộp `["API", "api", "Java"]` vào `TreeMap` dùng `String.CASE_INSENSITIVE_ORDER`. Thử `Integer::sum` và một merge function ném lỗi. Giải thích vì sao `"API"` và `"api"` là khóa trùng theo Map này.

### Bài 6: Thu thập đồng thời

Với một triệu phép thanh toán chỉ thuộc vài khu vực, so sánh `toMap(..., HashMap::new)`, `toConcurrentMap(..., ConcurrentHashMap::new)` và `toConcurrentMap(..., ConcurrentSkipListMap::new)`. Dự đoán ảnh hưởng của việc nhiều bản ghi cùng một khóa; đo thực tế trước khi kết luận.

### Bài 7: Báo cáo không thể sửa nhưng giữ thứ tự

Từ `List<Product>`, thu thập vào `LinkedHashMap` rồi dùng `collectingAndThen` để tạo một bản sao có thứ tự và view không thể sửa. Thử `put` và kiểm tra thứ tự `keySet()` sau khi thu thập.

## 16. Tự kiểm tra kiến thức

- `mapFactory` nhận kiểu functional interface nào và tạo ra cái gì?
- Vì sao `toMap` cần **bốn tham số** khi chỉ định `mapFactory`?
- `mapFactory` nằm ở vị trí nào trong overload `groupingBy`?
- `LinkedHashMap` và `TreeMap` khác nhau về thứ tự duyệt như thế nào?
- Comparator của `TreeMap` liên quan gì đến việc xác định hai khóa trùng nhau?
- Khi nào `EnumMap` phù hợp hơn một Map thông thường?
- Factory dùng trong `toConcurrentMap` cần trả về loại Map nào?
- Collector concurrent có bảo đảm thứ tự gặp của nguồn không?
- Vì sao `Map.copyOf` không phải lựa chọn tốt nếu cần giữ thứ tự chèn?
- Khi nào dùng `groupingBy` thay vì `toMap`?
- Vì sao việc chỉ đổi mapFactory không tự khắc phục lỗi null, khóa trùng hay tràn số?
- Những chi phí nào cần đo khi so sánh xử lý tuần tự và song song?

**Ghi nhớ:** `mapFactory` là cách chỉ định **Map được tạo bởi collector**. Chọn `HashMap` khi chỉ cần tra cứu, `LinkedHashMap` khi cần thứ tự chèn, `TreeMap` khi cần sắp khóa, `EnumMap` cho khóa enum và `ConcurrentMap` cho các collector tích lũy đồng thời. Luôn thiết kế cùng lúc chính sách **khóa trùng, comparator, null, thứ tự và tính đúng khi song song** trước khi tối ưu hiệu năng.
