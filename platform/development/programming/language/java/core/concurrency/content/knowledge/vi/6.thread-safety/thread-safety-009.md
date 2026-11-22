# Thread-safe collection và compound action chưa atomic trong Java

## Mục tiêu và phạm vi

Một collection được quảng bá là **thread-safe** không có nghĩa **mọi đoạn chương trình sử dụng collection đó đều atomic**. Hai lời gọi phương thức an toàn nếu xét riêng vẫn có thể bị một thread khác chen vào giữa. Vì thế, một chuỗi gồm “kiểm tra rồi thay đổi”, “đọc rồi tăng”, “đếm rồi truy cập”, hay “cập nhật hai key liên quan” có thể vi phạm bất biến nghiệp vụ dù collection không bị hỏng cấu trúc nội bộ.

Bài này tập trung vào **Java concurrency nói chung**: `Collections.synchronizedList/Map`, `ConcurrentHashMap`, `ConcurrentLinkedQueue`, `BlockingQueue`, `CopyOnWriteArrayList`, khóa ngoài và snapshot immutable. Không dùng API, annotation hoặc cấu hình riêng của Spring vì phần đó được học trong chương Spring khác.

Sau bài, bạn có thể:
- Diễn giải chính xác **thread safety**, **atomicity**, **visibility**, **compound action** và **linearization point** khi thao tác trên collection.
- Phân biệt “một method thread-safe” với “một chuỗi nhiều method là transaction”.
- Tìm và sửa lỗi `containsKey` → `put`, `get` → `put`, `isEmpty` → `remove/take`, `size` → `get` và iteration đồng thời.
- Chọn đúng API nguyên tử như `putIfAbsent`, `compute`, `merge`, `remove(key,value)`, `replace(key,old,new)`, `poll` hoặc bảo vệ trọn compound action bằng cùng lock.
- Biết vì sao **atomic theo một key** không đồng nghĩa **atomic trên nhiều key**, và vì sao iterator **weakly consistent** hoặc **snapshot** không phải giao dịch nhất quán toàn collection.
- Chạy ví dụ **Java 17+** với stdout được kiểm soát để thấy race xảy ra và cách sửa.

## 1. “Thread-safe” đang bảo đảm điều gì?

Trong Java, các collection thread-safe được thiết kế để **nhiều thread có thể truy cập theo một hợp đồng concurrency đã định** mà không vi phạm các bảo đảm của cấu trúc dữ liệu. Nhưng hợp đồng khác nhau tùy loại collection và từng phương thức:

| Collection / wrapper | Tính chất cốt lõi | Giới hạn cần hiểu |
| --- | --- | --- |
| `Collections.synchronizedList(...)` | Đồng bộ nhiều thao tác trên một monitor của wrapper | Vòng lặp và chuỗi nhiều lời gọi thường cần tự `synchronized(list)` trên wrapper |
| `Collections.synchronizedMap(...)` | Bảo vệ các thao tác theo hợp đồng wrapper | `get` rồi `put` là hai thao tác riêng nếu không khóa ngoài toàn chuỗi |
| `ConcurrentHashMap<K,V>` | Cho phép nhiều thao tác đồng thời; hỗ trợ update atomic **theo key** | Không tự biến cập nhật nhiều key thành transaction; iteration không phải snapshot cố định |
| `ConcurrentLinkedQueue<E>` | Queue không khóa theo thuật toán phù hợp concurrency; `poll` lấy một phần tử nếu có theo một thao tác | `isEmpty` → `poll` và `peek` → `poll` không là một thao tác nguyên tử |
| `BlockingQueue<E>` | `put/take/offer/poll` phối hợp producer–consumer, có semantics chờ/timeout | Kiểm tra `size/isEmpty` rồi `take` không khóa tình trạng queue ở thời điểm kiểm tra |
| `CopyOnWriteArrayList<E>` | Tạo bản sao mảng khi cập nhật, iterator là snapshot | Iterator không phản ánh cập nhật sau khi được tạo; mỗi lần sửa có chi phí copy |
| `List.of` / `List.copyOf` | Danh sách không cho sửa cấu trúc sau khi tạo | Các object mutable **bên trong** có thể vẫn thay đổi; cần safe publication thích hợp |

Không có câu khẳng định chung nào rằng “mọi phép gọi trên mọi thread-safe collection đều là linearizable transaction” nếu chưa xét **contract của phương thức và phạm vi dữ liệu**. Tương tự, `Collections.synchronizedList` và `ConcurrentHashMap` đều an toàn theo mục đích thiết kế nhưng chúng **khác nhau về khóa, cách iteration và atomic API**.

### Một phép thao tác và một bất biến

Giả sử map lưu số lượt truy cập:

~~~java
Integer old = visits.get("home");
visits.put("home", old + 1);
~~~

Ngay cả khi `visits.get` và `visits.put` đều được đồng bộ riêng lẻ, phép **“tăng đúng một đơn vị”** chưa được bảo đảm. Hai thread có thể cùng đọc 0 rồi cùng ghi 1. Collection vẫn toàn vẹn, nhưng **kết quả nghiệp vụ sai**.

**Bất biến (invariant)** là điều kiện phải đúng sau một thao tác nghiệp vụ; ví dụ: “sau N lần tăng thành công, counter tăng đúng N”, “một job chỉ được một worker claim”, hoặc “tổng tiền giữa hai tài khoản không đổi”. Muốn sửa compound action, phải xác định **toàn bộ các bước cần bảo vệ để giữ invariant**.

