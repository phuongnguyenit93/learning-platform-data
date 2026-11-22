# `Collectors.toUnmodifiableMap()` và yêu cầu về dữ liệu `null` trong Java

## 1. Khi nào cần một Map không thể sửa đổi?

Trong Stream API, `collect` là thao tác kết thúc (*terminal operation*) biến các phần tử Stream thành kết quả tổng hợp. Một nhu cầu phổ biến là tạo `Map<K,V>`, trong đó mỗi phần tử cung cấp một khóa và một giá trị. Nếu Map kết quả **không được phép thêm, xóa hoặc sửa các ánh xạ key-value**, Java có collector chuyên biệt:

~~~java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
~~~

Ví dụ, với danh sách mặt hàng:

~~~java
record Item(String code, String name, int price) {}

List<Item> items = List.of(
        new Item("P01", "Book", 120),
        new Item("P02", "Pen", 15));

Map<String, Item> byCode = items.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::code,
                Function.identity()));

System.out.println(byCode.get("P01").name()); // Book
~~~

Trong ví dụ:

- `Item::code` biến mỗi `Item` thành khóa `String`.
- `Function.identity()` giữ nguyên `Item` làm giá trị của Map.
- `toUnmodifiableMap` thu thập các cặp khóa/giá trị và trả **Map không thể sửa đổi**.
- Nếu `keyMapper` hoặc `valueMapper` trả `null`, collector không chấp nhận và ném `NullPointerException`.
- Nếu hai phần tử tạo cùng khóa, overload **hai đối số** ném `IllegalStateException`; overload ba đối số cho phép cung cấp cách giải quyết xung đột.

Điểm quan trọng của bài: **“Map không thể sửa đổi” và “không chấp nhận null” là hai đặc tính khác nhau.** Chúng cùng tồn tại ở `toUnmodifiableMap` nhưng không nên suy rằng *mọi* cấu trúc Map không thể sửa đều có ràng buộc null giống hệt.

## 2. API và phiên bản Java

`Collectors.toUnmodifiableMap` được bổ sung từ **Java 10** và có trong Java 17+. Có hai overload chính:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
~~~

Giải thích các tham số kiểu:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu từng phần tử nguồn | `Item` |
| `K` | Kiểu khóa trong Map | `String` |
| `U` | Kiểu giá trị trong Map | `Integer` hoặc `Item` |
| `keyMapper` | Chuyển `T` thành `K` | `Item::code` |
| `valueMapper` | Chuyển `T` thành `U` | `Item::price` hoặc `Function.identity()` |
| `mergeFunction` | Gộp hai giá trị `U` khi khóa trùng | `Integer::sum` |

Ví dụ với kết quả số:

~~~java
Map<String, Integer> prices = items.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::code,
                Item::price));

System.out.println(prices.get("P02")); // 15
~~~

`Stream<Item>` trở thành `Map<String,Integer>`. `collect` thực hiện bước thu thập, còn `toUnmodifiableMap(...)` là **factory tạo Collector**; lời gọi factory chưa tự duyệt Stream.

**Đừng nhầm `Collectors.toUnmodifiableMap` với `Map.of`:** `Map.of` xây Map từ các đối số được cung cấp trực tiếp, không thu thập từng phần tử của Stream.

## 3. Ràng buộc null: không nhận khóa null và giá trị null

Theo hợp đồng API, kết quả của `Collectors.toUnmodifiableMap` **không chứa key hoặc value bằng `null`**. Nếu một trong hai hàm ánh xạ tạo `null` cho phần tử được thu thập, phép thu thập ném **`NullPointerException`**.

### 3.1. Khi `keyMapper` trả null

~~~java
record Row(String key, Integer value) {}

List<Row> rows = List.of(
        new Row("A", 10),
        new Row(null, 20));

Map<String, Integer> result = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value)); // NullPointerException.
~~~

