# Mở package cho framework bằng `--add-opens`

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao framework cần deep reflection trong JPMS, đọc đúng cú pháp `--add-opens`, chọn target module phù hợp cho framework chạy trên module path hoặc class path, cấu hình JVM khi chạy ứng dụng và xử lý lỗi `InaccessibleObjectException` do package chưa được mở.

## 1. Vì sao framework cần mở package?

Nhiều framework cần đọc hoặc thay đổi trạng thái của object bằng reflection. Ví dụ, dependency injection container có thể cần truy cập constructor hoặc field; ORM có thể cần đọc field để ánh xạ dữ liệu; serializer có thể cần truy cập constructor hoặc field không public để chuyển đổi object.

Trong Java trước JPMS, nhiều framework thường dùng reflection để truy cập thành viên không public mà không gặp ranh giới module rõ ràng. Với Java Platform Module System, mỗi named module kiểm soát package nào được export để truy cập thông thường và package nào được open cho deep reflection.

Khi framework gọi `setAccessible(true)` hoặc `trySetAccessible()` để truy cập private/protected/package-private member trong package của module khác, JVM kiểm tra package đó có được mở cho module chứa framework hay không. Nếu chưa mở, thao tác có thể bị từ chối, thường với lỗi:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module ...
~~~

Thông điệp lỗi thường cho biết ba thông tin quan trọng:

- Module sở hữu package, ví dụ `java.base`.
- Package cần mở, ví dụ `java.lang`.
- Module đang yêu cầu quyền reflection, ví dụ một unnamed module hoặc một named module cụ thể.

Hãy dùng chính ba thông tin đó để tạo `--add-opens` chính xác.

## 2. Cú pháp của `--add-opens`

Cú pháp tổng quát:

~~~bash
--add-opens source-module/package=target-module
~~~

Có thể mở package cho nhiều target module:

~~~bash
--add-opens source-module/package=target-one,target-two
~~~

Trong đó:

- `source-module` là module sở hữu package cần mở.
- `package` là tên package đầy đủ, không phải tên class.
- `target-module` là module chứa code framework sẽ thực hiện reflection.
- `ALL-UNNAMED` là target đặc biệt đại diện cho tất cả unnamed module.

Ví dụ mở package `java.lang` của module JDK `java.base` cho code chạy trên class path:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Ví dụ mở package `com.acme.model` trong module ứng dụng `com.acme.app` cho một framework named module:

~~~bash
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

Cách đọc biểu thức:

~~~text
com.acme.app / com.acme.model = org.example.framework
     source module     package          target module
~~~

Dấu gạch chéo phân tách source module và package. Dấu bằng phân tách package được mở và target module được nhận quyền. Không ghi tên class sau package, không dùng đường dẫn file và không bỏ tên source module.

## 3. Framework nằm trên class path: dùng `ALL-UNNAMED`

Nếu framework được nạp từ class path, code framework thuộc unnamed module của class loader tương ứng. Khi đó, target trong `--add-opens` là `ALL-UNNAMED`.

