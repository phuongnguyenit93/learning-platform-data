# Biến thể toUnmodifiableMap có hàm hợp nhất trong Java

## 1. Bài toán và kiến thức chính

Khi chuyển một `Stream<T>` thành `Map<K,U>`, nhiều phần tử nguồn có thể tạo ra **cùng một khóa**. Java cần một quy tắc quyết định giá trị nào sẽ được lưu cho khóa đó. Trong nhóm **Collector bản đồ** của Java 10, `Collectors.toUnmodifiableMap` có hai biến thể:

~~~java
// Chữ ký API minh họa, không phải khai báo phương thức độc lập:
Collectors.toUnmodifiableMap(keyMapper, valueMapper);
Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction);
~~~

Khác biệt cốt lõi:

- **Hai tham số**: khi hai phần tử tạo ra khóa trùng theo `equals`, thao tác `collect` ném `IllegalStateException`. Chỉ dùng khi khóa được đảm bảo duy nhất, hoặc muốn chủ động phát hiện dữ liệu trùng.
- **Ba tham số**: khi khóa trùng, Java dùng `mergeFunction` để kết hợp các giá trị tương ứng thành một giá trị cho khóa đó. Kết quả là **Map không sửa được (unmodifiable)**.
- Cả hai đều có từ **Java 10**, vẫn được hỗ trợ trên JDK hiện đại, **không cho phép khóa/giá trị null** và không cam kết thứ tự duyệt Map kết quả.

Một ví dụ dễ hiểu: các dòng bán hàng cùng mã sản phẩm phải được **cộng số lượng**, không phải gây lỗi hay âm thầm ghi đè.

~~~java
// Đoạn minh họa trong phương thức, Java 17+.
record Sale(String sku, int quantity) {}

var sales = List.of(
        new Sale("A", 2),
        new Sale("B", 4),
        new Sale("A", 3)
);

var totals = sales.stream().collect(
        Collectors.toUnmodifiableMap(
                Sale::sku,         // Tạo key String.
                Sale::quantity,    // Tạo value Integer qua boxing.
                Integer::sum       // Khi key trùng: cộng hai value.
        )
);

System.out.println(totals.get("A")); // 5
System.out.println(totals.get("B")); // 4
~~~

`record Sale` là khai báo kiểu minh họa, có thể đặt trong một phương thức ở Java 17+ hoặc ở cấp class. Muốn chạy riêng, xem chương trình đầy đủ ở mục 9.

Với mã sản phẩm `"A"`, hai phần tử có value `2` và `3`. Hàm `Integer::sum` tính `2 + 3 = 5`. Map cuối chứa một entry cho key `"A"`, thay vì hai entry trùng nhau (vì Map không cho phép khóa trùng).

**Không nhầm:** `mergeFunction` giải quyết **trùng khóa đầu ra sau ánh xạ**, không nhất thiết giải quyết hai phần tử đầu vào bằng nhau. Hai đối tượng `Sale` khác nhau hoàn toàn vẫn có thể cho cùng key `"A"`.

## 2. Chữ ký generic và vai trò từng tham số

Chữ ký đầy đủ của biến thể ba tham số:

~~~java
// Mô tả chữ ký trong Javadoc java.util.stream.Collectors:
public static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction
)
~~~

Bảng đọc kiểu:

| Thành phần | Vai trò | Ví dụ trong dữ liệu bán hàng |
| --- | --- | --- |
| `T` | Kiểu của từng phần tử đi qua Stream | `Sale` |
| `K` | Kiểu khóa trong Map | `String` |
| `U` | Kiểu giá trị trong Map | `Integer` |
| `keyMapper` | Hàm biến `T` thành khóa `K` | `Sale::sku` |
| `valueMapper` | Hàm biến `T` thành giá trị `U` | `Sale::quantity` (boxing `int` thành `Integer`) |
| `mergeFunction` | `BinaryOperator<U>`, kết hợp hai giá trị `U` có cùng khóa | `Integer::sum` |
| `Collector<T, ?, Map<K,U>>` | Bộ thu thập kết quả | `Map<String,Integer>` không sửa được |

Một `BinaryOperator<U>` nhận **hai giá trị cùng kiểu `U`** rồi trả về một giá trị `U`. Nó không nhận key trực tiếp theo chữ ký. Nếu quy tắc hợp nhất cần biết key, hãy cân nhắc chuyển thông tin cần thiết vào value, chuẩn hóa dữ liệu trước collect hoặc dùng thuật toán tổng hợp phù hợp thay vì giả định `mergeFunction` sẽ tự nhận key.

~~~java
// Hai dạng tương đương khi U là Integer:
Integer::sum
(left, right) -> left + right
~~~

