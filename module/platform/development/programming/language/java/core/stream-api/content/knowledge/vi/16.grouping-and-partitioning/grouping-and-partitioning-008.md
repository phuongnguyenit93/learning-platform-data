# Phân biệt groupingBy, partitioningBy và toMap

> **Chương:** Phân nhóm và phân hoạch  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Lựa chọn đúng giữa `Collectors.groupingBy`, `Collectors.partitioningBy` và `Collectors.toMap` dựa trên cấu trúc dữ liệu đầu ra, số giá trị trên một khóa, yêu cầu xử lý trùng khóa và cách tổng hợp kết quả.

Khi viết pipeline **Java Stream API**, các phép `filter`, `map` và `sorted` mô tả cách dữ liệu đi qua luồng; còn `collect` thường được dùng để đưa kết quả vào một cấu trúc như `List`, `Set` hay `Map`. Trong nhóm các collector trả về Map, ba API dễ bị nhầm nhất là **`groupingBy`**, **`partitioningBy`** và **`toMap`**.

Cả ba đều có thể tạo một `Map`, nhưng **ý nghĩa hoàn toàn khác nhau**:

- `groupingBy` chia các phần tử theo **một khóa phân loại**, mặc định giữ **danh sách nhiều phần tử** cho mỗi khóa.
- `partitioningBy` chia phần tử theo **một điều kiện boolean**, luôn có **hai khóa `true` và `false`**.
- `toMap` ánh xạ từng phần tử thành **một cặp khóa–giá trị**; khi khóa trùng, phải quyết định **từ chối, chọn một giá trị hay gộp các giá trị**.

Bài này đi từ cách đọc chữ ký API đến ví dụ nghiệp vụ, downstream collector, dữ liệu rỗng, thứ tự, `null`, xử lý song song và hiệu năng. Đó cũng là nền tảng để tiếp tục học grouping nhiều tầng, collector tùy chỉnh, `Spliterator` và Stream Gatherers trong module **JAVA_STREAM_API**.

Các ví dụ sử dụng Java 17+ để hỗ trợ `record`, `List.of` và `Stream.toList()`. Ba collector chính đã có từ Java 8; `Collectors.filtering` được bổ sung từ Java 9.

## 1. Nhìn nhanh: cùng là Map nhưng khác hợp đồng

Giả sử có một tập giao dịch bán hàng với mã, vùng, số tiền và trạng thái thanh toán. Ta có ba yêu cầu:

1. **Theo vùng:** vùng “Bắc” chứa những giao dịch nào?
2. **Theo trạng thái:** các giao dịch đã thanh toán và chưa thanh toán là những giao dịch nào?
3. **Theo mã giao dịch:** lấy giao dịch có mã “S03” nhanh bằng cách nào?

Ba yêu cầu ấy dẫn đến ba cách thu thập:

```java
// Map<String, List<Sale>>: một vùng có thể chứa nhiều giao dịch.
Map<String, List<Sale>> byRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));

// Map<Boolean, List<Sale>>: chỉ có nhóm true và false.
Map<Boolean, List<Sale>> byPaid = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

// Map<String, Sale>: một mã giao dịch ứng với một Sale.
Map<String, Sale> byId = sales.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));
```

Các biến và kiểu `Sale` được khai báo đầy đủ trong ví dụ ở mục 2. Cần import `java.util.List`, `java.util.Map`, `java.util.function.Function` và `java.util.stream.Collectors`.

| Tiêu chí | `groupingBy` | `partitioningBy` | `toMap` |
| --- | --- | --- | --- |
| Câu hỏi chính | “Phần tử thuộc nhóm nào?” | “Điều kiện đúng hay sai?” | “Phần tử tạo ra khóa và giá trị nào?” |
| Hàm đầu vào | `Function<T,K>` | `Predicate<T>` | `keyMapper` và `valueMapper` |
| Kiểu khóa điển hình | `K` bất kỳ, khác `null` | `Boolean` | `K` tùy ý theo Map được tạo |
| Kiểu kết quả mặc định | `Map<K,List<T>>` | `Map<Boolean,List<T>>` | `Map<K,U>` |
| Nhiều phần tử cùng khóa | Được gom vào một nhóm | Được gom vào một trong hai nhánh | Lỗi ở overload không có merge function |
| Có downstream collector? | Có | Có | Không theo cú pháp downstream; có merge function |
| Nguồn rỗng | Map rỗng | Vẫn có `true` và `false` | Map rỗng |
| Số khóa | 0 đến nhiều khóa đã phát sinh | Luôn đúng 2 khóa boolean | 0 đến nhiều khóa sau ánh xạ |

**Quy tắc nhận diện nhanh:** nếu muốn giữ **tập phần tử cho mỗi khóa**, dùng `groupingBy`; nếu chỉ có **hai nhánh theo điều kiện**, dùng `partitioningBy`; nếu cần **một giá trị cho mỗi khóa**, xem `toMap` và xác định chính sách khóa trùng.

## 2. Dữ liệu mẫu thống nhất cho cả bài

Ta dùng record `Sale`:

```java
record Sale(String id, String region, long amount, boolean paid) {}
```

Danh sách đầu vào:

```java
List<Sale> sales = List.of(
    new Sale("S01", "Bắc", 120_000L, true),
    new Sale("S02", "Nam",  60_000L, false),
    new Sale("S03", "Bắc",  80_000L, true),
    new Sale("S04", "Nam", 140_000L, true),
    new Sale("S05", "Bắc",  50_000L, false),
    new Sale("S06", "Tây", 200_000L, true)
);
```

Bảng dữ liệu:

| Mã | Vùng | Số tiền | Đã thanh toán |
| --- | --- | ---: | --- |
| S01 | Bắc | 120.000 | true |
| S02 | Nam | 60.000 | false |
| S03 | Bắc | 80.000 | true |
| S04 | Nam | 140.000 | true |
| S05 | Bắc | 50.000 | false |
| S06 | Tây | 200.000 | true |

Từ bảng này, các kết quả mong đợi là:

- Theo vùng: **Bắc có 3**, **Nam có 2**, **Tây có 1** giao dịch.
- Theo thanh toán: **true có 4**, **false có 2** giao dịch.
- Doanh thu gộp theo vùng **chưa lọc trạng thái**: Bắc **250.000**, Nam **200.000**, Tây **200.000**.
- Doanh thu **chỉ các giao dịch đã thanh toán** theo vùng: Bắc **200.000**, Nam **140.000**, Tây **200.000**.

Việc phân biệt “tổng tiền mọi giao dịch” với “doanh thu đã thanh toán” là một phần của yêu cầu nghiệp vụ, không phải tính năng tự quyết định của collector.

## 3. groupingBy: nhóm nhiều phần tử theo một khóa

Overload đơn giản nhất:

```java
Map<String, List<Sale>> salesByRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));
```

`Sale::region` là *classifier* – một hàm nhận `Sale` và trả khóa `String`. Với mỗi khóa, collector tạo nhóm những phần tử có cùng giá trị phân loại:

