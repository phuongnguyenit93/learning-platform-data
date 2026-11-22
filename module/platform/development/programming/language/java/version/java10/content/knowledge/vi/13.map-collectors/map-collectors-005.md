# Chọn giá trị giữ lại khi khóa trùng trong Collector bản đồ (Java 10+)

## 1. Bài toán: nhiều phần tử cùng ánh xạ tới một khóa

Khi biến một `Stream<T>` thành `Map<K, V>` bằng `Collectors.toMap` hoặc `Collectors.toUnmodifiableMap`, hai bản ghi đầu vào khác nhau có thể sinh ra **cùng một khóa**. Một `Map` không thể giữ hai ánh xạ độc lập cho các khóa bằng nhau theo `equals`. Vì vậy cần quyết định **giữ giá trị nào** hoặc **gộp các giá trị như thế nào**.

Ví dụ một danh sách sản phẩm có nhiều phiên bản cùng mã `sku`:

```java
record Product(String sku, int revision, String label) {}

var products = List.of(
        new Product("A", 1, "draft"),
        new Product("B", 1, "base"),
        new Product("A", 3, "final"),
        new Product("A", 2, "review")
);
```

Đây là đoạn minh họa; cần `import java.util.List;`, record `Product` được khai báo trong phạm vi cho phép (chẳng hạn bên trong lớp hoặc trên cấp cao nhất). Vì ba bản ghi có `sku` bằng `"A"`, nếu tạo `Map<String, String>` theo `Product::sku`, phải xử lý ba giá trị `"draft"`, `"final"` và `"review"` đụng khóa.

Câu hỏi thiết kế không chỉ là “làm sao tránh lỗi?”, mà là:

- Muốn **giữ bản ghi đầu tiên** theo thứ tự đã xác định?
- Muốn **giữ bản ghi cuối cùng**?
- Muốn chọn **bản ghi có revision/timestamp lớn nhất**, không phụ thuộc thứ tự?
- Muốn **gộp** thông tin, chẳng hạn cộng số lượng hay kết hợp danh sách?
- Hay **khóa trùng là lỗi dữ liệu**, cần dừng xử lý thay vì tự chọn?

Đặt ra chính sách trước khi viết collector sẽ giúp tránh các lỗi dữ liệu âm thầm.

## 2. Không truyền merge function: mặc định báo lỗi khi khóa trùng

Overload đơn giản của `Collectors.toMap`:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper)
```

Đây là chữ ký API được rút gọn để học, không phải phương thức bạn cần tự định nghĩa.

`keyMapper` tạo khóa; `valueMapper` tạo giá trị. Nếu có hai khóa bằng nhau theo `Object.equals`, collector **ném `IllegalStateException`** trong quá trình `collect`.

```java
var products = List.of(
        new Product("A", 1, "draft"),
        new Product("A", 2, "review")
);

// Ném IllegalStateException khi collect:
var bySku = products.stream().collect(
        Collectors.toMap(Product::sku, Product::label));
```

Cần `import java.util.stream.Collectors;` và record `Product` ở phần 1. Chú ý:

- Lỗi xảy ra **ngay cả khi hai giá trị trùng nhau**. Điều kiện va chạm là **khóa**, không phải “giá trị khác nhau”.
- Với khóa `String`, so sánh bằng `String.equals`: `"A"` bằng `"A"`; `"A"` khác `"a"` trừ khi bạn chủ động chuẩn hóa.
- Nếu khóa là object nghiệp vụ, `equals` và `hashCode` phải tuân thủ hợp đồng. Đừng thay đổi các trường ảnh hưởng đến `hashCode` khi object đang làm khóa Map.

**Đây đôi khi là hành vi mong muốn:** nếu mã giao dịch `transactionId` bắt buộc duy nhất, để collector báo lỗi tốt hơn tự giữ một dòng dữ liệu bất kỳ và che mất trùng lặp.

## 3. Overload ba đối số: `mergeFunction` xác định cách xử lý va chạm

`Collectors.toMap` có overload hiện hành:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction)
```

`mergeFunction` nhận **hai giá trị `U`** của cùng một khóa và trả về giá trị cần lưu sau khi gộp. Theo hợp đồng `Map.merge` mà collector sử dụng, có thể đọc lambda hai tham số là:

```java
(existingValue, incomingValue) -> mergedValue
```

