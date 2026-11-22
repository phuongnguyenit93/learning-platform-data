# ConcurrentHashMap.mappingCount và giới hạn quan sát kích thước

## 1. Mục tiêu: đếm mapping trong một map có nhiều luồng cập nhật

`java.util.concurrent.ConcurrentHashMap<K,V>` được dùng khi nhiều luồng cùng đọc và sửa một bảng ánh xạ khóa–giá trị. Một câu hỏi tưởng như đơn giản thường xuất hiện trong ứng dụng: **“Map hiện đang chứa bao nhiêu phần tử?”**

Có hai phương thức liên quan trực tiếp:

```java
int countAsInt = map.size();
long countAsLong = map.mappingCount();
```

Hai phương thức đều phản ánh **số lượng ánh xạ khóa–giá trị (mapping)** trong `ConcurrentHashMap`, nhưng khác ở miền số nguyên trả về. Quan trọng hơn, trong lúc các luồng đang thêm/xóa phần tử, đây **không phải ảnh chụp nhất quán** của toàn bộ map để dùng làm điều kiện điều khiển một thay đổi khác.

Bài này tập trung đúng chủ đề **“mappingCount và giới hạn quan sát kích thước”** thuộc mục **“ConcurrentHashMap”** của Java 8. Những API và cảnh báo sử dụng đều còn áp dụng trong JDK hiện đại; những nhận xét về cấu trúc dữ liệu bên trong sẽ được đánh dấu là **chi tiết triển khai**, không biến thành hợp đồng API.

Sau bài học bạn có thể:

1. Giải thích `mappingCount()` trả `long` còn `size()` trả `int`, và ý nghĩa của giới hạn `Integer.MAX_VALUE`.
2. Hiểu **“mapping” là số khóa được ánh xạ**, không phải số lần `put`, số request, số sự kiện hay tổng các counter ở giá trị.
3. Đọc đúng cảnh báo của Java API: khi có cập nhật đồng thời, `mappingCount` là **ước lượng**; các aggregate-status methods phản ánh trạng thái nhất thời.
4. Phân biệt một phép đọc kích thước đơn lẻ với **snapshot nhất quán** và một chuỗi thao tác **check-then-act nguyên tử**.
5. Viết được bài test đa luồng tái hiện chắc chắn lỗi kiểm tra quota bằng `mappingCount() < max` rồi `put`.
6. Lựa chọn cách thực thi điều kiện giới hạn cardinality có phối hợp; dùng atomic per-key operations đúng phạm vi.
7. Dùng `mappingCount` đúng cho thống kê/gauge và phân biệt với mẫu `ConcurrentHashMap<String,LongAdder>` cho histogram.
8. Hiểu vì sao duyệt `keySet`, `entrySet` hay đếm qua stream trong lúc map thay đổi **không tự tạo snapshot chính xác**.
9. Viết Java 17+ chạy được và đối chiếu stdout về các trạng thái ổn định, thay đổi số mapping, quota race, barrier và histogram.
10. Đưa ra quyết định rõ ràng khi một business rule **cần đúng tuyệt đối**, thay vì mặc định số đếm “có vẻ đúng” là đủ.

## 2. Định nghĩa chính thức của mappingCount

Trên `ConcurrentHashMap<K,V>`, API có phương thức:

```java
public long mappingCount()
```

Theo Javadoc Java hiện đại, nó trả số mapping hiện có; phương thức này nên được chọn thay cho `size()` khi số mapping **có thể vượt miền `int`**. **Giá trị trả về là một ước lượng**; kết quả thực tế có thể khác nếu có các thao tác chèn/xóa diễn ra đồng thời. Phương thức được cung cấp từ **Java 8**.

Hãy tách hai mệnh đề ra:

- **Miền dữ liệu:** `long` chứa được những số lớn hơn `int`, do đó có khả năng biểu diễn cardinality lớn hơn.
- **Tính nhất quán khi quan sát:** việc trả kiểu `long` **không biến kết quả thành một snapshot nguyên tử**. Khi concurrent updates còn tiếp diễn, số đọc được vẫn chỉ là ước lượng.

Đây là hai thuộc tính độc lập. Một phép đếm có kiểu dữ liệu rộng **không đồng nghĩa** một phép đếm có tính chính xác thời điểm cao hơn.

### 2.1. Vì sao không chỉ dùng size()?

`size()` có chữ ký:

```java
public int size()
```

Với `ConcurrentHashMap`, API quy định nếu map chứa **nhiều hơn `Integer.MAX_VALUE` mapping**, `size()` trả lại **`Integer.MAX_VALUE`**, tức `2_147_483_647`, thay vì thể hiện số thực bằng một `int` không đủ chỗ.

Điều này khác với `mappingCount()`, vốn trả `long`. Nhưng không có nghĩa ứng dụng nên cố tạo một map có hàng tỷ phần tử: memory, indexing và cấu trúc dữ liệu thực tế có các giới hạn khác. **Không cần cấp phát hàng tỷ phần tử để kiểm thử đặc tả này**; chỉ cần hiểu API contract.

Bảng so sánh:

| Đặc điểm | `size()` | `mappingCount()` |
| --- | --- | --- |
| Kiểu trả về | `int` | `long` |
| Nơi khai báo chính | `Map.size()` và override của `ConcurrentHashMap` | Phương thức của `ConcurrentHashMap` |
| Giá trị khi tổng mapping vượt `Integer.MAX_VALUE` | Trả `Integer.MAX_VALUE` theo đặc tả `ConcurrentHashMap` | Có thể biểu diễn số lớn hơn dưới dạng `long` |
| Khi không có cập nhật đồng thời | Có thể đọc số lượng mapping của map ổn định | Có thể đọc số lượng mapping của map ổn định |
| Khi các luồng đang thêm/xóa | Có thể phản ánh trạng thái nhất thời | **Ước lượng**; có thể khác số mapping thực tại thời điểm mong muốn |
| Có bảo đảm snapshot nhất quán của toàn map? | Không | Không |
| Có phù hợp làm điều kiện quota check-then-put? | Không, nếu thiếu phối hợp | Không, nếu thiếu phối hợp |
| Dùng làm gauge quan sát gần đúng? | Có, trong miền `int` | Có, thường hợp lý hơn khi cần `long` |

**Chọn `mappingCount` không phải để “sửa race của size”** mà để dùng một API có miền số phù hợp và một lời cảnh báo nhất quán rõ ràng.

### 2.2. size() là API của Map; mappingCount() không phải

`Map<K,V>` và `ConcurrentMap<K,V>` khai báo `size()` nhưng **không khai báo `mappingCount()`**. Vì thế:

```java
ConcurrentHashMap<String, Integer> concrete = new ConcurrentHashMap<>();
long n = concrete.mappingCount(); // Hợp lệ.
```

Nhưng biến được khai báo kiểu `Map<String,Integer>` hoặc `ConcurrentMap<String,Integer>` không gọi trực tiếp được `mappingCount()` tại compile time, dù runtime implementation có thể là ConcurrentHashMap.

Nếu API của bạn thực sự cần ý nghĩa `mappingCount`, có thể dùng kiểu cụ thể khi phù hợp hoặc thiết kế một interface quan sát riêng. **Không ép kiểu `(ConcurrentHashMap<?,?>)map` tùy tiện** khi chưa có bảo đảm về implementation.

## 3. “Mapping” thực chất đếm gì?

`ConcurrentHashMap` lưu quan hệ **mỗi khóa tới tối đa một giá trị tại một thời điểm**. Vì thế:

- `put("A",10)` vào map chưa có A: tạo **1 mapping**.
- `put("B",20)`: thêm một khóa mới: tổng **2 mapping**.
- `replace("A",11)`: chỉ cập nhật giá trị của khóa A: tổng vẫn **2 mapping**.
- `put("A",12)` khi A đã tồn tại: thay value, không tạo khóa thứ hai.
- `remove("B")`: xóa mapping của B: tổng còn **1 mapping**.
- `putIfAbsent("A",...)` khi A đã tồn tại: không tăng cardinality.
- `clear()` sau khi mọi writer dừng: map trống, count 0.

Ví dụ, khi không có writer khác:

```java
ConcurrentHashMap<String,Integer> map = new ConcurrentHashMap<>();
map.put("A", 10);
map.put("B", 20);

System.out.println(map.mappingCount()); // 2

map.replace("A", 11);
System.out.println(map.mappingCount()); // Vẫn 2.

map.remove("B");
System.out.println(map.mappingCount()); // 1.
```

Trong ví dụ này, mọi thao tác theo thứ tự trên một luồng và không có cập nhật đồng thời, nên các giá trị được dự đoán chính xác.

### 3.1. Không phải số thao tác put

Một map có cùng khóa bị `put` 10.000 lần vẫn có thể chỉ có **1 mapping**. `mappingCount` **không phải counter sự kiện** và không phải tổng số thao tác update từng xảy ra.

