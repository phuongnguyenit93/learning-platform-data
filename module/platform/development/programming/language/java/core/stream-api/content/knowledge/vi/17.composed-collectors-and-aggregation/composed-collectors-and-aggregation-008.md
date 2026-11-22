# Hoàn thiện kết quả bằng collectingAndThen

> **Chương:** Collector nhiều tầng và tổng hợp  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Dùng `Collectors.collectingAndThen` để áp dụng một bước **hoàn thiện kết quả** (*finishing transformation*) lên giá trị do collector bên trong tạo ra. Kỹ thuật này đặc biệt hữu ích khi kết hợp `groupingBy`, `partitioningBy`, `mapping`, `filtering`, `maxBy`, `summarizingInt` và collector tùy chỉnh.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác chữ ký `collectingAndThen(downstream, finisher)` và ba kiểu dữ liệu trung gian `T`, `A`, `R`, `RR`.
2. Phân biệt phép biến đổi **từng phần tử** trong `map`/`mapping` với phép biến đổi **kết quả sau thu thập** trong `collectingAndThen`.
3. Tạo kết quả không cho sửa cấu trúc bằng `List.copyOf`/`Map.copyOf`, đồng thời hiểu sự khác nhau giữa bất biến nông và bất biến sâu.
4. Rút giá trị từ `Optional` do `maxBy`/`minBy` trả về và xử lý trường hợp dữ liệu rỗng.
5. Hoàn thiện **từng nhóm** hoặc **toàn bộ Map** khi phối hợp nhiều tầng collector.
6. Trả DTO/record thống kê từ `IntSummaryStatistics` hoặc các giá trị tổng hợp thay vì để lộ trạng thái mutable.
7. Xác định tác động của `IDENTITY_FINISH`, tính kết hợp của downstream collector, thao tác song song và chi phí thực thi.
8. Viết kiểm tra cho nguồn rỗng, nhóm rỗng, dữ liệu null, tính không thể sửa và kết quả tuần tự/song song.

Các ví dụ sử dụng **Java 17+**. `collectingAndThen` và `groupingBy` có từ Java 8; `Collectors.filtering`/`flatMapping` có từ Java 9; `Collectors.teeing` có từ Java 12; `List.copyOf` có từ Java 10; `Stream.toList()` và `record` có từ Java 16.

## 1. Vì sao cần một bước hoàn thiện sau collect?

Trong Java Stream API, ta thường có pipeline khai báo:

~~~text
Nguồn dữ liệu
   │
   ├─ filter(...)       lọc phần tử
   ├─ map(...)          biến đổi phần tử
   │
   └─ collect(...)      tổng hợp toàn bộ dữ liệu
          │
          ├─ supplier    tạo container
          ├─ accumulator đưa từng phần tử vào container
          ├─ combiner    gộp container trung gian
          └─ finisher    trả kết quả cuối
~~~

Nhiều collector chuẩn tạo một kết quả **chưa đúng kiểu hoặc chưa đúng ràng buộc muốn công bố**. Ví dụ:

- Thu thập vào một `ArrayList` mutable, nhưng API muốn trả một `List` không cho chỉnh sửa.
- `maxBy` trả `Optional<T>`, nhưng yêu cầu nghiệp vụ muốn trực tiếp nhận `T` hoặc phát lỗi khi không có phần tử.
- `summarizingInt` trả `IntSummaryStatistics` mutable, nhưng API muốn một `record` bất biến.
- `groupingBy` trả `Map<K, List<T>>`, nhưng mỗi danh sách nhóm phải được chuẩn hóa, sắp xếp hoặc đóng băng cấu trúc.

Ta có thể xử lý kết quả sau khi `collect` trả về:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> mutable = List.of(" an ", " bình ", " chi ").stream()
        .map(String::strip)
        .collect(Collectors.toList());

List<String> immutable = List.copyOf(mutable);
System.out.println(immutable); // [an, bình, chi]
~~~

Hoặc gói luôn bước cuối vào collector:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutable = List.of(" an ", " bình ", " chi ").stream()
        .map(String::strip)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(immutable); // [an, bình, chi]
~~~

Hai đoạn cùng giải quyết ví dụ. Giá trị của `collectingAndThen` hiện rõ hơn khi phép hoàn thiện được **lồng vào một collector khác**, chẳng hạn chỉ chuyển đổi danh sách của từng nhóm trong `groupingBy`.

## 2. Hợp đồng API và dòng chảy của các kiểu dữ liệu

Chữ ký khái niệm của API:

~~~java
public static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher
);
~~~

Ý nghĩa của từng kiểu:

| Ký hiệu | Vai trò | Ví dụ |
|---|---|---|
| `T` | Phần tử đầu vào của Stream | `Order` |
| `A` | Trạng thái tích lũy bên trong downstream | `ArrayList<Order>` |
| `R` | Kết quả mà downstream collector tạo ra | `List<Order>` |
| `RR` | Kết quả **sau khi finisher hoàn thiện** | `List<Order>` bất biến, `Summary`, `String`... |

Có thể mô tả quá trình:

~~~text
Stream<T>
   |
   v
downstream: Collector<T, A, R>
   |   supplier / accumulator / combiner
   v
  A (trạng thái đã hoàn tất việc gộp)
   |
   | downstream.finisher()
   v
  R
   |
   | finisher.apply(R)
   v
  RR
~~~

`collectingAndThen` không thay chức năng tích lũy của downstream: nó sử dụng các thành phần downstream rồi **nối thêm một finisher** để chuyển `R` thành `RR`.

Những điều cần nhớ:

- Đây là **factory method tạo Collector**, không phải intermediate operation mới của Stream.
- Lambda `finisher` hoạt động trên **kết quả của downstream**; nó không được gọi cho mỗi phần tử đầu vào.
- Đối với một lần `collect` hoàn tất thành một kết quả duy nhất, finisher bên ngoài được áp dụng lên kết quả đã giảm gộp. Khi collector này làm downstream của `groupingBy`, finisher được áp dụng cho kết quả **của mỗi nhóm được tạo**.
- `collectingAndThen` trả về collector **không có đặc tính `IDENTITY_FINISH`**; những characteristics hợp lệ khác được kế thừa từ downstream.
- `finisher` phải chấp nhận trạng thái đầu ra hợp lệ của downstream, gồm cả đầu ra rỗng nếu nguồn/nhóm có thể rỗng.

### 2.1. Không nhầm finisher với map

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(1, 2, 3);

List<Integer> doubled = values.stream()
        .map(n -> n * 2)
        .collect(Collectors.toList());

int count = values.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::size
        ));

System.out.println(doubled); // [2, 4, 6]
System.out.println(count);   // 3
~~~

