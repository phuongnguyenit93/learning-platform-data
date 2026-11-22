# ModuleLayer.defineModulesWithManyLoaders — tạo module layer với ClassLoader riêng cho từng module

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa **Module**, **Configuration**, **ModuleLayer** và **ClassLoader** trong Java Platform Module System (JPMS).
- Sử dụng **ModuleLayer.defineModulesWithManyLoaders** để tạo một layer mà **mỗi module được định nghĩa vào một ClassLoader riêng**.
- Lấy đúng ClassLoader của một module qua **layer.findLoader(moduleName)** và quan sát class thuộc module nào.
- Phân biệt hai overload của API, hiểu cách liên kết parent layer, quan hệ đọc module và cơ chế ủy quyền tải class.
- Nhận biết giới hạn về tính cô lập, khả năng tương thích kiểu dữ liệu và lỗi khi tạo layer.

Phạm vi: JPMS từ Java 9 trở đi; ví dụ dùng cú pháp Java 17/21.

## 2. ModuleLayer giải quyết vấn đề gì?

Một **module** là đơn vị đặt tên chứa package, class, tài nguyên và khai báo trong **module-info.java** (ví dụ: requires, exports, opens, uses, provides). **Configuration** là đồ thị các module đã được phân giải từ những module khả dụng. **ModuleLayer** biến cấu hình đã phân giải thành các **Module** tồn tại lúc chạy, đồng thời gắn từng module với một ClassLoader.

JVM khởi động với **ModuleLayer.boot()**, chứa các module nền tảng và những module được giải quyết lúc khởi chạy. Ứng dụng có thể tạo layer mới, chẳng hạn để nạp plugin hoặc tập hợp module tại runtime mà không phải đưa tất cả vào boot layer.

Một hình dung đơn giản:

~~~text
ModuleFinder (đọc các module có thể nạp)
    |
    v
Configuration (giải quyết requires, đồ thị module)
    |
    v
ModuleLayer (định nghĩa các module trong JVM)
    |-- module com.demo.api  --> ClassLoader A
    |-- module com.demo.job  --> ClassLoader B
    +-- quan hệ với parent layer --> ModuleLayer.boot()
~~~

Với **defineModulesWithManyLoaders**, hai module trong layer mới có **ClassLoader A != ClassLoader B**. Đây là khác biệt quan trọng so với **defineModulesWithOneLoader**, vốn tạo một loader dùng chung cho toàn bộ module trong layer mới.

## 3. Hai overload và ý nghĩa tham số

~~~java
// Phương thức trên một parent layer cụ thể:
public ModuleLayer defineModulesWithManyLoaders(
        Configuration cf,
        ClassLoader parentLoader);

// Phương thức static, cho phép nhiều parent layer và trả về Controller:
public static ModuleLayer.Controller defineModulesWithManyLoaders(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);
~~~

- **cf**: cấu hình chứa các module cần định nghĩa trong layer mới. Cấu hình này phải được giải quyết trước khi gọi API.
- **parentLayers**: danh sách parent layer theo đúng thứ tự tương ứng với các parent configuration của **cf**. Chỉ xuất hiện ở overload static.
- **parentLoader**: ClassLoader cha của **từng ClassLoader mới được tạo**; có thể truyền **null** nếu muốn dùng bootstrap class loader làm parent. Đây là quan hệ loader, khác với quan hệ parent layer.
- **Giá trị trả về**: overload instance trả thẳng **ModuleLayer**; overload static trả **ModuleLayer.Controller**, từ đó gọi **controller.layer()** để nhận layer, và có thể điều chỉnh một số quan hệ reads/exports/opens lúc chạy nếu thật sự cần.

Khi **parent** là một ModuleLayer đơn lẻ, hai cách sau tương đương về layer được tạo:

~~~java
ModuleLayer child1 = parent.defineModulesWithManyLoaders(cf, parentLoader);

ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                cf, List.of(parent), parentLoader);
ModuleLayer child2 = controller.layer();
~~~

