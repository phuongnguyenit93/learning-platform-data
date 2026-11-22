# ConcurrentMap và các thao tác cập nhật có điều kiện

Một map lưu quan hệ từ khóa đến giá trị. Khi nhiều luồng cùng dùng map, yêu cầu thường vượt quá “đọc một giá trị” hoặc “ghi một giá trị”: chỉ đăng ký khi chưa có, chỉ thay trạng thái nếu vẫn là trạng thái đã đọc, hoặc chỉ xóa đăng ký mà chính mình còn sở hữu.

`ConcurrentMap<K, V>` mở rộng `Map<K, V>` bằng các bảo đảm đồng thời, trong đó có những thao tác gộp **kiểm tra điều kiện và cập nhật** thành một hành động nguyên tử. Đó là công cụ để diễn đạt quyết định trên một ánh xạ mà không để một thao tác cạnh tranh chen vào giữa phần kiểm tra và phần ghi. [Java 17: ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

Bài học dùng `ConcurrentHashMap` làm triển khai cụ thể để có quy tắc rõ ràng: không có khóa hay giá trị `null`. Từ đó có thể đọc kết quả trả về mà không nhầm `null` với một giá trị được lưu thật.

Trước khi đi vào API, cần nắm bốn ý:

- **Ánh xạ:** cặp khóa và giá trị đang được map lưu tại thời điểm xét.
- **Điều kiện cập nhật:** yêu cầu phải đúng ngay lúc map thực hiện thao tác, không chỉ đúng ở một lần đọc trước đó.
- **Nguyên tử:** phần quyết định và thay đổi của một lời gọi được thực hiện như một hành động đối với ánh xạ đang xét.
- **Giá trị mong đợi:** giá trị cũ dùng làm điều kiện, chẳng hạn “chỉ đổi từ `PENDING` sang `RUNNING` nếu hiện tại vẫn bằng `PENDING`”.

Lộ trình là hiểu khoảng trống của thao tác ghép, đọc bốn API cốt lõi, chạy ví dụ có tranh chấp được điều khiển, rồi xét giới hạn của phép so sánh và phạm vi nguyên tử.

## 1. Một map an toàn không tự làm cả chuỗi lời gọi nguyên tử

Xét một ô đăng ký `"slot"` mà ban đầu chưa có người nhận. Đoạn mã minh họa sau giả sử `claims` là `ConcurrentMap<String, String>` đã được khởi tạo:

~~~java
if (!claims.containsKey("slot")) {
    claims.put("slot", "CLAIMED");
    // Tiếp tục công việc vì cho rằng mình vừa giành được ô.
}
~~~

Mỗi lần `containsKey` và `put` có thể hoàn toàn an toàn khi được gọi đồng thời. Nhưng giữa hai lời gọi có một khoảng thời gian. Một lịch hợp lệ là:

~~~text
Luồng 1: thấy slot chưa có
Luồng 2: thấy slot chưa có
Luồng 1: ghi CLAIMED và nhận mình thắng
Luồng 2: ghi CLAIMED và cũng nhận mình thắng
~~~

Map vẫn chỉ có một khóa `slot`. Cấu trúc dữ liệu không hỏng. Điều bị vi phạm là quy tắc **chỉ một bên được công nhận đã đăng ký thành công**.

`putIfAbsent` chuyển điều kiện “chưa có” vào bên trong cùng một thao tác cập nhật. Bên gọi phải dựa vào kết quả của thao tác ấy để quyết định mình có giành được quyền hay không.

Vấn đề tương tự xảy ra khi đọc một số đếm rồi ghi số cũ cộng một, đọc trạng thái rồi thay không điều kiện, hoặc kiểm tra chủ sở hữu rồi xóa không điều kiện. Sự an toàn của từng lời gọi không nối chúng thành một giao dịch lớn hơn.

## 2. Bốn thao tác cần phân biệt

Bảng sau xét map không chấp nhận giá trị `null`, cụ thể là `ConcurrentHashMap` dùng trong bài. Tất cả điều kiện đều được đánh giá như một phần của chính thao tác, không phải bằng một lần kiểm tra tách rời trước đó.

| Lời gọi | Khi nào thay đổi ánh xạ? | Kết quả trả về |
|---|---|---|
| `putIfAbsent(k, candidate)` | Khi chưa có giá trị tại `k`. | Giá trị trước đó; `null` cho biết lời gọi đã thêm vào khóa đang vắng. |
| `replace(k, replacement)` | Khi `k` đang có ánh xạ, bất kể giá trị cũ cụ thể là gì. | Giá trị bị thay; `null` nếu không có ánh xạ để thay. |
| `replace(k, expected, replacement)` | Khi giá trị hiện tại tại `k` bằng `expected` theo hợp đồng so sánh của thao tác. | `true` nếu đã thay, `false` nếu điều kiện không khớp. |
| `remove(k, expected)` | Khi giá trị hiện tại tại `k` bằng `expected`. | `true` nếu đã xóa, `false` nếu không xóa. |

Hợp đồng nguyên tử của các thao tác trên được quy định trong `ConcurrentMap`; riêng sự xuất hiện cùng tên phương thức trong giao diện `Map` chưa tạo bảo đảm đồng thời cho mọi triển khai. [Java 17: các phương thức điều kiện của ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#putIfAbsent(K,V))

### 2.1. putIfAbsent: chỉ thêm khi chưa có

Đoạn sau là minh họa trong một phương thức:

~~~java
java.util.concurrent.ConcurrentMap<String, String> registrations =
        new java.util.concurrent.ConcurrentHashMap<>();

String previous = registrations.putIfAbsent("id-5", "Lan");
boolean inserted = previous == null;
~~~

Với map vừa khởi tạo, `previous` là `null` và `inserted` là `true`. Nếu một bên đã lưu `"Minh"` tại `id-5`, lời gọi trả `"Minh"` và không ghi đè bằng `"Lan"`.

Các điểm dễ đọc sai:

- Kết quả không phải giá trị mới mà bên gọi muốn lưu.
- Kết quả không phải `boolean`.
- Giá trị hiện có có thể bằng ứng viên về nội dung; điều đó không chứng minh bên gọi vừa thắng.
- Đừng gọi `containsKey` thêm lần nữa để suy luận kết quả vừa rồi; đó là một quan sát ở thời điểm khác.

Nếu cần trả về giá trị thực sự được chọn trong tình huống không chấp nhận `null`, mẫu thường dùng là:

~~~java
String candidate = "Lan";
String existing = registrations.putIfAbsent("id-5", candidate);
String selected = existing == null ? candidate : existing;
~~~

`selected` là kết quả lựa chọn của lời gọi ấy. Nó không phải lời hứa rằng không ai có thể thay hoặc xóa ánh xạ ngay sau đó.

### 2.2. replace với hai đối số: chỉ cần khóa tồn tại

`replace(k, replacement)` khác `put(k, replacement)` ở chỗ nó không tạo ánh xạ cho khóa đang vắng.

~~~java
String old = registrations.replace("id-missing", "Hoa");
// Với dữ liệu trên: old là null và không tạo id-missing.
~~~

Tuy nhiên, dạng hai đối số **không kiểm tra một giá trị cũ cụ thể**. Nếu yêu cầu là “chỉ chấp nhận thay đổi khi đăng ký vẫn là bản mình đã đọc”, dạng này chưa đủ.

Ví dụ một luồng đọc `PENDING`, một luồng khác đổi sang `CANCELLED`, rồi luồng đầu gọi `replace(k, "RUNNING")`. Dạng hai đối số có thể thay cả `CANCELLED` vì khóa vẫn tồn tại. Để bảo vệ giả định về trạng thái cũ, phải dùng dạng ba đối số.

### 2.3. replace với ba đối số: chỉ thay đúng giá trị mong đợi

~~~java
boolean started = states.replace("job-8", "PENDING", "RUNNING");
~~~

Đoạn minh họa giả sử `states` là một `ConcurrentMap<String, String>` không chấp nhận `null`. `started` chỉ là `true` khi thao tác thay đã diễn ra.

Nếu khóa vắng hoặc đang có một giá trị khác, kết quả là `false` và lời gọi không ghi `RUNNING`. Hai trường hợp thất bại ấy không được phân biệt chỉ bằng kết quả `boolean`. Có thể đọc lại để xử lý tiếp, nhưng lần đọc sau là một quan sát mới.

Ví dụ này diễn đạt một chuyển trạng thái rất hẹp: `PENDING → RUNNING`. Nó không tự kiểm tra mọi quy tắc nghiệp vụ như quyền người gọi, hạn chót, phiên bản công việc hoặc trạng thái của khóa khác. Nếu các yếu tố ấy phải quyết định cùng nhau, cần đưa chúng vào mô hình điều kiện hoặc chọn cơ chế phối hợp rộng hơn.

### 2.4. remove với hai đối số: dọn đúng ánh xạ

`remove(k)` xóa ánh xạ hiện tại theo khóa. `remove(k, expected)` chỉ xóa khi giá trị vẫn khớp điều kiện.

Tình huống điển hình là dọn một đăng ký cũ:

~~~text
Bên A đã đăng ký bằng mã phiên A-1.
Đăng ký được thay bằng mã phiên B-1.
Bên A hoàn tất muộn và tiến hành dọn.
~~~

Nếu A gọi `remove(key)`, nó có thể xóa đăng ký B-1. Nếu A gọi `remove(key, "A-1")`, phép xóa sẽ thất bại khi ánh xạ hiện tại là B-1.

Đây là **xóa có điều kiện theo giá trị hiện tại**. Muốn điều kiện mang nghĩa “đúng lần đăng ký của tôi”, giá trị phải chứa dấu nhận diện không bị tái sử dụng nhầm. Chỉ dùng tên chủ sở hữu chung như `"A"` có thể không phân biệt được hai lần đăng ký khác nhau của cùng bên A.

## 3. Hiểu kết quả nguyên tử theo thời gian

Có thể lập luận về mỗi lời gọi điều kiện như một quyết định có hiệu lực tại một thời điểm nằm trong khoảng lời gọi bắt đầu và kết thúc. Điều kiện và cập nhật không bị tách thành hai quyết định độc lập mà bên khác có thể chen vào giữa.

Nhưng map không bị đóng băng sau khi trả kết quả:

~~~text
T1: replace(k, OLD, NEW) thành công
T2: remove(k, NEW) thành công
T1: thực hiện dòng mã tiếp theo
~~~

T1 đã thay thành công và vẫn có thể thấy khóa vắng nếu đọc lại ở dòng tiếp theo. Hai việc đó không mâu thuẫn.

Tương tự, `remove(k, expected)` trả `true` không bảo đảm `k` vẫn vắng ở lần `get` tiếp theo; một bên khác có thể đã thêm lại.

Phân biệt hai mục tiêu:

- **Biết hành động của lời gọi vừa rồi có được chấp nhận hay không:** dùng kết quả trả về.
- **Biết trạng thái đang quan sát ở lần đọc sau:** dùng lần đọc đó, với giới hạn rằng nó cũng có thể sớm thay đổi.

Không dùng một lần `get` sau cập nhật để thay thế ý nghĩa kết quả trả về. Cũng không giữ một kết quả cũ rồi coi nó là quyền độc quyền kéo dài vô hạn.

## 4. So sánh giá trị không đồng nghĩa so sánh cùng đối tượng

Điều kiện của `replace(k, expected, replacement)` và `remove(k, expected)` được định nghĩa theo sự bằng nhau của giá trị, không yêu cầu hai tham chiếu `==` nhau. Với `String`, hai đối tượng được tạo riêng có cùng nội dung vẫn có thể khớp.

~~~java
String stored = new String("OPEN");
String expected = new String("OPEN");

boolean sameObject = stored == expected; // false
boolean sameValue = stored.equals(expected); // true
~~~

`equals` biểu diễn quan hệ bằng nhau mà kiểu định nghĩa; nó không mặc nhiên mang nghĩa “cùng phiên bản”, “cùng lần đăng ký” hoặc “chưa từng bị thay đổi”. [Java 17: Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))

Thiết kế điều kiện phải đi cùng thiết kế kiểu giá trị:

- Với một giá trị bất biến đơn giản, so sánh nội dung thường phù hợp.
- Với một phiên đăng ký, nên có mã phiên riêng.
- Với một trạng thái cần phát hiện sửa đổi ở giữa, nên có phiên bản được đưa vào phép bằng nhau.
- Với đối tượng có thể sửa tại chỗ, một tham chiếu giữ lại chưa chắc là bản chụp của giá trị tại lúc đọc.

Nếu `equals` bỏ qua phiên bản hoặc mã phiên, đặt thêm trường ấy vào lớp mà không đưa vào phép so sánh cũng không tạo được điều kiện mong muốn.

## 5. Chương trình kiểm chứng đầy đủ

Lưu tệp `ConditionalMapDemo.java`. Chương trình dùng API và cú pháp có trong Java 17, đã biên dịch bằng `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2. Kết quả dưới đây là của môi trường đó; không suy thành tuyên bố đã chạy trên JVM 17.

Các phần nhiều luồng dùng `CyclicBarrier` để điều khiển thời điểm kiểm tra và cập nhật. Không dùng `Thread.sleep` để hy vọng tạo đúng tranh chấp. `ConcurrentHashMap` bảo vệ các lời gọi riêng lẻ, nên ví dụ sai về thao tác ghép không cần gây hỏng cấu trúc map.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ConditionalMapDemo {
    record Revision(long number, String state) {}

    @FunctionalInterface
    interface CheckedTask {
        void execute() throws Exception;
    }

    static void together(CheckedTask task) throws Exception {
        AtomicReference<Throwable> problem = new AtomicReference<>();
        Thread[] threads = new Thread[2];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                try {
                    task.execute();
                } catch (Throwable ex) {
                    problem.compareAndSet(null, ex);
                }
            }, "contender-" + i);
            threads[i].setDaemon(true);
        }
        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join(5000);
        }
        for (Thread thread : threads) {
            if (thread.isAlive()) {
                for (Thread other : threads) {
                    other.interrupt();
                }
                throw new AssertionError("Concurrent scenario timed out");
            }
        }
        if (problem.get() != null) {
            throw new AssertionError("Concurrent scenario failed", problem.get());
        }
    }

    static void addOne(ConcurrentMap<String, Integer> counts, String key) {
        for (;;) {
            Integer observed = counts.get(key);
            if (observed == null) {
                if (counts.putIfAbsent(key, 1) == null) {
                    return;
                }
            } else {
                int updated = Math.addExact(observed, 1);
                if (counts.replace(key, observed, updated)) {
                    return;
                }
            }
        }
    }

    static String build(AtomicInteger builds) {
        return "candidate-" + builds.incrementAndGet();
    }

    static String nullResult(Runnable task) {
        try {
            task.run();
            return "completed";
        } catch (NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentMap<String, String> state = new ConcurrentHashMap<>();
        System.out.println("insert-first = "
                + state.putIfAbsent("job", "PENDING"));
        System.out.println("insert-second = "
                + state.putIfAbsent("job", "OTHER"));
        System.out.println("stored = " + state.get("job"));

        System.out.println("replace-missing = "
                + state.replace("missing", "RUNNING"));
        System.out.println("missing-present = " + state.containsKey("missing"));
        System.out.println("replace-present-old = "
                + state.replace("job", "RUNNING"));
        System.out.println("replace-stale = "
                + state.replace("job", "PENDING", "DONE"));
        System.out.println("replace-match = "
                + state.replace("job", "RUNNING", "DONE"));
        System.out.println("after-replace = " + state.get("job"));
        System.out.println("remove-stale = " + state.remove("job", "RUNNING"));
        System.out.println("remove-match = " + state.remove("job", "DONE"));
        System.out.println("remove-again = " + state.remove("job", "DONE"));

        ConcurrentMap<String, String> equality = new ConcurrentHashMap<>();
        String actual = new String("OPEN");
        String equivalent = new String("OPEN");
        equality.put("door", actual);
        System.out.println("same-reference = " + (actual == equivalent));
        System.out.println("replace-equal-value = "
                + equality.replace("door", equivalent, "CLOSED"));

        ConcurrentMap<String, String> claims = new ConcurrentHashMap<>();
        AtomicInteger reportedWinners = new AtomicInteger();
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        together(() -> {
            boolean vacant = !claims.containsKey("slot");
            bothChecked.await(5, TimeUnit.SECONDS);
            if (vacant) {
                claims.put("slot", "CLAIMED");
                reportedWinners.incrementAndGet();
            }
        });
        System.out.println("check-then-put-winners = " + reportedWinners.get());

        claims.clear();
        reportedWinners.set(0);
        CyclicBarrier bothReady = new CyclicBarrier(2);
        together(() -> {
            bothReady.await(5, TimeUnit.SECONDS);
            if (claims.putIfAbsent("slot", "CLAIMED") == null) {
                reportedWinners.incrementAndGet();
            }
        });
        System.out.println("putIfAbsent-winners = " + reportedWinners.get());

        ConcurrentMap<String, Integer> broken = new ConcurrentHashMap<>();
        broken.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        together(() -> {
            int previous = broken.get("hits");
            bothRead.await(5, TimeUnit.SECONDS);
            broken.put("hits", previous + 1);
        });
        System.out.println("get-then-put-count = " + broken.get("hits"));

        ConcurrentMap<String, Integer> fixed = new ConcurrentHashMap<>();
        CyclicBarrier startCounting = new CyclicBarrier(2);
        together(() -> {
            startCounting.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                addOne(fixed, "hits");
            }
        });
        System.out.println("conditional-loop-count = " + fixed.get("hits"));

        ConcurrentMap<String, String> plain = new ConcurrentHashMap<>();
        plain.put("item", "A");
        String oldState = plain.get("item");
        plain.put("item", "B");
        plain.put("item", "A");
        System.out.println("plain-ABA-update = "
                + plain.replace("item", oldState, "C"));

        ConcurrentMap<String, Revision> versions = new ConcurrentHashMap<>();
        versions.put("item", new Revision(1, "READY"));
        Revision observed = versions.get("item");
        versions.put("item", new Revision(2, "BUSY"));
        versions.put("item", new Revision(3, "READY"));
        System.out.println("versioned-stale-update = "
                + versions.replace("item", observed, new Revision(4, "DONE")));
        System.out.println("versioned-current = " + versions.get("item"));

        ConcurrentMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger builds = new AtomicInteger();
        cache.putIfAbsent("key", build(builds));
        cache.putIfAbsent("key", build(builds));
        System.out.println("eager-builds = " + builds.get());
        System.out.println("eager-stored = " + cache.get("key"));

        AtomicInteger lazyBuilds = new AtomicInteger();
        String reused = cache.computeIfAbsent("key", key -> build(lazyBuilds));
        System.out.println("existing-compute-builds = " + lazyBuilds.get());
        System.out.println("existing-compute-value = " + reused);

        System.out.println("null-key = "
                + nullResult(() -> cache.putIfAbsent(null, "x")));
        System.out.println("null-value = "
                + nullResult(() -> cache.putIfAbsent("null-test", null)));
    }
}
~~~

Lệnh biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ConditionalMapDemo.java
java ConditionalMapDemo
~~~

Stdout đã kiểm chứng:

~~~text
insert-first = null
insert-second = PENDING
stored = PENDING
replace-missing = null
missing-present = false
replace-present-old = PENDING
replace-stale = false
replace-match = true
after-replace = DONE
remove-stale = false
remove-match = true
remove-again = false
same-reference = false
replace-equal-value = true
check-then-put-winners = 2
putIfAbsent-winners = 1
get-then-put-count = 1
conditional-loop-count = 2000
plain-ABA-update = true
versioned-stale-update = false
versioned-current = Revision[number=3, state=READY]
eager-builds = 2
eager-stored = candidate-1
existing-compute-builds = 0
existing-compute-value = candidate-1
null-key = NullPointerException
null-value = NullPointerException
~~~

`together` đợi cả hai luồng kết thúc trước khi luồng chính in kết quả, đồng thời chuyển lỗi của luồng phụ về luồng chính. Các thời hạn năm giây chỉ giới hạn thời gian chờ của phép kiểm chứng, không quyết định thứ tự thắng.

## 6. Phân tích kết quả

### 6.1. Giá trị trả về phân biệt việc thêm với việc giữ nguyên

Ba dòng đầu:

~~~text
insert-first = null
insert-second = PENDING
stored = PENDING
~~~

Lần đầu tạo ánh xạ `job → PENDING`. Lần sau đưa ra ứng viên `OTHER` nhưng nhận về giá trị `PENDING` đã có. Giá trị đang lưu vẫn là `PENDING`.

Không cần một cờ “đã có” được kiểm tra trước. Bản thân kết quả của `putIfAbsent` là thông tin của lần quyết định nguyên tử.

### 6.2. Hai dạng replace bảo vệ hai điều kiện khác nhau

~~~text
replace-missing = null
missing-present = false
replace-present-old = PENDING
replace-stale = false
replace-match = true
after-replace = DONE
~~~

`replace` dạng hai đối số trên `missing` không tạo khóa. Dạng hai đối số trên `job` thay `PENDING` bằng `RUNNING` và trả lại `PENDING`.

Sau đó lời gọi đòi `PENDING` làm điều kiện thất bại vì giá trị hiện tại đã là `RUNNING`. Lời gọi đòi `RUNNING` thành công và đổi thành `DONE`.

Phần này chạy tuần tự để kiểm chứng rõ hợp đồng từng thao tác trước khi đưa tranh chấp vào. Không cần nhiều luồng để quan sát sự khác nhau giữa “khóa còn tồn tại” và “giá trị vẫn khớp bản mong đợi”.

### 6.3. Xóa có điều kiện không xóa trạng thái đã khác

~~~text
remove-stale = false
remove-match = true
remove-again = false
~~~

Điều kiện `RUNNING` không còn khớp `DONE` nên không xóa. Điều kiện `DONE` khớp nên xóa. Lần xóa tiếp theo không có ánh xạ để xóa nên trả `false`.

Đây là kết quả của thao tác, không phải ngoại lệ phải bắt để xử lý tranh chấp. Việc một điều kiện không còn đúng là một kết quả dự kiến khi nhiều bên cạnh tranh.

### 6.4. Điều kiện dùng bằng nhau về giá trị

~~~text
same-reference = false
replace-equal-value = true
~~~

Hai đối tượng `String` khác tham chiếu nhưng cùng nội dung `OPEN`. Điều kiện thay vẫn khớp. Vì vậy, dùng `new String(...)` để tạo “mã riêng” không tạo danh tính phiên riêng nếu nội dung mã vẫn giống nhau.

### 6.5. Map chỉ có một khóa nhưng hai bên vẫn có thể tự nhận thắng

Trong phần `check-then-put`, hàng rào bắt buộc hai luồng hoàn tất việc kiểm tra khóa vắng trước khi bên nào được ghi. Cả hai đi vào nhánh `if` và đều tăng số người tự nhận thắng. Kết quả là `2`.

Phần `putIfAbsent` đặt hàng rào trước thao tác nguyên tử. Hai bên vẫn cạnh tranh nhưng chỉ bên nhận `null` mới tăng số thắng. Vì không có xóa hay thay khóa trong giai đoạn này, kết quả là `1`.

Nếu có bên xóa rồi cho phép tạo lại, nhiều lời gọi `putIfAbsent` có thể lần lượt thành công ở những vòng đời khác nhau của cùng khóa. Do đó “một người thắng” phải được gắn với khoảng thời gian và quy tắc vòng đời mà bài toán định nghĩa.

### 6.6. get rồi put có thể làm mất một lần tăng

Trong phần `broken`, cả hai luồng đọc `0` trước hàng rào, rồi đều ghi `1`. Có hai yêu cầu tăng nhưng kết quả chỉ là `1`.

Trong `fixed`, `addOne` lặp lại việc đọc và thử thay bằng điều kiện. Nếu khóa vắng, nó thử thêm `1`; nếu đã có, nó chỉ thay khi giá trị vẫn bằng giá trị vừa đọc. Khi một bên đã cập nhật trước, bên còn lại phải đọc lại và tính lại.

Hai luồng mỗi luồng tăng `1.000` lần, không có bên xóa khóa và không có phép ghi khác, nên kết quả kiểm chứng là `2.000`.

### 6.7. Điều kiện bằng nhau không giữ lịch sử thay đổi

`plain-ABA-update = true` đến từ trình tự:

~~~text
Đọc A làm giá trị mong đợi
Giá trị được thay thành B
Giá trị được thay lại thành A
Thử thay với điều kiện vẫn bằng A
Kết quả: điều kiện khớp
~~~

Nếu yêu cầu chỉ là “giá trị hiện tại bằng A”, việc thành công là đúng hợp đồng. Nếu yêu cầu là “không có ai cập nhật kể từ khi tôi đọc”, điều kiện ấy quá yếu. Hiện tượng giá trị quay lại A sau khi đã qua B thường được gọi là **ABA**.

Phần `versions` thêm số phiên bản. Giá trị hiện tại là `Revision(3, "READY")`, khác bản đã đọc `Revision(1, "READY")`, nên cập nhật cũ bị từ chối.

Record trong ví dụ có các thành phần `long` và `String`; phép bằng nhau do record tạo sẵn xét các thành phần tương ứng. Vì vậy số phiên bản là một phần của điều kiện, không chỉ là dữ liệu để ghi log. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

### 6.8. Điều kiện thêm không trì hoãn tính đối số

~~~text
eager-builds = 2
eager-stored = candidate-1
~~~

Hai lời gọi `build` đã chạy khi Java đánh giá đối số trước khi gọi `putIfAbsent`. Lần tạo thứ hai có thể tốn công dù giá trị của nó không được chọn.

Khi `computeIfAbsent` được gọi trên khóa đã có trong ví dụ, hàm tạo không chạy:

~~~text
existing-compute-builds = 0
existing-compute-value = candidate-1
~~~

Sự khác nhau này giúp chọn API, nhưng không được suy rằng mọi triển khai `ConcurrentMap` đều có cùng số lần gọi hàm tính trong mọi tình huống cạnh tranh.

## 7. Vòng lặp cập nhật có điều kiện

`addOne` là một mẫu cập nhật lạc quan: đọc trạng thái, tính ứng viên mới, yêu cầu thay nếu trạng thái vẫn khớp; nếu không được chấp nhận thì thử lại trên dữ liệu vừa đọc lại.

Mẫu được dùng để hiểu cơ chế, không phải khuyến nghị tự viết mọi phép đếm bằng một vòng lặp dài. Với một phép tính đơn giản, API như `merge` của lớp cụ thể có thể biểu đạt ngắn hơn.

### 7.1. Vì sao cần đọc lại sau thất bại?

Giả sử hai luồng cùng đọc số `10` và cùng tính `11`. Một bên thay thành công. Bên còn lại phải dùng `11` để tính `12`.

Nếu bên thất bại cứ thử `replace(key, 10, 11)` mà không đọc lại, nó đang giữ nguyên một giả định đã lỗi thời. Nếu nó gọi `put(key, 11)` để “chắc chắn ghi được” thì lại có thể ghi đè một cập nhật mới hơn.

Vòng lặp trong chương trình luôn quay lại `get`. Tính toán dựa trên bản đọc mới, không dùng lại kết quả của lần thất bại.

### 7.2. Giữ phần tính có thể lặp lại được

Trong một lần cập nhật thành công, đoạn tính ứng viên có thể đã chạy nhiều lần do các lần thử thất bại. Vì vậy đoạn này nên tính trên dữ liệu đầu vào và tạo một kết quả mới, tránh tác dụng bên ngoài không thể lặp an toàn.

Không đặt việc gửi thông báo, trừ tiền ở hệ thống khác hoặc xác nhận hoàn tất tác vụ vào trước phép thay có điều kiện rồi cho rằng chúng chỉ xảy ra một lần. Kết quả map không hoàn tác các tác dụng ấy khi phép thay thất bại.

Sau khi `replace` trả `true`, thực hiện một tác dụng bên ngoài cũng chưa trở thành một giao dịch chung với map. Nếu tiến trình dừng giữa hai bước, vẫn cần thiết kế khôi phục theo yêu cầu thực tế.

### 7.3. Khóa vắng và việc tạo lại phải có ý nghĩa

`addOne` coi khóa vắng là số đếm chưa tồn tại và thử tạo `1`. Nếu một luồng khác xóa khóa giữa chừng, vòng lặp có thể tạo lại nó.

Điều đó phù hợp với một bộ đếm cho phép bắt đầu lại sau khi vắng, nhưng có thể sai nếu xóa nghĩa là “tác vụ đã đóng, không được mở lại”. Khi ấy cần mô hình trạng thái đóng riêng hoặc một giao thức không tái tạo tùy ý.

Không có một vòng lặp điều kiện chung phù hợp cho mọi ý nghĩa của thao tác xóa.

### 7.4. Nguyên tử không nói lên thuật toán không khóa

`ConcurrentMap` là hợp đồng giao diện. Không thể từ việc có `replace` nguyên tử mà kết luận triển khai dùng đúng một lệnh CPU, không bao giờ chặn hoặc bảo đảm một luồng cụ thể luôn thắng trong thời gian hữu hạn.

Dưới tranh chấp liên tục, một bên có thể phải thử lại nhiều lần. Khi lựa chọn thuật toán cho đường xử lý quan trọng, cần xét hợp đồng lớp, mức tranh chấp và yêu cầu tiến triển, thay vì chỉ nhìn tên thao tác.

## 8. Thiết kế giá trị cho điều kiện đáng tin

### 8.1. Ưu tiên thay cả giá trị bất biến

Một mô hình thuận lợi là:

~~~text
Đọc một giá trị không bị sửa tại chỗ
    -> tạo một giá trị mới
    -> thay có điều kiện dựa trên giá trị cũ
~~~

Với record `Revision` trong chương trình, thành phần số và chuỗi không bị thay đổi qua đối tượng cũ. Khi giá trị mới được lưu, bản đọc cũ vẫn mô tả đúng trạng thái mà bên gọi đã đọc.

Một record nói chung không tự sao chép sâu mọi đối tượng nằm trong các thành phần. Nếu thành phần là danh sách có thể sửa, tính bất biến phải được thiết kế thêm. Trong ví dụ chỉ dùng `long` và `String` để tránh vấn đề ấy.

### 8.2. Tham chiếu cũ đến đối tượng có thể sửa chưa phải bản cũ

Giả sử giá trị là một đối tượng `Account` có trường `balance` có thể đổi. Bên gọi lấy `observed = map.get(key)`. Sau đó ai đó sửa `balance` trên chính đối tượng mà `observed` trỏ tới.

Lúc ấy `observed` không còn mô tả riêng “số dư tại lúc tôi đọc”. Nó vẫn trỏ đến đối tượng đang bị sửa. Một phép điều kiện dùng lại tham chiếu ấy có thể khớp dù nội dung đã đổi.

Cách giải quyết không nằm ở việc thêm một lần `get`. Cần giá trị bất biến, một bản dữ liệu có phiên bản, hoặc giao thức khóa riêng cho đối tượng và thao tác liên quan.

### 8.3. Phiên bản chỉ hữu ích khi mọi bên tuân thủ

Ví dụ `Revision` chống được trường hợp cũ phiên bản `1` quay lại trạng thái chữ `READY` ở phiên bản `3`. Nhưng bảo đảm này phụ thuộc vào quy tắc cập nhật:

- Mỗi cập nhật cần tăng hoặc tạo một dấu phiên bản mới phù hợp.
- Mọi đường ghi phải giữ quy tắc đó, kể cả công cụ dọn dẹp và đường khôi phục.
- Xóa rồi thêm lại không được vô tình tái sử dụng dấu nhận diện mà một yêu cầu cũ vẫn còn giữ.
- Phép bằng nhau phải bao gồm dấu nhận diện cần kiểm tra.
- Phải xét giới hạn miền giá trị và việc cấp lại phiên bản nếu hệ thống tồn tại đủ lâu.

Chỉ thêm một trường `version` vào lớp không tự buộc các bên ghi phải dùng nó. Việc một bên gọi `put` không điều kiện có thể vượt qua giao thức cập nhật lạc quan của các bên khác.

### 8.4. Khóa cũng phải có ngữ nghĩa ổn định

Khóa dùng trong map phải tuân thủ hợp đồng bằng nhau và băm hoặc so sánh thứ tự của lớp map đang dùng. Thay các thành phần quyết định `equals`/`hashCode` của khóa trong lúc khóa đang được lưu có thể làm cách truy tìm không còn đáng tin. `Map` cảnh báo rõ về khóa có thể thay đổi theo cách ảnh hưởng phép bằng nhau. [Java 17: quy tắc về khóa có thể thay đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Các thao tác điều kiện không chữa được một mô hình khóa đang thay danh tính trong lúc được dùng làm khóa.

## 9. Liên hệ với compute và merge

Bốn thao tác cốt lõi nhận một ứng viên đã được bên gọi tính sẵn. Các phương thức `computeIfAbsent`, `computeIfPresent`, `compute` và `merge` nhận thêm hàm tính để map có thể phối hợp quá trình cập nhật theo hợp đồng của phương thức.

Phân biệt nhu cầu:

| Nhu cầu | Công cụ thường được xét |
|---|---|
| Có sẵn ứng viên, chỉ muốn thêm khi vắng | `putIfAbsent` |
| Có bản cũ cụ thể, chỉ muốn thay nếu vẫn khớp | `replace(k, expected, replacement)` |
| Chỉ muốn dọn đúng đăng ký đang giữ | `remove(k, expected)` |
| Muốn tạo giá trị khi chưa có bằng hàm tính | `computeIfAbsent` |
| Muốn tính giá trị mới từ giá trị hiện tại | `compute`, `computeIfPresent` hoặc `merge`, tùy điều kiện vắng và ý nghĩa kết quả |

Điểm cần lưu ý là **hợp đồng của giao diện và hợp đồng mạnh hơn của lớp triển khai không luôn giống nhau**.

Trong `ConcurrentMap`, các triển khai mặc định của một số phương thức tính lại có thể thực hiện lại quá trình khi cập nhật cạnh tranh; hàm cập nhật có thể chạy nhiều lần. Không mang giả định “hàm luôn chỉ chạy một lần” sang một triển khai bất kỳ. [Java 17: ConcurrentMap.compute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction))

`ConcurrentHashMap` quy định lời gọi `computeIfAbsent` được thực hiện nguyên tử và hàm được gọi một lần cho lời gọi cần tính khi khóa vắng; tính toán nên ngắn, đơn giản và không sửa map trong lúc tính. Đó vẫn không phải cam kết “một lần duy nhất trong toàn bộ vòng đời khóa”: giá trị có thể bị xóa, hàm có thể trả `null` hoặc ném lỗi, và các lời gọi sau có điều kiện khác. [Java 17: ConcurrentHashMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

`ConcurrentSkipListMap` là một triển khai `ConcurrentMap` khác, có khóa theo thứ tự. Tài liệu của nó không hứa hàm `computeIfAbsent` chỉ được áp dụng một lần nguyên tử khi vắng. Vì vậy không sao chép giả định riêng của `ConcurrentHashMap` chỉ vì cả hai cùng mang giao diện `ConcurrentMap`. [Java 17: ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function))

Các khác biệt ấy là lý do cần đọc hợp đồng đúng phương thức trên đúng lớp triển khai khi hàm có chi phí lớn, tác dụng bên ngoài hoặc yêu cầu số lần gọi.

## 10. Các giới hạn cần giữ rõ

### 10.1. Chính sách null thuộc triển khai cụ thể

`ConcurrentHashMap` và `ConcurrentSkipListMap` không cho phép khóa hoặc giá trị `null`. Chương trình kiểm chứng dùng `ConcurrentHashMap` và cho thấy `putIfAbsent` với khóa hoặc giá trị `null` ném `NullPointerException`.

Không biến điều đó thành phát biểu rằng mọi lớp có thể triển khai `ConcurrentMap` đều bắt buộc cấm `null` theo cùng một cách. Javadoc giao diện có các ghi chú cho triển khai hỗ trợ `null`; nhiều phương thức mặc định dựa trên giả định `get` trả `null` có nghĩa là vắng và cần được ghi đè khi giả định không đúng. [Java 17: ConcurrentMap.getOrDefault, ghi chú triển khai](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#getOrDefault(java.lang.Object,V))

Trong mã tổng quát, không dùng `replace(key, null, value)` làm phép “thêm khi vắng”. API diễn đạt đúng ý đó là `putIfAbsent`, cùng với chính sách null của lớp cụ thể.

### 10.2. Công bố ánh xạ không tự đồng bộ mọi thay đổi về sau

`ConcurrentMap` có bảo đảm công bố dữ liệu đối với các hành động trước khi đưa đối tượng vào map và hành động truy cập hoặc lấy ra đối tượng ấy ở luồng khác. Điều này giúp trao đối tượng đã khởi tạo qua map. Nó không tự bảo vệ mọi sửa đổi tại chỗ diễn ra sau đó. [Java 17: hiệu ứng nhất quán bộ nhớ của ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

Ví dụ `ConcurrentMap<String, List<String>>` không tự làm một `ArrayList` được lưu làm giá trị trở nên an toàn khi nhiều luồng gọi `add` trên danh sách đó. Cần chọn giá trị có hợp đồng phù hợp hoặc thay cả giá trị theo giao thức điều kiện.

### 10.3. Một khóa không phải giao dịch nhiều khóa

Hai lời gọi điều kiện trên `account-A` và `account-B` là hai thao tác. Nếu lần đầu thành công còn lần sau thất bại, map không tự hoàn tác lần đầu.

Những quy tắc như chuyển số lượng giữa hai kho, đổi cả hai chỉ mục, hoặc cập nhật map cùng một bản ghi bên ngoài cần cơ chế nhất quán rộng hơn. Có thể là khóa chung mà tất cả bên liên quan tuân thủ, gom trạng thái vào một giá trị, hoặc giao dịch ở nơi sở hữu dữ liệu; lựa chọn phụ thuộc bài toán.

`synchronized (map)` do một bên tự thêm không khiến các lời gọi thông thường của `ConcurrentHashMap` từ bên khác tự động tham gia monitor ấy. Một giao thức khóa ngoài chỉ có tác dụng bao trùm khi mọi truy cập liên quan phối hợp theo nó.

### 10.4. Cập nhật có điều kiện không cung cấp bản chụp toàn map

Các phép điều kiện bảo vệ quyết định trên ánh xạ đang xét. Chúng không làm một lượt duyệt, `size` hoặc một chuỗi đọc nhiều khóa trở thành bản chụp nguyên khối.

Nếu cần xuất một báo cáo nhất quán của toàn map, hãy xác định thời điểm dữ liệu và cơ chế lấy bản chụp. Nếu chỉ cần giám sát trạng thái đang biến động, mức nhất quán yếu hơn có thể phù hợp. Cần phân biệt yêu cầu ấy với việc cập nhật một khóa có điều kiện.

### 10.5. Kiểu khai báo không tự đổi triển khai

`Map` đã có các tên phương thức như `putIfAbsent` và `replace`, nhưng triển khai mặc định của nó không hứa đồng bộ/nguyên tử cho mọi map. Một `HashMap` không trở thành cấu trúc đồng thời chỉ vì dùng tên API này. [Java 17: Map.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putIfAbsent(K,V))

Ngược lại, một biến khai báo là `Map` nhưng thực sự trỏ đến `ConcurrentHashMap` vẫn gọi phương thức của đối tượng đó. Khai báo `ConcurrentMap` thường giúp thể hiện yêu cầu đồng thời của mã sử dụng; điều quyết định bảo đảm thực tế là hợp đồng mà đối tượng triển khai đáp ứng.

## 11. Cách chọn và kiểm chứng

Trước khi viết mã, mô tả thao tác bằng một câu có điều kiện:

- “Chỉ thêm nếu khóa chưa có.”
- “Chỉ thay nếu giá trị vẫn bằng bản tôi đang dùng.”
- “Chỉ xóa nếu đăng ký vẫn thuộc đúng phiên này.”
- “Tính lại từ giá trị hiện tại và thử lại nếu đã bị thay.”

Sau đó đối chiếu lần lượt:

1. Điều kiện chỉ liên quan một ánh xạ hay nhiều đối tượng?
2. So sánh theo `equals` đã đủ hay cần mã phiên/phiên bản?
3. Giá trị có bị sửa tại chỗ làm bản mong đợi thay đổi theo không?
4. Kết quả trả về được dùng ngay để phân biệt thành công và thất bại chưa?
5. Đoạn tính có thể chạy lại mà không tạo tác dụng lặp sai không?
6. Khóa có thể bị xóa và tái tạo trong khi yêu cầu cũ vẫn còn chạy không?
7. Chính sách `null` và hợp đồng hàm tính thuộc đúng lớp triển khai nào?

Trong kiểm thử, hãy kiểm tra kết quả trực tiếp: số người được công nhận thắng, số đếm cuối, trạng thái mới và việc một yêu cầu cũ bị từ chối. Không chỉ kiểm tra “không ném ngoại lệ”.

Chương trình trên dùng hàng rào để buộc lịch làm mất cập nhật và lịch cùng nhận thắng. Các ví dụ ABA và phiên bản dùng chuỗi tuần tự để tái hiện lịch sử mà một yêu cầu cũ có thể gặp. Việc tách các điều kiện như vậy giúp giải thích kết quả, thay vì phụ thuộc vào xác suất luồng chạy theo thứ tự nào.

## 12. Bài tập tự kiểm tra

### Bài 1 — Đọc đúng putIfAbsent

Một `ConcurrentHashMap` đã có `id → "Mai"`. Lời gọi `putIfAbsent(id, "Lan")` trả gì, lưu gì, và bên gọi có vừa thêm thành công không?

**Đáp án:** Trả `"Mai"`, giữ `"Mai"`, không thêm. Ứng viên `"Lan"` không phải kết quả được chọn.

### Bài 2 — Hai dạng replace

Một luồng đọc `PENDING` nhưng trước khi ghi, luồng khác đổi sang `CANCELLED`. So sánh `replace(k, "RUNNING")` và `replace(k, "PENDING", "RUNNING")`.

**Đáp án:** Dạng hai đối số chỉ đòi khóa còn có giá trị, nên có thể thay `CANCELLED`. Dạng ba đối số thất bại nếu giá trị hiện tại không còn bằng `PENDING`. Chọn dạng thứ hai khi cần bảo vệ giả định trạng thái cũ.

### Bài 3 — Dọn đăng ký cũ

A giữ mã phiên `A-1`. Map đã chuyển sang phiên `B-1`. A nên gọi `remove(k)` hay `remove(k, "A-1")`?

**Đáp án:** Dạng có giá trị mong đợi, để không xóa ánh xạ mới `B-1`. Nếu ứng dụng tái sử dụng mã phiên không phân biệt các lần đăng ký, phải sửa mô hình dấu nhận diện trước.

### Bài 4 — Thành công nhưng get lại thấy khác

`replace(k, old, next)` trả `true`, nhưng `get(k)` ở dòng sau trả một giá trị thứ ba. Có đủ cơ sở kết luận thao tác điều kiện không nguyên tử không?

**Đáp án:** Không. Một bên khác có thể cập nhật sau lần thay thành công và trước lần đọc. Kết quả `true` nói về lời gọi vừa thực hiện, không khóa trạng thái cho các dòng sau.

### Bài 5 — Giá trị A quay lại

Một yêu cầu giữ `A`; map lần lượt có `B` rồi lại `A`. `replace(k, A, C)` có đủ để phát hiện mọi cập nhật ở giữa không?

**Đáp án:** Không. Nó kiểm tra giá trị hiện tại bằng `A`, không kiểm tra lịch sử. Nếu cần phát hiện lịch sử thay đổi, dùng giá trị có phiên bản hoặc dấu nhận diện phù hợp và bảo đảm mọi đường ghi tuân thủ.

### Bài 6 — Hàm tạo tốn công

Vì sao `putIfAbsent(k, create())` vẫn gọi `create` khi khóa đã có? Có thể luôn thay bằng `computeIfAbsent` rồi khẳng định hàm chỉ chạy một lần trong suốt đời chương trình không?

**Đáp án:** Đối số được tính trước lời gọi. `computeIfAbsent` có thể tránh tính khi đã có giá trị, nhưng số lần và phạm vi nguyên tử của hàm phải đọc theo lớp triển khai. Ngay cả hợp đồng mạnh của `ConcurrentHashMap` cũng không phải bảo đảm chỉ tính một lần suốt vòng đời khóa.

### Bài 7 — Map an toàn, danh sách bên trong

`ConcurrentMap<String, ArrayList<String>>` được nhiều luồng lấy danh sách rồi cùng `add`. Tính nguyên tử của `putIfAbsent` có đủ bảo vệ các lần `add` không?

**Đáp án:** Không. Thêm ánh xạ an toàn và sửa đối tượng làm giá trị là hai việc khác nhau. Cần loại giá trị phù hợp hoặc giao thức cập nhật riêng.

### Bài 8 — Tăng số đếm và xóa khóa

Một vòng lặp như `addOne` đọc thấy khóa vắng sau khi bên quản lý đã xóa để đóng tác vụ. Nó thử `putIfAbsent(k, 1)`. Vì sao thao tác có thể đúng hợp đồng map nhưng sai yêu cầu?

**Đáp án:** Map cho phép tạo ánh xạ khi vắng, nhưng “đã xóa” có thể mang nghĩa nghiệp vụ không được tái tạo. Cần mô hình trạng thái đóng hoặc quy tắc vòng đời rõ, không dùng sự vắng mặt đồng thời cho hai ý nghĩa khác nhau.

Một thao tác điều kiện hữu ích khi điều kiện của API diễn đạt đúng điều kiện mà chương trình cần bảo vệ. Hãy thiết kế khóa, giá trị, phiên bản và cách đọc kết quả cùng nhau; từ đó mới có cơ sở mở rộng từ một cập nhật nguyên tử sang một luồng xử lý đúng.
