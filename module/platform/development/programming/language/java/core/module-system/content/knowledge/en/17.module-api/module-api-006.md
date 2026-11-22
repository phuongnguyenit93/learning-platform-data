# Module::isNamed, getName và getDescriptor

JPMS cung cấp lớp **java.lang.Module** để biểu diễn một module trong runtime. Từ một đối tượng Module, chương trình có thể xác định module đó có tên hay không, lấy tên module và đọc descriptor mô tả dependency, package export, package mở cho reflection và service. Ba API **isNamed()**, **getName()** và **getDescriptor()** là điểm bắt đầu khi cần quan sát module của một class hoặc kiểm tra các module trong một ModuleLayer.

Cần phân biệt đối tượng **Module** với **ModuleDescriptor**. Module là đối tượng runtime đại diện cho module đã được định nghĩa; ModuleDescriptor là mô tả bất biến về cấu trúc và metadata của module. Một module không có tên (unnamed module) không có descriptor, vì vậy code cần xử lý kết quả null khi đọc tên hoặc descriptor.

## 1. Lấy Module object từ một class

Mỗi class được JVM định nghĩa đều có thể cho biết module mà nó thuộc về bằng **Class.getModule()**:

~~~java
Module module = OrderService.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
System.out.println(module.getDescriptor());
~~~

Trong ví dụ, **OrderService** là một class thuộc module của ứng dụng. Nếu class được biên dịch trong named module, đối tượng trả về đại diện cho module đó. Nếu class được nạp từ classpath, nó thuộc unnamed module của class loader tương ứng.

Có thể lấy module của chính class đang chạy:

~~~java
Module currentModule = Main.class.getModule();
~~~

Hoặc lấy module của một kiểu JDK:

~~~java
Module baseModule = String.class.getModule();
System.out.println(baseModule.getName()); // java.base
~~~

Đây là cách hữu ích để kiểm tra runtime thực tế. Không nên suy luận module chỉ từ tên package, tên file JAR hoặc vị trí source; class có thể được nạp từ module path, classpath hoặc một ModuleLayer được tạo động.

## 2. Module.isNamed()

**Module.isNamed()** trả về boolean cho biết module object có phải named module hay không.

~~~java
Module module = OrderService.class.getModule();

if (module.isNamed()) {
    System.out.println("Named module");
} else {
    System.out.println("Unnamed module");
}
~~~

Named module có tên được module system nhận diện. Những trường hợp thường gặp gồm:

- **Explicit named module:** module có descriptor **module-info.class** được tác giả khai báo.
- **Automatic module:** JAR không có module descriptor tường minh nhưng được đặt trên module path, vì vậy module system tạo descriptor tự động.
- **System module:** module thuộc runtime image/JDK, ví dụ **java.base**.

Automatic module vẫn là named module, vì vậy **isNamed()** trả về **true**. Đừng dùng phương thức này để phân biệt explicit module với automatic module; hãy đọc **Module.getDescriptor()** rồi kiểm tra **ModuleDescriptor.isAutomatic()**.

Code nằm trên classpath thuộc **unnamed module**, nên **isNamed()** trả về **false**. Mỗi class loader có unnamed module riêng. Vì vậy, hai class loader khác nhau có thể có hai unnamed module khác nhau, dù cả hai đều không có tên.

## 3. Module.getName()

**Module.getName()** trả về tên của module nếu module đó là named module. Với unnamed module, phương thức trả về **null**.

~~~java
Module module = OrderService.class.getModule();
String moduleName = module.getName();

if (moduleName != null) {
    System.out.println("Module name: " + moduleName);
} else {
    System.out.println("Class belongs to an unnamed module");
}
~~~

Ví dụ, một class trong module có descriptor:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

sẽ có tên module là **com.acme.orders**. Class **String** thuộc module **java.base**, nên **String.class.getModule().getName()** trả về **java.base**.

Nếu class nằm trên classpath, kết quả tên module là null. Không nên gọi các thao tác như **module.getName().equals(...)** mà chưa kiểm tra null. Có thể dùng **Objects.equals(...)** để so sánh an toàn:

~~~java
boolean isOrdersModule =
    Objects.equals(module.getName(), "com.acme.orders");
~~~

Nếu chỉ cần lọc named module trong một stream, method reference **Module::isNamed** giúp code rõ ràng:

~~~java
ModuleLayer.boot().modules().stream()
    .filter(Module::isNamed)
    .forEach(module -> System.out.println(module.getName()));
~~~

Các module trong boot layer vốn là named modules; ví dụ này minh họa cách dùng method reference trên một tập Module. Với một tập module có thể chứa unnamed module, hãy giữ bước lọc trước khi dùng tên.

## 4. Module.getDescriptor()

**Module.getDescriptor()** trả về **java.lang.module.ModuleDescriptor** mô tả module. Nếu module là unnamed module, phương thức trả về **null**.

~~~java
Module module = OrderService.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    System.out.println("Descriptor name: " + descriptor.name());
} else {
    System.out.println("Unnamed module has no descriptor");
}
~~~

Với explicit named module, descriptor được tạo từ **module-info.java**. Với automatic module, module system tạo descriptor tự động từ metadata như **Automatic-Module-Name** hoặc tên JAR. Vì vậy, descriptor tồn tại không có nghĩa module chắc chắn là explicit module.

Có thể phân biệt automatic module bằng:

~~~java
if (descriptor != null && descriptor.isAutomatic()) {
    System.out.println("Automatic module");
}
~~~

Một descriptor là đối tượng mô tả bất biến. Đọc descriptor không thay đổi module hoặc cấp thêm quyền truy cập. Nó cho phép công cụ và ứng dụng quan sát metadata đã được khai báo hoặc được module system suy ra.

## 5. Đọc thông tin từ ModuleDescriptor

**ModuleDescriptor** cung cấp các thông tin quan trọng về cấu trúc module:

| API | Thông tin |
|---|---|
| **name()** | Tên module trong descriptor. |
| **requires()** | Tập các dependency được khai báo. |
| **exports()** | Các package được export, gồm cả qualified exports. |
| **opens()** | Các package được mở cho deep reflection, gồm cả qualified opens. |
| **uses()** | Các service type mà module sử dụng. |
| **provides()** | Các service và provider implementation mà module cung cấp. |
| **packages()** | Tập tên package thuộc module. |
| **isOpen()** | Cho biết descriptor khai báo open module hay không. |
| **isAutomatic()** | Cho biết descriptor đại diện automatic module hay không. |
| **version()** | Phiên bản module nếu descriptor có khai báo metadata phiên bản. |
| **mainClass()** | Main class nếu descriptor có khai báo. |

Ví dụ in tên, dependency và package được export:

~~~java
Module module = OrderService.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    System.out.println("Name: " + descriptor.name());

    descriptor.requires().forEach(requirement ->
        System.out.println("Requires: " + requirement.name())
    );

    descriptor.exports().forEach(exportedPackage ->
        System.out.println("Exports: " + exportedPackage.source())
    );

    System.out.println("Automatic: " + descriptor.isAutomatic());
}
~~~

**requires()** trả về tập đối tượng **ModuleDescriptor.Requires**; **exports()** trả về tập **ModuleDescriptor.Exports**. Các đối tượng này chứa thông tin chi tiết như tên module phụ thuộc, package nguồn và các modifier liên quan. Dùng descriptor để quan sát metadata, còn việc module có thực sự đọc hoặc export package cho một module cụ thể trong runtime cần kiểm tra trên Module object.

Ví dụ, **Module.canRead(other)** kiểm tra readability trong runtime; **Module.isExported(packageName, other)** kiểm tra package có được export cho module đích hay không; **Module.isOpen(packageName, other)** kiểm tra quyền deep reflection. Descriptor cho biết những directive đã khai báo, trong khi các API trên Module phản ánh quyền truy cập trong runtime context.

## 6. So sánh ba phương thức

Ba phương thức trả lời ba câu hỏi khác nhau:

| Phương thức | Kiểu trả về | Câu hỏi |
|---|---|---|
| **isNamed()** | boolean | Module này có phải named module không? |
| **getName()** | String hoặc null | Tên module là gì? |
| **getDescriptor()** | ModuleDescriptor hoặc null | Descriptor mô tả module là gì? |

Ví dụ:

~~~java
Module module = OrderService.class.getModule();

System.out.println("Named: " + module.isNamed());
System.out.println("Name: " + module.getName());

