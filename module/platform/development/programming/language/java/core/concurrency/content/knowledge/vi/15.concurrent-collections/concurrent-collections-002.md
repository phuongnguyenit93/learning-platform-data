# ConcurrentHashMap: `putIfAbsent()`, `compute()` và `merge()` trong Java

## 1. Vấn đề: một Map được nhiều thread cập nhật

Trong Java concurrency, `Map<K,V>` thường dùng để lưu cấu hình theo key, số lần truy cập, trạng thái phiên làm việc, cache hoặc các phép tổng hợp. Khi nhiều thread cùng truy cập, cần phân biệt hai yêu cầu:

1. **Cấu trúc Map an toàn:** các thao tác không làm hỏng cấu trúc dữ liệu nội bộ khi nhiều thread đọc/ghi.
2. **Một thay đổi nghiệp vụ nguyên tử:** phép “kiểm tra → tính toán → cập nhật” phải không bị thread khác chen vào làm mất cập nhật hoặc phá điều kiện.

Một `HashMap` thông thường **không thread-safe** khi nhiều thread cùng sửa. Chỉ đổi thành `ConcurrentHashMap` giúp các thao tác của Map có cơ chế đồng thời phù hợp; tuy nhiên không có nghĩa **mọi chuỗi lệnh ứng dụng** trên Map đều trở thành một transaction.

Ví dụ phản diện:

```java
Integer old = counts.get("java");
counts.put("java", old == null ? 1 : old + 1);
```

Đây là đoạn minh họa, `counts` được nhiều thread dùng chung. Hai worker có thể cùng đọc `5`, đều tính `6` và ghi `6`. Kết quả mất một lần tăng (**lost update**) ngay cả khi `counts` là `ConcurrentHashMap`.

Giải pháp là dùng những thao tác **nguyên tử theo key**, như:

- `putIfAbsent(key, value)`: chỉ thêm khi key chưa có ánh xạ.
- `compute(key, remappingFunction)`: tính lại và cập nhật/xóa giá trị theo **giá trị hiện tại** của key.
- `merge(key, value, remappingFunction)`: thêm giá trị ban đầu nếu key vắng mặt; nếu đã có thì kết hợp với giá trị cũ.

Đây là bài học thuộc mục **Concurrent Collections** trong Java concurrency nói chung, không cần bất kỳ framework nào.

## 2. Vì sao `get()` rồi `put()` không đủ?

Giả sử ban đầu `counts["A"] == 10`:

```text
Thread 1                         Thread 2
--------                         --------
get("A") -> 10
                                 get("A") -> 10
tính 11
                                 tính 11
put("A", 11)
                                 put("A", 11)

Kết quả: 11, mặc dù có hai yêu cầu tăng.
```

`ConcurrentHashMap.get` và `put` riêng lẻ đều được thiết kế cho truy cập đồng thời, nhưng **khoảng giữa chúng không được khóa như một giao dịch nghiệp vụ**.

Vấn đề tương tự xuất hiện khi viết:

```java
if (!map.containsKey(key)) {
    map.put(key, candidate);
}
```

Hai thread có thể cùng thấy key vắng mặt rồi lần lượt `put` hai ứng viên khác nhau. Thread ghi sau ghi đè thread trước; cả hai caller có thể tưởng rằng mình là người khởi tạo.

Không nên tự sửa bằng một cờ `boolean initialized` hay `volatile` rời rạc nếu vẫn thiếu một thao tác nguyên tử gộp kiểm tra với thay đổi. Với `ConcurrentHashMap`, hãy dùng API đúng **ngữ nghĩa của nghiệp vụ**.

## 3. Ba API nhìn cạnh nhau

| API | Khi key vắng mặt | Khi key đã có giá trị | Giá trị trả về | Khi muốn xóa |
| --- | --- | --- | --- | --- |
| `putIfAbsent(k, v)` | Gắn `v` mới | Giữ nguyên giá trị cũ | Giá trị cũ nếu có; `null` nếu thêm thành công | API này không xóa |
| `compute(k, f)` | Gọi `f(k, null)` | Gọi `f(k, oldValue)` | Giá trị mới hoặc `null` | `f` trả `null` |
| `merge(k, v, f)` | Gắn `v` mà **không gọi `f`** | Gọi `f(oldValue, v)` | Giá trị sau khi hợp nhất hoặc `null` | `f` trả `null` |

Ba API có những hợp đồng khác nhau. Chọn dựa trên ý nghĩa nghiệp vụ, không chỉ vì chúng đều nghe như “cập nhật Map”.

**Điểm bắt buộc:** `ConcurrentHashMap` **không cho phép key hoặc value là `null`**. Gọi `putIfAbsent(null, ...)`, `putIfAbsent(key, null)` hay `merge(key, null, ...)` đều không hợp lệ. Trong `compute`, `null` được dùng làm **tín hiệu vắng mặt/xóa mapping**, không phải giá trị `null` được lưu trong Map.

Trong bài này, mọi ví dụ dùng JDK 17 trở lên và kiểu `ConcurrentHashMap` trực tiếp để dựa trên hợp đồng mạnh của implementation này. Không suy diễn rằng mọi implementation `ConcurrentMap` khác có cùng cách thực thi hàm callback.

## 4. `putIfAbsent()`: chỉ một caller cài đặt khi key chưa tồn tại

Chữ ký:

```java
V putIfAbsent(K key, V value);
```

Ngữ nghĩa:

- Nếu key chưa có mapping, gắn `value` và trả `null`.
- Nếu key đã có mapping, **không thay thế**, trả giá trị đang có.
- Toàn thao tác “kiểm tra key vắng mặt + ghi giá trị” diễn ra **nguyên tử** cho key đó.
- Do `ConcurrentHashMap` cấm value `null`, giá trị trả về `null` biểu thị **không có giá trị cũ** và lời gọi đã cài mapping do nó cung cấp.

Một use case: đăng ký ID duy nhất, cài config mặc định, khởi tạo một đối tượng có thể dùng lại hoặc chọn người thắng trong cuộc tranh chấp khởi tạo.

### Ví dụ 1: quan sát kết quả trả về

Tạo tệp `PutIfAbsentBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class PutIfAbsentBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> services =
                new ConcurrentHashMap<>();

        String first = services.putIfAbsent("search", "node-A");
        String second = services.putIfAbsent("search", "node-B");

        System.out.println("first previous=" + first);
        System.out.println("second previous=" + second);
        System.out.println("current=" + services.get("search"));
        System.out.println("size=" + services.size());
    }
}
```

Chạy:

```bash
javac PutIfAbsentBasicsDemo.java
java PutIfAbsentBasicsDemo
```

Kết quả:

```text
first previous=null
second previous=node-A
current=node-A
size=1
```

Giải thích:

- Lần đầu key `"search"` chưa có, ghi `"node-A"` và trả `null`.
- Lần hai key đã tồn tại, `"node-B"` **không** được gắn; trả về `"node-A"`.
- Map có đúng một key.

### Khi nào `putIfAbsent` chưa đủ?

Nếu mục đích là **cộng thêm 1 vào giá trị đang có**, `putIfAbsent(key, 1)` chỉ có tác dụng ở lần đầu. Những lần sau giá trị bị giữ nguyên, **không tăng**.

Nếu muốn “khởi tạo nếu vắng mặt, còn đã có thì sử dụng đối tượng cũ”, `putIfAbsent` phù hợp; nếu việc tạo candidate rất tốn kém, nên cân nhắc `computeIfAbsent` để tránh dựng một candidate mới trong mọi lần gọi khi key đã tồn tại.

Chú ý: `putIfAbsent` nhận **value đã được tính từ trước**, nghĩa là hai thread có thể **đều tốn chi phí tạo candidate** trước khi một thread thắng. API chỉ đảm bảo một mapping được cài, không đảm bảo chỉ một constructor/call bên ngoài từng được thực hiện.

## 5. `putIfAbsent` khi hai thread tranh cùng key

Giả sử hai worker cùng muốn cài key `"leader"`. Không thể dự đoán **thread tên gì thắng** vì scheduler quyết định thứ tự. Nhưng có thể kiểm chứng chắc chắn rằng **chỉ một lời gọi** báo thành công.

Tạo tệp `PutIfAbsentRaceDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class PutIfAbsentRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger installed = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                if (map.putIfAbsent("leader", "ready") == null) {
                    installed.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(job, "candidate-A");
        Thread b = new Thread(job, "candidate-B");

        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("installed=" + installed.get());
        System.out.println("value=" + map.get("leader"));
        System.out.println("size=" + map.size());
    }
}
```

```bash
javac PutIfAbsentRaceDemo.java
java PutIfAbsentRaceDemo
```

Output khi worker không bị interrupt ngoài ý muốn:

```text
installed=1
value=ready
size=1
```

Dù cả hai thread có thể thử cùng lúc, tại key `leader`, chỉ một phép cài mapping từ trạng thái vắng mặt thành `"ready"` thành công. Không cần dự đoán ai thắng vì hai ứng viên cài cùng giá trị để output ổn định.

**Không đồng nhất “một caller cài mapping” với “một tác vụ nghiệp vụ đã chạy duy nhất”.** Nếu hai thread gọi API ngoài, tạo file, gửi email hay ghi database **trước** khi `putIfAbsent`, side effect đã có thể xảy ra hai lần. Hãy thực hiện side effect dựa trên kết quả thắng/thua hoặc một giao thức idempotency phù hợp.

## 6. `compute()`: đọc giá trị hiện tại và quyết định mapping mới

Chữ ký:

```java
V compute(
        K key,
        BiFunction<? super K, ? super V, ? extends V> remappingFunction);
```

Hàm callback nhận:

1. `key` đang được cập nhật.
2. `oldValue` hiện tại; với `ConcurrentHashMap`, `oldValue == null` biểu thị **key vắng mặt**.

Callback trả:

- Giá trị `newValue != null`: cài hoặc thay mapping.
- `null`: không giữ mapping cho key (nếu đang tồn tại thì **xóa**; nếu chưa có thì vẫn vắng mặt).

Với `ConcurrentHashMap.compute`, toàn bộ thao tác của **một key** được thực hiện nguyên tử theo hợp đồng; callback được gọi một lần trong mỗi lời gọi method này. Các cập nhật khác trong Map có thể bị chặn trong khi callback đang chạy, vì vậy callback phải **ngắn và đơn giản**.

### Ví dụ 2: cài, cập nhật và xóa bằng compute

Tạo tệp `ComputeBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ComputeBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        Integer first = map.compute("quota",
                (key, oldValue) ->
                        oldValue == null ? 10 : oldValue + 10);

        Integer second = map.compute("quota",
                (key, oldValue) ->
                        oldValue == null ? 10 : oldValue + 10);

        Integer removed = map.compute("quota",
                (key, oldValue) -> null);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("removed=" + removed);
        System.out.println("contains=" + map.containsKey("quota"));
        System.out.println("size=" + map.size());
    }
}
```

```bash
javac ComputeBasicsDemo.java
java ComputeBasicsDemo
```

Output:

```text
first=10
second=20
removed=null
contains=false
size=0
```

Trình tự:

- Lần đầu `oldValue == null`, callback trả `10`.
- Lần thứ hai `oldValue == 10`, callback trả `20`.
- Lần cuối callback trả `null`, xóa mapping.
- Map không lưu `"quota" -> null`; nó **không còn key**.

**Phân biệt:** `compute(k, (key, old) -> null)` là một thao tác xóa có điều kiện theo callback; nếu không cần tính toán, `remove(k)` thường rõ ràng hơn.

## 7. Tại sao `compute` giải quyết lost update?

Giả sử hai thread cùng thực hiện:

```java
counts.compute("java",
        (key, old) -> old == null ? 1 : old + 1);
```

Mỗi lời gọi là một phép cập nhật nguyên tử **theo key "java"**. Một lời gọi áp dụng từ `10 -> 11`; lời gọi còn lại áp dụng tiếp `11 -> 12`, chứ không thể cả hai cùng ghi `11` dựa trên snapshot lỗi thời theo cách `get`/`put`.

### Ví dụ 3: 20.000 lần cập nhật cạnh tranh

Tạo tệp `ComputeCounterDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ComputeCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    counts.compute("java", (key, old) ->
                            old == null ? 1 : old + 1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(job);
        Thread second = new Thread(job);
        first.start();
        second.start();
        start.countDown();

        first.join();
        second.join();

        System.out.println("java=" + counts.get("java"));
        System.out.println("size=" + counts.size());
    }
}
```

```bash
javac ComputeCounterDemo.java
java ComputeCounterDemo
```

Output khi không có interrupt ngoài ý muốn:

```text
java=20000
size=1
```

Hai worker mỗi người thực hiện 10.000 lần tăng. Không sử dụng lock bên ngoài hay biến đếm global. `compute` bảo vệ phép đọc–sửa–ghi đối với key đích.

**Giới hạn:** phép cộng kiểu `int` có thể overflow; nếu business yêu cầu số không được vượt giới hạn, hãy kiểm tra ngay trong callback hoặc dùng kiểu số phù hợp. Đồng thời, Map không tự bảo vệ object mutable được lưu làm value nếu những code path khác sửa các field bên trong object đó.

## 8. `merge()`: khởi tạo hoặc gộp giá trị chỉ bằng một lời gọi

Chữ ký:

```java
V merge(
        K key,
        V value,
        BiFunction<? super V, ? super V, ? extends V> remappingFunction);
```

