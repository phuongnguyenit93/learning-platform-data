# Ước lượng bộ nhớ của sorted, distinct, groupingBy và collect

Java Stream API giúp diễn đạt việc xử lý dữ liệu bằng pipeline khai báo, có tính *lazy*, với các bước như `filter`, `map`, `sorted`, `distinct`, `reduce` và `collect`. Tuy vậy, **lazy không có nghĩa pipeline luôn dùng bộ nhớ hằng số**. Một số phép toán phải ghi nhớ dữ liệu đã gặp hoặc gom nhiều phần tử trước khi tạo kết quả. Điển hình là `sorted`, `distinct`, `groupingBy` và các dạng `collect` giữ toàn bộ phần tử.

Bài thuộc chương **Hiệu năng và bộ nhớ** của module **JAVA_STREAM_API**. Mục tiêu là biết cách **ước lượng bộ nhớ tăng thêm**, phân biệt bộ nhớ đỉnh với bộ nhớ kết quả, xác định yếu tố chi phối từng phép toán, đánh giá tác động của `Spliterator` và parallel stream, rồi chọn thiết kế phù hợp cho dữ liệu lớn. Kiến thức này liên hệ trực tiếp tới grouping, collector tùy chỉnh, xử lý song song và giới hạn tài nguyên; các phép biến đổi nâng cao như Stream Gatherers cũng phải tuân theo cùng nguyên tắc về trạng thái và đầu ra.

> **Nguyên tắc:** Không kết luận một pipeline có bộ nhớ `O(1)` chỉ vì nó không có vòng lặp hoặc vì nó trả về `Stream`. Phải xem **từng thao tác**, **terminal operation** và **kích thước kết quả còn được giữ**.

## 1. Phân biệt những loại bộ nhớ cần tính

Trước khi ghi con số “pipeline dùng X MB”, hãy xác định **đang đếm phần nào**:

| Thành phần | Ví dụ | Có nên tính khi ước lượng? |
|---|---|---|
| **Nguồn đã có sẵn** | `ArrayList<Order>` chứa một triệu đối tượng | Có trong **tổng heap ứng dụng**; có thể tách khỏi **bộ nhớ tăng thêm do pipeline** |
| **Trạng thái trung gian** | Buffer sắp xếp, bảng băm của `distinct` | Có; có thể tồn tại trong lúc pipeline chạy |
| **Trạng thái collector** | Map các nhóm, danh sách ở mỗi nhóm | Có; thường trở thành một phần kết quả cuối |
| **Đầu ra giữ lại** | `List` từ `collect(toList())` | Có; vẫn còn sau khi terminal operation kết thúc |
| **Đối tượng tạm** | Wrapper, iterator, entry, kết quả mapper | Có thể tăng cấp phát và áp lực GC dù không còn sống lâu |
| **Bộ nhớ thực thi song song** | State riêng của nhánh, hàng đợi fork/join, buffer gộp | Có; thay đổi theo cách phân nhánh và độ song song |
| **Tài nguyên ngoài heap** | File handle, native buffer, direct memory | Phải quản lý; không phản ánh hết qua số heap của collector |

### 1.1. Bộ nhớ giữ lại, bộ nhớ tăng thêm và bộ nhớ đỉnh

Đặt:

- `B_source`: kích thước phần nguồn đã tồn tại và còn được tham chiếu.
- `B_state(t)`: trạng thái trung gian còn sống tại thời điểm `t`.
- `B_result(t)`: phần kết quả đã tạo và còn sống tại `t`.
- `B_misc(t)`: các vùng đệm, đối tượng phụ trợ và dữ liệu tạm còn sống.

Ước lượng **đỉnh heap sống** của tác vụ:

\[
B_{\text{peak}}\;\approx\; B_{\text{source}}\;+\;
\max_t\bigl(B_{\text{state}}(t)+B_{\text{result}}(t)+B_{\text{misc}}(t)\bigr)
\]

Đây là **mô hình ước lượng**, không phải đẳng thức chính xác về heap JVM. GC, phân bổ nội bộ, thời điểm giải phóng tham chiếu và implementation có thể làm đỉnh khác với tổng các con số đơn giản. Không nên cộng mọi buffer từng xuất hiện như thể tất cả luôn sống đồng thời.

**Bộ nhớ giữ lại sau khi collect** có thể nhỏ hơn nhiều bộ nhớ đỉnh: buffer `sorted` có thể được giải phóng, trong khi `List` hoặc `Map` kết quả còn được caller giữ. Trái lại, một pipeline `sorted().limit(5).toList()` có thể **trả về chỉ 5 phần tử nhưng vẫn từng cần buffer lớn** trong quá trình sắp xếp.

### 1.2. Ký hiệu xuyên suốt bài

| Ký hiệu | Nghĩa |
|---|---|
| `n` | Số phần tử thực sự đến thao tác đang xét |
| `u` | Số phần tử **phân biệt** theo `equals/hashCode` sau `distinct`, `u ≤ n` |
| `k` | Số **khóa nhóm** phân biệt trong `groupingBy`, `k ≤ n` |
| `m` | Số phần tử thực sự được giữ trong một collection kết quả |
| `p` | Số bộ tích lũy hoặc nhánh trung gian có thể cùng tồn tại, **không nhất thiết bằng số thread** |
| `L` | Tổng độ dài nội dung chuỗi khi nối thành String |

Các ký hiệu này dùng cho **độ phức tạp bộ nhớ** theo số phần tử/phần nhóm; để quy ra byte phải tính cấu trúc đối tượng, tham chiếu và cách triển khai trên JVM mục tiêu.

## 2. Bảng tổng quan độ phức tạp bộ nhớ

Với nguồn hữu hạn, thao tác thực sự phải duyệt và tạo đầy đủ kết quả cần thiết, bảng sau là cách ước lượng định hướng:

| Phép toán | Trạng thái thêm thường gặp | Kết quả giữ lại nếu là terminal phù hợp | Điểm dễ nhầm |
|---|---|---|---|
| `map`, `filter` | Thường `O(1)` trên pipeline tuần tự đơn giản | Phụ thuộc terminal operation | Lazy không có nghĩa không cấp phát đối tượng |
| `sorted` | Thường **`O(n)`** để sắp xếp các phần tử đến bước đó | Nếu `collect(toList())`: `O(n)` tham chiếu đầu ra | `limit` đặt **sau** `sorted` không mặc nhiên giảm bộ nhớ sort |
| `distinct` | Thường **`O(u)`** cho thông tin phần tử đã gặp | Nếu giữ mọi giá trị phân biệt: `O(u)` | `u` phụ thuộc nội dung và `equals/hashCode` |
| `groupingBy(key, counting())` | Thường **`O(k)`** | Map `k` nhóm với số đếm | Chỉ đếm, không giữ từng phần tử |
| `groupingBy(key, toList())` | Thường **`O(k+n)`** | Map và các List tổng cộng chứa `n` tham chiếu | Có thể giữ tất cả đối tượng đầu vào |
| `groupingBy(key, toSet())` | Thường **`O(k+\sum u_i)`** | Map với Set phân biệt trong từng nhóm | Mỗi nhóm có bảng băm riêng |
| `collect(toList())` | Thường **`O(m)`** | List `m` phần tử | Chỉ giữ tham chiếu không có nghĩa các đối tượng có kích thước 0 |
| `collect(toSet())` | Thường **`O(u)`** | Set `u` phần tử | Tốn thêm bucket/node của hash table |
| `collect(toMap(...))` | Thường **`O(k)`** cho Map; giá trị có thể lớn hơn | Map `k` khóa | Nếu value là List, phải cộng kích thước mọi List |
| `count()`, `sum()` | Thường **`O(1)`** trên nguồn đơn giản | Một số | Có thể xuất hiện buffer ở các bước **trước** terminal |
| `summarizingLong(...)` | **`O(1)`** cho một bộ thống kê | `LongSummaryStatistics` | Không giữ tất cả số liệu đầu vào |

