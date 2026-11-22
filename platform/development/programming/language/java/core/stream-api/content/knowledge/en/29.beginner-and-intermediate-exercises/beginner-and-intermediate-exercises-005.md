# Thiết kế Map với khóa trùng và thứ tự đầu ra xác định

## 1. Đề bài: kết quả đúng phải vừa xử lý khóa trùng, vừa có thứ tự rõ ràng

Khi xử lý dữ liệu khai báo bằng **Java Stream API**, ta thường chuyển một `Stream<T>` thành `Map<K, V>` để tra cứu nhanh theo mã sản phẩm, mã khách hàng hoặc nhóm nghiệp vụ. Phép thu thập này dễ gặp hai vấn đề:

1. **Khóa trùng:** nhiều phần tử nguồn sinh ra cùng một khóa `K`. Chương trình phải quyết định giữ bản nào, cộng giá trị hay báo lỗi.
2. **Thứ tự đầu ra:** thứ tự duyệt các entry của Map có thể cần theo thứ tự xuất hiện ban đầu hoặc theo khóa đã sắp xếp, thay vì phụ thuộc vào hành vi tình cờ của `HashMap`.

Ví dụ, bảng cập nhật sản phẩm có cùng mã `"P01"` ở nhiều dòng:

```text
Dòng nguồn (có thứ tự):
  P02 | Tai nghe     | phiên bản 1
  P01 | Sổ cũ       | phiên bản 1
  P01 | Sổ mới      | phiên bản 2
  P03 | Bút         | phiên bản 1
  P02 | Tai nghe Pro | phiên bản 3

Yêu cầu:
  - Mỗi SKU chỉ xuất hiện một lần trong Map.
  - Khóa trùng: giữ bản có phiên bản cao nhất.
  - Khi xuất báo cáo: duyệt theo SKU tăng dần.

Kết quả mong đợi:
  P01 -> Sổ mới       (v2)
  P02 -> Tai nghe Pro (v3)
  P03 -> Bút          (v1)
```

Bài học thuộc chương **Bài tập nền tảng và trung cấp** của module `JAVA_STREAM_API`. Ta sẽ giải bài toán qua `Collectors.toMap`, `Map.merge`, `LinkedHashMap`, `TreeMap` và các thao tác Stream như `sorted`, `groupingBy` và `collect`.

**Mục tiêu sau khi học:**

- Hiểu vì sao `Collectors.toMap` hai đối số ném lỗi khi có khóa trùng.
- Viết merge function có ý nghĩa: giữ cũ, thay mới, cộng dồn hoặc chọn bản tốt nhất.
- Chọn `LinkedHashMap` khi cần thứ tự chèn và `TreeMap` khi cần sắp theo khóa.
- Phân biệt **thứ tự nguồn**, **thứ tự xử lý song song** và **thứ tự duyệt Map**.
- Viết chương trình Java 17+ có dữ liệu thử, kết quả dự kiến và các phép kiểm tra xác định.

Các collector cơ bản và các loại Map ở đây có từ Java 8. Ví dụ hoàn chỉnh sử dụng `record` và `Stream.toList()` nên chọn **Java 17+**.

## 2. Ôn tập: Map là gì và tại sao có thể phát sinh trùng khóa?

`Map<K, V>` chứa những cặp `key → value`. Một khóa chỉ có thể tương ứng với **một giá trị trực tiếp** trong cùng một Map; khi thêm một giá trị khác cho khóa đó, cần có chính sách thay thế hoặc kết hợp.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> points = new HashMap<>();
points.put("A", 3);
points.put("B", 5);
points.put("A", 7); // Ghi đè giá trị cũ của A.

System.out.println(points.get("A")); // 7
System.out.println(points.size());   // 2
```

Khi thu thập bằng Stream, khóa được tạo ra bởi **key mapper**; giá trị được tạo ra bởi **value mapper**. Hai phần tử nguồn khác nhau vẫn có thể tạo cùng khóa:

```java
record Sale(String id, String sku, int quantity) {}

List<Sale> sales = List.of(
        new Sale("S01", "P01", 2),
        new Sale("S02", "P02", 3),
        new Sale("S03", "P01", 4)
);

// Hai sale S01 và S03 đều có khóa P01.
```

Quan trọng: **khóa trùng không nhất thiết là lỗi dữ liệu**. Trong báo cáo tổng số lượng theo SKU, trùng là điều bình thường và cần **cộng**. Trong bảng "mỗi SKU chỉ có một bản ghi duy nhất", trùng có thể là lỗi, hoặc cần giữ phiên bản mới nhất.

Trước khi viết code, hãy trả lời:

1. **Khóa là gì?** `sku`, `customerId` hay một khóa ghép?
2. **Khi trùng phải làm gì?** Ném lỗi, cộng, chọn bản đầu, bản cuối hay bản có thứ hạng cao nhất?
3. **Thứ tự đầu ra cần gì?** Không quan trọng, thứ tự xuất hiện đầu tiên hay sắp theo khóa?

Nếu chưa xác định được ba điều đó, một pipeline `toMap` ngắn gọn vẫn có thể sai yêu cầu nghiệp vụ.

## 3. Collectors.toMap hai đối số: khóa trùng sẽ ném lỗi

Hãy bắt đầu với dạng ngắn nhất:

```java
Map<String, Sale> bySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity()
        ));
```

Đoạn trên **ném `IllegalStateException`** do cả `S01` và `S03` cùng ánh xạ tới khóa `"P01"`. Overload hai đối số không mặc định chọn dòng đầu tiên hay dòng cuối cùng.

Chữ ký khái quát:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper
)
```

