# Vì sao module path khác classpath trong Java?

## 1. Mục tiêu

Trong Java, **classpath** là cơ chế truyền thống để tìm các class và JAR, còn **module path** được dùng bởi Java Platform Module System (JPMS) để tìm các **module có tên**, phân giải quan hệ phụ thuộc và thực thi các ranh giới truy cập do module descriptor quy định.

Hai cơ chế có thể cùng trỏ tới file .class hoặc JAR, nhưng mang ý nghĩa khác nhau:

- Classpath trả lời chủ yếu câu hỏi **lớp và tài nguyên này nằm ở đâu?**
- Module path còn trả lời **lớp thuộc module nào, module nào đọc module nào, package nào được phép truy cập từ bên ngoài, và package nào được mở cho reflection?**

JPMS xuất hiện trong Java 9. Bài này dùng **Java 17+**, tự biên dịch hai module, chạy lại cùng source bằng classpath, quan sát đầu ra, giải thích automatic/unnamed module, module-info.java, requires, exports, opens, các lỗi thường gặp và cách chuyển đổi ứng dụng cũ.

## 2. Bảng so sánh thực dụng

| Khía cạnh | Classpath | Module path |
| --- | --- | --- |
| Đơn vị tìm kiếm | Class/resource trong directory hoặc JAR | Named module từ modular JAR, exploded module và automatic module |
| Tên module | Classpath application code thường ở unnamed module | Named module có tên ổn định theo descriptor hoặc quy tắc automatic module |
| Khai báo dependency | Thường do ứng dụng và Maven/Gradle cấu hình ngoài class | Explicit module có requires trong module-info.java |
| Phân giải | Class loader tìm class theo cơ chế nạp và đường dẫn | Module resolver xác định root module và dependency graph |
| Ranh giới package | Java access modifier; chưa có export contract riêng cho JAR truyền thống | Phải thỏa module readability và package exports cùng Java access modifier |
| Reflection sâu | Phụ thuộc class/module thực tế và quy tắc runtime | Với named module thường cần opens cho non-public reflective access |
| Lỗi phổ biến | ClassNotFoundException, NoClassDefFoundError, xung đột JAR | FindException, lỗi readability, package not exported, InaccessibleObjectException |
| Công cụ | javac -cp, java -cp | javac --module-path, java --module-path, --module-source-path |

Không thể chỉ đổi tên tùy chọn -cp thành --module-path để mọi thư viện tự có cấu trúc module đúng. Module path tham gia một cơ chế **phân giải và kiểm tra mô hình module**, không đơn thuần là danh sách thư mục.

## 3. Cách classpath hoạt động

Ví dụ lệnh:

~~~sh
java -cp out com.example.app.Main
~~~

Với tên lớp com.example.app.Main, application class loader có thể tìm file:

~~~text
out/com/example/app/Main.class
~~~

Nếu có thư viện JAR, các JAR cần được đưa vào classpath phù hợp. Classloader tra cứu các lớp qua danh sách địa điểm và quy tắc tải lớp tương ứng. Cơ chế này không yêu cầu mỗi JAR khai báo một module-info.class cho biết nó cần module nào và export package nào.

Một class public trong thư viện classpath thường có thể được code classpath khác tham chiếu nếu thư viện hiện diện và các quy tắc truy cập Java cho phép. Vấn đề là thiếu một ranh giới package được kiểm tra qua module descriptor: ngay cả package được tác giả đặt tên internal cũng có thể chứa public type bị client sử dụng.

Một chương trình lớn thường nhờ Maven/Gradle quản lý dependency, nhưng **dependency của build tool không đồng nghĩa quan hệ requires trong JPMS**. Build tool giúp chọn/đưa JAR vào đúng chỗ; module descriptor mô tả quyền đọc và API của module lúc biên dịch/chạy.

Classpath vẫn là lựa chọn hợp lệ cho nhiều ứng dụng. Hiểu giới hạn của nó giúp biết khi nào module path mang lại lợi ích.

## 4. JPMS bổ sung điều gì?

JPMS cho phép một module khai báo:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Và module thư viện khai báo:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

Cấu trúc logic:

~~~text
com.example.app
     |
     | requires com.example.greetings
     v
com.example.greetings
     |
     | exports com.example.greetings.api
     v
Các public API của package api được module khác sử dụng
~~~

