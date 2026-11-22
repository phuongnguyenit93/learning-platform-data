# ConcurrentHashMap: chính sách null, computeIfAbsent() và giới hạn hàm ánh xạ

## 1. Bối cảnh: nhiều thread cùng truy cập một Map

`ConcurrentHashMap<K,V>` là một triển khai của `ConcurrentMap` trong `java.util.concurrent`, phù hợp khi nhiều thread cùng cần đọc và cập nhật ánh xạ key–value. Khác với `HashMap` thông thường, nó thiết kế các thao tác của mình để sử dụng đồng thời, không yêu cầu ứng dụng khóa toàn bộ map quanh mỗi lời gọi đơn lẻ.

Tuy nhiên, **thread-safe không có nghĩa mọi chuỗi thao tác của caller đều nguyên tử**. Hai câu hỏi đặc biệt quan trọng:

1. **Vì sao `ConcurrentHashMap` không cho phép key hoặc value là `null`?**
2. **`computeIfAbsent()` bảo đảm điều gì và tại sao hàm ánh xạ (*mapping function*) bị giới hạn?**

Đây là kiến thức Java concurrency nói chung trên **Java 17+**, không liên quan đến một framework cụ thể.

Ví dụ ban đầu:

```java
ConcurrentHashMap<String, String> map = new ConcurrentHashMap<>();
String value = map.computeIfAbsent("language", key -> "Java");
```

Đây là **snippet**, cần import `java.util.concurrent.ConcurrentHashMap`. Nếu key chưa tồn tại, hàm ánh xạ được sử dụng để tính giá trị. Map sẽ ghi giá trị không-null theo hợp đồng nguyên tử và trả về giá trị hiện có hoặc vừa tạo.

Điều không được suy ra: bất kỳ đoạn mã nào đặt trong lambda của `computeIfAbsent` cũng an toàn, mọi thao tác trên object được trả về đều thread-safe, hoặc việc khởi tạo giá trị đã tạo ra một transaction cho cả chương trình.

## 2. Chính sách null: cả key lẫn value đều bị cấm

`ConcurrentHashMap` **không cho phép `null` làm key và không cho phép `null` làm value**. Những API cần một key/value hợp lệ thường ném `NullPointerException` nếu được truyền null tại vị trí bị cấm.

Ví dụ:

```java
map.put(null, "value"); // NullPointerException.
map.put("key", null);   // NullPointerException.
map.get(null);          // NullPointerException.
```

Đây là snippet (giả sử `map` đã được khai báo); không chạy nối tiếp trong demo bình thường nếu không xử lý exception. `putIfAbsent`, `replace`, `merge`, `computeIfAbsent` và các API liên quan cũng có quy tắc kiểm tra key, value và function theo hợp đồng của từng phương thức.

### Vì sao thiết kế này có ý nghĩa trong concurrency?

Với map thông thường có thể lưu value null, một lời gọi `get(key) == null` có hai cách hiểu:

- Key **không có** trong map.
- Key có trong map nhưng value của nó là `null`.

Trong môi trường đồng thời, việc gọi thêm `containsKey(key)` **sau** `get(key)` để phân biệt cũng không tạo ra một snapshot nguyên tử: thread khác có thể thay map giữa hai lời gọi.

`ConcurrentHashMap` loại bỏ nhập nhằng này bằng cách **không bao giờ lưu ánh xạ key → null**. Bởi vậy khi `get(key)` trả null với key hợp lệ, tại thời điểm đọc không có mapping value hợp lệ cho key ấy. Nhưng **thread khác vẫn có thể thêm mapping ngay sau đó**: null không bảo đảm trạng thái vắng mặt sẽ tồn tại mãi.

Chính sách null cũng hữu ích trong các bulk operation, nơi giá trị null thường biểu thị “không có kết quả” cho một phép transform/filter theo hợp đồng của API.

### Ví dụ Java 17+ hoàn chỉnh: key/value null và kết quả null

Tạo file `ConcurrentHashMapNullDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentHashMapNullDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();

        try {
            map.put(null, "x");
        } catch (NullPointerException expected) {
            System.out.println("Null key rejected");
        }

        try {
            map.put("x", null);
        } catch (NullPointerException expected) {
            System.out.println("Null value rejected");
        }

        String calculated = map.computeIfAbsent(
                "missing", key -> null);

        System.out.println("Returned null: "
                + (calculated == null));
        System.out.println("Missing key stored: "
                + map.containsKey("missing"));

        ConcurrentHashMap<String, Optional<String>> negativeCache =
                new ConcurrentHashMap<>();
        negativeCache.computeIfAbsent(
                "absent-item", key -> Optional.empty());

        System.out.println("Negative result stored: "
                + negativeCache.containsKey("absent-item"));
    }
}
```

Biên dịch/chạy:

