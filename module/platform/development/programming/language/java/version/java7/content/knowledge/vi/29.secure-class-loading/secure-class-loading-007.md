# Tránh khóa chéo khi ủy quyền giữa nhiều ClassLoader

## 1. Mục tiêu

Trong Java, một `ClassLoader` có thể **ủy quyền** cho loader khác tìm và nạp một lớp. Khi nhiều luồng đồng thời yêu cầu những lớp khác nhau qua nhiều loader, các lời gọi lồng nhau có thể giữ khóa của loader này rồi chờ khóa của loader kia, tạo ra **deadlock (khóa chéo)**.

Bài này tập trung vào cách nhận diện, phòng tránh và chẩn đoán deadlock khi class loading có **nhiều loader**:

- Hiểu quan hệ giữa `ClassLoader.loadClass`, ủy quyền và khóa trong lúc nạp lớp.
- Thấy vì sao luồng T1 giữ khóa của L1 rồi chờ L2, còn T2 giữ L2 rồi chờ L1 có thể làm chương trình đứng mãi.
- Ưu tiên sơ đồ ủy quyền **không có chu trình**, và dùng cơ chế **parallel-capable class loader** khi thực sự cần mô hình ủy quyền phi phân cấp.
- Sử dụng đúng `registerAsParallelCapable()`, `getClassLoadingLock(String)` và quy tắc override `findClass`/`loadClass` của Java 17+.
- Kiểm tra bằng một chương trình Java 17+ chạy được, nạp lớp đồng thời qua chuỗi nhiều loader, có timeout và output xác định.
- Phân biệt loại deadlock được khóa theo tên lớp giúp tránh với các vòng phụ thuộc vẫn có thể deadlock ngay cả khi loader đã đăng ký parallel-capable.

`registerAsParallelCapable` và `getClassLoadingLock` được đưa vào từ Java 7 và **vẫn là API chính thức trong Java 17+**. Kiến thức ở đây áp dụng cho class loader tùy chỉnh đang được sử dụng, không dựa vào cơ chế hoặc cờ tương thích đã lỗi thời.

## 2. Ủy quyền giữa loader là gì?

Khi có yêu cầu `loader.loadClass("com.example.Widget")`, mặc định `ClassLoader.loadClass(String, boolean)`:

1. Kiểm tra lớp có được loader này nạp trước đó chưa (`findLoadedClass`).
2. Thử ủy quyền cho **parent loader**; nếu không có parent, thử bootstrap loader.
3. Nếu chưa tìm thấy, gọi `findClass(name)` của loader hiện tại.
4. Nếu yêu cầu liên kết lớp, thực hiện `resolveClass` khi thích hợp.

Những bước này thể hiện **mô hình parent-first** mặc định. Khi mọi loader chỉ ủy quyền lên một cây cha cố định, đồ thị phụ thuộc thường không có vòng.

~~~text
              Bootstrap
                 ↑
              Platform
                 ↑
             Application
              ↑      ↑
         Plugin-A    Plugin-B
~~~

Mũi tên “↑” biểu thị “hỏi loader cha trước”. Plugin-A và Plugin-B cùng đi lên cha, không cần gọi ngược nhau để tìm lớp.

Trong hệ thống plugin, module động hoặc bộ nạp thư viện riêng, có thể có cơ chế **ủy quyền ngang**: L1 hỏi L2 về một nhóm class, L2 hỏi L3 cho nhóm khác. Đó là trường hợp cần thiết kế cẩn thận. Việc một loader biết một loader khác không tự gây deadlock; rủi ro nằm ở **đường gọi đang giữ khóa và yêu cầu khóa khác**.

### Tên lớp và loader định nghĩa lớp

Tên binary như `com.example.Widget` chưa đủ để xác định một kiểu ở runtime. **Defining class loader** cũng ảnh hưởng danh tính class. Một yêu cầu `loadClass` có thể trả về `Class<?>` thực sự do **loader được ủy quyền** định nghĩa. Vì vậy đừng nhầm “loader được gọi để tìm lớp” với “loader đã `defineClass` cho lớp đó”.

