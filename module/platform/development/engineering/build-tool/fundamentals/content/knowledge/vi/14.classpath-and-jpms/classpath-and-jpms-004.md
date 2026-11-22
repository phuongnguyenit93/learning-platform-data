# Lớp trùng tên và ảnh hưởng của thứ tự classpath

Một ứng dụng Java thường được tạo từ nhiều thư mục class và nhiều JAR. Mỗi thư viện có thể chứa hàng trăm hoặc hàng nghìn lớp. Khi JVM cần nạp một lớp, nó phải tìm định nghĩa lớp phù hợp từ các nguồn được cung cấp cho class loader.

Vấn đề xuất hiện khi hai nguồn cùng chứa một lớp có tên đầy đủ giống nhau, chẳng hạn cả `library-a.jar` và `library-b.jar` đều có `com.example.util.StringHelper`. Khi đó, thứ tự classpath và chính sách của class loader có thể quyết định định nghĩa nào được sử dụng. Kết quả có thể là ứng dụng chạy với phiên bản khác dự kiến, lỗi `NoSuchMethodError`, `NoSuchFieldError`, `ClassCastException`, hoặc lỗi chỉ xuất hiện trên một môi trường.

Để hiểu hiện tượng này, cần phân biệt **tên lớp**, **định danh lớp trong JVM**, **thứ tự tìm kiếm classpath** và **cơ chế delegation của class loader**. Thứ tự classpath là một yếu tố quan trọng, nhưng không phải yếu tố duy nhất quyết định lớp nào được nạp.

## 1. Classpath là gì?

Classpath là danh sách vị trí mà Java compiler, launcher hoặc class loader sử dụng để tìm lớp và tài nguyên. Các phần tử có thể là:

- Thư mục chứa cấu trúc package và các tệp `.class`.
- Tệp JAR chứa class file và resource.
- Các JAR/thư mục khác được thêm vào qua cấu hình khởi chạy hoặc công cụ build.

Ví dụ cấu trúc:

```text
application/
├── build/classes/java/main/
│   └── com/example/Application.class
└── lib/
    ├── commons.jar
    └── reporting.jar
```

Khi chạy ứng dụng, có thể chỉ định classpath:

```bash
# Linux/macOS: các phần tử classpath phân cách bằng dấu :
java -cp "build/classes/java/main:lib/commons.jar:lib/reporting.jar" \
  com.example.Application
```

```powershell
# Windows: các phần tử classpath phân cách bằng dấu ;
java -cp "build\classes\java\main;lib\commons.jar;lib\reporting.jar" `
  com.example.Application
```

Classpath có thể được đặt bằng tùy chọn `-cp` hoặc `-classpath`, biến môi trường `CLASSPATH`, manifest của JAR trong một số cách khởi chạy, hay build tool. Nếu chỉ định `-cp` trên command line, giá trị đó được dùng cho lần khởi chạy và thay thế classpath môi trường theo quy tắc của launcher.

Trong dự án Gradle/Maven, người dùng thường không tự ghép classpath. Build tool phân giải dependency và xây dựng compile/runtime classpath tương ứng.

## 2. Tên lớp đầy đủ và vị trí class file

Một lớp Java có tên đầy đủ (fully qualified class name) gồm package và tên lớp. Ví dụ:

```java
package com.example.util;

public class StringHelper {
}
```

Tên đầy đủ của lớp là:

```text
com.example.util.StringHelper
```

Khi class loader tìm lớp này trong một thư mục classpath, nó tìm đường dẫn tương ứng:

```text
com/example/util/StringHelper.class
```

Trong JAR, entry cũng có đường dẫn tương tự:

```text
com/example/util/StringHelper.class
```

Vì vậy, nếu hai JAR đều chứa entry này, chúng đang cung cấp hai định nghĩa nhị phân có cùng tên lớp đầy đủ. JVM không xem chúng là hai lớp khác nhau chỉ vì chúng nằm trong hai file JAR khác nhau.

Ví dụ:

```text
lib-a.jar
└── com/example/util/StringHelper.class