```bash
javac ConcurrentHashMapNullDemo.java
java ConcurrentHashMapNullDemo
```

Đầu ra xác định:

```text
Null key rejected
Null value rejected
Returned null: true
Missing key stored: false
Negative result stored: true
```

**Phân biệt rất quan trọng:**

- `map.put("x", null)` **ném NPE**: đây là yêu cầu ghi value null.
- `computeIfAbsent("missing", key -> null)` **không ném NPE chỉ vì kết quả lambda là null**. Nó trả null và **không ghi mapping**.
- Nếu muốn lưu trạng thái “đã tra cứu nhưng không tìm thấy”, có thể lưu một **value khác null** đại diện cho kết quả vắng mặt, như `Optional.empty()`. Đây gọi là *negative caching*; cần định nghĩa chính sách làm mới hoặc hết hạn để tránh cache kết quả âm quá lâu.

`Optional` chỉ là một cách biểu diễn, không bắt buộc. Trong API nghiệp vụ có nhiều trường hợp lỗi/không tìm thấy/đang chờ, một immutable result type rõ ràng có thể phù hợp hơn.

## 3. Tại sao `get` + `put` không thay được `computeIfAbsent`?

Giả sử hai thread cùng muốn khởi tạo một giá trị khi key chưa tồn tại.

Cách làm **không nguyên tử**:

```java
// Snippet KHÔNG an toàn để đảm bảo chỉ khởi tạo một lần.
String old = map.get("setting");
if (old == null) {
    String created = expensiveCreate();
    map.put("setting", created);
}
```

Đoạn trên giả sử `map` và `expensiveCreate()` đã được khai báo, không phải một chương trình độc lập.

Một interleaving có thể xảy ra:

```text
Thread A                         Thread B
--------                         --------
get("setting") -> null
                                 get("setting") -> null
expensiveCreate() -> "A"
                                 expensiveCreate() -> "B"
put("setting", "A")
                                 put("setting", "B")
```

Dù `ConcurrentHashMap.get` và `put` riêng lẻ đều được đồng bộ theo hợp đồng, **tổ hợp “kiểm tra vắng mặt → tạo → ghi” bị tách làm nhiều bước**. Hai thread có thể tạo trùng giá trị, thực thi side effect hai lần, thậm chí ghi đè kết quả nhau.

`putIfAbsent(key, value)` đảm bảo **thao tác ghi có điều kiện** là nguyên tử, nhưng nếu bạn **tính value trước khi gọi**, hai thread vẫn có thể thực hiện phép tính đắt đỏ:

```java
// Snippet: hai thread có thể cùng tính trước, dù chỉ một giá trị được ghi.
String computed = expensiveCreate();
map.putIfAbsent("setting", computed);
```

`computeIfAbsent(key, mappingFunction)` đưa phép **tính cho trường hợp vắng mặt** vào giao thức phối hợp của chính `ConcurrentHashMap`.

## 4. Hợp đồng của `ConcurrentHashMap.computeIfAbsent`

Chữ ký chính:

```java
V computeIfAbsent(
        K key,
        Function<? super K, ? extends V> mappingFunction)
```

Đây là chữ ký rút gọn; không phải file Java độc lập.

### Theo từng trường hợp

| Trạng thái key | Hành vi của `computeIfAbsent` | Kết quả |
| --- | --- | --- |
| Key đã gắn value không-null | Không chạy mapping function | Trả value đang có |
| Key vắng mặt, function trả value không-null | Ánh xạ key → value được thiết lập nguyên tử | Trả value đã thiết lập |
| Key vắng mặt, function trả `null` | Không thiết lập mapping | Trả `null` |
| Key vắng mặt, function ném unchecked exception hoặc `Error` | Không thiết lập mapping từ lần tính đó; exception truyền ra | Caller thấy lỗi |
| Key là `null` | Không hợp lệ | `NullPointerException` |
| Mapping function là `null` | Không hợp lệ | `NullPointerException` |
| Function cố cập nhật đệ quy vào map | Vi phạm hợp đồng | Có thể bị phát hiện và ném `IllegalStateException`; không được dựa vào khả năng phát hiện mọi trường hợp |

**Bảo đảm quan trọng trong JDK 17:** lời gọi `computeIfAbsent` của `ConcurrentHashMap` được thực hiện **nguyên tử** đối với mapping tương ứng. Theo hợp đồng, mapping function chỉ được gọi **một lần trong lần gọi cần tính** khi key đang vắng mặt; nếu key đã có thì không gọi.

Không được diễn giải thành “hàm này chỉ chạy đúng một lần trong **toàn bộ vòng đời ứng dụng**”. Nếu lần đầu trả null, ném lỗi, hoặc mapping sau đó bị xóa, lời gọi tương lai có thể phải tính lại. Với mỗi key, chỉ một mapping có thể được thiết lập ở một thời điểm theo giao thức của map; đó không phải guarantee *exactly-once* cho một side effect ngoài map trên toàn hệ thống.

