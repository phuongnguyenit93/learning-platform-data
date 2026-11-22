# Quan hệ giữa compile-time, run-time và module graph

Trong Java Platform Module System (JPMS), một ứng dụng không chỉ có các file `.class` và JAR. Nó còn có **module graph**: tập những named module được chọn và quan hệ phụ thuộc giữa chúng. Graph này ảnh hưởng trực tiếp đến hai thời điểm quan trọng:

- **Compile-time:** `javac` cần tìm được module và API để kiểm tra mã nguồn, kiểu dữ liệu và quyền truy cập.
- **Run-time:** Java launcher và JVM cần resolve những module cần thiết, tạo module layer, nạp class và thực thi ứng dụng.

Compile thành công là điều kiện cần nhưng không bảo đảm runtime có đầy đủ module, đúng phiên bản và cấu hình giống lúc build. Ngược lại, một module có trong JDK runtime nhưng không được resolve vào graph khởi động chưa chắc đã dùng được theo cách mã nguồn đang giả định.

Bài này kết nối ba khái niệm **compile-time, run-time và module graph**, rồi minh họa bằng một ứng dụng JPMS gồm nhiều module.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt dependency lúc biên dịch và lúc chạy trong JPMS.
- Giải thích module resolution tạo graph từ root modules và quan hệ `requires`.
- Hiểu vai trò của `module-info.java` trong cả `javac` và Java launcher.
- Phân biệt **observable modules**, **resolved modules**, **readability** và **accessibility**.
- Giải thích `requires`, `requires transitive` và `requires static` trong hai giai đoạn.
- Biên dịch và chạy một ví dụ đa module với `--module-source-path` và `--module-path`.
- Dùng `--show-module-resolution` và Java API để quan sát graph runtime.
- Nhận diện các lỗi “compile được nhưng chạy lỗi” và “module có mặt nhưng không đọc/truy cập được”.

## 1. Ba lớp trong một ứng dụng Java modular

Hãy tưởng tượng ứng dụng gồm:

~~~text
com.acme.app
      |
      | requires
      v
com.acme.service
      |
      | requires transitive
      v
com.acme.model
~~~

Mỗi node là một **named module**, không phải đơn thuần một JAR. Mỗi cạnh thể hiện quan hệ module được khai báo hoặc được suy ra theo quy tắc JPMS.

Để hiểu graph, cần tách ba lớp thông tin:

| Lớp | Câu hỏi cần trả lời | Nơi kiểm tra |
|---|---|---|
| Artifact | Class/JAR thực sự nằm ở đâu? | Source tree, output folder, module path |
| Module resolution | Những named module nào tham gia configuration? | `module-info.java`, root modules, resolver |
| Module access | Module nào đọc được module nào và package nào được truy cập? | `requires`, `exports`, `opens` và quy tắc Java |

Một JAR có thể tồn tại trên ổ đĩa nhưng không nằm trên module path. Một module có thể được tìm thấy trên module path nhưng chưa được chọn vào graph. Một module đã resolved vẫn có thể không export package mà mã nguồn muốn import.

Đó là lý do cần chẩn đoán đúng tầng, thay vì coi mọi lỗi là “thiếu dependency”.

## 2. Compile-time diễn ra như thế nào?

Ở compile-time, `javac` đọc mã nguồn và module descriptors để kiểm tra:

1. Module đang biên dịch có tên gì?
2. Nó khai báo cần đọc những module nào?
3. Các module dependency có thể được tìm thấy không?
4. Package được import có được export cho module sử dụng không?
5. Class, constructor và method có đủ quyền truy cập theo ngôn ngữ Java không?

Ví dụ descriptor:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Khai báo này nói rằng `com.acme.app` phụ thuộc `com.acme.service` ở cấp module. Khi biên dịch app, compiler phải có khả năng tìm được module service, chẳng hạn qua compiled module directory hoặc modular JAR trên `--module-path`.

Việc một IDE hiển thị dependency trong project không tự bảo đảm compiler chạy ở CI hoặc terminal cũng nhìn thấy module đó.

### 2.1. Module path là nguồn tìm module, không phải graph cuối cùng

Ví dụ:

~~~bash
javac --module-path mods -d out/app \
    src/com.acme.app/module-info.java \
    src/com.acme.app/com/acme/app/Main.java
~~~

`--module-path mods` chỉ định vị trí tìm module dependency. Resolver vẫn cần dựa trên root và `requires` để tạo configuration dùng cho compilation.

