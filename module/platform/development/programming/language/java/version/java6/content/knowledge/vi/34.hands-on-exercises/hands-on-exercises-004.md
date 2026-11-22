# Chỉ mục có thứ tự và cập nhật đồng thời bằng ConcurrentSkipListMap

## 1. Mục tiêu của bài thực hành

Ứng dụng Java thường phải quản lý những bản ghi có **thứ tự theo thời điểm**, mã tăng dần hoặc một tiêu chí xếp hạng, đồng thời nhiều luồng có thể thêm, đọc, cập nhật và xóa. Dùng một `TreeMap` rồi cho nhiều threads thao tác trực tiếp là không an toàn; dùng `ConcurrentHashMap` thì thao tác theo khóa an toàn nhưng **không có trật tự khóa và truy vấn theo khoảng** giống `NavigableMap`.

**`java.util.concurrent.ConcurrentSkipListMap<K,V>`** kết hợp hai nhu cầu: một map được sắp xếp theo **thứ tự comparator/natural ordering**, đồng thời hỗ trợ các thao tác cập nhật và truy vấn theo khóa bởi nhiều threads. Đây là hiện thực chuẩn của `ConcurrentNavigableMap<K,V>`, còn được hỗ trợ và cập nhật trong Java SE 26.

Bài thực hành **“Chỉ mục có thứ tự và cập nhật đồng thời bằng ConcurrentSkipListMap”** (chủ đề cha **Thực hành**, module **Java 6**) hướng dẫn thiết kế một **in-memory ordered event index** có nhiều producers và consumers. Nội dung giữ các quy tắc Java còn áp dụng hiện nay, không giới thiệu mẫu code legacy hoặc giả định sai về tính nhất quán.

Sau bài học, bạn có thể:
1. Thiết kế khóa có **thứ tự tổng quát**: `(epochMillis, sequence)`, không mất bản ghi khi hai sự kiện trùng timestamp.
2. Dùng `firstKey`/`lastKey` và `lowerKey`/`floorKey`/`ceilingKey`/`higherKey` để tìm điểm lân cận.
3. Truy vấn **nửa mở** `[fromInclusive,toExclusive)` bằng `subMap` và hiểu vùng hiển thị *backed view*.
4. Sử dụng `headMap`, `tailMap`, `descendingMap`, `navigableKeySet`, `pollFirstEntry` và `pollLastEntry`.
5. Phân biệt độ an toàn của update từng key với **transaction đa key/map** không được `ConcurrentSkipListMap` tự đảm bảo.
6. Dùng `putIfAbsent`, `replace(key,expected,newValue)`, `remove(key,expected)`, `compute`, `computeIfAbsent` và `merge` đúng ngữ nghĩa.
7. Hiểu vì sao **remapping function có thể được thực thi nhiều lần** dù update kết quả cuối vẫn đúng.
8. Hiểu **weakly consistent iterators**: không fail-fast khi có concurrent writes, nhưng không bảo đảm snapshot atomic.
9. Tạo một chương trình **Java 17+ đầy đủ** với **8 producer threads × 800 = 6.400 events**, counters và four-consumer drain.
10. Chạy **93/93 kiểm thử PASS** trên OpenJDK 24, lặp 6 process runs đều PASS; kiểm chứng các điều kiện độc lập với thời gian interleaving.
11. Nêu rõ khi nào không nên dùng cấu trúc này thay cho database index, hàng đợi bền vững hoặc một cấu trúc snapshot có transaction.

**Các nguồn chính:** Oracle Java SE 26 Javadoc `ConcurrentSkipListMap`, `ConcurrentNavigableMap`, `NavigableMap` và `ConcurrentMap`. Code chỉ dùng Java SE standard library, được biên dịch `javac --release 17`, không yêu cầu external dependencies hay thay đổi repository.

## 2. Bản chất: ConcurrentSkipListMap là một concurrent ordered map

`ConcurrentSkipListMap<K,V>`:
- Giữ các mappings theo **thứ tự khóa**: natural ordering hoặc `Comparator<? super K>` cung cấp lúc khởi tạo.
- Thực hiện `get`, `put`, `remove` và các biến thể với **độ phức tạp kỳ vọng trung bình `O(log n)`**.
- Cho phép nhiều threads cùng đọc/ghi không cần gọi một `synchronized(map)` bên ngoài cho từng thao tác.
- Cung cấp `ConcurrentNavigableMap` với các **range views** (`subMap`/`headMap`/`tailMap`) cũng hỗ trợ concurrent updates.
- Iterator và spliterator **weakly consistent**, không phải fail-fast kiểu `TreeMap`.
- **Không chấp nhận khóa hoặc giá trị `null`**, tương tự đa số concurrent collections.

Từ skip-list là cách tổ chức dữ liệu theo nhiều tầng liên kết, giúp tìm kiếm tuần tự có bỏ qua các bước. Tuy nhiên, bạn không nên dựa vào số tầng, hình dạng nút hoặc internal layout của một JVM implementation để viết business code. Contract của JDK là điều phải tuân thủ.

### 2.1. So sánh các lựa chọn

| Cấu trúc | Thread-safe cho concurrent writes? | Sắp xếp keys? | Truy vấn range? | Phù hợp |
| --- | --- | --- | --- | --- |
| `HashMap` | Không | Không | Không | Dữ liệu chỉ do một thread/ngoại lực đồng bộ |
| `TreeMap` | Không tự động | Có | Có | Index single-threaded hoặc dưới lock ngoài |
| `Collections.synchronizedSortedMap(TreeMap)` | Có lock wrapper cho đơn lẻ ops | Có | Có nhưng cần guard traversal | Workload nhỏ có yêu cầu lock chung |
| `ConcurrentHashMap` | Có | Không | Không theo thứ tự | Lookup/update key throughput cao |
| **`ConcurrentSkipListMap`** | **Có** | **Có** | **Có** | Concurrent ordered index và range queries |

**Không mặc định `ConcurrentSkipListMap` nhanh hơn `ConcurrentHashMap`.** Nếu không cần thứ tự hay range, map băm đồng thời thường đơn giản hơn. Skip-list cần duy trì cấu trúc sắp xếp, có overhead cho pointers/nodes và comparator; kết quả phụ thuộc workload và JVM.

### 2.2. Không phải mọi tác vụ “concurrent” đều thành transaction

Một lời gọi `put` hoặc `remove` xử lý một mapping theo concurrency semantics của map. Nhưng:

```java
index.put(eventKey, event);
counts.merge("events", 1L, Long::sum);
```

Hai dòng trên là **hai bước riêng**, không phải transaction chung. Trong lúc giữa hai bước, reader có thể thấy event đã được insert nhưng counter chưa tăng. Nếu thread bị hủy sau dòng đầu, counter có thể vĩnh viễn lệch nếu không có recovery. Phần ví dụ dùng counters để học atomic update theo khóa và chỉ assert sự nhất quán **sau khi tất cả producers đã kết thúc**. Trong production, nếu cần cross-index consistency mạnh, dùng transaction/database hoặc một cơ chế commit/lock/coordination rõ ràng.

## 3. Thiết kế khóa chỉ mục: timestamp chưa đủ

Một sai lầm phổ biến là tạo:

```java
ConcurrentSkipListMap<Long, Event> byTimestamp =
        new ConcurrentSkipListMap<>();
```

rồi dùng `event.timestampMillis()` làm key. Nếu hai sự kiện có **cùng timestamp**, bản ghi sau sẽ ghi đè bản trước. Đồng hồ theo millisecond hoàn toàn có thể trùng khi nhiều threads cùng tạo sự kiện.

### 3.1. Khóa ghép có thứ tự tổng quát

Trong file demo:

```java
public record EventKey(long epochMillis, long sequence)
        implements Comparable<EventKey> {
    @Override
    public int compareTo(EventKey other) {
        int byTime = Long.compare(epochMillis, other.epochMillis);
        return byTime != 0
                ? byTime
                : Long.compare(sequence, other.sequence);
    }
}
```

Đây là **snippet** cho biết logic; file runnable ở Phần 12 có cùng ý tưởng. Lợi ích:
- Sắp xếp theo thời điểm trước, sequence sau.
- Nhiều events cùng timestamp vẫn có **key duy nhất** nếu sequence unique.
- Sử dụng `Long.compare` thay vì phép trừ `a-b` tránh tràn số khi so sánh.
- `record` immutable, giảm nguy cơ khóa bị thay đổi sau khi insert.
- `compareTo(a,b)==0` khi cả hai components bằng nhau, nhất quán với record `equals`.

**Yêu cầu kiến trúc:** Sequence phải duy nhất **trong phạm vi keyspace cần lưu**. Trong demo, producer ID và chỉ số event đảm bảo unique. Trong production nếu có nhiều processes, không thể dùng một `AtomicLong` cục bộ để mặc nhiên đảm bảo unique toàn cluster; cần ID generator phù hợp (composite source ID, UUID chuyển đổi có thứ tự được xác định, database sequence, Snowflake-like keys với kiểm chứng collision).

### 3.2. Vì sao comparator phải nhất quán với equals?

`ConcurrentSkipListMap` quyết định vị trí/đẳng thức của **khóa** dựa trên natural ordering hoặc comparator. Nếu `compare(a,b)==0` trong khi `!a.equals(b)`, map có thể coi hai keys là cùng mapping, gây hành vi bất ngờ so với contract của `Map` theo `equals`.

Đừng viết comparator chỉ so `epochMillis` khi bạn muốn lưu hàng trăm events trên cùng timestamp.

### 3.3. Không mutate key sau insertion

Dùng mutable key như một POJO có timestamp/setter và thay field sau khi đã insert khiến cấu trúc sắp xếp không còn phản ánh logical key. Dùng immutable `record EventKey`/`final class` và tạo **mapping mới** khi đổi timestamp.

