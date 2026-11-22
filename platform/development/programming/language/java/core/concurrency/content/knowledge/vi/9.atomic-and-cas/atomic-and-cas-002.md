# AtomicReference và cập nhật object state trong Java Concurrency

## 1. Mục tiêu: cập nhật trạng thái của cả đối tượng bằng một điểm nguyên tử

Trong Java, một nghiệp vụ có thể phải cập nhật **nhiều trường liên quan** cùng lúc. Ví dụ, đặt chỗ cần giảm `available` và tăng `reserved` sao cho bất biến `available + reserved = total` luôn đúng. Nếu hai thread đọc rồi ghi từng trường riêng lẻ, chúng có thể làm mất cập nhật hoặc để lộ trạng thái dở dang.

`AtomicReference<V>` giữ **một tham chiếu đối tượng** có thể đọc, ghi hoặc thay thế nguyên tử. Khi kết hợp với **object state bất biến** và thao tác **compare-and-set (CAS)**, ta có thể biến việc thay đổi nhiều giá trị thành **một lần thay tham chiếu tới snapshot mới**. Reader lấy một tham chiếu sẽ quan sát một phiên bản trạng thái nhất quán.

Mục tiêu của bài:

- Hiểu `AtomicReference<V>` thực sự bảo vệ **tham chiếu** nào, và vì sao nó không tự biến đối tượng mutable được trỏ tới thành thread-safe.
- Phân biệt `get()`, `set()`, `getAndSet()`, `compareAndSet(expected, update)`, `getAndUpdate()`, `updateAndGet()` và các phương thức tích lũy.
- Giải thích CAS loop, reference identity (`==`), retry khi tranh chấp và điểm tuyến tính hóa (**linearization point**) của lần cập nhật thành công.
- Biết khi nào sử dụng immutable record/immutable class, vì sao phải coi update function là **side-effect-free**, và cách giữ invariant nhiều trường.
- Tái hiện hai thread cạnh tranh một snapshot, chứng minh một CAS thất bại được thử lại thay vì làm mất cập nhật.
- Nhận diện ABA, snapshot cũ, mutable nested objects, side effects bên ngoài, starvation/contention và giới hạn giao dịch nhiều tài nguyên.
- Lựa chọn giữa `AtomicReference`, `AtomicInteger`/`AtomicLong`, `LongAdder`, `synchronized` và `Lock` theo bài toán.

**Phạm vi:** Java SE/JVM concurrency. Ví dụ dùng **Java 17+**, phù hợp với record và `java.util.concurrent.atomic`. Không dùng framework.

## 2. AtomicReference bảo đảm gì?

Khai báo:

~~~java
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> state = new AtomicReference<>("NEW");
String observed = state.get();
state.set("READY");
~~~

Đối tượng `AtomicReference` chứa một ô tham chiếu; trong ví dụ, ô tham chiếu ban đầu trỏ tới `"NEW"`, rồi được thay bằng tham chiếu tới `"READY"`. Trong Java Memory Model, `get()` có ngữ nghĩa đọc volatile; `set()` có ngữ nghĩa ghi volatile. CAS có tính nguyên tử với memory effects theo `VarHandle.compareAndSet`.

Ta có thể hình dung:

~~~text
           AtomicReference<State>
           ┌─────────────────────┐
           │ current ────────────┼────────► State v1 (immutable)
           └─────────────────────┘            available=5
                                              reserved=0

Một thread tạo State v2 hoàn chỉnh (3,2) rồi CAS thành công:

           AtomicReference<State>
           ┌─────────────────────┐
           │ current ────────────┼────────► State v2 (immutable)
           └─────────────────────┘            available=3
                                              reserved=2

Reader đã giữ v1 tiếp tục thấy v1; reader mới có thể lấy v2.
Không có thời điểm reader thấy một nửa v1 cộng một nửa v2
nếu nó đọc một snapshot và snapshot thật sự immutable.
~~~

**Giới hạn cốt lõi:** AtomicReference chỉ bảo vệ việc **đọc/thay thế tham chiếu**, không tự khóa object hoặc mọi field bên trong. Ví dụ sau vẫn có data race:

~~~java
class MutableState {
    int count;
}

AtomicReference<MutableState> ref =
        new AtomicReference<>(new MutableState());

// Hai thread cùng gọi:
ref.get().count++; // KHÔNG atomic, có thể lost update
~~~

`ref.get()` trả về tham chiếu theo ngữ nghĩa atomic/volatile, nhưng `count++` thay đổi **cùng object mutable** mà không được bảo vệ. Không có CAS nào trên tham chiếu ở biểu thức này. Dùng `AtomicReference` quanh một object mutable **không phải** là phép biến đổi tự động sang thread-safe.

## 3. Từ các field cập nhật rời rạc đến immutable snapshot

Xét trạng thái tồn kho có hai field:

~~~java
int available = 5;
int reserved = 0;
~~~

Mọi thao tác `reserve(2)` hợp lệ phải giảm available và tăng reserved, giữ bất biến tổng bằng 5. Nếu cập nhật hai field rời rạc:

~~~java
available -= 2;
reserved += 2;
~~~

một reader có thể đi vào giữa và thấy available đã giảm còn reserved chưa tăng. Nếu có nhiều writer, cả hai còn có thể đọc cùng giá trị cũ và ghi đè nhau.

Giải pháp: dùng một immutable record chứa **toàn bộ trạng thái cần nhất quán**:

~~~java
record Stock(int available, int reserved) {
    Stock {
        if (available < 0 || reserved < 0) {
            throw new IllegalArgumentException("negative stock");
        }
    }
}
~~~

Sau khi tạo, record không có setter cho `available` hoặc `reserved`; cả hai là thành phần primitive và không có mutable nested references. Một cập nhật tạo **record mới**, sau đó CAS thay tham chiếu:

~~~java
AtomicReference<Stock> stock =
        new AtomicReference<>(new Stock(5, 0));

