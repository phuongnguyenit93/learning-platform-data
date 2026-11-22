# Java Memory Model khác với sơ đồ heap, stack và bộ nhớ vật lý

## 1. Trả lời ngắn: JMM là tập quy tắc về hành vi, không phải sơ đồ nơi dữ liệu được đặt

**Java Memory Model (JMM)** là mô hình ngữ nghĩa trong **Java Language Specification (JLS), Chương 17**, xác định **những kết quả quan sát được nào là hợp lệ** khi các threads cùng đọc, ghi và đồng bộ dữ liệu. Nó mô tả **hành vi đọc/ghi, thứ tự được phép quan sát, quan hệ happens-before, data races, volatile, monitors và final fields**.

Ngược lại, sơ đồ **JVM heap/stack** trong **Java Virtual Machine Specification (JVMS) §2.5** mô tả các **vùng dữ liệu runtime** của máy ảo: heap chia sẻ, mỗi thread có JVM stack, frames/local variables/operand stacks, method area, runtime constant pool, PC register và native method stacks.

Còn **bộ nhớ vật lý** là cách CPU, OS, máy ảo và HotSpot triển khai chương trình: registers, CPU caches, RAM, virtual memory, memory pages, allocation buffers, GC barriers, compiler optimizations...

Ba lớp giải thích **những câu hỏi khác nhau**:

| Lớp | Câu hỏi chính | Nguồn mô tả |
| --- | --- | --- |
| **JMM** | Thread B được phép nhìn giá trị nào từ thread A? Khi nào write được publish an toàn? Có data race không? | JLS `17.4–`17.5 |
| **JVM runtime data areas** | Heap, JVM stacks, frames, local-variable slots và method area có vai trò gì? | JVMS `2.5–`2.6 |
| **Implementation/hardware** | Bit nằm trong CPU register/cache/RAM ở thời điểm nào? JIT dùng instructions/barriers gì? Object bố trí thế nào? | HotSpot, OS và CPU architecture |

**Không được suy ra Java Memory Model chỉ bằng hình “biến local ở stack, object ở heap”.** Một thread có thể có biến local riêng **trỏ tới object chung**. Hơn nữa, even if một Java field nằm trong heap theo mô hình ngôn ngữ, JIT có thể giữ giá trị trong register, loại allocation bằng scalar replacement hoặc sắp xếp instructions lại theo cách vẫn tuân JMM.

### 1.1. Sơ đồ ba tầng

```text
JAVA PROGRAM                    JVM MODEL                    IMPLEMENTATION
--------------                  ----------------            ----------------------
Thread A, Thread B              Heap/shared fields          CPU registers
read/write shared state         Per-thread frames           L1/L2/L3 caches
synchronized, volatile          JVM stacks                  DRAM / virtual memory
final fields, Thread.start      Class metadata              HotSpot JIT, GC, barriers
        |                              |                            |
        v                              v                            v
        JMM: quan sát nào             JVMS: vùng dữ liệu            CPU/OS: hiện thực
        được phép?                    nào tồn tại?                 bằng cách nào?
        |                                                           |
        +--------------- RÀNG BUỘC NGỮ NGHĨA -----------------------+
```

Sơ đồ này **không đồng nhất** JMM với một khối RAM/caches có sẵn. Một implementation được tự do tối ưu miễn chương trình thực hiện **một execution hợp lệ theo JMM**.

## 2. Heap và stack trong JVMS: đúng ở cấp kiến trúc nhưng không đủ cho concurrency

Theo **JVMS §2.5.3**, JVM có **heap chia sẻ giữa tất cả JVM threads** để cấp phát class instances và arrays. Heap storage được quản lý bởi garbage collector; đặc tả không ép một phương pháp quản lý bộ nhớ cụ thể.

Theo **JVMS `2.5.2**, **mỗi JVM thread có JVM stack riêng**, được dùng để chứa frames cho method invocations. Theo `2.6, mỗi frame chứa **local variables array**, **operand stack** và thông tin liên quan.

```text
              THREAD A                      THREAD B
        +--------------------+        +--------------------+
        | JVM stack A        |        | JVM stack B        |
        | frame: local ref p |        | frame: local ref q |
        +---------+----------+        +----------+---------+
                  |                              |
                  +---------------+--------------+
                                  v
                        SHARED JVM HEAP
                        +-------------------+
                        | Payload object    |
                        | value = 42        |
                        +-------------------+
```

Biến `p` và `q` là **hai local variables khác nhau**, mỗi biến thuộc method frame riêng. Nhưng cả hai có thể chứa **reference tới cùng object** trên heap. Nếu hai threads cùng đọc/ghi `Payload.value`, có khả năng xảy ra **conflicting accesses** trên một shared field.

### 2.1. Stack riêng không làm object được trỏ tới trở nên riêng

Ví dụ khái niệm:

```java
class Box {
    int value;
}

Box shared = new Box();
Thread t1 = new Thread(() -> shared.value++);
Thread t2 = new Thread(() -> shared.value++);
```

Đây là **snippet**, chưa tạo/start/join đầy đủ. Dù tham số/local references trong hai threads không phải cùng local variable, cả hai có thể truy cập **field `value` của cùng một `Box`**. `value++` không phải phép increment atomic theo JMM; nếu không có synchronization phù hợp sẽ có data race và có thể mất cập nhật.

**Điều quyết định:** có đang truy cập **cùng shared variable** hay không, không phải reference nằm trong frame nào.

### 2.2. Local variables không phải shared variables của JMM

**JLS §17.4.1** nói rõ local variables, formal method parameters và exception handler parameters **không được chia sẻ trực tiếp giữa các threads** và không thuộc cơ chế shared-variable memory model.

Nhưng **giá trị của local variable có thể là reference tới shared object**. Chính **instance fields, static fields và array elements** mới thuộc các shared variables đang được JLS §17.4 nghiên cứu.

Do vậy câu “mọi biến local đều thread-safe” **quá rộng và sai**: local reference riêng có thể dẫn tới shared mutable state không an toàn.

### 2.3. JVM stack không nhất thiết khớp tuyệt đối với stack frame vật lý bạn tưởng tượng

JVMS mô tả các khái niệm runtime như frames/local-variable slots. Trên HotSpot thực tế, JIT có thể:

- Đặt một số values trong CPU registers.
- Inline methods khiến biên giới source frames không còn hiện hữu vật lý như suy đoán.
- Eliminate allocations hoặc scalar-replace object fields.
- Reuse/rearrange slots theo tối ưu.
- Lưu thêm metadata hỗ trợ safepoints, deoptimization và GC roots.

**Đừng gắn mọi local Java vào một địa chỉ stack vật lý cố định** hoặc coi mỗi Java object bắt buộc được materialize trong heap mọi thời điểm.

### 2.4. Heap chia sẻ không có nghĩa mọi heap object đều thực tế bị chia sẻ

Một Java object có thể chỉ được thread A truy cập, dù Java heap về mặt kiến trúc là vùng dùng chung. Compiler có thể chứng minh object không escape và tối ưu, nhưng **đây là kết luận từ luồng tham chiếu**, không phải do heap biến thành private memory.

## 3. Tại sao cần Java Memory Model?

Bởi một chương trình đa luồng muốn biết **thread B được phép nhìn kết quả nào** khi thread A ghi dữ liệu.