`map` chạy theo **từng phần tử**, còn `List::size` chỉ nhận **một danh sách đã được thu thập**. Nếu mục tiêu chỉ là đếm phần tử, `stream.count()` hoặc `Collectors.counting()` ngắn và không cần giữ toàn bộ list; ví dụ này chủ yếu để thấy vị trí của finisher.

## 3. Ví dụ nền tảng: biến danh sách kết quả thành snapshot không thể sửa

Giả sử ứng dụng nhận danh sách tên, chuẩn hóa và muốn công bố kết quả chỉ đọc:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of(" An ", " Bình ", " Chi ");

List<String> result = names.stream()
        .map(String::strip)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(result); // [An, Bình, Chi]

// result.add("Dũng"); // Ném UnsupportedOperationException khi chạy.
~~~

`Collectors.toList()` không bảo đảm danh sách kết quả có thể hay không thể sửa, hoặc chính xác là kiểu cài đặt gì. `List.copyOf` tạo một List không thể thay đổi **cấu trúc** theo hợp đồng và **không chấp nhận phần tử null**.

Với dữ liệu có thể chứa null, bước hoàn thiện có thể ném `NullPointerException`; phải có chính sách xác thực hoặc loại bỏ null từ trước, không nên giả định collector này tự xử lý giá trị thiếu.

### 3.1. So với Collectors.toUnmodifiableList và Stream.toList

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("a", "b", "c");

List<String> a = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

List<String> b = source.stream()
        .collect(Collectors.toUnmodifiableList());

List<String> c = source.stream()
        .toList();
~~~

Cả ba kết quả trong ví dụ đều không cho thêm, xóa hoặc thay phần tử qua API List. Tuy nhiên:

| Cách viết | Phiên bản | Khi thích hợp |
|---|---|---|
| `collectingAndThen(toList(), List::copyOf)` | Java 10+ | Cần cấu trúc hoàn thiện tùy chỉnh, hoặc làm downstream trong collector nhiều tầng |
| `Collectors.toUnmodifiableList()` | Java 10+ | Chỉ muốn thu thập thành list không cho sửa; từ chối null |
| `Stream.toList()` | Java 16+ | Terminal operation đơn giản tạo list không cho sửa; không thay thế một downstream `Collector` khi phải lồng collector |

Đối với tác vụ chỉ cần một danh sách bất biến cấu trúc, `toUnmodifiableList` hay `Stream.toList` thường ngắn hơn. `collectingAndThen` có lợi khi cần **bước hoàn thiện không được collector chuẩn trực tiếp diễn đạt**, hoặc **một danh sách được hoàn thiện trong mỗi nhóm**.

### 3.2. Bất biến cấu trúc không phải deep immutability

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

final class Note {
    String title;
    Note(String title) { this.title = title; }
}

Note original = new Note("Bản nháp");

List<Note> notes = List.of(original).stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

original.title = "Đã sửa";

System.out.println(notes.get(0).title); // Đã sửa
~~~

`List.copyOf` không sao chép sâu từng `Note`; nó giữ tham chiếu đến đối tượng. Nếu cần snapshot bất biến **cả dữ liệu bên trong**, chuyển các đối tượng mutable thành DTO/`record` bất biến trước khi thu thập hoặc sao chép phòng vệ phù hợp.

## 4. Sắp xếp hoặc chuẩn hóa kết quả trong finisher

Một finisher có thể tạo kiểu đầu ra khác, sắp xếp danh sách hoặc diễn đạt bước hậu xử lý chỉ chạy khi downstream đã hoàn tất.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = List.of("chi", "an", "binh");

List<String> sorted = values.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> {
                    ArrayList<String> copy = new ArrayList<>(list);
                    copy.sort(Comparator.naturalOrder());
                    return List.copyOf(copy);
                }
        ));

System.out.println(sorted); // [an, binh, chi]
~~~

Ở đây:

1. `toList()` thu thập các phần tử.
2. Finisher nhận danh sách kết quả.
3. Tạo một bản sao để thể hiện rõ quyền sở hữu dữ liệu.
4. Sắp xếp bản sao.
5. Trả danh sách không cho sửa.

**Có cách ngắn hơn cho bài toán toàn cục:**

~~~java
List<String> sorted = values.stream()
        .sorted()
        .toList();
~~~

Cách sử dụng `collectingAndThen` đáng giá hơn khi sắp xếp **riêng danh sách của từng nhóm** hoặc khi finisher thực hiện bước chuẩn hóa đặc thù.

### 4.1. Không yêu cầu finisher phải sửa trực tiếp downstream result

~~~java
list -> {
    list.sort(Comparator.naturalOrder()); // Có thể được nếu list mutable.
    return List.copyOf(list);
}
~~~

Mẫu trên phù hợp nếu biết chắc downstream tạo list có thể sửa; tuy nhiên viết một finisher **không phụ thuộc vào khả năng sửa** của kết quả sẽ dễ tái sử dụng hơn. Ví dụ dùng `list.stream().sorted().toList()` khi chạy Java 16+.

Một finisher có side effect lên collection được chia sẻ ngoài pipeline thường không cần thiết. Ưu tiên trả **một giá trị mới** và giữ logic hoàn thiện tường minh.

## 5. Optional từ maxBy/minBy: đưa ra chính sách khi không có dữ liệu

`Collectors.maxBy(comparator)` trả `Optional<T>` vì một nhóm dữ liệu có thể rỗng. `collectingAndThen` cho phép quyết định trực tiếp kiểu kết quả cuối:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

record Product(String code, int price) {}

List<Product> products = List.of(
        new Product("PEN", 15),
        new Product("BOOK", 45),
        new Product("BAG", 120)
);

Product mostExpensive = products.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Comparator.comparingInt(Product::price)),
                optional -> optional.orElseThrow(
                        () -> new IllegalStateException("Danh sách rỗng")
                )
        ));

System.out.println(mostExpensive.code()); // BAG
~~~

Tại đây:

- Downstream `maxBy` tạo `Optional<Product>`.
- Finisher chuyển `Optional<Product>` thành `Product` hoặc ném lỗi đã định.
- Biểu thức `optional.orElseThrow()` chỉ phù hợp nếu hợp đồng đầu ra **bắt buộc có phần tử**.

Đối với một Stream đơn thuần, `products.stream().max(comparator)` có thể rõ hơn. Cách kết hợp với `collectingAndThen` phát huy tác dụng khi nó nằm **trong `groupingBy`** để lấy một đại diện tốt nhất của mỗi nhóm.

### 5.1. Có thể giữ Optional thay vì ép phải có giá trị

~~~java
import java.util.Optional;

Optional<Product> max = products.stream()
        .collect(Collectors.maxBy(
                Comparator.comparingInt(Product::price)
        ));
