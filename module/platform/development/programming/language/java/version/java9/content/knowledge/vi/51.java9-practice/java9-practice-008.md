# Xử lý dữ liệu bằng collection gọn, Stream và Optional (Java 9+)

## Mục tiêu bài học

Một tác vụ xử lý dữ liệu thường phải kết hợp ba việc: **lưu tập dữ liệu có cấu trúc**, **lọc/biến đổi/tổng hợp dữ liệu**, và **xử lý trường hợp một giá trị có thể không tồn tại**. Từ Java 9, bạn có các công cụ ngắn gọn và vẫn được hỗ trợ trong JDK hiện đại:

- `List.of(...)`, `Set.of(...)`, `Map.of(...)`, `Map.ofEntries(...)`: tạo collection **không cho sửa** trực tiếp, phù hợp dữ liệu đầu vào và cấu hình cố định.
- `Stream.takeWhile(...)`, `dropWhile(...)`, `ofNullable(...)` và `iterate(seed, predicate, next)`: mở rộng cách tạo và xử lý luồng dữ liệu.
- `Optional.stream()`, `Optional.or(...)` và `Optional.ifPresentOrElse(...)`: kết hợp kết quả tùy chọn với pipeline và xử lý nhánh có/không có dữ liệu.

Các API cơ bản như `filter`, `map`, `flatMap`, `collect`, `groupingBy`, `findFirst` và `Optional.ofNullable` có từ trước Java 9 nhưng vẫn là thành phần thiết yếu để phối hợp các tính năng trên. Bài này dùng một ví dụ báo cáo đơn hàng trọn vẹn, **biên dịch được với `javac --release 9`** và chạy tốt trên JDK mới, sau đó chỉ ra các tiện ích xuất hiện ở Java 10/16 để bạn không nhầm phiên bản.

## 1. Từ yêu cầu nghiệp vụ đến pipeline dữ liệu

Giả sử hệ thống nhận danh sách đơn hàng. Mỗi đơn có mã, nhóm sản phẩm, số lượng, đơn giá tính bằng **đơn vị nhỏ nhất của tiền** và mã giảm giá có thể thiếu. Yêu cầu là:

1. Lưu danh sách đơn theo thứ tự nhập, các nhóm hợp lệ, tên hiển thị nhóm và bảng tỷ lệ giảm giá.
2. Tính tổng doanh thu trước và sau giảm giá; tổng hợp doanh thu theo nhóm.
3. Tìm đơn giá trị cao, lọc những mã giảm giá thật sự có mặt.
4. Tìm đơn theo mã; nếu không có thì thử mã dự phòng mà không phải trả về `null`.
5. Phân biệt lọc toàn bộ phần tử phù hợp với lấy/bỏ **đoạn đầu liên tiếp** của một luồng có thứ tự.

```text
List<Order>             Set<String> / Map<...>
    |                           |
    |                      Cấu hình bất biến
    v                           |
   stream() ---------------------+
    |
    +-- filter -> map -> sorted -> collect -> List
    |
    +-- mapToLong -> sum -> tổng số
    |
    +-- groupingBy -> TreeMap -> báo cáo theo nhóm
    |
    +-- Optional<Order> -> map/flatMap/or/ifPresentOrElse
    |
    +-- Optional<String>.stream() / Stream.ofNullable -> mã tùy chọn
```

Với tập dữ liệu nhỏ, danh sách nguồn đọc nhiều lần là bình thường: **mỗi lần gọi `orders.stream()` tạo một luồng mới**. Không thể chạy nhiều terminal operation trên cùng một đối tượng `Stream` đã được tiêu thụ.

## 2. Tạo collection gọn bằng factory methods từ Java 9

### 2.1. List.of, Set.of, Map.of và Map.ofEntries

```java
List<String> teams = List.of("backend", "frontend", "qa");

Set<String> statuses = Set.of("NEW", "PAID", "CANCELLED");

Map<String, Integer> discounts =
        Map.of("WELCOME", 10, "STUDENT", 5);

Map<String, String> labels = Map.ofEntries(
        Map.entry("books", "Books"),
        Map.entry("tools", "Tools"),
        Map.entry("stationery", "Stationery"));
```

Đây là các mảnh Java hợp lệ trong method/class có import `java.util.*`. Từ Java 9, `List.of`, `Set.of`, `Map.of`, `Map.entry` và `Map.ofEntries` đều có mặt trong API chuẩn.

| Factory | Đặc tính | Điều cần kiểm tra |
| --- | --- | --- |
| `List.of(...)` | Có thứ tự theo tham số, cho phép phần tử trùng | Không chấp nhận `null`; không được `add`/`remove`/`set` |
| `Set.of(...)` | Không có phần tử trùng, không cho sửa | Phần tử `null` gây `NullPointerException`; trùng gây `IllegalArgumentException`; thứ tự duyệt không xác định |
| `Map.of(k,v,...)` | Map nhỏ không cho sửa | Tối đa **10 cặp** cho overload `of`; cấm `null`, trùng key gây lỗi |
| `Map.ofEntries(entry...)` | Map không cho sửa với số lượng entry tùy ý | Cấm `null`, trùng key; thứ tự key không xác định |
| `Map.entry(k,v)` | Tạo entry tiện lợi để truyền cho `Map.ofEntries` | Cả key/value đều không được `null` |

