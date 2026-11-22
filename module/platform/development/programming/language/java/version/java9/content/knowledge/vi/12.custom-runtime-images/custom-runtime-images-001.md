# Vai trò của jlink trong giai đoạn liên kết

## Mục tiêu

Trong một ứng dụng Java modular, biên dịch và đóng gói JAR mới là hai bước đầu. Khi triển khai, ứng dụng vẫn cần một runtime có các mô-đun Java mà chương trình sử dụng. Công cụ **jlink** thực hiện giai đoạn liên kết: nó phân giải tập mô-đun đầu vào, lấy các dependency cần thiết và tạo một **custom runtime image** chứa runtime cùng các mô-đun ứng dụng đã chọn.

Bài này trình bày vai trò của jlink trong quy trình phát triển và triển khai JPMS, cách chọn mô-đun gốc, cách xử lý service provider, cách cấu hình runtime image và cách xác minh image sau khi tạo.

Sau bài này, bạn có thể:

- Phân biệt compile, package, link và run.
- Chuẩn bị module path cho jlink bằng JDK modules và modular JAR.
- Chọn root modules bằng --add-modules và hiểu dependency closure.
- Quyết định khi nào cần --bind-services.
- Tạo runtime image có launcher riêng.
- Tinh chỉnh kích thước image bằng các tùy chọn hiện hành.
- Kiểm tra mô-đun, launcher và hành vi của image trước khi phát hành.

## 1. jlink nằm ở đâu trong quy trình Java modular?

Quy trình triển khai một ứng dụng modular thường có bốn giai đoạn:

1. **Compile:** javac biên dịch mã nguồn thành bytecode và module descriptor.
2. **Package:** jar đóng gói các lớp và module-info.class thành modular JAR.
3. **Link:** jlink phân giải mô-đun và tạo runtime image.
4. **Run:** người dùng khởi chạy ứng dụng bằng runtime image đã tạo.

Ví dụ:

~~~text
Mã nguồn Java
    |
    v
javac
    |
    v
Các mô-đun đã biên dịch
    |
    v
jar
    |
    v
Modular JAR
    |
    v
jlink + JDK jmods
    |
    v
Custom runtime image
    |
    v
Launcher của ứng dụng
~~~

**javac** chịu trách nhiệm biên dịch mã nguồn. **jar** đóng gói mô-đun. **jlink** liên kết các mô-đun thành một runtime image có thể triển khai. jlink không biên dịch mã nguồn Java và cũng không biến bytecode thành native executable.

Một runtime image thường chứa:

- Runtime Java cần để chạy ứng dụng.
- Các mô-đun nền tảng được phân giải.
- Các mô-đun ứng dụng được chọn để liên kết.
- Native libraries, cấu hình runtime và dữ liệu đi kèm.
- Các lệnh Java hoặc launcher tùy chỉnh được tạo trong image.

Mục tiêu là cung cấp runtime phù hợp với tập mô-đun ứng dụng cần dùng. Image có thể nhỏ hơn một JDK đầy đủ, nhưng kích thước thực tế phụ thuộc vào dependency, service binding, resource và tùy chọn tối ưu hóa.

jlink được giới thiệu cùng JPMS trong Java 9 và vẫn là công cụ hiện hành trong các JDK mới. Nó được cung cấp trong JDK, không phải một công cụ runtime độc lập.

## 2. jlink nhận đầu vào nào?

jlink làm việc với mô-đun. Module path khi liên kết thường gồm hai nhóm đầu vào:

- Thư mục **jmods** của JDK đang dùng để liên kết.
- Thư mục chứa modular JAR hoặc JMOD của ứng dụng và dependency.

Ví dụ cấu trúc:

~~~text
project/
├── src/
│   └── com.acme.cli/
│       ├── module-info.java
│       └── com/acme/cli/Main.java
├── out/
│   └── com.acme.cli/
│       ├── module-info.class
│       └── com/acme/cli/Main.class
├── mods/
│   └── com.acme.cli.jar
└── image/
    └── runtime image được jlink tạo
~~~

JDK có thư mục jmods chứa các mô-đun nền tảng ở định dạng JMOD. Modular JAR của ứng dụng có module descriptor ở gốc JAR. jlink dùng các mô-đun này để phân giải và liên kết.

Một mô-đun ứng dụng tường minh có descriptor, ví dụ:

~~~java
module com.acme.cli {
    requires java.logging;
}
~~~

Tên mô-đun trong descriptor là định danh được dùng khi chọn root hoặc khai báo dependency. Tên file JAR có thể khác, nhưng tên mô-đun phải đúng.

### Những đầu vào không thay thế được module path

jlink không phải công cụ đóng gói tùy ý mọi JAR trên classpath. Một thư viện chưa có module descriptor hoặc chỉ là automatic module không thể được đưa trực tiếp vào runtime image như một named module đầu vào. Hãy chuyển dependency cần liên kết thành mô-đun có descriptor phù hợp, hoặc dùng giải pháp đóng gói khác cho phần mã chưa modular hóa.

Nếu ứng dụng còn dependency chỉ chạy trên classpath, cần xử lý kiến trúc và cách phân phối dependency đó trước khi chọn jlink làm công cụ tạo image.

## 3. Chọn mô-đun gốc bằng --add-modules

Tùy chọn quan trọng nhất để bắt đầu liên kết là:

~~~bash
jlink --module-path PATH --add-modules MODULES --output IMAGE
~~~

**--add-modules** chỉ định các root modules mà image phải chứa. Từ các root đó, module resolver tự động lấy các dependency requires cần thiết.

Ví dụ, ứng dụng có descriptor:

~~~java
module com.acme.cli {
    requires java.logging;
}
~~~

Khi chọn com.acme.cli làm root, dependency java.logging và các dependency tiếp theo của nó được phân giải. java.base là mô-đun nền tảng cơ bản và luôn có mặt trong runtime image.

Nếu ứng dụng có nhiều mô-đun gốc, liệt kê chúng bằng dấu phẩy:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli,com.acme.reporting \
      --output image
~~~

Các mô-đun được chọn có thể cùng nằm trong một ứng dụng. jlink sẽ liên kết dependency closure của các root đó.

### ALL-MODULE-PATH

Có thể dùng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules ALL-MODULE-PATH \
      --output image
~~~

ALL-MODULE-PATH đưa mọi mô-đun tìm thấy trên module path vào tập root. Cách này có thể hữu ích trong một số quy trình kiểm thử, nhưng dễ làm runtime image chứa nhiều mô-đun ứng dụng không cần thiết. Khi biết rõ entry point, hãy ưu tiên khai báo chính xác các root modules.

### --limit-modules

--limit-modules giới hạn tập mô-đun mà resolver có thể quan sát trong quá trình liên kết:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli \
      --limit-modules java.base,java.logging,com.acme.cli \
      --output image
~~~

Tùy chọn này có thể giúp giới hạn module universe cho một image chuyên biệt. Danh sách phải bao gồm các mô-đun cần thiết để phân giải root và dependency. Nếu giới hạn bỏ sót một mô-đun bắt buộc, quá trình liên kết sẽ thất bại.

## 4. Module path của jlink

Tùy chọn --module-path chỉ định nơi tìm các mô-đun:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli \
      --output image
~~~

Trong ví dụ:

- $JAVA_HOME/jmods chứa các mô-đun của JDK.
- mods chứa modular JAR của ứng dụng.
- com.acme.cli là root module.
- image là thư mục runtime image được tạo.

Dấu phân cách nhiều mục trong module path phụ thuộc hệ điều hành:

| Môi trường | Dấu phân cách |
|---|---|
| Windows | Dấu chấm phẩy ; |
| Linux | Dấu hai chấm : |
| macOS | Dấu hai chấm : |

Ví dụ PowerShell trên Windows:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.cli --output image
~~~

Ví dụ trên Linux hoặc macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.cli --output image
~~~

Nên chỉ rõ cả JDK jmods và module path của ứng dụng để lệnh có thể đọc, kiểm tra và tái lập dễ dàng. Hãy dùng JDK phù hợp với phiên bản runtime mà bạn muốn phân phối.

## 5. Service binding với --bind-services

Một mô-đun có thể khai báo uses để tiêu thụ service:

~~~java
module com.acme.app {
    requires com.acme.api;
    uses com.acme.spi.Formatter;
}
~~~

Một mô-đun khác cung cấp implementation:

~~~java
module com.acme.provider {
    requires com.acme.api;
    provides com.acme.spi.Formatter
        with com.acme.provider.UpperFormatter;
}
~~~

