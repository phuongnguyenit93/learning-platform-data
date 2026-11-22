# Phân biệt khóa nạp lớp với khóa khởi tạo lớp trong Java

Khi nhiều thread đồng thời sử dụng một class, Java cần xử lý hai vấn đề khác nhau: **không cho hai thread định nghĩa trùng một class trong cùng class loader**, và **không cho nhiều thread thực thi static initializer của cùng runtime class một cách độc lập**. Hai vấn đề này được giải quyết bằng **khóa nạp lớp** và **cơ chế khóa khởi tạo lớp** — chúng có liên quan tới vòng đời class nhưng **không phải cùng một lock**.

- **Class-loading lock** thuộc cơ chế của `java.lang.ClassLoader`, thường được lấy qua `getClassLoadingLock(String name)` trong `loadClass`. Nó điều phối `findLoadedClass`, parent delegation và `findClass/defineClass`, đặc biệt khi nhiều threads yêu cầu cùng binary name.
- **Class-initialization lock `LC`** được Java Language Specification `12.4.2 mô tả là khóa nội bộ **theo từng runtime class hoặc interface `C`**. JVM dùng nó để điều phối trạng thái `not initialized / initializing / initialized / erroneous` và việc chạy `<clinit>`. Không có API công khai để ứng dụng lấy `LC` như một `java.util.concurrent.locks.Lock`.

**Điểm cần nhớ ngay:** `ClassLoader.loadClass(...)` thông thường **không yêu cầu static initialization**; `Class.forName(name, true, loader)`, gọi static method hoặc tạo instance có thể yêu cầu initialization. Việc một loader được đăng ký **parallel-capable** giúp nạp những *tên class khác nhau* song song, nhưng không khiến **`<clinit>` của cùng runtime class** chạy hai lần.

Bài học thuộc **Java core – classloader / Nạp đồng thời**, dùng ví dụ Java 17+ có thể biên dịch/chạy, bảng so sánh, mô hình trạng thái JVM và những tình huống deadlock/initialization lỗi thường gặp.

## 1. Hai loại khóa bảo vệ hai bất biến khác nhau

| Góc nhìn | Khóa nạp lớp | Khóa khởi tạo lớp |
| --- | --- | --- |
| Mục tiêu | Không có lookup/định nghĩa trùng gây race trong một loader | Phối hợp đúng một quá trình initialization cho mỗi runtime class/interface |
| Phạm vi | Class loader instance; lock có thể chung mọi tên hoặc riêng cho mỗi binary name | Một runtime `Class<?>`/interface `C` và trạng thái initialization do JVM quản lý |
| API/đặc tả | `ClassLoader.getClassLoadingLock` và `loadClass` | JLS §12.4.2 với khóa `LC` |
| Khi được dùng | Trong đường xử lý loading/delegation của loader | Khi active use cần initialize class chưa initialized |
| Loader parallel-capable ảnh hưởng? | Có: thường có locks theo tên class | Không: JVM vẫn giữ semantics initialization |
| Có bảo vệ mọi dòng `static { ... }`? | Không | Khóa dùng cho điều phối trạng thái; không nhất thiết được giữ suốt body `<clinit>` |
| Lỗi đặc trưng | `ClassNotFoundException`, `LinkageError` khi lookup/definition/linking | `ExceptionInInitializerError`, class erroneous, active use sau có `NoClassDefFoundError` |
| Ai điều khiển? | Tác giả subclass loader có thể ảnh hưởng cách lấy lock khi override `loadClass` | JVM, theo JLS/JVMS; ứng dụng không được thay trực tiếp |

**Đừng nhầm khóa nạp lớp với monitor của `Class<?>` object.** `synchronized (SomeClass.class)` khóa một monitor mà Java code nhìn thấy; đặc tả không bảo đảm object monitor đó chính là `LC` nội bộ cho mọi JVM/optimization.

### Một dòng thời gian có hai cơ chế

```text
T1 cần demo.Widget
  │
  ├── Loading: loader.lookup / defineClass
  │       └── class-loading lock phối hợp khi nhiều threads cùng nạp
  │
  ├── Linking: verification / preparation / resolution
  │
  └── Active use: demo.Widget.perform()
          └── JVM kiểm tra trạng thái initialization của Widget
                ├── thread khác đang initialize → đợi
                ├── chưa initialize → thread này chạy <clinit>
                └── đã initialized → sử dụng bình thường