Trong ví dụ:

| Thành phần | Biểu thức | Kiểu và vai trò |
| --- | --- | --- |
| Phần tử đầu vào | `Sale` | Mỗi giao dịch là một đối tượng. |
| `keyMapper` | `Sale::sku` | Tạo `String` làm khóa. |
| `valueMapper` | `Function.identity()` | Giữ nguyên đối tượng `Sale` làm value. |
| Kiểu kết quả nếu thành công | `Map<String, Sale>` | Một `Sale` cho mỗi SKU. |
| Khi trùng khóa | Không cung cấp merge function | Ném `IllegalStateException`. |

**Khi nào nên dùng hai đối số?** Khi yêu cầu đầu vào **phải duy nhất theo khóa** và phát hiện khóa trùng là lỗi nghiệp vụ. Chẳng hạn, một danh sách cấu hình đã được validate là không có ID trùng.

Lưu ý: overload mặc định của `toMap` **không cam kết kiểu Map hay thứ tự lặp entry**. Ngay cả khi dữ liệu không trùng, đừng viết test phụ thuộc `map.toString()` có thứ tự cố định.

## 4. Collectors.toMap ba đối số: định nghĩa luật xử lý trùng

Khi khóa trùng là hợp lệ, dùng overload có `mergeFunction`:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction
)
```

`mergeFunction` nhận **giá trị đang có** và **giá trị mới cho cùng khóa** rồi tạo giá trị kết hợp. Nó không được tự sửa nguồn đang được Stream duyệt. Có ba cách xử lý thường gặp:

### 4.1. Giữ giá trị đang có

```java
Map<String, Sale> keepExisting = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity(),
                (existing, incoming) -> existing
        ));

System.out.println(keepExisting.get("P01").id()); // S01
```

Trong pipeline **tuần tự có encounter order** ở ví dụ, quy tắc trên giữ bản đầu tiên gặp cho SKU `P01`.

### 4.2. Dùng giá trị mới

```java
Map<String, Sale> useIncoming = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                java.util.function.Function.identity(),
                (existing, incoming) -> incoming
        ));

System.out.println(useIncoming.get("P01").id()); // S03
```

Với nguồn `List` được duyệt tuần tự, quy tắc này giữ bản cuối cùng gặp. **Đừng nhầm "bản cuối theo List" với "bản mới nhất theo ngày"**: để chọn theo phiên bản hoặc thời gian, cần một comparator.

### 4.3. Cộng dồn giá trị

```java
Map<String, Integer> quantityBySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum
        ));

System.out.println(quantityBySku.get("P01")); // 6 = 2 + 4
System.out.println(quantityBySku.get("P02")); // 3
```

Nếu cộng số lượng rất lớn, `int` có thể bị tràn. Hãy chọn `long` hoặc mô hình số phù hợp với phạm vi nghiệp vụ; `Long::sum` vẫn có thể tràn `long`.

### Bảng lựa chọn merge function

| Yêu cầu khi khóa trùng | Merge function mẫu | Điều cần kiểm soát |
| --- | --- | --- |
| Giữ giá trị cũ | `(oldValue, newValue) -> oldValue` | "Cũ" là thứ tự gặp của pipeline, không phải mặc nhiên cũ theo thời gian. |
| Thay bằng giá trị mới | `(oldValue, newValue) -> newValue` | Thứ tự gặp phải có ý nghĩa rõ ràng. |
| Tính tổng | `Integer::sum` / `Long::sum` | Phạm vi số, tính đúng khi kết hợp. |
| Lấy giá trị lớn nhất | `Integer::max` / `BinaryOperator.maxBy(comparator)` | Comparator phải phản ánh nghiệp vụ. |
| Nối chuỗi | `(left, right) -> left + "," + right` | Thứ tự và dấu phân cách, chi phí tạo chuỗi. |

Nếu yêu cầu không chấp nhận dữ liệu trùng, **không nên thêm một merge function tùy ý chỉ để tránh lỗi**. Việc bỏ dữ liệu âm thầm có thể khiến báo cáo sai mà không được phát hiện.

## 5. Chọn bản ghi có ưu tiên cao nhất bằng comparator

Giả sử cùng SKU có nhiều bản cập nhật sản phẩm. Thay vì "đến trước" hay "đến sau", nghiệp vụ yêu cầu **giữ phiên bản lớn nhất**:

```java
record Product(String sku, String name, int version, long priceCents) {}

List<Product> updates = List.of(
        new Product("P02", "Tai nghe", 1, 200_000L),
        new Product("P01", "Sổ cũ", 1, 30_000L),
        new Product("P01", "Sổ mới", 2, 35_000L),
        new Product("P03", "Bút", 1, 8_000L),
        new Product("P02", "Tai nghe Pro", 3, 250_000L)
);

Comparator<Product> byVersion =
        Comparator.comparingInt(Product::version);

Map<String, Product> latestBySku = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion)
        ));

System.out.println(latestBySku.get("P01").name()); // Sổ mới
System.out.println(latestBySku.get("P02").version()); // 3
```

`maxBy` sử dụng comparator để chọn một trong hai value khi trùng khóa. Tuy nhiên, nếu **hai bản cùng version**, comparator trên trả kết quả bằng 0. Khi đó bản nào được giữ có thể không diễn đạt đầy đủ yêu cầu, nhất là nếu xử lý song song hoặc đầu vào không có thứ tự xác định.

Hãy thêm tiêu chí phụ (*tie-break*) nếu kết quả cần **ổn định**:

```java
Comparator<Product> policy = Comparator
        .comparingInt(Product::version)
        .thenComparing(Product::name)
        .thenComparingLong(Product::priceCents);

