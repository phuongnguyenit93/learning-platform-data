# Parallel-capable ClassLoader là gì? Nạp lớp đồng thời và khóa theo tên lớp trong Java

## 1. Khái niệm

**Parallel-capable class loader** là một `ClassLoader` được **đăng ký có khả năng hỗ trợ nạp các lớp khác tên một cách đồng thời**. Khi sử dụng triển khai `ClassLoader.loadClass(String, boolean)` mặc định, cơ chế khóa của nó được thu hẹp từ **toàn bộ đối tượng loader** xuống **mỗi binary name đang được tải**.

Nói ngắn gọn:

- **Loader thông thường (không parallel-capable):** hai thread yêu cầu *hai class khác nhau* qua **cùng loader** có thể phải chờ nhau vì cùng sử dụng khóa trên **đối tượng ClassLoader**.
- **Loader parallel-capable:** hai thread yêu cầu *hai tên class khác nhau* qua **cùng loader** có thể đi vào đường nạp đồng thời nhờ **khóa riêng theo tên**. Nếu cùng tên class, chúng vẫn được phối hợp để tránh định nghĩa trùng.
- **Đăng ký không tự làm mọi logic thread-safe:** người viết loader vẫn phải bảo vệ trạng thái mutable, cache, stream, package definition, xử lý classpath và bất kỳ lệnh override `loadClass` nào.
- **Không phải “nạp một class bằng nhiều thread”:** parallel-capable chủ yếu nhằm cho phép **nhiều class khác nhau** được nạp song song, vẫn bảo vệ yêu cầu nạp cùng binary name.

Cơ chế này xuất hiện từ **Java 7** nhằm giảm tình trạng deadlock ở hệ có nhiều class loaders và hỗ trợ nạp đồng thời an toàn hơn.

### Bài học trong module ClassLoader

Mục này thuộc nhóm **Nạp đồng thời**. Điều cần hiểu không chỉ là cách gọi `registerAsParallelCapable()`, mà còn là **khóa thực sự nằm ở đâu**, **vì sao thiết kế loader ảnh hưởng deadlock**, **cách đăng ký hợp lệ**, và **khi nào đăng ký vẫn không đủ**.

## 2. Vì sao ClassLoader cần khóa khi nạp lớp?

Giả sử hai thread đồng thời gọi:

```java
// Trích đoạn: loader là một ClassLoader do ứng dụng quản lý.
Class<?> first = loader.loadClass("plugin.Service");
Class<?> second = loader.loadClass("plugin.Service");
```

Nếu không phối hợp, cả hai có thể cùng thấy class chưa được nạp, đọc cùng file `plugin/Service.class`, rồi cùng gọi `defineClass("plugin.Service", ...)` trên một defining loader. Điều này có thể gây **`LinkageError` vì định nghĩa trùng**.

Triển khai `ClassLoader.loadClass(name, resolve)` mặc định dùng thứ tự:

1. `findLoadedClass(name)`: class đã được ghi nhận chưa?
2. `parent.loadClass(name)` (hoặc bootstrap nếu parent là `null`): hỏi loader cha.
3. `findClass(name)`: loader hiện tại tự tìm và định nghĩa khi parent không tìm thấy.
4. `resolveClass(c)` nếu tham số `resolve` là `true`.

Toàn bộ chuỗi mặc định được đồng bộ trên **`getClassLoadingLock(name)`**. Đây là điểm mấu chốt của parallel-capable: **đối tượng khóa do phương thức này trả về phụ thuộc trạng thái đăng ký của loader**.

Đừng đánh đồng `loadClass` với initialization (`<clinit>`). Một loader có thể nạp hoặc link class mà chưa yêu cầu chạy static initializer. Những khóa dùng cho class initialization của JVM không phải đơn giản là chính khóa do `getClassLoadingLock` trả về.

## 3. Không parallel-capable và parallel-capable khác nhau ở khóa nào?

Theo hợp đồng `ClassLoader.getClassLoadingLock(String)`:

- Nếu **loader không đăng ký parallel-capable**, phương thức **trả về `this`** — đối tượng loader hiện tại.
- Nếu **loader đã đăng ký parallel-capable**, phương thức trả về **một đối tượng khóa riêng gắn với binary name** được yêu cầu.
- Cùng loader, **cùng tên** thì nhận lại cùng khóa thích hợp; các tên khác nhau có thể có khóa khác nhau.
- Khi loader parallel-capable, truyền `null` cho `getClassLoadingLock` sẽ dẫn đến `NullPointerException` theo hợp đồng API. Với tên lớp hợp lệ, luôn truyền binary name không null.

### Hình dung sự khác nhau

```text
Không parallel-capable: một khóa L cho cả loader
-------------------------------------------------
Thread T1: loadClass("plugin.A")
             └── giữ khóa L ─────────────────┐
Thread T2: loadClass("plugin.B")              │
             └── cần cùng khóa L → chờ ◀─────┘


Parallel-capable: khóa theo từng binary name
---------------------------------------------
Thread T1: loadClass("plugin.A")
             └── giữ khóa K_A ───▶ nạp A
Thread T2: loadClass("plugin.B")
             └── giữ khóa K_B ───▶ nạp B
             (K_A và K_B khác nhau; có thể chạy đồng thời)

Thread T3: loadClass("plugin.A")
             └── cần K_A → chờ T1 rồi dùng kết quả đã nạp
```

