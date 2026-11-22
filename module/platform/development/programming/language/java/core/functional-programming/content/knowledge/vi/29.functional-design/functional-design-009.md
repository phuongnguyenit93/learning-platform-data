# Cân bằng độ ngắn, khả năng đọc và chi phí xử lý khi thiết kế theo hàm trong Java

Trong Java, **lập trình theo hàm** giúp mô tả phép biến đổi dữ liệu bằng `Stream`, lambda, method reference, `Optional` và các hàm thuần (*pure functions*). Nhưng code **ngắn dòng** không tự động là code **dễ hiểu** hoặc **hiệu quả**. Một pipeline dùng một dòng duy nhất có thể giấu nhiều lần duyệt danh sách, truy vấn database hoặc cấp phát đối tượng; ngược lại, tách code thành quá nhiều helper vụn vặt có thể làm người đọc liên tục nhảy qua các hàm.

Mục tiêu không phải là tối thiểu hóa số ký tự, mà là tìm điểm cân bằng giữa:

1. **Đúng nghiệp vụ**: thứ tự lọc, lựa chọn và tổng hợp cho kết quả chính xác.
2. **Khả năng đọc/duy trì**: người tiếp theo hiểu kiểu dữ liệu, ý nghĩa các bước, cách xử lý lỗi và trường hợp rỗng.
3. **Chi phí xử lý**: thời gian, bộ nhớ, I/O, độ phức tạp thuật toán, boxing, khả năng dừng sớm và chi phí song song.

**Nguyên tắc thực tế:** Đầu tiên viết code đúng và dễ đọc; sau đó nhận diện các chi phí đáng kể, đo bằng dữ liệu thực, tối ưu **điểm nghẽn** mà không hy sinh tính đúng hoặc tạo sự phức tạp không cần thiết.

## 1. Ba chiều đánh đổi và những câu hỏi cần trả lời

| Tiêu chí | Câu hỏi | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Độ ngắn | Bước này có thực sự giúp giảm boilerplate không? | Một dòng có quá nhiều điều kiện lồng nhau hoặc ternary khó đọc. |
| Khả năng đọc | Có nhìn ra nguồn → lọc → biến đổi → thu kết quả? | Lambda dài, tên biến `x`/`y`, nhiều `map` làm đổi kiểu mà không rõ. |
| Chi phí CPU | Có duyệt lại cùng dữ liệu, sort hay hash lookup nhiều lần? | `stream()` lồng trong `filter`, `sorted` không cần thiết. |
| Chi phí bộ nhớ | Có tạo list, map, wrapper object trung gian lớn? | `boxed()` rồi unbox, `toList()` chỉ để stream lại. |
| I/O | Có gọi network/database hoặc mở file trong từng mapper? | N+1 query, blocking trong parallel stream, thiếu đóng tài nguyên. |
| Đặc tính nguồn | Nguồn nhỏ/lớn, có thứ tự, rỗng, một lần hay vô hạn? | Tưởng `Stream` dùng lại được hoặc xử lý nguồn vô hạn bằng `toList()`. |
| Kiểm thử | Trường hợp biên có xác định? | Null, duplicate, thứ tự, số lớn, nguồn rỗng bị bỏ qua. |

Một phép biến đổi `O(n)` có thể trở thành `O(n²)` khi lồng một phép quét toàn danh sách trong mỗi phần tử. Đây thường là vấn đề lớn hơn việc tiết kiệm vài ký tự trong lambda.

## 2. Stream pipeline ngắn, rõ và diễn đạt đúng ý định

Giả sử yêu cầu là **lấy tên khách hàng có hóa đơn từ 100 trở lên, bỏ tên trùng và sắp theo chữ cái**. Với dữ liệu rời rạc, một pipeline có tên phương thức rõ ràng thường dễ đọc hơn mã cập nhật danh sách thủ công.

Tạo file `ReadablePipelineDemo.java`:

~~~java
import java.util.List;

public class ReadablePipelineDemo {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Chi", 130),
                new Order("An", 75),
                new Order("Bình", 160),
                new Order("Chi", 210),
                new Order("An", 120));

        List<String> customers = orders.stream()
                .filter(order -> order.total() >= 100)
                .map(Order::customer)
                .distinct()
                .sorted()
                .toList();

        System.out.println(customers);
    }
}
~~~

~~~bash
javac --release 17 ReadablePipelineDemo.java
java ReadablePipelineDemo
~~~

Kết quả:

~~~text
[An, Bình, Chi]
~~~

**Vì sao pipeline này đọc tốt?** Mỗi bước có một vai trò rõ:

~~~text
List<Order>
  .stream()                       → Stream<Order>
  .filter(Order -> boolean)        → Stream<Order>
  .map(Order -> String)            → Stream<String>
  .distinct()                      → Stream<String>
  .sorted()                        → Stream<String>
  .toList()                        → List<String>
