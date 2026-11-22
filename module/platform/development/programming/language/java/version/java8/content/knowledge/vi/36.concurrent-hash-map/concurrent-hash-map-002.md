# Giới hạn thời gian và tác dụng phụ trong hàm tính của ConcurrentHashMap

## 1. Vì sao một lambda “nhỏ” có thể làm cả hệ thống chậm?

`ConcurrentHashMap<K,V>` được thiết kế cho nhiều luồng truy cập đồng thời. Bên cạnh `get`, `put` và `putIfAbsent`, Java cung cấp các phương thức tính giá trị theo khóa như `computeIfAbsent`, `computeIfPresent`, `compute` và `merge`. Đây là công cụ mạnh để cập nhật một khóa **nguyên tử** (*atomic*), nhưng có một ràng buộc rất quan trọng: **hàm tính/remapping phải ngắn gọn, đơn giản và không cập nhật chính map đang được tính**.

Ví dụ tưởng chừng tự nhiên nhưng nguy hiểm:

```java
// Phản ví dụ; KHÔNG dùng cho I/O chậm.
cache.computeIfAbsent(userId, id -> {
    return remoteService.fetchUser(id); // Có thể chờ mạng rất lâu.
});
```

`computeIfAbsent` là thao tác nguyên tử trên map, nên khi callback đang chạy, một số thao tác cập nhật từ luồng khác **có thể bị chặn**. Nếu callback mất hàng giây vì I/O, chờ khóa khác, sleep hoặc chờ future, latency của các thao tác khác có thể tăng mạnh. `ConcurrentHashMap` **không có một tham số timeout tự động cho callback**.

Một phản ví dụ khác:

```java
// Phản ví dụ; KHÔNG cập nhật cùng map trong callback.
map.computeIfAbsent("A", key -> {
    map.put("B", "other");  // Vi phạm contract.
    return "value";
});
```

Callback có thể thay đổi những thứ khác bên ngoài map, nhưng tác dụng phụ ấy **không được transaction của ConcurrentHashMap bảo vệ**. Nếu callback bị gọi lại ở một invocation khác, trả `null` hoặc ném exception, những side effect bên ngoài **không được tự rollback**.

Bài này tập trung vào đúng chủ đề: **giới hạn thời gian thực thi và tác dụng phụ trong các hàm tính của ConcurrentHashMap**. Nội dung gồm hợp đồng API, nguyên nhân tranh chấp, deadlock/recursive update, ngoại lệ, `null`, “exactly once” đúng nghĩa, thiết kế callback thuần, tích hợp I/O ngoài critical section, pattern `LongAdder` và `CompletableFuture`, kiểm thử đồng thời và checklist production.

Các API này tồn tại từ Java 8 và **vẫn còn áp dụng trong Java hiện đại**. Ví dụ viết bằng Java tương thích JDK 17+ và không sử dụng kỹ thuật legacy. Phần khác biệt giữa `Map`, `ConcurrentMap` và chính `ConcurrentHashMap` được ghi rõ vì những lớp này **không có mọi bảo đảm thực thi giống nhau**.

## 2. Bốn phương thức compute và khi nào callback chạy

| Phương thức | Chạy callback khi nào? | Đầu vào callback | Nếu callback trả `null` |
| --- | --- | --- | --- |
| `computeIfAbsent(k, f)` | Chỉ khi khóa chưa có mapping | `f(k)` | Không thêm mapping |
| `computeIfPresent(k, f)` | Chỉ khi khóa đang có mapping | `f(k, oldValue)` | Xóa mapping hiện có |
| `compute(k, f)` | Mỗi invocation của phương thức | `f(k, oldValueOrNull)` | Xóa mapping nếu có; nếu vắng thì vẫn vắng |
| `merge(k, nonNullValue, f)` | Chỉ khi khóa đã có mapping | `f(oldValue, suppliedValue)` | Xóa mapping hiện có |

Với `merge`, nếu khóa chưa có mapping, nó chèn trực tiếp `nonNullValue` và **không gọi remapping function**. Không nhầm điều này với `compute` hoặc `computeIfAbsent`.

### 2.1. Chữ ký API

```java
// Các chữ ký minh họa, không phải chương trình độc lập.
V computeIfAbsent(
    K key,
    Function<? super K, ? extends V> mappingFunction
);

V computeIfPresent(
    K key,
    BiFunction<? super K, ? super V, ? extends V> remappingFunction
);

V compute(
    K key,
    BiFunction<? super K, ? super V, ? extends V> remappingFunction
);

V merge(
    K key,
    V value,
    BiFunction<? super V, ? super V, ? extends V> remappingFunction
);
```

Trong `ConcurrentHashMap`, **khóa và giá trị `null` không được hỗ trợ**. Do đó `get(k)==null` chỉ sự vắng mặt của mapping. Callback trả `null` mang ngữ nghĩa **không lưu/xóa**, chứ không phải “lưu một giá trị null”.

### 2.2. Atomicity áp dụng đến đâu?

`compute` và các biến thể của `ConcurrentHashMap` thực thi cập nhật **một key** theo cách nguyên tử đối với các cập nhật cạnh tranh liên quan. Không có một transaction tự động bao trùm:

- Các cập nhật trên nhiều key khác nhau.
- Cơ sở dữ liệu hay dịch vụ HTTP bên ngoài.
- Ghi log, gửi email, phát sự kiện.
- Đọc/ghi những object mutable được giữ ngoài map.
- Những lần gọi method khác nhau theo thời gian.

Vì thế một callback có thể **tính và công bố một value mới** nguyên tử trong map, nhưng **không làm cho tất cả side effect của callback trở thành nguyên tử**.

## 3. Điều hợp đồng API thực sự yêu cầu

Javadoc hiện hành của `ConcurrentHashMap` nêu rõ với `computeIfAbsent`, `computeIfPresent` và `compute`:

- Phương thức hoàn thành nguyên tử.
- Callback được gọi đúng một lần **trong mỗi invocation thích hợp**: `computeIfAbsent` chỉ khi absent, `computeIfPresent` chỉ khi present, `compute` mỗi invocation.
- Một số thao tác cập nhật của luồng khác **có thể bị block trong thời gian callback chạy**.
- Callback nên **ngắn và đơn giản**.
- Callback **không được cập nhật chính map này trong lúc tính**.
- Đệ quy cập nhật map có thể gây `IllegalStateException` **nếu triển khai phát hiện được** trường hợp sẽ không hoàn tất.

`merge` cũng nguyên tử và yêu cầu remapping function ngắn gọn, không cập nhật mapping khác của chính map.

**Quan trọng:** Lời hứa “đúng một lần trong mỗi invocation” **không phải** “một lần duy nhất trong suốt đời ứng dụng” hoặc “tác dụng phụ của callback được xử lý exactly-once bởi mọi hệ thống”.

