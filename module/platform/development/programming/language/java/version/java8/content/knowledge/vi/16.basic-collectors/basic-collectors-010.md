# Collectors.minBy, maxBy và Optional kết quả trong Java Stream

`Collectors.minBy(...)` và `Collectors.maxBy(...)` là hai **Collector** có từ Java 8 và vẫn thuộc API Java hiện hành. Chúng chọn **một phần tử nhỏ nhất hoặc lớn nhất theo quy tắc so sánh do lập trình viên cung cấp**, rồi đóng gói kết quả trong `Optional<T>`. Đây là bài học thuộc nhóm **Collector cơ bản**: mục tiêu là hiểu cách dùng hai Collector, ý nghĩa `Comparator`, cách xử lý Stream rỗng và lý do kết quả phải là `Optional`.

Ví dụ điển hình: lấy sản phẩm rẻ nhất trong danh sách, sản phẩm đắt nhất của từng nhóm, hoặc điểm lớn nhất trong mỗi nhánh phân loại. `minBy` và `maxBy` dùng **một tiêu chí so sánh rõ ràng**; chúng không tự biết “nhỏ/lớn” theo ý nghĩa nghiệp vụ khi chưa có `Comparator`.

## 1. API và luồng thực thi

Chữ ký quan trọng:

~~~java
// Trong java.util.stream.Collectors:
public static <T> Collector<T, ?, Optional<T>> minBy(
        Comparator<? super T> comparator);

public static <T> Collector<T, ?, Optional<T>> maxBy(
        Comparator<? super T> comparator);
~~~

Đây là **chữ ký minh họa lấy từ API**, không phải một chương trình Java độc lập. Cách dùng:

~~~java
Optional<T> smallest = stream.collect(Collectors.minBy(comparator));
Optional<T> largest  = stream.collect(Collectors.maxBy(comparator));
~~~

Đoạn trên là **mẫu tổng quát**: cần thay `T`, `stream` và `comparator` bằng giá trị thật trong chương trình.

Diễn giải các thành phần:

1. `Comparator<? super T>` quyết định thứ tự so sánh. Khi `compare(a, b) < 0`, `a` đứng **trước** `b` theo comparator.
2. `minBy(comparator)` chọn phần tử **nhỏ nhất theo thứ tự ấy**. `maxBy(comparator)` chọn phần tử **lớn nhất**.
3. `collect(...)` là **terminal operation**: nó tiêu thụ Stream để tổng hợp kết quả. Stream đã tiêu thụ không thể dùng lại cho lần collect khác.
4. Kiểu trả về của cả hai là `Optional<T>`. `Optional` có thể chứa phần tử đã chọn, hoặc rỗng nếu không có phần tử đầu vào.
5. Việc chọn cực trị là một dạng **reduction**; theo hợp đồng API, `Collectors.minBy(cmp)` tương đương về phép giảm với `Collectors.reducing(BinaryOperator.minBy(cmp))`, và tương tự cho `maxBy`.

Ví dụ dữ liệu là các giá `[10, 30, 250, 600]`, so sánh theo giá tăng dần: `minBy` cho `10`, `maxBy` cho `600`. Với Stream rỗng, **không có phần tử cực trị**, vì vậy kết quả là `Optional.empty()`, không phải `null`, `0` hoặc một giá trị mặc định tự chọn.

## 2. Phân biệt Collector với Stream.min/max

Java Stream cũng có hai terminal operation trực tiếp:

~~~java
Optional<T> smallest = stream.min(comparator);
Optional<T> largest  = stream.max(comparator);
~~~

| Cách gọi | Kiểu trả về | Dùng khi |
|---|---|---|
| `stream.min(cmp)` | `Optional<T>` | Chỉ cần tìm min của một Stream |
| `stream.max(cmp)` | `Optional<T>` | Chỉ cần tìm max của một Stream |
| `stream.collect(Collectors.minBy(cmp))` | `Optional<T>` | Cần min dưới dạng Collector, đặc biệt khi ghép với Collector khác |
| `stream.collect(Collectors.maxBy(cmp))` | `Optional<T>` | Cần max làm downstream Collector trong nhóm/phân hoạch |

