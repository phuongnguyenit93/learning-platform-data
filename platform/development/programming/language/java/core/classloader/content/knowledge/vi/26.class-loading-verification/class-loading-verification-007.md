# Kiểm chứng nạp đồng thời và xử lý tên lớp trùng trong Java ClassLoader

## 1. Mục tiêu: chứng minh hành vi, không chỉ nhìn sơ đồ

Trong hệ Java plugin, application server, test runner hoặc custom `ClassLoader`, nhiều thread có thể yêu cầu nạp class cùng lúc. Một số yêu cầu sử dụng **cùng binary name**; các yêu cầu khác sử dụng **hai binary names khác nhau**. Đồng thời, hai JAR hoặc hai plugin có thể chứa **class cùng fully qualified name**. Những tình huống này liên quan nhau nhưng **không phải cùng một vấn đề**.

Bài thực hành này tập trung vào ba câu hỏi có thể kiểm chứng bằng Java 17+:

1. **Hai thread đồng thời gọi `loadClass("demo.Alpha")` trên cùng loader sẽ nhận gì?** Với triển khai đúng, chúng nhận **cùng `Class<?>`**; loader không được định nghĩa trùng tên trong cùng defining loader.
2. **Hai thread nạp `demo.Alpha` và `demo.Beta` trên cùng loader có thể tiến vào `findClass` cùng lúc không?** Có, nếu loader được đăng ký **parallel-capable**, không bị khóa toàn cục khác chặn và dependencies cho phép.
3. **Hai loader độc lập cùng định nghĩa `demo.Alpha` thì sao?** JVM có thể có **hai runtime classes khác nhau nhưng cùng binary name**, mỗi class gắn với defining loader riêng. Không được mặc định cast object của loader này thành class do loader kia định nghĩa.

Sau khi đọc bài, bạn sẽ tự xây:
- Một chương trình quan sát **khóa theo tên** qua `getClassLoadingLock`.
- Một chương trình Java 17+ có **hai thread, CountDownLatch, ClassLoader.findClass và bytecode thực**, kiểm chứng cả nạp khác tên lẫn cùng tên.
- Một thử nghiệm gọi `defineClass` trùng tên để quan sát **`LinkageError`** và so sánh việc định nghĩa cùng tên ở hai loaders.

**Điểm cần giữ:** “concurrent class loading” không đồng nghĩa “hai thread được phép tạo hai class cùng tên trong cùng loader”; ngược lại, **đồng bộ đủ hẹp theo tên** vừa bảo vệ nạp cùng tên, vừa cho phép nạp các tên khác nhau khi phù hợp.

## 2. Các thuật ngữ phải phân biệt

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Binary name** | Tên dùng khi `ClassLoader.loadClass` tìm kiểu tham chiếu thông thường, ví dụ `demo.Alpha`; nested class thường có `$` trong binary name |
| **Initiating loader** | Loader đứng ở phía khởi xướng yêu cầu load và có thể delegate cho loader khác |
| **Defining loader** | Loader thực sự gọi `defineClass` hoặc tương đương để định nghĩa runtime class |
| **Runtime class identity** | Đối với lớp thông thường, xác định bởi **binary name + defining ClassLoader** |
| **`findLoadedClass(name)`** | Kiểm tra loader/JVM đã biết runtime class cho binary name này chưa |
| **`findClass(name)`** | Hook dành cho custom loader tìm bytecode và gọi `defineClass` khi cần |
| **`defineClass(...)`** | Yêu cầu JVM biến class file bytes hợp lệ thành runtime class |
| **Parallel-capable loader** | ClassLoader subclass đã đăng ký để sử dụng khóa theo tên class trong thuật toán load mặc định |
| **`getClassLoadingLock(name)`** | Đối tượng lock dùng khi loading tên đó |
| **Class initialization** | Chạy static initializers theo quy tắc JVM; không phải cùng cơ chế với per-name class-loading lock |

### “Tên trùng” có ít nhất ba nghĩa

**A. Hai requests cùng tên, cùng một loader:**

```text
T1 → Loader-X.loadClass("demo.Alpha")
T2 → Loader-X.loadClass("demo.Alpha")
            └── kỳ vọng: cùng một Class<?> kết quả
```

**B. Hai class files cùng tên xuất hiện trong nhiều classpath/JAR entries:**

```text
lib-old.jar: demo/Alpha.class
lib-new.jar: demo/Alpha.class
            └── loader/delegation/search order quyết định class nào
```

**C. Hai defining loaders độc lập cố ý dùng cùng tên:**

```text
Loader-X.defineClass("demo.Alpha", ...)
Loader-Y.defineClass("demo.Alpha", ...)
            └── có thể tạo hai Class<?> khác nhau
```

Ba trường hợp có cách chẩn đoán khác nhau. Không gom tất cả thành “duplicate class error”.

## 3. Vì sao cần khóa cho `loadClass`?

Một loader tự định nghĩa class có thể làm những bước như:

```text
loadClass(name)
    │
    ▼
findLoadedClass(name)
    │ class đã có? ── Có ──► trả Class<?> cũ
    │ Không
    ▼
ủy quyền cho parent
    │ parent tìm được? ── Có ──► trả Class<?> của parent
    │ Không
    ▼
findClass(name)
    └── đọc class file bytes
        └── defineClass(name, bytes, ...)
                └── Class<?> mới
```

Nếu hai threads đồng thời làm **“check rồi define”** mà không có đồng bộ:
- Cả hai có thể thấy `findLoadedClass(name) == null`.
- Cả hai cùng đọc bytes.
- Cả hai gọi `defineClass` cho cùng **binary name và defining loader**.
- JVM phải từ chối lần định nghĩa trùng, thường bằng **`LinkageError`**.

Vì vậy, điều kiện **kiểm tra trạng thái chưa loaded rồi định nghĩa class** phải được điều phối như một vùng tới hạn phù hợp theo tên.

### Thuật toán load mặc định đã làm việc này

`ClassLoader.loadClass(String name, boolean resolve)` có triển khai đồng bộ dạng tương đương:

```java
// PSEUDOCODE: mô tả cấu trúc, không phải copy mã JDK nội bộ.
synchronized (getClassLoadingLock(name)) {
    Class<?> result = findLoadedClass(name);

    if (result == null) {
        try {
            result = parentOrBootstrapLoad(name);
        } catch (ClassNotFoundException notFound) {
            result = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(result);
    }
    return result;
}
```

Đoạn trên chỉ minh họa trình tự và lock; `parentOrBootstrapLoad` không phải API Java thực. Cách an toàn nhất khi xây loader đơn giản là **override `findClass`**, giữ lại `loadClass` chuẩn để tận dụng:
- `findLoadedClass` trước `defineClass`;
- parent delegation;
- khóa per-name hoặc whole-loader thích hợp;
- xử lý `resolve` mặc định.

**Không nên tự override `loadClass` chỉ để đọc bytes từ directory/JAR mới**. Chỉ cần override `findClass` khi parent-first phù hợp.

## 4. Khóa whole-loader và per-name khác nhau thế nào?

Theo contract `ClassLoader.getClassLoadingLock(String)`:

- Nếu class loader **không đăng ký parallel-capable**, mặc định trả về **`this`**, tức monitor của cả loader.
- Nếu class loader **đã đăng ký parallel-capable**, trả về lock gắn với **binary name** được yêu cầu.
- Với **cùng loader và cùng tên**, các lần gọi trả lock thích hợp cho tên ấy.
- Với hai tên khác nhau, parallel-capable loader có thể dùng **hai lock khác nhau**, nhờ vậy hai `findClass` calls có khả năng chồng thời gian.