Khi ứng dụng dùng named modules, hệ thống phân giải graph từ các root modules và requires. Một class ở module khác có thể tồn tại trên module path nhưng vẫn **không truy cập được** vì module gọi chưa đọc module đó hoặc package chưa được export.

Một module có thể chứa nhiều package. **Tên module không bắt buộc trùng tên package**. Tên giống nhau ở tiền tố chỉ là quy ước giúp quản lý.

## 5. Ba loại module cần phân biệt

### Explicit named module

Là module có descriptor module-info.class được biên dịch từ module-info.java. Descriptor có tên module và các khai báo như requires, exports, opens, uses, provides. Khi artifact được phân giải trên module path, hệ thống áp dụng những ràng buộc tương ứng.

### Unnamed module

Các class được tải từ classpath thuộc một **unnamed module** của class loader tương ứng. Unnamed module không có tên module để một explicit module viết requires theo cách thông thường. Nó có các quy tắc đặc biệt phục vụ tương thích với code classpath cũ.

Đừng hiểu cả JVM chỉ có đúng một unnamed module: các class loader khác nhau có thể có unnamed module khác nhau. Trong ví dụ đơn giản dùng application class loader, các class cùng cpout nằm trong một unnamed module.

### Automatic module

Một JAR không có module-info.class vẫn có thể trở thành **automatic named module** khi đặt trên module path theo cơ chế JPMS. Tên module có thể lấy từ manifest Automatic-Module-Name hoặc được suy ra từ tên JAR. Automatic module có quy tắc đặc biệt để dễ chuyển đổi, bao gồm export các package và khả năng đọc phù hợp với cơ chế automatic modules.

Vì vậy **plain JAR trên module path không tự có cùng mức đóng gói với explicit module**. Khi phụ thuộc vào automatic module, nên chọn artifact có tên module ổn định, tránh tên tự suy ra bất ngờ thay đổi khi đổi filename hoặc phiên bản.

## 6. module-info.java mô tả những gì?

Một số khai báo quan trọng:

| Khai báo | Ý nghĩa |
| --- | --- |
| module m { ... } | Định nghĩa module có tên m |
| requires m; | Module hiện tại đọc/phụ thuộc m |
| requires transitive m; | Truyền quan hệ đọc m cho module đọc module hiện tại theo quy tắc implied readability |
| requires static m; | Dependency cần ở compile-time nhưng không nhất thiết hiện diện khi resolution lúc chạy |
| exports p; | Công khai API thông thường của package p đến các module đọc module này |
| exports p to m; | Export package có giới hạn tới module m |
| opens p; | Mở package cho deep reflection |
| opens p to m; | Mở package cho reflection của module m |
| uses service.Type; | Module sử dụng một service |
| provides service.Type with impl.Provider; | Module cung cấp implementation của service |

Mọi module ngầm đọc **java.base**. Do đó một module cơ bản không cần ghi requires java.base. Nếu cần API thuộc một module khác của JDK, ví dụ java.sql, code của explicit named module thường phải khai báo requires java.sql.

Các khai báo trong module-info.java là một phần của mô hình module: **đặt JAR trên module path không tự điền requires vào descriptor của ứng dụng**.

### Readability và accessibility là hai điều kiện riêng

Để code trong com.example.app gọi public Greeter từ com.example.greetings, cần ba điều kiện:

1. App có quan hệ đọc đến com.example.greetings, chẳng hạn qua requires.
2. com.example.greetings export package chứa Greeter tới app.
3. Bản thân Greeter và member cần gọi có quyền Java tương thích, ví dụ public.

Chỉ có requires mà thiếu exports vẫn bị giới hạn API. Chỉ có exports mà app không đọc module thư viện thì cũng không có đủ điều kiện. Package internal chứa public class có thể vẫn không được sử dụng từ module khác.

## 7. Dự án mẫu hai module

Tạo thư mục **module-lab** với cấu trúc:

~~~text
module-lab/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greetings/
    │               ├── api/
    │               │   └── Greeter.java
    │               └── internal/
    │                   └── Hidden.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Dưới src, tên thư mục **com.example.greetings** và **com.example.app** tương ứng tên module. Bên trong mỗi module, các nhánh com/example/... là cấu trúc package thông thường.

### Tệp src/com.example.greetings/module-info.java

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

Module thư viện export package api. Package internal không export, dù có thể chứa public class.