**Lưu ý về lớp cụ thể:** `Map.computeIfAbsent` là một **default method** với những giới hạn bảo đảm tùy implementation. Không khái quát atomicity của `ConcurrentHashMap.computeIfAbsent` sang `HashMap` hay mọi triển khai `Map` khác. Khi viết code nhận `Map<K,V>` từ bên ngoài, phải xác định rõ loại map/hợp đồng concurrent thực tế.

## 5. Java 17+: nhiều thread khởi tạo cùng một key

Ta dùng một `CountDownLatch` để phát lệnh bắt đầu đồng thời cho tám thread, và `AtomicInteger` đếm số lần mapping function được thực sự gọi. Mỗi thread lấy value của cùng key.

Tạo file `AtomicMapInitialization.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicMapInitialization {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger creations = new AtomicInteger();
        AtomicInteger received = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[8];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                    String value = map.computeIfAbsent("topic", key -> {
                        creations.incrementAndGet();
                        return "Java";
                    });
                    if ("Java".equals(value)) {
                        received.incrementAndGet();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Received: " + received.get());
        System.out.println("Mapping calls: " + creations.get());
        System.out.println("Entries: " + map.size());
        System.out.println("Stored: " + map.get("topic"));
    }
}
```

Chạy:

```bash
javac AtomicMapInitialization.java
java AtomicMapInitialization
```

Đầu ra khi không có interrupt từ bên ngoài:

```text
Received: 8
Mapping calls: 1
Entries: 1
Stored: Java
```

**Tại sao kết quả không phụ thuộc scheduling?**

1. Không có code xóa hoặc thay mapping của key `topic`.
2. Function luôn trả một chuỗi không-null, nên mapping được thiết lập thành công.
3. Trong tình huống nhiều thread cạnh tranh cùng key, `ConcurrentHashMap` điều phối `computeIfAbsent` để mapping function không bị chạy đồng thời nhiều lần cho **chính ánh xạ đang được tạo**. Sau khi mapping tồn tại, các lời gọi sau chỉ trả value.
4. Tám thread đều nhận value `Java`. `AtomicInteger` bảo đảm việc đếm số lần gọi và số lượt nhận không bị lost update.
5. `join()` của main chờ tất cả worker hoàn tất trước khi in.

**Cảnh báo về side effect:** ví dụ dùng `creations.incrementAndGet()` để **đo việc gọi hàm**. Không suy rằng đưa một thao tác ghi cơ sở dữ liệu hoặc gửi email vào mapping function sẽ trở thành exactly-once toàn hệ thống; nếu mapping không được thiết lập thành công hoặc bị xóa về sau, các lần gọi khác có thể lặp lại side effect.

## 6. Giới hạn quan trọng: mapping function phải ngắn, đơn giản, không sửa chính map

Javadoc của `ConcurrentHashMap.computeIfAbsent` nêu rõ: **toàn bộ invocation nguyên tử**, và **một số update operation từ thread khác có thể bị chặn trong khi hàm tính đang chạy**. Vì vậy mapping function nên **ngắn và đơn giản**.

Đặc biệt, **mapping function không được sửa map đang được compute trong quá trình tính**. Đây không chỉ là lời khuyên tối ưu hiệu năng; đó là ràng buộc hợp đồng API.

### Những việc không nên làm bên trong lambda

- Gọi `map.put(...)`, `remove(...)`, `compute(...)` hoặc `computeIfAbsent(...)` trên **cùng map**, dù key khác.
- Đệ quy yêu cầu tạo **cùng key** đang được compute.
- Gọi callback không kiểm soát mà callback có thể sửa cùng map.
- Đợi task ở một executor mà task đó lại cần cập nhật hoặc compute cùng map.
- Thực hiện I/O lâu, gọi HTTP, chờ database, sleep dài hoặc khóa một resource không bảo đảm tiến triển.
- Tạo nhiều object rất nặng hoặc làm logic nghiệp vụ lâu ngay dưới cơ chế mapping.

Ví dụ **sai**:

```java
// Snippet CẤM thực hiện trong cùng ConcurrentHashMap.
// map đã khai báo, đoạn này không dùng làm demo chạy.
map.computeIfAbsent("a", key -> {
    map.put("b", "side-effect");
    return "value-a";
});
```

Đoạn trên vi phạm hợp đồng **không sửa chính map trong lúc tính**. Tùy key, trạng thái bảng, implementation và đường tranh chấp, có thể bị chặn, gặp lỗi hoặc hành vi không mong muốn. **Không** thiết kế dựa vào việc “chạy thử thấy vẫn được”.

### Đệ quy cùng key

