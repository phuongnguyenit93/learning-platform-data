# Kiểm thử khóa, null và dữ liệu trùng lặp khi phân nhóm Java Stream

`Collectors.groupingBy(...)` là công cụ phân nhóm dữ liệu còn được hỗ trợ trong Java hiện hành. Khi áp dụng vào ứng dụng thực tế, ba nhóm lỗi dễ lọt qua bài kiểm tra đơn giản nhất là **khóa phân nhóm không đúng**, **giá trị null chưa được xử lý** và **dữ liệu bị trùng**. Bài này tập trung vào việc **thiết kế ca kiểm thử và xác minh kết quả** của pipeline phân nhóm, thay vì chỉ viết một lời gọi `groupingBy` chạy được với dữ liệu đẹp.

Mục tiêu sau bài:

1. Phân biệt phần tử nguồn, khóa do classifier sinh ra và danh sách phần tử của mỗi nhóm.
2. Kiểm thử cách khóa được chuẩn hóa, trường hợp hai bản ghi thuộc cùng nhóm và trường hợp hai khóa có vẻ giống nhau nhưng thực chất khác nhau.
3. Chủ động xác định chính sách cho **phần tử null** và **khóa null**, rồi kiểm tra cả nhánh lỗi lẫn nhánh xử lý hợp lệ.
4. Phân biệt **trùng khóa nhóm**, **trùng ID nghiệp vụ** và **trùng toàn bộ bản ghi**; lựa chọn giữ, gộp, loại hay từ chối dữ liệu trùng theo yêu cầu.
5. Viết những phép kiểm không phụ thuộc vào thứ tự của `HashMap` hoặc chi tiết triển khai không được API bảo đảm.

## 1. Nắm đúng hợp đồng phân nhóm

Ví dụ cơ bản:

~~~java
Map<String, List<Order>> byCategory = orders.stream()
        .collect(Collectors.groupingBy(order -> order.category));
~~~

Đây là **mảnh mã minh họa**, giả sử đã khai báo `Order`, `orders` và các import tương ứng. Hàm `order -> order.category` được gọi là **classifier**. Nó biến một `Order` thành một khóa `String`; các phần tử có khóa bằng nhau được đặt trong cùng danh sách. `groupingBy(classifier)` tương đương về ý nghĩa với `groupingBy(classifier, toList())`.

Ba yếu tố cần tách biệt khi kiểm thử:

- **Giá trị phần tử:** một object `Order`. Object này có thể chứa các trường null, hoặc chính object có thể là null trong nguồn.
- **Khóa phân nhóm:** kết quả từ classifier, ví dụ `"north"`. Đây là khóa của `Map`, và trong `groupingBy` hiện hành, classifier trả `null` sẽ gây `NullPointerException`.
- **Kết quả downstream:** với `toList()` là danh sách các bản ghi thuộc nhóm; với `counting()` là số phần tử của nhóm; với `summingInt(...)` là tổng của một trường.

`groupingBy` mặc định tạo một `Map` nhưng **không bảo đảm loại Map cụ thể, thứ tự duyệt khóa, khả năng sửa đổi hay an toàn luồng**. Vì thế một bài test đúng nên so sánh **tập khóa, số lượng, nội dung và các phép tổng hợp**, thay vì cố định chuỗi `Map.toString()` từ một `HashMap` bất kỳ.

Khi cần thứ tự khóa xác định để hiển thị hoặc làm ví dụ, sử dụng overload nhận `mapFactory`:

~~~java
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(
                order -> order.category,
                TreeMap::new,
                Collectors.toList()
        ));
~~~

Đây cũng là mảnh mã minh họa phụ thuộc vào `Order` và `orders`. `TreeMap::new` sắp khóa theo thứ tự tự nhiên của `String`. Việc chọn Map có thứ tự **không tự sửa lỗi khóa hoặc dữ liệu trùng**.

## 2. Ma trận kiểm thử tối thiểu