~~~

Nếu nghiệp vụ cho phép nguồn rỗng, trả `Optional<Product>` thường trung thực hơn việc ném lỗi hoặc chọn một sản phẩm “mặc định” không có thật. `collectingAndThen` không buộc phải unwrap Optional; nó chỉ tạo chỗ để làm việc ấy **khi đúng yêu cầu**.

## 6. groupingBy + collectingAndThen: hoàn thiện từng nhóm

Giả sử đơn hàng có nhóm danh mục. Muốn trả `Map<String, List<Order>>` sao cho **danh sách từng danh mục** không thể thay đổi cấu trúc.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String id, String category, long amount) {}

List<Order> orders = List.of(
        new Order("O-01", "BOOK", 100),
        new Order("O-02", "PEN", 30),
        new Order("O-03", "BOOK", 200),
        new Order("O-04", "PEN", 70)
);

Map<String, List<Order>> byCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));

System.out.println(byCategory.get("BOOK").size()); // 2
// byCategory.get("BOOK").add(...); // UnsupportedOperationException.
~~~

Nhìn vào cấu trúc:

~~~text
orders.stream()
   |
   v
groupingBy(Order::category,
     collectingAndThen(
         toList(),       -- tạo danh sách cho từng khóa
         List::copyOf    -- hoàn thiện mỗi danh sách
     )
   )
   |
   v
{
  "BOOK": immutableList[O-01, O-03],
  "PEN" : immutableList[O-02, O-04]
}
~~~

**Ranh giới quan trọng:** `List.copyOf` được gọi cho **mỗi giá trị nhóm** đã thu thập, không phải cho từng `Order`. Điều này cũng **không tự làm Map ngoài cùng không thể sửa**. Người gọi vẫn có thể thêm một khóa mới vào một Map mutable nếu Map được cung cấp có hỗ trợ; API `groupingBy` không bảo đảm đặc tính Map cụ thể.

### 6.1. Sắp xếp từng nhóm trước khi công bố

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> byAmountDesc = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(
                                        Comparator
                                                .comparingLong(Order::amount)
                                                .reversed()
                                                .thenComparing(Order::id)
                                )
                                .toList()
                )
        ));

System.out.println(byAmountDesc.get("BOOK")
        .stream().map(Order::id).toList()); // [O-03, O-01]
~~~

Với các bản ghi cùng `amount`, `thenComparing(Order::id)` xác định thứ tự ổn định theo mã đơn. `Stream.toList()` trong finisher trả list không cho sửa cấu trúc.

Lưu ý cách viết này phải giữ toàn bộ phần tử nhóm trước khi sắp xếp; nếu chỉ cần đơn hàng có giá trị lớn nhất của mỗi nhóm, dùng `maxBy` thay vì giữ cả list.

## 7. Hai lớp collectingAndThen: khóa Map và danh sách nhóm đều được bảo vệ

Nếu API muốn công bố **cả Map lẫn mọi List bên trong** dưới dạng cấu trúc không cho sửa, có thể hoàn thiện ở hai tầng:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> immutableIndex = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ),
                Map::copyOf
        ));

// immutableIndex.put("OTHER", List.of()); // UnsupportedOperationException.
// immutableIndex.get("BOOK").add(...);     // UnsupportedOperationException.
~~~

Diễn giải từ trong ra ngoài:

1. Mỗi đơn hàng được phân loại theo `category`.
2. Downstream `toList` xây một list cho mỗi category.
3. Finisher **bên trong** `List.copyOf` bảo vệ cấu trúc của từng list.
4. `groupingBy` tạo `Map<String, List<Order>>`.
5. Finisher **bên ngoài** `Map.copyOf` bảo vệ cấu trúc của Map.

~~~text
Stream<Order>
   |
   v
groupingBy(category)
   ├─ BOOK -> toList() -> List.copyOf(...)
   └─ PEN  -> toList() -> List.copyOf(...)
   |
   v
Map<String, List<Order>>
   |
   v
Map.copyOf(...)
   |
   v
Map không cho sửa + các List giá trị không cho sửa
~~~

`Map.copyOf` không sao chép sâu phần tử `Order`. Trong ví dụ, `Order` là record chỉ chứa `String` và `long` nên trạng thái trường được dùng có tính ổn định; với object mutable làm giá trị, phải thiết kế snapshot sâu riêng.

**Điểm khác biệt:** đặt `collectingAndThen` **chỉ ở bên ngoài** `groupingBy` và gọi `Map.copyOf` sẽ **không** làm các list bên trong trở thành không thể sửa. Đó là lý do phải phân biệt “hoàn thiện mỗi nhóm” và “hoàn thiện toàn bộ kết quả”.

## 8. groupingBy + maxBy + collectingAndThen: một đại diện cho mỗi nhóm

Yêu cầu: lấy **đơn hàng lớn nhất của từng danh mục**, trả thẳng `Order` thay vì `Optional<Order>` trong Map.

~~~java
import java.util.Comparator;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Order> largestByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.maxBy(
                                Comparator.comparingLong(Order::amount)
                                        .thenComparing(Order::id)
                        ),
                        optional -> optional.orElseThrow(
                                () -> new IllegalStateException("Nhóm trống")
                        )
                )
        ));

System.out.println(largestByCategory.get("BOOK").id()); // O-03
System.out.println(largestByCategory.get("PEN").id());  // O-04
~~~

Đối với `groupingBy` thông thường, mỗi khóa trong Map được tạo từ ít nhất một phần tử nguồn, nên `maxBy` cho nhóm ấy có giá trị nếu nguồn hợp lệ và không làm mất phần tử. Tuy nhiên finisher vẫn phải có chính sách rõ ràng với `Optional.empty()`, để collector có thể hiểu và kiểm thử độc lập.

Khi **toàn bộ Stream rỗng**, `groupingBy` trả Map rỗng, **không** tạo ra một khóa giả rồi gọi finisher của nhóm đó. Đừng nhầm trường hợp này với `partitioningBy`, vốn thiết lập cả hai khóa Boolean.

### 8.1. Khi yêu cầu thứ tự ưu tiên phải rõ

Với nhiều đơn hàng có cùng số tiền, comparator chỉ xét `amount` có thể chọn một phần tử trong số các giá trị đồng hạng mà không diễn đạt tie-break nghiệp vụ. Dùng `thenComparing(Order::id)` khi ID là tiêu chí phù hợp, hoặc nêu chính sách xung đột rõ ràng.

Nếu giá trị tiền vượt giới hạn `long`, phải chọn kiểu dữ liệu và comparator phù hợp; finisher không sửa được một kết quả tổng hợp đã bị tràn trong các bước trước.

