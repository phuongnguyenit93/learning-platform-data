# collect() và phép rút gọn với vùng tích lũy có thể thay đổi

## Mục tiêu bài học

Trong Java Stream, **`collect()`** là thao tác kết thúc (*terminal operation*) dùng để thu các phần tử thành một kết quả có cấu trúc. Một khả năng quan trọng là **mutable reduction**: thay vì tính một giá trị mới hoàn toàn ở mỗi bước, chương trình tạo một **vùng tích lũy có thể thay đổi** (mutable result container), thêm dữ liệu vào nó và kết hợp các vùng tích lũy từng phần khi cần.

Sau bài này, bạn có thể:

- Hiểu đúng cơ chế `collect(supplier, accumulator, combiner)` trên `Stream<T>`.
- Viết ba hàm tạo container, tích lũy phần tử, kết hợp container mà không chia sẻ sai trạng thái.
- Dùng `collect` tạo `ArrayList`, `LinkedHashSet`, `Map` hoặc một class thống kê mutable tùy nghiệp vụ.
- So sánh `collect` dạng ba tham số với `collect(Collector)` và các `Collectors` chuẩn.
- Phân biệt **mutable reduction bằng collect** với **immutable/value reduction bằng reduce**.
- Nhận diện identity, yêu cầu kết hợp, đặc tính thứ tự, lỗi concurrent, ngoại lệ và tài nguyên.
- Biên dịch/chạy ví dụ Java 17 rồi dự đoán kết quả khi nguồn rỗng và khi dùng parallel stream.

## 1. Vùng tích lũy mutable là gì?

Giả sử có Stream chứa `"Book"`, `"Pen"`, `"Tea"`. Ta muốn tạo một `ArrayList<String>` để thêm/xóa phần tử sau khi thu thập. Một cách suy nghĩ trực tiếp là:

1. Tạo danh sách rỗng `new ArrayList<String>()`.
2. Với mỗi phần tử Stream, gọi `list.add(element)` trên danh sách đang được tích lũy.
3. Nếu chạy song song, có thể có nhiều danh sách từng phần; kết hợp các danh sách bằng `left.addAll(right)`.
4. Trả lại vùng tích lũy sau khi hoàn thành.

Đây chính là hình thức mutable reduction mà overload ba tham số của `collect` hỗ trợ.

```java
ArrayList<String> names = Stream.of("Book", "Pen", "Tea")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

Kết quả chứa `[Book, Pen, Tea]`. Điểm thiết yếu không phải tên `ArrayList`, mà là quy trình **khởi tạo một container mới → cập nhật nó bằng các phần tử → ghép các container thành kết quả cuối**.

Mutable reduction **không có nghĩa sửa đổi collection nguồn**. Nó có nghĩa sửa một **container kết quả** được cấp phát riêng cho phép thu thập. Nên để các thao tác trung gian `map`, `filter` không có tác dụng phụ không cần thiết và hạn chế đột biến nguồn đang duyệt.

## 2. Hai overload chính của collect()

### 2.1. collect(supplier, accumulator, combiner)

Chữ ký trên `Stream<T>`:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
```

Đây là chữ ký API rút gọn để học, không phải một phương thức cần tự khai báo lại. Ba functional interface đến từ `java.util.function`.

| Tham số | Function descriptor | Nhiệm vụ |
| --- | --- | --- |
| `supplier` | `() -> R` | Tạo một vùng tích lũy `R` **mới** ở trạng thái ban đầu |
| `accumulator` | `(R, T) -> void` | Đưa phần tử `T` vào vùng tích lũy `R` |
| `combiner` | `(R, R) -> void` | Ghép container thứ hai vào container thứ nhất khi cần |
| Giá trị trả về | `R` | Container hoặc object kết quả |

Ví dụ:

```java
ArrayList<String> names = Stream.of("A", "B", "C").collect(
        ArrayList::new,      // Supplier<ArrayList<String>>
        ArrayList::add,      // BiConsumer<ArrayList<String>, String>
        ArrayList::addAll    // BiConsumer<ArrayList<String>, ArrayList<String>>
);
```

Dạng `collect` này đặc biệt dễ hiểu với các kiểu có API thêm/gộp phần tử rõ như `List`, `Set`, `StringBuilder` hoặc một class accumulator tự định nghĩa. `combiner` trả `void`; nó phải tạo tác dụng gộp đúng vào container được truyền, không chỉ tạo một object khác rồi bỏ đi.

Trong Stream tuần tự đơn giản, runtime có thể chỉ cần một container nên combiner không nhất thiết chạy. **Không được kết luận combiner không quan trọng**: Stream song song hoặc cách triển khai hợp lệ khác có thể dùng nó để ghép kết quả từng phần.

### 2.2. collect(Collector)

Dạng còn lại:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

`Collector` là một đối tượng mô tả quy trình tích lũy, gồm cách tạo container, thêm phần tử, kết hợp container, hoàn thiện kết quả và các characteristics. Với `Collector<T,A,R>`, kiểu trung gian `A` **có thể khác** kiểu đầu ra `R`.

```java
List<String> names = Stream.of("A", "B", "C")
        .collect(Collectors.toList());
```

