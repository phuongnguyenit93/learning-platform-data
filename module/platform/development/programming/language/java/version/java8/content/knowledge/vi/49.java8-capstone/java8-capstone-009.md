# Đếm sự kiện đồng thời bằng map và biến tích lũy trong Java

## 1. Bài toán: nhiều thread cùng ghi nhận sự kiện

Một ứng dụng thường cần đếm số lần xuất hiện của từng loại sự kiện: request theo endpoint, đăng nhập, giao dịch theo trạng thái, message theo topic hoặc lỗi theo mã. Khi nhiều thread xử lý sự kiện cùng lúc, nhiều thread có thể cập nhật cùng một bộ đếm.

Ví dụ, ta muốn giữ hai loại số liệu:

- **Bộ đếm theo khóa:** map lưu số lần xuất hiện của từng loại sự kiện.
- **Tổng tích lũy:** một biến đếm tổng số sự kiện đã xử lý.

Nếu dùng HashMap và biến long thông thường rồi để nhiều thread cùng tăng giá trị, chương trình có thể mất cập nhật. Hai thread đọc cùng giá trị cũ, cùng cộng một, rồi ghi đè kết quả của nhau. Kết quả cuối nhỏ hơn số sự kiện thực tế.

Java có các công cụ đồng thời phù hợp: ConcurrentHashMap để cập nhật cấu trúc map an toàn, LongAdder cho bộ đếm chịu nhiều lần cập nhật đồng thời, AtomicLong cho một bộ đếm nguyên tử và Collectors.groupingByConcurrent() khi có thể biểu diễn bài toán dưới dạng Stream reduction.

**Mục tiêu:** chọn đúng cấu trúc cho map và biến tích lũy, bảo đảm không mất cập nhật, đọc kết quả đúng thời điểm và kiểm thử bằng một chương trình có kết quả xác định.

## 2. Vì sao count++ không an toàn giữa nhiều thread?

Biểu thức:

```java
count++;
```

trông giống một thao tác đơn, nhưng với biến số nguyên thông thường, nó tương đương về ý nghĩa với chuỗi đọc, cộng, ghi:

```java
long current = count;
long next = current + 1;
count = next;
```

Giả sử count đang là 10:

1. Thread A đọc 10.
2. Thread B cũng đọc 10.
3. Thread A tính 11.
4. Thread B cũng tính 11.
5. Thread A ghi 11.
6. Thread B ghi 11.

Hai sự kiện đã xảy ra nhưng bộ đếm chỉ tăng một lần. Đây là lỗi lost update.

volatile không sửa được vấn đề này. volatile hỗ trợ visibility và thứ tự quan sát đối với biến, nhưng không biến chuỗi đọc-cộng-ghi thành một thao tác nguyên tử.

```java
volatile long count = 0L;
count++; // Vẫn có thể mất cập nhật khi nhiều thread cùng chạy.
```

Cần dùng một thao tác nguyên tử như AtomicLong.incrementAndGet(), LongAdder.increment() hoặc đồng bộ hóa một critical section.

## 3. Vì sao HashMap không phù hợp cho cập nhật đồng thời?

HashMap không hỗ trợ nhiều thread cùng sửa đổi map mà không có đồng bộ hóa bên ngoài. Khi nhiều thread gọi put, compute, merge hoặc sửa cấu trúc map cùng lúc, chương trình có thể có race condition, kết quả sai hoặc hành vi không được bảo đảm.

Ví dụ không an toàn:

```java
Map<String, Long> counts = new HashMap<>();

events.parallelStream().forEach(type -> {
    Long oldValue = counts.get(type);
    counts.put(type, oldValue == null ? 1L : oldValue + 1L);
});
```

Có hai vấn đề:

- HashMap không thread-safe cho các thao tác ghi đồng thời.
- Chuỗi get rồi put là read-modify-write; ngay cả khi map có hỗ trợ từng thao tác riêng lẻ, cả chuỗi vẫn có thể bị xen kẽ.

Không nên dùng Collections.synchronizedMap() rồi giả định mọi chuỗi thao tác nhiều bước tự động nguyên tử. Wrapper đồng bộ hóa từng method; nếu cần đọc rồi cập nhật trong một giao dịch nhỏ, phải đồng bộ đúng trên monitor của map hoặc dùng API atomic của concurrent map.

## 4. ConcurrentHashMap: map an toàn cho thao tác đồng thời

ConcurrentHashMap là map hỗ trợ truy cập đồng thời. Nhiều thread có thể đọc và cập nhật map thông qua API của nó mà không cần khóa toàn bộ map bằng một synchronized block.

Ví dụ tạo map:

```java
ConcurrentMap<String, Long> counts = new ConcurrentHashMap<>();
```

Các method hữu ích cho cập nhật nguyên tử theo khóa:

- putIfAbsent(key, value).
- computeIfAbsent(key, mappingFunction).
- compute(key, remappingFunction).
- merge(key, value, remappingFunction).
- replace(key, oldValue, newValue).
- remove(key, value).

Các method này cho phép thực hiện một phép cập nhật gắn với một khóa theo semantics nguyên tử của concurrent map. Chúng không làm cho mọi chuỗi gọi method tùy ý trở thành một giao dịch chung.