Trong phép thu thập **tuần tự từ stream có encounter order**, `existingValue` là giá trị đã tích lũy cho khóa, `incomingValue` là giá trị vừa đến. Chẳng hạn:

```java
var bySku = products.stream().collect(
        Collectors.toMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> existing));
```

Với danh sách nguồn có thứ tự và `stream()` tuần tự, đoạn này giữ giá trị **xuất hiện đầu tiên** cho mỗi khóa.

**Phân biệt:** tham số của `mergeFunction` là **hai giá trị do `valueMapper` tạo ra**, không phải hai object đầu vào nếu `valueMapper` chỉ trả về một trường. Nếu cần so sánh `revision` của hai `Product`, hãy để `valueMapper` trả về chính `Product` (xem phần 5).

## 4. Chính sách 1: giữ giá trị đầu tiên hoặc cuối cùng

### 4.1. Giữ đầu tiên

```java
var firstBySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> existing));
```

Với danh sách ordered tuần tự:

| SKU | Giá trị cuối trong Map |
| --- | --- |
| `A` | `draft` |
| `B` | `base` |

Mọi lần gặp lại khóa `A`, hàm gộp chọn `existing` và bỏ qua `incoming`.

### 4.2. Giữ cuối cùng

```java
var lastBySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> incoming));
```

Với đầu vào `A(draft), B(base), A(final), A(review)`, kết quả giữ:

- `A -> review`;
- `B -> base`.

Đây là quy tắc “**last wins**” dựa trên thứ tự đưa dữ liệu vào quá trình thu thập. Nếu các bản ghi cập nhật ở nguồn không được sắp theo thời gian thật, “đến cuối stream” **không đồng nghĩa** với “phiên bản mới nhất”.

### 4.3. Điều kiện để “đầu/cuối” mang ý nghĩa

Hai lambda trên dễ hiểu khi dùng `List.stream()` **tuần tự** với encounter order rõ ràng. Nhưng nếu nguồn không có thứ tự, bạn gọi `unordered()`, hoặc sử dụng một **concurrent, unordered collector** như `toConcurrentMap` trong pipeline song song, khái niệm “đầu tiên/cuối cùng” theo thời gian nghiệp vụ có thể không còn ổn định.

Không áp đặt giả định rằng tốc độ xử lý hay thứ tự hoàn thành luồng quyết định “bản ghi cuối” theo điều bạn mong muốn. Nếu ưu tiên bản ghi có thời gian cập nhật mới nhất, hãy **so sánh timestamp/revision** ngay trong merge function thay vì lựa chọn bằng vị trí.

## 5. Chính sách 2: chọn bản ghi theo tiêu chí, không theo thứ tự gặp

Nếu muốn giữ bản ghi có `revision` lớn nhất, cần so sánh bản ghi đầy đủ:

```java
var newestBySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Function.identity(),
                BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::revision))));
```

Cần `import java.util.function.Function;`, `import java.util.function.BinaryOperator;` và `import java.util.Comparator;`.

Giải thích:

- `Product::sku` tạo khóa `String`.
- `Function.identity()` cho giá trị là **Product**, để hàm gộp nhìn thấy `revision`.
- `BinaryOperator.maxBy` chọn bản ghi lớn hơn theo comparator. Nếu `A` có revision `1`, `3` và `2`, giá trị được giữ là bản ghi revision `3`.
- Nếu hai bản ghi có **revision bằng nhau**, comparator trên chỉ so sánh revision nên không có quy tắc nghiệp vụ đủ rõ để chọn bản nào.

Có thể bổ sung tiêu chí phụ:

```java
var newestBySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Function.identity(),
                BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::revision)
                                .thenComparing(Product::label))));
```

Dùng `label` làm tie-break ở ví dụ này nhằm tạo kết quả xác định hơn. Trong thực tế nên chọn **tiêu chí nghiệp vụ phù hợp và đủ phân biệt**, ví dụ timestamp cộng mã sự kiện duy nhất, thay vì tùy tiện dùng chữ cái của tên hiển thị.

**Ưu điểm:** quy tắc chọn “max revision” có thể rõ ràng hơn quy tắc đầu/cuối khi dữ liệu đến không theo thứ tự thời gian. Với comparator nhất quán và không có tie quan trọng chưa được giải quyết, kết quả không phụ thuộc vào vị trí của phần tử trong stream như “first wins” hoặc “last wins”.