```java
// Snippet NGUY HIỂM: có thể ném IllegalStateException.
map.computeIfAbsent("a", key ->
        map.computeIfAbsent("a", nested -> "nested"));
```

Javadoc quy định có thể ném `IllegalStateException` nếu phát hiện được một recursive update khiến computation không thể kết thúc. Không dùng exception này như cách điều khiển luồng bình thường; sửa thiết kế để việc khởi tạo không đệ quy cập nhật cùng map.

### Vì sao hàm chậm ảnh hưởng thread khác?

Map cần bảo vệ tính nguyên tử của việc cài mapping. Khi function đang tính value, các update khác có thể phải chờ một số vùng/trường hợp tranh chấp. Điều này **không** đồng nghĩa toàn map bị khóa một monitor toàn cục cho mọi hoạt động: nhiều thao tác đọc và cập nhật ở các phần độc lập có thể vẫn tiến triển. Nhưng không có cam kết hàm chậm chỉ làm chậm đúng một key.

**Quy tắc an toàn:** dùng lambda như một bước **tạo value cục bộ nhanh, không side effect lên cùng map**. Nếu cần tải dữ liệu nặng, nên cân nhắc lưu một **đối tượng đại diện cho công việc** rồi cho công việc chạy **ngoài mapping function**, hoặc dùng một executor/cache được thiết kế cho tải bất đồng bộ.

## 7. Khi computeIfAbsent trả null hoặc ném lỗi: có thể tính lại lần sau

Một kết quả null không thể được đưa vào `ConcurrentHashMap` vì value null bị cấm. Tương tự, khi mapping function ném một exception, lần tính không ghi mapping của key.

Tạo file `MappingFailureDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class MappingFailureDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger calls = new AtomicInteger();

        try {
            map.computeIfAbsent("item", key -> {
                calls.incrementAndGet();
                throw new IllegalStateException("cannot initialize");
            });
        } catch (IllegalStateException expected) {
            System.out.println("First computation failed");
        }

        System.out.println("Absent after exception: "
                + !map.containsKey("item"));

        String value = map.computeIfAbsent("item", key -> {
            calls.incrementAndGet();
            return "recovered";
        });

        System.out.println("Recovered: " + value);
        System.out.println("Mapping calls: " + calls.get());

        String missing = map.computeIfAbsent("nil", key -> null);
        System.out.println("Null result: " + (missing == null));
        System.out.println("Nil stored: " + map.containsKey("nil"));
    }
}
```

Biên dịch/chạy:

```bash
javac MappingFailureDemo.java
java MappingFailureDemo
```

Đầu ra:

```text
First computation failed
Absent after exception: true
Recovered: recovered
Mapping calls: 2
Null result: true
Nil stored: false
```

Lần đầu function ném lỗi và key không được ghi. Lần sau key vẫn vắng mặt nên function chạy **lại**, lần này trả value. Trường hợp `nil` trả null cũng không lập mapping.

**Đây là điểm phá vỡ cách nghĩ “computeIfAbsent đảm bảo chỉ tính một lần mãi mãi”**. Nó chỉ phối hợp việc tính/ghi khi cần theo hợp đồng của map và **lần invocation**. Nếu nghiệp vụ cần khởi tạo đúng một lần bất kể process restart hay lỗi, phải có giao thức idempotency hoặc transaction ở nguồn chân lý tương ứng.

## 8. Ví dụ phổ biến: frequency map bằng `LongAdder`

Javadoc của `ConcurrentHashMap` có cách dùng rất hữu ích: map từ key sang bộ đếm. Với nhiều thread, tạo `LongAdder` cho key vắng mặt và tăng chính bộ đếm đó.

```java
frequencies.computeIfAbsent(key, k -> new LongAdder())
           .increment();
```

Đây là snippet; `frequencies`, `key` và import `LongAdder` chưa khai báo ở đây. Điểm hay là:

- `computeIfAbsent` chỉ chịu trách nhiệm **đặt một LongAdder dùng chung** cho key khi chưa có.
- `LongAdder.increment()` thực hiện cập nhật an toàn với nhiều thread vào **chính object LongAdder**.
- Không cần đưa `increment()` vào bên trong mapping function, vì điều đó khiến việc **đếm mỗi sự kiện** phụ thuộc vào key có vắng mặt hay không. Nếu key đã có sẵn, mapping function **không chạy** và sự kiện sẽ không được đếm.
- Không dùng `Integer` thường rồi `get()+1`/`put()`; giá trị immutable Integer không biến cặp read–modify–write thành atomic.

### Java 17+: bốn worker cùng tăng bộ đếm

Tạo file `ConcurrentFrequencyDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentFrequencyDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> frequencies =
                new ConcurrentHashMap<>();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    frequencies.computeIfAbsent(
                            "java", key -> new LongAdder())
                            .increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Keys: " + frequencies.size());
        System.out.println("Java count: "
                + frequencies.get("java").sum());
    }
}
```

