# Chuyển Stream thành Map bằng Collectors.toMap

Trong chương **Thu thập thành Map** của **Java Stream API**, nhiều bài toán cần biến một dãy đối tượng thành cấu trúc tra cứu theo khóa: mã sản phẩm → sản phẩm, mã nhân viên → tên, mã khách hàng → tổng doanh thu. `Collectors.toMap` là collector dùng để tạo `Map<K, V>` từ các phần tử của một Stream bằng cách xác định **khóa** và **giá trị** cho từng phần tử.

Điểm phải thiết kế trước là **khóa có duy nhất không**. Nếu nhiều phần tử tạo cùng một khóa, phiên bản `toMap` đơn giản sẽ ném ngoại lệ; khi đó phải chọn chính sách xử lý xung đột, hoặc chuyển sang collector nhóm nhiều giá trị như `groupingBy`. Những vấn đề khác cũng quan trọng: kiểu `Map` cần nhận, quy tắc thứ tự, xử lý `null`, an toàn khi chạy song song và chi phí giữ dữ liệu trong bộ nhớ.

Bài này xây dựng từ ví dụ cơ bản đến xử lý khóa trùng, tổng hợp dữ liệu và thiết kế collector theo hợp đồng nghiệp vụ.

## 1. Bài toán: tra cứu nhanh theo khóa

Giả sử dữ liệu đầu vào là một `List<Product>`. Mỗi sản phẩm có một mã `sku` duy nhất; hệ thống thường xuyên cần tìm giá bán theo mã.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ProductIndexDemo {

    record Product(String sku, String name, BigDecimal price) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("PEN", "Bút", new BigDecimal("12000")),
                new Product("BOOK", "Sách", new BigDecimal("50000")),
                new Product("BAG", "Túi", new BigDecimal("95000"))
        );

        Map<String, BigDecimal> priceBySku = products.stream()
                .collect(Collectors.toMap(
                        Product::sku,
                        Product::price
                ));

        System.out.println(priceBySku.get("BOOK"));       // 50000
        System.out.println(priceBySku.containsKey("PEN")); // true
        System.out.println(priceBySku.size());             // 3
    }
}
~~~

Trong pipeline này:

1. `products.stream()` tạo Stream các `Product`.
2. `Product::sku` là **key mapper**: mỗi sản phẩm sinh một khóa kiểu `String`.
3. `Product::price` là **value mapper**: mỗi sản phẩm sinh một giá trị kiểu `BigDecimal`.
4. `collect(Collectors.toMap(...))` là **terminal operation**: nó kích hoạt pipeline, tích lũy các cặp khóa–giá trị và trả về `Map<String, BigDecimal>`.

Sau khi thu thập, có thể dùng `get(key)`, `containsKey(key)` và các phương thức `Map` thông thường. Dù vậy, `Map` không phải bản sao tự động của toàn bộ đối tượng nguồn: trong ví dụ nó chỉ giữ mã và giá.

> **Điều kiện ngầm của overload hai tham số:** Mỗi khóa phải xuất hiện tối đa một lần trong kết quả ánh xạ. `toMap` không tự động chọn giá trị đầu tiên hoặc giá trị cuối cùng khi khóa trùng.

## 2. Hiểu vai trò của key mapper và value mapper

Chữ ký khái quát của overload cơ bản là:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper)
~~~

Ở đây:

| Thành phần | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử Stream | `Product` |
| `K` | Kiểu khóa của Map | `String` |
| `U` | Kiểu giá trị của Map | `BigDecimal` |
| `keyMapper` | Hàm chuyển `T -> K` | `Product::sku` |
| `valueMapper` | Hàm chuyển `T -> U` | `Product::price` |
| Kết quả | Collector tạo `Map<K, U>` | `Map<String, BigDecimal>` |

Hai hàm ánh xạ **không bắt buộc trả chính phần tử đầu vào**. Chẳng hạn, lập chỉ mục toàn bộ đối tượng theo mã:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// products có kiểu List<Product>.
Map<String, Product> bySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Function.identity()
        ));

Product book = bySku.get("BOOK");
~~~

`Function.identity()` trả về chính phần tử nhận vào, nhờ vậy giá trị của Map là `Product`. Cách làm này thích hợp khi cần tìm cả đối tượng bằng khóa. Tuy nhiên, Map vẫn giữ tham chiếu đến `Product` gốc; nó không tự sao chép sâu các trường dữ liệu.

Khóa cũng có thể là một loại khác, chẳng hạn số nguyên:

~~~java
record Worker(int id, String name) {}

Map<Integer, String> nameById = workers.stream()
        .collect(Collectors.toMap(
                Worker::id,
                Worker::name
        ));
~~~

Đoạn ví dụ giả định `workers` là một collection các `Worker`. Dạng mã này dễ đọc khi mỗi ID là duy nhất và giá trị không `null`.

## 3. Bốn dạng toMap cần nhớ

`Collectors` có bốn overload chính của `toMap`:

~~~java
// 1. Khóa phải duy nhất.
toMap(keyMapper, valueMapper)

