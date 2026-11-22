# putIfAbsent, compute, merge và tính nguyên tử theo khóa

Một bộ đếm dùng chung cần tăng từ giá trị hiện tại. Một bộ nhớ đệm cần tạo dữ liệu khi chưa có. Một mục trạng thái cần được tính lại hoặc xóa tùy kết quả kiểm tra. Những bài toán ấy đều có điểm chung: quyết định ghi phụ thuộc vào trạng thái đang lưu.

Nếu đọc trạng thái bằng một lời gọi rồi ghi bằng lời gọi khác, luồng khác có thể thay đổi dữ liệu ở giữa. **Tính nguyên tử theo khóa** giúp gộp quyết định và thay đổi của một ánh xạ thành thao tác có hợp đồng rõ ràng. Nó không làm mọi công việc quanh map trở thành một giao dịch.

Bài học dùng `ConcurrentHashMap` của Java 17 làm đối tượng chính khi nói về các lời gọi `compute` và `merge` nguyên tử. Đồng thời phân biệt với `Map` nói chung và những triển khai `ConcurrentMap` khác, vì bảo đảm về hàm tính có thể khác nhau.

Các khái niệm cần nhận diện:

- **Ứng viên:** giá trị bên gọi đã tính sẵn và muốn đưa vào map.
- **Hàm tính ánh xạ:** hàm được truyền cho map để tính giá trị từ khóa hoặc từ giá trị hiện tại.
- **Giá trị đầu vào để gộp:** dữ liệu mới truyền cho `merge`, sẽ được lưu trực tiếp khi khóa vắng hoặc kết hợp với giá trị cũ khi đã có.
- **Nguyên tử của ánh xạ:** điều kiện và cập nhật trên khóa được phối hợp theo hợp đồng của phương thức.
- **Tác dụng bên ngoài:** việc gửi thông báo, sửa đối tượng khác, ghi file hoặc gọi hệ thống khác; chúng không tự thuộc giao dịch của map.
- **Vòng đời ánh xạ:** quá trình tạo, cập nhật, xóa và có thể tạo lại cùng khóa.

Hãy bắt đầu từ ý nghĩa dữ liệu cần cập nhật, rồi chọn API. Việc dùng một cấu trúc an toàn giữa nhiều luồng mới là nền tảng; cách ghép các lời gọi vẫn quyết định kết quả.

## 1. Khoảng trống giữa đọc và ghi

Giả sử `totals` là `ConcurrentHashMap<String, Integer>` và khóa `"visits"` đang có giá trị `10`:

~~~java
int old = totals.get("visits");
totals.put("visits", old + 1);
~~~

Đây là đoạn minh họa trong phương thức, không phải chương trình độc lập. Một lịch thực thi hợp lệ có thể là:

~~~text
Luồng A đọc 10
Luồng B đọc 10
Luồng A ghi 11
Luồng B ghi 11
~~~

Có hai yêu cầu tăng, nhưng số cuối là `11`. Không cần map hỏng hoặc có ngoại lệ mới xảy ra sai số. Từng lời gọi đã thực hiện đúng, còn cả chuỗi đọc rồi ghi chưa phải một thao tác nguyên tử.

Với `ConcurrentHashMap`, có thể diễn đạt một lần tăng bằng:

~~~java
totals.compute("visits", (key, old) -> old == null ? 1 : old + 1);
~~~

Hoặc:

~~~java
totals.merge("visits", 1, Integer::sum);
~~~

Hai cách trên có thể cùng diễn đạt bộ đếm bắt đầu từ `1` khi khóa vắng. Nhưng chúng không có cùng hình dạng đầu vào và cách gọi hàm; phải hiểu các nhánh trước khi dùng cho bài toán phức tạp hơn.

## 2. Bản đồ chọn API

Bảng dưới áp dụng cho `ConcurrentHashMap`, nơi không lưu giá trị `null`.

| API | Khi khóa vắng | Khi khóa đã có | Kết quả trả về |
|---|---|---|---|
| `putIfAbsent(k, candidate)` | Thêm ứng viên. | Giữ giá trị hiện có. | Giá trị trước đó, hoặc `null` khi vừa thêm. |
| `computeIfAbsent(k, loader)` | Gọi hàm theo khóa; lưu nếu kết quả khác `null`. | Không gọi hàm, dùng giá trị có sẵn. | Giá trị có sẵn/được tính, hoặc `null` nếu không tạo ánh xạ. |
| `computeIfPresent(k, updater)` | Không gọi hàm. | Gọi hàm với khóa và giá trị cũ; kết quả `null` nghĩa là xóa. | Giá trị sau cập nhật, hoặc `null` nếu không còn ánh xạ. |
| `compute(k, updater)` | Gọi hàm với giá trị cũ `null`. | Gọi hàm với giá trị cũ. | Giá trị sau tính, hoặc `null` nếu vắng/xóa. |
| `merge(k, incoming, combiner)` | Lưu `incoming`, không gọi hàm gộp. | Gọi hàm gộp với giá trị cũ và `incoming`; kết quả `null` nghĩa là xóa. | Giá trị được lưu, hoặc `null` nếu xóa. |

`ConcurrentHashMap` quy định các lời gọi tính/cập nhật này được thực hiện nguyên tử theo hợp đồng phương thức. Cần đọc quy tắc cụ thể của hàm tính và điều kiện vắng/có trên đúng triển khai. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Bảng không nói rằng một giá trị trả về sẽ còn được giữ mãi. Sau khi lời gọi hoàn tất, một bên khác có thể tiếp tục cập nhật hoặc xóa khóa.

## 3. putIfAbsent: có sẵn ứng viên, chỉ thêm khi vắng

Mẫu minh họa:

~~~java
String old = cache.putIfAbsent("profile-3", candidate);
String chosen = old == null ? candidate : old;
~~~

Đoạn này giả sử `cache` là `ConcurrentHashMap<String, String>` và `candidate` là chuỗi khác `null` đã có sẵn. Nếu khóa vắng, `old` là `null` và ứng viên được chọn. Nếu khóa có, `old` là giá trị được giữ tại lần quyết định đó.