## 9. mapping và collectingAndThen: chuyển kiểu rồi hoàn thiện một nhóm

Giả sử API cần chỉ mục `Map<String, List<String>>` gồm **mã đơn hàng** theo danh mục thay vì giữ toàn bộ `Order`.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> idsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Order::id,
                                Collectors.toList()
                        ),
                        List::copyOf
                )
        ));

System.out.println(idsByCategory.get("BOOK")); // [O-01, O-03]
~~~

Dòng xử lý:

~~~text
Order -> group(category)
            |
            v
        mapping(Order::id)
            |
            v
         toList()
            |
            v
        List.copyOf()
            |
            v
       List<String> của từng nhóm
~~~

`mapping` biến đổi **phần tử đi vào downstream**; `collectingAndThen` hoàn thiện **kết quả downstream**. Phối hợp chúng là một cấu trúc phổ biến trong collector nhiều tầng.

### 9.1. Sắp thứ tự mã trong mỗi nhóm

~~~java
Map<String, List<String>> sortedIds = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.mapping(Order::id, Collectors.toList()),
                        ids -> ids.stream().sorted().toList()
                )
        ));

System.out.println(sortedIds.get("BOOK")); // [O-01, O-03]
~~~

Với `List<String>`, `String::compareTo` xác định thứ tự tự nhiên. Nếu muốn sắp theo `amount` của `Order` rồi chỉ giữ ID, nên sắp `Order` trước khi biến thành String, hoặc chọn một downstream phù hợp hơn; khi đã mất thông tin amount, finisher không thể khôi phục nó một cách tự nhiên.

## 10. filtering/flatMapping trong downstream: không nhầm nhóm rỗng với khóa vắng mặt

`Collectors.filtering` (Java 9+) lọc **phần tử của downstream**, khác với `stream.filter` trước `groupingBy` ở chỗ nhóm có thể vẫn tồn tại dù tất cả phần tử của nó bị downstream bỏ.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Ticket(String id, String team, boolean resolved) {}

List<Ticket> tickets = List.of(
        new Ticket("T-01", "CORE", false),
        new Ticket("T-02", "CORE", true),
        new Ticket("T-03", "UI", true)
);

Map<String, List<String>> unresolvedIds = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.collectingAndThen(
                        Collectors.filtering(
                                ticket -> !ticket.resolved(),
                                Collectors.mapping(
                                        Ticket::id,
                                        Collectors.toList()
                                )
                        ),
                        List::copyOf
                )
        ));

System.out.println(unresolvedIds.get("CORE")); // [T-01]
System.out.println(unresolvedIds.get("UI"));   // []
~~~

Nhóm `"UI"` **có trong Map** vì có ticket của đội UI đi vào `groupingBy`; downstream `filtering` chỉ bỏ giá trị khỏi list của nhóm ấy.

Nếu lọc **trước** khi nhóm:

~~~java
Map<String, List<String>> onlyUnresolvedGroups = tickets.stream()
        .filter(ticket -> !ticket.resolved())
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.mapping(Ticket::id, Collectors.toList())
        ));

System.out.println(onlyUnresolvedGroups.containsKey("UI")); // false
~~~

Đó là **hai hợp đồng dữ liệu khác nhau**. Khi hoàn thiện kết quả bằng `List.copyOf`, danh sách rỗng vẫn là một kết quả hợp lệ nếu chính sách nghiệp vụ cho phép nhóm rỗng.

### 10.1. flatMapping + collectingAndThen

Khi mỗi đơn hàng có nhiều mã sản phẩm, `flatMapping` (Java 9+) cho phép phát nhiều giá trị vào downstream của từng nhóm.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Basket(String owner, List<String> productCodes) {}

List<Basket> baskets = List.of(
        new Basket("An", List.of("PEN", "BOOK")),
        new Basket("An", List.of("BAG")),
        new Basket("Bình", List.of("BOOK"))
);

Map<String, List<String>> codesByOwner = baskets.stream()
        .collect(Collectors.groupingBy(
                Basket::owner,
                Collectors.collectingAndThen(
                        Collectors.flatMapping(
                                basket -> basket.productCodes().stream(),
                                Collectors.toList()
                        ),
                        List::copyOf
                )
        ));

System.out.println(codesByOwner.get("An")); // [PEN, BOOK, BAG]
~~~

`flatMapping` đóng mỗi Stream con do mapper trả về theo hợp đồng. Finisher `List.copyOf` chỉ chạy trên danh sách đã thu thập xong; nó **không** tham gia đọc nguồn con hoặc quản lý tài nguyên của từng Stream con.

Nếu danh sách mã có thể chứa null, `List.copyOf` sẽ từ chối kết quả; cần chọn chính sách null ngay ở bước nhập hoặc biến đổi phần tử.

## 11. partitioningBy + collectingAndThen: hoàn thiện cả hai nhánh Boolean

`partitioningBy` tạo kết quả theo hai khóa `true` và `false`. Ví dụ tách ticket đã xử lý và chưa xử lý:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Ticket>> partitioned = tickets.stream()
        .collect(Collectors.partitioningBy(
                Ticket::resolved,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));

System.out.println(partitioned.get(true).size());  // 2
System.out.println(partitioned.get(false).size()); // 1
~~~

Đặc điểm:

- `true` biểu diễn nhóm `resolved`.
- `false` biểu diễn nhóm chưa `resolved`.
- Downstream collector được hoàn thiện **riêng cho từng nhánh**.
- Khác `groupingBy`, kết quả của `partitioningBy` có cả **hai khóa Boolean**, kể cả khi một nhánh không có phần tử.

### 11.1. Khi Stream rỗng

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Ticket>> emptyPartitions =
        List.<Ticket>of().stream()
                .collect(Collectors.partitioningBy(
                        Ticket::resolved,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ));

System.out.println(emptyPartitions.get(true));  // []
System.out.println(emptyPartitions.get(false)); // []
~~~

Điều đó giải thích vì sao finisher của downstream **phải xử lý được danh sách rỗng** khi dùng trong `partitioningBy`. Không nên đặt `list.get(0)` trong finisher mà không có nhánh xử lý rỗng.

## 12. Biến IntSummaryStatistics thành record kết quả

`Collectors.summarizingInt` thu thập số lượng, tổng, giá trị min/max và trung bình vào một `IntSummaryStatistics` mutable. Nếu chỉ muốn xuất ra một đối tượng thống kê bất biến theo giao diện nghiệp vụ, `collectingAndThen` giúp chuyển kiểu.

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.Collectors;

record Stats(
        long count,
        long total,
        OptionalInt min,
        OptionalInt max,
        OptionalDouble average
) {}

List<Integer> scores = List.of(5, 10, 8, 7);

