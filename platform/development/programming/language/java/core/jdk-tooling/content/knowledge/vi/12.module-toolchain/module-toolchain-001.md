# Module descriptor trong Java

Module descriptor là bản khai báo chính thức về một Java module: tên module, các module mà nó phụ thuộc, package nào được công khai, package nào mở cho reflection và những service mà module sử dụng hoặc cung cấp. Trong Java Platform Module System (JPMS), descriptor được viết trong tệp **module-info.java** và được biên dịch thành **module-info.class**.

Module descriptor là một phần của toolchain Java: javac đọc descriptor để kiểm tra dependency và quyền truy cập khi biên dịch; JVM dùng nó để phân giải module khi khởi chạy; các công cụ như jar, jdeps và javap giúp đóng gói, phân tích và kiểm tra cấu hình module.

Ví dụ descriptor:

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Trong đó, module có tên com.example.orders, phụ thuộc vào java.logging, công khai package api và mở package model cho deep reflection. Các directive này tạo thành hợp đồng giữa module và phần còn lại của ứng dụng.

## 1. Java module và module descriptor

Một Java module là đơn vị tổ chức mã nguồn và dependency ở mức cao hơn package. Module có thể chứa nhiều package; descriptor quy định cách những package và dependency đó được nhìn thấy từ module khác.

JPMS được giới thiệu trong Java 9. Trước JPMS, Java chủ yếu tổ chức code bằng package và quản lý dependency qua classpath. Classpath không có khai báo dependency hay ranh giới export rõ ràng; nhiều thư viện có thể nhìn thấy nhau chỉ vì cùng nằm trên classpath.

Module system bổ sung:

- **Readability:** module khai báo module nào nó cần đọc qua requires.
- **Strong encapsulation:** package chỉ được truy cập từ module khác khi được export hoặc mở theo đúng quy tắc.
- **Dependency resolution:** JVM kiểm tra và liên kết các module cần thiết khi khởi chạy.
- **Service binding:** module có thể khai báo uses/provides để dùng cơ chế ServiceLoader.
- **Module metadata:** các directive được lưu trong module-info.class để công cụ và JVM đọc.

Module descriptor không thay thế package. Package vẫn tổ chức tên lớp; module tổ chức các package và xác định ranh giới phụ thuộc.

Tên module thường dùng dạng tên miền đảo ngược, ví dụ com.example.orders hoặc org.acme.reporting. Tên module phân biệt chữ hoa/chữ thường và gồm các định danh Java phân tách bằng dấu chấm. Không dùng dấu gạch ngang như trong tên artifact Maven làm tên module Java.

## 2. module-info.java và module-info.class

Tệp nguồn descriptor phải có tên chính xác là **module-info.java**. Nó nằm ở gốc cây source của module, không nằm bên trong một package.

Ví dụ:

~~~text
src/
└── com.example.orders/
    ├── module-info.java
    └── com/
        └── example/
            └── orders/
                ├── api/
                │   └── OrderService.java
                └── internal/
                    └── OrderRepository.java
~~~

Nội dung module-info.java:

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
}
~~~

Khi biên dịch, javac tạo module-info.class trong output root của module. Class file này có cấu trúc riêng:

- Tên class nội bộ là module-info.
- Class access_flags chứa ACC_MODULE.
- Có Module attribute lưu tên module và các directive.
- Không có field hay method thông thường như class Java.
- Có thể có các attribute liên quan khác như ModulePackages hoặc ModuleMainClass tùy artifact.

ACC_MODULE có giá trị 0x8000 trong ClassFile.access_flags. Đây là flag nhận diện module descriptor, không phải modifier để viết lên class thông thường.

Một module source thông thường chỉ có một module-info.java. Một compilation unit module descriptor khai báo đúng một module; không thể đặt nhiều khai báo module trong cùng một file.

## 3. Cấu trúc cơ bản của descriptor

Cú pháp tổng quát:

~~~java
module module.name {
    requires other.module;
    exports package.name;
    opens package.name;
    uses service.Type;
    provides service.Type with provider.Type;
}
~~~

Các directive không bắt buộc phải xuất hiện hết. Chỉ khai báo những dependency, API và service module thực sự cần.

Một descriptor rỗng hợp lệ:

~~~java
module com.example.empty {
}
~~~

Module vẫn là named module, dù không khai báo dependency hay package export. Module thông thường vẫn ngầm đọc java.base; không cần viết requires java.base.