`List.of` ở đây vẫn hợp lệ vì **hai phần tử Row không null**. Một trường `key` nằm *bên trong* Row có thể null. Khi `Row::key` được áp dụng lên Row thứ hai, nó trả null, gây lỗi ở collector.

### 3.2. Khi `valueMapper` trả null

~~~java
List<Row> rows = List.of(
        new Row("A", 10),
        new Row("B", null));

Map<String, Integer> result = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value)); // NullPointerException.
~~~

Khóa `"B"` hợp lệ, nhưng giá trị `null` không hợp lệ. Không nên nghĩ rằng Map sẽ lưu `"B" -> null` hoặc âm thầm bỏ qua phần tử đó.

### 3.3. Khi chính phần tử của Stream bằng null

Đây là trường hợp khác với **mapper trả null**:

~~~java
List<Row> rows = java.util.Arrays.asList(
        new Row("A", 10),
        null);

// rows.stream().collect(Collectors.toUnmodifiableMap(
//         Row::key, Row::value));
~~~

Một lời gọi method reference như `Row::key` trên phần tử nguồn null có thể ném `NullPointerException` **ngay trong mapper**. Kết quả vẫn là lỗi, nhưng nguyên nhân trực tiếp là không thể truy cập phương thức của đối tượng nguồn null, không phải một cặp key/value được collector chấp nhận.

Khi có thể gặp phần tử null ở nguồn, nên làm rõ chính sách: lọc chúng, từ chối dữ liệu không hợp lệ hoặc thay bằng dữ liệu được chuẩn hóa theo quy tắc nghiệp vụ.

### 3.4. Null trong Map không đồng nghĩa với “không tìm thấy khóa”

Trong một số Map khác, `get(key) == null` có thể đồng nghĩa *không có key* **hoặc** *key tồn tại với value null*. Với Map tạo từ `toUnmodifiableMap`, value không thể null, nên nếu `map.get("missing")` trả null thì khóa ấy không có trong Map.

Tuy nhiên, hãy dùng `containsKey` khi điều bạn muốn hỏi là **sự hiện diện của khóa**, thay vì dựa vào biểu thức so sánh value cho những API Map tổng quát khác.

## 4. Chiến lược 1: lọc dữ liệu không hợp lệ trước khi collect

Nếu nghiệp vụ cho phép **bỏ qua** bản ghi thiếu khóa hoặc giá trị, hãy lọc một cách tường minh:

~~~java
List<Row> raw = List.of(
        new Row("A", 10),
        new Row(null, 20),
        new Row("B", null),
        new Row("C", 30));

Map<String, Integer> clean = raw.stream()
        .filter(row -> row.key() != null && row.value() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));

System.out.println(clean.size());     // 2
System.out.println(clean.get("A"));   // 10
System.out.println(clean.get("C"));   // 30
~~~

Điều kiện lọc là phần của **chính sách dữ liệu**, không phải hành vi tự động của `toUnmodifiableMap`. Khi lọc, những bản ghi thiếu dữ liệu sẽ không còn trong kết quả. Nếu bài toán yêu cầu báo lỗi hoặc kiểm toán dữ liệu bị thiếu, việc im lặng bỏ qua thường không phù hợp.

Nếu có cả phần tử nguồn null:

~~~java
List<Row> raw = java.util.Arrays.asList(
        new Row("A", 10), null, new Row("B", 20));

Map<String, Integer> clean = raw.stream()
        .filter(java.util.Objects::nonNull)
        .filter(row -> row.key() != null && row.value() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));
~~~

Lọc chính Row null trước, rồi mới gọi `row.key()` và `row.value()`. Dùng `Objects::nonNull` ở **đúng vị trí** là cần thiết để tránh lỗi từ mapper.

## 5. Chiến lược 2: chuẩn hóa hoặc yêu cầu dữ liệu bắt buộc

Nhiều hệ thống **không được phép bỏ** bản ghi chỉ vì thiếu thông tin. Khi đó, có thể chọn một trong hai cách:

