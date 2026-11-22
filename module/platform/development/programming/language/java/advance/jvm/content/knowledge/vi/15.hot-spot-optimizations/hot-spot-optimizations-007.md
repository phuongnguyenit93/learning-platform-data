# Loại bỏ khóa không cần thiết khi đối tượng không được chia sẻ

## 1. Bài toán: tại sao mã có `synchronized` đôi khi chạy mà không cần thực thi khóa?

Trong Java, từ khóa **`synchronized`** cung cấp cơ chế khóa monitor và các quan hệ **happens-before** theo Java Memory Model (JMM). Việc có keyword `synchronized` trong Java source/bytecode **không có nghĩa mọi lần thực thi trên HotSpot bắt buộc thực hiện đầy đủ thao tác monitor tại mức machine code**.

Khi **HotSpot C2 JIT compiler** chứng minh một monitor chỉ bảo vệ một đối tượng **không thể được chia sẻ theo cách dẫn tới cạnh tranh giữa các threads**, nó có thể **loại bỏ những thao tác khóa không cần thiết** (*lock elimination*, cũng gọi là *lock elision* trong bối cảnh này).

Ví dụ cơ bản:

```java
static int calculate(int x) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return x * 3 + 1;
    }
}
```

Ở mức source:

1. Mỗi lời gọi `calculate` tạo một monitor object mới.
2. `privateLock` không được trả ra ngoài, không ghi vào field/static field và không truyền cho thread khác.
3. Không có thread khác có reference hợp lệ để yêu cầu khóa **chính monitor object đó** trong thời gian đối tượng được dùng.
4. HotSpot có thể chứng minh điều kiện và bỏ thao tác **monitor enter/exit** trong optimized machine code.

Điều này **không** có nghĩa Java bỏ qua `synchronized` tùy tiện. Đây là một phép tối ưu **chỉ hợp lệ khi compiler có đủ bằng chứng**, và phải bảo toàn mọi hành vi quan sát được của chương trình.

### 1.1. Kết luận trước khi đi sâu

- **Đối tượng không thoát và không bị chia sẻ:** lock có thể là thừa; C2 có thể loại bỏ.
- **Đối tượng được chia sẻ giữa các threads:** synchronization có thể cần cho **mutual exclusion, atomicity và visibility**; không tự được bỏ.
- **Bytecode vẫn có monitor instructions:** JIT có thể loại chúng khỏi **machine code tối ưu**, không cần sửa tệp `.class`.
- **Không được viết logic phụ thuộc việc tối ưu có xảy ra:** HotSpot có thể không loại khóa khi không inline đủ, profile chưa nóng hoặc compiler không chứng minh được.
- **Không phải cùng một thứ với biased locking, lock coarsening hay scalar replacement**, dù các tối ưu này có liên quan.

Bài này tập trung HotSpot/JDK 17+ (nhất là C2) và phân biệt rõ **ngữ nghĩa Java bắt buộc** với **tối ưu implementation-specific**.

## 2. Monitor và `synchronized` hoạt động như thế nào về mặt ngữ nghĩa?

Java cung cấp hai cách phổ biến dùng intrinsic monitor:

```java
synchronized (someLock) {
    updateSharedState();
}
```

và:

```java
synchronized void update() {
    // khóa implicit monitor của this
}
```

Đây là **snippets minh họa**, chưa khai báo `someLock`, `updateSharedState` hoặc class đầy đủ.

### 2.1. Mutual exclusion

Mỗi Java object có một monitor liên quan về mặt ngữ nghĩa. Nếu hai threads cố **acquire cùng một monitor** theo cơ chế `synchronized`, JVM phải tuân theo mutual exclusion và monitor rules: tại một thời điểm một thread giữ quyền sở hữu monitor đó (với khả năng **reentrant** của cùng thread).

Điều này giúp bảo vệ các thao tác *read-modify-write* trên dữ liệu chia sẻ, chẳng hạn `count++` không phải phép tăng atomic khi thiếu đồng bộ phù hợp.

### 2.2. Visibility và happens-before

Việc **unlock monitor M** *happens-before* lần **lock M** tiếp theo theo các quy tắc của JMM. Nhờ đó các writes được publish đúng qua monitor có thể được thread acquire cùng monitor quan sát theo quan hệ happens-before.

Điều rất quan trọng: chỉ cần monitor dùng riêng cho một object mà **không thể có thread thứ hai tham gia giao tiếp qua monitor đó**, các hiệu ứng đồng bộ với thread khác có thể **không mang giá trị thực**. Compiler có thể loại bỏ thao tác monitor khi chứng minh các ràng buộc liên quan không cần thiết, **nhưng không được loại bỏ các synchronizations mà chương trình hợp lệ dùng để chia sẻ dữ liệu**.

### 2.3. Reentrancy

Một thread đang giữ monitor có thể acquire **cùng monitor** thêm lần nữa; JVM phải quản lý mức reentrant của synchronization đúng ngữ nghĩa.

Ví dụ:

```java
synchronized (lock) {
    synchronized (lock) {
        operation();
    }
}
```

Đây là **snippet minh họa**; `lock` và `operation` phải được định nghĩa. Nếu lock object thực sự được chia sẻ, các thao tác khóa có thể cần được giữ về mặt ngữ nghĩa; các tối ưu **nested lock elimination** là chủ đề riêng, không chứng minh monitor là thread-private.

### 2.4. Đồng bộ vẫn quan trọng ngay cả khi không thấy data race trong thử nghiệm

Một chương trình có thể “chạy đúng” 1.000 lần thiếu khóa nhưng vẫn có data race. HotSpot **không được** suy luận khóa thừa chỉ vì một đợt benchmark chưa có thread tranh chấp.

Sự khác biệt giữa **không có tranh chấp được quan sát** và **compiler có bằng chứng đối tượng không thể chia sẻ** là trọng tâm của lock elimination.

## 3. Phân biệt lock object và dữ liệu được bảo vệ

Trong code:

```java
static final Object LOCK = new Object();
static int counter;

static void increment() {
    synchronized (LOCK) {
        counter++;
    }
}
```

`LOCK` là **đối tượng monitor**, còn `counter` là **dữ liệu được bảo vệ**. Vì `LOCK` nằm trong static field, nhiều threads có thể truy cập cùng instance monitor.

Đừng suy luận “`LOCK` không có fields nên JIT chắc loại bỏ nó”. Không có fields không làm một monitor chia sẻ trở thành thừa. `synchronized` có tác dụng **theo identity của monitor**, không theo số fields trong object.

Ngược lại:

```java
static int computeLocally(int x) {
    Object lock = new Object();
    synchronized (lock) {
        return x + 7;
    }
}
```

monitor này được tạo trong method, không được public/publish, nên là ứng viên tốt cho loại bỏ monitor operations. Kết quả không liên quan thread khác vì họ không thể acquire chính object đó qua bất kỳ reference nào.

### 3.1. Một lỗi thiết kế: tạo khóa mới mỗi lần để bảo vệ static state