Nếu bạn cần thống kê “bao nhiêu request đã đến”, “bao nhiêu lần gọi API”, hay “bao nhiêu sự kiện Kafka đã xử lý”, phải có cơ chế ghi nhận **số sự kiện** riêng; không dùng cardinality của map thay thế.

### 3.2. ConcurrentHashMap không cho phép null key/value

`ConcurrentHashMap` **không cho phép `null` làm key hoặc value**. Vì thế:

```java
ConcurrentHashMap<String,Integer> map = new ConcurrentHashMap<>();
map.put("A", null);  // NullPointerException.
```

Đây là **đoạn cố ý gây lỗi**, không phải mẫu happy path. Kết quả `get(key) == null` được dùng để chỉ việc không có mapping tương ứng tại thời điểm đọc, nhưng không bảo đảm **một luồng khác không thể thêm mapping đó ngay sau đó**.

Nếu cần phân biệt dữ liệu “chưa tải”, “không có”, “lỗi”, nên dùng giá trị trạng thái có cấu trúc, không nhét null vào ConcurrentHashMap.

### 3.3. Một giá trị có thể là một đối tượng counter

Với:

```java
ConcurrentHashMap<String, LongAdder> events = new ConcurrentHashMap<>();

events.computeIfAbsent("java", k -> new LongAdder()).increment();
events.computeIfAbsent("java", k -> new LongAdder()).increment();
events.computeIfAbsent("kotlin", k -> new LongAdder()).increment();
```

map chứa **2 mapping** (hai khóa “java”, “kotlin”) nhưng đã đếm được **3 sự kiện**. `mappingCount() == 2`, trong khi hai giá trị `LongAdder` có tổng 2+1=3 tại lúc không có cập nhật đồng thời.

Đây là hai trục đo khác nhau:

```text
Số mapping       = số khóa hiện đang tồn tại = 2.
Số sự kiện java  = events.get("java").sum() = 2.
Số sự kiện kotlin= events.get("kotlin").sum() = 1.
Tổng sự kiện     = 3.
```

Mẫu `ConcurrentHashMap<String,LongAdder>` còn được đề cập trong Javadoc như cách làm một bảng tần suất có khả năng cập nhật đồng thời. Nhưng lưu ý `LongAdder.sum()` **không cung cấp snapshot nguyên tử** khi các thread đang tăng counter; nó hữu ích cho thống kê chấp nhận giá trị gần đúng trong lúc cập nhật.

## 4. ConcurrentHashMap thread-safe nhưng aggregate count không phải snapshot

Một câu dễ gây hiểu lầm là “ConcurrentHashMap thread-safe, vậy `mappingCount` chắc chắn là số phần tử chính xác trong một thời điểm”.

**Thread-safe không đồng nghĩa mọi phép tổng hợp đều linearizable như một giao dịch toàn map.**

`ConcurrentHashMap` cung cấp cơ chế an toàn cho những thao tác trên map trong môi trường đa luồng. Những thao tác gắn với một khóa có những bảo đảm riêng; ví dụ `putIfAbsent` là một thao tác nguyên tử đối với **mapping của khóa đó**.

Tuy nhiên, việc **quan sát số mapping của toàn map** là aggregate status. Javadoc lưu ý các phương thức như `size`, `isEmpty` và `containsValue` thường hữu ích nhất khi map **không đang chịu cập nhật đồng thời**. Khi đang thêm/xóa, chúng có thể phản ánh trạng thái nhất thời phù hợp để giám sát hoặc ước lượng, nhưng **không nên dùng làm logic điều khiển chương trình**.

### 4.1. Vì sao một map có thể đổi ngay sau khi đo?

Hãy tưởng tượng:

```text
Thread A                            Thread B
-----------------------------------------------------------
đọc mappingCount() -> 100
                                    put("new", value)
                                    hoàn tất cập nhật
in "Current count=100"
-----------------------------------------------------------
Map tại lúc in có thể chứa 101 mapping.
```

Ngay cả giả sử số `100` hoàn toàn chính xác **tại thời điểm Thread A đọc**, nó cũng **không còn chính xác cho một thời điểm sau đó**. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**, độc lập với cách triển khai bên trong của `mappingCount`.

### 4.2. Vì sao ngay trong lúc đếm cũng chỉ là ước lượng?

Trong một hệ thống có rất nhiều writer cùng sửa các khóa khác nhau, việc đòi một snapshot toàn map “cùng một thời điểm” cần cơ chế phối hợp mạnh hơn.

Không nên thiết kế thuật toán nghiệp vụ dựa vào giả định `mappingCount` có một **linearization point chung với mọi put/remove** hoặc cùng lúc khóa toàn map. Hợp đồng của phương thức đã gọi rõ nó là **ước lượng khi đang có chèn/xóa đồng thời**; API không hứa một biên sai số cố định, không hứa số luôn tăng nếu nhiều writer chỉ thêm/xóa tùy ý, và không cho phép quan sát một danh sách entry nhất quán cùng phép đếm.

**Lưu ý:** Một lần thử đơn lẻ có thể luôn trả số “trông đúng” vì scheduling ít va chạm. Điều đó **không phủ định** giới hạn được mô tả trong API. Để kiểm thử race về quota, hãy dùng điều khiển thứ tự xác định thay vì cố tạo một mismatch nội bộ bất định.

### 4.3. Không nhầm “ước lượng” với “số ngẫu nhiên vô nghĩa”

`mappingCount` vẫn có ích:

- Giao diện giám sát cho biết map có khoảng bao nhiêu khóa đang sống.
- Metric/gauge phục vụ biểu đồ theo thời gian.
- Ước lượng dung lượng cần dùng, phân tích load hoặc phát hiện bất thường.
- Kiểm tra sau khi ứng dụng **biết chắc không còn concurrent mutations**, ví dụ sau khi đợi tất cả writer hoàn tất.

Điều cần tránh là biến số gần đúng thành điều kiện quyết định **quyền truy cập, quota tuyệt đối, thanh toán hoặc bất biến không được vi phạm**.

## 5. Kiểm tra rồi cập nhật là hai hành động riêng biệt

Một lỗi phổ biến khi muốn giới hạn map tối đa 1 mapping:

```java
if (map.mappingCount() < 1) {
    map.put(newKey, value);
}
```

Đoạn mã này **không an toàn nếu nhiều luồng đồng thời thêm các khóa khác nhau**. Vì sao? Cả hai luồng có thể cùng đọc **0** rồi đều được phép gọi `put`.

Sơ đồ:

```text
Map ban đầu rỗng. Giới hạn mong muốn = 1.

Thread A                             Thread B
----------------------------------------------------------------
mappingCount() -> 0
                                     mappingCount() -> 0
kiểm tra 0 < 1 -> đúng
                                     kiểm tra 0 < 1 -> đúng
put("A", 1)
                                     put("B", 2)
----------------------------------------------------------------
Map cuối có 2 mapping, vượt quota 1.
```

Điều này có thể xảy ra **ngay cả khi cả hai phép đọc `mappingCount()` lúc ấy chính xác**, vì không có mutation nào giữa hai lượt đọc. Lỗi nằm ở việc **điều kiện và hành động ghi không được phối hợp nguyên tử**.

### 5.1. Đây không phải lỗi riêng của mappingCount

Thay thành:

```java
if (map.size() < 1) {
    map.put(newKey, value);
}
```

vẫn sai tương tự. Hoặc:

```java
if (map.isEmpty()) {
    map.put(newKey, value);
}
```

cũng không ngăn hai luồng cùng thấy rỗng rồi thêm hai khóa. `isEmpty()` không phải khóa hoặc guard độc quyền cho những thao tác tương lai.

Không có phép đọc số lượng nào tự làm cho **một phép ghi tiếp theo** trở thành một giao dịch chung.

### 5.2. Atomic với một khóa chưa phải atomic với toàn map

`map.putIfAbsent(key,value)` bảo đảm chỉ một giá trị được cài vào **một khóa cụ thể** trong bối cảnh cạnh tranh. Nhưng:

```java
map.putIfAbsent("A", 1);
map.putIfAbsent("B", 2);
```

là hai khóa khác nhau; mỗi thao tác có thể hợp lệ đồng thời và cả hai có thể làm cardinality tăng. Không thể áp giới hạn **tổng số mapping** chỉ nhờ dùng `putIfAbsent` nếu hai writer không tranh cùng một khóa.

Tương tự, `compute(key,...)` và `computeIfAbsent(key,...)` tạo điểm phối hợp nguyên tử theo **key** cho cập nhật riêng, không làm một phép kiểm tra `mappingCount` trở thành transaction toàn map.

## 6. Giới hạn số mapping đúng cách cần phối hợp writer

