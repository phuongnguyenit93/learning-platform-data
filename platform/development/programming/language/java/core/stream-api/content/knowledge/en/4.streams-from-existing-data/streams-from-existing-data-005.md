# Tạo Stream từ khóa, giá trị và entry của Map

## 1. Vì sao không gọi trực tiếp `map.stream()`?

Trong **Java Stream API**, một pipeline gồm nguồn dữ liệu, các thao tác trung gian như `filter`, `map`, `sorted` và một thao tác kết thúc như `toList`, `count`, `reduce` hoặc `collect`. Phần lớn thao tác trung gian chạy **lười** (*lazy*): pipeline chỉ thực sự duyệt dữ liệu khi thao tác kết thúc được gọi.

Một `Map<K, V>` lưu quan hệ **khóa → giá trị**, không phải một chuỗi phần tử duy nhất. Vì vậy, giao diện `Map` **không có** phương thức `stream()` trực tiếp. Ta phải quyết định muốn duyệt phần nào của Map:

```text
                         Map<K, V>
                        /    |     \
              keySet()    values()   entrySet()
                  |          |          |
              Set<K>    Collection<V> Set<Map.Entry<K,V>>
                  |          |          |
               stream()   stream()    stream()
                  |          |          |
              Stream<K>  Stream<V> Stream<Map.Entry<K,V>>
```

Ba nguồn này đều là **view được liên kết với Map gốc**, không tự tạo bản sao dữ liệu. Chọn nguồn nào sẽ quyết định những thông tin mà mỗi phần tử trong pipeline mang theo.

Sau bài này, bạn sẽ biết cách:

- Tạo Stream từ `keySet()`, `values()` và `entrySet()`; chọn đúng cách theo yêu cầu nghiệp vụ.
- Lọc, biến đổi, sắp xếp, tính tổng và gom nhóm dữ liệu lấy từ Map.
- Chuyển kết quả Stream về `List` hoặc Map mới và xử lý khóa trùng khi `Collectors.toMap`.
- Nhận diện những vấn đề về thứ tự duyệt, view có thể thay đổi, nguồn concurrent và giới hạn hiệu năng.

Các ví dụ dùng Java 17 trở lên để có `record`, `Map.of` và `Stream.toList()`. Những thao tác nguồn `keySet()`/`values()`/`entrySet()` cùng `stream()` có từ Java 8.

## 2. Ví dụ khởi đầu: một Map với ba góc nhìn

Xét kho hàng, trong đó khóa là mã sản phẩm và giá trị là số lượng tồn:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("SACH", 3);
stock.put("BUT", 8);
stock.put("VO", 2);
```

Dùng `LinkedHashMap` để giữ thứ tự chèn trong ví dụ, nhờ vậy kết quả minh họa có thứ tự dễ kiểm tra.

| Nguồn | Kiểu phần tử Stream | Phần tử lấy được | Phù hợp khi |
| --- | --- | --- | --- |
| `stock.keySet().stream()` | `String` | `"SACH"`, `"BUT"`, `"VO"` | Chỉ cần mã sản phẩm/khóa. |
| `stock.values().stream()` | `Integer` | `3`, `8`, `2` | Chỉ cần số lượng/giá trị. |
| `stock.entrySet().stream()` | `Map.Entry<String, Integer>` | `("SACH", 3)`, … | Cần đồng thời khóa **và** giá trị. |

Trong một `Map`, mỗi khóa là duy nhất. Giá trị thì **có thể trùng nhau**, nên `values()` trả về `Collection<V>` thay vì `Set<V>`. Nếu có hai sản phẩm cùng tồn 3 chiếc, `values().stream()` vẫn chứa hai phần tử có giá trị 3.

## 3. Stream từ `keySet()`: xử lý danh sách khóa

`keySet()` cung cấp tập hợp tất cả khóa. Mỗi bước trong pipeline chỉ nhận khóa, nên đây là lựa chọn gọn khi điều kiện lọc không phụ thuộc giá trị.

```java
List<String> codes = stock.keySet().stream()
        .filter(code -> code.startsWith("S"))
        .map(String::toLowerCase)
        .toList();