Một số quy tắc quan trọng:

- requires khai báo dependency module.
- exports công khai package cho truy cập Java thông thường.
- opens cho phép deep reflection.
- uses khai báo service mà module cần tìm.
- provides khai báo implementation cho service.
- open module mở tất cả package của module cho deep reflection.
- open module không được đồng thời khai báo directive opens riêng trong thân descriptor.

## 4. requires: khai báo dependency

Directive requires cho biết module hiện tại cần đọc một module khác.

~~~java
module com.example.orders {
    requires java.logging;
    requires com.example.customer;
}
~~~

Khi biên dịch module orders, javac cần tìm được module java.logging và com.example.customer trên module path hoặc trong các module system image phù hợp.

### requires transitive

requires transitive làm dependency trở thành một phần của API phụ thuộc được chuyển tiếp. Module khác đọc module hiện tại cũng được đọc dependency transitive đó.

Ví dụ:

~~~java
module com.example.api {
    requires transitive java.sql;
    exports com.example.api;
}
~~~

Nếu public API của com.example.api để lộ kiểu thuộc java.sql, module sử dụng API này có thể cần đọc java.sql. requires transitive giúp thể hiện quan hệ đó trong descriptor.

Không dùng transitive chỉ để làm build hết lỗi. Chỉ khai báo khi dependency thực sự là một phần của hợp đồng API công khai.

### requires static

requires static biểu thị dependency cần ở compile time nhưng không bắt buộc phải có mặt trong runtime resolution theo cách của requires thông thường.

~~~java
module com.example.reporting {
    requires static java.compiler;
}
~~~

Directive này thường hữu ích với dependency tùy chọn, ví dụ annotation hoặc API chỉ cần khi biên dịch. Nếu code thực tế cần class của module đó khi chạy một nhánh cụ thể, ứng dụng phải bảo đảm dependency có mặt ở runtime khi nhánh đó được sử dụng.

Có thể kết hợp modifier:

~~~java
module com.example.adapter {
    requires static transitive com.example.spi;
}
~~~

static và transitive là modifier của requires. Trong class file, chúng được biểu diễn bằng các module-specific flag như ACC_STATIC_PHASE và ACC_TRANSITIVE trong requires_flags.

### java.base là dependency ngầm định

Mọi module thông thường đều đọc java.base. Vì vậy không cần viết:

~~~java
requires java.base;
~~~

Nếu xem descriptor đã biên dịch bằng javap, có thể thấy requires java.base với cờ mandated dù source không khai báo directive này. Đây là dependency do module system bổ sung theo quy tắc.

## 5. exports: công khai package

Directive exports cho phép module khác truy cập public type trong package đã công khai.

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Nếu module khác khai báo:

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

thì code của module app có thể import public type từ com.example.orders.api.

Exports không tự biến package-private hoặc private member thành public. Các quy tắc truy cập của ngôn ngữ Java vẫn áp dụng sau khi module readability và package export được thỏa mãn.

Package con không tự động được export theo package cha. Ví dụ exports com.example.api không đồng nghĩa exports com.example.api.internal.

### Qualified exports

Có thể giới hạn package chỉ được export cho một số module:

~~~java
module com.example.orders {
    exports com.example.orders.spi to
        com.example.plugin,
        com.example.integration;
}
~~~

Đây là qualified export. Module không nằm trong danh sách không được truy cập package thông qua export đó, kể cả khi nó có requires tới module orders.

Qualified export hữu ích khi muốn công khai SPI cho một nhóm module tích hợp cụ thể nhưng giữ các package nội bộ không được truy cập rộng rãi.

## 6. opens: cho phép deep reflection

Exports và opens phục vụ hai mục tiêu khác nhau:

- exports cho phép truy cập thông thường tới public API của package.
- opens cho phép deep reflection vào package theo quy tắc của JPMS.

Framework ORM, dependency injection hoặc serialization đôi khi cần truy cập field, constructor hoặc member không public. Với named module, package có thể cần được mở cho framework đó.

~~~java
module com.example.model {
    opens com.example.model.entity;
}
~~~

Directive trên mở package cho deep reflection từ các module khác theo quy tắc module system.

### Qualified opens

Có thể chỉ mở package cho một module cụ thể:

~~~java
module com.example.model {
    opens com.example.model.entity to com.example.orm;
}
~~~

