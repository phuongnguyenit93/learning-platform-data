# Module descriptor trong JAR modular

Một **modular JAR** là file JAR đóng gói một Java module có tên. Thành phần quyết định JAR đó là explicit named module là **module descriptor**: file nhị phân `module-info.class` được đặt ở thư mục gốc của JAR. Descriptor ghi tên module, các phụ thuộc và những package mà module công khai hoặc mở cho reflection.

Module descriptor được viết trong mã nguồn bằng `module-info.java`, sau đó trình biên dịch tạo ra `module-info.class`. Khi JAR được đặt trên module path, JVM đọc descriptor để giải quyết module và áp dụng các quy tắc JPMS. Nội dung lớp Java và tài nguyên vẫn được đóng gói trong JAR như bình thường.

## 1. Cấu trúc của một modular JAR

Một modular JAR đơn giản có thể có cấu trúc như sau:

~~~text
com.acme.geometry.jar
├── META-INF/
│   └── MANIFEST.MF
├── module-info.class
└── com/
    └── acme/
        └── geometry/
            └── api/
                └── Point.class
~~~

Các thành phần có vai trò khác nhau:

- `module-info.class` là descriptor nhị phân của module. Nó nằm ở thư mục gốc của JAR, không nằm trong package của ứng dụng.
- Các thư mục package chứa bytecode của lớp Java, ví dụ `com/acme/geometry/api/Point.class`.
- `META-INF/MANIFEST.MF` chứa metadata của JAR như phiên bản manifest, main class hoặc thuộc tính khác. Manifest không thay thế module descriptor.
- Các tài nguyên như file cấu hình, ảnh hoặc dữ liệu có thể được đóng gói cùng JAR.

Một modular JAR thông thường đại diện cho một named module. Tên module được khai báo bên trong descriptor; nó không bắt buộc phải trùng với tên file JAR. Ví dụ, file `geometry-library-2.1.jar` vẫn có thể khai báo module `com.acme.geometry`.

## 2. Tạo module descriptor từ mã nguồn

Giả sử ta xây dựng module `com.acme.geometry` với một API công khai và một lớp chạy ứng dụng. Cấu trúc mã nguồn:

~~~text
src/
└── com.acme.geometry/
    ├── module-info.java
    └── com/
        └── acme/
            └── geometry/
                ├── api/
                │   └── Point.java
                └── app/
                    └── Main.java
~~~

File `module-info.java`:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Descriptor khai báo tên module là `com.acme.geometry` và export package `com.acme.geometry.api`. Các module khác có thể đọc module này và truy cập các kiểu public trong package được export nếu chúng khai báo phụ thuộc phù hợp.

Ví dụ lớp API:

~~~java
package com.acme.geometry.api;

public record Point(int x, int y) {
}
~~~

Ví dụ lớp chạy ứng dụng nằm trong package nội bộ:

~~~java
package com.acme.geometry.app;

import com.acme.geometry.api.Point;

public class Main {
    public static void main(String[] args) {
        Point point = new Point(3, 4);
        System.out.println(point);
    }
}
~~~

Package `com.acme.geometry.app` không được export. Lớp `Main` vẫn có thể được khởi chạy trực tiếp bằng tên module và tên lớp main, nhưng module khác không thể dùng package này như API công khai.

Một module không cần khai báo `requires java.base` vì module `java.base` được yêu cầu ngầm định cho mọi named module.

## 3. Những directive thường có trong descriptor

Module descriptor không chỉ đặt tên module. Các directive mô tả quan hệ phụ thuộc, API và cơ chế dịch vụ.

### requires

`requires` khai báo module hiện tại cần đọc một module khác:

~~~java
module com.acme.report {
    requires java.sql;
}
~~~

Trong ví dụ này, module `com.acme.report` phụ thuộc vào `java.sql`. Module được yêu cầu phải có thể được tìm thấy khi biên dịch và khi giải quyết cấu hình chạy, trừ trường hợp dùng biến thể `requires static`.