Không nên diễn giải “JAR nằm trên module path” thành “ứng dụng tự động đọc toàn bộ package của JAR đó”.

### 2.2. Readability khác package export

Giả sử app đã có:

~~~java
requires com.acme.service;
~~~

Nhưng service descriptor là:

~~~java
module com.acme.service {
}
~~~

Nếu app muốn import public class từ `com.acme.service.api`, compiler có thể báo package không được export.

Khi đó:

- `requires` của app tạo quan hệ đọc.
- `exports com.acme.service.api;` trong module service công bố package API.
- `public` trên class mới cho phép code ngoài package tham chiếu class theo các quy tắc Java thông thường.

**Đủ readability mà thiếu exports vẫn có thể không compile được.** Tương tự, package đã export nhưng app không đọc module chứa nó cũng chưa đủ.

## 3. Runtime diễn ra như thế nào?

Khi chạy một ứng dụng modular:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Java launcher xác định main module `com.acme.app` là một root. Module system tìm module này, đọc descriptor và resolve các dependency bắt buộc. Kết quả là một **resolved module graph** dùng để định nghĩa những module trong boot layer và thực thi ứng dụng.

Luồng tổng quát:

~~~text
Lệnh java -m com.acme.app/...
               |
               v
       Root: com.acme.app
               |
               v
    Tìm module từ runtime image
    và --module-path
               |
               v
       Resolve dependencies
         từ module-info
               |
               v
       Runtime configuration
               |
               v
       Boot ModuleLayer
               |
               v
       Class loading + execution
~~~

Một số dependency xuất hiện ở compile-time có thể vắng mặt hợp lệ lúc runtime nếu được khai báo bằng `requires static` và ứng dụng thực sự không cần các kiểu đó khi chạy. Những dependency bắt buộc do `requires` thông thường vẫn phải có để graph được resolve.

### 3.1. Module hiện diện chưa chắc đã resolved

Phân biệt hai câu hỏi:

- Runtime image **có chứa** `java.sql` không?
- Boot layer của tiến trình **đã resolve** `java.sql` chưa?

Có thể kiểm tra bằng code:

~~~java
import java.lang.module.ModuleFinder;

public class ModuleState {
    public static void main(String[] args) {
        String moduleName = "java.sql";

        boolean present =
            ModuleFinder.ofSystem()
                        .find(moduleName)
                        .isPresent();

        boolean resolved =
            ModuleLayer.boot()
                       .findModule(moduleName)
                       .isPresent();

        System.out.println("Present in runtime image: " + present);
        System.out.println("Resolved in boot layer: " + resolved);
    }
}
~~~

`ModuleFinder.ofSystem()` tra cứu system modules có trong runtime image; `ModuleLayer.boot().findModule()` tra cứu module trong boot layer. Kết quả có thể khác nhau vì **module có sẵn** không đồng nghĩa nó **đã tham gia graph khởi động**.

Không nên dùng kết quả của một phép kiểm tra để suy ra kết quả của phép còn lại.

## 4. Module graph được xây dựng từ đâu?

Graph không được tạo bằng cách “đưa toàn bộ JAR vào JVM”. Quá trình resolution bắt đầu từ các **root modules** và đi theo dependency được khai báo.

Nguồn thông tin quan trọng:

- `module-info.class` của các explicit named modules.
- Root modules được chọn bởi chế độ khởi chạy, ví dụ main module với `-m`.
- Những root bổ sung qua `--add-modules`.
- System modules của runtime image.
- Application modules từ `--module-path`.
- Một số tùy chọn launcher hoặc cấu hình service binding phù hợp.

Khi main module yêu cầu service và service yêu cầu model:

~~~text
Root com.acme.app
    |
    +-- requires com.acme.service
              |
              +-- requires transitive com.acme.model
~~~

Resolver tìm những dependency cần thiết, kiểm tra tính nhất quán và hình thành graph trước khi gọi `Main.main()`.

### 4.1. Node và edge có ý nghĩa riêng

**Node** là một module được resolve. **Edge** mô tả quan hệ phụ thuộc/readability phù hợp theo descriptor hoặc cơ chế bổ sung.

Với:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App có cạnh phụ thuộc trực tiếp tới service. Nhưng khả năng app sử dụng một public type bên trong service vẫn phụ thuộc package đó có export hay không.

### 4.2. Readability không phải quyền truy cập tùy ý

Một module đã đọc module khác không có nghĩa mọi package nội bộ đều được truy cập. JPMS còn thực hiện strong encapsulation:

~~~java
module com.acme.service {
    exports com.acme.service.api;
}
~~~