System.out.println(codes); // [sach]
```

Một vài trường hợp khác:

```java
long numberOfShortCodes = stock.keySet().stream()
        .filter(code -> code.length() <= 3)
        .count(); // 2: BUT, VO

List<String> sortedCodes = stock.keySet().stream()
        .sorted()
        .toList(); // [BUT, SACH, VO]
```

**Có cần truy cập giá trị không?** Có thể gọi `stock.get(code)` từ Stream khóa, nhưng khi điều kiện xử lý cần cả khóa lẫn giá trị thì `entrySet().stream()` thường biểu đạt ý định rõ hơn và tránh tra cứu Map lặp lại:

```java
// Chạy được, nhưng phải tra cứu lại giá trị theo từng khóa.
List<String> lowStockCodes = stock.keySet().stream()
        .filter(code -> stock.get(code) < 5)
        .toList();

// Phù hợp hơn khi cần cả khóa và giá trị.
List<String> lowStockCodesFromEntries = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .map(Map.Entry::getKey)
        .toList();

System.out.println(lowStockCodesFromEntries); // [SACH, VO]
```

Không nên giả định mọi Map đều có thao tác `get` với chi phí như `HashMap`. Hơn nữa, nếu có thread khác đang cập nhật Map, gọi `get` độc lập không tạo nên một bản đọc nguyên tử gắn với khóa đang được duyệt.

## 4. Stream từ `values()`: phân tích chỉ giá trị

`values()` trả về các giá trị trong Map. Nếu không cần biết giá trị thuộc khóa nào, nguồn này trực tiếp và dễ đọc hơn `entrySet()`.

```java
int totalStock = stock.values().stream()
        .mapToInt(Integer::intValue)
        .sum();

double averageStock = stock.values().stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0);

long nearlyEmptyProducts = stock.values().stream()
        .filter(quantity -> quantity < 5)
        .count();

System.out.println(totalStock);           // 13
System.out.println(averageStock);         // 4.333333333333333
System.out.println(nearlyEmptyProducts);  // 2
```

`mapToInt` tạo một `IntStream` để dùng `sum`, `average`, `min`, `max` hoặc `summaryStatistics` mà không phải tự viết vòng cộng dồn. Với Map rỗng, `average()` trả về `OptionalDouble.empty()`; trong ví dụ trên, `orElse(0.0)` xác định kết quả mặc định.

Có thể thống kê tần suất giá trị, bao gồm các giá trị giống nhau:

```java
Map<Integer, Long> frequency = stock.values().stream()
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

// Với stock hiện tại: {2=1, 3=1, 8=1}, thứ tự hiển thị không được bảo đảm.
```

Đối với Map cho phép giá trị `null`, mã sử dụng `Integer::intValue` sẽ gây `NullPointerException` khi gặp `null`. `Collectors.groupingBy` cũng không chấp nhận khóa nhóm `null` trong cách dùng trên. Nếu nghiệp vụ cần bỏ qua những giá trị trống, hãy lọc rõ ràng:

```java
int safeTotal = stock.values().stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
```

Các đoạn mã nhỏ ở trên sử dụng `List`, `Collectors`, `Function` và `Objects` từ các gói `java.util` và `java.util.stream`; ví dụ hoàn chỉnh có `import` ở mục 10.

## 5. Stream từ `entrySet()`: cần cả khóa lẫn giá trị

`entrySet()` trả về tập `Map.Entry<K, V>`. Mỗi entry cho phép lấy `getKey()` và `getValue()` từ cùng một cặp.

```java
List<String> warnings = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .map(entry -> entry.getKey() + " chỉ còn " + entry.getValue())
        .toList();