| Trường hợp | Dữ liệu đầu vào | Điều cần kiểm tra |
|---|---|---|
| Nguồn rỗng | Không có phần tử | Kết quả `groupingBy` là Map rỗng |
| Một nhóm | Hai đơn hàng cùng vùng | Map chỉ có một khóa, nhóm chứa đủ hai đơn |
| Nhiều nhóm | `north` và `south` | Mỗi phần tử thuộc đúng nhóm |
| Khác chữ hoa/thường | `North`, `NORTH`, `north` | Có gộp hay tách tùy chính sách chuẩn hóa |
| Khoảng trắng | `" North "` và `"north"` | Quy tắc trim/normalize áp dụng nhất quán |
| Null ở khóa | `category == null` | Phải xử lý trước khi classifier trả null, hoặc chủ động kiểm tra exception |
| Null ở phần tử | Danh sách có một `Order` null | Lọc, từ chối hoặc xử lý có chủ đích trước khi truy cập thuộc tính |
| Khóa nhóm trùng | Nhiều đơn cùng category | `groupingBy(..., toList())` giữ nhiều phần tử trong cùng nhóm |
| ID nghiệp vụ trùng | Hai đơn có cùng `id` | Kiểm tra chính sách giữ nguyên, gộp hoặc báo trùng |
| Toàn bản ghi trùng | Cùng dữ liệu xuất hiện hai lần | Test có nhận diện đúng duplicate theo các trường nghiệp vụ không |
| Khóa rỗng sau chuẩn hóa | `"   "` | Được gán nhóm thiếu hoặc bị từ chối rõ ràng |
| Null trong thống kê | Bản ghi thiếu số lượng/giá | Không tự âm thầm cộng sai hoặc ném lỗi không rõ nguyên nhân |

Ma trận trên là điểm xuất phát, **không phải một chính sách duy nhất cho mọi hệ thống**. Chẳng hạn dữ liệu sự kiện có thể cố ý lặp một ID để thể hiện các lượt phát sinh; ngược lại bảng đơn hàng chuẩn có thể yêu cầu ID duy nhất. Phải xác định quy tắc nghiệp vụ rồi mới khẳng định đầu ra mong đợi.

## 3. Kiểm thử khóa phân nhóm: so sánh, chuẩn hóa và va chạm

### 3.1. Hai chuỗi khác ký tự là hai khóa khác nhau

Nếu classifier trả trực tiếp `category` và không chuẩn hóa, `"North"`, `"north"` và `" North "` là ba khóa `String` khác nhau theo `String.equals`. `Map` không tự hiểu rằng chúng cùng một vùng.

Khi yêu cầu nghiệp vụ coi chúng là cùng một nhóm, hãy thiết kế **một hàm sinh khóa duy nhất**:

~~~java
static String categoryKey(Order order) {
    if (order.category == null) {
        return "<unknown>";
    }
    String key = order.category.trim().toLowerCase(Locale.ROOT);
    return key.isEmpty() ? "<unknown>" : key;
}
~~~

Đây là phương thức minh họa, cần một lớp `Order` có trường `category` và import `java.util.Locale`. Hàm này chọn chính sách: null hoặc chuỗi chỉ có khoảng trắng đưa vào nhóm `"<unknown>"`; còn chữ thường/chữ hoa được gộp sau `trim` và `toLowerCase(Locale.ROOT)`.

**Điều cần kiểm tra:**

- `" North "` và `"NORTH"` cùng sinh khóa `"north"`.
- `"South"` sinh khóa `"south"`, **không bị gộp vào `"north"`**.
- Null và chuỗi trắng được đưa về `"<unknown>"`, không tạo khóa null.
- Nếu giá trị thực có thể đúng bằng `"<unknown>"`, nó sẽ va chạm với nhóm thiếu. Trong sản phẩm thật nên dùng một **enum/kiểu khóa riêng**, hoặc một nhãn đặc biệt được hệ thống đặt trước và cấm người dùng nhập.

