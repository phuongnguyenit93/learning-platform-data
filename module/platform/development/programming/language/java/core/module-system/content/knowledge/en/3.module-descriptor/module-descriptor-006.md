# Đọc descriptor bằng javap hoặc ModuleDescriptor

## 1. Module descriptor lưu thông tin gì?

Trong Java Platform Module System (JPMS), mỗi module có một **module descriptor** mô tả danh tính và hợp đồng phụ thuộc/truy cập của module. Descriptor được khai báo bằng file nguồn module-info.java và được trình biên dịch chuyển thành file nhị phân module-info.class.

Một descriptor có thể chứa:

- **Tên module**: định danh được dùng trong các khai báo phụ thuộc.
- **requires**: các module mà module hiện tại đọc và phụ thuộc vào.
- **exports**: package được công khai cho module khác; có thể export cho tất cả module đọc hoặc chỉ một số module được nêu tên.
- **opens**: package được mở cho truy cập reflection sâu; cũng có thể mở cho tất cả hoặc chỉ các module được chỉ định.
- **uses**: các service type mà module cần sử dụng.
- **provides**: service type mà module cung cấp cùng các lớp triển khai.
- **Phiên bản và lớp main tùy chọn**: metadata bổ sung nếu descriptor khai báo.

Ví dụ descriptor nguồn:

~~~java
module com.acme.greeting {
    requires java.logging;
    requires transitive com.acme.model;

    exports com.acme.greeting;
    exports com.acme.greeting.spi to com.acme.app;

    opens com.acme.greeting.internal to com.acme.test;

    uses com.acme.greeting.spi.GreetingProvider;
    provides com.acme.greeting.spi.GreetingProvider
        with com.acme.greeting.internal.DefaultGreetingProvider;
}
~~~

Khi biên dịch, Java tạo module-info.class trong output của module. Nếu đóng gói thành modular JAR, file này nằm ở gốc JAR. Đọc descriptor giúp xác định chính xác những gì module đã khai báo mà không cần suy đoán từ tên thư mục hoặc danh sách class.

## 2. Chọn công cụ phù hợp

Có hai cách phổ biến để đọc descriptor:

| Công cụ | Khi nên dùng | Kết quả |
|---|---|---|
| javap | Kiểm tra nhanh descriptor đã biên dịch, xem chi tiết bytecode và flags | Văn bản disassembly, có thể kèm constant pool và thuộc tính Module |
| java.lang.module.ModuleDescriptor | Đọc descriptor trong chương trình Java, lọc và xử lý thông tin bằng code | Đối tượng Java có các thuộc tính requires, exports, opens, uses, provides... |

Cả hai cách đều đọc metadata đã biên dịch. Chúng không tự động chứng minh mọi phụ thuộc của module đều có mặt hoặc module đã được đưa vào cấu hình runtime hiện tại.

## 3. Đọc module-info.class bằng javap

### Trường hợp output là một exploded module

Giả sử module đã được biên dịch vào thư mục out:

~~~text
out/
└── com.acme.greeting/
    ├── module-info.class
    └── com/
        └── acme/
            └── greeting/
                └── Greeting.class
~~~

Có thể truyền trực tiếp đường dẫn tới file descriptor cho javap:

~~~bash
javap -v out/com.acme.greeting/module-info.class
~~~

Tùy chọn -v (verbose) hiển thị thông tin chi tiết của class file. Với module descriptor, phần quan trọng là thuộc tính Module, trong đó có tên module, flags, các requires, exports, opens, uses và provides.

Nếu chỉ muốn xem dạng tóm tắt dễ đọc, có thể dùng:

~~~bash
javap out/com.acme.greeting/module-info.class
~~~

Kết quả phụ thuộc phiên bản JDK và mức độ chi tiết được yêu cầu. Khi cần kiểm tra modifier hoặc metadata nhị phân, nên dùng -v.

### Trường hợp module nằm trong modular JAR

Nếu module được đóng gói thành JAR trên module path, có thể chỉ định module path và tên module:

~~~bash
javap -v --module-path mods --module com.acme.greeting module-info
~~~

Trong đó:

- --module-path mods chỉ vị trí chứa các module.
- --module com.acme.greeting chọn module cần đọc.
- module-info yêu cầu javap hiển thị descriptor của module đó.
- -v hiển thị thông tin chi tiết thay vì chỉ phần khai báo rút gọn.

Tên sau --module phải là tên module, không phải tên file JAR. Tên này cần khớp với descriptor của module.

### Đọc phần nào trong kết quả?

Phần Module thường có hình thức tương tự:

~~~text
Module:
  #... // com.acme.greeting
  requires java.base
  requires java.logging
  requires transitive com.acme.model
  exports com.acme.greeting
  exports com.acme.greeting.spi to com.acme.app
  opens com.acme.greeting.internal to com.acme.test
  uses com.acme.greeting.spi.GreetingProvider
  provides com.acme.greeting.spi.GreetingProvider
    with com.acme.greeting.internal.DefaultGreetingProvider
~~~

Đây là ví dụ minh họa cấu trúc thông tin; chỉ số constant-pool và cách trình bày cụ thể có thể khác giữa các JDK.

Khi đọc kết quả, chú ý:

1. Tên module ở phần đầu để chắc chắn đang xem đúng artifact.
2. Danh sách requires để biết module khai báo phụ thuộc nào.
3. Modifier transitive hoặc static của requires để hiểu phạm vi quan hệ phụ thuộc.
4. Danh sách exports để xác định package nào thuộc API công khai.
5. Danh sách opens để nhận diện các package phục vụ reflection.
6. uses và provides để biết module tham gia ServiceLoader như thế nào.

Một dòng requires java.base thường xuất hiện trong descriptor đã biên dịch dù mã nguồn không viết trực tiếp, vì mọi module thông thường đều ngầm phụ thuộc vào module nền tảng này.

### Dùng jar để xem nhanh

Ngoài javap, công cụ jar có tùy chọn mô tả module:

~~~bash
jar --describe-module --file mods/com.acme.greeting.jar
~~~

Lệnh này hữu ích khi chỉ cần tên module, các package export, các phụ thuộc và thông tin service ở dạng tóm tắt. Dùng javap -v khi cần xem descriptor nhị phân chi tiết hơn.

## 4. Đọc descriptor bằng ModuleDescriptor trong Java

API java.lang.module.ModuleDescriptor biểu diễn descriptor dưới dạng một đối tượng Java bất biến. Có thể dùng nó để đọc tên, modifier, phụ thuộc, package export/open và service mà không phải phân tích chuỗi output của javap.

Có hai tình huống cần phân biệt:

- **Đọc module từ vị trí lưu trữ**: dùng ModuleFinder để tìm module trên module path hoặc trong các module hệ thống.
- **Đọc module đang có trong runtime**: lấy Module từ một class đã nạp rồi gọi getDescriptor().

### Đọc từ module path bằng ModuleFinder

Giả sử modular JAR nằm trong thư mục mods. Chương trình sau tìm module theo tên và lấy descriptor:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        Path modulePath = Path.of("mods");

        ModuleReference reference = ModuleFinder.of(modulePath)
            .find("com.acme.greeting")
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy module com.acme.greeting")
            );

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Module: " + descriptor.name());
        System.out.println("Automatic: " + descriptor.isAutomatic());
        System.out.println("Open: " + descriptor.isOpen());

        descriptor.requires().forEach(requirement ->
            System.out.println(
                "requires " + requirement.name()
                    + " " + requirement.modifiers()
            )
        );
    }
}
~~~

Các thành phần chính:

- ModuleFinder.of(modulePath) tạo bộ tìm module từ một hoặc nhiều vị trí trên đĩa.
- find(name) trả về Optional chứa ModuleReference nếu tìm thấy module.
- ModuleReference đại diện cho module được tìm thấy trong vị trí lưu trữ.
- descriptor() trả về ModuleDescriptor của module đó.

