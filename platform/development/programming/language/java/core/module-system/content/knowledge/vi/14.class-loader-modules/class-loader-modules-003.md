# One loader và many loaders trong ModuleLayer (Java 9+)

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **module**, **configuration**, **module layer** và **class loader** trong Java Platform Module System (JPMS).
- Giải thích khi nào các module trong một layer dùng chung một class loader và khi nào mỗi module có class loader riêng.
- Tạo layer bằng **defineModulesWithOneLoader** và **defineModulesWithManyLoaders**, kiểm tra loader thực tế bằng **findLoader**.
- Chạy một ví dụ gồm hai named module, quan sát kết quả, và chọn cách tổ chức loader phù hợp với ứng dụng/plugin.
- Nhận ra các lỗi thường gặp về package, readability, exports, reflection và định danh lớp.

**Phạm vi:** Java 9 trở lên; ví dụ dùng cú pháp và công cụ JDK 21. Đây là cơ chế JPMS của Java SE, không yêu cầu Spring hay framework.

## 1. Bốn khái niệm phải tách bạch

**Module** là một đơn vị chứa package, class, resource và tệp **module-info.class**. Descriptor có thể khai báo **requires**, **exports**, **opens**, **uses** và **provides**. Ví dụ, module **com.demo.app** khai báo **requires com.demo.api** để đọc module thư viện.

**Configuration** là kết quả giải quyết đồ thị module ở mức mô tả: module nào được chọn, phụ thuộc nào được nối, và các ràng buộc có thỏa mãn hay không. Nó chưa định nghĩa các class vào JVM.

**ModuleLayer** là lớp tổ chức các module đã được định nghĩa ở thời gian chạy dựa trên một configuration. Một layer có thể có một hoặc nhiều parent layer. JVM khởi động với **ModuleLayer.boot()**; ứng dụng có thể tạo layer con để nạp module/plugin động.

**ClassLoader** là đối tượng tham gia tìm và định nghĩa class. Định danh runtime của một class gắn với **tên nhị phân + defining class loader**. Do đó, hai class cùng tên nhưng được định nghĩa bởi hai loader khác nhau vẫn là hai kiểu khác nhau.

Một hình dung ngắn:

~~~text
ModuleFinder: tìm module trên đĩa
    ↓
Configuration: giải quyết đồ thị phụ thuộc
    ↓
ModuleLayer: định nghĩa các module vào runtime
    ↓
ClassLoader: tải/định nghĩa các class thuộc module
~~~

**Module layer không đồng nghĩa với class loader.** Một layer có thể chứa nhiều module và ánh xạ chúng tới một hoặc nhiều loader. Đồng thời, đồ thị parent layer không đơn thuần là cây parent của các class loader.

## 2. Hai lựa chọn khi tạo layer

Giả sử một configuration chứa hai module mới:

~~~text
com.demo.app  --requires-->  com.demo.api
~~~

Từ parent layer, ta có thể gọi:

~~~java
ModuleLayer parent = ModuleLayer.boot();
Configuration cf = /* configuration đã resolve */;
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();

ModuleLayer one =
        parent.defineModulesWithOneLoader(cf, parentLoader);

ModuleLayer many =
        parent.defineModulesWithManyLoaders(cf, parentLoader);
~~~

Cả hai cách đều tạo **layer mới** với các module trong configuration. Điểm khác biệt chính là chiến lược ánh xạ module → loader.

| Khía cạnh | One loader | Many loaders |
|---|---|---|
| API instance | **defineModulesWithOneLoader** | **defineModulesWithManyLoaders** |
| Module mới trong layer | Cùng một loader mới | Mỗi module một loader mới |
| So sánh loader của hai module khác nhau trong cùng layer | Cùng tham chiếu | Khác tham chiếu |
| Phân tách namespace class ở mức loader | Thấp hơn | Cao hơn |
| Chi phí quản lý loader | Ít đối tượng loader hơn | Nhiều đối tượng loader hơn |
| Khả năng có package trùng tên giữa các module | Bị hạn chế vì cùng loader | Linh hoạt hơn, vẫn chịu ràng buộc JPMS |
| Phù hợp thường gặp | Nhóm module phát hành/vận hành cùng nhau | Các module/plugin cần ranh giới loader riêng |

**Lưu ý quan trọng về tham số parentLoader:** đây là *loader cha* được truyền vào khi tạo loader mới. Nó **không phải** đối tượng loader sẽ được trả về bởi **layer.findLoader("tên-module")**. Với cả hai API, các loader cho module mới được tạo bởi runtime.