**Bảng không phải lời hứa implementation.** Một số đường thực thi có thể tối ưu hóa nguồn đã sắp xếp, nguồn biết trước số lượng hoặc chuỗi thao tác đặc biệt. Ngược lại, parallel stream có thể cần thêm buffer và container cục bộ. Phân tích an toàn phải dựa trên **ngữ nghĩa cần thực hiện**, sau đó dùng profiling để kiểm chứng JVM cụ thể.

## 3. sorted: vì sao dễ cần O(n) bộ nhớ?

`Stream.sorted()` sắp xếp các phần tử theo thứ tự tự nhiên; `sorted(comparator)` dùng comparator đã cung cấp. Để phát phần tử **nhỏ nhất trước**, thuật toán sắp xếp thông thường phải biết các phần tử của nguồn liên quan, bởi phần tử cuối có thể nhỏ hơn tất cả những phần tử đã thấy.

```java
List<Integer> sorted = Stream.of(9, 1, 7, 3, 2)
        .sorted()
        .collect(Collectors.toList());

System.out.println(sorted); // [1, 2, 3, 7, 9]
```

Với nguồn hữu hạn nhưng chưa có thứ tự phù hợp, thư viện thường **đệm các phần tử cần sắp xếp** rồi sắp xếp chúng. Vì vậy, trạng thái trung gian có thể tỷ lệ với **`n` phần tử tới bước sorted**, tức `O(n)` tham chiếu hoặc đối tượng bao gói tùy loại Stream/implementation.

### 3.1. Tính số byte ở mức mô hình

Giả sử:

- `n = 1_000_000` đối tượng `Sale` đã có sẵn trong một List.
- JVM 64-bit giả định tham chiếu nén (*compressed ordinary object pointers*) có kích thước **4 byte**.
- Một mảng tham chiếu dùng để giữ đúng một triệu phần tử, **không tính bản thân đối tượng `Sale`**.

Chỉ riêng vùng phần tử của một mảng tham chiếu sẽ là:

\[
1\,000\,000 \times 4 = 4\,000\,000\ \text{byte}
\approx 3{,}81\ \text{MiB}
\]

Đó là **phần dữ liệu tham chiếu** trong một mảng giả định, **chưa phải tổng bộ nhớ `sorted`**. Cần cộng header mảng, căn chỉnh, dung lượng dự phòng, buffer phụ hoặc mảng trung gian do implementation sử dụng, các đối tượng mới tạo từ mapper và kết quả cuối. Nếu JVM sử dụng tham chiếu 8 byte, riêng một triệu tham chiếu đã xấp xỉ **7,63 MiB**.

### 3.2. sorted().limit(10) vẫn có thể tốn O(n)

```java
List<Sale> cheapestTen = sales.stream()
        .sorted(Comparator.comparingLong(Sale::getCents))
        .limit(10)
        .collect(Collectors.toList());
```

Giả sử `sales` có một triệu bản ghi. `limit(10)` chỉ yêu cầu **10 kết quả đầu**, nhưng để biết đó là những bản ghi rẻ nhất, quá trình sắp xếp thông thường vẫn cần xem toàn bộ bản ghi. Không được suy từ `limit(10)` rằng buffer trước nó có kích thước tối đa 10.

Nếu chỉ cần **một phần tử nhỏ nhất**, dùng:

```java
Optional<Sale> cheapest = sales.stream()
        .min(Comparator.comparingLong(Sale::getCents));
```

`min` là phép reduction cần trạng thái rất nhỏ, không cần dựng List đã sắp xếp. Nếu có nhiều bản ghi cùng giá, hãy xác định tie-breaker (ví dụ mã đơn) để lựa chọn là ổn định theo nghiệp vụ.

Nếu cần **top-K** bản ghi nhỏ nhất với `K` rất nhỏ so với `n`, thuật toán dùng heap giới hạn `K` có thể chỉ cần bộ nhớ bổ sung **`O(K)`**, với chi phí thời gian thường **`O(n log K)`**. Java Stream `sorted().limit(K)` không tự cam kết thực hiện một thuật toán top-K có bộ nhớ giới hạn như vậy.

### 3.3. Thứ tự của filter và sorted rất quan trọng

```java
// Lọc trước: chỉ sắp xếp các phần tử thỏa điều kiện.
List<Sale> activeSorted = sales.stream()
        .filter(Sale::isActive)
        .sorted(Comparator.comparingLong(Sale::getCents))
        .collect(Collectors.toList());

// Sắp xếp trước: có thể phải giữ toàn bộ nguồn để sắp xếp.
List<Sale> sameContent = sales.stream()
        .sorted(Comparator.comparingLong(Sale::getCents))
        .filter(Sale::isActive)
        .collect(Collectors.toList());
```

Khi predicate không có side effect và comparator hợp lệ, hai pipeline có thể cho cùng tập phần tử theo thứ tự giá (với các ràng buộc ổn định/tie-breaker phù hợp). Tuy nhiên, pipeline đầu tiên có thể giảm `n` của phép sắp xếp từ số bản ghi gốc xuống số bản ghi `active`.

Đừng đổi thứ tự thao tác một cách máy móc nếu predicate phụ thuộc vào vị trí/nguồn hoặc có yêu cầu đặc biệt về thứ tự; tốt nhất là giữ các hàm thuần và kiểm tra tương đương kết quả.

### 3.4. sorted trên nguồn vô hạn hoặc song song

- Với Stream vô hạn không có điểm kết thúc, việc yêu cầu **toàn bộ dãy sắp xếp** thường không thể hoàn tất. Ví dụ `Stream.generate(...).sorted().findFirst()` không phải cách an toàn để tìm cực tiểu của nguồn vô hạn.
- Với **parallel stream**, `sorted` có thể cần các buffer/mảng và giai đoạn hợp nhất bổ sung. Độ phức tạp vẫn thường ở bậc `O(n)`, nhưng **hằng số và đỉnh bộ nhớ** có thể tăng.
- Nếu nguồn đã có đặc tính `SORTED` đúng với kiểu sắp xếp cần thiết, một số đường thực thi có thể tránh làm công việc thừa. Không dựa vào điều đó khi lập ngân sách bộ nhớ cho nguồn chưa biết.
- `sorted().count()` hoặc những pipeline chỉ cần thông tin số lượng có thể được tối ưu hóa mà không thực sự sắp xếp mọi phần tử. **Chỉ phân tích buffer sắp xếp khi kết quả ngữ nghĩa thật sự đòi hỏi thứ tự sắp xếp được tạo ra**.

## 4. distinct: giữ thông tin đã gặp theo số giá trị phân biệt

`distinct()` loại trùng theo `Object.equals` (và các cấu trúc băm thường phụ thuộc `hashCode`). Với nguồn không được bảo đảm sắp xếp theo giá trị, để biết phần tử hiện tại đã xuất hiện chưa, implementation thường giữ **một tập các phần tử hoặc khóa đã thấy**.

```java
List<String> skus = Arrays.asList(
        "P01", "P02", "P01", "P03", "P02");

List<String> unique = skus.stream()
        .distinct()
        .collect(Collectors.toList());

System.out.println(unique); // [P01, P02, P03]
```

Nếu có `n` dòng nhưng chỉ `u` SKU phân biệt, **trạng thái cho phát hiện trùng thường tăng theo `u`**, không phải cứ bằng `n`. Tuy nhiên, trường hợp xấu nhất `u = n` nên `distinct` có thể cần bộ nhớ tăng tuyến tính theo toàn bộ nguồn.

### 4.1. Ước lượng hash table

Với giả định minh họa:

- `n = 1_000_000` mã SKU.
- `u = 100_000` mã SKU phân biệt.
- JVM dùng tham chiếu 4 byte, cấu trúc tương tự `HashMap` hoặc `HashSet`.

