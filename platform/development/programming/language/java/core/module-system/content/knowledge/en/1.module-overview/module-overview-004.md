# Biên dịch, chạy và phân phối ứng dụng modular

Một ứng dụng Java sử dụng Java Platform Module System (JPMS) cần đi qua ba chặng có liên hệ với nhau: biên dịch source thành các module, chạy các module trên module path và đóng gói những artifact cần thiết để người dùng có thể triển khai ứng dụng. Ở mỗi chặng, Java compiler, JVM và công cụ đóng gói đều dựa vào module descriptor để hiểu tên module, dependency và ranh giới truy cập.

Bài này sử dụng JDK 21 và một ví dụ có hai module:

- `com.example.greeter`: thư viện cung cấp API chào hỏi.
- `com.example.app`: ứng dụng chính phụ thuộc vào thư viện.

Mục tiêu là hiểu luồng làm việc từ source đến chương trình chạy được, sau đó lựa chọn cách phân phối phù hợp.

## 1. Chuẩn bị cấu trúc source cho nhiều module

Với một ứng dụng nhỏ, có thể đặt source của từng module trong thư mục riêng. Ví dụ:

~~~text
modular-demo/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/example/greeter/api/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Descriptor của thư viện:

~~~java
// src/com.example.greeter/module-info.java
module com.example.greeter {
    exports com.example.greeter.api;
}
~~~

Lớp API:

~~~java
// src/com.example.greeter/com/example/greeter/api/Greeter.java
package com.example.greeter.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Descriptor của ứng dụng:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeter;
}
~~~

Lớp main:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeter.api.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

Ví dụ thể hiện hai ranh giới khác nhau:

- Gradle/Maven hoặc cách tổ chức thư mục có thể xem đây là hai project/module source riêng.
- JPMS xem chúng là hai named module vì mỗi module có `module-info.java`.
- `com.example.app` khai báo `requires com.example.greeter`, còn module thư viện export package chứa API.

Tên thư mục source module ở ví dụ trùng với tên module để dễ đọc. Đây là quy ước bố trí source; tên module thực tế được xác định bởi khai báo trong `module-info.java`.

## 2. Biên dịch nhiều module bằng javac

Java compiler hỗ trợ biên dịch một hoặc nhiều module trong cùng một lần gọi. Tùy chọn `--module-source-path` chỉ ra nơi chứa source của các module; `-d` chỉ định thư mục output; `-m` hoặc `--module` chỉ các module cần biên dịch.

Đứng tại thư mục gốc `modular-demo`, chạy:

~~~bash
javac --module-source-path src -d out -m com.example.greeter,com.example.app
~~~

Ý nghĩa từng phần:

| Tùy chọn | Vai trò |
|---|---|
| `--module-source-path src` | Tìm source của các module dưới thư mục `src` |
| `-d out` | Ghi bytecode vào thư mục `out` |
| `-m com.example.greeter,com.example.app` | Biên dịch hai module được chỉ định |

Compiler đọc descriptor của cả hai module, kiểm tra dependency và quy tắc truy cập. Nếu ứng dụng import một kiểu từ package không được module thư viện export, hoặc module ứng dụng chưa khai báo dependency cần thiết, compiler sẽ báo lỗi.

Sau khi biên dịch thành công, output có dạng:

~~~text
out/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Mỗi thư mục con trực tiếp của `out` là một module đã biên dịch. `module-info.class` là module descriptor dạng bytecode mà công cụ Java dùng để nhận diện module.

### Biên dịch khi dependency nằm trong module path

Nếu module phụ thuộc vào một module đã được biên dịch hoặc một modular JAR bên ngoài, đưa vị trí chứa dependency vào `--module-path`.

Ví dụ thư mục `mods` đã có module thư viện:

~~~bash
javac --module-path mods --module-source-path src -d out -m com.example.app
~~~