```text
Stream<Sale>
      │
      ▼
groupingBy(Sale::region)
      │
      ├── "Bắc" ──► [S01, S03, S05]
      ├── "Nam" ──► [S02, S04]
      └── "Tây" ──► [S06]
```

Có thể truy cập nhóm:

```java
List<Sale> northern = salesByRegion.get("Bắc");

System.out.println(northern.size()); // 3
```

### 3.1. groupingBy không giới hạn số nhóm

Hàm phân loại có thể trả chuỗi, số, enum, record hoặc khóa nghiệp vụ khác, miễn đáp ứng yêu cầu của collector và Map. Số nhóm phụ thuộc **những khóa thực sự xuất hiện trong nguồn**, không phụ thuộc số giá trị có thể có về mặt kiểu.

Ví dụ phân nhóm theo năm:

```java
record Invoice(String id, int year, long amount) {}

List<Invoice> invoices = List.of(
    new Invoice("I01", 2025, 100),
    new Invoice("I02", 2026, 200),
    new Invoice("I03", 2025, 300)
);

Map<Integer, List<Invoice>> byYear = invoices.stream()
    .collect(Collectors.groupingBy(Invoice::year));

// byYear có 2 khóa: 2025 và 2026.
```

Nếu không có hóa đơn năm 2024, Map không tự tạo nhóm 2024 với danh sách rỗng.

### 3.2. groupingBy không bắt buộc trả danh sách

Mặc định, `groupingBy(classifier)` có thể hiểu như gom bằng downstream `toList()`. Nhưng overload nhận **downstream collector** cho phép kết quả của mỗi nhóm là số đếm, tổng tiền, tập mã hoặc báo cáo riêng:

```java
Map<String, Long> counts = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));

// Bắc -> 3; Nam -> 2; Tây -> 1.
```

`Collectors.counting()` xử lý phần tử trong từng nhóm rồi tạo `Long`. Vì vậy kết quả trở thành `Map<String, Long>`, không phải `Map<String, List<Sale>>`.

### 3.3. groupingBy và khóa phân loại null

`Collectors.groupingBy` không chấp nhận kết quả classifier là `null`. Nếu `region` là `null`, lời gọi:

```java
// Có thể gây NullPointerException khi một Sale có region == null.
// sales.stream().collect(Collectors.groupingBy(Sale::region));
```

sẽ thất bại. Không nên cho rằng vì `HashMap` có thể chứa khóa `null`, `groupingBy` cũng tự chấp nhận.

Cần xác định ý nghĩa nghiệp vụ của dữ liệu thiếu vùng. Nếu muốn có nhóm “Chưa xác định”:

```java
Map<String, List<Sale>> safeGroups = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.region() == null
            ? "Chưa xác định"
            : sale.region()
    ));
```

Nếu chuỗi “Chưa xác định” có thể là giá trị hợp lệ thực sự, nên dùng một kiểu khóa phân biệt rõ hai trường hợp, chẳng hạn một record hoặc `Optional<String>` phù hợp:

```java
Map<Optional<String>, List<Sale>> byOptionalRegion = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> Optional.ofNullable(sale.region())
    ));
```

Ví dụ cần import `java.util.Optional`. Khóa `Optional.empty()` đại diện cho vùng thiếu, còn khóa `Optional.of("Bắc")` đại diện cho vùng có giá trị.

## 4. partitioningBy: một điều kiện, hai nhóm boolean

`Collectors.partitioningBy` không nhận classifier tùy ý mà nhận **`Predicate<T>`**, tức điều kiện trả `boolean`:

```java
Map<Boolean, List<Sale>> paidPartition = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));
```

Kết quả:

```text
Stream<Sale>
     │
     ▼
partitioningBy(Sale::paid)
     │
     ├── true  ──► [S01, S03, S04, S06]
     └── false ──► [S02, S05]
```

Ví dụ lấy hai nhánh:

```java
List<Sale> paid = paidPartition.get(true);
List<Sale> unpaid = paidPartition.get(false);

System.out.println(paid.size());   // 4
System.out.println(unpaid.size()); // 2
```

### 4.1. partitioningBy luôn có hai khóa, kể cả khi một nhóm trống

Đây là khác biệt quan trọng nhất so với `groupingBy`:

```java
Map<Boolean, List<Integer>> emptyPartition =
    Stream.<Integer>empty()
        .collect(Collectors.partitioningBy(n -> n > 0));

System.out.println(emptyPartition.containsKey(true));  // true
System.out.println(emptyPartition.containsKey(false)); // true
System.out.println(emptyPartition.get(true));           // []
System.out.println(emptyPartition.get(false));          // []
```

`partitioningBy` bảo đảm một kết quả ứng với `true` và một kết quả ứng với `false`. Với downstream collector, **cả hai nhánh vẫn có kết quả downstream**, kể cả khi không có phần tử trong nhánh đó.

So với `groupingBy` trên nguồn rỗng:

```java
Map<String, List<String>> emptyGroup =
    Stream.<String>empty()
        .collect(Collectors.groupingBy(Function.identity()));

System.out.println(emptyGroup.isEmpty()); // true
```

`groupingBy` không tạo khóa “giả định” cho những nhóm không xuất hiện; `partitioningBy` tạo sẵn hai nhánh boolean.

### 4.2. Khi nào dùng partitioningBy thay vì groupingBy?

Có thể viết:

```java
Map<Boolean, List<Sale>> groupedBoolean = sales.stream()
    .collect(Collectors.groupingBy(Sale::paid));
```

Với tập `sales` hiện tại có cả `true` và `false`, kết quả về nhóm phần tử giống nhau. Nhưng nếu tất cả giao dịch đều đã thanh toán, `groupingBy(Sale::paid)` chỉ chứa khóa `true`, trong khi `partitioningBy(Sale::paid)` vẫn có khóa `false` với danh sách rỗng.

Vì vậy, **khi miền kết quả phải bao gồm đủ hai trạng thái**, dùng `partitioningBy` để diễn đạt hợp đồng đó ngay trong API.

### 4.3. Hai nhánh không bắt buộc là đúng/sai về nghiệp vụ

Predicate có thể kiểm tra bất kỳ điều kiện nào:

```java
Map<Boolean, List<Sale>> largeOrders = sales.stream()
    .collect(Collectors.partitioningBy(
        sale -> sale.amount() >= 100_000
    ));
```

`true` nghĩa là “đơn đạt ngưỡng”; `false` nghĩa là “đơn dưới ngưỡng”. Khi trả Map cho thành phần khác, nên đặt tên biến hoặc chuyển sang một kiểu kết quả có tên trường rõ ràng để tránh người đọc phải đoán ý nghĩa của khóa boolean.

## 5. toMap: ánh xạ một khóa sang một giá trị

`Collectors.toMap` nhận **hai hàm** quan trọng:

```java
Collectors.toMap(
    keyMapper,
    valueMapper
);
```

Trong ví dụ bán hàng, mỗi giao dịch có mã `id` duy nhất:

```java
Map<String, Sale> byId = sales.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));

Sale found = byId.get("S03");
System.out.println(found.amount()); // 80000
```

Với `toMap`, mỗi khóa ứng với **một giá trị**. Kết quả có thể là đối tượng đầy đủ, thuộc tính số, chuỗi hoặc record thống kê.

