# ConcurrentHashMap: compute, computeIfAbsent và merge theo khóa

**Chủ đề cha:** `ConcurrentHashMap`. **Đề bài:** Sử dụng `compute`, `computeIfAbsent` và `merge` khi nhiều thread cùng tạo/cập nhật ánh xạ của một khóa; phân biệt khi nào callback được gọi, giá trị trả về `null` có nghĩa gì, mức nguyên tử được bảo đảm và giới hạn thực tế của việc cập nhật nhiều khóa hoặc giá trị mutable. Các ví dụ tập trung vào cơ chế **nguyên tử theo ánh xạ của khóa**, tránh lối viết `get` rồi `put` gây lost update.

**Phiên bản:** `ConcurrentHashMap` đã có từ Java trước Java 8, còn các phương thức compute/merge theo hàm được bổ sung vào bộ Map/ConcurrentMap ở **Java 8** và vẫn là API hiện hành. `LongAdder` cũng có từ Java 8. Những chương trình độc lập dùng **JDK 17+**, lệnh `javac --release 17` và stdout kiểm chứng được; không cần kỹ thuật đồng bộ hoặc thư viện đã lỗi thời.

> **Nguyên tắc:** `ConcurrentHashMap.compute(key, fn)`, `computeIfAbsent(key, fn)` và `merge(key, value, fn)` thực hiện **việc tính toán/cập nhật ánh xạ tương ứng một cách nguyên tử**. Trong bản triển khai `ConcurrentHashMap`, callback compute được gọi một lần cho mỗi lời gọi, còn callback computeIfAbsent chỉ được gọi khi khóa vắng mặt ở lúc thực thi thao tác. Nhưng tính nguyên tử **không kéo dài sang toàn map, các khóa khác hoặc nội dung mutable được lấy ra**. Callback phải **ngắn, đơn giản, không tự cập nhật map này**, vì một số thao tác cập nhật khác có thể phải chờ khi callback đang chạy.

## 1. Bài toán: get rồi put không phải một thao tác nguyên tử

Tưởng tượng nhiều request cùng tăng số lượt xem cho khóa `"article-7"`:

```java
ConcurrentHashMap<String, Integer> counters =
        new ConcurrentHashMap<>();
counters.put("article-7", 0);

// Phản ví dụ khi nhiều thread cùng chạy:
Integer old = counters.get("article-7");
counters.put("article-7", old + 1);
```

Đây là **đoạn mã minh họa bên trong phương thức**, không phải một demo chạy đa luồng độc lập. Dù cả `get` và `put` của `ConcurrentHashMap` đều thread-safe, tổ hợp `get -> cộng -> put` **không nguyên tử**. Hai thread có thể cùng đọc 0, rồi cùng ghi 1, khiến kết quả cuối là 1 thay vì 2 (*lost update*).

Đây là sự khác biệt giữa:

- **An toàn cho từng lời gọi map:** không làm hỏng cấu trúc nội bộ khi nhiều thread đọc/ghi.
- **Nguyên tử của toàn bộ phép đọc–sửa–ghi:** không thread nào chen vào giữa lúc một khóa được tính giá trị mới.

`compute` và `merge` cho phép diễn đạt *read–modify–write* của một ánh xạ trong **một lời gọi nguyên tử**:

```java
counters.compute(
        "article-7",
        (key, oldValue) -> oldValue == null ? 1 : oldValue + 1);

counters.merge("article-7", 1, Integer::sum);
```

Trong ví dụ hai lời gọi được thực hiện **liên tiếp**, sau đó số đếm là 2. Nếu nhiều thread cùng thực thi, mỗi lần cập nhật có ý nghĩa tuần tự trên khóa đích, tránh mất lượt tăng như chuỗi `get/put`.

**Cần phân biệt:** Việc tạo giá trị mới `Integer` và gán nó vào map là nguyên tử theo khóa. Nếu giá trị map là một `ArrayList` và thread tự gọi `list.add(...)` ngoài hàm map, CHM **không tự biến ArrayList thành thread-safe**.

## 2. ConcurrentHashMap không chứa null: Nền tảng ngữ nghĩa compute

`ConcurrentHashMap` **không chấp nhận khóa null hoặc giá trị null**. Nó được thiết kế để việc `get(key) == null` có ý nghĩa đáng tin là **không có ánh xạ hiện tại**.

Ví dụ:

```java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();

map.put("ok", 10);   // Hợp lệ.
// map.put("bad", null); // Ném NullPointerException.
// map.put(null, 20);   // Ném NullPointerException.
```

Đây là đoạn **trong phương thức**; các dòng bị comment cố ý là các lời gọi không hợp lệ.

Nhưng `null` **bên trong callback** có ngữ nghĩa đặc biệt:

- Trong `compute`, nếu callback trả `null` → **xóa ánh xạ nếu đang có**, còn nếu vắng mặt thì vẫn vắng mặt.
- Trong `computeIfAbsent`, nếu callback trả `null` → **không tạo ánh xạ**.
- Trong `merge`, nếu hàm gộp được gọi cho khóa đã có và trả `null` → **xóa ánh xạ**.
- Trong `computeIfPresent`, nếu callback trả `null` → **xóa ánh xạ**.

`null` ở đây **không được lưu vào map**. Nó là **tín hiệu điều khiển thao tác**, chứ không phải một trạng thái giá trị `key -> null`.

Chú ý riêng: `merge(key, value, fn)` đòi **`value` tham số là non-null**. Truyền `null` làm giá trị đến `merge` sẽ ném `NullPointerException`; khác với việc hàm remapping được gọi và *trả* `null` để xóa ánh xạ.

## 3. Bốn phép thường được so sánh

| Phương thức | Gọi callback khi khóa absent? | Gọi callback khi khóa present? | Callback nhận gì? | Khi callback trả null |
| --- | --- | --- | --- | --- |
| `compute(key, f)` | **Có** | **Có** | `(key, oldValue)`, oldValue là null nếu absent | Không tạo hoặc xóa mapping |
| `computeIfAbsent(key, f)` | **Có** | **Không** | `(key)` | Không tạo mapping |
| `computeIfPresent(key, f)` | **Không** | **Có** | `(key, oldValue)`, oldValue non-null | Xóa mapping |
| `merge(key, value, f)` | **Không**; chèn ngay tham số value | **Có** | `(oldValue, incomingValue)` | Xóa mapping nếu callback được gọi |

Mỗi hàng mô tả `ConcurrentHashMap` khi **không có concurrent update nào khác chen vào ngoài ngữ nghĩa nguyên tử của chính lời gọi**. Với nhiều thread, sự hiện diện của một khóa có thể thay đổi trước khi phương thức thực hiện thao tác; các điều kiện trên được xét **ở điểm thực thi nguyên tử**, không phải từ kết quả `containsKey` mà caller từng đọc trước đó.

### 3.1. Chữ ký API thực tế

```java
V compute(
        K key,
        BiFunction<? super K, ? super V, ? extends V> fn);

V computeIfAbsent(
        K key,
        Function<? super K, ? extends V> fn);

V computeIfPresent(
        K key,
        BiFunction<? super K, ? super V, ? extends V> fn);

V merge(
        K key,
        V value,
        BiFunction<? super V, ? super V, ? extends V> fn);
```

Đây là **chữ ký minh họa bằng generics** lấy từ API, không phải một khai báo Java độc lập (K/V phải là tham số type của class/interface). `compute` và `computeIfPresent` truyền **key + old value**; `merge` truyền **old value + incoming value**, **không truyền key** vào callback. Lẫn lộn thứ tự này sẽ làm tính toán sai ngay cả khi chương trình biên dịch được.

### 3.2. Giá trị trả về của cả phương thức

Các phương thức trả **giá trị hiện tại hoặc mới sau thao tác**, hoặc `null` nếu không còn mapping. Không phải lúc nào chúng cũng trả **giá trị cũ** giống `put`.

Ví dụ `map.merge("count", 1, Integer::sum)` khi khóa absent trả **1** và lưu 1. Lần sau nếu giá trị cũ là 1, nó trả **2** và lưu 2. `map.compute("count", ..., null)` có thể trả `null` vì xóa ánh xạ.

Nếu caller muốn biết một thao tác business có thật sự cấp quyền cho request cụ thể hay không, cần thiết kế dữ liệu/trạng thái trả về phù hợp, không suy đoán từ kết quả `compute` trả 0.

## 4. `compute`: Cập nhật bất kể khóa đã có hay chưa

`compute(key, remappingFunction)` chạy callback với:

- `key`: khóa đang cập nhật.
- `oldValue`: giá trị hiện có, hoặc `null` nếu khóa absent (vì CHM không hỗ trợ null values).
- Giá trị callback trả về: sẽ là mapping mới nếu non-null; nếu null thì mapping bị xóa hoặc vẫn absent.

Công thức tăng một đơn vị:

```java
map.compute(
        "hits",
        (key, oldValue) ->
                oldValue == null ? 1 : oldValue + 1);
```