`trim()` chỉ giải quyết cách xử lý khoảng trắng theo quy tắc của phương thức đó; nó không phải bộ chuẩn hóa Unicode đầy đủ. `String.strip()` từ Java 11 xử lý khoảng trắng theo Unicode tốt hơn trong nhiều trường hợp và vẫn là API hiện hành. Chọn quy tắc đúng loại dữ liệu và kiểm thử cả ký tự dấu/Unicode nếu ứng dụng hỗ trợ. Với mã định danh có yêu cầu bảo toàn chữ hoa, **không tự động lowercase**; quy tắc trên chỉ là ví dụ cho tên vùng có so sánh không phân biệt chữ hoa.

### 3.2. Khóa nhóm không đồng nhất với ID đơn hàng

Đơn `A-01` và `A-02` có thể cùng vùng `north` và phải nằm trong **cùng một nhóm**, dù ID khác nhau. Ngược lại, hai dòng cùng ID `A-02` có thể là bản ghi bị nhập lặp; `groupingBy(categoryKey)` vẫn đặt **cả hai dòng vào danh sách**, vì Collector mặc định không loại trùng.

Hãy đặt các assert khác nhau cho:

- Số lượng **khóa nhóm**: `grouped.keySet().size()`.
- Số lượng **bản ghi trong nhóm**: `grouped.get("north").size()`.
- Số lượng **ID phân biệt**: `stream.map(order -> order.id).distinct().count()`.
- Số lần một ID xuất hiện: lọc `order.id.equals(id)` rồi đếm.

Chỉ kiểm tra `Map.size()` sẽ không phát hiện mất hoặc nhân đôi bản ghi trong một nhóm.

## 4. Kiểm thử null: phần tử nguồn khác khóa classifier

### 4.1. Null ở trường dùng làm khóa

Đoạn dưới đây cố tình tạo khóa null:

~~~java
Stream.of(new Order("X-01", null, 1))
        .collect(Collectors.groupingBy(order -> order.category));
~~~

Đây là **phản ví dụ chạy trong chương trình có lớp `Order` và import thích hợp**. Với JDK hiện hành, `Collectors.groupingBy` không chấp nhận kết quả classifier là null và ném `NullPointerException`. Điều đó vẫn đúng nếu `HashMap` có khả năng chứa khóa null: **khả năng của một loại Map không thay thế hợp đồng của Collector**.

Có ba chính sách hợp lệ tùy ứng dụng, và mỗi chính sách phải có test:

1. **Từ chối dữ liệu thiếu khóa:** kiểm tra điều kiện rồi ném lỗi dữ liệu rõ ràng trước khi phân nhóm.
2. **Loại bản ghi thiếu khóa:** `filter(order -> order.category != null)`, nhưng chỉ khi nghiệp vụ cho phép bỏ dòng.
3. **Gán nhóm thiếu riêng:** classifier trả một khóa không null như `"<unknown>"` hoặc một giá trị enum `UNKNOWN`.

Không nên mặc định chính sách thứ hai vì bỏ dữ liệu có thể làm sai số lượng, doanh thu và thống kê.

### 4.2. Null ở chính phần tử Stream

~~~java
Stream.<Order>of((Order) null)
        .collect(Collectors.groupingBy(order -> order.category));
~~~

Đoạn này gây `NullPointerException` **ngay khi lambda truy cập `order.category`**. Nó khác trường hợp object tồn tại nhưng field `category == null`. Muốn bỏ null element có chủ ý:

~~~java
stream.filter(Objects::nonNull)
        .collect(Collectors.groupingBy(GroupingTests::categoryKey));
~~~

Đây là mẫu minh họa: cần `stream`, lớp `GroupingTests` và các import tương ứng. Nếu null element là lỗi nghiêm trọng, thay việc filter bằng bước kiểm tra dữ liệu và báo lỗi để không mất bản ghi âm thầm.

