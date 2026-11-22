# Java 7 — Nạp lớp an toàn: Nạp song song và registerAsParallelCapable

## 1. Mục tiêu bài học

Khi viết một `ClassLoader` tùy biến, bạn có thể phải xử lý **nhiều threads cùng yêu cầu tải lớp**. Một loader không thiết kế đúng có thể khiến việc nạp các lớp khác tên bị tuần tự hóa không cần thiết, rơi vào deadlock ở đồ thị delegation phức tạp, hoặc phát sinh race khi đọc bytecode/định nghĩa class. Java cung cấp cơ chế **parallel-capable class loader**, được đăng ký bằng `ClassLoader.registerAsParallelCapable()`, để giảm mức độ khóa từ **toàn bộ loader** xuống **khóa theo tên lớp** trong mặc định của `loadClass`.

Sau bài này, bạn có thể:

- Hiểu parent delegation và chu trình `loadClass → findLoadedClass → parent → findClass → defineClass`.
- Phân biệt **parallel capable** với “tất cả các lệnh trong custom loader đều thread-safe”.
- Biết **khi nào và ở đâu** gọi `registerAsParallelCapable()`.
- Hiểu hai điều kiện đăng ký: **chưa tạo instance của lớp caller** và **mọi lớp cha (trừ Object) đã đăng ký**.
- Quan sát trạng thái bằng `isRegisteredAsParallelCapable()` và khóa bằng `getClassLoadingLock(name)`.
- Phân biệt **hai tên lớp khác nhau được phép chạy song song** với **một tên lớp phải tránh định nghĩa lặp**.
- Viết subclass an toàn bằng cách **ưu tiên override `findClass`**, giữ mặc định `loadClass`.
- Kiểm soát state dùng chung, lỗi `ClassNotFoundException`/`LinkageError`, khóa, delegation cycles, class identity, kiểm thử và giám sát.
- Tách các bảo đảm về nạp lớp khỏi các vấn đề bảo mật như nạp bytecode không đáng tin.

Các API này xuất hiện từ Java 7 và **vẫn áp dụng trong Java 17+**. Phương thức `isRegisteredAsParallelCapable()` được bổ sung từ Java 9, nên toàn bộ ví dụ sử dụng Java 17+ để kiểm tra trạng thái dễ dàng.

**Thông điệp quan trọng:** Đăng ký parallel-capable **chỉ khai báo và kích hoạt cơ chế khóa phù hợp của ClassLoader mặc định**. Nó **không tự biến một `HashMap` mutable, bộ đệm bytecode, hệ thống plugin hay code trong `findClass` thành thread-safe**. Tác giả custom loader phải tự bảo đảm tính an toàn toàn bộ đường nạp lớp.

## 2. Vì sao nạp lớp cần đồng bộ?

Giả sử hai threads cùng gọi:

```java
Class<?> first = loader.loadClass("plugin.billing.Invoice");
Class<?> second = loader.loadClass("plugin.billing.Invoice");
```

Đây là snippet với `ClassLoader loader` đã được khai báo. Trong **cùng một loader**, một binary name cần được xử lý để nhiều yêu cầu không cùng chạy `defineClass` một cách đua nhau cho chính tên đó.

Một kịch bản không đồng bộ sai:

```text
Thread A                       Thread B
loadClass("plugin.Invoice")    loadClass("plugin.Invoice")
    |                              |
findLoadedClass -> null       findLoadedClass -> null
    |                              |
đọc bytecode                  đọc bytecode
    |                              |
defineClass("plugin.Invoice") defineClass("plugin.Invoice")
    |                              |
định nghĩa thành công         định nghĩa trùng -> LinkageError
```

Chỉ cần hai requests chạy đồng thời **cho cùng một tên lớp** đã xuất hiện nguy cơ định nghĩa trùng. Mặt khác, nếu Thread A yêu cầu `plugin.Invoice` còn Thread B yêu cầu `plugin.Report`, việc bắt cả hai chờ **một khóa toàn cục của loader** có thể làm giảm concurrency không cần thiết.

**Mục tiêu của khóa theo tên:** cùng tên → cùng khóa, được bảo vệ; khác tên → hai khóa khác nhau, có thể thực hiện song song. Điều này **không bảo đảm** hai công việc sẽ luôn chạy đồng thời vì scheduler, I/O, parent loader và state khác vẫn có thể gây tranh chấp.

## 3. ClassLoader và quy trình parent delegation

Ở mức khái niệm, mặc định `ClassLoader.loadClass(String,boolean)` thực hiện:

1. Lấy **khóa nạp lớp** qua `getClassLoadingLock(name)` và giữ khóa trong quá trình nạp.
2. Gọi `findLoadedClass(name)` để xem class đã được ghi nhận là loaded cho loader này chưa.
3. Nếu chưa, thử delegate tới **parent loader**.
4. Nếu parent không tìm được, gọi `findClass(name)` của subclass.
5. Nếu `resolve==true`, gọi `resolveClass(result)` để liên kết class.
6. Trả `Class<?>` hoặc ném `ClassNotFoundException` nếu không tìm được.

```text
loadClass("plugin.Service")
        |
        v
synchronized(getClassLoadingLock("plugin.Service"))
        |
        v
findLoadedClass("plugin.Service")
        |
        +-- found --------------------------> return Class
        |
        +-- not found
                |
                v
           parent.loadClass(...)
                |
                +-- found ------------------> return Class
                |
                +-- ClassNotFoundException
                        |
                        v
                   findClass(name)
                        |
                        +-- load bytes; defineClass(...)
                        +-- or ClassNotFoundException
```

Với lớp cha null, mặc định JVM cố nạp từ bootstrap loader trong giai đoạn delegation. **Không nên mặc định parent=null trong loader production**: nó có thể làm thiếu quyền truy cập các platform classes hoặc phá vỡ cấu trúc modules; demo bytecode bên dưới dùng null **có chủ đích** để tránh application parent lấy trước các lớp tự sinh.

### 3.1. Lý do override findClass trước

Javadoc chính thức Java SE 17 **khuyến nghị subclass override `findClass(String)` thay vì `loadClass(String,boolean)`** khi vẫn tuân thủ mô hình delegation thông thường. Vì:

- Mặc định `loadClass` đã có synchronized trên đúng khóa.
- Mặc định kiểm tra `findLoadedClass` trước khi thử định nghĩa.
- Mặc định delegate parent đúng thứ tự.
- Mặc định gọi `resolveClass` nếu yêu cầu resolve.
- Bạn chỉ cần cung cấp logic tìm/đọc class bytes và `defineClass`.

Nếu override `loadClass` theo kiểu child-first hoặc thay đổi lock, bạn phải tự giữ các bảo đảm này và kiểm thử mọi đường đua; đó là phạm vi nâng cao, không nên thực hiện chỉ để “bật tải song song”.

### 3.2. findLoadedClass không đồng nghĩa một Map do ứng dụng tự tạo

`findLoadedClass(name)` là API của ClassLoader/JVM kiểm tra class đã được ghi nhận cho loader. Không thể thay hoàn toàn bằng một `HashMap<String,Class<?>>` không đồng bộ rồi giả định mọi ràng buộc JVM về class identity và defining loader được bảo vệ.

### 3.3. defineClass và ClassNotFoundException

`findClass(String)` có thể đọc bytecode từ một nguồn do ứng dụng kiểm soát rồi gọi:

```java
return defineClass(binaryName, bytes, 0, bytes.length);
```

Đây là snippet **trong subclass ClassLoader** với `binaryName` và `bytes` hợp lệ. Sử dụng overload có tên binary rõ ràng. Nếu không tìm được class, ném `ClassNotFoundException(binaryName)`. Nếu bytecode sai, tên không khớp, vi phạm package/signing constraints hoặc định nghĩa trùng, có thể gặp `ClassFormatError`, `NoClassDefFoundError`, `SecurityException` hay các dạng `LinkageError` khác tùy nguyên nhân.

Không catch `LinkageError` rồi trả null như thể class chỉ không tồn tại. Lỗi định nghĩa/linkage không giống “not found” và có thể là dấu hiệu nghiêm trọng của custom loader.

## 4. Parallel-capable là gì?

Theo Java SE 17, một custom class loader hỗ trợ **nạp nhiều class khác nhau đồng thời** được gọi là *parallel capable*. Loại này **đăng ký chính lớp loader** với JVM bằng:

```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError(
                "ClassLoader registration failed");
    }
}
```