Khác `compute`, callback của `merge` **không nhận key**. Hai tham số callback lần lượt là:

1. **Giá trị cũ** đang lưu trong Map.
2. **Giá trị đầu vào** `value` được truyền trong lời gọi `merge`.

Khi key **vắng mặt**, `merge` đặt ngay giá trị đầu vào `value` mà **không gọi callback**. Khi key đã có giá trị, hàm remapping sẽ tính giá trị mới. Nếu callback trả `null`, mapping bị xóa.

Use case điển hình: counter, word frequency, tổng tiền theo mã sản phẩm, cộng dồn thống kê, kết hợp hai tập kết quả bất biến.

### Ví dụ 4: merge để tăng và xóa

Tạo tệp `MergeBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class MergeBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        int first = map.merge("hits", 1, Integer::sum);
        int second = map.merge("hits", 4, Integer::sum);
        int third = map.merge("hits", 5, Integer::sum);

        Integer removed = map.merge(
                "hits", 2, (oldValue, incoming) -> null);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("third=" + third);
        System.out.println("removed=" + removed);
        System.out.println("contains=" + map.containsKey("hits"));

        Integer again = map.merge("hits", 7, Integer::sum);
        System.out.println("again=" + again);
    }
}
```

```bash
javac MergeBasicsDemo.java
java MergeBasicsDemo
```

Output:

```text
first=1
second=5
third=10
removed=null
contains=false
again=7
```

Tại sao callback không chạy ở lần đầu? Vì key `hits` chưa có, `merge("hits", 1, ...)` cài `1` trực tiếp. Sau đó `Integer::sum` gộp giá trị cũ với giá trị đầu vào.

Ở lần xóa, callback nhận `(10, 2)` nhưng cố tình trả `null`, nên key bị xóa. Sau đó `merge("hits", 7, ...)` thấy key vắng mặt, lại gắn `7`.

**Không coi merge trả `null` là Map chứa một giá trị null.** `ConcurrentHashMap` không có value null; trả `null` ở đây là tín hiệu xóa mapping.

## 9. Bảng tình huống cùng một key

Giả sử bắt đầu từ Map rỗng, sau đó dùng một key `k`:

| Thao tác | Nếu trước đó key vắng mặt | Nếu trước đó `k -> 4` |
| --- | --- | --- |
| `putIfAbsent(k, 7)` | Ghi `7`, trả `null` | Giữ `4`, trả `4` |
| `compute(k, (key,v) -> v==null ? 1 : v+1)` | Ghi `1`, trả `1` | Ghi `5`, trả `5` |
| `merge(k, 3, Integer::sum)` | Ghi `3`, trả `3` | Ghi `7`, trả `7` |
| `compute(k, (key,v) -> null)` | Vẫn vắng, trả `null` | Xóa mapping, trả `null` |
| `merge(k, 3, (a,b) -> null)` | Ghi `3`, **không gọi callback** | Xóa mapping, trả `null` |

Dòng cuối là một bẫy dễ gặp: nếu bạn định dùng `merge` làm “xóa key”, callback trả null **chỉ chạy khi key đã có giá trị**. Trường hợp key vắng mặt, `merge` sẽ cài value đầu vào. Khi chỉ muốn xóa key, dùng `remove` hoặc `compute` theo điều kiện thích hợp.

## 10. Dùng `merge` để đếm tần suất từ nhiều thread

Giả sử nhiều task đang đọc các đoạn văn bản độc lập và cần đếm số lần xuất hiện từng từ. Với `ConcurrentHashMap<String,Integer>`:

```java
frequency.merge(word, 1, Integer::sum);
```

đã gom việc “nếu chưa có thì đặt 1, nếu đã có thì tăng 1” thành một thao tác nguyên tử theo từ khóa.

### Ví dụ 5: word frequency song song, output ổn định

Tạo tệp `MergeWordFrequencyDemo.java`:

```java
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class MergeWordFrequencyDemo {
    public static void main(String[] args) throws InterruptedException {
        String[] words = {
                "java", "map", "java", "atomic",
                "map", "java", "thread", "atomic"
        };
        ConcurrentHashMap<String, Integer> frequency =
                new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);

        Runnable even = () -> {
            try {
                start.await();
                for (int i = 0; i < words.length; i += 2) {
                    frequency.merge(words[i], 1, Integer::sum);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable odd = () -> {
            try {
                start.await();
                for (int i = 1; i < words.length; i += 2) {
                    frequency.merge(words[i], 1, Integer::sum);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(even);
        Thread second = new Thread(odd);
        first.start();
        second.start();
        start.countDown();
        first.join();
        second.join();

        System.out.println("frequencies="
                + new TreeMap<>(frequency));
    }
}
```

```bash
javac MergeWordFrequencyDemo.java
java MergeWordFrequencyDemo
```

Output khi không có interrupt ngoài ý muốn:

```text
frequencies={atomic=2, java=3, map=2, thread=1}
```

`ConcurrentHashMap` **không cam kết thứ tự duyệt**. `new TreeMap<>(frequency)` chỉ dùng sau khi **cả hai worker đã `join()`**, nên snapshot đã hoàn tất và TreeMap sắp xếp các key `String` theo thứ tự tự nhiên trước khi in.

Nếu liên tục tạo `new TreeMap<>(frequency)` trong khi các producer vẫn đang cập nhật, không thể mặc định đó là một snapshot nguyên tử của mọi key tại cùng một thời điểm.

### Tại sao không dùng một `HashMap` với `synchronized`?

Hoàn toàn có thể dùng khóa chung quanh mọi thao tác, ví dụ `synchronized(lock)`, để đảm bảo correctness. `ConcurrentHashMap` là lựa chọn tiện dụng khi muốn nhiều thread thao tác trên các key khác nhau mà không phải khóa toàn bộ Map bằng monitor của ứng dụng. Hiệu năng phụ thuộc workload, số key nóng và contention; **không khẳng định ConcurrentHashMap luôn nhanh hơn mọi cách khóa**.

## 11. `compute()` khác `merge()` khi nào nên chọn?

Chọn `compute` khi phép cập nhật:

- Cần biết **key** trong callback.
- Cần đọc giá trị cũ và áp dụng **điều kiện phức tạp**.
- Cần cho phép kết quả `null` để xóa key.
- Muốn xây lại một value bất biến từ value cũ.
- Cần xử lý cả trường hợp key vắng mặt và hiện hữu theo **hai nhánh logic khác nhau**.

Ví dụ giảm tồn kho, xóa mapping khi số lượng về 0:

```java
stock.compute("pencil", (key, current) -> {
    if (current == null || current <= 0) {
        throw new IllegalStateException("out of stock");
    }
    return current == 1 ? null : current - 1;
});
```