**Lợi ích:** giảm khóa quá rộng khi nhiều request nạp các class độc lập. Khi loader tìm class trong JAR hoặc directory, phần I/O/tìm kiếm của những class khác tên có cơ hội tiến hành đồng thời.

**Giới hạn:** class A và B có thể phụ thuộc nhau hoặc loader có tài nguyên nội bộ dùng chung; một phần công việc vẫn có thể phải tuần tự hóa. Việc đăng ký không cam kết tốc độ luôn tăng và **không cam kết không bao giờ deadlock**.

## 4. Các API liên quan

| API | Vai trò | Điều cần nhớ |
|---|---|---|
| `ClassLoader.registerAsParallelCapable()` | Đăng ký **class của loader** là parallel-capable | `protected static`; gọi từ initializer của subclass |
| `loader.isRegisteredAsParallelCapable()` | Hỏi instance loader đã có đăng ký hay chưa | `public final`, từ Java 9 |
| `getClassLoadingLock(String name)` | Lấy khóa dùng khi nạp binary name | `protected`; mặc định trả `this` hoặc khóa theo tên |
| `loadClass(String name)` | Đường vào công khai khi yêu cầu class | Mặc định gọi protected `loadClass(name, false)` |
| `loadClass(String name, boolean resolve)` | Thuật toán tra loaded → parent → findClass → resolve | Mặc định đồng bộ trên khóa do `getClassLoadingLock` trả |
| `findLoadedClass(String name)` | Kiểm tra tên đã được JVM ghi nhận với initiating loader | Tránh định nghĩa lại class cũ |
| `findClass(String name)` | Hook custom loader tự tìm và định nghĩa class | Nên override phương thức này khi có thể |
| `defineClass(...)` | Giao bytes cho JVM định nghĩa runtime class | Không được gọi trùng cho cùng tên/defining loader |

`getClassLoadingLock` là phương thức có thể được subclass override nếu cần chính sách khóa đặc biệt. Tuy nhiên, với loader đơn giản, nên **để nguyên cơ chế chuẩn** và chỉ override `findClass`. Override khóa tùy tiện có thể làm mất những bảo đảm vốn có và khó chứng minh đúng ở nhiều thread.

## 5. Đăng ký parallel-capable
Subclass muốn song song phải gọi `registerAsParallelCapable()` từ static initializer của **chính lớp ấy**, khi chưa có instance và mọi superclass loader đã được đăng ký. Giá trị `false` cho biết không đủ điều kiện; nếu ứng dụng phụ thuộc vào parallel loading, báo lỗi sớm. Registration là theo **loader class**, không phải thiết lập trên từng object, và không thể hủy sau khi thành công.
```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError("Parallel registration failed");
    }
}
```
Ví dụ `ParallelLockDemo` và `ParallelDirectoryDemo` sau đây sử dụng chính quy tắc này. Đối với hierarchy nhiều cấp, caller và điều kiện đăng ký muộn, xem bài **registerAsParallelCapable và điều kiện đăng ký**; tại đây mục tiêu là hiểu lợi ích cùng giới hạn của **nạp nhiều tên class đồng thời**.

## 6. Ví dụ Java 17+ số 1: xem chính xác khóa theo tên

Tạo file `ParallelLockDemo.java`:

```java
public final class ParallelLockDemo {
    static class PlainLoader extends ClassLoader {
        PlainLoader() {
            super(ParallelLockDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Could not register ParallelLoader"
                );
            }
        }

        ParallelLoader() {
            super(ParallelLockDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    public static void main(String[] args) {
        PlainLoader plain = new PlainLoader();
        ParallelLoader parallel = new ParallelLoader();

        System.out.println("plain registered: "
                + plain.isRegisteredAsParallelCapable());
        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());

        System.out.println("plain A lock == B lock: "
                + (plain.lockFor("demo.A") == plain.lockFor("demo.B")));
        System.out.println("plain A lock == loader: "
                + (plain.lockFor("demo.A") == plain));

        System.out.println("parallel A lock == B lock: "
                + (parallel.lockFor("demo.A")
                   == parallel.lockFor("demo.B")));
        System.out.println("parallel A lock == A lock: "
                + (parallel.lockFor("demo.A")
                   == parallel.lockFor("demo.A")));
        System.out.println("parallel A lock == loader: "
                + (parallel.lockFor("demo.A") == parallel));
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac ParallelLockDemo.java
java ParallelLockDemo
```

Stdout:

```text
plain registered: false
parallel registered: true
plain A lock == B lock: true
plain A lock == loader: true
parallel A lock == B lock: false
parallel A lock == A lock: true
parallel A lock == loader: false
```

**Giải thích từng kết quả:**