Compiler sẽ tìm module `com.example.greeter` trong `mods` để biên dịch `com.example.app`. Dependency cần có trên module path và tên module thực tế phải khớp với tên trong directive `requires`.

Nếu dùng classpath thay cho module path, compiler có thể biên dịch theo mô hình truyền thống, nhưng khi đó các thư viện trên classpath không được xử lý như các named module tường minh. Hãy chọn đúng cơ chế dựa trên việc ứng dụng có sử dụng JPMS hay không.

## 3. Chạy ứng dụng trên module path

Sau khi biên dịch, có thể chạy trực tiếp từ các thư mục module trong `out`:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Hoặc truyền tham số cho chương trình:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main Phuong
~~~

Các phần của lệnh:

- `--module-path out` chỉ vị trí chứa các module đã biên dịch.
- `-m` hoặc `--module` chọn module cần khởi chạy.
- `com.example.app/com.example.app.Main` chỉ module `com.example.app` và lớp main đầy đủ tên package.

Khi khởi chạy, JVM phân giải module chính cùng các dependency cần thiết. Module `com.example.app` cần đọc `com.example.greeter`; descriptor của thư viện cho phép truy cập package `com.example.greeter.api`. Nếu dependency không có trong module path, tên module không khớp hoặc package chưa được export, chương trình có thể không khởi chạy được hoặc gặp lỗi truy cập lớp.

### Phân biệt module path và classpath khi chạy

Classpath là cơ chế tìm class truyền thống. Module path là cơ chế tìm module của JPMS.

~~~bash
# Mô hình classpath
java -cp libs/greeter.jar:app.jar com.example.app.Main

# Mô hình JPMS
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Dấu phân cách đường dẫn trong classpath/module path phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy (`;`), Linux và macOS dùng dấu hai chấm (`:`). Hai lệnh trên chỉ minh họa cách viết trên Linux/macOS; khi chạy trên Windows cần thay dấu phân cách phù hợp.

Không nên trộn hai mô hình một cách tùy tiện. Một ứng dụng modular cần đảm bảo các named module nằm trên module path để JVM có thể áp dụng descriptor. Thư viện cũ không có module descriptor vẫn có thể tham gia module path dưới dạng automatic module; nếu để trên classpath, chúng thuộc unnamed module.

## 4. Đóng gói từng module thành modular JAR

Thư mục output sau biên dịch có thể chạy trực tiếp, nhưng để phân phối thư viện hoặc ứng dụng, thông thường ta đóng gói module thành JAR.

Tạo thư mục chứa artifact:

~~~bash
mkdir -p mods
~~~

Đóng gói module thư viện:

~~~bash
jar --create --file mods/com.example.greeter.jar -C out/com.example.greeter .
~~~

Đóng gói module ứng dụng:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
~~~

Tùy chọn `-C` yêu cầu công cụ jar chuyển vào thư mục output của module trước khi lấy các file để đưa vào archive. Vì output có `module-info.class`, JAR tạo ra giữ được module descriptor và trở thành modular JAR.

Tùy chọn `--main-class` ghi nhận lớp main cho artifact. Khi cần cách khởi chạy rõ ràng, vẫn có thể chỉ định đầy đủ module và lớp main bằng `-m module/class`.

Sau khi đóng gói:

~~~text
mods/
├── com.example.greeter.jar
└── com.example.app.jar
~~~

Chạy các modular JAR:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

JVM tìm cả hai module trong `mods`, đọc descriptor của chúng và phân giải dependency. Thư mục chứa nhiều modular JAR có thể được dùng làm module path; không cần giải nén từng JAR.

## 5. Kiểm tra nội dung và descriptor của JAR

Trước khi phân phối, nên xác nhận JAR chứa đúng module descriptor và các package/class cần thiết.

Xem nội dung archive:

~~~bash
jar --list --file mods/com.example.greeter.jar
~~~

Xem module descriptor mà JAR công bố:

~~~bash
jar --describe-module --file mods/com.example.greeter.jar
~~~