Chỉ module com.example.orm được hưởng quyền deep reflection từ directive này.

### open module

Nếu muốn mở tất cả package của module:

~~~java
open module com.example.model {
    requires com.example.orm;
}
~~~

Một open module mở tất cả package cho deep reflection. Trong open module, không khai báo thêm directive opens riêng. Vẫn có thể khai báo requires, exports, uses và provides.

Chỉ mở những package thực sự cần thiết. Mở toàn module làm giảm mức encapsulation và có thể khiến framework hoặc code khác truy cập nội bộ sâu hơn dự định.

## 7. uses và provides: ServiceLoader

JPMS tích hợp service binding vào module descriptor.

- uses khai báo module cần một service interface.
- provides ... with ... khai báo module cung cấp implementation cho service đó.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.GreetingService;
}
~~~

Ví dụ module provider:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

Trong Java code, ứng dụng có thể tìm implementation:

~~~java
GreetingService service = ServiceLoader
        .load(GreetingService.class)
        .findFirst()
        .orElseThrow();
~~~

Module app không cần requires trực tiếp provider module để dùng service abstraction. Khi chạy với module path và service binding, module system có thể tìm provider được khai báo cho service mà app uses.

Provider class trong ví dụ sử dụng public no-argument constructor. JPMS cũng hỗ trợ provider method theo quy tắc ServiceLoader, nhưng cần tuân theo đúng cấu trúc và kiểu trả về được quy định.

ServiceLoader giúp module phụ thuộc vào abstraction. Có thể thêm provider mới mà không phải sửa code tìm service, miễn provider module có mặt và được cấu hình đúng.

## 8. Module readability và accessibility

Để một kiểu public từ module khác có thể được sử dụng, thường cần thỏa các điều kiện:

1. Module hiện tại đọc được module chứa kiểu đó.
2. Module chứa kiểu export package tương ứng cho module hiện tại.
3. Kiểu và member cần dùng có mức truy cập phù hợp theo Java language rules.
4. Module resolution tìm thấy module và dependency cần thiết.

Ví dụ module app cần đọc module API:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

Module API phải export package:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

Nếu thiếu requires, javac có thể báo package nằm trong module nhưng module hiện tại không đọc được. Nếu thiếu exports, package tồn tại nhưng không được công khai cho module app.

requires không đồng nghĩa exports: một directive mô tả module hiện tại cần dependency nào; directive kia mô tả package nào module hiện tại cho phép module khác truy cập.

Module system cũng có quan hệ readability ngầm định với java.base và một số quan hệ được mở rộng qua requires transitive, automatic module hoặc các tùy chọn tương thích.

## 9. Classpath, module path và các loại module

Java có hai cách phổ biến để nạp thư viện:

### Classpath và unnamed module

Các JAR hoặc class directory trên classpath được xem là thuộc unnamed module của class loader tương ứng. Unnamed module có khả năng đọc các module khác và các package của nó không được quản lý bằng descriptor theo cách của named module.

Cách chạy classpath truyền thống:

~~~bash
java -cp "lib/*:build/classes" com.example.app.Main
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "lib/*;build/classes" com.example.app.Main
~~~

### Module path và named module

Module path chứa modular JAR hoặc exploded module. JVM phân giải module theo descriptor và dependency.

~~~bash
java --module-path mlib -m com.example.app/com.example.app.Main
~~~

--module-path xác định nơi tìm module. -m hoặc --module chỉ định module và main class cần chạy.

### Automatic module

Một JAR không có module-info.class nhưng được đặt trên module path có thể trở thành automatic module. Tên module có thể được xác định bởi Automatic-Module-Name trong manifest hoặc suy ra từ tên JAR.

Automatic module hỗ trợ giai đoạn chuyển đổi từ classpath sang JPMS. Nó có hành vi tương thích rộng hơn named module thông thường, nhưng không cung cấp hợp đồng encapsulation chi tiết như descriptor tường minh.

### Unnamed module và named module

Code trên classpath thuộc unnamed module. Named module không thể khai báo requires tới unnamed module. Khi chuyển thư viện cũ sang JPMS, có thể bắt đầu bằng automatic module hoặc sắp xếp dependency để dần chuyển sang named module.

Không nên xem automatic module là thiết kế cuối cùng nếu thư viện cần module boundary rõ ràng. Hãy thêm descriptor tường minh khi có thể.

