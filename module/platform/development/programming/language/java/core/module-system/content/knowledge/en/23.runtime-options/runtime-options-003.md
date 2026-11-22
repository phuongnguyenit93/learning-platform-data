# --add-opens cho deep reflection

## 1. Vấn đề truy cập reflection trong JPMS

Java Reflection cho phép chương trình khám phá class, field, method và constructor lúc runtime. Reflection thông thường có thể đọc metadata public; deep reflection còn cần truy cập thành viên không public, chẳng hạn private field hoặc private constructor.

Trước Java 9, code thường dùng `setAccessible(true)` để yêu cầu bỏ qua kiểm tra truy cập Java. Từ Java Platform Module System (JPMS), quyền truy cập còn chịu sự kiểm soát của ranh giới module. Một package thuộc named module có thể không được mở cho module đang thực hiện reflection, dù class và member đã được tìm thấy.

Ví dụ, framework cần đọc private field trong `java.lang.String`. Trên JDK hiện đại, lời gọi `Field.setAccessible(true)` có thể ném `InaccessibleObjectException` vì package `java.lang` của module `java.base` không được mở cho module của framework.

Tùy chọn JVM `--add-opens` cho phép mở một package cụ thể của module nguồn cho module đích tại runtime. Đây là cơ chế tương thích hữu ích khi thư viện cũ hoặc framework cần deep reflection vào package chưa được mở sẵn.

## 2. Cú pháp của --add-opens

Cú pháp tổng quát:

~~~text
--add-opens source-module/package=target-module
~~~

Có thể mở cho nhiều module đích bằng danh sách phân tách dấu phẩy:

~~~text
--add-opens source-module/package=target-module-1,target-module-2
~~~

Các thành phần:

- `source-module`: tên module sở hữu package cần mở, ví dụ `java.base`.
- `package`: tên package đầy đủ, ví dụ `java.lang`; không thêm dấu gạch chéo ở đầu và không dùng wildcard.
- `target-module`: module chứa code thực hiện deep reflection, ví dụ `com.acme.reflector`.
- `ALL-UNNAMED`: ký hiệu đặc biệt đại diện cho tất cả unnamed module, thường là code được nạp từ classpath.

Ví dụ mở package `java.lang` của `java.base` cho ứng dụng chạy trên classpath:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Ví dụ mở cùng package cho một named module:

~~~bash
java \
  --add-opens=java.base/java.lang=com.acme.reflector \
  --module-path mods \
  --module com.acme.reflector/com.acme.reflector.Main
~~~

Hãy xác định đúng module đích. Nếu framework nằm trong unnamed module, dùng `ALL-UNNAMED`. Nếu framework là named module, mở cho tên module đó. Mở cho sai target có thể khiến flag được chấp nhận nhưng code thực hiện reflection vẫn không có quyền truy cập.

## 3. Hiểu chiều mở package

Một cách dễ nhầm là đảo ngược module nguồn và module đích.

Giả sử code của ứng dụng nằm trong module `com.acme.reflector` và cần truy cập private member của class thuộc `java.lang`:

~~~text
Module nguồn: java.base
Package nguồn: java.lang
Module đích: com.acme.reflector
~~~

Cấu hình đúng:

~~~text
--add-opens=java.base/java.lang=com.acme.reflector
~~~

Module đứng trước dấu gạch chéo là module chứa package được mở. Module đứng sau dấu bằng là module được cấp quyền deep reflection vào package đó.

Nếu ứng dụng chạy bằng classpath, code phản chiếu thuộc unnamed module:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

`ALL-UNNAMED` chỉ có ý nghĩa ở vị trí module đích. Nó bao gồm các unnamed module trong JVM, kể cả những unnamed module được tạo ra sau khi JVM khởi động. Không dùng nó làm tên module nguồn.

## 4. Ví dụ thực hành với private member

Đoạn chương trình sau thử bật quyền truy cập cho field nội bộ `value` của `String`:

~~~java
import java.lang.reflect.Field;

public class ReflectiveAccess {
    public static void main(String[] args) throws NoSuchFieldException {
        Field valueField = String.class.getDeclaredField("value");

        boolean accessible = valueField.trySetAccessible();

        System.out.println("trySetAccessible: " + accessible);

        if (!accessible) {
            throw new IllegalStateException(
                    "Package java.lang chưa được mở cho module của ứng dụng");
        }

        System.out.println("Deep reflection access is enabled");
    }
}
~~~

Biên dịch và chạy trên classpath:

~~~bash
javac ReflectiveAccess.java
java ReflectiveAccess
~~~

Trên JDK hiện đại, nếu package chưa được mở, `trySetAccessible()` trả về `false`. Nếu gọi trực tiếp `setAccessible(true)` trong tình huống không được phép, chương trình có thể nhận `InaccessibleObjectException`.

Chạy lại với tùy chọn:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED ReflectiveAccess
~~~

Lúc này, `trySetAccessible()` có thể trả về `true` vì module `java.base` đã mở package `java.lang` cho unnamed module chứa chương trình.