- `PlainLoader` không gọi `registerAsParallelCapable`. Dù superclass `ClassLoader` đã đăng ký, **chính PlainLoader chưa đăng ký**, nên `getClassLoadingLock` trả đối tượng `plain` cho cả `demo.A` lẫn `demo.B`.
- `ParallelLoader` đăng ký thành công trong static initializer. Mỗi binary name có khóa riêng, nên khóa `demo.A` khác `demo.B`.
- Hai lần hỏi **cùng tên** `demo.A` nhận lại khóa tương ứng, giúp các thread yêu cầu cùng class không định nghĩa trùng.
- Khóa của `demo.A` trong loader parallel-capable không phải đối tượng loader, nên một thread `synchronized(parallel)` không phải chính cơ chế khóa theo tên do triển khai mặc định sử dụng.

Đây là **ví dụ xác minh hợp đồng locking**, không phải benchmark tốc độ. Nó cố ý không tạo thread, vì muốn chứng minh **nguyên nhân cho phép nạp song song** một cách không phụ thuộc scheduler.

## 7. Ví dụ Java 17+ số 2: nạp hai class qua loader parallel-capable

Ở ví dụ trước, ta chỉ quan sát khóa. Ví dụ này nạp bytecode thật từ directory qua hai thread, bảo toàn parent-first mặc định và giữ phần `findClass` đơn giản.

### 7.1. Chuẩn bị class plugin

Trong một thư mục làm việc trống, tạo `A.java`:

```java
package plugin;

public final class A {
    public static String id() {
        return "A";
    }
}
```

Tạo `B.java`:

```java
package plugin;

public final class B {
    public static String id() {
        return "B";
    }
}
```

### 7.2. Tạo ParallelDirectoryDemo.java

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class ParallelDirectoryDemo {
    static final class DirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "DirectoryLoader registration failed"
                );
            }
        }

        private final Path root;
        private final AtomicInteger definitions = new AtomicInteger();

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            );

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }

            Class<?> defined =
                    defineClass(name, bytes, 0, bytes.length);
            definitions.incrementAndGet();
            return defined;
        }

        int definitions() {
            return definitions.get();
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader = new DirectoryLoader(
                Path.of("plugin-classes"),
                ParallelDirectoryDemo.class.getClassLoader()
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> left =
                    pool.submit(() -> loader.loadClass("plugin.A"));
            Future<Class<?>> right =
                    pool.submit(() -> loader.loadClass("plugin.B"));

            Class<?> a = left.get();
            Class<?> b = right.get();

            System.out.println("parallel capable: "
                    + loader.isRegisteredAsParallelCapable());
            System.out.println("A from child: "
                    + (a.getClassLoader() == loader));
            System.out.println("B from child: "
                    + (b.getClassLoader() == loader));
            System.out.println("definitions: "
                    + loader.definitions());
            System.out.println("A reused: "
                    + (loader.loadClass("plugin.A") == a));
        } finally {
            pool.shutdown();
        }
    }
}
```

### 7.3. Biên dịch và chạy

Tạo output directory. Trên Bash:

```bash
mkdir -p plugin-classes
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Sau đó:

```bash
javac --release 17 -d plugin-classes A.java B.java
javac --release 17 ParallelDirectoryDemo.java
java -cp . ParallelDirectoryDemo
```

Cấu trúc đầu ra:

```text
working-directory/
├── A.java
├── B.java
├── ParallelDirectoryDemo.java
├── ParallelDirectoryDemo.class
├── ParallelDirectoryDemo$DirectoryLoader.class
└── plugin-classes/
    └── plugin/
        ├── A.class
        └── B.class
```

**Không thêm `plugin-classes` vào `-cp`** của chương trình host. Nếu parent (application loader) cũng thấy `plugin.A` hoặc `plugin.B`, nó có thể nạp class đó trước; `findClass` của custom loader sẽ không được gọi cho tên đó, khiến `definitions` không phản ánh ví dụ mong muốn.

Stdout với đúng cấu trúc trên:

```text
parallel capable: true
A from child: true
B from child: true
definitions: 2
A reused: true
```

### 7.4. Ý nghĩa và giới hạn của ví dụ

Hai tác vụ `Future` yêu cầu **hai binary names khác nhau** trên **cùng DirectoryLoader instance**. Loader đã đăng ký parallel-capable và kế thừa `ClassLoader.loadClass` mặc định, nên đường nạp sử dụng khóa theo tên.

- Mỗi class được định nghĩa đúng một lần trong ví dụ.
- `AtomicInteger` làm bộ đếm `definitions` an toàn khi hai thread có thể tăng cùng lúc.
- `findClass` chỉ dùng dữ liệu `root` bất biến và biến byte array cục bộ của từng lời gọi, không dùng một `InputStream` chia sẻ thiếu khóa.
- `loadClass("plugin.A")` lại sau đó dùng trạng thái đã nạp, trả cùng đối tượng `Class<?>`.
- Thứ tự thực tế T1/T2 chạy I/O có thể khác theo scheduler. **Stdout không đo hay chứng minh hai thao tác `Files.readAllBytes` đã thực sự chồng thời gian.** Nó xác nhận loader được đăng ký, kết quả nạp thành công và giữ đúng danh tính kiểu.

Ví dụ này **không chạy các static initializers của A/B** chỉ vì dùng `loadClass`. Chúng không có static initializer quan sát được; nếu thêm `static { ... }`, hãy nhớ initialization là một giai đoạn riêng.