### 5.1. Khóa trùng sẽ ra sao?

Nếu thay `Sale::id` bằng `Sale::region` thì nhiều giao dịch cùng khóa “Bắc”:

```java
// Ném IllegalStateException vì region không duy nhất:
// Map<String, Sale> byRegion = sales.stream()
//     .collect(Collectors.toMap(
//         Sale::region,
//         Function.identity()
//     ));
```

Overload hai tham số của `toMap` **không mặc định giữ đầu, giữ cuối hay gom thành danh sách**. Nó báo lỗi khi hai phần tử tạo cùng khóa.

Đây là hành vi phù hợp nếu khóa được kỳ vọng duy nhất, vì dữ liệu trùng có thể là lỗi cần phát hiện thay vì bị âm thầm ghi đè.

### 5.2. Cho phép khóa trùng bằng mergeFunction

Overload ba tham số bổ sung **`BinaryOperator<U> mergeFunction`**:

```java
Map<String, Long> amountByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Sale::amount,
        Long::sum
    ));

// Bắc -> 250000, Nam -> 200000, Tây -> 200000.
```

Tại mỗi xung đột khóa, `Long::sum` gộp giá trị tiền. Kết quả là **một số `Long` cho mỗi vùng**, không phải danh sách các `Sale`.

Hai chính sách khác:

```java
// Giữ phần tử xuất hiện đầu theo thứ tự gặp phần tử có bảo đảm.
Map<String, Sale> firstByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Function.identity(),
        (first, next) -> first
    ));

// Giữ phần tử xuất hiện cuối theo thứ tự gặp phần tử có bảo đảm.
Map<String, Sale> lastByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Function.identity(),
        (first, next) -> next
    ));
```

Với `sales` là một `List` có thứ tự, vùng Bắc giữ `S01` ở chính sách đầu và `S05` ở chính sách cuối. Nhưng **gặp sau không mặc định là cập nhật mới nhất theo thời gian nghiệp vụ**; nếu cần chọn theo timestamp, hãy so sánh timestamp.

### 5.3. Khi nào dùng toMap thay groupingBy?

Câu hỏi quan trọng là **mỗi khóa cần giữ bao nhiêu thông tin**:

| Yêu cầu | Hướng chọn |
| --- | --- |
| Giữ toàn bộ giao dịch của vùng | `groupingBy(Sale::region)` |
| Tính tổng tiền của vùng | `groupingBy(Sale::region, summingLong(...))` **hoặc** `toMap(..., Long::sum)` |
| Tra cứu giao dịch theo mã duy nhất | `toMap(Sale::id, identity())` |
| Giữ một đại diện mỗi vùng theo quy tắc rõ ràng | `toMap(..., mergeFunction)` |
| Cần nhiều thống kê có cấu trúc cho từng vùng | `groupingBy` với downstream collector thường dễ mở rộng |

Không nên viết `groupingBy` chỉ để sau đó gọi `list.get(0)` nếu nhu cầu thực là chọn một đại diện theo quy tắc rõ ràng; đồng thời không nên dùng `toMap` làm mất lịch sử nếu nghiệp vụ cần toàn bộ các phần tử.

## 6. Chữ ký API và cách đọc các kiểu trả về

Viết dưới dạng tổng quát, rút gọn wildcard để tập trung vào ý nghĩa:

```java
// Một khóa -> danh sách phần tử:
groupingBy(Function<T, K> classifier)
    // Collector<T, ?, Map<K, List<T>>>

// Một khóa -> kết quả từ downstream:
groupingBy(Function<T, K> classifier,
           Collector<T, A, D> downstream)
    // Collector<T, ?, Map<K, D>>

// Hai nhánh boolean -> danh sách:
partitioningBy(Predicate<T> predicate)
    // Collector<T, ?, Map<Boolean, List<T>>>

// Hai nhánh boolean -> kết quả từ downstream:
partitioningBy(Predicate<T> predicate,
               Collector<T, A, D> downstream)
    // Collector<T, ?, Map<Boolean, D>>

// Một khóa -> một giá trị U; trùng khóa sẽ bị từ chối:
toMap(Function<T, K> keyMapper,
      Function<T, U> valueMapper)
    // Collector<T, ?, Map<K, U>>

// Có quy tắc gộp U khi trùng khóa:
toMap(Function<T, K> keyMapper,
      Function<T, U> valueMapper,
      BinaryOperator<U> mergeFunction)
    // Collector<T, ?, Map<K, U>>
```

Các dòng trên là **sơ đồ chữ ký**, không phải mã Java độc lập có thể biên dịch. Trong Java thực, generic có wildcard như `? super T` và `? extends K` để hỗ trợ các kiểu tương thích.

Chú ý sự khác nhau:

- **Classifier** của `groupingBy` tạo khóa nhóm; từng phần tử sau đó đi vào downstream collector.
- **Predicate** của `partitioningBy` quyết định đúng một nhánh `true` hay `false`.
- **Key mapper + value mapper** của `toMap` tạo trực tiếp cặp `K,V`; khi trùng khóa, `mergeFunction` quyết định giá trị `V` kết hợp.

Bản thân `collect` là phép kết thúc của Stream; ba collector chỉ khác **cách thiết kế việc tích lũy**.

## 7. Downstream collector: điểm mạnh của groupingBy và partitioningBy

Downstream collector cho phép sau khi phân nhóm/phân hoạch, ta tính ngay một kết quả cho mỗi nhóm thay vì bắt buộc giữ toàn bộ danh sách.

### 7.1. Đếm phần tử theo vùng

```java
Map<String, Long> countByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Kết quả: Bắc = 3, Nam = 2, Tây = 1.

### 7.2. Tổng số tiền theo vùng

```java
Map<String, Long> totalByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amount)
    ));

// Bắc=250000, Nam=200000, Tây=200000.
```

Kết quả này tương đương về giá trị với `toMap(Sale::region, Sale::amount, Long::sum)` trong bộ dữ liệu hiện tại.

Khi cần thống kê nhiều chiều, `groupingBy` thường dễ mở rộng bằng các downstream khác như `summarizingLong`, `mapping`, `maxBy`, `filtering`, `collectingAndThen` hoặc một collector tùy chỉnh.

### 7.3. Đếm số giao dịch theo hai nhánh

```java
Map<Boolean, Long> countByPayment = sales.stream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));

System.out.println(countByPayment.get(true));  // 4
System.out.println(countByPayment.get(false)); // 2
```

Với nguồn rỗng, kết quả vẫn có `true -> 0L` và `false -> 0L`. Giá trị 0 đến từ hành vi của downstream `counting()` trên nhánh rỗng.

### 7.4. Thu danh sách mã thay vì đối tượng

`Collectors.mapping` biến phần tử trước khi downstream thu thập:

```java
Map<String, List<String>> idsByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.mapping(
            Sale::id,
            Collectors.toList()
        )
    ));

// "Bắc" -> ["S01", "S03", "S05"]
```

Với phân hoạch:

```java
Map<Boolean, List<String>> idsByPaid = sales.stream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.mapping(
            Sale::id,
            Collectors.toList()
        )
    ));