Ví dụ chỉ kiểm tra khả năng bật quyền truy cập. Không nên phụ thuộc vào cấu trúc nội bộ của `String` trong ứng dụng thực tế: field và cách biểu diễn dữ liệu có thể thay đổi giữa các phiên bản JDK. Việc được phép truy cập một field cũng không có nghĩa mọi thao tác đọc hoặc ghi đều được JVM hỗ trợ.

## 5. Kiểm tra trạng thái mở bằng Module API

Có thể kiểm tra trạng thái mở của package từ chính JVM bằng `Module.isOpen(String, Module)`.

~~~java
public class CheckOpenPackage {
    public static void main(String[] args) {
        Module sourceModule = String.class.getModule();
        Module targetModule = CheckOpenPackage.class.getModule();

        boolean opened = sourceModule.isOpen("java.lang", targetModule);

        System.out.println("Source module: " + sourceModule.getName());
        System.out.println("Target module: " + targetModule.getName());
        System.out.println("java.lang opened: " + opened);
    }
}
~~~

Khi chạy classpath, `targetModule.getName()` là `null`, vì unnamed module không có tên. Nếu dùng `--add-opens=java.base/java.lang=ALL-UNNAMED`, kiểm tra `isOpen` với module đích sẽ cho kết quả `true`.

Có thể dùng overload `Module.isOpen(String)` để kiểm tra package có được mở không giới hạn cho mọi module hay không. Khi cần xác minh quyền giữa hai module cụ thể, nên dùng overload nhận module đích.

Phân biệt hai loại thông tin:

- `ModuleDescriptor.opens()` phản ánh các chỉ thị `opens` được khai báo trong descriptor.
- `Module.isOpen(packageName, targetModule)` phản ánh khả năng truy cập thực tế tại runtime, bao gồm các quyền mở được cấp động bằng tùy chọn JVM.

Do đó, một package có thể được mở bởi `--add-opens` dù file `module-info.java` gốc không khai báo `opens` cho package đó.

## 6. --add-opens khác gì opens và exports?

Ba cơ chế này liên quan đến module access nhưng phục vụ các mục đích khác nhau.

| Cơ chế | Phạm vi | Mục đích |
| --- | --- | --- |
| `exports package` | Khai báo trong `module-info.java` | Cho phép module khác truy cập public API của package theo quy tắc Java thông thường. |
| `opens package` | Khai báo trong `module-info.java` | Mở package cho deep reflection ở runtime. |
| `--add-opens` | Tùy chọn JVM lúc khởi chạy | Cấp quyền mở package cho module đích mà không sửa descriptor của module nguồn. |
| `--add-exports` | Tùy chọn JVM lúc khởi chạy | Cho phép truy cập public types trong package chưa export; không thay thế quyền deep reflection. |

Ví dụ module khai báo:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Module khác có thể sử dụng public API trong `com.acme.domain.api`. Framework `com.acme.json` có thể deep reflection vào `com.acme.domain.model`.

Nếu không thể sửa module nguồn, có thể mở package tại runtime:

~~~bash
java --add-opens=com.acme.domain/com.acme.domain.model=com.acme.json ...
~~~

Nếu code cần tham chiếu trực tiếp một public class nằm trong package không export, hãy xem xét `--add-exports`. Nếu code cần truy cập private field hoặc private method qua reflection, dùng `--add-opens`.

`--add-opens` không cấp quyền import hoặc gọi trực tiếp một API nội bộ khi biên dịch. Nó cũng không thay thế `requires`, không thêm module dependency và không làm package trở thành public API.

## 7. Khi nào cần --add-opens?

Các tình huống thường gặp:

- Framework dependency injection cần đọc hoặc gán private field của class trong module khác.
- ORM cần truy cập constructor hoặc field không public để ánh xạ object.
- Serialization framework cần deep reflection để đọc trạng thái object.
- Thư viện cũ truy cập implementation detail của JDK hoặc thư viện bên thứ ba.
- Test framework cần truy cập private member để kiểm tra hành vi hoặc chuẩn bị fixture.
- Plugin hoặc công cụ instrumentation cần introspection vào package của module khác.

Trước khi thêm flag, kiểm tra framework có phiên bản mới hỗ trợ JPMS hay không. Framework hiện đại có thể dùng public API, method handle hoặc yêu cầu ứng dụng mở đúng package bằng descriptor. Nếu module do chính dự án sở hữu, khai báo `opens package to target.module;` trong `module-info.java` thường giúp cấu hình được kiểm soát cùng source code.

Dùng `--add-opens` phù hợp khi cần cấu hình môi trường chạy, khi không thể chỉnh sửa module nguồn hoặc khi cần một giải pháp chuyển tiếp cho dependency cũ.

## 8. Cấu hình trong môi trường build và triển khai

Tùy chọn phải được truyền cho JVM chạy ứng dụng hoặc JVM chạy test. Thêm nó vào lệnh `javac` như một compiler option thông thường không mở package cho ứng dụng chạy sau đó.