1. **Chuẩn hóa** thành giá trị hợp lệ được nghiệp vụ chấp nhận.
2. **Từ chối** bản ghi lỗi bằng exception có thông điệp rõ ràng.

Ví dụ: giá trị thiếu được định nghĩa là 0.

~~~java
Map<String, Integer> quantities = raw.stream()
        .filter(row -> row.key() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                row -> row.value() == null ? 0 : row.value()));
~~~

Đoạn này vẫn yêu cầu **khóa khác null**. Việc đặt số lượng thiếu thành 0 chỉ đúng nếu đó là quy tắc nghiệp vụ, không nên làm một cách máy móc.

Nếu trường `code` phải bắt buộc có, hãy kiểm tra sớm:

~~~java
Map<String, Integer> quantities = raw.stream()
        .collect(Collectors.toUnmodifiableMap(
                row -> java.util.Objects.requireNonNull(
                        row.key(), "code must not be null"),
                row -> java.util.Objects.requireNonNull(
                        row.value(), "quantity must not be null")));
~~~

Với phần tử nguồn không null và các khóa duy nhất, lỗi thiếu trường sẽ được báo thành `NullPointerException` kèm thông báo xác định do `requireNonNull` tạo. Trong một ứng dụng xử lý lỗi nghiệp vụ, cũng có thể dùng validation riêng để trả danh sách lỗi đầy đủ, thay vì để một lỗi đầu tiên chặn cả quá trình.

**Không dùng placeholder chung cho tất cả khóa null nếu nó có thể tạo trùng khóa.** Ví dụ thay mọi khóa thiếu bằng `"UNKNOWN"` khiến nhiều bản ghi cùng khóa và overload hai đối số chuyển sang ném `IllegalStateException`. Chuẩn hóa khóa phải đảm bảo tính duy nhất hoặc có chiến lược xử lý trùng.

## 6. Chiến lược 3: biểu diễn “vắng giá trị” bằng một value không null

Khi muốn **giữ lại khóa** nhưng ghi nhận rằng giá trị chưa có, có thể chọn một kiểu biểu diễn không null như `Optional<U>` làm value:

~~~java
List<Row> raw = List.of(
        new Row("A", null),
        new Row("B", 20));

Map<String, Optional<Integer>> values = raw.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                row -> Optional.ofNullable(row.value())));

System.out.println(values.get("A").isEmpty()); // true
System.out.println(values.get("B").orElse(-1)); // 20
~~~

Lúc này `valueMapper` trả **`Optional<Integer>` luôn khác null**, nên collector chấp nhận. Nội dung Optional có thể `empty`, nhưng **chính đối tượng Optional không null**.

Phương án này thay đổi mô hình API từ `Map<String,Integer>` thành `Map<String,Optional<Integer>>`; nó chỉ nên dùng nếu miền dữ liệu thực sự cần phân biệt “khóa tồn tại nhưng thiếu giá trị” với “không có khóa”.

Lưu ý `values.get("missing")` vẫn trả `null` vì **khóa không tồn tại**. Vì vậy hãy phân biệt:

- `values.containsKey("A") == true`, và `values.get("A") == Optional.empty()`.
- `values.containsKey("missing") == false`, và `values.get("missing") == null`.

Đừng gọi `isEmpty()` trên kết quả `get` của một khóa chưa xác minh là tồn tại.

## 7. Khóa trùng: lỗi riêng, không phải lỗi null

Overload hai tham số:

~~~java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
~~~

**không tự chọn bản ghi đầu hay bản ghi cuối** nếu nhiều phần tử tạo cùng key. Nó ném **`IllegalStateException`** khi gặp trùng khóa.

~~~java
List<Row> rows = List.of(
        new Row("A", 2),
        new Row("A", 5));

// Ném IllegalStateException:
Map<String, Integer> totals = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));
~~~

Để xử lý trùng khóa, dùng overload có tham số thứ ba:

~~~java
Map<String, Integer> totals = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value,
                Integer::sum));