// true -> [S01, S03, S04, S06]
// false -> [S02, S05]
```

So với chuyển cả Stream sang mã `Sale::id` trước khi grouping, cách đặt `mapping` downstream giữ khả năng phân nhóm theo các thuộc tính của đối tượng gốc.

### 7.5. Chọn phần tử lớn nhất trong mỗi nhóm

```java
Map<String, Optional<Sale>> largestByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.maxBy(
            Comparator.comparingLong(Sale::amount)
        )
    ));
```

`Collectors.maxBy` trả `Optional<Sale>` trong mỗi nhóm theo hợp đồng collector. Trong `groupingBy` thông thường, các khóa phát sinh từ phần tử đầu vào nên mỗi nhóm có ít nhất một phần tử, nhưng kiểu Optional vẫn được giữ vì collector `maxBy` có thể xử lý đầu vào rỗng.

Để lấy giá trị theo vùng:

```java
Optional<Sale> largestNorthern =
    largestByRegion.getOrDefault("Bắc", Optional.empty());

System.out.println(
    largestNorthern.map(Sale::id).orElse("Không có")
); // S01
```

Ví dụ cần import `java.util.Comparator` và `java.util.Optional`.

## 8. Kết hợp nhóm và phân hoạch nhiều tầng

Không có quy tắc rằng một báo cáo chỉ được dùng một collector. `groupingBy` và `partitioningBy` có thể đóng vai trò downstream của nhau.

### 8.1. Theo vùng, sau đó chia đã/chưa thanh toán

```java
Map<String, Map<Boolean, List<Sale>>> byRegionAndPaid =
    sales.stream()
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.partitioningBy(Sale::paid)
        ));
```

Cấu trúc:

```text
"Bắc" ──► true  : [S01, S03]
           false : [S05]

"Nam" ──► true  : [S04]
           false : [S02]

"Tây" ──► true  : [S06]
           false : []
```

**Đặc tính quan trọng:** vùng “Tây” đã xuất hiện nên có một nhóm `groupingBy`. Bên trong nhóm đó, `partitioningBy` vẫn tạo **đủ hai nhánh**; nhánh chưa thanh toán là danh sách rỗng.

Nhưng một vùng không hề xuất hiện, chẳng hạn “Đông”, sẽ **không** được tạo tự động ở Map lớp ngoài.

### 8.2. Theo trạng thái, sau đó nhóm doanh thu theo vùng

```java
Map<Boolean, Map<String, Long>> amountByPaymentAndRegion =
    sales.stream()
        .collect(Collectors.partitioningBy(
            Sale::paid,
            Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::amount)
            )
        ));
```

Kết quả:

| Trạng thái | Bắc | Nam | Tây |
| --- | ---: | ---: | ---: |
| true (đã thanh toán) | 200.000 | 140.000 | 200.000 |
| false (chưa thanh toán) | 50.000 | 60.000 | Không có khóa Tây |

Bên trong nhánh `false` không có vùng Tây vì không có giao dịch chưa thanh toán ở vùng đó. Hai **nhánh boolean** luôn tồn tại, nhưng các **khóa vùng ở downstream groupingBy** chỉ xuất hiện khi có dữ liệu tương ứng.

### 8.3. Phân nhóm theo khóa tổng hợp bằng record

Nếu chỉ cần mỗi cặp *(vùng, trạng thái)* là một nhóm riêng, có thể dùng record làm khóa:

```java
record GroupKey(String region, boolean paid) {}

Map<GroupKey, Long> counts = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> new GroupKey(sale.region(), sale.paid()),
        Collectors.counting()
    ));
```

`record` cung cấp `equals` và `hashCode` dựa trên các thành phần, thuận tiện khi khóa gồm nhiều trường.

Khác với lồng `partitioningBy`, cách `GroupKey` chỉ tạo các cặp thực sự xuất hiện: không có khóa `GroupKey("Tây", false)` trừ khi có phần tử phù hợp.

## 9. Lọc trước grouping khác filtering bên trong downstream

Đây là khác biệt dễ bị bỏ qua khi xây báo cáo cần hiển thị đủ nhóm.

### 9.1. Lọc trước: nhóm không có phần tử đạt điều kiện sẽ biến mất

```java
Map<String, Long> paidCount = sales.stream()
    .filter(Sale::paid)
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Ở bộ dữ liệu hiện tại, cả ba vùng đều có giao dịch đã thanh toán nên Map vẫn chứa ba vùng. Nhưng nếu có vùng chỉ chứa các giao dịch chưa thanh toán, vùng đó **không xuất hiện**.

### 9.2. filtering downstream: giữ nhóm đã được tạo

`Collectors.filtering` (Java 9+) áp dụng điều kiện **sau khi đã xác định khóa grouping**:

```java
Map<String, Long> paidCountIncludingZero = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.filtering(
            Sale::paid,
            Collectors.counting()
        )
    ));
```

Giả sử thêm giao dịch `new Sale("S07", "Đông", 30_000L, false)`:

- Với `filter(Sale::paid)` **trước** `groupingBy`, khóa “Đông” sẽ không xuất hiện.
- Với `filtering(Sale::paid, counting())` **trong downstream**, khóa “Đông” vẫn xuất hiện và có giá trị **0L**.

Điều này hữu ích khi một báo cáo phải giữ các nhóm có trong dữ liệu đầu vào kể cả khi không có phần tử đạt tiêu chí phụ.

`Collectors.filtering` không hoàn toàn thay thế `Stream.filter`; chúng diễn đạt **vị trí của phép lọc trong quá trình phân nhóm** và vì vậy có thể tạo cấu trúc kết quả khác nhau.

### 9.3. partitioningBy vẫn bảo đảm cả hai nhóm

Tương tự, trên một tập giao dịch chỉ có trạng thái `paid=true`:

```java
Map<Boolean, Long> counts = Stream.of(
        new Sale("S08", "Bắc", 10_000L, true)
    )
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 1
System.out.println(counts.get(false)); // 0
```

Không cần tự thêm khóa `false`. Đây là lợi thế của `partitioningBy` khi bài toán đúng là phân đôi theo boolean.

## 10. Map factory và thứ tự duyệt kết quả

Thứ tự phần tử trong Stream và thứ tự lặp qua các **khóa Map** là hai khái niệm khác nhau.

### 10.1. groupingBy có overload chỉ định loại Map

```java
Map<String, List<Sale>> sortedRegionKeys = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.toList()
    ));
```

`TreeMap::new` làm khóa vùng được duyệt theo thứ tự tự nhiên của `String`.

Có thể dùng `LinkedHashMap` khi muốn bảo toàn thứ tự chèn khóa theo một quy trình có encounter order rõ ràng:

```java
Map<String, List<Sale>> encounterRegionKeys = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

Trong ví dụ tuần tự với `List`, khóa được đưa vào lần đầu theo thứ tự gặp vùng. Không suy luận rằng mọi Map do `groupingBy` tạo mặc định là `LinkedHashMap`; loại Map mặc định và thứ tự duyệt của nó không được API cam kết.

### 10.2. toMap cũng có mapFactory

```java
Map<String, Long> sortedAmountByRegion = sales.stream()
    .collect(Collectors.toMap(
        Sale::region,
        Sale::amount,
        Long::sum,
        TreeMap::new
    ));
