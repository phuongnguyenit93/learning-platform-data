# ConcurrentHashMap: Iterator nhất quán yếu và cập nhật đồng thời trong Java

Khi một thread duyệt `Map` trong lúc thread khác thêm, sửa hoặc xóa phần tử, ta phải trả lời hai câu hỏi riêng biệt: **các thao tác có an toàn khi chạy đồng thời không?** và **iterator quan sát được phiên bản dữ liệu nào?** Trong Java, `ConcurrentHashMap<K,V>` được thiết kế để nhiều thread truy cập và cập nhật đồng thời, nhưng **iterator của nó không cung cấp một snapshot nguyên tử của toàn bộ map**.

Một iterator từ `ConcurrentHashMap` được gọi là **weakly consistent iterator — iterator nhất quán yếu**. Nó có thể duyệt map khi các thread khác thay đổi nội dung mà **không ném `ConcurrentModificationException` chỉ vì cập nhật đồng thời**. Tuy nhiên, kết quả quan sát có thể chứa một số cập nhật mới và không chứa những cập nhật khác; không được suy rằng iterator ghi lại chính xác trạng thái map ở một thời điểm duy nhất.

~~~java
ConcurrentHashMap<String, Integer> counts =
    new ConcurrentHashMap<>();

counts.put("A", 1);
counts.put("B", 2);

Iterator<String> cursor = counts.keySet().iterator();

// Trong lúc cursor còn tồn tại, một thread khác có thể:
counts.put("C", 3);

// Việc duyệt cursor không fail-fast chỉ vì map đổi,
// nhưng không được khẳng định cursor chắc chắn thấy "C".
while (cursor.hasNext()) {
    String key = cursor.next();
    System.out.println(key);
}
~~~

Đây là **đoạn minh họa**, cần imports `ConcurrentHashMap` và `Iterator`. Thứ tự in và việc có quan sát `"C"` hay không **không phải output cố định**. Điều chắc chắn cần học là hợp đồng **không fail-fast, không snapshot, không thứ tự duyệt cố định**.

Bài thuộc mục **ConcurrentHashMap** và tập trung vào **iterator nhất quán yếu khi có cập nhật đồng thời**, các view `keySet`/`values`/`entrySet`, `Spliterator`, quan hệ happens-before theo từng khóa, giới hạn của `size` và phép tổng hợp, cách cập nhật atomically, xóa qua iterator, lấy snapshot đúng cách, thiết kế sản phẩm và kiểm thử. Các API trình bày có từ Java 8 hoặc được gắn nhãn phiên bản rõ ràng, **vẫn hiện hành trong Java hiện đại**.

## 1. “Weakly consistent” thực chất bảo đảm gì?

Theo tài liệu chính thức của `ConcurrentHashMap`:

- Các phép lấy dữ liệu như `get` thường **không chặn** và có thể chồng lấp với `put`, `remove`.
- Iterator, Spliterator và Enumeration của map phản ánh các phần tử từ trạng thái bảng băm **ở một thời điểm nào đó kể từ lúc đối tượng duyệt được tạo ra**.
- Chúng **không ném `ConcurrentModificationException`** khi map bị cập nhật.
- **Mỗi iterator được thiết kế để dùng bởi một thread tại một thời điểm**.
- Các phép trạng thái tổng hợp như `size`, `isEmpty`, `containsValue` dưới tải ghi đồng thời có thể chỉ phản ánh **trạng thái tạm thời**, phù hợp cho quan sát/ước lượng chứ không thích hợp làm điều kiện điều khiển nghiệp vụ đòi snapshot chính xác.

**Chữ “weakly” không có nghĩa hoạt động tùy tiện hoặc thiếu an toàn dữ liệu.** Map vẫn có bảo đảm concurrency cho các thao tác cụ thể; điểm yếu nằm ở **tính nhất quán của toàn bộ lần duyệt** khi thế giới xung quanh đang thay đổi.

### 1.1. Có thể thấy cập nhật mới, nhưng không bắt buộc thấy hết

Giả sử ban đầu map có ba khóa `A`, `B`, `C`. Iterator được tạo, sau đó:

~~~text
Thread duyệt:  tạo iterator ---- đọc A ---- đọc ... ---- kết thúc
Thread ghi:                     put(D) --- remove(B) --- replace(C)
~~~

Một lần duyệt có thể gặp `D` hoặc không, có thể gặp `B` trước hoặc sau lúc `remove(B)` có hiệu lực, và có thể đọc giá trị cũ hoặc mới của `C` tùy thời điểm từng thao tác được quan sát. Đừng viết kiểm thử đòi chính xác một tập kết quả cho mọi lịch chạy đồng thời.

**Không nên khẳng định ngược lại:** iterator sẽ bỏ qua mọi thay đổi sau khi được tạo. Đó sẽ là **snapshot iterator**, không phải hợp đồng của `ConcurrentHashMap`.

### 1.2. Không cam kết thứ tự phần tử

`ConcurrentHashMap` là hash map, không phải `SortedMap` hay cấu trúc có thứ tự encounter cố định. `entrySet().iterator()` có thể trả các khóa theo một thứ tự khác với thứ tự `put`. Resize, cập nhật, cấu trúc bảng và scheduling làm thứ tự càng không thích hợp để làm hợp đồng ứng dụng.

~~~java
for (String key : map.keySet()) {
    // Không được dựa vào key xuất hiện theo thứ tự chèn.
}
~~~

Đây là mã minh họa, `map` là `ConcurrentHashMap` được tạo trước. Nếu chỉ cần **sắp xếp dữ liệu sau khi các writer dừng**, copy hoặc thu các giá trị rồi dùng `TreeMap`, `TreeSet` hoặc `List.sort`. Việc sắp xếp những giá trị được chọn **không tự biến lần duyệt dưới concurrent writes thành snapshot đầy đủ**.

### 1.3. Không có lỗi ConcurrentModificationException không đồng nghĩa kết quả là giao dịch

`ConcurrentModificationException` thường dùng như cơ chế *fail-fast*, cố phát hiện sửa đổi cấu trúc không được phép khi duyệt một collection không có hợp đồng concurrent tương ứng. Iterator nhất quán yếu **không sử dụng kiểu bảo đảm fail-fast này**, nhưng đó không phải bằng chứng lần duyệt tương đương một truy vấn database với isolation level snapshot.

Nếu một workflow phải thấy **tất cả và chỉ các record tồn tại tại thời điểm T**, chỉ một `ConcurrentHashMap` + iterator không đủ điều kiện.

## 2. So sánh với iterator fail-fast và snapshot

| Kiểu iterator | Ví dụ | Khi nguồn bị cập nhật đồng thời | Có snapshot cố định? |
| --- | --- | --- | --- |
| **Weakly consistent** | `ConcurrentHashMap.keySet().iterator()` | Không ném `ConcurrentModificationException` chỉ do concurrent update; có thể phản ánh một phần thay đổi | **Không** |
| **Fail-fast, best-effort** | `HashMap.keySet().iterator()` | Có thể ném `ConcurrentModificationException`; không phải cơ chế bảo đảm an toàn đồng bộ | **Không** |
| **Snapshot-style** | Một số iterator của `CopyOnWriteArrayList` | Duyệt mảng trạng thái tại thời điểm tạo iterator; thay đổi sau đó không hiện vào iterator | **Có**, theo hợp đồng collection đó |
| **Bản sao khi quiescent** | `new HashMap<>(concurrentMap)` sau khi toàn bộ writer hoàn tất | Dữ liệu bản sao không còn bị các sửa đổi sau này trên map gốc làm thay đổi | **Có tại lúc copy nếu không có writer đồng thời**, theo ngữ cảnh được kiểm soát |