System.out.println(totals.get("A")); // 7
~~~

`Integer::sum` là `BinaryOperator<Integer>` để gộp hai value. Phép cộng kết hợp và không phụ thuộc thứ tự cho ví dụ số nguyên này (không overflow trong dữ liệu nhỏ). Đây là chiến lược thích hợp khi các bản ghi chung key cần tổng hợp số lượng.

**Điểm cần nhớ:** có `mergeFunction` không giúp hợp thức hóa key/value null. Các hàm mapper vẫn không được trả null. Đừng dùng `mergeFunction` để “sửa lỗi null đầu vào” thay cho validation trước bước thu thập.

### 7.1. Chọn bản ghi đầu hay cuối khi khóa trùng

Có thể cung cấp:

~~~java
(left, right) -> left    // Giữ giá trị từ đối số bên trái.
(left, right) -> right   // Giữ giá trị từ đối số bên phải.
~~~

Nhưng không nên suy rằng `left` luôn là “bản ghi xuất hiện sớm nhất theo thời gian” trong mọi trường hợp song song, không có encounter order hoặc có thay đổi nguồn. Nếu bản ghi ưu tiên được xác định bằng thời điểm/độ quan trọng, thiết kế merge bằng **quy tắc so sánh rõ ràng** thay vì dựa vào thứ tự xử lý callback:

~~~java
record Event(String key, int priority) {}

Map<String, Event> chosen = events.stream()
        .collect(Collectors.toUnmodifiableMap(
                Event::key,
                Function.identity(),
                (a, b) -> a.priority() >= b.priority() ? a : b));
~~~

Ở ví dụ minh họa này, `events` giả định đã được khai báo là `List<Event>`. Để có kết quả xác định khi hai bản ghi cùng `priority`, có thể thêm tie-breaker theo một trường định danh thích hợp nếu nghiệp vụ yêu cầu.

### 7.2. Không dùng merge trả null như một cách lưu null value

`mergeFunction` không nên được coi là một kênh để lưu value null vào Map kết quả. Với các collector dựa vào ngữ nghĩa `Map.merge`, một kết quả merge null có thể dẫn tới **loại bỏ ánh xạ** của key thay vì lưu key với value null. Hãy thiết kế hàm merge trả **giá trị hợp lệ khác null** theo chính sách nghiệp vụ; nếu cần lưu trạng thái thiếu dữ liệu, dùng kiểu kết quả phù hợp như `Optional` hoặc cấu trúc domain khác.

## 8. Map kết quả không thể sửa, nhưng không “deep immutable”

Với Map trả về từ `toUnmodifiableMap`, các thao tác sửa cấu trúc phải bị từ chối:

~~~java
Map<String, Integer> prices = Stream.of(
        new Row("A", 10),
        new Row("B", 20))
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));

// prices.put("C", 30); // Ném UnsupportedOperationException.
// prices.remove("A"); // Ném UnsupportedOperationException.
// prices.clear();     // Ném UnsupportedOperationException.
~~~

Không nên suy ra Map sẽ thuộc lớp `HashMap`, `LinkedHashMap` hay một implementation cụ thể nào. API không yêu cầu một thứ tự duyệt cố định của keys hoặc entries; **đừng viết bài kiểm thử dựa trên `map.toString()` với thứ tự phần tử cụ thể**. Thay vào đó, kiểm tra `get(key)`, `containsKey(key)` và `size()`.

### 8.1. Object value mutable vẫn có thể thay đổi

~~~java
record Box(String id, List<String> tags) {}

List<String> tags = new ArrayList<>(List.of("new"));
Box box = new Box("B01", tags);

Map<String, Box> boxes = Stream.of(box)
        .collect(Collectors.toUnmodifiableMap(
                Box::id,
                Function.identity()));

tags.add("sale");

System.out.println(boxes.get("B01").tags()); // [new, sale]
~~~