**Hai test riêng** cho null field và null element giúp biết exception xuất phát từ quy tắc collector hay từ chính classifier. Không dựa vào chuỗi thông báo exception vì thông báo có thể thay đổi giữa các JDK; kiểm tra loại exception và điều kiện gây lỗi.

### 4.3. Null ở giá trị downstream

Ngay cả khi khóa không null, các trường khác trong phần tử có thể null. Ví dụ `Collectors.summingInt(order -> order.quantity)` có thể thất bại nếu `quantity` là `Integer` nullable và bị unbox. Hãy kiểm tra đầu vào, chọn cách xử lý thiếu dữ liệu (báo lỗi, bỏ, hay dùng giá trị mặc định có cơ sở), và viết test xác nhận tổng đúng. Đừng giả định `groupingBy` sẽ tự xử lý tất cả null trong object.

## 5. Kiểm thử dữ liệu trùng lặp

### 5.1. Trùng khóa nhóm là hành vi bình thường

~~~java
Map<String, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.counting()
        ));
~~~

Mảnh mã dùng lại `Order` và `orders` ở ví dụ giả định, trong đó `Order::category` phải tồn tại như phương thức và trả khóa không null. `counting()` đếm **số phần tử đầu vào của nhóm**, không đếm số ID duy nhất. Hai bản ghi cùng khóa sẽ làm kết quả tăng thêm hai đơn vị.

Nếu nguồn có hai đơn hàng cùng vùng, việc tạo hai phần tử trong danh sách là đúng. **Trùng khóa nhóm không phải lỗi** trừ khi yêu cầu nghiệp vụ nói rằng mỗi nhóm chỉ được có một giá trị.

### 5.2. Trùng ID khi chuyển thành Map đơn trị

`Collectors.toMap(keyMapper, valueMapper)` khác `groupingBy`: một khóa phải ánh xạ tới **một giá trị**. Nếu hai phần tử có khóa `String` bằng nhau theo `equals`, overload hai tham số của `toMap` ném `IllegalStateException`.

~~~java
orders.stream()
        .collect(Collectors.toMap(order -> order.id, Function.identity()));
~~~

Đoạn trên là ví dụ kiểm tra **phải ném exception nếu ID trùng**, không phải cách tạo Map an toàn khi dữ liệu có thể trùng. Có thể dùng overload ba tham số nếu bài toán cho phép một chính sách gộp rõ ràng:

~~~java
Map<String, Integer> unitsById = orders.stream()
        .collect(Collectors.toMap(
                order -> order.id,
                order -> order.units,
                Integer::sum
        ));
~~~

Khi có hai dòng ID `A-02`, mỗi dòng `units=3`, kết quả cho khóa ấy là `6`. **Chỉ dùng gộp bằng phép cộng nếu hai dòng thể hiện hai giao dịch hợp lệ**. Nếu đó là một bản ghi bị gửi lại hai lần do retry, cộng `6` có thể làm sai kết quả nghiệp vụ; cần deduplicate theo event ID/khóa idempotency, hoặc phát hiện và từ chối dòng trùng theo chính sách.

### 5.3. `distinct()` không biết ID nghiệp vụ

`Stream.distinct()` dùng `Object.equals(...)` để xác định phần tử bằng nhau, không tự hiểu thuộc tính `id`. Nếu lớp `Order` không override `equals/hashCode`, hai object có cùng ID vẫn có thể được coi là khác nhau:

~~~java
long differentIds = orders.stream()
        .map(order -> order.id)
        .distinct()
        .count();
~~~

Mảnh mã này đếm ID phân biệt vì nó gọi `distinct()` trên `String`, vốn có so sánh theo nội dung. Nhưng **lọc ID khác nhau rồi tạo lại object nào** là quyết định khác: nếu cần chọn “bản ghi mới nhất theo ID”, phải định nghĩa timestamp, chính sách thắng/thua và xử lý va chạm có thể kiểm thử.

`Collectors.toSet()` cũng dùng `equals/hashCode` của các phần tử khi xác định trùng. Chuyển `List<Order>` thành `Set<Order>` không tự loại các object cùng ID nếu định nghĩa equality của lớp không phản ánh ID; thêm nữa, Set làm mất số lần một sự kiện xuất hiện.