// 2. Tự xử lý khi hai phần tử sinh cùng khóa.
toMap(keyMapper, valueMapper, mergeFunction)

// 3. Xử lý khóa trùng và chọn cách tạo Map kết quả.
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

Ba dòng trên là ba **cách gọi** (overload) thông dụng; thực tế `Collectors.toMap` có **ba overload**, theo chữ ký Java 8 trở lên. Mỗi overload sau bổ sung một chính sách rõ ràng.

| Overload | Khi nào dùng | Yêu cầu cần chú ý |
| --- | --- | --- |
| `toMap(k, v)` | Khóa đã duy nhất theo hợp đồng | Khóa trùng gây `IllegalStateException`. |
| `toMap(k, v, merge)` | Có thể trùng khóa; cần gộp/chọn giá trị | Hàm gộp phải diễn đạt đúng nghiệp vụ. |
| `toMap(k, v, merge, factory)` | Cần thêm loại Map cụ thể | Factory tạo Map mới, ví dụ `LinkedHashMap::new` hoặc `TreeMap::new`. |

Mặc định, đặc tả của `toMap` **không bảo đảm** loại Map, khả năng sửa đổi, tính serializable hay thread-safety của kết quả. Không nên thiết kế logic phụ thuộc vào việc một bản JDK hiện trả về `HashMap`.

> **Chú ý:** `Collectors.toUnmodifiableMap` và `Collectors.toConcurrentMap` là **các factory collector khác**, không phải overload bổ sung của `Collectors.toMap`. Chúng có hợp đồng riêng về tính không sửa đổi hoặc khả năng thu thập đồng thời.

## 4. Khóa trùng: lỗi quan trọng nhất khi dùng toMap

Một tập dữ liệu hợp lệ về mặt nghiệp vụ vẫn có thể chứa nhiều dòng chung mã sản phẩm:

~~~java
import java.util.List;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3)
);

var quantityBySku = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity
        )); // IllegalStateException vì PEN xuất hiện hai lần.
~~~

Hai dòng `PEN` đều sinh khóa `"PEN"`. Overload hai tham số **không tự ghi đè** giá trị cũ bằng giá trị mới; nó từ chối khóa trùng.

Thông báo thường có nội dung kiểu `Duplicate key ...`, nhưng chi tiết của chuỗi lỗi có thể khác theo phiên bản JDK. Điều quan trọng là điều kiện trùng khóa, được xác định theo cách Map so sánh khóa, thường dựa trên `equals` và `hashCode`.

Ngay cả khi **hai giá trị bằng nhau**, khóa trùng vẫn vi phạm hợp đồng overload này:

~~~java
List<Item> same = List.of(
        new Item("PEN", 2),
        new Item("PEN", 2)
);

// Vẫn báo duplicate key; không tự gộp chỉ vì cả hai quantity đều là 2.
same.stream().collect(Collectors.toMap(Item::sku, Item::quantity));
~~~

Nếu khóa phải duy nhất nhưng dữ liệu có trùng, ngoại lệ có thể là tín hiệu cần thiết để phát hiện dữ liệu không hợp lệ. Đừng vội bổ sung merge function chỉ để “cho chương trình chạy qua” nếu nghiệp vụ yêu cầu khóa duy nhất.

## 5. Dùng mergeFunction để quyết định giá trị khi khóa trùng

Overload ba tham số nhận thêm một `BinaryOperator<U>`:

~~~java
toMap(keyMapper, valueMapper, mergeFunction)
~~~

Khi khóa đã có giá trị, collector gọi hàm gộp với **giá trị đã tích lũy** và **giá trị mới**:

~~~text
merge(oldValue, incomingValue) -> mergedValue
~~~

### 5.1. Cộng số lượng cho các mã sản phẩm trùng

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3)
);

Map<String, Integer> quantityBySku = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));

System.out.println(quantityBySku.get("PEN"));  // 5
System.out.println(quantityBySku.get("BOOK")); // 1
~~~

`Integer::sum` gộp `2` và `3` thành `5`. Quy tắc này có tính kết hợp với phép cộng số nguyên theo ngữ nghĩa Java, nên thích hợp khi các kết quả trung gian được ghép trong parallel stream. Với dữ liệu thực, cần cân nhắc tràn `int`; nếu tổng có thể lớn hơn giới hạn, dùng `long` hoặc kiểu số thích hợp.

### 5.2. Chọn giá trị đầu hoặc cuối trong luồng có thứ tự

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Event(String id, String status) {}

List<Event> events = List.of(
        new Event("E-1", "NEW"),
        new Event("E-1", "CHECKED"),
        new Event("E-2", "NEW")
);

Map<String, String> keepFirst = events.stream()
        .collect(Collectors.toMap(
                Event::id,
                Event::status,
                (first, next) -> first
        ));

Map<String, String> keepLast = events.stream()
        .collect(Collectors.toMap(
                Event::id,
                Event::status,
                (first, next) -> next
        ));

System.out.println(keepFirst.get("E-1")); // NEW
System.out.println(keepLast.get("E-1"));  // CHECKED
~~~