Một bảng băm thường có:

1. **Mảng bucket** với dung lượng lớn hơn số phần tử theo hệ số tải và quy tắc mở rộng.
2. **Node/entry** cho những phần tử phân biệt được giữ.
3. Tham chiếu tới **key** và đôi khi các đối tượng key thực tế nếu chúng vừa được tạo ra.

Ví dụ mang tính **minh họa**, nếu một node chiếm khoảng 32 byte:

\[
100\,000 \times 32 \approx 3{,}2\ \text{MB}
\]

Đây chỉ là phần node giả định, **chưa có mảng bucket, key String hoặc các overhead khác**. Kích thước đối tượng thực tế phụ thuộc phiên bản JVM, cách căn chỉnh, loại collection, cấu hình heap và dữ liệu.

### 4.2. Sự khác biệt giữa u và n quyết định lợi ích

| Dữ liệu | `n` | `u` | Diễn giải |
|---|---:|---:|---|
| Một triệu giao dịch thuộc 100 SKU | 1.000.000 | 100 | Bộ nhớ trạng thái phân biệt có thể nhỏ so với nguồn |
| Một triệu giao dịch có SKU riêng | 1.000.000 | 1.000.000 | Tập đã gặp có thể lớn gần bằng số phần tử |
| Mười nghìn giá trị, đều bằng nhau | 10.000 | 1 | Trạng thái phân biệt rất nhỏ |
| Nguồn chưa biết cardinality | Chưa biết | Chưa biết | Không thể lập ngân sách chỉ bằng `n` nếu chưa khảo sát phân bố |

**Lưu ý:** nếu mapper tạo String mới cho mỗi bản ghi trước `distinct`, những String tạm đó cũng có chi phí cấp phát/GC. `distinct` có thể chỉ giữ đại diện của các giá trị phân biệt, nhưng vẫn phải xử lý các giá trị ứng viên đã tạo.

### 4.3. distinct trên nguồn đã sorted

Trên một dãy **đã sắp xếp theo thứ tự phù hợp với khái niệm trùng lặp**, các bản ghi trùng nhau thường nằm liền nhau. Một thuật toán quét tuần tự có thể chỉ cần ghi nhớ phần tử trước để loại trùng. Một số implementation có thể khai thác đặc tính `SORTED`.

Tuy vậy, **không được khẳng định mọi `sorted(comparator).distinct()` trong mọi JDK đều dùng `O(1)` trạng thái distinct**. Comparator có thể không nhất quán với `equals`; đặc tính nguồn, thứ tự và chiến lược implementation ảnh hưởng cách tối ưu. Hãy coi `O(u)` là giả định thận trọng cho nguồn tổng quát.

### 4.4. distinct và xử lý song song

Với parallel stream **có encounter order**, `distinct` phải giữ bản ghi đại diện tương ứng **lần gặp đầu** của giá trị, có thể cần điều phối, lưu trữ và hợp nhất dữ liệu giữa các nhánh. Với Stream unordered, framework có nhiều tự do hơn và có thể dùng kỹ thuật bảng băm đồng thời.

```java
Set<String> uniqueSkus = sales.parallelStream()
        .map(Sale::getSku)
        .unordered()
        .collect(Collectors.toSet());
```

Nếu mục tiêu **chỉ là một Set SKU**, pipeline trên có thể **không cần `distinct()` riêng**: `toSet()` đã loại trùng. `unordered()` chỉ hợp lệ khi nghiệp vụ không quan tâm encounter order. Đừng bỏ thứ tự nếu cần “SKU xuất hiện đầu theo nguồn”.

## 5. groupingBy: bộ nhớ phụ thuộc số nhóm VÀ downstream

`Collectors.groupingBy(classifier, downstream)` tạo `Map<K, D>`. Chi phí bộ nhớ không chỉ là “có `k` khóa” mà còn phụ thuộc loại dữ liệu `D` được tích lũy trong mỗi nhóm.

```java
Map<String, Long> countByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.counting()));
```

Nếu có một triệu bản ghi nhưng chỉ năm khu vực, kết quả chỉ cần một Map khoảng năm khóa, mỗi khóa có số đếm. Chi phí trạng thái giữ lại về mặt cấu trúc thường **`O(k)`**, không phải `O(n)`.

### 5.1. groupingBy với counting

```java
Map<String, Long> countBySku = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getSku,
                Collectors.counting()));
```

Kết quả chứa một bộ đếm trên mỗi SKU. Ở mức **bộ nhớ giữ lại**, đây thường là `O(k)`. Tuy nhiên, cách một collector đếm triển khai phép cập nhật có thể phát sinh **đối tượng tạm** hoặc boxing; vì vậy **số byte được cấp phát trong suốt quá trình** có thể cao hơn nhiều kích thước Map cuối.

Nếu mục tiêu tính tổng một trường số:

```java
Map<String, Long> centsByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.summingLong(Sale::getCents)));
```

`summingLong` giữ trạng thái tổng nhỏ cho mỗi nhóm. Lưu ý tổng `long` có thể tràn; chọn kiểu số và chính sách tràn thích hợp khi dữ liệu lớn.

### 5.2. groupingBy với toList

```java
Map<String, List<Sale>> salesByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.toList()));
```

Giả sử toàn bộ `n` bản ghi đều thuộc một trong `k` nhóm. Khi đó:

\[
\sum_{i=1}^{k} |\text{list}_i| = n
\]

Vì vậy, bộ nhớ cho kết quả bao gồm:

- Map có khoảng `k` entry.
- Khoảng `k` đối tượng List và mảng backing của từng List.
- **Tổng cộng `n` tham chiếu tới các bản ghi `Sale`** (chưa tính capacity dư).
- Các đối tượng `Sale` gốc, nếu chúng vẫn còn sống do List/Map tham chiếu.

Mức bộ nhớ **giữ lại** cho cấu trúc thường `O(k+n)`. Nếu `n = 1_000_000` và tham chiếu 4 byte, **chỉ các tham chiếu trong các List** đã vào khoảng **4 MB**, chưa tính các cấu trúc khác.

**Dữ liệu không được nhân đôi về mặt object một cách mặc định**: List nhóm có thể giữ các tham chiếu tới `Sale` gốc, chứ không nhất thiết clone một triệu đối tượng. Dù vậy, nó giữ các đối tượng gốc **không được GC** chừng nào kết quả còn tham chiếu.

### 5.3. groupingBy với mapping/toSet

```java
Map<String, Set<String>> skusByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.mapping(
                        Sale::getSku,
                        Collectors.toSet())));
```

Nếu nhóm thứ `i` có `u_i` SKU phân biệt, trạng thái giữ lại thường vào bậc:

\[
O\left(k + \sum_{i=1}^{k}u_i\right)
\]

Cùng một SKU xuất hiện ở hai khu vực sẽ thường có **hai vị trí thành viên Set**, mỗi khu vực một vị trí. Nếu mục tiêu là một Set SKU **toàn hệ thống**, dùng `map(Sale::getSku).collect(toSet())` có thể cần ít cấu trúc hơn.

### 5.4. groupingBy nhiều tầng

```java
Map<String, Map<String, Long>> counts =
        sales.stream().collect(
                Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.groupingBy(
                                Sale::getSku,
                                Collectors.counting())));
```

Ở đây có Map tầng ngoài theo khu vực và Map con theo SKU cho **mỗi** khu vực. Ước lượng theo số cặp khóa thực sự xuất hiện, không chỉ số SKU toàn cục:

\[
O\left(k_{\text{region}} +
\#\{(\text{region},\text{sku})\text{ xuất hiện}\}\right)
\]

Nếu hai tiêu chí phân nhóm gần như duy nhất cho từng phần tử, số cặp có thể tiến gần `n`. Nếu nhiều bản ghi lặp các cặp, số cặp có thể rất nhỏ.

### 5.5. groupingBy không tự tạo nhóm không có phần tử

Nếu một khu vực không xuất hiện trong nguồn, `groupingBy` không tự tạo khóa cho khu vực đó. Nếu dữ liệu đã được `flatMap` từ đơn hàng sang dòng chi tiết, đơn không có dòng có thể **không còn được đếm**. Đây là một vấn đề **ngữ nghĩa**, không chỉ bộ nhớ. Không tối ưu bằng cách bỏ các nhóm cần thiết cho báo cáo.

## 6. collect: không có một mức độ phức tạp bộ nhớ chung

`collect` là thao tác kết thúc. Bộ nhớ phụ thuộc vào **Collector** mà chương trình đưa vào:

| Collector / terminal | Ý nghĩa dữ liệu | Bộ nhớ kết quả/trạng thái thường gặp |
|---|---|---|
| `toList()` / `toCollection(ArrayList::new)` | Giữ mọi phần tử | `O(n)` tham chiếu và collection |
| `toSet()` | Giữ phần tử phân biệt | `O(u)` entry/bucket và key |
| `toMap(key, value, merge)` | Giữ một giá trị mỗi khóa | `O(k)` nếu value nhỏ; hơn nếu value phức tạp |
| `counting()` | Số phần tử | `O(1)` cho một collector độc lập |
| `summingLong(...)` | Tổng một trường | `O(1)` |
| `averagingDouble(...)` | Trung bình | `O(1)` trạng thái số học |
| `summarizingLong(...)` | Count/sum/min/max/avg | `O(1)` |
| `joining(delimiter)` | Một String kết quả | Ít nhất tỷ lệ theo tổng chiều dài đầu ra `L` |
| `groupingBy(key, downstream)` | Một kết quả mỗi nhóm | `O(k)` cộng trạng thái downstream |
| Collector tùy biến | Do `supplier`/`accumulator`/`combiner` quyết định | Phải phân tích trạng thái tự thiết kế |

### 6.1. collect(toList) và toList không phải “streaming ra List” với O(1) RAM

```java
List<String> names = source.stream()
        .map(Person::getName)
        .collect(Collectors.toList());
```

Khi terminal operation kết thúc, danh sách phải giữ tất cả `n` giá trị tên được trả về. Nếu mapper tạo một String mới, List còn giữ cả những String đó. `map` có thể xử lý từng phần tử một, nhưng **terminal collector quyết định kích thước kết quả**.

Từ Java 16 có `Stream.toList()`, trả List không sửa được; **đổi API không biến đầu ra n phần tử thành O(1) bộ nhớ**. Nếu caller cần List mutable, phải chọn contract phù hợp, ví dụ `Collectors.toCollection(ArrayList::new)`.

### 6.2. collect(toMap): khóa nhỏ, giá trị lớn

```java
Map<String, List<Sale>> bySku = sales.stream()
        .collect(Collectors.groupingBy(Sale::getSku));
```

Map có thể chỉ vài chục khóa, nhưng **mỗi value là một List chứa các bản ghi**. Không được ước lượng `O(k)` chỉ từ kích thước Map. Với một Map có giá trị là cấu trúc lồng nhau, cần tính:

\[
B_{\text{map result}}
\;\approx\;
B_{\text{map structure}}
\;+\;\sum_{\text{key}} B_{\text{value(key)}}
\]

Nếu thay value List bằng số đếm/tổng, bộ nhớ giữ lại có thể giảm rất lớn, nhưng bạn cũng **mất khả năng truy cập từng bản ghi** trong báo cáo. Đây là lựa chọn theo mục tiêu nghiệp vụ, không chỉ một tối ưu kỹ thuật.

### 6.3. collectingAndThen, teeing và các finisher

`Collectors.collectingAndThen(downstream, finisher)` thường có bộ nhớ phụ thuộc `downstream`. Finisher có thể tạo **bản sao** hoặc sắp xếp kết quả, làm tăng bộ nhớ đỉnh:

```java
List<String> immutable = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> Collections.unmodifiableList(list)));
```

Ví dụ này tạo **view không sửa được** trên List đã thu thập, không tự bảo đảm một bản sao dữ liệu mới. Nếu finisher dùng `new ArrayList<>(list)` hoặc `List.copyOf(list)`, có thể cần thêm bộ nhớ trong lúc tạo bản sao. `List.copyOf` có từ Java 10 và từ chối phần tử null.

`Collectors.teeing` (Java 12+) dùng hai downstream collector trên cùng dữ liệu; bộ nhớ tích lũy phụ thuộc **cả hai trạng thái** và phép merger cuối, không thể mặc định `O(1)` nếu một nhánh giữ toàn bộ phần tử.

### 6.4. Collector tùy biến: phân tích từng field

Ví dụ accumulator tự viết:

```java
final class Stats {
    long count;
    long sum;
    long min = Long.MAX_VALUE;
    long max = Long.MIN_VALUE;
}
```

Nếu `supplier` tạo một `Stats`, `accumulator` chỉ cập nhật các trường đó, `combiner` gộp từng số, thì trạng thái cho **một collector** là `O(1)`. Nếu thêm `Map<String, Stats> bySku`, trạng thái sẽ tăng theo **số SKU `k`**. Nếu thêm `List<Sale> allSales`, trạng thái tăng theo **n**. Không có “độ phức tạp tự động” khi gọi `Collector.of(...)`.

## 7. Minh họa ngân sách bộ nhớ với một triệu bản ghi

Giả sử một dịch vụ có:

- `n = 1_000_000` bản ghi bán hàng trong một `ArrayList` có sẵn.
- `u = 100_000` SKU phân biệt.
- `k = 500` khu vực/nhóm phân loại.
- Tham chiếu 4 byte trên một JVM 64-bit được cấu hình phù hợp.
- Các đối tượng `Sale` đã tồn tại, **không tính kích thước bản thân chúng vào cột tăng thêm**.

| Phương án | Phần có thể phải giữ thêm | Ước lượng ban đầu |
|---|---|---|
| `sales.stream().count()` | Một counter hoặc tối ưu kích thước nguồn | Rất nhỏ so với `n` |
| `sales.stream().min(cmp)` | Một ứng viên cực trị và comparator | Rất nhỏ so với `n` |
| `sales.stream().sorted(cmp).toList()` | Buffer sort `O(n)` + List kết quả `O(n)` | Mỗi **một triệu tham chiếu** đã khoảng **4 MB**, có thể có nhiều vùng đệm |
| `sales.stream().map(Sale::getSku).distinct().toList()` | Thông tin `u` giá trị + List `u` tham chiếu | Hash state lớn hơn nhiều chỉ một mảng `u × 4` |
| `groupingBy(region, counting())` | Map `k` khóa, trạng thái đếm | Tăng chủ yếu theo `k = 500` |
| `groupingBy(region, toList())` | Map `k` và tổng cộng `n` tham chiếu List | Ít nhất nhiều MB chỉ cho backing arrays |
| `groupingBy(sku, summingLong(...))` | Map khoảng `u` khóa và tổng | Tăng theo `u = 100_000` |

**Không dùng bảng này để cam kết số MB cụ thể khi triển khai.** Bảng chỉ xác định **thành phần chi phối**. Việc đổi JVM flags, loại tham chiếu, kích thước String, bảng băm, số lần resize, cách chia nhánh và giới hạn heap có thể làm số thực đo khác đáng kể.

### 7.1. Phép tính thô cho tham chiếu

\[
B_{\text{refs}} \approx m \times B_{\text{ref}}
\]

Ví dụ, với `m = 1_000_000`:

- `B_ref = 4` byte: **4.000.000 byte ≈ 3,81 MiB**.
- `B_ref = 8` byte: **8.000.000 byte ≈ 7,63 MiB**.

Đây là **phần mảng tham chiếu giả định**, chưa cộng header, capacity dư, bảng băm hay đối tượng được tham chiếu. Nhầm **MB** (10^6 byte) với **MiB** (2^20 byte) cũng có thể làm kết quả dự toán chênh lệch.

### 7.2. Công thức sơ bộ cho groupingBy(toList)

Nếu mỗi `Sale` đã tồn tại và chỉ tính cấu trúc Map/List bổ sung:

\[
B \approx B_{\text{map buckets}}
 + k \cdot B_{\text{map entry}}
 + \sum_{i=1}^{k}
   \bigl(B_{\text{list object},i}
   + \text{capacity}_i \cdot B_{\text{ref}}\bigr)
\]

Vì `\sum_i \text{size}_i = n` nhưng `capacity_i` có thể lớn hơn `size_i`, số byte backing arrays thường **lớn hơn hoặc bằng** `n × B_ref`. Nếu result được giữ lâu trong cache, nó cũng giữ các đối tượng `Sale` tồn tại lâu theo.

## 8. Ví dụ Java 8 hoàn chỉnh: so sánh kích thước kết quả

Chương trình sau tự sinh dữ liệu để có thể chạy mà không cần file ngoài. Mục tiêu là **quan sát cardinality và hình dạng kết quả**, không phải dùng số liệu console thay thế profiler.

Lưu thành `StreamMemoryEstimationDemo.java` và chạy bằng JDK 8 trở lên:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Optional;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class StreamMemoryEstimationDemo {
    static final class Sale {
        private final int id;
        private final String region;
        private final String sku;
        private final long cents;
        private final boolean active;

        Sale(int id, String region, String sku,
                long cents, boolean active) {
            this.id = id;
            this.region = region;
            this.sku = sku;
            this.cents = cents;
            this.active = active;
        }

        int getId() { return id; }
        String getRegion() { return region; }
        String getSku() { return sku; }
        long getCents() { return cents; }
        boolean isActive() { return active; }
    }

    // Tìm K bản ghi nhỏ nhất bằng max-heap giới hạn K.
    // Ví dụ minh họa có k > 0 và nguồn là List có sẵn.
    static List<Sale> smallestK(
            List<Sale> source,
            int k,
            Comparator<Sale> ascending) {
        if (k <= 0) {
            throw new IllegalArgumentException("k phải dương");
        }
        PriorityQueue<Sale> heap =
                new PriorityQueue<>(k, ascending.reversed());

        for (Sale sale : source) {
            if (heap.size() < k) {
                heap.offer(sale);
            } else if (ascending.compare(sale, heap.peek()) < 0) {
                heap.poll();
                heap.offer(sale);
            }
        }

        List<Sale> result = new ArrayList<>(heap);
        result.sort(ascending);
        return result;
    }

    public static void main(String[] args) {
        final int n = 100_000;
        final String[] regions = {
                "BAC", "NAM", "TRUNG", "TAY"
        };
        final String[] skus = IntStream.range(0, 100)
                .mapToObj(i -> "SKU-" + i)
                .toArray(String[]::new);

        List<Sale> sales = IntStream.range(0, n)
                .mapToObj(i -> new Sale(
                        i,
                        regions[i % regions.length],
                        skus[i % skus.length],
                        (long) (i % 500) * 100L,
                        i % 5 != 0))
                .collect(Collectors.toList());

        Comparator<Sale> byCentsThenId =
                Comparator.comparingLong(Sale::getCents)
                        .thenComparingInt(Sale::getId);

        // A. sorted().limit(5): 5 kết quả, nhưng sort có thể
        // phải đệm n phần tử trước khi trả về.
        List<Sale> fiveSorted = sales.stream()
                .sorted(byCentsThenId)
                .limit(5)
                .collect(Collectors.toList());

        // B. Min: chỉ cần một ứng viên cực trị.
        Optional<Sale> oneMin = sales.stream()
                .min(byCentsThenId);

        // C. Top-K bằng heap: chỉ giữ tối đa K ứng viên,
        // không cần sắp xếp toàn bộ n phần tử.
        List<Sale> fiveHeap = smallestK(
                sales, 5, byCentsThenId);

        // D. distinct: chỉ trả 100 SKU phân biệt.
        List<String> uniqueSkus = sales.stream()
                .map(Sale::getSku)
                .distinct()
                .collect(Collectors.toList());

        // E. groupingBy + counting: giữ bốn số đếm.
        Map<String, Long> counts = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.counting()));

        // F. groupingBy + toList: giữ n tham chiếu bản ghi.
        Map<String, List<Sale>> allByRegion = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.toList()));

        // G. groupingBy + summingLong: chỉ giữ tổng của nhóm.
        Map<String, Long> totals = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.summingLong(Sale::getCents)));

        // H. LongSummaryStatistics: một đối tượng thống kê
        // thay cho việc giữ mọi giá trị cents.
        LongSummaryStatistics stats = sales.stream()
                .collect(Collectors.summarizingLong(
                        Sale::getCents));

        int keptInGroupLists = allByRegion.values().stream()
                .mapToInt(List::size)
                .sum();

        System.out.println("source size      = " + sales.size());
        System.out.println("sorted top 5     = " + fiveSorted.size());
        System.out.println("heap top 5       = " + fiveHeap.size());
        System.out.println("same top 5 IDs   = "
                + IntStream.range(0, 5).allMatch(i ->
                        fiveSorted.get(i).getId()
                                == fiveHeap.get(i).getId()));
        System.out.println("min ID           = "
                + oneMin.orElseThrow(IllegalStateException::new)
                        .getId());
        System.out.println("distinct SKUs    = " + uniqueSkus.size());
        System.out.println("region count     = " + counts.size());
        System.out.println("grouped references = "
                + keptInGroupLists);
        System.out.println("grouped totals keys = "
                + totals.size());
        System.out.println("statistics count = "
                + stats.getCount());
    }
}
```

**Kết quả chính cần quan sát:**

```text
source size      = 100000
sorted top 5     = 5
heap top 5       = 5
same top 5 IDs   = true
min ID           = 0
distinct SKUs    = 100
region count     = 4
grouped references = 100000
grouped totals keys = 4
statistics count = 100000
```

Chương trình không in “sorted dùng X MB” vì những con số ấy cần được **đo trong runtime thực tế**. Nó chứng minh một sự khác biệt quan trọng: hai kết quả `Map` cùng có **4 khóa** nhưng `groupingBy(counting())` giữ bốn số đếm, còn `groupingBy(toList())` giữ **100.000 tham chiếu bản ghi** trong các List.

### 8.1. Phân tích smallestK

`PriorityQueue` trong ví dụ được cấu hình thành **max-heap** theo comparator tăng dần, để phần tử **lớn nhất trong K ứng viên hiện có** ở đầu heap. Với bản ghi mới:

1. Nếu heap chưa đủ K phần tử, thêm vào.
2. Nếu heap đã đủ và bản ghi mới **nhỏ hơn** phần tử lớn nhất đang giữ, loại phần tử lớn nhất rồi thêm bản ghi mới.
3. Sau cùng, sắp xếp K ứng viên còn lại để trả theo thứ tự tăng dần.

Độ phức tạp bộ nhớ phụ thêm thường **`O(K)`** cho heap và List kết quả; thời gian **`O(n log K + K log K)`**. Kết quả bằng `sorted(...).limit(K)` nếu comparator xác định thứ tự đầy đủ nhất quán (ví dụ có `id` để phá hòa) và không có trường hợp null không được xử lý.

### 8.2. Nguồn dữ liệu cũng chiếm bộ nhớ

Ở chương trình này, `sales` có 100.000 đối tượng `Sale` được tạo **trước** các phép Stream. Chúng và mảng tham chiếu gốc vẫn chiếm heap trong lúc chương trình chạy. Khi profiler ghi tổng heap sử dụng, đó không phải toàn bộ là chi phí của `sorted`, `distinct` hay collector.

Để phân biệt chi phí, cần đo **allocation**, **retained size** và **peak live set** theo từng giai đoạn; không chỉ nhìn một con số `Runtime.totalMemory() - Runtime.freeMemory()` ở cuối chương trình.

## 9. Ảnh hưởng của thứ tự pipeline tới bộ nhớ

Hai pipeline cùng nội dung nghiệp vụ có thể dùng bộ nhớ rất khác nhau khi thay thứ tự các phép toán.

### 9.1. filter trước sorted

```java
// Chỉ sắp xếp những bản ghi đang hoạt động.
List<Sale> a = sales.stream()
        .filter(Sale::isActive)
        .sorted(byCentsThenId)
        .collect(Collectors.toList());