### Minh họa

```text
Loader bình thường:
    T1 loadClass("demo.Alpha") ──lock Loader-X──▶ tìm/define A
    T2 loadClass("demo.Beta")  ──chờ Loader-X─────────────▶ tìm B

Parallel-capable loader:
    T1 loadClass("demo.Alpha") ──lock K_Alpha──▶ tìm/define A
    T2 loadClass("demo.Beta")  ──lock K_Beta ──▶ tìm/define B

Cùng tên trên parallel-capable loader:
    T1 loadClass("demo.Alpha") ──lock K_Alpha──▶ define A
    T2 loadClass("demo.Alpha") ──chờ K_Alpha───▶ dùng A đã loaded
```

Đây là sơ đồ **cơ chế khóa**, không cam kết lịch scheduler sẽ cho hai thread chạy đồng thời trên mọi máy. Nếu có dependency, shared I/O lock hoặc synchronized toàn loader ở code khác thì việc nạp vẫn có thể bị tuần tự hóa.

## 5. Đăng ký parallel-capable đúng cách

Một subclass muốn dùng per-name locks theo triển khai mặc định cần đăng ký trong static initializer:

```java
public final class MyLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "ClassLoader parallel registration failed");
        }
    }

    public MyLoader(ClassLoader parent) {
        super(parent);
    }
}
```

Đây là một class Java hợp lệ, có thể lưu trong `MyLoader.java`. Nó kế thừa thuật toán `loadClass` chuẩn, chưa thêm logic tìm bytes riêng.

**Các yêu cầu quan trọng:**
- `registerAsParallelCapable()` là `protected static`; gọi trong initialization của **chính loader subclass** là cách phổ biến.
- Đăng ký phải thực hiện **trước khi tạo instance đầu tiên** của loader class đó.
- Mọi superclass thuộc chuỗi loader class (trừ `Object`) phải đăng ký theo API. Chính `ClassLoader` đã đăng ký, nhưng **subclass không tự động được tính là đã đăng ký**.
- Không bỏ qua giá trị `boolean` trả về; trả `false` nghĩa là **không đăng ký thành công**.
- Nếu định nghĩa `BaseLoader extends ClassLoader` nhưng **BaseLoader không đăng ký**, `ChildLoader extends BaseLoader` không thể đăng ký thành công theo contract.
- `isRegisteredAsParallelCapable()` trên loader instance xác nhận trạng thái (Java 9+).

**Quan trọng:** việc đăng ký là **khai báo khả năng hỗ trợ nạp đồng thời**, không làm các cache, maps, JAR readers hay code `findClass` tự thread-safe.

## 6. Ví dụ 1 — In ra sự khác biệt của khóa

### 6.1. Tạo `LockGranularityDemo.java`

```java
public final class LockGranularityDemo {
    static class Serial extends ClassLoader {
        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class Parallel extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "registration failed");
            }
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    public static void main(String[] args) {
        Serial serial = new Serial();
        Parallel parallel = new Parallel();

        System.out.println("serial registered: "
                + serial.isRegisteredAsParallelCapable());
        System.out.println("serial A/B same lock: "
                + (serial.lock("demo.Alpha")
                   == serial.lock("demo.Beta")));
        System.out.println("serial lock is loader: "
                + (serial.lock("demo.Alpha") == serial));

        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());
        System.out.println("parallel A/B same lock: "
                + (parallel.lock("demo.Alpha")
                   == parallel.lock("demo.Beta")));
        System.out.println("parallel same name same lock: "
                + (parallel.lock("demo.Alpha")
                   == parallel.lock(new String("demo.Alpha"))));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac --release 17 LockGranularityDemo.java
java LockGranularityDemo
```

Stdout đã được kiểm chứng:

```text
serial registered: false
serial A/B same lock: true
serial lock is loader: true
parallel registered: true
parallel A/B same lock: false
parallel same name same lock: true
```

### 6.2. Giải thích

- `Serial` chưa gọi `registerAsParallelCapable`, nên lock cho Alpha và Beta cùng là đối tượng `serial`.
- `Parallel` đăng ký thành công, nên lock cho Alpha và Beta là hai objects khác nhau.
- `new String("demo.Alpha")` tạo **String object khác**, nhưng nội dung tên vẫn là `demo.Alpha`. Cùng binary name sẽ dùng lại lock tương ứng trong cùng loader.
- `==` ở đây được dùng để so **đối tượng khóa**, không phải so tên bằng reference identity.

Đây là thử nghiệm **khóa**, chưa chứng minh `findClass` thật sự chạy đồng thời. Ví dụ tiếp theo sẽ dùng bytecode hợp lệ, hai threads và latches để kiểm chứng đường tải thực tế.

## 7. Thiết kế bài kiểm chứng concurrency đúng

Để quan sát một race, nhiều ví dụ sai chỉ tạo hai threads rồi `Thread.sleep(100)` và đọc thứ tự log. Cách này không đáng tin vì:
- Scheduler có thể chạy một task xong rồi mới chạy task kia.
- Máy CI có thể chậm hơn, timeout bất thường.
- Thread sleep không bảo đảm các thao tác đã vào cùng đoạn code.
- Thứ tự của `System.out.println` không tương đương với thứ tự vào `findClass`.
- Hai classes có thể đã được parent nạp trước, khiến custom `findClass` không được gọi.

Trong bài này ta dùng:
- `CountDownLatch(2)` để chứng minh **hai binary names khác nhau đã cùng đi vào `findClass` trước khi bất kỳ thao tác nào được nhả ra**.
- `CountDownLatch(1)` để giữ tác vụ bên trong `findClass` cho tới khi thread chính cho phép tiếp tục.
- Hai `Future<Class<?>>` từ `ExecutorService.newFixedThreadPool(2)`.
- `AtomicInteger` để đếm số lần mỗi class đi qua `findClass` một cách thread-safe.
- Một loader mới cho kịch bản **cùng tên**, tránh cache từ kịch bản khác.
- Một lớp `RawLoader` độc lập cho việc **cố ý định nghĩa trùng** (không dùng `loadClass`) để quan sát JVM từ chối.

Timeout trong latch là **biện pháp chống test treo vô hạn**, không phải yếu tố xác định stdout. Khi máy bị nghẽn bất thường, test có thể fail vì timeout; thay vì in thứ tự ngẫu nhiên, nó báo sự cố kiểm chứng rõ ràng.

## 8. Ví dụ 2 — Nạp hai class khác tên và cùng tên bằng thread thật

### 8.1. Cấu trúc source và output

Tạo project:

```text
loader-race/
├── src/
│   └── demo/
│       ├── Alpha.java
│       └── Beta.java
├── LoadRaceDemo.java
├── plugin-classes/
└── host-classes/
```

**Không đặt `plugin-classes` lên host application classpath.** Nếu host parent loader đã tìm thấy Alpha hoặc Beta thì custom `findClass` không được gọi; bài kiểm chứng mất giá trị.

### 8.2. File `src/demo/Alpha.java`

```java
package demo;

public final class Alpha {
    public static String id() {
        return "Alpha";
    }
}
```

### 8.3. File `src/demo/Beta.java`