## 8. Tại sao vẫn phải bảo vệ cùng binary name?

Giả sử cả hai thread đều gọi:

```java
loader.loadClass("plugin.A");
```

Với loader parallel-capable mặc định, cả hai sẽ cần **cùng khóa dành cho `plugin.A`**. Một thread vào, kiểm tra `findLoadedClass`, tìm/định nghĩa A nếu cần; thread còn lại chờ, sau đó kiểm tra lại và lấy class đã được ghi nhận. Điều đó tránh hai đường cùng `defineClass` cho **cùng loader + cùng binary name**.

Sơ đồ:

```text
Thread T1                            Thread T2
---------                            ---------
loadClass("plugin.A")                loadClass("plugin.A")
lock K_A                              chờ lock K_A
findLoadedClass → null               ...
parent không tìm thấy                 ...
findClass → defineClass A             ...
unlock K_A                            nhận lock K_A
                                     findLoadedClass → A
                                     return A
```

**Parallel-capable không bỏ đồng bộ**; nó chỉ **thay độ hạt của đồng bộ**. Cơ chế này vẫn cần chính sách khóa đúng với tên class.

Nếu tự override `loadClass` mà bỏ qua `findLoadedClass` và `getClassLoadingLock`, một custom loader có thể thử định nghĩa cùng tên nhiều lần và gặp `LinkageError`. Đăng ký parallel-capable không sửa hộ một `loadClass` sai.

## 9. Vì sao ClassLoader là parallel-capable nhưng subclass có thể không?

Một sai lầm phổ biến là nghĩ:

> “`ClassLoader` vốn parallel-capable; tất cả class `extends ClassLoader` chắc cũng parallel-capable.”

Điều này **sai**. Từng class trong chuỗi subclass cần được đăng ký nếu muốn khả năng đó.

Ví dụ cây kế thừa:

```text
ClassLoader                         [registered]
   │
   ▼
MyBaseLoader                        [registered]
   ├── MyChildA                      [chưa đăng ký]
   │       └── MyGrandchildA         [không thể đăng ký thành công
   │                                   khi superclass chưa đăng ký]
   └── MyChildB                      [registered]
           └── MyGrandchildB         [phải đăng ký riêng nếu muốn]
```

### Ví dụ Java 17+ kiểm tra đăng ký thất bại

Tạo file `RegistrationChainDemo.java`:

```java
public final class RegistrationChainDemo {
    static class LegacyBase extends ClassLoader {
        // Không registerAsParallelCapable().
    }

    static class CannotRegisterChild extends LegacyBase {
        static final boolean REGISTERED =
                registerAsParallelCapable();
    }

    static class GoodBase extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "GoodBase registration failed"
                );
            }
        }
    }

    static class GoodChild extends GoodBase {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "GoodChild registration failed"
                );
            }
        }
    }

    public static void main(String[] args) {
        LegacyBase legacy = new LegacyBase();
        CannotRegisterChild rejected = new CannotRegisterChild();
        GoodChild accepted = new GoodChild();

        System.out.println("legacy: "
                + legacy.isRegisteredAsParallelCapable());
        System.out.println("registration attempt: "
                + CannotRegisterChild.REGISTERED);
        System.out.println("rejected child: "
                + rejected.isRegisteredAsParallelCapable());
        System.out.println("accepted child: "
                + accepted.isRegisteredAsParallelCapable());
    }
}
```

Chạy:

```bash
javac RegistrationChainDemo.java
java RegistrationChainDemo
```

Stdout:

```text
legacy: false
registration attempt: false
rejected child: false
accepted child: true
```

`CannotRegisterChild` đăng ký thất bại vì superclass `LegacyBase` không đăng ký; không có “kế thừa tự động” trạng thái đăng ký từ grandparent `ClassLoader`. Ngược lại, cả `GoodBase` và `GoodChild` đều tự đăng ký trong initializer của chính chúng nên chuỗi hợp lệ.

Đoạn `if (!registerAsParallelCapable()) throw ...` trong các loader production giúp phát hiện sớm giả định sai về hierarchy; không nên lờ đi giá trị `false` rồi tuyên bố loader đã hỗ trợ song song.

## 10. Deadlock khi đường ủy quyền không theo cây
Nếu hai loader có thể gọi sang nhau khi đang giữ các loading locks, hai thread có thể tạo vòng chờ A → B → A. Lock theo tên giảm tắc nghẽn do **các tên khác nhau trên cùng loader**, nhưng vòng chờ giữa những per-name locks cụ thể vẫn có thể xảy ra. Vì vậy loader parallel-capable cần một delegation graph có route kết thúc và lock ordering đúng. Bài **Deadlock khi nhiều loader ủy quyền chéo** chứa thí nghiệm chạy được và quy trình lấy thread dump; không xem `registerAsParallelCapable` là biện pháp sửa vòng phụ thuộc.

## 11. Phân biệt deadlock loading với deadlock initialization

Đây là hai lớp vấn đề khác nhau:

| Phạm vi | Khóa/đồng bộ | Dấu hiệu |
|---|---|---|
| Class loading | `getClassLoadingLock(name)` và khóa custom loader nếu có | Thread chờ khi gọi `loadClass`/`findClass` |
| Class initialization | Đồng bộ initialization do JVM quản lý cho từng runtime class/interface | Thread chờ trong/qua `<clinit>` hoặc code liên quan |
| Lock ứng dụng | `synchronized`, `ReentrantLock`, `Future.get`, `Thread.join`... | Thread chờ nhau do logic ứng dụng |

Nếu thread T1 đang initialize A và cần B, trong khi thread T2 đang initialize B và cần A, deadlock có thể xuất hiện **ngay cả khi ClassLoader đã parallel-capable**. Không “sửa” một vòng static initialization bằng cách chỉ thêm `registerAsParallelCapable`.

Mặt khác, một vòng yêu cầu initialization cùng thread A → B → A có thể đọc static fields chưa được gán, không nhất thiết deadlock. Muốn phân biệt, xem stack traces, các `<clinit>` và đường gọi `loadClass` của từng thread.

**Không dùng `ThreadMXBean.findDeadlockedThreads()` làm phép thử duy nhất**: API đó không bảo đảm phát hiện mọi vòng chờ nội bộ khi JVM điều phối class loading/initialization. Cần thread dump và thông tin class loader cụ thể.

## 12. Trường hợp override loadClass: đừng bỏ mất locking

Khi chỉ override `findClass`, ta dùng được khóa theo tên của triển khai mặc định. Nhưng một số loader muốn **child-first** cho vài package, nên phải override `loadClass`.

Mẫu ở đây là **pseudocode định hướng**, không phải một class Java độc lập và **không** phải cách duy nhất để triển khai loader tùy chỉnh:

```java
// PSEUDOCODE — cần handling parent==null, policy package,
// loader/module constraints và exception rõ ràng.
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> loaded = findLoadedClass(name);
        if (loaded == null) {
            if (isChildFirstNamespace(name)) {
                try {
                    loaded = findClass(name);
                } catch (ClassNotFoundException ignored) {
                    loaded = getParent().loadClass(name);
                }
            } else {
                try {
                    loaded = getParent().loadClass(name);
                } catch (ClassNotFoundException ignored) {
                    loaded = findClass(name);
                }
            }
        }
        if (resolve) {
            resolveClass(loaded);
        }
        return loaded;
    }
}
```

**Cảnh báo bắt buộc:** đoạn này dùng `getParent().loadClass`, nên không xử lý parent `null`; nó không có namespace whitelist/blacklist hoặc module/package checks đầy đủ. **Không copy như implementation production**. Dùng nó để thấy rằng khi override `loadClass` phải giữ **`synchronized(getClassLoadingLock(name))` + `findLoadedClass` + định nghĩa class một lần** theo từng tên.

Khi thiết kế child-first:
- Không cố child-first cho `java.*` hay các platform classes.
- Xác định package nào là API dùng chung phải do parent định nghĩa để tránh hai runtime types cùng tên.
- Không catch mọi `LinkageError` từ parent rồi giả vờ “không tìm thấy” để fallback sang child.
- Kiểm tra vòng lặp delegation trong hệ nhiều loaders.
- Bảo đảm hai yêu cầu cùng tên không đồng thời gọi `defineClass`.
- Không đặt `synchronized(this)` quanh toàn bộ `loadClass` nếu mục tiêu là parallel-capable; khóa này lại tuần tự hóa mọi tên.

### Tại sao synchronized(this) có thể vô hiệu hóa lợi ích?

```java
// ANTI-PATTERN — chỉ minh họa:
@Override
public synchronized Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return super.loadClass(name);
}
```

Một loader dù đã đăng ký parallel-capable vẫn phải lấy **monitor của toàn bộ instance** khi vào method trên; các request khác tên bị tuần tự hóa ngay từ cửa. Đừng dùng `synchronized` trên cả loader chỉ vì “sợ race”, rồi kỳ vọng parallel loading có hiệu quả.

Nếu phải bảo vệ cấu trúc dữ liệu chung, hãy dùng khóa riêng cho dữ liệu đó hoặc concurrent collections; tránh giữ khóa toàn cục trong những thao tác I/O hoặc delegation có thể gọi loader khác.

## 13. Thread-safety của findClass: đăng ký chỉ là lời cam kết

Đăng ký thành công có ý nghĩa rằng **các lời gọi nạp class khác nhau có thể đồng thời tiến vào code loader**. Vì vậy `findClass` phải sẵn sàng cho đồng thời.

### Những phần dễ có race condition

- Một `HashMap<String, byte[]>` mutable được đọc/ghi từ nhiều thread mà không có đồng bộ.
- Dùng **một InputStream hoặc ZipInputStream chia sẻ** và để các thread đọc class entries đồng thời.
- Dùng biến instance kiểu `String currentClassName` hoặc `byte[] scratchBuffer` làm bộ nhớ tạm chung cho mọi yêu cầu nạp.
- Hai thread đồng thời cố định nghĩa cùng package hoặc cập nhật một registry package/certificate không đúng quy tắc.
- Cập nhật classpath/URL list trong lúc nạp mà không có chính sách đồng bộ rõ.
- Giữ một monitor rồi gọi loader khác, mở ra chu trình khóa.
- Không quản lý vòng đời đóng JAR/URLClassLoader khi nhiều thread còn nạp class từ nguồn đó.