Đây là **bảng so sánh ngữ nghĩa**, không phải lời khuyên chuyển mọi chương trình sang một collection khác. `CopyOnWriteArrayList` thích hợp với workload nhiều đọc/ít ghi, nhưng có chi phí copy khi update và không thay thế đơn giản cho map key-value.

### 2.1. Fail-fast không phải khóa đồng bộ

Một số người nghĩ: “`HashMap` sẽ ném lỗi nếu bị sửa lúc duyệt, nên dùng trong multi-thread vẫn an toàn nếu bắt exception.” Điều đó **sai**. Tài liệu `ConcurrentModificationException` lưu ý fail-fast có tính best-effort và **không được dùng làm cơ sở để chương trình đúng**.

Nếu nhiều thread sửa `HashMap` không đồng bộ, bạn có data race và các vấn đề concurrency của collection. Đừng coi exception như một cơ chế bảo vệ dữ liệu. Chọn `ConcurrentHashMap` khi cần các thao tác concurrent được hỗ trợ; chọn cơ chế đồng bộ khác nếu cần tính nhất quán mạnh.

### 2.2. Snapshot iterator khác snapshot của toàn bộ hệ thống

Ngay cả khi copy map sau khi dừng các writer, bản sao chỉ phản ánh **dữ liệu map đó**; nó không tự khóa transaction database hoặc snapshot các hệ thống khác. Nếu dữ liệu trong `V` là object mutable và các thread tiếp tục sửa nội dung object đó, **shallow copy** vẫn chia sẻ reference đến cùng giá trị mutable.

Do đó hãy phân biệt:
- **Snapshot cấu trúc mapping:** tập khóa → value reference được copy.
- **Snapshot nội dung sâu:** các value mutable cũng phải được sao chép/đóng băng theo quy tắc riêng.
- **Snapshot nhiều tài nguyên:** cần giao thức nhất quán/transaction/cơ chế versioning ở cấp hệ thống.

## 3. Những view nào cung cấp iterator nhất quán yếu?

`ConcurrentHashMap` cung cấp ba view cơ bản được hỗ trợ trực tiếp bởi map:

| View | Duyệt gì? | Thay đổi khi map đổi? | Iterator/Spliterator |
| --- | --- | --- | --- |
| `keySet()` | Khóa `K` | Có | Weakly consistent |
| `values()` | Giá trị `V` | Có | Weakly consistent |
| `entrySet()` | Các cặp `Map.Entry<K,V>` | Có | Weakly consistent |

**View là live, backed by map**, không phải một danh sách đã chép sẵn. Thay đổi `map.put`, `map.remove` có thể được phản ánh trong view khi quan sát; thao tác xóa qua view cũng có thể xóa mapping trong map.

~~~java
ConcurrentHashMap<String, Integer> map =
    new ConcurrentHashMap<>();

map.put("alpha", 1);

Set<String> keys = map.keySet();
map.put("beta", 2);

System.out.println(keys.contains("beta")); // true
~~~

Đây là minh họa, cần import `Set` và `ConcurrentHashMap`. Việc gọi `contains` sau `put` đã hoàn tất trên cùng thread xác nhận view là backed view.

### 3.1. `keySet()`

`keySet()` trả `ConcurrentHashMap.KeySetView<K,V>`. Với bản view không định nghĩa mapped value để thêm mới, các thao tác như `add`/`addAll` không được hỗ trợ. Nhưng **`remove`, `clear`, `removeAll`, `retainAll` và `Iterator.remove` được hỗ trợ** và tác động lên map gốc.

~~~java
ConcurrentHashMap<String, Integer> map =
    new ConcurrentHashMap<>();
map.put("obsolete", 1);

Iterator<String> it = map.keySet().iterator();
String key = it.next();
it.remove();

System.out.println(map.containsKey(key)); // false
~~~

Đây là minh họa single-thread, vì map chỉ có một khóa. `Iterator.remove` được gọi **sau khi `next` trả một khóa**, theo hợp đồng Iterator. Đừng tuyên bố “iterator của ConcurrentHashMap không cho remove” — Javadoc của `keySet` nêu rõ hỗ trợ.

### 3.2. `values()`

`values()` là một `Collection<V>` backed by map. Nó có thể chứa **nhiều giá trị bằng nhau** từ nhiều khóa; không phải `Set<V>`. Iterator của view vẫn weakly consistent, và có hỗ trợ xóa mapping qua `Iterator.remove`/`Collection.remove` theo hợp đồng.

~~~java
Collection<Integer> view = map.values();

for (Integer value : view) {
    // Quan sát giá trị nhưng không có khóa K trực tiếp.
}
~~~

Nếu cần biết mapping nào đã tạo giá trị đó, dùng `entrySet` hoặc `forEach((key,value) -> ...)` thay vì cố tìm lại khóa bằng cách quét lần hai (dễ bị thay đổi giữa hai lượt).

### 3.3. `entrySet()`

`entrySet()` cho phép đọc `key` và `value` cùng trong một cặp:

~~~java
for (Map.Entry<String, Integer> entry : map.entrySet()) {
    String key = entry.getKey();
    Integer value = entry.getValue();
    // Dùng cặp quan sát được tại bước duyệt này.
}
~~~

Từng entry phản ánh mapping được iterator trả tại thời điểm quan sát, nhưng **không biến tất cả entry trong vòng lặp thành một bức ảnh nhất quán**. Nếu một writer sửa khóa đã duyệt, entry cũ bạn đang giữ không tự bảo đảm đại diện cho mapping mới nhất hiện tại. Khi quyết định nghiệp vụ phụ thuộc **trạng thái hiện hành**, cần một thao tác kiểm tra/cập nhật nguyên tử ở chính map.

**Lưu ý `setValue`:** bulk operations trên `Map.Entry` của `ConcurrentHashMap` không hỗ trợ `setValue` theo Javadoc. Với thao tác sửa concurrent, ưu tiên `compute`/`merge`/`replace` trên map; đừng dựa vào việc sửa một entry lấy từ kết quả bulk để thay đổi toàn bộ trạng thái một cách nguyên tử.

### 3.4. Java for-each cũng là duyệt iterator

~~~java
for (String key : map.keySet()) {
    // Một iterator được tạo/ngầm dùng bởi for-each.
}
~~~

`for-each` không tạo snapshot. Nếu `map` thay đổi trong vòng lặp, nó vẫn có đặc tính weakly consistent của view. Chuyển từ vòng `while(iterator.hasNext())` sang for-each **không thay đổi hợp đồng nhất quán**.

## 4. Spliterator và Stream từ ConcurrentHashMap

`Spliterator` giúp phân tách công việc cho các stream hoặc thuật toán song song. Spliterator của các view `ConcurrentHashMap` báo đặc tính `Spliterator.CONCURRENT`, cho biết nguồn **cho phép cập nhật concurrent** với chính sách quan sát được mô tả trong API.

Theo Javadoc:

- `keySet().spliterator()` có `CONCURRENT`, `DISTINCT`, `NONNULL`.
- `values().spliterator()` có `CONCURRENT` và `NONNULL`, **không có `DISTINCT`** vì nhiều khóa có thể chứa cùng value.
- `entrySet().spliterator()` có `CONCURRENT`, `DISTINCT`, `NONNULL`.

