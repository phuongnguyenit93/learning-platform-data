# Giới hạn reflection và dynamic loading

## 1. Mục tiêu

Java cung cấp reflection và dynamic class loading để chương trình có thể tìm kiểu, đọc metadata, gọi constructor/method hoặc nạp implementation trong lúc chạy. Những khả năng này hữu ích cho framework, dependency injection, ORM, serialization, plugin và hệ thống mở rộng.

Khi ứng dụng chạy trên Java Platform Module System (JPMS), reflection và dynamic loading vẫn chịu các quy tắc module. Một class có thể được tìm thấy và nạp thành công nhưng package chứa nó chưa được export; một field có thể được tìm thấy bằng reflection nhưng không được phép truy cập; một plugin có thể được nạp bằng class loader riêng nhưng vẫn không có quyền đọc API của module khác.

Bài này giải thích giới hạn của reflection và dynamic loading trong môi trường module, cách phân biệt export với open, cách nạp class hoặc module layer, các lỗi thường gặp và những giới hạn bảo mật cần hiểu khi thiết kế plugin.

Sau bài học, bạn có thể:
- Phân biệt truy cập Java thông thường với reflective access và deep reflection.
- Hiểu vì sao tìm thấy class không có nghĩa là được phép sử dụng class đó.
- Dùng **exports**, **opens**, **--add-exports** và **--add-opens** đúng mục đích.
- Sử dụng **Class.forName**, **ClassLoader** và **ModuleLayer** để nạp implementation động.
- Hiểu vai trò của class loader, module readability và module layer.
- Thiết kế plugin có kiểm soát và nhận biết vì sao JPMS không phải sandbox bảo mật.

## 2. Reflection là gì?

Reflection là khả năng chương trình quan sát và thao tác với cấu trúc của class tại runtime thông qua các API trong **java.lang.reflect** và **java.lang.invoke**.

Ví dụ, lấy metadata của một class:

~~~java
Class<?> type = Class.forName("com.example.model.Customer");

System.out.println(type.getName());

for (var method : type.getDeclaredMethods()) {
    System.out.println(method.getName());
}
~~~

Một số thao tác thường dùng:

- **Class.forName(...)**: tìm và nạp class theo tên.
- **getDeclaredFields()**, **getDeclaredMethods()**, **getDeclaredConstructors()**: lấy metadata của các thành viên được khai báo trong class, bao gồm cả thành viên không public.
- **getField()**, **getMethod()**: tìm thành viên public theo quy tắc kế thừa.
- **Constructor.newInstance()**, **Method.invoke()**, **Field.get()/set()**: tạo object, gọi method và đọc/ghi field bằng reflection.
- **MethodHandles.Lookup**: cung cấp cơ chế tra cứu và gọi method/field với các quyền truy cập được kiểm soát.

Reflection giúp framework làm việc với class mà không cần biết trước toàn bộ tên class hoặc cấu trúc dữ liệu khi biên dịch. Tuy nhiên, reflection không xóa bỏ kiểm tra access của Java. Việc lấy được một đối tượng **Field** hoặc **Method** không tự động cho phép gọi hoặc đọc/ghi thành viên đó.

## 3. Ba bước cần phân biệt: tìm class, truy cập type và truy cập member

Khi làm việc với class ở runtime, hãy phân biệt ba việc:

1. **Tìm và nạp class:** class loader tìm bytecode và tạo đối tượng Class.
2. **Truy cập type/package:** module system kiểm tra module đích có đọc module nguồn và package có được export hay không.
3. **Truy cập member:** Java kiểm tra modifier, quan hệ kế thừa, package, module và quyền reflection đối với thành viên cụ thể.

Ví dụ, ứng dụng có thể gọi **Class.forName("com.example.internal.Secret")** thành công vì class loader tìm được class. Nhưng nếu package **com.example.internal** thuộc một named module và không được export cho module ứng dụng, mã có thể không sử dụng public type đó theo cách thông thường.

Tương tự, **getDeclaredField("token")** có thể trả về một đối tượng Field cho private field. Điều đó chỉ cho biết field tồn tại. Khi gọi **field.get(object)** hoặc **field.set(object, value)**, access check vẫn được áp dụng. Nếu muốn bỏ qua một số kiểm tra truy cập ngôn ngữ để deep reflection, package của module nguồn phải được mở cho module gọi theo quy tắc JPMS.