## 4. Khởi tạo và thứ tự khóa

Các cách phổ biến:

```java
ConcurrentSkipListMap<EventKey, Event> index =
        new ConcurrentSkipListMap<>();
```

Natural order yêu cầu `EventKey implements Comparable<EventKey>` và các keys mutually comparable.

Hoặc:

```java
ConcurrentSkipListMap<Integer, String> descendingKeys =
        new ConcurrentSkipListMap<>(Comparator.reverseOrder());
```

Cần import `Comparator` và `ConcurrentSkipListMap`. Với comparator đảo, `firstKey()` là **khóa đứng đầu theo comparator**, ví dụ số lớn nhất, chứ không mặc định là giá trị số nhỏ nhất. Tất cả phép `lower/floor/ceiling/higher` cũng diễn giải theo ordering của map.

### 4.1. Bảng API điều hướng

Giả sử tập khóa đã ổn định là `10, 20, 30, 40`:

| Method | Kết quả khi hỏi 25 | Ý nghĩa |
| --- | ---: | --- |
| `lowerKey(25)` | 20 | Khóa lớn nhất **nhỏ hơn** 25 |
| `floorKey(25)` | 20 | Khóa lớn nhất **không lớn hơn** 25 |
| `ceilingKey(25)` | 30 | Khóa nhỏ nhất **không nhỏ hơn** 25 |
| `higherKey(25)` | 30 | Khóa nhỏ nhất **lớn hơn** 25 |
| `firstKey()` | 10 | Đầu theo comparator |
| `lastKey()` | 40 | Cuối theo comparator |

Với truy vấn tại key **20**:
- `lowerKey(20)==10`.
- `floorKey(20)==20`.
- `ceilingKey(20)==20`.
- `higherKey(20)==30`.

Nếu không có key phù hợp, `lowerKey`/`floorKey`/`ceilingKey`/`higherKey` trả **null**. Trong khi đó `firstKey`/`lastKey` ném `NoSuchElementException` khi map rỗng; `firstEntry`/`lastEntry` trả null khi rỗng. Không dùng `firstKey()` không có guard trên map có thể đã bị consumer khác drain.

## 5. Chỉ mục theo khoảng thời gian: half-open subMap

Dùng `subMap(fromKey,fromInclusive,toKey,toInclusive)` để lấy view theo khoảng. Quy ước rất hữu ích là khoảng nửa mở `[startInclusive,endExclusive)`, tránh double-count events đúng boundary giữa hai cửa sổ liên tiếp.

Ví dụ:

```java
EventKey from = new EventKey(startMillis, Long.MIN_VALUE);
EventKey to = new EventKey(endMillis, Long.MIN_VALUE);

ConcurrentNavigableMap<EventKey, Event> window =
        index.subMap(from, true, to, false);
```

Đây là snippet, cần `startMillis`/`endMillis` và `index` đã khai báo. Nó tạo **view**, không copy.

**Điều kiện để sentinel trên đúng:** Trong thực hành, sequence IDs được quy ước **không âm**, nên `Long.MIN_VALUE` luôn đứng trước mọi sequence hợp lệ tại cùng timestamp. Nếu cho phép dùng chính `Long.MIN_VALUE` làm sequence hợp lệ, bạn phải xem lại tính bao gồm của boundary theo use case. Với timestamp tính milliseconds, làm rõ đơn vị và timezone; dùng `Instant.toEpochMilli()` trong application thường dễ kiểm soát hơn là lưu chuỗi local date/time không timezone.

### 5.1. Phạm vi inclusive/exclusive

| Biểu thức | Khoảng theo comparator |
| --- | --- |
| `subMap(from,true,to,false)` | `[from,to)` |
| `subMap(from,true,to,true)` | `[from,to]` |
| `subMap(from,false,to,true)` | `(from,to]` |
| `headMap(to,false)` | keys `< to` |
| `tailMap(from,true)` | keys `>= from` |

Cần kiểm tra thứ tự `fromKey<=toKey` **theo comparator của map**. Với comparator reverse, numeric lớn hơn có thể đứng **trước**, nên thứ tự lập subMap cũng phải theo comparator đó, không theo direct numeric comparison.

### 5.2. Range view là backed view, không phải snapshot

Nếu tạo `window=index.subMap(...)`:
- `window.put(k,value)` với `k` trong khoảng làm thay đổi **index gốc**.
- `index.remove(k)` cũng phản ánh vào window.
- Thêm key ngoài khoảng vào window thường ném **`IllegalArgumentException`**.
- Iterator của window cũng **weakly consistent** khi có concurrent writers.
- Nếu code cần một snapshot cố định, phải tạo bản sao **khi đã kiểm soát giai đoạn ghi** hoặc dùng transaction/coordination ngoài map.

Không giữ một view rồi hiển thị như thể nó là “kết quả ở một thời điểm database transaction” trong lúc writers vẫn đang chạy.

### 5.3. Bằng nhau ở endpoints

Theo `NavigableMap`:
- `subMap(key,true,key,true)` là khoảng có thể gồm chính key đó.
- `subMap(key,true,key,false)` rỗng.
- `fromKey > toKey` theo comparator → `IllegalArgumentException`.

Ví dụ file test xác minh cả ba trường hợp trên.

## 6. Backed views, descending order và snapshots

### 6.1. View trả về vẫn là concurrent map

`descendingMap()` tạo một **view đảo chiều**; `navigableKeySet()` tạo một NavigableSet backed by map; `headMap/tailMap/subMap` tạo view có giới hạn.

```java
var descending = index.descendingMap();
var keys = index.navigableKeySet();
```

Hai biến đều liên kết với map gốc. `descending.put(k,v)` cập nhật bản gốc. `keys.remove(k)` xóa mapping tương ứng. Không dùng `keys.add(k)` vì key set không hỗ trợ thêm khóa thiếu value.

Đối với performance, Javadoc của `ConcurrentSkipListMap` ghi rõ **ascending views/iterators thường nhanh hơn descending**. Nếu chỉ cần lấy vài key mới nhất, cân nhắc `lastEntry`/`lowerEntry` hay một range có giới hạn; đừng lạm dụng descending scan toàn bộ map cho mọi request.

### 6.2. Entries là snapshots, không thể setValue

`Map.Entry<K,V>` được trả bởi `firstEntry()`/`lastEntry()`/`entrySet()` và các view đại diện **snapshot của mapping tại thời điểm được tạo**. Entry **không hỗ trợ `setValue`**.

```java
Map.Entry<EventKey, Event> before = index.firstEntry();
index.put(before.getKey(), newerEvent);

// before.getValue() không tự đổi thành newerEvent.
// before.setValue(newerEvent) -> UnsupportedOperationException.
```

Đây là snippet, biến `newerEvent` cần có. Muốn cập nhật thật, gọi `index.put`, `replace`, `compute` hoặc `merge` trên map.

**Lưu ý:** Nếu value bản thân là **mutable object**, snapshot entry chỉ giữ reference value vào lúc đó; nó không tạo deep copy nội dung object. Demo dùng `record Event` immutable để tránh hiểu nhầm này.

### 6.3. List.copyOf chỉ tách collection khi đã quiescent

`List.copyOf(index.values())` tạo immutable list **từ quá trình traversal**. Nếu map đang concurrent mutate, danh sách đó không nhất thiết là snapshot atomic tại một thời điểm. Trong demo, chỉ copy sau khi mọi producers đã `Future.get` hoàn tất, nên số lượng và thứ tự giá trị **ổn định**.

Để có snapshot nhất quán khi writers luôn hoạt động, cần có cơ chế khác, ví dụ external commit version, lock toàn nghiệp vụ hoặc transactional storage.

## 7. Các phép cập nhật đơn mapping và điều kiện

Một `ConcurrentSkipListMap` hỗ trợ `ConcurrentMap` methods có giá trị học tập:

| API | Ý nghĩa | Giá trị trả về quan trọng |
| --- | --- | --- |
| `putIfAbsent(k,v)` | Chỉ thêm nếu key vắng | Giá trị trước hoặc null |
| `replace(k,old,new)` | So sánh old rồi thay new | Boolean thành công/thất bại |
| `replace(k,new)` | Thay khi đã tồn tại | Giá trị trước hoặc null |
| `remove(k,expected)` | Xóa chỉ nếu value hiện tại match | Boolean |
| `compute(k,f)` | Tính mapping mới từ key và old value | New value hoặc null nếu xóa |
| `computeIfAbsent(k,f)` | Tính value nếu absent | Existing/new value hoặc null |
| `computeIfPresent(k,f)` | Tính value nếu present | New value hoặc null nếu xóa |
| `merge(k,value,f)` | Gộp increment/delta hoặc tạo mới | New value hoặc null nếu xóa |

### 7.1. Tránh read-modify-write thủ công

**Không đúng khi có concurrent writers:**

```java
Long old = counters.get("orders");
counters.put("orders", old == null ? 1L : old + 1L);
```

Hai threads có thể cùng đọc old=10, cùng put 11, làm mất một increment.

**Đúng hướng:**

```java
counters.merge("orders", 1L, Long::sum);
```

hoặc:

```java
counters.compute("orders", (key, old) ->
        old == null ? 1L : old + 1L);
```

Các snippets cần `counters` map kiểu `ConcurrentSkipListMap<String,Long>`. Với các update cạnh tranh trên cùng key, map điều phối kết quả mapping theo contract concurrency; chương trình test chứng minh không mất 6.400 increments sau khi workers kết thúc.

### 7.2. Hai phiên bản compare-and-set cho value

```java
boolean updated =
        counters.replace("orders", expectedOldValue, newValue);
```

Nếu value hiện tại khác `expectedOldValue`, method trả false. Đây là một cách làm **optimistic update** theo value. Nếu cần retry, đọc lại value và tính lại proposal trong vòng lặp có giới hạn. Đừng retry vô hạn khi có contention quá cao hoặc value updates không idempotent.