## 6. Chính sách 3: tổng hợp thay vì loại bỏ giá trị

Không phải khóa trùng nào cũng nên chọn một bản ghi. Khi các phần tử thuộc cùng nhóm nghiệp vụ, có thể **gộp giá trị**.

### 6.1. Đếm số bản ghi cho mỗi khóa

```java
var counts = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                product -> 1,
                Integer::sum));
```

Với dữ liệu mẫu có ba bản ghi `A` và hai bản ghi `B`:

```text
A -> 3
B -> 2
```

`Integer::sum` có tính kết hợp và giao hoán cho ý nghĩa phép cộng số lượng (trong phạm vi kiểu số nguyên được sử dụng). Đây là lựa chọn phù hợp khi muốn **tổng hợp mọi bản ghi**, không phải chọn một bản ghi đại diện. Với dữ liệu khổng lồ có thể vượt `int`, hãy dùng kiểu đếm thích hợp như `long`/`Long::sum`.

### 6.2. Gộp chuỗi hoặc các giá trị có ý nghĩa kết hợp

```java
var labels = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::label,
                (a, b) -> a + " | " + b));
```

Với stream tuần tự ordered, các label của cùng khóa có thể được nối theo thứ tự gặp. Nhưng phép nối này **phụ thuộc vào thứ tự**, vì `"draft | review"` khác `"review | draft"`. Nếu dùng nguồn unordered hoặc collector concurrent, không được dựa vào thứ tự nối để tạo kết quả chuẩn.

Với nhiều giá trị trên cùng khóa, đôi khi mô hình đúng là **`Map<K, List<V>>`** thay vì nối thành một `String` hoặc tùy tiện giữ một bản ghi. Xem `Collectors.groupingBy` ở phần 10.

## 7. Điểm dễ bỏ sót: `mergeFunction` có liên quan trực tiếp đến `Map.merge`

Javadoc nói rằng merge function của `toMap` được sử dụng theo hợp đồng `Map.merge`. Vì vậy:

- `existing` là giá trị đã có cho khóa trong Map tích lũy.
- `incoming` là giá trị mới do `valueMapper` cung cấp.
- Nếu remapping function **trả về `null`**, `Map.merge` **xóa ánh xạ hiện tại** thay vì “giữ nguyên” hay “bỏ qua incoming”.

Ví dụ:

```java
var removed = List.of("A", "A").stream()
        .collect(Collectors.toMap(
                Function.identity(),
                Function.identity(),
                (oldValue, newValue) -> null));

// removed.isEmpty() == true
```

Đoạn trên cần `java.util.List`, `Collectors` và `Function`. Đây là ví dụ giải thích cơ chế, **không phải cách nên dùng để loại các phần tử không hợp lệ**. Nếu khóa `A` lại xuất hiện lần thứ ba sau khi đã bị xóa, nó có thể được thêm lại. Khi muốn bỏ dữ liệu theo quy tắc, hãy dùng `filter` trước khi collect hoặc thực hiện phép gộp có ngữ nghĩa rõ.

**Không nên có side effect trong merge function.** Đừng đồng thời sửa một Map ngoài, tăng biến đếm chia sẻ, ghi file hoặc phụ thuộc số lần hàm được gọi. Pipeline có thể xử lý/kết hợp theo chiến lược khác nhau, đặc biệt với stream song song. Hãy làm phép gộp **thuần, dễ kiểm thử, có tính kết hợp** khi có thể.

## 8. `Collectors.toUnmodifiableMap`: chọn va chạm và có kết quả không sửa được (Java 10)

Java 10 bổ sung `Collectors.toUnmodifiableMap`. Hai overload quan trọng:

```java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
```

Chúng có logic khóa trùng tương tự nhóm `toMap`:

1. **Không có mergeFunction:** gặp khóa bằng nhau sẽ ném `IllegalStateException`.
2. **Có mergeFunction:** giá trị của các phần tử cùng khóa được gộp theo hàm đã cung cấp.
3. **Kết quả là Map không sửa đổi:** các lệnh mutator như `put`, `remove` không được hỗ trợ.
4. **Không cho phép khóa và giá trị `null`:** nếu keyMapper hoặc valueMapper trả `null`, collector ném `NullPointerException`.
5. **Không bảo đảm thứ tự duyệt:** không khẳng định kết quả sẽ in theo encounter order hoặc kiểu Map cụ thể.