### 8.1. Chạy JAR trực tiếp

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Đặt tùy chọn JVM trước `-jar`. Tùy chọn được truyền cho process Java được tạo bởi lệnh này.

### 8.2. Gradle test

Với Groovy DSL:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

Nếu chỉ một test task cần quyền mở package, hãy cấu hình đúng task đó thay vì áp dụng cho toàn bộ test suite.

Với task `JavaExec`:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

`Test` và `JavaExec` khởi chạy JVM riêng. Cấu hình cho một loại task không tự động áp dụng cho loại task còn lại.

### 8.3. Maven Surefire

Trong Maven Surefire Plugin, truyền tùy chọn qua `argLine`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-opens=java.base/java.lang=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Nếu dự án đã dùng `argLine` cho JaCoCo hoặc agent khác, hãy ghép tùy chọn vào cấu hình hiện có thay vì ghi đè toàn bộ giá trị. Nếu không, agent hoặc tùy chọn JVM trước đó có thể biến mất.

### 8.4. IDE, container và service

Trong IDE, đặt flag trong mục VM options của Run/Debug Configuration. Trong Docker hoặc service script, thêm flag vào command khởi chạy JVM thực tế.

Ví dụ một container chạy ứng dụng trên classpath:

~~~dockerfile
ENTRYPOINT ["java", "--add-opens=java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
~~~

Đảm bảo flag được truyền tới process Java cuối cùng. Đặt flag trong một shell script hoặc cấu hình của build process không có tác dụng với JVM khác nếu build tool không chuyển tiếp tùy chọn đó.

Nếu ứng dụng tạo process Java con, mỗi process cần được cấu hình riêng. Tùy chọn của JVM cha không tự động trở thành tùy chọn khởi chạy của JVM con.

## 9. Giới hạn và lưu ý bảo mật

`--add-opens` là quyền mở package khá rộng: mọi class trong module đích được cấp khả năng deep reflection vào package được chỉ định. Vì vậy:

1. Chỉ mở package thực sự cần thiết. Tránh mở toàn bộ `java.base` hoặc nhiều package nội bộ cùng lúc.
2. Ưu tiên chỉ định named target module thay vì `ALL-UNNAMED` nếu framework chạy trong named module.
3. Không coi flag là cách sửa thiết kế API. Nếu code mới cần truy cập dữ liệu, hãy ưu tiên public API hoặc một SPI được module công khai.
4. Flag không sửa `module-info.class`, không thay đổi file JAR và không tự làm dependency được resolve.
5. Flag không bỏ qua mọi giới hạn của JVM. Ví dụ, một số field final đặc biệt vẫn không thể thay đổi bằng reflection ngay cả khi package đã được mở.
6. Quyền mở chỉ tồn tại trong JVM được khởi chạy với flag. Một lần chạy test thành công không chứng minh production đã có cùng cấu hình.
7. Tránh dựa vào các package nội bộ của JDK vì chúng không phải API ổn định và có thể thay đổi giữa các bản phát hành.

Từ JDK 16/17, strong encapsulation đối với nhiều API nội bộ được thực thi chặt chẽ hơn. Tùy chọn `--illegal-access` cũ không phải giải pháp thay thế đáng tin cậy trên JDK mới. Khi gặp `InaccessibleObjectException`, hãy xác định module và package trong thông báo lỗi rồi mở đúng package cho đúng module đích nếu thật sự cần.

## 10. Quy trình chẩn đoán lỗi deep reflection

Khi một thư viện ném `InaccessibleObjectException` hoặc `trySetAccessible()` trả về `false`, làm theo thứ tự:

1. Đọc đầy đủ thông báo lỗi để xác định module nguồn và package bị chặn.
2. Xác định module đích chứa code thực hiện reflection. Nếu code nằm trên classpath, module đích là unnamed module.
3. Xác nhận API đang cần deep reflection. Nếu chỉ cần public API của package chưa export, đánh giá `--add-exports`.
4. Thêm đúng một tùy chọn `--add-opens=source-module/package=target-module` vào JVM thực sự chạy code.
5. Khởi chạy lại cùng command và xác nhận `trySetAccessible()` hoặc `Module.isOpen(package, targetModule)`.
6. Nếu chạy qua Gradle, Maven, IDE hoặc container, kiểm tra command line của JVM con; đừng chỉ kiểm tra cấu hình build.
7. Nếu module thuộc dự án của mình, cân nhắc khai báo `opens package to target.module;` trong descriptor để quyền truy cập được quản lý cùng source.
8. Sau khi nâng cấp framework hoặc loại bỏ nhu cầu reflection, gỡ flag và xác nhận ứng dụng vẫn hoạt động.

Mục tiêu là mở đúng package, đúng chiều module và đúng JVM. Điều đó giúp giải quyết yêu cầu deep reflection trong khi vẫn giữ phạm vi truy cập có thể kiểm soát.