### 4.1. Không dùng get rồi put để tăng bộ đếm

Mẫu dễ viết nhưng sai khi nhiều thread cùng cập nhật:

```java
Long oldValue = counts.get(type);
counts.put(type, oldValue == null ? 1L : oldValue + 1L);
```

Hai thread có thể cùng đọc một giá trị cũ và ghi đè nhau. Hãy dùng merge, compute hoặc map chứa một bộ đếm thread-safe.

### 4.2. Dùng merge với giá trị Long bất biến

Cách ngắn gọn:

```java
counts.merge(type, 1L, Long::sum);
```

merge thực hiện cập nhật cho khóa theo cách nguyên tử. Nếu chưa có khóa, giá trị mới là 1L; nếu đã có, hàm Long::sum cộng giá trị cũ với một.

Cách này dễ hiểu và phù hợp với số lượng cập nhật vừa phải. Khi một khóa nóng nhận rất nhiều cập nhật, các lần sửa cùng khóa vẫn phải phối hợp với nhau; một Long mới được tạo cho mỗi kết quả cộng.

### 4.3. Dùng compute khi quy tắc cập nhật phức tạp hơn

```java
counts.compute(type, (key, oldValue) ->
    oldValue == null ? 1L : oldValue + 1L);
```

Hàm remapping nhận khóa và giá trị hiện có, rồi trả về giá trị mới. Nếu trả null, mapping bị loại bỏ. Không gọi các thao tác cập nhật đệ quy trên chính map từ remapping function; giữ hàm ngắn, đơn giản và không có side effect bên ngoài.

## 5. LongAdder: biến tích lũy cho nhiều lần tăng đồng thời

LongAdder thuộc java.util.concurrent.atomic và có từ Java 8. Nó được thiết kế cho trường hợp nhiều thread thường xuyên cộng hoặc tăng một bộ đếm. Thay vì buộc mọi thread tranh chấp trên một biến duy nhất như AtomicLong, LongAdder có thể phân tán cập nhật qua các ô nội bộ rồi tổng hợp khi đọc.

Cách dùng:

```java
LongAdder total = new LongAdder();

total.increment();
total.add(5L);

long current = total.sum();
```

Các method thường dùng:

| Method | Ý nghĩa |
| --- | --- |
| increment() | Tăng một |
| decrement() | Giảm một |
| add(long x) | Cộng một lượng |
| sum() | Đọc tổng hiện tại |
| reset() | Đặt lại bộ đếm |
| sumThenReset() | Lấy tổng rồi đặt lại |

### 5.1. Khi nào chọn LongAdder?

Chọn LongAdder khi:

- Có nhiều thread cập nhật cùng một bộ đếm.
- Cần thông lượng cập nhật tốt dưới contention.
- Chủ yếu đọc kết quả sau một giai đoạn xử lý.
- Không cần dùng giá trị đọc được làm điều kiện đồng bộ chính xác ngay trong lúc cập nhật.

Đây là lựa chọn phù hợp cho metrics, event counters, số request, số lỗi và các thống kê tích lũy.

### 5.2. sum() trong lúc đang cập nhật không phải snapshot nguyên tử

LongAdder.sum() cộng các phần dữ liệu nội bộ để trả về tổng tại thời điểm đọc. Trong khi vẫn có thread cập nhật, kết quả không phải một snapshot nguyên tử tại một thời điểm duy nhất. Nó phù hợp để quan sát thống kê đang chạy, nhưng không dùng làm điều kiện đồng bộ yêu cầu một giá trị tuyến tính hóa chính xác.

Sau khi mọi worker đã hoàn tất và không còn cập nhật, sum() trả tổng cuối ổn định. Ví dụ bên dưới đợi mọi Future hoàn thành trước khi đọc.

### 5.3. reset() và sumThenReset() cần có ranh giới đồng bộ

Không reset bộ đếm khi thread khác vẫn đang tăng nếu bạn cần bảo đảm không mất sự kiện ở ranh giới giữa hai kỳ. sumThenReset() không phải một giao dịch nguyên tử với mọi lần cập nhật đồng thời. Hãy thiết kế rõ chu kỳ snapshot/reset, dùng cơ chế đồng bộ phù hợp hoặc thay bộ đếm theo epoch.

### 5.4. LongAdder không thay thế mọi use case của AtomicLong

LongAdder không cung cấp các thao tác như compareAndSet, getAndIncrement hoặc một phép cập nhật có điều kiện dựa trên giá trị hiện tại. Nếu cần cấp số thứ tự duy nhất, điều khiển ngưỡng, token bucket chính xác hoặc phối hợp trạng thái, hãy xem AtomicLong.

## 6. AtomicLong: bộ đếm nguyên tử với giá trị đọc chính xác

AtomicLong có từ các phiên bản Java hỗ trợ package java.util.concurrent.atomic và vẫn là API hiện hành.

```java
AtomicLong total = new AtomicLong();

long next = total.incrementAndGet();
long current = total.get();
boolean changed = total.compareAndSet(10L, 11L);
```

Các method hữu ích:

- incrementAndGet() và getAndIncrement().
- addAndGet(delta) và getAndAdd(delta).
- get(), set(value).
- compareAndSet(expected, update).
- updateAndGet(function) và getAndUpdate(function).

AtomicLong phù hợp khi mỗi lần đọc cần quan sát giá trị nguyên tử và ứng dụng cần CAS hoặc cập nhật có điều kiện. Khi nhiều thread cùng tăng một biến duy nhất với contention cao, LongAdder thường có thông lượng tốt hơn, nhưng không cung cấp cùng semantics đọc/cập nhật.

### 6.1. Chọn nhanh giữa LongAdder và AtomicLong

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Đếm metrics với nhiều writer | LongAdder |
| Tổng hợp sau khi worker hoàn tất | LongAdder |
| Cấp sequence number duy nhất | AtomicLong |
| CAS hoặc cập nhật có điều kiện | AtomicLong |
| Cần đọc giá trị nguyên tử làm quyết định | AtomicLong |
| Một bộ đếm ít contention, cần API đơn giản | Cả hai đều có thể phù hợp |

Không chọn chỉ dựa trên tên class. Hãy chọn theo semantics cần bảo đảm và đo workload thật nếu hiệu năng quan trọng.

## 7. Map chứa LongAdder: mẫu đếm theo khóa phổ biến

Đối với nhiều loại sự kiện, có thể dùng ConcurrentHashMap<K, LongAdder>:

```java
ConcurrentMap<String, LongAdder> counts = new ConcurrentHashMap<>();

counts.computeIfAbsent(type, key -> new LongAdder())
      .increment();
```

Hai bước có vai trò khác nhau:

1. computeIfAbsent tạo và đăng ký LongAdder cho khóa nếu chưa có.
2. increment() tăng bộ đếm thread-safe tương ứng với khóa.

Nếu nhiều thread cùng gặp một loại sự kiện, chúng lấy cùng mapping LongAdder và cập nhật bằng API của LongAdder.

Đây là mẫu thường dùng cho frequency map:

```java
ConcurrentHashMap<String, LongAdder> frequencies =
    new ConcurrentHashMap<>();

for (String word : words) {
    frequencies.computeIfAbsent(word, ignored -> new LongAdder())
               .increment();
}
```

Với ConcurrentHashMap, computeIfAbsent thực hiện việc thiết lập mapping theo semantics nguyên tử của map. Mapping function nên ngắn, đơn giản, không gọi lại thao tác cập nhật trên chính map. Tạo một LongAdder mới là công việc phù hợp.

### 7.1. Map thread-safe không tự làm value object thread-safe

ConcurrentHashMap bảo vệ các thao tác map. Nếu value là một object mutable tùy ý, các thao tác trên object đó vẫn phải có thread-safety riêng.

Ví dụ:

```java
ConcurrentMap<String, ArrayList<String>> map =
    new ConcurrentHashMap<>();

map.computeIfAbsent(type, key -> new ArrayList<>()).add(event);
```

Phần computeIfAbsent an toàn cho việc tạo mapping, nhưng ArrayList.add() không trở nên thread-safe chỉ vì nó nằm trong ConcurrentHashMap. Nhiều thread cùng thêm vào list vẫn có thể gây race condition.

Với bộ đếm, dùng value là LongAdder hoặc AtomicLong để chính value cũng hỗ trợ cập nhật đồng thời.

### 7.2. Không xóa mapping trong lúc thread còn giữ reference tới adder

Nếu một thread lấy LongAdder cũ, trong khi thread khác xóa key rồi một thread khác tạo adder mới cho cùng key, các lần tăng có thể bị chia vào hai object. Một số lần cập nhật sẽ không nằm trong mapping hiện tại.

Nếu cần xóa/reset key, hãy có ranh giới đồng bộ hoặc thiết kế epoch/snapshot rõ ràng. Không kết hợp tùy tiện remove với computeIfAbsent và increment khi writers còn hoạt động.

## 8. Đếm tổng và đếm theo loại sự kiện cùng lúc

Một yêu cầu thường gặp là vừa đếm theo từng loại, vừa đếm tổng. Có thể giữ:

```java
ConcurrentMap<String, LongAdder> byType =
    new ConcurrentHashMap<>();
LongAdder total = new LongAdder();
```

Khi xử lý mỗi sự kiện:

```java
byType.computeIfAbsent(type, key -> new LongAdder()).increment();
total.increment();
```

Sau khi tất cả worker kết thúc, đọc total.sum() và từng LongAdder.sum() trong map.

**Lưu ý về snapshot:** hai thao tác tăng là hai thao tác riêng. Trong lúc workers đang chạy, một thread đọc tổng và map có thể quan sát chúng ở những thời điểm khác nhau; tổng và tổng các nhóm chưa chắc khớp tại đúng lần đọc đó. Sau khi đã đợi mọi worker hoàn tất, dữ liệu ổn định và có thể kiểm tra:

```text
total == sum(byType.values())
```

Nếu nghiệp vụ yêu cầu một snapshot nhất quán tuyệt đối ngay khi hệ thống vẫn nhận sự kiện, cần thiết kế cơ chế snapshot/locking hoặc luồng ghi sự kiện riêng; hai bộ LongAdder độc lập không tạo thành một transaction chung.

