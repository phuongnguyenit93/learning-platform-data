# Cấu trúc module-info.java và module-info.class

## 1. Module descriptor là gì?

Java Platform Module System (JPMS) được đưa vào Java 9 và vẫn là cơ chế mô-đun được dùng trong các JDK hiện hành. Một module gom các package có liên quan, khai báo module mà nó phụ thuộc, xác định package nào được công khai cho module khác và mô tả các service mà module sử dụng hoặc cung cấp.

JPMS có hai dạng descriptor tương ứng với hai giai đoạn:

- **module-info.java** là descriptor ở dạng mã nguồn. Lập trình viên viết và quản lý file này.
- **module-info.class** là descriptor ở dạng nhị phân do trình biên dịch tạo ra. Compiler và JVM đọc file này để hiểu tên module, quan hệ phụ thuộc, package được export hoặc open và các service.

Hai file mô tả cùng một module nhưng không thay thế nhau. Khi biên dịch, javac chuyển khai báo trong module-info.java thành dữ liệu nhị phân trong module-info.class.

## 2. Vị trí và quy tắc của module-info.java

Mỗi named module được khai báo tường minh có một file module-info.java ở thư mục gốc của module source tree. File này nằm ngang cấp với các thư mục package, không nằm bên trong một package.

Ví dụ cấu trúc source:

~~~text
src/
└── com.example.greeting/
    ├── module-info.java
    └── com/
        └── example/
            └── greeting/
                └── api/
                    └── Greeter.java
~~~

Các điểm cần nhớ:

- Tên file theo quy ước là **module-info.java**.
- Không viết khai báo package ở đầu file.
- Tên sau từ khóa module là tên module, thường dùng quy ước đảo ngược tên miền, ví dụ com.example.greeting.
- Tên module và tên package là hai khái niệm riêng. Module có thể chứa nhiều package.
- Module descriptor có thể có annotation và các import declaration trước khai báo module. Phần import chỉ giúp rút gọn tên kiểu dùng trong descriptor; nó không tự tạo quan hệ requires.

## 3. Cấu trúc khai báo module

Dạng tổng quát:

~~~java
module com.example.inventory {
    requires java.sql;

    exports com.example.inventory.api;
    opens com.example.inventory.model to com.example.json;

    uses com.example.inventory.spi.Storage;
    provides com.example.inventory.spi.Storage
        with com.example.inventory.internal.FileStorage;
}
~~~

Các directive trong thân module có thể được sắp xếp theo nhóm để dễ đọc. Thứ tự nhóm trong ví dụ là quy ước trình bày, không phải thứ tự bắt buộc.

### 3.1. requires — khai báo phụ thuộc

**requires module.name;** khai báo module hiện tại cần đọc module được chỉ định. Module được yêu cầu phải có thể được tìm thấy trong môi trường biên dịch hoặc phân giải module.

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Hai modifier có ý nghĩa đặc biệt:

- **requires transitive module.name;**: module phụ thuộc được đưa vào tập module mà các module đọc module hiện tại cũng có thể đọc. Dùng khi API công khai của module hiện tại phụ thuộc vào kiểu từ module kia và người dùng API cần truy cập các kiểu đó.
- **requires static module.name;**: phụ thuộc bắt buộc khi biên dịch nhưng có thể vắng mặt lúc chạy. Chỉ dùng khi ứng dụng thực sự có thể hoạt động mà không cần module đó ở runtime.

Có thể kết hợp hai modifier: **requires static transitive module.name;**.

Mọi module thông thường đều có phụ thuộc ngầm định vào **java.base**. Vì vậy không cần viết **requires java.base;**. Module java.base là module nền tảng và không khai báo requires.

### 3.2. exports — công khai package cho module khác

**exports package.name;** cho phép module khác đọc các kiểu public và protected trong package được công khai, cùng các thành viên public và protected của những kiểu đó.

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

Có thể giới hạn quyền truy cập cho một số module cụ thể:

~~~java
exports com.example.greeting.spi to com.example.integration,
                                    com.example.test;
~~~

Đây là qualified export. Nếu không có mệnh đề to, package được export cho mọi module đọc module hiện tại.

Một lớp public nằm trong package không được export vẫn không trở thành API truy cập thông thường của module khác. exports cũng không làm lộ các thành viên private hoặc package-private.

### 3.3. opens — cho phép reflection

**opens package.name;** mở package cho truy cập reflection ở runtime. Khác với exports, opens cho phép framework hoặc thư viện reflection truy cập cả kiểu và thành viên không public trong package, theo các quy tắc của Core Reflection API.

~~~java
opens com.example.inventory.model;
~~~

Có thể chỉ mở package cho module được chỉ định:

~~~java
opens com.example.inventory.model to com.example.json;
~~~

Dùng opens khi framework cần đọc hoặc ghi field private, tạo đối tượng qua reflection hoặc thực hiện các thao tác deep reflection. opens không làm package trở thành API có thể import và sử dụng trong mã nguồn của module khác.

### 3.4. open module — mở toàn bộ package cho reflection

Nếu cần mở tất cả package của một module cho reflection, có thể khai báo:

~~~java
open module com.example.persistence {
    requires java.sql;
    exports com.example.persistence.api;
}
~~~

open module mở mọi package cho reflection tại runtime. Các package vẫn phải được khai báo bằng exports nếu muốn module khác sử dụng chúng như API ở thời điểm biên dịch. Không được đặt directive opens bên trong khai báo open module; việc mở package đã được áp dụng cho toàn module.

Chỉ dùng open module khi thực sự cần phạm vi reflection rộng. Nếu chỉ một vài package cần reflection, opens theo từng package giúp giới hạn quyền truy cập tốt hơn.

### 3.5. uses và provides — khai báo ServiceLoader

**uses service.Type;** khai báo module tiêu thụ một service có thể được tìm thấy bằng java.util.ServiceLoader.

~~~java
uses com.example.inventory.spi.Storage;
~~~

**provides service.Type with provider.Type;** khai báo module cung cấp một hoặc nhiều implementation của service đó.

~~~java
provides com.example.inventory.spi.Storage
    with com.example.inventory.internal.FileStorage;
~~~

Service provider cần tuân theo mô hình provider của ServiceLoader. Cách phổ biến là provider class public, triển khai service và có public constructor không tham số. Mô hình provider method cũng được hỗ trợ: provider class có public static method tên provider không nhận tham số và trả về một implementation phù hợp.

Một module tiêu thụ service khai báo uses; module chứa implementation khai báo provides. Việc có class implementation trong module không tự động đăng ký class đó thành service provider.

## 4. Ví dụ hai module có thể biên dịch và chạy

Ví dụ sau có một module thư viện và một module ứng dụng. Thư viện export package API; ứng dụng requires thư viện để sử dụng lớp Greeter.

### 4.1. Cấu trúc thư mục

~~~text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 4.2. Descriptor của module thư viện

File src/com.example.greeting/module-info.java:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

File src/com.example.greeting/com/example/greeting/api/Greeter.java:

~~~java
package com.example.greeting.api;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 4.3. Descriptor của module ứng dụng

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Java modules"));
    }
}
~~~

### 4.4. Biên dịch và chạy

Mở terminal tại thư mục chứa thư mục src, sau đó biên dịch cả hai module:

~~~bash
javac --module-source-path src -d out -m com.example.greeting,com.example.app
~~~

Chạy main class của module ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello, Java modules!
~~~

Trong lệnh biên dịch:

- **--module-source-path src** chỉ định nơi chứa các thư mục mã nguồn theo tên module.
- **-d out** chỉ định thư mục đầu ra cho các file class.
- **-m** là dạng rút gọn của **--module**, dùng để chọn module cần biên dịch.

Trong lệnh chạy:

- **--module-path out** chỉ định nơi JVM tìm các module đã biên dịch.
- **-m module.name/main.class** chọn module và main class cần khởi chạy.

Ví dụ này đã được biên dịch và chạy thành công bằng JDK 24.0.2. Cú pháp module cơ bản trong ví dụ tương thích từ Java 9 trở lên.

Sau khi biên dịch, cấu trúc đầu ra có dạng:

~~~text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Điểm quan trọng là module-info.class nằm ở thư mục gốc của từng module, ngang cấp với cây package đã biên dịch.

## 5. Cấu trúc nhị phân của module-info.class

module-info.class tuân theo định dạng class file của JVM, nhưng nó biểu diễn một module chứ không phải một lớp Java thông thường.

Các đặc điểm được quy định trong JVM Specification:

- Cờ access_flags có **ACC_MODULE (0x8000)**. Khi cờ này được đặt, các cờ truy cập khác không được đặt.
- this_class tham chiếu tên **module-info**.
- major_version và minor_version phải biểu diễn định dạng class file từ phiên bản 53.0 trở lên, tương ứng Java 9 trở lên.
- super_class, interfaces_count, fields_count và methods_count đều bằng 0.
- Phải có đúng một thuộc tính **Module**. Thuộc tính này chứa tên module, các cờ của module, thông tin phiên bản nếu có, danh sách requires, exports, opens, uses và provides.

Constant pool của class file có thể chứa các cấu trúc chuyên biệt:

- **CONSTANT_Module_info** biểu diễn tên module.
- **CONSTANT_Package_info** biểu diễn tên package được export hoặc open.

Ngoài thuộc tính Module bắt buộc, descriptor có thể chứa một số thuộc tính bổ sung:

- **ModulePackages** ghi nhận các package thuộc module, bao gồm package được export hoặc open và package chứa service implementation.
- **ModuleMainClass** ghi nhận main class của module khi có thông tin này.

Do đó, module-info.class không chứa bytecode của các phương thức nghiệp vụ và không phải class để tạo đối tượng bằng new. Nó là dữ liệu descriptor nhị phân được compiler và hệ thống module sử dụng.

## 6. Quan hệ giữa hai file