Nếu giá trị không được tạo (callback trả `null` hoặc ném exception), sau đó bị xóa, hoặc nhiều invocation độc lập được thực hiện, callback có thể được gọi nhiều lần **theo các invocation đó**. Nếu bạn gắn một hành động không idempotent vào callback, không thể dựa vào atomicity của map để bảo đảm hành động ấy chỉ diễn ra một lần trên toàn hệ thống.

### 3.1. Vì sao phải phân biệt `Map`/`ConcurrentMap` với `ConcurrentHashMap`?

`Map` có các phương thức default về `compute`, `computeIfAbsent` và `merge` nhưng không bảo đảm nguyên tử cho mọi implementation. Một số default method của `ConcurrentMap` có thể dùng vòng lặp `replace`/`remove` để retry khi có cạnh tranh, do đó callback có thể bị đánh giá lại. `ConcurrentHashMap` có triển khai riêng với contract cụ thể ở trên.

Khi viết thư viện nhận tham số kiểu `Map<K,V>` hay `ConcurrentMap<K,V>`, **không được suy tất cả implementation đều hứa callback đúng một lần mỗi invocation**. Cần đọc Javadoc của **kiểu map thực tế**.

## 4. Ví dụ 1 — callback nào chạy, khi nào ghi/xóa?

Tạo file **ComputeMethodsDemo.java**:

```java
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ComputeMethodsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
            new ConcurrentHashMap<>();

        AtomicInteger calls = new AtomicInteger();

        System.out.println("first=" +
            map.computeIfAbsent("a", k -> {
                calls.incrementAndGet(); // Đếm để quan sát demo.
                return "A";
            }));

        System.out.println("second=" +
            map.computeIfAbsent("a", k -> {
                calls.incrementAndGet();
                return "B";
            }));

        System.out.println("calls=" + calls.get());

        System.out.println("present=" +
            map.computeIfPresent(
                "a", (k, v) -> v + "!"
            ));

        System.out.println("missingPresent=" +
            map.computeIfPresent(
                "z", (k, v) -> "X"
            ));

        System.out.println("computed=" +
            map.compute(
                "b", (k, v) -> v == null ? "B" : v + "+"
            ));

        System.out.println("merged=" +
            map.merge(
                "a", "?",
                (oldValue, newValue) ->
                    oldValue + newValue
            ));

        System.out.println("mergeAbsent=" +
            map.merge(
                "c", "C",
                (oldValue, newValue) -> "UNUSED"
            ));

        System.out.println("removed=" +
            map.compute("b", (k, v) -> null));

        System.out.println("snapshot=" +
            new TreeMap<>(map));
    }
}
```

```bash
javac ComputeMethodsDemo.java
java ComputeMethodsDemo
```

Stdout đã kiểm thử:

```text
first=A
second=A
calls=1
present=A!
missingPresent=null
computed=B
merged=A!?
mergeAbsent=C
removed=null
snapshot={a=A!?, c=C}
```

**Phân tích:**

1. Trong invocation thứ hai của `computeIfAbsent("a", ...)`, khóa đã có value nên callback thứ hai **không chạy**.
2. `computeIfPresent` chỉ chạy callback khi khóa đang tồn tại.
3. `compute("b", ...)` nhận `null` làm oldValue khi khóa ban đầu absent.
4. `merge("a","?",...)` gọi callback vì `a` đã tồn tại.
5. `merge("c","C",...)` thêm `C` trực tiếp, **không gọi callback**.
6. `compute("b", ..., -> null)` xóa mapping `b`.

`AtomicInteger calls` trong ví dụ chỉ là dụng cụ đo số lần callback được gọi; trong production, callback có side effect nên được cân nhắc kỹ. Khi thiết kế logic business, ưu tiên chỉ tính **giá trị trả về** trong callback.

## 5. Tại sao callback dài gây tranh chấp?

`ConcurrentHashMap` có cơ chế đồng bộ nội bộ để một operation cập nhật một khóa không bị tranh chấp bất nhất. Khi callback của `computeIfAbsent`/`compute`/`merge` đang chạy, operation có thể phải duy trì trạng thái đồng bộ hoặc reservation thích hợp trong thời gian đó.

Một timeline điển hình:

```text
Thread A                         Thread B
   |                                |
computeIfAbsent("hot", f)             |
   |                                |
   +--- bắt đầu f()                 |
   |    (đợi I/O 2 giây)            |
   |                           computeIfAbsent("hot", g)
   |                                |
   |                                +--- chờ A
   |                                |
   +--- f() trả value               |
   +--- công bố mapping             |
                                    +--- đọc value đã có
                                    +--- g() không cần chạy
```

**Không hiểu nhầm:** Điều này không có nghĩa **toàn bộ map bị lock**. Các cập nhật trên khóa khác có thể tiếp tục song song; nhưng một số khóa cập nhật có thể tranh chấp nội bộ, ví dụ cùng khóa hoặc vùng cấu trúc/bucket liên quan. Javadoc cố ý không hứa một thời gian chặn cố định hay một sơ đồ khóa cụ thể.

### 5.1. Các thao tác nên tránh bên trong callback

- HTTP request, RPC, truy vấn database có latency khó dự đoán.
- `Thread.sleep`, `wait`, `Future.get`, `CompletableFuture.join`.
- `CountDownLatch.await` chờ tín hiệu từ luồng khác.
- Chờ một mutex do code khác đang giữ.
- Truy cập file hoặc mạng đồng bộ.
- Chạy thuật toán CPU rất nặng hoặc vòng lặp không giới hạn.
- Parse dữ liệu không tin cậy có chi phí không kiểm soát.
- Ghi log đồng bộ có thể chặn trên thiết bị I/O.
- Gọi lại phương thức `compute`/`put` trên **chính map**.

**Quy tắc thiết kế:** Callback chỉ nên dùng những phép toán **trong bộ nhớ, thời gian chạy nhỏ và có giới hạn hợp lý theo tải thực tế**, không có việc chờ ngoại vi không kiểm soát.

### 5.2. Không có “timeout của compute”

`computeIfAbsent` và `compute` **không có tham số deadline/timeout**. Nếu một luồng gọi `future.get(100, TimeUnit.MILLISECONDS)` để chờ task đang chạy `map.compute(...)`, thì timeout đó **chỉ giới hạn thời gian luồng chờ future**.

Task gốc có thể **tiếp tục chạy**, có thể vẫn đang giữ một trạng thái đồng bộ của map. `Future.cancel(true)` chỉ gửi yêu cầu ngắt khi được hỗ trợ; nó **không bảo đảm callback dừng** hoặc side effect bị rollback. Do đó “bọc compute bằng executor + get(timeout)” **không tự giải quyết** rủi ro long-running callback.

## 6. Ví dụ 2 — minh họa chờ khi cùng khóa đang được tính