Ví dụ:

```java
class Message {
    int data;
    boolean ready;
}
```

Giả sử A làm:

```java
message.data = 42;
message.ready = true;
```

và B làm:

```java
if (message.ready) {
    System.out.println(message.data);
}
```

Các snippets trên **chưa có synchronization**. Dù A viết `data` trước `ready` theo source program order, nếu có data race thì **không thể kết luận B khi thấy `ready == true` chắc chắn đọc `data == 42`**. Compiler, runtime hoặc processor được phép thực hiện những transformations phù hợp với JMM mà trực giác đơn luồng không lường trước.

### 3.1. Điều JMM mô tả là các execution hợp lệ

Theo **JLS §17.4**, memory model xem một execution trace và kiểm tra read action có thể quan sát write action nào theo các quy tắc hợp lệ hay không.

Nó không cung cấp một sơ đồ như:

```text
volatile write == copy bytes immediately to RAM
volatile read  == fetch bytes directly from RAM
```

Hai đẳng thức trên **không phải định nghĩa của JMM**. Compiler/hardware có nhiều cách duy trì visibility/ordering mà không cần thực hiện các “RAM flushes” như mô tả giản lược.

### 3.2. Vấn đề nằm ở visibility, ordering và atomicity

- **Visibility:** một thread có thể được bảo đảm quan sát các writes của thread khác trong điều kiện nào.
- **Ordering:** những actions có thể được thấy theo quan hệ thứ tự ra sao.
- **Atomicity:** thao tác được coi như một bước nguyên tử với khả năng xen kẽ giữa các threads thế nào.

Ba thuộc tính này liên quan, nhưng **không tương đương**. `volatile` cung cấp những bảo đảm visibility/ordering cho biến thích hợp, **không làm `counter++` atomic**.

## 4. Các thành phần khái niệm chính của JMM

JMM sử dụng các khái niệm:

1. **Actions:** reads/writes và các synchronization actions của threads.
2. **Program order:** thứ tự actions của **một thread** theo thực thi ngôn ngữ.
3. **Synchronization order:** tổng thứ tự các synchronization actions trong một execution, nhất quán với program order cho mỗi thread.
4. **Synchronizes-with:** các cạnh đồng bộ được JLS định nghĩa, ví dụ volatile write → subsequent read của cùng volatile variable, unlock → subsequent lock cùng monitor.
5. **Happens-before (HB):** quan hệ thứ tự từng phần được xây từ program order, synchronizes-with và tính bắc cầu.
6. **Conflicting accesses:** hai accesses tới **cùng shared variable**, trong đó ít nhất một access là write.
7. **Data race:** hai conflicting accesses không được sắp thứ tự bằng happens-before.
8. **Well-formed execution/casuality rules:** quy tắc đảm bảo những values mà reads quan sát hợp lệ, giới hạn suy luận từ chương trình racy.

**Không phải mọi sự kiện trong JMM là một CPU instruction đơn lẻ.** Đó là **semantic actions**, implementation có thể hiện thực bằng nhiều instructions hoặc tối ưu không tạo instruction tương ứng nếu observable behavior vẫn hợp lệ.

### 4.1. Shared variables cụ thể gồm gì?

Theo §17.4.1:

- **Instance fields**.
- **Static fields**.
- **Array elements**.

Đừng loại array elements khỏi phân tích data races chỉ vì không có tên field như `count`. Hai threads cùng ghi `array[0]` có thể race; còn ghi vào **những array elements khác nhau** thì đó là những shared variables khác, dù vẫn có các vấn đề concurrency cấp cao cần xét.

### 4.2. Local primitive khác reference tới object

```java
int local = 7;
Box box = sharedBox;
local++;
box.value++;
```

Đây là **snippet**, `sharedBox` cần định nghĩa.

- `local`: local primitive trong frame, không được trực tiếp chia sẻ theo JMM.
- `box`: local reference riêng; giá trị reference có thể là địa chỉ/handle JVM hiện thực.
- `box.value`: field của object có thể shared; nếu được nhiều threads cập nhật không đồng bộ, có thể race.

Không được kết luận “`box` local nên `box.value` local”.

## 5. Program order không phải lời hứa về thứ tự physical instructions

Một thread theo source:

```java
a = 1;
b = 2;
```

có **program order** giữa hai actions theo JMM khi chúng xuất hiện trong execution tương ứng. Nhưng compiler và CPU có thể reorder hoặc loại bỏ operations khi điều đó không thay đổi behaviors được phép của chương trình.

Trong một chương trình đa luồng thiếu synchronization, một thread khác **không có quyền suy ra** từ source order đơn thuần rằng thấy `b == 2` đồng nghĩa phải thấy `a == 1`.

### 5.1. As-if-serial không đủ cho các shared-variable races

Trên một thread riêng lẻ, tối ưu thường phải bảo toàn intra-thread semantics. Nhưng các threads khác có thể quan sát những thứ tự tưởng như bất ngờ nếu không có HB edges.

JLS §17.4 có những ví dụ về **reordering** hợp lệ dù tưởng trái với source code.

### 5.2. CPU cache không là căn cứ để “chứng minh” một read hợp lệ

Các CPUs có cache coherence protocols, store buffers và memory-ordering rules khác nhau. Nhưng cách hiểu chính xác Java program phải dựa vào **JMM**, không phải phỏng đoán `L1 cache` của thread A đã flush hay chưa.

Hai CPUs cùng chạy một chương trình Java có thể có memory ordering hardware khác nhau; **JVM/JIT phải hiện thực synchronization semantics của Java trên cả hai**.

### 5.3. Wall-clock order khác happens-before

Một write “thật sự xảy ra sớm hơn” theo đồng hồ người quan sát **không tự tạo HB edge** với một read của thread khác. HB là **quan hệ trong execution theo JMM** được xây từ program order/synchronization rules.

Ngược lại, JMM cho phép implementation thực hiện một số reorderings vật lý nếu kết quả vẫn nhất quán với executions hợp lệ; **HB không có nghĩa mọi memory instruction phải hoàn tất vật lý theo cùng một lịch thời gian tuyệt đối**.

## 6. Happens-before: công cụ suy luận quan trọng nhất

Viết `hb(A, B)` khi action A **happens-before** action B.

JLS §17.4.5 xây HB từ:

- **Program order:** action trước trong cùng thread happens-before action sau.
- **Synchronizes-with:** action đồng bộ nguồn happens-before action đồng bộ đích.
- **Transitivity:** nếu `hb(A,B)` và `hb(B,C)` thì `hb(A,C)`.

Một số quy tắc quan trọng:

| Nguồn | Đích | Ý nghĩa |
| --- | --- | --- |
| Unlock monitor `M` | Subsequent lock monitor `M` theo synchronization order | Publish writes qua cùng monitor |
| Write volatile `v` | Subsequent read volatile `v` theo synchronization order | Publish các writes trước tới thread đọc flag/reference |
| `Thread.start()` | Hành động của thread được start | Công bố state đã chuẩn bị trước khi start |
| Actions trong thread `T` | Thread khác trở về thành công từ `T.join()` | Thread joiner nhìn thấy effects trước khi T kết thúc |
| Default initialization của object | Những actions về sau theo quy tắc JLS | Các fields có giá trị mặc định trước usage thích hợp |
| `Thread.interrupt()` | Thread khác phát hiện interruption theo quy tắc | Có cạnh synchronization tương ứng |