## 10. Module descriptor trong toolchain javac, jar và java

Một quy trình modular build thường có các bước:

1. Tổ chức source theo module.
2. Viết module-info.java cho từng module.
3. Biên dịch bằng javac với module source path và module path khi cần.
4. Kiểm tra module-info.class bằng javap.
5. Đóng gói module thành modular JAR bằng jar.
6. Kiểm tra JAR bằng jar --describe-module.
7. Chạy bằng java --module-path và --module.

### javac --module-source-path

Khi nhiều module nằm dưới cùng source root:

~~~text
src/
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Có thể biên dịch theo tên module:

~~~bash
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.api,com.example.app
~~~

--module-source-path xác định gốc source chứa các module. -d xác định output root. -m chọn module cần biên dịch.

### javac --module-path

Nếu module app phụ thuộc modular JAR đã được build trước:

~~~bash
javac --release 17 \
    --module-path mlib \
    -d mods \
    --module-source-path src \
    -m com.example.app
~~~

Module path chứa các dependency module cần thiết. Javac đọc descriptor của các module đó để kiểm tra requires và exports.

### jar đóng gói modular JAR

Sau khi compile, mỗi exploded module có thể được đóng gói thành JAR:

~~~bash
jar --create \
    --file mlib/com.example.api.jar \
    -C mods/com.example.api .
~~~

Module descriptor module-info.class được giữ ở gốc JAR. Khi đặt JAR trên module path, JVM có thể nhận diện nó là named module.

### java chạy module

~~~bash
java --module-path mlib \
    --module com.example.app/com.example.app.Main
~~~

Có thể viết ngắn -m thay cho --module. Nếu module khai báo main class bằng ModuleMainClass hoặc manifest phù hợp, cách gọi có thể đơn giản hơn, nhưng chỉ định module/class tường minh giúp lệnh dễ hiểu.

## 11. Ví dụ hoàn chỉnh Java 17+: ba module dùng ServiceLoader

Ví dụ này tạo ba module:

- **com.example.greeter.api:** công khai service interface.
- **com.example.greeter.provider:** cung cấp implementation.
- **com.example.greeter.app:** tìm service và chạy ứng dụng.

Cấu trúc source:

~~~text
module-demo/
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

### Bước 1: module API

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

Package được export để module app và provider có thể import interface.

### Bước 2: module provider

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
        return "Hello from JPMS ServiceLoader.";
    }
}
~~~

Module provider đọc API module và công bố implementation qua provides. Package implementation không cần export chỉ để module system nạp provider được khai báo trong descriptor.

### Bước 3: module ứng dụng

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

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        GreetingService service = ServiceLoader
                .load(GreetingService.class)
                .findFirst()
                .orElseThrow();

        System.out.println(service.greeting());
    }
}
~~~

Module app khai báo uses để module system biết service nào cần được bind khi chạy.

### Bước 4: biên dịch các module

Từ thư mục gốc module-demo:

~~~bash
mkdir -p mods
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.greeter.api,com.example.greeter.provider,com.example.greeter.app
~~~

Kết quả có dạng:

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

### Bước 5: chạy từ exploded modules

~~~bash
java --module-path mods \
    --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Output:

~~~text
Hello from JPMS ServiceLoader.
~~~

Module system tìm module app, đọc requires và uses, sau đó tìm provider phù hợp trên module path.

### Bước 6: đóng gói thành modular JAR

Tạo thư mục:

~~~bash
mkdir -p mlib
~~~

Đóng gói từng module:

~~~bash
jar --create --file mlib/com.example.greeter.api.jar \
    -C mods/com.example.greeter.api .

jar --create --file mlib/com.example.greeter.provider.jar \
    -C mods/com.example.greeter.provider .

jar --create --file mlib/com.example.greeter.app.jar \
    -C mods/com.example.greeter.app .
~~~

Kiểm tra module:

~~~bash
jar --describe-module --file mlib/com.example.greeter.app.jar
~~~

Lệnh này mô tả module app, requires API và uses service. Cấu trúc dòng cụ thể tùy JDK.

Chạy các modular JAR:

~~~bash
java --module-path mlib \
    --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Output vẫn là:

~~~text
Hello from JPMS ServiceLoader.
~~~

## 12. Kiểm tra descriptor bằng javap và jar

### javap -v

Có thể đọc trực tiếp module-info.class:

~~~bash
javap -v mods/com.example.greeter.app/module-info.class
~~~

Phần output quan trọng gồm:

- flags: (0x8000) ACC_MODULE: xác nhận đây là module descriptor.
- Module: attribute chứa tên module và directive.
- requires: các dependency, gồm java.base được mandated.
- uses: service module cần.
- exports hoặc opens: package và target module tương ứng.
- provides: service và provider class.

Constant pool index và cách căn dòng thay đổi theo class file; hãy đọc tên directive và module thực tế, không so sánh số index với một output mẫu khác.

### jar --describe-module

Với modular JAR:

~~~bash
jar --describe-module --file mlib/com.example.greeter.app.jar
~~~

Lệnh này hiển thị bản mô tả module dễ đọc, thích hợp để kiểm tra nhanh sau đóng gói.

Liệt kê nội dung JAR:

~~~bash
jar --list --file mlib/com.example.greeter.app.jar
~~~

Xác nhận module-info.class nằm ở gốc archive. Nếu descriptor bị đặt sai cấp thư mục, JAR có thể không được nhận diện như named module đúng mong muốn.

### jdeps

jdeps phân tích dependency ở mức package và module:

~~~bash
jdeps --module-path mlib --check com.example.greeter.app
~~~

Có thể dùng jdeps để kiểm tra dependency module, tìm dependency không được khai báo hoặc phân tích module của thư viện. Tùy chọn chính xác phụ thuộc mục tiêu phân tích và phiên bản JDK; xem jdeps --help khi cần.

## 13. Các module flag và attribute trong class file

Module descriptor có class access flag và các module-specific flag trong Module attribute.

### ACC_MODULE

- Giá trị: 0x8000.
- Vị trí: ClassFile.access_flags.
- Ý nghĩa: class file là module descriptor module-info.class.

### Module flags

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_OPEN | 0x0020 | Module là open module |
| ACC_SYNTHETIC | 0x1000 | Module được tạo tổng hợp |
| ACC_MANDATED | 0x8000 | Module được đưa vào theo quy tắc bắt buộc |

### requires_flags

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_TRANSITIVE | 0x0020 | Dependency được chuyển tiếp |
| ACC_STATIC_PHASE | 0x0040 | Dependency cần ở compile time |
| ACC_SYNTHETIC | 0x1000 | Directive được tạo tổng hợp |
| ACC_MANDATED | 0x8000 | Directive được thêm theo quy tắc bắt buộc |

Các giá trị bit phải được giải mã theo đúng trường. Ví dụ 0x0020 là ACC_SUPER trong class access_flags, ACC_SYNCHRONIZED trong method access_flags, ACC_OPEN trong Module flags và ACC_TRANSITIVE trong requires_flags.

Module attribute cũng có thể đi cùng các attribute như ModulePackages, ModuleMainClass, ModuleTarget hoặc ModuleHashes tùy artifact. Không phải module-info.class nào cũng chứa tất cả các attribute đó.

## 14. Automatic module và migration từ classpath

Thư viện cũ thường không có module-info.class. Khi đưa JAR đó lên module path, Java có thể tạo automatic module.

Tên automatic module có thể lấy từ manifest attribute:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

Nếu không có attribute này, tên có thể được suy ra từ tên file JAR sau khi chuẩn hóa. Tên suy ra có thể không ổn định nếu artifact đổi tên; thư viện muốn hỗ trợ JPMS nên công bố Automatic-Module-Name ổn định hoặc cung cấp module descriptor thực.

Automatic module có thể đọc các module khác và export rộng các package của nó để hỗ trợ migration. Đây là cơ chế chuyển tiếp; nó không có ranh giới API rõ như explicit named module.

Một lộ trình migration thường là:

1. Xác định dependency và package của thư viện.
2. Đặt JAR legacy lên module path như automatic module.
3. Ghi nhận tên module thực tế bằng jar --describe-module.
4. Dần thay dependency hoặc cập nhật thư viện để có descriptor tường minh.
5. Khai báo requires và exports rõ ràng.
6. Chuyển code ứng dụng sang module path và kiểm tra reflection.

Không thể viết requires tới unnamed module. Nếu một dependency chỉ có trên classpath, hãy cân nhắc đặt nó trên module path dưới dạng automatic module hoặc giữ phần ứng dụng tương ứng trong unnamed module trong giai đoạn chuyển đổi.

