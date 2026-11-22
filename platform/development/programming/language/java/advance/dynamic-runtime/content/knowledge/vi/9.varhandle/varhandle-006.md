# 9.6 `compareAndSet`, `compareAndExchange` và các thao tác cập nhật nguyên tử với VarHandle

Khi nhiều luồng cùng cập nhật một biến, `counter++` không phải một hành động nguyên tử: mỗi lần tăng gồm đọc, tính và ghi. Nếu hai luồng cùng đọc số cũ trước khi ghi, một lần tăng có thể bị mất. `java.lang.invoke.VarHandle` (có từ Java 9, dùng tốt trên Java 17) cung cấp nhiều **atomic read-modify-write operations** trên field hoặc phần tử mảng để thực hiện kiểm tra–cập nhật, cộng số và sửa bit mà không tách thành các thao tác có thể bị luồng khác chen vào.

Phần cốt lõi của bài:

- `compareAndSet(expected,newValue)` kiểm tra và cập nhật nguyên tử, trả **`boolean` thành công/thất bại**.
- `compareAndExchange(expected,newValue)` cũng kiểm tra và cập nhật nguyên tử nhưng trả **witness**: giá trị thực sự được quan sát khi so sánh.
- `weakCompareAndSet*` có thể **thất bại giả** (*spurious failure*) ngay cả khi expected khớp; cần retry đúng cách.
- `getAndSet`, `getAndAdd`, `getAndBitwiseOr/And/Xor` và các biến thể Acquire/Release cập nhật nguyên tử theo phép biến đổi có sẵn, trả **giá trị cũ**.
- **Atomicity và memory ordering là hai vấn đề khác nhau.** Chọn sai mode hoặc kết hợp access plain/volatile không nhất quán có thể làm chương trình đồng thời sai dù một thao tác RMW riêng lẻ vẫn atomic.

Bài tập trung vào access mode của VarHandle trong Java 17, cách gọi với đúng receiver/coordinate, kiểu trả về, ngữ nghĩa bộ nhớ, lỗi và các tình huống dùng thực tế.

## 1. Vì sao `volatile` không đủ cho phép tăng?

Đoạn code:

~~~java
volatile int counter;
counter++;
~~~

là **một đoạn minh họa trong khai báo class**, chưa phải chương trình độc lập. Về mặt logic, phép tăng có thể coi là:

~~~text
old  = đọc counter
next = old + 1
ghi counter = next
~~~

Hai luồng có thể interleave:

~~~text
counter ban đầu = 0
Thread A                         Thread B
--------                         --------
đọc counter => 0
                                 đọc counter => 0
tính 1
                                 tính 1
ghi 1
                                 ghi 1
cuối cùng = 1 thay vì 2
~~~

Khai báo `volatile` quy định visibility và ordering của từng truy cập volatile, nhưng **không gom cả read + add + write thành một đơn vị không thể chen vào**. Muốn tăng chính xác, có thể dùng `synchronized`, `AtomicInteger.incrementAndGet`, hoặc một atomic update qua `VarHandle`.

Ví dụ CAS (*compare-and-set*) trên biến nguyên:

~~~text
CAS(counter, expected=0, newValue=1)
           |
           +--- counter đang là 0? --- Có ---> ghi 1, trả true
                                  |
                                  Không ---> giữ nguyên, trả false
~~~

Phép kiểm tra witness và thao tác ghi có điều kiện được thực hiện **nguyên tử trên một vị trí nhớ đích**. Không thể có một luồng xen vào đúng giữa check và write của cùng một CAS. Nhưng CAS **không phải transaction cho toàn bộ object hoặc nhiều biến**.

## 2. VarHandle tham chiếu tới một biến và tọa độ của biến

Một `VarHandle` có kiểu giá trị (**variable type** `T`) và danh sách kiểu tọa độ (**coordinate types** `CT1,...,CTn`). Cùng một handle truy cập được một nhóm biến cùng hình dạng, tùy tọa độ cụ thể khi gọi.

| Trường hợp | Tạo handle | Tọa độ | Kiểu `compareAndSet` |
| --- | --- | --- | --- |
| Instance field `Holder.number` kiểu `int` | `lookup.findVarHandle(Holder.class,"number",int.class)` | `Holder` instance | `(Holder,int,int)boolean` |
| Static field `Metrics.total` kiểu `int` | `lookup.findStaticVarHandle(Metrics.class,"total",int.class)` | Không có | `(int,int)boolean` |
| Phần tử của `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int[]`, chỉ số `int` | `(int[],int,int,int)boolean` |
| Instance field `Slot.value` kiểu `String` | `lookup.findVarHandle(Slot.class,"value",String.class)` | `Slot` instance | `(Slot,String,String)boolean` |

Dạng access mode chính:

~~~text
getVolatile:          (CT1,...,CTn) -> T
setVolatile:          (CT1,...,CTn,T newValue) -> void
compareAndSet:        (CT1,...,CTn,T expected,T newValue) -> boolean
compareAndExchange:   (CT1,...,CTn,T expected,T newValue) -> T
weakCompareAndSet:    (CT1,...,CTn,T expected,T newValue) -> boolean
getAndSet:            (CT1,...,CTn,T newValue) -> T
getAndAdd:            (CT1,...,CTn,T delta) -> T
getAndBitwiseOr:      (CT1,...,CTn,T mask) -> T
~~~

VarHandle access mode methods là **signature-polymorphic**: JavaDoc hiển thị `Object...` nhưng JVM kiểm tra symbolic call-site descriptor với access-mode type thực tế. Điều đó có nghĩa là **tham số và kiểu trả về tại vị trí gọi phải đúng**, bao gồm receiver, chỉ số mảng, expected, newValue và cast kiểu trả về phù hợp.

Có thể kiểm tra kiểu bằng `varType()`, `coordinateTypes()` và `accessModeType(VarHandle.AccessMode.COMPARE_AND_SET)`. Muốn biết một mode có được hỗ trợ hay không, dùng `isAccessModeSupported(...)`. Những API metadata này không tự tạo transaction hay cấp quyền vào field mà caller không được phép lookup.

## 3. `compareAndSet` và `compareAndExchange` khác nhau ở kết quả

Đây đều là **atomic conditional updates**: nếu witness (giá trị đọc nguyên tử từ biến) bằng expected, ghi giá trị mới; nếu khác, không ghi. Với `int`, điều kiện so sánh giá trị số. Với reference, dùng identity `==`, không dùng `equals`.

| Access mode | Khi khớp expected | Khi không khớp | Trả về |
| --- | --- | --- | --- |
| `compareAndSet` | Ghi mới | Không ghi | `true` / `false` |
| `compareAndExchange` | Ghi mới | Không ghi | **Witness cũ**, tức giá trị đọc tại thời điểm so sánh |
| `compareAndExchangeAcquire` | Ghi mới với memory ordering kiểu Acquire | Không ghi | Witness |
| `compareAndExchangeRelease` | Ghi mới với memory ordering kiểu Release | Không ghi | Witness |

**Điểm dễ nhầm:** `compareAndExchange` **không** trả `newValue`. Khi thành công, nó trả witness bằng expected; khi thất bại, nó trả witness khác expected. Giá trị trả về chỉ phản ánh lần quan sát nguyên tử ấy. Một luồng khác có thể cập nhật biến ngay sau đó, nên không được coi witness là snapshot bất biến về tương lai.

### Ví dụ 1: CAS boolean và exchange witness

Tạo file **`CasCompareDemo.java`**:

~~~java
import java.lang.invoke.*;

public class CasCompareDemo {
    static class Holder {
        volatile int number;
    }

    public static void main(String[] args) throws Exception {
        VarHandle vh = MethodHandles.lookup().findVarHandle(
            Holder.class, "number", int.class
        );
        Holder holder = new Holder();

        System.out.println("type=" + vh.varType().getSimpleName());
        System.out.println("cas1=" + vh.compareAndSet(holder, 0, 5));
        System.out.println("casFail=" + vh.compareAndSet(holder, 0, 9));

        System.out.println(
            "exchangeFail=" + (int) vh.compareAndExchange(holder, 0, 9)
        );
        System.out.println("afterFail=" + (int) vh.getVolatile(holder));

        System.out.println(
            "exchangeSuccess=" + (int) vh.compareAndExchange(holder, 5, 8)
        );
        System.out.println("final=" + (int) vh.getVolatile(holder));

        System.out.println("casType=" + vh.accessModeType(
            VarHandle.AccessMode.COMPARE_AND_SET
        ));
    }
}
~~~

~~~sh
javac --release 17 CasCompareDemo.java
java CasCompareDemo
~~~

**Stdout:**

~~~text
type=int
cas1=true
casFail=false
exchangeFail=5
afterFail=5
exchangeSuccess=5
final=8
casType=(Holder,int,int)boolean
~~~

Diễn giải theo thứ tự:

1. `Holder.number` khởi tạo bằng 0. `compareAndSet(holder,0,5)` thành công và ghi 5, nên trả `true`.
2. CAS với expected 0, new 9 thất bại vì hiện tại đang là 5; trả `false`.
3. `compareAndExchange(holder,0,9)` cũng không ghi, nhưng **trả 5** là witness thực tế. `getVolatile` sau đó vẫn thấy 5 trong ví dụ một luồng này.
4. `compareAndExchange(holder,5,8)` ghi 8, nhưng trả **5**, là giá trị trước ghi. Đọc lại cho 8.
5. `accessModeType` in chữ ký `(Holder,int,int)boolean`: instance receiver đứng trước expected và new value.