Những APIs trong `java.util.concurrent` còn định nghĩa **memory consistency effects** của riêng chúng. Hãy đọc tài liệu API để biết vì sao việc enqueue/dequeue, CountDownLatch, Future.get hoặc atomic operations tạo ra quan hệ quan sát phù hợp.

### 6.1. Ví dụ tuyến tính bắc cầu

```text
Thread A:                   Thread B:
  payload.value = 84          local = published  [volatile read]
  published = payload         print(local.value)
      [volatile write]

Program order: A.value write -> A.volatile write
Synchronizes-with: A.volatile write -> B.volatile read
Program order: B.volatile read -> B.value read

=> A.value write happens-before B.value read
   (khi B đọc reference đã được publish theo volatile)
```

Đây là **semantic proof**, không phải sơ đồ “copy 84 từ L1 sang DRAM”.

### 6.2. `happens-before` không đồng nghĩa mọi read sẽ thấy “giá trị mới nhất theo đồng hồ”

Một HB edge giúp ràng buộc các writes mà read có thể quan sát. Nhưng muốn suy read thấy **giá trị cụ thể**, phải xét **các writes khác tới cùng variable**, thứ tự liên quan và semantics đầy đủ của program.

Đừng nói “có HB là đọc ngay lập tức mọi giá trị mới nhất ngoài hệ thống” — JMM không cung cấp một global memory snapshot bằng timestamp vật lý.

## 7. `volatile`: publication và ordering, không phải “bắt buộc ghi thẳng RAM”

Một field khai báo:

```java
private static volatile boolean done;
```

là **volatile variable**. Theo JMM, **write volatile** và **read volatile** là **synchronization actions**. Một write vào `done` **synchronizes-with** những subsequent reads của cùng volatile variable theo synchronization order.

### 7.1. Ví dụ cờ dừng

```java
class Flag {
    volatile boolean done;
}

static void worker(Flag flag) {
    while (!flag.done) {
        Thread.onSpinWait();
    }
}
```

Đây là **đoạn mã minh họa**, chưa phải chương trình độc lập. `Thread.onSpinWait()` là **hint hiệu năng**, không thay thế `volatile` hay tạo một HB edge đặc biệt.

Nếu `done` là **non-volatile** và không có synchronization khác, JVM có thể tối ưu phép đọc, hoặc chương trình có thể mãi không quan sát thay đổi từ thread khác. Đừng dùng `Thread.sleep`/`onSpinWait` như giải pháp thay volatile.

### 7.2. Safe publication bằng volatile reference

```java
class Data {
    int value;
}

static volatile Data published;

static void producer() {
    Data data = new Data();
    data.value = 84;
    published = data;
}
```

Khi consumer quan sát **reference được publish** thông qua volatile read, những writes đi trước volatile write có HB path tới reads sau. Vì vậy consumer có thể dựa vào state đã được khởi tạo an toàn theo thứ tự đó.

### 7.3. Volatile reference không làm toàn object graph trở thành synchronized

Sau publication:

```java
Data snapshot = published;
snapshot.value++;
```

Nếu nhiều threads đồng thời tăng `value` mà không synchronization, **field `value` vẫn có thể race**. `volatile Data published` làm reference accesses volatile, **không biến mọi field của Data thành volatile/atomic**.

### 7.4. Volatile increment không atomic

```java
volatile int counter;

void increment() {
    counter++;
}
```

Đây là **snippet minh họa**; `counter++` gồm đọc, tính toán và ghi. Hai threads có thể đọc cùng giá trị rồi cùng ghi kết quả, gây **lost update**, dù access từng lần có volatile semantics.

Dùng `AtomicInteger.incrementAndGet()` hoặc `synchronized` khi cần atomic increment.

### 7.5. Volatile không nhất thiết luôn sinh full hardware fence

JIT có thể hiện thực volatile bằng instructions/ordering/barriers phù hợp từng CPU architecture. Không có cam kết rằng **mỗi volatile read gây một memory fence instruction cụ thể** hay **ép CPU cache flush toàn bộ lên main memory**.

**JMM cam kết hiệu ứng quan sát được**, không quy định instruction set implementation.

## 8. `synchronized`: vừa mutual exclusion vừa publication

```java
private static final Object LOCK = new Object();
private static int count;

static void increment() {
    synchronized (LOCK) {
        count++;
    }
}
```

Nếu mọi threads sửa `count` đều khóa **cùng monitor `LOCK`**, phép read-modify-write được bảo vệ bằng mutual exclusion.

### 8.1. Unlock → lock HB

Thread A:

```java
synchronized (LOCK) {
    count = 42;
}
```

Thread B:

```java
synchronized (LOCK) {
    System.out.println(count);
}
```

Khi B acquire cùng monitor sau A release, JMM có đồng bộ phù hợp để B nhìn thấy writes đi trước. Nhưng **không được chỉ nhìn hai snippets rồi tuyên bố output của B luôn 42** nếu B có thể chạy trước A; thứ tự acquiring monitor rất quan trọng.

### 8.2. Hai khóa khác nhau không tạo cùng quan hệ

```java
synchronized (new Object()) {
    count++;
}
```

Nếu mỗi thread tạo một khóa mới, họ **không dùng chung monitor**. Khối synchronized ấy không bảo vệ `count` khỏi các threads khác cùng làm tương tự. JIT còn có thể loại khóa nếu chứng minh monitor không escape.

**Monitor identity** mới quyết định việc đồng bộ, không phải hình dạng source code giống nhau.

### 8.3. Synchronized method khóa ai?

- `synchronized` instance method khóa **`this`**.
- `static synchronized` method khóa **`Class` object** đại diện class.
- `synchronized(lock)` block khóa **đúng object reference mà biểu thức trả về**.

Không được hiểu “khóa cả heap” hoặc “đóng băng RAM” khi chạy synchronized.

### 8.4. Synchronized và hardware instructions

HotSpot có thể triển khai các đường khóa không tranh chấp/tranh chấp bằng những cơ chế khác nhau theo phiên bản. JIT có thể tối ưu lock elision khi an toàn. JMM chỉ yêu cầu **hành vi monitor và memory ordering hợp lệ**; không quy định chính xác byte trong object header hoặc một instruction cố định.

## 9. Một ví dụ Java 17+ độc lập: volatile publication và synchronized counter

Tạo tệp **`MemoryModelDemo.java`**:

```java
public final class MemoryModelDemo {
    private static final class Payload {
        final int id;
        int value;

        Payload(int id, int value) {
            this.id = id;
            this.value = value;
        }
    }

    private static volatile Payload published;
    private static final Object LOCK = new Object();
    private static int count;

    private static void increment() {
        synchronized (LOCK) {
            count++;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread producer = new Thread(() -> {
            Payload localReference = new Payload(42, 84);
            published = localReference;
        });

        Thread consumer = new Thread(() -> {
            Payload localReference;
            do {
                localReference = published;
            } while (localReference == null);

            System.out.println("published id=" + localReference.id);
            System.out.println("published value=" + localReference.value);
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();

        Thread first = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                increment();
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                increment();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized count=" + count);
        System.out.println("expected count=40000");
    }
}
```