Khi chỉ cần cực trị của **toàn bộ Stream**, `stream.min(cmp)` hoặc `stream.max(cmp)` thường ngắn gọn hơn. Sức mạnh của `Collectors.minBy/maxBy` thể hiện khi làm **downstream collector** của `groupingBy(...)`, `partitioningBy(...)`, hoặc tổ hợp Collector khác.

Cả hai cách đều dựa vào `Comparator`, trả `Optional` khi có thể rỗng và không cần sắp xếp toàn bộ danh sách trước khi tìm cực trị. Tuy nhiên, nếu hai phần tử **bằng nhau theo Comparator**, không nên phụ thuộc vào việc API sẽ chọn chính xác đối tượng nào, đặc biệt khi xử lý song song. Hãy thêm tiêu chí phụ khi cần kết quả có thể tái lập.

## 3. Comparator quyết định “nhỏ nhất” và “lớn nhất”

Các Comparator thường gặp:

~~~java
Comparator<Integer> ascendingNumbers = Integer::compare;
Comparator<String> alphabetical = Comparator.naturalOrder();
Comparator<String> byLength = Comparator.comparingInt(String::length);
~~~

Đây là các khai báo độc lập khi đặt trong phương thức có import `java.util.Comparator`. Ý nghĩa:

- `ascendingNumbers`: số nhỏ hơn theo giá trị số học được `minBy` chọn.
- `alphabetical`: chuỗi được so sánh theo thứ tự tự nhiên của `String`, không phải theo độ dài.
- `byLength`: chuỗi ngắn nhất là min, chuỗi dài nhất là max. Hai chuỗi có cùng độ dài được coi là bằng nhau theo comparator này.

Với đối tượng nghiệp vụ, nên biểu đạt rõ trường so sánh:

~~~java
Comparator<Product> byPrice = Comparator.comparingInt(p -> p.price);
~~~

Đây là **mảnh mã minh họa** giả sử đã khai báo kiểu `Product` và trường `price`. Với chương trình hoàn chỉnh bên dưới, ta dùng lớp `Item` và thêm tie-break bằng tên:

~~~java
Comparator<Item> byPriceThenName = Comparator
        .comparingInt((Item item) -> item.price)
        .thenComparing(item -> item.name);
~~~

Khi hai sản phẩm cùng giá, `thenComparing` so sánh tiếp theo tên. Nếu muốn thứ tự giá **giảm dần**, có thể dùng `byPriceThenName.reversed()`; nhưng lúc đó `minBy` sẽ chọn **giá cao** nhất theo tiêu chí đã đảo. Để tránh gây hiểu nhầm cho người đọc code, thường nên giữ Comparator tăng dần và chọn đúng `minBy` hoặc `maxBy` theo yêu cầu.

**Cảnh báo về null:** `Optional` không chứa giá trị `null`. Dù `Comparator.nullsFirst/nullsLast` có thể so sánh null, nếu phần tử được chọn là null, phép reduction có thể ném `NullPointerException`. Với bài toán chọn cực trị, cách rõ ràng là loại hoặc xử lý giá trị null **trước** khi collect, ví dụ `filter(Objects::nonNull)`, rồi dùng Comparator phù hợp.

## 4. Ví dụ hoàn chỉnh chạy được: min, max, rỗng và downstream