Stats stats = scores.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.summarizingInt(Integer::intValue),
                s -> new Stats(
                        s.getCount(),
                        s.getSum(),
                        s.getCount() == 0
                                ? OptionalInt.empty()
                                : OptionalInt.of(s.getMin()),
                        s.getCount() == 0
                                ? OptionalInt.empty()
                                : OptionalInt.of(s.getMax()),
                        s.getCount() == 0
                                ? OptionalDouble.empty()
                                : OptionalDouble.of(s.getAverage())
                )
        ));

System.out.println(stats.count());               // 4
System.out.println(stats.total());               // 30
System.out.println(stats.average().orElseThrow()); // 7.5
~~~

Điểm cần phân biệt:

- Downstream tính toán thống kê bằng các thao tác tích lũy và gộp riêng của nó.
- Finisher **không** phải tính lại từ toàn bộ list; nó chỉ đọc thống kê sau thu thập.
- Khi nguồn rỗng, `getMin()`/`getMax()` của `IntSummaryStatistics` chứa giá trị sentinel của kiểu nguyên thủy; ví dụ trên chuyển chúng thành `OptionalInt.empty()` thay vì công bố min/max không có thật.
- `getAverage()` dùng `double`; nếu nghiệp vụ yêu cầu trung bình thập phân chính xác, cần một thuật toán cộng/đếm và làm tròn phù hợp thay cho việc chỉ bọc `IntSummaryStatistics`.
- Tổng của `summarizingInt` dùng kiểu `long`, **vẫn có thể tràn** với khối dữ liệu vượt miền `long`. Finisher không sửa được một tổng đã sai.

### 12.1. Thống kê theo nhóm

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Stats> statsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(
                                order -> Math.toIntExact(order.amount())
                        ),
                        s -> new Stats(
                                s.getCount(),
                                s.getSum(),
                                s.getCount() == 0
                                        ? OptionalInt.empty()
                                        : OptionalInt.of(s.getMin()),
                                s.getCount() == 0
                                        ? OptionalInt.empty()
                                        : OptionalInt.of(s.getMax()),
                                s.getCount() == 0
                                        ? OptionalDouble.empty()
                                        : OptionalDouble.of(s.getAverage())
                        )
                )
        ));
~~~

Ở đây `Order.amount()` trong ví dụ là `long` và được chuyển bằng `Math.toIntExact`; nếu dữ liệu có thể vượt phạm vi `int`, phép chuyển sẽ ném `ArithmeticException`. Đây **chỉ** là minh họa kết nối với `summarizingInt`; trong hệ thống thật, có thể chọn `summarizingLong(Order::amount)` hoặc accumulator `BigInteger` để phù hợp miền dữ liệu hơn.

Đừng dùng `(int) order.amount()` một cách âm thầm khi giá trị có nguy cơ vượt miền `int`.

## 13. Dùng collectingAndThen để kiểm tra ràng buộc trên kết quả cuối

Không phải finisher nào cũng chuyển sang collection bất biến. Nó có thể thực hiện **validation** trên kết quả đã tổng hợp.

Ví dụ một batch đơn hàng **bắt buộc có ít nhất một đơn** và tổng cent phải không âm:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Sale(long cents) {}
record SaleSummary(long count, BigInteger total) {}

Collector<Sale, ?, SaleSummary> validatedSummary =
        Collectors.collectingAndThen(
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.mapping(
                                sale -> BigInteger.valueOf(sale.cents()),
                                Collectors.reducing(
                                        BigInteger.ZERO,
                                        BigInteger::add
                                )
                        ),
                        SaleSummary::new
                ),
                summary -> {
                    if (summary.count() == 0) {
                        throw new IllegalStateException("Batch rỗng");
                    }
                    if (summary.total().signum() < 0) {
                        throw new IllegalStateException("Tổng tiền âm");
                    }
                    return summary;
                }
        );

List<Sale> sales = List.of(new Sale(100), new Sale(-20));
SaleSummary result = sales.parallelStream().collect(validatedSummary);

System.out.println(result); // SaleSummary[count=2, total=80]
~~~

`Collectors.teeing` (Java 12+) chạy **hai collector downstream** song song trên cùng luồng phần tử: một nhánh đếm, một nhánh cộng BigInteger; sau đó dùng merger tạo `SaleSummary`. `collectingAndThen` tiếp tục **xác thực toàn bộ summary**.

Mặc dù tên `teeing` là “chia hai nhánh”, không có nghĩa mỗi nhánh nhất thiết chạy trên hai thread độc lập; nó mô tả cấu trúc thu thập, không bảo đảm kế hoạch thực thi vật lý.

**Khi nào không cần collectingAndThen?** Nếu logic kiểm tra và chuẩn hóa đầu ra đã đặt gọn trong merger của `teeing` hoặc finisher của collector tùy chỉnh, việc bọc thêm có thể không cần thiết. Chọn cách giúp hợp đồng rõ nhất.

## 14. Finisher không phải một thao tác có thể sửa sai phép tích lũy

Một Collector hợp lệ khi xử lý song song vẫn cần:

- `supplier` tạo trạng thái rỗng đúng.
- `accumulator` thêm phần tử theo hợp đồng.
- `combiner` ghép hai trạng thái đúng **identity** và **associativity**.
- `finisher` chuyển trạng thái đã hoàn tất thành kết quả cuối theo hợp đồng.

`collectingAndThen` chỉ thay/chồng bước cuối. Nó **không làm một combiner sai trở thành đúng**.

~~~text
Phân vùng A -> accumulator(A) ---\
                                   combiner() -> trạng thái tổng
Phân vùng B -> accumulator(B) ---/                  |
                                                      v
                                        downstream.finisher()
                                                      |
                                                      v
                                         finisher thêm của
                                         collectingAndThen
                                                      |
                                                      v
                                                kết quả công bố
~~~

Ví dụ lỗi kinh điển: mỗi phân vùng tạo một mức trung bình, combiner lấy trung bình của hai mức trung bình mà không xét kích thước từng nhóm. Sau đó finisher có định dạng đẹp đến đâu thì kết quả vẫn sai nếu hai phân vùng có số phần tử khác nhau.

Cách đúng: giữ `sum` và `count` trong trạng thái, combiner cộng hai trường, cuối cùng finisher mới chia theo quy tắc số học đã chọn.

### 14.1. Làm tròn sau khi gộp, không làm tròn trong mỗi lần ghép

Với tiền tệ hoặc thập phân, nếu nghiệp vụ yêu cầu **tổng các số thập phân chính xác rồi làm tròn một lần**, có thể chọn downstream dùng `BigDecimal::add` không có `MathContext` rồi dùng finisher `setScale`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.Collectors;

