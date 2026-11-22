# Xem module descriptor bằng javap

Module descriptor là metadata mô tả một Java module: tên module, dependency, package được export hoặc open, service được sử dụng và service provider được cung cấp. Trong Java Platform Module System (JPMS), descriptor được viết trong mã nguồn bằng **module-info.java** và được biên dịch thành **module-info.class**.

Công cụ **javap** đọc class file và hiển thị cấu trúc bên trong. Khi kiểm tra module descriptor, javap giúp xác nhận các chỉ thị như requires, exports, opens, uses và provides đã được compiler ghi nhận đúng hay chưa.

Một lệnh cơ bản:

~~~bash
javap -v path/to/module-info.class
~~~

Tùy chọn **-v** (verbose) hiển thị access flags, constant pool và các attribute chi tiết của class file, trong đó có Module attribute chứa phần lớn thông tin của module descriptor.

## 1. Module descriptor là gì?

Một module là đơn vị đóng gói và quản lý phụ thuộc của Java. Nó gom các package, khai báo những module mà nó cần và xác định package nào được module khác truy cập.

Descriptor được khai báo trong tệp có tên chính xác là module-info.java:

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Ý nghĩa:

- **module com.example.orders**: tên module.
- **requires java.logging**: module phụ thuộc vào java.logging.
- **exports com.example.orders.api**: cho phép module khác truy cập các public type trong package này theo quy tắc module.
- **opens com.example.orders.model**: cho phép reflection sâu vào package theo quy tắc của JPMS.

Javac biên dịch module-info.java thành module-info.class. Tệp này không phải class thông thường có phương thức main; nó là class file đặc biệt chứa metadata của module.

Khi kiểm tra module descriptor, cần phân biệt:

- **module-info.java** là văn bản nguồn mà developer viết.
- **module-info.class** là biểu diễn nhị phân do compiler tạo.
- **Module attribute** là attribute trong class file chứa tên module và các directive.
- **javap** là công cụ đọc class file, giúp xem biểu diễn đã biên dịch.

## 2. Class file đặc biệt module-info.class

Module descriptor được lưu trong class file có tên module-info.class. Tệp này có cấu trúc class file, nhưng có quy tắc riêng:

- Tên lớp nội bộ là module-info.
- Class access_flags có bit **ACC_MODULE**.
- Class file chứa Module attribute.
- Tệp không khai báo field hoặc method như class Java thông thường.
- Có thể có các attribute khác như ModulePackages hoặc ModuleMainClass tùy nội dung module và cách đóng gói.

**ACC_MODULE** có giá trị 0x8000 trong ClassFile.access_flags. Đây là flag nhận diện module descriptor, không phải modifier để thêm vào một class Java bình thường.

Khi javap đọc module-info.class, phần đầu output thường có dạng khái quát:

~~~text
Classfile .../module-info.class
  Compiled from "module-info.java"
  minor version: ...
  major version: ...
  flags: (0x8000) ACC_MODULE
  this_class: ... // module-info
  super_class: 0
  interfaces: 0, fields: 0, methods: 0
  ...
Module:
  ...
~~~

Các chỉ số constant pool, class file version và số lượng attribute thay đổi theo JDK và nội dung module. Đây là ví dụ minh họa cấu trúc, không phải output cố định để so sánh từng dòng.

## 3. Biên dịch module để tạo module-info.class

Với module source path, thư mục gốc chứa một thư mục con cho mỗi module:

~~~text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Ví dụ module-info.java:

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Từ thư mục gốc project, tạo thư mục output và biên dịch:

~~~bash
mkdir -p mods
javac --release 17 --module-source-path src -d mods -m com.example.app
~~~

Trong đó:

- **--release 17** biên dịch theo API và ngôn ngữ của Java 17.
- **--module-source-path src** chỉ định gốc cây thư mục chứa source của các module.
- **-d mods** chỉ định output directory.
- **-m com.example.app** yêu cầu biên dịch module có tên com.example.app.

Sau khi biên dịch, cấu trúc output thường có dạng:

~~~text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Tệp descriptor nằm ngay dưới thư mục gốc của module trong output directory. Đây là đường dẫn có thể truyền trực tiếp cho javap.

## 4. Dùng javap -v để đọc module descriptor

Lệnh trực tiếp:

~~~bash
javap -v mods/com.example.app/module-info.class
~~~

Javap hiển thị class file và các attribute. Phần quan trọng có tên **Module:**. Một đoạn output rút gọn có thể trông như sau:

~~~text
Classfile .../module-info.class
  flags: (0x8000) ACC_MODULE
  ...
Module:
  #... ,0                                   // com.example.app
  #...                                       // requires
  #... ,0                                   // java.base mandated
  #...                                       // java.logging
  #...                                       // exports
  #...                                       // com.example.app.api
~~~

Các số constant pool được thay bằng dấu ba chấm vì index phụ thuộc vào file thực tế. Khi chạy javap, hãy đọc tên module và directive sau phần chú thích; không dựa vào số index từ một ví dụ khác.

Có thể dùng đường dẫn tuyệt đối nếu đang chạy từ thư mục khác:

~~~bash
javap -v C:/work/project/mods/com.example.app/module-info.class
~~~

Trên Windows, dấu gạch chéo xuôi thường được javap chấp nhận trong đường dẫn. Nếu đường dẫn có khoảng trắng, đặt nó trong dấu nháy theo quy tắc của shell.

### Vì sao dùng -v?

Nếu chỉ dùng:

~~~bash
javap module-info.class
~~~

thông tin hiển thị có thể không đủ để kiểm tra các attribute và flag nội bộ. **-v** hiển thị chi tiết class file, bao gồm Module attribute, access flags và các attribute liên quan.

Tùy chọn **-p** (private) hữu ích khi xem class có member private. Module descriptor không có field/method thông thường để liệt kê, nên -p thường không cần thiết khi chỉ xem module-info.class.

## 5. Ý nghĩa các directive trong Module attribute

Module attribute lưu thông tin về module và các directive. Khi javap hiển thị phần Module, hãy nhận diện các nhóm sau:

| Directive | Ý nghĩa |
|---|---|
| requires | Module này phụ thuộc vào module khác |
| exports | Package được công khai cho module khác |
| opens | Package được mở cho reflection sâu |
| uses | Module sử dụng một service |
| provides | Module cung cấp implementation của một service |

### requires

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Module cần module java.logging. Trong module descriptor, requires có thể đi kèm các modifier:

- **transitive**: module phụ thuộc công khai lại dependency này cho module phụ thuộc vào nó.
- **static**: dependency cần ở compile time nhưng không bắt buộc phải có mặt trong runtime resolution theo cách của requires thông thường.

Ví dụ:

~~~java
module com.example.api {
    requires transitive java.sql;
    requires static java.compiler;
}
~~~

Trong javap, các cờ tương ứng có thể hiển thị là **ACC_TRANSITIVE** và **ACC_STATIC_PHASE** trong phần requires của Module attribute. Đây là module-specific flags; không nhầm chúng với access_flags của method hoặc class.

Module java.base được ngầm yêu cầu bởi mọi module thông thường. Vì vậy, javap thường hiển thị requires java.base với cờ mandated, dù module-info.java không viết directive này.

### exports

~~~java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.spi to com.example.plugin;
}
~~~

- Exports không kèm danh sách module: package được export rộng rãi.
- Exports có danh sách module: qualified export, chỉ các module được nêu mới được truy cập package theo quy tắc module.

Exports kiểm soát truy cập thông thường tới public type trong package. Nó không tự biến class hoặc member package-private thành public.

Trong javap, phần exports thể hiện package và có thể kèm danh sách module đích nếu là qualified export.

### opens

~~~java
module com.example.model {
    opens com.example.model.entity;
    opens com.example.model.internal to com.example.orm;
}
~~~

Opens phục vụ reflection sâu, ví dụ framework cần truy cập field hoặc constructor không public. Opens không giống exports:

- Exports cho phép truy cập thông thường tới public type và public/protected member theo quy tắc Java.
- Opens cho phép deep reflection trong phạm vi module được mở, thường phục vụ serialization, dependency injection hoặc ORM.