`Integer::sum` rõ ý định và hợp với tổng số lượng. Trong tính toán nghiệp vụ có thể tràn số, `Integer::sum` sử dụng phép cộng `int` thông thường; nếu cần phát hiện overflow, có thể cân nhắc `Math::addExact` (và chấp nhận khả năng ném `ArithmeticException`) hoặc chọn kiểu dữ liệu có độ rộng thích hợp.

### Khi nào merge được gọi?

Khi các giá trị của **hai phần tử được ánh xạ tới cùng key theo `equals`**, collector gọi hàm hợp nhất theo cơ chế `Map.merge`. Một key chỉ xuất hiện một lần không cần hợp nhất. Một key xuất hiện nhiều lần có thể được hợp nhất nhiều lần cho tới khi có giá trị kết quả.

Ví dụ nguồn có `A:2, A:3, A:4`, `Integer::sum` tạo tổng `9`. Không nên giả định merge được gọi theo một thứ tự thực thi duy nhất trên **parallel stream**; chọn phép hợp nhất phù hợp với các cách chia và kết hợp dữ liệu.

## 3. So sánh biến thể hai và ba tham số

### Hai tham số: trùng khóa là lỗi

~~~java
// Đoạn minh họa trong phương thức.
var items = List.of("A:2", "A:3");

var result = items.stream().collect(
        Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2))
        )
);
// Khi collect: IllegalStateException do key "A" trùng.
~~~

Đoạn trên **cố ý ném lỗi runtime**, không phải chương trình độc lập cần chạy nguyên trạng. Với hai mapper, Java không được tự quyết định giữ giá trị `2` hay `3`. Lỗi giúp phát hiện những dữ liệu lẽ ra phải unique.

### Ba tham số: xử lý trùng khóa theo chính sách

~~~java
var items = List.of("A:2", "A:3");

var result = items.stream().collect(
        Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2)),
                Integer::sum
        )
);

System.out.println(result.get("A")); // 5
~~~

Collector sẽ gộp hai giá trị `2` và `3` thành `5`. Dùng hàm hợp nhất là một **quyết định nghiệp vụ**: tổng số, giá trị lớn nhất, trạng thái ưu tiên, tập hợp dữ liệu… phải được xác định trước khi viết code.

| Tiêu chí | Hai tham số | Ba tham số |
| --- | --- | --- |
| Tham số `keyMapper` và `valueMapper` | Có | Có |
| Khóa trùng | `IllegalStateException` | Gọi `mergeFunction` |
| Kết quả | Unmodifiable Map | Unmodifiable Map |
| Cho phép key/value null | Không | Không |
| Thứ tự iteration Map | Không bảo đảm | Không bảo đảm |
| Cần định nghĩa chính sách gộp | Không; trùng là lỗi | **Có**, qua `BinaryOperator<U>` |
| Mục đích phổ biến | Bảng tra khóa chắc chắn unique | Tổng hợp theo khóa có thể lặp |

**Đừng dùng ba tham số với `(left, right) -> right` chỉ để bỏ qua lỗi** nếu việc khóa trùng là bất thường. Chọn “giữ giá trị cuối” làm mất dữ liệu, nên cần có yêu cầu nghiệp vụ rõ ràng và cách kiểm thử xác nhận chính sách.

## 4. Các chính sách hợp nhất thường dùng

### 4.1. Cộng số lượng

~~~java
var quantities = List.of(2, 3, 4);
var totals = quantities.stream().collect(
        Collectors.toUnmodifiableMap(
                number -> "A",
                number -> number,
                Integer::sum
        )
);

System.out.println(totals.get("A")); // 9
~~~

Đây là phép hợp nhất **có tính kết hợp và giao hoán** với phép cộng `int` (xét theo quy tắc overflow `int` của Java), nên kết quả không phụ thuộc việc đổi nhóm/thứ tự tính toán trên các giá trị `int`. Tuy nhiên không dùng dữ liệu có thể vượt giới hạn nếu nghiệp vụ đòi tính toán không tràn số.

### 4.2. Lấy giá trị lớn nhất

~~~java
var scores = List.of(8, 6, 9, 7);
var highest = scores.stream().collect(
        Collectors.toUnmodifiableMap(
                number -> "team",
                number -> number,
                Integer::max
        )
);

System.out.println(highest.get("team")); // 9
~~~

`Integer::max` kết hợp các value giống kiểu `Integer` và có tính kết hợp, giao hoán, thích hợp khi muốn chọn điểm cao nhất cho một key.

### 4.3. Ghép thông tin thành một value

~~~java
var tags = List.of("red", "blue", "green");