~~~java
Spliterator<String> keys =
    map.keySet().spliterator();

boolean concurrent =
    keys.hasCharacteristics(Spliterator.CONCURRENT);
~~~

Đây là minh họa; cần `java.util.Spliterator`. Với keySet của ConcurrentHashMap, `concurrent` là true.

### 4.1. `CONCURRENT` không phải `SIZED` cố định

Một nguồn có thể được thêm/xóa trong lúc duyệt nên một spliterator cấp cao không thể đồng thời hứa kích thước chính xác bất biến thông qua đặc tính `SIZED` và cho phép cập nhật qua `CONCURRENT` theo contract chung. Không dùng `estimateSize()` như đếm chính xác từng item sau khi các writer đổi map.

### 4.2. `parallelStream()` không biến dữ liệu thành snapshot

~~~java
long howMany =
    map.keySet().parallelStream().count();
~~~

Đây là mã minh họa. Dưới concurrent writes, `howMany` **không phải một số record chính xác ở một instant cụ thể**. Stream pipeline có thể quan sát trạng thái thay đổi; kết quả còn phụ thuộc nguồn và tối ưu hóa của implementation.

Đặc biệt, **không cho hai thread tự ý gọi đồng thời `tryAdvance`, `forEachRemaining` hay `trySplit` trên cùng một đối tượng Spliterator**; theo hợp đồng chung, bản thân spliterator không mặc nhiên thread-safe. Thuật toán parallel stream xử lý việc chia và chuyển giao spliterator đúng cách, khác với việc một lập trình viên chia sẻ một instance spliterator mutable cho nhiều thread cùng thao tác.

### 4.3. Khi cần output có thứ tự

Có thể snapshot tại thời điểm quiescent, rồi sắp xếp:

~~~java
List<String> sorted = new ArrayList<>(map.keySet());
Collections.sort(sorted);
~~~

Đây là đoạn minh họa; nếu các writer vẫn đang chạy, việc tạo list **không có nghĩa snapshot nguyên tử**. Chỉ khi quiescence được bảo đảm, danh sách sẽ chứa dữ liệu cố định để sắp xếp. Việc dùng `sorted()` trong stream cũng **không chữa được dữ liệu thiếu/trộn phiên bản** đã quan sát trong một lượt duyệt live.

## 5. Vì sao đọc theo từng khóa vẫn có bảo đảm nhưng duyệt toàn map không nguyên tử?

`ConcurrentHashMap` được thiết kế với **bảo đảm concurrency ở mức thao tác mapping**. Theo Javadoc, một thao tác update đối với **một khóa** có quan hệ **happens-before** với phép retrieval không-null đối với khóa đó khi retrieval báo giá trị update tương ứng.

~~~java
map.put("order-7", "PAID");

String state = map.get("order-7");
// Khi đọc được "PAID", get chịu quan hệ happens-before
// với cập nhật tương ứng theo hợp đồng.
~~~

Đây là minh họa, giả sử `map` là `ConcurrentHashMap<String,String>`. Quan hệ visibility theo khóa giúp publish kết quả mapping đúng cách; **không phải giao dịch atomically trên hàng nghìn khóa**.

### 5.1. Ví dụ không có snapshot nguyên tử nhiều khóa

Giả sử thread ghi cần cập nhật cả:

~~~java
map.put("accountA", 100);
map.put("accountB", 200);
~~~

Với map khác đang đọc `get("accountA")` và `get("accountB")`, nếu có ghi đồng thời, người đọc có thể quan sát **một khóa đã mới và khóa còn lại vẫn cũ**, dù mỗi `put` riêng lẻ an toàn. `ConcurrentHashMap` không tự cung cấp transaction hai khóa.

Một iterator còn quan sát theo từng phần tử trong nhiều thời điểm: kết quả là tập hợp những **quan sát riêng lẻ**, không nhất thiết tương ứng một thời điểm logic chung.

### 5.2. Không dùng `containsValue`, `size` làm điều kiện transaction

~~~java
if (map.size() == expectedCount) {
    // Không có nghĩa trạng thái tất cả keys đã ổn định.
}
~~~

Đây là minh họa. Nếu các writer có thể thêm/xóa sau ngay thời điểm gọi `size`, số lượng không còn ràng buộc trạng thái khi thực hiện bước sau. Ngay cả một kết quả `size` chính xác tại một thời điểm cũng không đảm bảo **không có writer tiếp theo**.

`mappingCount()` trả `long` ước lượng số mapping, hữu ích khi map lớn hơn phạm vi `int`, nhưng dưới cập nhật đồng thời **không phải snapshot count**. Các phép `isEmpty()`, `containsValue()` cũng có giới hạn tương tự khi cần kiểm soát logic toàn map.

## 6. Iterator một thread, map nhiều thread: đừng nhầm

Một hiểu nhầm phổ biến:

> “ConcurrentHashMap thread-safe nên có thể cho ba thread cùng gọi `iterator.next()` trên **cùng một iterator**.”

**Không đúng.** Javadoc nói **iterators are designed to be used by only one thread at a time**. Map cho phép nhiều thread đọc/ghi; **trạng thái vị trí duyệt của một iterator riêng** không được API bảo đảm an toàn khi chia sẻ tùy tiện.

**Được hỗ trợ theo thiết kế:**

~~~text
Thread reader:   sở hữu Iterator I -------- duyệt I
Thread writer A: put(k,v), remove(k)
Thread writer B: compute(k,f), merge(k,v,f)
~~~

**Không nên dùng nếu thiếu đồng bộ riêng:**

~~~text
Thread reader A: I.hasNext(), I.next()
Thread reader B: I.hasNext(), I.next()  [cùng Iterator I]
~~~

Nếu nhiều thread cần cùng duyệt map, mỗi thread có thể tạo **iterator riêng** hoặc sử dụng các phép bulk/Stream phù hợp. Từng iterator vẫn weakly consistent; việc có nhiều iterator **không đồng bộ hóa các bức ảnh của map** giữa chúng.

### 6.1. Vòng `hasNext()` / `next()` và thời gian thay đổi

Ngay cả nếu iterator không có lỗi concurrent modification, hai thao tác `hasNext` và `next` không biến chuỗi toàn vòng lặp thành một giao dịch. Các writer có thể thay đổi cấu trúc map giữa hai lần gọi; đó chính là lý do weak consistency cần có trong hợp đồng.

Một thiết kế muốn “tôi đã duyệt mọi key tồn tại lúc bắt đầu” không thể suy điều đó chỉ từ một vòng `hasNext/next` ở map đang có writer chạy.

## 7. Cập nhật đồng thời trong lúc duyệt: thao tác nào là atomic?

`ConcurrentHashMap` hỗ trợ nhiều thao tác atomic cho **từng khóa**:

| Thao tác | Ý định |
| --- | --- |
| `putIfAbsent(key,value)` | Thêm khi khóa chưa có mapping |
| `remove(key,expectedValue)` | Xóa **chỉ khi** mapping hiện tại khớp expectedValue |
| `replace(key,oldValue,newValue)` | Thay **chỉ khi** mapping hiện tại khớp oldValue |
| `computeIfAbsent(key,f)` | Tính giá trị khi thiếu mapping; atomic theo khóa |
| `computeIfPresent(key,f)` | Biến đổi mapping đang có; atomic theo khóa |
| `compute(key,f)` | Tính mapping mới theo trạng thái khóa |
| `merge(key,value,fn)` | Gộp giá trị cho một khóa theo atomic remapping |