Ví dụ `DirectoryLoader` ở mục 7 dùng `Path root` bất biến, `byte[]` cục bộ và `AtomicInteger`. Thiết kế đó nhỏ và an toàn hơn việc chia sẻ một byte array để tiết kiệm allocation bằng cách không có khóa.

### Một cache phù hợp

```java
// Trích đoạn trong custom loader:
private final java.util.concurrent.ConcurrentMap<String, byte[]>
        bytesCache = new java.util.concurrent.ConcurrentHashMap<>();
```

`ConcurrentHashMap` có thể bảo vệ map khỏi race, nhưng **không thay thế khóa của việc định nghĩa class**. Nếu loader override `loadClass` sai và hai thread vẫn cùng `defineClass` một binary name, cache bytecode an toàn cũng không cứu được.

Cũng cần thiết kế lifecycle cache: một cache giữ class loader, `Class<?>` hoặc object plugin lâu hơn cần thiết có thể cản trở class unloading khi redeploy.

## 14. Cùng tên, nhiều defining loaders: phân biệt với song song

Hai thread nạp cùng binary name thông qua **hai loader khác nhau** không nhất thiết tạo ra cùng runtime class:

```text
Thread T1 → Loader-A.loadClass("plugin.Service")
Thread T2 → Loader-B.loadClass("plugin.Service")

Nếu Loader-A và Loader-B tự định nghĩa:
  ("plugin.Service", Loader-A) ≠ ("plugin.Service", Loader-B)
```

Đây là vấn đề **type identity**, không phải bản chất parallel-capable. Khóa theo tên thường **thuộc từng instance loader**, không phải một khóa global chung trên toàn JVM cho mọi loader có cùng binary name.

Ngược lại, một loader con có thể ủy quyền cho parent và nhận lại class do parent định nghĩa; lúc đó defining loader khác initiating loader. Khi kiểm tra:

```java
Class<?> result = loader.loadClass("plugin.Service");
System.out.println(result.getClassLoader());
```

Đây là **trích đoạn**; kết quả `getClassLoader()` cho biết defining loader của runtime class (với bootstrap thường biểu diễn bằng `null`). Không suy diễn từ thread đã gọi loader nào rằng loader đó chắc chắn đã định nghĩa class.

## 15. Parallel-capable có tự tăng hiệu năng không?

Không có bảo đảm. Nó **mở khả năng** chứ không phải lời cam kết tăng tốc ở mọi workload.

Hiệu quả phụ thuộc vào:

1. **Số lượng tên class khác nhau đang được yêu cầu đồng thời.**
2. **Chi phí thực tế của việc tìm và định nghĩa class**: đọc JAR qua file system/network, verify/link, caching.
3. **Mức phụ thuộc giữa các class**: một class có thể cần class khác, dẫn đến chờ.
4. **Tính thread-safe của storage/resource loader**: vẫn có thể có khóa ở Zip/JAR reader, data store hoặc network client.
5. **Parent delegation và module graph**: class được parent trả ngay có thể không đi vào `findClass` của child.
6. **Độ hạt khóa bổ sung** do ứng dụng đặt; `synchronized(this)` và cache lock dài hạn có thể vô hiệu hóa lợi ích.
7. **JVM/OS scheduling và I/O contention**: nhiều thread không chắc nhanh hơn một thread trong môi trường I/O giới hạn.

Không benchmark chỉ bằng việc so hai dòng `System.currentTimeMillis()` trong một lần run. Nên dùng nhiều iteration, warm-up, class names khác nhau hợp lệ, quan sát throughput/latency và thread dumps. Một loader đã nạp tất cả class từ trước thường khiến benchmark chủ yếu đo cache hit `findLoadedClass` chứ không còn đo concurrent class definition.

## 16. Cách debug deadlock/race trong class loading

### Bước 1: xác định loader và trạng thái đăng ký

```java
// Trích đoạn khi đã có một ClassLoader loader:
System.out.println(loader.getClass().getName());
System.out.println(loader.isRegisteredAsParallelCapable());
System.out.println(loader.getParent());
```

`isRegisteredAsParallelCapable()` có từ Java 9; ví dụ ở bài này nhắm Java 17+.

### Bước 2: xác định các tên class cạnh tranh

Log binary name, thread name và ID loader ngay **trước/sau** các điểm:

- `loadClass(name)`
- `findClass(name)`
- `defineClass(name, bytes, ...)`
- Các lời gọi delegation giữa loaders
- Khóa custom và I/O source

Không log mỗi URL có query string chứa credential hoặc đường dẫn nhạy cảm trong hệ production.

### Bước 3: xem thread dump

Trên HotSpot/JDK có công cụ tương ứng:

```bash
jcmd <pid> Thread.print -l
```

`<pid>` là **placeholder cho process ID thật**, không phải chuỗi cần nhập nguyên văn. Tìm thread đang chờ trong `ClassLoader.loadClass`, `getClassLoadingLock`, `findClass`, static initializer hoặc code plugin. Đối chiếu hai thread có đang giữ lock trên cùng loader instance hoặc những per-name locks hay không.