### 9.1. Chạy chương trình

```bash
javac --release 17 MemoryModelDemo.java
java MemoryModelDemo
```

**Stdout chính xác khi chương trình hoàn tất bình thường:**

```text
published id=42
published value=84
synchronized count=40000
expected count=40000
```

Ví dụ đã được **biên dịch bằng `javac --release 17`** và chạy trên HotSpot ở ba chế độ: mặc định, `-Xint` và `-Xmixed`. Cả ba cho cùng kết quả logic này.

### 9.2. Vì sao `published id` và `published value` ổn định?

Producer tạo `Payload(42,84)` và **ghi volatile reference `published` sau khi constructor hoàn tất**.

Consumer đọc `published` **qua volatile read** cho tới khi nhận reference khác null. Từ volatile write đến subsequent volatile read có **synchronizes-with edge**; nhờ tính bắc cầu của HB, các fields được producer khởi tạo trước publication có thể được consumer đọc an toàn.

**Không phải vì object “nằm trên heap nên cả hai thread tự nhìn cùng state tức thời”**. Một field trên shared heap nhưng thiếu publication có thể không có HB guarantee tương ứng.

### 9.3. Vì sao dùng một biến local trong mỗi thread vẫn có shared object?

Producer có `localReference` trong frame riêng. Consumer cũng có một **biến local tên giống vậy** trong frame riêng. Chúng không phải cùng biến local. Producer đưa **reference tới Payload object** vào `published`, và consumer đọc reference đó.

Chính object được refer tới là shared; **JMM phân tích volatile field và object fields**, không một phép “chuyển biến local từ stack A sang stack B”.

### 9.4. Vì sao bộ đếm luôn 40.000?

Hai threads chạy 20.000 calls `increment()`, và mỗi call khóa **cùng `LOCK`**. Nhờ mutual exclusion, các increments không bị lost update. `join()` của main tạo quan hệ completion/happens-before cho main đọc `count` sau khi workers kết thúc.

`count` không cần khai báo volatile vì mọi updates được bảo vệ bằng monitor và main chỉ đọc sau successful joins. Nếu code mở rộng có thread thứ ba đọc count trong lúc workers chạy, phải xác định cơ chế synchronization phù hợp cho reader.

### 9.5. Vì sao spin-loop không phải mẫu production được khuyến nghị?

Consumer của demo chờ một volatile reference bằng vòng đọc liên tục. Nó giúp cô lập ví dụ về volatile, nhưng có thể **tốn CPU** và không có timeout/cancellation. Trong production, ưu tiên `CountDownLatch`, `BlockingQueue`, `Future`, `CompletableFuture` hoặc các APIs thích hợp để phối hợp thread lifecycle.

### 9.6. Vì sao `-Xint` và `-Xmixed` cho cùng logic?

JMM thuộc **ngữ nghĩa Java**; JIT có thể sắp xếp instructions/barriers tùy kiến trúc nhưng không được làm chương trình đồng bộ đúng quan sát kết quả không hợp lệ. Execution mode có thể làm khác timing, không được phá HB guarantees.

## 10. Data race: một thuộc tính của execution, không phải “CPU cache bị lỗi”

Một **data race** theo JLS §17.4.5 xảy ra khi có hai **conflicting accesses** đến cùng shared variable mà không được sắp thứ tự bằng happens-before. Ví dụ:

```java
static int total;

static void add() {
    total++;
}
```

Nếu hai threads gọi `add()` đồng thời mà không có synchronization, accesses có thể race. Mỗi phép `total++` gồm đọc, cộng, ghi, nên số cuối có thể **nhỏ hơn** số increments dự kiến.

### 10.1. Không thể chứng minh an toàn bằng “chạy thử 100 lần vẫn đúng”

Thread scheduling và optimizer decisions không bắt buộc tạo lost updates trong mọi lần chạy. Một chương trình có race vẫn là chương trình thiếu ràng buộc JMM, dù máy thử thường cho output mong muốn.

### 10.2. Data race trong Java không giống “undefined behavior” vô giới hạn của C/C++

Java Memory Model **vẫn đặt những ràng buộc** lên executions hợp lệ của chương trình racy (read-from legality và causality constraints). Không nên nói “data race khiến JVM được làm bất cứ điều gì, kể cả bịa giá trị tùy ý” theo kiểu đơn giản hóa từ một ngôn ngữ khác.

Tuy nhiên, **hành vi racy có thể rất bất ngờ** và không thích hợp để xây tính đúng của phần mềm.

### 10.3. “Data-race-free ⇒ sequential consistency” với điều kiện thích hợp

JLS §17.4 nêu rằng **chương trình được đồng bộ đúng**, tức mọi sequentially consistent execution của nó không có data races, sẽ có những behaviors xuất hiện **sequentially consistent (SC)**. Đây là **DRF–SC guarantee** của JMM.

Trực giác của sequential consistency: execution có thể được hiểu như một tổng thứ tự các actions nhất quán với program order của mỗi thread và reads quan sát write phù hợp trong thứ tự ấy.

**Cẩn trọng:** “DRF–SC” **không có nghĩa** mọi action thật sự được thực thi vật lý từng instruction một theo một global clock. Nó là **bảo đảm về behaviors được phép quan sát**.

## 11. Reordering litmus test: tại sao hai reads có thể cùng bằng 0?

Xét hai shared ints ban đầu bằng 0:

```java
int x = 0;
int y = 0;
```

Hai threads chạy các operations:

```text
Thread A               Thread B
--------               --------
x = 1;                 y = 1;
r1 = y;                r2 = x;
```

Nếu `x`/`y` là non-volatile fields chia sẻ và không có synchronization đặt thứ tự phù hợp, một số executions của chương trình có thể cho **`r1 == 0` và `r2 == 0`**, dù source code của từng thread ghi trước khi đọc.

### 11.1. Không suy “hai writes đã chạy trước hai reads” từ cấu trúc hai cột

Program order chỉ cho:

```text
A: write x -> read y
B: write y -> read x
```

Không có HB edges giữa threads để bắt buộc mỗi read nhìn thấy write của thread kia. Một execution hợp lệ có thể tương ứng reads quan sát giá trị khởi tạo. Đây là ví dụ loại *store buffering* thường dùng để thảo luận memory models.

### 11.2. Chuyển x và y sang volatile có thay đổi kết quả được phép không?

Với các volatile reads/writes thuộc synchronization order và semantics tương ứng, **`r1 == 0 && r2 == 0` bị loại khỏi những kết quả hợp lệ trong litmus test này**: để cả hai read thấy zero theo thứ tự toàn cục sẽ cần sắp hai writes/reads mâu thuẫn với program order và synchronization order.

**Không nên khái quát rằng volatile khiến mọi chương trình concurrent hoàn toàn tuần tự**. Đây là kết luận cho một mẫu thao tác cụ thể; compound actions, nhiều variables và các objects khác vẫn cần phân tích.

### 11.3. Vì sao không viết unit test “thử 1 triệu vòng phải thấy 0,0”?

Những outcomes hợp lệ không có nghĩa chúng phải được quan sát trong một số lần chạy hữu hạn. CPU, VM, JIT, OS scheduling có thể khiến kết quả đó hiếm hoặc không xuất hiện trong thử nghiệm. Để nghiên cứu concurrency litmus tests, dùng frameworks như **JCStress** thay vì tự viết vòng lặp rồi đưa ra khẳng định sai.

