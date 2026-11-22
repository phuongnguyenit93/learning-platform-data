# Stateless objects và tránh trạng thái chia sẻ trong Java Concurrency

## 1. Vì sao thiết kế stateless giúp thread-safe?

Một tình huống quen thuộc: nhiều thread cùng gọi một đối tượng dùng chung. Nếu mỗi lời gọi ghi dữ liệu tạm của chính nó vào một field của đối tượng, lời gọi sau có thể ghi đè dữ liệu mà lời gọi trước chưa sử dụng xong. Đó là một dạng race condition thường gặp, dù từng phương thức trông rất đơn giản.

**Thiết kế stateless (không giữ trạng thái thay đổi theo từng tác vụ)** giúp loại bỏ nhiều nguồn race ngay từ cấu trúc chương trình: mỗi lần gọi nhận đầu vào, tính toán bằng biến cục bộ và trả kết quả; dữ liệu đang xử lý không được lưu trong các instance/static fields dùng chung. Khi không có mutable state chung, không cần khóa chỉ để bảo vệ dữ liệu trung gian của các lời gọi độc lập.

Sau bài này, bạn sẽ:

- Phân biệt **stateless object**, **immutable object**, **thread-confined state** và **thread-safe stateful object**.
- Xác định đúng nơi tồn tại shared mutable state, kể cả static field, collection, đối tượng được truyền tham chiếu, lambda capture và dependency bên ngoài.
- Nhận diện lỗi lưu dữ liệu theo tác vụ vào field; hiểu tại sao synchronized từng getter/setter không cứu được chuỗi hành động phụ thuộc nhau.
- Chuyển thiết kế sang truyền dữ liệu qua tham số, dùng biến local, giá trị trả về, immutable snapshots và kết hợp kết quả sau khi task hoàn thành.
- Biết giới hạn: stateless Java object vẫn có thể gây lỗi concurrency nếu gọi dependency không thread-safe hoặc thao tác lên tài nguyên ngoài có trạng thái.
- Biên dịch/chạy ví dụ Java 17+ để thấy rõ lỗi và cách sửa, đồng thời có checklist review code.

Phạm vi bài học chỉ là **Java SE/JVM concurrency**, không phụ thuộc vào framework.

## 2. Ba câu hỏi phải tách biệt

Ba khái niệm sau liên quan nhau nhưng **không đồng nghĩa**:

| Khái niệm | Đặc điểm | Ví dụ |
|---|---|---|
| **Stateless** | Không giữ mutable data giữa các lần gọi có thể ảnh hưởng kết quả của lần gọi khác; dữ liệu tác vụ nằm trong tham số/local/result. | Hàm chuẩn hóa chuỗi chỉ nhận đầu vào và tạo chuỗi mới. |
| **Immutable** | Trạng thái một đối tượng không thay đổi sau khi xây dựng đúng cách; có thể có state cấu hình cố định. | Record chứa String, int; BigDecimal; một policy có final immutable settings. |
| **Thread-safe** | Có hợp đồng hoạt động đúng khi nhiều thread truy cập theo cách được hỗ trợ. Có thể stateless, immutable hoặc stateful được đồng bộ. | AtomicInteger là thread-safe nhưng **stateful**; counter có synchronized method cũng stateful. |

Một đối tượng **strictly stateless** không cần lưu state phụ thuộc từng lời gọi. Tuy vậy, trong thực tế người ta còn gọi một *service stateless* khi nó giữ **immutable configuration** cố định (ví dụ tỷ lệ thuế), bởi nó không lưu tiến trình hay dữ liệu theo từng request. Để diễn đạt chính xác: service đó **không giữ mutable per-call state**, chứ không phải hoàn toàn không có field.

**Thread safety là thuộc tính của toàn bộ giao thức sử dụng đối tượng**, không chỉ của tên class hay annotation. Một phương thức có thể không giữ field nhưng vẫn không an toàn nếu nó sửa một List dùng chung, gọi static mutable state hoặc tương tác với dependency không thread-safe.

### Phân biệt các phạm vi dữ liệu

~~~text
                 Một instance dùng chung
             ┌───────────────────────────┐
Thread A ───▶│ method(inputA)            │
             │   localA = ...            │──▶ resultA
             │                           │
Thread B ───▶│ method(inputB)            │
             │   localB = ...            │──▶ resultB
             └───────────────────────────┘
                  KHÔNG có mutable
                 per-call field chung

Khác với:
             ┌───────────────────────────┐
Thread A ───▶│ this.currentInput = "A"  │
Thread B ───▶│ this.currentInput = "B"  │
             │ dùng this.currentInput    │
             └───────────────────────────┘
                Cùng đọc/ghi một field
~~~

