# Khóa nạp lớp trong triển khai mặc định của ClassLoader

> **Phạm vi:** Java Core → ClassLoader → Nạp đồng thời. Bài học giải thích vì sao JVM cần đồng bộ khi nhiều thread cùng yêu cầu một lớp, đường đi khóa mặc định của `ClassLoader.loadClass(String, boolean)`, vai trò của `getClassLoadingLock(String)`, sự khác biệt giữa loader thường và *parallel-capable loader*, cùng các trường hợp deadlock, race condition và lỗi `LinkageError` khi tự viết loader. Ví dụ biên dịch với Java 17+.

## 1. Bài toán: hai thread cùng load một tên lớp

Giả sử một chương trình có một custom loader `L`, và hai thread gần như đồng thời gọi:

```java
// Hai lời gọi trên cùng ClassLoader instance L:
L.loadClass("demo.Widget");
L.loadClass("demo.Widget");
```

Nếu đường nạp không được đồng bộ đúng, cả hai thread có thể:

1. Cùng kiểm tra rằng chưa có `demo.Widget`.
2. Cùng đọc `demo/Widget.class` từ disk/JAR.
3. Cùng định gọi `defineClass("demo.Widget", ...)` bằng **cùng defining loader**.
4. Một thread định nghĩa trước; thread kia cố định nghĩa lại cùng binary name và có thể gây **`LinkageError`: duplicate class definition**.

JVM xác định một lớp/interface thông thường bằng cặp **(binary name, defining loader)**. Không thể có hai định nghĩa khác nhau cùng binary name được đăng ký ở **cùng defining loader**, kể cả bytecode của hai lần đọc giống nhau.

Đồng thời, JVM cần cho phép nhiều thread truy cập một lớp đã nạp và nhận lại **cùng object `Class<?>`**. Đó là lý do đường `loadClass` chuẩn có bước kiểm tra class đã được ghi nhận, parent delegation, tìm bytes và đồng bộ theo **class-loading lock**.

**Ý chính:** Không phải mọi việc liên quan tới JVM đều bị khóa toàn cục; khóa mà Java `ClassLoader` dùng phụ thuộc loader có được đăng ký *parallel-capable* hay không.

## 2. Đường đi chuẩn của ClassLoader.loadClass

Hai API:

```java
public Class<?> loadClass(String name) throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;
```

Overload public gọi logic tương đương `loadClass(name, false)`. Trong **triển khai mặc định** của overload protected, Javadoc mô tả luồng xử lý như sau:

```text
loadClass("demo.Widget", resolve)
           |
           v
synchronized (getClassLoadingLock("demo.Widget"))
           |
           +--> findLoadedClass("demo.Widget")
           |        |
           |        '--> đã có -> tái sử dụng Class<?> tương ứng
           |
           +--> nếu chưa có, thử parent.loadClass("demo.Widget")
           |        |
           |        '--> parent tìm được -> dùng Class<?> do parent trả
           |
           +--> nếu parent không tìm được, gọi findClass("demo.Widget")
           |        |
           |        '--> subclass tìm bytes và defineClass(...)
           |
           +--> nếu resolve == true: resolveClass(result)
           |
           '--> return Class<?>
        (nhả class-loading lock)
```

Đây là trình tự khái quát theo Java SE 21 `ClassLoader.loadClass(String, boolean)`. Điều quan trọng nhất là khóa bao phủ **toàn bộ chu trình tìm class trong implementation mặc định**, không chỉ câu lệnh `defineClass`.

### Ý nghĩa từng bước

- `getClassLoadingLock(name)`: trả về object để đồng bộ hóa việc load lớp có tên `name`.
- `findLoadedClass(name)`: kiểm tra lớp đã được JVM ghi nhận là tải bởi loader theo semantics của API; nếu có thì không định nghĩa lại.
- **Parent delegation:** hỏi parent trước để giữ các lớp nền tảng và lớp chia sẻ có định danh nhất quán trong chính sách mặc định.
- `findClass(name)`: điểm mở rộng được khuyến nghị cho subclass; đọc class bytes từ nguồn của custom loader và gọi `defineClass`.
- `resolveClass(clazz)`: nếu requested, kích hoạt linking theo hợp đồng method. **Không đồng nghĩa tự chạy static initializer.**