### Tệp src/com.example.greetings/com/example/greetings/api/Greeter.java

~~~java
package com.example.greetings.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Tệp src/com.example.greetings/com/example/greetings/internal/Hidden.java

~~~java
package com.example.greetings.internal;

public final class Hidden {
    private Hidden() {
    }

    public static String secret() {
        return "internal";
    }
}
~~~

Hidden được khai báo public, nhưng package không export. Đây là ví dụ cho thấy public modifier **chưa đủ** để loại bỏ ranh giới giữa hai named modules.

### Tệp src/com.example.app/module-info.java

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Đây là cạnh phụ thuộc từ app tới thư viện. Module app có thể đọc module thư viện; package api của thư viện được export nên app có thể dùng Greeter.

### Tệp src/com.example.app/com/example/app/Main.java

~~~java
package com.example.app;

import com.example.greetings.api.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.hello("Lan"));
        System.out.println("App named: "
                + Main.class.getModule().isNamed());
        System.out.println("Lib named: "
                + Greeter.class.getModule().isNamed());
    }
}
~~~

Phương thức getModule().isNamed() giúp quan sát một class thuộc named module hay unnamed module. Bài không cần thư viện ngoài và phù hợp Java 17.

## 8. Biên dịch và chạy bằng module path

Đặt CWD của terminal tại gốc **module-lab**, tức thư mục chứa src.

Trên Bash:

~~~bash
mkdir -p mods
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Path mods -Force | Out-Null
~~~

Biên dịch cả hai module:

~~~sh
javac --release 17 --module-source-path src -d mods -m com.example.greetings,com.example.app
~~~

Ý nghĩa từng option:

- **--module-source-path src**: gốc cây mã nguồn modular, chứa các thư mục theo tên module.
- **-d mods**: ghi class files của mỗi module xuống cây thư mục đầu ra.
- **-m com.example.greetings,com.example.app**: trong ngữ cảnh javac, liệt kê tên các module nguồn cần biên dịch.

Sau compile, đầu ra chính:

~~~text
mods/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/example/greetings/
│       ├── api/Greeter.class
│       └── internal/Hidden.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Đường dẫn mods là một entry của module path chứa hai **exploded modules**. Mỗi thư mục con mang tên module và chứa module-info.class.

Chạy từ cùng CWD:

~~~sh
java --module-path mods -m com.example.app/com.example.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello, Lan!
App named: true
Lib named: true
~~~

Khi Java launcher giải quyết module root com.example.app, quan hệ requires kéo com.example.greetings vào graph; lớp Main và Greeter được tải trong named modules tương ứng. Lệnh -m của java có dạng moduleName/mainClass. Nếu module đã có main class metadata phù hợp, phần /mainClass đôi khi có thể bỏ; ví dụ chủ động viết đầy đủ để rõ ràng.

**Đừng nhầm ba đường dẫn:**

| Đường dẫn | Công cụ | Ý nghĩa |
| --- | --- | --- |
| --module-source-path src | javac | Nơi tìm nguồn của module |
| -d mods | javac | Nơi ghi bytecode của module |
| --module-path mods | java | Nơi tìm module artifacts để phân giải và chạy |

Nếu biên dịch riêng app sau khi module thư viện đã được biên dịch, javac có thể cần --module-path mods để nhìn thấy module dependency dưới dạng bytecode. Module source path và module path đóng hai vai trò khác nhau.

## 9. Cùng mã Java, nhưng biên dịch/chạy bằng classpath

Giữ nguyên **Greeter.java và Main.java**. Ở chế độ classpath dưới đây, chỉ biên dịch tường minh hai tệp class nguồn, không đưa hai module-info.java vào lượt javac.

Từ CWD = module-lab, tạo output root:

~~~bash
mkdir -p cpout
~~~

~~~powershell
New-Item -ItemType Directory -Path cpout -Force | Out-Null
~~~

Biên dịch:

~~~sh
javac --release 17 -d cpout src/com.example.greetings/com/example/greetings/api/Greeter.java src/com.example.app/com/example/app/Main.java
~~~

Chạy:

~~~sh
java -cp cpout com.example.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello, Lan!
App named: false
Lib named: false
~~~

Hai method hello và main không đổi. Sự khác biệt đến từ **cách compile và load**:

- Trong ví dụ classpath, compiler không xử lý module-info.java vì không đưa chúng vào lượt biên dịch.
- Runtime tìm class trực tiếp dưới cpout/com/example/... bằng tên package và class.
- Hai class trong ví dụ thuộc unnamed module, vì vậy isNamed() trả false.
- Không có named-module graph của com.example.app và com.example.greetings đang được dùng để kiểm tra requires/exports giữa chúng.

| Đối chiếu | Modular mode | Classpath mode |
| --- | --- | --- |
| Compile | javac --module-source-path src -d mods -m com.example.greetings,com.example.app | javac -d cpout cùng hai .java |
| Run | java --module-path mods -m com.example.app/com.example.app.Main | java -cp cpout com.example.app.Main |
| Output root | mods/[moduleName]/[package]/Class.class | cpout/[package]/Class.class |
| App named | true | false |
| Lib named | true | false |

Đây là bằng chứng thực nghiệm quan trọng: **tên package tự nó không biến class thành named module**. Module descriptor và chế độ phân giải/tải module quyết định sự khác biệt.

### Nếu modular JAR đặt trên classpath

Một JAR chứa module-info.class vẫn có thể được chạy qua classpath nếu thư viện hỗ trợ cấu hình đó. Khi ấy module descriptor không khiến JAR được phân giải thành named module chỉ vì bên trong có module-info.class. Ngược lại, một plain JAR chưa có descriptor có thể trở thành automatic module khi đặt trên module path. **Vị trí và cơ chế nạp quyết định vai trò**, không chỉ tên file.

## 10. Thử nghiệm thiếu requires và thiếu exports

Các sửa đổi sau là **thí nghiệm cố tình gây lỗi biên dịch**; hãy khôi phục source gốc sau khi thử.

### Thí nghiệm A — Bỏ requires

Trong src/com.example.app/module-info.java, tạm bỏ dòng:

~~~java
requires com.example.greetings;
~~~

Giữ Main.java vẫn import Greeter, sau đó chạy lại lệnh javac modular. Compiler sẽ không có quan hệ đọc phù hợp để app truy cập package thư viện; thông báo thường nhắc module không đọc module chứa package.

**Cách sửa đúng:** khôi phục requires com.example.greetings. Chỉ thêm file/JAR vào module path không tự bổ sung cạnh requires cho một explicit module.

### Thí nghiệm B — Package public nhưng không export

Trong Main.java, tạm thêm:

~~~java
import com.example.greetings.internal.Hidden;
~~~

Và bên trong main thử gọi:

~~~java
System.out.println(Hidden.secret());
~~~

Những dòng trên là **phần thay đổi trong tệp hiện có**, không phải chương trình độc lập. Khi biên dịch dưới dạng named modules, javac từ chối truy cập vì com.example.greetings.internal không export tới app, dù Hidden và secret đều public.

**Cách sửa đúng trong thiết kế thư viện:** sử dụng API do package com.example.greetings.api công khai. Chỉ thêm exports cho internal nếu chủ đích thay đổi ranh giới API. Không nên mở mọi package chỉ để biên dịch qua lỗi.

### Thí nghiệm C — Truy cập cùng class trên classpath

Trong bản thực hành tách riêng, biên dịch cả Hidden.java vào cpout và dùng một Main.java tạm thời import Hidden mà **không biên dịch module-info.java**. Khi classpath chứa lớp cần thiết, việc dùng public Hidden có thể được chấp nhận vì không tồn tại ranh giới exports của named module cho hai lớp này.

Đây là ví dụ cho **sự khác nhau của hai chế độ**, không phải lý do nên công khai class internal cho client trong dự án thật.

## 11. Module resolution khác tìm class như thế nào?

**Classpath lookup** tìm class theo tên và cơ chế class loader. Với nhiều JAR chứa cùng binary class name, classloader và thứ tự nguồn được cấu hình có thể ảnh hưởng lớp nào được nạp. Không có một module graph bắt buộc dựa trên requires của từng JAR.

**Module resolution** bắt đầu từ các root modules, sau đó tìm các module cần thiết qua requires cùng các quy tắc JPMS khác. Hệ thống tạo module graph, xác định readability và kiểm tra các ràng buộc liên quan. JVM vẫn dùng class loader để tải các class, nhưng named-module access có thêm giới hạn so với phép tra cứu classpath thông thường.

Với:

~~~sh
java --module-path mods -m com.example.app/com.example.app.Main
~~~

com.example.app là root module. com.example.greetings được kéo vào vì app có requires tương ứng. Chỉ việc đặt một module thứ ba trên module path **không bảo đảm module đó luôn được resolve**; phải có root, cạnh dependency, hoặc lựa chọn resolution phù hợp.

### Quan sát cấu hình module

Từ gốc module-lab:

~~~sh
java --module-path mods --describe-module com.example.app
java --module-path mods --describe-module com.example.greetings
~~~

Các lệnh mô tả descriptor/module có thể cho thấy requires và exports. Đầu ra chính xác có thể khác chi tiết theo phiên bản JDK.

Để in thông tin resolution khi chạy:

~~~sh
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Lệnh này còn in thông tin module resolution. Vì vậy **không lấy toàn bộ output debug làm stdout chuẩn** ba dòng của chương trình ví dụ.

## 12. Automatic module: cách dùng JAR chưa có descriptor

Một JAR thường không có module-info.class có thể được đưa lên module path dưới dạng automatic module. Khi đó nó có tên được xác định qua Automatic-Module-Name hoặc quy tắc suy ra từ filename, và được hưởng cơ chế tương thích của automatic modules.

Những điều cần nhớ:

- Automatic module **có tên**, khác unnamed module của classpath.
- Nó thường export tất cả packages của mình; không phải explicit module đã được tác giả giới hạn API theo từng exports.
- Nó có các quy tắc readability đặc biệt để hỗ trợ migration.
- Một explicit module có thể requires tên của automatic module.
- Nếu tên được suy ra từ JAR filename, thay đổi tên artifact có thể làm dependency khai báo trong module-info.java bị sai.

Một explicit named module không thể đơn giản viết requires với một unnamed module vốn không có tên. Đó là lý do việc chuyển một ứng dụng nhiều JAR sang module path đôi khi cần dùng automatic module, thay dependency hoặc thay đổi cách tổ chức module.

## 13. exports khác opens

Mô hình JPMS phân biệt quyền sử dụng public API bình thường và quyền truy cập sâu qua reflection.

- **exports p**: module đọc phù hợp có thể dùng các public types/member truy cập được trong package p theo quy tắc Java.
- **opens p**: cho phép deep reflection vào package, chẳng hạn reflective access đối với non-public member khi thỏa điều kiện runtime.
- **exports p to m** và **opens p to m**: chỉ định các module đích được cấp quyền tương ứng.
- **open module m**: cho phép mở các packages của module cho reflection theo quy tắc của dạng module đó.

Ví dụ descriptor minh họa, không phải project hoàn chỉnh:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.entity to com.example.serializer;
}
~~~

Package api phục vụ API thông thường; entity được mở tới một framework module cụ thể. Một package được opens không vì vậy tự trở thành package được export cho mọi module ở compile-time.

Khi framework dùng reflection (chẳng hạn một bộ serializer), lỗi runtime **InaccessibleObjectException** có thể cho thấy module thiếu opens phù hợp. Tùy chọn --add-opens hỗ trợ migration/diagnostics; về lâu dài cần đặt ranh giới reflection có chủ đích.

**JPMS không phải security sandbox**: nó kiểm soát ranh giới module theo mô hình ngôn ngữ/JVM, không thay quyền của hệ điều hành hoặc các cơ chế bảo vệ dữ liệu.

## 14. requires transitive và requires static

### requires transitive

Giả sử facade module công khai API chứa các kiểu thuộc service module:

~~~text
app --requires--> facade --requires transitive--> service
~~~

Khi app đọc facade, quan hệ **implied readability** cho phép app cũng đọc service theo quy tắc requires transitive. Điều này hữu ích nếu API công khai của facade biểu lộ kiểu của service.

Nhưng requires transitive **không làm tất cả packages của service tự động được export**. Package đó còn phải được service export phù hợp; các điều kiện về quyền Java vẫn có hiệu lực.

### requires static

Khai báo requires static dành cho dependency cần lúc biên dịch nhưng không bị bắt buộc phải hiện diện khi module được phân giải lúc runtime. Nó thường dùng cho một số dependency tùy chọn/annotation.

Nếu code thực sự cần class từ dependency bị thiếu khi chạy, nó vẫn có thể lỗi runtime. **requires static không bảo đảm code tham chiếu dependency vắng mặt luôn hoạt động**.