var joined = tags.stream().collect(
        Collectors.toUnmodifiableMap(
                s -> "colors",
                s -> s,
                (left, right) -> left + "|" + right
        )
);

System.out.println(joined.get("colors")); // red|blue|green
~~~

Ví dụ dùng **ordered sequential stream** của `List`, với phép ghép chuỗi có tính kết hợp; cùng một key nên kết quả là chuỗi các màu được nối. Phép ghép chuỗi không giao hoán. Nếu áp dụng cho những nguồn không có encounter order hoặc dùng collector không cam kết order, không nên dựa vào vị trí left/right là “bản ghi đến trước” theo thời gian.

Cách an toàn hơn khi **thứ tự có ý nghĩa nghiệp vụ** là giữ dữ liệu thành `List` theo đúng encounter order hoặc dùng một quy tắc sort trước khi ghép, rồi chỉ công bố bản đồ sau khi đã xác định dữ liệu.

### 4.4. Giữ bản ghi ưu tiên theo thuộc tính

~~~java
// Minh họa trong method, record hỗ trợ Java 17+.
record Offer(String sku, int priority, String text) {}

var offers = List.of(
        new Offer("P", 2, "basic"),
        new Offer("P", 5, "premium")
);

var selected = offers.stream().collect(
        Collectors.toUnmodifiableMap(
                Offer::sku,
                offer -> offer,
                (a, b) -> a.priority() >= b.priority() ? a : b
        )
);

System.out.println(selected.get("P").text()); // premium
~~~

Hàm chọn giá trị có `priority` cao hơn có ý nghĩa khi các giá trị trong cùng nhóm được so sánh nhất quán. Nếu có nhiều phần tử cùng priority mà cần tie-breaker ổn định, phải công bố thêm quy tắc phân xử (ví dụ thời điểm/id); hàm chọn một phía mơ hồ có thể khiến kết quả phụ thuộc cách gộp dữ liệu.

## 5. Tính kết hợp của mergeFunction và parallel stream

Collector có thể được dùng trong pipeline song song, nơi dữ liệu bị chia thành nhiều phần rồi được kết hợp. Để kết quả chính xác, hàm hợp nhất nên:

1. **Có tính kết hợp (associative):** `merge(merge(a,b),c)` tương đương `merge(a,merge(b,c))` theo nghĩa kết quả mong muốn.
2. **Không có side effect không được kiểm soát:** không thay đổi biến dùng chung, không ghi vào cấu trúc ngoài collector, không phụ thuộc số lần/góc độ gọi.
3. **Đóng trên kiểu value:** luôn trả một giá trị hợp lệ của `U` phù hợp với hợp đồng Map.
4. **Giao hoán (commutative) nếu nghiệp vụ không có thứ tự:** `merge(a,b)` bằng `merge(b,a)` giúp kết quả độc lập thứ tự quan sát. Tính giao hoán không phải yêu cầu tuyệt đối của mọi phép gộp có thứ tự, nhưng hữu ích khi phải bảo đảm tính xác định với nguồn không có order.

~~~java
// HỢP LỆ cho cả ordered stream tuần tự và song song:
var values = List.of(2, 3, 4, 5);

var parallelResult = values.parallelStream().collect(
        Collectors.toUnmodifiableMap(
                v -> "sum",
                v -> v,
                Integer::sum
        )
);

System.out.println(parallelResult.get("sum")); // 14
~~~

Trái lại, dùng phép **trừ**:

~~~java
// Ví dụ được viết để chỉ ra nguy cơ, không khẳng định stdout cụ thể.
var potentiallyUnstable = List.of(20, 5, 2).parallelStream().collect(
        Collectors.toUnmodifiableMap(
                v -> "result",
                v -> v,
                (a, b) -> a - b
        )
);
~~~

Phép trừ không kết hợp: `(20 - 5) - 2 = 13` nhưng `20 - (5 - 2) = 17`. Nếu quy tắc tổng hợp phụ thuộc vào nhóm do collector lựa chọn, kết quả có thể ngoài kỳ vọng. Tránh dùng các merge function không kết hợp, đặc biệt với parallel stream. Không dùng việc một lần chạy tuần tự tình cờ cho đúng kết quả để khẳng định code an toàn khi chuyển sang parallel.

### Phân biệt với concurrent collector

`Collectors.toUnmodifiableMap` không được quảng bá là concurrent collector. Nó tạo Map **không sửa được ở đầu ra**, nhưng bản thân điều đó **không đồng nghĩa** với Map concurrent trong quá trình collect.