## 9. Dùng Collectors.groupingByConcurrent() khi đầu vào là Stream

Nếu dữ liệu đã nằm trong một collection và muốn nhóm bằng parallel stream, có thể dùng collector thay vì tự chia sẻ map bên ngoài:

```java
ConcurrentMap<String, Long> counts =
    events.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Function.identity(),
            Collectors.counting()
        )
    );
```

groupingByConcurrent trả về ConcurrentMap và là collector concurrent, unordered. Collectors.counting() tạo số đếm cho từng khóa. Cách này diễn đạt trực tiếp phép nhóm và để Stream framework quản lý quá trình reduction.

### 9.1. Khi nào dùng collector thay cho map mutable bên ngoài?

Dùng groupingByConcurrent khi:

- Nguồn dữ liệu là Stream.
- Kết quả chỉ cần tổng hợp sau khi collect hoàn tất.
- Không cần cập nhật map từ nhiều luồng xử lý độc lập ngoài pipeline.
- Muốn tránh side effect chia sẻ trong forEach.

Nếu stream tuần tự, Collectors.groupingBy() cũng là lựa chọn phù hợp. Với parallel stream, groupingBy() có thể cần ghép các map trung gian; groupingByConcurrent() có thể giảm công việc merge tùy dữ liệu và contention.

### 9.2. groupingByConcurrent không bảo đảm tăng tốc trong mọi trường hợp

Nếu tất cả sự kiện cùng rơi vào một khóa nóng, contention trên một nhóm vẫn có thể đáng kể. Nếu key cardinality cao, map và object overhead tăng. Đo bằng dữ liệu có phân bố khóa giống production trước khi kết luận collector nào nhanh hơn.

### 9.3. Collector quản lý accumulator khác với side effect trong forEach

Đoạn sau có cập nhật shared map nhưng không cần thiết nếu có thể dùng collector:

```java
ConcurrentMap<String, LongAdder> counts = new ConcurrentHashMap<>();

events.parallelStream().forEach(type ->
    counts.computeIfAbsent(type, key -> new LongAdder()).increment()
);
```

Nó có thể đúng vì map và value đều hỗ trợ concurrency, nhưng pipeline có side effect ra ngoài. groupingByConcurrent thường biểu đạt mục tiêu tổng hợp rõ hơn và dễ kiểm thử hơn.

## 10. Biến local trong lambda và lỗi effectively final

Java yêu cầu biến local được lambda capture phải là final hoặc effectively final. Vì vậy đoạn code sau không biên dịch:

```java
long total = 0L;

events.forEach(event -> total++);
```

Biến total bị thay đổi sau khi khai báo nên không effectively final. Quy tắc này cũng giúp tránh một kiểu shared mutable local không được Java cho phép.

Một số người dùng mảng một phần tử để lách compiler:

```java
long[] total = {0L};
events.parallelStream().forEach(event -> total[0]++);
```

Cách này vẫn không thread-safe. Mảng chỉ giữ một ô nhớ; nhiều thread cùng tăng có thể mất cập nhật.

Dùng một object có API đồng thời phù hợp:

```java
LongAdder total = new LongAdder();

events.parallelStream().forEach(event -> total.increment());
```

Reference total không thay đổi nên có thể capture; trạng thái nội bộ được cập nhật bằng LongAdder. Tuy vậy, nếu chỉ cần tổng hợp kết quả stream, mapToLong(...).sum() hoặc collect() thường là cách diễn đạt tốt hơn.

## 11. Chọn cách đếm theo hình dạng bài toán

| Bài toán | Cách nên xem xét |
| --- | --- |
| Đếm một loại sự kiện, nhiều writer | LongAdder |
| Đếm một loại sự kiện, cần CAS/sequence | AtomicLong |
| Đếm theo key, nhiều writer | ConcurrentHashMap<K, LongAdder> |
| Đếm theo key bằng giá trị immutable | ConcurrentHashMap.merge() |
| Nhóm collection bằng parallel stream | groupingByConcurrent() |
| Nhóm tuần tự | groupingBy() |
| Tổng đơn giản trên numeric stream | mapToLong(...).sum() |
| Tổng hợp nhiều field từ mỗi phần tử | collect() với accumulator/combiner phù hợp |

Không nên thêm một map đồng thời nếu kết quả chỉ là một tổng số. Ngược lại, không dùng một LongAdder toàn cục nếu cần phân biệt nhiều key.

## 12. Chương trình Java 8 hoàn chỉnh: đếm 10.000 sự kiện trên 4 worker

Chương trình dưới đây tạo 10.000 sự kiện có phân bố xác định, chia thành bốn đoạn và giao cho bốn worker. Mỗi worker cập nhật map theo loại sự kiện và một bộ đếm tổng.

- ConcurrentHashMap<String, LongAdder> giữ số lượng theo loại.
- LongAdder total giữ tổng số sự kiện.
- Future.get() đợi từng worker hoàn tất và chuyển lỗi từ worker về thread chính.
- TreeMap tạo snapshot có thứ tự ổn định để stdout dễ kiểm tra.
- Chương trình xác minh tổng và số lượng từng loại trước khi in.

