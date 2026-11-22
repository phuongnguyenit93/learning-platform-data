# `Map.Entry.comparingByKey()` và `Map.Entry.comparingByValue()` (Java 8+)

Trong Java, khi cần **sắp xếp các cặp khóa–giá trị của một `Map<K,V>`**, ta thường lấy `map.entrySet()` rồi sử dụng `Stream.sorted(...)` với một `Comparator<Map.Entry<K,V>>`. Thay vì viết lambda dài như `(a,b) -> a.getKey().compareTo(b.getKey())`, Java 8 cung cấp sẵn bốn factory method trong `Map.Entry`: hai nhóm **`comparingByKey`** và **`comparingByValue`**, mỗi nhóm có overload theo thứ tự tự nhiên hoặc theo một `Comparator` tùy chọn.

Hai nhóm API giải quyết những yêu cầu khác nhau:

- **`Map.Entry.comparingByKey(...)`:** so sánh hai entry bằng **khóa** của chúng.
- **`Map.Entry.comparingByValue(...)`:** so sánh hai entry bằng **giá trị** của chúng.

Điểm quan trọng: **Comparator chỉ xác định thứ tự giữa các entry; nó không tự sắp xếp lại cấu trúc `Map` gốc**. Muốn lấy kết quả đã sắp, ta cần một terminal operation như `collect(toList())` hoặc thu các entry vào `LinkedHashMap` theo thứ tự mới.

Các phương thức trong bài **đã có từ Java 8 và vẫn được hỗ trợ ở các JDK hiện đại**. Chương trình hoàn chỉnh dùng Java 8 API và có thể biên dịch/chạy bằng JDK 17+.

## 1. Vì sao phải dùng `entrySet()`?

Một `Map<K,V>` gồm nhiều mapping: mỗi mapping là một **`Map.Entry<K,V>`** với `getKey()` và `getValue()`. Các view thông dụng:

| Lời gọi | Phần tử của kết quả | Dùng khi nào |
| --- | --- | --- |
| `map.keySet()` | Chỉ khóa `K` | Duyệt, tìm hoặc sắp **khóa** mà không cần giá trị |
| `map.values()` | Chỉ giá trị `V` | Xử lý giá trị mà không cần biết chúng thuộc khóa nào |
| `map.entrySet()` | `Map.Entry<K,V>` | Vừa giữ khóa vừa giữ giá trị, cần sắp theo một trong hai tiêu chí |
| `map.entrySet().stream()` | `Stream<Map.Entry<K,V>>` | Tạo pipeline xử lý và sắp xếp entry |

Ví dụ:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("gamma", 80);
scores.put("alpha", 95);
scores.put("beta", 80);
scores.put("delta", 60);
```

Ở đây `Map.Entry<String,Integer>` là một cặp như `gamma=80`. Muốn sắp các entry theo điểm nhưng vẫn biết điểm thuộc người nào, **`scores.values().stream()` không đủ**, vì nó làm mất mối liên hệ với khóa. Hãy dùng `scores.entrySet().stream()`.

**Ghi chú về iteration order:** `LinkedHashMap` mặc định duyệt theo thứ tự chèn (`gamma`, `alpha`, `beta`, `delta`). `HashMap` không cam kết thứ tự duyệt; `TreeMap` sắp theo khóa, không sắp theo giá trị. Những khác biệt này rất quan trọng khi có **nhiều entry có cùng điểm**.

## 2. Bốn overload: chữ ký và hợp đồng

`Map.Entry` là interface lồng trong `java.util.Map`; các phương thức `comparingByKey` và `comparingByValue` là **static methods**, không phải các method của một entry đơn lẻ.

Dưới đây là chữ ký generic (định dạng lại từ API):

```java
// (1) So sánh khóa theo thứ tự tự nhiên:
static <K extends Comparable<? super K>, V>
Comparator<Map.Entry<K, V>> comparingByKey();

// (2) So sánh khóa bằng comparator riêng:
static <K, V>
Comparator<Map.Entry<K, V>> comparingByKey(Comparator<? super K> cmp);

// (3) So sánh giá trị theo thứ tự tự nhiên:
static <K, V extends Comparable<? super V>>
Comparator<Map.Entry<K, V>> comparingByValue();

// (4) So sánh giá trị bằng comparator riêng:
static <K, V>
Comparator<Map.Entry<K, V>> comparingByValue(Comparator<? super V> cmp);
```

Bảng ý nghĩa:

| Factory | Tiêu chí | Ràng buộc kiểu | Ví dụ |
| --- | --- | --- | --- |
| `comparingByKey()` | Khóa tăng theo natural order | `K` phải `Comparable` | Khóa `String` A–Z, `Integer` nhỏ–lớn |
| `comparingByKey(cmp)` | Khóa theo `cmp` | Không đòi `K` tự `Comparable` | Khóa giảm dần, không phân biệt hoa/thường |
| `comparingByValue()` | Giá trị tăng theo natural order | `V` phải `Comparable` | Điểm số tăng dần |
| `comparingByValue(cmp)` | Giá trị theo `cmp` | Không đòi `V` tự `Comparable` | Điểm giảm dần, null đứng cuối |

**`comparingByKey()` và `comparingByValue()` không có đối số** dùng natural order, tức thứ tự do `Comparable.compareTo(...)` định nghĩa. Chúng ném `NullPointerException` nếu cần so sánh một entry có khóa hoặc giá trị tương ứng là `null`.

Với overload nhận comparator, bạn **chịu trách nhiệm lựa chọn comparator phù hợp**. Chẳng hạn, muốn chấp nhận giá trị null, cần đưa `Comparator.nullsFirst(...)` hoặc `Comparator.nullsLast(...)` vào đúng vị trí; `Comparator.naturalOrder()` đơn lẻ không xử lý null.

## 3. Sắp theo khóa bằng `comparingByKey`

### 3.1. Khóa tăng dần theo natural order

```java
List<Map.Entry<String, Integer>> byKey = scores.entrySet().stream()
    .sorted(Map.Entry.comparingByKey())
    .collect(Collectors.toList());