Vì vậy, không nên kết luận rằng reflection đã "vượt qua module system" chỉ vì framework tìm thấy tên class hoặc field.

## 4. Export và open trong JPMS

### Export: truy cập API công khai

Một module export package để module khác truy cập public type và public/protected member theo quy tắc Java thông thường:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module consumer cần đọc module nguồn, thường bằng **requires**:

~~~java
module com.example.application {
    requires com.example.domain;
}
~~~

Khi package được export và module consumer đọc module nguồn, consumer có thể dùng public API trong package đó. Export không mở private field hoặc private method cho deep reflection.

### Open: deep reflection

Nếu framework cần truy cập reflective vào thành viên không public, module nguồn có thể mở package:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.orm;
}
~~~

Trong ví dụ này:
- Package **com.example.domain.api** được export để consumer gọi API công khai.
- Package **com.example.domain.model** được mở cho module **com.example.orm** để framework thực hiện deep reflection.

Có thể mở mọi package của một module cho deep reflection bằng khai báo:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

Một open module mở các package của nó cho deep reflection ở runtime. Nó không tự export tất cả package cho truy cập code thông thường; nếu consumer cần import public type trong package, vẫn phải có export phù hợp.

### Bảng phân biệt

| Cơ chế | Cho phép | Không tự cho phép |
|---|---|---|
| **exports p** | Truy cập public API của package p | Deep reflection vào private member |
| **exports p to m** | Public API của p cho module m | Truy cập package từ mọi module khác |
| **opens p** | Deep reflection vào package p ở runtime | Import public type từ p khi package chưa export |
| **opens p to m** | Deep reflection từ module m vào p | Truy cập reflection sâu từ module khác |
| **open module** | Deep reflection vào mọi package của module | Tự động export mọi package |

## 5. setAccessible, trySetAccessible và giới hạn module

Trước JPMS, framework thường dùng **setAccessible(true)** để yêu cầu reflection bỏ qua một số kiểm tra truy cập ngôn ngữ. Từ Java 9, thao tác này chịu thêm ranh giới module.

Ví dụ:

~~~java
Field field = Customer.class.getDeclaredField("internalId");

if (field.trySetAccessible()) {
    Object value = field.get(customer);
    System.out.println(value);
} else {
    throw new IllegalStateException(
        "Module không mở package cho deep reflection"
    );
}
~~~

**trySetAccessible()** cố gắng bật quyền truy cập reflective và trả về **false** nếu không thể thực hiện. Trong trường hợp bị chặn bởi module system, nó không tự mở package.

**setAccessible(true)** có thể ném **InaccessibleObjectException** nếu không thể bật quyền truy cập do giới hạn module. Vì vậy, đoạn mã cũ giả định mọi field đều có thể gọi setAccessible(true) có thể lỗi khi chạy trên JDK có strong encapsulation.

Để deep reflection từ module **com.example.orm** vào package **com.example.domain.model**, module nguồn có thể khai báo:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.orm;
}
~~~

Hoặc cấu hình runtime bằng tùy chọn:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.orm --module-path mods --module com.example.application/com.example.application.Main
~~~

**--add-opens** là tùy chọn runtime. Nó không biến package thành API công khai cho mã nguồn import và gọi trực tiếp. Nếu cần public type access, hãy dùng exports hoặc --add-exports.

Nếu framework chạy trong unnamed module trên classpath, target có thể là **ALL-UNNAMED**:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED -cp app.jar com.example.Main
~~~

ALL-UNNAMED mở package cho các unnamed module trong tiến trình. Đây là phạm vi rộng; nếu có thể, hãy dùng named module và chỉ mở cho module framework cụ thể.

## 6. Reflection với MethodHandles

Reflection không phải cơ chế duy nhất để truy cập thành viên động. **MethodHandles** cung cấp các handle có kiểu cho việc gọi method, truy cập field và constructor.

Một lookup thông thường:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findVirtual(
    String.class,
    "length",
    MethodType.methodType(int.class)
);

int length = (int) handle.invokeExact("modules");
~~~

Lookup object mang theo quyền truy cập của class tạo ra nó. Không phải lookup nào cũng có quyền truy cập private member của class khác.