Trên ví dụ **tuần tự từ List có thứ tự**, hai hàm trên thể hiện cách chọn giá trị của lần xuất hiện đầu tiên hoặc cuối cùng. Với dữ liệu **không có thứ tự encounter order**, khái niệm “đầu” và “cuối” không được xác định ổn định; không dùng cách đó khi nghiệp vụ cần bản ghi mới nhất theo thời gian.

Nếu muốn bản ghi có thời gian mới nhất, hãy **so sánh bằng timestamp thực**:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.stream.Collectors;

record StatusEvent(String id, Instant occurredAt, String status) {}

Map<String, StatusEvent> latest = statusEvents.stream()
        .collect(Collectors.toMap(
                StatusEvent::id,
                event -> event,
                (a, b) -> a.occurredAt().isAfter(b.occurredAt()) ? a : b
        ));
~~~

Đoạn trên giả định `statusEvents` là tập `StatusEvent` và các timestamp hợp lệ. Nếu hai thời điểm bằng nhau, ví dụ chọn `b`; trong hệ thống thật, cần thêm quy tắc phá hòa ổn định như sequence hoặc ID sự kiện để kết quả không phụ thuộc cách kết hợp.

### 5.3. Chọn lớn nhất hoặc cộng tiền

Khi giá trị có kiểu `BigDecimal`, có thể gộp bằng phép cộng chính xác:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> amountBySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                sale -> sale.unitPrice()
                        .multiply(BigDecimal.valueOf(sale.quantity())),
                BigDecimal::add
        ));
~~~

Ở đây `sales` là tập các `Sale` với `sku()`, `quantity()`, `unitPrice()`. Cách này tổng hợp tiền theo từng mã sản phẩm: mỗi phần tử ánh xạ thành một khoản tiền, sau đó gộp các khoản có cùng khóa.

Nếu cần làm tròn tiền, hãy xác định **điểm làm tròn theo nghiệp vụ**. Không tự đưa `setScale` vào merge function sau mỗi phép cộng nếu mục tiêu là cộng chính xác rồi làm tròn một lần, vì làm tròn trung gian có thể làm kết quả phụ thuộc thứ tự ghép.

## 6. Quy tắc kỹ thuật của mergeFunction

Hàm merge không chỉ giải quyết ngoại lệ; nó xác định **ý nghĩa dữ liệu khi nhiều phần tử cùng khóa**.

- **Phù hợp với nghiệp vụ:** cộng số lượng, lấy giá lớn nhất, lấy bản ghi mới nhất theo timestamp hoặc chấp nhận trùng đều là những chính sách khác nhau.
- **Tránh side effect:** đừng thay đổi một biến đếm, danh sách hoặc Map bên ngoài trong merge function; cách phân chia và ghép pipeline có thể khác giữa chạy tuần tự và song song.
- **Ưu tiên phép kết hợp:** cộng, lấy min/max theo một thứ tự so sánh xác định thường thích hợp hơn các thao tác phụ thuộc vào tổng chạy trước đó. Điều này giúp kết quả ổn định khi Collector ghép các Map trung gian.
- **Nhận biết hợp đồng `Map.merge`:** nếu merge function trả về `null`, ánh xạ của khóa liên quan có thể bị xóa. Không dùng `null` như một giá trị “bỏ qua” nếu mục tiêu là giữ lại khóa.
- **Không đánh đồng thứ tự với tính đúng:** hàm `(a, b) -> a` có thể có ý nghĩa “giữ phần tử đầu” trên nguồn có thứ tự; hàm đó không giải quyết bài toán “bản ghi có thời gian mới nhất” nếu nguồn đến ngẫu nhiên.

Ví dụ việc trả `null` có thể làm mất khóa:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Tag(String key, String value) {}

Map<String, String> result = List.of(
        new Tag("A", "one"),
        new Tag("A", "two")
).stream().collect(Collectors.toMap(
        Tag::key,
        Tag::value,
        (oldValue, newValue) -> null
));

System.out.println(result.containsKey("A")); // false
~~~

Chính sách “gặp trùng thì xóa khóa” rất hiếm khi phù hợp cho lập chỉ mục nghiệp vụ. Nếu muốn loại dữ liệu không hợp lệ, thường tốt hơn khi xác thực trước, loại phần tử bằng `filter` có chủ đích hoặc ném ngoại lệ tường minh.

## 7. Chỉ định loại Map bằng mapFactory

Overload có bốn tham số cho phép chọn loại Map:

~~~java
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

`mapFactory` là một `Supplier<M>` tạo Map mới để tích lũy. Nó hữu ích khi caller cần quy tắc thứ tự, kiểu Map cụ thể hoặc semantics của khóa khác mặc định.

### 7.1. LinkedHashMap giữ thứ tự chèn

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3),
        new Item("BAG", 4)
);

Map<String, Integer> quantities = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                LinkedHashMap::new
        ));

System.out.println(quantities);
// {PEN=5, BOOK=1, BAG=4}
~~~