```

Với `scores` nêu ở mục 1, kết quả:

```text
[alpha=95, beta=80, delta=60, gamma=80]
```

Đây là thứ tự natural của `String` (với các khóa chữ thường ASCII ở ví dụ). **Không phải** thứ tự ngôn ngữ của mọi locale. Khi dữ liệu có dấu tiếng Việt, ký tự Unicode hoặc quy tắc phân biệt hoa/thường, cần cân nhắc comparator theo yêu cầu sản phẩm.

### 3.2. Khóa giảm dần

Dùng overload có comparator:

```java
List<Map.Entry<String, Integer>> byKeyDescending =
    scores.entrySet().stream()
        .sorted(Map.Entry.comparingByKey(Comparator.reverseOrder()))
        .collect(Collectors.toList());
```

Kết quả:

```text
[gamma=80, delta=60, beta=80, alpha=95]
```

Một cách diễn đạt tương đương là lấy comparator tự nhiên rồi `reversed()`:

```java
Comparator<Map.Entry<String, Integer>> keyDescending =
    Map.Entry.<String, Integer>comparingByKey().reversed();
```

Việc ghi rõ type witness `<String, Integer>` đôi khi giúp trình biên dịch suy luận generic khi gọi chuỗi `reversed()`/`thenComparing(...)`.

### 3.3. So sánh khóa theo quy tắc riêng

Ví dụ, nếu các khóa chứa chữ hoa và chữ thường và bài toán muốn gom **thứ tự so sánh** không phân biệt hoa/thường:

```java
Comparator<Map.Entry<String, Integer>> ignoreCase =
    Map.Entry.comparingByKey(String.CASE_INSENSITIVE_ORDER);
```

**Chú ý:** comparator chỉ làm thay đổi cách **sắp entry**, không tự biến `"Java"` và `"java"` thành một key duy nhất trong `HashMap`. Hai entry có thể cùng tồn tại và có so sánh bằng `0`; nếu cần thứ tự duy nhất, thêm điều kiện phụ:

```java
Comparator<Map.Entry<String, Integer>> ignoreCaseThenExact =
    Map.Entry.<String, Integer>comparingByKey(
            String.CASE_INSENSITIVE_ORDER)
        .thenComparing(Map.Entry.comparingByKey());
```

Với tên có dấu và thứ tự theo ngôn ngữ, có thể cân nhắc `java.text.Collator` theo `Locale` được lựa chọn rõ ràng, thay vì mặc định cho rằng natural order của `String` là thứ tự chữ cái theo tiếng Việt. Comparator nên được thiết kế và kiểm thử với dữ liệu thực tế.

## 4. Sắp theo giá trị bằng `comparingByValue`

### 4.1. Điểm tăng dần

```java
List<Map.Entry<String, Integer>> byValue =
    scores.entrySet().stream()
        .sorted(Map.Entry.comparingByValue())
        .collect(Collectors.toList());
```

Kết quả từ `LinkedHashMap` ở mục 1:

```text
[delta=60, gamma=80, beta=80, alpha=95]
```

Đối với `Integer`, natural order là tăng dần theo số. Cả `gamma=80` và `beta=80` có giá trị bằng nhau; thứ tự tương đối `gamma` trước `beta` ở đây xuất phát từ **encounter order** của `LinkedHashMap` và tính **stable** của `Stream.sorted` trên một stream ordered, không phải do `comparingByValue` tự sắp khóa phụ.

### 4.2. Điểm giảm dần

```java
List<Map.Entry<String, Integer>> descending =
    scores.entrySet().stream()
        .sorted(Map.Entry.comparingByValue(Comparator.reverseOrder()))
        .collect(Collectors.toList());
```

Kết quả:

```text
[alpha=95, gamma=80, beta=80, delta=60]
```

Đối với giá trị natural-order, cũng có thể viết:

```java
Comparator<Map.Entry<String, Integer>> byValueDesc =
    Map.Entry.<String, Integer>comparingByValue().reversed();
```

Hai cách trên đều đảo thứ tự **theo giá trị**. Nếu điểm bằng nhau, chúng không tự tạo tiêu chí sắp thứ hai theo khóa.

**Lưu ý với giá trị null:** `Comparator.reverseOrder()` không giải quyết null. Muốn giảm dần nhưng null đứng **cuối**, dùng `Map.Entry.comparingByValue(Comparator.nullsLast(Comparator.reverseOrder()))`, không đơn thuần `comparingByValue().reversed()` trên nguồn có null.

### 4.3. Giá trị là đối tượng không implement `Comparable`

Giả sử `Map<String, Product>` với `Product` có `getPrice()` kiểu `int` nhưng không implements `Comparable<Product>`. Overload không tham số `comparingByValue()` **không dùng được** vì `V` chưa có natural order. Cách đúng là truyền comparator cho `Product`:

```java
Comparator<Map.Entry<String, Product>> byProductPrice =
    Map.Entry.comparingByValue(
        Comparator.comparingInt(Product::getPrice));