Nếu tên module không tồn tại trong vị trí tìm kiếm, find trả về Optional rỗng. Nếu vị trí chứa module không hợp lệ hoặc có lỗi khi đọc module, thao tác tìm kiếm có thể phát sinh FindException. Cần phân biệt hai tình huống này khi chẩn đoán.

Để đọc một module của JDK, có thể dùng ModuleFinder.ofSystem():

~~~java
ModuleDescriptor systemDescriptor = ModuleFinder.ofSystem()
    .find("java.sql")
    .orElseThrow()
    .descriptor();

System.out.println(systemDescriptor.name());
systemDescriptor.requires().forEach(r ->
    System.out.println("requires " + r.name())
);
~~~

Cách này cho phép kiểm tra descriptor của module hệ thống mà không cần sao chép JAR của JDK vào dự án.

## 5. Duyệt các thành phần của ModuleDescriptor

ModuleDescriptor cung cấp các tập hợp có kiểu rõ ràng. Có thể đọc từng phần để tạo báo cáo hoặc kiểm tra một quy ước module.

~~~java
import java.lang.module.ModuleDescriptor;

static void printDescriptor(ModuleDescriptor descriptor) {
    System.out.println("Module: " + descriptor.name());
    System.out.println("Packages: " + descriptor.packages());

    System.out.println("Requires:");
    descriptor.requires().forEach(r ->
        System.out.println("  " + r.name() + " " + r.modifiers())
    );

    System.out.println("Exports:");
    descriptor.exports().forEach(e -> {
        String target = e.targets().isEmpty()
            ? "all modules"
            : e.targets().toString();

        System.out.println("  " + e.source() + " -> " + target);
    });

    System.out.println("Opens:");
    descriptor.opens().forEach(o -> {
        String target = o.targets().isEmpty()
            ? "all modules"
            : o.targets().toString();

        System.out.println("  " + o.source() + " -> " + target);
    });

    System.out.println("Uses:");
    descriptor.uses().forEach(service ->
        System.out.println("  " + service)
    );

    System.out.println("Provides:");
    descriptor.provides().forEach(provider ->
        System.out.println(
            "  " + provider.service() + " with " + provider.providers()
        )
    );
}
~~~

Các phương thức đáng chú ý:

| Phương thức | Giá trị trả về hoặc ý nghĩa |
|---|---|
| name() | Tên module |
| modifiers() | Các modifier của descriptor |
| isOpen() | Module có được khai báo open ở cấp module hay không |
| isAutomatic() | Descriptor có đại diện automatic module hay không |
| requires() | Các phụ thuộc được khai báo |
| exports() | Các package được export |
| opens() | Các package được mở cho reflection |
| uses() | Các service type module sử dụng |
| provides() | Các service và provider module cung cấp |
| packages() | Tập package thuộc module |
| mainClass() | Optional chứa tên lớp main nếu được khai báo |
| version() | Optional chứa version của module nếu có |

Các tập hợp trả về mô tả nội dung descriptor, không phải danh sách class đã được nạp. Ví dụ packages() cho biết các package thuộc module; nó không có nghĩa tất cả class trong các package đó đã được JVM nạp.

## 6. Hiểu đúng requires, exports và opens trong kết quả

### requires

Mỗi phần tử ModuleDescriptor.Requires cung cấp tên module phụ thuộc và các modifier:

- TRANSITIVE: quan hệ đọc được truyền tới module phụ thuộc vào module hiện tại.
- STATIC: phụ thuộc có thể vắng mặt ở runtime theo quy tắc requires static.
- MANDATED hoặc SYNTHETIC: các cờ do nền tảng hoặc công cụ sinh ra trong những trường hợp tương ứng.

Có thể kiểm tra một phụ thuộc cụ thể:

~~~java
boolean requiresModelTransitively = descriptor.requires().stream()
    .anyMatch(r ->
        r.name().equals("com.acme.model")
            && r.modifiers().contains(
                ModuleDescriptor.Requires.Modifier.TRANSITIVE
            )
    );