Để tạo private lookup vào một class ở module khác, API **MethodHandles.privateLookupIn(...)** yêu cầu các điều kiện module phù hợp. Về cơ bản, module của caller phải đọc được module đích và package chứa class đích phải được mở cho module caller. Nếu package chưa mở, thao tác có thể ném **IllegalAccessException**.

Ví dụ khung:

~~~java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();

MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Customer.class,
        callerLookup
    );
~~~

Đoạn mã chỉ thành công nếu module graph và package openness cho phép. **privateLookupIn** không phải đường vòng để bỏ qua JPMS; nó tuân theo điều kiện access của module.

Khi thiết kế framework, hãy ưu tiên API công khai hoặc một SPI rõ ràng. Chỉ dùng private lookup khi framework thực sự cần truy cập sâu và module nguồn đã chủ động mở package cho nó.

## 7. Dynamic class loading là gì?

Dynamic class loading là quá trình nạp class khi chương trình đang chạy thay vì tham chiếu trực tiếp mọi implementation ở thời điểm biên dịch.

Cách đơn giản nhất là **Class.forName**:

~~~java
Class<?> type = Class.forName("com.example.plugin.JsonPlugin");
Object plugin = type.getDeclaredConstructor().newInstance();
~~~

Lời gọi một tham số **Class.forName(String)** sử dụng defining class loader của class gọi và khởi tạo class. Nếu chỉ muốn nạp class mà chưa chạy static initializer, có thể dùng overload ba tham số:

~~~java
Class<?> type = Class.forName(
    "com.example.plugin.JsonPlugin",
    false,
    pluginClassLoader
);
~~~

Tham số **false** yêu cầu không khởi tạo class tại thời điểm gọi này. Static initialization vẫn có thể chạy khi class được chủ động sử dụng sau đó.

Hoặc dùng class loader trực tiếp:

~~~java
Class<?> type = pluginClassLoader.loadClass(
    "com.example.plugin.JsonPlugin"
);
~~~

**ClassLoader.loadClass(...)** không chủ động khởi tạo class. Việc nạp, liên kết và khởi tạo là các giai đoạn riêng; JVM có thể trì hoãn một phần linking cho tới khi class thực sự được sử dụng.

Khi tạo instance bằng reflection, constructor có thể ném exception. **Constructor.newInstance()** bọc exception do constructor ném ra trong **InvocationTargetException**. Hãy kiểm tra cause để tìm lỗi gốc.

## 8. Dynamic loading không bỏ qua module access

Nạp được class không đồng nghĩa có quyền sử dụng class đó.

Giả sử **com.example.plugin.impl** là một named module chứa package **com.example.plugin.internal**. Module ứng dụng có thể tìm thấy class qua module layer hoặc class loader, nhưng nếu package không được export thì mã consumer vẫn không thể truy cập public type theo quy tắc module.

Các điều kiện thường cần xem xét:

- Module consumer có đọc module chứa class hay không.
- Package chứa public type có được export cho consumer hay không.
- Nếu framework cần deep reflection, package có được mở cho module framework hay không.
- Class loader có thể tìm đúng class và dependency của nó hay không.
- Module có nằm trong module graph/layer mà ứng dụng đang sử dụng hay không.

Không dùng **Class.forName**, **loadClass** hoặc reflection như cách sửa lỗi thiếu **requires**, **exports** hay **opens**. Những API này chỉ giúp tìm và thao tác với class theo quyền mà JVM cho phép.

## 9. Class loader và danh tính của class

Mỗi class trong JVM có danh tính gắn với tên nhị phân và defining class loader. Hai class có cùng tên đầy đủ nhưng được định nghĩa bởi hai class loader khác nhau vẫn là hai kiểu runtime khác nhau.

Ví dụ, ứng dụng và plugin cùng nạp một bản **com.example.api.Plugin** từ hai loader riêng. Một object triển khai bản interface của plugin có thể không ép kiểu được sang bản interface mà ứng dụng đang giữ. Kết quả có thể là **ClassCastException**, dù tên interface hiển thị giống nhau.

Để tránh lỗi này:

1. Đặt API dùng chung ở một class loader cha hoặc module cha mà cả ứng dụng và plugin đều đọc được.
2. Đảm bảo plugin không đóng gói một bản khác của API dùng chung nếu kiến trúc yêu cầu chia sẻ cùng kiểu.
3. Xác định rõ parent delegation và class loader chịu trách nhiệm nạp từng package.
4. Dùng module name và module layer rõ ràng khi plugin là modular JAR.
5. Ghi log cả tên class và class loader khi điều tra lỗi cast hoặc linkage.