Tạo file **BlockingDemo.java**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class BlockingDemo {
    public static void main(String[] args)
            throws Exception {
        ConcurrentHashMap<String, String> map =
            new ConcurrentHashMap<>();

        ExecutorService pool =
            Executors.newFixedThreadPool(2);

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch attempted = new CountDownLatch(1);
        AtomicInteger created = new AtomicInteger();

        try {
            Future<String> first = pool.submit(() ->
                map.computeIfAbsent("hot", k -> {
                    created.incrementAndGet();
                    entered.countDown();

                    // Cố ý chặn để minh họa:
                    // KHÔNG làm thế trong production.
                    try {
                        if (!release.await(
                                4, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                "timed out"
                            );
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(ex);
                    }

                    return "ready";
                })
            );

            if (!entered.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not entered"
                );
            }

            Future<String> second = pool.submit(() -> {
                attempted.countDown();
                return map.computeIfAbsent(
                    "hot", k -> {
                        created.incrementAndGet();
                        return "second";
                    }
                );
            });

            if (!attempted.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not attempted"
                );
            }

            try {
                second.get(100, TimeUnit.MILLISECONDS);
                System.out.println(
                    "secondBeforeRelease=DONE"
                );
            } catch (TimeoutException ex) {
                System.out.println(
                    "secondBeforeRelease=WAITING"
                );
            } finally {
                release.countDown();
            }

            System.out.println("first=" +
                first.get(3, TimeUnit.SECONDS));

            System.out.println("second=" +
                second.get(3, TimeUnit.SECONDS));

            System.out.println("created=" +
                created.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BlockingDemo.java
java BlockingDemo
```

Stdout được kiểm thử với các latch bảo đảm thứ tự:

```text
secondBeforeRelease=WAITING
first=ready
second=ready
created=1
```

**Bản chất của demo:** Thread A giữ callback ở khóa `"hot"` trong lúc chờ latch; thread B cũng muốn tạo mapping của cùng key nên chưa hoàn tất trước khi A được release. Sau đó hai thread nhận cùng value `"ready"`; callback thứ hai không cần chạy.

**Đây là thử nghiệm phản ví dụ có chủ ý.** Không dùng `CountDownLatch.await` trong callback production. Các timeout `get(...)` chỉ bảo vệ bộ test khỏi đợi vô hạn và **không định nghĩa timeout cho ConcurrentHashMap**.

## 7. Atomic increment: công việc ngắn, đúng và nhanh

Một use case hợp lý của `compute` là cập nhật một counter bằng phép tính trong bộ nhớ:

```java
// Đoạn minh họa.
map.compute("hits",
    (key, oldValue) ->
        oldValue == null ? 1 : oldValue + 1
);
```

Callback không cần I/O, không gọi update khác trên map, không chia sẻ object mutable bên ngoài. Mỗi invocation xét giá trị của key theo contract của `ConcurrentHashMap` và công bố kết quả mới nguyên tử.

**Không thay thế bằng `get` + `put`:**

```java
// Phản ví dụ: có lost update khi nhiều thread cùng chạy.
Integer old = map.get("hits");
map.put("hits", old == null ? 1 : old + 1);
```

Hai thread có thể cùng đọc một giá trị cũ rồi cùng ghi giá trị mới giống nhau, khiến mất một lần tăng.

### Ví dụ 3 — AtomicCounterDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AtomicCounterDemo {
    public static void main(String[] args)
            throws Exception {
        ConcurrentHashMap<String, Integer> map =
            new ConcurrentHashMap<>();

        ExecutorService pool =
            Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs = new ArrayList<>();

            for (int i = 0; i < 4; i++) {
                jobs.add(pool.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        map.compute(
                            "hits",
                            (k, v) -> v == null ? 1 : v + 1
                        );
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }

            System.out.println("hits=" +
                map.get("hits"));

            System.out.println("keys=" +
                map.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Stdout:

```text
hits=4000
keys=1
```

Có 4 thread × 1000 lần tăng, sau khi chờ tất cả task hoàn tất thì counter bằng 4000. Đây là **một cập nhật ngắn trên một key**, phù hợp hơn nhiều so với I/O chậm trong callback.

**Giới hạn:** `Integer` có thể overflow nếu counter vượt `Integer.MAX_VALUE`; với bộ đếm lớn, chọn kiểu/value/chiến lược phù hợp như `LongAdder`. Kết quả `map.size()` hoặc việc đọc một trạng thái tổng trong lúc nhiều update đang xảy ra không có nghĩa map cung cấp snapshot transaction toàn cục.

## 8. Tác dụng phụ: vì sao “exactly once” dễ bị hiểu sai?

Một **side effect** là hành vi không chỉ tạo giá trị trả về, ví dụ:

- Ghi vào database, gửi email, tạo hóa đơn.
- Phát Kafka event, ghi queue, gọi HTTP API.
- Tăng counter dùng chung ở ngoài map.
- Thay đổi một `List` mutable hoặc trường của object bên ngoài.
- Ghi log, sửa file, cập nhật một map khác.

Ngay cả khi `ConcurrentHashMap` gọi callback đúng một lần cho invocation thích hợp, **callback vẫn có thể chạy lại ở invocation khác** nếu không tạo mapping, mapping bị xóa, hoặc ứng dụng gọi lại sau thất bại.

### 8.1. Side effect không được rollback

```text
1) Callback thực hiện externalSideEffect()
2) Callback gặp exception
3) Map giữ nguyên giá trị cũ hoặc không tạo mapping
4) Caller retry
5) externalSideEffect() chạy lần nữa
```

Sự thay đổi map là nguyên tử theo một key; tác dụng phụ ngoài map **không nằm trong transaction đó**.

### 8.2. Nếu callback trả null

`computeIfAbsent` trả `null` và không lưu mapping. Invocation sau đó với cùng key vẫn thấy absent và có thể gọi callback lại. Nếu callback gửi email rồi trả null, các lần gọi có thể gửi **nhiều email** mà map vẫn trống.

### 8.3. Nếu callback ném exception

`computeIfAbsent` không tạo mapping khi callback ném `RuntimeException`/`Error`. `compute`, `computeIfPresent` và `merge` giữ nguyên mapping hiện có khi remapping function ném exception. Điều đó không hoàn tác side effect đã xảy ra **ngoài map** trước lỗi.

### Ví dụ 4 — RetrySideEffectDemo.java

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class RetrySideEffectDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
            new ConcurrentHashMap<>();

        AtomicInteger attempts =
            new AtomicInteger();

        for (int i = 0; i < 2; i++) {
            map.computeIfAbsent("missing", key -> {
                attempts.incrementAndGet();
                return null;
            });
        }

        System.out.println("attempts=" +
            attempts.get());

        System.out.println("contains=" +
            map.containsKey("missing"));

        AtomicInteger notifications =
            new AtomicInteger();

        for (int i = 0; i < 2; i++) {
            try {
                map.computeIfAbsent("bad", key -> {
                    notifications.incrementAndGet();
                    throw new IllegalArgumentException(
                        "bad"
                    );
                });
            } catch (IllegalArgumentException ex) {
                System.out.println("error=" +
                    ex.getMessage());
            }
        }

        System.out.println("notifications=" +
            notifications.get());

        System.out.println("badPresent=" +
            map.containsKey("bad"));
    }
}
```

```bash
javac RetrySideEffectDemo.java
java RetrySideEffectDemo
```

Stdout:

```text
attempts=2
contains=false
error=bad
error=bad
notifications=2
badPresent=false
```

Những `AtomicInteger` trong ví dụ mô phỏng side effect để dễ thấy số lần. Sau hai invocation, side effect đã xảy ra hai lần, nhưng **không có mapping nào được lưu**.

Trong ứng dụng thật, thay `notifications.incrementAndGet()` bằng gửi thông báo hoặc trừ tiền có thể gây hậu quả nghiêm trọng. **Không đặt business action không idempotent trong remapping function** và đừng coi map như hệ thống giao dịch phân tán.

## 9. Recursion và cập nhật chính map: vi phạm contract

Callback của `computeIfAbsent`/`compute`/`computeIfPresent` không được cập nhật chính `ConcurrentHashMap` đang gọi. Các trường hợp nguy hiểm:

```java
// Phản ví dụ: recursive update trên cùng key.
map.computeIfAbsent("A", key ->
    map.computeIfAbsent("A", another -> "value")
);
```

```java
// Phản ví dụ: dù cập nhật key khác vẫn vi phạm contract.
map.compute("A", (key, oldValue) -> {
    map.put("B", "changed");
    return "new";
});
```

```java
// Phản ví dụ: gọi map.merge bên trong mapping function.
map.computeIfAbsent("A", key -> {
    map.merge("B", 1, Integer::sum);
    return 100;
});
```

**Không chỉ cần tránh chính key hiện tại.** Contract yêu cầu **không sửa map đó từ trong callback**; các cập nhật key khác cũng không được coi là phương án an toàn.

`IllegalStateException` có thể được ném khi `ConcurrentHashMap` **phát hiện** recursive update gây ra tình huống sẽ không kết thúc. Nhưng cơ chế phát hiện này là **best-effort**: không nên viết code sai rồi trông chờ exception luôn xuất hiện.

### 9.1. Truy cập map bên ngoài callback cũng cần thiết kế rõ

Nếu muốn đồng thời cập nhật `"A"` và `"B"`, không có phép `compute("A",...)` tự tạo transaction hai key. Hãy xác định yêu cầu:

- Nếu chỉ cần từng key nguyên tử: gọi hai operation **riêng biệt**, chấp nhận trạng thái trung gian.
- Nếu phải bảo đảm invariant xuyên hai key: thiết kế một state immutable duy nhất dưới một key, hoặc dùng synchronization/transaction ở tầng phù hợp.
- Nếu cần side effect bên ngoài: thực hiện **sau khi callback hoàn tất** và có cơ chế idempotency/retry thích hợp.

### Ví dụ 5 — RecursiveUpdateDemo.java

```java
import java.util.concurrent.ConcurrentHashMap;

public class RecursiveUpdateDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
            new ConcurrentHashMap<>();

        try {
            map.computeIfAbsent(
                "a",
                key -> map.computeIfAbsent(
                    "a", other -> 42
                )
            );

            System.out.println(
                "recursive=ACCEPTED"
            );
        } catch (IllegalStateException ex) {
            System.out.println(
                "recursive=REJECTED"
            );
        }

        System.out.println("contains=" +
            map.containsKey("a"));
    }
}
```

```bash
javac RecursiveUpdateDemo.java
java RecursiveUpdateDemo
```

Stdout trong JDK đã kiểm thử:

```text
recursive=REJECTED
contains=false
```

**Cảnh báo:** Đây là ví dụ **chủ ý vi phạm contract** để minh họa lỗi. Đừng phụ thuộc vào thông báo hoặc lớp exception này để làm đường xử lý bình thường trong production. Đặc biệt, recursion trên các khóa khác hoặc phụ thuộc nhiều khóa có thể tạo tình huống khó dự đoán mà detection không luôn bắt được.

## 10. Ngoại lệ, null và tính nhất quán của mapping

Nhớ bảng sau:

| Phương thức | Khi callback ném exception | Khi callback trả null |
| --- | --- | --- |
| `computeIfAbsent` | Không thêm mapping mới | Không thêm mapping mới |
| `computeIfPresent` | Mapping cũ không đổi | Xóa mapping đang có |
| `compute` | Mapping cũ không đổi | Xóa mapping nếu trước đó tồn tại |
| `merge` | Mapping cũ không đổi | Xóa mapping đang có nếu callback được gọi |

Trong mọi trường hợp, **side effect ngoài map trước exception không được rollback**.

`ConcurrentHashMap` cấm `null` là key/value. `merge(k, null, f)` sẽ ném `NullPointerException`; callback trả null khi được gọi lại có nghĩa **xóa mapping**, không phải ghi null. Nếu business cần biểu diễn “đã xử lý nhưng không có kết quả”, cân nhắc một value cụ thể như `Optional` hoặc một enum/record kết quả phù hợp, chứ không dựa vào `null` cho trường hợp đã cache.

### Ví dụ 6 — ExceptionSemanticsDemo.java

```java
import java.util.concurrent.ConcurrentHashMap;

public class ExceptionSemanticsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
            new ConcurrentHashMap<>();

        map.put("x", 7);

        try {
            map.compute("x", (k, v) -> {
                throw new IllegalStateException(
                    "failed"
                );
            });
        } catch (IllegalStateException ex) {
            System.out.println(
                "error=" + ex.getMessage()
            );
        }

        System.out.println("x=" + map.get("x"));

        System.out.println("deleted=" +
            map.computeIfPresent(
                "x", (k, v) -> null
            ));

        System.out.println("contains=" +
            map.containsKey("x"));

        System.out.println("merging=" +
            map.merge("y", 1, Integer::sum));

        System.out.println("sum=" +
            map.merge("y", 2, Integer::sum));
    }
}
```

```bash
javac ExceptionSemanticsDemo.java
java ExceptionSemanticsDemo
```

Stdout:

```text
error=failed
x=7
deleted=null
contains=false
merging=1
sum=3
```

Lỗi trong `compute` **không thay mapping `x`** đang có giá trị 7. Callback trả null trong `computeIfPresent` xóa khóa `x`. Với `merge`, khóa `y` absent nên chèn trực tiếp 1; invocation tiếp theo dùng callback `Integer::sum` cho ra 3.

**Không thiết kế callback dựa trên việc exception sẽ tự retry.** Chính ứng dụng quyết định retry theo chính sách, giới hạn số lần, phân loại lỗi và idempotency.

## 11. Callback thuần: nguyên tắc an toàn nhất

Một callback tốt thường có các đặc điểm:

1. **Chỉ phụ thuộc tham số** `key` và `oldValue` cùng những hằng số/bất biến cần thiết.
2. **Không sửa `ConcurrentHashMap` đang được tính**.
3. **Không chờ I/O** hoặc future.
4. **Không có side effect bên ngoài** cần exactly-once.
5. **Chi phí CPU/nhớ có giới hạn thực tế** theo input.
6. **Không tạo object mutable rồi chia sẻ không có đồng bộ**.
7. **Không bắt exception để tạo trạng thái giả** hoặc đổi lỗi âm thầm thành null.
8. **Trả một value hợp lệ**; hiểu rõ ý nghĩa null trong từng method.