```

Đoạn trên **chỉ là minh họa**: cần có lớp `Product` và `getPrice()` thực tế. Điểm chính là `comparingByValue(cmp)` có thể sắp các value object bất kỳ miễn bạn cung cấp thứ tự so sánh phù hợp. Tương tự, `comparingByKey(cmp)` dùng được cho khóa chưa implements `Comparable`.

## 5. Kết hợp điều kiện phụ bằng `thenComparing`

Chỉ sắp theo điểm có thể chưa đủ cho một **bảng xếp hạng cần kết quả xác định**. Ví dụ hai người có điểm 80: `gamma` và `beta`. Nếu đầu vào là `HashMap`, encounter order không được cam kết; nếu đầu vào là `LinkedHashMap`, sort ổn định giữ thứ tự chèn, nhưng đó chưa chắc là quy tắc nghiệp vụ mong muốn.

Yêu cầu thường gặp: **điểm giảm dần; nếu bằng điểm thì khóa tăng dần**.

```java
Comparator<Map.Entry<String, Integer>> ranking =
    Map.Entry.<String, Integer>comparingByValue()
        .reversed()
        .thenComparing(Map.Entry.comparingByKey());

List<Map.Entry<String, Integer>> ranked =
    scores.entrySet().stream()
        .sorted(ranking)
        .collect(Collectors.toList());
```

Kết quả:

```text
[alpha=95, beta=80, gamma=80, delta=60]
```

Cách đọc theo thứ tự:

1. `comparingByValue()`: comparator điểm tăng.
2. `reversed()`: đổi thành điểm giảm.
3. `thenComparing(comparingByKey())`: nếu điểm bằng nhau, sắp khóa tăng.

**Vị trí gọi `reversed()` rất quan trọng.** Nếu đảo toàn bộ comparator *sau khi đã thêm* `thenComparing`, cả điều kiện phụ cũng đảo:

```java
// Cẩn thận: đảo cả thứ tự điểm LẪN thứ tự khóa phụ.
Comparator<Map.Entry<String, Integer>> bothReversed =
    Map.Entry.<String, Integer>comparingByValue()
        .thenComparing(Map.Entry.comparingByKey())
        .reversed();
```

Ví dụ này cho điểm giảm, nhưng khi hai điểm bằng nhau, **khóa cũng giảm**. Với yêu cầu điểm giảm và khóa tăng, hãy đảo comparator của điểm **trước** khi `thenComparing`, như mẫu `ranking`.

### `sorted` stable không có nghĩa tự giải quyết tie

Theo hợp đồng `Stream.sorted(comparator)`:

- Với **ordered stream**, sort là **stable**: những phần tử mà comparator coi là bằng nhau giữ thứ tự tương đối trước khi sort.
- Với **unordered stream**, Java **không cam kết stability**.
- `LinkedHashMap.entrySet().stream()` có thứ tự duyệt xác định theo map; `HashMap.entrySet().stream()` không có encounter order được bảo đảm. Vì thế thứ tự tie khi chỉ dùng `comparingByValue()` có thể không ổn định theo nguồn.
- Viết một **tie-breaker minh bạch** cho báo cáo, API phân trang, test snapshot và dữ liệu cần sắp ổn định theo quy tắc nghiệp vụ.

**Điều kiện phụ cũng phải đủ phân biệt các phần tử nếu bạn muốn tổng thứ tự hoàn toàn xác định.** Ví dụ, dùng `String.CASE_INSENSITIVE_ORDER` ở điều kiện phụ có thể vẫn coi hai khóa khác nhau về chữ hoa/thường là bằng nhau. Bổ sung một tiêu chí so sánh khác nếu điều đó có ý nghĩa.

## 6. Khóa hoặc giá trị `null`: quy tắc so sánh phải rõ ràng

Một số map như `HashMap` và `LinkedHashMap` chấp nhận giá trị `null`. Với natural comparator:

```java
Map<String, Integer> ratings = new LinkedHashMap<>();
ratings.put("x", null);
ratings.put("y", 2);
ratings.put("z", 1);

// Có thể ném NullPointerException khi sort phải so sánh null:
// ratings.entrySet().stream()
//     .sorted(Map.Entry.comparingByValue())
//     .collect(Collectors.toList());
```

Hãy quyết định rõ null đứng **đầu hay cuối**, rồi truyền comparator có chính sách null:

```java
List<Map.Entry<String, Integer>> nullsLast =
    ratings.entrySet().stream()
        .sorted(Map.Entry.comparingByValue(
            Comparator.nullsLast(Comparator.naturalOrder())))
        .collect(Collectors.toList());
```

Kết quả:

```text
[z=1, y=2, x=null]
```

Một số biến thể:

```java
// Null trước, số tăng:
Map.Entry.comparingByValue(
    Comparator.nullsFirst(Comparator.<Integer>naturalOrder()));

// Null sau, số giảm:
Map.Entry.comparingByValue(
    Comparator.nullsLast(Comparator.<Integer>reverseOrder()));

// Null trước, số giảm:
Map.Entry.comparingByValue(
    Comparator.nullsFirst(Comparator.<Integer>reverseOrder()));
```

Các dòng trên là **biểu thức comparator minh họa**, không phải chương trình chạy độc lập.

### Khóa null và `comparingByKey`

`HashMap` / `LinkedHashMap` có thể chứa **khóa `null`**. `Map.Entry.comparingByKey()` theo natural order **không hỗ trợ so sánh khóa null**; nếu có phép so sánh chạm tới null, nó ném `NullPointerException`. Có thể viết:

```java
Comparator<Map.Entry<String, Integer>> nullableKeys =
    Map.Entry.comparingByKey(
        Comparator.nullsFirst(Comparator.naturalOrder()));
```

Cách này chỉ có ý nghĩa nếu **chính map nguồn cho phép khóa null**. `ConcurrentHashMap` không chấp nhận key/value null; `Map.of(...)` (Java 9+) cũng không chấp nhận null. Không nên đưa giả định "mọi Map đều có thể chứa null" vào thiết kế.

### Không chỉ dựa vào việc một test nhỏ không ném lỗi

Một collection có đúng **một** entry null có thể không cần thực hiện bất kỳ phép so sánh nào trong `sorted`, nên chương trình không ném exception ở test đó. Điều này **không** biến natural comparator thành comparator xử lý null an toàn. Quy định null ngay trong comparator và kiểm thử ít nhất hai phần tử.

## 7. Sắp xếp thành `List<Map.Entry<K,V>>` hay một `Map` mới?

### 7.1. Chỉ cần hiển thị danh sách đã xếp hạng

Dùng `List<Map.Entry<K,V>>`:

```java
List<Map.Entry<String, Integer>> ranked =
    scores.entrySet().stream()
        .sorted(ranking)
        .collect(Collectors.toList());