## 3. Deadlock phát sinh như thế nào?

Giả sử hai custom loader **không parallel-capable**, mỗi loader sử dụng một khóa chung cho mọi class nó nạp. Hai luồng chạy đồng thời:

~~~text
Thread T1                                 Thread T2
----------------------------------        ---------------------------------
L1.loadClass("pkg.A")                     L2.loadClass("pkg.C")
  giữ khóa monitor L1                      giữ khóa monitor L2
  cần nạp pkg.B qua L2                     cần nạp pkg.D qua L1
  đợi khóa L2  ───────────────┐          ┌── đợi khóa L1
                             │          │
                             └── VÒNG CHỜ ┘
~~~

Thứ tự chờ:

1. T1 đang nạp `pkg.A` bằng L1, giữ khóa L1.
2. T2 đang nạp `pkg.C` bằng L2, giữ khóa L2.
3. Trong quá trình định nghĩa/liên kết lớp hoặc quy tắc delegate, T1 cần L2 nạp `pkg.B` nên phải lấy khóa L2, nhưng T2 đang giữ.
4. T2 đồng thời cần L1 nạp `pkg.D` nên phải lấy khóa L1, nhưng T1 đang giữ.
5. Không luồng nào nhả khóa cho đến khi lời gọi `loadClass` lồng bên trong kết thúc. T1 đợi T2, T2 đợi T1 → **deadlock**.

Điểm mấu chốt: `A`, `B`, `C`, `D` **có thể là các lớp hoàn toàn khác tên**. Nếu khóa duy nhất là cả đối tượng loader, yêu cầu nạp lớp không liên quan cũng bị chặn, làm tăng khả năng hình thành vòng chờ giữa các loader.

**Deadlock không giống `ClassNotFoundException`:** lỗi “không tìm thấy lớp” thường làm lời gọi thất bại; deadlock khiến các luồng đợi nhau và không nhận được kết quả. `ClassCircularityError` nói về vòng trong quan hệ class/interface theo JVM và không đồng nghĩa với mọi deadlock ủy quyền.

## 4. Khóa theo từng tên lớp: parallel-capable class loader

API `ClassLoader` có hai cơ chế khóa quan trọng:

- **Loader không đăng ký parallel-capable:** `getClassLoadingLock(name)` mặc định trả về chính **đối tượng loader (`this`)**. Các yêu cầu nạp tên lớp khác nhau qua loader đó có thể bị tuần tự hóa trên cùng monitor.
- **Loader đăng ký parallel-capable:** `getClassLoadingLock(name)` mặc định trả về một đối tượng khóa riêng gắn với **tên binary của lớp trong loader đó**. Các yêu cầu nạp tên khác nhau có thể thực hiện đồng thời.

~~~text
Không parallel-capable:
  L1 + "pkg.A"  ---> [LOCK: L1]
  L1 + "pkg.D"  ---> [LOCK: L1]    // cùng khóa
  L2 + "pkg.B"  ---> [LOCK: L2]
  L2 + "pkg.C"  ---> [LOCK: L2]

Parallel-capable:
  L1 + "pkg.A"  ---> [LOCK: (L1,A)]
  L1 + "pkg.D"  ---> [LOCK: (L1,D)]
  L2 + "pkg.B"  ---> [LOCK: (L2,B)]
  L2 + "pkg.C"  ---> [LOCK: (L2,C)]
~~~

Với ví dụ T1/T2 ở mục 3, T1 giữ `(L1,A)` rồi yêu cầu `(L2,B)`; T2 giữ `(L2,C)` rồi yêu cầu `(L1,D)`. Những khóa khác nhau này cho phép hai chuỗi tiếp tục thay vì chờ khóa **toàn bộ** L1 hoặc L2.