Kết quả mô tả module thường thể hiện tên module, các package, dependency `requires` và package `exports`. Đây là cách nhanh để kiểm tra tên module mà công cụ Java nhận diện từ artifact.

Có thể xem dependency ở cấp module bằng:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Lệnh `jdeps` hỗ trợ phân tích dependency và một số vấn đề về module. Kết quả phụ thuộc vào cấu trúc và phiên bản JDK; nếu module có dependency ngoài, hãy đưa chúng vào module path khi phân tích.

Có thể yêu cầu Java kiểm tra tính hợp lệ của các module trên module path:

~~~bash
java --validate-modules --module-path mods
~~~

Các bước này giúp phát hiện sớm lỗi đóng gói, thiếu module hoặc cấu hình dependency không hợp lệ. Chúng không thay thế kiểm thử chức năng của ứng dụng.

## 6. Chạy modular JAR với main class

Có hai cách phổ biến để chỉ định điểm vào khi chạy module.

Cách tường minh, luôn nêu cả module và lớp main:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Cách chỉ nêu tên module:

~~~bash
java --module-path mods -m com.example.app
~~~

Cách thứ hai cần runtime xác định được main class mặc định của module. Có thể thiết lập thông tin main class khi đóng gói bằng `jar --main-class` như ví dụ ở trên; với các quy trình đóng gói khác, hãy kiểm tra metadata thực tế của artifact. Nếu chưa khai báo main class hoặc muốn tránh phụ thuộc metadata đó, dùng cách tường minh `module/class`.

Một modular JAR là artifact của module. Nó không nhất thiết là một ứng dụng độc lập có thể chạy mà không cần các module phụ thuộc. Nếu ứng dụng yêu cầu `com.example.greeter`, JAR tương ứng vẫn phải có mặt trên module path khi khởi chạy.

## 7. Phân phối ứng dụng modular

Có nhiều mức độ phân phối, từ cung cấp JAR cho môi trường Java có sẵn đến tạo runtime riêng hoặc bộ cài đặt theo hệ điều hành.

### 7.1. Phân phối các modular JAR

Đây là cách đơn giản nhất:

~~~text
distribution/
├── mods/
│   ├── com.example.app.jar
│   ├── com.example.greeter.jar
│   └── third-party-module.jar
└── README.txt
~~~

Người nhận cần cài đặt một JDK/JRE tương thích và chạy lệnh được tài liệu hóa:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Ưu điểm:

- Artifact nhỏ và dễ cập nhật từng module.
- Dependency được tách thành các JAR riêng.
- Phù hợp với ứng dụng nội bộ, thư viện hoặc môi trường đã quản lý sẵn Java runtime.

Điểm cần chuẩn bị:

- Ghi rõ phiên bản Java tối thiểu và cách cài runtime.
- Cung cấp đầy đủ module phụ thuộc, bao gồm dependency bên thứ ba.
- Ghi lại lệnh khởi chạy, tham số và cấu hình cần thiết.
- Đảm bảo module name ổn định và khớp với các directive `requires`.
- Kiểm tra quyền đọc file, cấu hình và tài nguyên mà ứng dụng cần tại môi trường triển khai.

Không nên giả định người dùng có cùng thư mục làm việc, cùng biến môi trường hoặc cùng cấu hình Java như máy phát triển.

### 7.2. Tạo custom runtime bằng jlink

Nếu muốn phân phối ứng dụng cùng một runtime Java đã được rút gọn theo các module cần thiết, có thể dùng `jlink`. Công cụ này tạo runtime image từ các module đã phân giải, bao gồm các module nền tảng cần thiết.

Ví dụ trên Linux/macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime-image
~~~

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime-image
~~~

Ý nghĩa:

- `--module-path` cung cấp module nền tảng của JDK và các module ứng dụng.
- `--add-modules com.example.app` chọn module gốc cho runtime image.
- `--output runtime-image` chỉ định thư mục chứa runtime được tạo.

