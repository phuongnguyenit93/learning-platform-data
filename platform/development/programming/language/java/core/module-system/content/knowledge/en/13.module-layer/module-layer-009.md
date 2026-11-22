# Vòng đời và khả năng thu hồi của custom layer trong Java Module System

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích khi nào một custom `ModuleLayer` được tạo, sử dụng và trở thành đối tượng có thể thu gom rác.
- Phân biệt vòng đời của `ModuleLayer`, `ClassLoader`, đối tượng plugin và metadata của lớp trong JVM.
- Thiết kế thao tác dừng plugin để không vô tình giữ lại các module của layer cũ.
- Nhận biết các nguồn tham chiếu mạnh và cách quan sát hiện tượng class unloading.
- Hiểu vì sao không có lệnh `close()` hay `unload()` tức thời dành cho `ModuleLayer`.

Ví dụ dùng Java 17+ và JPMS (Java Platform Module System). Cơ chế cốt lõi áp dụng cho các JDK hiện đại có hỗ trợ `ModuleLayer`.

## 2. Custom ModuleLayer sống và kết thúc như thế nào?

`ModuleLayer` là một tập các module được gắn với một `Configuration`, có quan hệ cha với một hoặc nhiều layer và có ánh xạ từ module đến class loader. Layer boot (`ModuleLayer.boot()`) chứa các module của môi trường chạy ban đầu. Ứng dụng có thể định nghĩa thêm layer để nạp một tập module tại thời điểm chạy, chẳng hạn module plugin hoặc phiên bản thành phần được cô lập.

Một vòng đời ứng dụng điển hình:

1. **Khám phá module:** dùng `ModuleFinder` tìm các module trong JAR hoặc thư mục module.
2. **Resolve:** tạo `Configuration` từ cấu hình của layer cha và tập module gốc.
3. **Define layer:** định nghĩa module và class loader tương ứng bằng API của `ModuleLayer`.
4. **Khởi tạo và sử dụng:** nạp provider bằng `ServiceLoader`, tạo đối tượng, gọi nghiệp vụ.
5. **Dừng sử dụng:** dừng task, thread, bộ lập lịch, đóng tài nguyên và ngừng đăng ký callback.
6. **Bỏ tham chiếu mạnh:** xóa cache, registry, danh sách provider và các tham chiếu ngoài còn giữ layer hoặc class loader.
7. **GC và class unloading (nếu đủ điều kiện):** JVM có thể thu hồi đối tượng Java, sau đó thu hồi metadata lớp của class loader đã không còn sống tại một đợt GC thích hợp.

**Điểm then chốt:** Layer không sở hữu một cơ chế hủy chủ động. API `ModuleLayer` không cung cấp `close()`, `dispose()` hoặc `unload()`. Việc một layer không còn được chương trình sử dụng chỉ mở ra khả năng thu gom rác; không bảo đảm bộ nhớ được giải phóng ngay tại thời điểm đó.

### Ba vòng đời cần phân biệt

| Thành phần | Điều kiện còn sống | Ý nghĩa khi kết thúc |
| --- | --- | --- |
| Đối tượng `ModuleLayer` | Còn được truy cập từ GC root qua các tham chiếu mạnh | Bản thân đối tượng layer có thể được GC khi không còn reachable |
| Class loader định nghĩa module trong layer | Còn reachable trực tiếp hoặc gián tiếp qua thread, lớp, đối tượng, cache, layer khác... | Khi class loader không còn sống và JVM thực hiện class unloading, các lớp do loader đó định nghĩa có thể được dỡ |
| Instance và tài nguyên của plugin | Còn người sử dụng giữ tham chiếu; thread, stream, socket, executor... còn hoạt động | Cần dừng/đóng đúng hợp đồng nghiệp vụ; GC không thay thế việc dọn tài nguyên |