`remove(key,expectedValue)` cũng là conditional deletion, hữu ích khi xóa một bản ghi **chỉ nếu bản ghi vẫn là phiên bản mà caller đã đọc**. Nó không phải transaction giữa hai map khác nhau.

## 8. Cảnh báo quan trọng: compute/merge callbacks có thể chạy nhiều lần

**Đây là điểm dễ hiểu sai nhất.** Trong Java SE 26 Javadoc của chính `ConcurrentSkipListMap`:
- `computeIfAbsent` không đảm bảo mapping function được áp dụng **đúng một lần**.
- `computeIfPresent` không đảm bảo remapping function được áp dụng **đúng một lần một cách atomic**.
- `compute` không đảm bảo remapping function được áp dụng **đúng một lần một cách atomic**.
- `merge` không đảm bảo remapping function được áp dụng **đúng một lần một cách atomic**.

Khi nhiều threads sửa cùng key, implementation có thể gọi lại hàm remapping để tính với giá trị mới sau một lần cạnh tranh. Điều cần tránh là lẫn **kết quả update mapping** với **số lần callback Java function được thực thi**.

### 8.1. Sai: side effect trong remapping function

```java
counters.merge("orders", 1L, (oldValue, delta) -> {
    chargeCustomer(); // SAI: có thể bị gọi lặp.
    return oldValue + delta;
});
```

Đây là **anti-pattern**, `chargeCustomer()` không được định nghĩa trong snippet. Không đặt:
- Charge payment.
- Gửi email/SMS/webhook.
- Gọi HTTP request.
- Insert một record ra database.
- Cấp phát ID nghiệp vụ có side effects không thể hoàn tác.
- Ghi thêm một event vào queue chỉ vì remapping function đã chạy.

Trong các trường hợp này callback có thể chạy lại khi cạnh tranh, gây double-effects dù value cuối của map đúng.

### 8.2. Đúng: hàm thuần, retry-safe

```java
counters.merge("orders", 1L, Long::sum);

counters.compute("orders", (key, oldValue) ->
        oldValue == null ? 1L : oldValue + 1L);
```

Hàm pure theo inputs, kết quả không phụ thuộc vào số lần callback invocation. Side effect business nên xảy ra **sau khi update được xác nhận thành công** bằng một workflow có idempotency key/transaction rõ ràng.

### 8.3. Counter callback attempts để debug cũng là một side effect

File test đếm số lần vào remapping functions bằng `AtomicInteger` **chỉ để quan sát retry attempts trong JVM test**. Bài **không** dùng số attempt này làm business counter và **không** khẳng định nó luôn bằng số operations. Nếu bạn không cần đo retry, đừng đặt side effects trong lambda.

### 8.4. Kết quả null có nghĩa khác nhau theo operation

| Method | Remapping function trả null | Ý nghĩa |
| --- | --- | --- |
| `compute(k,f)` | null | Xóa mapping hiện có, hoặc giữ absent |
| `computeIfPresent(k,f)` | null | Xóa mapping hiện có |
| `computeIfAbsent(k,f)` | null | Không thêm mapping |
| `merge(k,v,f)` | null | Xóa mapping hiện có nếu đã present |

Đừng dùng null làm value lưu trong `ConcurrentSkipListMap` vì map **không cho phép null key/value**; tuy nhiên return null từ một callback có ngữ nghĩa delete/no mapping theo contract.

## 9. Weakly consistent iterator: đúng và sai

Javadoc hiện hành mô tả `ConcurrentSkipListMap` iterators/spliterators là **weakly consistent**. Khác với fail-fast iterator của nhiều collections thông thường, chúng có thể duyệt khi map bị cập nhật đồng thời mà không cần fail vì `ConcurrentModificationException`.

Nhưng:
- Không đảm bảo thấy **mọi** insertion đồng thời.
- Không đảm bảo thấy **mọi** removal theo một snapshot duy nhất.
- Không đảm bảo size của stream/collection view là bản ghi chính xác tại một thời điểm chung với các reads khác.
- Các phần tử được traversal vẫn theo thứ tự key của view tương ứng (ascending hoặc descending).
- Không có transaction/snapshot isolation chỉ vì iterator hoạt động mà không ném exception.

### 9.1. Tránh assertion về số entry lúc cùng ghi

Ví dụ test phù hợp:
1. Preseed 800 keys.
2. Tạo iterator.
3. Một writer thêm keys `800..1599` và xóa 200 khóa chẵn từ `0..398`.
4. Duyệt iterator đồng thời, xác nhận không throw, các keys đã quan sát có order.
5. **Sau khi writer Future kết thúc**, xác nhận tổng entries ổn định là `800+800-200 = 1.400`.

Không assert rằng iterator luôn nhìn thấy chính xác 800, 1.400 hay 1.600 entries: weak consistency cho phép khác nhau theo interleaving.

### 9.2. Phân biệt lỗi logic với tính nhất quán yếu

Nếu pagination:
- Page 1 đọc `first N keys`.
- Writer thêm bản ghi mới trước cursor.
- Page 2 đọc `higherKey(lastRead)`.

Bạn có thể **bỏ lỡ** bản ghi được thêm trước cursor giữa hai pages; đó là semantics của **live ordered index**. Nếu yêu cầu pagination ổn định “như một ảnh chụp database”, hãy dùng versioned snapshots/DB transactions hoặc application-level snapshot coordination.

## 10. Atomic pollFirstEntry để “lấy việc sớm nhất”

`pollFirstEntry()` xóa và trả mapping đầu tiên theo comparator, mỗi invocation tương ứng một update đơn key an toàn trước cạnh tranh. `pollLastEntry()` làm tương tự ở đầu ngược.

```java
Map.Entry<EventKey, Event> item = index.pollFirstEntry();
if (item != null) {
    Event event = item.getValue();
    // Handle this event.
}
```

Đây là snippet, `index` đã khai báo. Nếu map rỗng, method trả null.

### 10.1. Nhiều consumers có thể poll không trùng nhau

Trong chương trình:
- Tất cả producers **đã hoàn tất**, không còn insert mới.
- Bốn consumers cùng gọi `pollFirstEntry()` đến khi null.
- Thu các event IDs đã remove vào `ConcurrentLinkedQueue`.
- Sau khi consumers kết thúc, kiểm tra đúng 6.400 IDs, tất cả unique và map empty.

Điều này chứng minh concurrent removal **không phát cùng mapping cho hai pollers** trong fixture. Nhưng nó **không** chứng minh exactly-once processing end-to-end:
- Nếu consumer crash sau poll trước khi persist kết quả, event có thể mất.
- Không có ack/retry/visibility timeout tự động.
- Không có persistence khi JVM restart.
- Không có blocking `take()` hay capacity backpressure tự động.

Nếu bài toán là hàng đợi công việc đáng tin cậy, cần thiết kế durable queue, task state/lease, idempotency và recovery. `ConcurrentSkipListMap` thích hợp làm **in-memory ordered work index**, không phải broker message bền vững.

### 10.2. Poll khi vẫn có producers

Nếu producers tiếp tục ghi, một consumer thấy `pollFirstEntry()==null` tại thời điểm đó **không chứng minh sẽ không còn events trong tương lai**. Trong demo, producers `Future.get` hoàn thành trước khi drain, nên null được phép dùng làm điều kiện kết thúc. Trong production có producers liên tục, dùng coordination signaling/condition/queue/workflow completion thay vì spin hoặc dừng chỉ dựa vào một lần empty.

## 11. Memory, performance và operational limits

### 11.1. Kỳ vọng O(log n), không đồng nghĩa constant-time

`get`/`put`/`remove` có chi phí kỳ vọng `O(log n)`. Thực tế phụ thuộc key distributions, comparator cost, contention, allocation và GC.

`size()` trong `ConcurrentSkipListMap` có thể **O(n)** và số liệu có thể không chính xác khi concurrent updates. `containsValue()` cũng tuyến tính và có thể không chính xác trong lúc map thay đổi; Javadoc cảnh báo điều này. Không scrape `size()` ở tần suất rất cao trên chỉ mục hàng triệu keys mà không đo overhead.

### 11.2. Ascending thường rẻ hơn descending

Ascending key ordered views và iterators thường được tối ưu hơn descending, theo class Javadoc. Dùng `descendingMap()` khi cần kết quả đảo nhưng profile khi nó là hot path. Đừng mặc định `descendingMap` tạo bản sao; nó vẫn backed/live.

### 11.3. Bulk operations không atomic

`putAll`, `equals`, `toArray`, `containsValue`, `clear` là ví dụ bulk operations **không bảo đảm atomic** trước concurrent writers/readers. Một iterator có thể quan sát chỉ một phần batch `putAll`. Nếu yêu cầu xóa toàn range như một transaction, `headMap(cutoff).clear()` chỉ là hàng loạt xóa, không phải một bước atomic.

### 11.4. Giới hạn tài nguyên

Một in-memory index có thể tăng vô hạn nếu không:
- Đặt retention/TTL.
- Xóa data cũ có kiểm soát.
- Giới hạn producers/concurrency.
- Thiết kế bounded payload size.
- Áp backpressure và quotas.
- Theo dõi heap/GC/retained keys.
- Có recovery từ nguồn dữ liệu bền vững khi restart.

Map không tự quản lý TTL, không tự lưu disk, không tự replicate nhiều JVMs. `pollFirstEntry` hoặc range cleanup chỉ là memory operations, không nên dùng như database transaction.

## 12. Thực hành: chỉ mục sự kiện có nhiều producers/consumers