Ví dụ giữ bản ghi đến cuối stream tuần tự có thứ tự:

```java
var immutableLatestSeen = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> incoming));

// immutableLatestSeen.put("A", "other"); // biên dịch được nhưng
// sẽ ném UnsupportedOperationException khi chạy
```

Nếu yêu cầu “kết quả không thể sửa được và chỉ giữ giá trị phù hợp theo revision”, có thể kết hợp cả hai:

```java
var unmodifiableNewest = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::sku,
                Function.identity(),
                BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::revision)
                                .thenComparing(Product::label))));
```

**Đừng dùng `Collectors.toMap` không có hợp đồng về khả năng sửa** rồi mặc định kết quả luôn là một `HashMap` mutable. API `toMap` không cam kết kiểu implementation, tính sửa được, serializability hoặc thread-safety. Nếu muốn unmodifiable Map **theo hợp đồng**, `toUnmodifiableMap` là phương thức diễn đạt trực tiếp từ Java 10.

## 9. Nếu cần thứ tự duyệt key, dùng overload có `mapFactory`

Ba tham số của `toMap` cho phép chọn giá trị khi khóa trùng, nhưng **không quy định implementation Map hay iteration order**. Overload bốn tham số thêm `mapFactory` để tự chọn Map đích:

```java
var firstBySkuInOrder = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> existing,
                LinkedHashMap::new));
```

Với `products` là `List` và `stream()` tuần tự, `LinkedHashMap` mặc định giữ **thứ tự chèn khóa lần đầu**. Trên dữ liệu mẫu, nếu `A` xuất hiện trước `B` thì:

```text
firstBySkuInOrder.keySet() -> [A, B]
```

Cần `import java.util.LinkedHashMap;`. `LinkedHashMap` khác `HashMap`: thứ tự iteration được quy định theo chế độ insertion-order mặc định. Gọi merge để thay giá trị của khóa đã có **không tạo lần chèn khóa mới**, nên vị trí khóa không bị đẩy xuống cuối trong chế độ này.

Nếu cần **Map kết quả không sửa được** nhưng vẫn giữ iteration order của `LinkedHashMap`, có thể bao một Map mới do ứng dụng sở hữu:

```java
var mutableOrdered = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::label,
                (a, b) -> b,
                LinkedHashMap::new));

Map<String, String> orderedReadOnly =
        Collections.unmodifiableMap(new LinkedHashMap<>(mutableOrdered));
```

Đây là một **unmodifiable view trên bản sao `LinkedHashMap` riêng**, có bảo đảm về iteration order của backing. Nó khác với `toUnmodifiableMap`: không nên đổi trực tiếp sang `Map.copyOf` rồi kỳ vọng vẫn giữ order, vì `Map.copyOf` không cam kết iteration order.

## 10. Khi nào dùng `groupingBy` thay vì chọn một giá trị?

Nếu mỗi khóa cần giữ **tất cả** bản ghi, việc “giữ đầu”, “giữ cuối” hoặc “max revision” sẽ làm mất thông tin. Dùng:

```java
Map<String, List<Product>> allBySku = products.stream()
        .collect(Collectors.groupingBy(Product::sku));
```

Khi đó, các bản ghi có `sku = "A"` nằm trong một danh sách tương ứng. Cách này phù hợp với nghiệp vụ cần:

- Hiển thị toàn bộ lịch sử thay đổi.
- Phân tích các phiên bản hoặc kiểm toán dữ liệu.
- Thực hiện phép tổng hợp downstream nhiều bước.
- Giữ các bản ghi và ra quyết định sau khi xem đủ thông tin.

Nếu muốn **chọn một giá trị duy nhất** theo quy tắc rõ ràng, `toMap` với merge function thường trực tiếp hơn. Nếu muốn **mỗi khóa gắn với một collection**, `groupingBy` diễn đạt cấu trúc kết quả rõ hơn.

Không có giải pháp “luôn đúng”: đầu tiên cần xác định **trùng khóa có phải lỗi hay là dữ liệu hợp lệ cần xử lý**.

## 11. Khóa trùng được xác định bởi `equals`, không phải chỉ vì chuỗi trông giống nhau