List<BigDecimal> amounts = List.of(
        new BigDecimal("1.235"),
        new BigDecimal("2.235"),
        new BigDecimal("3.235")
);

BigDecimal roundedTotal = amounts.parallelStream()
        .collect(Collectors.collectingAndThen(
                Collectors.reducing(
                        BigDecimal.ZERO,
                        BigDecimal::add
                ),
                total -> total.setScale(2, RoundingMode.HALF_UP)
        ));

System.out.println(roundedTotal); // 6.71
~~~

Vì `1.235 + 2.235 + 3.235 = 6.705` nên làm tròn `HALF_UP` tới hai chữ số thành `6.71`. Nếu quy tắc nghiệp vụ yêu cầu **làm tròn mỗi giao dịch trước khi cộng**, kết quả có thể khác; phải xác định quy tắc trước khi chọn collector.

Finisher là chỗ tự nhiên cho *làm tròn cuối*, nhưng không nên dùng nó để che lấp overflow đã xảy ra trong accumulator hoặc các lỗi độ chính xác do dùng `double` không phù hợp.

## 15. Characteristics: vì sao IDENTITY_FINISH bị loại bỏ?

Hợp đồng `Collector.Characteristics.IDENTITY_FINISH` cho phép framework bỏ qua bước finisher vì chuyển trạng thái tích lũy thành kết quả được coi là đồng nhất theo kiểu và hành vi. `collectingAndThen` thêm một bước hoàn thiện thực sự nên **loại bỏ `IDENTITY_FINISH`**.

~~~java
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> ordinary =
        Collectors.toList();

Collector<String, ?, List<String>> finished =
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        );

System.out.println(
        ordinary.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
);

System.out.println(
        finished.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
); // false
~~~

Bản in đầu có thể là `true` đối với `Collectors.toList()` theo cấu hình thông thường, nhưng điều quan trọng cần kiểm tra về `collectingAndThen` là **kết quả không còn `IDENTITY_FINISH`**. Đừng gắn cờ ấy thủ công cho collector thật sự cần chạy `List.copyOf`, chuẩn hóa thống kê hoặc validation: framework có thể bỏ qua bước cuối mà ứng dụng cần.

Những đặc tính khác như `CONCURRENT` và `UNORDERED` (khi downstream có và vẫn hợp lệ) được kế thừa. Nhưng việc **collector cho phép** tích lũy đồng thời không nói rằng finisher phải tự chạy trên từng phần tử hoặc rằng mỗi lần xử lý đều sử dụng đúng một lịch trình thread.

### 15.1. Có được dùng trên parallelStream không?

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> parallelGroups = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));
~~~

Với downstream collector chuẩn có hợp đồng phù hợp, Stream có thể tạo nhiều container riêng rồi ghép trước khi hoàn thiện các nhóm. Finisher thấy kết quả **đã gộp**, không chỉ một phân vùng riêng lẻ.

Tuy nhiên:

- Phải bảo đảm các lambda lấy khóa, biến đổi dữ liệu và collector tùy chỉnh là **non-interfering/stateless** theo hợp đồng.
- Không lấy hiệu năng song song làm mặc định; nhóm nhỏ và ít phần tử có thể chậm hơn vì chi phí gộp.
- Nếu sắp thứ tự nhóm trong finisher, chi phí sắp xếp có thể đáng kể.
- Nên kiểm tra kết quả tuần tự và song song theo **hợp đồng dữ liệu**, không so thứ tự duyệt của `HashMap` nếu thứ tự không được bảo đảm.

## 16. Thứ tự, null và độ bất biến: ba giới hạn dễ bị hiểu sai

### 16.1. collectingAndThen không tự sắp xếp

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = List.of(3, 1, 2);

List<Integer> result = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(result); // [3, 1, 2]
~~~

`List.copyOf` không tự xếp lại phần tử; nó giữ thứ tự duyệt danh sách truyền vào. Nếu cần `[1, 2, 3]`, phải sắp xếp trước hoặc trong finisher. Với downstream collector không bảo đảm thứ tự, `collectingAndThen` không tự tạo ra bảo đảm mới.

### 16.2. collectingAndThen không tự loại bỏ null

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = new ArrayList<>(
        Arrays.asList("A", null, "B")
);

// Ném NullPointerException khi finisher List.copyOf gặp null:
// List<String> result = source.stream()
//         .collect(Collectors.collectingAndThen(
//                 Collectors.toList(), List::copyOf
//         ));
~~~

Nếu nghiệp vụ cho phép bỏ giá trị null, lọc trước:

~~~java
import java.util.Objects;

List<String> cleaned = source.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(cleaned); // [A, B]
~~~

Nếu null là lỗi dữ liệu, nên báo lỗi thay vì lặng lẽ bỏ qua phần tử. `collectingAndThen` không đặt ra chính sách null thay cho nghiệp vụ.

### 16.3. Bảo vệ Map ngoài không đồng nghĩa bảo vệ list trong

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> outerOnly = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Order::category),
                Map::copyOf
        ));
~~~

Kết quả Map không cho sửa cấu trúc, nhưng **List ở mỗi nhóm vẫn có thể mutable**. Muốn bảo vệ cả hai tầng, dùng hai `collectingAndThen` như mục 7.

### 16.4. Collections.unmodifiableList là view, List.copyOf là snapshot cấu trúc

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> original = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(original);
List<String> copy = List.copyOf(original);

original.add("B");

System.out.println(view); // [A, B]
System.out.println(copy); // [A]
~~~

`unmodifiableList` ngăn thay đổi **qua view**, nhưng nội dung view có thể thay đổi nếu list nguồn vẫn bị sửa từ nơi khác. `List.copyOf` tạo kết quả không thay đổi cấu trúc theo thời gian bởi những sửa đổi của `original`. Cả hai đều có thể vẫn tham chiếu đến **phần tử mutable**.

## 17. Khi nào không nên dùng collectingAndThen?

Không phải mọi thao tác cuối đều cần bọc thêm finisher. Bảng sau giúp chọn giải pháp rõ ràng:

| Mục tiêu | Thường ưu tiên | Khi collectingAndThen có lợi |
|---|---|---|
| Tạo List không cho sửa từ một Stream | `Stream.toList()` (Java 16+) hoặc `toUnmodifiableList` | Khi cần đặt trong downstream của `groupingBy` hoặc thêm logic cuối |
| Tạo Set không cho sửa | `toUnmodifiableSet` | Khi cần thêm validation, chuyển dạng hoặc logic khác |
| Lấy max/min của một Stream | `stream.max/min` | Khi muốn Map khóa → giá trị max/min không bọc Optional |
| Chỉ đếm phần tử | `count()` hoặc `Collectors.counting()` | Khi cần đổi từ count thành DTO/nhãn tại mức nhóm |
| Làm phẳng hoặc biến đổi phần tử | `flatMap`/`map` hoặc `flatMapping`/`mapping` | Khi còn cần hậu xử lý **toàn bộ** danh sách kết quả |
| Nhóm và giữ List bình thường | `groupingBy(classifier)` | Khi phải sắp xếp/đóng băng danh sách nhóm |
| Tổng chính xác | `reduce` hoặc collector số thích hợp | Khi cần validation/rounding **một lần cuối** |
| Phân nhóm theo Boolean | `partitioningBy` | Khi cần chuẩn hóa riêng từng nhánh |
| Tạo DTO từ hai thống kê | `teeing` với merger | Khi validation/chuẩn hóa sau merger là một bước độc lập |