Ví dụ về lỗi cần xử lý ở điểm tạo dữ liệu:

```java
List.of("a", (String) null); // NullPointerException
Set.of("a", "a");            // IllegalArgumentException
Map.of("x", 1, "x", 2);     // IllegalArgumentException
```

Ba dòng này là **minh họa từng lỗi**, không phải chương trình có thể chạy liên tiếp mà không xử lý ngoại lệ. Thay vì tìm cách ép factory chấp nhận dữ liệu sai, hãy lọc/chuẩn hóa hoặc báo lỗi đầu vào trước.

### 2.2. Unmodifiable khác deep immutable

Không thể `add`/`remove`/`set` vào collection do `List.of`/`Set.of`/`Map.of` tạo. Nhưng nếu bản thân phần tử là **đối tượng có thể thay đổi**, nội dung quan sát vẫn có thể đổi:

```java
StringBuilder name = new StringBuilder("A");
List<StringBuilder> list = List.of(name);

name.append("B");
System.out.println(list.get(0)); // AB
```

Đây là khác biệt giữa collection **unmodifiable** và toàn bộ đồ thị đối tượng **deeply immutable**. Trong ví dụ đơn hàng bên dưới, các trường của `Order` đều `final`, kiểu nguyên thủy hoặc `String`; đây là cách hợp lý để dữ liệu nguồn không bị thay đổi bất ngờ.

`Collections.unmodifiableList(existingList)` tạo một **view** không cho sửa qua reference đó, nhưng khi `existingList` vẫn được chỉnh bằng reference gốc, view phản ánh thay đổi. `List.of(...)` không phải unmodifiable view của một `ArrayList` bên ngoài.

### 2.3. Thứ tự của List và Map/Set

`List.of` giữ thứ tự đối số, thuận tiện cho `findFirst`, `takeWhile` và `dropWhile`. `Set.of` và `Map.of` **không cam kết thứ tự duyệt**; không dựa vào `toString()` hay `forEach()` của chúng để tạo báo cáo có thứ tự ổn định.

Nếu cần một kết quả sắp xếp theo khóa để in, dùng `TreeMap` hoặc một bước `sorted` có comparator rõ ràng:

```java
Map<String, Integer> rates =
        Map.of("WELCOME", 10, "STUDENT", 5);

Map<String, Integer> sortedRates = new TreeMap<>(rates);
// sortedRates in theo thứ tự khóa: STUDENT trước WELCOME
```

Điều quan trọng là tạo **thứ tự hiển thị ở nơi sử dụng**, không dự đoán thứ tự cài đặt của factory.

## 3. Stream là pipeline xử lý, không phải một collection mới

`Collection.stream()` tạo một `Stream`. Các intermediate operation như `filter`, `map`, `flatMap`, `distinct` và `sorted` thường thực hiện **lười (lazy)**: pipeline được thực thi khi có terminal operation như `collect`, `sum`, `count`, `forEach` hoặc `findFirst`.

```java
List<String> ids = orders.stream()
        .filter(o -> o.grossCents() >= 10_000)
        .map(o -> o.id)
        .sorted()
        .collect(Collectors.toList());
```

Đây là mảnh mã dùng lớp `Order` và biến `orders` ở chương trình hoàn chỉnh. Các bước:

- `filter` loại đơn không thỏa điều kiện.
- `map` chuyển mỗi `Order` thành chuỗi mã đơn.
- `sorted` đưa mã về thứ tự từ điển.
- `collect(Collectors.toList())` lấy kết quả thành `List`.

Lưu ý `Collectors.toList()` **không cam kết** loại implementation hay khả năng sửa danh sách kết quả. Nếu thực sự cần mutable `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. Nếu cần danh sách không cho sửa trong JDK hiện đại, xem mục 9 để chọn API đúng phiên bản.

### 3.1. Stream chuyên biệt cho số

Thay vì chuyển từng `long` thành `Long` rồi tự cộng, dùng `mapToLong`:

```java
long revenue = orders.stream()
        .mapToLong(Order::grossCents)
        .sum();
```

`mapToLong` tạo `LongStream` để tránh boxing không cần thiết trong pipeline tính tổng. Khi tính tiền, ví dụ dùng **số nguyên đơn vị nhỏ nhất** thay vì `double` để tránh lỗi biểu diễn nhị phân của số thập phân. Trong ứng dụng thực, quy tắc làm tròn/thuế/chiết khấu phải được định nghĩa rõ; `Math.multiplyExact` có thể giúp phát hiện overflow ở phép nhân.

### 3.2. Nhóm và tổng hợp

```java
Map<String, Long> byCategory = orders.stream()
        .collect(Collectors.groupingBy(
                o -> o.category,
                Collectors.summingLong(Order::grossCents)));
