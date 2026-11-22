# Export package cho compile hoặc runtime access

## 1. Export package trong Java Platform Module System

Java Platform Module System (JPMS) kiểm soát package nào của một module có thể được module khác truy cập. Một module có thể chứa nhiều package public, nhưng package chỉ trở thành API có thể được module khác sử dụng khi module nguồn export package đó.

Có hai thời điểm cần quan tâm:

- **Compile time:** compiler phải cho phép source code tham chiếu kiểu và thành viên public trong package.
- **Runtime:** JVM phải cho phép bytecode của module đích truy cập các kiểu đó khi ứng dụng chạy.

Nếu chỉ cấp quyền ở một thời điểm, chương trình có thể compile thành công nhưng thất bại khi chạy. Tùy chọn **--add-exports** có thể bổ sung quyền export tại compiler hoặc JVM mà không phải sửa module descriptor của module nguồn.

Bài này tập trung vào quyền truy cập public API của package. Nếu mục tiêu là truy cập private field, private method hoặc constructor bằng deep reflection, cần hiểu thêm cơ chế **opens** và **--add-opens**.

## 2. Khai báo exports trong module-info.java

Khi sở hữu source code của module, cách rõ ràng nhất là khai báo package được export trong file module descriptor.

Ví dụ module domain có cấu trúc:

~~~text
com.acme.domain/
  module-info.java
  com/acme/domain/api/Customer.java
  com/acme/domain/internal/CustomerRepositoryImpl.java
~~~

File module-info.java:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Module khác có thể đọc public types trong package com.acme.domain.api nếu nó cũng đọc được module com.acme.domain. Package com.acme.domain.internal vẫn được giữ kín ở cấp module.

Một package được export không có nghĩa mọi class và member trong package đều trở thành public. Quy tắc truy cập Java vẫn áp dụng:

- Class hoặc interface cần được khai báo public để module khác có thể sử dụng trực tiếp.
- Member public có thể được truy cập theo quy tắc ngôn ngữ.
- Member protected, package-private và private vẫn chịu quy tắc truy cập tương ứng.
- Export không cấp quyền deep reflection vào private members.

### 2.1. Qualified exports

Nếu package chỉ nên được sử dụng bởi một số module cụ thể, có thể dùng qualified export:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin;
}
~~~

Trong ví dụ này, mọi module có thể truy cập public API trong package api, nhưng chỉ module com.acme.plugin được truy cập package spi theo quy tắc export của JPMS.

Qualified export hữu ích khi module cần cung cấp một SPI hoặc API nội bộ cho một integration cụ thể mà không công khai package đó cho toàn bộ module graph.

Tên module sau từ khóa to là tên module đích, không phải package hoặc tên JAR. Các module đích có thể được liệt kê cách nhau bằng dấu phẩy.

## 3. Cú pháp --add-exports

Tùy chọn dòng lệnh có dạng:

~~~text
--add-exports source-module/package=target-module
~~~

Có thể mở quyền export cho nhiều module đích:

~~~text
--add-exports source-module/package=target-one,target-two
~~~

Ý nghĩa từng phần:

- **source-module:** module sở hữu package, ví dụ java.base hoặc com.acme.domain.
- **package:** tên package đầy đủ, ví dụ sun.nio.ch hoặc com.acme.domain.internal.
- **target-module:** module cần được phép truy cập package.
- **ALL-UNNAMED:** ký hiệu đặc biệt đại diện cho các unnamed module, thường là code được nạp từ classpath.

Ví dụ mở một package nội bộ của JDK cho ứng dụng chạy trên classpath:

~~~bash
java --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

Ví dụ mở package cho named module:

~~~bash
java --add-exports=java.base/sun.nio.ch=com.acme.app --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Module nguồn đứng trước dấu gạch chéo. Module đích đứng sau dấu bằng. Không đảo ngược hai phía: tùy chọn này mở package của source module cho target module.