Nếu chỉ liên kết các root và dependency requires, provider không nhất thiết được thêm vào image chỉ vì ứng dụng khai báo uses. Khi muốn jlink bổ sung các service provider có thể tìm thấy trên module path, dùng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output image
~~~

**--bind-services** yêu cầu jlink liên kết các mô-đun cung cấp service và dependency của chúng. Điều này hữu ích khi ứng dụng cần service implementation ngay trong runtime image.

Cần lưu ý:

- Provider phải có mặt trên module path tại thời điểm liên kết.
- Provider cần khai báo provides trong module descriptor hoặc cơ chế provider tương ứng được JPMS hỗ trợ.
- Service consumer phải khai báo uses.
- Service binding có thể đưa thêm nhiều mô-đun vào image, bao gồm provider của các service nền tảng.
- Nên kiểm tra lại danh sách mô-đun sau liên kết để biết image thực tế chứa gì.

--bind-services là quyết định ở giai đoạn liên kết. Nó không tự biến thư mục plugin bên ngoài thành cơ chế nạp plugin động. Nếu ứng dụng cần tìm plugin được cài thêm sau khi runtime image đã phát hành, hãy thiết kế ModuleLayer và ServiceLoader ở runtime riêng.

## 6. Tạo launcher cho ứng dụng

Một runtime image có thể chứa lệnh Java chung. Để người dùng không cần nhớ module name và main class, có thể tạo launcher riêng bằng --launcher:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli \
      --launcher demo=com.acme.cli/com.acme.cli.Main \
      --output image
~~~

Cú pháp:

~~~text
--launcher <name>=<module>[/<mainclass>]
~~~

Trong đó:

- name là tên lệnh launcher được tạo.
- module là mô-đun ứng dụng.
- mainclass là lớp chứa main nếu cần chỉ định tường minh.

Launcher sử dụng runtime image đã liên kết. Trên Linux/macOS, lệnh thường nằm ở image/bin/demo. Trên Windows, jlink tạo launcher thực thi và tệp batch tương ứng, ví dụ image/bin/demo.bat.

Có thể truyền đối số ứng dụng sau tên launcher như khi chạy Java thông thường. Launcher không cần người dùng chỉ định lại module path của JDK bên ngoài vì runtime đã được chứa trong image.

## 7. Các tùy chọn tinh chỉnh runtime image

jlink có các tùy chọn giúp điều chỉnh dung lượng và nội dung runtime image. Chọn theo yêu cầu sản phẩm và kiểm thử image sau khi áp dụng.

| Tùy chọn | Vai trò |
|---|---|
| --output | Thư mục đích của runtime image |
| --add-modules | Các root modules cần liên kết |
| --module-path | Vị trí tìm mô-đun đầu vào |
| --bind-services | Bổ sung service provider modules và dependency của chúng |
| --launcher | Tạo lệnh khởi chạy ứng dụng |
| --strip-debug | Loại bỏ thông tin debug |
| --no-header-files | Không đưa C header files vào image |
| --no-man-pages | Không đưa manual pages vào image |
| --compress=zip-N | Nén resource trong image theo mức zip |
| --limit-modules | Giới hạn tập mô-đun có thể quan sát |
| --verbose | In thông tin chi tiết trong quá trình liên kết |
| --list-plugins | Liệt kê các plugin tối ưu hóa mà JDK hiện tại hỗ trợ |

### Compression

Trong JDK hiện đại, cú pháp compression dùng giá trị zip-N:

~~~bash
--compress=zip-6
~~~

Các mức thường dùng:

- zip-0: không nén resource.
- zip-6: mức nén mặc định trên JDK 24.
- zip-9: mức nén cao hơn.

Không dùng dạng số cũ như --compress=2 trong build mới. JDK 24 cảnh báo các giá trị số này đã deprecated và có thể bị loại bỏ trong phiên bản tương lai. Dùng zip-0 đến zip-9 để thể hiện ý định rõ ràng.

Nén có thể giảm dung lượng lưu trữ nhưng cần cân nhắc thời gian giải nén và đặc điểm tải ứng dụng. Hãy đo kích thước image và kiểm tra thời gian khởi động trong môi trường mục tiêu.

### Strip debug và loại bỏ tài liệu phát triển

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli \
      --strip-debug \
      --no-header-files \
      --no-man-pages \
      --output image
~~~