```java
static int unsafeCount;

static void unsafeIncrement() {
    Object lock = new Object();
    synchronized (lock) {
        unsafeCount++; // KHÔNG bảo vệ shared state giữa các threads
    }
}
```

Đây là **anti-pattern**, không phải ví dụ thread-safe. Mỗi lời gọi dùng **một object khác nhau**. Hai threads không đồng bộ trên **cùng monitor**, nên `unsafeCount++` vẫn có data race/lost updates.

HotSpot có thể loại khóa, nhưng **lỗi correctness đã tồn tại trong source**. Đừng giải quyết bằng cách “tắt escape analysis để giữ monitor”, vì monitor mới tạo mỗi lần vẫn không bảo vệ static data giữa threads.

Đúng hơn là dùng một **monitor chung** hoặc cơ chế atomic thích hợp:

```java
static final Object COUNT_LOCK = new Object();
static int count;

static void safeIncrement() {
    synchronized (COUNT_LOCK) {
        count++;
    }
}
```

Để bảo vệ cùng tài nguyên, các threads phải đồng bộ trên **cùng monitor object**.

## 4. Escape analysis đặt điều kiện để bỏ khóa

Để quyết định có thể bỏ monitor enter/exit, C2 phải chứng minh khóa **không cần thiết để bảo toàn đồng bộ hóa và observable behavior**. HotSpot escape analysis (EA) giúp nhận diện object có thể được chia sẻ hoặc thoát ra ngoài compiled scope. Trong thuật ngữ implementation, **NoEscape**, **ArgEscape** và **GlobalEscape** mô tả các mức độ thoát khác nhau; chúng **không** là bảo đảm public Java API rằng monitor chắc chắn được loại.

Một biến local vẫn có thể trỏ tới object đã được công bố ra static field; ngược lại, compiler có thể nhìn xuyên helper calls khi **inlining** mở rộng phạm vi phân tích. Vì vậy “local object” không mặc định có nghĩa “monitor không cần thiết”, và việc object **không escape khỏi thread** vẫn chưa đủ nếu compiler không chứng minh được một số điều kiện khác.

**Điểm riêng của bài lock elimination:** compiler có thể bỏ **các thao tác khóa không quan sát được** nhưng phải giữ quy tắc `synchronized`, exceptions, happens-before và identity khi thực sự có chia sẻ. Scalar replacement có thể hỗ trợ hoặc đi kèm, song việc một allocation bị loại **không đồng nhất** với một monitor bị loại; bài trước đã tập trung vào trạng thái escape và mô hình object/scalars.

## 5. Quá trình HotSpot loại bỏ khóa

Một sơ đồ hợp lý cho ví dụ private monitor:

```text
Java source
  Object lock = new Object();
  synchronized (lock) { result = x * 3 + 1; }
                 |
                 v
javac tạo bytecode chứa monitorenter/monitorexit
                 |
                 v
HotSpot interpreter/C1/C2 execution
                 |
            method trở nên hot
                 |
                 v
       C2 inlining / escape analysis
                 |
      compiler có chứng minh được
      object không thể global escape?
            /                \
          Có                 Không
          |                    |
          v                    v
   Có thể loại bỏ         Giữ đủ monitor
   monitor operations     semantics runtime
          |
          +-- object scalar replace được?
                /           \
              Có             Không
              |                |
              v                v
       Có thể bỏ object    Object allocation
       allocation           vẫn có thể tồn tại
```

Đây là mô hình **khái niệm**, không hứa mọi HotSpot release thực hiện các passes đúng theo thứ tự đơn giản trên. EA có thể thất bại do giới hạn phân tích, call không được inline, đường exception hoặc điều kiện khác.

### 5.1. Compiler loại bỏ cái gì?

Khi an toàn, compiler có thể loại chi phí:

- Monitor enter/exit ở optimized path.
- Các checks/bookkeeping liên quan monitor nếu chứng minh là thừa.
- Trong trường hợp object được scalar replace, cả allocation của monitor object.
- Những thao tác nội bộ liên quan object header/locking mà không còn cần.

Nhưng việc **sinh/loại machine instructions** phụ thuộc JIT build. Java source và bytecode vẫn có `synchronized`/`monitorenter`/`monitorexit`.

### 5.2. Vẫn phải giữ tính đúng của exceptions

Nếu code trong critical section ném exception, Java compiler sinh các đường exception để **nhả monitor** theo semantics. JIT có thể tối ưu những đường được chứng minh không cần monitor, nhưng exception propagation phải đúng.

Không được giả định xóa monitor đồng nghĩa bỏ qua exception handling hoặc các side effects của body.

### 5.3. Compile không phải chạy interpreter và C2 cùng một lúc

Phương thức có thể ban đầu interpreted, rồi C1, cuối cùng C2. **Không có guarantee JIT level 4** sau đúng 10.000 invocations. Vì vậy cùng một source code có thể thấy runtime chi phí lock khác trong warm-up và steady state.

## 6. `synchronized` ở bytecode vẫn hiện hữu

Xem đoạn method:

```java
static int localCriticalSection(int value) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return value * 3 + 1;
    }
}
```

Biên dịch với `javac`, dùng:

```bash
javap -c -p LockElisionDemo
```

Đoạn bytecode cho block synchronized có **`monitorenter`** và **`monitorexit`**, cùng exception-handling path để bảo đảm monitor exit khi có lỗi. Một mẫu logic:

```text
... new java/lang/Object
... dup
... invokespecial java/lang/Object.<init>
... astore ...
... monitorenter
... iload ...
... imul
... iadd
... monitorexit
... ireturn
... monitorexit   // nhánh xử lý exception
... athrow
```

**Đây là sơ đồ diễn giải, KHÔNG phải dump bytecode đầy đủ từ một phiên bản compiler cụ thể.** Những instruction offsets/local slots/exception table entries thay đổi khi code/`javac` thay đổi.

### 6.1. Tại sao `javap` không chứng minh lock vẫn hoạt động ở CPU?

`javap` chỉ đọc **class file bytecode**. C2 compiled machine code được tạo **khi JVM đang chạy**; tối ưu đó không sửa class file. Vì vậy thấy `monitorenter` trong `javap` **không bác bỏ lock elimination ở JIT**.

### 6.2. Tại sao cùng bytecode có thể chạy khác?

Interpreter cần thực thi monitor semantics theo bytecode. C2 JIT có thể xem toàn bộ control flow và escape state, rồi chọn đường machine code tương đương nhưng rẻ hơn.

Một chương trình chạy với `-Xint` hay JIT disabled có thể có chi phí locking khác; không có yêu cầu hai execution modes phải phát cùng số machine instructions, chỉ phải bảo đảm Java semantics.

## 7. Ví dụ Java 17+ chạy được: private monitor và shared monitor

Tạo tệp **`LockElisionDemo.java`**:

```java
public final class LockElisionDemo {
    private static final Object SHARED_LOCK = new Object();
    private static int sharedCount;
    private static volatile long checksumSink;

    static int localCriticalSection(int value) {
        Object privateLock = new Object();
        synchronized (privateLock) {
            return value * 3 + 1;
        }
    }

    static void incrementShared() {
        synchronized (SHARED_LOCK) {
            sharedCount++;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long total = 0;

        for (int i = 0; i < 100_000; i++) {
            total += localCriticalSection(i);
        }

        checksumSink = total;
        System.out.println("local checksum=" + checksumSink);

        Thread first = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                incrementShared();
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                incrementShared();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("shared count=" + sharedCount);
        System.out.println("expected shared=40000");
    }
}
```

### 7.1. Biên dịch và chạy

Yêu cầu JDK 17 trở lên:

```bash
javac --release 17 LockElisionDemo.java
java LockElisionDemo
```

**Stdout chính xác khi chạy bình thường:**

```text
local checksum=14999950000
shared count=40000
expected shared=40000
```

Tệp Java này được biên dịch bằng `javac --release 17` và thực thi thành công trên HotSpot với các cấu hình mặc định, `-Xint`, `-XX:-DoEscapeAnalysis` và `-XX:-EliminateLocks`. **Mọi cấu hình đều cho cùng ba dòng trên.**

### 7.2. Vì sao checksum bằng 14.999.950.000?

`localCriticalSection(i)` trả `3*i + 1` với `i` từ 0 tới 99.999. Tổng:

```text
sum(i=0..99999) (3*i + 1)
= 3 * (99999 * 100000 / 2) + 100000
= 3 * 4,999,950,000 + 100000
= 14,999,950,000
```

Đây là phép toán trong Java `long total` nên không bị overflow ở tổng này. Trong `localCriticalSection`, phép `value * 3 + 1` cũng chưa vượt giới hạn `int` với input của chương trình.

### 7.3. Vì sao sharedCount chính xác 40.000?

Hai threads cùng gọi `incrementShared()` 20.000 lần. Mỗi lần tăng đều nằm trong:

```java
synchronized (SHARED_LOCK) {
    sharedCount++;
}
```

Vì cùng một **static final monitor object** được dùng, increments trên `sharedCount` được bảo vệ bằng mutual exclusion. Các lời gọi `Thread.join()` tạo quan hệ happens-before cần thiết để `main` đọc kết quả sau khi hai threads kết thúc.

**Nếu xóa khóa chung**, `sharedCount++` có data race và chương trình có thể bị mất cập nhật; không còn cơ sở bảo đảm kết quả là 40.000.

### 7.4. Một ví dụ có thể loại khóa; một ví dụ phải giữ semantics

- **`localCriticalSection`:** lock mới tạo, không được publish. Đây là **ứng viên tốt** cho HotSpot lock elimination.
- **`incrementShared`:** lock là object chung qua static field. Các threads có thể tranh chấp; JIT **không được phép loại monitor semantics** làm phép tăng mất tính atomic.

Lưu ý: **Stdout giống nhau không chứng minh machine code của localCriticalSection đã bỏ monitor thật**. Muốn xác nhận optimizer đã loại instructions, cần công cụ phân tích compiled code hoặc benchmark có kiểm soát cộng với bằng chứng hỗ trợ.

## 8. Các cờ HotSpot để quan sát và tạo đối chứng

### 8.1. Mặc định

```bash
java LockElisionDemo
```

HotSpot thường bật escape analysis và lock elimination cho optimizing compiler khi feature/build hỗ trợ. Đừng dựa hoàn toàn vào giả định mặc định; hãy kiểm tra flags hiện tại.

### 8.2. Tắt escape analysis

```bash
java -XX:-DoEscapeAnalysis LockElisionDemo
```

Cờ HotSpot này tắt escape analysis, có thể ảnh hưởng **nhiều tối ưu cùng lúc**, gồm scalar replacement và lock elimination. Vì thay nhiều cơ chế, **không dùng chênh lệch thời gian để quy toàn bộ tác động chỉ cho khóa**.

### 8.3. Tắt lock elimination

```bash
java -XX:-EliminateLocks LockElisionDemo
```

Tùy build/version, đây là cách tạo đối chứng **gần trực tiếp hơn** với những tối ưu liên quan lock. Cờ `EliminateLocks` của HotSpot có phạm vi implementation-specific, liên quan lock optimizations (gồm lock coarsening theo các bản source/flag descriptions). Vì vậy **không khẳng định nó tắt duy nhất một transformation và giữ nguyên mọi thứ khác**.

### 8.4. Chạy interpreter-only

```bash
java -Xint LockElisionDemo
```

Chế độ này yêu cầu thực thi Java bytecode bằng interpreter, không JIT compile bytecode ứng dụng. Nó là **đối chứng**, nhưng loại bỏ **mọi lợi ích JIT** chứ không chỉ lock elimination. Nếu `-Xint` chậm hơn, không thể kết luận toàn bộ sự chênh lệch là “chi phí synchronized”.

### 8.5. Kiểm tra flags thật trên runtime

```bash
java -XX:+PrintFlagsFinal -version
```

Các mục quan tâm gồm `DoEscapeAnalysis`, `EliminateLocks`, `TieredCompilation`. Hãy so khớp output theo JDK/vendor/architecture cụ thể.

### 8.6. Tại sao không mặc định dùng `-XX:+PrintEliminateLocks`?

Một số tài liệu cũ khuyên bật `PrintEliminateLocks` hoặc `PrintEscapeAnalysis`. Trong nhiều **production HotSpot builds**, đây là **non-product/debug-only flags**, không hoạt động dù có `-XX:+UnlockDiagnosticVMOptions`.

**Không hứa JDK 17 bản phát hành thông thường sẽ in được danh sách “eliminated lock” bằng flag đó**. Nếu cần xác nhận optimizer, dùng bản VM/tool có khả năng phân tích machine code, thử nghiệm JMH có kiểm soát, hoặc debug/non-product build được hỗ trợ.

## 9. Dùng `javap` và `PrintCompilation` đúng mục đích

### 9.1. `javap` chứng minh compiler đã tạo monitor bytecode

```bash
javap -c -p LockElisionDemo
```

Trong thử nghiệm với mã trên, `javap` hiển thị **`monitorenter`** và **`monitorexit`** trong các methods tương ứng. Đây là bằng chứng `synchronized` tồn tại ở bytecode, **không phải đo trực tiếp optimized JIT machine code**.

### 9.2. `PrintCompilation` xác nhận JIT đã chạy

```bash
java -XX:+PrintCompilation LockElisionDemo
```

Tìm các tên như:

```text
LockElisionDemo::localCriticalSection
LockElisionDemo::incrementShared
```

Trong một lần chạy thử trên HotSpot, log chứa các dòng kiểu:

```text
... 3 ... LockElisionDemo::localCriticalSection (25 bytes)
... 4 ... LockElisionDemo::localCriticalSection (25 bytes)
... 3 ... LockElisionDemo::incrementShared (25 bytes)
... 4 ... LockElisionDemo::incrementShared (25 bytes)
```