**ALL-UNNAMED** chỉ được dùng ở vị trí module đích. Nó không phải tên một module nguồn và không có nghĩa là export package cho mọi named module.

## 4. --add-exports khi compile

Nếu source code tham chiếu một public type trong package chưa được export, javac có thể báo lỗi package không được export hoặc package không visible.

Ví dụ một class thử sử dụng kiểu nội bộ của JDK:

~~~java
package com.acme.app;

import sun.nio.ch.DirectBuffer;
import java.nio.ByteBuffer;

public class InternalApiProbe {
    public static boolean isDirectBuffer(ByteBuffer buffer) {
        return buffer instanceof DirectBuffer;
    }
}
~~~

Package sun.nio.ch thuộc module java.base và không phải API được export rộng rãi cho ứng dụng. Với ứng dụng trên classpath, có thể yêu cầu javac export package cho unnamed module:

~~~bash
javac --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -d out InternalApiProbe.java
~~~

Với source thuộc named module com.acme.app, target module phải là tên module:

~~~bash
javac --module-path mods --add-exports=java.base/sun.nio.ch=com.acme.app --module-source-path src -d out -m com.acme.app
~~~

Tùy chọn này cho phép compiler chấp nhận tham chiếu tới public types trong package đó. Nó không biến package thành public API ổn định và không bảo đảm code sẽ chạy được nếu runtime chưa có quyền export tương ứng.

### 4.1. Lưu ý khi dùng --release

Khi javac được gọi với **--release**, compiler dùng API và module metadata của phiên bản Java mục tiêu. javac không cho phép dùng **--add-exports** để mở rộng tập package được export từ các system modules trong chế độ --release.

Nếu compiler từ chối kết hợp hai tùy chọn này, đó là giới hạn có chủ đích của chế độ cross-compilation. Không nên cố lách giới hạn bằng cách dựa vào implementation detail của một JDK khác. Hãy ưu tiên API công khai; nếu dự án bắt buộc dùng internal API, phải lựa chọn rõ JDK/compiler baseline và chấp nhận rủi ro tương thích.

## 5. --add-exports khi chạy ứng dụng

Quyền export ở compile time và runtime là hai cấu hình độc lập. Nếu source đã compile nhờ javac option nhưng JVM không được cấp quyền tương ứng, chương trình có thể ném **IllegalAccessError** khi thực hiện truy cập.

Với ứng dụng classpath:

~~~bash
java --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -cp out com.acme.app.InternalApiProbe
~~~

Với ứng dụng modular:

~~~bash
java --add-exports=java.base/sun.nio.ch=com.acme.app --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Cần truyền tùy chọn cho đúng JVM đang chạy ứng dụng. Đưa flag vào lệnh javac không tự động lưu quyền export vào file class hoặc JAR. Đưa flag vào một build process cũng không có nghĩa JVM production sẽ nhận được flag đó.

Nếu ứng dụng tạo JVM con, process con phải có cấu hình riêng. Tùy chọn của JVM cha không tự động được kế thừa như một quyền module của process mới.

## 6. So sánh exports, --add-exports và --add-opens

Các cơ chế này liên quan đến access control nhưng không thay thế nhau.

| Cơ chế | Đặt ở đâu | Quyền được cấp |
| --- | --- | --- |
| exports package | module-info.java của module nguồn | Export package cho mọi module theo quy tắc public access. |
| exports package to target | module-info.java của module nguồn | Export package có giới hạn cho module đích. |
| --add-exports | javac hoặc JVM | Bổ sung export động cho package của module nguồn tới module đích. |
| opens package | module-info.java của module nguồn | Mở package cho deep reflection theo phạm vi khai báo. |
| --add-opens | JVM | Bổ sung quyền deep reflection cho package và module đích. |

Nếu code cần import một public class trong package chưa export, hãy xem xét **--add-exports**.

Nếu framework cần đọc private field, gọi private method hoặc truy cập private constructor qua reflection, hãy xem xét **--add-opens**.