Hai biến local độc lập trong hai lượt thực thi không trở thành một biến dùng chung chỉ vì hai thread cùng gọi một instance method. Mỗi lời gọi có các local variables và tham số riêng về mặt ngữ nghĩa. Nhưng **giá trị tham chiếu** trong local có thể trỏ tới cùng một object mutable; chỉ tên biến là local không tự bảo đảm object được tham chiếu là riêng.

## 3. Trạng thái chia sẻ xuất hiện từ đâu?

Một giá trị trở thành nguồn rủi ro khi có các điều kiện:

1. Có thể được nhiều thread truy cập trong khoảng thời gian chồng lấn.
2. Ít nhất một thread có thể **thay đổi** cùng trạng thái đó.
3. Không có ownership hoặc giao thức đồng bộ bảo đảm cho những truy cập cạnh tranh.

Các nguồn shared state phổ biến:

| Nơi tồn tại | Ví dụ | Cần kiểm tra |
|---|---|---|
| Instance field | this.lastInput, this.buffer | Cùng instance có được nhiều worker dùng chung không? |
| Static field | static int requestCount | Nhiều instance vẫn cùng ghi một class-level field. |
| Collection truyền vào method | List, Map, Set, array | Các caller có giữ cùng một tham chiếu và sửa đồng thời không? |
| Object nằm trong collection | Map<String, MutableValue> | Map thread-safe cũng không tự làm value mutable thành thread-safe. |
| Dependency giữ bên trong service | client, formatter, accumulator, cache | Dependency có state mutable và được dùng đồng thời không? |
| Lambda/closure | Runnable bắt giữ một List, AtomicInteger hoặc object | Biến local được capture có thể trỏ tới shared mutable object. |
| File, DB, socket, process ngoài | ghi cùng tệp, update cùng bản ghi, gửi cùng session | Dữ liệu ngoài JVM có thứ tự và bất biến riêng. |
| ThreadLocal | dữ liệu riêng theo thread | Không phải stateless; worker pool có thể giữ state giữa nhiều task. |

Đặc biệt, **final chỉ khóa tham chiếu field**, không đóng băng đối tượng mà nó trỏ tới:

~~~java
final class UnsafeTags {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    void add(String tag) {
        tags.add(tag); // vẫn thay đổi ArrayList dùng chung
    }
}
~~~

Đây là đoạn class minh họa, không có main độc lập. Field final không thể đổi sang List khác, nhưng nội dung ArrayList vẫn mutable. Nếu nhiều thread cùng gọi add, ArrayList không cung cấp bảo đảm thread-safe.

## 4. Ví dụ lỗi: lưu input của từng tác vụ vào field

Giả sử một formatter phục vụ nhiều cuộc gọi:

~~~java
class StatefulLabelService {
    private String lastLabel;

    void remember(String label) {
        lastLabel = label;
    }

    String render() {
        return "[" + lastLabel + "]";
    }
}
~~~

Caller mong rằng chuỗi gọi remember("A") rồi render() sẽ trả [A]. Nhưng nếu một thread khác kịp gọi remember("B") trước render(), kết quả thành [B]. Đây là lỗi **cross-request interference**: dữ liệu của tác vụ này lẫn sang tác vụ khác.

Một suy nghĩ sai: “Nếu thêm synchronized cho remember và render thì ổn.” Việc khóa mỗi method riêng lẻ chỉ làm mỗi method có mutual exclusion khi chạy; **cặp** remember → render vẫn có thể xen kẽ với tác vụ khác:

~~~text
Thread A                  Thread B
remember("A")
                          remember("B")
render() -> "[B]"
                          render() -> "[B]"
~~~

Ngay cả khi cả remember() và render() đều synchronized, lịch thực thi trên vẫn hợp lệ vì monitor được nhả giữa hai lần gọi. Muốn giữ tính nhất quán của **cả chuỗi**, phải thiết kế một atomic method hoặc một lock bao toàn sequence. Giải pháp đơn giản hơn ở đây là **không lưu lastLabel trong shared field**.

## 5. Ví dụ chạy độc lập: dàn dựng lỗi và thiết kế stateless

Ví dụ sau dùng CountDownLatch để tạo một lịch chạy xác định. Thread A ghi "A", thread B ghi đè "B", sau đó cả hai đọc lại một field chung. Sau đó chương trình cho hai thread dùng **cùng một StatelessLabelService** nhưng mỗi lần gọi giữ input trong tham số; kết quả đúng với từng caller.