lib-b.jar
└── com/example/util/StringHelper.class
```

Nếu cả hai JAR nằm trong cùng classpath và được cùng một class loader tìm kiếm, một định nghĩa thường được tìm thấy trước và được dùng cho tên lớp đó. JAR còn lại không tự tạo ra một lớp thứ hai cùng tên trong cùng class loader.

## 3. Thứ tự phần tử classpath ảnh hưởng thế nào?

Khi class loader tìm một lớp trong các phần tử classpath, thứ tự tìm kiếm của các phần tử có thể quyết định nguồn định nghĩa được chọn. Với application class loader thông thường, classpath được cung cấp cho launcher được tìm theo thứ tự của các entry sau khi xét cơ chế delegation tới parent loader.

Giả sử:

```text
classpath = build/classes/java/main:lib-a.jar:lib-b.jar
```

Trong đó:

- `lib-a.jar` chứa `com.example.util.StringHelper` phiên bản 1.
- `lib-b.jar` chứa cùng lớp nhưng là phiên bản 2.

Khi application class loader tìm `com.example.util.StringHelper`, nếu parent loader không định nghĩa lớp đó, nó tìm trong classpath theo thứ tự. Nếu lớp được tìm thấy trong `lib-a.jar` trước, định nghĩa từ `lib-a.jar` thường được nạp. Việc đảo thứ tự hai JAR có thể làm định nghĩa từ `lib-b.jar` được chọn.

```text
Classpath A:
build/classes -> lib-a.jar -> lib-b.jar
                         |
                         +--> StringHelper version 1 được tìm thấy trước

Classpath B:
build/classes -> lib-b.jar -> lib-a.jar
                         |
                         +--> StringHelper version 2 được tìm thấy trước