## 12. `final` fields: initialization safety không phải “mọi thứ bất biến”

JLS §17.5 định nghĩa **final field semantics** đặc biệt. Khi object được xây dựng **đúng cách**, không để `this` thoát khỏi constructor sớm, các final fields có bảo đảm khởi tạo đặc biệt giúp threads khác có thể nhìn thấy những giá trị final fields được thiết lập trong constructor dù cách publish không có synchronization thông thường.

Ví dụ:

```java
final class Configuration {
    final int port;
    final String name;

    Configuration(int port, String name) {
        this.port = port;
        this.name = name;
    }
}
```

Nếu constructor không leak `this`, final fields `port` và `name` hưởng các bảo đảm initialization safety theo JLS. Nhưng có các giới hạn quan trọng.

### 12.1. `final` không biến reference tới mutable object thành immutable deep graph

```java
final class Holder {
    final int[] values = new int[1];
}
```

`values` là final reference: reference không thể bị gán lại sau construction bình thường. Nhưng **`values[0]` vẫn mutable**.

Nếu nhiều threads cùng ghi/đọc `values[0]` mà thiếu synchronization, array element có thể có **data race**. Final field semantics không biến mọi mutation sau constructor thành safely synchronized.

### 12.2. Constructor escape phá những giả định an toàn

```java
final class BadPublication {
    final int value;

    BadPublication(java.util.List<BadPublication> registry) {
        registry.add(this); // publish this trước khi constructor hoàn tất
        value = 42;
    }
}
```

Đây là **anti-pattern minh họa**. Nếu một thread khác truy cập object qua registry trong khi constructor còn chạy, bảo đảm final field initialization safety có thể không áp dụng như trường hợp object được xây dựng đúng rồi mới publish.

### 12.3. `final` không thay publish protocol cho mọi trường hợp

Final fields có bảo đảm riêng, nhưng đối với state mutable thông thường, an toàn thread và visibility sau construction vẫn nên dựa vào **safe publication** hoặc cơ chế synchronization phù hợp.

## 13. Safe publication: làm sao đưa một object từ thread A sang thread B?

**Safe publication** nghĩa là có cơ sở JMM để thread B quan sát state đã được chuẩn bị bởi A, thay vì chỉ “tình cờ thấy reference khác null”.

Các cơ chế thường dùng:

- Ghi reference qua **volatile field**, đọc lại qua volatile read.
- Ghi/đọc state bên trong **`synchronized`** trên cùng monitor.
- Publish trước `Thread.start()` phù hợp với happens-before của start.
- Chờ hoàn thành bằng `Thread.join()` hoặc các cơ chế `Future.get()` có memory-consistency effects.
- Sử dụng `BlockingQueue`/concurrent collections/atomic APIs theo hợp đồng riêng của thư viện.
- Sử dụng class initialization an toàn khi áp dụng đúng.

### 13.1. Cẩn trọng với static field bình thường

```java
static Config config;

static void init() {
    config = new Config();
}
```

Đây là **snippet**, `Config` chưa định nghĩa. Nếu thread khác đọc `config` không synchronization, **không được tự khẳng định** mọi fields bình thường của Config đã được publish an toàn.

Nếu initialization diễn ra trong **class initialization** được JVM phối hợp theo JLS §12.4.2, tình hình khác: JVM cung cấp synchronization/happens-before phù hợp của class initialization. Nhưng một static field được **gán động về sau** không mặc nhiên được an toàn chỉ vì có từ khóa `static`.

### 13.2. Publication và mutation là hai giai đoạn riêng

Một object được publish an toàn tại thời điểm T chưa có nghĩa mọi writes sau T cũng được publish an toàn. Nếu thread A tiếp tục sửa normal fields sau publication còn thread B đọc chúng, cần synchronization tiếp theo.

### 13.3. Concurrent containers hỗ trợ HB theo hợp đồng API

Các `java.util.concurrent` containers như `BlockingQueue`, `ConcurrentHashMap` và các concurrency utilities có memory-consistency guarantees. Tùy API, hành động trước khi enqueue/put một object có thể happens-before những hành động sau khi thread khác thành công nhận truy cập object theo cách được quy định.

Đọc **API docs**, không suy bảo đảm chỉ từ tên “Concurrent”.

## 14. `Thread.start()` và `Thread.join()`: các HB edges không cần volatile field

### 14.1. Start

```java
class State {
    int value;
}

State state = new State();
state.value = 123;
Thread worker = new Thread(() -> System.out.println(state.value));
worker.start();
```

Đây là **snippet**, không phải chương trình độc lập. Những actions trước `worker.start()` trong thread gọi start happens-before actions trong thread mới. Vì vậy, nếu không có những concurrent writes khác tới `state.value`, thread worker có cơ sở JMM để đọc giá trị đã được chuẩn bị.

### 14.2. Join

```java
Thread worker = new Thread(() -> result[0] = 42);
worker.start();
worker.join();
System.out.println(result[0]);
```

Đây là snippet cần `result` và xử lý `InterruptedException`. Khi thread gọi join **trở về thành công và worker đã hoàn tất**, effects của worker được publish với thread joiner theo JMM.

Lưu ý: đọc array element **trong lúc worker đang ghi mà không có HB khác** vẫn là câu hỏi khác. `join()` không retroactively biến mọi race giữa các threads thành đúng.

### 14.3. Sleep không thay start/join/synchronization

```java
Thread.sleep(500);
System.out.println(sharedValue);
```

`Thread.sleep` không tạo ra HB edge tới write của thread khác chỉ vì đã trôi qua 500 ms. Một phương pháp polling dựa vào timing mà không có volatile/locks/concurrent APIs không được JMM bảo đảm.

## 15. Atomicity: loại biến và loại thao tác quan trọng hơn “nằm ở RAM”

```java
volatile int count;
count++;
```

Volatile read và write từng lần có atomicity/ordering phù hợp, nhưng **chuỗi đọc → cộng → ghi không atomic**.