Điểm quan trọng là kiểm tra vắng và thêm không bị tách như cách viết `containsKey` rồi `put`. Hợp đồng `ConcurrentMap.putIfAbsent` quy định hành động có điều kiện ấy được thực hiện nguyên tử. [Java 17: ConcurrentMap.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#putIfAbsent(K,V))

### 3.1. Đối số được tính trước khi phương thức chạy

~~~java
cache.putIfAbsent("profile-3", loadProfile());
~~~

Đoạn minh họa trên giả sử có phương thức `loadProfile` trả về chuỗi phù hợp. Java vẫn phải gọi nó để có đối số trước khi gọi `putIfAbsent`, kể cả khi map đã có giá trị.

Vì vậy hai luồng có thể cùng xây hai ứng viên tốn kém, rồi chỉ một ứng viên được thêm. Tính nguyên tử của việc thêm không ngăn công việc chuẩn bị bị lặp.

Đây có thể là lựa chọn phù hợp nếu ứng viên rẻ, đã có sẵn hoặc được chủ động xây bên ngoài vùng tính của map. Nếu việc tạo chỉ cần diễn ra khi chưa có, hãy xét `computeIfAbsent` và hợp đồng của lớp map cụ thể.

### 3.2. Lưu thành công không tự kéo dài quyền sở hữu

`putIfAbsent` trả `null` xác nhận lần thêm đó thành công trên map không lưu `null`. Nó không bảo đảm một bên khác không thể xóa và tạo lại khóa trước khi bên gọi làm việc tiếp theo.

Nếu dùng ánh xạ để ghi quyền nhận công việc, còn phải định nghĩa mã phiên, thời hạn, điều kiện dọn và việc yêu cầu cũ có được phép tác động lên phiên mới không. Một lần thêm nguyên tử là một thành phần của giao thức ấy.

## 4. computeIfAbsent: tính khi chưa có

Ví dụ minh họa với map dữ liệu cấu hình:

~~~java
String value = settings.computeIfAbsent("region", key -> "local");
~~~

Giả sử `settings` là một `ConcurrentHashMap<String, String>`. Nếu đã có giá trị, nó được trả lại. Nếu chưa có, hàm được dùng để tính giá trị.

Với `ConcurrentHashMap`, Javadoc Java 17 quy định hàm được gọi một lần trong lời gọi cần tính khi khóa vắng, còn khi đã có thì không gọi. Một số cập nhật có thể phải chờ trong lúc tính, nên hàm cần ngắn, đơn giản và không sửa chính map trong quá trình tính. [Java 17: ConcurrentHashMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

### 4.1. Trả null không lưu kết quả vắng

Nếu hàm trả `null`, không có ánh xạ mới được tạo. Lần gọi tiếp theo vẫn có thể gọi lại hàm.

Điều này khác với “đã ghi nhớ rằng không tìm thấy”. Nếu ứng dụng muốn ghi nhớ cả kết quả tìm kiếm thất bại, có thể dùng một kiểu giá trị diễn đạt rõ trạng thái ấy, chẳng hạn một đối tượng kết quả hoặc `Optional` khác `null`. Khi đó cần thiết kế thêm thời hạn và điều kiện làm mới theo ý nghĩa dữ liệu.

### 4.2. Một lần trong lời gọi không phải một lần suốt đời khóa

Hàm có thể được gọi lại ở lần sử dụng sau vì:

- Lần trước trả `null` nên chưa tạo ánh xạ.
- Lần trước ném lỗi nên chưa thiết lập giá trị.
- Giá trị đã được xóa.
- Ứng dụng dùng một map hoặc khóa khác.

Ví dụ hai luồng cùng gọi trên một khóa vắng, hàm tạo thành công, không ai xóa hay thay ánh xạ trong giai đoạn ấy: có thể kiểm chứng hàm tải chạy một lần và cả hai nhận giá trị. Khi thay những điều kiện vòng đời này, không còn được giữ nguyên kết luận “một lần”.

## 5. compute: tính lại từ trạng thái hiện tại

`compute` nhận hàm hai đối số: khóa và giá trị cũ. Trên `ConcurrentHashMap`, giá trị cũ `null` cho biết khóa vắng.

Ví dụ:

~~~java
Integer remaining = stock.compute("book", (key, old) -> {
    if (old == null) {
        return null;
    }
    return old > 0 ? old - 1 : old;
});
~~~

Đoạn minh họa giả sử `stock` là `ConcurrentHashMap<String, Integer>`. Nó không tạo mặt hàng chưa có, giảm một đơn vị khi số lượng dương và giữ nguyên `0` khi hết hàng.

**Không được đọc `remaining` rồi kết luận chắc chắn mình vừa lấy được một đơn vị.** Kết quả `0` có thể đến từ việc giảm `1` xuống `0` hoặc từ việc giữ nguyên một số `0` đã có. Nếu bên gọi cần biết thao tác đã được chấp nhận hay bị từ chối, mô hình kết quả phải thể hiện được điều đó bằng giao thức phù hợp; riêng giá trị tồn cuối chưa đủ phân biệt.

### 5.1. Kết quả null có nghĩa là xóa

Với khóa đang có, hàm `compute` trả `null` làm ánh xạ bị xóa. Với khóa đang vắng, trả `null` giữ nó vắng. Map không lưu một “giá trị null mới”.

Do đó không dùng `return null` như cách nói “không muốn đổi gì” nếu muốn giữ ánh xạ hiện có. Muốn giữ nguyên, trả lại giá trị cũ.

### 5.2. Giữ nguyên giá trị vẫn là một nhánh có ý nghĩa

Một hàm có thể trả lại giá trị cũ khi điều kiện không cho phép thay đổi. Tuy nhiên, như ví dụ tồn kho, kết quả trả về có thể không cho biết riêng lý do nhánh được chọn. Cần xác định điều bên gọi phải biết trước khi thiết kế hàm.

Không lén dùng một danh sách hoặc biến dùng chung không an toàn bên ngoài chỉ để truyền thêm kết quả từ hàm tính. Nếu mô hình đòi cả trạng thái và kết quả quyết định, hãy dùng một thiết kế có hợp đồng rõ và kiểm chứng cách công bố kết quả đó.

### 5.3. computeIfPresent thu hẹp điều kiện gọi hàm

`computeIfPresent` chỉ gọi hàm khi khóa đang có giá trị. Trên map không lưu `null`, khóa vắng khiến hàm không được gọi và kết quả là `null`. Hàm trả `null` khi đang có thì xóa ánh xạ.

Nó hữu ích khi việc cập nhật chỉ áp dụng cho một mục đã tồn tại. Nếu cần xử lý cả nhánh vắng để tạo mới hoặc phát hiện điều kiện, `compute` phù hợp hơn.

## 6. merge: có dữ liệu mới cần kết hợp theo cùng khóa

`merge` tách rõ dữ liệu đầu vào mới với hàm kết hợp:

~~~java
totals.merge("visits", 1, Integer::sum);
~~~

Nếu khóa vắng, số `1` được lưu trực tiếp. Nếu đã có, hàm nhận số cũ rồi số đầu vào mới và tính tổng. Trên `ConcurrentHashMap`, cả lời gọi được thực hiện nguyên tử. [Java 17: ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction))

### 6.1. Hàm gộp không nhận khóa

Dạng hàm của `merge` là:

~~~text
(oldValue, incomingValue) -> combinedValue
~~~

Dạng hàm của `compute` là:

~~~text
(key, oldValue) -> newValue
~~~

Nhầm hai dạng này có thể tạo một hàm vẫn biên dịch nếu các kiểu tình cờ giống nhau, nhưng tính nhầm dữ liệu. Đặt tên đối số rõ giúp tránh lỗi.

### 6.2. Khóa vắng không gọi hàm gộp

Nếu mong đợi việc chuẩn hóa hoặc kiểm tra luôn nằm trong hàm gộp, nhánh vắng có thể bỏ qua việc ấy. `incoming` được chọn trực tiếp trong nhánh đó.

Chẳng hạn `merge(k, text, combiner)` không tự chạy `combiner` để cắt khoảng trắng cho giá trị đầu tiên. Hãy chuẩn hóa dữ liệu trước hoặc chọn một phép tính xử lý cả hai nhánh đúng yêu cầu.

### 6.3. Null đầu vào và null kết quả có ý nghĩa khác nhau

`merge` yêu cầu `incoming` khác `null`. Truyền `null` làm dữ liệu đầu vào không phải yêu cầu xóa.

Ngược lại, hàm gộp trả `null` có nghĩa xóa ánh xạ đang có. Lần `merge` sau trên khóa đã xóa sẽ quay về nhánh lưu trực tiếp dữ liệu đầu vào mới.

Không dùng chung một câu “merge chấp nhận null” cho cả hai vị trí. Cần nói rõ đó là tham số đầu vào hay kết quả của hàm.

### 6.4. Nguyên tử không chọn thứ tự nghiệp vụ

Nếu nhiều luồng gộp các chuỗi, từng lần gộp có thể nguyên tử nhưng thứ tự chuỗi cuối phụ thuộc thứ tự cập nhật. Hàm nối `old + incoming` không làm dữ liệu tự được sắp theo thời gian sự kiện hoặc thứ tự số thứ tự bên ngoài.

Với phép cộng số nguyên nhỏ trong ví dụ, các lần tăng cho cùng kết quả tổng dù bên nào vào trước. Với phép trừ, phép chọn “bản mới nhất”, số thực hoặc chuỗi có thứ tự, phải xem phép gộp có phù hợp với các thứ tự cập nhật có thể xảy ra không.

## 7. Chương trình chạy độc lập

Tệp `PerKeyUpdateDemo.java` dưới đây dùng API có trong Java 17. Ví dụ đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2; không coi đây là bằng chứng đã chạy trên JVM 17.

Ví dụ dùng map không chấp nhận `null`. Các đoạn nhiều luồng có hàng rào để điều khiển thời điểm quan trọng, giữ phạm vi dữ liệu rõ ràng và chờ luồng kết thúc trước khi in.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class PerKeyUpdateDemo {
    @FunctionalInterface
    interface Operation {
        void perform() throws Exception;
    }

    static void twoThreads(Operation operation) throws Exception {
        AtomicReference<Throwable> error = new AtomicReference<>();
        Runnable wrapped = () -> {
            try {
                operation.perform();
            } catch (Throwable failure) {
                error.compareAndSet(null, failure);
            }
        };
        Thread alpha = new Thread(wrapped, "alpha");
        Thread beta = new Thread(wrapped, "beta");
        alpha.setDaemon(true);
        beta.setDaemon(true);
        alpha.start();
        beta.start();
        alpha.join(5000);
        beta.join(5000);
        if (alpha.isAlive() || beta.isAlive()) {
            alpha.interrupt();
            beta.interrupt();
            throw new AssertionError("Threads did not terminate");
        }
        if (error.get() != null) {
            throw new AssertionError("Unexpected thread failure", error.get());
        }
    }

    static String exceptionName(Runnable operation) {
        try {
            operation.run();
            return "none";
        } catch (RuntimeException failure) {
            return failure.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        System.out.println("put-first-old = " + counts.putIfAbsent("p", 2));
        System.out.println("put-again-old = " + counts.putIfAbsent("p", 9));
        System.out.println("put-current = " + counts.get("p"));

        System.out.println("compute-create = "
                + counts.compute("c", (key, old) -> old == null ? 5 : old + 5));
        System.out.println("compute-update = "
                + counts.compute("c", (key, old) -> old + 2));
        System.out.println("compute-delete = "
                + counts.compute("c", (key, old) -> null));
        System.out.println("compute-present-after-delete = "
                + counts.containsKey("c"));

        AtomicInteger absentCalls = new AtomicInteger();
        System.out.println("absent-load = " + counts.computeIfAbsent("a", key -> {
            absentCalls.incrementAndGet();
            return 3;
        }));
        System.out.println("absent-reuse = " + counts.computeIfAbsent("a", key -> {
            absentCalls.incrementAndGet();
            return 99;
        }));
        System.out.println("absent-load-calls = " + absentCalls.get());

        AtomicInteger nullCalls = new AtomicInteger();
        for (int attempt = 0; attempt < 2; attempt++) {
            counts.computeIfAbsent("not-cached", key -> {
                nullCalls.incrementAndGet();
                return null;
            });
        }
        System.out.println("null-load-calls = " + nullCalls.get());
        System.out.println("null-load-cached = " + counts.containsKey("not-cached"));

        AtomicInteger presentCalls = new AtomicInteger();
        System.out.println("present-missing = "
                + counts.computeIfPresent("missing", (key, old) -> {
                    presentCalls.incrementAndGet();
                    return old + 1;
                }));
        System.out.println("present-missing-calls = " + presentCalls.get());
        System.out.println("present-update = "
                + counts.computeIfPresent("p", (key, old) -> old + 8));

        AtomicInteger mergeCalls = new AtomicInteger();
        System.out.println("merge-seed = " + counts.merge("m", 4, (old, incoming) -> {
            mergeCalls.incrementAndGet();
            return old + incoming;
        }));
        System.out.println("merge-calls-after-seed = " + mergeCalls.get());
        System.out.println("merge-combine = " + counts.merge("m", 3, (old, incoming) -> {
            mergeCalls.incrementAndGet();
            return old + incoming;
        }));
        System.out.println("merge-delete = "
                + counts.merge("m", 1, (old, incoming) -> null));
        System.out.println("merge-reseed = " + counts.merge("m", 6, Integer::sum));

        ConcurrentHashMap<String, String> words = new ConcurrentHashMap<>();
        words.put("line", "A");
        System.out.println("merge-argument-order = "
                + words.merge("line", "B", (old, incoming) -> old + ">" + incoming));

        counts.put("failure", 8);
        System.out.println("compute-error = " + exceptionName(() ->
                counts.compute("failure", (key, old) -> {
                    throw new IllegalArgumentException("Cannot compute");
                })));
        System.out.println("value-after-error = " + counts.get("failure"));
        System.out.println("merge-null-seed = " + exceptionName(() ->
                counts.merge("failure", null, Integer::sum)));

        ConcurrentHashMap<String, List<String>> boxes = new ConcurrentHashMap<>();
        List<String> original = new ArrayList<>(List.of("start"));
        boxes.put("box", original);
        System.out.println("mutable-error = " + exceptionName(() ->
                boxes.compute("box", (key, old) -> {
                    old.add("touched");
                    throw new IllegalStateException("After object mutation");
                })));
        System.out.println("same-mapped-object = " + (boxes.get("box") == original));
        System.out.println("mutable-value-after-error = " + boxes.get("box"));

        ConcurrentHashMap<String, Integer> broken = new ConcurrentHashMap<>();
        broken.put("n", 10);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        twoThreads(() -> {
            int observed = broken.get("n");
            bothRead.await(5, TimeUnit.SECONDS);
            broken.put("n", observed + 1);
        });
        System.out.println("separate-read-write = " + broken.get("n"));

        ConcurrentHashMap<String, Integer> merged = new ConcurrentHashMap<>();
        CyclicBarrier mergeStart = new CyclicBarrier(2);
        twoThreads(() -> {
            mergeStart.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                merged.merge("n", 1, Integer::sum);
            }
        });
        System.out.println("concurrent-merge = " + merged.get("n"));

        ConcurrentHashMap<String, Integer> computed = new ConcurrentHashMap<>();
        CyclicBarrier computeStart = new CyclicBarrier(2);
        twoThreads(() -> {
            computeStart.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                computed.compute("n", (key, old) -> old == null ? 1 : old + 1);
            }
        });
        System.out.println("concurrent-compute = " + computed.get("n"));

        ConcurrentHashMap<String, String> offered = new ConcurrentHashMap<>();
        AtomicInteger constructed = new AtomicInteger();
        AtomicInteger insertions = new AtomicInteger();
        CyclicBarrier offersReady = new CyclicBarrier(2);
        twoThreads(() -> {
            String candidate = "offer-" + constructed.incrementAndGet();
            offersReady.await(5, TimeUnit.SECONDS);
            if (offered.putIfAbsent("one", candidate) == null) {
                insertions.incrementAndGet();
            }
        });
        System.out.println("putIfAbsent-constructed = " + constructed.get());
        System.out.println("putIfAbsent-insertions = " + insertions.get());

        ConcurrentHashMap<String, String> loaded = new ConcurrentHashMap<>();
        AtomicInteger loaderCalls = new AtomicInteger();
        AtomicInteger validResults = new AtomicInteger();
        CyclicBarrier loadsReady = new CyclicBarrier(2);
        twoThreads(() -> {
            loadsReady.await(5, TimeUnit.SECONDS);
            String value = loaded.computeIfAbsent("one", key -> {
                loaderCalls.incrementAndGet();
                return "ready";
            });
            if ("ready".equals(value)) {
                validResults.incrementAndGet();
            }
        });
        System.out.println("computeIfAbsent-loader-calls = " + loaderCalls.get());
        System.out.println("computeIfAbsent-valid-results = " + validResults.get());
    }
}
~~~