```

Điều này có thể làm cùng một mã nguồn chạy khác nhau chỉ vì thứ tự JAR trong classpath khác nhau.

### 3.1. Thứ tự classpath không phải lúc nào cũng là toàn bộ quy tắc

Trước khi tìm trong classpath ứng dụng, class loader có thể hỏi parent loader theo mô hình delegation. Vì vậy, một lớp có thể được nạp từ JDK hoặc một loader cha trước khi application classpath được xét.

Ngoài ra:

- Class loader tùy chỉnh có thể dùng chính sách child-first hoặc quy tắc tìm kiếm khác.
- Một số framework/module container quản lý class loader theo ứng dụng, plugin hoặc module.
- Nếu lớp đã được nạp bởi một class loader, thay đổi thứ tự classpath sau đó không làm JVM tự thay thế lớp đã nạp.
- Wildcard classpath như `lib/*` không bảo đảm thứ tự các JAR được mở rộng theo một thứ tự cố định.

Do đó, muốn kết luận lớp đến từ đâu, cần quan sát class loader và nguồn thực tế của lớp, không chỉ đọc chuỗi `-cp`.

## 4. Hai lớp cùng tên có thực sự là một lớp không?

Trong JVM, danh tính của một lớp được xác định bởi **tên nhị phân (binary name) và defining class loader**. Có thể diễn đạt:

```text
Class identity = (binary name, defining class loader)
```

Ví dụ:

```text
com.example.Plugin được định nghĩa bởi Loader A
com.example.Plugin được định nghĩa bởi Loader B
```

Hai lớp này có cùng binary name nhưng khác defining class loader, vì vậy JVM xem chúng là hai kiểu khác nhau.

Ngược lại, nếu hai JAR cùng chứa `com.example.Plugin` nhưng cả hai được tìm qua cùng một class loader, class loader thường chỉ định nghĩa lớp một lần cho binary name đó. Nguồn được tìm thấy đầu tiên thường quyết định bytecode được dùng.

Điều này giải thích hai loại tình huống:

1. **Trùng lớp trong cùng class loader:** một bản định nghĩa che khuất bản còn lại theo thứ tự tìm kiếm.
2. **Cùng tên lớp trong các class loader khác nhau:** cả hai có thể được nạp, nhưng đối tượng và kiểu của chúng không tương thích trực tiếp chỉ vì tên giống nhau.

## 5. Class loader delegation

JVM dùng class loader để nạp định nghĩa lớp. Mô hình phổ biến là parent delegation: khi một loader cần lớp, nó yêu cầu parent loader thử nạp trước; nếu parent không tìm được, loader hiện tại mới tìm theo nguồn của nó.

Sơ đồ khái quát:

```text
Application Class Loader
          |
          | yêu cầu lớp
          v
Platform Class Loader
          |
          | yêu cầu lớp
          v
Bootstrap Class Loader
          |
          v
Các lớp nền tảng được nạp
```

Trong thực tế, luồng gọi bắt đầu từ application loader và delegation đi lên parent chain; nếu parent không tìm được, việc tìm kiếm quay lại loader con để nó tự tìm. Sơ đồ trên mô tả quan hệ parent, không phải thứ tự chạy từ trên xuống.

Các loader thường gặp trong JVM hiện đại:

- **Bootstrap class loader:** nạp các lớp cốt lõi của nền tảng Java. Nó được triển khai ở mức runtime và có thể được biểu diễn là `null` khi gọi `Class.getClassLoader()` đối với lớp do bootstrap loader định nghĩa.
- **Platform class loader:** nạp các module/lớp nền tảng thuộc JDK.
- **Application class loader:** nạp lớp ứng dụng từ classpath thông thường.
- **Custom class loader:** do ứng dụng hoặc framework tạo để nạp lớp từ nguồn riêng, chẳng hạn plugin, network, encrypted archive hoặc thư mục module.

Parent delegation giúp các lớp nền tảng được ưu tiên và tránh việc ứng dụng vô tình thay thế lớp cốt lõi bằng một định nghĩa cùng tên.

### 5.1. Parent-first và child-first

**Parent-first** là chính sách yêu cầu parent thử nạp lớp trước. Đây là mô hình phổ biến của class loader tiêu chuẩn.

**Child-first** là chính sách loader con ưu tiên tìm lớp trong nguồn của nó trước, sau đó mới hỏi parent nếu không tìm được. Một số plugin framework hoặc application server dùng child-first cho một số package để cô lập phiên bản thư viện.

Child-first có thể giúp hai ứng dụng dùng hai version thư viện khác nhau trong cùng tiến trình, nhưng cũng làm tăng độ phức tạp. Nếu class loader con tự định nghĩa một kiểu mà API cha mong đợi, lỗi tương thích kiểu có thể xảy ra.

Các framework thường áp dụng quy tắc ngoại lệ cho package nền tảng như `java.*`, hoặc các API phải dùng chung giữa container và ứng dụng. Không nên tự viết child-first loader nếu chưa hiểu đầy đủ ranh giới API và lifecycle của class loader.

### 5.2. Class loader và phạm vi nhìn thấy lớp

Một class loader có thể tìm lớp trong phạm vi nguồn của nó và delegation chain. Loader con thường có thể nhìn thấy lớp do parent định nghĩa, nhưng parent không tự nhìn thấy lớp chỉ được định nghĩa bởi loader con.

Ví dụ:

```text
Parent loader
  └── framework-api.jar

Plugin loader A
  ├── plugin-a.jar
  └── plugin-a-library.jar

Plugin loader B
  ├── plugin-b.jar
  └── plugin-b-library.jar
```

Hai plugin có thể dùng hai version của một thư viện nếu loader được thiết kế để cô lập chúng. Tuy nhiên, các kiểu trao đổi qua ranh giới plugin nên đến từ một API chung được loader cha định nghĩa. Nếu plugin A và plugin B cùng truyền một đối tượng có kiểu riêng được định nghĩa độc lập, JVM có thể từ chối ép kiểu dù tên lớp trông giống nhau.

## 6. Lớp đã nạp không tự đổi khi classpath thay đổi

Trong cùng một class loader, một binary name được định nghĩa một lần. Sau khi lớp đã được nạp, việc thay thế JAR trên đĩa hoặc thay đổi chuỗi classpath không khiến loader tự động nạp lại một định nghĩa khác cho cùng tên lớp.

Ví dụ, ứng dụng đã nạp `com.example.Service` từ `service-v1.jar`. Sau đó, một tiến trình khác thay file JAR trên đĩa bằng phiên bản mới. Lớp đang tồn tại trong JVM vẫn là định nghĩa đã nạp trước đó. Để dùng định nghĩa mới, thường cần khởi động JVM mới hoặc dùng cơ chế class loader mới/hot reload được thiết kế rõ ràng.

Đây là lý do việc cập nhật file JAR trong thư mục ứng dụng đang chạy không đồng nghĩa code mới đã có hiệu lực.

## 7. Hậu quả khi nạp nhầm phiên bản lớp

Hai JAR có thể chứa cùng tên lớp nhưng API khác nhau.

Giả sử phiên bản 1:

```java
package com.example.api;

public class Formatter {
    public String format(String value) {
        return value;
    }
}
```

Phiên bản 2 bổ sung method:

```java
package com.example.api;

public class Formatter {
    public String format(String value) {
        return value.trim();
    }

    public String format(String value, boolean uppercase) {
        return uppercase ? value.toUpperCase() : value;
    }
}
```

Ứng dụng được biên dịch với phiên bản 2 và gọi:

```java
formatter.format("hello", true);
```

Nhưng lúc chạy, classpath lại đặt JAR phiên bản 1 trước. Compiler đã tạo bytecode chứa lời gọi method hai tham số, trong khi class được nạp không có method đó. Khi lời gọi được liên kết/thực hiện, JVM có thể ném:

```text
java.lang.NoSuchMethodError
```

Các lỗi liên quan thường gặp:

| Lỗi | Nguyên nhân có thể liên quan đến phiên bản lớp |
|---|---|
| `NoSuchMethodError` | Bytecode gọi method không có trong class được nạp |
| `NoSuchFieldError` | Bytecode truy cập field không có trong class được nạp |
| `AbstractMethodError` | Implementation được nạp không cung cấp implementation phù hợp cho method cần gọi |
| `IncompatibleClassChangeError` | Thay đổi không tương thích giữa class được compile và class được nạp |
| `ClassCastException` | Đối tượng không thuộc kiểu đích; có thể do cùng tên lớp được định nghĩa bởi loader khác nhau |
| `LinkageError` | Nhóm lỗi liên kết lớp/method/field không tương thích |

Không phải mọi lỗi trên đều do thứ tự classpath. Nhưng khi lỗi xuất hiện sau khi thay JAR hoặc khác nhau giữa local và CI, cần kiểm tra phiên bản class thực tế đã được nạp.

## 8. Trùng resource cũng chịu ảnh hưởng của classpath

Classpath không chỉ chứa class file mà còn có resource như:

- `application.properties`.
- `META-INF/services/...`.
- File cấu hình logging.
- Template, schema và dữ liệu đóng gói trong JAR.

Hai JAR có thể chứa resource cùng đường dẫn, ví dụ:

```text
config/default.properties
```

Khi gọi `ClassLoader.getResource(...)`, class loader thường trả về một resource phù hợp đầu tiên theo quy tắc delegation và tìm kiếm của loader. Vì vậy, thứ tự classpath có thể làm ứng dụng đọc nhầm file cấu hình hoặc template.

Nếu muốn liệt kê nhiều resource cùng tên, dùng `getResources(...)`:

```java
import java.net.URL;
import java.util.Enumeration;

ClassLoader loader = Thread.currentThread().getContextClassLoader();
Enumeration<URL> resources = loader.getResources("config/default.properties");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

Đoạn code giúp quan sát các URL resource được tìm thấy. Thứ tự enumeration phụ thuộc class loader và nguồn tài nguyên; không nên dựa vào thứ tự đó nếu ứng dụng cần hợp nhất cấu hình theo quy tắc riêng.

### 8.1. `ServiceLoader` và nhiều file service descriptor

Java SPI thường dùng file dưới `META-INF/services/` để đăng ký implementation. Nhiều JAR có thể cùng cung cấp descriptor cho một interface. `ServiceLoader` được thiết kế để tìm các provider theo các descriptor nhìn thấy qua class loader, nên trường hợp này có thể cần đọc nhiều resource thay vì chỉ lấy file đầu tiên.

Ví dụ:

```java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    System.out.println(provider.name());
}
```

Nếu đóng gói các JAR thành một fat JAR, cần bảo đảm quá trình merge resource không ghi đè mất các file `META-INF/services` của thư viện khác. Một số plugin cung cấp chiến lược merge service descriptor.

## 9. Wildcard classpath và thứ tự không xác định

Java launcher hỗ trợ wildcard cho các JAR trong một thư mục:

```bash
java -cp "lib/*:build/classes/java/main" com.example.Application
```

Trên Windows, dùng dấu `;` để phân tách:

```powershell
java -cp "lib\*;build\classes\java\main" com.example.Application
```

Wildcard `lib/*` cho phép launcher đưa các JAR phù hợp trong thư mục vào classpath. Tuy nhiên, thứ tự các JAR được mở rộng không được bảo đảm theo một thứ tự cố định.

Vì vậy, nếu hai JAR trong `lib/` chứa cùng lớp, không nên dựa vào wildcard để quyết định JAR nào được ưu tiên. Hãy loại bỏ xung đột hoặc xây dựng classpath có thứ tự tường minh.

## 10. Manifest `Class-Path` trong JAR

Manifest của một JAR có thể khai báo thuộc tính `Class-Path` để tham chiếu thêm các JAR hoặc thư mục liên quan. Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Application
Class-Path: lib/commons.jar lib/reporting.jar
```

Khi launcher sử dụng JAR theo cách hỗ trợ manifest class path, các URL được khai báo có thể được thêm vào phạm vi tìm kiếm. Đường dẫn tương đối được diễn giải tương đối với vị trí JAR chứa manifest.

Manifest class path có quy tắc riêng về URL và phân tách bằng khoảng trắng; không dùng dấu `:` hoặc `;` như chuỗi classpath của command line. Khi điều tra một ứng dụng chạy bằng `java -jar`, cần kiểm tra cả `Main-Class` và `Class-Path` trong manifest.

Có thể xem manifest bằng:

```bash
jar --list --file application.jar
jar --describe-module --file application.jar
```

Lệnh thứ hai liên quan đến thông tin module và có thể không cần cho mọi JAR. Để đọc manifest, có thể giải nén hoặc dùng công cụ JDK phù hợp; kiểm tra nội dung `META-INF/MANIFEST.MF` trong archive.

## 11. Compile classpath và runtime classpath

Một dự án có thể biên dịch thành công nhưng chạy với classpath khác. Khi đó, compiler đã nhìn thấy một version API, còn JVM lại nạp version khác.

Ví dụ:

```text
Compile classpath:
  api-v2.jar
  support.jar

Runtime classpath:
  api-v1.jar
  support.jar
```

Nếu source code gọi method chỉ có trong `api-v2.jar`, compile sẽ thành công. Nhưng runtime nạp `api-v1.jar`, dẫn đến `NoSuchMethodError` khi method đó được gọi.

Trong Gradle, compile và runtime classpath được biểu diễn bằng các configuration riêng như `compileClasspath` và `runtimeClasspath`. Có thể xem chúng bằng:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Để xem lý do version được chọn:

```bash
./gradlew dependencyInsight \
  --dependency api-library \
  --configuration runtimeClasspath
```

Trong Maven, dùng dependency tree và các plugin goal phù hợp để xem dependency graph. Cần kiểm tra cả scope và cách plugin đóng gói runtime dependency.

## 12. Classpath trong Gradle và Maven

Trong dự án build tool, classpath thường được tạo tự động từ source set và dependency configuration.

### 12.1. Gradle

Với Java plugin, các configuration phổ biến:

| Configuration | Vai trò |
|---|---|
| `compileClasspath` | Classpath dùng để biên dịch source set chính |
| `runtimeClasspath` | Classpath dùng khi chạy ứng dụng/test tùy source set |
| `testCompileClasspath` | Classpath biên dịch test |
| `testRuntimeClasspath` | Classpath chạy test |

Dependency được khai báo trong `implementation`, `api`, `compileOnly` hoặc `runtimeOnly` sẽ tham gia các classpath theo quy tắc của plugin và variant. Nếu hai dependency cung cấp cùng binary name, cần xem dependency graph và artifact nội dung thực tế.

Gradle có thể giải quyết version conflict trong cùng một module coordinate, nhưng nó không tự hiểu rằng hai artifact khác tọa độ chứa cùng một class. Ví dụ `com.vendor:legacy-utils` và `org.other:compat-utils` có thể cùng đóng gói `com.example.util.StringHelper`. Cả hai module đều có thể được giữ trong graph vì tọa độ khác nhau, dẫn đến duplicate class.

### 12.2. Maven

Maven dependency mediation giải quyết xung đột version theo tọa độ dependency, chẳng hạn hai đường dependency yêu cầu các version khác nhau của cùng `groupId:artifactId`. Nhưng nếu hai artifact khác tọa độ cùng chứa một binary class name, Maven không nhất thiết phát hiện hoặc loại bỏ duplicate class đó.

Vì vậy, `mvn dependency:tree` là bước đầu để hiểu graph, nhưng không đủ để phát hiện mọi lớp trùng. Có thể cần kiểm tra nội dung JAR hoặc dùng plugin kiểm tra duplicate classes.

## 13. Quan sát lớp được nạp từ đâu

Khi nghi ngờ JVM đang nạp sai JAR, hãy kiểm tra nguồn của lớp trong runtime.

### 13.1. In nguồn định nghĩa từ Java code

```java
public final class ClassOrigin {
    public static void print(Class<?> type) {
        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());

        var protectionDomain = type.getProtectionDomain();
        var codeSource = protectionDomain == null
            ? null
            : protectionDomain.getCodeSource();

        System.out.println(
            "Location: " +
            (codeSource == null ? "unknown/bootstrap" : codeSource.getLocation())
        );
    }
}
```

`Class.getClassLoader()` cho biết defining loader; với lớp do bootstrap loader định nghĩa, giá trị có thể là `null`. `ProtectionDomain.getCodeSource()` có thể không có giá trị hoặc không cung cấp vị trí trong một số môi trường, nên code cần xử lý trường hợp `null`.

Có thể gọi:

```java
ClassOrigin.print(com.example.util.StringHelper.class);
```

Kết quả giúp xác định lớp đến từ thư mục hoặc JAR nào khi runtime cung cấp CodeSource.

### 13.2. Bật log nạp lớp

Với Java 9 trở lên:

```bash
java -Xlog:class+load=info -cp "app.jar:lib/*" com.example.Application
```

Log có thể hiển thị lớp được nạp và nguồn tương ứng. Cú pháp classpath trong ví dụ dùng dấu `:` cho Linux/macOS; trên Windows dùng `;`.

Với Java 8:

```bash
java -verbose:class -cp "app.jar;lib/*" com.example.Application
```

Tùy chọn log có thể tạo output lớn. Khi điều tra, có thể lọc log theo package hoặc tên lớp bằng công cụ shell tương ứng.

### 13.3. Kiểm tra nội dung JAR

Liệt kê nội dung một JAR:

```bash
jar tf lib-a.jar
```

Tìm class cụ thể:

```bash
jar tf lib-a.jar | grep 'com/example/util/StringHelper.class'
```

Trên PowerShell:

```powershell
jar tf .\lib-a.jar | Select-String 'com/example/util/StringHelper.class'
```

Lặp lại với các JAR nghi ngờ. Nếu cùng một entry xuất hiện trong nhiều artifact, cần xác định vì sao cả hai dependency cùng có mặt.

### 13.4. Kiểm tra bằng `javap`

Có thể xem chữ ký method của lớp trong một classpath cụ thể:

```bash
javap -classpath lib-a.jar -p com.example.util.StringHelper
javap -classpath lib-b.jar -p com.example.util.StringHelper
```

So sánh output để nhận ra API khác nhau. `javap` chỉ kiểm tra định nghĩa được tìm thấy theo classpath truyền vào lệnh; nó không tự chứng minh ứng dụng runtime đã nạp đúng định nghĩa đó.

## 14. Duplicate class và cách xử lý

Khi hai artifact khác nhau chứa cùng binary name, nên giải quyết ở nguồn dependency thay vì dựa vào thứ tự classpath.

Các hướng xử lý thường gặp:

1. **Loại dependency dư thừa:** nếu một JAR cũ được kéo vào qua module khác nhưng không còn cần thiết, loại nó khỏi graph.
2. **Dùng một version thống nhất:** nếu hai đường dependency yêu cầu các version khác nhau của cùng module, dùng constraint, dependency management hoặc resolution rule phù hợp.
3. **Thay thư viện trùng lớp:** chọn một artifact chính thức thay vì hai bản fork chứa cùng package/class.
4. **Relocate/shade package:** nếu cần đóng gói hai thư viện cùng tên lớp, có thể đổi package của một thư viện bằng shading/relocation để binary name không còn trùng.
5. **Tách class loader:** trong kiến trúc plugin/container, cô lập dependency theo loader nếu thực sự cần nhiều version cùng tiến trình.
6. **Sửa publication:** nếu thư viện publish nhầm class đã có trong dependency khác, sửa artifact đầu ra hoặc dependency metadata.

### 14.1. Exclude dependency bắc cầu

Với Gradle, có thể exclude module được kéo vào qua một dependency:

```groovy
dependencies {
    implementation('com.example:reporting-library:2.0.0') {
        exclude group: 'org.legacy', module: 'legacy-utils'
    }
}
```

Với Maven:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>reporting-library</artifactId>
  <version>2.0.0</version>
  <exclusions>
    <exclusion>
      <groupId>org.legacy</groupId>
      <artifactId>legacy-utils</artifactId>
    </exclusion>
  </exclusions>
</dependency>
```

Exclude chỉ phù hợp khi dependency bị loại không còn cần thiết hoặc đã được thay bằng một dependency tương thích khác. Nếu thư viện cần class đó ở runtime, loại bỏ nó có thể dẫn tới `ClassNotFoundException` hoặc `NoClassDefFoundError`.

### 14.2. Dependency version conflict khác duplicate class

Hai tình huống cần phân biệt:

| Tình huống | Ví dụ | Cách giải quyết thường dùng |
|---|---|---|
| Cùng tọa độ, khác version | `com.example:util:1.0` và `com.example:util:2.0` | Version conflict resolution, constraints, dependency management |
| Khác tọa độ, cùng binary class | `com.vendor:util-a` và `org.fork:util-b` đều chứa `com.example.Util` | Exclude, thay artifact, relocate hoặc tách class loader |

Build tool thường giải quyết trường hợp thứ nhất dựa trên metadata dependency. Trường hợp thứ hai cần phân tích nội dung artifact vì dependency coordinates không cho biết chúng chứa class trùng nhau.

## 15. Package sealing và các vấn đề liên quan

JAR manifest có thể khai báo package sealing, yêu cầu các class thuộc một package được nạp từ cùng một code source trong phạm vi class loader theo quy tắc sealing. Nếu cùng package bị nạp từ nhiều JAR không phù hợp với sealing policy, JVM có thể ném `SecurityException` khi định nghĩa lớp.

Đây là một cơ chế khác với việc hai JAR chứa cùng một class. Ngay cả khi các class có tên khác nhau nhưng cùng package, sealing vẫn có thể khiến việc kết hợp nhiều nguồn thất bại.

Khi gặp lỗi liên quan đến sealed package, kiểm tra `Sealed: true` hoặc thuộc tính package-specific trong `META-INF/MANIFEST.MF` của JAR. Không nên khắc phục bằng cách tùy tiện đảo classpath; cần xác định package nào được seal và artifact nào phải cùng một code source.

## 16. Classpath và JPMS module path

Từ Java 9, Java Platform Module System (JPMS) bổ sung module path. Classpath và module path có vai trò khác nhau.

| Classpath | Module path |
|---|---|
| Các lớp thường thuộc unnamed module của class loader tương ứng | Các module được nhận diện bằng module descriptor hoặc automatic module name |
| Không có module descriptor bắt buộc | Module có tên và metadata module |
| Không áp dụng module readability/exports như module có tên | Có quy tắc `requires`, `exports`, `opens` và module resolution |
| Duplicate class có thể bị che khuất theo class loader/search order | Module resolution có quy tắc module name, readability, package và version metadata; không phải cơ chế chọn JAR theo classpath order |

### 16.1. Classpath trong ứng dụng dùng JPMS

Các lớp đặt trên classpath thuộc unnamed module của class loader tương ứng. Chúng không có `module-info.class` để khai báo module name và exports. Khi ứng dụng kết hợp classpath với module path, cần hiểu ranh giới giữa unnamed module và named modules.

### 16.2. Module path và module resolution

Trên module path, JVM/launcher tìm các module có tên và giải quyết module graph dựa trên descriptor, yêu cầu `requires`, exports và các quy tắc JPMS. Hai module không thể tùy tiện chứa cùng package theo cách làm split package trong một layer/module configuration thông thường; module system có các kiểm tra để phát hiện cấu hình không hợp lệ.

Một JAR không có `module-info.class` có thể được xử lý như automatic module khi đặt trên module path, thường dùng tên từ `Automatic-Module-Name` trong manifest hoặc tên suy ra từ tên JAR theo quy tắc module naming. Automatic module có hành vi tương thích khác named module tường minh và thường đọc rộng hơn các module khác.

### 16.3. Không dùng thứ tự classpath để sửa lỗi module path

Nếu lỗi liên quan tới module resolution, `requires`, `exports`, split package hoặc module name, đổi thứ tự JAR trên classpath thường không giải quyết đúng vấn đề. Cần kiểm tra module path, module descriptor và lệnh khởi chạy.

Có thể xem module của JAR bằng:

```bash
jar --describe-module --file library.jar
```

Nếu JAR không phải explicit module, công cụ có thể hiển thị thông tin automatic module hoặc thông báo phù hợp tùy phiên bản JDK và nội dung archive.

## 17. Thứ tự classpath trong các môi trường phổ biến

### 17.1. Command line

Với danh sách tường minh:

```bash
java -cp "classes:lib-a.jar:lib-b.jar" com.example.Application
```

thứ tự các phần tử được thể hiện rõ trong chuỗi classpath. Khi điều tra xung đột, có thể đổi vị trí hai JAR để xác nhận giả thuyết về lớp được tìm thấy trước, nhưng đó chỉ là thử nghiệm chẩn đoán, không phải giải pháp kiến trúc lâu dài.

### 17.2. Gradle

Gradle xây dựng runtime classpath từ dependency graph và artifact đã phân giải. Không nên tự thêm JAR thủ công vào `-cp` để che một dependency conflict mà build script chưa mô hình hóa. Hãy kiểm tra `runtimeClasspath`, dependencyInsight và artifact thực tế.

### 17.3. Maven

Maven xây dựng classpath thông qua dependency resolution và plugin. Thứ tự dependency trong classpath có thể chịu ảnh hưởng từ dependency graph và cách plugin tạo classpath. Không nên giả định việc đổi thứ tự trong `<dependencies>` là cách ổn định để chọn class trùng.

### 17.4. Application server và plugin framework

Application server có thể có class loader riêng cho server, application, module hoặc plugin. Quy tắc parent-first/child-first có thể được cấu hình. Khi triển khai lên server, cần đọc chính sách class loading của server cụ thể; classpath của lệnh `java` đơn giản không mô tả đầy đủ môi trường đó.

## 18. Quy trình chẩn đoán lớp trùng tên

Khi nghi ngờ lớp được nạp từ JAR sai, hãy lần theo các bước:

1. **Xác định binary name:** ghi lại tên đầy đủ của lớp trong stack trace hoặc code.
2. **Liệt kê dependency graph:** dùng Gradle `dependencies`/`dependencyInsight` hoặc Maven `dependency:tree`.
3. **Tìm class entry trùng:** chạy `jar tf` trên các JAR nghi ngờ và tìm đường dẫn `.class` tương ứng.
4. **So sánh API:** dùng `javap` trên từng artifact để xem method/field khác nhau.
5. **Quan sát runtime origin:** in `Class.getClassLoader()` và `ProtectionDomain.getCodeSource()` hoặc bật log class loading.
6. **Kiểm tra compile/runtime classpath:** xác nhận compiler và JVM đang dùng cùng phiên bản tương thích.
7. **Kiểm tra loader delegation:** nếu dùng framework/container, tìm hiểu parent-first hay child-first và loader nào định nghĩa lớp.
8. **Kiểm tra resource trùng:** nếu lỗi liên quan cấu hình hoặc SPI, liệt kê `getResources(...)` và kiểm tra merge trong archive.
9. **Sửa dependency graph hoặc đóng gói:** loại dependency dư, thống nhất version, relocate package hoặc tách class loader khi phù hợp.
10. **Kiểm thử trên môi trường thực:** xác nhận CI, container và production nạp đúng artifact sau khi sửa.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `NoSuchMethodError` sau khi deploy | Runtime nạp JAR cũ hơn lúc compile | Kiểm tra class origin, runtime classpath và version artifact |
| Local chạy được nhưng CI lỗi | Thứ tự classpath hoặc dependency graph khác nhau | So sánh runtime classpath và log class loading |
| Hai JAR có cùng class entry | Dependency khác tọa độ đóng gói trùng package/class | Tìm đường dependency và loại/relocate một bản |
| `ClassCastException` dù hai lớp in ra cùng tên | Hai defining class loader khác nhau | In `getClassLoader()` và kiểm tra ranh giới loader |
| `ClassNotFoundException` | Không có lớp trong phạm vi loader đang tìm hoặc loader không nhìn thấy nguồn | Kiểm tra classpath, loader và nguồn class |
| `NoClassDefFoundError` | Lớp cần thiết không có hoặc lỗi nạp/khởi tạo trước đó | Đọc nguyên nhân gốc trong stack trace và kiểm tra runtime dependency |
| Đọc nhầm file cấu hình trong JAR | Resource cùng đường dẫn xuất hiện nhiều lần | Dùng `getResources()` và kiểm tra classpath order |
| SPI provider bị mất sau khi đóng gói fat JAR | `META-INF/services` bị ghi đè thay vì merge | Cấu hình merge service descriptors trong packaging plugin |
| `SecurityException: sealing violation` | Package bị seal nhưng class cùng package đến từ code source khác | Kiểm tra manifest và package sealing |
| Module resolution báo split package | Hai named modules chứa package xung đột trong module layer | Kiểm tra module path và module descriptors |

## 20. Nguyên tắc phòng tránh

- Tránh đưa nhiều artifact chứa cùng binary class name vào runtime classpath.
- Dùng dependency coordinates và version rõ ràng; không dựa vào thứ tự JAR để chọn phiên bản.
- Giữ compile classpath và runtime classpath tương thích.
- Không dựa vào thứ tự mở rộng của wildcard `lib/*`.
- Kiểm tra class origin khi lỗi chỉ xuất hiện ở một môi trường.
- Dùng dependency constraints, locking và repository metadata để kiểm soát version.
- Exclude dependency chỉ khi đã xác nhận không làm mất class cần thiết.
- Dùng shading/relocation khi thực sự cần đóng gói hai thư viện có package trùng.
- Thiết kế plugin class loader với API chung rõ ràng nếu cần cô lập version.
- Khi dùng JPMS, xử lý lỗi module resolution theo module path và descriptor, không theo mẹo sắp xếp classpath.
- Kiểm tra resource và SPI descriptor trùng khi đóng gói fat JAR.

## 21. Kết luận

Thứ tự classpath có thể quyết định nguồn định nghĩa lớp được tìm thấy trước khi cùng một class loader nạp một binary name. Tuy nhiên, kết quả thực tế còn phụ thuộc parent delegation, class loader tùy chỉnh, lớp đã được nạp trước đó và cách launcher/build tool tạo classpath.

Hai JAR chứa cùng một class không tự tạo ra hai kiểu độc lập trong cùng class loader. Nếu hai class loader khác nhau cùng định nghĩa một binary name, JVM xem chúng là hai kiểu khác nhau vì defining loader là một phần của class identity. Trùng resource cũng có thể khiến ứng dụng đọc nhầm cấu hình hoặc mất service provider khi đóng gói.

Khi gặp lỗi liên quan phiên bản lớp, hãy kiểm tra dependency graph, nội dung JAR, compile/runtime classpath và nguồn lớp thực tế trong JVM. Sửa dependency graph hoặc ranh giới class loader sẽ tạo ra kết quả ổn định hơn việc chỉ đảo thứ tự JAR. Với JPMS, hãy phân biệt classpath và module path vì module resolution có quy tắc riêng.