```java
package demo;

public final class Beta {
    public static String id() {
        return "Beta";
    }
}
```

Hai classes độc lập; không tham chiếu trực tiếp nhau, vì mục tiêu là kiểm tra per-name concurrency mà không vô tình tạo dependency giữa Alpha và Beta.

### 8.4. File `LoadRaceDemo.java` — chương trình đầy đủ

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class LoadRaceDemo {
    static class ParallelDirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "parallel registration failed");
            }
        }

        private final Path root;
        final AtomicInteger alphaFinds = new AtomicInteger();
        final AtomicInteger betaFinds = new AtomicInteger();
        volatile CountDownLatch entered;
        volatile CountDownLatch release;

        ParallelDirectoryLoader(Path root) {
            super(LoadRaceDemo.class.getClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("demo.Alpha")
                    && !name.equals("demo.Beta")) {
                throw new ClassNotFoundException(name);
            }

            if (name.equals("demo.Alpha")) {
                alphaFinds.incrementAndGet();
            } else {
                betaFinds.incrementAndGet();
            }

            CountDownLatch started = entered;
            CountDownLatch gate = release;
            if (started != null && gate != null) {
                started.countDown();
                try {
                    if (!gate.await(10, TimeUnit.SECONDS)) {
                        throw new ClassNotFoundException(
                                "gate timed out for " + name);
                    }
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new ClassNotFoundException(
                            "interrupted: " + name, error);
                }
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(
                                name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    static class RawLoader extends ClassLoader {
        RawLoader() {
            super(null);
        }

        Class<?> define(String name, byte[] data) {
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("plugin-classes");

        // KỊCH BẢN 1: hai binary names khác nhau.
        ParallelDirectoryLoader different =
                new ParallelDirectoryLoader(root);
        different.entered = new CountDownLatch(2);
        different.release = new CountDownLatch(1);

        ExecutorService two = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> alpha = two.submit(
                    () -> different.loadClass("demo.Alpha"));
            Future<Class<?>> beta = two.submit(
                    () -> different.loadClass("demo.Beta"));

            boolean bothEntered =
                    different.entered.await(10, TimeUnit.SECONDS);

            different.release.countDown();
            Class<?> a = alpha.get();
            Class<?> b = beta.get();

            System.out.println("parallel capable: "
                    + different.isRegisteredAsParallelCapable());
            System.out.println("two names entered findClass: "
                    + bothEntered);
            System.out.println("different classes: " + (a != b));
            System.out.println("same defining loader: "
                    + (a.getClassLoader() == b.getClassLoader()));
            System.out.println("find counts: "
                    + different.alphaFinds.get() + ","
                    + different.betaFinds.get());
        } finally {
            different.release.countDown();
            two.shutdownNow();
        }

        // KỊCH BẢN 2: hai requests cùng binary name.
        ParallelDirectoryLoader same =
                new ParallelDirectoryLoader(root);
        same.entered = new CountDownLatch(1);
        same.release = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> first = pool.submit(
                    () -> same.loadClass("demo.Alpha"));

            if (!same.entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "first load did not enter findClass");
            }

            CountDownLatch secondStarted = new CountDownLatch(1);
            Future<Class<?>> second = pool.submit(() -> {
                secondStarted.countDown();
                return same.loadClass(new String("demo.Alpha"));
            });

            if (!secondStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "second task did not start");
            }

            same.release.countDown();
            Class<?> c1 = first.get();
            Class<?> c2 = second.get();

            System.out.println("same name same Class: "
                    + (c1 == c2));
            System.out.println("same name findClass calls: "
                    + same.alphaFinds.get());
        } finally {
            same.release.countDown();
            pool.shutdownNow();
        }

        // KỊCH BẢN 3: cố ý define trùng trên cùng loader.
        byte[] bytecode = Files.readAllBytes(
                root.resolve("demo/Alpha.class"));

        RawLoader raw1 = new RawLoader();
        Class<?> r1 = raw1.define("demo.Alpha", bytecode);

        try {
            raw1.define("demo.Alpha", bytecode);
            System.out.println("duplicate unexpectedly allowed");
        } catch (LinkageError expected) {
            System.out.println("duplicate define rejected: "
                    + expected.getClass().getSimpleName());
        }

        // KỊCH BẢN 4: cùng binary name, hai defining loaders.
        RawLoader raw2 = new RawLoader();
        Class<?> r2 = raw2.define("demo.Alpha", bytecode);

        System.out.println("two loaders same binary name: "
                + r1.getName().equals(r2.getName()));
        System.out.println("two loaders same Class: " + (r1 == r2));
    }
}
```

**Ghi chú về thiết kế fixture:**
- `ParallelDirectoryLoader` chỉ cho phép đúng hai tên trong fixture, tránh custom loader cố vô tình nạp classes của JDK/host từ directory.
- `entered` và `release` là **latches dành cho test**, không phải cơ chế cần có trong production loader.
- `volatile` bảo đảm worker threads quan sát các tham chiếu latches mà main thread cấu hình trước khi submit tasks.
- `AtomicInteger` bảo đảm phép đếm `findClass` không bị data race khi các tên khác nhau được nạp đồng thời.
- `RawLoader` có parent `null` (bootstrap delegation); nó cố ý phơi một method `define` để kiểm chứng lỗi duplicate. **Không sử dụng RawLoader như loader tổng quát cho ứng dụng thật.**

### 8.5. Biên dịch và chạy Java 17+

Trong thư mục `loader-race`, tạo hai output directories:

Bash:

```bash
mkdir -p plugin-classes host-classes
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes,host-classes | Out-Null
```

Biên dịch và chạy:

```bash
javac --release 17 -d plugin-classes src/demo/Alpha.java src/demo/Beta.java
javac --release 17 -d host-classes LoadRaceDemo.java
java -cp host-classes LoadRaceDemo
```

`--release 17` tạo bytecode target Java 17 và giới hạn API Java theo release đó. Vì source dùng switch-free syntax cơ bản, `ExecutorService` và `Path` đều có thể chạy trên Java 17+.

**Điều kiện cực kỳ quan trọng:** chỉ `host-classes` có trong `-cp`, **không phải `plugin-classes`**. Nếu thêm `plugin-classes` vào classpath của host:
- application parent loader có thể nạp Alpha/Beta trực tiếp;
- `ParallelDirectoryLoader.findClass` không được gọi;
- `entered.await(...)` timeout vì fixture không vào đoạn code cần đo;
- đó là lỗi **thiết lập test**, không phải chứng cứ loader không hỗ trợ concurrency.

### 8.6. Stdout đã chạy kiểm chứng

```text
parallel capable: true
two names entered findClass: true
different classes: true
same defining loader: true
find counts: 1,1
same name same Class: true
same name findClass calls: 1
duplicate define rejected: LinkageError
two loaders same binary name: true
two loaders same Class: false
```

Kết quả đã được biên dịch với `javac --release 17` và chạy trên OpenJDK 21. Khi chạy trên JDK 17+, trên máy có đủ tài nguyên và không vượt timeout kiểm thử, các dòng logic có kết quả như trên. Không đo hoặc dự đoán tốc độ thực tế từ các dòng stdout này.

## 9. Đọc kết quả kịch bản 1 — hai tên khác nhau thật sự vào findClass đồng thời

Đầu tiên:

```java
different.entered = new CountDownLatch(2);
different.release = new CountDownLatch(1);
```

Mỗi lần `findClass` bắt đầu cho một tên hợp lệ:
- tăng counter;
- gọi `entered.countDown()`;
- chờ `release.await(...)` trước khi đọc bytes và gọi `defineClass`.

Nếu loader **khóa toàn bộ instance**, thread đầu tiên giữ monitor và đứng ở `findClass` chờ `release`. Thread thứ hai bị chặn **trước khi có thể đi vào `findClass`**, nên latch đếm hai arrivals sẽ không về 0 trước khi release.

Với **parallel-capable loader** có per-name locks, thread A giữ khóa Alpha và thread B giữ khóa Beta — khác nhau. Cả hai đều tiến đến `entered.countDown()` trước khi main thread nhả `release`. Vì thế:

```text
two names entered findClass: true
```

Đây là bằng chứng mạnh hơn việc chỉ nhìn thứ tự log: **hai thread đã đồng thời có mặt trong đoạn findClass** (một hoặc cả hai đang chờ release, trước khi main thread cho phép bất kỳ cái nào hoàn tất).

Các dòng còn lại:
- `different classes: true` vì Alpha và Beta khác binary name/runtime type.
- `same defining loader: true` vì cả hai do **cùng instance `different`** định nghĩa.
- `find counts: 1,1` vì mỗi binary name cần một lần `findClass` trong kịch bản mới.

### Có phải luôn hai tên khác nhau sẽ vào đồng thời?

Không. Trong production có thể có:
- Code `findClass` dùng `synchronized(this)` hoặc global monitor khác.
- Một thread đang giữ khóa của shared cache/JAR resource.
- Class A cần load B và tạo dependency-driven blocking.
- Parent loader có thể tìm lớp trước custom `findClass`.
- Scheduler không cho hai tasks chạy ngay trong cùng một thời điểm.
- Application đã load classes từ trước nên `findLoadedClass` trả kết quả trực tiếp.
- Container hoặc custom `loadClass` có chính sách khóa riêng.

Do đó nói đúng là **parallel-capable mở khả năng load các tên khác nhau song song**, không phải cam kết hai operation luôn overlap hoặc tăng tốc.

## 10. Đọc kết quả kịch bản 2 — cùng tên chỉ define một lần

Dùng một `ParallelDirectoryLoader same` **mới** để Alpha chưa có trong bộ nhớ của loader đó.

Thread thứ nhất gọi:

```java
same.loadClass("demo.Alpha")
```

Nó đi vào `findClass` rồi chờ `release`. Thread thứ hai bắt đầu:

```java
same.loadClass(new String("demo.Alpha"))
```

Chuỗi mới có identity khác, nhưng binary name giống nhau. Thuật toán `getClassLoadingLock` dựa trên **giá trị tên class**, không đòi hai `String` phải là cùng object.

Theo thuật toán mặc định:
1. Thread 1 lấy per-name lock cho Alpha.
2. `findLoadedClass` trả `null`; parent không có Alpha.
3. Thread 1 vào `findClass` và chờ latch.
4. Thread 2 cũng muốn lock **Alpha**, nên không thể cùng chạy đoạn “check then define”.
5. Sau release, thread 1 `defineClass` và trả `Class<?>`.
6. Thread 2 lấy lock, `findLoadedClass("demo.Alpha")` thấy runtime class đã loaded, trả lại class đó.
7. Không gọi `findClass` lần hai.

Vì thế stdout:

```text
same name same Class: true
same name findClass calls: 1
```

**Tại sao dùng reference equality `c1 == c2`?** Vì đây là hai references tới `Class<?>`. So `c1.getName().equals(c2.getName())` chỉ xác nhận **tên giống**, không chứng minh hai threads nhận **cùng runtime class object**.

**Giới hạn cách kiểm tra:** `secondStarted.countDown()` chạy trước `loadClass` của thread 2, nên chứng minh task thứ hai đã bắt đầu chứ không bắt buộc chứng minh nó đã đứng chờ đúng tại monitor tại thời điểm release. Tuy vậy, việc cả hai `Future` trả cùng `Class<?>` và `alphaFinds=1` xác minh tính đúng của kết quả. Có thể thêm ThreadMXBean/thread dump nếu cần quan sát chính xác trạng thái blocked, nhưng bài kiểm chứng không cần phụ thuộc vào thread scheduling details.

## 11. Đọc kết quả kịch bản 3 — cố tình defineClass trùng một loader

Khác với `loadClass` chuẩn, test cố ý gọi trực tiếp method exposed:

```java
Class<?> r1 = raw1.define("demo.Alpha", bytecode);
raw1.define("demo.Alpha", bytecode); // lần hai → LinkageError
```

`RawLoader.define` gọi `defineClass` mà **không** đi qua `findLoadedClass` hoặc per-name load lock. JVM không cho một defining loader định nghĩa hai runtime classes riêng biệt có **cùng binary name**.

Do đó lần hai bị từ chối. Trong JVM đã thử, error class đơn giản là `LinkageError`:

```text
duplicate define rejected: LinkageError
```

**Không nên phụ thuộc vào exact message** như “attempted duplicate class definition”, vì text stack trace có thể khác giữa JVM versions. Bản chất là **duplicate definition của cùng loader và binary name**.

Đừng “khắc phục” bằng cách nuốt `LinkageError` và tự trả một class tùy ý. Nếu custom loader gặp duplicate trong lúc concurrent load, điều cần sửa là:
- check `findLoadedClass` đúng thứ tự;
- lock đúng tên trong `loadClass`;
- không gọi `defineClass` trùng;
- không có race trong cache mapping tên → definition;
- không override `loadClass` làm mất synchronization mặc định.

### Khi nào cần tự gọi defineClass?

`findClass` custom loader cần `defineClass` để định nghĩa bytes từ nguồn tùy chỉnh. Nhưng thông thường **không nên cung cấp public `define(name, bytes)`** mà mọi caller đều có thể gọi không qua load policy. RawLoader ở đây cố ý phá luồng chuẩn **để biểu diễn JVM từ chối**.

## 12. Đọc kết quả kịch bản 4 — cùng tên ở hai defining loaders là hợp lệ

```java
RawLoader raw2 = new RawLoader();
Class<?> r2 = raw2.define("demo.Alpha", bytecode);
```

`raw1` và `raw2` là hai loader instances riêng. Mỗi cái định nghĩa một runtime class của `demo.Alpha` từ cùng bytes. Kết quả:

```text
two loaders same binary name: true
two loaders same Class: false
```

Điều này không mâu thuẫn với quy tắc từ chối duplicate definition:

- **Một defining loader + một binary name**: không được định nghĩa hai class versions riêng.
- **Hai defining loaders khác nhau + cùng binary name**: có thể có hai runtime classes khác nhau.
- Mỗi runtime class có thể có **static fields riêng** và initialization riêng.
- Một object do `raw1` định nghĩa không tự cast thành class `demo.Alpha` do `raw2` định nghĩa.
- Nếu hai plugins cần giao tiếp, đặt **shared interface/API** ở loader cha chung thay vì tự định nghĩa lại interface ở từng child loader.

Cần lưu ý rằng hai loader con có thể delegate và nhận cùng class do parent định nghĩa. **Hai loader objects khác nhau không tự chứng minh hai class objects khác nhau** nếu bạn chỉ gọi `loadClass` parent-first. Demo dùng `defineClass` riêng để kiểm chứng rõ defining-loader identity.

## 13. “Trùng tên class trên classpath” là bài toán khác “trùng defineClass”

Giả sử:

```text
lib-a.jar ── demo/util/Codec.class [version A]
lib-b.jar ── demo/util/Codec.class [version B]
```

Nếu cả hai nằm trong **application classpath của cùng loader**:
- Loader thường tìm class theo quy tắc tìm nguồn/đường dẫn tương ứng.
- Một binary name được định nghĩa **một lần** trong loader đó; không phải cả hai files tự biến thành hai runtime classes trong cùng loader.
- Sau khi class đã được load, việc đổi thứ tự classpath hoặc ghi đè JAR trên đĩa không tự thay runtime class đã tồn tại.
- Kết quả có thể phụ thuộc launch configuration, manifest, parent loader và custom search order.

Nếu hai JAR chứa API không tương thích:
- Compiler dùng version A.
- Runtime load version B.
- Khi code resolve một method/field chỉ có ở A, có thể nhận `NoSuchMethodError`/`NoSuchFieldError`.
- Đây là **binary compatibility/duplicate source conflict**, không phải **`defineClass` duplicate trong cùng loader**.

Để kiểm tra:
- In `Class.getClassLoader()` và `CodeSource` của **class đã thực sự được JVM định nghĩa**.
- Dùng `-Xlog:class+load=info` khi phù hợp.
- Xem runtime classpath/module path thật, không chỉ Maven/Gradle dependency tree.
- Dùng `ClassLoader.getResources("demo/util/Codec.class")` như manh mối các nguồn trùng; kết quả **không tự chứng minh nguồn nào được define**.
- Kiểm tra parent delegation và classloader graph của application server/plugin host.

**Maven/Gradle có thể chọn một version cho dependency graph**, nhưng container hoặc launcher còn có thể cung cấp một JAR khác ở runtime. Vì vậy đừng cho rằng dependency resolution thành công là bảo đảm không có binary name collision ở hệ thống chạy thật.

## 14. Khi nào “duplicate binary name” gây ClassCastException?

Giả sử service API bị đóng gói hai lần:

```text
HostLoader
  └── api.Service [Class A]