Stock before = stock.get();
Stock after = new Stock(before.available() - 2,
                        before.reserved() + 2);

boolean ok = stock.compareAndSet(before, after);
~~~

Nếu `ok == true` thì update toàn cặp đã công bố nguyên tử. Nếu `ok == false`, trạng thái có thể đã đổi bởi thread khác: không được mặc định cập nhật thành công, mà phải **đọc lại và tính lại** dựa trên phiên bản mới.

Để giữ bất biến nhiều trường, logic tạo trạng thái mới phải bảo vệ các điều kiện trước khi CAS. Chẳng hạn, không tạo Stock âm khi available không đủ. Constructor bất biến còn là một lớp phòng thủ bổ sung, nhưng không thay cho việc kiểm tra điều kiện nghiệp vụ và cập nhật trên snapshot mới nhất.

## 4. compareAndSet(expected, update): so sánh danh tính tham chiếu

Phương thức quan trọng nhất:

~~~java
boolean updated = ref.compareAndSet(expected, replacement);
~~~

Quy tắc của `AtomicReference.compareAndSet`:

1. Lấy tham chiếu hiện tại của atomic reference.
2. Nếu tham chiếu hiện tại **chính là đối tượng** `expected` theo phép `==`, thay bằng `replacement` trong một thao tác atomic và trả `true`.
3. Nếu tham chiếu hiện tại **không phải cùng đối tượng**, giữ nguyên reference và trả `false`.
4. Tính đúng của thao tác được bảo đảm theo memory semantics của API, không cần thêm `synchronized` chỉ để bảo vệ chính lần CAS đó.

**CAS so sánh identity, không gọi `equals()` để so giá trị nội dung.** Với record, `equals()` có thể coi hai record có field giống nhau là bằng nhau, nhưng `compareAndSet` vẫn coi chúng là **hai references khác nhau**.

Ví dụ:

~~~java
AtomicReference<String> text =
        new AtomicReference<>(new String("READY"));

String equalButDifferent = new String("READY");
System.out.println(text.get().equals(equalButDifferent)); // true
System.out.println(text.compareAndSet(equalButDifferent, "DONE")); // false
~~~

Đây là đoạn trích Java nằm trong một method, không phải chương trình `main` độc lập. Hai chuỗi được tạo bằng `new String(...)` có nội dung bằng nhau nhưng khác tham chiếu. Việc dùng `String` để minh họa CAS không có nghĩa mọi phép so sánh chuỗi trong nghiệp vụ nên dùng `==`; giá trị chuỗi thông thường vẫn cần `equals()`.

### Linearization point

Một CAS thành công là một điểm trong trình tự đồng thời mà ta có thể xem toàn bộ phép thay reference diễn ra **tại một thời điểm logic**. Các thread tranh cùng atomic reference có thể thấy phiên bản trước hoặc phiên bản sau, nhưng không thấy một phần của lần thay thế reference.

Với snapshot bất biến, điểm CAS thành công chính là điểm **publish** phiên bản mới. Nếu state chứa hai trường được tạo nhất quán từ trước, việc publish chỉ một reference giúp reader không cần khóa để lấy một **phiên bản đầy đủ**.

### Tại sao không dùng get() rồi set()?

~~~java
State old = current.get();
State updated = transform(old);
current.set(updated); // nguy cơ ghi đè bản cập nhật từ thread khác
~~~

`get()` và `set()` đều là atomic accesses **riêng lẻ**. Nếu thread A và B đều đọc cùng `old`, cả hai có thể tính phiên bản mới và gọi set; lần set sau có thể ghi đè update hợp lệ của thread trước. Đây là **lost update** tại mức object state.

`getAndSet(newState)` cũng chỉ **thay thế vô điều kiện** và trả về reference cũ; nó không phù hợp nếu bản mới được tính từ snapshot cũ mà phải giữ toàn bộ cập nhật cạnh tranh. Để bảo vệ read–modify–write, dùng CAS loop hoặc `updateAndGet` với update function thuần.

## 5. CAS loop đúng: đọc, tính, thử thay, thất bại thì thử lại

Mẫu cơ bản:

~~~java
while (true) {
    State before = state.get();       // một snapshot hiện tại
    State after = transform(before);  // tạo phiên bản mới
    if (state.compareAndSet(before, after)) {
        return;                       // cập nhật đã thành công
    }
    // Một thread khác thay state: đọc lại và tính lại.
}
~~~

Ở đây `State` và `transform` là các kiểu/hàm của ứng dụng; đoạn này mô tả thuật toán nằm trong một method, **không phải chương trình chạy độc lập**.

Một chu trình CAS cần chú ý:

- `transform(before)` phải tạo một trạng thái hợp lệ dựa trên **snapshot before**.
- Nếu có **điều kiện thất bại nghiệp vụ** (hết hàng, không đủ quota), kiểm tra điều kiện trên **mỗi snapshot được đọc lại**, không chỉ lần đầu.
- CAS false không phải exception; đó là kết quả cạnh tranh bình thường. Không được trả thành công khi CAS false.
- Dưới contention, một thread có thể phải thử nhiều lần. AtomicReference không hứa mỗi caller đều hoàn thành sau số vòng lặp hữu hạn; **lock-free ở cấp thuật toán** không đồng nghĩa **wait-free cho từng thread**.
- Update function không nên thực hiện I/O, gửi event, ghi file, tăng metric phụ hay thay đổi state có thể quan sát. Nếu CAS thất bại, hàm có thể được gọi thêm lần nữa.
- Nếu thao tác có thể tạo exception (validation, `Math.addExact`), exception nên xảy ra **trước khi CAS** và không để lại cập nhật bất toàn vào shared state.
- Một CAS thành công chỉ bảo vệ trạng thái bên trong atomic reference này. Nếu vừa thay state vừa cập nhật một database/queue khác, hai hành động **không tự biến thành một transaction**.