```

`groupingBy` gom theo giá trị khóa mà bạn trích ra, còn `summingLong` cộng trong từng nhóm. **Không giả định thứ tự key** của kết quả collector. Nếu cần thứ tự, có thể chuyển sang `new TreeMap<>(byCategory)` hoặc dùng overload `groupingBy(classifier, TreeMap::new, downstream)`.

Với collection đã chứa tất cả dữ liệu và cần nhiều báo cáo, tạo một Stream mới cho mỗi phép tính thường rõ ràng và dễ kiểm thử hơn việc giữ một Stream dùng lại. Với dữ liệu lớn, hãy đo hiệu năng rồi cân nhắc gom các phép tính trong một lượt phù hợp.

## 4. Bốn bổ sung quan trọng cho Stream từ Java 9

### 4.1. takeWhile: giữ đoạn đầu liên tiếp thỏa điều kiện

```java
List<Integer> data = List.of(2, 4, 6, 1, 8);

List<Integer> prefix = data.stream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
// [2, 4, 6]
```

Trên **ordered stream**, `takeWhile` lấy đoạn liên tiếp dài nhất **từ đầu** còn thỏa predicate, dừng ở phần tử đầu tiên không thỏa. Vì vậy nó không lấy số `8` cuối danh sách.

Khác với:

```java
List<Integer> allEven = data.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());
// [2, 4, 6, 8]
```

`filter` xét mọi phần tử, còn `takeWhile` quan tâm **ranh giới đoạn đầu** của một luồng có thứ tự.

### 4.2. dropWhile: bỏ đoạn đầu liên tiếp thỏa điều kiện

```java
List<Integer> suffix = data.stream()
        .dropWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
// [1, 8]
```

`dropWhile` bỏ `2, 4, 6` và giữ lại `1, 8`. Nó **không** tiếp tục loại `8` chỉ vì `8` thỏa predicate.

Với **unordered stream** (ví dụ nguồn `Set.of(...)` hoặc stream bị `unordered()`), các thao tác `takeWhile`/`dropWhile` không nhất thiết có khái niệm đoạn đầu ổn định; Java cho phép chọn/bỏ một tập con phù hợp theo quy tắc unordered. Vì vậy **không dùng chúng thay `filter`** khi bài toán yêu cầu chọn mọi phần tử phù hợp không phụ thuộc thứ tự. Trên ordered parallel stream, chúng cũng có thể tốn chi phí đồng bộ do ràng buộc prefix.

### 4.3. Stream.ofNullable: 0 hoặc 1 phần tử

```java
String coupon = null;

List<String> nonNull = Stream.ofNullable(coupon)
        .collect(Collectors.toList());
// []
```

`Stream.ofNullable(value)` tạo stream chứa **một phần tử** khi `value` khác `null`, hoặc stream **rỗng** khi bằng `null`. Rất hữu ích khi một thuộc tính tùy chọn từ nguồn cũ có thể null:

```java
List<String> coupons = orders.stream()
        .flatMap(o -> Stream.ofNullable(o.coupon))
        .distinct()
        .sorted()
        .collect(Collectors.toList());
```

Đây là mảnh code dùng lớp `Order` ở ví dụ hoàn chỉnh. `flatMap` biến mỗi coupon thành 0 hoặc 1 phần tử và nối kết quả; `distinct` bỏ trùng, `sorted` bảo đảm thứ tự hiển thị.

**Đừng nhầm `Stream.ofNullable(null)` với `Stream.of((String) null)`**: lời gọi thứ hai tạo stream chứa đúng **một phần tử null**. Các collector hoặc factory vốn không chấp nhận null sẽ gặp lỗi khi nhận dữ liệu đó.

### 4.4. Stream.iterate(seed, hasNext, next): tạo dãy hữu hạn

```java
List<Integer> oneToFive = Stream.iterate(
        1, n -> n <= 5, n -> n + 1)
        .collect(Collectors.toList());