Chạy:

```bash
javac ConcurrentFrequencyDemo.java
java ConcurrentFrequencyDemo
```

Đầu ra:

```text
Keys: 1
Java count: 4000
```

Mọi worker tăng **cùng một LongAdder** gắn với key `java`. Khi main đã `join()` đủ bốn worker, tổng cuối là 4.000. Trong lúc nhiều thread còn đang cập nhật, `LongAdder.sum()` **không phải một snapshot nguyên tử tuyệt đối**; nó thích hợp cho thống kê/đếm khi contention cao nhưng không nên dùng làm điều kiện kiểm tra chính xác cho transaction nghiệp vụ.

### Cạm bẫy khi remove/replace counter

Nếu một thread gọi `frequencies.remove("java")` trong lúc thread khác đã lấy `LongAdder` cũ rồi tiếp tục `increment()`, lượt tăng có thể xảy ra trên **object đã bị gỡ khỏi map**. Map bảo đảm thao tác thiết lập/lấy mapping riêng lẻ, không tự “khóa sống” object được trả về cho toàn bộ quá trình dùng tiếp.

Nếu cần mọi increment được tính chính xác xuyên qua việc reset/rotate counter, phải thiết kế giao thức reset riêng. Đừng đồng thời xóa/thay `LongAdder` trong map rồi suy rằng mọi thread đã chuyển sang bộ đếm mới.

## 9. Atomic mapping không có nghĩa value được thread-safe

`ConcurrentHashMap<K,V>` bảo vệ **cấu trúc ánh xạ key → value**, nhưng không tự bảo vệ **trạng thái mutable bên trong V**.

Ví dụ nguy hiểm:

```java
// Snippet: list là ArrayList mutable không có synchronization riêng.
ConcurrentHashMap<String, java.util.ArrayList<String>> map =
        new ConcurrentHashMap<>();

java.util.ArrayList<String> list = map.computeIfAbsent(
        "users", key -> new java.util.ArrayList<>());

// Nhiều thread cùng gọi list.add(...) là KHÔNG an toàn.
list.add("user-1");
```

`computeIfAbsent` có thể tạo và công bố **một List object dùng chung**, nhưng `ArrayList.add` không trở nên thread-safe chỉ vì List nằm trong `ConcurrentHashMap`.

Lựa chọn tùy yêu cầu:

- Value là **immutable object** khi đọc nhiều và thay nguyên value bằng `compute`/`replace`/CAS-map operation.
- Value là **atomic/concurrent structure** như `LongAdder`, `ConcurrentLinkedQueue` hoặc `CopyOnWriteArrayList` nếu hành vi của nó thực sự phù hợp.
- Dùng khóa riêng hoặc đóng gói state trong một class có policy đồng bộ rõ.
- Nếu cần atomicity của **nhiều key cùng lúc**, cơ chế riêng lẻ của `computeIfAbsent` **không tạo một transaction đa key**.

Ngay cả với một value immutable, quy tắc lấy tham chiếu rồi cập nhật map cũng cần xử lý trường hợp mapping bị thay giữa hai bước nếu đó là điều kiện nghiệp vụ.

## 10. Không nên đưa I/O và expensive computation trực tiếp vào mapping function

Một pattern ban đầu trông đơn giản:

```java
// Snippet KHÔNG KHUYẾN NGHỊ nếu loadFromRemote() có thể chờ lâu.
Result result = map.computeIfAbsent(
        key, k -> loadFromRemote(k));
```

`Result`, `map`, `key` và `loadFromRemote` chưa khai báo trong snippet này. Vấn đề:

1. Mapping function có thể chạy lâu hoặc chờ I/O không có timeout.
2. Một số update của thread khác trên map có thể bị chặn trong giai đoạn compute.
3. Nếu I/O cần một callback cập nhật cùng map, có thể xuất hiện deadlock/recursive update.
4. Khi function trả null, không cache được kết quả âm; những lời gọi sau lặp lại load.
5. Khi function ném lỗi, không cache được failure; các yêu cầu kế tiếp có thể gây **retry storm**.
6. Một side effect bên ngoài không được rollback nếu sau đó mapping thất bại.

Khi giá trị cần khởi tạo nặng, có thể dùng **placeholder** đại diện cho một phép tính, cài placeholder nhanh vào map rồi thực hiện công việc thật ở bên ngoài vùng mapping function. Cách này vẫn cần chính sách timeout, cancellation, lỗi và eviction.

### Java 17+: memoization bằng `FutureTask` được cài nhanh

