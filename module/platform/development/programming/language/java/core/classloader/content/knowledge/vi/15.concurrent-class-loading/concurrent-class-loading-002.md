# getClassLoadingLock và khóa theo tên lớp trong Java ClassLoader

## 1. Bài toán: nhiều thread cùng yêu cầu nạp lớp

Một ứng dụng Java có thể có nhiều thread đồng thời gọi:

~~~java
Class<?> a = loader.loadClass("demo.plugin.Alpha");
~~~

Với một custom `ClassLoader`, thao tác tìm và định nghĩa một lớp không chỉ là đọc file `.class`. JVM phải duy trì **định danh kiểu**, **loading constraints**, mối quan hệ với **parent loader** và trạng thái một lớp đã được nạp hay chưa. Nếu hai thread cùng thấy “chưa có `demo.plugin.Alpha`” rồi đều gọi `defineClass`, một thread có thể thành công, thread còn lại gặp `LinkageError` vì cố định nghĩa trùng tên trong cùng loader.

Tuy nhiên, nếu một thread đang nạp `demo.plugin.Alpha`, tại sao thread khác muốn nạp `demo.plugin.Beta` cũng phải đợi? Java hỗ trợ hai cách khóa:

- **ClassLoader không đăng ký parallel-capable:** thao tác `loadClass` mặc định đồng bộ trên **chính đối tượng ClassLoader**, tức một khóa chung cho mọi tên lớp trong loader đó.
- **ClassLoader đã đăng ký parallel-capable:** `getClassLoadingLock(name)` mặc định trả **một đối tượng khóa dành riêng cho tên class đó**. Hai thread hỏi **cùng tên** sẽ lấy cùng khóa; các tên **khác nhau** có khóa khác nhau.

Hai cơ chế đều có nhiệm vụ bảo vệ tính nhất quán khi nạp class. Khóa mịn hơn theo tên class giúp nhiều tên khác nhau **có thể** được xử lý song song, không có nghĩa đảm bảo nạp nhanh hơn trong mọi chương trình.

**Điểm nhớ ngắn gọn:**

~~~text
Non-parallel-capable loader L:
  getClassLoadingLock("a.A") == L
  getClassLoadingLock("b.B") == L
  => các tên lớp cùng tranh một monitor

Parallel-capable loader L:
  getClassLoadingLock("a.A") == lock_A
  getClassLoadingLock("a.A") == lock_A
  getClassLoadingLock("b.B") == lock_B
  lock_A != lock_B
  => cùng tên vẫn tuần tự, khác tên có thể tiến hành đồng thời
~~~

Không có “một khóa toàn JVM cho tên class”. Các khóa là thành phần của **mỗi ClassLoader instance**. Hai loader khác nhau có thể định nghĩa hai lớp cùng binary name nhưng trở thành hai runtime types khác nhau.

## 2. `ClassLoader.getClassLoadingLock(String className)` là gì?

API được bổ sung từ **Java 7**:

~~~java
protected Object getClassLoadingLock(String className)
~~~

Đây là **protected instance method** của `java.lang.ClassLoader`. Mục đích của nó là trả một đối tượng làm **monitor lock** cho hoạt động nạp class có tên nhị phân `className`.