Javadoc nhấn mạnh: **trừ khi bị override**, `loadClass(String, boolean)` đồng bộ trên kết quả của `getClassLoadingLock` trong suốt quá trình tải. Nếu subclass override toàn bộ `loadClass`, nó có trách nhiệm duy trì logic tìm lớp, synchronization, deadlock safety và Java type identity phù hợp.

## 3. Class-loading lock không luôn là chính ClassLoader

Method:

```java
protected Object getClassLoadingLock(String className);
```

Theo Java SE 21:

| Loại ClassLoader instance | Giá trị `getClassLoadingLock(name)` |
| --- | --- |
| **Không được đăng ký parallel-capable** | **Chính object loader (`this`)**, dùng chung cho mọi tên. |
| **Được đăng ký parallel-capable** | **Một khóa gắn với tên lớp cụ thể** cho loader ấy. |

Sơ đồ:

```text
Non-parallel loader L:
    getClassLoadingLock("demo.A") --> L
    getClassLoadingLock("demo.B") --> L
    getClassLoadingLock("demo.C") --> L
                                    cùng một monitor

Parallel-capable loader P:
    getClassLoadingLock("demo.A") --> lock[A]
    getClassLoadingLock("demo.B") --> lock[B]
    getClassLoadingLock("demo.A") --> lock[A]
                                    khác tên khác lock,
                                    cùng tên cùng lock
```

Với non-parallel loader, nhiều thread load **hai lớp khác tên** trên cùng loader vẫn phải chờ cùng monitor nếu dùng triển khai `loadClass` mặc định. Đơn giản nhưng có thể hạn chế throughput.

Với parallel-capable loader, các request **khác tên** có thể đi qua phần load của cùng loader đồng thời. Tuy nhiên, thread cần tải **cùng tên** vẫn đồng bộ trên cùng lock để không double-define.

**Cần hiểu đúng giới hạn:** parallel-capable là *khả năng cho phép* concurrency ở cấp khóa tên lớp, không phải bảo đảm mọi công việc load sẽ thực sự chạy song song với tốc độ tối đa. Disk I/O, parent loader, package metadata, filesystem, network, JVM linking và các khóa khác vẫn có thể gây contention.

### Quan sát getClassLoadingLock từ subclass

Vì `getClassLoadingLock` là `protected`, có thể tạo method wrapper phục vụ chẩn đoán trong subclass:

```java
class DiagnosticLoader extends ClassLoader {
    Object lockFor(String className) {
        return getClassLoadingLock(className);
    }
}
```

Đây là **class có thể biên dịch**, nhưng thiếu `main`. Đừng xuất public lock object vào API sản phẩm để các caller tùy ý khóa lâu; nó có thể làm các request tải lớp khác bị tắc hoặc tạo deadlock.

## 4. Parallel-capable ảnh hưởng gì tới khóa mặc định?
Một subclass `ClassLoader` **chưa đăng ký** dùng khóa chung `this`; loại **parallel-capable** dùng lock theo binary name và có thể tải các tên khác nhau đồng thời. Đăng ký qua `registerAsParallelCapable()` trong static initializer **của từng subclass**, trước khi có instance, và yêu cầu toàn bộ superclass loader cũng đã đăng ký. Kiểm tra `isRegisteredAsParallelCapable()` để tránh giả định sai.
Ví dụ `ParallelLoader` ngay dưới đây cho thấy đầy đủ: cùng tên giữ một khóa ổn định, tám threads trả cùng `Class<?>`, `findClass` chỉ cần định nghĩa một lần. Việc đăng ký **không tự làm an toàn** `HashMap`, I/O stream, package metadata hay code `loadClass` do bạn override. Bài riêng về `registerAsParallelCapable` phân tích sâu quy tắc superclass, caller và thời điểm.

## 5. Ví dụ chạy được trên Java 17+: quan sát lock và 8 thread nạp cùng một lớp