Đoạn trên là **static initializer đặt trong subclass của `ClassLoader`**, không phải code tự do gọi ở application main.

`registerAsParallelCapable()` là phương thức `protected static`. Việc đăng ký dùng **lớp caller** là subclass ClassLoader, không phải instance trong tay. Không có một cờ instance `loader.parallel=true` mà app có thể bật tùy lúc.

### 4.1. Vì sao static initializer là vị trí phù hợp?

Đăng ký phải diễn ra **trước khi có instance của lớp loader caller**. Static initializer chạy trong quá trình initialize class, trước khi tạo instance bằng constructor thông thường. Nó làm điều kiện “chưa tạo instance” rõ ràng, và nếu trả false có thể **fail fast** thay vì vận hành trong trạng thái không đúng như thiết kế.

Cố đăng ký **sau khi đã tạo các instances** là quá muộn theo hợp đồng API. Không viết một method `enableParallelLoading()` để gọi vào lúc server đang chạy rồi mong trạng thái tự chuyển.

### 4.2. Điều kiện thành công theo Javadoc

`registerAsParallelCapable()` trả `true` **nếu và chỉ nếu**:

1. **Chưa có instance nào của lớp caller được tạo**.
2. **Tất cả superclasses của caller (trừ `Object`) đã đăng ký parallel-capable**.

Phương thức trả `false` nếu không đáp ứng điều kiện. Một khi một loader class được đăng ký parallel-capable, **không có API hủy đăng ký**.

### 4.3. ClassLoader gốc đã đăng ký; subclasses thì chưa chắc

Javadoc Java 17 nói `java.lang.ClassLoader` **được đăng ký parallel-capable mặc định**. Nhưng mỗi subclass muốn hỗ trợ cần **tự đăng ký**; không được suy rằng:

```java
class MyLoader extends ClassLoader {}
```

tự động có khả năng parallel chỉ vì `ClassLoader` là parent. `isRegisteredAsParallelCapable()` trên một instance `MyLoader` ở trên sẽ là false trừ khi lớp đó đăng ký.

### 4.4. Một lớp cha không đăng ký chặn lớp con

Giả sử:

```java
class SerialBaseLoader extends ClassLoader {
    // Không đăng ký.
}

class AttemptParallelChild extends SerialBaseLoader {
    static final boolean REGISTERED = registerAsParallelCapable();
}
```

Đây là snippet; `AttemptParallelChild.REGISTERED` là false vì `SerialBaseLoader` không registered. **Lớp con không thể vượt qua chuỗi kế thừa bị ngắt** chỉ bằng cách gọi register.

Khi có nhiều tầng, mỗi lớp trung gian phải được thiết kế thread-safe và đăng ký, không chỉ lớp cuối.

### 4.5. Xác minh trạng thái bằng Java 17+

`isRegisteredAsParallelCapable()` là phương thức `public final boolean` của `ClassLoader` (từ Java 9). Nó cho phép kiểm tra trên instance:

```java
boolean capable = loader.isRegisteredAsParallelCapable();
```

Nhớ phân biệt “đã đăng ký thành công” với “thiết kế nội bộ thực sự thread-safe”. JVM không thể tự kiểm định mọi shared field của bạn chỉ vì method trả true.

## 5. getClassLoadingLock(String) và mức độ khóa

Mặc định `getClassLoadingLock(className)` trả:

- Nếu loader **không** registered parallel-capable: **chính object `this`** (khóa toàn loader).
- Nếu loader **đã** registered parallel-capable: **object khóa riêng gắn với binary name** đã yêu cầu. Hai lần gọi cùng name trả cùng monitor tương ứng; hai names khác nhau có thể dùng các monitor khác nhau.

```text
Chưa đăng ký:
  load(A) --\
  load(B) ----> synchronized(this) --> cùng một vùng khóa
  load(C) --/

Đã đăng ký:
  load(A) ----> lock("A")
  load(B) ----> lock("B")
  load(A) ----> lock("A")   // cùng tên A phải chờ nhau
```

**Đây là behavior của `getClassLoadingLock` mặc định.** Một subclass có thể override method này và thay đổi semantics; nếu làm vậy, phải đảm bảo synchronization và identity của lock phù hợp. Phần lớn code nên **giữ mặc định**.

### 5.1. Không hiểu khóa theo tên là “một class file có thể define hai lần”

Hai requests đồng thời nạp **cùng tên** qua **cùng loader instance** vẫn được tuần tự hóa trong mặc định của `loadClass`. Request thứ hai kiểm tra `findLoadedClass` sau khi request đầu xong và thường lấy chính `Class<?>` đã có, thay vì lại định nghĩa. Đó là bảo đảm thiết yếu của loader.

### 5.2. Không suy rằng hai loader khác instance chia sẻ cùng monitor

Khóa per-name thuộc **loader instance**, không phải một map toàn JVM theo binary name. Hai loader instances khác nhau có thể định nghĩa classes cùng binary name, tạo ra hai class identities khác nhau. Điều này là nền tảng của plugin isolation và cũng là nguồn của `ClassCastException` nếu trộn class giữa loaders.

### 5.3. Không dùng String.intern() làm khóa tùy tiện

Không tự triển khai “khóa tên lớp” bằng:

```java
synchronized (className.intern()) {
    // ...
}
```

Đây là **anti-pattern**, vì các `String` interned có thể vô tình dùng chung trên phạm vi rộng của JVM và tạo cross-component contention, thậm chí deadlock. Dùng `getClassLoadingLock(name)` của loader (hoặc tốt hơn, để mặc định `loadClass` quản lý).

### 5.4. Tránh khóa bao trùm quá rộng

Nếu trong `findClass` có:

```java
synchronized (this) {
    return loadOrDefine(name);
}
```

đây là **anti-pattern minh họa** nếu dùng trong loader parallel-capable: tất cả tên lại tranh một monitor toàn loader, triệt tiêu lợi ích khóa theo name. Nếu cần đồng bộ shared state, sử dụng cấu trúc dữ liệu concurrent hoặc khóa theo đúng resource, cố gắng tránh network/slow disk I/O trong critical section không cần thiết.

## 6. Chương trình Java 17+ hoàn chỉnh: đăng ký, khóa và kế thừa

**Tệp `ParallelRegistrationDemo.java`**

Ví dụ tạo bốn lớp loader:

- `LegacyLoader` không đăng ký.
- `BlockedChild` cố đăng ký nhưng parent `LegacyLoader` không hỗ trợ, nên thất bại.
- `ParallelLoader` trực tiếp extends ClassLoader và đăng ký thành công.
- `ParallelChild` extends ParallelLoader và tiếp tục đăng ký thành công.

Phương thức `lockFor` chỉ **phơi bày getClassLoadingLock để demo**, không override hay làm thay semantics của nó.

```java
public class ParallelRegistrationDemo {
    static class LegacyLoader extends ClassLoader {
        LegacyLoader() {
            super(ParallelRegistrationDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class BlockedChild extends LegacyLoader {
        static final boolean REGISTERED = registerAsParallelCapable();
    }

    static class ParallelLoader extends ClassLoader {
        static final boolean REGISTERED = registerAsParallelCapable();

        ParallelLoader() {
            super(ParallelRegistrationDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class ParallelChild extends ParallelLoader {
        static final boolean REGISTERED = registerAsParallelCapable();
    }

    public static void main(String[] args) {
        LegacyLoader legacy = new LegacyLoader();
        ParallelLoader parallel = new ParallelLoader();
        BlockedChild blocked = new BlockedChild();
        ParallelChild child = new ParallelChild();

        System.out.println("legacy registered = " +
                legacy.isRegisteredAsParallelCapable());
        System.out.println("parallel registration succeeded = " +
                ParallelLoader.REGISTERED);
        System.out.println("parallel registered = " +
                parallel.isRegisteredAsParallelCapable());
        System.out.println("legacy locks on loader = " +
                (legacy.lockFor("sample.A") == legacy));
        System.out.println("legacy shares locks for names = " +
                (legacy.lockFor("sample.A") ==
                 legacy.lockFor("sample.B")));
        System.out.println("parallel same name same lock = " +
                (parallel.lockFor("sample.A") ==
                 parallel.lockFor("sample.A")));
        System.out.println("parallel different names distinct locks = " +
                (parallel.lockFor("sample.A") !=
                 parallel.lockFor("sample.B")));
        System.out.println("blocked child registration = " +
                BlockedChild.REGISTERED);
        System.out.println("blocked child still serial = " +
                !blocked.isRegisteredAsParallelCapable());
        System.out.println("parallel child registration = " +
                ParallelChild.REGISTERED);
        System.out.println("parallel child registered = " +
                child.isRegisteredAsParallelCapable());
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac --release 17 ParallelRegistrationDemo.java
java ParallelRegistrationDemo
```