~~~

`filter` chọn đối tượng trước, `map` mới chuyển thành tên; `distinct` loại tên trùng, và `sorted` xếp chuỗi theo thứ tự tự nhiên. Nguồn `List` có encounter order, nhưng kết quả được sort để thứ tự hiển thị có thể dự đoán.

**Nhược điểm tiềm năng:** `distinct` giữ trạng thái loại trùng, `sorted` là thao tác có trạng thái và có chi phí sắp xếp. Những bước đó cần thiết khi **yêu cầu nghiệp vụ** đúng là bỏ trùng và sắp xếp. Nếu chỉ cần đếm hóa đơn đạt ngưỡng, đừng giữ các bước không cần thiết chỉ vì code trông “functional”.

## 3. Không phải Stream ngắn hơn là luôn tốt hơn vòng lặp

Hai cách viết dưới đây có cùng mục tiêu: tính tổng số lượng của các sản phẩm có trạng thái active. Khi quy tắc đơn giản, cả vòng lặp và Stream đều có thể dễ hiểu; không cần biến mọi vòng lặp thành Stream.

Tạo file `LoopVsStreamDemo.java`:

~~~java
import java.util.List;

public class LoopVsStreamDemo {
    record Item(boolean active, int quantity) {}

    static long totalWithLoop(List<Item> items) {
        long total = 0;
        for (Item item : items) {
            if (item.active()) {
                total += item.quantity();
            }
        }
        return total;
    }

    static long totalWithStream(List<Item> items) {
        return items.stream()
                .filter(Item::active)
                .mapToLong(Item::quantity)
                .sum();
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item(true, 4),
                new Item(false, 9),
                new Item(true, 6));

        System.out.println("loop=" + totalWithLoop(items));
        System.out.println("stream=" + totalWithStream(items));
    }
}
~~~

~~~bash
javac --release 17 LoopVsStreamDemo.java
java LoopVsStreamDemo
~~~

Kết quả:

~~~text
loop=10
stream=10
~~~

`mapToLong(Item::quantity)` chủ ý dùng phép cộng kiểu `long` để giảm nguy cơ tràn so với tổng `int`. Hai cách đều có độ phức tạp thời gian **`O(n)`** và không cần danh sách trung gian; nhưng chi phí runtime chính xác phụ thuộc JIT, kích thước dữ liệu và môi trường.

Vòng lặp thường phù hợp khi phải điều khiển luồng xử lý phức tạp, có `break`/`continue` theo nhiều trạng thái, hoặc khi một vòng lặp thu nhiều kết quả đặc thù. Stream thường phù hợp khi có chuỗi lọc/biến đổi/thu kết quả ngắn, các bước độc lập, không có side effect. **Đừng quyết định chỉ theo cảm giác “có lambda tức là hiện đại hơn”.**

## 4. Tránh lambda quá dài: đặt tên cho quy tắc nghiệp vụ

Một lambda gom cả kiểm tra null, trạng thái, hạn mức và định dạng có thể ngắn về số dòng nhưng khó đọc:

~~~java
// Minh họa với biến orders và kiểu Order đã được khai báo.
orders.stream().filter(o -> o != null && o.active()
        && o.total() >= 100 && o.customer() != null)
        .map(o -> o.customer().trim().toUpperCase())
        .toList();
~~~

Khi điều kiện phát triển, nên đặt tên cho các bước có **ý nghĩa nghiệp vụ**. Method reference hoặc phương thức nhỏ có tên rõ giúp đọc pipeline như một mô tả yêu cầu.