Nếu hệ thống chỉ chạy **trong một JVM** và có một tập API ghi do bạn kiểm soát, giải pháp dễ giải thích cho quota cardinality nhỏ là **đi qua một khóa đồng bộ chung** đối với mọi thay đổi số khóa.

Ví dụ minh họa:

```java
static boolean putIfRoom(
        ConcurrentHashMap<String, Integer> map,
        Object admissionLock,
        int max,
        String key,
        int value) {

    synchronized (admissionLock) {
        if (map.containsKey(key)) {
            map.put(key, value); // Thay giá trị, cardinality không tăng.
            return true;
        }

        if (map.mappingCount() >= max) {
            return false;       // Từ chối thêm khóa mới.
        }

        map.put(key, value);     // Ghi dưới cùng một lock.
        return true;
    }
}
```

Điều kiện đúng của ví dụ:

1. **Tất cả thao tác làm thay đổi cardinality** của map phải tôn trọng cùng `admissionLock` (thêm, xóa, `clear`, những thao tác mutation qua views, v.v.).
2. Cùng một process/JVM giữ chung map và khóa.
3. Không có một writer bí mật dùng `map.put` ngoài lock này.
4. Khi vào vùng đồng bộ, những writer theo quy tắc trên không thể đồng thời đổi số mapping, nên việc kiểm tra và thêm khóa có một critical section rõ.
5. Nếu phải giữ cardinality chính xác **trên nhiều máy chủ**, khóa `synchronized` trong một JVM không đủ; cần cơ chế điều phối tập trung/transaction phù hợp với hệ thống phân tán.

Phương pháp này có thể **giảm throughput** của các thao tác ghi cần kiểm tra quota vì tập trung vào một lock chung. Đó là trade-off có chủ đích: một **quy tắc toàn map chính xác** cần phối hợp toàn map hoặc một mô hình admission/counter có đủ bảo đảm.

### 6.1. Khi nào không nên dùng synchronized toàn map?

Nếu map có tần suất cập nhật cực cao, khóa chung có thể thành bottleneck. Hãy cân nhắc:

- Một **bộ quản lý quota** có state riêng và thực hiện atomic reservation/release cùng mutation qua một API thống nhất.
- Một `Semaphore` để giới hạn **số tác vụ đồng thời**; lưu ý giới hạn tác vụ concurrent **không tự bằng** giới hạn số khóa đang tồn tại.
- Một thiết kế shard/partition có chính sách giới hạn từng partition và tính toán tổng chính xác theo nhu cầu.
- Transaction database, unique constraints và cơ chế tính quota đúng khi dữ liệu phải thống nhất giữa nhiều JVM.
- Hàng đợi một writer/single owner cho bảng mapping cần consistency mạnh.
- Một cache có chính sách eviction/capacity được cung cấp bởi thư viện chuyên dụng nếu bài toán thực sự là cache bounded.

**Không dùng riêng `LongAdder` làm “vé quota chính xác”** dưới cạnh tranh: giá trị tổng của LongAdder không phải một snapshot atomic khi cập nhật, và không tự liên kết với mutation của map.

### 6.2. Chốt quota trước khi commit và rollback thế nào?

Một hệ thống nghiêm ngặt cần quy định rõ thứ tự: **reserve capacity → ghi mapping → confirm**, cùng cách **release** khi xóa hoặc nếu ghi thất bại. Nếu có side effect ngoài JVM (DB, API khác), cần xử lý lỗi/rollback/idempotency ở lớp transaction. Ví dụ `synchronized` ở đây chỉ có trách nhiệm minh họa guard cho map **đơn process**, không phải giải pháp cho nghiệp vụ phân tán.

Nếu chỉ muốn tính quota theo **số request đang xử lý**, một `Semaphore` với `tryAcquire`/`release` trong `finally` có thể hợp lý. Nhưng permit được trả lại khi request xong, không có nghĩa một key trong map đã bị xóa. Đặt tên metric/quota đúng đối tượng.

## 7. Khi nào kết quả quan sát có thể coi là chính xác?

Trong tình huống **quiescent** — không còn thao tác cập nhật đồng thời và bạn có cơ chế biết điều đó — số mapping có thể được đọc như cardinality của trạng thái ổn định.

Ví dụ:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);

ConcurrentHashMap<Integer,Integer> map = new ConcurrentHashMap<>();
List<CompletableFuture<Void>> tasks = new ArrayList<>();

for (int worker = 0; worker < 4; worker++) {
    final int w = worker;
    tasks.add(CompletableFuture.runAsync(() -> {
        for (int i = 0; i < 100; i++) {
            map.put(w * 100 + i, i);
        }
    }, pool));
}

CompletableFuture.allOf(
        tasks.toArray(new CompletableFuture[0])).join();

// Giả sử không còn writer mới hay các mutation khác:
long n = map.mappingCount(); // 400.
int size = map.size();       // 400.
pool.shutdown();
```

Đây là ví dụ trong một method với imports từ `java.util.*` và `java.util.concurrent.*`. Mỗi worker dùng 100 khóa riêng; tất cả 400 thao tác `put` thành công. `CompletableFuture.allOf(...).join()` ở thread điều phối chờ toàn bộ worker hoàn tất trước khi đọc.

**Điểm then chốt không phải “sleep đủ lâu”** mà là **đã có bảo đảm các tác vụ cập nhật xong** và không có writer khác đang sửa map.

### 7.1. Vì sao `Thread.sleep` không phải barrier?

`Thread.sleep(100)` chỉ cho luồng gọi tạm dừng. Nó không chứng minh tất cả tác vụ writer đã hoàn thành hoặc không còn writer khác. Máy CI tải nặng có thể làm writer chậm hơn dự kiến.

Dùng `CompletableFuture.allOf(...).join()`, `CountDownLatch`, `Phaser`, `ExecutorService.awaitTermination` hoặc cơ chế phối hợp phù hợp, thay vì quyết định dựa trên thời gian ngủ tùy ý.

### 7.2. Đừng biến một lần đo ổn định thành cam kết ổn định mãi

Ngay sau khi barrier hoàn tất, nếu một tác vụ khác vẫn có quyền thêm/xóa, giá trị vừa đọc có thể lỗi thời. “Đọc đúng ở thời điểm hệ thống yên lặng” không đảm bảo nó đúng suốt thời gian sau đó.

Muốn làm một snapshot toàn bộ keys/values **bất biến**, cần kiến trúc snapshot/copy theo một protocol không có mutations liên quan trong khoảng snapshot hoặc cơ chế phiên bản hóa/điều phối riêng.

## 8. Weakly consistent iterator không thay thế phép chụp ảnh thống nhất

`ConcurrentHashMap.keySet()`, `values()`, `entrySet()` và các iterator/spliterator của những view này được thiết kế cho môi trường concurrent. Chúng có tính **weakly consistent**: việc duyệt có thể nhìn thấy các trạng thái của bảng ở những thời điểm khác nhau, và không ném `ConcurrentModificationException` chỉ vì map bị cập nhật đồng thời.

Ví dụ:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("A", 1);

Set<String> keys = map.keySet();
map.put("B", 2);

System.out.println(keys.contains("B")); // true trong ví dụ ổn định.
```

`keySet()` là **view được backed bởi map**, không phải một bản copy cố định tại thời điểm gọi.

### 8.1. Đếm bằng stream không tạo snapshot

Một anti-pattern:

```java
long counted = map.entrySet().stream().count();
```

Kết quả có kiểu `long`, nhưng **không tự bảo đảm snapshot**, bởi nguồn là view concurrent có thể thay đổi trong quá trình duyệt. Việc lấy `stream().count()` cũng có thể có chi phí/chi tiết tối ưu hóa khác nhau tùy spliterator, vì vậy không được coi nó như một phương thức “tính cardinality chính xác bằng mọi giá”.

Nếu nghiệp vụ đòi một danh sách các entry cùng một thời điểm, phải **ngăn các writer liên quan** hoặc dùng một mô hình snapshot riêng; stream không thay thế transaction.

### 8.2. Duyệt một lần và mappingCount có thể không trùng

Giả sử một thread duyệt keySet, một thread khác thêm/xóa liên tục. Iterator có thể phản ánh những mapping tại các thời điểm khác nhau, trong khi `mappingCount` được đọc ở một thời điểm riêng. Không có contract bảo đảm:

```java
map.mappingCount() == numberOfElementsSeenDuringIteration
```

khi concurrent mutations đang diễn ra.

Đừng viết test “đếm stream bắt buộc luôn bằng mappingCount” dưới tải concurrent; nó có thể flaky và kiểm thử một điều API không hứa.

### 8.3. containsValue không phải điều kiện quản lý toàn map chắc chắn

`containsValue(value)` trên ConcurrentHashMap là phép tìm trên bảng, và Javadoc cảnh báo các **aggregate status methods** gồm `containsValue` phản ánh trạng thái nhất thời khi có writer.