## 15. Split package và các xung đột

**Split package** xuất hiện khi nhiều artifact cùng định nghĩa class trong một package, ví dụ hai JAR đều chứa com.example.shared.

Classpath có thể chứa các JAR như vậy, mặc dù dễ gây mơ hồ và xung đột version. JPMS đặt thêm các giới hạn về package giữa các named modules trong một configuration, đặc biệt khi một module có thể đọc cùng package từ nhiều nguồn. Tùy module graph và loader, lỗi có thể xảy ra trong compile hoặc resolution với thông báo về package conflict.

Đừng kết luận mọi trường hợp package cùng tên luôn thất bại giống hệt nhau; phải xem graph/exports/readability. Nhưng khi thiết kế explicit modules, **nên xác định mỗi package thuộc module nào một cách rõ ràng**, tránh tùy tiện chia cùng một package giữa nhiều JAR.

Module path cũng không tự giải quyết mọi version conflict hoặc API mismatch. Dù module graph được phân giải thành công, bạn vẫn cần quản lý dependency và chạy test.

## 16. Classpath, module path và JAR trong dự án lớn

Cả hai path đều có thể liên quan đến JAR, nhưng được diễn giải khác:

- Classpath thường liệt kê thư mục/JAR cung cấp các class.
- Module path liệt kê nơi chứa modular JAR hoặc exploded modules; plain JAR đủ điều kiện có thể trở thành automatic module.
- Modular JAR có module-info.class; khi được nhận dạng/phân giải trên module path, các ranh giới named module có hiệu lực.
- Modular JAR khi đưa vào classpath có thể chạy ở classpath mode nếu dependency và mã thư viện tương thích; descriptor không tự biến nó thành named module ở chế độ đó.

Classpath separator thường là dấu **;** trên Windows, dấu **:** trên Linux/macOS. Các ví dụ của bài chỉ dùng một output directory nên không cần separator.

Một số tùy chọn đặc biệt:

| Tùy chọn | Mục đích |
| --- | --- |
| --module-path hoặc -p | Nơi tìm các module artifacts |
| --module hoặc -m | Chọn root module/main ở java; chọn module nguồn ở javac theo ngữ cảnh |
| --add-modules | Bổ sung root modules để module resolution xét |
| --add-reads | Bổ sung quan hệ module readability trong cấu hình đặc biệt |
| --add-exports | Bổ sung quyền export package trong cấu hình |
| --add-opens | Cho phép reflective access sâu phù hợp cấu hình |
| --show-module-resolution | In module graph resolution lúc launcher khởi động |

Đừng thử tất cả --add-... option để làm lỗi biến mất. Mỗi option giải quyết một loại quan hệ khác nhau, thường chỉ thích hợp khi migration hoặc debug có kiểm soát.

## 17. Bảng chẩn đoán lỗi

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Module ... not found | Thiếu module artifact, tên module sai, module path sai | Xác nhận tên, module-info.class, nơi đặt module và đường dẫn |
| package ... is not visible / module ... does not read | Thiếu quan hệ readability | Kiểm tra requires và graph |
| package ... is not exported | Dependency tồn tại nhưng package không export tới caller | Dùng exported API hoặc chỉnh contract exports có chủ đích |
| Could not find or load main class | Sai classpath root hoặc tên lớp đầy đủ | Kiểm tra -cp và package.Class |
| java.lang.module.FindException | Module cần thiết không resolve được | Kiểm tra module path, tên và dependency |
| InaccessibleObjectException | Thiếu quyền deep reflection vào package | Kiểm tra opens/module caller |
| Package conflict | Split package hoặc module graph không hợp lệ | Kiểm tra module chứa package và JAR trùng |
| isNamed() false bất ngờ | Code đang chạy qua classpath/unnamed module | Kiểm tra java command và artifact thực sự nạp |
| Runtime lỗi dù compile thành công | Runtime path khác compile path, bản artifact cũ | So sánh compile/runtime dependencies, build lại đúng scope |

Quy trình khắc phục:

1. Kiểm tra javac -version và java -version, dùng JDK 17+ cho bài.
2. Xác nhận CWD, đường dẫn source và output.
3. Nếu dùng explicit modules, kiểm tra module-info.java đã được compile thành module-info.class.
4. Đọc requires ở module gọi, exports ở module thư viện và quyền Java của class/member.
5. Phân biệt thiếu artifact, thiếu module graph edge, thiếu export hay thiếu opens.
6. Dùng --describe-module và --show-module-resolution khi cần.
7. Kiểm tra bản .class/JAR đang chạy thực sự; không nhầm cpout với mods.

## 18. Khi nào chọn cơ chế nào?

**Classpath** phù hợp cho nhiều ứng dụng hiện có, nhất là khi thư viện chưa modular hóa và Maven/Gradle đã kiểm soát được packaging. Không phải mọi chương trình Java đều phải tạo module-info.java.

**Module path** có giá trị khi muốn thiết kế ranh giới public API, quan hệ dependency có khai báo, module resolution rõ ràng, và từng bước khai thác modular runtime. JPMS cũng hỗ trợ các công cụ như jlink để tạo custom runtime image từ tập module thích hợp, nhưng không phải ứng dụng nào cần custom image.

Dự án chuyển đổi có thể kết hợp classpath và module path, nhưng cần hiểu named/unnamed/automatic modules; explicit named module không thể cứ viết requires tới unnamed module. Chuyển đổi đòi hỏi kiểm tra dependency, package conflicts và framework reflection, thay vì chỉ đổi option launcher.

## 19. Bài tập tự thực hành

1. Tự tạo cấu trúc hai module và chạy lệnh javac --module-source-path src -d mods -m com.example.greetings,com.example.app. Kiểm tra mỗi module có module-info.class dưới mods.
2. Chạy modular mode. Vì sao App named và Lib named đều true?
3. Chỉ compile hai class nguồn vào cpout, chạy bằng -cp. Vì sao hai giá trị đều false dù logic hello giống hệt?
4. Tạm bỏ requires của app, compile lại modular và phân tích thông báo về readability.
5. Tạm import Hidden. Vì sao public class vẫn không được dùng từ named module khác nếu package không export?
6. Đọc descriptor bằng --describe-module; thử --show-module-resolution và xác định root module cũng như dependency.
7. Tự giải thích khác nhau giữa exports và opens, đồng thời nêu một trường hợp framework cần deep reflection.
8. Giả sử một plain JAR được đặt trên module path. Nó có thể được nhận dạng thế nào, và tại sao tên suy ra từ filename có thể gây rủi ro?
9. Giải thích vì sao module path không đơn thuần là classpath có tên khác và vì sao build tool vẫn có vai trò trong ứng dụng JPMS.

## 20. Kiểm tra kiến thức

- Classpath tra cứu class/JAR; module path tham gia nhận diện named modules và module graph.
- Explicit module có module-info.java, được biên dịch thành module-info.class.
- requires tạo quan hệ đọc; exports công khai package; opens phục vụ deep reflection.
- Public class nằm trong package không export vẫn có thể không truy cập được từ named module khác.
- Class trên classpath thuộc unnamed module của class loader tương ứng.
- Plain JAR trên module path có thể trở thành automatic module, không mang mọi giới hạn của explicit descriptor.
- Không phải module nào nằm trên module path cũng được resolve nếu không có root/dependency phù hợp.
- JPMS không thay thế Maven/Gradle, không tự khắc phục mọi version conflict và không phải sandbox bảo mật.
- Lệnh module path chọn root module bằng -m; lệnh classpath chọn class main theo tên đầy đủ.
- Cùng mã nguồn có thể chạy theo hai mode với hợp đồng truy cập khác nhau.

### Tài liệu đọc sâu

- **Java Language Specification**: phần *Modules*, *Accessibility*, yêu cầu của module declaration.
- **Java Virtual Machine Specification**: định dạng module-info.class và quyền truy cập theo module.
- **OpenJDK JPMS**: *The State of the Module System* và tài liệu giải thích module resolution.
- Tài liệu chính thức **java**, **javac**, **jar** và **jlink** của phiên bản JDK đang dùng để đối chiếu cú pháp command-line.

**Điểm cần nhớ:** classpath là cơ chế tìm class truyền thống; module path khiến những class được tổ chức dưới các named modules với descriptor, graph phụ thuộc và ranh giới export/reflective access. Sự khác biệt chủ yếu nằm ở **ngữ nghĩa module và cách Java phân giải, nạp và kiểm tra quyền truy cập**, không chỉ ở hai tên tham số terminal.