Các API này **vẫn được dùng trong Java hiện đại**. Chúng giúp tránh vòng `get` rồi `put` không nguyên tử khi nhiều thread cùng sửa một khóa.

### 7.1. Chọn `merge` cho đếm sự kiện

~~~java
ConcurrentHashMap<String, Integer> counts =
    new ConcurrentHashMap<>();

counts.merge("requests", 1, Integer::sum);
counts.merge("requests", 1, Integer::sum);

// counts.get("requests") == 2 khi không có writer khác.
~~~

Dưới nhiều writer, mỗi lời gọi `merge` là thao tác atomic trên mapping của khóa tương ứng, tránh lost update của kiểu:

~~~java
// PHẢN VÍ DỤ: hai thread có thể đọc cùng giá trị rồi ghi đè.
Integer current = counts.get("requests");
counts.put("requests", current == null ? 1 : current + 1);
~~~

Ở ví dụ phản chứng, hai thread có thể cùng lấy current=0/1 rồi ghi kết quả giống nhau, làm mất số lần tăng.

### 7.2. `LongAdder` cho frequency map khi contention cao

Một mẫu được Oracle nêu:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies =
    new ConcurrentHashMap<>();

frequencies
    .computeIfAbsent("events", key -> new LongAdder())
    .increment();
~~~

Đoạn minh họa, cần import `java.util.concurrent.atomic.LongAdder`. `computeIfAbsent` giúp tạo một `LongAdder` cho khóa nếu chưa có; `increment` cập nhật bộ đếm. `LongAdder` thường được dùng cho thống kê tần suất dưới cạnh tranh cao.

Tuy nhiên, **`sum()` dưới các cập nhật đang diễn ra không phải snapshot nguyên tử**. Dùng làm metric/ước lượng rất phù hợp; nếu nghiệp vụ phải khóa số lượng chính xác để thanh toán, cần thiết kế tính nhất quán khác.

### 7.3. Hàm remapping phải gọn và không tự gây phụ thuộc vòng

Các phương thức `compute`/`merge` có thể phải phối hợp update theo khóa. Không nên đặt I/O blocking dài, thao tác retry không idempotent hay recursive update map trong callback nếu có nguy cơ lock contention hoặc illegal recursive update. Tài liệu có ràng buộc về việc remapping function không được thay đổi các mapping khác theo cách không phù hợp.

Tác vụ nặng nên được thực hiện **ngoài** mapping function khi có thể, rồi dùng atomic update ngắn để công bố kết quả với điều kiện phù hợp.

## 8. Xóa trong lúc duyệt: `Iterator.remove` và `remove(key,expectedValue)`

### 8.1. `Iterator.remove` có hỗ trợ trên các view

Với `ConcurrentHashMap.keySet()`, `values()`, `entrySet()`, Javadoc nêu rõ view hỗ trợ xóa mapping qua `Iterator.remove`. Đây **không phải** một iterator read-only:

~~~java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();

map.put("expired", "OLD");
Iterator<String> cursor = map.keySet().iterator();

while (cursor.hasNext()) {
    if ("expired".equals(cursor.next())) {
        cursor.remove();
    }
}
~~~

Đoạn trên minh họa việc xóa mapping trong một lượt duyệt không có writer khác. Khi các thread khác sửa cùng khóa, **việc xóa dựa trên giá trị đã quan sát trước đó có thể không còn phù hợp** với giá trị đang tồn tại.

### 8.2. Xóa theo giá trị đã quan sát khi có race

Giả sử iterator đã đọc:

~~~text
key = "order-1"
observedValue = "EXPIRED"
~~~

Ngay sau đó, thread khác đổi mapping của khóa thành `"ACTIVE"`. Nếu reader xóa không điều kiện theo khóa, nó có thể xóa cả trạng thái mới.

Cách rõ ý hơn:

~~~java
boolean removed =
    map.remove("order-1", "EXPIRED");
~~~

`remove(key,expectedValue)` chỉ xóa nếu giá trị hiện tại **vẫn khớp** giá trị kỳ vọng lúc thao tác được thực hiện. Đây là một **conditional atomic update** hữu ích cho vòng quét dọn các mục hết hạn khi nhiều thread khác có thể gia hạn.

**Lưu ý:** một key có thể trở lại đúng cùng value cũ sau nhiều thay đổi (*ABA problem*). Nếu business cần phân biệt phiên bản lịch sử chứ không chỉ equality của value, cần thêm version/generation trong value hoặc một mô hình CAS phù hợp. `remove(key,expectedValue)` kiểm tra equality hiện tại, **không kiểm tra lịch sử biến đổi**.

### 8.3. Không xem mỗi entry đã đọc là “khóa hiện tại”

Khi duyệt `entrySet`:

~~~java
for (Map.Entry<String, Integer> entry : map.entrySet()) {
    String key = entry.getKey();
    Integer observed = entry.getValue();

    // Nếu cần thay với điều kiện:
    map.replace(key, observed, observed + 1);
}
~~~

Đây là đoạn minh họa. `replace(key,old,new)` có thể trả false nếu mapping bị xóa hoặc thay sau khi iterator đọc. Nếu bắt buộc cập nhật, phải có chính sách retry/re-read hoặc tính toán trong `compute`, chứ không đơn giản giả định thao tác chắc thành công.

## 9. `forEach` và bulk operations cũng không tạo transaction cho toàn map

Java 8 bổ sung các phép bulk chuyên dụng như:

~~~java
map.forEach((key, value) -> use(key, value));
map.forEach(Long.MAX_VALUE, (key, value) -> use(key, value));
~~~

Đây là **mã minh họa**, `use` do ứng dụng định nghĩa. Lời gọi không threshold dùng `Map.forEach`; overload có `parallelismThreshold` là bulk API riêng của `ConcurrentHashMap`.

Các bulk operations từ `ConcurrentHashMap` được thiết kế để có thể chạy trên map đang bị cập nhật mà vẫn giữ tính an toàn của thao tác concurrent. Nhưng:

- Một lần `forEach`/`search`/`reduce` dưới concurrent updates **không phản ánh snapshot nguyên tử**.
- Không được phụ thuộc **thứ tự callback**, kể cả khi bulk chạy tuần tự, vì map không có encounter order cố định.
- Khi parallel, transformation/reduction cần **associative và commutative** nếu muốn kết quả không phụ thuộc order, và nên tránh side effect trừ những callback được thiết kế phù hợp.
- Các bulk `Map.Entry` không hỗ trợ `setValue`; dùng thao tác sửa trên map thay vì tìm cách thay thông qua entry của bulk.

### 9.1. `parallelismThreshold` không phải khóa tính nhất quán

~~~java
map.forEach(
    Long.MAX_VALUE,
    (key, value) -> record(key, value)
);
~~~

Ngưỡng `Long.MAX_VALUE` suppress parallelism theo contract, nhưng **không khóa map**. Writer khác vẫn có thể cập nhật map trong khi callback được gọi. Đổi ngưỡng thành `1` cho mức parallelism tối đa không làm snapshot mạnh hơn; chỉ ảnh hưởng cách phân chia công việc/chi phí.

### 9.2. Một phép tổng hợp có thể trộn các thời điểm