Package `com.acme.service.internal` không tự được export chỉ vì app có `requires com.acme.service;`.

Nếu framework cần deep reflection, module cung cấp có thể phải dùng `opens` hoặc qualified opens đúng package và module framework. Đây là một cơ chế khác với compile-time access tới public API.

### 4.3. Runtime graph không nhất thiết là toàn bộ hệ thống

Graph của boot layer không phải toàn bộ những module có thể tồn tại trong JVM. Ứng dụng plugin có thể tạo `ModuleLayer` mới từ một `Configuration` đã resolve riêng, hoặc một số class vẫn thuộc unnamed module trên classpath.

Do đó, khi nói “module graph của ứng dụng”, nên xác định đang xét **compile-time configuration**, **boot layer** hay **một layer động**.

## 5. Ví dụ hoàn chỉnh gồm ba module

Ta tạo:

~~~text
project/
└── src/
    ├── com.acme.model/
    │   ├── module-info.java
    │   └── com/acme/model/api/Message.java
    ├── com.acme.service/
    │   ├── module-info.java
    │   └── com/acme/service/api/GreetingService.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Ví dụ dùng JDK 17 trở lên.

### 5.1. Model module

`src/com.acme.model/module-info.java`:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

`src/com.acme.model/com/acme/model/api/Message.java`:

~~~java
package com.acme.model.api;

public record Message(String text) {
}
~~~

Model công bố package chứa `Message`. Đây là public API mà các module khác có thể sử dụng khi đã có quan hệ đọc phù hợp.

### 5.2. Service module

`src/com.acme.service/module-info.java`:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

`src/com.acme.service/com/acme/service/api/GreetingService.java`:

~~~java
package com.acme.service.api;

import com.acme.model.api.Message;

public final class GreetingService {
    public Message greet(String name) {
        return new Message("Xin chào, " + name);
    }
}
~~~

Service trả về `Message` từ model trong chữ ký public method. Vì vậy, việc khai báo `requires transitive com.acme.model;` giúp các module đọc service cũng đọc model. Đây là lựa chọn hợp lý khi model nằm trong hợp đồng API của service.

### 5.3. App module

`src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

`src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.model.api.Message;
import com.acme.service.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        Message message = service.greet("JPMS");
        System.out.println(message.text());
    }
}
~~~

App trực tiếp khai báo dependency tới service; readability tới model được truyền qua `requires transitive` của service. Cả service và model đều export package API cần thiết.

### 5.4. Biên dịch toàn bộ module cùng lúc

Đứng tại thư mục `project`:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

Trên Windows PowerShell:

~~~powershell
javac --module-source-path src -d mods -m com.acme.model,com.acme.service,com.acme.app
~~~

Compiler đọc module source path, tìm source theo tên module và đặt compiled output theo module:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/api/Message.class
├── com.acme.service/
│   ├── module-info.class
│   └── com/acme/service/api/GreetingService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

### 5.5. Chạy bằng module path

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Lệnh một dòng:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Xin chào, JPMS
~~~

Ứng dụng chỉ chạy sau khi launcher tìm được main module và những dependency bắt buộc. Runtime ở đây dựa trên compiled module descriptors và thư mục `mods` được cung cấp.

## 6. Từ compile graph tới runtime graph

Với ví dụ trên, cả hai giai đoạn đều dùng những khai báo module:

~~~text
COMPILE TIME

javac
  |
  +-- com.acme.model
  +-- com.acme.service ---> com.acme.model
  +-- com.acme.app     ---> com.acme.service
                             |
                             +-- transitive readability tới model

RUNTIME

java -m com.acme.app
  |
  +-- resolve com.acme.app
        |
        +-- com.acme.service
                |
                +-- com.acme.model
  |
  +-- define modules in boot layer
  |
  +-- load Main and invoke main()
~~~

Điều tương đồng: module descriptor xác định dependency và ranh giới API ở cả compile và runtime.

Điều khác biệt: compiler làm việc với source/compiled artifacts trong một môi trường build; launcher resolve các module hiện diện trong **runtime image và module path của tiến trình**. Nếu hai môi trường không thống nhất, kết quả có thể khác.

