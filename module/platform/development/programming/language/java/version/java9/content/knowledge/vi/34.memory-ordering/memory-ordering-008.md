# Phân biệt hàng rào bộ nhớ với tính nguyên tử của thuật toán

Trong lập trình đa luồng, hai vấn đề thường bị nhầm lẫn là **thứ tự quan sát thao tác bộ nhớ** và **tính nguyên tử của một phép cập nhật**. Memory fence kiểm soát những thao tác đọc/ghi nào được phép quan sát trước hoặc sau một ranh giới. Atomic operation bảo đảm một thao tác cập nhật trên một biến diễn ra như một đơn vị không thể bị xen giữa bởi cập nhật cạnh tranh.

Một hàng rào bộ nhớ không khóa thread, không giữ độc quyền biến và không biến chuỗi đọc–tính toán–ghi thành một thao tác nguyên tử. Muốn bảo vệ một thuật toán, phải xác định invariant cần giữ và dùng primitive phù hợp: CAS, atomic read-modify-write, lock, synchronized hoặc một cấu trúc dữ liệu đồng thời đã được thiết kế đúng.

## 1. Ba khái niệm cần tách biệt

### Ordering – thứ tự bộ nhớ

Ordering mô tả các ràng buộc về cách thao tác đọc/ghi được quan sát giữa các thread. Compiler và CPU có thể tối ưu hoặc sắp xếp lại thao tác nếu kết quả vẫn tuân thủ Java Memory Model. Vì vậy thứ tự dòng lệnh trong source không phải lúc nào cũng đủ để suy ra thứ tự quan sát của thread khác.

Fence và các access mode như acquire/release đặt ra những ràng buộc ordering.

### Visibility – khả năng nhìn thấy dữ liệu

Visibility mô tả khi nào một thread có thể quan sát giá trị được thread khác ghi. Một giao thức đồng bộ đúng cần một cơ chế truyền tín hiệu hoặc quan hệ đồng bộ phù hợp, chẳng hạn volatile access, lock/unlock hoặc release/acquire trên cùng biến điều phối.

Chỉ gọi một fence không tạo ra một thông điệp, không bảo đảm thread khác sẽ đọc được một cờ bất kỳ và không thay thế giao thức truyền dữ liệu.

### Atomicity – tính không thể chia cắt

Atomicity bảo đảm một thao tác được quan sát như một đơn vị duy nhất. Ví dụ, VarHandle.compareAndSet hoặc getAndAdd thực hiện một read-modify-write nguyên tử trên một biến được hỗ trợ.

Atomicity của một thao tác không tự động bảo vệ cả thuật toán gồm nhiều thao tác hoặc nhiều biến. Phải xác định rõ ranh giới mà ứng dụng yêu cầu không bị xen giữa.

## 2. Memory fence làm gì?

Java 9 bổ sung các fence method static trên VarHandle. Chúng đặt ràng buộc về việc các thao tác đọc/ghi ở hai phía của fence có thể bị quan sát theo thứ tự nào.

| Fence | Ràng buộc |
|---|---|
| fullFence() | Load và store trước fence không được reorder qua các load và store sau fence |
| acquireFence() | Load trước fence không được reorder qua load và store sau fence |
| releaseFence() | Load và store trước fence không được reorder qua store sau fence |
| loadLoadFence() | Load trước fence không được reorder qua load sau fence |
| storeStoreFence() | Store trước fence không được reorder qua store sau fence |

Có thể hình dung fence là một ranh giới ordering trong luồng thực thi của thread đang gọi. Nó không đọc hay ghi một biến cụ thể và không tự tạo ra mutual exclusion.

Ví dụ gọi fence:

~~~java
VarHandle.releaseFence();
// Các store sau đây không được đưa lên trước fence theo ràng buộc release.
publishFlag = true;
~~~

Đoạn trên chỉ minh họa vị trí của fence. Một giao thức trao đổi dữ liệu thực tế còn cần cách công bố và quan sát publishFlag đúng theo Java Memory Model; không dùng một biến cờ plain bị data race rồi suy luận rằng fence đơn lẻ bảo đảm thread khác sẽ nhìn thấy nó.

### fullFence

fullFence đặt ràng buộc mạnh nhất trong nhóm fence của VarHandle: load và store ở trước không được reorder với load và store ở sau. Tài liệu API mô tả memory ordering effect tương thích với sequentially consistent atomic fence, khi bỏ qua các khác biệt ngữ nghĩa giữa Java và C/C++.