Ví dụ một ứng dụng class path sử dụng framework cần deep reflection vào package `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;lib/*" com.acme.Main
~~~

Ví dụ trên dùng dấu chấm phẩy làm path separator trên Windows. Trên Linux và macOS, dùng dấu hai chấm:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar:lib/*" com.acme.Main
~~~

Nếu framework cần truy cập package trong module ứng dụng, source module là module ứng dụng:

~~~bash
java --add-opens com.acme.app/com.acme.model=ALL-UNNAMED -cp "app.jar;lib/*" com.acme.Main
~~~

Lưu ý: `ALL-UNNAMED` mở package đã chỉ định cho tất cả unnamed module. Nó không mở tất cả package của source module. Ví dụ `java.base/java.lang=ALL-UNNAMED` chỉ mở package `java.lang` trong module `java.base`.

Chỉ dùng `ALL-UNNAMED` khi framework thực sự chạy trong unnamed module. Nếu framework là named module trên module path, hãy chỉ định tên module đó để giới hạn quyền.

## 4. Framework là named module: chỉ mở cho module đích

Nếu framework được đóng gói thành named module, hãy dùng tên module của framework làm target.

Ví dụ ứng dụng `com.acme.app` có package model cần mở cho framework `org.example.framework`:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework      --module-path mods      --module com.acme.app/com.acme.app.Main
~~~

Nếu package cần mở cho nhiều framework named module:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework,org.example.orm      --module-path mods      --module com.acme.app/com.acme.app.Main
~~~

Có thể lặp lại option `--add-opens` cho những package khác nhau:

~~~bash
java   --add-opens java.base/java.lang=org.example.framework   --add-opens java.base/java.util=org.example.framework   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Hãy xác định đúng module name từ descriptor của framework. Tên artifact Maven/Gradle hoặc tên file JAR không nhất thiết giống tên module. Có thể kiểm tra module bằng:

~~~bash
jar --describe-module --file path/to/framework.jar
~~~

Hoặc xem descriptor mà runtime tìm thấy:

~~~bash
java --module-path mods --describe-module org.example.framework
~~~

Tên target phải là tên module mà JVM nhận diện trong runtime graph.

## 5. Đặt option vào đúng nơi: JVM arguments

`--add-opens` là launcher/JVM option. Nó phải được truyền cho JVM khi tiến trình Java khởi động, trước phần chọn ứng dụng như `-m`, `-jar` hoặc tên main class.

Chạy executable JAR:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Chạy named module:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework      -p mods      -m com.acme.app/com.acme.app.Main
~~~

Chạy class path:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED      -cp "app.jar;lib/*"      com.acme.Main
~~~

Nếu framework chạy trong JVM do IDE, build tool, test runner, application server hoặc container khởi tạo, hãy thêm option vào cấu hình VM/JVM arguments của đúng tiến trình đó. Không đặt nó trong program arguments của ứng dụng.

Với test runner tạo forked JVM, option phải được truyền tới JVM con thực thi test. Việc thêm option vào JVM của Maven/Gradle không tự động bảo đảm nó được truyền sang mọi forked test process.

Trong IntelliJ IDEA hoặc IDE tương tự, tìm trường **VM options** trong cấu hình Run/Debug và thêm:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Trong Docker, thêm option vào lệnh khởi chạy Java trong `ENTRYPOINT` hoặc `CMD`, ví dụ:

~~~dockerfile
ENTRYPOINT ["java", "--add-opens=java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
~~~

Cú pháp dạng `--add-opens=...` cũng hợp lệ. Với wrapper script, hãy kiểm tra command cuối cùng thực sự gọi Java để bảo đảm option được đặt ở phía JVM.

## 6. Khi nào nên dùng `opens` trong module-info.java?

Nếu bạn phát triển module và biết framework named module nào cần reflection vào package của mình, có thể khai báo quyền mở ngay trong module descriptor.

~~~java
module com.acme.app {
    requires org.example.framework;

    exports com.acme.api;

    opens com.acme.model to org.example.framework;
}
~~~

Ở đây:

- `exports com.acme.api` cho phép module khác sử dụng API public của package.
- `opens com.acme.model to org.example.framework` cho phép framework thực hiện deep reflection trong package model.
- `requires org.example.framework` là dependency readability nếu code module ứng dụng cần đọc kiểu của framework; chỉ mở package không thay thế dependency này.

Qualified `opens` chỉ cấp quyền reflection cho target module được chỉ định. Nếu có nhiều framework named module cần truy cập, liệt kê chúng:

~~~java
opens com.acme.model to org.example.framework, org.example.orm;
~~~

Nếu framework nằm trong unnamed module, không thể viết `ALL-UNNAMED` làm target trong directive `opens` của `module-info.java`. Hãy dùng `--add-opens` ở runtime hoặc thiết kế lại cách đóng gói framework thành named module.

Một module cũng có thể dùng khai báo `open module`:

~~~java
open module com.acme.app {
    requires org.example.framework;
}
~~~

Khai báo này mở tất cả package của module cho deep reflection ở runtime. Nó có phạm vi rộng hơn qualified `opens`, nên chỉ dùng khi thực sự cần. Một open module không khai báo thêm các directive `opens` riêng bên trong.

## 7. Phân biệt `--add-opens`, `--add-exports` và `--add-reads`

Ba option thường bị nhầm lẫn:

| Option | Quyền được bổ sung | Trường hợp sử dụng |
| --- | --- | --- |
| `--add-reads` | Readability edge giữa source module và target module | Module cần đọc module khác theo module graph. |
| `--add-exports` | Export package cho target module | Code module khác cần truy cập kiểu/member public trong package. |
| `--add-opens` | Open package cho target module | Framework cần deep reflection vào thành viên không public. |

Ví dụ:

~~~bash
--add-reads com.acme.app=org.example.api
--add-exports com.acme.internal/com.acme.spi=org.example.client
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

Nếu framework báo không thể truy cập private field hoặc gọi `setAccessible(true)` thất bại, hãy kiểm tra `opens`. Thêm `exports` không phải cách thay thế cho deep reflection.

Ngược lại, nếu code Java thông thường không biên dịch hoặc không thể truy cập public type trong package, hãy kiểm tra `requires` và `exports`. `--add-opens` là quyền phục vụ reflection ở runtime, không làm package trở thành API public để code khác biên dịch phụ thuộc.

## 8. Strong encapsulation trên các JDK hiện đại

JPMS tăng cường đóng gói các package nội bộ của JDK. Từ JDK 17, strong encapsulation của các JDK internal package được áp dụng mặc định rộng rãi theo JEP 403. Những framework cũ dựa vào reflection trên JDK internals có thể bắt đầu gặp lỗi khi nâng cấp Java.

Option `--illegal-access` từng được dùng như cơ chế chuyển tiếp trong các bản Java trước đó. Trên JDK 17 trở lên, option này không còn khôi phục cơ chế truy cập rộng cũ. Khi một package cụ thể thực sự cần mở, hãy dùng `--add-opens` với source package và target module chính xác.

Không nên mở toàn bộ package của JDK hoặc toàn bộ module ứng dụng chỉ để làm mất thông báo lỗi. Hãy dùng stack trace để xác định package bị chặn, module yêu cầu reflection và thao tác framework đang thực hiện.

## 9. Đọc lỗi và tìm đúng package cần mở

Ví dụ lỗi:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final java.lang.String
java.lang.Throwable.detailMessage accessible:
module java.base does not "opens java.lang"
to unnamed module @4f3f5b24
~~~

Có thể phân tích:

- `java.lang.Throwable.detailMessage` là member mà framework muốn truy cập.
- Package cần mở là `java.lang`.
- Module sở hữu package là `java.base`.
- Target là unnamed module, vì thông báo ghi `unnamed module`.

Option tương ứng:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Nếu thông báo ghi `does not "opens com.acme.model" to module org.example.framework`, option tương ứng sẽ là:

~~~bash
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

Các bước chẩn đoán:

1. Đọc stack trace để tìm exception và member bị truy cập.
2. Xác định package chứa member, không dùng tên class làm package.
3. Xác định module sở hữu package.
4. Xác định target module từ phần `to ...` trong thông báo.
5. Thêm đúng option vào JVM arguments của tiến trình thực hiện reflection.
6. Chạy lại và xác nhận lỗi đã chuyển qua bước truy cập đó; framework có thể tiếp tục phát hiện một package khác cũng cần mở.

Không nên thêm nhiều package theo phỏng đoán. Một option chỉ giải quyết đúng package và target được ghi trong nó.

## 10. Kiểm tra trạng thái open trong code

API `Module` có thể giúp kiểm tra package có được mở cho một module đích hay không:

~~~java
Module source = SomeModel.class.getModule();
Module target = FrameworkEntryPoint.class.getModule();

boolean openToFramework =
        source.isOpen("com.acme.model", target);

System.out.println("open to framework = " + openToFramework);
~~~

Gọi `isOpen(packageName, targetModule)` trên module sở hữu package. Kết quả `true` nghĩa là package được mở cho target module theo cấu hình runtime hiện tại.

Nếu framework chạy trên class path, target có thể là unnamed module:

~~~java
Module target = FrameworkEntryPoint.class.getModule();

System.out.println(target.isNamed()); // false
~~~

Đây là cách xác định target thực tế thay vì đoán framework đang chạy trên class path hay module path.

## 11. Những lưu ý về bảo mật và bảo trì

Mở package làm giảm mức độ đóng gói của module đối với target được cấp quyền. Khi framework có thể deep-reflect vào private state, framework có thể phụ thuộc vào chi tiết triển khai nội bộ mà module không cam kết ổn định.

Một số nguyên tắc thực tế:

- Chỉ mở package mà framework thực sự cần.
- Chỉ định named target module khi có thể, thay vì dùng `ALL-UNNAMED` cho mọi trường hợp.
- Ưu tiên mở package model cần thiết thay vì mở toàn bộ module.
- Nếu bạn sở hữu module, cân nhắc qualified `opens` trong descriptor để quyền truy cập được thể hiện cùng cấu hình module.
- Ghi lại lý do của từng JVM option và kiểm tra lại khi nâng cấp framework hoặc JDK.
- Ưu tiên API công khai hoặc extension point được framework hỗ trợ nếu có thể tránh deep reflection.

`--add-opens` là công cụ tương thích hữu ích, đặc biệt khi nâng cấp ứng dụng cũ, nhưng không nên biến thành danh sách quyền mở rộng không được quản lý.

## Ghi nhớ

`--add-opens source-module/package=target-module` mở một package cho deep reflection từ module đích. Dùng `ALL-UNNAMED` khi framework chạy trên class path; dùng tên module cụ thể khi framework là named module. Đặt option trong JVM arguments của đúng tiến trình, trước `-m`, `-jar` hoặc main class. Với module do bạn quản lý, qualified `opens` trong `module-info.java` thường là cách khai báo bền vững hơn. `exports` phục vụ truy cập API public, còn `opens` phục vụ reflection sâu.
