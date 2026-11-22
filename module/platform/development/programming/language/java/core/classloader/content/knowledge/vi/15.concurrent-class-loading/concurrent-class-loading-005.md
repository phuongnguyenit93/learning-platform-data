# Tránh race condition giữa `findLoadedClass` và `defineClass`

> **Java Core → ClassLoader → Nạp đồng thời.** Bài học tập trung vào một lỗi rất cụ thể của custom class loader: **hai thread cùng thấy một binary name chưa được nạp và cùng cố định nghĩa class ấy trong cùng một loader**. Mục tiêu là hiểu bất biến cần giữ, cách `ClassLoader.loadClass` mặc định phối hợp concurrency, khi nào dùng `getClassLoadingLock`, `registerAsParallelCapable`, cách tự tái hiện lỗi có kiểm soát, và cách kiểm thử khi triển khai plugin/child-first loader.

## 1. Bất biến quan trọng nhất

Với một runtime class/interface thông thường, định danh kiểu dựa trên cặp **(binary name, defining class loader)**. Đối với mỗi binary name, một defining loader phải tránh cố `defineClass` cùng class **hai lần** trong namespace của chính nó. Việc nạp một tên bằng hai thread cùng lúc phải đưa đến **cùng một đối tượng `Class<?>`** nếu cả hai thành công, thay vì hai lần định nghĩa trùng tên.

Các API:

- `findLoadedClass(String name)`: trả `Class<?>` đã được VM ghi nhận với loader này là **initiating loader** của tên tương ứng, hoặc `null` nếu chưa thấy. Không phải phép **giữ chỗ** hay lệnh khóa tên class.
- `defineClass(String name, byte[] b, int off, int len)`: chuyển bytecode thành runtime `Class<?>` được loader hiện tại định nghĩa. Định nghĩa trùng binary name trong cùng loader không được phép; JVM thường ném `LinkageError`.
- `loadClass(String name, boolean resolve)`: theo implementation mặc định, làm một chuỗi thao tác gồm kiểm tra đã nạp → delegation tới parent → `findClass` nếu cần → `resolveClass` khi flag `resolve=true`, được đồng bộ bằng `getClassLoadingLock(name)`.
- `getClassLoadingLock(String name)`: cung cấp lock phù hợp cho **toàn bộ critical section** của một yêu cầu nạp class. Nếu loader **không parallel capable**, lock là chính loader; nếu đã đăng ký parallel capable, thường là lock riêng cho binary name.
- `registerAsParallelCapable()`: khai báo subclass hỗ trợ nạp class đồng thời với locking đúng. Nó **không tự sửa một override `loadClass` thiếu đồng bộ**.

**Ý chính:** `findLoadedClass(name) == null` tại một thời điểm **không cấp độc quyền** gọi `defineClass(name, ...)`. Check và define phải được phối hợp trong một giao thức khóa/ownership nhất quán.

## 2. Race check-then-act xảy ra thế nào?

Mẫu sai:

~~~java
// CHỈ MINH HỌA LỖI: nằm trong subclass ClassLoader.
// Không dùng pattern này trong loader production.
Class<?> c = findLoadedClass(name);
if (c == null) {
    byte[] bytes = fetchClassBytes(name);
    c = defineClass(name, bytes, 0, bytes.length);
}
return c;
~~~

`fetchClassBytes` là hàm giả định. Khi hai thread đi vào `loadClass` của **cùng một loader instance**, có thể xảy ra:

~~~text
                 Thread T1                       Thread T2
                    |                               |
findLoadedClass(X) -> null                         |
                    |               findLoadedClass(X) -> null
                    |                               |
       fetch bytes(X)                       fetch bytes(X)
                    |                               |
         defineClass(X) OK                    |
                    |                          defineClass(X)
                    |                               |
                    |                            LinkageError
                    v
          Class<?> X đã tồn tại
~~~