`LinkedHashMap` mặc định giữ thứ tự chèn khóa. Trong ví dụ tuần tự, khóa `PEN` xuất hiện trước, rồi `BOOK`, rồi `BAG`. Khi `PEN` xuất hiện lại, merge cập nhật giá trị nhưng không chèn khóa mới, nên thứ tự khóa không thay đổi.

**Đừng dựa vào thứ tự in Map mặc định** khi dùng overload không có supplier. Hợp đồng `toMap` không cam kết loại Map hoặc thứ tự duyệt khóa.

### 7.2. TreeMap sắp xếp khóa

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Integer> sortedQuantities = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                TreeMap::new
        ));

System.out.println(sortedQuantities);
// {BAG=4, BOOK=1, PEN=5}
~~~

`TreeMap` có thứ tự theo khóa. Với kiểu `String` trong ví dụ, thứ tự tự nhiên được áp dụng. Nếu khóa không có thứ tự tự nhiên hoặc cần quy tắc sắp xếp đặc biệt, tạo TreeMap với comparator rõ ràng.

Một điểm cần cân nhắc: trong `TreeMap`, **tính duy nhất của khóa phụ thuộc comparator**. Nếu comparator xem hai khóa khác nhau là bằng nhau (kết quả so sánh bằng 0), Map coi chúng là cùng một vị trí khóa, dù `String.equals` của chúng có thể khác.

~~~java
import java.util.TreeMap;

Map<String, Integer> caseInsensitive = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)
        ));
~~~

Kiểu Map và comparator là một phần quan trọng của mô hình dữ liệu. Không nên thay `HashMap` bằng `TreeMap` mà không xét tác động đến nhận diện khóa.

### 7.3. Factory phải tạo Map mới

Tránh dùng một Map có thể thay đổi được và **dùng chung qua nhiều lần gọi** làm kết quả của supplier. Trong xử lý song song, collector có thể yêu cầu nhiều vùng tích lũy độc lập; factory nên tạo một Map trống mới mỗi lần.

~~~java
// Đúng: supplier tạo Map mới khi được gọi.
LinkedHashMap::new
~~~

Đây là ý nghĩa của `Supplier<M>` trong overload, không phải một tham số Map đã có sẵn để trực tiếp ghi dữ liệu vào.

## 8. Phân biệt toMap với groupingBy

Nhiều phần tử cùng khóa có thể có hai ý nghĩa rất khác nhau:

1. **Một giá trị kết quả cho mỗi khóa:** Cần gộp nhiều giá trị thành một, như tổng số lượng hoặc tổng tiền. Dùng `toMap` với merge function.
2. **Một tập giá trị cho mỗi khóa:** Cần giữ mọi phần tử, như danh sách đơn hàng theo khách hàng. Dùng `groupingBy`.

Ví dụ cùng một nguồn:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customerId, String orderId, int quantity) {}

List<Order> orders = List.of(
        new Order("C-01", "O-1", 2),
        new Order("C-02", "O-2", 1),
        new Order("C-01", "O-3", 4)
);

// Một số tổng cho mỗi khách hàng.
Map<String, Integer> totalUnits = orders.stream()
        .collect(Collectors.toMap(
                Order::customerId,
                Order::quantity,
                Integer::sum
        ));

// Danh sách toàn bộ đơn hàng cho mỗi khách hàng.
Map<String, List<Order>> ordersByCustomer = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));

System.out.println(totalUnits.get("C-01"));          // 6
System.out.println(ordersByCustomer.get("C-01").size()); // 2
~~~

Nếu cố dùng `toMap(Order::customerId, order -> order)`, khóa khách `C-01` sẽ trùng và gây lỗi. Nếu chọn `(first, second) -> first` để tránh lỗi, hệ thống **làm mất một đơn hàng**. Khi yêu cầu là giữ mọi đơn, `groupingBy` mới thể hiện đúng ý định.

Ngoài ra, có thể dùng `groupingBy` kết hợp downstream collector để vừa nhóm vừa tính tổng:

~~~java
Map<String, Integer> totals = orders.stream()
        .collect(Collectors.groupingBy(
                Order::customerId,
                Collectors.summingInt(Order::quantity)
        ));
~~~

Đối với collector phức tạp như `groupingBy`, các downstream collector cho phép tính trung bình, đếm, chuyển đổi phần tử, gom danh sách hoặc thực hiện reduction tùy chỉnh. Lựa chọn giữa `toMap` và `groupingBy` nên dựa vào **hình dạng kết quả** và ý nghĩa khóa, không chỉ số dòng mã.

## 9. Chuẩn hóa khóa trước khi thu thập

Một hệ thống có thể xem các mã `"pen"`, `"PEN"` và `" Pen "` là cùng sản phẩm. Khi đó, phải chuẩn hóa khóa theo quy tắc đã công bố:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> input = List.of(
        new Item("pen", 2),
        new Item(" PEN ", 3),
        new Item("book", 1)
);

Map<String, Integer> quantityByCanonicalSku = input.stream()
        .collect(Collectors.toMap(
                item -> item.sku().trim().toUpperCase(Locale.ROOT),
                Item::quantity,
                Integer::sum
        ));