System.out.println(warnings);
// [SACH chỉ còn 3, VO chỉ còn 2]
```

Có thể kết hợp `filter`, `map` với việc chọn một đối tượng có giá trị lớn nhất:

```java
Optional<Map.Entry<String, Integer>> mostStocked = stock.entrySet().stream()
        .max(Map.Entry.comparingByValue());

mostStocked.ifPresent(entry ->
        System.out.println(entry.getKey() + ": " + entry.getValue())
); // BUT: 8
```

`max` trả về `Optional` vì Map có thể rỗng. Với các giá trị bằng nhau, ví dụ trên không xác định quy tắc ưu tiên khóa; nếu cần kết quả ổn định, thêm quy tắc phụ.

### Sắp xếp theo giá trị

Thứ tự mặc định của `TreeMap` dựa theo **khóa**. Muốn sắp xếp theo **giá trị**, sử dụng Stream trên `entrySet`:

```java
List<Map.Entry<String, Integer>> smallestFirst = stock.entrySet().stream()
        .sorted(Map.Entry.comparingByValue())
        .toList();

smallestFirst.forEach(entry ->
        System.out.println(entry.getKey() + " -> " + entry.getValue())
);
// VO -> 2
// SACH -> 3
// BUT -> 8
```

Để có thứ tự nhất quán kể cả khi tồn kho trùng nhau, thêm một so sánh phụ theo khóa:

```java
List<Map.Entry<String, Integer>> sorted = stock.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue()
                .thenComparing(Map.Entry.comparingByKey()))
        .toList();
```

Lưu ý `sorted` tạo **thứ tự trên Stream kết quả**, không sắp xếp lại Map gốc. Phép so sánh tự nhiên cần giá trị có thể so sánh và không phải `null`, hoặc cần cung cấp comparator có quy tắc xử lý `null`.

## 6. Thu thập Stream entry thành một Map mới

Một pipeline thường kết thúc bằng `collect` để tạo Map khác: lọc phần tử, thay đổi giá trị, đổi kiểu khóa, hoặc giữ thứ tự đã sắp xếp.

Ví dụ tạo một Map chứa các sản phẩm tồn ít:

```java
Map<String, Integer> lowStock = stock.entrySet().stream()
        .filter(entry -> entry.getValue() < 5)
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
        ));

// Các cặp khóa/giá trị là SACH=3 và VO=2.
// Map kết quả từ toMap dạng đơn giản không cam kết thứ tự hay kiểu Map.
```

Nếu cần giữ **thứ tự sau `sorted`** trong Map kết quả, yêu cầu `LinkedHashMap` qua overload bốn tham số của `toMap`:

```java
Map<String, Integer> sortedByQuantity = stock.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue()
                .thenComparing(Map.Entry.comparingByKey()))
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue,
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(sortedByQuantity);
// {VO=2, SACH=3, BUT=8}
```

Overload này nhận lần lượt `keyMapper`, `valueMapper`, hàm xử lý **khóa trùng** và factory tạo Map. Vì các entry của Map nguồn có khóa duy nhất và ví dụ không đổi khóa, hàm merge sẽ không được gọi, nhưng vẫn bắt buộc có khi muốn chỉ rõ loại Map.

### Khóa trùng sau khi biến đổi là một lỗi dễ bỏ sót

Map ban đầu có khóa khác nhau nhưng thao tác `map` có thể biến chúng thành cùng khóa:

```java
Map<String, Integer> original = Map.of(
        "VIP", 10,
        "vip", 20
);

// SAI: hai khóa khác nhau cùng thành "vip", toMap ném IllegalStateException.
Map<String, Integer> broken = original.entrySet().stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey().toLowerCase(Locale.ROOT),
                Map.Entry::getValue
        ));
```

Nếu muốn gộp số liệu thay vì từ chối khóa trùng, truyền quy tắc merge:

```java
Map<String, Integer> merged = original.entrySet().stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey().toLowerCase(Locale.ROOT),
                Map.Entry::getValue,
                Integer::sum
        ));