Map<String, Product> selected = updates.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(policy)
        ));
```

Ở đây ưu tiên version cao; nếu version bằng nhau, dùng tên rồi giá tiền làm tiêu chí tiếp theo. **Đây chỉ là quy tắc minh họa**, không phải mặc định nghiệp vụ hợp lý cho mọi hệ thống. Với dữ liệu thật, thường cần `updatedAt`, số revision hoặc ID bản ghi ổn định để phân xử. Nếu hai đối tượng vẫn so sánh bằng nhau nhưng chứa dữ liệu khác, kết quả "chọn bản nào" chưa được định nghĩa đủ rõ.

**Quan trọng cho parallel reduction:** merge function nên có tính kết hợp và không phụ thuộc vào trạng thái mutable dùng chung. Phép lấy phần tử lớn nhất theo một comparator ổn định và có tiêu chí phân xử đầy đủ thường thích hợp hơn việc "ưu tiên bản đến trước trên thread".

## 6. Thứ tự Map không phải là thứ tự Stream

Đây là phần thứ hai của bài: **cùng một nội dung Map có thể được duyệt theo các thứ tự khác nhau**.

```java
Map<String, Integer> unorderedByContract = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::version,
                Integer::max
        ));

System.out.println(unorderedByContract);
// Có các cặp P01=2, P02=3, P03=1;
// thứ tự xuất hiện của các cặp không được bảo đảm.
```

`Collectors.toMap` mặc định **không cam kết** `HashMap`, `LinkedHashMap`, `TreeMap` hoặc thứ tự lặp entry cụ thể. Vì vậy, không được dựa vào việc máy hiện tại luôn in `P01` trước `P02`.

Phân biệt ba thứ tự:

| Loại thứ tự | Ví dụ | Có phải điều được bảo đảm không? |
| --- | --- | --- |
| Thứ tự nguồn | Vị trí của phần tử trong `List` | Có, với nguồn ordered như `List.stream()`. |
| Thứ tự thực thi | Thread nào chạy `map`/`filter` trước | Không cố định với `parallelStream()`. |
| Thứ tự duyệt Map kết quả | `entrySet()`, `keySet()`, `forEach` | Phụ thuộc hợp đồng loại Map thực tế. |

Nếu báo cáo yêu cầu "mã sản phẩm từ nhỏ đến lớn", phải **chọn một loại Map có thứ tự sắp xếp** hoặc **sắp xếp các entry khi xuất báo cáo**. Việc Stream nguồn ordered không tự tạo một Map có thứ tự key.

## 7. LinkedHashMap: giữ thứ tự chèn khóa

`LinkedHashMap` có thứ tự lặp theo **thứ tự chèn** khi dùng cấu hình mặc định. Khi một khóa đã tồn tại và được cập nhật value, thao tác cập nhật đó **không đổi vị trí của khóa** trong chế độ insertion-order.

Để chọn loại Map trong `Collectors.toMap`, dùng overload **bốn đối số**:

```java
static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction,
        Supplier<M> mapFactory
)
```

Ví dụ:

```java
Map<String, Product> insertionOrder = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                LinkedHashMap::new
        ));

System.out.println(new ArrayList<>(insertionOrder.keySet()));
// [P02, P01, P03]
```

Vì đây là **Stream tuần tự có thứ tự nguồn**, các khóa xuất hiện lần đầu lần lượt là `P02`, `P01`, `P03`. Khi xuất hiện lại `P01` hoặc `P02`, merge function cập nhật value nhưng không đổi vị trí chèn key.

**Khi nào chọn?** Báo cáo yêu cầu giữ **thứ tự xuất hiện đầu tiên của các khóa** trong nguồn ổn định, ví dụ nhóm các lần truy cập theo mã phiên đầu tiên được ghi nhận.

### Nếu thứ tự nguồn không được xác định thì sao?

`LinkedHashMap` chỉ ghi nhận thứ tự chèn nó **được cung cấp**. Nếu đầu vào là một `HashSet` không có encounter order, việc dùng `LinkedHashMap::new` không tạo ra một thứ tự nghiệp vụ ổn định.

Muốn đầu ra xác định, phải **xác lập thứ tự đầu vào** (ví dụ sắp theo SKU, timestamp và ID) hoặc dùng Map có comparator. Đừng coi việc chọn `LinkedHashMap` là phép thay thế cho quy tắc sắp xếp.

## 8. TreeMap: đầu ra được sắp theo khóa

`TreeMap` duy trì khóa theo thứ tự **tự nhiên** hoặc một `Comparator` chỉ định. Khi cần in báo cáo theo SKU tăng dần, `TreeMap` là lựa chọn trực tiếp:

```java
Map<String, Product> sortedBySku = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                TreeMap::new
        ));

System.out.println(new ArrayList<>(sortedBySku.keySet()));
// [P01, P02, P03]
```

Khác với `LinkedHashMap`, `TreeMap` không dựa vào thứ tự chèn để xác định thứ tự lặp khóa. Khi dùng khóa `String`, thứ tự tự nhiên dựa trên `String.compareTo`, **không nhất thiết là thứ tự ngôn ngữ của người dùng**.

### Sắp xếp giảm dần

```java
Map<String, Product> descending = updates.stream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                () -> new TreeMap<String, Product>(
                        Comparator.reverseOrder()
                )
        ));