Hai dòng trên chỉ minh họa **hai cách gọi API**: mỗi lần gọi tạo một layer mới, nên **child1 và child2 không phải cùng một đối tượng**. Trong ứng dụng thực tế, chọn một cách gọi.

## 4. Cơ chế ClassLoader và module readability

### 4.1. Một ClassLoader cho từng module

Giả sử cấu hình layer mới có hai module **com.demo.api** và **com.demo.job**. Phương thức tạo ra hai ClassLoader tách biệt:

~~~text
Layer L
  com.demo.api   --(defined to)--> Loader A --parent--> parentLoader
  com.demo.job   --(defined to)--> Loader B --parent--> parentLoader
         |
         +-- requires com.demo.api
~~~

Khi Loader B cần một class thuộc package được **com.demo.api** xuất ra và được **com.demo.job** đọc, loader có thể **ủy quyền trực tiếp đến Loader A**. Đây là cơ chế phân tuyến theo package/module. Nó không đồng nghĩa với việc Loader A là **getParent()** của Loader B.

Khi tên class không ánh xạ được tới một module trong quan hệ phân tuyến đó, loader chuyển tiếp sang **parentLoader**. Đối với resource, mỗi loader ưu tiên tìm resource thuộc module mà nó quản lý rồi mới tìm qua parent loader, theo quy tắc của API và giới hạn đóng gói module.

### 4.2. Readability và exports vẫn có hiệu lực

- **requires** xác định module nào cần đọc module nào trong quá trình phân giải; runtime có quan hệ **reads** tương ứng.
- **exports** cho phép truy cập public types của package được xuất; **opens** dành cho quyền truy cập phản chiếu sâu khi áp dụng.
- Việc class được một loader tìm thấy **không tự động cấp quyền truy cập** vào package không export hoặc mở khóa truy cập private.
- **parent layer** và **parentLoader** là hai khái niệm khác nhau: một cái mô tả quan hệ module ở runtime, một cái là quan hệ cha của class loader.

Vì vậy, nhiều ClassLoader hỗ trợ tổ chức không gian nạp class, nhưng **không biến JPMS thành cơ chế sandbox bảo mật**, cũng không loại bỏ các quy tắc truy cập của Java.

## 5. Ví dụ hoàn chỉnh: nạp hai module vào layer mới

Ta có hai module: **com.demo.api** cung cấp lời chào; **com.demo.job** phụ thuộc vào module đó. Chương trình **Launcher** chạy trên classpath, giải quyết hai module từ thư mục **mods** rồi tạo layer bằng API đang học.

### 5.1. Cấu trúc nguồn

~~~text
src/
  com.demo.api/
    module-info.java
    com/demo/api/Message.java
  com.demo.job/
    module-info.java
    com/demo/job/Job.java
Launcher.java
~~~

File **src/com.demo.api/module-info.java**:

~~~java
module com.demo.api {
    exports com.demo.api;
}
~~~

File **src/com.demo.api/com/demo/api/Message.java**:

~~~java
package com.demo.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "Hello from module";
    }
}
~~~

File **src/com.demo.job/module-info.java**:

~~~java
module com.demo.job {
    requires com.demo.api;
    exports com.demo.job;
}
~~~

File **src/com.demo.job/com/demo/job/Job.java**:

~~~java
package com.demo.job;

import com.demo.api.Message;

public final class Job {
    private Job() {}

    public static String run() {
        return Message.text();
    }
}
~~~

### 5.2. Viết chương trình khởi tạo layer

File **Launcher.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        // 1. Đọc các module đã biên dịch trong thư mục mods/.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        // 2. Giải quyết module gốc và các module phụ thuộc.
        ModuleLayer parent = ModuleLayer.boot();
        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.demo.job"));

        // 3. Mỗi module trong cấu hình nhận một ClassLoader mới.
        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithManyLoaders(
                        cf,
                        List.of(parent),
                        ClassLoader.getSystemClassLoader());

        ModuleLayer layer = controller.layer();

        // 4. Lấy ClassLoader theo tên module.
        ClassLoader apiLoader = layer.findLoader("com.demo.api");
        ClassLoader jobLoader = layer.findLoader("com.demo.job");

        System.out.println("Different loaders: "
                + (apiLoader != jobLoader));

        // 5. Nạp class từ chính loader của module chứa class.
        Class<?> jobClass = jobLoader.loadClass("com.demo.job.Job");

        System.out.println("Module: "
                + jobClass.getModule().getName());
        System.out.println("Result: "
                + jobClass.getMethod("run").invoke(null));
    }
}
~~~