// Sắp xếp tất cả bản ghi rồi mới bỏ bản ghi không hoạt động.
List<Sale> b = sales.stream()
        .sorted(byCentsThenId)
        .filter(Sale::isActive)
        .collect(Collectors.toList());
```

Nếu predicate thuần và comparator có tie-breaker xác định, kết quả có thể tương đương; nhưng pipeline đầu chỉ đưa các bản ghi active vào buffer sắp xếp, trong khi pipeline sau có thể đưa mọi bản ghi vào buffer.

### 9.2. distinct trước sorted

```java
List<String> a = sales.stream()
        .map(Sale::getSku)
        .distinct()
        .sorted()
        .collect(Collectors.toList());

List<String> b = sales.stream()
        .map(Sale::getSku)
        .sorted()
        .distinct()
        .collect(Collectors.toList());
```

Với `String` và thứ tự tự nhiên, hai pipeline trả cùng danh sách SKU phân biệt tăng dần. Tuy nhiên:

- Cách A có thể chỉ cần **sắp xếp `u` SKU** sau khi loại trùng, nhưng vẫn cần trạng thái phân biệt.
- Cách B có thể phải **sắp xếp `n` giá trị** trước, dù kết quả cuối chỉ có `u` SKU.

Khi `u ≪ n`, việc loại trùng **trước** sắp xếp thường đáng cân nhắc về lượng dữ liệu vào sort. Tuy nhiên, với dữ liệu mà equality và comparator không nhất quán, hoặc khi yêu cầu giữ bản ghi đại diện cụ thể, không được đổi thứ tự pipeline mà bỏ kiểm tra ngữ nghĩa.

### 9.3. groupingBy trước và sau map

```java
// Giữ Sale trong List của mỗi nhóm.
Map<String, List<Sale>> detailed = sales.stream()
        .collect(Collectors.groupingBy(Sale::getRegion));