| Khía cạnh | Compile-time | Run-time |
|---|---|---|
| Công cụ | `javac`, Maven/Gradle compiler tasks | Java launcher và JVM |
| Đầu vào | Source, descriptor, compile module path | Compiled descriptors/JAR, runtime image và runtime module path |
| Root modules | Các module được yêu cầu biên dịch hoặc root do tool xác định | Main module và những root theo chế độ khởi chạy |
| Mục tiêu | Kiểm tra type, readability, accessibility; tạo bytecode | Resolve configuration, tạo layer, nạp class, thực thi |
| Lỗi điển hình | `module not found`, `package is not visible` | `FindException`, `LayerInstantiationException`, `NoClassDefFoundError`, lỗi truy cập runtime |

Đừng coi hai graph luôn có đúng cùng tập node chỉ vì mã nguồn và file `module-info.java` không đổi. Các module ngoài dependency bắt buộc hoặc các plugin/service provider được chọn thêm có thể khác theo môi trường.

## 7. requires, requires transitive và requires static

Ba chỉ thị này ảnh hưởng khác nhau đến cách đọc graph.

### 7.1. requires: dependency bắt buộc

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App cần module service để biên dịch với API của service; service cũng là dependency bắt buộc khi resolve app ở runtime.

Nếu thiếu module service trên runtime module path, launcher có thể thất bại **trước khi gọi main()**:

~~~text
java.lang.module.FindException:
Module com.acme.service not found, required by com.acme.app
~~~

Thông báo cụ thể phụ thuộc JDK và lệnh khởi chạy, nhưng nguyên nhân là dependency bắt buộc không được giải quyết.

### 7.2. requires transitive: truyền readability

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

Module app đọc service cũng đọc được model theo quan hệ transitive. Điều này cần thiết trong ví dụ khi public API của service trả về `Message` thuộc model.

Nếu thay bằng:

~~~java
requires com.acme.model;
~~~

thì app chỉ có `requires com.acme.service;` không tự có readability tới model. Nếu app trực tiếp dùng `Message`, nên khai báo dependency đọc model hoặc thiết kế lại API phù hợp.

**`requires transitive` truyền readability, không tự export những package bị module model giữ nội bộ.**

### 7.3. requires static: dependency bắt buộc ở compile-time, tùy chọn ở runtime

Ví dụ thư viện annotation:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Khi compile, compiler cần nhìn thấy module annotations. Nhưng module này được phép vắng mặt ở runtime, miễn mã thực thi không cần nạp kiểu từ module đó tại thời điểm chạy.

Tình huống phổ biến là annotation chỉ dùng phục vụ compile-time và không cần reflection ở runtime.

Phân biệt:

| Chỉ thị | Yêu cầu ở compile-time | Bắt buộc hiện diện ở runtime? | Readability tới client phụ thuộc? |
|---|---|---|---|
| `requires M;` | Có | Có | Không tự truyền |
| `requires transitive M;` | Có | Có | Có, theo quy tắc transitive |
| `requires static M;` | Có | Không bắt buộc | Không tự truyền như transitive |

Với dependency tùy chọn, hãy kiểm tra xem runtime có thật sự sử dụng class đó không. `requires static` không làm class tự xuất hiện; nếu mã nạp trực tiếp một kiểu từ module vắng mặt, lỗi runtime vẫn có thể xảy ra.

### 7.4. Khi static và transitive kết hợp

JPMS còn cho phép:

~~~java
requires static transitive com.acme.annotations;
~~~

Đây là dependency liên quan compilation và khả năng truyền readability khi phù hợp, nhưng vẫn không bắt buộc module đó phải có mặt ở runtime theo ý nghĩa của static dependency. Chỉ dùng tổ hợp này khi API public thật sự phơi bày kiểu từ dependency tùy chọn; đừng dùng để “chữa” mọi lỗi thiếu module.

## 8. Ba trạng thái một module có thể có

Xét module `java.sql` trên một runtime image:

1. **Có trong image:** JDK/runtime đã đóng gói module này.
2. **Observable:** module finder/resolution có thể nhìn thấy module trong ngữ cảnh hiện tại.
3. **Resolved:** module được chọn vào configuration của ứng dụng.

Một module có thể **có trong image** nhưng chưa tham gia boot layer. Một module JAR có thể tồn tại trong thư mục nhưng không observable nếu không được đưa vào module path.

Kiểm tra các system modules:

~~~bash
java --list-modules
~~~

Kiểm tra module descriptor:

~~~bash
java --describe-module java.sql
~~~

Kiểm tra graph được resolve khi chạy ứng dụng:

~~~bash
java --module-path mods \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

`--show-module-resolution` phù hợp để xác nhận những module nào được chọn và quan hệ resolution của chính lệnh chạy đó. Ngược lại, `--list-modules` nói về module observable, không phải danh sách những node chắc chắn đã resolve.