`jlink` lần theo dependency graph để đưa các module cần thiết vào runtime image. Nếu ứng dụng cần một module không được tìm thấy, quá trình liên kết sẽ thất bại. Các thư viện không modular hoặc thành phần cần xử lý đặc biệt phải được đánh giá riêng; `jlink` không thể đóng gói tùy ý mọi JAR trên classpath như thể chúng là named module.

Có thể dùng runtime image vừa tạo để chạy ứng dụng:

~~~bash
runtime-image/bin/java --module-path mods -m com.example.app/com.example.app.Main
~~~

Trên Windows, executable nằm tại `runtime-image/bin/java.exe`.

Nếu muốn đóng gói cả ứng dụng vào một cấu trúc triển khai, hãy tổ chức runtime image và thư mục `mods` theo một layout cố định, sau đó kiểm tra lệnh khởi chạy bằng chính runtime được phân phối. Không nên kiểm thử chỉ bằng JDK trên máy phát triển rồi mặc định runtime rút gọn sẽ hoạt động giống hệt.

Ưu điểm của `jlink`:

- Người dùng không phải cài một JDK đầy đủ riêng.
- Runtime chỉ chứa các module nền tảng cần thiết cho ứng dụng.
- Có thể kiểm soát tốt hơn môi trường Java đi kèm ứng dụng.

Giới hạn:

- Runtime image gắn với nền tảng và kiến trúc hệ điều hành mục tiêu; cần build riêng cho từng nền tảng cần hỗ trợ.
- Các dependency phải phân giải được dưới dạng module phù hợp.
- Cần kiểm thử runtime image sau khi tạo, đặc biệt với reflection, service loading, locale, charset và các tính năng runtime mà ứng dụng sử dụng.

### 7.3. Tạo bộ cài đặt bằng jpackage

`jpackage` hỗ trợ đóng gói ứng dụng Java thành application image hoặc định dạng cài đặt phụ thuộc nền tảng, ví dụ MSI/EXE trên Windows, DMG/PKG trên macOS và DEB/RPM trên Linux (tùy hệ điều hành, công cụ hệ thống và cấu hình JDK).

Ví dụ tạo application image từ module:

~~~bash
jpackage \
  --name ModularDemo \
  --module-path mods \
  --module com.example.app/com.example.app.Main \
  --type app-image
~~~

Nếu đã tạo runtime image bằng `jlink`, có thể yêu cầu `jpackage` sử dụng runtime đó:

~~~bash
jpackage \
  --name ModularDemo \
  --runtime-image runtime-image \
  --module-path mods \
  --module com.example.app/com.example.app.Main \
  --type app-image
~~~

Để tạo installer, thay `app-image` bằng loại package được nền tảng hỗ trợ, ví dụ `msi`, `exe`, `dmg`, `deb` hoặc `rpm`. Không phải loại package nào cũng có thể tạo trên mọi hệ điều hành; cần build và kiểm thử trên nền tảng mục tiêu.

`jpackage` giúp người dùng cài đặt và mở ứng dụng theo cách gần với ứng dụng desktop thông thường. Nó không tự sửa lỗi dependency hoặc bảo đảm ứng dụng tương thích với mọi hệ điều hành. Hãy kiểm tra icon, tên sản phẩm, phiên bản, thư mục cài đặt, quyền truy cập, runtime và quy trình nâng cấp/gỡ cài đặt theo yêu cầu sản phẩm.

## 8. Dependency bên thứ ba và thư viện không modular

Ứng dụng thực tế thường dùng thư viện bên ngoài. Khi phân phối, cần xác định từng dependency là explicit module, automatic module hay thư viện chỉ được sử dụng theo classpath.

Một số cách kiểm tra:

~~~bash
jar --describe-module --file libs/example-library.jar
~~~

Nếu JAR không có module descriptor, công cụ có thể hiển thị tên automatic module được suy ra. Tên module suy ra từ tên file có thể thay đổi nếu tên JAR thay đổi; thư viện có thể cung cấp thuộc tính manifest `Automatic-Module-Name` để giữ tên ổn định.