**Stdout đã kiểm thử bằng Windows/JDK 24 (code Java 17-compatible):**

```text
legacy registered = false
parallel registration succeeded = true
parallel registered = true
legacy locks on loader = true
legacy shares locks for names = true
parallel same name same lock = true
parallel different names distinct locks = true
blocked child registration = false
blocked child still serial = true
parallel child registration = true
parallel child registered = true
```

### 6.1. Điểm quan trọng của demo

`ParallelLoader` được đăng ký ở thời điểm class initialization, không phải lúc một request bắt đầu. `ParallelChild` cũng phải gọi `registerAsParallelCapable()` của riêng nó. `BlockedChild` thất bại, chứng minh không thể tự “bật parallel” nếu chuỗi kế thừa có một parent không đăng ký.

### 6.2. Vì sao so sánh reference với ==?

Trong ví dụ này mục tiêu là kiểm tra **cùng monitor object hay khác monitor object**, nên toán tử identity `==` và `!=` là phù hợp. Không so `toString()` hoặc `hashCode()` vì hai object có thể in giống nhau hoặc có hash collision.

### 6.3. Static field REGISTERED có phải bắt buộc?

Không. Có thể dùng static block:

```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError("not parallel capable");
    }
}
```

Dạng static block **fail fast** thường tốt cho production loader phải có concurrency thật sự. Demo giữ boolean để minh họa cả điều kiện thất bại mà không phá chương trình.

### 6.4. Trạng thái đăng ký không đo độ song song thực tế

`isRegisteredAsParallelCapable() == true` cho biết JVM ghi nhận loader class là parallel capable. Không chứng minh đoạn `findClass` của bạn không có lock rộng, không có data race hoặc không đang chờ I/O. Phải kiểm thử các đường nạp lớp thực sự.

## 7. Chương trình Java 17+: hai khóa theo hai tên có thể giữ đồng thời

**Tệp `ParallelNameLockDemo.java`**

Chương trình sử dụng `getClassLoadingLock` để lấy monitor cho hai tên, rồi đặt hai tasks cùng vào critical section trên **hai monitor khác nhau**. `CountDownLatch` kiểm tra cả hai tasks đã bước vào vùng khóa trước deadline.

