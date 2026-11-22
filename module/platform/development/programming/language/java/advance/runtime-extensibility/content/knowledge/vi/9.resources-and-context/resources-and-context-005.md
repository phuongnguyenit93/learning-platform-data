# Đặt và khôi phục Thread Context Class Loader bằng try/finally tại ranh giới gọi

Trong ứng dụng Java hỗ trợ plugin, một lời gọi vào thư viện hoặc plugin đôi khi cần tìm class, service provider hay resource từ **ClassLoader của plugin**, thay vì chỉ từ classpath của host. Cơ chế **Thread Context Class Loader (TCCL)** cho phép code đang chạy hỏi "ngữ cảnh class loader của thread hiện tại là gì?" và sử dụng loader đó cho việc tìm kiếm.

TCCL rất hữu ích ở ranh giới host → plugin → thư viện, nhưng nó là **trạng thái có thể thay đổi gắn với một Thread**. Nếu host đặt TCCL sang loader của plugin mà quên khôi phục, request tiếp theo trên cùng thread có thể nhìn thấy nhầm class/resource, còn class loader cũ có nguy cơ bị giữ sống lâu hơn dự kiến. Quy tắc nền tảng là: **lưu loader cũ, đặt loader cần dùng, thực hiện công việc trong try, và khôi phục loader cũ trong finally**.

Bài học tập trung vào ranh giới gọi đồng bộ, giải thích điều gì thực sự sử dụng TCCL, ví dụ Java 17+ tự biên dịch được, lỗi thường gặp và cách chuyển cùng nguyên tắc sang task chạy trên thread pool.

## 1. Phân biệt TCCL với ClassLoader định nghĩa class

Java có nhiều đường chọn loader. Không phải thao tác nạp class nào cũng lấy TCCL:

| Đường truy cập | Loader liên quan | Ý nghĩa |
| --- | --- | --- |
| Thread.currentThread().getContextClassLoader() | Ngữ cảnh hiện tại của **thread đang chạy** | Thư viện có thể dùng để tra cứu class, provider và resource |
| Thread.currentThread().setContextClassLoader(loader) | Thay TCCL của **thread hiện tại** | Không tự nạp class, không thay loader đã định nghĩa các class |
| ServiceLoader.load(MyService.class) | Theo Java 17: dùng TCCL của thread gọi | Provider trong loader plugin có thể được tìm khi TCCL trỏ đúng loader |
| ServiceLoader.load(MyService.class, loader) | Dùng loader được truyền rõ ràng | Hữu ích nếu chỉ một lookup cần plugin loader, không phải toàn bộ call chain |
| SomeType.class.getClassLoader() | Loader đã định nghĩa SomeType | Không đổi chỉ vì thread chuyển TCCL |
| SomeType.class.getResourceAsStream("/path") | Tìm resource theo loader của SomeType | Phù hợp khi resource thuộc chính implementation |
| contextLoader.getResourceAsStream("path") | Tìm resource qua loader được chỉ định | Phù hợp khi framework dùng resource của plugin theo ngữ cảnh |

**Class identity** phụ thuộc vào tên binary **và loader định nghĩa class**. Đặt TCCL không biến một class đã nạp bởi host thành class do plugin loader định nghĩa. Nếu host và plugin trao đổi đối tượng qua interface SPI, interface đó phải có danh tính class chung; thông thường loader plugin có parent nhìn thấy SPI do host cung cấp.

TCCL không phải classpath toàn JVM, cũng không phải sandbox bảo mật. TCCL chỉ ảnh hưởng đến các API **thực sự tham khảo TCCL**; nhiều lời gọi nạp class/resource khác chọn loader theo cách riêng. Đừng cho rằng mọi lỗi ClassNotFoundException sẽ biến mất sau khi đặt TCCL.

## 2. Vì sao phải đặt ở ranh giới gọi và khôi phục ngay?