## 6. Chương trình kiểm thử hoàn chỉnh, chạy được

Tạo file **`GroupingEdgeCasesTest.java`**. Chương trình không yêu cầu thư viện test ngoài JDK: tự dùng `check(...)` để ném `AssertionError` khi điều kiện sai và `expectThrows(...)` để xác minh exception. Chạy được trên JDK 17+ (các API trong chương trình đều có từ Java 8).

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class GroupingEdgeCasesTest {
    static final class Entry {
        final String id;
        final String category;
        final int units;

        Entry(String id, String category, int units) {
            this.id = id;
            this.category = category;
            this.units = units;
        }
    }

    static String categoryKey(Entry entry) {
        if (entry.category == null) {
            return "<unknown>";
        }
        String key = entry.category.trim()
                .toLowerCase(Locale.ROOT);
        return key.isEmpty() ? "<unknown>" : key;
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectThrows(
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    "Wrong exception: " + actual, actual);
        }
        throw new AssertionError(
                "Expected: " + expected.getSimpleName());
    }

    public static void main(String[] args) {
        List<Entry> rows = Arrays.asList(
                new Entry("A-01", " North ", 2),
                new Entry("A-02", "north", 3),
                new Entry("B-01", null, 1),
                new Entry("C-01", "   ", 5),
                new Entry("A-02", "NORTH", 3),
                new Entry("D-01", "South", 2),
                null
        );

        // 1. Object tồn tại nhưng classifier trả khóa null.
        expectThrows(NullPointerException.class, () ->
                Stream.of(new Entry("bad", null, 1))
                        .collect(Collectors.groupingBy(
                                e -> e.category)));

        // 2. Chính phần tử nguồn là null.
        expectThrows(NullPointerException.class, () ->
                Stream.<Entry>of((Entry) null)
                        .collect(Collectors.groupingBy(
                                e -> e.category)));

        // 3. Chính sách: lọc phần tử null, nhóm field thiếu.
        Map<String, List<Entry>> groups = rows.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.groupingBy(
                        GroupingEdgeCasesTest::categoryKey,
                        TreeMap::new,
                        Collectors.toList()
                ));

        check(groups.keySet().equals(new TreeSet<>(
                Arrays.asList("<unknown>", "north", "south"))),
                "Unexpected group keys");

        check(groups.get("north").size() == 3,
                "North must contain three rows");
        check(groups.get("<unknown>").size() == 2,
                "Missing categories must be grouped");
        check(groups.get("south").size() == 1,
                "South must contain one row");

        // 4. ID lặp vẫn được giữ nguyên trong List của nhóm.
        check(groups.get("north").stream()
                        .filter(e -> e.id.equals("A-02"))
                        .count() == 2,
                "Repeated ID must remain in group");

        // 5. Đếm ID phân biệt theo String.equals().
        long distinctIds = rows.stream()
                .filter(Objects::nonNull)
                .map(e -> e.id)
                .distinct()
                .count();

        check(distinctIds == 5, "Expected five unique IDs");

        // 6. toMap hai tham số phải báo trùng khóa ID.
        expectThrows(IllegalStateException.class, () ->
                rows.stream()
                        .filter(Objects::nonNull)
                        .collect(Collectors.toMap(
                                e -> e.id,
                                Function.identity()
                        )));

        // 7. Chỉ cộng khi chính sách nghiệp vụ cho phép.
        Map<String, Integer> unitsById = rows.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toMap(
                        e -> e.id,
                        e -> e.units,
                        Integer::sum
                ));
        check(unitsById.get("A-02") == 6,
                "Duplicate ID should sum to six");

        System.out.println("Groups: " + groups.keySet());
        System.out.println("North count: "
                + groups.get("north").size());
        System.out.println("Unknown count: "
                + groups.get("<unknown>").size());
        System.out.println("Distinct IDs: " + distinctIds);
        System.out.println("A-02 units: " + unitsById.get("A-02"));
        System.out.println("PASS: key, null and duplicate checks");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GroupingEdgeCasesTest.java