Chương trình Java độc lập `ConcurrentSkipListIndexDemo.java` triển khai:
- `record EventKey(epochMillis,sequence)` làm comparable key.
- `record Event(id,category,payload)` immutable value.
- Ordered navigation trên một index nhỏ để kiểm thử ranh giới.
- Bounded range view `[startInclusive,endExclusive)` và live writes.
- Reverse comparator, descending views, snapshot entries/`List.copyOf`.
- Null key/value rejection.
- Key-set spliterator flags `CONCURRENT`/`SORTED`/`ORDERED`/`NONNULL`.
- `putIfAbsent`, CAS-style `replace/remove`, `compute`, `merge`.
- 8 producer threads dùng `CountDownLatch`, mỗi thread chèn 800 events (tổng 6.400).
- Bảng đếm `even`/`odd` bằng `merge` và tổng `all` bằng `compute`.
- Range query lấy đúng 1.600 events ở 4/16 buckets thời gian (sau producers hoàn thành).
- 4 consumer threads gọi `pollFirstEntry`, xác minh 6.400 IDs unique.
- Một weak iterator đồng thời với writer: reader không giả định số elements đang quan sát.
- Timeouts `Future.get(timeout)`, shutdown/awaitTermination trong `finally` để fixture không để lại thread pool.

**Chạy độc lập:** Chỉ dùng Java SE standard library, không chạy database, không mở network, không sửa file repository, không cần Maven/Gradle.

### 12.1. Toàn bộ file `ConcurrentSkipListIndexDemo.java`


