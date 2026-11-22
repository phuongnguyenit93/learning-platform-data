# Kiến thức cần chuẩn bị cho Java Instrumentation: vòng đời lớp, bytecode, class loader, module và xử lý đồng thời

Java Instrumentation tác động vào chương trình ở cấp **lớp và bytecode**. Trước khi viết agent hoặc gắn công cụ quan sát, cần hiểu JVM lấy định nghĩa lớp từ đâu, kiểm tra và khởi tạo lớp khi nào, danh tính của một lớp được xác định thế nào, module giới hạn quyền truy cập ra sao và chuyện gì xảy ra nếu nhiều luồng cùng tải lớp. Bài này xây nền tảng cho những thao tác đó; ví dụ sử dụng Java 17 trở lên.

## 1. Bức tranh tổng thể và mục tiêu học tập

Luồng khái quát khi chạy một ứng dụng Java:

~~~text
Mã nguồn .java
    │ javac
    ▼
Class file (.class, chứa bytecode và metadata)
    │ ClassLoader tìm/đọc bytes
    ▼
[ClassFileTransformer có thể nhận và biến đổi bytes khi định nghĩa lớp]
    │
    ▼
JVM định nghĩa lớp, liên kết (verification + preparation; resolution theo nhu cầu)
    │
    ▼
Khởi tạo lớp khi có yêu cầu sử dụng chủ động (<clinit>, nếu có)
    │
    ▼
Thực thi các phương thức, có thể được JIT biên dịch thành mã máy
~~~ 

Sơ đồ diễn tả một trường hợp tải lớp mới, không khẳng định mọi bước liên kết xảy ra tại một thời điểm cố định. **Retransformation/redefinition** là luồng khác, tác động lên lớp đã được định nghĩa; không đơn giản là chạy lại toàn bộ chu kỳ khởi tạo.

Sau bài này, người học cần trả lời được:

1. Phân biệt **loading**, **linking**, **initialization** và tìm đúng thời điểm có thể biến đổi bytes.
2. Đọc được cấu trúc cơ bản của class file, bytecode và nguyên nhân JVM từ chối bytecode sai.
3. Giải thích tại sao hai lớp có cùng tên đầy đủ vẫn có thể không cùng kiểu nếu khác defining class loader.
4. Phân biệt **module readability**, **exports** và **opens**, đặc biệt khi agent dùng reflection.
5. Nhận diện các vấn đề cạnh tranh, tái nhập, deadlock và tính nhất quán khi class loading/transform diễn ra đồng thời.

## 2. Vòng đời lớp: load, link, initialize, use

### 2.1. Loading — tìm và định nghĩa lớp

Khi cần kiểu tên nhị phân như **com.example.Service**, JVM yêu cầu class loader phù hợp tìm định nghĩa. Trong triển khai thông thường, loader lấy bytes từ classpath, module path, JAR hoặc một nguồn tùy chỉnh rồi định nghĩa lớp (ví dụ thông qua **ClassLoader.defineClass**). Tên nhị phân là dạng dùng dấu chấm; trong tên nội bộ của class file/transformer, dấu phân cách package thường là dấu gạch chéo, chẳng hạn **com/example/Service**.

Phải phân biệt:

- **Initiating loader**: loader tham gia yêu cầu nạp lớp; nó có thể ủy quyền cho loader khác.
- **Defining loader**: loader thực sự định nghĩa lớp. Chính defining loader cùng với tên nhị phân quyết định danh tính runtime của kiểu.
- **Class object**: đại diện của kiểu đã nạp; có thể hỏi **Class.getClassLoader()**. Với nhiều lớp nền tảng do bootstrap loader định nghĩa, kết quả là **null**.

Nếu dùng agent và đăng ký **ClassFileTransformer** đủ sớm, transformer có thể được gọi trong quá trình JVM định nghĩa lớp. Việc transformer được gọi **không có nghĩa** lớp đã chạy static initializer hay constructor.