System.out.println(quantityByCanonicalSku.get("PEN")); // 5
~~~

`Locale.ROOT` giúp diễn đạt ý định chuẩn hóa mã theo quy tắc độc lập locale hiển thị người dùng. Nhưng `trim` và `toUpperCase` không phải chính sách hợp lệ cho **mọi** loại định danh; mã phân biệt chữ hoa/thường hoặc mã Unicode phức tạp có thể cần chuẩn hóa riêng.

Sau khi chuẩn hóa, **những khóa ban đầu khác nhau có thể trở thành trùng**. Vì vậy, thiết kế merge function phải phù hợp ngay cả khi dữ liệu nguồn ban đầu không có khóa trùng theo phép so sánh chuỗi thô.

Không nên tự biến `null` thành chuỗi `"null"` hoặc chuỗi rỗng làm khóa, nếu việc đó có thể gộp những bản ghi độc lập. Khi khóa bắt buộc tồn tại, hãy kiểm tra và từ chối dữ liệu thiếu mã.

## 10. Xử lý null ở key mapper và value mapper

Các collector tạo Map **không phải cơ chế chuẩn hóa null**.

Với `Collectors.toMap`, không nên dựa vào khả năng hỗ trợ khóa `null` của Map triển khai mặc định. Đặc tả không cam kết loại Map; các cách thu thập hoặc loại Map khác nhau có thể xử lý khóa `null` khác nhau. Với giá trị `null`, cách triển khai thông thường từ chối và có thể ném `NullPointerException`.

Chính sách an toàn nhất là **xác minh cả khóa và giá trị phù hợp trước khi thu**. Ví dụ:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

record User(String id, String email) {}

List<User> users = List.of(
        new User("U-1", "lan@example.com"),
        new User("U-2", null),
        new User("U-3", "minh@example.com")
);

// Quy định minh họa: chỉ lập chỉ mục user có cả ID và email.
Map<String, String> emailById = users.stream()
        .filter(user -> user.id() != null && user.email() != null)
        .collect(Collectors.toMap(
                User::id,
                User::email
        ));
~~~

`List.of` không cho phép **phần tử List** bằng `null`, nhưng các `record User` trong danh sách vẫn có thể có trường `email` bằng `null`; ví dụ vì vậy hợp lệ.

Trong tình huống cần giữ user chưa có email, việc lọc bỏ user có thể không phù hợp. Khi đó hãy chọn một mô hình rõ ràng, chẳng hạn `Map<String, User>` (giữ toàn bộ đối tượng và trường email rỗng), `Optional<String>` ở lớp nghiệp vụ hoặc một danh sách lỗi validation riêng. **Không biến mất dữ liệu một cách im lặng** chỉ để tránh ngoại lệ.

`Collectors.toUnmodifiableMap` (Java 10+) chặt chẽ hơn: nó từ chối `null` cả ở khóa lẫn giá trị và không cho phép sửa Map kết quả.

## 11. Khi nào dùng toUnmodifiableMap?

Nếu mục tiêu là trả về một **Map không sửa đổi được** và các khóa, giá trị không `null`, có thể sử dụng:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Product> bySku = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::sku,
                product -> product
        ));
~~~

Với mã nguồn trong ví dụ này, `Product` là kiểu record khai báo ở phần trước và `products` chứa khóa duy nhất. `bySku.put(...)` hoặc `remove(...)` sẽ ném `UnsupportedOperationException`.

Collector này có overload với merge function nếu cần xử lý khóa trùng:

~~~java
Map<String, Integer> quantities = lines.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

Tính **không sửa đổi được** chỉ ngăn thao tác sửa cấu trúc Map. Nếu giá trị là một đối tượng mutable, thuộc tính của đối tượng đó vẫn có thể thay đổi qua tham chiếu khác; Map không tự sao chép sâu giá trị.

Một lựa chọn khác là thu Map rồi dùng `Map.copyOf(...)` (Java 10+) nếu đáp ứng hợp đồng `null` và cần bản sao không sửa đổi được. `Map.copyOf` không cam kết thứ tự lặp giống Map nguồn; nếu cần cả thứ tự và cấu trúc không sửa, phải thiết kế hợp đồng riêng và xác định có sử dụng view hay snapshot.

Đặc biệt, không suy rằng `Collectors.toMap` luôn tạo Map mutable chỉ vì một bản JDK cho phép gọi `put` trên kết quả. Nếu khả năng sửa Map là yêu cầu bắt buộc, chọn một `mapFactory` tạo Map mutable cụ thể như `LinkedHashMap::new`.

## 12. Thứ tự kết quả, parallel stream và collector đồng thời

### 12.1. Map không có thứ tự mặc định được bảo đảm

Dù nguồn là `List` có thứ tự, overload mặc định `toMap(k, v)` **không cam kết thứ tự duyệt của Map**. Nếu cần xuất kết quả theo thứ tự xuất hiện khóa, dùng `LinkedHashMap::new` với pipeline tuần tự có encounter order. Nếu cần sắp theo khóa, dùng `TreeMap::new` với comparator phù hợp.