### Bước 4: kiểm tra đường override

Nếu class loader đăng ký parallel-capable nhưng hiệu năng vẫn tuần tự:

- Có override `loadClass` bằng `synchronized` trên cả instance không?
- Có dùng `synchronized(this)`/global lock trong `findClass` không?
- Có mọi thread chờ một `ZipFile`/cache lock duy nhất không?
- Có khóa trước khi gọi loader khác khiến vòng delegation deadlock không?
- Có class initialization/`<clinit>` chờ thread khác khiến tưởng là lỗi class loading không?

### Bước 5: tái hiện và sửa đúng nguyên nhân

- Dùng test nhiều thread với hai nhóm: **nhiều tên khác nhau** và **cùng một tên**.
- Kiểm tra mọi tên được định nghĩa **tối đa một lần trên mỗi defining loader**.
- Sử dụng `CountDownLatch` hoặc `CyclicBarrier` ở test để kiểm soát thời điểm bắt đầu, không dựa vào `Thread.sleep()` tùy tiện.
- Nếu có race do cache/shared resources, sửa đồng bộ hoặc dữ liệu; không chỉ bật registration.
- Nếu có vòng chờ do các loader ủy quyền chéo, đơn giản hóa dependency graph; per-name locking chỉ giảm một lớp rủi ro.

## 17. Một bài tập thử nghiệm đồng thời (không ép stdout cố định)

Có thể mở rộng `DirectoryLoader` ở mục 7 bằng bộ đếm thời điểm vào `findClass` cho hai tên khác nhau:

```java
// Trích đoạn ý tưởng test, không phải file chạy độc lập:
CountDownLatch firstTwoEntered = new CountDownLatch(2);

@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    firstTwoEntered.countDown();
    // Sau đó test cho phép hai thread tiếp tục bằng latch khác
    // trước khi đọc bytes và defineClass.
    ...
}
```

Để kiểm chứng đồng thời:
1. Dùng **một loader instance** và hai thread gọi `loadClass` cho **hai binary names khác nhau**.
2. Chặn cả hai ở đầu `findClass` trên một latch khác; thread chính kiểm tra cả hai đã vào.
3. Lặp lại với loader **không đăng ký**. Với đường `loadClass` mặc định, một thread có thể không vào `findClass` trước khi thread thứ nhất nhả khóa toàn loader.
4. Dùng timeout và giải phóng latch trong `finally` để không làm test treo vĩnh viễn.
5. Không gán stdout hoặc thời gian chờ tuyệt đối cố định; scheduler và machine load khác nhau.

Mục này mô tả phương pháp kiểm thử. Các đoạn có `...` chỉ là **pseudocode**, không phải Java source có thể biên dịch trực tiếp. Hai demo runnable ở mục 6, 7 và ví dụ hierarchy ở mục 9 đã có code hoàn chỉnh, lệnh compile và stdout xác định.

## 18. Những nhầm lẫn phổ biến

| Nhầm lẫn | Sự thật |
|---|---|
| Kế thừa `ClassLoader` thì auto parallel-capable | Không; subclass cần tự đăng ký |
| Đăng ký bằng cách gọi method trong constructor | Sai thời điểm; phải trước khi tạo instance, thường static initializer |
| Chỉ class con đăng ký là đủ | Không; toàn bộ superclass chain liên quan cũng phải đăng ký |
| Parallel-capable nghĩa là nạp một class trên nhiều thread đồng thời | Khóa theo tên vẫn ngăn định nghĩa trùng cùng tên |
| Parallel-capable bỏ hết synchronized | Không; thay khóa toàn loader bằng khóa theo class name |
| Đăng ký làm `findClass` thread-safe tự động | Không; cache, I/O, trạng thái dùng chung vẫn cần bảo vệ |
| `synchronized(this)` quanh `loadClass` vẫn được song song | Nó tuần tự hóa mọi tên, làm giảm lợi ích |
| Chỉ cần parallel-capable là không deadlock | Vòng cùng tên, init và khóa riêng vẫn có thể deadlock |
| Nạp class song song là chạy `<clinit>` song song theo cách không kiểm soát | Loading và initialization có quy tắc riêng |
| Có hai loader nạp cùng tên thì chắc cùng class | Không; defining loader là một phần của runtime identity |
| Có `AtomicInteger` đếm class là đủ an toàn | Không; việc `defineClass` trùng và state khác vẫn cần đúng khóa |
| Loader đã nạp class xong thì sửa file và gọi lại sẽ nhận bản mới | Không; `findLoadedClass` có thể trả class cũ |
| Registration tự biến ClassLoader thành child-first | Không; delegation order không đổi |

## 19. Checklist thiết kế custom loader cho ứng dụng thực tế

**Trước khi triển khai:**

- Xác định cần **nạp nhiều class khác nhau đồng thời** hay chỉ load lần lượt.
- Kiểm tra mọi superclass loader hỗ trợ parallel-capable.
- Quyết định có thể chỉ override `findClass` hay thật sự phải override `loadClass`.
- Làm rõ parent/shared API, namespace riêng của plugin và loader lifecycle.