Thí nghiệm tạo một `SerialLoader` không đăng ký parallel-capable và một `ParallelLoader` có đăng ký. Cả hai đều kế thừa trực tiếp `ClassLoader`, nên không bị ảnh hưởng bởi implementation của application loader.

`ParallelLoader` override **`findClass`**, không override `loadClass`. Nhờ đó khóa chuẩn của Java SE vẫn bao phủ kiểm tra đã tải, parent delegation và định nghĩa mới.

### Cấu trúc nguồn

```text
src/
  demo/
    Widget.java
  app/
    LoadingLockDemo.java
plugin-classes/    (javac tạo)
app-classes/       (javac tạo)
```

**File `src/demo/Widget.java`:**

```java
package demo;

public class Widget {
    public int answer() {
        return 42;
    }
}
```

**File `src/app/LoadingLockDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class LoadingLockDemo {
    static class SerialLoader extends ClassLoader {
        SerialLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Registration failed");
            }
        }

        private final Path root;
        final AtomicInteger findCalls = new AtomicInteger();

        ParallelLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            findCalls.incrementAndGet();

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(
                                binaryName.replace('.', '/') + ".class"));
                return defineClass(
                        binaryName, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel =
                new ParallelLoader(Path.of("plugin-classes"));

        System.out.println("serial registered: "
                + serial.isRegisteredAsParallelCapable());
        System.out.println("serial same lock for A/B: "
                + (serial.lockFor("demo.A")
                        == serial.lockFor("demo.B")));
        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());
        System.out.println("parallel same lock for A/B: "
                + (parallel.lockFor("demo.A")
                        == parallel.lockFor("demo.B")));
        System.out.println("parallel same lock for A: "
                + (parallel.lockFor("demo.A")
                        == parallel.lockFor("demo.A")));

        int requests = 8;
        CountDownLatch start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(requests);
        try {
            List<Future<Class<?>>> tasks = new ArrayList<>();
            for (int i = 0; i < requests; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    return parallel.loadClass("demo.Widget");
                }));
            }

            start.countDown();
            Class<?> first = tasks.get(0).get();

            boolean same = true;
            for (Future<Class<?>> task : tasks) {
                same &= task.get() == first;
            }

            System.out.println("requests: " + requests);
            System.out.println("one Class object: " + same);
            System.out.println("findClass calls: "
                    + parallel.findCalls.get());
            System.out.println("defining loader matches: "
                    + (first.getClassLoader() == parallel));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

### Biên dịch và chạy

Từ thư mục gốc chứa `src`, chạy:

```bash
javac --release 17 -d plugin-classes src/demo/Widget.java
javac --release 17 -d app-classes src/app/LoadingLockDemo.java
java -cp app-classes LoadingLockDemo
```

**Stdout đã được biên dịch bằng `--release 17` và kiểm chứng trên OpenJDK 24:**

```text
serial registered: false
serial same lock for A/B: true
parallel registered: true
parallel same lock for A/B: false
parallel same lock for A: true
requests: 8
one Class object: true
findClass calls: 1
defining loader matches: true
```

### Giải thích từng dòng

1. `SerialLoader` không gọi `registerAsParallelCapable`: trạng thái `false`. Hai tên `demo.A`, `demo.B` cùng dùng monitor của instance `serial`, nên phép so sánh `==` là `true`.
2. `ParallelLoader` gọi đăng ký trong static initializer trước khi được tạo: trạng thái `true`. Hai tên khác nhau dùng hai lock khác nhau; gọi lại cùng tên trả cùng lock.
3. `plugin-classes` **không nằm trong `-cp app-classes`; parent platform loader không định nghĩa `demo.Widget` từ nơi đó. Vì vậy `ParallelLoader.findClass` thực sự đọc bytes và tạo class.
4. `CountDownLatch` làm tám task sẵn sàng rồi đồng thời được phép gọi `parallel.loadClass("demo.Widget")`. Trình lập lịch có thể chạy chúng ở những thời điểm khác nhau; ta **không dựa trên timing** để khẳng định mức song song.
5. Vì cùng loader + cùng binary name, khóa theo tên, `findLoadedClass` và `defineClass` phối hợp để kết quả mọi task là **chính một `Class<?>`**, còn `findClass` chỉ được gọi **một lần trong cấu hình này**.
6. `first.getClassLoader() == parallel` chứng minh custom loader là **defining loader** trong ví dụ. Nếu parent đã chứa `demo.Widget`, kết quả cần diễn giải khác.

**Quan trọng:** test này chứng minh behavior của khóa và việc nạp một tên an toàn. Nó **không** đo tốc độ hay chứng minh `findClass` của hai tên khác nhau luôn chạy song song; muốn đo cần benchmark được kiểm soát.

## 6. Tại sao hai luồng cùng tên không tự tạo hai Class<?>?

Bên trong `loadClass` mặc định, `synchronized (getClassLoadingLock(name))` bảo vệ chuỗi *check–delegate–find–define*.

Một lịch trình minh họa:

```text
Thread A                              Thread B
--------                              --------
lock("demo.Widget") acquired          waits for same lock
findLoadedClass -> null
parent lookup -> missing
findClass -> defineClass -> C
return C; release lock
                                      acquire same lock
                                      findLoadedClass -> C
                                      return C; release lock