Tạo file `NamedRulesDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NamedRulesDemo {
    record Order(String customer, int total, boolean active) {}

    static boolean isEligible(Order order) {
        return order != null
                && order.active()
                && order.total() >= 100
                && order.customer() != null;
    }

    static String normalizedCustomer(Order order) {
        return order.customer().trim()
                .toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order(" An ", 120, true),
                new Order("Bình", 80, true),
                null,
                new Order("Chi", 150, false),
                new Order("Mai", 130, true));

        List<String> names = orders.stream()
                .filter(NamedRulesDemo::isEligible)
                .map(NamedRulesDemo::normalizedCustomer)
                .toList();

        System.out.println(names);
    }
}
~~~

~~~bash
javac --release 17 NamedRulesDemo.java
java NamedRulesDemo
~~~

Kết quả:

~~~text
[AN, MAI]
~~~

`isEligible` bao gồm kiểm tra null, nên `normalizedCustomer` có thể giả định phần tử được truyền vào không null và có tên. Đó là **invariant của pipeline**; nếu phương thức `normalizedCustomer` được gọi nơi khác, hợp đồng của nó cần được làm rõ hoặc kiểm tra riêng.

Đặt tên nên dựa trên **mục tiêu**, không chỉ trích mỗi phép toán nhỏ thành một helper như `getTotal()` chỉ vì muốn giảm một lambda. Quá nhiều phương thức chuyển tiếp một dòng mà không mang ý nghĩa mới có thể khiến code phải đọc ở nhiều nơi hơn.

## 5. Chọn thứ tự thao tác: đẩy phép lọc rẻ lên trước khi đúng ngữ nghĩa

Với pipeline độc lập, thường có lợi khi thực hiện phép lọc đơn giản trước một biến đổi tốn kém:

~~~java
// Nếu hợp đồng nghiệp vụ cho phép:
// lọc từ Order trước rồi mới chuyển thành Report.
orders.stream()
        .filter(Order::active)
        .map(this::expensiveReport)
        .toList();
~~~

Đoạn trên **chỉ để minh họa trong phương thức instance** với `Order::active` và `expensiveReport` đã tồn tại, không phải lớp Java độc lập. Chi phí tạo report chỉ phát sinh cho những order được giữ lại.

Cách viết `.map(this::expensiveReport).filter(Report::active)` có thể tính report cho toàn bộ nguồn và đôi khi còn không tương đương nếu `Report.active` mang nghĩa khác `Order.active`. **Chỉ đổi thứ tự khi bảo toàn ý nghĩa, lỗi và các side effect hợp lệ**. Không mặc định `filter` với predicate dựa vào dữ liệu **sau** `map` có thể đặt trước map.

Nên chú ý:

- `filter` thường giữ nguyên kiểu phần tử và có thể giảm lượng việc sau đó.
- `map` đổi kiểu từ `T` sang `R`; lambda sau map không còn nhận `T`.
- `sorted` có chi phí trạng thái, có thể xử lý toàn tập; bỏ qua nếu không cần thứ tự.
- `distinct` chỉ có ý nghĩa loại trùng của **kiểu phần tử tại vị trí đó**; đặt trước/sau `map` có thể cho kết quả khác.
- `limit` và `findFirst` có thể dừng sớm, nhưng thứ tự lọc/map và encounter order ảnh hưởng ý nghĩa của “đầu tiên”.

## 6. Độ ngắn có thể che một lần duyệt lồng nhau `O(n²)`

Một lỗi đáng lo là gọi `stream().anyMatch(...)` trên toàn bộ danh sách **bên trong** một `filter` đang duyệt danh sách khác. Nếu cả hai danh sách tăng theo `n`, phương án này có thể làm khoảng `n²` phép so sánh ở trường hợp bất lợi.

Ví dụ yêu cầu: **chỉ giữ đơn hàng có `customerId` nằm trong danh sách khách hợp lệ**.

Cách đơn giản nhưng có thể chậm:

~~~java
// Minh họa trong phương thức có orders và allowedIds.
List<Order> selected = orders.stream()
        .filter(o -> allowedIds.stream()
                .anyMatch(id -> id.equals(o.customerId())))
        .toList();
~~~

Với `orders` có `n` phần tử và `allowedIds` có `m` phần tử, cách này có chi phí xấu nhất xấp xỉ **`O(n × m)`**. Dùng `HashSet` để tra cứu membership trung bình nhanh hơn:

~~~java
// Minh họa, allowedIds là List<String>.
Set<String> allowed = new HashSet<>(allowedIds);
List<Order> selected = orders.stream()
        .filter(o -> allowed.contains(o.customerId()))
        .toList();
~~~

Chi phí xây set trung bình khoảng `O(m)`, rồi n lượt `contains` trung bình `O(1)`, cho tổng kỳ vọng khoảng **`O(n + m)`** với hash tốt. Đây là **phân tích trung bình**, không phải bảo đảm thời gian xấu nhất tuyệt đối của mọi hash collection.

### Ví dụ Java hoàn chỉnh: lọc theo tập ID

Tạo file `MembershipLookupDemo.java`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class MembershipLookupDemo {
    record Order(String code, String customerId) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O1", "C1"),
                new Order("O2", "C9"),
                new Order("O3", "C2"),
                new Order("O4", "C1"));

        List<String> allowedIds = List.of("C1", "C2");
        Set<String> allowed = new HashSet<>(allowedIds);

        List<String> selected = orders.stream()
                .filter(order -> allowed.contains(order.customerId()))
                .map(Order::code)
                .toList();

        System.out.println(selected);
    }
}
~~~

~~~bash
javac --release 17 MembershipLookupDemo.java
java MembershipLookupDemo
~~~

Kết quả:

~~~text
[O1, O3, O4]
~~~

`HashSet` được tạo **một lần trước** pipeline. Không xây `new HashSet<>(allowedIds)` bên trong từng `filter`, vì làm vậy lại tạo bộ nhớ và thực hiện công việc lặp. Nếu ID có thể null, cần làm rõ hợp đồng và chọn cấu trúc phù hợp; ví dụ dùng ID không null.

## 7. N+1 truy vấn: đừng gọi database trong mỗi `map` chỉ vì code gọn

Một mapper có thể trông rất tự nhiên:

~~~java
// Minh họa, repository là dịch vụ I/O chặn:
List<Customer> customers = orders.stream()
        .map(order -> repository.loadCustomer(order.customerId()))
        .toList();
~~~

Nếu `loadCustomer` thực hiện **một truy vấn database mỗi phần tử**, danh sách 1.000 order có thể tạo 1.000 lượt truy vấn — dù code chỉ vài dòng. Đó là dạng **N+1 query/problem** (tùy cách lấy danh sách nguồn) và thường chịu overhead network, connection pool, serialization, transaction, retry.

Lựa chọn phù hợp hơn, khi API/data model hỗ trợ:

1. Thu các ID khách hàng cần thiết thành một tập.
2. Dùng truy vấn **batch** theo tập ID, có chính sách phân trang/chunk nếu backend giới hạn.
3. Lập `Map<ID,Customer>`.
4. Dùng `map`/lookup trong bộ nhớ để ghép dữ liệu.

Các bước này dài hơn code `map(repository::load)`, nhưng thường rõ ràng hơn về số round trip I/O và dễ kiểm soát timeout/khối lượng dữ liệu. Tuy vậy, **batch query không phải luôn nhanh hơn** nếu tập rất nhỏ, backend có ràng buộc riêng hoặc cần nhất quán giao dịch; đo trên hệ thống thực.

Không dùng `parallelStream()` để chữa N+1 truy vấn bằng cách bắn 1.000 yêu cầu đồng thời. Nó có thể gây quá tải connection pool/backend và làm thiếu thread xử lý trong common fork/join pool. Với I/O chặn, cần giới hạn concurrency, timeout và mô hình executor/async riêng phù hợp.

## 8. Boxing/unboxing: tránh chuyển kiểu đi vòng khi xử lý số nhiều

`Stream<Integer>` xử lý phần tử kiểu wrapper; `IntStream`, `LongStream`, `DoubleStream` xử lý primitive tương ứng. Một pipeline:

~~~java
long result = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .boxed()
        .mapToLong(Integer::longValue)
        .sum();
~~~

đi theo đường `int → Integer → long`. Nếu không thật sự cần object `Integer`, có thể viết:

~~~java
long result = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .asLongStream()
        .sum();
~~~

Trong Java 17, hai biểu thức cho cùng tổng `5_000_050_000`. Kiểu `long` quan trọng vì tổng đã vượt giới hạn `int`.

Nhưng `boxed()` **không sai** khi đầu ra hoặc thư viện thật sự yêu cầu `List<Integer>` hay `Map<Integer,V>`. Mục tiêu là tránh chuyển primitive thành wrapper rồi quay lại primitive chỉ vì thói quen viết `map` trên object stream.

Tạo file `PrimitivePipelineDesignDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitivePipelineDesignDemo {
    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 100_000)
                .asLongStream()
                .sum();

        List<Integer> firstFive = IntStream.rangeClosed(1, 5)
                .boxed()
                .toList();

        System.out.println("sum=" + sum);
        System.out.println("firstFive=" + firstFive);
    }
}
~~~

