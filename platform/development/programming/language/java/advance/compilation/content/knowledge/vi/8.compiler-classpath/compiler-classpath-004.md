# Thứ tự tìm kiếm và xung đột khi nhiều thư viện chứa cùng kiểu trong Java classpath

Trong một dự án Java, một tên kiểu như `org.example.api.Message` có thể xuất hiện ở nhiều thư viện JAR khác nhau. Nếu hai JAR cùng chứa `org/example/api/Message.class`, trình biên dịch hoặc JVM phải tìm một định nghĩa phù hợp theo các đường tìm kiếm đang được cấu hình. Khi hai bản class có cùng tên nhưng khác bytecode hoặc API, chương trình có thể **chạy với hành vi không mong muốn**, hoặc phát sinh lỗi liên kết như `NoSuchMethodError`. Hiểu thứ tự tìm kiếm giúp giải thích tại sao một ứng dụng biên dịch thành công nhưng lỗi khi triển khai hoặc thay đổi hành vi khi đảo thứ tự JAR.

Bài này tập trung vào **classpath**, nơi `javac` tìm bytecode phụ thuộc và nơi application class loader chuẩn tìm class khi chạy. Đồng thời cần phân biệt nó với source path, module path và cơ chế nạp lớp tùy biến.

## 1. Classpath entry và tên kiểu

Classpath là một danh sách **entry có thứ tự**. Một entry có thể là thư mục gốc chứa các file `.class` hoặc file JAR chứa những file này. Ví dụ:

~~~text
project/
├── classes/
│   └── org/example/app/Main.class
├── libs/
│   ├── alpha.jar
│   │   └── org/example/api/Message.class    (nội dung JAR)
│   └── beta.jar
│       └── org/example/api/Message.class    (nội dung JAR)
└── src/
    └── org/example/app/Main.java
~~~

Tên nhị phân `org.example.api.Message` ứng với đường dẫn `org/example/api/Message.class` bên dưới **gốc classpath entry** hoặc gốc của JAR. Vì vậy:

- Nếu `classes` chứa `classes/org/example/app/Main.class`, classpath root là `classes`.
- Nếu JAR chứa `org/example/api/Message.class` bên trong, classpath entry là **đường dẫn tới JAR**, không phải đường dẫn package trong JAR.
- Câu lệnh `import org.example.api.Message;` trong source chỉ cho phép dùng tên `Message` ngắn gọn. Nó **không** thêm JAR vào classpath.