Có thể mở toàn bộ module bằng:

~~~java
open module com.example.model {
}
~~~

Một open module mở các package của module cho deep reflection. Trong trường hợp này không khai báo thêm các directive opens riêng bên trong module descriptor.

### uses

~~~java
module com.example.app {
    uses com.example.spi.GreetingService;
}
~~~

Directive uses khai báo module sẽ sử dụng một service thông qua ServiceLoader. Nó giúp module system biết module cần service type nào để phục vụ quá trình resolution.

### provides

~~~java
module com.example.provider {
    provides com.example.spi.GreetingService
        with com.example.impl.DefaultGreetingService;
}
~~~

Directive provides khai báo implementation của service. Tên service và provider được ghi trong Module attribute.

Module provider phải đáp ứng quy tắc của ServiceLoader: provider class có thể được khởi tạo theo cơ chế được hỗ trợ, thường là public class có public no-argument constructor hoặc provider method phù hợp.

## 6. Module-specific flags trong descriptor

Ngoài ACC_MODULE ở ClassFile.access_flags, Module attribute có các flag riêng:

| Flag | Giá trị hex | Vị trí và ý nghĩa |
|---|---:|---|
| ACC_OPEN | 0x0020 | Module là open module |
| ACC_SYNTHETIC | 0x1000 | Module được tạo tổng hợp |
| ACC_MANDATED | 0x8000 | Module được đưa vào do quy tắc hoặc công cụ bắt buộc |

Trong phần requires của Module attribute, có các flag riêng:

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_TRANSITIVE | 0x0020 | Dependency được yêu cầu theo kiểu transitive |
| ACC_STATIC_PHASE | 0x0040 | Dependency chỉ bắt buộc ở compile time |
| ACC_SYNTHETIC | 0x1000 | Directive được tạo tổng hợp |
| ACC_MANDATED | 0x8000 | Directive được thêm theo quy tắc bắt buộc |

Các giá trị bit này phải được giải mã theo đúng trường. Ví dụ 0x0020 trong Module attribute có thể là ACC_OPEN; trong requires flags là ACC_TRANSITIVE; trong class access_flags là ACC_SUPER; trong method access_flags là ACC_SYNCHRONIZED.

Đây là lý do parser class file phải biết đang đọc loại cấu trúc nào trước khi diễn giải bitmask.

## 7. Các attribute liên quan tới module

Module attribute là phần chính, nhưng module-info.class có thể có các attribute bổ sung:

- **ModulePackages:** liệt kê package thuộc module, gồm cả package không được export.
- **ModuleMainClass:** xác định main class của module nếu module được đóng gói với main class.
- **ModuleTarget:** metadata về nền tảng mục tiêu trong một số artifact.
- **ModuleHashes:** metadata hash module trong một số cách đóng gói và kiểm soát module.

Không phải module descriptor nào cũng có tất cả các attribute này. Chúng phụ thuộc cách module được biên dịch, đóng gói và công cụ tạo artifact.

Khi javap hiển thị ModulePackages: hoặc ModuleMainClass:, đó là attribute riêng trong class file, không phải directive requires/exports/opens của module-info.java.

## 8. Xem module descriptor trong JAR

Khi module được đóng gói thành JAR, module-info.class thường nằm ở gốc archive:

~~~text
com.example.app.jar
├── META-INF/
│   └── MANIFEST.MF
├── module-info.class
└── com/
    └── example/
        └── app/
            └── Main.class
~~~

Dùng jar để mô tả module:

~~~bash
jar --describe-module --file build/com.example.app.jar
~~~

Lệnh này hiển thị tên module, các dependency và package/service metadata ở mức mô tả dễ đọc. Nó hữu ích để kiểm tra nhanh nội dung module sau khi đóng gói.

Muốn xem cấu trúc class file chi tiết, trích module-info.class hoặc dùng javap với module/class phù hợp. Có thể liệt kê nội dung JAR:

~~~bash
jar --list --file build/com.example.app.jar
~~~