System.out.println(new ArrayList<>(descending.keySet()));
// [P03, P02, P01]
```

**Cẩn thận:** comparator của `TreeMap` không chỉ điều khiển thứ tự mà còn ảnh hưởng việc Map xem hai khóa có tương đương hay không. Nếu `compare(a, b) == 0` với hai khóa được nghiệp vụ coi là khác nhau, `TreeMap` có thể gộp chúng thành một entry.

Ví dụ:

```java
TreeMap<String, Integer> caseInsensitive =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

caseInsensitive.put("abc", 1);
caseInsensitive.put("ABC", 2);

System.out.println(caseInsensitive.size()); // 1
```

Nếu SKU phân biệt chữ hoa/chữ thường, comparator trên là **không phù hợp**. Ngược lại, nếu SKU không phân biệt chữ hoa/chữ thường, hãy chuẩn hóa theo quy tắc nghiệp vụ và dùng nhất quán từ lúc nhận dữ liệu.

## 9. sorted trước khi collect: khi nào hữu ích?

Ta cũng có thể tạo Map giữ thứ tự chèn sau khi sắp nguồn:

```java
Map<String, Product> sortedThenInserted = updates.stream()
        .sorted(Comparator.comparing(Product::sku))
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                LinkedHashMap::new
        ));

System.out.println(new ArrayList<>(sortedThenInserted.keySet()));
// [P01, P02, P03]
```

Ở đây, `sorted` đưa các record cùng SKU tới gần nhau theo thứ tự SKU; `LinkedHashMap` giữ thứ tự chèn những khóa lần đầu tiên. Kết quả có thứ tự theo SKU trong ví dụ **Stream tuần tự có thứ tự**.

So sánh hai chiến lược:

| Chiến lược | Ngữ nghĩa | Khi nên chọn |
| --- | --- | --- |
| `toMap(..., TreeMap::new)` | Map luôn duyệt key theo comparator | Khi bản thân Map phải có thứ tự khóa. |
| `sorted(...).collect(toMap(..., LinkedHashMap::new))` | Sắp nguồn rồi giữ thứ tự chèn key | Khi bước sắp xếp nguồn có ý nghĩa hoặc cần kiểm soát quy tắc phát sinh khóa. |
| Thu thập Map rồi sắp `entrySet` lúc xuất | Map lưu trữ không yêu cầu thứ tự, output được sắp | Khi chỉ một kênh báo cáo cần thứ tự cụ thể. |

Nếu chỉ cần sắp theo khóa, không phải lúc nào `sorted` toàn bộ nguồn cũng đáng dùng: `TreeMap` có thể đơn giản hơn. Nếu cần thứ tự theo **một giá trị của record** hoặc theo chính sách tùy chỉnh, `sorted` trước collect có thể là một phần hợp lý của thiết kế, nhưng vẫn phải xác định luật chọn value khi khóa trùng.

## 10. Xuất Map theo thứ tự ổn định mà không thay cấu trúc lưu trữ

Có những trường hợp dịch vụ cần Map để tra cứu nhanh, nhưng chỉ khi xuất báo cáo mới cần sắp theo khóa.

Không nhất thiết phải thu thập lại Map; có thể sắp trực tiếp các entry:

```java
Map<String, Integer> rawTotals = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum
        ));

List<String> reportLines = rawTotals.entrySet().stream()
        .sorted(Map.Entry.comparingByKey())
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(reportLines);
// [P01=6, P02=3]
```

`Map.Entry.comparingByKey()` chọn thứ tự tự nhiên của `String`, vì vậy **thứ tự dòng báo cáo được xác định** bất kể Map nội bộ dùng cấu trúc nào.

Nếu báo cáo cần sắp theo **giá trị giảm dần**, thêm tie-break theo khóa để hai dòng có cùng giá trị vẫn có thứ tự xác định:

```java
List<String> linesByQuantity = rawTotals.entrySet().stream()
        .sorted(
                Map.Entry.<String, Integer>comparingByValue(
                        Comparator.reverseOrder()
                ).thenComparing(Map.Entry.comparingByKey())
        )
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(linesByQuantity);
// [P01=6, P02=3]
```

**Điều này rất quan trọng khi kiểm thử:** `Map.equals` so sánh nội dung key/value, **không so sánh thứ tự lặp**. Nếu yêu cầu đầu ra là các dòng có thứ tự, kiểm tra chính `reportLines` hoặc danh sách key theo thứ tự, không chỉ kiểm tra Map bằng nhau.

Một serializer bên ngoài có thể có chính sách thứ tự riêng. Khi cần định dạng JSON/CSV ổn định, nên thể hiện thứ tự ở tầng xuất báo cáo và kiểm tra chính chuỗi hoặc cấu trúc được xuất, thay vì suy đoán rằng mọi serializer đều duyệt Map theo cùng quy tắc.

## 11. Thứ tự khi parallelStream: tách hai vấn đề

Với nguồn `List`, `parallelStream()` **không xóa encounter order**, nhưng không cam kết lịch thực thi của các lambda.

```java
List<String> orderedCodes = updates.parallelStream()
        .map(Product::sku)
        .toList();

System.out.println(orderedCodes);
// [P02, P01, P01, P03, P02]
```

Tuy vậy, với yêu cầu **chọn giá trị cho khóa trùng**, nên dựa vào phép kết hợp có tiêu chí rõ ràng, không dựa vào "thread nào ghi Map trước":

```java
Map<String, Product> deterministicValues = updates.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(policy),
                TreeMap::new
        ));

System.out.println(new ArrayList<>(deterministicValues.keySet()));
// [P01, P02, P03]
```

Ở đây, `TreeMap` sắp khóa; `maxBy(policy)` chọn bản ghi theo giá trị, **không theo thời điểm kết thúc của thread**. Muốn hoàn toàn xác định khi có hai record khác nhau nhưng comparator trả 0, phải thêm tie-break hoặc xác định xử lý lỗi trùng thứ hạng.

**Không nên làm:**

```java
Map<String, Product> shared = new HashMap<>();