Thu gom `ModuleLayer` **không đồng nghĩa** với việc mọi lớp hoặc tài nguyên của plugin đã được giải phóng. Ngược lại, nếu lớp, loader và instance còn bị giữ bởi các nguồn bên ngoài thì layer cũ có thể tiếp tục tồn tại qua các quan hệ tham chiếu hoặc phần lớn bộ nhớ của nó vẫn chưa thể thu hồi.

## 3. Quan hệ tham chiếu quyết định khả năng thu hồi

Hãy nhìn custom layer như một đồ thị đối tượng, không phải một tiến trình riêng có nút tắt:

~~~text
GC roots (thread đang chạy, static của module tồn tại lâu, registry, ...)
    |
    +-- PluginRegistry --> PluginSession --> ModuleLayer
    |                                        |--> Configuration
    |                                        +--> Module / ClassLoader
    |
    +-- Thread.contextClassLoader ------------> ClassLoader plugin
    |
    +-- Cache<Class<?>, Object> --------------> Class<?> của plugin
    |
    +-- Listener / callback ------------------> instance của plugin
                                                 |
                                                 +--> Class<?> --> defining ClassLoader
~~~

Các mũi tên trên minh họa **những đường giữ tham chiếu có thể xảy ra**, không phải cấu trúc nội bộ bắt buộc của mọi phiên bản JDK. GC xác định đối tượng còn sống từ các GC root. Một vòng tham chiếu chỉ nằm trong nhóm đối tượng không còn reachable từ root vẫn có thể được GC; việc hai đối tượng trỏ lẫn nhau tự nó không tạo memory leak.

Các nguồn giữ class loader đáng kiểm tra:

- **Registry của host:** `Map<String, ModuleLayer>`, `List<Plugin>`, `ServiceLoader` hoặc `Provider` giữ đối tượng của lần nạp trước.
- **Thread:** thread do plugin tạo chưa dừng; thread pool tồn tại lâu; `Thread.contextClassLoader` đang trỏ tới loader của plugin.
- **Callback và listener:** event bus, scheduler, JMX, logging handler, shutdown hook hoặc framework registry còn chứa listener, lambda hay method reference do plugin tạo.
- **Cache và reflection:** `Class<?>`, `Method`, `Constructor`, `MethodHandle`, dynamic proxy, serializer hoặc cache với khóa/giá trị là lớp của plugin.
- **Tài nguyên chưa giải phóng:** socket, file, timer, executor, watcher... gây hệ quả vận hành và có thể giữ thêm tham chiếu tới plugin.
- **Layer con:** layer được định nghĩa từ một parent layer có quan hệ tới parent; nếu còn giữ layer con, các parent cần thiết cũng có thể tiếp tục sống.

Không nên hiểu `static` của mọi lớp plugin là một GC root độc lập. Trường static trong lớp chỉ do class loader đã có thể được thu hồi quản lý thường không tự ngăn một loader không còn reachable bị dỡ. Rủi ro lớn xuất hiện khi **một đối tượng sống lâu ở bên ngoài** (ví dụ lớp trong boot/application layer hoặc registry toàn cục) giữ instance, `Class` hoặc loader của plugin.

## 4. Chọn chiến lược định nghĩa layer cho phù hợp

Các cách thường dùng:

- `parentLayer.defineModulesWithOneLoader(configuration, parentLoader)`: tạo một class loader mới cho các module trong cấu hình mới; các module đó dùng chung loader này.
- `parentLayer.defineModulesWithManyLoaders(configuration, parentLoader)`: tạo loader mới riêng cho mỗi module trong cấu hình.
- `ModuleLayer.defineModules(configuration, parentLayers, mapper)`: dùng hàm ánh xạ module sang class loader do ứng dụng cung cấp; cần đặc biệt chú ý vòng đời của loader mà mapper trả về.
- Các phương thức static trả về `ModuleLayer.Controller` cho phép điều chỉnh quan hệ đọc, export, open của các module trong layer tương ứng; controller cũng là một đối tượng cần bỏ tham chiếu khi không dùng nữa.