Lệnh chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 PerKeyUpdateDemo.java
java PerKeyUpdateDemo
~~~

Stdout đã kiểm chứng:

~~~text
put-first-old = null
put-again-old = 2
put-current = 2
compute-create = 5
compute-update = 7
compute-delete = null
compute-present-after-delete = false
absent-load = 3
absent-reuse = 3
absent-load-calls = 1
null-load-calls = 2
null-load-cached = false
present-missing = null
present-missing-calls = 0
present-update = 10
merge-seed = 4
merge-calls-after-seed = 0
merge-combine = 7
merge-delete = null
merge-reseed = 6
merge-argument-order = A>B
compute-error = IllegalArgumentException
value-after-error = 8
merge-null-seed = NullPointerException
mutable-error = IllegalStateException
same-mapped-object = true
mutable-value-after-error = [start, touched]
separate-read-write = 11
concurrent-merge = 2000
concurrent-compute = 2000
putIfAbsent-constructed = 2
putIfAbsent-insertions = 1
computeIfAbsent-loader-calls = 1
computeIfAbsent-valid-results = 2
~~~

Hai luồng trong mỗi tình huống dùng dữ liệu riêng cho tình huống ấy. Lỗi ở luồng phụ được chuyển về luồng chính; thời hạn chờ giúp phép kiểm chứng báo thất bại khi bị kẹt, không dùng để quyết định bên nào thắng.