```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NavigableSet;
import java.util.Set;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ConcurrentSkipListIndexDemo {
    private static int passed;

    public record EventKey(long epochMillis, long sequence)
            implements Comparable<EventKey> {
        @Override
        public int compareTo(EventKey other) {
            int time = Long.compare(epochMillis, other.epochMillis);
            return time != 0 ? time : Long.compare(sequence, other.sequence);
        }
    }

    public record Event(long id, String category, String payload) {}

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    static boolean rejects(Class<? extends Throwable> expected, Runnable work) {
        try {
            work.run();
            return false;
        } catch (Throwable actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError("Wrong exception " + actual, actual);
            }
            return true;
        }
    }

    static <T> List<T> snapshot(Iterable<T> source) {
        ArrayList<T> copy = new ArrayList<>();
        for (T value : source) copy.add(value);
        return List.copyOf(copy);
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker start timeout");
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new AssertionError("Worker interrupted", interrupted);
        }
    }

    static void readAndNavigate() {
        ConcurrentSkipListMap<EventKey, Event> index =
                new ConcurrentSkipListMap<>();
        EventKey a = new EventKey(100, 1);
        EventKey b = new EventKey(100, 2);
        EventKey c = new EventKey(101, 1);
        EventKey d = new EventKey(102, 1);
        EventKey e = new EventKey(103, 1);
        index.put(d, new Event(4, "late", "D"));
        index.put(a, new Event(1, "early", "A"));
        index.put(e, new Event(5, "late", "E"));
        index.put(c, new Event(3, "middle", "C"));
        index.put(b, new Event(2, "early", "B"));

        check("key-record-has-total-order",
                a.compareTo(b) < 0 && b.compareTo(c) < 0
                        && c.compareTo(d) < 0);
        check("sorted-first-key", index.firstKey().equals(a));
        check("sorted-last-key", index.lastKey().equals(e));
        check("natural-comparator-is-null", index.comparator() == null);
        check("get-by-composite-key", index.get(c).payload().equals("C"));
        check("ascending-key-order",
                snapshot(index.navigableKeySet())
                        .equals(List.of(a, b, c, d, e)));
        check("descending-key-order",
                snapshot(index.descendingKeySet())
                        .equals(List.of(e, d, c, b, a)));
        check("lower-key-strict", index.lowerKey(c).equals(b));
        check("floor-key-inclusive", index.floorKey(c).equals(c));
        check("ceiling-key-inclusive", index.ceilingKey(c).equals(c));
        check("higher-key-strict", index.higherKey(c).equals(d));
        check("lower-key-null-at-beginning", index.lowerKey(a) == null);
        check("higher-key-null-at-end", index.higherKey(e) == null);

        EventKey low = new EventKey(100, Long.MIN_VALUE);
        EventKey high = new EventKey(102, Long.MIN_VALUE);
        ConcurrentNavigableMap<EventKey, Event> window =
                index.subMap(low, true, high, false);
        check("time-window-half-open-100-through-101",
                snapshot(window.navigableKeySet())
                        .equals(List.of(a, b, c)));
        check("time-window-values-sorted",
                snapshot(window.values()).stream()
                        .map(Event::payload).toList()
                        .equals(List.of("A", "B", "C")));
        EventKey inRange = new EventKey(101, 2);
        window.put(inRange, new Event(6, "middle", "F"));
        check("submap-is-backed-write-through",
                index.containsKey(inRange));
        index.remove(inRange);
        check("parent-removal-reflects-in-submap",
                !window.containsKey(inRange));
        check("out-of-range-write-rejected",
                rejects(IllegalArgumentException.class,
                        () -> window.put(e, new Event(6, "bad", "X"))));
        check("headmap-exclusive",
                snapshot(index.headMap(c, false).navigableKeySet())
                        .equals(List.of(a, b)));
        check("tailmap-inclusive",
                snapshot(index.tailMap(c, true).navigableKeySet())
                        .equals(List.of(c, d, e)));
        check("equal-endpoints-both-inclusive",
                index.subMap(c, true, c, true).size() == 1);
        check("equal-endpoints-half-open-empty",
                index.subMap(c, true, c, false).isEmpty());
        check("descending-map-is-backed",
                index.descendingMap().get(d).equals(index.get(d)));
        EventKey p = new EventKey(104, 1);
        index.descendingMap().put(p, new Event(7, "late", "P"));
        check("descending-view-write-through",
                index.lastKey().equals(p));
        index.remove(p);

        Map.Entry<EventKey, Event> firstSnapshot = index.firstEntry();
        index.put(a, new Event(100, "changed", "A2"));
        check("entry-snapshot-not-live-value",
                firstSnapshot.getValue().payload().equals("A"));
        check("entry-snapshot-reflects-old-key",
                firstSnapshot.getKey().equals(a));
        check("entry-setvalue-unsupported",
                rejects(UnsupportedOperationException.class,
                        () -> firstSnapshot.setValue(
                                new Event(200, "invalid", "Y"))));
        List<Event> copied = List.copyOf(index.values());
        index.remove(a);
        check("copied-snapshot-independent",
                copied.size() == 5
                        && copied.stream().anyMatch(
                        event -> event.payload().equals("A2")));
        check("entryset-backed-view",
                index.entrySet().size() == 4);

        check("null-key-rejected",
                rejects(NullPointerException.class,
                        () -> index.put(null, new Event(8, "bad", "N"))));
        check("null-value-rejected",
                rejects(NullPointerException.class,
                        () -> index.put(a, null)));
        check("null-lookup-rejected",
                rejects(NullPointerException.class, () -> index.get(null)));
        check("null-boundary-rejected",
                rejects(NullPointerException.class,
                        () -> index.tailMap(null, true)));

        int characteristics = index.navigableKeySet()
                .spliterator().characteristics();
        check("spliterator-concurrent",
                (characteristics & Spliterator.CONCURRENT) != 0);
        check("spliterator-sorted",
                (characteristics & Spliterator.SORTED) != 0);
        check("spliterator-ordered",
                (characteristics & Spliterator.ORDERED) != 0);
        check("spliterator-nonnull",
                (characteristics & Spliterator.NONNULL) != 0);

        ConcurrentSkipListMap<Integer, String> reverse =
                new ConcurrentSkipListMap<>(Comparator.reverseOrder());
        reverse.put(1, "one");
        reverse.put(3, "three");
        reverse.put(2, "two");
        check("custom-comparator-first-key", reverse.firstKey() == 3);
        check("custom-comparator-last-key", reverse.lastKey() == 1);
        check("custom-comparator-descending-reverses-back",
                snapshot(reverse.descendingKeySet()).equals(
                        List.of(1, 2, 3)));
        check("reverse-submap-follows-comparator",
                snapshot(reverse.subMap(3, true, 1, true)
                        .navigableKeySet()).equals(List.of(3, 2, 1)));
        check("natural-comparator-separate-from-reverse",
                reverse.comparator() != null);
    }

    static void atomicIndividualUpdates() {
        ConcurrentSkipListMap<String, Long> counters =
                new ConcurrentSkipListMap<>();
        check("putifabsent-creates-once",
                counters.putIfAbsent("orders", 1L) == null);
        check("putifabsent-does-not-overwrite",
                counters.putIfAbsent("orders", 7L) == 1L);
        check("replace-conditional-rejects-stale",
                !counters.replace("orders", 2L, 9L));
        check("replace-conditional-success",
                counters.replace("orders", 1L, 9L));
        check("replace-has-new-value",
                counters.get("orders") == 9L);
        check("remove-conditional-rejects-stale",
                !counters.remove("orders", 1L));
        check("remove-conditional-success",
                counters.remove("orders", 9L));
        check("remove-really-deleted",
                !counters.containsKey("orders"));

        check("merge-inserts-when-absent",
                counters.merge("counter", 1L, Long::sum) == 1L);
        check("merge-updates-when-present",
                counters.merge("counter", 2L, Long::sum) == 3L);
        check("compute-reads-and-updates",
                counters.compute("counter",
                        (k, old) -> old + 4L) == 7L);
        check("computeifpresent-updates",
                counters.computeIfPresent("counter",
                        (k, old) -> old * 2L) == 14L);
        check("computeifpresent-absent-returns-null",
                counters.computeIfPresent("missing",
                        (k, old) -> old + 1) == null);
        check("computeifabsent-creates",
                counters.computeIfAbsent("new",
                        k -> 11L) == 11L);
        check("computeifabsent-keeps-existing",
                counters.computeIfAbsent("new",
                        k -> 99L) == 11L);
        check("compute-null-removes-mapping",
                counters.compute("new", (k, v) -> null) == null
                        && !counters.containsKey("new"));
        check("merge-null-removes-mapping",
                counters.merge("counter", 1L,
                        (left, right) -> null) == null
                        && !counters.containsKey("counter"));
        check("computeifabsent-null-stays-absent",
                counters.computeIfAbsent("missing",
                        k -> null) == null
                        && !counters.containsKey("missing"));
    }

    static void concurrentIndexAndCounters() throws Exception {
        final int producers = 8;
        final int perProducer = 800;
        final int expected = producers * perProducer;
        final long epoch = 2_000L;
        ConcurrentSkipListMap<EventKey, Event> index =
                new ConcurrentSkipListMap<>();
        ConcurrentSkipListMap<String, Long> byCategory =
                new ConcurrentSkipListMap<>();
        ConcurrentSkipListMap<String, Long> total =
                new ConcurrentSkipListMap<>();
        AtomicInteger mergeFunctionAttempts = new AtomicInteger();
        AtomicInteger computeFunctionAttempts = new AtomicInteger();
        ExecutorService workers = Executors.newFixedThreadPool(producers);
        CountDownLatch gate = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int worker = 0; worker < producers; worker++) {
                final int producer = worker;
                futures.add(workers.submit(() -> {
                    await(gate);
                    for (int i = 0; i < perProducer; i++) {
                        long id = (long) producer * perProducer + i;
                        long timestamp = epoch + (i % 16);
                        String category = i % 2 == 0 ? "even" : "odd";
                        EventKey key = new EventKey(timestamp, id);
                        Event old = index.putIfAbsent(
                                key, new Event(id, category, "p-" + id));
                        if (old != null)
                            throw new AssertionError("Duplicate key");
                        byCategory.merge(category, 1L, (left, right) -> {
                            mergeFunctionAttempts.incrementAndGet();
                            return left + right;
                        });
                        total.compute("all", (keyText, previous) -> {
                            computeFunctionAttempts.incrementAndGet();
                            return previous == null ? 1L : previous + 1L;
                        });
                    }
                }));
            }
            gate.countDown();
            for (Future<?> future : futures) {
                future.get(30, TimeUnit.SECONDS);
            }
        } finally {
            workers.shutdownNow();
            if (!workers.awaitTermination(10, TimeUnit.SECONDS))
                throw new AssertionError("Producer pool did not terminate");
        }

        check("concurrent-write-no-lost-index-events",
                index.size() == expected);
        check("concurrent-write-all-count-exact",
                total.get("all") == (long) expected);
        check("concurrent-merge-even-count-exact",
                byCategory.get("even") == expected / 2);
        check("concurrent-merge-odd-count-exact",
                byCategory.get("odd") == expected / 2);
        check("concurrent-merge-function-can-be-retried",
                mergeFunctionAttempts.get() >= expected - 2);
        check("concurrent-compute-function-can-be-retried",
                computeFunctionAttempts.get() >= expected);
        check("first-index-timestamp-correct",
                index.firstKey().epochMillis() == epoch);
        check("last-index-timestamp-correct",
                index.lastKey().epochMillis() == epoch + 15);

        EventKey previous = null;
        Set<Long> seenIds = new HashSet<>();
        boolean ascending = true;
        for (Map.Entry<EventKey, Event> entry : index.entrySet()) {
            if (previous != null && previous.compareTo(entry.getKey()) >= 0)
                ascending = false;
            previous = entry.getKey();
            seenIds.add(entry.getValue().id());
        }
        check("all-concurrent-keys-traversed-in-order", ascending);
        check("unique-event-identities",
                seenIds.size() == expected);
        check("last-key-seen-matches-lastentry",
                previous.equals(index.lastKey()));

        ConcurrentNavigableMap<EventKey, Event> middle =
                index.subMap(new EventKey(epoch + 4, Long.MIN_VALUE),
                        true, new EventKey(epoch + 8, Long.MIN_VALUE),
                        false);
        check("middle-time-window-count",
                middle.size() == expected / 4);
        check("middle-window-only-4-through-7",
                middle.keySet().stream().allMatch(k ->
                        k.epochMillis() >= epoch + 4
                        && k.epochMillis() < epoch + 8));
        check("time-range-reversed-rejected",
                rejects(IllegalArgumentException.class,
                        () -> index.subMap(
                                new EventKey(epoch + 8, 0), true,
                                new EventKey(epoch + 4, 0), true)));
        check("full-key-collision-protection",
                new EventKey(epoch + 4, 1).compareTo(
                        new EventKey(epoch + 4, 2)) != 0);

        ExecutorService consumers = Executors.newFixedThreadPool(4);
        ConcurrentLinkedQueue<Long> removed = new ConcurrentLinkedQueue<>();
        AtomicInteger actualRemovals = new AtomicInteger();
        try {
            List<Future<?>> drain = new ArrayList<>();
            for (int t = 0; t < 4; t++) {
                drain.add(consumers.submit(() -> {
                    for (;;) {
                        Map.Entry<EventKey, Event> item =
                                index.pollFirstEntry();
                        if (item == null) return;
                        removed.add(item.getValue().id());
                        actualRemovals.incrementAndGet();
                    }
                }));
            }
            for (Future<?> f : drain) f.get(30, TimeUnit.SECONDS);
        } finally {
            consumers.shutdownNow();
            if (!consumers.awaitTermination(10, TimeUnit.SECONDS))
                throw new AssertionError("Consumer pool did not terminate");
        }
        check("atomic-pollfirst-all-events-drained",
                actualRemovals.get() == expected);
        check("atomic-pollfirst-no-duplicate-removals",
                new HashSet<>(removed).size() == expected);
        check("atomic-pollfirst-map-empty-after-drain",
                index.isEmpty());
        check("pollfirst-returns-null-when-empty",
                index.pollFirstEntry() == null);
        check("polllast-returns-null-when-empty",
                index.pollLastEntry() == null);
    }

    static void concurrentIterationIsWeaklyConsistent() throws Exception {
        ConcurrentSkipListMap<Integer, Integer> mutable =
                new ConcurrentSkipListMap<>();
        for (int i = 0; i < 800; i++) mutable.put(i, i);
        Iterator<Map.Entry<Integer, Integer>> iterator =
                mutable.entrySet().iterator();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService writer = Executors.newSingleThreadExecutor();
        Future<?> result;
        try {
            result = writer.submit(() -> {
                await(start);
                for (int i = 800; i < 1_600; i++) {
                    mutable.put(i, i);
                }
                for (int i = 0; i < 400; i += 2) {
                    mutable.remove(i);
                }
            });
            start.countDown();
            int prior = Integer.MIN_VALUE;
            int visited = 0;
            while (iterator.hasNext()) {
                Map.Entry<Integer, Integer> entry = iterator.next();
                if (entry.getKey() <= prior)
                    throw new AssertionError("Out of key order");
                prior = entry.getKey();
                visited++;
            }
            result.get(30, TimeUnit.SECONDS);
            check("weak-iterator-iterated-with-concurrent-write",
                    visited > 0);
            check("weak-iterator-maintained-key-order",
                    prior >= 0);
            check("weak-iterator-final-map-complete",
                    mutable.size() == 1_400);
            check("weak-iterator-post-join-max-key",
                    mutable.lastKey() == 1_599);
            check("weak-iterator-removed-expected-even-keys",
                    !mutable.containsKey(0)
                            && !mutable.containsKey(398)
                            && mutable.containsKey(399));
            check("weak-iterator-new-keys-present",
                    mutable.containsKey(800)
                            && mutable.containsKey(1_599));
            check("weak-iterator-snapshot-after-quiescence",
                    snapshot(mutable.navigableKeySet()).size() == 1_400);
        } finally {
            writer.shutdownNow();
            if (!writer.awaitTermination(10, TimeUnit.SECONDS))
                throw new AssertionError("Writer pool did not terminate");
        }
    }

    static void pollAndSetViews() {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();
        map.put(3, "third");
        map.put(1, "first");
        map.put(2, "second");
        NavigableSet<Integer> keys = map.navigableKeySet();
        check("navigablekeyset-backed", keys.contains(2));
        check("keyset-remove-updates-map",
                keys.remove(2) && !map.containsKey(2));
        check("pollfirst-removes-smallest",
                map.pollFirstEntry().getKey() == 1);
        check("polllast-removes-largest",
                map.pollLastEntry().getKey() == 3);
        check("pollfirst-last-empty-map", map.isEmpty());
        check("pollfirst-last-null-when-empty",
                map.pollFirstEntry() == null
                        && map.pollLastEntry() == null);
    }

    public static void main(String[] args) throws Exception {
        readAndNavigate();
        atomicIndividualUpdates();
        concurrentIndexAndCounters();
        concurrentIterationIsWeaklyConsistent();
        pollAndSetViews();
        System.out.println("passed=" + passed);
    }
}
```

### 12.2. Biên dịch và chạy (Java 17+)

Lưu source trên trong file **`ConcurrentSkipListIndexDemo.java`** ở một thư mục thử nghiệm riêng. Với Windows PowerShell:

```powershell
javac --release 17 -encoding UTF-8 ConcurrentSkipListIndexDemo.java
java ConcurrentSkipListIndexDemo
```

Linux/macOS:

```bash
javac --release 17 -encoding UTF-8 ConcurrentSkipListIndexDemo.java
java ConcurrentSkipListIndexDemo
```

Mã không dùng preview features. `record`, `List.copyOf`, `List.toList()` và concurrency APIs dùng trong file đều khả dụng với `--release 17`. Trong một named module, các class ở đây thuộc `java.base` đã được đọc mặc định; nếu chuyển demo từ default package sang module, phải đặt tên package và bố trí source layout đúng JPMS convention.