Ví dụ tốt:

```java
// Đoạn minh họa: nguyên tử và chỉ tính tại bộ nhớ.
map.compute("quantity", (key, oldQty) -> {
    int current = oldQty == null ? 0 : oldQty;
    return Math.addExact(current, 1);
});
```

`Math.addExact` phát sinh exception khi overflow thay vì cho giá trị số bị tràn; phù hợp nếu business không cho phép đếm âm vì overflow.

### 11.1. “Không side effect” có nghĩa tuyệt đối?

Trong thực tế, callback có thể tạo object, ghi một metric nhẹ hoặc thực hiện logging đã được chấp nhận. Nhưng **phép cập nhật chính map không được phép**, còn những side effect bên ngoài nên **tránh tối đa** vì dễ bị retry, chặn hoặc làm rối tính bất biến.

Nếu cần đo performance, có thể lấy thời điểm trước/sau operation ở **ngoài callback** hoặc dùng profiler/JFR. Không nên đặt synchronized logger, network exporter hay writer chậm ngay trong remapping function.

## 12. LongAdder: pattern hiệu quả khi cập nhật bộ đếm theo key

Javadoc `ConcurrentHashMap` giới thiệu cách dùng `LongAdder` cho frequency map:

```java
// Đoạn minh họa.
frequencyMap
    .computeIfAbsent(key, k -> new LongAdder())
    .increment();
```

Vì sao hợp lý?

- Callback chỉ **tạo một LongAdder mới**, thường là việc nhỏ và không sửa map.
- `computeIfAbsent` bảo đảm map chỉ công bố một object `LongAdder` tại key khi absent.
- `increment()` xảy ra **sau khi computeIfAbsent đã trả về**, tức **ngoài callback**.
- `LongAdder` hỗ trợ nhiều luồng tăng một cách thread-safe, thường hữu ích với counter chịu tranh chấp.

**Nhưng:** `sum()` của `LongAdder` không tạo snapshot nguyên tử trong khi các thread còn tăng. Nếu cần một số liệu tuyệt đối nhất quán tại một điểm thời gian, phải thiết kế thêm cơ chế đồng bộ/quiescence hoặc một cấu trúc khác phù hợp.

### Ví dụ 7 — LongAdderDemo.java

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, LongAdder> freq =
            new ConcurrentHashMap<>();

        for (String word : Arrays.asList(
            "java", "java", "map", "java", "map"
        )) {
            freq.computeIfAbsent(
                word, k -> new LongAdder()
            ).increment();
        }

        System.out.println("java=" +
            freq.get("java").sum());

        System.out.println("map=" +
            freq.get("map").sum());

        System.out.println("size=" +
            freq.size());
    }
}
```

```bash
javac LongAdderDemo.java
java LongAdderDemo
```

Stdout:

```text
java=3
map=2
size=2
```

**Quan trọng về thread safety:** `ConcurrentHashMap` bảo vệ mapping trong map; nó **không tự bảo vệ mọi trường mutable** bên trong V. Cách này đúng vì bản thân `LongAdder` được thiết kế concurrent. Không thay `LongAdder` bằng một `int[]` hoặc `ArrayList` mutable rồi tăng không đồng bộ và nghĩ rằng map đã bảo đảm an toàn cho value đó.

## 13. I/O chậm: đặt ngoài callback như thế nào?

Khi cần load từ database hoặc HTTP, tránh:

```java
// Phản ví dụ.
UserProfile p = cache.computeIfAbsent(
    userId, id -> httpClient.fetchProfile(id)
);
```

Một phương án đơn giản nếu chấp nhận **có thể load trùng** dưới cạnh tranh:

```java
// Đoạn minh họa, giả định kiểu UserProfile, userId và client đã có.
UserProfile present = cache.get(userId);
if (present != null) {
    return present;
}

// Đặt I/O có timeout ngoài callback của map:
UserProfile loaded = client.fetchWithTimeout(userId);

// Chỉ công bố value khi còn absent:
UserProfile previous = cache.putIfAbsent(userId, loaded);

return previous != null ? previous : loaded;
```

**Trade-off:** Nhiều thread có thể cùng thấy absent và cùng gọi I/O. Điều đó **không làm hỏng map**, nhưng gây tải trùng. Nếu cần tránh load trùng, dùng **single-flight/in-flight future** theo key hoặc hệ thống cache chuyên dụng với hợp đồng loading/timeout rõ ràng.

### 13.1. Không biến putIfAbsent thành giao dịch giữa map và hệ thống ngoài

`putIfAbsent` nguyên tử khi ghi một key, nhưng **không rollback request HTTP** mà đã chạy trước đó. Nếu mỗi request HTTP là một hành động có tác dụng phụ, duplicate call vẫn là vấn đề. Một operation remote có side effect cần **idempotency key**, transaction/outbox hoặc cơ chế đảm bảo của dịch vụ đích.

### 13.2. Tránh ghi đè kết quả mới bằng dữ liệu cũ

Nếu trong lúc load chậm, một thread khác đã cập nhật cache bằng thông tin mới hơn, `cache.put(key, loadedOld)` có thể ghi đè dữ liệu mới. `putIfAbsent` chỉ phù hợp cho trường hợp muốn chèn khi absent.

Khi cache có **version** hoặc invariant state, sau khi tính toán/I/O ngoài callback, có thể dùng `replace(key, expectedOld, newValue)` hoặc `compute` với callback **chỉ kiểm tra và công bố kết quả nhanh**. Phải thiết kế giải quyết stale result, ABA/version và retry theo nhu cầu. Không tự coi `compute` dài là phương án đúng để giữ kết quả remote.

## 14. Single-flight bằng CompletableFuture: công việc chậm chạy ở ngoài map

Một cách tránh nhiều request đồng thời cùng load một key là map lưu **future của công việc đang chạy**, thay vì bắt callback `computeIfAbsent` làm chính I/O.

Ý tưởng:

```text
Caller A: putIfAbsent("A", futureA)
     |            |
     |          thắng
     |            |
     |       schedule I/O ngoài map
     |
Caller B: putIfAbsent("A", futureB)
                  |
                thua
                  |
             nhận futureA
                  |
        cả hai cùng chờ futureA