Có thể kiểm tra defining loader:

~~~java
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

Với class thuộc bootstrap loader, **getClassLoader()** có thể trả về null. Điều đó là bình thường và không có nghĩa class chưa được nạp.

## 10. Nạp plugin bằng ModuleLayer

Với plugin được đóng gói thành modular JAR, **ModuleLayer** cho phép tạo một module layer mới từ các module tìm thấy trong một thư mục hoặc nguồn module khác.

Ví dụ cấu trúc:
- Module API **com.example.plugin.api** nằm trong layer cha.
- Module triển khai **com.example.plugin.json** nằm trong thư mục **plugins**.
- Module plugin khai báo **provides** cho service interface.

Module plugin:

~~~java
module com.example.plugin.json {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.json.JsonPlugin;
}
~~~

Module ứng dụng tiêu thụ service cần khai báo:

~~~java
module com.example.application {
    requires com.example.plugin.api;
    uses com.example.plugin.api.Plugin;
}
~~~

Tạo layer và tìm provider:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin.json")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ServiceLoader<Plugin> plugins =
    ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : plugins) {
    plugin.start();
}
~~~

Ví dụ giả định các module API và ứng dụng đã được đặt trong boot layer, thư mục **plugins** chứa module plugin hợp lệ, và các class/package được khai báo đúng. **ModuleLayer.defineModulesWithOneLoader** tạo layer mới với một class loader cho các module được định nghĩa trong layer đó.

Dùng **ServiceLoader.load(pluginLayer, Plugin.class)** giúp tìm provider trong layer chỉ định và các layer cha. Module gọi ServiceLoader trong named module phải khai báo **uses** cho service; module cung cấp phải khai báo **provides ... with ...**.

Nếu dùng plugin không phải modular JAR, có thể dùng class loader riêng hoặc cơ chế plugin khác. Tuy nhiên, class loader riêng không tự tạo ra ranh giới bảo mật và cũng không thay thế module readability/export.

## 11. ServiceLoader, context class loader và plugin

Trong ứng dụng plugin, provider có thể được nạp bởi class loader khác với class loader của ứng dụng. Lời gọi:

~~~java
ServiceLoader.load(Plugin.class)
~~~

sử dụng context class loader của thread hiện tại để tìm provider trên classpath.

Nếu ứng dụng dùng module layer, overload nhận layer giúp xác định rõ phạm vi tìm kiếm:

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
~~~

Nếu framework hoặc application server thay đổi context class loader, provider discovery có thể khác nhau giữa các thread. Khi chẩn đoán, hãy kiểm tra:

~~~java
System.out.println(
    Thread.currentThread().getContextClassLoader()
);
~~~

Ngoài ra, **ServiceLoader** thực hiện tìm và khởi tạo provider theo cơ chế lazy. Lỗi cấu hình hoặc khởi tạo có thể chỉ xuất hiện khi duyệt iterator hoặc stream, không nhất thiết tại lúc gọi **load()**. Nếu provider không hợp lệ, có thể xuất hiện **ServiceConfigurationError**.

Với plugin production, SPI thường dễ quản lý hơn việc tự ghép tên class từ chuỗi cấu hình rồi gọi Class.forName. SPI cung cấp một hợp đồng service rõ ràng và tận dụng module descriptor hoặc provider configuration.

## 12. Lỗi thường gặp khi reflection và dynamic loading

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **ClassNotFoundException** | Class loader không tìm thấy tên class được yêu cầu | Kiểm tra tên class, classpath/module path, module layer và loader |
| **NoClassDefFoundError** | Class đã biên dịch tham chiếu dependency không có lúc runtime hoặc class khởi tạo trước đó thất bại | Kiểm tra dependency và exception gốc trong log |
| **IllegalAccessException** | Reflection không có quyền truy cập member theo access check | Kiểm tra modifier, package export và quyền mở |
| **InaccessibleObjectException** | Không thể bật deep reflection do package chưa mở | Dùng opens/--add-opens có phạm vi hẹp hoặc đổi thiết kế |
| **IllegalAccessError** | Bytecode truy cập type/member bị module system chặn | Kiểm tra readability và exports ở runtime |
| **ClassCastException** | Cùng tên class nhưng được định nghĩa bởi loader khác nhau, hoặc object không triển khai đúng API | Kiểm tra class loader và vị trí đóng gói API chung |
| **NoSuchMethodException** | Class được nạp nhưng không có constructor/method đúng chữ ký | Kiểm tra API version và kiểu tham số |
| **InvocationTargetException** | Constructor hoặc method đích ném exception | Kiểm tra getCause() để tìm lỗi thực tế |
| **ExceptionInInitializerError** | Static initializer của class ném exception khi khởi tạo | Kiểm tra static block và nguyên nhân gốc |
| **ServiceConfigurationError** | Provider SPI khai báo sai, không nạp được hoặc khởi tạo thất bại | Kiểm tra provides/META-INF/services, dependency và provider constructor |