**Lưu ý:** Đối số `parentLoader` của hai phương thức tiện ích đầu tiên là loader cha cho các loader mới, không có nghĩa các module mới được định nghĩa trực tiếp vào `parentLoader`. Nếu tự ánh xạ module vào một loader dùng chung, sống suốt ứng dụng, bạn thường không đạt được khả năng thu hồi độc lập cho từng đợt plugin.

Layer không phải ranh giới bảo mật tuyệt đối hay ranh giới tài nguyên: mã plugin vẫn chạy trong cùng JVM và có thể tạo thread, tương tác với module nó được phép truy cập, giữ tài nguyên native, hoặc làm xuất hiện tham chiếu từ host.

### Nạp lại một plugin

Muốn thay thế phiên bản module đang chạy, cách phổ biến là:

1. Dừng toàn bộ công việc của phiên bản cũ.
2. Gỡ mọi đăng ký và đóng tài nguyên của phiên bản cũ.
3. Xóa các tham chiếu mạnh tới các instance, lớp, loader và layer cũ.
4. Tạo **configuration và layer mới** từ artifact phiên bản mới.
5. Nạp provider và đưa phiên bản mới vào phục vụ.

Không thể sửa một module đã định nghĩa trong layer hiện tại thành bytecode phiên bản mới bằng cách gọi `ModuleLayer` một lần nữa. Các điều chỉnh reads/exports/opens qua controller không phải cơ chế thay bytecode hoặc hoàn tác mọi trạng thái do module cũ gây ra.

## 5. Ví dụ: quản lý một phiên plugin bằng AutoCloseable

Giả sử host có module `com.example.host`, API chung `com.example.spi` nằm trong boot layer và JAR plugin chứa module `com.example.plugin`. Đặt interface SPI ở module sống lâu giúp host gọi dịch vụ qua một kiểu ổn định, không cần giữ trực tiếp implementation class của plugin.

**Trong module SPI:**

~~~java
// module-info.java của com.example.spi
module com.example.spi {
    exports com.example.spi;
}
~~~

~~~java
// com/example/spi/TaskPlugin.java
package com.example.spi;

public interface TaskPlugin {
    void execute();
    void shutdown();
}
~~~

**Trong module plugin:**

~~~java
// module-info.java của com.example.plugin
module com.example.plugin {
    requires com.example.spi;
    provides com.example.spi.TaskPlugin
        with com.example.plugin.ExampleTaskPlugin;
}
~~~

~~~java
// com/example/plugin/ExampleTaskPlugin.java
package com.example.plugin;

import com.example.spi.TaskPlugin;

public final class ExampleTaskPlugin implements TaskPlugin {
    @Override
    public void execute() {
        System.out.println("Executing from custom layer");
    }

    @Override
    public void shutdown() {
        // Hủy đăng ký callback, đóng tài nguyên thuộc quyền sở hữu plugin.
    }
}
~~~

**Trong module host:**

~~~java
// module-info.java của com.example.host
module com.example.host {
    requires com.example.spi;
    uses com.example.spi.TaskPlugin;
}
~~~

~~~java
package com.example.host;

import com.example.spi.TaskPlugin;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.Set;

public final class PluginSession implements AutoCloseable {
    private ModuleLayer layer;
    private List<TaskPlugin> providers;

    private PluginSession(ModuleLayer layer, List<TaskPlugin> providers) {
        this.layer = layer;
        this.providers = providers;
    }

    public static PluginSession open(Path pluginJar) {
        Objects.requireNonNull(pluginJar);

        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(pluginJar);
        Configuration configuration = parent.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("com.example.plugin")
        );

        // Tạo loader mới cho module của custom layer.
        ModuleLayer child = parent.defineModulesWithOneLoader(
            configuration,
            TaskPlugin.class.getClassLoader()
        );