Khi dependency nằm trên module path, descriptor của ứng dụng cần `requires` đúng tên module. Khi dependency chỉ được dùng trên classpath, nó thuộc unnamed module và không có descriptor tường minh để kiểm soát package như explicit module.

Khi lập gói phân phối, cần:

- Đưa đủ JAR dependency vào vị trí runtime có thể tìm thấy.
- Tránh để hai phiên bản khác nhau của cùng thư viện gây xung đột.
- Kiểm tra tên automatic module và module name thực tế bằng công cụ JDK.
- Xác nhận dependency nào cần có ở runtime, dependency nào chỉ dùng khi compile hoặc test.
- Đảm bảo giấy phép và điều kiện phân phối của thư viện bên thứ ba được đáp ứng.

Module descriptor không quản lý phiên bản thư viện theo kiểu dependency manager. JPMS giải quyết module name và quan hệ module; Gradle/Maven vẫn là nơi phù hợp để quản lý phiên bản artifact, repository và dependency resolution.

## 9. Service loading và runtime image

Nếu ứng dụng sử dụng `ServiceLoader`, module tiêu thụ cần khai báo `uses` và module cung cấp cần khai báo `provides ... with ...`. Các provider module phải có mặt trong môi trường module resolution để service có thể được khám phá.

Khi tạo runtime image, hãy kiểm tra các provider có thực sự được đưa vào image hay không. Có thể chỉ định thêm module gốc khi cần:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,com.example.payment.card \
  --output runtime-image
~~~

Ví dụ trên giả sử `com.example.payment.card` là module provider có trong module path. Tập module gốc cần chọn phụ thuộc thiết kế ứng dụng và cơ chế service binding; không nên thêm module theo phỏng đoán. Kiểm tra bằng cách chạy chức năng sử dụng service trên runtime image đã tạo.

Reflection và resource cũng cần được kiểm thử trong runtime rút gọn. Một số framework dựa vào quét classpath, reflection hoặc metadata động; các hành vi này có thể cần cấu hình module, resource hoặc runtime image bổ sung. Nếu ứng dụng dùng `opens`, hãy xác nhận descriptor đã được đóng gói đúng và module framework có mặt khi chạy.

## 10. Lỗi thường gặp khi biên dịch, chạy và đóng gói

**Không tìm thấy module được yêu cầu.** Kiểm tra module path, tên module hiển thị từ `jar --describe-module` và directive `requires`. Đảm bảo dependency được cung cấp ở cả môi trường compile và runtime phù hợp.

**Package không được export.** Nếu ứng dụng truy cập API từ module khác, kiểm tra package đó có được export trong descriptor của module cung cấp hay không. Một class public trong package không export vẫn không phải API có thể truy cập tự do từ named module khác.

**Chạy bằng classpath rồi mong JPMS áp dụng đầy đủ.** Nếu muốn kiểm tra readability và encapsulation của named module, hãy chạy với module path và module descriptor thực tế.

**Đóng gói JAR nhưng quên module-info.class.** Kiểm tra danh sách file trong JAR và dùng `jar --describe-module`. Nếu descriptor không có trong artifact, xem lại output compile và lệnh đóng gói.

**JAR chạy được trên máy phát triển nhưng thiếu dependency khi phân phối.** Máy phát triển có thể có thư viện trong cache hoặc cấu hình môi trường riêng. Hãy dựng thư mục distribution từ các artifact đã xác định, rồi chạy bằng đúng lệnh mà người dùng sẽ sử dụng.

**Không tìm thấy main class.** Kiểm tra tên lớp đầy đủ, module chứa lớp main, khai báo `--main-class` khi đóng gói nếu muốn chạy chỉ bằng tên module, hoặc chỉ định `module/class` tường minh.