## 15. Tùy chọn hỗ trợ tương thích khi migration

JVM cung cấp một số tùy chọn để hỗ trợ ứng dụng cũ trong giai đoạn chuyển sang JPMS:

- --add-reads: bổ sung quan hệ readability giữa các module.
- --add-exports: export một package cho module đích ở runtime.
- --add-opens: mở package cho deep reflection ở runtime.
- --patch-module: bổ sung hoặc thay thế class/resource trong một module.

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
    -jar legacy-app.jar
~~~

Lệnh này mở package java.lang của java.base cho unnamed module để hỗ trợ deep reflection. Đây là ví dụ tương thích; chỉ dùng khi đã hiểu lý do framework cần truy cập nội bộ.

Các tùy chọn này nên được xem là biện pháp migration hoặc cấu hình có chủ đích. Không dùng chúng để che giấu descriptor sai hoặc mở rộng quyền truy cập rộng hơn nhu cầu. Khi thư viện đã hỗ trợ JPMS đúng cách, nên loại bỏ các override không còn cần thiết.

## 16. Lỗi thường gặp và cách chẩn đoán

**Không tìm thấy module khi biên dịch**

Kiểm tra module path, tên module trong requires và module đã được build hay chưa. Nếu dependency là modular JAR, bảo đảm JAR nằm trực tiếp hoặc trong thư mục được module path quét.

**Package exists but is not visible**

Module hiện tại có thể thiếu requires hoặc module cung cấp package chưa exports package đó. Kiểm tra cả hai descriptor.

**Package is not exported**

Package có thể tồn tại nhưng không được module kia truy cập. Thêm exports nếu đó là API công khai thực sự; dùng opens chỉ khi cần deep reflection.

**IllegalAccessException hoặc InaccessibleObjectException**

Framework có thể cần package được opens. Ưu tiên cập nhật framework hoặc khai báo opens hẹp cho module cụ thể; chỉ dùng --add-opens khi cần cấu hình runtime tạm thời.

**ServiceLoader không tìm thấy provider**

Kiểm tra module consumer có uses, provider module có provides, provider module nằm trên module path và implementation đáp ứng quy tắc ServiceLoader.

**Module name không khớp**

Tên thư mục source module, tên trong module-info.java, tên module được requires và tên module được dùng khi chạy phải nhất quán. Với automatic module, kiểm tra tên do jar --describe-module hiển thị.

**Chạy được trên classpath nhưng lỗi trên module path**

Classpath không áp dụng các ranh giới readability/export giống named module. Kiểm tra package access, reflection và dependency không được khai báo.

**JAR không được nhận diện là modular JAR**

Kiểm tra module-info.class nằm ở gốc JAR, không nằm trong thư mục lồng thêm. Dùng jar --describe-module để xác nhận cách JDK nhận diện artifact.

**Module descriptor cũ còn sót**

Clean output directory trước khi build lại nếu đã thay đổi module-info.java hoặc package layout. Tránh đóng gói module-info.class cũ từ lần compile trước.

## 17. Quy trình thiết kế và kiểm thử module descriptor

1. Chọn tên module ổn định, dễ nhận diện.
2. Xác định package nào thuộc API công khai và package nào là nội bộ.
3. Khai báo requires tối thiểu; dùng transitive khi dependency là một phần API công khai.
4. Dùng requires static cho dependency chỉ cần ở compile time khi phù hợp.
5. Chỉ exports package cần công khai.
6. Dùng opens hẹp cho framework cần deep reflection.
7. Khai báo uses/provides nếu dùng ServiceLoader trong named modules.
8. Compile bằng javac với module source path và module path rõ ràng.
9. Kiểm tra module-info.class bằng javap -v.
10. Đóng gói và kiểm tra bằng jar --describe-module.
11. Chạy ứng dụng bằng java --module-path trên runtime mục tiêu.
12. Kiểm thử API, reflection, service binding và migration dependency.
13. Loại bỏ các tùy chọn --add-reads/--add-exports/--add-opens tạm thời khi không còn cần.

Module descriptor là hợp đồng về dependency và ranh giới truy cập của một module. Khi khai báo đúng requires, exports, opens, uses và provides, toolchain Java có thể kiểm tra dependency sớm, đóng gói module nhất quán và giúp JVM phân giải ứng dụng rõ ràng hơn.