**Đây là ví dụ về phần ý nghĩa của các dòng log được quan sát, không phải output đầy đủ hoặc cố định.** Các số compile IDs, timestamps và thứ tự thay đổi tùy JVM. Level 3 thường là C1 với profiling, level 4 thường là C2.

### 9.3. Level 4 có chứng minh lock bị loại không?

**Không.** Level 4 chỉ chứng minh method được C2 compile trong lần chạy tương ứng, không cho biết mỗi `monitorenter` đã bị loại. Muốn chứng minh lock elimination ở một call site, cần thêm **quan sát compiled IR/assembly hoặc thông tin compiler phù hợp**.

### 9.4. Bytecode monitor và nmethod có thể khác

```text
javap:
  monitorenter / monitorexit có mặt trong class file
           |
           v
C2 optimized code:
  có thể vẫn giữ monitor operations
  HOẶC loại chúng nếu chứng minh được an toàn
```

Kết luận tối ưu phải dựa vào **compiled execution path thực tế**, không suy luận từ một cờ đang bật hay từ sự tồn tại của `synchronized` trong source.

## 10. Scalar replacement và lock elimination khác nhau ra sao?

Hai tối ưu này thường được nhắc cùng nhau vì đều dựa trên escape analysis, nhưng **không đồng nhất**.

### 10.1. Lock elimination

Mục tiêu: bỏ chi phí monitor khi compiler chứng minh các synchronization operations không cần để giữ Java semantics.

Một object vẫn có thể cần materialize vì identity được quan sát theo cách không cho phép loại allocation, nhưng compiler có thể vẫn có cơ hội tối ưu monitor trong trường hợp đối tượng đủ thread-local.

### 10.2. Scalar replacement

Mục tiêu: không materialize một object đầy đủ trên Java heap khi có thể biểu diễn các fields bằng scalar values.

```java
static int computeFields(int x) {
    Pair pair = new Pair(x, x + 1);
    return pair.left + pair.right;
}
```

Đây là **mã minh họa**, `Pair` cần được định nghĩa. Nếu `Pair` không escape và mọi uses phù hợp, C2 có thể thay object bằng các scalar values và không cần một heap allocation vật lý trong optimized path.

### 10.3. Allocation elimination không phải “đối tượng sẽ nằm trên stack”

HotSpot C2 theo mô tả Oracle không thực hiện stack allocation thông thường cho non-globally escaping objects. Việc một optimized allocation biến mất vì scalar replacement khác với việc “chuyển object đầy đủ từ heap sang stack”.

### 10.4. Có thể lock bị loại nhưng allocation chưa bị loại?

Về **khái niệm**, có. Một số escape states có thể đủ để loại lock nhưng không đủ để scalar replace object. Tuy nhiên, **một ví dụ cụ thể có thực hiện điều đó không** còn tùy JDK/compiler graph.

Không nên đọc kết quả benchmark rồi khẳng định “lock elimination là nguyên nhân duy nhất” nếu có thể đồng thời xảy ra allocation elimination, inlining hoặc loop optimization.

## 11. Vì sao inlining rất quan trọng?

EA thường hiệu quả hơn khi compiler thấy **toàn bộ đường sử dụng object**. Nếu monitor object được truyền cho một method và compiler có thể inline method ấy, đường tham chiếu có thể trở nên rõ ràng.

Ví dụ:

```java
static int guardedCompute(Object lock, int x) {
    synchronized (lock) {
        return x * 7;
    }
}

static int caller(int x) {
    Object fresh = new Object();
    return guardedCompute(fresh, x);
}
```

Đây là **snippet**, cần đặt trong class. Ở method `guardedCompute` nếu xét độc lập, tham số `lock` có thể đến từ bất kỳ caller nào và có thể được chia sẻ. Ở call site `caller`, object `fresh` mới tạo, không publish, và compiler **có thể thấy/inline** đoạn code.

Vì vậy:

- Nếu inline đủ, compiler có thể chứng minh monitor thread-private và loại lock.
- Nếu không inline (method quá lớn, call site đa hình, profile hạn chế, compilation budget...), compiler có thể phải giữ monitor.
- Không có ngưỡng kích thước method bắt buộc cho mọi JDK mà “dưới ngưỡng thì chắc chắn elide lock”.

### 11.1. Method boundaries không đồng nghĩa boundaries của EA

Một số compiler optimizations hoạt động tốt khi được inlined xuyên methods. Nhưng JIT không luôn inline mọi helper, nên cấu trúc call graph thực sự quan trọng.

### 11.2. Polymorphic calls có thể cản tối ưu

Nếu `guardedCompute` ủy quyền cho một interface call tới implementation chưa thể dự đoán, compiler có thể không biết callee có publish monitor hay không. Không chứng minh được no-escape thì an toàn nhất là giữ monitor semantics.

### 11.3. Reflection và native calls

Nếu một object được truyền vào reflective/JNI/native code, việc chứng minh nó không escape có thể khó hơn. JIT không được tự giả định mã ngoài Java không publish object hoặc không lưu reference nếu không có cơ sở phù hợp.

**Không gọi internal/native code chỉ nhằm ép khóa bị loại trong benchmark; thao tác đó thường làm EA khó hơn.**

## 12. Tính đúng khi object thực sự được chia sẻ

### 12.1. Static/shared monitor

```java
private static final Object LOCK = new Object();
private static int balance;

static void changeBalance() {
    synchronized (LOCK) {
        balance++;
    }
}
```

Nếu nhiều threads cùng gọi `changeBalance`, shared monitor có vai trò bảo vệ `balance++`. **Lock elimination không được làm mất mutual exclusion** khi chương trình chia sẻ cùng lock.

### 12.2. Publish monitor qua field

```java
final class Service {
    final Object lock = new Object();
    int count;

    void increment() {
        synchronized (lock) {
            count++;
        }
    }
}
```

Khi một `Service` instance được chia sẻ giữa threads, trường `lock` của **cùng instance** cũng được dùng chung. Do đó monitor có vai trò thực.

Ngược lại, nếu toàn bộ instance Service chứng minh chỉ dùng ở một thread trong một optimized scope, compiler có thể có cơ hội tối ưu. **Không quyết định từ chữ `final`**: `final Object lock` chỉ khiến reference field không thể được gán lại sau initialization bình thường; nó không cam kết object không bị publish.

### 12.3. Java Memory Model vẫn phải được giữ

Nếu code dùng đúng cùng monitor để publish shared state, JIT phải bảo toàn các happens-before relationships. Nó không thể loại bỏ khóa dựa vào phỏng đoán “trên máy thử không có contention”.

### 12.4. Một object được chia sẻ không có nghĩa mọi khóa liên quan đều bắt buộc tồn tại vật lý

JIT vẫn có thể tối ưu một số nested/merged monitor operations hoặc vùng không ảnh hưởng observable synchronization theo luật. Nhưng **không được đánh đồng** tối ưu cục bộ với việc loại toàn bộ monitor semantics của shared synchronization.

## 13. Không nhầm ba tối ưu: elimination, coarsening, nesting