Nếu bài toán yêu cầu tổng hợp concurrent, có các collector khác như `toConcurrentMap`, song chúng có hợp đồng khác và không tự tạo unmodifiable Map. Cần phân biệt concurrency của quá trình thu thập với tính không sửa được của kết quả, cũng như với khả năng thay đổi trạng thái các object value.

## 6. Key trùng theo equals, không phải do cùng instance

Hai phần tử stream có thể khác nhau nhưng `keyMapper` trả các key **bằng nhau theo `equals`**. Ví dụ:

~~~java
var names = List.of("Java", "java", "JDK");

var byFirstCharacter = names.stream().collect(
        Collectors.toUnmodifiableMap(
                word -> word.substring(0, 1).toLowerCase(),
                word -> 1,
                Integer::sum
        )
);

System.out.println(byFirstCharacter.get("j")); // 3
~~~

Các chuỗi không giống nhau hoàn toàn, nhưng mapper chuẩn hóa chữ đầu thành `"j"` cho tất cả; collector gộp chúng thành một key với tổng `3`.

Trong thực tế, chuẩn hóa key (chữ hoa/thường, khoảng trắng, mã định danh…) cần được quyết định rõ. Nếu thao tác chuẩn hóa làm hai key vốn có ý nghĩa khác nhau trở thành một, merge sẽ kết hợp dữ liệu theo quy tắc bạn đã viết. Hãy kiểm tra kỹ `equals`/`hashCode` của kiểu key; dùng key mutable có các trường ảnh hưởng equality là rủi ro chung của Map.

**Không có entry kép với cùng key** trong kết quả. Map không phải multi-map. Nếu cần giữ **mọi value cho một key**, hãy dùng `groupingBy` với `List` thích hợp rồi chủ động chuyển sang cấu trúc không sửa được, thay vì dùng merge để chọn một value và đánh mất những giá trị khác.

## 7. Null và lỗi cần xử lý

### 7.1. Mapper trả null

Cả biến thể hai và ba tham số của `toUnmodifiableMap` đều **từ chối null key và null value**. Nếu `keyMapper` hoặc `valueMapper` trả null, thao tác `collect` ném `NullPointerException`.

~~~java
// Đoạn minh họa lỗi runtime:
var lines = List.of("A", "B");

var invalid = lines.stream().collect(
        Collectors.toUnmodifiableMap(
                s -> s.equals("B") ? null : s,
                s -> s.length(),
                Integer::sum
        )
);
// NullPointerException: keyMapper trả null với phần tử "B".
~~~

Không nên suy rằng một Map implementation có thể chứa null nên collector unmodifiable map cũng sẽ chấp nhận. **Hợp đồng API collector** mới là nguồn quyết định.

### 7.2. Null ở tham số chức năng

Truyền `null` thay cho `keyMapper`, `valueMapper` hoặc `mergeFunction` cũng bị từ chối. Các callback phải có giá trị hợp lệ. Nếu phần tử nguồn là null thì mapper của bạn cũng có thể ném `NullPointerException` khi truy cập nó; đây là trường hợp riêng cần cân nhắc trong pipeline.

### 7.3. Hàm merge trả null: không phải quy tắc giữ một giá trị null

Javadoc liên hệ `mergeFunction` với cách hoạt động của `Map.merge`. Trong những implementation sử dụng quy tắc đó, một kết quả merge bằng `null` có thể làm **loại bỏ entry của key**, thay vì ghi value null. Không xem `null` là một value hợp lệ được lưu trong unmodifiable Map, và **không** chọn việc trả null để giải quyết trùng nếu nghiệp vụ không chủ đích xóa ánh xạ. Tốt nhất hãy viết merge function trả value **không null** có nghĩa rõ ràng và kiểm thử hành vi đầy đủ trên target JDK của dự án.

### 7.4. Hàm mapper/merge tự ném ngoại lệ

Nếu mapper gọi hàm xử lý dữ liệu lỗi hoặc merge function chủ động `throw`, thao tác `collect` sẽ thất bại và không trả về Map hợp lệ. Đừng bắt rồi bỏ qua lỗi một cách âm thầm; nếu dữ liệu không thể gộp, tốt hơn để lỗi thể hiện rõ hoặc chuyển dữ liệu lỗi sang luồng xử lý/kiểm tra riêng.