Khi điều tra, đừng chỉ bắt exception ngoài cùng rồi bỏ qua cause. Ví dụ, InvocationTargetException thường chỉ là wrapper; lỗi thật có thể là IllegalStateException hoặc lỗi cấu hình do constructor plugin ném ra.

## 13. Giới hạn bảo mật của reflection và dynamic loading

JPMS giúp đóng gói module và kiểm soát khả năng truy cập giữa các module. Tuy nhiên, **module system không phải sandbox để chạy code không đáng tin cậy**.

Nếu ứng dụng nạp một plugin Java vào cùng JVM, code plugin thường chạy với quyền của process và có thể gọi các API mà ứng dụng cũng được phép gọi. Việc đặt plugin trong module riêng hoặc class loader riêng không tự cô lập file system, network, thread, CPU, memory hay các tài nguyên hệ điều hành.

Một số rủi ro:
- **Class initialization:** static initializer có thể chạy code ngay khi class được khởi tạo.
- **Constructor side effects:** tạo instance plugin có thể mở socket, đọc file, tạo thread hoặc thay đổi trạng thái ứng dụng.
- **Reflection abuse:** framework hoặc plugin có thể truy cập sâu vào object nếu module đã mở package.
- **Untrusted class name:** nạp class name trực tiếp từ cấu hình/user input có thể khiến ứng dụng thực thi implementation ngoài dự kiến.
- **Dependency confusion:** plugin có thể mang theo dependency hoặc API trùng tên gây xung đột class loader.
- **Resource exhaustion:** plugin có thể tạo thread, cấp phát bộ nhớ hoặc chạy tác vụ tốn CPU.

Các biện pháp thực tế:

1. Chỉ nạp plugin từ nguồn được phê duyệt và kiểm soát danh sách module/class được phép.
2. Xác minh nguồn artifact, checksum hoặc chữ ký theo chính sách phát hành trước khi nạp.
3. Không coi certificate hợp lệ là bằng chứng code an toàn; chữ ký chỉ giúp xác định nguồn ký và tính toàn vẹn.
4. Xác định API plugin nhỏ, version rõ ràng và không mở package nội bộ không cần thiết.
5. Quản lý vòng đời plugin: start, stop, đóng resource, dừng thread và giải phóng tham chiếu tới class loader/layer.
6. Nếu chạy code không tin cậy, dùng process/container riêng cùng quyền hệ điều hành và giới hạn tài nguyên phù hợp thay vì dựa vào module hoặc class loader.
7. Ghi log module name, class name, class loader, nguồn artifact và lỗi khởi tạo.

Không dùng **SecurityManager** như nền tảng cho thiết kế sandbox mới. Security Manager đã bị deprecated for removal từ JDK 17; cần chọn cơ chế cô lập ở cấp process và hệ điều hành cho code không tin cậy.

## 14. Quản lý vòng đời class loader và module layer

Plugin loader không còn cần thiết vẫn có thể giữ class trong bộ nhớ nếu ứng dụng giữ tham chiếu tới class, object, thread, ThreadLocal, context class loader hoặc resource do plugin tạo.

Một số lưu ý:

- Đóng **URLClassLoader** khi không còn cần nạp thêm class/resource từ JAR. Việc close loader không tự unload các class đã được nạp.
- Dừng thread do plugin tạo và xóa ThreadLocal/context class loader trỏ tới plugin.
- Đóng file, socket, executor, watcher và resource do plugin mở.
- Xóa tham chiếu tới instance, Class, Method, MethodHandle và callback của plugin nếu muốn loader có thể được garbage collector thu hồi.
- ModuleLayer không có API unload trực tiếp. Các class của layer chỉ có thể được thu hồi khi các loader liên quan không còn được giữ sống và mọi điều kiện khác cho class unloading được đáp ứng.