```

Mấu chốt là **kiểm tra lại dưới khóa**. Chỉ kiểm tra `findLoadedClass` ở ngoài khóa, sau đó gọi `defineClass` không đồng bộ, là pattern time-of-check/time-of-use dễ phát sinh race.

Với loader parallel-capable, khóa theo tên bảo vệ từng class riêng. Hai tên `demo.Widget` và `demo.Helper` có khóa khác nhau; điều đó không miễn trừ nhu cầu đồng bộ **trạng thái chia sẻ** ở nơi khác:

- Cùng một archive/JAR reader với state mutable.
- Cache ánh xạ resource, metadata package hoặc verification result.
- `definePackage` cho hai class khác tên nhưng **cùng package**.
- Global bytecode transform pipeline, generator cache và class signers.
- Tham chiếu chéo giữa plugin loaders tạo delegation graph.

Nên phân biệt **class-loading lock** của base class với các mutex khác do bạn tự thiết kế. Một loader đã parallel-capable mà `findClass` không thread-safe vẫn có thể lỗi.

## 7. Override findClass, không vội override loadClass

Khuyến nghị của Javadoc: các subclass phù hợp với delegation model thường nên override `findClass` để cung cấp nguồn bytecode mới.

Mẫu tối giản:

```java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    byte[] bytes = obtainVerifiedClassBytes(binaryName);
    if (bytes == null) {
        throw new ClassNotFoundException(binaryName);
    }
    return defineClass(binaryName, bytes, 0, bytes.length);
}
```

Đây là **snippet** đặt trong `ClassLoader` subclass, với `obtainVerifiedClassBytes` là helper phụ thuộc repository/bộ đọc JAR của ứng dụng. Nó không tự biên dịch độc lập.

Ưu điểm:

- `loadClass` mặc định xử lý `getClassLoadingLock` và `findLoadedClass`.
- Parent delegation đã có theo mô hình Java chuẩn.
- `resolveClass` được gọi đúng khi overload protected được dùng với `resolve=true`.
- Subclass chỉ tập trung đọc bytes đúng tên và gọi `defineClass`.

Nếu override `loadClass` để đổi sang child-first, bạn phải tự kiểm tra `findLoadedClass` và tự khóa đồng bộ đúng trước khi định nghĩa. Một ví dụ pseudocode cấu trúc an toàn:

```java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);
        if (c == null) {
            // Cài đặt chính sách delegation/fallback hợp lệ tại đây:
            // bảo đảm không define trùng tên và bảo vệ namespaces.
            c = super.loadClass(name, false);
        }
        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