`Collectors` (thuộc `java.util.stream`) có các factory hữu ích: `toList`, `toSet`, `toMap`, `groupingBy`, `mapping`, `joining`, `counting`, `summarizingInt`, `toCollection`.

Hai overload cùng là terminal operation. Tuy nhiên:

- Overload ba tham số làm rõ ba hàm `supplier/accumulator/combiner`, kết quả là container `R` được tích lũy.
- Overload nhận Collector có thể thực hiện **finisher** để chuyển accumulator `A` thành kết quả cuối `R`, hỗ trợ kết hợp Collector theo tầng, và mang các đặc tính phục vụ tối ưu hóa.
- Nếu có sẵn Collector chuẩn với ý nghĩa rõ, thường nên ưu tiên nó trước khi tự viết một cơ chế tích lũy nhiều bước.

**Lưu ý phiên bản:** `Stream.collect` và `Collectors` tồn tại từ Java 8; các ví dụ đầy đủ phía dưới dùng Java 17. Đừng nhầm với `Stream.toList()` (Java 16+) vốn trả List không cho phép sửa cấu trúc.

## 3. Supplier: phải tạo accumulator mới, không dùng chung một object

Trong mutable collect, `supplier` có thể được gọi nhiều lần để tạo container riêng cho các phần của pipeline. Vì vậy, nó cần cung cấp **một result container mới tương thích trạng thái rỗng** trên mỗi lần gọi.

**Đúng:**

```java
ArrayList<String> collected = Stream.of("A", "B", "C")
        .parallel()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

`ArrayList::new` tạo một danh sách khác nhau khi được gọi mỗi lần. Các vùng từng phần có thể được gộp về sau.

**Sai ý định:**

```java
ArrayList<String> shared = new ArrayList<>();

List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                () -> shared,
                List::add,
                List::addAll
        );
```

Đoạn trên có thể biên dịch, nhưng `() -> shared` **luôn trả cùng một danh sách**; điều này phá yêu cầu container rỗng, độc lập cho mỗi lần supplier được gọi. Trong xử lý song song có thể xảy ra mất dữ liệu, đua ghi hoặc `left.addAll(right)` nhận cùng object ở hai vị trí gây nhân bản sai. Ngay cả trong pipeline tuần tự, việc tái sử dụng container đã chứa sẵn dữ liệu cũng làm mất tính rõ ràng của hợp đồng.

Cách sửa: dùng `ArrayList::new`. Nếu muốn bắt đầu từ dữ liệu nền, cần mô hình hóa cách khởi tạo mỗi container và cách kết hợp sao cho không nhân bản dữ liệu nền qua nhiều nhánh. Không lấy một List từ bên ngoài để dùng chung cho mọi accumulator của parallel reduction.

**Phân biệt:** có thể dùng một `StringBuilder` mutable bên trong container được tạo, nhưng không chia sẻ cùng `StringBuilder` đó giữa tất cả kết quả từng phần.

## 4. Accumulator: sửa container kết quả, không sửa nguồn

`accumulator` nhận một container hiện tại `R` và phần tử `T`. Nó nên **đưa phần tử vào trạng thái tích lũy** mà vẫn giữ được hợp đồng kết quả.

```java
ArrayList<String> names = Stream.of("A", "B")
        .collect(
                ArrayList::new,
                (list, value) -> list.add(value),
                ArrayList::addAll
        );
```

Với `List`, lời gọi `add` trả `boolean`, nhưng `BiConsumer.accept` trả `void`. Method reference `ArrayList::add` vẫn tương thích: giá trị trả về của statement expression được bỏ qua trong ngữ cảnh `void`.

### 4.1. Thêm dữ liệu sau phép biến đổi

Muốn thu tên sản phẩm, có thể ánh xạ trước:

```java
ArrayList<String> names = sales.stream()
        .map(Sale::product)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Đây là đoạn minh họa với `Sale` được định nghĩa ở chương trình đầy đủ. `map` biến từng `Sale` thành `String`, nên tại `collect` ta có `T = String` và `R = ArrayList<String>`.

Cũng có thể giữ nguồn `Stream<Sale>` và viết accumulator:

```java
ArrayList<String> names = sales.stream().collect(
        ArrayList::new,
        (list, sale) -> list.add(sale.product()),
        ArrayList::addAll
);
```

Hai cách cùng tạo tên sản phẩm. Cách nào rõ hơn tùy độ phức tạp; pipeline `map(...).collect(...)` thường cho các bước một chức năng dễ kiểm thử.

### 4.2. Callback không nên có side effect không thuộc kết quả

`accumulator` được phép sửa container `R` do cơ chế collect cấp; **không có nghĩa** nên tự ý sửa `sales`, ghi database, gửi email hoặc cập nhật chung một biến đếm bên ngoài. Một pipeline song song có thể thay đổi cách chia nhóm và thứ tự thực thi.

Nếu cần thao tác nghiệp vụ bắt buộc đúng một lần, hãy thực hiện ở một tầng điều phối có kiểm soát, thay vì ẩn trong accumulator chỉ nhằm đếm/thu dữ liệu. Sự tồn tại của mutable reduction không biến các side effect bên ngoài thành transaction.