Một module cụ thể chỉ gắn với **một** defining loader trong layer đã tạo. Khi dùng many loaders, các loader còn có cơ chế tìm class thuộc module mà module hiện tại đọc được; vì vậy việc mỗi module có loader riêng không làm mất đi quan hệ **requires**.

## 3. Ví dụ đầy đủ: hai module và một Launcher ở classpath

Ta tạo hai module có quan hệ phụ thuộc rõ ràng. Chương trình **Launcher** nằm trên classpath để chủ động tạo layer lúc chạy; hai module sẽ được tìm từ thư mục **mods**.

### 3.1. Cấu trúc thư mục

~~~text
demo/
├── Launcher.java
└── src/
    ├── com.demo.api/
    │   ├── module-info.java
    │   └── com/demo/api/Greeting.java
    └── com.demo.app/
        ├── module-info.java
        └── com/demo/app/Entry.java
~~~

### 3.2. Module thư viện: com.demo.api

Tệp **src/com.demo.api/module-info.java**:

~~~java
module com.demo.api {
    exports com.demo.api;
}
~~~

Tệp **src/com.demo.api/com/demo/api/Greeting.java**:

~~~java
package com.demo.api;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "Xin chào từ com.demo.api";
    }
}
~~~

**exports** làm cho package **com.demo.api** có thể được module khác sử dụng theo luật JPMS.

### 3.3. Module ứng dụng: com.demo.app

Tệp **src/com.demo.app/module-info.java**:

~~~java
module com.demo.app {
    requires com.demo.api;
    exports com.demo.app;
}
~~~

Tệp **src/com.demo.app/com/demo/app/Entry.java**:

~~~java
package com.demo.app;

import com.demo.api.Greeting;

public final class Entry {
    private Entry() {}

    public static void run() {
        System.out.println(Greeting.text());
    }
}
~~~

**requires** cho phép **com.demo.app** đọc **com.demo.api**. Dòng **exports com.demo.app** cho phép code của **Launcher** gọi phương thức public của **Entry** bằng reflection thông thường. Export package không đồng nghĩa với cho phép truy cập private member; trường hợp đó cần cơ chế **opens** phù hợp.

### 3.4. Launcher tạo layer theo chế độ one hoặc many

Tệp **Launcher.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Launcher {
    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "one" : args[0];

        // Tìm hai module đã biên dịch trong thư mục mods.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        // Resolve app và các dependency (bao gồm com.demo.api)
        // trên nền configuration của boot layer.
        ModuleLayer parent = ModuleLayer.boot();
        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.demo.app")
        );

        // Đây là parent loader, không phải loader mới của module.
        ClassLoader parentLoader = ClassLoader.getSystemClassLoader();

        ModuleLayer layer = switch (mode) {
            case "one" ->
                    parent.defineModulesWithOneLoader(cf, parentLoader);
            case "many" ->
                    parent.defineModulesWithManyLoaders(cf, parentLoader);
            default ->
                    throw new IllegalArgumentException(
                            "Chế độ hợp lệ: one hoặc many"
                    );
        };

        ClassLoader appLoader = layer.findLoader("com.demo.app");
        ClassLoader apiLoader = layer.findLoader("com.demo.api");

        System.out.println("Chế độ: " + mode);
        System.out.println("Cùng loader: " + (appLoader == apiLoader));
        System.out.println("App dùng parentLoader: "
                + (appLoader == parentLoader));

        // Launcher không import Entry ở compile time.
        // Nó lấy class qua loader của module đã tạo trong layer.
        Class<?> entry = appLoader.loadClass("com.demo.app.Entry");
        entry.getMethod("run").invoke(null);

        System.out.println("Entry thuộc module: "
                + entry.getModule().getName());
        System.out.println("Module thuộc layer mới: "
                + (entry.getModule().getLayer() == layer));
    }
}
~~~

Diễn giải các dòng quan trọng:

1. **ModuleFinder.of(Path.of("mods"))** tìm artifact module trong thư mục **mods** (ví dụ các thư mục exploded module sau khi biên dịch).
2. **parent.configuration().resolve(...)** giải quyết module gốc **com.demo.app** và module nó cần đọc. Configuration này là đầu vào chung cho cả hai chế độ.
3. **defineModulesWithOneLoader** hoặc **defineModulesWithManyLoaders** tạo layer và các loader tương ứng.
4. **layer.findLoader(...)** lấy loader được gắn với module có tên được chỉ định trong layer này; tên không tồn tại trong layer sẽ gây **IllegalArgumentException**.
5. **appLoader.loadClass(...)** nạp class qua loader của module ứng dụng, còn **getModule().getLayer()** cho thấy class thuộc layer mới.