~~~bash
javac --release 17 PrimitivePipelineDesignDemo.java
java PrimitivePipelineDesignDemo
~~~

Kết quả:

~~~text
sum=5000050000
firstFive=[1, 2, 3, 4, 5]
~~~

Dùng `mapToInt`/`mapToLong` khi thao tác số và đếm/tổng kết tương ứng. Với số tiền yêu cầu chính xác, không dùng `double` chỉ để pipeline ngắn: ưu tiên đơn vị nhỏ với kiểm soát overflow hoặc `BigDecimal` theo hợp đồng nghiệp vụ.

## 9. Materialization: `toList()` rồi `stream()` lại có cần không?

Một pipeline như:

~~~java
// Minh họa, source là Collection<Order>.
List<Order> filtered = source.stream()
        .filter(Order::active)
        .toList();

List<String> names = filtered.stream()
        .map(Order::customer)
        .toList();
~~~

tạo một **danh sách trung gian**. Nếu danh sách `filtered` chỉ được dùng một lần, có thể nối trực tiếp:

~~~java
List<String> names = source.stream()
        .filter(Order::active)
        .map(Order::customer)
        .toList();
~~~

Cách thứ hai tránh việc lưu `filtered` riêng, thường gọn và tiết kiệm bộ nhớ. Tuy nhiên **materialization vẫn hợp lý** khi cần dùng kết quả trung gian cho nhiều truy vấn, cần snapshot ở một thời điểm, gỡ lỗi hoặc chia ranh giới giữa các giai đoạn xử lý.

Đặc biệt với nguồn chỉ đọc một lần (I/O stream, iterator), việc materialize có thể giúp đọc lại kết quả nếu dữ liệu đủ nhỏ; nhưng có chi phí bộ nhớ và không phù hợp với nguồn vô hạn.