fullFence hữu ích trong các cấu trúc đồng bộ mức thấp khi thuật toán đã xác định rõ các thao tác liên lạc và cần một ranh giới ordering mạnh. Không nên thêm fullFence tùy tiện vào code thông thường; nó không thay thế lock, CAS hoặc volatile protocol.

### acquireFence

acquireFence ngăn load trước fence bị reorder qua load/store sau fence. Nó thường được dùng ở phía đọc của một giao thức công bố dữ liệu, khi một thao tác đọc/điều kiện trước đó đã xác định dữ liệu cần được quan sát.

### releaseFence

releaseFence ngăn load/store trước fence bị reorder qua store sau fence. Nó thường được dùng ở phía ghi khi dữ liệu được chuẩn bị trước khi công bố trạng thái.

### loadLoadFence và storeStoreFence

Hai fence này chỉ ràng buộc một số cặp thao tác cụ thể:

- loadLoadFence giữ thứ tự giữa các load.
- storeStoreFence giữ thứ tự giữa các store.

Chúng yếu hơn fullFence và chỉ hữu ích khi thuật toán cần đúng chính xác ràng buộc đó. Nếu chưa có chứng minh về memory ordering, đừng tự thay fullFence bằng một fence yếu hơn chỉ để tối ưu.

## 3. Fence không làm phép cập nhật trở thành atomic

Giả sử hai thread cùng tăng một biến counter. Phép tăng thông thường gồm ba bước:

1. Đọc giá trị hiện tại.
2. Tính giá trị mới bằng cách cộng 1.
3. Ghi giá trị mới.

Hai thread có thể xen kẽ như sau:

| Bước | Thread 1 | Thread 2 |
|---|---|---|
| 1 | Đọc counter = 0 | |
| 2 | | Đọc counter = 0 |
| 3 | Tính 1 | Tính 1 |
| 4 | Ghi counter = 1 | |
| 5 | | Ghi counter = 1 |

Kết quả cuối là 1 dù có hai lần tăng. Đây là lost update.

Đặt fullFence giữa các bước không biến ba bước thành một thao tác nguyên tử. Cả hai thread vẫn có thể đọc cùng giá trị trước khi thread nào ghi kết quả. Fence ràng buộc ordering; nó không giành quyền sở hữu counter và không ngăn thread khác xen vào.

Tương tự, khai báo biến là volatile cũng không làm counter++ trở thành atomic. Volatile bảo đảm semantics của từng lần đọc/ghi volatile, còn phép tăng vẫn là chuỗi đọc–tính–ghi riêng biệt.

## 4. Dùng atomic read-modify-write cho một biến

Nếu cần tăng một biến nguyên tử, dùng thao tác read-modify-write phù hợp. Với VarHandle:

~~~java
int previous = (int) COUNTER.getAndAdd(1);
~~~

getAndAdd thực hiện phép cộng và trả về giá trị trước cập nhật như một thao tác nguyên tử trên biến được hỗ trợ. compareAndSet thực hiện cập nhật có điều kiện nguyên tử:

~~~java
boolean changed = (boolean) COUNTER.compareAndSet(
        expectedValue,
        newValue
);
~~~

Nếu cần tính giá trị mới dựa trên giá trị hiện tại, có thể dùng CAS loop:

~~~java
int current;
int next;

do {
    current = (int) COUNTER.getVolatile();
    next = calculateNext(current);
} while (!COUNTER.compareAndSet(current, next));
~~~

Mỗi compareAndSet là nguyên tử. Nếu thread khác cập nhật trước, CAS thất bại và vòng lặp đọc lại giá trị mới rồi tính lại. Cách này có thể bảo vệ một biến hoặc một trạng thái được gói trong một biến tham chiếu, nhưng phải kiểm tra tính đúng đắn của hàm calculateNext, khả năng retry và các tác dụng phụ.

Không đặt thao tác có side effect không thể lặp bên trong phép tính của CAS loop. Hàm tính next có thể được chạy nhiều lần khi CAS thất bại.

## 5. Khi invariant gồm nhiều bước hoặc nhiều biến

Một thao tác nguyên tử trên một biến chưa chắc bảo vệ được invariant liên quan đến nhiều biến.

Ví dụ một tài khoản có balance và reservedAmount. Quy tắc nghiệp vụ có thể yêu cầu:

- balance không âm;
- reservedAmount không vượt balance;
- cập nhật cả hai giá trị như một giao dịch.

Nếu cập nhật hai field riêng biệt bằng hai CAS độc lập, thread khác có thể quan sát trạng thái trung gian giữa hai lần cập nhật. Fence không biến hai CAS thành một giao dịch nguyên tử.

Các lựa chọn phổ biến:

**Dùng synchronized hoặc Lock**