### requires transitive

`requires transitive` truyền khả năng đọc module phụ thuộc tới các module phụ thuộc vào module hiện tại:

~~~java
module com.acme.persistence {
    requires transitive java.sql;
    exports com.acme.persistence.api;
}
~~~

Nếu module khác khai báo `requires com.acme.persistence`, module đó cũng đọc được `java.sql`. Cách khai báo này phù hợp khi API public của module hiện tại làm lộ các kiểu thuộc module phụ thuộc, khiến người dùng API cũng cần đọc module đó.

Không nên dùng `transitive` cho mọi dependency. Chỉ dùng khi module phụ thuộc thực sự là một phần của hợp đồng API cần truyền tới người dùng.

### requires static

`requires static` biểu thị dependency cần có khi biên dịch nhưng có thể không cần hiện diện ở runtime:

~~~java
module com.acme.integration {
    requires static com.acme.optional.annotations;
}
~~~

Directive này thường hữu ích với thư viện annotation hoặc công cụ hỗ trợ biên dịch. Nếu mã thực thi thực sự cần lớp của module đó khi chạy, việc thiếu module vẫn có thể gây lỗi khi lớp được nạp hoặc sử dụng.

### exports

`exports` công khai một package cho các module khác:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Chỉ các kiểu public trong package được export mới có thể được module khác truy cập theo quy tắc JPMS. `exports` không làm các thành viên package-private hoặc private trở thành public.

Có thể giới hạn package được export cho một số module cụ thể:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
    exports com.acme.geometry.spi to com.acme.plugin;
}
~~~

Trong ví dụ này, `com.acme.geometry.spi` chỉ được export cho `com.acme.plugin`; `com.acme.geometry.api` vẫn được export không giới hạn.

### opens

`opens` cho phép deep reflection vào package ở runtime:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.json;
}
~~~

Directive này hữu ích khi framework serialization, dependency injection hoặc persistence cần truy cập trường, constructor hay thành viên không public bằng reflection. `opens` không thay thế `exports`: nó không tạo API để module khác import và gọi các kiểu trong package ở thời điểm biên dịch.

Có thể mở toàn bộ package của một module bằng khai báo:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Một open module cho phép deep reflection vào tất cả package của nó. Chỉ dùng cách này khi thực sự cần phạm vi mở rộng; nếu chỉ một framework cần truy cập một package, `opens package.name to module.name` có phạm vi rõ ràng hơn. Không khai báo các directive `opens` riêng lẻ bên trong một `open module`.

### uses và provides

JPMS hỗ trợ cơ chế service provider. Module tiêu thụ dịch vụ khai báo `uses`:

~~~java
module com.acme.app {
    requires com.acme.geometry.spi;
    uses com.acme.geometry.spi.ShapeProvider;
}
~~~

Module cung cấp implementation khai báo `provides ... with ...`:

~~~java
module com.acme.geometry.provider {
    requires com.acme.geometry.spi;

    provides com.acme.geometry.spi.ShapeProvider
        with com.acme.geometry.provider.DefaultShapeProvider;
}
~~~

Ứng dụng có thể tìm implementation thông qua `ServiceLoader`. Kiểu provider phải đáp ứng quy tắc của service provider; lớp triển khai không nhất thiết phải được export như một API thông thường.

## 4. Biên dịch và đóng gói thành modular JAR

Với cấu trúc mã nguồn ở phần trên, dùng JDK 21 để biên dịch module:

~~~bash
javac --module-source-path src -d out -m com.acme.geometry
~~~

Ý nghĩa các tùy chọn:

- `--module-source-path src` cho biết thư mục gốc chứa các thư mục mã nguồn theo tên module.
- `-d out` đặt kết quả biên dịch vào thư mục `out`.
- `-m com.acme.geometry` yêu cầu biên dịch module có tên tương ứng.

