# Java 10 – Collector bản đồ: Khóa trùng và IllegalStateException

> **Phạm vi:** Java 10 → **Collector bản đồ** → **Khóa trùng và IllegalStateException**. Bài giải thích `java.util.stream.Collectors.toMap`, `toUnmodifiableMap` và cách xử lý trùng khóa bằng các quy tắc còn áp dụng trên Java 17+ và các JDK hiện đại. `Collectors.toMap` có từ Java 8; `Collectors.toUnmodifiableMap` được bổ sung ở **Java 10**; `Collectors.toConcurrentMap` cũng còn được sử dụng. Ví dụ hoàn chỉnh chạy với `javac --release 17`. `record` trong ví dụ là tính năng chính thức từ Java 16.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt **hai stream element khác nhau** với **hai giá trị key bằng nhau sau khi chạy `keyMapper`**.
2. Giải thích nguyên nhân `Collectors.toMap(keyMapper, valueMapper)` ném **`IllegalStateException`** khi có khóa trùng, kể cả lúc hai value giống nhau.
3. Phân biệt lỗi trùng khóa của `Collectors.toMap` với lỗi của `Map.of` và lỗi null.
4. Chọn overload có **`mergeFunction`** để giải quyết xung đột: cộng dồn, giữ bản đầu, giữ bản cuối hoặc chọn giá trị tốt nhất.
5. Sử dụng `Collectors.groupingBy` khi yêu cầu phải giữ **mọi bản ghi** có cùng khóa, không được gộp thành một.
6. Dùng `Collectors.toUnmodifiableMap` trong Java 10+ và hiểu yêu cầu khác biệt về **null** và mutability.
7. Sử dụng `LinkedHashMap::new` khi kết quả cần có thứ tự duyệt có ý nghĩa, thay vì dựa vào loại Map mặc định.
8. Nhận diện rủi ro trong **parallel stream**, `toConcurrentMap`, phép merge không kết hợp được, khóa mutable, chuẩn hóa văn bản và nguồn unordered.
9. Viết test đúng API contract mà không phụ thuộc nguyên văn thông báo lỗi hay một implementation JDK cụ thể.

## 2. Vì sao collector bản đồ có thể gặp khóa trùng?

Stream cung cấp các phần tử `T`; collector `toMap` dùng hai ánh xạ:

~~~java
Collectors.toMap(keyMapper, valueMapper)
~~~

Ở mỗi phần tử:

- `keyMapper`: tính ra khóa `K`.
- `valueMapper`: tính ra giá trị `U`.
- Collector cần ghép thành **một `Map<K,U>`**, trong đó mỗi key chỉ gắn với tối đa một value tại một thời điểm.

Một Map không có khái niệm “hai entry độc lập mang cùng key theo `equals`”. Nếu hai phần tử stream cùng sinh ra một key, collector phải chọn **chính sách xung đột**. Với overload hai tham số, chính sách mặc định là **thất bại nhanh** thay vì âm thầm chọn một trong hai giá trị.

Ví dụ dữ liệu:

| Phần tử nguồn | `keyMapper` | `valueMapper` |
| --- | --- | --- |
| `Sale("A", 2)` | `"A"` | `2` |
| `Sale("B", 3)` | `"B"` | `3` |
| `Sale("A", 5)` | `"A"` | `5` |

Hai phần tử thứ nhất và thứ ba cùng sinh key `"A"`. Khi collector phải gộp chúng, overload hai tham số không biết muốn giữ `2`, `5` hay cộng thành `7`, nên ném `IllegalStateException`.

**Điểm then chốt:** Lỗi được xác định theo **key sau ánh xạ**, không chỉ theo việc object nguồn có `equals` nhau hay không.

### 2.1. Chương trình tối thiểu minh họa lỗi

~~~java
import java.util.List;
import java.util.stream.Collectors;

class Example {
    record Sale(String sku, int quantity) {}