~~~java
synchronized (accountLock) {
    if (balance - amount >= reservedAmount) {
        balance -= amount;
        reservedAmount += amount;
    }
}
~~~

Mọi đường đọc/ghi liên quan đến invariant phải dùng cùng lock. Nếu một thread bỏ qua lock, vùng bảo vệ không còn đầy đủ.

**Gói trạng thái vào một object bất biến và CAS một reference**

~~~java
State current;
State next;

do {
    current = (State) STATE_HANDLE.getVolatile(this);
    next = current.reserve(amount);
} while (!STATE_HANDLE.compareAndSet(this, current, next));
~~~

Nếu State bất biến và toàn bộ invariant được biểu diễn trong một object, CAS trên reference có thể thay thế toàn bộ trạng thái như một đơn vị. Cần chú ý ABA, retry và việc không để lộ object mutable có thể bị sửa sau khi công bố.

**Dùng cấu trúc dữ liệu đồng thời có sẵn**

Concurrent collections, AtomicReference, AtomicInteger, LongAdder, locks hoặc các abstraction phù hợp thường an toàn và dễ bảo trì hơn tự lắp ghép fence. Chọn công cụ theo invariant, contention và semantics cần có.

## 6. Fence, volatile và acquire/release khác nhau thế nào?

| Cơ chế | Ordering / visibility | Atomicity |
|---|---|---|
| Plain get/set | Không tạo quan hệ đồng bộ liên thread | Một lần đọc/ghi có giới hạn atomicity theo kiểu và nền tảng |
| Volatile read/write | Có volatile visibility và ordering | Từng lần đọc/ghi volatile là atomic; chuỗi nhiều thao tác không tự atomic |
| getAcquire / setRelease | Ordering một chiều quanh access trên cùng biến điều phối | Không tự biến chuỗi thao tác thành atomic |
| Fence | Đặt ràng buộc ordering trong thread | Không cung cấp atomic read-modify-write |
| compareAndSet / getAndAdd | Có memory semantics theo access mode | Atomic cho thao tác trên một biến |
| synchronized / Lock | Visibility qua quan hệ unlock-lock và ordering | Bảo vệ critical section nếu mọi thread tuân thủ cùng lock |

Release/acquire access mode thường dễ gắn với biến điều phối hơn là tự đặt fence rời rạc.

Ví dụ công bố dữ liệu bằng một cờ:

~~~java
final class MessageBox {
    int payload;
    boolean ready;

    static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup().findVarHandle(
                    MessageBox.class,
                    "ready",
                    boolean.class
            );
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    void publish(int value) {
        payload = value;
        READY.setRelease(this, true);
    }

    int consume() {
        if ((boolean) READY.getAcquire(this)) {
            return payload;
        }
        return -1;
    }
}
~~~

Khi getAcquire quan sát giá trị được công bố bằng setRelease trên cùng biến ready, các ghi trước release được sắp thứ tự trước các đọc sau acquire. Đây là giao thức công bố một lần; nếu cần reset ready và tái sử dụng nhiều vòng, phải thiết kế state transition và đồng bộ hóa cho từng vòng.

Ví dụ này dùng access mode release/acquire trên biến điều phối. Nó không chứng minh rằng chỉ gọi releaseFence/acquireFence mà không có một biến hoặc sự kiện liên lạc là đủ để truyền dữ liệu.

## 7. Các lỗi suy luận thường gặp

**Thấy fullFence rồi kết luận không còn race condition**

Fence không loại bỏ interleaving và không khóa dữ liệu. Hai thread vẫn có thể cùng đọc một giá trị rồi ghi kết quả cạnh tranh.

**Cho rằng volatile counter++ là atomic**

Mỗi volatile read/write có semantics volatile, nhưng phép tăng vẫn là read-modify-write gồm nhiều bước. Dùng getAndAdd, AtomicInteger hoặc lock.

**Dùng fence thay cho happens-before protocol**

Fence đơn lẻ không tự thông báo cho thread khác rằng dữ liệu đã sẵn sàng. Cần một biến điều phối hoặc primitive đồng bộ thích hợp.

**Cho rằng CAS một field bảo vệ nhiều field**

CAS chỉ nguyên tử cho biến mà handle tham chiếu. Nếu invariant trải trên nhiều biến, dùng lock hoặc gói trạng thái thành một giá trị duy nhất có thể thay thế nguyên tử.

**Dùng fence quá mạnh ở mọi nơi**

fullFence có thể hạn chế tối ưu hóa nhiều hơn cần thiết. Ưu tiên volatile, acquire/release hoặc lock có hợp đồng rõ; chỉ dùng fence mức thấp khi có lý do và kiểm chứng theo Java Memory Model.