`boxes` không cho thêm/xóa/sửa ánh xạ, nhưng value `Box` giữ tham chiếu tới một `List<String>` mutable. Thay đổi `tags` vẫn nhìn thấy qua đối tượng được Map tham chiếu.

**Unmodifiable Map không tự deep-copy phần tử đầu vào.** Nếu cần bất biến xuyên suốt, phải xây dựng những value phù hợp, chẳng hạn record với thành phần bất biến hoặc tạo defensive copy cho collection:

~~~java
record SafeBox(String id, List<String> tags) {
    SafeBox {
        tags = List.copyOf(tags);
    }
}
~~~

`List.copyOf` từ chối phần tử null và tạo/cung cấp List unmodifiable; với các object con mutable, vẫn cần xử lý sao chép theo tầng nếu đòi hỏi deep immutability.

## 9. So sánh với các API Map có tên gần nhau

| API | Mục tiêu | Đặc điểm cần nhớ |
| --- | --- | --- |
| `Collectors.toUnmodifiableMap(k,v)` | Thu thập Stream thành Map không thể sửa | Cấm key/value null; key trùng gây lỗi |
| `Collectors.toUnmodifiableMap(k,v,merge)` | Thu thập thành Map không thể sửa, xử lý key trùng | Cấm key/value null; merge phải có chính sách phù hợp |
| `Collectors.toMap(k,v)` | Thu thập Stream thành Map | Không bảo đảm Map có implementation, mutability hoặc đặc tính null cụ thể theo hợp đồng |
| `Collectors.toMap(k,v,merge)` | Thu thập Stream, gộp key trùng | Cần hiểu chính sách merge và Map đầu ra |
| `Map.of(k,v,...)` | Tạo trực tiếp Map không thể sửa từ cặp key/value | Cấm null và key trùng |
| `Map.ofEntries(entries...)` | Tạo trực tiếp Map không thể sửa từ entries | Cấm null và key trùng |
| `Map.copyOf(existing)` | Tạo Map không thể sửa chứa các ánh xạ của Map có sẵn | Cấm null key/value; không bảo đảm deep copy |
| `Collections.unmodifiableMap(existing)` | Tạo **view** không thể sửa trên Map có sẵn | Các thay đổi thực hiện qua Map gốc có thể hiển thị trong view |

**Cẩn trọng về `Collectors.toMap`:** đừng dùng nó chỉ với giả định “`toMap` chắc chắn chấp nhận null”. Với các overload, implementation và phiên bản JDK, hành vi liên quan null có các ràng buộc riêng, không phải hợp đồng chắc chắn để thay cho `toUnmodifiableMap`. Nếu cần xử lý null, tốt nhất là đưa chính sách rõ ràng vào pipeline và chọn cấu trúc kết quả có hợp đồng phù hợp.

Ví dụ phân biệt với `Collections.unmodifiableMap`:

~~~java
Map<String, Integer> mutable = new HashMap<>();
mutable.put("A", 1);

Map<String, Integer> view =
        Collections.unmodifiableMap(mutable);
mutable.put("B", 2);

System.out.println(view.containsKey("B")); // true
~~~

`view` không cho sửa qua nó, nhưng **Map nguồn mutable** vẫn được cập nhật từ biến `mutable` và view phản ánh sự thay đổi. Với `toUnmodifiableMap`, Map đầu ra không phải chỉ một wrapper trực tiếp trên collection nguồn; nó là kết quả thu thập từ các cặp key/value của Stream. Tuy nhiên, các đối tượng value mutable vẫn có thể được chia sẻ tham chiếu như phần 8.

## 10. Parallel Stream, thứ tự và tính đúng của merge

`Collectors.toUnmodifiableMap` có thể được dùng trong pipeline tuần tự hoặc song song:

~~~java
Map<String, Integer> totals = Stream.of(
        new Row("A", 2),
        new Row("B", 3),
        new Row("A", 5))
        .parallel()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value,
                Integer::sum));

System.out.println(totals.get("A")); // 7
System.out.println(totals.get("B")); // 3
~~~