Export package không tự mở package cho deep reflection. Ngược lại, opens không cho phép source code import một public type trong package chưa export như một API thông thường.

Ví dụ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Module consumer có thể dùng public API trong package api. Framework com.acme.json có thể deep reflection vào package model.

## 7. Phân biệt export với readability

Để module đích truy cập một package của module nguồn, hai điều kiện cơ bản phải được đáp ứng:

1. Module đích phải đọc được module nguồn.
2. Module nguồn phải export package cho module đích.

Chỉ thị **requires** trong module descriptor thường thiết lập readability. **exports** thiết lập khả năng truy cập package.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.domain;
}
~~~

Nếu com.acme.domain không export package com.acme.domain.internal, module app vẫn không thể tham chiếu public type trong package đó.

Tùy chọn **--add-exports** bổ sung quyền export. Nó không nên được hiểu là cách thay thế tổng quát cho dependency hoặc readability. Khi module đích chưa đọc module nguồn, có thể cần cấu hình **--add-reads target-module=source-module** riêng, đồng thời bảo đảm module nguồn đã được resolve.

Với ứng dụng classpath, unnamed module có khả năng đọc các named modules phù hợp trong module graph, nên ví dụ thường dùng ALL-UNNAMED.

## 8. Cấu hình trong Gradle và Maven

Tùy chọn compile phải được truyền đến compiler. Tùy chọn runtime phải được truyền đến JVM chạy ứng dụng hoặc test. Hai vị trí cấu hình này cần được quản lý riêng.

### 8.1. Gradle compile

Với Groovy DSL và source chạy trên classpath:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
    ]
}
~~~

Nếu source là named module, thay ALL-UNNAMED bằng tên module đích, ví dụ:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports=java.base/sun.nio.ch=com.acme.app'
    ]
}
~~~

Chỉ cấu hình các task thực sự cần truy cập package đó. Nếu dùng toolchain hoặc compiler fork riêng, hãy xác nhận compiler nhận đúng arguments.

### 8.2. Gradle runtime và test

Với task Test:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
}
~~~

Với task JavaExec:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
}
~~~

Nếu dùng Application plugin, có thể cấu hình JVM arguments mặc định:

~~~groovy
application {
    applicationDefaultJvmArgs = [
        '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
    ]
}
~~~

Không giả định cấu hình Test cũng áp dụng cho JavaExec hoặc application distribution. Mỗi task có thể khởi chạy JVM riêng.

### 8.3. Maven Compiler Plugin

Ví dụ cấu hình compiler arguments cho ứng dụng classpath:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-exports</arg>
            <arg>java.base/sun.nio.ch=ALL-UNNAMED</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Với named module, thay target bằng tên module thực tế. Kiểm tra cấu hình compiler plugin và phiên bản JDK đang chạy Maven.

### 8.4. Maven Surefire

Để cấp quyền trong JVM chạy test:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-exports=java.base/sun.nio.ch=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Nếu dự án đã có argLine cho JaCoCo hoặc Java agent, cần ghép thêm tùy chọn vào giá trị hiện tại. Ghi đè argLine có thể làm mất các agent hoặc JVM flags đã cấu hình trước đó.