Đây là cơ chế **giảm xung đột khóa**, không phải phép bảo đảm mọi sơ đồ ủy quyền đều an toàn:

- Nếu T1 giữ `(L1,A)` rồi chờ `(L2,B)`, T2 lại giữ `(L2,B)` rồi chờ **chính `(L1,A)`**, vòng chờ vẫn có thể tồn tại.
- Một phương thức `synchronized` trên toàn bộ loader, một `synchronized(this)`, khóa cache chung hoặc khóa của subsystem khác có thể khiến per-name lock mất tác dụng.
- Class initialization và các callback lồng nhau có thể có khóa và vòng phụ thuộc riêng, không được giải quyết chỉ bằng đăng ký parallel-capable.

Vì vậy, cách phòng ngừa mạnh nhất vẫn là **thiết kế đồ thị ủy quyền không có vòng và quản lý khóa nhất quán**.

## 5. Đăng ký parallel-capable đúng cách

`ClassLoader.registerAsParallelCapable()` là phương thức `protected static`. Một subclass tự xây cần gọi nó từ **khối khởi tạo static** của chính subclass, trước khi tạo bất kỳ instance nào của class đó:

~~~java
public final class SafePluginLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "Không thể đăng ký parallel-capable");
        }
    }

    public SafePluginLoader(ClassLoader parent) {
        super(parent);
    }

    // Khi cần đọc bytecode riêng, ưu tiên override findClass(String).
}
~~~

Đây là **đoạn minh họa class**, chưa có `main` và chưa có logic định nghĩa lớp. Dấu mốc quan trọng:

1. `ClassLoader` của JDK đã được đăng ký parallel-capable, nhưng **mỗi subclass cần tự đăng ký** nếu muốn cùng khả năng; đừng suy ra subclass tự động được đăng ký.
2. Tất cả superclass trong chuỗi (ngoại trừ `Object`) phải được đăng ký. Nếu bạn kế thừa một custom loader **không** parallel-capable, subclass mới không thể tự sửa vấn đề chỉ bằng gọi registration.
3. Việc đăng ký phải xảy ra **trước khi có instance** của subclass. Đăng ký thành công là trạng thái của class và không thể gỡ lại.
4. Kiểm tra kết quả `registerAsParallelCapable()`. Khi trả `false`, đừng im lặng coi loader đã hỗ trợ nạp song song.
5. Việc đăng ký là lời cam kết rằng **cài đặt custom loader thực sự thread-safe khi nạp các tên lớp khác nhau cùng lúc**. Nó không tự sửa code giữ khóa sai.

Có thể kiểm tra một instance bằng API công khai:

~~~java
System.out.println(loader.isRegisteredAsParallelCapable());
~~~

Đây là fragment sử dụng biến `loader` có sẵn. Trên instance của class đã đăng ký thành công, kết quả là `true`; trên loader subclass chưa đăng ký, có thể là `false`.

### `getClassLoadingLock(String)`

~~~java
// Bên trong subclass của ClassLoader:
Object lock = getClassLoadingLock(name);
~~~

Method này là `protected`, cho phép subclass dùng khóa theo tên của `loadClass`. Với loader parallel-capable, nhiều yêu cầu cho **cùng một tên** lấy cùng khóa, còn các tên khác có thể có khóa riêng. Việc expose khóa qua một phương thức công khai trong ví dụ bên dưới chỉ để quan sát bài học, không phải cách thiết kế API bình thường.

## 6. Sáu nguyên tắc để tránh khóa chéo

### 6.1. Giữ đồ thị ủy quyền không có chu trình

Ưu tiên:

~~~text
                     ApplicationLoader
                            ↑
                        SharedLoader
                         ↑      ↑
                     PluginA   PluginB
~~~

Hoặc nếu phải dùng ủy quyền ngang, hãy xây **đồ thị có hướng không chu trình (DAG)**:

~~~text
PluginA  ──>  SharedServices  ──>  ApplicationLoader
PluginB  ──>  SharedServices
PluginC  ──>  PluginB
~~~