// Chỉ giữ số lượng theo nhóm.
Map<String, Long> summary = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.counting()));
```

Phương án `summary` thường giữ ít bộ nhớ hơn vì **không cần giữ các tham chiếu tới từng Sale trong kết quả**. Nhưng nếu báo cáo cần xem lại từng giao dịch của mỗi khu vực, summary không đáp ứng đủ nghiệp vụ.

## 10. Parallel stream: nhân lên trạng thái trung gian ra sao?

Khi gọi `parallel()`, framework có thể chia nguồn bằng `Spliterator`, tích lũy trên nhiều nhánh và gộp kết quả. Tác động bộ nhớ phụ thuộc từng phép toán:

| Phép toán | Rủi ro bộ nhớ khi song song |
|---|---|
| `sorted` | Các buffer/mảng hỗ trợ sắp xếp và hợp nhất có thể làm tăng bộ nhớ đỉnh |
| `distinct` | Tập phần tử phân biệt, cấu trúc kết hợp hoặc cơ chế bảo toàn thứ tự có thể tốn thêm |
| `groupingBy` | Nhiều Map trung gian có thể đồng thời tồn tại trước khi combiner gộp |
| `groupingByConcurrent` | Có thể giảm nhu cầu gộp nhiều Map trong một số trường hợp, nhưng có contention và cấu trúc concurrent |
| `toList` | Có thể có nhiều buffer/collection cục bộ trước khi tạo kết quả cuối |
| `count` / `sum` | Trạng thái của từng nhánh nhỏ, nhưng vẫn có overhead quản lý task |

### 10.1. Không lấy số thread làm số accumulator chính xác

Nếu có `p` container trung gian, mỗi container giữ khoảng `k` entry Map, chi phí **trạng thái sao lặp ở các nhánh** có thể lên tới bậc `O(p × k)` cho phần cấu trúc nhóm trong mô hình xấu. Tuy nhiên, **`p` không nhất thiết bằng số thread**: framework có thể tạo nhiều tác vụ/nhánh hơn worker, và mỗi nhánh thường chỉ có phần dữ liệu riêng của mình.

Với `groupingBy(toList())`, tổng số tham chiếu phần tử qua các container cục bộ vẫn liên quan tới `n` trước khi gộp, nhưng lúc combiner hợp nhất có thể tồn tại **mảng/danh sách tạm hoặc capacity dư**, làm tăng đỉnh bộ nhớ.

### 10.2. Collector concurrent không tự động tiết kiệm RAM

```java
ConcurrentMap<String, Long> counts = sales.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Sale::getRegion,
                Collectors.counting()));
```

`groupingByConcurrent` có thể cho phép nhiều worker tích lũy vào cấu trúc concurrent trong các điều kiện phù hợp, giảm một số chi phí gộp Map trung gian. Nhưng nếu mọi phần tử thuộc cùng một khóa, contention có thể cao. Một concurrent map cũng có chi phí đồng bộ/cấu trúc riêng. **Không có bảo đảm** rằng nó dùng ít RAM hay chạy nhanh hơn `groupingBy`.

### 10.3. Trạng thái chia sẻ ngoài pipeline không phải tối ưu

```java
Map<String, List<Sale>> shared = new HashMap<>();

sales.parallelStream().forEach(sale ->
        shared.computeIfAbsent(
                sale.getRegion(), key -> new ArrayList<>())
                .add(sale));