### 2.2. Linking — xác minh, chuẩn bị, phân giải

**Linking** gồm ba hoạt động liên quan nhưng không nhất thiết hoàn tất cùng lúc:

| Hoạt động | JVM làm gì? | Điều cần nhớ khi instrumentation |
| --- | --- | --- |
| Verification | Kiểm tra class file và bytecode có cấu trúc, kiểu và luồng điều khiển hợp lệ | Stack, local variables, nhánh nhảy hoặc StackMapTable sai có thể gây **VerifyError** |
| Preparation | Chuẩn bị các static field và giá trị mặc định; constant variable có ngoại lệ theo quy tắc **ConstantValue** | Không được đồng nhất preparation với việc chạy khối **static {}** |
| Resolution | Chuyển tham chiếu ký hiệu trong constant pool thành tham chiếu runtime, có thể làm lộ nhu cầu tải thêm lớp | Có thể xảy ra sớm hoặc muộn theo điểm sử dụng; lỗi liên kết đôi khi chỉ xuất hiện ở lần chạy một nhánh cụ thể |

JVM đảm bảo lớp đã được verify và prepare trước khi initialize, nhưng **resolution** được phép thực hiện lười. Đừng dựa vào giả định cứng rằng mọi kiểu mà một phương thức nhắc đến đều đã được nạp và resolve ngay khi lớp chứa phương thức được load.

### 2.3. Initialization — chạy mã khởi tạo tĩnh

Khởi tạo lớp thực thi **<clinit>** do trình biên dịch tổng hợp từ các phép gán static field không phải constant expression và các khối **static {}** theo thứ tự mã nguồn. Mỗi lớp được initialize một lần trong một vòng đời định nghĩa lớp; JVM đồng bộ hóa việc này khi nhiều luồng cùng yêu cầu.

Các hành động có thể gây initialize gồm **new**, đọc/ghi một static field không phải constant variable, gọi static method và một số thao tác phản chiếu. Ngược lại, lấy class literal như **Target.class** hoặc đọc compile-time constant không tự nó buộc initialize.

Ví dụ độc lập:

~~~java
// File: LifecycleDemo.java
public class LifecycleDemo {
    static class Target {
        static final int CONSTANT = 7;  // compile-time constant
        static int value = initialize();

        static int initialize() {
            System.out.println("Target.<clinit> chạy");
            return 42;
        }

        static void ping() {
            System.out.println("ping(): " + value);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "LifecycleDemo$Target",
                false,  // tải lớp nhưng chưa yêu cầu khởi tạo
                LifecycleDemo.class.getClassLoader()
        );
        System.out.println("Đã có Class: " + type.getSimpleName());
        System.out.println("Hằng số: " + Target.CONSTANT);
        Target.ping();
        Target.ping();
    }
}
~~~

~~~bash
javac --release 17 LifecycleDemo.java
java LifecycleDemo
~~~

Kết quả chuẩn:

~~~text
Đã có Class: Target
Hằng số: 7
Target.<clinit> chạy
ping(): 42
ping(): 42
~~~

Giải thích: **Class.forName(name, false, loader)** nhận được đối tượng **Class** mà chưa yêu cầu khởi tạo; giá trị **CONSTANT** được trình biên dịch nhúng vào bytecode nơi sử dụng; lời gọi **ping()** lần đầu mới kích hoạt việc initialize lớp. Hai lần gọi không chạy lại **<clinit>**. Nếu **initialize()** lỗi, lần đầu có thể gặp **ExceptionInInitializerError**; những lần dùng sau có thể gặp **NoClassDefFoundError** do lớp ở trạng thái khởi tạo thất bại.

### 2.4. Vị trí của instrumentation trên vòng đời