### 12.3. Stdout **đã kiểm chứng** trên OpenJDK 24

```text
PASS key-record-has-total-order
PASS sorted-first-key
PASS sorted-last-key
PASS natural-comparator-is-null
PASS get-by-composite-key
PASS ascending-key-order
PASS descending-key-order
PASS lower-key-strict
PASS floor-key-inclusive
PASS ceiling-key-inclusive
PASS higher-key-strict
PASS lower-key-null-at-beginning
PASS higher-key-null-at-end
PASS time-window-half-open-100-through-101
PASS time-window-values-sorted
PASS submap-is-backed-write-through
PASS parent-removal-reflects-in-submap
PASS out-of-range-write-rejected
PASS headmap-exclusive
PASS tailmap-inclusive
PASS equal-endpoints-both-inclusive
PASS equal-endpoints-half-open-empty
PASS descending-map-is-backed
PASS descending-view-write-through
PASS entry-snapshot-not-live-value
PASS entry-snapshot-reflects-old-key
PASS entry-setvalue-unsupported
PASS copied-snapshot-independent
PASS entryset-backed-view
PASS null-key-rejected
PASS null-value-rejected
PASS null-lookup-rejected
PASS null-boundary-rejected
PASS spliterator-concurrent
PASS spliterator-sorted
PASS spliterator-ordered
PASS spliterator-nonnull
PASS custom-comparator-first-key
PASS custom-comparator-last-key
PASS custom-comparator-descending-reverses-back
PASS reverse-submap-follows-comparator
PASS natural-comparator-separate-from-reverse
PASS putifabsent-creates-once
PASS putifabsent-does-not-overwrite
PASS replace-conditional-rejects-stale
PASS replace-conditional-success
PASS replace-has-new-value
PASS remove-conditional-rejects-stale
PASS remove-conditional-success
PASS remove-really-deleted
PASS merge-inserts-when-absent
PASS merge-updates-when-present
PASS compute-reads-and-updates
PASS computeifpresent-updates
PASS computeifpresent-absent-returns-null
PASS computeifabsent-creates
PASS computeifabsent-keeps-existing
PASS compute-null-removes-mapping
PASS merge-null-removes-mapping
PASS computeifabsent-null-stays-absent
PASS concurrent-write-no-lost-index-events
PASS concurrent-write-all-count-exact
PASS concurrent-merge-even-count-exact
PASS concurrent-merge-odd-count-exact
PASS concurrent-merge-function-can-be-retried
PASS concurrent-compute-function-can-be-retried
PASS first-index-timestamp-correct
PASS last-index-timestamp-correct
PASS all-concurrent-keys-traversed-in-order
PASS unique-event-identities
PASS last-key-seen-matches-lastentry
PASS middle-time-window-count
PASS middle-window-only-4-through-7
PASS time-range-reversed-rejected
PASS full-key-collision-protection
PASS atomic-pollfirst-all-events-drained
PASS atomic-pollfirst-no-duplicate-removals
PASS atomic-pollfirst-map-empty-after-drain
PASS pollfirst-returns-null-when-empty
PASS polllast-returns-null-when-empty
PASS weak-iterator-iterated-with-concurrent-write
PASS weak-iterator-maintained-key-order
PASS weak-iterator-final-map-complete
PASS weak-iterator-post-join-max-key
PASS weak-iterator-removed-expected-even-keys
PASS weak-iterator-new-keys-present
PASS weak-iterator-snapshot-after-quiescence
PASS navigablekeyset-backed
PASS keyset-remove-updates-map
PASS pollfirst-removes-smallest
PASS polllast-removes-largest
PASS pollfirst-last-empty-map
PASS pollfirst-last-null-when-empty
passed=93
```

**QA thực tế:** `javac --release 17 -encoding UTF-8` thành công; `java ConcurrentSkipListIndexDemo` đạt **93/93 PASS**. Sau đó toàn bộ chương trình được chạy lại năm process runs độc lập, cả năm đều **93/93 PASS**. Không sử dụng sleep để quyết định kết quả concurrency; mọi giai đoạn có `CountDownLatch` và `Future.get(30,SECONDS)`.

### 12.4. Vì sao 6.400 events thực sự là đồng thời?

Các producer threads cùng chờ một `CountDownLatch gate`, rồi:
1. Xác định sequence unique qua `producer*800 + i`.
2. Tạo timestamp trong 16 buckets lặp lại `base + (i % 16)`.
3. Gọi `index.putIfAbsent(key,event)`.
4. Gọi `byCategory.merge(category,1L,...)`.
5. Gọi `total.compute("all",...)`.

Do 8 threads có thể interleave tùy JVM scheduling, **điều được assert sau cùng** là:
- `index.size()==6400`.
- `total.get("all")==6400L`.
- `byCategory.get("even")==3200L`.
- `byCategory.get("odd")==3200L`.
- `seenIds.size()==6400`.
- Keys duyệt ở **ascending order** khi producers đã ngừng.
- Range `[base+4,base+8)` có **1600 events**.

**Không nên hiểu 3 maps là một transaction**: mỗi producer gọi index trước rồi counters sau. Fixture dùng `Future.get` để đảm bảo đã hoàn tất tất cả các bước trước khi kiểm tra. Nếu ứng dụng production cần một *snapshot cùng thời điểm* giữa các maps, phải thêm coordination/transaction.

### 12.5. Giải thích 4 consumers

Consumers không poll trong khi producers còn ghi; đây là chủ đích để điều kiện kết thúc bằng null không bị race với future insertions. Mỗi consumer:
- Poll entry có key nhỏ nhất còn lại bằng `pollFirstEntry()`.
- Ghi ID vào `ConcurrentLinkedQueue`.
- Dừng khi map empty.
- Driver `Future.get` đợi tất cả xong.

Kết quả xác minh:
- `actualRemovals.get()==6400`.
- `new HashSet<>(removed).size()==6400`.
- `index.isEmpty()==true`.
- `pollFirstEntry()==null` sau khi drain.
- `pollLastEntry()==null` sau khi drain.

Đây là bằng chứng đúng cho **atomic extraction trong fixture**, không phải đảm bảo exactly-once durable business processing.

## 13. Phân tích các nhóm kiểm thử quan trọng

| Nhóm | Một số assertions | Nội dung xác nhận |
| --- | --- | --- |
| Tổng thứ tự khóa | `key-record-has-total-order` | Timestamp tie-break bằng sequence |
| Navigation | `lower-key-strict`, `ceiling-key-inclusive` | Floor/ceiling/lower/higher đúng nghĩa |
| Thứ tự views | `ascending-key-order`, `descending-key-order` | Ascending/descending keys |
| Time window | `time-window-half-open-100-through-101` | Range nửa mở |
| Backed view | `submap-is-backed-write-through` | Ghi vào subMap cập nhật map gốc |
| Range protection | `out-of-range-write-rejected` | Ngoài bounds ném IAE |
| Snapshots | `entry-snapshot-not-live-value` | Entry giữ mapping lúc tạo |
| Immutability | `entry-setvalue-unsupported` | Entry không hỗ trợ setValue |
| Null policy | `null-key-rejected`, `null-value-rejected` | Map không cho null |
| Spliterator | `spliterator-concurrent`, `spliterator-sorted` | Concurrent, ordered traversal |
| Comparator tùy chỉnh | `custom-comparator-first-key` | First theo comparator, không theo số học |
| Conditional updates | `replace-conditional-success`, `remove-conditional-success` | Compare-and-update cho một mapping |
| Remapping | `merge-updates-when-present`, `compute-null-removes-mapping` | Value mới và delete semantics |
| Concurrent write | `concurrent-write-no-lost-index-events` | 6.400 keys unique |
| Concurrent counters | `concurrent-merge-even-count-exact`, `concurrent-write-all-count-exact` | Không mất increments sau join |
| Bounded query | `middle-time-window-count` | Khoảng 4/16 buckets = 1.600 |
| Concurrent drain | `atomic-pollfirst-no-duplicate-removals` | Không lấy cùng mapping hai lần |
| Weak iterator | `weak-iterator-iterated-with-concurrent-write` | Traverse trong lúc writer thay map |
| Stable post-join | `weak-iterator-final-map-complete` | Sau writer kết thúc, final size đúng |
| Key set view | `keyset-remove-updates-map` | Backed key set làm thay đổi map |

### 13.1. Những assertion **không** được viết

Không có assertion:
- “Remapping function chắc chắn được gọi đúng một lần”.
- “Iterator thấy đúng tất cả concurrent writes”.
- “Map size giữa quá trình ghi bằng số events đã commit cùng thời điểm với counter”.
- “Bốn consumers lấy events toàn cục theo hoàn toàn thứ tự thời gian giữa các luồng”.
- “Poll event bảo đảm nó được xử lý thành công trong database”.

Các điều này **không** được class contract bảo đảm và có thể khiến unit test flake hoặc production logic sai.

## 14. Thiết kế API chỉ mục thực tế

### 14.1. Một interface đơn giản

Một ứng dụng có thể tổ chức:

```java
public interface OrderedEventIndex {
    void append(Event event, long epochMillis, long sequence);
    List<Event> between(long fromInclusive, long toExclusive);
    Event peekEarliest();
    Event pollEarliest();
}
```

Đây là **snippet thiết kế**, không chạy riêng vì cần định nghĩa `Event`, import `List`, implementation và chính sách null/duplicate keys. Trong implementation:
- `append` dùng `putIfAbsent` để tránh ghi đè nếu duplicate sequence.
- `between` tạo subMap view, có thể copy thành list nhưng phải ghi rõ consistency.
- `peekEarliest` dùng `firstEntry` (null nếu empty).
- `pollEarliest` dùng `pollFirstEntry` (null nếu empty).