```

Mọi entry vẫn có `getKey()` và `getValue()`, rất tiện để hiển thị bảng xếp hạng, xuất dữ liệu hoặc lấy top-N.

**Tuy nhiên:** entry thu trực tiếp từ `map.entrySet()` có thể là một đối tượng **liên kết với backing map**. Không giả định lưu `List<Map.Entry<...>>` này thật lâu thì nó trở thành bản sao dữ liệu bất biến độc lập; xem mục 9 về snapshot.

### 7.2. Muốn một map mới duyệt theo thứ tự giá trị đã sắp

Dùng `LinkedHashMap` làm đích sau khi sort:

```java
Map<String, Integer> rankedMap = scores.entrySet().stream()
    .sorted(ranking)
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue,
        (left, right) -> left,
        LinkedHashMap::new
    ));
```

Kết quả khi duyệt `rankedMap`:

```text
{alpha=95, beta=80, gamma=80, delta=60}
```

Ở đây:

- `sorted(ranking)` sắp thứ tự **entry** trước.
- `Map.Entry::getKey` và `Map.Entry::getValue` lấy lại khóa/giá trị để tạo map mới.
- `(left, right) -> left` là **merge function** cho overload `toMap` bốn tham số. Với nguồn trực tiếp từ `entrySet()` của một `Map` bình thường, khóa vốn đã duy nhất; lambda này chỉ cung cấp hợp đồng cần thiết cho API, **không phải cách xử lý trùng nghiệp vụ phổ quát**.
- `LinkedHashMap::new` bảo đảm bản đồ kết quả duyệt theo **thứ tự chèn**, do đó thể hiện thứ tự từ stream đã sắp khi pipeline tuần tự có thứ tự.

**Không nên thay `LinkedHashMap::new` bằng `HashMap::new` nếu thứ tự kết quả là yêu cầu**. `Collectors.toMap(...)` không có factory cũng không cam kết insertion order.

### 7.3. Tại sao không dùng `TreeMap` để sắp theo giá trị?

`TreeMap<K,V>` luôn tổ chức mapping theo **khóa `K`**, dùng `Comparator<? super K>` hoặc natural order của `K`. Không thể dùng `Map.Entry.comparingByValue()` làm comparator của một `TreeMap<String,Integer>`: nó so sánh **`Map.Entry`**, không so sánh `String` keys.

Không nên viết một comparator cho `TreeMap` tìm `map.get(key)` rồi so theo **value** của một map khác:

- Giá trị có thể thay đổi, khiến invariant cấu trúc tree không còn hợp lệ.
- Hai khóa có cùng giá trị có thể bị so là bằng nhau (`compare == 0`), làm một khóa bị coi như trùng với khóa khác.
- Comparator phụ thuộc dữ liệu ngoài khó giữ được hợp đồng nhất quán.

Nếu muốn bảng xếp hạng theo giá trị: **sắp `entrySet()` thành danh sách** hoặc chèn các entry đã sắp vào `LinkedHashMap`. Nếu muốn map theo thứ tự khóa: dùng `TreeMap` với comparator **của khóa**.

## 8. Lấy top-N, cực đại/cực tiểu và quy tắc độ phức tạp

### Top-N theo giá trị

```java
List<Map.Entry<String, Integer>> top2 =
    scores.entrySet().stream()
        .sorted(ranking)
        .limit(2)
        .collect(Collectors.toList());
// [alpha=95, beta=80]
```

Hãy đặt `limit(2)` **sau `sorted(ranking)`**. Nếu giới hạn trước, bạn chỉ xét một nhóm entry đầu tiên của nguồn và có thể bỏ sót giá trị tốt hơn.

Tie-breaker trong `ranking` quyết định kết quả ổn định khi có hai người bằng điểm ở ranh giới top-N.

### Chỉ tìm một entry lớn nhất/nhỏ nhất

Không cần sắp toàn bộ danh sách nếu chỉ muốn một extrema:

```java
Optional<Map.Entry<String, Integer>> highest =
    scores.entrySet().stream()
        .max(Map.Entry.comparingByValue());

Optional<Map.Entry<String, Integer>> lowest =
    scores.entrySet().stream()
        .min(Map.Entry.comparingByValue());
