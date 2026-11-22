# So sánh plain, opaque, acquire, release và volatile trong Java

## 1. Trật tự bộ nhớ trong Java là gì?

Trật tự bộ nhớ (memory ordering) mô tả những bảo đảm mà Java đưa ra về thứ tự quan sát các lần đọc và ghi biến giữa nhiều thread. Trình biên dịch và CPU có thể tối ưu hoặc sắp xếp lại một số thao tác nếu kết quả vẫn hợp lệ theo Java Memory Model (JMM).

Trong một thread, chương trình có thứ tự thực thi theo quy tắc của ngôn ngữ. Nhưng khi nhiều thread cùng truy cập dữ liệu, thứ tự trong mã nguồn không tự động tạo ra quan hệ nhìn thấy dữ liệu giữa các thread.

Ví dụ, thread A ghi dữ liệu rồi đặt cờ báo sẵn sàng; thread B đọc cờ rồi đọc dữ liệu. Nếu hai biến được truy cập bằng plain mode, chỉ nhìn vào thứ tự câu lệnh không đủ để bảo đảm thread B thấy dữ liệu mà A đã ghi.

VarHandle từ Java 9 cho phép chọn memory access mode cho từng lần truy cập:

- **plain**: truy cập thông thường, không tạo ordering liên luồng.
- **opaque**: bảo đảm tính nguyên tử và nhất quán theo từng biến, không sắp thứ tự với biến khác.
- **acquire/release**: tạo ordering một chiều giữa lần đọc acquire và lần ghi release tương ứng.
- **volatile**: cung cấp ngữ nghĩa volatile và total order giữa các volatile access.

Các mode này tạo thành những mức bảo đảm khác nhau. Chọn mode theo giao thức đồng bộ của dữ liệu; dùng mode mạnh hơn không tự sửa được một thuật toán sai.

## 2. Plain: truy cập thông thường

Plain là memory mode cơ bản của VarHandle:

~~~java
int value = (int) handle.get(target);
handle.set(target, 10);
~~~

get() và set() có ngữ nghĩa như đọc/ghi biến không volatile. Chúng phù hợp khi dữ liệu chỉ được truy cập trong một thread, hoặc khi việc đồng bộ đã được bảo đảm bởi một cơ chế khác như khóa, thread confinement hay immutable publication.

Plain access không tạo quan hệ happens-before giữa các thread. Nếu một thread ghi biến plain và thread khác đọc biến plain mà không có đồng bộ thích hợp, reader có thể thấy giá trị cũ hoặc hành vi quan sát không như mong đợi.

Về atomicity, hợp đồng VarHandle bảo đảm plain read/write bitwise atomic đối với reference và primitive có kích thước tối đa 32 bit. Không dựa vào tính nguyên tử của plain access với long hoặc double trên mọi nền tảng; đặc biệt không giả định chúng luôn được đọc/ghi nguyên tử trên nền tảng 32-bit.

Plain không có nghĩa là "chạy ngay lập tức" hoặc "luôn đọc giá trị mới nhất". Nó chỉ có các bảo đảm tối thiểu của truy cập thông thường trong JMM.

## 3. Opaque: nhất quán trên cùng một biến

Opaque mode được cung cấp qua getOpaque() và setOpaque():

~~~java
handle.setOpaque(target, 10);
int value = (int) handle.getOpaque(target);
~~~

Opaque access có tính nguyên tử và được sắp thứ tự nhất quán đối với các truy cập vào cùng biến. Tuy nhiên, nó không áp đặt ordering đối với những biến khác.

Điều đó có nghĩa là các thread có thể quan sát các thao tác opaque trên cùng một biến theo một thứ tự nhất quán, nhưng opaque flag không đủ để công bố những lần ghi trước đó vào các biến payload khác.

Opaque thường hữu ích khi cần tính nhất quán cho một giá trị độc lập, chẳng hạn một trạng thái đơn giản hoặc một tham chiếu mà không cần quan hệ publish/consume với những trường khác.