- **Khi load mới**: transformer nhận bytes trước khi JVM hoàn tất định nghĩa/kiểm tra lớp. Nó có thể trả về một mảng bytes hợp lệ khác hoặc **null** để không thay đổi.
- **Khi lớp đã load**: đăng ký transformer mới không tự sửa những lớp cũ. Muốn tác động lên lớp đã tồn tại cần cơ chế như **Instrumentation.retransformClasses** hoặc **redefineClasses**, tùy khả năng JVM và quyền của agent.
- **Retransform/redefine không tự chạy lại static initializer**, không tự tạo lại object đã tồn tại. Static state giữ nguyên trừ khi logic chương trình chủ động thay đổi.
- **Active stack frame** có thể tiếp tục thực thi định nghĩa phương thức cũ; các invocation mới sẽ đi theo định nghĩa đã được cập nhật. Vì vậy không nên diễn giải việc redefine như một chuyển đổi nguyên tử của mọi lời gọi đang chạy.
- Với class redefinition/retransformation thông thường, JVM áp giới hạn thay đổi schema: không tùy ý thêm/xóa field hoặc method, đổi cấu trúc kế thừa hay thay nhiều thuộc tính cấu trúc khác. Transform **ngay lần định nghĩa đầu** có biên độ khác với việc sửa lớp đang hoạt động.

## 3. Bytecode: JVM thực sự đọc và kiểm tra điều gì?

### 3.1. Từ Java source đến class file

**javac** biến Java source thành class file (hoặc nhiều class file cho kiểu lồng, anonymous class, v.v.). Class file thường gồm:

- **Magic và version**: dấu hiệu định dạng class file, phiên bản class file mà runtime phải hỗ trợ.
- **Constant pool**: chuỗi, literal, tên kiểu, tên field/method, descriptor, tham chiếu tới method handle và các thực thể cần resolve.
- **Access flags, this/super, interfaces**: metadata của kiểu và quan hệ kế thừa.
- **Fields, methods, attributes**: định nghĩa thành viên, annotation, generic signature, metadata module/nest/record khi tương ứng.
- **Code attribute** của phương thức có bytecode: **max_stack**, **max_locals**, dãy instruction, exception table và các thuộc tính con; **StackMapTable** hỗ trợ verifier ở các phiên bản class file hiện đại.

Các lệnh JVM hoạt động trên **operand stack**, **local-variable slots** và **constant pool**. Ví dụ, một phép cộng **int** có thể nạp hai toán hạng lên stack bằng các instruction như **iload**, thực hiện **iadd**, rồi trả kết quả với **ireturn**. Tên biến và generic source-level thường không phải là thông tin định kiểu runtime đầy đủ; nhiều dạng generic bị erase.

### 3.2. Đọc bytecode thay vì đoán từ source

Tạo file sau:

~~~java
// File: BytecodeDemo.java
public class BytecodeDemo {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(add(3, 4));
    }
}
~~~

~~~bash
javac --release 17 BytecodeDemo.java
java BytecodeDemo
javap -c -p BytecodeDemo
javap -v -p BytecodeDemo
~~~

**java** in ra **7**. Ở phương thức **add**, bản disassembly thông thường có chuỗi **iload_0**, **iload_1**, **iadd**, **ireturn**; **javap -v** cho thấy version, constant pool, descriptor, attributes và các metadata bổ sung. Khi đối chiếu output, quan sát **stack effect** của mỗi instruction và kiểu dữ liệu ở từng nhánh, không chỉ đọc mnemonic.

Với Java 17, **javac --release 17** tạo class file major version **61**. Lớp biên dịch cho version cao hơn runtime có thể gây **UnsupportedClassVersionError**.

### 3.3. Vì sao thêm vài byte có thể làm hỏng cả lớp?

Giả sử chèn lệnh ghi log vào đầu một method. Nếu chỉ thêm bytes mà không cập nhật cấu trúc liên quan, có thể gây lỗi:

1. **Control flow**: offset của jump, exception handler và try/catch thay đổi.
2. **Operand stack**: đưa giá trị sai kiểu, thiếu pop/return, hoặc tính **max_stack** không đủ.
3. **Local slots**: thêm biến mà quên **max_locals** hoặc làm sai kiểu.
4. **Stack map frames**: frame không còn khớp luồng điều khiển sau khi thêm nhánh.
5. **Descriptors và symbolic refs**: gọi method với chữ ký không phù hợp, thiếu dependency hoặc resolve ở sai loader.
6. **Metadata**: annotation, line number, module/nest/record attributes có thể cần được giữ nhất quán.