        List<TaskPlugin> instances = ServiceLoader
            .load(child, TaskPlugin.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .toList();

        return new PluginSession(child, instances);
    }

    public synchronized void runAll() {
        if (layer == null) {
            throw new IllegalStateException("PluginSession already closed");
        }
        for (TaskPlugin plugin : providers) {
            plugin.execute();
        }
    }

    @Override
    public synchronized void close() {
        if (layer == null) {
            return;
        }

        RuntimeException failure = null;
        try {
            for (TaskPlugin plugin : providers) {
                try {
                    plugin.shutdown();
                } catch (RuntimeException ex) {
                    if (failure == null) {
                        failure = ex;
                    } else {
                        failure.addSuppressed(ex);
                    }
                }
            }
        } finally {
            // Ngắt các tham chiếu mà session trực tiếp sở hữu.
            providers = List.of();
            layer = null;
        }

        if (failure != null) {
            throw failure;
        }
    }
}
~~~

Cách gọi:

~~~java
try (PluginSession session =
         PluginSession.open(Path.of("plugins", "example-plugin.jar"))) {
    session.runAll();
}
// close() đã gọi shutdown() và bỏ tham chiếu do session quản lý.
~~~

Điều kiện để ví dụ hoạt động:

- JAR là **modular JAR hợp lệ** với tên module đúng `com.example.plugin`; `com.example.spi` có thể được giải quyết từ layer cha.
- Module host phải có quyền đọc SPI và khai báo `uses` tương ứng; plugin khai báo `provides`.
- Host không giữ `TaskPlugin` instance, `ServiceLoader`, provider hoặc class loader của phiên cũ ở chỗ khác.
- `shutdown()` thật sự dừng các thread/task và gỡ các tài nguyên, listener mà plugin đã tạo.
- Đường đi mở phiên có thể phát sinh lỗi trong lúc tìm provider hoặc khởi tạo. Ở hệ thống thực tế, cần bổ sung cleanup khi **khởi tạo dở dang thất bại**, không chỉ khi `close()` của phiên thành công được gọi.

Mẫu `AutoCloseable` định nghĩa **hợp đồng dừng tài nguyên do ứng dụng kiểm soát**. Nó không ép JVM dỡ lớp ngay lập tức, và cũng không thể tự phát hiện mọi tham chiếu do framework hoặc mã plugin đặt vào registry bên ngoài.

## 6. Vì sao một custom layer tưởng đã đóng vẫn tồn tại?

### 6.1. Thread context class loader

Một thư viện có thể tạm đổi context class loader để khám phá tài nguyên hoặc provider:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Thực hiện thao tác cần context loader của plugin.
} finally {
    current.setContextClassLoader(previous);
}
~~~

Nếu bỏ qua `finally`, thread xử lý request sống lâu có thể giữ loader sau khi plugin session kết thúc. Nếu tạo thread mới, phải quản lý vòng đời thread đó, dừng bằng giao thức phù hợp và `join` hoặc chờ executor kết thúc khi cần; chỉ reset context loader của thread hiện tại là chưa đủ.

### 6.2. Registry và cache sống lâu hơn layer

Ví dụ nguy hiểm:

~~~java
// Registry của host tồn tại trong suốt quá trình chạy.
static final java.util.Map<String, TaskPlugin> ACTIVE =
    new java.util.concurrent.ConcurrentHashMap<>();
~~~

Nếu host đưa một instance từ custom layer vào `ACTIVE` rồi chỉ đặt biến `layer = null`, instance vẫn reachable. Khi ngừng plugin, phải `remove` entry tương ứng; tương tự với cache kiểu `Class<?>`, listener, scheduler và mọi registry đăng ký trong quá trình nạp.

Các cache khóa bằng `Class<?>` đặc biệt dễ gây nhầm lẫn. Nếu bản thân cache là static của host, khóa mạnh có thể giữ lớp và class loader cũ. Dùng weak key có thể hỗ trợ, nhưng cần xem xét cả value và chuỗi tham chiếu từ value; `WeakHashMap` không tự giải quyết một chu trình có đường mạnh từ value về key.