Không dùng opaque thay cho acquire/release khi một cờ được dùng để báo rằng một nhóm dữ liệu khác đã sẵn sàng. Opaque không tạo ordering giữa cờ và payload.

## 4. Release: công bố các thao tác trước lần ghi

Release mode thường dùng ở phía producer. setRelease() ghi giá trị và bảo đảm các load/store trước lần ghi đó không bị sắp xếp lại ra sau nó:

~~~java
PAYLOAD.set(data);
READY.setRelease(1);
~~~

Trong ví dụ, producer ghi payload trước rồi mới ghi cờ READY bằng release. Các thao tác trước release được giữ trước lần ghi release theo memory ordering contract.

Release không tự buộc thread khác nhìn thấy dữ liệu. Cần một lần đọc acquire tương ứng ở phía consumer để thiết lập ordering giữa hai thread.

Release phù hợp cho thao tác publish: chuẩn bị dữ liệu trước, sau đó phát tín hiệu rằng dữ liệu đã sẵn sàng.

## 5. Acquire: nhận dữ liệu sau khi quan sát tín hiệu

Acquire mode thường dùng ở phía consumer. getAcquire() đọc giá trị và bảo đảm các load/store sau lần đọc đó không bị sắp xếp lại lên trước nó:

~~~java
while ((int) READY.getAcquire() == 0) {
    Thread.onSpinWait();
}

int data = (int) PAYLOAD.get();
~~~

Khi lần đọc acquire quan sát được giá trị được ghi bởi release tương ứng trên cùng biến READY, các thao tác trước release được sắp thứ tự trước những thao tác sau acquire. Vì vậy consumer có thể đọc payload đã được producer chuẩn bị.

Cặp release/acquire là một giao thức publish/consume:

1. Producer ghi payload.
2. Producer ghi cờ bằng setRelease().
3. Consumer đọc cờ bằng getAcquire().
4. Sau khi thấy tín hiệu, consumer đọc payload.

Acquire và release yếu hơn volatile ở một số khía cạnh. Chúng không tạo total order toàn cục giữa mọi volatile-style access. Chúng chỉ thiết lập ordering cần thiết quanh cặp truy cập tương ứng.

Đừng đảo chiều cặp: dùng setRelease ở phía ghi và getAcquire ở phía đọc. getOpaque hoặc get plain không thay thế được acquire trong giao thức công bố dữ liệu này.

## 6. Volatile: ordering mạnh và total order

Volatile mode được dùng qua getVolatile() và setVolatile():

~~~java
handle.setVolatile(target, 1);
int value = (int) handle.getVolatile(target);
~~~

Volatile access có ngữ nghĩa như đọc/ghi biến volatile. Volatile write và volatile read tạo quan hệ đồng bộ theo JMM; volatile operations cũng được đặt trong một total order nhất quán với thứ tự chương trình của từng thread.

Một mẫu publish/consume:

~~~java
PAYLOAD.set(data);
READY.setVolatile(1);

// Thread khác:
while ((int) READY.getVolatile() == 0) {
    Thread.onSpinWait();
}
int data = (int) PAYLOAD.get();
~~~

Volatile phù hợp cho cờ trạng thái, publication đơn giản và dữ liệu cần visibility cùng ordering rõ ràng. Nó không làm cho một chuỗi thao tác như count++ trở thành nguyên tử. Với cập nhật read-modify-write, dùng compareAndSet, getAndAdd hoặc khóa phù hợp.

Volatile access thường mạnh hơn acquire/release cần thiết cho một số giao thức publish/consume. Chọn volatile khi cần ngữ nghĩa volatile dễ hiểu hoặc total order; cân nhắc acquire/release khi đã có giao thức rõ ràng và muốn ordering hẹp hơn.

## 7. So sánh năm memory mode

