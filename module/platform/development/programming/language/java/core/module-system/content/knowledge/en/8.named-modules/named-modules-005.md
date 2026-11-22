# Unnamed module đọc named module theo điều kiện nào

Trong JPMS, **unnamed module** là module đặc biệt gắn với một class loader khi các lớp được nạp từ classpath. Dù không có tên và không có file `module-info.java`, unnamed module vẫn có thể sử dụng các named module trong cấu hình runtime.

Quy tắc quan trọng là: **unnamed module đọc được tất cả named module thuộc boot layer, nhưng chỉ truy cập được các package được export phù hợp**. Vì vậy, việc một modular JAR có mặt trên module path chưa đủ để kết luận mã classpath có thể dùng mọi lớp bên trong JAR đó. Module phải được giải quyết vào cấu hình đang chạy, package cần dùng phải được export cho unnamed module, và kiểu/thành viên vẫn phải đáp ứng access modifier của Java.

## 1. Unnamed module được tạo ra như thế nào?

Khi chạy ứng dụng theo classpath, các lớp không thuộc named module được nạp vào unnamed module gắn với class loader tương ứng. Ví dụ:

~~~bash
java -cp "out:lib/*" com.acme.app.Main
~~~

Nếu chạy trên Windows, dấu phân cách các mục classpath là dấu chấm phẩy:

~~~powershell
java -cp "out;lib/*" com.acme.app.Main
~~~

Lớp `com.acme.app.Main` và các lớp thư viện được nạp từ classpath thuộc unnamed module của class loader đã nạp chúng. Unnamed module có một số đặc điểm:

- Không có tên module để khai báo bằng `requires` trong module descriptor.
- Không có file `module-info.class` riêng.
- Các package của nó được export và mở theo quy tắc đặc biệt của unnamed module.
- Nó đọc được tất cả named module trong boot layer.
- Nó không tự động trở thành named module chỉ vì classpath chứa một JAR có `module-info.class`.

Có một unnamed module riêng cho mỗi class loader. Vì vậy, nếu ứng dụng hoặc container tạo nhiều class loader, mỗi class loader có thể có unnamed module riêng. Khi dùng tùy chọn launcher `ALL-UNNAMED`, JVM áp dụng thay đổi tương ứng cho các unnamed module, bao gồm cả những module gắn với class loader được tạo trong tiến trình.

## 2. Điều kiện thứ nhất: named module phải thuộc cấu hình runtime

Unnamed module đọc được các named module trong **boot layer**. Boot layer là module layer ban đầu do JVM tạo khi khởi chạy. Các module của JDK cần thiết thường được giải quyết vào layer này; module ứng dụng hoặc thư viện trên module path cũng có thể được đưa vào nếu là root hoặc được kéo vào qua dependency/service binding.

Giả sử có một modular JAR:

~~~text
mods/
└── com.acme.api.jar
~~~

Descriptor bên trong JAR:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Ứng dụng classpath có thể chạy cùng module này bằng cách thêm module làm root:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

Tùy chọn `--add-modules com.acme.api` yêu cầu JVM đưa module đó vào quá trình resolution như một root module. Nếu module đã được kéo vào bởi dependency của một root khác, không cần thêm nó lần nữa.

Điểm cần nhớ: **module path là nơi tìm module; boot layer là cấu hình các module đã được giải quyết**. Một JAR nằm trong thư mục module path nhưng không được chọn làm root, không được dependency kéo vào và không được service binding đưa vào có thể không xuất hiện trong boot layer. Khi đó, unnamed module không thể sử dụng module đó chỉ nhờ việc file JAR tồn tại trên đĩa.

Có thể dùng `--add-modules ALL-MODULE-PATH` để yêu cầu resolution thêm tất cả module quan sát được trên module path, nhưng trong ứng dụng thông thường nên chọn các root cần thiết để cấu hình rõ ràng hơn.