Nếu bạn cần kiểm tra và thiết lập một quy tắc độc nhất theo value, mô hình map theo key có thể không đúng; hãy cân nhắc tạo một index/constraint tương ứng với value hoặc giao dịch bảo đảm uniqueness. Không dùng `containsValue` trước `put` rồi coi đó là atomic unique-value guarantee.

## 9. Các phương thức quan sát khác và rủi ro TOCTOU

| Phương thức | Ý nghĩa | Điều không được suy ra khi có writer |
| --- | --- | --- |
| `mappingCount()` | Số mapping dạng `long`, ước lượng khi đang cập nhật | “Có đúng N khóa tại một instant giao dịch toàn map” |
| `size()` | Số mapping dạng `int`, giới hạn `Integer.MAX_VALUE` | “Dùng làm quota check rồi thêm khóa là an toàn” |
| `isEmpty()` | Kiểm tra bảng rỗng tại một lần quan sát | “Sau lời gọi này không ai có thể thêm/xóa” |
| `containsKey(k)` | Kiểm tra mapping của **một key** | “Key còn tồn tại khi hành động tiếp theo diễn ra” |
| `get(k)` | Đọc value cho key tại phép tra cứu | “Value sẽ không đổi đến lúc dùng nó” |
| `containsValue(v)` | Tìm value ở đâu đó trong bảng | “Có thể áp một unique-value constraint toàn map bằng check-then-put” |
| `keySet().iterator()` | Duyệt khóa weakly consistent | “Đây là danh sách khóa cùng một snapshot” |
| `entrySet().size()` | Dạng size của view, liên quan map | “Nó cho một số đếm độc lập chính xác hơn mappingCount” |

**Không phải tất cả các API này đều có cùng contract per-key.** `get(k)` và `putIfAbsent(k,v)` có những bảo đảm cho **cùng key**. Nhưng những bảo đảm per-key không hợp thành một phép check-then-act trên **toàn bộ tập khóa** nếu thiếu phối hợp.

### 9.1. isEmpty và nghĩa của “hiện không có dữ liệu”

Khi `map.isEmpty()` trả true, một thao tác `put` từ luồng khác có thể xảy ra ngay sau đó. Khi cần chờ “mọi producer đã kết thúc và queue không còn item”, `map.isEmpty()` đơn lẻ **không đủ** làm điều kiện dừng; phải có một tín hiệu hoàn tất producer/ownership hoặc protocol shutdown rõ.

### 9.2. Kiểm tra có khóa rồi thay đổi state

Thay vì:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

với cùng một khóa, dùng:

```java
map.putIfAbsent(key, value);
```

để thao tác cho key ấy là nguyên tử theo contract của ConcurrentMap. Còn quota toàn map, như đã giải thích, cần coordination riêng.

## 10. LongAdder và số mapping: hai phép đo không được trộn

Một ứng dụng dùng `ConcurrentHashMap<String, LongAdder>` làm histogram:

```java
ConcurrentHashMap<String, LongAdder> freqs =
        new ConcurrentHashMap<>();

for (String event : List.of("java", "java", "kotlin")) {
    freqs.computeIfAbsent(event, k -> new LongAdder()).increment();
}
```

Sau vòng lặp không có writer khác:

- `freqs.mappingCount()` = **2**: có 2 nhóm/khóa.
- `freqs.get("java").sum()` = **2**: số lần thấy sự kiện java.
- `freqs.get("kotlin").sum()` = **1**.
- Tổng số sự kiện đã đếm = **3**.

**Cảnh báo quan trọng:** Trong lúc thread khác vẫn gọi `increment()`, `LongAdder.sum()` không phải ảnh chụp nguyên tử của tất cả cell counter. Đối với monitor/rate statistic, một giá trị gần đúng thường chấp nhận được. Với số liệu tài chính/kiểm toán, cần nguồn dữ liệu hoặc giao dịch có bảo đảm phù hợp.

### 10.1. “Mapping ổn định” không đồng nghĩa value bất biến

Có thể `mappingCount()` giữ nguyên 2 trong khi:

```java
freqs.get("java").increment();
freqs.get("java").increment();
```

làm tổng tần suất java tăng từ 2 lên 4. Map **không thay cardinality**, nhưng **nội dung của object value** đã thay đổi.

Với map chứa object mutable bất kỳ, `mappingCount` không nói gì về tính nhất quán của các field trong object đó. Thread safety của map không tự bảo vệ mọi object mutable bên trong.

### 10.2. computeIfAbsent không phải bộ đếm dung lượng chung

`computeIfAbsent(key, mappingFunction)` phối hợp việc tạo value cho **key tương ứng**. Nó không nhận biết và chặn tổng cardinality vượt ngưỡng. Nếu có 1.000 key khác nhau và mỗi thread thêm một key, tất cả vẫn có thể tạo thêm mapping khi không có quota policy khác.

Trong Java hiện đại, mapping function truyền cho `ConcurrentHashMap.computeIfAbsent` nên **ngắn gọn**, không tự tìm cách sửa các mapping khác của chính map trong quá trình tính; Javadoc có những ràng buộc và cảnh báo về thao tác trên map trong callback. Dùng nó để **tạo một value ban đầu**, không làm một transaction đa-key.

## 11. Vì sao mappingCount trả long không có nghĩa map “chứa vô hạn”

`long` có miền lớn hơn `int`, nhưng **giới hạn kiểu số** khác **giới hạn tài nguyên vật lý** và cấu trúc triển khai.

Một map có hàng tỷ mapping cần đáng kể memory cho keys, values, entry structures và capacity. Trong JVM thực, bạn còn chịu:

- Giới hạn heap, garbage collector, object headers, bộ cấp phát.
- Giới hạn dung lượng bảng, độ phân bố hash và resize.
- Chi phí lưu key/value, phân phối khóa, contention khi cập nhật.
- Thời gian duyệt/hủy/serialize/backup dữ liệu lớn.
- Số lượng luồng và tốc độ tạo/xóa object.
- Ràng buộc của nền tảng lưu trữ và các client khác.

**Không nên tạo hàng tỷ entry để test `size()` bão hòa**. Javadoc đã quy định ý nghĩa `size()` khi vượt `Integer.MAX_VALUE`; bài kiểm thử nên tập trung vào logic, bằng test đa luồng nhỏ và có kiểm soát.

### 11.1. Cẩn thận với conversion trở lại int

Nếu một thư viện hoặc giao diện UI chỉ nhận `int`:

```java
long observed = map.mappingCount();

int shown = observed > Integer.MAX_VALUE
        ? Integer.MAX_VALUE
        : (int) observed;
```

Đây là phép **saturating conversion** có chủ ý; chỉ phù hợp nếu UI/API muốn biểu diễn “ít nhất ngưỡng này”. Nếu yêu cầu báo số đếm chính xác trong miền lớn, hãy sửa contract để truyền `long` thay vì cắt.

**Không ép `(int) observed` trực tiếp** khi số có thể vượt `Integer.MAX_VALUE`: phép chuyển narrowing có thể làm mất bit cao và cho kết quả sai. Cũng không nên giả sử mọi thư viện JSON/JavaScript xử lý số nguyên 64 bit chính xác: nếu truyền count rất lớn qua biên giữa ngôn ngữ, xác định serialization contract rõ.

## 12. Đo size cho monitoring và telemetry

Đối với **gauge** (đồ thị số mapping hiện có theo thời gian), `mappingCount()` phù hợp vì:

- Không đòi duyệt toàn bộ entry bằng code ứng dụng.
- Trả `long`, tránh giới hạn giao diện `int`.
- Được thiết kế để đưa ra một quan sát hữu ích dù đang có writer.
- Metric không nhất thiết cần chính xác tới từng entry tại một instant.

Ví dụ:

```java
long approxEntries = map.mappingCount();
metrics.gauge("cache.entries", approxEntries);
```

Đây là **mã minh họa**, biến `map` và `metrics` do ứng dụng cung cấp. Không nhầm số đo này với tổng request được xử lý hoặc số bản ghi lưu ở database.

### 12.1. Đặt tên metric cho đúng

Tên như `active_mappings_estimate` hoặc `in_memory_registry_keys` (có mô tả “approximate under concurrent updates”) tránh làm người vận hành hiểu nhầm thành giao dịch chính xác.

Nếu metric có nguy cơ bị đọc như số liệu tài chính, billing hoặc quota tuyệt đối, thêm mô tả rõ **giới hạn quan sát** và giữ nguồn dữ liệu authoritative riêng.

### 12.2. Gauge khác counter sự kiện

- **Gauge cardinality:** số key đang lưu hiện tại — có thể tăng hoặc giảm.
- **Event counter:** tổng số sự kiện đi qua — thường tăng theo sự kiện, không bị ảnh hưởng bởi việc xóa key.
- **Histogram:** phân bố tần suất các nhãn — có thể dùng LongAdder làm value và đọc sum.
- **Quota reservation:** số slot đã chiếm theo quy tắc admission — cần có bảo đảm tính nhất quán riêng.