## 5. Combiner: ghép đúng hai trạng thái từng phần

Đây là phần dễ viết sai nhất khi mới học `collect`. `combiner` của overload ba tham số nhận hai container `R`, **kết hợp nội dung thứ hai vào thứ nhất**, không trả một container thay thế:

```java
(left, right) -> left.addAll(right)
```

Với `ArrayList`, `addAll` thêm các phần tử từ `right` vào `left`. Đối với một thống kê:

```java
(left, right) -> {
    left.count += right.count;
    left.total += right.total;
}
```

Đoạn thống kê là minh họa, giả sử `left/right` thuộc một class có các trường `count` và `total`.

### 5.1. Sai: combiner không thực sự gộp

```java
// Sai logic: không thêm nội dung right vào left.
(left, right) -> {
    new ArrayList<>(right);
}
```

Câu lệnh tạo List tạm rồi bỏ đi, nên dữ liệu phần `right` không được đưa vào `left`. Với Stream tuần tự, lỗi này có thể bị che vì combiner không chạy. Khi chạy song song, phần dữ liệu có thể bị mất.

**Quy tắc:** trong overload ba tham số, combiner phải làm thay đổi vùng tích lũy nhận đầu tiên sao cho nó đại diện đúng kết quả kết hợp hai nhánh.

### 5.2. Tính trung hòa và tính kết hợp

Mỗi kết quả do supplier tạo phải là trạng thái **rỗng/trung hòa** cho phép tích lũy. Cách kết hợp các nhánh phải tạo kết quả tương đương dù nhóm phần tử khác nhau theo thứ tự cho phép:

- Với danh sách có encounter order, `addAll` ghép đúng thứ tự các phần cần ghép.
- Với số đếm, cộng hai số đếm.
- Với Map số lượng theo khóa, cộng giá trị tương ứng cùng khóa.
- Với thống kê phức tạp, kết hợp đầy đủ mọi trường cần thiết (count, sum, min, max…), không bỏ một thành phần.

Ví dụ một thiết kế thống kê có `count` và `sum`: nếu combiner chỉ cộng `sum` mà quên `count`, kết quả trung bình `sum/count` sẽ sai trong một pipeline song song.

**Điều kiện tương thích:** khi tích lũy một phần tử rồi gộp với phần còn lại, kết quả phải phù hợp với việc gộp các phần kết quả đã được tích lũy riêng. Đây là cơ sở để runtime phân vùng công việc mà vẫn giữ ý nghĩa phép thu thập.

## 6. Ví dụ đơn giản: List, Set, Map và StringBuilder

### 6.1. ArrayList mutable

```java
ArrayList<String> names = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
names.add("D"); // hợp lệ
```

Khi yêu cầu một List có thể chỉnh sửa cấu trúc, `collect(Collectors.toCollection(ArrayList::new))` cũng diễn đạt rất rõ. `Stream.toList()` thì trả List không sửa được.

### 6.2. LinkedHashSet theo thứ tự thêm

```java
LinkedHashSet<String> unique = Stream.of("java", "api", "java")
        .collect(
                LinkedHashSet::new,
                LinkedHashSet::add,
                LinkedHashSet::addAll
        );
```

Kết quả lặp theo thứ tự chèn `java` rồi `api`. Với `Collectors.toSet()`, loại Set và thứ tự iteration không được hứa. Khi cần loại cụ thể, hãy yêu cầu bằng `toCollection(LinkedHashSet::new)` hoặc overload ba tham số như trên.

### 6.3. Map cộng dồn theo khóa

Giả sử mỗi `Sale` có `category()` và `units()`:

```java
Map<String, Integer> totals = sales.stream().collect(
        TreeMap::new,
        (map, sale) -> map.merge(
                sale.category(), sale.units(), Integer::sum),
        (left, right) -> right.forEach((key, value) ->
                left.merge(key, value, Integer::sum))
);
```

`supplier` cấp `TreeMap` mới. Accumulator cộng `units` vào category. Combiner duyệt Map bên phải rồi cộng giá trị của các khóa tương ứng vào bên trái.

Ở ví dụ song song, **mỗi accumulator Map là một kết quả từng phần**, không phải một TreeMap chung để tất cả thread trực tiếp gọi `merge` mà không đồng bộ. Sự độc lập của container là điểm then chốt.

Trong mã sản phẩm, thường có thể thay bằng Collector chuẩn dễ bảo trì:

```java
Map<String, Integer> totals = sales.stream().collect(
        Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::units)
        )
);
```

Hai đoạn tạo cùng loại kết quả tổng số lượng theo category trong dữ liệu mẫu. `groupingBy` diễn đạt chủ ý nhóm dữ liệu rõ hơn một thuật toán gộp Map tự viết.

### 6.4. StringBuilder và lỗi dấu phân cách

`StringBuilder` là vùng tích lũy mutable thích hợp để nối văn bản:

```java
StringBuilder result = Stream.of("Book", "Pen", "Tea").collect(
        StringBuilder::new,
        (sb, text) -> {
            if (sb.length() > 0) sb.append(" | ");
            sb.append(text);
        },
        (left, right) -> {
            if (left.length() > 0 && right.length() > 0) {
                left.append(" | ");
            }
            left.append(right);
        }
);
```

Với dữ liệu chỉ gồm chuỗi **không rỗng** trong ví dụ, kết quả là `Book | Pen | Tea`.

Lưu ý **không sao chép quy tắc này cho mọi chuỗi một cách máy móc**: một chuỗi rỗng `""` có thể là phần tử hợp lệ, nhưng `StringBuilder.length() == 0` không phân biệt “chưa có phần tử” với “đã thêm một chuỗi rỗng”. Nếu cần nối chính xác bất kể chuỗi rỗng, nên dùng `Collectors.joining(" | ")` hoặc class accumulator có thêm số phần tử để quản lý dấu phân cách.

```java
String result = Stream.of("Book", "Pen", "Tea")
        .collect(Collectors.joining(" | "));
```

Collector `joining` là lựa chọn dễ đọc hơn khi tác vụ chỉ là ghép chuỗi. Không cần tự tạo mutable result container nếu thư viện đã có implementation chuẩn phù hợp.

## 7. Chương trình Java 17 hoàn chỉnh

Chương trình sau minh họa ba hàm chính, kết hợp dữ liệu trong parallel stream, thống kê bằng class mutable và các Collector tương đương. Mọi kết quả được in theo thứ tự xác định.

Lưu vào tệp **`MutableCollectDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MutableCollectDemo {
    record Sale(String product, String category, int units,
                long unitPriceCents) {}

    static final class Stats {
        long count;
        long units;
        long revenueCents;

        void add(Sale sale) {
            count++;
            units += sale.units();
            revenueCents += sale.units() * sale.unitPriceCents();
        }

        void merge(Stats other) {
            count += other.count;
            units += other.units;
            revenueCents += other.revenueCents;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Book", "office", 2, 1_250),
                new Sale("Pen", "office", 3, 200),
                new Sale("Tea", "food", 1, 700)
        );

        ArrayList<String> names = sales.stream()
                .map(Sale::product)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        names.add("Extra");
        System.out.println("Names: " + names);

        LinkedHashSet<String> categories = sales.stream()
                .map(Sale::category)
                .collect(LinkedHashSet::new, LinkedHashSet::add,
                        LinkedHashSet::addAll);
        System.out.println("Categories: " + categories);

        Stats stats = sales.parallelStream()
                .collect(Stats::new, Stats::add, Stats::merge);
        System.out.println("Stats: count=" + stats.count
                + ", units=" + stats.units
                + ", revenue=" + stats.revenueCents);

        Map<String, Integer> unitTotals = sales.parallelStream().collect(
                TreeMap::new,
                (map, sale) -> map.merge(
                        sale.category(), sale.units(), Integer::sum),
                (left, right) -> right.forEach((key, value) ->
                        left.merge(key, value, Integer::sum))
        );
        System.out.println("By category: " + unitTotals);

        StringBuilder joined = sales.stream()
                .map(Sale::product)
                .collect(
                        StringBuilder::new,
                        (sb, name) -> {
                            if (sb.length() > 0) sb.append(" | ");
                            sb.append(name);
                        },
                        (left, right) -> {
                            if (left.length() > 0 && right.length() > 0)
                                left.append(" | ");
                            left.append(right);
                        });
        System.out.println("Joined: " + joined);

        List<String> standard = sales.stream()
                .map(Sale::product)
                .collect(Collectors.toList());
        System.out.println("Standard: " + standard);

        System.out.println("Empty stats: " +
                List.<Sale>of().stream()
                        .collect(Stats::new, Stats::add, Stats::merge).count);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac MutableCollectDemo.java
java MutableCollectDemo
```

**Stdout chính xác:**

```text
Names: [Book, Pen, Tea, Extra]
Categories: [office, food]
Stats: count=3, units=6, revenue=3800
By category: {food=1, office=5}
Joined: Book | Pen | Tea
Standard: [Book, Pen, Tea]
Empty stats: 0
```

### Phân tích kết quả

1. `names` được collect thành một `ArrayList` mutable nên `names.add("Extra")` thành công và in bốn phần tử.
2. `categories` là `LinkedHashSet`: loại trùng category `office`, giữ thứ tự gặp đầu tiên là `office` rồi `food`.
3. `Stats::new` tạo trạng thái với ba trường `long` mặc định bằng 0. `Stats::add` cập nhật từng Sale, `Stats::merge` cộng các kết quả từng phần. Ba dòng Sale có `units = 2,3,1` nên tổng units là `6`; doanh thu xu là `2*1250 + 3*200 + 1*700 = 3800`.
4. `TreeMap` sắp khóa category theo thứ tự tự nhiên, nên Map in `{food=1, office=5}`. `office` có `2+3 = 5`, `food` có `1`.
5. `StringBuilder` tích lũy tên sản phẩm và dấu `" | "`. Do cả ba tên đều khác chuỗi rỗng, kết quả `Book | Pen | Tea` đúng.
6. `Collectors.toList()` thu danh sách tên. Chương trình chỉ in kết quả, **không mặc định List của collector này là mutable**.
7. Stream rỗng vẫn được supplier cấp một `Stats` có giá trị mặc định `count = 0`, nên `Empty stats: 0`.