## 2. Atomicity khác visibility và thread-safe method

Hình dung hai thread cùng chạy:

~~~text
Thread A                       Thread B
--------                       --------
old = map.get("count")  -> 0
                               old = map.get("count") -> 0
map.put("count", 1)
                               map.put("count", 1)

Hai lần get an toàn; hai lần put an toàn.
Kết quả sau hai lần cộng có thể vẫn là 1.
~~~

Trong Java Memory Model:

- **Visibility:** thay đổi do một thread tạo ra có được thread khác quan sát đúng theo một quan hệ happens-before hay không.
- **Atomicity:** các bước của một thao tác logic có thể bị xen giữa không; có một thời điểm quan sát mà toàn bộ thao tác đã có hiệu lực hay không.
- **Ordering:** những hành động nào được đặt trước/sau theo hợp đồng đồng bộ, không phụ thuộc đơn thuần thứ tự dòng code của các thread.
- **Linearization point:** thời điểm tưởng tượng mỗi thao tác atomic có hiệu lực như một thao tác đơn lẻ, giúp suy luận thứ tự các thao tác cạnh tranh.

Một thao tác `get` có thể hoàn toàn thread-safe và nhìn thấy giá trị mới nhất theo hợp đồng của collection, nhưng **sau khi `get` trả về**, một thread khác vẫn có quyền thay đổi collection. Do đó, kết quả kiểm tra ở `t1` không tự còn đúng khi thread thực hiện hành động ở `t2`.

**Điểm quan trọng:** nếu cần tính đúng đắn cho cả chuỗi, hãy dùng **một compound API được bảo đảm atomic**, hoặc **một lock/giao thức ownership bảo vệ tất cả các bước**. Chỉ chọn collection thread-safe mà không đổi đoạn code check-then-act là chưa đủ.

## 3. Ví dụ xác định: synchronizedMap vẫn có lost update

`Collections.synchronizedMap` cung cấp wrapper đồng bộ cho các thao tác theo contract, nhưng đoạn `get` rồi `put` gọi tách rời vẫn có một khoảng trống. Ví dụ sau cố tình buộc cả hai thread **đọc trước khi thread nào ghi** để lỗi không phụ thuộc may rủi scheduler.

Tạo file **`SynchronizedMapRaceDemo.java`**:

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;