```

Với bảng ví dụ, `highest` là `alpha=95` và `lowest` là `delta=60`. `Optional` rỗng khi map rỗng. Nếu có **nhiều extrema bằng nhau**, đừng giả định comparator chỉ theo value chọn entry nào theo nghiệp vụ; cung cấp tie-breaker rõ ràng hoặc xử lý toàn bộ các entry cùng giá trị.

**Chi phí điển hình:**

| Thao tác | Chi phí thường gặp với `n` entry | Khi phù hợp |
| --- | --- | --- |
| `stream().max/min(comparator)` | Khoảng `O(n)` lần so sánh | Chỉ cần một cực trị |
| `stream().sorted(comparator).collect(toList())` | Khoảng `O(n log n)`, cần lưu thứ tự | Cần xem toàn bộ entry đã sắp |
| `sorted(...).limit(k)` | Vẫn thường trả giá cho sort toàn bộ nguồn | Dữ liệu vừa và nhỏ, ưu tiên sự rõ ràng |
| Thu vào `LinkedHashMap` sau sort | Thêm bước tạo map mới và bộ nhớ | Muốn tiếp tục dùng API `Map` với thứ tự duyệt kết quả |
| Priority queue cho top-k | Có thể đạt khoảng `O(n log k)` | Dữ liệu rất lớn, `k` nhỏ, đã xác nhận nhu cầu tối ưu |

Các mức là đánh giá thuật toán phổ biến, **không phải cam kết tuyệt đối của JVM hay collector**. Với dataset nhỏ, code dễ hiểu thường quan trọng hơn tối ưu sớm. Với dữ liệu lớn hoặc comparator đắt, cần benchmark bằng dữ liệu đại diện.

## 9. `Map.Entry` có thể liên kết với map gốc: cần hiểu snapshot

`map.entrySet()` là một **view** của map. Theo hợp đồng `Map.Entry`, các entry lấy từ quá trình iteration có thể liên kết với backing map; việc dùng chúng ngoài vòng đời iteration hoặc sau khi map bị sửa có thể dẫn đến kết quả không được bảo đảm tùy implementation.

Vì vậy:

- `sorted(...)` **không tự thay đổi map gốc**. Nó tạo một pipeline có thứ tự mới; terminal operation tạo kết quả.
- `collect(toList())` chứa **tham chiếu entry**, không tự tạo bản sao khóa và giá trị.
- Đừng sửa map đang được duyệt từ một `Comparator`, `peek` hay callback của stream. Điều này vi phạm yêu cầu **non-interference** của Stream API và có thể gây `ConcurrentModificationException` hoặc kết quả sai.
- Nếu cần giữ danh sách đã sắp **độc lập với vòng đời map**, hãy sao chép các cặp khóa–giá trị.

Cách tạo entry snapshot dùng API có từ trước Java 8:

```java
List<Map.Entry<String, Integer>> snapshot =
    scores.entrySet().stream()
        .map(AbstractMap.SimpleImmutableEntry::new)
        .sorted(Map.Entry.comparingByKey())
        .collect(Collectors.toList());
```

`AbstractMap.SimpleImmutableEntry` giữ cặp khóa/giá trị của mỗi entry trong object không cho `setValue`; nó không gắn việc đọc `getValue()` với map gốc. Ví dụ dùng `String` và `Integer` (đều bất biến) nên snapshot đủ cho mục đích báo cáo.

**Snapshot này chỉ là shallow copy:** nếu value là một đối tượng mutable (như `List`) và vẫn bị thay đổi qua tham chiếu bên ngoài, nội dung object value có thể thay đổi. Muốn deep immutable cần sao chép/thiết kế kiểu value tương ứng.

Từ **Java 17**, có thêm:

```java
// Java 17+, không dùng dòng này khi biên dịch Java 8:
List<Map.Entry<String, Integer>> snapshot17 =
    scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .collect(Collectors.toList());
```

`Map.Entry.copyOf` tạo entry độc lập, không sửa được, nhưng **không cho khóa/giá trị null**. Đây là lựa chọn hiện đại khi target JDK từ 17 và điều kiện null phù hợp. Ví dụ chính của bài vẫn dùng `SimpleImmutableEntry` để tương thích Java 8.

## 10. Comparator đúng hợp đồng: tránh kết quả khó dự đoán

Comparator phải xác định một thứ tự hợp lý và nhất quán. Với hai phần tử `a`, `b`:

- Kết quả âm: `a` đứng trước `b`.
- Kết quả 0: comparator xem hai phần tử có thứ tự ngang nhau ở tiêu chí đó.
- Kết quả dương: `a` đứng sau `b`.

Cần đáp ứng **tính phản đối xứng dấu**, **bắc cầu** và **tính nhất quán của kết quả so sánh** theo `Comparator`. Một comparator sai có thể khiến quá trình sort đưa ra kết quả không ổn định hoặc ném `IllegalArgumentException` trong một số triển khai.

### Không trừ số để so sánh

Tránh:

```java
// Sai tiềm ẩn tràn int:
// (a, b) -> a.getValue() - b.getValue()
```

Hai số `int` lớn có thể tràn, làm kết quả so sánh sai dấu. Dùng API chuẩn:

```java
Comparator<Map.Entry<String, Integer>> safe =
    Map.Entry.comparingByValue(Integer::compare);