## 8. Đọc kết quả theo từng nhóm

### 8.1. putIfAbsent trả giá trị cũ

~~~text
put-first-old = null
put-again-old = 2
put-current = 2
~~~

Lần đầu thêm `2`. Lần sau đưa ra ứng viên `9` nhưng nhận lại `2` đã có; giá trị đang lưu vẫn là `2`.

Đó là sự khác nhau giữa kết quả của `putIfAbsent` và kết quả của các phép tính trả giá trị sau cập nhật. Không viết một hàm dùng chung rồi coi tất cả kết quả trả về đều là giá trị mới.

### 8.2. compute tạo, cập nhật và xóa

~~~text
compute-create = 5
compute-update = 7
compute-delete = null
compute-present-after-delete = false
~~~

Nhánh vắng tạo `5`, lần tiếp theo dùng `5` để tính `7`, lần trả `null` xóa khóa. Kết quả cuối kiểm tra bằng `containsKey` trong tình huống tuần tự này xác nhận khóa vắng.

Trong hệ thống có bên ghi tiếp tục chạy, một lần đọc sau chỉ là một quan sát mới. Không cần khóa còn vắng mãi để lần xóa vừa rồi vẫn đúng hợp đồng.

### 8.3. Hàm tải chỉ chạy khi cần, còn null không được ghi nhớ