Tạo file **ConcurrentEventCounterDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentEventCounterDemo {
    private static List<String> createEvents() {
        List<String> events = new ArrayList<>(10000);

        for (int i = 0; i < 10000; i++) {
            int slot = i % 10;

            if (slot < 4) {
                events.add("LOGIN");
            } else if (slot < 7) {
                events.add("PURCHASE");
            } else {
                events.add("LOGOUT");
            }
        }

        return events;
    }

    public static void main(String[] args) throws Exception {
        final List<String> events = createEvents();
        final ConcurrentMap<String, LongAdder> byType =
            new ConcurrentHashMap<>();
        final LongAdder total = new LongAdder();

        final int workerCount = 4;
        ExecutorService pool =
            Executors.newFixedThreadPool(workerCount);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < workerCount; worker++) {
                final int from =
                    worker * events.size() / workerCount;
                final int to =
                    (worker + 1) * events.size() / workerCount;

                futures.add(pool.submit(() -> {
                    for (int i = from; i < to; i++) {
                        String type = events.get(i);

                        byType.computeIfAbsent(
                            type, key -> new LongAdder()
                        ).increment();

                        total.increment();
                    }
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }

            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                throw new IllegalStateException(
                    "workers did not terminate");
            }

            Map<String, Long> snapshot = new TreeMap<>();
            for (Map.Entry<String, LongAdder> entry
                    : byType.entrySet()) {
                snapshot.put(entry.getKey(), entry.getValue().sum());
            }

            if (total.sum() != events.size()) {
                throw new AssertionError("total count mismatch");
            }
            if (!Long.valueOf(4000L).equals(snapshot.get("LOGIN"))) {
                throw new AssertionError("LOGIN count mismatch");
            }
            if (!Long.valueOf(3000L).equals(snapshot.get("LOGOUT"))) {
                throw new AssertionError("LOGOUT count mismatch");
            }
            if (!Long.valueOf(3000L).equals(snapshot.get("PURCHASE"))) {
                throw new AssertionError("PURCHASE count mismatch");
            }

            System.out.println("total=" + total.sum());
            for (Map.Entry<String, Long> entry : snapshot.entrySet()) {
                System.out.println(
                    entry.getKey() + "=" + entry.getValue());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK mới có hỗ trợ --release:

```bash
javac --release 8 -encoding UTF-8 ConcurrentEventCounterDemo.java
java ConcurrentEventCounterDemo
```

Nếu dùng JDK 8 trực tiếp, bỏ tùy chọn --release 8 khỏi lệnh javac; các class và method trong ví dụ đều có sẵn từ Java 8.

**Stdout chính xác:**

```text
total=10000
LOGIN=4000
LOGOUT=3000
PURCHASE=3000
```

## 13. Vì sao chương trình cho kết quả ổn định?

### 13.1. Phân bố input được xác định trước

Trong mỗi nhóm mười sự kiện:

- Bốn sự kiện là LOGIN.
- Ba sự kiện là PURCHASE.
- Ba sự kiện là LOGOUT.

Với 10.000 sự kiện, kết quả kỳ vọng là 4.000, 3.000 và 3.000. Tổng là 10.000.

### 13.2. Các worker xử lý những đoạn riêng

Với bốn worker, mỗi worker nhận một đoạn chỉ số. Các đoạn không chồng lấn và phủ toàn bộ danh sách. Mỗi event được xử lý đúng một lần trong chương trình này.

### 13.3. Future.get() tạo ranh giới hoàn tất

Thread chính gọi get() trên tất cả future. Khi tất cả lời gọi trả về, công việc của worker đã hoàn tất; exception trong worker cũng được truyền về caller qua ExecutionException.

Sau ranh giới này, không còn writer của ví dụ cập nhật map hoặc LongAdder. Đọc sum() và tạo snapshot khi đó cho kết quả cuối ổn định.

### 13.4. TreeMap chỉ dùng để sắp xếp kết quả hiển thị

TreeMap được tạo sau khi worker hoàn tất, chỉ trên thread chính. Nó không tham gia cập nhật đồng thời. Mục đích là in thứ tự key cố định, không phụ thuộc thứ tự iteration của ConcurrentHashMap.

## 14. Biến thể dùng ConcurrentHashMap.merge()

Nếu không cần LongAdder làm value, có thể dùng map số đếm Long:

```java
ConcurrentMap<String, Long> counts = new ConcurrentHashMap<>();

for (String type : events) {
    counts.merge(type, 1L, Long::sum);
}
```

Trong xử lý song song:

```java
events.parallelStream().forEach(type ->
    counts.merge(type, 1L, Long::sum)
);
```

Mỗi lần merge cập nhật mapping của khóa một cách nguyên tử. Tuy nhiên, ví dụ parallelStream().forEach vẫn là side effect ra map ngoài pipeline. Nếu mục tiêu đơn thuần là nhóm stream, ưu tiên groupingByConcurrent().

Chọn merge khi:

- Muốn một biểu thức cập nhật ngắn.
- Cần giá trị map là Long.
- Tần suất cập nhật mỗi khóa không quá nóng hoặc hiệu năng đã được đo.
- Muốn đọc giá trị trực tiếp bằng map sau khi writers hoàn tất.

Chọn ConcurrentHashMap<K, LongAdder> khi:

- Một số khóa nhận nhiều update đồng thời.
- Bộ đếm chủ yếu tăng và đọc tổng.
- Chấp nhận semantics đọc sum() không phải snapshot nguyên tử khi writers còn hoạt động.

## 15. Biến thể dùng groupingByConcurrent()

Nếu dữ liệu đã có sẵn trong collection, có thể để collector quản lý accumulation:

```java
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts =
    events.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Function.identity(),
            Collectors.counting()
        )
    );
```

Có thể kiểm tra tổng:

```java
long total = counts.values().stream()
    .mapToLong(Long::longValue)
    .sum();
```

Ở đây total được tính sau khi collect hoàn tất, nên không cần một shared mutable counter trong pipeline. Với yêu cầu thống kê đơn giản, đây thường là cách dễ đọc và dễ kiểm thử.

Nếu cần nhiều metric cho từng loại, có thể tạo downstream collector phù hợp hoặc dùng một accumulator type riêng. Đừng lồng nhiều shared map/counter bên ngoài nếu một collector có thể biểu diễn cùng phép tổng hợp.

## 16. Dùng LongAccumulator cho phép tích lũy tổng quát

Java 8 còn có LongAccumulator, cho phép khai báo một hàm tích lũy và giá trị identity:

```java
LongAccumulator max =
    new LongAccumulator(Long::max, Long.MIN_VALUE);

max.accumulate(12L);
max.accumulate(35L);

System.out.println(max.get());
```

Nó hữu ích cho các phép tổng hợp như max/min hoặc phép toán khác có identity phù hợp. Để kết quả có ý nghĩa độc lập với thứ tự và cách kết hợp, hàm tích lũy nên associative và commutative, và identity phải đúng với phép toán.

Đếm số sự kiện chỉ cần cộng một, vì vậy LongAdder thường đơn giản hơn. Không dùng LongAccumulator chỉ để thay tên cho một bộ đếm.

## 17. Kiểm thử tính đúng đắn của bộ đếm đồng thời

Một test hữu ích cần xác định số sự kiện kỳ vọng trước khi chạy, chạy nhiều worker, đợi tất cả worker hoàn tất và so sánh từng key lẫn tổng.

Các điều cần xác minh:

1. Mỗi input event được xử lý đúng một lần trong test.
2. Tổng số đếm bằng số event đầu vào.
3. Tổng các nhóm bằng tổng chung sau khi workers hoàn tất.
4. Key không xuất hiện không được tự tạo mapping.
5. Key trùng lặp được cộng đúng số lần.
6. Supplier của value được gọi đúng API; không chia sẻ một LongAdder sai cách cho mọi key.
7. Exception trong worker không bị bỏ qua.
8. Snapshot được đọc sau ranh giới hoàn tất nếu cần kết quả cuối chính xác.

Không dùng Thread.sleep() để đoán rằng workers đã xong. Dùng Future.get(), CountDownLatch, Phaser hoặc cơ chế hoàn tất có semantics rõ ràng.

### 17.1. Kiểm thử nhiều lần và nhiều phân bố key

Một lần chạy thành công chưa đủ để phát hiện mọi race condition. Hãy lặp test với:

- Một key duy nhất để tạo contention cao.
- Nhiều key phân bố đều.
- Một số key rất nóng, nhiều key hiếm.
- Input rỗng và input một phần tử.
- Số lượng event không chia hết cho số worker.
- Nhiều worker hơn số key.
- Nhiều worker hơn số phần tử.

Test với một key duy nhất đặc biệt hữu ích để làm lộ lỗi lost update trong implementation dùng get rồi put.

### 17.2. Kiểm thử snapshot trong lúc writers còn hoạt động

Nếu sản phẩm cần dashboard hoặc endpoint đọc số liệu khi workers đang cập nhật, hãy xác định rõ consistency mong muốn. LongAdder.sum() và iteration trên ConcurrentHashMap có thể phản ánh trạng thái đang thay đổi; chúng phù hợp với metrics gần thời gian thực, không tạo snapshot transaction nhất quán trên toàn bộ map.

Nếu cần snapshot chính xác, hãy thiết kế điểm đồng bộ hoặc copy-on-write/epoch phù hợp. Đừng chỉ gọi sum() nhiều lần rồi giả định các kết quả thuộc cùng một thời điểm.

## 18. Hiệu năng, contention và bộ nhớ

### 18.1. Hot key

Nếu phần lớn event có cùng key, nhiều thread sẽ cập nhật cùng một value. LongAdder được thiết kế để giảm contention cho bộ đếm nóng. AtomicLong đơn giản hơn nhưng có thể tạo điểm tranh chấp trên cùng một biến.

### 18.2. High cardinality

Nếu mỗi event tạo một key mới, map tăng kích thước liên tục. LongAdder cho mỗi key cũng tiêu tốn bộ nhớ. Cần xác định:

- Key có miền hữu hạn hay không.
- Khi nào một key hết hạn.
- Có thể chuẩn hóa hoặc gom nhóm key không.
- Có cần giới hạn số lượng key.
- Cách xóa/reset có phối hợp với writers đang chạy không.

### 18.3. Không reset tùy tiện để chia cửa sổ thời gian

Gọi sumThenReset() trong lúc update có thể làm ranh giới sự kiện giữa hai cửa sổ không rõ ràng. Nếu cần số liệu theo phút/giờ, hãy cân nhắc map theo bucket/epoch, thay thế accumulator theo chu kỳ với quy trình phối hợp, hoặc một hệ thống metrics đã hỗ trợ window aggregation.

### 18.4. Benchmark bằng workload thực

Đừng kết luận LongAdder luôn nhanh hơn AtomicLong hoặc groupingByConcurrent luôn nhanh hơn merge. Kết quả phụ thuộc số thread, phân bố key, tỷ lệ đọc/ghi, chi phí tạo event, garbage collection và phần cứng.

Dùng JMH cho microbenchmark với warmup, measurement và forks. Benchmark cần so sánh cùng dữ liệu và cùng semantics; không trộn console I/O vào phép đo cập nhật bộ đếm.

## 19. Những lỗi thường gặp và cách sửa

1. **Dùng count++ trên biến long chia sẻ.** Read-modify-write không nguyên tử; dùng LongAdder, AtomicLong hoặc khóa.
2. **Cho rằng volatile long làm count++ an toàn.** volatile không làm phép cộng thành atomic.
3. **Dùng HashMap trong nhiều writer.** Dùng ConcurrentHashMap hoặc đồng bộ hóa toàn bộ thao tác đúng cách.
4. **Dùng get() rồi put() để tăng count.** Hai thao tác có thể xen kẽ; dùng merge, compute hoặc LongAdder.
5. **Cho rằng ConcurrentHashMap làm value object thread-safe.** Value mutable cần cơ chế riêng.
6. **Dùng ArrayList trong map đồng thời rồi cùng gọi add.** Map an toàn không bảo vệ list.
7. **Dùng LongAdder.sum() làm quyết định chính xác trong lúc update.** Kết quả đang chạy không phải snapshot nguyên tử.
8. **Dùng LongAdder để cấp sequence duy nhất.** Dùng AtomicLong và incrementAndGet().
9. **Reset adder khi workers vẫn chạy.** Có thể làm mất hoặc phân loại sai update; cần ranh giới đồng bộ.
10. **Dùng mảng một phần tử để lách effectively final.** Mảng vẫn là shared mutable state không an toàn.
11. **Dùng parallelStream().forEach với map thường.** Chọn collector hoặc concurrent map/value phù hợp.
12. **Cho rằng mỗi method call của map tạo thành transaction nhiều bước.** Chỉ semantics của từng API atomic được bảo đảm.
13. **Xóa key trong lúc thread đang giữ LongAdder cũ.** Có thể chia update giữa adder cũ và mới.
14. **Bỏ qua exception trong Future.** Gọi get() để phát hiện lỗi worker.
15. **Dùng sleep để chờ xử lý xong.** Dùng Future/latch/phaser.
16. **Đọc map khi writer vẫn chạy rồi so với tổng như snapshot.** Chỉ so sánh sau barrier hoặc dùng snapshot protocol.
17. **Đếm lại event khi retry mà không deduplicate.** Retry có thể làm tăng số đếm hai lần.
18. **Coi counter là cơ chế exactly-once.** Counter chỉ đếm lần xử lý; cần event ID/idempotency store nếu yêu cầu chống trùng.
19. **Không giới hạn key cardinality.** Map và bộ đếm theo key có thể tăng bộ nhớ không giới hạn.
20. **Dùng LongAdder cho phép cập nhật có điều kiện.** Dùng AtomicLong hoặc lock khi cần CAS/threshold semantics.
21. **Dùng groupingByConcurrent mà không đo hot key.** Một key nóng vẫn có contention.
22. **Tính tổng bằng shared counter trong khi collector đã làm được việc đó.** Dùng collect, count hoặc numeric reduction nếu phù hợp.
23. **Giả định hai bộ đếm cập nhật cùng lúc tạo snapshot nhất quán.** Cập nhật map và total là hai thao tác riêng.
24. **Không xác định overflow policy.** Bộ đếm long có thể tràn; nếu cần phát hiện overflow, thiết kế phép cập nhật có kiểm tra và đồng bộ phù hợp.
25. **Đánh giá hiệu năng bằng một lần chạy.** Dùng benchmark lặp lại với workload gần thực tế.

## 20. Chọn semantics theo yêu cầu nghiệp vụ

Trước khi chọn API, trả lời các câu hỏi:

- Bạn cần đếm tổng hay theo nhiều key?
- Có bao nhiêu writer cùng cập nhật?
- Key có nóng hay phân bố đều?
- Cần đọc trong lúc cập nhật hay chỉ sau khi hoàn tất?
- Giá trị đọc cần chính xác nguyên tử hay chỉ là metric gần thời gian thực?
- Có cần cấp sequence hoặc kiểm tra threshold?
- Có retry hoặc event trùng lặp không?
- Có cần snapshot nhất quán giữa tổng và từng nhóm?
- Key có thể tăng không giới hạn không?
- Có thể biểu diễn bằng Stream collector thay cho side effect không?

Những câu trả lời này quyết định nên dùng LongAdder, AtomicLong, ConcurrentHashMap.merge, map chứa adder hay groupingByConcurrent.

## 21. Câu hỏi ôn luyện và đáp án

**1. Vì sao count++ không an toàn khi nhiều thread cùng chạy?**  
Vì đây là chuỗi đọc, cộng và ghi; hai thread có thể đọc cùng giá trị rồi ghi đè kết quả.

**2. volatile có sửa được lost update không?**  
Không. volatile hỗ trợ visibility/order, không biến increment thành atomic.

**3. Vì sao HashMap không phù hợp cho nhiều writer?**  
Nó không hỗ trợ sửa đổi cấu trúc đồng thời nếu không có đồng bộ hóa bên ngoài.

**4. ConcurrentHashMap bảo vệ điều gì?**  
Các thao tác map được hỗ trợ đồng thời; value mutable vẫn cần thread-safety riêng.

**5. Dùng API nào để tăng giá trị Long trong map nguyên tử?**  
merge(key, 1L, Long::sum) hoặc compute(...).

**6. Vì sao get rồi put vẫn sai?**  
Vì cả chuỗi không nguyên tử; cập nhật của thread khác có thể chen giữa.

**7. LongAdder phù hợp với tình huống nào?**  
Nhiều thread thường xuyên cập nhật một bộ đếm, chủ yếu đọc tổng sau hoặc trong quá trình thống kê.

**8. Khi nào nên chọn AtomicLong?**  
Khi cần CAS, cấp sequence duy nhất, cập nhật có điều kiện hoặc đọc giá trị nguyên tử làm quyết định.

**9. LongAdder.sum() có phải snapshot nguyên tử khi writers còn chạy?**  
Không. Sau khi writers hoàn tất, tổng mới ổn định để kiểm tra kết quả cuối.

**10. Tại sao map chứa LongAdder phù hợp với frequency map?**  
Map quản lý mapping theo key; mỗi LongAdder hỗ trợ nhiều thread tăng bộ đếm của key đó.

**11. ConcurrentHashMap có làm ArrayList trong value thread-safe không?**  
Không. Value phải tự có cơ chế đồng bộ phù hợp.

**12. computeIfAbsent nên dùng mapping function như thế nào?**  
Ngắn, đơn giản, không cập nhật đệ quy trên chính map; tạo new LongAdder() là phù hợp.

**13. groupingByConcurrent() trả về loại kết quả nào?**  
Một ConcurrentMap<K, D> và collector concurrent, unordered.

**14. Khi nào dùng groupingByConcurrent thay cho shared map?**  
Khi đầu vào là stream và mục tiêu là nhóm/tổng hợp sau pipeline.

**15. Vì sao biến local long total không thể tăng trong lambda?**  
Biến được capture phải final hoặc effectively final.

**16. Mảng một phần tử có giải quyết concurrency không?**  
Không. Nó chỉ lách giới hạn capture; thao tác tăng vẫn có race condition.

**17. Vì sao phải gọi Future.get() trong ví dụ?**  
Để đợi worker hoàn tất và truyền exception của worker về thread chính.

**18. Vì sao TreeMap chỉ được tạo sau khi worker kết thúc?**  
Để tạo snapshot có thứ tự ổn định trên một thread, không phải map dùng để cập nhật đồng thời.

**19. Counter có bảo đảm event được xử lý exactly-once không?**  
Không. Retry hoặc event trùng có thể làm tăng nhiều lần; cần idempotency/deduplication theo event ID.

**20. Cần làm gì nếu cần snapshot nhất quán giữa total và mọi key khi hệ thống vẫn chạy?**  
Thiết kế barrier, lock hoặc epoch/snapshot protocol; các LongAdder riêng lẻ không tạo transaction chung.

## 22. Tài liệu API chính thức

- [ConcurrentHashMap — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): các thao tác nguyên tử compute, computeIfAbsent, merge và semantics truy cập đồng thời.
- [LongAdder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): increment, add, sum, reset, contention và semantics đọc tổng.
- [AtomicLong — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): CAS, increment, add và atomic update.
- [LongAccumulator — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): phép tích lũy tổng quát với identity.
- [Collectors — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): groupingBy, groupingByConcurrent, counting và các downstream collector.
- [ConcurrentHashMap — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentHashMap.html): xác nhận các API concurrent map dùng trong ví dụ đã có từ Java 8.
- [LongAdder — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/LongAdder.html): xác nhận bộ đếm phân tán đã có từ Java 8.
- [Stream — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): collect, parallel stream và các thao tác reduction.

Các API trong chương trình mẫu đều có từ Java 8. Không cần Hashtable, Vector, API nội bộ của JDK hoặc thư viện đã deprecated để đếm sự kiện đồng thời.

**Nguyên tắc cuối:** map phải an toàn cho cập nhật theo key, value phải an toàn cho việc tích lũy, và kết quả chỉ được coi là snapshot cuối sau khi có ranh giới hoàn tất rõ ràng. Với nhiều writer và bộ đếm metrics, ConcurrentHashMap<K, LongAdder> là mẫu thực dụng; với CAS/sequence dùng AtomicLong, còn với stream aggregation hãy cân nhắc groupingByConcurrent().