`AtomicInteger` cung cấp các operations như:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();
int updated = counter.incrementAndGet();
```

`AtomicInteger.incrementAndGet` đảm bảo atomic read-modify-write theo API, thích hợp cho counter độc lập.

### 15.1. `long` và `double` non-volatile theo JLS §17.7

JLS §17.7 lịch sử cho phép **non-volatile `long` và `double`** accesses được xem như hai thao tác 32-bit trong một số implementations; vì thế **không nên coi atomic 64-bit access non-volatile là bảo đảm ngôn ngữ tuyệt đối trên mọi JVM**.

Trong nhiều HotSpot/JDK hiện đại, thực tế xử lý 64-bit aligned values có thể atomic do implementation/architecture. Nhưng **đó không thay đổi tính chất của JLS guarantee**. Reads/writes volatile `long` và `double` là atomic theo đặc tả.

### 15.2. Không đồng nhất atomicity với visibility

Một phép đọc/ghi atomic một field không đủ để bảo đảm thread khác nhìn thấy cùng giá trị vào thời điểm mong muốn nếu thiếu ordering/visibility phù hợp.

### 15.3. Cùng dữ liệu, nhiều fields

Nếu một invariant gồm `balance` và `version` phải thay đổi atomically cùng nhau, chỉ dùng hai volatile fields không tự biến **cặp cập nhật** thành một transaction atomic. Cần cùng lock, immutable snapshot được publish, hoặc cơ chế thiết kế phù hợp.

## 16. JMM không cho phép suy đoán CPU cache line theo thread

Một số bài viết giản lược:

```text
Thread A -> CPU core A -> L1 cache A
Thread B -> CPU core B -> L1 cache B
volatile -> flush RAM
```

Đây là **sơ đồ học phần cứng**, không là định nghĩa JMM. Nó bỏ qua:

- Hai Java threads có thể **chạy luân phiên trên cùng core**, hoặc di chuyển core.
- CPUs có nhiều mức cache, coherence protocols, store buffers và các quy tắc memory ordering riêng.
- OS có thể preempt threads; JVM có thể execute compiled/interpreted code khác nhau.
- Object có thể nằm trong heap, registers hoặc đã được scalar replace trong optimized path.
- Volatile/barriers có thể được implement khác giữa x86-64, AArch64 và platforms khác.

**Cách giải đúng:** dựa vào JMM để xác định legal outcomes; nếu tối ưu hiệu năng ở cấp CPU, phân tích **implementation** sau khi correctness đã đúng.

### 16.1. “Main memory” trong JMM không đồng nghĩa mỗi thao tác vào DRAM thật

Những mô hình giáo khoa có thể nói “working memory của thread” và “main memory” để xây trực giác. Nhưng JLS §17.4 hiện hành định nghĩa JMM thông qua **actions/executions/happens-before**, không hứa mỗi biến có một “bản chính” đặt cố định tại DRAM rồi volatile buộc flush toàn bộ.

### 16.2. Cache coherence không thay thế happens-before

Ngay cả khi CPU cache coherence đảm bảo một số properties cho single memory locations, **ordering across multiple locations** và compiler transformations vẫn là vấn đề. Một chương trình Java có data race không trở thành hợp lệ chỉ vì chạy trên “CPU có cache nhất quán”.

## 17. False sharing: liên quan hiệu năng phần cứng, không cùng khái niệm với data race

**False sharing** xảy ra khi những threads sửa các variables/fields khác nhau nhưng chúng nằm gần nhau trên cùng cache line, gây cache-line traffic không mong muốn.

Ví dụ ý tưởng:

```text
Cache line:
+-------------------+-------------------+
| counter của A     | counter của B     |
+-------------------+-------------------+
       A ghi                B ghi
   (hai biến khác nhau, có thể không data race)
       |
       v
  Cache coherence traffic ảnh hưởng throughput
```

Có thể có **false sharing mà không có data race** vì hai threads sửa **các variables khác nhau**. Ngược lại, data race có thể tồn tại dù hai fields nằm ở hai cache lines khác nhau.

- **JMM correctness:** có conflicting accesses thiếu HB hay không?
- **Hardware performance:** các memory locations cùng cache line gây tranh chấp coherence không?

**Đừng giải một vấn đề correctness bằng cách thêm padding cache line**. Padding có thể giúp throughput trong một số tình huống, không tạo HB edges.

## 18. Reordering và compiler optimizations trên HotSpot

Một JIT compiler có thể:

- Hoist loads ra khỏi loop nếu không có synchronization buộc phải thấy updates từ threads khác.
- Inline methods và scalar-replace objects.
- Remove redundant writes/reads nếu observable behavior cho phép.
- Coalesce/canonicalize computations.
- Chèn barriers để hiện thực volatile/locks/atomic APIs theo platform.
- Deoptimize/recompile khi một giả định tối ưu không còn phù hợp.

Ví dụ:

```java
boolean done;

void waitUntilDone() {
    while (!done) {
        // không volatile, không synchronization
    }
}
```

Nếu thread khác ghi `done = true` thiếu synchronization, loop này **không có guarantee sẽ kết thúc**. Không nên kết luận “chắc sau vài milliseconds cache coherence tự làm nó thấy true”.

### 18.1. JIT optimization không được làm chương trình đồng bộ đúng thành sai

Nếu dùng volatile, monitor hay concurrent API đúng cách, implementation phải giữ những ordering/visibility constraints mà JMM quy định. C2 có thể loại một lock chỉ khi chứng minh việc loại đó không đổi behavior hợp lệ — không được “bỏ khóa vì thấy tốn CPU”.

### 18.2. Interpreter-only vẫn tuân JMM

Chạy:

```bash
java -Xint MemoryModelDemo
java -Xmixed MemoryModelDemo
```

Hai execution modes phải duy trì JMM semantics. Chạy `-Xint` **không phải cách chữa data race**: chương trình racy vẫn thiếu bảo đảm, dù interpreter vô tình ít reorder hơn optimizing compiler.

### 18.3. Bytecode không cố định CPU memory barriers

Trong class file, `synchronized` block có monitor bytecodes, volatile access có field access instructions và metadata flags, nhưng JIT/hardware lowering có thể rất khác theo architecture.

`javap -c` cho biết bytecode operations, **không phải một bản dump của memory instructions thực tế** sau C2 optimization.

## 19. GC reachability và JMM là hai vấn đề riêng

GC giải bài toán: **object nào còn reachable và khi nào heap storage có thể được thu hồi?** JMM giải bài toán: **read/write observations giữa threads nào là hợp lệ?**

Ví dụ:

```java
static Object shared;