Đây là race **time-of-check to time-of-use (TOCTOU)**: kết quả `null` chỉ đúng tại thời điểm đọc; hai thread không được phân công ai là **người duy nhất** định nghĩa class.

**Không coi `LinkageError` là cách đồng bộ thay thế.** JVM bảo vệ bất biến định danh kiểu bằng cách từ chối việc định nghĩa trùng, nhưng ứng dụng có thể thất bại ngẫu nhiên dưới tải. Đặc biệt, không nên bắt `LinkageError` rồi coi như `ClassNotFoundException` và âm thầm thử loader khác: như thế có thể che lấp bytecode hỏng, loader constraints hoặc version conflict.

### 2.1. Điều không giúp sửa race

- `volatile boolean loaded` không làm chuỗi “check → bytes → define” trở thành atomic.
- `ConcurrentHashMap<String, byte[]>` chỉ làm map bytes thread-safe; nó không tự bảo vệ thao tác `defineClass` nếu hai bên đồng thời đi qua check.
- Gọi `Thread.sleep(...)` để giãn thời điểm không phải fix; nó chỉ thay xác suất xuất hiện lỗi.
- Chỉ đặt `synchronized` trên `findClass` không chắc đủ nếu nơi khác gọi `defineClass` ngoài cùng lock, hoặc `loadClass` tự gọi recursion/delegation sai.
- Đăng ký `registerAsParallelCapable` nhưng tự override `loadClass` và bỏ `synchronized(getClassLoadingLock(name))` vẫn sai.
- `resolveClass(c)` chỉ link class; nó không thay thế việc bảo vệ `defineClass` và không chạy initializer.

## 3. Cách mặc định của `ClassLoader` giải quyết vấn đề

Java `ClassLoader` khuyến nghị **override `findClass` khi có thể**, không override toàn bộ `loadClass`. Theo Javadoc, implementation mặc định của `loadClass(name, resolve)` về cơ bản:

~~~java
// PSEUDOCODE: minh họa ý tưởng; không phải source để copy.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = parentLoadClass(name);
        } catch (ClassNotFoundException notInParent) {
            // Sẽ tìm trong loader hiện tại.
        }
        if (c == null) {
            c = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

`parentLoadClass` ở đây là **ký hiệu giả** để giải thích delegation tới parent/VM bootstrap; không phải method trong API `ClassLoader`. Điểm học cần giữ là **toàn bộ** check, delegation, find và optional link nằm dưới **cùng loading lock**.

Với hai thread cùng yêu cầu binary name X:

1. T1 lấy lock của X.
2. T2 chờ lock của X, thay vì cũng thấy `findLoadedClass(X)==null` bên trong cùng vùng bảo vệ.
3. T1 tìm class từ parent hoặc gọi `findClass` để tạo một class, rồi trả.
4. T2 lấy lock, kiểm tra lại `findLoadedClass(X)` sau khi T1 hoàn thành và nhận đúng class đã được tải/ghi nhận.
5. Cả hai thành công trả **cùng `Class<?>`**. Nếu có lỗi thực về bytecode/parent/linking, lỗi thích hợp vẫn phải được xử lý, không bị khóa “nuốt” đi.

Đây là lý do các bước **check và define** phải giữ nguyên trong critical section, không phải:

~~~java
// SAI: check ở ngoài khóa và không recheck trước define.
Class<?> c = findLoadedClass(name);
if (c == null) {
    synchronized (getClassLoadingLock(name)) {
        c = defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Cả T1 và T2 có thể đã thấy `null` trước lock; khi mỗi thread lần lượt lấy lock, T2 vẫn gọi `defineClass` lần nữa. Nếu dùng mô hình double-check, **bắt buộc check lại** bên trong đúng lock, nhưng với custom classloader thường viết nguyên đoạn dưới lock rõ ràng hơn.

## 4. Cách an toàn nhất: chỉ override `findClass`

Nếu chỉ có nhu cầu đọc bytecode từ thư mục/JAR/service riêng, hãy giữ `loadClass` mặc định:

~~~java
public final class BytesLoader extends ClassLoader {
    public BytesLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        byte[] bytes = readBytesFromTrustedStore(name);
        return defineClass(name, bytes, 0, bytes.length);
    }

    private byte[] readBytesFromTrustedStore(String name)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(name); // Minh họa điểm mở rộng.
    }
}
~~~

Tệp `BytesLoader.java` trên Java 17+ biên dịch được, nhưng method `readBytesFromTrustedStore` được để ở trạng thái **chỉ minh họa**: nó luôn báo chưa tìm thấy, không phải implementation load bytes thật. Đối với project thực, thay method này bằng logic đọc bytes theo binary name, xác minh nguồn, đóng streams và chuyển lỗi I/O phù hợp.

Lợi ích: `ClassLoader.loadClass` mặc định đã quản lý locking theo `getClassLoadingLock` và gọi `findLoadedClass`. Bạn ít phải tự viết các chi tiết concurrency nguy hiểm.

Tuy nhiên **không** gọi trực tiếp `customLoader.findClass(name)` từ phần còn lại của ứng dụng để “bỏ qua delegation”: `findClass` là protected hook, không phải public entrypoint chuẩn. Kể cả bạn public hóa một wrapper gọi thẳng `findClass`, nó có thể **bỏ qua locking và kiểm tra đã nạp** nếu thiết kế sai. Phía caller nên dùng `loadClass(name)`.

## 5. Nếu bắt buộc override `loadClass`: khóa quanh toàn bộ check/define

Một child-first loader có thể cần load package sở hữu trước khi delegate; phải đặc biệt thận trọng. Skeleton:

~~~java
public final class PackageLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "parallel-capable registration failed");
        }
    }

    public PackageLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        synchronized (getClassLoadingLock(name)) {
            Class<?> c = findLoadedClass(name);

            if (c == null) {
                if (name.startsWith("myplugin.impl.")) {
                    try {
                        c = findClass(name);
                    } catch (ClassNotFoundException missingLocally) {
                        c = super.loadClass(name, false);
                    }
                } else {
                    c = super.loadClass(name, false);
                }
            }

            if (resolve) {
                resolveClass(c);
            }
            return c;
        }
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(name); // Tìm bytes tại đây.
    }
}
~~~

Tệp `PackageLoader.java` là **skeleton biên dịch được Java 17+** nhưng `findClass` chỉ là placeholder hành vi (luôn ném `ClassNotFoundException`) nên không nạp plugin thật. Phần đáng học là khóa theo `getClassLoadingLock(name)` và check `findLoadedClass` **bên trong** critical section.

**Lưu ý đặc biệt về child-first + parallel loading:**

- `registerAsParallelCapable()` phải được gọi trong quá trình **class initialization của chính subclass**, trước khi tạo instance; mọi superclass classloader cũng phải đăng ký phù hợp. `ClassLoader` gốc đã đăng ký, nhưng một superclass custom trung gian có thể chưa đăng ký, làm registration của child thất bại.
- Nếu loader **chưa parallel capable**, `getClassLoadingLock(name)` trả chính loader object. Khi đăng ký thành công, lock theo name giúp tải **các tên khác nhau** đồng thời, nhưng với **cùng name** vẫn phải tuần tự.
- Không nên dùng `synchronized(this)` nếu mục đích là nạp song song các tên khác nhau: khóa toàn loader có thể làm giảm concurrency hoặc gây deadlock khi delegation graph không thuần thứ bậc. Tuy vậy dùng khóa chung vẫn có thể phù hợp nếu loader không hỗ trợ parallel loading.
- `getClassLoadingLock` là protected, và trả lock khác nhau tùy loại loader; không lấy lock vào một map riêng không đồng bộ với các đường nạp khác.
- `super.loadClass(name,false)` ở skeleton là cách dùng semantics parent-first mặc định khi đã quyết định fallback, nhưng phải đảm bảo không tạo vòng delegation giữa các loader và không có code tự gọi lại vòng không kết thúc.
- Catch **chỉ `ClassNotFoundException`** khi cần fallback có chủ đích. Không catch mọi `Throwable`/`LinkageError` để giả vờ class không tồn tại.
- `resolveClass(c)` thực hiện linking nếu `resolve=true`, **không** làm `<clinit>` chạy; static initialization là một giai đoạn khác.