--strip-debug loại bỏ thông tin debug trong các thành phần phù hợp của image. --no-header-files và --no-man-pages loại bỏ tài liệu/header phục vụ phát triển native. Chỉ bật khi ứng dụng triển khai không cần những thành phần đó.

### Plugin của jlink

Một số tùy chọn tối ưu hóa được cung cấp dưới dạng plugin. Danh sách có thể thay đổi theo JDK và nhà cung cấp. Dùng:

~~~bash
jlink --list-plugins
~~~

để kiểm tra các plugin thực sự có trong JDK đang build. Không sao chép tùy chọn từ một JDK khác mà chưa kiểm tra khả năng hỗ trợ.

## 8. Dùng jdeps để xác định dependency cần liên kết

Khi chưa chắc ứng dụng cần mô-đun nền tảng nào, jdeps có thể phân tích dependency của ứng dụng modular.

Ví dụ:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.cli
~~~

Với ví dụ dùng java.logging, kết quả trên JDK 24:

~~~text
java.base,java.logging
~~~

Danh sách này giúp kiểm tra các mô-đun nền tảng mà ứng dụng tham chiếu. Nó hữu ích khi chuẩn bị lệnh jlink hoặc rà soát dependency sau khi thay đổi code.

jdeps phân tích dependency bytecode và module descriptor. Kết quả cần được đối chiếu với hành vi runtime thực tế, đặc biệt khi ứng dụng dùng reflection, ServiceLoader, resource được nạp theo tên hoặc thư viện tích hợp qua cấu hình.

Không nên bỏ một mô-đun chỉ vì jdeps không thấy tham chiếu tĩnh nếu ứng dụng cần mô-đun đó qua cơ chế động.

## 9. Ví dụ hoàn chỉnh: tạo custom runtime image

Ví dụ tạo ứng dụng modular có sử dụng java.logging, đóng gói thành JAR rồi liên kết runtime image có launcher riêng.

### Cấu trúc source

~~~text
src/
└── com.acme.cli/
    ├── module-info.java
    └── com/acme/cli/Main.java
~~~

Tệp src/com.acme.cli/module-info.java:

~~~java
module com.acme.cli {
    requires java.logging;
}
~~~

Tệp src/com.acme.cli/com/acme/cli/Main.java:

~~~java
package com.acme.cli;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.getLogger(Main.class.getName())
                .info("Linked runtime ready");
        System.out.println("Hello from custom runtime");
    }
}
~~~

### Biên dịch mô-đun

Chạy tại thư mục gốc project:

~~~bash
javac --release 17 -d out --module-source-path src -m com.acme.cli
~~~

Lệnh tạo class file và module-info.class dưới out/com.acme.cli.

### Đóng gói modular JAR

~~~bash
mkdir mods
jar --create --file mods/com.acme.cli.jar -C out/com.acme.cli .
~~~

Có thể xác nhận module descriptor:

~~~bash
jar --describe-module --file mods/com.acme.cli.jar
~~~

Kết quả cần thể hiện mô-đun com.acme.cli và dependency java.logging.

### Liên kết runtime image

Trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.cli \
      --launcher demo=com.acme.cli/com.acme.cli.Main \
      --strip-debug \
      --no-header-files \
      --no-man-pages \
      --compress=zip-6 \
      --output image
~~~

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.cli --launcher demo=com.acme.cli/com.acme.cli.Main --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output image
~~~

Lệnh này:

1. Đọc các mô-đun nền tảng từ JDK jmods và mô-đun ứng dụng từ mods.
2. Chọn com.acme.cli làm root.
3. Tự động phân giải java.logging và dependency cần thiết.
4. Tạo launcher demo.
5. Loại bỏ debug information, header files và man pages.
6. Nén resource bằng zip-6.
7. Ghi runtime image vào image.

Thư mục output phải phù hợp điều kiện của jlink: chưa tồn tại hoặc là thư mục rỗng. Hãy chọn một output path mới cho mỗi lần build để tránh ghi nhầm lên image đang được sử dụng.

### Chạy ứng dụng từ image

Linux/macOS:

~~~bash
./image/bin/demo
~~~

Windows:

~~~powershell
.\image\bin\demo.bat
~~~

Stdout của chương trình:

~~~text
Hello from custom runtime
~~~

Logger cũng ghi một dòng INFO ra stderr. Khi chạy trên JDK 24, thông báo có dạng:

~~~text
INFO: Linked runtime ready
~~~

Có thể chạy main class trực tiếp bằng Java trong image:

~~~bash
./image/bin/java --module com.acme.cli/com.acme.cli.Main
~~~

Trên Windows:

~~~powershell
.\image\bin\java.exe --module com.acme.cli/com.acme.cli.Main
~~~

### Kiểm tra mô-đun trong image

Dùng Java executable của chính image:

~~~bash
./image/bin/java --list-modules
~~~

Với JDK 24 và ví dụ trên, danh sách gồm:

~~~text
com.acme.cli
java.base@24.0.2
java.logging@24.0.2
~~~

Điều này cho thấy image có ứng dụng, java.base và java.logging. Các mô-đun JDK không liên quan đến dependency của ứng dụng không xuất hiện trong danh sách này.

Ví dụ đã được biên dịch bằng javac --release 17 và liên kết bằng jlink của JDK 24. Runtime image tạo ra là runtime JDK 24; tùy chọn --release 17 chỉ đặt baseline biên dịch cho bytecode/API của mã nguồn, không biến image thành runtime Java 17.

## 10. Service binding trong runtime image: ví dụ khái niệm

Giả sử ứng dụng có service consumer:

~~~java
module com.acme.app {
    requires com.acme.api;
    uses com.acme.spi.Formatter;
}
~~~

và provider module:

~~~java
module com.acme.provider {
    requires com.acme.api;
    provides com.acme.spi.Formatter
        with com.acme.provider.UpperFormatter;
}
~~~

Nếu com.acme.provider nằm trên module path lúc liên kết, có thể yêu cầu jlink bổ sung provider:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output image
~~~

Sau khi liên kết, dùng java --list-modules để xác nhận provider có mặt. Khi ứng dụng gọi ServiceLoader.load(Formatter.class), provider được liên kết vào image có thể được khám phá theo service configuration.

Trong kiểm thử trên JDK 24, ứng dụng dùng Formatter và provider UpperFormatter được liên kết bằng --bind-services. Khi chạy ứng dụng trong image, stdout là:

~~~text
JLINK
~~~

Service binding có thể đưa thêm nhiều mô-đun nền tảng vào image vì chúng cũng cung cấp service được dùng trong đồ thị mô-đun. Do đó, hãy so sánh danh sách mô-đun và kích thước image trước và sau khi bật tùy chọn này.

## 11. jlink và jpackage có vai trò khác nhau

jlink tạo runtime image chứa runtime Java và các mô-đun ứng dụng được liên kết. jpackage dùng để tạo gói phân phối ứng dụng theo nền tảng, chẳng hạn bộ cài hoặc gói ứng dụng phù hợp hệ điều hành.

| Công cụ | Vai trò |
|---|---|
| javac | Biên dịch source code |
| jar | Đóng gói modular JAR |
| jlink | Liên kết mô-đun thành custom runtime image |
| jpackage | Đóng gói ứng dụng thành gói cài đặt/phân phối |

Một quy trình có thể dùng jlink để tạo runtime image, sau đó dùng jpackage để tạo bộ cài chứa ứng dụng và runtime đó. jlink tự nó không tạo installer hệ điều hành.

## 12. Những giới hạn cần tính đến

### Runtime image gắn với nền tảng

Runtime image chứa native libraries và thành phần phụ thuộc nền tảng. Hãy tạo và kiểm thử image cho đúng hệ điều hành, kiến trúc CPU và môi trường triển khai dự kiến. Không giả định một image Windows có thể chạy nguyên trạng trên Linux hoặc macOS.

### Phiên bản JDK dùng để liên kết

Runtime image được tạo từ các mô-đun của JDK cung cấp jmods cho lệnh jlink. Nếu dùng JDK 24 để liên kết, image sẽ chứa runtime JDK 24. Biên dịch code bằng --release 17 không làm thay đổi phiên bản runtime này.

Nếu sản phẩm cần chạy trên Java 17, hãy dùng JDK 17 phù hợp để liên kết image và kiểm thử với đúng baseline đó.

### Dependency động và reflection

jdeps chủ yếu phân tích dependency có thể quan sát từ bytecode và module descriptor. Ứng dụng dùng reflection, ServiceLoader, tên lớp từ cấu hình hoặc resource động có thể cần mô-đun mà phân tích tĩnh không tự nhận ra.