Đây là đoạn minh họa. Nó coi key vắng mặt là hết hàng và dùng việc xóa mapping khi hết số lượng. Đây chỉ là một cách biểu diễn; có domain cần giữ mapping số lượng 0 để báo cáo, khi đó nên trả `0` thay vì `null`.

Chọn `merge` khi logic tự nhiên là **lấy giá trị đầu vào rồi kết hợp với giá trị đang có**:

```java
totals.merge(productId, amount, Long::sum);
```

Đây là đoạn minh họa với `totals` là `ConcurrentHashMap<String,Long>`, `productId` là `String`, `amount` là `Long` không null. Nếu chưa có key thì ghi `amount`. Nếu đã có thì cộng vào số cũ.

Chọn `putIfAbsent` khi không muốn thay đổi giá trị hiện tại:

```java
RegistryEntry previous = entries.putIfAbsent(id, candidate);
```

Đây là đoạn minh họa với `entries` và `candidate` được tạo hợp lệ. Nếu cần kiểm tra object nào thắng, dùng `previous == null`; nếu không, có thể dùng lại previous.

## 12. Callback của `compute`/`merge` cần ngắn và không gây side effect ngoài

Với `ConcurrentHashMap`, các lời gọi `compute` và `merge` thực hiện toàn phần một cập nhật nguyên tử theo key; tài liệu API chỉ rõ callback được gọi một lần cho mỗi **lời gọi method** đó. Tuy nhiên, khi callback chạy, **các thao tác cập nhật khác có thể bị chặn**; một callback lâu làm tăng contention và rủi ro liveness.

Không nên:

```java
map.compute(key, (k, old) -> {
    callRemotePaymentService();
    Thread.sleep(5000);
    return expensiveRebuild(old);
});
```

Đây là **pseudocode phản ví dụ**, không phải mã chạy độc lập: `Thread.sleep` yêu cầu xử lý `InterruptedException`; các helper do ứng dụng định nghĩa. Trọng tâm là **không đặt I/O chặn, đợi dài hoặc side effect bên ngoài vào callback**.

Những vấn đề:

- Thread khác cập nhật những mapping liên quan có thể phải chờ.
- Nếu callback ném unchecked exception, lần tính mapping có thể không commit; **side effect đã thực hiện ngoài Map không được rollback**.
- Nếu callback gọi API bên ngoài và bên ngoài callback đó sửa Map hoặc chờ một task cũng cần Map, dễ tạo vòng chờ/deadlock.
- Nếu chính code ứng dụng retry lời gọi `compute` sau lỗi, side effect ngoài Map có thể chạy lại; **“callback một lần mỗi invocation” không có nghĩa side effect một lần suốt vòng đời nghiệp vụ**.

Cách tiếp cận tốt hơn là tạo dữ liệu đầu vào ngoài callback (nếu an toàn), sau đó callback chỉ tính trạng thái mới, commit nguyên tử trong Map, và điều phối side effect riêng với idempotency/transaction nếu cần.

**Không tuyên bố hai hệ thống trở thành transaction:** cập nhật `ConcurrentHashMap` trong RAM và gửi email/ghi database không thể tự commit nguyên tử cùng nhau chỉ vì một lời gọi `compute` thành công.

## 13. Không cập nhật chính Map đó từ callback

Javadoc của `ConcurrentHashMap` cảnh báo rằng **remapping function không nên cố cập nhật các mapping khác của cùng Map** trong khi đang chạy. Một số trường hợp cập nhật đệ quy có thể bị phát hiện và ném `IllegalStateException`; các trường hợp khác có thể gây blocking hoặc vòng chờ không mong muốn.

Ví dụ cần tránh:

```java
map.compute("a", (key, old) -> {
    map.put("b", "new value"); // Không nên cập nhật cùng map tại callback.
    return "done";
});
```

Đây là đoạn phản ví dụ. **Đừng dựa vào việc code có vẻ chạy được trên một bộ key/bucket cụ thể**: chi tiết bucket, hash collision, version JDK và cơ chế cập nhật nội bộ không phải contract được phép khai thác.

Nếu cần cập nhật **hai key như một giao dịch**, đừng ép bằng nested `compute` trên cùng Map. Hãy dùng một khóa nghiệp vụ bao trùm, một immutable aggregate lưu dưới **một key**, hoặc một cấu trúc đồng bộ/transaction phù hợp.

Đặc biệt cần tránh đợi `Future.get()` trong callback nếu task mà bạn đang chờ phải cập nhật một key trên Map ấy. Đây là một cách tạo **thread-starvation/blocking dependency** khó phân tích.

## 14. Trả null, ném exception và callback không cập nhật

Với `compute`:

- **Trả value không null:** ánh xạ mới được gắn.
- **Trả null:** mapping bị xóa hoặc giữ vắng mặt.
- **Callback ném exception:** lời gọi ném exception ra caller; mapping tại key đó **không được thay đổi bởi lần tính lỗi đó** theo contract.
- **Map chứa value mutable:** thay mapping không làm cho mọi sửa đổi tiếp theo bên trong object an toàn.

Với `merge`:

- Nếu key vắng, thêm input `value` mà không gọi callback.
- Nếu key có, gọi callback với `oldValue` và `incomingValue`.
- Nếu callback trả null, xóa mapping.
- Nếu callback ném exception, mapping tại key đó không được cập nhật bởi lần hợp nhất lỗi đó.

### Ví dụ 6: exception không tự commit giá trị mới

Tạo tệp `ComputeFailureDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ComputeFailureDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("balance", 100);

        try {
            map.compute("balance", (key, old) -> {
                if (old < 200) {
                    throw new IllegalStateException("insufficient");
                }
                return old - 200;
            });
        } catch (IllegalStateException e) {
            System.out.println("error=" + e.getMessage());
        }

        System.out.println("balance=" + map.get("balance"));
    }
}
```

```bash
javac ComputeFailureDemo.java
java ComputeFailureDemo
```

Output:

```text
error=insufficient
balance=100
```

Callback throw, nên lần `compute` không ghi giá trị mới cho `balance`. Nếu callback đã gọi một dịch vụ ngoài JVM **trước** khi throw, dịch vụ đó có thể đã thay đổi; Map không tự rollback dịch vụ ngoài. Mã ví dụ chỉ thực hiện kiểm tra và tính toán nội bộ, nên không có side effect như vậy.

## 15. Atomicity chỉ theo từng key, không theo toàn Map

Đây là một giới hạn quan trọng của cả ba API. Giả sử Map lưu hai số dư:

```text
left = 100
right = 0
Bất biến: left + right = 100
```

Nếu chuyển 10 đơn vị bằng hai thao tác:

```java
accounts.compute("left", (k, v) -> v - 10);
accounts.compute("right", (k, v) -> v + 10);
```

thì **mỗi key được cập nhật nguyên tử riêng**, nhưng một reader có thể đọc giữa hai lời gọi và thấy `left + right == 90`.