```

Overload bốn tham số chọn chính sách gộp `Long::sum` và loại Map `TreeMap`. **`mapFactory` không thay thế merge function**: nếu có khóa trùng, quy tắc gộp vẫn phải đúng.

### 10.3. partitioningBy không cần mapFactory

`Collectors.partitioningBy` không cung cấp overload `mapFactory` vì miền khóa đã cố định ở hai giá trị boolean. Đừng dựa vào thứ tự duyệt nội bộ của Map kết quả.

Nếu cần trình bày đúng thứ tự:

```java
Map<Boolean, List<Sale>> partitions = sales.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

List<Sale> paidFirst = partitions.get(true);
List<Sale> unpaidSecond = partitions.get(false);
```

Việc truy cập theo khóa rõ ràng và không cần suy đoán thứ tự `entrySet()`.

### 10.4. TreeMap và quy tắc bằng khóa

Với `HashMap`, khóa tương đương theo `equals`/`hashCode`. Với `TreeMap`, thứ tự và việc xác định khóa trùng dựa trên Comparator hoặc thứ tự tự nhiên của khóa.

Nếu Comparator coi hai khóa khác nhau là bằng nhau (`compare(a,b) == 0`), `TreeMap` có thể xem chúng là cùng khóa. Khi cần mã không phân biệt hoa thường, nên quyết định rõ việc chuẩn hóa khóa thay vì vô tình làm mất phân biệt:

```java
Map<String, Long> normalized = sales.stream()
    .collect(Collectors.toMap(
        sale -> sale.region().trim()
            .toLowerCase(Locale.ROOT),
        Sale::amount,
        Long::sum
    ));
```

Ví dụ cần import `java.util.Locale`. Việc chuẩn hóa chuỗi phải theo quy tắc dữ liệu; với một số mã, chữ hoa và chữ thường có thể mang ý nghĩa khác nhau.

## 11. Các trường hợp biên: nguồn rỗng, null và khóa trùng

### 11.1. So sánh ba collector trên nguồn rỗng

```java
List<Sale> empty = List.of();

Map<String, List<Sale>> groups = empty.stream()
    .collect(Collectors.groupingBy(Sale::region));

Map<Boolean, List<Sale>> partitions = empty.stream()
    .collect(Collectors.partitioningBy(Sale::paid));

Map<String, Sale> map = empty.stream()
    .collect(Collectors.toMap(
        Sale::id,
        Function.identity()
    ));

System.out.println(groups.isEmpty());          // true
System.out.println(partitions.size());         // 2
System.out.println(partitions.get(true));      // []
System.out.println(partitions.get(false));     // []
System.out.println(map.isEmpty());             // true
```

Đây là bài kiểm tra nhanh giúp phân biệt hợp đồng của ba API.

### 11.2. null ở khóa và giá trị

Với `groupingBy`, classifier trả `null` gây `NullPointerException`. Với `toMap`, cần tránh dựa vào hành vi chấp nhận khóa `null` của một triển khai Map cụ thể; hãy định nghĩa chính sách dữ liệu hợp lệ.

Giá trị tạo bởi `valueMapper` của `toMap` nên khác `null`. Trên các triển khai JDK phổ biến, giá trị `null` sẽ dẫn đến `NullPointerException`:

```java
record User(String id, String email) {}

List<User> users = List.of(
    new User("U1", "an@example.com"),
    new User("U2", null)
);

// Không thu trực tiếp bằng toMap(User::id, User::email)
// khi email có thể null và không có chính sách xử lý.
```

Nếu nghiệp vụ cho phép bỏ qua bản ghi thiếu email:

```java
Map<String, String> emailsById = users.stream()
    .filter(user -> user.email() != null)
    .collect(Collectors.toMap(
        User::id,
        User::email
    ));
```

Nếu việc thiếu email là trạng thái cần bảo toàn, dùng một kiểu giá trị khác `null` để biểu diễn, chẳng hạn record hoặc `Optional<String>`, và xem xét yêu cầu API tiêu thụ Map sau đó.

### 11.3. null từ mergeFunction có thể loại bỏ mục

`Map.merge` có quy tắc: nếu hàm gộp trả `null`, ánh xạ đang tồn tại có thể bị xóa. Vì `toMap` dùng cơ chế gộp Map, **không trả null để có nghĩa “giữ giá trị hiện có”**.

```java
Map<String, Long> map = new HashMap<>();

map.merge("Bắc", 100L, Long::sum);
map.merge("Bắc", 20L, (oldValue, newValue) -> null);

System.out.println(map.containsKey("Bắc")); // false
```

Ví dụ cần import `java.util.HashMap`. Với nghiệp vụ muốn giữ giá trị đầu, trả `oldValue` rõ ràng.

### 11.4. Phân biệt null với nhóm trống

- **Khóa không tồn tại trong Map groupingBy:** không có phần tử nào phân loại ra khóa đó.
- **Khóa `true/false` của partitioningBy có danh sách rỗng:** nhánh được bảo đảm tồn tại nhưng không có phần tử.
- **Một Map toMap không chứa khóa:** không có phần tử tạo khóa đó, hoặc quy tắc gộp đặc biệt đã loại bỏ ánh xạ.

Không nên đồng nhất các ý nghĩa này khi viết API trả báo cáo cho người dùng.

## 12. Thứ tự, tính kết hợp và chế độ song song

### 12.1. Collector có thể tích lũy theo nhiều nhánh

Một pipeline `parallelStream()` có thể chia nguồn thành các phần, tích lũy từng phần và kết hợp các kết quả trung gian.

```text
Nguồn [S01, S02, S03, S04, S05, S06]
                   │
               trySplit(...)
             ┌─────┴──────┐
             ▼            ▼
         phần A         phần B
             │            │
         Map tạm A      Map tạm B
             └────┬───────┘
                  ▼
              gộp Map
                  │
                  ▼
             kết quả cuối
```

Cách chia nguồn và số lần gọi các hàm nội bộ phụ thuộc framework, không được dùng làm quy tắc nghiệp vụ. Để `collect` đúng trong song song, các phép tích lũy và gộp phải tuân thủ hợp đồng collector, bao gồm **identity, associativity, tương đương kết quả** và tránh trạng thái mutable dùng chung không an toàn.

### 12.2. groupingBy có thể dùng trên parallelStream

```java
Map<String, Long> parallelCounts = sales.parallelStream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Kết quả số đếm vẫn phải tương đương về mặt nghiệp vụ với xử lý tuần tự. Nhưng `groupingBy` thông thường **không phải concurrent collector**. Framework có thể phải gộp Map của các nhánh; nếu có rất nhiều khóa, việc gộp gây chi phí.

`Collectors.groupingByConcurrent` là một lựa chọn khác khi phù hợp, nhưng kết quả không bảo đảm thứ tự gặp phần tử như collector ordered. Nếu cần danh sách trong mỗi nhóm theo thứ tự nguồn, đừng tự ý thay bằng `groupingByConcurrent` chỉ để tăng tốc.