## 6. Ví dụ độc lập 1: hai thread cùng cập nhật một snapshot, không mất update

Để tái hiện chính xác tranh chấp, chương trình cho hai thread **cùng đọc phiên bản đầu** rồi mới cho chúng thử CAS. Một thread thắng CAS lần đầu; thread còn lại phải thất bại **đúng một lần**, đọc lại, tính phiên bản mới rồi thành công. Kết quả được xác định bằng latch, không phụ thuộc khoảng ngủ.

Lưu tệp **AtomicReferenceCasDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceCasDemo {
    record State(int count, int revision) {}

    private static final AtomicReference<State> state =
            new AtomicReference<>(new State(0, 0));
    private static final AtomicInteger failedCas = new AtomicInteger();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch beginCas = new CountDownLatch(1);

        Runnable increment = () -> {
            State before = state.get();
            bothRead.countDown();

            try {
                beginCas.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            while (true) {
                State after =
                        new State(before.count() + 1, before.revision() + 1);
                if (state.compareAndSet(before, after)) {
                    return;
                }
                failedCas.incrementAndGet();
                before = state.get();
            }
        };

        Thread a = new Thread(increment, "cas-a");
        Thread b = new Thread(increment, "cas-b");
        a.start();
        b.start();

        bothRead.await();
        beginCas.countDown();
        a.join();
        b.join();

        State result = state.get();
        System.out.println("count=" + result.count());
        System.out.println("revision=" + result.revision());
        System.out.println("failedCAS=" + failedCas.get());
    }
}
~~~

Biên dịch, chạy trên JDK 17+:

~~~bash
javac AtomicReferenceCasDemo.java
java AtomicReferenceCasDemo
~~~

Output khi không có yêu cầu interrupt bên ngoài:

~~~text
count=2
revision=2
failedCAS=1
~~~

**Giải thích tính xác định:**

1. `bothRead` đảm bảo cả A và B đã lấy cùng reference `State(0,0)` ban đầu trước khi `beginCas` được mở.
2. Cả hai tạo `State(1,1)` riêng và thử thay **cùng expected object ban đầu**.
3. Chỉ **một** CAS có thể thay reference ban đầu thành phiên bản mới. CAS của thread còn lại trả false, tăng `failedCas` đúng một lần.
4. Thread thua đọc phiên bản `State(1,1)` vừa publish, tạo `State(2,2)` và CAS thành công; không còn contender khác đang cập nhật.
5. `join()` chờ cả hai thread kết thúc; các thao tác trước khi worker kết thúc được quan sát đúng bởi main sau join. Kết quả cuối là hai lần tăng, không bị lost update.
6. Đây là ví dụ CAS **đúng ở cấp logic**. Nó không chứng minh ứng dụng nên có retry vô hạn trong mọi workload và không phải benchmark tốc độ.

Quan sát: Nếu thay vòng CAS bằng `state.set(after)`, cả A và B đều có thể ghi `State(1,1)` và làm mất một lần tăng. Bản chất của bài là liên kết phiên bản đã đọc với quyền thay thế **chỉ khi phiên bản đó còn là hiện hành**.

## 7. Ví dụ độc lập 2: cập nhật nhiều field của object state

Bài toán: giữ bất biến `available + reserved = initialStock` trong **một JVM**. Mỗi thao tác đặt chỗ cần kiểm tra đủ hàng rồi chuyển số lượng từ available sang reserved. Nếu nhiều thread đến đồng thời, CAS phải bảo vệ trọn **check + update**.