// SAI: HashMap/ArrayList không an toàn khi nhiều worker cùng sửa.
```

Mục tiêu tiết kiệm “nhiều Map cục bộ” không biện minh cho data race. Hãy dùng collector có hợp đồng đúng, hoặc thiết kế một cơ chế concurrent an toàn và đo thực tế nếu thực sự cần.

## 11. Các yếu tố JVM làm dự toán byte khác thực tế

### 11.1. Header, căn chỉnh, boxing và kích thước tham chiếu

Một đối tượng không chỉ chứa dữ liệu của các field:

- Header và căn chỉnh đối tượng.
- Tham chiếu tới các object con.
- Mảng backing với header và capacity có thể lớn hơn `size()`.
- Entry/node của `HashMap`, `HashSet`, `TreeMap` và các collection khác.
- Wrapper như `Integer`, `Long` khi boxing hoặc giữ Map value.
- String và mảng nội dung, đôi khi được chia sẻ, đôi khi mới tạo bởi mapper.

Ví dụ `Collectors.toList()` có thể giữ một triệu **tham chiếu** tới đối tượng nguồn; nếu phía trước có `map(s -> new DTO(s))`, nó còn giữ một triệu **DTO mới**. Ước lượng chỉ từ `list.size()` mà bỏ qua object graph thường thấp hơn thực tế rất nhiều.

### 11.2. Hash table có capacity và load factor

Với `distinct`, `toSet`, `toMap` và `groupingBy`, số phần tử `u` hoặc `k` không bằng chính xác số bucket. Bảng băm thường mở rộng theo ngưỡng tải; resize có thể tạo mảng mới trong khi mảng cũ chưa được giải phóng ngay. Mức bộ nhớ đỉnh vì thế có thể **lớn hơn** bộ nhớ giữ lại của kết quả ổn định.

### 11.3. Cấp phát tích lũy khác bộ nhớ còn sống

Giả sử một triệu lần mapper tạo object tạm nhưng không giữ lại. **Tổng byte cấp phát** có thể rất lớn, trong khi heap còn sống cuối pipeline nhỏ. GC có thể dọn object tạm, nhưng việc cấp phát và thu gom vẫn tốn CPU và ảnh hưởng độ trễ.

Vì vậy cần phân biệt:

1. **Allocation rate / allocated bytes**: bao nhiêu byte đã được cấp phát.
2. **Peak live heap**: đỉnh lượng object còn sống.
3. **Retained size**: bao nhiêu object còn bị kết quả/nguồn tham chiếu.
4. **GC pause/throughput**: chi phí thu gom và ảnh hưởng tới hiệu năng.

Không tối ưu chỉ dựa vào một ảnh chụp bộ nhớ sau khi pipeline đã hoàn thành.

## 12. Cách đo kiểm bộ nhớ đáng tin cậy

### 12.1. Chọn một đường đo thực tế

Các công cụ thông dụng trong hệ sinh thái Java:

| Công cụ | Hữu ích để quan sát |
|---|---|
| **Java Flight Recorder (JFR)** | Allocation, GC, CPU, các sự kiện liên quan runtime |
| **Java Mission Control (JMC)** | Phân tích bản ghi JFR |
| **VisualVM** | Heap, class/instance và xu hướng sử dụng bộ nhớ |
| **Heap dump / công cụ phân tích heap** | Retained size, dominator tree và chuỗi tham chiếu giữ object |
| **JMH với GC profiler** | Benchmark vi mô, allocation rate và so sánh các phương án |

Với yêu cầu chặt về môi trường, phiên bản và kích thước, hãy ghi rõ JDK, tùy chọn VM, mức song song, GC, heap limit, phần cứng và dữ liệu đầu vào. Không so sánh một bản JDK có compressed references với cấu hình khác rồi coi chênh lệch hoàn toàn do Stream API.

### 12.2. Quy trình profiling từng phương án

1. **Định nghĩa kết quả đúng**: số phần tử, thứ tự, nhóm, doanh thu, min/max phải tương đương giữa các phương án.
2. **Giữ nguồn/fixture ổn định**: không tự ý thay phân bố `u`, `k` hoặc kích thước n giữa các phép đo.
3. **Đo từng pipeline riêng**: `sorted`, `distinct`, `groupingBy(counting)`, `groupingBy(toList)`, v.v.; tránh giữ kết quả của phép trước nếu không chủ đích đo đồng thời.
4. **Phân biệt nguồn đã có với bộ nhớ tăng thêm**: biết có bao nhiêu object nguồn được tạo trước khi đo.
5. **Đo cả allocation và retained heap**: theo dõi GC, peak live set và object nào được kết quả giữ.
6. **Thử nguồn tuần tự và song song** nếu hệ thống thực sự sử dụng cả hai.
7. **Lặp lại với `n`, `u`, `k` thay đổi**: tăng n gấp đôi nhưng giữ k, rồi tăng cả k để tìm yếu tố gây tăng bộ nhớ.
8. **Xác nhận tác động tài nguyên ngoài heap** nếu dữ liệu đến từ file, database hoặc network.

### 12.3. Vì sao Runtime.totalMemory - freeMemory chỉ là chỉ báo thô?

`Runtime.getRuntime().totalMemory() - freeMemory()` cho một ảnh chụp tại thời điểm gọi, chịu ảnh hưởng bởi vùng heap đã cam kết, thời điểm GC, thread khác và object tạm đã/chưa được thu gom. Nó không phản ánh đầy đủ **đỉnh trong khi sort**, vì bạn có thể đo sau khi buffer đã bị giải phóng.

Ngay cả việc gọi `System.gc()` cũng không tạo một phép đo chính xác, có thể không được runtime thực hiện như mong muốn và không nên nằm trong thuật toán sản xuất. Dùng profiler phù hợp thay vì công thức “trước/sau” duy nhất.

## 13. Chọn phương án theo bài toán nghiệp vụ

| Nhu cầu | Cách thường phù hợp | Lợi ích về bộ nhớ |
|---|---|---|
| Chỉ cần bản ghi rẻ nhất | `min(comparator)` | Tránh lưu danh sách sort đầy đủ |
| Cần K bản ghi nhỏ nhất, K nhỏ | Top-K với heap giới hạn | Giữ khoảng K ứng viên thay vì n |
| Chỉ cần số SKU phân biệt | `map(Sale::getSku).collect(toSet())` | Không cần `distinct().toList()` nếu chỉ cần Set |
| Cần đếm đơn theo khu vực | `groupingBy(region, counting())` | Giữ một bộ đếm mỗi khóa |
| Cần tổng tiền theo khu vực | `groupingBy(region, summingLong(...))` | Không giữ mọi đơn trong mỗi nhóm |
| Cần xem lại từng đơn của mỗi khu vực | `groupingBy(region, toList())` | Phải chấp nhận giữ tham chiếu tới từng đơn |
| Cần toàn bộ dữ liệu đã sắp xếp | `sorted(...).toList()` | Chấp nhận bộ nhớ tỷ lệ dữ liệu đầu ra/sort |
| Chỉ cần count/sum/min/max/avg | `summarizingLong(...)` | Một trạng thái thống kê nhỏ |
| Cần nhiều KPI cùng quy tắc phức tạp | Collector tùy biến có state tối thiểu | Tránh materialize dữ liệu không cần |

**Lựa chọn tốt nhất không phải luôn là phương án ít byte nhất.** Nếu cần xuất toàn bộ báo cáo chi tiết có thứ tự, một List lớn có thể là yêu cầu không tránh được. Ngược lại, nếu chỉ cần số đếm/tổng, giữ một triệu bản ghi trong Map các List để rồi tính `size()` là sự lãng phí có thể loại bỏ.

## 14. Những hiểu nhầm và lỗi thường gặp

| Nhận định hoặc cách làm | Vì sao không đúng | Cách sửa |
|---|---|---|
| “Stream lazy nên luôn O(1) RAM.” | `sorted`, `distinct`, collector giữ trạng thái | Phân tích cả intermediate và terminal |
| “`sorted().limit(5)` chỉ giữ 5 phần tử.” | Sắp xếp thường phải xét và đệm nhiều đầu vào | Dùng `min` hoặc thuật toán top-K nếu phù hợp |
| “`distinct` phải giữ toàn bộ n phần tử.” | Trạng thái thường tỷ lệ số giá trị phân biệt u | Đo u và chi phí hash table |
| “Map có 5 khóa nên groupingBy luôn nhỏ.” | Downstream `toList` có thể giữ n tham chiếu | Xem cấu trúc value ở từng nhóm |
| “`collect` luôn tốn O(n).” | `counting`, `summingLong` có state nhỏ | Phân loại theo Collector được chọn |
| “`toSet` luôn rẻ hơn `toList`.” | Hash table có bucket/node overhead | So theo u, n và yêu cầu semantics |
| “`parallel()` giúp giảm peak heap.” | Nhiều buffer/container có thể cùng tồn tại | Benchmark và profile parallel riêng |
| “`groupingByConcurrent` luôn nhanh và ít RAM hơn.” | Concurrent map có contention và overhead | So với groupingBy theo phân bố khóa thực tế |
| “Kích thước List là đủ để tính byte chính xác.” | Có header, capacity, object graph, boxing | Dùng mô hình rồi xác minh bằng profiler |
| “Có thể đổi List các giao dịch thành số đếm mà không ảnh hưởng API.” | Mất dữ liệu chi tiết | Bảo toàn hợp đồng nghiệp vụ |
| “Chỉ cần đo heap sau khi collect.” | Buffer sort và object tạm có thể đã hết sống | Đo allocation và peak live heap |
| “Đọc Files.lines rồi collect là file tự đóng.” | Terminal operation không thay `close` | Dùng `try-with-resources` |

## 15. Bài tập thực hành có đáp án

### Bài 1. Bộ nhớ sorted và limit

**Đề bài:** Một triệu đối tượng đi vào `sorted(comparator).limit(10).toList()`. Có thể kết luận trạng thái của `sorted` chỉ giữ mười phần tử không?

**Đáp án:** Không. Trên nguồn chưa được sắp xếp, sort thường cần xét và đệm toàn bộ dữ liệu liên quan trước khi biết mười phần tử đầu. Kết quả cuối có 10 phần tử nhưng **peak state** có thể tỷ lệ với một triệu. Nếu chỉ cần top-10, cân nhắc một thuật toán heap giới hạn 10.

### Bài 2. Distinct và cardinality

**Đề bài:** Có 500.000 dòng, trong đó chỉ có 200 SKU phân biệt. Trạng thái `distinct` nên được mô hình hóa theo 500.000 hay 200?

**Đáp án:** Với kỹ thuật bảng băm thông dụng, trạng thái giữ thông tin theo khoảng **`u = 200`** phần tử phân biệt, ngoài buffer/overhead khác. Không xem số 200 là số byte, vì mỗi entry còn có node, bucket và key. Nếu tất cả dòng có SKU khác nhau, `u` tiến tới `n`.

### Bài 3. Chọn downstream phù hợp

**Đề bài:** Một triệu đơn thuộc 4 khu vực. Báo cáo chỉ cần **số đơn theo khu vực**. Nên chọn `groupingBy(region, toList())` hay `groupingBy(region, counting())`?

**Đáp án:** `groupingBy(region, counting())`. Nó giữ Map bốn nhóm với số đếm thay vì giữ một triệu tham chiếu trong các List, nếu nghiệp vụ không yêu cầu lấy lại từng đơn.

### Bài 4. Tính thô mảng tham chiếu

**Đề bài:** Giả sử mỗi tham chiếu chiếm 4 byte. Một List cần mảng backing đúng 2.000.000 tham chiếu, chưa tính header/capacity dư. Riêng phần tham chiếu chiếm bao nhiêu?

**Đáp án:**

\[
2\,000\,000 \times 4
= 8\,000\,000\ \text{byte}
\approx 7{,}63\ \text{MiB}
\]

Đây không phải tổng heap của List hay của các object mà List tham chiếu.

### Bài 5. Sắp xếp trước hay loại trùng trước?

**Đề bài:** Có một triệu chuỗi SKU với chỉ 100 SKU phân biệt. Nếu cần danh sách SKU **phân biệt và tăng dần**, nên cân nhắc thứ tự nào?

**Đáp án:** `stream.distinct().sorted().toList()` thường làm sort chỉ nhận khoảng 100 giá trị phân biệt, thay vì sắp xếp một triệu chuỗi rồi mới loại trùng. Áp dụng khi equality và ordering của SKU đúng với ngữ nghĩa mong muốn.

### Bài 6. Parallel grouping và số Map

**Đề bài:** Vì sao `parallelStream().collect(groupingBy(region, counting()))` có thể có bộ nhớ đỉnh lớn hơn bản tuần tự?

**Đáp án:** Framework có thể tạo **nhiều Map và container tích lũy** trên các nhánh rồi gộp; các trạng thái có thể cùng tồn tại trong quá trình xử lý. Số container không đơn giản bằng số thread. `groupingByConcurrent` có chiến lược khác nhưng không tự bảo đảm ít RAM hơn.

### Bài 7. Retained heap và object tạm

**Đề bài:** Một pipeline tạo nhiều DTO trong `map`, sau đó chỉ đếm bằng `count()`. Khi kết thúc, bộ nhớ kết quả rất nhỏ. Có thể khẳng định pipeline đã không cấp phát nhiều object không?

**Đáp án:** Không. Nó **có thể** đã cấp phát nhiều DTO tạm, nhưng cũng có thể được tối ưu hóa để không cần thực thi mapper nếu kết quả đếm đã biết. Cần đo allocation thực tế; retained size nhỏ không chứng minh tổng cấp phát nhỏ.

### Bài 8. Tự đánh giá một báo cáo theo khóa

**Đề bài:** Một service chỉ cần tổng tiền theo SKU nhưng đang dùng `groupingBy(sku, toList())` rồi duyệt từng List để cộng tiền. Có thể giảm bộ nhớ thế nào?

**Đáp án:** Dùng `groupingBy(sku, summingLong(Sale::getCents))` nếu số học `long` phù hợp và không cần chi tiết giao dịch. Nếu phải phát hiện tràn số, thiết kế collector cộng bằng `Math.addExact` hoặc dùng kiểu số lớn hơn. Kết quả Map sẽ chứa một tổng mỗi SKU thay vì List các giao dịch.

### Bài 9. Phân biệt MB và MiB

**Đề bài:** Vì sao 4.000.000 byte không bằng 4 MiB?

**Đáp án:** `1 MB = 1.000.000 byte`, còn `1 MiB = 1.048.576 byte`. Do đó 4.000.000 byte bằng **4 MB** nhưng chỉ khoảng **3,81 MiB**. Phải ghi rõ đơn vị khi so ngân sách heap.

## 16. Checklist trước khi tối ưu bộ nhớ Stream

1. **Đã xác định bộ nhớ cần đo chưa?** Tổng heap, phần tăng thêm, đỉnh trong lúc chạy hay phần kết quả giữ lại?
2. **Biết `n`, `u`, `k` chưa?** Tập dữ liệu nhiều trùng lặp có đặc điểm khác nhiều khóa duy nhất.
3. **Có `sorted` không?** Có thật sự cần toàn bộ kết quả sắp xếp, hay chỉ min/top-K?
4. **Có `distinct` không?** Kết quả cần List giữ thứ tự hay chỉ một Set giá trị phân biệt?
5. **`groupingBy` đang dùng downstream nào?** `counting`, `summingLong`, `toList` hay `toSet` có bộ nhớ rất khác nhau.
6. **`collect` giữ lại bao nhiêu phần tử?** Nếu n kết quả phải tồn tại, không thể coi `map` lazy là đủ để O(1) RAM.
7. **Có giảm dữ liệu trước thao tác stateful được không?** Lọc đúng nghiệp vụ trước `sorted`, cân nhắc `distinct` trước `sorted`.
8. **Có tăng đối tượng tạm hoặc boxing không?** Đo allocation và GC, không chỉ retained heap.
9. **Có song song không?** Kiểm tra buffer, Map cục bộ, contention và chi phí combiner.
10. **Đã đo theo cấu hình JVM thực tế chưa?** Kích thước tham chiếu, header, load factor và GC khác nhau.
11. **Nguồn I/O có được đóng không?** Chi phí heap và file descriptor là hai vấn đề khác nhau.
12. **Mọi tối ưu có giữ nguyên kết quả đúng không?** Không bỏ các bản ghi, thứ tự hoặc khả năng truy vấn mà nghiệp vụ yêu cầu.

**Kết luận:** Khi ước lượng bộ nhớ Java Stream, đừng gán một độ phức tạp chung cho cả pipeline. **`sorted` thường cần trạng thái theo `n`**, **`distinct` thường theo `u`**, **`groupingBy` theo `k` cộng trạng thái downstream**, và **`collect` hoàn toàn phụ thuộc Collector cùng kích thước kết quả**. Phân biệt buffer trung gian, dữ liệu được giữ lại, đối tượng nguồn, allocation tạm và peak live heap; sau đó xác minh mô hình bằng profiling trên JVM và dữ liệu thật. Cách tiếp cận này giúp tối ưu có cơ sở mà không đánh đổi tính đúng hoặc những yêu cầu nghiệp vụ về thứ tự, chi tiết và tài nguyên.