```

Các bước JVM có thể đan xen hoặc trì hoãn một số resolution; sơ đồ nhấn mạnh **mục đích và ranh giới**, không áp một thứ tự giữ khóa cứng cho mọi JVM.

## 2. Nhắc lại loading, linking, initialization và constructor

**Loading:** xác định class theo **binary name và defining loader**, đọc/định nghĩa bytecode nếu cần và có đối tượng `Class<?>`. Với cùng binary name trong cùng defining loader, JVM không cho `defineClass` hợp lệ diễn ra lần thứ hai như một class mới.

**Linking:** verification, preparation, resolution theo JVM specification. Preparation chuẩn bị static fields với giá trị mặc định và các cơ chế riêng cho constant values. Linking không đồng nghĩa body `static { ... }` đã chạy.

**Initialization:** thực thi các static field initializers và static initializer blocks (class initialization method `<clinit>` khi compiler/JVM cần) theo Java rules. Chỉ một quá trình initialization thành công cho mỗi runtime class.

**Instantiation:** tạo instance bằng `new` hoặc reflective constructor. Instance constructor (`<init>`) không phải `<clinit>`. Sau khi class được initialized, rất nhiều instances có thể được tạo đồng thời; `LC` không serialize mọi constructor về sau.

Ví dụ:

```java
ClassLoader loader = Example.class.getClassLoader();
Class<?> type = loader.loadClass("demo.Widget");
Class<?> noInit = Class.forName("demo.Widget", false, loader);
Class<?> initialized = Class.forName("demo.Widget", true, loader);
```

Đây là **snippet minh họa** cần class `Example`, `demo.Widget` và xử lý `ClassNotFoundException`. Hai lời gọi đầu **không bắt buộc static initializer chạy**; lời gọi cuối có `initialize=true` yêu cầu initialization trước khi trả về thành công. Cả ba trả `Class<?>`, không tự tạo instance của `Widget`.

## 3. Khóa nạp lớp bảo vệ giai đoạn nào?
Trong triển khai mặc định, `ClassLoader.loadClass(name, resolve)` giữ `getClassLoadingLock(name)` khi kiểm tra `findLoadedClass`, delegation lên parent/bootstrap, gọi `findClass` nếu cần và `resolveClass` khi yêu cầu. Đường này đảm bảo loader không tự định nghĩa trùng một tên dưới concurrent requests.
**`loadClass` không tự yêu cầu chạy `<clinit>`**. Nếu JVM sau đó cần initialize runtime class, nó sử dụng thủ tục và trạng thái `LC` riêng như §7. Chẩn đoán phải tách lỗi loading/linking khỏi lỗi initialization.

## 4. Parallel-capable chỉ thay khóa của loader
Loader chưa đăng ký dùng monitor `this` cho mọi tên; loader registered parallel-capable dùng lock riêng theo tên. Điều này cho phép nhiều tên được load đồng thời nhưng không làm thay đổi trạng thái initialization theo runtime `Class<?>`. `registerAsParallelCapable` phải được gọi từ static initializer của subclass khi toàn bộ superclass loader đã registered. Thí nghiệm A kiểm chứng đối tượng khóa, còn B chứng minh cùng một tên được định nghĩa một lần.

## 5. Thực hành A — kiểm tra object của class-loading lock

Cấu trúc:

```text
lock-scope-lab/
└── src/demo/LockScopeDemo.java
```

**`src/demo/LockScopeDemo.java`:**

```java
package demo;

public final class LockScopeDemo {
    static final class SerialLoader extends ClassLoader {
        SerialLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        boolean same(String a, String b) {
            return getClassLoadingLock(a) == getClassLoadingLock(b);
        }

        boolean lockIsLoader(String name) {
            return getClassLoadingLock(name) == this;
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Parallel registration failed");
            }
        }

        ParallelLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        boolean same(String a, String b) {
            return getClassLoadingLock(a) == getClassLoadingLock(b);
        }
    }

    public static void main(String[] args) {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel = new ParallelLoader();

        System.out.println("serial same A/B: " +
                serial.same("demo.A", "demo.B"));
        System.out.println("serial lock is loader: " +
                serial.lockIsLoader("demo.A"));
        System.out.println("parallel different A/B: " +
                !parallel.same("demo.A", "demo.B"));
        System.out.println("parallel same A/A: " +
                parallel.same("demo.A", "demo.A"));
    }
}
```

Chạy trên **JDK 17+** từ `lock-scope-lab`:

```sh
javac --release 17 -d out src/demo/LockScopeDemo.java
java -cp out demo.LockScopeDemo
```

**Stdout dự kiến:**

```text
serial same A/B: true
serial lock is loader: true
parallel different A/B: true
parallel same A/A: true
```

Phân tích:

1. `SerialLoader` không đăng ký, nên các tên dùng cùng lock là **instance `serial`**.
2. `ParallelLoader` đăng ký trong static initializer trước khi tạo đối tượng; locks theo hai tên khác nhau có thể khác nhau.
3. Cùng tên trên cùng parallel-capable loader trả lock tương ứng nhất quán.
4. Chương trình chỉ hỏi lock object và so sánh identity; nó **không** nạp `demo.A`, `demo.B` hay chạy static initializers của chúng.
5. `getClassLoadingLock` là API `protected` cho loader implementer; ứng dụng không có cách dùng nó để lấy `LC` JVM.

**Không suy luận:** đăng ký parallel-capable sẽ buộc JVM chạy static blocks đồng thời. Nó chỉ ảnh hưởng synchronization trong hoạt động class loading của loader.

## 6. Thực hành B — hai threads cùng tải một class, chỉ một definition thành công

Ta tạo custom loader với `findClass` đọc bytes từ một output directory không thuộc application classpath. Hai threads cùng gọi `loadClass("payload.Target")` sau latch.

Cây tệp:

```text
load-once-lab/
├── src/payload/Target.java
└── src/demo/LoadOnceDemo.java
```

**`src/payload/Target.java`:**

```java
package payload;