Trong Java 17, `Stream.toList()` trả danh sách **không hỗ trợ thao tác sửa cấu trúc**. Nó không deep-copy các đối tượng mutable bên trong; muốn snapshot bất biến đầy đủ cần thiết kế phần tử bất biến hoặc copy phù hợp.

## 10. Chọn terminal operation đúng để giảm xử lý thừa

Đừng thu danh sách lớn chỉ để biết có phần tử thỏa điều kiện hay không:

~~~java
// Không cần tạo list nếu chỉ hỏi có tồn tại không:
boolean hasMatch = orders.stream()
        .filter(o -> o.total() > 100)
        .toList()
        .size() > 0;
~~~

Cách tự nhiên hơn:

~~~java
boolean hasMatch = orders.stream()
        .anyMatch(o -> o.total() > 100);
~~~

`anyMatch` là **short-circuit terminal operation**: có thể dừng khi tìm thấy một phần tử thỏa điều kiện. `filter(...).toList().size()` thu toàn bộ các kết quả lọc trước khi đếm; ngoài chi phí duyệt, nó có thể cấp phát danh sách không cần thiết.

Các terminal operation có ý nghĩa khác nhau:

| Câu hỏi | API thường phù hợp | Trên nguồn rỗng |
| --- | --- | --- |
| Có ít nhất một phần tử thỏa? | `anyMatch(p)` | `false` |
| Tất cả phần tử thỏa? | `allMatch(p)` | `true` |
| Không có phần tử nào thỏa? | `noneMatch(p)` | `true` |
| Phần tử đầu theo encounter order? | `findFirst()` | `Optional.empty()` |
| Đếm số phần tử trong pipeline? | `count()` | `0L` |
| Tính tổng primitive? | `mapToLong(...).sum()` | `0L` |
| Thu toàn bộ vào danh sách? | `toList()` | Danh sách rỗng |

**Tối ưu phải theo nghĩa câu hỏi.** Đừng thay `findFirst` bằng `findAny` chỉ để giảm ràng buộc thứ tự nếu nghiệp vụ cần đối tượng đầu tiên theo thứ tự nguồn. Đừng thay `allMatch` bằng `anyMatch`: một phép yêu cầu tất cả, phép kia chỉ cần một nhân chứng.

## 11. Trường hợp `Optional`: xử lý vắng mặt rõ hơn là viết thật ngắn

Trong pipeline, `findFirst`, `min`, `max`, hoặc `reduce` không identity trả `Optional<T>`. Thay vì gọi `get()` vô điều kiện, hãy chọn hợp đồng:

~~~java
// Minh họa với một Stream<Order>:
String name = orders.stream()
        .filter(o -> o.total() >= 100)
        .map(Order::customer)
        .findFirst()
        .orElse("Không có khách phù hợp");
~~~

Cách này đọc rõ: nếu không tìm thấy, trả thông điệp thay thế. Nếu việc không có kết quả là lỗi, dùng `orElseThrow(() -> new IllegalStateException(...))` và thông điệp thích hợp.

`Optional` không nên bị dùng như cơ chế thay thế cho **toàn bộ** điều khiển luồng chương trình hoặc để che lỗi dữ liệu. Với nhánh xử lý phức tạp, một `if` có tên trạng thái rõ có thể dễ đọc hơn chuỗi `map/flatMap/orElseGet` nhiều tầng.

`orElse(expensiveFallback())` đánh giá đối số fallback trước khi gọi phương thức, kể cả khi Optional có giá trị; nếu fallback tốn chi phí, dùng `orElseGet(() -> expensiveFallback())` để chỉ gọi khi thiếu. Cả hai đoạn là **minh họa**, không phải chương trình độc lập.

## 12. `flatMap`: dùng khi giải quyết cấu trúc nhiều giá trị, không chỉ làm code ngắn

Với danh sách các nhóm thành viên:

~~~text
List<List<String>>
    .stream()                → Stream<List<String>>
    .map(List::stream)       → Stream<Stream<String>>
    .flatMap(List::stream)   → Stream<String> (thay map ở cùng vị trí)
~~~

`map` và `flatMap` ở sơ đồ là **hai lựa chọn khác nhau**, không phải gọi liên tiếp.

Tạo file `FlattenReadableDemo.java`:

~~~java
import java.util.List;

public class FlattenReadableDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("An", "Bình"),
                List.of("Chi"),
                List.of());

        List<String> all = groups.stream()
                .flatMap(List::stream)
                .toList();

        System.out.println(all);
    }
}
~~~

~~~bash
javac --release 17 FlattenReadableDemo.java
java FlattenReadableDemo
~~~

Kết quả:

~~~text
[An, Bình, Chi]
~~~