Classpath không phải tên package: dấu `.` nối phần package, dấu `/` hoặc `\` nối thư mục, còn dấu nối **các entry** classpath phụ thuộc hệ điều hành.

| Nền tảng | Phân cách nhiều entry classpath | Lệnh minh họa |
| --- | --- | --- |
| Linux/macOS | Dấu hai chấm `:` | `java -cp "classes:libs/alpha.jar:libs/beta.jar" org.example.app.Main` |
| Windows | Dấu chấm phẩy `;` | `java -cp "classes;libs\alpha.jar;libs\beta.jar" org.example.app.Main` |

Đặt dấu nháy quanh toàn bộ giá trị `-cp`, nhất là khi tên thư mục có khoảng trắng hoặc khi chạy PowerShell, nơi `;` có ý nghĩa phân cách lệnh nếu nằm ngoài chuỗi.

## 2. Quy tắc “entry trước được thử trước” và giới hạn của nó

Trong cách chạy `java -cp ...` thông thường, **khi application class loader chuẩn tìm trong các entry classpath của chính nó**, danh sách được xét theo thứ tự. Giả sử hai thư viện cùng có class `org.example.api.Message`, nhưng entry trước không có bản sao nào khác của class đó:

~~~bash
java -cp "classes:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Trong tình huống chuẩn, `alpha.jar` sẽ cung cấp class được tra trước `beta.jar`. Đảo hai JAR có thể đổi class thực tế được nạp:

~~~bash
java -cp "classes:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

Tuy vậy **không** xem thứ tự classpath là một quy tắc bao trùm mọi class loading:

1. Class loader thông thường **ủy quyền cho parent trước**. Nếu parent đã cung cấp class, application classpath phía dưới không tự thay thế class đó.
2. Một class đã được định nghĩa trong một loader sẽ không tự đổi thành bytecode của JAR khác chỉ vì có một JAR mới xuất hiện.
3. Framework/container hoặc hệ plugin có thể dùng **custom loader** theo chiến lược child-first, cô lập loader hoặc nạp class theo cách khác. Khi đó `-cp` không đủ để dự đoán nguồn của class.
4. Java Platform Module System (JPMS) dùng **module path** và cơ chế phân giải module khác với classpath thông thường.
5. Quy tắc tìm nguồn hoặc class của `javac` có khác biệt riêng khi compile trực tiếp file `.java`; không nên đồng nhất mọi xử lý source file với việc JVM chọn file `.class` lúc runtime.

Trong bài thực hành, ta chủ động dùng `java -cp` và application class loader chuẩn để kiểm chứng thứ tự classpath.

## 3. Thực hành Java 17+: hai JAR cùng binary name

Tạo ba file dưới thư mục dự án `classpath-order-lab`:

~~~text
classpath-order-lab/
└── src/
    ├── alpha/org/example/api/Message.java
    ├── beta/org/example/api/Message.java
    └── app/org/example/app/Main.java
~~~

**Tệp `src/alpha/org/example/api/Message.java`:**

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "alpha";
    }
}
~~~

**Tệp `src/beta/org/example/api/Message.java`:**

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "beta";
    }
}
~~~

**Tệp `src/app/org/example/app/Main.java`:**

~~~java
package org.example.app;

import org.example.api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Hai file `Message.java` khai báo **cùng package, cùng tên class, cùng chữ ký method `text(): String`**, nhưng phần thân khác. Không biên dịch hai bản Message cùng một output root: mỗi bản sẽ nằm trong thư viện riêng.

### Biên dịch và chạy trên Linux/macOS

Từ thư mục `classpath-order-lab`:

~~~bash
mkdir -p out/alpha out/beta out/app libs
javac -encoding UTF-8 -d out/alpha src/alpha/org/example/api/Message.java
javac -encoding UTF-8 -d out/beta src/beta/org/example/api/Message.java
jar --create --file libs/alpha.jar -C out/alpha .
jar --create --file libs/beta.jar -C out/beta .
javac -encoding UTF-8 -cp libs/alpha.jar -d out/app src/app/org/example/app/Main.java
~~~

Lúc biên dịch `Main`, compiler sử dụng `Message` từ `alpha.jar`. Chạy:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Stdout chính xác:

~~~text
alpha
~~~

Đảo thứ tự hai JAR:

~~~bash
java -cp "out/app:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

Stdout chính xác:

~~~text
beta
~~~

Không cần biên dịch lại `Main`, vì hai bản `Message.text()` có cùng chữ ký nhị phân. Class được tải từ beta vẫn đáp ứng lời gọi, nhưng trả giá trị khác.

### Các lệnh tương ứng trên Windows PowerShell

Đứng ở thư mục `classpath-order-lab`:

~~~powershell
New-Item -ItemType Directory -Force "out\alpha", "out\beta", "out\app", "libs" | Out-Null
javac -encoding UTF-8 -d "out\alpha" "src\alpha\org\example\api\Message.java"
javac -encoding UTF-8 -d "out\beta" "src\beta\org\example\api\Message.java"
jar --create --file "libs\alpha.jar" -C "out\alpha" .
jar --create --file "libs\beta.jar" -C "out\beta" .
javac -encoding UTF-8 -cp "libs\alpha.jar" -d "out\app" "src\app\org\example\app\Main.java"
java -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
java -cp "out\app;libs\beta.jar;libs\alpha.jar" org.example.app.Main
~~~

Hai lệnh `java` lần lượt in:

~~~text
alpha
beta
~~~

Dấu `;` là ký hiệu nối entry classpath Windows, thay vì `:` trên Linux. Các lệnh chạy từ root dự án; nếu đứng ở thư mục khác, đường dẫn tương đối không còn đúng. Nếu có khoảng trắng trong đường dẫn, cần quote đầy đủ giá trị, ví dụ `-cp "out classes;third party\alpha.jar"`.

### Vì sao đoạn code không import được “cả alpha và beta”?

Cả hai thư viện đưa ra **một tên kiểu Java y hệt**: `org.example.api.Message`. Import chỉ xác định tên kiểu này, không có cú pháp `import ... as AlphaMessage` để chọn class theo JAR. Khi cùng một class loader phải định nghĩa binary name đó, ứng dụng không thể dùng hai class khác bytecode với **cùng danh tính kiểu/loader** chỉ bằng hai dòng import.

Giải pháp tùy nhu cầu: thống nhất phiên bản, loại bản trùng, relocation sang package khác, hoặc thiết kế hai class loader độc lập khi thực sự cần cô lập nhiều phiên bản.

## 4. Compile classpath khác runtime classpath

`javac` và `java` được gọi độc lập nên có thể nhìn thấy các thư viện khác nhau.

| Giai đoạn | Classpath | Kết quả |
| --- | --- | --- |
| Compile | `libs/alpha.jar` | `javac` xác minh `Message.text()` theo khai báo trong alpha |
| Runtime A | `out/app:libs/alpha.jar:libs/beta.jar` | Trong loader chuẩn, alpha cung cấp `Message` |
| Runtime B | `out/app:libs/beta.jar:libs/alpha.jar` | Trong loader chuẩn, beta cung cấp `Message` |

Khi biên dịch, bytecode chứa **tham chiếu tượng trưng** đến class và method (ví dụ tên nhị phân của `Message` và descriptor `text:()Ljava/lang/String;`). File `Main.class` không ghi cứng đường dẫn tuyệt đối `libs/alpha.jar`. JVM khi chạy phải tìm một định nghĩa class tương ứng, sau đó phân giải method phù hợp.

Do đó:

- Compile thành công **không bảo đảm** runtime dùng đúng bản thư viện khi compile.
- Tên class và method vẫn giống nhau nhưng implementation khác có thể gây **sai lệch hành vi mà không có exception**.
- API nhị phân khác có thể gây lỗi **runtime linkage**, không chỉ lỗi biên dịch.
- Runtime classpath phải chứa các class phụ thuộc thật sự cần thiết, ngay cả khi compiler trước đó đã thấy chúng.

Một số build tool phân biệt compile dependencies, runtime dependencies, test dependencies. Trong một môi trường triển khai, launcher hoặc container có thể đóng góp thêm thư viện. Hãy kiểm tra **classpath được phân giải ở môi trường thực tế**, không chỉ file build hoặc câu lệnh import.

## 5. Khi bản beta không còn phương thức: lỗi NoSuchMethodError

Giữ `Main.class` đã compile với alpha trong ví dụ mục 3, và thay **chỉ** file `src/beta/org/example/api/Message.java` thành:

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String newApi() {
        return "beta-new";
    }
}
~~~

Sau đó compile lại riêng beta và tạo lại JAR. Linux/macOS:

~~~bash
javac -encoding UTF-8 -d out/beta src/beta/org/example/api/Message.java
jar --create --file libs/beta.jar -C out/beta .
java -cp "out/app:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

`Main.class` yêu cầu `Message.text(): String`, nhưng định nghĩa `Message` được tải từ beta không còn method `text()`. Vì vậy JVM có thể ném:

~~~text
java.lang.NoSuchMethodError: ... Message.text() ...
~~~

Dòng trên chỉ là **kiểu lỗi minh họa**; nội dung stderr, descriptor và stack trace phụ thuộc JDK. Đây không phải stdout cố định của chương trình.

Làm lại với alpha trước:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Stdout là:

~~~text
alpha
~~~

Đặt alpha trước có thể giúp thí nghiệm chạy được, nhưng trong hệ thống thật bạn nên **sửa sự không nhất quán phiên bản**, tránh dùng thứ tự classpath như một giải pháp che giấu dependency conflict.

Nếu compile trực tiếp `Main.java` với beta mới **và không cung cấp alpha**, `javac` sẽ phát hiện `text()` không tồn tại. `NoSuchMethodError` chủ yếu đáng chú ý khi **mã đã biên dịch** được chạy với binary definition khác bản đã dùng ở compile-time.

Các lỗi liên quan:

| Lỗi | Một nguyên nhân tiêu biểu |
| --- | --- |
| `NoSuchMethodError` | Runtime class thiếu method/chữ ký đã tồn tại khi compile |
| `NoSuchFieldError` | Runtime class thiếu field được bytecode tham chiếu |
| `IncompatibleClassChangeError` | Thay đổi không tương thích như static/instance hoặc class/interface |
| `NoClassDefFoundError` | JVM cần class nhưng không tìm được hoặc không hoàn tất định nghĩa/khởi tạo trong tình huống phù hợp |
| `ClassCastException` | Object không tương thích với type được ép; có thể do cùng tên class nhưng khác defining loader |
| Không có lỗi nhưng output thay đổi | Binary API vẫn tương thích nhưng implementation từ JAR khác |

Không suy luận rằng mọi `NoClassDefFoundError` đều do thiếu JAR: một số trường hợp class đã khởi tạo lỗi từ trước, hoặc nguyên nhân nằm ở loading/linking khác. Hãy đọc toàn bộ cause/stack trace.

## 6. Cơ chế class loader và parent delegation

Một mô hình hữu ích cho launcher Java chuẩn:

~~~text
Yêu cầu: org.example.api.Message
              |
              v
Application class loader
              |
              +--> Parent/platform/bootstrap
              |       Nếu đã có class phù hợp, thường trả kết quả
              |
              +--> Nếu parent không đáp ứng
                      tìm entry trong application classpath
                      out/app -> libs/alpha.jar -> libs/beta.jar
~~~

Đây là sơ đồ khái niệm. Parent delegation giúp tránh class ứng dụng dễ dàng thay thế các class nền tảng JDK như `java.lang.String`. Cấu trúc loader, module JDK và cách tìm class có những chi tiết tùy bản Java; không nên dùng hình trên như mô tả mọi internal API của VM.

**Danh tính runtime của một class** gồm binary name và **defining class loader**. Điều này có hai hệ quả:

1. Hai JAR có cùng binary name, cùng loader tìm kiếm: loader thông thường chọn một bản; các bản còn lại không tạo ra hai runtime type riêng biệt bên trong cùng defining loader.
2. Hai **defining loader khác nhau** có thể định nghĩa hai class cùng binary name, nhưng đó là **hai type khác nhau**. Object từ loader A có thể không ép kiểu được sang class được định nghĩa bởi loader B, dù tên hiển thị giống nhau.

Các container web, plugin engine, application server và framework hot reload có thể dùng custom loader hoặc child-first. Trong tình huống đó, chỉ biết chuỗi `-cp` là chưa đủ. Cần kiểm tra **loader đã định nghĩa class**, quan hệ parent/child và các đường tìm kiếm mà loader thực sự sử dụng.

Một class đã được định nghĩa trong loader không tự đổi bytecode khi bạn sửa JAR trên đĩa. Để kiểm chứng phiên bản mới bằng lệnh `java` thông thường, khởi động tiến trình mới; các cơ chế instrumentation hoặc reload riêng nằm ngoài quy tắc classpath cơ bản.

## 7. Xác định class thực sự đã tải từ đâu

### 7.1. CodeSource và class loader

Thêm vào phương thức `main` của `Main.java`:

~~~java
System.out.println(
        Message.class.getProtectionDomain()
                .getCodeSource()
                .getLocation()
);
System.out.println(Message.class.getClassLoader());
~~~

Sau đó compile lại `Main.java` với alpha và chạy các lệnh đổi thứ tự classpath như mục 3. Với JAR thông thường, `getLocation()` thường trả URL như `file:/.../libs/alpha.jar` hoặc `file:/.../libs/beta.jar`. **Không có output cố định** ở đây vì đường dẫn phụ thuộc môi trường và biểu diễn class loader tùy JDK.

`getCodeSource()` có thể trả `null` với một số class/loader; nếu áp dụng cho class khác ngoài thí nghiệm, cần xử lý null khi xây công cụ chẩn đoán. Giá trị CodeSource là bằng chứng hữu ích, nhưng không phải API bảo đảm cho mọi cơ chế class loading.

### 7.2. Nhật ký class loading

Java 17 trên HotSpot hỗ trợ unified logging cho class loading:

~~~bash
java -Xlog:class+load=info -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Windows:

~~~bat
java -Xlog:class+load=info -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
~~~

Bộ log sẽ có nhiều dòng cho các class JDK và class ứng dụng. Tìm `org.example.api.Message` và thông tin `source` của entry tương ứng. Số dòng và vị trí log (stdout/stderr hoặc file nếu cấu hình) tùy JVM, nên không có “stdout chính xác” duy nhất cho lệnh bật log.

### 7.3. Kiểm tra nội dung JAR và API bằng javap

~~~bash
jar --list --file libs/alpha.jar
jar --list --file libs/beta.jar
javap -classpath libs/alpha.jar org.example.api.Message
javap -classpath libs/beta.jar org.example.api.Message
~~~

`jar --list` cho biết file class có thật trong JAR hay không. `javap` hiển thị chữ ký công khai của class được chỉ định, từ đó đối chiếu bản alpha và beta. Nếu cần kiểm tra tham chiếu tượng trưng trong `Main.class`, dùng thêm `javap -c -verbose -classpath out/app org.example.app.Main` và đọc bytecode/constant pool; đây là thao tác chẩn đoán, không làm thay đổi bytecode.

Đừng nhầm “JAR chứa file” với “JVM đã tải file từ JAR đó”: một thư viện có thể nằm trên classpath nhưng bị entry đứng trước che mất.

## 8. Classpath wildcard: không dựa vào thứ tự ngẫu nhiên

Java hỗ trợ classpath wildcard:

~~~bash
java -cp "out/app:libs/*" org.example.app.Main
~~~

Mẫu `libs/*` bao gồm các JAR/ZIP phù hợp nằm **trực tiếp** trong thư mục `libs`. Nó không tự đệ quy thư mục con và không phải glob arbitrary như `libs/**/*.jar`. Trong Bash, quote mẫu để tránh shell mở rộng nó thành các đối số trước khi Java nhận.

**Thứ tự JAR được mở rộng từ wildcard không được Java đảm bảo.** Không được dựa vào tên `01-alpha.jar`, `02-beta.jar` hay thứ tự liệt kê file system để quyết định bản class nào được dùng. Nếu cần minh họa thứ tự, liệt kê JAR rõ ràng:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

~~~bat
java -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
~~~

Ngay cả khi thứ tự tường minh giúp dự đoán kết quả của thí nghiệm, **giải pháp bền vững** là xử lý class trùng hoặc phiên bản không tương thích ở dependency graph. Wildcard tạo thêm biến số khi thay file trong thư mục, thay máy build hoặc đổi hệ điều hành.

## 9. Các trường hợp duplicate class thường gặp

### 9.1. Hai phiên bản thư viện trong cùng application

Ví dụ `logging-core-1.jar` và `logging-core-2.jar` cùng chứa `org.example.logging.Logger`. Java classpath chuẩn **không tự chọn phiên bản mới hơn** theo tên file hay số phiên bản. Nó tìm class theo cơ chế loader và classpath hiệu lực.

### 9.2. Dependency bắc cầu

Ứng dụng phụ thuộc A và B; A cần bản C cũ, B cần bản C mới. Maven/Gradle có cơ chế chọn phiên bản/giải quyết dependency riêng. File được thực sự chọn vào runtime classpath có thể không trùng với trực giác từ khai báo dependency đầu tiên. Hãy kiểm tra **resolved dependency graph** chứ không chỉ file build.

### 9.3. Output của dự án che thư viện

Nếu `out/app` cũng chứa `org/example/api/Message.class` và được đặt trước `libs/alpha.jar`, class từ output có thể thắng. Đây là lỗi dễ gặp khi còn class cũ hoặc copy bytecode vào output. Kiểm tra nội dung output, clean build có kiểm soát, tránh gói source/bytecode của vendor vào classpath root ứng dụng nếu không cần.

### 9.4. Fat JAR, shaded JAR và ứng dụng có nested JAR

Một uber JAR có thể gộp bytecode nhiều dependency. Khi gặp hai entry trùng cùng path, công cụ đóng gói có thể chọn một bản, loại bỏ, ghi đè hoặc báo lỗi tùy chính sách. Một Spring Boot executable JAR với nested libraries và launcher riêng cũng không nhất thiết vận hành giống hệt chuỗi `java -cp` đơn giản.

**Shading relocation** đổi package của một số class để tránh trùng binary name, nhưng phải tính đến reflection, resource paths, ServiceLoader, serialization và native integration. Không chỉ đổi tên class một cách máy móc.

### 9.5. Test, plugin và application server

Test runtime có thể thêm test classes hoặc dependency riêng; server có thể thêm thư viện chia sẻ; plugin framework có thể dùng child-first loader. Vì vậy cùng một chương trình có thể chạy khác giữa IDE, test, CLI và production.

Chẩn đoán cần ghi nhận: JDK version, launcher, runtime classpath, classloader identity, nguồn class đã tải và phiên bản JAR được đóng gói.

## 10. JPMS module path khác classpath phẳng

Từ Java 9, **Java Platform Module System** cho phép module có tên với khai báo `module-info.java`, `requires` và `exports`. Module path có các quy tắc giải quyết module/package khác classpath.

Ví dụ minh họa cú pháp (chỉ chạy nếu có module hợp lệ):

~~~bash
java --module-path "mods:external-mods" --module org.example.app/org.example.app.Main
~~~

Đừng coi đây là lệnh tương đương trực tiếp của ví dụ `java -cp` ở mục 3. Với JPMS:

- Classpath thông thường cung cấp class trong **unnamed module**.
- Module path là đường tìm các module được resolved.
- **Split package** giữa các named module có thể tạo lỗi module resolution/visibility, thay vì âm thầm lấy một class theo “JAR đầu tiên”.
- Module cùng tên, automatic module naming và việc đọc/export package đòi hỏi phân tích module graph cụ thể.
- Parent delegation và lớp nền tảng JDK vẫn có tác động; không thể tùy ý override JDK classes bằng cách đưa JAR lên đầu application classpath.

Khi báo lỗi nêu `module ... reads package ... from both ...`, hãy kiểm tra cấu hình module, không chỉ đảo thứ tự JAR.

## 11. Resource trùng tên không giống class trùng tên

Hai JAR có thể cùng chứa resource:

~~~text
config/default.properties
META-INF/services/org.example.spi.Plugin
~~~

Resource không phải định nghĩa class theo cùng cơ chế. Ví dụ `ClassLoader.getResources("config/default.properties")` có thể trả **nhiều URL**. Mã minh họa đặt trong một phương thức được khai báo xử lý `IOException`:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
java.util.Enumeration<java.net.URL> urls =
        loader.getResources("config/default.properties");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

Đoạn trên **không phải chương trình độc lập**; để dùng cần đặt trong method có `throws java.io.IOException` hoặc xử lý exception. `getResource` trả một resource phù hợp, còn `getResources` liệt kê nhiều resource theo quy tắc class loader.

`META-INF/services` thường được `ServiceLoader` dùng để tìm provider. Khi nhiều JAR cung cấp provider metadata, có thể có nhiều provider được phát hiện; không suy luận rằng chỉ JAR đầu tiên được dùng như lúc chọn một binary class name. Hợp nhất service configuration trong fat JAR phải được xử lý có chủ đích.

## 12. Quy trình chẩn đoán xung đột theo bằng chứng

Khi gặp sai hành vi hoặc liên kết runtime thất bại:

1. **Xác định binary name** bị ảnh hưởng (package + class name, gồm kiểu lồng khi có).
2. **Lấy compile classpath** đã dùng thực tế và API compiler thấy. Xem source, bytecode/chữ ký bằng `javap`.
3. **Lấy runtime classpath** chính xác từ launcher, build artifact, container hoặc cấu hình chạy. Kiểm tra dấu phân cách entry theo OS.
4. **Dò class thực tế đã tải** bằng `-Xlog:class+load=info`, CodeSource nếu có, hoặc thông tin từ class loader.
5. **Tìm mọi bản sao** trong các JAR và thư mục output: dùng `jar --list` hoặc công cụ kiểm tra duplicate classes.
6. **So sánh API và implementation** giữa bản compile và runtime. Có method/field bị xóa, đổi static/instance, khác phiên bản hoặc khác hành vi?
7. **Loại xung đột ở dependency** bằng chọn phiên bản nhất quán, loại dependency dư, lock/constraint, hoặc isolation hợp lý.
8. **Xác minh lại** trên môi trường giống production và kiểm thử hành vi chứ không chỉ nhìn exit code của `javac`.

Một số công cụ Gradle thường hữu ích ở dự án có wrapper và configuration `runtimeClasspath`:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

Trên Windows:

~~~bat
gradlew.bat dependencies --configuration runtimeClasspath
gradlew.bat dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

`example-library` là chỗ ghi tên dependency cần kiểm tra và các configuration phụ thuộc plugin/dự án. Maven có `mvn dependency:tree` khi Maven và dependency plugin phù hợp đã sẵn sàng. Những lệnh này giúp đọc **đồ thị dependency đã resolved**; với hệ thống loader đặc biệt, vẫn phải kiểm tra class được nạp lúc runtime.

### Bảng nhận diện nhanh

| Triệu chứng | Giả thuyết và hành động |
| --- | --- |
| Đổi thứ tự JAR làm stdout đổi | Duplicate binary class với API tương thích nhưng implementation khác; kiểm tra nguồn class |
| `NoSuchMethodError` ở production | Compile/runtime khác API; xem method descriptor và JAR thực tải |
| `NoSuchFieldError` | Runtime class không còn field tương thích |
| `ClassCastException` giữa đối tượng “cùng tên” | Xem defining class loader, có thể là hai class khác danh tính runtime |
| `lib/*` khi chạy cho kết quả bất định | Wildcard JAR order không đảm bảo; loại class trùng, dùng dependency nhất quán |
| `package ... does not exist` ở compile | Thiếu class/JAR trong compile classpath hoặc source path sai |
| `Could not find or load main class ...` | Sai classpath root/main FQN, không nhất thiết duplicate class |
| Test chạy đúng, application lỗi | So sánh test/runtime dependency và custom loader |
| Lỗi “module reads package from both” | Tập trung điều tra module graph/split package, không dùng quy tắc classpath đơn giản |

## 13. Bài tập tự kiểm tra

**Bài 1.** Trên Linux, `classes:libs/beta.jar:libs/alpha.jar` là classpath runtime; cả hai JAR có `org.example.api.Message`, class loader chuẩn không tìm được class này từ parent hay `classes`. Bản nào thắng?

**Đáp án:** Beta được xét trước alpha trong application classpath. Nếu chữ ký tương thích, kết quả `Message.text()` trong thí nghiệm là `beta`.

**Bài 2.** `Main.class` được compile với alpha có method `text()`; runtime tải beta đã xóa `text()`. Compiler có tự phát hiện lỗi runtime không?

**Đáp án:** Không bảo đảm. Compiler đã dùng API alpha và thành công. Khi JVM phân giải method trên beta, có thể ném `NoSuchMethodError`. Biên dịch lại source với beta mới sẽ phát hiện thiếu method ngay ở compile-time.

**Bài 3.** Có bảo đảm `libs/01-alpha.jar` thắng `libs/02-beta.jar` khi classpath chỉ ghi `libs/*` không?

**Đáp án:** Không. Thứ tự mở rộng wildcard không được đặc tả. Tên file không phải chính sách phiên bản.

**Bài 4.** Một `Greeting` có cùng binary name được nạp bởi hai defining class loader khác nhau. Có chắc chúng là cùng type không?

**Đáp án:** Không. Runtime class identity còn phụ thuộc defining class loader; hai type có thể không cast cho nhau.

**Bài 5.** Tại sao `jar --list --file libs/alpha.jar` thấy `Message.class` vẫn chưa chứng minh alpha đang được dùng?

**Đáp án:** Một entry khác đứng trước có thể cung cấp class, hoặc class được parent/custom loader định nghĩa. Phải kiểm tra nguồn class được nạp, không chỉ sự tồn tại trong JAR.

**Bài 6.** Nếu có hai file `META-INF/services/...` trong hai JAR, chúng có bị bỏ bản thứ hai theo cùng quy tắc duplicate class không?

**Đáp án:** Không suy luận vậy. Service provider metadata có thể được liệt kê/đọc từ nhiều resource; cần xét `ServiceLoader` và module/loader tương ứng.

## Ghi nhớ

- **Classpath có thứ tự**; trong phạm vi application class loader chuẩn, entry đầu tiên cung cấp binary class name thường được chọn.
- **Parent delegation, custom class loaders và JPMS** có thể khiến việc nhìn `-cp` đơn thuần chưa đủ.
- **Compile classpath và runtime classpath khác nhau** có thể gây hành vi khác hoặc lỗi liên kết như `NoSuchMethodError`, dù source đã compile thành công.
- **Wildcard `libs/*` không bảo đảm thứ tự JAR**; không dùng việc đổi tên file để giải quyết class trùng.
- **Kiểm tra bằng chứng**: `jar --list`, `javap`, `-Xlog:class+load=info`, CodeSource, class loader và resolved dependency graph.
- **Xử lý xung đột từ dependency/version** hoặc cô lập có chủ đích; đừng mặc định đảo thứ tự classpath là giải pháp dài hạn.