~~~text
absent-load = 3
absent-reuse = 3
absent-load-calls = 1
null-load-calls = 2
null-load-cached = false
~~~

Giá trị `3` đã có khiến lời gọi sau không chạy hàm tạo `99`. Trong khi đó, hàm luôn trả `null` được gọi lại ở hai lần thử vì không có ánh xạ được tạo.

Nếu hàm tải truy cập một dịch vụ đắt tiền, việc không lưu kết quả vắng có thể rất đáng kể đối với chi phí và lưu lượng. Hành vi này cần được lựa chọn có chủ đích.

### 8.4. computeIfPresent không xử lý khóa vắng

~~~text
present-missing = null
present-missing-calls = 0
present-update = 10
~~~

Trên `missing`, hàm không chạy. Trên `p` đã có `2`, hàm cộng `8` tạo `10`.

Nếu yêu cầu là một hành động phải diễn ra kể cả khi khóa vắng, đặt nó chỉ trong hàm `computeIfPresent` sẽ bỏ sót nhánh ấy.

### 8.5. merge phân biệt tạo đầu tiên với kết hợp

~~~text
merge-seed = 4
merge-calls-after-seed = 0
merge-combine = 7
merge-delete = null
merge-reseed = 6
~~~

Giá trị đầu tiên `4` được lưu mà chưa gọi hàm gộp. Giá trị mới `3` được cộng với `4` thành `7`. Hàm trả `null` xóa khóa; lần sau số `6` trở thành giá trị đầu tiên của một ánh xạ mới.

Dòng `merge-argument-order = A>B` xác nhận hàm nhận giá trị đang lưu `A` trước và dữ liệu đầu vào `B` sau. Đây là ví dụ tuần tự nên thứ tự ký tự có thể dự đoán chính xác.

### 8.6. Ngoại lệ không phải giao dịch cho mọi đối tượng

~~~text
compute-error = IllegalArgumentException
value-after-error = 8
merge-null-seed = NullPointerException
~~~

Hàm tính trên số nguyên ném lỗi trước khi trả một giá trị mới; ánh xạ vẫn giữ `8`. Đầu vào `null` của `merge` bị từ chối.

Nhóm tiếp theo có kết quả khác về nội dung đối tượng:

~~~text
mutable-error = IllegalStateException
same-mapped-object = true
mutable-value-after-error = [start, touched]
~~~

Map vẫn trỏ tới cùng một danh sách. Nhưng hàm đã sửa chính danh sách ấy trước khi ném lỗi, nên phần tử `touched` không tự biến mất.

Đoạn này cố ý chạy trong một luồng để minh họa giới hạn hoàn tác; nó không phải mẫu an toàn cho nhiều luồng cùng sửa một `ArrayList`. “Ánh xạ giữ nguyên khi hàm ném lỗi” không có nghĩa “mọi đối tượng đã bị chạm tới được khôi phục”.

### 8.7. Hai nghìn lần cập nhật không bị mất do tách đọc và ghi

~~~text
separate-read-write = 11
concurrent-merge = 2000
concurrent-compute = 2000
~~~

Ở tình huống đầu, cả hai luồng đọc `10` rồi đều ghi `11`. Hai tình huống sau mỗi luồng thực hiện `1.000` lần cập nhật nguyên tử trên cùng khóa, không có xóa hoặc ghi xen kẽ khác, nên tổng là `2.000`.

Ví dụ dùng miền số nhỏ để không có tràn `int`. Trong ứng dụng, phép cộng vẫn phải xét giới hạn số hoặc dùng kiểu/phép kiểm tra phù hợp. Tính nguyên tử không loại bỏ lỗi số học.

### 8.8. Nguyên tử của thêm và việc xây ứng viên là hai phạm vi