Tạo file `ConcurrentMemoDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentMemoDemo {
    private final ConcurrentHashMap<String, FutureTask<String>> cache =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public String load(String key)
            throws InterruptedException, ExecutionException {
        FutureTask<String> task = cache.computeIfAbsent(
                key,
                k -> new FutureTask<>(() -> {
                    loads.incrementAndGet();
                    return k.toUpperCase(Locale.ROOT);
                })
        );

        // Chạy bên ngoài mapping function: run() chỉ thực thi
        // callable một lần dù nhiều thread cùng gọi.
        task.run();

        try {
            return task.get();
        } catch (ExecutionException e) {
            cache.remove(key, task); // Gỡ đúng instance thất bại.
            throw e;
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentMemoDemo memo = new ConcurrentMemoDemo();
        ExecutorService executor = Executors.newFixedThreadPool(6);
        try {
            List<Callable<String>> calls = new ArrayList<>();
            for (int i = 0; i < 6; i++) {
                calls.add(() -> memo.load("java"));
            }

            List<Future<String>> results = executor.invokeAll(calls);
            boolean allMatch = true;
            for (Future<String> result : results) {
                allMatch &= "JAVA".equals(result.get());
            }

            System.out.println("All equal: " + allMatch);
            System.out.println("Load calls: " + memo.loads.get());
            System.out.println("Cache entries: " + memo.cache.size());
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ConcurrentMemoDemo.java
java ConcurrentMemoDemo
```

Đầu ra khi không có interrupt từ bên ngoài:

```text
All equal: true
Load calls: 1
Cache entries: 1
```

**Giải thích:**

1. `computeIfAbsent` **chỉ tạo `FutureTask`**, một object nhỏ đại diện cho lần tính, và nhanh chóng cài vào map.
2. Hàm tính thật `k.toUpperCase(...)` và bộ đếm `loads` nằm **bên trong Callable của `FutureTask`**, được chạy bởi `task.run()` **sau khi `computeIfAbsent` đã trả về**.
3. Nếu nhiều caller cùng lấy một key, họ cùng nhận một `FutureTask`. `FutureTask.run()` được thiết kế để callable bên trong chỉ chạy **một lần** cho một instance task; các caller khác có thể `get()` chờ kết quả.
4. `FutureTask.get()` công bố kết quả hoặc ném `ExecutionException`. Nếu task thất bại, mã dùng `cache.remove(key, task)` để chỉ gỡ mapping **nếu nó vẫn đang trỏ đến đúng task này**, giúp lần gọi sau có thể thử lại.
5. Không cần suy đoán lịch của sáu worker: kết quả của tác vụ là `JAVA` và `FutureTask` duy nhất cho key giữ số lượt chạy là 1.

**Giới hạn của ví dụ:** việc `task.run()` diễn ra **trên thread caller** nào đó; nó có thể chặn caller nếu load nặng. Nếu muốn chạy trên executor riêng, phải thiết kế cơ chế **chỉ submit một lần**, không tự động gọi `executor.submit(task)` từ mọi caller sau `computeIfAbsent` vì như vậy có thể lặp việc submit không cần thiết. Cũng phải quan tâm timeout, hủy nhiệm vụ, retry sau lỗi và giới hạn số task cache.

Trong hệ thống production, một cache library có loader, expiry, size limit và quan sát thống kê thường dễ bảo trì hơn một thuật toán memoization tự viết. Đừng biến ví dụ `FutureTask` thành cache vô hạn mà không có eviction hoặc chính sách lỗi.

## 11. Đặt `computeIfAbsent()` cạnh các API remapping khác

Bài này đi sâu vào **null policy và mapping function**. Các API khác chỉ cần đối chiếu theo trạng thái mapping:

| API | Khi nào áp dụng hàm | Khi hàm trả null |
| --- | --- | --- |
| `computeIfAbsent(k, fn)` | Khi key vắng; hàm nhận key | Không thêm mapping |
| `computeIfPresent(k, fn)` | Khi key hiện diện; hàm nhận key và value cũ | Xóa mapping |
| `compute(k, fn)` | Khi key có hoặc không; value cũ có thể null | Không thêm hoặc xóa mapping |
| `merge(k, v, fn)` | Nếu absent gắn v; nếu present gọi fn(old, v) | Xóa mapping |

Các method có contract atomic theo mapping liên quan nhưng không bảo vệ side effect khác; callback không nên sửa chính map trong lúc remapping. Cách chọn `compute` và `merge` cho cập nhật thông dụng đã được triển khai, kiểm chứng ở bài API trước đó.

## 12. Tính nguyên tử theo key, không phải snapshot toàn map

ConcurrentHashMap hỗ trợ concurrency cao nhưng không cam kết mọi phép kiểm tra gồm **nhiều key** đều là một transaction:

```java
// Snippet, KHÔNG tạo transaction giữa hai key.
map.computeIfAbsent("left", key -> "L");
map.computeIfAbsent("right", key -> "R");
```