`flatMap` rõ nghĩa khi một phần tử nguồn tương ứng với 0/nhiều phần tử kết quả. Nhưng nếu đang có một danh sách lồng nhau cực lớn, việc `flatMap` còn phụ thuộc đặc điểm nguồn và terminal operation; không kết luận nó luôn nhanh hơn vòng lặp lồng nhau. Khi chỉ có nhu cầu rõ ràng và không cần nhiều biến trung gian, nó thường cải thiện khả năng đọc.

## 13. Ranh giới của hàm thuần và side effect

Trong thiết kế theo hàm, lambda trong `map`, `filter`, `sorted` nên **stateless, non-interfering**. Dùng chúng để đẩy dữ liệu ra ngoài làm code ngắn nhưng rất dễ sai:

~~~java
// Sai về an toàn đồng thời khi dùng parallel:
List<String> shared = new ArrayList<>();
names.parallelStream().forEach(shared::add);
~~~

`ArrayList` không an toàn khi nhiều thread thêm đồng thời. Một pipeline đúng hơn khi cần danh sách:

~~~java
List<String> selected = names.parallelStream()
        .filter(s -> !s.isBlank())
        .toList();
~~~

Hai đoạn minh họa nằm trong phương thức với `names: List<String>` và import phù hợp. `toList()` thu kết quả theo cơ chế của Stream; với nguồn ordered nó bảo toàn encounter order, không đồng nghĩa lambda được chạy tuần tự.

**Side effect cũng ảnh hưởng khả năng đọc.** Một mapper vừa gọi database vừa sửa cache vừa trả chuỗi khiến người đọc khó biết chức năng và chi phí thực. Thay bằng các pha độc lập: lấy dữ liệu, biến đổi thuần, rồi thực hiện I/O được kiểm soát.

Không phụ thuộc `peek` để thực thi nghiệp vụ: nó chủ yếu hữu ích khi quan sát và không bảo đảm được gọi một lần cho mỗi phần tử trong mọi cấu trúc pipeline/terminal operation, do tối ưu hóa và short-circuit.

## 14. `parallel()` không phải tối ưu hóa miễn phí

Một pipeline ngắn nhưng có `.parallel()` có thể bị **chậm hơn** do:

- Chi phí tách dữ liệu qua `Spliterator`;
- Lên lịch và phối hợp task trên fork/join;
- Kết hợp kết quả cục bộ của `reduce` hoặc `collect`;
- Các thao tác có trạng thái như `sorted`, `distinct`, `limit` trên ordered stream;
- Tranh chấp bộ nhớ, cache, GC và contention;
- I/O chặn trong `map` làm worker phải chờ, gây nghẽn pool chung.

`parallel()` thường đáng thử khi nguồn **đủ lớn, dễ chia** (mảng, `ArrayList`), phép tính **CPU-bound** và độc lập, combiner rẻ, không có side effect hay yêu cầu thứ tự khó xử lý. Nhưng vẫn phải **benchmark với dữ liệu thực**.

Nếu pipeline xử lý HTTP/JDBC/file I/O chặn, ưu tiên thiết kế giới hạn số thao tác đồng thời, quản lý timeout và cân nhắc executor I/O/async thay vì bọc tùy tiện bằng `parallelStream()`. Mã ngắn như `ids.parallelStream().map(api::fetch).toList()` có thể gây số lời gọi đồng thời khó kiểm soát.

## 15. Tính dễ đọc khi sắp xếp và nhóm dữ liệu

Với nhiều khóa sắp xếp, `Comparator.comparing(...).thenComparing(...)` thường dễ đọc hơn lambda so sánh tay nhiều nhánh. Nhưng khi khóa có thể null, code ngắn dạng `Comparator.comparing(Person::department)` có thể ném `NullPointerException`.

Minh họa comparator có chính sách rõ:

~~~java
// Minh họa với Person::department trả String nullable
// và Person::age trả int:
Comparator<Person> comparator = Comparator.comparing(
        Person::department,
        Comparator.nullsLast(Comparator.naturalOrder()))
        .thenComparingInt(Person::age);
~~~

Đoạn này giả định **Person không null** và đã import `Comparator`. Bọc `nullsLast` trên comparator của **khóa** khác với bọc trên comparator của **cả Person**. Khi dữ liệu nullable hoặc có nhiều khóa, một vài dòng thêm vào để mô tả đúng chính sách null là đáng giá.

`Collectors.groupingBy(classifier)` cho `Map<K,List<T>>` có thể rõ ý hơn viết vòng lặp tự quản lý `computeIfAbsent`, đặc biệt với downstream collector như `summingInt`, `mapping` hoặc `counting`. Tuy nhiên, nếu source rỗng hoặc khóa null, kiểm tra hợp đồng của collector; không mặc nhiên suy ra nó chấp nhận null key hoặc tạo nhóm chưa xuất hiện.

## 16. Bài thực hành: báo cáo khách hàng có tổng chi tiêu theo mã