Ở các bài toán concurrent, `compareAndSet` thường đủ khi chỉ cần boolean thành công. `compareAndExchange` có ích khi muốn biết witness của lần thất bại để suy ra expected mới; nó không tự retry.

## 4. Cập nhật vô điều kiện: `getAndSet`, `getAndAdd` và bitwise RMW

Nếu phép sửa biến thuộc nhóm có sẵn, có thể dùng atomic update **không cần tự viết CAS loop**:

| Access mode | Giá trị sau cập nhật | Giá trị trả |
| --- | --- | --- |
| `getAndSet(new)` | `new` | `old` |
| `getAndAdd(delta)` | `old + delta` | `old` |
| `getAndBitwiseOr(mask)` | `old \| mask` | `old` |
| `getAndBitwiseAnd(mask)` | `old & mask` | `old` |
| `getAndBitwiseXor(mask)` | `old ^ mask` | `old` |

Ngoài các mode mặc định còn có những biến thể `getAndSetAcquire/Release`, `getAndAddAcquire/Release` và `getAndBitwiseOr/And/XorAcquire/Release` với memory ordering khác. Các mode vẫn là nguyên tử trên biến đích, nhưng **khả năng hỗ trợ phụ thuộc loại biến**. Chẳng hạn không có `getAndAdd` để nối `String`; bitwise update áp dụng cho kiểu integral/boolean phù hợp.

### Ví dụ 2: static field, số đếm, bit cờ và boolean

Lưu **`AtomicOpsDemo.java`**:

~~~java
import java.lang.invoke.*;

public class AtomicOpsDemo {
    static volatile int counter;
    static volatile int flags;
    static volatile boolean ready;

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle count = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "counter", int.class
        );
        VarHandle bits = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "flags", int.class
        );
        VarHandle state = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "ready", boolean.class
        );

        System.out.println("countOld=" + (int) count.getAndAdd(3));
        System.out.println("countNow=" + (int) count.getVolatile());

        System.out.println("setOld=" + (int) count.getAndSet(10));
        System.out.println("setNow=" + (int) count.getVolatile());

        System.out.println(
            "orOld=" + (int) bits.getAndBitwiseOr(0b0101)
        );
        System.out.println(
            "andOld=" + (int) bits.getAndBitwiseAnd(0b0011)
        );
        System.out.println(
            "xorOld=" + (int) bits.getAndBitwiseXor(0b0011)
        );
        System.out.println("bitsNow=" + (int) bits.getVolatile());

        System.out.println(
            "readyOld=" + (boolean) state.getAndBitwiseOr(true)
        );
        System.out.println("readyNow=" + (boolean) state.getVolatile());
    }
}
~~~

~~~sh
javac --release 17 AtomicOpsDemo.java
java AtomicOpsDemo
~~~

~~~text
countOld=0
countNow=3
setOld=3
setNow=10
orOld=0
andOld=5
xorOld=1
bitsNow=2
readyOld=false
readyNow=true
~~~

Flags: khởi đầu 0; OR `0101` tạo 5 và trả 0; AND `0011` tạo 1 và trả 5; XOR `0011` tạo 2 và trả 1. `ready` sử dụng logic OR với boolean. Cả ba field đều `static` nên **không truyền receiver**.

**`getAndAdd` trả old, không phải new.** `AtomicInteger.addAndGet` là API khác, trả new. Nếu có nhiều thread cập nhật, lần đọc lại ngay sau RMW có thể thấy một cập nhật khác nữa; giá trị cũ trả về từ chính thao tác là thông tin xác định cho lần RMW đó.

Tương tự, một phép cộng số nguyên có thể overflow theo quy tắc kiểu số Java. Atomicity không tự thêm kiểm tra miền giá trị, giới hạn số dư hay business rule.

## 5. CAS trên reference dùng `==`, không gọi `equals`

Đối với VarHandle tới một field tham chiếu, điều kiện witness bằng expected là **cùng object**, không phải hai object có nội dung tương đương. Đây là đặc tính quan trọng khi lưu immutable state, linked nodes, reference cache hay một snapshot toàn cục.

### Ví dụ 3: nội dung String bằng nhau nhưng CAS thất bại