System.out.println(merged); // {vip=30}
```

Không nên dựa vào `(oldValue, newValue) -> oldValue` hoặc phép ghi đè `newValue` khi thứ tự nguồn không được bảo đảm: phần tử nào đến trước có thể không xác định được. Với logic nghiệp vụ thực tế, hãy định nghĩa phép gộp phù hợp (cộng số, chọn giá trị lớn nhất, hoặc báo trùng một cách tường minh).

`Collectors.toMap` không chấp nhận giá trị kết quả là `null` trong các triển khai Java thông dụng. Nếu Map nguồn có giá trị `null`, hãy lọc, thay thế hoặc chọn phương thức thu thập hỗ trợ dữ liệu đó theo yêu cầu của bài toán.

## 7. Gom nhóm Map entry theo thuộc tính của giá trị

Khi mỗi giá trị là một đối tượng, `entrySet()` cho phép gom theo thuộc tính của đối tượng mà vẫn giữ được mã khóa.

Giả sử Map chứa `Product`:

```java
record Product(String category, int stock) {}

Map<String, Product> products = new LinkedHashMap<>();
products.put("P-01", new Product("Văn phòng phẩm", 3));
products.put("P-02", new Product("Sách", 8));
products.put("P-03", new Product("Văn phòng phẩm", 2));
```

Thống kê tổng tồn theo nhóm:

```java
Map<String, Integer> stockByCategory = products.values().stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::stock)
        ));

System.out.println(stockByCategory);
// {Văn phòng phẩm=5, Sách=8}, không cam kết thứ tự nhóm.
```

Ở đây **chỉ cần giá trị**, nên `values()` là đủ. Nhưng nếu muốn lấy **mã sản phẩm theo nhóm**, phải dùng `entrySet()`:

```java
Map<String, List<String>> codesByCategory = products.entrySet().stream()
        .collect(Collectors.groupingBy(
                entry -> entry.getValue().category(),
                Collectors.mapping(
                        Map.Entry::getKey,
                        Collectors.toList()
                )
        ));

// Văn phòng phẩm -> [P-01, P-03]
// Sách -> [P-02]
```

Đây là một cách lựa chọn nguồn Stream theo thông tin cần giữ lại: khi đã dùng `values().stream()`, pipeline không còn trực tiếp biết mã khóa của từng giá trị.

## 8. View của Map liên kết với nguồn: tránh sửa Map trong lúc Stream chạy

`keySet()`, `values()` và `entrySet()` của các Map thông thường là **backed views**: khi Map thay đổi, nội dung view cũng thay đổi. Xóa thông qua một view có thể làm thay đổi Map gốc. Các collection view đó không được coi là bản snapshot.

Ví dụ sai:

```java
Map<String, Integer> items = new HashMap<>();
items.put("A", 1);
items.put("B", 0);

items.entrySet().stream()
        .filter(entry -> entry.getValue() == 0)
        .forEach(entry -> items.remove(entry.getKey())); // SAI
```

Pipeline đang duyệt `items.entrySet()` nhưng lại xóa phần tử trong `items`. Với `HashMap`, hành vi có thể dẫn đến `ConcurrentModificationException`; không được xem exception là cơ chế phát hiện lỗi duy nhất.

Ngay cả việc gọi `entry.setValue(...)` cũng có thể thay đổi **giá trị trong Map nguồn**, dù không thay đổi số lượng phần tử:

```java
items.entrySet().stream()
        .forEach(entry -> entry.setValue(entry.getValue() + 1)); // Tránh: sửa nguồn khi duyệt
```

Không phải entry nào cũng cho phép `setValue`: entry từ Map bất biến có thể ném `UnsupportedOperationException`. Còn với entry sửa được, việc không phát sinh exception cũng không làm cách dùng trên trở thành mô hình Stream an toàn.

Để lọc và xóa dữ liệu, tách hai giai đoạn:

```java
List<String> outOfStock = items.entrySet().stream()
        .filter(entry -> entry.getValue() == 0)
        .map(Map.Entry::getKey)
        .toList();