Đây là đoạn **trong phương thức**; `map` là `ConcurrentHashMap<String,Integer>`. Nếu không có mapping, tạo `"hits" -> 1`; nếu đang có 7, trở thành 8. Hàm được thực thi một lần cho mỗi invocation của CHM.compute theo hợp đồng API.

### 4.1. Trả null để xóa

```java
map.compute("hits", (key, oldValue) -> null);
```

Nếu `"hits"` tồn tại, mapping bị **xóa**. Nếu chưa tồn tại, map vẫn không có khóa đó. Điều này **không** tạo ánh xạ `"hits" -> null`.

### 4.2. Giữ nguyên nếu không thỏa điều kiện

Có thể trả `oldValue` để không đổi mapping khi điều kiện không thỏa:

```java
map.compute("balance", (key, old) -> {
    if (old == null) {
        return null; // Không tự tạo số dư mới.
    }
    return old >= 10 ? old - 10 : old;
});
```

Đây là đoạn trong phương thức. Nếu absent thì vẫn absent; nếu old=5 thì giữ 5; nếu old=15 thì giảm còn 5. **Không đặt blocking I/O, sleep hoặc retry dài bên trong callback**, vì update khác trên cùng map có thể bị ảnh hưởng khi chờ khóa nội bộ.

### 4.3. Tránh NullPointerException khi unboxing

Đây là **phản ví dụ**:

```java
map.compute("new", (key, old) -> old + 1);
```

Nếu `"new"` absent, `old == null`, phép `old + 1` unbox Integer sẽ gây `NullPointerException`. Nên dùng điều kiện `old == null ? initial : old + delta` hoặc `merge` với incoming value khi logic chỉ là cộng/gộp.

### 4.4. Bất biến của value vẫn quan trọng

Nếu map lưu `Integer`, mỗi update tính một Integer mới và thay mapping. Nếu map lưu một object mutable, callback trả lại **cùng reference** sau khi sửa object có thể không bảo vệ các thay đổi đó khỏi thread khác đang giữ reference. Với một state gồm nhiều field phải cập nhật đồng thời theo khóa, thường nên lưu **value bất biến** rồi tạo value mới trong callback.

## 5. `computeIfAbsent`: Khởi tạo khi thiếu ánh xạ

`computeIfAbsent(key, mappingFunction)` phù hợp khi một khóa **chưa có giá trị** và ta muốn tạo **một giá trị khởi đầu**:

```java
ConcurrentHashMap<String, String> cache =
        new ConcurrentHashMap<>();

String first = cache.computeIfAbsent(
        "language", key -> key.toUpperCase());
// "LANGUAGE"

String second = cache.computeIfAbsent(
        "language", key -> "WRONG");
// Vẫn là "LANGUAGE"; callback thứ hai không được gọi.
```

Đây là đoạn trong phương thức. Nếu khóa có mapping non-null, phương thức trả giá trị sẵn có **mà không chạy factory**.

### 5.1. Tính nguyên tử của quá trình khởi tạo

`ConcurrentHashMap` override phương thức này: toàn invocation được thực hiện nguyên tử. Nếu khóa absent, hàm ánh xạ được gọi **đúng một lần trong invocation đó**; nếu khóa present thì không gọi. Khi nhiều thread cùng cố tạo **một khóa vắng mặt**, và một callback trả giá trị non-null để cài vào map, các lời gọi khác có thể đợi và đọc mapping đã tạo, thay vì ghi đè hoặc tạo nhiều giá trị đã lưu.

**Đừng diễn giải quá mức thành “factory được gọi nhiều nhất một lần trong suốt đời khóa”:**

- Nếu factory trả `null`, không có mapping, lời gọi sau vẫn có thể chạy factory lần nữa.
- Nếu factory ném exception, mapping chưa được tạo; lần sau có thể thử lại.
- Nếu một thread xóa mapping sau khi tạo, lần `computeIfAbsent` tiếp theo có thể tạo lại.
- Nếu value thay đổi theo một logic khác, factory hiện tại có thể không bao giờ chạy vì khóa chưa absent.
- Đây là hợp đồng cụ thể của **ConcurrentHashMap**, không tự động áp cho mọi implementation của `ConcurrentMap`.

### 5.2. `null` không phải một cache entry

`cache.computeIfAbsent("missing", key -> null)` trả `null`, và `cache.containsKey("missing")` vẫn **false**. Nếu dịch vụ cần cache cả trường hợp “không có dữ liệu”, hãy thiết kế một **sentinel/kiểu kết quả** phù hợp, như `Optional<Value>` đã được thỏa thuận làm value non-null, thay vì mong CHM lưu null.

**Cẩn thận:** `Optional.empty()` là một object non-null, nên CHM có thể lưu nó; nhưng cần xác định rõ thời gian hiệu lực của kết quả âm tính và invalidation để tránh cache “không tìm thấy” vĩnh viễn.

### 5.3. Callback nên ngắn và không tự sửa map

`computeIfAbsent` thường được dùng để tạo object nhanh, ví dụ:

```java
ConcurrentHashMap<String, LongAdder> frequency =
        new ConcurrentHashMap<>();

frequency.computeIfAbsent(
        "java", key -> new LongAdder())
        .increment();
```

Khởi tạo `LongAdder` rẻ và không phụ thuộc mạng/database. Ngược lại:

```java
// Phản ví dụ: hàm gọi I/O chặn và có thể tốn nhiều thời gian.
cache.computeIfAbsent(
        "remote", key -> slowNetworkRequest(key));
```

Đây là đoạn phản ví dụ, `slowNetworkRequest` chưa được khai báo, **không chạy độc lập**. Vì một số update khác có thể bị chặn khi hàm đang chạy, callback thực hiện I/O chậm rất dễ gây trễ, thậm chí tăng nguy cơ deadlock khi tài nguyên có quan hệ vòng.

Nếu cần load từ DB/HTTP, hãy thiết kế **async cache/single-flight** riêng, hoặc tính giá trị ngoài map rồi dùng chiến lược atomic insertion có kiểm soát. Tuy nhiên, tính ngoài map rồi `putIfAbsent` có thể khiến nhiều thread cùng tính **dư thừa**; phải chọn đánh đổi đúng theo yêu cầu.

## 6. `merge`: Gộp giá trị đến theo khóa

`merge(key, value, remappingFunction)` nhận **giá trị mới muốn bổ sung** dưới dạng tham số `value` (phải non-null):

- Nếu khóa absent → **gắn trực tiếp `value`**, **không gọi callback**.
- Nếu khóa present → gọi `remappingFunction(oldValue, value)`; kết quả non-null thay value.
- Nếu callback trả `null` → xóa ánh xạ hiện tại.
- Nếu callback ném RuntimeException/Error → mapping ban đầu vẫn không đổi.

### 6.1. Đếm lượt bằng merge

```java
ConcurrentHashMap<String, Integer> counts =
        new ConcurrentHashMap<>();

counts.merge("java", 1, Integer::sum); // 1
counts.merge("java", 1, Integer::sum); // 2
counts.merge("go", 1, Integer::sum);   // 1
```

Đây là đoạn trong phương thức. Không cần kiểm tra `get` trước; hành vi absent/present được giải quyết nguyên tử trong một lời gọi.

### 6.2. Gộp trường hợp có thể xóa mapping

```java
counts.merge("java", 1, (oldCount, incoming) -> null);
// Xóa "java" nếu nó đang tồn tại.
```

Trả null từ **callback** là tín hiệu xóa. Trái lại:

```java
// Phản ví dụ, NPE vì incoming value bắt buộc non-null:
counts.merge("java", null, Integer::sum);
```

Lưu ý khi xóa theo điều kiện: nếu callback trả null khi tổng đạt 0, một lời gọi `merge` lên khóa **absent** sẽ **chèn incoming value ngay**, không chạy callback để kiểm tra. Ví dụ `merge(key, -1, Integer::sum)` khi absent sẽ chèn **-1**, điều này có thể sai với bài toán không cho số âm. Khi cần kiểm soát trạng thái absent hoặc áp đặt nhiều điều kiện, `compute` thường phù hợp hơn.

### 6.3. Khi nào chọn compute thay vì merge?

Dùng `merge` cho một quy tắc có dạng “giá trị mới = old kết hợp incoming”, và **giá trị đến đã có sẵn**: cộng điểm, gộp thống kê, chọn phiên bản cao hơn, gộp tập bất biến…

Dùng `compute` khi cần biết **khóa đang absent hay present**, cần tạo/giữ/xóa theo điều kiện phức tạp hoặc cần giá trị mới phụ thuộc trực tiếp vào key. Ví dụ hạ số lượng còn lại nhưng **không cho âm** nên dùng compute trả old nếu không đủ, thay vì merge với số âm rồi phải sửa lại.

**Không có một phương thức duy nhất tối ưu cho mọi nghiệp vụ:** `computeIfAbsent` là factory khi thiếu, `merge` là phép gộp với incoming value, `compute` là phép chuyển trạng thái tổng quát.