| Tối ưu | Tác động | Điều kiện trực giác | Ví dụ |
| --- | --- | --- | --- |
| **Lock elimination** | Bỏ monitor operations | Chứng minh monitor không cần, như thread-private object | `synchronized(new Object())` với object không escape |
| **Lock coarsening** | Gộp nhiều khóa nhỏ liên tiếp thành vùng khóa lớn hơn | Compiler chứng minh gộp không đổi semantics | Nhiều synchronized blocks liên tiếp trên cùng monitor |
| **Nested lock elimination** | Bỏ chi phí khóa lồng có tính dư thừa | Reentrant lock cùng monitor trong một scope phù hợp | `synchronized(lock)` bên trong `synchronized(lock)` |

### 13.1. Lock coarsening không phải loại khóa

```java
synchronized (lock) { a(); }
synchronized (lock) { b(); }
```

Đây là snippet minh họa. Một số compiler optimizations có thể cân nhắc gộp thành vùng:

```java
synchronized (lock) {
    a();
    b();
}
```

nhưng **không phải lúc nào việc gộp cũng hợp lệ**. Nó thay đổi khoảng thời gian giữ lock; nếu thread khác có thể can thiệp giữa hai synchronized blocks, semantic differences phải được xem xét. Đây chỉ là mô hình minh họa cơ chế, không phải hướng dẫn refactor trực tiếp mọi code.

### 13.2. Lock elimination không phải biased locking

**Biased locking** là cơ chế HotSpot lịch sử nhằm tối ưu một số tình huống khóa ít có contention bằng cách thiên về thread quen thuộc. **JEP 374** đã tắt biased locking mặc định từ JDK 15 và deprecated các flags liên quan.

Điều quan trọng:

- Lock elimination dựa vào **compiler chứng minh synchronized operations là thừa**.
- Biased locking là một cách tối ưu **thực hiện locking** trong HotSpot trước đây.
- Tắt biased locking **không đồng nghĩa** tắt C2 escape analysis/lock elimination.
- Không sử dụng mô tả “HotSpot hiện nay luôn dùng biased locking” như kiến thức bất biến.

## 14. Vì sao `synchronized(new Object())` dễ được tối ưu?

Hãy nhìn trực tiếp:

```java
static int local(int x) {
    synchronized (new Object()) {
        return x + 1;
    }
}
```

Nếu không có code nào nhận được reference tới object literal allocation, một thread khác không thể acquire **cùng monitor** để cùng tham gia synchronization. Compiler có thể chứng minh không có hữu ích observable synchronization thông qua monitor đó.

Nhưng có một số lưu ý:

1. Đây là **điển hình ứng viên**, không phải cam kết JIT loại khóa trong mọi JDK/compile mode.
2. Source vẫn tuân Java semantics và tạo ra bytecode liên quan monitor; interpreter vẫn xử lý.
3. Monitor object có identity và allocation semantics, nhưng optimized path có thể được scalar replace khi đủ điều kiện.
4. Nếu body có side effects, exceptions hoặc calls phức tạp, JIT vẫn phải bảo toàn chúng.
5. Nếu một reference tới lock được publish ra ngoài, lập luận này không còn hợp lệ.

**Tuyệt đối không dùng khóa mới mỗi lần để bảo vệ dữ liệu chia sẻ**. Dù compiler bỏ khóa hay không, nó không thể đồng bộ hai threads trên hai objects khác nhau.

## 15. `synchronized` method và lock elimination

Một instance method:

```java
final class Counter {
    private int value;

    synchronized void addOne() {
        value++;
    }

    int value() {
        return value;
    }
}
```

khóa monitor của **`this`** khi gọi `addOne`.

Nếu một `Counter` instance được tạo rồi sử dụng riêng trong một method, không escape và compiler thấy rõ đường sử dụng, lock trong `addOne` **có thể là ứng viên loại bỏ**, thường cần inlining hoặc phân tích tương đương.

Ví dụ minh họa:

```java
static int isolated() {
    Counter counter = new Counter();
    counter.addOne();
    counter.addOne();
    return counter.value();
}
```

Đây là snippet cần ghép với class `Counter` ở trên. `Counter` không được publish trong method này, nên optimized code có thể đồng thời áp dụng **inlining**, **scalar replacement** và **lock elimination**.

Nhưng nếu gọi `counter` từ một static registry, thread khác có thể quan sát và gọi `addOne`; **không được giả định khóa bị loại**.

### 15.1. `synchronized static` khóa gì?

`static synchronized` method khóa **Class object** của class chứa method, không khóa một `new Object()` riêng cho mỗi invocation. Class mirror đó có thể được các threads dùng chung; không suy rằng static method không nhận tham số object thì khóa thừa.

### 15.2. Tại sao `StringBuffer` là ví dụ lịch sử kinh điển?

`StringBuffer` có nhiều methods synchronized theo API; khi một `StringBuffer` được tạo và dùng hoàn toàn cục bộ, HotSpot có thể tận dụng EA/inlining để giảm chi phí monitor ở các methods synchronized.

Tuy nhiên:

- `StringBuffer` còn có allocation/backing array, buffer expansion và copy chi phí riêng.
- `StringBuilder` được thiết kế cho tác vụ không cần synchronization và thường là lựa chọn source-level hợp lý nếu không chia sẻ.
- Đổi `StringBuffer` sang `StringBuilder` phải cân nhắc **API contract và publication**, không chỉ benchmark một trường hợp.
- Không có guarantee mọi `StringBuffer.append` được loại lock trong mọi JVM.

## 16. Các yếu tố làm C2 không loại được khóa

Một trường hợp source “trông local” vẫn có thể không được tối ưu do:

1. **Object escape:** lưu vào static/shared field hoặc trả reference cho caller không phân tích được.
2. **Method không được inline:** compiler không thấy hết uses hoặc call graph quá lớn.
3. **Polymorphism:** receiver/callee thay đổi nhiều, profile không đủ chắc.
4. **JNI/native/reflective paths:** compiler thiếu thông tin để kết luận non-escape.
5. **Compiler EA constraints:** độ phức tạp control-flow, memory graphs hoặc limits/thời gian phân tích.
6. **Cold method:** chưa compile lên tier hỗ trợ optimization đó.
7. **JVM flags:** `-Xint`, `-XX:-DoEscapeAnalysis`, `-XX:-EliminateLocks`, hoặc các compile directives.
8. **JDK/compiler version:** implementation thay đổi, tối ưu có thể xuất hiện/mất đi.
9. **Observability requirements:** monitor/object identity được dùng theo cách không thể loại bỏ mà vẫn giữ semantics.
10. **Deoptimization/safepoint state:** VM cần khôi phục đúng state khi optimized assumptions không còn phù hợp.

**Không nên sửa code chỉ để “làm EA chắc chắn tối ưu” bằng các mẹo không portable**, nhất là với code có shared mutable state.

## 17. Quan sát performance một cách khoa học

### 17.1. Thí nghiệm đối chứng gợi ý

Dùng **cùng** `LockElisionDemo.class` và JDK build, chạy các modes:

```bash
java LockElisionDemo
java -XX:-EliminateLocks LockElisionDemo
java -XX:-DoEscapeAnalysis LockElisionDemo
java -Xint LockElisionDemo
```

Những lệnh trên phù hợp để **kiểm tra correctness**. Demo chỉ in checksum và count, **không in timing**; vì vậy không lấy output này để tuyên bố speedup.

### 17.2. Vì sao so mode mặc định với `-Xint` chưa đủ chứng minh lock elimination?

`-Xint` tắt **toàn bộ JIT bytecode compilation**. Sự khác biệt hiệu năng có thể đến từ:

- Method-call overhead.
- Inlining.
- Loop optimization.
- Bounds-check/branch optimizations.
- Allocation elimination.
- Lock elimination.
- Interpreter dispatch overhead.

Muốn cô lập tác động riêng của lock elimination, `-XX:-EliminateLocks` là đối chứng gần mục tiêu hơn **nếu build hỗ trợ** và bạn đã kiểm tra các optimization tương tác.

### 17.3. Dùng JMH cho microbenchmark

**JMH (Java Microbenchmark Harness)** của OpenJDK giúp benchmark có:

- Warm-up và measurement iterations.
- Forked JVM processes với flags tách biệt.
- Blackhole/result consumption để tránh dead-code elimination.
- Statistical reporting, score units và error estimation.
- Baseline kiểm soát mức compiler optimization.

Một JMH plan hợp lý:

```text
Fork A:
  default HotSpot options

Fork B:
  -XX:-EliminateLocks

Fork C:
  -XX:-DoEscapeAnalysis  (phụ trợ, không cô lập riêng lock)

Same:
  JDK build
  CPU quota
  benchmark code
  data distribution
  warm-up and measurement parameters
```

Nếu benchmark method trả result đơn giản, optimizer có thể bỏ rất nhiều computation; cần thiết kế sao cho **workload đo thật sự còn tồn tại**.

### 17.4. Tại sao `System.nanoTime` vòng lặp đơn giản dễ sai?

Một vòng lặp nhỏ có thể được:

- Fully inlined.
- Unrolled.
- Strength-reduced hoặc constant-folded.
- Escape-analyzed và scalar-replaced.
- Dead-code eliminated nếu result không dùng.

Điều đó chính là thứ bạn đang nghiên cứu. Nhưng nếu thí nghiệm không kiểm soát, kết quả **không cho biết khóa nào bị loại**.

### 17.5. Không coi “tối ưu vô hình” là guarantee

Nếu benchmark mặc định nhanh hơn khi tắt EliminateLocks, kết quả **phù hợp** giả thuyết lock elimination giúp giảm overhead, nhưng vẫn cần các điều kiện thống kê và compiled-code evidence để gán nguyên nhân chắc chắn.

## 18. Phân tích assembly và compiler diagnostics

Muốn quan sát một monitor site đã bị loại ở machine code, có thể sử dụng những công cụ chuyên sâu tùy JDK build:

- **`-XX:+PrintCompilation`:** biết compilation level/event, **không biết lock đã loại**.
- **`-XX:+PrintInlining`:** hiểu một số inlining decisions, **không trực tiếp chứng minh lock bị loại**.
- **`-XX:+PrintAssembly`** với disassembler `hsdis` phù hợp: nhìn compiled code, nhưng phải có kinh nghiệm đọc assembly/GC stubs.
- **JITWatch** hoặc công cụ phân tích JIT logs: kết hợp bytecode/assembly/compilation metadata.
- **Debug/non-product HotSpot builds:** có thể có flags để in compiler transformations không có trong production release.

### 18.1. Cẩn trọng với PrintAssembly

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly LockElisionDemo
```

Đây là **lệnh gợi ý thử trên build có disassembler hỗ trợ**; nếu thiếu `hsdis` hoặc output khác kiến trúc, không thể mong đợi một bản assembly đầy đủ dễ đọc.

### 18.2. Deoptimization làm việc kiểm chứng khó hơn

Một compiled method có thể được deoptimize hoặc recompilation khi assumptions thay đổi. Code được đo ở thời điểm A chưa chắc là cùng compiled version ở thời điểm B. Cần kiểm tra compilation timeline/profile và warm-up.

### 18.3. C2 level 4 vẫn có thể chứa monitor

Compiler C2 không bắt buộc loại khóa nếu EA không đủ bằng chứng. Do đó:

```text
C2 compilation happened
             ≠
Every synchronized monitor in that method was removed
```

### 18.4. Bằng chứng tin cậy

Một kết luận mạnh cần có:

1. Bytecode thể hiện source synchronized.
2. HotSpot compiled version/machine code được nhận diện.
3. Phân tích cho thấy monitor operations tương ứng không còn ở optimized path, hoặc compiler IR/debug evidence đáng tin.
4. Thử nghiệm đối chứng/timing không trái với suy luận.
5. Correctness được giữ khi chạy interpreter/JIT và multi-thread sharing case.

## 19. Lock elimination không giải quyết mọi contention

Một chương trình thực tế thường khóa **đối tượng chia sẻ** để bảo vệ state:

```java
final class QueueState {
    private final Object lock = new Object();
    private int pending;