### 6.3. Đóng resource nhưng còn giữ instance

`shutdown()` hoặc `close()` có thể giải phóng file/socket/thread nhưng nếu host vẫn giữ service instance, GC chưa thể thu hồi toàn bộ đối tượng và loader liên quan. Hai việc cần làm riêng biệt: **dọn tài nguyên chủ động** và **loại bỏ tham chiếu mạnh**.

### 6.4. Dùng class loader sống toàn tiến trình

Khi nhiều lần cập nhật plugin nhưng vẫn định nghĩa các lớp vào loader do hệ thống giữ lâu dài, việc bỏ layer wrapper không tạo khả năng class unloading độc lập. Với plugin cần thay thế nhiều lần, hãy thiết kế ranh giới loader tương ứng với phiên nạp và tránh giữ loader đó sau khi kết thúc phiên.

### 6.5. Layer cha và layer con

Custom layer có thể có nhiều parent; `parents()` phản ánh quan hệ layer. Bản thân một layer con còn sống có thể giữ những parent cần thiết. Việc dỡ một nhánh phải tính cả các layer/connections còn hoạt động, không chỉ phiên được đánh dấu là đã dừng.

## 7. Quan sát khả năng thu hồi và class unloading

### 7.1. WeakReference chỉ là tín hiệu về reachability

Có thể theo dõi layer hoặc loader bằng `WeakReference` mà không giữ nó sống bằng một tham chiếu mạnh:

~~~java
import java.lang.ref.WeakReference;

// Ghi nhận khi phiên còn hoạt động:
WeakReference<ClassLoader> weakLoader =
    new WeakReference<>(layer.findLoader("com.example.plugin"));

// Sau khi dừng phiên, xóa mọi tham chiếu mạnh còn giữ ở host.
// Khi JVM GC, weakLoader.get() có thể trở thành null.
~~~

Đoạn trên chỉ minh họa kỹ thuật lấy yếu tham chiếu; trong chương trình thực, biến `layer` và các biến local chứa loader phải kết thúc phạm vi sử dụng. `weakLoader.get() == null` cho thấy đối tượng được tham chiếu yếu không còn được giữ mạnh vào lúc kiểm tra; điều đó **không thay thế bằng chứng từ log class unloading**. Ngược lại, giá trị khác null ngay sau khi đóng phiên cũng chưa chứng minh memory leak.

`System.gc()` chỉ là một yêu cầu/gợi ý thực hiện GC và JVM có thể không đáp ứng theo cách mong đợi. Không viết kiểm thử chức năng phụ thuộc vào một số mili giây cố định để buộc weak reference phải trở thành null.

### 7.2. Công cụ chẩn đoán

Với JVM HotSpot hỗ trợ unified logging:

~~~text
java -Xlog:class+unload=info -m com.example.host/com.example.host.Main
~~~

Log class unloading giúp xác nhận có lớp được dỡ trong thực tế. Có thể kết hợp log GC hoặc JFR/JDK Mission Control để quan sát xu hướng của class loader và metaspace. Trên môi trường hỗ trợ, lệnh `jcmd <pid> VM.classloader_stats` cho biết thống kê loader; cú pháp và mức dữ liệu phụ thuộc JDK/JVM.

Để điều tra trường hợp lặp nhiều lần:

1. Tạo phiên plugin, dùng một số tác vụ rồi đóng phiên; lặp lại trong môi trường kiểm thử có kiểm soát.
2. Theo dõi số class loader và class đã nạp, metaspace sau những đợt GC thực tế; ưu tiên **xu hướng qua nhiều chu kỳ**.
3. Nếu số loader/lớp tăng liên tục, dùng heap dump và công cụ phân tích đường đi tới GC root để tìm holder cụ thể.
4. Kiểm tra thread dump, thread context class loader, listener, registry, cache, scheduler và static field trong module host.
5. Sau khi gỡ đúng đường giữ tham chiếu, lặp lại phép đo và tìm các sự kiện unloading khi JVM thực hiện GC phù hợp.