Giả sử mỗi account có điểm, writer thay đổi nhiều account trong lúc reader `reduceValues`. Reader có thể cộng một số account **trước update** và một số **sau update**. Đó là một chỉ số **trong lúc đang thay đổi**, không phải tổng của một trạng thái giao dịch đồng nhất.

Với metrics quan sát, tính chất này thường chấp nhận được. Với hóa đơn, đối soát hay invariant ngân hàng, cần atomic snapshot/transaction/coordination khác.

## 10. Lấy snapshot đúng cách khi cần kết quả chính xác

### 10.1. Đơn giản: dừng hoặc phối hợp tất cả writer trước khi copy

~~~java
// Chỉ sau khi bảo đảm KHÔNG CÓ writer thay đổi map
// trong khoảng đang copy:
Map<String, Integer> snapshot = new HashMap<>(map);
~~~

Đây là **đoạn minh họa**; `map` là `ConcurrentHashMap<String,Integer>`. Sau khi copy hoàn tất, các `put/remove` sau đó lên map gốc không thay đổi **cấu trúc mapping** của `snapshot`.

Nhưng nếu writer vẫn đang cập nhật trong quá trình constructor `new HashMap<>(map)` đọc map, bản copy cũng được tạo từ các quan sát weakly consistent; nó **không phải một snapshot nguyên tử tại T** chỉ vì được lưu vào một HashMap riêng.

### 10.2. Chặn writer bằng một giao thức phối hợp

Nếu ứng dụng kiểm soát toàn bộ writers, có thể thiết kế lock/quiescence protocol để tất cả writer tạm ngừng khi snapshot. Quan trọng là **mọi writer phải tham gia giao thức đó**. Chỉ `synchronized(snapshot)` hoặc chỉ khóa ở reader mà writers không dùng cùng lock sẽ **không có tác dụng**.

Với hệ thống lớn, có thể cân nhắc:
- Bản dữ liệu immutable mới được xây rồi thay **reference nguyên tử**.
- Versioned data, epoch hoặc generation phù hợp.
- Database MVCC/transaction snapshot khi dữ liệu gốc nằm ở database.
- Event log/snapshot log cho kiểm toán và khôi phục.

Mỗi cách có chi phí về đồng bộ, bộ nhớ và latency. `ConcurrentHashMap` mặc định ưu tiên hỗ trợ các cập nhật theo khóa và duyệt yếu trong môi trường concurrent, **không cung cấp giao dịch toàn map**.

### 10.3. Phân biệt snapshot nông với sâu

~~~java
Map<String, MutableProfile> snapshot =
    new HashMap<>(liveProfiles);
~~~

Đây là **mã pseudocode**; `MutableProfile` là kiểu của ứng dụng. Bản copy chứa **cùng reference profile**: nếu thread khác sửa field trong `MutableProfile`, nội dung của bản copy vẫn có thể thay đổi. Với giá trị immutable (`String`, `Integer`, record immutable...) hoặc sao chép sâu đúng cách, rủi ro thấp hơn.

### 10.4. Không dùng snapshot để kiểm tra điều kiện rồi cập nhật map gốc thiếu CAS

Giả sử bạn copy map, quyết định key K đã có version 2 rồi định thay thành version 3. Trước khi cập nhật, một writer khác đã chuyển K lên version 4. Nếu bạn dùng `put(K,version3)` không điều kiện, bạn có thể ghi đè dữ liệu mới.

Dùng `replace(K,expectedVersion,newValue)` hoặc `compute` với kiểm tra version ở thời điểm update, hoặc transaction phù hợp. Snapshot để **đọc nhất quán** và atomic update để **ghi an toàn** là hai bài toán khác nhau.

## 11. Chương trình Java hoàn chỉnh: kiểm soát thời điểm cập nhật khi iterator còn tồn tại

Lưu chương trình dưới đây thành **`WeakIteratorConcurrentMapDemo.java`**. Mã sử dụng API Java 8, có thể biên dịch và chạy bằng **JDK 17+**. Nó mô tả:

1. `keySet()` là backed view và cập nhật `put` được phản ánh.
2. `Iterator.remove` được hỗ trợ trên view.
3. Một iterator bắt đầu đọc, **tạm dừng**, writer cập nhật/thêm/xóa, sau đó iterator **tiếp tục** mà không ném `ConcurrentModificationException`.
4. Không assert số entry mà iterator quan sát, vì **weakly consistent**.
5. Kiểm tra trạng thái map **sau khi writer đã hoàn tất**, nên những kết quả này xác định được.
6. Bốn task cập nhật cùng khóa qua `merge`, kiểm tra kết quả nguyên tử sau `Future.get`.
7. `remove(key,expectedValue)`/`replace(key,old,new)` bảo vệ cập nhật có điều kiện.
8. Snapshot được copy khi **writer đã dừng**, rồi kiểm tra copy không nhận mapping mới.
9. Spliterator keySet có các cờ `CONCURRENT`, `DISTINCT`, `NONNULL`.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.Spliterator;
import java.util.TreeSet;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class WeakIteratorConcurrentMapDemo {

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> small =
                new ConcurrentHashMap<>();
        small.put("alpha", 1);

        Set<String> view = small.keySet();
        small.put("beta", 2);

        System.out.println("viewReflectsPut="
                + view.contains("beta"));

        Iterator<String> removeCursor = view.iterator();
        while (removeCursor.hasNext()) {
            if ("alpha".equals(removeCursor.next())) {
                removeCursor.remove();
            }
        }
        System.out.println("iteratorRemove="
                + !small.containsKey("alpha"));
        System.out.println("remainingKeys="
                + new TreeSet<>(view));
        System.out.println("spliteratorConcurrent="
                + view.spliterator().hasCharacteristics(
                    Spliterator.CONCURRENT));

        ConcurrentHashMap<Integer, Integer> live =
                new ConcurrentHashMap<>();
        for (int i = 0; i < 1000; i++) {
            live.put(i, i);
        }

        CountDownLatch iteratorStarted =
                new CountDownLatch(1);
        CountDownLatch writerFinished =
                new CountDownLatch(1);

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        try {
            Future<Integer> reader = pool.submit(() -> {
                Iterator<Map.Entry<Integer, Integer>> it =
                        live.entrySet().iterator();

                int seen = 0;
                // Có dữ liệu ban đầu; writer CHƯA bắt đầu.
                if (it.hasNext()) {
                    Map.Entry<Integer, Integer> entry = it.next();
                    if (entry.getKey() == null
                            || entry.getValue() == null) {
                        throw new AssertionError("null entry");
                    }
                    seen++;
                }

                // Writer chỉ được đi tiếp sau điểm này.
                iteratorStarted.countDown();
                writerFinished.await();

                while (it.hasNext()) {
                    Map.Entry<Integer, Integer> entry = it.next();
                    if (entry.getKey() == null
                            || entry.getValue() == null) {
                        throw new AssertionError("null entry");
                    }
                    seen++;
                }
                return seen;
            });

            Future<Void> writer = pool.submit(
                    (Callable<Void>) () -> {
                        try {
                            iteratorStarted.await();

                            for (int i = 0; i < 1000; i++) {
                                live.computeIfPresent(
                                    i, (key, old) -> old + 1);
                            }
                            for (int i = 1000; i < 1500; i++) {
                                live.put(i, i);
                            }
                            for (int i = 0; i < 200; i++) {
                                live.remove(i);
                            }
                        } finally {
                            writerFinished.countDown();
                        }
                        return null;
                    });

            // Reader đã có iterator trước khi map bị đổi.
            // Không assert chính xác số entry reader quan sát.
            int observed = reader.get();
            writer.get();

            System.out.println("readerFinished=true");
            System.out.println("observedAtLeastOne="
                    + (observed >= 1));
            System.out.println("finalSize=" + live.size());
            System.out.println("updated200=" + live.get(200));
            System.out.println("removed0="
                    + !live.containsKey(0));
            System.out.println("inserted1499="
                    + (live.get(1499) == 1499));

            // Sau các writer trên, không còn ai sửa live
            // trong lúc copy, nên bản copy là snapshot mapping.
            Map<Integer, Integer> copy = new HashMap<>(live);
            live.put(2000, 2000);

            System.out.println("copySize=" + copy.size());
            System.out.println("copyHasNew="
                    + copy.containsKey(2000));
            System.out.println("liveHasNew="
                    + live.containsKey(2000));

            ConcurrentHashMap<String, Integer> hits =
                    new ConcurrentHashMap<>();
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                tasks.add(pool.submit(() -> {
                    for (int n = 0; n < 250; n++) {
                        hits.merge("events", 1, Integer::sum);
                    }
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("atomicHits="
                    + hits.get("events"));

            ConcurrentHashMap<String, String> states =
                    new ConcurrentHashMap<>();
            states.put("job", "PENDING");

            System.out.println("wrongRemove="
                    + states.remove("job", "RUNNING"));
            System.out.println("conditionalReplace="
                    + states.replace(
                        "job", "PENDING", "DONE"));
            System.out.println("staleRemove="
                    + states.remove("job", "PENDING"));
            System.out.println("currentRemove="
                    + states.remove("job", "DONE"));

        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 WeakIteratorConcurrentMapDemo.java
java WeakIteratorConcurrentMapDemo
~~~

Đầu ra **dự kiến và không phụ thuộc số phần tử iterator gặp trong lúc map đổi**:

~~~text
viewReflectsPut=true
iteratorRemove=true
remainingKeys=[beta]
spliteratorConcurrent=true
readerFinished=true
observedAtLeastOne=true
finalSize=1300
updated200=201
removed0=true
inserted1499=true
copySize=1300
copyHasNew=false
liveHasNew=true
atomicHits=1000
wrongRemove=false
conditionalReplace=true
staleRemove=false
currentRemove=true
~~~

### Phân tích chi tiết chương trình

**Nhóm view và iterator.remove:** `keySet` backed by map, nên `contains("beta")` là true sau `put`. Iterator xóa `alpha` khi không có writer khác, nên map chỉ còn `beta`, được in bằng `TreeSet` để tránh phụ thuộc thứ tự hash.

**Nhóm weakly consistent:** `live` ban đầu có 1000 mapping. Reader tạo iterator, lấy một entry và phát tín hiệu qua `iteratorStarted`. Writer đợi tín hiệu rồi cập nhật các khóa 0–999, thêm 500 khóa 1000–1499 và xóa 200 khóa 0–199. Reader đợi `writerFinished` rồi tiếp tục duyệt chính iterator đã tạo **trước khi các cập nhật xảy ra**. Việc duyệt hoàn tất mà không ném `ConcurrentModificationException`. `observedAtLeastOne=true` là điều kiện tối thiểu do reader đã đọc một entry **trước khi writer bắt đầu**; bài **không in và không assert tổng số entry trong lượt duyệt** vì kết quả ấy không được hợp đồng bảo đảm.

**Nhóm trạng thái sau writer:** lúc này tất cả thao tác của writer đã hoàn tất. Có `1000 + 500 - 200 = 1300` mapping. Khóa 200 không bị xóa và đã tăng từ 200 lên 201. Khóa 0 bị xóa. Khóa 1499 đã được thêm. Đây là những kiểm tra **sau khi đã quiescent**, nên xác định, không phải test snapshot khi vẫn ghi.

**Nhóm copy:** `copy` được tạo sau khi writer đã kết thúc và trước khi có `put(2000,2000)`. Copy có 1300 mapping và không chứa khóa 2000; map live sau đó có khóa 2000. Bản sao là độc lập **về cấu trúc mapping**, không tự deep-copy value mutable.

**Nhóm atomic merge:** bốn task cùng gọi `hits.merge("events",1,Integer::sum)` 250 lần mỗi task. Tất cả `Future.get` đã hoàn tất trước khi in `atomicHits=1000`, minh họa thao tác cập nhật nguyên tử của cùng một key; không dùng `get` rồi `put` thiếu đồng bộ.

**Nhóm conditional update:** trạng thái ban đầu `PENDING`. `remove("job","RUNNING")` false, `replace("job","PENDING","DONE")` true, `remove("job","PENDING")` false và `remove("job","DONE")` true. Các thao tác này tránh xóa/thay một value không còn khớp kỳ vọng, phù hợp với reader đã quan sát thông tin trước đó.

**Về kết quả lập lại được:** không có `Thread.sleep` hoặc phụ thuộc thứ tự hash trong expected stdout. Các latch xác định **khi nào writer được phép cập nhật**, còn `Future.get` xác nhận công việc đã hoàn tất. Chương trình thể hiện đặc tính weakly consistent mà **không ép một kết quả traversal bất định thành assert sai**.

## 12. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Hiểu weakly consistent là snapshot tại lúc iterator được tạo

Có thể thấy một số thay đổi sau khi tạo iterator. Không ghi lại số lượng hay tập key dự kiến chỉ dựa vào thời điểm tạo. Nếu yêu cầu ảnh chụp cố định, phối hợp writer hoặc dùng kiến trúc snapshot riêng.

### Lỗi 2 — Nghĩ iterator thấy ngay mọi cập nhật mới

Không có bảo đảm đó. Iterator có thể bỏ qua key mới hoặc thấy key cũ trong một số lịch thực thi. Đừng dùng một lượt duyệt để bảo đảm xử lý mọi event trong hệ thống nhiều writer.

### Lỗi 3 — Nghĩ không ném ConcurrentModificationException là giao dịch toàn map

Không fail-fast là đặc tính của cơ chế traversal, không phải atomic consistency cho mọi mapping. Một vòng lặp có thể đọc dữ liệu ở nhiều thời điểm.

### Lỗi 4 — Chia sẻ một iterator cho nhiều thread cùng next

Map thread-safe **không kéo theo** một iterator riêng an toàn khi nhiều thread cùng điều khiển vị trí. Mỗi iterator dành cho một thread, hoặc cần một giao thức điều phối rõ ràng.

### Lỗi 5 — Dùng HashMap trong concurrent writers rồi bắt ConcurrentModificationException

Fail-fast không phải synchronization; phải chọn cấu trúc concurrent hoặc bảo vệ dữ liệu bằng khóa/transaction phù hợp.

### Lỗi 6 — Dùng size/isEmpty/containsValue để điều khiển invariant

Dưới cập nhật đồng thời, các phép trạng thái tổng hợp phản ánh trạng thái tạm thời. Dùng cho metric, không dùng như một hàng rào giao dịch mà không đồng bộ.

### Lỗi 7 — Dùng mappingCount như exact snapshot

`mappingCount` trả ước lượng long dưới concurrent changes. Nó không giải quyết bài toán “tất cả mapping tại T”.

### Lỗi 8 — Dùng get rồi put cho counter

Hai thread có thể ghi đè kết quả lẫn nhau. Dùng `merge`, `compute`, `AtomicInteger`/`LongAdder` tùy loại dữ liệu và contention.

### Lỗi 9 — Dùng Iterator.remove để xóa key có giá trị đã bị thay

Nếu writer đổi giá trị sau khi bạn quan sát, xóa không điều kiện theo key có thể xóa bản ghi mới. Dùng `remove(key,expectedValue)` khi muốn guard bằng equality; dùng version khi cần ngăn ABA.

### Lỗi 10 — Tưởng keySet là bản copy

`keySet`, `values`, `entrySet` là backed views; thao tác trên view có thể ảnh hưởng map và ngược lại. Nếu cần danh sách không đổi, copy sau quiescence theo nhu cầu.

### Lỗi 11 — Nghĩ iterator của view không hỗ trợ remove

Javadoc hiện hành của `ConcurrentHashMap` nêu `Iterator.remove` được hỗ trợ trên các view. Đừng áp dụng một quy tắc của collection khác mà không đọc hợp đồng.

### Lỗi 12 — Dùng entry.setValue trong bulk operation

Javadoc ghi bulk operations trên `Map.Entry` không hỗ trợ `setValue`. Với cập nhật, dùng `compute`/`merge`/`replace` trên map; chú ý giá trị đã quan sát có thể stale.

### Lỗi 13 — Cho rằng parallelStream tạo snapshot

`parallelStream` và `Spliterator.CONCURRENT` cho phép xử lý nguồn concurrent, không khóa dữ liệu đầu vào. Kết quả dưới cập nhật đồng thời có thể phản ánh tập khác với trạng thái một thời điểm.

### Lỗi 14 — Đo kích thước từ iterator rồi so với size dưới tải ghi

Giữa `iterator` và `size()`, map có thể đổi. Hai kết quả khác nhau không nhất thiết là lỗi implementation. Nếu invariant cần đúng tuyệt đối, dừng writer hoặc đổi thiết kế.

### Lỗi 15 — Sửa đối tượng value mutable mà quên bảo vệ nội dung

Map bảo vệ mapping key → value reference, không biến mọi field bên trong value thành thread-safe. Ưu tiên immutable value, `AtomicInteger`, synchronized state hoặc data structure phù hợp.

### Lỗi 16 — Gọi callback compute/merge quá lâu

Remapping functions nên ngắn, rõ ràng, tránh blocking I/O và recursive map updates. Một operation atomic theo key có thể giữ tài nguyên nội bộ ảnh hưởng updates khác.

### Lỗi 17 — Tưởng chỉ khóa reader đủ tạo snapshot

Nếu các writer không cùng dùng khóa/giao thức, reader giữ lock riêng **không ngăn** map thay đổi. Phải bảo đảm tất cả nguồn ghi tạm dừng hoặc dùng versioned snapshot theo thiết kế.

### Lỗi 18 — Đòi output iterator luôn theo thứ tự put

ConcurrentHashMap không định nghĩa thứ tự duyệt. Để presentation ổn định, có thể sort một bản copy sau khi ngừng writers, nhưng sorting không chữa mất snapshot consistency khi vẫn ghi.

### Lỗi 19 — Lấy giá trị null như sentinel dữ liệu trong map

ConcurrentHashMap **không hỗ trợ key hoặc value null**. `get(key)==null` là chỉ báo không có mapping được trả tại thời điểm tra cứu; không dùng null làm một giá trị nghiệp vụ được lưu vào map. Nếu cần biểu diễn “chưa có dữ liệu”, dùng một object khác hoặc cấu trúc trạng thái thích hợp.

### Lỗi 20 — Tưởng cache concurrent tự cung cấp delivery guarantee

Iterator không bảo đảm sẽ bắt gặp mọi key được thêm trong lúc đang chạy. Nếu cần xử lý **mọi event đúng một lần**, dùng queue/event log, offset/ack, hoặc cơ chế delivery/transaction phù hợp. Đừng quét một ConcurrentHashMap đang thay đổi rồi coi đó là event stream đáng tin cậy.

## 13. Bài toán ứng dụng: nên dùng iterator weakly consistent khi nào?

| Bài toán | Có phù hợp không? | Lý do |
| --- | --- | --- |
| Hiển thị trạng thái sơ bộ của các session đang hoạt động | **Có thể** | Chấp nhận một vài session vừa đến/đi chưa xuất hiện |
| Monitoring số lượng cache entries | **Có thể** | Chấp nhận ước lượng dưới tải ghi |
| Quét cleanup với `remove(key,expected)` | **Có**, khi định nghĩa policy hợp lý | Mỗi phép xóa được guard theo giá trị hiện hành |
| Thống kê best-effort theo khóa | **Có thể** | Không đòi atomic tổng toàn map |
| Đối soát tài chính phải có đúng tất cả bản ghi tại T | **Không đủ** | Cần transaction/snapshot hoặc phiên bản dữ liệu |
| Export snapshot pháp lý không thiếu/không trùng | **Không đủ** | Weakly consistent không đảm bảo view nhất quán |
| Phát sự kiện một lần cho mọi key mới thêm | **Không đủ** | Iterator có thể bỏ qua thêm mới khi đang duyệt |
| Quyết định “không còn nhiệm vụ nào” chỉ qua `isEmpty` | **Không đủ** khi writers đang chạy | Sau kiểm tra có thể thêm task mới, và trạng thái tổng hợp là transient |
| Sắp xếp danh sách key khi writer đã hoàn tất | **Có** | Copy tại quiescence rồi sort |
| Dùng mỗi key làm counter cập nhật atomic | **Có** | `merge`/`compute` giúp tránh lost updates theo key |

**Cách đặt câu hỏi thiết kế:** “Nếu tôi nhìn thiếu một cập nhật vừa xảy ra, hoặc nhìn trộn các phiên bản ở hai key, có gây sai nghiệp vụ không?” Nếu câu trả lời là **có**, iterator nhất quán yếu có thể không đáp ứng mà cần giao thức nhất quán mạnh hơn.

### 13.1. Quét TTL/cleanup là case hay gặp

Một map cache nội bộ có thể chứa phiên bản record gồm `lastSeen` và `expiry`. Một thread duyệt các entry và đề xuất xóa những mục đã hết hạn. Đồng thời một writer cập nhật record để gia hạn.

Mẫu nên theo hướng:

~~~java
for (Map.Entry<String, Session> entry : sessions.entrySet()) {
    Session observed = entry.getValue();

    if (observed.expiredAt(now)) {
        sessions.remove(entry.getKey(), observed);
    }
}
~~~

Đây là **pseudocode**, `Session` là kiểu miền do ứng dụng định nghĩa, `now`/`sessions` được cung cấp từ ngoài; `Session` nên immutable hoặc có cơ chế đồng bộ phù hợp. `remove(key,observed)` guard bằng equality của value.

Tuy nhiên, nếu `Session` mutable và `equals` không phân biệt version, guard có thể chưa đủ. Nếu cần xóa dựa trên phiên bản record, gắn version vào value và làm điều kiện atomic; cần chú ý **ABA** (giá trị trở lại bằng trạng thái cũ). Vòng scan yếu cũng có thể bỏ qua một session vừa thêm hoặc vừa hết hạn; chạy quét định kỳ/queue expiration theo yêu cầu, không coi một lượt scan là bằng chứng “mọi phần tử hết hạn đã được xóa”.

### 13.2. Monitoring và báo cáo

Dashboard có thể chấp nhận số lượng entry thay đổi trong vài mili-giây, đặc biệt nếu người dùng chỉ cần xu hướng. `size`/`mappingCount` hoặc bulk reductions có thể dùng **cho quan sát** nếu bạn ghi rõ đó là approximate/transient under concurrent writes.

Nếu cần chốt số liệu cuối ngày cho kế toán, hãy đóng cửa sổ ghi hoặc lấy snapshot từ hệ lưu trữ có transaction, rồi mới tính tổng. Đừng để “không ném ConcurrentModificationException” trở thành lý do tin một báo cáo luôn chính xác.

## 14. Kiểm thử concurrency sao cho đáng tin

### 14.1. Không hardcode số entry nhìn thấy khi đang ghi

Một bài test như sau **không ổn định**:

~~~java
Iterator<Integer> it = map.keySet().iterator();
writer.start();
// Sai: assert số phần tử it duyệt == kích thước cuối
// ở mọi lần chạy, trong khi writer vẫn cập nhật.
~~~

Đây là đoạn minh họa không độc lập. Scheduling, cấu trúc bảng, resize và timing của writer có thể làm lượt duyệt quan sát tập khác nhau mà vẫn đúng hợp đồng.

### 14.2. Kiểm tra điều chắc chắn

Kiểm thử nên xác minh:

1. Iterator có thể tiếp tục duyệt khi map bị sửa sau lúc tạo mà **không ném `ConcurrentModificationException`**.
2. Mỗi key/value trả về không phải null, vì `ConcurrentHashMap` không lưu mapping null.
3. Các phép `put`/`remove`/`replace` và conditional update có kết quả đúng khi đã **quiescent**.
4. `Iterator.remove` trên view thực sự xóa mapping trong tình huống không có race.
5. `merge`/`compute` cập nhật atomic cho key khi nhiều worker cạnh tranh; kết quả cuối đo sau `Future.get`.
6. Snapshot copy được tạo khi writer đã dừng không thay đổi cấu trúc khi map gốc tiếp tục sửa.
7. `Spliterator.CONCURRENT` được báo trên view, nhưng không assert `SIZED` hoặc thứ tự.
8. Đối với output từ concurrency demo, **chỉ assert invariant được API bảo đảm**, không assert thứ tự entry hay số entry weakly consistent.

### 14.3. Dùng latch thay cho sleep

`CountDownLatch` cho phép xác định reader đã tạo và bắt đầu dùng iterator trước khi writer thay đổi map. Dùng `Future.get` để chờ worker hoàn tất. `Thread.sleep` chỉ trì hoãn một khoảng thời gian, **không bảo đảm** một thread đã đạt tới điểm mong muốn.

Một test hỏng ngẫu nhiên không nên được “chữa” bằng cách tăng thời gian sleep, mà cần làm rõ barrier, happens-before và điều kiện assert.

### 14.4. Phân biệt correctness test và performance test

Thực thi một lần không có exception không chứng minh mọi lịch chạy đúng. Có thể dùng stress test và công cụ phù hợp như **jcstress** (cho các tình huống memory/concurrency) khi cần kiểm tra sâu, nhưng bài học quan trọng nhất là **không viết postcondition mạnh hơn contract**.

Nếu tối ưu throughput, đo workload thực bằng JMH hoặc công cụ benchmark đúng cách: số reader/writer, key distribution, mức contention, resize, số core, GC, kích thước map. Không khẳng định `ConcurrentHashMap` “luôn nhanh hơn mọi cấu trúc” chỉ dựa trên một phép thử nhỏ.

## 15. Checklist cho code review và production

- [ ] Dữ liệu được duyệt có bị writer khác thay đổi không? Nếu có, sản phẩm có chấp nhận **weakly consistent** không?
- [ ] Người viết code có hiểu iterator **không snapshot** và không bảo đảm thấy mọi thêm/xóa không?
- [ ] Có dựa vào thứ tự key/entry khi duyệt không? Nếu cần sort, đã tạo bản sao đúng lúc chưa?
- [ ] Có nhầm an toàn thread của map với an toàn thread của **cùng một iterator** không?
- [ ] Có biết `keySet`/`values`/`entrySet` là backed views, không phải bản copy không?
- [ ] Có đang bắt `ConcurrentModificationException` để điều khiển luồng thay vì thiết kế concurrency đúng không?
- [ ] `Iterator.remove` có được dùng đúng sau `next` và có nguy cơ xóa value mới từ writer khác không?
- [ ] Nếu xóa dựa trên quan sát, đã cân nhắc `remove(key,expectedValue)` và version/ABA chưa?
- [ ] Nếu tăng bộ đếm, đã dùng `merge`/`compute`/`LongAdder` thay vì `get+put` thiếu atomic chưa?
- [ ] Có nhầm `size`/`mappingCount` dưới tải ghi với snapshot count chính xác không?
- [ ] Callback bulk `forEach/search/reduce` có phụ thuộc order hoặc side effect nhạy race không?
- [ ] Spliterator/parallelStream có bị hiểu sai là tự tạo ảnh chụp cố định không?
- [ ] Có bảo vệ object `V` mutable sau khi đưa reference vào map không?
- [ ] Nếu cần kiểm toán/đối soát, đã có cơ chế dừng writer, versioning hoặc database snapshot chưa?
- [ ] Nếu copy map, có bảo đảm **không có writer trong thời điểm copy** hoặc chấp nhận bản sao weakly consistent không?
- [ ] Có kiểm tra xử lý null rõ ràng, không truyền key/value null vào ConcurrentHashMap không?
- [ ] Test có dùng latch/Future thay cho sleep và tránh assert thứ tự hoặc count iterator dưới tải ghi không?
- [ ] Có policy rate limit/cleanup khi một lượt duyệt có thể bỏ lỡ entry mới không?
- [ ] Cơ chế snapshot/coordination có áp dụng cho **mọi writer** chứ không chỉ reader không?
- [ ] Có kiểm tra rằng hệ thống thật sự cần nhất quán mạnh hay chỉ cần best-effort monitoring không?

**Ghi nhớ:** `ConcurrentHashMap` cho phép nhiều thread cập nhật mapping an toàn, còn iterator từ `keySet`/`values`/`entrySet` **nhất quán yếu**: không fail-fast do cập nhật đồng thời, có thể phản ánh một phần thay đổi và **không đại diện một thời điểm nguyên tử của toàn map**. Mỗi iterator dành cho một thread; còn `compute`/`merge`/`replace`/`remove(key,expectedValue)` giúp thực hiện các cập nhật **atomic theo khóa**. Khi nghiệp vụ cần snapshot chính xác, phải phối hợp writers hoặc chọn mô hình dữ liệu/transaction phù hợp. Các nguyên tắc này **vẫn áp dụng trong Java hiện đại**.

## Tài liệu chính thức

- [Oracle Java SE 26 — ConcurrentHashMap: weakly consistent iterators, views, per-key happens-before, aggregate status, bulk operations](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Oracle Java SE 26 — Spliterator: CONCURRENT, NONNULL, DISTINCT và giới hạn thread safety của từng Spliterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 26 — Iterator: next, remove và giao thức duyệt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Iterator.html)
- [Oracle Java SE 26 — ConcurrentMap: putIfAbsent, remove(key,value), replace và atomicity](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)
- [Oracle Java SE 26 — LongAdder: frequency counters và tính chất sum under concurrency](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Oracle Java SE 26 — ConcurrentModificationException: fail-fast là best-effort](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ConcurrentModificationException.html)