    void addTask() {
        synchronized (lock) {
            pending++;
        }
    }
}
```

Nếu cùng `QueueState` được truy cập từ nhiều threads, lock này có tác dụng mutual exclusion. **Không có “phép màu EA” tự loại contention** mà vẫn giữ cùng semantics của `pending++`.

Muốn tối ưu đúng, cân nhắc:

- Giảm thời gian giữ shared lock.
- Đưa I/O/blocking work ra ngoài critical section nếu logic cho phép.
- Chia state theo thread/shard để giảm sharing.
- Dùng atomic operations cho counter thật sự độc lập.
- Dùng concurrent collections/pools thay cấu trúc tự viết khi phù hợp.
- Kiểm tra false sharing, thread scheduling và allocation rate bằng profiler.
- Cân nhắc `ReentrantLock`/`StampedLock` hoặc cấu trúc khác khi có nhu cầu rõ, **không mặc định luôn nhanh hơn intrinsic lock**.

### 19.1. `LongAdder` và counters chịu tải

Nếu nhiều threads tăng counter độc lập với một invariant lớn, `LongAdder` có thể phù hợp hơn một single shared lock trong workload có contention. Nhưng `LongAdder.sum()` không cung cấp một atomic snapshot đối với concurrent updates giống mọi thao tác synchronized tùy ý.

Không thay synchronized bằng `LongAdder` khi logic cần transaction nhiều fields hoặc invariant phải được duy trì trong cùng critical section.

### 19.2. Không bỏ khóa để sửa benchmark

Nếu đồng bộ là cần thiết, **không xóa `synchronized` chỉ để đạt tốc độ cao**. Một benchmark ít tranh chấp không chứng minh an toàn concurrency trong production.

## 20. Vấn đề identity, null và synchronized exceptions

### 20.1. `synchronized(null)`

Java sẽ ném `NullPointerException` khi expression monitor được đánh giá ra `null`:

```java
Object lock = null;
synchronized (lock) {
    System.out.println("never reached");
}
```

Đây là snippet minh họa. JIT **không được** loại bỏ các semantics của NPE một cách sai khi tối ưu; chỉ có thể biến đổi khi hành vi quan sát được không đổi.

### 20.2. Lock identity quan trọng

Hai object khác nhau có thể `equals` nhau nhưng **không phải cùng monitor**. Java `synchronized` khóa theo **reference identity của object**, không theo `equals()` hoặc `hashCode()`.

Đừng dùng object mới với cùng giá trị `equals` rồi kỳ vọng những threads dùng hai instances tự đồng bộ với nhau.

### 20.3. Identity hash không phải bằng chứng khóa không thể loại

Gọi `System.identityHashCode(lock)` có thể làm compiler phải materialize identity theo những điều kiện cụ thể. Nhưng **không có quy tắc portable “gọi identityHashCode chắc chắn cấm lock elimination”** hoặc “nó luôn pin object ở một địa chỉ”.

Việc identity được quan sát, allocation được scalar replace và khóa có thể bị loại là những quyết định compiler riêng, phụ thuộc behavior cần bảo toàn.

### 20.4. Wait/notify và monitor state

`Object.wait()`/`notify()` yêu cầu monitor ownership và có semantics riêng. Nếu code gọi chúng trên một monitor, compiler phải giữ behavior về ownership, `IllegalMonitorStateException` và các tác động concurrency cần thiết. **Không thể xóa những operations này bừa bãi** chỉ vì tên biến là local.

### 20.5. `volatile` không thay thế khóa trong mọi trường hợp

`volatile` hữu ích cho visibility/ordering theo JMM; nhưng `counter++` gồm read-modify-write và **không trở thành atomic** chỉ vì `counter` là volatile. Nếu cần atomic increment hãy dùng lock hay atomic primitives phù hợp.

## 21. Những hiểu lầm phổ biến

| Nhận định sai | Diễn giải đúng |
| --- | --- |
| “Cứ có `synchronized` là CPU luôn thực hiện full monitorenter/exit.” | C2 có thể loại monitor nếu chứng minh synchronization không cần. |
| “Biến khóa là local thì object chắc chắn không escape.” | Object có thể được return, publish vào static/shared field hoặc truyền qua call. |
| “Tối ưu lock elimination làm `synchronized` mất Java semantics.” | JIT bắt buộc bảo toàn semantics quan sát được. |
| “Thử không có contention nên compiler chắc bỏ khóa.” | Không tranh chấp được quan sát **không bằng** chứng minh thread-private. |
| “`synchronized(new Object())` là cách bảo vệ shared count.” | Mỗi lần gọi dùng monitor khác, **không đồng bộ threads với nhau**. |
| “Nhóm NoEscape là keyword/type của Java.” | Là phân loại EA của compiler, không phải cấu trúc ngôn ngữ. |
| “Non-escaping object chắc được cấp phát trên stack.” | C2 có scalar replacement; không hứa stack allocation cho object. |
| “Lock elimination và scalar replacement luôn xảy ra cùng nhau.” | Có thể có những điều kiện khác nhau và compiler decisions riêng. |
| “`-XX:-DoEscapeAnalysis` chỉ tắt lock elimination.” | Nó có thể ảnh hưởng allocation/scalar replacement và nhiều tối ưu EA. |
| “`-XX:-EliminateLocks` là lựa chọn production phải dùng.” | Chủ yếu là cờ thí nghiệm/đối chứng, có thể làm performance xấu đi. |
| “`-Xint` là đối chứng cô lập riêng lock overhead.” | Nó tắt toàn JIT bytecode compilation và ảnh hưởng nhiều tối ưu khác. |
| “`PrintCompilation` level 4 chứng minh monitor bị xóa.” | Chỉ cho thấy C2 compilation, không chứng minh specific transformation. |
| “`javap` có monitorenter nghĩa JIT không thể loại khóa.” | `javap` đọc bytecode trước JIT, không đọc optimized machine code. |
| “Lock coarsening cũng là xóa toàn bộ monitor.” | Coarsening gộp/đổi phạm vi khóa; khác elimination. |
| “Biased locking và C2 lock elimination là một.” | Một cái là historic runtime locking optimization; một cái là compiler optimization. |
| “Object `final lock` không thể bị chia sẻ.” | `final` giữ reference field không đổi, không ngăn publish owner object. |
| “Mọi method nóng chắc được EA tối ưu.” | Inlining, compiler limits, escape paths và build quyết định. |
| “Shared monitor có thể bỏ vì JIT thấy update luôn thành công.” | Nếu threads dùng chung monitor, mutual exclusion/JMM phải được giữ. |
| “`synchronized(null)` có thể không ném lỗi nếu JIT đủ tốt.” | NPE semantics vẫn bắt buộc được bảo toàn. |
| “`volatile int++` là atomic.” | Không; volatile không tự làm compound increment atomic. |
| “Một lần timing nhanh hơn chứng minh lock elision.” | Cần warm-up, lặp, profiler/assembly hoặc compiler evidence. |

## 22. Bài tập tự kiểm tra có đáp án

**Câu 1.** Lock elimination là gì?

**Đáp án:** Một tối ưu HotSpot JIT có thể bỏ monitor enter/exit ở optimized machine code khi compiler chứng minh khóa không cần để bảo toàn Java semantics, thường nhờ escape analysis.

**Câu 2.** Tại sao tạo `new Object()` trong synchronized block có thể là ứng viên loại khóa?

**Đáp án:** Nếu object không được publish/escape, thread khác không thể acquire cùng monitor để phối hợp, nên thao tác khóa có thể được chứng minh thừa.

**Câu 3.** Khóa một `new Object()` ở mỗi lời gọi có bảo vệ static counter giữa nhiều threads không?

**Đáp án:** Không. Mỗi lời gọi có monitor riêng, nên không có mutual exclusion giữa threads trên static counter.

**Câu 4.** EA có mấy nhóm escape states nổi tiếng trong tài liệu HotSpot?

**Đáp án:** NoEscape, ArgEscape và GlobalEscape.

**Câu 5.** `NoEscape` có nghĩa JVM cam kết stack-allocate object không?

**Đáp án:** Không. HotSpot có thể scalar-replace allocation; không được suy nó tạo object trên stack.

**Câu 6.** Một object được đặt vào static field còn nên coi chắc chắn non-escaping không?

**Đáp án:** Không. Static field là một đường publish ra ngoài local scope, có khả năng được nhiều threads truy cập.

**Câu 7.** `synchronized(lock)` trên một static shared lock có thể bỏ vô điều kiện không?

**Đáp án:** Không. Nó có thể cần bảo đảm atomicity/visibility giữa threads.

**Câu 8.** Vì sao `javap` vẫn thấy `monitorenter` sau khi C2 tối ưu?

**Đáp án:** `javap` đọc `.class` bytecode; C2 tối ưu machine code trong JVM runtime, không sửa class file.

**Câu 9.** `PrintCompilation` level 4 có chứng minh lock elimination xảy ra không?

**Đáp án:** Không. Nó chỉ cho thấy một C2 compilation event, không báo riêng monitor đã được loại.

**Câu 10.** Sự khác nhau giữa lock elimination và lock coarsening?

**Đáp án:** Elimination bỏ monitor operations chứng minh thừa; coarsening có thể gộp vùng synchronized theo điều kiện giữ semantics.

**Câu 11.** `-Xint` có là đối chứng chỉ riêng lock elimination không?

**Đáp án:** Không. Nó tắt JIT compilation cho bytecode nên còn loại bỏ nhiều tối ưu khác.

**Câu 12.** `-XX:-DoEscapeAnalysis` có thể ảnh hưởng gì ngoài khóa?

**Đáp án:** Scalar replacement, allocation elimination và các tối ưu EA khác.

**Câu 13.** JDK 17 còn bật biased locking mặc định không?

**Đáp án:** Không. JEP 374 đã tắt biased locking theo mặc định từ JDK 15; nó khác lock elimination.

**Câu 14.** Synchronized instance method khóa monitor nào?

**Đáp án:** Monitor của `this` instance nhận lời gọi.

**Câu 15.** Static synchronized method khóa monitor nào?

**Đáp án:** Monitor của `Class` object đại diện class chứa method.

**Câu 16.** Nếu `StringBuffer` chỉ dùng local thì mọi synchronized method chắc chắn bị JIT xóa khóa không?

**Đáp án:** Không. Nó là ứng viên tối ưu khi compiler có đủ bằng chứng; không có guarantee của Java/HotSpot cho mọi trường hợp.

**Câu 17.** Vì sao JMH phù hợp hơn đo một lần `System.nanoTime`?

**Đáp án:** JMH cung cấp forks, warm-up, measurement, blackhole và thống kê, giảm nhiều bẫy JIT benchmark.

**Câu 18.** Kết quả `local checksum` ở ví dụ là bao nhiêu?

**Đáp án:** `14999950000` với 100.000 giá trị `i = 0..99999`.

**Câu 19.** Hai threads cùng increment sharedCount 20.000 lần qua cùng monitor và join. Giá trị expected?

**Đáp án:** `40000` khi chạy hoàn tất bình thường.

**Câu 20.** Một monitor thật sự được dùng trong wait/notify có thể bị xóa tùy tiện không?

**Đáp án:** Không. Monitor ownership, wait/notify semantics và các exceptions phải được bảo toàn.

**Câu 21.** Nếu muốn chứng minh lock cụ thể đã bị loại ở machine code, cần quan sát gì?

**Đáp án:** Compiled code/IR hoặc compiler diagnostics đáng tin ở phiên bản HotSpot cụ thể, cộng thí nghiệm đối chứng; một log compilation đơn thuần không đủ.

## 23. Checklist ứng dụng và chẩn đoán thực tế

1. Xác nhận JVM là HotSpot và ghi **JDK build, CPU architecture, VM flags**.
2. Phân biệt **monitor object** với **dữ liệu được bảo vệ**.
3. Đảm bảo mọi threads muốn bảo vệ cùng invariant phải đồng bộ theo cùng cơ chế thích hợp.
4. Đừng xem tên biến local là bằng chứng đầy đủ của non-escape.
5. Tìm các escape paths: return, static/shared fields, callbacks, native calls.
6. Khi code hot, quan sát inlining/C1/C2/EA trong giới hạn công cụ.
7. Hiểu `javap` báo bytecode, không báo optimized assembly.
8. Dùng `-XX:-EliminateLocks` làm đối chứng có điều kiện, không coi là tuning mặc định.
9. Biết `-XX:-DoEscapeAnalysis` còn ảnh hưởng allocation optimizations.
10. Giữ code correctness ở `-Xint`, JIT và multi-threaded contexts.
11. Dùng JMH/benchmark nhiều forks và warm-up nếu đánh giá performance.
12. Không dựa vào `PrintEliminateLocks` trên bản JDK production nếu flag không được hỗ trợ.
13. Không nhầm lock coarsening/nested locks/biased locking với compiler lock elimination.
14. Khi shared state có contention thật, xử lý ở architecture/data sharing level thay vì trông cậy EA.
15. Đọc JMM/happens-before trước khi thay cơ chế đồng bộ.
16. Quan sát throughput, p95/p99 latency, CPU và GC cùng nhau khi tuning HotSpot.
17. Không thay đổi logic synchronization chỉ vì benchmark nhỏ dường như nhanh hơn.
18. Sau nâng JDK/đổi JVM vendor, **kiểm tra lại các giả thuyết performance** thay vì hardcode compiler behavior.

### Tóm tắt cuối bài

```text
Java source synchronized(lock)
                |
                v