java GroupingEdgeCasesTest
~~~

Stdout:

~~~text
Groups: [<unknown>, north, south]
North count: 3
Unknown count: 2
Distinct IDs: 5
A-02 units: 6
PASS: key, null and duplicate checks
~~~

Nếu một `check` thất bại hoặc một `expectThrows` không nhận exception đúng loại, chương trình ném `AssertionError` và **không in dòng PASS cuối cùng**. `check` được viết riêng thay vì dùng toán tử `assert` của Java để tránh phụ thuộc vào cờ JVM `-ea`; vì mặc định Java có thể tắt `assert`. Trong bộ kiểm thử thực tế, chuyển từng trường hợp thành một test độc lập bằng JUnit Jupiter `@Test`, `assertEquals` và `assertThrows` để dễ định vị ca hỏng.

**Điều chương trình đã kiểm chứng:**

- Null field dẫn đến null khóa trong classifier và null element đều được bắt thành hai lỗi độc lập.
- Dữ liệu đầu vào có bảy vị trí, một vị trí là null. Sau `filter(Objects::nonNull)` còn **sáu bản ghi**.
- `" North "`, `"north"`, `"NORTH"` cùng thuộc nhóm `north` với **ba bản ghi**; `null` và chuỗi toàn khoảng trắng vào nhóm `<unknown>` có **hai bản ghi**; `south` có một.
- Hai lần xuất hiện ID `A-02` được giữ trong danh sách của nhóm; `distinct()` trên ID phân biệt cho **năm giá trị**.
- `toMap` không có merge function từ chối ID trùng. Phiên bản có `Integer::sum` cho ID `A-02` kết quả **6** đúng theo chính sách minh họa.

Việc dùng `TreeMap` nhằm cố định thứ tự khi in `groups.keySet()`. Các kiểm tra đúng/sai chính dựa trên **tập khóa và số lượng**, không dựa vào thứ tự không được bảo đảm của Map mặc định.

## 7. Thiết kế kiểm thử có giá trị lâu dài

### 7.1. Kiểm tra bất biến thay vì chuỗi hiển thị

Với `groupingBy(classifier, toList())` trên nguồn đã xử lý null theo chính sách, các bất biến hữu ích là:

- **Tổng số phần tử trong các nhóm** bằng số phần tử thực sự đưa vào collector. Nếu cố tình lọc một null, số lượng đầu ra phải giảm **đúng một**, không hơn.
- Mỗi phần tử trong một nhóm phải được classifier xác định ra **đúng khóa của nhóm đó** (sau chuẩn hóa).
- Không xuất hiện khóa null. Nếu bài toán coi khóa rỗng là lỗi, không được để khóa `""` xuất hiện ngầm.
- Những bản ghi có cùng khóa phân nhóm phải được gộp, còn bản ghi khác khóa phải tách đúng.
- Nếu cần loại trùng theo ID, tổng số bản ghi sau xử lý phải bằng số **ID phân biệt theo quy tắc nghiệp vụ**; nếu không được loại trùng, số bản ghi cần được giữ nguyên.

Có thể kiểm tổng số bản ghi bằng:

~~~java
long totalGroupedRows = groups.values().stream()
        .mapToLong(List::size)
        .sum();
~~~

Đây là mảnh mã giả sử `groups` đã tồn tại như trong chương trình trên; giá trị phải là `6`. Một phép kiểm này phát hiện được nhiều lỗi mất bản ghi khi filter hoặc chuyển sai sang Map đơn trị.

### 7.2. Không dùng thứ tự HashMap làm tiêu chí test

Không nên viết test so sánh một chuỗi cố định do `HashMap.toString()` sinh ra hoặc lấy `map.entrySet().iterator().next()` để đoán nhóm đầu tiên. `groupingBy` không bảo đảm Map trả về là `HashMap` hay giữ một thứ tự nào đó. Dùng:

- `assertEquals(expectedKeySet, actual.keySet())`.
- `assertEquals(expectedCount, actual.get(key).size())`.
- So sánh phần tử theo ID hoặc so sánh `Set` nếu thứ tự danh sách không quan trọng.
- Chỉ dùng `TreeMap`/`LinkedHashMap` khi bài toán thực sự yêu cầu thứ tự; kiểm thử đúng **hợp đồng của Map bạn đã chọn**.

### 7.3. Trường hợp dữ liệu song song

`groupingBy` cũng dùng được trong parallel Stream, nhưng không phải Collector concurrent. Combiner có thể gộp các Map từng nhánh, nên hiệu năng phụ thuộc số nhóm và cách chia dữ liệu. `groupingByConcurrent` là Collector concurrent và **unordered**; không dùng khi logic cần dựa vào encounter order của từng nhóm. Điều quan trọng trong test là **tập khóa và dữ liệu của các nhóm** vẫn đúng, chứ không phải thứ tự callback hay Map ngẫu nhiên.

Với cùng đầu vào có thứ tự, có thể so sánh Map kết quả của stream tuần tự và parallel sau khi chuyển mỗi nhóm thành **bảng đếm ID**. Cách này bảo toàn thông tin bản ghi trùng, không bị `Set` làm mất số lượng:

~~~java
Map<String, Long> idCounts(List<Entry> input) {
    return input.stream().collect(Collectors.groupingBy(
            e -> e.id,
            Collectors.counting()
    ));
}
~~~

Đây là **mẫu phương thức** dùng lớp `Entry` ở phần 6. Nếu gọi cho các phần tử còn null, phải lọc null trước theo chính sách. Việc so sánh count theo ID có ý nghĩa ngay cả khi hai kết quả có thứ tự danh sách khác nhau.

### 7.4. Không bịa identity khi không có dữ liệu

Nếu nguồn sau filter hoàn toàn rỗng, `Collectors.groupingBy` trả **Map rỗng**, không tự tạo nhóm `"<unknown>"`. Nhóm `"<unknown>"` trong ví dụ xuất hiện vì **có hai bản ghi thực** được classifier trả về khóa ấy. Đây là hai tình huống khác nhau và nên có hai ca kiểm thử riêng. Nếu cần hiển thị tất cả nhóm chuẩn ngay cả khi chưa có dữ liệu, phải bổ sung các nhóm đó một cách tường minh sau quá trình thu thập.

## 8. Lỗi phổ biến và cách phát hiện

**Lỗi 1 — Chỉ kiểm số khóa.** Map có đủ `north`, `south` nhưng thiếu mất một đơn hàng; test `keySet` vẫn pass. Thêm assert kích thước từng nhóm và tổng số phần tử.

**Lỗi 2 — Cho rằng null key được chấp nhận vì HashMap cho phép.** `Collectors.groupingBy` từ chối kết quả classifier null. Viết test nhận `NullPointerException` cho đầu vào xấu hoặc test chính sách chuẩn hóa trả khóa thay thế.

**Lỗi 3 — Dùng một ca test chung cho null object và null field.** Hai lỗi có nguồn gốc khác nhau. Test riêng chúng để biết cần sửa bộ lọc nguồn hay logic classifier.

**Lỗi 4 — Lọc null không chủ đích.** `filter(Objects::nonNull)` làm chương trình chạy nhưng có thể làm thiếu kết quả nghiệp vụ. Test số lượng dòng đầu vào, số dòng bị loại và cách báo dữ liệu hỏng.

**Lỗi 5 — Giả định trùng ID sẽ tự biến mất.** `groupingBy(..., toList())` giữ toàn bộ bản ghi có khóa bằng nhau; `distinct()` lại dựa trên `equals/hashCode` của phần tử. Muốn loại trùng theo ID phải định nghĩa quy tắc riêng.