Sau khi biên dịch, thư mục output có dạng:

~~~text
out/
└── com.acme.geometry/
    ├── module-info.class
    └── com/
        └── acme/
            └── geometry/
                ├── api/
                │   └── Point.class
                └── app/
                    └── Main.class
~~~

Dùng công cụ `jar` để đóng gói toàn bộ nội dung của module đã biên dịch:

~~~bash
jar --create --file com.acme.geometry.jar -C out/com.acme.geometry .
~~~

Tùy chọn `-C` chuyển thư mục làm việc của `jar` sang thư mục output của module trước khi thêm nội dung. Nhờ vậy, `module-info.class` được đặt ở gốc file JAR cùng với các package, đúng cấu trúc của modular JAR.

Nếu bỏ sót `module-info.class` khi đóng gói, file JAR không còn descriptor tường minh như mong muốn. Khi được đặt trên module path, JAR không có descriptor có thể được coi là automatic module; hành vi đó khác với explicit named module.

## 5. Kiểm tra descriptor bên trong JAR

Sau khi đóng gói, dùng `jar --describe-module`:

~~~bash
jar --describe-module --file com.acme.geometry.jar
~~~

Kết quả sẽ cho biết tên module và các thuộc tính mà công cụ nhận diện, ví dụ:

~~~text
com.acme.geometry jar:file:///.../com.acme.geometry.jar!/module-info.class
exports com.acme.geometry.api
requires java.base mandated
~~~

Các dòng này xác nhận:

- Tên module là `com.acme.geometry`.
- Descriptor được đọc từ `module-info.class` bên trong JAR.
- Package `com.acme.geometry.api` được export.
- Module có dependency ngầm định vào `java.base`.

Có thể liệt kê nội dung JAR để kiểm tra file descriptor và các class đã được đóng gói:

~~~bash
jar --list --file com.acme.geometry.jar
~~~

Trong kết quả cần thấy `module-info.class` ở gốc JAR và các class nằm đúng đường dẫn package. Nếu descriptor không xuất hiện hoặc tên module không đúng, hãy quay lại bước biên dịch/đóng gói để kiểm tra cấu trúc nguồn và thư mục được thêm vào JAR.

## 6. Chạy modular JAR trên module path

Đặt file JAR trên module path và chỉ rõ module cùng lớp main:

~~~bash
java --module-path com.acme.geometry.jar \
     -m com.acme.geometry/com.acme.geometry.app.Main
~~~

Phần trước dấu `/` trong đối số `-m` là tên module; phần sau là tên đầy đủ của lớp main. JVM đọc descriptor, giải quyết module rồi khởi chạy lớp được chỉ định.

Nếu module cần các module khác, những dependency đó cũng phải có mặt trên module path và được khai báo trong descriptor bằng `requires`. Ví dụ khi có nhiều JAR trong thư mục `mods`:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Không cần đặt modular JAR vào classpath để JVM nhận diện module descriptor. Nếu cùng JAR được đặt trên classpath bằng `-cp`, JVM nạp các lớp của nó vào unnamed module và bỏ qua descriptor JPMS.

## 7. Module descriptor và manifest khác nhau thế nào?

`module-info.class` và `META-INF/MANIFEST.MF` đều là metadata của JAR, nhưng phục vụ các cơ chế khác nhau.

| Thành phần | Vai trò |
|---|---|
| `module-info.class` | Khai báo tên module, dependency, package export/open và service |
| `Main-Class` trong manifest | Chỉ định lớp main cho cách chạy executable JAR bằng `java -jar` |
| `Class-Path` trong manifest | Khai báo các JAR/phần tử classpath liên quan khi chạy theo cơ chế manifest |
| `Automatic-Module-Name` trong manifest | Đặt tên ổn định cho automatic module khi JAR chưa có descriptor tường minh |