```

Hoặc đơn giản hơn `Map.Entry.comparingByValue()` nếu `Integer` không null.

### So sánh số thực và độ chính xác

Với `Double`, `Double.compare` có quy tắc riêng về `NaN`, `+0.0` và `-0.0`. Với tiền hoặc số thập phân cần chính xác, `BigDecimal` thường hợp lý hơn `double` tùy yêu cầu nghiệp vụ. Lưu ý `BigDecimal.compareTo` có thể coi `1.0` và `1.00` là ngang nhau dù `equals` khác. **Sắp danh sách entry** với comparator trả 0 vẫn giữ đủ entry; nhưng nếu dùng comparator như vậy để điều khiển **khóa trong `TreeMap/TreeSet`**, hai giá trị compare 0 có thể bị xem là cùng khóa/phần tử.

### Phép so sánh phụ thuộc dữ liệu thay đổi

Không nên viết comparator đọc một biến trạng thái mutable hay gọi tới mạng/cơ sở dữ liệu trong mỗi lần compare. Nếu dữ liệu thay đổi trong lúc sort, comparator có thể cho kết quả không nhất quán. Tính giá trị dùng để sort trước hoặc dùng các snapshot ổn định.

### Vấn đề kiểu generic

Cú pháp như:

```java
Map.Entry.<String, Integer>comparingByValue()
```

là cách chỉ rõ hai type parameter của static generic method. Nó đặc biệt hữu ích khi tiếp tục gọi `reversed()` hoặc `thenComparing(...)` và trình biên dịch không suy luận đủ thông tin từ ngữ cảnh. Không nên dùng raw type `Map.Entry` hay ép kiểu unchecked chỉ để làm comparator compile.

## 11. `sorted`, encounter order và stream song song

`sorted(comparator)` là **stateful intermediate operation**: việc trả thứ tự toàn cục thường đòi nhìn nhiều/đủ phần tử trước khi kết quả được tiêu thụ. Nó không nhất thiết rẻ khi dữ liệu lớn.

- Với một nguồn có encounter order (ví dụ `LinkedHashMap.entrySet()` hoặc một `List`), `sorted` **stable** theo hợp đồng.
- Với `HashMap.entrySet()`, không dựa vào thứ tự ban đầu khi comparator so hai entry bằng nhau.
- Với **parallel stream**, `sorted` vẫn có thể tạo kết quả đúng theo comparator và encounter order do API cam kết, nhưng chi phí phối hợp/sắp xếp có thể lớn; không tự cho rằng chạy song song nhanh hơn.
- `parallelStream().sorted(...).forEach(...)` có thể in theo thứ tự không xác định vì `forEach` không cam kết encounter order. Nếu thực sự cần gọi hành động theo thứ tự đã sắp, dùng `forEachOrdered(...)` hoặc `collect(toList())` rồi duyệt tuần tự.
- Nếu chỉ lấy bảng xếp hạng có thứ tự ổn định và dataset vừa phải, pipeline `entrySet().stream().sorted(...).collect(toList())` thường dễ đọc, dễ kiểm thử.

**Một comparator với tie-breaker rõ ràng** đáng tin hơn dựa vào thứ tự gặp vô tình của `HashMap`. Khi yêu cầu đầu ra là API phân trang, sự ổn định giữa hai lần truy vấn còn phụ thuộc việc **dữ liệu nguồn có thay đổi hay không**, không chỉ comparator.

## 12. Chương trình Java hoàn chỉnh và kết quả kiểm chứng

Tạo file **`EntryComparatorsDemo.java`**. Chương trình dùng API Java 8, chạy được trên JDK 17+ và thể hiện:

1. So sánh entry theo khóa tăng/giảm.
2. So sánh entry theo value tăng/giảm.
3. Quy tắc tie-break **value giảm, key tăng**.
4. Lấy top-2.
5. Tạo `LinkedHashMap` duyệt theo thứ tự xếp hạng.
6. Sắp giá trị `null` xuống cuối.
7. Sao chép entry độc lập bằng `SimpleImmutableEntry`.
8. Xác nhận map gốc không thay đổi.

```java
import java.util.*;
import java.util.stream.Collectors;

public class EntryComparatorsDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("gamma", 80);
        scores.put("alpha", 95);
        scores.put("beta", 80);
        scores.put("delta", 60);

        List<Map.Entry<String, Integer>> byKey = scores.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .collect(Collectors.toList());

        List<Map.Entry<String, Integer>> byKeyDescending =
                scores.entrySet().stream()
                    .sorted(Map.Entry.comparingByKey(Comparator.reverseOrder()))
                    .collect(Collectors.toList());

        List<Map.Entry<String, Integer>> byValue = scores.entrySet().stream()
                .sorted(Map.Entry.comparingByValue())
                .collect(Collectors.toList());

        List<Map.Entry<String, Integer>> byValueDescending =
                scores.entrySet().stream()
                    .sorted(Map.Entry.comparingByValue(Comparator.reverseOrder()))
                    .collect(Collectors.toList());

        Comparator<Map.Entry<String, Integer>> ranking =
                Map.Entry.<String, Integer>comparingByValue()
                    .reversed()
                    .thenComparing(Map.Entry.comparingByKey());

        List<Map.Entry<String, Integer>> byRank = scores.entrySet().stream()
                .sorted(ranking)
                .collect(Collectors.toList());

        List<Map.Entry<String, Integer>> top2 = scores.entrySet().stream()
                .sorted(ranking)
                .limit(2)
                .collect(Collectors.toList());

        LinkedHashMap<String, Integer> sortedMap = scores.entrySet().stream()
                .sorted(ranking)
                .collect(Collectors.toMap(
                        Map.Entry::getKey,
                        Map.Entry::getValue,
                        (left, right) -> left,
                        LinkedHashMap::new));

        Map<String, Integer> nullable = new LinkedHashMap<>();
        nullable.put("x", null);
        nullable.put("y", 2);
        nullable.put("z", 1);

        List<Map.Entry<String, Integer>> nullsLast =
                nullable.entrySet().stream()
                    .sorted(Map.Entry.comparingByValue(
                            Comparator.nullsLast(Comparator.naturalOrder())))
                    .collect(Collectors.toList());

        List<Map.Entry<String, Integer>> snapshot = scores.entrySet().stream()
                .map(AbstractMap.SimpleImmutableEntry::new)
                .sorted(Map.Entry.comparingByKey())
                .collect(Collectors.toList());

        System.out.println("original map: " + scores);
        System.out.println("by key: " + byKey);
        System.out.println("by key descending: " + byKeyDescending);
        System.out.println("by value: " + byValue);
        System.out.println("by value descending: " + byValueDescending);
        System.out.println("by value desc, key asc: " + byRank);
        System.out.println("top 2: " + top2);
        System.out.println("ranked LinkedHashMap: " + sortedMap);
        System.out.println("nulls last: " + nullsLast);
        System.out.println("snapshot: " + snapshot);
        System.out.println("original unchanged: " + scores);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 EntryComparatorsDemo.java