// SAI: sửa một HashMap chung từ nhiều thread.
updates.parallelStream()
        .forEach(product -> shared.put(product.sku(), product));
```

`HashMap` không hỗ trợ những cập nhật đồng thời này, và quy tắc "giữ bản sau" ở đây phụ thuộc vào lịch thực thi. Ngay cả thay bằng `ConcurrentHashMap` vẫn chưa định nghĩa **bản nào phải thắng** nếu dùng `put` không kèm tiêu chí nghiệp vụ.

### Gợi ý khi cần "dòng đầu tiên" theo nguồn trong parallel

Không mã hóa "đầu tiên" bằng thời điểm thread chạy. Khi cần bảo đảm lựa chọn theo **vị trí nguồn**, có thể gắn chỉ số trước khi thu thập:

```java
record IndexedProduct(int index, Product product) {}

Map<String, IndexedProduct> firstByIndex =
        java.util.stream.IntStream.range(0, updates.size())
                .parallel()
                .mapToObj(i -> new IndexedProduct(i, updates.get(i)))
                .collect(Collectors.toMap(
                        entry -> entry.product().sku(),
                        java.util.function.Function.identity(),
                        java.util.function.BinaryOperator.minBy(
                                Comparator.comparingInt(IndexedProduct::index)
                        ),
                        TreeMap::new
                ));

System.out.println(firstByIndex.get("P01").product().name()); // Sổ cũ
System.out.println(firstByIndex.get("P01").index());          // 1
```

Mọi vị trí trong List có chỉ số duy nhất, do đó `minBy(index)` tạo quy tắc chọn rõ ràng. Cách này rất hữu ích khi có ràng buộc chọn **vị trí đầu tiên** mà pipeline có thể xử lý song song.

## 12. Null, khóa không hợp lệ và quy tắc bình đẳng

Trước khi thu thập vào Map, cần quyết định chính sách với dữ liệu thiếu:

- **Phần tử nguồn là `null`:** những method reference như `Product::sku` sẽ ném `NullPointerException`.
- **Giá trị do value mapper trả về `null`:** các collector `toMap` thông dụng không chấp nhận null value; không dùng `null` làm giá trị dự phòng.
- **Khóa `null`:** các loại Map có chính sách khác nhau; `TreeMap` với thứ tự tự nhiên, `ConcurrentHashMap` và `toUnmodifiableMap` không hỗ trợ null key. Không dựa vào sự tình cờ của một triển khai Map cụ thể.
- **Hai khóa bằng nhau:** với hash-based Map dựa vào `equals`/`hashCode`; với `TreeMap` dựa vào comparator, nên comparator cần phù hợp quy tắc danh tính.

Ví dụ lọc phần tử và khóa thiếu trước khi thu thập:

```java
List<Product> input = new ArrayList<>(updates);
input.add(null);
input.add(new Product(null, "Chưa có mã", 1, 0L));

Map<String, Product> valid = input.stream()
        .filter(java.util.Objects::nonNull)
        .filter(product -> product.sku() != null
                && !product.sku().isBlank())
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(byVersion),
                TreeMap::new
        ));
```

Nếu mã phân biệt chữ hoa và chữ thường, `"p01"` và `"P01"` là hai khóa khác nhau. Nếu nghiệp vụ xem chúng là một, chuẩn hóa trước:

```java
Map<String, Long> normalizedCount = updates.stream()
        .collect(Collectors.toMap(
                product -> product.sku().strip()
                        .toUpperCase(java.util.Locale.ROOT),
                product -> 1L,
                Long::sum,
                TreeMap::new
        ));
```

Trong dữ liệu ví dụ, `P01` và `P02` đều xuất hiện hai lần. Việc chuẩn hóa cần có **quy tắc nhất quán giữa ghi và tra cứu**. Không tự ý chuẩn hóa nếu hệ thống đang phân biệt chính xác chữ hoa/chữ thường.

## 13. Map unmodifiable không đồng nghĩa với Map có thứ tự

Trong Java hiện đại, có các phương thức tạo Map không cho phép sửa, như `Map.copyOf` và `Collectors.toUnmodifiableMap`. Chúng phù hợp để **không cho phép thêm/xóa entry**, nhưng **không tự bảo đảm thứ tự duyệt theo nguồn hoặc theo khóa**:

```java
Map<String, Integer> fixed = Map.copyOf(quantityBySku);
// fixed.put("P99", 1); // UnsupportedOperationException
```

`Map.copyOf` từ chối khóa hoặc giá trị `null`. Nó không phải công cụ cam kết thứ tự lặp của Map. Tương tự, `Collectors.toUnmodifiableMap` cũng cần merge function nếu có khóa trùng, và không định nghĩa thứ tự đầu ra.

Nếu phải **giữ thứ tự của một Map đã được sắp**, có thể tạo bản sao riêng rồi trả về view không cho sửa:

```java
Map<String, Product> orderedReadOnly =
        java.util.Collections.unmodifiableMap(
                new TreeMap<>(sortedBySku)
        );