Các thư viện như **ASM** hoặc **Byte Buddy** xử lý nhiều phần cơ học; chúng không thay thế việc hiểu cấu trúc class file và semantics chương trình. Chẳng hạn, chế độ tự tính frame của ASM có thể cần giải quyết common superclass; nếu resolver dùng nhầm class loader, kết quả vẫn có thể sai. Tránh cố nạp các class của ứng dụng ngay bên trong transformer chỉ để suy ra kiểu, vì có thể kích hoạt class loading lồng nhau.

Quy tắc tối thiểu khi biến đổi: xử lý một lần theo **internal class name**, bảo toàn semantics mong muốn, tính lại offset/frame khi cần, kiểm tra compatibility phiên bản bytecode và chạy thử trên các nhánh thật sự được thực thi.

## 4. Class loader: danh tính kiểu, ủy quyền và cách ly

### 4.1. Hệ phân cấp phổ biến

Trong runtime Java hiện đại thường gặp:

| Loader | Vai trò điển hình |
| --- | --- |
| Bootstrap | Định nghĩa nhiều lớp nền tảng của Java, được JVM hỗ trợ; **getClassLoader()** có thể trả **null** |
| Platform | Một phần các module nền tảng; không có nghĩa mọi lớp platform đều có quyền đặc biệt |
| Application/system | Thường nạp code của ứng dụng từ classpath/module path phù hợp |
| Custom loader | Nạp plugin, ứng dụng cô lập, lớp sinh động hoặc triển khai cơ chế hot deployment |

Các loader chuẩn thường áp dụng **parent-first delegation**, nhưng loader tùy chỉnh có thể sử dụng chiến lược khác. **Thread context class loader** là một con trỏ trên thread để thư viện hoặc SPI tìm implementation; nó không tự động trở thành defining loader của mọi lớp mà thread dùng.

### 4.2. Công thức danh tính runtime

Một kiểu runtime về cơ bản được phân biệt bằng **(tên nhị phân, defining class loader)**. Hai định nghĩa của **example.Item** ở hai loader khác nhau là hai kiểu khác nhau, dù bytecode giống hệt. Vì vậy, cast có thể thất bại và **isAssignableFrom** có thể trả **false** khi tên lớp trông như nhau.

Ví dụ Java 17 chạy được và tự định nghĩa bản sao của nested class **Item** ở loader khác:

~~~java
// File: LoaderIdentityDemo.java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    public static class Item { }

    static final class IsolatedLoader extends ClassLoader {
        private final String targetName = Item.class.getName();

        IsolatedLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(targetName)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent().getResourceAsStream(resource)) {
                        if (in == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = in.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> fromApp = Item.class;
        Class<?> isolated = new IsolatedLoader(
                LoaderIdentityDemo.class.getClassLoader()
        ).loadClass(Item.class.getName());

        System.out.println(fromApp.getName().equals(isolated.getName()));
        System.out.println(fromApp == isolated);
        System.out.println(fromApp.isAssignableFrom(isolated));
    }
}
~~~

~~~bash
javac --release 17 LoaderIdentityDemo.java
java LoaderIdentityDemo
~~~

~~~text
true
false
false
~~~

**Giải thích**: tên đầy đủ trùng nhau, nhưng **IsolatedLoader** tự gọi **defineClass** cho **Item**; lớp tải từ application loader và lớp tải từ isolated loader có danh tính khác nhau. Mẫu này cố ý phá parent-first cho đúng một tên để minh họa; không nên sao chép nguyên trạng thành class loader production vì còn nhiều vấn đề như package, resource, sealing, signature, protection domain và lifecycle.

### 4.3. Hệ quả đối với agent và transformer