Tạo file `MinMaxCollectorDemo.java`. Ví dụ dùng API có từ Java 8, biên dịch và chạy được trên JDK 17+; sử dụng `TreeMap` chỉ để thứ tự in các nhóm ổn định:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MinMaxCollectorDemo {
    static final class Item {
        final String name;
        final String category;
        final int price;

        Item(String name, String category, int price) {
            this.name = name;
            this.category = category;
            this.price = price;
        }

        String label() {
            return name + "(" + price + ")";
        }
    }

    public static void main(String[] args) {
        List<Item> items = Arrays.asList(
                new Item("Pen", "office", 10),
                new Item("Notebook", "office", 30),
                new Item("Mouse", "device", 250),
                new Item("Keyboard", "device", 600)
        );

        Comparator<Item> byPriceThenName = Comparator
                .comparingInt((Item item) -> item.price)
                .thenComparing(item -> item.name);

        Optional<Item> min = items.stream()
                .collect(Collectors.minBy(byPriceThenName));

        Optional<Item> max = items.stream()
                .collect(Collectors.maxBy(byPriceThenName));

        System.out.println("Minimum: "
                + min.map(Item::label).orElse("none"));
        System.out.println("Maximum: "
                + max.map(Item::label).orElse("none"));

        Optional<Item> empty = Stream.<Item>empty()
                .collect(Collectors.minBy(byPriceThenName));
        System.out.println("Empty: " + empty);

        Map<String, Optional<Item>> maxByCategory = items.stream()
                .collect(Collectors.groupingBy(
                        item -> item.category,
                        TreeMap::new,
                        Collectors.maxBy(byPriceThenName)
                ));

        maxByCategory.forEach((category, result) ->
                System.out.println(category + ": "
                        + result.map(Item::label).orElse("none")));

        Map<Boolean, Optional<Integer>> byEven =
                Arrays.asList(3, 5, 9).stream()
                        .collect(Collectors.partitioningBy(
                                n -> n % 2 == 0,
                                Collectors.maxBy(Integer::compareTo)
                        ));

        System.out.println("Even: " + byEven.get(true));
        System.out.println("Odd: " + byEven.get(false));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MinMaxCollectorDemo.java
java MinMaxCollectorDemo
~~~

Stdout:

~~~text
Minimum: Pen(10)
Maximum: Keyboard(600)
Empty: Optional.empty
device: Keyboard(600)
office: Notebook(30)
Even: Optional.empty
Odd: Optional[9]
~~~

**Giải thích theo từng phần:**

- `min` chọn `Pen` với giá `10`, còn `max` chọn `Keyboard` với giá `600`; `Optional.map(Item::label)` biến phần tử bên trong thành chuỗi hiển thị, rồi `orElse("none")` đặt fallback nếu rỗng.
- Stream rỗng trả `Optional.empty`. Không tự tạo một sản phẩm giả có giá 0 để đại diện cho kết quả thiếu.
- `groupingBy` phân loại theo `category`, sau đó `Collectors.maxBy` chọn sản phẩm đắt nhất **trong từng nhóm**. Kiểu giá trị map là `Optional<Item>`, không phải `Item`; `TreeMap` giúp in `device` trước `office` theo thứ tự khóa tăng dần.
- `partitioningBy` chia theo số chẵn/lẻ. Dữ liệu `3, 5, 9` không chứa số chẵn, nhưng map phân hoạch **vẫn có hai khóa** `true` và `false`. Nhánh `true` được downstream `maxBy` trả `Optional.empty`; nhánh `false` trả `Optional[9]`.

Nếu đổi mã nguồn thành Stream song song, các biểu thức reduction vẫn cần Comparator hợp lệ, không biến đổi state bên ngoài. Thứ tự in trong ví dụ đến từ việc lặp `TreeMap` ở cuối; **không** suy ra thứ tự thực thi các bước bên trong parallel pipeline.

## 5. Vì sao kết quả là Optional?

`Optional<T>` mô tả việc có thể **có** hoặc **không có** một phần tử cực trị. Nó giúp mã gọi phải xem xét tình huống dữ liệu rỗng thay vì âm thầm nhận `null` hoặc một giá trị giả.

| Dữ liệu đầu vào | Kết quả `minBy(Integer::compareTo)` | Kết quả `maxBy(Integer::compareTo)` |
|---|---|---|
| `[]` | `Optional.empty` | `Optional.empty` |
| `[7]` | `Optional[7]` | `Optional[7]` |
| `[4, 7, 2]` | `Optional[2]` | `Optional[7]` |

Sự rỗng có thể xảy ra vì danh sách nguồn rỗng, hoặc vì các phép `filter` ở trước đã loại hết dữ liệu. `Optional.empty()` không có nghĩa giá trị nhỏ nhất là 0, cũng không nên được hiểu là dữ liệu bị lỗi: nó chỉ nói rằng **không có phần tử để chọn**.

Các cách xử lý an toàn:

~~~java
Optional<Integer> minimum = java.util.stream.Stream.of(4, 7, 2)
        .collect(java.util.stream.Collectors.minBy(Integer::compareTo));

minimum.ifPresent(value -> System.out.println("Min = " + value));

int valueOrFallback = minimum.orElse(-1);

int valueOrThrow = minimum.orElseThrow(
        () -> new IllegalStateException("No elements"));
~~~

Đây là đoạn mã chạy được **khi đặt trong `main`** với import `java.util.Optional`. `ifPresent` chỉ chạy khi có giá trị; `orElse(-1)` trả fallback nếu rỗng; `orElseThrow(...)` báo lỗi có chủ đích nếu dữ liệu bắt buộc phải tồn tại. Giá trị `-1` chỉ là quy ước ứng dụng, không liên quan đến Comparator hay identity của Collector.

Một số lựa chọn khác:

- `optional.map(f)` biến đổi giá trị **bên trong** nếu nó hiện diện, rồi vẫn trả `Optional`.
- `optional.orElse(defaultValue)` dùng giá trị mặc định. Biểu thức `defaultValue` được đánh giá trước lúc gọi hàm, kể cả khi `Optional` đang có giá trị.
- `optional.orElseGet(supplier)` chỉ gọi supplier để tạo giá trị mặc định khi Optional rỗng; phù hợp khi việc tạo fallback tốn chi phí.
- `optional.isPresent()` hoặc `optional.ifPresent(consumer)` cho xử lý có điều kiện; `Optional.isEmpty()` có từ Java 11 và vẫn được hỗ trợ ở JDK hiện đại.
- Tránh `optional.get()` nếu không chứng minh trước được có giá trị: một Optional rỗng sẽ ném `NoSuchElementException`. Không so sánh `optional == Optional.empty()` để kiểm tra giá trị; dùng API Optional.

Đừng lưu `Optional` vào collection như một cách giả lập dữ liệu thật khi mục tiêu cần một phần tử chắc chắn; hãy quyết định rõ chính sách ứng dụng: bỏ qua nhóm rỗng, hiển thị “không có dữ liệu”, dùng fallback hợp lệ, hay báo lỗi.

## 6. Downstream Collector: nhóm và phân hoạch

### 6.1. `groupingBy(..., minBy/maxBy)`

Mẫu phổ biến:

~~~java
Map<String, Optional<Item>> cheapestByCategory = items.stream()
        .collect(Collectors.groupingBy(
                item -> item.category,
                Collectors.minBy(byPriceThenName)
        ));
~~~

Đây là **mảnh mã dùng lại** các khai báo `Item`, `items`, `byPriceThenName` và imports của chương trình ở phần 4; không phải chương trình độc lập. Mỗi khóa là một nhóm; value là `Optional<Item>` chứa phần tử rẻ nhất theo Comparator ở nhóm đó.

Một chi tiết quan trọng: khi dùng `groupingBy` trực tiếp trên Stream rỗng, kết quả thường là **map rỗng**, không có một khóa bất kỳ để chứa `Optional.empty`. `groupingBy` tạo khóa từ những phần tử được phân nhóm; không tự tạo những danh mục không xuất hiện trong nguồn. Với nhóm có phần tử, downstream `minBy` nhận dữ liệu không rỗng; tuy vậy kiểu trả về vẫn là `Optional<Item>` theo API Collector.

Nếu ứng dụng cần hiển thị **mọi danh mục đã định nghĩa**, kể cả không có sản phẩm, phải kết hợp các danh mục chuẩn với map kết quả theo một quy tắc riêng. Không giả định `groupingBy` tự cung cấp bản ghi cho danh mục rỗng.

### 6.2. `partitioningBy(..., minBy/maxBy)`

`partitioningBy(predicate, downstream)` chia phần tử vào hai phân hoạch boolean. Khác với `groupingBy`, kết quả chứa cả `true` và `false` ngay cả khi một nhánh không có phần tử; nhánh rỗng được downstream `minBy` hoặc `maxBy` biểu diễn bằng `Optional.empty`.

~~~java
Map<Boolean, Optional<Integer>> smallestByParity =
        java.util.Arrays.asList(3, 5, 9).stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.minBy(Integer::compareTo)
                ));