Bài toán: mỗi đơn hàng có một mã khách và giá trị `amount` kiểu `long`. Hãy tạo báo cáo tổng giá trị theo khách, sắp theo mã khách, **không duyệt lặp** để tìm tổng cho từng khách.

Tạo file `FunctionalReportDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class FunctionalReportDemo {
    record Order(String customerId, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("C2", 40L),
                new Order("C1", 20L),
                new Order("C2", 15L),
                new Order("C1", 5L));

        Map<String, Long> totalByCustomer = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customerId,
                        TreeMap::new,
                        Collectors.summingLong(Order::amount)));

        totalByCustomer.forEach((id, amount) ->
                System.out.println(id + "=" + amount));
    }
}
~~~

~~~bash
javac --release 17 FunctionalReportDemo.java
java FunctionalReportDemo
~~~

Kết quả:

~~~text
C1=25
C2=55
~~~

`groupingBy` phân nhóm theo `customerId`, `summingLong` cộng amount cho từng nhóm, còn `TreeMap::new` làm thứ tự duyệt khóa xác định trong ví dụ. Cách này diễn đạt rõ cấu trúc đầu ra `Map<String,Long>` mà không cần gọi `orders.stream().filter(...)` riêng **cho mỗi khách**.

Cần lưu ý `summingLong` và phép cộng `long` vẫn có nguy cơ overflow nếu số liệu vượt miền `long`. Với tiền tệ cần chính xác/kiểm tra tràn, chọn mô hình giá trị phù hợp. Nếu không cần sắp thứ tự khóa, có thể bỏ `TreeMap` và dùng overload `groupingBy` đơn giản hơn, tránh chi phí duy trì cây sắp xếp.

## 17. Đo hiệu năng đúng cách thay vì tối ưu theo trực giác

Không nên kết luận “Stream nhanh hơn vòng lặp” hoặc “vòng lặp nhanh hơn Stream” từ một lần đo `System.nanoTime()`. Kết quả bị ảnh hưởng bởi JIT, warmup, GC, CPU throttling, escape analysis, dữ liệu đầu vào, tính nóng/lạnh của cache và tối ưu hóa của compiler/JVM.

Nếu hiệu năng quan trọng:

1. Xác định **đầu vào đại diện**: kích thước, tỷ lệ lọc, phân bố khóa trùng, số lần chạy, dữ liệu nullable.
2. Xác định **tính đúng tương đương** giữa các phương án (cùng kết quả, cùng chính sách thứ tự/null/overflow).
3. Đo **end-to-end** nếu chi phí I/O hoặc network đáng kể.
4. Dùng **JMH** cho microbenchmark CPU: warmup, nhiều iteration, benchmark state, fork và cách tiêu thụ kết quả phù hợp.
5. Quan sát **allocation, GC, latency p95/p99 và throughput**, không chỉ thời gian một lời gọi.
6. Chỉ giữ tối ưu nếu lợi ích đáng kể, ổn định và không làm code trở nên khó hiểu quá mức.

Đừng tạo `List` trong mỗi lượt benchmark của riêng phần thuật toán nếu một ứng viên không phải trả cùng chi phí khởi tạo đó. Đừng so các cách viết khác ý nghĩa hoặc loại bỏ các phần tử khác nhau. Với I/O, microbenchmark một hàm `map` không đủ để hiểu chi phí backend, connection pool và retry.

Độ phức tạp thuật toán thường quan trọng hơn micro-tuning: chuyển `O(n × m)` sang tra cứu Set `O(n + m)` có thể đem lại lợi ích lớn hơn việc thay method reference bằng lambda hoặc rút bớt một phép gọi nhỏ.

## 18. Khi nào nên giữ vòng lặp thay vì tiếp tục nối Stream?

**Vòng lặp rõ ràng** có thể tốt hơn khi:

- Có trạng thái nghiệp vụ cần thay đổi từng bước, nhiều nhánh `break/continue` khó diễn đạt qua Stream;
- Cần xử lý ngoại lệ checked hoặc rollback tài nguyên theo từng phần tử;
- Cần thu nhiều kết quả tương quan mà Collector tùy chỉnh sẽ phức tạp;
- Thao tác đòi tương tác thứ tự tuần tự rõ ràng và side effect được kiểm soát;
- Profiling xác nhận một đoạn hot path quá nhỏ chịu overhead quan trọng của pipeline.

**Stream rõ ràng** thường phù hợp khi:

- Chuỗi nguồn → lọc → chuyển đổi → thu kết quả có tên bước dễ hiểu;
- Hàm xử lý có tính thuần, không dựa vào trạng thái mutable ngoài;
- Có API chuyên biệt như `anyMatch`, `findFirst`, `mapToLong`, `groupingBy`;
- Cần tính composability và dễ kiểm thử từng phép biến đổi.

Vòng lặp không “kém functional” theo nghĩa chất lượng phần mềm; mô hình tư duy hàm hữu ích ở cả hai cách: **hạn chế side effect, tách logic thuần, đặt tên ý nghĩa và quản lý dữ liệu nhất quán**.

## 19. Lỗi thường gặp cần tránh

1. **Tối thiểu hóa dòng code bằng mọi giá:** một lambda dài, chứa nhiều side effect khó bảo trì hơn vài helper có tên.
2. **Tách quá nhiều phương thức vụn:** nhảy qua 5 phương thức chỉ để đọc `x -> x.getValue()` gây mất mạch logic.
3. **Dùng Stream lồng trong `filter` để tìm membership:** dễ biến `O(n)` thành `O(n × m)`; preindex bằng `Set` khi phù hợp.
4. **Gọi database/network trong mỗi `map`:** N+1 I/O có thể thống trị thời gian thực thi.
5. **Thu `toList()` rồi stream lại không cần thiết:** thêm bộ nhớ và lượt duyệt; nối tiếp nếu chỉ dùng một lần.
6. **Boxing/unboxing đi vòng:** `int → Integer → int` trong pipeline số lớn có thể gây overhead.
7. **`sorted` hoặc `distinct` để “đẹp” mà không cần nghiệp vụ:** tốn CPU/bộ nhớ và có thể đổi ý nghĩa.
8. **Dùng `count()` hay `toList()` để trả lời câu hỏi tồn tại:** `anyMatch` có thể dừng sớm.
9. **Dùng `Optional.get()` khi không chắc có giá trị:** có thể ném `NoSuchElementException` trên nguồn rỗng.
10. **Giấu side effect trong `peek`, `map`, `filter`:** gây phụ thuộc vào cách đánh giá lazy/short-circuit.
11. **Gọi `parallel()` như tối ưu hóa mặc định:** scheduling, combiner, boxing, stateful operations và I/O có thể làm chậm hơn.
12. **Tưởng `Stream.toList()` là một List mutable:** trên Java 17 danh sách kết quả không hỗ trợ sửa cấu trúc.
13. **Thay đổi thứ tự `filter`, `map`, `distinct` tùy tiện:** có thể khác kiểu và ngữ nghĩa kết quả.
14. **Tái sử dụng một đối tượng Stream:** terminal operation tiêu thụ stream; phải tạo stream mới từ nguồn nếu cần xử lý lại.
15. **Bỏ qua chính sách null/duplicate của collector:** `toMap` có thể ném lỗi khi khóa trùng, `groupingBy` không tự chấp nhận null key.
16. **Chạy benchmark một lần trên dữ liệu quá nhỏ:** không phản ánh JIT, GC, saturation hay workload thực.

## 20. Checklist code review theo ba trục

Trước khi hoàn thiện một pipeline theo hàm, hãy tự hỏi:

- **Ý nghĩa:** người khác có thể đọc tên các bước và hiểu yêu cầu đầu ra không?
- **Độ ngắn:** dòng code nào thật sự thừa, dòng nào cần giữ để giải thích một quyết định nghiệp vụ?
- **Trạng thái:** lambda có thuần, stateless, không thay đổi nguồn hoặc state dùng chung không?
- **Kiểu:** sau mỗi `map`/`flatMap`/primitive conversion, kiểu phần tử còn là gì?
- **Thuật toán:** có quét lặp một danh sách ở mỗi phần tử, truy vấn I/O lặp hoặc sort thừa không?
- **Bộ nhớ:** có tạo List/Map trung gian hoặc boxing không cần thiết không?
- **Dừng sớm:** mục tiêu là tất cả phần tử hay chỉ tìm một phần tử phù hợp?
- **Nguồn:** có thể rỗng, null, duplicate, rất lớn, vô hạn hoặc dùng một lần không?
- **Thứ tự:** cần encounter order không, kết quả có phụ thuộc `findFirst`/`sorted` không?
- **Chi phí:** hiệu năng đã được đo đúng trên workload đại diện chưa? Tối ưu có đáng giá không?
- **Thiết kế:** có phương thức/collector Java chuẩn rõ hơn mà không đổi ý nghĩa không?
- **Kiểm thử:** có kiểm tra empty, một phần tử, dữ liệu lớn, khóa trùng, giá trị biên và xử lý lỗi chưa?

**Ghi nhớ:** Viết code theo hàm tốt không có nghĩa “pipeline càng dài hoặc càng ngắn càng tốt”. Một thiết kế chất lượng làm rõ **ý định nghiệp vụ**, giữ các phép biến đổi đơn giản, nhận diện chi phí **duyệt lại, sắp xếp, boxing, I/O và parallel**, và chỉ tối ưu sau khi hiểu thuật toán và đo đúng điểm nghẽn. **Ngắn vừa đủ, dễ đọc trước, tối ưu có chứng cứ.**