Giả sử host có hai plugin A và B. Cả hai được nạp bằng URLClassLoader khác nhau; cùng có file config/defaults.properties, nhưng dữ liệu khác nhau. Khi framework gọi code của plugin A, một thư viện bên trong sử dụng Thread.currentThread().getContextClassLoader() để tìm resource. Nếu TCCL vẫn trỏ về host loader, thư viện có thể không thấy resource của A. Nếu host đặt TCCL = loaderA và quên trả lại, lượt gọi B trên cùng thread có thể tìm nhầm resource của A.

Mẫu đúng cho công việc **đồng bộ trên cùng thread**:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
current.setContextClassLoader(pluginLoader);

try {
    // Toàn bộ lời gọi cần ngữ cảnh plugin nằm trong phạm vi này.
    invokePlugin();
} finally {
    current.setContextClassLoader(previous);
}
~~~

Đoạn mã trên là **mã minh họa ranh giới gọi**, giả định pluginLoader và invokePlugin() đã được xác định bởi host. finally chạy khi thân try trả về bình thường, return sớm, ném checked exception, RuntimeException hoặc Error trong điều kiện JVM tiếp tục thực thi thông thường. Đây là lý do không đặt khôi phục chỉ ở cuối nhánh thành công.

Thứ tự thực thi cần giữ:

1. Lấy **chính xác loader trước đó**; giá trị có thể là null và null cũng cần được khôi phục nguyên trạng.
2. Đặt loader của plugin ngay trước lời gọi cần ngữ cảnh đó.
3. Đưa mọi thao tác cần TCCL, kể cả bước khởi tạo provider theo cách lazy, vào **phạm vi try**.
4. Trong finally, khôi phục loader đã lưu, không mặc định thay bằng ClassLoader.getSystemClassLoader() hay loader của host.
5. Chỉ đóng loader và giải phóng tài nguyên plugin **sau khi** các lời gọi đang dùng nó hoàn tất.

Lưu ý: setContextClassLoader có thể ném SecurityException trong môi trường dùng chính sách SecurityManager (liên quan đặc biệt tới Java 17 và các ứng dụng cũ). Nếu việc **đặt** loader thất bại trước khi vào try, host phải coi đây là lỗi thiết lập ngữ cảnh; đừng tiếp tục gọi plugin rồi giả định TCCL đã được đổi. Mẫu trên không cố xử lý việc chương trình bị kết thúc cưỡng bức hoặc JVM không còn khả năng chạy finally.

## 3. Một phương thức dùng lại cho mọi lời gọi đồng bộ

Thay vì rải các cặp set/restore trong nhiều controller và adapter, host có thể cung cấp một helper nhỏ. Dùng Callable<T> để giữ kết quả trả về và cho phép ngoại lệ checked được truyền ra:

~~~java
import java.util.concurrent.Callable;