public final class Target {
    public static String message() {
        return "payload";
    }
}
```

**`src/demo/LoadOnceDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class LoadOnceDemo {
    static final class CountingLoader extends ClassLoader {
        final AtomicInteger findCalls = new AtomicInteger();

        CountingLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("payload.Target")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        Path.of("payload-out", "payload", "Target.class"));
                findCalls.incrementAndGet();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountingLoader loader = new CountingLoader();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);

        Callable<Class<?>> task = () -> {
            go.await();
            return loader.loadClass("payload.Target");
        };

        try {
            Future<Class<?>> first = pool.submit(task);
            Future<Class<?>> second = pool.submit(task);
            go.countDown();

            Class<?> a = first.get();
            Class<?> b = second.get();

            System.out.println("same Class: " + (a == b));
            System.out.println("defined by child: " +
                    (a.getClassLoader() == loader));
            System.out.println("findClass calls: " +
                    loader.findCalls.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Biên dịch** từ thư mục `load-once-lab`:

```sh
javac --release 17 -d payload-out src/payload/Target.java
javac --release 17 -d app-out src/demo/LoadOnceDemo.java
```

**Chạy** (chỉ đưa `app-out` lên classpath, không thêm `payload-out`):

```sh
java -cp app-out demo.LoadOnceDemo
```

**Stdout:**

```text
same Class: true
defined by child: true
findClass calls: 1
```

Vì sao?

- Parent là platform loader, nên không nhìn thấy `payload.Target` trong thư mục riêng `payload-out`.
- Hai tasks được khởi động từ cùng latch và cùng yêu cầu một loader instance nạp đúng một binary name.
- `CountingLoader` không đăng ký parallel-capable, nên đường `loadClass` mặc định khóa trên loader.
- Một thread đọc bytes và gọi `defineClass`. Thread kia qua `findLoadedClass` nhận class đã được ghi nhận, không define trùng.
- `findClass calls: 1` xảy ra do lần định nghĩa đầu thành công. Nếu class luôn vắng mặt, nhiều lần lookup thất bại **có thể gọi `findClass` nhiều lần**.
- Chương trình không gọi `Target.message()`; không có lý do coi kết quả là bằng chứng static initializer chạy.

**Lưu ý môi trường:** tất cả các lệnh chạy từ project root vì `Path.of("payload-out",...)` tương đối với working directory. Trên Windows và Linux/macOS, lệnh `java -cp app-out` giống nhau khi chỉ có một mục.

## 7. Khóa `LC` và trạng thái khởi tạo của JVM

JLS §12.4.2 quy định một thủ tục cho mỗi runtime class/interface `C`, cùng khóa initialization `LC`. Mục tiêu của nó là bảo đảm:

1. Nếu `C` **đã initialized**, các active uses không chạy `<clinit>` lại.
2. Nếu `C` **chưa initialized và chưa được thread nào initialize**, một thread được ghi nhận là thread đang thực hiện initialization.
3. Nếu **chính thread đang initialize** lại yêu cầu initialization của `C` đệ quy, thuật toán nhận ra same-thread recursion và không chờ chính mình.
4. Nếu **thread khác** yêu cầu initialization khi `C` đang initializing, thread đó **đợi** kết quả thích hợp thay vì thực thi body `<clinit>` song song.
5. Nếu initialization kết thúc thành công, trạng thái chuyển **initialized** và các threads đang chờ được phép tiếp tục phù hợp.
6. Nếu initialization thất bại, class trở thành **erroneous**; các active uses sau trên cùng runtime class không tự chạy lại initializer.

Mô hình:

```text
C đã load và prepared
          │
          ▼
   not initialized
          │
          ▼
 initializing by thread T
    ┌──────┴────────┐
    │               │
 thành công       thất bại
    │               │
    ▼               ▼
 initialized      erroneous
    │               │
active use sau   active use sau
bình thường      có thể NoClassDefFoundError
```

**Tinh tế nhưng quan trọng:** `LC` được dùng để kiểm tra/cập nhật trạng thái và phối hợp chờ; **JLS không yêu cầu giữ monitor `LC` suốt mọi dòng user code trong static initializer**. JVM implementation được phép tối ưu synchronization miễn semantics và happens-before tương ứng được bảo toàn.

Do đó, `synchronized (C.class)` của ứng dụng **không được xem là giao diện công khai để nắm `LC`**. Nếu cần đồng bộ mutable application state, hãy dùng `synchronized`/`Lock`/atomics của chính ứng dụng.

## 8. Khi nào class initialization được yêu cầu?

Các hoạt động như sau thường là active use:

- `new C()`: tạo instance class `C`.
- `C.staticMethod()`: gọi static method được khai báo bởi `C`.
- Đọc/ghi static field của `C` trong các trường hợp JLS quy định; **đọc constant variable** có thể được inline và không buộc initialize.
- `Class.forName("pkg.C", true, loader)`: yêu cầu initialization.
- Một số reflection operations và JVM bootstrap behaviors được đặc tả.

Những thao tác **không tự yêu cầu initialization** của target theo cách thông thường:

- `loader.loadClass("pkg.C")`.
- `Class.forName("pkg.C", false, loader)`.
- `C.class` hoặc truy cập metadata nhất định.
- Chỉ biết tên class trong constant pool nhưng chưa active-use.

Trong một class hierarchy, initialization superclass và những superinterfaces thích hợp có quy tắc thứ tự riêng. Không coi mọi interface được implement đều chắc chắn initialized chỉ vì class được initialized.

**Không nhầm static constructor với instance constructor:** `<clinit>` nói về initialization của class/interface; `<init>` là constructors được thực thi khi tạo từng instance. Khóa `LC` không tự serialize mọi lời gọi `new C()` sau khi class đã initialized.

## 9. Thực hành C — hai tasks gọi static method nhưng `<clinit>` chỉ chạy một lần

Bài tập này dùng latches để quan sát initialization đang diễn ra. Ta cố ý cho static initializer **đợi main thread** trước khi kết thúc; một worker khác cũng chuẩn bị gọi static method.

Tệp **`src/demo/InitializationDemo.java`:**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class InitializationDemo {
    private static final CountDownLatch INIT_ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch LET_FINISH =
            new CountDownLatch(1);
    private static final CountDownLatch SECOND_READY =
            new CountDownLatch(1);
    private static final AtomicInteger CALLS = new AtomicInteger();

    static final class SlowInit {
        static {
            System.out.println("<clinit>: begin");
            INIT_ENTERED.countDown();
            try {
                LET_FINISH.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new ExceptionInInitializerError(error);
            }
            System.out.println("<clinit>: end");
        }

        static void ping() {
            CALLS.incrementAndGet();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        System.out.println("main: start");
        try {
            Future<?> first = pool.submit(() -> SlowInit.ping());
            INIT_ENTERED.await();

            Future<?> second = pool.submit(() -> {
                SECOND_READY.countDown();
                SlowInit.ping();
            });
            SECOND_READY.await();

            System.out.println("main: release initializer");
            LET_FINISH.countDown();

            first.get();
            second.get();
            System.out.println("method calls=" + CALLS.get());
        } finally {
            LET_FINISH.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy trong một JVM mới bằng JDK 17+:

```sh
javac --release 17 -d out src/demo/InitializationDemo.java
java -cp out demo.InitializationDemo
```

**Stdout:**

```text
main: start
<clinit>: begin
main: release initializer
<clinit>: end
method calls=2
```

Giải thích:

1. Main in `main: start` trước khi submit, nên thông báo này xuất hiện đầu.
2. Worker đầu active-use `SlowInit.ping()` và kích hoạt initialization; `<clinit>` in `begin`, báo cho main rồi đợi latch.
3. Main chỉ tạo worker thứ hai sau khi biết initializer đã bắt đầu. Thread thứ hai sẵn sàng gọi `ping()`, nhưng không được hoàn tất active use không phù hợp khi class còn initializing.
4. Main in `release`, mở latch; initializer in `end` và kết thúc thành công.
5. Hai lời gọi `ping()` cuối cùng đều hoàn tất, nên `CALLS == 2`. Static initializer chỉ thực thi một lần dù có hai tasks.

**Đây không phải cách lấy `LC`.** `CountDownLatch` là synchronization **do chương trình dựng trong body initializer** để tạo các dấu mốc quan sát được. `SECOND_READY` báo thread đã đến ngay trước lệnh gọi; nó **không bảo đảm** đúng tại thời điểm main mở latch thread ấy đã đứng chờ trong cơ chế `LC`. Không viết assertion phụ thuộc trạng thái thread tức thời hoặc `Thread.sleep`.

## 10. Class loading và class initialization có thể nối tiếp trong một thao tác

Một lời gọi:

```java
Class<?> c = Class.forName("demo.Widget", true, loader);
```

có thể yêu cầu cả **loading** lẫn **initialization**:

```text
Nếu Widget chưa được nạp:
    loader lookup và define/link theo quy tắc
    └── class-loading synchronization phù hợp

Khi Widget phải initialized:
    JVM kiểm tra initialization state của runtime Widget
    └── điều phối qua LC theo JLS 12.4.2
        rồi chạy <clinit> khi phù hợp
```

Tuy nhiên **không thể suy ra** “một lock giữ xuyên suốt hai pha”. Hành vi linking/resolution có thể không trùng một timeline cứng và custom loaders có thể làm thêm công việc. Với triển khai mặc định, `loadClass` không tự thực thi `<clinit>` để chuẩn bị ứng dụng.

### Loader locks khác nhau theo instance

Nếu `loaderA` và `loaderB` tự định nghĩa cùng binary name `pkg.C`, chúng có thể có những class-loading locks độc lập. Hai runtime classes được định nghĩa cũng có **initialization states riêng**:

```text
(pkg.C, loaderA) → Class<?> A → trạng thái khởi tạo A
(pkg.C, loaderB) → Class<?> B → trạng thái khởi tạo B
```

Một class cùng tên có thể được initialized một lần **trong mỗi runtime definition**. Đừng mô tả “mỗi binary name chỉ có một `<clinit>` trong cả JVM”.

Nếu `loaderB` hỏi parent và nhận bản `C` do `loaderA` định nghĩa, thì hai callers vẫn sử dụng **cùng Class<?>** và cùng trạng thái initialization. Defining loader mới là thành phần của type identity, không phải loader chỉ được dùng để khởi xướng lookup.

## 11. Same-thread initialization recursion và giá trị static mặc định

JLS còn mô tả trường hợp **thread đang initialize `C` lại yêu cầu initialize `C` lần nữa**. JVM nhận biết cùng thread và không tự chờ chính mình.

Ví dụ **minh họa** (cần một caller active-use để chạy):

```java
class Recursive {
    static int x = compute();

    private static int compute() {
        return Recursive.x;
    }
}
```

Trong preparation, `x` có giá trị mặc định `0`. Khi `compute()` chạy trong initialization, nó có thể đọc `Recursive.x` trước khi phép gán cuối hoàn tất. Yêu cầu initialization đệ quy cùng thread không gây chờ; giá trị trả về có thể đến từ trạng thái preparation/initializers đã chạy một phần.

Điều này chứng minh **thứ tự phụ thuộc static state rất quan trọng**, không có nghĩa JVM khóa toàn bộ class ở một monitor để không ai được đụng đến bất kỳ field nào.

**Tránh cyclic static initialization** khi code không chấp nhận giá trị default hay state chưa hoàn chỉnh. Chuyển công việc phụ thuộc vòng sang factory/startup phase có thứ tự rõ ràng.

## 12. Cross-thread class initialization deadlock

Một kịch bản điển hình khi hai threads cùng khởi tạo **hai classes khác nhau**:

```text
Thread A                           Thread B
initialize Alpha                   initialize Beta
    │                                  │
    ▼                                  ▼
Alpha.<clinit>                    Beta.<clinit>
    │                                  │
needs Beta                        needs Alpha
    │                                  │
    └── waits for Beta                └── waits for Alpha

          Vòng chờ A ↔ B
```

Đây là **sơ đồ deadlock**, không phải một chương trình demo nên chạy (vì có thể treo vô thời hạn). Cơ chế chờ class initialization có thể góp phần tạo deadlock dù **cả hai classes đã load xong**. Đổi loader sang parallel-capable không tự chữa vòng chờ của `<clinit>`.

Các nguồn nguy cơ:

- Static initializer gọi I/O chậm, network hoặc chờ asynchronous tasks.
- Hai classes static-initialize dựa vào nhau qua locks/futures.
- Class initializer giữ một application lock rồi active-use class khác; thread kia giữ lock theo thứ tự ngược.
- Plugin callbacks được chạy trong static initialization trong khi host đợi plugin readiness.

**Thiết kế tốt hơn:** giữ `<clinit>` nhẹ, tránh khởi chạy thread/callback lồng nhau, đặt startup có dependencies rõ ràng sau khi class được initialized và quy định lock ordering cho application locks.

Khóa `LC` của hai runtime classes khác nhau **không phải một mutex chung** bảo vệ toàn bộ global mutable state. Nếu hai static initializers cùng ghi một shared map, vẫn cần synchronization của ứng dụng.

## 13. Initialization thất bại và trạng thái erroneous

Khi class initializer ném exception, JVM xử lý initialization failure theo JLS/JVMS. Nếu initializer kết thúc bất thường bởi exception không phải `Error`, lần dùng đầu thường nhận `ExceptionInInitializerError`. Runtime class có thể được đánh dấu **erroneous**, và các active uses sau có thể nhận `NoClassDefFoundError` thay vì chạy `<clinit>` lại.

Điểm rất dễ nhầm: `NoClassDefFoundError` ở lần sau **không nhất thiết** có nghĩa file `.class` không còn trên classpath.

## 14. Thực hành D — initializer ném lỗi, lần sau không được chạy lại

Tệp **`src/demo/InitializationFailureDemo.java`:**

```java
package demo;

public final class InitializationFailureDemo {
    static final class Broken {
        static int value = fail();

        static int fail() {
            System.out.println("initializer executes");
            throw new IllegalStateException("bad configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                int value = Broken.value;
                System.out.println(value);
            } catch (LinkageError error) {
                System.out.println("attempt " + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy trong **một tiến trình JVM mới**:

```sh
javac --release 17 -d out src/demo/InitializationFailureDemo.java
java -cp out demo.InitializationFailureDemo
```

**Stdout:**

```text
initializer executes
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
```

Phân tích:

1. Lần truy cập `Broken.value` đầu buộc initialize `Broken`; `fail()` được chạy và ném `IllegalStateException`.
2. Vì exception ném ra không phải `Error`, JVM bọc thành `ExceptionInInitializerError`, rồi class ở trạng thái erroneous.
3. Lần truy cập sau trên cùng runtime class không chạy lại `fail()`. JVM báo `NoClassDefFoundError`.
4. `catch (LinkageError)` ở đây chỉ nhằm in nhãn kết quả để học. Ứng dụng thật cần giữ stacktrace/cause và thường không nên tiếp tục xử lý nghiệp vụ nếu một class bắt buộc đã initialization hỏng.
5. Đừng “sửa” bằng cách gọi `loader.loadClass` lần nữa: `loadClass` không reset trạng thái erroneous của runtime definition.

Để có runtime class mới với vòng đời initialization khác, cần cơ chế class loading đúng đắn với **defining loader identity mới**; đó là vấn đề plugin/version lifecycle, không phải một kỹ thuật retry lỗi tùy tiện.

## 15. `<clinit>` và `<init>` khác nhau như thế nào?

| Thuộc tính | `<clinit>` | `<init>` |
| --- | --- | --- |
| Vai trò | Class/interface initialization | Object constructor/instance initialization |
| Số lần trong vòng đời | Một lần thành công cho runtime class khi initialized | Theo mỗi instance construction |
| Mối quan hệ với JVM `LC` | Trạng thái/chờ do JVM điều phối | Không bị `LC` serialize cho mọi instance sau khi class initialized |
| Có thể được gọi trực tiếp như method Java? | Không | Qua `new` hoặc reflection constructor theo Java access rules |
| Có gây lỗi riêng? | `ExceptionInInitializerError`, class erroneous | Constructor body có thể ném exception; reflection có thể bọc `InvocationTargetException` |

Một class đã initialized có thể được nhiều threads tạo instances đồng thời. Nếu constructor thao tác counter hoặc collection mutable, caller phải bảo vệ state bằng primitives thích hợp. Không dùng class-loading lock để synchronize business code trong constructor.

## 16. Khác biệt giữa lỗi loading, linking và initialization

| Hiện tượng | Giai đoạn hay gặp | Cần kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` khi gọi `loadClass` | Lookup không tìm class | Binary name, parent graph, classpath/JAR/URL |
| `ClassFormatError` | Class bytes/verification | Format, bytecode version, source JAR |
| `LinkageError` duplicate definition | Custom loader race khi `defineClass` | `getClassLoadingLock`, `findLoadedClass`, concurrency |
| `NoSuchMethodError` / `NoSuchFieldError` | Resolution/linking với binary API sai version | Descriptors, dependency collision |
| `ExceptionInInitializerError` | `<clinit>` thất bại | Cause đầu tiên, static blocks, I/O/callback |
| `NoClassDefFoundError` ở lần active use sau lỗi init | Runtime class erroneous | Tìm exception lúc initialization đầu |
| Program hang chỉ khi nhiều threads | Loading lock, class-init state hoặc application lock/deadlock | Thread dumps, lock ordering, stacktraces |
| Static block chạy lại sau plugin reload | Runtime class khác do defining loader mới | Class identity, class loader lifecycle |
| `ClassCastException` với cùng binary name | Hai runtime type identities khác nhau | In defining loaders, shared API graph |

**Không áp một biện pháp cho mọi lỗi.** Nạp lớp đúng không bảo đảm binary compatibility. Khởi tạo class thành công không thay thế synchronization cho mutable state trong ứng dụng.

## 17. Debug: quan sát class loading và class initialization độc lập

### API xem defining loader

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defining loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

Đây là **method minh họa**, cần được đặt vào class. `getClassLoader() == null` thường biểu diễn bootstrap loader; `getModule().getName() == null` có thể là unnamed module.

### JVM logging

Trên HotSpot hỗ trợ Unified Logging:

```sh
java -Xlog:class+load=info -cp out demo.InitializationDemo
java -Xlog:class+init=info -cp out demo.InitializationDemo
java -Xlog:help
```

Tag availability phụ thuộc JVM/JDK build; `class+load` giúp xem loading events, `class+init` có thể giúp xem initialization events nếu runtime hỗ trợ. Output log dài và thứ tự phụ thuộc runtime, nên **không có stdout cố định** cho lệnh log này. `-Xlog:help` liệt kê tags/mức hỗ trợ.

### Thread dumps

Dùng `jcmd <pid> Thread.print` trên JVM hỗ trợ hoặc công cụ thread dump tương đương. Khi xem dump:

1. Tìm threads trong `ClassLoader.loadClass`, `findClass` hoặc loader callback.
2. Tìm threads trong static initializer `<clinit>` hoặc chờ initialization của class khác.
3. Đối chiếu parent loader relationships và những application locks đang được giữ.
4. Thu nhiều snapshots nếu có thể để tránh kết luận từ một trạng thái tạm thời.
5. Không giả định JVM `LC` luôn hiển thị như một Java monitor trùng `getClassLoadingLock`.

### Bytecode

```sh
javap -classpath out -c -p demo.InitializationFailureDemo
javap -classpath out -c -p 'demo.InitializationFailureDemo$Broken'
```

`javap` có thể hiện `<clinit>`, field operations và invocation bytecode; nó **không** chứng minh ở thời điểm nào một runtime thread đã nắm initialization coordination. Ở PowerShell và POSIX shell, single quotes giữ ký tự `$` của nested binary name khỏi expansion.

## 18. Quy tắc thiết kế class loader đa luồng

- **Ưu tiên override `findClass`** khi chỉ cần đọc bytecode từ nguồn riêng; giữ `loadClass` chuẩn nếu không cần chính sách delegation tùy biến.
- Khi override `loadClass`, dùng `synchronized (getClassLoadingLock(name))` phù hợp, kiểm tra `findLoadedClass` và chỉ `defineClass` một lần cho một binary name trong loader instance.
- Nếu cần nạp những class names khác nhau đồng thời, hiểu `registerAsParallelCapable` và điều kiện superclass; không bật chỉ để chạy `<clinit>` nhanh hơn.
- Tránh giữ loader lock trong các hoạt động I/O/blocking/callback kéo dài nếu kiến trúc cho phép tách trách nhiệm.
- Không nuốt `Throwable` rồi thử nạp lớp khác: có thể che `LinkageError`, security failure hoặc lỗi tài nguyên nghiêm trọng.
- Đảm bảo shared API/DTO/exception từ host được cả hai bên resolve về **cùng runtime `Class<?>`**, bất kể chính sách parent-first hay child-first.
- Tránh side effects nặng và circular dependencies trong static initializers; tách initialization của type khỏi lifecycle startup của plugin.
- Kiểm thử với **loader graph thực** và nhiều threads, không chỉ chạy tất cả classes trên cùng system classpath trong IDE.
- Quản lý loader lifecycle và references; `URLClassLoader.close()` đóng resource handles nhưng không bảo đảm class unload ngay.
- Nếu thấy một thread chờ, xác định nó đang chờ **loading lock**, **class initialization state** hay **application synchronization** trước khi sửa code.

## 19. Những ngộ nhận cần tránh

- **“Khóa nạp lớp bảo vệ static initializer.”** Không phải vai trò của class-loading lock.
- **“Khóa `LC` là object mà `getClassLoadingLock` trả về.”** Không có hợp đồng API nào nói vậy.
- **“`synchronized (MyClass.class)` luôn chặn được JVM initialization.”** Không nên giả định; JVM có quy tắc `LC` nội bộ riêng.
- **“Parallel-capable nghĩa là hai threads cùng chạy `<clinit>` một class.”** Sai.
- **“Loading hoàn tất thì `<clinit>` đã chạy.”** Không nhất thiết.
- **“`findClass` chỉ gọi một lần trong mọi trường hợp.”** Sai nếu những lần lookup đều thất bại.
- **“Static initializer chạy một lần theo binary name trên toàn JVM.”** Sai nếu có hai defining loaders tạo hai runtime class identities.
- **“`<clinit>` thất bại thì gọi lại `loadClass` để thử initialization lại.”** Không; class đã có thể ở trạng thái erroneous.
- **“Khóa `LC` được giữ trong toàn bộ body static block.”** Không được suy luận từ JLS như vậy.
- **“Class-init deadlock sẽ hết nếu bật parallel-capable.”** Không; đây là hai mechanisms khác nhau.
- **“Constructor instance được serialize bằng class-init lock.”** Không sau khi class đã initialized.
- **“Thread dump có `BLOCKED` chắc chắn là loading-lock deadlock.”** Không: cần inspect stacks/monitor relationships.
- **“Khóa class initialization bảo vệ mọi shared mutable field của ứng dụng.”** Không; ứng dụng vẫn phải tự synchronize state.

## 20. Câu hỏi tự kiểm tra có đáp án

**1. API nào gắn với class-loading lock?** `ClassLoader.getClassLoadingLock(String)`.

**2. Loader chưa parallel-capable thường dùng khóa gì cho các tên khác nhau?** Chính loader instance.

**3. Parallel-capable giúp ích gì?** Cho phép khóa theo class name, giúp những class names khác nhau có thể nạp đồng thời.

**4. Ai quản lý class-initialization lock `LC`?** JVM theo thủ tục JLS §12.4.2, gắn với một runtime class/interface.

**5. `ClassLoader.loadClass` có tự chạy static block không?** Thông thường không yêu cầu initialization.

**6. Hai threads cùng active-use class chưa initialized có chạy `<clinit>` hai lần không?** Không; JVM điều phối cho một quá trình initialization đúng semantics.

**7. Có public Java API để lấy `LC` không?** Không.

**8. JVM có buộc giữ `LC` suốt body `<clinit>` không?** Không nên xem đó là bảo đảm; `LC` điều phối trạng thái và chờ.

**9. `registerAsParallelCapable` có thay đổi initialization semantics không?** Không.

**10. Vì sao loader có thể gọi `findClass` hai lần cho cùng tên?** Nếu lookup không tìm được class, lần sau có thể thử lại; chỉ successful definition mới tạo class để reuse.

**11. Khi `<clinit>` ném exception, lần active use sau có thể thấy gì?** `NoClassDefFoundError` do class ở trạng thái erroneous.

**12. Hai loaders định nghĩa cùng binary name có cùng initialization state không?** Không; chúng tạo hai runtime type identities.

**13. Tại sao hai static initializers có thể deadlock?** Hai threads có thể chờ nhau khi mỗi initializer active-use class mà thread còn lại đang initialize.

**14. `<init>` khác `<clinit>` ở đâu?** `<init>` là constructor instance, `<clinit>` là initialization của runtime class/interface.

**15. Debug thread hang nên xem gì trước?** Thread stack, loader object/parent, `<clinit>` state, application locks và runtime class identity.

## 21. Tài liệu chuẩn

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `getClassLoadingLock` và `registerAsParallelCapable`.
- [Java Language Specification 17 — §12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): `LC`, same-thread recursion, waiting, initialized và erroneous states.
- [Java Language Specification 17 — §12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, constant variables và initiation.
- [Java Virtual Machine Specification 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization, defining loader và runtime type identity.
- [Java SE 17 `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronization tự thiết kế trong ví dụ để có quan sát xác định.

**Kết luận:** **Class-loading lock** phối hợp công việc **tra cứu/định nghĩa class qua một loader**, có thể tuần tự toàn loader hoặc khóa theo tên khi parallel-capable. **Class-initialization lock `LC`** là **cơ chế JVM theo runtime class/interface**, bảo đảm initialization tuân thủ trạng thái và thread ownership. Hai locks có thể xuất hiện gần nhau trong một lần sử dụng class, nhưng **khác đối tượng, khác phạm vi, khác lỗi và không thay thế nhau**.