```

Đây là **snippet minh họa**, không phải template child-first hoàn chỉnh. Trên thực tế, với `super.loadClass`, parent-first vẫn áp dụng; muốn child-first phải thiết kế đầy đủ thứ tự nguồn riêng, xử lý protected namespace và các lỗi liên kết. Không copy rồi tưởng đã thay đổi strategy.

Một nguy cơ khác: nếu subclass **cố tình override `loadClass` không đồng bộ**, hợp đồng khóa mặc định của superclass **không tự đảm bảo** độ an toàn cho code override đó.

## 8. Khi ủy quyền chéo có thể gây deadlock
Nếu thread T1 đang giữ monitor loader A rồi đợi loader B, còn T2 đang giữ B rồi đợi A, tạo vòng chờ và deadlock. Khóa theo từng tên class ở loader parallel-capable **giảm những vòng chờ do khóa toàn loader**, nhưng không ngăn mọi dependency cycle. Bài **Deadlock khi nhiều loader ủy quyền chéo** có ví dụ hai loader, thread dump và cách loại bỏ vòng chờ; ở đây cần nhớ không tự giữ `synchronized(this)` quanh các lời gọi sang loader khác.

## 9. Class loading lock không phải khóa khởi tạo lớp

Các giai đoạn cần phân biệt:

| Giai đoạn | Điều gì diễn ra | Khóa nào liên quan? |
| --- | --- | --- |
| **Loading** | Tìm/định nghĩa `Class<?>` từ binary name/bytes. | `ClassLoader.loadClass` mặc định dùng `getClassLoadingLock`. |
| **Linking** | Verification, preparation, resolution theo quy tắc JVM. | JVM có cơ chế riêng; `resolveClass` không phải gọi static initializer. |
| **Initialization** | Chạy `<clinit>` gồm static field initializers/static blocks. | JVM dùng **initialization lock/protocol** cho từng class theo JVMS `5.5. |

Không suy luận rằng hai thread gọi `Class.forName("demo.Widget")` và static initializer chỉ chạy một lần **chỉ do** `getClassLoadingLock`. JVM có cơ chế đồng bộ khởi tạo lớp **riêng**. Đặc biệt, `Class.forName(name, false, loader)` yêu cầu load/link theo API nhưng **không yêu cầu initialization**; `Class.forName(name)` thông thường có thể kích hoạt initialization.

Vì thế:

- Một class có thể đã load nhưng chưa initialized.
- Một class có thể đang initializing trong thread khác; JVM phải phối hợp theo quy tắc `<clinit>`.
- Deadlock liên quan static initializers không được chữa chỉ bằng đăng ký parallel-capable loader.
- Việc monitor theo class name không phải monitor dùng cho toàn bộ method `static synchronized` của class.

Đây là lý do khi debug hang cần biết thread đang kẹt tại **loader delegation/defineClass** hay **class initialization**.

## 10. Race condition ở custom loaders: những lỗi cần phòng

| Thiết kế sai | Điều có thể xảy ra | Cách làm đúng |
| --- | --- | --- |
| Bỏ `synchronized(getClassLoadingLock(name))` khi override `loadClass` | Hai thread cùng `defineClass` một tên → `LinkageError`. | Dùng implement mặc định hoặc khóa theo tên chính xác. |
| Chỉ kiểm tra `findLoadedClass` ở ngoài khóa | Race giữa check và define. | Check và define dưới cùng lock cho tên ấy. |
| Subclass đăng ký parallel-capable nhưng share `HashMap` mutable không đồng bộ | Lỗi race/corruption cache. | Dùng concurrent collections và chính sách visibility phù hợp. |
| Hai tên class khác nhau cùng gọi `definePackage` | Package có thể bị define hai lần → `IllegalArgumentException`. | Đồng bộ state theo package; xác minh metadata/sealing. |
| Dùng một `InputStream`/`JarFile` có thao tác mutable từ nhiều threads mà không có contract thread-safe | Đọc nhầm/cắt bytes hoặc lỗi tài nguyên. | Tách stream, đồng bộ theo nguồn hoặc sử dụng API quản lý concurrency. |
| Gọi sang loader khác trong khi giữ nhiều lock không có thứ tự | Circular wait/deadlock. | Thiết kế DAG delegation hoặc thứ tự lấy khóa rõ ràng. |
| `registerAsParallelCapable` ở subclass nhưng superclass chưa đăng ký | Đăng ký trả false. | Đăng ký đúng từ từng lớp hierarchy. |
| Gọi `registerAsParallelCapable` quá muộn | Đăng ký thất bại vì đã tạo instance. | Thực hiện ở class initialization trước constructor. |
| Tự khóa vào một `new Object()` mỗi lần gọi load | Không hề phối hợp giữa các thread. | Dùng ổ khóa ổn định theo loader/tên. |
| Dùng tên resource path `demo/Widget.class` thay binary name `demo.Widget` | Sai lookup/định nghĩa. | Phân biệt binary name và path trong archive. |