`Collectors.toMap` đánh giá va chạm theo tính bằng nhau của khóa trong Map. Với `String`:

```java
var keys = List.of("JAVA", "java", "Java");

var caseSensitive = keys.stream()
        .collect(Collectors.toMap(
                Function.identity(),
                String::length));
// Có 3 khóa khác nhau vì String.equals phân biệt hoa/thường.

var normalized = keys.stream()
        .collect(Collectors.toMap(
                s -> s.toLowerCase(java.util.Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> existing));
```

`normalized` chỉ có **một khóa `"java"`**, vì `keyMapper` đã chuẩn hóa cả ba chuỗi trước khi đưa vào Map.

Cần quyết định việc chuẩn hóa trước khi chọn merge policy:

- Có phân biệt `"ABC"` và `"abc"` về nghiệp vụ không?
- Chuẩn hóa khoảng trắng, Unicode hoặc chữ hoa/thường có làm hai ID vốn khác nhau bị xem là một không?
- `equals`/`hashCode` của object key có ổn định không?
- Nếu khóa trùng sau chuẩn hóa, phải báo lỗi hay gộp?

Tránh chọn đại một hàm `(a,b) -> a` để “chữa” các collision do thiết kế key chưa đúng. Merge function chỉ xử lý hậu quả của khóa trùng; nó không tự quyết định đúng sai của **quy tắc xác định khóa**.

## 12. Parallel stream: chọn giá trị theo vị trí và chọn theo tiêu chí khác nhau

Với stream song song, collector có thể tạo các Map tạm rồi kết hợp chúng. Vì thế merge function tốt nên có tính **kết hợp** (*associative*): gộp `(a,b)` rồi với `c` cho kết quả tương đương gộp `a` với `(b,c)` theo ý nghĩa bài toán.

Các ví dụ thường thích hợp:

- `Integer::sum` hoặc `Long::sum` để cộng số lượng (chú ý giới hạn kiểu số).
- `Integer::max` hoặc `BinaryOperator.maxBy(comparator)` để chọn giá trị lớn nhất theo một tiêu chí đủ rõ.
- Quy tắc merge hoạt động trên các giá trị bất biến, không có side effect và không phụ thuộc vào đồng hồ hệ thống.

**Giữ “first/last” theo encounter order** là một quyết định phụ thuộc thứ tự. Với stream ordered tuần tự, đây là chính sách dễ kiểm soát. Khi dùng nguồn unordered hoặc `toConcurrentMap` — một **concurrent, unordered collector** — không có cơ sở để coi thứ tự gộp là “bản ghi sớm nhất/muộn nhất” theo nghĩa nghiệp vụ.

Nếu đích thực muốn bản ghi **mới nhất theo thời gian**, hãy dùng trường `timestamp`/`revision` và tie-break rõ ràng, thay vì dựa vào luồng nào hoàn thành trước.

Nếu đích thực muốn **vị trí đầu tiên trong danh sách nguồn**, có thể gắn chỉ số thứ tự vào từng phần tử và lấy min theo chỉ số. Cách này giữ ý nghĩa thứ tự mà không phải suy diễn ngầm theo kế hoạch thực thi.

**Không nhầm:** `UNORDERED` của `toConcurrentMap` khác với `toMap` thông thường. Cả hai đều có thể dùng với parallel streams, nhưng có hợp đồng khác về concurrency và thứ tự. Đọc đúng collector đang dùng thay vì mặc định tất cả Map collector đều là concurrent/unordered.

## 13. Lưu ý `null` và kết quả merge

Với `Collectors.toUnmodifiableMap`, Javadoc quy định rõ:

- `keyMapper` trả `null` → `NullPointerException`.
- `valueMapper` trả `null` → `NullPointerException`.
- `mergeFunction` là `null` (thay vì một hàm) → `NullPointerException` khi tạo collector.

`Collectors.toMap` không cung cấp một lời hứa chung rằng giá trị `null` luôn hợp lệ: overload ba tham số dùng `Map.merge`, trong đó giá trị mới đưa vào merge **phải không phải `null`**. Đừng suy diễn từ việc `HashMap` trực tiếp cho phép `null` sang việc mọi collector Map sẽ chấp nhận `null`.

Nếu dữ liệu có thể chứa giá trị vắng, hãy lựa chọn chính sách:

```java
var cleaned = products.stream()
        .filter(p -> p.sku() != null && p.label() != null)
        .collect(Collectors.toUnmodifiableMap(
                Product::sku,
                Product::label,
                (existing, incoming) -> incoming));
```

Đây chỉ là ví dụ chính sách **loại các phần tử thiếu key/value**. Nếu `null` mang ý nghĩa nghiệp vụ (ví dụ phân biệt “không có key” và “key có giá trị chưa được xác định”), không được âm thầm lọc mà phải thiết kế kết quả khác, dùng kiểu bao như `Optional` khi phù hợp hoặc xây Map theo cách kiểm soát rõ hợp đồng.

Đừng dùng `return null` từ merge function như một cách “bỏ bản ghi trùng” nếu bạn muốn giữ khóa: theo `Map.merge`, điều đó có thể **xóa ánh xạ**, khiến phần tử sau lại thêm khóa vào.

## 14. Ví dụ hoàn chỉnh Java 17+ — nhiều chính sách cho cùng dữ liệu

Tạo tệp `DuplicateKeyPolicyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DuplicateKeyPolicyDemo {
    record Product(String sku, int revision, String label) { }

    static void checkFailure(String label, Runnable task) {
        try {
            task.run();
            System.out.println(label + "=none");
        } catch (IllegalStateException | UnsupportedOperationException
                | NullPointerException ex) {
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        var products = List.of(
                new Product("A", 1, "draft"),
                new Product("B", 1, "base"),
                new Product("A", 3, "final"),
                new Product("A", 2, "review"),
                new Product("B", 2, "updated")
        );

        checkFailure("withoutMerge", () ->
                products.stream().collect(
                        Collectors.toMap(Product::sku, Product::label))
        );

        var first = products.stream().collect(Collectors.toMap(
                Product::sku, Product::label,
                (current, incoming) -> current));

        var last = products.stream().collect(Collectors.toMap(
                Product::sku, Product::label,
                (current, incoming) -> incoming));

        var latest = products.stream().collect(Collectors.toMap(
                Product::sku, Function.identity(),
                BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::revision)
                                .thenComparing(Product::label))));

        var counts = products.stream().collect(Collectors.toMap(
                Product::sku, p -> 1, Integer::sum));

        var ordered = products.stream().collect(Collectors.toMap(
                Product::sku, Product::label,
                (current, incoming) -> current,
                LinkedHashMap::new));

        var immutable = products.stream().collect(
                Collectors.toUnmodifiableMap(
                        Product::sku, Product::label,
                        (current, incoming) -> incoming));

        System.out.println("first=" + new TreeMap<>(first));
        System.out.println("last=" + new TreeMap<>(last));
        System.out.println("latestRevision="
                + new TreeMap<>(latest).get("A").revision());
        System.out.println("counts=" + new TreeMap<>(counts));
        System.out.println("orderedKeys="
                + new ArrayList<>(ordered.keySet()));
        System.out.println("unmodifiable=" + new TreeMap<>(immutable));

        checkFailure("modify", () -> immutable.put("Z", "new"));
        checkFailure("nullValue", () -> Stream.of("X").collect(
                Collectors.toUnmodifiableMap(
                        Function.identity(),
                        s -> (String) null)));
    }
}
```

Chạy:

```bash
javac DuplicateKeyPolicyDemo.java
java DuplicateKeyPolicyDemo
```

Output:

```text
withoutMerge=IllegalStateException
first={A=draft, B=base}
last={A=review, B=updated}
latestRevision=3
counts={A=3, B=2}
orderedKeys=[A, B]
unmodifiable={A=review, B=updated}
modify=UnsupportedOperationException
nullValue=NullPointerException
```

**Giải thích:**

1. `withoutMerge` báo `IllegalStateException` vì khóa `"A"` xuất hiện nhiều lần, mặc dù tất cả các bản ghi đều hợp lệ về cú pháp.
2. `first` giữ `A=draft` và `B=base` từ lần xuất hiện đầu trong stream ordered tuần tự.
3. `last` giữ `A=review` và `B=updated`, là giá trị ở lần xuất hiện cuối của mỗi khóa.
4. `latestRevision=3` khác `last`: phiên bản `A=final` có revision lớn nhất, dù nó không xuất hiện cuối danh sách. Ví dụ này minh họa vì sao “last seen” không đồng nghĩa “latest version”.
5. `counts` không bỏ qua dữ liệu trùng, mà gom số lượng `A`/`B` bằng phép cộng.
6. `orderedKeys=[A, B]` vì Map đích được tạo bằng `LinkedHashMap::new` trong stream có encounter order.
7. `immutable` dùng overload merge của `toUnmodifiableMap`, vừa quyết định collision vừa tạo Map không cho sửa.
8. `nullValue` bị từ chối vì `toUnmodifiableMap` không nhận giá trị null do mapper sinh ra.