```

Lợi ích: cập nhật map rất ngắn. Phần I/O bất đồng bộ không chạy trong callback `compute` hoặc dưới trạng thái đồng bộ của map.

### Ví dụ 8 — SingleFlightDemo.java

Tạo file:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SingleFlightDemo {
    static CompletableFuture<String> getOrLoad(
        String key,
        ConcurrentHashMap<
            String, CompletableFuture<String>> inFlight,
        ExecutorService pool,
        CountDownLatch gate,
        AtomicInteger loads
    ) {
        CompletableFuture<String> candidate =
            new CompletableFuture<>();

        CompletableFuture<String> prior =
            inFlight.putIfAbsent(key, candidate);

        if (prior != null) {
            return prior;
        }

        // Chỉ thread thắng mới schedule việc chậm.
        // Không thực hiện I/O trong callback của map.
        try {
            pool.execute(() -> {
                try {
                    // Gate chỉ để demo giữ job chưa xong.
                    if (!gate.await(3, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "gate"
                        );
                    }

                    loads.incrementAndGet();
                    candidate.complete("value-" + key);
                } catch (Throwable ex) {
                    candidate.completeExceptionally(ex);
                } finally {
                    // Chỉ xóa nếu mapping vẫn là future này.
                    inFlight.remove(key, candidate);
                }
            });
        } catch (RejectedExecutionException ex) {
            candidate.completeExceptionally(ex);
            inFlight.remove(key, candidate);
        }

        return candidate;
    }

    public static void main(String[] args)
            throws Exception {
        ConcurrentHashMap<
            String, CompletableFuture<String>> inFlight =
            new ConcurrentHashMap<>();

        ExecutorService pool =
            Executors.newSingleThreadExecutor();

        CountDownLatch gate =
            new CountDownLatch(1);

        AtomicInteger loads =
            new AtomicInteger();

        try {
            CompletableFuture<String> a =
                getOrLoad(
                    "A", inFlight, pool, gate, loads
                );

            CompletableFuture<String> b =
                getOrLoad(
                    "A", inFlight, pool, gate, loads
                );

            System.out.println("sameFuture=" +
                (a == b));

            gate.countDown();

            System.out.println("result=" +
                a.get(3, TimeUnit.SECONDS));

            System.out.println("loads=" +
                loads.get());
        } finally {
            gate.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac SingleFlightDemo.java
java SingleFlightDemo
```

Stdout đã kiểm thử:

```text
sameFuture=true
result=value-A
loads=1
```

**Diễn giải:** Hai yêu cầu cùng key được nối vào cùng future `a`/`b` trong lúc việc đang chạy, nên chỉ một load được schedule. `putIfAbsent` kết thúc nhanh và không giữ callback map trong lúc chờ gate.

**Giới hạn quan trọng của ví dụ:**

1. Đây là **single-flight cho tác vụ đang diễn ra**, **không phải cache thành công lâu dài**. Sau khi task hoàn tất, `inFlight.remove(key,candidate)` có thể cho phép một request mới bắt đầu load lại.
2. `remove(key,candidate)` là xóa có điều kiện, tránh xóa nhầm future mới của cùng key nếu mapping đã đổi.
3. Nếu task gặp lỗi, future được complete exceptionally; cleanup giúp invocation sau có thể thử lại. Nhưng retry phải có backoff và giới hạn tùy yêu cầu.
4. Các caller đang cầm future hoàn tất vẫn nhận kết quả/exception của lần ấy, dù entry trong map đã bị xóa.
5. Timeout ở `a.get(...)` **chỉ giới hạn chờ ở caller**. Muốn kiểm soát hoạt động HTTP thật, phải cấu hình timeout trong HTTP/database client và quản lý việc cancel/circuit breaker ở ngoài map.
6. `CompletableFuture.complete` có thể kích hoạt dependent actions; trong hệ thống thực tế cần xét executor và độ nặng của các handler, không để side effect callback khác chạy nhầm trong một vùng đồng bộ quan trọng.
7. Demo cố tình dùng latch để bảo đảm hai yêu cầu cùng tham gia **trước khi load hoàn tất**, không phải pattern production.

Với những bài toán cache phức tạp như TTL, refresh, deduplication xuyên nhiều instance, giới hạn bộ nhớ và thống kê, một cache library được bảo trì có thể phù hợp hơn việc tự triển khai toàn bộ chính sách qua `ConcurrentHashMap`.

## 15. Tránh deadlock do lock-order và phụ thuộc chéo

Ngoài đệ quy trực tiếp, callback có thể tạo deadlock nếu chờ một khóa hoặc kết quả cần được một thread khác công bố nhưng thread ấy đang chờ update map. Ví dụ về thứ tự khóa có thể gây nguy hiểm:

```text
Thread A:
  map.compute("A", callback)
    -> chờ externalLock

Thread B:
  giữ externalLock
    -> chờ update của map đối với key A
```

Nếu A giữ trạng thái đồng bộ nội bộ trong khi chờ khóa ngoài và B giữ khóa ngoài trong lúc chờ A, hai thread có thể kẹt.

Không cần mã phụ thuộc vào cách cài đặt bin/lock của một phiên bản JDK để nhận ra nguy cơ: nguyên tắc là **đừng block chờ resource khác trong remapping function** và **đừng thực hiện cập nhật lồng nhau trên cùng map**.

Nếu ứng dụng có nhiều resource bắt buộc cập nhật nguyên tử cùng nhau, cần thiết kế lock ordering/transaction riêng. `ConcurrentHashMap.compute` chỉ là công cụ cập nhật mapping theo key, **không phải hệ thống transaction nhiều resource**.

## 16. Giới hạn thời gian: thiết kế, đo và kiểm soát

Không có một ngưỡng toàn cầu như “mọi callback phải dưới 1 ms” được Java API bảo đảm. “Ngắn gọn” là quy tắc kỹ thuật: cần xem workload, quy mô map, tần suất cập nhật, phân phối key và yêu cầu latency.

Những biện pháp phù hợp:

- **Đo latency operation** trước/sau `map.compute(...)` bên ngoài callback.
- Quan sát percentile (p50, p95, p99), đỉnh chờ, throughput dưới hot-key contention.
- Theo dõi CPU và allocation của phép tính; tránh tạo object rất lớn trong callback.
- Dùng thread dump/JFR để phát hiện thread chờ và lock contention khi có sự cố.
- Test các key “hot” được nhiều luồng cập nhật, không chỉ key phân tán.
- Khi callback cần phép tính lớn, tính trước ngoài map rồi **chỉ xác thực/publish nhanh** trong callback, với cơ chế chống stale data.
- Khi I/O có deadline, đặt timeout thật ở client/database, quản lý cancellation và retry ở tầng I/O.
- Với side effect không idempotent, sử dụng idempotency keys, outbox/transaction hoặc cơ chế nghiệp vụ tương ứng.

**Không nên đọc latency của `get` rồi kết luận `compute` cũng nhanh như vậy.** `get` và cập nhật/remapping có đặc điểm đồng bộ khác nhau. Benchmarks phải phản ánh tần suất key trùng nhau và phân phối công việc thật, không chỉ một microbenchmark đơn luồng.

## 17. Không làm mutable value trở nên thread-safe chỉ nhờ map

Đây là một ngộ nhận phổ biến:

```java
// Phản ví dụ khi nhiều thread cập nhật cùng danh sách.
ConcurrentHashMap<String, ArrayList<String>> map =
    new ConcurrentHashMap<>();

map.computeIfAbsent(
    "events", k -> new ArrayList<>()
).add("newEvent");
```

Việc thêm `ArrayList` vào map là atomic ở bước xây mapping, **nhưng `ArrayList.add` sau đó không được map tự đồng bộ**. Các thread có thể cùng sửa list và gây race.