Thread khác có thể quan sát thấy `left` đã được thiết lập trong khi `right` chưa được thiết lập. Nếu invariant của ứng dụng là “cả hai mapping cùng thay đổi hoặc không mapping nào thay đổi”, cần thiết kế khác: một immutable aggregate value dưới **một key**, một lock ngoài, hoặc cơ chế transaction ở tầng dữ liệu phù hợp.

### Map views và iteration

`keySet()`, `values()`, `entrySet()` của `ConcurrentHashMap` cung cấp các view có thể dùng khi cập nhật đồng thời; iterator có tính **weakly consistent**: nó không ném `ConcurrentModificationException` chỉ vì những cập nhật thông thường đồng thời, nhưng **không** bảo đảm một snapshot tĩnh toàn map.

Các câu như “lặp ra tất cả key chính xác tại một thời điểm duy nhất” không nên dựa vào iterator của `ConcurrentHashMap` trong khi writer đang cập nhật. Nếu cần snapshot nhất quán theo nghiệp vụ, phải tạm dừng writer theo giao thức của ứng dụng, dùng immutable snapshot hoặc lựa chọn thiết kế thích hợp.

`size()` và `mappingCount()` khi map đang bị sửa đồng thời mang ý nghĩa đo trạng thái **có thể thay đổi/ước lượng**, không phải phép đồng bộ xác định số task có thể được nhận. `mappingCount()` trả `long` để biểu diễn số lượng ánh xạ lớn hơn phạm vi `int` và cũng được xem là estimate dưới concurrent updates.

## 13. Visibility, publication và sự an toàn của object được trả về

ConcurrentHashMap cung cấp quan hệ memory-consistency cho các thao tác truy cập ánh xạ: một phép cập nhật thành công cho key có thể được quan sát qua một phép đọc thấy value đó với những bảo đảm đồng bộ tương ứng.

Tuy nhiên:

- Map bảo vệ **cách công bố reference** cho một value; nó không ngăn một thread khác **sửa field mutable của object ấy** sau khi reference được công bố.
- Nếu value có nhiều field liên quan, invariant trong object cần được giữ bằng immutable design, lock hoặc atomic state riêng.
- Dùng `final` trong một immutable value type/record giúp thiết kế dễ suy luận, nhưng **record chứa một `List` mutable vẫn có thể bị sửa bên ngoài** nếu không defensive copy.
- Một thread có thể gọi `get(k)`, nhận value cũ, rồi thread khác gọi `replace(k, newValue)`. Việc thread đầu tiếp tục sử dụng value cũ không đồng nghĩa map đã giữ snapshot toàn cục.
- Với `computeIfAbsent`, giá trị do lambda tạo ra nên được **khởi tạo đầy đủ trước khi trả về**; không để object bị rò rỉ từ constructor hoặc callback khi state chưa hoàn chỉnh.

### Mutable value vs immutable snapshot

Ví dụ cho mapping một giá trị bất biến:

```java
// Snippet Java 17+: record Position(int x, int y) {} đã khai báo.
ConcurrentHashMap<String, Position> positions =
        new ConcurrentHashMap<>();
positions.compute("current",
        (key, oldValue) -> new Position(10, 20));
```

Không phải file độc lập vì `Position` chưa khai báo. Khi đã có mapping, reader có thể lấy object `Position` chứa hai primitive final đã được tạo xong; nếu writer muốn đổi cả hai cùng lúc, nó có thể thay **một reference value** qua `compute` hoặc `replace`, thay vì sửa hai trường mutable riêng lẻ ngoài khóa.

**Không được suy ra** update nhiều key trở thành nguyên tử chỉ vì từng value là record; ranh giới atomic của map vẫn là mapping riêng.

## 14. Một số sai lầm thường gặp