// [1, 2, 3, 4, 5]
```

Overload ba đối số có từ Java 9, tương tự vòng lặp `for (int n = 1; n <= 5; n++)`. Khác với overload hai đối số `iterate(seed, next)`, phương thức mới có điều kiện kết thúc rõ ràng. Không sử dụng stream vô hạn với terminal operation yêu cầu duyệt hết khi không có `limit` hoặc điểm dừng hợp lệ.

## 5. Optional giúp biểu diễn giá trị có thể vắng mặt

`Optional<T>` đại diện cho **có một giá trị T** hoặc **không có giá trị**. Thường nên dùng làm kiểu trả về của thao tác tìm kiếm hay phân giải tùy chọn, ví dụ `Optional<Order> findById(...)`. Không tạo `Optional` bằng `null`; khi đầu vào có thể null, dùng `Optional.ofNullable(value)`.

| API | Nghĩa | Phiên bản |
| --- | --- | --- |
| `Optional.of(value)` | Có giá trị, `null` gây `NullPointerException` | Java 8 |
| `Optional.ofNullable(value)` | Có giá trị nếu khác `null`, không thì empty | Java 8 |
| `map(mapper)` | Chuyển một giá trị nếu hiện diện; mapper trả `null` thành empty | Java 8 |
| `flatMap(mapper)` | Mapper đã trả `Optional<U>`, tránh `Optional<Optional<U>>` | Java 8 |
| `orElse(value)` / `orElseGet(supplier)` | Nhận giá trị hoặc mặc định | Java 8 |
| `orElseThrow(supplier)` | Ném exception có chủ đích nếu empty | Java 8 |
| `stream()` | Chuyển Optional thành stream 0/1 phần tử | **Java 9** |
| `or(supplier)` | Nếu empty, thử một `Optional` dự phòng bằng supplier | **Java 9** |
| `ifPresentOrElse(consumer, runnable)` | Có giá trị thì xử lý, không có thì chạy nhánh else | **Java 9** |

Các phương thức trên đều còn hiện hành. Một số tiện ích như `Optional.isEmpty()` chỉ xuất hiện từ Java 11, nên **không đặt chúng vào code phải biên dịch với `--release 9`**.

### 5.1. map và flatMap

Giả sử tìm được đơn hàng, nhưng trường coupon có thể null:

```java
Optional<String> coupon = findById(orders, "A02")
        .flatMap(o -> Optional.ofNullable(o.coupon));

Optional<Integer> percent = coupon.map(discountRates::get);
int value = percent.orElse(0);
```

Đây là đoạn dùng phương thức `findById` và biến `discountRates` trong ví dụ hoàn chỉnh. `flatMap` được dùng ở đây vì mapper trả về `Optional<String>`; nếu dùng `map` thay cho `flatMap`, kết quả sẽ là `Optional<Optional<String>>`, khó thao tác không cần thiết.

Trường hợp `discountRates.get(code)` trả null (coupon không nằm trong map), `Optional.map` sẽ chuyển thành empty. **Quy tắc nghiệp vụ** phải quyết định việc thiếu mã là “không giảm giá” hay “lỗi dữ liệu”; trong ví dụ học tập, mã giảm giá đã được định nghĩa và missing code cho tỷ lệ 0. Trong sản phẩm thật nên kiểm tra đầu vào, ghi nhận mã không hợp lệ hoặc từ chối đơn theo chính sách.

### 5.2. Optional.stream kết hợp với Stream.flatMap

```java
List<String> couponCodes = orders.stream()
        .map(o -> Optional.ofNullable(o.coupon))
        .flatMap(Optional::stream)
        .distinct()
        .sorted()
        .collect(Collectors.toList());
```

Mỗi `Optional<String>` thành stream chứa **0 hoặc 1** chuỗi; `flatMap` nối các stream và loại được các trường thiếu dữ liệu mà không cần `get()`. Đây là cách biểu đạt đặc biệt rõ khi pipeline thật sự làm việc với nhiều `Optional`.

Với nguồn ban đầu là trường có thể `null`, `flatMap(o -> Stream.ofNullable(o.coupon))` là lựa chọn trực tiếp và đơn giản hơn; hai cách cho cùng tập coupon trong ví dụ. Không cần tạo Optional trung gian nếu bài toán chỉ muốn loại null.

### 5.3. Optional.or và ifPresentOrElse

```java
Optional<Order> selected = findById(orders, "MISSING")
        .or(() -> findById(orders, "A02"));

selected.ifPresentOrElse(
        o -> System.out.println(o.id),
        () -> System.out.println("No order"));
```

`or` được thêm ở Java 9. Nó chỉ gọi supplier khi Optional đầu rỗng và **trả về một Optional**. Điều này tiện khi cần **thử nguồn tìm kiếm tiếp theo** nhưng vẫn muốn xử lý kết quả theo Optional. `orElseGet` lại trả một `Order` thực tế, không phải `Optional<Order>`.

`ifPresentOrElse` cũng có từ Java 9, giúp ghi cả hai nhánh có/không có giá trị. Không dùng `Optional.get()` mà chưa kiểm tra trạng thái; ưu tiên `map`, `orElse`, `orElseGet`, `or`, `ifPresentOrElse` hoặc `orElseThrow`.

**Phân biệt eager/lazy:** `orElse(expensiveMethod())` luôn đánh giá tham số trước khi gọi, kể cả khi Optional có giá trị. `orElseGet(() -> expensiveMethod())` chỉ gọi supplier khi rỗng. Dùng `orElseGet` khi việc tạo fallback tốn chi phí hoặc có side effect.

## 6. Chương trình tổng hợp hoàn chỉnh: báo cáo đơn hàng

Chương trình sau dùng **chỉ các API có trong Java 9** (ngoài một số API cũ vẫn hiện hành), để có thể biên dịch bằng `--release 9`. Không dùng `record`, `var`, `Stream.toList()` hay các API ra đời sau Java 9.

### 6.1. File OrderReport.java

```java
import java.util.*;
import java.util.stream.*;
import static java.util.Map.entry;

public final class OrderReport {
    static final class Order {
        final String id;
        final String category;
        final int quantity;
        final long unitPriceCents;
        final String coupon;