~~~text
putIfAbsent-constructed = 2
putIfAbsent-insertions = 1
computeIfAbsent-loader-calls = 1
computeIfAbsent-valid-results = 2
~~~

Ở phần `putIfAbsent`, hai luồng được buộc xây xong ứng viên trước khi tranh chấp thêm, nên có hai lần xây và một lần thêm được chấp nhận.

Ở phần `computeIfAbsent` trên `ConcurrentHashMap`, không có xóa hoặc lỗi trong giai đoạn ấy. Hàm tải chạy một lần, hai lời gọi nhận `ready`. Chương trình không phụ thuộc vào việc luồng nào được tải trước.

## 9. Phạm vi nguyên tử chính xác

### 9.1. Cập nhật ánh xạ của một khóa

Đối với một lời gọi `compute`/`merge` của `ConcurrentHashMap`, không có bước đọc ngoài rồi ghi đè không điều kiện như mẫu sai đầu bài. Các cập nhật cạnh tranh được phối hợp theo hợp đồng phương thức.

Điều này không hứa mỗi khóa dữ liệu có một cơ chế khóa hoàn toàn độc lập ở mức triển khai. Cấu trúc bên trong, va chạm băm và các công việc quản lý map có thể ảnh hưởng việc chờ và hiệu năng. Đừng suy từ “theo khóa” rằng các khóa khác nhau luôn chạy song song không ảnh hưởng nhau.

### 9.2. Đọc có thể tiếp tục trong lúc tính

Các thao tác truy xuất của `ConcurrentHashMap` nhìn chung không cần khóa theo cùng cách với cập nhật và có thể chồng lấn với cập nhật. Vì vậy đừng coi hàm `compute` đang chạy như một phòng kín nơi không ai có thể đọc giá trị.

Với giá trị bất biến, người đọc có thể quan sát giá trị cũ hoặc giá trị đã được công bố theo hợp đồng, thay vì tự truy cập một bản đang bị sửa tại chỗ. Với đối tượng có thể sửa, việc hàm tính thay trường của đối tượng cũ tạo thêm một bài toán đồng bộ mà map không tự giải quyết.

Đó là lý do nên ưu tiên **tạo giá trị mới rồi trả nó về** khi cập nhật trạng thái qua map.

### 9.3. Không kéo dài sang thao tác trên đối tượng trả về

Mẫu sau cần được đọc thành hai bước:

~~~java
groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(member);
~~~

Đây là đoạn minh họa có chủ ý để phân tích giới hạn, giả sử `groups` chứa danh sách và các biến còn lại đã có. Bước tìm hoặc tạo danh sách có thể được map phối hợp. Bước `add` diễn ra **sau khi lời gọi map trả về**, không tự thuộc vùng nguyên tử của `computeIfAbsent`.

Nếu nhiều luồng nhận cùng một `ArrayList` rồi cùng thêm, cần cơ chế riêng cho danh sách. Ngoài ra, danh sách có thể đã bị xóa khỏi map trước lúc thêm; cập nhật khi ấy tác động lên đối tượng còn được giữ tham chiếu nhưng không còn là ánh xạ hiện tại.

Chọn một danh sách đồng thời có thể giải quyết truy cập bên trong danh sách, nhưng chưa tự giải quyết ý nghĩa cập nhật sau khi bị gỡ khỏi map. Đó là vấn đề vòng đời.

### 9.4. Không bao trùm nhiều khóa

~~~java
balances.compute("A", (key, old) -> old - amount);
balances.compute("B", (key, old) -> old + amount);
~~~

Đây là mã minh họa thiếu giao thức giao dịch, không phải phương án chuyển tiền hoàn chỉnh. Nó giả sử hai giá trị đã có và `amount` hợp lệ chỉ để chỉ ra phạm vi: có hai lời gọi, nên người đọc có thể gặp trạng thái giữa hai lời gọi hoặc một lần có thể thất bại sau lần kia.

Cần cơ chế rộng hơn nếu quy tắc phải đồng thời giữ đúng tổng hoặc điều kiện trên cả A và B: khóa chung mà mọi bên liên quan tuân thủ, một giá trị gộp chứa cả trạng thái, hoặc giao dịch tại nơi sở hữu dữ liệu. Không mở rộng bảo đảm một khóa thành bảo đảm nhiều khóa bằng cách đặt hai lời gọi gần nhau.

### 9.5. Không bao trùm hệ thống bên ngoài

Lưu `DONE` trong map và gửi thông báo là hai tác dụng. Một tiến trình có thể dừng giữa chúng. Hàm tính nguyên tử của map không tạo giao dịch với file, cơ sở dữ liệu hoặc máy chủ khác.

Giữ hàm tính tập trung vào việc tạo giá trị ánh xạ. Nếu yêu cầu có tác dụng bên ngoài, phải định nghĩa thứ tự, tính lặp an toàn và khôi phục theo đúng yêu cầu ấy.

## 10. Thiết kế hàm tính

### 10.1. Ngắn, rõ và không cập nhật lồng chính map

Tránh thực hiện I/O dài, chờ người dùng, gọi dịch vụ chậm hoặc chờ một tác vụ khác cần cập nhật map trong hàm tính. Một số cập nhật có thể bị chặn khi tính đang diễn ra; việc chờ phụ thuộc ngược có thể làm giao thức bị kẹt.

Không gọi `put`, `compute` hoặc `merge` lồng để sửa chính map từ hàm tính. Với `ConcurrentHashMap`, hợp đồng các hàm tính cấm sửa map trong lúc tính; một số cập nhật đệ quy không thể hoàn tất có thể bị phát hiện bằng `IllegalStateException`. Không dựa vào ngoại lệ để biến thiết kế lồng không hợp lệ thành hợp lệ.