## 9. Khi compile thành công nhưng runtime thất bại

Đây là nhóm lỗi rất quan trọng khi chuyển từ classpath sang JPMS hoặc triển khai lên môi trường khác.

### 9.1. Runtime module path thiếu dependency

Biên dịch thành công:

~~~bash
javac --module-source-path src -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

Sau đó tạo một môi trường chạy chỉ chứa app, không chứa service hoặc model.

Lệnh chạy trông có vẻ hợp lệ nhưng sẽ thất bại khi resolve dependency:

~~~bash
java --module-path runtime-only-app \
     -m com.acme.app/com.acme.app.Main
~~~

Vấn đề không nằm ở source code nữa mà ở **runtime artifact/module path**. Cần đưa đủ module bắt buộc vào deployment hoặc xây dựng runtime image đúng cấu hình.

### 9.2. Phiên bản thư viện runtime khác lúc compile

Compile có module `com.acme.service` phiên bản mới, nhưng production dùng JAR cũ cùng tên module. Khi chạy, module có thể vẫn được resolve nhưng bytecode không tương thích với API runtime.

Những lỗi có thể xuất hiện:

- `NoSuchMethodError` khi method từng tồn tại ở compile-time nhưng không có ở runtime.
- `NoSuchFieldError` khi field bị đổi hoặc thiếu.
- `IncompatibleClassChangeError` khi hình dạng class/interface không tương thích.
- `IllegalAccessError` khi bytecode cố truy cập vào API hoặc package không còn được phép.

Giải pháp là kiểm tra artifact thực tế, module descriptor và nguồn class được nạp, không chỉ kiểm tra tên module.

### 9.3. Class khởi tạo thất bại

Một module được resolve đầy đủ nhưng class bên trong vẫn có thể lỗi ở static initializer:

~~~java
public final class Configuration {
    static final String ENDPOINT =
        System.getenv("SERVICE_ENDPOINT");

    static {
        if (ENDPOINT == null) {
            throw new IllegalStateException("Missing SERVICE_ENDPOINT");
        }
    }
}
~~~

Lỗi này không chứng minh module graph sai. Nó xuất hiện sau resolution, khi class được khởi tạo. Trong một số trường hợp có thể thấy `ExceptionInInitializerError` hoặc `NoClassDefFoundError: Could not initialize class ...`.

### 9.4. Reflection vào package bị đóng

App compile với public API thành công; framework runtime muốn deep reflection vào field private của module khác và bị từ chối.

Lúc đó cần xem:

~~~java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to some.framework.module;
}
~~~

`opens` chỉ mở đúng package cho framework được chỉ định nếu có nhu cầu thực tế. Không nên đổi thành `open module` chỉ để bỏ qua chẩn đoán.

## 10. Khi compile thất bại dù JAR/module có mặt

### 10.1. Không tìm thấy module

Ví dụ compiler:

~~~text
error: module not found: com.acme.service
~~~

Có thể module path sai, module name không đúng hoặc dependency artifact chưa được build. Hãy kiểm tra:

~~~bash
jar --describe-module --file libs/service.jar
~~~

Nếu project dùng directory compiled module, kiểm tra rằng directory chứa `module-info.class` được đưa vào module path đúng cấp.

### 10.2. Module không đọc được module khác

Ví dụ:

~~~text
package com.acme.service.api is not visible
  (module com.acme.app does not read com.acme.service)
~~~

Tìm `requires com.acme.service;` trong `module-info.java` của app.

### 10.3. Package không export

Ví dụ:

~~~text
package com.acme.service.internal is not visible
  (module com.acme.service does not export it)
~~~

App có thể đã đọc được service, nhưng package nội bộ không được công bố. Chuyển sang API được hỗ trợ hoặc chủ động export package nếu đó thật sự là hợp đồng công khai.

### 10.4. Split package

Hai module cùng chứa package `com.acme.shared` và app đọc cả hai có thể gây lỗi:

~~~text
module com.acme.app reads package com.acme.shared
from both com.acme.alpha and com.acme.beta
~~~

Sửa bằng cách xác định module sở hữu package, di chuyển class hoặc đổi namespace; việc thêm `requires` hay `--add-exports` không thay đổi ownership của package.

## 11. Maven/Gradle graph khác JPMS graph

Trong build đa project, thường tồn tại hai đồ thị đồng thời:

~~~text
Maven/Gradle project dependencies
    -> quyết định build order
    -> đưa artifact lên compile/runtime paths