Lưu tệp **AtomicInventoryDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicInventoryDemo {
    record Stock(int available, int reserved) {
        Stock {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("negative stock");
            }
        }
    }

    private final AtomicReference<Stock> current;

    public AtomicInventoryDemo(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial stock");
        }
        current = new AtomicReference<>(new Stock(initial, 0));
    }

    public boolean reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        while (true) {
            Stock before = current.get();
            if (before.available() < amount) {
                return false;
            }

            Stock after = new Stock(
                    before.available() - amount,
                    Math.addExact(before.reserved(), amount));

            if (current.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    public Stock snapshot() {
        return current.get();
    }

    public static void main(String[] args) {
        AtomicInventoryDemo inventory = new AtomicInventoryDemo(5);

        System.out.println("reserve2=" + inventory.reserve(2));
        System.out.println("reserve4=" + inventory.reserve(4));
        System.out.println("reserve1=" + inventory.reserve(1));

        Stock result = inventory.snapshot();
        System.out.println("available=" + result.available());
        System.out.println("reserved=" + result.reserved());
        System.out.println("total=" +
                (result.available() + result.reserved()));
    }
}
~~~

Chạy:

~~~bash
javac AtomicInventoryDemo.java
java AtomicInventoryDemo
~~~

Output:

~~~text
reserve2=true
reserve4=false
reserve1=true
available=2
reserved=3
total=5
~~~

**Tại sao thread-safe cho thao tác reserve trên cùng instance?**

- `Stock` record chỉ có hai thành phần primitive, nên mỗi phiên bản thực sự immutable.
- `reserve` đọc **một snapshot**, kiểm tra điều kiện đủ hàng và tạo snapshot mới với tổng không đổi.
- Nếu thread khác đã thay current trước CAS, phép thử false và vòng lặp **đọc lại**; không đặt chỗ dựa trên một snapshot đã lỗi thời.
- CAS thành công publish **cả available và reserved** trong một lần thay tham chiếu; reader dùng một `Stock` local thấy cùng phiên bản của cả hai trường.
- `snapshot()` lấy một reference nhất quán tại thời điểm đọc, nhưng **không khóa các cập nhật tương lai**. Nếu caller đọc `snapshot()` nhiều lần, mỗi lần có thể thấy phiên bản khác.
- `Math.addExact` giúp phát hiện overflow khi cộng reserved; ở trạng thái hợp lệ bình thường với kho nhỏ, nó không phát sinh lỗi.
- Ví dụ main gọi tuần tự để stdout xác định. Cùng mã `reserve` có thể được gọi đồng thời bởi nhiều thread; đảm bảo invariant chỉ áp dụng nếu **mọi** thay đổi Stock đều đi qua giao thức đúng của instance đó.

**Ranh giới quan trọng:** `AtomicReference` ở đây không phải transaction giữa nhiều process, database hoặc dịch vụ khác. Nó không quản lý reservation timeout, idempotency hay giao dịch bên ngoài. Đó là các yêu cầu nghiệp vụ riêng.

## 8. Các convenience methods để cập nhật dựa trên trạng thái cũ

`AtomicReference` có các API phổ biến:

| API | Ý nghĩa | Giá trị trả về |
|---|---|---|
| `get()` | Đọc reference hiện tại với volatile read semantics | Reference hiện tại |
| `set(next)` | Ghi reference mới với volatile write semantics | `void` |
| `lazySet(next)` | Ghi reference mới với release semantics | `void` |
| `getAndSet(next)` | Thay vô điều kiện một cách atomic | Reference trước khi thay |
| `compareAndSet(expect, next)` | Thay nếu reference hiện tại `== expect` | `boolean` thành công/thất bại |
| `compareAndExchange(expect, next)` | Thay nếu reference hiện tại `== expect` | Reference thực tế quan sát tại phép thử (witness) |
| `updateAndGet(fn)` | Tính từ state hiện tại và cập nhật nguyên tử | Reference **mới** sau cập nhật |
| `getAndUpdate(fn)` | Tính từ state hiện tại và cập nhật nguyên tử | Reference **cũ** trước cập nhật |
| `accumulateAndGet(x, fn)` | Kết hợp current và `x` bằng hàm hai đối số | Reference **mới** sau cập nhật |
| `getAndAccumulate(x, fn)` | Tương tự nhưng trả phiên bản trước | Reference **cũ** |

Các phương thức dựa trên function dùng cơ chế nguyên tử; trong quá trình cạnh tranh, **function có thể được gọi lặp lại**. Do đó tránh side effects trong hàm và không giả định function chỉ chạy một lần trên mỗi lời gọi API.

Ví dụ với record bất biến:

~~~java
record Versioned(String text, int revision) {}

AtomicReference<Versioned> ref =
        new AtomicReference<>(new Versioned("draft", 0));

Versioned old = ref.getAndUpdate(s ->
        new Versioned(s.text(), s.revision() + 1));

Versioned current = ref.updateAndGet(s ->
        new Versioned("published", s.revision() + 1));
~~~

Đây là đoạn trích bên trong một method. Khi chỉ một thread chạy các dòng này, `old` là `Versioned("draft", 0)` và `current` là `Versioned("published", 2)`. Điểm khác nhau là **giá trị trả về** của `getAndUpdate` và `updateAndGet`. Với concurrency, kết quả và thời điểm của mỗi phiên bản tuân theo thứ tự các cập nhật thành công, không thể suy từ thứ tự câu lệnh giữa các thread khác nhau.

### Khi dùng `set` hoặc `getAndSet` hợp lý?

`set(next)` phù hợp khi caller chủ ý **publish một trạng thái hoàn toàn mới không cần giữ update cạnh tranh**, chẳng hạn cập nhật một immutable configuration snapshot có chính sách “bản mới nhất thay thế bản cũ”. `getAndSet(next)` hữu ích nếu cần đồng thời **thay và thu lại reference cũ**. Nhưng nếu `next` được suy ra từ current state và không được phép mất update khác, hãy dùng CAS hoặc hàm cập nhật nguyên tử.

## 9. Ví dụ độc lập 3: API updateAndGet và getAndUpdate

Lưu tệp **AtomicReferenceUpdateDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceUpdateDemo {
    record Config(String mode, int revision) {}

    public static void main(String[] args) {
        AtomicReference<Config> ref =
                new AtomicReference<>(new Config("draft", 0));

        Config before = ref.getAndUpdate(s ->
                new Config(s.mode(), s.revision() + 1));

        Config after = ref.updateAndGet(s ->
                new Config("published", s.revision() + 1));

        System.out.println("old=" + before.mode()
                + "/" + before.revision());
        System.out.println("new=" + after.mode()
                + "/" + after.revision());
        System.out.println("current=" + ref.get().revision());
    }
}
~~~

Chạy:

~~~bash
javac AtomicReferenceUpdateDemo.java
java AtomicReferenceUpdateDemo
~~~

Output trong trình tự đơn thread này:

~~~text
old=draft/0
new=published/2
current=2
~~~

Dùng các update methods giúp viết ngắn gọn, nhưng **không thay đổi quy tắc purity** của hàm chuyển trạng thái. Trong ứng dụng có contention, lambda có thể được chạy lại và tạo nhiều object ứng viên; chỉ một cập nhật tại mỗi lần gọi thành công được publish.

## 10. Vì sao lambda cập nhật phải side-effect-free?

Ví dụ **sai**:

~~~java
ref.updateAndGet(old -> {
    sendEmail("State is changing"); // SAI: side effect có thể lặp
    return new State(old.value() + 1);
});
~~~

Đoạn code là minh họa trong một method có `ref` và các kiểu/phương thức do ứng dụng định nghĩa. Giả sử thread A tính candidate từ version 1, nhưng thread B publish version 2 trước khi A CAS. A phải **thử lại** lambda với version 2. `sendEmail` có thể đã chạy lần đầu **dù candidate của lần đó không được publish**, sau đó chạy tiếp lần thứ hai. Kết quả là gửi dư sự kiện hoặc gây effect không khớp state.

Giải pháp nguyên tắc:

1. Lambda chỉ tính toán và trả về **candidate immutable state**, không I/O và không mutation bên ngoài.
2. Sau khi CAS thành công, caller có thể thực hiện side effect **một lần theo nhánh success**.
3. Nếu yêu cầu **atomically** gắn side effect với state transition (ví dụ cập nhật DB và gửi thông báo bắt buộc đúng một lần), AtomicReference **không đủ**: cần một giao thức ở tầng sở hữu tài nguyên (transaction/outbox/idempotency hoặc cơ chế tương đương), không tự giả định bước “CAS xong rồi gửi” là atomic với hai hệ thống.

Ngay cả side effect sau CAS vẫn có thể thất bại: cập nhật memory thành công, nhưng gửi thông báo thất bại. Phải xác định yêu cầu bền vững, retry và idempotency riêng.

### Exception trong hàm cập nhật

Nếu update function ném exception **trước CAS** thì lời gọi cập nhật đó thất bại và không publish candidate của lần thử đang xét. Tuy nhiên, nếu function đã có side effect trước khi ném, side effect đó **không tự rollback**. Vì thế purity giúp cả correctness và khả năng khôi phục lỗi.

## 11. Snapshot reference, tính bất biến và cấu trúc lồng nhau

Một snapshot immutable phải thật sự bất biến trong phạm vi dữ liệu mà reader dựa vào.

**Không an toàn nếu chỉ record ở tầng ngoài:**

~~~java
import java.util.List;

record Settings(List<String> features) {}

List<String> mutable = new java.util.ArrayList<>();
mutable.add("search");

AtomicReference<Settings> ref =
        new AtomicReference<>(new Settings(mutable));

// Thread khác vẫn có thể:
mutable.add("billing");
~~~

Record không cho thay reference `features` nhưng bản thân `List` bên trong vẫn mutable và bị caller giữ tham chiếu. Một reader nhận `Settings` qua AtomicReference có thể thấy List bị sửa đồng thời sau publication.

**Tạo defensive copy thích hợp:**

~~~java
import java.util.List;

record Settings(List<String> features) {
    Settings {
        features = List.copyOf(features);
    }
}
~~~

`List.copyOf` tạo danh sách unmodifiable ở cấp container. Nếu phần tử là **immutable String**, cách này giúp trạng thái phù hợp. Nếu phần tử là mutable object, `List.copyOf` không tự làm các phần tử thành immutable; cần copy sâu hơn hoặc thiết kế immutable element.

Bài học:
- Reference swap an toàn **không tự cô lập mutation trên object cũ**.
- Reader giữ một snapshot cũ vẫn có thể sử dụng nó sau khi current trỏ sang snapshot mới; thiết kế cần bảo đảm snapshot cũ **không bị mutate**.
- Nếu muốn cập nhật Map/List phức tạp, thường tạo một immutable copy mới rồi CAS publish thay vì sửa Map/List cũ tại chỗ.
- Copy-on-write phù hợp khi **đọc nhiều, cập nhật ít**; nếu trạng thái lớn và update liên tục, copy có thể tốn CPU/heap/GC.

## 12. Multi-field invariant: atomicity của snapshot không mở rộng sang tài nguyên khác

Với một immutable `State(a,b,c)`, CAS thay reference làm ba field xuất hiện cùng nhau trong một phiên bản. Nhưng cần phân biệt:

| Phạm vi | Có thể bảo đảm bằng AtomicReference? | Lưu ý |
|---|---|---|
| Thay một tham chiếu từ old sang new | **Có** | CAS cung cấp điểm atomic. |
| Giữ invariant của các field trong **cùng immutable state** | **Có nếu transform đúng** | Mỗi candidate phải hợp lệ và tất cả writers dùng protocol. |
| Thay cùng lúc hai AtomicReferences khác nhau | **Không tự động** | Hai CAS riêng có thể bị reader chen giữa. |
| Mutation trong object mutable đã publish | **Không** | Cần cơ chế riêng hoặc immutable design. |
| Ghi file, database, network cùng một lúc với CAS | **Không** | Ngoài phạm vi atomic reference của JVM. |
| Đảm bảo writer riêng lẻ không bị starvation | **Không** | CAS loop có thể retry liên tục dưới contention. |
| Bảo đảm trạng thái bền vững sau process crash | **Không** | AtomicReference nằm trong memory của tiến trình. |

Nếu một invariant trải qua nhiều objects mà không thể gộp vào một immutable snapshot, `synchronized`/`Lock` có thể dễ hiểu hơn; với nhiều tiến trình hay storage ngoài, cần hệ thống transaction/consistency tại nguồn dữ liệu.

## 13. ABA: reference đã đổi A → B → A mà CAS không phát hiện

CAS trả true nếu **reference hiện tại `== expected`**. Nó không trả lời câu hỏi “giữa lúc tôi đọc và lúc tôi cập nhật, object này **đã từng thay đổi** hay chưa?”.

Ví dụ:

~~~text
T1 đọc expected = tham chiếu A
T2 CAS A -> B             (state đổi)
T2 CAS B -> A             (trỏ lại đúng object A cũ)
T1 CAS expected A -> C    (thành công vì current == A)
~~~

T1 không phát hiện chu trình A→B→A, dù các hành động ở giữa có thể ảnh hưởng logic của cấu trúc dữ liệu. Đây là **ABA problem**, đặc biệt cần chú ý trong các cấu trúc lock-free quản lý node, stack, freelist hoặc vòng đời object.

**Không đồng nhất ABA với hai object bằng `equals()`:** nếu T2 thay A bằng một object A2 có cùng nội dung nhưng **reference khác**, T1 đang giữ A sẽ CAS thất bại. ABA nguy hiểm khi current trở lại **chính reference A cũ**.

### Giải pháp khi cần biết lịch sử thay đổi

`AtomicStampedReference<V>` giữ **cặp (reference, integer stamp)** và cho phép CAS cả reference lẫn stamp:

~~~java
import java.util.concurrent.atomic.AtomicStampedReference;

AtomicStampedReference<String> stamped =
        new AtomicStampedReference<>("A", 0);

int[] holder = new int[1];
String current = stamped.get(holder);  // đọc cặp nhất quán
int version = holder[0];

boolean changed =
        stamped.compareAndSet(current, "B", version, version + 1);
~~~

Đây là đoạn trích dùng trong một method. `get(holder)` trả reference và điền stamp tương ứng vào `holder[0]`. `compareAndSet` chỉ thành công khi **cả reference và stamp** khớp expected. Tăng stamp trên mỗi transition có thể giúp phát hiện A→B→A ngay cả khi reference quay lại A. Tuy nhiên integer stamp có phạm vi hữu hạn, có thể overflow/quay vòng; cần đánh giá khả năng wraparound trong workload dài.

`AtomicMarkableReference<V>` lưu (reference, boolean mark), phù hợp một số thuật toán cần đánh dấu, nhưng boolean mark không thay thế được version counter tổng quát.

**Khi nào không cần quá lo ABA?** Trong mẫu immutable state mà **mỗi lần cập nhật tạo một object mới và không bao giờ publish lại object cũ**, cùng identity cũ khó xuất hiện trở lại theo giao thức đó. Dù vậy không suy từ đó rằng mọi thuật toán CAS đều miễn ABA: hãy xét cụ thể việc tái sử dụng reference và invariant của cấu trúc.

## 14. Cập nhật object state và Java Memory Model

Các bảo đảm đồng bộ không phải là “ngẫu nhiên nhờ CPU cache”. Java API quy định memory effects:

- `AtomicReference.get()` có semantics của volatile read.
- `AtomicReference.set(...)` có semantics của volatile write.
- `compareAndSet(...)` có memory effects theo `VarHandle.compareAndSet` và thực hiện phép cập nhật reference atomically.
- Khi writer khởi tạo candidate object **trước** khi publish thành công, reader đọc reference đã publish phù hợp có thể quan sát các ghi khởi tạo trước đó theo happens-before.
- Final fields trong immutable object còn có các quy tắc khởi tạo riêng của JMM; nhưng không nên dựa vào final để cho phép mutable nested objects bị thay đổi tùy ý sau publish.

Một mô hình hữu ích:

~~~text
Writer:    new State(fields hoàn chỉnh)
                  │
                  ▼
           CAS current old → new (publish)
                  │
            đồng bộ phù hợp
                  │
                  ▼
Reader:    State snapshot = current.get()
                  │
                  ▼
           đọc fields từ đúng snapshot
~~~

Reader **không cần khóa** để đọc các trường của một immutable state đã publish an toàn. Tuy nhiên, reader có thể quan sát **phiên bản cũ hoặc mới** tùy thứ tự tương tác; nó không được đảm bảo luôn thấy bản cập nhật tương lai trước khi bản đó tồn tại.

Nếu reader gọi `current.get()` hai lần và đọc field A từ phiên bản đầu, field B từ phiên bản sau, nó có thể tự tạo snapshot trộn. Giữ **một tham chiếu local**:

~~~java
State snapshot = current.get();
int a = snapshot.a();
int b = snapshot.b();
~~~

Đoạn minh họa này giả định State có accessor a()/b(). Cả hai field được đọc từ **cùng một immutable object**. Điều này khác với “khóa mọi update” và vẫn cho writer hoạt động đồng thời.

## 15. CAS thất bại, retry và chi phí hiệu năng

AtomicReference thường rất hữu ích khi state thay đổi tương đối ít hoặc phép biến đổi nhanh; nhưng **mỗi CAS thất bại** có thể làm lãng phí công tính toán và object ứng viên vừa được tạo.

Các nguồn chi phí:

1. **Contention:** nhiều writers cùng đọc một reference và tranh commit.
2. **Allocation:** mỗi lần thử có thể tạo immutable State object mới; candidate thất bại trở thành garbage.
3. **Retry:** transform có thể chạy lại nhiều lần, đặc biệt nếu dùng updateAndGet/functional methods.
4. **Cache coherence:** nhiều core tranh một vị trí cập nhật chung.
5. **Read/write balance:** copy immutable Map/Tree quá lớn cho mỗi update có thể tốn hơn một lock bảo vệ cấu trúc mutable.
6. **Fairness/starvation:** CAS lock-free không cam kết từng thread hoàn thành trong thời gian có giới hạn.
7. **Chính sách áp lực:** nếu mọi request retry không giới hạn khi hệ thống quá tải, CPU contention có thể tăng thay vì phục vụ tốt hơn.

**Không benchmark bằng một lần chạy.** Muốn so sánh `AtomicReference` với lock, cần cùng invariant, cùng workload, số writers/readers, thời gian transform, số field, tỷ lệ contention, cấu hình JDK/CPU và đo throughput, p95/p99 latency, allocation và GC. Trong một số trường hợp, `synchronized` hoặc `ReentrantLock` đơn giản hơn và có hiệu quả tốt hơn.

### Có cần backoff?

Với contention cao, đôi khi cân nhắc retry có giới hạn, backoff hoặc serializing updates qua một owner thread. Không có công thức backoff cố định phù hợp mọi workload. `Thread.onSpinWait()` chỉ là **hint** cho vòng spin ngắn, không biến CAS thành công hay tạo fairness; không gọi sleep/yield tùy tiện để “sửa” tính đúng. Nếu cần bảo đảm thời hạn hoặc hủy, thiết kế chính sách retry/cancellation riêng.

## 16. Chọn AtomicReference, atomic counter hay lock

| Tình huống | Lựa chọn thường hợp lý | Vì sao |
|---|---|---|
| Tăng một biến `int` hoặc `long` chính xác | `AtomicInteger`/`AtomicLong` | Increment/CAS chuyên biệt, không cần tạo object snapshot mỗi lần tăng. |
| Nhiều writers ghi nhận metric, reader chỉ lấy tổng quan sát | `LongAdder` | Giảm contention, nhưng `sum()` không phải snapshot atomically khi có writer. |
| Thay một immutable config snapshot | `AtomicReference<Config>` | Atomic publish một object mới, reader có snapshot nhất quán. |
| Check và cập nhật **nhiều field trong cùng immutable state** | `AtomicReference<State>` + CAS loop | Atomic reference swap bảo vệ invariant giữa các field. |
| Mutable graph lớn, transform phức tạp, contention cao | `synchronized`/`ReentrantLock` | Có thể dễ bảo trì hơn và tránh cấp phát/copy lại liên tục. |
| Một trạng thái phụ thuộc tài nguyên ngoài | Transaction/consistency protocol phù hợp | AtomicReference không bao trùm database, file, network. |
| Cần phân biệt A→B→A trên cùng reference | `AtomicStampedReference` hoặc thuật toán versioning phù hợp | Có version/stamp để phát hiện chu kỳ reference nếu không bị wraparound. |
| Chỉ cần publish một immutable value không phụ thuộc old | `volatile` field hoặc `AtomicReference.set` | Không cần CAS nếu không có read-modify-write cạnh tranh cần bảo vệ. |

### Khi lock đơn giản hơn

Nếu phép cập nhật cần làm việc dài, gọi API có side effect hoặc thao tác trên nhiều cấu trúc mutable khó copy, CAS loop buộc transform có thể chạy lặp; code dễ phức tạp. Một critical section có lock chung đôi khi diễn đạt đúng **trọn đơn vị nghiệp vụ** rõ hơn. Nhưng giữ lock qua I/O dài có thể tăng contention; thiết kế cần đánh giá ranh giới đồng bộ, không mặc định lock luôn tốt hơn hay CAS luôn nhanh hơn.

## 17. Các lỗi phổ biến khi code review

**Lỗi 1 — Coi AtomicReference<Mutable> là khóa.** `ref.get().field++` vẫn racy. Reference atomic không làm field update atomic.

**Lỗi 2 — Gọi get() rồi set(transform(old)).** Hai thao tác riêng có thể lost update. Cần CAS hoặc function update atomically nếu update phụ thuộc state hiện tại.

**Lỗi 3 — Dùng equals thay cho expected identity.** `compareAndSet` dựa trên `==` reference identity. Hai record có nội dung bằng nhau vẫn có thể là reference khác.

**Lỗi 4 — Sau CAS false vẫn trả true hoặc áp dụng candidate cũ.** Đọc lại current rồi tính lại toàn bộ điều kiện và snapshot.

**Lỗi 5 — Cập nhật nhiều trường bằng hai AtomicReferences độc lập.** Hai CAS riêng không phải một transaction. Nếu cần snapshot nhất quán, gói cả hai field vào một immutable State.

**Lỗi 6 — Record chứa List/Map mutable.** Record chỉ shallow immutable. Phải copy/tránh sửa nested state đang chia sẻ.

**Lỗi 7 — Gửi email hoặc tăng metric phụ bên trong updateAndGet lambda.** Function có thể được chạy nhiều lần khi CAS retry. Chỉ dùng hàm thuần, thực hiện side effect sau success nếu hợp đồng cho phép.

**Lỗi 8 — Đọc current hai lần rồi ghép field của hai phiên bản.** Giữ một `State snapshot = ref.get()` để đọc nhiều field nhất quán.

**Lỗi 9 — Nhầm reference identity với lịch sử version.** ABA có thể xảy ra nếu cùng reference được publish lại. Xét stamped/versioned protocol khi invariant cần biết mọi thay đổi trung gian.

**Lỗi 10 — Ghi object cũ sau khi đã publish mới.** Reader đang giữ object cũ có thể bị tác động. Dùng immutable snapshots và không mutate chúng sau publish.

**Lỗi 11 — CAS loop vô hạn trong mọi workload.** Dưới contention cao có thể starvation, CPU và allocation tăng. Đo tải, đặt deadline/retry budget khi yêu cầu nghiệp vụ cần.

**Lỗi 12 — Giữ lẫn Java in-memory CAS và database transaction.** AtomicReference chỉ có phạm vi trong một JVM process.

**Lỗi 13 — Bỏ qua overflow/validation.** Atomic snapshot vẫn có thể chứa dữ liệu nghiệp vụ sai nếu transform không giữ invariant. Dùng kiểm tra điều kiện và `Math.addExact` khi cần.

**Lỗi 14 — Thay state bằng set(null) và assume mọi reader đều không-null.** Constructor không tham số của AtomicReference khởi tạo null; nếu cho phép null, mọi đường đọc phải có contract xử lý hoặc validation rõ ràng.

## 18. Mẫu thiết kế thực tế

Một service giữ immutable runtime configuration với các thao tác:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class RuntimeSettings {
    public record Config(String endpoint, int retryLimit) {
        public Config {
            Objects.requireNonNull(endpoint);
            if (retryLimit < 0) {
                throw new IllegalArgumentException("negative retryLimit");
            }
        }
    }

    private final AtomicReference<Config> current =
            new AtomicReference<>(new Config("api-a", 2));

    public Config snapshot() {
        return current.get();
    }

    public Config updateRetryLimit(int newLimit) {
        if (newLimit < 0) {
            throw new IllegalArgumentException("negative newLimit");
        }
        return current.updateAndGet(
                old -> new Config(old.endpoint(), newLimit));
    }

    public void publish(Config replacement) {
        current.set(Objects.requireNonNull(replacement));
    }
}
~~~

Class Java 17+ này không có main; mục đích là chỉ ra **hai chính sách cập nhật khác nhau**:

- `publish(replacement)`: chủ ý thay **toàn bộ config** bằng snapshot từ caller, không cần giữ update khác. Nếu concurrent writers gọi publish, bản ghi cuối theo thứ tự thực tế sẽ thắng.
- `updateRetryLimit(newLimit)`: cập nhật **một thuộc tính dựa trên config mới nhất**; nếu writer khác thay endpoint trước CAS, function có thể được chạy lại và giữ endpoint mới thay vì ghi đè bằng một endpoint cũ.

**Giới hạn semantics:** Trong một cuộc đua giữa `publish` và `updateRetryLimit`, mỗi method có điểm atomic riêng. Caller không được giả định “lệnh được gọi trước” nhất thiết được commit trước giữa các thread khác nhau. Nếu có thứ tự nghiệp vụ bắt buộc hoặc quyền ưu tiên giữa hai loại cập nhật, cần chính sách version/locking rõ hơn.

### Tư duy về quyền sở hữu writer

Nếu ứng dụng chỉ có một config publisher và nhiều readers, `volatile Config` đơn giản đôi khi đủ. Khi có nhiều writers cần update dựa trên old state mà không làm mất nhau, AtomicReference/CAS phù hợp hơn. Không chọn CAS chỉ vì “thread-safe” nghe hấp dẫn; trước tiên xác định có **compound update/invariant** cần bảo vệ hay không.

## 19. Kiểm tra bằng stress test và công cụ

Cách kiểm tra đúng:

1. **Deterministic interleaving**: dùng `CountDownLatch` để ép hai writers đọc cùng snapshot, chứng minh CAS false và retry như ví dụ đầu.
2. **Stress test**: cho nhiều threads cập nhật một shared reference; chờ `join()` hoặc `Future.get()` rồi kiểm tra invariant và tổng lượng update, tránh đọc quá sớm.
3. **Snapshot consistency**: với state đa trường, kiểm tra mọi phiên bản đọc được đều tuân thủ invariant, không chỉ final state.
4. **Contention metrics**: đếm CAS failures/retries, allocation, CPU, độ trễ xử lý, tail latency và throughput.
5. **Exception/cancellation**: xem function ném lỗi giữa chừng có side effect không; khi ngừng task, còn writer nào update sau điểm kiểm tra không.
6. **Reference lifecycle**: có reuse object identity hoặc mutate old snapshots không; ABA hoặc memory retention có thể ảnh hưởng thuật toán.

Một lần stress test chạy đúng **không chứng minh** không có race trên mọi interleaving. Với thuật toán concurrency tinh vi, có thể nghiên cứu OpenJDK jcstress để thăm dò các kết quả quan sát được theo Java Memory Model. Không dùng thời gian `Thread.sleep()` làm bằng chứng tính đúng hoặc để “đồng bộ” các thread.

## 20. Bài tập tự kiểm tra

**Câu 1.** Vì sao `AtomicReference<MutableCounter> ref` với `ref.get().count++` không thread-safe?

**Đáp án:** AtomicReference chỉ bảo vệ việc lấy/thay **tham chiếu**. Phép tăng trên field của object mutable vẫn là read–modify–write không atomic và có thể lost update.

**Câu 2.** Hai records có `equals() == true` có thể làm `compareAndSet` trả false không?

**Đáp án:** Có. CAS so reference identity bằng `==`; hai records có field bằng nhau nhưng là instances khác nhau không phải cùng expected reference.

**Câu 3.** CAS false thì candidate đã tính có nên được publish bằng `set(candidate)` để “khỏi mất công” không?

**Đáp án:** Không nếu candidate phụ thuộc state cũ. `set` có thể ghi đè update của thread khác. Đọc lại snapshot và tính lại điều kiện, rồi CAS mới.

**Câu 4.** Tại sao updateAndGet lambda không được gửi email?

**Đáp án:** Khi tranh chấp, lambda có thể chạy lại trước khi CAS thành công; side effect có thể xảy ra nhiều lần hoặc xảy ra dù không commit candidate.

**Câu 5.** Với hai trường `balance` và `version`, dùng hai AtomicInteger riêng có đảm bảo reader luôn thấy cùng phiên bản không?

**Đáp án:** Không. Hai atomic updates độc lập không trở thành một transaction. Gói dữ liệu trong một immutable snapshot và thay reference nguyên tử hoặc dùng lock bảo vệ đọc/ghi theo invariant.

**Câu 6.** Reader gọi `ref.get()` một lần và giữ immutable State local trong khi writer CAS nhiều lần. Reader có thấy state “bị đổi giữa chừng” không?

**Đáp án:** Không nếu State thật sự immutable. Reader giữ một object snapshot cụ thể, trong khi writer publish references mới.

**Câu 7.** Tại sao CAS đôi lúc vẫn sai dù mỗi CAS là nguyên tử?

**Đáp án:** Code xung quanh có thể dùng stale assumptions, vi phạm invariants, chứa side effects hoặc gặp ABA nếu cùng reference được tái sử dụng. Atomic CAS không tự chứng minh toàn thuật toán đúng.

**Câu 8.** Khi nào `AtomicLong` tốt hơn `AtomicReference<State>`?

**Đáp án:** Khi chỉ cần tăng/giảm một số nguyên đơn lẻ, AtomicLong có API trực tiếp và tránh allocation snapshot cho mỗi lần cập nhật; nếu cần invariant nhiều trường, State snapshot có thể phù hợp hơn.

## 21. Tài liệu API chính thức

- `AtomicReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- `AtomicStampedReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- `AtomicMarkableReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html
- `AtomicInteger`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `VarHandle`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html
- **JLS `17 — Threads and Locks (Java Memory Model):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Ghi nhớ cốt lõi:** AtomicReference bảo vệ **một lần thay object reference**, không tự bảo vệ mutation bên trong object. Để cập nhật state nhiều trường một cách nhất quán, hãy dựng **immutable snapshot mới** từ snapshot cũ, kiểm tra invariant và publish bằng CAS; nếu CAS thất bại, đọc lại và tính lại. Mọi hàm có thể bị gọi khi retry phải không có side effect. Khi state vượt quá một reference hoặc đụng tài nguyên ngoài, cần một protocol nhất quán rộng hơn.
