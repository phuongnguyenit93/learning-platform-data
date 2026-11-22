# Phân biệt an toàn từng thao tác với an toàn cả chuỗi thao tác

## 1. Vấn đề cần hiểu trước khi chọn collection

Giả sử một bộ đếm lượt truy cập được lưu trong map. Mỗi yêu cầu đọc số hiện tại, cộng một, rồi ghi trở lại. Bạn thay `HashMap` bằng `ConcurrentHashMap`, nhưng tổng cuối cùng vẫn thấp hơn số yêu cầu đã xử lý. Điều này có thể xảy ra dù từng lần `get` và `put` đều được thực hiện đúng theo hợp đồng của map.

Điểm mấu chốt là **ranh giới thao tác mà collection bảo vệ có thể nhỏ hơn ranh giới công việc mà chương trình cần bảo vệ**. “Tăng bộ đếm một lần” là một công việc; “đọc một giá trị” và “ghi một giá trị” là hai lần gọi riêng. Luồng khác có thể chạy vào khoảng giữa chúng.

Bài học này tập trung vào việc xác định và thu hẹp khoảng trống đó trong Java Collections. Sau khi học, bạn cần làm được bốn việc:

- Chỉ ra điều kiện phải luôn đúng khi nhiều luồng cùng làm việc.
- Viết một lịch xen kẽ khiến chuỗi thao tác hiện tại sai.
- Chọn phương thức gộp sẵn hoặc khóa chung bao phủ đúng công việc.
- Kiểm tra cả đường đọc, đường ghi và đối tượng phần tử, thay vì chỉ nhìn tên lớp collection.

Kiến thức nền cần có là `Map`, `List`, `Queue`, tham chiếu đối tượng, lambda và cách đọc một khối `synchronized`. Các chương trình dùng cú pháp/API tương thích Java 17 trở lên. Không cần biết cách JVM triển khai bảng băm hay mã máy để theo dõi lập luận.

### 1.1. Các khái niệm liên quan

| Khái niệm | Câu hỏi nó trả lời | Ví dụ trong bài |
| --- | --- | --- |
| An toàn đa luồng (thread safety) | Đối tượng có giữ đúng hợp đồng khi nhiều luồng sử dụng theo cách được quy định không? | Hai luồng cùng gọi `ConcurrentHashMap.put` |
| Tính nguyên tử (atomicity) | Một công việc có được quan sát như một bước không bị chen ngang trong phạm vi đã cam kết không? | Gộp “đọc số cũ rồi cộng một” bằng `merge` |
| Tính nhìn thấy (visibility) | Luồng đọc có quan hệ đồng bộ cần thiết để thấy dữ liệu đã được công bố không? | Đọc kết quả sau khi tác vụ hoàn tất qua `Future.get` |
| Điều kiện bất biến (invariant) | Điều gì phải đúng ở mọi trạng thái mà bên sử dụng được phép quan sát? | Tổng số chỗ của hai ngăn luôn bằng 20 |
| Thao tác ghép (compound action) | Công việc nào gồm nhiều bước phụ thuộc lẫn nhau? | Kiểm tra chưa có rồi thêm, hoặc đọc hai khóa rồi tính tổng |
| Giao thức đồng bộ | Các bên phải tuân thủ quy tắc phối hợp nào? | Mọi lần di chuyển và đọc tổng đều giữ cùng một khóa |

Tính nguyên tử luôn cần một phạm vi cụ thể: một lần cập nhật, một khóa, một collection, hay cả nhiều đối tượng. Không nên dùng từ “atomic” mà bỏ qua phạm vi đó.

Một collection an toàn đa luồng không tự nhận biết quy tắc nghiệp vụ của chương trình. Nó không biết hai khóa `left` và `right` phải giữ tổng bằng 20, cũng không biết một tên chỉ được đăng ký một lần nếu bạn tự ghép `contains` với `add`.

## 2. Vì sao nhiều thao tác an toàn vẫn tạo thành chuỗi sai?

### 2.1. Đọc–sửa–ghi có thể làm mất cập nhật

Đoạn sau là **mã minh họa cố ý sai khi nhiều luồng cùng tăng**, không phải một chương trình độc lập:

```java
int before = counts.get("hits");
counts.put("hits", before + 1);
```

Giả sử `counts` là `ConcurrentHashMap<String, Integer>` và đã chứa `"hits" -> 0`. Hai luồng có thể thực hiện:

| Bước | Luồng A | Luồng B | Giá trị trong map |
| --- | --- | --- | --- |
| 1 | Đọc được 0 | Chưa đọc | 0 |
| 2 | Giữ số 0 trong biến cục bộ | Đọc được 0 | 0 |
| 3 | Tính 0 + 1, ghi 1 | Giữ số 0 trong biến cục bộ | 1 |
| 4 | Đã xong | Tính 0 + 1, ghi 1 | 1 |

Hai lần tăng đã hoàn thành nhưng chỉ còn kết quả 1. Map không làm sai một lần `put` nào: cả hai luồng đều yêu cầu ghi 1. Sai sót nằm trong cách chương trình tạo ra hai giá trị mới từ cùng một giá trị cũ.