public class SynchronizedMapRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("views", 0);

        CountDownLatch readByBoth = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increase = () -> {
            int old = counts.get("views");
            readByBoth.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counts.put("views", old + 1);
        };

        Thread first = new Thread(increase, "writer-1");
        Thread second = new Thread(increase, "writer-2");
        first.start();
        second.start();

        readByBoth.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("expected=2 actual=" + counts.get("views"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac SynchronizedMapRaceDemo.java
java SynchronizedMapRaceDemo
~~~

Stdout nếu các thread hoàn thành bình thường:

~~~text
expected=2 actual=1
~~~

Tại sao kết quả xác định là 1?
1. Map ban đầu lưu `"views" -> 0`.
2. Cả hai thread gọi `get` và nhận 0 trước khi được mở latch `allowWrite`.
3. Mỗi thread tính `0 + 1` rồi gọi `put`; hai thao tác ghi riêng có thể hợp lệ nhưng đều đặt giá trị 1.
4. `join` khiến main chờ cả hai hoàn tất trước khi đọc và in kết quả.

Đây là **race ở cấp thao tác nghiệp vụ**, không phải bằng chứng wrapper `synchronizedMap` hỏng cấu trúc. Latch chỉ phục vụ tái hiện sai lầm; code production không dùng latch theo cách này để “sửa” counter.

## 4. Giải pháp A: khóa toàn bộ compound action

### 4.1. Một lock cho cả đọc và sửa

Với `Collections.synchronizedMap`, có thể dùng monitor của chính wrapper:

~~~java
Map<String, Integer> counts =
        java.util.Collections.synchronizedMap(new java.util.HashMap<>());

synchronized (counts) {
    counts.put("views", counts.getOrDefault("views", 0) + 1);
}
~~~

Đây là **đoạn mã minh họa trong một method**; biến `counts` cần được chia sẻ đúng nơi. Vì wrapper đồng bộ trên monitor của nó cho các method được bảo vệ, khối `synchronized(counts)` bao cả chuỗi kiểm tra–cập nhật. Khi thread khác cũng sử dụng wrapper theo contract, nó không thể xen vào giữa chuỗi này bằng các thao tác được đồng bộ trên cùng monitor.

Nếu dùng wrapper `Collections.synchronizedMap(backing)`, **không tiếp tục cho các thread khác truy cập trực tiếp `backing`**: họ có thể vượt qua wrapper và phá toàn bộ giao thức. Nếu nhiều đường truy cập dùng lock khác nhau, chúng cũng không phối hợp.

### 4.2. Vòng lặp synchronizedList cần cùng monitor

Một hiểu lầm khác: mọi method của `Collections.synchronizedList` được đồng bộ, nên vòng `for-each` cũng tự an toàn. Thực tế iterator thường được tạo rồi sử dụng qua nhiều bước. Một thread khác có thể sửa list giữa lúc iterator đang duyệt.

~~~java
List<String> names =
        java.util.Collections.synchronizedList(new java.util.ArrayList<>());

names.add("An");
names.add("Bình");

synchronized (names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Đây là đoạn code trong một method, không phải một chương trình độc lập. **Khóa trên chính wrapper `names`** trong toàn bộ iteration, miễn tất cả thread cùng dùng wrapper đó cho các thao tác cạnh tranh. Tương tự, nếu gọi `Iterator`/`Spliterator`/`Stream` trên wrapper, cần tuân theo tài liệu đồng bộ của collection và giữ lock phù hợp khi đang duyệt.

**Không dựa vào `ConcurrentModificationException` để “phát hiện” hoặc ngăn race.** Với các collection dùng fail-fast iterator, exception là cơ chế best-effort báo lỗi sử dụng, không phải hàng rào đồng bộ; việc *không* ném exception không có nghĩa vòng duyệt an toàn.

### 4.3. Check-then-act trên list

Sai khi concurrent removal vẫn có thể xảy ra:

~~~java
if (names.size() > 0) {
    String first = names.get(0);
}
~~~

Ngay sau `size() > 0`, một thread khác có thể xóa phần tử đầu. Dù `size()` và `get(0)` đều được đồng bộ riêng, `get(0)` có thể ném `IndexOutOfBoundsException`.

Cách sửa khi muốn đọc phần tử đầu theo snapshot hợp lệ:

~~~java
synchronized (names) {
    if (!names.isEmpty()) {
        String first = names.get(0);
        System.out.println(first);
    }
}
~~~

Nếu nghiệp vụ thực sự cần **lấy phần tử ra để không ai lấy trùng**, tốt hơn là chọn API queue `poll()` atomic (phần tiếp theo) thay vì tự ghép `isEmpty` + `remove(0)`.

### 4.4. Khóa đúng phạm vi invariant

Một monitor chung giúp bảo vệ cả các bước đọc/ghi, nhưng phạm vi quá rộng có thể gây contention. Không nên giữ lock trong lúc gọi network I/O, callback không kiểm soát, hoặc xử lý lâu nếu bất biến không cần. Ngược lại, thu nhỏ lock đến mức **đánh mất tính nguyên tử** lại làm race xuất hiện.

Cách kiểm tra một giải pháp khóa:
- **Tất cả** writer và reader quan trọng có dùng **cùng lock** không?
- Critical section có bao trọn check và update không?
- Có đường truy cập trực tiếp backing collection vượt lock không?
- Có ngoại lệ làm lock không được nhả (với `ReentrantLock` cần `unlock()` trong `finally`)?
- Có nhiều lock được lấy theo thứ tự khác nhau dẫn đến deadlock không?

## 5. Giải pháp B: dùng compound operation nguyên tử theo đúng contract

Đối với `ConcurrentHashMap`, một số thao tác gom cả check/update thành một lời gọi có semantics atomic theo key. Ví dụ:

| Nhu cầu | Mẫu dễ sai | Phương thức phù hợp |
| --- | --- | --- |
| Chỉ đặt giá trị khi key chưa tồn tại | `if (!containsKey(k)) put(k,v)` | `putIfAbsent(k,v)` |
| Tăng giá trị gắn với một key | `put(k, get(k)+1)` | `compute(k, fn)` hoặc `merge(k, 1, Integer::sum)` |
| Xóa key nếu giá trị vẫn là bản đã quan sát | `if (get(k).equals(v)) remove(k)` | `remove(k,v)` |
| Đổi giá trị nếu vẫn bằng giá trị cũ | `if (get(k).equals(old)) put(k,next)` | `replace(k, old, next)` |
| Tạo value cho key thiếu | `if (get(k)==null) put(k, factory())` | `computeIfAbsent(k, factory)` khi contract phù hợp |

Trong `ConcurrentHashMap`, khóa/thuật toán nội bộ hỗ trợ atomicity của những cập nhật này **cho một key**, nhưng một thao tác liên quan **hai key** hoặc một collection khác không tự thành transaction.

**Cẩn thận với `null`:** `ConcurrentHashMap` không cho key/value `null`. `compute`/`merge` dùng kết quả `null` theo semantics xóa hoặc không có mapping tùy method. Nếu nghiệp vụ cần lưu “giá trị null là trạng thái hợp lệ”, hãy thiết kế sentinel/Optional/value object thay vì lén đưa `null` vào map.

### 5.1. Ví dụ Java 17: ConcurrentHashMap.compute sửa lost update

Tạo file **`ConcurrentMapAtomicDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentMapAtomicDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        counts.put("views", 0);

        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 8; worker++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        counts.compute("views", (key, oldValue) ->
                                oldValue == null ? 1 : oldValue + 1);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("expected=8000 actual=" + counts.get("views"));
            System.out.println("keys=" + counts.size());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConcurrentMapAtomicDemo.java
java ConcurrentMapAtomicDemo
~~~

Stdout khi mọi task thành công:

~~~text
expected=8000 actual=8000
keys=1
~~~

Tám task, mỗi task tăng một nghìn lần: tổng cộng 8.000 phép cập nhật. `ConcurrentHashMap.compute` bảo đảm cập nhật tính toán đối với **một mapping key** được thực hiện nguyên tử theo contract của class. Các thread có thể tranh chấp và chờ khi cập nhật key này, nhưng không có interleaving giữa `get` và `put` của caller vì đoạn read-modify-write đã được đưa vào một compound method.

**Điều kiện dùng đúng `compute`:**
- Hàm remapping phải ngắn, đáng tin cậy, không block quá lâu và nên không có tác dụng phụ đối với bên ngoài.
- Không sửa những mapping khác của cùng map trong chính callback; tài liệu `ConcurrentHashMap` cấm cố gắng cập nhật các mapping khác từ hàm compute trong một số trường hợp và có thể phát hiện recursive update không bao giờ hoàn tất.
- Không giả định logic thêm hai key hoặc cập nhật database bên ngoài đã được bao trong thao tác atomic.
- `Future.get()` giúp main biết mọi tác vụ thực sự hoàn thành và phát hiện exception, thay vì chỉ đọc một giá trị khi pool còn chạy.

Với một implementation khác chỉ tuân theo interface `Map` hoặc `ConcurrentMap`, cần đọc **đúng contract class**; không suy toàn bộ bảo đảm atomic mạnh của `ConcurrentHashMap` sang mọi custom map.

### 5.2. putIfAbsent và câu chuyện “chỉ một người thắng”

Thay vì:

~~~java
if (!jobs.containsKey(id)) {
    jobs.put(id, "running");
}
~~~

dùng:

~~~java
String previous = jobs.putIfAbsent(id, "running");
boolean claimed = (previous == null);
~~~

Đây là đoạn trong một method khi `jobs` là `ConcurrentHashMap<String,String>` và `id` là một `String` khác null. Chỉ caller đầu tiên đặt mapping từ absent sang `"running"` được trả về `null` theo hợp đồng. Các caller sau nhận giá trị hiện có.

**Nhưng:** nếu trạng thái cần chuyển từ `"queued"` sang `"running"` chứ không phải absent → present, `putIfAbsent` không phải API đúng. Khi đó dùng `replace(id,"queued","running")` để thực hiện **compare-and-update** theo giá trị kỳ vọng, hoặc `compute` khi logic phức tạp hơn.

Thao tác atomic trên map chỉ bảo đảm **trạng thái của map**. Nếu sau `putIfAbsent` phải gửi email, ghi database, gọi HTTP, việc bên ngoài đó **không tự thuộc cùng một transaction**. Cần thiết kế idempotency, retry và bù trừ cho side effect nghiệp vụ theo phạm vi hệ thống.

### 5.3. merge cho bộ đếm theo key

Với `ConcurrentHashMap<String, Integer>`, có thể viết ngắn:

~~~java
counts.merge("views", 1, Integer::sum);
~~~

Nếu key chưa có, đặt 1; nếu đã có giá trị thì kết hợp old và 1. Phép cập nhật một mapping là atomic theo hợp đồng `ConcurrentHashMap`. Tự viết `getOrDefault` rồi `put` làm mất ý nghĩa này.

Với thống kê cập nhật cực nhiều, một mô hình khác là map từ key sang `LongAdder`. Tuy nhiên `LongAdder.sum()` khi có cập nhật đồng thời **không phải một snapshot nguyên tử**. Chỉ chọn nó nếu nghiệp vụ chấp nhận giá trị quan sát xấp xỉ trong lúc cập nhật; số dư, giới hạn tín dụng và quyết định “chỉ bán khi còn hàng” thường cần invariant chặt hơn.

## 6. Giải pháp C: lấy phần tử khỏi queue bằng một thao tác

Một lỗi check-then-act phổ biến trong consumer:

~~~java
if (!queue.isEmpty()) {
    String task = queue.remove();
    process(task);
}
~~~

Đây là đoạn minh họa với `queue` và `process` đã khai báo. Ngay sau `isEmpty() == false`, một consumer khác có thể lấy hết phần tử. Khi đó `remove()` trên queue trống ném `NoSuchElementException`. Nếu dùng `take()` sau `isEmpty()`, thread có thể **bị chờ** khi phần tử đã bị thread khác lấy.

Khi không muốn chờ, dùng **`poll()` duy nhất**:

~~~java
String task = queue.poll();
if (task != null) {
    process(task);
}
~~~

`poll()` đồng thời kiểm tra và lấy một phần tử ở đầu queue (hoặc trả `null` nếu trống) theo hợp đồng của queue. Với `ConcurrentLinkedQueue`, `null` không phải phần tử hợp lệ, nên `null` biểu thị không lấy được task.

### Ví dụ Java 17: hai consumer, một phần tử

Tạo file **`QueueClaimDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class QueueClaimDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>();
        queue.add("job-1");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Callable<String> claim = () -> {
                start.await();
                return queue.poll();
            };

            Future<String> first = pool.submit(claim);
            Future<String> second = pool.submit(claim);

            start.countDown();
            String a = first.get();
            String b = second.get();

            int claimed = (a != null ? 1 : 0) + (b != null ? 1 : 0);
            int empty = (a == null ? 1 : 0) + (b == null ? 1 : 0);

            System.out.printf(
                    "claimed=%d empty=%d remaining=%d%n",
                    claimed, empty, queue.size());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac QueueClaimDemo.java
java QueueClaimDemo
~~~

Stdout:

~~~text
claimed=1 empty=1 remaining=0
~~~

Không dự đoán thread nào thắng. Nhưng vì chỉ có **một phần tử** và mỗi worker gọi `poll()` đúng một lần, chỉ một worker nhận `"job-1"`, worker còn lại nhận `null`. `Future.get()` đảm bảo main đọc kết quả sau khi cả hai thao tác hoàn tất.

**Lưu ý về kiểu queue:** `BlockingQueue.take()` cố tình **chờ** khi trống; `poll(timeout, unit)` chờ có hạn, `poll()` không chờ. Chọn theo nhu cầu consumer. Không dùng `isEmpty()` trước `take()` như một bảo đảm rằng `take()` sẽ không block.

## 7. Iteration: fail-fast, weakly consistent và snapshot

Mỗi họ collection có hợp đồng iterator khác nhau; “thread-safe” không đồng nghĩa “đang duyệt toàn bộ collection ở một thời điểm duy nhất”.

| Kiểu quan sát | Thường gặp | Ý nghĩa |
| --- | --- | --- |
| Fail-fast (best effort) | `ArrayList`, `HashMap` iterator thông thường | Có thể ném `ConcurrentModificationException` nếu bị thay đổi cấu trúc ngoài iterator; không phải cơ chế bảo đảm an toàn khi chạy đồng thời |
| Iterator cần đồng bộ ngoài | `Collections.synchronizedList/Map` | Giữ đúng monitor của wrapper trong **toàn bộ lần duyệt** theo hợp đồng |
| Weakly consistent | `ConcurrentHashMap`, `ConcurrentLinkedQueue` | Không fail-fast do update đồng thời; có thể thấy một số update, bỏ qua một số update; không phải snapshot atomic |
| Snapshot iterator | `CopyOnWriteArrayList` | Nhìn trạng thái mảng tại lúc iterator được tạo, không thấy các thay đổi sau đó |

### 7.1. Ví dụ Java 17: snapshot iterator của CopyOnWriteArrayList

Tạo file **`CopyOnWriteSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>();
        names.add("A");

        Iterator<String> before = names.iterator();
        names.add("B");

        List<String> seen = new ArrayList<>();
        before.forEachRemaining(seen::add);

        System.out.println("iterator=" + seen);
        System.out.println("current=" + names);
    }
}
~~~

Chạy:

~~~bash
javac CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
~~~

Stdout:

~~~text
iterator=[A]
current=[A, B]
~~~

Iterator được tạo trước khi list thêm B, nên nó duyệt snapshot chứa A. List hiện tại có A và B. Đây là hành vi có chủ đích: vòng duyệt ổn định, ít phải phối hợp reader/writer, rất phù hợp tình huống **đọc nhiều, ghi ít**.

Đổi lại, mỗi update cấu trúc thường phải tạo/copy mảng; ghi thường xuyên hoặc list rất lớn có thể tạo chi phí allocation/copy đáng kể. Iterator snapshot của `CopyOnWriteArrayList` không hỗ trợ `Iterator.remove()`; cố xóa qua iterator sẽ ném `UnsupportedOperationException`.

### 7.2. Weakly consistent không đồng nghĩa ảnh chụp nhất quán

`ConcurrentHashMap.entrySet().iterator()` có thể duyệt trong lúc thread khác cập nhật map mà không cần khóa ngoài kiểu synchronizedMap. Nhưng các entry thu được **không nhất thiết là snapshot tại cùng một thời điểm**. Ví dụ, hệ thống chuyển tiền từ key A sang key B bằng hai cập nhật độc lập; một vòng duyệt có thể thấy A sau khi trừ và B trước khi cộng, dù cả hai thao tác riêng trên map đều an toàn.

Do đó:
- Dùng weakly consistent iterator để quan sát/monitor **chấp nhận biến động**.
- Nếu cần báo cáo tài chính hoặc invariant nhiều key tại một thời điểm, phải thiết kế đồng bộ/snapshot riêng.
- Đừng dùng `size()`, `isEmpty()` hoặc kết quả aggregate trong lúc mutation đồng thời làm bằng chứng tuyệt đối cho một quyết định đa bước. Các giá trị có thể lỗi thời ngay khi trả về.
- Không dựa vào `ConcurrentModificationException` để kiểm soát logic.

## 8. Atomic theo một key vẫn chưa atomic qua nhiều key

Giả sử lưu tài khoản A và B trong một `ConcurrentHashMap<String,Integer>`. Ta cần chuyển 70 đơn vị từ A sang B, ban đầu `A=100, B=0`, với invariant `A+B=100`.

~~~java
balances.compute("A", (key, old) -> old - 70);
balances.compute("B", (key, old) -> old + 70);
~~~

Hai lời gọi `compute` đều có thể atomic **cho key tương ứng**. Nhưng ở giữa chúng, một reader có thể thấy `A=30, B=0` và kết luận tổng là 30. Nếu một thao tác khác xen vào hoặc bước thứ hai ném exception, hệ thống có thể còn sai về nghiệp vụ.

**Không giả định có thể dùng một callback `ConcurrentHashMap.compute` để sửa key khác trong map** nhằm biến hai key thành một transaction; cách đó không thuộc hợp đồng an toàn của callback, có thể gây lỗi hoặc vấn đề tiến triển.

### 8.1. Sửa bằng một lock bảo vệ trọn invariant

Tạo file **`MultiKeyTransferDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultiKeyTransferDemo {
    private record Balances(int a, int b) {}

    private static final class Ledger {
        private int a = 100;
        private int b = 0;

        synchronized boolean transferAToB(int amount) {
            if (amount <= 0 || a < amount) {
                return false;
            }
            a -= amount;
            b += amount;
            return true;
        }

        synchronized Balances snapshot() {
            return new Balances(a, b);
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> first =
                    pool.submit(() -> ledger.transferAToB(70));
            Future<Boolean> second =
                    pool.submit(() -> ledger.transferAToB(70));

            int accepted = (first.get() ? 1 : 0) +
                    (second.get() ? 1 : 0);

            Balances view = ledger.snapshot();
            System.out.printf(
                    "accepted=%d A=%d B=%d total=%d%n",
                    accepted, view.a(), view.b(), view.a() + view.b());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MultiKeyTransferDemo.java
java MultiKeyTransferDemo
~~~

Stdout:

~~~text
accepted=1 A=30 B=70 total=100
~~~

Hai task đồng thời cố chuyển 70, nhưng lock của **cùng đối tượng Ledger** buộc mỗi lần kiểm tra–trừ–cộng diễn ra nguyên tử với các thao tác khác của Ledger. Chỉ một lần chuyển thành công; lần kia thấy `a=30` và trả `false`. `snapshot()` cũng khóa monitor đó, nên không quan sát trạng thái ở giữa bước trừ và bước cộng.

Ví dụ dùng hai trường để làm nổi bật invariant; nếu trạng thái thực nằm trong map thì có thể bảo vệ **mọi cập nhật và snapshot** qua một lock của service sở hữu map. Một lựa chọn khác là chứa cả A/B trong **một immutable record** rồi cập nhật record qua `AtomicReference.compareAndSet`/`updateAndGet`. Chọn dựa vào độ phức tạp invariant, tần suất ghi, contention và phạm vi dữ liệu.

**Ranh giới cần nhớ:** `synchronized`/`AtomicReference` của một JVM chỉ phối hợp các thread **trong cùng tiến trình**. Nếu hai process cùng sửa một database hoặc một tài nguyên phân tán, bạn cần giao thức giao dịch/phối hợp riêng của hệ thống đó; thread-safe collection không giải quyết concurrency liên tiến trình.

## 9. Kiểm tra kỹ các compound action thường gặp

### 9.1. containsKey + put

~~~java
if (!map.containsKey(key)) {
    map.put(key, value);
}
~~~

Một thread khác có thể chèn key sau `containsKey`. Với `ConcurrentHashMap`, dùng `putIfAbsent` khi cần **chỉ đặt nếu absent**. Nếu giá trị `null` có semantics đặc biệt, đọc contract cụ thể.

### 9.2. get + put để tăng counter

~~~java
map.put(key, map.getOrDefault(key, 0) + 1);
~~~

Nếu map bị nhiều writer sửa, có lost update. Dùng `compute`/`merge` của `ConcurrentHashMap`, hoặc khóa toàn chuỗi nếu dùng synchronized wrapper.

### 9.3. contains + add để tránh trùng trong list

~~~java
if (!list.contains(item)) {
    list.add(item);
}
~~~

Hai thread có thể cùng thấy chưa có rồi cùng thêm. Nếu invariant là **set không có phần tử trùng**, dùng cấu trúc `Set` thích hợp (ví dụ `ConcurrentHashMap.newKeySet()`) và một lời gọi `add(item)` có semantics atomic cho membership. Nếu vẫn cần thứ tự và cho phép duplicate theo các quy tắc khác, phải khóa toàn chuỗi dưới một monitor thống nhất.

### 9.4. size + get hoặc isEmpty + remove

~~~java
if (list.size() > index) {
    return list.get(index);
}
~~~

Một thread khác có thể xóa hoặc sắp lại list sau kiểm tra. Với synchronizedList, khóa wrapper cho toàn bộ chuỗi. Nếu dùng queue để nhận một phần tử, dùng `poll()` thay cho check-then-remove.

### 9.5. peek + poll

~~~java
String expectedHead = queue.peek();
String removed = queue.poll();
~~~

Hai lời gọi an toàn riêng nhưng thread khác có thể lấy head ở giữa; `removed` không nhất thiết bằng `expectedHead`. Nếu chỉ muốn **claim phần tử**, chỉ dùng kết quả `poll()`. Nếu phải “kiểm tra head thỏa điều kiện mới lấy”, cần một API/giao thức nguyên tử phù hợp, như một lock bảo vệ cả thao tác hoặc queue có semantics riêng được thiết kế cho yêu cầu đó.

### 9.6. Iteration + update

~~~java
for (String value : list) {
    if (shouldRemove(value)) {
        list.remove(value);
    }
}
~~~

Đây là đoạn minh họa có `shouldRemove`. Với một `ArrayList` bình thường, gọi `list.remove` trong enhanced for có thể gây `ConcurrentModificationException` ngay cả trong **một thread**. Với concurrent list, semantics tùy loại; iterator snapshot không sửa được snapshot. Hãy dùng `removeIf` nếu contract của collection đáp ứng chính xác phạm vi atomic bạn cần, hoặc khóa và thao tác qua `Iterator.remove()` khi collection hỗ trợ. **Không suy ra** mọi implementation của `removeIf` đều atomic so với mọi update khác.

## 10. Chọn công cụ theo yêu cầu

| Yêu cầu thực tế | Cách tiếp cận |
| --- | --- |
| Một writer, nhiều thread cần gửi command | Ownership + queue/actor-like executor |
| Tăng counter độc lập trong map | `ConcurrentHashMap.compute/merge`; hoặc map key -> `LongAdder` nếu chấp nhận snapshot không nguyên tử |
| Đăng ký một key nếu chưa có | `putIfAbsent` |
| Chuyển trạng thái theo giá trị cũ | `replace(key, expected, next)` hoặc `compute` |
| Nhiều consumer tranh một task | `BlockingQueue.take/poll` hoặc `ConcurrentLinkedQueue.poll` |
| Đọc nhiều, ít thay đổi, iteration ổn định | `CopyOnWriteArrayList` hoặc publish immutable list |
| Synchronized wrapper và một đoạn nhiều bước | `synchronized(wrapper)` trọn đoạn, mọi đường truy cập cùng giao thức |
| Cập nhật/snapshot nhất quán nhiều trường hoặc key | Lock chung hoặc immutable aggregate + `AtomicReference` |
| Báo cáo xấp xỉ khi cập nhật đồng thời | Weakly consistent iteration, metric snapshot có giới hạn rõ |
| Transaction đi qua nhiều JVM/database | Giao thức đồng bộ/giao dịch ngoài phạm vi collection Java |

**Không có giải pháp tốt nhất cho mọi workload.** Lock bảo vệ invariant lớn nhưng có contention; `ConcurrentHashMap` có concurrency tốt theo key nhưng không cung cấp transaction nhiều key; copy-on-write tối ưu iteration read-heavy nhưng tốn copy khi ghi; queue giải quyết công việc theo phần tử nhưng không tự xử lý consistency giữa hai hệ thống.

## 11. Liveness và hiệu năng sau khi sửa race

Sửa đúng atomicity mới là bước đầu. Còn cần kiểm tra **liveness** và throughput:

- **Khóa quá rộng:** nhiều thread chờ dù làm việc trên dữ liệu độc lập. Có thể chia state thành các partition độc lập nếu invariant cho phép.
- **Deadlock:** hai thread lấy nhiều lock theo thứ tự ngược nhau. Dùng thứ tự khóa toàn cục và giới hạn đường gọi callback trong lock.
- **Compute callback chạy lâu:** `ConcurrentHashMap.compute` có thể chặn các update cạnh tranh liên quan trong lúc callback còn chạy; tránh I/O hoặc tính toán nặng trong callback.
- **Backpressure:** producer gửi công việc vào queue nhanh hơn consumer lấy ra, làm tăng backlog và latency. Chọn queue hữu hạn và chính sách từ chối/timeout khi phù hợp.
- **Copy-on-write nhiều ghi:** thường tạo chi phí copy và áp lực GC. Không dùng cho list bị sửa liên tục, dung lượng lớn, chỉ vì muốn iteration dễ.
- **CAS retry:** giải pháp nguyên tử không tự có latency thấp khi contention cao. Đo số retry và p95/p99 trước khi kết luận.
- **Không có snapshot atomic:** thống kê `size()`, duyệt map hoặc đọc nhiều key trong khi có update vẫn có thể cho ảnh quan sát không nhất quán; cần nêu rõ tính approximate.

Khi đo hiệu năng, luôn dùng workload có cùng kích thước, warm-up thích hợp, chờ task hoàn tất, theo dõi **throughput thành công**, latency, contention, CPU, GC và lỗi. **Một kết quả nhanh nhưng sai invariant không phải tối ưu hóa hợp lệ.**

## 12. Cách kiểm chứng thread-safe code của riêng bạn

1. **Viết invariant thành điều kiện cụ thể**: “mỗi job chỉ claim một lần”, “counter bằng số increment thành công”, “tổng A+B không đổi”.
2. **Liệt kê mọi đường đọc/ghi**, bao gồm iterator, callback, getter, snapshot, thread background và API bên ngoài có thể sửa backing collection.
3. **Chỉ rõ phạm vi atomic** của từng operation cần có hiệu lực như một lần duy nhất. Hỏi “giữa hai lời gọi method này, thread khác có thể chen vào không?”.
4. **Đọc đúng contract implementation**, không chỉ interface. `Map` thông thường, synchronized wrapper và `ConcurrentHashMap` có những bảo đảm khác nhau.
5. **Chọn API một bước hoặc khóa trọn chuỗi**: `putIfAbsent`, `compute`, `poll`; hoặc cùng lock/ownership/immutable snapshot khi invariant rộng hơn.
6. **Thiết kế test race có điều phối**, dùng `CountDownLatch`/`CyclicBarrier` để tạo interleaving nguy hiểm. Không dùng `Thread.sleep` như bằng chứng ordering.
7. **Chờ và kiểm tra mọi task** qua `Future.get()`/`join()`; nếu task trong executor thất bại mà không đọc Future, test có thể báo xanh sai.
8. **Kiểm tra trong lúc cập nhật**, không chỉ sau khi tất cả task kết thúc. Một snapshot nhiều field có thể sai tạm thời rồi đúng trở lại.
9. **Thử lỗi và cancellation**, đảm bảo `finally` nhả lock/đóng tài nguyên; queue không tăng không giới hạn và callback compute không mang side effect bất ngờ.
10. **Đo hiệu năng khi đã đúng**, xem cả contention, backlog, CPU/GC và p99 chứ không chỉ số operations/s.

Stress test có thể phát hiện regression nhưng không chứng minh vắng mặt mọi race. Lập luận trên **Java Memory Model, bất biến nghiệp vụ và contract của collection** là nền tảng.

## 13. Những hiểu lầm thường gặp

1. **“Collection thread-safe nên cả đoạn code sử dụng nó thread-safe.”** Sai khi đoạn đó chứa compound action nhiều lời gọi.
2. **“SynchronizedMap không thể có lost update.”** Wrapper bảo vệ operation theo contract; `get` và `put` tách rời vẫn có thể mất cập nhật.
3. **“Thấy key không tồn tại thì chắc chắn put sẽ là người đầu tiên.”** Một thread khác có thể chèn key sau check; dùng `putIfAbsent`.
4. **“ConcurrentHashMap giúp chuyển tiền giữa hai key atomic.”** `compute` atomic theo mapping/key, không tự gom hai key.
5. **“size() > 0 đảm bảo get(0) sẽ thành công.”** Thread khác có thể xóa phần tử sau lúc đọc size.
6. **“isEmpty() == false đảm bảo take() sẽ không chờ.”** Consumer khác có thể lấy hết queue; chọn `poll/take` theo contract.
7. **“Concurrent iterator cho snapshot nhất quán.”** Weakly consistent iterator không giữ một phiên bản cố định toàn map.
8. **“Iterator không ném ConcurrentModificationException nghĩa là an toàn.”** Fail-fast chỉ best effort; không phải synchronization.
9. **“CopyOnWriteArrayList thấy ngay phần tử mới trong iterator cũ.”** Iterator là snapshot; tạo iterator mới nếu muốn bản mới.
10. **“Atomic theo key là atomic với database và service ngoài.”** Side effect ngoài map không tự được transaction hóa.
11. **“Một HashMap được bọc synchronized rồi có thể cho caller khác dùng backing map trực tiếp.”** Bypass wrapper phá giao thức.
12. **“Dùng sleep để tránh thread chen vào.”** Sleep không lập happens-before hay mutual exclusion.
13. **“Không cần kiểm tra Future.”** Task có thể ném exception và kết quả test sau cùng không phản ánh đủ lỗi.
14. **“Chỉ sửa writer là đủ.”** Reader snapshot nhiều trường cũng phải tuân theo cơ chế nhất quán.

## 14. Câu hỏi tự kiểm tra

1. Hai thread làm `get("x")` rồi `put("x", old+1)` trên `Collections.synchronizedMap`. Có mất cập nhật không? **Có**, vì hai thao tác riêng không được gói thành một critical section.
2. API nào phù hợp để chỉ chèn `id -> "running"` khi chưa có mapping trong `ConcurrentHashMap`? **`putIfAbsent`**.
3. API nào phù hợp để tăng counter gắn với một key trong `ConcurrentHashMap`? **`compute` hoặc `merge`**, theo contract atomic của class.
4. Vì sao callback `compute` không nên gọi I/O chậm hoặc sửa các mapping khác cùng map? **Có thể giữ những update cạnh tranh phải đợi và vi phạm ràng buộc callback/tiến triển**.
5. Với `ConcurrentLinkedQueue`, tại sao `peek` rồi `poll` không bảo đảm lấy đúng phần tử vừa nhìn thấy? **Một consumer khác có thể lấy head ở giữa**.
6. Nếu hai consumer `poll` cùng lúc trên queue chỉ có một item, bao nhiêu consumer có thể nhận item đó? **Tối đa một**.
7. Cách duyệt `Collections.synchronizedList` khi có modifier khác dùng cùng wrapper? **Giữ `synchronized(list)` xuyên suốt iteration**.
8. `ConcurrentHashMap` iterator có phải ảnh snapshot atomic không? **Không**, là weakly consistent.
9. `CopyOnWriteArrayList` iterator tạo trước `list.add("B")` có thấy B không? **Không**, iterator đọc snapshot cũ.
10. Một invariant là `balanceA + balanceB == 100`. Vì sao hai lần `compute` riêng không bảo vệ invariant đối với observer? **Có khoảng trung gian giữa hai cập nhật**.
11. Vì sao test chỉ kiểm tra dữ liệu sau khi mọi thread kết thúc có thể bỏ sót lỗi? **Trong lúc chạy, reader có thể thấy trạng thái trung gian sai rồi sau cùng lại đúng**.
12. Điều gì phải đi cùng lời khẳng định “đây là collection thread-safe”? **Nêu rõ contract của từng operation, iterator, giới hạn compound action và invariant cần bảo vệ**.

## Kết luận

**Thread-safe collection bảo vệ những thao tác mà hợp đồng của chính collection bảo đảm; nó không tự biến một chuỗi thao tác nghiệp vụ thành một transaction.** Với compound action, hãy xác định invariant và phạm vi dữ liệu: dùng `ConcurrentHashMap.compute/putIfAbsent/replace` cho cập nhật **một key**, `poll` cho **claim một phần tử queue**, `synchronized(wrapper)` cho **một chuỗi trên synchronized collection**, và **lock chung/ownership/immutable snapshot** cho invariants nhiều trường hoặc key.

Cần luôn phân biệt thread safety, atomicity và snapshot consistency; đo độ đúng trước rồi mới đo hiệu năng.

## Tham khảo Java SE 17

- [Collections.synchronizedList / synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): yêu cầu đồng bộ ngoài khi iteration và hợp đồng synchronized wrapper.
- [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute`, `merge`, `putIfAbsent`, iterator weakly consistent.
- [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): `poll` và semantics concurrent queue.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take`, `offer`, `poll`, timeout.
- [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterators và write-copy tradeoff.
- [Java Language Specification 17, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): threads, locks, happens-before và Java Memory Model.