`collectingAndThen` có thể không tốt khi finisher phải duyệt hoặc sao chép một collection khổng lồ trong khi bài toán thực sự chỉ cần một con số đơn giản. Với mục tiêu `count`, việc thu thập một danh sách rồi tính `size` có thể tăng chi phí bộ nhớ từ O(1) cho bộ đếm lên O(n) cho danh sách.

## 18. Hiệu năng và vòng đời tài nguyên

Một số lưu ý khi dùng collector nhiều tầng:

- **Phân bổ bộ nhớ:** `toList` rồi `List.copyOf` có thể phát sinh sao chép mảng/tham chiếu, tùy JDK và kiểu downstream. Đừng mặc định `collectingAndThen` “miễn phí”.
- **Tần suất finisher:** một finisher sau khi thu thập toàn cục khác với finisher cho **mỗi nhóm**. Nếu có hàng trăm nghìn nhóm, chi phí hoàn thiện từng nhóm có thể đáng kể.
- **Không thay thế thuật toán:** nếu chỉ cần min/max, đừng tích lũy cả list rồi `sort` để chọn một phần tử. `maxBy` thích hợp hơn.
- **Short-circuit:** `collect` là terminal operation, thông thường phải xử lý đủ phần tử cần thu thập; `collectingAndThen` không tự thêm khả năng dừng sớm như `findFirst` hay `anyMatch`.
- **Nguồn I/O:** nếu nguồn là `Files.lines`, phải quản lý vòng đời Stream bằng `try-with-resources`. Finisher không tự đóng nguồn I/O.
- **Độ chính xác:** nếu downstream đã tính sai do tràn số hoặc làm tròn sai tại mỗi combiner, việc format hoặc làm tròn lại trong finisher không khôi phục kết quả đúng.

Ví dụ sử dụng `Files.lines` để thu thập các dòng không rỗng thành list snapshot:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Path path = Path.of("application.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> snapshot = lines
            .filter(line -> !line.isBlank())
            .collect(Collectors.collectingAndThen(
                    Collectors.toList(),
                    List::copyOf
            ));

    System.out.println("Số dòng: " + snapshot.size());
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Không đọc được tệp: " + ex.getMessage());
}
~~~

`try-with-resources` quản lý đóng nguồn tệp; `List.copyOf` chỉ hoàn thiện kết quả đã đưa vào bộ nhớ, không chịu trách nhiệm vòng đời của `Files.lines`. Với tệp cực lớn, giữ mọi dòng vào bộ nhớ có thể không phù hợp; khi đó chọn một downstream tổng hợp gọn hơn.

## 19. Kiểm thử collectingAndThen đúng hợp đồng

Khi thiết kế bộ kiểm tra, xác định một **oracle** hoặc kết quả mong đợi cụ thể và thử các chiều sau:

| Ca | Cần xác nhận |
|---|---|
| Stream rỗng | Finisher có xử lý được kết quả downstream rỗng không? |
| Một phần tử | Kiểu và giá trị cuối đúng; không thêm dữ liệu giả |
| Nhiều nhóm | Finisher áp dụng riêng cho từng nhóm |
| Một nhóm không có phần tử sau downstream filtering | Danh sách rỗng hợp lệ hay phải báo lỗi? |
| `partitioningBy` rỗng | Cả `true` và `false` vẫn được hoàn thiện |
| Dữ liệu null | Lọc/báo lỗi theo yêu cầu; `List.copyOf`/`Map.copyOf` từ chối null |
| Bảo vệ Map ngoài | `put` không hợp lệ nếu Map đã được đóng băng |
| Bảo vệ List bên trong | `add` không hợp lệ nếu list nhóm đã được đóng băng |
| Giá trị mutable trong List | Đừng nhầm bất biến cấu trúc với deep copy |
| Sequential vs parallel | So kết quả theo hợp đồng, không dựa vào thứ tự `Map` không được bảo đảm |
| Collector tùy chỉnh | Supplier/accumulator/combiner vẫn giữ identity và associativity |
| Tính đúng số học | Không có overflow, làm tròn đúng thời điểm |

### 19.1. Chương trình kiểm tra nhỏ: bảo vệ cả hai tầng

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class CollectingAndThenCheck {
    record Order(String id, String category) {}

    static Map<String, List<Order>> index(List<Order> orders) {
        return orders.stream()
                .collect(Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Order::category,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        ),
                        Map::copyOf
                ));
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("A", "BOOK"),
                new Order("B", "PEN"),
                new Order("C", "BOOK")
        );

        Map<String, List<Order>> sequential = index(data);
        Map<String, List<Order>> parallel = data.parallelStream()
                .collect(Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Order::category,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        ),
                        Map::copyOf
                ));

        if (!sequential.equals(parallel)) {
            throw new AssertionError("Parallel khác sequential");
        }
        if (sequential.get("BOOK").size() != 2) {
            throw new AssertionError("Sai số lượng BOOK");
        }

        try {
            sequential.put("OTHER", List.of());
            throw new AssertionError("Map vẫn sửa được");
        } catch (UnsupportedOperationException expected) {
            // PASS: Map không cho sửa.
        }

        try {
            sequential.get("BOOK").add(new Order("D", "BOOK"));
            throw new AssertionError("List nhóm vẫn sửa được");
        } catch (UnsupportedOperationException expected) {
            // PASS: List nhóm không cho sửa.
        }

        Map<String, List<Order>> empty = index(List.of());
        if (!empty.isEmpty()) {
            throw new AssertionError("Nguồn rỗng phải cho Map rỗng");
        }

        System.out.println("PASS");
    }
}
~~~

Đây là ví dụ minh họa, **không thay thế một bộ kiểm thử chuyên môn đầy đủ**. Trong thực tế còn cần kiểm tra khóa/giá trị null, thứ tự theo yêu cầu, đối tượng mutable, quy mô dữ liệu lớn và collector downstream có phép tổng hợp phức tạp. Việc test tuần tự và song song giống nhau **không đủ** nếu cả hai cùng dựa trên một accumulator sai; đối chiếu thêm dữ liệu nhỏ có kết quả tính tay và các bất biến thống kê.