## 9. Chẩn đoán lỗi compile và runtime access

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| javac báo package is not visible hoặc package is not exported | Module nguồn chưa export package cho module đích | Dùng exports trong module-info.java hoặc --add-exports lúc compile. |
| javac không nhận diện module đích | Tên target module sai hoặc source đang chạy trên classpath | Dùng đúng tên named module hoặc ALL-UNNAMED. |
| Compile thành công nhưng runtime ném IllegalAccessError | JVM chạy ứng dụng chưa được cấp export tương ứng | Truyền --add-exports vào lệnh java hoặc cấu hình runtime task. |
| Runtime báo module không đọc module nguồn | Readability chưa được thiết lập hoặc module chưa resolve | Kiểm tra requires, module path và cân nhắc --add-reads khi phù hợp. |
| setAccessible(true) ném InaccessibleObjectException | Code đang cần deep reflection thay vì public access | Dùng opens hoặc --add-opens nếu thật sự cần reflection sâu. |
| Flag có trong cấu hình Gradle nhưng chạy ứng dụng vẫn lỗi | Flag chỉ được truyền cho compiler hoặc một task khác | Kiểm tra arguments của đúng JVM process đang chạy. |
| Ứng dụng hoạt động trên một JDK nhưng lỗi khi nâng cấp | Code phụ thuộc internal API đã thay đổi hoặc bị đóng gói chặt hơn | Thay bằng API công khai và kiểm tra bằng jdeps. |

Có thể dùng công cụ jdeps để phát hiện dependency vào JDK internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

Kết quả chỉ ra các class/package nội bộ mà artifact tham chiếu. Hãy xem đây là danh sách cần xử lý trong quá trình nâng cấp JDK, không phải danh sách package nên mở hàng loạt bằng --add-exports.

Có thể xem module descriptor của JAR:

~~~bash
jar --describe-module --file app.jar
~~~

Lệnh này giúp xác nhận module name và các package đã export trong descriptor. Nó không phản ánh các export động được cấp bởi command line lúc runtime.

## 10. Lựa chọn cách sửa phù hợp

Khi cần truy cập package chưa export, hãy chọn theo quyền sở hữu và mục đích:

- **Module do dự án quản lý:** khai báo exports hoặc qualified exports trong module-info.java.
- **Chỉ một module integration cần API:** dùng qualified exports để giới hạn module đích.
- **Dependency bên thứ ba hoặc JDK module không thể sửa:** dùng --add-exports tại compile và runtime nếu thực sự cần public types trong package đó.
- **Cần private reflection:** dùng opens hoặc --add-opens, không dùng --add-exports để thay thế.
- **Chỉ cần compile nhưng runtime không cần annotation/API đó:** xem xét dependency compile-time phù hợp và tránh thêm module không cần thiết vào runtime.
- **Đang dùng JDK internal API:** ưu tiên thay bằng API công khai trước khi duy trì flag dài hạn.

Không nên mở rộng toàn bộ package nội bộ cho ALL-UNNAMED chỉ để làm build hết lỗi. Mỗi flag nên chỉ rõ source module, package và target module cần quyền. Khi dependency được nâng cấp và không còn cần truy cập package đó, hãy gỡ flag và kiểm tra lại compile lẫn runtime.

## 11. Quy trình kiểm tra hoàn chỉnh

Khi gặp lỗi truy cập package trong modular application, thực hiện lần lượt:

1. Đọc thông báo lỗi để xác định module nguồn, package và module đích.
2. Kiểm tra module descriptor của module nguồn: package đã được export chưa, export có giới hạn target không?
3. Kiểm tra module đích có đọc được module nguồn không; xác nhận requires và module resolution.
4. Nếu sở hữu module nguồn, chọn exports hoặc qualified exports trong module-info.java.
5. Nếu không thể sửa module nguồn, thêm --add-exports vào javac để compile source cần quyền.
6. Thêm cùng quyền export vào JVM runtime nếu bytecode sẽ truy cập package đó khi chạy.
7. Nếu lỗi thực tế là deep reflection, chuyển sang opens hoặc --add-opens.
8. Kiểm tra command line thực tế của Gradle, Maven, IDE, container hoặc service process.
9. Dùng jdeps để tìm dependency nội bộ và lập kế hoạch loại bỏ các tham chiếu không ổn định.

JPMS yêu cầu cả readability lẫn package export để cho phép truy cập public types giữa các module. Phân biệt đúng hai điều kiện này, đồng thời cấu hình riêng compile và runtime, giúp xử lý lỗi truy cập một cách có kiểm soát mà không làm suy yếu ranh giới module rộng hơn mức cần thiết.