Sau đó giải nén module-info.class vào một thư mục tạm và chạy:

~~~bash
javap -v extracted/module-info.class
~~~

Không nhầm **jar --describe-module** với **javap -v**: jar đưa ra bản mô tả module, còn javap giải mã class file và attribute.

## 9. Dùng javap với module path

Ngoài việc trỏ thẳng tới module-info.class, javap có thể tìm class trong module thông qua module path.

Cú pháp khái quát:

~~~bash
javap --module-path mods --module com.example.app com.example.app.Main
~~~

Lệnh trên yêu cầu javap tìm class Main trong module com.example.app trên module path mods.

Để xem bytecode của class trong module:

~~~bash
javap -c --module-path mods --module com.example.app com.example.app.Main
~~~

Để xem thông tin chi tiết class:

~~~bash
javap -v --module-path mods --module com.example.app com.example.app.Main
~~~

Các lệnh này xem class Main trong module. Nếu mục tiêu là descriptor, hãy chỉ định file module-info.class trực tiếp hoặc dùng lệnh mô tả module của jar. Tách rõ hai mục tiêu tránh nhầm lẫn giữa class member và module directive.

## 10. Ví dụ thực hành Java 17+: ba module và ServiceLoader

Ví dụ sau tạo ba module:

- **com.example.greeter.api** export service interface.
- **com.example.greeter.provider** cung cấp implementation.
- **com.example.greeter.app** sử dụng service thông qua ServiceLoader.

Cấu trúc source:

~~~text
service-demo/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/GreetingService.java
    ├── com.example.greeter.provider/
    │   ├── module-info.java
    │   └── com/example/greeter/impl/DefaultGreetingService.java
    └── com.example.greeter.app/
        ├── module-info.java
        └── com/example/greeter/app/Main.java
~~~

### Module API

Tệp src/com.example.greeter.api/module-info.java:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

Tệp src/com.example.greeter.api/com/example/greeter/GreetingService.java:

~~~java
package com.example.greeter;

public interface GreetingService {
    String greeting();
}
~~~

Module export package chứa interface để các module khác có thể tham chiếu service type.

### Module provider

Tệp src/com.example.greeter.provider/module-info.java:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

Tệp src/com.example.greeter.provider/com/example/greeter/impl/DefaultGreetingService.java:

~~~java
package com.example.greeter.impl;

import com.example.greeter.GreetingService;

public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String greeting() {
        return "Hello from modular ServiceLoader.";
    }
}
~~~

Package implementation không cần export chỉ để ServiceLoader dùng provider được khai báo bằng provides. Module descriptor cung cấp thông tin provider cho module system.

### Module ứng dụng

Tệp src/com.example.greeter.app/module-info.java:

~~~java
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.GreetingService;
}
~~~

Tệp src/com.example.greeter.app/com/example/greeter/app/Main.java:

~~~java
package com.example.greeter.app;

import com.example.greeter.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        GreetingService service = ServiceLoader
                .load(GreetingService.class)
                .findFirst()
                .orElseThrow();

        System.out.println(service.greeting());
    }
}
~~~

Module ứng dụng khai báo uses vì nó tìm provider của GreetingService tại runtime.

### Biên dịch ba module

Từ thư mục gốc service-demo:

~~~bash
mkdir -p mods
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.greeter.api,com.example.greeter.provider,com.example.greeter.app
~~~

Sau khi biên dịch, output có dạng:

~~~text
mods/
├── com.example.greeter.api/
│   ├── module-info.class
│   └── com/example/greeter/GreetingService.class
├── com.example.greeter.provider/
│   ├── module-info.class
│   └── com/example/greeter/impl/DefaultGreetingService.class
└── com.example.greeter.app/
    ├── module-info.class
    └── com/example/greeter/app/Main.class
~~~

### Kiểm tra descriptor

Xem descriptor của module ứng dụng:

~~~bash
javap -v mods/com.example.greeter.app/module-info.class
~~~

Phần Module cần thể hiện:

- Module name com.example.greeter.app.
- Requires com.example.greeter.api.
- Uses com.example.greeter.GreetingService.
- Requires java.base có thể xuất hiện với cờ mandated.