    static void run() {
        var input = List.of(
                new Sale("A", 2),
                new Sale("B", 3),
                new Sale("A", 5));

        // Ném IllegalStateException khi collect:
        var result = input.stream().collect(
                Collectors.toMap(Sale::sku, Sale::quantity));
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình main độc lập. Khi chạy phương thức `run()`, terminal operation `collect` bắt đầu xử lý phần tử và phát hiện key trùng. Sự tồn tại của collector được tạo bằng `Collectors.toMap(...)` chưa tự làm stream chạy; exception phát sinh **khi thực sự thực hiện phép thu thập**.

### 2.2. Hai value giống nhau vẫn là khóa trùng

~~~java
var input = List.of(
        new Sale("A", 7),
        new Sale("A", 7));

// Vẫn ném IllegalStateException:
var map = input.stream().collect(
        Collectors.toMap(Sale::sku, Sale::quantity));
~~~

Không có quy tắc “nếu oldValue.equals(newValue) thì bỏ qua”. Overload hai tham số **không nhận merge function** và từ chối duplicate keys dù hai giá trị được ánh xạ giống hệt nhau. Nếu nghiệp vụ coi duplicate hoàn toàn giống nhau là hợp lệ, bạn cần đưa ra chính sách rõ ràng bằng overload ba tham số, hoặc validate dữ liệu trước.

## 3. “Khóa trùng” thực sự được so sánh như thế nào?

### 3.1. `equals` và `hashCode` của key

Collector xử lý các key theo quy tắc bình đẳng của Map phù hợp. Với Map sử dụng hash, key object phải tôn trọng hợp đồng Java:

- Nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()`.
- Hash code giống nhau **không đủ** để kết luận hai key bằng nhau; hash collision phải được giải quyết bằng equality.
- Đừng sửa field tham gia `equals`/`hashCode` của key sau khi nó đã được đặt vào hash-based Map.
- Không coi identity `a == b` là đồng nghĩa với `equals`. Hai String object khác tham chiếu có thể là cùng key theo nội dung.

~~~java
var key1 = new String("A");
var key2 = new String("A");
System.out.println(key1 == key2);      // false
System.out.println(key1.equals(key2)); // true
~~~

Dù hai String này không phải cùng object, nếu chúng được tạo bởi `keyMapper` ở hai phần tử thì vẫn bị xem là **khóa trùng**.

### 3.2. Khóa do hàm chuẩn hóa tạo ra

~~~java
var names = List.of(" Ada ", "ada");

var counts = names.stream().collect(Collectors.toMap(
        name -> name.strip().toLowerCase(java.util.Locale.ROOT),
        name -> 1,
        Integer::sum));

System.out.println(counts.get("ada")); // 2
~~~

Trong ví dụ, chuỗi gốc khác nhau, nhưng sau khi `strip()` và chuyển về chữ thường theo `Locale.ROOT`, cả hai cho key `"ada"`. Đây là **trùng theo keyMapper**, không phải “hai source object trùng nhau” đơn giản.

`String.strip()` xuất hiện từ Java 11; ví dụ này được dùng trên Java 17+. Khi cần xử lý nhận diện Unicode, có thể còn cần quy tắc chuẩn hóa khác (NFC, locale, business ID); hãy định nghĩa rõ và áp dụng nhất quán giữa hệ thống nhập liệu, lưu trữ và đọc dữ liệu.

### 3.3. Record có thể không trùng theo `equals`, nhưng keyMapper vẫn trùng

~~~java
record Product(String sku, long revision) {}

var data = List.of(
        new Product("p1", 1),
        new Product("p1", 2));

System.out.println(data.get(0).equals(data.get(1))); // false

// Vẫn có duplicate key "p1":
// data.stream().collect(Collectors.toMap(Product::sku, Product::revision));
~~~

Record mặc định so sánh **mọi component**; hai record có revision khác nhau không bằng nhau. Nhưng `Product::sku` chọn một key chỉ dựa trên SKU, nên hai phần tử vẫn va chạm ở cùng key. Đó là lý do `stream.distinct()` trước `toMap` **không chắc** giải quyết lỗi: `distinct()` dựa trên `equals` của phần tử *trước* khi chuyển sang key, trong khi `toMap` dựa trên key đã chọn.

## 4. `IllegalStateException` của `toMap` nghĩa là gì?

Với overload:

~~~java
toMap(Function<? super T, ? extends K> keyMapper,
      Function<? super T, ? extends U> valueMapper)
~~~

Java SE API quy định: nếu các key được ánh xạ trùng nhau theo `Object.equals`, collector ném `IllegalStateException` khi thực hiện collect. Nó không ngầm overwrite, bỏ phần tử sau hoặc gộp value bằng toán tử cộng.

Trong các JDK hiện đại, message thường có dạng gần giống:

~~~text
Duplicate key A (attempted merging values 2 and 5)
~~~

**Không cần assert nguyên văn message**: phần nội dung, thứ tự giá trị, chi tiết stack trace và implementation cụ thể không phải contract cần dựa vào cho logic nghiệp vụ. Điều được quy định là **loại lỗi** khi duplicate keys xuất hiện ở overload không có merge function.

### 4.1. Nên bắt lỗi ở đâu?

Nếu duplicate key là **dữ liệu không hợp lệ**, cho phép `IllegalStateException` nổi lên tới ranh giới xử lý thích hợp, hoặc chuyển thành lỗi domain có thông tin input cụ thể. Không nên bọc tất cả `IllegalStateException` trong một `catch` chung rồi đoán mọi lỗi đều đến từ duplicate: các phần khác của pipeline cũng có thể ném cùng loại exception.

Ví dụ để **giải thích lỗi khi thử nghiệm**:

~~~java
try {
    input.stream().collect(
            Collectors.toMap(Sale::sku, Sale::quantity));
} catch (IllegalStateException expected) {
    System.out.println("duplicate key detected");
}
~~~

Trong API production, hãy quyết định liệu duplicate nên là lỗi nghiệp vụ có mã rõ ràng, hay một trường hợp hợp lệ cần merge. Nếu cần báo rõ **khóa trùng nào và vị trí nào**, `mergeFunction` của collector chỉ nhận **hai value**, không nhận key trực tiếp; bạn có thể validate keys qua một bước tường minh hoặc mang key vào đối tượng value để tạo thông điệp chi tiết.

### 4.2. Đừng nhầm với `Map.of`

~~~java
// Ném IllegalArgumentException khi tạo Map:
Map.of("A", 1, "A", 2);
~~~

`Map.of` nhận các cặp key/value và từ chối key trùng bằng `IllegalArgumentException`. `Collectors.toMap(keyMapper, valueMapper)` từ chối trùng key trong quá trình collect bằng `IllegalStateException`. Hai API ở ngữ cảnh khác nhau; không bắt một loại exception và giả định nó bao trùm API còn lại.

## 5. Giải quyết duplicate bằng overload có `mergeFunction`

Chọn:

~~~java
Collectors.toMap(keyMapper, valueMapper, mergeFunction)
~~~

Ở đây `mergeFunction` có kiểu `BinaryOperator<U>`, nhận **giá trị đang gắn với key** và **giá trị mới**, rồi quyết định giá trị kết quả. Hợp đồng dùng cơ chế merge của Map; khi hai phần tử sinh cùng key, hàm này được sử dụng để giải quyết xung đột.

### 5.1. Cộng dồn số lượng

~~~java
var totals = sales.stream().collect(Collectors.toMap(
        Sale::sku,
        Sale::quantity,
        Integer::sum));

System.out.println(totals.get("A")); // 7
System.out.println(totals.get("B")); // 3
~~~

Với nguồn `A→2`, `B→3`, `A→5`, `Integer::sum` cộng các quantity của cùng key. Chính sách này hợp lý cho tổng doanh số/số lượng khi dữ liệu là các dòng chi tiết, không hợp lý nếu quantity là một “trạng thái cuối” chỉ được giữ một bản.

Vì `Integer::sum` có tính kết hợp và giao hoán đối với phép cộng modulo 32 bit, nó thuận tiện hơn các merge phụ thuộc thứ tự khi xử lý song song; tuy vậy phải nhớ **int có thể overflow**. Với tổng lớn, cân nhắc `long`, `Math.addExact` hoặc `BigInteger` tùy nghiệp vụ.

### 5.2. Giữ bản đầu tiên – `first wins`

~~~java
var first = sales.stream().collect(Collectors.toMap(
        Sale::sku,
        java.util.function.Function.identity(),
        (existing, incoming) -> existing));
~~~

`Function.identity()` giữ nguyên object `Sale` làm value. Với **stream tuần tự có encounter order rõ ràng**, lần đầu xuất hiện của key `A` là bản `revision=1` và `existing` được giữ lại khi gặp bản sau.

Quan trọng:

- `first wins` nghĩa là đầu tiên trong **encounter order được xác định** của source/pipeline; `HashSet`/unordered stream hoặc `toConcurrentMap` unordered không có cùng bảo đảm.
- Merge function là quy tắc logic **của giá trị**, không cần thay đổi `equals` của `Sale`.
- Với dữ liệu database, chỉ dùng “đầu tiên” nếu truy vấn đã có thứ tự rõ ràng (ví dụ `ORDER BY`); không dựa vào thứ tự ngẫu nhiên.
- Nếu muốn vừa giữ bản đầu vừa giữ thứ tự duyệt các key, dùng overload bốn tham số và `LinkedHashMap::new` (xem phần 7).

### 5.3. Giữ bản cuối cùng – `last wins`

~~~java
var last = sales.stream().collect(Collectors.toMap(
        Sale::sku,
        java.util.function.Function.identity(),
        (existing, incoming) -> incoming));
~~~

Với stream tuần tự có thứ tự, bản `A` ở cuối sẽ thay bản `A` ở đầu. Điều này hợp lý nếu source đã được sắp xếp theo quy tắc “bản sau ưu tiên” và bạn muốn giá trị mới nhất theo **thứ tự nguồn**, không phải theo timestamp.

Không tự coi “last in stream” là “latest by time”. Nếu source được sắp xếp ngược, hoặc có event gửi trễ, `last wins` không đồng nghĩa bản mới nhất. Khi có trường version/time, hãy chọn theo trường đó.

### 5.4. Chọn bản có phiên bản lớn hơn

~~~java
var newest = sales.stream().collect(Collectors.toMap(
        Sale::sku,
        java.util.function.Function.identity(),
        (a, b) -> a.revision() >= b.revision() ? a : b));
~~~

Đây là chính sách **max revision**. Với revision bằng nhau, mẫu trên giữ `a`; nếu thứ tự nguồn không ổn định, kết quả khi tie có thể phụ thuộc thứ tự xử lý. Đối với tính xác định độc lập thứ tự, hãy bổ sung tie-breaker rõ (ví dụ một ID duy nhất, nguồn ưu tiên hoặc reject xung đột) và giữ merge function có tính kết hợp phù hợp.

### 5.5. Khi merge trả `null`

Theo `Map.merge`, nếu remapping function trả `null` thì mapping hiện tại **bị xóa**:

~~~java
var result = List.of("P", "P").stream().collect(
        Collectors.toMap(
                java.util.function.Function.identity(),
                value -> 1,
                (existing, incoming) -> null));

System.out.println(result.containsKey("P")); // false
~~~

Không nhầm `null` ở **kết quả merge** với một value `null` được cho trực tiếp từ `valueMapper`: đó là hai tình huống khác. Việc xóa mapping khi merge trả null có thể gây hành vi khó đoán nếu key xuất hiện lần thứ ba: khi đó lần thứ ba có thể chèn lại mapping. Không dùng chiến thuật này làm “bỏ hết duplicate” trừ khi đã mô hình hóa toàn bộ quy tắc.

## 6. Nếu cần giữ **mọi bản ghi** trùng khóa, dùng `groupingBy`

Giả sử `A` có hai record và bạn cần phân tích cả hai, không được giữ mỗi bản đại diện:

~~~java
var grouped = sales.stream().collect(
        Collectors.groupingBy(
                Sale::sku,
                java.util.LinkedHashMap::new,
                Collectors.toList()));

System.out.println(grouped.get("A").size()); // 2
~~~

Kết quả có dạng logic `Map<String,List<Sale>>`, nên mỗi key chứa **danh sách** các bản ghi. `groupingBy` không ném lỗi chỉ vì hai phần tử sinh cùng group key như overload `toMap` không có merger.

Đây không phải cùng hợp đồng với `Map<String,Sale>` hoặc `Map<String,Integer>`:

- `toMap` phù hợp khi bạn thật sự cần **một value cho mỗi key** và có chính sách trùng rõ ràng.
- `groupingBy` phù hợp khi mọi phần tử trong một nhóm đều có ý nghĩa.
- `groupingBy(..., counting())` hoặc `summingInt(...)` phù hợp khi cần thống kê trong mỗi nhóm.
- Nếu muốn kết quả collection không thể sửa, cần thiết kế thêm bước tạo snapshot phù hợp; `groupingBy` không tự cam kết trả Map/List immutable.

### 6.1. Vì sao `distinct()` không phải “thuốc chữa” tổng quát?

~~~java
record Sale(String sku, int quantity, int revision) {}

var input = List.of(
        new Sale("A", 2, 1),
        new Sale("A", 5, 2));
~~~

Hai record khác nhau về quantity/revision nên `equals` mặc định cho `false`. Do đó `input.stream().distinct()` vẫn có cả hai. Nếu ngay sau đó dùng `Collectors.toMap(Sale::sku, Sale::quantity)`, keyMapper vẫn tạo hai `"A"` và ném exception.

Muốn unique theo `sku`, hãy **chọn key và chính sách merge** hoặc group theo SKU. Đừng kỳ vọng `distinct()` tự hiểu quan hệ domain.

## 7. Overload bốn tham số và vai trò `mapFactory`

Chữ ký:

~~~java
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

`mapFactory` cung cấp Map đích, ví dụ `LinkedHashMap::new`:

~~~java
var orderedFirst = sales.stream().collect(Collectors.toMap(
        Sale::sku,
        java.util.function.Function.identity(),
        (existing, incoming) -> existing,
        java.util.LinkedHashMap::new));
~~~

Với một stream tuần tự có thứ tự ổn định, `LinkedHashMap` mặc định duyệt key theo **insertion order**. Nếu đầu tiên thấy key `A`, rồi `B`, lần xuất hiện thứ hai của `A` không chuyển key `A` xuống cuối.

~~~java
System.out.println(new java.util.ArrayList<>(orderedFirst.keySet()));
// [A, B]
~~~

**Phân biệt hai chính sách:**

- Giữ **value** theo `first wins` hay `last wins` là nhiệm vụ của `mergeFunction`.
- Giữ **thứ tự duyệt key** của Map là nhiệm vụ của `mapFactory` và thứ tự nguồn. `LinkedHashMap` không khiến một collector tự xử lý duplicate theo cách bạn muốn nếu thiếu merge function.

Overload hai hoặc ba tham số của `toMap` không cam kết kiểu implementation Map, tính mutable, serializable hoặc thread-safe của Map trả về. Trên một OpenJDK cụ thể bạn thường thấy `HashMap`, nhưng đừng viết API giả định kết quả luôn là `HashMap` hoặc luôn giữ encounter order. Nếu yêu cầu cấu trúc cụ thể, dùng overload bốn tham số.

### 7.1. `TreeMap`/comparator có thể thay “khái niệm trùng”

Nếu cung cấp một `TreeMap` có `Comparator` riêng làm `mapFactory`, quan hệ “cùng key” trong Map có thể dựa vào so sánh comparator thay vì `equals` theo cách HashMap dùng. Chẳng hạn comparator không phân biệt chữ hoa/thường có thể coi `"A"` và `"a"` là cùng key.

Vì vậy, khi cần kết quả portable, hãy bảo đảm comparator **phù hợp với equals** nếu API yêu cầu đúng semantics Map thông thường, hoặc ghi rõ domain comparator và test behavior. Không nhầm lỗi trùng do **mapping key** với việc thay chiến lược định danh key ở Map implementation.

## 8. Java 10: `Collectors.toUnmodifiableMap` và khóa trùng

Java 10 cung cấp hai overload quan trọng:

~~~java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
~~~

So sánh:

| Trường hợp | `toMap` hai tham số | `toUnmodifiableMap` hai tham số |
| --- | --- | --- |
| Khóa trùng theo keyMapper | `IllegalStateException` | `IllegalStateException` |
| Có thể cung cấp merge function? | Có, qua overload ba/bốn tham số | Có, qua overload ba tham số |
| Kết quả có bảo đảm unmodifiable? | **Không cam kết** | **Có** |
| Kết quả có cam kết thứ tự duyệt? | **Không** | **Không** |
| Có cho null key/value trong output? | Không dựa vào hành vi implementation cho null; validate tường minh | **Không**; `NullPointerException` |
| Khi nào dùng? | Tạo Map kết quả theo API không yêu cầu immutable hoặc có supplier phù hợp | Công bố snapshot không sửa cấu trúc ngay từ pipeline |

### 8.1. Không có merge function: lỗi cũng là `IllegalStateException`

~~~java
// Hai bản ghi trùng SKU "A" → IllegalStateException
var frozen = sales.stream().collect(
        Collectors.toUnmodifiableMap(
                Sale::sku, Sale::quantity));
~~~

Tính unmodifiable **không** tự giải quyết xung đột key.

### 8.2. Có merge function: cộng dồn rồi trả Map không cho sửa

~~~java
var frozenTotals = sales.stream().collect(
        Collectors.toUnmodifiableMap(
                Sale::sku, Sale::quantity, Integer::sum));

System.out.println(frozenTotals.get("A")); // 7
// frozenTotals.put("C", 1); // Biên dịch được, nhưng runtime ném UnsupportedOperationException
~~~

Khi cần giá trị tổng hợp và muốn chặn việc thay mapping sau khi collect, đây là API phù hợp trên Java 10+. Nó không deep-copy các object key/value mutable; chỉ bảo vệ **cấu trúc mapping**.

### 8.3. `null` phải được phân biệt với duplicate keys

`Collectors.toUnmodifiableMap` **từ chối cả null key và null value**. Nếu `keyMapper` hoặc `valueMapper` trả `null`, JavaDoc chỉ rõ `NullPointerException`. Không mô tả tình huống này thành “duplicate-key IllegalStateException” vì nguyên nhân và cách sửa khác nhau.

~~~java
var source = List.of("ok", "bad");

// Ném NullPointerException vì valueMapper trả null cho "bad":
// source.stream().collect(Collectors.toUnmodifiableMap(
//     java.util.function.Function.identity(),
//     value -> value.equals("bad") ? null : value));
~~~

Nếu null mang ý nghĩa domain, hãy validate hoặc ánh xạ nó thành kiểu dữ liệu thể hiện trạng thái (ví dụ một value object/Optional tại ranh giới phù hợp) **trước khi** thu thập vào Map unmodifiable. Với `toMap` thông thường, hành vi null có thể phụ thuộc implementation Map/đường thực hiện; không viết code phụ thuộc việc nó cho phép null.

### 8.4. Không nhầm `Collectors.toUnmodifiableMap` với `Map.copyOf`

- `toUnmodifiableMap` biến **một stream các phần tử** thành Map bằng `keyMapper`, `valueMapper` và tùy chọn merger.
- `Map.copyOf(existingMap)` nhận **một Map đã tồn tại**. Tại thời điểm đó, một Map hợp lệ đã không còn hai entry cùng key, vì các lần `put` trước đã giải quyết chúng theo một quy tắc nào đó.
- Vì vậy, `Map.copyOf` không thể “khôi phục” duplicate record bị ghi đè khi xây Map, còn `toUnmodifiableMap` có cơ hội phát hiện hoặc xử lý ngay trong stream.

## 9. Xử lý nhiều luồng và parallel stream

### 9.1. `toMap` không phải concurrent collector

Trong JavaDoc, `toMap` không phải concurrent collector. Với parallel stream, combiner phải hợp nhất các Map trung gian; việc merge các key từ Map này vào Map kia có thể tốn chi phí.

~~~java
var totals = sales.parallelStream().collect(
        Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum));
~~~

Với chính sách cộng dồn associative/không có side effect, kết quả tổng theo key vẫn phù hợp. Nhưng nếu merge phụ thuộc thứ tự, thời điểm, state bên ngoài hoặc side effect, cách phân vùng/ghép Map có thể gây khó hiểu và làm mất tính xác định. Đừng dùng parallelization chỉ vì dữ liệu “nhiều”, hãy đo với workload thực tế.

### 9.2. `toConcurrentMap` là collector concurrent và unordered

~~~java
var concurrentTotals = sales.parallelStream().collect(
        Collectors.toConcurrentMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum));
~~~

`toConcurrentMap` trả `ConcurrentMap` theo hợp đồng, phù hợp với một số workload song song. Nhưng overload **hai tham số** `toConcurrentMap(keyMapper, valueMapper)` vẫn ném `IllegalStateException` nếu key trùng; cũng cần overload với merger khi duplicate hợp lệ.

**Rất quan trọng:** `toConcurrentMap` được định nghĩa là **concurrent, unordered collector**. Không dùng merger `(old, next) -> old` hoặc `(old, next) -> next` rồi hứa “first/last theo thứ tự input” trong pipeline unordered/concurrent. Nếu nghiệp vụ thực sự cần trình tự, xử lý tuần tự theo source có encounter order rõ, hoặc chọn theo một khóa/phiên bản độc lập thứ tự.

### 9.3. Merge function nên có tính kết hợp, thuần và ít bất ngờ

Với collector có khả năng kết hợp partial results, merge thích hợp nên:

- Có tính **kết hợp** (associative) khi cần kết quả nhất quán bất kể cách phân nhóm.
- Không ghi shared mutable state, không phụ thuộc số lần callback chạy.
- Không thực hiện I/O, gửi sự kiện, ghi database trong merger.
- Nếu unordered/parallel, nên dùng phép gộp **giao hoán** hoặc có tie-breaker xác định nếu kết quả cần không phụ thuộc encounter order.
- Nếu giá trị mutable, tránh mutate trực tiếp value object cũ mà thread khác có thể đang dùng; có thể trả value object mới nếu cần.

Phép trừ không có tính kết hợp: `(10 - 3) - 2` khác `10 - (3 - 2)`. Merge `(a,b)->a-b` vì vậy nguy hiểm cho kết quả dự kiến trên parallel stream. Chọn quy tắc tổng hợp phù hợp với đại số dữ liệu.

## 10. Chẩn đoán lỗi trùng khóa trong ứng dụng thật

### 10.1. Các nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Hai user thành một key | `keyMapper` chỉ lấy tên hiển thị, không unique ID | Chọn ID duy nhất thực sự |
| Lỗi sau khi trim/lowercase | Hai input khác nhau bị normalize thành cùng key | Quy định canonicalization và merge/reject rõ |
| Record khác nhau nhưng cùng key | `distinct()` so sánh cả record, còn keyMapper lấy một field | Group hoặc merge theo field đó |
| Lỗi khi có 2 value giống hệt | Overload hai tham số vẫn reject duplicate key | Chọn rule “identical allowed”, merger hoặc validate |
| Chạy trên dev không lỗi, prod lỗi | Dataset prod có duplicate thực sự, stream source khác | Tái hiện bằng dữ liệu mẫu đã ẩn thông tin nhạy cảm |
| Lỗi chỉ trong parallel pipeline | Có duplicate và/hoặc merger không an toàn, thứ tự xử lý khác | Dùng policies associative, kiểm tra input, test cả sequential/parallel |
| Lỗi từ `toUnmodifiableMap` khi value null | `NullPointerException`, không phải duplicate-key exception | Validate null và mapping output |
| Lỗi vì key có field mutable | Key hash/equality đổi khi dùng trong Map | Dùng immutable key |
| Kết quả lần lượt khác nhau | `first/last wins` trên nguồn unordered | Xác định order nguồn hoặc comparator độc lập thứ tự |

### 10.2. Cách xác định khóa lỗi trước khi tạo Map

Nếu cần phát hiện duplicate key và báo chính xác các dòng vi phạm, hãy group **theo cùng một keyMapper** rồi kiểm tra số lượng:

~~~java
var bySku = sales.stream().collect(
        Collectors.groupingBy(Sale::sku));

var duplicateKeys = bySku.entrySet().stream()
        .filter(entry -> entry.getValue().size() > 1)
        .map(java.util.Map.Entry::getKey)
        .sorted()
        .toList();

System.out.println(duplicateKeys); // [A] với dữ liệu của bài
~~~

`groupingBy` ở đây được dùng như một **bước validation**, không phải vì cuối cùng phải trả `Map<String,List<Sale>>`. Cách làm giữ được tất cả record để báo lỗi chi tiết, nhưng tốn thêm memory và chi phí tính toán. Với input lớn hoặc cần dừng ngay khi thấy duplicate, có thể sử dụng một vòng lặp với `Map.putIfAbsent` và báo key/vị trí trực tiếp (bảo đảm dữ liệu đầu vào và policy nhất quán).

### 10.3. Dùng vòng lặp tường minh để báo lỗi domain có key cụ thể

~~~java
var index = new java.util.LinkedHashMap<String, Sale>();
for (var sale : sales) {
    var previous = index.putIfAbsent(sale.sku(), sale);
    if (previous != null) {
        throw new IllegalArgumentException(
                "Duplicate SKU: " + sale.sku());
    }
}
~~~

Đoạn trên **minh họa trong phương thức có biến `sales` và record `Sale`**, không phải main độc lập. Nó chọn lỗi domain `IllegalArgumentException` với key rõ ràng; lựa chọn exception tùy API. `putIfAbsent` chỉ phù hợp với rule “đã có mapping” khi value không-null, như record `Sale` ở đây. Nếu null value được phép và vẫn coi key đã hiện diện là duplicate, dùng `containsKey` với chính sách tường minh.

### 10.4. Không bắt exception rồi âm thầm trả Map rỗng

~~~java
// Phản ví dụ, không áp dụng:
// try { return stream.collect(toMap(...)); }
// catch (IllegalStateException ignored) { return Map.of(); }
~~~

Cách này che giấu dữ liệu bị mất và khiến caller nghĩ rằng không có dữ liệu. Tùy yêu cầu, hãy:

- Từ chối input và trả lỗi có thông điệp/chỉ số record;
- Chọn merge function thực sự đúng;
- Group các record và trả tất cả;
- Chuẩn hóa nguồn và log lỗi dữ liệu có kiểm soát.

Không nên biến một vấn đề dữ liệu quan trọng thành một Map rỗng “thành công”.

## 11. Ví dụ hoàn chỉnh Java 17+ đã chạy thử

Chương trình sau vừa kiểm chứng `IllegalStateException` cho hai collector không có merger, vừa cho thấy các chính sách xử lý trùng. Nó **không in trực tiếp `HashMap` mặc định** hay thông điệp exception không ổn định, nhờ đó stdout dưới đây đáng tin trên Java 17+.

Lưu file đúng tên **`DuplicateKeyCollectorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class DuplicateKeyCollectorDemo {
    record Sale(String sku, int quantity, int revision) {}

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("A", 2, 1),
                new Sale("B", 3, 1),
                new Sale("A", 5, 2));

        try {
            sales.stream().collect(Collectors.toMap(
                    Sale::sku, Sale::quantity));
        } catch (IllegalStateException expected) {
            System.out.println("duplicate-toMap=IllegalStateException");
        }

        var identical = List.of(
                new Sale("X", 7, 1),
                new Sale("X", 7, 2));
        try {
            identical.stream().collect(Collectors.toMap(
                    Sale::sku, Sale::quantity));
        } catch (IllegalStateException expected) {
            System.out.println("equal-values-still-duplicate=true");
        }

        var totals = sales.stream().collect(Collectors.toMap(
                Sale::sku, Sale::quantity, Integer::sum));
        System.out.println("totals-A=" + totals.get("A"));
        System.out.println("totals-B=" + totals.get("B"));

        var first = sales.stream().collect(Collectors.toMap(
                Sale::sku,
                Function.identity(),
                (existing, incoming) -> existing,
                LinkedHashMap::new));
        var last = sales.stream().collect(Collectors.toMap(
                Sale::sku,
                Function.identity(),
                (existing, incoming) -> incoming,
                LinkedHashMap::new));
        System.out.println("first-A-revision=" + first.get("A").revision());
        System.out.println("last-A-revision=" + last.get("A").revision());
        System.out.println("ordered-keys=" + new ArrayList<>(first.keySet()));

        var grouped = sales.stream().collect(Collectors.groupingBy(
                Sale::sku, LinkedHashMap::new, Collectors.toList()));
        System.out.println("grouped-A-size=" + grouped.get("A").size());

        try {
            sales.stream().collect(Collectors.toUnmodifiableMap(
                    Sale::sku, Sale::quantity));
        } catch (IllegalStateException expected) {
            System.out.println("duplicate-unmodifiable=IllegalStateException");
        }

        var frozen = sales.stream().collect(Collectors.toUnmodifiableMap(
                Sale::sku, Sale::quantity, Integer::sum));
        System.out.println("frozen-A=" + frozen.get("A"));
        try {
            frozen.put("C", 1);
        } catch (UnsupportedOperationException expected) {
            System.out.println("frozen-write=blocked");
        }

        try {
            List.of("ok", "bad").stream().collect(
                    Collectors.toUnmodifiableMap(
                            Function.identity(),
                            value -> value.equals("bad") ? null : value));
        } catch (NullPointerException expected) {
            System.out.println("unmodifiable-null-value=rejected");
        }

        try {
            List.of("A", "B").stream().collect(
                    Collectors.toUnmodifiableMap(
                            value -> value.equals("B") ? null : value,
                            Function.identity()));
        } catch (NullPointerException expected) {
            System.out.println("unmodifiable-null-key=rejected");
        }

        var normalized = List.of(" Ada ", "ada").stream()
                .map(value -> value.strip().toLowerCase(Locale.ROOT))
                .collect(Collectors.toMap(
                        Function.identity(), value -> 1, Integer::sum));
        System.out.println("normalized-ada-count=" + normalized.get("ada"));

        var concurrent = sales.parallelStream().collect(
                Collectors.toConcurrentMap(
                        Sale::sku, Sale::quantity, Integer::sum));
        System.out.println("concurrent-A=" + concurrent.get("A"));

        var removed = List.of("P", "P").stream()
                .collect(Collectors.toMap(
                        Function.identity(), value -> 1,
                        (existing, incoming) -> null));
        System.out.println("null-merge-removes-key=" + !removed.containsKey("P"));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac --release 17 DuplicateKeyCollectorDemo.java
java DuplicateKeyCollectorDemo
~~~

**Stdout chính xác** (đã biên dịch và chạy thành công):

~~~text
duplicate-toMap=IllegalStateException
equal-values-still-duplicate=true
totals-A=7
totals-B=3
first-A-revision=1
last-A-revision=2
ordered-keys=[A, B]
grouped-A-size=2
duplicate-unmodifiable=IllegalStateException
frozen-A=7
frozen-write=blocked
unmodifiable-null-value=rejected
unmodifiable-null-key=rejected
normalized-ada-count=2
concurrent-A=7
null-merge-removes-key=true
~~~

### 11.1. Giải thích từng nhóm output

- Hai dòng đầu chứng minh **khóa trùng** làm overload `toMap` hai tham số ném `IllegalStateException` dù value khác nhau hoặc giống hệt nhau.
- `totals-A=7` là kết quả `2+5`; `totals-B=3` vì SKU B chỉ có một bản ghi.
- `first-A-revision=1` và `last-A-revision=2` xác nhận hai chính sách chọn value khác nhau trong **ordered sequential stream**.
- `ordered-keys=[A, B]` xuất phát từ `LinkedHashMap::new`, không phải thứ tự được hứa bởi `toMap` mặc định.
- `grouped-A-size=2` vì `groupingBy` giữ hai Sale trong nhóm A.
- `duplicate-unmodifiable=IllegalStateException` cho thấy Java 10 `toUnmodifiableMap` không tự merge khóa trùng.
- `frozen-A=7` và `frozen-write=blocked`: merge hợp lệ rồi tạo Map không sửa được cấu trúc.
- Hai dòng `unmodifiable-null-...` kiểm chứng null key và null value là lỗi `NullPointerException`, tách với duplicate-key exception.
- `normalized-ada-count=2` cho thấy hai chuỗi khác nhau ban đầu trùng sau chuẩn hóa.
- `concurrent-A=7` kiểm chứng aggregation bằng `toConcurrentMap`, không kiểm tra thứ tự trong concurrent Map.
- `null-merge-removes-key=true` minh họa kết quả null của remapping function loại mapping hiện có theo `Map.merge`.

### 11.2. Giới hạn cần hiểu đúng

Mã chạy thử không phải benchmark. Nó không thể chứng minh mọi merger sẽ an toàn trong parallel stream, mọi data source đều có encounter order, hoặc mọi exception message trên các JDK giống nhau. Chương trình tập trung vào **các hợp đồng**: trùng key với overload không có merger, policy xác định, Map unmodifiable và null restrictions.

## 12. Bảng chọn nhanh: yêu cầu nào, collector nào?

| Yêu cầu nghiệp vụ | Cách tiếp cận | Kết quả |
| --- | --- | --- |
| Key phải duy nhất; duplicate là lỗi | `toMap(keyMapper, valueMapper)` | Ném `IllegalStateException` khi trùng |
| Key duy nhất; muốn Map unmodifiable | `toUnmodifiableMap(keyMapper, valueMapper)` | Ném `IllegalStateException` khi trùng, từ chối null |
| Các dòng cùng key cần cộng dồn | `toMap(..., Integer::sum)` hoặc `toUnmodifiableMap(..., Integer::sum)` | Một tổng mỗi key |
| Giữ bản đầu tiên trong stream tuần tự có thứ tự | `toMap(..., (old, next) -> old)` | Một value được chọn cho mỗi key |
| Giữ bản cuối cùng trong stream tuần tự có thứ tự | `toMap(..., (old, next) -> next)` | Một value được chọn cho mỗi key |
| Chọn version cao nhất | `toMap(..., mergeByVersion)` | Một bản thắng theo quy tắc |
| Giữ mọi phần tử của mỗi key | `groupingBy(keyMapper)` | `Map<K,List<T>>` |
| Cần insertion order của key | `toMap(..., merger, LinkedHashMap::new)` | Map duyệt theo thứ tự chèn |
| Nhiều core, unordered tổng hợp theo key | `toConcurrentMap(..., associativeMerger)` | ConcurrentMap; không hứa first/last |
| Có dữ liệu trùng cần error message giàu ngữ cảnh | Validate trước bằng grouping/vòng lặp | Báo key, vị trí, record theo domain |
| Source là Map đã hình thành | `Map.copyOf(existingMap)` nếu cần snapshot | Không còn cơ hội phát hiện các sự kiện trùng đã overwrite |

## 13. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| “Cùng key thì `toMap` tự giữ bản sau” | Thực tế ném `IllegalStateException` ở overload 2 args | Chọn merger rõ ràng |
| “Value giống nhau nên duplicate được bỏ qua” | Vẫn ném lỗi | Chọn rule bỏ bản trùng hoặc validate |
| “`distinct()` sẽ tránh mọi duplicate-key” | Nó dùng equality của source object, không phải keyMapper | Dùng key-based policy |
| “`HashMap` có thể chứa hai entry cùng key” | Map không có hai mapping độc lập cùng key | Dùng `groupingBy` nếu cần nhiều value |
| “`Map.of` và `toMap` ném cùng lỗi” | `Map.of` trùng key → `IllegalArgumentException` | Bắt lỗi đúng API |
| “`toUnmodifiableMap` không cần merge vì immutable” | Vẫn ném `IllegalStateException` nếu key trùng | Thêm merger hoặc reject |
| “Null luôn có nghĩa khóa trùng” | Null ở `toUnmodifiableMap` → `NullPointerException` | Validate key/value |
| “`toMap` luôn trả `HashMap` mutable” | API không cam kết type/mutability | Sử dụng explicit supplier nếu cần |
| “Giữ first/last trong concurrent unordered stream” | Thứ tự không ổn định theo input | Dùng ordered sequential/priority rule |
| “Merger có thể tự gửi event mỗi lần chạy” | Callback có thể chạy trong lúc ghép partial results, side effect khó kiểm soát | Giữ merger pure |
| “Merger trả null tương đương bỏ lần mới” | `Map.merge` xóa mapping hiện có | Trả `old` nếu muốn giữ giá trị cũ |
| “Chỉ sửa `hashCode` để loại trùng” | Vi phạm hợp đồng equals/hashCode | Thiết kế key immutable với equality đúng |
| “Không cần xem keyMapper vì source object là unique” | Nhiều unique objects vẫn có thể tạo cùng key | Kiểm tra canonicalization và key domain |
| “Bắt mọi `IllegalStateException` rồi trả Map rỗng” | Che mất lỗi dữ liệu và có thể nuốt exception khác | Xử lý tại đúng ranh giới nghiệp vụ |
| “Sắp xếp theo tên rồi lấy last nghĩa là mới nhất” | Thứ tự tên không phải thứ tự version/time | Chọn theo version/timestamp và tie-breaker |
| “Đã chạy thử parallel một lần nên deterministic” | Một lịch trình không kiểm chứng mọi cách kết hợp | Lập luận associativity, test đa điều kiện |

## 14. Các bài tập tự kiểm tra và đáp án

**Bài 1.** `List.of("A", "A").stream().collect(Collectors.toMap(Function.identity(), value -> 1))` xảy ra điều gì?

**Đáp án:** Ném `IllegalStateException` vì hai element sinh cùng key `"A"`. Value đều là 1 không thay đổi điều đó.

**Bài 2.** `Map.of("A",1,"A",2)` có cùng exception không?

**Đáp án:** Không. `Map.of` từ chối duplicate key bằng `IllegalArgumentException`.

**Bài 3.** Cho `Sale(A,2)` và `Sale(A,5)`, muốn `A→7` thì chọn overload nào?

**Đáp án:** `Collectors.toMap(Sale::sku, Sale::quantity, Integer::sum)`; kết quả value cho A bằng 7.

**Bài 4.** Muốn giữ bản đầu tiên của SKU A trong nguồn `List` có thứ tự, viết merger nào?

**Đáp án:** `(existing, incoming) -> existing` với stream tuần tự có encounter order rõ. Nếu nguồn unordered, “đầu tiên” không được xác định theo nghiệp vụ.

**Bài 5.** Muốn giữ bản cuối của SKU A, viết merger nào?

**Đáp án:** `(existing, incoming) -> incoming` với ordered sequential stream. Không gọi nó là “latest by version” khi thứ tự không dựa trên revision.

**Bài 6.** Tại sao `stream.distinct()` không loại được hai `Product("p1",1)` và `Product("p1",2)` trước `toMap(Product::sku,...)`?

**Đáp án:** Record equality bao gồm cả revision nên chúng không bằng nhau; keyMapper chỉ chọn SKU nên trùng ở khâu tạo Map.

**Bài 7.** `List.of(" Ada ", "ada")` tạo key trùng khi nào?

**Đáp án:** Khi keyMapper chuẩn hóa (ví dụ trim/strip rồi lower-case theo Locale.ROOT) để cả hai thành `"ada"`.

**Bài 8.** Muốn giữ tất cả Sale cùng SKU A thì chọn `toMap` hay `groupingBy`?

**Đáp án:** `groupingBy(Sale::sku)` nếu cần `Map<String,List<Sale>>`; `toMap` chỉ trả một value cho key nếu có merger.

**Bài 9.** `toUnmodifiableMap` từ Java 10 có loại trừ duplicate key không?

**Đáp án:** Không. Overload hai tham số ném `IllegalStateException`; overload ba tham số nhận merger để giải quyết xung đột.

**Bài 10.** `toUnmodifiableMap` với valueMapper trả null có thể lỗi gì?

**Đáp án:** `NullPointerException` vì collector này không cho null key/value; không phải lỗi duplicate key.

**Bài 11.** Sau `toMap(..., Integer::sum)`, có được bảo đảm kết quả luôn là `HashMap` và mutable không?

**Đáp án:** Không; Java SE không cam kết implementation, mutability, serializability hay thread safety của Map trả về từ `toMap` thông thường. Nếu cần một loại Map cụ thể, dùng overload bốn tham số.

**Bài 12.** Muốn thứ tự duyệt key theo lần chèn đầu tiên, dùng gì?

**Đáp án:** `Collectors.toMap(keyMapper, valueMapper, mergeFunction, LinkedHashMap::new)` trên nguồn có encounter order rõ.

**Bài 13.** `toConcurrentMap` có hỗ trợ duplicate keys với merger không?

**Đáp án:** Có. Dùng overload `toConcurrentMap(keyMapper,valueMapper,mergeFunction)`. Overload hai tham số vẫn reject duplicate; concurrent collector là unordered nên đừng hứa first/last theo input.

**Bài 14.** `mergeFunction` trả `null` khi gặp key trùng thì thế nào?

**Đáp án:** Với cơ chế `Map.merge`, mapping được xóa. Đây không phải hành vi “giữ cũ”; nếu key sau đó xuất hiện lần nữa có thể được thêm lại.

**Bài 15.** Nếu dữ liệu có version, vì sao dùng max revision thường tốt hơn first/last?

**Đáp án:** Vì first/last phụ thuộc vào thứ tự nguồn, còn chọn version cao nhất bám theo tiêu chí nghiệp vụ. Cần tie-breaker khi cùng version.

**Bài 16.** Có nên assert nguyên văn `IllegalStateException.getMessage()` trong bài test portable không?

**Đáp án:** Không nên. Kiểm tra loại lỗi và hành vi; phần thông báo cụ thể có thể thay đổi theo implementation/JDK.

**Bài 17.** Nếu muốn hiện khóa gây lỗi cùng hai bản ghi nguồn để sửa dữ liệu, merger của `toMap` có nhận key trực tiếp không?

**Đáp án:** Không; merger nhận hai **value**. Hãy validate trước bằng `groupingBy` hoặc vòng lặp theo key, hoặc mang thông tin key trong value để tạo diagnostic đúng.

**Bài 18.** Tại sao phép merge `(a,b)->a-b` không phải lựa chọn tốt cho parallel pipeline?

**Đáp án:** Phép trừ không có tính kết hợp; kết quả phụ thuộc cách nhóm và thứ tự merge. Nên dùng phép gộp associative/pure hoặc tuần tự hóa theo yêu cầu.

## 15. Checklist khi đưa vào code production

Trước khi chọn một collector bản đồ, kiểm tra theo thứ tự:

1. **Key là gì?** `keyMapper` dùng unique ID hay tên hiển thị dễ trùng?
2. **Các thao tác chuẩn hóa có thể tạo collision không?** Case-folding, trim, Unicode normalization, phiên bản, tenant ID?
3. **Trùng là lỗi hay tình huống hợp lệ?** Nếu lỗi, có cần thông báo domain chứa key/vị trí không?
4. **Nếu trùng hợp lệ, merger là gì?** Sum, first, last, max version, tie-breaker, hay giữ tất cả?
5. **Có nguồn ordered không?** Nếu không, đừng chọn first/last mà không xác định chính sách bổ sung.
6. **Có cần đủ mọi record không?** Nếu có, dùng `groupingBy`.
7. **Có cần Map unmodifiable?** Chọn `toUnmodifiableMap` hoặc tạo snapshot khi kết quả hoàn thành; nắm rõ null restrictions.
8. **Có null key/value không?** Validate trước, đừng quy mọi NPE thành duplicate key.
9. **Có cần insertion order/implementation cụ thể?** Dùng overload có `mapFactory` như `LinkedHashMap::new`.
10. **Có dùng parallel/concurrent collector không?** Merger phải có tính kết hợp phù hợp, không side effect, và kết quả không phụ thuộc encounter order nếu collector unordered.
11. **Có key mutable không?** Bảo đảm equals/hashCode ổn định khi key nằm trong Map.
12. **Test đúng API contract chưa?** Kiểm tra dữ liệu, exception type và policy, không phụ thuộc HashMap output order hay nguyên văn message.
13. **Có quá nhiều thao tác copy/collect lại không?** Nếu pipeline lớn, đo CPU/memory bằng workload phù hợp thay vì tối ưu theo phỏng đoán.

## 16. Nguồn tài liệu chính thức

1. [Java SE 17 – Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `toMap` overload hai/ba/bốn tham số, duplicate key → `IllegalStateException`, merger và `mapFactory`, `groupingBy` và `toConcurrentMap`.
2. [Java SE 25 – Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): hợp đồng hiện đại, `toUnmodifiableMap` (Since 10), giới hạn null và behavior duplicate.
3. [Oracle – Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): giải thích `toUnmodifiableMap`, khóa trùng và merge function.
4. [Java SE 17 – Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): hành vi remapping function, đặc biệt kết quả null làm xóa mapping.
5. [Java SE 17 – LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): insertion order và semantics thay giá trị key đã tồn tại.
6. [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): encounter order, `distinct`, parallel stream và terminal operations.
7. [Java SE 17 – Object.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): bình đẳng key và hợp đồng hash code.
8. [OpenJDK – JEP 269](https://openjdk.org/jeps/269): các unmodifiable collection factories được đưa vào Java 9, giúp phân biệt `Map.of` với collectors.
9. [OpenJDK – JEP 286](https://openjdk.org/jeps/286): suy luận kiểu biến cục bộ `var` từ Java 10, được dùng trong ví dụ.
10. [Java SE 17 – Collectors.toUnmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function)): overload giới thiệu từ Java 10 và cơ chế fail-on-duplicate.

**Kết luận:** Với `Collectors.toMap(keyMapper,valueMapper)` và `Collectors.toUnmodifiableMap(keyMapper,valueMapper)`, **trùng khóa sau `keyMapper` là lỗi `IllegalStateException`**, kể cả khi hai value giống hệt. Nếu duplicate là hợp lệ, phải định nghĩa merger rõ ràng; nếu cần giữ tất cả bản ghi, dùng `groupingBy`. Chọn loại Map, thứ tự và semantics null/concurrency theo **hợp đồng API**, tránh phụ thuộc vào implementation detail hoặc thứ tự không được bảo đảm.