Không thiết kế các đường gọi kiểu:

~~~text
Loader A ──> Loader B
   ^            |
   └────────────┘
~~~

Trong hệ thống thực tế, quan hệ có thể phụ thuộc **tên lớp và gói**; vì vậy cần xem cả **đồ thị lời gọi có thể xảy ra**, không chỉ sơ đồ các trường `parent`.

### 6.2. Ưu tiên override `findClass`

Nếu chỉ muốn định nghĩa lớp từ nguồn bytecode riêng sau khi parent không tìm thấy, **override `findClass(String)`** để tận dụng phần kiểm tra cache, parent-first delegation và đồng bộ của `ClassLoader.loadClass` mặc định.

~~~java
@Override
protected Class<?> findClass(String name) throws ClassNotFoundException {
    // Tìm bytecode được phép cho đúng binary name.
    // Khi tìm thấy, defineClass(name, bytes, 0, bytes.length).
    // Nếu không tìm thấy, throw new ClassNotFoundException(name).
    throw new ClassNotFoundException(name);
}
~~~

Đây chỉ là **khung minh họa**, cần cung cấp logic bytecode thật khi triển khai. Không copy nguyên phương thức này vào một loader với kỳ vọng nó sẽ nạp lớp mới. Chỉ override `loadClass` khi chính sách ủy quyền khác parent-first là yêu cầu có chủ đích.

### 6.3. Nếu override `loadClass`, giữ đúng quy tắc khóa và cache

Loader có custom delegation cần xử lý:

- Kiểm tra `findLoadedClass(name)` trước khi tìm/định nghĩa.
- Dùng `synchronized (getClassLoadingLock(name))` **khi cần thực hiện thuật toán nạp có khóa theo từng tên**; đừng thay bằng `synchronized(this)` cho toàn bộ nạp lớp.
- Chỉ một luồng định nghĩa **mỗi cặp (defining loader, class name)**; hai luồng đua nhau `defineClass` cùng tên có thể phát sinh `LinkageError`.
- Tôn trọng `resolve` và `resolveClass` khi override biến thể có đối số `boolean resolve`.
- Giữ giới hạn quyền truy cập và chính sách class/package hợp lệ; không tùy ý làm mất khả năng nạp lớp nền tảng.

Chỉ thêm cờ parallel-capable không đủ nếu bản override của bạn vẫn `synchronized` trên toàn bộ object hoặc dùng một khóa chung ngoài ý muốn. Nếu phải có nhiều khóa, xác định **thứ tự cấp phát khóa nhất quán** và tránh giữ chúng trong lúc gọi một loader bên ngoài khi có thể.

### 6.4. Không gọi ngược loader khác trong khi đang giữ khóa chung

Ví dụ thiết kế rủi ro:

~~~java
// Pseudocode: không dùng triển khai như sau.
synchronized (loaderWideLock) {
    return peerLoader.loadClass(name);  // lời gọi sang loader khác
}
~~~

Nếu peerLoader đồng thời giữ khóa của nó và gọi ngược về loader hiện tại, vòng chờ hình thành. Hãy thu thập metadata và quyết định nơi ủy quyền bằng cấu trúc an toàn, tránh khóa quá rộng; với `loadClass` mặc định, vẫn nhớ loader có thể đang giữ **khóa theo tên lớp** trong suốt `findClass`.

### 6.5. Giới hạn trạng thái mutable và callback trong lúc nạp

Tài nguyên như cache tên lớp, map lookup, cấu hình plugin hoặc registry chia sẻ phải thread-safe khi nhiều luồng nạp lớp khác tên. Dùng collection đồng thời hoặc đồng bộ hẹp phù hợp; không đặt toàn bộ quy trình nạp bên trong một `synchronized` lớn.