## 3. Điều kiện thứ hai: package phải được export cho unnamed module

Unnamed module có readability tới named module trong boot layer, nhưng readability không đồng nghĩa với quyền truy cập mọi package. Module nguồn phải export package chứa kiểu cần dùng.

Ví dụ module thư viện:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Lớp public:

~~~java
package com.acme.api;

public class Greeting {
    public String message() {
        return "Hello from named module";
    }
}
~~~

Ứng dụng không có `module-info.java`:

~~~java
package com.acme.app;

import com.acme.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeting().message());
    }
}
~~~

Biên dịch ứng dụng classpath trong khi module thư viện nằm trên module path:

~~~bash
javac --module-path mods \
      --add-modules com.acme.api \
      -d out \
      src/com/acme/app/Main.java
~~~

Chạy ứng dụng:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

Ứng dụng classpath không cần viết `requires com.acme.api` vì unnamed module có quy tắc readability đặc biệt. Tuy nhiên, package `com.acme.api` phải được export không giới hạn hoặc được mở quyền export bằng cấu hình runtime phù hợp.

Nếu module descriptor không export package:

~~~java
module com.acme.api {
    // com.acme.api không được export
}
~~~

thì mã classpath không thể import `com.acme.api.Greeting` qua module boundary. Việc thêm `public` vào lớp không giải quyết được vấn đề này.

## 4. Qualified exports không tự động cấp quyền cho unnamed module

Module có thể export package cho một số named module cụ thể:

~~~java
module com.acme.api {
    exports com.acme.api.spi to com.acme.plugin;
}
~~~

Trong trường hợp này, package `com.acme.api.spi` chỉ được export cho module `com.acme.plugin`. Unnamed module không có tên để xuất hiện trong danh sách module đích, nên không nhận quyền truy cập package chỉ từ qualified export này.

Nếu ứng dụng classpath thực sự cần truy cập kiểu public trong package đó, có thể bổ sung export tại runtime:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     --add-exports com.acme.api/com.acme.api.spi=ALL-UNNAMED \
     -cp out \
     com.acme.app.Main
~~~

Cấu trúc tùy chọn:

~~~text
--add-exports source.module/package=target.module
~~~

Ở đây:

- `com.acme.api` là module nguồn.
- `com.acme.api.spi` là package cần export.
- `ALL-UNNAMED` là đích đặc biệt đại diện cho các unnamed module.

`ALL-UNNAMED` là ký hiệu đặc biệt dành cho các tùy chọn launcher/compiler như `--add-exports`; nó không phải tên module để ghi trong `module-info.java`. Không thể viết `exports com.acme.api.spi to ALL-UNNAMED;` trong descriptor.

Nếu có thể thay đổi module nguồn, hãy cân nhắc thiết kế API công khai phù hợp thay vì dựa lâu dài vào tùy chọn mở rộng runtime.

## 5. Điều kiện thứ ba: kiểu và thành viên vẫn tuân theo access modifier Java

Sau khi module được giải quyết và package được export, các quy tắc truy cập của ngôn ngữ Java vẫn áp dụng.

Ví dụ:

~~~java
package com.acme.api;

public class Customer {
    public String name() {
        return "An";
    }

    String internalLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }
}
~~~

Mã trong unnamed module có thể sử dụng lớp `Customer` và gọi method public `name()`. Nó không thể gọi trực tiếp `internalLabel()` vì method package-private, cũng không thể gọi `secret()` vì method private.

`exports` không biến tất cả thành viên trong package thành public. Nó chỉ cho phép module khác truy cập các kiểu public trong package theo quy tắc JPMS. Sau đó, access modifier tiếp tục quyết định thành viên nào được truy cập.

Nếu framework cần truy cập field private hoặc constructor không public bằng reflection, điều kiện export chưa đủ. Package phải được mở cho deep reflection.

## 6. Deep reflection cần opens

`exports` và `opens` phục vụ hai mục đích khác nhau:

- `exports` cho phép mã module khác truy cập API public trong package.
- `opens` cho phép reflection truy cập sâu vào các thành viên không public của package ở runtime.

Ví dụ module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model;
}
~~~

Package `com.acme.domain.model` được mở cho mọi module ở runtime. Nếu chỉ framework classpath cần reflection, có thể giới hạn bằng tùy chọn launcher:

~~~bash
java --module-path mods \
     --add-modules com.acme.domain \
     --add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED \
     -cp out \
     com.acme.app.Main
~~~

Nếu framework là named module, thay `ALL-UNNAMED` bằng tên module framework. Nếu có thể sửa descriptor, qualified opens thường thể hiện phạm vi tốt hơn:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.json;
}
~~~

Một package được mở cho reflection không tự động trở thành API để mã nguồn bên ngoài import. Nếu ứng dụng cần gọi kiểu public trong package, hãy kiểm tra thêm `exports`.

## 7. Named module có đọc được unnamed module không?

Chiều ngược lại có quy tắc khác. Unnamed module đọc các named module trong boot layer theo mặc định; named module **không tự động đọc unnamed module**.

Ví dụ ứng dụng module hóa có khai báo:

~~~java
module com.acme.app {
    // Không có requires tới thư viện classpath
}
~~~

Nếu lớp của ứng dụng cần import một thư viện chỉ có trên classpath, named module không thể tự động đọc unnamed module chứa thư viện đó. Trong giai đoạn chuyển đổi, có thể bổ sung quan hệ đọc ở runtime:

~~~bash
java --module-path mods \
     --add-reads com.acme.app=ALL-UNNAMED \
     --class-path lib/legacy.jar \
     -m com.acme.app/com.acme.app.Main
~~~

`--add-reads com.acme.app=ALL-UNNAMED` cho phép named module `com.acme.app` đọc các unnamed module. Đây là thay đổi chiều ngược lại với quy tắc đang xét trong bài. Unnamed module đọc named module vốn đã được JPMS cho phép khi module nằm trong boot layer; named module cần cấu hình bổ sung nếu muốn đọc thư viện classpath.

Một module không thể viết `requires unnamed.module` vì unnamed module không có tên ổn định để tham chiếu trong descriptor.

## 8. Kiểm tra readability và export bằng Java API

Có thể kiểm tra quan hệ module trong chương trình:

~~~java
public class ModuleAccessCheck {
    public static void main(String[] args) {
        Module unnamed = ModuleAccessCheck.class.getModule();

        Module named = ModuleLayer.boot()
            .findModule("com.acme.api")
            .orElseThrow();

        System.out.println("Caller is named: " + unnamed.isNamed());
        System.out.println("Can read named module: " + unnamed.canRead(named));
        System.out.println(
            "API package exported to caller: "
                + named.isExported("com.acme.api", unnamed)
        );
        System.out.println(
            "API package open to caller: "
                + named.isOpen("com.acme.api", unnamed)
        );
    }
}
~~~

Khi lớp `ModuleAccessCheck` được nạp từ classpath:

- `unnamed.isNamed()` trả về `false`.
- `unnamed.canRead(named)` cho biết caller có readability tới module được tìm trong boot layer hay không.
- `named.isExported(packageName, unnamed)` kiểm tra package có được export cho đúng caller không.
- `named.isOpen(packageName, unnamed)` kiểm tra package có được mở cho deep reflection đối với caller không.

Nếu `findModule` không tìm thấy module, hãy kiểm tra module đó đã được đưa vào boot layer chưa. Nếu `canRead` đúng nhưng `isExported` sai, vấn đề nằm ở quyền export package, không phải readability.

## 9. Quan sát module resolution khi chạy

Thêm `--show-module-resolution` để xem module nào được JVM giải quyết:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

Kết quả giúp xác nhận module `com.acme.api` đã tham gia cấu hình runtime hay chưa. Để kiểm tra metadata tĩnh của JAR:

~~~bash
jar --describe-module --file mods/com.acme.api.jar
~~~

Lệnh này hiển thị tên module, các directive `requires` và package `exports`. Kết hợp hai cách kiểm tra giúp phân biệt:

- JAR không được tìm thấy hoặc module không được resolve.
- Module đã resolve nhưng package không được export cho unnamed module.
- Package được export nhưng kiểu/thành viên không đáp ứng access modifier Java.
- Package cần reflection nhưng chưa được mở.

## 10. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `package ... is not visible` khi biên dịch classpath app | Package của named module chưa export hoặc module chưa được đưa vào cấu hình biên dịch | Kiểm tra `exports`, module path và `--add-modules` |
| `FindException: Module ... not found` | Module bắt buộc không có trong nguồn module được quan sát | Kiểm tra tên module và module path |
| `IllegalAccessError` | Module readability hoặc export không đáp ứng khi liên kết/chạy | Kiểm tra `canRead`, `isExported`, descriptor và tùy chọn runtime |
| `InaccessibleObjectException` | Reflection cố truy cập thành viên không public trong package chưa mở | Dùng qualified `opens` hoặc `--add-opens` cho đúng caller |
| Ứng dụng classpath gọi được API nhưng named module không gọi được | Named module không đọc unnamed module, hoặc package chưa export cho nó | Khai báo `requires`/`exports` đúng; chỉ dùng `--add-reads` khi tích hợp classpath có chủ đích |
| Module có trong thư mục `mods` nhưng không xuất hiện trong boot layer | Module không phải root và không được dependency/service binding kéo vào | Kiểm tra `--add-modules` và `--show-module-resolution` |

## 11. Quy trình chẩn đoán thực tế

Khi ứng dụng classpath cần sử dụng một named module, hãy kiểm tra theo thứ tự:

1. **Xác định module caller:** lớp gọi API thuộc unnamed module nào và được nạp bởi class loader nào?
2. **Xác nhận module nguồn:** JAR có descriptor hợp lệ và tên module đúng không?
3. **Xác nhận module được resolve:** module có thuộc boot layer không? Dùng `--add-modules` nếu cần thêm root.
4. **Kiểm tra readability:** gọi `canRead` hoặc quan sát graph để xác nhận unnamed module đọc được module nguồn.
5. **Kiểm tra export:** package chứa kiểu có được export không? Qualified export có thể không cấp quyền cho unnamed module.
6. **Kiểm tra access modifier:** lớp và thành viên có public ở mức cần thiết không?
7. **Kiểm tra reflection:** nếu framework cần deep reflection, xác nhận package được mở cho caller bằng `opens` hoặc `--add-opens`.
8. **Thử cấu hình đúng tiến trình:** đặt tùy chọn vào JVM thực sự chạy ứng dụng/test, sau đó chạy lại và kiểm tra output resolution.

Đừng thêm hàng loạt `--add-exports` hoặc `--add-opens` khi chưa xác định ranh giới nào đang chặn truy cập. Mỗi tùy chọn nên giải quyết một package và một module caller cụ thể.

## 12. Ghi nhớ

Unnamed module đọc được các named module trong boot layer, nhưng quyền đọc module không đồng nghĩa với quyền truy cập mọi package. Module nguồn phải export package cho unnamed module; các kiểu và thành viên vẫn phải tuân theo access modifier Java. Nếu cần deep reflection, package phải được mở riêng.

Khi tích hợp thư viện module hóa với ứng dụng classpath, hãy xác nhận module đã được resolve, package API được export không giới hạn hoặc được bổ sung bằng `--add-exports ...=ALL-UNNAMED`, và framework reflection được cấp `opens` phù hợp. `ALL-UNNAMED` là đích đặc biệt cho tùy chọn runtime, không phải tên module để khai báo trong `module-info.java`.