Ví dụ không dùng **Class.forName("com.demo.app.Entry")** một tham số từ Launcher: loader nhìn thấy classpath của Launcher không tự động dò xuống các child loader của layer mới.

### 3.5. Biên dịch và chạy

Đứng tại thư mục **demo**. Các lệnh sau dùng được trong terminal có JDK 21 và lệnh **javac**/**java** trên PATH:

~~~bash
javac --module-source-path src -d mods -m com.demo.api,com.demo.app
javac -d out Launcher.java

java -cp out Launcher one
java -cp out Launcher many
~~~

Khi chạy chế độ **one**, phần đầu kết quả sẽ tương tự:

~~~text
Chế độ: one
Cùng loader: true
App dùng parentLoader: false
Xin chào từ com.demo.api
Entry thuộc module: com.demo.app
Module thuộc layer mới: true
~~~

Khi chạy chế độ **many**:

~~~text
Chế độ: many
Cùng loader: false
App dùng parentLoader: false
Xin chào từ com.demo.api
Entry thuộc module: com.demo.app
Module thuộc layer mới: true
~~~

**Điểm cần quan sát:** ứng dụng hoạt động giống nhau trong hai chế độ. Sự khác biệt xác minh được là biểu thức **appLoader == apiLoader**. Đầu ra cụ thể của **ClassLoader.toString()** có thể khác giữa các JDK; so sánh bằng **==** làm rõ quan hệ identity.

## 4. Hiểu đúng readability, exports, opens và delegation

JPMS có hai nhóm quy tắc liên quan nhưng không thay thế nhau:

**Quy tắc module:**

- **requires** tạo cạnh đọc từ module tiêu thụ tới module phụ thuộc.
- **exports** cho phép module khác truy cập public type/member trong package được export, theo phạm vi export.
- **opens** cho phép reflective access sâu tới package theo phạm vi được mở; khác **exports**.
- Các quy tắc này được JVM và API phản chiếu áp dụng dù module được gắn cùng loader hay khác loader.

**Quy tắc class loader:**

- Loader tìm/định nghĩa class; việc một loader có thể tìm thấy class không tự làm thay đổi quan hệ readability và exports.
- Trong chế độ many loaders, loader của một module có thể cần phối hợp tìm class từ loader của module được đọc. Vì vậy không nên suy ra rằng mọi lời gọi **loadClass** chỉ nhìn thấy đúng một module.
- **parentLoader** thường phục vụ delegation tới hệ thống có sẵn. Không suy luận layer parent giống hệt loader parent.
- Boot layer tiếp tục chứa module nền tảng Java; tạo layer con không nhân bản **java.base** thành module mới.

Ví dụ: nếu bỏ **requires com.demo.api**, việc **com.demo.app** truy cập **Greeting** không được bảo đảm bởi việc hai module dùng chung một loader. Nếu bỏ **exports com.demo.api**, class công khai trong package đó vẫn không được module khác truy cập như một API công khai. Loader không phải công cụ bỏ qua encapsulation của JPMS.

## 5. Định danh lớp và cô lập giữa các layer

Trong JVM, hai bản class có cùng tên nhị phân có thể là hai kiểu khác nhau khi chúng được định nghĩa bởi hai class loader khác nhau.

Giả sử tạo hai layer độc lập, mỗi layer resolve lại cùng module **com.demo.app** từ cùng artifact:

~~~java
ModuleLayer first = parent.defineModulesWithOneLoader(cf, parentLoader);
ModuleLayer second = parent.defineModulesWithOneLoader(cf, parentLoader);

Class<?> a = first.findLoader("com.demo.app")
        .loadClass("com.demo.app.Entry");
Class<?> b = second.findLoader("com.demo.app")
        .loadClass("com.demo.app.Entry");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                          // false
~~~

Mỗi lần tạo layer đều có loader mới cho module mới; vì thế hai lớp có cùng tên nhưng identity khác nhau. Hệ quả thực tế:

- Không ép kiểu trực tiếp object tạo từ bản class ở layer A sang class đồng tên của layer B.
- Không dựa vào tên đầy đủ của class để xác định hai object có cùng kiểu runtime.
- Khi trao đổi object giữa các plugin, ưu tiên API chung được nạp ở một layer cha chia sẻ, hoặc trao đổi dữ liệu đã chuẩn hóa qua một giao diện rõ ràng.
- Với many loaders trong **cùng một layer**, module app và module api có loader khác nhau; điều này vẫn cho phép app sử dụng type của api nếu đồ thị module và quy tắc truy cập đúng.

**ClassCastException** hoặc **LinkageError** có thể xuất hiện nếu thư viện/plugin giả định class cùng tên từ hai loader là cùng một kiểu. Chọn one loader hoặc many loaders không thay thế việc thiết kế API boundary.

## 6. Chọn one loader hay many loaders?

**Ưu tiên one loader khi:**

- Các module tạo thành một đơn vị chức năng thống nhất, vòng đời và phiên bản thường đi cùng nhau.
- Bạn muốn một loader chung cho các module mới của layer.
- Các module không có xung đột package khiến việc gán vào cùng loader bị từ chối.
- Không cần phân tách namespace class theo từng module trong layer.

**Cân nhắc many loaders khi:**

- Mỗi module cần identity loader riêng, ví dụ các thành phần mở rộng được quản lý tách biệt.
- Muốn tránh ràng buộc một loader phải định nghĩa các package của tất cả module mới; trường hợp package trùng tên vẫn phải thỏa quy tắc giải quyết và truy cập của JPMS.
- Công cụ chẩn đoán hoặc cơ chế nạp class của ứng dụng cần phân biệt rõ loader theo module.
- Chấp nhận có thêm đối tượng loader và sự phức tạp khi truyền class/object giữa các thành phần.

Không nên mặc định **many loaders = bảo mật**, **one loader = nhanh hơn** hay **mỗi module có loader riêng = có thể unload độc lập bất cứ lúc nào**. JPMS không phải security sandbox. Việc giải phóng class/layer phụ thuộc vào khả năng thu gom rác của loader và toàn bộ tham chiếu còn sống (class, instance, thread, static field, service, cache, v.v.); không có lệnh “unload module” đơn giản.

Với hệ thống plugin thật, cân nhắc thêm vòng đời plugin, dependency version, API chia sẻ, thread context class loader, **ServiceLoader**, resource lookup và chiến lược đóng tài nguyên. Hai API ở đây chỉ quyết định cách gán loader cho module trong layer mới.

## 7. Những lỗi thường gặp và cách suy luận

### 7.1. Nhầm cấu hình với layer

**Triệu chứng:** resolve thành công nhưng không lấy được class theo cách đã kỳ vọng.

**Lý do:** **Configuration** chỉ giải quyết đồ thị. Cần gọi một API **defineModules...** để định nghĩa module vào runtime và lấy class loader trong layer đã tạo.

### 7.2. Nhầm parentLoader với loader của module

**Triệu chứng:** kiểm tra **layer.findLoader(name) == parentLoader** và cho rằng false là lỗi.

**Lý do:** hai API tạo loader mới. Dùng **findLoader** để quan sát mapping thực, không suy luận theo tham số truyền vào.

### 7.3. Thiếu requires, exports hoặc opens

**Triệu chứng:** lỗi module resolution, **IllegalAccessException**, **InaccessibleObjectException** hoặc lỗi truy cập khác.

**Cách suy luận:** xác định module nào đọc module nào; package nào phải export; code có chỉ gọi public member hay muốn phản chiếu private member. Sửa **module-info.java** phù hợp, không thay loader để “vượt rào”.

### 7.4. Trùng package khi dùng one loader

**Triệu chứng:** tạo layer thất bại với **LayerInstantiationException** hoặc lỗi kiểm tra package/module.

**Lý do:** hai module mới không thể tùy ý định nghĩa cùng package vào cùng một loader. Kiểm tra cấu trúc package và đồ thị module. Many loaders có thể cho phép các package cùng tên ở các loader khác nhau trong những cấu hình hợp lệ, nhưng vẫn phải tuân thủ quy tắc JPMS; không có bảo đảm mọi xung đột package đều được giải quyết chỉ bằng cách đổi API.

### 7.5. Dùng loader của Launcher để tìm class trong layer mới

**Triệu chứng:** **ClassNotFoundException** khi gọi **Class.forName** từ classpath hoặc **ClassLoader.getSystemClassLoader().loadClass(...)**.

**Lý do:** loader hệ thống không tự đi tìm class trong loader con mới tạo. Dùng **layer.findLoader("com.demo.app")** rồi nạp class tương ứng, hoặc dùng API được thiết kế riêng cho việc tương tác với layer.

### 7.6. Tưởng many loaders cho phép trao đổi object tùy ý

**Triệu chứng:** ép kiểu lỗi dù class có cùng tên; framework giữ object từ loader khác.

**Lý do:** identity class bao gồm defining loader. Thiết kế ranh giới API dùng chung từ parent layer, hoặc định nghĩa giao thức dữ liệu rõ ràng. Đừng cast bằng tên lớp.

### 7.7. Tưởng tạo layer mới thay đổi boot layer

**Triệu chứng:** gọi **ModuleLayer.boot().findModule(...)** không thấy module vừa thêm.

**Lý do:** module được định nghĩa trong layer con, không được chèn vào boot layer. Hãy giữ tham chiếu tới layer mới và gọi **layer.findModule(...)** / **layer.findLoader(...)** trên đó.

## 8. API liên quan cần biết

- **ModuleLayer.boot()**: lấy boot layer của JVM.
- **ModuleLayer.configuration()**: lấy configuration của một layer.
- **Configuration.resolve(...)**: giải quyết module từ các finder và tập root module.
- **ModuleFinder.of(Path...)**: tạo finder từ module artifact trên đĩa.
- **ModuleLayer.defineModulesWithOneLoader(cf, parentLoader)**: instance API, tạo layer con với một loader cho các module mới.
- **ModuleLayer.defineModulesWithManyLoaders(cf, parentLoader)**: instance API, tạo layer con có loader riêng cho từng module mới.
- **ModuleLayer.findLoader(moduleName)**: lấy loader của module được định nghĩa **trong layer đó**; trả về **null** có thể là hợp lệ đối với module do bootstrap loader định nghĩa, ví dụ trong boot layer.
- **ModuleLayer.findModule(moduleName)**: tìm module qua layer hiện tại và các layer cha theo quy tắc của API.
- **Class.getModule()** và **Module.getLayer()**: xác định module và layer chứa class runtime.
- **ModuleLayer.defineModulesWithOneLoader(cf, parentLayers, parentLoader)** và bản **defineModulesWithManyLoaders** dạng **static**: dùng danh sách parent layer, trả về **ModuleLayer.Controller**; lấy layer qua **controller.layer()**. Đừng nhầm kiểu trả về này với hai instance method trong ví dụ.
- **ServiceLoader.load(layer, serviceType)**: cách tìm service provider trong các module của layer khi xây kiến trúc plugin theo JPMS. Module provider cần khai báo **provides ... with ...**, module tiêu thụ cần khai báo **uses** khi phù hợp.

## 9. Tự luyện tập

**Bài 1 — Kiểm tra loader.** Chạy ví dụ ở cả hai chế độ. Ghi lại ba biểu thức:

~~~java
appLoader == apiLoader
appLoader == parentLoader
entry.getModule().getLayer() == layer
~~~

Kỳ vọng lần lượt: **true / false / true** ở chế độ one; **false / false / true** ở chế độ many. Giải thích vì sao biểu thức cuối vẫn true trong cả hai chế độ.

**Bài 2 — Thử module boundary.** Xóa **exports com.demo.app** trong descriptor của app, biên dịch lại rồi thử reflective invocation từ Launcher. Quan sát lỗi truy cập và khôi phục **exports**. Phân tích vì sao việc đổi one ↔ many không phải lời giải cho giới hạn này.

**Bài 3 — Hai layer độc lập.** Tạo hai layer bằng cùng configuration và cùng chế độ one. Lấy class **com.demo.app.Entry** từ từng layer, so sánh **getName()** và **==**. Giải thích bằng cặp *(binary name, defining class loader)*.

**Bài 4 — Thiết kế plugin.** Một hệ thống có module API chung và ba module plugin. Hãy phác thảo module nào cần ở parent layer, module nào ở layer con, và nên dùng one hay many loaders. Đánh giá trên các tiêu chí: chia sẻ API, class identity, xung đột package, vòng đời và mức độ phức tạp.

## 10. Ghi nhớ

- **Configuration** giải quyết đồ thị module; **ModuleLayer** định nghĩa chúng ở runtime; **ClassLoader** tải class.
- **One loader:** các module mới trong cùng layer dùng chung một loader.
- **Many loaders:** mỗi module mới trong layer có một loader riêng; quan hệ đọc module vẫn được JPMS duy trì.
- **parentLoader** là đầu vào cho delegation; muốn biết loader gắn với module, dùng **layer.findLoader(name)**.
- **requires/exports/opens** và **class-loader identity** giải quyết hai vấn đề khác nhau; phải hiểu cả hai khi thiết kế ứng dụng module hóa.
- Lựa chọn loader chỉ là một phần của kiến trúc. Khi xây plugin thực tế, hãy thiết kế rõ các lớp dùng chung, lớp cô lập, dependency và vòng đời tài nguyên.