JPMS module-info.java
    -> mô tả named module
    -> quyết định readability và exports
    -> phục vụ compile/runtime resolution
~~~

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation project(':service')
}
~~~

và JPMS:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Hai khai báo này hỗ trợ lẫn nhau nhưng **không thay thế** nhau. Nếu chỉ có Gradle dependency, app chưa tự đọc named module service theo JPMS. Nếu chỉ có `requires` mà Gradle không cung cấp artifact service, compiler có thể không tìm được module.

Với Maven:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>service</artifactId>
  <version>1.0.0</version>
</dependency>
~~~

Khối dependency của Maven đưa artifact vào build graph, còn `requires com.acme.service;` vẫn cần đúng tên module thực tế trong descriptor.

Một build tool có thể dùng compile module path và runtime module path khác nhau. Cần đối chiếu cả hai khi app compile được nhưng chạy lỗi.

## 12. Classpath và unnamed module đứng ở đâu?

Trước JPMS, classpath là cơ chế phổ biến để đưa class vào ứng dụng:

~~~bash
java -cp "app.jar:libs/*" com.acme.app.Main
~~~

Trên Windows:

~~~powershell
java -cp "app.jar;libs/*" com.acme.app.Main
~~~

Các class trên classpath thuộc unnamed module của class loader tương ứng. Khi chuyển sang JPMS, cần hiểu:

- Named module khai báo `requires` tới **named module**, không khai báo `requires` tới unnamed module thông thường.
- Automatic module là JAR truyền thống nằm trên module path và có tên module theo quy tắc JPMS.
- Automatic module tạo cầu nối migration, nhưng không có descriptor explicit và có hành vi export rộng.
- Chuyển một JAR từ classpath sang module path có thể làm lộ split package hoặc dependency khác trước.

Đừng giả định mọi code đang chạy tốt trên classpath sẽ biên dịch ngay sau khi thêm `module-info.java`. Build có thể cần di chuyển dependency từng bước và cập nhật ranh giới API.

## 13. --add-modules, --limit-modules và các root

Các tùy chọn launcher có thể làm runtime graph khác với những gì bạn dự đoán chỉ từ source code.

### 13.1. --add-modules

~~~bash
java --module-path mods \
     --add-modules com.acme.tools \
     -m com.acme.app/com.acme.app.Main
~~~

`--add-modules` bổ sung root modules cần resolve. Nó phù hợp khi module không phải dependency bắt buộc trực tiếp từ main graph nhưng cần hiện diện theo cấu hình chạy.

### 13.2. --limit-modules

~~~bash
java --limit-modules java.base --list-modules
~~~

`--limit-modules` giới hạn universe of observable modules. Lệnh không xóa module khỏi runtime image, và cách tính universe còn xét dependency closure cùng các quy tắc cho main module/roots được bổ sung. Không nên dùng flag này như một cơ chế sandbox bảo mật.

### 13.3. --show-module-resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Đây là lựa chọn tốt để kiểm chứng graph thực tế, thay vì suy đoán từ danh sách JAR.

### 13.4. --add-reads, --add-exports, --add-opens

Trong migration legacy, có thể gặp những tùy chọn bổ sung quyền runtime/compile đặc biệt. Chúng có thể giúp chẩn đoán hoặc chuyển tiếp, nhưng không nên dùng thay thiết kế module rõ ràng:

- `--add-reads`: bổ sung quan hệ đọc.
- `--add-exports`: mở rộng export một package.
- `--add-opens`: cho phép deep reflection vào package.

Không dùng các flag này để che lỗi thiếu dependency, split package hay deploy sai artifact.

## 14. ServiceLoader và module graph runtime

Một plugin/service provider có thể không được gọi trực tiếp từ mã nguồn app. Vì vậy, module graph phục vụ dịch vụ có thể cần thêm module provider ở runtime.

Ví dụ contract:

~~~java
package com.acme.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Module SPI:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Module app:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

Module provider:

~~~java
module com.acme.greeter.impl {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

App có thể biên dịch chỉ với module SPI, vì lúc compile nó không tham chiếu trực tiếp class `DefaultGreeter`. Nhưng để `ServiceLoader` tìm provider trong một module layer, module provider phải được đưa vào configuration/layer phù hợp (chẳng hạn qua cấu hình root, service binding hoặc layer dành cho plugin).

Ví dụ sử dụng:

~~~java
ServiceLoader<Greeter> providers =
    ServiceLoader.load(Greeter.class);

for (Greeter provider : providers) {
    System.out.println(provider.greet("JPMS"));
}
~~~

Điểm cần nhớ: sự hiện diện của interface ở compile-time không tự bảo đảm có provider ở runtime. Đây là một dạng khác biệt giữa compile graph và runtime configuration.

## 15. ModuleLayer động và graph riêng

Không phải mọi module đều xuất hiện trong boot layer lúc khởi động. Ứng dụng có thể resolve một nhóm module plugin sau đó tạo layer riêng.

Ý tưởng:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    boot.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

Ví dụ là một đoạn mã đặt trong ngữ cảnh hợp lệ, chẳng hạn trong method có thể thực thi. Nó cho thấy:

1. Tìm module plugin từ vị trí cụ thể.
2. Resolve một configuration mới dựa trên boot configuration.
3. Định nghĩa module đó trong `ModuleLayer` mới.

Khi debug plugin, hỏi **module đã được resolve vào layer nào**, chứ không chỉ kiểm tra `ModuleLayer.boot().findModule()`.

Layer mới không thay thế boot layer, và class loader của layer cũng ảnh hưởng khả năng nạp class.

## 16. Cách kiểm tra compile graph và runtime graph

Một quy trình chẩn đoán hiệu quả:

### Bước 1: Xác định JDK và Java executable

~~~bash
java --version
javac --version
~~~

Nếu IDE, build server và production dùng Java khác nhau, kiểm tra executable thực tế và `java.home` trong tiến trình.

### Bước 2: Kiểm tra module descriptor

~~~bash
jar --describe-module --file libs/service.jar
~~~

Xác nhận tên module, `requires` và exports. Với output đã compile thành directory, kiểm tra có `module-info.class` đúng cấp.

### Bước 3: Kiểm tra compile module path

Đối chiếu compiler flags trong Maven/Gradle hoặc lệnh `javac`:

~~~bash
javac --module-path mods -d out \
    src/com.acme.app/module-info.java \
    src/com.acme.app/com/acme/app/Main.java
~~~

Tìm đúng artifact của module dependency. Lỗi `module not found` ở giai đoạn này thường không liên quan tới permission của package.

### Bước 4: Kiểm tra runtime module path

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Runtime phải thấy những module bắt buộc trong configuration. Kiểm tra các đường dẫn được deploy, không chỉ thư mục build trên máy phát triển.

### Bước 5: Hiển thị module resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Dùng log để đối chiếu root, dependencies và graph thực tế.

### Bước 6: Phân biệt missing module và missing class

Nếu module resolution thành công nhưng runtime báo `ClassNotFoundException` hoặc `NoClassDefFoundError`, tiếp tục kiểm tra:

- Class nằm trong JAR nào?
- JAR thực tế có đúng phiên bản không?
- Class loader nào thực hiện yêu cầu?
- Module có được resolve ở layer chứa class không?
- Có dependency bắc cầu hoặc static initialization bị lỗi không?

Một `ClassNotFoundException` do gọi `Class.forName()` không tự động có nghĩa module graph chưa resolve.

### Bước 7: Kiểm tra runtime class loading

Có thể dùng:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Log hỗ trợ tìm nguồn class được nạp. Nếu module được resolve nhưng class đến từ JAR không mong đợi, lỗi có thể nằm ở build/deploy artifact thay vì `requires`.

## 17. Các câu hỏi thường gặp

### Compile thành công có nghĩa runtime graph chắc chắn giống compile graph?

Không. Runtime có module path, runtime image, root selection, service providers và phiên bản artifact riêng. Những khác biệt đó có thể làm module resolution hoặc class loading thất bại.

### Một module được liệt kê trong java --list-modules có chắc đã vào boot layer?

Không. Lệnh liệt kê các module observable trong ngữ cảnh gọi; việc module được resolve vào boot layer phụ thuộc roots và dependencies.

### Module đã resolve có tự export toàn bộ package không?

Không. Explicit named module chỉ export các package mà descriptor công bố (hoặc được điều chỉnh bằng cơ chế phù hợp). Có quan hệ đọc không đồng nghĩa truy cập được implementation nội bộ.

### requires static có phải không cần dependency lúc compile?

Không. Từ khóa `static` ở đây làm dependency không bắt buộc tại runtime; compiler vẫn cần module để kiểm tra mã nguồn tham chiếu tới nó.

### requires transitive có biến model thành dependency runtime tùy chọn?

Không. Nếu chỉ dùng `requires transitive` mà không có `static`, model vẫn là dependency bắt buộc ở runtime. `transitive` chủ yếu thay đổi readability lan tới module consumer.

### Có nên đặt toàn bộ JAR trên module path rồi cho rằng graph đã đủ?

Không. Module path chỉ cung cấp nơi tìm module. Graph còn phụ thuộc roots, descriptors, khả năng resolution và cách thiết kế module.

### Nếu chỉ một plugin bị lỗi, có cần kiểm tra boot layer không?

Cần biết plugin được resolve ở boot layer hay layer động. Nếu được nạp trong `ModuleLayer` riêng, hãy kiểm tra configuration/layer và class loader tương ứng.

## 18. Tự kiểm tra

**Tình huống 1:** App có `requires com.acme.service;`, nhưng runtime module path chỉ chứa app. Compiler trước đó thành công. Khi chạy có thể xảy ra gì?

**Trả lời:** Runtime có thể thất bại ở module resolution vì không tìm thấy module service bắt buộc.

**Tình huống 2:** Service export package API nhưng app không có `requires` và không có readability gián tiếp. App có import class từ service được không?

**Trả lời:** Không. Export package không tự tạo quan hệ đọc; app cần có readability phù hợp.

**Tình huống 3:** App dùng `Message` từ model qua API của service. Service nên khai báo gì nếu model là một phần public API?

**Trả lời:** Có thể dùng `requires transitive com.acme.model;` để consumer đọc service cũng đọc model; model vẫn phải export package chứa `Message`.

**Tình huống 4:** Module annotation được khai báo `requires static`, biên dịch thành công. Nó có bắt buộc hiện diện ở runtime không?

**Trả lời:** Không bắt buộc chỉ vì chỉ thị static. Nhưng nếu mã runtime thực sự cần class từ module đó thì vẫn có thể phát sinh lỗi khi module vắng mặt.

**Tình huống 5:** `ModuleFinder.ofSystem().find("java.sql")` có giá trị nhưng `ModuleLayer.boot().findModule("java.sql")` rỗng. Hai kết quả có mâu thuẫn không?

**Trả lời:** Không. Một module có thể có trong runtime image nhưng không được resolve vào boot layer.

**Tình huống 6:** Module service đã resolved nhưng framework không thể reflection vào một private field. Nguyên nhân có khả năng là gì?

**Trả lời:** Package chưa được mở cho deep reflection; cần kiểm tra `opens`, qualified opens hoặc cấu hình framework.

**Tình huống 7:** App compile được với phiên bản API mới nhưng runtime dùng JAR service cũ thiếu method. Loại lỗi nào có thể xuất hiện?

**Trả lời:** Có thể gặp `NoSuchMethodError` hoặc lỗi liên kết nhị phân khác; không nên kết luận là thiếu `requires`.

**Tình huống 8:** Hai module cùng chứa `com.acme.shared` và app đọc cả hai. Lỗi liên quan tới graph có thể là gì?

**Trả lời:** Split package; cần tổ chức lại package ownership thay vì chỉ tăng `exports`.

**Tình huống 9:** Tại sao `--show-module-resolution` hữu ích hơn `--list-modules` khi debug một lệnh chạy cụ thể?

**Trả lời:** Vì nó thể hiện module graph thực sự được resolve cho lần khởi chạy, còn `--list-modules` chỉ liệt kê modules observable.

**Tình huống 10:** Một plugin không xuất hiện trong boot layer nhưng vẫn được nạp vào layer riêng. Điều này có bất thường không?

**Trả lời:** Không. Module có thể được resolve và định nghĩa trong một `ModuleLayer` mới sau khi ứng dụng khởi động.

## Tổng kết

**Compile-time**, **run-time** và **module graph** là ba góc nhìn gắn kết:

- Ở **compile-time**, `javac` dựa vào source, module descriptors và compile module path để xác thực dependency, kiểu và quyền truy cập.
- Ở **run-time**, Java launcher và JVM dựa vào runtime image, module path, root modules và descriptors để resolve configuration, tạo layer, nạp class và chạy code.
- **Module graph** liên kết hai giai đoạn thông qua các node module và quan hệ `requires`/readability. Tuy nhiên, tập module được tìm thấy, được chọn và thực sự có mặt có thể khác theo môi trường.

Khi gặp lỗi, đừng vội thêm flag hoặc JAR. Hãy lần lượt xác định **module có tồn tại**, **có observable**, **đã resolved**, **có readability**, **package có export**, rồi **class có được nạp/khởi tạo thành công**. Cách phân tách này giúp chẩn đoán JPMS rõ ràng và thiết kế ứng dụng modular bền vững.