        Order(String id, String category, int quantity,
              long unitPriceCents, String coupon) {
            this.id = Objects.requireNonNull(id);
            this.category = Objects.requireNonNull(category);
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Invalid order values");
            }
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
            this.coupon = coupon;
        }

        long grossCents() {
            return Math.multiplyExact((long) quantity, unitPriceCents);
        }
    }

    static Optional<Order> findById(List<Order> orders, String id) {
        return orders.stream().filter(o -> o.id.equals(id)).findFirst();
    }

    static long netCents(Order order, Map<String, Integer> discountRates) {
        int rate = Optional.ofNullable(order.coupon)
                .map(discountRates::get).orElse(0);
        long gross = order.grossCents();
        return gross - Math.multiplyExact(gross, (long) rate) / 100;
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", "books", 2, 5000, null),
                new Order("A02", "tools", 1, 12000, "WELCOME"),
                new Order("A03", "books", 1, 7000, null),
                new Order("A04", "stationery", 3, 2000, "STUDENT"),
                new Order("A05", "tools", 2, 8000, null),
                new Order("A06", "books", 1, 3000, "WELCOME")
        );

        Set<String> allowedCategories =
                Set.of("books", "tools", "stationery");
        Map<String, Integer> discountRates =
                Map.of("WELCOME", 10, "STUDENT", 5);
        Map<String, String> labels = Map.ofEntries(
                entry("books", "Books"),
                entry("tools", "Tools"),
                entry("stationery", "Stationery"));

        long gross = orders.stream().mapToLong(Order::grossCents).sum();
        long net = orders.stream()
                .mapToLong(o -> netCents(o, discountRates)).sum();

        Map<String, Long> byCategory = new TreeMap<>(
                orders.stream()
                        .filter(o -> allowedCategories.contains(o.category))
                        .collect(Collectors.groupingBy(
                                o -> labels.get(o.category),
                                Collectors.summingLong(Order::grossCents))));

        List<String> largeOrderIds = orders.stream()
                .filter(o -> o.grossCents() >= 10000)
                .map(o -> o.id)
                .sorted()
                .collect(Collectors.toList());

        List<String> couponCodes = orders.stream()
                .map(o -> Optional.ofNullable(o.coupon))
                .flatMap(Optional::stream)
                .distinct()
                .sorted()
                .collect(Collectors.toList());

        List<String> couponCodesNullable = orders.stream()
                .flatMap(o -> Stream.ofNullable(o.coupon))
                .distinct()
                .sorted()
                .collect(Collectors.toList());

        Optional<Order> fallback = findById(orders, "MISSING")
                .or(() -> findById(orders, "A02"));

        int discountForA02 = findById(orders, "A02")
                .flatMap(o -> Optional.ofNullable(o.coupon))
                .map(discountRates::get)
                .orElse(0);

        System.out.println("orders=" + orders.size());
        System.out.println("grossCents=" + gross);
        System.out.println("netCents=" + net);
        System.out.println("byCategory=" + byCategory);
        System.out.println("largeOrderIds=" + largeOrderIds);
        System.out.println("couponCodes=" + couponCodes);
        System.out.println("couponCodesNullable=" + couponCodesNullable);
        System.out.println("fallback=" + fallback.map(o -> o.id).orElse("NONE"));
        System.out.println("discountA02=" + discountForA02);
        findById(orders, "A03").ifPresentOrElse(
                o -> System.out.println("found=" + o.id),
                () -> System.out.println("found=NONE"));

        List<Integer> readings = List.of(2, 4, 6, 1, 8);
        System.out.println("takeWhile=" + readings.stream()
                .takeWhile(n -> n % 2 == 0)
                .collect(Collectors.toList()));
        System.out.println("dropWhile=" + readings.stream()
                .dropWhile(n -> n % 2 == 0)
                .collect(Collectors.toList()));
        System.out.println("iterate=" + Stream.iterate(
                1, n -> n <= 5, n -> n + 1)
                .collect(Collectors.toList()));
    }
}
```

### 6.2. Biên dịch và chạy

Mở terminal tại thư mục chứa `OrderReport.java`, đã cài JDK 17 hoặc mới hơn. Để kiểm chứng ví dụ **không phụ thuộc API ra sau Java 9**, dùng:

```sh
javac --release 9 -encoding UTF-8 OrderReport.java
java OrderReport
```

Chương trình đã được kiểm tra bằng `javac --release 9` và chạy trên OpenJDK 24. **Stdout chính xác:**

```text
orders=6
grossCents=54000
netCents=52200
byCategory={Books=20000, Stationery=6000, Tools=28000}
largeOrderIds=[A01, A02, A05]
couponCodes=[STUDENT, WELCOME]
couponCodesNullable=[STUDENT, WELCOME]
fallback=A02
discountA02=10
found=A03
takeWhile=[2, 4, 6]
dropWhile=[1, 8]
iterate=[1, 2, 3, 4, 5]
```

### 6.3. Kiểm chứng dữ liệu và kết quả

| Mã | Nhóm | Số lượng | Đơn giá (đơn vị nhỏ nhất) | Coupon | Thành tiền trước giảm |
| --- | --- | ---: | ---: | --- | ---: |
| A01 | books | 2 | 5.000 | không có | 10.000 |
| A02 | tools | 1 | 12.000 | WELCOME (10%) | 12.000 |
| A03 | books | 1 | 7.000 | không có | 7.000 |
| A04 | stationery | 3 | 2.000 | STUDENT (5%) | 6.000 |
| A05 | tools | 2 | 8.000 | không có | 16.000 |
| A06 | books | 1 | 3.000 | WELCOME (10%) | 3.000 |

Tổng trước giảm là **54.000**. Giảm giá A02 = 1.200; A04 = 300; A06 = 300; tổng giảm **1.800**, nên sau giảm còn **52.200**. Tổng theo nhóm trước giảm là Books = 20.000, Tools = 28.000, Stationery = 6.000. `new TreeMap<>(...)` làm thứ tự báo cáo rõ ràng theo khóa: Books, Stationery, Tools.

Chương trình cố ý không in mã của những collection `Set.of`/`Map.of` theo thứ tự chèn. Các mã coupon được `sorted()` rồi mới in. Điều này khiến output ổn định khi đổi phiên bản JVM hoặc nhà cung cấp JDK.

### 6.4. Tại sao ví dụ phối hợp các API như vậy?

- `orders` là `List.of`: không đổi danh sách input bằng `add`/`remove`. Mỗi `Order` có trường `final` để tránh thay đổi dữ liệu trong pipeline.
- `allowedCategories` là `Set.of`: kiểm tra membership bằng `contains`, không cần thứ tự duyệt.
- `discountRates` là `Map.of`: bảng tra cứu nhỏ, cố định, không cho cập nhật trực tiếp.
- `labels` là `Map.ofEntries`: tập các cặp khóa/giá trị, dễ mở rộng.
- `mapToLong(...).sum()` tổng hợp số nguyên; `groupingBy` ghép với `summingLong` cho tổng theo nhóm.
- `findById` trả `Optional<Order>`; `or` tìm fallback một cách lazy; `ifPresentOrElse` xử lý cả hai trường hợp.
- `Optional::stream` loại các coupon thiếu thông qua `flatMap`; `Stream.ofNullable` cho một cách trực tiếp khi nguồn ban đầu là chuỗi có thể null.
- `takeWhile` và `dropWhile` minh họa hai phía của **ranh giới đoạn đầu**, hoàn toàn khác `filter`.

**Giới hạn nghiệp vụ của ví dụ:** giả định dữ liệu đã được kiểm tra và tỷ lệ phần trăm hợp lệ, các mã coupon đều được khai báo. Việc làm tròn chiết khấu đang dùng **chia nguyên** theo đơn vị tiền nhỏ nhất. Một hệ thống tính tiền thật phải xác định quy tắc làm tròn, thuế, tiền tệ và hành vi với mã không hợp lệ; không dùng ví dụ này làm chuẩn hóa đơn tài chính khi chưa định nghĩa những quy tắc đó.

## 7. Thực hành xử lý duplicate, null và dữ liệu không hợp lệ

### 7.1. Duplicate có ý nghĩa khác nhau ở List, Set, Map

- `List.of("A", "A")` hợp lệ: danh sách giữ hai phần tử.
- `Set.of("A", "A")` ném `IllegalArgumentException`: factory không nhận duplicate.
- `Map.of("A", 1, "A", 2)` ném `IllegalArgumentException`: key trùng.
- Trong `Stream`, `distinct()` loại phần tử trùng theo `equals`, **không** phải yêu cầu đầu vào không được trùng.
- Với `Collectors.toMap(keyFn, valueFn)`, duplicate key sẽ gây `IllegalStateException` nếu không có merge function; có thể chỉ định merge function hoặc dùng `groupingBy` nếu nghiệp vụ cần một-nhiều.

Ví dụ chọn chính sách cộng dồn khi key bị trùng:

```java
Map<String, Long> totals = orders.stream()
        .collect(Collectors.toMap(
                o -> o.category,
                Order::grossCents,
                Long::sum));