Không lấy `mappingCount()` rồi suy ra tốc độ request theo phép trừ hai mẫu nếu giữa hai mẫu có cả chèn/xóa; kết quả đó chỉ phản ánh **thay đổi net cardinality**, không phải số sự kiện được xử lý.

## 13. Bulk operations và số lượng đọc được

`ConcurrentHashMap` có các bulk operations như `forEach`, `search`, `reduce`, và các phiên bản `reduceToLong`/`reduceEntriesToLong`. Chúng có thể phù hợp để tóm tắt dữ liệu trong map đang hoạt động, nhưng **không bảo đảm toàn bộ dữ liệu được quan sát trong cùng một snapshot atomic** nếu map còn cập nhật.

Ví dụ minh họa:

```java
long totalValue = map.reduceValuesToLong(
        Long.MAX_VALUE,
        value -> (long) value,
        0L,
        Long::sum);
```

Đoạn này yêu cầu `map` kiểu `ConcurrentHashMap<?, Integer>` và giả định giá trị không null (đúng với ConcurrentHashMap). `Long.MAX_VALUE` ở đây được dùng cho `parallelismThreshold` để ngăn parallelism của bulk operation, **không làm phép đọc trở thành snapshot nguyên tử**.

### 13.1. ParallelismThreshold không phải độ chính xác của mappingCount

Bulk API dùng `parallelismThreshold` để quyết định cách chia việc xử lý, có thể dựa trên số phần tử được **ước lượng**. Điều này liên quan hiệu năng thực thi, không thay đổi contract consistency của `mappingCount()`.

Đừng đặt `parallelismThreshold=1` với kỳ vọng “đếm nhanh và chính xác hơn”. Một bulk reduction chạy song song cũng có thể quan sát map thay đổi giữa lúc các nhánh duyệt.

### 13.2. Muốn snapshot chính xác cần protocol riêng

Có ba lựa chọn kiến trúc thường gặp, tùy workload:

1. **Quiescence:** dừng hoặc phối hợp writer, chờ các cập nhật đã bắt đầu kết thúc, rồi đọc và copy/snapshot.
2. **Ownership:** một actor/owner hoặc transactional service quản lý writes và cung cấp trạng thái nhất quán.
3. **Versioning/transaction:** có phiên bản nhất quán và truy vấn theo một version, ví dụ trong database có snapshot isolation phù hợp.

Chỉ copy `new HashMap<>(concurrentMap)` trong lúc writer còn hoạt động **không tự biến dữ liệu thành snapshot tại một thời điểm duy nhất**; việc copy có thể thu giá trị được quan sát ở nhiều thời điểm khác nhau. Nếu snapshot correctness là yêu cầu bắt buộc, phải xác định protocol kiểm soát writer hoặc hệ thống lưu trữ có transaction.

## 14. Phân biệt per-key atomicity và global consistency

Các API như:

```java
map.putIfAbsent(key, value);
map.compute(key, (k, old) -> newValue);
map.replace(key, oldValue, newValue);
map.remove(key, expectedValue);
```

có những contract cập nhật nguyên tử **đối với mapping của key chỉ định**. Điều này rất mạnh trong bài toán cache, registry và state machine theo key.

Ví dụ giảm race trên cùng một key:

```java
ConcurrentHashMap<String,Integer> map = new ConcurrentHashMap<>();
Integer previous = map.putIfAbsent("A", 1);
```

Nếu nhiều thread cùng tranh key “A”, cuối cùng tại một thời điểm map chỉ có tối đa một mapping “A”. Nhưng kết quả không nói gì về quy tắc **“toàn map tối đa 100 keys”** khi các thread tranh những key khác nhau.

### 14.1. Global quota không thể suy ra từ nhiều per-key atomics

Một chuỗi:

```text
read global count
  -> inspect a key
  -> compute something
  -> put key
```

không tự thành atomic toàn map chỉ vì bước cuối dùng `compute` hoặc `putIfAbsent`. Cần một shared coordinator hoặc transaction mà **mọi write path có khả năng đổi cardinality đều tuân thủ**.

### 14.2. Mutable value và số mapping độc lập

Nếu một value chứa object mutable, hai luồng có thể sửa object đó đồng thời dù không chạm `put`/`remove`. `ConcurrentHashMap` bảo vệ cấu trúc ánh xạ, **không tự cung cấp thread safety cho mọi field bên trong value**.

Dùng immutable values, atomic fields, locks hoặc concurrent data structures khi nhiều luồng cần sửa trạng thái value.

## 15. Thiết kế bài test: khẳng định đúng cái mà API hứa

### 15.1. Test bình thường không có writer

```java
ConcurrentHashMap<String,Integer> map = new ConcurrentHashMap<>();

map.put("A", 10);
map.put("B", 20);

assert map.mappingCount() == 2;
assert map.size() == 2;

map.replace("A", 11);
assert map.mappingCount() == 2;

map.remove("B");
assert map.mappingCount() == 1;
```

Đây là **đoạn minh họa**; `assert` Java chỉ có hiệu lực khi JVM chạy với `-ea`. Chương trình hoàn chỉnh sẽ dùng `require(...)` ném `AssertionError` kể cả khi assertions của JVM bị tắt.

### 15.2. Test quota sai bằng barrier, không bằng may rủi

- Map bắt đầu rỗng, quota tối đa 1.
- Hai writer đều đọc mappingCount trước khi **bất kỳ writer nào thêm key**.
- Dùng `CountDownLatch(2)` ghi nhận cả hai đã đọc.
- Dùng một `CountDownLatch(1)` khác mở cửa cho hai writer cùng tiến tới `put`.
- Chờ cả hai hoàn tất bằng `CompletableFuture.join()`.
- Cả hai đã quan sát 0, nên cả hai thêm key riêng, final count = **2**.

Test này **không phụ thuộc máy nhanh hay chậm** và không cần cố tạo trường hợp `mappingCount` nội bộ ước lượng sai. Nó chứng minh ngay cả phép đọc chính xác cũng **không đủ** thực hiện một business rule atomic.

### 15.3. Test quota có guard

Với một `Object admissionLock` được dùng chung, cho hai writer cùng cố thêm hai key khi quota max=1. Cả hai đi qua `synchronized`; chỉ một thêm mới, writer kia thấy count 1 và bị từ chối.

Test không cần assert “writer A phải thắng”, vì thứ tự scheduler không được đảm bảo. Chỉ assert **accepted == 1**, **mappingCount == 1**.

### 15.4. Test sau khi worker kết thúc

Tạo 4 worker, mỗi worker chèn 100 key riêng. Sau `CompletableFuture.allOf(...).join()`, kết quả cardinality là 400. Không assert số count chính xác trong lúc các worker đang chạy, vì tài liệu không hứa snapshot. Đây cũng là cách phân biệt **giá trị cuối sau barrier** với **giá trị lúc đang cập nhật**.

## 16. Chương trình Java 17+ hoàn chỉnh

Chương trình sau bao gồm:

- Quan sát `mappingCount` và `size` trong trạng thái ổn định.
- Thay value và xóa key để xem cardinality đổi thế nào.
- Minh họa `keySet()` là live view.
- Tái hiện lỗi quota check-then-put với 2 writer bằng latch.
- Khắc phục quota trong **một JVM với tất cả writers đi qua một lock**.
- 4 writer chèn tổng 400 khóa và kiểm tra sau completion barrier.
- Sử dụng `LongAdder` trong một bảng tần suất, phân biệt số keys và sự kiện.
- Kiểm chứng `null` value bị từ chối.
- Dọn `ExecutorService` ở `finally`.