~~~

Đoạn mã được đặt trong `main` và cần import `java.util.Map`, `java.util.stream.Collectors`. `smallestByParity.get(true)` trả `Optional.empty` do không có số chẵn; `smallestByParity.get(false)` là `Optional[3]`. Đây là trường hợp thực tế cho thấy **Optional rỗng có thể xuất hiện ở một nhánh downstream dù nguồn tổng thể không rỗng**.

### 6.3. Trường hợp chỉ cần một extreme

Khi không cần nhóm/phân hoạch, viết:

~~~java
Optional<Item> cheapest = items.stream().min(byPriceThenName);
Optional<Item> priciest = items.stream().max(byPriceThenName);
~~~

Hai dòng dùng lại biến từ phần 4. Kết quả có cùng ý nghĩa cực trị như dùng `Collectors.minBy/maxBy` tương ứng, và biểu đạt ngắn hơn. Nếu có nhiều tiêu chí so sánh khác nhau, tạo Comparator có tên rõ ý nghĩa thay vì lồng các phép đảo chiều khó đọc.

## 7. Nguyên tắc đúng đắn và hiệu năng

**Comparator đúng:** phải có hành vi nhất quán, tuân theo hợp đồng so sánh, không gây side effect và không phụ thuộc vào trạng thái thay đổi trong lúc collect. `Comparator.comparingInt(...)`, `thenComparing(...)`, `naturalOrder()` và `reversed()` là các API hiện hành để biểu đạt quy tắc này.