### 7.5. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `IllegalStateException` khi dùng 2 mapper | Hai phần tử tạo key trùng | Dùng biến thể ba tham số nếu trùng hợp lệ; hoặc kiểm dữ liệu |
| `NullPointerException` khi collect | Null key/value từ mapper hoặc tham số callback null | Xử lý/kiểm tra null trước khi collect |
| Kết quả khác khi song song | Hàm merge không có tính kết hợp hoặc dựa vào thứ tự/sự kiện ngoài | Dùng phép gộp kết hợp, tránh side effect |
| Mất bản ghi sau khi gộp | Chọn `(a,b)->a` hoặc `(a,b)->b` làm mất giá trị khác | Xác định chính sách; dùng grouping khi cần giữ mọi bản ghi |
| Không thể `put` vào Map trả về | Kết quả unmodifiable | Thu vào Map mutable khi cần sửa, hoặc tạo bản sao mutable |
| Output `map.toString()` đổi thứ tự | Không cam kết iteration order | Kiểm theo key; sắp xếp rõ ràng khi trình bày |
| Gọi `toUnmodifiableMap` với map factory 4 tham số | API không có overload 4 tham số với supplier | Dùng `toMap(..., supplier)` rồi chụp/bọc kết quả khi cần |
| Mong Map copy làm value object bất biến sâu | Chỉ container không sửa được, object value có thể mutable | Dùng immutable value/defensive copy |

## 8. Không sửa được, thứ tự duyệt và các overload liên quan

### 8.1. Không thể sửa kết quả

~~~java
var counts = List.of("A", "B", "A").stream().collect(
        Collectors.toUnmodifiableMap(s -> s, s -> 1, Integer::sum)
);

// Nếu thực thi, lệnh dưới ném UnsupportedOperationException:
// counts.put("C", 1);
~~~

`toUnmodifiableMap` bảo đảm Map đầu ra không sửa được qua API mutator, không phải chỉ “trả Map” theo nghĩa chung. Điều này giúp công bố các bảng tổng hợp đã chốt một lần.

Nhưng các object value vẫn có thể mutable. Nếu `U` là một `ArrayList`, bản thân giá trị được tham chiếu vẫn có thể được sửa nếu có lối truy cập, dù không thể `put` key mới qua Map. Nếu yêu cầu immutable sâu, hãy chọn value object immutable hoặc tạo bản sao dữ liệu con thích hợp trước khi công bố kết quả.

### 8.2. Không bảo đảm thứ tự duyệt Map

Kết quả `toUnmodifiableMap` là Map không sửa được, **không cam kết giữ insertion order của nguồn Stream**. Không viết unit test dựa vào chuỗi `{A=1, B=2}` theo một thứ tự key giả định.

Kiểm tra bằng key:

~~~java
System.out.println(counts.get("A")); // 2
System.out.println(counts.size());   // 2
~~~

Hoặc nếu cần hiển thị có thứ tự từ điển:

~~~java
System.out.println(new java.util.TreeMap<>(counts)); // {A=2, B=1}
~~~

`TreeMap` dùng thứ tự tự nhiên/comparator theo key, nên kết quả trình bày cố định. Không nhầm việc tạo bản sao `TreeMap` để hiển thị với việc Map gốc tự giữ thứ tự.

### 8.3. Phân biệt `toMap` có merge và `toUnmodifiableMap` có merge

~~~java
// Không bảo đảm tính sửa được của Map từ toMap:
var raw = stream.collect(
        Collectors.toMap(keyMapper, valueMapper, mergeFunction)
);

// Đảm bảo Map kết quả không sửa được:
var fixed = stream.collect(
        Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
);
~~~

Hai đoạn là **mã minh họa**, giả sử `stream` và ba callback đã được khai báo hợp lệ. `Collectors.toMap` không cam kết implementation hay mutability của Map kết quả, nên không dùng nó như hợp đồng bảo đảm unmodifiable hoặc mutable. Nếu cần chắc chắn có một mutable Map, dùng overload `toMap(..., mapFactory)` với supplier phù hợp như `HashMap::new` hoặc `LinkedHashMap::new`.

### 8.4. Nếu cần một Map unmodifiable giữ insertion order

`toUnmodifiableMap` **không có** overload nhận `mapFactory`. Bạn có thể sử dụng `Collectors.toMap` với `LinkedHashMap::new` để kiểm soát backing Map, rồi tạo một **bản sao LinkedHashMap** và bọc view không sửa được:

~~~java
// Minh họa trong method, các input không null.
var orderedMutable = sales.stream().collect(
        Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum,
                java.util.LinkedHashMap::new
        )
);

var orderedSnapshot = java.util.Collections.unmodifiableMap(
        new java.util.LinkedHashMap<>(orderedMutable)
);
~~~

Khi source là ordered sequential stream, `LinkedHashMap` ghi nhận thứ tự lần xuất hiện đầu của các key trong quá trình chèn. Bọc một **bản sao mới** đảm bảo thay đổi cấu trúc `orderedMutable` sau đó không phản ánh vào snapshot; wrapper bản thân là view của backing copy mới (không rò rỉ). Không thay bằng `Map.copyOf(orderedMutable)` nếu yêu cầu thứ tự duyệt, vì `Map.copyOf` không cam kết giữ insertion order.