Nếu event đã được update, đừng sửa mutable value trong place rồi kỳ vọng snapshot entry đại diện lịch sử; dùng immutable `record Event` và replace mapping theo version.

### 14.2. Độ nhất quán cần chọn

| Nhu cầu | ConcurrentSkipListMap có sẵn? | Cách xử lý |
| --- | --- | --- |
| An toàn concurrent single-key put/remove | Có | Dùng trực tiếp |
| Đọc key range theo comparator | Có | `subMap` backed view |
| Consistent snapshot toàn range dưới concurrent writes | **Không** | Application coordination, copy khi quiescent hoặc transactional store |
| Transaction cập nhật index và counter ở hai maps | **Không** | DB transaction/explicit lock/commit protocol |
| Exactly-once durable dequeue | **Không** | Durable queue + ack/idempotency |
| Tự evict theo TTL | **Không** | Maintenance job, scheduled cleanup/eviction policy |
| Persistence và recovery sau JVM crash | **Không** | Database/event log/storage layer |
| Global ordering giữa nhiều JVMs | **Không** | Distributed sequence/consensus/partition policy |

Chọn cấu trúc theo consistency, reliability và throughput requirements; không chọn chỉ vì tên class có chữ `Concurrent`.

### 14.3. Dữ liệu bền vững và replay

Nếu dữ liệu là sự kiện nghiệp vụ quan trọng, hãy lưu source-of-truth trong database/log. `ConcurrentSkipListMap` có thể là **materialized in-memory view** được rebuild từ events. Khi JVM restart:
- Clear in-memory index.
- Load snapshot/checkpoint nếu có.
- Replay events có idempotency keys.
- Kiểm tra sequence uniqueness và order invariants.
- Chỉ phát “index ready” khi đã xây dựng trạng thái phù hợp.

Không dùng Java serialization của map như một thay thế cho transaction log có schema versioning và recovery guarantees.

## 15. Query pagination, thời gian và key collisions

### 15.1. Cursor theo composite key

Pagination trên live ordered index nên dùng chính key đầy đủ `(timestamp,sequence)` làm cursor. Sau trang đầu, `higherKey(lastSeenKey)` có thể tìm mapping kế tiếp hiện có. Nếu dùng chỉ timestamp làm cursor, dễ bỏ qua những records cùng millisecond.

Nhưng **cursor trên live index không tạo snapshot isolation**. Một event được thêm trước `lastSeenKey` giữa hai pages có thể bị bỏ lỡ. Nếu cần pagination không bỏ/mất/lặp theo một dataset “đóng băng”, dùng snapshot version hoặc database read transaction.

### 15.2. Clock source và timestamp order

- `System.currentTimeMillis()` là wall-clock; có thể nhảy do sync/điều chỉnh đồng hồ.
- `Instant.now()` là timestamp theo wall clock, phù hợp ghi nhận business time nhưng không mặc định monotonic.
- `System.nanoTime()` dành đo khoảng thời gian trong cùng JVM, không phải epoch timestamp chia sẻ.
- Đừng suy “event được insert sau thì timestamp luôn lớn hơn”.
- Khi cần strict insertion order, thêm sequence được cấp từ một nguồn có ordering guarantee rõ ràng.

### 15.3. Ranges cho retention

Một phương án xóa entries quá cũ:

```java
var expired = index.headMap(cutoffKey, false);
expired.clear();
```

Đây là **snippet**. `clear()` trên range view **không bảo đảm xóa toàn range như một transaction atomic** trong lúc writers vẫn hoạt động. Một item có thể được thêm cùng vùng thời gian trong khi cleanup chạy. Với invariant quan trọng, dùng version/lock/retention protocol; với best-effort eviction, ghi rõ eventual semantics và giới hạn batch để tránh chi phí lớn.

## 16. ConcurrentSkipListMap và dữ liệu mutable

Map là thread-safe cho các **mapping operations**. Nó **không tự bảo vệ fields bên trong mutable value object** khi nhiều threads trực tiếp sửa object đó.

**Không nên:**

```java
record Holder(MutableStatus status) {}
// Nhiều threads cùng holder.status().setCount(...)
// mà không có synchronization cho MutableStatus.
```

Đây là **anti-pattern**, `MutableStatus` chỉ là tên minh họa. Không tưởng rằng lưu một object trong concurrent map làm mọi field changes bên trong object trở thành atomic.

**Nên ưu tiên:**
- Immutable value `record Event`.
- Thay cả value bằng `replace`/`compute`/`merge` với remapping functions thuần.
- Nếu cần mutable counters rất nóng, dùng `LongAdder` ở tầng metric phù hợp, nhưng hiểu thứ tự map và consistency riêng.
- Không để mutable key ảnh hưởng comparator.

### 16.1. Value replacement có thể thay đổi giữa khi đọc và sử dụng

Một reader:
```java
Event read = index.get(key);
```

nhận reference tới một immutable record đại diện value tại một thời điểm. Producer có thể `replace` mapping ngay sau `get`; reader vẫn giữ old reference. Đây là snapshot ở **mức một value reference**, không phải toàn bộ index transaction. Khi phải đảm bảo version:
- Thêm `version` field vào immutable value.
- Sử dụng `replace(key,expectedOld,newValue)`.
- Retry với bounded backoff.
- Ghi nhận conflict như một kết quả hợp lệ.

## 17. Benchmark và kiểm thử concurrency đúng cách

### 17.1. Không dùng thời gian một lần chạy làm bằng chứng hiệu năng

Chương trình trong bài cố ý đo **tính đúng**, không in throughput/ops-per-second do phụ thuộc CPU, JIT, GC và scheduler. Để benchmark hiệu năng đáng tin:
- Dùng JMH hoặc harness benchmark được thiết kế cho JVM.
- Warm up trước khi đo.
- So sánh số threads, key distribution, write/read ratio, map size và contention.
- Tránh dead-code elimination và false sharing effects.
- Đo p50/p95/p99 latency ngoài throughput trung bình.
- So `ConcurrentHashMap` và `ConcurrentSkipListMap` với workload thực sự cần ordered operations.
- Đo memory pressure và GC allocation.

Không công bố “map này luôn O(log n) tốn đúng X nanoseconds”, vì O-notation là đặc tính tiệm cận kỳ vọng, không là latency guarantee.

### 17.2. Test concurrency có khả năng tái lập

File demo:
- Dùng `CountDownLatch` để đồng thời khởi động producers.
- Dùng `ExecutorService` và `Future.get(30,SECONDS)` để thu exceptions và đợi hoàn tất.
- Đóng pools trong `finally` với `shutdownNow`/`awaitTermination`.
- Không dùng sleep để giả định thread scheduling chính xác.
- Kiểm tra invariant sau **quiescence**.
- Với iterator đang concurrent mutate, không assert một số lượng traverse cố định.
- Lặp **6 process runs** đều pass (lần đầu + năm lần xác minh thêm).

Những kiểm thử cao cấp hơn có thể dùng race detector, JCStress (OpenJDK), model-based testing hoặc linearizability harness; chúng bổ sung chứ không thay thế đặc tả API.

## 18. Lỗi phổ biến

**1. Dùng `HashMap` từ nhiều threads mà không đồng bộ.**  
Không an toàn; dùng concurrent collection đúng mục đích.

**2. Dùng `TreeMap` và nghĩ nó thread-safe vì đã sorted.**  
Không. Sorted và thread-safe là hai đặc tính khác nhau.

**3. Chọn `ConcurrentHashMap` rồi kỳ vọng `subMap`/`floorKey`.**  
Nó không cung cấp ordered-key navigation.

**4. Chọn `ConcurrentSkipListMap` cho mọi key lookup không cần sort.**  
Không tối ưu mặc định; đo theo workload.

**5. Dùng timestamp một mình làm key.**  
Events cùng millisecond ghi đè nhau. Dùng tie-break ID.

**6. Viết `compareTo` bằng phép trừ longs.**  
Có thể overflow và phá thứ tự; dùng `Long.compare`.

**7. Comparator trả 0 cho hai keys khác nhau.**  
Map coi chúng cùng mapping; dễ mất dữ liệu.

**8. Thay đổi field của key sau insertion.**  
Phá sorted invariant.

**9. Hiểu `firstKey()` luôn là numeric min dù dùng reverse comparator.**  
First theo comparator.

**10. Không xử lý null từ `lowerKey/ceilingKey/higherKey` ở biên.**  
Có thể gây NullPointerException.

**11. Gọi `firstKey`/`lastKey` trên map rỗng.**  
Có thể ném NoSuchElementException; dùng entry variants khi thích hợp.

**12. Nghĩ `subMap` trả deep snapshot.**  
Nó là backed live view.

**13. Insert key ngoài range qua subMap.**  
Có thể ném IllegalArgumentException.

**14. Đảo endpoints theo numeric ordering trong reverse map.**  
Ranh giới phải theo comparator.

**15. Coi `descendingMap` là bản sao độc lập.**  
Nó là view của map gốc.

**16. Lấy `Map.Entry` rồi gọi `setValue`.**  
Snapshot entries không hỗ trợ setter.

**17. Dùng mutable values và nghĩ map tự khóa mọi field của chúng.**  
Không; thread safety chỉ ở mapping operations.

**18. Cho phép null key/value.**  
ConcurrentSkipListMap cấm cả hai.

**19. Viết `get` rồi `put` để tăng counter.**  
Mất increments dưới contention.

**20. Đặt side effects trong `compute`/`merge` lambda.**  
Function có thể được gọi nhiều lần; không an toàn cho charge/email/DB.

**21. Giả định `computeIfAbsent` chạy factory một lần duy nhất.**  
Javadoc không bảo đảm, nhất là khi cạnh tranh.

**22. Trả null trong callback mà mong lưu null value.**  
Null nghĩa xóa/không thêm mapping theo method.