Nếu cần tính ở ngoài vì công việc tốn kém, có thể phải chấp nhận nhiều ứng viên rồi dùng thao tác điều kiện để chọn một, hoặc thiết kế một cơ chế quản lý tác vụ tính riêng. Đó là đánh đổi cần nói rõ, không có cách tự động vừa loại mọi lần tính trùng vừa cho phép mọi công việc chạy không chặn.

### 10.2. Tránh sửa trực tiếp giá trị cũ

Ví dụ minh họa sau dùng các kiểu được ghi đầy đủ và tạo một bản mới trong hàm tính:

~~~java
java.util.concurrent.ConcurrentHashMap<String, java.util.List<String>> groups =
        new java.util.concurrent.ConcurrentHashMap<>();

groups.compute("team", (key, old) -> {
    java.util.List<String> next =
            old == null ? new java.util.ArrayList<>()
                        : new java.util.ArrayList<>(old);
    next.add("Linh");
    return java.util.List.copyOf(next);
});
~~~

Danh sách đã công bố trong mô hình này không bị sửa sau đó; mỗi cập nhật tạo và công bố một danh sách mới. Các phần tử là chuỗi nên không cần xử lý sự biến đổi bên trong phần tử cho ví dụ này. `List.copyOf` không chấp nhận phần tử `null`.

Cách này có chi phí sao chép. Nó hữu ích khi cần ngữ nghĩa rõ về bản dữ liệu và lượng cập nhật phù hợp, không phải lời khuyên sao chép mọi collection trong mọi tải công việc.

### 10.3. Không biến hàm tính thành nơi phát sinh tác dụng khó lặp

Ngay cả khi dùng `ConcurrentHashMap` có bảo đảm mạnh cho một lời gọi `compute`, nhiều lời gọi riêng vẫn có thể cùng thực hiện cùng ý định nghiệp vụ. Thử lại ở tầng gọi, lỗi mạng hoặc việc xóa rồi tạo lại khóa có thể làm ý định lặp.

Hàm chỉ tính giá trị mới thường dễ kiểm tra hơn hàm vừa sửa map vừa gửi email vừa sửa một danh sách bên ngoài. Nếu cần các tác dụng ấy, hãy thiết kế chúng như những phần có hợp đồng riêng.

## 11. Map, ConcurrentMap và lớp triển khai

### 11.1. Có cùng tên API chưa có cùng bảo đảm