// Terminal operation đã kết thúc, giờ mới sửa Map.
outOfStock.forEach(items::remove);
```

Nếu **chỉ** muốn xóa theo điều kiện, không cần Stream:

```java
items.entrySet().removeIf(entry -> entry.getValue() == 0);
```

`removeIf` thực hiện việc cập nhật Map có chủ đích. Cách này phù hợp với Map cho phép sửa và khi không có luồng khác cùng truy cập gây vi phạm an toàn. Map bất biến như `Map.of(...)` không cho phép thao tác xóa.

### Tính lazy và vòng đời

Giống các nguồn Stream khác, lời gọi `items.entrySet().stream().filter(...)` mới xây dựng pipeline; thao tác kết thúc mới kích hoạt duyệt. Các Stream được tạo từ những Map có bộ duyệt **late-binding** có thể phản ánh thay đổi diễn ra trước khi bắt đầu terminal operation. Tuy nhiên, không phải mọi Map có cùng ràng buộc thời điểm đọc; đừng dựa vào tính chất này nếu cần snapshot ổn định.

Muốn xử lý trên một tập cặp khóa/giá trị đã chốt, tạo bản sao **trước** khi chạy Stream, khi nguồn đang ổn định:

```java
Map<String, Integer> snapshot = new HashMap<>(items);
List<String> names = snapshot.entrySet().stream()
        .filter(entry -> entry.getValue() > 0)
        .map(Map.Entry::getKey)
        .toList();
```

Đây là bản sao **nông**: các đối tượng giá trị có thể vẫn được chia sẻ. Đồng thời, việc tạo bản sao từ Map đang bị thay đổi không cung cấp snapshot nguyên tử; nếu có truy cập concurrent, cần đồng bộ hoặc dùng cơ chế snapshot phù hợp trước khi sao chép.

## 9. Thứ tự duyệt, Map concurrent và xử lý song song

Không nên nhìn thứ tự hiện tại của một Map rồi giả định Stream luôn dùng thứ tự đó.

| Kiểu Map | Thứ tự duyệt | Lưu ý khi tạo Stream |
| --- | --- | --- |
| `HashMap` | Không cam kết thứ tự | Muốn kết quả nhất quán thì `sorted` theo tiêu chí rõ ràng. |
| `LinkedHashMap` | Thường theo thứ tự chèn | Có chế độ *access-order*; gọi `get` có thể đổi thứ tự duyệt. |
| `TreeMap` | Theo bộ so sánh khóa | Muốn thứ tự theo giá trị thì vẫn phải `sorted` entry. |
| `Map.of(...)` | Không cam kết thứ tự | Map bất biến, không cho thêm/xóa và không cho khóa/giá trị `null`. |
| `ConcurrentHashMap` | Không cam kết thứ tự cố định | Bộ duyệt *weakly consistent* hỗ trợ cập nhật đồng thời, nhưng không tạo snapshot. |

### Với `parallelStream()`

Có thể tạo pipeline song song từ một view:

```java
long available = stock.entrySet().parallelStream()
        .filter(entry -> entry.getValue() > 0)
        .count();
```

Nhưng `parallelStream()` **không biến `HashMap` hoặc `LinkedHashMap` thành collection an toàn để sửa đồng thời**. Đối với Map mutable thông thường, giữ nguồn ổn định trong lúc duyệt; các lambda nên *stateless*, không sửa nguồn và tránh dùng bộ tích lũy bên ngoài không đồng bộ.

`ConcurrentHashMap` có bộ duyệt hỗ trợ sửa đổi đồng thời, song kết quả khi có thread đang cập nhật phụ thuộc thời điểm quan sát:

```java
ConcurrentHashMap<String, Integer> live = new ConcurrentHashMap<>();
live.put("A", 1);
live.put("B", 2);