### Không tự gán mọi LinkageError cho double-define

`LinkageError` có nhiều nguyên nhân: loading constraint violation, incompatibility giữa phiên bản thư viện, `NoSuchMethodError`, `ClassFormatError` (subclass của `LinkageError`), duplicate class definition, v.v. Đọc exception message/stack trace trước khi kết luận do race.

Chạy nhiều thread mà **không thấy exception** cũng chưa chứng minh loader thread-safe; bug concurrency có thể phụ thuộc timing, nguồn I/O và thứ tự scheduler.

## 11. Mẫu chuẩn cho loader có nhiều nguồn bytes

Một custom loader phục vụ plugin lớn thường cần những quy tắc sau:

**A. Ownership rõ ràng.** Một loader instance là một không gian tên class và tài nguyên. Đừng chia sẻ trạng thái mutable trên nhiều loader instance nếu không có lý do.

**B. Chỉ override điểm mở rộng cần thiết.** Khi policy vẫn parent-first, ưu tiên `findClass`. Tránh override `loadClass` chỉ để đọc từ database/directory.

**C. Đăng ký parallel-capable có chủ đích.** Nếu throughput hoặc mô hình delegation cần load khác tên đồng thời, dùng `registerAsParallelCapable` **kèm review toàn bộ thread-safety**. Với loader đơn giản, non-parallel có thể dễ suy luận và đủ nhanh.

**D. Lock ngoài lớp là riêng biệt.** Package metadata, cache, JAR handle và class generator cần đồng bộ đúng theo chia sẻ dữ liệu. Không phụ thuộc khóa loader bao trùm toàn bộ khi đã parallel-capable.

**E. Kiểm soát thứ tự parent/plugin.** Một lớp tên trùng ở parent có thể được parent trả về; `Class<?>` trả ra có defining loader là parent, không phải loader đang gọi `loadClass`.

**F. Lỗi phải được phân loại.** `ClassNotFoundException` khi không có class; `IOException` đọc bytes được bọc với cause; `LinkageError` duplicate/incompatibility; `VerifyError` verifier; `ExceptionInInitializerError` ở initialization là giai đoạn khác.

**G. Kiểm tra cả load trùng tên và khác tên.** Test cùng tên để chứng minh không double-define, test khác tên để xem lock contention/các cache, test parent delegation và nhiều loader có dependency cross-reference.

**H. Đừng tắt an toàn để tối ưu sớm.** Mục tiêu là correctness trước; chỉ sau đó đo contention bằng thread dump/JFR/profiling rồi mới tối ưu.

## 12. Debug hang khi ClassLoader tải đồng thời

Khi ứng dụng đứng yên lúc startup hoặc khi kích hoạt plugin:

1. **Lấy thread dump** bằng công cụ JDK phù hợp, ví dụ `jcmd <pid> Thread.dump_to_file -format=text dump.txt` (cú pháp/capability có thể khác phiên bản), hoặc `jstack <pid>` trên JVM có hỗ trợ.
2. Nhìn các thread ở `BLOCKED`/`WAITING` trong `ClassLoader.loadClass`, `getClassLoadingLock`, `findClass`, I/O và `<clinit>`. Không chỉ tìm chuỗi `ClassNotFoundException`.
3. Nếu thread A giữ loader A lock và chờ loader B, trong khi B đợi A, vẽ delegation graph và monitor owner/waiters.
4. Kiểm tra `loader.isRegisteredAsParallelCapable()` và hierarchy thực tế; không suy từ tên class loader là “parallel”.
5. Nếu hai thread cùng tên lớp, xem có override `loadClass` bỏ khóa không; nếu có double-define, tìm stack tại `defineClass` và đường `findLoadedClass`.
6. Nếu khác tên nhưng cùng package, kiểm tra race trong `definePackage`, sealing và shared caches.
7. Nếu static initializer đang chờ, phân biệt **JVM initialization protocol** với monitor của loader; tránh chữa sai bằng `registerAsParallelCapable`.
8. Test tái hiện bằng chương trình tối giản, dùng `CountDownLatch`/`CyclicBarrier` để kích hoạt gần nhau, so sánh `Class<?>` bằng `==` và đếm `findClass` calls.
9. Giữ biểu đồ lock graph đơn giản và loại bỏ cycle; tuyệt đối không ép `Thread.stop()` để “giải” deadlock trong production.