java EntryComparatorsDemo
```

Kết quả chuẩn:

```text
original map: {gamma=80, alpha=95, beta=80, delta=60}
by key: [alpha=95, beta=80, delta=60, gamma=80]
by key descending: [gamma=80, delta=60, beta=80, alpha=95]
by value: [delta=60, gamma=80, beta=80, alpha=95]
by value descending: [alpha=95, gamma=80, beta=80, delta=60]
by value desc, key asc: [alpha=95, beta=80, gamma=80, delta=60]
top 2: [alpha=95, beta=80]
ranked LinkedHashMap: {alpha=95, beta=80, gamma=80, delta=60}
nulls last: [z=1, y=2, x=null]
snapshot: [alpha=95, beta=80, delta=60, gamma=80]
original unchanged: {gamma=80, alpha=95, beta=80, delta=60}
```

Giải thích các chi tiết dễ nhầm:

- `original map` giữ thứ tự chèn `gamma`, `alpha`, `beta`, `delta`; các thao tác sắp trong pipeline không làm đổi `scores`.
- `by key` và `by key descending` là hai cách so khóa `String`.
- `by value` giữ `gamma=80` trước `beta=80` vì input là `LinkedHashMap` có encounter order, và `sorted` stable đối với ordered stream.
- `by value descending` cũng giữ `gamma` trước `beta` khi bằng điểm. Nó không tự so khóa phụ.
- `by value desc, key asc` chủ động đặt `beta` trước `gamma` với điều kiện phụ `comparingByKey()`.
- `ranked LinkedHashMap` là một map **mới** mang iteration order theo xếp hạng; `TreeMap` không giải quyết thứ tự value này.
- `nulls last` dùng comparator riêng, tránh áp đặt natural comparison lên value null.
- `snapshot` dùng `SimpleImmutableEntry` để tách entry khỏi backing map, tiện lưu/đọc lâu hơn; với giá trị mutable, vẫn cần cân nhắc deep copy.

## 13. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `comparingByKey()` khi muốn xếp theo điểm | Chỉ sắp theo khóa | Dùng `comparingByValue()` |
| Gọi `comparingByValue()` trên `map.values().stream()` | Comparator cần `Map.Entry`, không phải `V` | Sử dụng `map.entrySet().stream()` |
| Nghĩ gọi `sorted(...)` đã sửa thứ tự map gốc | Stream pipeline không biến đổi map gốc | Thu ra list/map mới phù hợp |
| Thu về `HashMap` rồi kỳ vọng duyệt theo thứ tự đã sort | `HashMap` không cam kết iteration order | `LinkedHashMap::new` khi cần giữ thứ tự chèn |
| Dùng `TreeMap` để sắp theo value | `TreeMap` sắp theo **key** | Sort `entrySet()` theo value |
| Dùng `comparingByValue()` với value null | Natural comparator không xử lý null | `Comparator.nullsFirst/Last` ở overload comparator |
| Đảo toàn bộ comparator sau `thenComparing` mà chỉ muốn đảo tiêu chí chính | Điều kiện phụ cũng bị đảo | Đảo comparator chính **trước** khi thêm tiêu chí phụ |
| Dùng `HashMap` và tin thứ tự tie của `sorted(comparingByValue())` ổn định | Nguồn unordered, stability không được cam kết | Thêm `thenComparing(comparingByKey())` |
| So số bằng phép trừ `a-b` | Có thể overflow, sai thứ tự | `Integer.compare` hoặc comparator chuẩn |
| So sánh các giá trị không implement `Comparable` bằng overload không tham số | Ràng buộc generic không thỏa | Cung cấp comparator cho kiểu value |
| Giữ `Map.Entry` từ entrySet lâu dài rồi thay đổi backing map | Entry có liên kết nguồn; hành vi không bảo đảm | Snapshot bằng `SimpleImmutableEntry` / `Map.Entry.copyOf` (Java 17+) |
| Dùng `Map.Entry.copyOf` với khóa hoặc value null | API từ Java 17 không chấp nhận null | Dùng `SimpleImmutableEntry` và chính sách null rõ |
| Đặt `limit(k)` trước `sorted` | Top-k có thể sai vì chỉ xét k entry đầu | `sorted(...).limit(k)` |
| Cần một maximum nhưng luôn sort toàn map | Phí bộ nhớ và số phép so | `stream().max(comparator)` |
| Dùng `forEach` trên parallel sorted stream và đòi thứ tự hiển thị | `forEach` không bảo đảm encounter order | `forEachOrdered` hoặc thu list |
| Đổi dữ liệu/key/value trong comparator | So sánh không nhất quán, sai hoặc exception | Comparator không side effect, dựa trên dữ liệu ổn định |
| Dùng `Comparator` thiếu tie-breaker trong API phân trang | Các entry cùng điểm dễ đổi vị trí giữa lần duyệt | Có tie-breaker và nguồn dữ liệu nhất quán |
| Dùng comparator custom mà không kiểm thử transitivity | Sort có thể bất nhất | Kiểm tra hợp đồng `Comparator` và các ca biên |

## 14. Bài tập có lời giải

### Bài 1. Sắp khóa trước, giá trị sau

Cho:

```java
Map<String, Integer> m = new LinkedHashMap<>();
m.put("c", 3);
m.put("a", 2);
m.put("b", 1);
```

Sắp entry theo **khóa tăng dần**.

**Đáp án:**

```java
List<Map.Entry<String, Integer>> result = m.entrySet().stream()
    .sorted(Map.Entry.comparingByKey())
    .collect(Collectors.toList());
// [a=2, b=1, c=3]
```

### Bài 2. Xếp hạng giá trị giảm dần, khóa tăng dần khi bằng điểm

Cho:

```java
Map<String, Integer> points = new LinkedHashMap<>();
points.put("z", 5);
points.put("b", 8);
points.put("a", 8);
```

**Đáp án:**

```java
Comparator<Map.Entry<String, Integer>> cmp =
    Map.Entry.<String, Integer>comparingByValue()
        .reversed()
        .thenComparing(Map.Entry.comparingByKey());