### 12.3. partitioningBy không cần tranh chấp nhiều khóa

`partitioningBy` chỉ có hai nhánh; điều đó không đồng nghĩa mặc định an toàn để nhiều luồng ghi trực tiếp vào cùng một `ArrayList`. Collector tiêu chuẩn chịu trách nhiệm tổ chức các container tích lũy và gộp chúng theo hợp đồng khi chạy song song.

```java
Map<Boolean, Long> parallelPaidCounts = sales.parallelStream()
    .collect(Collectors.partitioningBy(
        Sale::paid,
        Collectors.counting()
    ));
```

Không cần tạo biến `long[]` chia sẻ rồi tăng đếm trong `forEach`; cách đó có thể tạo race condition.

### 12.4. toMap và mergeFunction phải có tính kết hợp

`Long::sum`, `Long::max`, `Long::min` là những quy tắc gộp thường phù hợp cho các bài toán tổng hợp số nguyên, với lưu ý tràn số. Phép trừ không có tính kết hợp:

```text
(100 - 40) - 10 = 50
100 - (40 - 10) = 70
```

Vì vậy:

```java
// Không dùng phép trừ như merge function tổng quát khi
// cần kết quả không phụ thuộc cách chia/gộp:
// (left, right) -> left - right
```

Nếu `mergeFunction` có tác động phụ, ví dụ ghi log vào một `ArrayList` dùng chung, số lần gọi và thứ tự gọi có thể thay đổi khi chạy song song. Một collector đúng nên biểu diễn kết quả bằng **dữ liệu tích lũy**, không đặt tác vụ nghiệp vụ bắt buộc bên trong merge function.

### 12.5. "Giữ đầu" và "giữ cuối" phụ thuộc thứ tự nguồn

Với một `List` có thứ tự gặp phần tử, `(first,next)->first` và `(first,next)->next` có thể diễn đạt việc chọn phần tử đầu/cuối cho mỗi khóa theo thứ tự đó khi dùng `toMap` thông thường.

Nhưng với nguồn không có encounter order, khái niệm đầu/cuối không được bảo đảm. Nếu yêu cầu là **đơn mới nhất theo thời gian**, nên gộp bằng `BinaryOperator.maxBy(Comparator.comparing(...))` với tie-breaker ổn định, thay vì giả định phần tử được xử lý cuối cùng là mới nhất.

`toConcurrentMap` là concurrent, unordered collector. Dùng nó cùng chính sách first/last dựa trên thứ tự nguồn có thể chọn giá trị tùy lịch thực thi; nó không phải lựa chọn phù hợp nếu thứ tự là yêu cầu nghiệp vụ.

## 13. Hiệu năng và cấu trúc dữ liệu trung gian

Không có collector nào luôn nhanh nhất. Hiệu quả phụ thuộc mục tiêu, số khóa phân biệt, kích thước nguồn và lượng dữ liệu cần giữ.

### 13.1. Bộ nhớ khác nhau

Với `n` phần tử và `k` khóa phân biệt:

| Cách thu | Đặc trưng bộ nhớ cần lưu |
| --- | --- |
| `groupingBy(key)` mặc định | Giữ danh sách phần tử; tổng số tham chiếu có thể tỷ lệ với `n`, cộng chi phí nhóm. |
| `groupingBy(key, counting())` | Chủ yếu giữ trạng thái đếm cho `k` nhóm. |
| `partitioningBy(predicate)` mặc định | Giữ phần tử trong hai danh sách; tổng số tham chiếu tỷ lệ với `n`. |
| `partitioningBy(predicate, counting())` | Chỉ cần hai bộ đếm kết quả và trạng thái tích lũy phù hợp. |
| `toMap(key, value, merge)` | Một giá trị cuối cho mỗi khóa, thường tỷ lệ với `k`. |

Nếu chỉ cần số lượng theo vùng, không cần thu mọi giao dịch vào danh sách rồi gọi `size()`. Nếu chỉ cần doanh thu theo vùng, `summingLong` hoặc `Long::sum` tránh giữ toàn bộ giao dịch.

### 13.2. Thời gian và chi phí gộp

Thu Map trên nền hash thông thường thường có chi phí trung bình gần tuyến tính với số phần tử, nhưng phụ thuộc chất lượng hash, phân phối khóa, việc trích khóa, merge function và số lượng va chạm.

`TreeMap` thường có chi phí thao tác `O(log k)` theo số khóa `k` và cung cấp thứ tự duyệt khóa theo comparator. `LinkedHashMap` cần thêm cấu trúc lưu thứ tự. Khi chạy song song, chi phí chia/gộp Map có thể vượt lợi ích tính toán nếu dữ liệu không đủ lớn hoặc phép tích lũy quá nhẹ.

### 13.3. Dữ liệu vô hạn và tài nguyên I/O

Các phép `collect` tổng hợp toàn bộ nguồn thường cần nguồn **có điểm kết thúc**. Trên `Stream.generate(...)` vô hạn mà không giới hạn, pipeline có thể không hoàn thành, và collector giữ danh sách có thể tăng bộ nhớ không giới hạn.

Nếu dữ liệu đến từ tệp:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class PaidStateFromFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("statuses.txt");

        try (Stream<String> lines = Files.lines(path)) {
            Map<Boolean, Long> counts = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.partitioningBy(
                    line -> line.equalsIgnoreCase("PAID"),
                    Collectors.counting()
                ));

            System.out.println(counts.get(true));
            System.out.println(counts.get(false));
        }
    }
}
```

Ví dụ minh họa giả định mỗi dòng là một trạng thái, và mọi trạng thái không phải `PAID` đều được xếp vào `false`. Với dữ liệu sản xuất, cần chính sách cho trạng thái không hợp lệ. `Files.lines` phải được đóng bằng `try-with-resources`: **`collect` không tự động đóng tài nguyên tệp**.

## 14. Ví dụ Java hoàn chỉnh: cả ba collector trên một nguồn

Chương trình dưới đây minh họa grouping, partitioning, toMap và downstream nhiều tầng trong một lần chạy. Lưu thành `GroupingPartitioningMapDemo.java` và sử dụng Java 17+.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class GroupingPartitioningMapDemo {
    record Sale(String id, String region, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S01", "Bắc", 120_000L, true),
            new Sale("S02", "Nam",  60_000L, false),
            new Sale("S03", "Bắc",  80_000L, true),
            new Sale("S04", "Nam", 140_000L, true),
            new Sale("S05", "Bắc",  50_000L, false),
            new Sale("S06", "Tây", 200_000L, true)
        );

        // 1. Nhiều phần tử cho mỗi khóa region.
        Map<String, List<Sale>> byRegion = sales.stream()
            .collect(Collectors.groupingBy(Sale::region));

        // 2. Luôn có đủ hai nhánh true và false.
        Map<Boolean, List<Sale>> byPayment = sales.stream()
            .collect(Collectors.partitioningBy(Sale::paid));

        // 3. Một Sale cho mỗi ID duy nhất.
        Map<String, Sale> byId = sales.stream()
            .collect(Collectors.toMap(
                Sale::id,
                Function.identity()
            ));

        // 4. Một tổng long cho mỗi vùng, khóa được sắp.
        Map<String, Long> totalAmountByRegion = sales.stream()
            .collect(Collectors.toMap(
                Sale::region,
                Sale::amount,
                Long::sum,
                TreeMap::new
            ));

        // 5. Hai nhánh boolean, mỗi nhánh lại nhóm theo vùng.
        Map<Boolean, Map<String, Long>> amountByPaymentAndRegion =
            sales.stream()
                .collect(Collectors.partitioningBy(
                    Sale::paid,
                    Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingLong(Sale::amount)
                    )
                ));

        System.out.println(byRegion.get("Bắc").size());       // 3
        System.out.println(byPayment.get(true).size());       // 4
        System.out.println(byPayment.get(false).size());      // 2
        System.out.println(byId.get("S03").amount());         // 80000
        System.out.println(totalAmountByRegion.get("Bắc"));  // 250000

        System.out.println(
            amountByPaymentAndRegion.get(true).get("Bắc")
        ); // 200000

        System.out.println(
            amountByPaymentAndRegion.get(false).get("Nam")
        ); // 60000

        System.out.println(
            amountByPaymentAndRegion.get(false).containsKey("Tây")
        ); // false: không có giao dịch chưa thanh toán ở Tây.
    }
}
```