PluginLoader
  ├── api.Service [Class B, cùng binary name]
  └── impl.Plugin [implements Class B]
```

Host nhận plugin object và muốn cast thành `api.Service` của host (Class A). JVM kiểm tra runtime type identity, không chỉ `getName()`. Nếu B và A khác defining loaders, cast không hợp lệ.

**Giải pháp thường dùng:**

```text
Shared ParentLoader
   └── api.Service [một runtime Class<?> duy nhất]
          /                          \
    PluginLoader-1             PluginLoader-2
      impl.One                   impl.Two
        implements api.Service qua parent
```

- Đặt hợp đồng chung ở loader cha hoặc module chia sẻ.
- Không đóng gói trùng service API trong plugin nếu plugin loader định nghĩa lại nó.
- Nếu cần child-first cho implementation, whitelist `api.*` và platform API dùng parent-first.
- Kiểm tra `serviceType == pluginInstance.getClass().getInterfaces()[i]` chỉ khi biết đúng interface position; tốt hơn dùng `serviceType.isInstance(instance)` để xác định assignability.
- Với JPMS, xem thêm `Class.getModule()`, readability và exports/opens.

**Lỗi cast và duplicate definition có thể cùng được gọi nôm na là “trùng class”, nhưng root cause hoàn toàn khác nhau**.

## 15. Khi override loadClass: giữ nguyên vùng tới hạn

Một custom loader muốn child-first có thể override `loadClass`. Khi đó, việc chỉ đăng ký `registerAsParallelCapable()` **không tự vá** implementation không thread-safe.

Mẫu định hướng:

```java
// PSEUDOCODE TRONG SUBCLASS: chưa đủ production validation.
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> loaded = findLoadedClass(name);
        if (loaded == null) {
            if (isPrivatePluginNamespace(name)) {
                try {
                    loaded = findClass(name);
                } catch (ClassNotFoundException absent) {
                    loaded = getParent().loadClass(name);
                }
            } else {
                loaded = super.loadClass(name, false);
            }
        }
        if (resolve) {
            resolveClass(loaded);
        }
        return loaded;
    }
}
```

**Không copy thành production source**: `isPrivatePluginNamespace` là placeholder, `getParent()` có thể `null`, và policy phải xử lý Java platform classes, package/module constraints, security và delegation theo kiến trúc.

Những điểm đúng cần chú ý:
- Cùng tên phải dùng cùng per-name lock.
- Phải hỏi `findLoadedClass` trước định nghĩa.
- Chỉ gọi `defineClass` một lần cho cùng binary name/loader.
- Không catch `LinkageError` của parent rồi cố định nghĩa một bản khác tùy tiện.
- Không giữ `synchronized(this)` quanh toàn bộ `loadClass` nếu muốn các tên khác nhau có thể nạp đồng thời.
- Không cho nhiều threads tự bypass `loadClass` để gọi `defineClass` trực tiếp.

Nếu có thể, **chỉ override `findClass`** và giữ thuật toán mặc định là lựa chọn ít lỗi hơn.

## 16. Dấu hiệu loader “parallel-capable nhưng nạp vẫn tuần tự”

Đăng ký thành công không bảo đảm throughput tăng. Dù `isRegisteredAsParallelCapable() == true`, có thể có:

1. Override `public synchronized Class<?> loadClass(String)` hoặc `synchronized(this)` ở code khác.
2. Một global lock bảo vệ cache, zip reader, module mapping hoặc code generation.
3. Cả hai class names được parent tìm thấy, khiến custom `findClass` không chạy.
4. Class A phụ thuộc vào B, chờ dependency dù per-name locks khác nhau.
5. JVM linkage/verification/class initialization tạo điểm chờ riêng.
6. OS/filesystem I/O hoặc CPU bị nghẽn dù logic loader không chặn.
7. Custom `getClassLoadingLock` trả một lock chung cho mọi tên.
8. Loader implementation có synchronization nhiều tầng hoặc một thư viện không thread-safe.

### Vì sao synchronized(this) làm mất lợi ích?

```java
// ANTI-PATTERN minh họa.
@Override
public synchronized Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return super.loadClass(name);
}
```

Nếu dùng trong một parallel-capable loader, monitor của cả instance vẫn bị giữ cho lời gọi `loadClass` ở method này. Hai tên khác nhau bị tuần tự hóa ở outer method dù `super.loadClass` dùng per-name locks.

Cách tốt hơn là dùng khóa hẹp cho mutable resources cụ thể hoặc concurrent collections, không đặt global monitor phủ toàn bộ quá trình tìm class/I/O/delegation.

## 17. Thread safety trong findClass: đừng quên shared state

Trong ví dụ, mỗi lời gọi `findClass`:
- dùng một `String name` cục bộ;
- tính `Path` cục bộ từ `root`;
- đọc `byte[]` riêng;
- tăng counters bằng `AtomicInteger`;
- đồng bộ theo per-name lock ở `loadClass` mặc định.

Trong loader thực tế, phải kiểm soát:
- `HashMap` cache bytes/classes mutable;
- `JarFile`/`ZipInputStream` chia sẻ;
- package definition và certificates/sealing constraints;
- plugin classpath URLs đang cập nhật;
- bytecode transformer dùng mutable buffers;
- module-specific class mapping;
- log/metrics không an toàn khi nhiều threads ghi.

### Một cache concurrent đơn giản

```java
// Trích đoạn trong custom ClassLoader:
private final java.util.concurrent.ConcurrentMap<String, byte[]>
        bytecodeCache = new java.util.concurrent.ConcurrentHashMap<>();