**23. Dựa vào `iterator.size` như snapshot atomic khi concurrent mutate.**  
Không; weak consistency không phải transaction isolation.

**24. Mong iterator tự ném ConcurrentModificationException khi có writes.**  
Đó không phải contract của concurrent skip-list iterators.

**25. Dùng `size()` như phép đếm O(1) trên hàng triệu keys.**  
Có thể O(n), không phù hợp scrape rất nóng.

**26. Coi `containsValue()` là indexed lookup nhanh.**  
Nó có linear cost và kết quả có thể nhiễu khi concurrent updates.

**27. Coi `putAll` là một atomic bulk transaction.**  
Không được đảm bảo atomic.

**28. Coi `headMap(...).clear()` là transaction cùng lúc cho cả range.**  
Không được bảo đảm.

**29. Poll một entry rồi coi event đã xử lý durable.**  
Poll chỉ xóa khỏi memory; cần ack/recovery riêng.

**30. Dừng consumer khi null dù producers còn làm việc.**  
Null chỉ mô tả emptiness lúc gọi, không là future guarantee.

**31. Dùng một map update để giả định counters trên map khác đã được cập nhật.**  
Không có transaction đa map.

**32. Copy list khi writers còn chạy rồi gọi đó là consistent snapshot.**  
Copy có thể thấy nhiều phiên bản state.

**33. Không giới hạn map size/retention.**  
Có thể dẫn đến heap bloat và GC pressure.

**34. Dùng System.nanoTime như epoch milliseconds.**  
Sai: nanoTime chỉ đo relative duration trong JVM.

**35. Sử dụng cùng ID namespace giữa processes không có coordination.**  
Có thể va chạm composite keys.

**36. Thiết kế live pagination nhưng bảo đảm không bao giờ miss concurrent inserts.**  
Không thể từ weak view; cần snapshot/version.

**37. Chạy bài kiểm thử trong service production.**  
Không nên; fixture tạo nhiều threads và xóa test index, chỉ chạy JVM riêng.

**38. Bỏ qua timeout/shutdown của test executors.**  
Dễ treo tests hoặc để thread chạy vô hạn.

## 19. Checklist triển khai production

- [ ] Dùng `ConcurrentSkipListMap` khi thực sự cần key ordering/range.
- [ ] Nếu chỉ cần key lookup, cân nhắc `ConcurrentHashMap`.
- [ ] Chọn key immutable, comparator consistent với equals.
- [ ] Không dùng timestamp đơn độc nếu có khả năng trùng.
- [ ] Quy ước timestamp units/timezone và ID uniqueness.
- [ ] Dùng `subMap` với inclusive/exclusive rõ, kiểm tra comparator bounds.
- [ ] Biết range views/descending/key sets đều backed by map.
- [ ] Không mutate Map.Entry snapshot bằng `setValue`.
- [ ] Dùng immutable values/records hoặc synchronization riêng cho mutable payload.
- [ ] Dùng `putIfAbsent`/`replace`/`remove(key,expected)` khi cần conditional update.
- [ ] Dùng `merge`/`compute` thuần, retry-safe, không business side effects.
- [ ] Không đặt HTTP/DB/email/payment trong remapping lambda.
- [ ] Không mặc định factory `computeIfAbsent` chạy đúng một lần.
- [ ] Với concurrent iteration, chấp nhận weak consistency hoặc thêm snapshot coordination.
- [ ] Không dùng `size` như constant-time operation.
- [ ] Không dùng `putAll`/`clear` như transaction.
- [ ] Phân biệt atomic mapping update với cross-map transaction.
- [ ] Xác định retention, memory limits, TTL/eviction policy.
- [ ] Khi poll, có cơ chế ack/lease/replay nếu dữ liệu quan trọng.
- [ ] Không dừng consumers dựa vào một empty poll khi producers chưa đóng.
- [ ] Chạy concurrency tests dưới nhiều interleavings và JDK target.
- [ ] Dùng JMH hoặc benchmark chuyên biệt để đo performance thực.
- [ ] Ghi rõ consistency và durability của API chỉ mục.
- [ ] Không mở network hoặc sửa dữ liệu thật khi chạy fixture.

## 20. Câu hỏi ôn tập

**1. `ConcurrentSkipListMap` giải quyết hai yêu cầu nào?**  
Concurrent updates và sorted-key navigation/range queries.

**2. Nó có đảm bảo `O(1)` cho `get/put` không?**  
Không; chi phí kỳ vọng trung bình `O(log n)`.

**3. Nếu chỉ cần key lookup, nên so sánh với class nào?**  
`ConcurrentHashMap`.

**4. Vì sao timestamp đơn độc không phù hợp làm key cho nhiều events?**  
Nhiều events có thể trùng timestamp và ghi đè cùng key.

**5. Cách tránh overflow trong comparator của hai longs?**  
Dùng `Long.compare`.

**6. `compare(a,b)==0` nên nhất quán với gì?**  
`equals(a,b)` để đáp ứng Map semantics.

**7. `subMap(start,true,end,false)` là khoảng gì?**  
`[start,end)` theo comparator.

**8. `subMap` là copy hay backed view?**  
Backed live view.

**9. Ghi vào subMap ngoài range có thể gặp gì?**  
`IllegalArgumentException`.

**10. `firstKey()` trên map rỗng trả null?**  
Không; có thể ném NoSuchElementException. `firstEntry()` trả null.

**11. `higherKey` và `ceilingKey` khác nhau ra sao?**  
Higher là strictly greater; ceiling là greater-or-equal.

**12. `descendingMap()` có tạo bản sao độc lập không?**  
Không, nó là reverse-order view backed by original.

**13. `Map.Entry.setValue` có được hỗ trợ không?**  
Không trên các snapshot entry được trả về.

**14. Có thể lưu `null` key/value không?**  
Không.

**15. Tại sao `get` rồi `put` không an toàn cho increment?**  
Rủi ro lost updates giữa nhiều threads.

**16. `merge("x",1L,Long::sum)` bảo vệ điều gì?**  
Per-mapping update dưới concurrency; callback có thể được gọi lại.

**17. `merge` function được đảm bảo chạy đúng một lần không?**  
Không theo Javadoc `ConcurrentSkipListMap`.

**18. Có nên gửi email trong `computeIfAbsent` function?**  
Không; callback có thể chạy nhiều lần.

**19. `compute` trả null nghĩa gì?**  
Xóa mapping hoặc giữ absent.

**20. Weakly consistent iterator là snapshot atomic không?**  
Không, nó có thể thấy một phần concurrent changes và không fail-fast.

**21. `size()` luôn constant-time không?**  
Không, có thể tuyến tính theo số entries.

**22. `putAll` và `clear` có atomic bulk semantics không?**  
Không được bảo đảm.

**23. `pollFirstEntry` có đồng nghĩa exactly-once durable processing không?**  
Không. Nó chỉ lấy và xóa một mapping trong memory.

**24. Vì sao producer/consumer fixture chỉ poll sau khi producer Future kết thúc?**  
Để null nghĩa đã hết dữ liệu của giai đoạn đó, không bị future insertion race.

**25. 8 producers × 800 events cho bao nhiêu records?**  
6.400 nếu unique keys và không lỗi, đã xác minh.

**26. Có bao nhiêu events nằm trong 4 trên 16 buckets?**  
1.600 với phân phối đồng đều của fixture.

**27. Bài demo đã qua bao nhiêu assertions?**  
93 assertions, qua 6 process runs trên OpenJDK24.

**28. Nếu cần transaction giữa index và counters nằm ở map khác, làm sao?**  
Dùng explicit coordination hoặc transactional database, không dựa vào mỗi map's concurrency.

**29. Khi xây pagination trên live map, có đảm bảo không miss concurrent inserts không?**  
Không. Cần snapshots/versioning nếu đó là yêu cầu.

**30. Vì sao nên chọn immutable Event record?**  
Giảm rủi ro data races trên nội dung value và giúp snapshot entries dễ hiểu.

## 21. Tài liệu chính thức, hiện hành

- [Oracle Java SE 26 — `ConcurrentSkipListMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): class contract, O(log n) expected average, weak iterators, callback retry warning, null restrictions, size/bulk behavior, ordered views.
- [Oracle Java SE 26 — `ConcurrentNavigableMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html): range views, navigational API, concurrent ordered map.
- [Oracle Java SE 26 — `NavigableMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/NavigableMap.html): inclusive/exclusive bounds, floor/ceiling/higher/lower, snapshots and descending.
- [Oracle Java SE 26 — `ConcurrentMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): conditional updates, compute/merge semantics.
- [Oracle Java SE 26 — `Map`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html): map contract, key equality, mutation methods.
- [Oracle Java SE 26 — `Comparator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): ordering consistency.
- [Oracle Java SE 26 — `ExecutorService`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): bounded worker pools, shutdown.
- [Oracle Java SE 26 — `Future`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): wait for completion and propagate worker failures.
- [Oracle Java SE 26 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinated start.
- [Oracle Java SE 26 — `ConcurrentLinkedQueue`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): collect drained event IDs safely.
- [Oracle Java SE 26 — `LongAdder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): metrics alternatives under high contention.

**Ghi nhớ:** `ConcurrentSkipListMap` là một **concurrent ordered index**, không phải database transaction engine. Sắp xếp bằng comparator/Comparable, dùng composite key để tránh collisions, truy vấn range qua backed views, cập nhật một mapping bằng các methods đồng thời và để remapping functions **pure/retry-safe**. Iterator yếu nhất quán, bulk operations không atomic, `size` có thể tốn chi phí tuyến tính, và map không tự cung cấp durability/TTL/ack. Mọi bài toán cần snapshot nhất quán, transaction đa maps hay exactly-once processing cần cơ chế bổ sung rõ ràng.