**Lỗi 6 — Dùng `toMap` hai tham số cho ID có thể trùng.** Nó ném `IllegalStateException`; test trường hợp trùng và quyết định xử lý bằng reject, merge, hay dùng `groupingBy` tạo List.

**Lỗi 7 — Gộp bản ghi trùng bằng cộng số lượng mà không xác nhận ngữ nghĩa.** Nếu đây là hai sự kiện hợp lệ thì tổng đúng; nếu cùng sự kiện được gửi hai lần thì tổng sai. Cần test dữ liệu replay và idempotency theo yêu cầu hệ thống.

**Lỗi 8 — Gộp nhầm vì chuẩn hóa quá mạnh.** Chuyển chữ thường, bỏ dấu, cắt khoảng trắng hay đổi ký tự có thể làm **hai khóa nghiệp vụ khác nhau trở thành một**. Giữ test cho các khóa không được phép va chạm; chỉ chuẩn hóa theo quy tắc đã được chấp thuận.

**Lỗi 9 — Dựa vào thứ tự HashMap hoặc `toSet()`.** Thứ tự không được bảo đảm. So sánh tập, count hoặc dùng đúng collection có hợp đồng thứ tự.

## 9. Bài tập tự luyện

1. Thêm dòng `new Entry("E-01", "NORTH", 1)`. Hãy dự đoán số phần tử nhóm `north`, tổng số bản ghi và số ID phân biệt sau khi lọc null.
2. Thêm dòng `new Entry("Z-01", "<unknown>", 1)`. Tại sao dòng này có thể bị gộp nhầm với bản ghi thiếu category? Thiết kế một kiểu khóa tránh va chạm.
3. Thay quy tắc xử lý null từ “gán nhóm thiếu” sang “từ chối bản ghi”. Ca kiểm thử nào cần đổi và trường hợp nào nên ném exception riêng có thông điệp rõ?
4. Cho hai dòng ID `A-02` cùng đại diện một sự kiện được gửi lại. Vì sao `Integer::sum` không còn đúng? Hãy xác định khóa idempotency và cách chọn bản ghi được giữ lại.
5. Viết thêm một phép kiểm rằng với cùng dữ liệu hợp lệ, số bản ghi được giữ trong nhóm ở stream tuần tự và parallel là như nhau, kể cả khi thứ tự duyệt Map khác nhau.

**Đáp án gợi ý:** (1) `north=4`, tổng bản ghi được nhóm `7`, ID phân biệt `6`. (2) Sentinel dạng chuỗi có thể trùng với category thực; dùng enum/kiểu khóa riêng hoặc không cho category đó là dữ liệu người dùng. (3) Test phải xác minh bản ghi thiếu category bị từ chối, thay vì xuất hiện dưới khóa `<unknown>`; vẫn phải kiểm null element riêng. (4) Gộp theo ID sự kiện và quy tắc chống replay trước khi tính tổng. (5) Dùng Map đếm theo ID hoặc tổng kích thước từng nhóm, không so sánh thứ tự in.

## Ghi nhớ

Khi phân nhóm dữ liệu bằng Stream, bài test đáng tin phải kiểm **giá trị khóa**, **chính sách null**, **số lượng và nội dung của từng nhóm**, cùng **ý nghĩa nghiệp vụ của bản ghi trùng**. `Collectors.groupingBy` giữ các phần tử có khóa bằng nhau trong cùng nhóm; nó không tự loại trùng và không chấp nhận khóa null do classifier trả về ở JDK hiện hành. `Collectors.toMap` có quy tắc va chạm khác với `groupingBy`. Viết test dựa trên các bất biến nghiệp vụ và hợp đồng API để có kết quả chính xác trên cả phiên bản Java đang được sử dụng.

### Tài liệu Java chính thức (API hiện hành)

- [Oracle Java SE 26 — Collectors.groupingBy, counting, toList, toMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Stream.distinct và xử lý thứ tự](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — java.util.stream package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — Objects.nonNull](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