Tạo file **`MappingCountObservationDemo.java`**:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class MappingCountObservationDemo {
    static void require(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
    }

    // Demo quota trong một JVM: MỌI mutation đổi cardinality
    // phải đi qua admissionLock này để điều kiện được bảo vệ.
    static boolean putIfRoom(
            ConcurrentHashMap<String, Integer> map,
            Object admissionLock,
            int max,
            String key,
            int value) {
        synchronized (admissionLock) {
            if (map.containsKey(key)) {
                map.put(key, value);
                return true;
            }
            if (map.mappingCount() >= max) {
                return false;
            }
            map.put(key, value);
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String,Integer> stable =
                new ConcurrentHashMap<>();
        stable.put("A", 10);
        stable.put("B", 20);

        require(stable.mappingCount() == 2, "stable count");
        System.out.println("quiescentMappingCount=" +
                stable.mappingCount());
        System.out.println("quiescentSize=" + stable.size());

        stable.replace("A", 11);
        System.out.println("afterReplaceCount=" +
                stable.mappingCount());

        stable.remove("B");
        System.out.println("afterRemoveCount=" +
                stable.mappingCount());

        Set<String> liveKeys = stable.keySet();
        stable.put("C", 30);
        System.out.println("liveKeySetSeesC=" +
                liveKeys.contains("C"));

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            // Hai writer đọc 0, rồi đều thêm key khác nhau:
            // check-then-put KHÔNG bảo vệ quota max=1.
            ConcurrentHashMap<String,Integer> naive =
                    new ConcurrentHashMap<>();
            CountDownLatch sampled = new CountDownLatch(2);
            CountDownLatch proceed = new CountDownLatch(1);

            CompletableFuture<Long> readerA =
                    CompletableFuture.supplyAsync(() -> {
                        long seen = naive.mappingCount();
                        sampled.countDown();
                        await(proceed);
                        if (seen < 1) {
                            naive.put("threadA", 1);
                        }
                        return seen;
                    }, pool);

            CompletableFuture<Long> readerB =
                    CompletableFuture.supplyAsync(() -> {
                        long seen = naive.mappingCount();
                        sampled.countDown();
                        await(proceed);
                        if (seen < 1) {
                            naive.put("threadB", 1);
                        }
                        return seen;
                    }, pool);

            await(sampled);
            proceed.countDown();
            long a = readerA.join();
            long b = readerB.join();

            require(a == 0 && b == 0
                    && naive.mappingCount() == 2,
                    "TOCTOU quota broken");
            System.out.println("observedA=" + a);
            System.out.println("observedB=" + b);
            System.out.println("naiveLimitOneActualCount=" +
                    naive.mappingCount());

            // Tất cả writer mới đi qua cùng một lock.
            ConcurrentHashMap<String,Integer> admitted =
                    new ConcurrentHashMap<>();
            Object lock = new Object();

            CompletableFuture<Boolean> one =
                    CompletableFuture.supplyAsync(
                            () -> putIfRoom(
                                    admitted, lock, 1, "one", 1),
                            pool);
            CompletableFuture<Boolean> two =
                    CompletableFuture.supplyAsync(
                            () -> putIfRoom(
                                    admitted, lock, 1, "two", 2),
                            pool);

            int accepted = (one.join() ? 1 : 0)
                    + (two.join() ? 1 : 0);

            require(accepted == 1
                    && admitted.mappingCount() == 1,
                    "coordinated admission");

            System.out.println("coordinatedAccepted=" + accepted);
            System.out.println("coordinatedCount=" +
                    admitted.mappingCount());

            // Hoàn tất 4 worker, mỗi worker 100 khóa riêng.
            ConcurrentHashMap<Integer,Integer> concurrent =
                    new ConcurrentHashMap<>();
            List<CompletableFuture<Void>> tasks = new ArrayList<>();

            for (int w = 0; w < 4; w++) {
                final int worker = w;
                tasks.add(CompletableFuture.runAsync(() -> {
                    for (int i = 0; i < 100; i++) {
                        concurrent.put(worker * 100 + i, i);
                    }
                }, pool));
            }

            CompletableFuture.allOf(
                    tasks.toArray(new CompletableFuture[0])).join();
            require(concurrent.mappingCount() == 400
                    && concurrent.size() == 400,
                    "join observed 400");

            System.out.println("afterWorkersMappingCount=" +
                    concurrent.mappingCount());
            System.out.println("afterWorkersSize=" +
                    concurrent.size());

            concurrent.clear();
            System.out.println("afterClearCount=" +
                    concurrent.mappingCount());
        } finally {
            pool.shutdown();
            require(pool.awaitTermination(
                    5, TimeUnit.SECONDS), "pool shutdown");
        }

        // 2 loại sự kiện -> 2 mapping, nhưng tổng có 3 sự kiện.
        ConcurrentHashMap<String,LongAdder> counts =
                new ConcurrentHashMap<>();
        for (String key : List.of("java", "java", "kotlin")) {
            counts.computeIfAbsent(
                    key, k -> new LongAdder()).increment();
        }

        require(counts.mappingCount() == 2, "distinct keys");
        System.out.println("histogramKeys=" +
                counts.mappingCount());
        System.out.println("javaEvents=" +
                counts.get("java").sum());
        System.out.println("kotlinEvents=" +
                counts.get("kotlin").sum());

        boolean rejectedNull = false;
        try {
            stable.put("oops", null);
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }
        System.out.println("nullValueRejected=" + rejectedNull);
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac MappingCountObservationDemo.java
java MappingCountObservationDemo
```

**Stdout chính xác (đã chạy kiểm thử với JDK hiện đại, không dựa vào thứ tự thread thắng):**

```text
quiescentMappingCount=2
quiescentSize=2
afterReplaceCount=2
afterRemoveCount=1
liveKeySetSeesC=true
observedA=0
observedB=0
naiveLimitOneActualCount=2
coordinatedAccepted=1
coordinatedCount=1
afterWorkersMappingCount=400
afterWorkersSize=400
afterClearCount=0
histogramKeys=2
javaEvents=2
kotlinEvents=1
nullValueRejected=true
ALL CHECKS PASSED
```

### 16.1. Đọc nhóm kết quả trạng thái ổn định

`quiescentMappingCount=2` và `quiescentSize=2` cho thấy khi không có concurrent writer, hai API cùng biểu diễn cardinality 2. Thay giá trị A không làm tăng key count, nên `afterReplaceCount=2`. Xóa B còn một key, nên `afterRemoveCount=1`.

`liveKeySetSeesC=true` xác nhận `keySet()` là view theo map, không phải snapshot bất biến: thêm C sau khi lấy view vẫn khiến `keys.contains("C")` đúng.

### 16.2. Đọc nhóm quota sai

`observedA=0` và `observedB=0` **không phải** lỗi ước lượng của mappingCount. Khi cả hai đọc, map thực sự rỗng. Vì cả hai dùng kết quả cũ sau barrier, chúng cùng thêm hai khóa khác nhau. Kết quả `naiveLimitOneActualCount=2` phá quy tắc max=1.

Đây là bài học sâu nhất của chủ đề: **Ngay cả một phép đọc kích thước hoàn hảo cũng không bảo đảm check-then-act atomic.**

### 16.3. Đọc nhóm quota có phối hợp

`coordinatedAccepted=1` và `coordinatedCount=1` xuất hiện vì cả hai writer dùng cùng lock và không có con đường mutation lách lock. Không cần biết “one” hay “two” là writer được nhận; chương trình chỉ cần bảo đảm **cardinality tối đa 1**.

Trong môi trường thật, nếu có writer khác gọi `admitted.put("third",3)` trực tiếp không qua lock, giả định bị phá. Vì thế kiến trúc cần giới hạn quyền ghi và cung cấp một API duy nhất cho mutation khi business có quy tắc mạnh.

### 16.4. Đọc nhóm sau barrier

`afterWorkersMappingCount=400` và `afterWorkersSize=400` là số sau khi cả bốn worker đã hoàn tất, mỗi worker chèn 100 khóa độc lập. Nó **không chứng minh** mappingCount luôn exact khi đang có writer; nó minh họa cách đọc count ở trạng thái quiescent đã phối hợp.

Sau `clear()` và không có writer khác, `afterClearCount=0`.

### 16.5. Đọc nhóm histogram

`histogramKeys=2` vì có hai loại key. `javaEvents=2` và `kotlinEvents=1` vì có ba sự kiện được đếm. Không dùng `mappingCount()` cho tổng số sự kiện.

`nullValueRejected=true` nhắc lại khác biệt giữa ConcurrentHashMap và các map cho phép null: bản này không cho null keys/values.

## 17. Một số điều không nên suy luận từ kết quả vừa đo

### 17.1. Count hiện tại không khẳng định công việc đang chạy có bao nhiêu

Nếu map lưu các futures hoặc task handles, `mappingCount` đếm số **key còn trong map**, không đếm số task **thực sự đang thực thi**. Một task có thể hoàn tất nhưng chưa được xóa; một task khác có thể chạy ngoài map. Muốn “tasks currently running”, phải có lifecycle state được quản lý và metric tương ứng.

### 17.2. Count không phải độ dài hàng đợi

`ConcurrentHashMap` là map, không phải queue. Nếu có 100 key ánh xạ tới công việc cần xử lý, không đồng nghĩa 100 task đang chờ trong `BlockingQueue`. Nếu cần queue depth, đọc API của queue và hiểu tương tự giới hạn quan sát concurrency của chính loại queue đó.

### 17.3. Count không phản ánh kích thước bộ nhớ

Hai map có cùng số key vẫn có thể dùng lượng RAM khác nhau vì key/value khác kích thước, khác capacity, khác phân bố hash và retention. Để giám sát memory, dùng đo heap/GC/allocation thực tế, không nhân cố định `mappingCount * số byte giả định` rồi coi đó là chính xác.

### 17.4. Count bằng 0 không chứng minh hệ thống đã quiescent

Nếu các producer còn có thể thêm vào map, số đếm 0 chỉ phản ánh **một quan sát**. Muốn chấm dứt pipeline an toàn, phải kết hợp tín hiệu “không còn producer”, “mọi task đang chạy đã kết thúc” và “buffer rỗng” theo một protocol được thiết kế. Riêng `isEmpty()` hay `mappingCount() == 0` không phải shutdown barrier.

### 17.5. Count nhỏ không bảo đảm throughput sẽ tốt

Tính đúng của `equals/hashCode`, chất lượng phân phối hash, size của values, tần suất mutation, contention và hiệu ứng GC đều ảnh hưởng performance. Không tối ưu hệ thống chỉ dựa vào số mapping.

## 18. Ghi chú triển khai OpenJDK: đừng lập trình phụ thuộc field nội bộ

Trong một số bản triển khai OpenJDK, ConcurrentHashMap theo dõi count bằng các trường/cơ chế cộng dồn nội bộ để giảm contention khi nhiều thread cập nhật. Có thể gặp những tên như **baseCount** và cấu trúc đếm phân tán trong mã nguồn.

Đây là **chi tiết implementation**, **không phải public API contract**. Nó có thể thay đổi giữa phiên bản hoặc JVM vendor. Bài học quan trọng không phải nhớ công thức cộng cell hay field riêng, mà là:

- Contract `mappingCount()` trả `long`.
- Khi có chèn/xóa đồng thời, kết quả là **ước lượng**.
- Không có snapshot toàn map hoặc atomic check-then-act được hứa.
- Ứng dụng phải dùng API công khai và một protocol đúng cho yêu cầu consistency.

Đừng dùng reflection để đọc private counters, sửa field nội bộ, hoặc phân tích `mappingCount` dựa trên một phiên bản source rồi coi đó là tính chất vĩnh viễn. Việc truy cập private data có thể còn bị hạn chế bởi Java module encapsulation và không phù hợp cho production.

## 19. Những lỗi thường gặp và cách sửa

### Lỗi 1. Nghĩ mappingCount chính xác tuyệt đối vì trả long

**Sai:** kiểu `long` không nói gì về snapshot hay linearizability. **Sửa:** coi đây là estimate khi đang update; áp coordination riêng nếu cần con số giao dịch chính xác.

### Lỗi 2. Dùng size() vì “Map chỉ vài nghìn key”

`size()` có thể phù hợp cho code thường, nhưng vẫn không biến check-then-put thành nguyên tử trong môi trường có writer. **Sửa:** chọn API theo miền kiểu và áp đúng protocol cho quota.

### Lỗi 3. Nghĩ mappingCount là số lượt put

Một khóa cập nhật 100 lần vẫn chỉ là 1 mapping. **Sửa:** tách metric event counter và cardinality gauge.

### Lỗi 4. Coi LongAdder.sum là số mapping

`LongAdder` là value counter, không phải key count. **Sửa:** `mappingCount` đếm distinct keys, `sum()` đếm lượng value đó tích lũy và vẫn có giới hạn snapshot khi concurrent increments.

### Lỗi 5. Đọc mappingCount rồi put để enforce max

TOCTOU: nhiều writer cùng đọc một số cũ rồi đều thêm. **Sửa:** atomic admission guard/lock/capacity reservation theo toàn bộ mutation paths.

### Lỗi 6. Dùng putIfAbsent cho các key khác nhau rồi tưởng đã giữ global quota

`putIfAbsent` chỉ atomic cho **key đó**. **Sửa:** một coordinator chung hoặc storage transaction cho cardinality toàn map.

### Lỗi 7. Giữ synchronized lock cho một writer nhưng writer khác vẫn gọi put trực tiếp

Một đường viết tắt phá toàn bộ bảo đảm quota. **Sửa:** encapsulate map trong service, hạn chế quyền truy cập raw map; mọi thêm/xóa/clear phải qua cùng policy.

### Lỗi 8. Dùng synchronized trong JVM để giới hạn dữ liệu trên nhiều server

Mỗi JVM có lock riêng nên không ngăn các server khác ghi cùng tài nguyên trung tâm. **Sửa:** dùng transaction/distributed coordinator có contract phù hợp.

### Lỗi 9. Nghĩ keySet() trả snapshot

`keySet()` là view backed bởi map. **Sửa:** khi cần snapshot chính xác, dùng protocol quiescence/transaction và copy sau khi writer được phối hợp.

### Lỗi 10. Thay mappingCount bằng stream.count() để “đếm chắc hơn”

`stream()` dựa trên nguồn có tính weakly consistent. **Sửa:** không dùng bất kỳ phép duyệt nào như snapshot toàn map khi writer đang đổi dữ liệu.

### Lỗi 11. Assert stream.count == mappingCount trong stress test

Nếu map đang cập nhật, các quan sát có thể đến từ những thời điểm khác nhau. **Sửa:** assert bất biến thực sự của workflow và kết quả sau barrier.

### Lỗi 12. Dùng isEmpty() làm điều kiện dừng producer/consumer

Empty tại một thời điểm không có nghĩa không còn công việc đến. **Sửa:** protocol dừng producer, chờ in-flight work hoàn tất rồi kiểm tra state.

### Lỗi 13. Dùng containsValue để enforce uniqueness

Phép đọc rồi ghi không atomic; concurrent writer có thể thêm value đó. **Sửa:** thiết kế index/constraint theo value hoặc transaction thích hợp.

### Lỗi 14. Ép long sang int trực tiếp để đưa vào UI

Có thể overflow/narrowing sai. **Sửa:** contract long hoặc saturating conversion có chủ đích với nhãn rõ.

### Lỗi 15. Cố cấp phát hàng tỷ mapping để test Integer.MAX_VALUE

Không cần thiết, dễ OOM hoặc gây ảnh hưởng môi trường. **Sửa:** kiểm tra Javadoc contract và test logic trên dữ liệu nhỏ.

### Lỗi 16. Dùng Thread.sleep để đợi writer hoàn tất

Thời gian ngủ không phải completion barrier. **Sửa:** latch, future completion, awaitTermination hoặc protocol tương đương.

### Lỗi 17. Dùng volatile int global và tự tăng cho exact cardinality

`volatile` bảo đảm visibility phù hợp nhưng `count++` không atomic. **Sửa:** nếu xây counter quản lý cardinality, cần atomic update protocol đồng nhất với mọi mutation và rollback.

### Lỗi 18. Nghĩ ConcurrentHashMap bảo vệ mutable values

Nó quản lý map concurrency, không biến object value thành immutable hay synchronized. **Sửa:** dùng thread-safe value, immutable records hoặc khóa phù hợp.

### Lỗi 19. Xóa key mà không release quota reservation

Nếu hệ thống dùng một counter/reservation độc lập, cardinality thực và reservation có thể lệch. **Sửa:** thiết kế tất cả đường đi insert/remove/failure trong cùng protocol và kiểm thử rollback.

### Lỗi 20. Dùng mappingCount như số liệu billing hoặc security

Aggregate estimate không đủ để quyết định số tiền, số giấy phép hoặc điều kiện quyền truy cập tuyệt đối. **Sửa:** hệ thống nguồn authoritative với transaction hoặc snapshot có thể audit.

### Lỗi 21. Không đo tài nguyên vì mappingCount “đang thấp”

Map ít key nhưng chứa payload lớn có thể vẫn quá RAM. **Sửa:** đo heap/capacity/GC/retention và size thực của đối tượng.

### Lỗi 22. Dựa vào private fields của OpenJDK để suy ra tính đúng

Các chi tiết đếm nội bộ có thể thay đổi. **Sửa:** dựa trên public API/Javadoc và concurrency protocol được thiết kế.

## 20. Bài tập thực hành và đáp án

**Bài 1.** `mappingCount()` trả kiểu gì và từ phiên bản nào?

**Đáp án:** `long`; có từ **Java 8**. Đây là phương thức trên `ConcurrentHashMap`, không có trên interface `Map`.

**Bài 2.** `size()` trả gì nếu số mapping vượt `Integer.MAX_VALUE`?

**Đáp án:** Theo Javadoc `ConcurrentHashMap`, trả `Integer.MAX_VALUE`, vì return type là `int`. Không cần cấp phát quá 2 tỷ key để xác minh đặc tả.

**Bài 3.** Vì sao `mappingCount` có thể không khớp cardinality thực khi hai thread đang put/remove?

**Đáp án:** Đây là phép quan sát aggregate trong map đang thay đổi; Javadoc nêu rõ kết quả là ước lượng và có thể khác khi có chèn/xóa đồng thời.

**Bài 4.** Nếu không có concurrent writer, hai API có thể đọc số mapping chính xác không?

**Đáp án:** Có thể đọc cardinality của map ở trạng thái ổn định, miễn giá trị size nằm trong miền `int` với `size()`. Nhưng phải có cơ chế biết rằng không có writer khác và quan sát có thể cũ ngay khi writer mới xuất hiện.

**Bài 5.** Thực hiện `put("A",1)` rồi `put("A",2)` trên map ban đầu trống: mappingCount là bao nhiêu?

**Đáp án:** **1** mapping vì cùng một key A, `put` thứ hai thay value.

**Bài 6.** Map có 2 key “java”, “kotlin” trỏ tới LongAdder có sum lần lượt 100 và 50. mappingCount là bao nhiêu?

**Đáp án:** **2**, còn tổng events theo values là 150 khi không có cập nhật đồng thời. Hai số không thể thay cho nhau.

**Bài 7.** Hai luồng cùng đọc `mappingCount()==0` rồi cùng thêm key khác nhau nếu count nhỏ hơn 1. Có thể cuối cùng có 2 key không?

**Đáp án:** Có. **Check và put không atomic**, ngay cả khi hai phép đọc ban đầu đều chính xác.

**Bài 8.** Đổi `mappingCount` thành `size` có sửa được race không?

**Đáp án:** Không. Vẫn là hai thao tác riêng; cần coordinator cho toàn bộ mutation paths.

**Bài 9.** Dùng `putIfAbsent` cho các key A và B có ngăn count vượt 1 không?

**Đáp án:** Không. `putIfAbsent` chỉ cho bảo đảm nguyên tử theo **một key**, không cho quota toàn map.

**Bài 10.** Điều kiện nào để ví dụ `putIfRoom` với `synchronized` giữ quota?

**Đáp án:** **Mọi writer có khả năng thay đổi cardinality trong cùng JVM** phải đi qua cùng một lock, bao gồm cả các thao tác xóa/clear và thao tác qua view nếu có; không được có mutation đi vòng.

**Bài 11.** Có thể dùng lock JVM đó làm quota phân tán qua 3 server không?

**Đáp án:** Không. Mỗi JVM có lock độc lập; cần cơ chế đồng bộ ở tầng có chung nguồn dữ liệu, ví dụ transaction/constraint hoặc coordinator có bảo đảm đúng yêu cầu.

**Bài 12.** `keySet()` trả live view hay snapshot?

**Đáp án:** **Live view** backed bởi map. Trong ví dụ ổn định, thêm key sau khi lấy view vẫn làm `keys.contains(key)` đúng.

**Bài 13.** `entrySet().stream().count()` có luôn chính xác hơn `mappingCount()` khi đang có writer không?

**Đáp án:** Không. Duyệt weakly consistent không tạo snapshot toàn map; hai phép đọc cũng có thể ở những thời điểm khác nhau.

**Bài 14.** Tại sao `map.isEmpty()==true` chưa đủ làm điều kiện shutdown?

**Đáp án:** Thread khác vẫn có thể thêm mapping sau phép đọc. Cần biết producers đã dừng và in-flight work hoàn tất.

**Bài 15.** Tại sao trong test 4 worker, giá trị 400 có thể được assert sau `allOf().join()`?

**Đáp án:** Vì mỗi worker ghi vào 100 key duy nhất và tất cả worker đã hoàn thành. Không còn cập nhật liên quan sau barrier nên cardinality ổn định.

**Bài 16.** Một metric muốn đo “số request đã được xử lý”. Dùng mappingCount có đúng không?

**Đáp án:** Không. MappingCount là cardinality hiện thời của map. Số request cần counter sự kiện hoặc số liệu authoritative khác.

**Bài 17.** Nếu UI chỉ nhận int mà mappingCount trả long lớn, nên làm gì?

**Đáp án:** Tốt nhất sửa UI contract thành long nếu cần số thật. Nếu UI chấp nhận bão hòa, dùng saturating conversion có chủ đích và nhãn rõ, không cast trực tiếp gây narrowing.

**Bài 18.** `LongAdder.sum()` trên map tần suất có phải ảnh chụp nguyên tử của các lần tăng đồng thời không?

**Đáp án:** Không. Nó phù hợp cho thống kê, không tự đảm bảo một snapshot linearizable của tất cả cập nhật đang diễn ra.

**Bài 19.** Có thể lấy chính xác bao nhiêu mapping và nội dung từng mapping bằng cách gọi `mappingCount` rồi duyệt entrySet lúc map đang cập nhật không?

**Đáp án:** Không có bảo đảm snapshot chung. Cần một protocol tạm ngừng/phối hợp writes hoặc hệ thống snapshot/transaction phù hợp.

**Bài 20.** Nếu business yêu cầu “không bao giờ vượt 500 key kể cả dưới concurrent load”, hướng thiết kế đúng là gì?

**Đáp án:** Dùng một cơ chế admission/quota có atomicity trên toàn bộ mutation liên quan (ví dụ synchronized global guard cho một JVM khi mọi writers tuân thủ, hoặc transaction/coordinator ở hệ phân tán). Không dùng riêng `if (mappingCount() < 500) put(...)`.

## 21. Checklist production

- [ ] Hiểu `ConcurrentHashMap.mappingCount()` trả `long`, và `size()` trả `int`.
- [ ] Biết `size()` bão hòa ở `Integer.MAX_VALUE` theo đặc tả ConcurrentHashMap.
- [ ] Không nhầm độ rộng `long` với khả năng tạo snapshot nguyên tử.
- [ ] Có ghi chú rõ `mappingCount` là **estimate khi map đang chịu concurrent insert/remove**.
- [ ] Dùng mappingCount như **gauge/cardinality observation**, không dùng làm nguồn sự thật cho quota/security/billing.
- [ ] Phân biệt **mapping count** với số put/update, số event, số task đang chạy và memory consumption.
- [ ] Biết `LongAdder.sum` không tự cho snapshot khi đang bị tăng từ nhiều luồng.
- [ ] Không dùng `map.mappingCount() < max` rồi `put` để enforce capacity.
- [ ] Không tin `putIfAbsent`/`computeIfAbsent` per-key có thể tự enforce global cardinality.
- [ ] Nếu cần quota exact, đã phối hợp **tất cả** con đường ghi làm thay đổi key count.
- [ ] Nếu nhiều JVM chia sẻ dữ liệu, quota được quản lý ở nguồn phối hợp chung, không chỉ synchronized local.
- [ ] Không dùng `isEmpty` đơn lẻ để kết luận workflow hoàn tất.
- [ ] Không dùng `keySet`/`entrySet`/`stream.count` làm snapshot nhất quán khi map đang thay đổi.
- [ ] Khi cần dữ liệu chính xác sau batch, đã có completion barrier để biết writers xong.
- [ ] Có test tái hiện TOCTOU bằng latch thay vì sleep/race may rủi.
- [ ] Có test replace không đổi cardinality, remove giảm count, histogram tách key/event.
- [ ] Không cấp phát hàng tỷ phần tử chỉ để test giới hạn kiểu `int`.
- [ ] Có policy chuyển đổi `long` sang giao diện chỉ hỗ trợ int, tránh narrowing overflow.
- [ ] Không phụ thuộc field nội bộ của một bản OpenJDK; dựa trên Javadoc và public API.
- [ ] Có metrics về độ trễ, heap, GC, số request và cardinality theo đúng ý nghĩa từng phép đo.

## 22. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — ConcurrentHashMap: mappingCount, size, cảnh báo aggregate status methods, weakly consistent iterator, null và frequency-map LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
2. [Oracle Java SE 26 — ConcurrentMap: atomic putIfAbsent và các thao tác cập nhật per-key](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)
3. [Oracle Java SE 26 — LongAdder: sum không là atomic snapshot khi có cập nhật đồng thời](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
4. [Oracle Java SE 26 — CountDownLatch: thiết kế test với tín hiệu đồng bộ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
5. [Oracle Java SE 26 — CompletableFuture: allOf và join để đợi các worker đã hoàn tất](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
6. [Oracle Java SE 26 — ExecutorService: quản lý vòng đời thread pool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
7. [Oracle Java SE 26 — Map: interface size và contract key/value](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
8. [OpenJDK source — ConcurrentHashMap.java: chi tiết triển khai để tham khảo, không phải API guarantee](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java)

**Thông điệp cần nhớ:** `mappingCount()` giúp **quan sát số mapping bằng kiểu `long`**, nhưng trong lúc map có cập nhật đồng thời, nó là **ước lượng**, không phải phép chụp ảnh nguyên tử và không thể làm điều kiện quản lý quota theo kiểu **đọc trước – ghi sau**. Khi nghiệp vụ cần giới hạn hoặc thống kê nhất quán tuyệt đối, hãy thiết kế **protocol phối hợp các writer** hoặc một nguồn dữ liệu có transaction đúng yêu cầu; khi chỉ cần giám sát gần đúng, `mappingCount()` là công cụ phù hợp.