Không nên kết luận rò rỉ bộ nhớ chỉ từ việc metaspace chưa giảm ngay sau một lần đóng layer: JVM có chính sách GC và cấp phát/giữ vùng bộ nhớ riêng.

## 8. Nguyên tắc thiết kế lifecycle cho hệ thống plugin

- Định nghĩa rõ **ai sở hữu** layer, loader, provider, task, listener và tài nguyên bên ngoài.
- Cung cấp hợp đồng dừng như `AutoCloseable`, `shutdown` hoặc `stop`; gọi đúng một lần theo vòng đời quản lý.
- Tách API/SPI sống lâu khỏi implementation nạp trong custom layer.
- Tránh để plugin tự tạo background thread không được quản lý; dùng executor do host cấp hoặc giao diện lifecycle rõ ràng.
- Mọi thao tác `register` cần có đường `unregister`, mọi cache cho plugin cần chính sách gỡ entry.
- Giữ `ServiceLoader`, `Provider`, `Class<?>`, `MethodHandle` và class loader ở phạm vi phiên thay vì biến toàn cục.
- Nếu đổi thread context class loader, luôn phục hồi bằng `finally`.
- Khi reload, tạo layer/loader mới cho mã phiên bản mới và xử lý tài nguyên của phiên cũ trước khi bỏ tham chiếu.
- Chẩn đoán khả năng thu hồi bằng quan sát reachability, class unloading và GC roots; tránh giả định thời gian GC cụ thể.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Đặt `layer = null` là unload plugin.” | Chỉ bỏ một tham chiếu; còn phải xét mọi tham chiếu tới loader, lớp, provider và tài nguyên liên quan. |
| “`ModuleLayer` có API đóng giống `URLClassLoader`.” | `ModuleLayer` không có API close/unload. Lifecycle nghiệp vụ phải do host thiết kế. |
| “Đóng file/socket đủ để dỡ lớp.” | Dọn tài nguyên và làm loader không còn reachable là hai điều kiện khác nhau. |
| “GC chạy thì mọi class sẽ unload.” | Unloading phụ thuộc reachability của loader và chính sách/chu kỳ JVM. |
| “Tạo layer mới tự động thay thế module cũ.” | Hai phiên có thể cùng tồn tại với các loader khác nhau; host phải chuyển điều phối và giải phóng phiên cũ. |
| “Layer con không ảnh hưởng tới parent.” | Quan hệ parent và tham chiếu từ layer còn sống có thể kéo dài vòng đời các thành phần liên quan. |

## 10. Câu hỏi tự kiểm tra

1. Vì sao một `TaskPlugin` instance nằm trong static registry của host có thể ngăn class loader plugin được thu hồi?
2. Phân biệt tác dụng của `PluginSession.close()` với quá trình JVM class unloading.
3. Khi thấy `WeakReference<ClassLoader>.get()` vẫn khác null ngay sau khi kết thúc plugin, cần kiểm tra điều gì trước khi tuyên bố memory leak?
4. Với hệ thống reload plugin hàng trăm lần, vì sao nên tránh tái sử dụng một defining class loader sống suốt tiến trình?
5. Những đường giữ tham chiếu nào có thể xuất hiện từ context class loader, scheduler, listener và `ServiceLoader`?

**Kết luận:** Khả năng thu hồi custom layer là kết quả của thiết kế vòng đời, quản lý tài nguyên và đồ thị tham chiếu. Host phải chủ động dừng hoạt động và bỏ tham chiếu của phiên plugin; JVM mới có cơ hội thu gom layer, class loader và metadata lớp ở thời điểm thích hợp.