Các phương thức `compute`/`merge` cũng tồn tại trên `Map`. Triển khai mặc định của `Map` không hứa các thuộc tính đồng bộ/nguyên tử cho mọi map. Dùng những tên phương thức ấy trên `HashMap` không tự làm nó an toàn giữa nhiều luồng. [Java 17: Map.compute và Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#compute(K,java.util.function.BiFunction))

Kiểu khai báo là một phần mô tả yêu cầu, còn hành vi thực tế được quyết định bởi đối tượng và hợp đồng lớp triển khai. Biến kiểu `Map` trỏ đến `ConcurrentHashMap` vẫn gọi phương thức của đối tượng đó.

### 11.2. ConcurrentMap có thể phối hợp bằng thử lại

Một số phương thức mặc định của `ConcurrentMap` phối hợp việc tính bằng các thao tác điều kiện như `putIfAbsent`, `replace` và `remove`. Dưới tranh chấp, các bước và hàm tính lại có thể chạy nhiều lần. Vì vậy không gán cho một triển khai `ConcurrentMap` bất kỳ bảo đảm về hàm tính của `ConcurrentHashMap`. [Java 17: ConcurrentMap.compute và merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#merge(K,V,java.util.function.BiFunction))

Đây là hai loại bảo đảm cần tách:

- Kết quả cập nhật ánh xạ được chấp nhận theo thao tác điều kiện.
- Toàn bộ lần thực thi hàm tính có được phối hợp như một lần tính nguyên tử, và hàm có thể chạy bao nhiêu lần.

Một hàm không có tác dụng bên ngoài và chỉ tạo kết quả từ dữ liệu đầu vào thường dễ dùng đúng hơn khi có thử lại.

### 11.3. Ví dụ khác: ConcurrentSkipListMap

`ConcurrentSkipListMap` cung cấp map đồng thời có thứ tự khóa. Hợp đồng của nó nói rõ hàm `computeIfAbsent` không được bảo đảm chỉ áp dụng một lần nguyên tử khi vắng; các phương thức tính khác cũng có ghi chú tương ứng. [Java 17: ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function))

Do đó, một bài kiểm thử đếm số lần hàm tải trên `ConcurrentHashMap` không phải bằng chứng rằng số ấy giữ nguyên sau khi đổi sang map đồng thời khác.

### 11.4. Chính sách null cũng cần đọc theo lớp

Các ví dụ trong bài dùng `ConcurrentHashMap` để `null` có nghĩa vắng ở các vị trí đã nêu. `ConcurrentMap` nói chung có các ghi chú dành cho triển khai hỗ trợ giá trị `null`; những phương thức mặc định dựa trên giả định “`get` trả `null` là vắng” cần được ghi đè khi giả định không đúng.

Khi đổi lớp map, không chỉ kiểm tra tên phương thức còn biên dịch; phải kiểm tra chính sách null, điều kiện gọi hàm, phép thử lại và bảo đảm nguyên tử.

## 12. Liên hệ với bộ đếm LongAdder

Một mẫu thống kê thường gặp là dùng `ConcurrentHashMap` chứa `LongAdder` rồi tìm hoặc tạo bộ cộng trước khi tăng. `LongAdder` được thiết kế để hỗ trợ nhiều cập nhật số đếm có tranh chấp; `sum` không phải bản chụp nguyên tử trong lúc các cập nhật vẫn đang diễn ra. [Java 17: LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)

Mẫu này có hai lớp hợp đồng:

1. Map phối hợp việc tìm hoặc tạo đối tượng bộ cộng.
2. Bộ cộng phối hợp các lần tăng trên chính đối tượng đó.

Nó khác với `merge` thay giá trị `Integer` trong một ánh xạ. Nếu ứng dụng cho phép xóa và thay bộ cộng, một luồng đã lấy tham chiếu cũ có thể tăng bộ cộng không còn nằm trong map. Muốn đếm chính xác theo vòng đời phải thiết kế quy tắc gỡ/thay tương ứng.

Không chọn giữa hai mô hình chỉ bằng số dòng mã. Hãy xét mức tranh chấp, yêu cầu đọc tổng, vòng đời khóa và chi phí tạo/thay giá trị.

## 13. Kiểm chứng điều kiện thay vì chỉ kiểm tra không lỗi

Một phép thử tốt nói rõ yêu cầu:

- Với bộ đếm không có xóa, sau khi mọi lần tăng hoàn tất, tổng bằng số lần cập nhật được yêu cầu.
- Với hàm tải, số lần gọi được kiểm tra dưới điều kiện cụ thể về loại map, lỗi, xóa và kết quả `null`.
- Với hàm gộp không giao hoán, thứ tự cần thiết được mô hình hóa thay vì đoán từ lịch luồng.
- Với hàm ném lỗi, phân biệt ánh xạ có được thay không và đối tượng cũ có bị sửa trước đó không.
- Với nhiều khóa, kiểm tra trực tiếp bất biến nhiều khóa thay vì cho rằng các lời gọi riêng đã đủ.

Các hàng rào trong chương trình ép lịch của trường hợp mất cập nhật, còn các bộ đếm được in sau khi các luồng hoàn tất. Không dựa vào việc một lần chạy tự nhiên tình cờ có hoặc không có tranh chấp.

Đừng đặt một hàng rào đợi hai luồng cùng vào **bên trong** hai hàm `compute` trên cùng khóa để thử tính nguyên tử: một lời gọi có thể đang ngăn lời gọi còn lại tiến vào, khiến chính phép thử tự tạo chờ vòng. Điều khiển điểm bắt đầu bên ngoài như trong chương trình giúp tránh giả định sai đó.

## 14. Bài tập tự kiểm tra

### Bài 1 — Cùng là tạo khi vắng

Vì sao hai luồng gọi `putIfAbsent(k, expensiveLoad())` có thể cùng tải dữ liệu, dù chỉ một giá trị được thêm?

**Đáp án:** Đối số được tính trước lời gọi. Tính nguyên tử bảo vệ việc kiểm tra/thêm ánh xạ, không bao trùm phần tạo ứng viên bên ngoài.

### Bài 2 — Null không phải giá trị được ghi nhớ

Hàm `computeIfAbsent` luôn trả `null`. Sau mười lần gọi tuần tự, có thể khẳng định hàm chỉ chạy lần đầu vì khóa đã được kiểm tra rồi không?

**Đáp án:** Không. Không có ánh xạ được tạo, nên mỗi lần sau vẫn có thể gọi lại hàm. Nếu cần ghi nhớ kết quả không tìm thấy, dùng mô hình giá trị rõ ràng.

### Bài 3 — Giữ nguyên hay xóa

Một khóa đã có dữ liệu. Trong `compute`, người viết trả `null` khi không muốn đổi dữ liệu. Mã thực sự làm gì trên `ConcurrentHashMap`?

**Đáp án:** Xóa ánh xạ. Muốn giữ giá trị cũ thì trả lại giá trị cũ; muốn biểu diễn từ chối cập nhật cho bên gọi phải thiết kế thông tin kết quả phù hợp.

### Bài 4 — Hàm merge không chạy

`merge(k, rawText, normalizer)` được dùng với kỳ vọng `normalizer` luôn chuẩn hóa dữ liệu. Vì sao giá trị đầu tiên có thể chưa được chuẩn hóa?

**Đáp án:** Khi khóa vắng, `rawText` được lưu trực tiếp và hàm gộp không chạy. Chuẩn hóa trước khi truyền hoặc chọn phép tính xử lý cả nhánh vắng.

### Bài 5 — Null ở hai vị trí

So sánh `merge(k, null, combiner)` với một `combiner` trả `null` khi khóa đang có.

**Đáp án:** Đối số dữ liệu đầu vào của `merge` phải khác `null`. Kết quả `null` từ hàm gộp lại là yêu cầu xóa ánh xạ hiện có.

### Bài 6 — Hàm ném lỗi sau khi sửa danh sách

Một hàm `compute` thêm phần tử vào danh sách cũ rồi ném lỗi. Map vẫn trỏ đến danh sách ấy. Có thể mong phần tử vừa thêm tự bị hoàn tác không?

**Đáp án:** Không. Ánh xạ không được thay không đồng nghĩa đối tượng đã bị sửa được khôi phục. Nên tránh sửa tại chỗ khi cần ngữ nghĩa cập nhật rõ; tạo một giá trị mới hoặc dùng giao thức phù hợp.

### Bài 7 — Hai khóa cạnh nhau

Hai lời gọi `compute` cập nhật hai khóa A và B. Nếu cả hai phương thức đều nguyên tử theo khóa, có bảo đảm người đọc không quan sát trạng thái giữa hai cập nhật không?

**Đáp án:** Không. Chúng là hai thao tác. Một bất biến chung giữa A và B cần cơ chế rộng hơn hoặc mô hình gộp trạng thái.

### Bài 8 — Đổi loại map

Một phép thử trên `ConcurrentHashMap` cho thấy hai luồng cùng lấy dữ liệu nhưng hàm `computeIfAbsent` chỉ chạy một lần. Có thể dùng số lần đó như hợp đồng chung của mọi `ConcurrentMap` không?

**Đáp án:** Không. Cần xem hợp đồng lớp cụ thể; những triển khai dùng thử lại hoặc có quy tắc hàm tính khác không tự mang bảo đảm ấy.

Việc chọn `putIfAbsent`, `compute` hay `merge` bắt đầu từ điều kiện vắng/có và ý nghĩa dữ liệu mới. Sau đó xác định đúng phạm vi nguyên tử: ánh xạ nào được bảo vệ, hàm tính có thể làm gì, và phần công việc nào vẫn cần một giao thức riêng.