**Trộn plain, volatile và các access mode khác nhau tùy tiện**

Access mode của VarHandle quyết định memory semantics của lần truy cập, kể cả khi field khai báo volatile. Trộn mode trên cùng biến cần phân tích cẩn thận; không suy luận rằng khai báo volatile sẽ tự nâng mọi plain access thành volatile access.

**Dùng CAS loop với side effect**

CAS có thể thất bại và chạy lại. Chỉ tính trạng thái mới trong loop; thực hiện gửi email, ghi file hoặc side effect không lặp sau khi cập nhật thành công.

## 8. Cách chọn cơ chế theo yêu cầu

| Yêu cầu | Cơ chế nên xem xét |
|---|---|
| Một biến đếm cần tăng nguyên tử | VarHandle.getAndAdd, AtomicInteger hoặc LongAdder |
| Cập nhật có điều kiện trên một biến | compareAndSet hoặc compareAndExchange |
| Công bố dữ liệu giữa writer và reader | volatile flag hoặc setRelease/getAcquire trên cùng biến |
| Bảo vệ invariant nhiều bước trên nhiều field | synchronized hoặc Lock |
| Thay thế toàn bộ trạng thái bất biến | AtomicReference hoặc VarHandle CAS trên reference |
| Ràng buộc ordering trong thuật toán lock-free mức thấp | Fence phù hợp, kết hợp với giao thức đồng bộ đã chứng minh |

Trước khi dùng fence, hãy viết ra invariant và quan hệ giữa thread: thread nào ghi dữ liệu, thread nào đọc, biến nào truyền tín hiệu, access mode nào được dùng và điều gì xảy ra khi có nhiều writer. Nếu chưa mô tả được giao thức, việc thêm fence không làm thuật toán tự trở nên đúng.

## 9. Ví dụ chạy được với Java 17+

Tạo file **FenceVsAtomicityDemo.java**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FenceVsAtomicityDemo {
    private static int counter;
    private static final VarHandle COUNTER;

    static {
        try {
            COUNTER = MethodHandles.lookup().findStaticVarHandle(
                    FenceVsAtomicityDemo.class,
                    "counter",
                    int.class
            );
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) throws Exception {
        int workerCount = 4;
        int incrementsPerWorker = 100_000;
        ExecutorService executor =
                Executors.newFixedThreadPool(workerCount);

        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int worker = 0; worker < workerCount; worker++) {
                tasks.add(executor.submit(() -> {
                    for (int i = 0; i < incrementsPerWorker; i++) {
                        COUNTER.getAndAdd(1);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            executor.shutdown();
        }

        System.out.println("atomic increments: " + counter);

        VarHandle.fullFence();
        System.out.println("full fence invoked");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FenceVsAtomicityDemo.java
java FenceVsAtomicityDemo
~~~

Kết quả stdout:

~~~text
atomic increments: 400000
full fence invoked
~~~

Có bốn thread, mỗi thread tăng counter 100.000 lần. getAndAdd là thao tác read-modify-write nguyên tử nên tổng cuối là 400.000.

Lời gọi fullFence ở cuối chỉ minh họa API fence. Nó không tham gia vào việc bảo vệ counter và không phải lý do khiến tổng tăng chính xác. Nếu thay getAndAdd bằng chuỗi get rồi set, thêm fullFence giữa hai thao tác vẫn không ngăn lost update.

## 10. Checklist trước khi dùng fence hoặc atomic

- Xác định vấn đề là ordering, visibility, atomicity hay invariant nhiều biến.
- Xác định biến hoặc trạng thái nào được chia sẻ giữa các thread.
- Chọn access mode theo memory semantics cần có.
- Dùng getAndAdd hoặc CAS cho cập nhật nguyên tử trên một biến.
- Dùng lock khi cần bảo vệ một critical section nhiều bước hoặc nhiều field.
- Nếu dùng release/acquire, bảo đảm hai phía phối hợp trên cùng biến điều phối.
- Không coi fence là lock, cache flush hoặc atomic read-modify-write.
- Không giả định volatile làm cho toán tử ++ trở thành atomic.
- Phân tích CAS retry, ABA và side effect nếu dùng thuật toán lock-free.
- Kiểm thử các interleaving quan trọng và ghi rõ invariant mà test phải bảo vệ.

## Tài liệu tham khảo

- [VarHandle — Java SE 24 API: memory fence methods](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [VarHandle — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/VarHandle.html)
- [Java Language Specification — Threads and Locks / Memory Model](https://docs.oracle.com/javase/specs/jls/se24/html/jls-17.html)