List<String> seen = live.entrySet().parallelStream()
        .filter(entry -> entry.getValue() > 0)
        .map(Map.Entry::getKey)
        .toList();
```

Nếu một thread khác thay đổi `live`, danh sách `seen` không nhất thiết phản ánh toàn bộ Map tại một thời điểm duy nhất. Nguồn concurrent giúp việc duyệt chấp nhận cập nhật đồng thời theo hợp đồng của nó; yêu cầu nhất quán nghiệp vụ cần được thiết kế riêng.

Về hiệu năng, `entrySet()` thường hợp lý khi cần cả khóa và giá trị vì không phải gọi `get` cho từng khóa. Với Map nhỏ hoặc phép xử lý rẻ, chi phí phân luồng, chia tách và kết hợp của `parallelStream()` có thể lớn hơn lợi ích; hãy đo trên dữ liệu và yêu cầu thực tế. Các thao tác `sorted`, `distinct` hoặc gom nhóm có thể tạo thêm bộ nhớ trung gian.

## 10. Ví dụ hoàn chỉnh: báo cáo và xử lý hàng tồn

Chương trình sau minh họa cả ba nguồn Stream trên cùng một `Map`, rồi cập nhật nguồn **sau** khi toàn bộ phép tính Stream kết thúc.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class MapStreamsDemo {
    record Product(String category, int quantity, boolean active) {}

    public static void main(String[] args) {
        Map<String, Product> catalog = new LinkedHashMap<>();
        catalog.put("P-01", new Product("Sách", 5, true));
        catalog.put("P-02", new Product("Bút", 0, false));
        catalog.put("P-03", new Product("Sách", 7, true));
        catalog.put("P-04", new Product("Vở", 2, true));

        // keySet: chỉ dùng mã sản phẩm.
        List<String> codes = catalog.keySet().stream()
                .filter(code -> code.startsWith("P-0"))
                .toList();

        // values: cộng số lượng theo thuộc tính của Product.
        int totalQuantity = catalog.values().stream()
                .filter(Product::active)
                .mapToInt(Product::quantity)
                .sum();

        // entrySet: cần mã sản phẩm gắn với số lượng của chính nó.
        List<String> depletedCodes = catalog.entrySet().stream()
                .filter(entry -> entry.getValue().quantity() == 0)
                .map(Map.Entry::getKey)
                .toList();

        Map<String, Integer> quantityByCategory = catalog.values().stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        LinkedHashMap::new,
                        Collectors.summingInt(Product::quantity)
                ));

        System.out.println(codes);              // [P-01, P-02, P-03, P-04]
        System.out.println(totalQuantity);      // 14
        System.out.println(depletedCodes);      // [P-02]
        System.out.println(quantityByCategory); // {Sách=12, Bút=0, Vở=2}

        // Các terminal operation đã xong: bây giờ mới thay đổi Map nguồn.
        depletedCodes.forEach(catalog::remove);
        System.out.println(catalog.keySet());   // [P-01, P-03, P-04]
    }
}
```

Ở đây:

1. `keySet()` thích hợp vì chỉ lọc theo mã sản phẩm.
2. `values()` thích hợp vì tổng tồn và phân nhóm chỉ phụ thuộc thuộc tính `Product`.
3. `entrySet()` thích hợp để tìm **mã** của các sản phẩm có lượng tồn bằng 0.
4. `Collectors.groupingBy` tích lũy vào Map kết quả riêng. `LinkedHashMap::new` giữ thứ tự gặp nhóm của pipeline tuần tự này.
5. Việc xóa mã hết hàng diễn ra sau terminal operation, nên không can thiệp vào nguồn đang được xử lý.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Gọi `map.stream()` không biên dịch | `Map` không triển khai `Collection` và không có `stream()` | Chọn `keySet()`, `values()` hoặc `entrySet()`. |
| Đã dùng `values()` nhưng lại cần khóa | Stream chỉ còn phần tử kiểu `V` | Dùng `entrySet()` ngay từ đầu. |
| `Collectors.toMap` ném `IllegalStateException` | Phép biến đổi tạo khóa trùng | Cung cấp hàm merge hoặc định nghĩa lại khóa. |
| Map thu được không giữ thứ tự sau `sorted` | `toMap` mặc định không cam kết loại Map | Chọn `LinkedHashMap::new` ở overload bốn tham số. |
| `ConcurrentModificationException` khi đang `forEach` | Pipeline sửa Map nguồn trong lúc duyệt | Thu thập kết quả trước; cập nhật Map sau, hoặc dùng API sửa trực tiếp. |
| Kết quả thay đổi giữa các lần chạy | Dựa vào thứ tự `HashMap`/`Map.of` hoặc nguồn đang bị cập nhật | Sắp xếp tường minh; có snapshot nhất quán khi cần. |
| `NullPointerException` khi tính tổng/sắp xếp | Giá trị `null` không được xử lý | Lọc `null` hoặc cung cấp quy tắc rõ ràng. |

## 12. Bài tập thực hành

Cho danh sách điểm theo mã sinh viên:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("SV01", 8);
scores.put("SV02", 5);
scores.put("SV03", 9);
scores.put("SV04", 5);
```

**Yêu cầu:**

1. Lấy danh sách mã sinh viên bắt đầu bằng `SV0`.
2. Tính điểm trung bình bằng Stream trên **giá trị**.
3. Lấy danh sách mã đạt điểm từ 8 trở lên, sắp xếp theo điểm giảm dần, rồi theo mã tăng dần nếu hòa điểm.
4. Tạo Map `passOrFail` gồm mã sinh viên và chuỗi `"PASS"` nếu điểm từ 5 trở lên, `"FAIL"` nếu thấp hơn. Không sửa `scores`.

**Gợi ý lời giải:**

```java
List<String> studentCodes = scores.keySet().stream()
        .filter(code -> code.startsWith("SV0"))
        .toList();

double average = scores.values().stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0); // 6.75

List<String> highScorers = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 8)
        .sorted(Map.Entry.<String, Integer>comparingByValue(
                Comparator.reverseOrder()
        ).thenComparing(Map.Entry.comparingByKey()))
        .map(Map.Entry::getKey)
        .toList(); // [SV03, SV01]

Map<String, String> passOrFail = scores.entrySet().stream()
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> entry.getValue() >= 5 ? "PASS" : "FAIL",
                (first, second) -> first,
                LinkedHashMap::new
        ));

// {SV01=PASS, SV02=PASS, SV03=PASS, SV04=PASS}
```

Đoạn lời giải dùng thêm `Comparator` từ `java.util`. Khi làm bài tương tự, hãy tự trả lời hai câu hỏi trước khi viết code: **mỗi phần tử Stream cần chứa thông tin gì?** và **kết quả phải là List, số liệu tổng hợp hay Map mới?**

## Ghi nhớ

- Dùng `keySet().stream()` khi chỉ cần khóa; dùng `values().stream()` khi chỉ cần giá trị; dùng `entrySet().stream()` khi cần **cả khóa và giá trị**.
- Ba collection view của Map thông thường liên kết với Map gốc. Không sửa nguồn trong lúc một Stream đang duyệt nguồn đó.
- `sorted` chỉ sắp thứ tự các phần tử Stream; muốn Map kết quả giữ thứ tự phải chọn implementation thích hợp, chẳng hạn `LinkedHashMap`.
- `Collectors.toMap` cần chính sách rõ ràng khi các khóa **sau biến đổi** có thể trùng. `groupingBy` và `summingInt` phù hợp với báo cáo tổng hợp.
- Không giả định thứ tự `HashMap`, độ nhất quán snapshot của `ConcurrentHashMap` hoặc lợi ích hiệu năng của `parallelStream()`. Lựa chọn dựa trên hợp đồng nguồn và nhu cầu nghiệp vụ.