Lưu **`ReferenceIdentityDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReferenceIdentityDemo {
    static class Slot {
        volatile String text;
    }

    public static void main(String[] args) throws Exception {
        VarHandle text = MethodHandles.lookup().findVarHandle(
            Slot.class, "text", String.class
        );
        Slot slot = new Slot();

        String original = new String("token");
        String equalButDifferent = new String("token");
        slot.text = original;

        System.out.println("equals=" +
            original.equals(equalButDifferent));
        System.out.println("sameRef=" +
            (original == equalButDifferent));

        System.out.println("casEqualContents=" + text.compareAndSet(
            slot, equalButDifferent, "changed"
        ));

        String witness = (String) text.compareAndExchange(
            slot, original, "changed"
        );
        System.out.println("witnessWasOriginal=" + (witness == original));
        System.out.println("now=" + (String) text.getVolatile(slot));
    }
}
~~~

~~~sh
javac --release 17 ReferenceIdentityDemo.java
java ReferenceIdentityDemo
~~~

~~~text
equals=true
sameRef=false
casEqualContents=false
witnessWasOriginal=true
now=changed
~~~

Hai `new String("token")` tạo hai instance khác nhau mặc dù `equals` trả true. CAS với instance khác không phù hợp expected. Exchange với đúng reference `original` thành công; witness bằng object gốc. Không nên thử ví dụ identity bằng cách dùng hai string literal rồi khẳng định chúng khác nhau: interning có thể dùng chung reference.

**Lưu ý:** đổi nguyên tử reference trong field **không** làm cho dữ liệu mutable nằm bên trong object trở nên tự động thread-safe. VarHandle bảo vệ phép truy cập tới **biến được trỏ**, không bảo vệ mọi phép sửa trên object mà biến chứa.

## 6. Memory ordering: volatile, acquire, release, plain và opaque

Một thao tác có thể bảo đảm **atomicity trên một biến** nhưng lại có ràng buộc khác nhau về thứ tự quan sát các biến khác giữa các luồng. Java SE 17 định nghĩa nhiều access mode với memory effects:

| Cấp độ | Ví dụ | Ý nghĩa cần hiểu |
| --- | --- | --- |
| Plain | `get`, `set` | Truy cập tương tự trường không volatile; không mang đồng bộ liên luồng như acquire/release |
| Opaque | `getOpaque`, `setOpaque` | Bitwise atomic và coherent order cho cùng biến; ít ràng buộc thứ tự với dữ liệu khác |
| Acquire | `getAcquire`, `...Acquire` | Những load/store sau acquire không được đưa lên trước acquire theo hợp đồng bộ nhớ |
| Release | `setRelease`, `...Release` | Những load/store trước release không được đưa xuống sau release theo hợp đồng |
| Volatile | `getVolatile`, `setVolatile`, `compareAndSet`, `compareAndExchange` và RMW thường | Hiệu ứng volatile read/write, mạnh hơn acquire/release riêng lẻ trong các giao thức thông dụng |

Với các atomic update:

- `compareAndSet` và `compareAndExchange` có hiệu ứng đọc `getVolatile` và ghi `setVolatile` khi điều kiện thỏa.
- `compareAndExchangeAcquire` đọc witness với `getAcquire`, ghi mới với `set` (plain).
- `compareAndExchangeRelease` đọc witness với `get` (plain), ghi mới với `setRelease`.
- `getAndSetAcquire`, `getAndAddAcquire` và các bitwise `...Acquire` áp dụng read-acquire + write-plain.
- `getAndSetRelease`, `getAndAddRelease` và các bitwise `...Release` áp dụng read-plain + write-release.

Tên mode yếu hơn **không có nghĩa cập nhật mất tính nguyên tử**. Nhưng một luồng publish dữ liệu bằng release và luồng khác consume bằng acquire phải tham gia đúng **cùng một giao thức đồng bộ hóa**; thay một phía bằng plain tùy ý có thể khiến dữ liệu khác chưa được thấy đúng lúc.

Mặc dù ví dụ dùng các field `volatile` để làm rõ ý định, VarHandle có thể dùng access mode volatile/CAS trên field không được khai báo `volatile` khi mode đó được hỗ trợ. Tuy nhiên trộn các đường truy cập plain và volatile thiếu thiết kế nhất quán là nguồn rủi ro về data race/visibility. Chỉ giảm memory ordering sau khi đã chứng minh được tính đúng đắn theo Java Memory Model.

## 7. `weakCompareAndSet*` có thể trả false giả

Java 17 cung cấp:

- `weakCompareAndSetPlain`: read/write plain.
- `weakCompareAndSet`: read/write volatile.
- `weakCompareAndSetAcquire`: read acquire, write plain.
- `weakCompareAndSetRelease`: read plain, write release.

Chúng vẫn thực hiện CAS nguyên tử khi thành công, nhưng **được phép thất bại giả (spurious failure)** ngay cả khi witness đúng expected. Vì vậy không được hiểu mọi `false` của weak CAS là bằng chứng một luồng khác đã đổi biến. `compareAndSet` mạnh không có đường thất bại giả này theo đặc tả; `false` nghĩa là witness không bằng expected.

Một **snippet** dùng biến `VarHandle VALUE` và object `counter` (được định nghĩa trong ví dụ 4 bên dưới) để tăng số theo weak CAS:

~~~java
for (;;) {
    int old = (int) VALUE.getVolatile(counter);
    int next = old + 1;

    if (VALUE.weakCompareAndSet(counter, old, next)) {
        break;
    }

    Thread.onSpinWait(); // chỉ là CPU hint
}
~~~

Vòng lặp đọc lại giá trị sau mỗi lần thất bại để tính lại next. Nó không tự bảo đảm thời gian hoàn thành hoặc số lần thử hữu hạn. `Thread.onSpinWait()` là hint giúp tối ưu một số spin loop, không phải synchronization primitive; khi có tranh chấp lớn có thể cân nhắc backoff hoặc giải pháp khác.

Với weak CAS Plain, không được lầm rằng nó tự mang volatile memory semantics chỉ vì có tên “CAS”. Chọn suffix theo yêu cầu visibility và ordering của thuật toán.

## 8. CAS loop và `getAndAdd` trong ứng dụng đa luồng

Khi cập nhật phụ thuộc vào old value, thường dùng vòng:

~~~text
old = đọc biến
next = f(old)
try CAS(expected=old, new=next)
  thành công: xong
  thất bại: đọc lại và tính lại
~~~

Nhờ CAS, việc ghi chỉ xảy ra nếu dữ liệu chưa thay đổi kể từ lần đọc expected (xét đúng phép so sánh ở thời điểm CAS). Nếu dùng `setVolatile(old + 1)` sau một lần đọc, check và ghi **không phải một đơn vị nguyên tử**.

### Ví dụ 4: bốn thread cập nhật cùng hai bộ đếm

Lưu **`CasConcurrencyDemo.java`**:

~~~java
import java.lang.invoke.*;

public class CasConcurrencyDemo {
    static class Counter {
        volatile int value;
    }

    static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class
            );
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter cas = new Counter();
        Counter rmw = new Counter();
        Thread[] threads = new Thread[4];

        for (int t = 0; t < threads.length; t++) {
            threads[t] = new Thread(() -> {
                for (int i = 0; i < 10_000; i++) {
                    while (true) {
                        int old = (int) VALUE.getVolatile(cas);

                        if (VALUE.compareAndSet(cas, old, old + 1)) {
                            break;
                        }
                        Thread.onSpinWait();
                    }

                    VALUE.getAndAdd(rmw, 1);
                }
            });
            threads[t].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("cas=" + (int) VALUE.getVolatile(cas));
        System.out.println("getAndAdd=" + (int) VALUE.getVolatile(rmw));
    }
}
~~~

~~~sh
javac --release 17 CasConcurrencyDemo.java
java CasConcurrencyDemo
~~~

~~~text
cas=40000
getAndAdd=40000
~~~

Mỗi luồng cập nhật mỗi counter 10.000 lần. Sau `join()`, tổng là 40.000 nếu các thread kết thúc bình thường. `getAndAdd(rmw,1)` tiện khi quy tắc update chỉ là cộng; CAS loop thích hợp nếu `next=f(old)` là hàm tùy chỉnh.

Nếu cần dùng witness từ `compareAndExchange` thay vì gọi `getVolatile` lại sau mỗi lần CAS thất bại, có thể viết **snippet phụ thuộc vào VALUE và counter của ví dụ trên**:

~~~java
int seen = (int) VALUE.getVolatile(counter);
for (;;) {
    int witness = (int) VALUE.compareAndExchange(
        counter, seen, seen + 1
    );
    if (witness == seen) {
        break; // cập nhật thành công
    }
    seen = witness; // giá trị đã quan sát; thử lại
}
~~~

Snippet này không độc lập; muốn dùng trong ứng dụng hãy đặt nó trong method có `counter` và `VALUE` đúng kiểu. Một thread khác vẫn có thể sửa biến sau khi witness được trả, vì thế **lần thử tiếp theo luôn phải kiểm tra bằng CAS**, không giả định witness còn là current value.

**Side effects:** hàm tính `f(old)` trong vòng retry có thể chạy nhiều lần. Tránh gửi thông báo, thu tiền, ghi giao dịch hoặc thực hiện tác dụng phụ không thể lặp an toàn bên trong tính toán trước khi CAS được xác nhận. CAS một biến cũng không biến toàn bộ nghiệp vụ thành transaction.

## 9. Những access mode không được hỗ trợ và lỗi kiểu

`VarHandle` chỉ cung cấp mode được hỗ trợ bởi dạng và kiểu biến tương ứng:

- Một field `final` được xem là read-only qua VarHandle; write, CAS và RMW modes không được hỗ trợ.
- `getAndAdd` trên `String` không phải phép nối chuỗi và không được hỗ trợ.
- Bitwise modes dùng cho các kiểu integral/boolean phù hợp, không phải phép cập nhật tùy ý lên object.
- Access mode có thể hợp lệ nhưng lời gọi vẫn sai **signature**: thiếu instance receiver, thiếu array index, dùng `long` khi field là `int`, hoặc cast return type không đúng.

### Ví dụ 5: final field, String field, phần tử mảng và kiểu sai

Lưu **`ModesAndArrayDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ModesAndArrayDemo {
    static class Data {
        final int id = 7;
        volatile String label = "start";
        volatile int counter = 7;
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle id = lookup.findVarHandle(
            Data.class, "id", int.class
        );
        VarHandle label = lookup.findVarHandle(
            Data.class, "label", String.class
        );
        VarHandle count = lookup.findVarHandle(
            Data.class, "counter", int.class
        );
        Data data = new Data();

        System.out.println("finalCasSupported=" +
            id.isAccessModeSupported(
                VarHandle.AccessMode.COMPARE_AND_SET
            ));

        try {
            boolean ignored = id.compareAndSet(data, 7, 8);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                "finalCas=" + ex.getClass().getSimpleName()
            );
        }

        System.out.println("stringAddSupported=" +
            label.isAccessModeSupported(
                VarHandle.AccessMode.GET_AND_ADD
            ));

        try {
            String ignored = (String) label.getAndAdd(data, "x");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                "stringAdd=" + ex.getClass().getSimpleName()
            );
        }

        int[] values = { 10 };
        VarHandle element =
            MethodHandles.arrayElementVarHandle(int[].class);

        System.out.println("arrayCas=" +
            element.compareAndSet(values, 0, 10, 12));
        System.out.println("arrayOld=" +
            (int) element.getAndAdd(values, 0, 5));
        System.out.println("arrayNow=" + values[0]);

        try {
            boolean ignored = count.compareAndSet(data, 7L, 8L);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "wrongType=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 ModesAndArrayDemo.java
java ModesAndArrayDemo
~~~

~~~text
finalCasSupported=false
finalCas=UnsupportedOperationException
stringAddSupported=false
stringAdd=UnsupportedOperationException
arrayCas=true
arrayOld=12
arrayNow=17
wrongType=WrongMethodTypeException
~~~

`finalCasSupported=false` vì field id là final; `stringAddSupported=false` vì String không hỗ trợ phép cộng số. Mảng `{10}` đổi từ 10 sang 12 bằng CAS, `getAndAdd(values,0,5)` trả old 12 và cập nhật thành 17. Với field `counter` kiểu `int`, truyền expected/new kiểu `long` khiến call-site descriptor sai, nên ném `WrongMethodTypeException`.

**Đặc biệt:** khi dùng một handle vừa **không hỗ trợ mode**, vừa truyền sai signature, `UnsupportedOperationException` có thể xuất hiện trước lỗi kiểu. Để kiểm tra riêng wrong type, ví dụ đã gọi trên field `counter` writable.

### Phân biệt exception để sửa đúng nguyên nhân

| Exception | Nguyên nhân thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `NoSuchFieldException` | Lookup không tìm đúng field/tên/kiểu | `findVarHandle`, field khai báo, type |
| `IllegalAccessException` | Lookup thiếu quyền | Declaring type, package, module, `Lookup` mode |
| `UnsupportedOperationException` | Access mode unsupported trên VarHandle | `isAccessModeSupported(...)`, `final`, type |
| `WrongMethodTypeException` | Call-site descriptor sai so với access-mode type | Tọa độ, số lượng argument, type, return cast |
| `ClassCastException` | Một reference cast thất bại | Kiểu object thực tế và descriptor |
| `NullPointerException` | Tọa độ receiver/array `null` hoặc trường hợp dùng `null` không phù hợp | Kiểm tra input |
| `ArrayIndexOutOfBoundsException` | Chỉ số mảng sai | Tọa độ index |
| `ExceptionInInitializerError` | Lỗi khởi tạo lớp khi xây handle trong static initializer | Cause gốc |

Không giải quyết lỗi type bằng cách gọi `setAccessible(true)` hay mặc định đổi biến sang `Object`. Quyền lookup, mode support và call-site type là các điều kiện độc lập.

## 10. Vấn đề ABA, nhiều biến và progress

### ABA: expected quay trở lại sau khi đã thay đổi

Giả sử thread A đọc reference `A`. Trong lúc đó thread B đổi reference thành `B` rồi đổi lại `A`:

~~~text
A đọc expected=A
B ghi B
B ghi A
A compareAndSet(expected=A,new=C) => thành công
~~~

CAS thành công vì witness **đúng bằng A** tại thời điểm so sánh, nhưng nó **không chứng minh trạng thái chưa từng thay đổi**. Đây là **ABA problem**. `compareAndExchange` cũng không tự giải quyết ABA, vì witness vẫn có thể bằng expected sau chuỗi A→B→A.

Nếu thuật toán cần phân biệt các thế hệ của cùng reference, có thể dùng `AtomicStampedReference`, hoặc lưu một **immutable state chứa value và version** trong một reference rồi CAS thay toàn bộ snapshot. Chỉ tăng version ở một field khác trong khi CAS field gốc **không tự làm cặp field trở thành một đơn vị nguyên tử**.

### Atomic trên một field không tạo transaction nhiều field

Chuyển tiền từ tài khoản A sang B bằng hai lệnh `getAndAdd(A,-amount)` và `getAndAdd(B,+amount)` không atomic như một giao dịch. Thread thứ ba có thể quan sát thời điểm sau khi trừ nhưng trước khi cộng. Cần cơ chế transaction/lock hoặc mô hình gộp trạng thái và CAS phù hợp.

### CAS không bảo đảm mỗi thread luôn tiến triển nhanh

CAS loop có thể rất hiệu quả khi cạnh tranh thấp, nhưng nếu các luồng liên tục làm mất hiệu lực expected của nhau thì retry lặp nhiều lần. **Không suy ra tính wait-free** hoặc đảm bảo thời gian hoàn thành cố định chỉ vì có CAS. `Thread.onSpinWait()` không tạo bảo đảm tiến độ. Với counter cập nhật cực nóng, `LongAdder` có thể giảm contention trong một số workload nhưng có semantics đọc khác `AtomicLong`; cần đánh giá tùy yêu cầu độ chính xác snapshot.

## 11. Nên chọn VarHandle hay Atomic classes?

| Nhu cầu | Cách thích hợp | Lý do |
| --- | --- | --- |
| Cần CAS với boolean kết quả | `VarHandle.compareAndSet` | Đơn giản, strong CAS |
| Cần biết witness cũ để retry | `VarHandle.compareAndExchange` | Trả giá trị thực tế tại phép so sánh |
| Cần thay luôn và biết old | `getAndSet` | Atomic exchange |
| Cần tăng/giảm | `getAndAdd` hoặc `AtomicInteger` | Không phải tự viết CAS loop |
| Cần cập nhật bit flags | `getAndBitwiseOr/And/Xor` | Atomic bitwise RMW |
| Cần kiểu memory ordering cụ thể | Các biến thể `Acquire/Release` | Phù hợp giao thức đồng bộ hóa có chứng minh |
| Chỉ cần bộ đếm ứng dụng | `AtomicInteger`/`AtomicLong` | API trực tiếp, thường đơn giản hơn VarHandle |
| Nhiều thread cập nhật counter rất nóng | Cân nhắc `LongAdder` | Có thể giảm contention, đổi semantics snapshot |
| Phải cập nhật hàm tùy ý của old | CAS loop hoặc `AtomicInteger.updateAndGet` | Retry đúng cách, hàm phải tránh side effects |
| Cần cập nhật nhiều field nguyên tử như transaction | Lock/transaction hoặc gộp state | Một CAS không bảo vệ đa biến |

**Lưu ý về VarHandle:** một handle immutable mô tả trường chứ không sở hữu giá trị của trường. Ví dụ 4 dùng cùng `VALUE` trên hai instance `cas` và `rmw`: chúng là hai vị trí khác nhau nhờ receiver. Nếu sử dụng thư viện/concurrent abstraction, ưu tiên API trừu tượng rõ ràng thay vì lặp lại lookup/code xử lý lỗi ở mọi nơi.

## 12. Quy trình tự kiểm tra và lỗi phổ biến

Trước khi đưa một updater VarHandle vào code concurrent:

1. Kiểm tra **biến và coordinate**: instance/static/array, `varType()`, `coordinateTypes()`; với array cần index, với static không cần receiver.
2. Kiểm tra **lookup access**: `Lookup` có quyền truy cập declaring field và các ràng buộc module không?
3. Kiểm tra **access mode support**: `isAccessModeSupported(...)` trước những mode phụ thuộc kiểu hoặc `final`.
4. Kiểm tra **call-site signature**: đối số và kiểu trả về chính xác theo `accessModeType(...)`; đừng nhầm `long`/`int` hay thiếu receiver.
5. Phân biệt **kết quả**: `compareAndSet` là boolean; `compareAndExchange` là witness; `getAnd*` trả old.
6. Xác định **memory ordering**: volatile/acquire/release/plain; bảo đảm cả giao thức publish/read phù hợp Java Memory Model.
7. Nếu có **retry**, tính lại từ old mới, tránh side effects bị lặp, và đánh giá contention/starvation.
8. Kiểm tra **ABA** và bất biến nhiều biến; chọn stamp/version hoặc cơ chế đồng bộ khác nếu cần.
9. Với test một luồng, kiểm tra cả nhánh CAS đúng và sai, giá trị trả và state sau thao tác. Với test đa luồng, đồng bộ kết thúc bằng `join()` rồi kiểm tra tổng. Nhiều lần test/stress hữu ích nhưng không phải chứng minh hình thức không có race.

Các ngộ nhận thường gặp:

- “`volatile counter++` đã atomic” — sai.
- “`compareAndSet` trả số cũ” — sai: trả boolean.
- “`compareAndExchange` trả số mới” — sai: trả witness.
- “Hai object `equals` là CAS reference chắc chắn thành công” — sai: CAS so `==`.
- “`weakCompareAndSetPlain` trả false chứng minh dữ liệu đã khác” — sai: có thể thất bại giả.
- “`getAndAdd` trả tổng sau khi cộng” — sai: trả old.
- “`final` field cứ có VarHandle là CAS được” — sai: access mode ghi/RMW unsupported.
- “Atomic RMW một field làm toàn object thread-safe” — sai.
- “CAS không gặp starvation vì không cần lock” — sai.
- “Witness trùng expected chứng minh chưa từng có thay đổi” — sai nếu xảy ra ABA.
- “Acquire/Release nghĩa là không atomic” — sai; atomic update vẫn atomic nhưng hiệu ứng thứ tự khác.
- “Gọi VarHandle như varargs Object[] bình thường” — sai; các access modes là signature-polymorphic.

## 13. Câu hỏi tự luyện

**Câu 1.** `int state=10`, gọi `compareAndSet(expected=9,new=20)` thì trả gì, state còn bao nhiêu?

**Đáp án:** Trả `false`, state vẫn 10.

**Câu 2.** `compareAndExchange(expected=9,new=20)` trên state 10 trả gì? Nếu expected=10?

**Đáp án:** Trường hợp expected 9 trả witness 10 và không ghi; expected 10 trả witness **vẫn là 10** nhưng ghi state thành 20.

**Câu 3.** `getAndAdd(4)` trên state 7 trả gì?

**Đáp án:** Trả 7; state sau cập nhật là 11.

**Câu 4.** `getAndBitwiseOr(0b0100)` trên flags `0b0001` cho kết quả cũ/mới nào?

**Đáp án:** Trả old 1, flags thành `0b0101` (5).

**Câu 5.** Hai reference cùng nội dung `equals` nhưng là hai object khác nhau: CAS dùng expected là object thứ hai có thành công nếu field trỏ object thứ nhất không?

**Đáp án:** Không; identity `==` khác nhau.

**Câu 6.** Vì sao weak CAS phải có retry và kiểm tra lại giá trị?

**Đáp án:** Nó có thể thất bại giả, đồng thời thread khác cũng có thể cập nhật giữa các lần thử. Mỗi vòng phải đọc/tính lại expected phù hợp.

**Câu 7.** Với VarHandle của `int[]`, `compareAndSet` cần những tham số nào?

**Đáp án:** `int[] array`, `int index`, `int expected`, `int newValue`; trả boolean.

**Câu 8.** Hai lệnh `getAndAdd` trên hai field có là một transaction không?

**Đáp án:** Không. Mỗi lệnh atomic riêng; cần cơ chế đồng bộ cho bất biến xuyên nhiều field.

**Câu 9.** Vì sao `compareAndExchange` trả witness khác expected hữu ích khi retry?

**Đáp án:** Caller có thêm một giá trị đã quan sát để làm expected mới mà không nhất thiết đọc lại ngay. Tuy nhiên luồng khác vẫn có thể thay đổi tiếp, vì vậy vẫn phải CAS kiểm tra.

**Câu 10.** `isAccessModeSupported(COMPARE_AND_SET)==false` và `WrongMethodTypeException` nói cùng vấn đề không?

**Đáp án:** Không. Một bên là mode không được hỗ trợ, một bên là descriptor của call site không phù hợp với mode/handle.

## 14. Nguồn tra cứu Java 17

- `java.lang.invoke.VarHandle` — các atomic access modes và memory ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html
- `VarHandle.AccessMode`, `accessModeType`, `isAccessModeSupported`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html
- `MethodHandles.Lookup.findVarHandle`, `findStaticVarHandle` và `arrayElementVarHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- `java.util.concurrent.atomic.AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `java.util.concurrent.atomic.AtomicStampedReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- JLS Java 17, Chapter 17 — Threads and Locks/Memory Model: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Ghi nhớ:** `compareAndSet` trả boolean, `compareAndExchange` trả witness, `getAnd*` trả old. Chúng giải quyết nguyên tử trên **một biến** và có nhiều lựa chọn memory ordering. Muốn dùng chính xác phải hiểu tọa độ, kiểu biến, access mode support, reference identity, retry, ABA và ranh giới atomicity của toàn hệ thống.