### 19.2. Không dùng side effect để đếm số lần finisher chạy

~~~java
// Tránh thiết kế nghiệp vụ kiểu:
// AtomicInteger calls = new AtomicInteger();
// collectingAndThen(toList(), list -> {
//     calls.incrementAndGet(); // Phụ thuộc cấu trúc pipeline sử dụng collector
//     return List.copyOf(list);
// });
~~~

Trong collector đặt lồng nhau, số lần hoàn thiện phụ thuộc vào số kết quả downstream được tạo (chẳng hạn số nhóm). Việc log/metric có thể hữu ích để chẩn đoán, nhưng không nên biến số lần gọi finisher thành dữ liệu nghiệp vụ hoặc dựa vào nó để đồng bộ ngoài pipeline.

## 20. Bài tập tự kiểm tra (có đáp án)

### Bài 1. Finisher nhận gì?

**Đề:** Với `collectingAndThen(toList(), List::copyOf)` trên `Stream<String>`, `List::copyOf` được gọi cho từng String hay cho danh sách?

**Đáp án:** Nó nhận **danh sách đã được downstream thu thập**, không nhận từng String. `toList` thực hiện tích lũy; `List.copyOf` hoàn thiện kết quả List.

### Bài 2. Map ngoài và list nhóm

**Đề:** `collectingAndThen(groupingBy(Order::category), Map::copyOf)` có bảo đảm list trong mỗi nhóm không thể chỉnh sửa không?

**Đáp án:** Không. Nó bảo vệ cấu trúc Map ngoài, nhưng không tự bảo vệ list nhóm. Cần `collectingAndThen(toList(), List::copyOf)` ở downstream bên trong `groupingBy`.

### Bài 3. maxBy và Optional

**Đề:** Vì sao `maxBy` trả `Optional<Order>`? Khi nào nên dùng finisher `orElseThrow`?

**Đáp án:** Nguồn có thể rỗng và không có phần tử tối đa. `orElseThrow` chỉ phù hợp khi **bắt buộc** có kết quả, ví dụ một nhóm đã tồn tại và theo nghiệp vụ không được rỗng; nếu nguồn rỗng là trạng thái bình thường, nên giữ `Optional` hoặc biểu diễn thiếu dữ liệu rõ ràng.

### Bài 4. groupingBy và filtering

**Đề:** Một nhóm `UI` có ticket nhưng tất cả đã resolved. Vì sao `groupingBy(Ticket::team, filtering(notResolved, collectingAndThen(toList(), List::copyOf)))` vẫn có khóa UI?

**Đáp án:** `groupingBy` tạo khóa khi xử lý ticket UI, còn `filtering` downstream bỏ phần tử ra khỏi danh sách **của khóa đã hình thành**. Kết quả nhóm UI là list rỗng, không phải khóa vắng mặt.

### Bài 5. partitioningBy rỗng

**Đề:** Thu thập một Stream rỗng bằng `partitioningBy(predicate, collectingAndThen(toList(), List::copyOf))` có những khóa nào?

**Đáp án:** Có cả `true` và `false`, mỗi khóa tương ứng với list rỗng không cho sửa. Finisher ở nhánh này cần xử lý trường hợp list rỗng.

### Bài 6. Bước làm tròn đặt ở đâu?

**Đề:** Tổng các giá trị `BigDecimal` được phép cộng chính xác rồi làm tròn một lần sau cùng. Finisher có phù hợp không?

**Đáp án:** Có. Dùng downstream `reducing(BigDecimal.ZERO, BigDecimal::add)` không làm tròn trung gian, sau đó finisher `total -> total.setScale(2, RoundingMode.HALF_UP)`. Nếu nghiệp vụ yêu cầu mỗi giao dịch làm tròn riêng, phải làm điều đó trước khi gộp.

### Bài 7. IDENTITY_FINISH

**Đề:** Một collector `toList` được bọc bằng `collectingAndThen(toList(), List::copyOf)` có còn `IDENTITY_FINISH` không?

**Đáp án:** Không. Bước `List.copyOf` là một finisher có ý nghĩa, nên collector kết quả loại bỏ đặc tính `IDENTITY_FINISH`. Nếu framework bỏ qua bước cuối, tính không thể sửa cấu trúc sẽ không được bảo đảm.

### Bài 8. Bất biến nông

**Đề:** Danh sách được tạo bằng `List.copyOf` chứa các đối tượng `Note` mutable. Sửa `Note.title` qua tham chiếu khác có ảnh hưởng phần tử trong danh sách không?

**Đáp án:** Có thể. `List.copyOf` không sao chép sâu giá trị. Danh sách không cho thêm/bớt nhưng vẫn giữ tham chiếu tới Note có thể thay đổi. Cần mô hình DTO bất biến hoặc defensive copy sâu nếu muốn snapshot dữ liệu thật sự ổn định.

### Bài 9. Finisher có sửa được combiner sai?

**Đề:** Downstream collector của phép tính trung bình gộp hai phân vùng bằng cách lấy trung bình của hai trung bình không trọng số. Có thể thêm `collectingAndThen` để đảm bảo đúng không?

**Đáp án:** Không. Khi mất thông tin số phần tử của từng phân vùng, finisher không khôi phục đủ dữ liệu. Sửa accumulator và combiner để giữ/cộng `sum` và `count`; chỉ chia trong finisher cuối.

### Bài 10. Chọn API gọn nhất

**Đề:** Chỉ cần một List không cho sửa từ Stream trên Java 17, không có grouping hoặc hậu xử lý khác. Có nhất thiết dùng `collectingAndThen` không?

**Đáp án:** Không. `stream.toList()` thường gọn hơn. `collectingAndThen` hữu ích khi bước hoàn thiện phải lồng vào downstream collector hoặc chuyển kết quả thành kiểu/hợp đồng khác.

---

**Ghi nhớ:** `Collectors.collectingAndThen(downstream, finisher)` là cách **nối một bước hoàn thiện vào kết quả của collector**, không biến đổi từng phần tử. Đặt nó **bên trong** `groupingBy` để hoàn thiện **mỗi nhóm**, đặt **bên ngoài** để hoàn thiện **toàn bộ Map**, hoặc lồng cả hai khi cần bảo vệ nhiều tầng. Bước hoàn thiện có thể đóng băng cấu trúc, sắp xếp, unwrap `Optional`, tạo DTO thống kê hoặc xác thực kết quả. Nó không sửa được một accumulator/combiner sai, không tự tạo deep copy và không thay thế việc kiểm soát null, tài nguyên, độ chính xác hoặc hiệu năng trong Java Stream API.