System.out.println(new ArrayList<>(orderedReadOnly.keySet()));
// [P01, P02, P03]
```

`Collections.unmodifiableMap` tạo view không cho chỉnh sửa qua tham chiếu đó. Ở đây, `TreeMap` mới được tạo bên trong và không có tham chiếu mutable nào khác được công bố, nên **cấu trúc entry** của kết quả được bảo vệ khỏi code sử dụng view. Đây vẫn là **bản sao nông**: nếu value là đối tượng mutable, tình trạng bên trong value có thể thay đổi từ nơi khác.

Nếu code khác còn giữ tham chiếu tới Map gốc của một unmodifiable view, thay đổi Map gốc vẫn có thể hiện trong view. Vì vậy việc **tạo bản sao riêng** là điểm quan trọng.

## 14. So sánh với groupingBy: khi nào giữ tất cả bản ghi trùng?

`toMap` yêu cầu **mỗi khóa có một value**, dù value đó có thể là một List. Nếu nghiệp vụ muốn **giữ tất cả bản ghi** cùng khóa, `groupingBy` là cách trực tiếp:

```java
Map<String, List<Sale>> allSalesBySku = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::sku,
                TreeMap::new,
                Collectors.toList()
        ));

System.out.println(allSalesBySku.get("P01").size()); // 2
System.out.println(new ArrayList<>(allSalesBySku.keySet()));
// [P01, P02]
```

So sánh:

| Nhu cầu | Collector thích hợp |
| --- | --- |
| Khóa phải duy nhất, trùng là lỗi | `toMap(keyMapper, valueMapper)` |
| Mỗi khóa giữ một bản được chọn | `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` |
| Mỗi khóa giữ tổng hoặc số đếm | `toMap(..., Long::sum, ...)` hoặc `groupingBy(..., summingLong/counting)` |
| Mỗi khóa giữ **toàn bộ danh sách bản ghi** | `groupingBy(keyMapper, mapFactory, toList())` |
| Phân nhóm có nhiều tầng | `groupingBy(..., groupingBy(...))` hoặc khóa ghép |

`groupingBy` mặc định không cam kết thứ tự của Map; overload có `mapFactory` giúp ta yêu cầu `TreeMap` hoặc `LinkedHashMap` khi phù hợp.

Với các downstream collector như `mapping`, `counting` hoặc `summarizingLong`, có thể tổng hợp trong từng nhóm mà không cần viết merge function thủ công. Khi chọn collector, ưu tiên ý nghĩa nghiệp vụ rõ ràng.

## 15. Ví dụ Java 17+ hoàn chỉnh: danh mục sản phẩm cập nhật nhiều lần

Bài toán: hệ thống nhận các bản cập nhật sản phẩm theo SKU. Một SKU có thể xuất hiện nhiều lần, và cần tạo **bản ghi đại diện có revision lớn nhất**. Nếu revision bằng nhau, so sánh thời điểm cập nhật; nếu vẫn bằng, dùng ID bản ghi để có kết quả xác định. Cuối cùng, báo cáo phải duyệt SKU **tăng dần**.

Đoạn mã dưới đây là chương trình có thể chạy độc lập (Java 17+):

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class DeterministicMapDemo {
    record CatalogRow(
            String rowId,
            String sku,
            String label,
            int revision,
            long updatedAt,
            long priceCents
    ) {}

    private static final Comparator<CatalogRow> PREFERENCE =
            Comparator.comparingInt(CatalogRow::revision)
                    .thenComparingLong(CatalogRow::updatedAt)
                    .thenComparing(CatalogRow::rowId)
                    .thenComparing(CatalogRow::label)
                    .thenComparingLong(CatalogRow::priceCents);

    static Map<String, CatalogRow> createCatalog(
            List<CatalogRow> updates, boolean parallel) {
        var stream = parallel
                ? updates.parallelStream()
                : updates.stream();

        return stream.collect(Collectors.toMap(
                CatalogRow::sku,
                Function.identity(),
                BinaryOperator.maxBy(PREFERENCE),
                TreeMap::new
        ));
    }

    public static void main(String[] args) {
        List<CatalogRow> updates = List.of(
                new CatalogRow("R01", "P02", "Tai nghe", 1, 100L, 200_000L),
                new CatalogRow("R02", "P01", "Sổ cũ", 1, 110L, 30_000L),
                new CatalogRow("R03", "P01", "Sổ mới", 2, 120L, 35_000L),
                new CatalogRow("R04", "P03", "Bút", 1, 130L, 8_000L),
                new CatalogRow("R05", "P02", "Tai nghe Pro", 3, 140L, 250_000L),
                new CatalogRow("R06", "P02", "Tai nghe Max", 3, 150L, 260_000L)
        );

        Map<String, CatalogRow> sequential = createCatalog(updates, false);
        Map<String, CatalogRow> parallel = createCatalog(updates, true);

        // Map.equals so sánh nội dung, không so thứ tự lặp.
        if (!sequential.equals(parallel)) {
            throw new AssertionError("Sequential/parallel khác nội dung");
        }

        List<String> sortedKeys = new ArrayList<>(sequential.keySet());
        if (!sortedKeys.equals(List.of("P01", "P02", "P03"))) {
            throw new AssertionError("Sai thứ tự khóa");
        }

        if (!sequential.get("P01").rowId().equals("R03")) {
            throw new AssertionError("P01 không chọn revision lớn nhất");
        }
        if (!sequential.get("P02").rowId().equals("R06")) {
            throw new AssertionError("P02 không chọn updatedAt mới nhất");
        }

        sequential.forEach((sku, row) ->
                System.out.printf(
                        "%s | %s | revision=%d | price=%d%n",
                        sku, row.label(), row.revision(), row.priceCents()
                )
        );

        // P01 | Sổ mới       | revision=2 | price=35000
        // P02 | Tai nghe Max | revision=3 | price=260000
        // P03 | Bút          | revision=1 | price=8000
        System.out.println("PASS");
    }
}
```