**Tie (cực trị bằng nhau):** nếu `cmp.compare(a, b) == 0`, cả hai đều hợp lệ theo tiêu chí ấy. Không nên dựa vào “phần tử đầu tiên chắc chắn thắng” như một hợp đồng của Collector. Khi cần kết quả nhất quán, hãy thêm tie-breaker ổn định như tên hoặc ID bất biến qua `thenComparing(...)`.

**Không sort toàn bộ:** để lấy một min/max, phép duyệt và so sánh trực tiếp thường đủ, với chi phí thời gian tuyến tính theo số phần tử (khoảng `O(n)` phép so sánh); gọi `sorted(...).findFirst()` buộc triển khai sắp xếp không cần thiết với chi phí thường cao hơn. Chọn `min/max` hoặc `minBy/maxBy` khi chỉ muốn một cực trị.

**Song song:** phép tìm cực trị có thể gộp kết quả từng nhánh. Comparator nên stateless và không can thiệp nguồn để kết quả đáng tin cậy; parallel Stream không tự động nhanh hơn với dữ liệu nhỏ. Không log, ghi dữ liệu ngoài hay thay đổi object đang được so sánh trong Comparator.

**Null:** tránh để phần tử được chọn là null. `Optional` không chứa null; với Stream chứa null và Comparator chấp nhận null, reduction vẫn có thể gặp `NullPointerException` nếu phần tử được chọn là null. Làm sạch dữ liệu trước khi so sánh thay vì hy vọng Optional tự chuyển null thành empty.

**Dữ liệu không cần boxing:** nếu đầu vào là `IntStream`, có thể gọi trực tiếp `min()`/`max()` để nhận `OptionalInt`, thay vì boxing sang `Stream<Integer>` chỉ để dùng Collector. Chọn theo kiểu dữ liệu và yêu cầu downstream.

## 8. Những lỗi thường gặp