~~~

Lưu ý rằng requires trong descriptor là thông tin module đã khai báo. Nó không tự chứng minh module phụ thuộc có mặt trên module path hoặc đã được phân giải thành công.

### exports

Mỗi ModuleDescriptor.Exports mô tả package nguồn và tập module đích (nếu có).

- targets() rỗng: package được export không giới hạn cho các module đọc module hiện tại.
- targets() có phần tử: đây là qualified export, chỉ những module được liệt kê mới nhận quyền truy cập package.

Ví dụ kiểm tra package công khai:

~~~java
descriptor.exports().forEach(exported -> {
    System.out.println("Package: " + exported.source());
    System.out.println("Targets: " + exported.targets());
});
~~~

Không nên nhầm exports với public của class. Một class có thể khai báo public nhưng nếu package của nó không được export, module khác vẫn không thể sử dụng API đó theo quy tắc truy cập module thông thường.

### opens

ModuleDescriptor.Opens cũng có package nguồn và tập module đích, nhưng phục vụ deep reflection.

- opens package không đồng nghĩa package đó được export để import và gọi API thông thường.
- qualified opens chỉ mở package cho các module được nêu tên.
- open module mở tất cả package của module cho deep reflection theo quy tắc JPMS; khi đó descriptor thể hiện trạng thái module mở ở cấp module.

Khi framework báo lỗi truy cập reflection, hãy xem cả isOpen() và opens() để xác định module có mở package cần thiết hay không.

### uses và provides

uses() chứa tên các service type mà module cần sử dụng. provides() chứa mô tả service và các provider class.

Ví dụ duyệt provider:

~~~java
descriptor.provides().forEach(provision -> {
    System.out.println("Service: " + provision.service());

    provision.providers().forEach(provider ->
        System.out.println("  Provider: " + provider)
    );
});
~~~

Thông tin này giúp hiểu module tham gia cơ chế ServiceLoader ra sao. Descriptor cho biết provider đã được khai báo; nó không chứng minh provider có thể khởi tạo thành công trong mọi môi trường runtime.

## 7. Đọc descriptor của module đang chạy

Nếu đã có một class thuộc module cần kiểm tra, có thể lấy module gắn với class đó:

~~~java
Module module = Greeting.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor == null) {
    System.out.println("Class thuộc unnamed module");
} else {
    System.out.println("Module đang chạy: " + descriptor.name());
    System.out.println("Requires: " + descriptor.requires());
    System.out.println("Exports: " + descriptor.exports());
}
~~~

Module.getDescriptor() trả về descriptor của named module. Với unnamed module, kết quả là null vì unnamed module không có module descriptor như một named module.

Cũng có thể kiểm tra module đã được phân giải trong boot layer:

~~~java
Module module = ModuleLayer.boot()
    .findModule("com.acme.greeting")
    .orElseThrow(() ->
        new IllegalStateException("Module chưa có trong boot layer")
    );

ModuleDescriptor descriptor = module.getDescriptor();
System.out.println(descriptor);
~~~

ModuleLayer.boot() đại diện boot layer của ứng dụng. Nếu ứng dụng tạo module layer riêng, cần kiểm tra đúng layer thay vì chỉ tìm trong boot layer.

Cách đọc từ Module object hữu ích khi muốn quan sát module thực sự đang gắn với class tại runtime. Cách đọc từ ModuleFinder hữu ích khi muốn kiểm tra artifact trên đĩa trước khi đưa nó vào runtime.

## 8. Đọc descriptor không đồng nghĩa phân giải module thành công

Đây là điểm quan trọng khi phân tích sự cố JPMS:

- javap có thể hiển thị descriptor của một modular JAR ngay cả khi module đó không được dùng trong lần chạy hiện tại.
- ModuleFinder có thể tìm và đọc descriptor của module trong một thư mục, nhưng thao tác này chưa xây dựng cấu hình module cho ứng dụng.
- ModuleDescriptor mô tả các yêu cầu và quyền truy cập đã khai báo; nó không xác nhận mọi requires đều được thỏa mãn.
- Module.getDescriptor() đọc descriptor của Module object đang có; để biết module có nằm trong một layer cụ thể hay không, cần truy vấn layer đó.

Nếu mục tiêu là tìm hiểu **module đã khai báo gì**, dùng javap hoặc ModuleDescriptor. Nếu mục tiêu là xác định **module nào đã được phân giải trong một lần chạy**, cần quan sát cấu hình/layer runtime hoặc dùng tùy chọn chẩn đoán như --show-module-resolution.

Một quy trình kiểm tra có thể thực hiện theo thứ tự:

1. Xác định đúng JAR hoặc thư mục module cần kiểm tra.
2. Dùng javap -v hoặc ModuleFinder để đọc descriptor trên đĩa.
3. Đối chiếu requires với các module mà ứng dụng cung cấp trên module path.
4. Dùng --show-module-resolution khi chạy để xem module thực tế được phân giải.
5. Nếu lỗi liên quan truy cập, kiểm tra exports, opens và quan hệ đọc phù hợp.

## 9. Lỗi thường gặp khi đọc descriptor

**Không tìm thấy module theo tên**

Tên truyền vào ModuleFinder.find phải là tên module, không phải tên file JAR. Kiểm tra tên descriptor bằng javap hoặc jar --describe-module trước khi gọi find.

**javap báo không tìm thấy module hoặc class**

Kiểm tra module path, tên module và tên class được truyền. Khi đọc descriptor trong exploded module, truyền đúng đường dẫn tới module-info.class; khi đọc từ module path, chọn module bằng tên đã khai báo.

**Đọc nhầm descriptor của artifact khác**

Một thư mục có thể chứa nhiều JAR hoặc nhiều phiên bản module. Đảm bảo đường dẫn và tên module trỏ tới đúng artifact mà ứng dụng đang dùng. Khi cần xác định nguồn class runtime, kết hợp log class loading và thông tin module layer.

**Không thấy exports như mong đợi**

Có thể package chỉ được mở bằng opens, hoặc module đang xem là automatic module/unnamed module. Kiểm tra descriptor thực tế và loại module trước khi kết luận.

**Descriptor có requires nhưng module phụ thuộc không tồn tại**

Đây không phải lỗi đọc descriptor. Descriptor vẫn có thể đọc được; lỗi chỉ xuất hiện khi bộ phân giải cần thỏa mãn phụ thuộc mà không tìm thấy module tương ứng.

**getDescriptor() trả về null**

Kiểm tra class có thuộc unnamed module hay không. Đây là kết quả hợp lệ đối với unnamed module, không phải lỗi đọc file.

## 10. Ghi nhớ

- module-info.java là nguồn khai báo; module-info.class là descriptor nhị phân được lưu trong output hoặc modular JAR.
- javap -v đọc chi tiết descriptor đã biên dịch, đặc biệt phần Module.
- ModuleFinder tìm module trên module path hoặc trong các module hệ thống; ModuleReference.descriptor() trả về ModuleDescriptor.
- ModuleDescriptor cung cấp API có kiểu cho requires, exports, opens, uses, provides, packages và metadata khác.
- targets() rỗng ở exports/opens thể hiện phạm vi không giới hạn theo tên module đích; có targets là qualified export/open.
- Module.getDescriptor() đọc descriptor của named module đang gắn với class; unnamed module trả về null.
- Đọc descriptor chỉ cho biết module đã khai báo gì; muốn biết module đã được phân giải trong lần chạy cần xem runtime configuration hoặc module layer.

Khi cần hiểu một module trước khi tích hợp, hãy đọc descriptor của đúng artifact bằng javap hoặc ModuleFinder. Sau đó đối chiếu các khai báo với module path và cấu hình runtime để xác định phụ thuộc, API công khai và quyền reflection thực tế.