```

Map concurrent tránh race map, nhưng **không thay thế tính đúng của `findLoadedClass` + per-name lock**. Hai threads vẫn không được gọi `defineClass` hai lần cùng tên chỉ vì cache có cùng bytes. Các API `computeIfAbsent` cũng không tự làm mọi thao tác load/class definition không deadlock; tránh side effects đệ quy hoặc khóa chéo trong mapping function.

Nếu loader có thể được dỡ/reload, đừng giữ mãi cache chứa `Class<?>`/ClassLoader/instances ở singleton host: chúng có thể giữ classloader generation cũ reachable.

## 18. Tránh deadlock khi nhiều ClassLoaders ủy quyền chéo

Một tình huống:

```text
Thread T1:
   giữ lock Loader-A khi nạp a.One
       └── gọi Loader-B nạp b.Two

Thread T2:
   giữ lock Loader-B khi nạp b.Three
       └── gọi Loader-A nạp a.Four
```

Với whole-loader locks, có thể thành:
- T1 giữ A, chờ B.
- T2 giữ B, chờ A.
- **Deadlock**.

Per-name locks giảm một nguyên nhân: nạp những **tên khác nhau** không bắt buộc tranh toàn bộ monitor của loader A/B. Nhưng:
- Vòng chờ theo **cùng per-name locks** vẫn có thể xảy ra.
- Custom locks/delegation cycles vẫn có thể deadlock.
- Static initialization có locking riêng và có thể gây vòng chờ ngay cả với parallel-capable loaders.
- Parallel-capable không thay policy parent-first/child-first.

**Kết luận chẩn đoán:** nếu thread dump cho thấy deadlock, cần tìm **vòng chờ thực tế và khóa cụ thể**, không chỉ bật registration rồi xem là xử lý triệt để.

## 19. Phân biệt class loading đồng thời với initialization đồng thời

`ClassLoader.loadClass("demo.Alpha")` chủ yếu yêu cầu class được load (và một số linking tùy JVM/option); nó **không mặc nhiên chạy `Alpha.<clinit>`**. Ngược lại:

```java
// Trích đoạn: loader đã có trong ứng dụng.
Class<?> type = Class.forName("demo.Alpha", true, loader);
```

Overload trên yêu cầu **initialize class** nếu chưa initialized; JVM quản lý đồng bộ initialization theo quy tắc riêng.

Nếu hai threads cùng lần đầu sử dụng static field/method của một runtime class, JVM không cho cả hai cùng chạy một lần static initialization thành công như hai instances độc lập. Điều này **không có nghĩa** class loader per-name lock chính là initialization lock.

Khi test:
- Đếm `findClass` để kiểm tra class loading.
- Đếm/quan sát static initialization riêng, nếu đó là nội dung bạn cần đo.
- Đừng suy từ thứ tự `System.out.println` trong static block ra điều gì về locking của `findClass`.
- `Class.forName(name, false, loader)` có thể dùng để lấy `Class<?>` mà chưa yêu cầu initialization, nhưng có thể có linking/verification theo contract.

Với trường hợp circular static initializers, còn có thể thấy giá trị static fields chưa hoàn tất hoặc deadlock do multi-thread code; **không đánh đồng với `ClassCircularityError`** (vòng superclass/superinterface hierarchy).

## 20. Nạp mảng, primitive, nested class: tên cần chính xác

Trong Java, `ClassLoader.loadClass` nhận **binary name** cho class/interface thông thường. Dùng:

```text
demo.Alpha
demo.Outer$Nested
java.util.ArrayList
```

Đừng truyền:
- source-like `demo/Alpha.class` vào `loadClass` như binary name;
- `demo.Alpha.class` (có suffix `.class`) làm binary name;
- `demo.Outer.Nested` nếu runtime binary name thật là `demo.Outer$Nested`;
- tên kiểu nguyên thủy `int` rồi nghĩ rằng loader sẽ tìm `int.class`.

Với `Class.forName`:
- `Class.forName("int")` **không trả `int.class`** theo overload thông thường.
- Tên descriptor như `[Ljava.lang.String;` dùng cho class mảng trong overload phù hợp và có quy tắc loader/component riêng.
- Mảng không được custom loader định nghĩa bằng cách đọc một `[L...;.class` theo đường file như class thường.
- Đối với named modules, `Class.forName(Module, String)` có semantics khác overload dùng loader và có thể trả `null` khi không tìm thấy trong module; không trộn lẫn các API khi viết test.

Những khác biệt đó giải thích một số “duplicate/not found” logs mà nguyên nhân thực sự là **sai dạng tên**, không phải concurrency.

## 21. Dùng ClassLoader nào để test? Parent và TCCL

Một framework có thể có:
- loader định nghĩa chính framework;
- loader cha cung cấp shared API;
- loader con định nghĩa plugin implementation;
- **Thread Context ClassLoader (TCCL)** dùng cho SPI/discovery;
- loader riêng cho JPMS ModuleLayer.

`Thread.currentThread().getContextClassLoader()` **không bắt buộc trùng với defining loader** của một class đang chạy.

Đặc biệt:
- `Class.forName(String)` dùng loader của caller, không tự dùng TCCL.
- `ServiceLoader.load(S.class)` thường dùng TCCL để tìm providers.
- `ClassLoader.loadClass(name)` dùng receiver loader và policy delegation.
- `type.getClassLoader()` cho biết defining loader thật của runtime class.
- `type.getModule()` cho biết runtime module trong JPMS.

Khi thử duplicate names, log cả **loader receiver** và **defining loader**. Hai requests đi vào hai receiver loaders không đủ chứng minh classes khác nhau nếu chúng cùng delegate cho parent.

## 22. Kiểm chứng thực tế trong app server hoặc plugin host

Trong production có thể không tự viết `findClass`, vì Tomcat, OSGi-style runtimes, build/test runners hoặc framework loaders đã quản lý class search. Quy trình chẩn đoán hợp lý:

1. **Xác định binary name** thật của class nghi vấn.
2. **Ghi process/thread IDs** và thời gian các yêu cầu load xảy ra.
3. **Ghi loader identity**: `ClassLoader` object, class của loader, defining loader của `Class<?>` kết quả.
4. Kiểm tra trạng thái `isRegisteredAsParallelCapable()` nếu API khả dụng.
5. Xem code loader override `loadClass` hay `findClass`, có global synchronization không.
6. Kiểm tra parent delegation và classpath/module-path/resources.
7. Kiểm tra nếu cùng name xuất hiện trong nhiều JARs: **artifact nào thật sự cung cấp bytes**.
8. Nếu gặp `LinkageError`, tìm điểm gọi `defineClass` và đường check/lock trước đó.
9. Nếu gặp `ClassCastException` dù names giống nhau, xem **defining loaders** và shared API placement.
10. Nếu nghi deadlock, lấy thread dumps ở thời điểm treo và phân tích vòng monitor/lock.
11. Nếu nghi leak/redeploy, xem loader generations còn reachable, TCCL và registries.
12. Tái hiện bằng test hai tên/cùng tên trong loader mới thay vì thay đổi source JAR của class đã load sẵn.

### Probe chẩn đoán tối thiểu

```java
public final class ClassOriginProbe {
    public static void print(Class<?> type) {
        System.out.println("name: " + type.getName());
        System.out.println("loader: " + type.getClassLoader());
        System.out.println("module: " + type.getModule());

        var domain = type.getProtectionDomain();
        var source = domain == null ? null : domain.getCodeSource();
        System.out.println("source: "
                + (source == null ? "<unavailable>"
                                  : source.getLocation()));
    }

    public static void main(String[] args) {
        print(ClassOriginProbe.class);
    }
}
```

Chạy:

```bash
javac --release 17 ClassOriginProbe.java
java ClassOriginProbe
```

Không đưa stdout cố định cho loader identity/CodeSource, vì tùy JDK, đường dẫn và môi trường. **CodeSource có thể `null` hoặc là URL trừu tượng**; với dynamic code, class bytes đã transform không nhất thiết trùng artifact disk hiện tại.

## 23. Instrumentation và JVM logs khi race khó tái hiện

### Java 17+ class loading log

Trên HotSpot:

```bash
java -Xlog:class+load=info -cp host-classes LoadRaceDemo
```

Lệnh dựa vào output của bài thực hành mục 8. Log có thể cho thấy `demo.Alpha`/`demo.Beta` được nạp từ byte array hoặc nguồn tùy loader. Thông tin chính xác của log phụ thuộc JDK; không coi đường log là cố định.

### Thread dump

```bash
jcmd <pid> Thread.print -l
```

`<pid>` là placeholder, thay bằng process ID thật. Trong dump, tìm threads đang:
- chờ `ClassLoader.loadClass` hoặc custom synchronized block;
- thực thi `findClass`/`defineClass`;
- giữ monitor của loader hoặc lock object theo tên;
- chờ JAR/cache/filesystem I/O;
- ở static initialization hoặc callback loader khác.

Cần chú ý rằng JVM có các đồng bộ nội bộ không nhất thiết được một công cụ deadlock detection báo đầy đủ. Đối chiếu nhiều thread dumps theo thời gian và logic code thay vì suy chỉ một snapshot.

### Heap/classloader stats

Nếu nhiều runs/redeploy làm classloader count tăng bất thường:

```bash
jcmd <pid> VM.classloader_stats
```

Đây là tiện ích phụ trợ, không phải phép thử correctness của nạp concurrent. Một class đã loaded trên nhiều independent plugin loaders có thể hoàn toàn hợp lệ; câu hỏi lifecycle là những loader cũ có còn cần thiết sau unload không.

## 24. Chẩn đoán lỗi theo hiện tượng

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Hai threads cùng name, `findClass` gọi hai lần | Override `loadClass` thiếu synchronization hoặc không kiểm tra loaded | Per-name lock, `findLoadedClass`, trace |
| `LinkageError: duplicate class definition` | `defineClass` lại cùng binary name trong cùng loader | Find/check/define order, race window |
| Hai tên khác nhau vẫn bị tuần tự hóa | Non-parallel loader, global monitor/cache lock | `isRegisteredAsParallelCapable` và thread dump |
| Latch không về 0 ở demo | Parent đã load class, sai `-cp`, registration lỗi, timeout/scheduler | Parent classpath, target directory, console |
| Hai loaders nạp cùng tên nhưng `Class<?>` vẫn bằng nhau | Cả hai delegate cho một parent defining loader | `getClassLoader` của kết quả |
| `ClassCastException` dù tên class giống nhau | Hai defining loaders độc lập | So `Class<?>` identity, shared API |
| `NoSuchMethodError` khi đổi classpath/JAR | Compile/runtime binary API mismatch | CodeSource, class loading log, dependency versions |
| `NoClassDefFoundError` ở class dependency | Dependency thiếu hoặc initialization failure khác | Lỗi gốc, loader hierarchy |
| `ClassCircularityError` | Vòng superclass/superinterface hierarchy, không phải chỉ hai threads | Kiểm tra class file/type graph |
| Deadlock khi loaders ủy quyền chéo | Whole-loader locks hoặc chu trình theo tên/global locks | Thread dumps và lock graph |
| Lỗi chỉ trên test runner | Test JVM/loader khác IDE/main app; TCCL khác | TestRuntimeClasspath, process/loader |
| Một class cũ vẫn được dùng sau thay JAR | Loader đã định nghĩa class và cache | Loader generation mới, process restart |

Không sửa tất cả các triệu chứng trên bằng cách “đăng ký parallel-capable”. Chỉ một số thuộc locking/concurrency; những lỗi khác thuộc identity, ABI, module access hoặc deployment.

## 25. Làm test concurrency đáng tin cậy

Một bài kiểm chứng tốt có **điều kiện quan sát cụ thể**:

### 25.1. Dùng fresh loader

Mỗi kịch bản cần loader mới hoặc tên class mới để tránh `findLoadedClass` trả cache hit trước khi test. Một lần đã load Alpha bằng một loader, gọi lại nó không còn test việc tìm bytes hay define class.

### 25.2. Điều khiển điểm vào, không điều khiển lịch scheduler bằng sleep

`CountDownLatch`/`CyclicBarrier` tạo điểm đồng bộ có thể chờ, nhưng cần:
- timeout có ý nghĩa và báo failure rõ;
- `finally` luôn release gates;
- không chờ hai arrivals trong một whole-loader monitor khi không có thread nào bên ngoài có thể release;
- không cố đo tốc độ từ một lần chạy.

### 25.3. Test cả khác tên và cùng tên

**Khác tên:** hai tasks phải có thể vào `findClass` khi tên không phụ thuộc nhau và policy không có global lock.

**Cùng tên:** kết quả hai futures phải là **cùng `Class<?>`** và custom loader chỉ **define một lần**.

Không chỉ test khác tên: một loader có thể cho tất cả tên chạy song song **nhưng sai** vì không bảo vệ duplicate define. Không chỉ test cùng tên: loader serial toàn bộ cũng làm đúng việc chống trùng nhưng mất concurrency.

### 25.4. Đừng “chứng minh” bằng log có thứ tự ngẫu nhiên

Một số dòng log có thể interleave bất kỳ. Hãy đưa ra:
- boolean assertions;
- counts;
- identity comparisons;
- latches/queues ghi nhận trạng thái;
- classloader IDs;
- errors theo loại, không phụ thuộc exact message.

Demo mục 8 làm đúng hướng này: stdout quyết định bởi invariants khi test hoàn tất, không dựa vào thread nào in trước.

### 25.5. Tránh biến test thành stress vô hạn

Nếu muốn stress:
- tạo nhiều loaders độc lập hoặc nhiều names khác nhau;
- giới hạn thread/heap/class count;
- chạy nhiều iterations;
- thu failure logs, không nuốt exceptions;
- cleanup executors và loaders/resource handles;
- lưu nhận diện JDK/OS/CI config.

Không viết test mở hàng ngàn JAR/threads không giới hạn chỉ để “kiểm chứng race”; nó có thể tự tạo OutOfMemoryError/file descriptor exhaustion.

## 26. Gợi ý assertion cho automated test

Nếu dùng JUnit, có thể kiểm tra tương tự:

```java
// TRÍCH ĐOẠN JUnit — yêu cầu project có JUnit Jupiter dependency.
assertSame(classFromT1, classFromT2);
assertEquals(1, loader.alphaFinds.get());
assertSame(loader, classFromT1.getClassLoader());
```

Đây là trích đoạn, không phải file Java SE độc lập. Thứ tự assertions cần phối hợp sau khi các `Future` hoàn tất, không đọc counters trong lúc workers chưa xong.

Đối với **khác tên**:
- Chứng minh `CountDownLatch(2)` đã đếm về 0 trong khi gate chưa release.
- Kiểm tra `Class<?>` được định nghĩa bởi đúng loader.
- Kiểm tra counter cho mỗi tên bằng 1.

Đối với **same name**:
- `assertSame(c1, c2)`;
- `alphaFinds == 1`;
- không gặp duplicate `LinkageError` trong luồng loading chuẩn.

Đối với **direct duplicate define**:
- `assertThrows(LinkageError.class, () -> raw.define(...))` sau lần define đầu tiên thành công.

Các ví dụ `assertSame`/`assertThrows` là API JUnit 5 khi đã import và cấu hình đúng; **các file Java chạy độc lập** trong mục 6 và 8 không phụ thuộc JUnit.

## 27. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
|---|---|
| “Parallel-capable nghĩa là hai thread có thể định nghĩa cùng tên hai lần” | Không; cùng tên vẫn phải dùng chung lock/loaded class |
| “Chỉ `registerAsParallelCapable()` là mọi loader code đã thread-safe” | Không; shared caches/resources và overrides cần đúng |
| “Subclass kế thừa trạng thái registered của ClassLoader tự động” | Không; subclass cần đăng ký riêng và superclass chain hợp lệ |
| “`getClassLoadingLock` luôn trả chính loader” | Chỉ mặc định khi non-parallel-capable |
| “Hai String objects khác nhau nghĩa là hai class names khác nhau” | Không; xét nội dung binary name |
| “Hai ClassLoaders có tên class giống thì Class<?> chắc bằng nhau” | Không; còn defining loader và delegation |
| “Hai loader objects khác nhau thì Class<?> chắc khác” | Không; có thể cùng delegate parent |
| “Trùng class ở hai JAR luôn gây `LinkageError` duplicate” | Không; loader thường chỉ chọn một definition cho cùng tên |
| “Gọi `defineClass` trực tiếp giống gọi `loadClass`” | Không; bỏ check/delegation/lock |
| “`loadClass` luôn chạy static initializer” | Không; initialization có quy tắc riêng |
| “Khác binary names là chắc có tốc độ gấp đôi” | Không; scheduler, dependencies, I/O và locks khác |
| “Loader parallel-capable không thể deadlock” | Không; cycles và custom locks vẫn có thể |
| “`findLoadedClass` là một cache ứng dụng có thể xóa tùy ý” | Không; gắn với runtime loader state |
| “Đổi file .class trên disk là JVM tự nạp lại definition cũ” | Không; thường phải dùng loader/process mới |
| “Catch mọi LinkageError rồi child-first fallback sẽ sửa class collision” | Dễ che lỗi thật và phá type identity |
| “Dùng Thread.sleep là đủ chứng minh cùng lúc” | Không; dùng synchronization primitives và kiểm tra invariants |
| “Log từ một thread đủ biết class source thực tế” | Cần defining loader/CodeSource/log và parent hierarchy |

## 28. Câu hỏi tự kiểm tra

1. **Hai threads cùng gọi `loadClass` cho cùng tên qua cùng loader chuẩn nhận mấy runtime classes?** Một class object được chia sẻ sau khi load thành công.
2. **Mục đích `findLoadedClass` là gì?** Trả class đã loaded, tránh định nghĩa lại và giữ identity.
3. **Không parallel-capable, `getClassLoadingLock` mặc định trả gì?** Chính loader instance (`this`).
4. **Parallel-capable, hai tên khác nhau có thể dùng locks khác nhau không?** Có.
5. **Hai `new String("demo.Alpha")` khác references nhưng cùng content có nên dùng cùng class loading lock không?** Có, cùng binary name.
6. **Vì sao cần `registerAsParallelCapable` trong static initializer?** Đăng ký loader class trước khi tạo instance, với superclass chain hợp lệ.
7. **Chỉ override `findClass` có lợi gì?** Giữ thuật toán `loadClass`, loaded check, delegation và locking mặc định.
8. **`AtomicInteger` trong demo dùng làm gì?** Đếm findClass calls an toàn khi các threads vào đồng thời.
9. **CountDownLatch(2) ở khác tên chứng minh gì?** Hai lời gọi `findClass` đã đến điểm gate trước release.
10. **Kết quả `same name findClass calls: 1` chứng minh gì?** Hai requests cùng name không làm loader định nghĩa/tìm lại class hai lần trong kịch bản test.
11. **Direct `defineClass` hai lần cùng binary name và loader gây gì?** `LinkageError`.
12. **Hai loaders độc lập define cùng binary name có hợp lệ không?** Có thể, nhưng tạo runtime classes khác nhau.
13. **Hai class cùng binary name nhưng defining loader khác nhau cast được không?** Không mặc nhiên.
14. **Hai loader con cùng delegate parent có nhận cùng Class<?> không?** Có thể.
15. **Một parent đã load Alpha, child `findClass` có luôn được gọi không?** Không trong parent-first delegation mặc định.
16. **Tại sao không đưa plugin-classes vào host classpath của demo?** Tránh parent định nghĩa Alpha/Beta trước custom loader.
17. **`ClassLoader.loadClass` khác `Class.forName(name,true,loader)` thế nào về initialization?** loadClass không tự bắt buộc init; forName overload với `true` yêu cầu init.
18. **Nạp class cùng lúc nghĩa là code static initialization chạy hai lần không?** Không.
19. **Để kiểm tra duplicates runtime, chỉ xem Maven dependency tree có đủ không?** Không; phải xem loader và class source thực tế.
20. **Nếu worker test timeout, nên suy loader sai ngay không?** Không; kiểm tra classpath, parent, scheduler, latches và resource starvation.

## 29. Tài liệu chuẩn

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, `registerAsParallelCapable`, `getClassLoadingLock`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): runtime `Class<?>`, `getClassLoader()`, `forName()`, type identity.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ điểm bắt đầu và đợi tín hiệu không dùng `Thread.sleep`.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit tasks và `Future` kết quả.
- [Java SE 17 — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): lỗi linking/definition không tương thích.
- [Java Virtual Machine Specification 17 — 5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class creation, defining/initiating loader, constraints và runtime identity.
- [Oracle — Multithreaded Custom Class Loaders](https://docs.oracle.com/javase/8/docs/technotes/guides/lang/cl-mt.html): nguyên tắc parallel-capable và custom loader đa luồng.

**Kết luận:** Một ClassLoader đúng phải thực hiện hai điều **cùng lúc**: **đảm bảo duy nhất một definition cho mỗi binary name trên một defining loader**, và khi đã đăng ký parallel-capable thì **không khóa rộng vô ích khiến các tên khác nhau không thể nạp đồng thời**. Kiểm chứng bằng **fresh loaders, CountDownLatch, `Class<?>` identity, `findClass` counters và lỗi duplicate `defineClass`**. Với các JARs hoặc plugins trùng tên, luôn phân biệt **trùng bytes nguồn**, **trùng định nghĩa trong một loader** và **hai runtime classes cùng tên ở hai loaders** trước khi quyết định cách xử lý.