**Giới hạn:** Đây là demo **hành vi khóa**, **không** định nghĩa bytecode/class. Demo định nghĩa class thực tế ở phần sau sẽ kiểm thử thêm `findClass` và `defineClass`.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ParallelNameLockDemo {
    static final class NamedLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError("cannot register");
            }
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    public static void main(String[] args) throws Exception {
        NamedLoader loader = new NamedLoader();
        CountDownLatch bothInside = new CountDownLatch(2);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        boolean together;
        try {
            Future<Boolean> a = executor.submit(() -> {
                synchronized (loader.lock("plugin.A")) {
                    bothInside.countDown();
                    return bothInside.await(5, TimeUnit.SECONDS);
                }
            });
            Future<Boolean> b = executor.submit(() -> {
                synchronized (loader.lock("plugin.B")) {
                    bothInside.countDown();
                    return bothInside.await(5, TimeUnit.SECONDS);
                }
            });
            together = a.get(8, TimeUnit.SECONDS) &&
                       b.get(8, TimeUnit.SECONDS);
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(8, TimeUnit.SECONDS);
        }

        System.out.println("parallel capable = " +
                loader.isRegisteredAsParallelCapable());
        System.out.println("same name same lock = " +
                (loader.lock("plugin.A") == loader.lock("plugin.A")));
        System.out.println("different names different locks = " +
                (loader.lock("plugin.A") != loader.lock("plugin.B")));
        System.out.println("two name locks overlap = " + together);
        System.out.println("executor stopped = " +
                executor.isTerminated());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ParallelNameLockDemo.java
java ParallelNameLockDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
parallel capable = true
same name same lock = true
different names different locks = true
two name locks overlap = true
executor stopped = true
```

### 7.1. Vì sao dùng CountDownLatch?

Hai tasks đều giữ monitor trước khi `bothInside.countDown()`. Nếu cùng tranh **một monitor**, chỉ một task giữ được monitor tại một thời điểm; nó chờ latch trong khi task kia chưa thể đi vào, nên test không đạt deadline. Với **hai monitors khác nhau**, cả hai tasks có thể cùng bước vào và latch về 0.

### 7.2. Tại sao có timeout trong await?

Một bài test concurrency không nên treo vô hạn nếu implementation sai. `await(5,SECONDS)` và `Future.get(8,SECONDS)` giới hạn thời gian. Trên máy quá tải, deadline có thể gây false negative; tăng deadline hợp lý khi chạy CI, nhưng không bỏ giới hạn chờ.

### 7.3. Có thể suy ra mọi lần nạp hai tên sẽ song song không?

Không. Mặc định cung cấp **khả năng khóa khác nhau**, nhưng parent loader, source I/O, cache, plugin initialization và tài nguyên chung khác vẫn có thể gây serialization. Bài test chỉ khẳng định chính xác rằng **hai khóa riêng có thể được giữ đồng thời**.

### 7.4. Không tự quản lý locks nếu không cần

Trong loader production, không cần gọi `getClassLoadingLock` thủ công khi chỉ override `findClass`; mặc định `loadClass` đã gọi và synchronized đúng. Demo cố ý expose lock để người học thấy sự khác biệt, không nhằm khuyên copy nó vào mọi đoạn code.

## 8. findClass an toàn: source bytecode và state chia sẻ

Đối với một loader dùng parent-first delegation:

```java
public final class PluginLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "PluginLoader must be parallel capable");
        }
    }

    private final Map<String, byte[]> definitions;

    public PluginLoader(ClassLoader parent, Map<String, byte[]> definitions) {
        super(parent);
        this.definitions = Map.copyOf(definitions);
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] bytes = definitions.get(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
```

Đây là **class Java 17+ minh họa**, cần `import java.util.Map;` và nguồn bytecode hợp lệ từ caller; không có `main` độc lập. Trong production, `byte[]` có thể bị caller thay đổi dù map đã được sao chép: để an toàn về ownership, **clone các mảng bytes khi nhận và không expose chúng cho writer khác**. Chỉ nạp bytes từ nguồn tin cậy và kiểm soát giới hạn kích thước.

### 8.1. Tại sao Map.copyOf chưa đóng băng byte[]?

`Map.copyOf` tạo immutable map structure, nhưng **các values vẫn là tham chiếu tới mảng `byte[]` mutable**. Nếu producer giữ các mảng gốc và ghi vào chúng khi findClass đang đọc, bạn có data race và có thể define bytecode bị thay giữa chừng.

Một thiết kế production tốt cần snapshot/clone từng byte array trước khi publish cho loader, hoặc dùng storage immutable được quản lý đúng.

### 8.2. Không dùng chung HashMap mutable thiếu synchronization

Nếu nhiều threads đồng thời thay đổi `HashMap<String,byte[]>` và gọi `findClass`, đăng ký parallel-capable **không bảo vệ map này**. Dùng immutable snapshot cho danh sách plugin đã được xác thực, hoặc `ConcurrentHashMap` với chính sách atomic publication rõ.

### 8.3. Mặc định loadClass đã kiểm tra lớp đã nạp

Nếu override chỉ `findClass`, không cần tự viết vòng `findLoadedClass` rồi `defineClass` trong `findClass`. Khi toàn bộ nạp lớp đi qua mặc định `loadClass`, JVM đã giữ per-name lock và tránh gọi lại findClass cho tên đã loaded.

### 8.4. Phân biệt không tìm được và bytecode hỏng

- Không có tên trong repository → `ClassNotFoundException`.
- Bytecode không hợp lệ → `ClassFormatError`.
- Tên bytes và expected binary name không phù hợp → lỗi linkage/name.
- Cố định nghĩa lớp trong package bị cấm, ví dụ `java.*` → có thể `SecurityException`.
- Hai lần định nghĩa cùng name trong cùng defining loader → `LinkageError`.

Không catch mọi `Throwable` rồi trả ClassNotFoundException: như thế có thể che nguyên nhân lỗi class format/definition đáng điều tra.

### 8.5. Parent-first delegation giúp gì?

JDK/default loader ưu tiên parent trước, giảm khả năng plugin định nghĩa lại lớp core hoặc API dùng chung theo cách xung đột. Nếu cần child-first cho plugin, thiết kế whitelist/parent-first cho Java/platform/shared contracts, kiểm soát package ownership, modules, resources và lock ordering kỹ hơn. **Chỉ vì muốn song song không phải lý do override loadClass thành child-first.**

## 9. Demo Java 17+ thực sự nạp hai lớp khác tên cùng lúc

**Tệp `ParallelDefinitionDemo.java`**

Ví dụ dưới đây hoạt động **không cần file JAR, database hay network**, giúp kiểm thử thread-safety và default class loading:

1. Tạo ba **class files tối giản** trong bộ nhớ cho `demo.parallel.GeneratedAlpha`, `GeneratedBeta`, `GeneratedGamma`. Chúng có Java class-file version **61** (Java 17), superclass `java.lang.Object`, không có method/constructor. Đây là dữ liệu **chỉ dùng để test khả năng nạp**, không có hành vi nghiệp vụ.
2. Custom `ParallelBytesLoader` đăng ký parallel-capable trong static initializer.
3. Override **`findClass`**, không override `loadClass`.
4. Hai threads nạp Alpha và Beta; `CountDownLatch` buộc cả hai phải **vào được `findClass`** trước khi đi tiếp. Một loader dùng khóa toàn cục sẽ không vượt qua barrier này đúng hạn.
5. Sau đó gửi **16 tasks nạp cùng tên Gamma** bằng cùng một loader. Mặc định `loadClass` phải đảm bảo chỉ có **một lần `findClass/defineClass`** cho tên Gamma.
6. Kiểm tra class identity, defining loader, số lượt findClass và ClassNotFoundException.

Chương trình dùng `super(null)` **chỉ để bootstrap delegate `java.lang.Object` mà không để application parent tìm ba class test trước**. Trong loader thật nên cấp parent thích hợp; `super(null)` không phải cấu hình mặc định an toàn cho plugin production.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ParallelDefinitionDemo {
    static byte[] minimalClass(String binaryName) throws IOException {
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);
            out.writeShort(61);
            out.writeShort(5);
            out.writeByte(1);
            out.writeUTF(binaryName.replace('.', '/'));
            out.writeByte(7);
            out.writeShort(1);
            out.writeByte(1);
            out.writeUTF("java/lang/Object");
            out.writeByte(7);
            out.writeShort(3);
            out.writeShort(0x0021);
            out.writeShort(2);
            out.writeShort(4);
            out.writeShort(0);
            out.writeShort(0);
            out.writeShort(0);
            out.writeShort(0);
            return buffer.toByteArray();
        }
    }

    static class ParallelBytesLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError("register failed");
            }
        }

        private final Map<String, byte[]> definitions;
        private final ConcurrentHashMap<String, AtomicInteger> findCounts =
                new ConcurrentHashMap<>();
        private final CountDownLatch differentEntered =
                new CountDownLatch(2);

        ParallelBytesLoader(Map<String, byte[]> definitions) {
            super(null);
            this.definitions = Map.copyOf(definitions);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = definitions.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }

            findCounts.computeIfAbsent(name, k -> new AtomicInteger())
                    .incrementAndGet();

            if (name.endsWith("Alpha") || name.endsWith("Beta")) {
                differentEntered.countDown();
                try {
                    if (!differentEntered.await(5, TimeUnit.SECONDS)) {
                        throw new ClassNotFoundException(
                                "overlap not observed");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new ClassNotFoundException(name, e);
                }
            }
            return defineClass(name, bytes, 0, bytes.length);
        }

        int finds(String name) {
            AtomicInteger count = findCounts.get(name);
            return count == null ? 0 : count.get();
        }

        boolean bothEntered() {
            return differentEntered.getCount() == 0;
        }
    }

    public static void main(String[] args) throws Exception {
        String alpha = "demo.parallel.GeneratedAlpha";
        String beta = "demo.parallel.GeneratedBeta";
        String gamma = "demo.parallel.GeneratedGamma";

        ParallelBytesLoader loader = new ParallelBytesLoader(Map.of(
                alpha, minimalClass(alpha),
                beta, minimalClass(beta),
                gamma, minimalClass(gamma)));

        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            Future<Class<?>> fa = pool.submit(
                    () -> loader.loadClass(alpha));
            Future<Class<?>> fb = pool.submit(
                    () -> loader.loadClass(beta));
            Class<?> a = fa.get(8, TimeUnit.SECONDS);
            Class<?> b = fb.get(8, TimeUnit.SECONDS);

            List<Future<Class<?>>> same = new ArrayList<>();
            for (int i = 0; i < 16; i++) {
                same.add(pool.submit(() -> loader.loadClass(gamma)));
            }

            Class<?> first = same.get(0).get(8, TimeUnit.SECONDS);
            boolean allSame = true;
            for (Future<Class<?>> f : same) {
                allSame &= f.get(8, TimeUnit.SECONDS) == first;
            }

            boolean missingRejected = false;
            try {
                loader.loadClass("demo.parallel.Missing");
            } catch (ClassNotFoundException expected) {
                missingRejected = true;
            }

            System.out.println("registered = " +
                    loader.isRegisteredAsParallelCapable());
            System.out.println("different names entered together = " +
                    loader.bothEntered());
            System.out.println("different class objects = " + (a != b));
            System.out.println("defining loader matches = " +
                    (a.getClassLoader() == loader &&
                     b.getClassLoader() == loader));
            System.out.println("alpha findClass calls = " +
                    loader.finds(alpha));
            System.out.println("beta findClass calls = " +
                    loader.finds(beta));
            System.out.println("gamma findClass calls = " +
                    loader.finds(gamma));
            System.out.println("same name same Class object = " + allSame);
            System.out.println("missing class rejected = " +
                    missingRejected);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(8, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ParallelDefinitionDemo.java
java ParallelDefinitionDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
registered = true
different names entered together = true
different class objects = true
defining loader matches = true
alpha findClass calls = 1
beta findClass calls = 1
gamma findClass calls = 1
same name same Class object = true
missing class rejected = true
```

### 9.1. Vì sao tự tạo class file tối giản?

Để chương trình **độc lập với file ngoài** và có thể chứng minh đường `defineClass` thật, không chỉ giả lập loadClass. Hàm `minimalClass` viết một class-file header và constant pool tối giản với cấu trúc hợp lệ cho Java 17. Class được tạo **không có constructor**, nên không dùng để tạo object hay chạy business logic. Trong production, **không** tự tạo bytecode bằng phương pháp này; hãy sử dụng classfile compiler/build artifacts đã được kiểm tra.

### 9.2. Vì sao two names entered together = true có ý nghĩa?

Trong `findClass`, Alpha và Beta mỗi bên giảm `CountDownLatch(2)` rồi chờ tới khi cả hai đã vào phương thức. Nếu loader chỉ giữ **một global lock** xuyên suốt quá trình tìm class, một thread sẽ không vào được khi thread còn lại chờ, và barrier timeout. Với khóa riêng theo name, hai threads có thể vào `findClass` đồng thời, nên test vượt barrier.

Điều này kiểm chứng **một thuộc tính concurrency** ở đường `findClass` của ví dụ, không phải đo tốc độ production. Trên máy quá tải, timeout test vẫn có thể thất bại do scheduling, nên cần timeout phù hợp CI.

### 9.3. Vì sao gamma findClass calls = 1?

Cả 16 tasks gọi `loader.loadClass(gamma)` trên **cùng một loader instance**. Mặc định `loadClass` đồng bộ theo `getClassLoadingLock(gamma)`, và lần tới kiểm tra `findLoadedClass(gamma)`; do đó trong ví dụ thành công, `findClass` chỉ gọi một lần. Nếu tự override `loadClass` mà bỏ locking và loaded-check, test này có thể phát hiện lỗi.

### 9.4. findCounts dùng ConcurrentHashMap có ích gì?

`findClass` cho Alpha và Beta có thể chạy đồng thời, nên cập nhật counters bằng `HashMap` không đồng bộ là sai. Code dùng `ConcurrentHashMap<String,AtomicInteger>` cùng `computeIfAbsent` và `incrementAndGet` để đếm chính xác mà không giữ global lock của loader.

### 9.5. Vì sao using Map.copyOf đủ trong demo nhưng chưa đủ ở production?

Trong demo, mọi `byte[]` được tạo một lần và không còn bị chỉnh sửa. Trong production, nếu input byte arrays có writer khác, `Map.copyOf` **không copy sâu**. Cần clone hoặc parse từ immutable artifact có ownership rõ ràng. Đây là khác biệt quan trọng giữa sample kiểm thử và code được phép xử lý plugin/bytecode thật.

### 9.6. Làm thế nào chứng minh Class<?> thuộc loader nào?

`a.getClassLoader() == loader`. Đây là bằng chứng **defining loader** trong demo vì class test không có ở bootstrap. Một class được tìm thấy qua parent delegation có thể có `getClassLoader()` là parent hoặc null (bootstrap), dù request bắt đầu từ loader con.

## 10. Class identity và bài toán nhiều loader

Trong JVM, class identity gắn với **binary name và defining ClassLoader**. Hai loaders có thể định nghĩa các lớp cùng tên nhưng JVM coi đó là hai loại khác nhau.

```text
Loader A defines "plugin.User" -> Class A
Loader B defines "plugin.User" -> Class B

Tên trùng nhau nhưng Class A != Class B.
```

Một request ở loader con có thể được parent đáp ứng, nên `Class.getClassLoader()` cho thấy **loader định nghĩa thực sự** chứ không nhất thiết là loader mà bạn gọi `loadClass`.

### 10.1. Parallel loading không làm mất class identity

Đăng ký `registerAsParallelCapable()` chỉ thay mô hình lock cho nạp lớp. Nó không có nghĩa hai loaders khác nhau tự chia sẻ cùng một `Class<?>` khi tên giống nhau, cũng không tạo cơ chế dedup toàn JVM.

### 10.2. Vì sao ClassCastException vẫn xảy ra?

Hai plugin tự nạp hai định nghĩa cùng tên cho API contract, sau đó cast object từ plugin A sang class ở plugin B có thể fail, dù tên in giống nhau. Cần thiết kế **shared API loader** / parent delegation phù hợp để các component thực sự chia sẻ cùng Class identity khi muốn tương tác.

### 10.3. Khóa per-name không xuyên qua nhiều loaders

`loaderA.getClassLoadingLock("plugin.User")` và `loaderB.getClassLoadingLock("plugin.User")` thuộc hai loader instances khác nhau. Không có chuyện chúng đồng bộ global để “chỉ một Class plugin.User trên JVM”. Đó chính là lý do nhiều class-loader namespaces tồn tại.

## 11. Khi nào phải tự override loadClass?

**Khuyến nghị mặc định: chỉ override findClass.** Tuy nhiên một plugin engine có chủ đích child-first, delegation có nhiều nhánh, bytecode transformer, package routing đặc biệt hoặc OSGi-like framework có thể cần override `loadClass`. Khi đó bạn chịu trách nhiệm thực hiện **đúng chu kỳ concurrency**:

```java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);
        if (c == null) {
            // Chọn chiến lược delegation được thiết kế/kiểm chứng.
            // Thử parent trước hoặc findClass trước theo policy hợp lệ.
            c = decideAndLoad(name);
        }
        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
```

Đây là **pseudocode không độc lập**: `decideAndLoad(name)` chỉ là tên chỉ chỗ cho một chiến lược có thật, chưa được định nghĩa. Không copy vào production rồi chạy. Nó nhắc các **bước phải bảo tồn**, không cung cấp triển khai child-first đầy đủ.

### 11.1. Không bỏ findLoadedClass check

Nếu bỏ check và cứ gọi `defineClass(name,bytes,...)`, hai threads cùng tên có thể đua, định nghĩa lặp và ném `LinkageError`. Nếu class đã được parent delegate, tình trạng initiating loader cũng cần được xử lý đúng theo JVM contract.

### 11.2. Không giữ global lock vô lý

Nếu code override dùng `synchronized(this)` xuyên suốt I/O hoặc recursive delegation, hai tên khác nhau lại phải chờ nhau. Registration vẫn true nhưng concurrency thực tế trở lại serial.

### 11.3. Không tạo lock object mới mỗi lượt gọi

Sai:

```java
synchronized (new Object()) {
    // Không hề khóa cùng monitor giữa các callers.
}
```

Hai threads vào hai monitors khác nhau ngay cả khi yêu cầu cùng binary name; không ngăn race. Dùng `getClassLoadingLock(name)` (hoặc mặc định loadClass) để có lock cùng name ổn định.

### 11.4. Có thể dùng cache concurrent thay thế lock không?

Một cache `ConcurrentHashMap.computeIfAbsent` có thể bảo vệ một số operations cache, nhưng **không tự thay thế mọi JVM classloading contract**, đặc biệt khi code tự dùng `defineClass`, parent delegation, linking và recursive requests. Giữ lớp khóa thích hợp quanh load path; dùng cache concurrent để bảo vệ **dữ liệu bổ sung** của loader.

## 12. Lỗi deadlock khi có delegation phức tạp

Trong mô hình parent-first thuần cây, việc delegate theo một chiều thường đơn giản hơn. Nhưng nhiều plugin runtimes có **đồ thị delegation không phân cấp**, ví dụ A tìm class ở B còn B có thể gọi ngược A.

```text
Thread-1: loader A giữ khóa A rồi cần loader B
Thread-2: loader B giữ khóa B rồi cần loader A

Nếu cả hai dùng khóa toàn loader:
  Thread-1 giữ lock A, đợi lock B
  Thread-2 giữ lock B, đợi lock A
  -> deadlock.
```

Parallel-capable per-name locking giúp **giảm phạm vi khóa** và có thể tránh những deadlocks do khóa toàn loader trong các trường hợp nhiều tên lớp khác nhau. Javadoc ClassLoader nhấn mạnh parallel capability trong môi trường delegation không strictly hierarchical.

Tuy nhiên, nó **không bảo đảm loại bỏ mọi deadlock**: nếu hai threads đều muốn cùng một tên, hoặc plugin code sử dụng các locks khác với thứ tự vòng, vẫn có thể xảy ra deadlock.

### 12.1. Lock-order inversion

Ngay cả với per-name locks:

```text
Thread 1: giữ lock("plugin.A"), trong findClass cần load("plugin.B")
Thread 2: giữ lock("plugin.B"), trong findClass cần load("plugin.A")
```

Hai locks khác nhau có thể tạo cycle nếu code nạp đệ quy mà không có thứ tự nhất quán. Registration không phát hiện cycle hộ bạn. Thiết kế dependency graph rõ, hạn chế delegation vòng và phân tích lock ordering.

### 12.2. Không giữ lock riêng khi gọi ngược plugin code không tin cậy

Nếu `findClass` gọi callback của plugin có thể lại `loadClass` hoặc giữ nhiều locks khác, rất khó chứng minh không có cycle. Nên giới hạn trách nhiệm `findClass`: tìm bytes, kiểm tra/define class và trả; không làm business logic hoặc khởi chạy plugin trong vùng nạp lớp.

### 12.3. Class initialization cũng có thể gây deadlock

`loadClass(name)` là hoạt động **loading/linking**, không đồng nhất với **initialization** của class. `Class.forName(name,true,loader)` kích hoạt initialization; static initializers có thể giữ các locks khác hoặc chờ threads. Parallel capable của loader **không sửa** deadlock do static initializer phức tạp.

## 13. Loading, linking và initialization khác nhau

Trong JVM có các pha liên quan:

1. **Loading**: tìm/định nghĩa class.
2. **Linking**: verification, preparation và resolution khi cần.
3. **Initialization**: thực thi static field initializers và static blocks của class.

`ClassLoader.loadClass("plugin.Foo")` thường tải/lấy Class object mà **không chủ động initialize class**. `Class.forName("plugin.Foo", true, loader)` có thể kích hoạt initialization.

### 13.1. registerAsParallelCapable là static initializer của LOADER CLASS

Đây là điểm rất dễ nhầm: lệnh `registerAsParallelCapable()` nằm trong static block của **lớp custom ClassLoader**, không phải static block của từng class plugin được loader nạp. Đăng ký có hiệu lực cho hành vi nạp của loader class, không phải “bật song song” riêng cho một class plugin.

### 13.2. resolveClass không phải tự chạy static initializer

Trong mặc định `loadClass(String,boolean)`, flag `resolve` khiến loader gọi `resolveClass(c)`. Đây là **linking/resolution**, không đồng nghĩa thực thi static block của target. Vì vậy không nên viết test “loadClass phải luôn in dòng static initializer của plugin”.

### 13.3. Class.forName(name,false,loader) giúp tách loading khỏi init

Với test runtime cần quan sát chỉ loading/linking mà không kích hoạt static initializer, dùng `Class.forName(name, false, loader)` khi thích hợp. Nhưng bản thân việc tạo Class objects, resolution dependencies và class loader callbacks vẫn có thể sinh hoạt động khác; không giả định nó không bao giờ nạp dependencies.

## 14. Thread safety của dữ liệu nội bộ ClassLoader

Đăng ký parallel capable có nghĩa `findClass` **có thể** được gọi đồng thời cho hai tên khác nhau. Do đó mọi state chia sẻ phải có mô hình concurrency:

| Thành phần trong loader | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `HashMap<String,byte[]>` có writers | Data race, state không nhất quán | Immutable snapshot hoặc ConcurrentHashMap |
| Mutable byte arrays từ caller | Reader nhìn bytecode bị thay đổi | Clone/copy bytes trước publication |
| Counter `int findCount++` | Lost updates | AtomicInteger/LongAdder |
| Resource cache mutable | Race/duplicate fetch | Concurrent cache + ownership |
| Global `synchronized(this)` | Serialization các names khác nhau | Per-name locks, giảm critical section |
| Callback plugin trong findClass | Re-entrant loading/deadlock | Tách lifecycle, giới hạn callbacks |
| Concurrent JAR/ZIP access | Tùy API/implementation | Storage access thread-safe, test |
| Parent delegation cycle | Deadlock hoặc circularity | Graph rõ ràng, lock ordering |
| Bytecode từ nguồn không tin cậy | Execution of malicious code | Chỉ nạp artifacts đáng tin hoặc isolate process |

### 14.1. ConcurrentHashMap không thay cho toàn bộ thiết kế

`ConcurrentHashMap` giúp bảo vệ **chính map đó**. Nếu class bytes là mutable, hoặc loader gọi `defineClass` hai lần ngoài per-name lock, map concurrent vẫn không đủ. Concurrent cache cần policy invalidation, class versioning, errors và visibility rõ.

### 14.2. Một ClassLoader không có API unload từng class đơn giản

Class loading ảnh hưởng lifecycle lâu dài. Không thể cứ xoá entry trong map rồi mong JVM “quên” một Class đã định nghĩa trong cùng loader. Class unloading phụ thuộc garbage collection và toàn bộ defining loader/classes không còn reachable theo điều kiện runtime. Nếu cần thay version plugin, thường tạo **loader instance mới** và giải phóng mọi references tới loader cũ.

### 14.3. Mutable configuration nên ổn định trong suốt load

Nếu một request đang nạp `plugin.Service` mà repository plugin bị đổi version cùng lúc, cùng loader có thể thấy bytes mới/không đồng nhất. Nên snapshot artifact version hoặc quản lý lifecycle swap khi không còn in-flight loads. Tránh viết xuyên vào files đang được đọc ở đường defineClass.

## 15. An toàn bảo mật: parallel capable không phải sandbox

**Không được xem `registerAsParallelCapable` là API bảo mật.** Nó giải quyết vấn đề concurrency, không xác thực class files, không chặn mã độc và không cách ly quyền thực thi của bytecode do ứng dụng nạp.

Khi thiết kế plugin:

- Chỉ nạp bytecode từ **nguồn tin cậy** hoặc được xác thực bằng cơ chế phù hợp.
- Kiểm tra binary name, artifact origin, metadata/version, chữ ký/checksums khi yêu cầu.
- Giới hạn kích thước input và tránh zip bombs/resources exhaustion.
- Không cho phép plugin override tùy tiện các shared API packages.
- Hiểu module boundaries, exports/opens và parent delegation.
- Đối với code thực sự **không đáng tin**, cân nhắc chạy ở **process/container riêng** với hệ thống quyền hạn/resource limits phù hợp; ClassLoader không phải một security boundary đủ mạnh.
- Đảm bảo plugin resource cleanup, thread/callback lifecycle và classloader unloading khi reload.

### 15.1. Không định nghĩa lớp trong java.* bằng custom loader

Javadoc `defineClass` có hạn chế với class name bắt đầu bằng `java.`, có thể ném `SecurityException`. Đừng cố dùng child-first loading để ghi đè core Java classes trong application. Giữ parent/platform class identity nhất quán.

### 15.2. ClassLoader không “verify nguồn tin cậy” hộ bạn

JVM kiểm tra **hợp lệ của classfile và rules về loại**, nhưng không đánh giá bytecode nghiệp vụ có độc hại hay không. Một classfile hợp lệ vẫn có thể chạy mã nguy hiểm khi được initialization/call. Xử lý bytecode ngoài phạm vi trust không thể giải quyết chỉ bằng synchronized hoặc parallel registration.

## 16. Khi nào KHÔNG cần custom parallel ClassLoader?

Đa số ứng dụng chỉ dùng **system/application class loader** hoặc framework class loading chuẩn. Không cần tạo subclass ClassLoader và gọi `registerAsParallelCapable` chỉ vì một service có nhiều threads. Chỉ cần khi bạn thật sự implement class-loading logic riêng, chẳng hạn:

- Plugin system riêng có repository class bytes.
- Dynamic module/runtime với nhiều sources.
- Công cụ instrumentation/code generation có loader quản lý danh tính class.
- Nạp class files từ lưu trữ đặc thù cần parent delegation có kiểm soát.
- Framework có dynamic class resolution phức tạp.

Nếu một thư viện đã cung cấp loader parallel-capable đã được kiểm chứng, **ưu tiên dùng thư viện** hơn tự viết class-loader concurrency engine.

### 16.1. URLClassLoader và custom loaders

`java.net.URLClassLoader` vẫn có trong Java 17; bạn có thể cần cung cấp URL/JAR paths và lifecycle phù hợp. Nhưng không suy rằng một subclass tự viết của URLClassLoader hoặc SecureClassLoader đã registered chỉ vì superclass hoạt động theo kiểu nào đó. Với **lớp con**, kiểm tra `isRegisteredAsParallelCapable()` và registration chain theo Javadoc.

### 16.2. Với module system

Trong Java 9+ có JPMS. `ClassLoader` có API `findClass(String moduleName,String name)` và các quy tắc module/resource access. Nếu loader của bạn phục vụ **named modules**, cần xem API module-aware và resolution rules, không áp dụng máy móc lời giải chỉ dành cho classpath/unnamed module.

## 17. Kiểm thử concurrency có giá trị thực

Một test tốt cần tạo điều kiện thật sự có hai workers và có **đồng bộ thời điểm** để quan sát overlap. Chỉ submit hai tasks rồi nhìn stdout theo thứ tự bất kỳ không chứng minh parallelism, vì scheduler có thể vô tình tuần tự.

### 17.1. Ba loại kiểm thử quan trọng

**Kiểm thử đăng ký:**
- Một subclass không đăng ký trả false.
- Subclass đăng ký từ ClassLoader trả true.
- Lớp con của parent chưa đăng ký không thể đăng ký.
- Chuỗi parent/child có đủ registration trả true.

**Kiểm thử per-name locking:**
- Cùng name cho cùng monitor.
- Khác names cho monitors khác nhau.
- Hai threads có thể đồng thời giữ hai monitors.
- Không giữ global lock trong code tùy biến.

**Kiểm thử thực sự định nghĩa class:**
- Hai tên khác nhau đi vào `findClass` đồng thời.
- Cùng name được yêu cầu bởi N threads vẫn chỉ định nghĩa một lần trên cùng loader.
- Class<?> trả cho các requests cùng name cùng identity.
- Định nghĩa khác tên trả Class objects khác nhau.
- Class not found ném `ClassNotFoundException`.
- Bytecode lỗi/class name sai truyền `LinkageError`/format errors phù hợp.

### 17.2. Các test bổ sung nên có

- Parent tìm được class: `findClass` của child **không** được gọi.
- Parent không tìm được: child `findClass` mới định nghĩa.
- Nạp transitive dependencies với package khác nhau.
- Interruption/timeout trong custom I/O: tránh treo các locks.
- Concurrent plugin repository updates: snapshot consistency.
- Classloader hierarchy với nhiều tầng registered/unregistered.
- Class definitions trong các modules/packages phù hợp.
- Nạp lại cùng tên từ **loader instance khác**: class identity khác khi cả hai tự định nghĩa.
- Long-running soak test cho deadlock, memory leak và throughput.
- Reload plugin: không giữ stale Class<?>/ClassLoader refs.
- Stress test lỗi cùng thời điểm mà nhiều threads yêu cầu cùng name.

### 17.3. Không dùng Thread.sleep làm bằng chứng concurrency

Nếu chỉ viết `Thread.sleep(100)` bên trong hai tasks, chúng có thể chạy nối tiếp mà vẫn in đúng số dòng. Dùng latch/barrier và timeout để xác nhận “cả hai đã vào cùng critical section”, như hai demos ở trên.

### 17.4. Không giả định executor 8 threads bảo đảm 8 tasks đồng thời

Thread scheduler, CPU saturation và synchronization vẫn ảnh hưởng. Một pool size 8 cho **khả năng có tối đa 8 workers** trong ví dụ; không có bảo đảm mọi task bắt đầu cùng nano-second. Do đó sử dụng `CountDownLatch` kiểm thử overlap và `Future.get(timeout)` để có deadline.

## 18. Hiệu năng và khả năng quan sát

Parallel-capable có thể giảm **loader-wide contention** cho những tên lớp khác nhau, nhất là khi `findClass` chậm hoặc loader graph có delegation phức tạp. Nhưng không nên tuyên bố nó luôn tăng throughput lên một tỷ lệ cố định.

Những bottlenecks khác:

- Parent loader có locks hoặc I/O riêng.
- JAR/ZIP đọc từ cùng storage, disk contention.
- Global mutable cache.
- Lock trên `this` trong findClass.
- Đồng bộ ở logging/metrics.
- Remote artifact fetch.
- Class verification/resolution.
- Static initialization phức tạp.
- Plugin code hoặc callback giữ global locks.
- JVM GC hoặc class-loading pressure.

### 18.1. Nên đo gì?

- Số lần `findClass` theo binary name.
- Thời gian `loadClass` trung bình và tail latency.
- Thời gian chờ mỗi lock theo tên (nếu đo được).
- Số concurrent class requests và số active findClass.
- Tần suất ClassNotFoundException/LinkageError.
- Thời gian I/O đọc class bytes.
- Class-load counts và class-unloading/memory metrics.
- Số deadlocks qua thread dumps.
- Loading failures dưới plugin reload/deploy.
- CPU/allocation overhead của caches và instrumentation.

### 18.2. Không benchmark bằng println trong findClass

Logging mỗi class trong hot path có thể tạo lock I/O console và che hết lợi ích của per-name locking. Nếu cần đo, dùng counters/metrics hợp lý và benchmark theo cấu trúc thực tế. Java Flight Recorder (JFR), thread dumps và Java tooling hiện hành có thể hỗ trợ phân tích class loading.

### 18.3. Không quy mọi slow startup cho parallel loading

Một ứng dụng có thể chậm do class initialization, static dependency cycles, injection framework, scanning annotations, network calls hoặc JIT. Parallel-capable giải quyết **mức độ khóa khi tải lớp**, không tự song song hóa mọi giai đoạn startup hoặc việc instantiate beans.

## 19. Các lỗi thường gặp

**1. “ClassLoader gốc parallel capable nên mọi subclass tự động parallel.”** Sai: subclass cần đăng ký riêng.

**2. “Gọi registerAsParallelCapable từ main sau khi đã tạo loader vẫn bật được.”** Sai: registration cần trước instance của caller.

**3. “Subclass của một parent không registered vẫn đăng ký thành công.”** Sai: tất cả superclasses trừ Object phải registered.

**4. “registerAsParallelCapable là method của từng instance.”** Sai: protected static, xét caller class.

**5. “Chỉ cần gọi method mà không kiểm tra boolean.”** Không an toàn: false đồng nghĩa chưa registered.

**6. “Sau khi registered có thể tắt parallel lại.”** Không có cơ chế unregister.

**7. “isRegisteredAsParallelCapable có từ Java 7.”** Không: kiểm tra instance được bổ sung từ Java 9; Java 17 có.

**8. “getClassLoadingLock luôn trả this.”** Sai nếu loader đã registered parallel-capable.

**9. “Hai tên khác nhau sẽ luôn dùng cùng monitor trong parallel loader.”** Sai: mặc định per-name locks.

**10. “Cùng tên ở một loader sẽ được define hai lần nếu có hai threads.”** Không trong mặc định loadClass; nó đồng bộ per-name và kiểm tra loaded.

**11. “Locks per-name nghĩa không thể có deadlock.”** Sai: còn lock cycles và plugin state.

**12. “Override findClass nghĩa cần tự bỏ mặc định loadClass.”** Sai: thường chỉ cần override findClass.

**13. “Không kiểm tra findLoadedClass khi tự override loadClass cũng được.”** Sai: dễ race/duplicate definition.

**14. “registerAsParallelCapable tự bảo vệ HashMap mutable.”** Sai: state app vẫn phải thread-safe.

**15. “Map.copyOf clone toàn bộ byte[] values.”** Sai: clone map structure, không deep copy arrays.

**16. “synchronized(this) trong findClass không ảnh hưởng throughput.”** Sai: gây serialization giữa các tên.

**17. “new Object() trong mỗi synchronized bảo vệ cùng name.”** Sai: mỗi lần là monitor khác.

**18. “String.intern thích hợp làm global lock cho mọi loader.”** Rủi ro cross-component lock contention/cycles.

**19. “ConcurrentHashMap thay thế toàn bộ JVM classloading synchronization.”** Sai: cache thread-safety không thay contract define/delegate.

**20. “Parent đã có class vẫn luôn gọi findClass của child.”** Sai: mặc định parent-first có thể trả class từ parent.

**21. “getClassLoader() luôn là loader được gọi trong loadClass.”** Sai: parent có thể định nghĩa.

**22. “Hai loaders có cùng binary name là một class identity.”** Sai: defining loader là thành phần identity.

**23. “LinkageError luôn có nghĩa class file không tìm thấy.”** Sai: not found thường ClassNotFoundException; linkage có lỗi khác.

**24. “ClassNotFoundException bao trùm mọi lỗi bytecode.”** Sai: bytecode malformed có thể ClassFormatError.

**25. “Cứ retry defineClass khi LinkageError do duplicate.”** Không: phải kiểm tra locking/name/loaded state.

**26. “ClassLoader bảo đảm bytecode không tin cậy được sandbox.”** Sai: class loading không phải security boundary đầy đủ.

**27. “super(null) là parent thích hợp cho mọi plugin.”** Không: chỉ dùng có chủ đích, có thể thiếu platform/shared APIs.

**28. “Parallel capable cho phép override lớp java.*.”** Sai: class definition bị ràng buộc package/name và access rules.

**29. “loadClass luôn thực thi static initializer của plugin.”** Không: loading/linking khác initialization.

**30. “resolveClass tương đương Class.forName(name,true,...).”** Sai: resolve/link không đồng nghĩa initialize.

**31. “Static initializer đăng ký nằm trong mọi class plugin.”** Sai: nằm trong subclass ClassLoader.

**32. “Có hai tasks nạp đồng thời thì chắc hai findClass chạy đồng thời.”** Không: kiểm tra bằng barrier.

**33. “16 tasks cùng name nên findClass bị gọi 16 lần.”** Không với default loadClass đúng và same loader.

**34. “Một loader registered true bảo đảm mọi worker không tranh resource.”** Không: storage/cache/parent có thể tranh chấp.

**35. “Có thể unload một class bằng cách xóa Map entry.”** Sai: class identity/lifetime phụ thuộc JVM loader reachability.

**36. “Reload cùng class bằng cùng loader sau khi định nghĩa là đơn giản.”** Không: thường cần loader instance mới khi thay plugin version.

**37. “ClassLoader immutable vì API đăng ký static.”** Sai: custom loader có thể chứa state mutable và phải tự bảo vệ.

**38. “Class initialization không thể deadlock nếu loader parallel.”** Sai: static initializers có locks riêng.

**39. “Mọi custom ClassLoader nên bỏ parent delegation để chạy nhanh.”** Sai: rủi ro identity/security/modules.

**40. “Một lần chạy demo đúng đồng nghĩa production không bao giờ deadlock.”** Không: cần stress/integration tests và review toàn bộ lock graph.

## 20. Checklist code review

- [ ] Đây có thật sự là trường hợp phải viết custom ClassLoader?
- [ ] Đã hiểu binary name và defining ClassLoader?
- [ ] Có parent được thiết kế đúng cho application/framework?
- [ ] Mặc định chỉ override `findClass`, không override loadClass nếu không bắt buộc?
- [ ] Đã đăng ký `registerAsParallelCapable()` trong static initializer?
- [ ] Đã kiểm tra return value true, không im lặng tiếp tục khi false?
- [ ] Đã bảo đảm chưa tạo instance của loader class khi đăng ký?
- [ ] Mọi superclass của loader (trừ Object) đều registered?
- [ ] Có thể xác minh bằng `isRegisteredAsParallelCapable()` trên Java 17+?
- [ ] Có tránh nhầm registration của parent với registration của child?
- [ ] Không override getClassLoadingLock nếu không có lý do kỹ thuật rõ?
- [ ] Cùng name có cùng lock trong loader instance?
- [ ] Khác names có thể tiến hành song song theo chính sách locks?
- [ ] Không giữ synchronized(this) quanh toàn bộ findClass và slow I/O?
- [ ] Nếu override loadClass, có lock theo name và check findLoadedClass?
- [ ] Nếu override loadClass, có bảo toàn delegation, resolve và errors?
- [ ] Không dùng new Object() mỗi request làm monitor vô hiệu?
- [ ] Không dùng String.intern() làm lock tùy tiện?
- [ ] Bytecode repository là immutable hoặc concurrent-safe?
- [ ] Mỗi byte[] được snapshot/clone nếu có writer khác?
- [ ] Không để plugin artifact bị thay khi đang load?
- [ ] Metrics/counters được cập nhật thread-safe?
- [ ] Cache không dùng HashMap mutable thiếu bảo vệ?
- [ ] Có kiểm tra class name khớp bytes và package policy?
- [ ] Có phân biệt ClassNotFoundException với LinkageError/ClassFormatError?
- [ ] Có tránh swallow Throwable trong findClass?
- [ ] Có thiết kế parent-first/shared API identity phù hợp?
- [ ] Không cho plugin đè lên java.* hoặc shared contract classes?
- [ ] Có xét module system nếu dùng named modules?
- [ ] Có kiểm tra delegation cycles và lock order?
- [ ] Không gọi plugin callbacks không tin cậy trong critical section?
- [ ] Có phân biệt loading/linking với initialization?
- [ ] Không coi ClassLoader là security sandbox?
- [ ] Với untrusted code, có isolation mạnh hơn như process/container?
- [ ] Có test 2 tên khác nhau cùng vào findClass?
- [ ] Có test nhiều threads cùng tên và findClass chỉ một lần?
- [ ] Có test parent fallback, not found và malformed bytecode?
- [ ] Có stress/load testing và thread dump diagnostics?
- [ ] Có kiểm tra classloader lifecycle khi plugin reload?
- [ ] Không tuyên bố speedup cố định nếu chưa benchmark?
- [ ] API và ví dụ Java 17+ còn được hỗ trợ?

## 21. Câu hỏi tự kiểm tra

**1.** Parallel-capable class loader là gì? — Loader được đăng ký và thiết kế để có thể nạp những lớp khác tên đồng thời.

**2.** API đăng ký là gì? — `ClassLoader.registerAsParallelCapable()`.

**3.** Method register là static hay instance? — Protected static, xét caller class.

**4.** Gọi register ở đâu? — Static initializer của custom ClassLoader subclass, trước khi tạo instance.

**5.** Hai điều kiện đăng ký thành công? — Chưa có instance của caller và mọi superclass trừ Object đã đăng ký.

**6.** Register trả false khi nào? — Không thỏa điều kiện đăng ký.

**7.** Có API unregister không? — Không.

**8.** ClassLoader gốc đã registered chưa? — Có, mặc định theo Javadoc.

**9.** Subclass extends ClassLoader tự động registered chưa? — Chưa; phải đăng ký.

**10.** Method kiểm tra trạng thái trên instance? — `isRegisteredAsParallelCapable()` (Java 9+).

**11.** ClassLoader không parallel-capable khóa theo gì? — Mặc định getClassLoadingLock trả this, khóa toàn loader.

**12.** Parallel-capable khóa theo gì? — Mặc định một monitor gắn với binary name.

**13.** Hai threads cùng tên có được define class hai lần trên cùng loader? — Không trong mặc định loadClass đúng; phải giữ same-name synchronization và loaded check.

**14.** Hai threads khác tên có thể vào findClass đồng thời không? — Có khả năng, nếu các resources/locks khác không chặn.

**15.** Có cần override getClassLoadingLock để bật parallel không? — Không, đăng ký và dùng mặc định thường đủ.

**16.** Override method nào được Javadoc khuyên? — `findClass(String)`, không phải loadClass.

**17.** Các bước loadClass mặc định? — get lock, findLoadedClass, parent, findClass, resolve nếu cần.

**18.** Ưu tiên parent-first có tác dụng gì? — Giúp duy trì shared API/platform class identity và delegation rõ.

**19.** Khi parent load được class, child findClass có được gọi không? — Thường không trong parent-first default.

**20.** Method tạo Class từ bytes? — `defineClass(name,bytes,offset,length)` trong subclass.

**21.** Không tìm thấy class thường báo gì? — `ClassNotFoundException`.

**22.** Bytecode không hợp lệ có thể báo gì? — `ClassFormatError` và errors liên quan.

**23.** Vì sao cùng binary name ở hai loaders có thể khác type? — Class identity gồm defining loader.

**24.** Map.copyOf có deep-copy byte arrays không? — Không.

**25.** ConcurrentHashMap giải quyết những gì? — Thread safety của map operations, không tự bảo vệ mọi class loading rules.

**26.** Vì sao synchronized(this) không phù hợp trong parallel findClass? — Tuần tự hóa cả những tên khác nhau.

**27.** Vì sao new Object() mỗi lần khóa là sai? — Callers không cùng monitor, mất bảo vệ cho cùng tên.

**28.** Vì sao String.intern lock nguy hiểm? — Có thể tranh khóa/lock cycle giữa các components.

**29.** Parallel registration có loại bỏ mọi deadlock không? — Không, còn dependency/lock cycles và static initialization.

**30.** loadClass có bắt buộc initialize class không? — Không.

**31.** resolveClass có chạy static initializer không? — Không đồng nhất với initialization.

**32.** Static block register thuộc loader hay plugin class? — Loader class.

**33.** Tại sao cần CountDownLatch khi test parallel? — Chứng minh overlap chứ không chỉ có hai tasks submit.

**34.** Demo 16 tasks cùng Gamma kiểm tra gì? — Chỉ một findClass/defineClass và cùng Class object trên một loader.

**35.** Dùng super(null) trong production plugin có an toàn mặc định không? — Không, phải chọn parent theo module/platform/shared API requirements.

**36.** Custom ClassLoader có là sandbox chống bytecode độc hại không? — Không.

**37.** Nếu muốn thay plugin class đã nạp, chỉ xoá entry cache đủ không? — Không; thường cần loader instance mới và giải phóng references cũ.

**38.** Loader registered true nhưng có HashMap race thì sao? — Vẫn sai; registration không sửa state race.

**39.** Khi nào cần benchmark? — Khi muốn kết luận performance; đo workload thực và contention.

**40.** Quy tắc nhớ lâu nhất? — **Cùng name: đồng bộ một class definition; khác name: cho phép tải song song, nhưng mọi shared state phải thread-safe**.

## 22. Nguồn chính thức Java SE 17

- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): mô hình parent delegation, `loadClass`, `findClass`, `getClassLoadingLock`, `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `defineClass`.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class identity, defining loader, `Class.forName(name,initialize,loader)`.
- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): state/caches thread-safe.
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ điều kiện overlap trong kiểm thử.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit concurrent tasks, Future, shutdown và awaitTermination.
- [Java Language Specification §12.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): loading of classes/interfaces.
- [Java Virtual Machine Specification §5.3](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): creation/loading và class loader namespace.

**Ghi nhớ cuối:** Một subclass `ClassLoader` muốn nạp song song phải gọi `registerAsParallelCapable()` trong static initializer **trước khi có instance**, và toàn bộ các lớp cha trong chuỗi cũng phải registered. Với `loadClass` mặc định, loader chưa đăng ký dùng khóa toàn loader; loader registered dùng `getClassLoadingLock(name)` để các tên khác nhau có thể được xử lý đồng thời, còn cùng tên tránh định nghĩa trùng. **Ưu tiên override `findClass`**, giữ parent delegation và loaded-check của JDK. Registration chỉ thay mô hình đồng bộ khi nạp class; mọi map, bytecode arrays, cache và callbacks trong subclass vẫn cần được thiết kế thread-safe. Parallel class loading không đồng nghĩa class initialization song song vô điều kiện, không loại bỏ mọi deadlock và không tạo sandbox để chạy mã không tin cậy.