Đối với Map có cùng tập khóa và giá trị, thứ tự của `Map.toString()` không phải cách kiểm chứng tính đúng đắn của overload mặc định. Hãy truy cập bằng `get` hoặc so sánh Map theo hợp đồng ánh xạ.

### 12.2. Parallel stream không làm một Map thông thường tự trở thành concurrent

~~~java
Map<String, Integer> quantities = lines.parallelStream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

Với Collector chuẩn, thư viện có thể tạo **nhiều Map trung gian** rồi ghép. Đây khác với việc nhiều luồng cùng sửa một `HashMap` tùy ý từ bên ngoài. Không nên thay collector bằng:

~~~java
// Sai: ghi vào HashMap dùng chung từ các tác vụ song song.
Map<String, Integer> shared = new java.util.HashMap<>();

lines.parallelStream().forEach(item ->
        shared.put(item.sku(), item.quantity())
);
~~~

Cách này vừa có rủi ro race condition, vừa ghi đè giá trị của khóa trùng và không gộp theo quy tắc số lượng. Hãy dùng Collector tương ứng.

### 12.3. toConcurrentMap có hợp đồng khác

Khi thực sự cần một `ConcurrentMap` và pipeline có thể thu thập không phụ thuộc encounter order, Java cung cấp `Collectors.toConcurrentMap`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Integer> concurrentTotals = lines.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

`toConcurrentMap` có collector hỗ trợ tích lũy đồng thời và có đặc tính unordered; thứ tự duyệt Map kết quả không phải thứ tự danh sách đầu vào. Khi có trùng khóa, merge function phải có ngữ nghĩa ổn định dưới các cách ghép khác nhau.

Không mặc định `toConcurrentMap` nhanh hơn `toMap`: kết quả phụ thuộc vào kích thước nguồn, số khóa phân biệt, độ cạnh tranh trên các khóa, chi phí ánh xạ và đặc điểm môi trường chạy. Đo hiệu năng trước khi tối ưu.

### 12.4. Giới hạn tính kết hợp của merge

Khi pipeline chạy song song, cách kết hợp các giá trị trùng có thể khác chạy tuần tự. Vì vậy, nên ưu tiên merge có tính kết hợp đối với các giá trị cần tổng hợp, ví dụ cộng số lượng, cộng `BigDecimal` chính xác hoặc lấy min/max theo thứ tự nhất quán.

Các thao tác trừ tuần tự, làm tròn sau **mỗi lần** cộng hoặc dựa vào số thứ tự cập nhật của biến dùng chung có thể thay đổi kết quả theo lịch chạy. Nếu bài toán cần “sự kiện mới nhất”, so sánh theo khóa thời gian và quy tắc phá hòa ổn định thường phù hợp hơn giữ “bản ghi được xử lý cuối”.

## 13. Ví dụ thực tế đầy đủ: tổng tiền theo mã sản phẩm

Một ứng dụng cần tổng doanh thu theo từng mã sản phẩm từ các dòng đơn hàng. Mỗi dòng có mã, số lượng và đơn giá; nhiều dòng có thể cùng mã. Yêu cầu: giữ thứ tự xuất hiện **đầu tiên** của từng mã trong dữ liệu nhập và tính tiền bằng `BigDecimal` chính xác trước khi định dạng.

~~~java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SalesBySkuDemo {

    record Sale(String sku, long quantity, BigDecimal unitPrice) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("PEN", 2, new BigDecimal("12.50")),
                new Sale("BOOK", 1, new BigDecimal("30.00")),
                new Sale("PEN", 1, new BigDecimal("10.00"))
        );

        Map<String, BigDecimal> revenueBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::sku,
                        sale -> sale.unitPrice().multiply(
                                BigDecimal.valueOf(sale.quantity())),
                        BigDecimal::add,
                        LinkedHashMap::new
                ));

        System.out.println(revenueBySku);
        // {PEN=35.00, BOOK=30.00}

        System.out.println(revenueBySku.get("PEN"));  // 35.00
        System.out.println(revenueBySku.get("BOOK")); // 30.00
    }
}
~~~

Tính toán:

~~~text
PEN:  2 x 12.50 + 1 x 10.00 = 35.00
BOOK: 1 x 30.00               = 30.00
~~~

Pipeline thực hiện:

1. `Sale::sku` tạo khóa cho mỗi dòng.
2. Value mapper tính thành tiền của dòng và tạo giá trị `BigDecimal`.
3. `BigDecimal::add` gộp các khoản có cùng khóa **không làm tròn trung gian**.
4. `LinkedHashMap::new` yêu cầu Map giữ thứ tự chèn, nên khi xử lý tuần tự các mã xuất hiện lần đầu theo thứ tự `PEN`, `BOOK`.

Nếu nghiệp vụ quy định làm tròn thành tiền ở cấp hóa đơn, cấp thuế hoặc từng dòng, phải áp dụng đúng quy tắc ở **ranh giới đã định**. Đoạn ví dụ cố tình không tự áp dụng rounding policy vì giá trị đầu vào đã chính xác và nhiệm vụ chỉ là cộng theo mã sản phẩm.