javac giữ monitorenter / monitorexit bytecode
                |
                v
HotSpot JIT (khi code đủ hot)
                |
         Escape analysis
                |
     monitor không bị share?
          /           \
        Có            Không / không chứng minh được
        |                       |
        v                       v
  Có thể loại lock        Giữ monitor semantics
        |
        +--> Nếu scalar replace được:
             có thể loại cả object allocation

BẮT BUỘC trong cả hai trường hợp:
  - Mutual exclusion của shared synchronization vẫn đúng.
  - Happens-before / memory visibility vẫn đúng.
  - Exceptions, identity và observable Java semantics vẫn đúng.
```

**Thông điệp cốt lõi:** **HotSpot có thể loại bỏ khóa `synchronized` không cần thiết nhờ escape analysis khi đối tượng monitor không được chia sẻ theo cách gây tác dụng đồng bộ.** Đây là khả năng tối ưu của compiler, **không phải lời hứa rằng mọi khóa local đều được xóa**, càng không phải quyền xóa synchronization bảo vệ shared mutable state. Hãy thiết kế code đúng theo Java Memory Model trước; để HotSpot tự tối ưu khi nó có đủ bằng chứng.

### Tài liệu chính thức và mở rộng

- [Oracle JDK 21 — Java HotSpot VM Performance Enhancements, Escape Analysis](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html): NoEscape/ArgEscape/GlobalEscape, scalar replacement, elimination of non-global-escaping locks và ví dụ local StringBuffer.
- [Oracle JDK 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cờ `-XX:+DoEscapeAnalysis` và các JIT/diagnostic flags.
- [OpenJDK JDK 17u — C2 compiler flags](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp): `EliminateLocks`, `DoEscapeAnalysis`, `EliminateAllocations`, các flags debugging không có trong mọi product build.
- [OpenJDK — Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): khả năng và giới hạn EA/C2, phân biệt stack allocation với scalar replacement.
- [JLS §17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronized, memory model và happens-before.
- [JVMS §6.5 — monitorenter/monitorexit (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): semantics của bytecode synchronization.
- [OpenJDK JEP 374 — Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): phân biệt biased locking lịch sử với C2 lock elimination.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmark Java có warm-up, forks và output statistics.