**Vì sao output ổn định?** Ví dụ dùng `new TreeMap<>(...)` cho những Map **không có thứ tự iteration được đảm bảo**, thay vì in trực tiếp `HashMap` hoặc kết quả `toUnmodifiableMap`. Chỉ `ordered` được in qua `LinkedHashMap.keySet()` vì chính loại Map và nguồn ordered tuần tự bảo đảm thứ tự chèn khóa.

## 15. Những lỗi thường gặp

| Tình huống | Sai ở đâu? | Hướng xử lý |
| --- | --- | --- |
| `Collectors.toMap(keyMapper, valueMapper)` khi khóa có thể trùng | Mặc định ném `IllegalStateException` | Nếu trùng hợp lệ, cung cấp `mergeFunction`; nếu trùng là lỗi, giữ hành vi fail-fast |
| `(a, b) -> a` để “giữ bản mới nhất” | Chỉ giữ giá trị đã tích lũy; không xem revision/timestamp | Chọn theo comparator/metadata |
| `(a, b) -> b` trên dữ liệu unordered và khẳng định “mới nhất” | Thứ tự gộp không phải thời gian nghiệp vụ | Dùng trường timestamp/revision và tie-break |
| `(a, b) -> null` để “bỏ bản ghi mới” | `Map.merge` hiểu null là **xóa ánh xạ** | Dùng `(a, b) -> a` hoặc `filter` theo ngữ nghĩa cần |
| Dùng `Collectors.toMap(...)` rồi kỳ vọng Map luôn là `HashMap` | API không cam kết implementation | Dùng overload có `mapFactory` khi cần cụ thể |
| Muốn Map unmodifiable nhưng lấy kết quả `toMap` và giả định không sửa được | API `toMap` không cam kết mutability | Dùng `toUnmodifiableMap` (Java 10+) |
| Muốn giữ thứ tự khóa nhưng dùng `toUnmodifiableMap` | Không bảo đảm iteration order | Dùng `LinkedHashMap::new` và unmodifiable wrapper nếu cần |
| `toUnmodifiableMap` với key/value `null` | Javadoc từ chối null | Kiểm tra chính sách dữ liệu rồi filter/validate |
| Chọn một bản ghi trong khi nghiệp vụ cần mọi bản ghi | Mất dữ liệu do merge | Dùng `groupingBy` tạo `Map<K, List<T>>` |
| Kỳ vọng `Integer::sum` an toàn với dữ liệu vượt `int` | Có thể overflow | Chọn kiểu/tổng hợp số phù hợp |
| Dựa vào `Map.toString()` để so sánh kết quả test | Thứ tự Map không luôn cố định | So sánh theo `Map.equals` hoặc sắp xếp khi hiển thị |

## 16. Bài tập tự kiểm tra

Cho danh sách sau và giả sử các import từ `java.util`/`java.util.stream` đã có:

```java
record Entry(String key, int priority, String value) {}

var entries = List.of(
        new Entry("A", 2, "older"),
        new Entry("B", 1, "only"),
        new Entry("A", 5, "newer"),
        new Entry("A", 3, "middle")
);
```

**Câu 1:** Nếu gọi `toMap(Entry::key, Entry::value)` thì sao?

**Đáp án:** Ném `IllegalStateException` vì khóa `A` bị trùng. Việc cả bốn entry đều là object hợp lệ không loại bỏ lỗi va chạm.

**Câu 2:** Với stream ordered tuần tự, `(a,b)->a` và `(a,b)->b` chọn giá trị nào cho `A`?

**Đáp án:** Giữ đầu cho `A=older`; giữ cuối cho `A=middle`. Không cách nào tự xét `priority`.

**Câu 3:** Muốn chọn `A=newer` vì `priority=5`, cần làm gì?