## 14. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException: Duplicate key ...` | Hai phần tử sinh khóa trùng trong `toMap(k, v)` | Nếu trùng là lỗi, xác thực nguồn; nếu hợp lệ, thêm merge function đúng nghiệp vụ. |
| Mất dòng dữ liệu sau khi dùng `(old, next) -> old` | Chọn giữ một giá trị nhưng thực tế cần tất cả | Dùng `groupingBy` khi mỗi khóa phải có danh sách nhiều giá trị. |
| `NullPointerException` khi thu Map | Key/value mapper tạo giá trị thiếu hoặc null, không đáp ứng collector/Map kết quả | Kiểm tra và áp dụng chính sách null tường minh trước khi thu. |
| Thứ tự duyệt Map không giống List đầu vào | `toMap` không mặc định cam kết thứ tự Map | Chọn `LinkedHashMap::new` hoặc `TreeMap::new` phù hợp yêu cầu. |
| Kết quả thay đổi trên nguồn unordered khi “giữ cuối” | Quy tắc dựa vào thứ tự không được bảo đảm | Chọn giá trị theo timestamp và tie-breaker ổn định. |
| Bản ghi trùng không được gộp sau khi chuẩn hóa mã | Khóa chưa được chuẩn hóa nhất quán | Dùng canonical key và merge function có ý nghĩa. |
| Tổng khi chạy song song không ổn định | Merge không kết hợp hoặc phụ thuộc side effect | Dùng phép gộp kết hợp, tránh trạng thái dùng chung; không làm tròn trung gian tùy tiện. |
| Ép kiểu Map kết quả gây lỗi | Tin rằng overload mặc định luôn trả một lớp cụ thể | Dùng giao diện `Map` hoặc cung cấp `mapFactory`. |
| Muốn Map không sửa được nhưng vẫn có `put` | Dùng `toUnmodifiableMap` / `Map.copyOf` | Xác định rõ mutable hay unmodifiable trong hợp đồng API. |
| Tăng bộ nhớ lớn | Map giữ tất cả các cặp khóa–giá trị phân biệt và đối tượng liên quan | Giảm số trường, tổng hợp trực tiếp, xử lý theo lô hoặc dùng cơ sở dữ liệu khi phù hợp. |

## 15. Hiệu năng, vòng đời và giới hạn của pipeline

`collect(Collectors.toMap(...))` là **terminal operation**. Các bước `filter`, `map`, `flatMap` phía trước thường chỉ được thực thi khi terminal operation bắt đầu xử lý. Sau khi thu Map, không được sử dụng lại **cùng đối tượng Stream** cho terminal operation khác.

Một Map thường giữ một mục cho mỗi khóa phân biệt; nếu Stream chứa hàng triệu khóa, bộ nhớ vẫn tăng theo số mục. `toMap` không phải phép tổng hợp dùng bộ nhớ hằng số đối với số lượng khóa tăng không giới hạn.

Một nguồn vô hạn với liên tục xuất hiện khóa mới sẽ không thể thu thành Map hữu hạn bằng `collect(toMap)` nếu không có điểm dừng. Dùng `limit(n)` hoặc nguồn hữu hạn phù hợp khi cần kết quả được vật hóa hoàn toàn. Với dữ liệu đọc từ tệp hoặc nguồn I/O, phải quản lý vòng đời và đóng tài nguyên riêng; `collect` không tự thay thế `try-with-resources`.

Các lưu ý tối ưu:

- Nếu cần tra cứu bằng khóa nhiều lần, một Map có thể tiết kiệm công sức so với liên tục lọc lại danh sách; hiệu quả còn phụ thuộc loại Map và số mục.
- Nếu chỉ cần xác định một mã có tồn tại hay không, `anyMatch` có thể dừng sớm và tránh tạo toàn bộ Map.
- Nếu cần nhiều giá trị trên một khóa, `groupingBy` có thể tránh phải tự viết logic ghép danh sách trong `toMap`.
- Không nhất thiết chuyển Stream sang parallel chỉ vì có nhiều phần tử; với quá ít dữ liệu hoặc nhiều khóa trùng gây cạnh tranh, overhead có thể lớn.
- Tránh khóa mutable: sửa các trường tham gia `equals`/`hashCode` của khóa sau khi chèn vào hash-based Map có thể khiến mục trở nên khó tra cứu.
- Khi chọn `TreeMap`, xem xét chi phí sắp xếp và comparator; lựa chọn cấu trúc dựa trên nhu cầu thay vì chỉ nhìn vào cú pháp ngắn.

Những kỹ thuật này cũng liên quan đến collector tùy chỉnh, Spliterator và xử lý song song của Stream API: hợp đồng khóa và kết hợp dữ liệu phải giữ nguyên dù nguồn được chia hoặc duyệt theo cách khác.

## 16. Bài tập tự kiểm tra

### Bài 1 — Dự đoán lỗi khóa trùng

~~~java
record Product(String sku, int price) {}