Hai phép `parallelStream()` trong ví dụ **không chia sẻ một Stats hay TreeMap toàn cục**. Mỗi lần supplier cần một container, nó tạo container riêng; combiner định nghĩa cách ghép. Kết quả bài toán cộng số có ý nghĩa không phụ thuộc cách chia thành các nhánh.

Nếu số lượng tiền có thể vượt phạm vi `long`, chương trình cần giải pháp kiểm soát tràn hoặc dùng kiểu số lớn hơn; trong dữ liệu ví dụ, mọi phép tính nằm trong phạm vi hợp lệ.

## 8. collect() và reduce(): khác nhau ở cách biểu diễn sự tích lũy

`reduce` thường được dùng khi cần tạo **một giá trị mới** từ kết quả trước và phần tử kế tiếp:

```java
int sum = Stream.of(2, 3, 1)
        .reduce(0, Integer::sum); // 6
```

Còn `collect` phù hợp khi cần **một đối tượng tích lũy mutable**:

```java
ArrayList<Integer> values = Stream.of(2, 3, 1)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

So sánh:

| Tiêu chí | `reduce` | `collect` với mutable container |
| --- | --- | --- |
| Mục tiêu điển hình | Tổng, tích, max/min, chuỗi tổng hợp, giá trị bất biến | List, Set, Map, thống kê nhiều trường |
| Accumulator | Thường trả giá trị kết quả mới | `BiConsumer` sửa container được truyền |
| Identity | Giá trị trung hòa cho phép gộp | Container rỗng mới từ supplier |
| Kết hợp | `BinaryOperator` trả giá trị gộp | `BiConsumer<R,R>` sửa container thứ nhất |
| Tạo List bằng cách sửa identity | Sai mô hình | Chính là một ứng dụng phổ biến |
| Xử lý parallel | Cần phép kết hợp và identity đúng | Cần supplier cấp container độc lập, accumulator/combiner đúng |

### Anti-pattern: reduce với ArrayList mutable

```java
// Không nên dùng làm cách thu List, nhất là trên parallel Stream.
List<String> wrong = Stream.of("A", "B", "C").parallel()
        .reduce(
                new ArrayList<>(),
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

Đây là **mã minh họa một thiết kế sai**, không phải mẫu nên sao chép. Đối tượng identity `new ArrayList<>()` không được thiết kế để bị nhiều nhánh sửa chung. Hàm accumulator vừa thay đổi trạng thái object vừa trả chính object ấy, vi phạm nguyên tắc cần thiết để `reduce` hoạt động đúng trong nhiều cách phân chia.

**Cách đúng:**

```java
List<String> collected = Stream.of("A", "B", "C").parallel()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Lưu ý rằng `reduce` với **giá trị bất biến** có thể đúng và phù hợp, ví dụ `reduce(0L, Long::sum)`. Không có nghĩa `reduce` luôn chậm hoặc sai; chỉ cần dùng đúng mô hình phép gộp.

## 9. Quy tắc khi chạy song song

### 9.1. Không cần ArrayList tự thread-safe nếu mỗi nhánh có container độc lập

Trong một phép `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)`, framework tổ chức việc tạo và kết hợp các vùng tích lũy để thực hiện reduction. Người lập trình **không phải đặt một `ArrayList` chia sẻ vào biến static** hay viết synchronized cho từng `add` ở mọi trường hợp.

Điều cần bảo đảm là:

- Supplier tạo container rỗng và mới mỗi lần cần.
- Accumulator chỉ cập nhật container của nhánh được cấp, không cập nhật container chung được capture từ bên ngoài.
- Combiner gộp đúng hai container; không làm mất hoặc nhân bản phần tử.
- Các hàm không phụ thuộc một trạng thái bên ngoài bị thay đổi không kiểm soát.
- Nếu có yêu cầu thứ tự, phải giữ kết quả đúng theo encounter order và quy tắc Collector/Stream.

Điều này **không biến ArrayList kết quả thành thread-safe để sử dụng về sau**. Nếu nhiều thread cùng sửa danh sách sau khi thu, ứng dụng vẫn phải đồng bộ hoặc chọn cấu trúc dữ liệu thích hợp.

### 9.2. Combiner có thể không chạy trong pipeline tuần tự

Đừng kiểm thử chỉ bằng một Stream tuần tự rồi cho rằng combiner đúng. Một combiner sai có thể không được gọi ở đường chạy đó. Hãy kiểm thử cả trường hợp chia dữ liệu thành các nhánh riêng, chạy `parallelStream` với kết quả có thể tính độc lập, và kiểm tra trường hợp rỗng.

**Không dùng log thứ tự của lambda như bằng chứng tính đúng đắn** trong parallel: thứ tự và số lần tạo container có thể phụ thuộc chiến lược runtime, kích thước dữ liệu và cấu trúc nguồn.

### 9.3. collect không đồng nghĩa Collector.CONCURRENT

Có hai ý tưởng khác nhau:

1. `collect(supplier, accumulator, combiner)` tạo và kết hợp các container, có thể dùng với Stream song song khi các hàm đáp ứng hợp đồng.
2. Một `Collector` có characteristic `CONCURRENT` biểu đạt rằng container của Collector có thể được accumulator cập nhật đồng thời từ nhiều thread theo những điều kiện của API.

`Collectors.toConcurrentMap` và `groupingByConcurrent` là những ví dụ tạo collector cho các cấu trúc concurrent trong tình huống phù hợp. Tuy nhiên, **không tự viết `Collector.Characteristics.CONCURRENT`** cho một accumulator sử dụng `ArrayList` hoặc `HashMap` thường rồi hy vọng runtime tự đồng bộ. Nếu công bố characteristic này, phần tích lũy phải thực sự đáp ứng việc cập nhật đồng thời đúng hợp đồng.

Collector có `UNORDERED` cũng không giống việc output Map hoặc Set “tình cờ in ra không theo thứ tự”. Đặc tính của Collector là thông tin cho runtime và ảnh hưởng đến điều kiện tối ưu; cần hiểu rõ trước khi tự định nghĩa Collector.

### 9.4. Tính kết hợp và thứ tự dữ liệu

`List.addAll` và phép cộng tổng theo từng nhóm có tính chất cần thiết để ghép kết quả từng phần khi nhóm đúng. Nhưng không phải mọi phép biến đổi trên mutable object đều an toàn: ví dụ một combiner lấy hiệu `left.count -= right.count` sẽ cho kết quả sai khi kết hợp theo cách khác nhau.

Nếu muốn một output có thứ tự cụ thể, `LinkedHashSet`/`LinkedHashMap` và nguồn ordered có thể là phần của thiết kế. Với Map có thứ tự khóa theo comparator, dùng `TreeMap` như chương trình chính. Nếu chỉ cần tổng số, không dựa vào thứ tự việc gộp nhánh.

## 10. Stream.collect() không thay thế quản lý tài nguyên

`collect` kích hoạt pipeline nhưng **không tự đóng mọi Stream nguồn có tài nguyên I/O**. Ví dụ `Files.lines(path)` có thể giữ một file đang mở. Khi cần thu dữ liệu từ file:

```java
// Minh họa: path là java.nio.file.Path đã khai báo;
// phương thức bao quanh phải xử lý/khai báo IOException.
try (Stream<String> lines = Files.lines(path)) {
    List<String> content = lines
            .filter(s -> !s.isBlank())
            .collect(Collectors.toList());
}
```

`try-with-resources` là nơi bảo đảm đóng Stream. Không mặc định terminal operation `collect` đồng nghĩa `close()`.

**Không thu một Stream vô hạn thành danh sách vô hạn**: `Stream.generate(...)` tạo nguồn không giới hạn theo ngữ nghĩa, nên `collect(toList())` không có điều kiện dừng có thể chạy mãi hoặc hết bộ nhớ. Dùng `limit` hay một chiến lược dừng phù hợp trước khi thu.

Nếu bạn chỉ cần **một thống kê**, có thể tránh giữ toàn bộ phần tử bằng cách collect vào đối tượng thống kê nhỏ. Đây là lợi ích thiết kế quan trọng của mutable reduction.

## 11. Null, ngoại lệ và tính đúng đắn

### 11.1. Null trong Stream đầu vào

Một `Stream<String>` có thể chứa phần tử `null` nếu nguồn cho phép. `ArrayList::add` chấp nhận null; nhưng một accumulator gọi `value.length()` sẽ gây `NullPointerException` nếu `value` null.

```java
ArrayList<String> values = Stream.of("A", null, "B")
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
// [A, null, B]
```

Nếu null là dữ liệu không hợp lệ, cần xác thực, lọc có chủ đích hoặc báo lỗi. Không đơn giản chọn accumulator bỏ qua null khi nghiệp vụ yêu cầu phát hiện dữ liệu thiếu.

### 11.2. Supplier, accumulator, combiner có thể ném runtime exception

Nếu accumulator ném `IllegalArgumentException` hoặc lỗi khác, terminal operation có thể kết thúc bất thường. Những thay đổi **đã xảy ra trên object bên ngoài** không tự rollback. Không dùng mutable collect như một giao dịch database; phải thiết kế chính sách lỗi và bồi hoàn riêng.

`Supplier.get()`, `BiConsumer.accept()` không khai báo checked exception. Nếu accumulator gọi API có `IOException`, cần xử lý nó trong callback, chuyển loại ngoại lệ theo quy tắc ứng dụng, hoặc tách thao tác I/O ra khỏi bước thu thập.

### 11.3. Null container và kiểu kết quả

Supplier cần trả một container thích hợp. `() -> null` có thể khiến accumulator/combiner gặp lỗi và vi phạm hợp đồng mong đợi. Một `Collector` có finisher không được tùy tiện trả null nếu nơi sử dụng không chấp nhận; cần định nghĩa rõ hợp đồng kết quả.

Khi kết quả là một Map, mapper có thể tạo khóa trùng. Nếu dùng `toMap` không có merge function, các khóa trùng có thể ném `IllegalStateException`. Nếu mục tiêu là cộng dồn, dùng overload `toMap` có merge function hoặc `groupingBy` với downstream phù hợp.

### 11.4. Tràn số và dữ liệu lớn

Trong `Stats` mẫu, count, units, revenue dùng `long`. Nhưng `long` vẫn có giới hạn. Nếu dữ liệu có thể vượt phạm vi, dùng phép tính kiểm tra tràn, `BigInteger` hoặc `BigDecimal` theo nghiệp vụ, thay vì tin rằng kết quả của `collect` tự động an toàn số học.

Đặc biệt với tiền tệ, tránh `double` nếu cần chính xác đến đơn vị nhỏ hoặc áp dụng quy tắc làm tròn; dữ liệu mẫu dùng **xu dạng `long`** để dễ kiểm chứng.

## 12. Khi nào nên dùng cách nào?

| Nhu cầu | Cách phù hợp | Ghi chú |
| --- | --- | --- |
| Chỉ lấy danh sách để đọc, không cần sửa | `stream.toList()` | List unmodifiable, Java 16+ |
| Cần ArrayList mutable | `collect(toCollection(ArrayList::new))` | Nêu rõ loại kết quả |
| Muốn hiểu hoặc tùy biến quy trình thêm/gộp List | `collect(ArrayList::new, List::add, List::addAll)` | Ba hàm tường minh |
| Cần Set không trùng, loại cụ thể | `collect(toCollection(LinkedHashSet::new))` | Có thể giữ thứ tự chèn |
| Cần Map tổng theo khóa | `groupingBy(..., summingInt(...))` | Thường dễ hiểu hơn tự gộp Map |
| Cần tổng, tích, min/max | `reduce(...)` hoặc primitive `sum/min/max` | Giá trị gộp, không cần container lớn |
| Cần nhiều thống kê trên một lần duyệt | `summaryStatistics()` hoặc custom mutable collector | Có thể tránh giữ toàn bộ phần tử |
| Cần chuỗi nối với dấu phân cách | `Collectors.joining(delimiter)` | Xử lý chuỗi rỗng đúng ngữ nghĩa |
| Cần output dạng record bất biến | Collector có finisher hoặc collect rồi chuyển đổi | Giữ accumulator nội bộ, kết quả public bất biến |
| Cần cập nhật shared cache/database | API đồng bộ/giao dịch chuyên dụng | Không biến collect thành công cụ side effect |

Một nguyên tắc thực tế: **dùng Collector chuẩn nếu nó diễn đạt đúng nhu cầu; tự viết mutable collect chỉ khi cần một quy tắc tích lũy riêng hoặc đang học cơ chế API**. Mã viết bằng lambda ngắn không tự động đúng khi chạy song song.

## 13. Những lỗi phổ biến

1. **Supplier trả cùng mutable container** cho mọi lần gọi → chia sẻ trạng thái, sai khi kết hợp và có thể race.
2. **Quên combiner** hoặc combiner không thêm dữ liệu của container phải → chỉ lộ lỗi khi phải ghép các phần.
3. **Combiner sửa object ngoài thay vì container nhận vào** → kết quả sai, không đáp ứng contract.
4. **Dùng `reduce` để `add` vào ArrayList identity** → vi phạm mô hình reduction; dùng `collect`.
5. **Tin rằng `Collectors.toList()` luôn mutable** → API không bảo đảm; dùng `toCollection(ArrayList::new)`.
6. **Tin rằng `Stream.toList()` mutable** → thực tế nó unmodifiable.
7. **Chia sẻ ArrayList hoặc HashMap từ biến ngoài cho parallel accumulator** → không tự thread-safe.
8. **Đặt side effect như gửi email trong accumulator** → thời điểm và luồng thực thi phụ thuộc pipeline; không có transaction.
9. **Quên ghép tất cả trường thống kê** → count, sum hoặc các chỉ số khác có thể sai.
10. **Dùng StringBuilder.length() để suy số phần tử** khi phần tử có thể là chuỗi rỗng → dấu phân cách sai.
11. **Quên nguồn rỗng** → Supplier vẫn phải tạo trạng thái rỗng có nghĩa; nếu không có phần tử thì không giả định accumulator đã chạy.
12. **Lẫn collect với resource close** → terminal không tự đóng Stream dùng file/network.
13. **Cho rằng kết quả có thứ tự cố định khi nguồn unordered** → chọn cấu trúc và quy tắc thứ tự rõ.
14. **Quên khả năng tràn số hoặc parse lỗi** → làm sai thống kê dù collect đúng hợp đồng.
15. **Mặc định mọi Collector là CONCURRENT** → chỉ collector đã công bố và thực hiện đúng characteristic mới hỗ trợ cách tích lũy đồng thời tương ứng.

## 14. Bài tập tự luyện

**Bài 1.** Tạo `ArrayList<Integer>` từ `Stream.of(2, 4, 6)` bằng collect ba tham số. Viết rõ vai trò của `supplier`, `accumulator`, `combiner`.

**Bài 2.** Với `Stream.of("java", "api", "java")`, tạo `LinkedHashSet<String>`. Vì sao `LinkedHashSet` có lợi nếu cần thứ tự xuất hiện đầu tiên?

**Bài 3.** Cho `record Item(String group, int count) {}`. Tạo `TreeMap<String,Integer>` cộng `count` theo group bằng collect ba tham số. Viết combiner sao cho hai Map từng phần có các khóa trùng vẫn cho tổng đúng.

**Bài 4.** Định nghĩa class `Summary` có `long count` và `long sum`. Viết `add(int value)` và `merge(Summary other)`; sử dụng `collect(Summary::new, ..., ...)` và nêu kết quả khi nguồn rỗng.

**Bài 5.** Vì sao `() -> sharedList` là supplier không phù hợp cho parallel collect? Ngay cả khi dùng `Collections.synchronizedList`, vấn đề nào vẫn còn liên quan đến hợp đồng identity/combiner?

**Bài 6.** So sánh `stream.collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` và `stream.collect(Collectors.toCollection(ArrayList::new))` về loại kết quả và độ rõ ý định.

**Bài 7.** Nếu `combiner` chỉ thực hiện `left.addAll(left)` thay vì `left.addAll(right)`, lỗi nào có thể xảy ra khi chạy song song?

**Bài 8.** Có nên dùng `reduce(new ArrayList<>(), ...)` để tạo một List rồi sửa identity trong accumulator? Vì sao?

**Bài 9.** Với chuỗi nguồn có thể chứa `""`, hãy chọn `Collectors.joining(" | ")` thay vì tự dùng `StringBuilder.length()` để phân biệt danh sách rỗng. Tại sao?

**Bài 10.** Bạn cần thống kê tổng số hàng, tổng số lượng và tổng doanh thu từ `Stream<Sale>`. Khi nào một custom accumulator mutable thích hợp hơn việc `toList()` rồi duyệt lại?

**Bài 11.** Chạy một phép collect trên `parallelStream()` và phát hiện kết quả thiếu vài phần tử. Những thành phần nào cần kiểm tra đầu tiên? Có nên giả định runtime có bug?

**Bài 12.** Một Stream đọc từ `Files.lines(path)` được collect thành List. Vì sao vẫn cần `try-with-resources`? Có cách nào giảm bộ nhớ nếu chỉ cần đếm và tổng?

### Gợi ý đáp án

1. `Stream.of(2,4,6).collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` → `[2,4,6]`; ba thành phần lần lượt tạo mới, thêm phần tử, ghép List.
2. `collect(LinkedHashSet::new, LinkedHashSet::add, LinkedHashSet::addAll)` → lần lượt `java`, `api`, không lặp.
3. Supplier `TreeMap::new`, accumulator `map.merge(item.group(), item.count(), Integer::sum)`, combiner lặp `right.forEach((k,v) -> left.merge(k,v,Integer::sum))`.
4. `count++`, `sum += value` ở accumulator; combiner cộng hai trường; Stream rỗng trả summary có count và sum bằng 0.
5. Cùng container bị chia sẻ, không còn container mới và trung hòa; chỉ synchronized không sửa tính sai của việc gộp container với chính nó.
6. Cả hai có thể tạo `ArrayList` mutable; dạng Collector chuẩn thường ngắn và rõ hơn, dạng ba tham số giúp tự định nghĩa từng bước.
7. Có thể nhân bản dữ liệu nhánh trái, đánh mất dữ liệu nhánh phải.
8. Không; identity mutable được chia sẻ không phù hợp luật `reduce`, dùng `collect`.
9. `length() == 0` không đủ để biết đã có phần tử rỗng hay chưa; `joining` xử lý ngữ nghĩa phân cách theo từng phần tử.
10. Khi chỉ cần vài số tổng, custom accumulator không giữ toàn bộ Sale, giảm bộ nhớ và tránh duyệt lại nguồn khó tái sử dụng.
11. Kiểm tra supplier cấp container mới, accumulator cập nhật đúng, combiner gộp đúng, side effect và tương thích thứ tự trước khi kết luận về runtime.
12. `collect` không tự `close()` nguồn I/O; dùng try-with-resources. Nếu chỉ cần thống kê, thu vào accumulator nhỏ thay vì List lớn.

## Kết luận

**Mutable reduction bằng `collect()`** gồm ba nhiệm vụ cốt lõi: **tạo container mới**, **đưa từng phần tử vào container**, và **gộp các container từng phần**. Overload `collect(supplier, accumulator, combiner)` diễn đạt ba nhiệm vụ này trực tiếp; overload `collect(Collector)` đóng gói chúng cùng tùy chọn finisher và characteristics để tạo nhiều loại kết quả.

Hãy phân biệt rõ collect với reduce: **collect phù hợp khi tích lũy vào vùng mutable do phép thu thập quản lý; reduce phù hợp khi dùng giá trị trung hòa và phép gộp có tính kết hợp để tạo một giá trị**. Viết supplier độc lập, accumulator đúng phạm vi và combiner hợp đồng là chìa khóa để pipeline chính xác cả khi chạy tuần tự lẫn song song.