Không có cách gọi `compute` **trên hai key độc lập** để tự nhiên biến chúng thành một transaction duy nhất. Nếu invariant liên quan nhiều key, phải bảo vệ toàn bộ thao tác bằng một cơ chế chung hoặc thiết kế một immutable aggregate dưới **một key**.

### Ví dụ 7: nhìn thấy trạng thái trung gian một cách xác định

Tạo tệp `MultiKeyInvariantDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class MultiKeyInvariantDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> accounts =
                new ConcurrentHashMap<>();
        accounts.put("left", 100);
        accounts.put("right", 0);

        CountDownLatch leftUpdated = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            accounts.compute("left", (k, v) -> v - 10);
            leftUpdated.countDown();
            try {
                proceed.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            accounts.compute("right", (k, v) -> v + 10);
        });

        writer.start();
        leftUpdated.await();

        int during = accounts.get("left")
                + accounts.get("right");
        System.out.println("during=" + during);

        proceed.countDown();
        writer.join();

        int after = accounts.get("left")
                + accounts.get("right");
        System.out.println("after=" + after);
    }
}
```

```bash
javac MultiKeyInvariantDemo.java
java MultiKeyInvariantDemo
```

Output nếu không có interrupt ngoài ý muốn:

```text
during=90
after=100
```

`leftUpdated.await()` đảm bảo thao tác giảm `left` đã commit. `proceed` giữ writer chưa được cập nhật `right`. Main nhìn thấy tổng trung gian `90`. Sau khi main mở latch, writer tăng `right` và tổng trở lại `100`.

**Không có data race trong container theo nghĩa thao tác Map bị hỏng**; vấn đề là **logic nghiệp vụ gồm hai bước không có atomicity xuyên key**.

Để sửa, có thể biểu diễn hai số dư trong một record bất biến `Balances(left,right)` và dùng `compute("accounts", ...)` để thay **cả record** trong một key; hoặc dùng khóa chung cho cả đọc và ghi aggregate. Với database, cần transaction của hệ thống lưu trữ, không chỉ khóa trong JVM.

## 16. Immutable value giúp reader có snapshot nhất quán

Một pattern tốt: lưu **value bất biến** thay vì object mutable nhiều field. Mỗi `compute` tạo một object mới từ state cũ và thay nguyên một reference dưới cùng key.

Ví dụ `Profile`:

```java
record Profile(int version, String city) {}
```

Record giữ component final; ở ví dụ chỉ chứa `int` và `String` nên hợp lý để xem là bất biến. Nếu record chứa `List` mutable, nó **không tự động deep immutable**.

### Ví dụ 8: tăng version atomically trong một record

Tạo tệp `ComputeImmutableStateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ComputeImmutableStateDemo {
    record Profile(int version, String city) {}

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Profile> profiles =
                new ConcurrentHashMap<>();
        profiles.put("u1", new Profile(0, "Ha Noi"));

        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                for (int i = 0; i < 500; i++) {
                    profiles.compute("u1", (key, old) ->
                            new Profile(
                                    old.version() + 1,
                                    old.city()));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(job);
        Thread b = new Thread(job);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        Profile snapshot = profiles.get("u1");
        System.out.println("version=" + snapshot.version());
        System.out.println("city=" + snapshot.city());
    }
}
```

```bash
javac ComputeImmutableStateDemo.java
java ComputeImmutableStateDemo
```

Output khi không có interrupt ngoài ý muốn:

```text
version=1000
city=Ha Noi
```

Mỗi worker cập nhật version 500 lần, `compute` trên cùng key `u1` bảo đảm không lost update. Mỗi lần tạo `Profile` mới, không sửa bản cũ. Reader lấy một `Profile snapshot = profiles.get("u1")` rồi đọc cả `version` và `city` từ **cùng object**.

Nếu reader gọi `profiles.get("u1").version()` rồi `profiles.get("u1").city()` trong hai lượt riêng biệt, kết quả có thể đến từ hai phiên bản khác nhau khi writer còn hoạt động. **Lấy một snapshot reference cục bộ khi cần nhiều trường nhất quán cùng phiên bản.**

## 17. Mutable values: Map an toàn không đồng nghĩa value an toàn

Hãy xem:

```java
ConcurrentHashMap<String, ArrayList<String>> lists =
        new ConcurrentHashMap<>();
lists.put("events", new ArrayList<>());

lists.get("events").add("A");
```

Đây là đoạn minh họa, cần import `java.util.ArrayList` và `ConcurrentHashMap`. Nếu nhiều thread cùng lấy `ArrayList` đó rồi gọi `add`, container Map an toàn **không bảo vệ các thao tác sửa bên trong ArrayList**.

Các lựa chọn:

- Dùng **immutable copy-on-write value** rồi `compute(key, ...)` để thay reference một cách nguyên tử.
- Dùng một concurrent collection phù hợp làm value nếu bài toán thực sự cần sửa trực tiếp đồng thời.
- Dùng khóa gắn với object/aggregate theo giao thức chung.
- Phân quyền một owner duy nhất sửa dữ liệu, chỉ xuất snapshot bất biến cho reader.

Ví dụ bất biến theo key:

```java
events.compute("topic", (key, old) -> {
    List<String> next = new ArrayList<>(
            old == null ? List.of() : old);
    next.add("new event");
    return List.copyOf(next);
});
```

Đây là đoạn minh họa, cần khai báo `events` là `ConcurrentHashMap<String,List<String>>` và import `List`, `ArrayList`. `List.copyOf` tạo list không thể sửa cấu trúc qua API thông thường, nhưng **không deep-copy phần tử mutable**. Trong ví dụ phần tử `String` bất biến nên cách tiếp cận hợp lý.

**Lưu ý:** ở mỗi lần update, copy toàn bộ danh sách cũ tốn chi phí `O(n)` theo kích thước list. Nếu lượng sự kiện lớn hoặc cập nhật rất thường xuyên, mô hình bất biến copy-on-write cho một key có thể không hiệu quả; phải chọn cấu trúc/ownership khác.

## 18. `computeIfAbsent`: gần với putIfAbsent nhưng có callback

Dù trọng tâm bài là `putIfAbsent`, `compute` và `merge`, `computeIfAbsent` là API thường xuất hiện ngay bên cạnh:

```java
map.computeIfAbsent(key, k -> createValue(k));
```

Nó tính mapping cho key **chỉ khi key vắng mặt**, rồi cài value nếu mapping function trả **khác null**. Nếu trả null, không cài mapping. Với `ConcurrentHashMap`, toàn invocation atomic theo key và mapping function được gọi một lần trong invocation khi cần tính; callback phải ngắn và không sửa cùng Map đệ quy.

So sánh:

| Ý định | API gợi ý |
| --- | --- |
| Candidate đã có sẵn, chỉ cài nếu chưa có | `putIfAbsent(k, candidate)` |
| Tạo candidate **khi chưa có** | `computeIfAbsent(k, factory)` |
| Luôn tính lại từ trạng thái hiện tại, có thể xóa | `compute(k, remap)` |
| Có một giá trị đầu vào để gộp với giá trị cũ | `merge(k, incoming, combine)` |

### Ví dụ `LongAdder` cho frequency map

`LongAdder` thường hữu ích khi **nhiều thread liên tục tăng một bộ đếm nóng**, vì nội bộ có thể phân tán tranh chấp hơn một atomic counter đơn lẻ.

```java
ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent(
        "java", key -> new LongAdder()).increment();

long total = counts.get("java").sum();
```

Đây là đoạn minh họa, cần import `java.util.concurrent.ConcurrentHashMap` và `java.util.concurrent.atomic.LongAdder`. `computeIfAbsent` cài một `LongAdder` nếu vắng mặt; sau đó caller tăng chính bộ đếm đó.

**Phân biệt tính nhất quán:**

- `LongAdder.increment()` hỗ trợ cập nhật đồng thời.
- `LongAdder.sum()` trong lúc các thread khác vẫn tăng **không phải một snapshot nguyên tử toàn bộ cập nhật**, nên phù hợp thống kê/monitoring khi chấp nhận một lần đọc tức thời không hoàn toàn đồng bộ.
- Nếu cần quyết định nghiệp vụ dựa trên **giá trị chính xác tại một điểm tuyến tính hóa**, nên xem xét primitive khác và giao thức phù hợp.

`computeIfAbsent` chỉ giải quyết **khởi tạo adder**, không biến việc đọc `sum()` và đặt điều kiện nhiều bước thành một transaction.

## 19. Atomicity và thứ tự bộ nhớ theo Java Memory Model

`ConcurrentHashMap` cung cấp bảo đảm đồng thời để các thread có thể truy cập cùng Map an toàn và quan sát mapping được công bố. Một thao tác update thành công có các quan hệ happens-before phù hợp đối với những lần truy cập nhận value từ mapping đó theo hợp đồng concurrent collection.

Một hệ quả thực hành: worker có thể tạo một **object đã được khởi tạo hoàn chỉnh**, đưa nó vào `ConcurrentHashMap`, và worker khác lấy object ấy bằng `get(key)` sau khi mapping được công bố sẽ có bảo đảm bộ nhớ để nhìn thấy những ghi xảy ra trước khi công bố.

Nhưng đừng suy diễn quá mức:

- **An toàn công bố không biến mutable value thành immutable.**
- Một reader lấy tham chiếu rồi writer bên ngoài sửa fields chưa được đồng bộ vẫn có thể tạo data race.
- Một chuỗi `get(A)`, `get(B)` không tự tạo snapshot nguyên tử của hai key.
- Một lượt duyệt `entrySet()` khi Map đang thay đổi không tạo giao dịch ảnh chụp toàn bộ Map.
- Chỉ khi đúng cùng Map và giao thức cập nhật hợp lệ, API atomic theo key mới có thể được dùng để chứng minh các cập nhật nghiệp vụ tương ứng.

Khi cần tính nhất quán chặt chẽ, hãy chỉ rõ **đơn vị nguyên tử**: một mapping, một value aggregate hay một nhóm nhiều mapping đòi hỏi khóa/protocol.

## 20. Duyệt ConcurrentHashMap: weakly consistent, không phải snapshot bất biến

`ConcurrentHashMap` hỗ trợ iterator và các thao tác duyệt trong lúc Map còn bị cập nhật. Iterator của nó thuộc loại **weakly consistent**: không ném `ConcurrentModificationException` chỉ vì các thread khác đang thay đổi Map, và có thể phản ánh một số thay đổi đồng thời.

Điều **không** được đảm bảo: một lượt duyệt cho thấy chính xác tất cả key/value tại một thời điểm duy nhất, theo một thứ tự ổn định.

Ví dụ:

```java
for (var entry : map.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Đây là đoạn minh họa, `map` là `ConcurrentHashMap`. Nếu Map đang thay đổi, output có thể khác nhau giữa các lần chạy; không thể dùng kết quả của vòng duyệt làm bằng chứng bất biến xuyên toàn Map.

Các API như `size()`, `mappingCount()`, `containsValue()` cũng cần được hiểu theo điều kiện cập nhật đồng thời. Khi Map đang chịu ghi mạnh, các phép thống kê/tổng hợp toàn Map thường phù hợp **monitoring** hơn quyết định nghiệp vụ yêu cầu snapshot nhất quán.

Nếu cần báo cáo chính xác sau một batch, hãy đợi mọi producer hoàn thành (ví dụ `Thread.join()`, `Future.get()`) rồi tạo bản sao để trình bày. Nếu writer vẫn chạy, cần khóa, versioning/snapshot protocol hoặc một cách cô lập dữ liệu phù hợp để đảm bảo consistency.

## 21. Key phải có equals/hashCode ổn định

`ConcurrentHashMap` là hash-based map. Nó cần `hashCode()` và `equals()` của key phù hợp trong suốt thời gian key được dùng. Nếu object key bị sửa các trường tham gia hash/equality sau khi đưa vào Map, thao tác `get()`/`remove()` có thể không tìm ra mapping như mong đợi.

Ví dụ sai:

```java
final class MutableKey {
    int id;