**Vì sao chương trình đúng theo yêu cầu?**

1. `CatalogRow::sku` tạo khóa nhóm; mỗi SKU có đúng một value cuối.
2. `BinaryOperator.maxBy(PREFERENCE)` chọn bản có revision cao hơn; khi bằng revision, chọn timestamp lớn hơn và tiếp tục dùng các tie-break ổn định. Với cùng SKU, nếu toàn bộ tiêu chí so sánh bằng nhau thì hai record có cùng nội dung các trường còn lại.
3. `TreeMap::new` khiến key được duyệt theo thứ tự tự nhiên của `String`; không phụ thuộc thứ tự xử lý các nhánh song song.
4. Các giá trị của `CatalogRow` là các thành phần bất biến trong record; merge function không sửa nguồn hoặc biến trạng thái dùng chung.
5. Chương trình xác nhận cả **nội dung Map** lẫn **thứ tự key** bằng các điều kiện riêng; không dựa vào thứ tự chuỗi `HashMap.toString()`.
6. Mỗi lần gọi `createCatalog` tạo một Stream mới từ cùng danh sách nguồn ổn định.

**Lưu ý nghiệp vụ:** trong hệ thống thật, timestamp có thể trùng nhau, giá tiền có thể thay đổi độc lập với version, và ID có thể không phải quy tắc ưu tiên phù hợp. Vì vậy PREFERENCE là **quy tắc được công bố rõ trong bài tập**, không phải cách mặc định để giải quyết mọi xung đột dữ liệu.

## 16. Bài tập từ nền tảng đến trung cấp

### Bài 1 — Phát hiện khóa trùng

Cho:

```java
record Student(String code, String name) {}
List<Student> students = List.of(
        new Student("S01", "An"),
        new Student("S02", "Bình"),
        new Student("S01", "Chi")
);
```

**Yêu cầu:** thử thu thập bằng `toMap(Student::code, Function.identity())`; dự đoán ngoại lệ. Sau đó sửa để giữ bản ghi xuất hiện đầu tiên khi duyệt **tuần tự theo List**.

**Lời giải:**

```java
Map<String, Student> firstStudent = students.stream()
        .collect(Collectors.toMap(
                Student::code,
                java.util.function.Function.identity(),
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(firstStudent.get("S01").name()); // An
System.out.println(new ArrayList<>(firstStudent.keySet()));
// [S01, S02]
```

### Bài 2 — Cộng số lượng và xuất theo khóa

Cho:

```java
record Item(String sku, long quantity) {}
List<Item> items = List.of(
        new Item("B", 3),
        new Item("A", 4),
        new Item("B", 5),
        new Item("C", 2)
);
```

**Yêu cầu:** tạo `Map<String, Long>`, gộp số lượng khi trùng SKU, rồi in theo SKU tăng dần.

**Lời giải:**

```java
Map<String, Long> totals = items.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Long::sum,
                TreeMap::new
        ));

totals.forEach((sku, quantity) ->
        System.out.println(sku + "=" + quantity));

// A=4
// B=8
// C=2
```

### Bài 3 — Chọn bản cập nhật mới nhất có tie-break

Cho:

```java
record Update(String key, long timestamp, String updateId) {}
List<Update> changes = List.of(
        new Update("X", 100L, "U02"),
        new Update("Y", 150L, "U01"),
        new Update("X", 100L, "U03"),
        new Update("X", 200L, "U04")
);
```

**Yêu cầu:** giữ `Update` có timestamp cao nhất theo mỗi key. Nếu timestamp bằng nhau, dùng `updateId` tăng dần để xác định bản thắng. Xuất theo thứ tự key tăng dần.

**Lời giải:**

```java
Comparator<Update> updatePolicy = Comparator
        .comparingLong(Update::timestamp)
        .thenComparing(Update::updateId);

Map<String, Update> chosen = changes.parallelStream()
        .collect(Collectors.toMap(
                Update::key,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(updatePolicy),
                TreeMap::new
        ));

System.out.println(chosen.get("X").updateId()); // U04
System.out.println(new ArrayList<>(chosen.keySet())); // [X, Y]
```

Thử xóa dòng `U04`: lúc này `U03` thắng `U02` vì cùng timestamp 100 nhưng ID lớn hơn. Đó là tie-break tường minh, không phụ thuộc lịch thread.

### Bài 4 — Giữ tất cả phần tử theo nhóm

**Yêu cầu:** Với `items` ở Bài 2, tạo `Map<String, List<Item>>` được sắp theo SKU và **không bỏ bản ghi trùng**.

**Lời giải:**

```java
Map<String, List<Item>> groupedItems = items.stream()
        .collect(Collectors.groupingBy(
                Item::sku,
                TreeMap::new,
                Collectors.toList()
        ));

System.out.println(groupedItems.get("B").size()); // 2
```

Chú ý rằng `groupingBy` ở đây giải bài toán **giữ toàn bộ bản ghi**, trong khi `toMap` với `Long::sum` giải bài toán **tính tổng**. Chọn theo đầu ra cần thiết, không chỉ theo cú pháp ngắn nhất.

### Bài 5 — Phân biệt thứ tự Map và thứ tự dòng báo cáo

**Yêu cầu:** thu thập bản đồ tổng số lượng bằng `toMap` mặc định (không chỉ định mapFactory), sau đó tạo `List<String>` các dòng `"SKU=quantity"` sắp theo **quantity giảm dần**, nếu bằng thì SKU tăng dần.

**Lời giải:**