### 14.1. Ý nghĩa từng kết quả

| Biến | Kiểu Map | Ý nghĩa |
| --- | --- | --- |
| `byRegion` | `Map<String, List<Sale>>` | Mỗi vùng giữ nhiều `Sale`. |
| `byPayment` | `Map<Boolean, List<Sale>>` | Hai tập đã/chưa thanh toán. |
| `byId` | `Map<String, Sale>` | Tra cứu theo mã duy nhất. |
| `totalAmountByRegion` | `Map<String, Long>` | Tổng tiền theo vùng, gồm cả giao dịch chưa thanh toán. |
| `amountByPaymentAndRegion` | `Map<Boolean, Map<String, Long>>` | Tổng tiền theo trạng thái, rồi theo vùng. |

Không có phép thu thập nào trên đây làm thay đổi nội dung `sales`.

### 14.2. Vì sao phải tạo Stream mới cho mỗi phép collect?

`Stream` chỉ được tiêu thụ một lần. Vì `sales` là một `List` có thể duyệt lại, mỗi lời gọi `sales.stream()` tạo một Stream mới:

```java
var stream = sales.stream();
long count = stream.count();

// Không dùng lại:
// Map<String, List<Sale>> wrong = stream.collect(
//     Collectors.groupingBy(Sale::region)
// );
```

Nếu nguồn gốc là một iterator chỉ dùng một lần hoặc một Stream đọc tệp, cần thiết kế để tính các kết quả cần thiết trong một lần duyệt, ví dụ một collector tổng hợp riêng hoặc `Collectors.teeing` khi thích hợp.

### 14.3. Nếu chỉ cần ba kết quả khác nhau?

Việc thu thập nhiều lần từ List nhỏ có thể đủ đơn giản. Nhưng nếu nguồn rất lớn hoặc việc duyệt đắt đỏ, cần cân nhắc một bản tóm tắt kết hợp nhiều phép đếm và tổng để chỉ duyệt một lần. Cách làm đó thuộc thiết kế collector tùy chỉnh hoặc `teeing`, không phải lý do để lạm dụng một `Map<String, List<Sale>>` chứa tất cả dữ liệu nếu chỉ cần thống kê.

## 15. Bảng quyết định lựa chọn collector

| Yêu cầu thực tế | Collector nên cân nhắc | Lý do |
| --- | --- | --- |
| Danh sách giao dịch theo vùng | `groupingBy(Sale::region)` | Mỗi khóa giữ nhiều phần tử. |
| Đếm giao dịch theo vùng | `groupingBy(Sale::region, counting())` | Không cần giữ từng phần tử. |
| Tổng tiền theo vùng | `groupingBy(..., summingLong(...))` hoặc `toMap(..., Long::sum)` | Mỗi khóa chỉ cần tổng. |
| Tách đơn đã thanh toán/chưa thanh toán | `partitioningBy(Sale::paid)` | Hai nhánh boolean, kể cả nhánh rỗng. |
| Đếm đơn đạt/chưa đạt ngưỡng | `partitioningBy(predicate, counting())` | Hai giá trị đếm cho đủ hai trạng thái. |
| Tra giao dịch theo mã duy nhất | `toMap(Sale::id, identity())` | Một đối tượng cho mỗi khóa. |
| Chọn bản ghi tốt nhất theo khóa | `toMap(key, identity(), BinaryOperator.maxBy(comparator))` | Quy tắc chọn một đại diện rõ ràng. |
| Giữ mọi bản ghi theo từng tổ hợp vùng/trạng thái | `groupingBy(compositeKey)` hoặc nhóm lồng `partitioningBy` | Tùy yêu cầu có cần hai nhánh luôn tồn tại. |
| Theo vùng nhưng tính riêng các đơn đạt tiêu chí | `groupingBy(region, filtering(predicate, downstream))` | Giữ cả vùng chỉ có phần tử không đạt. |
| Khóa cần sắp theo thứ tự từ điển | `groupingBy(key, TreeMap::new, downstream)` hoặc `toMap(..., TreeMap::new)` | Quyết định thứ tự duyệt Map. |
| Xử lý song song với nhiều nhóm | `groupingByConcurrent` nếu chấp nhận kết quả không bảo đảm thứ tự | Cần cân nhắc tính đúng và đo hiệu năng. |

Nếu không thể chọn trong vài giây, hãy viết trước **kiểu dữ liệu kết quả mong muốn**. Ví dụ `Map<String, List<Sale>>` thường gợi `groupingBy`; `Map<Boolean, Long>` gợi `partitioningBy(predicate, counting())`; `Map<String, Sale>` gợi `toMap` với chính sách khóa trùng.