Xem descriptor provider:

~~~bash
javap -v mods/com.example.greeter.provider/module-info.class
~~~

Phần Module cần thể hiện:

- Module name com.example.greeter.provider.
- Requires com.example.greeter.api.
- Provides com.example.greeter.GreetingService.
- Provider com.example.greeter.impl.DefaultGreetingService.

Các constant pool index và cách căn dòng phụ thuộc bản JDK; hãy xác nhận theo tên directive và class thực tế.

### Chạy ứng dụng

~~~bash
java --module-path mods \
    -m com.example.greeter.app/com.example.greeter.app.Main
~~~

Output:

~~~text
Hello from modular ServiceLoader.
~~~

Module provider được tìm trên module path và được module resolution liên kết thông qua service binding vì module ứng dụng khai báo uses. Ứng dụng không cần requires trực tiếp provider module để sử dụng service abstraction.

## 11. Các lỗi thường gặp khi kiểm tra descriptor

**Không tìm thấy module-info.class**

Kiểm tra thư mục output sau khi biên dịch. Với --module-source-path src và -d mods, descriptor thường nằm dưới thư mục module trong mods, không nằm trực tiếp ở mods.

**Javap báo class không tồn tại**

Đưa đường dẫn module-info.class đúng vào lệnh, hoặc dùng --module-path và --module khi xem class trong module. Kiểm tra tên module và thư mục output.

**Không thấy directive trong descriptor**

Kiểm tra đúng module-info.java đã được biên dịch chưa, build có dùng output cũ không và lệnh javac có biên dịch đúng module không. Clean output trước khi build lại nếu cần.

**Nhầm Module attribute với ACC_MODULE**

ACC_MODULE là class access flag nhận diện module-info.class. Module attribute mới chứa requires, exports, opens, uses và provides.

**Nhầm exports với opens**

Exports dành cho truy cập thông thường tới public API. Opens dành cho deep reflection. Một framework cần reflection vào private field thường cần package được opens theo đúng module.

**Không tìm thấy provider của ServiceLoader**

Kiểm tra module ứng dụng có uses, module provider có provides, provider module có mặt trên module path và provider implementation đáp ứng quy tắc ServiceLoader.

**Nhầm requires transitive với requires thông thường**

Transitive làm dependency trở thành một phần hợp đồng phụ thuộc được chuyển tiếp. Chỉ dùng khi API public của module thực sự làm lộ kiểu từ dependency đó và module phụ thuộc cần đọc được kiểu ấy.

**Đọc class file của lớp thay cho descriptor**

javap -v Main.class hiển thị metadata của lớp Main, không phải Module attribute của module. Muốn xem descriptor, chọn module-info.class.

**Dựa vào thứ tự dòng trong output**

Javap hiển thị tên directive và thông tin constant pool; thứ tự, index và format có thể thay đổi. Đọc ngữ nghĩa directive thay vì so sánh output như một chuỗi cố định.

## 12. Quy trình kiểm tra module descriptor

1. Xác định tên module và vị trí module-info.java.
2. Biên dịch module bằng --module-source-path và -d.
3. Xác định đúng đường dẫn module-info.class trong output.
4. Chạy javap -v trên descriptor.
5. Kiểm tra ACC_MODULE và Module attribute.
6. Đối chiếu requires, exports, opens, uses và provides với source.
7. Kiểm tra các flag module-specific như transitive, static phase và open.
8. Dùng jar --describe-module để kiểm tra module sau đóng gói.
9. Dùng java --module-path để kiểm thử module resolution và service binding.
10. Nếu kết quả không đúng, kiểm tra lại artifact thực tế thay vì chỉ đọc source.

Module descriptor là hợp đồng giữa một module và phần còn lại của ứng dụng. javap giúp xác nhận hợp đồng này đã được ghi vào class file đúng như mong muốn. Kết hợp javap -v, jar --describe-module và một lần chạy với module path sẽ giúp phát hiện lỗi dependency, export, reflection hoặc service provider sớm trong quy trình build.