- **ClassFileTransformer** nhận cả **loader** và **className**. Cần xét **loader + tên** khi lọc lớp, cache bytecode, gắn marker hay ghi metric. Chỉ lọc theo tên có thể đụng nhiều bản định nghĩa trong hệ plugin/app server.
- **null loader** cần được xử lý có chủ đích; đừng gọi **loader.loadClass(...)** mà không kiểm tra.
- Không giả định classpath của agent nhìn thấy mọi kiểu ứng dụng. Agent có thể được load bởi system loader trong khi code cần quan sát được định nghĩa bởi loader khác.
- Tránh giữ tham chiếu mạnh tới **Class**, **ClassLoader** hoặc key cache gắn loader mãi mãi; điều đó có thể chặn **class unloading** và gây memory leak khi ứng dụng reload.
- Không dùng transformer để gọi lại code ứng dụng một cách tùy tiện: việc nạp lớp mới trong lúc đang transform có thể gây recursion, deadlock hoặc class circularity.

## 5. Java Platform Module System (JPMS): reads, exports và opens

Từ Java 9, **module** bổ sung biên giới truy cập bên cạnh package/class loader. Mỗi lớp thuộc một module; module có thể **named** (được khai báo bằng **module-info.java**) hoặc **unnamed** (ví dụ nhiều class trên classpath). Mỗi class loader có unnamed module của nó; không nên xem tất cả code classpath ở mọi loader như cùng một module.

### 5.1. Ba khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **Readability** | Module A có quan hệ đọc module B để tham chiếu tới kiểu công khai phù hợp | Khai báo **requires** hoặc điều chỉnh graph khi cần |
| **exports** | Cho phép các module được phép truy cập **public** type/member của package theo quy tắc JPMS | Sử dụng API công khai từ module khác |
| **opens** | Cho phép **deep reflection** đối với package, gồm truy cập thành viên không public nếu luật reflection khác cho phép | Agent/framework dùng **setAccessible(true)** hoặc reflection sâu |

Ví dụ khai báo module ứng dụng:

~~~java
// File: module-info.java
module com.example.app {
    exports com.example.app.api;
}
~~~

Package **com.example.app.api** công khai cho module khác theo quyền đọc; package **com.example.app.internal** chưa được export/open. **exports** không tự cho phép can thiệp private field qua reflection. Để mở package internal cho một module chẩn đoán được đặt tên:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.internal to com.example.inspector;
}
~~~

Khi ứng dụng không thể sửa **module-info.java**, môi trường chạy có thể chọn mở package cho code trên classpath bằng tham số:

~~~bash
java --add-opens com.example.app/com.example.app.internal=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Lệnh minh họa cú pháp: chỉ chạy khi các module/class đúng tên đã được biên dịch và có trên **module path**. **--add-exports** và **--add-opens** không đồng nghĩa; chỉ dùng quyền tối thiểu cần thiết. Khi agent có **Instrumentation**, API **redefineModule** còn cho phép điều chỉnh một số quan hệ reads/exports/opens ở runtime; điều này không xóa các ràng buộc về class loader và bytecode hợp lệ.

### 5.2. Đặt class loader cạnh module để chẩn đoán

Khi một agent báo không gọi được API hoặc không đọc được field, hãy hỏi theo thứ tự:

1. **Kiểu thực sự được định nghĩa bởi loader nào?** Cùng FQCN đã chắc là cùng **Class** chưa?
2. **Kiểu nằm trong module nào?** Có phải named module không?
3. **Module của caller có đọc được module đích không?**
4. **Package đã export cho caller chưa?** Nếu cần reflection sâu, đã **open** cho caller chưa?
5. **Phương thức/field và access modifiers** có cho phép thao tác dự kiến không?

Ví dụ **InaccessibleObjectException** thường chỉ tới hạn chế deep reflection của module; chuyển sang loader khác không phải cách chữa tổng quát. Trái lại, lỗi **ClassCastException** khi hai tên giống nhau có thể đến từ hai loader, ngay cả khi đã mở module.