    MutableKey(int id) {
        this.id = id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other
                && other.id == id;
    }
}
```

Đây là lớp minh họa. Nếu dùng `new MutableKey(1)` làm key, rồi đổi `id` thành `2` sau `put`, hash/equality của key thay đổi. `ConcurrentHashMap` thread-safe **không thể tự khôi phục một key mutable đã thay đổi identity logic**.

Ưu tiên:

```java
record Key(int id) {}
```

Với `record Key(int id)`, component primitive `int` là final, thuận tiện làm key ổn định. Với record chứa mảng hoặc object mutable, vẫn phải xét deep immutability và equals/hashCode của component.

Ngoài ra, callback `compute` hoặc `merge` không nên dựa vào một key có hashCode thay đổi khi đang xử lý.

## 22. Khả năng scale và key nóng

`ConcurrentHashMap` cho phép nhiều thao tác trên các key khác nhau có thể tiến triển đồng thời. Nhưng **tất cả thread cập nhật cùng một key** vẫn tranh chấp trên cùng đơn vị nguyên tử đó.

Ví dụ 100 thread đều gọi:

```java
counts.merge("global", 1, Integer::sum);
```

thì key `global` là điểm nóng. Không có phép màu phân tán phép tính trên một key ra nhiều core mà vẫn giữ một biến `Integer` với một thứ tự cập nhật nguyên tử.

Các hướng tối ưu, tùy bài toán:

1. **Sharding theo key:** mỗi nhóm dữ liệu có key riêng nếu nghiệp vụ cho phép; giảm contention.
2. **LongAdder:** phù hợp số liệu tăng nhiều, đọc tổng không cần linearizable snapshot dưới cập nhật đồng thời.
3. **Batching:** mỗi worker gom số local, rồi merge một lần mỗi batch thay vì một lần mỗi phần tử.
4. **Immutable aggregate:** giúp đọc snapshot của một key nhất quán nếu value có nhiều field.
5. **Thay thuật toán:** nếu workload quá nhỏ hoặc chỉ một thread, Map concurrent có overhead không cần thiết.

Đừng benchmark bằng một lần `System.nanoTime()` trên mảng vài phần tử rồi kết luận thư viện A “nhanh hơn luôn”. Với JVM cần warm-up, cùng dữ liệu, nhiều lần chạy và công cụ như JMH nếu đo vi mô.

## 23. Xử lý contention, khóa nội bộ và hàm callback dài

Một số thao tác đọc của `ConcurrentHashMap` được thiết kế rất hiệu quả khi nhiều thread; các cập nhật phức tạp như `compute`/`merge` có thể phải phối hợp các writer ở vùng liên quan. Không nên viết logic nghiệp vụ giả định “`ConcurrentHashMap` hoàn toàn lock-free trong mọi phương thức”.

Mỗi `compute`/`merge` có thể cần chặn các update cạnh tranh trong lúc callback đang chạy. Vì vậy:

- Callback chỉ làm phép tính nhanh, không gọi remote API.
- Không giữ một khóa nghiệp vụ khác rồi chờ callback ở key khác theo vòng phụ thuộc.
- Không tạo dependency “callback A đợi task B, task B cần callback A”.
- Không chỉnh các mapping khác của chính Map trong callback.
- Không thiết kế callback có side effect rồi mong một exception của callback sẽ rollback mọi hệ thống khác.

Nếu cần giữ một invariant trên nhiều key, chọn chiến lược rõ ràng: khóa ngoài cho toàn aggregate, immutable value dưới một key, actor/single-owner, hoặc transaction ở tầng lưu trữ. Sử dụng các callback theo key chỉ vì “Map concurrent” không đủ để chứng minh workflow an toàn.

## 24. Lỗi thường gặp và cách sửa

### 24.1. `get()` rồi `put()` để tăng counter

**Sai:** hai thread đọc cùng old value rồi cùng ghi kết quả mới. **Sửa:** dùng `merge(k, 1, Integer::sum)` hoặc `compute(k, (key, old) -> old == null ? 1 : old + 1)`.

### 24.2. `containsKey()` rồi `put()` để khởi tạo

**Sai:** check-then-act không nguyên tử. **Sửa:** dùng `putIfAbsent(k, candidate)` hoặc `computeIfAbsent(k, factory)`.

### 24.3. Dùng `putIfAbsent` để cộng dồn

**Sai:** lần đầu có thể gắn `1`, những lần sau không tăng nữa. **Sửa:** `merge` hoặc `compute` tùy logic.

### 24.4. Quên kiểm tra `null` trong callback `compute`

Khi key vắng, `oldValue == null`. Nếu viết `oldValue + 1` sẽ `NullPointerException` do unboxing. **Sửa:** xử lý nhánh vắng mặt rõ ràng.

### 24.5. Truyền null để lưu vào ConcurrentHashMap

`ConcurrentHashMap` không cho phép key/value null. **Sửa:** chọn sentinel/value type không null hoặc `remove` nếu muốn biểu thị không còn mapping.

### 24.6. Nhầm `merge` với `compute` khi key vắng

`merge` không gọi callback khi key vắng, mà gắn input value trực tiếp. **Sửa:** nếu cần xử lý cả absent/present bằng callback, dùng `compute`.

### 24.7. Trả null từ callback nhưng mong Map lưu null

Trả null làm xóa/không tạo mapping. **Sửa:** dùng một object thể hiện trạng thái “empty” nếu nghiệp vụ cần giữ key.

### 24.8. Gọi I/O hoặc thao tác chờ dài trong callback

Callback dài có thể block cập nhật cạnh tranh, tạo lock contention. **Sửa:** chuyển I/O ra ranh giới giao thức riêng và giữ callback ngắn.

### 24.9. Cập nhật Map từ chính callback

Nested update có thể bị cấm hoặc gây liveness bug. **Sửa:** không sửa các mapping khác trong remapping function; xử lý đa key theo một thiết kế khác.

### 24.10. Nghĩ update hai key là một transaction

Hai `compute` có hai bước nguyên tử khác nhau. **Sửa:** gộp immutable aggregate dưới một key hoặc đồng bộ toàn thao tác.

### 24.11. Dùng mutable ArrayList làm value mà không đồng bộ

Map an toàn không làm `ArrayList.add` an toàn. **Sửa:** concurrent collection phù hợp hoặc copy-on-write immutable value qua `compute`.

### 24.12. Coi iterator là một snapshot nhất quán

Duyệt Map đang bị ghi là weakly consistent. **Sửa:** cần quiescence/snapshot protocol nếu muốn số liệu chính xác.

### 24.13. Dùng key mutable

Hash/equality thay đổi làm lookup sai. **Sửa:** dùng key bất biến với `equals`/`hashCode` ổn định.

### 24.14. Bỏ qua overflow

`Integer::sum` có thể overflow nếu đếm vượt phạm vi int. **Sửa:** dùng `long` hoặc kiểm tra `Math.addExact` theo yêu cầu domain, và có chiến lược khi vượt ngưỡng.

### 24.15. Nghĩ `LongAdder.sum()` là snapshot nguyên tử trong lúc ghi

`LongAdder` tối ưu throughput hơn trong một số workload nhưng tổng đọc đồng thời không phải snapshot tuyến tính hóa. **Sửa:** chọn atomic counter/giao thức chốt dữ liệu nếu quyết định nghiệp vụ cần exact point-in-time value.

### 24.16. Bỏ qua exception của callback

Nếu callback throw, mapping không commit lần cập nhật đó. Caller phải phân biệt lỗi input, lỗi số học, lỗi runtime và xử lý có kiểm soát; không trả “success” như thể thay đổi đã xảy ra.

## 25. Bài tập thực hành

**Bài tập 1: đếm theo key.** Dùng `ConcurrentHashMap<String,Integer>` để đếm tần suất các từ từ bốn producer. Triển khai hai cách `compute` và `merge`, đợi các worker bằng `join()`/`Future.get()` rồi so sánh kết quả.

**Bài tập 2: khởi tạo winner duy nhất.** Hai thread cùng `putIfAbsent("leader", candidate)`, ghi lại caller nào nhận `null`. Không hardcode ai thắng; assert chỉ có đúng một lần cài mapping.

**Bài tập 3: decrement đến zero.** Dùng `compute` cho một key tồn kho. Khi current == 1, trả `null` để xóa; khi current > 1, trừ 1; khi key vắng, báo out-of-stock. Kiểm tra số âm, retry policy và exception.

**Bài tập 4: giá trị bất biến.** Thay `String` đơn lẻ bằng record `Config(version, url)` và cập nhật version/url trong **một `compute`**. Reader gọi `get()` một lần rồi dùng snapshot.

**Bài tập 5: invariant nhiều key.** Mô phỏng chuyển 10 đơn vị từ key A sang B bằng hai `compute`. Tạo latch để reader đọc giữa hai bước, chứng minh tổng có thể lệch; sau đó sửa bằng một immutable aggregate hoặc lock chung.

**Bài tập 6: callback nguy hiểm.** Thử đặt một thao tác chờ dài trong callback và quan sát giảm throughput (trên môi trường test). Không dùng cách đó trong production. Viết lại để callback chỉ tính state.

**Bài tập 7: kiểm thử mảng kết quả.** Dùng `TreeMap` sau khi tất cả producer đã dừng để có output key sắp xếp ổn định. Thử duyệt trước khi chờ producer và giải thích vì sao kết quả có thể khác nhau.

**Bài tập 8: throughput.** So sánh `merge(k,1,Integer::sum)`, `computeIfAbsent(k,()->LongAdder).increment()` (sửa đúng lambda chỉ nhận key) và batching local. Benchmark với cùng lượng key và contention; không chỉ đo một lần chạy nhỏ.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao `ConcurrentHashMap` không làm `get` rồi `put` trở thành một lần tăng nguyên tử?**

Vì hai lời gọi có khoảng trống để thread khác cập nhật. Từng API riêng thread-safe không ghép hai lời gọi thành transaction.

**2. `putIfAbsent(k, v)` trả `null` nghĩa là gì?**

Với `ConcurrentHashMap` không cho phép null value, nghĩa là không có mapping trước đó và lời gọi đã cài `v`.

**3. Hai thread cùng `putIfAbsent` một key vắng có thể cùng trả `null` không?**

Không nếu key không bị xóa xen vào và không có cập nhật làm nó vắng trở lại. Với cuộc đua cài một lần như ví dụ, chỉ một caller thắng.

**4. `compute(k, (key, old) -> null)` làm gì?**

Xóa mapping nếu có, hoặc giữ key vắng mặt; Map không lưu giá trị null.

**5. `merge("hits", 3, Integer::sum)` khi key vắng mặt có gọi `Integer::sum` không?**

Không. Nó gắn `3` trực tiếp.

**6. `merge(k, 3, (old, incoming) -> null)` khi key vắng mặt có xóa không?**

Không. Nó thêm `3`. Callback chỉ chạy nếu key đã có value.

**7. Có nên gọi API thanh toán từ callback `compute` không?**

Không nên. Callback có thể chặn các update liên quan, và side effect ngoài Map không rollback nếu lần cập nhật lỗi hoặc nghiệp vụ retry.

**8. Một `ConcurrentHashMap<String, ArrayList<String>>` có bảo vệ được `get(k).add(...)` đồng thời không?**

Không. Thread safety của Map không truyền vào các field/method mutable của value.

**9. Hai lần `compute` cập nhật hai key có bảo đảm invariant xuyên cả hai không?**

Không. Cần một cơ chế atomicity chung hoặc gộp state dưới một key.

**10. Vì sao một record bất biến dưới một key dễ đọc nhất quán hơn nhiều key rời rạc?**

Reader lấy một reference snapshot duy nhất, chứa các field thuộc cùng phiên bản được công bố nguyên tử bằng một update của mapping.

**11. Có thể coi `entrySet()` trong lúc Map bị ghi là ảnh chụp chính xác tại một thời điểm không?**

Không. Iterator weakly consistent; có thể phản ánh một số thay đổi đồng thời, không hứa snapshot tuyến tính hóa toàn Map.

**12. `computeIfAbsent` và `putIfAbsent` khác nhau ở đâu về việc tạo candidate?**

`putIfAbsent` nhận value đã được tạo trước. `computeIfAbsent` gọi mapping function khi key vắng mặt để tạo value; phải giữ callback ngắn, không side effect không kiểm soát.

**13. `LongAdder.sum()` dưới contention có phải giá trị snapshot nguyên tử tuyệt đối không?**

Không. Nó hữu ích cho thống kê cộng dồn, nhưng không phải snapshot đồng thời tuyến tính hóa.

**14. Nếu callback `compute` ném `IllegalStateException`, mapping có được cập nhật từ lần tính lỗi đó không?**

Không; thao tác thất bại và mapping tại key không bị cập nhật do lần gọi đó. Side effect ngoài Map đã xảy ra trước exception thì không được tự rollback.

**15. Tại sao key mutable là nguy hiểm dù dùng ConcurrentHashMap?**

Vì `equals`/`hashCode` có thể thay đổi sau khi chèn; Map có thể không tìm lại mapping như mong đợi.

**16. ConcurrentHashMap có luôn nhanh hơn một khóa `synchronized` không?**

Không. Kết quả phụ thuộc workload, số key nóng, contention, độ dài callback, bộ nhớ/cache và chi phí thực tế.

## 27. Tổng kết

**`putIfAbsent`**, **`compute`** và **`merge`** là ba thao tác nền tảng để thực hiện những thay đổi **nguyên tử theo từng key** của `ConcurrentHashMap`:

1. **`putIfAbsent(k,v)`:** chỉ cài giá trị khi key chưa có, không ghi đè giá trị cũ; phù hợp đăng ký/khởi tạo.
2. **`compute(k,f)`:** tính lại state từ giá trị hiện tại và có thể xóa bằng `null`; phù hợp validation, biến đổi state, immutable snapshots.
3. **`merge(k,v,f)`:** nếu chưa có key thì cài `v`; nếu có thì gộp với giá trị cũ; phù hợp counter và tổng hợp.

Chúng sửa được các race condition kiểu **check-then-act** và **read-modify-write** trong phạm vi **một mapping**, nhưng không biến các chuỗi thao tác nhiều key thành transaction, không tự bảo vệ mutable object chứa trong value và không đảm bảo side effect ngoài JVM atomic cùng Map.

Để dùng an toàn: giữ key/value không null, key có hash/equality ổn định, callback ngắn và không cập nhật lại Map từ bên trong, hiểu semantics của `null`/exception, chọn primitive phù hợp khi key nóng, và đợi các worker hoàn tất trước khi tạo báo cáo toàn Map cần độ chính xác. **Thread-safe collection là công cụ; tính đúng đắn vẫn phụ thuộc giao thức dữ liệu và invariant của ứng dụng.**