### 8.5. So sánh với groupingBy

Nếu cần tất cả các value cho một key, hãy lưu **danh sách** thay vì hợp nhất thành một value duy nhất:

~~~java
// Minh họa trong method, các dòng Sale đã có.
var grouped = sales.stream().collect(
        Collectors.groupingBy(Sale::sku)
);
~~~

`groupingBy` mặc định tạo `Map<String,List<Sale>>` với các nhóm, không bảo đảm map unmodifiable; danh sách nhóm có thể cần được đóng băng riêng để tránh lộ tham chiếu mutable. Nếu mục tiêu là chỉ lưu **tổng**, `toUnmodifiableMap(Sale::sku, Sale::quantity, Integer::sum)` gọn hơn và công bố rõ chính sách merge.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sau dùng dữ liệu bán hàng có khóa trùng, thực hiện hai chính sách merge (`sum` và `max`), đối chiếu xử lý parallel stream, bắt lỗi overload hai mapper, xác nhận unmodifiable và kiểm thử null. Các dòng output có thứ tự được xác định, không phụ thuộc iteration order của Map.

Lưu tệp đúng tên **`UnmodifiableMapMergeDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class UnmodifiableMapMergeDemo {
    record Sale(String sku, int quantity) {}

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("P1", 2),
                new Sale("P2", 4),
                new Sale("P1", 3),
                new Sale("P2", 1),
                new Sale("P3", 5)
        );

        Map<String, Integer> totals = sales.stream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::sku,
                        Sale::quantity,
                        Integer::sum
                )
        );

        System.out.println("totals=" + new TreeMap<>(totals));
        System.out.println("p1Total=" + totals.get("P1"));
        System.out.println("totalKeys=" + totals.size());

        var maximums = sales.stream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::sku,
                        Sale::quantity,
                        Integer::max
                )
        );

        System.out.println("maximums=" + new TreeMap<>(maximums));

        var parallelTotals = sales.parallelStream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::sku,
                        Sale::quantity,
                        Integer::sum
                )
        );

        System.out.println("parallelMatches=" + totals.equals(parallelTotals));

        try {
            sales.stream().collect(
                    Collectors.toUnmodifiableMap(
                            Sale::sku,
                            Sale::quantity
                    )
            );
        } catch (IllegalStateException expected) {
            System.out.println("duplicateWithoutMergeRejected=true");
        }

        try {
            totals.put("P4", 10);
        } catch (UnsupportedOperationException expected) {
            System.out.println("immutableResult=true");
        }

        try {
            sales.stream().collect(
                    Collectors.toUnmodifiableMap(
                            sale -> sale.sku().equals("P2") ? null : sale.sku(),
                            Sale::quantity,
                            Integer::sum
                    )
            );
        } catch (NullPointerException expected) {
            System.out.println("nullKeyRejected=true");
        }

        try {
            sales.stream().collect(
                    Collectors.toUnmodifiableMap(
                            Sale::sku,
                            sale -> sale.sku().equals("P1") ? null : sale.quantity(),
                            Integer::sum
                    )
            );
        } catch (NullPointerException expected) {
            System.out.println("nullValueRejected=true");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên có hỗ trợ `--release 17`:

~~~bash
javac --release 17 UnmodifiableMapMergeDemo.java
java UnmodifiableMapMergeDemo
~~~

**Stdout chính xác:**

~~~text
totals={P1=5, P2=5, P3=5}
p1Total=5
totalKeys=3
maximums={P1=3, P2=4, P3=5}
parallelMatches=true
duplicateWithoutMergeRejected=true
immutableResult=true
nullKeyRejected=true
nullValueRejected=true
~~~

### Giải thích đầu ra

1. `Sale::sku` tạo các key `P1`, `P2`, `P3`. `P1` xuất hiện hai lần với quantity `2` và `3`, nên `Integer::sum` cho `5`. `P2` có `4` và `1`, cũng ra `5`. `P3` chỉ có một dòng và giữ `5`. `new TreeMap<>(totals)` sắp xếp các key để in ổn định.
2. `totals.get("P1")` cho `5`, `size()` cho `3` bởi kết quả có một entry cho mỗi key phân biệt.
3. `Integer::max` chọn giá trị lớn nhất của từng key: `P1=3`, `P2=4`, `P3=5`.
4. `parallelStream()` cộng số nguyên bằng hàm kết hợp/giao hoán nên cho Map cùng nội dung; `Map.equals` không phụ thuộc thứ tự duyệt, vì vậy in `parallelMatches=true`.
5. Bỏ `mergeFunction` ở biến thể hai mapper khiến các key `P1`/`P2` trùng và `collect` ném `IllegalStateException`.
6. Gọi `totals.put(...)` ném `UnsupportedOperationException`; kết quả của collector là unmodifiable Map.
7. Hàm `keyMapper` được cố ý cho trả `null` với `P2`; `valueMapper` cố ý trả `null` với `P1` trong hai phép thử riêng. Cả hai đều bị `NullPointerException`, không có Map hợp lệ nào được trả về.

Mã không in trực tiếp Map có iteration order không cam kết. Các tình huống gây ngoại lệ được bọc riêng trong `try/catch`, vì vậy chương trình chạy hết và output có thể xác minh trên Java 17+.

## 10. Lưu ý thiết kế và hiệu năng

### Không nhầm tính unmodifiable với thread-safety sâu

Sau khi `collect` hoàn thành, cấu trúc Map không bị sửa qua API của chính Map kết quả. Tuy nhiên:

- Nếu value là object mutable, mã khác vẫn có thể sửa trạng thái object ấy.
- Nếu key là object mutable và các trường ảnh hưởng `equals/hashCode` bị sửa, truy vấn `get` có thể không còn đúng như dự kiến.
- Việc tạo Map không sửa được không đồng nghĩa rằng toàn bộ các object bên trong là thread-safe.

Ưu tiên key/value immutable khi dùng Map làm bảng tra nhiều luồng hoặc công bố trạng thái ổn định.

### Không phụ thuộc thứ tự merge tùy tiện

`BinaryOperator` nên diễn đạt một phép gộp xác định, đặc biệt nếu chạy parallel hoặc unordered stream. Với dữ liệu mà thứ tự thời gian quan trọng, nên làm rõ order và lựa chọn value theo thuộc tính dữ liệu (timestamp, priority, ID) thay vì suy vào một thứ tự thực thi không được cam kết của callback.

### Tránh cấp phát/copy thừa khi hiệu năng quan trọng

`toUnmodifiableMap` là collector thông thường và không được công bố là concurrent. Trong parallel stream, các map tạm có thể cần hợp nhất; điều này có chi phí. Không kết luận `parallelStream()` nhanh hơn `stream()` chỉ từ cú pháp. Đo hiệu năng với kích thước dữ liệu và workload thực tế trước khi chọn.

### Không có overload thứ tư nhận Supplier

`Collectors.toUnmodifiableMap` chỉ có hai overload nhận **2** và **3** đối số. Nếu muốn điều khiển loại Map cụ thể, dùng `Collectors.toMap` có `mapFactory` hoặc tự xây Map, sau đó bọc một bản sao phù hợp để ngăn sửa. Kể cả khi Map đầu ra không sửa được, `Map.copyOf` cũng không cam kết giữ thứ tự chèn hay comparator của Map nguồn.

### Khi nào nên dùng hàm merge và khi nào không?

- **Trùng là lỗi dữ liệu:** dùng hai mapper để nhận `IllegalStateException`, hoặc kiểm tra unique key từ trước.
- **Trùng hợp lệ và cần tổng:** ba mapper với `Integer::sum`, `Long::sum` hoặc kiểu số/hàm có kiểm soát overflow phù hợp.
- **Trùng hợp lệ và cần max/min:** dùng phép chọn theo comparator có quy tắc tie-breaker rõ.
- **Cần tất cả value, không được mất occurrence:** dùng `groupingBy`/`groupingByConcurrent` theo thiết kế tương ứng, hoặc value là danh sách được tổng hợp đúng cách và đóng băng sau cùng.
- **Cần thứ tự key ổn định:** chọn `LinkedHashMap`/`TreeMap` và wrapper snapshot thay vì tin vào order của unmodifiable Map factory.

## 11. Checklist kiểm thử

- [ ] Đã xác định rõ key do `keyMapper` tạo ra và điều kiện hai key được coi là trùng theo `equals` chưa?
- [ ] Với key trùng hợp lệ, merge function có phản ánh đúng yêu cầu nghiệp vụ không?
- [ ] Hàm merge có tính kết hợp? Nếu stream không có order, có cần tính giao hoán?
- [ ] Mapper và merge function có tránh side effect, đặc biệt trong parallel stream không?
- [ ] Có xử lý null key/value trước collect không?
- [ ] Có kiểm thử overload không merge ném `IllegalStateException` khi key trùng không?
- [ ] Có kiểm thử map kết quả không cho `put`/`remove` không?
- [ ] Unit test so sánh `Map.equals` hoặc `get(key)` thay vì thứ tự `toString()` chưa?
- [ ] Nếu output phải có thứ tự, đã sắp xếp hoặc chọn backing Map có order rõ ràng chưa?
- [ ] Nếu key/value mutable, có defensive copy hoặc mô hình immutable thích hợp chưa?
- [ ] Nếu dùng parallel, đã kiểm thử kết quả có giống serial với dữ liệu lớn/khóa trùng nhiều chưa?
- [ ] Đã biên dịch với `--release` tương ứng target Java chưa?

## 12. Câu hỏi tự đánh giá

**Câu 1.** `Stream.of("A","A").collect(Collectors.toUnmodifiableMap(s -> s, s -> 1))` xảy ra điều gì?

**Đáp án:** Ném `IllegalStateException` vì hai phần tử tạo cùng key `"A"` và không có merge function.

**Câu 2.** Nếu thêm `Integer::sum` làm đối số thứ ba thì kết quả `get("A")` bằng bao nhiêu?

**Đáp án:** `2`. Hai value `1` được cộng lại thành một value của key `A`.

**Câu 3.** `mergeFunction` nhận những gì? Nó có nhận key trực tiếp không?

**Đáp án:** Là `BinaryOperator<U>` nhận **hai value cùng kiểu `U`**, trả một value `U`; chữ ký không có tham số key.

**Câu 4.** Tại sao `Integer::max` phù hợp với parallel stream hơn phép `(a,b)->a-b`?

**Đáp án:** `max` có tính kết hợp; phép trừ không có tính kết hợp và có thể cho kết quả khác khi thay đổi cách nhóm thao tác.

**Câu 5.** Có thể gọi `put` vào map trả về bởi `toUnmodifiableMap` không?

**Đáp án:** Không. Mutator sẽ bị từ chối, thường bằng `UnsupportedOperationException`.

**Câu 6.** `keyMapper` hoặc `valueMapper` trả `null` thì sao?

**Đáp án:** `collect` ném `NullPointerException`; Map kết quả không cho phép null key/value.

**Câu 7.** Có thể dùng `Collectors.toUnmodifiableMap(key, value, merge, LinkedHashMap::new)` không?

**Đáp án:** Không có overload thứ tư. Dùng `Collectors.toMap` với map factory rồi bọc snapshot phù hợp nếu cần Map không sửa được và duyệt theo thứ tự.

**Câu 8.** Vì sao ví dụ `new TreeMap<>(totals)` được dùng khi in?

**Đáp án:** Vì unmodifiable Map không cam kết iteration order; TreeMap sắp xếp theo key, giúp stdout ổn định.

**Câu 9.** Nếu muốn lưu tất cả giá trị cho một key thay vì hợp nhất thành một value, dùng gì?

**Đáp án:** Cân nhắc `Collectors.groupingBy` tạo `Map<K,List<T>>` rồi bảo vệ/dùng bản sao của các danh sách và map khi công bố. Không dùng merger chọn một value khiến mất occurrence.

## 13. Tài liệu chuẩn vẫn đang áp dụng

- [Oracle Java SE 26 — Collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): tài liệu hiện hành cho cả hai overload `toUnmodifiableMap`, xử lý key trùng, quy tắc null, giới thiệu từ Java 10, và liên kết với `Map.merge`.
- [Oracle Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): cùng hợp đồng trên Java 17, dùng để kiểm tra dự án với `--release 17`.
- [Oracle Java SE 17 — Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): ngữ nghĩa hợp nhất key/value, bao gồm trường hợp hàm remapping trả null.
- [Oracle Java SE 17 — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html): interface hàm nhận hai value cùng kiểu.
- [Oracle Java SE 17 — Collectors.toMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toMap(java.util.function.Function,java.util.function.Function,java.util.function.BinaryOperator,java.util.function.Supplier)): overload có mapFactory nếu cần kiểm soát implementation.
- [Oracle Java SE 17 — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): tạo unmodifiable map từ Map đã có; không dùng làm bước tự gộp duplicate.
- [Dev.java — Collectors](https://dev.java/learn/api/streams/collectors/): tài liệu học tập về collector và cách kết hợp stream thành collection theo hợp đồng.

**Ghi nhớ:** `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` là công cụ **hợp nhất những giá trị của các phần tử tạo key trùng** thành một entry trong Map **không sửa được**. Hàm merge phải thể hiện đúng quy tắc nghiệp vụ, nên có tính kết hợp và không gây side effect để chạy ổn định. Nếu trùng khóa là lỗi, dùng overload hai tham số; nếu cần giữ toàn bộ các value, chọn mô hình grouping thay vì làm mất dữ liệu bằng một phép gộp không phù hợp.