**jlink báo không tìm thấy module.** Kiểm tra `--module-path` có chứa JDK `jmods` và các modular JAR ứng dụng hay không. Kiểm tra dependency graph và đảm bảo module gốc được chỉ định đúng.

**Ứng dụng chạy khác trên runtime image.** Kiểm tra service provider, resource, locale, charset, reflection, native library và các module nền tảng cần thiết. Runtime image rút gọn phải được kiểm thử như một sản phẩm triển khai riêng.

**Installer chỉ tạo được trên một số máy.** `jpackage` phụ thuộc nền tảng và công cụ đóng gói của hệ điều hành. Tạo installer trên nền tảng mục tiêu và kiểm tra cài đặt, khởi chạy, nâng cấp, gỡ cài đặt.

## 11. Quy trình triển khai đề xuất

Một quy trình có thể lặp lại cho ứng dụng modular:

1. **Thiết kế module:** đặt tên module, tách package API/internal và khai báo `requires`, `exports`, `opens`, `uses`, `provides` theo nhu cầu.
2. **Biên dịch:** dùng `javac --module-source-path` hoặc cấu hình build tool để compiler xử lý đúng module path.
3. **Chạy từ output:** khởi chạy bằng `java --module-path ... -m module/class` để xác nhận module resolution.
4. **Đóng gói:** tạo modular JAR cho từng module cần phân phối.
5. **Kiểm tra artifact:** dùng `jar --list`, `jar --describe-module`, `jdeps` và `java --validate-modules` khi phù hợp.
6. **Chọn hình thức phân phối:** JAR cho môi trường Java đã quản lý; `jlink` khi cần runtime image riêng; `jpackage` khi cần application image hoặc installer.
7. **Kiểm thử môi trường sạch:** chạy từ thư mục distribution mới tạo, không dựa vào classpath, cache hay biến môi trường chỉ tồn tại trên máy phát triển.
8. **Tài liệu hóa:** ghi phiên bản Java, nền tảng hỗ trợ, cách cài đặt, lệnh chạy, tham số, cấu hình và cách cập nhật.

Hình thức phân phối nên được chọn theo người sử dụng và môi trường triển khai. Thư viện dùng trong hệ thống đã quản lý Java có thể chỉ cần modular JAR. Ứng dụng nội bộ cần runtime nhất quán có thể dùng `jlink`. Ứng dụng desktop dành cho người dùng cuối có thể cần `jpackage` để cung cấp installer phù hợp hệ điều hành.

## 12. Tự kiểm tra

Trước khi coi một bản phát hành modular đã sẵn sàng, hãy trả lời:

1. Mỗi module source đã có descriptor đúng vị trí chưa?
2. Compiler đã biên dịch tất cả module cần thiết và kiểm tra dependency chưa?
3. Các module đã chạy được bằng module path trên môi trường sạch chưa?
4. Modular JAR có chứa `module-info.class` và đúng package/class chưa?
5. Tên module trong `requires` có khớp với tên thực tế của dependency không?
6. Các thư viện bên thứ ba đã được phân loại đúng là explicit module, automatic module hay classpath dependency chưa?
7. Nếu dùng `jlink`, runtime image có đủ module nền tảng, service provider và tài nguyên cần thiết không?
8. Nếu dùng `jpackage`, installer đã được tạo và kiểm thử trên hệ điều hành mục tiêu chưa?
9. Tài liệu phân phối đã nêu phiên bản Java, lệnh chạy, cấu hình và các dependency cần thiết chưa?

Biên dịch, chạy và phân phối là ba bước liên tục của một ứng dụng modular. Compiler kiểm tra source và quan hệ module; JVM phân giải module khi khởi chạy; các công cụ `jar`, `jlink` và `jpackage` biến kết quả thành artifact phù hợp để triển khai. Khi giữ module descriptor, module path và dependency của build nhất quán xuyên suốt các bước này, ứng dụng sẽ có ranh giới rõ ràng và dễ đóng gói, vận hành hơn.