static <T> T withContextClassLoader(ClassLoader next, Callable<T> action)
        throws Exception {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    thread.setContextClassLoader(next);
    try {
        return action.call();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
~~~

Đây là đoạn mã thành viên của một class, không phải file Java độc lập. Đoạn lab ở phần sau sẽ đưa phương thức này vào một chương trình biên dịch được.

Các thuộc tính quan trọng:

- Helper chạy **action trên cùng thread đã gọi helper**. Nó không tự tạo thread mới hay chuyển công việc sang Executor.
- Nếu action.call() ném ngoại lệ, finally vẫn khôi phục loader trước khi ngoại lệ tiếp tục truyền về caller.
- Nếu lời gọi khác ở bên trong cũng đổi TCCL theo mẫu chuẩn, hai lớp try/finally sẽ **khôi phục theo thứ tự ngược** (LIFO).
- Helper **không tự đóng** ClassLoader. Ownership và vòng đời của pluginLoader là trách nhiệm riêng của plugin manager.
- Nếu code trong action tự đổi TCCL, finally vẫn đưa thread về previous. Vì vậy phải đặt ranh giới đúng quanh lời gọi mà host thực sự sở hữu.

Trong Java, finally có thể tự ném lỗi, ví dụ khi thao tác khôi phục bị từ chối. Khi đó lỗi khôi phục có thể che lỗi gốc; đây là sự cố môi trường/cấu hình cần quan sát ở lớp quản lý host, không phải tình huống để âm thầm bỏ qua.

## 4. Lab Java 17+: host nhìn thấy plugin sau khi chuyển TCCL

Thí nghiệm dưới đây tạo **hai artifact độc lập**: api.jar trên classpath host và hello-plugin.jar chỉ được đưa vào URLClassLoader ở runtime. Bên trong hello-plugin.jar có một provider của ServiceLoader và một file resource riêng. Host sử dụng đúng phương thức withContextClassLoader để gọi provider, đọc resource và mô phỏng một ngoại lệ.

### 4.1. Cấu trúc thư mục

Từ thư mục gốc **lab/**:

~~~text
lab/
├── src/
│   ├── api/dev/example/spi/Greeter.java
│   ├── plugin/dev/example/impl/HelloGreeter.java
│   └── host/dev/example/host/Demo.java
├── resources/
│   ├── META-INF/services/dev.example.spi.Greeter
│   └── config/message.txt
├── build/             (tạo khi biên dịch)
└── dist/              (tạo khi đóng gói)
~~~

Chỉ cần JDK 17 trở lên với javac, jar, java. Các lệnh build trình bày theo bash/POSIX; trên Windows dùng bash tương thích hoặc chuyển lệnh tạo thư mục và dấu phân cách classpath cho shell đang sử dụng.

### 4.2. Interface SPI thuộc API chung

File **src/api/dev/example/spi/Greeter.java**:

~~~java
package dev.example.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Host và plugin đều tham chiếu interface này. Khi tạo URLClassLoader, host chọn loader đã định nghĩa Greeter làm parent, để provider thấy **cùng bản SPI**, tránh ClassCastException hoặc ServiceConfigurationError vì hai bản SPI khác loader.

### 4.3. Provider do plugin cung cấp

File **src/plugin/dev/example/impl/HelloGreeter.java**:

~~~java
package dev.example.impl;

import dev.example.spi.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

File **resources/META-INF/services/dev.example.spi.Greeter** có đúng một dòng:

~~~text
dev.example.impl.HelloGreeter
~~~

File **resources/config/message.txt**:

~~~text
plugin-message
~~~

META-INF/services phải nằm ở **gốc JAR**. Tên file descriptor là tên binary của SPI; nội dung là tên binary của provider. Resource config/message.txt cũng phải là entry ở gốc JAR, không mang tiền tố resources/. Để thấy rõ tác động của TCCL, host sẽ đọc resource bằng loader lấy từ thread thay vì dùng đường dẫn file trên đĩa.

### 4.4. Host tạo plugin loader, đặt TCCL, gọi và khôi phục

File **src/host/dev/example/host/Demo.java**:

~~~java
package dev.example.host;

import dev.example.spi.Greeter;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.concurrent.Callable;

public final class Demo {
    private static <T> T withContextClassLoader(
            ClassLoader next, Callable<T> action) throws Exception {
        Thread current = Thread.currentThread();
        ClassLoader previous = current.getContextClassLoader();
        current.setContextClassLoader(next);
        try {
            return action.call();
        } finally {
            current.setContextClassLoader(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Demo <path-to-plugin-jar>");
        }

        Thread current = Thread.currentThread();
        ClassLoader original = current.getContextClassLoader();
        System.out.println("before original: "
                + (current.getContextClassLoader() == original));

        long withoutPlugin = ServiceLoader.load(Greeter.class)
                .stream()
                .count();
        System.out.println("providers outside: " + withoutPlugin);

        URL pluginUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl}, Greeter.class.getClassLoader())) {

            withContextClassLoader(pluginLoader, () -> {
                System.out.println("inside plugin loader: "
                        + (Thread.currentThread().getContextClassLoader()
                                == pluginLoader));

                int count = 0;
                for (Greeter provider : ServiceLoader.load(Greeter.class)) {
                    System.out.println("provider: " + provider.greet("Java"));
                    count++;
                }
                if (count != 1) {
                    throw new IllegalStateException(
                            "Expected one provider, got " + count);
                }

                ClassLoader context =
                        Thread.currentThread().getContextClassLoader();
                try (InputStream input =
                        context.getResourceAsStream("config/message.txt")) {
                    if (input == null) {
                        throw new IllegalStateException("Missing plugin resource");
                    }
                    String message = new String(
                            input.readAllBytes(), StandardCharsets.UTF_8).strip();
                    System.out.println("resource: " + message);
                }
                return null;
            });

            System.out.println("after success: "
                    + (current.getContextClassLoader() == original));

            try {
                withContextClassLoader(pluginLoader, () -> {
                    throw new IllegalArgumentException("simulated failure");
                });
            } catch (IllegalArgumentException expected) {
                System.out.println("caught: " + expected.getMessage());
            }

            System.out.println("after failure: "
                    + (current.getContextClassLoader() == original));
        }

        System.out.println("after close: "
                + (current.getContextClassLoader() == original));
    }
}
~~~

**Điểm mấu chốt của chương trình:**

- Classpath của lệnh chạy **không chứa hello-plugin.jar**. Host không thể tìm provider plugin thông qua loader ứng dụng mặc định; lúc chưa chuyển TCCL, ServiceLoader không thấy provider của plugin.
- new URLClassLoader(..., Greeter.class.getClassLoader()) mở một không gian tìm class/resource có chứa plugin JAR, đồng thời ủy quyền SPI cho loader chung. Tạo plugin loader **chưa tự thay TCCL**.
- Khi withContextClassLoader đặt TCCL = pluginLoader, ServiceLoader.load(Greeter.class) sử dụng context loader và có thể tìm descriptor bên trong hello-plugin.jar.
- ClassLoader context.getResourceAsStream("config/message.txt") tìm resource bằng chính loader từ TCCL. Đường dẫn truyền cho ClassLoader không có dấu / ở đầu.
- Return bình thường hay IllegalArgumentException đều chạy finally để khôi phục exact original.
- try-with-resources đóng URLClassLoader **sau** khi các lời gọi sử dụng nó đã hoàn tất và TCCL đã được khôi phục.

Chú ý việc đóng URLClassLoader không cưỡng bức unload class hay hủy mọi instance/provider. Một plugin manager thực tế chỉ đóng loader sau khi không còn request, task, callback, cache hoặc object thuộc plugin đang hoạt động.

### 4.5. Biên dịch và chạy

Từ thư mục **lab/**, chạy các lệnh bash:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac -encoding UTF-8 -d build/api src/api/dev/example/spi/Greeter.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/plugin src/plugin/dev/example/impl/HelloGreeter.java
jar --create --file dist/hello-plugin.jar -C build/plugin . -C resources .

javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/dev/example/host/Demo.java
java -cp "build/host:build/api.jar" dev.example.host.Demo dist/hello-plugin.jar
~~~

**Stdout kỳ vọng khi chạy đúng cấu trúc trên, không có provider cùng SPI từ nơi khác trong host classpath:**

~~~text
before original: true
providers outside: 0
inside plugin loader: true
provider: Hello, Java
resource: plugin-message
after success: true
caught: simulated failure
after failure: true
after close: true
~~~

Dòng providers outside: 0 xuất hiện vì host runtime classpath của lệnh minh họa chỉ có host classes và api.jar. Nếu người học **tự thêm plugin JAR vào host classpath**, không còn đúng điều kiện thí nghiệm và kết quả discovery ở ngoài có thể khác.

Trên Windows, trong tham số -cp phân cách các entry bằng dấu **;** thay cho dấu **:**; riêng cú pháp mkdir -p là của bash. Khi dùng PowerShell, có thể tạo thư mục bằng New-Item -ItemType Directory -Force rồi giữ các lệnh javac, jar, java với classpath dùng dấu chấm phẩy.

Kiểm tra JAR trước khi chạy:

~~~bash
jar --list --file dist/hello-plugin.jar
~~~

Trong output phải có các entry quan trọng:

~~~text
dev/example/impl/HelloGreeter.class
META-INF/services/dev.example.spi.Greeter
config/message.txt
~~~

Đây là **ba entry cần xác nhận**, không phải toàn bộ stdout của jar; công cụ có thể liệt kê thêm manifest và các thư mục. Nếu thiếu descriptor, ServiceLoader không tìm provider. Nếu thiếu resource, host sẽ báo Missing plugin resource dù provider có thể nạp thành công. Hai lỗi này khác hoàn toàn việc quên khôi phục TCCL.

## 5. Phân tích từng bước của ranh giới gọi

Diễn biến của ví dụ có thể hình dung:

~~~text
Thread main
    TCCL = original
       |
       | tạo pluginLoader (chưa thay TCCL)
       v
    withContextClassLoader(pluginLoader)
       | lưu previous = original
       | set TCCL = pluginLoader
       |  ServiceLoader.load(Greeter.class)
       |  plugin resource lookup
       |  invoke provider.greet(...)
       | finally: TCCL = original
       v
    Thread main: TCCL = original
       |
       | vào lần gọi thứ hai
       | set pluginLoader
       | throw IllegalArgumentException
       | finally: TCCL = original
       v
    Thread main: TCCL = original
       |
       | hoàn thành work và đóng pluginLoader
       v
    Thread main: TCCL vẫn = original
~~~

Tại thời điểm finally chạy, **action có thể chưa trả kết quả cho caller** hoặc có thể đang lan truyền ngoại lệ. finally vẫn khôi phục trước khi caller tiếp tục xử lý. Nếu caller dùng thread pool, điều này rất quan trọng: worker thread có thể lập tức nhận công việc của plugin khác.

Nguyên tắc còn giúp tránh **class loader retention**. TCCL là một tham chiếu từ Thread tới ClassLoader. Nếu thread tồn tại lâu, giữ loader của plugin đã gỡ trong TCCL có thể giữ cả các class và đối tượng liên quan sống lâu. Khôi phục TCCL giải phóng một đường tham chiếu quan trọng; vẫn phải xử lý những reference khác như thread con, registry, ThreadLocal và cache.

## 6. Gọi lồng nhau: khôi phục chính xác theo thứ tự LIFO

Giả sử host gọi plugin A, bên trong A lại gọi một adapter cần plugin B. Phạm vi B phải khôi phục về **A**, sau đó phạm vi A mới khôi phục về original:

~~~java
// Mã minh họa, giả định đã có withContextClassLoader,
// loaderA, loaderB và phương thức callA()/callB().
withContextClassLoader(loaderA, () -> {
    callA(); // TCCL = loaderA
    withContextClassLoader(loaderB, () -> {
        callB(); // TCCL = loaderB
        return null;
    });
    callA(); // TCCL trở về loaderA
    return null;
});
// Ở đây TCCL trở về loader trước khi gọi A.
~~~

Mỗi phạm vi lưu loader thực tế tại thời điểm **bắt đầu phạm vi đó**. Không dùng biến toàn cục "default loader" để khôi phục, vì nó không thể biểu diễn chính xác ngữ cảnh lồng nhau.

Nếu callB() ném exception, finally của B vẫn chạy, đưa TCCL về loaderA, rồi exception có thể đi qua finally của A và đưa TCCL về original. Đây là tính chất của mô hình stack các ranh giới gọi đồng bộ. Tránh gọi setContextClassLoader trong các nhánh điều kiện mà không có finally tương ứng.

## 7. Khi chuyển sang executor và tác vụ bất đồng bộ

**TCCL thuộc về thread**, không thuộc về request, CompletableFuture hay đối tượng plugin. Đặt TCCL trên thread gửi công việc không đảm bảo công việc chạy trên thread đó.

Phản ví dụ:

~~~java
// Phản ví dụ: executor có thể chạy task trên thread khác.
Thread.currentThread().setContextClassLoader(pluginLoader);
try {
    executor.submit(task);
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
~~~

Nếu executor đã có worker thread, task sẽ chạy với TCCL của **worker**, có thể không phải pluginLoader. Một thread mới có thể thừa hưởng TCCL của thread tạo nó, nhưng cơ chế kế thừa này không giải quyết việc worker tồn tại lâu, tái sử dụng hoặc thay đổi ngữ cảnh giữa các tác vụ. Tệ hơn, tạo thread mới bên trong phạm vi TCCL tạm thời có thể khiến thread con giữ plugin loader lâu sau khi parent đã khôi phục.

Đúng hơn, **đặt và khôi phục ngay bên trong task khi worker thực sự chạy**:

~~~java
// Mã minh họa: executor, pluginLoader, task và previous đã được định nghĩa.
// Helper Callable<T> là phương thức ở phần 3.
Future<?> future = executor.submit(() -> {
    withContextClassLoader(pluginLoader, () -> {
        task.run();
        return null;
    });
    return null;
});
future.get(); // Chờ task hoàn thành trước khi đóng pluginLoader.
~~~

Ở đoạn này, lambda được chạy trên worker thread; withContextClassLoader đọc TCCL **của worker** tại thời điểm bắt đầu task và khôi phục nó trong finally. Future.get() chuyển kết quả/lỗi về thread gọi nhưng không làm thay đổi TCCL của thread gọi. Trong sản phẩm thực tế, cần xử lý InterruptedException, ExecutionException, timeout và hủy task theo lifecycle; không chờ vô hạn tùy tiện.

Để code trên biên dịch khi đứng độc lập trong class chứa nó, cần các import java.util.concurrent.Future và các biến executor, task, pluginLoader có kiểu phù hợp; đây là **minh họa tích hợp** chứ không phải chương trình hoàn chỉnh thứ hai.

**CompletableFuture:** supplyAsync/runAsync và callback async thường chạy trên executor hoặc thread khác. Nếu callback cần TCCL của plugin, phải bọc **chính callback** bằng ranh giới thiết lập/khôi phục trên thread thực thi callback. Không giả định context được tự lan truyền. Với callback không async, có trường hợp callback chạy trên thread hoàn thành stage, vì vậy cần đặc biệt rõ thread nào đang thực hiện mã.

**Executor sống lâu:** chỉ giữ reference tới pluginLoader trong những tác vụ đang thuộc vòng đời plugin. Không cache wrapper hoặc lambda giữ loader của plugin đã gỡ trong hàng đợi vô thời hạn; khi stop/reload, dừng nhận task mới, hủy/đợi task cũ, hủy đăng ký callback rồi mới đóng loader.

## 8. Khi nào cần TCCL, khi nào dùng loader tường minh?

Nếu API cho truyền loader một cách rõ ràng, đây thường là giải pháp ít phụ thuộc vào trạng thái ngầm hơn:

~~~java
// Khi chỉ cần ServiceLoader tìm provider:
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
~~~

Đoạn này là **minh họa** dùng các biến đã giới thiệu trong lab. Lời gọi ServiceLoader.load(service, loader) dùng pluginLoader cho việc tìm provider mà không cần sửa TCCL của thread. Tuy vậy, nếu constructor hoặc phương thức của provider gọi tới một thư viện **tự lấy TCCL**, truyền loader ở một lời gọi ServiceLoader chưa đủ để thiết lập ngữ cảnh cho toàn bộ call chain.

Lựa chọn theo từng tầng:

- **Truy vấn cục bộ có API nhận ClassLoader:** truyền tham số loader nếu phù hợp, tránh đổi TCCL không cần thiết.
- **Thư viện/framework chọn TCCL theo hợp đồng:** đặt TCCL bao quanh lời gọi đồng bộ mà host sở hữu, dùng try/finally.
- **Resource thuộc implementation cụ thể:** cân nhắc SomeProvider.class.getResourceAsStream("/path") để tra cứu theo defining loader của implementation, không phụ thuộc ambient TCCL.
- **Nhiều plugin với loader riêng:** duy trì SPI do loader dùng chung nạp; TCCL chỉ giúp framework chọn đường tìm, không sửa được sự cố class identity giữa các bản SPI khác loader.
- **Nghiệp vụ chạy bất đồng bộ:** chuyển ranh giới vào thread thực thi task, không đặt ở thread gửi task rồi giả định lan truyền.

Một chi tiết dễ bỏ qua: ServiceLoader có tính **lazy**. Nếu host đặt TCCL, tạo ServiceLoader.load(...), rồi khôi phục trước khi gọi iterator, việc tìm provider có thể phụ thuộc vào loader đã được ServiceLoader nắm giữ ở thời điểm tạo. Nhưng provider implementation sau đó có thể dùng TCCL khi khởi tạo hoặc xử lý, nên vẫn phải xác định **ranh giới thực sự chạy code cần TCCL**, không chỉ bọc thao tác tạo ServiceLoader rồi mặc định mọi bước đã xong.

## 9. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Plugin A chạy xong, request B thấy resource của A | Quên restore hoặc khôi phục về loader sai | Lưu previous ngay tại đầu boundary, restore bằng finally |
| ServiceLoader không tìm thấy provider dù JAR có descriptor | TCCL đang là host loader, plugin không có trong đường tìm | Chỉ rõ pluginLoader qua overload hoặc đặt TCCL quanh lookup |
| Provider tìm thấy nhưng ném lỗi khi chạy callback | Callback chạy trên thread khác hoặc framework tìm resource bằng TCCL khác | Đặt/khôi phục TCCL trong thread thực thi callback |
| Plugin có thể nạp nhưng host gặp ClassCastException | SPI bị định nghĩa lại bởi loader khác | Chia sẻ một bản SPI có đúng class identity; kiểm tra parent/delegation |
| Xóa plugin nhưng loader chưa được giải phóng | Thread pool, TCCL, task, cache hoặc provider instance còn giữ reference | Dừng lifecycle đúng thứ tự, cleanup rồi mới đóng loader |
| Khôi phục bằng system class loader vẫn gặp lỗi khi gọi lồng nhau | Previous có thể là loader A hoặc null, không phải system loader | Khôi phục **giá trị previous đã lưu** |
| Gọi setContextClassLoader bên ngoài try rồi action throw | Thiếu finally, thread bị lưu ngữ cảnh cũ | Bao action trong try/finally, kiểm thử cả nhánh lỗi |
| Đặt TCCL nhưng class loader vẫn không tìm được class | API đang dùng defining/caller loader hoặc JAR/dependency không nằm trong plugin loader | Xác định API lookup thực tế và dependency graph |
| SecurityException khi setContextClassLoader | Quyền đổi TCCL không được cấp trong môi trường áp dụng kiểm soát | Báo lỗi thiết lập ngữ cảnh, không tiếp tục như thể đã đổi thành công |
| Thời điểm đóng URLClassLoader quá sớm | Còn task/provider/resource đang hoạt động | Chờ hoàn thành tác vụ và cleanup lifecycle trước khi đóng |

**Đừng bắt Throwable chỉ để "bảo đảm restore".** finally sẽ khôi phục trong luồng thoát thông thường của Java, kể cả khi action ném RuntimeException hoặc Error, miễn JVM vẫn thực hiện finally. Catch rộng Throwable rồi nuốt lỗi có thể che các sự cố nghiêm trọng. Nếu cần bắt lỗi nghiệp vụ, hãy bắt các kiểu lỗi có ý nghĩa **bên ngoài** ranh giới withContextClassLoader, sau khi TCCL đã được phục hồi.

## 10. Kiểm thử hành vi khôi phục và tính độc lập giữa các plugin

Một bài test TCCL tốt kiểm chứng **danh tính loader bằng toán tử ==**, không chỉ so sánh tên class hoặc toString(). Trong lab, các dòng inside plugin loader, after success, after failure và after close đều in true. Điều đó chứng minh trong đúng thread thực thi, ranh giới đã đổi và phục hồi TCCL theo ý muốn.

Các phép thử có giá trị:

1. **Success path:** gọi provider và resource trong phạm vi plugin; xác nhận tất cả được tìm bằng loader mong muốn, và TCCL sau khi return trùng original.
2. **Exception path:** action ném IllegalArgumentException hoặc exception nghiệp vụ; caller bắt lỗi và kiểm tra TCCL trùng original. Không đặt restore chỉ trong catch hoặc nhánh thành công.
3. **Nested calls:** đặt loaderA, gọi lồng loaderB, xác nhận sau B trở về A, sau A trở về original, kể cả khi B ném lỗi.
4. **Reused worker thread:** gửi liên tiếp task của plugin A và B tới cùng một worker; sau mỗi task phải trở về TCCL trước khi task bắt đầu. Cần tránh dùng thread pool chung theo cách khiến plugin tạo worker bên trong phạm vi ngữ cảnh tạm thời.
5. **Absent plugin resource:** bỏ config/message.txt khỏi JAR, xác nhận lỗi được báo rõ nhưng finally vẫn khôi phục TCCL.
6. **Plugin unload:** dừng các task, hủy callback, loại reference và đóng pluginLoader; kiểm tra thread còn sống không giữ loader cũ qua TCCL. Không suy luận rằng loader đã unload ngay chỉ vì close() được gọi.

Ví dụ assertion không cần JUnit trong một đoạn test cục bộ:

~~~java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    withContextClassLoader(pluginLoader, () -> {
        throw new IllegalStateException("check");
    });
} catch (IllegalStateException expected) {
    if (!"check".equals(expected.getMessage())) {
        throw expected;
    }
}
if (thread.getContextClassLoader() != before) {
    throw new AssertionError("TCCL was not restored");
}
~~~

Đây là **mã thành viên minh họa** trong phạm vi có sẵn withContextClassLoader và pluginLoader. Nó chứng minh logic quan trọng: nếu code làm việc gặp lỗi, test vẫn kiểm tra được TCCL sau khi lỗi được truyền ra.

## 11. Quy tắc áp dụng trong host/plugin manager

Một host có thể đóng gói logic TCCL tại một nơi, ví dụ tầng adapter gọi plugin. Thiết kế đó cần xác định rõ: **ai sở hữu plugin loader, lời gọi nào thực sự cần context, thread nào chạy lời gọi, và khi nào loader có thể đóng**.

Một chuỗi thực thi hợp lý:

1. Khởi tạo hoặc chọn plugin loader đã được xác minh, có parent chia sẻ API/SPI và dependency đúng.
2. Xác định boundary đồng bộ gọi provider, callback hoặc framework vốn dùng TCCL; ưu tiên truyền loader rõ ràng nếu API cho phép.
3. Trên thread đang thực hiện lời gọi, lưu current TCCL rồi đặt pluginLoader.
4. Chạy trọn các thao tác cần ngữ cảnh (lazy lookup, provider construction, method invocation, resource read).
5. Khôi phục previous trong finally, bất kể kết quả hay exception.
6. Chuyển sang thread khác thì lặp lại boundary **trong task thực thi**, không dựa vào TCCL của thread gọi.
7. Khi gỡ plugin, ngừng nhận việc mới, kết thúc task và callback, loại reference còn giữ loader rồi đóng loader.

TCCL là cơ chế **định tuyến ngữ cảnh nạp class/resource theo thread**, không phải sự thay đổi classpath toàn cục hay một hàng rào bảo mật. Tài liệu Java SE 17 cần đọc thêm: [Thread.getContextClassLoader/setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html), [ServiceLoader.load](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

Hãy luôn giữ nguyên tắc **lưu đúng previous → đặt đúng pluginLoader → chạy đúng phạm vi → khôi phục previous bằng finally**. Chính độ chặt chẽ của ranh giới này giúp nhiều plugin dùng chung thread pool mà không làm rò rỉ ngữ cảnh và giảm nguy cơ giữ class loader sau khi plugin ngừng hoạt động.