List<Map.Entry<String, Integer>> result = points.entrySet().stream()
    .sorted(cmp)
    .collect(Collectors.toList());
// [a=8, b=8, z=5]
```

Nếu chỉ dùng `comparingByValue(Comparator.reverseOrder())`, thứ tự của hai entry điểm 8 sẽ theo encounter order nếu nguồn ordered, hoặc không được bảo đảm nếu nguồn unordered; không nhất thiết là khóa A–Z.

### Bài 3. Để null đứng cuối

Cho map chứa `A → null`, `B → 4`, `C → 1`. Hãy sắp theo giá trị tăng, null cuối.

**Đáp án:**

```java
List<Map.Entry<String, Integer>> result = m.entrySet().stream()
    .sorted(Map.Entry.comparingByValue(
        Comparator.nullsLast(Comparator.naturalOrder())))
    .collect(Collectors.toList());
// Với m chứa A=null, B=4, C=1: [C=1, B=4, A=null]
```

Trong đoạn này, `m` được hiểu là map có dữ liệu mới như đề bài, không phải biến `m` của bài 1.

### Bài 4. Map sau sắp value

Có thể gọi `new TreeMap<>(someMap)` để sắp mapping theo value không?

**Không.** `TreeMap` tổ chức **key order**. Hãy sắp `entrySet()` theo value thành `List<Map.Entry<...>>`. Nếu còn cần một `Map` có thứ tự duyệt giống danh sách đã sắp, thu bằng `Collectors.toMap(..., LinkedHashMap::new)`.

### Bài 5. Bản sao entry an toàn để lưu lâu hơn

Vì sao `scores.entrySet().stream().sorted(...).collect(toList())` chưa chắc tạo snapshot độc lập?

**Đáp án:** `entrySet()` là view được backing map hỗ trợ; các `Map.Entry` có thể duy trì kết nối với map và bị ảnh hưởng khi map thay đổi. Tạo bản sao entry bằng `new AbstractMap.SimpleImmutableEntry<>(entry)` ở Java 8 hoặc `Map.Entry.copyOf(entry)` (Java 17+, không nhận null). Nhớ rằng sao chép entry không tự deep-copy object value mutable.

### Bài 6. Sort hay max?

Cần tìm một entry có giá trị cao nhất từ hàng triệu mapping. Việc sort toàn bộ rồi lấy entry đầu có cần thiết không?

**Không** nếu chỉ cần một cực trị. `entrySet().stream().max(Map.Entry.comparingByValue())` là lựa chọn đơn giản và thường ít tốn chi phí hơn. Nếu có nhiều giá trị bằng nhau và muốn chọn khóa nhỏ nhất, hãy thiết kế comparator/tie-breaker theo đúng quy tắc mong muốn thay vì mặc định chọn entry ngẫu nhiên.

## 15. Checklist khi áp dụng

- [ ] Đang sắp **entry** (`map.entrySet()`) hay thực ra chỉ cần các keys/values đơn lẻ?
- [ ] Tiêu chí chính là **key** hay **value**?
- [ ] Natural order có phù hợp kiểu dữ liệu và quy tắc ngôn ngữ/địa phương không?
- [ ] Có cần **giảm dần** không? Dùng overload `Comparator.reverseOrder()` hoặc `reversed()` đúng vị trí.
- [ ] Có key/value `null` không? Đã dùng `nullsFirst/nullsLast` rõ ràng?
- [ ] Khi điểm bằng nhau, đã thêm **tie-breaker** để kết quả tái hiện được chưa?
- [ ] Có đang dựa vào iteration order không được cam kết của `HashMap`?
- [ ] Có muốn giữ nguyên map gốc không? `sorted` chỉ tạo thứ tự kết quả, không sửa map.
- [ ] Kết quả là `List<Map.Entry>`, một `LinkedHashMap` mới, hay chỉ một `min/max`?
- [ ] Nếu cần thứ tự sau khi thu vào `Map`, đã chọn `LinkedHashMap::new` chưa?
- [ ] Có dùng `TreeMap` sai mục đích sắp theo value không?
- [ ] Comparator có tuân thủ hợp đồng và tránh tràn số không?
- [ ] Có đang giữ entry của backing map vượt quá vòng đời iteration hoặc sau khi map sửa không? Có cần snapshot?
- [ ] Với parallel stream, việc in/duyệt kết quả có yêu cầu encounter order hay không?
- [ ] Đã kiểm thử map rỗng, một entry, điểm trùng, null, dữ liệu nhiều kiểu chữ và top-N ở ranh giới tie chưa?

**Ghi nhớ:** `comparingByKey(...)` sắp các entry **theo khóa**, `comparingByValue(...)` sắp **theo giá trị**. Muốn thứ tự xếp hạng rõ ràng, kết hợp `reversed()` và `thenComparing(...)` đúng vị trí; muốn map kết quả giữ thứ tự đã sắp, thu vào `LinkedHashMap`. Các API này là cách làm hiện hành, rõ nghĩa và an toàn khi hợp đồng null, tie-breaker và quyền sở hữu dữ liệu được xác định trước.

### Tài liệu API chính thức

- [`Map.Entry` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.Entry.html): cả bốn overload `comparingByKey`/`comparingByValue` và `Map.Entry.copyOf`.
- [`Comparator` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): `reverseOrder`, `naturalOrder`, `nullsFirst`, `nullsLast`, `thenComparing` và hợp đồng comparator.
- [`Stream.sorted` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): tính stable với ordered streams, không cam kết stability với unordered streams.
- [`Map.entrySet` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html): entry-set view và các quy tắc liên kết với backing map.
- [`LinkedHashMap` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự chèn và thứ tự duyệt.
- [`Collectors.toMap` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): overload có merge function và map factory.