| Mode | Read | Write | Bảo đảm chính |
|---|---|---|---|
| Plain | get() | set() | Ngữ nghĩa non-volatile; không ordering liên luồng |
| Opaque | getOpaque() | setOpaque() | Atomic và coherent trên cùng biến; không ordering biến khác |
| Acquire | getAcquire() | — | Các thao tác sau read không được chuyển lên trước; phối hợp với release tương ứng |
| Release | — | setRelease() | Các thao tác trước write không được chuyển xuống sau; phối hợp với acquire tương ứng |
| Volatile | getVolatile() | setVolatile() | Ngữ nghĩa volatile; volatile operations có total order |

Có thể hình dung mức ordering tăng dần như sau:

~~~text
Plain
  |
Opaque       (coherence trên cùng biến)
  |
Acquire / Release   (ordering một chiều giữa cặp phù hợp)
  |
Volatile     (ngữ nghĩa volatile và total order)
~~~

Sơ đồ chỉ mô tả mức bảo đảm khái quát, không phải thang đo hiệu năng. Chi phí thực tế phụ thuộc CPU, JVM, kiến trúc bộ nhớ, loại biến và cách JIT tối ưu.

Acquire là mode đọc, release là mode ghi. Không có getRelease() hoặc setAcquire() trong nhóm truy cập cơ bản; dùng đúng chiều của API.

## 8. Ví dụ publish/consume bằng release/acquire

Ví dụ đầy đủ dưới đây dùng hai thread. Producer ghi payload bằng plain access rồi phát cờ bằng release. Consumer đợi cờ bằng acquire rồi đọc payload bằng plain access.