1. **“ConcurrentHashMap cũng cho phép null như HashMap.”** Sai: cấm cả key null và value null.
2. **“`computeIfAbsent(k, f)` trả null nghĩa map đã lưu null.”** Sai: không thiết lập mapping.
3. **“`get(k) == null` bảo đảm key không xuất hiện ở thời điểm sau đó.”** Sai: thread khác có thể cập nhật ngay.
4. **“`get` rồi `put` là một bước atomic vì map concurrent.”** Sai: đây là check–then–act gồm hai lời gọi.
5. **“`putIfAbsent` giúp tránh tính hai giá trị đắt đỏ từ trước.”** Không nhất thiết: nếu cả hai caller tính giá trị **trước** putIfAbsent thì vẫn tính hai lần.
6. **“Mapping function chỉ chạy đúng một lần cho key trong suốt vòng đời process.”** Sai nếu mapping bị xóa, function trả null hoặc ném lỗi.
7. **“Lambda có thể thoải mái gọi `put` cho key khác của cùng map.”** Sai: mapping function không được sửa map đang tính.
8. **“Đệ quy cùng key có thể dùng để khởi tạo phụ thuộc.”** Sai: có thể ném `IllegalStateException` hoặc làm thuật toán không tiến triển.
9. **“Đưa HTTP/DB vào computeIfAbsent là mặc nhiên an toàn và tối ưu.”** Sai: function dài có thể cản trở update khác, gây contention và retry/timeout phức tạp.
10. **“Value trả về đã tự thread-safe.”** Sai: `ArrayList`, `HashMap` và mutable object vẫn cần bảo vệ.
11. **“Đặt `LongAdder.increment()` trong lambda là đếm mọi lần gọi.”** Sai: lambda không chạy khi key đã hiện diện.
12. **“`LongAdder.sum()` luôn là snapshot nguyên tử giữa concurrent updates.”** Sai: không nhất thiết.
13. **“`computeIfAbsent` có thể transactionally cập nhật nhiều key.”** Sai: atomicity chỉ áp dụng ở ranh giới của phép update tương ứng.
14. **“Iteration trên ConcurrentHashMap luôn là snapshot cố định.”** Sai: weakly consistent, có thể phản ánh cập nhật đồng thời.
15. **“ConcurrentHashMap.size()` là cách chặn nhận thêm task chính xác tuyệt đối.”** Sai: kích thước quan sát không phải phép admission atomic.
16. **“Dùng `Optional.empty()` nghĩa cache tự có TTL.”** Sai: đó chỉ là một value đại diện; expiry/eviction phải thiết kế riêng.
17. **“Một FutureTask trong map bảo đảm mọi side effect ngoài process exactly once.”** Sai: FutureTask điều phối một instance task trong JVM; lỗi/restart/retry cần giao thức khác.

## 15. Checklist trước khi triển khai

1. **Xác định null có ý nghĩa gì.** Nếu cần negative caching, dùng value đại diện không-null; không gọi `put(k,null)`.
2. **Chọn ranh giới atomic đúng.** Khởi tạo giá trị một key dùng `computeIfAbsent`; tăng counter dùng `merge` hoặc `LongAdder`; invariant đa key cần thiết kế khác.
3. **Đừng tách check–then–act.** Không viết `if (get == null) put(...)` rồi mong chỉ một thread khởi tạo.
4. **Mapping function nên ngắn, đơn giản, thuần về map.** Không sửa cùng map, không đệ quy cập nhật, tránh I/O/lock/callback chờ lâu.
5. **Phân biệt trả null và ném exception.** Cả hai để key vắng mặt nếu trước đó chưa có mapping; lời gọi sau có thể tính lại.
6. **Kiểm tra side effect.** Việc tính lại sau thất bại/removal có thể lặp thao tác bên ngoài; cần idempotency khi nghiệp vụ yêu cầu.
7. **Value có tự thread-safe không?** Dùng atomic/concurrent value hoặc immutable snapshot nếu nhiều thread tiếp tục sửa/đọc.
8. **Không xóa counter đang được dùng rồi cho rằng mọi update sẽ chuyển sang counter mới.** Có thể cần reset protocol.
9. **Khi work nặng, cân nhắc placeholder.** Cài `FutureTask`/future nhanh rồi tính ngoài mapping function; xử lý exception, timeout và eviction.
10. **Không phụ thuộc thứ tự iterator khi cần snapshot toàn map.** Dùng thiết kế snapshot riêng.
11. **Theo dõi contention và giá trị thực tế.** Đo mapping latency, tỷ lệ failure/retry, số key, memory và cache hit.
12. **Kiểm tra JVM/API mục tiêu.** Các ví dụ ở đây chạy với Java 17+; tham khảo Javadoc theo đúng JDK triển khai.
13. **Thử concurrency theo lịch đa dạng.** Dùng latch để phối hợp test, không dùng `sleep` làm bằng chứng không có data race.
14. **Dọn dẹp đúng vòng đời.** Pool và cache phải có owner; tránh giữ bản ghi lỗi hoặc giá trị không còn hợp lệ vô hạn.

## 16. Tài liệu chính thức

- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [ConcurrentMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)
- [Map.computeIfAbsent — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [LongAdder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)

**Tóm lại:** `ConcurrentHashMap` cấm key/value null để việc truy cập đồng thời có một tín hiệu vắng mặt không nhập nhằng. `computeIfAbsent` giúp thiết lập mapping **nguyên tử** khi key chưa có, nhưng function có thể không ghi mapping khi trả null hoặc ném lỗi, và **không được sửa chính map trong lúc tính**. Giữ mapping function nhanh, dùng loại value có giao thức thread safety rõ ràng, tránh đẩy I/O dài vào computation, và không xem atomicity của một key là transaction cho nhiều key hoặc nhiều side effect.