ModuleDescriptor descriptor = module.getDescriptor();
if (descriptor != null) {
    System.out.println("Automatic: " + descriptor.isAutomatic());
    System.out.println("Packages: " + descriptor.packages());
}
~~~

Các kết quả thường gặp:

| Loại module | isNamed() | getName() | getDescriptor() |
|---|---:|---|---|
| Explicit named module | true | Tên trong module-info.class | Descriptor tường minh |
| Automatic module | true | Tên automatic module | Descriptor tự động |
| Unnamed module | false | null | null |
| System module như java.base | true | java.base | Descriptor của system module |

Bảng này mô tả các trường hợp phổ biến. Khi viết code dùng chung cho nhiều nguồn class, hãy kiểm tra kết quả null thay vì giả định mọi Module object đều có tên và descriptor.

## 7. Dùng method reference trong Stream API

Tên bài học nhắc tới dạng **Module::isNamed**, **Module::getName** và **Module::getDescriptor**. Đây là method reference trỏ tới phương thức instance của kiểu **Module**. Nó có thể được dùng khi stream đang xử lý các đối tượng Module.

Ví dụ lấy tên các named module trong boot layer:

~~~java
List<String> names = ModuleLayer.boot()
    .modules()
    .stream()
    .filter(Module::isNamed)
    .map(Module::getName)
    .sorted()
    .toList();
~~~

Ví dụ lấy descriptor của những module có descriptor:

~~~java
List<ModuleDescriptor> descriptors = ModuleLayer.boot()
    .modules()
    .stream()
    .map(Module::getDescriptor)
    .filter(Objects::nonNull)
    .toList();
~~~

Ví dụ kết hợp để in tên và trạng thái automatic:

~~~java
ModuleLayer.boot().modules().stream()
    .filter(Module::isNamed)
    .forEach(module -> {
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.printf(
            "%s | automatic=%s%n",
            module.getName(),
            descriptor != null && descriptor.isAutomatic()
        );
    });
~~~

**Module::getName** tương đương việc gọi **module.getName()** cho từng phần tử. **Module::getDescriptor** tương đương gọi **module.getDescriptor()**. Khi dùng method reference trả về giá trị có thể null, hãy lọc null trước khi gọi tiếp các phương thức trên kết quả.

## 8. Quan sát module của class trong các nguồn khác nhau

Một chương trình có thể chứa class từ nhiều nguồn: module của ứng dụng, system module, automatic module hoặc classpath. Có thể viết helper để in thông tin:

~~~java
static void printModuleInfo(Class<?> type) {
    Module module = type.getModule();

    System.out.println("Class: " + type.getName());
    System.out.println("Named: " + module.isNamed());
    System.out.println("Name: " + module.getName());

    ModuleDescriptor descriptor = module.getDescriptor();
    if (descriptor == null) {
        System.out.println("Descriptor: none (unnamed module)");
    } else {
        System.out.println("Descriptor name: " + descriptor.name());
        System.out.println("Automatic: " + descriptor.isAutomatic());
        System.out.println("Packages: " + descriptor.packages());
    }
}
~~~

Có thể gọi:

~~~java
printModuleInfo(Main.class);
printModuleInfo(String.class);
printModuleInfo(OrderService.class);
~~~

Kết quả phụ thuộc vào cách các class được đóng gói và nạp:

- **String.class** thuộc **java.base**.
- **OrderService.class** thuộc module ứng dụng nếu được biên dịch và nạp như named module.
- **Main.class** thuộc unnamed module nếu ứng dụng đang chạy từ classpath; nếu chạy từ module path thì nó thuộc named module tương ứng.

Helper này phù hợp để chẩn đoán cấu hình runtime. Nếu class được nạp từ custom ModuleLayer, tên module và descriptor có thể giống một module ở layer khác, nhưng Module object là đối tượng runtime thuộc layer/class loader cụ thể.

## 9. Module name không phải runtime identity duy nhất

**getName()** trả về tên module, nhưng tên string không nên được dùng làm định danh duy nhất cho mọi module object trong toàn bộ JVM. Các ModuleLayer độc lập có thể chứa các module cùng tên nhưng được định nghĩa trong runtime context khác nhau.

Khi cần phân biệt module thực tế, hãy giữ hoặc so sánh Module object và kiểm tra layer:

~~~java
Module module = OrderService.class.getModule();

System.out.println("Name: " + module.getName());
System.out.println("Layer: " + module.getLayer());
System.out.println("Loader: " + module.getClassLoader());
~~~

Tên module hữu ích để log, tra cứu và hiển thị descriptor. Module object, layer và class loader cung cấp ngữ cảnh runtime để phân biệt các module khi ứng dụng dùng nhiều layer hoặc plugin.

Cũng cần nhớ rằng **ModuleDescriptor** mô tả cấu trúc, còn **Module** biểu diễn module đang tồn tại trong runtime. Hai đối tượng có vai trò khác nhau; không dùng descriptor thay cho Module object khi cần kiểm tra readability hoặc quyền truy cập thực tế.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi **getName().equals(...)** gây NullPointerException | Class thuộc unnamed module nên getName() trả về null | Kiểm tra **isNamed()** hoặc dùng **Objects.equals(...)** |
| **getDescriptor()** trả về null | Module là unnamed module | Xác định class có được nạp từ classpath hay không |
| isNamed() trả về true nhưng module vẫn là automatic | Automatic module cũng là named module | Kiểm tra **getDescriptor().isAutomatic()** |
| Tên module không như tên file JAR | Explicit descriptor hoặc Automatic-Module-Name quyết định tên module | Dùng **jar --describe-module** để xác nhận |
| Hai module có cùng tên trong log | Có thể chúng thuộc các layer/runtime context khác nhau | Kiểm tra Module object, **getLayer()** và class loader |
| Descriptor có export nhưng truy cập runtime vẫn lỗi | Readability, qualified export hoặc runtime context chưa phù hợp | Kiểm tra **canRead** và **isExported(packageName, targetModule)** |

Khi debug, hãy lấy Module object trực tiếp từ class gặp lỗi. Sau đó đọc isNamed, getName và getDescriptor trước khi suy luận về loại module. Điều này giúp tránh kết luận sai dựa trên tên package hoặc tên artifact.

## 11. Bài tập thực hành

1. Tạo một explicit named module **com.acme.orders** và lấy Module object bằng **OrderService.class.getModule()**.
2. In kết quả của **isNamed()**, **getName()** và **getDescriptor()**.
3. Chạy một class trên classpath và so sánh ba kết quả với class trong named module.
4. Đặt một JAR legacy không có module-info.class lên module path; xác nhận **isNamed()** trả về true và kiểm tra **getDescriptor().isAutomatic()**.
5. Dùng **String.class.getModule()** để quan sát thông tin của **java.base**.
6. Dùng **ModuleLayer.boot().modules()** kết hợp **Module::isNamed** và **Module::getName** để in tên module.
7. Dùng **Module::getDescriptor** trong stream, lọc descriptor null rồi in requires và exports.
8. Thử truy cập **getName()** và **getDescriptor()** từ unnamed module, xử lý null an toàn.
9. Tạo hai layer có module cùng tên trong hai runtime context khác nhau và so sánh tên với Module object/layer.
10. Dùng **ModuleDescriptor.isAutomatic()** để phân biệt automatic module với explicit named module.

## 12. Những điểm cần ghi nhớ

- **Module.isNamed()** trả về true cho explicit named module, automatic module và system module; unnamed module trả về false.
- **Module.getName()** trả về tên module hoặc null nếu module là unnamed module.
- **Module.getDescriptor()** trả về ModuleDescriptor hoặc null nếu module là unnamed module.
- Descriptor của automatic module vẫn tồn tại và có thể nhận diện qua **ModuleDescriptor.isAutomatic()**.
- **ModuleDescriptor** mô tả requires, exports, opens, uses, provides và các metadata của module.
- **Module::isNamed**, **Module::getName** và **Module::getDescriptor** là method reference hữu ích khi xử lý Stream<Module>.
- Tên module là dữ liệu nhận diện để đọc/log; khi cần phân biệt runtime module cụ thể, hãy xét Module object, ModuleLayer và class loader.
- Luôn xử lý null khi code có thể gặp class thuộc unnamed module.

Khi biết cách lấy Module object từ class và đọc ba phương thức cơ bản này, bạn có thể xác định class đang thuộc loại module nào, xem module name/descriptor và bắt đầu điều tra dependency hoặc quyền truy cập ở runtime.