Hãy kiểm tra module list và chạy test integration trên image thực tế. Bổ sung root modules hoặc bật service binding khi thiết kế ứng dụng yêu cầu.

### Kích thước không phải lúc nào cũng nhỏ hơn

Một image có thể lớn hơn dự kiến nếu root module kéo theo nhiều dependency, bật --bind-services hoặc giữ lại nhiều resource. Đừng giả định rằng bật tất cả tùy chọn tối ưu sẽ luôn làm ứng dụng nhanh hơn hoặc nhỏ hơn.

Đo kích thước, thời gian khởi động và hành vi trên môi trường đích trước khi chọn cấu hình phát hành.

### Module path phải có đủ mô-đun

Nếu jlink báo không tìm thấy mô-đun hoặc không giải quyết được dependency, kiểm tra tên mô-đun trong module-info.java, vị trí JAR/JMOD và module path. Tên file JAR không nhất thiết bằng tên mô-đun.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Module not found | Module path thiếu JAR/JMOD hoặc tên root sai | Kiểm tra --module-path và jar --describe-module |
| Module resolution failed | Dependency requires không có hoặc module graph xung đột | Kiểm tra module-info.java và dependency closure |
| Automatic module không được chấp nhận | Đầu vào chưa có descriptor phù hợp cho liên kết | Modular hóa dependency hoặc chọn phương án phân phối khác |
| Image thiếu provider | Chưa liên kết provider hoặc thiếu --bind-services | Kiểm tra uses/provides và module path tại thời điểm link |
| Launcher không chạy | Sai module/main class hoặc gọi sai tên launcher trên hệ điều hành | Kiểm tra --launcher và tệp trong image/bin |
| Image thiếu resource hoặc locale | Tối ưu hóa loại bỏ thành phần cần thiết hoặc chưa cấu hình plugin tương ứng | Kiểm tra plugin list và chạy integration test |
| Output path không hợp lệ | Thư mục đích đã có dữ liệu | Dùng thư mục output mới hoặc làm trống đúng thư mục build do bạn quản lý |
| Image chạy trên máy build nhưng lỗi máy đích | Khác hệ điều hành, kiến trúc, native dependency hoặc runtime expectation | Tạo image cho nền tảng mục tiêu và kiểm thử trên môi trường tương ứng |

Một quy trình chẩn đoán tốt là xác nhận module path, xác nhận root modules, đọc lỗi resolution, kiểm tra danh sách mô-đun trong image và chạy chính launcher được phát hành.

## 14. Quy trình build và kiểm tra có thể tái lập

Một pipeline liên kết nên thực hiện:

1. Biên dịch các mô-đun bằng JDK baseline đã chọn.
2. Đóng gói modular JAR.
3. Dùng jdeps --print-module-deps để hỗ trợ rà soát dependency.
4. Chọn root modules chính xác cho ứng dụng.
5. Chọn có cần --bind-services hay không.
6. Chạy jlink với module path JDK jmods và application modules.
7. Tạo launcher bằng --launcher nếu cần.
8. Chạy java --list-modules từ image vừa tạo.
9. Chạy integration test bằng launcher của image.
10. Kiểm tra image trên hệ điều hành và kiến trúc triển khai thực tế.
11. Ghi nhận phiên bản JDK, module roots, tùy chọn jlink và danh sách plugin được dùng.

Có thể lưu tùy chọn build trong script hoặc argument file để tái lập. jlink hỗ trợ đọc tùy chọn từ file bằng cú pháp @filename; hãy quản lý file này cùng cấu hình build.

## Kết luận

jlink đảm nhiệm giai đoạn liên kết trong quy trình triển khai ứng dụng JPMS. Nó nhận các mô-đun gốc, phân giải dependency, tùy chọn bổ sung service provider và tạo runtime image có thể chạy ứng dụng mà không cần cài một JDK đầy đủ trên máy đích.

Khi sử dụng jlink, hãy xác định module path và root modules chính xác, dùng --bind-services khi ứng dụng cần provider trong image, tạo launcher phù hợp và kiểm tra runtime image bằng chính Java executable của image. Dùng cú pháp compression hiện hành như zip-6, kiểm thử đúng nền tảng và phiên bản JDK mục tiêu, rồi mới đưa image vào quy trình phân phối.