## 6. Xử lý đồng thời: class loading và instrumentation không diễn ra trên một luồng duy nhất

### 6.1. JVM đồng bộ hóa khởi tạo lớp, nhưng không đồng bộ hóa mọi dữ liệu của agent

Một lớp được initialize theo cơ chế đồng bộ của JVM. Nếu nhiều thread cùng dùng một class chưa khởi tạo, một thread sẽ thực thi quá trình khởi tạo cần thiết; các thread khác được phối hợp theo quy tắc của JVM. Điều đó **không** biến tất cả static mutable fields thành thread-safe. Sau khi khởi tạo xong, mutation vẫn chịu Java Memory Model.

Class loaders có khóa tải lớp liên quan đến **getClassLoadingLock(name)**. Một số loader hỗ trợ parallel-capable class loading; không được giả định mọi callback từ những class load khác nhau luôn tuần tự. Quan hệ gọi lồng nhau giữa transformer, reflection và loader tùy chỉnh có thể dẫn đến chờ khóa vòng hoặc reentrancy.

### 6.2. Happens-before, visibility và atomicity

- **Happens-before** giải thích khi nào một thread có bảo đảm quan sát kết quả ghi từ thread khác.
- **volatile** giúp quy định visibility/ordering cho truy cập biến tương ứng, nhưng thao tác **counter++** không trở thành nguyên tử chỉ vì biến là volatile.
- **AtomicInteger/LongAdder** phù hợp cho bộ đếm đa luồng, tùy nhu cầu truy vấn chính xác tức thời hay throughput.
- **ConcurrentHashMap** hữu ích cho cache chia sẻ; thao tác nhiều bước trên map vẫn cần thiết kế tính nhất quán cẩn thận.
- **ThreadLocal** chỉ hợp lý cho trạng thái gắn luồng và phải được dọn khi dùng pool nếu không muốn tồn đọng dữ liệu.

Ví dụ thread-safe state, dùng cùng nguyên tắc cho metrics do nhiều callback transform cập nhật:

~~~java
// File: ConcurrentStateDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentStateDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                tasks.add(executor.submit(() -> {
                    hits.incrementAndGet();
                }));
            }
            for (Future<?> task : tasks) {
                task.get(); // chờ xong, đồng thời nhận lỗi của task nếu có
            }
            System.out.println("Số lượt: " + hits.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac --release 17 ConcurrentStateDemo.java
java ConcurrentStateDemo
~~~

~~~text
Số lượt: 1000
~~~

Nếu đổi **AtomicInteger** thành **int** thường rồi tăng trực tiếp từ bốn thread, có thể mất cập nhật. **Future.get()** chỉ đợi hoàn tất và truyền kết quả/lỗi của task; nó không sửa được race condition trong phần cập nhật.

### 6.3. Kỷ luật trong transformer

Một transformer có thể chạy trên luồng đang định nghĩa lớp. Vì vậy:

1. **Giữ callback ngắn, có giới hạn và hạn chế side effect**. Tránh I/O đồng bộ lâu, khóa toàn cục, kết nối mạng, hoặc gọi ngược vào subsystem ứng dụng.
2. **Không mutate trực tiếp mảng classfileBuffer đầu vào**; khi cần sửa, tạo bytes hợp lệ mới; trả **null** nếu không sửa. Lọc đúng đối tượng bằng tên/loader/module và tránh transform chính các dependency nhạy cảm của agent.
3. **Dự kiến reentrancy và invocation đồng thời**. Chống biến đổi lặp nếu transformer có thể chạy trong nhiều lần transform/retransform; bảo vệ cache bằng cơ chế phù hợp, tránh lock order phức tạp.
4. **Không phụ thuộc vào thứ tự load cố định** giữa các thread, các loader và các thư viện. Trạng thái cần đồng nhất phải được công bố an toàn theo Java Memory Model.
5. **Xử lý lỗi tường minh**. Nếu một lớp bị transform thành bytecode không hợp lệ, lỗi có thể xuất hiện trong quá trình define/link, làm hỏng startup hoặc chức năng mà lớp đó phục vụ. Khi chưa đủ chắc chắn, không transform lớp đó.

## 7. Ví dụ tối thiểu: thấy điểm chặn class loading bằng Java agent

Ví dụ này **quan sát** transformer callback, không thay đổi bytecode. Nó liên kết kiến thức load và internal name mà không cần thư viện ngoài JDK.

~~~java
// File: TraceAgent.java
import java.lang.instrument.Instrumentation;

public final class TraceAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(
                (loader, className, classBeingRedefined, protectionDomain, classfileBuffer) -> {
                    if ("ProbeApp$Target".equals(className)) {
                        System.out.println("Agent thấy: " + className);
                    }
                    return null; // không sửa class bytes
                }
        );
    }
}
~~~