| Tiêu chí | module-info.java | module-info.class |
|---|---|---|
| Dạng | Mã nguồn Java | Class file nhị phân |
| Tạo ra bởi | Lập trình viên hoặc công cụ tạo mã | javac |
| Mục đích | Khai báo cấu trúc và quy tắc của module | Cung cấp descriptor cho compiler và JVM |
| Nội dung | Tên module và các directive | Module attribute cùng các dữ liệu nhị phân tương ứng |
| Vị trí | Gốc của module source tree | Gốc của module output hoặc gốc JAR modular |
| Chỉnh sửa | Chỉnh sửa mã nguồn rồi biên dịch lại | Không chỉnh sửa thủ công; tạo lại từ mã nguồn |

Khi thay đổi requires, exports, opens, uses hoặc provides, cần biên dịch lại module để tạo module-info.class mới. Nếu đóng gói module thành modular JAR, file module-info.class phải nằm ở gốc JAR để hệ thống module nhận diện descriptor.

Một modular JAR được đặt trên classpath không được sử dụng như một named module; descriptor module-info.class không được áp dụng theo cách đó. Muốn dùng JPMS, đặt JAR trên module path bằng tùy chọn --module-path.

## 7. Kiểm tra descriptor sau khi biên dịch

Có thể dùng các công cụ JDK để kiểm tra descriptor mà không phải mở file nhị phân bằng tay.

Xem tên module và các directive của JAR:

~~~bash
jar --describe-module --file mods/com.example.greeting.jar
~~~

Xem cấu trúc class file, cờ ACC_MODULE và các attribute:

~~~bash
javap -v out/com.example.greeting/module-info.class
~~~

Khi đọc kết quả javap, chú ý các mục:

- **ACC_MODULE** trong access flags.
- Tên module trong descriptor.
- Thuộc tính **Module** và các bảng requires, exports, opens, uses, provides.
- **ModulePackages** hoặc **ModuleMainClass** nếu descriptor có các thuộc tính này.

## 8. Cú pháp import trong JDK mới

Từ Java 25, modular compilation unit có thể dùng single-module-import declaration trước khai báo module. Ví dụ:

~~~java
import module java.sql;

module com.example.database {
    requires java.sql;
    uses Driver;
}
~~~

Cú pháp import module giúp dùng tên kiểu ngắn hơn trong module descriptor. Nó không thay thế requires: module vẫn phải đọc java.sql thì mới có thể dùng các kiểu được export bởi module này. Đây là tiện ích cú pháp của JDK mới; nếu cần mã nguồn tương thích Java 9 đến Java 24, dùng tên kiểu đầy đủ trong module-info.java thay cho import module.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy module-info.java | Đặt file sai vị trí hoặc sai tên | Đặt module-info.java tại gốc thư mục module source |
| Lỗi cú pháp ở đầu file | Có khai báo package trong module-info.java | Bỏ khai báo package |
| Module không đọc được module khác | Thiếu requires hoặc tên module sai | Kiểm tra tên module trong descriptor và module path |
| Không truy cập được lớp public từ module khác | Package chứa lớp chưa được exports | Export đúng package trong module descriptor |
| Framework không truy cập được field private | Package chưa được mở cho reflection | Dùng opens theo package hoặc open module khi thật sự cần |
| Nhầm exports với opens | Dùng opens để thay cho API công khai hoặc dùng exports để cấp deep reflection | Dùng exports cho API thông thường; dùng opens cho reflection |
| Module không được nhận diện khi chạy | Đưa modular JAR lên classpath | Dùng --module-path và chọn module bằng -m |
| Lỗi khi dùng open module | Khai báo thêm directive opens | Bỏ opens; open module đã mở tất cả package cho reflection |
| Thiếu provider khi dùng ServiceLoader | Chưa khai báo uses hoặc provides, hoặc provider không đúng mô hình | Kiểm tra service type, provider type và constructor/provider method |
| Descriptor không phản ánh thay đổi mới | Chỉ sửa module-info.java nhưng chưa biên dịch lại | Chạy javac và đóng gói lại module/JAR |

Một module nên có ranh giới package rõ ràng. Tránh để cùng một package được phân tán trong nhiều named module trong cùng module layer, vì cấu hình module có thể thất bại do split package. Chỉ export package thuộc API mà module muốn hỗ trợ; giữ package triển khai ở trạng thái đóng nếu module khác không cần truy cập.

## 10. Checklist khi tạo module descriptor

- Đặt module-info.java ở gốc module source tree và không khai báo package.
- Dùng tên module ổn định, dễ nhận diện.
- Khai báo requires cho các phụ thuộc trực tiếp.
- Dùng requires transitive khi phụ thuộc là một phần của API công khai.
- Dùng requires static khi phụ thuộc chỉ bắt buộc ở thời điểm biên dịch và thực sự tùy chọn lúc chạy.
- Chỉ exports những package thuộc API cần công khai.
- Dùng opens với phạm vi nhỏ nhất cần thiết cho reflection.
- Khai báo uses và provides đúng với service và provider.
- Biên dịch để tạo module-info.class và kiểm tra descriptor.
- Đặt module-info.class ở gốc output/JAR và chạy module qua module path.

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html) — quy tắc về package, module declaration và các directive.
- [Java Virtual Machine Specification, Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html) — ACC_MODULE, Module, ModulePackages và ModuleMainClass.