## 7. Chương trình Java 17+: So sánh chính xác bốn phép

Tạo file **`ConcurrentMapMethodsDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentMapMethodsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        System.out.println("compute absent: "
                + map.compute("counter",
                        (key, old) -> old == null ? 1 : old + 1));
        System.out.println("compute present: "
                + map.compute("counter",
                        (key, old) -> old == null ? 1 : old + 1));
        System.out.println("compute no mapping: "
                + map.compute("ignored", (key, old) -> null));
        System.out.println("ignored present: "
                + map.containsKey("ignored"));

        AtomicInteger factoryCalls = new AtomicInteger();
        System.out.println("first default: "
                + map.computeIfAbsent("default", key -> {
                    factoryCalls.incrementAndGet();
                    return 10;
                }));
        System.out.println("second default: "
                + map.computeIfAbsent("default", key -> {
                    factoryCalls.incrementAndGet();
                    return 20;
                }));
        System.out.println("factory calls: "
                + factoryCalls.get());

        System.out.println("merge absent: "
                + map.merge("sum", 3, Integer::sum));
        System.out.println("merge present: "
                + map.merge("sum", 4, Integer::sum));
        System.out.println("merge remove: "
                + map.merge("sum", 1, (old, add) -> null));
        System.out.println("sum exists: "
                + map.containsKey("sum"));

        System.out.println("ifPresent: "
                + map.computeIfPresent(
                        "counter", (key, old) -> old + 5));
        System.out.println("counter final: "
                + map.get("counter"));
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentMapMethodsDemo.java
java ConcurrentMapMethodsDemo
```

**Stdout chính xác:**

```text
compute absent: 1
compute present: 2
compute no mapping: null
ignored present: false
first default: 10
second default: 10
factory calls: 1
merge absent: 3
merge present: 7
merge remove: null
sum exists: false
ifPresent: 7
counter final: 7
```

**Phân tích kết quả:**

1. `compute` callback chạy cả khi khóa absent và present. Lần đầu nhận old=null, lần sau nhận old=1.
2. Với khóa `"ignored"`, callback trả null: không có mapping nào được tạo.
3. `computeIfAbsent` tạo `"default" -> 10` một lần; lần tiếp theo đọc 10 và **không gọi factory** dù lambda thứ hai có thể trả 20.
4. `merge` ban đầu gắn trực tiếp 3, sau đó chạy `Integer::sum` để tạo 7.
5. Callback của `merge` trả null xóa `"sum"`; `containsKey` xác nhận khóa biến mất.
6. `computeIfPresent` chỉ cập nhật `"counter"` khi giá trị hiện có là 2, cộng 5 thành 7.
7. Program in từng giá trị riêng, **không phụ thuộc thứ tự duyệt ConcurrentHashMap**, nên stdout xác định.

## 8. Tính nguyên tử theo khóa và cách nó tương tác với nhiều thread

Điểm bảo đảm đặc biệt của `ConcurrentHashMap` là **toàn invocation của các hàm compute/merge được thực hiện nguyên tử** đối với ánh xạ được xử lý. Hai lời gọi `compute("count",...)` đồng thời không thể cùng đọc một giá trị cũ rồi cùng ghi đè giá trị mới gây lost update như chuỗi `get/put`.

Một pipeline có thể được hiểu như các chuyển trạng thái đối với một khóa:

```text
count = 0
thread A compute(count, +1) -> count = 1
thread B compute(count, +1) -> count = 2
...
```

Đây là sơ đồ **minh họa một thứ tự tương đương**, không khẳng định thread A luôn chạy trước B. Runtime có thể chọn thứ tự khác, nhưng nếu mỗi phép cập nhật cộng đúng 1 thì kết quả cuối cùng đúng bằng tổng số phép cập nhật thành công.

### 8.1. Không phải “khóa toàn bộ map”

`ConcurrentHashMap` hướng tới khả năng cập nhật nhiều khóa đồng thời, nhưng không đảm bảo **mọi khóa khác chắc chắn không bị chặn**. Javadoc cho biết một số cập nhật của thread khác có thể phải chờ khi remapping đang chạy, ví dụ do cơ chế phối hợp nội bộ/collision/resizing.

Do đó không được mô tả compute là một giao dịch toàn map, cũng không được mô tả nó là một thao tác lock-free tuyệt đối. `get` thường không khóa chặn theo đặc tính CHM, nhưng các writer có thể chịu tranh chấp.

### 8.2. Một khóa ổn định, bao nhiêu callback?

Với `ConcurrentHashMap.compute`, callback được gọi **đúng một lần trong một invocation**. Với `computeIfAbsent`, callback được gọi một lần **nếu khóa absent tại thời điểm thao tác**, hoặc không gọi nếu đã present. Đây là lý do ví dụ có thể đếm số lần factory tạo một giá trị non-null dưới tranh chấp.

**Không áp dụng bừa** kết luận “callback được gọi một lần” cho mọi kiểu `ConcurrentMap`: các **default method** trong interface có thể dùng vòng lặp compare-and-replace và thực thi lại callback khi tranh chấp. Đặc biệt nếu thư viện chỉ khai báo `ConcurrentMap`, cần xem **implementation thực tế** trước khi dựa vào số lần callback để thiết kế side effect.

Ngay cả khi CHM bảo đảm callback không bị gọi lặp trong một invocation, **side effect bên ngoài** như gửi email, trừ tiền ở DB hay gọi API không thể tự rollback nếu callback hoặc update thất bại. Hãy giữ callback đơn giản, thuần theo input cũ; tác vụ ngoài map nên có transaction/idempotency và kiến trúc riêng.

## 9. Java 17+: Stress test có kiểm soát, không bị lost update