static void publish() {
    shared = new Object();
}
```

Đây là snippet minh họa. Việc object được gán cho static field có thể giữ nó reachable; nhưng nếu thread khác đọc `shared` thiếu synchronization, **không có nghĩa việc publish state đã tuân JMM** chỉ vì object “sống trên heap”.

### 19.1. Object reachable không phải safely published

Một static list giữ reference không tự chứng minh reads/writes vào các mutable fields của object là thread-safe. Reachability và happens-before cần phân tích riêng.

### 19.2. GC không phải cơ chế visibility của business state

Một GC pause/safepoint có thể ảnh hưởng thực thi của VM, nhưng **không thay thế** synchronized/volatile/concurrent APIs theo JMM. Đừng thiết kế concurrency trên giả định “GC sẽ đồng bộ mọi cache nên state sẽ đúng”.

### 19.3. Cleaner và `Reference.reachabilityFence` không thay locks

Các APIs liên quan reachability hỗ trợ lifecycle của objects/native resources, không tự cung cấp atomicity cho shared mutable counters hoặc transaction state.

## 20. Những sai lầm kinh điển

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “JMM là hình heap ở giữa, mỗi thread một stack.” | Hình đó mô tả runtime data areas; JMM định nghĩa legal inter-thread observations. |
| “Biến local luôn thread-safe nên mọi object local đều safe.” | Local reference có thể trỏ tới shared mutable object. |
| “Field nằm ở heap nên mọi thread nhìn thấy giá trị mới ngay.” | Heap shared không tự tạo happens-before. |
| “Volatile luôn flush hết CPU caches ra RAM.” | JMM chỉ quy định synchronization/visibility/ordering semantics. |
| “Volatile counter++ là atomic.” | Volatile không tự làm compound read-modify-write atomic. |
| “Thread.sleep đảm bảo thấy write của thread khác.” | Sleep không tạo HB edge với write thông thường. |
| “Dùng synchronized với hai object khác nhau vẫn bảo vệ cùng static counter.” | Cần đồng bộ theo cùng monitor hoặc API thích hợp. |
| “Nếu code chạy đúng 100 lần thì không có data race.” | Một race có thể rất hiếm hoặc không lộ trong thử nghiệm. |
| “Mọi chương trình Java luôn sequentially consistent.” | DRF-SC đòi hỏi đồng bộ đúng; chương trình racy có behaviors khác. |
| “Data race Java cho phép bất kỳ giá trị tùy ý.” | JMM vẫn có well-formed execution/causality constraints. |
| “Final reference làm cả mutable graph bất biến.” | Final field không ngăn mutations của referenced object. |
| “Thấy reference khác null là object đã safely published.” | Cần HB path hoặc dựa đúng final-field semantics. |
| “Mỗi volatile read bắt buộc một full CPU fence instruction.” | Machine implementation phụ thuộc architecture/optimizer. |
| “CPU cache coherence tự thay JMM.” | Coherence không thay synchronization semantics của Java. |
| “False sharing là data race.” | Cache-line contention có thể xảy ra trên những variables khác nhau mà không có data race. |
| “Heap object luôn materialized ở DRAM.” | JIT có thể scalar-replace hoặc giữ data trong registers khi hợp lệ. |
| “-Xint cho phép bỏ volatile vì interpreter ít tối ưu.” | JMM không đổi theo interpreter/JIT mode. |
| “Class static field luôn safely published dù gán động ở bất kỳ thread nào.” | Class initialization có rules riêng; gán động thiếu sync vẫn có thể race. |
| “Thread.join chỉ đợi, không có memory effect.” | Join thành công có HB semantics với actions của thread đã kết thúc. |
| “GC là memory barrier cho business threads.” | GC scheduling không thay explicit concurrency guarantees. |
| “long/double thường atomic trên x64 nên Java Specification bảo đảm mọi nonvolatile 64-bit.” | JLS §17.7 cho phép non-atomic treatment với non-volatile long/double. |

## 21. Các tình huống thiết kế áp dụng JMM

### Tình huống A — Một request xây DTO rồi đưa sang worker thread

Nếu toàn bộ DTO được tạo trước `thread.start()` và không có concurrent mutations sai quy tắc, start HB có thể publish state cho worker. Nếu dùng executor pool, cần dựa vào **memory consistency effects của executor/queue APIs**, không giả định worker thread được tạo mới cho mỗi request.

### Tình huống B — Service khởi tạo singleton một lần

Có thể dùng **class initialization idiom** hoặc safe publication qua volatile/locks. Không nên viết lazy initialization với normal shared reference rồi giả định “chỉ có hai threads nên chắc ổn”.

### Tình huống C — Shared counter

Nếu cần atomic increment, dùng `AtomicInteger` hoặc monitor. Nếu throughput contention cao và chỉ cần tổng thống kê có semantics phù hợp, `LongAdder` đáng cân nhắc; nhưng phải đọc consistency behavior của `sum()` dưới concurrent updates.

### Tình huống D — Producer đưa message tới consumer

Sử dụng `BlockingQueue` để có ordering/coordination và memory effects theo API thay vì tự viết một non-volatile field + sleep-loop.

### Tình huống E — Immutable value object

Dùng final fields và constructor không leak `this`, tránh exposing mutable internal arrays trực tiếp. Nếu object chứa mutable fields, vẫn cần safe publication và mutation discipline theo nhu cầu.

### Tình huống F — Debug trên một CPU khác

Một code “đúng trên x86” nhưng thiếu HB có thể lộ lỗi trên architecture khác hoặc HotSpot/JDK khác. Sửa correctness bằng đúng memory-model rules, **không bằng thêm sleeps hay phụ thuộc cache layout**.

## 22. Công cụ và cách xác minh concurrency

### 22.1. `javap`

```bash
javap -c -p MemoryModelDemo
```

Dùng để đọc bytecode và cấu trúc methods, nhưng nó **không nói chính xác CPU instructions/barriers** mà HotSpot sử dụng sau JIT.

### 22.2. Java Flight Recorder và profiler

JFR có các sự kiện về thread activity, monitor contention và một số runtime events theo configuration. Nó giúp trả lời “threads có đang chờ monitor nhiều không?” nhưng không chứng minh một chương trình không có data race.

### 22.3. Thread dumps

Thread dumps cho thấy trạng thái tại một thời điểm như RUNNABLE/BLOCKED/WAITING, stacks/locks tùy tool. **Một thread dump không phải bằng chứng an toàn JMM**: data races là thuộc tính của accesses/orderings, không phải chỉ số threads đang blocked.

### 22.4. JCStress

**JCStress** là bộ công cụ OpenJDK để thử nghiệm các outcomes của concurrency litmus tests dưới nhiều interleavings/JIT/hardware conditions.

- Dùng JCStress để nghiên cứu những kết quả JMM cho phép hoặc cấm.
- Một outcome hợp lệ có thể không xuất hiện sau nhiều runs.
- JCStress không thay thế **logic proof** dựa trên JLS §17.4.
- Tránh biến một kết quả “chưa quan sát được” thành guarantee.

### 22.5. JMH

**JMH** tập trung vào microbenchmark performance, phù hợp đo overhead của volatile/locks/atomics trong các tình huống được kiểm soát. **JCStress là correctness/stress**, **JMH là performance benchmark**: hai công cụ trả lời hai câu hỏi khác nhau.

### 22.6. Static analyzers

IDE/static analysis tools có thể tìm những dấu hiệu concurrency bug: non-volatile flags, unsafe publication, lock misuse. Nhưng việc absence of warnings **không chứng minh toàn chương trình data-race-free**.

## 23. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** JMM và JVM heap là một khái niệm không?

**Đáp án:** Không. JMM định nghĩa allowed observations giữa threads; JVM heap là runtime data area dùng cho class instances/arrays theo JVMS.

**Câu 2.** Biến local `Box b` ở thread A có thể tham chiếu tới cùng Box với local `Box c` ở thread B không?

**Đáp án:** Có. Local variables riêng nhưng references có thể trỏ tới một shared object.

**Câu 3.** Tại sao `ready = true` sau `data = 42` không đủ publish nếu cả hai là normal fields?

**Đáp án:** Không có HB edge giữa writes của producer và reads của consumer; JMM có thể cho phép quan sát thiếu ordering/visibility mong muốn.

**Câu 4.** Volatile write → volatile read cùng variable tạo quan hệ gì?

**Đáp án:** Có synchronizes-with edge khi read là subsequent theo synchronization order, do đó đóng góp vào happens-before.

**Câu 5.** `volatile int counter; counter++;` có atomic không?

**Đáp án:** Không. `++` là compound read-modify-write, có thể lost updates khi nhiều threads.

**Câu 6.** `Thread.start()` có HB effect không?

**Đáp án:** Có. Những actions xảy ra trước start trong thread gọi start happens-before actions của thread được start theo quy tắc JLS.

**Câu 7.** `Thread.join()` thành công có effect nào?

**Đáp án:** Actions của thread đã kết thúc happens-before actions tiếp theo của thread quan sát termination/join thành công.

**Câu 8.** Cùng source synchronized nhưng dùng hai lock objects khác nhau có bảo đảm atomic shared counter không?

**Đáp án:** Không. Mutual exclusion yêu cầu các threads phối hợp qua cùng monitor hoặc cơ chế đồng bộ tương đương.

**Câu 9.** Thread.sleep có tạo HB với việc thread khác ghi normal field không?

**Đáp án:** Không chỉ vì ngủ một khoảng thời gian.

**Câu 10.** Khác biệt false sharing và data race?

**Đáp án:** False sharing là cache-line contention ảnh hưởng performance; data race là conflicting shared-variable accesses không được HB order.

**Câu 11.** Tại sao `final int[] values` không biến array immutable?

**Đáp án:** `final` áp dụng reference field; array elements vẫn mutable.

**Câu 12.** Việc publish `this` từ constructor nguy hiểm ở đâu?

**Đáp án:** Threads khác có thể quan sát object trước khi initialization hoàn tất; final-field initialization safety có thể không áp dụng như construction đúng.

**Câu 13.** Một object vẫn reachable từ static field có nghĩa mọi normal fields được safely published không?

**Đáp án:** Không. Reachability khác với HB/safe publication.

**Câu 14.** `-Xint` có thay JMM semantics không?

**Đáp án:** Không. Interpreter/JIT đều phải tuân legal Java executions.

**Câu 15.** Volatile có bắt buộc write-thẳng-DRAM trên mọi platform không?

**Đáp án:** Không. JMM quy định ordering/visibility semantics, JVM chọn implementation thích hợp.

**Câu 16.** Long/double non-volatile reads/writes có 64-bit atomicity portable theo JLS không?

**Đáp án:** Không thể cam kết cho mọi VM. JLS §17.7 cho phép non-atomic treatment; volatile long/double có atomicity guarantee.

**Câu 17.** Nếu code không có data races theo điều kiện JMM, nó được bảo đảm gì về behaviors?

**Đáp án:** Properly synchronized/data-race-free programs có **sequential consistency guarantee** về observable behaviors theo JMM.

**Câu 18.** Chỉ thấy giá trị đúng 1.000 lần có chứng minh code data-race-free không?

**Đáp án:** Không. Outcomes phụ thuộc scheduling, JIT và hardware; cần phân tích HB và synchronization.

**Câu 19.** Hai threads đọc/ghi `array[0]` khác với mỗi thread chỉ ghi `array[0]` và `array[1]` ở đâu?

**Đáp án:** Truy cập cùng element có thể conflicting; elements khác nhau là những variables khác, dù còn phải xét data sharing ở cấp thuật toán.

**Câu 20.** JCStress và JMH khác nhau thế nào?

**Đáp án:** JCStress khảo sát concurrency correctness/allowed outcomes; JMH đo performance theo phương pháp microbenchmark.

**Câu 21.** “Happens-before” có nghĩa action A chắc chạy trước B theo đồng hồ vật lý trong mọi optimization không?

**Đáp án:** Không. Nó là quan hệ semantics/ràng buộc outcomes; implementation có thể reorder vật lý nếu không gây execution bất hợp lệ.

**Câu 22.** Vì sao synchronized count trong demo là 40.000 mà không cần count volatile?

**Đáp án:** Hai worker threads cùng dùng monitor cho increments; main chỉ đọc sau successful joins tạo HB phù hợp.

## 24. Checklist khi phân tích lỗi đa luồng thực tế

1. Xác định **shared variables**: instance fields, static fields, array elements.
2. Với từng variable, liệt kê threads có thể read/write nó.
3. Tìm **conflicting accesses**, xem có ít nhất một write không.
4. Vẽ **happens-before graph** dựa trên start/join, volatile, monitor và concurrent APIs.
5. Không dùng “local variable ở stack” làm chứng minh data không shared.
6. Phân biệt **ownership** của object với vị trí vật lý object.
7. Nếu nhiều threads cùng increment, kiểm tra atomicity của **compound operations**.
8. Nếu publish object, kiểm tra constructor có leak `this` không, final field semantics và publication path.
9. Với immutable objects, kiểm tra internal mutable arrays/lists có lộ reference hay không.
10. Với `synchronized`, đảm bảo các threads khóa **cùng object monitor**.
11. Với volatile, nhớ chỉ volatile variable có ordering semantics; post-publication mutations cần xử lý riêng.
12. Không dùng sleep/spin timing làm cách tạo HB.
13. Đừng đồng nhất GC safepoint hoặc heap scan với business synchronization.
14. Không kết luận lỗi do CPU cache trước khi xác định legal JMM behaviors.
15. Chạy concurrency litmus tests bằng JCStress khi cần, nhưng vẫn phân tích đúng JLS.
16. Dùng JMH nếu đang hỏi về performance của volatile/locks, không dùng nó chứng minh không có races.
17. Khi nâng JDK/đổi architecture, kiểm thử lại nhưng giữ logic đúng **không phụ thuộc compiler timing**.
18. Đọc nguồn chuẩn **JLS §17.4/§17.5** và **JVMS §2.5** thay vì chỉ dựa vào sơ đồ heap/stack.

### Kết luận

```text
SƠ ĐỒ JVM:                 JAVA MEMORY MODEL:
  Thread A stack             Actions: reads/writes/sync
  Thread B stack             Program order
  Shared heap                Synchronization order
  Frames/locals              Synchronizes-with
                             Happens-before
          |                        |
          +-----------+------------+
                      |
          Correct Java program behavior
                      |
          Runtime hiện thực trên CPU:
          registers, caches, virtual memory,
          HotSpot JIT, barriers, GC...