```

Đây là mảnh code sử dụng `Order`/`orders` trong ví dụ chính. Nó tạo map tổng theo nhóm với merge function `Long::sum`; vẫn cần sắp xếp khi hiển thị nếu muốn thứ tự ổn định. Trong ứng dụng production có thể dùng `Math.addExact` khi cần phát hiện overflow, vì `Long::sum` tự nó không kiểm tra overflow.

### 7.2. Dữ liệu có null: chọn đúng biên xử lý

`List.of`/`Set.of`/`Map.of` đều không nhận `null` như một phần tử trực tiếp (Map cũng không nhận null key/value), nhưng các đối tượng trong `List` có thể chứa **field** null. Khi field như `coupon` được phép thiếu:

```java
List<String> knownCoupons = orders.stream()
        .flatMap(o -> Stream.ofNullable(o.coupon))
        .collect(Collectors.toList());
```

Nếu phần tử của input collection có thể chính là `null`, không nên tạo `List.of` từ dữ liệu đó. Hãy xác định chính sách **loại bỏ null** hoặc **từ chối** ở bước chuẩn hóa dữ liệu. Không che một lỗi nghiệp vụ bằng `Optional.ofNullable` khắp mọi nơi.

### 7.3. Optional không phải cơ chế xử lý mọi lỗi

`Optional.empty()` rất phù hợp với “không tìm thấy mã đơn”, nhưng không nên tự động biến lỗi đọc file, lỗi mạng, truy vấn SQL thất bại hay dữ liệu bị hỏng thành empty. Những tình huống đó cần exception hoặc trạng thái lỗi riêng. `Optional` mô hình hóa **sự vắng mặt được chấp nhận**, không thay thế error handling.

Tránh khai báo các field/call parameter `Optional` nếu API không thật sự yêu cầu: nó chủ yếu hữu ích ở **kiểu trả về**. Đừng dùng `Optional.get()` để quay về kiểu kiểm tra `null` hoặc ném `NoSuchElementException` ngoài ý muốn. Nếu thiếu giá trị là lỗi, dùng `orElseThrow(() -> new IllegalArgumentException(...))`.

## 8. Collection và Stream trong các JDK mới hơn

Bài tập chính dùng API Java 9 để phản ánh đúng nguồn gốc tính năng. Các tiện ích sau **còn hiện hành nhưng không phải Java 9**:

| API | Xuất hiện từ | Điểm khác biệt |
| --- | --- | --- |
| `List.copyOf(collection)`, `Set.copyOf`, `Map.copyOf` | Java 10 | Tạo collection không cho sửa từ collection/map có sẵn; từ chối null, có thể tái sử dụng instance phù hợp |
| `Collectors.toUnmodifiableList()` / `toUnmodifiableSet()` / `toUnmodifiableMap()` | Java 10 | Thu từ stream thành kết quả không cho sửa, có các quy tắc từ chối null/duplicate tương ứng |
| `Stream.toList()` | Java 16 | Thu trực tiếp thành danh sách **unmodifiable**, giữ encounter order nếu có |
| `Optional.isEmpty()` | Java 11 | Kiểm tra Optional rỗng một cách trực tiếp |
| `Stream.mapMulti(...)` | Java 16 | Có thể biểu diễn quan hệ một-nhiều hiệu quả trong một số pipeline |

Ví dụ khi dự án đã đặt baseline Java 17:

```java
List<String> ids = orders.stream()
        .map(o -> o.id)
        .toList();  // Java 16+, không sửa được kết quả