Khi JAR có `module-info.class` hợp lệ, descriptor là nguồn khai báo module. Thuộc tính `Automatic-Module-Name` không thay thế hoặc ghi đè tên module trong descriptor.

Một thư viện cũ chưa có `module-info.class` có thể khai báo `Automatic-Module-Name` để tên automatic module không phụ thuộc vào cách JVM suy ra từ tên file. Tuy nhiên, JAR đó chỉ trở thành automatic module khi được đặt trên module path. Khi đặt trên classpath, các lớp vẫn thuộc unnamed module.

## 8. Lỗi thường gặp khi tạo modular JAR

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| JVM không nhận ra tên module mong muốn | JAR thiếu `module-info.class` hoặc descriptor không nằm ở gốc JAR | Chạy `jar --list --file ...` và `jar --describe-module --file ...` |
| `FindException: Module ... not found` | Module phụ thuộc chưa có trên module path hoặc sai tên module | Kiểm tra các directive `requires` và đường dẫn chạy |
| `IllegalAccessError` hoặc lỗi truy cập package | Package cần dùng chưa được export hoặc module sử dụng chưa đọc module nguồn | Kiểm tra `exports` và `requires` |
| `InaccessibleObjectException` | Framework cần deep reflection vào package chưa được mở | Kiểm tra `opens` hoặc `open module` |
| Package không tồn tại khi biên dịch descriptor | Tên package trong `exports`/`opens` không khớp với package thực tế | Kiểm tra cấu trúc source và package declaration |
| Module chạy được trên classpath nhưng lỗi trên module path | Mã nguồn đang dựa vào truy cập xuyên package hoặc dependency không được khai báo | Kiểm tra module descriptor, API export và module graph |

Đặc biệt, đừng nhầm việc chạy được JAR trên classpath với việc JAR đã được module hóa. Classpath bỏ qua descriptor nên không kiểm tra đầy đủ các ranh giới module mà ứng dụng sẽ gặp trên module path.

## 9. Checklist kiểm tra một modular JAR

Trước khi phát hành hoặc tích hợp JAR vào ứng dụng JPMS, hãy xác nhận:

- [ ] Mã nguồn có đúng một `module-info.java` cho module đang đóng gói.
- [ ] Tên module trong descriptor ổn định và phù hợp với dependency khai báo ở các module sử dụng.
- [ ] Quá trình biên dịch tạo `module-info.class`.
- [ ] File JAR có `module-info.class` ở thư mục gốc.
- [ ] `jar --describe-module --file ...` hiển thị đúng tên module và các directive.
- [ ] Những package cần công khai được `exports` đúng phạm vi.
- [ ] Những package cần deep reflection được `opens` có giới hạn.
- [ ] Các dependency cần thiết được khai báo bằng `requires` và có mặt trên module path.
- [ ] Các directive `uses`/`provides` đúng nếu module sử dụng ServiceLoader.
- [ ] Ứng dụng được thử chạy bằng `--module-path` và `-m`.

## 10. Ghi nhớ

Module descriptor là hợp đồng JPMS được đóng gói trong `module-info.class` ở gốc modular JAR. Nó cho JVM biết module có tên gì, cần đọc module nào, công khai package nào, mở package nào cho reflection và cung cấp/tiêu thụ service ra sao. Quy trình cơ bản là viết `module-info.java`, biên dịch cùng mã nguồn, đóng gói cả descriptor vào JAR, kiểm tra bằng `jar --describe-module` rồi chạy JAR qua module path.

Khi kiểm tra một file JAR, hãy xem cả vị trí triển khai và nội dung thực tế của nó: descriptor chỉ có ý nghĩa khi JAR được sử dụng theo cơ chế module path. Việc đặt một modular JAR lên classpath vẫn khiến các lớp của nó chạy trong unnamed module và bỏ qua các quy tắc đóng gói mà descriptor đã khai báo.