1. **Nhầm `minBy`/`maxBy` với phép sort.** Chúng chọn **một** giá trị cực trị theo Comparator; không tạo danh sách đã sắp xếp.
2. **Gán kết quả vào `T` thay vì `Optional<T>`.** `Collectors.maxBy(...)` trả Collector; chỉ sau khi `collect(...)` mới có `Optional<T>`, và vẫn cần xử lý khả năng rỗng.
3. **Dùng `Optional.get()` vô điều kiện.** Nếu sau `filter` không còn phần tử hoặc nhánh phân hoạch rỗng, code ném `NoSuchElementException`. Dùng `map`, `ifPresent`, `orElse`/`orElseGet` hoặc `orElseThrow` có chủ đích.
4. **Đảo Comparator rồi quên ý nghĩa min/max.** `minBy(comparator.reversed())` chọn giá trị lớn nhất theo comparator gốc. Đặt tên Comparator theo nghiệp vụ.
5. **Không xử lý tie.** Với hai sản phẩm cùng giá, Comparator chỉ theo giá coi chúng tương đương; thêm `thenComparing` theo tên/ID khi cần chọn kết quả ổn định.
6. **Quên `Optional.empty` trong downstream.** Với `partitioningBy` một nhánh có thể rỗng; map vẫn có khóa nhưng giá trị của nhánh là Optional rỗng.
7. **Dùng `groupingBy` và chờ khóa cho nhóm không có phần tử.** `groupingBy` không tự tạo tất cả nhóm dự kiến; cần bổ sung khóa thiếu theo danh mục ứng dụng nếu cần.
8. **Comparator thay đổi trạng thái hoặc phụ thuộc object mutable.** Việc thay đổi thuộc tính tham gia so sánh trong quá trình reduction làm kết quả khó dự đoán. So sánh bằng thông tin ổn định.
9. **Ép dùng Collector cho bài toán đơn giản.** Tìm min/max trực tiếp của toàn Stream thường dùng `stream.min/max` dễ đọc hơn; `Collectors.minBy/maxBy` phát huy giá trị khi lồng trong Collector khác.

## 9. Bài tập ngắn và đáp án

**Bài 1.** Với `Stream.of(5, 8, 2)` và `Integer::compareTo`, `minBy` và `maxBy` cho kết quả gì? Nếu thay bằng Stream rỗng thì sao?

**Bài 2.** Một Stream có ba sản phẩm cùng giá 100 nhưng tên khác nhau. Vì sao `Collectors.minBy(Comparator.comparingInt(p -> p.price))` chưa đủ để xác định cụ thể sản phẩm nào được chọn? Cần làm gì để kết quả ổn định?

**Bài 3.** Vì sao `Collectors.groupingBy(category, Collectors.maxBy(cmp))` trả `Map<K, Optional<V>>`, còn `Collectors.partitioningBy(predicate, Collectors.maxBy(cmp))` có thể chứa `Optional.empty` dù danh sách ban đầu không rỗng?

**Bài 4.** Khi chỉ cần phần tử nhỏ nhất của Stream số nguyên, nên ưu tiên `stream.min(cmp)` hay `stream.collect(Collectors.minBy(cmp))`? Khi nào lựa chọn Collector tốt hơn?

**Gợi ý đáp án:**

1. `Optional[2]` và `Optional[8]`; nếu Stream rỗng, cả hai trả `Optional.empty`.
2. Vì Comparator chỉ theo giá cho kết quả so sánh bằng nhau, không nêu tiêu chí chọn giữa các đối tượng đồng hạng; thêm `thenComparing` dựa trên trường ổn định như tên hoặc ID.
3. `groupingBy` sinh khóa từ những phần tử đã thấy; `partitioningBy` luôn có hai khóa boolean và một nhánh có thể không nhận phần tử nào. Downstream `maxBy` trả `Optional.empty` cho nhánh ấy.
4. `stream.min(cmp)` ngắn và rõ mục tiêu cho một Stream; `Collectors.minBy(cmp)` phù hợp để truyền dưới dạng downstream Collector cho nhóm/phân hoạch.

## Ghi nhớ

`Collectors.minBy` và `Collectors.maxBy` vẫn là API hiện hành để chọn phần tử cực trị **theo một Comparator**, với kết quả `Optional<T>`. **Empty Stream trả Optional.empty**, không có giá trị “0” hay null mặc định. Xử lý Optional theo quy tắc nghiệp vụ; thêm tie-breaker khi cần kết quả ổn định; dùng `stream.min/max` nếu chỉ tìm cực trị trực tiếp, và dùng Collector khi cần kết hợp với `groupingBy` hoặc `partitioningBy`.

### Tài liệu chính thức đang áp dụng

- [Oracle Java SE 26 — Collectors.minBy, maxBy, groupingBy và partitioningBy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Stream.min và Stream.max](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — Optional](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 26 — Comparator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