```

Đây là mảnh code chỉ dùng được trong ngữ cảnh có `orders` ở ví dụ chính. Nếu build bắt buộc `--release 9`, hãy dùng `collect(Collectors.toList())` như chương trình hoàn chỉnh. **Không ngầm giả định** danh sách do `Collectors.toList()` tạo được phép sửa; JavaDoc không cam kết tính mutable hay implementation. Cần một `ArrayList` thực sự? Dùng:

```java
List<String> editable = orders.stream()
        .map(o -> o.id)
        .collect(Collectors.toCollection(ArrayList::new));
```

Còn nếu đầu vào là danh sách hiện có và muốn một snapshot không cho sửa trên Java 10+, `List.copyOf(input)` phù hợp (với điều kiện không có null). Không sử dụng `Collections.unmodifiableList(input)` như một snapshot độc lập nếu `input` vẫn tiếp tục bị chỉnh.

## 9. Những sai lầm cần tránh khi phối hợp Stream và Optional

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi `List.of` là mutable | `UnsupportedOperationException` khi gọi `add` hoặc `set` | Dùng `new ArrayList<>(source)` khi cần cập nhật |
| Truyền null vào factory | `NullPointerException` | Kiểm tra hoặc làm sạch input trước |
| Truyền key trùng vào `Map.of` | `IllegalArgumentException` | Xác định chính sách duplicate hoặc dùng collector có merge |
| Dựa vào thứ tự `Map.of`/`Set.of` | Output thay đổi theo runtime | Dùng `sorted`, `TreeMap` hoặc cấu trúc có thứ tự được đảm bảo |
| Dùng `takeWhile` thay `filter` | Bỏ sót các phần tử phù hợp nằm sau phần tử đầu tiên không khớp | Chọn theo semantics “prefix” hay “mọi phần tử” |
| Dùng `takeWhile` trên unordered stream rồi kỳ vọng prefix | Kết quả không có ý nghĩa prefix ổn định | Giữ nguồn có encounter order hoặc dùng thuật toán khác |
| Cố dùng lại một `Stream` đã gọi terminal | Có thể gặp `IllegalStateException` | Tạo `orders.stream()` mới |
| Dùng `Optional.get()` khi giá trị vắng mặt | `NoSuchElementException` | `map`, `orElse`, `orElseGet`, `or` hoặc `orElseThrow` |
| Dùng `map` khi mapper đã trả Optional | Tạo `Optional<Optional<T>>` | Dùng `flatMap` |
| Quên `sorted` trước khi in `groupingBy` map | Thứ tự hiển thị không ổn định | Bao bằng `TreeMap` hoặc collector có map factory |
| Biến state bên ngoài trong `map`/`filter` | Side effect khó đoán, lỗi khi chạy song song | Dùng phép biến đổi không can thiệp (non-interfering), collector phù hợp |
| Gọi `parallelStream()` chỉ để “tăng tốc” | Chi phí chia việc có thể tăng, output/side effect khó kiểm soát | Đo hiệu năng trước; giữ sequential cho pipeline nhỏ, có thứ tự |
| Sao chép code `Stream.toList()` vào dự án Java 9 | Lỗi biên dịch vì API ra đời từ Java 16 | Chọn API theo baseline và dùng `javac --release ...` để kiểm tra |

Thêm lưu ý: `Stream` không phải một cơ chế cache kết quả; nó mô tả một phép tính. `peek` chủ yếu phục vụ quan sát/debug chứ không nên chứa logic nghiệp vụ cần chắc chắn chạy. Với stream có thứ tự, `findFirst` có ý nghĩa phần tử đầu; với unordered stream và `findAny` thì không thể dự đoán phần tử nào được chọn.

## 10. Thử nghiệm nhỏ để tự luyện tập

1. **Không có đơn cần tìm:** đổi fallback `"A02"` thành `"MISSING2"`. Dự đoán kết quả: `fallback=NONE`. Giải thích vì sao supplier của `or` được gọi.
2. **Tăng số lượng đơn A03 từ 1 lên 2:** tính lại `grossCents` và `netCents` rồi chạy để kiểm tra. Các pipeline tự tạo từ `List` sẽ dùng dữ liệu mới được khởi tạo ở mỗi lần chạy.
3. **Thêm một mã coupon vào đơn A05:** kiểm tra kết quả `couponCodes` và `couponCodesNullable`. Tại sao mỗi code chỉ được in một lần?
4. **Đổi dãy đọc thành `List.of(1, 2, 4)`:** dự đoán `takeWhile(n -> n % 2 == 0)` trả danh sách rỗng, `dropWhile(...)` giữ nguyên toàn bộ danh sách. So sánh với `filter`.
5. **Thêm phần tử `null` vào `List.of`:** xử lý exception và đề xuất chính sách chuẩn hóa input.
6. **Dùng `Collectors.toMap` theo category mà bỏ merge function:** dự đoán lỗi khi có nhiều đơn cùng nhóm; sửa lại bằng `Long::sum` hoặc `groupingBy`.
7. **Tạo nhóm có thứ tự:** thay `new TreeMap<>(...)` bằng overload `groupingBy(classifier, TreeMap::new, downstream)`, so sánh output.
8. **Đổi baseline:** nếu tổ chức dùng Java 17, hãy cân nhắc `Stream.toList()` và giải thích sự khác biệt với `Collectors.toList()`; xác minh cả hai bằng `--release 17`.

## 11. Checklist triển khai trong dự án

- [ ] Phân biệt dữ liệu cấu hình cố định với collection sẽ cập nhật; chọn `List.of/Set.of/Map.of` chỉ khi cần unmodifiable.
- [ ] Kiểm tra null và duplicate ngay khi chuyển dữ liệu từ API/DB/file sang collection.
- [ ] Có encounter order nếu dùng `findFirst`, `takeWhile`, `dropWhile` hoặc muốn kết quả có thứ tự; sắp xếp map khi in.
- [ ] Chọn `filter` cho mọi phần tử phù hợp, chọn `takeWhile/dropWhile` chỉ cho logic prefix.
- [ ] Dùng `mapToInt/mapToLong` và collector thay vì cộng dồn qua biến mutable ngoài pipeline.
- [ ] Chỉ dùng `Optional` cho trường hợp thiếu giá trị có chủ ý; không nuốt lỗi thành `Optional.empty`.
- [ ] Với dữ liệu tùy chọn, cân nhắc `Optional.stream` hoặc `Stream.ofNullable` cho pipeline.
- [ ] Tránh stateful side effect trong pipeline; đo hiệu năng trước khi dùng parallel stream.
- [ ] Xác định rõ collection kết quả có cần sửa hay không; chọn collector phù hợp.
- [ ] Biên dịch với `--release` đúng baseline của sản phẩm để phát hiện API xuất hiện ở các bản Java mới hơn.

## Tài liệu chính thức

- [Java SE 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)
- [Java SE 25 — List API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [Java SE 25 — Set API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html)
- [Java SE 25 — Map API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)
- [Java SE 25 — Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 — Collectors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 25 — Optional API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html)

**Gợi ý tự kiểm tra:** JavaDoc ghi `Since: 9` cho các API Java 9 đã nêu; khi sử dụng JDK mới, tránh suy luận rằng mọi phương thức mới hiện trên trang JavaDoc đều đã có ở Java 9. Ví dụ tổng hợp được biên dịch với `--release 9` để xác nhận đúng giới hạn phiên bản.