Tạo file **`ConcurrentKeyAtomicityDemo.java`**. Tám worker bắt đầu gần đồng thời, mỗi worker tăng hai khóa độc lập 1.000 lần:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentKeyAtomicityDemo {
    public static void main(String[] args) throws Exception {
        final int workers = 8;
        final int rounds = 1_000;

        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("compute", 0);

        AtomicInteger constructions = new AtomicInteger();
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    for (int j = 0; j < rounds; j++) {
                        map.compute(
                                "compute", (key, old) -> old + 1);
                        map.merge("merge", 1, Integer::sum);
                        map.computeIfAbsent(
                                "once", key -> {
                                    constructions.incrementAndGet();
                                    return 7;
                                });
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get(); // Propagate worker errors.
            }

            System.out.println("compute count: "
                    + map.get("compute"));
            System.out.println("merge count: "
                    + map.get("merge"));
            System.out.println("created: "
                    + constructions.get());
            System.out.println("once: "
                    + map.get("once"));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentKeyAtomicityDemo.java
java ConcurrentKeyAtomicityDemo
```

**Stdout:**

```text
compute count: 8000
merge count: 8000
created: 1
once: 7
```

**Vì sao test này có ý nghĩa:**

- `CountDownLatch` cho worker chờ cùng một mốc bắt đầu, làm tăng khả năng tranh chấp, nhưng test **không dựa vào thứ tự chạy cụ thể**.
- `Future.get()` đợi toàn bộ tác vụ hoàn tất và **đẩy exception từ worker về thread main**. Khi đó mới đọc giá trị cuối.
- `compute` và `merge` cho kết quả đúng 8 × 1.000, chứng minh không mất cập nhật với **giá trị Integer bất biến được thay nguyên tử theo khóa**.
- Factory của `computeIfAbsent` tạo `"once" -> 7`. Không có thao tác xóa khóa, nên sau khi một thread thành công, các lời gọi sau đọc giá trị có sẵn và không chạy factory; counter bằng 1.
- `AtomicInteger constructions` chỉ dùng trong **test để quan sát callback**, không đại diện cho khuyến nghị làm side effect nghiệp vụ trong callback.
- `pool.shutdownNow()` trong `finally` là cleanup trong demo đã đợi toàn bộ Future bằng `get`; trong ứng dụng thực cần shutdown êm và chính sách chờ hoàn tất thích hợp.

**Lưu ý quan trọng:** Kết quả stress test thành công **không chứng minh toàn bộ chương trình đa luồng luôn đúng**. Nó xác nhận contract cho hai khóa và một tập tác vụ đã kiểm thử. Với logic đa khóa hoặc mutable value, cần thêm cơ chế đồng bộ riêng.

## 10. `LongAdder`: Frequency map dưới tải cao

Javadoc `ConcurrentHashMap` giới thiệu mẫu đếm số lần xuất hiện theo khóa:

```java
ConcurrentHashMap<String, LongAdder> frequencies =
        new ConcurrentHashMap<>();

frequencies.computeIfAbsent(
        "java", key -> new LongAdder()).increment();
```

**Cơ chế gồm hai phần khác nhau:**

1. `computeIfAbsent` tạo/bảo đảm có **một LongAdder được lưu** cho khóa đang absent. Khởi tạo mapping là thao tác nguyên tử theo khóa.
2. `increment()` cập nhật **LongAdder đã được lấy ra**, bằng cơ chế thread-safe của chính `LongAdder`, **không** dựa vào khóa nội bộ CHM cho mỗi lần tăng.

Điểm này quan trọng: nếu value là `ArrayList`, cùng cú pháp `computeIfAbsent(...).add(...)` **không tự làm ArrayList thread-safe**. Với `LongAdder`, cả bước khởi tạo map lẫn bước tăng bộ đếm đều có cơ chế thread-safe tương ứng, nhưng chúng **không hợp thành một giao dịch nguyên tử duy nhất** xuyên qua các thao tác map khác như `remove`.

### 10.1. Khi nào LongAdder hơn Integer + merge?

`merge(key, 1, Integer::sum)` dễ đọc, nguyên tử theo khóa, phù hợp với bộ đếm chính xác sau mỗi cập nhật. Nhưng mọi lần tăng khóa nóng đều cần cập nhật chính ánh xạ này theo cơ chế đồng bộ của CHM.

`LongAdder` phân tán cập nhật qua nhiều ô đếm nội bộ dưới tranh chấp, thường cho throughput cao hơn khi nhiều thread cùng tăng **một khóa nóng**, đổi lại tốn bộ nhớ hơn và `sum()` **không là snapshot nguyên tử** trong lúc có các cập nhật đồng thời. Sau khi tất cả worker đã hoàn tất, `sum()` trả kết quả chính xác của những increment đã thực hiện.

Với thao tác cần **đọc–điều kiện–ghi nguyên tử** trên một giá trị (ví dụ chỉ bán khi còn hàng), LongAdder **không phải thay thế trực tiếp cho `compute` hoặc `AtomicInteger.compareAndSet`**. Nó lý tưởng cho thống kê/frequency, không phải mọi state machine.

### 10.2. Không xóa LongAdder khi còn cập nhật

Nếu một thread gọi `map.computeIfAbsent(k,...).increment()`, còn thread khác gọi `map.remove(k)`, thread thứ nhất có thể tăng **LongAdder đã bị tách khỏi map**. Khi đó số lượt tăng không nằm trong value hiện tại của map. Tính thread-safe của CHM và LongAdder **không làm toàn chuỗi get-value rồi mutate trở thành nguyên tử cùng với remove/replace**.

Do đó với thống kê có reset/rotation, cần chính sách epoch, snapshot, stop-the-world/quiescence hoặc cấu trúc đồng bộ chuyên dụng. `LongAdder.sumThenReset()` cũng không bảo đảm snapshot chính xác khi có cập nhật đồng thời; đừng dùng nó như giao dịch kế toán.

## 11. Chương trình Java 17+: LongAdder qua nhiều worker

Tạo file **`LongAdderFrequencyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderFrequencyDemo {
    public static void main(String[] args) throws Exception {
        final int workers = 4;
        final int rounds = 2_500;

        ConcurrentHashMap<String, LongAdder> counts =
                new ConcurrentHashMap<>();
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    for (int j = 0; j < rounds; j++) {
                        counts.computeIfAbsent(
                                "java", key -> new LongAdder())
                                .increment();

                        counts.computeIfAbsent(
                                "go", key -> new LongAdder())
                                .add(2);
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("java: "
                    + counts.get("java").sum());
            System.out.println("go: "
                    + counts.get("go").sum());
            System.out.println("keys: " + counts.size());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 LongAdderFrequencyDemo.java
java LongAdderFrequencyDemo
```

**Stdout:**

```text
java: 10000
go: 20000
keys: 2
```

**Diễn giải:** Bốn worker tăng `"java"` mỗi lượt một đơn vị qua 2.500 vòng, tổng 10.000; `"go"` được tăng hai đơn vị mỗi lượt, tổng 20.000. Vì main chỉ đọc sau khi mọi Future đã `get()` thành công, không có cập nhật đồng thời khi gọi `sum()`. Nếu đọc `sum()` trong lúc worker đang chạy, đó chỉ là phép quan sát hiện tại, không phải atomic snapshot.

## 12. Tính toán trạng thái phức tạp: Value bất biến theo khóa

Một use case thường gặp là **tồn kho**, **định mức** hoặc **quota**. Một khóa có thể có nhiều field phải cập nhật nhất quán, chẳng hạn `available` và `sold`.

Thiết kế value bất biến:

```java
record Stock(int available, int sold) {}
```

`record` là cú pháp Java 16+ và dùng được với `--release 17`. Mỗi lần `compute` nhận giá trị cũ, tạo **Stock mới** chứa hai field đã tính tương thích.

```java
map.compute("SKU-1", (key, old) -> {
    if (old == null || old.available() == 0) {
        return old;
    }
    return new Stock(
            old.available() - 1, old.sold() + 1);
});
```

Đây là đoạn **trong phương thức** với `map` kiểu `ConcurrentHashMap<String,Stock>` và record Stock được khai báo trong scope hợp lệ.

**Tại sao không tách thành hai map?** Nếu `available` và `sold` nằm ở hai khóa hoặc hai map riêng, hai lời gọi `compute` **không tạo một transaction nguyên tử xuyên cả hai biến**. Khi cùng tồn tại trong một value bất biến gắn một khóa, một phép compute có thể thay cả hai field **một cách nhất quán tại thời điểm công bố mapping mới**.

### 12.1. Tại sao không mutate object trong callback?

`compute(key, (k, stock) -> { stock.available--; stock.sold++; return stock; })` khi value mutable có thể gây race đối với thread đã giữ reference và đọc trực tiếp value ngoài compute. Dù cập nhật *mapping* nguyên tử, việc ghi nhiều field trên một object **không trở thành transaction riêng** đối với các reader không đồng bộ.

Value bất biến giúp:

- Không có trạng thái một field đã đổi, field còn lại chưa đổi được thấy qua một reference công bố.
- Ít phải tự đồng bộ trên nội dung object.
- Dễ kiểm thử bất biến `available + sold == constant` khi logic chỉ bán và không nhập hàng.
- Cấu trúc value là snapshot gọn cho một khóa.

Tuy nhiên **không** có nghĩa một thao tác đọc **nhiều khóa** trên map đồng thời cho snapshot nhất quán.

## 13. Java 17+: Cạnh tranh bán ba sản phẩm, không oversell

Tạo file **`ConcurrentInventoryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentInventoryDemo {
    record Stock(int available, int sold) {}

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Stock> inventory =
                new ConcurrentHashMap<>();
        inventory.put("SKU-1", new Stock(3, 0));

        ExecutorService pool =
                Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> requests = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                requests.add(pool.submit(() -> {
                    start.await();
                    inventory.compute("SKU-1", (key, old) -> {
                        if (old == null || old.available() == 0) {
                            return old;
                        }
                        return new Stock(
                                old.available() - 1,
                                old.sold() + 1);
                    });
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> request : requests) {
                request.get();
            }

            Stock finalState = inventory.get("SKU-1");
            System.out.println("sold: "
                    + finalState.sold()
                    + ", available: "
                    + finalState.available());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentInventoryDemo.java
java ConcurrentInventoryDemo
```

**Stdout:**

```text
sold: 3, available: 0
```

Dù có tám request cùng cố giảm hàng, chỉ có ba phép trừ thành công vì sau đó `available == 0` và các callback tiếp theo giữ nguyên state. `sold` cũng được cập nhật trong **cùng một value mới**, tránh trạng thái hai field lệch nhau.

**Giới hạn rất quan trọng:** Demo chỉ bảo đảm tồn kho **của một khóa trong một tiến trình có một ConcurrentHashMap dùng chung**. Nếu ứng dụng có nhiều server/pod hay cần đồng thời cập nhật đơn hàng, ví tiền và kho trong database, không thể coi `ConcurrentHashMap.compute` là một distributed transaction. Cần cơ chế ở tầng lưu trữ hoặc điều phối, ví dụ transaction SQL/optimistic locking/unique constraints/idempotency theo thiết kế hệ thống.

## 14. Exception, null, và việc mapping giữ nguyên

Các lỗi trong callback phải có ngữ nghĩa rõ:

- Nếu `compute` / `merge` / `computeIfPresent` callback ném một unchecked exception hoặc `Error`, callback không trả giá trị hợp lệ và **mapping hiện có không bị thay đổi bởi invocation đó**. Exception được ném cho caller.
- Với `computeIfAbsent`, nếu callback ném unchecked exception, mapping absent vẫn không được thiết lập.
- Nếu callback trả `null`, đó **không phải exception**; nó là quy tắc **không tạo/xóa mapping**.
- Nếu `merge` nhận **incoming value null**, CHM ném `NullPointerException` trước khi có thể gộp.
- Nếu key hoặc callback function là null ở những phương thức này, CHM ném `NullPointerException`.

**Lưu ý ngoại lệ và side effect:** Bảo đảm “mapping unchanged” chỉ áp dụng cho **ánh xạ của CHM được thao tác**. Nếu callback đã gửi email, ghi ra file, trừ tiền hoặc sửa một object bên ngoài rồi mới ném exception, những side effect đó **không được rollback** bởi CHM. Vì vậy callback nên thuần/không có tác dụng phụ quan trọng.

### 14.1. `Math.addExact` để phát hiện overflow

`Integer::sum` dùng phép cộng `int` thông thường, có thể **tràn số** khi tổng vượt phạm vi int mà không ném exception. Nếu ứng dụng phải phát hiện overflow, có thể dùng:

```java
counts.merge("total", 1, Math::addExact);
```

Đây là đoạn trong phương thức với `counts` kiểu `ConcurrentHashMap<String,Integer>`. Khi phép cộng có overflow, `Math.addExact` ném `ArithmeticException`; trong thao tác merge với mapping present, ánh xạ cũ được giữ nguyên. Với số đếm dài và tần suất lớn, xem xét `Long`, `LongAdder` hoặc một cấu trúc domain phù hợp.

Tuy nhiên, `merge` chỉ gọi callback khi key present; nếu absent, incoming value được gắn trực tiếp, không có phép addExact. Điều này đúng cho phép tăng 1 nhưng có thể sai nếu incoming value tự nó vi phạm quy tắc domain; hãy validate đầu vào trước khi gọi.

## 15. Chương trình Java 17+: Lỗi callback và tín hiệu null

Tạo file **`ConcurrentMapFailureDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentMapFailureDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("stable", 9);

        boolean failedCompute = false;
        try {
            map.compute("stable", (key, old) -> {
                throw new IllegalArgumentException("invalid");
            });
        } catch (IllegalArgumentException ex) {
            failedCompute = true;
        }
        System.out.println("compute exception: "
                + failedCompute);
        System.out.println("stable after compute: "
                + map.get("stable"));

        boolean failedMerge = false;
        try {
            map.merge("stable", 1, (old, add) -> {
                throw new IllegalStateException("oops");
            });
        } catch (IllegalStateException ex) {
            failedMerge = true;
        }
        System.out.println("merge exception: "
                + failedMerge);
        System.out.println("stable after merge: "
                + map.get("stable"));

        System.out.println("null from ifAbsent: "
                + map.computeIfAbsent(
                        "missing", key -> null));
        System.out.println("missing exists: "
                + map.containsKey("missing"));

        boolean nullValueRejected = false;
        try {
            map.merge("stable", null, Integer::sum);
        } catch (NullPointerException ex) {
            nullValueRejected = true;
        }
        System.out.println("null merge value rejected: "
                + nullValueRejected);

        System.out.println("remove via compute: "
                + map.compute("stable", (key, old) -> null));
        System.out.println("stable exists: "
                + map.containsKey("stable"));
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentMapFailureDemo.java
java ConcurrentMapFailureDemo
```

**Stdout:**

```text
compute exception: true
stable after compute: 9
merge exception: true
stable after merge: 9
null from ifAbsent: null
missing exists: false
null merge value rejected: true
remove via compute: null
stable exists: false
```

**Giải thích từng nhóm:** `stable` giữ giá trị 9 sau hai lần callback ném lỗi; `computeIfAbsent` trả null nhưng không chèn `missing`; `merge` không chấp nhận incoming null; `compute` trả null xóa `stable`. Đây là bốn tình huống khác nhau, không nên gom chung vào cách nói “null làm lỗi map”.

## 16. Cảnh báo lớn: Không sửa map này bên trong callback compute

Javadoc `ConcurrentHashMap` yêu cầu **mapping/remapping function không được sửa chính map đó trong lúc tính toán**. Điều này áp dụng cho `compute`, `computeIfAbsent`, `computeIfPresent` và `merge`.

**Phản ví dụ không được chạy trong production:**

```java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();

map.computeIfAbsent("A", key -> {
    map.put("B", 1); // Vi phạm quy tắc callback.
    return 2;
});
```

Đây là **mã phản ví dụ**; không dựa vào nó để chứng minh một hành vi lỗi tất định. Dù sửa khóa khác, `put("B",1)` vẫn là **cập nhật cùng map** trong callback. Nó có thể va chạm cơ chế khóa/collision nội bộ, gây chờ hoặc làm chương trình bị lỗi; không nên dùng.

### 16.1. Tự gọi compute trên cùng khóa

```java
// Phản ví dụ: recursive update lên cùng ConcurrentHashMap.
map.computeIfAbsent("A", key ->
        map.computeIfAbsent("A", nestedKey -> 5));
```

Đây là đoạn phản ví dụ; implementation có thể ném `IllegalStateException` khi **phát hiện** recursion có nguy cơ không bao giờ kết thúc. Điều kiện “detectably” trong Javadoc rất quan trọng: **không bảo đảm** mọi dạng callback nguy hiểm đều được phát hiện hoặc luôn ném exception ngay.

**Giải pháp:** Tính dữ liệu phụ trợ **trước** invocation compute hoặc đưa nó sang cấu trúc/transaction khác có hợp đồng rõ; trong callback chỉ tính giá trị mới từ `key`, `oldValue` và input bất biến được chuẩn bị sẵn. Nếu cần cập nhật các khóa khác cùng lúc, không dựa vào nested compute của một map để làm transaction đa khóa.

### 16.2. Callback có được gọi một API đọc của map?

Tài liệu đặc biệt cấm **sửa** map trong callback và khuyên callback ngắn. Dù một số lời gọi đọc có thể hoạt động, **không nên thiết kế callback phụ thuộc vào snapshot của các khóa khác**, vì map có cập nhật đồng thời và không có atomic snapshot toàn bộ. Nếu logic phụ thuộc nhiều khóa, cần cơ chế đồng bộ/transaction cấp cao hơn thay vì suy ra rằng đọc trong callback ổn định.

### 16.3. Đặt I/O chặn trong callback nguy hiểm thế nào?

Khi callback chạy lâu, Javadoc cảnh báo một số thao tác cập nhật khác có thể bị chặn. Điều này không chỉ làm giảm throughput mà còn dễ sinh **lock-ordering / resource-cycle** khi callback chờ một tác vụ khác cần update cùng map. Hãy tách việc tải dữ liệu, tính toán phức tạp và side effect khỏi callback khi hợp đồng yêu cầu latency thấp.

Một số ứng dụng cache cần “chỉ một thread gọi loader” nhưng loader lại chậm. Khi đó nên thiết kế **single-flight bằng future per key**, cache loader chuyên dụng hoặc cơ chế của thư viện cache; không nhét HTTP call dài vào computeIfAbsent rồi mặc định map vẫn vận hành tốt dưới tải.

## 17. Mutable value: Vì sao synchronized map chưa đủ

Lấy một value mutable từ CHM không mang lại quyền **sửa nó an toàn**:

```java
ConcurrentHashMap<String, java.util.List<String>> map =
        new ConcurrentHashMap<>();

map.computeIfAbsent(
        "topic", key -> new java.util.ArrayList<>())
        .add("java");
```

Đây là **phản ví dụ cho nhiều thread cùng dùng**, không phải lời khuyên. `computeIfAbsent` đảm bảo khởi tạo một List cho khóa absent, nhưng `ArrayList.add` không thread-safe. Hai thread lấy cùng list có thể cạnh tranh làm hỏng dữ liệu hoặc mất phần tử.

### 17.1. Dùng collection value thread-safe

Nếu cần **nhiều giá trị theo từng khóa**, có thể dùng một concurrent set:

```java
ConcurrentHashMap<String, java.util.Set<String>> tags =
        new ConcurrentHashMap<>();

tags.computeIfAbsent(
        "topic", key -> ConcurrentHashMap.<String>newKeySet())
        .add("java");
```

`ConcurrentHashMap.newKeySet()` tạo một Set concurrent, phù hợp cho phần tử duy nhất theo key. `ConcurrentLinkedQueue` có thể phù hợp nếu cần giữ nhiều phần tử, cho phép trùng lặp; `CopyOnWriteArrayList` phù hợp khi đọc nhiều hơn ghi và chấp nhận chi phí copy cao mỗi lần thêm.

**Vẫn có giới hạn:** `computeIfAbsent` trả reference của set, rồi `set.add` diễn ra **sau** phép thao tác map, không phải cùng một transaction với map.remove/replace. Nếu có thread xóa mapping trong lúc thread khác giữ set cũ, phần tử mới có thể được thêm vào **set không còn được map tham chiếu**.

### 17.2. Muốn cập nhật cả entry một cách nguyên tử thì sao?

Có thể lưu một **value bất biến** (ví dụ `Set.copyOf(...)` khi phù hợp) rồi trong `compute` tạo một value mới. Điều này bảo vệ phép thay mapping theo khóa, nhưng sao chép cả set mỗi lần cập nhật có chi phí cao. Phải chọn cấu trúc dựa trên tần suất ghi/đọc, nhu cầu snapshot và chính sách xóa/thay thế mapping.

Đối với bài toán aggregate nhiều khóa cần giao dịch, một CHM chứa nested concurrent collections không tự tạo khả năng atomic cross-key.

## 18. Java 17+: Đưa nhiều tag vào một concurrent set

Tạo file **`ConcurrentMultiValueDemo.java`**:

```java
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentMultiValueDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Set<String>> tags =
                new ConcurrentHashMap<>();

        tags.computeIfAbsent(
                "topic",
                key -> ConcurrentHashMap.<String>newKeySet())
                .add("java");

        tags.computeIfAbsent(
                "topic",
                key -> ConcurrentHashMap.<String>newKeySet())
                .add("concurrency");

        System.out.println("topic tags: "
                + new TreeSet<>(tags.get("topic")));
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentMultiValueDemo.java
java ConcurrentMultiValueDemo
```

**Stdout:**

```text
topic tags: [concurrency, java]
```

`ConcurrentHashMap.newKeySet` cung cấp set thread-safe, còn `new TreeSet<>(...)` **chỉ dùng để in theo thứ tự ổn định** sau khi các thao tác demo đã hoàn thành. `ConcurrentHashMap` và key set của nó **không bảo đảm iteration order**, nên trong test không nên khẳng định thứ tự tự nhiên nếu không tự sắp xếp.

## 19. Tính nguyên tử theo khóa không bao trùm nhiều khóa

Một ngộ nhận nguy hiểm là:

```java
balances.compute("A", (key, old) -> old - amount);
balances.compute("B", (key, old) -> old + amount);
```

Đây là **phản ví dụ kiến trúc** với `balances` và `amount` giả định. Hai lần compute đều nguyên tử **cho từng khóa**, nhưng toàn bộ “chuyển tiền từ A sang B” **không nguyên tử xuyên hai khóa**:

- Thread khác có thể thấy A đã bị trừ, B chưa được cộng.
- Nếu bước thứ hai ném lỗi, số dư tổng có thể mất cân đối.
- Nếu nhiều server có các map bộ nhớ riêng, không có một CHM nào giúp đồng bộ dữ liệu giữa tiến trình.
- Nếu A và B là cùng khóa hoặc số tiền vượt số dư, còn phải kiểm tra business invariant.

**Không dùng ConcurrentHashMap làm kho giao dịch tài chính phân tán.** Khi yêu cầu tính nhất quán đa khóa/đa thực thể, chọn database transaction, lock cấp domain, thiết kế state một khóa khi khả thi, hoặc giao thức điều phối có bù trừ/idempotency theo hệ thống.

### 19.1. Điều gì thread-safe trong CHM?

CHM đảm bảo các operation riêng của map theo contract, và per-key happens-before đối với retrieval thấy giá trị update. Nó **không**:

- Tự đồng bộ state mutable bên trong mọi `V`.
- Cung cấp snapshot nguyên tử của tất cả entries khi map đang đổi.
- Khiến một chuỗi `get`, `containsKey`, `put` ở caller thành một transaction.
- Bảo đảm các key có cùng thứ tự/trật tự iteration.
- Duy trì tính bền vững qua crash/process restart như database.
- Đảm bảo nhiều map trong hai process chia sẻ dữ liệu.

### 19.2. Iterator, size và mappingCount dưới cập nhật đồng thời

Iterator/Spliterator của CHM được thiết kế **weakly consistent**: có thể phản ánh các phần tử được quan sát khi hoặc sau khi iterator tạo, nhưng **không phải một snapshot nguyên tử**. Chúng không ném `ConcurrentModificationException` chỉ vì thread khác cập nhật map. `size`, `isEmpty`, `containsValue` hoặc `mappingCount` trong lúc ghi có thể phản ánh **trạng thái tạm thời/ước lượng**.

Không làm quyết định quan trọng dạng “nếu size < quota thì put” mà tin phép kiểm tra và phép cập nhật là nguyên tử. Hãy đặt điều kiện quota vào một state/transaction thích hợp, hoặc dùng admission control khác.

## 20. So sánh compute, merge với các thao tác CAS trên map

`ConcurrentMap` còn có các phương thức hữu ích:

| API | Khi nào phù hợp? | Khác biệt so với compute/merge |
| --- | --- | --- |
| `putIfAbsent(key, value)` | Chèn value đã có sẵn nếu khóa absent | Không gọi factory; value có thể đã được tính dư thừa |
| `replace(key, expectedOld, newValue)` | CAS-like replace nếu mapping đúng giá trị kỳ vọng | Caller điều khiển vòng retry nếu cần |
| `remove(key, expectedValue)` | Xóa chỉ khi value còn bằng expected | Hữu ích để tránh xóa giá trị vừa thay bởi thread khác |
| `compute(key, fn)` | RMW tổng quát theo khóa | Callback thấy old hiện tại và trả state mới |
| `computeIfAbsent(key, fn)` | Khởi tạo khi absent | Bỏ qua factory nếu đã present |
| `merge(key, incoming, fn)` | Cộng/gộp incoming với old | Callback không chạy khi absent |
| `computeIfPresent(key, fn)` | Chỉ sửa mapping đã có | Không tạo entry mới |

`replace(key, expectedOld, newValue)` và `remove(key, expectedValue)` là những primitive cập nhật có điều kiện rất hữu ích khi muốn thao tác dựa trên một trạng thái đã đọc. Nhưng nếu phải đảm bảo nhiều field/value cùng lúc, một record bất biến với `compute` hoặc transaction phù hợp vẫn dễ diễn đạt hơn.

### 20.1. Nếu muốn “check then act”

Đoạn:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

không nguyên tử dưới cập nhật đồng thời, nên một thread khác có thể xen vào sau `containsKey`. Dùng `putIfAbsent` khi value đã sẵn sàng hoặc `computeIfAbsent` khi cần khởi tạo trên sự vắng mặt.

Tương tự, nếu muốn xóa khi value còn là một phiên bản cụ thể, `remove(key, expectedValue)` an toàn hơn chuỗi `if (Objects.equals(map.get(key),expected)) map.remove(key)`.

### 20.2. Tại sao không synchronized toàn bộ map?

Khóa ngoài map bằng `synchronized` có thể làm các thao tác caller tuần tự và làm mất lợi thế concurrency nếu khóa quá thô. `compute`/`merge` cho phép thể hiện **một update theo khóa** ngay qua contract CHM. Tuy nhiên, khi thật sự phải bảo vệ **bất biến xuyên nhiều khóa**, một cơ chế đồng bộ chung hoặc transaction có thể là lựa chọn cần thiết; đừng vì ngại lock mà để dữ liệu sai.

## 21. Hiệu năng và khả năng vận hành

Cả ba phương thức là công cụ **đúng đắn** trước khi là công cụ tối ưu tốc độ. Thời gian chạy thực phụ thuộc:

- **Contention theo khóa**: Một khóa “hot” được mọi thread cập nhật sẽ có nhiều tranh chấp hơn các khóa phân tán.
- **Chi phí callback**: Hàm tính toán lâu làm thao tác cập nhật khác chờ lâu hơn, đôi khi ảnh hưởng cả khóa chia sẻ bin.
- **HashCode chất lượng**: Khóa có hash collision cao gây thêm tranh chấp và giảm hiệu năng.
- **Kích cỡ map/resize**: Resizing, cấp phát value mới, GC có thể ảnh hưởng latency.
- **Chi phí boxing**: `Integer`/`Long` liên tục tạo/boxing giá trị, cần cân nhắc ở tải lớn.
- **Hình dạng dữ liệu**: `LongAdder` dùng ô đếm phân tán, đổi thêm bộ nhớ lấy throughput dưới contention.
- **Những lần tạo giá trị**: `computeIfAbsent` chỉ khởi tạo khi absent, còn `putIfAbsent(key, expensiveCreate())` vẫn đánh giá `expensiveCreate()` trước lời gọi dù key đã present.
- **Tài nguyên ngoài map**: Blocking DB/HTTP trong callback thường tệ hơn vài phép cộng.

### 21.1. Chọn cấu trúc theo nhu cầu

| Yêu cầu | Hướng cân nhắc |
| --- | --- |
| Tăng Integer chính xác theo khóa | `merge(key,1,Integer::sum)` hoặc `compute` |
| Khởi tạo object rẻ khi vắng | `computeIfAbsent` |
| Đếm khóa nóng tần suất cao | `ConcurrentHashMap<K, LongAdder>` |
| Điều chỉnh state phức tạp của một khóa | `compute` + value bất biến |
| Value đa tập cần concurrent mutation | `ConcurrentHashMap.newKeySet()` / collection concurrent phù hợp |
| Xóa nếu value vẫn là expected | `remove(key, expectedValue)` |
| Cập nhật nguyên tử nhiều khóa | Transaction/lock domain, **không chỉ CHM.compute** |
| Cache load dữ liệu I/O dài | Thư viện cache/single-flight/async architecture, callback ngắn |
| Chỉ cần lookup không có update | Map bất biến/read-only có thể đơn giản hơn CHM |

### 21.2. Benchmark mà không nhầm lẫn

Khi so sánh `merge` với `LongAdder`, cần đo throughput và latency với **phân bố khóa thực tế**: một khóa nóng khác nhiều khóa hiếm. JMH giúp benchmark vi mô; test tải ứng dụng giúp đánh giá GC, memory, request latency, contention và downstream. Không kết luận `LongAdder` luôn nhanh hơn `merge` với mọi mẫu tải; dưới contention thấp, chi phí triển khai và số entry có thể quyết định.

### 21.3. Cảnh báo `null`, overflow và memory

Tất cả key/value lưu trong CHM phải non-null. Khi dùng Integer, phép cộng số lớn có thể overflow. Với LongAdder, phép `sum()` không atomic snapshot trong lúc có update; với một reference tới mutable object, việc truy cập nội dung vẫn phải tuân hợp đồng thread-safety của object đó.

## 22. Bộ kiểm thử biên nên có

| Trường hợp | Kỳ vọng chính |
| --- | --- |
| `compute` trên khóa absent | Callback được gọi với old=null |
| `compute` trên khóa present | Callback thấy old non-null |
| `compute` callback trả null | Xóa mapping hoặc vẫn absent |
| `computeIfAbsent` lần đầu | Có thể khởi tạo một mapping non-null |
| `computeIfAbsent` lần thứ hai khi present | Factory không chạy |
| `computeIfAbsent` trả null | Không tạo mapping |
| `computeIfAbsent` ném lỗi | Mapping absent không được tạo |
| `computeIfPresent` khi absent | Callback không chạy |
| `computeIfPresent` trả null | Xóa mapping |
| `merge` khi absent | Gắn incoming value, callback không chạy |
| `merge` khi present | Callback nhận old và incoming |
| `merge` callback trả null | Xóa mapping |
| `merge` incoming value null | NullPointerException |
| Compute/merge callback ném RuntimeException | Mapping present giữ nguyên |
| Nhiều worker `compute(key,+1)` | Không lost update, tổng đúng |
| Nhiều worker `merge(key,1,Integer::sum)` | Không lost update, tổng đúng |
| Factory `computeIfAbsent` cùng khóa | Khi callback tạo non-null và mapping không bị xóa, chỉ một giá trị được tạo |
| Nhiều worker `LongAdder.increment` | Tổng đúng sau khi đã join worker |
| Callback recursive update | Không thực hiện; phải test kiến trúc tránh, không kỳ vọng loại deadlock luôn tự phát hiện |
| Tồn kho theo một khóa | Không âm nếu callback giữ điều kiện |
| Thay/xóa mapping khi value mutable đang dùng | Cần policy bổ sung, không giả định atomic |
| Hash collision / nhiều khóa | Kiểm tra latency dưới tải; không giả định khóa khác không bao giờ bị chặn |
| Đọc size/iteration dưới cập nhật | Không giả định snapshot nhất quán |
| Nhiều map/server | Không kỳ vọng tính nguyên tử phân tán |

**Nguyên tắc kiểm thử:** Khi muốn chứng minh đồng thời, dùng `CountDownLatch` để tổ chức cạnh tranh, `Future.get()` để nhận lỗi và chờ hoàn tất, sau đó assert **kết quả bất biến**. Đừng viết test dựa vào Thread.sleep hoặc tên/thứ tự thread để khẳng định scheduler luôn giống nhau.

## 23. Java 17+: Bài kiểm thử hợp đồng tính toán theo khóa

Tạo file **`ConcurrentMapBoundaryChecks.java`**. Hàm `check` chủ động ném `AssertionError`, không phụ thuộc cờ `-ea`.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentMapBoundaryChecks {
    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        check(map.compute("k", (key, old) ->
                        old == null ? 1 : old + 1) == 1,
                "compute absent");
        check(map.compute("k", (key, old) ->
                        old == null ? 1 : old + 1) == 2,
                "compute present");
        System.out.println("Compute: PASS");

        AtomicInteger calls = new AtomicInteger();
        check(map.computeIfAbsent("seed", key -> {
                    calls.incrementAndGet();
                    return 4;
                }) == 4, "ifAbsent first");
        check(map.computeIfAbsent("seed", key -> {
                    calls.incrementAndGet();
                    return 99;
                }) == 4, "ifAbsent second");
        check(calls.get() == 1, "factory called twice");
        check(map.computeIfAbsent(
                        "none", key -> null) == null,
                "null factory");
        check(!map.containsKey("none"), "unexpected null key");
        System.out.println("ComputeIfAbsent: PASS");

        check(map.merge("sum", 3, Integer::sum) == 3,
                "merge insert");
        check(map.merge("sum", 4, Integer::sum) == 7,
                "merge sum");
        check(map.merge(
                        "sum", 1, (old, add) -> null) == null,
                "merge remove");
        check(!map.containsKey("sum"), "not removed");
        System.out.println("Merge: PASS");

        check(map.computeIfPresent(
                        "k", (key, old) -> old + 3) == 5,
                "ifPresent");
        check(map.compute(
                        "k", (key, old) -> null) == null,
                "compute remove");
        check(!map.containsKey("k"), "compute did not remove");
        System.out.println("Removal: PASS");

        boolean rejected = false;
        try {
            map.merge("seed", null, Integer::sum);
        } catch (NullPointerException ex) {
            rejected = true;
        }
        check(rejected, "null merge value accepted");
        System.out.println("Null validation: PASS");

        check(map.get("seed") == 4, "seed changed");
        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 ConcurrentMapBoundaryChecks.java
java ConcurrentMapBoundaryChecks
```

**Stdout:**

```text
Compute: PASS
ComputeIfAbsent: PASS
Merge: PASS
Removal: PASS
Null validation: PASS
All checks: PASS
```

Bộ test này xác nhận các **trường hợp biên của API khi chạy tuần tự**. Nó cần được kết hợp với `ConcurrentKeyAtomicityDemo` và `LongAdderFrequencyDemo` cho cạnh tranh cùng khóa, `ConcurrentInventoryDemo` cho bất biến giá trị, và test tải/quy tắc domain khi sản phẩm thực sự phải chịu request đồng thời. Nó không khẳng định CHM giải quyết giao dịch nhiều khóa.

## 24. Những lỗi phổ biến cần tránh

1. **Dùng `get(key)` rồi `put(key, old+1)` khi nhiều thread:** mỗi lời gọi thread-safe nhưng chuỗi không nguyên tử, có thể mất cập nhật.
2. **Nghĩ `computeIfAbsent` luôn chạy callback:** nếu khóa đã có, callback không chạy.
3. **Nghĩ `compute` chỉ chạy khi khóa có sẵn:** callback chạy cho cả absent, old=null.
4. **Nghĩ `merge` callback chạy khi absent:** absent được gắn incoming value trực tiếp.
5. **Nhầm tham số callback của merge là `(key,old)`:** chúng là `(old,incoming)`.
6. **Dùng `old + 1` trong compute mà không xử lý old=null:** có thể NullPointerException khi unboxing.
7. **Nghĩ callback trả null sẽ lưu `key->null`:** CHM cấm null values; null là tín hiệu không tạo/xóa mapping.
8. **Truyền incoming null vào merge để yêu cầu xóa:** sẽ NPE; muốn xóa theo điều kiện, remapping callback trả null hoặc dùng remove/compute.
9. **Dùng `computeIfAbsent` như cache giá trị null:** null không được ghi; các lần gọi sau vẫn có thể tính lại.
10. **Tin factory chỉ gọi một lần trong toàn đời khóa:** xóa, lỗi hoặc trả null có thể khiến factory được gọi lại ở invocation sau.
11. **Áp dụng bảo đảm callback đúng một lần cho mọi ConcurrentMap:** default implementation có thể retry callback dưới contention.
12. **Sửa chính CHM trong callback:** vi phạm contract, có thể bị IllegalStateException hoặc gây chờ/deadlock.
13. **Gọi API I/O chậm trong callback:** có thể chặn các cập nhật khác, tăng latency.
14. **Thực hiện side effect tài chính/HTTP trong callback:** CHM không rollback tác vụ ngoài map khi callback ném exception.
15. **Lưu ArrayList trong CHM rồi nhiều thread cùng list.add:** CHM không làm value mutable trở thành thread-safe.
16. **Gọi `computeIfAbsent(...).increment()` với LongAdder rồi tin cả chuỗi là transaction cùng remove(key):** increment trên value riêng, không atomic cùng xóa entry.
17. **Dùng LongAdder cho kiểm tra quota nguyên tử:** sum() không là atomic snapshot dưới cập nhật đồng thời.
18. **Dùng `size() < limit` rồi `put` để kiểm soát giới hạn:** phép check và put tách rời.
19. **Tin hai compute trên hai khóa là một transaction:** không có bảo đảm multi-key atomicity.
20. **Tin map trong RAM đồng bộ giữa nhiều pod:** mỗi process có bộ nhớ riêng nếu không dùng cơ chế chia sẻ.
21. **Dùng Integer::sum cho số lớn mà không xét overflow:** phép cộng int có thể tràn, cân nhắc long/Math.addExact/LongAdder.
22. **Tin callback của computeIfPresent chạy khi khóa absent:** nó chỉ chạy khi present.
23. **Giả định iterator CHM phản ánh snapshot cố định:** weakly consistent, không đảm bảo toàn map nhất quán tại một thời điểm.
24. **In trực tiếp map.toString và assert thứ tự:** CHM không bảo đảm iteration order.
25. **Dùng `putIfAbsent(key, expensiveCreate())` và nghĩ factory chỉ chạy khi absent:** biểu thức `expensiveCreate()` được đánh giá trước khi gọi putIfAbsent.
26. **Dùng `merge(key,-1,Integer::sum)` để giảm quota mà không kiểm tra absent:** nếu absent, nó chèn -1.
27. **Gộp logic đa-field vào nhiều value/keys rồi mong toàn cục nhất quán:** cần value bất biến trong một khóa hoặc transaction khác.
28. **Bỏ qua callback exception:** cập nhật có thể không diễn ra, caller phải xử lý.
29. **Nghĩ CHM compute bảo đảm mọi update khóa khác chạy không chặn:** collision/chi tiết phối hợp có thể khiến một số writer phải chờ.
30. **Tăng số thread để tối ưu khóa nóng:** bottleneck là per-key contention; cần thiết kế counters/concurrency pattern hợp lý.
31. **Xóa LongAdder khi worker còn tăng nó:** thread có thể tăng object cũ đã rời map, làm mất số đếm hiển thị.
32. **Tưởng mọi biểu đồ LongAdder.sum() trong lúc đang cập nhật là snapshot nhất quán:** Javadoc nói rõ sum không phải atomic snapshot.
33. **Dùng cấu trúc không đồng bộ để làm map cache trong service đa thread:** CHM có ý nghĩa khi thực sự có concurrent writes/reads; nếu dữ liệu chỉ đọc, map bất biến có thể đơn giản hơn.
34. **Mặc định giá trị trả về compute/merge là giá trị cũ:** chúng trả giá trị mới hoặc null nếu không còn mapping.
35. **Không đợi Future.get khi test concurrency:** có thể đọc sớm hoặc bỏ qua exception từ worker.

## 25. Checklist chọn API trước khi code review

- [ ] Tôi đang **khởi tạo khi thiếu**, **cộng/gộp**, hay **chuyển trạng thái tổng quát**?
- [ ] Nếu chỉ khởi tạo khi vắng, `computeIfAbsent` có phù hợp không?
- [ ] Nếu cộng/gộp incoming value non-null, `merge` có đơn giản hơn `compute` không?
- [ ] Nếu phải xét trạng thái absent, trả null/xóa hoặc điều kiện phức tạp, `compute` có rõ hơn không?
- [ ] Callback có **xử lý old=null** đúng khi dùng compute không?
- [ ] Tôi có hiểu null **trả về** khác null **truyền vào merge** không?
- [ ] Callback có thực sự **ngắn, đơn giản, không I/O chặn**, và không sửa chính map không?
- [ ] Có side effect bên ngoài callback khiến exception không rollback đầy đủ không?
- [ ] Value là **bất biến** hay có cơ chế thread-safe riêng khi nhiều thread mutate?
- [ ] Cập nhật cần nguyên tử ở **một khóa** hay **nhiều khóa/dịch vụ**?
- [ ] Tôi có dựa sai vào `size`/iteration như snapshot hoặc precondition concurrency không?
- [ ] Tôi có dùng `LongAdder` vì profiling cho thấy contention đủ lớn, và hiểu `sum` không atomic không?
- [ ] Khi xóa/replace value đồng thời với việc mutate value, có chính sách bảo vệ không?
- [ ] Dữ liệu kiểu Integer/Long có nguy cơ overflow không?
- [ ] Unit test bao phủ absent, present, null, exception, callback call count?
- [ ] Concurrency test có dùng latch/futures và assert tổng sau khi worker hoàn tất?
- [ ] Tôi có dựa vào contract **ConcurrentHashMap** thay vì gán nhầm cho mọi implementation `ConcurrentMap` không?
- [ ] Nếu ứng dụng có nhiều process/DB, có transaction/lock/idempotency đúng phạm vi không?

## 26. Câu hỏi ôn tập

1. Vì sao `ConcurrentHashMap.get` và `put` riêng lẻ thread-safe nhưng chuỗi `get -> put` có thể bị mất lượt tăng?
2. `compute("x",(k,old)->...)` có được gọi khi key absent không? old bằng gì?
3. `computeIfAbsent` có gọi factory khi key đã có value non-null không?
4. `merge("x",1,Integer::sum)` với khóa absent có gọi `Integer::sum` không?
5. Callback của `merge` nhận `(key,old)` hay `(old,incoming)`?
6. Khi remapping callback trả null cho `compute` hoặc `merge`, entry đang có sẽ ra sao?
7. Tại sao `merge(key,null,fn)` khác với callback trả null?
8. Khi factory `computeIfAbsent` trả null, khóa có còn absent không? Lần gọi sau có thể chạy factory không?
9. Với map `ConcurrentHashMap<K,LongAdder>`, phép `increment` diễn ra trong khóa nội bộ CHM hay trên LongAdder object?
10. Vì sao `LongAdder.sum()` không thích hợp làm atomic snapshot khi nhiều thread đang update?
11. Vì sao `computeIfAbsent(k, x -> new ArrayList<>()).add(v)` không tự an toàn cho nhiều thread?
12. Callback `computeIfAbsent` có được update khóa khác của chính CHM không?
13. Exception từ callback `compute`/`merge` ảnh hưởng mapping cũ thế nào? Nó có rollback side effect database không?
14. Hai `compute` trên tài khoản A/B có tạo transaction chuyển tiền không?
15. Khi nào dùng `putIfAbsent` thay vì `computeIfAbsent`?
16. Vì sao test nhiều thread phải đợi `Future.get` trước khi assert kết quả?
17. Trong ví dụ quota 3 đơn vị, tám request đồng thời có thể bán quá ba không nếu dùng `compute` với record immutable đúng cách?
18. `ConcurrentMap` default method có nhất thiết cùng bảo đảm số lần gọi callback với `ConcurrentHashMap` override không?

**Đáp án gợi ý:** (1) Hai thread có thể cùng đọc old rồi ghi đè nhau. (2) Có; old=null vì CHM không chứa value null. (3) Không. (4) Không; chèn 1 trực tiếp. (5) old,incoming. (6) Xóa mapping nếu present, absent vẫn absent. (7) merge đòi incoming non-null và ném NPE khi null. (8) Vẫn absent, lời gọi sau có thể chạy lại. (9) Trên LongAdder; khởi tạo value mới là phần atomic của computeIfAbsent. (10) sum không là atomic snapshot. (11) ArrayList không thread-safe. (12) Không; callback không được sửa map đó. (13) Mapping được giữ nguyên, side effect ngoài map không được rollback. (14) Không. (15) Khi value đã được chuẩn bị sẵn và chỉ cần chèn có điều kiện. (16) Đợi worker hoàn tất/nhận lỗi để so kết quả cuối. (17) Không, số sold tối đa ba nếu tất cả update cùng một khóa/map dùng chung và callback đúng. (18) Không; cần xem implementation.

**Kết luận:** `ConcurrentHashMap.compute`, `computeIfAbsent` và `merge` là những công cụ cập nhật **nguyên tử theo ánh xạ của từng khóa**. `compute` phù hợp chuyển trạng thái tổng quát, `computeIfAbsent` khởi tạo khi thiếu, `merge` gộp incoming value. Giá trị callback `null` là **tín hiệu không tạo/xóa**, không phải giá trị được lưu. Callback phải **ngắn và không sửa map**, và tính nguyên tử không mở rộng sang giá trị mutable, nhiều khóa hoặc nhiều process. Với bộ đếm nóng, `LongAdder` hữu ích nếu hiểu giới hạn của snapshot; với state phức tạp một khóa, value bất biến + `compute` giúp giữ invariant. Kết hợp unit test các trường hợp absent/present/null/exception với concurrency test có latch và Future sẽ giúp code đúng, dễ vận hành trên Java hiện hành.

## Tài liệu Java chính thức còn áp dụng

- `ConcurrentHashMap` (Java SE 26): contract riêng của `compute`, `computeIfAbsent`, `computeIfPresent`, `merge`, atomic invocation, short callback và cấm recursive map update: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- `ConcurrentMap` (Java SE 26): contract interface, các default method có thể retry khi tranh chấp: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html
- `Map` (Java SE 26): ý nghĩa chung của compute/merge và null: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html
- `LongAdder` (Java SE 26): `increment`, `add`, `sum` và giới hạn snapshot: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `AtomicInteger` (Java SE 26): atomic counter và compareAndSet khi cần đồng bộ ở cấp value: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `CountDownLatch` / `Future` / `ExecutorService`: xây test đồng thời có chờ, thu lỗi và cleanup: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html