Đừng dựa vào việc gọi **System.gc()** để đảm bảo plugin được unload ngay. Garbage collection là hoạt động do JVM quyết định; thiết kế plugin phải quản lý resource và tham chiếu một cách rõ ràng.

## 15. Quy trình thiết kế plugin an toàn hơn

Một quy trình thực tế có thể gồm:

1. **Định nghĩa SPI:** đặt interface service trong module API ổn định; chỉ export package API cần thiết.
2. **Xác định cách đóng gói:** chọn classpath plugin hay modular JAR trên module path.
3. **Kiểm soát nguồn plugin:** kiểm tra artifact được phê duyệt, phiên bản, checksum/chữ ký và dependency.
4. **Tạo phạm vi nạp:** dùng class loader hoặc ModuleLayer với parent/API module được xác định rõ.
5. **Tìm provider:** ưu tiên ServiceLoader thay vì tự tạo tên class từ input tùy ý.
6. **Kiểm tra hợp đồng:** xác nhận provider đáp ứng interface, version và capability mà ứng dụng yêu cầu.
7. **Khởi tạo có kiểm soát:** xử lý exception, timeout phù hợp và lỗi ServiceConfigurationError; không coi plugin lỗi là plugin vắng mặt.
8. **Cấp quyền module tối thiểu:** export package API; chỉ mở package cho deep reflection nếu framework thực sự cần.
9. **Quản lý vòng đời:** cung cấp start/stop/close, đóng resource và ngăn plugin để lại thread hoặc callback.
10. **Cô lập code không tin cậy:** chạy ở process/container riêng nếu cần ranh giới bảo mật thực sự.

## 16. Tự kiểm tra

**1. getDeclaredField() trả về một Field có nghĩa là chương trình được phép đọc field đó không?**

Không. Nó chỉ xác nhận field được tìm thấy. Khi gọi get/set, access check vẫn được áp dụng; deep reflection có thể cần package được mở cho module gọi.

**2. Class.forName() có bỏ qua module system không?**

Không. Nó tìm và nạp class qua class loader. Việc sử dụng type và truy cập member vẫn chịu module readability, exports, opens và quy tắc access của Java.

**3. Vì sao setAccessible(true) có thể ném InaccessibleObjectException trên JDK mới?**

Vì module chứa class không mở package cho module đang gọi deep reflection. Cần dùng API công khai, khai báo opens có phạm vi hẹp hoặc cấu hình --add-opens nếu thực sự cần.

**4. Khi nào nên dùng ModuleLayer thay vì chỉ tạo URLClassLoader?**

Khi plugin được đóng gói thành named module và cần một module graph riêng, với requires, exports, uses và provides rõ ràng. URLClassLoader phù hợp với một số plugin trên classpath nhưng không tự cung cấp module configuration.

**5. Hai class cùng tên có thể gây ClassCastException không?**

Có. Nếu chúng được định nghĩa bởi hai defining class loader khác nhau, JVM xem chúng là hai kiểu runtime khác nhau.

**6. Module riêng có đủ để chạy plugin không đáng tin cậy một cách an toàn không?**

Không. JPMS kiểm soát truy cập theo module, không sandbox code. Với code không tin cậy, cần cô lập ở process/container và giới hạn quyền hệ điều hành.

## 17. Ghi nhớ

Reflection và dynamic loading là công cụ mạnh cho framework và plugin, nhưng không bỏ qua ranh giới JPMS. Tìm được class không đồng nghĩa được truy cập type; tìm được Field không đồng nghĩa được đọc/ghi member; nạp được plugin không đồng nghĩa plugin có quyền hoặc đáng tin cậy.

Dùng **exports** cho public API, **opens** cho deep reflection, **ClassLoader** hoặc **ModuleLayer** cho cơ chế nạp phù hợp, và **ServiceLoader** cho SPI. Quản lý class loader, module graph, dependency và vòng đời plugin rõ ràng. Khi cần chạy code không tin cậy, hãy dùng ranh giới cô lập ở cấp process thay vì coi module system là sandbox.

## Tài liệu tham khảo

- [AccessibleObject — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Class — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [MethodHandles — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