Tránh thực hiện I/O kéo dài hoặc gọi callback tùy ý của plugin khi vẫn đang giữ khóa class loading. Nếu bắt buộc cần nạp lại một lớp khác, xem nó có tạo cạnh ủy quyền ngược đang chờ khóa hay không.

### 6.6. Kiểm thử deadlock và class initialization riêng

Đăng ký parallel-capable giúp xử lý **một loại** xung đột khóa khi nạp class. Nếu static initializer của class X chờ class Y, còn Y chờ X, đó là một nguồn kẹt khác. Cần xem cả:

- Khóa loading của các `ClassLoader`.
- Khóa do ứng dụng/framework tự thêm.
- Vòng phụ thuộc trong static initialization và luồng callback.
- Thread context class loader (`Thread.currentThread().getContextClassLoader()`) khi thư viện dùng loader của bên gọi để nạp lớp.

Không coi một lần chạy thành công là chứng minh mọi lịch interleaving đều không deadlock.

## 7. Ví dụ Java 17+: nạp đồng thời qua chuỗi nhiều loader an toàn

Chương trình dưới đây minh họa:

- Loader `first` ủy quyền khi không tìm thấy lớp cho `second`; `second` tiếp tục ủy quyền cho class loader ứng dụng.
- Cả `first` và `second` đều là instance của subclass đã đăng ký parallel-capable.
- Khóa cho cùng tên ổn định; khóa cho hai tên khác nhau và hai loader khác nhau là các object khác nhau.
- Hai tác vụ nạp hai class song song; gọi `Future.get` có timeout để không chờ vô hạn nếu có lỗi.

**Giới hạn minh họa:** mỗi loader custom không tự định nghĩa bytecode; chúng **ủy quyền** tới loader ứng dụng, là nơi thật sự định nghĩa `Alpha`/`Beta`. Đây là cách nhìn tập trung vào **đường ủy quyền và khóa**, không phải ví dụ đọc file `.class` hoặc tự viết bytecode loader.