Nếu không có yêu cầu child-first rất rõ, ưu tiên `findClass` với implementation `loadClass` mặc định.

## 6. Thí nghiệm reproducible: cố tạo race và sửa bằng lock đúng

Thí nghiệm dùng **hai file Java 17+**. Chúng ta dùng cùng bytecode của `PluginTask` nhưng tạo các loader riêng để thử hai chính sách. `UnsafeLoader` cố ý sai và đặt `CyclicBarrier` sau `findLoadedClass` để **hai thread đều kiểm tra trước khi ai gọi `defineClass`**; đây là kỹ thuật tạo race có kiểm soát trong bài lab, không dành cho production.

### 6.1. File `PluginTask.java`

~~~java
public class PluginTask {
    public String result() {
        return "ok";
    }
}
~~~

Class này nằm ở default package để lệnh chạy đơn giản. Nó không chủ động tạo threads, không cần dependency ngoài JDK.

### 6.2. File `RaceDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RaceDemo {
    private static final String TARGET = "PluginTask";

    // SAI CÓ CHỦ Ý: thiếu class-loading lock.
    static class UnsafeLoader extends ClassLoader {
        private final byte[] bytes;
        private final CyclicBarrier twoChecks = new CyclicBarrier(2);

        UnsafeLoader(byte[] bytes) {
            super(RaceDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            Class<?> found = findLoadedClass(name);
            if (found == null) {
                try {
                    // Cả hai threads tới đây khi class vẫn chưa define.
                    twoChecks.await();
                } catch (Exception ex) {
                    throw new ClassNotFoundException(name, ex);
                }
                found = defineClass(name, bytes, 0, bytes.length);
            }

            if (resolve) {
                resolveClass(found);
            }
            return found;
        }
    }

    // ĐÚNG: hai yêu cầu cùng tên chỉ một thread được define.
    static class SafeLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "parallel registration failed");
            }
        }

        private final byte[] bytes;

        SafeLoader(byte[] bytes) {
            super(RaceDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytes, 0, bytes.length);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    static void test(String label, ClassLoader loader)
            throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Class<?>> request = () -> {
            start.await();
            return loader.loadClass(TARGET);
        };

        try {
            Future<Class<?>> first = workers.submit(request);
            Future<Class<?>> second = workers.submit(request);
            start.countDown();

            int successes = 0;
            int linkageErrors = 0;
            Class<?> firstResult = null;
            boolean sameClass = true;

            for (Future<Class<?>> f :
                    java.util.List.of(first, second)) {
                try {
                    Class<?> result = f.get();
                    successes++;
                    if (firstResult == null) {
                        firstResult = result;
                    } else {
                        sameClass &= firstResult == result;
                    }
                } catch (ExecutionException ex) {
                    if (ex.getCause() instanceof LinkageError) {
                        linkageErrors++;
                    } else {
                        throw ex;
                    }
                }
            }

            System.out.println(label + ": success=" + successes
                    + ", linkageError=" + linkageErrors
                    + ", sameClass=" + sameClass);
        } finally {
            workers.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("PluginTask.class"));
        test("unsafe", new UnsafeLoader(bytes));
        test("safe", new SafeLoader(bytes));
    }
}
~~~

**Lệnh** từ thư mục chứa cả hai source:

~~~bash
javac --release 17 PluginTask.java RaceDemo.java
java -cp . RaceDemo
~~~

**Output kỳ vọng khi `UnsafeLoader` bị ép qua barrier**:

~~~text
unsafe: success=1, linkageError=1, sameClass=true
safe: success=2, linkageError=0, sameClass=true
~~~

Ở dòng unsafe, một thread thành công, một thread bị VM từ chối do duplicate definition; giá trị `sameClass=true` chỉ vì **một** thread trả được `Class` nên không có hai kết quả thành công để so sánh. Ở dòng safe, cả hai đều thành công và trả **đúng cùng `Class<?>`**, vì thread thứ hai thấy class đã nạp dưới lock.

**Giới hạn thí nghiệm:**

- `CyclicBarrier` trong unsafe chỉ để ép đúng race; nếu thay bằng `sleep` hay `yield`, output có thể ngẫu nhiên, không chứng minh nguyên nhân.
- Mã intentionally bỏ parent-first cho **chính xác tên `PluginTask`** để loader tự định nghĩa class; mọi tên khác đi qua `super.loadClass`. Không dùng cách này cho toàn bộ `java.*` hoặc shared API packages.
- `PluginTask.class` có thể nằm trên application classpath vì `javac` tạo file; override riêng một binary name khiến loader thí nghiệm vẫn tự define. Không mở rộng kết luận rằng child-first toàn hệ thống là chính sách an toàn.
- File `PluginTask.class` cần tồn tại tại **current working directory** khi chạy. Lệnh trên đáp ứng điều đó nếu dùng đúng cấu trúc.
- Việc đếm `LinkageError` chỉ phục vụ minh họa; code production nên xử lý lỗi đúng loại, không bỏ qua.
- Khi đo performance/concurrency thật, phải kiểm tra nguồn bytes, I/O, delegation, class initialization và JIT warm-up; bài lab này chỉ cô lập check-then-define race.

### 6.3. Vì sao `findLoadedClass` vẫn cần nằm trong lock?

Giả sử `SafeLoader` bỏ bước `findLoadedClass` bên trong lock:

~~~java
synchronized (getClassLoadingLock(name)) {
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Cả T1 và T2 có thể lần lượt đi qua lock rồi **cả hai đều gọi `defineClass`**. Lock chỉ bảo đảm không đồng thời, **không** tự bảo đảm class chỉ được define một lần. Phải thực hiện **check lại khi giữ khóa**, và trả `Class<?>` đã có.

Ngược lại, nếu chỉ kiểm tra ngoài lock rồi vào lock nhưng không check lại, bạn vẫn bị duplicate definition. Cặp **same lock + recheck** mới giải quyết đúng vấn đề.

## 7. Race cùng tên khác với nạp nhiều tên song song
`getClassLoadingLock(name)` bảo vệ từng binary name khi loader đã parallel-capable; nếu subclass chưa đăng ký, default lock là chính loader. Điều kiện đăng ký là **trước khi tạo instance** và **mọi superclass loader phải registered**. Hai tên X/Y có thể tiến hành đồng thời, nhưng hai thread cùng tên X vẫn phải có **lock + `findLoadedClass` bên trong lock**.
```text
T1: lock(X) → findLoadedClass(X)==null → defineClass(X) → unlock
T2: đợi lock(X) → findLoadedClass(X)==Class X → reuse
```
Nếu loader A nạp X trong lúc chờ loader B nạp Y, và B lại chờ A, có thể xuất hiện deadlock kể cả dùng per-name locks. Hãy thiết kế graph delegation có điểm kết thúc. Đây là vấn đề riêng với race check-then-define mà bài đang xử lý.

## 8. Phân biệt race định nghĩa class với race khởi tạo class

**Loading/linking** và **initialization** là hai giai đoạn khác nhau:

- Hai thread đồng thời gọi `loadClass("X")` cần điều phối để **một runtime `Class`** được trả và không duplicate `defineClass`.
- Hai thread đồng thời thực hiện active use (ví dụ `new X()` hoặc static nonconstant field) được JVM phối hợp **class initialization** theo JLS `12.4.2`. `<clinit>` của một runtime class thành công chỉ chạy một lần, và thread khác chờ khi cần.
- `resolveClass(c)` chỉ yêu cầu linking, **không thay thế** cả hai cơ chế ở trên.
- `synchronized (getClassLoadingLock(name))` trong custom loader giải quyết class definition/lookup race, **không** phải lock bạn nên dùng để kiểm soát mutable static state sau initialization.

Vì vậy có thể có code load class thread-safe nhưng service bên trong class vẫn có **data race** ở các static fields khi update sau init. Hai loại lỗi dùng biện pháp khác nhau.

## 9. Identity, initiating loader và parent-first

`findLoadedClass` trả về class mà loader hiện tại đã được ghi nhận là **initiating loader**, không nhất thiết loader đó trực tiếp define class. Nếu loader L delegate tên `java.lang.String` lên bootstrap, `String.class.getClassLoader()` thường trả `null`; L vẫn có thể tham gia initiating loader record.

**Không tự define lại class đã được parent cung cấp** chỉ vì bạn muốn child-first toàn cục; điều này có thể phá type identity. Với plugin system:

- Các API chung như `host.api.PluginContract` nên được định nghĩa ở **shared parent**.
- Implementation riêng `plugin.impl.Handler` có thể do plugin loader định nghĩa.
- Nếu hai plugin loaders cùng define `plugin.impl.Handler`, đó là **hai runtime types** khác nhau, hợp lệ khi chủ đích là plugin isolation.
- Nhưng một loader **không được define hai phiên bản của cùng binary name** chỉ để hot reload. Tạo loader thế hệ mới, chuyển request routing có kiểm soát, dọn loader cũ khi không còn references.

Kiểm thử type contract bằng `sharedTypeFromHost == sharedTypeFromPlugin` và `SharedApi.class.isAssignableFrom(implType)`; đừng dùng `getName().equals` làm bằng chứng type compatible.

## 10. Một số lỗi cạnh tranh khác trong custom classloader

### 10.1. Cache bytes an toàn khác cache Class an toàn

Có thể dùng immutable `byte[]` được đọc trước, hoặc map cache bytes thread-safe để giảm I/O, nhưng **đảm bảo một người định nghĩa class** vẫn cần đúng lock. Nếu bytes có thể bị cập nhật đồng thời, bạn còn phải đảm bảo mỗi lần định nghĩa đọc **một bản nguyên vẹn**, không dùng `byte[]` bị mutate sau khi verify/checksum.

### 10.2. Đồng thời đóng loader và nạp class

Với `URLClassLoader.close()`, Javadoc không bảo đảm kết quả class loading khi `close` chạy cạnh tranh với `loadClass`. Đây là race **lifecycle** khác với duplicate `defineClass`. Cần ngăn công việc mới, drain tasks đang chạy, sau đó close loader; khóa `getClassLoadingLock(name)` chỉ bảo vệ loading, không tự quản lý toàn bộ vòng đời plugin.

### 10.3. Exception classification

| Lỗi | Ý nghĩa thường gặp | Không nên làm |
| --- | --- | --- |
| `ClassNotFoundException` | Loader không tìm class theo tên được yêu cầu | Nuốt lỗi rồi trả `null` từ `loadClass` |
| `LinkageError` khi define trùng | Bug phối hợp nạp hoặc xung đột runtime identity | Bắt lỗi để giả vờ chưa tìm thấy |
| `ClassFormatError`/`VerifyError` | Bytecode không đúng hoặc vi phạm verification | Retry vô hạn với cùng bytes |
| `UnsupportedClassVersionError` | Bytecode quá mới so với runtime | Dùng khóa thay vì sửa runtime/target |
| `ClassCircularityError` | Quan hệ superclass/interface vòng không hợp lệ | Bỏ khóa để cố vượt qua |
| `NoClassDefFoundError` | Thiếu class runtime, initialization trước đó thất bại hoặc nguyên nhân linkage | Kết luận ngay rằng chỉ thiếu JAR |

**Lưu ý:** Các lỗi ở bảng không buộc xuất hiện tại một thời điểm duy nhất do JVM có thể eager/lazy link/resolve. Hãy đọc nguyên nhân gốc và log ban đầu.

### 10.4. Thử đăng ký parallel capable nhưng không kiểm tra kết quả

`registerAsParallelCapable()` trả boolean. Nếu false, `getClassLoadingLock(name)` có thể không cho per-name lock bạn mong đợi. Không khẳng định performance song song chỉ vì có static call này; kiểm tra điều kiện superclass hierarchy và test.

### 10.5. Đổi chính sách nạp khi đang chạy

Một loader đã trả/define `foo.Bar` không thể “định nghĩa lại” `foo.Bar` ngay trong cùng namespace khi file JAR đổi trên disk. Nên coi package ownership/delegation policy là **bất biến** cho đời sống của loader, không để một thread đổi map prefix giữa lúc thread khác tìm class.

## 11. Test thực tế ngoài bài lab

Một bản custom loader production nên có các kiểm thử:

1. **Concurrent same name:** khởi tạo một loader mới, dùng `CountDownLatch` phát nhiều tác vụ đồng thời cùng gọi `loadClass(X)`; xác minh tất cả thành công, đối tượng `Class<?>` cùng identity.
2. **Concurrent different names:** dùng nhiều classes `X,Y,Z` và kiểm tra loader parallel capable cho phép nạp hợp lệ không deadlock; không đánh giá bằng output order cố định.
3. **Duplicate name fail-fast:** cố ý tạo broken implementation trong test riêng; assert nó thất bại thay vì chôn lỗi.
4. **Delegation:** shared API do parent define; plugin class do child define; `Class.getClassLoader()` và `isAssignableFrom` đúng.
5. **I/O errors:** bytes thiếu/hỏng, JAR đang đóng, mismatch name trong class file; exception được phân loại đúng.
6. **Lifecycle:** stop plugin trong lúc có worker; chắc chắn không đóng URLClassLoader trước khi in-flight loads kết thúc.
7. **Repeated reload:** tạo loader mới theo mỗi generation, không giữ TCCL/thread cache/host registry làm loader cũ còn reachable.
8. **Module/access:** nếu dùng JPMS, test readability/exports/opens; khóa đúng không sửa được module access violation.
9. **Stress:** chạy nhiều vòng, bật logging và kiểm tra stack traces; không dựa trên một lần test race không tái hiện.
10. **Timeout/deadlock:** test cancellation, lấy thread dump, tránh treo vô thời hạn trong CI.

### 11.1. Không sử dụng lệnh ngủ để “kiểm thử race”

Một chương trình chạy 100.000 lần không thấy lỗi **không chứng minh** code không race; scheduler có thể chưa tạo interleaving bất lợi. Dùng barrier trong test như `RaceDemo` buộc hai thread cùng đi qua check để minh họa lỗi một cách có kiểm soát. Với production, dựa vào **bất biến và khóa đúng**, rồi dùng stress/observability như bổ trợ.

### 11.2. Quan sát bằng công cụ JDK

~~~bash
java -version
javap -c -p RaceDemo
java -Xlog:class+load=info -cp . RaceDemo
~~~

`-Xlog` là chẩn đoán của JVM hỗ trợ unified logging như HotSpot; đầu ra và tag support phụ thuộc runtime. Khi nghi deadlock, có thể lấy thread dump (`jcmd <pid> Thread.print` nếu runtime hỗ trợ) và xem thread nào đang giữ loading lock; không thay bằng parse thứ tự `class+load` log như một contract của JLS.

## 12. Checklist khi review `loadClass`

- [ ] Có cần override `loadClass` không, hay chỉ `findClass` là đủ?
- [ ] Mỗi lần nạp cùng name có dùng đúng `getClassLoadingLock(name)`?
- [ ] `findLoadedClass(name)` **nằm trong critical section**, và được kiểm tra trước khi gọi `defineClass`?
- [ ] Có bỏ việc recheck bên trong lock không? Nếu có, sửa.
- [ ] `resolveClass(c)` chỉ gọi khi `resolve=true` và class token đã hợp lệ?
- [ ] Parent delegation/child-first package policy nhất quán, không tạo vòng?
- [ ] Có catch rộng `Throwable`/`LinkageError` rồi retry mù quáng không?
- [ ] `registerAsParallelCapable` được gọi đúng thời điểm và superclass hierarchy hỗ trợ?
- [ ] Các task load class đồng thời với close/unload được phối hợp lifecycle?
- [ ] Test nhiều threads cùng name trả đúng **một `Class<?>`**?
- [ ] Shared API không bị custom loader define lại?
- [ ] Code có phân biệt class loading, linking và initialization không?

## 13. Câu hỏi tự kiểm tra

1. Vì sao `findLoadedClass(name)==null` không đảm bảo thread được gọi `defineClass`? **Vì thread khác có thể define cùng tên ngay sau check.**
2. Vì sao `synchronized` chỉ quanh `defineClass` vẫn có thể sai? **Nếu không recheck dưới lock, thread thứ hai vẫn define trùng khi đến lượt.**
3. API nào cấp lock cho đúng tên? **`getClassLoadingLock(name)`.**
4. Không parallel capable, lock ấy là gì? **Chính ClassLoader object** theo API.
5. Parallel capable, hai class khác tên có thể load đồng thời không? **Có**, theo per-name locks nhưng không bảo đảm hoàn toàn không chờ do dependencies.
6. Có nên override toàn bộ `loadClass` nếu chỉ cần đọc bytes riêng? **Thường không; override `findClass`**.
7. `registerAsParallelCapable` có tự thêm synchronization vào override sai? **Không**.
8. Khi hai threads định nghĩa cùng binary name trong một loader, lỗi nào thường thấy? **`LinkageError`** do duplicate definition.
9. Khi hai loaders khác nhau cố ý định nghĩa cùng binary name để plugin isolation, có luôn là lỗi? **Không**, vì runtime identity khác; vấn đề sẽ phát sinh nếu phải chia sẻ type qua boundary.
10. `resolveClass` có chạy `static{}` không? **Không**, nó link chứ không initialize.
11. Vì sao `ClassNotFoundException` và `LinkageError` cần xử lý khác? **Một cái có thể là lookup miss, cái kia thường là vấn đề verification/binary identity/lỗi trong liên kết.**
12. Đóng `URLClassLoader` trong lúc worker đang nạp class có an toàn mặc định không? **Không**, phải phối hợp shutdown.
13. Test có barrier buộc hai threads cùng thấy null giúp gì? **Tái hiện TOCTOU, thay vì phụ thuộc xác suất scheduler.**

## 14. Tài liệu chuẩn

- [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock`, `registerAsParallelCapable`; implementation mặc định đồng bộ trên class-loading lock.
- [ClassLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): hợp đồng parallel loading và locking được duy trì trên JDK mới.
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defining/initiating loader, runtime type identity, loading constraints.
- [JVMS §5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4): verification, preparation, resolution.
- [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): initialization được phối hợp giữa threads, khác với duplicate class definition.
- [CyclicBarrier — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html) và [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): công cụ ép interleaving trong test concurrency.

**Kết luận:** `findLoadedClass` chỉ **quan sát trạng thái**, `defineClass` **thay đổi trạng thái**. Hai bước phải nằm trong cùng cơ chế **locking + recheck** cho từng tên class. Cách an toàn nhất thường là giữ `loadClass` mặc định và chỉ override `findClass`; nếu bắt buộc tự override, dùng `getClassLoadingLock(name)` cho **toàn bộ** check/delegation/define/resolve và kiểm tra `registerAsParallelCapable` đúng điều kiện. 