Lưu tệp **StatelessServiceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class StatelessServiceDemo {
    static final class StatefulLabelService {
        private String lastLabel;

        void remember(String label) {
            lastLabel = label;
        }

        String render() {
            return "[" + lastLabel + "]";
        }
    }

    static final class StatelessLabelService {
        String format(String label) {
            String normalized = label.trim();
            return "[" + normalized + "]";
        }
    }

    public static void main(String[] args) throws InterruptedException {
        StatefulLabelService bad = new StatefulLabelService();
        CountDownLatch aWritten = new CountDownLatch(1);
        CountDownLatch bWritten = new CountDownLatch(1);
        String[] badResults = new String[2];

        Thread a = new Thread(() -> {
            try {
                bad.remember("A");
                aWritten.countDown();
                bWritten.await();
                badResults[0] = bad.render();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "bad-A");

        Thread b = new Thread(() -> {
            try {
                aWritten.await();
                bad.remember("B");
                bWritten.countDown();
                badResults[1] = bad.render();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "bad-B");

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("stateful A=" + badResults[0]);
        System.out.println("stateful B=" + badResults[1]);

        StatelessLabelService good = new StatelessLabelService();
        String[] goodResults = new String[2];
        Thread c = new Thread(
                () -> goodResults[0] = good.format("A"), "good-A");
        Thread d = new Thread(
                () -> goodResults[1] = good.format("B"), "good-B");

        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("stateless A=" + goodResults[0]);
        System.out.println("stateless B=" + goodResults[1]);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac StatelessServiceDemo.java
java StatelessServiceDemo
~~~

Kết quả trong điều kiện không có interrupt bên ngoài:

~~~text
stateful A=[B]
stateful B=[B]
stateless A=[A]
stateless B=[B]
~~~

**Lý do output xác định:**

- \`aWritten\` buộc B đợi A ghi xong, rồi B ghi "B" trước khi A tiếp tục. \`bWritten\` buộc A đợi B ghi xong rồi mới đọc field, vì vậy A thấy "B".
- B đọc ngay sau khi ghi "B"; không có lần ghi nào khác. Vì thế hai kết quả stateful đều là [B].
- Hai thread good gọi \`format\` trên **cùng instance**, nhưng method chỉ sử dụng \`label\` và local \`normalized\`, tạo String mới; không có shared mutable field để ghi đè.
- Mỗi thread ghi vào **vị trí riêng** của mảng kết quả; main đọc sau khi join tất cả các thread tương ứng. \`join()\` cung cấp quan hệ happens-before để main quan sát kết quả đã hoàn tất.
- Latch được dùng **để dàn dựng trình tự lỗi**, không phải để sửa một shared state. Cách sửa thực sự ở phần good là loại bỏ field chứa dữ liệu per-call.

Ví dụ intentionally đơn giản, nhằm chứng minh **đúng/sai về tính độc lập của lượt gọi**, không phải benchmark. Không dùng \`Thread.sleep\` để tạo một “race chắc chắn” vì thời gian ngủ không bảo đảm thứ tự thực thi.

## 6. Refactor: biến method thành một giao dịch đầu vào → đầu ra

Thay vì:

~~~java
class Formatter {
    private String currentUser;

    void setUser(String user) {
        currentUser = user;
    }

    String greeting() {
        return "Hello, " + currentUser;
    }
}
~~~

Thiết kế lại:

~~~java
class Formatter {
    String greeting(String user) {
        String normalized = user.strip();
        return "Hello, " + normalized;
    }
}
~~~

Method mới có hai đặc tính:

1. Dữ liệu \`user\` được đưa vào **lời gọi cụ thể**, không cần một lượt ghi vào instance để chuẩn bị cho lượt đọc tiếp theo.
2. Kết quả được **trả về trực tiếp** cho caller. Không tồn tại \`lastResult\` hoặc \`currentUser\` bị tác vụ khác ghi đè.

Ở đây \`String\` bất biến, \`strip()\` trả String phù hợp chứ không sửa input. Vì vậy các caller không chia sẻ mutable working state qua method.

**Lưu ý thiết kế API:** Một method xử lý nhiều tham số có thể nhận một immutable input object (record) để giữ ngữ nghĩa rõ ràng. Tránh thiết kế hai bước \`setContext(x)\` rồi \`execute()\` trên object được dùng chung, vì đó là một temporal coupling dễ tạo race khi nhiều thread cùng gọi.

## 7. Stateless service có immutable configuration

Trong ứng dụng thật, một object có thể cần cấu hình cố định: tỷ lệ, quy tắc định dạng, giới hạn mặc định, danh sách chính sách bất biến. Giữ immutable config không giống lưu per-request state.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

final class PriceCalculator {
    private final BigDecimal taxRate;

    PriceCalculator(BigDecimal taxRate) {
        this.taxRate = Objects.requireNonNull(taxRate);
    }

    BigDecimal total(BigDecimal amount) {
        Objects.requireNonNull(amount);
        return amount.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

\`PriceCalculator\` có **state cấu hình bất biến** là \`taxRate\`, nhưng không ghi trạng thái riêng cho từng phép tính. \`BigDecimal\` là immutable; phép tính tạo giá trị mới. Nếu object được khởi tạo và **publish an toàn** cho các worker, nhiều thread có thể gọi \`total()\` đồng thời mà không cần lock bảo vệ chính việc tính toán này.

### Ví dụ độc lập với ExecutorService

Lưu **StatelessPriceDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StatelessPriceDemo {
    static final class PriceCalculator {
        private final BigDecimal taxRate;

        PriceCalculator(BigDecimal taxRate) {
            this.taxRate = Objects.requireNonNull(taxRate);
        }

        BigDecimal total(BigDecimal amount) {
            Objects.requireNonNull(amount);
            return amount.multiply(BigDecimal.ONE.add(taxRate))
                    .setScale(2, RoundingMode.HALF_UP);
        }
    }

    public static void main(String[] args) throws Exception {
        PriceCalculator calculator =
                new PriceCalculator(new BigDecimal("0.08"));

        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Future<BigDecimal> a = workers.submit(() ->
                    calculator.total(new BigDecimal("100.00")));
            Future<BigDecimal> b = workers.submit(() ->
                    calculator.total(new BigDecimal("50.00")));

            System.out.println("A=" + a.get());
            System.out.println("B=" + b.get());
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Lệnh:

~~~bash
javac StatelessPriceDemo.java
java StatelessPriceDemo
~~~

Output:

~~~text
A=108.00
B=54.00
~~~

**Vì sao an toàn cho hai task?**

- Calculator được khởi tạo đầy đủ **trước** khi được capture vào Runnable/Callable gửi cho executor. Hợp đồng memory consistency của ExecutorService đảm bảo các hành động trước lúc submit happens-before hành động của task; tác vụ nhận được trạng thái constructor đã thiết lập.
- \`taxRate\` là final reference tới BigDecimal immutable. Không task nào cập nhật nó.
- Mỗi lần gọi \`total\` dùng tham số riêng, tạo kết quả BigDecimal mới và không ghi instance field.
- \`Future.get()\` đợi task hoàn tất, đồng thời tạo quan hệ happens-before để caller quan sát kết quả.
- Việc in theo thứ tự \`a.get()\` rồi \`b.get()\` không yêu cầu task A hoàn thành trước B. Hai task có thể được lập lịch theo bất kỳ thứ tự nào.
- \`shutdown()\` đóng đường nhận task mới; ví dụ đã gọi get() cho cả hai Future trước khi rời try. Với vòng đời thực tế còn cần timeout/hủy và phương án khi tác vụ lỗi hoặc không kết thúc.

Điểm quan trọng: **final reference không đủ nếu object cấu hình vẫn mutable**. Ví dụ \`private final ArrayList<String> rules\` vẫn cho phép sửa \`rules\` sau constructor, có thể gây race. Hãy sao chép/đóng băng đúng độ sâu cần thiết và dùng immutable elements khi cần.

## 8. Các pattern tránh mutable shared state

### Pattern A — Đưa dữ liệu theo tác vụ vào tham số

Thay \`this.input = x; process()\` bằng \`process(x)\`; trả giá trị thay vì ghi \`this.lastResult\`.

~~~java
String normalize(String input) {
    return input.strip().toLowerCase(java.util.Locale.ROOT);
}
~~~

Đoạn method minh họa này không lưu state và tạo String mới. Locale.ROOT hữu ích khi cần chuẩn hóa kỹ thuật không phụ thuộc locale của người dùng; việc chọn quy tắc normalize thực tế phải theo domain.

### Pattern B — Đưa giá trị trung gian vào biến local

~~~java
long sumSquares(int[] source) {
    long total = 0;
    for (int n : source) {
        total += (long) n * n;
    }
    return total;
}
~~~

\`total\` riêng cho mỗi invocation, nên không cần lock cho \`total\`. **Tuy nhiên**, caller có thể sửa mảng \`source\` trong lúc method đọc, tạo vấn đề snapshot dữ liệu. Nếu muốn kết quả ổn định, yêu cầu input không bị sửa đồng thời hoặc tạo bản sao trước khi tính. Cũng cần xác định chính sách overflow của phép cộng long khi dữ liệu rất lớn.

### Pattern C — Thread confinement hoặc task confinement

Một object mutable có thể an toàn nếu **chỉ một task/thread sở hữu nó** và không chia sẻ trước khi kết thúc. Ví dụ, mỗi task tạo StringBuilder riêng:

~~~java
String makeLabel(String first, String second) {
    StringBuilder local = new StringBuilder();
    local.append(first).append(" / ").append(second);
    return local.toString();
}
~~~

StringBuilder không synchronized và không thread-safe khi chia sẻ tùy tiện, nhưng **không có race** nếu chỉ dùng nó trong một invocation, không escape sang thread khác và không tồn tại shared reference. Không vì có class mutable mà bắt buộc dùng StringBuffer.

### Pattern D — Immutable input/result snapshot

~~~java
record JobInput(String id, int quantity) {}
record JobResult(String id, long doubledQuantity) {}

JobResult calculate(JobInput input) {
    return new JobResult(
            input.id(),
            (long) input.quantity() * 2
    );
}
~~~

\`record\` gọn, có final components và thích hợp biểu diễn input/result. Tuy nhiên record **chỉ shallow immutable** nếu component là đối tượng mutable. \`record Payload(List<String> items)\` không tự chặn caller sửa chính List truyền vào. Có thể dùng \`List.copyOf(items)\` trong constructor phù hợp, đồng thời đảm bảo phần tử trong List cũng có tính bất biến cần thiết.

### Pattern E — Tổng hợp kết quả sau khi task hoàn thành

Nếu mỗi task cần tính một giá trị riêng, hãy để nó trả giá trị thay vì cùng ghi vào field \`total\` của service. Caller có thể kết hợp \`Future\` results sau khi chờ hoàn tất, hoặc dùng stream reduction phù hợp với phép toán.

~~~java
// Đoạn trích trong method có List<Future<Long>> futures:
long total = 0;
for (java.util.concurrent.Future<Long> future : futures) {
    total = Math.addExact(total, future.get());
}
~~~

Đây là **đoạn trích**, \`futures\` được tạo ở code gọi và method phải khai báo/handle checked exceptions của get(). \`Math.addExact\` giúp phát hiện overflow thay vì âm thầm wraparound.

### Pattern F — Shared state không tránh được thì quản lý bằng protocol rõ ràng

Không phải mọi bài toán đều xóa được state. Metrics, cache, hàng đợi, session, inventory và tài nguyên bên ngoài có state nghiệp vụ thực. Khi đó:
- \`AtomicInteger\`/\`AtomicLong\` cho counter cập nhật nguyên tử đơn giản.
- \`LongAdder\` cho metric có nhiều writer, chấp nhận \`sum()\` không phải snapshot nguyên tử khi còn cập nhật.
- \`ConcurrentHashMap\` hoặc collection concurrent phù hợp nếu nhiều thread truy cập cấu trúc chung; không cho rằng sequence \`containsKey\` rồi \`put\` tự atomic.
- \`synchronized\`, \`ReentrantLock\`, CAS loop hoặc một owner thread để duy trì invariant nhiều bước.
- Bounded queue, timeout và backpressure khi task được giao qua các luồng.

Mục tiêu của stateless design là **giảm tối đa state chia sẻ không cần thiết**, không phủ nhận nhu cầu state hợp lệ.

## 9. Những hiểu nhầm cần tránh

### “Không có field” nghĩa là thread-safe trong mọi hoàn cảnh

Sai. Ví dụ:

~~~java
void append(java.util.List<String> target, String text) {
    target.add(text);
}
~~~

Method này không có instance field, nhưng hai thread có thể truyền **cùng ArrayList** vào target. Nếu ArrayList bị thêm phần tử đồng thời mà không có đồng bộ thích hợp, chương trình vẫn không thread-safe.

Tính an toàn phải xét luôn **ownership và thread-safety của đối tượng được truyền vào**. Stateless service chỉ loại bỏ một nguồn shared state nội bộ.

### “Mỗi thread có local variable” nghĩa là mọi object nó dùng đều riêng

Sai. Hai biến local \`List<String> mine\` có thể cùng trỏ đến một List, vì biến local lưu **tham chiếu**, không tạo bản copy của object. Đừng nhầm bảo vệ biến tham chiếu local với bảo vệ object trên heap.

### “final” biến mutable object thành immutable

Sai. \`final Map<String, String> settings = new HashMap<>()\` vẫn cho phép \`settings.put(...)\`. Muốn trạng thái bất biến, cần xây dựng cấu trúc không thể sửa hoặc không để lộ khả năng sửa ra bên ngoài. \`Map.copyOf\` tạo unmodifiable map tại tầng map, nhưng nếu values là mutable objects thì chúng vẫn có thể thay đổi.

### “synchronized mọi getter/setter là đủ”

Không hẳn. Nếu logic yêu cầu \`setUser(x)\` rồi \`getGreeting()\` tương ứng, khóa từng method riêng vẫn cho thread khác chen vào giữa. Thay bằng method stateless một bước hoặc bảo vệ **cả quy trình** dưới một critical section đúng đối tượng lock.

### “static counter chỉ có một bản nên an toàn”

Không. Chính vì là một bản dùng chung nên \`static int count; count++\` càng cần xem xét cạnh tranh. Static không cung cấp atomicity, visibility hay mutual exclusion.

### “Sử dụng ThreadLocal thì trở thành stateless”

Không. ThreadLocal **lưu state** gắn với thread hiện tại. Với thread pool, worker sống lâu có thể dùng lại cho nhiều task và giữ giá trị của task trước. Khi dùng ThreadLocal phải xác định phạm vi, khởi tạo và \`remove()\` trong finally khi phù hợp. ThreadLocal không thay thế API truyền context rõ ràng khi có thể tránh dùng shared state.

### “Dùng concurrent collection là mọi workflow đã atomic”

Không. Cấu trúc như ConcurrentHashMap cung cấp các hành động thread-safe theo API của nó; nhiều lời gọi tuần tự vẫn có thể bị interleave. Khi invariant là “nếu chưa có thì tạo”, cần chọn atomic operation như \`computeIfAbsent\` hoặc putIfAbsent đúng yêu cầu; mapping function phải tuân thủ hợp đồng và tránh tác dụng phụ không mong muốn.

### “Object immutable thì mọi hệ thống liên quan tự nhất quán”

Không. Immutable snapshot bảo vệ **bên trong dữ liệu đã chụp**, nhưng bản ghi bên ngoài JVM, network request và filesystem vẫn có concurrency semantics riêng. Một service không giữ field nhưng gọi hệ thống ngoài có thể vẫn gặp lost update hoặc race ở phía tài nguyên ngoài.

## 10. Stateless vs thread-safe stateful: chọn giải pháp đúng

| Tình huống | Cách tiếp cận | Vì sao |
|---|---|---|
| Format/validate/compute theo từng đầu vào | Stateless method, local variables | Không cần lưu intermediate per-call fields. |
| Có cấu hình đọc nhiều, ít thay đổi | Immutable configuration, safe publication | Chia sẻ an toàn cấu hình cố định. |
| Công việc gồm nhiều bước cần context | Immutable request context truyền vào method/task | Tránh setContext() trên shared instance. |
| Mỗi task cần mutable buffer tạm | Tạo buffer riêng trong task | Thread confinement, không chia sẻ. |
| Đếm tổng số lượt gọi | AtomicLong/LongAdder | Đây là state nghiệp vụ có thật, không thể “giả stateless”. |
| Cache dùng chung | Concurrent map và cơ chế cập nhật đúng | Cần chính sách capacity, consistency, eviction và đồng bộ khi cập nhật. |
| Nhiều giá trị phải nhất quán cùng lúc | Immutable snapshot thay thế nguyên tử hoặc lock chung | Giữ invariant đa trường trong một protocol. |
| Dữ liệu request bị đẩy vào mutable dependency | Tái thiết kế dependency hoặc bảo vệ truy cập | Service stateless bề mặt vẫn có thể race ở tầng dưới. |

Một quy trình ra quyết định hiệu quả:

1. **State đó có thật sự cần sống qua lời gọi?** Nếu không, chuyển thành parameter/local/result.
2. **Nếu cần chia sẻ, có thể immutable sau khi xây dựng không?** Nếu có, publish an toàn và không mutate.
3. **Nếu cần thay đổi, ai là owner và invariant nào cần giữ?** Chọn lock/CAS/concurrent data structure cho toàn bộ thao tác liên quan.
4. **Bao nhiêu thread sẽ truy cập cùng object?** Đo contention và profile trước khi tối ưu.
5. **Tài nguyên ngoài có state không?** Thiết kế protocol phù hợp cả bên ngoài JVM.

## 11. Publication, Java Memory Model và tính đúng đắn

Loại bỏ mutable per-call fields làm giảm race nội bộ, nhưng **an toàn công bố object** vẫn quan trọng. Nếu một object có immutable configuration, các thread khác phải nhận được reference của nó qua con đường publication được JMM bảo đảm.

Những cách thông dụng gồm: khởi tạo qua static initialization an toàn; truyền object cho executor task sau khi khởi tạo xong; đồng bộ/volatile reference thích hợp; hoặc xuất bản đối tượng được thiết kế immutable đúng cách, không để \`this\` escape trong constructor.

Ví dụ với \`ExecutorService.submit\`: các hành động trong thread trước khi submit task happens-before hành động bên trong task theo hợp đồng memory consistency của ExecutorService. Vì vậy, một instance với immutable config được khởi tạo trước khi submit có thể được dùng bởi nhiều tasks một cách an toàn cho phần đọc cấu hình đó.

\`final\` fields có quy tắc bảo đảm khởi tạo riêng trong JMM khi constructor hoàn thành đúng cách. Nhưng final không bảo vệ nội dung object mutable được field trỏ tới, và không biện minh cho việc để \`this\` escape trước khi constructor hoàn tất. Nếu thiết kế cho chia sẻ, nên ưu tiên ownership rõ ràng và tránh publication mập mờ.

### Happens-before và việc đọc kết quả

Khi task trả về dữ liệu vào \`Future\`, hợp đồng \`Future.get()\` giúp caller thấy các hành động của task đã hoàn tất. Tương tự, những hành động của thread trước khi kết thúc happens-before thread khác quay về từ \`join()\` tương ứng.

**Nhưng join/get không sửa race đã diễn ra trong task**: nếu hai task cùng ghi \`this.lastResult\`, chờ chúng xong chỉ giúp bạn thấy một trong các giá trị cuối. Cách đúng là không dùng field kết quả chung nếu mỗi task cần kết quả riêng.

## 12. Một ví dụ thiết kế sai thường khó nhận ra: mutable helper

Giả sử một service không có counter hay user field, nhưng giữ một StringBuilder để “tái sử dụng bộ nhớ”:

~~~java
class SharedBuilderFormatter {
    private final StringBuilder builder = new StringBuilder();

    String format(String name) {
        builder.setLength(0);
        builder.append("Hello ");
        builder.append(name);
        return builder.toString();
    }
}
~~~

Đây là một **đối tượng có mutable shared state** và không thread-safe. Hai thread gọi format đồng thời có thể xen kẽ setLength/append/toString, trả sai chuỗi hoặc gây lỗi tùy tình huống. \`final\` chỉ bảo đảm field builder không bị trỏ sang StringBuilder khác.

Cách sửa tự nhiên:

~~~java
class LocalBuilderFormatter {
    String format(String name) {
        StringBuilder local = new StringBuilder();
        local.append("Hello ").append(name);
        return local.toString();
    }
}
~~~

Mỗi invocation có buffer riêng. Đây là ví dụ điển hình của việc **tránh chia sẻ** thay vì áp lock cho một tài nguyên vốn không cần chung. JVM có thể tối ưu allocation trong nhiều trường hợp, nhưng không nên tuyên bố runtime chắc chắn loại bỏ được mọi allocation; hãy benchmark nếu hiệu năng allocation là vấn đề thực tế.

Nếu workload rất nặng và cần pooling thực sự, pooling phải được thiết kế có ownership, reset, exception handling và lifecycle rõ ràng. Đó là tradeoff phức tạp, không phải mặc định tối ưu.

## 13. Ranh giới với external state và side effects

Một phương thức Java không có field vẫn có thể gọi database, filesystem, socket hoặc một remote service để ghi dữ liệu. Về mặt **trạng thái nội bộ của object**, nó có thể stateless; về mặt **hiệu ứng nghiệp vụ**, nó không phải pure function và có thể cạnh tranh với các lời gọi khác.

Ví dụ minh họa:

~~~java
void transfer(AccountRepository repository,
              String from, String to, long amount) {
    // Các bước thực tế phải có transaction/atomicity theo hợp đồng
    // của nguồn dữ liệu. Chỉ vì method không giữ field không đủ.
}
~~~

Đây là **đoạn chữ ký minh họa**, các kiểu AccountRepository và logic chuyển tiền không được định nghĩa ở đây. Không coi nó là chương trình chạy được. Ý nghĩa: khi nhiều worker thao tác cùng external account, stateless Java object không thể bảo đảm invariant số dư. Cần giao thức ở đúng nơi sở hữu dữ liệu (atomic operation, transaction, versioning hoặc thiết kế khác theo hệ thống đó).

Trong phạm vi một JVM, cùng nguyên tắc áp dụng với file, shared cache, concurrent collection và resource pool. **Tránh state trong service** không đồng nghĩa xóa hết state khỏi hệ thống; nó khiến nơi sở hữu và bảo vệ state trở nên rõ ràng hơn.

## 14. Khi nào nên giữ state có chủ đích?

Một số đối tượng nên là stateful:

- **Counter/metric:** số yêu cầu hoặc sự kiện; dùng atomic/adder với semantics quan sát thích hợp.
- **Queue/channel:** danh sách công việc đang chờ, với capacity/backpressure và hợp đồng producer–consumer.
- **Cache:** chia sẻ kết quả, giới hạn dung lượng, hết hạn và nhất quán theo key.
- **State machine:** trạng thái chuyển qua các giai đoạn, phải giữ invariant giữa các transition.
- **Rate limiter:** trạng thái cấp phép/tokens, cần phối hợp atomic.

Điều quan trọng là **đừng nhét state vào một service xử lý thuần túy chỉ vì muốn tái sử dụng object**. Nếu state thật sự cần tồn tại, hãy để nó thuộc một component có responsibility và synchronization policy rõ ràng.

Ví dụ đơn giản:

~~~java
import java.util.concurrent.atomic.AtomicLong;

final class RequestMetrics {
    private final AtomicLong handled = new AtomicLong();

    void recordHandled() {
        handled.incrementAndGet();
    }

    long handledSoFar() {
        return handled.get();
    }
}
~~~

\`RequestMetrics\` là một **stateful, thread-safe counter** cho thao tác tăng/lấy một giá trị. Nó không trở thành stateless chỉ vì dùng \`AtomicLong\`. Nếu một nghiệp vụ cần nhất quán giữa metric này và nhiều state khác, cần thêm giao thức phù hợp; atomic update của một counter không làm tất cả thao tác bên ngoài atomic.

## 15. Checklist review code theo hướng loại bỏ chia sẻ

Khi gặp một class được dùng đồng thời, kiểm tra theo thứ tự:

1. **Có mutable instance fields không?** Đặc biệt \`currentUser\`, \`lastResult\`, \`StringBuilder\`, \`ArrayList\`, \`HashMap\`, \`SimpleDateFormat\` hoặc bộ đệm nội bộ. Với Java date/time hiện đại, ưu tiên immutable API như \`DateTimeFormatter\`.
2. **Có static mutable fields không?** Một class “không field instance” vẫn có thể chia sẻ state qua static.
3. **Method có thực sự dùng input và local không?** Dữ liệu per-call có được trả về thay vì đưa vào shared field?
4. **Input có tham chiếu tới object mutable dùng chung không?** Local parameter không bảo đảm object là riêng. Cần quy ước owner/copy/immutable.
5. **Dependency được gọi có thread-safe không?** Một service không đổi state vẫn có thể gọi helper mutable.
6. **Có nhiều bước phụ thuộc nhau không?** Chuỗi set rồi get, check rồi act, read rồi write cần một invariant cấp operation.
7. **Kết quả của các task được gom ở đâu?** Ưu tiên return/Future/reduction; tránh lastResult trên shared instance.
8. **Object có được publish an toàn không?** Constructor hoàn tất, state immutable không bị sửa sau publish.
9. **ThreadLocal có được dọn không?** Nếu cần ThreadLocal, xác định rõ owner, thời điểm set/remove và nguy cơ giữ dữ liệu qua worker reuse.
10. **Có resource bên ngoài dùng chung không?** File, connection, cache, hệ thống dữ liệu có state và contract riêng.
11. **Đã kiểm tra tính đúng trước benchmark chưa?** Việc thêm synchronized có thể làm lỗi biến mất, nhưng stateless refactor thường còn loại bỏ cả temporal coupling khó hiểu.
12. **Đã mô tả rõ giới hạn concurrency của API chưa?** Stateless không tự giới hạn số task, memory, queue, connection hay CPU.

## 16. Bài tập tự kiểm tra

**Câu 1.** Một object có field \`private final BigDecimal rate\` được set từ constructor và không thay đổi, method \`calculate(x)\` chỉ dùng local. Có thể gọi chung từ nhiều thread không?

**Đáp án:** Có, nếu calculator được khởi tạo và publish an toàn, BigDecimal immutable, method không sửa shared state và không dùng dependency không an toàn. Đây là service **không giữ mutable per-call state** dù có immutable configuration.

**Câu 2.** Method không có field nhưng nhận \`List<String> input\` và gọi \`input.sort(...)\`. Nó có tự động thread-safe không?

**Đáp án:** Không. Nếu nhiều thread đưa cùng mutable list vào thì method có thể thay đổi shared input đồng thời. Cần ownership/copy hoặc đồng bộ phù hợp.

**Câu 3.** Hai method \`synchronized setUser()\` và \`synchronized getGreeting()\` trên cùng instance. Caller A gọi set("A"), caller B gọi set("B"), rồi A gọi get(). Có thể trả B không?

**Đáp án:** Có. Mỗi method atomic tương đối với monitor, nhưng lock đã nhả giữa hai method. Chuỗi set+get không atomic.

**Câu 4.** Một service có \`private final StringBuilder builder\`, mỗi method gọi setLength(0) rồi append, rồi toString. Đây có phải stateless không?

**Đáp án:** Không. Builder là mutable shared field. Đưa StringBuilder vào biến local trong method hoặc thiết kế ownership phù hợp.

**Câu 5.** Một \`ThreadLocal<UserContext>\` dùng trong worker pool có biến service thành stateless không?

**Đáp án:** Không. Nó vẫn lưu state theo thread, có thể tồn tại qua nhiều task của cùng worker và cần cleanup đúng cách.

**Câu 6.** Khi hai task cần cộng kết quả, cách nào giảm shared state: cùng tăng field \`sum\` không đồng bộ, hay mỗi task trả giá trị và caller tổng hợp sau \`Future.get()\`?

**Đáp án:** Mỗi task trả giá trị và caller tổng hợp sau get() thường đơn giản và tránh race trên field sum. Cần xử lý exception, hủy, overflow và số lượng task theo yêu cầu thực tế.

## 17. Tài liệu đối chiếu

- **Java Language Specification §17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- **ExecutorService:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Future:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **CountDownLatch:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **AtomicLong:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- **ConcurrentHashMap:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- **ThreadLocal:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html

**Điểm cần nhớ:** Giải pháp đơn giản nhất cho nhiều race condition là **không chia sẻ mutable state nếu không cần**. Đưa dữ liệu tác vụ vào tham số/local/result và giữ immutable configuration giúp một instance phục vụ nhiều thread an toàn hơn, giảm lock và giảm việc phải suy luận về interleaving. Nếu state chung là một phần thật sự của nghiệp vụ, hãy nêu rõ owner, invariant và cơ chế đồng bộ để bảo vệ nó.