Theo [Java SE 21 — ClassLoader#getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)):

1. Nếu **instance ClassLoader đã đăng ký parallel-capable**, phương thức trả đối tượng chuyên biệt gắn với tên class chỉ định.
2. Nếu **không parallel-capable**, phương thức trả **`this`**, tức chính ClassLoader instance.
3. Nếu loader parallel-capable và `className == null`, phương thức ném `NullPointerException` theo hợp đồng.
4. Vì đây là protected method, code bên ngoài không thể tùy ý gọi qua một `ClassLoader` bất kỳ. Subclass có thể gọi `getClassLoadingLock` để phục vụ logic nạp lớp của mình.

API trả về đối tượng khóa, **không thực hiện việc nạp lớp** và **không tự động khóa thread ngay khi được gọi**. Chỉ có `synchronized(lock)` hoặc đoạn mã tương đương sử dụng monitor đó mới tạo vùng đồng bộ.

### 2.1. Khóa theo tên được sử dụng khi nào?

Triển khai mặc định `ClassLoader.loadClass(String, boolean)` đồng bộ trên:

~~~java
synchronized (getClassLoadingLock(name)) {
    // kiểm tra class đã nạp;
    // ủy quyền cho parent;
    // nếu cần thì gọi findClass;
    // resolve nếu được yêu cầu;
}
~~~

Đây là **mã giải thích phạm vi khóa**, không phải toàn bộ mã nguồn thực thi của JDK.

Vì JVM có thể được nhiều thread yêu cầu load cùng tên, thao tác **kiểm tra `findLoadedClass` + quyết định `findClass`/`defineClass`** cần bảo vệ nhất quán. Nếu tách phần kiểm tra và phần define bằng hai khóa không liên quan, sẽ xảy ra tình huống race.

### 2.2. Vì sao không chỉ dùng `synchronized(this)`?

`synchronized(this)` là khóa trên toàn ClassLoader instance. Nó phù hợp với loader **không parallel-capable**, nhưng có thể gây **tranh chấp không cần thiết** nếu một loader cần nạp nhiều tên class độc lập.

Ví dụ:

~~~text
Thread-1 muốn plugin.First:
   giữ monitor Loader L
   đọc file/classpath chậm trong khi giữ L

Thread-2 muốn plugin.Second:
   phải đợi monitor L, dù không cùng class name

Nếu L parallel-capable và dùng lock riêng:
   Thread-1 giữ lock_First
   Thread-2 giữ lock_Second
   => có thể cùng tiến hành các bước tìm/nạp tương ứng
~~~

Lợi ích chỉ là **khả năng tiến hành đồng thời**. Chúng vẫn có thể phải chờ nhau khi cùng phụ thuộc parent loader không parallel-capable, dùng cache/JAR/resource lock chung, gặp loading constraints hoặc thực hiện logic đồng bộ khác.

## 3. Loader nào được dùng khóa riêng?
Một `ClassLoader` subclass chỉ trở thành **parallel-capable** khi đăng ký thành công bằng `protected static registerAsParallelCapable()`, thường gọi trong static initializer của chính subclass trước khi tạo instance. Mọi superclass loader trong chuỗi (trừ `Object`) cũng phải đã đăng ký. Bản thân `ClassLoader` gốc đã đăng ký nhưng trạng thái này **không tự truyền cho subclass**.
```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError("Registration failed");
    }
}
```
Đặt block trong custom `ClassLoader`; kiểm chứng ở runtime bằng `loader.isRegisteredAsParallelCapable()`. Nếu một superclass tự viết chưa đăng ký, lời gọi ở child trả `false`. Bài tiếp theo về `registerAsParallelCapable` đào sâu những điều kiện này; trọng tâm ở đây là **`getClassLoadingLock` trả lock nào** và cách phối hợp cùng tên.

## 4. Vì sao phải kiểm tra `findLoadedClass` dưới đúng khóa?

Algorithm chuẩn của `loadClass` có thể hình dung:

~~~text
loadClass(name, resolve)
  synchronized (getClassLoadingLock(name)):
      c = findLoadedClass(name)

      if c == null:
          thử parent.loadClass(name)

      if vẫn null:
          c = findClass(name)

      if resolve:
          resolveClass(c)

      return c
~~~

`findLoadedClass(name)` trả `Class<?>` nếu class cùng binary name đã được JVM ghi nhận cho **loader này như initiating loader**, không nhất thiết chỉ những class do loader này trực tiếp `defineClass`. Khi loader đã tìm thấy class qua parent, nó cũng cần tránh cố định nghĩa tên ấy một lần nữa.

### 4.1. Khi hai threads hỏi cùng một class

~~~text
Thread A: loadClass("pkg.Service")
  lock_Service acquired
  findLoadedClass == null
  parent không thấy
  findClass -> defineClass -> Class C
  release lock_Service

Thread B: loadClass("pkg.Service")
  chờ lock_Service
  sau đó findLoadedClass trả Class C
  không gọi defineClass lần nữa
  trả cùng Class C
~~~

Kết quả đúng là **hai threads nhận cùng `Class<?>`** từ cùng loader; số lần thực sự gọi `findClass` để định nghĩa class đó thường là **một lần** trong cấu hình thí nghiệm phù hợp.

### 4.2. Nếu hai threads hỏi hai tên khác nhau

~~~text
Thread A: lock_Alpha => load Alpha
Thread B: lock_Beta  => load Beta
~~~

Với loader parallel-capable, **khác tên, khác khóa** cho phép các thao tác diễn ra đồng thời. Nếu cả hai cùng cần parent, đọc chung cache hoặc có circular dependencies, việc chờ vẫn có thể xảy ra. Không khẳng định có phép thử thời gian nào sẽ luôn cho speedup 2×.

### 4.3. `getClassLoadingLock` không thay thế kiểm tra cache

Nếu custom loader viết:

~~~java
synchronized (getClassLoadingLock(name)) {
    byte[] bytes = readClassBytes(name);
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

thì đoạn mã trên **chưa đúng**: khi lần gọi thứ hai đã vào khóa, nó vẫn luôn `defineClass` lần nữa nếu không kiểm tra class đã nạp. Đoạn trên là **mã sai có chủ đích**, `readClassBytes` chỉ là tên helper giả, không phải API có sẵn.

Cách đúng là sử dụng `loadClass` mặc định — hoặc, khi override thật sự cần thiết, đảm bảo nguyên tắc **kiểm tra `findLoadedClass` trong cùng vùng khóa**, xử lý delegation, gọi `findClass` chỉ khi cần, rồi resolve phù hợp.

## 5. Thực hành Java 17+: kiểm tra khóa chung và khóa theo tên

Thí nghiệm sau không dùng thư viện bên ngoài, chỉ cần JDK 17+. Chúng ta tạo:

1. `SerialLoader` **không đăng ký parallel-capable** để cho thấy mọi tên class dùng chính loader object làm lock.
2. `ParallelLoader` **đăng ký parallel-capable** để quan sát khóa ổn định theo từng tên class.
3. Tám tasks cùng gọi `ParallelLoader.loadClass("demo.plugin.Alpha")`, chứng minh chúng nhận **cùng `Class<?>`** và custom `findClass` được gọi một lần.

Phần kiểm chứng không dựa vào trình tự scheduling của thread, chỉ so sánh danh tính đối tượng và đếm số lần `findClass` bằng `AtomicInteger`.

### 5.1. Cây thư mục

~~~text
demo/
├── src/
│   ├── app/
│   │   └── LockDemo.java
│   └── plugin/
│       └── demo/
│           └── plugin/
│               └── Alpha.java
└── build/
    ├── app/
    └── plugin/
~~~

**Bắt buộc:** khi chạy, `-cp` chỉ có `build/app`, không có `build/plugin`. Nếu vô tình thêm `build/plugin` vào system classpath, parent có thể tìm `Alpha` trước, khiến `ParallelLoader.findClass` không được gọi và phép đo mất ý nghĩa.

### 5.2. Tệp `src/plugin/demo/plugin/Alpha.java`

~~~java
package demo.plugin;

public class Alpha {
    public String name() {
        return "alpha";
    }
}
~~~

Đây là class mà `ParallelLoader` sẽ nạp bằng cách đọc file bytes từ `build/plugin`.

### 5.3. Tệp `src/app/LockDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LockDemo {
    static final String NAME = "demo.plugin.Alpha";

    static final class SerialLoader extends ClassLoader {
        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static final boolean REGISTERED = registerAsParallelCapable();
        final Path root;
        final AtomicInteger findCalls = new AtomicInteger();

        ParallelLoader(Path root) {
            super(LockDemo.class.getClassLoader());
            this.root = root;
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            findCalls.incrementAndGet();
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel = new ParallelLoader(Path.of("build/plugin"));

        System.out.println("serialSameLock="
                + (serial.lock(NAME) == serial.lock("demo.plugin.Beta")));
        System.out.println("serialLockIsLoader="
                + (serial.lock(NAME) == serial));
        System.out.println("parallelRegistered="
                + (ParallelLoader.REGISTERED
                        && parallel.isRegisteredAsParallelCapable()));
        System.out.println("parallelSameNameSameLock="
                + (parallel.lock(NAME) == parallel.lock(NAME)));
        System.out.println("parallelDifferentNamesDifferentLock="
                + (parallel.lock(NAME) != parallel.lock("demo.plugin.Beta")));
        System.out.println("parallelLockNotLoader="
                + (parallel.lock(NAME) != parallel));

        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Class<?>>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                futures.add(executor.submit(() -> {
                    start.await();
                    return parallel.loadClass(NAME);
                }));
            }
            start.countDown();

            Class<?> first = futures.get(0).get();
            boolean allSame = true;
            for (Future<Class<?>> f : futures) {
                allSame &= (f.get() == first);
            }
            System.out.println("allThreadsSameClass=" + allSame);
            System.out.println("findClassCalls=" + parallel.findCalls.get());
            System.out.println("loaderOwnsClass="
                    + (first.getClassLoader() == parallel));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Giải thích các phần quan trọng:

- `SerialLoader` không đăng ký parallel capability nên `getClassLoadingLock` trả lại **`this`** cho mọi tên, kể cả khi class chưa được load.
- `ParallelLoader.REGISTERED` được tính khi class được khởi tạo, **trước khi constructor của instance được gọi**. Vì superclass `ClassLoader` đã parallel-capable, registration thành công.
- `lock(...)` chỉ là method package-private cung cấp quyền đọc protected method cho bài thử; **không tự nạp một class**.
- `ParallelLoader.findClass` chỉ xử lý đúng `NAME`, còn `loadClass` vẫn dùng triển khai mặc định của JDK với `findLoadedClass`, delegation và khóa theo tên.
- `AtomicInteger` đếm số lần custom `findClass` được gọi cho `Alpha`; không phải số lần API `loadClass` được gọi.
- `CountDownLatch start` cho tám tasks cùng bắt đầu tìm class sau khi đã được gửi vào thread pool. Do JDK bảo vệ đường `loadClass`, chỉ một task cần tự define class `Alpha`; các task còn lại nhận `Class<?>` đã có.
- `Future.get()` đợi kết quả và làm lộ exceptions thay vì in không theo thứ tự. `finally` đảm bảo executor được shutdown.

### 5.4. Lệnh biên dịch/chạy

Trong thư mục `demo` trên Linux/macOS:

~~~sh
mkdir -p build/plugin build/app
javac --release 17 -d build/plugin src/plugin/demo/plugin/Alpha.java
javac --release 17 -d build/app src/app/LockDemo.java
java -cp build/app LockDemo
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/app | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Alpha.java
javac --release 17 -d build/app src/app/LockDemo.java
java -cp build/app LockDemo
~~~

**Stdout chính xác đã kiểm chứng với JDK và mức tương thích Java 17:**

~~~text
serialSameLock=true
serialLockIsLoader=true
parallelRegistered=true
parallelSameNameSameLock=true
parallelDifferentNamesDifferentLock=true
parallelLockNotLoader=true
allThreadsSameClass=true
findClassCalls=1
loaderOwnsClass=true
~~~

### 5.5. Tại sao mỗi dòng quan trọng?

| Dòng | Bằng chứng |
|---|---|
| `serialSameLock=true` | Loader chưa đăng ký dùng **một khóa chung** cho hai binary names khác nhau |
| `serialLockIsLoader=true` | Khóa chung đó chính là **đối tượng loader** |
| `parallelRegistered=true` | Loại subclass `ParallelLoader` đã đăng ký parallel-capable thành công |
| `parallelSameNameSameLock=true` | Trong **cùng loader instance**, hỏi cùng tên hai lần nhận cùng lock object |
| `parallelDifferentNamesDifferentLock=true` | Hai tên `Alpha` và `Beta` có hai khóa khác nhau |
| `parallelLockNotLoader=true` | Khóa theo tên không phải toàn bộ instance loader |
| `allThreadsSameClass=true` | Tám tasks đều nhận cùng một định nghĩa runtime `Alpha` |
| `findClassCalls=1` | Chỉ một task đi tới bước đọc bytes/`defineClass` qua custom `findClass` |
| `loaderOwnsClass=true` | Class được định nghĩa bởi `ParallelLoader`, không phải parent/system loader |

**Ý nghĩa kỹ thuật:** cùng tên được bảo vệ để không tạo class trùng, trong khi việc lấy khóa cho tên khác nhau không buộc mọi thread tranh một monitor. Ví dụ không cố đo tốc độ, nên kết quả không phụ thuộc vào máy chạy nhiều hay ít core.

### 5.6. Các thí nghiệm mở rộng

**Thử 1 — Không đăng ký:** bỏ `REGISTERED = registerAsParallelCapable()`, rồi chạy lại trên một JVM mới. `parallel.isRegisteredAsParallelCapable()` sẽ là `false`; các dòng khóa theo tên dự kiến thay đổi: nhiều tên dùng cùng đối tượng loader. Khi không đổi thêm code, việc `parallelRegistered` in `false` là đúng.

**Thử 2 — Hai loader parallel khác nhau:** tạo `ParallelLoader second = new ParallelLoader(root)`, so `parallel.lock(NAME)` với `second.lock(NAME)`. Đây là hai instance nên khóa theo tên **không phải cùng monitor dùng chung toàn JVM**.

**Thử 3 — Tải thêm class Beta:** tạo và biên dịch `demo.plugin.Beta`, điều chỉnh `findClass` hỗ trợ cả Alpha/Beta. Cho hai tasks nạp hai tên khác nhau, chúng có thể cùng qua những khóa riêng; **không lấy thứ tự in log hoặc thời gian chạy để chứng minh chắc chắn parallelism**.

**Thử 4 — Sai cách override:** tự override `loadClass` mà quên `findLoadedClass` hoặc quên khóa, sau đó bắn nhiều requests cùng tên. Bạn có thể gặp `LinkageError` hoặc lỗi không ổn định. Đây là thử nghiệm nên đặt trong sandbox, không làm trên loader production.

## 6. Ghi đè `loadClass`: khi nào cần và phải giữ điều gì?

Thông thường, **chỉ override `findClass(String)`** để cung cấp chiến lược đọc bytes riêng. Khi đó bạn tận dụng được implementation mặc định của `loadClass`: khóa, cache theo JVM, ủy quyền parent và `resolveClass`.

Nếu thật sự cần chiến lược custom như **child-first cho namespace plugin**, có thể phải override `loadClass(String, boolean)`. Lúc ấy, bạn chịu trách nhiệm bảo đảm:

1. Đồng bộ bằng một lock theo **cùng tên class**, ví dụ `synchronized(getClassLoadingLock(name))`.
2. Gọi `findLoadedClass(name)` **bên trong** vùng khóa trước khi cố định nghĩa.
3. Áp dụng đúng delegation policy của ứng dụng (parent-first, child-first có ngoại lệ).
4. Gọi `findClass`/`defineClass` chỉ khi chưa có class phù hợp.
5. Nếu `resolve` đúng, gọi `resolveClass` đúng chỗ.
6. Tránh gọi lại `loadClass` trong những đường khiến hai tên phụ thuộc vòng tròn và khóa bị giữ theo thứ tự đối nghịch.
7. Tuân thủ runtime package/security constraints và loading constraints giữa loaders.

Giả mã minh họa ý tưởng **parent-first** (không phải một custom loader runnable hoàn chỉnh):

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);

        if (c == null) {
            try {
                c = getParent().loadClass(name);
            } catch (ClassNotFoundException ex) {
                c = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
~~~

**Cảnh báo quan trọng:** đoạn trên bỏ qua xử lý hợp đồng parent `null` (bootstrap fallback) và các yêu cầu khác của loader thực tế, nên chỉ là **pseudocode cấu trúc**, **không copy vào production**. Đúng nhất nếu không có yêu cầu đặc biệt là **không override `loadClass`**.

### 6.1. Cùng tên, khác loader có cùng khóa không?

Không. `getClassLoadingLock("pkg.A")` trên `loader1` và `loader2` là hai kết quả gắn với **hai instance** khác nhau. Vì thế, khóa theo tên **không** giải quyết tất cả bài toán giao tiếp giữa các class loaders:

~~~text
Loader A -> class pkg.ServiceA
Loader B -> class pkg.ServiceB

Nếu A giữ lock cho ServiceA rồi chờ B nạp ServiceB,
và B giữ lock cho ServiceB rồi chờ A nạp ServiceA,
có thể xảy ra circular wait/deadlock tùy delegation/call graph.
~~~

Parallel-capable registration **giảm loại deadlock do đồng bộ toàn loader**, đặc biệt trong mô hình delegation không thuần phân cấp, nhưng **không bảo đảm mọi kiểu deadlock đều biến mất**.

## 7. Khóa toàn loader và khóa theo tên: đánh đổi

| Thuộc tính | Loader không parallel-capable | Loader parallel-capable |
|---|---|---|
| `getClassLoadingLock("A")` | Trả **`this`** | Trả đối tượng gắn với tên `A` |
| `getClassLoadingLock("B")` | Cũng **`this`** | Trả đối tượng gắn với tên `B` |
| Hai thread cùng nạp **A** | Tuần tự khi đi qua `loadClass` mặc định | Tuần tự trên cùng `lock_A` |
| Hai thread nạp **A** và **B** | Tranh monitor chung của loader | Có thể xử lý đồng thời |
| Yêu cầu đăng ký | Không | `registerAsParallelCapable` từ subclass trước khi tạo instance |
| Bảo đảm không có deadlock | **Không** | **Cũng không** |
| An toàn nếu override `loadClass` tùy tiện | **Không** | **Không** |
| Khuyến nghị thông thường | Dùng mặc định, override `findClass` nếu cần | Đăng ký đúng rồi vẫn ưu tiên override `findClass` |

Một framework có thể dùng parallel-capable để hỗ trợ plugin/resource loading với nhiều threads. Tuy nhiên, locking granular không biến class loading thành một hoạt động tùy tiện: định danh kiểu theo binary name + defining loader vẫn phải được duy trì.

## 8. Lỗi và ngộ nhận thường gặp

### 8.1. “`getClassLoadingLock(name)` tự động khóa thread”

Sai. Method **trả Object** dùng làm monitor. `loadClass` mặc định dùng `synchronized(getClassLoadingLock(name))`; còn code riêng của bạn phải thực sự đồng bộ trên lock khi tự xử lý quá trình nạp.

### 8.2. “Không parallel-capable thì Java không hỗ trợ đa luồng”

Sai. Nhiều threads vẫn có thể **gọi** `loadClass` của cùng loader. Chúng sẽ đồng bộ trên một monitor chung trong implementation mặc định. Parallel-capable liên quan **độ mịn của khóa**, không phải cấm threads khác.

### 8.3. “Đăng ký parallel-capable cho một instance bằng constructor”

Sai. Registration áp dụng cho **subclass gọi method**, không phải object constructor. Gọi khi chưa có instance của subclass và khi mọi superclass được đăng ký mới hợp lệ.

### 8.4. “`ClassLoader` đã parallel-capable nên mọi subclass tự động parallel-capable”

Sai. JDK `ClassLoader` đã đăng ký, nhưng các subclass custom vẫn cần tự gọi `registerAsParallelCapable`. Đừng suy đoán từ superclass mà bỏ qua trạng thái của subclass.

### 8.5. “Parallel-capable cho phép định nghĩa cùng một tên hai lần”

Sai. Cùng tên phải dùng cùng khóa và `findLoadedClass` để tránh `defineClass` lặp, nếu không JVM có thể ném `LinkageError`. Tạo runtime class mới cho cùng tên có thể cần **ClassLoader instance khác**, với các ràng buộc identity/loading constraints của JVM.

### 8.6. “Có khóa theo tên nên override `loadClass` thế nào cũng được”

Sai. Khóa chỉ là một phần: vẫn phải kiểm tra cache, delegation, linking/resolution, package constraints và phối hợp nhiều loaders.

### 8.7. “Hai tên lớp khác nhau sẽ luôn load song song và chạy nhanh hơn”

Sai. Việc thread thực sự chạy song song phụ thuộc scheduler, CPU, I/O, parent loader, dependencies và các khóa khác. API chỉ cho phép locking mịn hơn, không đảm bảo throughput hay thứ tự.

### 8.8. “Khóa được chia sẻ giữa hai ClassLoader nếu chuỗi tên giống nhau”

Sai. `getClassLoadingLock` là instance method, lock map gắn với loader. Hai class loaders không biến thành một lock registry toàn JVM.

### 8.9. “`findLoadedClass` chỉ tìm class do loader trực tiếp define”

Không đầy đủ. Nó kiểm tra record của JVM đối với **initiating loader**; class có thể đã được parent định nghĩa rồi được child nhận qua delegation.

### 8.10. “Nếu lỗi nạp đồng thời chỉ cần catch `LinkageError`”

Sai. Catch lỗi không sửa race condition. Hãy kiểm tra `findLoadedClass` nằm trong đúng critical section, registration, đường gọi `defineClass`, delegation và cách dùng `getClassLoadingLock`.

## 9. Debug khi gặp deadlock hoặc duplicate definition

### 9.1. Dấu hiệu duplicate definition

Log có thể có:

~~~text
java.lang.LinkageError: loader ... attempted duplicate class definition for ...
~~~

Đây là **ví dụ hình dạng thông báo**, không phải stdout chuẩn. Khi điều tra, cần ghi **tên binary class**, defining/initiating loader liên quan, stack trace đầy đủ, đường `defineClass` và các thread đang load cùng tên.

Checklist:

1. Loader nào đã xử lý tên này trước?
2. Có override `loadClass` không, có giữ `getClassLoadingLock(name)` không?
3. `findLoadedClass(name)` được gọi **trước** `findClass/defineClass` và **trong** cùng lock không?
4. Subclass đã thực sự đăng ký parallel-capable chưa?
5. Hai threads có đi qua **cùng instance loader** không?
6. Parent đã nạp class này rồi hay code cố child-first define tiếp?
7. Có lỗi do **loading constraints giữa hai loaders** thay vì duplicate definition cùng loader không?

### 9.2. Deadlock khi nhiều threads load các tên khác nhau

Đặc biệt với loaders có delegation không theo cây cha-con đơn giản, khi giữ khóa loader chung, một thread có thể chờ loader khác đang bị chiếm; thread kia lại chờ loader đầu, tạo chu trình. Java API note khuyến nghị loader có **non-hierarchical delegation** đăng ký parallel-capable để giảm nguy cơ deadlock do khóa loader giữ suốt thời gian nạp.

Để chẩn đoán:

- Thu **thread dump** bằng công cụ phù hợp, ví dụ `jcmd <pid> Thread.print` hoặc `jstack <pid>` ở môi trường hỗ trợ.
- Tìm các threads đang ở trạng thái `BLOCKED` và monitors liên quan loader.
- Xem call stack `ClassLoader.loadClass`, `findClass` và custom delegation.
- Kiểm tra deadlock do **đảo thứ tự khóa giữa các loader hoặc các class name**.
- Đừng chỉ bật parallel-capable mà không sửa dependency graph tạo vòng lặp; registration không loại hết mọi deadlock.

Lệnh có `<pid>` là **mẫu cú pháp**, thay bằng PID của tiến trình thật khi sử dụng; các công cụ và output khác nhau theo JDK.

### 9.3. Khi performance kém vì contention

Đừng lập tức override `loadClass` để dùng lock theo tên thủ công. Trước tiên:

1. Profile/sampling xem contention có thật sự nằm tại loader monitor hay không.
2. Kiểm tra loader có registered parallel-capable theo `isRegisteredAsParallelCapable()` không.
3. Loại bỏ I/O và thao tác tốn thời gian khỏi đường hot path khi phù hợp.
4. Kiểm tra parent delegation và thư viện đang dùng có giữ khóa khác không.
5. Dùng `findClass` chuẩn và registration đúng trước khi cân nhắc chiến lược phức tạp.

## 10. Tự kiểm tra

1. `getClassLoadingLock(String)` trả gì với loader **chưa đăng ký parallel-capable**?
2. Với loader parallel-capable, hai lần gọi cùng binary name có trả cùng lock object không? Hai binary names khác nhau thì sao?
3. Vì sao `getClassLoadingLock("X")` và `getClassLoadingLock("Y")` của loader không parallel-capable đều là `this`?
4. Khóa theo tên class là khóa global trên JVM hay gắn với ClassLoader instance?
5. `getClassLoadingLock` tự đồng bộ ngay khi được gọi hay chỉ trả object?
6. Trong `loadClass` mặc định, `findLoadedClass`, delegation và `findClass` nằm trong vùng khóa nào?
7. Vì sao `findLoadedClass` phải được kiểm tra khi thread đã giữ lock?
8. Tại sao đăng ký parallel-capable nên nằm ở static initializer, không phải sau khi tạo instance?
9. Điều kiện gì xảy ra nếu một superclass custom ở giữa chưa parallel-capable?
10. `isRegisteredAsParallelCapable()` dùng để xác minh điều gì?
11. Nếu tám threads cùng yêu cầu `Alpha`, tại sao demo chỉ gọi custom `findClass` một lần?
12. Vì sao hai tên class khác nhau **có thể** được nạp đồng thời mà không đảm bảo có speedup?
13. Vì sao chỉ `synchronized(getClassLoadingLock(name))` mà quên `findLoadedClass` vẫn có thể định nghĩa trùng?
14. Khi nào nên override `findClass` thay vì `loadClass`?
15. Điều gì khiến custom delegation giữa loaders có thể gây deadlock dù đã dùng khóa theo tên?
16. `registerAsParallelCapable` có cho phép class cùng tên được định nghĩa hai lần trong cùng loader không?
17. Nếu `Thread A` giữ lock theo tên `Alpha` và `Thread B` giữ lock theo tên `Beta`, có tình huống dependency nào vẫn làm hai thread phải chờ nhau?
18. Trong một stack trace `LinkageError`, bạn cần phân biệt duplicate definition với loại loading-constraint violation như thế nào?

**Tiêu chí hoàn thành:** chạy chương trình Java 17+, giải thích chính xác chín dòng stdout, phân biệt loader lock và per-name lock, dùng đúng `registerAsParallelCapable`/`getClassLoadingLock`, giữ `findLoadedClass` trong critical section khi customize loader và chẩn đoán được contention/race/deadlock.

## 11. Tài liệu chính thức

- [Java SE 21 — ClassLoader#getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): hợp đồng non-parallel trả `this`, parallel trả lock theo class name.
- [Java SE 21 — ClassLoader#registerAsParallelCapable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#registerAsParallelCapable()): điều kiện đăng ký cho subclass, trạng thái không thể đảo ngược.
- [Java SE 21 — ClassLoader#isRegisteredAsParallelCapable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#isRegisteredAsParallelCapable()): kiểm tra trạng thái runtime.
- [Java SE 21 — ClassLoader#loadClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): thuật toán chuẩn, parent delegation, `findLoadedClass` và `findClass`.
- [JVMS Java SE 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): nền tảng class loading, linking, identity và ràng buộc của JVM.

Bài sử dụng API có từ Java 7+; ví dụ Java 17 chạy độc lập không cần Maven/Gradle hoặc thư viện ngoài. Quan sát bằng **object identity** của khóa và class, không dựa trên thời gian thực thi hay chuỗi `toString()` phụ thuộc JDK.