Các lựa chọn:

- Dùng một value immutable, cập nhật atomically bằng `map.compute(key, (k,old)->newImmutableValue)`.
- Dùng cấu trúc value thread-safe phù hợp với bài toán, ví dụ `LongAdder` cho counter.
- Dùng queue/collection concurrent khi yêu cầu bảo đảm của nó phù hợp.
- Với invariant của nhiều field bên trong value, thiết kế synchronization/transaction ở tầng value hoặc dùng immutable snapshot.

**Phân biệt:** Callback không có side effect trên map ≠ tất cả thao tác với object được trả về đều tự động atomic.

## 18. Một số anti-pattern tinh vi

### 18.1. Gửi message trong compute rồi cho rằng không bao giờ gửi trùng

`computeIfAbsent` chỉ bảo đảm một callback cho invocation khi key absent; nếu callback ném exception hoặc null, invocation sau có thể chạy lại. Gửi message là side effect ngoài map, không được rollback.

### 18.2. Gọi `map.compute` để “khóa” mọi trạng thái của map

`compute` chỉ atomic cho mapping mục tiêu, không tạo transaction xuyên mọi key. Các thread có thể quan sát những cập nhật ở các key khác tại những thời điểm khác nhau.

### 18.3. Tạo timeout ở caller và tin callback đã kết thúc

`Future.get(timeout)` có thể timeout trong khi task thật vẫn chạy. Thay đổi resource phía ngoài có thể tiếp tục xảy ra, và trạng thái cập nhật map còn phụ thuộc việc callback hoàn thành.

### 18.4. Gọi lại cùng map trong callback để “đảm bảo nhất quán”

Vi phạm contract; có thể bị phát hiện và ném `IllegalStateException` hoặc gặp rủi ro chờ vô hạn/phụ thuộc chéo.

### 18.5. Đếm side effect theo số callback và gọi đó là exactly-once

Exactly once **per eligible invocation** của một implementation cụ thể không đồng nghĩa exactly-once trên toàn ứng dụng, qua retry, crash, failover hoặc nhiều node.

### 18.6. Dùng callback I/O chậm vì “chỉ một thread load”

Có thể giới hạn duplicated load cho một key, nhưng đánh đổi bằng contention và latency cao trong map. Với việc chậm/remote, dùng single-flight future hoặc cache loader tách phần scheduling khỏi critical section.

### 18.7. Dùng `ConcurrentMap` interface để khẳng định callback không bị retry

Phải biết implementation cụ thể; các default method của interface có thể thử lại khi cạnh tranh.

### 18.8. Trả null như thể lưu “không có dữ liệu”

`ConcurrentHashMap` không lưu null values. `computeIfAbsent` trả null để lại khóa absent, nên lần sau tiếp tục tính lại.

### 18.9. Coi exception tự rollback cả email/DB

Chỉ mapping trong map có contract giữ nguyên/không tạo khi callback ném exception. I/O đã thực hiện bên ngoài có thể không thể rollback.

### 18.10. Dùng logging đồng bộ bên trong hot callback

Logger có thể block vì disk/network hoặc khóa khác, kéo dài critical section; thu thập metric/trace ở ngoài callback khi có thể.

### 18.11. Dùng `Map.get` rồi `Map.put` để tăng một counter

Không nguyên tử; có thể mất update dưới cạnh tranh.

### 18.12. Dùng `LongAdder.sum` như snapshot nguyên tử ngay khi đang tăng

`sum` thích hợp cho đo đạc thống kê; trong điều kiện cập nhật đồng thời nó không phải snapshot transaction.

### 18.13. Chia sẻ `ArrayList` trong V rồi nghĩ CHM bảo vệ list

CHM bảo vệ mapping; các object mutable bên trong cần thread-safety riêng.

### 18.14. Dùng `compute` để công bố kết quả I/O cũ mà không kiểm tra version

Trong lúc I/O chạy, state có thể thay đổi. Khi công bố phải có điều kiện (ví dụ CAS/replace/compute ngắn với expected version) nếu business cần chống overwrite stale data.

### 18.15. Gắn side effect vào `merge` vì nghĩ callback luôn chạy

Khi key absent, `merge` chèn value trực tiếp và không gọi remapping function. Logic business đặt trong callback có thể bị **bỏ qua hoàn toàn** ở nhánh absent.

### 18.16. Bắt `IllegalStateException` rồi coi recursion hợp lệ

Exception là dấu hiệu code vi phạm contract; implementation chỉ phát hiện được một số trường hợp. Cần sửa thiết kế, không dùng exception như điều khiển luồng.

## 19. Quyết định nên dùng API nào?

| Mục tiêu | Cách phù hợp | Cần tránh |
| --- | --- | --- |
| Tạo value nhanh khi key absent | `computeIfAbsent` với constructor ngắn | HTTP/DB call trong callback |
| Cập nhật một counter theo key | `compute` thuần hoặc `LongAdder` | `get` + `put` |
| Gộp hai số theo key | `merge(k, delta, Integer::sum)` | Side effect trong remapping |
| Chỉ cập nhật khi key present | `computeIfPresent` | Giả định callback chạy khi absent |
| Khởi tạo mutable concurrent counter | `computeIfAbsent(k,new LongAdder()).increment()` | `ArrayList`/`int[]` sửa không đồng bộ |
| Load remote có thể trùng | I/O ngoài map + `putIfAbsent` | Giữ critical section trong lúc chờ mạng |
| Load remote dedupe trong một JVM | In-flight `CompletableFuture` + `putIfAbsent` | Sleep/await trong compute callback |
| Update nhiều key với invariant chung | Mô hình state/lock/transaction rõ | Xem compute một key như transaction nhiều key |
| Gửi email/thanh toán exactly-once | Idempotency/transaction/outbox | Coi callback map là nguồn bảo đảm exactly-once |
| Giới hạn thời gian gọi HTTP | Timeout ở HTTP client / circuit breaker | Chỉ dựa vào `Future.get(timeout)` quanh compute |

**Ghi chú:** Dòng `computeIfAbsent(k,new LongAdder()).increment()` trong bảng là ý tưởng viết tắt, không phải cú pháp Java đầy đủ. Cú pháp đúng là `computeIfAbsent(k, key -> new LongAdder()).increment()`.

## 20. Checklist production

Trước khi đưa một `ConcurrentHashMap.compute*` hoặc `merge` vào luồng hot, hãy kiểm tra:

1. Mapping/remapping function có thực hiện I/O, sleep, await, join, lock ngoài không?
2. Callback có cập nhật chính map (bất kỳ key nào) hay gọi recursive compute không?
3. Chi phí CPU/nhớ có giới hạn hợp lý theo input và tải production không?
4. Có side effect như email, DB write, event publish, metric chậm hoặc mutable object shared không?
5. Nếu callback trả null, application có chấp nhận key vẫn absent/bị xóa không?
6. Nếu callback ném exception, map state và side effect bên ngoài sẽ ra sao?
7. Với `merge`, nhánh key absent không gọi callback đã được xử lý chưa?
8. Logic có hiểu “per invocation” thay vì “globally exactly once” không?
9. Nếu chỉ có một interface `Map`/`ConcurrentMap`, có kiểm tra implementation thực tế không?
10. Nếu cập nhật counter, đã tránh `get` + `put` race?
11. Nếu giữ mutable value, value có thread-safety thích hợp không?
12. Nếu dùng `LongAdder`, có hiểu `sum` không phải atomic snapshot khi đang có write không?
13. I/O chậm đã được tách khỏi critical section của map chưa?
14. Timeout ở client, deadline ở caller, cancellation và retry được phân biệt rõ chưa?
15. Có giới hạn số task/queue/executor để tránh tạo quá nhiều load async không?
16. Với single-flight, thành công có cần cache lâu dài không, và lỗi được cleanup/retry thế nào?
17. Có tránh xóa future mới bằng thao tác `remove(key, oldFuture)` có điều kiện không?
18. Có bảo vệ dữ liệu mới khỏi kết quả I/O cũ bằng version/CAS khi cần không?
19. Có test hot-key contention và thread dumps/JFR khi nghi latency không?
20. Có test callback throw/null, recursive update, merge absent và side effects lặp không?
21. Có bảo vệ bí mật/dữ liệu cá nhân khi log lỗi từ callback không?
22. Có xác định transaction/idempotency cho nghiệp vụ xuyên map/DB/service không?

## 21. Câu hỏi ôn tập

**Câu 1.** `ConcurrentHashMap.computeIfAbsent` có giới hạn timeout sẵn không?

**Đáp án:** Không. Callback nên ngắn và đơn giản; deadline của I/O/caller phải được thiết kế bên ngoài map.

**Câu 2.** Callback `computeIfAbsent` có được cập nhật key khác trong chính map không?

**Đáp án:** Không. Contract cấm callback sửa chính map trong lúc tính.

**Câu 3.** `computeIfAbsent` có gọi callback nếu key đã có mapping không?

**Đáp án:** Không.

**Câu 4.** “Đúng một lần mỗi invocation” có nghĩa external email chỉ gửi đúng một lần toàn hệ thống không?

**Đáp án:** Không. Một invocation khác có thể gọi lại callback, và email không nằm trong transaction của map.

**Câu 5.** Callback `computeIfAbsent` trả null thì điều gì xảy ra?

**Đáp án:** Không thêm mapping. Invocation sau có thể tiếp tục gọi callback.

**Câu 6.** Callback `compute` ném RuntimeException thì mapping cũ thế nào?

**Đáp án:** Vẫn giữ nguyên theo contract của `ConcurrentHashMap`; side effect ngoài map không tự rollback.

**Câu 7.** `merge` có gọi remapping function khi key absent không?

**Đáp án:** Không; nó chèn value non-null được cung cấp.

**Câu 8.** `compute("k", (k,v)->v==null?1:v+1)` và `get` rồi `put` khác nhau ở đâu?

**Đáp án:** `compute` cập nhật nguyên tử theo key; `get` + `put` có lost update khi nhiều thread cạnh tranh.

**Câu 9.** Vì sao `LongAdder` thường được tạo trong `computeIfAbsent` rồi gọi `increment` bên ngoài?

**Đáp án:** Khởi tạo mapping nhanh và nguyên tử; object `LongAdder` tự hỗ trợ concurrent increments.

**Câu 10.** `ConcurrentHashMap<String,ArrayList<String>>` có làm `ArrayList.add` thread-safe không?

**Đáp án:** Không. Map chỉ bảo vệ mapping; list mutable cần đồng bộ riêng.

**Câu 11.** Nếu một `Future.get(100ms)` timeout, callback `compute` trong task đã bị hủy chưa?

**Đáp án:** Không nhất thiết; task có thể tiếp tục chạy. Ngay cả cancel(true) cũng không bảo đảm side effect được rollback.

**Câu 12.** Khi callback gọi recursive compute trên cùng map, có luôn nhận `IllegalStateException` không?

**Đáp án:** Không bảo đảm; phát hiện là best-effort. Dù có ném exception, đó vẫn là code vi phạm contract.

**Câu 13.** Dùng `putIfAbsent` sau khi load HTTP ngoài map có rủi ro gì?

**Đáp án:** Nhiều request có thể cùng load trước khi chỉ một value được chèn. Nếu load có side effect, cần idempotency/dedupe khác.

**Câu 14.** In-flight future khác cache kết quả lâu dài thế nào?

**Đáp án:** In-flight giữ **các công việc đang chạy**; sau khi xong có thể xóa entry. Cache giữ kết quả cho lần truy cập về sau theo TTL/invalidation.

**Câu 15.** Vì sao callback CPU nặng dù không chờ I/O vẫn cần tránh?

**Đáp án:** Có thể kéo dài thời gian tranh chấp map và làm tăng latency cho các cập nhật khác.

**Câu 16.** Có thể dùng một compute trên key A để làm transaction nguyên tử của A và B không?

**Đáp án:** Không. Atomicity của ConcurrentHashMap không bao phủ invariant đa key.

**Câu 17.** Khi `LongAdder.sum()` chạy đồng thời với increments, số liệu có là snapshot nguyên tử không?

**Đáp án:** Không, sum không cam kết snapshot nguyên tử trong lúc có update.

**Câu 18.** Khi load dữ liệu bên ngoài mất thời gian, làm sao không ghi đè state mới?

**Đáp án:** Công bố bằng `putIfAbsent` khi chỉ cho phép chèn absent, hoặc dùng version/CAS/`replace` hay `compute` ngắn để xác nhận state trước khi cập nhật.

## 22. Tài liệu chính thức, vẫn áp dụng

- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): các hợp đồng `computeIfAbsent`, `computeIfPresent`, `compute`, `merge`, atomicity, cảnh báo callback ngắn, recursive update và LongAdder.
- [Oracle Java SE 27 — Map](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): ngữ nghĩa `compute*`/`merge` của Map interface và điều kiện default implementations.
- [Oracle Java SE 26 — ConcurrentMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): contract và các default implementation concurrent có thể retry callback.
- [Oracle Java SE 26 — LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter phân tán cập nhật, đặc tính của `sum()`.
- [Oracle Java SE 26 — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): async completion, exceptional completion và phối hợp task.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)` và `cancel`, giới hạn cancellation.
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): thực thi/cấp phát thread và quản lý vòng đời executor.

**Kết luận:** Với `ConcurrentHashMap`, các hàm `computeIfAbsent`, `computeIfPresent`, `compute` và `merge` phù hợp cho phép tính **ngắn, trong bộ nhớ, không cập nhật lại chính map và không có side effect nghiệp vụ cần exactly-once**. Atomicity của một mapping không bao trùm HTTP/DB/email; timeout của caller không tự hủy callback. Khi cần I/O chậm, tách công việc ra ngoài map, dùng `putIfAbsent`/single-flight future và chính sách deadline, retry, idempotency, stale-result rõ ràng.