```java
Map<String, Long> totalsWithoutOrder = items.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Long::sum
        ));

List<String> lines = totalsWithoutOrder.entrySet().stream()
        .sorted(
                Map.Entry.<String, Long>comparingByValue(
                        Comparator.reverseOrder()
                ).thenComparing(Map.Entry.comparingByKey())
        )
        .map(entry -> entry.getKey() + "=" + entry.getValue())
        .toList();

System.out.println(lines); // [B=8, A=4, C=2]
```

Kết quả được xác định bởi comparator trên **entry**, không bởi kiểu Map đầu tiên.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `IllegalStateException` khi `toMap` | Hai phần tử sinh cùng khóa nhưng không có merge function | Quyết định chính sách trùng rồi dùng overload có merge, hoặc coi trùng là lỗi hợp lệ. |
| Giá trị bị thay thế ngoài mong đợi | Dùng `(old, next) -> next` mà không xét phiên bản/thời gian | Dùng comparator hoặc reducer theo tiêu chí nghiệp vụ. |
| Thứ tự key khác khi chạy lại | Dựa vào `toMap` mặc định hoặc `HashMap` | Chọn `LinkedHashMap`, `TreeMap` hoặc sắp entry khi xuất. |
| `LinkedHashMap` vẫn cho thứ tự không mong muốn | Đầu vào không có encounter order hoặc không được sắp theo nhu cầu | Xác định thứ tự nguồn hoặc sắp trước khi thu thập. |
| `TreeMap` làm mất một số khóa | Comparator trả 0 cho những khóa nghiệp vụ khác nhau | Dùng comparator phù hợp định nghĩa khóa. |
| `Map.equals` PASS nhưng báo cáo sai thứ tự | Map equality không xét thứ tự lặp | Kiểm tra `new ArrayList<>(map.keySet())` hoặc danh sách dòng xuất. |
| `NullPointerException` trong collector | Mapper cho giá trị null, khóa không hợp lệ với loại Map, hoặc nguồn có null | Validate/lọc/chuẩn hóa trước khi collect. |
| `ConcurrentModificationException` hoặc dữ liệu mất | `parallelStream().forEach(sharedMap::put)` sửa HashMap chia sẻ | Dùng `Collectors.toMap`/`groupingBy`, không sửa Map dùng chung. |
| Chọn bản "mới nhất" thay đổi giữa các lần chạy | Merge dựa vào thứ tự xử lý hoặc tie-break chưa đủ | Dùng comparator ổn định với tie-break xác định. |
| `Map.copyOf` làm thay đổi thứ tự lặp | Map không sửa được không đồng nghĩa có order | Dùng snapshot `TreeMap`/`LinkedHashMap` với unmodifiable view nếu cần. |
| Bảng báo cáo yêu cầu nhiều bản ghi nhưng chỉ còn một | Dùng `toMap` theo khóa thay vì nhóm thành danh sách | Dùng `groupingBy` với downstream `toList`. |
| Tổng số lớn bị tràn | Dùng `Integer::sum`/`Long::sum` vượt phạm vi biểu diễn | Chọn kiểu số phù hợp và kiểm soát overflow. |

## 18. Checklist bàn giao bài làm

1. **Khóa:** key mapper tạo khóa theo đúng định nghĩa nghiệp vụ chưa?
2. **Trùng khóa:** chính sách ném lỗi, cộng dồn hay chọn đại diện đã được nêu tường minh chưa?
3. **Merge:** có tính kết hợp, không sửa trạng thái dùng chung và không phụ thuộc lịch thực thi thread không?
4. **Tie-break:** nếu hai bản có cùng điểm ưu tiên, quy tắc chọn đã đủ xác định chưa?
5. **Nguồn:** là `List` ordered hay `Set` không có thứ tự? Có cần sắp để có kết quả ổn định?
6. **Map:** có cần giữ thứ tự chèn bằng `LinkedHashMap` hay thứ tự khóa bằng `TreeMap`?
7. **Đầu ra:** cần thứ tự của Map hay chỉ cần các dòng báo cáo đã sắp?
8. **Kiểm thử:** đã assert cả nội dung key/value và thứ tự khi thứ tự là yêu cầu chưa?
9. **Null:** có chính sách rõ cho phần tử, khóa và giá trị null chưa?
10. **Song song:** code có tránh cập nhật một `HashMap` chia sẻ trong `forEach` không?
11. **Nguồn rỗng:** kết quả Map rỗng có được xử lý đúng không?
12. **Độ phức tạp:** đã cân nhắc chi phí sort, Map, merge và bộ nhớ nếu dữ liệu tăng lớn chưa?

## Ghi nhớ

Khi thiết kế `Map` từ Stream, **định nghĩa khóa trùng** và **định nghĩa thứ tự đầu ra** là hai quyết định riêng. `Collectors.toMap(keyMapper, valueMapper)` ném lỗi nếu nhiều phần tử cùng khóa. Dùng merge function để cộng, giữ một bản hoặc chọn đại diện theo comparator; đừng chọn bản theo thứ tự chạy tình cờ của các thread.

`LinkedHashMap` giữ **thứ tự chèn**, phù hợp khi thứ tự nguồn có nghĩa và ổn định. `TreeMap` giữ **thứ tự sắp theo khóa**, phù hợp khi báo cáo cần duyệt key có thứ tự. Nếu chỉ tầng trình bày cần sắp, có thể lấy `entrySet().stream().sorted(...)` mà không đổi Map dùng để tra cứu. Với xử lý song song, giữ lambda stateless và non-interfering, định nghĩa tie-break đầy đủ, và kiểm tra kết quả **theo hợp đồng nghiệp vụ**, không theo cách Map tình cờ được in ra.