**Đáp án:** Dùng `valueMapper` trả lại toàn bộ `Entry`, sau đó dùng `BinaryOperator.maxBy(Comparator.comparingInt(Entry::priority))` hoặc một comparator có tie-break phù hợp. Nếu chỉ trả `Entry::value` thì đã mất thông tin priority cần so sánh.

**Câu 4:** Muốn giữ tất cả các entry của `A`?

**Đáp án:** Dùng `Collectors.groupingBy(Entry::key)` để có `Map<String, List<Entry>>`, không chọn một đại diện duy nhất.

**Câu 5:** Muốn Map kết quả không cho sửa, có merge function và không chứa null?

**Đáp án:** Dùng `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`. Đây là overload hiện hành từ Java 10, nhưng vẫn cần chủ động xử lý khóa trùng theo quy tắc nghiệp vụ.

## 17. Checklist khi quyết định giữ giá trị nào

1. **Khóa trùng là dữ liệu hợp lệ hay lỗi?** Nếu lỗi, hãy để `toMap` hai tham số báo `IllegalStateException`.
2. **Nếu trùng hợp lệ, giá trị được chọn theo thứ tự xuất hiện hay tiêu chí nghiệp vụ?** Đừng nhầm hai khái niệm.
3. **`valueMapper` có giữ đủ thông tin cho phép so sánh không?** Nếu cần revision, đừng chỉ map ra label.
4. **Comparator có giải quyết tie rõ ràng không?** Cần cân nhắc những bản ghi khác nhau nhưng revision bằng nhau.
5. **Nguồn có thứ tự rõ ràng không?** Nếu không, tránh “first wins/last wins” dựa vào thứ tự ngầm.
6. **Sẽ dùng parallel/concurrent collector không?** Phép gộp nên thuần và có tính kết hợp; với nghiệp vụ thứ tự phải dùng cơ chế chọn rõ.
7. **Cần một Map có thứ tự duyệt không?** `LinkedHashMap::new` ở overload bốn tham số là lựa chọn thích hợp cho stream ordered tuần tự.
8. **Cần Map không sửa được?** Dùng `toUnmodifiableMap` và chú ý null, hoặc xây Map chuyên biệt rồi tạo read-only wrapper nếu có yêu cầu riêng.
9. **Cần giữ mọi giá trị của khóa không?** Cân nhắc `groupingBy` thay vì merge ra một giá trị.
10. **Test có phụ thuộc iteration order không?** So sánh theo `Map.equals` hoặc tạo `TreeMap`/`LinkedHashMap` có hợp đồng thứ tự rõ ràng.

## Kết luận

Khi nhiều phần tử của Stream sinh ra cùng một khóa Map, **phải chủ động thiết kế quy tắc va chạm**. `Collectors.toMap` không có merge function sẽ báo lỗi — hợp lý khi key bắt buộc duy nhất. Nếu trùng khóa là dữ liệu bình thường, overload có `mergeFunction` cho phép **giữ giá trị hiện có, giữ giá trị mới, chọn theo revision/timestamp, hoặc tổng hợp**. Từ Java 10, `Collectors.toUnmodifiableMap` cung cấp lựa chọn tương tự khi cần kết quả không sửa đổi.

**Giữ đầu/cuối** cần hiểu rõ encounter order; **chọn theo tiêu chí** cần comparator/tie-break đúng nghiệp vụ; **giữ tất cả** thì nên dùng `groupingBy`. Tránh hàm gộp có side effect, kết quả null không chủ ý, và mọi giả định về loại/thứ tự Map mà API không cam kết.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Collectors.toMap` và `Collectors.toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): các overload, xử lý khóa trùng, `mergeFunction`, `mapFactory`, ràng buộc null và Map kết quả.
- [Java SE 26 — `Map.merge`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): cơ chế gộp hai giá trị và trường hợp kết quả null xóa ánh xạ.
- [Java SE 26 — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự chèn ổn định cho Map được chọn bằng `mapFactory`.
- [Java SE 26 — `Collectors.groupingBy`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#groupingBy(java.util.function.Function)): lưu toàn bộ phần tử tương ứng với một khóa.
- [Java SE 26 — `Collectors.toConcurrentMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toConcurrentMap(java.util.function.Function,java.util.function.Function,java.util.function.BinaryOperator)): khác biệt khi cần collector concurrent, unordered.