~~~java
// File: ProbeApp.java
public final class ProbeApp {
    static final class Target {
        static void ping() {
            System.out.println("App chạy");
        }
    }

    public static void main(String[] args) {
        Target.ping();
    }
}
~~~

Tạo file văn bản **agent.mf** với nội dung sau (có newline ở cuối file):

~~~text
Premain-Class: TraceAgent
~~~

Biên dịch, đóng gói rồi chạy trong một thư mục có ba file vừa tạo:

~~~bash
javac --release 17 TraceAgent.java ProbeApp.java
jar cfm trace-agent.jar agent.mf TraceAgent.class
java -javaagent:trace-agent.jar ProbeApp
~~~

Output:

~~~text
Agent thấy: ProbeApp$Target
App chạy
~~~

**Diễn giải**: JVM gọi **premain** trước **main**, agent đăng ký transformer, sau đó JVM mới định nghĩa **ProbeApp$Target** khi được dùng. Giá trị **className** sử dụng internal class name (có dấu **$** cho nested type), còn **return null** thông báo không thay đổi bytes. Chỉ đăng ký transformer không bảo đảm quan sát các lớp đã load trước đó. Trong agent thực tế, cần thêm lọc class/module/loader, tránh dependency của chính agent, kiểm tra quyền transform và thiết kế an toàn đa luồng. Nếu muốn retransform lớp đã load, cần hỏi **isRetransformClassesSupported()**, kiểm tra **isModifiableClass(...)**, cấu hình **Can-Retransform-Classes** cho agent khi cần và đăng ký transformer hỗ trợ retransform.

## 8. Bảng lỗi thường gặp và phương pháp chẩn đoán

| Triệu chứng/lỗi | Nguyên nhân nên kiểm tra trước | Bước kiểm tra |
| --- | --- | --- |
| **ClassNotFoundException** | Loader không tìm thấy tên được yêu cầu | Đúng binary name, classpath/module path, loader và delegation? |
| **NoClassDefFoundError** | Kiểu phụ thuộc thiếu ở runtime hoặc lớp từng initialize thất bại | Đọc **cause** và log lỗi đầu tiên, không chỉ thông báo cuối |
| **ClassFormatError** / **UnsupportedClassVersionError** | Class file sai cấu trúc hoặc major version vượt runtime | **javap -v**, JDK thực thi và bytes sau transform |
| **VerifyError** | Stack, frame, control flow, descriptor hoặc kiểu không hợp lệ | Disassemble bytecode; đối chiếu StackMapTable và nhánh nhảy |
| **LinkageError** / loader constraint violation | Định nghĩa/quan hệ kiểu không thống nhất giữa loader | In FQCN, **Class.getClassLoader()**, nguồn JAR và dependency graph |
| **ClassCastException** với tên lớp giống nhau | Hai defining loader khác nhau hoặc quan hệ kiểu không phù hợp | So sánh hai đối tượng **Class**, loader và module |
| **InaccessibleObjectException** | Package chưa **opens** cho module gọi reflection | Kiểm tra module của caller, **opens** và tùy chọn JVM |
| **UnmodifiableClassException** / API báo không hỗ trợ | JVM/class không cho phép retransform/redefine theo yêu cầu | Kiểm tra capability và giới hạn schema |
| Treo khi startup hay load plugin | Deadlock/reentrancy giữa class loader, transformer và static initializer | Lấy thread dump; tìm lock owner và call stack load/transform |
| Metrics sai hoặc leak sau reload | Race, cache không thread-safe hoặc giữ strong reference tới loader | Đánh giá happens-before, atomicity, lifecycle/cache cleanup |