Trong quá trình rút gọn song song, kết quả cục bộ có thể được ghép theo lịch thực thi khác nhau. Vì vậy merge nên là hành vi **stateless, non-interfering** và có tính **kết hợp** phù hợp nếu muốn kết quả xác định khi chia/gộp nguồn.

Ví dụ `Integer::sum` trên các giá trị nhỏ đáp ứng yêu cầu. Một merge như `(a,b) -> a - b` không kết hợp nên có thể cho kết quả khác nhau khi cấu trúc phân vùng thay đổi; không nên sử dụng làm phép tổng hợp song song trừ khi đã thiết kế rõ điều kiện phù hợp.

Không nên:

~~~java
// Tránh sửa chung state bên ngoài từ merger:
AtomicInteger calls = new AtomicInteger();
// (a, b) -> { calls.incrementAndGet(); return a + b; }
~~~

Đếm số lần gọi merge bằng side effect không phải căn cứ để suy luận bản ghi nào được ưu tiên, vì quá trình chia/gộp và thứ tự thực thi callback không phải hợp đồng ổn định cho bài toán đó.

## 11. Ví dụ Java 17+ hoàn chỉnh, biên dịch/chạy độc lập

Tạo tệp **`UnmodifiableMapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class UnmodifiableMapDemo {
    record Item(String code, Integer quantity) {}
    record Box(String code, List<String> tags) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 2),
                new Item("B", 4));

        Map<String, Item> byCode = items.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Function.identity()));
        System.out.println("A.quantity=" + byCode.get("A").quantity());
        System.out.println("containsB=" + byCode.containsKey("B"));

        try {
            byCode.put("C", new Item("C", 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        List<Item> duplicated = List.of(
                new Item("A", 2),
                new Item("A", 5));

        try {
            duplicated.stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (IllegalStateException ex) {
            System.out.println("duplicateRejected=true");
        }

        Map<String, Integer> merged = duplicated.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Item::quantity,
                        Integer::sum));
        System.out.println("mergedA=" + merged.get("A"));

        try {
            List.of(new Item(null, 1)).stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (NullPointerException ex) {
            System.out.println("nullKeyRejected=true");
        }

        try {
            List.of(new Item("X", null)).stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (NullPointerException ex) {
            System.out.println("nullValueRejected=true");
        }

        List<Item> incomplete = List.of(
                new Item(null, 10),
                new Item("X", null),
                new Item("Y", 5));

        Map<String, Integer> filtered = incomplete.stream()
                .filter(item ->
                        item.code() != null && item.quantity() != null)
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Item::quantity));
        System.out.println("filteredSize=" + filtered.size());
        System.out.println("filteredY=" + filtered.get("Y"));

        Map<String, Optional<Integer>> withMissing = List.of(
                new Item("X", null),
                new Item("Y", 5))
                .stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        item -> Optional.ofNullable(item.quantity())));
        System.out.println("X.isEmpty=" + withMissing.get("X").isEmpty());

        List<String> tags = new ArrayList<>(List.of("new"));
        Box box = new Box("B1", tags);
        Map<String, Box> boxes = List.of(box).stream()
                .collect(Collectors.toUnmodifiableMap(
                        Box::code,
                        Function.identity()));
        tags.add("sale");
        System.out.println("tagsCount=" + boxes.get("B1").tags().size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac UnmodifiableMapDemo.java
java UnmodifiableMapDemo
~~~

**Kết quả stdout:**

~~~text
A.quantity=2
containsB=true
unmodifiable=true
duplicateRejected=true
mergedA=7
nullKeyRejected=true
nullValueRejected=true
filteredSize=1
filteredY=5
X.isEmpty=true
tagsCount=2
~~~

Giải thích các nhóm kết quả:

1. `A.quantity=2` và `containsB=true`: hai phần tử Item được ánh xạ thành các entry trong Map, truy cập qua key.
2. `unmodifiable=true`: `put` không được hỗ trợ trên Map kết quả.
3. `duplicateRejected=true`: overload hai đối số gặp hai khóa `"A"` và ném `IllegalStateException`.
4. `mergedA=7`: overload ba đối số dùng `Integer::sum` để gộp hai giá trị 2 và 5.
5. `nullKeyRejected=true` và `nullValueRejected=true`: hai phép thu thập riêng chứng minh null ở key mapper hoặc value mapper đều bị từ chối.
6. `filteredSize=1` và `filteredY=5`: pipeline chỉ giữ bản ghi có đủ cả key và value.
7. `X.isEmpty=true`: Map có key `"X"` với **value là đối tượng `Optional.empty()`**, không phải null.
8. `tagsCount=2`: Map không thể sửa cấu trúc nhưng không deep-copy List mutable nằm trong value.

Chương trình cố ý **không in toàn bộ Map**, vì thứ tự duyệt entry không được bảo đảm. Các trường hợp lỗi được bắt đúng loại exception để stdout ổn định và không phụ thuộc thông báo lỗi do JVM tạo.

## 12. Lưu ý về `null`, lỗi và thiết kế API

### 12.1. Không lẫn ba tình huống lỗi

| Hiện tượng | Tình huống nguồn | Loại lỗi điển hình |
| --- | --- | --- |
| `keyMapper` trả null | `new Item(null, 1)` | `NullPointerException` |
| `valueMapper` trả null | `new Item("A", null)` | `NullPointerException` |
| Hai phần tử có cùng key | `new Item("A", 1)` và `new Item("A", 2)` | `IllegalStateException` nếu không có merger |
| Chính phần tử nguồn null | Nguồn chứa `null` | Có thể `NullPointerException` ngay khi gọi mapper |
| Sửa Map kết quả | `put`, `remove`, `clear` trên Map đầu ra | `UnsupportedOperationException` |

Đừng bắt tất cả `RuntimeException` rồi bỏ qua. Mỗi lỗi có ý nghĩa khác nhau và cần được xử lý ở nơi thích hợp: validation nguồn, chính sách giải quyết duplicate, hoặc quy tắc sử dụng kết quả.

### 12.2. Map không được sửa chưa đồng nghĩa thread-safe ở mọi tầng

Không sửa cấu trúc kết quả giúp chia sẻ Map an toàn hơn, nhưng Map có thể chứa value là đối tượng mutable do ứng dụng quản lý. Nếu những value được thay đổi đồng thời, **thread-safety vẫn phụ thuộc vào chính chúng và cách đồng bộ hóa**. Không lấy tên “unmodifiable” làm lời hứa toàn bộ đồ thị đối tượng là immutable hoặc tự động thread-safe.

### 12.3. Null có thể là tín hiệu nghiệp vụ quan trọng

Nếu `quantity == null` nghĩa là “chưa được kiểm kê”, còn `quantity == 0` nghĩa là “đã kiểm kê và hết hàng”, thay null bằng 0 sẽ **làm mất ý nghĩa dữ liệu**. Hãy dùng kiểu domain có trạng thái rõ ràng, `Optional` hoặc đối tượng kết quả mô tả dữ liệu thiếu khi cần. Phần xử lý chuẩn hóa phải dựa trên nhu cầu nghiệp vụ, không chỉ để tránh `NullPointerException`.

### 12.4. Một Map chỉ có một value cho mỗi key

Ngay cả khi cho phép merge, Map vẫn lưu **một ánh xạ duy nhất** cho mỗi key. Nếu cần lưu toàn bộ các bản ghi cùng khóa, cân nhắc `groupingBy` để tạo `Map<K,List<T>>`, sau đó thiết kế tính bất biến của Map và List theo mục tiêu; không nhầm phép gộp giá trị `toUnmodifiableMap` với phép nhóm nhiều giá trị.

## 13. Bài tập tự kiểm tra

**Câu 1.** Có `record R(String key, Integer value) {}`, một phần tử `new R("A", null)` được thu thập bằng `toUnmodifiableMap(R::key, R::value)`. Kết quả là gì?

**Đáp án:** `NullPointerException`, vì `valueMapper` trả null. Collector không lưu ánh xạ `"A" -> null`.

**Câu 2.** Có hai phần tử cùng key `"A"` và value lần lượt 3, 4. Dùng overload hai đối số thì sao? Muốn cộng hai value thì làm gì?

**Đáp án:** Hai đối số ném `IllegalStateException` do duplicate key. Dùng `Collectors.toUnmodifiableMap(R::key, R::value, Integer::sum)` để nhận value 7.

**Câu 3.** Map trả về từ `toUnmodifiableMap` có thể gọi `put` để thêm phần tử không?

**Đáp án:** Không. Thao tác sửa cấu trúc sẽ ném `UnsupportedOperationException`.

**Câu 4.** Nếu Map chứa value là `ArrayList` mutable, có thể thay đổi List từ một tham chiếu khác không?

**Đáp án:** Có. Tính không thể sửa của Map không tự biến value thành immutable hay tạo deep copy. Cần defensive copy/thiết kế value bất biến nếu đó là yêu cầu.

**Câu 5.** Vì sao không nên mặc định dùng `Collectors.toMap` như một cách lưu null?

**Đáp án:** Các overload/implementation có những ràng buộc riêng, không thể xem đó là lời hứa hỗ trợ null cho mọi trường hợp. Tốt nhất định nghĩa rõ cách lọc, chuẩn hóa, hoặc biểu diễn dữ liệu vắng mặt và chọn API phù hợp.

**Câu 6.** Khi nào nên dùng `Optional<Integer>` làm value?

**Đáp án:** Khi cần giữ key tồn tại trong Map nhưng một giá trị có thể chưa có, và mô hình domain thực sự cần phân biệt trạng thái ấy. `Optional.empty()` là đối tượng không null, phù hợp với collector.

**Câu 7.** Dùng `Map.of("A", null)` có giải quyết được ràng buộc null của `toUnmodifiableMap` không?

**Đáp án:** Không. `Map.of` cũng không chấp nhận null key hoặc null value.

**Câu 8.** Có thể dựa vào thứ tự `map.entrySet()` từ `toUnmodifiableMap` để tạo stdout cố định không?

**Đáp án:** Không nên. Không có hợp đồng bảo đảm thứ tự duyệt cụ thể. Kiểm tra theo key hoặc sắp xếp các entry khi có yêu cầu hiển thị theo thứ tự.

## 14. Ghi nhớ

`Collectors.toUnmodifiableMap` dùng để **thu thập Stream thành Map không thể sửa đổi**, bắt đầu từ Java 10. Những quy tắc cần luôn nhớ:

- **Key và value mapper không được trả `null`.** Nếu trả null, quá trình thu thập ném `NullPointerException`.
- **Khóa trùng không tự được giữ bản đầu hoặc bản cuối.** Overload hai đối số ném `IllegalStateException`; overload ba đối số dùng `mergeFunction` do bạn cung cấp.
- **Unmodifiable không phải deep immutable.** Map không sửa cấu trúc, nhưng value mutable có thể vẫn đổi trạng thái.
- **Không giả định thứ tự duyệt Map.** Hãy truy xuất theo khóa hoặc sắp xếp khi cần hiển thị có thứ tự.
- **Xử lý null theo chính sách nghiệp vụ trước `collect`:** lọc, validation, chuẩn hóa hoặc dùng value type biểu diễn sự vắng mặt.
- **Không nhầm với `Collectors.toMap`, `Map.of` hoặc `Collections.unmodifiableMap`.** Chúng có hợp đồng và mục đích khác nhau.

Chọn `toUnmodifiableMap` khi bạn muốn một kết quả thu thập có cấu trúc khóa-giá trị không thay đổi được và có chính sách rõ ràng cho null, duplicate key và kiểu giá trị.