Heap shared KHÔNG tự bảo đảm safe publication.
Stack riêng KHÔNG làm object được trỏ tới private.
Volatile/synchronized KHÔNG được định nghĩa bằng “flush RAM”.
```

**Thông điệp cần nhớ:** **Java Memory Model không phải bản đồ heap–stack hay mô hình CPU cache.** JMM quy định **threads được phép quan sát những reads/writes nào**, còn JVM runtime areas mô tả nơi lưu dữ liệu ở cấp trừu tượng, và phần cứng/JIT quyết định cách thực thi. Khi đánh giá correctness của code đa luồng, hãy **chứng minh bằng happens-before, atomicity và safe publication**, không suy luận từ nơi đặt biến hoặc thời điểm “flush cache”.

### Tài liệu chuẩn và chuyên sâu

- [JLS 17.4 — Memory Model, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): actions, shared variables, program order, synchronization order, happens-before và data races.
- [JLS 17.5 — final Field Semantics, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): initialization safety, freeze action và không publish `this` trước khi constructor hoàn tất.
- [JLS 17.7 — Non-Atomic Treatment of double and long, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.7): non-volatile 64-bit access và volatile atomicity.
- [JVMS 2.5 — Run-Time Data Areas, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): PC, JVM stacks, heap, method area và native method stacks.
- [JVMS 2.6 — Frames, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): local variables, operand stack, frames.
- [JLS 12.4.2 — Detailed Initialization Procedure, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class initialization synchronization.
- [java.util.concurrent package specification, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects của concurrent utilities.
- [AtomicInteger API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic operations.
- [OpenJDK JCStress](https://openjdk.org/projects/code-tools/jcstress/): kiểm thử các allowed outcomes của concurrency litmus tests.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmark performance trong Java.