Các công cụ nền tảng đáng biết:

~~~bash
javac --release 17 SomeClass.java
javap -c -p SomeClass
javap -v -p SomeClass
java -Xlog:class+load=info SomeClass
java --describe-module java.instrument
~~~

Các lệnh trên mang tính minh họa; **SomeClass.java** cần tồn tại. **-Xlog:class+load=info** có thể cho ra rất nhiều dòng; hãy lọc log theo lớp mục tiêu thay vì coi mọi lớp được load là do transformer của mình. Một **thread dump** bằng công cụ phù hợp (ví dụ **jcmd** trên JVM hỗ trợ) thường hữu ích hơn việc thêm log ngay giữa đoạn code có nguy cơ deadlock.

## 9. Checklist trước khi học hoặc viết instrumentation nâng cao

- Tôi chỉ rõ **lớp mới tải** hay **lớp đã được định nghĩa**, và biết tại sao đăng ký transformer muộn có thể không tác động tới lớp cũ.
- Tôi phân biệt **load/link/initialize**; không kỳ vọng retransform chạy lại constructor hoặc **<clinit>**.
- Tôi đọc được **class file version, constant pool, Code, instruction, stack frame** và hiểu khi nào JVM ném **VerifyError**.
- Tôi gắn mỗi class với đúng **defining loader**, xử lý loader **null** và tránh giữ loader trong cache vô thời hạn.
- Tôi biết module đích có **reads/exports/opens** thích hợp; không dùng reflection sâu khi chưa có quyền.
- Tôi biết callback có thể bị gọi đồng thời/tái nhập, bảo vệ shared state và tránh I/O/lock vòng trong đường class loading.
- Tôi có cách quan sát lỗi bằng **javap**, class-load log, stack trace/thread dump và chạy thử trên đúng JDK.

### Câu hỏi tự kiểm tra

1. **Tại sao đọc Target.CONSTANT không nhất thiết chạy Target.<clinit>?** Vì đây là compile-time constant; bytecode bên gọi có thể sử dụng giá trị đã nhúng.
2. **Hai class có FQCN giống nhau có luôn cast qua lại được không?** Không; defining class loader là một phần của danh tính kiểu.
3. **exports có đủ để đọc private field qua setAccessible(true) không?** Không; deep reflection cần điều kiện truy cập và package được **opens** phù hợp.
4. **Tại sao volatile counter++ vẫn có thể sai?** Vì phép đọc–cộng–ghi không nguyên tử; nhiều luồng có thể mất cập nhật.
5. **Vì sao một transformer được cài sau startup không tự sửa toàn bộ lớp đã nạp?** Transformer thấy các định nghĩa lớp về sau; lớp đã load cần cơ chế retransform/redefine được JVM hỗ trợ.
6. **Nếu có VerifyError sau khi thêm logging, nên kiểm tra gì?** Control flow, kiểu trên operand stack, max_stack/max_locals, descriptor, exception table và stack map frames.

## 10. Tài liệu chuẩn để đối chiếu

- [JVM Specification Java SE 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JVM Specification Java SE 17 — The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [JLS 17 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [Java 17 Instrumentation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 ClassFileTransformer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)

Các ví dụ dùng public API của Java 17, không cần bật preview feature. Khi chuyển sang runtime/JDK khác, cần kiểm tra lại capability của Instrumentation, quyền module và chính sách nạp agent tương ứng.