**Khi triển khai:**

- Đăng ký trong static initializer và xác nhận giá trị `true`.
- Giữ `loadClass` mặc định khi có thể; nó đã phối hợp khóa và caching.
- Chỉ dùng `defineClass` đúng một lần cho một binary name trong cùng defining loader.
- Dùng local variables và concurrent collections cho mutable shared state.
- Không giữ khóa toàn loader qua I/O hoặc delegation nếu không cần.
- Giữ đúng semantics `ClassNotFoundException` so với các `LinkageError` khi bytes hỏng.
- Không thay đổi parent-first ngầm; document rõ phần nào child-first nếu có.

**Khi kiểm thử:**

- Kiểm tra `isRegisteredAsParallelCapable()`.
- Kiểm tra cùng name → một runtime class; khác names → hai class được định nghĩa đúng.
- Kiểm tra race ở package definition, resources, cache, close/reload.
- Kiểm tra dependency chéo và class initialization.
- Dùng thread dump/structured logs để phân biệt loading lock với JVM initialization lock.

**Khi vận hành:**

- Không đóng `URLClassLoader` khi thread khác còn nạp từ nó; điều phối quiescence trước close.
- Dừng task, unregister callbacks và restore Thread Context ClassLoader khi ngừng plugin.
- Xem xét tình trạng classloader còn reachable sau redeploy, không giả định close dẫn đến unload.
- Theo dõi performance bằng workload thực thay vì chỉ nhìn trạng thái registered.

## 20. Câu hỏi tự kiểm tra

1. **Parallel-capable ClassLoader nghĩa là gì?** Loader được đăng ký để có thể nạp các binary names khác nhau đồng thời thông qua khóa theo tên của triển khai chuẩn.
2. **Non-parallel loader dùng khóa gì trong `loadClass` mặc định?** Chính đối tượng loader (`this`).
3. **Parallel loader dùng khóa gì?** Khóa riêng gắn với binary name được yêu cầu.
4. **Hai thread cùng yêu cầu `plugin.A` có cùng lúc được `defineClass` không?** Không theo triển khai đúng; cùng tên chia khóa/caching để tránh định nghĩa trùng.
5. **Đăng ký qua API nào?** `protected static ClassLoader.registerAsParallelCapable()` trong static initializer của subclass.
6. **Có bắt buộc các superclass cũng đăng ký không?** Có, trừ `Object` theo contract.
7. **`ClassLoader` đã đăng ký có làm `extends ClassLoader` tự đăng ký không?** Không.
8. **API nào hỏi một loader instance đã đăng ký chưa?** `isRegisteredAsParallelCapable()` (Java 9+).
9. **Vì sao nên override `findClass` thay vì `loadClass` khi chỉ cần nguồn bytecode mới?** Giữ thuật toán delegation, `findLoadedClass`, locking và `resolveClass` mặc định.
10. **`synchronized(this)` quanh toàn bộ loadClass ảnh hưởng gì?** Chặn nhiều class khác tên cùng lúc trên monitor của loader, làm mất lợi ích của per-name locks.
11. **Đăng ký có tự bảo vệ `HashMap` hoặc shared `InputStream` trong `findClass` không?** Không.
12. **Parallel-capable có ngăn deadlock của `<clinit>` không?** Không; class initialization là cơ chế đồng bộ khác.
13. **Hai defining loaders khác nhau tạo class cùng binary name có cùng runtime type không?** Không.
14. **Lý do chính tránh deadlock khi delegation chéo là gì?** Giảm các vòng chờ gây ra bởi khóa toàn bộ loader; vẫn cần thiết kế dependency và locking hợp lý.
15. **Có cần benchmark sau khi đăng ký không?** Có, nếu mục tiêu là performance; registration chỉ mở khả năng chứ không đảm bảo nhanh hơn.

## Tài liệu chuẩn

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `getClassLoadingLock` và `loadClass`; áp dụng cho toàn bộ ví dụ Java 17 trong bài.
- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): contract cập nhật của registration, locking, đồng bộ mặc định và loader hierarchy.
- [Oracle — Multithreaded Custom Class Loaders in Java](https://docs.oracle.com/javase/8/docs/technotes/guides/lang/cl-mt.html): hướng dẫn thiết kế custom class loader đa luồng, đăng ký parallel-capable và những cảnh báo khi override `loadClass`.
- [Java Virtual Machine Specification — §5.3 Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defining/initiating loaders và runtime class identity.
- [Java Language Specification — §§12.2 Loading, 12.3 Linking, 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): mối quan hệ giữa loading, linking và initialization.

**Kết luận:** **Parallel-capable** là năng lực đã đăng ký giúp một `ClassLoader` dùng **khóa theo tên class** thay vì khóa toàn bộ loader khi gọi `loadClass` mặc định. Nó vừa duy trì an toàn cho **cùng một binary name**, vừa cho phép **các tên khác nhau** có thể nạp đồng thời. Đăng ký đúng superclass chain là điều kiện cần; code `findClass` thread-safe, delegation không gây chu trình, và vòng đời tài nguyên đúng mới giúp hệ thống thực sự an toàn.