Giải thích:

1. **ModuleFinder.of(Path.of("mods"))** tìm các module đã biên dịch. Đây là đầu vào để giải quyết module, chưa tạo layer.
2. **resolve(...)** lấy **com.demo.job** làm root; khai báo **requires com.demo.api** khiến **com.demo.api** cũng được giải quyết.
3. **defineModulesWithManyLoaders(...)** dùng boot layer làm parent layer. Vì cấu hình chứa hai module, phương thức tạo ClassLoader riêng cho mỗi module.
4. **layer.findLoader(...)** trả loader của module được chỉ định. Không phải tự tạo **URLClassLoader** cho từng JAR.
5. Phản chiếu gọi phương thức public **Job.run()** trong package **com.demo.job** đã **exports**; **Job** sử dụng **Message** ở module được đọc.

### 5.3. Biên dịch và chạy

Từ thư mục chứa **src/** và **Launcher.java**, sử dụng JDK 17+:

~~~bash
javac --module-source-path src -d mods -m com.demo.api,com.demo.job
javac -d out Launcher.java
java -cp out Launcher
~~~

Kết quả dự kiến:

~~~text
Different loaders: true
Module: com.demo.job
Result: Hello from module
~~~

Nếu đổi sang API **parent.defineModulesWithOneLoader(cf, parentLoader)** thì hai module trong layer mới dùng **cùng một ClassLoader** và điều kiện so sánh loader trong ví dụ sẽ là **false**. Các phần khai báo module và đồ thị **requires** không tự thay đổi vì lựa chọn loader.

## 6. So sánh các phương pháp tạo layer

| API | Phân bổ ClassLoader | Trả về (instance/static) | Khi nên dùng |
| --- | --- | --- | --- |
| **defineModulesWithOneLoader** | Một loader cho tất cả module trong layer mới | ModuleLayer / Controller | Các module tin cậy, có cấu trúc package phù hợp và muốn giảm số loader |
| **defineModulesWithManyLoaders** | Mỗi module trong layer mới có một loader riêng | ModuleLayer / Controller | Muốn phân tách phạm vi định nghĩa class theo module và kiểm soát rõ module nào nạp class nào |
| **defineModules** | Dùng hàm do ứng dụng cung cấp để ánh xạ tên module sang loader | ModuleLayer / Controller | Cần chiến lược ClassLoader tùy chỉnh; phải tự đảm bảo quy tắc delegation/readability |

Tạo nhiều loader thường tốn thêm đối tượng và quản lý class/resource. Chọn phương pháp theo nhu cầu kiến trúc và đo lường thực tế, thay vì coi một loader mỗi module luôn tốt hơn.

## 7. Những quy tắc và lỗi dễ gặp

### Cấu hình phải khớp parent layer

**cf** phải có đúng các parent configuration của những layer truyền trong **parentLayers**, kể cả **thứ tự**. Trường hợp không khớp sẽ gây **IllegalArgumentException**. Overload instance chỉ thích hợp với cấu hình có **một parent configuration**, chính là cấu hình của layer gọi phương thức.

### Không định nghĩa lại java.base

Layer mới không được chứa module tên **java.base**, cũng không được chứa package **java** hoặc bắt đầu bằng **java.**. Các trường hợp như vậy làm việc tạo layer thất bại với **LayerInstantiationException**.

### Phân giải module là bước riêng

Nếu **ModuleFinder** không tìm thấy root module hay dependency, hoặc có xung đột ràng buộc khi phân giải, lỗi xuất hiện ở bước **Configuration.resolve(...)** (ví dụ **FindException**, **ResolutionException**) trước khi gọi **defineModulesWithManyLoaders**. Cần phân biệt lỗi phân giải với lỗi định nghĩa layer.

### Không tải nhầm class qua system class loader

Layer mới chứa class trong loader mới. Gọi **Class.forName("com.demo.job.Job")** mà không chỉ định loader, hoặc tìm class qua system loader, có thể không thấy class hoặc lấy class khác cùng tên trong môi trường phức tạp. Hãy dùng **layer.findLoader("com.demo.job")** và API tải class phù hợp.

### Chú ý class identity khi trao đổi dữ liệu

Trong JVM, danh tính class phụ thuộc cả **tên binary** và **ClassLoader định nghĩa**. Hai class cùng tên do hai loader khác nhau định nghĩa có thể **không ép kiểu qua lại**. Với kiến trúc plugin, hãy để API dùng chung trong module hoặc lớp cha có loader ổn định; giao tiếp qua interface và đối tượng dùng chung đó, thay vì cast trực tiếp giữa các loại nội bộ plugin.

### Đừng hiểu nhầm việc giải phóng module

Java không có API **unload ModuleLayer** trực tiếp. Class và loader chỉ có khả năng được thu gom khi không còn tham chiếu giữ chúng sống (bao gồm instance, thread, callback, cache, ServiceLoader hoặc TCCL). Tạo layer mới không bảo đảm các layer cũ tự biến mất.

### Không tự động bảo đảm an toàn hay tránh mọi xung đột

Mỗi module có loader riêng không đồng nghĩa hoàn toàn cô lập dependency, trạng thái static, native library, hệ thống file hay tài nguyên máy. JPMS vẫn thực thi ràng buộc exports/opens/reads; thiết kế loader và module graph cần nhất quán.

## 8. Khi nào áp dụng trong thực tế?

- **Hệ thống plugin**: mỗi plugin là module trong layer riêng hoặc một tập module ở layer mới, giúp host nạp động các module đã phân giải và nhận diện loader của từng module.
- **Công cụ xử lý nhiều nhóm chức năng**: phân tách các module có vòng đời và tài nguyên khác nhau.
- **Kiểm tra hoặc tái nạp phiên bản**: tạo layer mới cho phiên bản module khác; cần bảo đảm vòng đời tham chiếu và hợp đồng API khi thay thế.

Đối với plugin, cách thường gặp là định nghĩa **SPI/interface dùng chung trong parent layer**, cho module triển khai sử dụng **requires/provides**, rồi dùng **ServiceLoader.load(layer, serviceType)** để tìm provider trong layer. Khi làm vậy, kiểu dịch vụ mà host nhận phải là cùng một class identity; tránh đóng gói nhiều bản sao SPI trong các loader khác nhau.

## 9. Câu hỏi tự luyện

1. Khác nhau giữa **parentLayers** và **parentLoader** là gì? Vì sao Loader B có thể nạp class của Loader A mà **Loader A không phải getParent() của Loader B**?
2. Khi **com.demo.job requires com.demo.api**, điều đó có làm mọi package của **com.demo.api** truy cập công khai được không?
3. Nếu muốn lấy **Controller**, bạn chọn overload nào và cần đảm bảo điều kiện gì về parent configuration?
4. Nếu nạp một class cùng tên bằng hai ClassLoader khác nhau, tại sao việc ép kiểu có thể thất bại?
5. Hãy sửa ví dụ để dùng overload instance, rồi kiểm tra kết quả hai ClassLoader vẫn khác nhau.

## 10. Ghi nhớ

**ModuleLayer.defineModulesWithManyLoaders** định nghĩa mỗi module trong một Configuration vào **ClassLoader mới riêng biệt**, đồng thời giữ nguyên nguyên tắc phụ thuộc và kiểm soát truy cập của JPMS. Quy trình cần nhớ là **tìm module → resolve Configuration → define ModuleLayer → findLoader → sử dụng class/service**. Chỉ định đúng parent layer và parent loader là điều kiện để mô hình hoạt động như mong muốn.

Tài liệu API: [java.lang.ModuleLayer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html).