Đây là **mất cập nhật (lost update)**. Việc viết gọn thành `counts.put("hits", counts.get("hits") + 1)` chỉ giảm số dòng, không gộp hai lần gọi thành một thao tác nguyên tử. Ý tưởng đọc–tính–ghi cũng giải thích vì sao `x++` không tự trở thành nguyên tử. [Oracle: Thread Interference](https://docs.oracle.com/javase/tutorial/essential/concurrency/interfere.html)

### 2.2. Kiểm tra–rồi–làm phụ thuộc vào một quan sát đã cũ

Một ví dụ khác là **kiểm tra rồi hành động (check-then-act)**. Đoạn minh họa dưới đây cũng cố ý để lộ khoảng tranh chấp:

```java
if (!registrations.containsKey("seat-7")) {
    registrations.put("seat-7", "Lan");
}
```

Luồng A thấy chỗ trống. Trước khi A ghi, luồng B đăng ký chỗ đó cho `"Minh"`. Sau đó A ghi `"Lan"` và thay thế đăng ký của B. Nếu quy tắc là “chỉ người đầu tiên được đăng ký”, cách cài đặt này sai.

Không có hai khóa `"seat-7"` trong map; map vẫn giữ quy tắc mỗi khóa có tối đa một ánh xạ. **Không trùng khóa của map** và **không ghi đè người đã đăng ký** là hai điều kiện khác nhau. Một phép `put` luôn có thể thay giá trị tại khóa đã tồn tại.

Một giá trị trả về từ `isEmpty`, `containsKey`, `size` hay `get` là một quan sát. Muốn dùng nó để quyết định một thay đổi tiếp theo, cần chứng minh điều kiện đó vẫn được bảo vệ cho tới lúc thay đổi xảy ra.

### 2.3. Race condition không đồng nghĩa với data race

Trong bài, **lỗi phụ thuộc lịch chạy (race condition)** nghĩa là tính đúng đắn phụ thuộc vào cách các bước của nhiều luồng xen kẽ. Hai luồng dùng hoàn toàn những API an toàn của `ConcurrentHashMap` vẫn có thể tạo ra loại lỗi này.

**Tranh chấp dữ liệu theo mô hình bộ nhớ Java (data race)** có nghĩa hẹp hơn: hai truy cập xung đột không được sắp thứ tự bởi quan hệ happens-before. Không nên suy luận “không có data race trên cấu trúc map” thành “quy trình đăng ký chắc chắn đúng”.

Theo JLS, mở khóa một monitor tạo quan hệ happens-before với lần khóa tiếp theo trên chính monitor đó. Quy tắc này phục vụ việc phối hợp thứ tự và nhìn thấy dữ liệu; chương trình vẫn phải đặt đủ các bước cần bảo vệ trong phạm vi khóa. [JLS 17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

### 2.4. `final` và `volatile` không tự bảo vệ chuỗi thao tác

`final Map<...>` ngăn gán lại biến tham chiếu sau khi khởi tạo theo quy tắc của `final`; nó không biến map thành bất biến. Một biến tham chiếu `volatile` giúp phối hợp việc công bố/thay thế tham chiếu, nhưng không khiến `get` rồi `put`, hoặc `contains` rồi `add`, thành một thao tác duy nhất.

Tương tự, một bộ đếm khai báo `volatile int` vẫn cần cơ chế phù hợp nếu nhiều luồng cùng tăng bằng `++`. Khả năng nhìn thấy của từng truy cập không thay thế việc gộp toàn bộ bước đọc–sửa–ghi. [Oracle: Atomic Access](https://docs.oracle.com/javase/tutorial/essential/concurrency/atomic.html)

Vì vậy, khi xem xét một lỗi, hãy hỏi riêng hai câu: “dữ liệu được công bố/đọc bằng cơ chế nào?” và “những bước phụ thuộc nhau được gộp bằng cơ chế nào?”. Trả lời câu thứ nhất chưa đủ để trả lời câu thứ hai.

## 3. Thí nghiệm: cùng một lỗi với concurrent map và synchronized map

Chương trình đầy đủ sau ép hai luồng **đều đọc số 0 trước khi bất kỳ luồng nào ghi**. `CyclicBarrier` là điểm hẹn của hai tác vụ. Không dùng `Thread.sleep` và không trông chờ chạy nhiều lần để tình cờ thấy lỗi.

Chương trình thử bốn trường hợp:

1. `ConcurrentHashMap` với `get`/`put` tách rời.
2. `Collections.synchronizedMap` với `get`/`put` tách rời.
3. `ConcurrentHashMap.merge` để gộp tăng theo khóa.
4. Khối `synchronized` bao trọn đọc–sửa–ghi trên synchronized map.

Lưu thành **`AtomicStepDemo.java`**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AtomicStepDemo {
    private static final int REPETITIONS = 2_000;

    public static void main(String[] args) throws Exception {
        Map<String, Integer> concurrent = new ConcurrentHashMap<>();
        Map<String, Integer> wrapped =
                Collections.synchronizedMap(new HashMap<>());

        System.out.println("concurrent split = " + forceLostUpdate(concurrent));
        System.out.println("wrapped split = " + forceLostUpdate(wrapped));

        ConcurrentHashMap<String, Integer> merged = new ConcurrentHashMap<>();
        runTwice(() -> {
            for (int i = 0; i < REPETITIONS; i++) {
                merged.merge("hits", 1, Integer::sum);
            }
        });
        require(merged.get("hits") == 2 * REPETITIONS, "merge lost an update");
        System.out.println("concurrent merge = " + merged.get("hits"));

        Map<String, Integer> guarded =
                Collections.synchronizedMap(new HashMap<>());
        guarded.put("hits", 0);
        runTwice(() -> {
            for (int i = 0; i < REPETITIONS; i++) {
                synchronized (guarded) {
                    int before = guarded.get("hits");
                    guarded.put("hits", before + 1);
                }
            }
        });
        require(guarded.get("hits") == 2 * REPETITIONS, "guard lost an update");
        System.out.println("wrapped whole block = " + guarded.get("hits"));
    }

    private static int forceLostUpdate(Map<String, Integer> map)
            throws Exception {
        map.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(() -> {
                int before = map.get("hits");
                bothRead.await(5, TimeUnit.SECONDS);
                map.put("hits", before + 1);
                return null;
            });
            Future<?> second = pool.submit(() -> {
                int before = map.get("hits");
                bothRead.await(5, TimeUnit.SECONDS);
                map.put("hits", before + 1);
                return null;
            });
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            int result = map.get("hits");
            require(result == 1, "the forced schedule did not occur");
            return result;
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void runTwice(Runnable action) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(action);
            Future<?> second = pool.submit(action);
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AtomicStepDemo.java
java AtomicStepDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
concurrent split = 1
wrapped split = 1
concurrent merge = 4000
wrapped whole block = 4000
```

Hai dòng đầu luôn là 1 trong lịch mà chương trình ép được: mỗi luồng giữ một biến cục bộ `before = 0`, rồi cả hai ghi `1`. Thứ tự hai lần ghi không làm thay đổi kết quả này.

Hai dòng cuối là 4.000 vì có hai tác vụ, mỗi tác vụ tăng 2.000 lần. Ở trường hợp `merge`, thay đổi được gửi cho map dưới dạng một phép gộp. Ở trường hợp khóa ngoài, luồng thứ hai không thể chen vào giữa lần đọc và lần ghi của luồng đang giữ monitor.

`Collections.synchronizedMap` không tự giữ monitor từ lúc trả về `get` cho đến một lần `put` sau đó. Hai lần gọi của người dùng tạo hai phạm vi bảo vệ riêng. Chỉ khi khối bên ngoài bao cả chuỗi, khoảng trống giữa chúng mới được che phủ.

Điểm hẹn chỉ đặt trong trường hợp cố ý sai. **Không chuyển barrier vào bên trong khối giữ cùng một khóa**: tác vụ đầu có thể giữ khóa rồi chờ tác vụ thứ hai, trong khi tác vụ thứ hai đang chờ chính khóa đó. Khi đó thiết kế thử nghiệm tạo bế tắc thay vì chứng minh tính đúng đắn.

Theo hợp đồng, `CyclicBarrier` cho phép một nhóm luồng chờ nhau tại một điểm. `Future.get` nhận kết quả hoặc lỗi của tác vụ; các hành động của tác vụ xảy ra-trước các hành động sau lần `get` tương ứng. [CyclicBarrier Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html), [Future Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

Các thời hạn trong mã là để bài thử báo lỗi thay vì chờ vô hạn nếu môi trường không chạy được tác vụ. Chúng không phải điều kiện tạo ra lịch xen kẽ. Phần `finally` dừng nhóm luồng; ngoại lệ chờ/biên dịch/chạy không bị bỏ qua để in một kết quả có vẻ thành công.

## 4. Cách sửa thứ nhất: dùng thao tác gộp phù hợp

### 4.1. Chọn API diễn đạt đúng điều kiện cần bảo vệ

Với `ConcurrentMap`, một số thao tác có điều kiện được thiết kế để thực hiện nguyên tử. Đừng dựng lại chúng bằng nhiều lần `get`, `containsKey`, `put` hoặc `remove`:

| Ý định | Chuỗi tự ghép có khoảng trống | API cần xem xét |
| --- | --- | --- |
| Chỉ đăng ký khi chưa có khóa | `containsKey` rồi `put` | `putIfAbsent(key, value)` |
| Chỉ xóa nếu giá trị vẫn là giá trị đã biết | `get` rồi so sánh rồi `remove(key)` | `remove(key, expectedValue)` |
| Chỉ thay nếu giá trị chưa đổi | `get` rồi so sánh rồi `put` | `replace(key, expectedValue, newValue)` |

Giá trị trả về cho biết kết quả của thao tác có điều kiện. Đoạn sau là **mã minh họa**, giả sử `registrations` là `ConcurrentHashMap<String, String>` dùng chung:

```java
String previous = registrations.putIfAbsent("seat-7", "Lan");
if (previous == null) {
    System.out.println("Dang ky thanh cong");
} else {
    System.out.println("Cho da duoc dang ky");
}
```

Trong ví dụ này, `null` biểu thị không có giá trị cũ, vì loại map đang dùng không chứa giá trị null. Một khóa có thể được xóa rồi đăng ký lại trong tương lai nếu ứng dụng cho phép; thành công của lần gọi này không phải lời bảo đảm “chỗ đó thuộc về Lan mãi mãi”.

Các biến thể có điều kiện trên được quy định trong hợp đồng `ConcurrentMap`. Dùng kết quả của chính thao tác đó để quyết định nhánh tiếp theo. [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

### 4.2. Cập nhật theo giá trị hiện tại bằng `compute` hoặc `merge`

Với `ConcurrentHashMap`, có thể diễn đạt tăng bộ đếm theo khóa bằng một trong hai đoạn minh họa sau:

```java
counts.merge("hits", 1, Integer::sum);

counts.compute("hits", (key, oldValue) ->
        oldValue == null ? 1 : oldValue + 1);
```

Đây là **hai cách thay thế**, không phải hai dòng cần chạy cho một lượt truy cập; chạy cả hai sẽ tăng hai lần. Trong đoạn này, `counts` là `ConcurrentHashMap<String, Integer>`.

`merge` dùng giá trị 1 khi chưa có ánh xạ; khi đã có, nó kết hợp số cũ với 1. `compute` nhận cả trường hợp chưa có và đã có. `computeIfAbsent` thích hợp để tạo ánh xạ còn thiếu, không phải để tăng mọi lượt truy cập.

Trên `ConcurrentHashMap`, các lần gọi `compute`/`computeIfAbsent`/`merge` có cam kết nguyên tử cho phép cập nhật ánh xạ đang xét. Hàm trả về null có thể làm không tạo hoặc xóa ánh xạ tùy phương thức. Hàm tính cần ngắn, không sửa map đang tính; một số cập nhật khác có thể phải chờ. [ConcurrentHashMap — compute và merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#compute(K,java.util.function.BiFunction))

Cách sửa này vẫn đòi hỏi mọi đường tăng bộ đếm dùng quy tắc tương thích. Nếu một đường khác còn chạy `get` rồi `put` với số cũ, nó vẫn có thể ghi đè kết quả của một lần `merge`. Đổi một chỗ gọi không tự sửa những chỗ gọi khác.

### 4.3. Kiểu khai báo `Map` không tự mang bảo đảm của mọi lớp triển khai

Cần đọc hợp đồng lớp thực tế:

```java
Map<String, Integer> a = new HashMap<>();
Map<String, Integer> b = new ConcurrentHashMap<>();
```

Đây là **hai khai báo minh họa**, cần import tương ứng. Cả hai đều gọi được `merge`, nhưng tên phương thức giống nhau không chứng minh cùng mức bảo đảm đồng bộ. Nhiều phương thức mặc định của `Map`, bao gồm các phương thức tính/cập nhật, không cam kết đồng bộ hay nguyên tử; lớp triển khai phải quy định hành vi của nó. [Map Java 17 — các phương thức mặc định](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction))

Việc khai báo `b` bằng `Map` không làm mất cách cài đặt của `ConcurrentHashMap`: Java vẫn chọn phương thức ghi đè của đối tượng thực tế. Tuy nhiên, nếu hợp đồng của một thành phần chỉ nói “nhận một Map bất kỳ”, bên sử dụng không có cơ sở mặc định rằng tất cả đối tượng được truyền vào đều an toàn khi chia sẻ giữa các luồng.

Khi thiết kế API, hãy nêu rõ cần `ConcurrentMap`, một đối tượng cụ thể với cam kết đã biết, hay một map chỉ được truy cập dưới khóa riêng. Kiểu và tài liệu hợp đồng nên làm rõ yêu cầu này cho người gọi.

### 4.4. Tính nguyên tử của cập nhật không đồng nghĩa tác dụng phụ xảy ra đúng một lần

Một hàm tính nên chỉ xây dựng/biến đổi kết quả cục bộ rồi trả về. Không nên suy từ “ánh xạ được cập nhật nguyên tử” sang “gửi thông báo, trừ tiền bên ngoài, hoặc gọi dịch vụ từ xa đúng một lần”.

Các phương thức mặc định `compute`/`merge` của `ConcurrentMap` có thể thử lại và gọi hàm tính nhiều lần khi cạnh tranh. Riêng `ConcurrentHashMap.computeIfAbsent` gọi hàm một lần trong một lần gọi phương thức nếu khóa vắng, và không gọi hàm nếu khóa đã có giá trị; đây không phải cam kết chỉ chạy hàm một lần trong suốt đời khóa. [ConcurrentMap — merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#merge(K,V,java.util.function.BiFunction)), [ConcurrentHashMap — computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

Ví dụ, hàm tạo có thể trả về null, ném ngoại lệ, hoặc ánh xạ được xóa để lần gọi sau tạo lại. Nếu bạn làm một tác dụng phụ trước khi hàm thất bại, một thay đổi đối với map không tự hoàn tác tác dụng phụ đó.

Cũng không gọi `compute` trên map khác trong khi tùy tiện giữ khóa hay chờ tác vụ khác. Một tác vụ A giữ tài nguyên X và chờ Y, trong khi tác vụ B giữ Y và chờ X, có thể tạo vòng chờ. Đưa một công việc dài vào hàm tính còn khiến phần cần phối hợp bị giữ lâu hơn. Việc tải dữ liệu chậm cần một thiết kế quản lý vòng đời tác vụ riêng nếu yêu cầu ứng dụng đòi hỏi, không thể giải quyết chỉ bằng đổi tên phương thức map.

## 5. Cách sửa thứ hai: giữ một khóa cho toàn bộ chuỗi

### 5.1. Với synchronized wrapper, khóa đúng đối tượng trả về

Giả sử danh sách được tạo và công bố an toàn bằng:

```java
List<String> names =
        Collections.synchronizedList(new ArrayList<>());
```

Muốn thực hiện quy tắc “chưa có thì thêm”, đoạn minh họa dưới đây giữ monitor của chính `names` cho cả hai bước:

```java
synchronized (names) {
    if (!names.contains("Lan")) {
        names.add("Lan");
    }
}
```

Điều kiện là tất cả bên sử dụng phải truy cập danh sách qua wrapper đó và tuân thủ cùng giao thức cho các công việc ghép. Một luồng gọi `add` trực tiếp vẫn có thể thêm trùng sau khi khối này kết thúc; khóa không biến `List` thành `Set` và không cấm một thao tác mà chương trình vẫn cho phép.

Tương tự, nếu dữ liệu gốc bị giữ ở nơi khác rồi sửa trực tiếp, wrapper không thể bắt đường truy cập đó phải chờ monitor của nó.

Đối với các synchronized wrapper, tài liệu yêu cầu mọi truy cập cấu trúc nền đi qua đối tượng trả về. Khi duyệt bằng iterator/spliterator/stream, người dùng phải tự giữ khóa phù hợp. Với view của synchronized map, khóa map trả về, không khóa riêng `keySet`/`entrySet`. [Collections — synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

### 5.2. Khóa từng đoạn nhỏ vẫn để hở phần quyết định

Đoạn **minh họa cố ý sai về phạm vi khóa** sau vẫn có khoảng trống:

```java
int before;
synchronized (counts) {
    before = counts.get("hits");
}

synchronized (counts) {
    counts.put("hits", before + 1);
}
```

Giữa hai khối, một luồng khác có thể cập nhật giá trị. Biến cục bộ `before` không tự đổi theo map. Cần bao cả quyết định và cập nhật trong cùng lần giữ khóa.

Khóa cũng cần đúng **danh tính đối tượng**, không chỉ có cùng tên hay cùng nội dung:

- Hai đối tượng `new Object()` khác nhau là hai khóa khác nhau.
- Khóa map nền không đồng nghĩa khóa synchronized wrapper.
- Tạo một wrapper mới quanh cùng map ở mỗi lần gọi không tạo ra một khóa chung.
- Khóa `this` của hai đối tượng dịch vụ khác nhau không tạo loại trừ lẫn nhau giữa chúng.

Khả năng tái nhập của monitor cho phép cùng luồng đã giữ monitor gọi tiếp phương thức cũng dùng monitor đó. Nó không khiến hai monitor khác nhau trở thành một khóa chung. [JLS 17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)

### 5.3. Khóa ngoài quanh concurrent collection chỉ có tác dụng khi các bên hợp tác

Bạn có thể xây dựng một quy tắc dùng `synchronized (guard)` quanh một `ConcurrentHashMap`. Nhưng các luồng khác chỉ gọi `map.put` mà không lấy `guard` sẽ không tự chờ khóa ngoài đó.

Đặc biệt, `synchronized (concurrentMap)` không phải lệnh yêu cầu lớp đó dừng mọi cập nhật nội bộ. `ConcurrentHashMap` không cung cấp khóa toàn bảng chặn mọi truy cập theo cách này. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Nếu đã có một khóa chung bao toàn bộ thao tác và toàn bộ đường truy cập, một `HashMap` riêng tư có thể đáp ứng thiết kế đó. Khi ấy tính an toàn nằm ở lớp bao và giao thức khóa. Cần ngăn map thoát ra ngoài để người gọi không vô tình tạo một đường đi vòng.

Khi nhiều đối tượng cần khóa riêng, thứ tự lấy khóa phải nhất quán để tránh vòng chờ. Với một bài toán nhỏ, khóa chung thường dễ lập luận hơn; chỉ tách khóa khi bạn đã xác định rõ điều kiện bất biến và cách mọi đường truy cập phối hợp.

## 6. Một khóa nguyên tử không bảo vệ được điều kiện liên quan nhiều khóa

### 6.1. Hai lần `compute` vẫn là hai lần cập nhật

Giả sử có hai ngăn lưu số chỗ `left` và `right`. Ban đầu mỗi ngăn có 10 chỗ; công việc “di chuyển một chỗ từ trái sang phải” cần giữ điều kiện:

```text
left + right = 20
```

Bạn có thể viết hai phép `compute` an toàn theo từng khóa, nhưng vẫn tạo ra một trạng thái trung gian:

```java
slots.compute("left", (key, value) -> value - 1);
slots.compute("right", (key, value) -> value + 1);
```

Đoạn này là **mã minh họa cố ý chưa bảo vệ bất biến nhiều khóa**, với `slots` là `ConcurrentHashMap<String, Integer>` đã có hai khóa.

Sau dòng thứ nhất, trạng thái là `left = 9, right = 10`. Sau dòng thứ hai, trạng thái là `left = 9, right = 11`. Cả hai phép tính từng khóa đều đúng, nhưng một người đọc giữa hai dòng có thể thấy tổng 19.

Đọc tổng cũng là một chuỗi: `get("left")` rồi `get("right")`. Ngay cả khi hai lần cập nhật được đặt gần nhau và không cố ý dừng giữa chừng, một phép đọc ghép không được phối hợp vẫn có thể trộn quan sát từ hai giai đoạn.

Điều ứng dụng cần bảo vệ là **phép di chuyển và phép chụp hai số liên quan**, không chỉ các lần ghi từng số. Nguyên tử trên một khóa không tự mở rộng sang khóa thứ hai.

### 6.2. Thí nghiệm quan sát trạng thái trung gian và lớp bao có khóa chung

Chương trình sau có hai nửa:

- Nửa đầu dùng concurrent map và hai latch để người đọc chắc chắn chạy giữa hai cập nhật.
- Nửa sau đặt map riêng tư trong `SlotStore`. Cả `move` lẫn `snapshot` giữ cùng `guard`, và chỉ trả ra một record gồm hai số nguyên.

Lưu thành **`CollectionInvariantDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CollectionInvariantDemo {
    private static final int CHECKS = 1_000;

    public static void main(String[] args) throws Exception {
        showIntermediateState();
        showGuardedState();
    }

    private static void showIntermediateState() throws Exception {
        ConcurrentHashMap<String, Integer> slots = new ConcurrentHashMap<>();
        slots.put("left", 10);
        slots.put("right", 10);
        CountDownLatch firstWrite = new CountDownLatch(1);
        CountDownLatch readFinished = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> writer = pool.submit(() -> {
                slots.compute("left", (key, value) -> value - 1);
                firstWrite.countDown();
                await(readFinished);
                slots.compute("right", (key, value) -> value + 1);
                return null;
            });
            Future<Integer> reader = pool.submit(() -> {
                await(firstWrite);
                try {
                    return slots.get("left") + slots.get("right");
                } finally {
                    readFinished.countDown();
                }
            });
            int observed = reader.get(10, TimeUnit.SECONDS);
            writer.get(10, TimeUnit.SECONDS);
            require(observed == 19, "intermediate state was not observed");
            System.out.println("separate compute, observed total = " + observed);
            System.out.println("separate compute, final total = "
                    + (slots.get("left") + slots.get("right")));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void showGuardedState() throws Exception {
        SlotStore slots = new SlotStore();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> writer = pool.submit(() -> {
                await(start);
                for (int i = 0; i < CHECKS; i++) {
                    slots.move("left", "right");
                    slots.move("right", "left");
                }
                return null;
            });
            Future<Integer> reader = pool.submit(() -> {
                await(start);
                for (int i = 0; i < CHECKS; i++) {
                    Snapshot snapshot = slots.snapshot();
                    require(snapshot.total() == 20, "broken invariant");
                }
                return CHECKS;
            });
            start.countDown();
            int checks = reader.get(10, TimeUnit.SECONDS);
            writer.get(10, TimeUnit.SECONDS);
            Snapshot last = slots.snapshot();
            require(last.left() == 10 && last.right() == 10, "wrong final state");
            System.out.println("guarded snapshots checked = " + checks);
            System.out.println("guarded final = " + last);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static final class SlotStore {
        private final Object guard = new Object();
        private final Map<String, Integer> values = new HashMap<>();

        private SlotStore() {
            values.put("left", 10);
            values.put("right", 10);
        }

        private void move(String from, String to) {
            if (from.equals(to)) {
                throw new IllegalArgumentException("distinct slots required");
            }
            synchronized (guard) {
                Integer source = values.get(from);
                Integer target = values.get(to);
                if (source == null || target == null || source <= 0) {
                    throw new IllegalStateException("invalid move");
                }
                values.put(from, source - 1);
                values.put(to, target + 1);
            }
        }

        private Snapshot snapshot() {
            synchronized (guard) {
                return new Snapshot(values.get("left"), values.get("right"));
            }
        }
    }

    private record Snapshot(int left, int right) {
        private int total() {
            return left + right;
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all CollectionInvariantDemo.java
java CollectionInvariantDemo
```

Stdout khi chạy thành công:

```text
separate compute, observed total = 19
separate compute, final total = 20
guarded snapshots checked = 1000
guarded final = Snapshot[left=10, right=10]
```

Ở nửa đầu, `firstWrite` mở sau khi giảm ngăn trái. Luồng ghi chờ `readFinished`, nên không tăng ngăn phải trước khi luồng đọc lấy tổng. Kết quả 19 được tạo bởi quan hệ phối hợp rõ ràng, không dựa vào tốc độ máy.

Ở nửa sau, tác vụ ghi di chuyển sang phải rồi chuyển lại, lặp 1.000 lần. Tác vụ đọc kiểm tra 1.000 bản chụp. Mỗi bản chụp có thể thấy `10/10` hoặc `9/11`, nhưng tổng luôn là 20. Kết quả cuối `10/10` được đọc sau khi tác vụ ghi hoàn thành.

Đường đọc cũng lấy `guard` nên không được vào giữa hai lần `put` của một phép di chuyển. Nếu `snapshot` bỏ khóa, lập luận này mất cơ sở dù `move` vẫn còn `synchronized`.

Record `Snapshot` giữ hai giá trị `int`, không trả map nội bộ hay một `Map.Entry` sống. Sau khi thoát khóa, người đọc chỉ tính toán trên bản chụp của chính mình; tác vụ ghi sau đó không sửa được hai thành phần của record này.

`CountDownLatch` cung cấp cổng chờ một lần và quan hệ công bố dữ liệu qua `countDown`/`await` theo hợp đồng của nó. Trong thí nghiệm, latch dùng để điều khiển thứ tự, còn `guard` là cơ chế bảo vệ bất biến của lớp bao. [CountDownLatch Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

### 6.3. Điều gì thực sự chứng minh bản sửa?

Thí nghiệm là minh chứng chạy được, còn lý do đúng nằm trong cấu trúc lớp:

1. `values` là riêng tư và không được trả ra.
2. Mọi phương thức sau khởi tạo có đọc/sửa trạng thái đều giữ cùng `guard`.
3. Kiểm tra nguồn còn chỗ và cả hai lần ghi đều nằm trong một khối.
4. Người đọc lấy hai số dưới cùng khóa rồi trả ra dữ liệu độc lập.
5. Hai tác vụ chỉ nhận đối tượng sau khi nó đã được khởi tạo, qua cơ chế gửi tác vụ của executor.

Từ đó có thể xét từng lần di chuyển như một chuyển đổi giữa hai trạng thái hợp lệ đối với các bên tuân thủ giao thức. Một người đọc chỉ thấy trước hoặc sau lần di chuyển.

Trong ví dụ, các tên ngăn được xác định trước, số lượng nhỏ và phép tính không thể tràn `int`. Nếu mở rộng thành API tổng quát, phải xác định thêm miền giá trị, kiểm tra tràn số, quy tắc thêm/xóa ngăn và cách xử lý lỗi trước khi thay đổi trạng thái. Giữ khóa không tự cung cấp hoàn tác nếu bạn sửa được một nửa rồi ném ngoại lệ.

### 6.4. Đôi khi nên đổi cách biểu diễn trạng thái

Nếu nhiều dữ liệu luôn phải thay đổi cùng nhau, có thể gom chúng thành **một giá trị bất biến** rồi thay cả giá trị đó theo một thao tác có bảo đảm phù hợp. Ví dụ, lưu một record chứa cả hai số dưới một khóa, hoặc dùng `AtomicReference` tới trạng thái bất biến.

`AtomicReference` hỗ trợ cập nhật nguyên tử một tham chiếu. Điều đó có thể phù hợp khi ranh giới nghiệp vụ trùng với toàn bộ giá trị mà tham chiếu trỏ tới. [AtomicReference Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)

Đây là một lựa chọn thiết kế, không phải lời khuyên đưa mọi dữ liệu của chương trình vào một đối tượng khổng lồ. Cần cân nhắc kích thước bản sao, tần suất cập nhật và mức cạnh tranh. Nếu record vẫn chứa một danh sách có thể sửa được từ bên ngoài, riêng việc record không có setter chưa làm toàn bộ đồ thị đối tượng bất biến.

Với bài toán trong chương trình, một khóa chung và dữ liệu riêng tư đã đủ đơn giản để chứng minh. Chưa có lý do phải triển khai thêm giao thức nhiều khóa hoặc thuật toán thử lại phức tạp.

## 7. Map an toàn không tự làm đối tượng giá trị an toàn

### 7.1. `computeIfAbsent` chỉ gộp phần tạo/lấy ánh xạ

Đoạn minh họa sau rất dễ bị hiểu quá mức:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
groups.computeIfAbsent("team-a", key -> new ArrayList<>()).add("Lan");
```

Đây là **đoạn minh họa có vấn đề khi nhiều luồng cùng sửa danh sách**, cần import tương ứng. Có hai công việc nối nhau:

1. Tạo hoặc lấy tham chiếu danh sách trong map.
2. Gọi `add` lên danh sách được trả về.

Phần `add` xảy ra trên `ArrayList`, sau khi phương thức của map đã trả về. Những luồng cùng nhận được danh sách đó không tự có một giao thức bảo vệ cấu trúc danh sách. `ArrayList` yêu cầu đồng bộ bên ngoài khi được nhiều luồng truy cập và có ít nhất một luồng sửa cấu trúc. [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Hãy vẽ ranh giới đối tượng để nhận ra điều này:

```text
ConcurrentHashMap
    "team-a" -> tham chieu -> ArrayList dung chung

Bao ve anh xa khong tu bao ve moi thay doi trong ArrayList.
```

Đổi map bên ngoài không sửa hợp đồng của đối tượng bên trong. Ngược lại, bọc danh sách bên trong cũng chỉ giải quyết những thao tác mà wrapper của danh sách bảo vệ; một chuỗi `size`/`get`/`remove` khác vẫn cần xem lại.

### 7.2. Một cách giải quyết: thay giá trị bất biến theo khóa

Nếu yêu cầu là “thêm một thành viên và mọi người đọc nhận được danh sách không sửa được của một phiên bản”, đoạn minh họa dưới đây gom việc xây dựng phiên bản mới vào `compute`:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();

groups.compute("team-a", (key, oldMembers) -> {
    List<String> next = oldMembers == null
            ? new ArrayList<>()
            : new ArrayList<>(oldMembers);
    next.add("Lan");
    return List.copyOf(next);
});
```

Đây là **đoạn mã minh họa không độc lập**. Giả định quan trọng là mọi giá trị đã có trong map cũng tuân thủ chính sách không cho sửa, thành viên là `String` không null, và mọi đường thêm đều dùng giao thức tương thích.

`next` là danh sách mới chỉ dùng cục bộ trong lần tính. Không sửa `oldMembers`, nên một luồng đã giữ phiên bản cũ vẫn có thể đọc phiên bản đó theo hợp đồng đã định. Người đọc lấy được một tham chiếu danh sách là lấy một phiên bản, không phải giữ quyền ngăn phiên bản mới thay nó trong map. `List.copyOf` tạo danh sách không cho sửa và không nhận phần tử null. [List.copyOf Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

Chi phí là phải sao chép danh sách cho mỗi lần thay đổi. Nếu phần tử là đối tượng có trạng thái thay đổi, sao chép danh sách chỉ sao chép tham chiếu; cần quy tắc riêng cho trạng thái phần tử.

Một lựa chọn khác là giá trị cũng có cơ chế đồng bộ riêng, chẳng hạn collection concurrent phù hợp. Tuy vậy, khi yêu cầu liên quan cả ánh xạ và vòng đời giá trị, vẫn phải xem xét phép xóa/thay giá trị trong map.

### 7.3. Giá trị `AtomicInteger` cũng có ranh giới vòng đời

Với bộ đếm, có thể dùng đoạn minh họa:

```java
ConcurrentHashMap<String, AtomicInteger> counters = new ConcurrentHashMap<>();
AtomicInteger counter =
        counters.computeIfAbsent("hits", key -> new AtomicInteger());
counter.incrementAndGet();
```

`AtomicInteger.incrementAndGet` gộp việc tăng trên chính đối tượng bộ đếm. [AtomicInteger Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html#incrementAndGet())

Nhưng một luồng khác có thể xóa ánh xạ `"hits"` sau khi luồng đầu lấy `counter` và trước khi nó tăng. Khi đó số vẫn tăng đúng trên đối tượng đã nhận, nhưng đối tượng ấy có thể không còn là giá trị hiện tại trong map.

Vì thế, cách này có thể phù hợp nếu ánh xạ bộ đếm được giữ ổn định và yêu cầu cho phép đếm theo vòng đời đó. Nếu quy tắc là “mỗi lần tăng phải cập nhật chính giá trị đang đăng ký tại khóa, phối hợp với cả xóa/reset”, cần xác định lại giao thức; chỉ ghép hai đối tượng an toàn không chứng minh toàn bộ công việc.

`LongAdder` hay một collection concurrent bên trong không tự xóa vấn đề vòng đời này. Điều cần làm trước là định nghĩa ý nghĩa của xóa, reset, thay phiên bản và những thao tác đang thực hiện.

## 8. Duyệt an toàn và đọc bản chụp nhất quán là hai yêu cầu khác nhau

### 8.1. Duyệt synchronized wrapper phải giữ khóa cho cả lượt duyệt

Đoạn minh họa sau cho thấy cách lấy bản sao của synchronized map:

```java
Map<String, Integer> shared =
        Collections.synchronizedMap(new HashMap<>());

Map<String, Integer> snapshot;
synchronized (shared) {
    snapshot = new HashMap<>(shared);
}
```

Đây là **đoạn mã minh họa**, với mọi truy cập map nền đều qua cùng wrapper. Việc sao chép diễn ra trong khối khóa, nên các thao tác sửa qua wrapper ở luồng khác phải chờ. Sau đó có thể duyệt `snapshot` ngoài khóa nếu bản sao chỉ do luồng hiện tại dùng hoặc được công bố bằng giao thức phù hợp.

Muốn duyệt trực tiếp view, giữ khóa map cho **cả** quá trình tạo và sử dụng iterator:

```java
synchronized (shared) {
    for (Map.Entry<String, Integer> entry : shared.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

Đoạn này chỉ minh họa phạm vi khóa; không hứa thứ tự in của `HashMap`. Với view từ synchronized sorted/navigable wrapper, cần tuân thủ khóa của wrapper gốc theo tài liệu. Không đổi khóa sang đối tượng view chỉ vì vòng lặp đang duyệt view đó. [Collections Java 17 — quy tắc duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Giữ khóa trong lúc in, gọi hàm bên ngoài hoặc làm việc chậm có thể kéo dài thời gian chờ của bên khác. Khi yêu cầu cho phép, lấy bản chụp cần thiết dưới khóa rồi xử lý bản chụp ở ngoài thường làm phạm vi giữ khóa dễ kiểm soát hơn.

Bản sao của map vẫn chỉ độc lập về các ánh xạ và cấu trúc chứa. Trong ví dụ này `String` và `Integer` không đổi trạng thái, nên không có phần tử có thể sửa bên ngoài làm thay đổi số đã chụp. Với giá trị khác, phải xét độ sâu của bản chụp.

### 8.2. Concurrent traversal không mặc định là ảnh chụp toàn bộ tại một thời điểm

Iterator của nhiều collection concurrent được quy định là nhất quán yếu (weakly consistent): có thể duyệt khi cấu trúc đang thay đổi mà không mang ngữ nghĩa ảnh chụp bất biến toàn bộ. [java.util.concurrent — Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

Vì vậy, việc `new HashMap<>(concurrentMap)` tạo một map mới không tự chứng minh dữ liệu nguồn là ảnh chụp toàn cục tại một thời điểm. Bản đích có thể giữ nguyên kết quả sao chép sau đó, nhưng tính ổn định của bản đích và tính nhất quán của thời điểm lấy dữ liệu nguồn là hai câu hỏi khác nhau.

Cũng không dùng `size() == 0` hoặc `isEmpty()` như một quyền giữ chỗ để thao tác sau. Trong `ConcurrentHashMap`, các phép quan sát tổng hợp khi có cập nhật đồng thời chỉ phản ánh trạng thái tạm thời; `putAll`/`clear` không cung cấp một giao dịch toàn map cho người đọc đồng thời. [ConcurrentHashMap Java 17 — trạng thái tổng hợp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Nếu ứng dụng cần đối chiếu toàn bộ dữ liệu cùng một phiên bản, hãy định nghĩa cơ chế riêng: cùng khóa cho cả ghi và chụp, trạng thái bất biến theo phiên bản, hoặc một thiết kế lưu trữ có ranh giới giao dịch thích hợp.

### 8.3. Iterator dạng snapshot cũng không gộp các lời gọi khác nhau

`CopyOnWriteArrayList` có iterator nhìn phiên bản mảng tại lúc iterator được tạo. Nhưng `contains("Lan")` rồi `add("Lan")` là hai lời gọi khác nhau; một iterator có ảnh chụp không biến chuỗi đó thành thêm có điều kiện.

Lớp này có `addIfAbsent` để diễn đạt phép thêm nếu chưa có. Ảnh chụp cấu trúc cũng không sao chép sâu trạng thái của các đối tượng phần tử. [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#addIfAbsent(E))

Tương tự, gọi `get(0)` sau một lần `isEmpty()` trên danh sách có thể là hai quan sát khác thời điểm; sự an toàn của từng phương thức không giữ chỉ số còn hợp lệ đến lần gọi tiếp theo.

Không có `ConcurrentModificationException` cũng không chứng minh quy trình đúng. Ngược lại, không nên dùng ngoại lệ đó làm cơ chế đồng bộ hay làm bằng chứng rằng mọi lỗi tranh chấp chắc chắn sẽ được phát hiện. Iterator của từng loại collection có hợp đồng riêng; cơ chế fail-fast là để phát hiện lỗi theo khả năng tốt nhất, không phải một giao thức giữ bất biến. [HashMap Java 17 — fail-fast iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 9. Queue: lấy kết quả của thao tác nhận việc, không giữ một quan sát cũ

### 9.1. `isEmpty` không giữ lại phần tử cho người vừa kiểm tra

Đoạn minh họa sau cố ý để lộ lỗi khi hai bên cùng lấy việc từ queue:

```java
if (!jobs.isEmpty()) {
    String job = jobs.remove();
}
```

Với `ConcurrentLinkedQueue`, luồng A có thể thấy queue còn việc; luồng B lấy mất phần tử cuối; sau đó A gọi `remove` trên queue trống. `remove` ném `NoSuchElementException` trong trường hợp trống, còn `poll` trả về null. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

Một lần lấy không chờ nên dựa vào **kết quả của chính `poll`**. Đoạn minh họa dưới đây chưa gồm phần xử lý công việc:

```java
String job = jobs.poll();
if (job != null) {
    System.out.println("Da nhan: " + job);
} else {
    System.out.println("Hien chua co viec");
}
```

Giả sử `jobs` là `ConcurrentLinkedQueue<String>`. Loại queue này không cho phần tử null, nên null biểu thị lần lấy không nhận được phần tử. `size` của nó còn cần duyệt và không đáng dùng làm phép giữ chỗ khi có thay đổi đồng thời. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)

Khi hai luồng cùng `poll` một phần tử duy nhất, một bên lấy được việc, bên còn lại nhận null. Đây có thể là kết quả hoàn toàn đúng của một giao thức lấy việc không chờ. Không cần một câu hỏi `isEmpty` trước đó.

Tuy nhiên, null chỉ cho biết **lần lấy đó** không có phần tử. Nó không chứng minh nhà sản xuất đã hoàn tất hay hệ thống sẽ không có việc mới. Dừng một nhóm tác vụ tiêu thụ cần một quy tắc kết thúc riêng.

### 9.2. Nếu cần chờ, dùng thao tác chờ đúng nghĩa

Với `BlockingQueue`, chọn `take()` khi cần chờ tới khi lấy được phần tử; chọn `poll(timeout, unit)` khi có giới hạn chờ. Khi thêm, `offer` trả kết quả thành công/thất bại; `put` có thể chờ chỗ trống. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Quan sát `remainingCapacity() > 0` rồi `add` không giữ chỗ cho luồng hiện tại. Một bên khác có thể thêm trước. Hãy quyết định theo kết quả của `offer` hoặc theo giao thức chờ `put` phù hợp.

Nếu API trả về `InterruptedException`, cần truyền ngoại lệ lên tầng có trách nhiệm hoặc khôi phục cờ ngắt khi chuyển cách báo lỗi theo thiết kế. Không bắt rồi bỏ qua để tiếp tục như đã nhận được việc.

Cũng không giữ một khóa bên ngoài rồi gọi `take` vô thời hạn nếu nhà sản xuất phải lấy chính khóa đó để đưa việc vào. Thiết kế ấy có thể giữ khóa trong khi chờ một điều kiện mà chính nó ngăn bên khác tạo ra.

Nhận một phần tử an toàn không đồng nghĩa xử lý bên ngoài queue thành công đúng một lần. Nếu luồng lấy việc rồi lỗi trước khi lưu kết quả, cơ chế khôi phục/ghi nhận hoàn thành thuộc giao thức xử lý công việc, không phải bảo đảm của `poll`.

## 10. Thí nghiệm: queue và danh sách copy-on-write

Chương trình đầy đủ dưới đây kiểm chứng hai kiểu “kiểm tra rồi làm”:

- Queue: kiểm tra còn phần tử, để bên khác lấy hết, rồi `remove`.
- Danh sách: hai bên cùng xác nhận chưa có tên, rồi cả hai `add`.

Các trường hợp đúng dùng `poll` và `addIfAbsent`. Tác vụ nào thắng có thể thay đổi theo lịch chạy; stdout chỉ ghi các kết quả tổng hợp không phụ thuộc danh tính bên thắng.

Lưu thành **`CollectionProtocolDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CollectionProtocolDemo {
    public static void main(String[] args) throws Exception {
        showQueueRace();
        showSinglePoll();
        showListRace();
        showAddIfAbsent();
    }

    private static void showQueueRace() throws Exception {
        ConcurrentLinkedQueue<String> jobs = new ConcurrentLinkedQueue<>();
        jobs.add("job-1");
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch removed = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> {
                boolean wasNonEmpty = !jobs.isEmpty();
                checked.countDown();
                await(removed);
                if (wasNonEmpty) {
                    try {
                        return jobs.remove();
                    } catch (NoSuchElementException ex) {
                        return "NoSuchElementException";
                    }
                }
                return "unexpected empty observation";
            });
            Future<String> second = pool.submit(() -> {
                await(checked);
                try {
                    return jobs.poll();
                } finally {
                    removed.countDown();
                }
            });
            String removedJob = second.get(10, TimeUnit.SECONDS);
            String firstResult = first.get(10, TimeUnit.SECONDS);
            require("job-1".equals(removedJob), "wrong removed job");
            require("NoSuchElementException".equals(firstResult), "race not shown");
            System.out.println("check then remove = " + firstResult);
        } finally {
            stop(pool);
        }
    }

    private static void showSinglePoll() throws Exception {
        ConcurrentLinkedQueue<String> jobs = new ConcurrentLinkedQueue<>();
        jobs.add("job-1");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> jobs.poll());
            Future<String> second = pool.submit(() -> jobs.poll());
            String a = first.get(10, TimeUnit.SECONDS);
            String b = second.get(10, TimeUnit.SECONDS);
            int claimed = (a == null ? 0 : 1) + (b == null ? 0 : 1);
            int empty = (a == null ? 1 : 0) + (b == null ? 1 : 0);
            require(claimed == 1 && empty == 1, "wrong poll outcome");
            require("job-1".equals(a) || "job-1".equals(b), "wrong job");
            System.out.println("poll: claimed = " + claimed + ", empty = " + empty);
        } finally {
            stop(pool);
        }
    }

    private static void showListRace() throws Exception {
        CopyOnWriteArrayList<String> names = new CopyOnWriteArrayList<>();
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(() -> {
                boolean absent = !names.contains("Lan");
                bothChecked.await(5, TimeUnit.SECONDS);
                if (absent) {
                    names.add("Lan");
                }
                return null;
            });
            Future<?> second = pool.submit(() -> {
                boolean absent = !names.contains("Lan");
                bothChecked.await(5, TimeUnit.SECONDS);
                if (absent) {
                    names.add("Lan");
                }
                return null;
            });
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            require(names.size() == 2, "duplicate schedule not shown");
            System.out.println("contains then add = " + names);
        } finally {
            stop(pool);
        }
    }

    private static void showAddIfAbsent() throws Exception {
        CopyOnWriteArrayList<String> names = new CopyOnWriteArrayList<>();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> first = pool.submit(() -> names.addIfAbsent("Lan"));
            Future<Boolean> second = pool.submit(() -> names.addIfAbsent("Lan"));
            boolean a = first.get(10, TimeUnit.SECONDS);
            boolean b = second.get(10, TimeUnit.SECONDS);
            require(a != b && names.size() == 1, "wrong conditional add");
            System.out.println("addIfAbsent = " + names);
        } finally {
            stop(pool);
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void stop(ExecutorService pool) throws InterruptedException {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("pool did not terminate");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all CollectionProtocolDemo.java
java CollectionProtocolDemo
```

Stdout khi chạy thành công:

```text
check then remove = NoSuchElementException
poll: claimed = 1, empty = 1
contains then add = [Lan, Lan]
addIfAbsent = [Lan]
```

Ở trường hợp queue sai, latch `checked` cho phép bên thứ hai lấy việc chỉ sau khi bên thứ nhất quan sát queue còn phần tử. Latch `removed` chỉ cho bên thứ nhất tiếp tục khi việc đã bị lấy. Vì vậy, ngoại lệ phản ánh đúng khoảng hở giữa hai lần gọi.

Khối `catch` ở đây chỉ chuyển ngoại lệ thành kết quả để quan sát trong bài thử. Nó không phải cách sửa giao thức lấy việc. Bản sửa là quyết định bằng kết quả của một lần `poll`.

Ở trường hợp danh sách sai, barrier bảo đảm cả hai đều có `absent = true` trước khi thêm. Hai lần `add` hợp lệ tạo ra `[Lan, Lan]`. Danh sách không bị hỏng; quy tắc không thêm trùng do chương trình tự đặt mới là thứ bị vi phạm.

Ở bản dùng `addIfAbsent`, hai giá trị boolean trả về phải khác nhau và danh sách có đúng một tên. Điều này không hứa tên không bao giờ bị xóa/thêm lại sau đó. Nếu một đường khác vẫn gọi `add("Lan")` trực tiếp, quy tắc không trùng có thể lại bị phá.

Nhìn hai ví dụ cạnh nhau sẽ thấy cùng một lỗi thiết kế dưới hai hình thức: **đọc một điều kiện, nhả quyền phối hợp, rồi hành động như thể điều kiện còn nguyên**. Thao tác có điều kiện gộp sẵn có giá trị vì nó đặt kiểm tra và thay đổi vào cùng ranh giới bảo vệ.

## 11. Quy trình phân tích một chuỗi thao tác trong mã thực tế

### 11.1. Viết yêu cầu thành điều kiện có thể kiểm tra

Trước khi chọn `ConcurrentHashMap`, `synchronized` hay `CopyOnWriteArrayList`, hãy viết yêu cầu cụ thể. Ví dụ:

- Mỗi lần tăng hoàn tất đóng góp đúng một đơn vị, nếu không có thao tác reset/xóa.
- Một đăng ký không ghi đè đăng ký đang tồn tại.
- Một phép di chuyển không cho người đọc quan sát tổng khác 20.
- Mỗi lần lấy việc nhận tối đa một phần tử hoặc nhận kết quả không có việc.
- Một danh sách thành viên không chứa hai phần tử bằng nhau theo quy tắc đã chọn.

Không phải yêu cầu nào cũng cần một ảnh chụp toàn hệ thống. Ngược lại, nếu yêu cầu cần nhiều dữ liệu cùng một phiên bản, một phép đọc an toàn từng phần sẽ chưa đáp ứng.

### 11.2. Liệt kê mọi bước và điểm có thể xen kẽ

Chuyển một dòng viết gọn thành các hành động rõ ràng. Với `put(key, get(key) + 1)`, tách thành đọc, tính, ghi. Với `if (size() < limit) add(x)`, tách thành đo kích thước, so sánh, thêm.

Sau đó thử đặt một thao tác của luồng khác vào mỗi khoảng giữa. Nếu tạo được lịch hợp lệ khiến điều kiện sai, bạn đã có một phản ví dụ. Không cần chứng minh lỗi “thường xuyên xảy ra” mới sửa.

Nếu không tìm được lịch sai, vẫn phải đọc hợp đồng: có thể còn vấn đề công bố dữ liệu, phần tử có thể sửa, đường đi vòng hoặc ngoại lệ giữa chừng mà cách tách bước ban đầu chưa tính đến.

### 11.3. Chọn ranh giới bảo vệ nhỏ nhất đủ đáp ứng yêu cầu

| Phạm vi của điều kiện | Cơ chế có thể phù hợp | Điều cần kiểm chứng thêm |
| --- | --- | --- |
| Một cập nhật theo khóa | `putIfAbsent`, `replace`, `remove` có điều kiện, hoặc `compute`/`merge` trên lớp phù hợp | Cam kết lớp thực tế, giá trị trả về, quy tắc xóa/thay |
| Một chuỗi trên synchronized wrapper | Khóa chính wrapper cho toàn chuỗi | Không có đường sửa map/list nền bên ngoài |
| Nhiều khóa hoặc nhiều collection | Lớp bao riêng tư với khóa chung, hoặc thiết kế trạng thái gộp | Mọi người đọc và ghi cùng giao thức |
| Trạng thái trong một phần tử | Phần tử bất biến hoặc cơ chế đồng bộ riêng | Không lộ tham chiếu cho phép sửa ngoài giao thức |
| Lấy một việc hiện có | `poll` trên concurrent queue thích hợp | Xử lý null và vòng đời nhà sản xuất |
| Chờ việc/chỗ trống | Thao tác chờ của `BlockingQueue` | Ngắt, thời hạn, kết thúc và khóa đang giữ |
| Đọc toàn bộ dữ liệu cùng phiên bản | Chụp dưới khóa chung hoặc công bố trạng thái bất biến | Độ sâu bản sao và mọi đường cập nhật |

Đây là cách chọn theo yêu cầu. Không có cơ chế trong bảng tự bao phủ tất cả các hàng khác.

### 11.4. Đóng gói giao thức để người gọi khó dùng sai

Một dịch vụ chỉ cung cấp `increase`, `registerIfAbsent`, `move` và `snapshot` thường dễ kiểm soát hơn việc trả map sống rồi yêu cầu mọi nơi nhớ cùng một quy tắc khóa.

Nếu một đối tượng bị chia sẻ rộng, hãy rà soát cả:

- Chỗ tạo và công bố đối tượng cho các luồng.
- Phương thức đọc, ghi, xóa, reset và các thao tác hàng loạt.
- View, iterator và tham chiếu phần tử thoát ra ngoài.
- Hàm callback có gọi mã khác hoặc thực hiện tác dụng phụ.
- Đường đọc báo cáo dùng nhiều khóa để suy luận một điều kiện.
- Hành vi khi công việc bị ngắt, hết thời gian hoặc ném ngoại lệ.

Khóa riêng tư giúp giới hạn người phối hợp; trả về bản chụp cần thiết giúp giới hạn khả năng sửa ngoài ý muốn. Nếu buộc phải công khai collection, tài liệu của API cần mô tả đủ ranh giới và trách nhiệm của người gọi.

### 11.5. Kiểm thử phải đi cùng lập luận

Ba chương trình của bài ép các lịch sai cụ thể, rồi kiểm tra kết quả của cách sửa. Chúng phù hợp để học vì hành vi sai không phụ thuộc may rủi và lỗi tác vụ được chuyển về luồng chính.

Một lần chạy được 4.000 không tự chứng minh mọi cách cài đặt bộ đếm đều đúng. Một bài thử chạy hàng triệu lần không thấy lỗi cũng chưa loại bỏ được lịch chưa xuất hiện. Bằng chứng chính vẫn là hợp đồng API, phạm vi khóa, tính riêng tư của trạng thái và việc mọi đường truy cập tuân thủ cùng giao thức.

Không dùng `sleep`, tốc độ in log hay việc “máy của tôi chỉ có một lõi” để chứng minh không có tranh chấp. Đồng thời, không đặt thao tác chờ của bài thử vào trong vùng khóa theo cách làm thay đổi bản chất giao thức cần kiểm chứng.

## 12. Luyện tập và tự kiểm tra

### Bài 1 — Giới hạn số phần tử

Một `CopyOnWriteArrayList<String>` được dùng chung. Hai luồng chạy đoạn mã minh họa sau, với giới hạn 10:

```java
if (names.size() < 10) {
    names.add(candidate);
}
```

**Yêu cầu:** Khi danh sách đang có 9 phần tử và hai ứng viên khác nhau, hãy viết lịch làm kích thước thành 11. `addIfAbsent` có sửa đúng quy tắc giới hạn không?

**Đối chiếu:** Hai luồng đều có thể quan sát kích thước 9 rồi lần lượt thêm. `addIfAbsent` chỉ gộp kiểm tra phần tử bằng nhau và thêm, không kiểm tra giới hạn 10. Cần một cơ chế chung bao cả phép kiểm tra sức chứa và thêm, được mọi đường cập nhật tuân thủ; hoặc đổi sang cấu trúc/giao thức có giới hạn phù hợp với yêu cầu.

### Bài 2 — Khóa đúng bên ghi nhưng sai bên đọc

`move` dùng một khóa chung để sửa hai khóa. `total` chạy `map.get("left") + map.get("right")` mà không lấy khóa. Map là `ConcurrentHashMap`.

**Yêu cầu:** Phần nào của điều kiện “luôn đọc tổng bằng 20” còn thiếu?

**Đối chiếu:** Người đọc không tham gia giao thức bảo vệ bất biến. Nó vẫn có thể quan sát giữa hai lần ghi hoặc kết hợp dữ liệu từ hai thời điểm. Cần lấy cùng khóa cho toàn lần đọc, trả bản chụp được tạo dưới khóa, hoặc biểu diễn hai số thành một trạng thái gộp có cơ chế thay thế phù hợp.

### Bài 3 — Ánh xạ và đối tượng bên trong

Một dịch vụ tạo danh sách bằng `computeIfAbsent`, rồi trả `List<String>` đó cho người gọi. Dịch vụ tự dùng `compute` cho mọi lần sửa về sau.

**Yêu cầu:** Điều gì xảy ra nếu người gọi giữ và sửa danh sách đã nhận?

**Đối chiếu:** Một đường sửa có thể đi ngoài giao thức của dịch vụ. `compute` ở các đường khác không khóa mọi hành động trên danh sách đã thoát ra. Cần thiết kế giá trị bất biến/không cho sửa, bản sao có độ sâu phù hợp, hoặc API không trả tham chiếu sửa được. Cũng cần xem bản không cho sửa có còn phản ánh một cấu trúc nền đang thay đổi hay không.

### Bài 4 — Một dòng tăng atomic nhưng reset đồng thời

Map lưu `AtomicInteger`. Luồng A lấy bộ đếm, luồng B xóa khóa rồi tạo bộ đếm mới, luồng A tăng đối tượng cũ.

**Yêu cầu:** Lần tăng có bị mất trên chính đối tượng cũ không? Nó có nhất thiết xuất hiện khi đọc bộ đếm hiện tại trong map không?

**Đối chiếu:** Phép tăng trên đối tượng cũ vẫn có thể hoàn toàn đúng và nguyên tử. Nhưng map có thể đã trỏ sang đối tượng mới, nên người đọc theo khóa không thấy lần tăng ấy. Cần định nghĩa reset/xóa có ý nghĩa gì đối với thao tác đang chạy và chọn ranh giới phối hợp bao được ý nghĩa đó.

### Bài 5 — Queue tạm thời trống

Một tác vụ gọi `poll()`, nhận null rồi đóng toàn bộ hệ thống tiêu thụ; nhà sản xuất vẫn đang hoạt động.

**Yêu cầu:** Cách lấy đã an toàn, vậy vì sao quy trình vẫn có thể sai?

**Đối chiếu:** An toàn của một lần lấy không định nghĩa điều kiện kết thúc luồng công việc. Null phản ánh lần lấy hiện tại. Hệ thống cần tín hiệu hoàn tất, hủy hoặc một giao thức kết thúc khác, kết hợp với việc các nhà sản xuất thực sự đã dừng.

## 13. Tài liệu để kiểm tra hợp đồng khi áp dụng

Các ví dụ và lịch xen kẽ trong bài là minh họa tự xây dựng. Khi đổi lớp collection hoặc phiên bản Java, hãy đối chiếu đúng hợp đồng của lớp/phương thức đang dùng:

- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): synchronized wrapper và khóa khi duyệt.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): thao tác có điều kiện và hành vi mặc định của hàm tính.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): phạm vi nguyên tử của cập nhật theo khóa và giới hạn quan sát toàn map.
- [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html), [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): nhận/thêm bằng kết quả thao tác và biến thể chờ.
- [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): iterator dạng snapshot và `addIfAbsent`.
- [JLS chương 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitor, thứ tự và mô hình bộ nhớ Java.