List<Product> products = List.of(
        new Product("A", 10),
        new Product("A", 10)
);

Map<String, Integer> prices = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::price
        ));
~~~

**Đáp án:** Ném `IllegalStateException` vì khóa `"A"` xuất hiện hai lần, dù giá trị tương ứng đều bằng 10. Nếu nguồn phải duy nhất, cần sửa dữ liệu; nếu trùng hợp lệ, định nghĩa merge function.

### Bài 2 — Cộng số lượng theo khóa

~~~java
record Line(String code, int count) {}

List<Line> lines = List.of(
        new Line("A", 2),
        new Line("B", 4),
        new Line("A", 3)
);
~~~

**Yêu cầu:** Tạo `Map<String, Integer>` cộng số lượng cùng mã.

**Đáp án:**

~~~java
Map<String, Integer> total = lines.stream()
        .collect(Collectors.toMap(
                Line::code,
                Line::count,
                Integer::sum
        ));

System.out.println(total.get("A")); // 5
System.out.println(total.get("B")); // 4
~~~

### Bài 3 — Chọn toMap hay groupingBy

**Yêu cầu:** Có `Stream<Order>`, cần giữ **tất cả đơn hàng** theo `customerId`.

**Đáp án:** Dùng `Collectors.groupingBy(Order::customerId)` để nhận `Map<String, List<Order>>`. Nếu dùng `toMap(Order::customerId, Function.identity())`, khách có nhiều đơn sẽ gây lỗi; nếu chọn giữ một đơn, kết quả sẽ mất các đơn còn lại.

### Bài 4 — Thứ tự khóa

**Yêu cầu:** Từ `List` có thứ tự xuất hiện khóa `B`, `A`, `C`, trả một Map giữ thứ tự chèn của khóa.

**Đáp án:** Dùng pipeline tuần tự và `Collectors.toMap(keyMapper, valueMapper, mergeFunction, LinkedHashMap::new)`. Không phụ thuộc vào thứ tự khóa của overload mặc định.

### Bài 5 — Chọn bản ghi mới nhất

Hai sự kiện có cùng mã, nhưng được đọc theo thứ tự ngược thời gian. Có nên dùng `(oldValue, newValue) -> newValue` để lấy bản ghi mới nhất không?

**Đáp án:** Không nếu thứ tự xử lý không bảo đảm trùng thứ tự thời gian. Cần so sánh timestamp hoặc sequence đáng tin cậy và có tie-breaker xác định, rồi chọn sự kiện lớn nhất theo tiêu chí đó.

### Bài 6 — Map không sửa đổi được

~~~java
Map<String, String> result = Stream.of("a", "b")
        .collect(Collectors.toUnmodifiableMap(
                value -> value,
                value -> value.toUpperCase(java.util.Locale.ROOT)
        ));
~~~

**Hỏi:** Có gọi `result.put("c", "C")` được không? Nếu Stream có hai phần tử `"a"` thì sao?

**Đáp án:** `put` ném `UnsupportedOperationException`. Nếu hai phần tử đều sinh khóa `"a"` và dùng overload không có merge function, collector sẽ ném `IllegalStateException` vì khóa trùng.

## 17. Ghi nhớ

- `Collectors.toMap(keyMapper, valueMapper)` biến Stream thành `Map<K, V>` khi khóa duy nhất.
- Có thể trùng khóa thì dùng `toMap(keyMapper, valueMapper, mergeFunction)`, nhưng **chỉ sau khi đã chọn quy tắc gộp đúng nghiệp vụ**.
- Muốn loại Map cụ thể, sử dụng overload thêm `mapFactory`: `LinkedHashMap::new` cho thứ tự chèn hoặc `TreeMap::new` cho thứ tự khóa.
- Dùng `groupingBy` khi cần giữ **nhiều giá trị** cho một khóa; `toMap` thích hợp khi mỗi khóa cuối cùng tương ứng **một giá trị đã gộp**.
- Xử lý rõ khóa trùng, `null`, chuẩn hóa định danh, thứ tự duyệt, tính kết hợp của merge và giới hạn bộ nhớ trước khi đưa pipeline vào ứng dụng.
- `Collectors.toUnmodifiableMap` tạo Map không sửa đổi được và từ chối `null`; `toConcurrentMap` dành cho những tình huống cần Collector có tính chất đồng thời.
- `collect` kết thúc Stream; nguồn vô hạn cần điều kiện dừng, nguồn I/O cần được đóng đúng vòng đời.

**Ý chính:** `Collectors.toMap` là công cụ lập chỉ mục và tổng hợp dữ liệu theo khóa trong Java Stream API. Để kết quả đúng, cần trả lời ba câu hỏi trước: **khóa nào xác định một mục**, **gặp khóa trùng thì gộp ra sao**, và **kết quả cần loại Map/hợp đồng thứ tự nào**. Khi các quy tắc đó rõ ràng, pipeline sẽ dễ đọc, dễ kiểm thử và có thể mở rộng sang nhóm dữ liệu hoặc xử lý song song một cách có kiểm soát.