**Tệp VarHandleMemoryOrderDemo.java:**

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleMemoryOrderDemo {
    private static int plainValue;
    private static int opaqueValue;
    private static int volatileValue;
    private static int payload;
    private static int ready;

    private static final VarHandle PLAIN;
    private static final VarHandle OPAQUE;
    private static final VarHandle VOLATILE;
    private static final VarHandle PAYLOAD;
    private static final VarHandle READY;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            PLAIN = lookup.findStaticVarHandle(
                    VarHandleMemoryOrderDemo.class, "plainValue", int.class);
            OPAQUE = lookup.findStaticVarHandle(
                    VarHandleMemoryOrderDemo.class, "opaqueValue", int.class);
            VOLATILE = lookup.findStaticVarHandle(
                    VarHandleMemoryOrderDemo.class, "volatileValue", int.class);
            PAYLOAD = lookup.findStaticVarHandle(
                    VarHandleMemoryOrderDemo.class, "payload", int.class);
            READY = lookup.findStaticVarHandle(
                    VarHandleMemoryOrderDemo.class, "ready", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        PLAIN.set(10);
        System.out.println("plain value: " + (int) PLAIN.get());

        OPAQUE.setOpaque(20);
        System.out.println("opaque value: " + (int) OPAQUE.getOpaque());

        VOLATILE.setVolatile(30);
        System.out.println("volatile value: " + (int) VOLATILE.getVolatile());

        Thread writer = new Thread(() -> {
            PAYLOAD.set(42);
            READY.setRelease(1);
        });

        Thread reader = new Thread(() -> {
            while ((int) READY.getAcquire() == 0) {
                Thread.onSpinWait();
            }

            int observed = (int) PAYLOAD.get();
            System.out.println("release/acquire payload: " + observed);
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all VarHandleMemoryOrderDemo.java
java VarHandleMemoryOrderDemo
~~~

Output:

~~~text
plain value: 10
opaque value: 20
volatile value: 30
release/acquire payload: 42
~~~

Ba dòng đầu minh họa cách gọi các access mode trong cùng thread. Dòng cuối minh họa publication giữa hai thread: reader chỉ đọc payload sau khi getAcquire quan sát được cờ READY đã được setRelease.

Ví dụ không cố chứng minh rằng plain hoặc opaque chắc chắn sẽ đọc giá trị cũ. Các race test kiểu đó phụ thuộc timing và phần cứng; việc không quan sát thấy lỗi trong một lần chạy không chứng minh code có ordering đúng.

## 9. Access mode ghi đè modifier volatile tại khai báo

Một điểm rất quan trọng: VarHandle access mode quyết định memory semantics của lần truy cập. Nó ghi đè ordering được quy định tại khai báo biến.

Ví dụ một trường được khai báo volatile:

~~~java
private volatile int state;
~~~

Nếu VarHandle truy cập trường đó bằng get(), lần đọc có ngữ nghĩa plain. Nếu dùng getOpaque(), lần đọc có ngữ nghĩa opaque. Chỉ getVolatile() mới yêu cầu ngữ nghĩa volatile cho lần đọc đó.

Tương tự, set() trên một trường volatile vẫn là plain write theo access mode của lời gọi.

Vì vậy, không trộn tùy tiện get/set plain với getVolatile/setVolatile trên cùng biến. Nếu một giao thức đồng bộ cần volatile, tất cả đường truy cập liên quan phải tuân thủ cùng giao thức. Việc khai báo trường volatile không tự nâng mọi access mode của VarHandle lên volatile.

## 10. Atomic update mode và memory ordering

VarHandle còn có các thao tác read-modify-write nguyên tử. Một số phương thức phổ biến:

| Nhóm | Phương thức |
|---|---|
| Compare-and-set volatile | compareAndSet |
| Compare-and-exchange | compareAndExchange, compareAndExchangeAcquire, compareAndExchangeRelease |
| Weak CAS | weakCompareAndSetPlain, weakCompareAndSet, weakCompareAndSetAcquire, weakCompareAndSetRelease |
| Get-and-set | getAndSet, getAndSetAcquire, getAndSetRelease |
| Get-and-add | getAndAdd, getAndAddAcquire, getAndAddRelease |
| Bitwise atomic update | getAndBitwiseOr/And/Xor và các biến thể Acquire/Release |

Ví dụ:

~~~java
boolean changed = HANDLE.compareAndSet(target, expected, update);
int oldValue = (int) HANDLE.getAndAdd(target, 1);
~~~

compareAndSet có ngữ nghĩa volatile cho thao tác nguyên tử. Các biến thể Acquire/Release cho phép chọn ordering phù hợp khi thuật toán đã được thiết kế theo memory mode yếu hơn.

Atomicity và ordering là hai thuộc tính liên quan nhưng khác nhau. Một thao tác có thể nguyên tử mà không cung cấp ordering mạnh cho các biến khác. Đọc kỹ memory semantics của từng phương thức thay vì suy luận từ chữ "atomic".

Không phải mọi VarHandle đều hỗ trợ mọi access mode. Có thể kiểm tra bằng isAccessModeSupported(). Nếu mode không được hỗ trợ, lời gọi sẽ ném UnsupportedOperationException.

## 11. Memory fence

VarHandle cung cấp các fence tĩnh để kiểm soát thứ tự bộ nhớ ở mức thấp:

- fullFence(): ngăn load/store trước fence bị quan sát như thể chuyển xuống sau fence và ngược lại.
- acquireFence(): bảo đảm các load trước fence không bị chuyển xuống sau fence và các load/store sau fence không bị chuyển lên trước theo quy tắc acquire.
- releaseFence(): bảo đảm các load/store trước fence không bị chuyển xuống sau fence.
- loadLoadFence(): giữ thứ tự giữa các load.
- storeStoreFence(): giữ thứ tự giữa các store.

Ví dụ gọi fence:

~~~java
VarHandle.releaseFence();
// Publish hoặc thực hiện thao tác theo giao thức đã thiết kế.
VarHandle.acquireFence();
~~~

Fence không tự tạo một giao thức đồng bộ hoàn chỉnh và không thay thế việc phối hợp giữa thread. Cần có biến/cơ chế truyền tín hiệu tương ứng để các thread thiết lập quan hệ ordering.

Trong phần lớn code ứng dụng, ưu tiên access mode có ý nghĩa rõ ràng như setRelease/getAcquire hoặc setVolatile/getVolatile. Dùng fence riêng khi đã hiểu chính xác thứ tự cần bảo vệ và có lý do cụ thể để tách fence khỏi access.

## 12. Chọn memory mode theo tình huống

| Tình huống | Mode thường phù hợp |
|---|---|
| Dữ liệu chỉ dùng trong một thread | Plain |
| Cần atomic/coherent access cho cùng một biến, không publish dữ liệu khác | Opaque |
| Producer công bố dữ liệu rồi cập nhật cờ | setRelease |
| Consumer đọc cờ rồi đọc dữ liệu đã công bố | getAcquire |
| Cờ trạng thái cần ngữ nghĩa volatile dễ hiểu | setVolatile/getVolatile |
| Cần cập nhật biến nguyên tử có điều kiện | compareAndSet hoặc compareAndExchange |
| Cần cộng biến dùng chung nguyên tử | getAndAdd hoặc AtomicInteger/AtomicLong |
| Cần bảo vệ một invariant qua nhiều biến | synchronized hoặc Lock thường dễ kiểm chứng hơn |

Không chọn mode chỉ dựa trên giả định rằng mode yếu hơn luôn nhanh hơn. Hãy đo bằng benchmark phù hợp nếu hiệu năng là mục tiêu, và kiểm tra tính đúng đắn của giao thức trước.

## 13. Lỗi thường gặp

- **Dùng plain cho dữ liệu chia sẻ mà không đồng bộ:** không có happens-before giữa writer và reader; reader có thể thấy giá trị cũ.
- **Dùng opaque để publish payload:** opaque chỉ bảo đảm coherence trên cùng biến, không ordering payload với cờ.
- **Đảo chiều acquire/release:** writer cần setRelease; reader cần getAcquire trên cùng biến tín hiệu.
- **Cho rằng acquire/release tạo total order toàn cục:** cặp này cung cấp ordering phù hợp, không có total order như volatile operations.
- **Cho rằng volatile làm count++ nguyên tử:** volatile chỉ bảo đảm ngữ nghĩa truy cập; phép đọc rồi ghi vẫn có thể bị tranh chấp.
- **Trộn các access mode tùy ý trên cùng biến:** mode của từng lời gọi có thể khác nhau; modifier volatile tại khai báo không nâng mode plain thành volatile.
- **Dùng plain cho long/double và giả định luôn atomic:** hợp đồng plain không bảo đảm bitwise atomic cho mọi nền tảng.
- **Đọc payload trước khi acquire:** các thao tác đọc trước acquire không được hưởng ordering mà acquire tạo cho các thao tác sau nó.
- **Dùng fence mà không có giao thức truyền tín hiệu:** fence một mình không bảo đảm thread khác đã quan sát trạng thái cần thiết.
- **Dựa vào một stress test không thấy lỗi:** race có thể khó tái hiện; cần lập luận theo JMM và dùng công cụ kiểm thử concurrency phù hợp.
- **Chọn mode yếu chỉ vì hiệu năng:** mode yếu hơn đòi hỏi giao thức chính xác; sai ordering có thể tạo lỗi khó tái hiện.

## 14. Ghi nhớ

Plain là truy cập thông thường, không tạo ordering liên luồng. Opaque bổ sung atomicity và coherence trên cùng biến nhưng không sắp thứ tự biến khác. Release giữ các thao tác trước lần ghi ở phía trước; acquire giữ các thao tác sau lần đọc ở phía sau và phối hợp với release tương ứng để công bố dữ liệu. Volatile cung cấp ngữ nghĩa volatile cùng total order giữa các volatile operations. VarHandle access mode ghi đè ordering ở khai báo biến, vì vậy phải dùng nhất quán theo giao thức. Với publication, dùng setRelease/getAcquire hoặc setVolatile/getVolatile; với cập nhật nguyên tử, dùng CAS/getAndAdd; với invariant phức tạp, cân nhắc khóa để dễ kiểm chứng.

## 15. Tài liệu tham khảo

- [VarHandle – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java Language Specification – Threads and Locks, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [JEP 193: Variable Handles](https://openjdk.org/jeps/193)