Các kết quả của `ThreadMXBean.findDeadlockedThreads` có thể hỗ trợ chẩn đoán một số deadlock liên quan monitor/synchronizer, nhưng không thay thế phân tích I/O và dependency graph; thread không hoàn thành có thể đang chờ mạng/disk thay vì deadlock.

## 13. Các câu hỏi tự kiểm tra

1. **Với loader không parallel-capable, `getClassLoadingLock("A") == getClassLoadingLock("B")` là gì?**  
   `true`: method trả chính instance loader.
2. **Với loader đã parallel-capable, hai tên khác nhau dùng chung lock?**  
   Không theo implementation requirements; khóa được gắn với tên lớp. Cùng tên trên cùng loader nhận cùng lock.
3. **`ClassLoader` gốc đã parallel-capable, vậy subclass trực tiếp có tự parallel-capable?**  
   Không. Subclass phải đăng ký nếu muốn hỗ trợ.
4. **Đăng ký parallel-capable lúc nào?**  
   Trong quá trình initialization của class loader subclass, trước khi có instance, và mọi superclass ClassLoader cần đã đăng ký.
5. **Tám thread gọi `loader.loadClass("demo.Widget")` đồng thời, có hợp lệ tạo tám `Class<?>` ở cùng defining loader?**  
   Không; phải tái sử dụng class identity. Trong demo cả tám trả một object và `findClass` chỉ chạy một lần.
6. **Loader parallel-capable có tự làm mọi `HashMap` shared thread-safe?**  
   Không; phải đồng bộ state application riêng.
7. **Nên override `loadClass` hay `findClass` khi chỉ muốn nguồn class bytes từ thư mục riêng?**  
   Thường `findClass`; giữ logic khóa và parent delegation của `loadClass` mặc định.
8. **`synchronized(getClassLoadingLock(name))` có bảo đảm static initializer chỉ chạy một lần?**  
   Không phải trực tiếp; JVM có initialization lock/protocol riêng cho class.
9. **Tại sao non-hierarchical delegation dễ deadlock với non-parallel loader?**  
   Mỗi thread có thể giữ monitor toàn loader rồi chờ monitor loader khác theo chu trình.
10. **Đăng ký parallel-capable có loại bỏ mọi deadlock?**  
    Không; lock theo tên khác nhau vẫn có thể tạo circular wait.
11. **`resolveClass` có chạy constructor hoặc static block không?**  
    Không theo nghĩa initialization; nó phục vụ linking.
12. **Vì sao không nên tự khóa `synchronized(this)` trong mọi loader parallel-capable?**  
    Nó có thể đưa coarse lock quay lại, phá lợi ích nạp khác tên đồng thời và tăng rủi ro deadlock.

## 14. Tài liệu chuẩn

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getClassLoadingLock`, `findLoadedClass`, `findClass`, `registerAsParallelCapable` và `isRegisteredAsParallelCapable`.
- [Java SE 21 — Concurrent programming / java.util.concurrent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html): `CountDownLatch`, `ExecutorService`, `Future`, synchronization.
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): defining vs initiating loader và runtime type identity.
- [JVMS §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): class initialization synchronization/protocol riêng.
- [JLS Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): loading, linking và initialization.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): API hỗ trợ chẩn đoán monitor deadlocks.