## 16. Sai lầm phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `toMap(region, identity())` khi một vùng có nhiều bản ghi | `IllegalStateException` vì khóa trùng. | `groupingBy(region)` hoặc cung cấp merge function. |
| Dùng `groupingBy(Sale::paid)` rồi giả định luôn có cả `true`/`false` | Nhánh không xuất hiện có thể thiếu khóa. | `partitioningBy(Sale::paid)`. |
| Coi `partitioningBy` như grouping tùy ý nhiều nhóm | Chỉ phân chia theo boolean. | Dùng `groupingBy(classifier)` cho nhiều nhãn. |
| Cần tổng tiền nhưng giữ toàn bộ `List<Sale>` trong Map | Dùng bộ nhớ không cần thiết. | `summingLong`, `counting` hoặc `toMap` với merge. |
| Nhầm `filter` trước grouping với `Collectors.filtering` downstream | Nhóm không có bản ghi hợp lệ có thể biến mất. | Chọn vị trí lọc theo hợp đồng báo cáo. |
| Mong Map của `groupingBy` hoặc `toMap` mặc định giữ thứ tự Stream | Không có bảo đảm loại Map hay thứ tự duyệt. | Dùng `mapFactory` phù hợp nếu cần. |
| Mong `partitioningBy` có overload `mapFactory` | Không có overload như vậy. | Truy cập rõ khóa `true` và `false`. |
| Cho rằng `groupingBy` chấp nhận khóa `null` vì `HashMap` cho phép | `NullPointerException` ở classifier trả null. | Chuẩn hóa hoặc dùng khóa biểu diễn thiếu dữ liệu. |
| Giá trị của `toMap` là `null` | Có thể ném `NullPointerException`. | Lọc/xác thực hoặc dùng kiểu giá trị khác null. |
| Dùng `(a,b)->a-b` để gộp doanh thu | Không có tính kết hợp khi chia/gộp. | `Long::sum` hoặc phép tổng phù hợp. |
| Khai báo `parallelStream()` rồi cập nhật chung một `ArrayList` trong lambda | Race condition. | Sử dụng collector đúng hợp đồng. |
| Dùng first/last với nguồn unordered | Không bảo đảm phần tử nào thắng. | Chọn bằng Comparator theo trường nghiệp vụ. |
| Quên xử lý tràn `long` trong tổng tiền | Kết quả sai khi vượt miền số. | Chọn `Math.addExact` hoặc kiểu số đủ rộng theo chính sách. |
| Tạo `collect` từ Stream vô hạn không dừng | Không kết thúc hoặc cạn bộ nhớ. | Giới hạn nguồn phù hợp. |
| Gọi `collect` trên Stream lấy từ tệp mà không đóng | Rò rỉ tài nguyên I/O. | `try-with-resources`. |

## 17. Bài tập tự thực hành

**Bài 1 — Ba dạng Map.** Với danh sách `Sale` ở mục 2, tạo lần lượt `Map<String,List<Sale>>` theo vùng, `Map<Boolean,List<Sale>>` theo thanh toán và `Map<String,Sale>` theo ID. Giải thích khi nào mỗi Map phù hợp hơn hai Map còn lại.

**Bài 2 — Nguồn rỗng.** Cho `List<Sale> empty = List.of()`. Thu ba Map bằng `groupingBy`, `partitioningBy` và `toMap`. Kiểm tra số khóa và giá trị của hai nhánh boolean.

**Bài 3 — Tổng theo khóa.** Tính số tiền theo vùng bằng hai cách: `groupingBy(..., summingLong(...))` và `toMap(..., Long::sum)`. So sánh các giá trị của từng khóa.

**Bài 4 — Nhóm rỗng sau lọc.** Bổ sung vùng “Đông” chỉ có giao dịch chưa thanh toán. So sánh kết quả giữa lọc trước `groupingBy` và `Collectors.filtering` ở downstream.

**Bài 5 — Nhiều cấp.** Tạo `Map<String, Map<Boolean, Long>>` với tổng tiền theo vùng rồi theo trạng thái. Kiểm tra nhánh `false` của vùng Tây vẫn tồn tại và có tổng `0L`.

**Bài 6 — Chọn bản ghi đại diện.** Với các giao dịch trùng mã vùng, chọn giao dịch có `amount` cao nhất bằng `toMap` và `BinaryOperator.maxBy`. Bổ sung tie-breaker theo `id` nếu nhiều giao dịch có cùng số tiền.

**Bài 7 — Kiểm tra khóa null.** Thêm giao dịch có `region = null`. Quan sát cách `groupingBy` xử lý; đề xuất một quy tắc giữ thông tin vùng thiếu mà không trộn với tên vùng có thật.

**Bài 8 — Parallel.** Tính số giao dịch theo vùng bằng `stream()` và `parallelStream()`. So sánh hai Map theo giá trị, không phụ thuộc thứ tự duyệt Map. Giải thích tại sao một collector có thể song song mà vẫn phải gộp Map trung gian.

**Bài 9 — Lựa chọn độ chính xác.** Nếu tổng số tiền có thể vượt giới hạn `long`, đề xuất kiểu tích lũy hoặc chính sách phát hiện lỗi thay cho việc tin tuyệt đối vào `Long::sum`.

**Bài 10 — Thiết kế báo cáo.** Một hệ thống cần đồng thời đếm tổng số giao dịch, đếm số đã thanh toán và tổng tiền đã thanh toán theo vùng. Đề xuất kiểu kết quả và cách xây downstream collector phù hợp, chỉ rõ những nơi có thể cần collector tùy chỉnh.

Gợi ý Bài 5:

```java
Map<String, Map<Boolean, Long>> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.partitioningBy(
            Sale::paid,
            Collectors.summingLong(Sale::amount)
        )
    ));

System.out.println(totals.get("Tây").get(false)); // 0
```

Vì `groupingBy` đã tạo nhóm “Tây”, downstream `partitioningBy` dành cho nhóm đó vẫn có đủ `true` và `false`, kể cả khi danh sách của một nhánh rỗng.

## 18. Ghi nhớ cốt lõi

- **`groupingBy`** phân nhóm theo một khóa `K` và mặc định trả `Map<K,List<T>>`. Với downstream collector, mỗi nhóm có thể trở thành số đếm, tổng tiền, tập mã hoặc báo cáo riêng.
- **`partitioningBy`** phân nhóm theo `Predicate<T>` và luôn cung cấp **đúng hai khóa `true`, `false`**, kể cả khi nguồn hoặc một nhánh rỗng.
- **`toMap`** tạo **một giá trị cho mỗi khóa**. Overload không có merge function từ chối khóa trùng; overload có merge function cho phép giữ đầu, giữ cuối, cộng, chọn lớn nhất hoặc áp dụng quy tắc nghiệp vụ.
- **Downstream collector quyết định cấu trúc đầu ra** của `groupingBy`/`partitioningBy`. Có thể lồng hai collector để tạo báo cáo nhiều cấp và chú ý sự khác biệt giữa nhóm không tồn tại với nhánh rỗng.
- **Lọc trước `groupingBy` có thể làm mất một khóa nhóm**, còn `Collectors.filtering` trong downstream vẫn giữ nhóm đã được tạo và trả kết quả downstream cho nhóm không có phần tử đạt điều kiện.
- **Thứ tự duyệt Map không đồng nghĩa encounter order của Stream**. Dùng `TreeMap` hoặc `LinkedHashMap` theo mục tiêu; truy cập rõ hai khóa boolean khi dùng partitioning.
- **Collector phải tuân thủ hợp đồng tích lũy và kết hợp**, nhất là trong song song. Không dựa vào tác động phụ, thứ tự thực thi hay phép gộp không có tính kết hợp.
- **Độ đúng phụ thuộc dữ liệu và nguồn:** tránh classifier `null`, xem xét khóa trùng, tràn số, chi phí lưu nhiều danh sách, Stream vô hạn và tài nguyên I/O.
- Phân biệt rõ ba cách thu Map là nền tảng để thiết kế grouping sâu hơn, collector tùy chỉnh, tối ưu `Spliterator` và các pipeline khai báo nâng cao trong **JAVA_STREAM_API**.