Tạo file **`SafeLoaderDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SafeLoaderDemo {
    public static final class Alpha {}
    public static final class Beta {}

    public static final class PeerLoader extends ClassLoader {
        static {
            // ClassLoader đã parallel-capable,
            // nhưng subclass phải đăng ký riêng.
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "parallel registration failed");
            }
        }

        private final ClassLoader delegate;
        private final AtomicInteger delegates = new AtomicInteger();

        public PeerLoader(ClassLoader delegate) {
            // Không dùng parent ứng dụng; bootstrap vẫn khả dụng.
            // Các lớp ứng dụng sẽ được chuyển qua findClass -> delegate.
            super(null);
            this.delegate = delegate;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            delegates.incrementAndGet();
            return delegate.loadClass(name);
        }

        // Chỉ để minh họa khóa protected trong bài học.
        public Object lock(String name) {
            return getClassLoadingLock(name);
        }

        public int delegates() {
            return delegates.get();
        }
    }

    public static void main(String[] args) throws Exception {
        PeerLoader second =
                new PeerLoader(SafeLoaderDemo.class.getClassLoader());
        PeerLoader first = new PeerLoader(second);

        String alphaName = Alpha.class.getName();
        String betaName = Beta.class.getName();

        System.out.println("parallel: " +
                first.isRegisteredAsParallelCapable());
        System.out.println("stable lock: " +
                (first.lock(alphaName) == first.lock(alphaName)));
        System.out.println("per-name lock: " +
                (first.lock(alphaName) != first.lock(betaName)));
        System.out.println("per-loader lock: " +
                (first.lock(alphaName) != second.lock(alphaName)));

        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch gate = new CountDownLatch(1);

        try {
            Future<Class<?>> a = workers.submit(() -> {
                gate.await();
                return first.loadClass(alphaName);
            });
            Future<Class<?>> b = workers.submit(() -> {
                gate.await();
                return first.loadClass(betaName);
            });

            // Cho hai tác vụ bắt đầu gần nhau.
            gate.countDown();

            Class<?> aClass = a.get(5, TimeUnit.SECONDS);
            Class<?> bClass = b.get(5, TimeUnit.SECONDS);

            System.out.println("classes resolved: " +
                    (aClass == Alpha.class && bClass == Beta.class));
            System.out.println("peer delegation: " +
                    (first.delegates() == 2 && second.delegates() == 2));
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Chạy với **JDK 17+**, không cần thư viện ngoài:

~~~bash
javac --release 17 SafeLoaderDemo.java
java SafeLoaderDemo
~~~

`stdout` khi chạy thành công:

~~~text
parallel: true
stable lock: true
per-name lock: true
per-loader lock: true
classes resolved: true
peer delegation: true
~~~

Giải thích vì sao kết quả có thể kiểm tra:

1. `PeerLoader` tự đăng ký trong static initializer; superclass `ClassLoader` đã parallel-capable. Vì vậy `isRegisteredAsParallelCapable()` trả `true`.
2. `getClassLoadingLock(alphaName)` trả cùng object khi hỏi hai lần trên **cùng loader/tên**; khóa của `betaName` và khóa từ `second` là những object khác.
3. `super(null)` không đặt application loader làm parent. Với hai class `Alpha`/`Beta` không phải class bootstrap, quá trình nạp đi vào `findClass`: `first → second → application loader`.
4. `Alpha.class` và `Beta.class` thực sự được application loader định nghĩa; hai lời gọi `first.loadClass(...)` trả đúng hai `Class<?>` đó.
5. Hai tên lớp khác nhau khiến `first` và `second` sử dụng các khóa riêng. `AtomicInteger` chứng minh `findClass` được gọi một lần mỗi tên tại mỗi loader: `first.delegates()==2` và `second.delegates()==2`.
6. `CountDownLatch` giúp tạo yêu cầu đồng thời. `Future.get(5, TimeUnit.SECONDS)` tránh để main đợi vô hạn trong tình huống kiểm thử gặp kẹt. Kết quả in theo **thứ tự của main**, không phụ thuộc thứ tự scheduler chạy hai tác vụ.

**Giới hạn của timeout:** `Future.get` ném `TimeoutException` khi quá hạn; nó không tự sửa deadlock bên trong các thread. `shutdownNow()` cố gắng ngắt thread, nhưng code đang chờ monitor có thể không bị giải phóng nhờ interrupt. Trong kiểm thử kịch bản deadlock có chủ ý, hãy chạy trong **quy trình/JVM riêng** có giới hạn thời gian bên ngoài.

Không nên dùng riêng chương trình này làm bằng chứng “mọi cấu trúc ủy quyền đều an toàn”: nó chứng minh **một** chuỗi có hướng không vòng và kiểm tra khóa theo tên lớp của API.

## 8. Những trường hợp parallel-capable vẫn không đủ

### Vòng trên đúng khóa (loader, tên lớp)

~~~text
T1 giữ (L1, A)
    muốn lấy (L2, B)

T2 giữ (L2, B)
    muốn lấy (L1, A)
~~~

Hai thread vẫn đợi nhau trên **chính hai khóa** dù loader đã parallel-capable. Cần phá vòng phụ thuộc, không chỉ thay cơ chế khóa. Với mô hình ủy quyền có điều kiện, hãy kiểm tra từng đường phụ thuộc có thể có cho đúng class name.

### Override `loadClass` nhưng giữ một khóa trên toàn bộ loader

~~~java
// Anti-pattern minh họa: không dùng trong triển khai thực tế.
@Override
public synchronized Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return super.loadClass(name);
}
~~~

Override này giữ monitor `this` xuyên suốt lời gọi. Vì thế, dù subclass đã đăng ký parallel-capable và `super.loadClass` dùng khóa theo tên, lời gọi phía ngoài **vẫn tuần tự hóa theo cả loader**. Tệ hơn, khi cùng lúc hai loader ủy quyền ngược nhau, cơ chế khóa toàn cục này tái tạo rủi ro deadlock.

### Vòng của class initialization

Ví dụ lớp `A` có `static` initialization đợi một hành động của `B`, còn `B` đợi `A`. Đây là vấn đề của **class initialization và phối hợp giữa các luồng**, không thể giải quyết bằng cách đặt `registerAsParallelCapable()`. Tránh lấy các khóa ứng dụng phức tạp hoặc chờ callback trong static initializer.

### Cache không thread-safe

Khi loader hỗ trợ nạp các tên khác nhau song song, shared map/cache mutable có thể bị truy cập đồng thời. Nếu override `loadClass` hoặc `findClass` và tự `defineClass`, hãy bảo đảm không định nghĩa hai lần cùng tên ở cùng defining loader và không có race làm rò class khác version.

## 9. Chẩn đoán khi ứng dụng bị kẹt lúc nạp lớp

### 9.1. Quan sát thread dump

Nếu biết PID của JVM, JDK có công cụ:

~~~bash
jcmd <PID> Thread.print -l
~~~

Tìm thread đang trong `ClassLoader.loadClass`, `findClass`, `defineClass` hoặc code ủy quyền custom. Đối chiếu các thông tin:

- Thread đang chờ (`BLOCKED`, `WAITING`...) và monitor/lock được giữ.
- Class đang yêu cầu nạp, loader đang được gọi, loader delegate tiếp theo.
- Hai hay nhiều thread có đường chờ khép kín không.
- Có `synchronized(this)`, một `loaderWideLock` hoặc lock của plugin registry chen vào giữa hay không.

Đừng kết luận mọi thread đang `BLOCKED` trong loader đều là deadlock; nạp cùng class đồng thời thường phải chờ một luồng hoàn tất và sau đó tiếp tục. Deadlock cần một **vòng chờ không thể tự giải phóng**.

### 9.2. Ghi log nạp lớp ở JDK hiện hành

Có thể bật unified logging (ví dụ Java 17):

~~~bash
java -Xlog:class+load=info SafeLoaderDemo
~~~

Log của JVM sẽ bổ sung sự kiện nạp class ngoài stdout chương trình. Tùy JDK, mức log và classpath, nội dung log khác nhau; vì thế không trình bày output log như kết quả cố định. Log cho biết lịch nạp class nhưng không thay thế thread dump để xác định monitor nào đang bị giữ.

### 9.3. Instrument custom loader có kiểm soát

Khi sở hữu code `ClassLoader`, có thể log **tên class, danh tính loader và delegate được chọn** (ví dụ `System.identityHashCode(loader)`), thread name, thời điểm bắt đầu/kết thúc. Không log dữ liệu bí mật hoặc in quá nhiều event trên đường nóng. Đếm và giám sát thời gian nạp, timeout của test và số tác vụ còn chờ giúp tái hiện lỗi khó gặp.

Nếu hệ thống dùng plugin framework/OSGi/app server, cần xem tài liệu riêng của framework cho cơ chế delegation, loader namespaces và reload. Không giả định mọi framework dùng parent-first.

## 10. Bảng lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| T1 chờ khóa L2, T2 chờ L1 | Ủy quyền chéo dưới monitor toàn loader | Bỏ vòng phụ thuộc, tránh khóa global; cân nhắc parallel-capable |
| Đã đăng ký parallel-capable mà vẫn kẹt | Vòng trên đúng khóa `(loader,name)`, khóa ngoài hoặc class initialization | Lập wait-for graph, sửa quy tắc delegate và thứ tự khóa |
| `registerAsParallelCapable()` trả `false` | Superclass chưa parallel-capable hoặc class đã có instance | Rà lại chuỗi kế thừa và thời điểm đăng ký |
| `isRegisteredAsParallelCapable()` là `false` | Subclass chưa tự đăng ký thành công | Gọi registration trong static initializer và kiểm tra |
| Nạp đồng thời báo `LinkageError` | `defineClass` trùng tên/class tại cùng loader hoặc vi phạm ràng buộc liên kết | Kiểm tra cache, lock theo tên, không define hai lần |
| Gọi `findClass` từ code ứng dụng thay vì `loadClass` | Bỏ qua thuật toán loader/cơ chế mặc định | Gọi `loadClass`; chỉ override `findClass` để thực thi nguồn riêng |
| Method `loadClass` được đánh dấu `synchronized` | Khóa toàn bộ object dù loader parallel-capable | Thiết kế lại override theo `getClassLoadingLock(name)` hoặc dùng mặc định |
| Thread dump có nhiều thread `BLOCKED` | Có thể là cạnh tranh khóa bình thường, chưa chắc deadlock | Xác định vòng chờ thực sự, xem nhiều lần lấy dump |
| Chỉ xảy ra khi chạy đồng thời | Race trên cache hoặc vòng delegate hiếm gặp | Tạo test đồng thời có timeout, log theo class name/loader |
| Đổi sang parallel-capable gây lỗi dữ liệu | Shared mutable state trong loader vốn giả định chỉ một thread | Củng cố thread-safety trước khi đăng ký |
| Vòng gọi khi class static initializer chạy | Phụ thuộc initialization, callback hoặc monitor riêng | Giảm phụ thuộc static, tránh chờ chéo trong initializer |

## 11. Checklist thiết kế loader an toàn

1. Ưu tiên mô hình parent-first và **đồ thị ủy quyền không vòng**.
2. Nếu cần custom loader, ưu tiên override `findClass(String)`; chỉ override `loadClass` nếu cần chính sách ủy quyền riêng.
3. Nếu nhiều luồng có thể nạp các tên khác nhau, kiểm tra thread-safety của toàn bộ custom loader và trạng thái mutable dùng chung.
4. Khi phù hợp, đăng ký `registerAsParallelCapable()` **trong static initializer của từng subclass**, bảo đảm superclass cũng đã đăng ký.
5. Tránh `synchronized(this)` hoặc `public synchronized loadClass` kéo dài sang việc gọi delegate; dùng khóa đúng tên lớp và thứ tự lock nhất quán.
6. Trước mỗi `defineClass`, bảo đảm chỉ một đường tạo định nghĩa cho cùng **(loader, binary name)**.
7. Xem xét mọi cạnh loader-to-loader, kể cả delegate gián tiếp qua framework, callback và thread context class loader.
8. Không coi khóa theo tên lớp là bảo đảm tránh mọi deadlock; vòng chờ trên đúng cặp khóa vẫn xảy ra.
9. Dùng thread dump và log class loading để điều tra; phân biệt chờ bình thường với wait-for cycle.
10. Chạy test cạnh tranh có timeout trên JDK mục tiêu; nếu cần thử kịch bản deadlock chủ ý, dùng tiến trình test cách ly để không treo quy trình chính.

**Ghi nhớ:** nạp lớp an toàn = **ủy quyền có hướng rõ ràng, hạn chế chu trình, khóa đủ hẹp và code loader thread-safe**. Parallel-capable giúp các tên lớp khác nhau được nạp đồng thời; nó **không chữa được** mọi vòng ủy quyền hoặc khóa do ứng dụng tự thêm.

## Tài liệu tham khảo hiện hành

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): thuật toán `loadClass`, `getClassLoadingLock`, `registerAsParallelCapable`, `isRegisteredAsParallelCapable`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): định danh/đặc điểm đối tượng `Class<?>` được nạp.
- [Oracle — Multithreaded Custom Class Loaders in Java](https://docs.oracle.com/javase/8/docs/technotes/guides/lang/cl-mt.html): phân tích hình thành deadlock và cơ chế parallel capable; nội dung cốt lõi vẫn phù hợp với `ClassLoader` hiện hành.
- [Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print` để chẩn đoán luồng và khóa.
- [Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): unified logging `-Xlog`.
